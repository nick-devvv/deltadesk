"""contract_lab.py - which option contract turns a signal's stock move into option profit?

For every LIVE strategy-lab signal (seen within the lab's freshness window), up to 12 contracts are picked from the
real Schwab chain: expiry 0DTE / 1-2 days / 3-5 days / 6-10 days x delta 0.35 / 0.45 / 0.60 (the nearest expiry in
each bucket, the strike whose delta is closest to the target and within 0.10 of it, a two-sided quote no older than
20 s and not dated in the future). Each one is followed on real quotes until 3:26 PM ET: one batched request for all
of them every lab step. Nothing is filled or traded. After the close, each contract is scored at the moment the
signal's stock trade ended (the lab's shared yardstick):
  entry  = the ask when picked + $0.01, fees $0.02 per side (the strict paper model);
  held   = the bid of the first quote AFTER the stock exit, inside a declared window (90 s), - $0.01;
  with the 20% line = if a sampled bid touched your 20% planned-loss line first (same formula as the paper ledgers),
                      that bid - $0.01 instead.

v3.5 scorer (SCORER below) - what changed and why:
  * Every observation keeps two clocks: the provider's quote time and when the desk received it (lab_contract_quotes,
    append-only rows, not a JSON blob rewritten every minute).
  * A quote dated more than max_future_s in the future is rejected (clock skew up to that is tolerated and recorded).
  * The exit must be a real quote at or after the stock exit and no later than exit_window_s; otherwise the row is
    UNFILLED with the gap recorded. No quote from before the exit stands in, nothing is interpolated.
  * The contract entry is the chain sample; the stock's entry is the next 1-minute bar open. The gap (entry_lag_s) is
    recorded and shown: this is NOT a controlled paired comparison, and rows beyond max_entry_lag_s are kept out of it.
  * Two target deltas can pick the same physical contract: the bucket mapping is kept, but the copy is marked dup_of
    and is not counted as independent evidence.
  * The report reads ONE scorer version (old v3.4.2 rows never mix in silently), compares choices on the signals they
    have in common, and shows coverage and missingness per choice.
  * Throttles and de-duplication are rebuilt from the database, so a restart cannot double-follow a move.
Sampled bid extremes and sampled 20%-line touches are observed estimates between samples, not continuous-market
extremes or guaranteed fills.
"""
import json
import time
from datetime import date, datetime, timedelta

import pandas as pd

import core
import store

SCORER = "2026-10-31.v3.5-contracts2"
VERSION = SCORER
OLD_SCORERS = ("2026-10-30.v3.4.2-contracts1",)
BUCKETS = (("0DTE", 0, 0), ("1-2 days", 1, 2), ("3-5 days", 3, 5), ("6-10 days", 6, 10))
DELTAS = (0.35, 0.45, 0.60)
DEFAULTS = {"enabled": True, "starts_per_min": 4, "max_tracked_signals": 16, "sample_s": 20, "max_quote_age_s": 20,
            "track_until": "15:26", "delta_tol": 0.10, "strikes": 24, "same_stock_gap_min": 10, "slip": 0.01, "fee": 0.02,
            "exit_window_s": 90, "max_future_s": 5, "max_entry_lag_s": 90}
SCHEMA = """CREATE TABLE IF NOT EXISTS lab_contracts(id TEXT PRIMARY KEY, tape_id TEXT, day TEXT, ticker TEXT, family TEXT,
  side TEXT, bucket TEXT, target_delta REAL, symbol TEXT, exp TEXT, dte INTEGER, strike REAL, delta0 REAL, bid0 REAL, ask0 REAL,
  entry REAL, line REAL, started TEXT, hit_t TEXT, hit_bid REAL, min_bid REAL, max_bid REAL, last_t TEXT, samples TEXT,
  status TEXT, exit_t TEXT, exit_bid REAL, pnl_line REAL, pnl_hold REAL, pct_line REAL, pct_hold REAL, line_first INTEGER,
  resolved_at TEXT, version TEXT)"""
