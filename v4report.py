"""v4report.py - the numbers the Research page and /api/v4 show for the v4 lineup. Code computes, nothing estimated.

Per ledger (closed trades only, paper = simulated fills on live quotes): trades, win rate, average win, average loss,
expectancy per trade after costs, profit factor, max drawdown (peak to trough of cumulative P/L in close order), net,
average R, and a 95% interval for the expectancy that resamples whole SESSIONS (from 5 sessions up). Under 30 trades
the row says so. Index ledgers are split SPY vs QQQ (and XSP); stock ledgers sit next to their options shadow on the
SAME entries; share ledgers also show matched random entries (same stock, day, side, stop distance and flat time,
entered at a random bar's next open, $0.02/share, 50 paths, fixed seed), scored after the close by score_controls().
The `noise` reference ledger and the `old` ledger (legacy forward test, not from a published source; Nick kept it
active) live in the v3 positions table, unchanged, and are shown in the index book with the same metrics.
The swing book (etf10_rsi2.py, held overnight) row carries its evidence label, the T6 R2 backtest numbers (research and
sealed windows, labeled BACKTEST) and the forward mean % per trade in the same unit.
The core book (core_spy.py, the T30b SPY core) row carries its evidence label, the T30 backtest numbers (labeled BACKTEST
in-sample) and the T30b account view (equity, margin interest, overnight gross); the overview repeats the account view.
The sprint book (sprint_paper.py) rows also carry their evidence label ("PAPER (simulated fills)"), status ("forward
test of an in-sample backtest (not promoted)"), the source backtest run id and that backtest's own numbers (labeled
BACKTEST in-sample), split SPY vs QQQ.
"""
import hashlib

import numpy as np

import core
import retire
import store
import v4store as S

BOOKS = [
    ("index", "Index momentum: SPY / QQQ 0DTE options", ["noise", "noise_v2", "noise_trend", "old"]),
    ("premium", "Index premium selling: paper credit spreads (SPY / QQQ / XSP)", ["orb_credit", "ic_20d"]),
    ("stocks", "Stocks in play: shares, with an options shadow on the same entries", ["sip_orb5", "sip_orb5_x", "sip_orb15"]),
    ("catalyst", "Catalysts: earnings-day breakouts and the news-drift event study", ["earn_day"]),
    ("sprint", "Sprint forward tests: PAPER (simulated fills) twins of sprint backtests (in-sample; otm_h out-of-sample), SPY / QQQ 0DTE options, not promoted",
     ["fb_or", "otm_put", "otm_bounce", "otm_h"]),
    ("swing", "ETF swing (held overnight, approved 2026-11-10): PAPER (simulated fills) RSI(2) pullbacks on 10 ETFs in shares; "
              "BACKTEST research and sealed out-of-sample windows passed; forward test, not promoted", ["etf10_rsi2"]),
    ("trend", "Intraday trend: PAPER (simulated fills) noise band on SPY shares (T12a long/short, T12b long only), flat at the "
              "close; BACKTEST research 2003-2021 and sealed 2022-2025 passed; forward test, not promoted", ["nbs_spy_ls", "nbs_spy_long"]),
    ("pead", "Earnings drift (held overnight, approved 2026-11-11): PAPER (simulated fills) S&P 500 shares after a top-10% earnings "
             "reaction, held 20 sessions (pead_t21_tp also takes profit); BACKTEST research 1997-2021 and sealed 2022-2025 passed; forward test, "
             "not promoted", ["pead_t21", "pead_t21_tp"]),
    ("core", "SPY core (T30b, held, 2026-11-11): PAPER (simulated fills) SPY sized to the T30b account (core + noise band + ETF "
             "swing, minus 6.5% margin interest); BACKTEST in-sample portfolio arithmetic beat SPY alone; forward test, not promoted",
     ["core_spy"]),
]
SPRINT_LEDGERS = ("fb_or", "otm_put", "otm_bounce", "otm_h")
LEGACY_TABLE = ("noise", "old")             # ledgers kept in the v3 positions table, read-only here
LABELS = {"old": "Old rules (Oct 28): legacy forward test (not from a published source)",
          "noise": "Noise band (reference, unchanged)", "noise_v2": "Noise band v2 (paper exits, -50% stop)",
          "noise_trend": "Noise band on trend days", "orb_credit": "Opening-range credit spread", "ic_20d": "20-delta iron condor",
          "sip_orb5": "Stocks in play, 5-min ORB", "sip_orb5_x": "Stocks in play, RV 5x / ATR $2", "sip_orb15": "Stocks in play, 15-min ORB",
          "earn_day": "Earnings day, RV 5x / ATR $2",
          "fb_or": "Failed-break calls, opening-range lows (forward test of setups_v2-012)",
          "otm_put": "Far-OTM 10:30 puts, calm up days (forward test of otm_v1-011)",
          "otm_bounce": "Far-OTM 11:00 calls, stressed down days (forward test of otm_v1-042, WATCH-ONLY)",
          "otm_h": "Far-OTM 11:00 calls, busy days: rule H (forward test of otm_v1-040 + f_rvol >= 1.06)",
          "etf10_rsi2": "ETF RSI(2) swing, 10 ETFs, 3 x $1k (forward test of T6 R2)",
          "nbs_spy_ls": "Noise band, SPY shares, long + short, $3k (forward test of T12a)",
          "nbs_spy_long": "Noise band, SPY shares, long only, $3k (forward test of T12b)",
          "pead_t21": "Post-earnings drift, S&P 500 shares, 5 x $600, 20 sessions (forward test of T21)",
          "pead_t21_tp": "Post-earnings drift + take-profit, S&P 500 shares, 5 x $600 (forward test of T23a)",
          "core_spy": "SPY core = T30b account equity, held, monthly rebalance (forward test of T30b)"}
