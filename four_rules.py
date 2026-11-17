"""four_rules.py - the 4 Rules tab (2026-11-17): GET /api/v4/rules.

Nick, 2026-11-17: "i tought we found like 4 good rules after all of our backtesting and i want a way to track that
better like how we did with v3 trading". The desk paper-trades only these four (config/v4.json "four_rules"; everything
else was stopped the same day, Nick: "Stop them"), one card each, built like the old v3 paper page: forward paper trades
toward the 40 a rule needs (CLAUDE.md step 5), win rate, P/L, open trades, the latest closed trades and an equity line,
next to what the sealed out-of-sample backtest says to expect. A fifth card shows the reference noise band in 0DTE
options, which Nick's phone alerts follow, with its own evidence (T42 FAIL) and any VOID trades (expiry_void.py).

Every number comes from the desk's records (PAPER, simulated fills) or from each module's own BACKTEST constants.
Forward trades count from config "four_rules_since" (2026-11-13: the desk's first day on its own server; days Chart's
computer slept before that have gaps, deploy/VPS_MOVE.md). A trade counts on the day it was opened.
"""
import retire
import store
import v4report as R
import v4store as S

VERSION = "2026-11-17.four-rules1"
SINCE_DEFAULT = "2026-11-13"
NEEDED = 40                    # forward paper trades before a rule can be promoted (CLAUDE.md step 5)


def _bt_nb():
    import nb_shares
    b = nb_shares.BACKTEST["sealed_2022_2025"]["T12a"]
    return {"label": "BACKTEST 2022-2025, out-of-sample", "line": f"+{b['mean_bp_day']:.2f} bp a day after costs "
            f"(90% range {b['ci90_bp'][0]:+.2f} to {b['ci90_bp'][1]:+.2f}), Sharpe {b['sharpe']:.2f}, {b['trades']:,} trades",
            "win_rate": None}


def _bt_rsi2():
    import etf10_rsi2
    b = etf10_rsi2.BACKTEST["sealed_2022_2025"]
    return {"label": "BACKTEST 2022-2025, out-of-sample", "line": f"{b['trades']} trades, {b['win_rate']:.0f}% won, "
            f"{b['mean_pct_2x_cost']:+.2f}% a trade after double costs, profit factor {b['profit_factor']:.2f}",
            "win_rate": b["win_rate"]}


def _bt_pead():
    import pead_t21
    b = pead_t21.TP_BACKTEST["sealed_2022_2025"]
    return {"label": "BACKTEST 2022-2025, out-of-sample", "line": f"{b['trades']} trades, {b['win_rate']:.0f}% won, "
            f"{b['mean_pct_after_costs']:+.2f}% a trade after costs, profit factor {b['profit_factor']:.2f}, "
            f"take-profit hit {b['tp_hit_pct']:.0f}% of the time", "win_rate": b["win_rate"]}


def _bt_sso():
    import core_sso
    b = core_sso.BACKTEST["t44_2022_2025"]
    return {"label": "BACKTEST 2022-2025, out-of-sample", "line": f"{b['cagr_pct']:.1f}% a year, worst drop "
            f"{b['worst_drop_pct']:.1f}% (the T44 account: this core plus the noise band and the ETF dips)", "win_rate": None}


RULES = [
    {"ledger": "nbs_spy_ls", "n": 1, "name": "Noise band, SPY shares", "test": "T12a", "hold": "Same day", "size": "$3,000",
     "what": "Buys or shorts SPY when it breaks out of its usual range for that time of day (checked every half hour). "
             "Out by the close.", "bt": _bt_nb},
    {"ledger": "etf10_rsi2", "n": 2, "name": "ETF dip buying", "test": "T6 R2", "hold": "A few days", "size": "3 x $1,000",
     "what": "Buys one of 10 big ETFs after a sharp 2-day dip (RSI 2 under 10) while it's above its 200-day average. "
             "Sells at the next open after it closes back above its 5-day average.", "bt": _bt_rsi2},
    {"ledger": "pead_t21_tp", "n": 3, "name": "Earnings drift", "test": "T23a", "hold": "Up to 20 trading days",
     "size": "5 x $600",
     "what": "Buys S&P 500 stocks after a top-10% earnings-day jump. Sells after 20 trading days, or earlier at its "
             "take-profit.", "bt": _bt_pead},
    {"ledger": "core_sso", "n": 4, "name": "SSO trend core", "test": "T44", "hold": "Weeks to months",
     "size": "The T44 account",
     "what": "Holds SSO (2x the S&P 500) while SPY is in its 200-day uptrend, and SGOV (T-bills) when it isn't.",
     "bt": _bt_sso},
]
T42 = {"label": "BACKTEST on real 0DTE option prices, Feb 2024-2026 (T42: FAIL)",   # the reference card (CLAUDE.md step 6)
       "line": "627 trades, 13% won, -3.2% of the premium a trade on average (about -$711 a year at 1 contract). "
               "The same signals in SPY shares passed: that's rule 1."}


