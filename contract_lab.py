"""contract_lab.py - v3.4.2: which option contract turns a signal's stock move into option profit?

For every LIVE strategy-lab signal (seen within the lab's freshness window), up to 12 contracts are picked from the
real Schwab chain: expiry 0DTE / 1-2 days / 3-5 days / 6-10 days x delta 0.35 / 0.45 / 0.60 (the nearest expiry in
each bucket, the strike whose delta is closest to the target and within 0.10 of it, a two-sided quote no older than
20 s). Each one is followed on real quotes until 3:26 PM ET: one batched request for all of them every lab step.
Nothing is filled or traded. After the close, each contract is scored at the moment the signal's stock trade ended
(the lab's shared yardstick):
  entry  = the ask when picked + $0.01, fees $0.02 per side (the strict paper model);
  held   = the bid at the stock exit - $0.01;
  with the 20% line = if the bid touched your 20% planned-loss line first (same formula as the paper ledgers), the
                      bid at that moment - $0.01 instead.
The report groups by strategy and by contract choice: how often each choice made money, the average dollars per
contract and as % of premium, and how often the 20% line hit before the stock trade ended.
"""
import json
import time
from datetime import date, datetime, timedelta

import pandas as pd

import core
import store

VERSION = "2026-10-30.v3.4.2-contracts1"
BUCKETS = (("0DTE", 0, 0), ("1-2 days", 1, 2), ("3-5 days", 3, 5), ("6-10 days", 6, 10))
DELTAS = (0.35, 0.45, 0.60)
DEFAULTS = {"enabled": True, "starts_per_min": 4, "max_tracked_signals": 16, "sample_s": 60, "max_quote_age_s": 20,
            "track_until": "15:26", "delta_tol": 0.10, "strikes": 24, "same_stock_gap_min": 10, "slip": 0.01, "fee": 0.02}
SCHEMA = """CREATE TABLE IF NOT EXISTS lab_contracts(id TEXT PRIMARY KEY, tape_id TEXT, day TEXT, ticker TEXT, family TEXT,
  side TEXT, bucket TEXT, target_delta REAL, symbol TEXT, exp TEXT, dte INTEGER, strike REAL, delta0 REAL, bid0 REAL, ask0 REAL,
  entry REAL, line REAL, started TEXT, hit_t TEXT, hit_bid REAL, min_bid REAL, max_bid REAL, last_t TEXT, samples TEXT,
  status TEXT, exit_t TEXT, exit_bid REAL, pnl_line REAL, pnl_hold REAL, pct_line REAL, pct_hold REAL, line_first INTEGER,
  resolved_at TEXT, version TEXT)"""
_state = {"tokens": 0.0, "t": None, "tracked": None, "last_sample": {}, "recent": {}}


def cfg():
    c = dict(DEFAULTS)
    c.update(core.policy().get("contract_lab") or {})
    return c


def _schema():
    store.x(SCHEMA)
    store.x("CREATE INDEX IF NOT EXISTS lab_contracts_day ON lab_contracts(day, status)")


def _token(c):
    t = time.time()
    if _state["t"] is None:
        _state["tokens"] = float(c["starts_per_min"])
    _state["tokens"] = min(_state["tokens"] + (t - (_state["t"] or t)) * c["starts_per_min"] / 60, c["starts_per_min"])
    _state["t"] = t
    if _state["tokens"] < 1:
        return False
    _state["tokens"] -= 1
    return True


def line_for(entry, c=None):
    """The 20% planned-loss line from the actual entry, exactly as the strict paper ledgers compute it."""
    c = c or cfg()
    cap = core.policy()["risk"]["stop_cap_pct"]
    return core.cents_up(entry * (1 - cap) + c["slip"] + 2 * c["fee"] / 100)


