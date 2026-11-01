"""sprint/catalyst.py - round 9 Part G: news and catalysts on all stocks (U-STK) (SPRINT_PLAN Amendment 12, pre-registered
2026-11-01 before any round-9 code, pull or run). Research only: reads cached EDGAR records, daily bars, 1-minute stock
bars and option bars; no network, no orders. Every number is a BACKTEST; U-STK is SURVIVORSHIP-BIASED.

Events (sprint/edgar.py): form 8-K, EDGAR acceptance time (US Eastern), CIK -> tickers by SEC's company_tickers.json.
G1 news_go (Jiang, Li & Wang 2021, JFE): an 8-K accepted between 16:00 of the prior session and 09:15 on day t, for a U-STK
   name that passes the point-in-time filter on t (one event per symbol and day). 1-minute bars (split-adjusted, regular
   hours) of day t; prior close and the 20-session average daily volume from split-adjusted daily bars of the sessions
   before t. Signal at the bar finishing 09:45 (index 14) when all three hold:
     |gap| = |open (the 09:30 bar's open) / prior close - 1| >= 2%;
     the 09:30-09:45 move (close of index 14 - the open) is in the gap's direction (a zero move is not);
     RV15 = volume of indices 0-14 / (0.10 x the 20-session average daily volume) >= 3.
   Trade in the gap's direction at the next 1-minute open (index 15, or the first bar with an open within 3 minutes).
   Stop: the opposite end of the 09:30-09:45 range (indices 0-14: the low for a long, the high for a short), judged on
   finished 1-minute closes from the entry bar on, exiting at the next bar's open. Out at the 15:55 close (the close of
   index 384; 12:55 = index 204 on 1 PM early-close days, the literal analogue). Shares = floor(10,000 / the close of index
   14); costs 0.05% of the price per side (2x = 0.10%). Long-only reported too (gap-up trades only).
   Pass: Part F's 7 items (sprint/multiday.f_pass, at least 200 trades) plus beating random direction on the same events,
   p < 0.05 (the same entries and exits with a coin-flip side, seeds 31-230; costs unchanged). Item 6 (random entry) for an
   intraday rule with 1-minute bars pulled for event days only: for each trade, an entry at index 15 on a random pulled
   event day of the same symbol (with replacement), same side, same holding length in minutes (capped at the out bar), same
   sizing rule and costs; 200 draws, seeds 31-230. Literal-reading note: random days are limited to the symbol's event days
   because only those days' 1-minute bars exist (Amendment 12 pulls event days only).
G2 pre_earn_straddle (Gao, Xing & Zhang 2018, JFQA): Item 2.02 8-Ks (edgar.g2_timing: exit at the close of t-1 for a
   filing accepted before 09:30, else at the close of t; entry at the close of t-3). The name must pass the U-STK filter on
   the entry day (the decision is at that close; it uses data through the session before). DEV window only: entry and exit
   inside 2024-08-01..2026-06-30, never touching L1/L2. One event per symbol and t.
   Contract: the ATM call and put at the strike nearest the entry close (raw daily close) among strikes whose call AND put
   both printed in 15:30-15:59 of the entry day, of the first listed expiry 10-60 calendar days out. Expiries probed
   (straddle_candidates): the first Friday at least 10 days out (Thursday when that Friday is an NYSE holiday) and the first
   monthly (third Friday) at least 10 days out; the earlier one with any print is "the first listed expiry". Literal note:
   single-stock options listed Friday expiries in DEV; a Monday/Wednesday expiry, if any stock had one, is not probed.
   Prices: the close of the last 1-minute bar in 15:30-15:59 of the entry / exit day (no print in that half hour -> no fill:
   the window is not counted, and counted as such). OCC roots drop a class dot (BRK.B -> BRKB).
   Costs: half-spread 5% of premium per leg per side ($0.01 floor) + $0.65 per contract per side (4 contracts a round trip).
   Return per straddle = P/L / debit (debit = both legs' buy prices x 100 + entry fees). The pass is judged on returns per
   straddle (equal weight per event; PF = sum of positive returns / |sum of negative returns|); dollar P/L per 1 straddle is
   shown as information. Half-years by exit day: Aug-Dec 2024, H1 2025, H2 2025, H1 2026 ("positive" = mean return > 0).
   Benchmark: the same stocks' straddles on random non-earnings dates with the same 2- or 3-session hold. The pull prices a
   fixed pool of POOL_PER_EVENT = 3 random entry dates per event (random_pool: drawn once with default_rng(POOL_SEED = 31),
   without replacement, from the symbol's DEV sessions whose window fits in DEV and contains no 2.02 event day of that
   symbol from the entry through the session after the exit); each of the 200 draws (default_rng(seed), seeds 31-230)
   takes one priced pool date per event and averages the returns. Pass needs the actual mean above the 95th percentile of
   the 200 draw means. Literal-reading note: a fixed pool keeps the pull finite (fresh random dates for 200 draws x every
   event would need about 200 times the option requests).
   Pass: at least 100 events, mean return > 0 after costs, PF >= 1.25, positive in at least 3 of the 4 half-years, mean above
   the benchmark's 95th percentile. LOOK-AHEAD CAVEAT (edgar.LOOKAHEAD) on every G2 line.
"""
import math
from collections import defaultdict
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from . import edgar, periods, shares, universe as U
from .data import parse_occ

