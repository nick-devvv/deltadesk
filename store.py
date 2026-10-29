"""store.py - the desk's single record (SQLite). Events are append-only; positions/watches/plans are current state.

Ledgers are kept apart:
  'real'     = what Nick reports from Robinhood (never verified by us; Schwab quotes are not his fills)
  'paper'    = v3 MAIN paper portfolio (internal simulated fills on Schwab quotes; 4 ideas/day; streak stop)
  'research' = v3 shadow research portfolio (same per-trade rules, keeps going after the main limits)
  'old'      = frozen old-policy shadow (2026-10-28.3 rules) for comparison
Older rows from v2 (Alpaca paper fills, Yahoo/Alpaca data) keep their original policy_version and verified tags.
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
CREATE TABLE IF NOT EXISTS ideas(portfolio TEXT, idea TEXT, date TEXT, ticker TEXT, side TEXT, created TEXT, status TEXT,
  position_id TEXT, PRIMARY KEY(portfolio, idea));
CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY, date TEXT, ts TEXT, decision_t TEXT, ticker TEXT, side TEXT,
  family TEXT, tags TEXT, portfolio TEXT, decision TEXT, reasons TEXT, limit_blocked TEXT, evidence TEXT, plan TEXT,
  policy_version TEXT, provider TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS bars_archive(ticker TEXT, open TEXT, o REAL, h REAL, l REAL, c REAL, v REAL, src TEXT,
  PRIMARY KEY(ticker, open, src));
CREATE TABLE IF NOT EXISTS quotes_archive(symbol TEXT, ts TEXT, bid REAL, ask REAL, last REAL, delta REAL, gamma REAL,
  iv REAL, quote_time TEXT, src TEXT, PRIMARY KEY(symbol, ts));
"""


def conn():
    global _conn
    with _lock:
        if _conn is None:
            DB.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(DB, check_same_thread=False, isolation_level=None, timeout=15)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")  # the Kronos test process writes too
            _conn.executescript(SCHEMA)
        return _conn


def q(sql, args=()):
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


def x(sql, args=()):
    with _lock:
        return conn().execute(sql, args)


def _jd(o):
    """JSON for numpy/pandas scalars (bool_, int64, float64, Timestamp)."""
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
    except Exception:
        pass
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


def ts():
    return core.now_et().isoformat(timespec="seconds")


def new_id(prefix):
    return f"{prefix}-{core.now_et().strftime('%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


# ---------------- events ----------------
def event(kind, text, ledger="", ref="", data=None):
    x("INSERT INTO events(ts,kind,ledger,ref,text,data) VALUES(?,?,?,?,?,?)",
      (ts(), kind, ledger, ref, text, json.dumps(data or {}, default=_jd)))
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
    x("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, json.dumps(v, default=_jd)))


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
    d["plan"] = json.dumps(d.get("plan") or {}, default=_jd)
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


# ---------------- journal analytics (calendar, breakdowns, per-trade review, CSV) ----------------
REVIEW_FIELDS = ("entry_reason", "exit_reason", "went_well", "improve", "next_time", "followed_plan", "mistakes")
MISTAKES = ("chased", "early entry", "no stop set", "moved stop", "oversized", "revenge trade", "held too long", "cut winner early", "ignored chop", "against trend")


def trade_note(pid, fields):
    p = pos_get(pid)
    if not p:
        return None
    try:
        cur = json.loads(p.get("notes") or "{}") if isinstance(p.get("notes"), str) else (p.get("notes") or {})
    except ValueError:
        cur = {"text": p.get("notes")}
    cur.update({k: str(v)[:2000] for k, v in fields.items() if k in REVIEW_FIELDS})
    x("UPDATE positions SET notes=? WHERE id=?", (json.dumps(cur), pid))
    return cur


def calendar(ledger, month):
    rows = q("SELECT date, COUNT(*) n, SUM(realized) pnl, SUM(CASE WHEN realized>0 THEN 1 ELSE 0 END) wins FROM positions "
             "WHERE ledger=? AND status='CLOSED' AND date LIKE ? GROUP BY date ORDER BY date", (ledger, month + "%"))
    return [{"date": r["date"], "trades": r["n"], "pnl": round(r["pnl"] or 0, 2), "wins": r["wins"]} for r in rows]


def breakdown(ledger, since):
    import core
    rows = q("SELECT ticker, setup, grade, realized, opened, notes FROM positions WHERE ledger=? AND status='CLOSED' AND date>=?", (ledger, since))
    out = {}
    for key, f in (("setup", lambda r: r["setup"] or "—"), ("time", lambda r: core.time_bucket((r["opened"] or "")[11:16] or "09:30")),
                   ("ticker", lambda r: r["ticker"]), ("grade", lambda r: r["grade"] or "—")):
        g = {}
        for r in rows:
            b = g.setdefault(f(r), {"n": 0, "wins": 0, "pnl": 0.0})
            b["n"] += 1
            b["wins"] += 1 if (r["realized"] or 0) > 0 else 0
            b["pnl"] += r["realized"] or 0
        out[key] = sorted(({"name": k, "n": v["n"], "win_rate": round(100 * v["wins"] / v["n"]), "pnl": round(v["pnl"], 2)}
                           for k, v in g.items()), key=lambda z: -z["pnl"])
    g = {}
    for r in rows:
        try:
            tags = [t.strip() for t in (json.loads(r["notes"] or "{}").get("mistakes") or "").split(",") if t.strip()]
        except (ValueError, AttributeError):
            tags = []
        for t in tags:
            b = g.setdefault(t, {"n": 0, "wins": 0, "pnl": 0.0})
            b["n"] += 1
            b["wins"] += 1 if (r["realized"] or 0) > 0 else 0
            b["pnl"] += r["realized"] or 0
    out["mistakes"] = sorted(({"name": k, "n": v["n"], "win_rate": round(100 * v["wins"] / v["n"]), "pnl": round(v["pnl"], 2)}
                              for k, v in g.items()), key=lambda z: -z["n"])
    return out


def export_csv(ledger):
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "ticker", "contract", "qty", "fill", "realized", "status", "setup", "grade", "opened", "closed",
                "best_pct", "worst_pct", *REVIEW_FIELDS])
    for p in q("SELECT * FROM positions WHERE ledger=? ORDER BY opened", (ledger,)):
        try:
            n = json.loads(p.get("notes") or "{}")
            n = n if isinstance(n, dict) else {}
        except ValueError:
            n = {}
        w.writerow([p["date"], p["ticker"], p["contract"], p["qty_init"], p["fill"], p["realized"], p["status"], p["setup"],
                    p["grade"], p["opened"], p["closed"], p["mfe"], p["mae"], *[n.get(k, "") for k in REVIEW_FIELDS]])
    return buf.getvalue()
