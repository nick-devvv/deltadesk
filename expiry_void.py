"""expiry_void.py - v3-table option positions still OPEN after their contract expired become VOID (2026-11-17).

The bug (found 2026-11-17 from the desk's own database): the `noise` ledger's Nov 5 0DTE puts, SPY 757P and QQQ 671P,
were never closed at 15:25 ET, because the desk then ran on Chart's computer and it slept. From Nov 6 their exit
waited for a valid quote (paper.sell), and an expired contract never gets one, so they stayed OPEN for 12 days with a
stale mark on the page (+$1,716 and +$1,319 shown; not results). Three `old` contracts were stuck the same way.

The rule, the same one v4 already uses for its own tables (v4exec.overnight -> v4store.void): an option whose expiry
date is before today (ET) and that is still OPEN is VOID. VOID is excluded from every result (no trade count, no P/L)
and kept for review, because the desk never saw a price it could have sold at. For reference only, the note gives the
contract's value at that day's close (intrinsic value from the underlying's daily close, labeled MODELED); it is never
added to P/L.

This is bookkeeping, not a strategy change: noiseband.py and policy_old.py are untouched.
"""
import datetime as dt

import core
import store

VERSION = "2026-11-17.expiry-void1"


def expiry(p):
    """The contract's expiry date 'YYYY-MM-DD' from the position (plan, then the OCC symbol), or None for non-options."""
    pl = p.get("plan") if isinstance(p.get("plan"), dict) else {}
    c = pl.get("contract") if isinstance(pl.get("contract"), dict) else {}
    e = pl.get("expiry") or c.get("expiry")
    if e:
        return str(e)[:10]
    sym = str(p.get("symbol") or "").replace(" ", "")
    if len(sym) >= 15 and sym[-9] in "CP":
        try:
            d = dt.date(2000 + int(sym[-15:-13]), int(sym[-13:-11]), int(sym[-11:-9]))
            return d.isoformat()
        except ValueError:
            return None
    return None


def strike_side(p):
    sym = str(p.get("symbol") or "").replace(" ", "")
    try:
        return int(sym[-8:]) / 1000, sym[-9]
    except (ValueError, IndexError):
        return None, None


def expiry_value(p, exp, daily=None):
    """(value per share, underlying close) at the expiry day's close: intrinsic, MODELED. (None, None) if unknown."""
    k, side = strike_side(p)
    if k is None or side not in ("C", "P"):
        return None, None
    try:
        if daily is None:
            import schwab
            daily = schwab.bars_daily(p["ticker"])
        if daily is None or not len(daily):
            return None, None
        idx = [str(i)[:10] for i in daily.index]
        if exp not in idx:
            return None, None
        close = float(daily["Close"].iloc[idx.index(exp)])
    except Exception:
        return None, None
    v = max(0.0, close - k) if side == "C" else max(0.0, k - close)
    return round(v, 2), round(close, 2)


def void_if_expired(p, today=None, daily=None):
    """VOID an OPEN option position whose contract expired before `today` (ET). Returns True if it was voided."""
    if p.get("status") != "OPEN":
        return False
    exp = expiry(p)
    today = today or core.now_et().date().isoformat()
    if not exp or exp >= today:
        return False
    v, close = expiry_value(p, exp, daily)
    ref = (f" For reference only: worth ${v:.2f} at the {exp} close ({p['ticker']} closed at {close:.2f}), "
           f"vs ${float(p['fill']):.2f} paid (MODELED, intrinsic value, not counted).") if v is not None else ""
    note = (f"VOID: expired {exp} while still open (the desk missed the 15:25 exit, then waited for a quote an expired "
            f"contract never gets). No real exit price, so excluded from results.{ref}")
    pl = dict(p.get("plan") or {})
    pl.update(exit_reason=note, void={"expiry": exp, "value_modeled": v, "underlying_close": close, "version": VERSION})
    import json
    with store.tx():
        cur = store.x("UPDATE positions SET status='VOID', qty_open=0, closed=?, plan=? WHERE id=? AND status='OPEN'",
                      (store.ts(), json.dumps(pl, default=str), p["id"]))
        if not cur.rowcount:
            return False
        store.kv_set(f"pending_exit:{p['id']}", None)
        store.event("error", f"{str(p['ledger']).upper()} VOID {p['ticker']} {p['contract']}: {note}", p["ledger"], p["id"])
    return True


def sweep(today=None):
    """Void every expired OPEN option in the v3 positions table. Returns the voided ids."""
    out = []
    for p in store.positions(status="OPEN"):
        try:
            if void_if_expired(p, today):
                out.append(p["id"])
        except Exception:
            continue
    return out
