"""underlying_first.py - v3.5 (new): the underlying decides; the option is chosen and protected second.

Decision order (Nick's): a credible directional opportunity in the STOCK -> its entry, expected move, invalidation and
holding window -> only then a contract -> managed by both the stock setup and the contract's real risk.

What this module provides (no strategy rules change here; the frozen main policy is untouched):
  premium_trigger()  the exact 20% planned-loss trigger. For a long option with entry fill F per share, multiplier M,
                     per-contract fees fe (entry) and fx (exit) in dollars, and exit slippage s per share, the planned
                     net loss if the position is sold at a bid trigger B is  L(B) = M*(F - (B - s)) + fe + fx.
                     The budget is 20% of the premium paid, cap*M*F. L(B) <= budget  <=>  B >= F*(1-cap) + s + (fe+fx)/M.
                     That minimum B is rounded UP to a valid tick (a higher trigger = a smaller loss), and the entry is
                     rejected when the trigger would sit at or above the current bid (it would fire at once).
                     Planned, not guaranteed: gaps, latency and manual execution can make the real loss larger.
  zero_dte()         whether the chain the desk actually received has an expiration dated today (never assumed:
                     SPY/QQQ list Monday-Friday expirations; most single stocks only weeklies/Fridays).
  reach_odds()       how often the STOCK reaches the level the trade needs before its stop and before the cutoff, from
                     the stock's own recent sessions (an idea credited to day-trader-skill's Time Machine, MIT), with two
                     changes: moves are scaled to TODAY's volatility so far, and drawn in blocks of consecutive minutes
                     so short trends survive. Also the median minutes to the target: time is what decays an option.
                     Information only until its calibration is proven (hypothesis H-REACH-1).
"""
import math

import numpy as np
import pandas as pd

VERSION = "2026-10-31.uf1"
ALL_PENNY = {"SPY", "QQQ", "IWM"}          # quoted in $0.01 at every price
CAVEAT = ("planned, not guaranteed: a gap, a halt, latency or a manual order can fill below the trigger, so the real loss "
          "can be larger than planned")


def tick_for(symbol_root, px, penny=True):
    """Minimum option price increment. Penny-interval classes: $0.01 under $3, $0.05 at/above (SPY/QQQ/IWM: $0.01 always).
    Non-penny classes: $0.05 under $3, $0.10 at/above. `penny` comes from configuration per symbol; verify per class."""
    if symbol_root in ALL_PENNY:
        return 0.01
    if penny:
        return 0.01 if px < 3 else 0.05
    return 0.05 if px < 3 else 0.10


def round_up(x, tick):
    return round(math.ceil(round(x / tick, 9)) * tick, 2)


def premium_trigger(fill, qty=1, bid=None, symbol_root="SPY", cap=0.20, fee_in=0.02, fee_out=0.02, slip=0.01, mult=100, penny=True):
    """The minimum protective bid trigger B for a planned loss of at most `cap` of the premium paid (see module notes).
    Returns the trigger, dollars at risk for the actual quantity, and whether the entry is feasible."""
    raw = fill * (1 - cap) + slip + (fee_in + fee_out) / mult
    tick = tick_for(symbol_root, raw, penny)
    trig = round_up(raw, tick)
    loss = lambda b: mult * (fill - (b - slip)) + fee_in + fee_out
    out = {"fill": fill, "qty": qty, "trigger_bid": trig, "tick": tick, "raw_min_bid": round(raw, 4),
           "planned_loss_per_contract": round(loss(trig), 2), "planned_loss_total": round(loss(trig) * qty, 2),
           "budget_per_contract": round(cap * mult * fill, 2), "budget_total": round(cap * mult * fill * qty, 2),
           "premium_total": round(mult * fill * qty, 2), "formula": "L(B) = M*(F-(B-s)) + fe + fx", "caveat": CAVEAT, "version": VERSION}
    if trig >= fill:
        out.update(feasible=False, why=f"the 20% trigger {trig:.2f} is not below the fill {fill:.2f} (premium too small for the costs)")
    elif bid is not None and trig >= bid:
        out.update(feasible=False, why=f"the 20% trigger {trig:.2f} is at or above the bid {bid:.2f}: it would fire at once")
    else:
        out.update(feasible=True, why=None)
    return out


