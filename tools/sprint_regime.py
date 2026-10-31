#!/usr/bin/env python3
"""tools/sprint_regime.py - SPRINT_PLAN Amendment 6, holdout 2: the frozen regime rules and the HIST-trained learner,
scored on DEV's REAL option prices (research only; reads trade files, never trades).

  python3 tools/sprint_regime.py                       # default files under data/sprint
  python3 tools/sprint_regime.py --trades "data/sprint/trades_*.csv.gz" --hist "data/sprint/trades_hist_v1_*.csv.gz"

Rules (thresholds frozen in Amendment 6 from the 2016-2019 discovery set):
  F  10:30 far-OTM puts (DEV otm_v1-010 / HIST hist_v1-003): f_range_atr >= 0.52 and f_rvol >= 1.05
  G  11:00 far-OTM calls (DEV otm_v1-040 / HIST hist_v1-005): f_range_atr >= 0.61
  H  same: f_rvol >= 1.06
  I  same: f_range_atr >= 0.61 and f_rvol >= 1.06
  L-put / L-call  the Amendment 3 logit (sprint/learn.py) fit on ALL HIST trades of the run, applied to the DEV trades;
                  take when P(win) >= 0.5
Holdout-2 pass (pre-registered): PF >= 1.25, PF at 2x slippage > 1.0, at least 40 trades, and the total beats removing
the same number of trades by random whole days (2,000 draws, seed 23), p < 0.10. Also shown: two-month blocks,
without the best 5, by symbol. Every number: BACKTEST on DEV (in-sample period for the strategy, unseen by the rules),
real Alpaca option prices, MODELED 2% half-spread.
"""
import argparse
import glob
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from sprint import features, learn  # noqa: E402

RULES = {
    "F": ("otm_v1-010", "hist_v1-003", lambda d: (d.f_range_atr >= 0.52) & (d.f_rvol >= 1.05)),
    "G": ("otm_v1-040", "hist_v1-005", lambda d: d.f_range_atr >= 0.61),
    "H": ("otm_v1-040", "hist_v1-005", lambda d: d.f_rvol >= 1.06),
    "I": ("otm_v1-040", "hist_v1-005", lambda d: (d.f_range_atr >= 0.61) & (d.f_rvol >= 1.06)),
}
LEARNERS = {"L-put": ("otm_v1-010", "hist_v1-003"), "L-call": ("otm_v1-040", "hist_v1-005")}


def pf(x):
    x = np.asarray(x, float)
    loss = -x[x <= 0].sum()
    return round(float(x[x > 0].sum() / loss), 3) if loss > 0 else None


def day_skip_p(base, sel_total, n_keep, seed=23, draws=2000):
    """Share of random whole-day removals (removing at least as many trades as the rule did) whose total >= the rule's."""
    bd = base.groupby("day").pnl.agg(["size", "sum"])
    sz, sm = bd["size"].to_numpy(), bd["sum"].to_numpy()
    n_rm = len(base) - n_keep
    if n_rm <= 0:
        return None
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(draws):
        o = rng.permutation(len(bd))
        k = int(np.searchsorted(np.cumsum(sz[o]), n_rm)) + 1
        hits += (sm.sum() - sm[o[:k]].sum()) >= sel_total
    return round(hits / draws, 4)


def score(base, mask, name, run):
    sel = base[mask.fillna(False).to_numpy()]
    n, tot = len(sel), float(sel.pnl.sum()) if len(sel) else 0.0
    out = {"rule": name, "run": run, "base_trades": len(base), "base_pf": pf(base.pnl), "base_total": round(float(base.pnl.sum()), 2),
           "trades": n, "expectancy": round(tot / n, 2) if n else None, "pf": pf(sel.pnl), "pf_2x": pf(sel.pnl_2x),
           "total": round(tot, 2), "without_best5": round(tot - float(sel.pnl.nlargest(5).sum()), 2) if n else None,
           "p_day_skip": day_skip_p(base, tot, n) if n else None}
    blk = sel.assign(b=pd.to_datetime(sel.day).dt.to_period("2M").astype(str)).groupby("b").pnl.sum() if n else pd.Series(dtype=float)
    out["blocks_green"] = f"{int((blk > 0).sum())}/{len(blk)}"
    out["by_symbol"] = {s: {"n": len(g), "pf": pf(g.pnl), "total": round(float(g.pnl.sum()), 2)} for s, g in sel.groupby("symbol")}
    out["pass"] = bool(n >= 40 and (out["pf"] or 0) >= 1.25 and (out["pf_2x"] or 0) > 1.0 and out["p_day_skip"] is not None
                       and out["p_day_skip"] < 0.10)
    return out


