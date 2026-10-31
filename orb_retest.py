"""orb_retest.py - v3.5 (new): Nick's corrected ORB as ONE pure, versioned state machine (strategy ORBX-15-5).

    opening range forms -> a candle CLOSES beyond the boundary (B) -> a LATER, separate completed candle sits ENTIRELY
    beyond the boundary, wick included (C) -> a LATER candle touches the retest zone and CLOSES back on the breakout
    side (R) -> entry at the next executable quote after R closes -> trail.

Three distinct, ordered completed decision candles: B.close_time < C.close_time < R.close_time. No candle fills two
stages. Bullish C needs C.low > OR.high (strict, plus clear_ticks); bearish C needs C.high < OR.low. The old
detect_orb (strategy.py, ORB_BREAK on the first acceptance close) is FROZEN and unchanged; this is a new strategy id.

The same function runs live (engine), in the lab tape and in the historical study, so the three can't disagree.
Inputs are completed candles only; a candle is a decision candle only when all of its 1-minute bars exist and its
close time has passed. The opening range freezes only when every one of its 1-minute bars is present.

PROVISIONAL parameters (fixed before any test on our data, NOT validated, NOT optimized):
  or_minutes 15, tf_min 5         the desk's existing core ORB timeframe (15-minute range, 5-minute candles)
  clear_ticks 1                   C must clear the boundary by at least one cent; equality never counts
  retest_tol: max(2 ticks, 0.10 x ATR5)   the zone is boundary +/- tol, frozen when C closes (a tenth of a typical
                                  5-minute range: a real touch, not "somewhere near")
  fail_wick: max(3 ticks, 0.30 x ATR5)    a retest wick deeper than this inside the range is a FAILED retest
  fail_close: a retest candle that closes back inside the range (at or through the boundary) is a FAILED retest
  confirm_timeout 6 candles (30 min) after B; retest_timeout 9 candles (45 min) after C
  last_entry 15:00 ET             no new ENTRY CONFIRMED after this (the desk flattens at 15:25)
  max_extension_atr 0.5           anti-chasing: the entry quote may sit at most 0.5 x ATR5 beyond the boundary
  stop: the retest candle's extreme (or the boundary, whichever is further) +/- 0.05 x ATR5; max 1.5 x ATR5 away
Reset policy: after a failed or expired episode, ONE new episode per side per day, and only after a candle closes back
inside the range and a NEW breakout candle follows. After an ENTRY CONFIRMED that side is done for the day. Episode
ids are deterministic (day|ticker|side|n), so polling or a restart can never create a second trade from one signal.
Gap rule: a first post-range candle that opens beyond the boundary and closes beyond it is the breakout (B) only,
flagged "gap"; it can never also be the confirmation.
"""
import json
from datetime import timedelta

import pandas as pd

import core

VERSION = "2026-10-31.orbx1"
STRATEGY_ID = "ORBX-15-5"
TICK = 0.01
DEFAULTS = {"or_minutes": 15, "tf_min": 5, "clear_ticks": 1, "tol_ticks": 2, "tol_atr": 0.10, "fail_ticks": 3, "fail_atr": 0.30,
            "confirm_timeout": 6, "retest_timeout": 9, "last_entry": "15:00", "max_resets": 1, "max_extension_atr": 0.5,
            "stop_buf_atr": 0.05, "max_stop_atr": 1.5, "latency_s": 1, "atr_n": 14}
STAGES = ("OPENING RANGE FORMING", "WAITING FOR BREAKOUT", "WAITING FOR INDEPENDENT CANDLE", "WAITING FOR RETEST",
          "ENTRY CONFIRMED", "POSITION OPEN", "INVALIDATED", "EXPIRED", "DONE FOR THE DAY", "NO RANGE (data missing)")


def cfg(over=None):
    c = dict(DEFAULTS)
    c.update((core.policy().get("orbx") or {}) if hasattr(core, "policy") else {})
    c.update(over or {})
    return c


