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
Round 8 (SPRINT_PLAN Addendum 10.1, pre-registered 2026-11-01 before any round-8 run): "n1d03-12t07" (B4: FIN-H's far
out-of-the-money band on the next expiry) and "n1d55-75t65" (A-opt: the noise ledger's band on the next expiry), the same
way as n1d40-55t45: the next listed expiry after the session, BS-EST time including the calendar days to that expiry.
Round 9 (SPRINT_PLAN Amendment 12): "w5-10d03-12t07" (Part I, weekly expiry) and "m30-60d60-80t70" (F-opt, 30-60 day
calls at delta 0.60-0.80 nearest 0.70, picked by pick_daily); see the notes under RULES. Amendment 13 (Part S, the 1-minute
scalper, 0DTE): "d45-55t50" (|delta| 0.45-0.55 nearest 0.50, the alert bots' near-the-money shape) and "d20-30t25" (0.20-0.30
nearest 0.25, a cheaper contract that fits a $3,000 account), picked from the day's 0DTE contracts like d40-55t45.
Round 10 (SPRINT_PLAN Addendum 15.5, R1 and R2): "d55-70t60" (|delta| 0.55-0.70 nearest 0.60, "one strike in the money"),
picked from the day's 0DTE contracts like d40-55t45 (the existing +/-3% strike band of the DEV pull holds it on ordinary
days; sprint/r10grid.needed_option_contracts lists what a big-move day could add).
Far out-of-the-money rules (otm_v1, pre-registered 2026-10-31): "d03-12t07" (|delta| 0.03-0.12, target 0.07) and
"d06-15t10" (0.06-0.15, target 0.10): the deltas of Option Alpha's top-listed SPX/XSP lottery puts and calls (0.06-0.10).
SPY/QQQ/IWM have $1 strikes, about 0.5 (SPY/QQQ) to 1 (IWM) standard deviations of the rest-of-day move apart at
10:30, so a 0.05-0.10 band would often hold no strike; the bands are wide enough to usually hold one, and the picker
still takes the strike nearest the target.
"""
import math

import numpy as np

from . import bs

RULES = {"d40-55t45": (0.40, 0.55, 0.45), "d50-65t575": (0.50, 0.65, 0.575), "d55-75t65": (0.55, 0.75, 0.65),
         "d45-60t50": (0.45, 0.60, 0.50), "n1d40-55t45": (0.40, 0.55, 0.45), "n1d50-65t575": (0.50, 0.65, 0.575),
         "d03-12t07": (0.03, 0.12, 0.07), "d06-15t10": (0.06, 0.15, 0.10),
         "n1d03-12t07": (0.03, 0.12, 0.07), "n1d55-75t65": (0.55, 0.75, 0.65),           # round 8 (Addendum 10.1)
         "w5-10d03-12t07": (0.03, 0.12, 0.07),                                            # round 9 Part I (Amendment 12)
         "m30-60d60-80t70": (0.60, 0.80, 0.70),                                           # round 9 F-opt (Amendment 12)
         "d45-55t50": (0.45, 0.55, 0.50), "d20-30t25": (0.20, 0.30, 0.25),                 # round 9 Part S (Amendment 13)
         "d55-70t60": (0.55, 0.70, 0.60)}                  # round 10 (Addendum 15.5, R1 / R2): one strike in the money, 0DTE
NEXT = {"n1d40-55t45", "n1d50-65t575", "n1d03-12t07", "n1d55-75t65"}
# Round 9 (SPRINT_PLAN Amendment 12, pre-registered 2026-11-01 before any round-9 code, pull or run):
#   "w5-10d03-12t07" (Part I): the nearest listed expiry 5-10 calendar days after the session, BS-EST |delta| 0.03-0.12
#     nearest 0.07 (FIN-H's band). Its tapes come from data/alpaca/options_w5/ (tools/sprint_pull9.py) and are set on
#     ctx.tapes_weekly by sprint/weekly.py; BS-EST time includes the calendar days to that expiry, as the n1 rules do. The
#     engine never loads that folder, so an engine run on this rule finds no contracts and skips (it is not an "n1" rule).
#   "m30-60d60-80t70" (F-opt): calls 30-60 calendar days to expiry, BS-EST delta 0.60-0.80 nearest 0.70, picked at a
#     session's open from daily-bar trades (pick_daily below); not an intraday rule, so pick() refuses it.
WEEKLY = {"w5-10d03-12t07"}
DAILY = {"m30-60d60-80t70"}
DAILY_DTE = {"m30-60d60-80t70": (30, 60)}
WEEKLY_DTE = {"w5-10d03-12t07": (5, 10)}


def is_next(rule):
    return rule in NEXT
MAX_AGE = 5


def pick(ctx, side, i, rule="d40-55t45"):
    """(tape, info) or (None, reason)."""
    lo, hi, tgt = RULES[rule]
    if rule in DAILY:
        return None, f"{rule} is a daily-bar rule (contracts.pick_daily), not an intraday pick"
    S = ctx.c[i]
    if math.isnan(S):
        return None, "no underlying close at the signal bar"
    wk = rule in WEEKLY
    nxt = rule in NEXT or wk
    pool = (getattr(ctx, "tapes_weekly", None) or {}) if wk else (ctx.tapes_next if nxt else ctx.tapes)
    cands = [t for t in pool.values() if t.right == side]
    if not cands:
        return None, f"no {'weekly (5-10 day)' if wk else 'next-expiry' if nxt else '0DTE'} contracts on file for this side"
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


def pick_daily(cands, S, day, rule="m30-60d60-80t70", right="C"):
    """F-opt's pick at a session's open (round 9, Amendment 12). cands: [(occ symbol, expiry date, strike, right, price)]
    with price = the contract's first print of the session (its first 1-minute bar's open at most MAX_AGE minutes after
    09:30; the caller decides). S = the underlying's open that session (raw, unadjusted: strikes are raw). Keeps the
    `right` side with calendar days to expiry inside the rule's DTE range and BS-EST |delta| inside its band, picks the
    one nearest the target; ties -> the lower premium, then the earlier expiry, then the symbol. BS time = calendar minutes
    from 09:30 on `day` to 16:00 on the expiry. Returns (info dict, None) or (None, reason)."""
    lo, hi, tgt = RULES[rule]
    d0, d1 = DAILY_DTE[rule]
    if S is None or not (S > 0):
        return None, "no underlying open"
    keep = [c for c in cands if c[3] == right and d0 <= (c[1] - day).days <= d1 and c[4] is not None and c[4] > 0]
    if not keep:
        return None, f"no {right} contract {d0}-{d1} days out with a print at the open"
    best = None
    by_exp = {}
    for c in keep:
        by_exp.setdefault(c[1], []).append(c)
    for exp, grp in by_exp.items():                       # one vectorized solve per expiry (BS time is per expiry)
        T = bs.t_years(390 + 1440 * (exp - day).days)
        iv, d = bs.iv_delta_v(np.array([c[4] for c in grp], float), float(S), np.array([float(c[2]) for c in grp]), T,
                              np.array([c[3] == "C" for c in grp]))
        for (sym, _e, K, rt, px), v, dd in zip(grp, iv, d):
            if math.isnan(dd):
                continue
            ad = abs(float(dd))
            if not lo <= ad <= hi:
                continue
            key = (abs(ad - tgt), float(px), exp, sym)
            if best is None or key < best[0]:
                best = (key, {"symbol": sym, "strike": float(K), "right": rt, "px": float(px), "iv": float(v),
                              "delta": round(float(dd), 3), "delta_label": "BS-EST", "rule": rule, "expiry": exp.isoformat(),
                              "dte": (exp - day).days})
    if best is None:
        return None, f"no contract with BS-EST |delta| in {lo:.2f}-{hi:.2f}"
    return best[1], None
