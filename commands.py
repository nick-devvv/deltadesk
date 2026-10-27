"""commands.py - turns Nick's chat messages into actions. Standard commands are handled in code (no AI).

Only questions that need judgment ("why?", "what changed?", second opinions, a confirm explanation)
go to Chart, with a compact context built here.
"""
import json
import re

import core
import engine
import store
import watchlist

TICK = re.compile(r"\b(spy|qqq)\b", re.I)
NUM = r"(\d*\.?\d+)"


def _side(t):
    if re.search(r"\b(puts?|short|bear(ish)?|downside)\b", t, re.I):
        return "P"
    if re.search(r"\b(calls?|long|bull(ish)?|upside)\b", t, re.I):
        return "C"
    return None


def _level(t):
    for m in re.finditer(r"\b(\d{3,4}(?:\.\d{1,2})?)\b", t):
        v = float(m.group(1))
        if 100 <= v <= 3000:
            return v
    return None


def active_plan(ticker=None):
    r = store.q("SELECT plan FROM watches WHERE status='ACTIVE'" + (" AND ticker=?" if ticker else "") +
                " ORDER BY created DESC LIMIT 1", (ticker,) if ticker else ())
    if r:
        return json.loads(r[0]["plan"])
    return store.kv_get("last_plan")


def handle(text, selected="SPY"):
    t = text.strip()
    low = t.lower()
    tk = (TICK.search(t).group(1).upper() if TICK.search(t) else selected).upper()
    main = core.policy()["instruments"]

    # ---------- IN (real fill reported by Nick) ----------
    m = re.match(rf"^(?:in|bought|filled)\s+(?:([a-z]{{1,5}})\s+)?(?:(\d+(?:\.\d+)?)\s*([cp])\s+)?(\d+)\s*(?:x|@|at)?\s*\$?{NUM}(?:\s+(\d{{1,2}}:\d{{2}}))?", low)
    if m:
        tk2, strike, cp, qty, fill, when = m.groups()
        tk2 = (tk2 if tk2 and watchlist.valid(tk2) else tk).upper()
        plan = active_plan(tk2)
        plan = plan if plan and plan.get("ticker") == tk2 else None
        contract = f"{float(strike):g}{cp.upper()}" if strike else ((plan or {}).get("contract") or {}).get("label")
        if not contract:
            return {"reply": "Which contract? Send it once like: IN SPY 765C 2 at 0.95", "handled": True}
        pid = engine.log_real_in(tk2, contract, int(qty), float(fill), when, plan if plan and plan.get("ticker") == tk2 else None)
        p = store.pos_get(pid)
        return {"reply": store.q("SELECT text FROM events WHERE ref=? ORDER BY seq DESC LIMIT 1", (pid,))[0]["text"],
                "handled": True, "position": p}

    # ---------- OUT / SOLD ----------
    m = re.match(rf"^(?:out|sold|sell|exit(?:ed)?)\s+(?:([a-z]{{1,5}})\s+)?(?:(\d+(?:\.\d+)?[cp])\s+)?(?:(\d+)\s*(?:x|@|at)\s*)?\$?{NUM}\s*$", low)
    if m:
        tk2, contract, qty, price = m.groups()
        tk2 = tk2 if tk2 and watchlist.valid(tk2) else None
        opens = store.positions(ledger="real", status="OPEN")
        if tk2:
            opens = [p for p in opens if p["ticker"] == tk2.upper()]
        if contract:
            opens = [p for p in opens if p["contract"].lower() == contract.lower()]
        if not opens:
            return {"reply": "No open real trade logged. Log the entry first with IN.", "handled": True}
        if len(opens) > 1:
            return {"reply": "You have more than one open trade: " + ", ".join(f"{p['ticker']} {p['contract']}" for p in opens) +
                    ". Say which, e.g. OUT SPY 765C 1 at 1.10", "handled": True}
        return {"reply": engine.log_real_out(opens[0]["id"], int(qty) if qty else None, float(price)), "handled": True}

    # ---------- watch controls ----------
    if re.search(r"\bstop watch(ing)?\b|\bunwatch\b", low):
        n = engine.stop_watch(tk if TICK.search(t) else None)
        return {"reply": f"Stopped {n} watch(es). Paper engine and open-position protection keep running.", "handled": True}
    if re.search(r"\bpause paper\b", low):
        store.kv_set("paper_enabled", False)
        store.event("paper", "PAPER ENTRIES PAUSED by Nick (open paper positions still managed)", "paper")
        return {"reply": "Paper entries paused. Open paper positions are still managed.", "handled": True}
    if re.search(r"\b(resume|start) paper\b", low):
        store.kv_set("paper_enabled", True)
        store.event("paper", "PAPER ENTRIES RESUMED", "paper")
        return {"reply": "Paper entries resumed.", "handled": True}

    # ---------- check once / confirm & watch ----------
    once = bool(re.search(r"\b(check once|once|snapshot)\b", low))
    confirm = once or bool(re.search(r"\b(confirm|watch|setup|calls\?|puts\?|should i|entry|enter)\b", low)) or bool(re.search(r"\?$", t) and _side(t))
    if confirm and tk not in main:
        return {"reply": f"Desk plans cover SPY/QQQ 0DTE. Asking Chart about {tk} (desk read + quote + earnings date attached).",
                "handled": False, "coach": True}
    if confirm:
        side = _side(t)
        lvl = _level(t)
        mins = re.search(r"(\d+)\s*(?:min|minutes)", low)
        if side:
            plan = engine.build_plan(tk, side, lvl, "check" if once else "watch")
        else:
            a, b = engine.build_plan(tk, "C", lvl), engine.build_plan(tk, "P", lvl)
            rank = {"READY": 3, "WAIT": 2, "PASS": 1}
            g = {"A": 3, "B": 2, "C": 1}
            plan = max((a, b), key=lambda x: (rank.get(x.get("state"), 0), g.get(x.get("grade"), 0)))
            plan["note"] = "no direction given: showing the stronger side"
        store.kv_set("last_plan", plan)
        if not once and plan["state"] in ("WAIT", "READY"):
            wid, exp = engine.start_watch(plan, int(mins.group(1)) if mins else None)
            plan["watch"] = {"id": wid, "until": exp[11:16]}
        return {"reply": plan_text(plan), "handled": True, "plan": plan, "coach": True}

    return {"reply": None, "handled": False, "coach": True}