def since():
    s = str((retire.cfg() or {}).get("four_rules_since") or SINCE_DEFAULT)[:10]
    return s if len(s) == 10 else SINCE_DEFAULT


def _curve(trades):
    out, c = [], 0.0
    for t in trades:
        c += float(t["realized"] or 0)
        out.append(round(c, 2))
    return out


def _v4_card(rule, start):
    import v4api
    led = rule["ledger"]
    tr = R._v4_trades(led, start)
    m = R.metrics(tr)
    opens = [v4api.view(p) for p in S.positions(ledger=led, status="OPEN")]
    marks = [float(o["mtm"]) for o in opens if o.get("mtm") is not None]
    closed = [p for p in S.positions(ledger=led, status="CLOSED") if p["date"] >= start]
    closed.sort(key=lambda p: p.get("exit_t") or "", reverse=True)
    recent = [{"date": p["date"], "ticker": p["ticker"], "desc": v4api.view(p).get("desc"), "pl": round(float(p["realized"] or 0), 2),
               "why": p.get("exit_reason")} for p in closed[:8]]
    try:
        bt = rule["bt"]()
    except Exception as e:                      # a module that fails to import must not take the tab down
        bt = {"label": "BACKTEST", "line": f"unavailable ({type(e).__name__})", "win_rate": None}
    return {"ledger": led, "n": rule["n"], "name": rule["name"], "test": rule["test"], "what": rule["what"],
            "hold": rule["hold"], "size": rule["size"], "trading": not retire.is_retired(led),
            "trades": m["trades"], "needed": NEEDED, "win_rate": m.get("win_rate"), "net": m.get("net", 0.0),
            "expectancy": m.get("expectancy"), "avg_win": m.get("avg_win"), "avg_loss": m.get("avg_loss"),
            "profit_factor": m.get("profit_factor"), "max_drawdown": m.get("max_drawdown"),
            "open": opens, "open_pl": round(sum(marks), 2) if marks else None, "recent": recent, "curve": _curve(tr),
            "backtest": {k: bt[k] for k in ("label", "line", "win_rate")}, "label": "PAPER (simulated fills)"}


def _noise_card(start):
    led = "noise"
    tr = R._legacy_trades(led, start)
    m = R.metrics(tr)
    opens = []
    for p in store.positions(ledger=led, status="OPEN"):
        pl = p.get("plan") or {}
        opens.append({"ticker": p["ticker"], "desc": f"{p['contract']} x{p['qty_open']}", "entry_px": p["fill"],
                      "date": p["date"], "last_bid": pl.get("last_bid")})
    closed = store.q("SELECT date, ticker, contract, realized, plan FROM positions WHERE ledger=? AND status='CLOSED' "
                     "AND date>=? ORDER BY closed DESC LIMIT 8", (led, start))
    import json
    recent = []
    for r in closed:
        try:
            why = (json.loads(r["plan"] or "{}") or {}).get("exit_reason")
        except ValueError:
            why = None
        recent.append({"date": r["date"], "ticker": r["ticker"], "desc": r["contract"], "pl": round(float(r["realized"] or 0), 2),
                       "why": why})
    void = []
    for p in store.positions(ledger=led, status="VOID"):
        v = (p.get("plan") or {}).get("void") or {}
        void.append({"date": p["date"], "ticker": p["ticker"], "desc": p["contract"], "fill": p["fill"],
                     "value_modeled": v.get("value_modeled"), "expiry": v.get("expiry")})
    return {"ledger": led, "name": "Noise band, 0DTE options", "test": "Reference",
            "what": "The same noise band, traded with 1 SPY or QQQ 0DTE option. Your phone alerts follow this one. "
                    "Out by 3:25 PM ET, or at a 20% premium loss.",
            "hold": "Same day", "size": "1 contract", "trading": not retire.is_retired(led), "trades": m["trades"],
            "win_rate": m.get("win_rate"), "net": m.get("net", 0.0), "expectancy": m.get("expectancy"),
            "avg_win": m.get("avg_win"), "avg_loss": m.get("avg_loss"), "profit_factor": m.get("profit_factor"),
            "open": opens, "recent": recent, "void": void, "curve": _curve(tr), "backtest": T42,
            "label": "PAPER (simulated fills)"}


def view():
    start = since()
    cfg_rules = list((retire.cfg() or {}).get("four_rules") or [r["ledger"] for r in RULES])
    cards = [_v4_card(r, start) for r in RULES if r["ledger"] in cfg_rules]
    stopped_open = [{"ledger": p["ledger"], "ticker": p["ticker"]} for p in S.positions(status="OPEN")
                    if retire.is_retired(p["ledger"])]
    total = round(sum(float(c["net"] or 0) for c in cards), 2)
    return {"version": VERSION, "since": start, "needed": NEEDED, "rules": cards, "noise": _noise_card(start),
            "total_net": total, "total_trades": sum(c["trades"] for c in cards),
            "stopped_still_open": stopped_open,
            "note": (f"PAPER: simulated fills on live quotes, never real money. Trades counted from {start}. "
                     f"Each rule needs {NEEDED} paper trades before it can be trusted; under 30 is not evidence yet.")}
