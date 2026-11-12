"""core_trend.py - the T47 trend core: PAPER (simulated fills on live Schwab quotes), SSO and QLD shares held across
sessions, each half switched in or out by its own 200-day trend rule, plus the T47 account view (trend core +
nbs_spy_ls + etf10_rsi2, minus margin interest). REGISTERED 2026-11-12, before any forward trade. Not promoted. Never
real money (there is no order path here).

Scope and approval: on 2026-11-12 Claude offered Nick three choices for a paper trend core (T47 50/50 SSO + QLD trend,
T44 SSO trend only, or neither); Nick answered "do whatever you think is best for my portfolio". Claude's call: T47,
logged per half so the SSO half also gives T44's core a forward record. PAPER ONLY. The core rule of CLAUDE.md
(isolated multi-day risk book, exempt from the 1.5%-per-3-sigma-day size rule, the account drawdown throttle and the
daily stop) is extended to this ledger, exactly as tested; the satellites keep all their own rules. core_spy keeps
running unchanged beside it. Real money would need CLAUDE.md step 5 and Nick asking for it in that conversation.

Evidence (labels: BACKTEST = historical simulation, PAPER = this ledger's simulated fills)
  Rule: Gayed & Bilello (2016), "Leverage for the Long Run" (2x index above its 200-day average, T-bills below), with
  T5 V2's band (in above 1.04 x SMA200, out below 0.97 x; chosen in-sample in T5). T44 = the SSO core (TradingVault
  Research/2026-11-11-t44-*), T46 = the QLD core (-12 t46-*), T47 = 50/50 (-12 t47-*). Trials counted: 69.
    T44 BACKTEST research 2003-2021 (in-sample band): 24.6% CAGR, worst -32.4%; sealed 2022-2025 (real SSO, run once):
      22.9% CAGR, worst -28.2%, vs T30b 20.6%, -26.3%.
    T47 BACKTEST research 2003-2021: SEEN (T46's information line) 25.7% CAGR, worst -36.1%; sealed 2022-2025 (real
      SSO and QLD, run once): 27.5% CAGR, worst -28.1%, vs T44 23.0% and T30b 20.6%. Lead mostly from 2023.
  All with the band (T12a) and rsi2 (T6 R2) sleeves on 6.5% margin, T30 engine.

Rules (frozen; any change ships as a new version and the forward count starts over)
  Account    the T47 account = $3,000 at START (the day of the first trend-core fill) + realized and open P/L, since
             START, of core_trend, nbs_spy_ls ($3,000 intraday) and etf10_rsi2 (3 x $1,000 overnight) - margin interest.
             core_spy's T30b account view is separate; both views count the same satellites (what-if accounts).
  Halves     "S": SSO (2x S&P 500) switched by SPY; "Q": QLD (2x Nasdaq-100) switched by QQQ.
  Signal     per half, on FINISHED daily bars only (the last one = the previous session), over the whole Schwab daily
             history (2 years): the state starts IN when SMA(200) first exists; IN -> OUT when a close < 0.97 x SMA200;
             OUT -> IN when a close > 1.04 x SMA200.
  Timing     decided from the previous session's close, traded near today's close: from 10 minutes before the close
             (15:50, or 12:50 on early-close days) until 2 minutes before. A signal at close t is held from close t+1,
             as in the backtest (state shifted 2 days). No fill by then -> MISSED, retried the next session.
  Target     each half = 0.5 x account equity while IN, 0 while OUT. Below Alpaca's $2,000 margin minimum the halves
             split (equity - the swing book's open notional), floored at 0 (no borrowing).
  Trades     IN with no position: buy the target at ask + $0.01 (v4store.share_buy), fractional shares (4 decimals).
             OUT with a position: sell it all at bid - $0.01. IN with a position: on the first session of each month,
             if |mark notional - target| > 5% of target, sell it and buy the new target at the same quote time.
  Exit       only the trend rule and the v4 kill switch. No stop, no target, no time stop.
  Margin     as core_spy (own log): each session after the close, debit = max(0, trend-core mark notional + swing open
             mark notional - equity); interest += debit x 6.5% x calendar days to the next session / 360.
  Safety     MARGIN WARNING when equity / overnight gross < 0.40, or when the maintenance need (50% of the SSO + QLD
             notional, 30% of the swing notional) is above 80% of equity (backtest high: 75%).
  Risk       v4risk book "tcore" (isolated, multi-day, 2 positions): the v4 kill switch and pauses; no daily loss stop
             (the core rule). Exits are never blocked.
  Switch     config/v4.json "core_trend": true/false. Off stops new buys and rebalances; trend exits still run.
Known deviations from the backtest: the S half's signal uses SPY's close instead of the S&P 500 index level (SPY drops
by its dividend on ex-dates; checked on SPY 2016-2026: a 500-bar window gave the same state as full history on all 756
days of the last 3 years); near-close quotes instead of official closes; halves rebalanced monthly (backtest daily);
no interest on idle cash (the backtest credited T-bills while OUT, about 4-5% a year in 2023-2025); dividends not
credited; satellites at fixed sizes (backtest scaled them with equity).
Promotion: 40 forward weeks of the account view next to core_spy's T30b view, SPY alone and the backtest's range.
"""
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
from core_spy import interest, is_session, needs_rebalance, next_session, prev_session, rebalance_day, size
from etf10_rsi2 import finished_daily

