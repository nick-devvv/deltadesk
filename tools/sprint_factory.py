#!/usr/bin/env python3
"""tools/sprint_factory.py - SPRINT_PLAN Amendment 9: the 10-year strategy factory (research only; reads trade files,
never trades, no network).

  python3 tools/sprint_factory.py                      # the newest factory trade files under data/sprint
  python3 tools/sprint_factory.py --hist data/sprint/trades_factory_hist_v1_2026-11-02.csv.gz \\
                                  --dev data/sprint/trades_factory_dev_v1_2026-11-02.csv.gz

Reads the trades of the 21 factory runs on HIST (factory_hist_v1: option prices MODELED (BS, calibrated IV)) and on DEV
(factory_dev_v1: REAL Alpaca option prices), checks that the two specs hold the same 21 runs in the same order, and runs
sprint/factory.py: per strategy the all-days numbers, the rule found on 2016-2019 and its two holdouts, the walk-forward
learner, the verdict; then the book of the survivors and the "everything unfiltered" book.
Writes data/sprint/factory_<date>.md and .json and prints the summary table. Refuses trade rows dated inside L1 or L2,
or a HIST/DEV row outside its own period.
"""
import argparse
import csv
import glob
import json
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from sprint import engine, factory, features, periods, runner  # noqa: E402
from sprint import report as R  # noqa: E402


def newest(pattern):
    files = sorted(f for f in glob.glob(pattern) if "@" not in Path(f).name)
    return files[-1] if files else None


def load(path, run_ids, src):
    df = pd.read_csv(path, compression="gzip", low_memory=False)
    df = df[df["run_id"].isin(run_ids) & ~df["run_id"].astype(str).str.contains("@")]
    df = df.drop_duplicates(subset=["run_id", "symbol", "day", "signal_idx", "entry_time"])
    rows = df.to_dict("records")
    for r in rows:
        r["_src"] = src
        r["day"] = str(r["day"])[:10]
    return rows


def check_rows(rows):
    """Refuse locked dates and rows outside their own period. Returns None or the reason."""
    for r in rows:
        d = date.fromisoformat(r["day"])
        hit = periods.overlaps(d, d)
        if hit:
            return f"REFUSED: a trade on {d} is inside locked period {', '.join(hit)} ({r['run_id']})"
        lo, hi = periods.HIST if r["_src"] == "HIST" else periods.DEV
        if not lo <= d <= hi:
            return f"REFUSED: a {r['_src']} trade on {d} is outside {r['_src']} {lo}..{hi} ({r['run_id']})"
    return None


def run_log(patterns, ids):
    files = sorted({f for p in patterns for f in glob.glob(p)})
    rows = {}
    for f in files:
        try:
            with open(f) as fh:
                for r in csv.DictReader(fh):
                    if r.get("run_id") in ids:
                        rows[r["run_id"]] = r
        except OSError:
            continue
    return rows


def describe(r):
    stop, tp, tm, _ = R.describe(r)
    side = {"both": "both sides", "C": "calls", "P": "puts"}[r["side"]]
    return f"Rules: `{r['entry']}`, {side}, {'+'.join(r['symbols'])}, contract {r['exit'].contract}; stop: {stop}; target: {tp}; time: {tm}."