def _rth(m1):
    mins = m1.index.hour * 60 + m1.index.minute
    return m1[(mins >= 570) & (mins <= 959)]


def opening_range(m1_day, c=None, now=None):
    """(OR dict, None) or (None, why). Every 1-minute bar of the range must exist and be complete."""
    c = c or cfg()
    if m1_day is None or not len(m1_day):
        return None, "no bars"
    d = m1_day.index[0].date()
    start = pd.Timestamp(f"{d} 09:30", tz=core.ET)
    end = start + pd.Timedelta(minutes=c["or_minutes"])
    if now is not None and pd.Timestamp(now) < end:
        return None, "forming"
    w = m1_day[(m1_day.index >= start) & (m1_day.index < end)]
    if len(w) < c["or_minutes"]:
        return None, f"missing {c['or_minutes'] - len(w)} of {c['or_minutes']} opening-range bars"
    hi, lo = float(w["High"].max()), float(w["Low"].min())
    return {"high": round(hi, 4), "low": round(lo, 4), "mid": round((hi + lo) / 2, 4), "start": start, "end": end,
            "width": round(hi - lo, 4)}, None


def candles(m1_day, c=None, now=None, after=None):
    """Completed tf-minute decision candles (RTH) with start/close times; a candle missing any 1m bar is skipped."""
    c = c or cfg()
    tf = c["tf_min"]
    m = _rth(m1_day)
    if not len(m):
        return []
    g = m.groupby(m.index.floor(f"{tf}min"))
    out = []
    for st, b in g:
        ct = st + pd.Timedelta(minutes=tf)
        if len(b) < tf or (now is not None and ct > pd.Timestamp(now)) or (after is not None and st < after):
            continue
        out.append({"start": st, "close_time": ct, "o": float(b["Open"].iloc[0]), "h": float(b["High"].max()),
                    "l": float(b["Low"].min()), "c": float(b["Close"].iloc[-1]), "v": float(b["Volume"].sum())})
    return out


def atr_by_close(prior, today, n=14):
    """Wilder ATR(n) of 5-minute candles known at each candle's close (prior sessions' candles warm it up)."""
    allc = list(prior or []) + list(today)
    out, atr, pc = {}, None, None
    trs = []
    for k in allc:
        tr = k["h"] - k["l"] if pc is None else max(k["h"] - k["l"], abs(k["h"] - pc), abs(k["l"] - pc))
        pc = k["c"]
        if atr is None:
            trs.append(tr)
            if len(trs) >= n:
                atr = sum(trs[-n:]) / n
        else:
            atr = (atr * (n - 1) + tr) / n
        out[k["close_time"]] = atr if atr is not None else (sum(trs) / len(trs) if trs else None)
    return out


def _k(k):
    return {"start": k["start"].isoformat(), "close_time": k["close_time"].isoformat(), "o": round(k["o"], 4), "h": round(k["h"], 4),
            "l": round(k["l"], 4), "c": round(k["c"], 4)}


def run(m1_day, ticker="?", c=None, now=None, prior_candles=None, sides=("C", "P")):
    """The whole day's machine from completed candles. Pure and deterministic: the same bars give the same episodes,
    and candles after `now` can't change anything before it. Returns {or, why, stage{side}, episodes[]}."""
    c = c or cfg()
    rng, why = opening_range(m1_day, c, now)
    day = str(m1_day.index[0].date()) if m1_day is not None and len(m1_day) else None
    if rng is None:
        st = "OPENING RANGE FORMING" if why == "forming" else "NO RANGE (data missing)"
        return {"or": None, "why": why, "stage": {s: st for s in sides}, "episodes": [], "version": VERSION, "day": day}
    ks = candles(m1_day, c, now, after=rng["end"])
    atr = atr_by_close(prior_candles, candles(m1_day, c, now), c["atr_n"])
    eps, stage = [], {}
    for side in sides:
        e, st = _run_side(ks, rng, atr, side, ticker, day, c)
        eps += e
        stage[side] = st
    return {"or": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in rng.items()}, "why": None, "stage": stage,
            "episodes": eps, "version": VERSION, "day": day, "candles": len(ks)}


