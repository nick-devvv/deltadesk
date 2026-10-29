"""engine.py - v3 orchestrator: snapshot -> setups -> plans -> paper portfolios -> exits. No AI calls here.

Every number comes from marketdata.py (Schwab). Decisions happen once per finalized 1m bar, against ONE snapshot.
Portfolios: 'paper' = v3 main (4 ideas/day, streak stop, flat by 15:25), 'research' = v3 shadow that keeps
observing after the main limits (own ledger, own daily loss limit), 'old' = frozen old policy. 'real' = Nick's
reported trades: the desk only advises; it never places or infers a real fill.
Chart (Grok) only explains what this produces.
"""
import json
import re
import threading
from datetime import datetime, timedelta

import alerts
import core
import desk
import exits
import indicators as I
import marketdata
import optionmath
import paper
import policy_old
import store
import strategy

_cache = {}
_mx = threading.RLock()


# ======================= snapshot (shared by plans, paper, chart, Chart's context) =======================
def data_source():
    return marketdata.status()["live_label"]


def daily_from(m1):
    """Daily RTH bars built from the same 1m history (keeps one source for prior-day levels)."""
    if m1 is None or not len(m1):
        return None
    rows, idx = [], []
    for d in I.sessions(m1):
        r = I.rth(m1, d)
        if r is not None and len(r):
            rows.append({"Open": float(r["Open"].iloc[0]), "High": float(r["High"].max()), "Low": float(r["Low"].min()),
                         "Close": float(r["Close"].iloc[-1]), "Volume": float(r["Volume"].sum())})
            idx.append(datetime.combine(d, datetime.min.time()))
    import pandas as pd
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx)) if rows else None


class LazyRead(dict):
    """desk.read (trend / day type / EMAs for Chart's context and the old policy) computed only when first used."""

    def __init__(self, ticker, m1):
        super().__init__()
        self._t, self._m1, self._done, self.extra = ticker, m1, False, {}

    def _load(self):
        if not self._done:
            self._done = True
            d = daily_from(self._m1)
            try:
                rd = desk.read(self._t, self._m1.copy(), d.copy()) if d is not None and len(d) >= 2 else {}
            except Exception as e:
                rd = {"error": f"read failed: {type(e).__name__}"}
            super().update({k: v for k, v in rd.items() if not k.startswith("_")})
            super().update(self.extra)

    def __getitem__(self, k):
        self._load()
        return super().__getitem__(k)

    def get(self, k, d=None):
        self._load()
        return super().get(k, d)

    def items(self):
        self._load()
        return super().items()

    def keys(self):
        self._load()
        return super().keys()

    def __iter__(self):
        self._load()
        return super().__iter__()

    def __len__(self):
        self._load()
        return super().__len__()


def snapshot(ticker, max_age=3):
    with _mx:
        hit = _cache.get(ticker)
        if hit and (core.now_et() - hit["_at"]).total_seconds() < max_age:
            return hit
    m1, forming, meta = marketdata.bars(ticker)
    last_open = m1.index[-1] if m1 is not None and len(m1) else None
    with _mx:
        prev = _cache.get(ticker)
    if prev and prev.get("_bar") == last_open and last_open is not None:
        s = dict(prev, _at=core.now_et(), meta=meta, forming=forming)
        q = marketdata.quote(ticker)
        s.update(quote=q, price=(q or {}).get("last") or s.get("price"), bar_age_s=meta.get("bar_age_s"))
        with _mx:
            _cache[ticker] = s
        return s
    v3 = strategy.build_snapshot(ticker, m1, meta) if m1 is not None else {"ok": False, "reason": meta.get("error"), "meta": meta}
    s = {"ticker": ticker, "_at": core.now_et(), "_bar": last_open, "ok": bool(v3.get("ok")), "v3": v3, "meta": meta, "m1": m1,
         "forming": forming, "snap_id": store.new_id(f"S-{ticker}")}
    if m1 is None or not len(m1):
        s.update(ok=False, error=meta.get("error", "no data"), stale=True, bar_age_s=None, price=None, read={}, levels={})
    else:
        q = marketdata.quote(ticker)
        s.update(read=LazyRead(ticker, m1),
                 levels={k: v["value"] for k, v in (v3.get("levels") or {}).items()},
                 levels_full=v3.get("levels") or {},
                 price=(q or {}).get("last") or float(m1["Close"].iloc[-1]), price_src=(q or {}).get("src", meta.get("provider")),
                 quote=q, bar_age_s=meta.get("bar_age_s"), ok=bool(v3.get("ok") or len(m1)),
                 regime=(v3.get("regime") or {}).get("label"))
        st = core.session_info()["state"]
        s["stale"] = (meta.get("bar_age_s") or 0) > core.policy()["data"]["max_bar_age_s"] and st in (
            "OPEN", "ORB FORMING", "NO NEW ENTRIES", "ALL OUT")
        s["read"].extra = {"regime": s["regime"], "data": {"provider": meta.get("provider"), "executable": meta.get("executable"),
                                                           "bar_age_s": meta.get("bar_age_s")}}
    with _mx:
        _cache[ticker] = s
    return s


def occ_to_label(sym):
    return f"{int(sym[-8:]) / 1000:g}{sym[-9]}"