NEW_COLS = {"tape_entry_t": "TEXT", "entry_quote_t": "TEXT", "entry_recv_t": "TEXT", "entry_lag_s": "REAL", "entry_skew_s": "REAL",
            "dup_of": "TEXT", "exit_quote_t": "TEXT", "exit_gap_s": "REAL", "min_bid_held": "REAL", "max_bid_held": "REAL",
            "timing_ok": "INTEGER", "quality": "TEXT"}
QSCHEMA = """CREATE TABLE IF NOT EXISTS lab_contract_quotes(seq INTEGER PRIMARY KEY AUTOINCREMENT, cid TEXT NOT NULL,
  recv_t TEXT NOT NULL, quote_t TEXT, bid REAL, ask REAL, why TEXT)"""
_state = {"tokens": 0.0, "t": None, "tracked": None, "last_sample": {}, "recent": {}, "rejects": {}}


def cfg():
    c = dict(DEFAULTS)
    c.update(core.policy().get("contract_lab") or {})
    return c


def _schema():
    store.x(SCHEMA)
    store.x("CREATE INDEX IF NOT EXISTS lab_contracts_day ON lab_contracts(day, status)")
    have = {r["name"] for r in store.q("PRAGMA table_info(lab_contracts)")}
    for k, typ in NEW_COLS.items():
        if k not in have:
            store.x(f"ALTER TABLE lab_contracts ADD COLUMN {k} {typ}")
    store.x(QSCHEMA)
    store.x("CREATE INDEX IF NOT EXISTS lab_contract_quotes_cid ON lab_contract_quotes(cid, quote_t)")


def _ts(v):
    """Provider/stored time -> tz-aware ET Timestamp (ISO with or without offset, epoch ms, datetime). None if unknown."""
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (int, float)):
            t = pd.Timestamp(float(v), unit="ms", tz="UTC") if v > 1e11 else pd.Timestamp(float(v), unit="s", tz="UTC")
        else:
            t = pd.Timestamp(v)
    except (ValueError, TypeError):
        return None
    if t.tzinfo is None:
        t = t.tz_localize(core.ET)
    return t.tz_convert(core.ET)


def _iso(t):
    t = _ts(t)
    return t.isoformat() if t is not None else None


def _token(c, now):
    """Starts in the last minute, counted from the database (survives a restart)."""
    since = (_ts(now) - pd.Timedelta(seconds=60)).isoformat()
    n = store.q("SELECT COUNT(DISTINCT tape_id) n FROM lab_contracts WHERE started>=? AND started<=?", (since, _ts(now).isoformat()))[0]["n"]
    return n < c["starts_per_min"]


def line_for(entry, c=None):
    """The 20% planned-loss line from the actual entry, exactly as the strict paper ledgers compute it."""
    c = c or cfg()
    cap = core.policy()["risk"]["stop_cap_pct"]
    return core.cents_up(entry * (1 - cap) + c["slip"] + 2 * c["fee"] / 100)


def quote_age(qt, now):
    """Seconds old (negative = dated in the future)."""
    qt, now = _ts(qt), _ts(now)
    return None if qt is None or now is None else (now - qt).total_seconds()


