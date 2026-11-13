"""v4api.py - the /api/v4 endpoints (server.py hands every /api/v4* request here). Read-only views of the v4 paper
ledgers plus the v4 kill switch. Nothing here can place an order anywhere.

GET  /api/v4/chains           option-chain logger status (data/chains, gitignored)
GET  /api/v4/risk             the shared v4 risk layer: hard-coded limits, open counts, book P/L today, FOMC flag
POST /api/v4/kill             {"reason"}: v4 entries OFF and every open v4 paper position closed (pending if no quote)
POST /api/v4/enable           {"on": true|false}: v4 entries back on (or off without closing anything)
GET  /api/v4?since=           the v4 lineup by book: trades, win rate, avg win/loss, expectancy, profit factor, max DD,
                              SPY vs QQQ, shares vs options shadow, matched random entries; risk; retired archive
GET  /api/v4/tracking?start=&account=   the fresh-start view: each strategy as its own paper account (default from
                              config/v4.json "tracking": Nov 2 2026, $10,000), P/L and % return since then, books, desk
GET  /api/v4/positions?status=&ledger=&day=   v4 paper positions with a one-line description and the last mark
GET  /api/v4/decisions?day=&ledger=&kind=     every v4 decision (checks, entries, skips, risk blocks, rankings)
GET  /api/v4/swing            the ETF swing ledger (etf10_rsi2, held overnight): PAPER (simulated fills), today's plan
                              (signals from the last finished daily bar, exits due), switch, status
GET  /api/v4/trend            the SPY noise band shares ledgers (nb_shares: nbs_spy_ls, nbs_spy_long): PAPER (simulated
                              fills), today's prep (sigma, prior close), checks done, pending orders, status
GET  /api/v4/pead             the post-earnings drift ledgers (pead_t21, pead_t21_tp; held overnight): PAPER (simulated fills), today's
                              plan (8-K Item 2.02 events, EARs, the trailing cutoff, exits due), data status, switch
GET  /api/v4/core             the T30b SPY core (core_spy, held): PAPER (simulated fills), the T30b account view (equity,
                              P/L by ledger, margin interest, overnight gross, margin warning), the interest log, switch
GET  /api/v4/tcore            the T47 trend core (core_trend, held): PAPER (simulated fills), today's SPY/QQQ trend signals,
                              the T47 account view (equity, P/L by ledger, margin interest, maintenance need), interest log, switch
GET  /api/v4/score            the T44 SSO trend core (core_sso, held, SGOV while out): PAPER (simulated fills), today's SPY trend
                              signal, the T44 account view, interest log, switch
GET  /api/v4/killfile         B7: the KILL file watcher (touch KILL in the desk folder = v4 kill switch, once per file)
GET  /api/v4/copilot?day=     B8/B5/B9: today's co-pilot alerts (pattern, level, checklist, stop/target, event flags, lag; CONTEXT,
                              not tested edges), switches (watch-only = alerts without paper shadows), open PAPER shadows
GET  /api/v4/telegram         Telegram alerts: configured or not, messages sent, button taps, last error (never the token)
GET  /api/v4/copilot/score    B4: the report card: every labeled alert by pattern, checklist score, Nick's answer and ticker
POST /api/v4/copilot/feedback {"id", "took": true|false}: Nick's answer for one alert (feeds the report card)
GET  /api/v4/sprint           the sprint forward-test ledgers (fb_or, otm_put, otm_bounce, otm_h): PAPER (simulated fills), their
                              source backtest runs and numbers (in-sample), the rules read from the pinned specs, switches,
                              deviations from the backtest
"""
SPRINT = ("fb_or", "otm_put", "otm_bounce", "otm_h")


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
    if path == "/api/v4/tracking":
        import v4report
        acct = _one(q, "account")
        try:
            acct = float(acct) if acct else None
        except ValueError:
            acct = None
        st = _one(q, "start")
        return v4report.tracking(str(st)[:10] if st else None, acct if acct and acct > 0 else None)
    if path == "/api/v4/positions":
        import v4store as S
        st = _one(q, "status")
        rows = S.positions(status=st if st in ("OPEN", "CLOSED", "VOID") else None, ledger=_one(q, "ledger"), day=_one(q, "day"))
        return [view(p) for p in rows][-500:]
    if path == "/api/v4/tcore":
        import core_trend
        return core_trend.status()
    if path == "/api/v4/killfile":
        import killfile
        return killfile.status()
    if path == "/api/v4/copilot":
        import copilot
        return copilot.status(_one(q, "day"))
    if path == "/api/v4/telegram":
        import telegram_alerts
        return telegram_alerts.status()
    if path == "/api/v4/copilot/score":
        import copilot
        return copilot.scorecard()
    if path == "/api/v4/score":
        import core_sso
        return core_sso.status()
    if path == "/api/v4/core":
        import core_spy
        return core_spy.status()
    if path == "/api/v4/pead":
        import pead_t21
        return pead_t21.status()
    if path == "/api/v4/trend":
        import nb_shares
        return nb_shares.status()
    if path == "/api/v4/swing":
        import etf10_rsi2
        return etf10_rsi2.status()
    if path == "/api/v4/sprint":
        import sprint_paper
        return sprint_paper.status()
    if path == "/api/v4/decisions":
        import v4store as S
        lim = max(1, min(2000, int(_one(q, "limit", 300) or 300)))
        return S.decisions(day=_one(q, "day"), ledger=_one(q, "ledger"), kind=_one(q, "kind"), limit=lim)
    return None


