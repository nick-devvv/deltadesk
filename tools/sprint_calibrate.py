#!/usr/bin/env python3
"""tools/sprint_calibrate.py - fits the IV multipliers of the MODELED (BS, calibrated IV) option tapes on DEV, where real
Alpaca option trades exist (SPRINT_PLAN Amendment 5; sprint/modeled.py). Backtest data only: reads the sprint's own trade
files and cached stock bars, no network, no orders.

  python3 tools/sprint_calibrate.py                      # data/sprint/trades_*.csv.gz -> data/sprint/calib_modeled.json

For every real-tape DEV trade (files of specs with "tapes": "modeled" are excluded; one row per symbol, day, contract
and signal bar): ratio = iv_est (the BS-EST implied vol the engine solved from the real option's price at the decision)
/ the IV proxy of that symbol and day (20-session realized 1-minute volatility, prior sessions only, annualized on the
engine's calendar-minute year). The multiplier of each "<contract rule>|<side>" is the median ratio (quartiles, counts,
and medians by symbol and by setup are reported too). A key with fewer than 30 trades is marked thin: a modeled run that
needs it is refused. The contract rule of each trade comes from expanding its spec (sprint/specs/<spec_id>.json).
"""
import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from sprint import VERSION, data, engine, periods  # noqa: E402
from sprint import modeled as MD  # noqa: E402

USE = ["run_id", "symbol", "day", "setup", "side", "contract", "signal_idx", "iv_est"]


def spec_rules(specs_dir):
    """({run_id: contract rule} for real-tape specs, {spec_id: tapes mode})."""
    rules, modes = {}, {}
    for p in sorted(Path(specs_dir).glob("*.json")):
        try:
            spec = json.loads(p.read_text())
            runs = engine.expand(spec)
        except (ValueError, KeyError):
            continue
        modes[spec["spec_id"]] = spec.get("tapes", "real")
        if modes[spec["spec_id"]] != "real":
            continue
        for r in runs:
            rules[r["run_id"]] = r["exit"].contract
    return rules, modes


def spec_of_file(name):
    """trades_<spec>[@sX]_<YYYY-MM-DD>.csv.gz -> spec id (None if the name doesn't parse)."""
    if not (name.startswith("trades_") and name.endswith(".csv.gz")) or len(name) < len("trades_") + 18:
        return None
    stem = name[len("trades_"):-len(".csv.gz")]
    return stem[:-11].split("@")[0] if stem[-11] == "_" else None


def read_rows(files, rules, modes, log=print):
    rows, used, skipped = [], [], {}
    a, b = periods.DEV
    for f in files:
        sid = spec_of_file(f.name)
        if sid is None or sid not in modes:
            skipped[f.name] = "unknown spec"
            continue
        if modes[sid] != "real":
            skipped[f.name] = "MODELED spec (never used to calibrate)"
            continue
        try:
            df = pd.read_csv(f, compression="gzip", usecols=lambda c: c in USE, dtype={"signal_idx": str})
        except (OSError, ValueError, EOFError) as e:
            skipped[f.name] = f"unreadable: {e}"
            continue
        if not len(df):
            continue
        df = df.drop_duplicates(["symbol", "day", "contract", "signal_idx"])
        d = df["day"].astype(str).str[:10]
        keep = (d >= a.isoformat()) & (d <= b.isoformat())
        df = df[keep]
        df["rule"] = df["run_id"].astype(str).str.split("@").str[0].map(rules)
        rows += df.to_dict("records")
        used.append(f.name)
        log(f"  {f.name}: {len(df)} unique trades")
    return rows, used, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fit the MODELED-tape IV multipliers on DEV real-tape trades")
    ap.add_argument("--trades", default=None, help="folder with trades_*.csv.gz (default data/sprint)")
    ap.add_argument("--specs", default=str(HERE / "sprint" / "specs"))
    ap.add_argument("--data", default=None, help="cache root (default data/alpaca)")
    ap.add_argument("--out", default=None, help="output file (default data/sprint/calib_modeled.json)")
    ap.add_argument("--min-n", type=int, default=MD.MIN_CALIB)
    x = ap.parse_args(argv)
    a, b = periods.DEV
    periods.guard(a, b)
    folder = Path(x.trades or HERE / "data" / "sprint")
    out = Path(x.out or HERE / "data" / "sprint" / "calib_modeled.json")
    rules, modes = spec_rules(x.specs)
    files = sorted(folder.glob("trades_*.csv.gz"))
    print(f"sprint_calibrate: {len(files)} trade files in {folder}, DEV {a}..{b}, label {MD.LABEL}", flush=True)
    rows, used, skipped = read_rows(files, rules, modes)
    series = {}

    def proxy(sym, day):
        if sym not in series:
            series[sym] = data.Series(sym, data.read_stock(sym, a, b, x.data))
        d = date.fromisoformat(day)
        return MD.iv_proxy(series[sym], d) if d in series[sym].rth else None

    cal = MD.calibrate(rows, proxy, x.min_n)
    cal.update({"created": datetime.now().isoformat(timespec="seconds"), "engine": VERSION, "period": f"DEV {a}..{b}",
                "proxy": "sigma_1m (20 prior sessions, >= 10) x sqrt(525600)", "files_used": used, "files_skipped": skipped,
                "code_sha": hashlib.sha256((HERE / "sprint" / "modeled.py").read_bytes()).hexdigest()[:12]})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cal, indent=1, default=str))
    print(f"{'key':<16} {'n':>6} {'median':>7} {'q1':>7} {'q3':>7}  ok  by symbol", flush=True)
    for k, s in cal["keys"].items():
        print(f"{k:<16} {s['n']:>6} {s['median']:>7.3f} {s['q1']:>7.3f} {s['q3']:>7.3f}  {'yes' if s['ok'] else 'THIN'}  "
              + ", ".join(f"{sym} {v:.3f}" for sym, v in cal["by_symbol"].get(k, {}).items()), flush=True)
    need = sorted({MD.calib_key(r["exit"].contract, r["side"]) for n in ("hist_v1", "hist_val_v1")
                   for r in engine.expand(json.loads((Path(x.specs) / f"{n}.json").read_text()))} if (Path(x.specs) / "hist_v1.json").exists() else [])
    for k in need:
        s = cal["keys"].get(k)
        print(f"needed by hist_v1: {k}: " + ("MISSING (the modeled runs will be refused)" if not s else
                                            f"x{s['median']:.3f} (n={s['n']}{'' if s['ok'] else ', THIN: refused'})"), flush=True)
    print(f"skipped rows: {cal['skipped']}; skipped files: {len(skipped)}\ncalibration: {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