def pick(rows, side, today, now, c=None):
    """One contract per (expiry bucket, target delta), or a reason it couldn't be picked. Returns [(bucket, target, row|None, why)]."""
    c = c or cfg()
    good = []
    rej = {"future-dated": 0, "stale": 0, "no quote time": 0}
    for r in rows or []:
        bid, ask, d = r.get("bid") or 0, r.get("ask") or 0, r.get("delta")
        if bid <= 0 or ask <= 0 or ask < bid or d is None or not r.get("exp"):
            continue
        age = quote_age(r.get("quote_time") or r.get("ts"), now)
        if age is None:
            rej["no quote time"] += 1
            continue
        if age < -c["max_future_s"]:
            rej["future-dated"] += 1                     # a quote from the future is bad data, not a fresh quote
            continue
        if age > c["max_quote_age_s"]:
            rej["stale"] += 1
            continue
        dte = (date.fromisoformat(r["exp"]) - today).days
        good.append(dict(r, dte=dte, quote_t=_iso(r.get("quote_time") or r.get("ts")), skew_s=round(min(0.0, age), 1)))
    _state["rejects"] = rej
    rtxt = ", ".join(f"{n} {k}" for k, n in rej.items() if n)
    out = []
    for name, lo, hi in BUCKETS:
        inb = [r for r in good if lo <= r["dte"] <= hi]
        if not inb:
            for tg in DELTAS:
                out.append((name, tg, None, "no expiry with fresh two-sided quotes in this range" + (f" (rejected: {rtxt})" if rtxt else "")))
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


def _q_insert(cid, recv_t, quote_t, bid, ask, why="sample"):
    store.x("INSERT INTO lab_contract_quotes(cid, recv_t, quote_t, bid, ask, why) VALUES(?,?,?,?,?,?)",
            (cid, _iso(recv_t), _iso(quote_t), bid, ask, why))


def start(sig, now, fetch=None, c=None):
    """Begin following up to 12 contracts for one live signal. Returns how many were started (or a reason)."""
    c = c or cfg()
    if not c["enabled"]:
        return "off"
    _schema()
    t, side = sig["ticker"], sig["side"]
    day = str(now.date())
    last = store.q("SELECT MAX(started) m FROM lab_contracts WHERE day=? AND ticker=? AND side=?", (day, t, side))[0]["m"]
    if last and 0 <= (_ts(now) - _ts(last)).total_seconds() < c["same_stock_gap_min"] * 60:
        return "same stock and side followed in the last few minutes"
    if store.q("SELECT 1 FROM lab_contracts WHERE tape_id=? LIMIT 1", (sig["id"],)):
        return "this signal is already followed"
    tracked = store.q("SELECT COUNT(DISTINCT tape_id) n FROM lab_contracts WHERE day=? AND status='TRACKING'", (day,))[0]["n"]
    if tracked >= c["max_tracked_signals"]:
        return "the contract lab is following its maximum number of signals"
    if not _token(c, now):
        return "contract lab request budget for this minute used"
    if fetch is None:
        import scanner
        fetch = scanner._fetch
    rows, err = fetch.chain(t, side, now.date().isoformat(), (now.date() + timedelta(days=10)).isoformat(), c["strikes"])
    picks = pick(rows, side, now.date(), now, c)
    tape_entry = _iso(sig.get("bar_end"))
    n, seen = 0, {}
    started = _iso(now)
    with store.tx():
        for bucket, tg, r, why in picks:
            cid = f"{sig['id']}|{bucket}|{tg}"
            if r is None:
                store.x("INSERT OR IGNORE INTO lab_contracts(id, tape_id, day, ticker, family, side, bucket, target_delta, status, "
                        "started, version, tape_entry_t) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (cid, sig["id"], day, t, sig["family"], side, bucket, tg, "NOT PICKED: " + why, started, SCORER, tape_entry))
                continue
            entry = round(r["ask"] + c["slip"], 4)
            lag = round((_ts(r["quote_t"]) - _ts(tape_entry)).total_seconds(), 1) if tape_entry and r.get("quote_t") else None
            dup = seen.get(r["symbol"])
            seen.setdefault(r["symbol"], cid)
            store.x("INSERT OR IGNORE INTO lab_contracts(id, tape_id, day, ticker, family, side, bucket, target_delta, symbol, exp, dte, "
                    "strike, delta0, bid0, ask0, entry, line, started, min_bid, max_bid, last_t, samples, status, version, tape_entry_t, "
                    "entry_quote_t, entry_recv_t, entry_lag_s, entry_skew_s, dup_of, timing_ok) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, sig["id"], day, t, sig["family"], side, bucket, tg, r["symbol"], r["exp"], r["dte"],
                     r.get("strike"), r["delta"], r["bid"], r["ask"], entry, line_for(entry, c), started,
                     r["bid"], r["bid"], started, None, "TRACKING", SCORER, tape_entry, r["quote_t"], started, lag, r.get("skew_s"),
                     dup, None if lag is None else 1 if abs(lag) <= c["max_entry_lag_s"] else 0))
            _q_insert(cid, now, r["quote_t"], r["bid"], r["ask"], "entry")
            n += 1
    _state["recent"][f"{t}|{side}"] = now
    _state["tracked"] = None
    return n if n else ("no contract could be picked: " + (err or "empty chain"))


