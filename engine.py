"""engine.py - deterministic desk engine: snapshot, setups, plans, watches, paper engine, position management.

No AI calls here. Chart (Grok) only explains what this produces.
"""
import json
import threading
from datetime import datetime, timedelta

import pandas as pd

import broker
import core
import desk
import store

_cache = {}
_mx = threading.RLock()
BUF = 0.0003  # 0.03% of price: invalidation buffer beyond a level


# ======================= market snapshot =======================
def _bars(ticker):
    import chartdata
    m1 = chartdata._dl(ticker, "5d", "1m", True)
    daily = chartdata._dl(ticker, "2y", "1d", False)
    if m1 is None or m1.empty:
        return None, None
    m1 = m1.tz_convert(core.ET) if m1.index.tz is not None else m1.tz_localize(core.ET)
    return m1, daily


def snapshot(ticker, max_age=8):
    """One timestamped view of a ticker. Cached a few seconds so every consumer sees the same numbers."""
    with _mx:
        hit = _cache.get(ticker)
        if hit and (core.now_et() - hit["_at"]).total_seconds() < max_age:
            return hit
    m1, daily = _bars(ticker)
    if m1 is None:
        return {"ticker": ticker, "ok": False, "error": "NO DATA (Yahoo)", "_at": core.now_et()}
    r = desk.read(ticker, m1.copy(), daily.copy())
    last, err = broker.stock_last(ticker) if broker.configured() else (None, "no keys")
    bar_t = m1.index[-1]
    age = (core.now_et() - bar_t.to_pydatetime()).total_seconds() - 60  # bar stamp = start of minute
    s = {
        "ticker": ticker, "ok": "error" not in r, "_at": core.now_et(), "snap_id": store.new_id(f"S-{ticker}"),
        "read": {k: v for k, v in r.items() if not k.startswith("_")}, "levels": r.get("_draw", {}),
        "price": float(last["price"]) if last else float(m1["Close"].iloc[-1]),
        "price_src": (last or {}).get("feed", "Yahoo 1m close"), "price_ts": (last or {}).get("ts"),
        "bar_ts": bar_t.isoformat(), "bar_age_s": round(max(age, 0)), "m1": m1,
    }
    s["stale"] = s["bar_age_s"] > core.policy()["data"]["max_bar_age_s"] and core.session_info()["state"] in (
        "OPEN", "ORB FORMING", "NO NEW ENTRIES", "ALL OUT")
    with _mx:
        _cache[ticker] = s
    return s


def rth_today(m1):
    d = m1.index[-1].date()
    t = m1[m1.index.date == d]
    return t.between_time("09:30", "15:59")


def completed(df, minutes, now_bar):
    """Bars whose whole period has printed (start + minutes <= last 1m bar start + 1 minute)."""
    cutoff = now_bar + pd.Timedelta(minutes=1)
    return df[[i + pd.Timedelta(minutes=minutes) <= cutoff for i in df.index]]


def bars5(m1):
    r = rth_today(m1)
    if r.empty:
        return r
    b = desk.resample(r, "5min")
    return completed(b, 5, r.index[-1])


def bars1_done(m1):
    r = rth_today(m1)
    return r.iloc[:-1] if len(r) > 1 else r.iloc[0:0]  # the last 1m bar may still be forming


def vwap_series(m1):
    r = rth_today(m1)
    tp = (r["High"] + r["Low"] + r["Close"]) / 3
    return (tp * r["Volume"]).cumsum() / r["Volume"].cumsum().replace(0, 1e-9)


# ======================= setups (completed bars only) =======================
def detect(s):
    """New setups on the newest completed 5m bar. Families: ORB break/retest, failed break reclaim, VWAP reclaim."""
    m1, lv, rd = s["m1"], s["levels"], s["read"]
    b5 = bars5(m1)
    if len(b5) < 2 or "ORB_H" not in lv:
        return []
    oh, ol = lv["ORB_H"], lv["ORB_L"]
    last, prev = b5.iloc[-1], b5.iloc[-2]
    t = b5.index[-1]
    after = b5[b5.index >= b5.index[0] + pd.Timedelta(minutes=15)]  # bars after the ORB
    out = []
    px = float(last["Close"])
    ext = 0.0015 * px

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
            ext_hi = float(after["High"].max())
            add("FAILED_BREAK", "P", ext_hi * (1 + BUF), oh, "failed breakout: 5m close back inside ORB")
        if broke_dn and prev["Close"] < ol and ol <= last["Close"] < oh:
            ext_lo = float(after["Low"].min())
            add("FAILED_BREAK", "C", ext_lo * (1 - BUF), ol, "failed breakdown: 5m close back inside ORB")
    vw = vwap_series(m1)
    if len(vw) > 10:
        v_now = float(vw.iloc[-2]) if len(vw) > 1 else float(vw.iloc[-1])
        crosses = int(rd.get("vwap_crosses_1h") or 0)
        if prev["Close"] < v_now < last["Close"] and crosses <= 2:
            add("VWAP_RECLAIM", "C", v_now * (1 - BUF), v_now, "5m close back above VWAP")
        if prev["Close"] > v_now > last["Close"] and crosses <= 2:
            add("VWAP_RECLAIM", "P", v_now * (1 + BUF), v_now, "5m close back below VWAP")
    return out


