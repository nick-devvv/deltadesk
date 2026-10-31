"""v4common.py - small shared helpers for the v4 ledgers: the event calendar (FOMC / CPI / jobs), finished-bar cuts,
quote freshness and the v4 enable switch. Pure code, no network.

Calendar: config/events.json (written by the 9 AM routine through POST /api/events) is the primary source. When it has
no calendar for today, FOMC days come from the dated list in config/v4.json and CPI / jobs days are UNKNOWN (never
assumed false).
"""
import json
import re
from datetime import datetime, timedelta

import pandas as pd

import core
import store

FOMC_RE = re.compile(r"\b(fomc|fed(eral)?\s+(funds|reserve|rate|decision|statement|chair)|powell|rate decision)\b", re.I)
CPI_RE = re.compile(r"\b(cpi|consumer price)\b", re.I)
JOBS_RE = re.compile(r"\b(nfp|non-?farm|payrolls?|jobs report|employment situation|unemployment rate)\b", re.I)


def enabled():
    """v4 paper entries on/off (the v4 kill switch turns this off; exits always run)."""
    return bool(store.kv_get("v4_enabled", True))


def entries_blocked():
    """Why new v4 entries are blocked right now (None = allowed): the v4 kill switch, the desk's emergency pause, a
    stale stock feed measured by the engine."""
    if not enabled():
        return "v4 kill switch is on: no new v4 entries"
    if store.kv_get("paper_pause"):
        return "paper entries are paused (emergency pause)"
    try:
        import health
        b = health.entry_block()
        if b:
            return b
    except Exception:
        pass
    return None


def calendar(now=None):
    """{"known": bool, "source": str, "fomc": bool|None, "cpi": bool|None, "jobs": bool|None, "events": [...]}."""
    now = now or core.now_et()
    day = now.strftime("%Y-%m-%d")
    try:
        evs = json.loads(core.EVENTS_FILE.read_text())
    except (OSError, ValueError):
        evs = None
    if evs and evs.get("date") == day:
        names = [str(e.get("name", "")) for e in evs.get("events") or []]
        return {"known": True, "source": "config/events.json", "events": evs.get("events") or [],
                "fomc": any(FOMC_RE.search(n) for n in names), "cpi": any(CPI_RE.search(n) for n in names),
                "jobs": any(JOBS_RE.search(n) for n in names)}
    import retire
    fomc_days = set(retire.cfg().get("fomc_decision_days") or [])
    return {"known": False, "source": "config/v4.json FOMC list (no events.json for today)", "events": [],
            "fomc": True if day in fomc_days else (False if fomc_days and day[:4] == "2026" else None), "cpi": None, "jobs": None}


def is_fomc_day(now=None):
    """(True/False/None, source). None = unknown."""
    c = calendar(now)
    return c["fomc"], c["source"]


def macro_day(now=None):
    """FOMC, CPI or jobs day: True if any is known true, False only if all three are known false, else None."""
    c = calendar(now)
    vals = [c["fomc"], c["cpi"], c["jobs"]]
    if any(v is True for v in vals):
        return True
    if all(v is False for v in vals):
        return False
    return None


def finished(m1, now):
    """Only bars whose minute has ended by `now` (finished candles only)."""
    if m1 is None or not len(m1):
        return m1
    return m1[m1.index + pd.Timedelta(minutes=1) <= pd.Timestamp(now)]


def rth_day(m1, day):
    if m1 is None or not len(m1):
        return None
    r = m1[m1.index.date == day]
    return r.between_time("09:30", "15:59") if len(r) else r


def latency_s():
    return float(core.policy()["v3"]["contract"].get("latency_s", 1.0))


def quote_after(q, signal_t, max_age_s=20):
    """Fill rule: an executable quote dated at least the decision latency AFTER the signal, and not stale.
    Returns (ok, why)."""
    if not q:
        return False, "no quote"
    if q.get("executable") is False:
        return False, "not executable: " + (", ".join(q.get("problems") or []) or "provider")
    if q.get("bid") is None or q.get("ask") is None or q["ask"] <= 0 or q["bid"] < 0 or q["bid"] > q["ask"]:
        return False, "no valid two-sided quote"
    qt = q.get("quote_time")
    if qt is None:
        return False, "quote has no timestamp"
    qt = pd.Timestamp(qt)
    st = pd.Timestamp(signal_t)
    if qt.tzinfo is None:
        qt = qt.tz_localize(core.ET)
    if st.tzinfo is None:
        st = st.tz_localize(core.ET)
    if (qt - st).total_seconds() < latency_s():
        return False, f"no quote yet dated {latency_s():.0f}s after the signal {st.strftime('%H:%M:%S')}"
    age = (pd.Timestamp(core.now_et()) - qt).total_seconds()
    if age > max_age_s:
        return False, f"stale quote ({age:.0f}s old)"
    return True, None


def hm(t):
    return t.strftime("%H:%M")


def day_str(now=None):
    return (now or core.now_et()).strftime("%Y-%m-%d")


def iso(t):
    return pd.Timestamp(t).isoformat() if t is not None else None


def minutes_since_open(now):
    return (now.hour * 60 + now.minute) - 570


def at(day, hhmm):
    return datetime.combine(day, datetime.strptime(hhmm, "%H:%M").time(), core.ET)


def plus(t, minutes):
    return t + timedelta(minutes=minutes)
