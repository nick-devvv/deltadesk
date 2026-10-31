"""v4store.py - the v4 paper ledgers' own record: positions of any kind (shares, single options, multi-leg spreads),
their fills and every decision (traded or not). Same SQLite file as the rest of the desk, separate tables, so no
legacy loop (engine._manage_open, the lab, the kill switch of v3) can ever pick up or misroute a v4 position.

Integrity rules (same as v3.5): a position id is <ledger>:<idea> and is inserted once (a retry, a restart or a second
detector can never open it twice); an exit re-reads the row inside the transaction (a stale copy can never close it
twice or reopen it); fills and the position change commit together.

P/L conventions (all net of the fees stored with the position):
  shares long   (exit - entry) x qty          shares short  (entry - exit) x qty
  long option   (exit - entry) x 100 x qty    credit spread (credit - debit) x 100 x qty
"""
import json
import sqlite3

import core
import store

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS v4_positions(id TEXT PRIMARY KEY, ledger TEXT, book TEXT, kind TEXT, date TEXT, ticker TEXT,
       direction TEXT, side TEXT, qty REAL, entry_px REAL, entry_t TEXT, signal_t TEXT, quote_t TEXT, exit_px REAL, exit_t TEXT,
       exit_reason TEXT, status TEXT, realized REAL DEFAULT 0, fees REAL DEFAULT 0, risk_usd REAL, max_loss REAL, r_mult REAL,
       mfe REAL DEFAULT 0, mae REAL DEFAULT 0, legs TEXT, plan TEXT, version TEXT, parent_id TEXT, exec_model TEXT)""",
    "CREATE INDEX IF NOT EXISTS v4pos_led ON v4_positions(ledger, status)",
    "CREATE INDEX IF NOT EXISTS v4pos_day ON v4_positions(date)",
    """CREATE TABLE IF NOT EXISTS v4_fills(seq INTEGER PRIMARY KEY AUTOINCREMENT, position_id TEXT, ts TEXT, action TEXT,
       price REAL, qty REAL, legs TEXT, quote_t TEXT, reason TEXT)""",
    """CREATE TABLE IF NOT EXISTS v4_decisions(id TEXT PRIMARY KEY, ts TEXT, date TEXT, ledger TEXT, ticker TEXT, kind TEXT,
       decision TEXT, reasons TEXT, data TEXT, version TEXT)""",
    "CREATE INDEX IF NOT EXISTS v4dec_day ON v4_decisions(date, ledger)",
)
_ready = {"db": None}

EXEC = {"noise1": "exec1 as the noise ledger: buy ask + max($0.01, half spread), sell bid - same, $0.02/contract/side",
        "bidask065": "options at the quote: buy ask, sell bid, $0.65/contract/side",
        "spread065": "spreads: open credit = shorts at bid - longs at ask; close debit = shorts at ask - longs at bid; $0.65/contract/side",
        "shares1": "shares: buy ask + $0.01, sell bid - $0.01, no commission"}


def schema():
    db = str(store.DB)
    if _ready["db"] == db and store._conn is not None:
        return
    for s in SCHEMA:
        store.x(s)
    _ready["db"] = db


def _dec(r):
    r = dict(r)
    for k in ("legs", "plan"):
        r[k] = json.loads(r[k]) if r.get(k) else ({} if k == "plan" else [])
    return r


def get(pid):
    schema()
    r = store.q("SELECT * FROM v4_positions WHERE id=?", (pid,))
    return _dec(r[0]) if r else None


def positions(ledger=None, status=None, day=None, book=None, ledgers=None):
    schema()
    sql, a = "SELECT * FROM v4_positions WHERE 1=1", []
    for col, v in (("ledger", ledger), ("status", status), ("date", day), ("book", book)):
        if v is not None:
            sql += f" AND {col}=?"
            a.append(v)
    if ledgers:
        sql += f" AND ledger IN ({','.join('?' * len(ledgers))})"
        a += list(ledgers)
    return [_dec(r) for r in store.q(sql + " ORDER BY entry_t", tuple(a))]


def open_position(rec, fill_reason="open"):
    """Insert a new position plus its opening fill and an event, atomically. Returns (id, None) or (None, why)."""
    schema()
    d = dict(rec)
    d.setdefault("status", "OPEN")
    d.setdefault("realized", 0.0)
    d["legs"] = json.dumps(d.get("legs") or [], default=str)
    d["plan"] = json.dumps(d.get("plan") or {}, default=str)
    cols = list(d)
    try:
        with store.tx():
            if store.q("SELECT id FROM v4_positions WHERE id=?", (d["id"],)):
                return None, f"already opened as {d['id']} (a retry never opens twice)"
            store.x(f"INSERT INTO v4_positions({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [d[c] for c in cols])
            store.x("INSERT INTO v4_fills(position_id, ts, action, price, qty, legs, quote_t, reason) VALUES(?,?,?,?,?,?,?,?)",
                    (d["id"], store.ts(), "open", d.get("entry_px"), d.get("qty"), d["legs"], d.get("quote_t"), fill_reason))
            store.event("v4", f"{d['ledger'].upper()} OPEN {d.get('kind')} {d.get('ticker')} {_desc(rec)} @ {d.get('entry_px')} "
                        f"(paper, simulated fill)", d["ledger"], d["id"])
    except sqlite3.IntegrityError:
        return None, "already opened (integrity)"
    return d["id"], None


def _desc(rec):
    legs = rec.get("legs") or []
    if rec.get("kind") == "shares":
        return f"{rec.get('side')} {rec.get('qty')} sh"
    return " / ".join(f"{'-' if l.get('action') == 'sell' else '+'}{l.get('label') or l.get('symbol')}" for l in legs)


def pnl(p, exit_px, qty=None):
    q = p["qty"] if qty is None else qty
    k = p["kind"]
    if k == "shares":
        return (exit_px - p["entry_px"]) * q if p["side"] == "long" else (p["entry_px"] - exit_px) * q
    if k == "spread":
        return (p["entry_px"] - exit_px) * 100 * q
    return (exit_px - p["entry_px"]) * 100 * q


def close_position(pid, exit_px, reason, exit_fees=0.0, quote_t=None, legs=None, extra=None):
    """Close at exit_px (net of exit_fees). Returns (realized, None) or (None, why). Never closes twice."""
    schema()
    with store.tx():
        r = store.q("SELECT * FROM v4_positions WHERE id=?", (pid,))
        if not r:
            return None, "no such position"
        p = _dec(r[0])
        if p["status"] != "OPEN":
            return None, "already closed (a retry never closes twice)"
        fees = round((p["fees"] or 0) + exit_fees, 4)
        realized = round(pnl(p, exit_px) - fees, 2)
        rm = round(realized / p["risk_usd"], 3) if p.get("risk_usd") else None
        plan = dict(p["plan"], **(extra or {}))
        plan.pop("pending_exit", None)
        store.x("UPDATE v4_positions SET status='CLOSED', exit_px=?, exit_t=?, exit_reason=?, realized=?, fees=?, r_mult=?, plan=? "
                "WHERE id=? AND status='OPEN'", (round(exit_px, 4), store.ts(), reason[:300], realized, fees, rm,
                                                  json.dumps(plan, default=str), pid))
        store.x("INSERT INTO v4_fills(position_id, ts, action, price, qty, legs, quote_t, reason) VALUES(?,?,?,?,?,?,?,?)",
                (pid, store.ts(), "close", round(exit_px, 4), p["qty"], json.dumps(legs or [], default=str), quote_t, reason[:300]))
        store.event("v4", f"{p['ledger'].upper()} CLOSE {p['ticker']} @ {exit_px:.4g}: {reason} | P/L ${realized:+.2f} net (paper)",
                    p["ledger"], pid)
    return realized, None


def void(pid, reason):
    """An open position that can no longer be priced honestly (an option that expired while the desk was down): status
    VOID, excluded from every result, listed for review. Never used for a position that has a valid quote."""
    schema()
    with store.tx():
        r = store.q("SELECT ledger, status FROM v4_positions WHERE id=?", (pid,))
        if not r or r[0]["status"] != "OPEN":
            return False
        store.x("UPDATE v4_positions SET status='VOID', exit_t=?, exit_reason=? WHERE id=? AND status='OPEN'", (store.ts(), reason[:300], pid))
        store.event("v4", f"{r[0]['ledger'].upper()} VOID {pid}: {reason}", r[0]["ledger"], pid)
    return True


def update_plan(pid, **kv):
    """Merge fields into an OPEN position's plan (marks, mfe/mae, pending-exit notes). Closed rows are never edited."""
    schema()
    with store.tx():
        r = store.q("SELECT plan, status FROM v4_positions WHERE id=?", (pid,))
        if not r or r[0]["status"] != "OPEN":
            return False
        plan = json.loads(r[0]["plan"] or "{}")
        plan.update(kv)
        store.x("UPDATE v4_positions SET plan=? WHERE id=? AND status='OPEN'", (json.dumps(plan, default=str), pid))
    return True