def _tracked(day):
    """Today's followed contracts, cached per DAY (a cache from yesterday is never served after the rollover)."""
    cur = _state["tracked"]
    if not cur or cur[0] != day:
        _state["tracked"] = (day, store.q("SELECT * FROM lab_contracts WHERE day=? AND status='TRACKING'", (day,)))
    return _state["tracked"][1]


def _last_sample(cid):
    if cid not in _state["last_sample"]:
        r = store.q("SELECT MAX(recv_t) m FROM lab_contract_quotes WHERE cid=?", (cid,))[0]["m"]
        _state["last_sample"][cid] = _ts(r)
    return _state["last_sample"][cid]


def poll(now=None, c=None):
    """One batched quote request for every followed contract; record the 20% line touch, best/worst bids, and a quote
    row every sample_s (provider time + receipt time). Stops following at track_until."""
    import marketdata
    c = c or cfg()
    now = now or core.now_et()
    _schema()
    day = str(now.date())
    if store.q("SELECT 1 FROM lab_contracts WHERE day<? AND status='TRACKING' LIMIT 1", (day,)):
        store.x("UPDATE lab_contracts SET status='TRACKED' WHERE day<? AND status='TRACKING'", (day,))
    rows = _tracked(day)
    if not rows:
        return 0
    if now.strftime("%H:%M") >= c["track_until"]:
        store.x("UPDATE lab_contracts SET status='TRACKED' WHERE day=? AND status='TRACKING'", (day,))
        _state["tracked"] = None
        return 0
    got, _err = marketdata.option_quotes([r["symbol"] for r in rows])
    n = 0
    for r in rows:
        q = got.get(r["symbol"])
        if not q or q.get("bid") is None or not q.get("executable"):
            continue
        qt = _ts(q.get("quote_time")) or None
        recv = _ts(q.get("recv")) or _ts(now)
        age = quote_age(qt, now) if qt is not None else None
        if age is None or age < -c["max_future_s"] or age > c["max_quote_age_s"]:
            continue                                           # no provider time, future-dated or stale: not an observation
        bid, ask = float(q["bid"]), q.get("ask")
        upd = {}
        if bid < (r["min_bid"] if r["min_bid"] is not None else 1e9):
            upd["min_bid"] = r["min_bid"] = bid
        if bid > (r["max_bid"] if r["max_bid"] is not None else -1):
            upd["max_bid"] = r["max_bid"] = bid
        why = None
        if not r.get("hit_t") and bid <= r["line"]:
            upd["hit_t"], upd["hit_bid"] = r["hit_t"], r["hit_bid"] = qt.isoformat(), bid
            why = "20% line touch"
        ls = _last_sample(r["id"])
        if why or ls is None or (recv - ls).total_seconds() >= c["sample_s"]:
            _q_insert(r["id"], recv, qt, bid, ask, why or "sample")
            _state["last_sample"][r["id"]] = recv
            upd["last_t"] = recv.isoformat()
        if upd:
            sets = ", ".join(f"{k}=?" for k in upd)
            store.x(f"UPDATE lab_contracts SET {sets} WHERE id=?", tuple(upd.values()) + (r["id"],))
            n += 1
    return n


