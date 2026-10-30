"""entrygate.py - the anti-chasing rule, in code that nothing (Chart, Grok, a sentiment score, a headline) can override.

Rule: find the setup early, enter ONLY inside its predefined entry zone, and if price leaves the zone before you're in,
the setup is MISSED: wait for a NEW qualifying structure (a retest that holds, or a new consolidation break) or pass.
The entry is never moved higher for calls (lower for puts), the stop is never widened and the target is never moved
farther to make a late entry look acceptable.

Every setup is stored once, versioned, with: trigger, entry zone, latest acceptable entry, structural invalidation,
an evidence-based target (a real level), when it expires, and the market data it was built from.

States (deterministic; the inputs are prices and levels only, no sentiment):
  WATCHING               trigger defined, price not near it
  CONFIRMATION NEEDED    price at/through the trigger without a finished 1m close beyond it
  ENTRY CONDITIONS MET   confirmed, price inside the zone, remaining reward/risk from the CURRENT price after costs
                         passes, spread and data fresh
  TOO EXTENDED           confirmed, but the current price is past the latest acceptable entry (or remaining R/R fails)
  WAIT FOR RETEST        the setup was MISSED (a finished close past the latest entry, or the entry window expired):
                         terminal for this setup; only a NEW structure can create a new one
  INVALIDATED            a finished 1m close beyond the structural invalidation: terminal
  NO TRADE               no evidence-based target, R/R fails even at the trigger, spread too wide, or stale data

Remaining reward/risk at entry e (calls; puts mirror), with c = estimated round-trip cost in underlying dollars:
    RR(e) = (target - e - c) / (e - invalidation + c)
and the latest acceptable entry solves RR(e) = min_rr:  e* = (target + min_rr * invalidation - c * (1 + min_rr)) / (1 + min_rr)
Example (no costs): trigger 100.00, invalidation 99.50, target 101.00 -> RR(100.00) = 2.0; RR(100.80) = 0.20 / 1.30 = 0.15.
This is the UNDERLYING ratio. The option contract has its own (optionmath rr_option) and must pass separately.

All thresholds live in policy.json "entry_gate". They are starting hypotheses to test on paper, not proven values.
"""
import json
from datetime import datetime, timedelta

import core
import store

VERSION = "2026-10-30.v3.2-gate1"
SCHEMA = """CREATE TABLE IF NOT EXISTS gate_setups(id TEXT PRIMARY KEY, date TEXT, ticker TEXT, side TEXT, kind TEXT, version TEXT,
  status TEXT, created TEXT, updated TEXT, data TEXT)"""
TERMINAL = ("MISSED", "INVALIDATED", "EXPIRED")
DEFAULTS = {"zone_atr5": 0.6, "near_atr5": 0.15, "retest_atr5": 0.15, "window_min": 10, "expire_min": 60,
            "min_rr": None, "max_stock_spread_pct": 0.15, "slip_per_share": 0.01, "max_move_since_news_atr5": 2.0,
            "note": "starting hypotheses for paper testing, not validated values"}
STATES = ("WATCHING", "CONFIRMATION NEEDED", "ENTRY CONDITIONS MET", "TOO EXTENDED", "WAIT FOR RETEST", "INVALIDATED", "NO TRADE")


def cfg():
    c = dict(DEFAULTS)
    c.update(core.policy().get("entry_gate") or {})
    if c.get("min_rr") is None:
        c["min_rr"] = float(core.policy()["v3"]["min_reward_risk"])
    return c


def rr(entry, target, inval, side, cost):
    """Remaining reward/risk from `entry` after costs (None if the risk is not positive)."""
    if side == "C":
        reward, risk = target - entry - cost, entry - inval + cost
    else:
        reward, risk = entry - target - cost, inval - entry + cost
    return round(reward / risk, 2) if risk > 0 else None


def latest_entry(trigger, target, inval, side, cost, atr5, c):
    """The worst price still acceptable: inside the zone AND keeping remaining R/R >= min_rr."""
    m = c["min_rr"]
    if side == "C":
        by_rr = (target + m * inval - cost * (1 + m)) / (1 + m)
        return round(min(trigger + c["zone_atr5"] * atr5, by_rr), 2), round(by_rr, 2)
    by_rr = (target + m * inval + cost * (1 + m)) / (1 + m)
    return round(max(trigger - c["zone_atr5"] * atr5, by_rr), 2), round(by_rr, 2)


def _key(day, ticker, side, kind, trigger):
    return f"G-{day}-{ticker}-{side}-{kind}-{trigger:.2f}"


