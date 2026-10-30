"""strategy_router.py - one deterministic route from a candidate setup to a decision:

  data health -> the qualification record for that strategy and symbol (strategy_registry) -> clock window, session,
  warmup and regime eligibility (admit) -> the shared anti-chasing entry gate -> shared portfolio admission (2 open,
  4 ideas a day, losing streaks, across EVERY actionable specialist together) -> an isolated paper ledger and Nick's alert.

Only PAPER QUALIFIED strategies can reach a paper fill or an alert through the router, and none is qualified yet, so
today every route ends in SHADOW (recorded with the reason, nothing filled) or a rejection. RESEARCH ONLY strategies
keep running in their own research ledgers elsewhere; the router just never presents them as entries.
Each decision stores the exact qualification record (id, spec hash, status) and the versions that existed then.
"""
import json
from datetime import datetime

import core
import store
import strategy_registry as SR

VERSION = "2026-10-30.router1"
SCHEMA = ("CREATE TABLE IF NOT EXISTS router_decisions(id TEXT PRIMARY KEY, ts TEXT, date TEXT, ticker TEXT, side TEXT, family TEXT, "
          "decision TEXT, reasons TEXT, record TEXT, versions TEXT)")
REASONS = ("outside setup window", "wrong regime", "insufficient warmup", "incomplete bar", "stale data", "no eligible contract",
           "too extended", "insufficient remaining reward/risk", "expired setup", "loss-streak stop", "research-only status",
           "no qualified strategy", "session closed", "conflicting signals")


def _in_windows(hm, windows):
    return any(a <= hm <= b for a, b in (windows or [["09:45", "15:15"]]))


def admit(family, ticker, side, now=None, ctx=None):
    """The restriction layer BEFORE the shared gate. Returns {allowed, status, record, reasons[]} where reasons use the
    fixed vocabulary above. A True here never authorizes a fill by itself: the gate, the contract check and portfolio
    admission still run, and the clock is checked again at the proposed fill time."""
    now = now or core.now_et()
    ctx = ctx or {}
    rec = SR.status_for(family, ticker)
    reasons = []
    sess = core.session_info(now)
    hm = now.strftime("%H:%M")
    if not sess.get("entries_allowed"):
        reasons.append(f"session closed: {sess['state']}")
    exp = SR.get(rec["id"]) if rec.get("id") else None
    windows = ((exp or {}).get("spec") or {}).get("windows")
    if sess.get("early_close"):
        windows = [[a, min(b, core.policy()["session"]["early_close_last_entry"])] for a, b in (windows or [["09:45", "15:15"]])]
    if not _in_windows(hm, windows):
        reasons.append(f"outside setup window ({hm} not in {windows or '09:45-15:15'})")
    req = ((exp or {}).get("spec") or {}).get("requires") or {}
    if req.get("regime") and ctx.get("regime") is not None and ctx["regime"] not in req["regime"]:
        reasons.append(f"wrong regime ({ctx['regime']} not in {req['regime']})")
    if req.get("min_warmup_bars") and (ctx.get("warmup_bars") or 0) < req["min_warmup_bars"]:
        reasons.append(f"insufficient warmup ({ctx.get('warmup_bars') or 0} of {req['min_warmup_bars']} bars)")
    if ctx.get("bar_complete") is False:
        reasons.append("incomplete bar")
    if ctx.get("fresh") is not True:
        reasons.append("stale data" if ctx.get("fresh") is False else "stale data (freshness unknown)")
    if not rec["actionable"]:
        reasons.append(f"research-only status ({rec['status']}: {rec.get('why') or 'no demonstrated edge'})")
    return {"allowed": not reasons, "status": rec["status"], "record": rec, "reasons": reasons}


def portfolio_admission(day=None):
    """Shared limits across ALL actionable specialists together (not one allowance each)."""
    import engine
    day = day or core.now_et().strftime("%Y-%m-%d")
    led = sorted({r["ledger"] for r in store.q("SELECT DISTINCT ledger FROM positions WHERE ledger LIKE 'spec_%'")} |
                 {r["portfolio"] for r in store.q("SELECT DISTINCT portfolio FROM ideas WHERE portfolio LIKE 'spec_%'")})
    opens = [p for l in led for p in store.positions(ledger=l, status="OPEN")]
    if len(opens) >= core.policy()["risk"]["max_open_positions"]:
        return "max open positions across specialists"
    ideas = sum(len(store.q("SELECT idea FROM ideas WHERE portfolio=? AND created LIKE ?", (l, f"{day}%"))) for l in led)
    if ideas >= core.policy()["v3"]["limits"]["main_ideas_per_day"]:
        return "max ideas today across specialists"
    for l in led:
        g = engine.discipline_gate(l, "A")
        if g and g.startswith("STOP FOR TODAY"):
            return f"loss-streak stop ({l})"
    return None


def route(cand, now=None):
    """cand: {ticker, side, family, fresh, bar_complete, regime?, warmup_bars?, setup_id}. Records and returns the
    decision. With no PAPER QUALIFIED strategy this is always SHADOW or REJECT: nothing is filled or alerted."""
    store.x(SCHEMA)
    now = now or core.now_et()
    a = admit(cand.get("family"), cand.get("ticker"), cand.get("side"), now, cand)
    rid = f"R-{now.strftime('%Y-%m-%d')}-{cand.get('ticker')}-{cand.get('side')}-{cand.get('family')}-{cand.get('setup_id') or now.strftime('%H%M')}"
    if store.q("SELECT id FROM router_decisions WHERE id=?", (rid,)):
        return {"id": rid, "decision": "DUPLICATE", "reasons": ["the same setup was already routed"]}
    if a["allowed"]:
        lim = portfolio_admission()
        decision = "ADMIT" if not lim else "REJECT"
        reasons = [] if not lim else [lim]
    else:
        research_only = all(r.startswith("research-only") for r in a["reasons"])
        decision, reasons = ("SHADOW" if research_only else "REJECT"), a["reasons"]
    versions = {"router": VERSION, "registry": SR.load().get("version"), "policy": core.policy()["version"]}
    try:
        import entrygate
        versions["gate"] = entrygate.VERSION
    except Exception:
        pass
    store.x("INSERT OR IGNORE INTO router_decisions(id, ts, date, ticker, side, family, decision, reasons, record, versions) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)", (rid, now.isoformat(timespec="seconds"), now.strftime("%Y-%m-%d"), cand.get("ticker"),
                                            cand.get("side"), cand.get("family"), decision, json.dumps(reasons),
                                            json.dumps(a["record"], default=str), json.dumps(versions)))
    return {"id": rid, "decision": decision, "reasons": reasons, "record": a["record"], "versions": versions}


def today(limit=200):
    store.x(SCHEMA)
    day = core.now_et().strftime("%Y-%m-%d")
    rows = store.q("SELECT * FROM router_decisions WHERE date=? ORDER BY ts DESC LIMIT ?", (day, limit))
    for r in rows:
        r["reasons"] = json.loads(r["reasons"] or "[]")
        r["record"] = json.loads(r["record"] or "{}")
    return rows
