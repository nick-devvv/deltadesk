"""core_spy.py - the T30b SPY core: PAPER (simulated fills on live Schwab quotes), SPY shares held across sessions,
plus the T30b account view (core + nbs_spy_ls + etf10_rsi2, minus margin interest). REGISTERED 2026-11-11, before any
forward trade. Not promoted. Never real money (there is no order path here).

Scope and approval: on 2026-11-11 Nick chose "option 1" ("do 1 first": hold the market as the core, the desk's tested
strategies on top, using margin), and on the risk rule said "u do whats best". Claude's call, logged in TradingVault
Rules/risk-framework-proposal.md ("Core rule"): PAPER ONLY; the core lives in its own isolated multi-day risk book
("core", v4risk) and is exempt from the multi-day 1.5%-per-3-sigma-day size rule and from the account drawdown throttle,
exactly as tested in T30; the satellites keep all their own rules. Real money would need CLAUDE.md step 5 and Nick asking
for it explicitly in that conversation.

Evidence (labels: BACKTEST = historical simulation, PAPER = this ledger's simulated fills)
  T30 (TradingVault Research/2026-11-11-t30-prereg, -result): portfolio arithmetic on streams that had all been tested
  and seen before (SPY, T12a noise band, T6 R2 rsi2 on 10 ETFs), so IN-SAMPLE by construction; the forward paper test
  is the real check. 3 variants counted as trials (49 WRDS trials in total).
    BACKTEST 2003-09-10..2021-12-31: T30b CAGR 18.2% vs SPY alone 10.9%; worst drop -37.6% vs -55.2%.
    BACKTEST 2022-01-03..2025-12-31: T30b CAGR 20.6% vs SPY alone 11.1%; worst drop -26.3% vs -24.5%.
    Both with Alpaca's 6.5% margin interest on the overnight debit; still above SPY with 13% margin and 2x costs.

Rules (frozen; any change ships as a new version and the forward count starts over)
  Account    the T30b account = $3,000 at START (the day of the first core fill) + realized and open P/L, since START, of
             core_spy, nbs_spy_ls (noise band, $3,000 intraday) and etf10_rsi2 (3 x $1,000 overnight) - margin interest.
             Positions dated before START are not part of the account.
  Target     core notional = account equity (1x). Below Alpaca's $2,000 margin minimum: equity minus the swing book's open
             notional (no borrowing), floored at 0.
  Entry      the first session open with no core position: buy SPY at the first executable quote dated at least the
             decision latency after 09:30:00 ET and under 20 s old, at ask + $0.01 (v4store.share_buy), fractional shares
             (4 decimals). No fill by 09:40 -> MISSED (retried the next session).
  Rebalance  the first session of each calendar month, at the open: if |position mark notional - target| > 5% of target,
             sell the whole position at bid - $0.01 and buy the new target at ask + $0.01 at the same open.
  Exit       none: no stop, no target, no time stop. The v4 kill switch closes it like every v4 position.
  Margin     each session after the close: debit = max(0, core mark notional + swing open mark notional - equity);
             interest += debit x 6.5% x calendar days to the next session / 360 (Alpaca non-elite rate, Sep 2026).
             Recorded once per session; a missed evening is caught up the next morning with the morning's marks.
  Safety     the view flags MARGIN WARNING when equity / overnight gross < 0.40 (Alpaca maintenance is about 25-30%;
             the backtest's lowest was 0.50).
  Risk       v4risk book "core" (isolated, multi-day, 1 position): the v4 kill switch and pauses; no daily loss stop
             (the core rule). Exits are never blocked.
  Switch     config/v4.json "core_spy": true/false. Off stops the first entry and rebalances; an open core is kept.
Known deviations from the T30b backtest: the satellites keep their fixed sizes ($3,000 and 3 x $1,000; the backtest
scaled them with equity daily); the core is rebalanced monthly (the backtest daily); dividends are not credited to paper
P/L (SPY yields about 1.2% a year, so the paper core understates T30b by about that); Schwab quotes instead of CRSP.
Promotion: 40 forward weeks of the account view next to SPY alone and the backtest's range (CLAUDE.md step 5 spirit).
"""
import math
import threading
import time
from datetime import timedelta

import pandas as pd

import core
import store
import v4common as C
import v4exec
import v4risk
import v4store as S

