"""sprint/multiday.py - round 9 Part F: multi-day rules in shares on daily bars, and F-opt (SPRINT_PLAN Amendment 12,
pre-registered 2026-11-01 before any round-9 code, pull or run). Research only: reads cached daily bars (sprint/universe
Panel) and cached option bars; no network, no orders. Every number is a BACKTEST; U-STK numbers are SURVIVORSHIP-BIASED.

F1 rsi2 (Connors & Alvarez 2008): long only. Signal at the close of day s: close > SMA(200), close < SMA(5) and Wilder
   RSI(2) < 10 (split-adjusted closes, each symbol's own bars; universe.Panel). Buy at the symbol's next open. Exit at the
   next open after a close > SMA(5) (closes from the entry day on). No stop. One position per symbol. U-ETF: all 20 ETFs.
   U-STK: the symbol must pass the point-in-time filter on the entry day (it uses only data before that day), and at most
   10 NEW entries a day: that day's takeable signals with the lowest RSI(2) (ties: symbol).
F2 tom (Lakonishok & Smidt 1988; McConnell & Xu 2008): buy at the close of the last trading day of a month (L), sell at the
   close of the third trading day of the next month (T3); L and T3 from the NYSE calendar. U-ETF leg: SPY, QQQ, IWM, DIA
   (F2's list). U-STK leg: every U-STK name passing the filter on L. Literal-reading note: the trial count "2 rules x 2
   universes" needs tom on U-STK too, while F2 names only four ETFs for the ETF universe; no cap is stated for tom.
Windows: trades enter and exit inside HIST 2016-01-04..2024-01-31 or DEV 2024-08-01..2026-06-30 (the same window). A trade
   whose holding window [entry day, exit day] touches L1 or L2 is dropped (universe.touches_locked), and so is a trade still
   open when the data end (its exit would be in L1). A trade is booked on its EXIT day (realized P/L, the closed-trade
   convention of sprint/book.py); `entry_day` is kept on the row.
Costs and sizing: $10,000 a trade, shares = floor(10,000 / the RAW decision close: the signal close for rsi2, the entry close
   for tom). Return from split-adjusted prices, applied to the raw entry price (a split inside the window is neutral).
   Costs per side: $0.01 a share (U-ETF), 0.05% of the price (U-STK); 2x costs = double.
Pass (shares), per rule and universe: 1 at least 200 trades; 2 expectancy > 0 at 2x costs; 3 profitable in at least 6 of
   the 8 years 2016-2023 and in 2024-08..2026-06; 4 bootstrap 95% CI of the daily mean P/L above 0 (every HIST + DEV session,
   0 on days without an exit, 2,000 draws, numpy default_rng(29)); 5 positive without the best 5 days; 6 beats random entry,
   p < 0.05; 7 at least 55% of months green (months with at least one trade). A U-STK pass also needs U-ETF's same rule to
   pass. Random entry (item 6): for each trade, an entry on a random session of the same symbol with the same holding
   length in sessions and the same fills (open-to-open for rsi2, close-to-close for tom), drawn uniformly with replacement
   from the sessions where such a trade fits inside one window without touching L1/L2 (U-STK: the symbol passes the filter
   that day); same sizing and costs; 200 draws, default_rng(seed) for seeds 31-230; p = the share of draws whose total is at
   or above the rule's.
F-opt (DEV REAL): the F1 / F2 U-ETF trades in DEV carried by one call, contract rule m30-60d60-80t70 (30-60 calendar days to
   expiry, BS-EST delta 0.60-0.80 nearest 0.70, contracts.pick_daily). "Bought at the entry open, sold at the exit open",
   taken literally for both rules: the open of the share trade's entry day and of its exit day (for tom these are the opens
   of L and T3, not the share rule's closes). Price at the open = the contract's first 1-minute bar's open within
   09:30-09:34 (the pick and the entry basis); exit basis = the contract's first print of the exit session (labeled "late"
   if after 09:34; no print that session -> the trade is not counted, and counted as such). S for the pick = the raw daily
   open. Costs: half-spread 2% of premium per side ($0.005 floor) + $0.65 per contract per side; 2x = twice the half-spread.
   Pass: at least 40 trades, PF >= 1.25, PF 2x > 1.0, expectancy > 0.
"""
import math
from collections import defaultdict
from datetime import date