def chain_rows(ticker, side):
    exp = core.now_et().strftime("%Y-%m-%d")
    try:
        rows, err = marketdata.provider().chain(ticker, side, exp)
    except Exception as e:
        rows, err = None, type(e).__name__
    return rows or [], err


# ======================= options chain view (read-only; Nick buys in Robinhood) =======================
_chain_cache, _chain_mx = {}, threading.Lock()


def option_chain(ticker, side, exp=None, n=10, max_age=12):
    ticker, side = ticker.upper(), ("C" if side.upper().startswith("C") else "P")
    key = (ticker, side, exp, n)
    with _chain_mx:
        hit = _chain_cache.get(key)
        if hit and (core.now_et() - hit["_at"]).total_seconds() < max_age:
            return hit
    today = core.now_et().date()
    first = exp or today.isoformat()
    through = None if exp else (today + timedelta(days=21)).isoformat()
    p = marketdata.provider()
    try:
        rows, err = p.chain(ticker, side, first, through)
    except Exception as e:
        rows, err = None, type(e).__name__
    if not rows:
        return {"ticker": ticker, "side": side, "rows": [], "expiries": [], "error": err or "no option data", "_at": core.now_et(),
                "feed": p.name}
    expiries = sorted({r.get("exp") or first for r in rows})
    use = exp if exp in expiries else expiries[0]
    rows = [r for r in rows if (r.get("exp") or first) == use]
    q = marketdata.quote(ticker)
    spot = (q or {}).get("last")
    rows.sort(key=lambda r: r["strike"])
    if spot:
        rows = [r for r in rows if r["strike"] <= spot][-n:] + [r for r in rows if r["strike"] > spot][:n]
    cp = core.policy()["contract"]
    dte = (datetime.strptime(use, "%Y-%m-%d").date() - today).days
    out = []
    for r in rows:
        bid, ask = r.get("bid") or 0, r.get("ask") or 0
        mark = round((bid + ask) / 2, 2) if ask else None
        d, dsrc = r.get("delta"), None
        if d is None and r.get("iv") and spot:
            d, dsrc = core.bs_delta(spot, r["strike"], r["iv"], side), "est"
        be = (r["strike"] + mark if side == "C" else r["strike"] - mark) if mark is not None else None
        spread = (ask - bid) / ask if ask else None
        ref = r.get("last") or mark
        chg = round((ref - r["prev"]) / r["prev"] * 100, 1) if ref and r.get("prev") else None
        fits = bool(ask and bid > 0 and cp["premium_min"] <= ask <= cp["premium_max"] and spread is not None
                    and spread <= cp["max_spread_pct"] and d is not None and cp["abs_delta_min"] <= abs(d) <= cp["abs_delta_max"])
        out.append({"symbol": r["symbol"], "label": occ_to_label(r["symbol"]), "strike": r["strike"], "bid": bid, "ask": ask,
                    "mark": mark, "delta": round(d, 2) if d is not None else None, "delta_src": dsrc,
                    "iv": round(r["iv"] * 100, 1) if r.get("iv") else None, "breakeven": round(be, 2) if be is not None else None,
                    "to_be_pct": round((be - spot) / spot * 100, 2) if be is not None and spot else None,
                    "chg_pct": chg, "volume": r.get("volume"), "oi": r.get("oi"),
                    "spread_pct": round(spread * 100, 1) if spread is not None else None,
                    "itm": bool(spot and (r["strike"] < spot if side == "C" else r["strike"] > spot)), "fits": fits})
    res = {"ticker": ticker, "side": side, "exp": use, "dte": dte, "expiries": expiries, "spot": spot, "feed": p.name,
           "executable": p.executable, "rows": out, "fetched": core.now_et().isoformat(timespec="seconds"), "_at": core.now_et()}
    with _chain_mx:
        _chain_cache[key] = res
    return res


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
        stop = pl.get("premium_stop", pl.get("stop", p["fill"]))
        open_risk += max(0.0, (mark - stop) * 100 * p["qty_open"])
    left, day_left, week_left = core.budget_left(r_day, unreal, open_risk, r_week)
    if ledger == "research":
        lim = core.policy()["v3"]["research"]["daily_loss_usd"]
        rl = lim + r_day + unreal - open_risk
        left = max(0.0, rl) if left is None else min(left, max(0.0, rl))
    return {"realized_day": r_day, "realized_week": r_week, "unrealized": round(unreal, 2),
            "open_risk": round(open_risk, 2), "left": left, "day_left": day_left, "week_left": week_left,
            "trades_today": n_day}


