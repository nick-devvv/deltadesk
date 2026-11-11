"""etf10_rsi2.py - the ETF RSI(2) swing ledger: PAPER (simulated fills on live Schwab quotes), shares, multi-day holds.
REGISTERED 2026-11-10, before any forward trade. Not promoted. Never real money (there is no order path here).

Scope: Nick approved this overnight swing ledger on 2026-11-10 ("go"). It is the only v4 ledger that holds positions
across sessions; it lives in its own isolated risk book ("swing", v4risk) and its own worker thread, and it never calls
v4exec.overnight(), so the day-trading ledgers' "close anything left from an earlier session" rule never touches it.

Source and evidence (labels: BACKTEST = historical simulation, PAPER = this ledger's simulated fills)
  Rule family: Connors & Alvarez (2008), "Short Term Trading Strategies That Work": 2-period RSI pullbacks inside a
  200-day uptrend, exit on a close above the 5-day average. The desk's frozen variant "rsi2 F1" (TradingVault
  Research/2026-11-02-watchlist50-forward-prereg) also requires close < SMA(5) at entry and buys at the NEXT OPEN.
  Pre-registered as T6 R2 (TradingVault Research/2026-11-09-t56-prereg, approved by Nick 2026-11-09, rules locked
  before any result). Data: WRDS CRSP daily (split-adjusted open/close), survivorship-free.
    BACKTEST research 1997-2021: 1,491 trades, win 69%, +0.381%/trade after 2x costs, PF 1.77, 90% CI +0.25 to +0.51%,
      5/5 sub-periods positive, random-entry 90th percentile +0.12%. Portfolio (3 x $1k): Sharpe 0.72, max DD -5%.
    BACKTEST sealed 2022-2025 (out-of-sample, run once, pass criterion fixed before download): 270 trades, win 68%,
      +0.38%/trade after 2x costs, 90% CI +0.11 to +0.64%, PF 1.74. Portfolio (3 x $1k): CAGR 8.8%, Sharpe 0.71, max DD -7%.
      (Corrected 2026-11-10 for a CRSP old/v2 price-factor junction bug; rules unchanged, verdict unchanged. Was 267
      trades, PF 1.72, Sharpe 0.69.)
  Trials counted for the deflated Sharpe: TradingVault Ledger/variants-tried.md (T6 = 2 of the 19 WRDS trials, rows 51-69).

Rules (frozen; any change ships as a new ledger version and the forward count starts over)
  Universe   SPY QQQ IWM DIA XLF XLE XLV EEM GLD TLT (T6 R2's 10 ETFs). Long only.
  Signal     on the last FINISHED daily bar (the previous session; today's forming bar is never used):
             close > SMA(200) and close < SMA(5) and RSI(2) < 10. RSI is Wilder's (EWM alpha 1/2, adjust=False),
             computed exactly as wrds_lab/backtest_t56.rsi2.
  Entry      the next open: the first executable quote dated at least the decision latency after 09:30:00 ET and
             under 20 s old, bought at ask + $0.01 (v4store.share_buy). No fill by 09:40 -> MISSED (recorded).
  Exit       the next open after any finished daily close > SMA(5), counting the entry day's own close (backtest:
             j starts at the entry day). Sold at bid - $0.01. If the desk missed that open, the exit happens at the
             first valid quote afterwards and the reason says LATE. No stop, no target, no time stop.
  Positions  one per symbol; at most 3 open (3 slots of $1,000 notional, fractional shares to 4 decimals); same-day
             signals are taken in the universe order above (the backtest used CRSP permno order: also arbitrary).
             Exits at the open free their slot before that open's entries (as in the backtest).
  Costs      the shares1 fill model above, no commission. BACKTEST used $0.02/share per side at 2x costs.
  Risk       v4risk book "swing" (isolated): per-symbol and book caps, the v4 kill switch, the emergency pause, and the
             approved risk framework's daily stop (no new entries after -$90 today, realized + open marks measured
             from the previous session's last mark). Exits are never blocked. risk_usd on each position = a 3-sigma
             one-day move on its notional (20-day close-to-close sigma), the framework's swing-book measure.
  Switch     config/v4.json "etf10_rsi2": true/false. Off stops new entries only; open positions still exit by rule.
Known deviations from the backtest: Schwab daily bars instead of CRSP (both split-adjusted, neither dividend-adjusted);
the first fresh quote after 09:30 instead of the official opening print; $1,000 fixed notional per slot instead of
min($1,000, cash); dividends are not credited to paper P/L.
Promotion (CLAUDE.md step 5, gate G5): 40 forward paper trades whose fills match the backtest's cost assumption.
"""
import math
import threading
import time
from datetime import timedelta

