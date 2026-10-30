"""strategy_registry.py - the experiment register and each strategy's evidence status (config/specialists.json).

Every strategy, filter or window that has been tested is listed with its spec, where its evidence came from and a
status: DRAFT, RESEARCH ONLY, PAPER QUALIFIED, PAUSED or RETIRED. No status enables real orders: real trades are
always placed by Nick in Robinhood.

Immutability: the first time an experiment is seen, the sha256 of its spec is stored in the database. If the file's
spec later differs, the experiment is reported as SPEC CHANGED and treated as RESEARCH ONLY: a change needs a new id,
so a tested definition can't be quietly edited after its results are known.

Attempt log: every evaluation run (signal study, walk-forward fold, control comparison) is appended to
`experiment_attempts`, so a test period can't be reused silently.
"""
import hashlib
import json
import threading

import core
import store

STATUSES = ("DRAFT", "RESEARCH ONLY", "PAPER QUALIFIED", "PAUSED", "RETIRED")
ACTIONABLE = ("PAPER QUALIFIED",)        # the only status that may be shown as a desk entry (and still: Nick decides)
SCHEMA = ["CREATE TABLE IF NOT EXISTS experiment_hashes(id TEXT PRIMARY KEY, sha256 TEXT, first_seen TEXT)",
          "CREATE TABLE IF NOT EXISTS experiment_attempts(seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, exp_id TEXT, kind TEXT, "
          "period TEXT, params TEXT, result TEXT)"]
_lock = threading.Lock()
_cache = {"mtime": None, "data": None}
FILE = core.HERE / "config" / "specialists.json"


def _schema():
    for s in SCHEMA:
        store.x(s)


def spec_hash(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load():
    try:
        m = FILE.stat().st_mtime
    except OSError:
        return {"experiments": [], "qualified": [], "assignments": []}
    with _lock:
        if _cache["mtime"] != m:
            _cache.update(mtime=m, data=json.loads(FILE.read_text()))
        return _cache["data"]


def experiments():
    """Experiments with their integrity checked against the first-seen hash."""
    _schema()
    out = []
    for e in load().get("experiments", []):
        h = spec_hash(e.get("spec") or {})
        row = store.q("SELECT sha256 FROM experiment_hashes WHERE id=?", (e["id"],))
        if not row:
            store.x("INSERT OR IGNORE INTO experiment_hashes(id, sha256, first_seen) VALUES(?,?,?)", (e["id"], h, store.ts()))
            changed = False
        else:
            changed = row[0]["sha256"] != h
        st = e.get("status", "DRAFT")
        if st not in STATUSES:
            st = "DRAFT"
        out.append(dict(e, sha256=h, spec_changed=changed, status=("RESEARCH ONLY" if changed and st in ACTIONABLE else st),
                        status_note="SPEC CHANGED after registration: needs a new id" if changed else None))
    return out


def get(exp_id):
    return next((e for e in experiments() if e["id"] == exp_id), None)


def _matches(e, family, ticker):
    sp = e.get("spec") or {}
    fam = str(sp.get("family", ""))
    if fam not in ("*", family) and not (family and fam.upper() == family.upper()):
        return False
    a = sp.get("assets") or {}
    syms = a.get("symbols")
    return not syms or ticker in syms


def status_for(family, ticker):
    """The evidence status a desk setup carries right now: the best status among matching executable experiments.
    No match = DRAFT (untested). Only PAPER QUALIFIED may be presented as an entry."""
    best, rank = None, {"PAPER QUALIFIED": 4, "PAUSED": 3, "RESEARCH ONLY": 2, "DRAFT": 1, "RETIRED": 0}
    for e in experiments():
        if e.get("kind") != "executable" or not _matches(e, family, ticker):
            continue
        if best is None or rank.get(e["status"], 0) > rank.get(best["status"], 0) or \
                (e["spec"].get("family") != "*" and best["spec"].get("family") == "*" and e["status"] == best["status"]):
            best = e
    if not best:
        return {"status": "DRAFT", "id": None, "why": "not tested yet: no evidence either way", "actionable": False}
    return {"status": best["status"], "id": best["id"], "sha256": best["sha256"], "why": best.get("why_status"),
            "evidence": best.get("evidence"), "actionable": best["status"] in ACTIONABLE}


def qualified():
    """PAPER QUALIFIED experiments (starts empty). Each needs a review date and an evidence window."""
    return [e for e in experiments() if e["status"] == "PAPER QUALIFIED"]


def log_attempt(exp_id, kind, period, params, result):
    """Append-only: every evaluation run is recorded, including failures and abandoned variants."""
    _schema()
    store.x("INSERT INTO experiment_attempts(ts, exp_id, kind, period, params, result) VALUES(?,?,?,?,?,?)",
            (store.ts(), exp_id, kind, period, json.dumps(params, default=str), json.dumps(result, default=str)[:20000]))


def attempts(exp_id=None):
    _schema()
    q = "SELECT * FROM experiment_attempts" + (" WHERE exp_id=?" if exp_id else "") + " ORDER BY seq"
    return store.q(q, (exp_id,) if exp_id else ())


def evidence_table():
    """Every experiment with its status, evidence and attempt count, for the Markets page and Chart."""
    rows = []
    for e in experiments():
        sp = e.get("spec") or {}
        rows.append({"id": e["id"], "kind": e.get("kind"), "status": e["status"], "status_note": e.get("status_note"),
                     "family": sp.get("family"), "assets": sp.get("assets"), "windows": sp.get("windows"), "policy": sp.get("policy"),
                     "evidence": e.get("evidence") or [], "why_status": e.get("why_status"), "sha256": e["sha256"][:12],
                     "attempts": len(attempts(e["id"]))})
    return {"experiments": rows, "qualified": [e["id"] for e in qualified()],
            "qualified_note": ("No strategy is PAPER QUALIFIED. Every desk setup is research only until later, unseen evidence "
                               "beats a matched random-entry control after costs.") if not qualified() else None,
            "promotion_rule": load().get("promotion_rule"), "version": load().get("version")}
