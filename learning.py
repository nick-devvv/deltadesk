"""learning.py - v3.5 (new): the opportunity / decision / trade journal and the measured improvement process.

What it stores (all in the desk's SQLite file, migrations below; nothing here can place an order):
  decision_events   APPEND-ONLY (UPDATE/DELETE refused by triggers). Every evaluation, decision, order, exit and
                    shadow outcome, with: schema version, stable event id, full ledger id, strategy id + version +
                    config hash, opportunity id (groups repeated evaluations of one setup), correlation ids (position,
                    order), event time / receipt time / decision time (UTC) plus ET clock and minutes since the open,
                    and explicit data-quality flags. Every write to the older `candidates` table is mirrored here by a
                    trigger, so INSERT OR REPLACE there can no longer erase history.
  run_manifests     each study / end-of-day job: parameters, source hashes, result summary.
  hypotheses (+ hypothesis_events, append-only)  preregistered: statement, metric, minimum evidence, the decision rule
                    and the validation window are fixed BEFORE the validating outcomes are looked at; the spec hash
                    makes a later edit visible. Status: OPEN -> VALIDATING -> PAPER CANDIDATE / REJECTED / OBSERVING.
  shadow_outcomes   rejected opportunities scored by ONE fixed hypothetical rule (SHADOW-1) on the underlying only;
                    never mixed with paper fills or real trades; options outcome = unknown.
  opportunity_summary  a DERIVED table rebuilt from decision_events (may be dropped and rebuilt any time).
End-of-day (eod): consistent SQLite backup (the sqlite backup API, WAL-safe) + integrity check, shadow outcomes,
summary rebuild. Resumable and idempotent (per-day flags; INSERT OR IGNORE on deterministic keys).
AI commentary is never stored here as fact; the review summaries are computed from these rows.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone

import core
import store

SCHEMA_VERSION = 1
SHADOW_RULE = "SHADOW-1"
SHADOW_SPEC = {"entry": "open of the first 1m bar after the decision time", "stop": "the plan's invalidation distance, else 0.5 x ATR5 "
               "at the decision", "exit": "2R target or stop on 1m high/low (touching both = stop), flat 15:25", "cost_per_share": 0.04,
               "options": "unknown (no option quotes in the shadow ledger)"}
MIGRATIONS = [
    """CREATE TABLE IF NOT EXISTS decision_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
      schema_version INTEGER NOT NULL, kind TEXT NOT NULL, ledger TEXT, strategy_id TEXT, strategy_version TEXT, config_hash TEXT,
      opportunity_id TEXT, episode_id TEXT, position_id TEXT, order_id TEXT, ticker TEXT, side TEXT, decision TEXT, reasons TEXT,
      event_t TEXT, recv_t TEXT, decision_t TEXT NOT NULL, et_clock TEXT, min_since_open INTEGER, snapshot TEXT, quality TEXT,
      source TEXT, recorded_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS de_day ON decision_events(decision_t)",
    "CREATE INDEX IF NOT EXISTS de_opp ON decision_events(opportunity_id)",
    "CREATE INDEX IF NOT EXISTS de_ledger ON decision_events(ledger, decision_t)",
    "CREATE TRIGGER IF NOT EXISTS de_no_update BEFORE UPDATE ON decision_events BEGIN SELECT RAISE(ABORT, 'decision events are append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS de_no_delete BEFORE DELETE ON decision_events BEGIN SELECT RAISE(ABORT, 'decision events are append-only'); END",
    # mirror every candidates write (INSERT and the insert half of INSERT OR REPLACE) into the append-only log
    """CREATE TRIGGER IF NOT EXISTS candidates_to_events AFTER INSERT ON candidates BEGIN
      INSERT OR IGNORE INTO decision_events(event_id, schema_version, kind, ledger, strategy_id, strategy_version, opportunity_id,
        ticker, side, decision, reasons, event_t, decision_t, snapshot, quality, source, recorded_at)
      VALUES('C-' || NEW.id || '-' || lower(hex(randomblob(6))), 1, 'DECISION', NEW.portfolio, NEW.family, NEW.policy_version,
        NEW.date || '|' || NEW.ticker || '|' || NEW.side || '|' || COALESCE(NEW.family, ''), NEW.ticker, NEW.side, NEW.decision,
        NEW.reasons, NEW.ts, COALESCE(NEW.decision_t, NEW.ts), NEW.plan, json_object('provider', NEW.provider, 'limit', NEW.limit_blocked),
        'candidates', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
    END""",
    """CREATE TABLE IF NOT EXISTS run_manifests(manifest_id TEXT PRIMARY KEY, kind TEXT, created TEXT, params TEXT, sources TEXT,
      versions TEXT, result TEXT)""",
    """CREATE TABLE IF NOT EXISTS hypotheses(id TEXT PRIMARY KEY, created TEXT, statement TEXT, metric TEXT, criteria TEXT,
      candidate TEXT, dev_window TEXT, validation_from TEXT, spec_hash TEXT, status TEXT)""",
    """CREATE TABLE IF NOT EXISTS hypothesis_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, hypothesis_id TEXT, t TEXT, status TEXT,
      why TEXT, evidence TEXT)""",
    "CREATE TRIGGER IF NOT EXISTS he_no_update BEFORE UPDATE ON hypothesis_events BEGIN SELECT RAISE(ABORT, 'append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS he_no_delete BEFORE DELETE ON hypothesis_events BEGIN SELECT RAISE(ABORT, 'append-only'); END",
    """CREATE TABLE IF NOT EXISTS shadow_outcomes(opportunity_id TEXT, rule TEXT, day TEXT, ticker TEXT, side TEXT, ledger TEXT,
      decision TEXT, decided_at TEXT, entry_t TEXT, entry REAL, stop_dist REAL, r REAL, why TEXT, options TEXT, recorded_at TEXT,
      PRIMARY KEY(opportunity_id, rule))""",
    """CREATE TABLE IF NOT EXISTS opportunity_summary(opportunity_id TEXT PRIMARY KEY, day TEXT, ticker TEXT, side TEXT, strategy TEXT,
      ledgers TEXT, evaluations INTEGER, first_t TEXT, last_t TEXT, final_decision TEXT, entered INTEGER, reasons TEXT)""",
]
ENTERED = ("ORDER", "FILLED", "AUTHORIZED")


