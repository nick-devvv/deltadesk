"""optionhours.py - when an option can actually trade, so the paper engine never fills against a closed market.

Checked Oct 29 2026 against Cboe's equity-options hours FAQ and Robinhood's options-hours help article:
  * equity options: 9:30 a.m.-4:00 p.m. ET regular session; designated ETF/ETN options (SPY, QQQ, IWM ...) to 4:15 p.m.
  * half days: 1:00 p.m. ET close (1:15 p.m. for the late-close ETF classes)
  * Cboe also runs extended sessions (7:30-9:25 a.m. GTH, 4:00-4:15 p.m. Curb) for SOME classes, limit orders only. The
    desk does NOT simulate fills there: eligibility changes and the broker has to support it (EXTENDED_FILLS = False).
  * Robinhood: same-day-expiring stock/ETF options can be opened until 3:30 p.m. ET, and Robinhood starts closing at-risk
    expiring positions at 3:30 p.m. (3:45 p.m. for late-close options).
The ETF list is a configurable assumption (policy "options_hours.late_close"): check Cboe's designated list for changes.
"""
from datetime import datetime

import core

LATE_CLOSE = {"SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "TLT", "XLE", "XLF", "XLK", "EEM", "EFA", "USO", "UNG", "HYG", "SMH"}
EXTENDED_FILLS = False


def cfg():
    c = core.policy().get("options_hours") or {}
    return {"late_close": set(c.get("late_close") or LATE_CLOSE), "extended_fills": bool(c.get("extended_fills", EXTENDED_FILLS))}


def root(symbol):
    """'SPY261028C00600000' -> 'SPY'; a plain ticker stays as it is."""
    s = str(symbol or "").replace(" ", "")
    return s[:-15] if len(s) > 15 and s[-9] in "CP" and s[-15:-9].isdigit() else s


def session(underlying, t=None):
    """(open_bool, close_hhmm, why) for regular-session option trading of this underlying at time t (ET)."""
    t = t or core.now_et()
    d = t.strftime("%Y-%m-%d")
    if t.weekday() >= 5 or d in core.HOLIDAYS:
        return False, None, "options market closed (weekend or exchange holiday)"
    late = root(underlying).upper() in cfg()["late_close"]
    close = ("13:15" if late else "13:00") if d in core.EARLY_CLOSE else ("16:15" if late else "16:00")
    hm = t.strftime("%H:%M")
    if hm < "09:30":
        return False, close, "options market not open yet (regular session starts 9:30 ET; no simulated extended-hours fills)"
    if hm >= close:
        return False, close, f"options market closed at {close} ET"
    return True, close, None


def can_open_same_day(t=None):
    """Robinhood: no new positions in same-day-expiring stock/ETF options after 15:30 ET."""
    t = t or core.now_et()
    return t.strftime("%H:%M") < "15:30"


def tradable(symbol, t=None):
    """(ok, why) for a simulated fill on this option symbol now."""
    ok, close, why = session(root(symbol), t)
    if not ok:
        return False, why
    s = str(symbol or "")
    if len(s) > 15 and s[-15:-9].isdigit():
        exp = datetime.strptime("20" + s[-15:-9], "%Y%m%d").date()
        t = t or core.now_et()
        if exp < t.date():
            return False, "contract has expired"
    return True, None