LEDGER, BOOK = "core_trend", "tcore"
VERSION = "2026-11-12.core-trend-1"
HALVES = {"S": {"ticker": "SSO", "signal": "SPY", "name": "2x S&P 500"},
          "Q": {"ticker": "QLD", "signal": "QQQ", "name": "2x Nasdaq-100"}}
WEIGHT = 0.5
SATELLITES = ("nbs_spy_ls", "etf10_rsi2")
SWING_LEDGER = "etf10_rsi2"
START_USD, MARGIN_RATE, MARGIN_MIN_EQUITY = 3000.0, 0.065, 2000.0
REBAL_BAND, WARN_RATIO, MAINT_WARN, MAINT_LEV, MAINT_ETF = 0.05, 0.40, 0.80, 0.50, 0.30
SMA_N, IN_ABOVE, OUT_BELOW = 200, 1.04, 0.97
PLAN_FROM, OPEN, CLOSE = "08:00", "09:30", "16:00"
DECIDE_MIN, LAST_MIN = 10, 2                       # trade from 10 to 2 minutes before the close
QUOTE_MAX_AGE_S = 20
MARK_EVERY_S = 60
KEY = "core_trend"
LABEL = ("PAPER (simulated fills); rules = T47 (50/50 SSO + QLD 200-day trend core + noise band + rsi2 sleeve on margin): "
         "BACKTEST sealed 2022-2025 passed (research window seen)")
BACKTEST = {"t47_2003_2021": {"label": "BACKTEST (research window, SEEN before T47 was registered)", "cagr_pct": 25.7,
                              "worst_drop_pct": -36.1},
            "t47_2022_2025": {"label": "BACKTEST (sealed, out-of-sample, run once)", "cagr_pct": 27.5, "worst_drop_pct": -28.1,
                              "t44_cagr_pct": 23.0, "t44_worst_drop_pct": -28.2, "t30b_cagr_pct": 20.6, "t30b_worst_drop_pct": -26.3},
            "t44_2022_2025": {"label": "BACKTEST (sealed, out-of-sample, run once): the SSO half alone as the core",
                              "cagr_pct": 22.9, "worst_drop_pct": -28.2}}
_state = {"status": "idle", "last_error": None, "thread": None, "stop": False, "step_s": None, "mark_t": None, "plan_try": None}
_lock = threading.RLock()


def fetch():
    import scanner
    return scanner._fetch


def switch_on():
    """config/v4.json "core_trend" (missing = off). Off stops new buys and rebalances; trend exits still run."""
    import retire
    return bool(retire.cfg().get("core_trend", False))


