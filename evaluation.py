"""evaluation.py - the forward paper test, scored against the criteria fixed in policy.json -> evaluation
BEFORE any result existed. Read-only: it never changes a rule or a trade.

  python3 evaluation.py            # prints the scorecard
  GET /api/evaluation              # same, as JSON (the desk page and the 4:20 review can read it)
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402
import store  # noqa: E402

MIN_SCHWAB_RTH_MIN = 375          # a "complete valid session": Schwab bars for at least 375 of 390 RTH minutes


def _closed(ledger, since, version):
    return store.q("SELECT id, date, setup_id, realized, opened, closed, verified, policy_version FROM positions "
                   "WHERE ledger=? AND date>=? AND status='CLOSED' AND (policy_version=? OR ?='')"
                   " ORDER BY closed", (ledger, since, version, version))


def valid_sessions(since):
    rows = store.q("SELECT substr(open,1,10) d, COUNT(*) n FROM bars_archive WHERE ticker='SPY' AND src LIKE 'Schwab%' "
                   "AND substr(open,12,5) >= '09:30' AND substr(open,12,5) < '16:00' AND open >= ? GROUP BY d", (since,))
    return sorted(r["d"] for r in rows if r["n"] >= MIN_SCHWAB_RTH_MIN)


def stats(pnls):
    n = len(pnls)
    if not n:
        return {"n": 0}
    wins = [x for x in pnls if x > 1]
    losses = [x for x in pnls if x < -1]
    eq, peak, dd = 0.0, 0.0, 0.0
    for x in pnls:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    rnd = random.Random(7)                              # fixed seed: the same trades always give the same interval
    boots = sorted(sum(rnd.choice(pnls) for _ in range(n)) / n for _ in range(2000))
    gl = -sum(losses)
    return {"n": n, "net": round(sum(pnls), 2), "expectancy": round(sum(pnls) / n, 2),
            "ci95": [round(boots[49], 2), round(boots[1949], 2)], "wins": len(wins), "losses": len(losses),
            "breakeven": n - len(wins) - len(losses), "win_rate": round(100 * len(wins) / n, 1),
            "profit_factor": round(sum(wins) / gl, 2) if gl > 0 else None,
            "max_drawdown": round(dd, 2), "avg_loss": round(sum(losses) / len(losses), 2) if losses else None}


def violations(since, version):
    out = []
    for led in ("paper", "research"):
        ps = _closed(led, since, version)
        dup = store.q("SELECT setup_id, COUNT(*) n FROM positions WHERE ledger=? AND date>=? GROUP BY setup_id HAVING n > 1", (led, since))
        out += [f"{led}: idea {d['setup_id']} has {d['n']} positions" for d in dup]
        out += [f"{led}: {p['id']} filled on {p['verified']}" for p in ps if "Schwab" not in (p["verified"] or "")]
        for p in ps:
            day = core.session_info(__import__("datetime").datetime.fromisoformat(p["opened"]))
            if (p["closed"] or "")[11:16] > day["all_out"] and p["closed"][:10] == p["date"]:
                out.append(f"{led}: {p['id']} closed {p['closed'][11:16]}, after all out {day['all_out']}")
    return out


def report():
    ev = core.policy().get("evaluation") or {}
    since, version = ev.get("start", "2026-10-30"), ev.get("policy_version", "")
    sess = valid_sessions(since)
    res = {"config": ev, "valid_sessions": len(sess), "session_days": sess, "ledgers": {}}
    for led in ("paper", "research", "old", "real"):
        res["ledgers"][led] = stats([r["realized"] or 0 for r in _closed(led, since, version if led in ("paper", "research") else "")])
    m = res["ledgers"]["paper"]
    v = violations(since, version)
    checks = {
        "sessions": len(sess) >= ev.get("min_sessions", 10),
        "enough_trades": m.get("n", 0) >= 20,
        "expectancy_positive": (m.get("expectancy") or 0) > 0,
        "profit_factor": (m.get("profit_factor") or 0) >= 1.2,
        "drawdown": m.get("n", 0) > 0 and m.get("avg_loss") is not None and m["max_drawdown"] < 3 * abs(m["avg_loss"]),
        "no_violations": not v,
    }
    res["checks"], res["violations"] = checks, v
    if not checks["sessions"]:
        res["verdict"] = f"running: {len(sess)} of {ev.get('min_sessions', 10)} valid sessions"
    elif not checks["enough_trades"]:
        res["verdict"] = f"not enough trades ({m.get('n', 0)} of 20): extend the test"
    else:
        res["verdict"] = "criteria met (paper only; Nick decides what happens next)" if all(checks.values()) else \
                         "criteria not met: " + ", ".join(k for k, ok in checks.items() if not ok)
    res["note"] = "Paper results with modeled costs. A pass is not permission for real-money automation or larger size."
    return res


if __name__ == "__main__":
    print(json.dumps(report(), indent=1, default=str))