SHARE_LEDGERS = ("sip_orb5", "sip_orb5_x", "sip_orb15", "earn_day")


def metrics(trades):
    """trades: [{date, realized, r?}] in close order -> the standard block."""
    n = len(trades)
    out = {"trades": n, "small_sample": n < 30}
    if not n:
        return out
    pl = np.array([float(t["realized"] or 0) for t in trades])
    wins, losses = pl[pl > 0], pl[pl <= 0]
    cum = np.cumsum(pl)
    peak = np.maximum.accumulate(np.r_[0.0, cum])[1:]
    out.update(net=round(float(pl.sum()), 2), win_rate=round(100 * len(wins) / n, 1),
               avg_win=round(float(wins.mean()), 2) if len(wins) else None,
               avg_loss=round(float(losses.mean()), 2) if len(losses) else None,
               expectancy=round(float(pl.mean()), 2),
               profit_factor=round(float(wins.sum() / -losses.sum()), 2) if len(losses) and losses.sum() < 0 else None,
               max_drawdown=round(float((peak - cum).max()), 2), sessions=len({t["date"] for t in trades}))
    rs = [t["r"] for t in trades if t.get("r") is not None]
    out["avg_r"] = round(float(np.mean(rs)), 3) if rs else None
    by = {}
    for t in trades:
        by.setdefault(t["date"], []).append(float(t["realized"] or 0))
    if len(by) >= 5:
        rnd = np.random.default_rng(7)
        days = list(by.values())
        sims = []
        for _ in range(1000):
            pick = [days[i] for i in rnd.integers(0, len(days), len(days))]
            flat = [x for d in pick for x in d]
            sims.append(np.mean(flat))
        sims.sort()
        out["ci95"] = [round(float(sims[24]), 2), round(float(sims[974]), 2)]
    return out


def _v4_trades(ledger, since, ticker=None):
    rows = [p for p in S.positions(ledger=ledger, status="CLOSED") if p["date"] >= since and (ticker is None or p["ticker"] == ticker)]
    rows.sort(key=lambda p: p.get("exit_t") or "")
    return [{"date": p["date"], "realized": p["realized"], "r": p.get("r_mult"), "id": p["id"], "ticker": p["ticker"],
             "plan": p.get("plan") or {}, "parent_id": p.get("parent_id")} for p in rows]


def _legacy_trades(ledger, since, ticker=None):
    q = "SELECT id, date, ticker, realized, closed FROM positions WHERE ledger=? AND status='CLOSED' AND date>=?"
    a = [ledger, since]
    if ticker:
        q += " AND ticker=?"
        a.append(ticker)
    return [{"date": r["date"], "realized": r["realized"], "r": None, "id": r["id"], "ticker": r["ticker"]}
            for r in store.q(q + " ORDER BY closed", tuple(a))]


