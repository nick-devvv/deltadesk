"""news_momentum.py - v3.5 (new): NEWS-MOM-1, individual-stock trades that need BOTH a verified catalyst and a
confirmed price/volume reaction. The rules live in config/news_momentum.json (machine-readable, with the reason for
every threshold); this module applies them. ORB or any other technical setup is never a reason to enter here.

evaluate() is pure: given the catalyst AS KNOWN at `now`, today's finished 1m bars and prior sessions, it returns the
stage (WATCHING / CONFIRMING / ENTRY CONFIRMED / SKIP / EXPIRED) with the exact unmet requirement and every measured
number. live_step() runs it for today's eligible catalysts and opens ONE paper contract per catalyst cluster in the
`news_mom` research ledger. No news backtest exists (no contemporaneous history of publication and receipt times), so
the evidence for this candidate is collected forward (hypothesis H-NEWS-1).
"""
import json
from datetime import timedelta

import numpy as np
import pandas as pd

import core

SPEC_FILE = core.HERE / "config" / "news_momentum.json"
VERSION = "2026-10-31.newsmom1"
LEDGER = "news_mom"


def spec():
    return json.loads(SPEC_FILE.read_text())


def _rth(m):
    return m[(m.index.strftime("%H:%M") >= "09:30") & (m.index.strftime("%H:%M") <= "15:59")] if m is not None else None


def atr5(m1_today, prior_sessions, n=14):
    """5-minute ATR(14) from finished 5m candles (prior sessions warm it up)."""
    frames = [p for p in (prior_sessions or [])[-2:]] + ([m1_today] if m1_today is not None else [])
    m = pd.concat([_rth(f) for f in frames if f is not None and len(f)]) if frames else None
    if m is None or len(m) < 30:
        return None
    b5 = m.resample("5min").agg({"High": "max", "Low": "min", "Close": "last"}).dropna()
    pc = b5["Close"].shift(1)
    tr = pd.concat([b5["High"] - b5["Low"], (b5["High"] - pc).abs(), (b5["Low"] - pc).abs()], axis=1).max(axis=1).dropna()
    return float(tr.tail(n).mean()) if len(tr) >= n else None


def rvol_since(m1_today, prior_sessions, t0, t1):
    """Volume between t0 and t1 today vs the average for the SAME minutes over prior sessions (None if no baseline)."""
    v = float(m1_today[(m1_today.index >= t0) & (m1_today.index < t1)]["Volume"].sum())
    base = []
    for p in prior_sessions or []:
        if p is None or not len(p):
            continue
        d = p.index[0].date()
        a = pd.Timestamp(f"{d} {t0.strftime('%H:%M')}", tz=core.ET)
        b = pd.Timestamp(f"{d} {t1.strftime('%H:%M')}", tz=core.ET)
        base.append(float(p[(p.index >= a) & (p.index < b)]["Volume"].sum()))
    base = [x for x in base if x > 0]
    return (round(v / np.mean(base), 2), len(base)) if base else (None, 0)


