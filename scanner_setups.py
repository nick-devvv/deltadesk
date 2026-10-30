"""scanner_setups.py - the setups board: objective bullish and bearish setups across a DEFINED universe.

This is opportunity scanning, separate from symbol search (any ticker can be opened and charted, scanned or not).
Coverage is the universe file (config/universe.json, about 125 liquid optionable names) + SPY/QQQ + the watchlist +
the morning stocks-in-play list. It is NOT the whole market. The page shows the coverage and how fresh each row is.

Data and budget (all Schwab market data, through the shared 100-calls-a-minute limiter):
  * prices: one batched quote call per 100 symbols, every `quotes_every_s` (60 s);
  * 1m bars from 04:00 (pre-market included): refreshed in rotation, `bars_calls_per_min` (20) a minute.
    Names near a level, breaking out, or on unusual volume are refreshed first (about every minute); quiet names
    can be several minutes old, and their row says so.
  * baselines (ATR14, average volume, prior-day high/low, the time-of-day volume profile) come from the 08:30
    scanner pass (prior sessions only).

Every setup is a rule with numbers, listed in DEFINITIONS and shown on the page. ATR means the 14-day ATR.
A row is an observation, not a prediction. The rank score is a sort order made of the listed parts; it is NOT a
probability of winning. "No qualifying setups" is a normal answer.
"""
import threading
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import core
import indicators as I
import store

VERSION = "2026-10-30.v3.2-setups"
LIVE = ("ORB FORMING", "OPEN", "NO NEW ENTRIES", "ALL OUT")

DEFAULTS = {"enabled": True, "benchmark": "SPY", "quotes_every_s": 60, "bars_calls_per_min": 20, "mover_pct": 3.0,
            "rvol_unusual": 2.0, "approach_atr": 0.10, "retest_atr": 0.05, "extended_level_atr": 0.30,
            "extended_vwap_atr": 0.75, "wide_spread_pct": 0.15, "illiquid_avg_vol": 1_000_000, "min_price": 5.0,
            "rs_pts": 1.0, "vwap_sustain_min": 30, "vwap_sustain_frac": 0.9, "recent_min": 15,
            "orb_minutes": [5, 15, 30], "stale_s": 420, "thin_premarket_bars": 15}

DEFINITIONS = {
    "gainer": "Intraday gainer / loser: price vs the prior close is at least +mover_pct% / -mover_pct%. A list, not an entry.",
    "rvol": ("Unusual volume: time-of-day RVOL >= rvol_unusual. RVOL = today's regular-session volume from 09:30 to the end "
             "of the last finished 5-minute slot, divided by the MEDIAN volume over the same span on the last 10 sessions. "
             "If the profile is missing, an APPROXIMATION is used and labeled: volume / (14-day average daily volume x "
             "share of the session elapsed)."),
    "orb": ("Opening range N (5, 15, 30): high and low of the regular-session 1m bars from 09:30 to 09:30+N, used only "
            "once the range is complete. Approaching: within approach_atr x ATR of the edge. Breaking: price beyond the "
            "edge without a finished 1m close beyond. Closed beyond: a finished 1m close beyond the edge. Retest: after "
            "that close, price came back to within retest_atr x ATR of the edge and the last close is still beyond. "
            "Failed: after a close beyond, the last 1m close is back inside the range."),
    "vwap": ("VWAP (regular session, bar-based). Reclaim: within the last recent_min minutes a 1m close crossed above "
             "VWAP after at least 5 of the 10 bars before it closed below, and every close since is above. Reject: 7+ of the "
             "last 10 closes below VWAP, a high within approach_atr x ATR of VWAP in the last 5 bars, and the last close "
             "below VWAP by more than retest_atr x ATR. Sustained strength / weakness: at least vwap_sustain_frac of the "
             "last vwap_sustain_min closes above / below VWAP, the last one too, and VWAP rising / falling over that time."),
    "pm": ("Pre-market high / low (04:00-09:29): same break states as the opening range, on regular-session 1m closes. "
           "Fewer than thin_premarket_bars pre-market bars is flagged thin."),
    "pd": "Previous-day high / low (prior regular session, daily bar): same break states as the opening range.",
    "rs": ("Relative strength / weakness vs the benchmark (SPY): the stock's % change since 09:30 minus SPY's, in points. "
           "At least +rs_pts with price above VWAP = strength; at most -rs_pts below VWAP = weakness. Simple difference, "
           "not beta-adjusted."),
    "momo": ("Momentum continuation: above VWAP, 5m EMA9 > EMA21, a new high of day in the last 10 minutes, RVOL >= 1.2 "
             "(mirror for shorts). Pullback: same trend, the high of day is 10+ minutes old, price back within 0.15 ATR of "
             "the 5m EMA9 or VWAP and still above VWAP. Trigger still missing: a 1m close above the prior 1m high."),
    "flags": ("Flags: illiquid (14-day average volume < illiquid_avg_vol or price < min_price), wide spread (stock "
              "bid/ask > wide_spread_pct% of price), low-volume move (moved >= half of mover_pct% with RVOL < 1), extended "
              "(more than extended_level_atr x ATR past the trigger level, or more than extended_vwap_atr x ATR from VWAP), "
              "stale (no fresh bars or price for stale_s seconds)."),
    "score": ("Rank score = setup state (approaching 1, breaking 2, closed beyond / reclaim / reject 3, retest holding "
              "3.5, failed 2.5, sustained 2, continuation 2, pullback 2.5, relative strength 1.5, mover / unusual volume 1) "
              "(a failed break scores 2.5 as a watch; only REVERSAL CONFIRMED - a close through the range midpoint on the "
              "reversal side of VWAP - qualifies) + volume (0.75 x RVOL, at most 3) + liquidity (+1 tight and liquid, -1.5 wide spread, -2 illiquid) "
              "- 2 if extended +/- 0.5 for agreeing / disagreeing with SPY's direction since the open. "
              "It is only a sort order. It is not a probability of winning."),
}