def grade(s, side):
    """Rule-compliance grade (not a win probability). Counts context that agrees with the side."""
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
    chop = "CHOP" in day or (bool(rd.get("chop")) and "TREND" not in day)  # holding outside the ORB = trend day
    return g, agree, against, chop


# ======================= contracts =======================
def pick_contract(ticker, side, price, budget, grade_, chop, structural=None):
    p = core.policy()["contract"]
    exp = core.now_et().strftime("%Y-%m-%d")
    rows, err = broker.chain(ticker, side, exp)
    if not rows:
        return None, f"no option chain ({err})"
    cands, rejected = [], 0
    for c in rows:
        if c["bid"] <= 0 or not (p["premium_min"] <= c["ask"] <= p["premium_max"]):
            rejected += 1
            continue
        if (c["ask"] - c["bid"]) / c["ask"] > p["max_spread_pct"]:
            rejected += 1
            continue
        d = c["delta"]
        if d is not None and not (p["abs_delta_min"] <= abs(d) <= p["abs_delta_max"]):
            rejected += 1
            continue
        rank = abs(abs(d) - 0.40) if d is not None else abs(c["strike"] - price) / price * 10
        cands.append((rank, (c["ask"] - c["bid"]) / c["ask"], c))
    if not cands:
        return None, f"no contract passes price ${p['premium_min']}-{p['premium_max']}, spread <= {int(p['max_spread_pct']*100)}% and delta {p['abs_delta_min']}-{p['abs_delta_max']}"
    cands.sort(key=lambda z: (z[0], z[1]))
    t = core.hm(core.now_et())
    for _, _, c in cands:
        ex = core.exit_plan(c["ask"], t, c["ask"] - c["bid"])
        qn, rpc, cap, why = core.size(c["ask"], ex["stop"], ex["slippage_reserve"], grade_, budget, chop)
        if qn >= 1 or grade_ == "C":
            c.update(qty=qn, risk_per_contract=rpc, exit=ex, size_note=why, delta_known=c["delta"] is not None)
            return c, None
    c = cands[0][2]
    return None, f"too expensive for the risk cap: cheapest fit {c['symbol']} ask {c['ask']}"


def occ_to_label(sym):
    side = sym[-9]
    return f"{int(sym[-8:]) / 1000:g}{side}"


# ======================= budgets / discipline =======================
def ledger_budget(ledger):
    day = core.now_et().strftime("%Y-%m-%d")
    r_day, n_day = store.ledger_stats(ledger, day=day)
    r_week, _ = store.ledger_stats(ledger, since=core.week_start())
    unreal, open_risk = 0.0, 0.0
    for p in store.positions(ledger=ledger, status="OPEN"):
        pl = p["plan"]
        mark = pl.get("last_bid") or p["fill"]
        unreal += (mark - p["fill"]) * 100 * p["qty_open"]
        open_risk += max(0.0, (mark - pl.get("stop", p["fill"]) + pl.get("slippage_reserve", 0.01)) * 100 * p["qty_open"])
    left, day_left, week_left = core.budget_left(r_day, unreal, open_risk, r_week)
    return {"realized_day": r_day, "realized_week": r_week, "unrealized": round(unreal, 2),
            "open_risk": round(open_risk, 2), "left": left, "day_left": day_left, "week_left": week_left,
            "trades_today": n_day}


def discipline_gate(ledger, grade_):
    d = core.policy()["discipline"]
    day = core.now_et().strftime("%Y-%m-%d")
    done = [p for p in store.positions(ledger=ledger, day=day)]
    closed = [p for p in done if p["status"] == "CLOSED"]
    streak = 0
    for p in reversed(closed):
        if (p["realized"] or 0) < 0:
            streak += 1
        else:
            break
    if streak >= d.get("stop_day_after_consecutive_losses", 99):
        return f"STOP FOR TODAY: {streak} losses in a row"
    if len(done) >= d["max_trades_day"]:
        return f"max {d['max_trades_day']} trades today reached"
    if (len(done) >= d["a_only_after_trades"] or streak >= d["a_only_after_consecutive_losses"]) and grade_ != "A":
        return f"A setups only now ({len(done)} trades, {streak} losses in a row)"
    if closed and (closed[-1]["realized"] or 0) < 0 and closed[-1]["closed"]:
        last = datetime.fromisoformat(closed[-1]["closed"])
        if core.now_et() - last < timedelta(minutes=d["cooldown_min_after_loss"]):
            return f"cooldown {d['cooldown_min_after_loss']} min after a loss"
    return None


