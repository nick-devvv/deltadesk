"""autopilot.py - scheduled PAPER strategies that run during market hours whether or not Nick is trading. No orders go
anywhere: every fill is the internal simulator (paper.py) on live Schwab quotes, inside options market hours.

  earn_post  (default earnings strategy) post-release confirmation: on a reporting name's first regular session after
             the release, wait for a finished ORB15 break/retest or a VWAP reclaim/rejection IN the direction of the
             reaction, through the anti-chasing entry gate and a fresh contract check. One trade per name per day.
  earn_pre   (research mode only) hold an ATM straddle through the report: bought before the close on the last session
             before the event, sold at the bid 15 minutes into the next session. Sized by the FULL premium at risk
             (no 20% stop can protect an overnight gap). Measures IV crush and gaps; it is not expected to be profitable.

Every decision, accepted or rejected, is written to the candidates table with its reasons (so skipped setups stay in
the sample). Missing data blocks new entries. The emergency pause (kv "paper_pause") stops all new paper entries.
Taking no trade is a normal day.
"""
import json
import threading
import time
from datetime import datetime, timedelta

import core
import entrygate
import paper
import store

VERSION = "2026-10-30.v3.2-earnings"
DEFAULTS = {"enabled": True, "earn_post": True, "earn_pre": True, "earn_pre_buy_at": "15:40", "earn_pre_sell_at": "09:45",
            "earn_pre_max_premium_usd": 600.0, "earn_post_from": "09:46", "earn_post_until": "14:30", "max_spread_pct": 0.10,
            "max_open": 4}
_state = {"thread": None, "stop": False, "status": "idle", "last_error": None, "done": set()}


def cfg():
    c = dict(DEFAULTS)
    c.update(core.policy().get("autopilot") or {})
    return c


def _rec(cid, t, side, family, ledger, decision, reasons, plan=None, ticker=""):
    sess = core.session_info()
    store.x("INSERT OR REPLACE INTO candidates(id,date,ts,decision_t,ticker,side,family,tags,portfolio,decision,reasons,limit_blocked,evidence,plan,policy_version,provider,outcome) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, sess["date"], store.ts(), t, ticker, side, family, family, ledger, decision, json.dumps(reasons), None, None,
             json.dumps(plan, default=str) if plan else None, VERSION, "autopilot", None))


def _levels(info):
    lv = {}
    for k in ("hod", "lod", "vwap"):
        if info.get(k) is not None:
            lv[k.upper()] = {"value": info[k]}
    return lv