def migrate():
    if store.kv_get("learning_schema") == SCHEMA_VERSION and getattr(migrate, "_done_for", None) == str(store.DB):
        return
    store.conn()
    for sql in MIGRATIONS:
        store.x(sql)
    if not store.kv_get("learning_backfilled"):
        # existing candidate rows are copied once, flagged: before v3.5 only the LATEST state of each candidate survived
        store.x("""INSERT OR IGNORE INTO decision_events(event_id, schema_version, kind, ledger, strategy_id, strategy_version, opportunity_id,
                   ticker, side, decision, reasons, event_t, decision_t, snapshot, quality, source, recorded_at)
                   SELECT 'CB-' || id, 1, 'DECISION', portfolio, family, policy_version,
                     date || '|' || ticker || '|' || side || '|' || COALESCE(family, ''), ticker, side, decision, reasons, ts,
                     COALESCE(decision_t, ts), plan, json_object('backfilled', 1, 'note', 'pre-v3.5: only the latest state survived'),
                     'candidates-backfill', strftime('%Y-%m-%dT%H:%M:%fZ', 'now') FROM candidates""")
        store.kv_set("learning_backfilled", True)
    store.kv_set("learning_schema", SCHEMA_VERSION)
    migrate._done_for = str(store.DB)


def _utc(t=None):
    t = t or datetime.now(timezone.utc)
    if isinstance(t, str):
        t = datetime.fromisoformat(t.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=core.ET)
    return t.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def config_hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def record_decision(ledger, ticker, side, strategy_id, strategy_version, decision, reasons, opportunity=None, episode=None,
                    position=None, order=None, snapshot=None, event_t=None, recv_t=None, quality=None, kind="DECISION", config=None,
                    now=None):
    """Append one event. Missing values are recorded as missing (quality flags), never filled from later data."""
    migrate()
    now = now or core.now_et()
    et = now.astimezone(core.ET)
    mso = (et.hour * 60 + et.minute) - (9 * 60 + 30)
    snap = snapshot or {}
    q = dict(quality or {})
    q.setdefault("missing", sorted(k for k, v in snap.items() if v is None))
    body = json.dumps(snap, sort_keys=True, default=str)
    eid = "E-" + hashlib.sha256(f"{ledger}|{opportunity}|{kind}|{decision}|{_utc(now)}|{body}".encode()).hexdigest()[:20]
    store.x("INSERT OR IGNORE INTO decision_events(event_id, schema_version, kind, ledger, strategy_id, strategy_version, config_hash, "
            "opportunity_id, episode_id, position_id, order_id, ticker, side, decision, reasons, event_t, recv_t, decision_t, et_clock, "
            "min_since_open, snapshot, quality, source, recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (eid, SCHEMA_VERSION, kind, ledger, strategy_id, strategy_version, config_hash(config) if config else None,
             opportunity or f"{et.date()}|{ticker}|{side}|{strategy_id}", episode, position, order, ticker, side, decision,
             json.dumps(reasons or []), _utc(event_t) if event_t else None, _utc(recv_t) if recv_t else None, _utc(now),
             et.strftime("%H:%M:%S"), mso, body, json.dumps(q), "learning", _utc()))
    return eid