import numpy as np
import pandas as pd

from . import periods, shares, universe as U

NOTIONAL = 10_000.0
ETF_PER_SHARE, STK_PCT = 0.01, 0.0005
RSI_MAX, SMA_LONG, SMA_SHORT, CAP_USTK = 10.0, 200, 5, 10
TOM_EXIT_DAY = 3
BOOT_SEED, BOOT_DRAWS = 29, 2000
RANDOM_SEEDS = tuple(range(31, 231))
OPT_HS, OPT_FLOOR, FEE, MULT = 0.02, 0.005, 0.65, 100
OPEN_AGE = 5
FOPT_RULE = "m30-60d60-80t70"
LABEL = "BACKTEST on Alpaca daily bars (shares)"


def cost_side(univ, sh, px):
    return ETF_PER_SHARE * sh if univ == "U-ETF" else STK_PCT * sh * px


def make_trade(variant, univ, sym, p, e, x, s_px_raw, e_raw, ratio, kind, reason, extra=None):
    """One share trade. p: Panel; e, x: session indices of the entry and exit fills; ratio = adj exit / adj entry."""
    sh = int(math.floor(NOTIONAL / s_px_raw)) if s_px_raw and s_px_raw > 0 else 0
    if sh <= 0:
        return None
    x_ref = e_raw * ratio
    move = x_ref - e_raw
    c_in, c_out = cost_side(univ, sh, e_raw), cost_side(univ, sh, x_ref)
    pnl = sh * move - c_in - c_out
    ed, xd = p.days[e], p.days[x]
    src = "HIST" if xd <= periods.HIST[1] else "DEV"
    t = {"variant": variant, "universe": univ, "symbol": sym, "day": xd.isoformat(), "entry_day": ed.isoformat(),
         "exit_day": xd.isoformat(), "_src": src, "side": "L", "sign": 1, "entry_idx": int(e), "exit_idx": int(x), "hold": int(x - e),
         "fill": kind, "shares": sh, "entry_ref": round(e_raw, 4), "exit_ref": round(x_ref, 4), "move": round(move, 6),
         "pnl": round(pnl, 4), "pnl_2x": round(sh * move - 2 * (c_in + c_out), 4), "cost": round(c_in + c_out, 4),
         "bps": round(pnl / (sh * e_raw) * 1e4, 4), "notional": round(sh * e_raw, 2), "exit_reason": reason,
         "label": U.SB if univ == "U-STK" else ""}
    if extra:
        t.update(extra)
    return t


def ok_window(p, e, x):
    """The holding window [entry, exit] lies inside one trade window and touches no locked period."""
    ed, xd = p.days[e], p.days[x]
    if U.touches_locked(ed, xd):
        return False
    w = U.window_id(ed)
    return w is not None and w == U.window_id(xd)


def _next_open(p, j, t):
    """The symbol's first session index > t in t's segment with finite adjusted and raw opens, or None."""
    T = len(p.days)
    k = t + 1
    while k < T and p.seg[k] == p.seg[t]:
        if np.isfinite(p.adj_o[k, j]) and np.isfinite(p.raw_o[k, j]):
            return k
        k += 1
    return None


