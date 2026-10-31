"""sprint/book.py - several strategies traded together as one book (pre-registered 2026-10-31, sprint run 3). Research only.

Input: the trades of 2+ runs (data/sprint/trades_*.csv.gz rows), each run = one strategy sleeve trading 1 contract per
signal (P/L scales with size later; the edge does not). Every session in the period counts, including sessions on
which nothing traded (P/L 0), so daily numbers are not flattered.

Reported, per sleeve and for the combined book:
  trades, trades per session, % of sessions with a trade, expectancy, PF, total, total at 2x slippage, max drawdown on
  the daily equity curve, worst day, daily Sharpe (mean / std x sqrt(252)), and the 95% day-block bootstrap interval
  of the mean daily P/L (blocks of 5 sessions, 2,000 draws, seed 11).
  The correlation of daily P/L between sleeves: sleeves that lose on the same days add risk, not diversification.
  Overlap: trades in the same symbol and side whose holding times overlap in two sleeves (the book would be doubling up).
Optional desk-wide daily stop (`daily_stop`, $): within each session, trades are taken in entry-time order across all
sleeves, and once the realized P/L of trades CLOSED before an entry is at or below -daily_stop, later entries that
session are skipped. Only closed trades count (an open loss is not known at the time).
"""
import math

import numpy as np


def _hm(s):
    h, m = str(s).split(":")[:2]
    return int(h) * 60 + int(m)


def sessions_between(a, b):
    from datetime import date, timedelta
    from .periods import holidays
    hol = holidays()
    a, b = date.fromisoformat(str(a)), date.fromisoformat(str(b))
    out, d = [], a
    while d <= b:
        if d.weekday() < 5 and d.isoformat() not in hol:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def apply_daily_stop(rows, limit):
    """rows: trades of all sleeves (dicts with day, entry_time, exit_time, pnl). Returns (kept, skipped count)."""
    kept, skipped = [], 0
    by_day = {}
    for r in rows:
        by_day.setdefault(str(r["day"]), []).append(r)
    for d in sorted(by_day):
        taken = []
        for r in sorted(by_day[d], key=lambda x: (_hm(x["entry_time"]), str(x.get("run_id")), str(x.get("symbol")))):
            closed = sum(float(x["pnl"]) for x in taken if _hm(x["exit_time"]) <= _hm(r["entry_time"]))
            if closed <= -limit:
                skipped += 1
                continue
            taken.append(r)
        kept += taken
    return kept, skipped


def _daily(rows, days, key="pnl"):
    idx = {d: i for i, d in enumerate(days)}
    v = np.zeros(len(days))
    for r in rows:
        i = idx.get(str(r["day"]))
        if i is not None:
            v[i] += float(r[key])
    return v


def _boot(daily, block=5, n=2000, seed=11):
    if len(daily) < block * 2:
        return None
    rng = np.random.default_rng(seed)
    nb = int(math.ceil(len(daily) / block))
    starts = np.arange(0, len(daily) - block + 1)
    means = []
    for _ in range(n):
        s = rng.choice(starts, nb)
        means.append(np.concatenate([daily[x:x + block] for x in s])[:len(daily)].mean())
    lo, hi = np.percentile(means, [2.5, 97.5])
    return round(float(lo), 2), round(float(hi), 2)