def discipline_gate(ledger, grade_):
    """Streak rules read from configuration: A setups only after N losses in a row (+ cooldown), stop for the
    day after M. Main paper adds the 4-ideas/day cap (enforced atomically at reservation)."""
    d = core.policy()["discipline"]
    day = core.now_et().strftime("%Y-%m-%d")
    led = ledger if ledger in ("paper", "research", "old", "real") else "real"
    s = paper.streak(led, day)
    closed = sorted([p for p in store.positions(ledger=led, day=day) if p["status"] == "CLOSED"], key=lambda p: p["closed"] or "")
    if s >= d.get("stop_day_after_consecutive_losses", 99):
        return f"STOP FOR TODAY: {s} losses in a row"
    if ledger == "real" and len(store.positions(ledger="real", day=day)) >= d["max_trades_day"]:
        return f"max {d['max_trades_day']} trades today reached"
    if s >= d["a_only_after_consecutive_losses"] and grade_ != "A":
        return f"A setups only now ({s} losses in a row)"
    if closed and (closed[-1]["realized"] or 0) < 0 and closed[-1]["closed"]:
        last = datetime.fromisoformat(closed[-1]["closed"])
        if core.now_et() - last < timedelta(minutes=d["cooldown_min_after_loss"]):
            return f"cooldown {d['cooldown_min_after_loss']} min after a loss"
    return None


def event_block():
    e = strategy.event_state()
    if e["state"] in ("pre-event", "shock"):
        return f"EVENT: {e['event']['name']} at {e['event']['time']} ET ({e['state']}, no new entries {core.policy()['discipline']['event_block_min']} min around it)"
    return None


# ======================= plans (chat, watches, alerts) =======================
def build_plan(ticker, side, level=None, mode="check", ledger="real"):
    """Complete conditional plan with evidence. state: WAIT / READY / PASS / DATA UNAVAILABLE."""
    ticker, side = ticker.upper(), side.upper()[:1]
    up = side == "C"
    s = snapshot(ticker)
    v3 = s.get("v3") or {}
    sess = core.session_info()
    plan = {"id": store.new_id(f"P-{ticker}"), "ticker": ticker, "side": side, "mode": mode, "created": store.ts(),
            "policy_version": core.policy()["version"], "session": sess,
            "snap": {"id": s.get("snap_id"), "price": s.get("price"), "price_src": s.get("price_src"), "bar_age_s": s.get("bar_age_s")},
            "data": {k: (s.get("meta") or {}).get(k) for k in ("provider", "executable", "bar_age_s", "gaps_rth_today")},
            "objections": [], "support": [], "regime": (v3.get("regime") or {}).get("label"),
            "regime_evidence": (v3.get("regime") or {}).get("evidence")}
    if not v3.get("ok"):
        plan.update(state="DATA UNAVAILABLE", reason=v3.get("reason") or s.get("error") or "no data")
        return plan
    if s.get("stale"):
        plan.update(state="DATA UNAVAILABLE", reason=f"bars {s.get('bar_age_s')}s old")
        return plan
    cands = [c for c in strategy.detect_all(v3) if c["side"] == side]
    ideas, _ = strategy.arbitrate(cands)
    z, buf, px = v3["zone"], v3["buf"], v3["close1"]
    if ideas:
        idea = ideas[0]
        plan.update(setup=idea["family"], tags=idea.get("tags"), entry_mode=idea.get("entry_mode"),
                    setup_note=idea["confirm_rule"], trigger_level=idea["level"], invalidation=idea["invalidation"],
                    trigger_rule="confirmed candle close (already met)", state="READY", evidence=idea["evidence"])
    else:
        lvls = v3["levels"]
        if level is None:
            vals = sorted((v["value"], k) for k, v in lvls.items() if k != "PDC")
            pick = [x for x in vals if x[0] > px] if up else [x for x in reversed(vals) if x[0] < px]
            level, lname = (pick[0] if pick else (px, "price"))
        else:
            lname = "your level"
        lvl = float(level)
        inv = lvl - z - buf if up else lvl + z + buf
        met = (px > lvl + z) if up else (px < lvl - z)
        idea = {"family": "LEVEL", "side": side, "level": lvl, "level_name": lname, "invalidation": round(inv, 2),
                "confirm_rule": f"1m close {'above' if up else 'below'} {lvl:.2f} (+zone {z:.2f})", "evidence": {"level": lname},
                "kind": "continuation", "bar": v3["t"].isoformat()}
        plan.update(setup="LEVEL", setup_note=f"{lname} {lvl:.2f}", trigger_level=round(lvl, 2), invalidation=round(inv, 2),
                    trigger_rule=idea["confirm_rule"], state="READY" if met else "WAIT", evidence=idea["evidence"])
    passed, obj, sup = strategy.qualify(idea, v3)
    plan["objections"] += obj
    plan["support"] += sup
    if not sess["entries_allowed"]:
        plan["objections"].append(f"session: {sess['state']}")
        if plan["state"] == "READY":
            plan["state"] = "PASS" if sess["state"] in ("NO NEW ENTRIES", "ALL OUT", "AFTER HOURS") else "WAIT"
    rows, err = chain_rows(ticker, side)
    bud = ledger_budget(ledger)
    plan["budget"] = bud
    tp, why, diag = optionmath.plan_trade(idea, v3, rows, "A", bud["left"], ledger)
    g, gp, gf = strategy.grade(idea, v3, tp["rr_option"] if tp else None)
    plan.update(grade=g, grade_passed=gp, grade_failed=gf, day=plan["regime"], chop_day=plan["regime"] == "range/chop",
                diagnostics=diag)
    if not tp:
        plan.update(contract=None, contract_note=why or err)
        if plan["state"] == "READY":
            plan["state"], plan["reason"] = "PASS", why
        return plan
    caps = min(core.policy()["sizing_by_grade"].get(g, 0), core.policy()["risk"]["max_contracts"])
    tp["qty"] = min(tp["qty"], caps) if g != "C" else (1 if ledger == "real" else 0)
    win = core.window_for(core.hm(core.now_et())) or core.policy()["windows"][-1]
    flat_by = (core.now_et() + timedelta(minutes=win["flat_min"])).strftime("%H:%M")
    t1_prem = round(tp["entry_premium_est"] + tp["gain_per_contract"] / 100, 2)
    plan.update(contract={"symbol": tp["symbol"], "label": tp["label"], "bid": tp["bid"], "ask": tp["ask"], "delta": tp["delta"],
                          "delta_src": tp["delta_src"], "quote_ts": tp.get("quote_ts"), "feed": tp.get("feed") or marketdata.provider().name,
                          "spread": tp["spread"]},
                premium_limit=tp["premium_limit"], qty=tp["qty"], risk_per_contract=tp["loss_per_contract"],
                size_note=tp.get("qty_note"),
                exit={"stop": tp["premium_stop"], "stop_px": tp["stop_px"], "stop_pct": core.policy()["risk"]["stop_cap_pct"],
                      "window": "v3 structural", "be_trigger": tp["be_trigger"], "be_stop": tp["breakeven_net"],
                      "t1": t1_prem, "t1_name": tp["t1"], "t1_level": tp["t1_level"], "t1_px": tp["t1_px"],
                      "lock_after_t1": tp["breakeven_net"], "flat_by": flat_by, "all_out": sess["all_out"],
                      "rr_option": tp["rr_option"], "rr_underlying": tp["rr_underlying"], "loss_per_contract": tp["loss_per_contract"],
                      "gain_per_contract": tp["gain_per_contract"], "ceiling_per_contract": tp["ceiling_per_contract"],
                      "structural_premium_est": tp["structural_premium_est"], "model": tp["model"],
                      "stall_min": core.policy()["v3"]["exits"]["stall_min"]})
    if g == "C" and ledger != "paper":
        plan["objections"].append("grade C (failed: " + ", ".join(gf) + ")")
    if plan["state"] == "READY" and plan["objections"] and not passed:
        plan["state"], plan["reason"] = "PASS", "; ".join(obj[:2])
    return plan