# ================================================================ pure rules (no network, no clock)
def trend_states(close):
    """1 (IN) / 0 (OUT) per bar, NaN until SMA(200) exists. Starts IN; IN -> OUT below 0.97 x SMA200, OUT -> IN above
    1.04 x SMA200. Identical to wrds_lab/backtest_t44.sso_core / backtest_t46.qld_core's state machine."""
    c = pd.Series(close, dtype=float)
    sma = c.rolling(SMA_N).mean()
    out, inv = [], True
    for p, m in zip(c.to_numpy(), sma.to_numpy()):
        if np.isnan(m) or np.isnan(p):
            out.append(np.nan)
            continue
        if inv and p < OUT_BELOW * m:
            inv = False
        elif not inv and p > IN_ABOVE * m:
            inv = True
        out.append(1.0 if inv else 0.0)
    return pd.Series(out, index=c.index), sma


def signal(daily, day):
    """The state from finished bars before `day`: dict(state, asof, close, sma200) or None (fewer than 200 closes)."""
    d = finished_daily(daily, day)
    if d is None or len(d) < SMA_N:
        return None
    st, sma = trend_states(d["Close"].astype(float))
    return {"state": int(st.iloc[-1]), "asof": str(d.index[-1].date()), "close": round(float(d["Close"].iloc[-1]), 4),
            "sma200": round(float(sma.iloc[-1]), 4), "in_above": round(IN_ABOVE * float(sma.iloc[-1]), 4),
            "out_below": round(OUT_BELOW * float(sma.iloc[-1]), 4)}


def base(equity, swing_notional):
    """The core's dollars: account equity; below the $2,000 margin minimum, equity minus the swing book (no borrowing)."""
    if equity >= MARGIN_MIN_EQUITY:
        return max(0.0, equity)
    return max(0.0, equity - swing_notional)


def targets(equity, swing_notional, states):
    """{half: target notional}: 0.5 x base while IN, 0 while OUT (or unknown)."""
    b = base(equity, swing_notional)
    return {h: round(WEIGHT * b, 2) if states.get(h) == 1 else 0.0 for h in HALVES}


def window(day, close_hm):
    """(first decision time, last fill time) for a session closing at close_hm."""
    c = C.at(day, close_hm)
    return c - timedelta(minutes=DECIDE_MIN), c - timedelta(minutes=LAST_MIN)


# ================================================================ the T47 account view
def start_day():
    return (store.kv_get(f"{KEY}:start") or {}).get("day")


def _mark_px(p):
    pl = p.get("plan") or {}
    return float(pl.get("last_mark") or p.get("entry_px") or 0.0)


def account(now=None, states=None):
    """Equity, P/L by ledger since START, margin interest, overnight gross, maintenance need and the half targets.
    Before START the account is the untouched $3,000."""
    since = start_day()
    accr = store.kv_get(f"{KEY}:interest") or {}
    paid = round(sum(float(v.get("interest") or 0) for v in accr.values()), 2)
    pnl, core_n, swing_n, by_half = {}, 0.0, 0.0, {h: 0.0 for h in HALVES}
    tick_half = {v["ticker"]: h for h, v in HALVES.items()}
    for led in (LEDGER,) + SATELLITES:
        tot = 0.0
        for p in S.positions(ledger=led):
            if since is None or str(p["date"]) < since or p["status"] == "VOID":
                continue
            if p["status"] == "CLOSED":
                tot += float(p["realized"] or 0.0)
            elif p["status"] == "OPEN":
                tot += float((p.get("plan") or {}).get("mtm") or 0.0)
                n = float(p["qty"] or 0) * _mark_px(p)
                if led == LEDGER:
                    core_n += n
                    if p["ticker"] in tick_half:
                        by_half[tick_half[p["ticker"]]] += n
                elif led == SWING_LEDGER:
                    swing_n += n
        pnl[led] = round(tot, 2)
    equity = round(START_USD + sum(pnl.values()) - paid, 2)
    gross = round(core_n + swing_n, 2)
    ratio = round(equity / gross, 3) if gross > 0 else None
    maint = round(MAINT_LEV * core_n + MAINT_ETF * swing_n, 2)
    maint_ratio = round(maint / equity, 3) if equity > 0 else None
    if states is None:
        states = {h: (v or {}).get("state") for h, v in ((store.kv_get(_pkey(str((now or core.now_et()).date()))) or {})
                                                          .get("signals") or {}).items()}
    return {"start": since, "start_usd": START_USD, "equity": equity, "pnl_by_ledger": pnl, "margin_interest": paid,
            "core_notional": round(core_n, 2), "notional_by_half": {h: round(v, 2) for h, v in by_half.items()},
            "swing_notional": round(swing_n, 2), "overnight_gross": gross, "debit": round(max(0.0, gross - equity), 2),
            "equity_to_gross": ratio, "maintenance_need": maint, "maintenance_to_equity": maint_ratio,
            "margin_warning": bool((ratio is not None and ratio < WARN_RATIO) or (maint_ratio is not None and maint_ratio > MAINT_WARN)),
            "targets": targets(equity, swing_n, states), "label": "PAPER (simulated fills), T47 account view"}