def view(p):
    """A position for the page: one-line description, the last mark and what happens next."""
    pl = p.get("plan") or {}
    if p["kind"] == "shares":
        q = float(p["qty"] or 0)
        desc = f"{p['side']} {int(q) if q.is_integer() else q:g} sh"
        if p["status"] != "OPEN":
            nxt = p.get("exit_reason")
        elif pl.get("exit_rule"):                   # the swing book (etf10_rsi2): no stop, no 15:55 flat
            nxt = pl["exit_rule"]
        else:
            nxt = f"stop {pl.get('stop')}, flat 15:55"
    elif p["kind"] == "spread":
        desc = " / ".join(f"{'-' if l.get('action') == 'sell' else '+'}{l.get('label')}" for l in p["legs"])
        nxt = (f"max loss ${p.get('max_loss')}; " + (pl.get("stop") or pl.get("exit_rule") or "15:25")) if p["status"] == "OPEN" else p.get("exit_reason")
    else:
        desc = (p["legs"][0].get("label") if p["legs"] else "") + (" (options shadow)" if str(p["ledger"]).endswith("_opt") else "")
        nxt = (f"premium stop {pl.get('premium_stop')} ({pl.get('premium_stop_rule')})" if pl.get("premium_stop") else "exits with the share trade") \
            if p["status"] == "OPEN" else p.get("exit_reason")
    extra = {}
    if p["ledger"] in SPRINT:                       # sprint forward tests: label, source run, exit rule
        if p["status"] == "OPEN":
            nxt = pl.get("exit_rule") or nxt
        extra = {"label": pl.get("label"), "status_label": pl.get("status"), "source_run": pl.get("source_run"),
                 "watch_only": pl.get("watch_only")}
    if pl.get("pending_exit"):
        nxt = f"EXIT PENDING: {pl['pending_exit'].get('reason')} ({pl['pending_exit'].get('why')})"
    return {k: p.get(k) for k in ("id", "ledger", "book", "kind", "date", "ticker", "direction", "side", "qty", "entry_px", "entry_t",
                                  "exit_px", "exit_t", "exit_reason", "status", "realized", "fees", "risk_usd", "max_loss", "r_mult",
                                  "legs", "version", "parent_id")} | {"desc": desc, "next": nxt, "mtm": pl.get("mtm")} | extra


def post(path, body):
    import v4risk
    if path == "/api/v4/kill":
        return v4risk.kill(str((body or {}).get("reason") or "kill switch (API)")[:120])
    if path == "/api/v4/enable":
        return v4risk.enable(bool((body or {}).get("on", True)))
    if path == "/api/v4/copilot/feedback":
        import copilot
        b = body or {}
        return copilot.feedback(str(b.get("id") or "")[:200], bool(b.get("took")))
    return None