def zero_dte(chain_rows, day):
    """(True/False/None, why) from the chain actually received. None = unknown (no chain), never assumed."""
    if not chain_rows:
        return None, "no chain received: 0DTE availability unknown"
    exps = sorted({str(r.get("exp")) for r in chain_rows if r.get("exp")})
    d = str(day)
    return (d in exps), (f"expirations received: {', '.join(exps[:6])}" + (" ..." if len(exps) > 6 else ""))


# ---------------------------------------------------------------- reach odds (session bootstrap)
def _ratio_pool(sessions):
    """sessions: list of RTH 1m frames (09:30-15:59). -> array [n_sessions, 390, 4] of O/H/L/C over the previous close."""
    pools = []
    for m in sessions:
        m = m[(m.index.strftime("%H:%M") >= "09:30") & (m.index.strftime("%H:%M") <= "15:59")]
        if len(m) != 390:
            continue
        c = m["Close"].values.astype(float)
        prev = np.r_[float(m["Open"].iloc[0]), c[:-1]]
        pools.append(np.stack([m["Open"].values / prev, m["High"].values / prev, m["Low"].values / prev, c / prev], axis=1))
    return np.array(pools) if pools else None


def reach_odds(prior_sessions, today_m1, entry, stop, target, side, now, flat="15:25", n=2000, block=5, seed=19, min_sessions=15):
    """P(target first), P(stop first), P(neither by `flat`), median minutes to the target, from `n` simulated rest-of-day
    paths. Conservative: a minute touching both counts as the stop. Returns None + why when the inputs can't support it."""
    pool = _ratio_pool(prior_sessions)
    if pool is None or len(pool) < min_sessions:
        return None, f"needs {min_sessions} complete prior sessions (have {0 if pool is None else len(pool)})"
    up = side == "C"
    if (up and not (stop < entry < target)) or (not up and not (target < entry < stop)):
        return None, "entry, stop and target are not in order"
    now = pd.Timestamp(now)
    m0 = (now.hour * 60 + now.minute) - (9 * 60 + 30)
    mf = int(flat[:2]) * 60 + int(flat[3:5]) - (9 * 60 + 30)
    if m0 >= mf or m0 < 0:
        return None, "outside the session window"
    # volatility scaling: today's mean |1m log return| so far vs the pool's over the same minutes
    t = today_m1[(today_m1.index >= now.normalize() + pd.Timedelta(hours=9, minutes=30)) & (today_m1.index < now)]
    scale, why_scale = 1.0, "no scaling (fewer than 10 minutes today)"
    if len(t) >= 10:
        tr = np.abs(np.diff(np.log(t["Close"].values.astype(float))))
        pr = np.abs(np.log(pool[:, 1:max(2, len(tr) + 1), 3])).mean()
        if pr > 0:
            scale = float(np.clip(tr.mean() / pr, 0.5, 2.5))
            why_scale = f"x{scale:.2f} (today's 1m moves vs the same minutes in the pool, clamped 0.5-2.5)"
    rng = np.random.default_rng(seed)
    steps = mf - m0
    nb = math.ceil(steps / block)
    picks = rng.integers(0, len(pool), size=(n, nb))
    lr = np.log(pool)                                            # [S, 390, 4]
    paths = np.empty((n, nb * block, 4))
    for b in range(nb):
        mins = np.arange(m0 + b * block, min(m0 + (b + 1) * block, 390))
        if not len(mins):
            break
        paths[:, b * block:b * block + len(mins), :] = lr[picks[:, b]][:, mins, :]
    paths = paths[:, :steps, :] * scale
    closes = entry * np.exp(np.cumsum(paths[:, :, 3], axis=1))
    prev = np.concatenate([np.full((n, 1), entry), closes[:, :-1]], axis=1)
    hi, lo = prev * np.exp(paths[:, :, 1]), prev * np.exp(paths[:, :, 2])
    hit_s = (lo <= stop) if up else (hi >= stop)
    hit_t = (hi >= target) if up else (lo <= target)
    big = steps + 1
    fs = np.where(hit_s.any(axis=1), hit_s.argmax(axis=1), big)
    ft = np.where(hit_t.any(axis=1), hit_t.argmax(axis=1), big)
    tgt_first = ft < fs                                          # same minute -> stop (conservative)
    stop_first = (fs <= ft) & (fs < big)
    neither = ~tgt_first & ~stop_first
    med = float(np.median(ft[tgt_first] + 1)) if tgt_first.any() else None
    return {"p_target": round(float(tgt_first.mean()), 3), "p_stop": round(float(stop_first.mean()), 3), "p_neither": round(float(neither.mean()), 3),
            "median_min_to_target": med, "minutes_left": steps, "paths": n, "block_min": block, "seed": seed, "sessions": len(pool),
            "scaling": why_scale, "version": VERSION,
            "note": "simulated from this stock's own recent sessions; not a prediction. Calibration pending (H-REACH-1)."}, None