# ---------------------------------------------------------------- manifests and hypotheses
def record_manifest(kind, params, result, root=None):
    migrate()
    import release
    m, src = release.manifest(kind, params, root)
    store.x("INSERT OR IGNORE INTO run_manifests(manifest_id, kind, created, params, sources, versions, result) VALUES(?,?,?,?,?,?,?)",
            (m["manifest_id"], kind, _utc(), json.dumps(params, default=str), json.dumps(src), json.dumps(m.get("components"), default=str),
             json.dumps(result, default=str)))
    return m["manifest_id"]


def register_hypothesis(hid, statement, metric, criteria, candidate, dev_window, validation_from, now=None):
    """Preregister. The spec (statement, metric, criteria, candidate, windows) is hashed; registering the same id with a
    different spec is refused - a change needs a new id."""
    migrate()
    spec = {"statement": statement, "metric": metric, "criteria": criteria, "candidate": candidate, "dev_window": dev_window,
            "validation_from": validation_from}
    h = config_hash(spec)
    old = store.q("SELECT spec_hash FROM hypotheses WHERE id=?", (hid,))
    if old:
        if old[0]["spec_hash"] != h:
            raise ValueError(f"{hid} is already registered with a different spec: register a new id instead")
        return hid
    t = _utc(now)
    with store.tx():
        store.x("INSERT INTO hypotheses(id, created, statement, metric, criteria, candidate, dev_window, validation_from, spec_hash, status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)", (hid, t, statement, metric, json.dumps(criteria), candidate, json.dumps(dev_window),
                                                 validation_from, h, "OPEN"))
        store.x("INSERT INTO hypothesis_events(hypothesis_id, t, status, why, evidence) VALUES(?,?,?,?,?)",
                (hid, t, "OPEN", "preregistered", json.dumps({"spec_hash": h})))
    return hid


def set_status(hid, status, why, evidence=None):
    """Status changes are appended with the evidence (run / event ids); the hypothesis row only mirrors the latest."""
    migrate()
    if status not in ("OPEN", "VALIDATING", "PAPER CANDIDATE", "REJECTED", "OBSERVING", "SUSPENDED"):
        raise ValueError("unknown status")
    with store.tx():
        store.x("INSERT INTO hypothesis_events(hypothesis_id, t, status, why, evidence) VALUES(?,?,?,?,?)",
                (hid, _utc(), status, why, json.dumps(evidence or {}, default=str)))
        store.x("UPDATE hypotheses SET status=? WHERE id=?", (status, hid))


