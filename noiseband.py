"""noiseband.py - research variant 'noise': the intraday "noise area" momentum rules from Zarattini, Aziz & Barbon,
"Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)" (2024), traded with options on paper.

Rules as published (shares, 2007-2024):
  sigma(HH:MM) = average over the last 14 sessions of |close(HH:MM) / open(09:30) - 1|
  upper = max(today's open, yesterday's close) x (1 + sigma);  lower = min(open, prev close) x (1 - sigma)
  checks only at HH:00 and HH:30 from 10:00. Above upper -> long, below lower -> short.
  stop: long = max(upper, VWAP), short = min(lower, VWAP), checked at the same half-hour marks; flat at the close.
What changes here (and why it must be measured, not assumed):
  * options instead of shares (delta ~0.65 contracts: closer to the stock, less time decay per dollar of move);
  * the desk's hard rules still apply every tick: the 20% planned premium-loss ceiling and all out at 15:25
    (the paper holds to 16:00), entries only until 15:15 (last check 15:00);
  * results are kept in their own ledger with the underlying move and the option result side by side.
The paper's edge was measured on SPY shares with sub-cent costs. An option version pays spread and time decay, so it
can lose even if the stock signal works. That is exactly what this ledger is for.
"""
from datetime import timedelta

import numpy as np
import pandas as pd

import core
import indicators as I
import marketdata
import paper
import store

VERSION = "2026-10-30.v3.1-noise"


def cfg():
    return (core.policy().get("research_variants") or {}).get("noise") or {}


def _rth_days(m1):
    r = m1.between_time("09:30", "15:59")
    return r, sorted(set(r.index.date))


def sigma_profile(m1, day, lookback=14, min_sessions=10):
    """Average absolute move from the 09:30 open, by minutes since the open, over the prior `lookback` sessions.
    Returns (Series indexed 1..390 = minutes after 09:30 at the bar's END, n_sessions) or (None, n)."""
    r, days = _rth_days(m1)
    prior = [d for d in days if d < day][-lookback:]
    rows = []
    for d in prior:
        g = r[r.index.date == d]
        if len(g) < 300:
            continue                                  # half days / broken sessions don't define "normal"
        o = float(g["Open"].iloc[0])
        mins = ((g.index.hour * 60 + g.index.minute) - 570 + 1).astype(int)    # bar opened 09:30 ends at minute 1
        rows.append(pd.Series(np.abs(g["Close"].values / o - 1), index=mins))
    if len(rows) < min_sessions:
        return None, len(rows)
    return pd.concat(rows, axis=1).mean(axis=1), len(rows)


def bands(m1, day, t_end, vm=1.0, lookback=14, min_sessions=10):
    """Noise-area bands at the time a bar ENDS (t_end, e.g. 10:00). None if history or today's open is missing."""
    prof, n = sigma_profile(m1, day, lookback, min_sessions)
    if prof is None:
        return None
    r, days = _rth_days(m1)
    today = r[r.index.date == day]
    prev_days = [d for d in days if d < day]
    if not len(today) or not prev_days:
        return None
    prev = r[r.index.date == prev_days[-1]]
    o, pc = float(today["Open"].iloc[0]), float(prev["Close"].iloc[-1])
    m = int((t_end.hour * 60 + t_end.minute) - 570)
    if m not in prof.index:
        return None
    sig = float(prof.loc[m]) * vm
    return {"upper": round(max(o, pc) * (1 + sig), 4), "lower": round(min(o, pc) * (1 - sig), 4), "sigma": round(sig, 6),
            "open": o, "prev_close": pc, "sessions": n}


def check_times(day):
    c = cfg()
    first, last = c.get("first_check", "10:00"), c.get("last_check", "15:00")
    t = pd.Timestamp(f"{day} {first}", tz=core.ET)
    end = pd.Timestamp(f"{day} {last}", tz=core.ET)
    out = []
    while t <= end:
        out.append(t)
        t += timedelta(minutes=30)
    return out


def state_at(m1, day, t_end):
    """Signal and stop levels at a check time, from finished bars only. -> dict or None."""
    c = cfg()
    bar_open = t_end - timedelta(minutes=1)
    if bar_open not in m1.index:
        return None
    px = float(m1.loc[bar_open, "Close"])
    b = bands(m1, day, t_end, c.get("vm", 1.0), c.get("lookback", 14), c.get("min_sessions", 10))
    if not b:
        return None
    r = m1.between_time("09:30", "15:59")
    today = r[(r.index.date == day) & (r.index <= bar_open)]
    vw = I.last(I.session_vwap(today)) if len(today) else None
    sig = "C" if px > b["upper"] else "P" if px < b["lower"] else None
    return dict(b, price=px, vwap=vw, signal=sig, t=t_end.isoformat(),
                stop_long=max(b["upper"], vw) if vw is not None else b["upper"],
                stop_short=min(b["lower"], vw) if vw is not None else b["lower"])


def pick_contract(rows, side):
    c, cp = cfg(), core.policy()["contract"]
    best = None
    for r in rows or []:
        d, bid, ask = r.get("delta"), r.get("bid") or 0, r.get("ask") or 0
        if d is None or bid <= 0 or ask <= 0:
            continue
        if not (c.get("delta_min", 0.55) <= abs(d) <= c.get("delta_max", 0.75)):
            continue
        if (ask - bid) / ask > cp["max_spread_pct"]:
            continue
        k = abs(abs(d) - c.get("delta_target", 0.65))
        if best is None or k < best[0]:
            best = (k, r)
    return best[1] if best else None


