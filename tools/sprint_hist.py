#!/usr/bin/env python3
"""tools/sprint_hist.py - Layer 1 of the free 2016-2023 history check (SPRINT_PLAN Amendment 5): the sprint's surviving
entries and filters on STOCK bars only (sprint/underlying.py), no option model. Backtest only: reads cached Alpaca stock
bars (pulled by tools/sprint_pull.py --period HIST), no network, no orders, no broker code.

  python3 tools/sprint_hist.py                                  # HIST = 2016-01-04..2024-01-31
  python3 tools/sprint_hist.py --from 2018-01-02 --to 2018-12-31   # a sub-range (labeled as such)

Writes data/sprint/hist_layer1_<date>.md (the report with the pre-registered readings), .json (every number) and
_trades.csv.gz (every observation). Any range touching L1/L2 is refused (sprint/periods.guard); the history before the
period (from periods.WARMUP["HIST"]; 70 days before a sub-range's start) feeds indicators only.
"""
import argparse
import csv
import gzip
import io
import json
import socket
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from sprint import data, periods  # noqa: E402
from sprint import underlying as U  # noqa: E402

COLS = ["strategy", "symbol", "day", "side", "signal_idx", "signal_price", "invalid", "entry_idx", "entry", "stop", "risk",
        "exit_idx", "exit", "exit_reason", "r", "pct", "mfe_r", "ref", "close_1525", "extreme", "minutes_left", "sigma_rem_pct",
        "move_pct", "ext_pct", "z_close", "z_ext", "large", "large_ext"]


def load(symbols, h0, b, root=None, need_vixy_1m=True):
    series = {s: data.Series(s, data.read_stock(s, h0, b, root)) for s in symbols}
    aux = {"VIXY_D": data.read_daily("VIXY", root)}
    if need_vixy_1m:
        v = data.read_stock("VIXY", h0, b, root)
        aux["VIXY"] = data.Series("VIXY", v) if v is not None else None
    return series, aux


def main(argv=None):
    ap = argparse.ArgumentParser(description="Layer 1 (stock signal only) of the 2016-2023 history check")
    ap.add_argument("--from", dest="a")
    ap.add_argument("--to", dest="b")
    ap.add_argument("--spec", default=str(U.SPEC))
    ap.add_argument("--data", default=None, help="cache root (default data/alpaca)")
    ap.add_argument("--out", default=None, help="output folder (default data/sprint)")
    ap.add_argument("--host", default=None)
    ap.add_argument("--today", default=None)
    x = ap.parse_args(argv)
    pa, pb = periods.HIST
    a = date.fromisoformat(x.a) if x.a else pa
    b = date.fromisoformat(x.b) if x.b else pb
    h0 = periods.WARMUP["HIST"] if a == pa else a - timedelta(days=70)       # history for indicators only
    if periods.overlaps(h0, a):                                               # never reach back into a locked period
        h0 = a
    try:
        periods.guard(h0, b)
    except periods.LockedPeriod as e:
        print(str(e), file=sys.stderr)
        return 2
    out = Path(x.out or HERE / "data" / "sprint")
    out.mkdir(parents=True, exist_ok=True)
    today = x.today or date.today().isoformat()
    tag = "HIST" if (a, b) == (pa, pb) else f"HIST[{a}..{b}]"
    strats = U.strategies(x.spec)
    syms = sorted({s for st in strats for s in st["symbols"]})
    t0 = time.time()
    print(f"sprint_hist (Layer 1, {U.LABEL}): {tag} {a}..{b}, history from {h0}, symbols {','.join(syms)}, "
          f"strategies {', '.join(s['name'] for s in strats)}", flush=True)
    vix_1m = any(f.startswith("vixy_") and "pctl" not in f for s in strats for f in s["filters"])
    series, aux = load(syms, h0, b, x.data, vix_1m)
    for s, se in series.items():
        n = sum(1 for d in se.days if a <= d <= b)
        print(f"  {s}: {n} sessions in the period ({len(se.days)} loaded)", flush=True)
    vd = aux.get("VIXY_D")
    print(f"  VIXY daily: {'MISSING (percentile filters skip every signal)' if vd is None else str(len(vd)) + ' closes'}; VIXY 1m: "
          f"{'not needed' if not vix_1m else ('MISSING' if aux.get('VIXY') is None else str(len(aux['VIXY'].days)) + ' sessions')}", flush=True)
    res = U.run(series, aux, a, b, strats, progress=lambda m: print(m, flush=True))
    summ = U.summarize(res, strats)
    meta = {"at": datetime.now().strftime("%Y-%m-%d %H:%M"), "host": x.host or socket.gethostname(), "spec": x.spec,
            "spec_sha": periods.sha256_file(x.spec), "period": tag, "from": a.isoformat(), "to": b.isoformat(), "warm_from": h0.isoformat(),
            "coverage": ", ".join(f"{s}: {sum(1 for d in se.days if a <= d <= b)} sessions" for s, se in sorted(series.items())),
            "label": U.LABEL, "seconds": round(time.time() - t0, 1)}
    stem = out / f"hist_layer1_{today}"
    md = U.render(summ, a, b, meta)
    Path(f"{stem}.md").write_text(md)
    Path(f"{stem}.json").write_text(json.dumps({"meta": meta, "strategies": summ}, indent=1, default=str))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for s in strats:
        for t in res[s["name"]]["trades"]:
            w.writerow(t)
    with gzip.open(f"{stem}_trades.csv.gz", "wt") as f:
        f.write(buf.getvalue())
    for name, o in summ.items():
        ov = o["overall"]
        if o["kind"] == "stop":
            head = f"{ov.get('trades', 0)} trades, exp {ov.get('expectancy')}R, PF {ov.get('profit_factor')}"
        else:
            head = f"{ov.get('n', 0)} days, large-move rate {ov.get('large_rate')}"
        g = o.get("reading")
        print(f"layer1 {name}: {head}" + (f"; {g['name']}: {'YES' if g['verdict'] else 'NO'}" if g else " (context)"), flush=True)
    print(f"done in {time.time() - t0:.0f}s\nreport: {stem}.md\njson:   {stem}.json\ntrades: {stem}_trades.csv.gz", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