NOTIONAL = 10_000.0
COST_PCT = 0.0005
GAP_MIN, RV_MIN, RV_FRAC = 0.02, 3.0, 0.10
SIG_BAR, ENTRY_BAR, ENTRY_WAIT = 14, 15, 3
OUT_BAR, EARLY_OUT_BAR = 384, 204
RANDOM_SEEDS = tuple(range(31, 231))
G2_HS, G2_FLOOR, FEE, MULT = 0.05, 0.01, 0.65, 100
G2_LAST = (360, 389)
G2_DTE = (10, 60)
POOL_PER_EVENT, POOL_SEED = 3, 31
HALF_YEARS = (("Aug-Dec 2024", "2024-08-01", "2024-12-31"), ("H1 2025", "2025-01-01", "2025-06-30"),
              ("H2 2025", "2025-07-01", "2025-12-31"), ("H1 2026", "2026-01-01", "2026-06-30"))
DEV_A, DEV_B = periods.DEV[0], periods.DEV[1]


# ---------------------------------------------------------------- events
def _acc(r):
    a = r.get("accepted")
    if not a:
        return None
    return a if isinstance(a, datetime) else datetime.fromisoformat(str(a))


def g1_events(records, tmap, panel, cal):
    """[{"symbol", "t", "acc", "accepted"}] sorted by (t, symbol): one per symbol and day, the earliest acceptance."""
    elig = panel.eligible()
    best = {}
    for r in records:
        if r.get("form") != "8-K":
            continue
        a = _acc(r)
        t = edgar.g1_day(a, cal)
        if t is None or not U.in_trade_window(t) or periods.overlaps(t, t):
            continue
        k = panel.idx(t)
        if k is None:
            continue
        for sym in tmap.get(int(r["cik"]), []):
            j = panel.col.get(sym)
            if j is None or not elig[k, j]:
                continue
            key = (sym, t)
            if key not in best or a < best[key]["accepted"]:
                best[key] = {"symbol": sym, "t": t, "acc": r["acc"], "accepted": a}
    return sorted(best.values(), key=lambda e: (e["t"], e["symbol"]))