INITIAL_HYPOTHESES = [
    ("H-ORBX-1", "The corrected ORB (ORBX-15-5, provisional parameters) on SPY/QQQ beats matched random entries after costs.",
     "mean R per trade minus matched-control mean R (fixed 2R yardstick, $0.04/share), session-clustered 95% CI",
     {"min_trades": 60, "min_sessions": 20, "rule": "lower 95% bound > 0 on the validation window only; else REJECTED or OBSERVING",
      "multiplicity": "1 entry definition x 4 exit variants, Holm-adjusted across the 4"}, "orb_retest 2026-10-31.orbx1",
     ["2026-10-08", "2026-10-29"], "2026-11-02"),
    ("H-ORBX-TRAIL", "Among ORBX exits, a trailing exit (swing or ATR) beats the fixed 2R exit on the same entries.",
     "paired mean R difference per trade (same entries), session-clustered 95% CI",
     {"min_trades": 60, "min_sessions": 20, "rule": "lower bound > 0 for the trail minus fixed 2R; Holm across 2 trails"},
     "orbx_swing / orbx_atr vs orbx_2r", ["2026-10-08", "2026-10-29"], "2026-11-02"),
    ("H-NEWS-1", "Verified-catalyst stocks with confirmed price/volume momentum (NEWS-MOM-1) beat matched controls after costs.",
     "mean R minus matched-control mean R (underlying), and option P/L on the forward paper ledger (observed quotes)",
     {"min_trades": 40, "min_sessions": 20, "rule": "lower 95% bound > 0 on forward data collected from 2026-11-02; no news backtest exists"},
     "news_momentum 2026-10-31.newsmom1", [], "2026-11-02"),
    ("H-REACH-1", "Reach odds (session bootstrap) for the underlying level an option needs are calibrated.",
     "Brier score of P(target before stop by the cutoff) vs the base rate, and a reliability table",
     {"min_predictions": 100, "rule": "Brier skill > 0 with a bootstrap 95% CI above 0; until then the odds are information only"},
     "underlying_first 2026-10-31.uf1", [], "2026-11-02"),
]


def seed_hypotheses():
    for h in INITIAL_HYPOTHESES:
        try:
            register_hypothesis(*h)
        except ValueError:
            pass


# ---------------------------------------------------------------- derived views
def rebuild_summary(day=None):
    """Group repeated evaluations of one setup (never counted as separate trades). Derived: safe to rebuild."""
    migrate()
    where, args = ("WHERE substr(decision_t,1,10)>=?", (day,)) if day else ("", ())
    rows = store.q(f"SELECT opportunity_id, ledger, ticker, side, strategy_id, decision, reasons, decision_t FROM decision_events {where} "
                   "ORDER BY decision_t", args)
    g = {}
    for r in rows:
        o = g.setdefault(r["opportunity_id"], {"ledgers": set(), "n": 0, "first": r["decision_t"], "last": r["decision_t"], "final": None,
                                               "entered": 0, "reasons": [], "ticker": r["ticker"], "side": r["side"], "strategy": r["strategy_id"]})
        o["ledgers"].add(r["ledger"] or "")
        o["n"] += 1
        o["last"] = r["decision_t"]
        o["final"] = r["decision"]
        if (r["decision"] or "") in ENTERED:
            o["entered"] = 1
        try:
            rs = json.loads(r["reasons"] or "[]")
        except ValueError:
            rs = [r["reasons"]]
        for x in rs[:2]:
            if x and x not in o["reasons"]:
                o["reasons"].append(str(x)[:160])
    with store.tx():
        for oid, o in g.items():
            store.x("INSERT OR REPLACE INTO opportunity_summary(opportunity_id, day, ticker, side, strategy, ledgers, evaluations, first_t, last_t, "
                    "final_decision, entered, reasons) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (oid, (o["first"] or "")[:10], o["ticker"], o["side"], o["strategy"], ",".join(sorted(o["ledgers"])), o["n"], o["first"],
                     o["last"], o["final"], o["entered"], json.dumps(o["reasons"][:6])))
    return len(g)