def plan_brief(p):
    """One alert line with everything Nick needs."""
    c, ex = p["contract"], p["exit"]
    feed = "LIVE Schwab quote" if p.get("data", {}).get("executable") else "NOT executable data - check Legend"
    mode = f" ({p['entry_mode']})" if p.get("entry_mode") else ""
    return (f"{p['ticker']} {c['label']} 0DTE{mode} | buy at or under ${p['premium_limit']:.2f} ({feed}, bid {c['bid']:.2f}/ask {c['ask']:.2f}) | "
            f"size {p['qty']} | STOP: {p['ticker']} {'below' if p['side'] == 'C' else 'above'} {ex['stop_px']:.2f} (structure) "
            f"or ${ex['stop']:.2f} premium (20% ceiling) | T1 {ex['t1_name']} {ex['t1_level']:.2f} (~${ex['t1']:.2f}, model) | "
            f"R/R {ex['rr_underlying']} stock, {ex['rr_option']} option | BE at ${ex['be_trigger']:.2f} -> ${ex['be_stop']:.2f} | "
            f"stall exit {ex['stall_min']} min if green | all out {ex['all_out']} | {p.get('setup')}: {p.get('setup_note')}")


QUIET = re.compile(r"extended|cooldown|session|EVENT|STOP FOR TODAY|A setups only|max \d+ trades|daily cap|chop", re.I)


def setup_alert(ticker, idea, plan):
    """Alert Nick only when he could actually take it: A/B, his rules allow it, full plan with a contract."""
    if plan.get("grade") not in ("A", "B") or plan.get("state") not in ("READY",) or not plan.get("contract") or not plan.get("qty"):
        return False
    gate = discipline_gate("real", plan["grade"])
    if gate:
        return False
    k = f"setup_last:{ticker}:{idea['side']}"
    last = store.kv_get(k)
    if last and (core.now_et() - datetime.fromisoformat(last["at"])).total_seconds() < 600 and not (plan["grade"] == "A" and last.get("g") != "A"):
        return False
    store.kv_set("last_plan", plan)
    if not store.q("SELECT id FROM watches WHERE status='ACTIVE' AND ticker=?", (ticker,)):
        try:
            wid, exp = start_watch(plan, None)
            plan["watch"] = {"id": wid, "until": exp[11:16]}
        except Exception:
            pass
    st = {"family": idea["family"], "side": idea["side"], "note": idea["confirm_rule"], "level": idea["level"] or 0,
          "invalidation": idea["invalidation"], "bar": idea["bar"]}
    ok = alerts.setup(ticker, st, plan["grade"], "ALERT", None, brief=plan_brief(plan))
    if ok:
        store.kv_set(k, {"at": core.now_et().isoformat(), "g": plan["grade"]})
        store.event("desk", f"ALERT PLAN ({plan['grade']}) " + plan_brief(plan).replace(" | ", "\n"), "real", plan.get("id"))
    return ok