import numpy as np
import pandas as pd

import core
import store
import v4common as C
import v4exec
import v4risk
import v4store as S

LEDGER, BOOK = "etf10_rsi2", "swing"
VERSION = "2026-11-10.etf10-rsi2-1"   # rules version; evidence text corrected 2026-11-10 (no rule change)
SYMBOLS = ("SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLV", "EEM", "GLD", "TLT")
SMA_LONG, SMA_SHORT, RSI_MAX = 200, 5, 10.0
SLOTS, SLOT_USD = 3, 1000.0
PLAN_FROM, OPEN, FILL_LATE, CLOSE = "08:00", "09:30", "09:40", "16:00"
QUOTE_MAX_AGE_S = 20
MARK_EVERY_S = 60
SIGMA_DAYS = 20
LABEL = "PAPER (simulated fills); rules = T6 R2, BACKTEST research 1997-2021 pass + sealed 2022-2025 pass (out-of-sample)"
BACKTEST = {"research_1997_2021": {"label": "BACKTEST (research window)", "trades": 1491, "win_rate": 69.0,
                                   "mean_pct_2x_cost": 0.381, "profit_factor": 1.77, "ci90_pct": [0.25, 0.51],
                                   "portfolio_3x1k": {"sharpe": 0.72, "max_dd_pct": -5.0}},
            "sealed_2022_2025": {"label": "BACKTEST (sealed, out-of-sample, run once; corrected 2026-11-10)", "trades": 270,
                                 "win_rate": 68.1, "mean_pct_2x_cost": 0.38, "profit_factor": 1.74, "ci90_pct": [0.11, 0.64],
                                 "portfolio_3x1k": {"cagr_pct": 8.8, "sharpe": 0.71, "max_dd_pct": -7.1}}}
_state = {"status": "idle", "last_error": None, "thread": None, "stop": False, "step_s": None, "mark_t": None, "plan_try": None}
_lock = threading.RLock()


def fetch():
    import scanner
    return scanner._fetch


def switch_on():
    """config/v4.json "etf10_rsi2" (missing = off). Off stops new entries; exits always run."""
    import retire
    return bool(retire.cfg().get("etf10_rsi2", False))


# ================================================================ pure rules (no network, no clock)
def rsi(c, n=2):
    """Wilder RSI, identical to wrds_lab/backtest_t56.rsi2 (EWM alpha 1/n, adjust=False, over the whole history)."""
    d = c.diff()
    up, dn = d.clip(lower=0), (-d).clip(lower=0)
    rs = up.ewm(alpha=1.0 / n, adjust=False).mean() / dn.ewm(alpha=1.0 / n, adjust=False).mean()
    return 100 - 100 / (1 + rs)


def finished_daily(daily, day):
    """Daily bars dated strictly before `day` (finished sessions only), sorted, duplicates dropped."""
    if daily is None or not len(daily) or "Close" not in daily:
        return None
    d = daily.copy()
    d.index = pd.DatetimeIndex(d.index)
    if d.index.tz is not None:
        d.index = d.index.tz_convert(core.ET).tz_localize(None)
    d.index = d.index.normalize()
    d = d[~d.index.duplicated(keep="last")].sort_index()
    return d[d.index < pd.Timestamp(day)]


