#!/usr/bin/env python3
"""tools/sprint_study.py - the learner and the combined book over sprint trade files (research only; never trades).

  learn  walk-forward "when does this strategy work" models on chosen runs (sprint/learn.py)
  book   several runs traded together as one book (sprint/book.py)
  auto   the pre-registered pipeline: pick the candidate runs from the run log, run the learner on each, and combine the
         best run of each strategy family into one book, with and without a $150 desk daily stop

  python3 tools/sprint_study.py auto --trades "data/sprint/trades_*.csv.gz" --runs-csv "data/sprint/runs_*.csv"
  python3 tools/sprint_study.py learn --trades "data/sprint/trades_setups_v2_*.csv.gz" --runs setups_v2-001
  python3 tools/sprint_study.py book --trades "data/sprint/trades_*.csv.gz" --runs setups_v2-001,setups_v1-019 --daily-stop 150

auto's candidate rule (pre-registered 2026-10-31): base-cost runs (run ids without "@") on DEV with at least 60 trades,
PF >= 1.25 and PF at 2x slippage > 1.0; one per family (the entry name without its variant suffix: failed_break_w10 ->
failed_break, orb15/30/60 -> orb), the highest expectancy. Families with no candidate are listed as "none held up".
Every number printed is a BACKTEST (in-sample DEV unless the trade file says otherwise) with a MODELED spread.
"""
import argparse
import glob
import json
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from sprint import book, features, learn, periods  # noqa: E402


def family(entry):
    e = str(entry)
    if e.startswith("orb"):
        return "orb"
    if e.startswith("failed_break"):
        return "failed_break"
    return re.sub(r"_(w\d+|p\d+|pd|or|nocap)$", "", e)


def load_trades(patterns, runs):
    files = sorted({f for p in patterns for f in glob.glob(p)})
    parts = []
    for f in files:
        df = pd.read_csv(f, compression="gzip", low_memory=False)
        df = df[df["run_id"].isin(runs)]
        if len(df):
            parts.append(df)
    if not parts:
        return {}
    df = pd.concat(parts, ignore_index=True).drop_duplicates(subset=["run_id", "symbol", "day", "signal_idx", "entry_time"])
    out = {}
    for rid, g in df.groupby("run_id"):
        out[rid] = g.to_dict("records")
    return out


def candidates(runs_csv_patterns, period="DEV"):
    files = sorted({f for p in runs_csv_patterns for f in glob.glob(p)})
    if not files:
        return pd.DataFrame(), pd.DataFrame()
    d = pd.concat([pd.read_csv(f) for f in files], ignore_index=True).drop_duplicates("run_id", keep="last")
    d = d[(d["tool"] == "DeskEngine") & (~d["run_id"].astype(str).str.contains("@")) & (d["period_tag"] == period)]
    ok = d[(d["trades"] >= 60) & (d["profit_factor"] >= 1.25) & (d["pf_2x_slip"] > 1.0)].copy()
    ok["family"] = ok["setup"].map(family)
    best = ok.sort_values("expectancy", ascending=False).groupby("family", as_index=False).head(1)
    return d, best


def do_learn(by_run, root, min_train):
    out, md = {}, []
    for rid, rows in by_run.items():
        features.recompute(rows, root)
        res = learn.walk_forward(rows, min_train_months=min_train)
        out[rid] = res
        md.append(learn.report_md(rid, res))
    return out, md


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=["learn", "book", "auto"])
    ap.add_argument("--trades", nargs="+", default=["data/sprint/trades_*.csv.gz"])
    ap.add_argument("--runs", default="")
    ap.add_argument("--runs-csv", nargs="+", default=["data/sprint/runs_*.csv"])
    ap.add_argument("--from", dest="a", default=str(periods.DEV[0]))
    ap.add_argument("--to", dest="b", default=str(periods.DEV[1]))
    ap.add_argument("--daily-stop", type=float, default=None)
    ap.add_argument("--min-train-months", type=int, default=6)
    ap.add_argument("--data", default=None, help="cache root (default data/alpaca)")
    ap.add_argument("--out", default="data/sprint")
    x = ap.parse_args(argv)
    for d in (x.a, x.b):
        if any(lo <= date.fromisoformat(d) <= hi for lo, hi in periods.LOCKED.values()):
            print(f"refused: {d} is inside a locked period", file=sys.stderr)
            return 2
    md = [f"# Sprint study ({x.mode}), {date.today()}\n",
          "Every number is a BACKTEST with a MODELED spread, 1 contract per signal; DEV results are in-sample. Not financial advice.\n"]
    js = {}
    runs = [r for r in x.runs.split(",") if r]
    if x.mode == "auto":
        alld, best = candidates(x.runs_csv)
        fams = sorted({family(s) for s in alld.get("setup", pd.Series(dtype=str)).dropna()})
        md.append(f"Candidate rule: base cost, DEV, >= 60 trades, PF >= 1.25, PF 2x > 1.0, best per family. Runs in the log: {len(alld)}.\n")
        md.append("| family | candidate | trades | exp $ | PF | PF 2x |\n|---|---|---|---|---|---|")
        for f in fams:
            r = best[best["family"] == f]
            if len(r):
                r = r.iloc[0]
                md.append(f"| {f} | {r['run_id']} | {r['trades']} | {r['expectancy']} | {r['profit_factor']} | {r['pf_2x_slip']} |")
            else:
                md.append(f"| {f} | none held up | | | | |")
        runs = list(best["run_id"]) if len(best) else []
        js["candidates"] = runs
    if not runs:
        md.append("\nNo runs to study.\n")
    else:
        by_run = load_trades(x.trades, runs)
        missing = [r for r in runs if r not in by_run]
        if missing:
            md.append(f"\nNo trades found in the trade files for: {', '.join(missing)}\n")
        if x.mode in ("learn", "auto") and by_run:
            js["learn"], m = do_learn(by_run, x.data, x.min_train_months)
            md += ["\n## When does each strategy work? (walk-forward learner)\n"] + m
        if x.mode in ("book", "auto") and len(by_run) >= 1:
            md.append("\n## Combined book\n")
            res = book.combine(by_run, x.a, x.b)
            md.append(book.report_md(res))
            js["book"] = res
            stop = x.daily_stop or (150.0 if x.mode == "auto" else None)
            if stop:
                res2 = book.combine(by_run, x.a, x.b, daily_stop=stop)
                md.append(book.report_md(res2))
                js["book_daily_stop"] = res2
    out = Path(x.out)
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"study_{x.mode}_{date.today()}.md"
    p.write_text("\n".join(md))
    (out / f"study_{x.mode}_{date.today()}.json").write_text(json.dumps(js, default=str, indent=1))
    print("\n".join(md))
    print(f"\nstudy report: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