# ======================= v3 paper portfolios =======================
def paper_enabled():
    return store.kv_get("paper_enabled", True)


def _record(cid, sess, idea, portfolio, decision, reasons, limit, plan, provider_name):
    store.x("INSERT OR REPLACE INTO candidates(id,date,ts,decision_t,ticker,side,family,tags,portfolio,decision,reasons,limit_blocked,evidence,plan,policy_version,provider,outcome) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, sess["date"], store.ts(), idea.get("decision_t") or idea.get("bar"), idea.get("ticker") or "", idea["side"], idea["family"],
             ",".join(idea.get("tags") or [idea["family"]]), portfolio, decision, json.dumps(reasons), limit,
             json.dumps(idea.get("evidence"), default=str), json.dumps(plan, default=str) if plan else None,
             core.policy()["version"], provider_name, None))


def paper_scan(ticker):
    s = snapshot(ticker)
    v3 = s.get("v3") or {}
    if not v3.get("ok"):
        return
    t = v3["t"].isoformat()
    if store.kv_get(f"decided:{ticker}") == t:
        return                                # this finalized bar was already decided (restart/retry safe)
    store.kv_set(f"decided:{ticker}", t)
    sess = core.session_info()
    t_data = marketdata.now()
    cands = strategy.detect_all(v3)
    for c in cands:
        c["ticker"] = ticker
    ideas, skipped = strategy.arbitrate(cands)
    pname = (s.get("meta") or {}).get("provider")
    if skipped:
        for c in cands:
            _record(f"conflict-{ticker}-{t}-{c['family']}-{c['side']}", sess, c, "research", "SKIP-CONFLICT",
                    [skipped["reason"]], None, None, pname)
        store.event("opportunity", f"SKIPPED BAR {ticker} {t[11:16]}: {skipped['reason']} ({', '.join(skipped['candidates'])})", "paper", t)
        return
    for idea in ideas:
        idea["ticker"] = ticker
        passed, obj, sup = strategy.qualify(idea, v3)
        rows, err = chain_rows(ticker, idea["side"])
        tp, why, diag = optionmath.plan_trade(idea, v3, rows, "A", None)
        g, gp, gf = strategy.grade(idea, v3, tp["rr_option"] if tp else None)
        base = list(obj) + ([why] if not tp else [])
        if g == "C":
            base.append("grade C (failed: " + ", ".join(gf) + ")")
        idea_id = idea.get("idea_hint") or f"{sess['date']}-{ticker}-{idea['side']}-{idea['family']}-{idea['bar'][11:16]}"
        plan = dict(tp or {}, family=idea["family"], entry_mode=idea.get("entry_mode"), grade=g, evidence_rule=idea["confirm_rule"])
        if tp:
            win = core.window_for(core.hm(core.now_et())) or core.policy()["windows"][-1]
            plan["flat_by"] = (core.now_et() + timedelta(minutes=win["flat_min"])).strftime("%H:%M")
        marketdata.record_latency("signal", (marketdata.now() - (v3["t"])).total_seconds())
        for pf in ("paper", "research"):
            if pf == "research" and not core.policy()["v3"]["research"]["enabled"]:
                continue
            reasons, limit = list(base), None
            if not sess["entries_allowed"]:
                reasons.append(f"session {sess['state']}")
            if pf == "paper" and not paper_enabled():
                limit = "paper entries paused"
            gate = discipline_gate(pf, g)
            if gate and pf == "paper":
                limit = gate
            elif gate and pf == "research" and not gate.startswith(("STOP FOR TODAY", "A setups only", "cooldown")):
                limit = gate
            if pf == "research" and gate:
                plan.setdefault("research_note", f"main would be blocked: {gate}")
            opens = store.positions(ledger=pf, status="OPEN")
            if len(opens) >= core.policy()["risk"]["max_open_positions"]:
                limit = limit or "max open positions"
            same_dir = [p for p in opens if p["side"] == idea["side"]]
            if len(same_dir) >= core.policy()["v3"]["limits"]["max_same_direction_open"]:
                limit = limit or f"already {'long calls' if idea['side'] == 'C' else 'long puts'} on {same_dir[0]['ticker']} (correlated SPY/QQQ exposure)"
            cd = _setup_cooldown(pf, ticker, idea)
            if cd:
                limit = limit or cd
            decision, pid = "SKIP", None
            if not reasons and not limit:
                bud = ledger_budget(pf)
                qty_plan, _, _ = optionmath.plan_trade(idea, v3, rows, g, bud["left"], pf)
                qty = (qty_plan or {}).get("qty", 0)
                if qty <= 0:
                    reasons.append((qty_plan or {}).get("qty_note") or "size 0")
                else:
                    cap = core.policy()["v3"]["limits"]["main_ideas_per_day"] if pf == "paper" else None
                    ok, rwhy = paper.reserve_idea(pf, idea_id, ticker, idea["side"], cap)
                    if not ok:
                        limit = rwhy
                    else:
                        pid, bwhy = paper.buy(pf, idea_id, ticker, idea["side"], dict(plan, **{k: qty_plan[k] for k in ("premium_limit",)}),
                                              qty, t)
                        if pid:
                            decision = "ORDER"
                        else:
                            paper.release_idea(pf, idea_id, bwhy)
                            reasons.append(bwhy)
            elif not reasons and limit:
                decision = "BLOCKED-LIMIT"
            _record(f"{pf}-{idea_id}", sess, idea, pf, decision, reasons, limit, plan if tp else {"diagnostics": diag}, pname)
            if pf == "paper":
                txt = (f"PAPER {decision}: {ticker} {idea['family']}{' (' + idea['entry_mode'] + ')' if idea.get('entry_mode') else ''} "
                       f"{'calls' if idea['side'] == 'C' else 'puts'} ({g})")
                if decision != "ORDER":
                    txt += " | " + "; ".join((reasons + ([limit] if limit else []))[:3])
                store.event("opportunity", txt, "paper", idea_id)
        # Nick's alert (same plan, his own discipline)
        try:
            p_real = build_plan(ticker, idea["side"], idea["level"], "watch")
            if p_real.get("setup") == idea["family"]:
                setup_alert(ticker, idea, p_real)
        except Exception:
            pass


