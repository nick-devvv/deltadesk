"""policy_old.py - FROZEN old policy (2026-10-28.3) for comparison only. Do not tune.

This is the v2 logic exactly as it ran on Oct 28 (5m ORB/failed-break/PDH/VWAP detectors, the 3-check grade,
time-of-day stops 20% / 12% / 10%, breakeven +10/+8/+6%, T1 +20/+15/+12%, trail_v2), now driven by the same
Schwab data pipeline and the internal simulated fills, in its own 'old' ledger. It never trades real money and
never affects the main paper portfolio. It also keeps managing REAL trades that were logged under v2 plans.
"""
import json
from datetime import datetime, timedelta

import pandas as pd

import core
import paper
import store

OLD_FILE = core.HERE / "config" / "policy_old_2026-10-28.3.json"
BUF = 0.0003
_P = None


def P():
    global _P
    if _P is None:
        _P = json.loads(OLD_FILE.read_text())
    return _P


def window_for(hhmm):
    for w in P()["windows"]:
        if w["start"] <= hhmm < w["end"]:
            return w
    return None


def exit_plan(fill, t_entry_hhmm, spread=None):
    """Old fill-based plan (verified against the Oct 28 audit table)."""
    p = P()
    r = p["risk"]
    w = window_for(t_entry_hhmm) or p["windows"][-1]
    s = max(r["slippage_min"], (spread or 0) * r["slippage_spread_frac"])
    c = r["fees_per_contract_roundtrip"]
    stop = core.cents_up(fill * (1 - r["stop_cap_pct"]) + s + c / 100)
    pct = w.get("stop_pct")
    if pct is not None and pct < r["stop_cap_pct"]:
        stop = max(stop, core.cents_up(fill * (1 - pct)))
    t1m = w["t1_lo"] if p["exit_profile"]["t1_pick"] == "low" else (w["t1_lo"] + w["t1_hi"]) / 2
    flat_by = (datetime.strptime(t_entry_hhmm, "%H:%M") + timedelta(minutes=w["flat_min"])).strftime("%H:%M")
    return {"window": w["name"], "fill": round(fill, 2), "stop": stop, "slippage_reserve": round(s, 4),
            "stop_pct": pct or r["stop_cap_pct"], "be_trigger": core.cents_up(fill * w["be"]), "be_stop": round(fill, 2),
            "t1": core.cents_up(fill * t1m), "lock_after_t1": core.cents_up(fill * w["be"]), "flat_by": flat_by,
            "all_out": core.session_info()["all_out"], "policy_version": p["version"]}