def _load(gid):
    store.x(SCHEMA)
    r = store.q("SELECT * FROM gate_setups WHERE id=?", (gid,))
    return dict(json.loads(r[0]["data"]), status=r[0]["status"]) if r else None


def _save(g):
    store.x(SCHEMA)
    store.x("INSERT OR REPLACE INTO gate_setups(id,date,ticker,side,kind,version,status,created,updated,data) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (g["id"], g["date"], g["ticker"], g["side"], g["kind"], g["version"], g["status"], g["created"], store.ts(),
             json.dumps(g, default=str)))


def target_for(trigger, side, levels, zone):
    """Evidence-based target: the next real level beyond the trigger (not a made-up multiple)."""
    vals = sorted((v["value"], k) for k, v in (levels or {}).items() if v.get("value") is not None and k not in ("PDC", "VWAP"))
    if side == "C":
        ahead = [x for x in vals if x[0] > trigger + zone]
        return ahead[0] if ahead else (None, None)
    ahead = [x for x in reversed(vals) if x[0] < trigger - zone]
    return ahead[0] if ahead else (None, None)


def define(ticker, side, kind, trigger, inval, target, target_name, snap, trigger_rule, confirmed_at=None, catalyst=None):
    """Create (once) the versioned setup. An existing setup with the same key is returned unchanged: entry, stop and
    target can't be edited after the fact."""
    c = cfg()
    day = core.now_et().strftime("%Y-%m-%d")
    gid = _key(day, ticker, side, kind, trigger)
    old = _load(gid)
    if old:
        return old
    atr5 = float(snap.get("atr5") or 0) or max(0.05, abs(trigger) * 0.001)
    cost = _cost(snap, c)
    le, by_rr = (None, None) if target is None else latest_entry(trigger, target, inval, side, cost, atr5, c)
    now = core.now_et()
    g = {"id": gid, "date": day, "ticker": ticker, "side": side, "kind": kind, "version": VERSION, "status": "OPEN",
         "created": now.isoformat(timespec="seconds"), "trigger": round(trigger, 2), "trigger_rule": trigger_rule,
         "invalidation": round(inval, 2), "target": round(target, 2) if target is not None else None, "target_name": target_name,
         "zone": [round(trigger, 2), round(trigger + (c["zone_atr5"] * atr5 if side == "C" else -c["zone_atr5"] * atr5), 2)],
         "latest_entry": le, "latest_by_rr": by_rr, "cost_est": round(cost, 4), "atr5": round(atr5, 4),
         "rr_at_trigger": rr(trigger, target, inval, side, cost) if target is not None else None,
         "confirmed_at": confirmed_at, "confirmed_bar": str(snap.get("t")) if confirmed_at else None, "expires_at": (now + timedelta(minutes=c["expire_min"])).isoformat(timespec="seconds"),
         "params": {k: c[k] for k in ("zone_atr5", "near_atr5", "window_min", "expire_min", "min_rr", "max_stock_spread_pct")},
         "built_from": {"price": snap.get("price"), "close1": snap.get("close1"), "vwap": snap.get("vwap"),
                        "bar_t": str(snap.get("t")), "spread_pct": snap.get("spread_pct")},
         "catalyst": catalyst, "history": []}
    _save(g)
    return g


def _cost(snap, c):
    sp = snap.get("spread")
    return (sp / 2 if sp else 0.0) + c["slip_per_share"]