def _run_side(ks, rng, atr, side, ticker, day, c):
    up = side == "C"
    H = rng["high"] if up else rng["low"]
    sgn = 1 if up else -1
    beyond = lambda px: (px - H) * sgn                      # >0 = on the breakout side
    eps = []
    state, ep, resets, need_inside, n = "WAITING FOR BREAKOUT", None, 0, False, 0
    last_entry = c["last_entry"]

    def close_ep(st, k, why):
        nonlocal state, ep, resets, need_inside
        ep["state"], ep["why"] = st, why
        ep["transitions"].append({"t": k["close_time"].isoformat(), "to": st, "why": why})
        eps.append(ep)
        ep = None
        if resets < c["max_resets"]:
            resets += 1
            state = "WAITING FOR BREAKOUT"
            need_inside = beyond(k["c"]) > 0               # the closing candle itself may already be back inside
        else:
            state = "DONE FOR THE DAY"

    for i, k in enumerate(ks):
        hm = k["close_time"].strftime("%H:%M")
        if state == "DONE FOR THE DAY" or state == "ENTRY CONFIRMED":
            break
        if hm > last_entry:
            if ep:
                close_ep("EXPIRED", k, f"no entry after {last_entry} ET")
            state = "DONE FOR THE DAY"
            break
        if state == "WAITING FOR BREAKOUT":
            if need_inside:
                if beyond(k["c"]) <= 0:
                    need_inside = False
                continue
            if beyond(k["c"]) > 0:
                n += 1
                ep = {"id": f"{day}|{ticker}|{side}|{n}", "strategy": STRATEGY_ID, "version": VERSION, "ticker": ticker, "side": side,
                      "day": day, "n": n, "or_high": rng["high"], "or_low": rng["low"], "boundary": H, "B": _k(k), "C": None, "R": None,
                      "gap": i == 0 and beyond(k["o"]) > 0, "transitions": [{"t": k["close_time"].isoformat(), "to": "WAITING FOR INDEPENDENT CANDLE",
                                                                            "why": f"{'gap ' if i == 0 and beyond(k['o']) > 0 else ''}breakout close {k['c']:.2f} beyond {H:.2f}"}],
                      "_bi": i}
                state = "WAITING FOR INDEPENDENT CANDLE"
            continue
        if state == "WAITING FOR INDEPENDENT CANDLE":
            if beyond(k["c"]) <= 0:
                close_ep("INVALIDATED", k, f"closed back inside the range ({k['c']:.2f}) before an independent candle")
                continue
            far = (k["l"] if up else k["h"])                    # the candle's NEAR extreme (wick included)
            if beyond(far) >= c["clear_ticks"] * TICK - 1e-9 and beyond(far) > 0:
                a = atr.get(k["close_time"]) or max(TICK, rng["width"] / 3)
                ep["C"] = _k(k)
                ep["atr"] = round(a, 4)
                ep["tol"] = round(max(c["tol_ticks"] * TICK, c["tol_atr"] * a), 4)
                ep["fail"] = round(max(c["fail_ticks"] * TICK, c["fail_atr"] * a), 4)
                ep["zone"] = [round(H - ep["tol"], 4), round(H + ep["tol"], 4)]
                ep["transitions"].append({"t": k["close_time"].isoformat(), "to": "WAITING FOR RETEST",
                                          "why": f"independent candle entirely {'above' if up else 'below'} {H:.2f} ({'low' if up else 'high'} {far:.2f})"})
                ep["_ci"] = i
                state = "WAITING FOR RETEST"
            elif i - ep["_bi"] >= c["confirm_timeout"]:
                close_ep("EXPIRED", k, f"no independent candle within {c['confirm_timeout']} candles of the breakout")
            continue
        if state == "WAITING FOR RETEST":
            near = k["l"] if up else k["h"]
            touched = beyond(near) <= ep["tol"]
            if touched:
                if beyond(near) < -ep["fail"]:
                    close_ep("INVALIDATED", k, f"failed retest: wick {near:.2f} went {abs(beyond(near)):.2f} back into the range (limit {ep['fail']:.2f})")
                elif beyond(k["c"]) <= 0:
                    close_ep("INVALIDATED", k, f"failed retest: closed back inside the range at {k['c']:.2f}")
                else:
                    a = ep["atr"]
                    ext = min(near, H) if up else max(near, H)
                    stop = ext - sgn * c["stop_buf_atr"] * a
                    ep.update(R=_k(k), state="ENTRY CONFIRMED", stop=round(stop, 4),
                              entry_after=(k["close_time"] + pd.Timedelta(seconds=c["latency_s"])).isoformat(),
                              max_entry=round(H + sgn * c["max_extension_atr"] * a, 4), max_stop_dist=round(c["max_stop_atr"] * a, 4))
                    ep["transitions"].append({"t": k["close_time"].isoformat(), "to": "ENTRY CONFIRMED",
                                              "why": f"retest touched {near:.2f} (zone {ep['zone'][0]:.2f}-{ep['zone'][1]:.2f}) and closed {k['c']:.2f} back {'above' if up else 'below'}"})
                    eps.append(ep)
                    ep = None
                    state = "ENTRY CONFIRMED"
            elif i - ep["_ci"] >= c["retest_timeout"]:
                close_ep("EXPIRED", k, f"no retest within {c['retest_timeout']} candles of the independent candle")
            continue
    if ep:                                                   # still in progress at `now`
        ep["state"] = state
        eps.append(ep)
    for e in eps:
        e.pop("_bi", None)
        e.pop("_ci", None)
    return eps, state