def resample(df, rule):
    return df.resample(rule, label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()


def bars5(m1):
    d = m1.index[-1].date()
    r = m1[m1.index.date == d].between_time("09:30", "15:59")
    if r.empty:
        return r
    b = resample(r, "5min")
    cutoff = r.index[-1] + pd.Timedelta(minutes=1)
    return b[[i + pd.Timedelta(minutes=5) <= cutoff for i in b.index]]


def vwap_series(m1):
    d = m1.index[-1].date()
    r = m1[m1.index.date == d].between_time("09:30", "15:59")
    tp = (r["High"] + r["Low"] + r["Close"]) / 3
    return (tp * r["Volume"]).cumsum() / r["Volume"].cumsum().replace(0, 1e-9)


def avg_range(b5, n=14):
    r = (b5["High"] - b5["Low"]).iloc[-n - 1:-1]
    return float(r.mean()) if len(r) else 0.0


def detect(s):
    """Old detectors, unchanged (including their known defects: see docs/AUDIT_OCT28.md)."""
    m1, lv, rd = s["m1"], s["levels"], s["read"]
    b5 = bars5(m1)
    if len(b5) < 2 or "ORB_H" not in lv:
        return []
    oh, ol = lv["ORB_H"], lv["ORB_L"]
    last, prev = b5.iloc[-1], b5.iloc[-2]
    t = b5.index[-1]
    after = b5[b5.index >= b5.index[0] + pd.Timedelta(minutes=15)]
    out = []
    px = float(last["Close"])
    ar = avg_range(b5)
    ext = 1.5 * ar if ar > 0 else 0.0015 * px

    def add(fam, side, inv, level, note):
        out.append({"family": fam, "side": side, "bar": t.isoformat(), "trigger": round(px, 2),
                    "invalidation": round(inv, 2), "level": round(level, 2), "note": note})
    broke_up = (after["Close"].iloc[:-1] > oh).any() if len(after) > 1 else False
    broke_dn = (after["Close"].iloc[:-1] < ol).any() if len(after) > 1 else False
    if t >= b5.index[0] + pd.Timedelta(minutes=15):
        if prev["Close"] <= oh < last["Close"]:
            add("ORB_BREAK", "C", oh * (1 - BUF), oh, "5m close above ORB high" + (" (extended: wait for retest)" if px - oh > ext else ""))
        elif prev["Close"] >= ol > last["Close"]:
            add("ORB_BREAK", "P", ol * (1 + BUF), ol, "5m close below ORB low" + (" (extended: wait for retest)" if ol - px > ext else ""))
        elif broke_up and last["Low"] <= oh * (1 + 0.0005) and last["Close"] > oh and last["Close"] > last["Open"]:
            add("ORB_RETEST", "C", oh * (1 - BUF), oh, "retest of ORB high held, green 5m close")
        elif broke_dn and last["High"] >= ol * (1 - 0.0005) and last["Close"] < ol and last["Close"] < last["Open"]:
            add("ORB_RETEST", "P", ol * (1 + BUF), ol, "retest of ORB low rejected, red 5m close")
        if broke_up and prev["Close"] > oh and ol < last["Close"] <= oh:
            add("FAILED_BREAK", "P", float(after["High"].max()) * (1 + BUF), oh, "failed breakout: 5m close back inside ORB")
        if broke_dn and prev["Close"] < ol and ol <= last["Close"] < oh:
            add("FAILED_BREAK", "C", float(after["Low"].min()) * (1 - BUF), ol, "failed breakdown: 5m close back inside ORB")
    pdh, pdl, pmh, pml = lv.get("PDH"), lv.get("PDL"), lv.get("PMH"), lv.get("PML")
    if len(after) > 2:
        e9 = float(b5["Close"].ewm(span=9, adjust=False).mean().iloc[-1])
        tol = 0.0006 * px
        if pdh and (after["Close"].iloc[:-1] > pdh).any() and px > pdh and (pmh is None or px > pmh):
            if float(last["Low"]) <= max(pdh, e9) + tol and last["Close"] > last["Open"] and px > e9:
                add("PDH_RETEST", "C", min(float(last["Low"]), pdh) * (1 - BUF), pdh, "pullback to PDH/9 EMA held, green 5m close")
        if pdl and (after["Close"].iloc[:-1] < pdl).any() and px < pdl and (pml is None or px < pml):
            if float(last["High"]) >= min(pdl, e9) - tol and last["Close"] < last["Open"] and px < e9:
                add("PDL_RETEST", "P", max(float(last["High"]), pdl) * (1 + BUF), pdl, "pop to PDL/9 EMA rejected, red 5m close")
    vw = vwap_series(m1)
    if len(vw) > 10:
        v_now = float(vw.iloc[-2])
        crosses = int(rd.get("vwap_crosses_1h") or 0)
        if prev["Close"] < v_now < last["Close"] and crosses <= 2:
            add("VWAP_RECLAIM", "C", v_now * (1 - BUF), v_now, "5m close back above VWAP")
        if prev["Close"] > v_now > last["Close"] and crosses <= 2:
            add("VWAP_RECLAIM", "P", v_now * (1 + BUF), v_now, "5m close back below VWAP")
    return out


def grade(s, side):
    rd = s["read"]
    want_up = side == "C"
    agree, against = [], []
    t15 = (rd.get("trend") or {}).get("15m")
    (agree if t15 == ("UP" if want_up else "DOWN") else against).append(f"15m trend {t15}")
    v2 = rd.get("vs_200s", "n/a")
    (agree if v2 == ("ABOVE both" if want_up else "BELOW both") else against).append(f"200s: {v2}")
    day = rd.get("day_type", "")
    (agree if ("TREND UP" in day if want_up else "TREND DOWN" in day) else against).append(f"day: {day}")
    g = "A" if len(agree) == 3 else "B" if len(agree) == 2 else "C"
    chop = "CHOP" in day or (bool(rd.get("chop")) and "TREND" not in day)
    return g, agree, against, chop


def scan(ticker, s, chain_rows):
    """Old-policy shadow on the newest completed 5m bar. First contract with delta 0.40-0.55 nearest 0.45."""
    if not core.policy()["v3"]["old_policy_shadow"]["enabled"] or not s.get("ok"):
        return
    sess = core.session_info()
    if not sess["entries_allowed"]:
        return
    b5 = bars5(s["m1"])
    if not len(b5) or b5.index[-1] + pd.Timedelta(minutes=5) != (s["v3"] or {}).get("t"):
        return                     # the old detectors only ran on a newly completed 5m bar
    for st in detect(s):
        idea = f"{sess['date']}-{ticker}-{st['family']}-{st['side']}-{st['bar'][11:16]}"
        if store.q("SELECT idea FROM ideas WHERE portfolio='old' AND idea=?", (idea,)):
            continue
        g, agree, against, chop = grade(s, st["side"])
        reason = None
        d = P()["discipline"]
        if "extended" in st["note"]:
            reason = "extended (old rule)"
        elif g == "C":
            reason = "grade C (old rule)"
        elif paper.streak("old") >= d["stop_day_after_consecutive_losses"]:
            reason = "STOP FOR TODAY (old streak rule)"
        elif paper.ideas_today("old") >= d["max_trades_day"]:
            reason = "max trades (old rule)"
        c = _pick(chain_rows.get(st["side"]) or [], s["price"], st["side"]) if not reason else None
        if not reason and not c:
            reason = "no contract (old filters)"
        decision = "SKIP"
        if not reason:
            ok, why = paper.reserve_idea("old", idea, ticker, st["side"])
            if ok:
                pid = _open(idea, ticker, st, g, c)
                decision = "ORDER" if pid else "NO FILL"
                if not pid:
                    paper.release_idea("old", idea, "no fill")
            else:
                reason = why
        store.x("INSERT OR IGNORE INTO candidates(id,date,ts,decision_t,ticker,side,family,tags,portfolio,decision,reasons,limit_blocked,evidence,plan,policy_version,provider,outcome) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"old-{idea}", sess["date"], store.ts(), st["bar"], ticker, st["side"], st["family"], st["family"], "old", decision,
                 json.dumps([reason] if reason else []), None, json.dumps({"note": st["note"], "agree": agree, "against": against}),
                 None, P()["version"], s.get("price_src"), None))