def main(argv=None):
    ap = argparse.ArgumentParser(description="SPRINT_PLAN Amendment 9: the 10-year strategy factory (research only)")
    ap.add_argument("--hist", default=None, help="HIST trade file (default: newest data/sprint/trades_factory_hist_v1_*.csv.gz)")
    ap.add_argument("--dev", default=None, help="DEV trade file (default: newest data/sprint/trades_factory_dev_v1_*.csv.gz)")
    ap.add_argument("--hist-spec", default=str(HERE / "sprint" / "specs" / "factory_hist_v1.json"))
    ap.add_argument("--dev-spec", default=str(HERE / "sprint" / "specs" / "factory_dev_v1.json"))
    ap.add_argument("--runs-csv", nargs="+", default=None, help="run logs (default data/sprint/runs_*.csv)")
    ap.add_argument("--data", default=None, help="cache root, only for recomputing missing features (default data/alpaca)")
    ap.add_argument("--out", default=str(HERE / "data" / "sprint"))
    ap.add_argument("--today", default=None)
    x = ap.parse_args(argv)
    t0 = time.time()
    out = Path(x.out)
    out.mkdir(parents=True, exist_ok=True)
    today = x.today or date.today().isoformat()
    specs = {k: json.loads(Path(p).read_text()) for k, p in (("HIST", x.hist_spec), ("DEV", x.dev_spec))}
    runs = {k: engine.expand(s) for k, s in specs.items()}
    for k in runs:
        runner.validate(runs[k])
    strip = lambda r: json.loads(engine.run_key(r))
    if [strip(r) for r in runs["HIST"]] != [strip(r) for r in runs["DEV"]] or \
            [r["block"] for r in runs["HIST"]] != [r["block"] for r in runs["DEV"]]:
        print("REFUSED: the HIST and DEV specs do not hold the same runs in the same order", file=sys.stderr)
        return 2
    if str(specs["HIST"].get("period", "")).upper() != "HIST" or specs["HIST"].get("tapes") != "modeled" or \
            str(specs["DEV"].get("period", "DEV")).upper() != "DEV" or specs["DEV"].get("tapes", "real") != "real":
        print("REFUSED: the HIST spec must be HIST with modeled tapes and the DEV spec DEV with real tapes", file=sys.stderr)
        return 2
    hist_file = x.hist or newest(str(out / f"trades_{specs['HIST']['spec_id']}_*.csv.gz"))
    dev_file = x.dev or newest(str(out / f"trades_{specs['DEV']['spec_id']}_*.csv.gz"))
    for k, f in (("HIST", hist_file), ("DEV", dev_file)):
        if not f or not Path(f).exists():
            print(f"no {k} trade file found (run tools/sprint_run.py on the {k} factory spec first)", file=sys.stderr)
            return 2
    print(f"sprint_factory: HIST {hist_file}, DEV {dev_file}", flush=True)
    rows = {"HIST": load(hist_file, {r["run_id"] for r in runs["HIST"]}, "HIST"),
            "DEV": load(dev_file, {r["run_id"] for r in runs["DEV"]}, "DEV")}
    why = check_rows(rows["HIST"] + rows["DEV"])
    if why:
        print(why, file=sys.stderr)
        return 2
    warnings = []
    for k, rs in rows.items():
        miss = [r for r in rs if factory.num(r.get("f_minute")) is None]
        if miss:
            warnings.append(f"{len(miss)} {k} trades had no entry features; recomputed from cached bars.")
            features.recompute(miss, x.data)
    ids = {r["run_id"] for k in runs for r in runs[k]}
    logs = run_log(x.runs_csv or [str(out / "runs_*.csv")], ids)
    if logs:
        dev_lab = sorted({(logs.get(r["run_id"]) or {}).get("slippage", "?").split("(")[-1].split(")")[0] for r in runs["DEV"]})
        hist_lab = sorted({(logs.get(r["run_id"]) or {}).get("slippage", "?").split("(")[-1].split(")")[0] for r in runs["HIST"]})
        note = f"{len(logs)} of 42 factory runs found; HIST spread {', '.join(hist_lab)}; DEV spread {', '.join(dev_lab)}."
        if any("MEASURED" in s or "sensitivity" in s for s in dev_lab + hist_lab):
            warnings.append("A factory run did not use the pre-registered 2% MODELED-SPREAD (see the run log).")
        for k in runs:
            for r in runs[k]:
                lg = logs.get(r["run_id"])
                n = sum(1 for t in rows[k] if t["run_id"] == r["run_id"])
                if lg is not None and int(lg.get("trades") or 0) != n:
                    warnings.append(f"{r['run_id']}: run log says {lg.get('trades')} trades, the trade file has {n}.")
    else:
        note = "no run-log rows found for the factory runs"
    strategies, meta_ids, cfg = [], {}, {}
    for rh, rd in zip(runs["HIST"], runs["DEV"]):
        name = rh["block"]
        strategies.append((name, [t for t in rows["HIST"] if t["run_id"] == rh["run_id"]] +
                           [t for t in rows["DEV"] if t["run_id"] == rd["run_id"]]))
        meta_ids[name] = {"HIST": rh["run_id"], "DEV": rd["run_id"]}
        cfg[name] = describe(rh)
    n_prior = runner.count_prior_trials(out)
    res = factory.run(strategies, n_prior)
    meta = {"today": today, "hist_file": hist_file, "dev_file": dev_file, "hist_spec": x.hist_spec, "dev_spec": x.dev_spec,
            "hist_sha": periods.sha256_file(x.hist_spec), "dev_sha": periods.sha256_file(x.dev_spec), "runlog_note": note,
            "warnings": warnings, "run_ids": meta_ids, "configs": cfg}
    md = factory.render(res, meta)
    mp, jp = out / f"factory_{today}.md", out / f"factory_{today}.json"
    mp.write_text(md)
    jp.write_text(json.dumps(factory.clean({"meta": meta, "result": res}), indent=1))
    print("\n".join(factory.summary_lines(res)))
    for w in warnings:
        print(f"WARNING: {w}")
    print(f"factory done in {time.time() - t0:.0f}s\nreport: {mp}\njson:   {jp}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
