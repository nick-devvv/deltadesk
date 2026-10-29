"""strategy.py - v3 setups on ONE snapshot of finalized bars, with machine-checkable evidence.

Flow per completed decision moment (every finalized 1m bar):
  build_snapshot(ticker) -> levels, indicators, regime, all from marketdata (Schwab)
  detect_all(snapshot)   -> raw candidates from every detector, evaluated against the SAME snapshot
  arbitrate(candidates)  -> merge same-side detectors into one idea; calls AND puts on the same bar -> SKIP (main)
  qualify(idea, snap)    -> momentum / rejected-spike / regime / afternoon / extension / event / data checks
Contract choice, structural risk, 2:1 and sizing live in optionmath.py; execution in paper.py; exits in exits.py.

Grades are rules-based labels (which checks passed), NOT win probabilities.
"""
import json
from datetime import datetime

import pandas as pd

import core
import indicators as I
import marketdata
import store

CONTINUATION = {"ORB_BREAK", "ORB_RETEST", "PDH_RETEST", "PDL_RETEST", "VWAP_RECLAIM", "VWAP_MACD"}
REVERSAL = {"FAILED_BREAK"}
PRIORITY = ["ORB_RETEST", "PDH_RETEST", "PDL_RETEST", "VWAP_MACD", "FAILED_BREAK", "VWAP_RECLAIM", "ORB_BREAK"]


def cfg():
    return core.policy()["v3"]


# ================================================================ snapshot
def build_snapshot(ticker, m1=None, meta=None):
    """Everything a decision needs, from finalized bars only. Returns dict with ok=False + reason when unusable."""
    if m1 is None:
        m1, _forming, meta = marketdata.bars(ticker)
    meta = meta or {}
    snap = {"ticker": ticker, "ok": False, "meta": meta, "built": marketdata.now().isoformat(timespec="seconds")}
    if m1 is None or len(m1) < 30:
        snap["reason"] = "not enough finalized bars"
        return snap
    c = cfg()
    today = m1.index[-1].date()
    r1 = I.rth(m1, today)
    if r1 is None or not len(r1):
        snap["reason"] = "regular session not open yet"
        snap["levels"] = levels(m1, None, None)
        return snap
    last_open = r1.index[-1]
    t = last_open + pd.Timedelta(minutes=1)     # decision time = end of the newest finalized 1m bar
    b5, f5 = I.aggregate(r1, c["decision_tf_min"], last_open)
    b5 = b5[f5]
    # ATR / ADX continue across sessions on regular-hours 5m bars (like MACD), so they are usable from the open
    b5m, f5m = I.aggregate_multi(m1[m1.index <= last_open], c["decision_tf_min"], last_open)
    b5m = b5m[f5m]
    b2m, f2m = I.aggregate_multi(m1[m1.index <= last_open], c["momentum_tf_min"], last_open)
    b2m = b2m[f2m]
    b2 = b2m[b2m.index.date == today]
    vw1 = I.session_vwap(r1)
    vw_now = I.last(vw1)
    a5 = I.atr(b5m, c["atr_n"]) if len(b5m) else None
    atr5 = I.last(a5) if a5 is not None else None
    adx, pdi, mdi = I.adx_di(b5m, c["adx_n"]) if len(b5m) else (None, None, None)
    mc = c["macd"]
    M, S, H = I.macd(b2m["Close"], mc["fast"], mc["slow"], mc["signal"])
    prof = I.volume_profile(r1, c["profile"]["bin"], c["profile"]["value_area"])
    lv = levels(m1, r1, prof, vw_now)
    zone = max(c["zone"]["ticks"] * c["zone"]["tick"], c["zone"]["atr_frac"] * (atr5 or 0))
    buf = max(c["stop_buffer"]["ticks"] * c["zone"]["tick"], c["stop_buffer"]["atr_frac"] * (atr5 or 0))
    q = marketdata.quote(ticker)
    px = (q or {}).get("last") or float(r1["Close"].iloc[-1])
    snap.update(ok=True, t=t, last_open=last_open, m1=m1, r1=r1, b5=b5, b5m=b5m, b2=b2, b2m=b2m, vwap1=vw1, vwap=vw_now,
                atr5=atr5, adx=I.last(adx) if adx is not None else None, pdi=I.last(pdi) if pdi is not None else None,
                mdi=I.last(mdi) if mdi is not None else None, macd=M, signal=S, hist=H, profile=prof, levels=lv,
                zone=round(zone, 4), buf=round(buf, 4), price=float(px), quote=q,
                close1=float(r1["Close"].iloc[-1]))
    snap["regime"] = regime(snap)
    return snap