def _pick(rows, price, side):
    cp = P()["contract"]
    best = None
    for c in rows:
        if c["bid"] <= 0 or not (cp["premium_min"] <= c["ask"] <= cp["premium_max"]) or (c["ask"] - c["bid"]) / c["ask"] > cp["max_spread_pct"]:
            continue
        d = c.get("delta")
        if d is None or not (cp["abs_delta_min"] <= abs(d) <= cp["abs_delta_max"]):
            continue
        k = abs(abs(d) - cp.get("abs_delta_target", 0.45))
        if best is None or k < best[0]:
            best = (k, c)
    return best[1] if best else None


def _open(idea, ticker, st, g, c):
    import retire
    if retire.is_retired("old"):                       # v4: retired (no new entries; open trades still managed)
        return None
    q, err = paper.sim_quote(c["symbol"])
    if not q:
        return None
    qty = P()["sizing_by_grade"].get(g, 0)
    slip, fee = paper.costs(q["ask"] - q["bid"])
    fill = round(q["ask"] + slip, 4)
    ex = exit_plan(fill, core.hm(core.now_et()), q["ask"] - q["bid"])
    pid = f"OL-{idea}"
    plan = dict(ex, v=2, invalidation=st["invalidation"], be_hit=False, t1_done=False, trail=None, last_bid=q["bid"],
                entry_px=paper.underlying_px(ticker))
    with store.tx():                                   # v3.5: one atomic unit, and a retry never overwrites a fill
        if store.q("SELECT id FROM positions WHERE id=?", (pid,)):
            return None
        store.pos_insert({"id": pid, "ledger": "old", "date": core.now_et().strftime("%Y-%m-%d"), "ticker": ticker,
                          "contract": f"{int(c['symbol'][-8:]) / 1000:g}{c['symbol'][-9]}", "symbol": c["symbol"], "side": st["side"],
                          "qty_init": qty, "qty_open": qty, "fill": fill, "opened": store.ts(), "closed": None, "status": "OPEN",
                          "setup_id": idea, "grade": g, "setup": st["family"], "plan": plan, "realized": round(-fee * qty, 2),
                          "mfe": 0, "mae": 0, "policy_version": P()["version"], "verified": "sim fill (old-policy shadow)", "notes": st["note"]})
        store.x("UPDATE ideas SET status='FILLED', position_id=? WHERE portfolio='old' AND idea=?", (pid, idea))
        store.event("old", f"OLD-POLICY BUY {qty} {ticker} {plan.get('window')} {st['family']} sim ${fill:.2f}", "old", pid)
    return pid