STATE_PTS = {"REVERSAL CONFIRMED": 3, "APPROACHING": 1, "BREAKING": 2, "CLOSED BEYOND": 3, "RECLAIMED": 3, "REJECTED": 3, "RETEST HOLDING": 3.5,
             "FAILED": 2.5, "SUSTAINED": 2, "CONTINUATION": 2, "PULLBACK": 2.5, "RS": 1.5, "MOVER": 1, "UNUSUAL VOLUME": 1}
QUALIFYING = ("BREAKING", "CLOSED BEYOND", "RECLAIMED", "REJECTED", "RETEST HOLDING", "REVERSAL CONFIRMED", "CONTINUATION", "PULLBACK")

_lock = threading.Lock()
_state = {"thread": None, "stop": False, "status": "idle", "last_error": None, "rows": {}, "quotes": {}, "quotes_at": None,
          "bars": {}, "budget": 0.0, "last_step": None, "day": None, "cycle_s": None, "calls": 0}


def cfg():
    c = dict(DEFAULTS)
    c.update(core.policy().get("setups") or {})
    c.update(store.kv_get("setups_settings") or {})          # Nick's overrides from the Markets page
    return c


# ---------------------------------------------------------------- pure calculations
def _day_open(d):
    return pd.Timestamp(datetime.combine(d, datetime.min.time()), tz=core.ET) + timedelta(hours=9, minutes=30)


def rth_today(m1, day):
    if m1 is None or not len(m1):
        return m1
    x = m1[m1.index.date == day]
    return x[[("09:30" <= i.strftime("%H:%M") <= "15:59") for i in x.index]]


def orb(r1, n, now):
    """Opening range of the first n regular-session minutes. complete=True only once 09:30+n has passed AND at least
    80% of those minutes have bars (thin names can skip minutes). Pre-market bars are never included."""
    if r1 is None or not len(r1):
        return None
    s = _day_open(r1.index[0].date())
    end = s + timedelta(minutes=n)
    w = r1[(r1.index >= s) & (r1.index < end)]
    if not len(w):
        return None
    complete = now >= end and len(w) >= max(1, int(0.8 * n))
    return {"high": float(w["High"].max()), "low": float(w["Low"].min()), "complete": bool(complete), "bars": len(w),
            "end": end.isoformat(), "n": n}


def break_state(post, level, side, px, atr, c):
    """Break states of one level for one side ('long' = above, 'short' = below) from FINISHED 1m bars after the level
    became known (`post`) plus the current price `px`. Returns (state, info) or (None, info)."""
    sign = 1 if side == "long" else -1
    tol_a, tol_r = c["approach_atr"] * atr, c["retest_atr"] * atr
    closes = post["Close"] if post is not None and len(post) else pd.Series(dtype=float)
    beyond = closes[(closes - level) * sign > 0]
    info = {"level": level}
    if not len(beyond):
        if px is not None and (px - level) * sign > 0:
            return "BREAKING", info
        if px is not None and 0 <= (level - px) * sign <= tol_a:
            return "APPROACHING", info
        return None, info
    t0 = beyond.index[0]
    info["first_close_beyond"] = t0
    after = post[post.index > t0]
    bar = post.loc[t0]
    prior = post[post.index < t0]["Volume"]
    med = float(prior.median()) if len(prior) >= 3 else None
    info["break_vol_x"] = round(float(bar["Volume"]) / med, 1) if med else None
    last_close = float(closes.iloc[-1])
    if (last_close - level) * sign <= 0:
        return "FAILED", info
    if len(after):
        touch = after["Low"].min() if side == "long" else after["High"].max()
        if (touch - level) * sign <= tol_r:
            return "RETEST HOLDING", info
    return "CLOSED BEYOND", info