# ================================================================ levels (with origin and availability)
def levels(m1, r1, prof, vw_now=None):
    """Each level: value, source, the session it came from, and when it became known. Never uses future data."""
    out = {}
    if m1 is None or not len(m1):
        return out
    today = m1.index[-1].date()
    prior = [d for d in I.sessions(m1) if d < today]
    for d in reversed(prior):
        pr = I.rth(m1, d)
        if pr is not None and len(pr) >= 300:      # a (nearly) complete prior regular session
            out["PDH"] = {"value": round(float(pr["High"].max()), 2), "source": f"prior RTH high {d}", "complete": True}
            out["PDL"] = {"value": round(float(pr["Low"].min()), 2), "source": f"prior RTH low {d}", "complete": True}
            out["PDC"] = {"value": round(float(pr["Close"].iloc[-1]), 2), "source": f"prior RTH close {d}", "complete": True}
            break
    pre = m1[(m1.index.date == today)].between_time("04:00", "09:29")
    if len(pre):
        done = r1 is not None and len(r1) > 0
        out["PMH"] = {"value": round(float(pre["High"].max()), 2), "source": "premarket high 04:00-09:29", "complete": done}
        out["PML"] = {"value": round(float(pre["Low"].min()), 2), "source": "premarket low 04:00-09:29", "complete": done}
    if r1 is not None and len(r1):
        s = core.policy()["session"]
        ob = r1.between_time(s["orb_start"], (datetime.strptime(s["orb_end"], "%H:%M") - pd.Timedelta(minutes=1)).strftime("%H:%M"))
        if len(ob):
            complete = r1.index[-1].strftime("%H:%M") >= (datetime.strptime(s["orb_end"], "%H:%M") - pd.Timedelta(minutes=1)).strftime("%H:%M")
            src = f"opening range {s['orb_start']}-{s['orb_end']}" + ("" if complete else " (DEVELOPING)")
            out["ORB_H"] = {"value": round(float(ob["High"].max()), 2), "source": src, "complete": complete}
            out["ORB_L"] = {"value": round(float(ob["Low"].min()), 2), "source": src, "complete": complete}
        if vw_now is not None:
            out["VWAP"] = {"value": round(vw_now, 2), "source": "session VWAP (bar-based HLC3)", "complete": False}
    if prof:
        for k in ("poc", "vah", "val"):
            out[k.upper()] = {"value": prof[k], "source": f"developing volume profile {k.upper()} (APPROXIMATE, bin {prof['bin']})",
                              "complete": False}
    return out


def lv(snap, name):
    x = snap.get("levels", {}).get(name)
    return x["value"] if x else None


# ================================================================ regime (observable, timestamped)
def regime(snap):
    c = cfg()["regime"]
    b5, r1 = snap["b5"], snap["r1"]
    ev = {"t": snap["t"].isoformat(), "adx": snap.get("adx"), "+di": _r(snap.get("pdi")), "-di": _r(snap.get("mdi"))}
    lb = min(c["eff_lookback"], len(b5) - 1)
    eff = I.efficiency(b5["Close"], lb) if lb >= 3 else None
    cross = I.vwap_crossings(r1["Close"], snap["vwap1"], 60, snap["zone"])
    ov = I.overlap_ratio(b5, 8)
    rr = None
    if len(b5) >= 4 and snap.get("atr5"):
        rr = round(float(((b5["High"] - b5["Low"]).iloc[-3:]).mean()) / snap["atr5"], 2)
    ev.update(efficiency=eff, vwap_crossings_60m=cross, overlap=ov, range_atr_3bars=rr)
    ev["event"] = event_state()
    oh, ol, atr5 = lv(snap, "ORB_H"), lv(snap, "ORB_L"), snap.get("atr5")
    acc_up = acc_dn = False
    if oh is not None and atr5 and len(b5) >= c["accept_bars"]:
        last_n = b5["Close"].iloc[-c["accept_bars"]:]
        acc_up = bool((last_n > oh + c["accept_atr"] * atr5).all())
        acc_dn = bool((last_n < ol - c["accept_atr"] * atr5).all())
    ev.update(accepted_above_orb=acc_up, accepted_below_orb=acc_dn)
    if len(b5) < 3 or snap.get("adx") is None:
        return {"label": "insufficient data", "evidence": ev}
    if ev["event"]["state"] in ("released", "shock") and rr is not None and rr >= 2:
        return {"label": "event-driven", "evidence": ev}
    if rr is not None and rr >= c["vol_expansion_range_atr"] and eff < 0.35:
        return {"label": "volatility expansion (whipsaw)", "evidence": ev}
    pdi, mdi, adx = snap.get("pdi") or 0, snap.get("mdi") or 0, snap["adx"]
    if eff is None:
        return {"label": "mixed (no clear trend)", "evidence": ev}
    if adx >= c["adx_trend"] and eff >= c["eff_trend"] and (cross or 0) <= c["vwap_cross_max"]:
        if pdi > mdi and acc_up:
            return {"label": "trend up", "evidence": ev}
        if mdi > pdi and acc_dn:
            return {"label": "trend down", "evidence": ev}
    if adx < c["adx_chop"] or eff < c["eff_chop"] or (cross or 0) > c["vwap_cross_max"] or (ov or 0) > 0.6:
        return {"label": "range/chop", "evidence": ev}
    return {"label": "mixed (no clear trend)", "evidence": ev}