def event_block():
    """Scheduled events (config/events.json written by the 9 AM routine): [{"time":"08:30","name":"CPI"}]."""
    f = core.HERE / "config" / "events.json"
    try:
        evs = json.loads(f.read_text())
    except Exception:
        return None
    if evs.get("date") != core.now_et().strftime("%Y-%m-%d"):
        return None
    m = core.policy()["discipline"]["event_block_min"]
    now = core.now_et()
    for e in evs.get("events", []):
        t = datetime.combine(now.date(), datetime.strptime(e["time"], "%H:%M").time(), core.ET)
        if abs((t - now).total_seconds()) <= m * 60:
            return f"EVENT: {e['name']} at {e['time']} ET (no new entries {m} min around it)"
    return None


# ======================= plans (shared by paper engine, watches and chat) =======================
def build_plan(ticker, side, level=None, mode="check", ledger="real"):
    """Complete conditional plan. state: WAIT / READY / PASS / MANAGE / DATA UNAVAILABLE."""
    ticker, side = ticker.upper(), side.upper()[:1]
    s = snapshot(ticker)
    sess = core.session_info()
    plan = {"id": store.new_id(f"P-{ticker}"), "ticker": ticker, "side": side, "mode": mode,
            "created": store.ts(), "policy_version": core.policy()["version"], "session": sess,
            "snap": {"id": s.get("snap_id"), "price": s.get("price"), "price_src": s.get("price_src"),
                     "bar_age_s": s.get("bar_age_s")}, "objections": [], "support": []}
    if not s.get("ok"):
        plan.update(state="DATA UNAVAILABLE", reason=s.get("error"))
        return plan
    if s["stale"]:
        plan.update(state="DATA UNAVAILABLE", reason=f"bars {s['bar_age_s']}s old")
        return plan
    g, agree, against, chop = grade(s, side)
    plan.update(grade=g, support=agree, objections=against, chop_day=chop, day=s["read"].get("day_type"))
    # setup: newest engine setup in this direction, else a level-based trigger
    setups = [x for x in detect(s) if x["side"] == side]
    px = s["price"]
    if setups:
        st = setups[-1]
        plan.update(setup=st["family"], setup_note=st["note"], trigger_level=st["level"],
                    invalidation=st["invalidation"], trigger_rule="completed 5m close (already met)",
                    state="READY" if "extended" not in st["note"] else "WAIT")
        if "extended" in st["note"]:
            plan["trigger_rule"] = f"pullback that holds {st['level']} on a 1m close"
    else:
        lv = s["levels"]
        if level is None:
            above = sorted(v for v in lv.values() if v > px)
            below = sorted((v for v in lv.values() if v < px), reverse=True)
            level = (above[0] if side == "C" else below[0]) if (above if side == "C" else below) else px
        lvl = float(level)
        if side == "C":
            met = px > lvl
            plan.update(trigger_rule=f"1m close above {lvl:.2f}", invalidation=round(lvl * (1 - 2 * BUF), 2))
        else:
            met = px < lvl
            plan.update(trigger_rule=f"1m close below {lvl:.2f}", invalidation=round(lvl * (1 + 2 * BUF), 2))
        plan.update(setup="LEVEL", setup_note=f"level {lvl:.2f}", trigger_level=round(lvl, 2),
                    state="READY" if met else "WAIT")
    if not sess["entries_allowed"]:
        plan["objections"].append(f"session: {sess['state']}")
        if plan["state"] == "READY":
            plan["state"] = "PASS" if sess["state"] in ("NO NEW ENTRIES", "ALL OUT", "AFTER HOURS") else "WAIT"
    block = event_block()
    if block:
        plan["objections"].append(block)
    bud = ledger_budget(ledger)
    plan["budget"] = bud
    if not broker.configured():
        plan.update(contract=None, contract_note="option quotes unavailable (no Alpaca keys)")
        return plan
    sz_grade = g if ledger == "paper" or g != "C" else "B"  # for Nick a C never blocks: small size (chop cap applies)
    c, why = pick_contract(ticker, side, px, bud["left"], sz_grade, chop or g == "C")
    if g == "C" and ledger != "paper":
        plan["objections"].append("grade C: small size / scalp only")
    if not c:
        plan.update(contract=None, contract_note=why)
        if plan["state"] == "READY":
            plan["state"] = "PASS"
            plan["reason"] = why
        return plan
    plan.update(contract={"symbol": c["symbol"], "label": occ_to_label(c["symbol"]), "bid": c["bid"],
                          "ask": c["ask"], "delta": c["delta"], "quote_ts": c["ts"], "feed": "indicative"},
                premium_limit=core.cents_up(c["ask"] + 0.02), exit=c["exit"], qty=c["qty"],
                risk_per_contract=c["risk_per_contract"], size_note=c["size_note"])
    if c["qty"] == 0 and plan["state"] == "READY":
        plan["state"] = "PASS"
        plan["reason"] = c["size_note"]
    return plan