def indicators(daily, day):
    """Frame of close, sma5, sma200, rsi2, sig (entry signal) and above5 (exit signal) on finished bars; None if
    there are fewer than 200 finished closes (SMA(200) undefined: no signal, as in the backtest)."""
    d = finished_daily(daily, day)
    if d is None or len(d) < SMA_LONG:
        return None
    c = d["Close"].astype(float)
    out = pd.DataFrame({"close": c, "sma5": c.rolling(SMA_SHORT).mean(), "sma200": c.rolling(SMA_LONG).mean(), "rsi2": rsi(c)})
    out["sig"] = (out["close"] > out["sma200"]) & (out["close"] < out["sma5"]) & (out["rsi2"] < RSI_MAX)
    out["above5"] = out["close"] > out["sma5"]
    return out


def sigma20(daily, day):
    d = finished_daily(daily, day)
    if d is None or len(d) < SIGMA_DAYS + 1:
        return None
    r = d["Close"].astype(float).pct_change().dropna().iloc[-SIGMA_DAYS:]
    s = float(r.std())
    return s if s == s else None


def prev_session(day):
    """The last trading session before `day` (weekends and core.HOLIDAYS skipped)."""
    d = day - timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in core.HOLIDAYS:
        d -= timedelta(days=1)
    return d


def exit_due(ind, entry_date):
    """First finished close > SMA(5) on or after the entry day, or None. Returns (date, close, sma5)."""
    if ind is None:
        return None
    x = ind[(ind.index >= pd.Timestamp(entry_date)) & ind["above5"]]
    if not len(x):
        return None
    r = x.iloc[0]
    return x.index[0].date(), float(r["close"]), float(r["sma5"])


def size(fill):
    """(qty, notional): $1,000 per slot in fractional shares (4 decimals)."""
    if not fill or fill <= 0:
        return 0.0, 0.0
    q = math.floor(SLOT_USD / fill * 10_000) / 10_000
    return q, round(q * fill, 2)


def _r(x, k=4):
    return None if x is None or (isinstance(x, float) and x != x) else round(float(x), k)


# ================================================================ the morning plan (before the open)
def _pkey(day):
    return f"etf10:plan:{day}"


def make_plan(day, now, final=False):
    """Signals and due exits from the last finished daily bar. Stored once per day (a restart reuses it). A symbol
    whose history doesn't reach the previous session yet is retried; at `final` (the open) it's recorded NO DATA."""
    have = store.kv_get(_pkey(day))
    if have:
        return have
    f = fetch()
    want = prev_session(day)
    ind, raw, stale = {}, {}, []
    for t in SYMBOLS:
        try:
            dly = f.daily(t)
        except Exception as e:
            dly = None
            _state["last_error"] = f"daily {t}: {type(e).__name__}"
        i = indicators(dly, day)
        if i is None or i.index[-1].date() != want:
            stale.append(t)
            continue
        ind[t], raw[t] = i, dly
    if stale and not final:
        _state["status"] = f"waiting for {want} daily bars: {', '.join(stale)}"
        return None
    opens = {p["ticker"]: p for p in S.positions(ledger=LEDGER, status="OPEN")}
    exits, entries, rows = [], [], {}
    for t in SYMBOLS:
        if t not in ind:
            rows[t] = {"state": "NO DATA", "why": f"no finished daily bar for {want} by {now.strftime('%H:%M')}"}
            S.decide(f"{LEDGER}:check:{day}-{t}", LEDGER, t, "NO DATA", [rows[t]["why"]], {}, "check", VERSION)
            continue
        last = ind[t].iloc[-1]
        row = {"asof": str(want), "close": _r(last["close"]), "sma5": _r(last["sma5"]), "sma200": _r(last["sma200"]),
               "rsi2": _r(last["rsi2"], 2), "sig": bool(last["sig"]), "above5": bool(last["above5"]),
               "sigma20": _r(sigma20(raw[t], day), 6)}
        p = opens.get(t)
        if p is not None:
            due = exit_due(ind[t], p["date"])
            if due:
                d_sig, c, s5 = due
                late = d_sig != want
                why = (f"EXIT at the open: close {c:.2f} > SMA5 {s5:.2f} on {d_sig}" +
                       (f" (LATE: that session's next open was missed; exit at the first valid quote)" if late else ""))
                exits.append({"id": p["id"], "ticker": t, "reason": why, "signal_date": str(d_sig), "late": late})
                S.decide(f"{LEDGER}:exit:{day}-{p['id']}", LEDGER, t, "EXIT DUE", [why], dict(row, position=p["id"]), "exit", VERSION)
            row["state"] = "HOLDING" + (" (exit due)" if due else "")
            S.decide(f"{LEDGER}:check:{day}-{t}", LEDGER, t, "HOLDING", [f"open since {p['date']} (one position per symbol)"],
                     row, "check", VERSION)
        else:
            row["state"] = "SIGNAL" if row["sig"] else "NO SIGNAL"
            if row["sig"]:
                entries.append(t)
            why = (f"close {row['close']} > SMA200 {row['sma200']}, < SMA5 {row['sma5']}, RSI2 {row['rsi2']} < 10" if row["sig"] else
                   "; ".join(w for w, bad in ((f"close {row['close']} <= SMA200 {row['sma200']}", not row["close"] > row["sma200"]),
                                              (f"close {row['close']} >= SMA5 {row['sma5']}", not row["close"] < row["sma5"]),
                                              (f"RSI2 {row['rsi2']} >= 10", not row["rsi2"] < RSI_MAX)) if bad))
            S.decide(f"{LEDGER}:check:{day}-{t}", LEDGER, t, row["state"], [why], row, "check", VERSION)
        rows[t] = row
    plan = {"day": str(day), "asof": str(want), "made_at": now.isoformat(timespec="seconds"), "entries": entries,
            "exits": exits, "rows": rows, "no_data": stale, "version": VERSION}
    store.kv_set(_pkey(day), plan)
    S.decide(f"{LEDGER}:plan:{day}", LEDGER, "*", "PLAN", [f"{len(entries)} signal(s), {len(exits)} exit(s) due"],
             {"entries": entries, "exits": [e["id"] for e in exits], "no_data": stale, "asof": str(want)}, "plan", VERSION)
    return plan