def g2_events(records, tmap, panel, cal):
    """[{"symbol", "t", "entry", "exit", "hold", "intraday", "acc", "accepted"}] for Item 2.02, DEV only."""
    elig = panel.eligible()
    best = {}
    for r in records:
        if r.get("form") != "8-K" or "2.02" not in (r.get("items") or []):
            continue
        a = _acc(r)
        tm = edgar.g2_timing(a, cal)
        if tm is None:
            continue
        if not (DEV_A <= tm["entry"] and tm["exit"] <= DEV_B) or U.touches_locked(tm["entry"], tm["exit"]):
            continue
        k = panel.idx(tm["entry"])
        if k is None:
            continue
        for sym in tmap.get(int(r["cik"]), []):
            j = panel.col.get(sym)
            if j is None or not elig[k, j]:
                continue
            key = (sym, tm["t"])
            if key not in best or a < best[key]["accepted"]:
                best[key] = dict(tm, symbol=sym, acc=r["acc"], accepted=a)
    return sorted(best.values(), key=lambda e: (e["entry"], e["symbol"]))


def earnings_days(records, tmap):
    """{symbol: set of acceptance dates of Item 2.02 8-Ks} (every year, for the non-earnings test)."""
    out = defaultdict(set)
    for r in records:
        if r.get("form") == "8-K" and "2.02" in (r.get("items") or []):
            a = _acc(r)
            if a is None:
                continue
            for sym in tmap.get(int(r["cik"]), []):
                out[sym].add(a.date())
    return out


def random_pool(events, panel, earn, per_event=POOL_PER_EVENT, seed=POOL_SEED):
    """[{"event": index, "symbol", "entry", "exit", "hold"}] - the fixed pool of random non-earnings straddle dates."""
    rng = np.random.default_rng(seed)
    dev = [k for k, d in enumerate(panel.days) if DEV_A <= d <= DEV_B]
    out = []
    for n, ev in enumerate(events):
        h, sym = int(ev["hold"]), ev["symbol"]
        ed = earn.get(sym, set())
        cands = []
        for k in dev:
            x = k + h
            if x + 1 >= len(panel.days) or panel.days[x] > DEV_B or panel.seg[x] != panel.seg[k]:
                continue
            a, b = panel.days[k], panel.days[x + 1]
            if any(a <= d <= b for d in ed):
                continue
            cands.append(k)
        if not cands:
            continue
        pick = rng.choice(len(cands), size=min(per_event, len(cands)), replace=False)
        for i in sorted(int(x) for x in pick):
            k = cands[i]
            out.append({"event": n, "symbol": sym, "entry": panel.days[k], "exit": panel.days[k + h], "hold": h})
    return out


# ---------------------------------------------------------------- G1 on 1-minute bars
def day_grid(df_sym):
    """(5, 390) array o, h, l, c, v by regular-hours minute index from one symbol's bars of one day (NaN where none)."""
    g = np.full((5, 390), np.nan)
    if df_sym is None or not len(df_sym):
        return g
    s = df_sym["ts"].astype(str)
    m = (s.str.slice(11, 13).astype(int) * 60 + s.str.slice(14, 16).astype(int) - 570).to_numpy()
    ok = (m >= 0) & (m < 390)
    for k, c in enumerate(("o", "h", "l", "c", "v")):
        g[k, m[ok]] = df_sym[c].to_numpy(float)[ok]
    return g


def _fill(g, i, last, wait=ENTRY_WAIT):
    for k in range(i, min(i + wait, last) + 1):
        if np.isfinite(g[0, k]):
            return k
    return None


def g1_signal(g, prior_close, adv):
    """(side +1/-1, info) or (None, reason) at the bar finishing 09:45."""
    o0, c14 = g[0, 0], g[3, SIG_BAR]
    if not (np.isfinite(o0) and np.isfinite(c14)) or not (prior_close and prior_close > 0):
        return None, "no 09:30 open, no 09:44 close or no prior close"
    gap = o0 / prior_close - 1
    if abs(gap) < GAP_MIN:
        return None, f"|gap| {abs(gap):.4f} < 2%"
    mv = c14 - o0
    if mv == 0 or (mv > 0) != (gap > 0):
        return None, "09:30-09:45 move not in the gap's direction"
    if not (adv and adv > 0 and np.isfinite(adv)):
        return None, "no 20-session average volume"
    rv = float(np.nansum(g[4, :SIG_BAR + 1])) / (RV_FRAC * adv)
    if rv < RV_MIN:
        return None, f"RV15 {rv:.2f} < 3"
    return (1 if gap > 0 else -1), {"gap": round(float(gap), 6), "move15": round(float(mv), 4), "rv15": round(rv, 3)}