def evaluate(cat, m1_today, prior_sessions, now, sp=None):
    """Stage + reasons + numbers for one catalyst on one stock, from information available at `now` only."""
    import catalysts
    sp = sp or spec()
    th = sp["thresholds"]
    now = pd.Timestamp(now)
    out = {"catalyst": cat.get("id"), "rev": cat.get("_rev"), "ticker": (cat.get("tickers") or ["?"])[0], "label": cat.get("label"),
           "headline": (cat.get("headline") or "")[:160], "version": VERSION, "checks": [], "numbers": {}}

    def fail(stage, why):
        out.update(stage=stage, why=why)
        return out

    def chk(name, ok, detail):
        out["checks"].append({"check": name, "pass": bool(ok), "detail": detail})
        return ok
    if not chk("verified catalyst", catalysts.entry_eligible(cat), catalysts.eligibility(cat)):
        return fail("WATCHING", "catalyst not entry-eligible: " + catalysts.eligibility(cat))
    if not chk("company-specific", len(cat.get("tickers") or []) <= th["catalyst"]["max_tickers"] and cat.get("category") in th["catalyst"]["categories"],
               f"{len(cat.get('tickers') or [])} tickers, category {cat.get('category')}"):
        return fail("SKIP", "not a company-specific catalyst in the allowed categories")
    fd = pd.Timestamp(cat["first_detected_at"])
    age = (now - fd).total_seconds() / 60
    out["numbers"]["age_min"] = round(age, 1)
    pub = cat.get("published_at")
    lat = round((fd - pd.Timestamp(pub)).total_seconds() / 60, 1) if pub else None
    out["numbers"]["pub_to_detect_min"] = lat
    late = lat is not None and lat > th["catalyst"]["max_pub_to_detect_min"]
    out["late_news"] = late
    if age > th["entry"]["timeout_min"]:
        return fail("EXPIRED", f"{age:.0f} min since the desk received the news (limit {th['entry']['timeout_min']})")
    hm = now.strftime("%H:%M")
    m = _rth(m1_today)
    m = m[m.index + pd.Timedelta(minutes=1) <= now] if m is not None else None
    if m is None or len(m) < 15:
        return fail("WATCHING", "not enough of today's finished regular-session bars yet")
    a = atr5(m1_today[m1_today.index + pd.Timedelta(minutes=1) <= now], prior_sessions)
    if not chk("5m ATR known", a, f"{a}"):
        return fail("WATCHING", "5m ATR unavailable (needs prior sessions): fails closed")
    px = float(m["Close"].iloc[-1])
    ref = cat.get("price_at_detect")
    if ref is None:
        before = m[m.index < fd]
        ref = float(before["Close"].iloc[-1]) if len(before) else float(m["Open"].iloc[0])
    move = (px - ref) / a
    side = "C" if move > 0 else "P"
    sgn = 1 if side == "C" else -1
    lean = (((cat.get("sentiment") or {}).get("trader") or {}).get("lean") or "").lower()
    out["numbers"].update(atr5=round(a, 4), ref_px=ref, px=px, move_atr5=round(move, 2), side=side, sentiment_lean=lean or None)
    th_r = th["reaction"]
    if abs(move) > th_r["max_move_atr5"]:
        return fail("SKIP", f"exhausted: already {abs(move):.1f} x ATR5 from the price when the news arrived (limit {th_r['max_move_atr5']})")
    if not chk("move since the news", abs(move) >= th_r["min_move_atr5"], f"{move:+.2f} x ATR5 (needs {th_r['min_move_atr5']})"):
        return fail("WATCHING", f"price reaction {move:+.2f} x ATR5 is not yet {th_r['min_move_atr5']}")
    t0 = max(fd.floor("1min"), m.index[0])
    rv, nb = rvol_since(m, prior_sessions, t0, now.floor("1min"))
    out["numbers"].update(rvol_time=rv, rvol_sessions=nb)
    if not chk("relative volume (same minutes)", rv is not None and rv >= th_r["min_rvol_time"], f"{rv} over {nb} sessions"):
        return fail("WATCHING" if rv is not None else "WATCHING", "relative volume " + ("baseline unavailable: fails closed" if rv is None else f"{rv}x is under {th_r['min_rvol_time']}x"))
    since = m[m.index >= t0]
    ext = float(since["High"].max()) if side == "C" else float(since["Low"].min())
    retr = (ext - px) * sgn / max(1e-9, (ext - ref) * sgn)
    out["numbers"]["retrace_frac"] = round(retr, 2)
    if not chk("held its gain", retr <= th_r["max_retrace_frac"], f"gave back {retr:.0%} of the post-news range"):
        return fail("SKIP", f"spike, not momentum: gave back {retr:.0%} of the move (limit {th_r['max_retrace_frac']:.0%})")
    if not chk("lasted", (now - fd).total_seconds() / 60 >= th_r["min_minutes_since_detect"], f"{age:.0f} min since the news"):
        return fail("CONFIRMING", f"wait: the reaction must survive {th_r['min_minutes_since_detect']} min")
    en = th["entry"]
    if not (en["earliest"] <= hm <= en["latest"]):
        return fail("WATCHING" if hm < en["earliest"] else "EXPIRED", f"entries only {en['earliest']}-{en['latest']} ET")
    tp = (m["High"] * 0 + (m["High"] + m["Low"] + m["Close"]) / 3)
    vwap = float((tp * m["Volume"]).sum() / max(1.0, m["Volume"].sum()))
    last3 = m["Close"].iloc[-3:].values
    side_ok = all((x - vwap) * sgn > 0 for x in last3)
    cont = (float(m["Close"].iloc[-1]) - (float(m["High"].iloc[-2]) if side == "C" else float(m["Low"].iloc[-2]))) * sgn > 0
    out["numbers"].update(vwap=round(vwap, 4), ext_vwap_atr5=round((px - vwap) * sgn / a, 2))
    if not chk("continuation close", side_ok and cont, f"last 3 closes {'above' if side == 'C' else 'below'} VWAP {side_ok}, close beyond prior bar {cont}"):
        return fail("CONFIRMING", "wait for a completed 1m close beyond the prior candle with the last 3 closes on the news side of VWAP")
    if not chk("not chasing", (px - vwap) * sgn / a <= en["max_extension_vwap_atr5"], f"{(px - vwap) * sgn / a:.2f} x ATR5 from VWAP (max {en['max_extension_vwap_atr5']})"):
        return fail("CONFIRMING", f"too extended from VWAP: wait for a pullback (max {en['max_extension_vwap_atr5']} x ATR5)")
    b5 = m[m.index >= m.index[-1].floor("5min") - pd.Timedelta(minutes=5)]
    far = float(b5["Low"].min()) if side == "C" else float(b5["High"].max())
    base = min(far, vwap) if side == "C" else max(far, vwap)
    stop = base - sgn * 0.05 * a
    sd = (px - stop) * sgn
    if not chk("stop distance", 0 < sd <= en["max_stop_atr5"] * a, f"{sd:.2f} vs max {en['max_stop_atr5']} x ATR5"):
        return fail("SKIP", "the structural stop is too far for this entry")
    out.update(stage="ENTRY CONFIRMED", why=None, side=side, stop=round(stop, 4), stop_dist=round(sd, 4), entry_ref=px, late_news=late,
               signal_t=m.index[-1].isoformat())
    if late:
        out["checks"].append({"check": "news latency", "pass": False, "detail": f"received {lat} min after publication: recorded as LATE"})
    return out


