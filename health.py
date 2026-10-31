"""health.py - v3.5 (new): worker heartbeats, liveness/readiness, and the stale-feed entry block.

Every background worker calls beat(name, ...) once per loop. /healthz answers "is the process up" (no data at all),
/readyz answers "can the desk be trusted right now" (database writable, market data connected, the workers that
matter have beaten recently), /api/health (signed in) shows the details. Nothing here contains a secret, a token, a
desk link or a position: it is safe to point a free uptime checker at /healthz and /readyz.

The entry block: when the engine has just measured the stock feed as stale, new simulated entries are refused (exits
keep running). An UNKNOWN feed state never blocks by itself here; the entry gate already fails closed on freshness.
"""
import os
import threading
import time

import core

_lock = threading.Lock()
_beats = {}
STARTED = time.time()
# how long a worker may go quiet before it counts as stale (seconds), and whether readiness needs it in market hours
WORKERS = {"engine": (30, True), "lab": (90, False), "catalysts": (120, False), "contracts": (120, False),
           "v4stocks": (60, False), "chains": (180, False)}
_feed = {"ok": None, "t": None, "why": None}


def beat(name, ok=True, note=None, dur_s=None):
    with _lock:
        b = _beats.setdefault(name, {"n": 0, "errors": 0})
        b.update(t=time.time(), ok=bool(ok), note=(str(note)[:200] if note else None), dur_s=dur_s)
        b["n"] += 1
        if not ok:
            b["errors"] += 1
            b["last_error_t"] = time.time()


def set_feed(ok, why=None):
    with _lock:
        _feed.update(ok=bool(ok), t=time.time(), why=why)


def entry_block():
    """A reason to refuse NEW simulated entries right now, or None."""
    with _lock:
        f = dict(_feed)
    if f["ok"] is False and f["t"] and time.time() - f["t"] < 120:
        return f"market data is stale ({f['why'] or 'engine check'}): no new simulated entries until it is fresh"
    return None


def workers(now=None):
    now = now or time.time()
    out = {}
    with _lock:
        items = {k: dict(v) for k, v in _beats.items()}
    for name, (limit, _) in WORKERS.items():
        b = items.pop(name, None)
        out[name] = _row(b, limit, now)
    for name, b in items.items():
        out[name] = _row(b, 120, now)
    return out


def _row(b, limit, now):
    if not b:
        return {"state": "not started", "age_s": None}
    age = round(now - b["t"], 1)
    return {"state": "ok" if b["ok"] and age <= limit else "stale" if age > limit else "error", "age_s": age, "limit_s": limit,
            "beats": b["n"], "errors": b["errors"], "last_dur_s": b.get("dur_s"), "note": b.get("note")}


def _db_ok():
    try:
        import store
        store.x("CREATE TABLE IF NOT EXISTS health_probe(k TEXT PRIMARY KEY, t TEXT)")
        store.x("INSERT OR REPLACE INTO health_probe(k, t) VALUES('probe', ?)", (store.ts(),))
        return True, None
    except Exception as e:
        return False, type(e).__name__


def _rss_mb():
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    try:
        import resource
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(r / (1024 * 1024 if os.uname().sysname == "Darwin" else 1024), 1)
    except Exception:
        return None


def readiness():
    """(ready, reasons). Market-hours readiness needs the engine heartbeat; outside them the process + DB is enough."""
    reasons = []
    ok, why = _db_ok()
    if not ok:
        reasons.append(f"database not writable ({why})")
    sess = core.session_info()
    market = sess["state"] in ("OPEN", "ORB FORMING", "NO NEW ENTRIES", "ALL OUT")
    w = workers()
    for name, (limit, needed) in WORKERS.items():
        if needed and market and w[name]["state"] != "ok":
            reasons.append(f"{name} worker {w[name]['state']}" + (f" ({w[name]['age_s']} s since its last beat)" if w[name]["age_s"] else ""))
    try:
        import marketdata
        if market and marketdata._provider is None:
            import schwab
            st = schwab.status(verify=False).get("state")
            if st != "connected":
                reasons.append(f"Schwab market data {st}")
    except Exception:
        pass
    eb = entry_block()
    if eb and market:
        reasons.append(eb)
    return not reasons, reasons


def summary():
    """Detailed, secret-free health for /api/health."""
    ready, reasons = readiness()
    out = {"ready": ready, "reasons": reasons, "uptime_s": round(time.time() - STARTED), "workers": workers(),
           "feed": dict(_feed), "rss_mb": _rss_mb(), "pid": os.getpid(), "session": core.session_info()["state"]}
    try:
        import marketdata
        out["quotes"] = {"future_dated_seen": marketdata.CLOCK["future_quotes"], "last_future_s": marketdata.CLOCK["last_future_s"],
                         "tolerance_s": marketdata.FUTURE_TOL_S}
    except Exception:
        pass
    try:
        import schwab
        out["schwab_rate"] = {k: schwab.STATS.get(k) for k in ("calls", "waited_s", "http_errors")} | {"by_priority": dict(schwab.PRIORITY_STATS)}
    except Exception:
        pass
    try:                                           # E9: scan coverage, never a claim of full-market coverage
        import time as _t
        import scanner_setups as SS
        import lab
        bars = dict(SS._state.get("bars") or {})
        uni = len(SS.tickers()) if hasattr(SS, "tickers") else None
        fresh = sum(1 for v in bars.values() if _t.time() - v[0] < 300)
        out["coverage"] = {"tier1_open_positions": "managed first every engine tick (risk priority)",
                           "board_universe": uni, "bars_fresh_5min": fresh,
                           "coverage_pct": round(100 * fresh / uni, 1) if uni else None,
                           "lab_bars_behind": lab._state.get("behind"), "lab_step_s": lab._state.get("step_s"),
                           "note": "about 127 symbols plus the day's movers: not the whole market"}
    except Exception:
        pass
    try:
        import store
        out["db_mb"] = round(store.DB.stat().st_size / 1e6, 1) if store.DB.exists() else None
    except Exception:
        pass
    try:
        import release
        out["release"] = release.RELEASE_ID
    except Exception:
        pass
    return out