def accrue(day, now=None):
    """Margin interest for the night(s) after session `day`, once. Returns the record or None if already done."""
    k = str(day)
    accr = store.kv_get(f"{KEY}:interest") or {}
    if k in accr or start_day() is None or k < start_day():
        return None
    a = account(now, states={})
    days = (next_session(day) - day).days
    rec = {"debit": a["debit"], "days": days, "interest": interest(a["debit"], days), "equity": a["equity"],
           "gross": a["overnight_gross"], "maintenance_to_equity": a["maintenance_to_equity"],
           "at": (now or core.now_et()).isoformat(timespec="seconds")}
    accr[k] = rec
    store.kv_set(f"{KEY}:interest", accr)
    if rec["interest"] > 0:
        S.decide(f"{LEDGER}:interest:{k}", LEDGER, "SSO/QLD", "MARGIN INTEREST",
                 [f"debit ${rec['debit']:,.2f} x 6.5% x {days} day(s) / 360 = ${rec['interest']:.2f}"], rec, "account", VERSION)
    return rec


# ================================================================ the daily plan (signals from finished bars)
def _pkey(day):
    return f"{KEY}:plan:{day}"


def make_plan(day, now, final=False):
    """Both halves' states from the previous session's finished daily bar. Stored once per day (a restart reuses it).
    A signal whose history doesn't reach the previous session yet is retried; at `final` it is recorded NO DATA."""
    have = store.kv_get(_pkey(day))
    if have:
        return have
    f = fetch()
    want = str(prev_session(day))
    sig, stale = {}, []
    for h, v in HALVES.items():
        try:
            s = signal(f.daily(v["signal"]), day)
        except Exception as e:
            s = None
            _state["last_error"] = f"daily {v['signal']}: {type(e).__name__}"
        if s is None or s["asof"] != want:
            stale.append(v["signal"])
            continue
        sig[h] = s
    if stale and not final:
        _state["status"] = f"waiting for {want} daily bars: {', '.join(stale)}"
        return None
    for h in HALVES:
        if h not in sig:
            sig[h] = {"state": None, "asof": None, "why": f"no finished daily bar for {want}"}
    plan = {"day": str(day), "made": now.isoformat(timespec="seconds"), "signals": sig}
    store.kv_set(_pkey(day), plan)
    return plan


# ================================================================ near the close
def _equity_q(ticker, quotes):
    q = dict((quotes or {}).get(ticker) or {})
    if not q:
        return None
    if q.get("quote_time") is None and q.get("quote_ms"):
        q["quote_time"] = pd.Timestamp(q["quote_ms"], unit="ms", tz="UTC").tz_convert(core.ET)
    return v4exec.equity_quote(ticker, {ticker: q})