LEDGER, BOOK = "core_spy", "core"
VERSION = "2026-11-11.core-spy-1"
TICKER = "SPY"
SATELLITES = ("nbs_spy_ls", "etf10_rsi2")
SWING_LEDGER = "etf10_rsi2"
START_USD, MARGIN_RATE, MARGIN_MIN_EQUITY = 3000.0, 0.065, 2000.0
REBAL_BAND, WARN_RATIO = 0.05, 0.40
OPEN, FILL_LATE = "09:30", "09:40"
QUOTE_MAX_AGE_S = 20
MARK_EVERY_S = 60
LABEL = ("PAPER (simulated fills); rules = T30b (SPY core 1x + noise band + rsi2 sleeve on margin), BACKTEST in-sample "
         "portfolio arithmetic on already-tested streams")
BACKTEST = {"2003_2021": {"label": "BACKTEST (in-sample portfolio arithmetic)", "cagr_pct": 18.2, "worst_drop_pct": -37.6,
                          "spy_cagr_pct": 10.9, "spy_worst_drop_pct": -55.2},
            "2022_2025": {"label": "BACKTEST (in-sample portfolio arithmetic)", "cagr_pct": 20.6, "worst_drop_pct": -26.3,
                          "spy_cagr_pct": 11.1, "spy_worst_drop_pct": -24.5}}
_state = {"status": "idle", "last_error": None, "thread": None, "stop": False, "step_s": None, "mark_t": None}


def fetch():
    import scanner
    return scanner._fetch


def switch_on():
    """config/v4.json "core_spy" (missing = off). Off stops the first entry and rebalances; an open core is kept."""
    import retire
    return bool(retire.cfg().get("core_spy", False))


# ================================================================ calendar and pure rules
def is_session(d):
    return d.weekday() < 5 and d.isoformat() not in core.HOLIDAYS


def prev_session(d):
    x = d - timedelta(days=1)
    while not is_session(x):
        x -= timedelta(days=1)
    return x


def next_session(d):
    x = d + timedelta(days=1)
    while not is_session(x):
        x += timedelta(days=1)
    return x


def rebalance_day(d):
    """The first session of its calendar month."""
    return is_session(d) and prev_session(d).month != d.month


def target(equity, swing_notional):
    """Core notional: 1x equity; below the $2,000 margin minimum, equity minus the swing book (no borrowing)."""
    if equity >= MARGIN_MIN_EQUITY:
        return round(max(0.0, equity), 2)
    return round(max(0.0, equity - swing_notional), 2)


def needs_rebalance(mark_notional, tgt):
    if tgt <= 0:
        return mark_notional > 0
    return abs(mark_notional - tgt) / tgt > REBAL_BAND


def interest(debit, days):
    """The broker's margin interest for `days` calendar days on an overnight debit (rate / 360 per day)."""
    return round(max(0.0, debit) * MARGIN_RATE * days / 360.0, 4)


def size(notional, fill):
    """(qty, notional): fractional shares (4 decimals) for a dollar target."""
    if not fill or fill <= 0 or notional <= 0:
        return 0.0, 0.0
    q = math.floor(notional / fill * 10_000) / 10_000
    return q, round(q * fill, 2)


# ================================================================ the T30b account view
def start_day():
    return (store.kv_get("core:start") or {}).get("day")


def _mark_px(p):
    pl = p.get("plan") or {}
    return float(pl.get("last_mark") or p.get("entry_px") or 0.0)


def account(now=None):
    """Equity, P/L by ledger since START, margin interest, overnight gross and the equity/gross ratio. Before START the
    account is the untouched $3,000."""
    since = start_day()
    accr = store.kv_get("core:interest") or {}
    paid = round(sum(float(v.get("interest") or 0) for v in accr.values()), 2)
    pnl, core_n, swing_n = {}, 0.0, 0.0
    for led in (LEDGER,) + SATELLITES:
        tot = 0.0
        for p in S.positions(ledger=led):
            if since is None or str(p["date"]) < since or p["status"] == "VOID":
                continue
            if p["status"] == "CLOSED":
                tot += float(p["realized"] or 0.0)
            elif p["status"] == "OPEN":
                tot += float((p.get("plan") or {}).get("mtm") or 0.0)
                if led == LEDGER:
                    core_n += float(p["qty"] or 0) * _mark_px(p)
                elif led == SWING_LEDGER:
                    swing_n += float(p["qty"] or 0) * _mark_px(p)
        pnl[led] = round(tot, 2)
    equity = round(START_USD + sum(pnl.values()) - paid, 2)
    gross = round(core_n + swing_n, 2)
    ratio = round(equity / gross, 3) if gross > 0 else None
    return {"start": since, "start_usd": START_USD, "equity": equity, "pnl_by_ledger": pnl, "margin_interest": paid,
            "core_notional": round(core_n, 2), "swing_notional": round(swing_n, 2), "overnight_gross": gross,
            "debit": round(max(0.0, gross - equity), 2), "equity_to_gross": ratio,
            "margin_warning": bool(ratio is not None and ratio < WARN_RATIO),
            "target": target(equity, swing_n), "label": "PAPER (simulated fills), T30b account view"}