# ======================= paper engine =======================
def paper_enabled():
    return store.kv_get("paper_enabled", True)


def paper_scan(ticker):
    s = snapshot(ticker)
    if not s.get("ok") or s["stale"]:
        return
    sess = core.session_info()
    for st in detect(s):
        oid = f"{sess['date']}-{ticker}-{st['family']}-{st['side']}-{st['bar'][11:16]}"
        if store.q("SELECT id FROM opportunities WHERE id=?", (oid,)):
            continue  # idempotent: each setup bar is considered once
        g, agree, against, chop = grade(s, st["side"])
        decision, reason, pid = "SKIP", None, None
        if not paper_enabled():
            reason = "paper entries paused"
        elif not sess["entries_allowed"]:
            reason = f"session {sess['state']}"
        elif "extended" in st["note"]:
            reason = "extended: waiting for retest (no chase)"
        elif len(store.positions(ledger="paper", status="OPEN")) >= core.policy()["risk"]["max_open_positions"]:
            reason = "max open paper positions"
        else:
            reason = discipline_gate("paper", g) or event_block()
            if chop and not reason:
                day = sess["date"]
                n = len(store.positions(ledger="paper", day=day))
                if n >= core.policy()["discipline"]["chop_day_max_trades"]:
                    reason = "chop day: max trades reached"
        if not reason:
            bud = ledger_budget("paper")
            c, why = pick_contract(ticker, st["side"], s["price"], bud["left"], g, chop)
            if not c:
                reason = why
            elif g == "C" or c["qty"] == 0:
                decision, reason = "WATCH", c.get("size_note") or "grade C: watch only"
            else:
                pid = open_paper(ticker, st, g, c, oid, s)
                decision = "ORDER" if pid else "ERROR"
                reason = None if pid else "order failed"
        store.x("INSERT INTO opportunities(id,date,ts,ticker,side,setup,grade,decision,reason,data) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (oid, sess["date"], store.ts(), ticker, st["side"], st["family"], g, decision, reason,
                 json.dumps({"setup": st, "agree": agree, "against": against, "chop": chop, "position": pid})))
        store.event("opportunity", f"PAPER {decision}: {ticker} {st['family']} {'calls' if st['side']=='C' else 'puts'} ({g})"
                    + (f" | {reason}" if reason else ""), "paper", oid)


def open_paper(ticker, st, g, c, oid, s):
    o, err = broker.submit(c["symbol"], c["qty"], "buy", oid)
    if not o:
        store.event("error", f"PAPER ORDER FAILED {c['symbol']}: {err}", "paper", oid)
        return None
    pid = "PP-" + oid
    t = core.hm(core.now_et())
    plan = dict(c["exit"], stop=c["exit"]["stop"], invalidation=st["invalidation"], be_hit=False, t1_done=False,
                trail=None, last_bid=None, order_in=o.get("id"), entry_quote={"bid": c["bid"], "ask": c["ask"]})
    store.x("INSERT INTO orders(client_id,position_id,ts,side,qty,status,broker_id,reason) VALUES(?,?,?,?,?,?,?,?)",
            (oid, pid, store.ts(), "buy", c["qty"], "ACKNOWLEDGED", o.get("id"), st["family"]))
    store.pos_save({"id": pid, "ledger": "paper", "date": core.now_et().strftime("%Y-%m-%d"), "ticker": ticker,
                    "contract": occ_to_label(c["symbol"]), "symbol": c["symbol"], "side": st["side"],
                    "qty_init": c["qty"], "qty_open": c["qty"], "fill": c["ask"], "opened": store.ts(),
                    "closed": None, "status": "PENDING", "setup_id": oid, "grade": g, "setup": st["family"],
                    "plan": plan, "realized": 0, "mfe": 0, "mae": 0, "policy_version": core.policy()["version"],
                    "verified": "paper-broker", "notes": st["note"]})
    store.event("paper_open", f"PAPER BUY {c['qty']} {ticker} {occ_to_label(c['symbol'])} ~${c['ask']:.2f} ({g}, {st['family']})",
                "paper", pid)
    return pid