def learner_mask(hist_rows, dev):
    X = features.matrix(hist_rows)
    prep = learn._prep_fit(X)
    Z = learn._prep_apply(prep, X)
    y = (np.array([float(r["pnl"]) for r in hist_rows]) > 0).astype(float)
    w, b = learn.fit_logit(Z, y)
    Zd = learn._prep_apply(prep, features.matrix(dev.to_dict("records")))
    prob = 1.0 / (1.0 + np.exp(-np.clip(Zd @ w + b, -30, 30)))
    return pd.Series(prob >= 0.5, index=dev.index)


def load(patterns, runs):
    files = sorted({f for p in patterns for f in glob.glob(p)})
    parts = []
    for f in files:
        d = pd.read_csv(f, low_memory=False)
        d = d[d["run_id"].isin(runs)]
        if len(d):
            parts.append(d)
    if not parts:
        return pd.DataFrame()
    d = pd.concat(parts, ignore_index=True)
    return d.drop_duplicates(subset=["run_id", "symbol", "day", "signal_idx", "entry_time"])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", nargs="+", default=["data/sprint/trades_otm_v1_*.csv.gz"])
    ap.add_argument("--hist", nargs="+", default=["data/sprint/trades_hist_v1_*.csv.gz"])
    ap.add_argument("--data", default=None, help="cache root for recomputing features on old trade files")
    ap.add_argument("--out", default="data/sprint")
    x = ap.parse_args(argv)
    dev = load(x.trades, {r[0] for r in RULES.values()})
    dev = dev[~dev["run_id"].astype(str).str.contains("@")]
    hist = load(x.hist, {r[1] for r in RULES.values()})
    if dev.empty:
        print("no DEV trades found for otm_v1-010 / otm_v1-040", file=sys.stderr)
        return 2
    if dev["f_range_atr"].isna().all() if "f_range_atr" in dev else True:
        rows = dev.to_dict("records")
        features.recompute(rows, x.data)
        dev = pd.DataFrame(rows)
    res = []
    for name, (run, hrun, fn) in RULES.items():
        base = dev[dev.run_id == run]
        res.append(score(base, fn(base), name, run))
    for name, (run, hrun) in LEARNERS.items():
        base = dev[dev.run_id == run]
        hr = hist[hist.run_id == hrun].to_dict("records")
        if not hr:
            res.append({"rule": name, "run": run, "error": f"no HIST trades for {hrun}"})
            continue
        res.append(score(base, learner_mask(hr, base), name, run))
    L = [f"# Amendment 6 holdout 2: frozen regime rules and the HIST-trained learner on DEV real option prices ({date.today()})\n",
         "BACKTEST on DEV 2024-08 to 2026-06, real Alpaca option prices, MODELED 2% half-spread, 1 contract. Pass: PF >= 1.25, "
         "PF 2x > 1.0, >= 40 trades, beats random whole-day skips p < 0.10.\n",
         "| rule | run | all trades (n / PF / total) | taken | exp $ | PF | PF 2x | total $ | w/o best 5 | 2-month blocks green | p day-skip | PASS |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res:
        if "error" in r:
            L.append(f"| {r['rule']} | {r['run']} | {r['error']} |||||||||| no |")
            continue
        L.append(f"| {r['rule']} | {r['run']} | {r['base_trades']} / {r['base_pf']} / {r['base_total']} | {r['trades']} | {r['expectancy']} | "
                 f"{r['pf']} | {r['pf_2x']} | {r['total']} | {r['without_best5']} | {r['blocks_green']} | {r['p_day_skip']} | "
                 f"{'**PASS**' if r['pass'] else 'no'} |")
    L.append("\nBy symbol: " + "; ".join(f"{r['rule']}: " + ", ".join(f"{s} n={v['n']} PF {v['pf']}" for s, v in r.get('by_symbol', {}).items())
                                      for r in res if "by_symbol" in r))
    out = Path(x.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"regime_holdout2_{date.today()}.md").write_text("\n".join(L) + "\n")
    (out / f"regime_holdout2_{date.today()}.json").write_text(json.dumps(res, indent=1, default=str))
    print("\n".join(L))
    for r in res:
        if "error" not in r:
            print(f"holdout2 {r['rule']}: {'PASS' if r['pass'] else 'no'} (n={r['trades']} PF={r['pf']} PF2x={r['pf_2x']} total={r['total']} p={r['p_day_skip']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