def earn_post(now, fetch=None):
    """Post-release confirmation entries on today's NEXT SESSION earnings names."""
    import earnings
    import scanner
    import scanner_setups as SS
    c = cfg()
    hm = now.strftime("%H:%M")
    if not (c["earn_post_from"] <= hm <= c["earn_post_until"]) or not core.session_info(now)["entries_allowed"]:
        return []
    out = []
    names = [r for r in earnings.cached_calendar() if earnings.phase(r, now) == "NEXT SESSION"]
    for rec in names:
        t = rec["ticker"]
        day = now.date().isoformat()
        idea = f"{day}-{t}-EARNPOST"
        if store.q("SELECT idea FROM ideas WHERE portfolio='earn_post' AND idea=?", (idea,)):
            continue
        row = (SS._state["rows"].get(t) or {})
        info, rows = row.get("info") or {}, row.get("rows") or []
        react = info.get("day_pct")
        if react is None or not info.get("price"):
            _rec(f"earnpost-{idea}-{hm}", now.isoformat(), "-", "EARN_POST", "earn_post", "SKIP", ["no fresh data for the name: no entry"], ticker=t)
            continue
        side = "C" if react > 0 else "P"
        want = "long" if side == "C" else "short"
        picks = [r for r in rows if r["direction"] == want and ((r["kind"] == "orb" and r["setup"].startswith("ORB15") and r["state"] in ("CLOSED BEYOND", "RETEST HOLDING"))
                                                                 or (r["kind"] == "vwap" and r["state"] in ("RECLAIMED", "REJECTED")))]
        if not picks:
            key = f"earnpost-wait-{idea}"
            if not store.kv_get(key):
                store.kv_set(key, True)
                _rec(f"earnpost-{idea}-wait", now.isoformat(), side, "EARN_POST", "earn_post", "WAIT",
                     [f"reaction {react:+.2f}%: waiting for a finished ORB15 break/retest or VWAP reclaim/rejection in that direction"], ticker=t)
            continue
        r = picks[0]
        bars = (SS._state["bars"].get(t) or (None, None))[1]
        atr5 = _atr5(bars) or (info.get("atr14") or 1) / 8
        sn = {"price": info["price"], "close1": float(bars["Close"].iloc[-1]) if bars is not None and len(bars) else info["price"],
              "t": str(bars.index[-1]) if bars is not None and len(bars) else now.isoformat(), "atr5": atr5,
              "spread": None, "spread_pct": info.get("spread_pct"), "fresh": bool((r.get("fresh") or {}).get("ok")), "bar_age_s": None, "buf": 0.02}
        tgt, tname = entrygate.target_for(r["level"], side, dict(_levels(info), **{l["name"]: {"value": l["value"]} for l in r.get("chart_levels") or []}), atr5 * 0.1)
        g = entrygate.define(t, side, "earn_post", float(r["level"]), float(r["invalidation"]), tgt, tname, sn, r["why"],
                             confirmed_at=now.isoformat(timespec="seconds"), catalyst=rec.get("release_source"))
        ev = entrygate.evaluate(g, sn)
        if ev["state"] != "ENTRY CONDITIONS MET":
            _rec(f"earnpost-{idea}-{g['id']}", now.isoformat(), side, "EARN_POST", "earn_post", "SKIP-GATE",
                 [f"gate {ev['state']}: {ev['rejected']}"], {"gate": ev}, t)
            continue
        if len(store.positions(ledger="earn_post", status="OPEN")) >= c["max_open"]:
            _rec(f"earnpost-{idea}-limit", now.isoformat(), side, "EARN_POST", "earn_post", "BLOCKED-LIMIT", ["max open earnings trades"], ticker=t)
            continue
        f = fetch or scanner._fetch
        rows_c, err = f.chain(t, side, now.date().isoformat(), (now.date() + timedelta(days=10)).isoformat(), 16)
        best, _, rej = scanner.score_contracts(rows_c, side, now, None)
        if not best:
            _rec(f"earnpost-{idea}-noc", now.isoformat(), side, "EARN_POST", "earn_post", "SKIP",
                 ["valid stock setup, no valid option: " + (", ".join(f"{k} {n}" for k, n in rej.items()) or err or "empty chain")], {"gate": ev}, t)
            continue
        ok, why = paper.reserve_idea("earn_post", idea, t, side)
        if not ok:
            continue
        slip, fee = paper.costs(best["ask"] - best["bid"])
        plan = {"symbol": best["symbol"], "label": f"{best['strike']:g}{side} {best['exp'][5:]}", "family": "EARN_POST",
                "premium_stop": core.cents_up(best["ask"] * (1 - core.policy()["risk"]["stop_cap_pct"]) + slip + 2 * fee / 100),
                "stop_px": g["invalidation"], "t1": tname, "t1_level": tgt, "t1_px": None, "be_trigger": None,
                "breakeven_net": core.cents_up(best["ask"] + slip + 2 * fee / 100), "flat_by": None, "exit_profile": "earn_post",
                "variant": "earn_post", "policy_version": VERSION, "entry_px": info["price"], "expiry": best["exp"], "grade": "R", "v": 32,
                "gate": {k: ev.get(k) for k in ("state", "latest_entry", "rr_now", "id", "version")}, "catalyst_id": rec.get("release_source")}
        pid, bwhy = paper.buy("earn_post", idea, t, side, plan, 1, now.isoformat())
        if not pid:
            paper.release_idea("earn_post", idea, bwhy)
        _rec(f"earnpost-{idea}", now.isoformat(), side, "EARN_POST", "earn_post", "ORDER" if pid else "SKIP", [] if pid else [bwhy], plan, t)
        out.append(pid)
    return [p for p in out if p]