def g1_trade(ev, g, prior_close, adv, early=False, variant="news_go", long_only=False):
    side, info = g1_signal(g, prior_close, adv)
    if side is None:
        return None, info
    if long_only and side < 0:
        return None, "short (long-only variant)"
    xb = EARLY_OUT_BAR if early else OUT_BAR
    k = _fill(g, ENTRY_BAR, xb - 1)
    if k is None:
        return None, "no entry bar within 3 minutes"
    stop = float(np.nanmin(g[2, :SIG_BAR + 1])) if side > 0 else float(np.nanmax(g[1, :SIG_BAR + 1]))
    e_px = float(g[0, k])
    x_i, x_px, why = None, None, None
    for i in range(k, xb):
        c = g[3, i]
        if np.isfinite(c) and ((c < stop) if side > 0 else (c > stop)):
            j = next((q for q in range(i + 1, xb + 1) if np.isfinite(g[0, q])), None)
            if j is not None:
                x_i, x_px, why = j, float(g[0, j]), f"STOP {stop:.2f}: 1m close {float(c):.2f}"
            break
    if x_i is None:
        j = next((q for q in range(xb, k - 1, -1) if np.isfinite(g[3, q])), None)
        x_i, x_px, why = (j, float(g[3, j]), f"OUT at the {'12:55' if early else '15:55'} close") if j is not None else (k, e_px, "no later bar")
    sh = int(math.floor(NOTIONAL / float(g[3, SIG_BAR])))
    if sh <= 0:
        return None, "price too high for $10,000"
    mv = x_px - e_px
    cost = COST_PCT * sh * (e_px + x_px)
    pnl = sh * side * mv - cost
    t = {"variant": variant, "symbol": ev["symbol"], "day": ev["t"].isoformat(), "_src": "HIST" if ev["t"] <= periods.HIST[1] else "DEV",
         "side": "L" if side > 0 else "S", "sign": side, "decision_idx": SIG_BAR, "entry_idx": k, "exit_idx": x_i,
         "entry_time": _hm(k), "exit_time": _hm(x_i), "shares": sh, "entry_ref": round(e_px, 4), "exit_ref": round(x_px, 4),
         "move": round(mv, 6), "pnl": round(pnl, 4), "pnl_2x": round(pnl - cost, 4), "cost": round(cost, 4),
         "bps": round(pnl / (sh * e_px) * 1e4, 4), "notional": round(sh * e_px, 2), "exit_reason": why, "stop": round(stop, 4),
         "acc": ev.get("acc"), "accepted": str(ev.get("accepted")), "label": U.SB, **info}
    return t, None


def _hm(i):
    m = 570 + int(i)
    return f"{m // 60:02d}:{m % 60:02d}"


def random_direction(trades, seeds=RANDOM_SEEDS):
    """Same entries and exits, coin-flip side, the trade's own costs. (p, totals)."""
    tr = shares.ordered(trades)
    if not tr:
        return None, np.zeros(0)
    sh = np.array([float(t["shares"]) for t in tr])
    mv = np.array([float(t["move"]) for t in tr])
    cost = np.array([float(t["cost"]) for t in tr])
    actual = float(sum(float(t["pnl"]) for t in tr))
    tots = np.array([float((sh * np.random.default_rng(s).choice(np.array([-1.0, 1.0]), len(tr)) * mv - cost).sum()) for s in seeds])
    return round(float((tots >= actual - 1e-9).mean()), 4), tots