def _dkey(h, day):
    return f"{LEDGER}:{h}:{day}"


def _decide(h, day, decision, why, data=None):
    return S.decide(_dkey(h, day), LEDGER, HALVES[h]["ticker"], decision, [why] if why else [], data or {}, "entry", VERSION)


def _buy(day, h, tag, q, tgt, sig, t0):
    t = HALVES[h]["ticker"]
    fill = S.share_buy(q)
    qty, notional = size(tgt, fill)
    if qty <= 0:
        return None, f"size 0 (target ${tgt:,.2f} at {fill})"
    rec = {"id": f"{LEDGER}:{day}-{h}-{tag}", "ledger": LEDGER, "book": BOOK, "kind": "shares", "date": str(day), "ticker": t,
           "direction": "long", "side": "long", "qty": qty, "entry_px": fill, "entry_t": store.ts(),
           "signal_t": t0.isoformat(), "quote_t": str(q.get("quote_time")), "fees": 0.0, "risk_usd": None, "max_loss": None,
           "legs": [{"symbol": t, "label": f"{qty:g} sh", "action": "buy", "qty": qty}],
           "plan": {"label": LABEL, "status": "forward paper test (not promoted)", "half": h, "target": tgt,
                    "notional": notional, "bid": q["bid"], "ask": q["ask"], "last_mark": fill, "mtm": 0.0, "signal": sig,
                    "exit_rule": (f"held while {HALVES[h]['signal']} stays above 0.97 x its 200-day average (sold near the "
                                  "close after a finished close below it); rebalanced monthly; no stop"),
                    "risk_rule": "core rule: isolated tcore book, exempt from the 1.5% multi-day size rule and the throttle (T47)",
                    "day_base": 0.0, "day_base_day": str(day)},
           "version": VERSION, "exec_model": "shares1"}
    return S.open_position(rec, f"core_trend {h} {tag} near the close (paper, simulated fill)")