def plan_text(p):
    side = "CALLS" if p["side"] == "C" else "PUTS"
    if p["state"] == "DATA UNAVAILABLE":
        return f"{p['ticker']} {side}: DATA UNAVAILABLE ({p.get('reason')}). No plan until data is fresh."
    lines = [f"{p['state']} | {p['ticker']} {side} | {p.get('setup')} ({p.get('setup_note')}) | grade {p.get('grade')} | {p.get('day')}"]
    lines.append(f"TRIGGER: {p.get('trigger_rule')} | INVALID: {p.get('invalidation')}")
    c = p.get("contract")
    if c:
        ex = p["exit"]
        lines.append(f"BUY: {c['label']} at or under ${p['premium_limit']:.2f} (ask {c['ask']:.2f}, delta {c['delta'] if c['delta'] is not None else 'unknown'}, delayed quote)")
        lines.append(f"SIZE: {p['qty']} ({'$%.2f' % p['risk_per_contract']} planned loss per contract){' | ' + p['size_note'] if p.get('size_note') else ''}")
        lines.append(f"STOP ${ex['stop']:.2f} (20% cap) | BE at ${ex['be_trigger']:.2f} -> stop to fill | T1 ${ex['t1']:.2f} | flat exit {ex['flat_by']} | all out {ex['all_out']}")
    else:
        lines.append(f"CONTRACT: {p.get('contract_note')}")
    if p.get("objections"):
        lines.append("AGAINST: " + "; ".join(p["objections"]))
    if p.get("reason"):
        lines.append("WHY PASS: " + p["reason"])
    if p.get("watch"):
        lines.append(f"WATCHING until {p['watch']['until']} ET (say 'stop watching' to end)")
    return "\n".join(lines)


def _alt(t):
    try:
        import altdata
        return altdata.ticker(t) if altdata.enabled() else None
    except Exception:
        return None


_CARDS = None


def cards_for(text, k=3):
    """Pick the k most relevant knowledge cards by tag match (no AI, no embeddings)."""
    global _CARDS
    if _CARDS is None:
        try:
            _CARDS = json.loads((core.HERE / "knowledge" / "cards.json").read_text())
        except Exception:
            _CARDS = []
    low = (text or "").lower()
    scored = sorted(((sum(1 for t in c["tags"] if t in low), c) for c in _CARDS), key=lambda x: -x[0])
    out = [c for n, c in scored if n > 0][:k] or [c for c in _CARDS if c["id"] == "K01"]
    return [{"id": c["id"], "title": c["title"], "status": c["status"], "summary": c["summary"]} for c in out]


def coach_context(selected="SPY", text=""):
    """Compact state for Chart. No raw bars, no secrets."""
    s = engine.snapshot(selected)
    rd = s.get("read", {})
    lessons = store.q("SELECT id, text, status FROM lessons WHERE status IN ('ACTIVE','PROPOSED') ORDER BY created DESC LIMIT 5")
    return {
        "policy": {"version": core.policy()["version"], "stop_cap": "20% of premium (gross fill x 0.80, trigger above for costs)",
                   "per_trade_cap": core.policy()["risk"]["per_trade_cap"], "daily_loss": core.policy()["risk"]["daily_loss_usd"],
                   "weekly_loss": core.policy()["risk"]["weekly_loss_usd"], "exit_profile": core.policy()["exit_profile"]["name"]},
        "session": core.session_info(),
        "ticker": selected, "price": s.get("price"), "price_src": s.get("price_src"), "bar_age_s": s.get("bar_age_s"),
        "read": {k: rd.get(k) for k in ("day_type", "daily", "vs_vwap", "vs_200s", "chop", "trend", "rsi", "macd", "rvol", "setups", "above", "below")},
        "active_plan": active_plan(selected),
        "open_real": [{k: p[k] for k in ("ticker", "contract", "qty_open", "fill")} | {"stop": p["plan"].get("stop"), "t1": p["plan"].get("t1")}
                      for p in store.positions(ledger="real", status="OPEN")],
        "open_paper": [{k: p[k] for k in ("ticker", "contract", "qty_open", "fill")} for p in store.positions(ledger="paper", status="OPEN")],
        "budget_real": engine.ledger_budget("real"), "lessons": lessons,
        "recent_events": [e["text"] for e in store.q("SELECT text FROM events ORDER BY seq DESC LIMIT 6")],
        "desk_plans_for_ticker": selected in core.policy()["instruments"],
        "watchlist_quote": None if selected in core.policy()["instruments"] else watchlist.quote(selected),
        "alt_data": None if selected in core.policy()["instruments"] else _alt(selected),
        "cards": cards_for(text),
    }