def _setup_cooldown(pf, ticker, idea):
    """A new entry on the same ticker+side needs a fresh setup after the cooldown (requalification)."""
    m = core.policy()["discipline"].get("setup_cooldown_min", 20)
    since = (core.now_et() - timedelta(minutes=m)).isoformat(timespec="seconds")
    hit = store.q("SELECT created FROM ideas WHERE portfolio=? AND ticker=? AND side=? AND status='FILLED' AND created>=? ORDER BY created DESC LIMIT 1",
                  (pf, ticker, idea["side"], since))
    return f"cooldown: {ticker} {'calls' if idea['side'] == 'C' else 'puts'} already entered at {hit[0]['created'][11:16]} ({m} min)" if hit else None


# ======================= real trades (Nick reports) =======================
def log_real_in(ticker, contract, qty, fill, t=None, plan=None, setup=""):
    t = t or core.hm(core.now_et())
    side = contract[-1].upper()
    sym = f"{ticker.upper()}{core.now_et().strftime('%y%m%d')}{side}{int(round(float(contract[:-1]) * 1000)):08d}"
    pid = store.new_id("R")
    manual = ticker.upper() not in core.policy()["instruments"]
    p = core.policy()
    fee = p["v3"]["contract"]["fees_per_contract_side"]
    ex = (plan or {}).get("exit") or {}
    same = plan and (plan.get("contract") or {}).get("label", "").upper() == contract.upper()
    prem_stop = core.cents_up(fill * (1 - p["risk"]["stop_cap_pct"]) + 0.01 + 2 * fee / 100)
    st = {"v": 3, "symbol": sym, "entry_premium": fill, "fees_side": fee, "premium_stop": prem_stop,
          "stop_px": ex.get("stop_px") if same else None, "t1": ex.get("t1_name") if same else None,
          "t1_level": ex.get("t1_level") if same else None, "t1_px": ex.get("t1_px") if same else None,
          "be_trigger": core.cents_up(fill * (1 + p["v3"]["exits"]["be_trigger_pct"]) + 2 * fee / 100),
          "breakeven_net": core.cents_up(fill + 2 * fee / 100), "high_water": fill, "high_water_t": store.ts(),
          "last_progress_t": store.ts(), "be_hit": False, "lock_hit": False, "t1_done": False, "runner": False, "trail": None,
          "last_bid": None, "plan_id": (plan or {}).get("id"), "family": (plan or {}).get("setup") if same else None,
          "qualified": bool(same and (plan or {}).get("state") == "READY" and (plan or {}).get("grade") in ("A", "B")),
          "stops": [{"t": store.ts(), "stop": prem_stop, "by": "desk", "why": "20% ceiling on your reported fill"}],
          "actions_done": [], "flat_by": (datetime.strptime(t, "%H:%M") + timedelta(minutes=(core.window_for(t) or p["windows"][-1])["flat_min"])).strftime("%H:%M")}
    if manual:
        st["manual"] = True
    store.pos_save({"id": pid, "ledger": "real", "date": core.now_et().strftime("%Y-%m-%d"), "ticker": ticker.upper(),
                    "contract": contract.upper(), "symbol": sym, "side": side, "qty_init": qty, "qty_open": qty, "fill": fill,
                    "opened": store.ts(), "closed": None, "status": "OPEN", "setup_id": (plan or {}).get("id"),
                    "grade": (plan or {}).get("grade") if same else None, "setup": st["family"] or setup or "no qualified setup",
                    "plan": st, "realized": 0, "mfe": 0, "mae": 0, "policy_version": p["version"],
                    "verified": "reported by Nick", "notes": ""})
    risk = round((fill - prem_stop) * 100 * qty + 2 * fee * qty, 2)
    warn = ""
    gate = discipline_gate("real", (plan or {}).get("grade", "B"))
    if gate:
        warn += f" | {gate}"
    if not st["qualified"]:
        warn += " | NOT a qualified desk setup (no complete plan for this contract): treat it as a chase"
    if manual:
        store.event("real_in", f"LOGGED YOUR BUY {qty} {ticker.upper()} {contract.upper()} @ ${fill:.2f} | cost ${fill*100*qty:.0f} | "
                    f"STOP ${prem_stop:.2f} (20% ceiling, max planned loss ${risk:.2f}){warn} | journal only: ask Chart for the "
                    f"{ticker.upper()} exit plan | set your stop in Robinhood now", "real", pid)
        return pid
    struct = (f"STOP: {ticker.upper()} 1m close {'below' if side == 'C' else 'above'} {st['stop_px']:.2f} (structure) or ${prem_stop:.2f} premium"
              if st["stop_px"] else f"STOP ${prem_stop:.2f} premium (20% ceiling; no structural level from a plan)")
    t1 = f"T1 {st['t1']} {st['t1_level']:.2f}: {'sell 1, keep the rest only on a clean break' if qty >= 2 else 'full exit'}" if st["t1"] else "no level T1 (no plan)"
    store.event("real_in", f"LOGGED YOUR BUY {qty} {ticker.upper()} {contract.upper()} @ ${fill:.2f} | cost ${fill*100*qty:.0f} | "
                f"{struct}, max planned loss ${risk:.2f}{warn} | BE at ${st['be_trigger']:.2f} -> stop to ${st['breakeven_net']:.2f} | {t1} | "
                f"green but stalled {p['v3']['exits']['stall_min']} min or MACD turns -> out | all out {core.session_info()['all_out']} | "
                f"set your stop in Robinhood now. The desk watches it and tells you each step.", "real", pid)
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
    gate = discipline_gate("real", "B")
    return store.event("real_out", f"LOGGED YOUR SELL {qty} {p['contract']} @ ${price:.2f} | P/L ${pnl:+.2f} | "
                       f"{p['qty_open']} left | today ${b['realized_day']:+.2f}" + (f" | {gate}" if gate and pnl < 0 else ""), "real", pid)


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
    rows = store.q("SELECT id,ticker FROM watches WHERE status='ACTIVE'" + (" AND ticker=?" if ticker else ""), (ticker,) if ticker else ())
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
        v3 = s.get("v3") or {}
        if not v3.get("ok") or s.get("stale"):
            if w["last_state"] != "DATA":
                store.x("UPDATE watches SET last_state='DATA' WHERE id=?", (w["id"],))
                store.event("watch", f"{w['ticker']} DATA STALE: watch paused until fresh bars", "real", w["id"])
            continue
        c = v3["close1"]
        up = pl["side"] == "C"
        lvl, inv = pl.get("trigger_level"), pl.get("invalidation")
        z = v3["zone"]
        state = w["last_state"]
        if inv is not None and (c < inv if up else c > inv):
            new, text = "INVALIDATED", f"{w['ticker']} INVALIDATED: 1m close {c:.2f} beyond {inv:.2f}. No trade."
        elif lvl is not None and (c > lvl + z if up else c < lvl - z):
            new, text = "TRIGGER MET", f"{w['ticker']} TRIGGER MET {v3['last_open'].strftime('%H:%M')} ET: 1m close {c:.2f} {'above' if up else 'below'} {lvl:.2f}"
            cq = pl.get("contract")
            if cq:
                qd, _ = marketdata.option_quote(cq["symbol"])
                if qd and pl.get("premium_limit") and qd.get("ask") and qd["ask"] > pl["premium_limit"]:
                    new, text = "EXPIRED", f"{w['ticker']} ENTRY EXPIRED: {cq['label']} ask {qd['ask']:.2f} above your limit {pl['premium_limit']:.2f}. Don't chase."
                elif qd and qd.get("ask"):
                    text += f" | {cq['label']} bid {qd['bid']:.2f} / ask {qd['ask']:.2f} ({'live' if qd.get('executable') else 'not executable'}) | real execution is yours"
        elif lvl is not None and abs(c - lvl) <= z:
            new, text = "NEAR", f"{w['ticker']} at the level {lvl:.2f} (1m close {c:.2f}). Waiting for the close."
        else:
            new, text = state, None
        if new != state and text:
            store.x("UPDATE watches SET last_state=? WHERE id=?", (new, w["id"]))
            store.event("watch", text, "real", w["id"])
            if new in ("INVALIDATED", "EXPIRED"):
                store.x("UPDATE watches SET status=? WHERE id=?", (new, w["id"]))