# ---------------------------------------------------------------- live (called from engine.tick)
def tick(ticker, snap, chain_rows_fn):
    """At each half-hour check: manage the open noise position (stop / reversal), then enter on a fresh signal."""
    c = cfg()
    if not c.get("enabled") or ticker not in c.get("tickers", ["SPY", "QQQ"]):
        return None
    now = core.now_et()
    sess = core.session_info(now)
    t_end = pd.Timestamp(now).floor("30min")
    if now - t_end.to_pydatetime() > timedelta(minutes=5) or t_end.strftime("%H:%M") < c.get("first_check", "10:00"):
        return None
    key = f"noise:{ticker}:{t_end.isoformat()}"
    if store.kv_get(key):
        return None
    m1 = snap.get("m1")
    if m1 is None or not len(m1):
        return None
    st = state_at(m1, now.date(), t_end)
    if st is None:
        if (t_end - timedelta(minutes=1)) not in m1.index:
            return None                               # the check bar hasn't finished yet: try again next tick
        store.kv_set(key, {"skipped": "no noise band (needs 10+ full prior sessions)"})
        return None
    store.kv_set(key, st)
    opens = [p for p in store.positions(ledger="noise", status="OPEN") if p["ticker"] == ticker]
    for p in opens:
        up = p["side"] == "C"
        stop = st["stop_long"] if up else st["stop_short"]
        p["plan"]["stop_px"] = round(stop, 2)
        store.pos_save(p)
        if (st["price"] < stop) if up else (st["price"] > stop):
            paper.sell(p, p["qty_open"], f"NOISE STOP at {t_end.strftime('%H:%M')} check: {st['price']:.2f} "
                                         f"{'below' if up else 'above'} max(band, VWAP) {stop:.2f}")
        elif st["signal"] and st["signal"] != p["side"]:
            paper.sell(p, p["qty_open"], f"NOISE REVERSAL at {t_end.strftime('%H:%M')}: price left the other side of the band")
    if not st["signal"] or not sess["entries_allowed"] or t_end.strftime("%H:%M") > c.get("last_check", "15:00") \
            or not store.kv_get("paper_enabled", True):
        return st
    if [p for p in store.positions(ledger="noise", status="OPEN") if p["ticker"] == ticker]:
        return st
    side = st["signal"]
    rows, err = chain_rows_fn(ticker, side)
    k = pick_contract(rows, side)
    if not k:
        store.event("research", f"NOISE {ticker} {'calls' if side == 'C' else 'puts'} signal at {t_end.strftime('%H:%M')} "
                    f"({st['price']:.2f} vs band {st['upper']:.2f}/{st['lower']:.2f}): no contract fits delta "
                    f"{c.get('delta_min')}-{c.get('delta_max')} and the spread rule{(' (' + err + ')') if err else ''}", "noise")
        return st
    slip, fee = paper.costs(k["ask"] - k["bid"])
    idea = f"{now.strftime('%Y-%m-%d')}-{ticker}-{side}-NOISE-{t_end.strftime('%H%M')}"
    ok, why = paper.reserve_idea("noise", idea, ticker, side)
    if not ok:
        return st
    plan = {"symbol": k["symbol"], "label": f"{int(k['symbol'][-8:]) / 1000:g}{side}", "family": "NOISE_BAND",
            "premium_stop": core.cents_up(k["ask"] * (1 - core.policy()["risk"]["stop_cap_pct"]) + slip + 2 * fee / 100),
            "stop_px": round(st["stop_long"] if side == "C" else st["stop_short"], 2), "t1": None, "t1_level": None,
            "t1_px": None, "be_trigger": None, "breakeven_net": core.cents_up(k["ask"] + slip + 2 * fee / 100),
            "flat_by": None, "exit_profile": "noise", "variant": "noise", "policy_version": VERSION,
            "entry_px": st["price"], "noise_upper": st["upper"], "noise_lower": st["lower"], "grade": "R", "v": 31}
    pid, bwhy = paper.buy("noise", idea, ticker, side, plan, int(c.get("qty", 1)), t_end.isoformat())
    if not pid:
        paper.release_idea("noise", idea, bwhy)
    return st


def manage(p):
    """Every tick, between checks: the desk's hard rules (all out 15:25, the 20% premium ceiling). The band/VWAP stop
    is only checked at the half-hour marks, as in the paper."""
    now = core.now_et()
    sess = core.session_info(now)
    q, err = marketdata.option_quote(p["symbol"])
    pl = p["plan"]
    if q and q.get("executable"):
        pl["last_bid"] = q["bid"]
        mv = (q["bid"] - p["fill"]) / p["fill"] * 100
        p["mfe"], p["mae"] = round(max(p["mfe"] or 0, mv), 1), round(min(p["mae"] or 0, mv), 1)
        store.pos_save(p)
    if now.strftime("%H:%M") >= sess["all_out"]:
        return paper.sell(p, p["qty_open"], f"ALL OUT {sess['all_out']} (session rule)")
    if q and q.get("executable") and q["bid"] <= pl["premium_stop"]:
        return paper.sell(p, p["qty_open"], f"PREMIUM STOP (20% ceiling) ${pl['premium_stop']:.2f} hit (bid {q['bid']:.2f})")
    return None