def _bid_at(samples, t, hit=None):
    """v3.4.2 scorer, kept ONLY to re-read old rows: first sample at/after t, else one up to 3 min before (flawed, see
    the module notes). New rows never use it."""
    for s in samples:
        if s[0] >= t:
            return s[1], s[0]
    if samples and (pd.Timestamp(t) - pd.Timestamp(samples[-1][0])).total_seconds() <= 180:
        return samples[-1][1], samples[-1][0]
    return None, None


def exit_quote(quotes, exit_t, c=None):
    """The first quote with a provider time in [exit, exit + exit_window_s] that was fresh when received.
    Returns (quote|None, gap_s|None). gap_s = seconds from the exit to the next quote seen at all (for UNFILLED rows)."""
    c = c or cfg()
    et = _ts(exit_t)
    nxt = None
    for q in quotes:
        qt = _ts(q["quote_t"])
        if qt is None or qt < et:
            continue
        gap = (qt - et).total_seconds()
        nxt = gap if nxt is None else min(nxt, gap)
        if gap <= c["exit_window_s"]:
            rv = _ts(q["recv_t"])
            if rv is None or (rv - qt).total_seconds() <= c["max_quote_age_s"]:
                return q, gap
    return None, nxt


def _score_v2(r, c):
    quotes = store.q("SELECT recv_t, quote_t, bid, ask, why FROM lab_contract_quotes WHERE cid=? ORDER BY quote_t, seq", (r["id"],))
    et = _ts(r["exit_at"])
    en = _ts(r["entry_quote_t"]) or _ts(r["started"])
    held = [q for q in quotes if _ts(q["quote_t"]) is not None and en <= _ts(q["quote_t"]) <= et]
    upd = {"min_bid_held": min((q["bid"] for q in held), default=None), "max_bid_held": max((q["bid"] for q in held), default=None)}
    hit = next((q for q in held if q["bid"] <= r["line"]), None)
    xq, gap = exit_quote(quotes, r["exit_at"], c)
    fee2 = 2 * c["fee"]
    prem = r["entry"] * 100
    line_known = hit is not None
    if xq is None:
        upd.update(status=f"UNFILLED: no quote within {c['exit_window_s']} s after the stock exit", exit_gap_s=gap,
                   line_first=1 if line_known else 0, quality="exit gap" + (f" {gap:.0f} s" if gap is not None else " (no later quote)"))
        if line_known:
            pl = round((max(0.0, hit["bid"] - c["slip"]) - r["entry"]) * 100 - fee2, 2)
            upd.update(pnl_line=pl, pct_line=round(pl / prem * 100, 1))
        return upd
    bid = xq["bid"]
    hold = round((max(0.0, bid - c["slip"]) - r["entry"]) * 100 - fee2, 2)
    line_px = hit["bid"] if line_known else bid
    withline = round((max(0.0, line_px - c["slip"]) - r["entry"]) * 100 - fee2, 2)
    upd.update(status="DONE", exit_t=xq["quote_t"], exit_quote_t=xq["quote_t"], exit_bid=bid, exit_gap_s=round(gap, 1),
               pnl_hold=hold, pnl_line=withline, line_first=1 if line_known else 0, hit_t=hit["quote_t"] if hit else None,
               hit_bid=hit["bid"] if hit else None, pct_hold=round(hold / prem * 100, 1), pct_line=round(withline / prem * 100, 1),
               quality="ok" if r.get("timing_ok") else "entry timing unknown" if r.get("timing_ok") is None else "entry timing mismatch")
    return upd


def _score_v1(r, c):
    smp = json.loads(r["samples"] or "[]")
    exit_t = pd.Timestamp(r["exit_at"]).isoformat()
    bid, at = _bid_at(smp, exit_t)
    if bid is None:
        return {"status": "NO QUOTE AT THE STOCK EXIT"}
    fee2 = 2 * c["fee"]
    prem = r["entry"] * 100
    hold = round((max(0.0, bid - c["slip"]) - r["entry"]) * 100 - fee2, 2)
    first = bool(r["hit_t"] and r["hit_t"] <= exit_t)
    line_px = (r["hit_bid"] if first else bid)
    withline = round((max(0.0, line_px - c["slip"]) - r["entry"]) * 100 - fee2, 2)
    return dict(status="DONE", exit_t=at, exit_bid=bid, pnl_hold=hold, pnl_line=withline, line_first=1 if first else 0,
                pct_hold=round(hold / prem * 100, 1), pct_line=round(withline / prem * 100, 1))