def pick(rows, side, today, now, c=None):
    """One contract per (expiry bucket, target delta), or a reason it couldn't be picked. Returns [(bucket, target, row|None, why)]."""
    c = c or cfg()
    good = []
    for r in rows or []:
        bid, ask, d = r.get("bid") or 0, r.get("ask") or 0, r.get("delta")
        if bid <= 0 or ask <= 0 or ask < bid or d is None or not r.get("exp"):
            continue
        ts = r.get("ts")
        try:
            age = (now - datetime.fromisoformat(str(ts))).total_seconds() if ts else None
        except ValueError:
            age = None
        if age is None or age > c["max_quote_age_s"]:
            continue
        dte = (date.fromisoformat(r["exp"]) - today).days
        good.append(dict(r, dte=dte))
    out = []
    for name, lo, hi in BUCKETS:
        inb = [r for r in good if lo <= r["dte"] <= hi]
        if not inb:
            for tg in DELTAS:
                out.append((name, tg, None, "no expiry with fresh two-sided quotes in this range"))
            continue
        first = min(r["dte"] for r in inb)
        inb = [r for r in inb if r["dte"] == first]                     # the nearest expiry inside the bucket
        for tg in DELTAS:
            best = min(inb, key=lambda r: abs(abs(r["delta"]) - tg))
            if abs(abs(best["delta"]) - tg) > c["delta_tol"]:
                out.append((name, tg, None, f"no strike near delta {tg} (closest {abs(best['delta']):.2f})"))
            else:
                out.append((name, tg, best, None))
    return out


def start(sig, now, fetch=None, c=None):
    """Begin following up to 12 contracts for one live signal. Returns how many were started (or a reason)."""
    c = c or cfg()
    if not c["enabled"]:
        return "off"
    _schema()
    t, side = sig["ticker"], sig["side"]
    key = f"{t}|{side}"
    last = _state["recent"].get(key)
    if last and (now - last).total_seconds() < c["same_stock_gap_min"] * 60:
        return "same stock and side followed in the last few minutes"
    tracked = store.q("SELECT COUNT(DISTINCT tape_id) n FROM lab_contracts WHERE day=? AND status='TRACKING'", (str(now.date()),))[0]["n"]
    if tracked >= c["max_tracked_signals"]:
        return "the contract lab is following its maximum number of signals"
    if not _token(c):
        return "contract lab request budget for this minute used"
    if fetch is None:
        import scanner
        fetch = scanner._fetch
    rows, err = fetch.chain(t, side, now.date().isoformat(), (now.date() + timedelta(days=10)).isoformat(), c["strikes"])
    picks = pick(rows, side, now.date(), now, c)
    n = 0
    for bucket, tg, r, why in picks:
        cid = f"{sig['id']}|{bucket}|{tg}"
        if r is None:
            store.x("INSERT OR IGNORE INTO lab_contracts(id, tape_id, day, ticker, family, side, bucket, target_delta, status, "
                    "started, version) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, sig["id"], str(now.date()), t, sig["family"], side, bucket, tg, "NOT PICKED: " + why,
                     now.isoformat(timespec="seconds"), VERSION))
            continue
        entry = round(r["ask"] + c["slip"], 4)
        store.x("INSERT OR IGNORE INTO lab_contracts(id, tape_id, day, ticker, family, side, bucket, target_delta, symbol, exp, dte, "
                "strike, delta0, bid0, ask0, entry, line, started, min_bid, max_bid, last_t, samples, status, version) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, sig["id"], str(now.date()), t, sig["family"], side, bucket, tg, r["symbol"], r["exp"], r["dte"],
                 r.get("strike"), r["delta"], r["bid"], r["ask"], entry, line_for(entry, c), now.isoformat(timespec="seconds"),
                 r["bid"], r["bid"], now.isoformat(timespec="seconds"),
                 json.dumps([[now.isoformat(timespec="seconds"), r["bid"], r["ask"]]]), "TRACKING", VERSION))
        n += 1
    _state["recent"][key] = now
    _state["tracked"] = None
    return n if n else ("no contract could be picked: " + (err or "empty chain"))