def _atr5(m1):
    if m1 is None or len(m1) < 30:
        return None
    import indicators as I
    r = m1.between_time("09:30", "15:59")
    b = r.resample("5min").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    if len(b) < 6:
        return None
    a = I.atr(b, 14 if len(b) >= 15 else len(b) - 1)
    return float(a.iloc[-1]) if a.iloc[-1] == a.iloc[-1] else None


def earn_pre(now, fetch=None):
    """Research: an ATM straddle held through tonight's/tomorrow morning's report, sized by its full premium."""
    import earnings
    c = cfg()
    hm = now.strftime("%H:%M")
    out = []
    if hm == c["earn_pre_buy_at"] or (c["earn_pre_buy_at"] < hm < "15:55"):
        for rec in earnings.cached_calendar():
            if rec.get("status") != "confirmed":
                continue                                    # never hold through an unconfirmed date
            ev = datetime.fromisoformat(rec["date"]).date()
            timing = str(rec.get("timing") or "").lower()
            last_before = (ev if "after" in timing else earnings.prev_session(ev)) if ("after" in timing or "before" in timing) else None
            if last_before != now.date():
                continue
            idea = f"{now.date()}-{rec['ticker']}-EARNPRE"
            if store.q("SELECT idea FROM ideas WHERE portfolio='earn_pre' AND idea LIKE ?", (idea + "%",)):
                continue
            st = earnings.straddle(rec["ticker"], rec, chain=(fetch.chain_simple if fetch else None))
            if not st or st.get("error"):
                _rec(f"earnpre-{idea}", now.isoformat(), "-", "EARN_PRE", "earn_pre", "SKIP", [f"no straddle: {(st or {}).get('error')}"], ticker=rec["ticker"])
                continue
            total = (st["call_mid"] + st["put_mid"]) * 100
            if total > c["earn_pre_max_premium_usd"]:
                _rec(f"earnpre-{idea}", now.isoformat(), "-", "EARN_PRE", "earn_pre", "SKIP",
                     [f"full premium at risk ${total:.0f} > research cap ${c['earn_pre_max_premium_usd']:.0f}"], {"straddle": st}, rec["ticker"])
                continue
            if max(st.get("call_spread_pct") or 99, st.get("put_spread_pct") or 99) > c["max_spread_pct"] * 100:
                _rec(f"earnpre-{idea}", now.isoformat(), "-", "EARN_PRE", "earn_pre", "SKIP", ["spreads too wide on the event expiry"], {"straddle": st}, rec["ticker"])
                continue
            for side in ("C", "P"):
                sym = _occ(rec["ticker"], st["expiry"], side, st["strike"])
                ok, _ = paper.reserve_idea("earn_pre", f"{idea}-{side}", rec["ticker"], side)
                if not ok:
                    continue
                plan = {"symbol": sym, "label": f"{st['strike']:g}{side} {st['expiry'][5:]}", "family": "EARN_PRE", "premium_stop": 0.01,
                        "stop_px": None, "t1": None, "t1_level": None, "t1_px": None, "be_trigger": None, "breakeven_net": None,
                        "exit_profile": "earn_pre", "variant": "earn_pre", "policy_version": VERSION, "grade": "R", "v": 32,
                        "risk_note": "full premium at risk overnight; no stop can protect a gap", "straddle": st}
                pid, why = paper.buy("earn_pre", f"{idea}-{side}", rec["ticker"], side, plan, 1, now.isoformat())
                if not pid:
                    paper.release_idea("earn_pre", f"{idea}-{side}", why)
                _rec(f"earnpre-{idea}-{side}", now.isoformat(), side, "EARN_PRE", "earn_pre", "ORDER" if pid else "SKIP", [] if pid else [why], plan, rec["ticker"])
                out.append(pid)
    return [p for p in out if p]


def _occ(t, exp, side, strike):
    return f"{t}{exp[2:4]}{exp[5:7]}{exp[8:10]}{side}{int(round(strike * 1000)):08d}"