def resolve(day, c=None):
    """Score every followed contract whose signal has a resolved stock outcome (the lab's shared yardstick)."""
    c = c or cfg()
    _schema()
    rows = store.q("SELECT k.*, t.exit_at, t.r, t.status tape_status FROM lab_contracts k JOIN lab_tape t ON t.id = k.tape_id "
                   "WHERE k.day=? AND k.status IN ('TRACKED','TRACKING') AND k.entry IS NOT NULL AND t.status != 'OPEN'", (str(day),))
    n = 0
    for r in rows:
        if r["tape_status"] != "DONE" or not r["exit_at"]:
            upd = {"status": f"NO STOCK OUTCOME ({r['tape_status']})"}
        elif r["version"] in OLD_SCORERS:
            upd = _score_v1(r, c)
        else:
            upd = _score_v2(r, c)
        upd["resolved_at"] = store.ts()
        sets = ", ".join(f"{k}=?" for k in upd)
        store.x(f"UPDATE lab_contracts SET {sets} WHERE id=?", tuple(upd.values()) + (r["id"],))
        n += 1
    return n


def report(family=None, since=None, min_n=30, min_days=10, scorer=None):
    """By contract choice (expiry x delta) for ONE scorer version: how each choice converted the same signals.
    Independent contracts only (a duplicate pick of the same physical contract is shown, not counted), plus the same
    numbers on the signals every choice has in common, coverage and missingness."""
    _schema()
    scorer = scorer or SCORER
    base = "SELECT k.*, t.r stock_r FROM lab_contracts k LEFT JOIN lab_tape t ON t.id = k.tape_id WHERE k.version=?"
    args = [scorer]
    if family:
        base += " AND k.family=?"
        args.append(family)
    if since:
        base += " AND k.day>=?"
        args.append(since)
    allr = store.q(base, tuple(args))
    order = {b[0]: i for i, b in enumerate(BUCKETS)}
    cells = {}
    for r in allr:
        cells.setdefault((r["bucket"], r["target_delta"]), []).append(r)
    done = {k: [r for r in v if r["status"] == "DONE" and not r.get("dup_of")
                and (r.get("timing_ok") in (1, None) or r["version"] in OLD_SCORERS)] for k, v in cells.items()}
    sig_sets = [{r["tape_id"] for r in v} for v in done.values() if v]
    common = set.intersection(*sig_sets) if sig_sets else set()
    out = []
    for key in sorted(cells, key=lambda k: (order.get(k[0], 9), k[1])):
        b, tg = key
        rs, cl = done.get(key, []), cells[key]
        n = len(rs)
        days = len({r["day"] for r in rs})
        started = len({r["tape_id"] for r in cl})
        miss = {}
        for r in cl:
            if r["status"] != "DONE":
                k = r["status"].split(":")[0].split(" (")[0]
                miss[k] = miss.get(k, 0) + 1
        row = {"bucket": b, "delta": tg, "n": n, "days": days, "signals_started": started,
               "coverage_pct": round(100 * n / started, 1) if started else 0.0, "missing": miss,
               "duplicates": sum(1 for r in cl if r.get("dup_of")),
               "timing_mismatch": sum(1 for r in cl if r["status"] == "DONE" and r.get("timing_ok") == 0),
               "timing_unknown": sum(1 for r in cl if r["status"] == "DONE" and r.get("timing_ok") is None and r["version"] not in OLD_SCORERS),
               "too_few": n < min_n or days < min_days}
        if n:
            mean = lambda k, d=2, s=rs: round(sum(r[k] for r in s) / len(s), d)
            sr = [r["stock_r"] for r in rs if r["stock_r"] is not None]
            cm = [r for r in rs if r["tape_id"] in common]
            row.update(won_line=round(100 * sum(1 for r in rs if r["pnl_line"] > 0) / n, 1), avg_line=mean("pnl_line"),
                       avg_hold=mean("pnl_hold"), pct_line=mean("pct_line", 1), pct_hold=mean("pct_hold", 1),
                       line_first=round(100 * sum(r["line_first"] or 0 for r in rs) / n, 1),
                       avg_premium=round(sum(r["entry"] for r in rs) / n * 100, 2),
                       stock_r=round(sum(sr) / len(sr), 3) if sr else None,
                       n_common=len(cm), pct_line_common=mean("pct_line", 1, cm) if cm else None)
        else:
            row.update(won_line=0.0, avg_line=None, avg_hold=None, pct_line=0.0, pct_hold=0.0, line_first=0.0, avg_premium=None,
                       stock_r=None, n_common=0, pct_line_common=None)
        out.append(row)
    lags = sorted(abs(r["entry_lag_s"]) for r in allr if r.get("entry_lag_s") is not None)
    med = lags[len(lags) // 2] if lags else None
    gaps = sorted(r["exit_gap_s"] for r in allr if r["status"] == "DONE" and r.get("exit_gap_s") is not None)
    nots = store.q("SELECT status, COUNT(*) n FROM lab_contracts WHERE status LIKE 'NOT PICKED%' AND version=?" + (" AND family=?" if family else "")
                   + " GROUP BY status ORDER BY n DESC LIMIT 6", (scorer, family) if family else (scorer,))
    older = store.q("SELECT version, COUNT(*) n FROM lab_contracts WHERE version!=? AND status='DONE' GROUP BY version", (scorer,))
    return {"rows": out, "signals": len({r["tape_id"] for v in done.values() for r in v}), "common_signals": len(common),
            "not_picked": nots, "version": scorer, "other_versions": older,
            "timing": {"median_abs_entry_lag_s": med, "max_entry_lag_s": cfg()["max_entry_lag_s"],
                       "median_exit_gap_s": gaps[len(gaps) // 2] if gaps else None, "exit_window_s": cfg()["exit_window_s"]},
            "note": ("Scorer " + scorer + ". Each signal's contracts are scored when its stock trade ended under the lab's shared yardstick. "
                     "Entry = the ask + $0.01 when the chain was sampled; exit = the bid - $0.01 of the first quote within "
                     f"{cfg()['exit_window_s']} s after the stock exit (none = UNFILLED, shown as missing). $0.02 fees per side, 1 contract. "
                     "'With the 20% line' exits at the first sampled bid at or under the line. The stock enters at the next 1-minute "
                     f"bar open, the contract at the chain sample (median gap {med if med is not None else '?'} s): this is not a "
                     "controlled paired comparison. A second target delta that picked the same contract is not counted twice. "
                     f"Common signals across choices: {len(common)}. Nothing was filled. Rows under {min_n} contracts or {min_days} days are too few."
                     + (f" Older scorer rows ({', '.join(o['version'] for o in older)}) are kept apart." if older else ""))}


def status():
    _schema()
    day = core.now_et().strftime("%Y-%m-%d")
    r = store.q("SELECT COUNT(DISTINCT tape_id) s, COUNT(*) n, SUM(CASE WHEN status='TRACKING' THEN 1 ELSE 0 END) live FROM lab_contracts "
                "WHERE day=? AND symbol IS NOT NULL", (day,))[0]
    qn = store.q("SELECT COUNT(*) n FROM lab_contract_quotes WHERE recv_t>=?", (day,))[0]["n"]
    return {"signals_today": r["s"], "contracts_today": r["n"], "following_now": r["live"] or 0, "quotes_today": qn,
            "scorer": SCORER, "last_pick_rejects": _state.get("rejects") or {}}