# ---------------------------------------------------------------- F1 rsi2
def rsi2(p, symbols, univ, cap=None):
    """F1 trades over the panel for `symbols` (columns of p). cap: at most `cap` new entries a day (U-STK: 10).
    Returns (trades, info)."""
    cols = [p.col[s] for s in symbols if s in p.col]
    info = {"dropped": defaultdict(int), "signals": 0}
    if not cols:
        return [], {"dropped": {}, "signals": 0}
    C, s200, s5, r2 = p.adj_c[:, cols], p.sma(SMA_LONG)[:, cols], p.sma(SMA_SHORT)[:, cols], p.rsi(2)[:, cols]
    elig = p.eligible()[:, cols] if univ == "U-STK" else None
    with np.errstate(invalid="ignore"):
        sig = np.isfinite(C) & np.isfinite(s200) & np.isfinite(s5) & np.isfinite(r2) & (C > s200) & (C < s5) & (r2 < RSI_MAX)
    info["signals"] = int(sig.sum())
    T, N = C.shape
    pos = np.full(N, -1)                     # entry session index while held
    busy = np.full(N, -1)                    # the last exit fill's session (a new entry may fill at or after it)
    meta = {}
    out, dropped = [], info["dropped"]
    for t in range(T):
        if t and p.seg[t] != p.seg[t - 1]:                         # the L2 gap: an open position's exit would be inside L2
            n_open = int((pos >= 0).sum())
            if n_open:
                dropped["still open at the L2 gap (exit would be in L2)"] += n_open
            pos[:] = -1
            busy[:] = -1
        for k in np.flatnonzero(pos >= 0):                         # exits decided on today's close
            c, m = C[t, k], s5[t, k]
            if t < pos[k] or not (np.isfinite(c) and np.isfinite(m) and c > m):
                continue
            j = cols[k]
            x = _next_open(p, j, t)
            e, s_t, s_px, rv = meta[k]
            pos[k] = -1
            busy[k] = x if x is not None else T
            if x is None:
                dropped["exit after the segment / data end (would touch a locked period)"] += 1
                continue
            if not ok_window(p, e, x):
                dropped["holding window touches L1/L2 or leaves its window"] += 1
                continue
            tr = make_trade("rsi2", univ, p.symbols[j], p, e, x, s_px, float(p.raw_o[e, j]), float(p.adj_o[x, j] / p.adj_o[e, j]),
                            "open", f"close {c:.2f} > SMA(5) {m:.2f} on {p.days[t]}: out at the next open",
                            {"signal_day": p.days[s_t].isoformat(), "rsi2": round(float(rv), 3)})
            if tr:
                out.append(tr)
        cand = np.flatnonzero(sig[t] & (pos < 0))
        if not len(cand):
            continue
        picks = []
        for k in cand:
            j = cols[k]
            e = _next_open(p, j, t)
            if e is None or not U.in_trade_window(p.days[e]) or e < busy[k]:
                continue
            if elig is not None and not elig[e, k]:
                continue
            picks.append((float(r2[t, k]), p.symbols[j], k, e))
        picks.sort()
        if cap:
            dropped[f"U-STK daily cap ({cap} lowest RSI(2))"] += max(0, len(picks) - cap)
            picks = picks[:cap]
        for rv, _s, k, e in picks:
            pos[k] = e
            meta[k] = (e, t, float(p.raw_c[t, cols[k]]), rv)
    n_open = int((pos >= 0).sum())
    if n_open:
        dropped["still open when the data end (exit would be in L1)"] += n_open
    info["dropped"] = dict(dropped)
    return out, info


# ---------------------------------------------------------------- F2 tom
def tom_dates(p):
    """[(L, T3)] session pairs from the NYSE calendar (locked days included for counting): L = the last trading day of a
    month, T3 = the third trading day of the next month."""
    cal = U.all_sessions_cal(p.days[0], p.days[-1]) if p.days else []
    by_m = defaultdict(list)
    for d in cal:
        by_m[(d.year, d.month)].append(d)
    keys = sorted(by_m)
    out = []
    for a, b in zip(keys, keys[1:]):
        if len(by_m[b]) >= TOM_EXIT_DAY:
            out.append((by_m[a][-1], by_m[b][TOM_EXIT_DAY - 1]))
    return out