def random_entry_g1(trades, grids, seeds=RANDOM_SEEDS):
    """Item 6 for G1. grids: {symbol: [(day, grid, early)]} of every pulled event day. (p, totals)."""
    if not trades:
        return None, np.zeros(0)
    by = defaultdict(list)
    for t in trades:
        by[(t["symbol"], t["sign"], int(t["exit_idx"]) - int(t["entry_idx"]))].append(t)
    keys = sorted(by)
    vecs, ns = [], []
    for key in keys:
        sym, side, h = key
        v = []
        for _d, g, early in grids.get(sym, []):
            xb = EARLY_OUT_BAR if early else OUT_BAR
            k = _fill(g, ENTRY_BAR, xb - 1)
            c14 = g[3, SIG_BAR]
            if k is None or not np.isfinite(c14) or c14 <= 0:
                continue
            j = k + h
            if j >= xb:
                q = next((q for q in range(xb, k - 1, -1) if np.isfinite(g[3, q])), None)
                xp = float(g[3, q]) if q is not None else None
            else:
                q = next((q for q in range(j, xb + 1) if np.isfinite(g[0, q])), None)
                xp = float(g[0, q]) if q is not None else None
            if xp is None:
                continue
            sh = math.floor(NOTIONAL / float(c14))
            ep = float(g[0, k])
            v.append(sh * side * (xp - ep) - COST_PCT * sh * (ep + xp))
        if v:
            vecs.append(np.array(v))
            ns.append(len(by[key]))
    if not vecs:
        return None, np.zeros(0)
    lens = np.array([len(v) for v in vecs])
    offs = np.concatenate([[0], np.cumsum(lens)[:-1]])
    allv = np.concatenate(vecs)
    ro, rl = np.repeat(offs, ns), np.repeat(lens, ns)
    actual = sum(float(t["pnl"]) for t in trades)          # each trade's own day is in its symbol's pool
    tots = np.empty(len(seeds))
    for n, s in enumerate(seeds):
        u = np.random.default_rng(s).random(len(ro))
        tots[n] = allv[ro + np.minimum((u * rl).astype(np.int64), rl - 1)].sum()
    return round(float((tots >= actual - 1e-9).mean()), 4), tots


# ---------------------------------------------------------------- G2 straddles
def occ_root(sym):
    return str(sym).replace(".", "").upper()


def occ(sym, exp, right, k):
    return f"{occ_root(sym)}{exp:%y%m%d}{right}{int(round(k * 1000)):08d}"


def _fri_expiry(d, hol):
    """The Friday expiry date for the week of Friday d (Thursday when that Friday is a holiday)."""
    return d - timedelta(days=1) if d.isoformat() in hol else d


def g2_expiries(entry):
    """The probed expiries, earliest first: the first Friday >= entry + 10 days and the first third Friday >= entry + 10
    (each moved to Thursday on an NYSE-holiday Friday), within 60 days."""
    hol = periods.holidays()
    lo = entry + timedelta(days=G2_DTE[0])
    out = []
    d = lo + timedelta(days=(4 - lo.weekday()) % 7)
    e1 = _fri_expiry(d, hol)
    if e1 < lo:
        d += timedelta(days=7)
        e1 = _fri_expiry(d, hol)
    out.append(e1)
    m = date(lo.year, lo.month, 1)
    for _ in range(4):
        third = m + timedelta(days=(4 - m.weekday()) % 7 + 14)
        e = _fri_expiry(third, hol)
        if e >= lo:
            out.append(e)
            break
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return sorted({e for e in out if G2_DTE[0] <= (e - entry).days <= G2_DTE[1]})


def g2_strikes(close):
    out = set()
    grids = [g for g, ok in ((0.5, close < 75), (1.0, close < 300), (2.5, True), (5.0, True), (10.0, close >= 150)) if ok]
    for g in grids:
        k0 = math.floor(close / g) * g
        for k in (k0 - g, k0, k0 + g, k0 + 2 * g):
            if k > 0:
                out.add(round(k, 2))
    return sorted(out)


