"""Reproduction on OUR bars: Gao, Han, Li & Zhou (2018) "Market Intraday Momentum" - does the first half hour
(previous close -> 10:00 ET) predict the last half hour (15:30 -> 16:00 ET)?  v3.5, underlying only.

    python3 studies/first_last.py BARS.csv --out docs/studies/FIRST_LAST_SPY_QQQ.md

Trade rule as in the paper: at 15:30 take the sign of the first-half-hour return; hold to the 16:00 close. Returns in
basis points; $0.04/share round trip subtracted. Session-level bootstrap 95% CI (seed 7). Tiny sample: ~30 sessions
per symbol cannot confirm or reject a published effect; this only checks the implementation and the current sign.
"""
import argparse
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core  # noqa: E402


def sessions(m):
    m = m[(m.index.hour * 60 + m.index.minute >= 570) & (m.index.hour * 60 + m.index.minute <= 959)]
    out = {}
    for d, g in m.groupby(m.index.date):
        if len(g) >= 385:
            out[d] = g
    return out


def run(m, cost=0.04):
    ss = sessions(m)
    days = sorted(ss)
    rows = []
    for i in range(1, len(days)):
        prev, g = ss[days[i - 1]], ss[days[i]]
        pc = float(prev["Close"].iloc[-1])
        at = lambda hm: g[g.index.strftime("%H:%M") <= hm]["Close"]
        c10, c1530 = at("09:59"), at("15:29")
        if not len(c10) or not len(c1530):
            continue
        r1 = float(c10.iloc[-1]) / pc - 1
        p_in, p_out = float(c1530.iloc[-1]), float(g["Close"].iloc[-1])
        r_last = p_out / p_in - 1
        s = 1 if r1 > 0 else -1 if r1 < 0 else 0
        net = (s * (p_out - p_in) - (cost if s else 0)) / p_in
        rows.append({"day": str(days[i]), "r_first_bp": r1 * 1e4, "r_last_bp": r_last * 1e4, "trade_bp": net * 1e4})
    return rows


def ci(vals, boots=4000, seed=7):
    rng = random.Random(seed)
    ms = sorted(np.mean([rng.choice(vals) for _ in vals]) for _ in range(boots))
    return round(ms[int(.025 * boots)], 2), round(ms[int(.975 * boots)], 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default=str(ROOT / "docs" / "studies" / "FIRST_LAST_SPY_QQQ.md"))
    a = ap.parse_args()
    d = pd.read_csv(a.csv)
    d["ts"] = pd.to_datetime(d["ts"], utc=True).dt.tz_convert(core.ET)
    L = ["# First half hour -> last half hour (Gao, Han, Li, Zhou 2018) on our SPY/QQQ bars", "",
         "Rule: at 15:30 ET take the sign of (10:00 close / previous close - 1); hold to the 16:00 close. Basis points, "
         "$0.04/share round trip subtracted, session bootstrap 95% CI. Underlying only; options not modeled.", "",
         "| Symbol | Sessions | corr(first, last) | hit rate | mean trade (bp) [95% CI] | sum (bp) |", "|---|---|---|---|---|---|"]
    for t, g in d.groupby("ticker"):
        m = g.drop_duplicates("ts").set_index("ts").sort_index()
        rows = run(m)
        if len(rows) < 5:
            continue
        x = np.array([r["r_first_bp"] for r in rows])
        y = np.array([r["r_last_bp"] for r in rows])
        tr = [r["trade_bp"] for r in rows]
        lo, hi = ci(tr)
        L.append(f"| {t} | {len(rows)} ({rows[0]['day']} to {rows[-1]['day']}) | {np.corrcoef(x, y)[0, 1]:.2f} | "
                 f"{100 * np.mean([v > 0 for v in tr]):.0f}% | {np.mean(tr):.2f} [{lo}, {hi}] | {sum(tr):.1f} |")
    L += ["", "With about 30 sessions per symbol this cannot confirm or reject the published effect (the paper uses "
          "1993-2013; later re-creations report it weaker and concentrated in high-volatility days). It is recorded as "
          "a reproduction of the method on our data, not evidence of an edge. A forward paper candidate would need a "
          "preregistered hypothesis (see the Learning tab)."]
    Path(a.out).write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