def reconcile_paper():
    """Confirm fills / unknown orders with the broker before doing anything else."""
    for o in store.q("SELECT * FROM orders WHERE status IN ('ACKNOWLEDGED','SUBMITTING','UNKNOWN','PARTIAL')"):
        b, err = broker.order_by_client(o["client_id"])
        if not b:
            continue
        st = b.get("status")
        fq = int(float(b.get("filled_qty") or 0))
        fp = float(b["filled_avg_price"]) if b.get("filled_avg_price") else None
        new = {"filled": "FILLED", "partially_filled": "PARTIAL", "canceled": "CANCELED", "rejected": "REJECTED",
               "expired": "CANCELED"}.get(st, "ACKNOWLEDGED")
        store.x("UPDATE orders SET status=?, filled_qty=?, filled_price=? WHERE client_id=?", (new, fq, fp, o["client_id"]))
        p = store.pos_get(o["position_id"])
        if not p:
            continue
        if o["side"] == "buy" and new in ("FILLED", "PARTIAL") and fp:
            if p["status"] == "PENDING" or abs(p["fill"] - fp) > 1e-6:
                ex = core.exit_plan(fp, p["opened"][11:16], None)
                p["plan"].update({k: ex[k] for k in ("stop", "be_trigger", "be_stop", "t1", "t1_range", "lock_after_t1",
                                                      "gross_20pct_boundary", "slippage_reserve", "reward_risk_at_t1")})
                p.update(fill=fp, qty_init=fq, qty_open=fq, status="OPEN")
                store.pos_save(p)
                store.event("paper_fill", f"PAPER FILLED {fq} {p['ticker']} {p['contract']} @ ${fp:.2f} | stop ${ex['stop']:.2f} | BE at ${ex['be_trigger']:.2f} | T1 ${ex['t1']:.2f}", "paper", p["id"])
        elif o["side"] == "buy" and new in ("CANCELED", "REJECTED") and p["status"] == "PENDING":
            p["status"] = "CANCELED"
            store.pos_save(p)
            store.event("paper", f"PAPER ORDER {new}: {p['contract']}", "paper", p["id"])
        elif o["side"] == "sell" and new == "FILLED" and fp:
            done = store.q("SELECT data FROM events WHERE ref=? AND kind='sell_booked'", (o["client_id"],))
            if done:
                continue
            p["realized"] = round((p["realized"] or 0) + (fp - p["fill"]) * 100 * fq, 2)
            p["qty_open"] = max(0, p["qty_open"] - fq)
            if p["qty_open"] == 0:
                p.update(status="CLOSED", closed=store.ts())
            store.pos_save(p)
            store.event("sell_booked", f"PAPER SOLD {fq} {p['contract']} @ ${fp:.2f} ({o['reason']}) | P/L ${p['realized']:+.2f}", "paper", o["client_id"])


def _swing(b1, side):
    """Last confirmed 1m swing: higher low for calls / lower high for puts (needs the next bar closed)."""
    if len(b1) < 3:
        return None
    lows, highs = b1["Low"].values, b1["High"].values
    for i in range(len(b1) - 2, 0, -1):
        if side == "C" and lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            return float(lows[i])
        if side == "P" and highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            return float(highs[i])
    return None


