"""store.py - the desk's single record (SQLite). Events are append-only; positions/watches/plans are current state.

Ledgers are kept apart: 'real' = what Nick reports from Robinhood (never verified by us),
'paper' = Alpaca paper orders the engine actually placed.
"""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import core

DB = core.HERE / "journal" / "desk.db"
_lock = threading.RLock()
_conn = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, ledger TEXT,
  ref TEXT, text TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS positions(id TEXT PRIMARY KEY, ledger TEXT, date TEXT, ticker TEXT, contract TEXT,
  symbol TEXT, side TEXT, qty_init INTEGER, qty_open INTEGER, fill REAL, opened TEXT, closed TEXT,
  status TEXT, setup_id TEXT, grade TEXT, setup TEXT, plan TEXT, realized REAL DEFAULT 0, mfe REAL DEFAULT 0,
  mae REAL DEFAULT 0, policy_version TEXT, verified TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS orders(client_id TEXT PRIMARY KEY, position_id TEXT, ts TEXT, side TEXT, qty INTEGER,
  status TEXT, broker_id TEXT, filled_qty INTEGER DEFAULT 0, filled_price REAL, reason TEXT);
CREATE TABLE IF NOT EXISTS watches(id TEXT PRIMARY KEY, ticker TEXT, side TEXT, created TEXT, expires TEXT,
  status TEXT, plan TEXT, last_state TEXT);
CREATE TABLE IF NOT EXISTS opportunities(id TEXT PRIMARY KEY, date TEXT, ts TEXT, ticker TEXT, side TEXT,
  setup TEXT, grade TEXT, decision TEXT, reason TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS journal(date TEXT PRIMARY KEY, notes TEXT, summary TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS lessons(id TEXT PRIMARY KEY, created TEXT, status TEXT, text TEXT, evidence TEXT,
  setup TEXT, sample INTEGER);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
"""


def conn():
    global _conn
    with _lock:
        if _conn is None:
            DB.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(DB, check_same_thread=False, isolation_level=None)
            _conn.row_factory = sqlite3.Row
            _conn.executescript(SCHEMA)
        return _conn


def q(sql, args=()):
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


def x(sql, args=()):
    with _lock:
        return conn().execute(sql, args)


def ts():
    return core.now_et().isoformat(timespec="seconds")


def new_id(prefix):
    return f"{prefix}-{core.now_et().strftime('%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


# ---------------- events ----------------
def event(kind, text, ledger="", ref="", data=None):
    x("INSERT INTO events(ts,kind,ledger,ref,text,data) VALUES(?,?,?,?,?,?)",
      (ts(), kind, ledger, ref, text, json.dumps(data or {})))
    return text


def events_since(seq, limit=200):
    return q("SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?", (seq, limit))


def last_seq():
    r = q("SELECT MAX(seq) m FROM events")
    return r[0]["m"] or 0


# ---------------- kv ----------------
def kv_get(k, default=None):
    r = q("SELECT v FROM kv WHERE k=?", (k,))
    return json.loads(r[0]["v"]) if r else default


def kv_set(k, v):
    x("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, json.dumps(v)))


# ---------------- positions ----------------
def pos_get(pid):
    r = q("SELECT * FROM positions WHERE id=?", (pid,))
    return _dec(r[0]) if r else None


def _dec(p):
    p["plan"] = json.loads(p["plan"] or "{}")
    return p


def positions(ledger=None, status=None, day=None):
    sql, a = "SELECT * FROM positions WHERE 1=1", []
    if ledger:
        sql += " AND ledger=?"; a.append(ledger)
    if status:
        sql += " AND status=?"; a.append(status)
    if day:
        sql += " AND date=?"; a.append(day)
    return [_dec(p) for p in q(sql + " ORDER BY opened", a)]


def pos_save(p):
    d = dict(p)
    d["plan"] = json.dumps(d.get("plan") or {})
    cols = list(d)
    x(f"INSERT INTO positions({','.join(cols)}) VALUES({','.join('?' * len(cols))}) "
      f"ON CONFLICT(id) DO UPDATE SET {','.join(f'{c}=excluded.{c}' for c in cols if c != 'id')}",
      [d[c] for c in cols])
    return p


def ledger_stats(ledger, day=None, since=None):
    """Realized P&L for a ledger on a day (or since a date), plus trade counts."""
    if day:
        rows = q("SELECT realized, status, qty_open FROM positions WHERE ledger=? AND date=?", (ledger, day))
    else:
        rows = q("SELECT realized, status, qty_open FROM positions WHERE ledger=? AND date>=?", (ledger, since))
    return round(sum(r["realized"] or 0 for r in rows), 2), len(rows)


# ---------------- journal / lessons ----------------
def journal_get(day):
    r = q("SELECT * FROM journal WHERE date=?", (day,))
    if not r:
        return {"date": day, "notes": {}, "summary": {}, "updated": None}
    j = r[0]
    return {"date": day, "notes": json.loads(j["notes"] or "{}"), "summary": json.loads(j["summary"] or "{}"),
            "updated": j["updated"]}


def journal_set(day, notes=None, summary=None):
    cur = journal_get(day)
    n = cur["notes"] if notes is None else {**cur["notes"], **notes}
    s = cur["summary"] if summary is None else summary  # summaries never touch notes
    x("INSERT INTO journal(date,notes,summary,updated) VALUES(?,?,?,?) ON CONFLICT(date) DO UPDATE SET "
      "notes=excluded.notes, summary=excluded.summary, updated=excluded.updated",
      (day, json.dumps(n), json.dumps(s), ts()))
    return journal_get(day)
