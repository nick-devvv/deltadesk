"""orb_credit.py - v4 premium ledger `orb_credit` (docs/STRATEGY_PLAN.md section 3.3). PRE-REGISTERED, unvalidated.

Source: Option Alpha, "Opening range breakout 0DTE" (2025; SPX, $15 wide, held to the close; 89.4% wins, PF 1.44,
max DD -$3,453; costs not modeled). Rules frozen 2026-10-31, before any result:
  * Opening range = high / low of the 1m bars 09:30-10:29 ET (all 60 must exist). Skip the day if the range width is
    under 0.2% of the 09:30 open.
  * The FIRST finished 1m bar after the range that closes above the high, finishing by 12:00 ET -> sell a $2-wide PUT
    credit spread, short strike = the first listed strike at or below the range low (long = short - $2).
    Closes below the low -> sell a $2-wide CALL credit spread, short = first listed strike at or above the range high
    (long = short + $2).
  * One trade per symbol per day. No stop, no target. Exit 15:25 ET (deviation from the source, which holds to the
    close: SPY/QQQ are American-style and can be assigned). 1 spread; max loss recorded at entry.
  * Fills: v4spreads pricing (shorts at bid - longs at ask; $0.65/contract/side), every leg quoted after the signal
    bar closed; the entry is retried for 5 minutes, then recorded as missed. FOMC days: no entry (risk layer).
Symbols: SPY, QQQ, and XSP when Schwab lists it that day.
"""
import pandas as pd

import core
import store
import v4common as C
import v4risk
import v4spreads as SP
import v4store as S

VERSION = "2026-11-02.v4-orb_credit"
LEDGER = "orb_credit"
BOOK = "premium"
MIN_WIDTH_PCT = 0.002
OR_END = "10:30"
LAST_SIGNAL_END = "12:00"


def opening_range(m1_today):
    """{open, high, low, width_pct} from the 60 bars 09:30-10:29, or None if any is missing."""
    if m1_today is None or not len(m1_today):
        return None
    w = m1_today[(m1_today.index.strftime("%H:%M") >= "09:30") & (m1_today.index.strftime("%H:%M") < OR_END)]
    if len(w) < 60:
        return None
    o, hi, lo = float(w["Open"].iloc[0]), float(w["High"].max()), float(w["Low"].min())
    return {"open": o, "high": hi, "low": lo, "width": hi - lo, "width_pct": (hi - lo) / o}


def first_break(m1_today, orr, now):
    """(side, bar_open, close, signal_t) of the first finished close beyond the range finishing by 12:00, or None.
    side 'P' = put credit spread (close above the high), 'C' = call credit spread (close below the low)."""
    w = m1_today[(m1_today.index.strftime("%H:%M") >= OR_END)]
    w = w[(w.index + pd.Timedelta(minutes=1) <= pd.Timestamp(now))]
    for ts, r in w.iterrows():
        end = ts + pd.Timedelta(minutes=1)
        if end.strftime("%H:%M") > LAST_SIGNAL_END:
            break
        if float(r["Close"]) > orr["high"]:
            return "P", ts, float(r["Close"]), end
        if float(r["Close"]) < orr["low"]:
            return "C", ts, float(r["Close"]), end
    return None


def pick_legs(rows, side, orr):
    """Short strike at/beyond the opposite edge, long $2 further out. -> (legs, None) or (None, why)."""
    strikes = [float(r["strike"]) for r in rows]
    if side == "P":
        below = [k for k in strikes if k <= orr["low"] + 1e-9]
        if not below:
            return None, f"no listed put strike at or below the range low {orr['low']:.2f}"
        ks = max(below)
        kl = ks - SP.WIDTH
    else:
        above = [k for k in strikes if k >= orr["high"] - 1e-9]
        if not above:
            return None, f"no listed call strike at or above the range high {orr['high']:.2f}"
        ks = min(above)
        kl = ks + SP.WIDTH
    rs, rl = SP.by_strike(rows, ks), SP.by_strike(rows, kl)
    if not rs or not rl:
        return None, f"the ${SP.WIDTH:g} wing strike {kl:g} is not listed"
    return [SP.leg(rs, "sell", side), SP.leg(rl, "buy", side)], None


def tick(ticker, m1, now=None):
    """One pass for one symbol (engine tick). m1 = finished 1m bars including today."""
    now = now or core.now_et()
    day = now.date()
    hm = now.strftime("%H:%M")
    if hm < OR_END or hm >= "15:25":
        return None
    dkey = f"{LEDGER}:{ticker}:{day}"
    if S.decided(dkey):
        return None                                                # one trade (or one skip) per symbol per day

    def done(decision, why, data=None):
        S.decide(dkey, LEDGER, ticker, decision, [why] if why else [], data or {}, "day", VERSION)
        return decision
    today = C.rth_day(C.finished(m1, now), day) if m1 is not None else None
    orr = opening_range(today)
    if orr is None:
        if hm >= "10:35":
            return done("SKIP", "opening range incomplete (fewer than 60 finished 1m bars 09:30-10:29)")
        return None
    data = {"or": orr}
    if orr["width_pct"] < MIN_WIDTH_PCT:
        return done("SKIP", f"range width {orr['width']:.2f} = {orr['width_pct'] * 100:.3f}% of the open, under 0.2%", data)
    br = first_break(today, orr, now)
    if br is None:
        if hm > LAST_SIGNAL_END or (hm == LAST_SIGNAL_END and now.second >= 5):
            return done("NO TRADE", "no finished 1m close beyond the range by 12:00", data)
        return None
    side, bar, close, signal_t = br
    data.update(signal={"side": side, "bar": bar.isoformat(), "close": close, "signal_t": signal_t.isoformat()},
                structure="put credit" if side == "P" else "call credit")
    if (pd.Timestamp(now) - signal_t).total_seconds() > SP.ENTRY_WINDOW_MIN * 60:
        return done("MISSED", f"no fill within {SP.ENTRY_WINDOW_MIN} min of the signal", data)
    why = v4risk.admit(LEDGER, BOOK, ticker, "long" if side == "P" else "short", now)
    if why:
        return done("BLOCKED-RISK", why, data)
    legs = store.kv_get(f"{dkey}:legs")                   # chosen once; retries only re-quote the legs (rate budget)
    if not legs:
        rows, err = SP.chain(SP.chain_symbol(ticker), side, day)
        if not rows:
            return None if (pd.Timestamp(now) - signal_t).total_seconds() < SP.ENTRY_WINDOW_MIN * 60 - 15 else \
                done("MISSED", f"no {side} chain ({err})", data)
        legs, lwhy = pick_legs(rows, side, orr)
        if not legs:
            return done("SKIP", lwhy, data)
        store.kv_set(f"{dkey}:legs", legs)
    plan = {"structure": data["structure"], "or_high": orr["high"], "or_low": orr["low"], "or_open": orr["open"],
            "signal": data["signal"], "exit_rule": "15:25, no stop, no target"}
    pid, owhy = SP.open_spread(LEDGER, BOOK, VERSION, ticker, f"{day}-{ticker}-ORBC", legs, signal_t,
                               "long" if side == "P" else "short", plan, now)
    if pid:
        return done("ORDER", None, dict(data, position=pid))
    if owhy and owhy.startswith("WAIT"):
        if (pd.Timestamp(now) - signal_t).total_seconds() >= SP.ENTRY_WINDOW_MIN * 60 - 15:
            return done("MISSED", owhy[6:], data)
        return None
    return done("SKIP", owhy, data)


def manage(p, now=None):
    return SP.manage_spread(p, now or core.now_et(), None)