def accrue(day, now=None):
    """Margin interest for the night(s) after session `day`, once. Returns the record or None if already done."""
    k = str(day)
    accr = store.kv_get("core:interest") or {}
    if k in accr or start_day() is None or k < start_day():
        return None
    a = account(now)
    days = (next_session(day) - day).days
    rec = {"debit": a["debit"], "days": days, "interest": interest(a["debit"], days), "equity": a["equity"],
           "gross": a["overnight_gross"], "at": (now or core.now_et()).isoformat(timespec="seconds")}
    accr[k] = rec
    store.kv_set("core:interest", accr)
    if rec["interest"] > 0:
        S.decide(f"{LEDGER}:interest:{k}", LEDGER, TICKER, "MARGIN INTEREST",
                 [f"debit ${rec['debit']:,.2f} x 6.5% x {days} day(s) / 360 = ${rec['interest']:.2f}"], rec, "account", VERSION)
    return rec


# ================================================================ at the open
def _equity_q(quotes):
    q = dict((quotes or {}).get(TICKER) or {})
    if not q:
        return None
    if q.get("quote_time") is None and q.get("quote_ms"):
        q["quote_time"] = pd.Timestamp(q["quote_ms"], unit="ms", tz="UTC").tz_convert(core.ET)
    return v4exec.equity_quote(TICKER, {TICKER: q})


def _decide(day, decision, why, data=None):
    return S.decide(f"{LEDGER}:open:{day}", LEDGER, TICKER, decision, [why] if why else [], data or {}, "entry", VERSION)


def _buy(day, tag, q, tgt, sigma=None):
    fill = S.share_buy(q)
    qty, notional = size(tgt, fill)
    if qty <= 0:
        return None, f"size 0 (target ${tgt:,.2f} at {fill})"
    rec = {"id": f"{LEDGER}:{day}-{tag}", "ledger": LEDGER, "book": BOOK, "kind": "shares", "date": str(day), "ticker": TICKER,
           "direction": "long", "side": "long", "qty": qty, "entry_px": fill, "entry_t": store.ts(),
           "signal_t": C.at(day, OPEN).isoformat(), "quote_t": str(q.get("quote_time")), "fees": 0.0,
           "risk_usd": None, "max_loss": None,
           "legs": [{"symbol": TICKER, "label": f"{qty:g} sh", "action": "buy", "qty": qty}],
           "plan": {"label": LABEL, "status": "forward paper test (not promoted)", "target": tgt, "notional": notional,
                    "bid": q["bid"], "ask": q["ask"], "last_mark": fill, "mtm": 0.0,
                    "exit_rule": "held (no stop); rebalanced to the T30b account equity on the first session of each month",
                    "risk_rule": "core rule: isolated core book, exempt from the 1.5% multi-day size rule and the throttle (T30)",
                    "day_base": 0.0, "day_base_day": str(day)},
           "version": VERSION, "exec_model": "shares1"}
    return S.open_position(rec, f"core_spy {tag} at the open (paper, simulated fill)")