def tod_rvol(r1, base, now):
    """(rvol, label). Time-of-day RVOL through the last finished 5-minute slot; labeled approximation otherwise."""
    if r1 is None or not len(r1):
        return None, "no regular-session bars yet"
    s = _day_open(r1.index[0].date())
    slots_done = int(min((now - s).total_seconds() // 300, 78))
    if slots_done < 1:
        return None, "RVOL starts after the first 5 minutes"
    slot_end = s + timedelta(minutes=5 * slots_done)
    vol = float(r1[r1.index < slot_end]["Volume"].sum())
    last_slot = (slot_end - timedelta(minutes=5)).strftime("%H:%M")
    prof = (base or {}).get("tod_cum") or {}
    if prof.get(last_slot):
        return round(vol / prof[last_slot], 2), f"time of day: 09:30-{slot_end.strftime('%H:%M')} vs the median of {base.get('tod_n')} sessions"
    av = (base or {}).get("avg_vol14")
    if av:
        frac = slots_done / 78
        return round(vol / (av * frac), 2), "APPROXIMATE: vs average daily volume x share of the session (no time-of-day profile)"
    return None, "no volume baseline"


def _fmt_t(t):
    return pd.Timestamp(t).strftime("%H:%M")


def evaluate(ticker, m1, base, q, bench, now, c=None):
    """All setups for one ticker. m1 = today's 1m bars incl. pre-market (FINISHED bars only), base = scanner baseline,
    q = latest quote {last, prev, bid, ask, ...}, bench = (benchmark m1 today) or None. Returns (ticker_info, [setups])."""
    c = c or cfg()
    day = now.date()
    base = base or {}
    r1 = rth_today(m1, day)
    pre = None
    if m1 is not None and len(m1):
        x = m1[m1.index.date == day]
        pre = x[[("04:00" <= i.strftime("%H:%M") <= "09:29") for i in x.index]]
    px = (q or {}).get("last")
    if px is None and r1 is not None and len(r1):
        px = float(r1["Close"].iloc[-1])
    prev = (q or {}).get("prev") or base.get("prev_close")
    atr = base.get("atr14")
    bid, ask = (q or {}).get("bid"), (q or {}).get("ask")
    spread_pct = round((ask - bid) / px * 100, 3) if bid and ask and px and ask >= bid else None
    info = {"ticker": ticker, "price": px, "prev_close": prev, "atr14": atr, "spread_pct": spread_pct,
            "avg_vol14": base.get("avg_vol14"), "day_pct": round((px / prev - 1) * 100, 2) if px and prev else None,
            "flags": [], "bars_last": _fmt_t(m1.index[-1]) if m1 is not None and len(m1) else None}
    rvol, rvol_how = tod_rvol(r1, base, now)
    info.update(rvol=rvol, rvol_method=rvol_how)
    if not px or not atr or atr <= 0:
        info["flags"].append("no ATR baseline yet" if not atr else "no price")
        return info, []
    avg = base.get("avg_vol14") or 0
    if avg < c["illiquid_avg_vol"] or px < c["min_price"]:
        info["flags"].append("illiquid")
    if spread_pct is not None and spread_pct > c["wide_spread_pct"]:
        info["flags"].append("wide spread")
    dp = info["day_pct"]
    if dp is not None and abs(dp) >= c["mover_pct"] / 2 and (rvol is None or rvol < 1.0):
        info["flags"].append("low-volume move")
    vw = None
    if r1 is not None and len(r1):
        vws = I.session_vwap(r1)
        vw = float(vws.iloc[-1]) if vws.iloc[-1] == vws.iloc[-1] else None
        info["vwap"] = round(vw, 2) if vw else None
        info["hod"], info["lod"] = float(r1["High"].max()), float(r1["Low"].min())
        info["open"] = float(r1["Open"].iloc[0])
    bench_ret = None
    if bench is not None and len(bench):
        br = rth_today(bench, day)
        if br is not None and len(br):
            bench_ret = (float(br["Close"].iloc[-1]) / float(br["Open"].iloc[0]) - 1) * 100
    info["bench_ret"] = round(bench_ret, 2) if bench_ret is not None else None
    out = []

    def add(setup, kind, direction, state, level_name, level, why, missing, inval_level, inval_text, levels):
        dist = px - level if level is not None else None
        ext_lv = level is not None and state in ("CLOSED BEYOND", "RETEST HOLDING", "BREAKING", "RECLAIMED", "CONTINUATION") \
            and dist * (1 if direction == "long" else -1) > c["extended_level_atr"] * atr
        ext_vw = vw is not None and (px - vw) * (1 if direction == "long" else -1) > c["extended_vwap_atr"] * atr
        extended = bool(ext_lv or ext_vw)
        ext_why = []
        if ext_lv:
            ext_why.append(f"{abs(dist) / atr:.2f} ATR past {level_name}")
        if ext_vw:
            ext_why.append(f"{abs(px - vw) / atr:.2f} ATR from VWAP")
        out.append({"setup": setup, "kind": kind, "direction": direction, "state": state, "level_name": level_name,
                    "level": round(level, 2) if level is not None else None,
                    "distance": round(dist, 2) if dist is not None else None,
                    "distance_pct": round(dist / px * 100, 2) if dist is not None else None,
                    "distance_atr": round(dist / atr, 2) if dist is not None else None,
                    "why": why, "missing": missing, "invalidation": round(inval_level, 2) if inval_level is not None else None,
                    "invalidation_text": inval_text, "extended": extended, "extended_why": ", ".join(ext_why),
                    "chart_levels": levels})

    # --- opening ranges
    if r1 is not None and len(r1):
        for n in c["orb_minutes"]:
            o = orb(r1, n, now)
            if not o or not o["complete"]:
                continue
            post = r1[r1.index >= pd.Timestamp(o["end"])]
            lv = [{"name": f"ORB{n} high", "value": round(o["high"], 2)}, {"name": f"ORB{n} low", "value": round(o["low"], 2)}]
            for side, edge, other in (("long", o["high"], o["low"]), ("short", o["low"], o["high"])):
                st, inf = break_state(post, edge, side, px, atr, c)
                if not st:
                    continue
                word = "high" if side == "long" else "low"
                bx = f", breakout bar volume {inf['break_vol_x']}x the session's median 1m bar" if inf.get("break_vol_x") else ""
                t0 = f" at {_fmt_t(inf['first_close_beyond'])}" if inf.get("first_close_beyond") is not None else ""
                why = {"APPROACHING": f"price {px:.2f} is {abs(px - edge):.2f} from the ORB{n} {word} {edge:.2f} (within {c['approach_atr']} ATR)",
                       "BREAKING": f"price {px:.2f} is past the ORB{n} {word} {edge:.2f}, no finished 1m close beyond yet",
                       "CLOSED BEYOND": f"1m close beyond the ORB{n} {word} {edge:.2f}{t0}{bx}",
                       "RETEST HOLDING": f"closed beyond the ORB{n} {word}{t0}, came back to it, and the last close still holds{bx}",
                       "FAILED": f"closed beyond the ORB{n} {word}{t0} but the last 1m close is back inside the range"}[st]
                if st == "FAILED":
                    d2 = "short" if side == "long" else "long"
                    mid = (o["high"] + o["low"]) / 2
                    lc = float(post["Close"].iloc[-1]) if len(post) else None
                    # a failed break is only a WATCH; the reversal needs its own confirmation: a finished close through the
                    # range midpoint AND on the reversal side of VWAP. Anything less is ambiguous: wait.
                    conf = lc is not None and ((lc < mid and (vw is None or lc < vw)) if side == "long" else (lc > mid and (vw is None or lc > vw)))
                    add(f"ORB{n} failed {'breakout' if side == 'long' else 'breakdown'}", "orb", d2, "REVERSAL CONFIRMED" if conf else st,
                        f"ORB{n} {word}", edge,
                        why + (f"; then a 1m close {lc:.2f} through the range midpoint {mid:.2f} on the {'weak' if side == 'long' else 'strong'} side of VWAP" if conf else ""),
                        "nothing for the rule: a reversal setup, check the option" if conf else
                        f"reversal confirmation: a finished 1m close through the range midpoint {mid:.2f} and {'below' if side == 'long' else 'above'} VWAP",
                        edge, f"a 1m close back {'above' if side == 'long' else 'below'} {edge:.2f}", lv + [{"name": f"ORB{n} mid", "value": round(mid, 2)}])
                else:
                    miss = {"APPROACHING": f"price through {edge:.2f}, then a finished 1m close beyond it",
                            "BREAKING": f"a finished 1m close {'above' if side == 'long' else 'below'} {edge:.2f}",
                            "CLOSED BEYOND": "nothing for the rule; check the option and that it isn't extended",
                            "RETEST HOLDING": "nothing for the rule; the retest held"}[st]
                    add(f"ORB{n} {'breakout' if side == 'long' else 'breakdown'}", "orb", side, st, f"ORB{n} {word}", edge, why, miss,
                        edge, f"a 1m close back inside the range ({'below' if side == 'long' else 'above'} {edge:.2f})", lv)
    # --- pre-market and previous-day levels
    lvls = []
    if pre is not None and len(pre):
        thin = len(pre) < c["thin_premarket_bars"]
        if thin:
            info["flags"].append("thin pre-market")
        lvls += [("PM high", float(pre["High"].max()), "long", "pm"), ("PM low", float(pre["Low"].min()), "short", "pm")]
    if base.get("pdh") is not None:
        lvls += [("PD high", float(base["pdh"]), "long", "pd"), ("PD low", float(base["pdl"]), "short", "pd")]
    if r1 is not None and len(r1):
        for name, level, side, kind in lvls:
            st, inf = break_state(r1, level, side, px, atr, c)
            if not st:
                continue
            t0 = f" at {_fmt_t(inf['first_close_beyond'])}" if inf.get("first_close_beyond") is not None else ""
            word = "above" if side == "long" else "below"
            if st == "FAILED":
                add(f"{name} failed break", kind, "short" if side == "long" else "long", st, name, level,
                    f"closed {word} the {name} {level:.2f}{t0}, now back on the other side", f"follow-through away from {level:.2f}",
                    level, f"a 1m close back {word} {level:.2f}", [{"name": name, "value": round(level, 2)}])
            else:
                add(f"{name} break", kind, side, st, name, level,
                    {"APPROACHING": f"price {px:.2f} within {abs(px - level):.2f} of the {name} {level:.2f}",
                     "BREAKING": f"price past the {name} {level:.2f}, no finished 1m close beyond yet",
                     "CLOSED BEYOND": f"1m close {word} the {name} {level:.2f}{t0}",
                     "RETEST HOLDING": f"closed {word} the {name}{t0}, retested it and held"}[st],
                    {"APPROACHING": f"a finished 1m close {word} {level:.2f}", "BREAKING": f"a finished 1m close {word} {level:.2f}"}.get(st, "nothing for the rule"),
                    level, f"a 1m close back {'below' if side == 'long' else 'above'} {level:.2f}", [{"name": name, "value": round(level, 2)}])
    # --- VWAP
    if r1 is not None and len(r1) >= 12 and vw is not None:
        vws = I.session_vwap(r1)
        cl = r1["Close"]
        above = (cl > vws)
        tol_a, tol_r = c["approach_atr"] * atr, c["retest_atr"] * atr
        rec = c["recent_min"]
        k_list = [k for k in range(max(1, len(cl) - rec), len(cl)) if not above.iloc[k - 1] and above.iloc[k]]
        if k_list:
            k = k_list[-1]
            before = above.iloc[max(0, k - 10):k]
            if (~before).sum() >= 5 and above.iloc[k:].all():
                h = float(r1["High"].iloc[k])
                add("VWAP reclaim", "vwap", "long", "RECLAIMED", "VWAP", vw,
                    f"1m close back above VWAP at {_fmt_t(cl.index[k])} after {int((~before).sum())} of the 10 bars before closed below; every close since is above",
                    f"a pullback that holds VWAP, or a break of the reclaim bar's high {h:.2f}", vw, f"a 1m close back below VWAP ({vw:.2f})",
                    [{"name": "VWAP", "value": round(vw, 2)}])
        last10 = above.iloc[-10:]
        if (~last10).sum() >= 7 and (r1["High"].iloc[-5:] >= vws.iloc[-5:] - tol_a).any() and cl.iloc[-1] < vw - tol_r:
            add("VWAP rejection", "vwap", "short", "REJECTED", "VWAP", vw,
                f"{int((~last10).sum())} of the last 10 closes below VWAP, price tagged VWAP in the last 5 minutes and closed back below",
                f"a 1m close below the rejection bars' low {float(r1['Low'].iloc[-5:].min()):.2f}", vw,
                f"a 1m close back above VWAP ({vw:.2f})", [{"name": "VWAP", "value": round(vw, 2)}])
        m = c["vwap_sustain_min"]
        if len(cl) >= m:
            frac = float(above.iloc[-m:].mean())
            slope = float(vws.iloc[-1] - vws.iloc[-m])
            if frac >= c["vwap_sustain_frac"] and above.iloc[-1] and slope > 0:
                add("Holding above VWAP", "vwap", "long", "SUSTAINED", "VWAP", vw,
                    f"{int(round(frac * m))} of the last {m} closes above a rising VWAP", "an entry trigger (pullback to VWAP, or a new high)",
                    vw, f"a 1m close below VWAP ({vw:.2f})", [{"name": "VWAP", "value": round(vw, 2)}])
            if 1 - frac >= c["vwap_sustain_frac"] and not above.iloc[-1] and slope < 0:
                add("Holding below VWAP", "vwap", "short", "SUSTAINED", "VWAP", vw,
                    f"{int(round((1 - frac) * m))} of the last {m} closes below a falling VWAP", "an entry trigger (bounce into VWAP, or a new low)",
                    vw, f"a 1m close above VWAP ({vw:.2f})", [{"name": "VWAP", "value": round(vw, 2)}])
    # --- relative strength vs the benchmark
    if bench_ret is not None and info.get("open") and vw is not None and ticker != c["benchmark"]:
        sret = (px / info["open"] - 1) * 100
        diff = sret - bench_ret
        info["rs_pts"] = round(diff, 2)
        if diff >= c["rs_pts"] and px > vw:
            add("Relative strength vs SPY", "rs", "long", "RS", "VWAP", vw,
                f"{sret:+.2f}% since 09:30 vs SPY {bench_ret:+.2f}% ({diff:+.2f} pts), above VWAP", "an entry trigger on the stock's own chart",
                vw, f"losing VWAP ({vw:.2f})", [{"name": "VWAP", "value": round(vw, 2)}])
        elif diff <= -c["rs_pts"] and px < vw:
            add("Relative weakness vs SPY", "rs", "short", "RS", "VWAP", vw,
                f"{sret:+.2f}% since 09:30 vs SPY {bench_ret:+.2f}% ({diff:+.2f} pts), below VWAP", "an entry trigger on the stock's own chart",
                vw, f"reclaiming VWAP ({vw:.2f})", [{"name": "VWAP", "value": round(vw, 2)}])
    # --- momentum continuation / pullback (5m trend)
    if r1 is not None and len(r1) >= 30 and vw is not None:
        b5, done = I.aggregate(r1, 5, r1.index[-1])
        b5 = b5[done.values] if len(done) else b5
        if len(b5) >= 6:
            e9, e21 = float(I.ema(b5["Close"], 9).iloc[-1]), float(I.ema(b5["Close"], 21).iloc[-1])
            last10 = r1.iloc[-10:]
            for side in ("long", "short"):
                sign = 1 if side == "long" else -1
                trend = (px - vw) * sign > 0 and (e9 - e21) * sign > 0
                if not trend:
                    continue
                ext_now = info["hod"] if side == "long" else info["lod"]
                t_ext = r1["High"].idxmax() if side == "long" else r1["Low"].idxmin()
                fresh = t_ext >= last10.index[0]
                word = "high" if side == "long" else "low"
                if fresh and (rvol or 0) >= 1.2:
                    add(f"Momentum continuation ({'up' if side == 'long' else 'down'})", "momo", side, "CONTINUATION", f"day {word}", ext_now,
                        f"{'above' if side == 'long' else 'below'} VWAP, 5m EMA9 {e9:.2f} {'>' if side == 'long' else '<'} EMA21 {e21:.2f}, new day {word} at {_fmt_t(t_ext)}, RVOL {rvol}",
                        f"a break of the day {word} {ext_now:.2f}; entries far from VWAP are extended", e21,
                        f"a 5m close {'below' if side == 'long' else 'above'} EMA21 ({e21:.2f})",
                        [{"name": f"Day {word}", "value": round(ext_now, 2)}, {"name": "VWAP", "value": round(vw, 2)}])
                elif not fresh:
                    near = min((e9, vw), key=lambda v: abs(px - v))
                    if abs(px - near) <= 0.15 * atr and (px - vw) * sign >= 0:
                        pb = float(r1["High"].iloc[-2]) if side == "long" else float(r1["Low"].iloc[-2])
                        add(f"Pullback in an {'up' if side == 'long' else 'down'}trend", "momo", side, "PULLBACK",
                            "5m EMA9" if near == e9 else "VWAP", near,
                            f"trend intact ({'above' if side == 'long' else 'below'} VWAP, 5m EMA9 {'>' if side == 'long' else '<'} EMA21); day {word} {ext_now:.2f} set at {_fmt_t(t_ext)}; price back to {near:.2f}",
                            f"the turn: a 1m close {'above' if side == 'long' else 'below'} the prior 1m {word} {pb:.2f}", vw,
                            f"a 1m close {'below' if side == 'long' else 'above'} VWAP ({vw:.2f})",
                            [{"name": "VWAP", "value": round(vw, 2)}, {"name": f"Day {word}", "value": round(ext_now, 2)}])
    # --- lists: movers and unusual volume (information, not entries)
    if dp is not None and abs(dp) >= c["mover_pct"]:
        side = "long" if dp > 0 else "short"
        add("Intraday gainer" if dp > 0 else "Intraday loser", "mover", side, "MOVER", "VWAP" if vw else "prior close", vw or prev,
            f"{dp:+.2f}% vs the prior close {prev:.2f}", "a setup above, on its own chart", vw, "n/a: a list, not an entry", [])
    if rvol is not None and rvol >= c["rvol_unusual"]:
        side = "long" if (dp or 0) >= 0 else "short"
        add("Unusual volume", "rvol", side, "UNUSUAL VOLUME", "VWAP" if vw else "prior close", vw or prev,
            f"RVOL {rvol} ({rvol_how})", "a setup above, on its own chart", vw, "n/a: a list, not an entry", [])
    return info, out


def score(info, s, fresh_ok=True):
    """Transparent rank score: returns (score or None, parts)."""
    if not fresh_ok:
        return None, {"stale": "not ranked: data is stale"}
    parts = {"setup": STATE_PTS.get(s["state"], 0)}
    rv = info.get("rvol")
    parts["volume"] = round(min(0.75 * rv, 3), 2) if rv else 0
    liq = 0
    if "illiquid" in info["flags"]:
        liq -= 2
    if "wide spread" in info["flags"]:
        liq -= 1.5
    if not liq and info.get("spread_pct") is not None and (info.get("avg_vol14") or 0) >= 2_000_000:
        liq = 1
    parts["liquidity"] = liq
    parts["extended"] = -2 if s["extended"] else 0
    br = info.get("bench_ret")
    if br is not None and abs(br) >= 0.1 and s["kind"] not in ("rs",):
        parts["market"] = 0.5 if (br > 0) == (s["direction"] == "long") else -0.5
    else:
        parts["market"] = 0
    return round(sum(parts.values()), 2), parts


def rows_for(info, setups, fresh):
    out = []
    for s in setups:
        sc, parts = score(info, s, fresh["ok"])
        qualifies = (s["state"] in QUALIFYING and fresh["ok"] and not s["extended"]
                     and "illiquid" not in info["flags"] and "wide spread" not in info["flags"])
        out.append(dict(s, ticker=info["ticker"], price=info["price"], day_pct=info["day_pct"], rvol=info["rvol"],
                        rvol_method=info["rvol_method"], spread_pct=info["spread_pct"], avg_vol14=info["avg_vol14"],
                        flags=info["flags"] + (["extended"] if s["extended"] else []) + ([] if fresh["ok"] else ["stale"]),
                        fresh=fresh, score=sc, score_parts=parts, qualifies=qualifies, atr14=info["atr14"], vwap=info.get("vwap")))
    return out


# ---------------------------------------------------------------- the board (worker)
def coverage():
    import scanner
    c = cfg()
    tick = tickers()
    n = len(tick)
    cyc = n / max(1, c["bars_calls_per_min"])
    return {"universe": n, "universe_file": len(scanner.universe()), "quotes_every_s": c["quotes_every_s"],
            "bars_calls_per_min": c["bars_calls_per_min"], "bars_full_cycle_min": round(cyc, 1),
            "measured_cycle_s": _state["cycle_s"], "benchmark": c["benchmark"],
            "limits": [f"{n} symbols: the universe file, SPY/QQQ, your watchlist and today's stocks in play. Not the whole market.",
                       f"Prices every {c['quotes_every_s']} s (batched quotes).",
                       f"1m bars for {c['bars_calls_per_min']} symbols a minute; names near a level or on heavy volume first. "
                       f"A full pass over quiet names takes about {cyc:.0f} minutes, so their rows can be that old.",
                       "Option liquidity is checked when you open a plan for the symbol, not for every row.",
                       "Any other ticker: use the symbol search to chart it."]}


def tickers():
    import scanner
    out = list(dict.fromkeys(list(core.policy()["instruments"]) + scanner.universe()))
    try:
        import watchlist
        out += list(watchlist.tickers() or [])
    except Exception:
        pass
    day = str(core.now_et().date())
    try:
        out += [r["ticker"] for r in scanner._rows(day) if str(r.get("status", "")).startswith("watching")]
    except Exception:
        pass
    return list(dict.fromkeys(t.upper() for t in out if t))


def _fetch():
    import scanner
    return scanner._fetch


def _bars_for(t, day, now):
    """Main instruments come from the live pipeline (no extra calls); others from the rotation cache."""
    import marketdata
    if t in core.policy()["instruments"]:
        m1, _, meta = marketdata.bars(t, refresh=False)
        if m1 is not None and len(m1):
            return m1[m1.index.date == day], time.time() - (meta.get("bar_age_s") or 0)
    hit = _state["bars"].get(t)
    return (hit[1], hit[0]) if hit else (None, None)


def _finished(df, now):
    if df is None or not len(df):
        return df
    return df[df.index + pd.Timedelta(minutes=1) <= now]


def recompute(t, now, base_all):
    day = now.date()
    m1, fetched = _bars_for(t, day, now)
    m1 = _finished(m1, now)
    q = _state["quotes"].get(t)
    bench, _ = _bars_for(cfg()["benchmark"], day, now)
    info, setups = evaluate(t, m1, (base_all or {}).get(t), q, _finished(bench, now), now)
    c = cfg()
    q_age = time.time() - _state["quotes_at"] if _state["quotes_at"] else None
    b_age = time.time() - fetched if fetched else None
    ok = (q_age is not None and q_age <= c["stale_s"]) and (b_age is not None and b_age <= c["stale_s"])
    fresh = {"price_age_s": round(q_age) if q_age is not None else None, "bars_age_s": round(b_age) if b_age is not None else None,
             "ok": bool(ok), "bars_last": info.get("bars_last")}
    with _lock:
        _state["rows"][t] = {"info": info, "rows": rows_for(info, setups, fresh), "at": now.isoformat(timespec="seconds")}
    return _state["rows"][t]


def _priority(t):
    r = _state["rows"].get(t)
    hit = _state["bars"].get(t)
    if not hit:
        return 1e6
    p = (time.time() - hit[0]) / 60
    if r:
        st = {x["state"] for x in r["rows"]}
        if st & {"APPROACHING", "BREAKING", "RETEST HOLDING", "CLOSED BEYOND", "PULLBACK"}:
            p += 5
        if (r["info"].get("rvol") or 0) >= 2:
            p += 3
        p += min(abs(r["info"].get("day_pct") or 0), 10) / 2
    return p


def step(now=None):
    c = cfg()
    if not c.get("enabled", True):
        _state["status"] = "off"
        return
    now = now or core.now_et()
    f = _fetch()
    sess = core.session_info(now)
    hm = now.strftime("%H:%M")
    if sess.get("holiday") or now.weekday() >= 5 or not ("04:00" <= hm <= "16:05"):
        _state["status"] = "market closed (the board runs 04:00-16:05 ET on trading days)"
        return
    if not f.ready():
        _state["status"] = "waiting for Schwab (the board never scans delayed data)"
        return
    day = now.date()
    if _state["day"] != day:
        with _lock:
            _state.update(day=day, rows={}, quotes={}, bars={}, quotes_at=None, budget=0.0)
    base_all = store.kv_get(f"scan_base:{day}")
    if not base_all:
        _state["status"] = "waiting for the 08:30 baselines (ATR, average volume, volume profile)"
        return
    tick = tickers()
    t_now = time.time()
    dt = t_now - (_state["last_step"] or t_now - 5)
    _state["last_step"] = t_now
    _state["budget"] = min(_state["budget"] + dt * c["bars_calls_per_min"] / 60, c["bars_calls_per_min"])
    if not _state["quotes_at"] or t_now - _state["quotes_at"] >= c["quotes_every_s"]:
        qs, err = f.quotes([t for t in tick])
        if qs:
            _state["quotes"].update(qs)
            _state["quotes_at"] = t_now
        _state["calls"] += (len(tick) + 99) // 100
    todo = sorted([t for t in tick if t not in core.policy()["instruments"]], key=_priority, reverse=True)
    while _state["budget"] >= 1 and todo:
        t = todo.pop(0)
        _state["budget"] -= 1
        _state["calls"] += 1
        try:
            df = f.m1_ext(t, day, now)
        except Exception:
            df = None
        if df is not None and len(df):
            _state["bars"][t] = (time.time(), df.sort_index())
    ages = [time.time() - v[0] for k, v in _state["bars"].items()]
    _state["cycle_s"] = round(max(ages)) if ages else None
    for t in tick:
        try:
            recompute(t, now, base_all)
        except Exception as e:
            _state["last_error"] = f"{t}: {type(e).__name__}: {e}"[:200]
    _state["status"] = "scanning" if sess["state"] in LIVE else f"{sess['state'].lower()}: levels update, setups need the session"


def board(direction=None, setup=None, watch_only=False, best_per_stock=True):
    rows = []
    with _lock:
        for t, r in _state["rows"].items():
            rows += r["rows"]
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    if best_per_stock:
        seen, best = {}, []
        for r in rows:
            if r["ticker"] in seen:
                seen[r["ticker"]]["also"].append(r["setup"])
                continue
            r = dict(r, also=[])
            seen[r["ticker"]] = r
            best.append(r)
        rows = best
    q = [r for r in rows if r["qualifies"]]
    summary = (f"{len(q)} qualifying setup(s) right now." if q else
               "No qualifying setups right now. Waiting is a valid choice.")
    return {"status": _state["status"], "last_error": _state["last_error"], "version": VERSION, "coverage": coverage(),
            "rows": rows, "qualifying": len(q), "summary": summary, "definitions": DEFINITIONS, "config": cfg(),
            "updated": datetime.now(core.ET).isoformat(timespec="seconds")}


def _run():
    while not _state["stop"]:
        try:
            step()
            _state["last_error"] = None if not _state["last_error"] else _state["last_error"]
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {e}"[:200]
        time.sleep(5)


def start():
    if _state["thread"] or not cfg().get("enabled", True):
        return False
    th = threading.Thread(target=_run, daemon=True, name="setups-board")
    _state["thread"] = th
    th.start()
    return True
