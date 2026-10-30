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


def _known():
    try:
        u = set(json.loads((core.HERE / "config" / "universe.json").read_text())["tickers"])
    except Exception:
        u = set()
    try:
        u |= set(watchlist.tickers())
    except Exception:
        pass
    return u | set(core.policy()["instruments"])


def find_ticker(t):
    """SPY/QQQ, or any ticker from the scanner universe or the watchlist written in the message (e.g. 'NVDA calls?')."""
    m = TICK.search(t)
    if m:
        return m.group(1).upper()
    known = _known()
    for w in re.findall(r"\$?\b([A-Za-z]{1,5})\b", t):
        if w.upper() in known and (w.isupper() or w.startswith("$") or len(w) >= 3) and w.lower() not in ("in", "out", "at", "stop", "puts", "calls", "call", "put"):
            return w.upper()
    return None


def handle(text, selected="SPY"):
    t = text.strip()
    low = t.lower()
    tk = (find_ticker(t) or selected).upper()
    main = core.policy()["instruments"]

    # ---------- IN (real fill reported by Nick) ----------
    low = re.sub(r"^(?:ok(?:ay)?|so|just|yeah)[, ]+", "", low)
    m = re.match(rf"^(?:i'?m\s+in|i\s+(?:got\s+in|bought|entered|took)|got\s+in|entered|took|in|bought|filled)\s+(?:([a-z]{{1,5}})\s+)?(?:(\d+(?:\.\d+)?)\s*([cp])\s+)?(?:(\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?|\d{{4}}-\d{{2}}-\d{{2}})\s+)?(\d+)\s*(?:x|@|at)?\s*\$?{NUM}(?:\s+(\d{{1,2}}:\d{{2}}))?", low)
    if m:
        tk2, strike, cp, expiry, qty, fill, when = m.groups()
        expiry = _expiry(expiry)
        tk2 = (tk2 if tk2 and watchlist.valid(tk2) else tk).upper()
        plan = active_plan(tk2)
        plan = plan if plan and plan.get("ticker") == tk2 else None
        contract = f"{float(strike):g}{cp.upper()}" if strike else ((plan or {}).get("contract") or {}).get("label")
        if not contract:
            return {"reply": "Which contract? Send it once like: IN SPY 765C 2 at 0.95", "handled": True}
        if tk2 not in main and not expiry:
            return {"reply": f"Which expiry? {tk2} options aren't same-day by default. Send it like: IN {tk2} {contract} 11/07 {qty} at {fill}",
                    "handled": True}
        pid = engine.log_real_in(tk2, contract, int(qty), float(fill), when, plan if plan and plan.get("ticker") == tk2 else None,
                                 expiry=expiry)
        p = store.pos_get(pid)
        return {"reply": store.q("SELECT text FROM events WHERE ref=? ORDER BY seq DESC LIMIT 1", (pid,))[0]["text"],
                "handled": True, "position": p}

    # ---------- STOP change on a real trade (recorded; widening refused unless forced) ----------
    m = re.match(rf"^(?:my\s+)?stop(?:\s+(?:is|at|to|moved to))?\s+\$?{NUM}(\s+force)?\s*$", low)
    if m:
        import exits
        opens = store.positions(ledger="real", status="OPEN")
        if not opens:
            return {"reply": "No open real trade to set a stop on.", "handled": True}
        if len(opens) > 1:
            return {"reply": "More than one open trade: say which by closing one first, or tell Chart.", "handled": True}
        ok, why = exits.user_stop(opens[0], float(m.group(1)), force=bool(m.group(2)))
        return {"reply": store.q("SELECT text FROM events WHERE ref=? ORDER BY seq DESC LIMIT 1", (opens[0]["id"],))[0]["text"], "handled": True}

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
        pid = opens[0]["id"]
        reply = engine.log_real_out(pid, int(qty) if qty else None, float(price))
        closed = (store.pos_get(pid) or {}).get("status") == "CLOSED"
        return {"reply": reply, "handled": True, "review": {"id": pid, "trade": f"{opens[0]['ticker']} {opens[0]['contract']}"} if closed else None}

    # ---------- watch controls ----------
    if re.search(r"\bstop watch(ing)?\b|\bunwatch\b", low):
        n = engine.stop_watch(tk if TICK.search(t) else None)
        return {"reply": f"Stopped {n} watch(es). Paper engine and open-position protection keep running.", "handled": True}
    if re.search(r"\b(kill switch|kill paper|kill)\b", low) and not re.search(r"\b(kill zone)\b", low):
        return {"reply": engine.kill_paper(), "handled": True}
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