def _tracked(day):
    if _state["tracked"] is None:
        _state["tracked"] = store.q("SELECT * FROM lab_contracts WHERE day=? AND status='TRACKING'", (day,))
    return _state["tracked"]


def poll(now=None, c=None):
    """One batched quote request for every followed contract; record the 20% line touch, best/worst bids, a sample a
    minute. Stops following at track_until (or when the session's options market is closed for that contract)."""
    import marketdata
    c = c or cfg()
    now = now or core.now_et()
    _schema()
    day = str(now.date())
    rows = _tracked(day)
    stale = store.q("SELECT id FROM lab_contracts WHERE day<? AND status='TRACKING'", (day,))
    for r in stale:
        store.x("UPDATE lab_contracts SET status='TRACKED' WHERE id=?", (r["id"],))
    if not rows:
        return 0
    if now.strftime("%H:%M") >= c["track_until"]:
        store.x("UPDATE lab_contracts SET status='TRACKED' WHERE day=? AND status='TRACKING'", (day,))
        _state["tracked"] = None
        return 0
    got, _err = marketdata.option_quotes([r["symbol"] for r in rows])
    ts = now.isoformat(timespec="seconds")
    n = 0
    for r in rows:
        q = got.get(r["symbol"])
        if not q or q.get("bid") is None or not q.get("executable"):
            continue
        bid, ask = float(q["bid"]), q.get("ask")
        upd = {}
        if bid < (r["min_bid"] if r["min_bid"] is not None else 1e9):
            upd["min_bid"] = r["min_bid"] = bid
        if bid > (r["max_bid"] if r["max_bid"] is not None else -1):
            upd["max_bid"] = r["max_bid"] = bid
        if not r.get("hit_t") and bid <= r["line"]:
            upd["hit_t"], upd["hit_bid"] = r["hit_t"], r["hit_bid"] = ts, bid
        last = _state["last_sample"].get(r["id"]) or 0
        if time.time() - last >= c["sample_s"]:
            smp = json.loads(r.get("samples") or "[]")
            smp.append([ts, bid, ask])
            upd["samples"] = r["samples"] = json.dumps(smp)
            upd["last_t"] = ts
            _state["last_sample"][r["id"]] = time.time()
        if upd:
            sets = ", ".join(f"{k}=?" for k in upd)
            store.x(f"UPDATE lab_contracts SET {sets} WHERE id=?", tuple(upd.values()) + (r["id"],))
            n += 1
    return n


def _bid_at(samples, t, hit=None):
    """The first sampled bid at or after time t (None if the last sample is more than 3 minutes before it)."""
    for s in samples:
        if s[0] >= t:
            return s[1], s[0]
    if samples and (pd.Timestamp(t) - pd.Timestamp(samples[-1][0])).total_seconds() <= 180:
        return samples[-1][1], samples[-1][0]
    return None, None


def resolve(day, c=None):
    """Score every followed contract whose signal has a resolved stock outcome (the lab's shared yardstick)."""
    c = c or cfg()
    _schema()
    rows = store.q("SELECT k.*, t.exit_at, t.r, t.status tape_status FROM lab_contracts k JOIN lab_tape t ON t.id = k.tape_id "
                   "WHERE k.day=? AND k.status IN ('TRACKED','TRACKING') AND t.status != 'OPEN'", (str(day),))
    n = 0
    for r in rows:
        upd = {"resolved_at": store.ts()}
        if r["tape_status"] != "DONE" or not r["exit_at"]:
            upd["status"] = f"NO STOCK OUTCOME ({r['tape_status']})"
        else:
            smp = json.loads(r["samples"] or "[]")
            exit_t = pd.Timestamp(r["exit_at"]).isoformat()
            bid, at = _bid_at(smp, exit_t)
            if bid is None:
                upd["status"] = "NO QUOTE AT THE STOCK EXIT"
            else:
                fee2 = 2 * c["fee"]
                prem = r["entry"] * 100
                hold = round((max(0.0, bid - c["slip"]) - r["entry"]) * 100 - fee2, 2)
                first = bool(r["hit_t"] and r["hit_t"] <= exit_t)
                line_px = (r["hit_bid"] if first else bid)
                withline = round((max(0.0, line_px - c["slip"]) - r["entry"]) * 100 - fee2, 2)
                upd.update(status="DONE", exit_t=at, exit_bid=bid, pnl_hold=hold, pnl_line=withline, line_first=1 if first else 0,
                           pct_hold=round(hold / prem * 100, 1), pct_line=round(withline / prem * 100, 1))
        sets = ", ".join(f"{k}=?" for k in upd)
        store.x(f"UPDATE lab_contracts SET {sets} WHERE id=?", tuple(upd.values()) + (r["id"],))
        n += 1
    return n