def _r(v):
    return None if v is None else round(v, 1)


def _vw(snap, ts):
    """Session VWAP as of the 1m bar that opened at or before ts (from the precomputed series)."""
    v = snap["vwap1"]
    w = v[v.index <= ts]
    return float(w.iloc[-1]) if len(w) and w.iloc[-1] == w.iloc[-1] else None


def event_state():
    """Scheduled events from config/events.json (9 AM routine) and Chart's timestamped headlines.
    States: none / pre-event (inside the block window) / released (within 30 min after) / unknown (no calendar)."""
    f = core.EVENTS_FILE
    now = core.now_et()
    try:
        evs = json.loads(f.read_text())
    except Exception:
        return {"state": "unknown", "why": "no event calendar for today"}
    if evs.get("date") != now.strftime("%Y-%m-%d"):
        return {"state": "unknown", "why": "event calendar is not for today"}
    m = core.policy()["discipline"]["event_block_min"]
    for e in evs.get("events", []):
        t = datetime.combine(now.date(), datetime.strptime(e["time"], "%H:%M").time(), core.ET)
        dt = (now - t).total_seconds() / 60
        if -m <= dt < 0:
            return {"state": "pre-event", "event": e, "minutes": round(-dt)}
        if 0 <= dt <= m:
            return {"state": "shock", "event": e, "minutes": round(dt)}
        if m < dt <= 30:
            return {"state": "released", "event": e, "minutes": round(dt)}
    return {"state": "none"}


# ================================================================ detectors
def _cand(snap, fam, side, tf, bar_ts, level_name, level, inv, rule, ev, kind, entry_mode=None):
    return {"family": fam, "side": side, "tf": tf, "bar": bar_ts.isoformat(), "level_name": level_name,
            "level": round(level, 2) if level is not None else None, "invalidation": round(inv, 2),
            "confirm_rule": rule, "evidence": ev, "kind": kind, "entry_mode": entry_mode,
            "decision_t": snap["t"].isoformat()}


def _new_bar(snap, b):
    """True only on the moment the newest bar of this timeframe completed (so each bar is judged once)."""
    return len(b) and b.index[-1] + pd.Timedelta(minutes=_tf(b)) == snap["t"]