def tom(p, symbols, univ):
    """F2 trades. Returns (trades, info)."""
    cols = [p.col[s] for s in symbols if s in p.col]
    elig = p.eligible() if univ == "U-STK" else None
    out, dropped = [], defaultdict(int)
    for L, T3 in tom_dates(p):
        if U.touches_locked(L, T3):
            dropped["holding window touches L1/L2"] += 1
            continue
        e, x = p.idx(L), p.idx(T3)
        if e is None or x is None or not ok_window(p, e, x):
            dropped["outside the trade windows"] += 1
            continue
        for j in cols:
            if elig is not None and not elig[e, j]:
                continue
            ce, cx = p.adj_c[e, j], p.adj_c[x, j]
            rc = p.raw_c[e, j]
            if not (np.isfinite(ce) and np.isfinite(cx) and np.isfinite(rc)):
                continue
            tr = make_trade("tom", univ, p.symbols[j], p, e, x, float(rc), float(rc), float(cx / ce), "close",
                            f"turn of the month: bought {L} close, sold {T3} close (third trading day)", {"signal_day": L.isoformat()})
            if tr:
                out.append(tr)
    return out, {"dropped": dict(dropped)}


# ---------------------------------------------------------------- random entry (item 6)
def random_entry(p, trades, univ, seeds=RANDOM_SEEDS):
    """p-value and the draw totals of item 6. Returns (p, totals, info)."""
    if not trades:
        return None, np.zeros(0), {}
    groups = defaultdict(int)
    for t in trades:
        groups[(t["symbol"], int(t["hold"]), t["fill"])] += 1
    elig = p.eligible() if univ == "U-STK" else None
    T = len(p.days)
    win = np.array([-1 if U.window_id(d) is None else U.window_id(d) for d in p.days])
    pb = p.prior_bar()
    vecs, ns, empty = [], [], 0
    for key in sorted(groups):
        sym, h, kind = key
        j = p.col.get(sym)
        if j is None or h <= 0 or h >= T:
            empty += groups[key]
            continue
        e = np.arange(0, T - h)
        x = e + h
        ok = (p.seg[e] == p.seg[x]) & (win[e] >= 0) & (win[e] == win[x])
        if kind == "open":
            prev = pb[e, j]
            size = np.where(prev >= 0, p.raw_c[np.maximum(prev, 0), j], np.nan)
            a_in, a_out, raw_in = p.adj_o[e, j], p.adj_o[x, j], p.raw_o[e, j]
        else:
            a_in, a_out, raw_in, size = p.adj_c[e, j], p.adj_c[x, j], p.raw_c[e, j], p.raw_c[e, j]
        with np.errstate(invalid="ignore"):
            ok &= np.isfinite(a_in) & np.isfinite(a_out) & np.isfinite(raw_in) & np.isfinite(size) & (size > 0)
        if elig is not None:
            ok &= elig[e, j]
        if not ok.any():
            empty += groups[key]
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            sh = np.floor(NOTIONAL / size[ok])
            ri = raw_in[ok]
            xr = ri * a_out[ok] / a_in[ok]
            c = 2 * ETF_PER_SHARE * sh if univ == "U-ETF" else STK_PCT * sh * (ri + xr)
            v = sh * (xr - ri) - c
        vecs.append(v.astype(np.float64))
        ns.append(groups[key])
    if not vecs:
        return None, np.zeros(0), {"trades_without_random_days": empty}
    lens = np.array([len(v) for v in vecs])
    offs = np.concatenate([[0], np.cumsum(lens)[:-1]])
    allv = np.concatenate(vecs)
    rep_off, rep_len = np.repeat(offs, ns), np.repeat(lens, ns)
    actual = sum(float(t["pnl"]) for t in trades)
    tots = np.empty(len(seeds))
    for k, s in enumerate(seeds):
        u = np.random.default_rng(s).random(len(rep_off))
        idx = rep_off + np.minimum((u * rep_len).astype(np.int64), rep_len - 1)
        tots[k] = allv[idx].sum()
    pv = round(float((tots >= actual - 1e-9).mean()), 4)
    return pv, tots, {"groups": len(vecs), "trades_without_random_days": empty, "median_total": round(float(np.median(tots)), 2)}