def _prior_sessions(t, day, n=10):
    import lab
    out = []
    d = pd.Timestamp(day)
    k = 0
    while len(out) < n and k < 20:
        k += 1
        dd = (d - pd.Timedelta(days=k)).date()
        if dd.weekday() >= 5:
            continue
        a = lab.archive_read(dd, t)
        if a is not None and len(a):
            out.append(_rth(a))
    return list(reversed(out))


def live_step(now=None, fetch=None):
    """Today's eligible catalysts (as known now) -> evaluate -> at most one paper contract per catalyst cluster."""
    import catalysts
    import paper
    import scanner
    import store
    now = now or core.now_et()
    sp = spec()
    day = now.date()
    view = catalysts.view_as_of(catalysts.revisions_between(pd.Timestamp(now) - pd.Timedelta(hours=20), now), now)
    res = []
    for c in view.values():
        tks = c.get("tickers") or []
        if not tks or tks[0] in core.policy()["instruments"] or str(c.get("first_detected_at", ""))[:10] != str(day):
            continue
        t = tks[0]
        key = f"newsmom:{day}:{c.get('cluster') or c['id']}"
        if store.kv_get(key):
            continue
        try:
            import lab
            m1 = lab._today_bars(t, now)
        except Exception:
            m1 = None
        if m1 is None or not len(m1):
            continue
        ev = evaluate(c, m1, _prior_sessions(t, day), now, sp)
        store.kv_set(f"newsmom_stage:{t}:{c['id']}", {k: ev.get(k) for k in ("stage", "why", "numbers", "headline", "label", "rev", "side")} | {"t": now.isoformat()})
        if ev["stage"] != "ENTRY CONFIRMED":
            if ev["stage"] in ("SKIP", "EXPIRED"):
                store.kv_set(key, ev["stage"])
                _record(t, ev)
            continue
        store.kv_set(key, "ENTRY")
        f = fetch or scanner._fetch
        rows, err = f.chain(t, ev["side"], day.isoformat(), (day + timedelta(days=10)).isoformat(), 16)
        best, _, rej = scanner.score_contracts(rows, ev["side"], now, None)
        if not best:
            ev.update(stage="SKIP", why="valid stock reaction, no valid option: " + (", ".join(f"{k} {n}" for k, n in rej.items()) or err or "empty chain"))
            _record(t, ev)
            res.append((t, "SKIP", ev["why"]))
            continue
        import underlying_first as U
        trig = U.premium_trigger(best["ask"] + paper.strict_costs()[0], 1, best["bid"], t)
        if not trig["feasible"]:
            ev.update(stage="SKIP", why=trig["why"])
            _record(t, ev)
            res.append((t, "SKIP", ev["why"]))
            continue
        idea = f"{day}-{t}-NEWS-{c.get('cluster') or c['id']}"
        plan = {"symbol": best["symbol"], "label": f"{best['strike']:g}{ev['side']} {best['exp'][5:]}", "family": "NEWS-MOM-1",
                "premium_stop": trig["trigger_bid"], "premium_limit": round(best["ask"] + 0.05, 2), "stop_px": ev["stop"], "t1": None,
                "t1_level": None, "t1_px": None, "be_trigger": None, "breakeven_net": None, "flat_by": "15:25", "exit_profile": "news",
                "variant": LEDGER, "policy_version": VERSION, "entry_px": ev["entry_ref"], "expiry": best["exp"], "grade": "R", "v": 35,
                "atr5": ev["numbers"]["atr5"], "init_stop_dist": ev["stop_dist"], "catalyst": {"id": c["id"], "rev": c.get("_rev"),
                                                                                              "label": c.get("label"), "late": ev.get("late_news")}}
        ok, why = paper.reserve_idea(LEDGER, idea, t, ev["side"])
        pid = None
        if ok:
            pid, why = paper.buy(LEDGER, idea, t, ev["side"], plan, 1, ev["signal_t"])
            if not pid:
                paper.release_idea(LEDGER, idea, why)
        ev.update(stage="ORDER" if pid else "SKIP", why=None if pid else why, position=pid)
        _record(t, ev, plan)
        res.append((t, ev["stage"], pid or why))
    return res