def _tf(b):
    if len(b) < 2:
        return 5
    return int((b.index[-1] - b.index[-2]).total_seconds() // 60) or 5


def detect_all(snap):
    if not snap.get("ok"):
        return []
    out = []
    out += detect_orb(snap)
    out += detect_prior_day(snap)
    out += detect_vwap_reclaim(snap)
    if cfg()["vwap_macd"]["enabled"]:
        out += detect_vwap_macd(snap)
    return out


def detect_orb(snap):
    """ORB break (momentum family), ORB retest (valid break -> touch of the zone -> confirming close), failed break."""
    b5, z, buf = snap["b5"], snap["zone"], snap["buf"]
    oh, ol = lv(snap, "ORB_H"), lv(snap, "ORB_L")
    orb = snap["levels"].get("ORB_H")
    if not _new_bar(snap, b5) or oh is None or not orb["complete"] or len(b5) < 4:
        return []
    s = core.policy()["session"]
    after = b5[b5.index >= pd.Timestamp(f"{b5.index[-1].date()} {s['orb_end']}", tz=core.ET)]
    if len(after) < 1:
        return []
    last, prev = b5.iloc[-1], b5.iloc[-2]
    t = b5.index[-1]
    body = abs(last["Close"] - last["Open"]) / max(last["High"] - last["Low"], 1e-9)
    rv, n_rv = I.rvol_at_time(snap["m1"], t, 5, cfg()["rvol"]["lookback_sessions"], cfg()["rvol"]["min_sessions"])
    ev_base = {"orb_h": oh, "orb_l": ol, "zone": z, "close": round(float(last["Close"]), 2), "body_frac": round(body, 2),
               "rvol_5m_at_time": rv, "rvol_sessions": n_rv}
    out = []
    hist = after.iloc[:-1]
    broke_up_bars = hist[hist["Close"] > oh + z]
    broke_dn_bars = hist[hist["Close"] < ol - z]
    # momentum breakout: first acceptance close beyond the zone
    if prev["Close"] <= oh + z < last["Close"] and body >= 0.5:
        out.append(_cand(snap, "ORB_BREAK", "C", 5, t, "ORB_H", oh, oh - z - buf, f"5m close above ORB high + zone ({oh + z:.2f})",
                         dict(ev_base), "breakout"))
    if prev["Close"] >= ol - z > last["Close"] and body >= 0.5:
        out.append(_cand(snap, "ORB_BREAK", "P", 5, t, "ORB_L", ol, ol + z + buf, f"5m close below ORB low - zone ({ol - z:.2f})",
                         dict(ev_base), "breakout"))
    # retest: valid earlier break, no close back inside since, this bar touched the zone and closed back in direction
    if len(broke_up_bars):
        since = hist[hist.index > broke_up_bars.index[0]]
        held = not (since["Close"] < oh - z).any()
        touched = oh - z <= last["Low"] <= oh + z
        if held and touched and last["Close"] > oh and last["Close"] > last["Open"]:
            ev = dict(ev_base, break_bar=broke_up_bars.index[0].strftime("%H:%M"), touch_low=round(float(last["Low"]), 2))
            out.append(_cand(snap, "ORB_RETEST", "C", 5, t, "ORB_H", oh, min(float(last["Low"]), oh - z) - buf,
                             "valid break, touch of the ORB-high zone, green 5m close above it", ev, "continuation"))
        # failed breakout: broke up, now a 5m close back below the high by more than the zone
        if prev["Close"] > oh - z and last["Close"] < oh - z and last["Close"] > ol:
            ext = float(after["High"].max())
            ev = dict(ev_base, break_bar=broke_up_bars.index[0].strftime("%H:%M"), extreme=round(ext, 2))
            out.append(_cand(snap, "FAILED_BREAK", "P", 5, t, "ORB_H", oh, ext + buf,
                             "break above ORB failed: 5m close back inside below the zone", ev, "reversal"))
    if len(broke_dn_bars):
        since = hist[hist.index > broke_dn_bars.index[0]]
        held = not (since["Close"] > ol + z).any()
        touched = ol - z <= last["High"] <= ol + z
        if held and touched and last["Close"] < ol and last["Close"] < last["Open"]:
            ev = dict(ev_base, break_bar=broke_dn_bars.index[0].strftime("%H:%M"), touch_high=round(float(last["High"]), 2))
            out.append(_cand(snap, "ORB_RETEST", "P", 5, t, "ORB_L", ol, max(float(last["High"]), ol + z) + buf,
                             "valid breakdown, touch of the ORB-low zone, red 5m close below it", ev, "continuation"))
        if prev["Close"] < ol + z and last["Close"] > ol + z and last["Close"] < oh:
            ext = float(after["Low"].min())
            ev = dict(ev_base, break_bar=broke_dn_bars.index[0].strftime("%H:%M"), extreme=round(ext, 2))
            out.append(_cand(snap, "FAILED_BREAK", "C", 5, t, "ORB_L", ol, ext - buf,
                             "break below ORB failed: 5m close back inside above the zone", ev, "reversal"))
    return out


def detect_prior_day(snap):
    """PDH/PDL retest: an earlier close beyond the level, then THIS bar actually touches the zone and closes back
    in the trend direction. A bar that never reaches the zone is not a retest."""
    b5, z, buf = snap["b5"], snap["zone"], snap["buf"]
    if not _new_bar(snap, b5) or len(b5) < 4:
        return []
    last = b5.iloc[-1]
    t = b5.index[-1]
    hist = b5.iloc[:-1]
    out = []
    pdh, pdl = lv(snap, "PDH"), lv(snap, "PDL")
    if pdh is not None:
        broke = hist[hist["Close"] > pdh + z]
        if len(broke) and not (hist[hist.index > broke.index[0]]["Close"] < pdh - z).any():
            touched = pdh - z <= last["Low"] <= pdh + z
            if touched and last["Close"] > pdh and last["Close"] > last["Open"]:
                out.append(_cand(snap, "PDH_RETEST", "C", 5, t, "PDH", pdh, min(float(last["Low"]), pdh - z) - buf,
                                 "earlier close above PDH, touch of the PDH zone, green 5m close above it",
                                 {"pdh": pdh, "zone": z, "touch_low": round(float(last["Low"]), 2), "break_bar": broke.index[0].strftime("%H:%M"),
                                  "source": snap["levels"]["PDH"]["source"]}, "continuation"))
    if pdl is not None:
        broke = hist[hist["Close"] < pdl - z]
        if len(broke) and not (hist[hist.index > broke.index[0]]["Close"] > pdl + z).any():
            touched = pdl - z <= last["High"] <= pdl + z
            if touched and last["Close"] < pdl and last["Close"] < last["Open"]:
                out.append(_cand(snap, "PDL_RETEST", "P", 5, t, "PDL", pdl, max(float(last["High"]), pdl + z) + buf,
                                 "earlier close below PDL, touch of the PDL zone, red 5m close below it",
                                 {"pdl": pdl, "zone": z, "touch_high": round(float(last["High"]), 2), "break_bar": broke.index[0].strftime("%H:%M"),
                                  "source": snap["levels"]["PDL"]["source"]}, "continuation"))
    return out


def detect_vwap_reclaim(snap):
    b5, z, buf, r1 = snap["b5"], snap["zone"], snap["buf"], snap["r1"]
    if not _new_bar(snap, b5) or len(b5) < 3 or snap.get("vwap") is None:
        return []
    last, prev = b5.iloc[-1], b5.iloc[-2]
    t = b5.index[-1]
    v_prev = _vw(snap, b5.index[-2] + pd.Timedelta(minutes=4))
    v_now = snap["vwap"]
    cross = snap["regime"]["evidence"].get("vwap_crossings_60m")
    out = []
    ev = {"vwap": round(v_now, 2), "vwap_prev": round(v_prev, 2) if v_prev else None, "crossings_60m": cross, "zone": z}
    if v_prev and prev["Close"] < v_prev - z and last["Close"] > v_now + z and (cross or 0) <= 2:
        out.append(_cand(snap, "VWAP_RECLAIM", "C", 5, t, "VWAP", v_now, min(float(last["Low"]), v_now - z) - buf,
                         "5m close back above VWAP + zone after closing below it", ev, "continuation"))
    if v_prev and prev["Close"] > v_prev + z and last["Close"] < v_now - z and (cross or 0) <= 2:
        out.append(_cand(snap, "VWAP_RECLAIM", "P", 5, t, "VWAP", v_now, max(float(last["High"]), v_now + z) + buf,
                         "5m close back below VWAP - zone after closing above it", ev, "continuation"))
    return out


# ---------------------------------------------------------------- VWAP + MACD (one strategy, two confirmations)
def detect_vwap_macd(snap):
    """ONE strategy on finalized 2m bars of the underlying.
    ARM   : the 2m bar closes beyond session VWAP (by > tol) AND MACD crosses its signal in the same direction
            (cross EVENT: M[t-1] <= S[t-1] and M[t] > S[t] for calls; mirrored for puts).
    ENTER : normally on a VWAP RETEST - a later 2m bar taps the VWAP zone and closes back beyond VWAP in the trade
            direction while MACD is still on the trade's side (cheaper premium).
            EARLY only when the trend is clearly strong at the arming bar (ADX >= min with DI aligned, histogram
            building for N bars, VWAP sloping the trade's way, N closes on the right side of VWAP): enter on the
            cross close itself.
    CANCEL: a 2m close back through VWAP by more than the zone, a MACD cross against the trade, or no retest
            within the window. One arming -> at most one entry (the idea ID is the arming bar).
    """
    b2, M, S, H, z, buf = snap["b2"], snap["macd"], snap["signal"], snap["hist"], snap["zone"], snap["buf"]
    vc = cfg()["vwap_macd"]
    if len(b2) < 3 or not len(M) or not _new_bar(snap, b2):
        return []
    t = b2.index[-1]
    tk = snap["ticker"]
    tol = vc["vwap_tol_ticks"] * cfg()["zone"]["tick"]
    r1 = snap["r1"]
    vw_bar = _vw(snap, t + pd.Timedelta(minutes=1))   # VWAP through the end of this 2m bar
    if vw_bar is None:
        return []
    close, low, high, opn = (float(b2["Close"].iloc[-1]), float(b2["Low"].iloc[-1]), float(b2["High"].iloc[-1]),
                             float(b2["Open"].iloc[-1]))
    cross = I.macd_cross(M, S)
    state = I.macd_state(M, S)
    out = []
    key = f"vwmacd:{tk}:{t.date()}"
    done = store.kv_get(f"{key}:last") or {}
    if done.get("t") == t.isoformat():   # this bar was already processed (plan request, retry): same answer, no state change
        return done.get("out", [])
    armed = store.kv_get(key) or {}
    # cancel / expire existing arming
    for side in list(armed):
        a = armed[side]
        up = side == "C"
        why = None
        if (close < vw_bar - z) if up else (close > vw_bar + z):
            why = "2m close back through VWAP"
        elif cross == ("down" if up else "up"):
            why = "MACD crossed against the trade"
        elif a["bars_left"] <= 0:
            why = f"no VWAP retest within {vc['retest_window_bars']} bars"
        if why:
            store.event("research", f"VWAP+MACD {tk} {'calls' if up else 'puts'} armed at {a['armed_at'][11:16]} cancelled: {why}", "research", a["idea"])
            del armed[side]
        else:
            a["bars_left"] -= 1
    # new arming on a cross event beyond VWAP
    for side, want in (("C", "up"), ("P", "down")):
        up = side == "C"
        if cross == want and ((close > vw_bar + tol) if up else (close < vw_bar - tol)):
            ev = _vm_evidence(snap, side, vw_bar, close)
            strong = ev["strong_trend"]
            idea = f"{t.date()}-{tk}-VWAP_MACD-{side}-{t.strftime('%H%M')}"
            # always arm: if the early entry is skipped (extended, no room...), the VWAP retest can still enter.
            # Both share one idea ID, so at most ONE trade comes from this arming.
            armed[side] = {"armed_at": t.isoformat(), "bars_left": vc["retest_window_bars"], "idea": idea, "evidence": ev}
            if strong:
                inv = (min(low, vw_bar - z) - buf) if up else (max(high, vw_bar + z) + buf)
                out.append(_cand(snap, "VWAP_MACD", side, 2, t, "VWAP", vw_bar, inv,
                                 "MACD cross with the 2m close beyond VWAP; strong trend -> early entry on the cross close",
                                 ev, "continuation", entry_mode="early: strong trend"))
                out[-1]["idea_hint"] = idea
            store.event("research", f"VWAP+MACD {tk} {'calls' if up else 'puts'} ARMED at {t.strftime('%H:%M')}: "
                        + ("strong trend, early entry offered; " if strong else "trend not strong enough for early entry; ")
                        + f"VWAP retest window {vc['retest_window_bars']} bars", "research", idea)
    # retest entry for an armed side (not on the arming bar itself)
    for side, a in list(armed.items()):
        if a["armed_at"] == t.isoformat():
            continue
        up = side == "C"
        tapped = (low <= vw_bar + z) if up else (high >= vw_bar - z)
        confirmed = (close > vw_bar + tol and close > opn) if up else (close < vw_bar - tol and close < opn)
        mom_ok = state == ("bull" if up else "bear")
        if tapped and confirmed and mom_ok:
            ev = dict(a["evidence"], retest_bar=t.strftime("%H:%M"), retest_low=round(low, 2), retest_high=round(high, 2),
                      vwap_at_retest=round(vw_bar, 2))
            inv = (min(low, vw_bar - z) - buf) if up else (max(high, vw_bar + z) + buf)
            out.append(_cand(snap, "VWAP_MACD", side, 2, t, "VWAP", vw_bar, inv,
                             "armed by a MACD cross beyond VWAP, then a tap of the VWAP zone and a confirming 2m close",
                             ev, "continuation", entry_mode="VWAP retest"))
            out[-1]["idea_hint"] = a["idea"]
            del armed[side]
    store.kv_set(key, armed)
    store.kv_set(f"{key}:last", {"t": t.isoformat(), "out": out})
    return out


def _vm_evidence(snap, side, vw_bar, close):
    vc = cfg()["vwap_macd"]
    ee = vc["early_entry"]
    up = side == "C"
    H, r1, b2 = snap["hist"], snap["r1"], snap["b2"]
    vws = snap["vwap1"]
    slope_ok = None
    if len(vws) > ee["vwap_slope_bars"] * 2:
        old = float(vws.iloc[-1 - ee["vwap_slope_bars"] * 2])
        slope_ok = (vws.iloc[-1] > old) if up else (vws.iloc[-1] < old)
    acc = None
    if len(b2) >= ee["accept_bars"]:
        vb = [_vw(snap, i + pd.Timedelta(minutes=1)) for i in b2.index[-ee["accept_bars"]:]]
        cl = b2["Close"].iloc[-ee["accept_bars"]:].values
        acc = all(v is not None and ((c > v) if up else (c < v)) for c, v in zip(cl, vb))
    adx, pdi, mdi = snap.get("adx"), snap.get("pdi"), snap.get("mdi")
    di_ok = adx is not None and adx >= ee["adx_min"] and ((pdi or 0) > (mdi or 0) if up else (mdi or 0) > (pdi or 0))
    hr = I.hist_rising(H, side, ee["hist_rising_changes"])
    strong = bool(di_ok and hr and slope_ok and acc)
    ev = {"vwap": round(vw_bar, 2), "close": round(close, 2), "macd": _r4(I.last(snap["macd"])), "signal": _r4(I.last(snap["signal"])),
          "hist": _r4(I.last(H)), "adx_5m": adx, "di_aligned": bool(di_ok), "hist_building": hr, "vwap_slope_ok": slope_ok,
          "accepted_beyond_vwap": acc, "strong_trend": strong,
          "macd_settings": f"{cfg()['macd']['fast']}/{cfg()['macd']['slow']}/{cfg()['macd']['signal']} on 2m"}
    # research-only optional filters: logged, never applied in main
    of = vc.get("optional_filters", {})
    m = I.last(snap["macd"])
    ev["filters"] = {"macd_zero_line": (m > 0 if up else m < 0) if m is not None else None,
                     "enabled_in_main": [k for k, v in of.items() if v and k != "note"]}
    return ev


def _r4(v):
    return None if v is None else round(v, 4)


# ================================================================ arbitration and qualification
def arbitrate(cands):
    """Returns (ideas, skipped). Same-side candidates merge into one idea with supporting tags. If calls AND
    puts both fire on this decision moment, the main strategy skips the bar (both recorded for research)."""
    if not cands:
        return [], None
    sides = {c["side"] for c in cands}
    if len(sides) > 1:
        return [], {"reason": "calls and puts both fired on the same bar: skipped (no direction pick)",
                    "candidates": [f"{c['family']} {c['side']}" for c in cands]}
    side = sides.pop()
    cands = sorted(cands, key=lambda c: PRIORITY.index(c["family"]) if c["family"] in PRIORITY else 99)
    primary = dict(cands[0])
    primary["tags"] = [c["family"] for c in cands]
    primary["supporting"] = [{"family": c["family"], "rule": c["confirm_rule"]} for c in cands[1:]]
    # structural invalidation: the tightest level that actually disproves the idea is the primary's
    return [primary], None


def qualify(idea, snap):
    """Entry filters with plain reasons. Returns (passed, objections, support)."""
    c = cfg()
    side, fam = idea["side"], idea["family"]
    up = side == "C"
    obj, sup = [], []
    meta = snap.get("meta", {})
    if not meta.get("executable", False):
        obj.append(f"data not executable ({meta.get('provider', '?')}): no simulated fills")
    if meta.get("bar_age_s") is not None and meta["bar_age_s"] > core.policy()["data"]["max_bar_age_s"]:
        obj.append(f"bars stale ({meta['bar_age_s']:.0f}s)")
    recent_gaps = [g for g in meta.get("gaps_rth_today", []) if g >= (snap["t"] - pd.Timedelta(minutes=15)).strftime("%H:%M")]
    if recent_gaps:
        obj.append(f"missing minutes in the last 15 min: {', '.join(recent_gaps[:3])}")
    # momentum on finalized 2m bars
    H, M, S = snap["hist"], snap["macd"], snap["signal"]
    st = I.macd_state(M, S)
    fading = I.hist_fading(H, side)
    if fam in CONTINUATION:
        if st is None:
            obj.append("MACD warming up (not enough 2m history)")
        elif st == ("bear" if up else "bull"):
            obj.append(f"MACD on the wrong side ({st}) for {'calls' if up else 'puts'}")
        if fading:
            obj.append("MACD histogram fading for 3 straight 2m bars")
    elif fam in REVERSAL:
        turning = I.hist_rising(H, side, 2)
        if not turning and I.macd_cross(M, S) != ("up" if up else "down"):
            obj.append("reversal without momentum turning the new way (histogram not building, no cross)")
        else:
            sup.append("momentum turning for the reversal")
    # rejected spike above value (calls) / below value (puts, mirrored)
    rs = rejected_spike(snap, side)
    if rs:
        obj.append(rs)
    # extension
    atr5 = snap.get("atr5")
    if atr5 and idea.get("level") is not None and fam not in REVERSAL:
        ext = (snap["close1"] - idea["level"]) / atr5 if up else (idea["level"] - snap["close1"]) / atr5
        if ext > c["extension_max_atr"]:
            obj.append(f"extended: {ext:.1f} ATR past {idea['level_name']} (max {c['extension_max_atr']})")
    # regime
    rg = snap["regime"]
    lab = rg["label"]
    if lab == "insufficient data":
        obj.append("regime: not enough data yet")
    elif lab in ("range/chop", "volatility expansion (whipsaw)") and fam in ("ORB_BREAK", "VWAP_RECLAIM"):
        obj.append(f"regime {lab}: no continuation breakouts")
    elif lab.startswith("trend"):
        (sup if (lab == "trend up") == up else obj).append(f"regime {lab}")
    ev = rg["evidence"]["event"]
    if ev["state"] in ("pre-event", "shock"):
        obj.append(f"event: {ev['event']['name']} at {ev['event']['time']} ({ev['state']})")
    # afternoon: cleaner structure required
    af = c["afternoon"]
    if snap["t"].strftime("%H:%M") >= af["start"]:
        e = rg["evidence"]
        if e.get("efficiency") is not None and e["efficiency"] < af["eff_min"]:
            obj.append(f"afternoon: price action inefficient ({e['efficiency']} < {af['eff_min']})")
        if (e.get("vwap_crossings_60m") or 0) > af["vwap_cross_max"]:
            obj.append(f"afternoon: repeated VWAP crossings ({e['vwap_crossings_60m']} in 60 min)")
        if (e.get("overlap") or 0) > af["overlap_max"]:
            obj.append(f"afternoon: overlapping candles ({e['overlap']})")
        rv = idea["evidence"].get("rvol_5m_at_time")
        if rv is not None and rv < af["rvol_min"]:
            obj.append(f"afternoon: light participation (RVOL {rv})")
    rv = idea["evidence"].get("rvol_5m_at_time")
    if fam == "ORB_BREAK":
        if rv is None:
            sup.append("RVOL at time unavailable (not enough matching history)")
        elif rv < c["rvol"]["min_for_breakout"]:
            obj.append(f"breakout on light volume (RVOL {rv} vs same time on prior days)")
        else:
            sup.append(f"RVOL {rv} at time")
    # VWAP side
    vw = snap.get("vwap")
    if vw is not None and fam in CONTINUATION:
        (sup if ((snap["close1"] > vw) == up) else obj).append(f"{'above' if snap['close1'] > vw else 'below'} VWAP {vw:.2f}")
    elif vw is not None:
        sup.append(f"reversal from {'below' if snap['close1'] < vw else 'above'} VWAP {vw:.2f} (VWAP side not required)")
    return (not obj), obj, sup


def rejected_spike(snap, side):
    """Contextual filter: block continuation CALLS while price is above the developing value area after a confirmed
    rejected upward spike, until acceptance (N 5m closes above the spike high). Mirrored for puts below value."""
    rc = cfg()["rejected_spike"]
    if not rc["enabled"] or (side == "P" and not rc.get("mirror_puts")):
        return None
    r1, b5 = snap["r1"], snap["b5"]
    prof = snap.get("profile")
    if not prof or len(r1) < 30:
        return None
    up = side == "C"
    t0 = snap["t"] - pd.Timedelta(minutes=rc["lookback_min"])
    w = r1[r1.index >= t0]
    med = float(r1["Volume"].iloc[:-1].median()) if len(r1) > 1 else 0
    for ts, b in w.iterrows():
        rng = b["High"] - b["Low"]
        if rng <= 0 or med <= 0:
            continue
        if up:
            wick = (b["High"] - max(b["Open"], b["Close"])) / rng
            beyond = b["High"] > prof["vah"] and b["Close"] < b["High"] - 0.5 * rng
        else:
            wick = (min(b["Open"], b["Close"]) - b["Low"]) / rng
            beyond = b["Low"] < prof["val"] and b["Close"] > b["Low"] + 0.5 * rng
        if beyond and wick >= rc["wick_frac"] and b["Volume"] >= rc["vol_mult"] * med:
            extreme = b["High"] if up else b["Low"]
            later = b5[b5.index > ts]["Close"].iloc[-rc["accept_closes"]:]
            accepted = len(later) >= rc["accept_closes"] and ((later > extreme).all() if up else (later < extreme).all())
            px = snap["close1"]
            if not accepted and ((px > prof["vah"]) if up else (px < prof["val"])):
                return (f"rejected {'up' if up else 'down'}side spike at {ts.strftime('%H:%M')} ({extreme:.2f}, "
                        f"{b['Volume'] / med:.1f}x median volume) and price still {'above value VAH' if up else 'below value VAL'} "
                        f"{prof['vah'] if up else prof['val']:.2f} without acceptance (approximate profile)")
    return None


def grade(idea, snap, plan_rr=None):
    """Rules-based label: A = every quality check passes, B = all required checks pass, else C. Evidence listed."""
    up = idea["side"] == "C"
    checks = {
        "regime agrees": snap["regime"]["label"] == ("trend up" if up else "trend down"),
        "VWAP side agrees": snap.get("vwap") is not None and ((snap["close1"] > snap["vwap"]) == up),
        "MACD on the trade's side": I.macd_state(snap["macd"], snap["signal"]) == ("bull" if up else "bear"),
        "room to T1 >= 2.5R": plan_rr is not None and plan_rr >= 2.5,
    }
    rv = idea["evidence"].get("rvol_5m_at_time")
    if rv is not None:
        checks["RVOL >= 1.2 at time"] = rv >= 1.2
    passed = [k for k, v in checks.items() if v]
    failed = [k for k, v in checks.items() if not v]
    g = "A" if not failed else "B" if len(failed) <= 2 else "C"
    return g, passed, failed