def _open_count(ledger):
    if ledger in LEGACY_TABLE:
        return len(store.positions(ledger=ledger, status="OPEN"))
    return len(S.positions(ledger=ledger, status="OPEN"))


def ledger_row(ledger, book, since):
    legacy = ledger in LEGACY_TABLE
    get = _legacy_trades if legacy else _v4_trades
    tr = get(ledger, since)
    row = {"ledger": ledger, "label": LABELS.get(ledger, ledger), "book": book, "open": _open_count(ledger), **metrics(tr)}
    if retire.legacy_label(ledger):
        row["legacy"] = retire.legacy_label(ledger)
    if ledger in SPRINT_LEDGERS:
        try:
            import sprint_paper
            row.update({k: v for k, v in sprint_paper.report_meta(ledger).items() if k != "label"})
        except Exception as e:
            row["sprint_error"] = type(e).__name__
    if ledger == "etf10_rsi2":                      # evidence labels + the backtest numbers in the same unit (% per trade)
        try:
            import etf10_rsi2
            row.update({k: v for k, v in etf10_rsi2.report_meta(tr).items() if k != "label"}, evidence=etf10_rsi2.LABEL)
        except Exception as e:
            row["swing_error"] = type(e).__name__
    if book == "pead":                              # evidence labels + the T21 backtest numbers (% per trade)
        try:
            import pead_t21
            meta = pead_t21.report_meta(tr, ledger)
            row.update({k: v for k, v in meta.items() if k != "label"}, evidence=meta["label"])
        except Exception as e:
            row["pead_error"] = type(e).__name__
    if book == "core":                              # evidence label, the T30 backtest numbers and the T30b account view
        try:
            import core_spy
            row.update({k: v for k, v in core_spy.report_meta(tr).items() if k != "label"}, evidence=core_spy.LABEL)
        except Exception as e:
            row["core_error"] = type(e).__name__
    if book == "trend":                             # evidence labels + the T12 backtest numbers (bp per trade day)
        try:
            import nb_shares
            row.update({k: v for k, v in nb_shares.report_meta(ledger, tr).items() if k != "label"}, evidence=nb_shares.LABEL)
        except Exception as e:
            row["trend_error"] = type(e).__name__
    if book in ("index", "premium", "sprint"):
        tick = sorted({t["ticker"] for t in tr} | {"SPY", "QQQ"})
        row["by_ticker"] = {t: metrics(get(ledger, since, t)) for t in tick}
    if ledger in SHARE_LEDGERS:
        sh = _v4_trades(f"{ledger}_opt", since)
        row["shadow"] = dict(metrics(sh), ledger=f"{ledger}_opt", open=_open_count(f"{ledger}_opt"))
        parents = {t["parent_id"] for t in sh if t.get("parent_id")}
        paired = [t for t in tr if t["id"] in parents]
        row["shadow"]["same_entries"] = {"shares": metrics(paired), "options": metrics(sh),
                                         "note": "the share trades that had a shadow vs those shadows (same entry and exit moments)"}
        no_c = [d for d in S.decisions(ledger=f"{ledger}_opt", limit=5000) if d["decision"] != "ORDER" and d["date"] >= since]
        reasons = {}
        for d in no_c:
            k = (d["reasons"] or ["?"])[0].split(":")[0][:80]
            reasons[k] = reasons.get(k, 0) + 1
        row["shadow"]["no_contract"] = reasons
        ctl = [t for t in tr if (t.get("plan") or {}).get("ctl_r") is not None and (t.get("plan") or {}).get("yard_r") is not None]
        if ctl:
            yr, cr = [t["plan"]["yard_r"] for t in ctl], [t["plan"]["ctl_r"] for t in ctl]
            row["random"] = {"n": len(ctl), "strategy_r": round(float(np.mean(yr)), 3), "random_r": round(float(np.mean(cr)), 3),
                             "edge_r": round(float(np.mean(yr) - np.mean(cr)), 3),
                             "note": "same yardstick for both: next-bar-open entry, same stop distance, flat time, $0.02/share"}
        buckets = {}
        for t in tr:
            b = (t.get("plan") or {}).get("stop_bucket")
            if b:
                buckets.setdefault(b, []).append(t)
        if buckets:
            row["by_stop_bucket"] = {b: {k: v for k, v in metrics(x).items() if k in ("trades", "win_rate", "expectancy", "avg_r")}
                                     for b, x in sorted(buckets.items())}
    blocks = [d for d in S.decisions(ledger=ledger, limit=5000) if d["decision"] == "BLOCKED-RISK" and d["date"] >= since]
    row["risk_blocks"] = len(blocks)
    return row