def _record(t, ev, plan=None):
    try:
        import learning
        learning.record_decision(LEDGER, t, ev.get("side") or ev.get("numbers", {}).get("side"), "NEWS-MOM-1", VERSION,
                                 ev.get("stage"), [ev.get("why")] if ev.get("why") else [], opportunity=f"news|{ev.get('catalyst')}",
                                 position=ev.get("position"), snapshot={"numbers": ev.get("numbers"), "checks": ev.get("checks"),
                                                                        "catalyst_rev": ev.get("rev"), "plan": plan,
                                                                        "stop_dist": ev.get("stop_dist")})
    except Exception:
        pass


def manage(p, now=None):
    """Exit precedence: the 20% premium line, 15:25, the underlying stop/trail on the latest price, a completed 5m
    close back through VWAP. The trail only tightens."""
    import marketdata
    import paper
    import store
    now = now or core.now_et()
    pl = p["plan"]
    q, _ = marketdata.option_quote(p["symbol"])
    up = p["side"] == "C"
    sgn = 1 if up else -1
    reason = None
    if q and q.get("executable") and q["bid"] <= pl["premium_stop"]:
        reason = f"premium at/below the 20% line {pl['premium_stop']:.2f} (bid {q['bid']:.2f})"
    elif now.strftime("%H:%M") >= "15:25":
        reason = "ALL OUT 15:25"
    else:
        try:
            import lab
            m1 = lab._today_bars(p["ticker"], now)
        except Exception:
            m1 = None
        if m1 is not None and len(m1):
            m = _rth(m1[m1.index + pd.Timedelta(minutes=1) <= pd.Timestamp(now)])
            since = m[m.index >= pd.Timestamp(p["opened"])]
            px = float(m["Close"].iloc[-1]) if len(m) else None
            stop = float(pl.get("cur_stop") or pl["stop_px"])
            sd = float(pl.get("init_stop_dist") or abs(float(pl["entry_px"]) - float(pl["stop_px"])))
            if len(since):
                best = float(since["Close"].max()) if up else float(since["Close"].min())
                if (best - float(pl["entry_px"])) * sgn >= sd:
                    new = best - sgn * 2.0 * float(pl.get("atr5") or sd)
                    stop = max(stop, new) if up else min(stop, new)
            if stop != pl.get("cur_stop"):
                pl["cur_stop"] = round(stop, 4)
                pl.setdefault("stops", []).append({"t": now.isoformat(timespec="seconds"), "stop": round(stop, 4), "by": "atr trail"})
                store.pos_save(p)
            uq = marketdata.quote(p["ticker"]) or {}
            last = uq.get("last") or px
            if last is not None and (last - stop) * sgn <= 0:
                reason = f"underlying stop/trail {stop:.2f} touched ({last:.2f})"
            elif len(m) >= 6 and (now.minute % 5 == 0):
                tp = (m["High"] + m["Low"] + m["Close"]) / 3
                vwap = float((tp * m["Volume"]).sum() / max(1.0, m["Volume"].sum()))
                c5 = float(m["Close"].iloc[-1])
                if (c5 - vwap) * sgn < 0:
                    reason = f"momentum failure: 5m close {c5:.2f} back through VWAP {vwap:.2f}"
    if reason and q and q.get("executable"):
        return paper.sell(p, p["qty_open"], reason)
    return None