def manage(p):
    """Exit precedence: session all-out > premium stop > underlying invalidation > flat timer > BE > T1 > trail."""
    pl = p["plan"]
    if pl.get("manual"):
        return  # watchlist ticker (earnings/swing): journal only, Nick manages it with Chart
    qd, err = broker.option_quote(p["symbol"]) if broker.configured() else (None, "no keys")
    now = core.hm(core.now_et())
    sess = core.session_info()
    s = snapshot(p["ticker"])
    b1 = bars1_done(s["m1"]) if s.get("ok") else None
    last_close = float(b1["Close"].iloc[-1]) if b1 is not None and len(b1) else None
    acts = []  # (kind, qty, reason)
    if not qd or qd["bid"] <= 0:
        if now >= sess["all_out"]:
            acts.append(("exit", p["qty_open"], "ALL OUT time (no quote)"))
        _note_once(p, "noquote", f"NO OPTION QUOTE for {p['contract']} ({err}); protection uses the underlying only")
    else:
        bid = qd["bid"]
        pl["last_bid"] = bid
        move = (bid - p["fill"]) / p["fill"] * 100
        p["mfe"], p["mae"] = round(max(p["mfe"] or 0, move), 1), round(min(p["mae"] or 0, move), 1)
        up = p["side"] == "C"
        inv_hit = last_close is not None and (last_close < pl["invalidation"] if up else last_close > pl["invalidation"])
        if now >= sess["all_out"]:
            acts.append(("exit", p["qty_open"], f"ALL OUT {sess['all_out']}"))
        elif bid <= pl["stop"]:
            acts.append(("exit", p["qty_open"], "BREAKEVEN STOP" if pl["be_hit"] else "STOP (20% cap)" if not pl["t1_done"] else "LOCKED-PROFIT STOP"))
        elif not pl["t1_done"] and inv_hit:
            acts.append(("exit", p["qty_open"], f"SETUP INVALIDATED (1m close {last_close:.2f} beyond {pl['invalidation']:.2f})"))
        elif not pl["be_hit"] and now >= pl["flat_by"] and bid < pl["be_trigger"]:
            acts.append(("exit", p["qty_open"], f"IF FLAT: not at breakeven by {pl['flat_by']}"))
        else:
            if not pl["be_hit"] and bid >= pl["be_trigger"]:
                pl["be_hit"] = True
                pl["stop"] = core.tighten_only(pl["stop"], pl["be_stop"])
                acts.append(("note", 0, f"BREAKEVEN: move stop to ${pl['stop']:.2f} (your fill)"))
            if not pl["t1_done"] and bid >= pl["t1"]:
                pl["t1_done"] = True
                pl["stop"] = core.tighten_only(pl["stop"], pl["lock_after_t1"])
                pl["trail"] = _swing(b1, p["side"]) if b1 is not None else None
                if p["qty_open"] >= 2:
                    acts.append(("exit", 1, f"T1 ${pl['t1']:.2f}: sell 1, stop on the rest to ${pl['stop']:.2f}"))
                else:
                    acts.append(("note", 0, f"T1 ${pl['t1']:.2f} hit: hold, stop up to ${pl['stop']:.2f}, trailing the 1m swing"))
            elif pl["t1_done"] and b1 is not None:
                sw = _swing(b1, p["side"])
                if sw is not None and (pl["trail"] is None or (sw > pl["trail"] if up else sw < pl["trail"])):
                    pl["trail"] = sw
                    acts.append(("note", 0, f"TRAIL: underlying stop now {sw:.2f} (1m {'higher low' if up else 'lower high'})"))
                if pl["trail"] is not None and last_close is not None and (last_close < pl["trail"] if up else last_close > pl["trail"]):
                    acts.append(("exit", p["qty_open"], f"TRAIL HIT: 1m close {last_close:.2f} through {pl['trail']:.2f}"))
    store.pos_save(p)
    for kind, qn, why in acts:
        if p["ledger"] == "paper":
            if kind == "exit" and qn > 0:
                pend = sum(o["qty"] for o in store.q(
                    "SELECT qty FROM orders WHERE position_id=? AND side='sell' AND status IN ('ACKNOWLEDGED','UNKNOWN','PARTIAL','SUBMITTING')", (p["id"],)))
                qn = min(qn, p["qty_open"] - pend)
                if qn <= 0:
                    continue  # never oversell: an exit is already working
                cid =f"{p['id']}-S-{why.split(':')[0][:12].replace(' ', '_')}-{qn}"
                if store.q("SELECT client_id FROM orders WHERE client_id=?", (cid,)):
                    continue
                o, e = broker.submit(p["symbol"], qn, "sell", cid)
                store.x("INSERT INTO orders(client_id,position_id,ts,side,qty,status,broker_id,reason) VALUES(?,?,?,?,?,?,?,?)",
                        (cid, p["id"], store.ts(), "sell", qn, "ACKNOWLEDGED" if o else "UNKNOWN", (o or {}).get("id"), why))
                store.event("paper_exit", f"PAPER SELL {qn} {p['contract']}: {why}" + ("" if o else f" | order error {e}"), "paper", p["id"])
            else:
                _note_once(p, why[:24], f"PAPER {p['contract']}: {why}")
        else:  # real: advisory only, Nick acts in Robinhood
            _note_once(p, why[:24], f"YOUR {p['ticker']} {p['contract']}: {why}" + (" -> do it in Robinhood, then log OUT" if kind == "exit" else " -> update your stop in Robinhood"), kind="real_alert")
    return acts


def _note_once(p, key, text, kind="note"):
    k = f"once:{p['id']}:{key}"
    if store.kv_get(k):
        return
    store.kv_set(k, True)
    store.event(kind, text, p["ledger"], p["id"])