def mark(pid, mfe=None, mae=None):
    schema()
    store.x("UPDATE v4_positions SET mfe=COALESCE(MAX(mfe, ?), mfe), mae=COALESCE(MIN(mae, ?), mae) WHERE id=? AND status='OPEN'",
            (mfe if mfe is not None else -1e18, mae if mae is not None else 1e18, pid))


def decide(did, ledger, ticker, decision, reasons=None, data=None, kind="check", version=None, replace=False):
    """Every decision, traded or not. A deterministic id means a restart re-deciding the same thing is a no-op
    (replace=True only for a decision that legitimately advances, e.g. WAIT -> ORDER)."""
    schema()
    verb = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
    store.x(f"{verb} INTO v4_decisions(id, ts, date, ledger, ticker, kind, decision, reasons, data, version) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (did, store.ts(), core.now_et().strftime("%Y-%m-%d"), ledger, ticker, kind, decision,
             json.dumps(list(reasons or []), default=str), json.dumps(data or {}, default=str), version))
    return did


def decisions(day=None, ledger=None, kind=None, limit=500):
    schema()
    sql, a = "SELECT * FROM v4_decisions WHERE 1=1", []
    for col, v in (("date", day), ("ledger", ledger), ("kind", kind)):
        if v is not None:
            sql += f" AND {col}=?"
            a.append(v)
    rows = store.q(sql + " ORDER BY ts DESC LIMIT ?", tuple(a) + (int(limit),))
    for r in rows:
        r["reasons"] = json.loads(r["reasons"] or "[]")
        r["data"] = json.loads(r["data"] or "{}")
    return rows