def manage(p, now=None):
    """Exits for autopilot ledgers. earn_pre: sell at the next session's earn_pre_sell_at, at the bid (gaps are real).
    earn_post: all out at the session's all-out time, the 20% planned premium level, or a finished 1m close past the
    setup's invalidation. Paper exits only happen inside options hours and never at an invented price."""
    now = now or core.now_et()
    pl = p["plan"]
    sess = core.session_info(now)
    if p["ledger"] == "earn_pre":
        opened = datetime.fromisoformat(p["opened"]).date()
        if now.date() > opened and now.strftime("%H:%M") >= cfg()["earn_pre_sell_at"]:
            return paper.sell(p, p["qty_open"], f"earnings hold over: sold at the bid at {cfg()['earn_pre_sell_at']} after the report")
        return None
    import marketdata
    q, _ = marketdata.option_quote(p["symbol"])
    if now.strftime("%H:%M") >= sess["all_out"]:
        return paper.sell(p, p["qty_open"], f"ALL OUT {sess['all_out']} (session rule)")
    if q and q.get("executable") and q["bid"] <= pl["premium_stop"]:
        return paper.sell(p, p["qty_open"], f"premium at/below the planned 20% level ${pl['premium_stop']:.2f} (bid {q['bid']:.2f})")
    import scanner_setups as SS
    bars = (SS._state["bars"].get(p["ticker"]) or (None, None))[1]
    if bars is not None and len(bars) and pl.get("stop_px") is not None:
        fin = bars[bars.index + timedelta(minutes=1) <= now]
        if len(fin):
            c1 = float(fin["Close"].iloc[-1])
            if (c1 < pl["stop_px"]) if p["side"] == "C" else (c1 > pl["stop_px"]):
                return paper.sell(p, p["qty_open"], f"setup invalidated: 1m close {c1:.2f} beyond {pl['stop_px']:.2f}")
    if pl.get("t1_level") is not None and bars is not None and len(bars):
        c1 = float(bars["Close"].iloc[-1])
        if (c1 >= pl["t1_level"]) if p["side"] == "C" else (c1 <= pl["t1_level"]):
            return paper.sell(p, p["qty_open"], f"target {pl.get('t1')} {pl['t1_level']:.2f} reached")
    return None


def step(now=None):
    c = cfg()
    now = now or core.now_et()
    if not c["enabled"]:
        _state["status"] = "off"
        return
    if store.kv_get("paper_pause"):
        _state["status"] = "paused by Nick (no new paper entries)"
    sess = core.session_info(now)
    if sess["holiday"]:
        _state["status"] = "market closed"
        return
    if now.strftime("%H:%M") >= "07:00" and not store.kv_get(f"earn_cal_refreshed:{now.date()}") and not _state.get("cal_thread"):
        import earnings                  # the calendar refreshes once a day even if the server has been up for days
        def _cal():
            try:
                earnings.refresh_calendar()
            finally:
                _state["cal_thread"] = None
        _state["cal_thread"] = threading.Thread(target=_cal, daemon=True, name="earnings-calendar")
        _state["cal_thread"].start()
    if c["earn_post"]:
        earn_post(now)
    if c["earn_pre"]:
        earn_pre(now)                     # exits are managed by the engine tick (one place, no double sells)
    if not store.kv_get("paper_pause"):
        _state["status"] = "running"


def _run():
    while not _state["stop"]:
        try:
            step()
            _state["last_error"] = None
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {e}"[:200]
        time.sleep(20)


def start():
    if _state["thread"] or not cfg()["enabled"]:
        return False
    th = threading.Thread(target=_run, daemon=True, name="autopilot")
    _state["thread"] = th
    th.start()
    return True


def today():
    day = core.now_et().strftime("%Y-%m-%d")
    rows = store.q("SELECT ts, ticker, side, family, portfolio, decision, reasons FROM candidates WHERE date=? AND portfolio IN "
                   "('earn_post','earn_pre','gated','inplay','noise','research','paper','exit31') ORDER BY ts DESC LIMIT 200", (day,))
    return [dict(r, reasons=json.loads(r["reasons"] or "[]")) for r in rows]