# ======================= real trades (Nick reports) =======================
def log_real_in(ticker, contract, qty, fill, t=None, plan=None, setup=""):
    t = t or core.hm(core.now_et())
    side = contract[-1].upper()
    sym = f"{ticker.upper()}{core.now_et().strftime('%y%m%d')}{side}{int(round(float(contract[:-1]) * 1000)):08d}"
    inv = (plan or {}).get("invalidation")
    ex = core.exit_plan(fill, t, None)
    pid = store.new_id("R")
    pl = dict(ex, invalidation=inv if inv else (-1 if side == "C" else 1e9), be_hit=False, t1_done=False,
              trail=None, last_bid=None, plan_id=(plan or {}).get("id"))
    manual = ticker.upper() not in core.policy()["instruments"]
    if manual:
        pl["manual"] = True
    rpc = core.risk_per_contract(fill, ex["stop"], ex["slippage_reserve"])
    store.pos_save({"id": pid, "ledger": "real", "date": core.now_et().strftime("%Y-%m-%d"), "ticker": ticker.upper(),
                    "contract": contract.upper(), "symbol": sym, "side": side, "qty_init": qty, "qty_open": qty,
                    "fill": fill, "opened": store.ts(), "closed": None, "status": "OPEN",
                    "setup_id": (plan or {}).get("id"), "grade": (plan or {}).get("grade"), "setup": setup or (plan or {}).get("setup"),
                    "plan": pl, "realized": 0, "mfe": 0, "mae": 0, "policy_version": core.policy()["version"],
                    "verified": "reported by Nick", "notes": ""})
    risk = rpc * qty
    cap = core.per_trade_cap((plan or {}).get("grade", "B"), (plan or {}).get("chop_day", False))
    warn = ""
    if cap is not None and cap != float("inf") and risk > cap:
        warn = f" | OVER the ${cap:.0f} you can risk on this trade"
    streak_msg = discipline_gate("real", (plan or {}).get("grade", "B"))
    if streak_msg:
        warn += f" | {streak_msg}"
    if manual:
        store.event("real_in", f"LOGGED YOUR BUY {qty} {ticker.upper()} {contract.upper()} @ ${fill:.2f} | cost ${fill*100*qty:.0f} | "
                    f"STOP ${ex['stop']:.2f} (strict 20%, max planned loss ${risk:.2f}){warn} | BE at ${ex['be_trigger']:.2f} | "
                    f"journal only: the desk auto-manages SPY/QQQ 0DTE; ask Chart for the {ticker.upper()} exit plan | set your stop in Robinhood now", "real", pid)
        return pid
    store.event("real_in", f"LOGGED YOUR BUY {qty} {ticker.upper()} {contract.upper()} @ ${fill:.2f} | cost ${fill*100*qty:.0f} | "
                f"STOP ${ex['stop']:.2f} (max planned loss ${risk:.2f}){warn} | BE at ${ex['be_trigger']:.2f} -> stop to ${fill:.2f} | "
                f"T1 ${ex['t1']:.2f} | if flat exit by {ex['flat_by']} | all out {ex['all_out']} | set your stop in Robinhood now", "real", pid)
    return pid


def log_real_out(pid, qty, price):
    p = store.pos_get(pid)
    if not p or p["status"] != "OPEN":
        return "No open trade to close."
    qty = min(qty or p["qty_open"], p["qty_open"])
    pnl = round((price - p["fill"]) * 100 * qty, 2)
    p["realized"] = round((p["realized"] or 0) + pnl, 2)
    p["qty_open"] -= qty
    if p["qty_open"] == 0:
        p.update(status="CLOSED", closed=store.ts())
    store.pos_save(p)
    b = ledger_budget("real")
    return store.event("real_out", f"LOGGED YOUR SELL {qty} {p['contract']} @ ${price:.2f} | P/L ${pnl:+.2f} | "
                       f"{p['qty_open']} left | today ${b['realized_day']:+.2f}"
                       + (f" | {discipline_gate('real', 'B')}" if discipline_gate('real', 'B') and pnl < 0 else ""), "real", pid)


# ======================= watches =======================
def start_watch(plan, minutes=None):
    minutes = minutes or core.policy()["watch_default_min"]
    for w in store.q("SELECT id FROM watches WHERE status='ACTIVE' AND ticker=?", (plan["ticker"],)):
        store.x("UPDATE watches SET status='REPLACED' WHERE id=?", (w["id"],))
    wid = store.new_id("W")
    exp = (core.now_et() + timedelta(minutes=minutes)).isoformat(timespec="seconds")
    store.x("INSERT INTO watches(id,ticker,side,created,expires,status,plan,last_state) VALUES(?,?,?,?,?,?,?,?)",
            (wid, plan["ticker"], plan["side"], store.ts(), exp, "ACTIVE", json.dumps(plan, default=str), plan["state"]))
    store.event("watch", f"WATCHING {plan['ticker']} {'calls' if plan['side']=='C' else 'puts'} until {exp[11:16]} ET: {plan.get('trigger_rule','')}", "real", wid)
    return wid, exp


def stop_watch(ticker=None):
    rows = store.q("SELECT id,ticker FROM watches WHERE status='ACTIVE'" + (" AND ticker=?" if ticker else ""),
                   (ticker,) if ticker else ())
    for w in rows:
        store.x("UPDATE watches SET status='STOPPED' WHERE id=?", (w["id"],))
        store.event("watch", f"STOPPED WATCHING {w['ticker']} (paper engine keeps running)", "real", w["id"])
    return len(rows)