# ---------------------------------------------------------------- the pass bar
def f_pass(trades, sessions=None, rnd_p=None, min_trades=200, extra_checks=()):
    """Part F's 7 items (G1 adds random direction as an extra check)."""
    sessions = sessions or shares.all_sessions()
    tr = shares.ordered(trades)
    s = shares.stats(tr, len(sessions))
    d = shares.daily(tr, sessions)
    yrs = {str(y): sum(float(t["pnl"]) for t in tr if t["day"][:4] == str(y) and t["day"] <= shares.HIST_B) for y in range(2016, 2024)}
    up = sum(1 for v in yrs.values() if v > 0)
    dev = sum(float(t["pnl"]) for t in tr if shares.DEV_A <= t["day"] <= shares.DEV_B)
    ci = shares.bootstrap_daily(d, BOOT_SEED, BOOT_DRAWS)
    wb5 = float(d.sum() - np.sort(d)[::-1][:5].sum()) if len(d) else 0.0
    st = shares.steadiness(tr)
    checks = [(f"at least {min_trades} trades ({s['trades']})", s["trades"] >= min_trades),
              (f"expectancy > 0 at 2x costs ({s.get('expectancy_2x')})", (s.get("expectancy_2x") or -1) > 0),
              (f"profitable in at least 6 of the 8 years 2016-2023 ({up} of 8) and in 2024-08..2026-06 ({dev:.2f})", up >= 6 and dev > 0),
              (f"bootstrap 95% CI of the daily mean P/L above 0 ({ci})", ci is not None and ci[0] > 0),
              (f"positive without the best 5 days ({wb5:.2f})", wb5 > 0),
              (f"beats random entry, p < 0.05 (p = {rnd_p})", rnd_p is not None and rnd_p < 0.05),
              (f"at least 55% of months green ({st['months_green']}/{st['months']})", bool(st["months"]) and st["months_green"] / st["months"] >= 0.55)]
    checks += list(extra_checks)
    return {"stats": s, "years_2016_2023": {k: round(v, 2) for k, v in yrs.items()}, "dev_total": round(dev, 2), "boot_ci": ci,
            "without_best5_days": round(wb5, 2), "random_p": rnd_p, "steadiness": st, "checks": checks, "pass": all(ok for _, ok in checks)}


# ---------------------------------------------------------------- F-opt
def opt_hs(px, pct=OPT_HS, floor=OPT_FLOOR):
    return max(pct * float(px), floor)


def minute_frame(df):
    """Adds m = minutes after 09:30 (from the cache's ET ISO timestamps) to an option bar frame."""
    if df is None or not len(df):
        return pd.DataFrame(columns=["symbol", "m", "o", "h", "l", "c", "v"])
    s = df["ts"].astype(str)
    m = s.str.slice(11, 13).astype(int) * 60 + s.str.slice(14, 16).astype(int) - 570
    return df.assign(m=m.to_numpy())


def first_print(g, max_minute=None):
    """(minute index, open) of the first regular-hours bar of one contract's frame (columns m, o), within max_minute."""
    if g is None or not len(g):
        return None, None
    g = g[(g["m"] >= 0) & (g["m"] < 390)].sort_values("m")
    if max_minute is not None:
        g = g[g["m"] <= max_minute]
    if not len(g):
        return None, None
    return int(g["m"].iloc[0]), float(g["o"].iloc[0])