def _expiry(s):
    """'11/07', '11/07/26' or '2026-11-07' -> 'YYYY-MM-DD' (the next such date if the year is missing)."""
    if not s:
        return None
    if "-" in s:
        return s
    from datetime import date
    parts = [int(x) for x in s.split("/")]
    today = core.now_et().date()
    y = (parts[2] + 2000 if parts[2] < 100 else parts[2]) if len(parts) == 3 else today.year
    d = date(y, parts[0], parts[1])
    if len(parts) == 2 and d < today:
        d = date(y + 1, parts[0], parts[1])
    return d.isoformat()


VERDICT = {"READY": "ENTER", "WAIT": "WAIT", "PASS": "PASS"}


def plan_text(p):
    side = "CALLS" if p["side"] == "C" else "PUTS"
    if p["state"] == "DATA UNAVAILABLE":
        return f"{p['ticker']} {side}: DATA UNAVAILABLE ({p.get('reason')}). No plan until data is fresh."
    d = p.get("data") or {}
    mode = f" [{p['entry_mode']}]" if p.get("entry_mode") else ""
    verdict = VERDICT.get(p["state"], p["state"])
    if verdict == "ENTER" and not p.get("contract"):
        verdict = "PASS"
    if verdict == "ENTER" and p.get("research_only"):
        verdict = "RESEARCH ONLY (rules met, but this setup has no demonstrated edge: not an entry instruction)"
    lines = [f"{verdict}: {p['ticker']} {side} | {p.get('origin', '')}"]
    ev = p.get("evidence") or {}
    if ev.get("status"):
        lines.append(f"EVIDENCE: {ev['status']}" + (f" ({ev.get('why')})" if ev.get("why") else ""))
    a = p.get("assistant") or {}
    if a.get("state"):
        lines.append(f"DESK READ {a['at']} ET: {a['state']} ({a.get('why')})")
        if a.get("observations"):
            lines.append("OBSERVED: " + "; ".join(a["observations"][:5]))
        if a.get("conditions_met"):
            lines.append("CONDITIONS MET: " + "; ".join(a["conditions_met"]))
        if a.get("missing"):
            lines.append("STILL MISSING: " + "; ".join(x for x in a["missing"] if x))
    lines.append(f"{p['state']} | {p.get('setup')}{mode} ({p.get('setup_note')}) | grade {p.get('grade')} | regime {p.get('regime')} (interpretation)")
    lines.append(f"TRIGGER: {p.get('trigger_rule')} | STRUCTURE STOP: {p['ticker']} 1m close {'below' if p['side'] == 'C' else 'above'} {p.get('invalidation')}")
    c = p.get("contract")
    if c:
        ex = p["exit"]
        lines.append(f"{'CONTRACT (research only, not an instruction)' if p.get('research_only') else 'BUY'}: {c['label']} at or under ${p['premium_limit']:.2f} (bid {c['bid']:.2f} / ask {c['ask']:.2f}, delta {c['delta'] if c['delta'] is not None else 'unknown'}, "
                     f"{'LIVE Schwab' if d.get('executable') else 'NOT executable data, check Legend'})")
        lines.append(f"SIZE: {p['qty']} (stressed loss ${p['risk_per_contract']:.2f}/contract, ceiling ${ex['ceiling_per_contract']:.2f}){' | ' + p['size_note'] if p.get('size_note') else ''}")
        lines.append(f"T1: {ex['t1_name']} {ex['t1_level']:.2f} (option ~${ex['t1']:.2f}, {ex['model']}) | R/R {ex['rr_underlying']} on the stock, {ex['rr_option']} on the option")
        rk = a.get("risk") or {}
        if rk:
            lines.append(f"PLANNED MAX LOSS: premium stop ${rk['premium_stop']:.2f} vs the ${rk['entry_limit']:.2f} limit = about ${rk['per_contract_usd']:.0f} "
                         f"a contract, ${rk['total_usd']:.0f} for {rk['qty']} (a planned threshold: fills, gaps and slippage can make it larger). "
                         f"Separate from the stock invalidation: {rk.get('underlying_invalidation')}")
        lines.append(f"STOPS: structure above, or premium ${ex['stop']:.2f} (20% max planned loss; you place the order, a fast market can skip past it) | BE at ${ex['be_trigger']:.2f} -> stop ${ex['be_stop']:.2f} | "
                     f"green + no new high {ex['stall_min']} min or MACD turns -> out | if not green by {ex['flat_by']} -> out | all out {ex['all_out']}")
    else:
        lines.append(f"CONTRACT: {p.get('contract_note')}")
    if p.get("support"):
        lines.append("FOR: " + "; ".join(p["support"][:4]))
    if p.get("objections"):
        lines.append("AGAINST: " + "; ".join(p["objections"]))
    if p.get("reason"):
        lines.append("WHY PASS: " + p["reason"])
    if p.get("watch"):
        lines.append(f"WATCHING until {p['watch']['until']} ET (say 'stop watching' to end)")
    return "\n".join(lines)


