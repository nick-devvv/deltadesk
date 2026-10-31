"""v4risk.py - the shared risk layer for the v4 paper ledgers. HARD-CODED limits (code, not config, not editable
from the API, never set by an AI). Entries only: exits are never blocked by anything here.

Checks, in order, for every new v4 entry (admit):
  1. the v4 kill switch, the desk's emergency pause, a stale stock feed (v4common.entries_blocked)
  2. FOMC blackout for the premium-selling ledgers (orb_credit, ic_20d): no new entries on an FOMC statement day
  3. one open position per symbol per ledger
  4. open-position caps: whole v4 desk, per book, per symbol (all v4 ledgers together)
  5. same-direction exposure cap per book (long delta vs short delta; iron condors count as neutral)
  6. per-book daily paper loss limit: realized today + open marks; when it is hit, no new entries in that book today
Option shadows (<ledger>_opt) mirror a share trade that was already admitted: they are exempt from 3-6 (so the
comparison shares vs options is never biased by a cap) but are closed by the kill switch like everything else.

The limits are circuit breakers sized so they rarely bind on a normal day (each ledger is a separate forward
experiment and shared caps would distort the comparison); every block is recorded as a decision with its reason, so
how often they bind is measurable.
"""
import core
import store
import v4common as C
import v4store as S

VERSION = "2026-10-31.v4-risk1"
LIMITS = {
    "desk_max_open": 50,
    "book_max_open": {"index": 4, "premium": 6, "stocks": 40, "catalyst": 8},
    "symbol_max_open": 4,
    "book_max_same_direction": {"index": 4, "premium": 4, "stocks": 25, "catalyst": 6},
    "book_daily_loss_usd": {"index": 600.0, "premium": 800.0, "stocks": 2000.0, "catalyst": 800.0},
    "selling_ledgers": ("orb_credit", "ic_20d"),
}


def is_shadow(ledger):
    return str(ledger).endswith("_opt")


def _primary_open():
    return [p for p in S.positions(status="OPEN") if not is_shadow(p["ledger"])]


def book_pnl_today(book, now=None):
    """Realized today (closed) + the last mark of open positions, primary ledgers of the book only."""
    day = C.day_str(now)
    tot = 0.0
    for p in S.positions(book=book, day=day):
        if is_shadow(p["ledger"]):
            continue
        if p["status"] == "CLOSED":
            tot += p["realized"] or 0.0
        else:
            tot += float((p.get("plan") or {}).get("mtm") or 0.0)
    return round(tot, 2)


def admit(ledger, book, ticker, direction, now=None):
    """None if a new entry may proceed, else the reason (recorded by the caller)."""
    now = now or core.now_et()
    blk = C.entries_blocked()
    if blk:
        return blk
    if ledger in LIMITS["selling_ledgers"]:
        f, src = C.is_fomc_day(now)
        if f is True:
            return f"FOMC day ({src}): no new premium-selling entries"
    opens = S.positions(status="OPEN")
    if [p for p in opens if p["ledger"] == ledger and p["ticker"] == ticker]:
        return f"{ledger} already has an open {ticker} position (one per symbol per ledger)"
    if is_shadow(ledger):
        return None
    prim = [p for p in opens if not is_shadow(p["ledger"])]
    if len(prim) >= LIMITS["desk_max_open"]:
        return f"v4 desk cap: {len(prim)} open positions (max {LIMITS['desk_max_open']})"
    inbook = [p for p in prim if p["book"] == book]
    cap = LIMITS["book_max_open"].get(book, 4)
    if len(inbook) >= cap:
        return f"{book} book cap: {len(inbook)} open (max {cap})"
    sym = [p for p in prim if p["ticker"] == ticker]
    if len(sym) >= LIMITS["symbol_max_open"]:
        return f"{ticker} cap: {len(sym)} open v4 positions (max {LIMITS['symbol_max_open']})"
    if direction in ("long", "short"):
        same = [p for p in inbook if p["direction"] == direction]
        dcap = LIMITS["book_max_same_direction"].get(book, 4)
        if len(same) >= dcap:
            return f"{book} book same-direction cap: {len(same)} {direction} positions open (max {dcap})"
    lim = LIMITS["book_daily_loss_usd"].get(book)
    if lim is not None:
        pl = book_pnl_today(book, now)
        if pl <= -lim:
            return f"{book} book daily paper loss limit: ${pl:,.2f} today (limit -${lim:,.0f}); no new entries today"
    return None


def kill(reason="kill switch"):
    """Turn v4 entries off and close every open v4 paper position at the current quote (pending if none)."""
    import v4exec
    store.kv_set("v4_enabled", False)
    closed, pending = 0, 0
    for p in S.positions(status="OPEN"):
        r = v4exec.close_now(p, f"KILL SWITCH ({reason})")
        if r is None:
            pending += 1
        else:
            closed += 1
    msg = f"V4 KILL SWITCH: v4 entries OFF, {closed} v4 paper position(s) closed, {pending} pending a valid quote ({reason})"
    store.event("v4", msg, "v4")
    return {"ok": True, "closed": closed, "pending": pending, "message": msg}


def enable(on=True):
    store.kv_set("v4_enabled", bool(on))
    store.event("v4", f"v4 entries {'ON' if on else 'OFF'}", "v4")
    return {"ok": True, "v4_enabled": bool(on)}


def status(now=None):
    now = now or core.now_et()
    prim = _primary_open()
    return {"version": VERSION, "v4_enabled": C.enabled(), "entries_blocked": C.entries_blocked(),
            "limits": {k: (list(v) if isinstance(v, tuple) else v) for k, v in LIMITS.items()},
            "open": {"desk": len(prim), "by_book": {b: len([p for p in prim if p["book"] == b]) for b in LIMITS["book_max_open"]}},
            "pnl_today": {b: book_pnl_today(b, now) for b in LIMITS["book_daily_loss_usd"]},
            "fomc_today": C.is_fomc_day(now)[0], "calendar": C.calendar(now)}