def _half(day, now, h, plan, quotes, on, t0, late):
    """One half's decision for the session (idempotent). Returns True once decided."""
    if S.decided(_dkey(h, day)):
        return True
    t = HALVES[h]["ticker"]
    opens = [p for p in S.positions(ledger=LEDGER, status="OPEN") if p["ticker"] == t]
    if any((p.get("plan") or {}).get("pending_exit") for p in opens):
        return False                                           # a pending sale: manage() retries it first
    sig = plan["signals"].get(h) or {}
    st = sig.get("state")
    if st is None:
        _decide(h, day, "NO DATA", sig.get("why") or "no signal", {"signal": sig})
        return True
    q = _equity_q(t, quotes)
    ok, qwhy = C.quote_after(q, t0, QUOTE_MAX_AGE_S)
    if st == 0:
        if not opens:
            _decide(h, day, "OUT", f"{HALVES[h]['signal']} trend OUT (close {sig['close']} vs SMA200 {sig['sma200']}): cash",
                    {"signal": sig})
            return True
        if not ok:
            if late:
                _decide(h, day, "MISSED", f"trend exit due but no fresh {t} quote by the last fill time ({qwhy}); retried next session",
                        {"signal": sig})
                return True
            return False
        p = opens[0]
        r = v4exec.close_now(p, f"trend OUT: {HALVES[h]['signal']} close {sig['close']} < 0.97 x SMA200 ({sig['out_below']})", {t: q})
        if r is None:
            _decide(h, day, "PENDING", "trend exit pending a valid quote", {"signal": sig, "position": p["id"]})
        else:
            _decide(h, day, "EXIT", f"sold {t}: {HALVES[h]['signal']} trend OUT", {"signal": sig, "sold": p["id"], "realized": r})
        return True
    a = account(now, states={k: (plan["signals"].get(k) or {}).get("state") for k in HALVES})
    tgt = a["targets"][h]
    if not opens:
        if not on:
            _decide(h, day, "SWITCH OFF", 'config/v4.json "core_trend" is off: no new buy', {"signal": sig})
            return True
        if not ok:
            if late:
                _decide(h, day, "MISSED", f"no fresh {t} quote by the last fill time ({qwhy}); retried next session", {"signal": sig})
                return True
            return False
        blk = v4risk.admit(LEDGER, BOOK, t, "long", now)
        if blk:
            _decide(h, day, "BLOCKED-RISK", blk, {"signal": sig})
            return True
        if start_day() is None:
            store.kv_set(f"{KEY}:start", {"day": str(day), "at": now.isoformat(timespec="seconds")})
            a = account(now, states={k: (plan["signals"].get(k) or {}).get("state") for k in HALVES})
            tgt = a["targets"][h]
        got, why = _buy(day, h, "buy", q, tgt, sig, t0)
        if not got:
            _decide(h, day, "SKIP", why, {"signal": sig})
            return True
        _decide(h, day, "ORDER", f"trend IN: ${tgt:,.2f} of {t} (half of account equity ${a['equity']:,.2f})",
                {"signal": sig, "position": got, "target": tgt, "equity": a["equity"]})
        return True
    p = opens[0]
    if not rebalance_day(day):
        _decide(h, day, "HOLD", "trend IN, holding (rebalance on the first session of the month)", {"signal": sig, "position": p["id"]})
        return True
    if not on:
        _decide(h, day, "SWITCH OFF", 'config/v4.json "core_trend" is off: no rebalance (the open half is kept)', {"signal": sig})
        return True
    if not ok:
        if late:
            _decide(h, day, "MISSED", f"no fresh {t} quote for the monthly rebalance ({qwhy})", {"signal": sig})
            return True
        return False
    mark_n = float(p["qty"] or 0) * float(q["bid"])
    if not needs_rebalance(mark_n, tgt):
        _decide(h, day, "HOLD", f"rebalance check: ${mark_n:,.2f} vs target ${tgt:,.2f} (within {REBAL_BAND:.0%})",
                {"signal": sig, "position": p["id"], "mark_notional": round(mark_n, 2), "target": tgt})
        return True
    r = v4exec.close_now(p, f"monthly rebalance: ${mark_n:,.2f} vs target ${tgt:,.2f}", {t: q})
    if r is None:
        _decide(h, day, "PENDING", "rebalance sale pending a valid quote; no new buy until it fills", {"signal": sig})
        return True
    a = account(now, states={k: (plan["signals"].get(k) or {}).get("state") for k in HALVES})
    tgt = a["targets"][h]
    got, why = _buy(day, h, "rebal", q, tgt, sig, t0)
    _decide(h, day, "REBALANCE" if got else "SKIP", why if not got else f"rebalanced {t} to ${tgt:,.2f} (half of ${a['equity']:,.2f})",
            {"signal": sig, "sold": p["id"], "position": got, "target": tgt})
    return True


def execute(day, now, quotes, plan, close_hm=CLOSE):
    """Both halves, once per session, inside the near-close window."""
    t0, last = window(day, close_hm)
    if now < t0:
        return
    late = now >= last
    on = switch_on()
    with _lock:
        for h in HALVES:
            _half(day, now, h, plan, quotes, on, t0, late)