# ---------------------------------------------------------------- shadow ledger for rejections
def shadow_eod(day, bars_fn, now=None):
    """Score each REJECTED opportunity of `day` once under SHADOW-1 on the underlying (idempotent). bars_fn(day,
    ticker) -> that session's 1m bars or None. Unknown outcomes are stored as unknown, never imputed."""
    import pandas as pd

    import matched_benchmarks as MB
    migrate()
    rows = store.q("SELECT opportunity_id, MIN(decision_t) t, ticker, side, ledger, decision, snapshot FROM decision_events "
                   "WHERE substr(decision_t,1,10)=? AND decision NOT IN ('ORDER','FILLED','AUTHORIZED') AND kind='DECISION' "
                   "GROUP BY opportunity_id", (day,))
    entered = {r["opportunity_id"] for r in store.q("SELECT DISTINCT opportunity_id FROM decision_events WHERE substr(decision_t,1,10)=? "
                                                    "AND decision IN ('ORDER','FILLED','AUTHORIZED')", (day,))}
    n = 0
    for r in rows:
        if r["opportunity_id"] in entered or r["side"] not in ("C", "P") or not r["ticker"]:
            continue
        if store.q("SELECT 1 FROM shadow_outcomes WHERE opportunity_id=? AND rule=?", (r["opportunity_id"], SHADOW_RULE)):
            continue
        m1 = bars_fn(day, r["ticker"])
        res = {"r": None, "why": "no bars for that session (unknown, not imputed)", "entry": None, "entry_t": None, "sd": None}
        if m1 is not None and len(m1):
            t = pd.Timestamp(r["t"]).tz_convert(core.ET)
            i = int(m1.index.searchsorted(t.ceil("1min")))
            snap = {}
            try:
                snap = json.loads(r["snapshot"] or "{}")
            except ValueError:
                pass
            sd = None
            for k in ("stop_dist", "init_stop_dist"):
                if isinstance(snap.get(k), (int, float)) and snap[k] > 0:
                    sd = float(snap[k])
            if sd is None and i < len(m1):
                b5 = m1.iloc[max(0, i - 70):i]
                if len(b5) >= 15:
                    rng = (b5["High"].rolling(5).max() - b5["Low"].rolling(5).min()).dropna()
                    sd = 0.5 * float(rng.iloc[::5].tail(14).mean()) if len(rng) else None
            if i >= len(m1) or not sd:
                res["why"] = "no entry bar or no stop distance (unknown)"
            else:
                o = MB.stock_outcome(m1, i, r["side"], sd, cost_per_share=SHADOW_SPEC["cost_per_share"])
                res = {"r": o["r"] if o else None, "why": o["why"] if o else "no price path (unknown)", "entry": float(m1["Open"].iloc[i]),
                       "entry_t": m1.index[i].isoformat(), "sd": round(sd, 4)}
        store.x("INSERT OR IGNORE INTO shadow_outcomes(opportunity_id, rule, day, ticker, side, ledger, decision, decided_at, entry_t, entry, "
                "stop_dist, r, why, options, recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["opportunity_id"], SHADOW_RULE, day, r["ticker"], r["side"], r["ledger"], r["decision"], r["t"], res["entry_t"],
                 res["entry"], res["sd"], res["r"], res["why"], "unknown", _utc()))
        n += 1
    return n


def _bars_for(day, ticker):
    try:
        import lab
        m = lab.archive_read(day, ticker)
        if m is not None and len(m):
            return m
    except Exception:
        pass
    import pandas as pd
    rows = store.q("SELECT open, o, h, l, c, v FROM bars_archive WHERE ticker=? AND substr(open,1,10)=? ORDER BY open", (ticker, day))
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["open"]).dt.tz_convert(core.ET) if pd.to_datetime(df["open"]).dt.tz is not None else pd.to_datetime(df["open"]).dt.tz_localize(core.ET)
    return df.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})[["Open", "High", "Low", "Close", "Volume"]]


# ---------------------------------------------------------------- backup, export, end of day
def backup(dest_dir=None, keep=7):
    """A consistent snapshot through SQLite's backup API (includes committed WAL pages), then an integrity check of the
    copy. Keeps the newest `keep` copies. Returns (path, integrity)."""
    dest_dir = dest_dir or (core.HERE / "journal" / "backups")
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = core.now_et().strftime("%Y%m%d-%H%M%S")
    dst = dest_dir / f"desk-{stamp}.db"
    with store._lock:
        src = store.conn()
        out = sqlite3.connect(dst)
        src.backup(out)
        out.close()
    chk = sqlite3.connect(dst)
    ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
    chk.close()
    olds = sorted(dest_dir.glob("desk-*.db"))
    for p in olds[:-keep]:
        try:
            p.unlink()
        except OSError:
            pass
    return dst, ok