def candidates(entry_df):
    """[(symbol, expiry, strike, right, first open within 09:30-09:34)] from an entry-day candidate frame (contracts that
    did not print in that window are left out: they have no price to pick on)."""
    from .data import parse_occ
    f = minute_frame(entry_df)
    if not len(f):
        return []
    f = f[(f["m"] >= 0) & (f["m"] <= OPEN_AGE - 1)].sort_values(["symbol", "m"], kind="stable").drop_duplicates("symbol")
    out = []
    for sym, px in zip(f["symbol"], f["o"].astype(float)):
        meta = parse_occ(sym)
        if meta:
            out.append((sym, meta["expiry"], meta["strike"], meta["right"], float(px)))
    return out


def fopt_trade(tr, entry_df, exit_df, S_open, rule=FOPT_RULE, pct=OPT_HS):
    """One F-opt trade (1 call) for share trade `tr`, or (None, reason). entry_df: the entry day's candidate bars;
    exit_df: the exit day's bars of the chosen contract (the pull fetches it after the same pick)."""
    from . import contracts
    ed = date.fromisoformat(tr["entry_day"])
    if U.touches_locked(ed, date.fromisoformat(tr["exit_day"])):
        return None, "holding window touches L1/L2"
    info, why = contracts.pick_daily(candidates(entry_df), S_open, ed, rule, "C")
    if info is None:
        return None, why
    f = minute_frame(exit_df)
    g = f[f["symbol"] == info["symbol"]] if len(f) else f
    m_x, px_x = first_print(g)
    if px_x is None:
        return None, "no print of the chosen contract on the exit day"
    b_in, b_out = info["px"], px_x
    h_in, h_out = opt_hs(b_in, pct), opt_hs(b_out, pct)
    buy, sell = b_in + h_in, max(0.0, b_out - h_out)
    buy2, sell2 = b_in + 2 * h_in, max(0.0, b_out - 2 * h_out)
    pnl = MULT * (sell - buy) - 2 * FEE
    pnl2 = MULT * (sell2 - buy2) - 2 * FEE
    row = {"variant": f"fopt_{tr['variant']}", "symbol": tr["symbol"], "day": tr["exit_day"], "entry_day": tr["entry_day"],
           "exit_day": tr["exit_day"], "_src": "DEV", "side": "C", "contract": info["symbol"], "strike": info["strike"],
           "expiry": info["expiry"], "dte": info["dte"], "delta_est": info["delta"], "iv_est": round(info["iv"], 4),
           "entry_basis": round(b_in, 4), "exit_basis": round(b_out, 4), "exit_minute": m_x, "exit_late": m_x is not None and m_x > OPEN_AGE - 1,
           "debit": round(MULT * buy + FEE, 2), "pnl": round(pnl, 2), "pnl_2x": round(pnl2, 2), "entry_idx": 0, "exit_idx": 0,
           "entry_time": "09:30", "exit_time": "09:30", "share_pnl": tr["pnl"], "label": "REAL (Alpaca option prices)"}
    return row, None


def fopt_bar(rows):
    """F-opt's pass on DEV REAL: >= 40 trades, PF >= 1.25, PF 2x > 1.0, expectancy > 0."""
    from .round8 import ostats, _pfr
    s = ostats([r for r in rows if shares.DEV_A <= r["day"] <= shares.DEV_B])
    ch = [(f"at least 40 trades ({s['trades']})", s["trades"] >= 40), (f"PF >= 1.25 ({s.get('pf')})", _pfr(s.get("pf")) >= 1.25),
          (f"PF 2x > 1.0 ({s.get('pf_2x')})", _pfr(s.get("pf_2x")) > 1.0),
          (f"expectancy > 0 ({s.get('expectancy')})", (s.get("expectancy") or 0) > 0)]
    return {"dev": s, "checks": ch, "pass": all(ok for _, ok in ch)}


def fopt_targets(trades):
    """The U-ETF F1/F2 trades whose option twin is priced (DEV only, entry and exit inside DEV)."""
    return [t for t in trades if t["universe"] == "U-ETF" and shares.DEV_A <= t["entry_day"] and t["exit_day"] <= shares.DEV_B]