def execute(day, now, quotes):
    """Once per session: the first entry, or the monthly rebalance check. Idempotent (one decision per day)."""
    if S.decided(f"{LEDGER}:open:{day}"):
        return
    hm = now.strftime("%H:%M")
    late = hm >= FILL_LATE
    opens = S.positions(ledger=LEDGER, status="OPEN")
    if any((p.get("plan") or {}).get("pending_exit") for p in opens):
        return                                                # a pending sale: manage() retries it first
    on = switch_on()
    q = _equity_q(quotes)
    ok, qwhy = C.quote_after(q, C.at(day, OPEN), QUOTE_MAX_AGE_S)
    if not opens:
        if not on:
            _decide(day, "SWITCH OFF", 'config/v4.json "core_spy" is off: no core entry')
            return
        if not ok:
            if late:
                _decide(day, "MISSED", f"no fresh quote after the open by {FILL_LATE} ({qwhy}); retried next session")
            return
        blk = v4risk.admit(LEDGER, BOOK, TICKER, "long", now)
        if blk:
            _decide(day, "BLOCKED-RISK", blk)
            return
        if start_day() is None:
            store.kv_set("core:start", {"day": str(day), "at": now.isoformat(timespec="seconds")})
        a = account(now)
        got, why = _buy(day, "buy", q, a["target"])
        if not got:
            _decide(day, "SKIP", why)
            return
        _decide(day, "ORDER", f"core entry: ${a['target']:,.2f} of SPY (account equity ${a['equity']:,.2f})",
                {"position": got, "target": a["target"], "equity": a["equity"]})
        return
    p = opens[0]
    if not rebalance_day(day):
        _decide(day, "HOLD", "not the first session of the month (rebalance monthly)", {"position": p["id"]})
        return
    if not on:
        _decide(day, "SWITCH OFF", 'config/v4.json "core_spy" is off: no rebalance (the open core is kept)')
        return
    if not ok:
        if late:
            _decide(day, "MISSED", f"no fresh quote for the monthly rebalance by {FILL_LATE} ({qwhy})")
        return
    a = account(now)
    mark_n = float(p["qty"] or 0) * float(q["bid"])
    if not needs_rebalance(mark_n, a["target"]):
        _decide(day, "HOLD", f"rebalance check: ${mark_n:,.2f} vs target ${a['target']:,.2f} (within {REBAL_BAND:.0%})",
                {"position": p["id"], "mark_notional": round(mark_n, 2), "target": a["target"]})
        return
    r = v4exec.close_now(p, f"monthly rebalance: ${mark_n:,.2f} vs target ${a['target']:,.2f}", {TICKER: q})
    if r is None:
        _decide(day, "PENDING", "rebalance sale pending a valid quote; no new core until it fills")
        return
    a = account(now)                                          # the sale is realized; equity is unchanged by it
    got, why = _buy(day, "rebal", q, a["target"])
    _decide(day, "REBALANCE" if got else "SKIP", why if not got else
            f"rebalanced to ${a['target']:,.2f} (account equity ${a['equity']:,.2f})",
            {"sold": p["id"], "position": got, "target": a["target"]})


# ================================================================ marks
def manage(now, quotes=None):
    """Retry a pending sale, mark the core to the bid. Never closes it for being from an earlier session (no
    v4exec.overnight here: holding is the rule)."""
    day = str(now.date())
    for p in S.positions(ledger=LEDGER, status="OPEN"):
        q = _equity_q(quotes) if quotes else None
        pl = p.get("plan") or {}
        if pl.get("pending_exit"):
            if q and C.quote_after(q, C.at(now.date(), OPEN), QUOTE_MAX_AGE_S)[0]:
                v4exec.retry_pending(p, {TICKER: q})
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
    if start_day() and is_session(day) and hm < OPEN:         # catch up a missed evening accrual (morning marks)
        prev = prev_session(day)
        if str(prev) >= start_day():
            accrue(prev, now)
    if sess.get("holiday"):
        _state["status"] = "market closed"
        return
    close = sess.get("close", "16:00")
    if hm >= close:
        accrue(day, now)
        _state["status"] = f"closed; margin interest recorded for {day}"
        return
    f = fetch()
    if not f.ready():
        _state["status"] = "waiting for Schwab (no decisions on delayed data)"
        return
    if hm < OPEN:
        _state["status"] = "before the open"
        return
    import schwab
    opens = S.positions(ledger=LEDGER, status="OPEN")
    at_open = not S.decided(f"{LEDGER}:open:{day}") or any((p.get("plan") or {}).get("pending_exit") for p in opens)
    due_mark = _state["mark_t"] is None or (now - _state["mark_t"]).total_seconds() >= MARK_EVERY_S or _state["mark_t"] > now
    quotes = {}
    if at_open or due_mark:
        _state["mark_t"] = now
        with schwab.priority("risk" if opens else "normal"):
            try:
                quotes, _ = f.quotes([TICKER])
            except Exception as e:
                _state["last_error"] = f"quotes: {type(e).__name__}"
    with schwab.priority("risk"):
        try:
            manage(now, quotes)
        except Exception as e:
            _state["last_error"] = f"manage: {type(e).__name__}: {e}"[:200]
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
                health.beat("v4core", True, _state.get("status"), _state.get("step_s"))
            except Exception:
                pass
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {e}"[:200]
        time.sleep(5)


def start():
    if _state["thread"]:
        return False
    th = threading.Thread(target=_run, daemon=True, name="v4core")
    _state["thread"] = th
    th.start()
    return True


def report_meta(trades=None):
    """For the Research page: evidence label, the T30 backtest numbers and the live account view."""
    return {"label": LABEL, "status": "forward paper test (not promoted); compare the account view with SPY alone",
            "backtest": BACKTEST, "rules": "hold SPY = T30b account equity; rebalance on the first session of each month if off by > 5%",
            "account": account()}


def status():
    return {"version": VERSION, "status": _state["status"], "last_error": _state["last_error"], "step_s": _state["step_s"],
            "switch": switch_on(), "account": account(), "open": [p["id"] for p in S.positions(ledger=LEDGER, status="OPEN")],
            "interest_log": store.kv_get("core:interest") or {}, "label": LABEL}