def export_csv(what="decisions", day_from=None, day_to=None):
    import csv
    import io
    migrate()
    table = {"decisions": "decision_events", "shadow": "shadow_outcomes", "opportunities": "opportunity_summary",
             "hypotheses": "hypothesis_events"}[what]
    col = {"decision_events": "decision_t", "shadow_outcomes": "day", "opportunity_summary": "day", "hypothesis_events": "t"}[table]
    q, a = f"SELECT * FROM {table}", []
    if day_from:
        q += f" WHERE substr({col},1,10)>=?"
        a.append(day_from)
    if day_to:
        q += (" AND" if day_from else " WHERE") + f" substr({col},1,10)<=?"
        a.append(day_to)
    rows = store.q(q, tuple(a))
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return buf.getvalue()


def eod(now=None, bars_fn=None):
    """End-of-day job, safe to call repeatedly: each step runs once per day and resumes where it stopped."""
    migrate()
    now = now or core.now_et()
    day = now.strftime("%Y-%m-%d")
    done = store.kv_get(f"learning_eod:{day}") or {}
    if not done.get("shadow"):
        done["shadow_n"] = shadow_eod(day, bars_fn or _bars_for, now)
        done["shadow"] = True
        store.kv_set(f"learning_eod:{day}", done)
    if not done.get("summary"):
        done["summary_n"] = rebuild_summary(day)
        done["summary"] = True
        store.kv_set(f"learning_eod:{day}", done)
    if not done.get("backup"):
        p, ok = backup()
        done.update(backup=True, backup_file=p.name, integrity=ok)
        store.kv_set(f"learning_eod:{day}", done)
    return done


# ---------------------------------------------------------------- the Learning view
def view(day=None, limit=200):
    migrate()
    seed_hypotheses()
    day = day or core.now_et().strftime("%Y-%m-%d")
    rebuild_summary(day)
    opp = store.q("SELECT * FROM opportunity_summary WHERE day=? ORDER BY last_t DESC LIMIT ?", (day, limit))
    for o in opp:
        o["reasons"] = json.loads(o["reasons"] or "[]")
    by = store.q("SELECT final_decision d, COUNT(*) n FROM opportunity_summary WHERE day=? GROUP BY final_decision ORDER BY n DESC", (day,))
    sh = store.q("SELECT * FROM shadow_outcomes ORDER BY day DESC, decided_at DESC LIMIT 60")
    shs = store.q("SELECT COUNT(*) n, SUM(CASE WHEN r IS NULL THEN 1 ELSE 0 END) unknown, AVG(r) avg_r, "
                  "SUM(CASE WHEN r > 0 THEN 1 ELSE 0 END) wins FROM shadow_outcomes")[0]
    hyp = store.q("SELECT * FROM hypotheses ORDER BY created")
    for h in hyp:
        h["criteria"] = json.loads(h["criteria"] or "{}")
        h["history"] = store.q("SELECT t, status, why FROM hypothesis_events WHERE hypothesis_id=? ORDER BY seq", (h["id"],))
    runs = store.q("SELECT manifest_id, kind, created, result FROM run_manifests ORDER BY created DESC LIMIT 12")
    for r in runs:
        try:
            r["result"] = json.loads(r["result"] or "{}")
        except ValueError:
            pass
    orbx = {}
    for t in core.policy()["instruments"]:
        orbx[t] = store.kv_get(f"orbx_stage:{t}")
    eps = []
    try:
        import orb_retest
        eps = orb_retest.today(day)
    except Exception:
        pass
    return {"day": day, "opportunities": opp, "by_decision": by, "shadow": sh, "shadow_stats": shs, "shadow_rule": {"id": SHADOW_RULE, **SHADOW_SPEC},
            "hypotheses": hyp, "runs": runs, "orbx": orbx, "orbx_episodes": eps,
            "note": ("Facts only: every row comes from the desk's own records. Entered paper trades, rejected setups, shadow "
                     "outcomes (underlying only, one fixed rule) and real trades are kept apart and never summed into one equity curve.")}