def manage(p, s, quote_fn):
    """Old exit precedence: all-out > premium stop > underlying invalidation > if-flat > BE > T1 > trail.
    'old' ledger: simulated sells. 'real' (v2 plans): advice only."""
    pl = p["plan"]
    if pl.get("manual"):
        return []
    q, err = quote_fn(p["symbol"])
    now = core.hm(core.now_et())
    sess = core.session_info()
    m1 = s.get("m1") if s.get("ok") else None
    b1 = m1[m1.index.date == m1.index[-1].date()].between_time("09:30", "15:59") if m1 is not None and len(m1) else None
    last_close = float(b1["Close"].iloc[-1]) if b1 is not None and len(b1) else None
    acts = []
    if not q or not q.get("bid"):
        if now >= sess["all_out"]:
            acts.append(("exit", p["qty_open"], "ALL OUT time (no quote)"))
    else:
        bid = q["bid"]
        pl["last_bid"] = bid
        if p.get("fill"):                      # v3.4.2: best / worst % move from the fill (recording only; exits unchanged)
            mv = (bid - p["fill"]) / p["fill"] * 100
            p["mfe"], p["mae"] = round(max(p["mfe"] or 0, mv), 1), round(min(p["mae"] or 0, mv), 1)
        up = p["side"] == "C"
        inv_hit = last_close is not None and (last_close < pl["invalidation"] if up else last_close > pl["invalidation"])
        if now >= sess["all_out"]:
            acts.append(("exit", p["qty_open"], f"ALL OUT {sess['all_out']}"))
        elif bid <= pl["stop"]:
            acts.append(("exit", p["qty_open"], "BREAKEVEN STOP" if pl["be_hit"] else "STOP" if not pl["t1_done"] else "LOCKED-PROFIT STOP"))
        elif not pl["t1_done"] and inv_hit:
            acts.append(("exit", p["qty_open"], f"SETUP INVALIDATED (1m close {last_close:.2f} beyond {pl['invalidation']:.2f})"))
        elif not pl["be_hit"] and now >= pl["flat_by"] and bid < pl["be_trigger"]:
            acts.append(("exit", p["qty_open"], f"IF FLAT: not at breakeven by {pl['flat_by']}"))
        else:
            if not pl["be_hit"] and bid >= pl["be_trigger"]:
                pl["be_hit"] = True
                pl["stop"] = core.tighten_only(pl["stop"], pl["be_stop"])
                acts.append(("note", 0, f"BREAKEVEN: move stop to ${pl['stop']:.2f}"))
            if not pl["t1_done"] and bid >= pl["t1"]:
                pl["t1_done"] = True
                pl["stop"] = core.tighten_only(pl["stop"], pl["lock_after_t1"])
                acts.append(("exit", 1, f"T1 ${pl['t1']:.2f}: sell 1") if p["qty_open"] >= 2 else
                            ("note", 0, f"T1 ${pl['t1']:.2f}: hold, stop up to ${pl['stop']:.2f}"))
    store.pos_save(p)
    done = []
    for kind, qn, why in acts:
        key = f"oldact:{p['id']}:{why[:24]}:{p['qty_open']}"
        if store.kv_get(key):
            continue
        if p["ledger"] == "old" and kind == "exit" and qn > 0:
            n, px = paper.sell(p, qn, why)
            if n:
                store.kv_set(key, True)
                done.append((kind, n, why))
        elif p["ledger"] == "real":
            store.kv_set(key, True)
            store.event("real_alert", f"YOUR {p['ticker']} {p['contract']}: {why}" +
                        (" -> do it in Robinhood, then log OUT" if kind == "exit" else " -> update your stop in Robinhood"), "real", p["id"])
            done.append((kind, qn, why))
        else:
            store.kv_set(key, True)
    return done