def entry_check(ep, quote_px, quote_t, c=None):
    """Fill-time checks for an ENTRY CONFIRMED episode: the quote must come after the retest candle closed (+latency),
    and price must still be inside the anti-chasing limit with a sane stop distance. Returns (ok, why)."""
    c = c or cfg()
    if ep.get("state") != "ENTRY CONFIRMED":
        return False, f"episode is {ep.get('state')}"
    if quote_t is None or pd.Timestamp(quote_t) < pd.Timestamp(ep["entry_after"]):
        return False, "no quote after the retest candle closed yet (never a backfilled entry)"
    up = ep["side"] == "C"
    if (quote_px > ep["max_entry"]) if up else (quote_px < ep["max_entry"]):
        return False, f"too extended: {quote_px:.2f} is past the anti-chasing limit {ep['max_entry']:.2f}"
    dist = (quote_px - ep["stop"]) if up else (ep["stop"] - quote_px)
    if dist <= 0:
        return False, "price is already through the stop"
    if dist > ep["max_stop_dist"]:
        return False, f"stop {dist:.2f} away is more than {c['max_stop_atr']} x ATR5"
    return True, None


# ---------------------------------------------------------------- exits on the underlying (study + paper variants)
TRAILS = ("swing", "atr", "fixed2r", "ormid1r", "hold")


