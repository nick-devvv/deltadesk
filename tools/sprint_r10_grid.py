#!/usr/bin/env python3
"""tools/sprint_r10_grid.py - SPRINT_PLAN Amendment 15 (+ Amendment 16's stop "none" and R4), Addendum 15.3 and Addendum 15.5
(R1-R3 and the regime features): round 10's 0DTE exit / entry grid and its add-ons. Research only: reads cached bars, never
trades, no network. Every number is a BACKTEST; options MODELED on HIST, REAL on DEV.

  python3 tools/sprint_r10_grid.py                         # stage 1 (resumable) then stage 2
  python3 tools/sprint_r10_grid.py --stage compute         # stage 1 only (the slow part; re-run to resume)
  python3 tools/sprint_r10_grid.py --stage analyze         # stage 2 only, from the saved chunks
  python3 tools/sprint_r10_grid.py --limit-days 5          # smoke test: the first 5 sessions of each chunk (its own cache,
                                                           # frozen file and outputs, all named *_smoke; never the real ones)

Reads (data/alpaca unless --data): stocks/ (SPY, QQQ, IWM 1-minute bars: HIST from its 2015-11-01 warm-up, DEV), options/ and
options_next/ (DEV 0DTE and next-expiry bars, the existing pull), daily/VIXY.csv.gz (f_vixy_pctl), and run 4's MODELED
calibration (data/sprint/calib_modeled.json, --calib). No new pull is needed (sprint/r10grid.needed_option_contracts).
Stage 1 (sprint/r10grid.build_chunks): one pass per (period, symbol, year) over every entry, signal, contract and exit variant;
DEV first (its real picks give the round 10 calibration for d20-30t25, d55-70t60 and 15.3's contract, Amendment 5's method),
then HIST. Each chunk is saved to data/sprint/r10grid_cache/<period>_<symbol>_<year>.npz and reused on a re-run when the code
and inputs are the same, so an interrupted run resumes where it stopped and a finished one reproduces identical outputs.
Stage 2 (sprint/r10grid.analyze): every cell replayed; the per-entry choice on 2016-2019 only, frozen into
data/sprint/r10grid_frozen.json BEFORE any holdout readout (a re-run must reproduce the same choice or it stops); holdout 1
(MODELED) and holdout 2 (REAL, random-side twin seed 31); R2, R3, R4; 15.3 (with and without the day gates); R1; the
regime tables; the trials (7,587 this build; the deflated Sharpe uses the run logs' count + 7,767). Writes
data/sprint/r10grid_<date>.md and .json, r10grid_cells_<date>.csv.gz (every cell in every window), trades_r10grid_<date>.csv.gz
(the frozen cells and add-ons, real and twin, with the entry and regime features), trades_r10_af153_<date>.csv.gz,
trades_r10_r1_shares_<date>.csv.gz and trades_r10_r1_options_<date>.csv.gz. Refuses any row dated inside L1 or L2.
"""
import argparse
import csv
import glob
import gzip
import json
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from sprint import data, factory, periods, r10grid as G, runner, shares  # noqa: E402
from sprint import modeled as MD  # noqa: E402


def count_trials(out, patterns=None):
    """Rows in docs/research/sprint_runs.csv plus the run logs (default data/sprint/runs_*.csv), as round 9."""
    if not patterns:
        return runner.count_prior_trials(out)
    n = 0
    for f in [runner.RUN_LOG] + sorted({f for p in patterns for f in glob.glob(p)}):
        try:
            with open(f) as fh:
                n += max(0, sum(1 for _ in csv.reader(fh)) - 1)
        except OSError:
            pass
    return n


def check_rows(rows, what):
    for r in rows:
        d = date.fromisoformat(str(r["day"])[:10])
        hit = periods.overlaps(d, d)
        if hit:
            return f"REFUSED: a {what} row on {d} is inside locked period {', '.join(hit)}"
    return None