def kill_paper(reason="Nick pressed KILL"):
    """Kill switch (paper portfolios only): stop new paper entries and close every open paper/research position
    at the simulated bid (pending if no valid quote). Real trades are Nick's: the desk only reminds him."""
    store.kv_set("paper_enabled", False)
    closed = 0
    for led in ("paper", "research"):
        for p in store.positions(ledger=led, status="OPEN"):
            n, _ = paper.sell(p, p["qty_open"], "KILL SWITCH")
            closed += 1 if n else 0
    n = stop_watch()
    real = len(store.positions(ledger="real", status="OPEN"))
    msg = f"KILL SWITCH: paper entries OFF, {closed} paper position(s) closed (simulated), {n} watch(es) stopped"
    if real:
        msg += f" | you have {real} real trade(s) open: close them yourself in Robinhood"
    store.event("paper", msg + f" ({reason})", "paper")
    return msg


# ======================= journal =======================
def day_summary(day=None):
    day = day or core.now_et().strftime("%Y-%m-%d")
    out = {"date": day, "policy_version": core.policy()["version"], "data": marketdata.status().get("live_label")}
    for led in ("real", "paper", "research", "old"):
        ps = [p for p in store.positions(ledger=led, day=day) if p["status"] in ("CLOSED", "OPEN")]
        closed = [p for p in ps if p["status"] == "CLOSED"]
        wins = [p["realized"] for p in closed if p["realized"] > 1]
        losses = [p["realized"] for p in closed if p["realized"] <= -1]
        out[led] = {"trades": len(ps), "closed": len(closed), "open": len(ps) - len(closed),
                    "realized": round(sum(p["realized"] or 0 for p in ps), 2),
                    "wins": len(wins), "losses": len(losses), "breakeven": len(closed) - len(wins) - len(losses),
                    "win_rate": round(100 * len(wins) / len(closed), 1) if closed else None,
                    "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
                    "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
                    "list": [{k: p[k] for k in ("id", "ticker", "contract", "qty_init", "fill", "realized", "status",
                                                "setup", "grade", "mfe", "mae", "opened", "closed")} for p in ps]}
    cand = store.q("SELECT portfolio, decision, reasons, limit_blocked, family, ticker, side, ts FROM candidates WHERE date=?", (day,))
    out["candidates"] = cand
    out["opportunities"] = [{"decision": c["decision"], "reason": "; ".join(json.loads(c["reasons"] or "[]")) or c["limit_blocked"],
                             "setup": c["family"], "ticker": c["ticker"], "side": c["side"], "ts": c["ts"]} for c in cand if c["portfolio"] == "paper"]
    out["no_trade_reason"] = None if out["paper"]["trades"] else ("no qualified setup" if not cand else "setups found but skipped (see candidates)")
    return out