# ================================================================ at the open: exits first, then entries
def _equity_q(t, quotes):
    q = dict((quotes or {}).get(t) or {})
    if not q:
        return None
    if q.get("quote_time") is None and q.get("quote_ms"):
        q["quote_time"] = pd.Timestamp(q["quote_ms"], unit="ms", tz="UTC").tz_convert(core.ET)
    return v4exec.equity_quote(t, {t: q})


def _final_entry(day, t, decision, why=None, data=None):
    return S.decide(f"{LEDGER}:{day}-{t}", LEDGER, t, decision, [why] if why else [], data or {}, "entry", VERSION)


def execute(day, now, quotes):
    plan = store.kv_get(_pkey(day))
    if not plan:
        return
    hm = now.strftime("%H:%M")
    open_t = C.at(day, OPEN)
    late = hm >= FILL_LATE
    exit_ids = {e["id"] for e in plan["exits"]}
    for e in plan["exits"]:
        p = S.get(e["id"])
        if p is None or p["status"] != "OPEN" or (p.get("plan") or {}).get("pending_exit"):
            continue                                          # closed already, or pending: manage() retries it
        q = _equity_q(p["ticker"], quotes)
        ok, why = C.quote_after(q, open_t, QUOTE_MAX_AGE_S)
        if ok:
            reason = e["reason"] + (f" (filled {hm}, after {FILL_LATE}: LATE)" if late and not e.get("late") else "")
            v4exec.close_now(p, reason, {p["ticker"]: q})
        elif late:
            v4exec.close_now(p, e["reason"] + f" (no fresh quote by {FILL_LATE}: {why})", {p["ticker"]: q} if q else None)
    on = switch_on()
    for t in plan["entries"]:
        if S.decided(f"{LEDGER}:{day}-{t}"):
            continue
        if not on:
            _final_entry(day, t, "SWITCH OFF", 'config/v4.json "etf10_rsi2" is off: no new entries (exits still run)')
            continue
        held = [p for p in S.positions(ledger=LEDGER, status="OPEN") if p["id"] not in exit_ids]
        if any(p["ticker"] == t for p in held):
            _final_entry(day, t, "SKIP", f"{t} already held (one position per symbol)")
            continue
        if len(held) >= SLOTS:
            _final_entry(day, t, "NO SLOT", f"all {SLOTS} slots in use ({', '.join(p['ticker'] for p in held)})",
                         {"held": [p["id"] for p in held]})
            continue
        q = _equity_q(t, quotes)
        ok, qwhy = C.quote_after(q, open_t, QUOTE_MAX_AGE_S)
        if not ok:
            if late:
                _final_entry(day, t, "MISSED", f"no fresh quote after the open by {FILL_LATE} ({qwhy})")
            continue                                          # wait for a quote dated after 09:30
        why = v4risk.admit(LEDGER, BOOK, t, "long", now)
        if why:
            _final_entry(day, t, "BLOCKED-RISK", why)
            continue
        fill = S.share_buy(q)
        qty, notional = size(fill)
        if qty <= 0:
            _final_entry(day, t, "SKIP", f"size 0 at {fill}")
            continue
        row = plan["rows"].get(t) or {}
        sg = row.get("sigma20")
        risk = round(notional * 3 * sg, 2) if sg else None
        rec = {"id": f"{LEDGER}:{day}-{t}", "ledger": LEDGER, "book": BOOK, "kind": "shares", "date": str(day), "ticker": t,
               "direction": "long", "side": "long", "qty": qty, "entry_px": fill, "entry_t": store.ts(),
               "signal_t": open_t.isoformat(), "quote_t": str(q.get("quote_time")), "fees": 0.0, "risk_usd": risk, "max_loss": None,
               "legs": [{"symbol": t, "label": f"{qty:g} sh", "action": "buy", "qty": qty}],
               "plan": {"label": LABEL, "status": "forward paper test (not promoted)", "signal": row, "asof": plan["asof"],
                        "bid": q["bid"], "ask": q["ask"], "notional": notional, "slot_usd": SLOT_USD,
                        "exit_rule": "next open after a daily close > SMA(5); no stop; held overnight (swing book)",
                        "risk_rule": "risk_usd = 3 x 20-day sigma x notional (risk framework, swing books)",
                        "day_base": 0.0, "day_base_day": str(day), "late": late},
               "version": VERSION, "exec_model": "shares1"}
        got, owhy = S.open_position(rec, "etf10_rsi2 entry at the open (paper, simulated fill)")
        if not got:
            _final_entry(day, t, "SKIP", owhy)
            continue
        _final_entry(day, t, "ORDER", None, {"position": got, "fill": fill, "qty": qty, "quote_t": str(q.get("quote_time"))})