def write_rows(path, rows, cols=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = cols or (list(dict.fromkeys(k for r in rows for k in r.keys())) if rows else ["day"])
    with gzip.open(path, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return str(path)


def calib_note(calib, run4_path):
    if calib is None:
        return f"no run 4 calibration at {run4_path}: HIST (MODELED) not run"
    added = calib.get("r10_added") or {}
    parts = [f"run 4's {run4_path} where it has the key (n1d40-55t45|P: round 8's labeled d40-55t45|P fallback)"]
    for k, v in sorted(added.items()):
        parts.append(f"{k} from the round 10 DEV calibration: n {v.get('n')}, median {v.get('median')}"
                     + ("" if v.get("ok") else " (TOO FEW ROWS: its HIST cells are refused)"))
    return "; ".join(parts) + (". HIST numbers on d20-30t25, d55-70t60, 15.3's contract and n1d40-55t45 (modeled at the next NYSE "
                               "session, round 8) are NOT VALIDATED against real prices; run 4 validated d40-55t45 calls only "
                               "(failed-break, plain exit).")


def main(argv=None):
    ap = argparse.ArgumentParser(description="SPRINT_PLAN Amendment 15 / 16, Addenda 15.3 and 15.5: round 10's grid (research only)")
    ap.add_argument("--data", default=None, help="cache root (default data/alpaca)")
    ap.add_argument("--out", default=str(HERE / "data" / "sprint"))
    ap.add_argument("--cache", default=None, help="stage-1 chunk folder (default <out>/r10grid_cache)")
    ap.add_argument("--calib", default=None, help="run 4's MODELED calibration (default <out>/calib_modeled.json)")
    ap.add_argument("--today", default=None)
    ap.add_argument("--symbols", default=",".join(G.SYMBOLS))
    ap.add_argument("--periods", default="DEV,HIST")
    ap.add_argument("--stage", default="all", choices=("all", "compute", "analyze"))
    ap.add_argument("--runs-csv", nargs="+", default=None)
    ap.add_argument("--limit-days", type=int, default=None, help="first N sessions of each chunk (smoke test only)")
    x = ap.parse_args(argv)
    t_all = time.time()
    root = Path(x.data) if x.data else data.ROOT
    out = Path(x.out)
    out.mkdir(parents=True, exist_ok=True)
    smoke = "_smoke" if x.limit_days else ""                     # a smoke run never touches the real cache or frozen file
    cache = Path(x.cache) if x.cache else out / f"r10grid_cache{smoke}"
    today = (x.today or date.today().isoformat()) + smoke
    syms = [s.strip() for s in x.symbols.split(",") if s.strip()]
    pers = tuple(p.strip().upper() for p in x.periods.split(",") if p.strip())
    log = lambda s: print(s, flush=True)
    warnings = []
    log(f"sprint_r10_grid: {', '.join(syms)}; periods {', '.join(pers)}; cache {cache}; every number is a BACKTEST; L1/L2 never read")
    cp = Path(x.calib) if x.calib else out / "calib_modeled.json"
    run4 = MD.load_calib(cp) if cp.exists() else None
    if run4 is None and "HIST" in pers:
        warnings.append(f"No run 4 calibration at {cp}: HIST (MODELED) is not run, so no cell can be chosen.")
    if x.stage in ("all", "compute"):
        series = {}
        for sym in syms:
            for src in pers:
                a, b = (periods.WARMUP["HIST"], periods.HIST[1]) if src == "HIST" else periods.DEV
                ser = shares.load_series(sym, a, b, root)
                if ser.days:
                    series[(src, sym)] = ser
                else:
                    warnings.append(f"No {src} stock bars for {sym}.")
            log(f"  bars {sym}: " + ", ".join(f"{k[0]} {len(v.days)} sessions" for k, v in series.items() if k[1] == sym))
        vd = data.read_daily("VIXY", root)
        if vd is None:
            warnings.append("No VIXY daily file (data/alpaca/daily/VIXY.csv.gz): f_vixy_pctl and the VIXY tercile tables stay empty.")
        t0 = time.time()
        files, calib, sha = G.build_chunks(series, cache, run4, root=root, aux={"VIXY_D": vd}, log=log, limit_days=x.limit_days,
                                           symbols=syms, periods_=pers)
        log(f"stage 1 done in {(time.time() - t0) / 60:.1f} min: {len(files)} chunks in {cache}")
        if x.stage == "compute":
            return 0
    else:
        files = sorted(p for p in cache.glob("*.npz") if not p.name.endswith(".tmp.npz"))
        cf = cache / "r10grid_calib.json"
        calib = json.loads(cf.read_text()) if cf.exists() else None
    if not files:
        print("no stage-1 chunks: nothing to analyze", file=sys.stderr)
        return 2
    n_prior = count_trials(out, x.runs_csv)
    t1 = time.time()
    frozen_path = out / f"r10grid_frozen{smoke}.json"
    res, trades, cells = G.analyze(files, frozen_path, n_prior, log)
    for what, rows in (("grid trade", trades["tracked"]), ("15.3", trades["af"]), ("R1 shares", trades["r1_shares"]),
                       ("R1 options", trades["r1_options"])):
        why = check_rows(rows, what)
        if why:
            raise periods.LockedPeriod(why)
    log(f"stage 2 done in {time.time() - t1:.0f}s")
    files_out = {"cells": write_rows(out / f"r10grid_cells_{today}.csv.gz", cells),
                 "grid_trades": write_rows(out / f"trades_r10grid_{today}.csv.gz", trades["tracked"]),
                 "af153": write_rows(out / f"trades_r10_af153_{today}.csv.gz", trades["af"]),
                 "r1_shares": write_rows(out / f"trades_r10_r1_shares_{today}.csv.gz", trades["r1_shares"]),
                 "r1_options": write_rows(out / f"trades_r10_r1_options_{today}.csv.gz", trades["r1_options"])}
    meta = {"today": today, "warnings": warnings, "calib_note": calib_note(calib, cp), "frozen_path": str(frozen_path),
            "frozen_sha": res["frozen"]["sha256"], "chunks": [str(f) for f in files], "files": files_out,
            "files_note": "; ".join(f"{k} `{v}`" for k, v in files_out.items()) + f"; stage-1 chunks `{cache}` ({len(files)})"}
    md = G.render(res, meta)
    mp, jp = out / f"r10grid_{today}.md", out / f"r10grid_{today}.json"
    mp.write_text(md)
    jp.write_text(json.dumps(factory.clean({"meta": meta, "result": res}), indent=1, default=str))
    print("ROUND 10 GRID SUMMARY (BACKTEST; options MODELED on HIST, REAL on DEV)")
    print("\n".join(G.summary_lines(res)))
    for w in warnings:
        print(f"WARNING: {w}")
    print(f"round 10 grid done in {(time.time() - t_all) / 60:.1f} min\nreport: {mp}\njson:   {jp}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except periods.LockedPeriod as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