# ---------------------------------------------------------------- worked examples (model numbers, clearly labeled)
def bs_call_put(S, K, T_years, iv, r=0.04, side="C"):
    if T_years <= 0:
        return max(0.0, (S - K) if side == "C" else (K - S))
    d1 = (math.log(S / K) + (r + iv * iv / 2) * T_years) / (iv * math.sqrt(T_years))
    d2 = d1 - iv * math.sqrt(T_years)
    N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    if side == "C":
        return S * N(d1) - K * math.exp(-r * T_years) * N(d2)
    return K * math.exp(-r * T_years) * N(-d2) - S * N(-d1)


def examples():
    """MODEL examples (Black-Scholes mids with a stated spread), not market data: why a right-way stock move can still
    lose money on the option. Entry at the ask, exit at the bid, $0.02 fees per side per contract."""
    yr = 365 * 24 * 60
    out = []

    def trade(name, S0, S1, K, minutes_to_exp, hold_min, iv0, iv1, half_spread, side="C"):
        a0 = bs_call_put(S0, K, minutes_to_exp / yr, iv0, side=side) + half_spread
        b1 = max(0.0, bs_call_put(S1, K, (minutes_to_exp - hold_min) / yr, iv1, side=side) - half_spread)
        pnl = round((b1 - a0) * 100 - 0.04, 2)
        out.append({"example": name, "stock": f"{S0} -> {S1} ({'+' if S1 >= S0 else ''}{S1 - S0:.2f}) in {hold_min} min",
                    "contract": f"{K}{side}, {minutes_to_exp // 60} h {minutes_to_exp % 60} min to expiry", "iv": f"{iv0:.0%} -> {iv1:.0%}",
                    "entry_ask": round(a0, 2), "exit_bid": round(b1, 2), "pnl_per_contract": pnl})
    trade("A. right direction, fast move, 0DTE near the money: profit", 600.0, 601.5, 600, 300, 15, 0.14, 0.14, 0.02)
    trade("B. right direction but slow: 0DTE time decay wins (loss)", 600.0, 600.4, 601, 300, 150, 0.14, 0.14, 0.02)
    trade("C. right direction, IV falls after news (IV crush): loss", 600.0, 600.8, 600, 2 * 24 * 60, 30, 0.30, 0.20, 0.03)
    trade("D. right direction, wide spread on a cheap far-OTM 0DTE: loss", 600.0, 600.6, 603, 120, 20, 0.14, 0.14, 0.05)
    trade("E. same move as B with a 7-day contract: decay matters less", 600.0, 600.4, 601, 7 * 24 * 60, 150, 0.16, 0.16, 0.03)
    trade("F. puts: right-way DOWN move, fast, 0DTE: profit", 600.0, 598.6, 600, 300, 15, 0.14, 0.15, 0.02, side="P")
    return out