def _in_play():
    """Today's scanner ranking for Chart (ideas, not validated setups)."""
    try:
        import scanner
        rows = scanner._rows(core.now_et().strftime("%Y-%m-%d"))
    except Exception:
        return []
    return [{"ticker": r["ticker"], "rank": r["rank"], "rvol": r.get("rvol"), "direction": r.get("direction"), "change_pct": r.get("change_pct"),
             "range": [r.get("or_low"), r.get("or_high")], "status": r.get("status"), "earnings": r.get("earnings"),
             "contract": {k: (r.get("contract") or {}).get(k) for k in ("symbol", "exp", "delta", "spread_pct", "oi")} if r.get("contract") else None}
            for r in rows if r["rank"] < 900][:8]


def _setups_brief():
    """The setups board for Chart: the summary and the top qualifying rows (observations with their rule, not tips)."""
    try:
        import scanner_setups
        b = scanner_setups.board()
    except Exception:
        return None
    keep = ("ticker", "setup", "direction", "state", "level_name", "level", "distance_atr", "rvol", "rvol_method", "why", "missing",
            "invalidation_text", "extended", "flags", "score", "fresh")
    return {"status": b["status"], "summary": b["summary"], "coverage": b["coverage"]["limits"][0],
            "rows": [{k: r.get(k) for k in keep} for r in b["rows"] if r["qualifies"]][:6]}


def _strategies_brief():
    """v3.3: the evidence status of every registered strategy, compact, so Chart never calls a research-only setup an entry."""
    try:
        import strategy_registry
        t = strategy_registry.evidence_table()
    except Exception as e:
        return {"error": f"evidence table unavailable ({type(e).__name__}): treat every desk setup as research only"}
    return {"qualified": t["qualified"], "note": t["qualified_note"],
            "status": {e["id"]: e["status"] for e in t["experiments"]}}


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


def _schwab_ready():
    try:
        import schwab
        return schwab.ready()
    except Exception:
        return False


def rules_summary():
    """Nick's current trading rules in one compact block, sent with every Chart question (always up to date)."""
    p = core.policy()
    d, c, se, v = p["discipline"], p["contract"], p["session"], p["v3"]
    return {
        "version": p["version"],
        "stops": "STRUCTURE first: just beyond the level/swing that disproves the setup (+ buffer), on a finalized 1m close; "
                 "plus a hard 20% planned premium-loss CEILING (costs included). If the structure can't fit inside 20%, skip or pick another contract.",
        "old_stops": "the old 20/12/10% time-of-day stops are retired (kept only as the frozen 'old policy' comparison)",
        "reward_risk": f">= {v['min_reward_risk']}:1 on the stock move (to T1 vs to the stop) AND on the modeled option dollars after spread/fees/decay",
        "t1": "the next meaningful opposing level (resistance for calls, support for puts), minus an approach buffer",
        "exits": f"green + no new premium high {v['exits']['stall_min']} min -> out; green + 3 adverse 2m MACD histogram changes or MACD cross against -> out; "
                 "T1 with 2 contracts: sell 1, keep the rest only on a clean break with momentum; 1 contract: out at T1; "
                 f"breakeven at +{int(v['exits']['be_trigger_pct'] * 100)}%, lock +{int(v['exits']['lock_keep_pct'] * 100)}% after +{int(v['exits']['lock_trigger_pct'] * 100)}%; "
                 "losers still follow the structure stop and the if-flat timer",
        "entries": "confirmed candle closes only; calls and puts on the same bar = skip; one idea = one trade",
        "vwap_macd": "ONE strategy: a 2m MACD cross with the close beyond VWAP arms it; enter on a VWAP retest + confirming close; "
                     "enter early on the cross close only when the trend is clearly strong; cancel on a close back through VWAP or a MACD cross back",
        "size": "A = 2 contracts, B = 1, C = no paper trade; whole contracts that fit the stressed loss",
        "delta": f"{c['abs_delta_min']}-{c['abs_delta_max']} (aim {c.get('abs_delta_target', 0.45)}), premium ${c['premium_min']}-${c['premium_max']}, spread <= {round(c['max_spread_pct'] * 100)}%",
        "streak": f"{d['a_only_after_consecutive_losses']} losses in a row = A setups only + {d['cooldown_min_after_loss']} min cooldown; {d['stop_day_after_consecutive_losses']} in a row = STOP FOR TODAY",
        "limits": f"main paper: max {v['limits']['main_ideas_per_day']} ideas/day; research keeps observing after limits",
        "afternoon": f"after {v['afternoon']['start']}: cleaner structure required (efficiency, few VWAP crossings, little overlap, participation)",
        "session": f"no trades {se['orb_start']}-{se['orb_end']} (ORB), entries {se['first_entry']}-{se['last_entry']}, all out {se['all_out']} ET",
        "never": "Chart never places or clicks orders; real money is Nick's, in Robinhood; Schwab quotes are not his fills",
    }