def sleeve_stats(rows, days):
    pnl = np.array([float(r["pnl"]) for r in rows])
    p2 = np.array([float(r.get("pnl_2x", r["pnl"])) for r in rows])
    d = _daily(rows, days)
    eq = np.cumsum(d)
    dd = float((eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min()) if len(eq) else 0.0
    w, l = pnl[pnl > 0], pnl[pnl <= 0]
    traded = len({str(r["day"]) for r in rows})
    return {"trades": len(pnl), "per_session": round(len(pnl) / len(days), 2) if days else None,
            "pct_sessions": round(traded / len(days), 3) if days else None,
            "expectancy": round(float(pnl.mean()), 2) if len(pnl) else None,
            "pf": round(float(w.sum() / -l.sum()), 3) if l.sum() < 0 else None,
            "total": round(float(pnl.sum()), 2), "total_2x": round(float(p2.sum()), 2),
            "pf_2x": round(float(p2[p2 > 0].sum() / -p2[p2 <= 0].sum()), 3) if p2[p2 <= 0].sum() < 0 else None,
            "max_dd": round(min(dd, 0.0), 2), "worst_day": round(float(d.min()), 2) if len(d) else None,
            "sharpe": round(float(d.mean() / d.std() * math.sqrt(252)), 2) if len(d) and d.std() > 0 else None,
            "daily_ci95": _boot(d)}


def overlaps(by_run):
    n = 0
    runs = sorted(by_run)
    for i, a in enumerate(runs):
        for b in runs[i + 1:]:
            idx = {}
            for r in by_run[b]:
                idx.setdefault((str(r["day"]), r["symbol"], r["side"]), []).append(r)
            for r in by_run[a]:
                for x in idx.get((str(r["day"]), r["symbol"], r["side"]), []):
                    if _hm(r["entry_time"]) < _hm(x["exit_time"]) and _hm(x["entry_time"]) < _hm(r["exit_time"]):
                        n += 1
    return n


def combine(by_run, a, b, daily_stop=None):
    """by_run: {run_id: [trade dicts]}; a, b: the period's first and last session (ISO)."""
    days = sessions_between(a, b)
    out = {"sessions": len(days), "sleeves": {k: sleeve_stats(v, days) for k, v in by_run.items()}}
    allr = [dict(r, run_id=k) for k, v in by_run.items() for r in v]
    if daily_stop:
        allr, sk = apply_daily_stop(allr, daily_stop)
        out["daily_stop"] = {"limit": daily_stop, "skipped": sk}
    out["book"] = sleeve_stats(allr, days)
    keys = sorted(by_run)
    M = np.array([_daily(by_run[k], days) for k in keys])
    with np.errstate(invalid="ignore", divide="ignore"):
        C = np.corrcoef(M) if len(keys) > 1 else np.ones((1, 1))
    out["corr"] = {k: {k2: (None if math.isnan(C[i, j]) else round(float(C[i, j]), 2)) for j, k2 in enumerate(keys)} for i, k in enumerate(keys)}
    out["overlaps"] = overlaps(by_run)
    return out


def report_md(res, labels=None):
    labels = labels or {}
    L = [f"### Combined book ({res['sessions']} sessions, 1 contract per signal, BACKTEST, MODELED-SPREAD)\n",
         "| sleeve | trades | per session | % sessions | exp $ | PF | PF 2x | total $ | total 2x $ | max DD | worst day | Sharpe | daily CI95 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, s in list(res["sleeves"].items()) + [("BOOK" + (f" (daily stop ${res['daily_stop']['limit']:g})" if res.get("daily_stop") else ""), res["book"])]:
        L.append(f"| {labels.get(k, k)} | {s['trades']} | {s['per_session']} | {s['pct_sessions']} | {s['expectancy']} | {s['pf']} | {s['pf_2x']} | "
                 f"{s['total']} | {s['total_2x']} | {s['max_dd']} | {s['worst_day']} | {s['sharpe']} | {s['daily_ci95']} |")
    if res.get("daily_stop"):
        L.append(f"\nDaily stop skipped {res['daily_stop']['skipped']} entries.")
    keys = list(res["corr"])
    if len(keys) > 1:
        L.append("\nCorrelation of daily P/L (near 0 or negative = the sleeves diversify each other):\n")
        L.append("| | " + " | ".join(keys) + " |")
        L.append("|---" * (len(keys) + 1) + "|")
        for k in keys:
            L.append(f"| {k} | " + " | ".join("" if res["corr"][k][k2] is None else f"{res['corr'][k][k2]:+.2f}" for k2 in keys) + " |")
    L.append(f"\nSame symbol and side held at the same time in two sleeves: {res['overlaps']} trade pairs.\n")
    return "\n".join(L) + "\n"
