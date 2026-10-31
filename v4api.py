"""v4api.py - the /api/v4 endpoints (server.py hands every /api/v4* request here). Read-only views of the v4 paper
ledgers plus the v4 kill switch. Nothing here can place an order anywhere.

GET  /api/v4/chains           option-chain logger status (data/chains, gitignored)
GET  /api/v4/risk             the shared v4 risk layer: hard-coded limits, open counts, book P/L today, FOMC flag
POST /api/v4/kill             {"reason"}: v4 entries OFF and every open v4 paper position closed (pending if no quote)
POST /api/v4/enable           {"on": true|false}: v4 entries back on (or off without closing anything)
GET  /api/v4?since=           the v4 lineup by book: trades, win rate, avg win/loss, expectancy, profit factor, max DD,
                              SPY vs QQQ, shares vs options shadow, matched random entries; risk; retired archive
GET  /api/v4/positions?status=&ledger=&day=   v4 paper positions with a one-line description and the last mark
GET  /api/v4/decisions?day=&ledger=&kind=     every v4 decision (checks, entries, skips, risk blocks, rankings)
"""


def _one(q, k, default=None):
    v = (q or {}).get(k)
    return v[0] if isinstance(v, list) and v else (v if v is not None else default)


def get(path, q):
    if path == "/api/v4/chains":
        import chain_logger
        return chain_logger.status()
    if path == "/api/v4/risk":
        import v4risk
        return v4risk.status()
    if path == "/api/v4":
        import v4report
        return v4report.overview(str(_one(q, "since", "2026-11-02"))[:10])
    if path == "/api/v4/positions":
        import v4store as S
        st = _one(q, "status")
        rows = S.positions(status=st if st in ("OPEN", "CLOSED", "VOID") else None, ledger=_one(q, "ledger"), day=_one(q, "day"))
        return [view(p) for p in rows][-500:]
    if path == "/api/v4/decisions":
        import v4store as S
        lim = max(1, min(2000, int(_one(q, "limit", 300) or 300)))
        return S.decisions(day=_one(q, "day"), ledger=_one(q, "ledger"), kind=_one(q, "kind"), limit=lim)
    return None


def view(p):
    """A position for the page: one-line description, the last mark and what happens next."""
    pl = p.get("plan") or {}
    if p["kind"] == "shares":
        desc = f"{p['side']} {int(p['qty'])} sh"
        nxt = f"stop {pl.get('stop')}, flat 15:55" if p["status"] == "OPEN" else p.get("exit_reason")
    elif p["kind"] == "spread":
        desc = " / ".join(f"{'-' if l.get('action') == 'sell' else '+'}{l.get('label')}" for l in p["legs"])
        nxt = (f"max loss ${p.get('max_loss')}; " + (pl.get("stop") or pl.get("exit_rule") or "15:25")) if p["status"] == "OPEN" else p.get("exit_reason")
    else:
        desc = (p["legs"][0].get("label") if p["legs"] else "") + (" (options shadow)" if str(p["ledger"]).endswith("_opt") else "")
        nxt = (f"premium stop {pl.get('premium_stop')} ({pl.get('premium_stop_rule')})" if pl.get("premium_stop") else "exits with the share trade") \
            if p["status"] == "OPEN" else p.get("exit_reason")
    if pl.get("pending_exit"):
        nxt = f"EXIT PENDING: {pl['pending_exit'].get('reason')} ({pl['pending_exit'].get('why')})"
    return {k: p.get(k) for k in ("id", "ledger", "book", "kind", "date", "ticker", "direction", "side", "qty", "entry_px", "entry_t",
                                  "exit_px", "exit_t", "exit_reason", "status", "realized", "fees", "risk_usd", "max_loss", "r_mult",
                                  "legs", "version", "parent_id")} | {"desc": desc, "next": nxt, "mtm": pl.get("mtm")}


def post(path, body):
    import v4risk
    if path == "/api/v4/kill":
        return v4risk.kill(str((body or {}).get("reason") or "kill switch (API)")[:120])
    if path == "/api/v4/enable":
        return v4risk.enable(bool((body or {}).get("on", True)))
    return None