def straddle_candidates(sym, entry, close):
    return [occ(sym, e, r, k) for e in g2_expiries(entry) for k in g2_strikes(close) for r in ("C", "P")]


def last_close(df_sym, lo=G2_LAST[0], hi=G2_LAST[1]):
    """(minute, close) of the last bar with minute in [lo, hi], or (None, None)."""
    if df_sym is None or not len(df_sym):
        return None, None
    s = df_sym["ts"].astype(str)
    m = (s.str.slice(11, 13).astype(int) * 60 + s.str.slice(14, 16).astype(int) - 570).to_numpy()
    ok = (m >= lo) & (m <= hi)
    if not ok.any():
        return None, None
    i = np.where(ok)[0][np.argmax(m[ok])]
    return int(m[i]), float(df_sym["c"].to_numpy(float)[i])


def choose_straddle(entry_df, sym, entry, close):
    """{"call", "put", "strike", "expiry", "call_px", "put_px"} or (None, reason) from the entry day's candidate bars."""
    if entry_df is None or not len(entry_df) or not (close and close > 0):
        return None, "no candidate bars on the entry day"
    root = occ_root(sym)
    px = {}
    for s, g in entry_df.groupby("symbol"):
        if not str(s).startswith(root):
            continue
        meta = parse_occ(s)
        if not meta or meta["root"] != root:
            continue
        _m, c = last_close(g)
        if c is not None and c > 0:
            px[(meta["expiry"], meta["strike"], meta["right"])] = (s, c)
    for e in g2_expiries(entry):
        ks = sorted({k for (ee, k, r) in px if ee == e})
        if not ks:
            continue
        both = [k for k in ks if (e, k, "C") in px and (e, k, "P") in px]
        if not both:
            return None, f"first listed expiry {e}: no strike with both legs printed in 15:30-15:59"
        k = min(both, key=lambda x: (abs(x - close), x))
        return {"call": px[(e, k, "C")][0], "put": px[(e, k, "P")][0], "strike": k, "expiry": e.isoformat(),
                "call_px": px[(e, k, "C")][1], "put_px": px[(e, k, "P")][1], "dte": (e - entry).days}, None
    return None, "no listed expiry 10-60 days out with a print in 15:30-15:59"


def g2_hs(px, pct=G2_HS):
    return max(pct * float(px), G2_FLOOR)


def straddle_trade(ev, choice, exit_df, variant="pre_earn_straddle", pct=G2_HS):
    """One straddle (1 call + 1 put) P/L and return, or (None, reason)."""
    xs = {}
    for leg in ("call", "put"):
        g = exit_df[exit_df["symbol"] == choice[leg]] if exit_df is not None and len(exit_df) else None
        _m, c = last_close(g)
        if c is None:
            return None, "no exit print in 15:30-15:59"
        xs[leg] = c
    buy = {leg: choice[f"{leg}_px"] + g2_hs(choice[f"{leg}_px"], pct) for leg in ("call", "put")}
    sell = {leg: max(0.0, xs[leg] - g2_hs(xs[leg], pct)) for leg in ("call", "put")}
    buy2 = {leg: choice[f"{leg}_px"] + 2 * g2_hs(choice[f"{leg}_px"], pct) for leg in ("call", "put")}
    sell2 = {leg: max(0.0, xs[leg] - 2 * g2_hs(xs[leg], pct)) for leg in ("call", "put")}
    debit = MULT * (buy["call"] + buy["put"]) + 2 * FEE
    pnl = MULT * (sell["call"] + sell["put"] - buy["call"] - buy["put"]) - 4 * FEE
    pnl2 = MULT * (sell2["call"] + sell2["put"] - buy2["call"] - buy2["put"]) - 4 * FEE
    debit2 = MULT * (buy2["call"] + buy2["put"]) + 2 * FEE
    ex = ev["exit"] if isinstance(ev["exit"], date) else date.fromisoformat(str(ev["exit"]))
    en = ev["entry"] if isinstance(ev["entry"], date) else date.fromisoformat(str(ev["entry"]))
    return {"variant": variant, "symbol": ev["symbol"], "day": ex.isoformat(), "entry_day": en.isoformat(), "exit_day": ex.isoformat(),
            "t": str(ev.get("t", "")), "hold": int(ev["hold"]), "intraday": bool(ev.get("intraday", False)), "_src": "DEV",
            "side": "C", "entry_idx": 389, "exit_idx": 389, "call": choice["call"], "put": choice["put"], "strike": choice["strike"],
            "expiry": choice["expiry"], "dte": choice.get("dte"), "call_in": choice["call_px"], "put_in": choice["put_px"],
            "call_out": xs["call"], "put_out": xs["put"], "debit": round(debit, 2), "pnl": round(pnl, 2), "pnl_2x": round(pnl2, 2),
            "ret": round(pnl / debit, 6), "ret_2x": round(pnl2 / debit2, 6), "label": f"REAL (Alpaca option prices); {U.SB}"}, None


