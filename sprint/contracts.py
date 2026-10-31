"""sprint/contracts.py - the 0DTE contract picker (docs/research/SPRINT_PLAN.md, "Contracts").

At the decision time (end of the signal bar i):
  * candidates: that day's 0DTE contracts on the signal's side (calls for "C", puts for "P");
  * price = the contract's last traded price at or before bar i, at most 5 minutes old (a proxy for the mid);
  * delta = BS-EST: Black-Scholes delta with the implied vol solved from that price, the underlying's close at bar i
    and the minutes left to 16:00 (sprint/bs.py). Alpaca bars carry no greeks, so every delta here is an estimate;
  * keep |delta| inside the rule's band, pick the one nearest the target; ties -> the lower premium;
  * spread cap ~10% of price, only when the spread is MEASURED from logged chains (a modeled spread is not a quote).
Rules: "d40-55t45" (base: 0.40-0.55, target 0.45), "d50-65t575" (variant: 0.50-0.65, target the midpoint 0.575),
"d55-75t65" (the noise ledger's own band, for the noise entries), "d45-60t50" (Option Alpha T1's 0.50 delta, as the
base band shifted up by 0.05: 0.45-0.60, target 0.50; OA itself takes the closest delta with no band).
Next-expiry rules (setups_v2, pre-registered 2026-10-31): "n1d40-55t45" and "n1d50-65t575" pick, with the same bands,
from the NEXT listed expiry after the session (1 DTE for SPY/QQQ on most days; Friday -> Monday is 3 calendar days),
bought and sold the same session like every sprint trade. BS-EST time to expiry = minutes to 16:00 today + 1440 x the
calendar days to the expiry.
"""
import math

import numpy as np

from . import bs

RULES = {"d40-55t45": (0.40, 0.55, 0.45), "d50-65t575": (0.50, 0.65, 0.575), "d55-75t65": (0.55, 0.75, 0.65),
         "d45-60t50": (0.45, 0.60, 0.50), "n1d40-55t45": (0.40, 0.55, 0.45), "n1d50-65t575": (0.50, 0.65, 0.575)}
NEXT = {"n1d40-55t45", "n1d50-65t575"}


def is_next(rule):
    return rule in NEXT
MAX_AGE = 5


def pick(ctx, side, i, rule="d40-55t45"):
    """(tape, info) or (None, reason)."""
    lo, hi, tgt = RULES[rule]
    S = ctx.c[i]
    if math.isnan(S):
        return None, "no underlying close at the signal bar"
    nxt = rule in NEXT
    pool = ctx.tapes_next if nxt else ctx.tapes
    cands = [t for t in pool.values() if t.right == side]
    if not cands:
        return None, f"no {'next-expiry' if nxt else '0DTE'} contracts on file for this side"
    px = np.array([t.last_close(i, MAX_AGE) or np.nan for t in cands], float)
    K = np.array([t.strike for t in cands], float)
    ok = ~np.isnan(px)
    if not ok.any():
        return None, "no contract traded in the 5 minutes before the signal"
    extra = 0
    if nxt:
        exp = getattr(cands[0], "expiry", None)
        if exp is None:
            return None, "next-expiry contract without an expiry date"
        extra = 1440 * (exp - ctx.day).days
    T = bs.t_years(390 - (i + 1) + extra)
    iv, d = bs.iv_delta_v(np.where(ok, px, 1.0), float(S), K, T, np.array([side == "C"] * len(cands)))
    best = None
    for j, t in enumerate(cands):
        if not ok[j] or math.isnan(d[j]):
            continue
        ad = abs(float(d[j]))
        if not lo <= ad <= hi:
            continue
        if ctx.spread is not None and not ctx.spread.spread_ok(ctx.sym, float(px[j]), i + 1):
            continue
        key = (abs(ad - tgt), float(px[j]))
        if best is None or key < best[0]:
            best = (key, t, {"symbol": t.symbol, "strike": t.strike, "right": t.right, "px": float(px[j]), "iv": float(iv[j]),
                             "delta": round(float(d[j]), 3), "delta_label": "BS-EST", "rule": rule,
                             "expiry": str(getattr(t, "expiry", ctx.day))})
    if best is None:
        return None, f"no contract with BS-EST |delta| in {lo:.2f}-{hi:.2f}"
    return best[1], best[2]