def coach_context(selected="SPY", text=""):
    """Compact state for Chart. No raw bars, no secrets."""
    s = engine.snapshot(selected)
    rd = s.get("read", {})
    v3 = s.get("v3") or {}
    lessons = store.q("SELECT id, text, status FROM lessons WHERE status IN ('ACTIVE','PROPOSED') ORDER BY created DESC LIMIT 5")
    import marketdata
    md = marketdata.status()
    return {
        "policy": {"version": core.policy()["version"], "stops": "structure + 20% ceiling", "per_trade_cap": core.policy()["risk"]["per_trade_cap"]},
        "session": core.session_info(),
        "ticker": selected, "price": s.get("price"), "price_src": s.get("price_src"), "bar_age_s": s.get("bar_age_s"),
        "data": {"label": md.get("live_label"), "provider": md.get("provider"), "executable": md.get("executable")},
        "read": {k: rd.get(k) for k in ("day_type", "daily", "vs_vwap", "vs_200s", "chop", "trend", "rsi", "macd", "rvol", "setups", "above", "below")},
        "regime": v3.get("regime"),
        "levels": {k: {"value": v["value"], "source": v["source"]} for k, v in (v3.get("levels") or {}).items()},
        "active_plan": active_plan(selected),
        "open_real": [{k: p[k] for k in ("ticker", "contract", "symbol", "qty_open", "fill")} | {k: p["plan"].get(k) for k in ("premium_stop", "stop_px", "t1", "t1_level", "be_hit", "green", "guidance")}
                      for p in store.positions(ledger="real", status="OPEN")],
        "open_paper": [{k: p[k] for k in ("ticker", "contract", "qty_open", "fill", "ledger")} for p in store.positions(status="OPEN") if p["ledger"] in ("paper", "research")],
        "budget_real": engine.ledger_budget("real"), "lessons": lessons,
        "recent_events": [e["text"] for e in store.q("SELECT text FROM events ORDER BY seq DESC LIMIT 6")],
        "desk_plans_for_ticker": True,       # v3.2: the desk plans and tracks any Schwab-supported ticker
        "setups_board": _setups_brief(),
        "strategies": _strategies_brief(),
        "watchlist_quote": None if selected in core.policy()["instruments"] else watchlist.quote(selected),
        "alt_data": None if selected in core.policy()["instruments"] else _alt(selected),
        "cards": cards_for(text),
        "in_play": _in_play(),
        "open_research": [{k: p[k] for k in ("ledger", "ticker", "contract", "qty_open", "fill")} for p in store.positions(status="OPEN")
                          if p["ledger"] in ("exit31", "noise", "inplay")],
        "rules": rules_summary(),
        "training": {"library": ["Nick's Playbook", "Desk v3 rules map", "Desk knowledge pack", "Desk commands"],
                     "precedence": "desk numbers in this context > rules (this field) > Desk v3 rules map > Playbook",
                     "data": {"candles": md.get("live_label"), "options_feed": md.get("provider"), "executable": md.get("executable")}},
    }