# ======================= archive (for replay; never rewrites fills) =======================
def archive(ticker, m1):
    if m1 is None or not len(m1):
        return
    tail = m1.iloc[-5:]
    for ts, r in tail.iterrows():
        store.x("INSERT OR REPLACE INTO bars_archive(ticker,open,o,h,l,c,v,src) VALUES(?,?,?,?,?,?,?,?)",
                (ticker, ts.isoformat(), float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"]), float(r["Volume"]),
                 marketdata.provider().name))


def archive_quote(symbol, q):
    if not q:
        return
    store.x("INSERT OR IGNORE INTO quotes_archive(symbol,ts,bid,ask,last,delta,gamma,iv,quote_time,src) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (symbol, store.ts(), q.get("bid"), q.get("ask"), q.get("last"), q.get("delta"), q.get("gamma"), q.get("iv"),
             q["quote_time"].isoformat() if q.get("quote_time") is not None else None, q.get("src")))


# ======================= main tick =======================
_state = {"last_tick": None, "errors": 0, "last_error": None}


def tick():
    sess = core.session_info()
    try:
        if sess["state"] in ("OPEN", "NO NEW ENTRIES", "ALL OUT", "ORB FORMING"):
            for t in core.policy()["instruments"]:
                s = snapshot(t)
                archive(t, s.get("m1"))
                if sess["entries_allowed"]:
                    paper_scan(t)
                    if core.policy()["v3"]["old_policy_shadow"]["enabled"]:
                        try:
                            policy_old.scan(t, s, {"C": chain_rows(t, "C")[0], "P": chain_rows(t, "P")[0]})
                        except Exception as e:
                            _state["last_error"] = f"old shadow: {type(e).__name__}: {e}"
                try:
                    holding = any(p["ticker"] == t for p in store.positions(ledger="real", status="OPEN"))
                    v3 = s.get("v3") or {}
                    if v3.get("ok") and not s.get("stale") and (sess["entries_allowed"] or holding):
                        alerts.move_check(t, v3["b5"])
                except Exception:
                    pass
            want = []
            for p in store.positions(status="OPEN"):
                want.append(p["symbol"])
                s = snapshot(p["ticker"])
                if p["plan"].get("v") == 3:
                    exits.evaluate(p, s.get("v3") or {})
                else:
                    policy_old.manage(p, s, lambda sym: marketdata.option_quote(sym))
                q, _ = marketdata.option_quote(p["symbol"])
                archive_quote(p["symbol"], q)
            try:
                import schwab_stream
                schwab_stream.want_options(want)
            except Exception:
                pass
            check_watches()
        if sess["time"] >= "16:05" and not store.kv_get(f"summary:{sess['date']}") and not sess["holiday"]:
            store.journal_set(sess["date"], summary=day_summary(sess["date"]))
            store.kv_set(f"summary:{sess['date']}", True)
            todo = [p for p in store.positions(ledger="real", day=sess["date"]) if p["status"] == "CLOSED" and not (p.get("notes") or "").strip("{} ")]
            store.event("journal", f"Journal for {sess['date']} written (real, main paper, research, old policy)." +
                        (f" {len(todo)} of your trades need a quick review." if todo else ""), "", sess["date"])
        _state.update(last_tick=store.ts(), errors=0)
    except Exception as e:
        _state.update(errors=_state["errors"] + 1, last_error=f"{type(e).__name__}: {e}")
        if _state["errors"] in (1, 10):
            store.event("error", f"ENGINE ERROR: {_state['last_error']}")
    return _state