def decided(did):
    schema()
    return bool(store.q("SELECT id FROM v4_decisions WHERE id=?", (did,)))


# ---------------------------------------------------------------- fill prices (paper, simulated)
def option_costs(model, spread):
    """(slippage per contract in $/share, fee per contract per side in $)."""
    if model == "noise1":
        k = core.policy()["v3"]["contract"]
        return max(k["slippage_min"], (spread or 0) * k["slippage_spread_frac"]), k["fees_per_contract_side"]
    return 0.0, 0.65


def option_buy(q, model):
    slip, fee = option_costs(model, q["ask"] - q["bid"])
    return round(q["ask"] + slip, 4), fee


def option_sell(q, model):
    slip, fee = option_costs(model, q["ask"] - q["bid"])
    return round(max(0.0, q["bid"] - slip), 4), fee


SPREAD_FEE = 0.65


def spread_credit(legs, quotes):
    """Open credit per spread: short legs at the bid minus long legs at the ask."""
    c = 0.0
    for l in legs:
        q = quotes[l["symbol"]]
        c += q["bid"] if l["action"] == "sell" else -q["ask"]
    return round(c, 4)


def spread_debit(legs, quotes):
    """Close debit per spread: short legs at the ask minus long legs at the bid."""
    d = 0.0
    for l in legs:
        q = quotes[l["symbol"]]
        d += q["ask"] if l["action"] == "sell" else -q["bid"]
    return round(d, 4)


def share_buy(q):
    return round(q["ask"] + 0.01, 4)


def share_sell(q):
    return round(max(0.0, q["bid"] - 0.01), 4)