# ================================================================ marks
def manage(now, quotes=None):
    """Retry a pending sale, mark each half to the bid. Never closes a position for being from an earlier session
    (no v4exec.overnight here: holding is the rule)."""
    day = str(now.date())
    for p in S.positions(ledger=LEDGER, status="OPEN"):
        q = _equity_q(p["ticker"], quotes) if quotes else None
        pl = p.get("plan") or {}
        if pl.get("pending_exit"):
            if q and q.get("executable") and q.get("bid") is not None:
                v4exec.retry_pending(p, {p["ticker"]: q})
            continue
        if not (q and q.get("executable") and q.get("bid") is not None):
            continue
        if pl.get("day_base_day") != day:
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
    hm = now.strftime("%H:%M")
    if start_day() and is_session(day) and hm < OPEN:          # catch up a missed evening accrual (morning marks)
        prev = prev_session(day)
        if str(prev) >= start_day():
            accrue(prev, now)
    if sess.get("holiday") or not is_session(day):
        _state["status"] = "market closed"
        return
    close = sess.get("close", CLOSE)
    if hm >= close:
        accrue(day, now)
        _state["status"] = f"closed; margin interest recorded for {day}"
        return
    f = fetch()
    if not f.ready():
        _state["status"] = "waiting for Schwab (no decisions on delayed data)"
        return
    first, last = window(day, close)
    plan = store.kv_get(_pkey(day))
    if not plan and hm >= PLAN_FROM:
        lt = _state.get("plan_try")
        if hm >= first.strftime("%H:%M") or lt is None or lt > now or (now - lt).total_seconds() >= 300:
            _state["plan_try"] = now
            plan = make_plan(day, now, final=now >= last)
    if hm < OPEN:
        _state["status"] = "before the open" + ("" if plan else " (plan pending)")
        return
    import schwab
    opens = S.positions(ledger=LEDGER, status="OPEN")
    in_window = now >= first
    undecided = plan is not None and in_window and not all(S.decided(_dkey(h, day)) for h in HALVES)
    pending = any((p.get("plan") or {}).get("pending_exit") for p in opens)
    due_mark = _state["mark_t"] is None or (now - _state["mark_t"]).total_seconds() >= MARK_EVERY_S or _state["mark_t"] > now
    quotes = {}
    if undecided or pending or (due_mark and opens):
        _state["mark_t"] = now
        with schwab.priority("risk" if opens else "normal"):
            try:
                quotes, _ = f.quotes([v["ticker"] for v in HALVES.values()])
            except Exception as e:
                _state["last_error"] = f"quotes: {type(e).__name__}"
    with schwab.priority("risk"):
        try:
            manage(now, quotes)
        except Exception as e:
            _state["last_error"] = f"manage: {type(e).__name__}: {e}"[:200]
    if plan is not None:
        try:
            execute(day, now, quotes, plan, close)
        except Exception as e:
            _state["last_error"] = f"execute: {type(e).__name__}: {e}"[:200]
    n = len(S.positions(ledger=LEDGER, status="OPEN"))
    _state["status"] = f"{n} open" + (", deciding near the close" if undecided else "") + ("" if plan else ", plan pending")
    _state["step_s"] = round(time.time() - t0, 2)


def _run():
    while not _state["stop"]:
        try:
            step()
            try:
                import health
                health.beat("v4tcore", True, _state.get("status"), _state.get("step_s"))
            except Exception:
                pass
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {e}"[:200]
        time.sleep(5)


def start():
    if _state["thread"]:
        return False
    th = threading.Thread(target=_run, daemon=True, name="v4tcore")
    _state["thread"] = th
    th.start()
    return True


def report_meta(trades=None):
    """For the Research page: evidence label, the T44/T47 backtest numbers and the live account view."""
    plan = store.kv_get(_pkey(str(core.now_et().date()))) or {}
    return {"label": LABEL, "status": "forward paper test (not promoted); compare the account view with core_spy's T30b view and SPY",
            "backtest": BACKTEST, "rules": ("half SSO while SPY is in its 200-day uptrend, half QLD while QQQ is (in above 1.04 x "
                                            "SMA200, out below 0.97 x), traded near the close; monthly rebalance; T-bills/cash when out"),
            "signals": plan.get("signals"), "account": account()}


def status():
    plan = store.kv_get(_pkey(str(core.now_et().date()))) or {}
    return {"version": VERSION, "status": _state["status"], "last_error": _state["last_error"], "step_s": _state["step_s"],
            "switch": switch_on(), "signals": plan.get("signals"), "account": account(),
            "open": [p["id"] for p in S.positions(ledger=LEDGER, status="OPEN")],
            "interest_log": store.kv_get(f"{KEY}:interest") or {}, "label": LABEL}