def evaluate(g, snap):
    """State of a stored setup against the latest data. Persists terminal transitions. Returns a dict with the state,
    the rejected condition (if any) and every check with its numbers."""
    c = cfg()
    now = core.now_et()
    side, up = g["side"], g["side"] == "C"
    px, c1 = snap.get("price"), snap.get("close1")
    checks = []

    def chk(name, ok, detail):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})
        return ok

    out = {"id": g["id"], "kind": g["kind"], "trigger": g["trigger"], "zone": g["zone"], "latest_entry": g["latest_entry"],
           "invalidation": g["invalidation"], "target": g["target"], "target_name": g["target_name"], "version": g["version"],
           "at": now.strftime("%H:%M:%S"), "checks": checks, "params": g["params"], "confirmed_at": g.get("confirmed_at")}
    if g["status"] in TERMINAL:
        st = {"MISSED": "WAIT FOR RETEST", "INVALIDATED": "INVALIDATED", "EXPIRED": "NO TRADE"}[g["status"]]
        return dict(out, state=st, rejected=g.get("terminal_why"), terminal=True)
    fresh = snap.get("fresh", True)
    if not chk("data fresh", fresh, f"bar {snap.get('bar_age_s')} s old"):
        return dict(out, state="NO TRADE", rejected="data is stale or missing: no new entries until it is fresh")
    if g["target"] is None:
        chk("evidence-based target", False, "no real level beyond the trigger")
        return dict(out, state="NO TRADE", rejected="no evidence-based target beyond the trigger")
    # the structural invalidation applies once the trigger is confirmed (before that, a breakout level above price
    # naturally has its invalidation above price too: that is "not triggered", not "invalidated")
    if g.get("confirmed_at") and c1 is not None and ((c1 < g["invalidation"]) if up else (c1 > g["invalidation"])):
        return _terminal(g, out, "INVALIDATED", f"1m close {c1:.2f} beyond the invalidation {g['invalidation']:.2f}")
    if now.isoformat(timespec="seconds") > g["expires_at"] and not g.get("confirmed_at"):
        return _terminal(g, out, "EXPIRED", f"never confirmed before {g['expires_at'][11:16]}")
    if g["rr_at_trigger"] is not None and not chk("R/R at the trigger", g["rr_at_trigger"] >= c["min_rr"],
                                                 f"{g['rr_at_trigger']} vs minimum {c['min_rr']}"):
        return dict(out, state="NO TRADE", rejected=f"reward/risk is only {g['rr_at_trigger']} even at the trigger")
    confirmed = c1 is not None and ((c1 > g["trigger"]) if up else (c1 < g["trigger"]))
    if confirmed and not g.get("confirmed_at"):
        g["confirmed_at"], g["confirmed_bar"] = now.isoformat(timespec="seconds"), str(snap.get("t"))
        _save(g)
    if not g.get("confirmed_at"):
        near = c["near_atr5"] * g["atr5"]
        if px is not None and ((px >= g["trigger"] - near) if up else (px <= g["trigger"] + near)):
            chk("finished 1m close beyond the trigger", False, f"last close {c1}, trigger {g['trigger']}")
            return dict(out, state="CONFIRMATION NEEDED", rejected=f"needs a finished 1m close {'above' if up else 'below'} {g['trigger']:.2f}")
        return dict(out, state="WATCHING", rejected=f"price {px} not at the trigger {g['trigger']:.2f} yet")
    chk("finished 1m close beyond the trigger", True, f"confirmed at {g['confirmed_at'][11:19]}")
    # missed: a finished close past the latest entry, or the entry window ran out
    le = g["latest_entry"]
    after_confirm = str(snap.get("t")) != g.get("confirmed_bar")       # the confirming bar itself can't "miss" its own setup
    if after_confirm and c1 is not None and ((c1 > le) if up else (c1 < le)):
        return _terminal(g, out, "MISSED", f"a finished 1m close {c1:.2f} went past the latest acceptable entry {le:.2f}: "
                                            "the move already happened. Wait for a new setup or skip it.")
    win_end = datetime.fromisoformat(g["confirmed_at"]) + timedelta(minutes=c["window_min"])
    if now > win_end:
        return _terminal(g, out, "MISSED", f"the entry window closed at {win_end.strftime('%H:%M')} ({c['window_min']} min after confirmation)")
    cur = px if px is not None else c1
    r_now = rr(cur, g["target"], g["invalidation"], side, g["cost_est"])
    out["rr_now"] = r_now
    inside = (cur <= le) if up else (cur >= le)
    chk("price inside the entry zone", inside, f"price {cur:.2f}, latest acceptable {le:.2f}")
    chk("remaining R/R from the current price", r_now is not None and r_now >= c["min_rr"], f"{r_now} vs minimum {c['min_rr']} after est. costs ${g['cost_est']:.2f}")
    if not inside or r_now is None or r_now < c["min_rr"]:
        return dict(out, state="TOO EXTENDED", rejected=f"price {cur:.2f} is past the latest acceptable entry {le:.2f} "
                                                        f"(remaining reward/risk {r_now}). Don't chase: wait for a retest or skip.")
    sp = snap.get("spread_pct")
    if not chk("stock spread", sp is None or sp <= c["max_stock_spread_pct"], f"{sp}% vs {c['max_stock_spread_pct']}%"):
        return dict(out, state="NO TRADE", rejected=f"stock spread {sp}% is too wide")
    mv = snap.get("move_since_news_atr5")
    if mv is not None and not chk("move since the news", mv <= c["max_move_since_news_atr5"], f"{mv} x 5m ATR vs {c['max_move_since_news_atr5']}"):
        return dict(out, state="TOO EXTENDED", rejected=f"price already moved {mv} x the 5m ATR since the news")
    return dict(out, state="ENTRY CONDITIONS MET", rejected=None)