def retired_rows(since):
    import paper
    out = []
    for led in paper.PORTFOLIOS:
        if not retire.is_retired(led):
            continue
        tr = _legacy_trades(led, since)
        if not tr and not store.positions(ledger=led, status="OPEN"):
            continue
        out.append({"ledger": led, "open": len(store.positions(ledger=led, status="OPEN")), "retired": True, **metrics(tr)})
    return out


def overview(since="2026-11-02"):
    import v4risk
    books = []
    for b, title, leds in BOOKS:
        books.append({"book": b, "title": title, "ledgers": [ledger_row(l, b, since) for l in leds]})
    try:
        import news_drift
        nd = news_drift.summary(since)
    except Exception as e:
        nd = {"error": type(e).__name__}
    try:
        import chain_logger
        ch = chain_logger.status()
    except Exception as e:
        ch = {"error": type(e).__name__}
    try:
        import sip_orb
        sip = sip_orb.status()
    except Exception as e:
        sip = {"error": type(e).__name__}
    try:
        import v4index
        idx = v4index.status()
    except Exception as e:
        idx = {"error": type(e).__name__}
    try:
        import etf10_rsi2
        swing = etf10_rsi2.status()
    except Exception as e:
        swing = {"error": type(e).__name__}
    try:
        trk = tracking()
    except Exception as e:
        trk = {"error": type(e).__name__}
    try:
        import core_spy
        core_acct = core_spy.account()
    except Exception as e:
        core_acct = {"error": type(e).__name__}
    return {"since": since, "books": books, "tracking": trk, "risk": v4risk.status(), "news_drift": nd, "chains": ch, "stocks_worker": sip,
            "index_engine": idx, "swing_worker": swing, "core_account": core_acct,
            "retired": {"list": retire.retired_list(), "ledgers": retired_rows("2000-01-01")},
            "void": [{k: p[k] for k in ("id", "ledger", "date", "exit_reason")} for p in S.positions(status="VOID")],
            "note": ("Paper only: simulated fills on live Schwab quotes, never real money. Under 30 trades is not evidence. "
                     "Each ledger is its own forward test; promotion needs the gates in docs/STRATEGY_PLAN.md section 5.")}


# ---------------------------------------------------------------- fresh-start tracker (Nick, 2026-10-31)
TRACK_DEFAULT = {"start": "2026-11-02", "account_usd": 10000.0}


def tracking_cfg():
    """config/v4.json "tracking": {"start": "YYYY-MM-DD", "account_usd": n}. Each strategy is scored as its own account
    of that size from that date (paper, simulated fills). Bad or missing values fall back to Nov 2 2026 and $10,000."""
    try:
        t = retire.cfg().get("tracking") or {}
    except Exception:
        t = {}
    start = str(t.get("start") or TRACK_DEFAULT["start"])[:10]
    try:
        import datetime as _dt
        _dt.date.fromisoformat(start)
    except (TypeError, ValueError):
        start = TRACK_DEFAULT["start"]
    try:
        acct = float(t.get("account_usd") or TRACK_DEFAULT["account_usd"])
    except (TypeError, ValueError):
        acct = TRACK_DEFAULT["account_usd"]
    return {"start": start, "account_usd": acct if acct > 0 else TRACK_DEFAULT["account_usd"]}


def _track_row(ledger, book, start, acct, today):
    legacy = ledger in LEGACY_TABLE
    tr = (_legacy_trades if legacy else _v4_trades)(ledger, start)
    m = metrics(tr)
    net = float(m.get("net") or 0.0)
    today_pl = round(sum(float(t["realized"] or 0) for t in tr if t["date"] == today), 2)
    opens = store.positions(ledger=ledger, status="OPEN") if legacy else S.positions(ledger=ledger, status="OPEN")
    marks = [float((p.get("plan") or {}).get("mtm")) for p in opens if not legacy and (p.get("plan") or {}).get("mtm") is not None]
    open_mark = round(sum(marks), 2) if marks else None
    return {"ledger": ledger, "label": LABELS.get(ledger, ledger), "book": book, "trades": m["trades"],
            "win_rate": m.get("win_rate"), "profit_factor": m.get("profit_factor"), "expectancy": m.get("expectancy"),
            "net": round(net, 2), "return_pct": round(100 * net / acct, 2), "equity": round(acct + net, 2),
            "max_drawdown": m.get("max_drawdown"), "max_drawdown_pct": round(100 * float(m.get("max_drawdown") or 0) / acct, 2),
            "today": today_pl, "open": len(opens), "open_mark": open_mark, "small_sample": m.get("small_sample", True)}