def pf_ret(r):
    r = np.asarray(r, float)
    lo, w = -r[r < 0].sum(), r[r > 0].sum()
    return round(float(w / lo), 3) if lo > 0 else (math.inf if w > 0 else None)


def g2_benchmark(trades, pool_rets, seeds=RANDOM_SEEDS):
    """pool_rets: {event index: [returns of its priced pool dates]}. Each draw takes one per event that has any.
    Returns (95th percentile, means, events used)."""
    keys = sorted(k for k, v in pool_rets.items() if v)
    if not keys:
        return None, np.zeros(0), 0
    vecs = [np.asarray(pool_rets[k], float) for k in keys]
    means = []
    for s in seeds:
        rng = np.random.default_rng(s)
        means.append(float(np.mean([v[int(rng.integers(0, len(v)))] for v in vecs])))
    means = np.array(means)
    return round(float(np.percentile(means, 95)), 6), means, len(keys)


def g2_pass(trades, p95):
    r = np.array([float(t["ret"]) for t in trades])
    n = len(r)
    mean = float(r.mean()) if n else None
    pf = pf_ret(r) if n else None
    hy = {}
    for name, a, b in HALF_YEARS:
        sub = [float(t["ret"]) for t in trades if a <= t["day"] <= b]
        hy[name] = {"events": len(sub), "mean_ret": round(float(np.mean(sub)), 6) if sub else None}
    green = sum(1 for v in hy.values() if v["mean_ret"] is not None and v["mean_ret"] > 0)
    pfr = -1.0 if pf is None else pf
    checks = [(f"at least 100 events ({n})", n >= 100), (f"mean return per straddle > 0 after costs ({_p(mean)})", mean is not None and mean > 0),
              (f"PF >= 1.25 (on returns: {pf})", pfr >= 1.25), (f"positive in at least 3 of the 4 half-years ({green} of 4)", green >= 3),
              (f"mean above the random-date benchmark's 95th percentile ({_p(mean)} vs {_p(p95)})", mean is not None and p95 is not None and mean > p95)]
    pnl = np.array([float(t["pnl"]) for t in trades])
    return {"events": n, "mean_ret": None if mean is None else round(mean, 6), "pf_ret": pf, "half_years": hy, "p95_random": p95,
            "mean_ret_2x": round(float(np.mean([float(t["ret_2x"]) for t in trades])), 6) if n else None,
            "dollars": {"total": round(float(pnl.sum()), 2) if n else 0.0, "expectancy": round(float(pnl.mean()), 2) if n else None,
                        "avg_debit": round(float(np.mean([float(t["debit"]) for t in trades])), 2) if n else None},
            "intraday_events": sum(1 for t in trades if t.get("intraday")), "checks": checks, "pass": all(ok for _, ok in checks)}


def _p(x):
    return "-" if x is None else f"{100 * x:.2f}%"