def _terminal(g, out, status, why):
    g["status"], g["terminal_why"] = status, why
    g["history"].append({"t": store.ts(), "status": status, "why": why})
    _save(g)
    st = {"MISSED": "WAIT FOR RETEST", "INVALIDATED": "INVALIDATED", "EXPIRED": "NO TRADE"}[status]
    return dict(out, state=st, rejected=why, terminal=True)


def retest_setup(missed, r1, snap):
    """A NEW setup after a miss, only on a new structure: price came back to the old trigger (within retest_atr5 x ATR),
    and a finished 1m bar then closed back in the setup's direction. Its trigger is that bar's high (low for puts), its
    invalidation the retest low (high) minus/plus the buffer. Its reward/risk is computed fresh; nothing is carried over.
    Returns the new setup or None. A retest is not guaranteed to work."""
    if missed is None or missed.get("status") != "MISSED" or r1 is None or len(r1) < 3:
        return None
    c = cfg()
    up = missed["side"] == "C"
    tol = c["retest_atr5"] * missed["atr5"]
    after = r1[r1.index > datetime.fromisoformat(missed["history"][-1]["t"]).astimezone(r1.index.tz)] if missed.get("history") else r1
    if len(after) < 2:
        return None
    touch = after["Low"].min() if up else after["High"].max()
    if (touch - missed["trigger"]) * (1 if up else -1) > tol:
        return None
    last = after.iloc[-1]
    turned = (last["Close"] > missed["trigger"] and last["Close"] > last["Open"]) if up else (last["Close"] < missed["trigger"] and last["Close"] < last["Open"])
    if not turned:
        return None
    buf = float(snap.get("buf") or 0.02)
    trig = float(last["High"]) if up else float(last["Low"])
    inval = float(touch) - buf if up else float(touch) + buf
    tgt = missed["target"]
    if tgt is None or ((tgt <= trig) if up else (tgt >= trig)):
        return None
    return define(missed["ticker"], missed["side"], "retest", trig, inval, tgt, missed["target_name"], snap,
                  f"retest of {missed['trigger']:.2f} held; 1m close {'above' if up else 'below'} {trig:.2f}")


def snap_from(s):
    """Gate inputs from an engine snapshot (engine.snapshot) - the same Schwab data the chart and plan use."""
    v3 = s.get("v3") or {}
    q = s.get("quote") or {}
    bar_age = s.get("bar_age_s")
    max_age = core.policy()["data"]["max_bar_age_s"]
    sess = core.session_info()["state"]
    fresh = bool(v3.get("ok")) and not (bar_age is not None and bar_age > max_age and sess in ("OPEN", "ORB FORMING", "NO NEW ENTRIES", "ALL OUT"))
    px = q.get("last") or v3.get("close1")
    sp = q.get("spread")
    return {"price": px, "close1": v3.get("close1"), "vwap": v3.get("vwap"), "atr5": v3.get("atr5"), "t": v3.get("t"),
            "spread": sp, "spread_pct": round(sp / px * 100, 3) if sp and px else None, "bar_age_s": bar_age, "fresh": fresh,
            "buf": v3.get("buf"), "zone": v3.get("zone")}


def for_plan(plan, s):
    """Gate a desk plan (Nick's assistant): define/find the setup and evaluate it. None if the plan has no structure."""
    if plan.get("trigger_level") is None or plan.get("invalidation") is None:
        return None
    v3 = s.get("v3") or {}
    sn = snap_from(s)
    ex = plan.get("exit") or {}
    tgt, tname = (ex.get("t1_level"), ex.get("t1_name")) if ex.get("t1_level") is not None else \
        target_for(plan["trigger_level"], plan["side"], v3.get("levels"), v3.get("zone") or 0)
    kind = (plan.get("setup") or "LEVEL").lower()
    confirmed = v3["t"].isoformat(timespec="seconds") if plan.get("state") == "READY" and v3.get("t") is not None else None
    g = define(plan["ticker"], plan["side"], kind, float(plan["trigger_level"]), float(plan["invalidation"]), tgt, tname, sn,
               plan.get("trigger_rule"), confirmed_at=confirmed)
    res = evaluate(g, sn)
    if res["state"] == "WAIT FOR RETEST":
        nxt = retest_setup(_load(g["id"]), v3.get("r1"), sn)
        if nxt:
            res = dict(evaluate(nxt, sn), replaced=g["id"])
    return res


def today(ticker=None):
    store.x(SCHEMA)
    day = core.now_et().strftime("%Y-%m-%d")
    rows = store.q("SELECT data, status FROM gate_setups WHERE date=?" + (" AND ticker=?" if ticker else "") + " ORDER BY created",
                   (day, ticker) if ticker else (day,))
    return [dict(json.loads(r["data"]), status=r["status"]) for r in rows]