def tracking(start=None, account_usd=None):
    """The fresh-start view: every active strategy as its own paper account of `account_usd`, counted from `start`
    (closed trades; open trades shown as a count and, for v4 ledgers, their last mark). Plus each book and the desk."""
    c = tracking_cfg()
    start = str(start or c["start"])[:10]
    acct = float(account_usd or c["account_usd"])
    today = core.now_et().date().isoformat()
    rows = [_track_row(l, b, start, acct, today) for b, _, leds in BOOKS for l in leds]
    def total(rs, n_acct):
        net = round(sum(r["net"] for r in rs), 2)
        return {"trades": sum(r["trades"] for r in rs), "net": net, "today": round(sum(r["today"] for r in rs), 2),
                "open": sum(r["open"] for r in rs), "accounts": n_acct, "capital": round(acct * n_acct, 2),
                "return_pct": round(100 * net / (acct * n_acct), 2) if n_acct else None}
    books = {b: total([r for r in rows if r["book"] == b], len(leds)) for b, _, leds in BOOKS}
    return {"start": start, "account_usd": acct, "today": today, "ledgers": rows, "books": books,
            "desk": total(rows, len(rows)),
            "note": (f"Fresh start: each strategy is scored as its own ${acct:,.0f} paper account from {start} "
                     "(simulated fills on live quotes, never real money). Closed trades only; open trades are listed with "
                     "their last mark. Under 30 trades is not evidence. Change the date or size in config/v4.json \"tracking\".")}


# ---------------------------------------------------------------- matched random entries for share trades (after the close)
def _seed(pid):
    return int(hashlib.sha256(pid.encode()).hexdigest()[:8], 16)


def score_controls(day, bars_fn=None):
    """For each closed share trade of `day` without a score: its own outcome under one yardstick and the mean of 50
    matched random entries under the same yardstick. Annotates the position (never touches its P/L)."""
    import matched_benchmarks as MB
    import pandas as pd
    import sip_orb
    done = 0
    last_entry, flat = sip_orb._times(pd.Timestamp(f"{day} 12:00", tz=core.ET).to_pydatetime())
    for p in S.positions(day=str(day), status="CLOSED", ledgers=list(SHARE_LEDGERS)):
        pl = p.get("plan") or {}
        if pl.get("ctl_r") is not None or pl.get("ctl_why"):
            continue
        m1 = None
        try:
            m1 = (bars_fn or _bars_for)(p["ticker"], day)
        except Exception:
            m1 = None
        if m1 is None or not len(m1):
            S.annotate(p["id"], ctl_why="no bars for the day")
            continue
        m1 = m1[m1.index.date == pd.Timestamp(str(day)).date()].between_time("09:30", "15:59")
        a = MB.arrays(m1)
        side = "C" if p["side"] == "long" else "P"
        dist = pl.get("stop_dist")
        et = pd.Timestamp(p["entry_t"])
        after = [i for i, ts in enumerate(m1.index) if ts >= et.ceil("1min")]
        if not dist or not after:
            S.annotate(p["id"], ctl_why="no bar after the entry")
            continue
        own = MB.outcome_arrays(a, after[0], side, dist, target_r=1e6, flat=flat, cost_per_share=0.02)
        ctl, n = MB.control_mean(a, side, dist, paths=50, seed=_seed(p["id"]), window=("09:35", last_entry), target_r=1e6,
                                 flat=flat, cost_per_share=0.02)
        S.annotate(p["id"], yard_r=own["r"] if own else None, ctl_r=ctl, ctl_n=n,
                   ctl_rule="next-bar-open entry, same stop distance, flat time, $0.02/share; 50 random entries 09:35-last entry")
        done += 1
    return done


def _bars_for(t, day):
    try:
        import lab
        m = lab.archive_read(day, t)
        if m is not None and len(m):
            return m
    except Exception:
        pass
    import scanner
    return scanner._fetch.m1_today(t, day)