def report(family=None, since=None, min_n=30, min_days=10):
    """By contract choice (expiry x delta), overall or for one strategy: how each choice converted the same signals."""
    _schema()
    q = ("SELECT k.*, t.r stock_r FROM lab_contracts k JOIN lab_tape t ON t.id = k.tape_id WHERE k.status='DONE'")
    args = []
    if family:
        q += " AND k.family=?"
        args.append(family)
    if since:
        q += " AND k.day>=?"
        args.append(since)
    rows = store.q(q, tuple(args))
    groups = {}
    for r in rows:
        groups.setdefault((r["bucket"], r["target_delta"]), []).append(r)
    order = {b[0]: i for i, b in enumerate(BUCKETS)}
    out = []
    for (b, tg), rs in sorted(groups.items(), key=lambda kv: (order.get(kv[0][0], 9), kv[0][1])):
        n = len(rs)
        days = len({r["day"] for r in rs})
        mean = lambda k, d=2: round(sum(r[k] for r in rs) / n, d)
        out.append({"bucket": b, "delta": tg, "n": n, "days": days, "won_line": round(100 * sum(1 for r in rs if r["pnl_line"] > 0) / n, 1),
                    "avg_line": mean("pnl_line"), "avg_hold": mean("pnl_hold"), "pct_line": mean("pct_line", 1), "pct_hold": mean("pct_hold", 1),
                    "line_first": round(100 * sum(r["line_first"] for r in rs) / n, 1),
                    "avg_premium": round(sum(r["entry"] for r in rs) / n * 100, 2),
                    "stock_r": round(sum(r["stock_r"] for r in rs if r["stock_r"] is not None) / max(1, sum(1 for r in rs if r["stock_r"] is not None)), 3),
                    "too_few": n < min_n or days < min_days})
    nots = store.q("SELECT status, COUNT(*) n FROM lab_contracts WHERE status LIKE 'NOT PICKED%'" + (" AND family=?" if family else "")
                   + " GROUP BY status ORDER BY n DESC LIMIT 6", (family,) if family else ())
    return {"rows": out, "signals": len({r["tape_id"] for r in rows}), "not_picked": nots, "version": VERSION,
            "note": ("Each signal's contracts are scored at the moment its stock trade ended under the lab's shared yardstick. "
                     "Entry = the ask + $0.01, exit = the bid - $0.01, $0.02 fees per side, 1 contract. 'With the 20% line' exits "
                     "at the line if the bid touched it first. Nothing was filled; these are followed real quotes. Rows under "
                     f"{min_n} contracts or {min_days} days are too few.")}


def status():
    _schema()
    day = core.now_et().strftime("%Y-%m-%d")
    r = store.q("SELECT COUNT(DISTINCT tape_id) s, COUNT(*) n, SUM(CASE WHEN status='TRACKING' THEN 1 ELSE 0 END) live FROM lab_contracts "
                "WHERE day=? AND symbol IS NOT NULL", (day,))[0]
    return {"signals_today": r["s"], "contracts_today": r["n"], "following_now": r["live"] or 0}
