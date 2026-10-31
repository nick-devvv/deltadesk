"""v4index.py - runs the v4 index book (noise_v2, noise_trend) and premium book (orb_credit, ic_20d) from the engine
tick. Management (manage) runs FIRST each tick inside the engine's risk-priority block; entries (tick, tick_extra)
run after. Each ledger is independent; one failing never stops the others (errors are kept in _state)."""
import core
import store
import v4store as S

LEDGERS = {"noise_v2": "index", "noise_trend": "index", "orb_credit": "premium", "ic_20d": "premium"}
_state = {"last_error": None, "errors": 0}


def _err(where, e):
    _state["errors"] += 1
    _state["last_error"] = f"{where}: {type(e).__name__}: {e}"[:200]


def tick(ticker, snap, chain_rows_fn, now=None):
    """Per SPY/QQQ snapshot, every engine tick."""
    now = now or core.now_et()
    import noise_trend
    import noise_v2
    for name, mod in (("noise_v2", noise_v2), ("noise_trend", noise_trend)):
        try:
            mod.tick(ticker, snap, chain_rows_fn, now)
        except Exception as e:
            _err(f"{name} {ticker}", e)
    if core.session_info(now)["entries_allowed"]:
        import ic_20d
        import orb_credit
        try:
            orb_credit.tick(ticker, snap.get("m1"), now)
        except Exception as e:
            _err(f"orb_credit {ticker}", e)
        try:
            ic_20d.tick(ticker, now)
        except Exception as e:
            _err(f"ic_20d {ticker}", e)


def tick_extra(now=None):
    """XSP for the premium ledgers, only when Schwab lists it today (probed once a day from 10:00)."""
    now = now or core.now_et()
    sess = core.session_info(now)
    if not sess["entries_allowed"] or now.strftime("%H:%M") < "10:00":
        return None
    import ic_20d
    import orb_credit
    import v4spreads as SP
    try:
        if not SP.extra_available(now):
            return None
        ic_20d.tick(SP.EXTRA, now)
        if now.strftime("%H:%M") >= orb_credit.OR_END and not S.decided(f"{orb_credit.LEDGER}:{SP.EXTRA}:{now.date()}"):
            m1, src = SP.extra_bars(now)
            if m1 is not None:
                orb_credit.tick(SP.EXTRA, m1, now)
    except Exception as e:
        _err("XSP", e)


def manage(now=None):
    """Open v4 index/premium positions: pending exits, stops, all-out. Returns the option symbols held (for streaming)."""
    now = now or core.now_et()
    import ic_20d
    import noise_trend
    import noise_v2
    import orb_credit
    mods = {"noise_v2": noise_v2, "noise_trend": noise_trend, "orb_credit": orb_credit, "ic_20d": ic_20d}
    syms = []
    import v4exec
    for p in S.positions(status="OPEN", ledgers=list(LEDGERS)):
        syms += [l["symbol"] for l in p["legs"]]
        try:
            if v4exec.overnight(p, now):
                continue
            mods[p["ledger"]].manage(p, now)
        except Exception as e:
            _err(f"manage {p['id']}", e)
    return syms


def status():
    return {"ledgers": LEDGERS, "last_error": _state["last_error"], "errors": _state["errors"],
            "xsp_today": store.kv_get(f"v4_xsp:{core.now_et().date()}")}