# ================================================================ during the session: marks and pending exits
def manage(now, quotes=None):
    """Open positions of this ledger only: retry a pending exit, mark to the bid. Never closes a position for being
    from an earlier session (no v4exec.overnight here: holding overnight is the rule)."""
    day = str(now.date())
    for p in S.positions(ledger=LEDGER, status="OPEN"):
        q = _equity_q(p["ticker"], quotes) if quotes else None
        pl = p.get("plan") or {}
        if pl.get("pending_exit"):
            if q and C.quote_after(q, C.at(now.date(), OPEN), QUOTE_MAX_AGE_S)[0]:
                v4exec.retry_pending(p, {p["ticker"]: q})
            continue
        if not (q and q.get("executable") and q.get("bid") is not None):
            continue
        if pl.get("day_base_day") != day:                     # the day's P/L starts from the previous session's last mark
            S.update_plan(p["id"], day_base=float(pl.get("mtm") or 0.0) if str(p["date"]) != day else 0.0, day_base_day=day)
        mtm = round(S.pnl(p, q["bid"]), 2)
        S.update_plan(p["id"], mtm=mtm, last_mark=q["bid"], mark_t=str(q.get("quote_time")))
        S.mark(p["id"], mtm, mtm)


# ================================================================ worker
def step(now=None):
    now = now or core.now_et()
    t0 = time.time()
    day = now.date()
    sess = core.session_info(now)
    if sess.get("holiday"):
        _state["status"] = "market closed"
        return
    f = fetch()
    if not f.ready():
        _state["status"] = "waiting for Schwab (no decisions on delayed data)"
        return
    import schwab
    hm = now.strftime("%H:%M")
    plan = store.kv_get(_pkey(day))
    last_try = _state.get("plan_try")
    if not plan and PLAN_FROM <= hm < CLOSE and (hm >= OPEN or last_try is None or last_try > now
                                                 or (now - last_try).total_seconds() >= 60):
        _state["plan_try"] = now                              # before the open: at most one attempt a minute
        with schwab.priority("normal"):
            plan = make_plan(day, now, final=hm >= OPEN)
    opens = S.positions(ledger=LEDGER, status="OPEN")
    if not (OPEN <= hm < sess.get("close", CLOSE)):          # regular hours only (13:00 on early-close days)
        _state["status"] = f"{len(opens)} open, plan {'ready' if plan else 'not made'} ({sess['state']})"
        return
    at_open = hm < FILL_LATE or any((p.get("plan") or {}).get("pending_exit") for p in opens) or \
        (plan and any(S.get(e["id"]) and S.get(e["id"])["status"] == "OPEN" for e in plan["exits"])) or \
        (plan and not all(S.decided(f"{LEDGER}:{day}-{t}") for t in plan["entries"]))
    due_mark = _state["mark_t"] is None or (now - _state["mark_t"]).total_seconds() >= MARK_EVERY_S or _state["mark_t"] > now
    syms = sorted({p["ticker"] for p in opens} | (set(plan["entries"]) if plan and at_open else set()))
    quotes = {}
    if syms and (at_open or due_mark):
        _state["mark_t"] = now
        with schwab.priority("risk" if opens else "normal"):
            try:
                quotes, _ = f.quotes(syms)
            except Exception as e:
                _state["last_error"] = f"quotes: {type(e).__name__}"
    with schwab.priority("risk"):
        try:
            manage(now, quotes)
        except Exception as e:
            _state["last_error"] = f"manage: {type(e).__name__}: {e}"[:200]
    if plan:
        try:
            execute(day, now, quotes)
        except Exception as e:
            _state["last_error"] = f"execute: {type(e).__name__}: {e}"[:200]
    _state["status"] = f"{len(S.positions(ledger=LEDGER, status='OPEN'))} open" + (", at the open" if at_open else "")
    _state["step_s"] = round(time.time() - t0, 2)