def trail_exit(m1_day, entry_i, ep, method, c=None, flat="15:25", cost_per_share=0.04):
    """Underlying-only exit for one entry. All methods trail in the protective direction only, check the stop on
    every 1m bar's high/low (a protective stop never waits for a close), take the gap open when a bar opens through
    it, and are flat at `flat`. R = the INITIAL stop distance. A bar touching stop and target counts as the stop.
      swing   after +1R, stop -> the far extreme of the last 2 COMPLETED 5m candles (bull: their lowest low)
      atr     after +1R, stop -> highest close since entry - 2 x ATR5 (bull)
      fixed2r the desk's shared yardstick: initial stop, 2R target
      ormid1r day-trader-skill's plan: stop at the opening-range midpoint, 1R target (R = that distance)
      hold    initial stop only, flat at the cutoff"""
    c = c or cfg()
    up = ep["side"] == "C"
    sgn = 1 if up else -1
    o, h, l, cl = (m1_day[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    idx = m1_day.index
    if entry_i is None or entry_i >= len(m1_day):
        return None
    e = float(o[entry_i])
    stop = float(ep["stop"])
    if method == "ormid1r":
        stop = (ep["or_high"] + ep["or_low"]) / 2
    sd = (e - stop) * sgn
    if sd <= 0:
        return None
    tgt = e + sgn * (2 if method == "fixed2r" else 1) * sd if method in ("fixed2r", "ormid1r") else None
    a = float(ep.get("atr") or sd)
    fm = int(flat[:2]) * 60 + int(flat[3:5])
    best = e
    cr = cost_per_share / sd
    armed = False
    for j in range(entry_i, len(m1_day)):
        t = idx[j]
        if t.hour * 60 + t.minute >= fm:
            return {"r": round((float(o[j]) - e) * sgn / sd - cr, 4), "why": "flat", "exit_i": j, "sd": sd}
        if j > entry_i and (float(o[j]) - stop) * sgn <= 0:
            return {"r": round((float(o[j]) - e) * sgn / sd - cr, 4), "why": "stop gap" if not armed else "trail gap", "exit_i": j, "sd": sd}
        hit_s = ((l[j] if up else h[j]) - stop) * sgn <= 0
        hit_t = tgt is not None and ((h[j] if up else l[j]) - tgt) * sgn >= 0
        if hit_s:
            return {"r": round((stop - e) * sgn / sd - cr, 4), "why": "trail" if armed else "stop", "exit_i": j, "sd": sd}
        if hit_t:
            return {"r": round((tgt - e) * sgn / sd - cr, 4), "why": "target", "exit_i": j, "sd": sd}
        best = max(best, float(cl[j])) if up else min(best, float(cl[j]))
        if method in ("swing", "atr") and (best - e) * sgn >= sd:
            armed = True
        if armed and method == "atr":
            new = best - sgn * 2.0 * a
            stop = max(stop, new) if up else min(stop, new)
        if armed and method == "swing" and (t.minute + 1) % 5 == 0:       # a 5m candle just completed
            st5 = t.floor("5min")
            prev = m1_day[(m1_day.index >= st5 - pd.Timedelta(minutes=5)) & (m1_day.index <= t)]
            if len(prev):
                new = float(prev["Low"].min()) if up else float(prev["High"].max())
                stop = max(stop, new) if up else min(stop, new)
    return None


def entry_index(m1_day, ep):
    """Bars-only proxy for the next executable quote: the open of the first 1m bar starting at the retest candle's
    close (the lab's next-bar-open convention). Live entries use a real quote dated after R closed + latency."""
    pos = m1_day.index.searchsorted(pd.Timestamp(ep["R"]["close_time"]))
    return int(pos) if pos < len(m1_day) else None


# ---------------------------------------------------------------- persistence (episode identity survives restarts)
SCHEMA = ("CREATE TABLE IF NOT EXISTS orbx_episodes(id TEXT PRIMARY KEY, day TEXT, ticker TEXT, side TEXT, n INTEGER, state TEXT, "
          "data TEXT, version TEXT, updated TEXT)")


def save(result):
    """Upsert every episode by its deterministic id. A stored ENTRY CONFIRMED / terminal episode is never downgraded."""
    import store
    store.x(SCHEMA)
    out = []
    with store.tx():
        for e in result["episodes"]:
            old = store.q("SELECT state, data FROM orbx_episodes WHERE id=?", (e["id"],))
            if old and old[0]["state"] in ("ENTRY CONFIRMED", "POSITION OPEN", "INVALIDATED", "EXPIRED"):
                out.append(json.loads(old[0]["data"]))
                continue
            store.x("INSERT OR REPLACE INTO orbx_episodes(id, day, ticker, side, n, state, data, version, updated) VALUES(?,?,?,?,?,?,?,?,?)",
                    (e["id"], e["day"], e["ticker"], e["side"], e["n"], e["state"], json.dumps(e, default=str), VERSION, store.ts()))
            out.append(e)
    return out


def mark_open(ep_id, pid):
    import store
    store.x(SCHEMA)
    r = store.q("SELECT data FROM orbx_episodes WHERE id=?", (ep_id,))
    if r:
        d = json.loads(r[0]["data"])
        d.update(state="POSITION OPEN", position_id=pid)
        store.x("UPDATE orbx_episodes SET state='POSITION OPEN', data=?, updated=? WHERE id=?", (json.dumps(d, default=str), store.ts(), ep_id))


def today(day=None):
    import store
    store.x(SCHEMA)
    day = day or core.now_et().strftime("%Y-%m-%d")
    return [json.loads(r["data"]) for r in store.q("SELECT data FROM orbx_episodes WHERE day=? ORDER BY ticker, side, n", (day,))]


# ---------------------------------------------------------------- live paper ledgers (SPY/QQQ only; research, strict costs)
LEDGERS = {"orbx_swing": "swing", "orbx_atr": "atr", "orbx_2r": "fixed2r", "orbx_ormid": "ormid1r"}
_live_cache = {}


_prior_cache = {}


def _today_m1(s, now):
    """Today's finished 1m bars, and the two prior sessions' 5m candles (cached per ticker and day)."""
    import store
    m1 = s.get("m1")
    if m1 is None or not len(m1):
        return None, []
    now = pd.Timestamp(now)
    start = now.normalize()
    today = m1[(m1.index >= start) & (m1.index + pd.Timedelta(minutes=1) <= now)]     # finished 1m bars only
    key = (str(store.DB), s.get("ticker") or id(m1), str(start.date()))
    if key not in _prior_cache:
        old = m1[m1.index < start]
        days = pd.Index(old.index.normalize()).unique()[-2:]
        prior = []
        for d0 in days:
            prior += candles(old[(old.index >= d0) & (old.index < d0 + pd.Timedelta(days=1))])
        if len(_prior_cache) > 50:
            _prior_cache.clear()
        _prior_cache[key] = prior
    return today, _prior_cache[key]


def _record(ep, decision, why, extra=None):
    try:
        import learning
        learning.record_decision("orbx", ep["ticker"], ep["side"], STRATEGY_ID, VERSION, decision, [why] if why else [],
                                 opportunity=ep["id"], snapshot={"episode": {k: ep.get(k) for k in ("B", "C", "R", "zone", "tol", "stop",
                                                                                                      "max_entry", "boundary", "or_high", "or_low", "state")},
                                                                 **(extra or {})})
    except Exception:
        pass


def live_step(ticker, s, now, fetch_chain=None):
    """Run the machine on today's finished bars, persist episodes, and act once on a NEW entry confirmation:
    fill-time checks (quote after R + latency, anti-chasing, session, stop distance), one contract, one paper buy in
    each exit-variant ledger. Returns what happened (for the engine log)."""
    import paper
    import store
    m1 = s.get("m1")
    if m1 is None or not len(m1):
        return None
    fin = m1.index[m1.index + pd.Timedelta(minutes=1) <= pd.Timestamp(now)]
    last = (str(store.DB), str(pd.Timestamp(now).date()), str(fin[-1]) if len(fin) else None)
    hit = _live_cache.get(ticker)
    today, prior = (None, None) if hit and hit[0] == last else _today_m1(dict(s, ticker=ticker), now)
    if not (hit and hit[0] == last) and (today is None or not len(today)):
        return None
    if hit and hit[0] == last:
        eps = hit[1]                                   # no new finished bar: the machine can't have moved
    else:
        res = run(today, ticker, now=now, prior_candles=prior)
        eps = save(res)
        _live_cache[ticker] = (last, eps)
        store.kv_set(f"orbx_stage:{ticker}", {"stage": res["stage"], "or": res["or"], "t": pd.Timestamp(now).isoformat(), "version": VERSION})
    out = []
    sess = core.session_info(now)
    for e in eps:
        if e.get("state") != "ENTRY CONFIRMED" or store.kv_get(f"orbx_acted:{e['id']}"):
            continue
        q = s.get("quote") or {}
        px, qt = q.get("last"), q.get("quote_time") or q.get("trade_time")
        if px is None or qt is None or pd.Timestamp(qt) < pd.Timestamp(e["entry_after"]):
            continue                                                           # wait for a quote after R closed
        if q.get("age_s") is not None and q["age_s"] > core.policy()["data"].get("max_eq_quote_age_s", 15):
            continue                                                           # stale quote: wait, never act on it
        store.kv_set(f"orbx_acted:{e['id']}", True)                            # one decision per episode, ever
        ok, why = entry_check(e, float(px), qt)
        if ok and not sess.get("entries_allowed"):
            ok, why = False, f"session: {sess['state']}"
        if not ok:
            _set_state(e["id"], "SKIPPED", why)
            _record(e, "SKIP", why, {"quote": {"px": px, "t": str(qt)}})
            out.append((e["id"], "SKIP", why))
            continue
        import retire
        if all(retire.is_retired(led) for led in LEDGERS):          # v4: retired (stages still recorded)
            _set_state(e["id"], "SKIPPED", retire.REASON)
            _record(e, "SKIP", retire.REASON)
            out.append((e["id"], "SKIP", retire.REASON))
            continue
        rows, err = (fetch_chain or _chain)(ticker, e["side"])
        import scanner
        best, _, rej = scanner.score_contracts(rows, e["side"], pd.Timestamp(now).to_pydatetime(), None)
        if not best:
            why = "valid stock setup, no valid option: " + (", ".join(f"{k} {n}" for k, n in rej.items()) or err or "empty chain")
            _set_state(e["id"], "SKIPPED", why)
            _record(e, "SKIP", why)
            out.append((e["id"], "SKIP", why))
            continue
        slip, fee = paper.strict_costs()
        sd = abs(float(px) - e["stop"])
        pids = []
        for led, method in LEDGERS.items():
            plan = {"symbol": best["symbol"], "label": f"{best['strike']:g}{e['side']} {best['exp'][5:]}", "family": "ORBX",
                    "premium_stop": core.cents_up(best["ask"] * (1 - core.policy()["risk"]["stop_cap_pct"]) + slip + 2 * fee / 100),
                    "premium_limit": round(best["ask"] + 0.05, 2), "stop_px": round(e["stop"] if method != "ormid1r" else (e["or_high"] + e["or_low"]) / 2, 2),
                    "t1": None, "t1_level": None, "t1_px": None, "be_trigger": None, "breakeven_net": None, "flat_by": "15:25",
                    "exit_profile": "orbx", "variant": led, "trail": method, "policy_version": VERSION, "entry_px": float(px),
                    "expiry": best["exp"], "grade": "R", "v": 35, "episode": e["id"], "atr5": e.get("atr"), "init_stop_dist": round(sd, 4),
                    "or_high": e["or_high"], "or_low": e["or_low"]}
            ok2, rwhy = paper.reserve_idea(led, e["id"], ticker, e["side"])
            if not ok2:
                continue
            pid, bwhy = paper.buy(led, e["id"], ticker, e["side"], plan, 1, e["entry_after"])
            if pid:
                pids.append(pid)
            else:
                paper.release_idea(led, e["id"], bwhy)
        if pids:
            mark_open(e["id"], pids[0])
            _record(e, "ORDER", None, {"contract": {k: best.get(k) for k in ("symbol", "bid", "ask", "delta", "exp")}, "positions": pids})
            out.append((e["id"], "ORDER", pids))
        else:
            _set_state(e["id"], "SKIPPED", "no simulated fill")
            _record(e, "SKIP", "no simulated fill")
    return out


def _chain(ticker, side):
    import engine
    return engine.chain_rows(ticker, side)


def _set_state(ep_id, state, why):
    import store
    store.x(SCHEMA)
    r = store.q("SELECT data FROM orbx_episodes WHERE id=?", (ep_id,))
    if r:
        d = json.loads(r[0]["data"])
        d.update(state=state, why=why)
        store.x("UPDATE orbx_episodes SET state=?, data=?, updated=? WHERE id=?", (state, json.dumps(d, default=str), store.ts(), ep_id))


def live_stop(p, m1_since_entry):
    """The underlying stop for an open ORBX paper trade right now, recomputed from finished bars since entry and
    only ever tightened (never widened)."""
    pl = p["plan"]
    up = p["side"] == "C"
    sgn = 1 if up else -1
    stop = float(pl.get("cur_stop") or pl["stop_px"])
    e = float(pl["entry_px"])
    sd = float(pl.get("init_stop_dist") or abs(e - float(pl["stop_px"])))
    m = pl.get("trail")
    if m in ("swing", "atr") and m1_since_entry is not None and len(m1_since_entry):
        closes = m1_since_entry["Close"].astype(float)
        best = closes.max() if up else closes.min()
        if (best - e) * sgn >= sd:
            if m == "atr":
                new = best - sgn * 2.0 * float(pl.get("atr5") or sd)
            else:
                last5 = m1_since_entry[m1_since_entry.index >= m1_since_entry.index[-1].floor("5min") - pd.Timedelta(minutes=5)]
                new = float(last5["Low"].min()) if up else float(last5["High"].max())
            stop = max(stop, new) if up else min(stop, new)
    return round(stop, 4)


def manage(p, s, now=None):
    """Exit checks for one ORBX paper trade, in precedence: the 20% premium line, the 15:25 cutoff, the underlying
    stop/trail on the latest price (protective: no candle close needed), then the fixed target (2r / ormid only)."""
    import marketdata
    import paper
    import store
    now = now or core.now_et()
    pl = p["plan"]
    q, _ = marketdata.option_quote(p["symbol"])
    reason = None
    if q and q.get("executable") and q["bid"] <= pl["premium_stop"]:
        reason = f"premium at/below the 20% line {pl['premium_stop']:.2f} (bid {q['bid']:.2f})"
    elif now.strftime("%H:%M") >= "15:25":
        reason = "ALL OUT 15:25"
    else:
        uq = s.get("quote") or {}
        px = uq.get("last")
        m1 = s.get("m1")
        since = None
        if m1 is not None and len(m1):
            since = m1[(m1.index >= pd.Timestamp(p["opened"])) & (m1.index + pd.Timedelta(minutes=1) <= pd.Timestamp(now))]
        stop = live_stop(p, since)
        if stop != pl.get("cur_stop"):
            pl.setdefault("stops", []).append({"t": now.isoformat(timespec="seconds"), "stop": stop, "by": pl.get("trail")})
            pl["cur_stop"] = stop
            store.pos_save(p)
        up = p["side"] == "C"
        if px is not None:
            if (px <= stop) if up else (px >= stop):
                reason = f"underlying {'trail' if stop != pl['stop_px'] else 'stop'} {stop:.2f} touched ({px:.2f})"
            elif pl.get("trail") in ("fixed2r", "ormid1r"):
                r_mult = 2 if pl["trail"] == "fixed2r" else 1
                sd = abs(float(pl["entry_px"]) - float(pl["stop_px"]))
                tgt = float(pl["entry_px"]) + (sd * r_mult if up else -sd * r_mult)
                if (px >= tgt) if up else (px <= tgt):
                    reason = f"{r_mult}R target {tgt:.2f} reached ({px:.2f})"
    if reason and q and q.get("executable"):
        return paper.sell(p, p["qty_open"], reason)
    return None