def check_watches():
    for w in store.q("SELECT * FROM watches WHERE status='ACTIVE'"):
        pl = json.loads(w["plan"])
        if core.now_et().isoformat() >= w["expires"]:
            store.x("UPDATE watches SET status='EXPIRED' WHERE id=?", (w["id"],))
            store.event("watch", f"WATCH EXPIRED {w['ticker']} at {w['expires'][11:16]}: no entry. Don't chase the old signal.", "real", w["id"])
            continue
        s = snapshot(w["ticker"])
        if not s.get("ok") or s["stale"]:
            if w["last_state"] != "DATA":
                store.x("UPDATE watches SET last_state='DATA' WHERE id=?", (w["id"],))
                store.event("watch", f"{w['ticker']} DATA STALE: watch paused until fresh bars", "real", w["id"])
            continue
        b1 = bars1_done(s["m1"])
        if not len(b1):
            continue
        c = float(b1["Close"].iloc[-1])
        up = pl["side"] == "C"
        lvl, inv = pl.get("trigger_level"), pl.get("invalidation")
        state = w["last_state"]
        if inv is not None and (c < inv if up else c > inv):
            new, text = "INVALIDATED", f"{w['ticker']} INVALIDATED: 1m close {c:.2f} beyond {inv:.2f}. No trade."
        elif lvl is not None and (c > lvl if up else c < lvl):
            new, text = "TRIGGER MET", f"{w['ticker']} TRIGGER MET at {b1.index[-1].strftime('%H:%M')} ET: 1m close {c:.2f} {'above' if up else 'below'} {lvl:.2f}"
            cq = pl.get("contract")
            if cq:
                qd, _ = broker.option_quote(cq["symbol"])
                if qd and pl.get("premium_limit") and qd["ask"] > pl["premium_limit"]:
                    new, text = "EXPIRED", f"{w['ticker']} ENTRY EXPIRED: {cq['label']} ask {qd['ask']:.2f} above your limit {pl['premium_limit']:.2f}. Don't chase."
                elif qd:
                    text += f" | {cq['label']} ask {qd['ask']:.2f} (limit {pl.get('premium_limit')}) (delayed quote) | real execution is yours"
        elif lvl is not None and abs(c - lvl) / lvl < 0.0005:
            new, text = "NEAR", f"{w['ticker']} at the level {lvl:.2f} (1m close {c:.2f}). Waiting for the close."
        else:
            new, text = state, None
        if new != state and text:
            store.x("UPDATE watches SET last_state=? WHERE id=?", (new, w["id"]))
            store.event("watch", text, "real", w["id"])
            if new in ("INVALIDATED", "EXPIRED"):
                store.x("UPDATE watches SET status=? WHERE id=?", (new, w["id"]))


# ======================= daily journal =======================
def day_summary(day=None):
    day = day or core.now_et().strftime("%Y-%m-%d")
    out = {"date": day}
    for led in ("real", "paper"):
        ps = [p for p in store.positions(ledger=led, day=day) if p["status"] in ("CLOSED", "OPEN")]
        closed = [p for p in ps if p["status"] == "CLOSED"]
        wins = [p["realized"] for p in closed if p["realized"] > 0]
        losses = [p["realized"] for p in closed if p["realized"] <= 0]
        out[led] = {"trades": len(ps), "closed": len(closed), "open": len(ps) - len(closed),
                    "realized": round(sum(p["realized"] or 0 for p in ps), 2),
                    "win_rate": round(100 * len(wins) / len(closed), 1) if closed else None,
                    "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
                    "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
                    "list": [{k: p[k] for k in ("id", "ticker", "contract", "qty_init", "fill", "realized", "status",
                                                "setup", "grade", "mfe", "mae", "opened", "closed")} for p in ps]}
    opp = store.q("SELECT decision, reason, setup, ticker, side, grade, ts FROM opportunities WHERE date=?", (day,))
    out["opportunities"] = opp
    out["no_trade_reason"] = None if out["paper"]["trades"] else (
        "no qualified setup" if not opp else "setups found but skipped: " + "; ".join(sorted({o['reason'] or o['decision'] for o in opp}))[:300])
    return out


# ======================= main tick =======================
_state = {"last_tick": None, "errors": 0, "last_error": None}


def tick():
    sess = core.session_info()
    try:
        if broker.configured():
            reconcile_paper()
        if sess["state"] in ("OPEN", "NO NEW ENTRIES", "ALL OUT", "ORB FORMING"):
            for t in core.policy()["instruments"]:
                if sess["entries_allowed"]:
                    paper_scan(t)
            for p in store.positions(status="OPEN"):
                manage(p)
            check_watches()
        if sess["time"] >= "16:05" and not store.kv_get(f"summary:{sess['date']}") and not sess["holiday"]:
            store.journal_set(sess["date"], summary=day_summary(sess["date"]))
            store.kv_set(f"summary:{sess['date']}", True)
            store.event("journal", f"Journal for {sess['date']} written (paper + real).", "", sess["date"])
        _state.update(last_tick=store.ts(), errors=0)
    except Exception as e:
        _state.update(errors=_state["errors"] + 1, last_error=f"{type(e).__name__}: {e}")
        if _state["errors"] in (1, 10):
            store.event("error", f"ENGINE ERROR: {_state['last_error']}")
    return _state