def _run():
    while not _state["stop"]:
        try:
            step()
            try:
                import health
                health.beat("v4swing", True, _state.get("status"), _state.get("step_s"))
            except Exception:
                pass
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {e}"[:200]
        time.sleep(5)


def start():
    if _state["thread"]:
        return False
    th = threading.Thread(target=_run, daemon=True, name="v4swing")
    _state["thread"] = th
    th.start()
    return True


def report_meta(trades=None):
    """For the Research page: evidence labels, the backtest numbers, and the forward mean % per trade (same unit)."""
    out = {"label": LABEL, "status": "forward paper test (not promoted); promotion needs 40 forward trades (G5)",
           "backtest": BACKTEST, "rules": "close > SMA200, close < SMA5, RSI2 < 10 -> buy next open; sell next open after a close > SMA5",
           "slots": SLOTS, "slot_usd": SLOT_USD, "universe": list(SYMBOLS)}
    pct = [100.0 * float(t["realized"] or 0) / float((t.get("plan") or {}).get("notional") or 0)
           for t in trades or [] if (t.get("plan") or {}).get("notional")]
    if pct:
        out["forward_mean_pct"] = round(float(np.mean(pct)), 3)
        out["forward_trades"] = len(pct)
    return out


def status():
    day = core.now_et().date()
    return {"version": VERSION, "status": _state["status"], "last_error": _state["last_error"], "step_s": _state["step_s"],
            "switch": switch_on(), "plan": store.kv_get(_pkey(day)), "open": [p["id"] for p in S.positions(ledger=LEDGER, status="OPEN")],
            "label": LABEL}
