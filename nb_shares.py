"""nb_shares.py - the noise band on SPY SHARES, intraday, flat at the close: PAPER (simulated fills on live Schwab data).
REGISTERED 2026-11-10 before any forward trade. Not promoted. No order path. Two ledgers, one signal:
  nbs_spy_ls    T12a  long and short
  nbs_spy_long  T12b  long only (what a $3k cash account can do in shares)
The `noise` reference ledger (noiseband.py, options) is NOT changed and not imported.

Source and evidence (labels: BACKTEST = historical simulation on WRDS TAQ ticks; PAPER = this ledger)
  Zarattini, Aziz & Barbon (2024), "Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)",
  base rules, unlevered. Pre-registered as T12 (TradingVault Research/2026-11-10-t12-prereg, approved by Nick 2026-11-10,
  rules locked before any data). Fills at the real bid/ask of the first quote at/after check + 1 s, + $0.0035/share/side.
    BACKTEST research 2003-09-10..2021 (TAQ): T12a +1.76 bp/day after costs (90% CI +0.78 to +2.80), Sharpe 0.60,
      4,452 trades; T12b +0.98 bp/day (CI +0.39 to +1.56), Sharpe 0.55. Both pass all 4 pre-registered checks.
    BACKTEST sealed 2022-2025 (run once, criterion fixed before download): T12a +2.18 bp/day (CI +0.40 to +4.14),
      Sharpe 0.80; T12b +1.10 bp/day (CI -0.01 to +2.29), Sharpe 0.62. Both PASS.
    Caveats: half the research edge is 2008; 2012-2021 and 2024-2025 about flat (a crisis/trend strategy). Deflated
    Sharpe probability 0.75 / 0.68 at 21 WRDS trials. Desk blend with etf10_rsi2 (equal risk): 0.96 research, 1.04 sealed.

Rules (frozen; a change ships as a new ledger version)
  Band at check t (10:00, 10:30, ..., 15:30 ET):
    sigma(t) = average over the prior 14 full sessions (>= 10 needed) of |close(t) / open - 1| (half days skipped)
    upper = max(open, prior close) x (1 + sigma(t));  lower = min(open, prior close) x (1 - sigma(t))
    open = today's 09:30 bar open; prior close = the previous session's daily close minus today's dividend on an
    ex-dividend day (Schwab fundamentals; if unavailable, unadjusted and labeled).
  Signal price = close of the FINISHED 1-minute bar ending at t; VWAP = session VWAP of finished bars (HLC3 x volume).
  At each check, in order: a long exits if price < max(upper, VWAP); a short exits if price > min(lower, VWAP); then,
  if flat, price > upper -> buy; price < lower -> short (nbs_spy_ls only). Flat at 15:59. One position per ledger.
  Fills: the first fresh quote dated after the check (+ latency), buy at the ask, sell at the bid, + $0.0035/share/side
  (the backtest's cost model; execution model "nbspy1"). The bar is read from 10 s after the check. An entry with no
  fresh quote within 180 s is MISSED; exits are never dropped. A check whose bar isn't available within 120 s, or that
  passed while the desk was down, is recorded and
  skipped (no catch-up trading). Early-close days are skipped, as in the backtest.
  Size: $3,000 notional (1x Nick's account), fractional shares to 4 decimals.
  Risk: v4risk book "trend" (isolated), kill switch and pauses, the risk framework's -$90 daily stop on new entries.
  Switch: config/v4.json "nb_shares" (off stops new entries; exits still run).
Known deviations from the backtest: 1-minute bar closes instead of the NBBO mid at the exact second; bar VWAP instead of
trade VWAP; the 15:59 flat uses the first quote after 15:59:00 instead of the last before 15:59:59.
Promotion (CLAUDE.md step 5): 40 forward paper trades per ledger whose fills match the backtest's cost model.
"""
import math
import threading
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import core
import indicators as I
import store
import v4common as C
import v4exec
import v4risk
import v4store as S

LEDGERS = {"nbs_spy_ls": {"short": True, "test": "T12a"}, "nbs_spy_long": {"short": False, "test": "T12b"}}
BOOK, TICKER = "trend", "SPY"
VERSION = "2026-11-10.nbs-1"
CHECKS = [f"{10 + (30 * k) // 60:02d}:{(30 * k) % 60:02d}" for k in range(12)]      # 10:00 .. 15:30
FLAT, CLOSE, PREP_FROM = "15:59", "16:00", "08:00"
NOTIONAL, COMM = 3000.0, 0.0035
LOOKBACK, MIN_SESSIONS = 14, 10
BAR_WAIT_S, CHECK_GIVEUP_S, FILL_WINDOW_S, QUOTE_MAX_AGE_S, MARK_EVERY_S = 10, 120, 180, 20, 60
EXEC = "nbspy1"
LABEL = "PAPER (simulated fills); rules = T12, BACKTEST research 2003-2021 pass + sealed 2022-2025 pass (out-of-sample)"
BACKTEST = {"research_2003_2021": {"label": "BACKTEST (research window, WRDS TAQ)",
                                   "T12a": {"mean_bp_day": 1.76, "ci90_bp": [0.78, 2.80], "sharpe": 0.60, "trades": 4452},
                                   "T12b": {"mean_bp_day": 0.98, "ci90_bp": [0.39, 1.56], "sharpe": 0.55, "trades": 2244}},
            "sealed_2022_2025": {"label": "BACKTEST (sealed, out-of-sample, run once)",
                                 "T12a": {"mean_bp_day": 2.18, "ci90_bp": [0.40, 4.14], "sharpe": 0.80, "trades": 923},
                                 "T12b": {"mean_bp_day": 1.10, "ci90_bp": [-0.01, 2.29], "sharpe": 0.62, "trades": 472}}}
_state = {"status": "idle", "last_error": None, "thread": None, "stop": False, "step_s": None, "mark_t": None}


def fetch():
    import scanner
    return scanner._fetch


def switch_on():
    import retire
    return bool(retire.cfg().get("nb_shares", False))


# ================================================================ pure rules
def check_minute(hhmm):
    """Minutes after 09:30 at the END of the bar that closes at hhmm (10:00 -> 30): the sigma_profile index."""
    h, m = int(hhmm[:2]), int(hhmm[3:])
    return h * 60 + m - 570


def profile(m1_hist, day):
    """{check 'HH:MM': sigma} = mean |close(bar ending at the check) / 09:30 open - 1| over the prior 14 FULL sessions
    (>= 300 regular-hours bars; half days are skipped and the window reaches further back, as in the backtest, which
    used the prior 14 valid days). (None, n) if fewer than 10 full sessions."""
    m = _et(m1_hist)
    if m is None:
        return None, 0
    r = m.between_time("09:30", "15:59")
    full = []
    for d in sorted({x for x in r.index.date if x < day}, reverse=True):
        g = r[r.index.date == d]
        if len(g) >= 300:
            full.append((d, g))
        if len(full) == LOOKBACK:
            break
    if len(full) < MIN_SESSIONS:
        return None, len(full)
    out = {}
    for c in CHECKS:
        vals = []
        for d, g in full:
            t = pd.Timestamp(f"{d} {c}", tz=core.ET) - pd.Timedelta(minutes=1)
            if t in g.index:
                vals.append(abs(float(g.at[t, "Close"]) / float(g["Open"].iloc[0]) - 1))
        if len(vals) < MIN_SESSIONS:
            return None, len(full)
        out[c] = float(np.mean(vals))
    return out, len(full)


def band(sigma, open_, prev_close):
    return max(open_, prev_close) * (1 + sigma), min(open_, prev_close) * (1 - sigma)


def actions(pos, price, upper, lower, vwap, allow_short):
    """The backtest's per-check logic. pos: +1 long, -1 short, 0 flat. -> list of 'exit' / 'long' / 'short' in order."""
    acts = []
    if pos > 0 and price < max(upper, vwap):
        acts.append("exit")
        pos = 0
    elif pos < 0 and price > min(lower, vwap):
        acts.append("exit")
        pos = 0
    if pos == 0:
        if price > upper:
            acts.append("long")
        elif allow_short and price < lower:
            acts.append("short")
    return acts


def at_check(m1_today, day, hhmm):
    """(price, vwap) from FINISHED bars only: the bar that opened one minute before the check, and VWAP through it."""
    m = _et(m1_today)
    if m is None:
        return None
    t = pd.Timestamp(f"{day} {hhmm}", tz=core.ET)
    bar_open = t - pd.Timedelta(minutes=1)
    m = m[(m.index >= pd.Timestamp(f"{day} 09:30", tz=core.ET)) & (m.index <= bar_open)]
    if not len(m) or m.index[-1] != bar_open:
        return None
    vw = I.last(I.session_vwap(m))
    if vw is None or vw != vw:
        return None
    return float(m["Close"].iloc[-1]), float(vw)


def size(px):
    if not px or px <= 0:
        return 0.0
    return math.floor(NOTIONAL / px * 10_000) / 10_000


def prev_session(day):
    d = day - timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in core.HOLIDAYS:
        d -= timedelta(days=1)
    return d


# ================================================================ before the open: history, prior close, dividend
def _pk(day):
    return f"nbs:prep:{day}"


def prepare(day, now):
    """Sigma profile, prior close (dividend-adjusted when Schwab reports today as the ex-date). Stored once per day."""
    have = store.kv_get(_pk(day))
    if have:
        return have
    f = fetch()
    want = prev_session(day)
    start = datetime.combine(day - timedelta(days=30), datetime.min.time(), core.ET).replace(hour=9, minute=30)
    end = datetime.combine(want, datetime.min.time(), core.ET).replace(hour=16)
    try:
        hist = f.m1(TICKER, start, end)
    except Exception as e:
        _state["last_error"] = f"m1 history: {type(e).__name__}"
        return None
    prof, n = profile(hist, day) if hist is not None and len(hist) else (None, 0)
    daily = f.daily(TICKER)
    pc = None
    if daily is not None and len(daily):
        d = daily.copy()
        d.index = pd.DatetimeIndex(d.index).tz_localize(None).normalize() if pd.DatetimeIndex(d.index).tz is not None \
            else pd.DatetimeIndex(d.index).normalize()
        d = d[d.index < pd.Timestamp(day)]
        if len(d) and d.index[-1].date() == want:
            pc = float(d["Close"].iloc[-1])
    if prof is None or pc is None:
        _state["status"] = f"waiting for history (sessions {n}, prior close {'ok' if pc else 'missing'})"
        return None
    div, src = 0.0, "no dividend today"
    try:
        ex, amt = f.dividend(TICKER) if hasattr(f, "dividend") else (None, None)
        if ex == str(day) and amt:
            div, src = float(amt), f"ex-dividend today: ${float(amt):.4f} (Schwab fundamentals)"
        elif ex is None:
            src = "dividend data unavailable: prior close not adjusted"
    except Exception as e:
        src = f"dividend lookup failed ({type(e).__name__}): prior close not adjusted"
    prep = {"day": str(day), "asof": str(want), "made_at": now.isoformat(timespec="seconds"), "sigma": prof, "sessions": n,
            "prev_close": pc, "dividend": div, "dividend_src": src, "prev_close_adj": round(pc - div, 4), "version": VERSION}
    store.kv_set(_pk(day), prep)
    S.decide(f"nbs:prep:{day}", "nbs_spy_ls", TICKER, "PREP", [f"{n} sessions; prior close {pc} ({src})"], prep, "plan", VERSION)
    return prep


# ================================================================ checks and orders
def _ok(day):
    return set(store.kv_get(f"nbs:done:{day}") or [])


def _pend_key(ledger, day):
    return f"nbs:pend:{ledger}:{day}"


def _open(ledger):
    return [p for p in S.positions(ledger=ledger, status="OPEN")]


def run_check(day, hhmm, now, prep, open_, m1_today):
    """Evaluate one check for both ledgers; queue orders. Returns True when the check is finished (acted or recorded)."""
    done = _ok(day)
    t = pd.Timestamp(f"{day} {hhmm}", tz=core.ET)
    late = (now - t).total_seconds() > CHECK_GIVEUP_S
    got = at_check(m1_today, day, hhmm) if not late else None
    if got is None and not late:
        return False                                        # wait for the finished bar
    for led, spec in LEDGERS.items():
        did = f"{led}:{day}:{hhmm}"
        if got is None:
            S.decide(did, led, TICKER, "NO DATA", [f"no finished {hhmm} bar within {CHECK_GIVEUP_S} s (or the desk was down)"],
                     {}, "check", VERSION)
            continue
        price, vwap = got
        up, lo = band(prep["sigma"][hhmm], open_, prep["prev_close_adj"])
        ops = _open(led)
        pos = 0 if not ops else (1 if ops[0]["side"] == "long" else -1)
        acts = actions(pos, price, up, lo, vwap, spec["short"])
        data = {"price": round(price, 4), "vwap": round(vwap, 4), "upper": round(up, 4), "lower": round(lo, 4),
                "sigma": round(prep["sigma"][hhmm], 6), "open": open_, "prev_close_adj": prep["prev_close_adj"], "pos": pos,
                "actions": acts}
        label = " + ".join(a.upper() for a in acts) or ("HOLD" if pos else "NO SIGNAL")
        S.decide(did, led, TICKER, label, [f"price {price:.2f}, band {lo:.2f}-{up:.2f}, VWAP {vwap:.2f}"], data, "check", VERSION)
        if acts:
            pend = store.kv_get(_pend_key(led, day)) or []
            pend += [{"action": a, "check": hhmm} for a in acts]
            store.kv_set(_pend_key(led, day), pend)
    store.kv_set(f"nbs:done:{day}", sorted(done | {hhmm}))
    return True


def _quote(quotes):
    q = dict((quotes or {}).get(TICKER) or {})
    if not q:
        return None
    if q.get("quote_time") is None and q.get("quote_ms"):
        q["quote_time"] = pd.Timestamp(q["quote_ms"], unit="ms", tz="UTC").tz_convert(core.ET)
    return v4exec.equity_quote(TICKER, {TICKER: q})


def _exit(p, q, reason):
    px = q["bid"] if p["side"] == "long" else q["ask"]
    return S.close_position(p["id"], px, reason, exit_fees=round(COMM * p["qty"], 4), quote_t=str(q.get("quote_time")),
                            legs=[{"symbol": TICKER, "action": "sell" if p["side"] == "long" else "buy", "qty": p["qty"]}],
                            extra={"exit_bid": q["bid"], "exit_ask": q["ask"]})


def work_orders(day, now, quotes):
    q = _quote(quotes)
    on = switch_on()
    for led in LEDGERS:
        pend = store.kv_get(_pend_key(led, day)) or []
        changed = False
        while pend:
            o = pend[0]
            t = pd.Timestamp(f"{day} {o['check']}", tz=core.ET)
            ok, why = C.quote_after(q, t, QUOTE_MAX_AGE_S)
            if o["action"] == "exit":
                ops = _open(led)
                if not ops:
                    pend.pop(0); changed = True
                    continue
                if not ok:
                    break                                   # exits wait for a fresh quote; never dropped
                _exit(ops[0], q, f"EXIT at the {o['check']} check: back inside the band / VWAP stop")
                pend.pop(0); changed = True
                continue
            did = f"{led}:{day}:{o['check']}:{o['action']}"
            if _open(led):                                  # an exit ahead of it hasn't filled yet
                break
            if not on:
                S.decide(did, led, TICKER, "SWITCH OFF", ['config/v4.json "nb_shares" is off: no new entries'], {}, "entry", VERSION)
            elif (now - t).total_seconds() > FILL_WINDOW_S:
                S.decide(did, led, TICKER, "MISSED", [f"no fresh quote within {FILL_WINDOW_S} s of the {o['check']} check ({why})"],
                         {}, "entry", VERSION)
            elif not ok:
                break
            else:
                direction = o["action"]
                blk = v4risk.admit(led, BOOK, TICKER, direction, now)
                if blk:
                    S.decide(did, led, TICKER, "BLOCKED-RISK", [blk], {}, "entry", VERSION)
                else:
                    px = q["ask"] if direction == "long" else q["bid"]
                    qty = size(px)
                    rec = {"id": f"{led}:{day}:{o['check']}", "ledger": led, "book": BOOK, "kind": "shares", "date": str(day),
                           "ticker": TICKER, "direction": direction, "side": direction, "qty": qty, "entry_px": px,
                           "entry_t": store.ts(), "signal_t": t.isoformat(), "quote_t": str(q.get("quote_time")),
                           "fees": round(COMM * qty, 4), "risk_usd": None, "max_loss": None,
                           "legs": [{"symbol": TICKER, "label": f"{qty:g} sh", "action": "buy" if direction == "long" else "sell short",
                                     "qty": qty}],
                           "plan": {"label": LABEL, "test": LEDGERS[led]["test"], "check": o["check"], "bid": q["bid"], "ask": q["ask"],
                                    "notional": round(qty * px, 2), "exit_rule": "next check back inside the band / VWAP stop; flat 15:59"},
                           "version": VERSION, "exec_model": EXEC}
                    got, owhy = S.open_position(rec, f"{led} {direction} at the {o['check']} check (paper, simulated fill)")
                    S.decide(did, led, TICKER, "ORDER" if got else "SKIP", [] if got else [owhy],
                             {"position": got, "fill": px, "qty": qty} if got else {}, "entry", VERSION)
            pend.pop(0); changed = True
        if changed:
            store.kv_set(_pend_key(led, day), pend)


def flatten(day, now, quotes, reason):
    q = _quote(quotes)
    t = pd.Timestamp(f"{day} {FLAT}", tz=core.ET)
    for led in LEDGERS:
        store.kv_set(_pend_key(led, day), [])               # nothing new after the flat time
        for p in _open(led):
            if q and C.quote_after(q, t, QUOTE_MAX_AGE_S)[0]:
                _exit(p, q, reason)
            elif now.strftime("%H:%M") >= CLOSE:
                v4exec.close_now(p, reason + " (no fresh quote by 16:00: next valid quote)", {TICKER: q} if q else None)


def mark(now, quotes):
    q = _quote(quotes)
    if not (q and q.get("executable")):
        return
    for led in LEDGERS:
        for p in _open(led):
            if (p.get("plan") or {}).get("pending_exit"):
                v4exec.retry_pending(p, {TICKER: q})
                continue
            mtm = round(S.pnl(p, q["bid"] if p["side"] == "long" else q["ask"]), 2)
            S.update_plan(p["id"], mtm=mtm, mark_t=str(q.get("quote_time")))
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
    if "09:30" <= hm < "16:05":                             # a day ledger: anything from an earlier session closes
        for led in LEDGERS:
            for p in _open(led):
                if str(p["date"]) < str(day):
                    v4exec.overnight(p, now)
    if str(day) in core.EARLY_CLOSE:
        _state["status"] = "early-close day: skipped (as in the backtest)"
        return
    prep = store.kv_get(_pk(day))
    if not prep and PREP_FROM <= hm < CLOSE:
        with schwab.priority("normal"):
            prep = prepare(day, now)
    if not ("09:30" <= hm < "16:05"):
        _state["status"] = f"prep {'ready' if prep else 'not ready'} ({sess.get('state')})"
        return
    open_ = store.kv_get(f"nbs:open:{day}")
    due = [c for c in CHECKS if c not in _ok(day) and now >= pd.Timestamp(f"{day} {c}", tz=core.ET) + pd.Timedelta(seconds=BAR_WAIT_S)]
    m1 = None
    if (open_ is None or due) and hm < FLAT:
        with schwab.priority("normal"):
            try:
                m1 = f.m1_today(TICKER, day)
            except Exception as e:
                _state["last_error"] = f"m1 today: {type(e).__name__}"
        m1 = _et(m1)
        if open_ is None and m1 is not None:
            first = m1[m1.index >= pd.Timestamp(f"{day} 09:30", tz=core.ET)]
            if len(first) and first.index[0].strftime("%H:%M") == "09:30":
                open_ = float(first["Open"].iloc[0])
                store.kv_set(f"nbs:open:{day}", open_)
    for c in due:
        if hm >= FLAT:
            break
        if not prep or open_ is None:                       # can't evaluate: record it once the check is too old
            if (now - pd.Timestamp(f"{day} {c}", tz=core.ET)).total_seconds() > CHECK_GIVEUP_S:
                _skip(day, c, prep, open_)
            continue
        if not run_check(day, c, now, prep, open_, m1):
            break
    pend = any(store.kv_get(_pend_key(led, day)) for led in LEDGERS)
    opens = [p for led in LEDGERS for p in _open(led)]
    need_q = pend or (opens and hm >= FLAT)
    due_mark = _state["mark_t"] is None or _state["mark_t"] > now or (now - _state["mark_t"]).total_seconds() >= MARK_EVERY_S
    quotes = {}
    if need_q or (opens and due_mark):
        with schwab.priority("risk" if opens else "normal"):
            try:
                quotes, _ = f.quotes([TICKER])
            except Exception as e:
                _state["last_error"] = f"quotes: {type(e).__name__}"
        if opens and due_mark:
            _state["mark_t"] = now
            mark(now, quotes)
    if hm >= FLAT:
        flatten(day, now, quotes, "FLAT at the close (15:59)")
    elif pend:
        work_orders(day, now, quotes)
    _state["status"] = f"{len(opens)} open, checks done {len(_ok(day))}/12"
    _state["step_s"] = round(time.time() - t0, 2)


def _et(df):
    if df is None or not len(df):
        return None
    d = df.copy()
    d.index = pd.DatetimeIndex(d.index)
    d.index = d.index.tz_localize(core.ET) if d.index.tz is None else d.index.tz_convert(core.ET)
    return d


def _skip(day, c, prep, open_):
    why = "no history / prior close" if not prep else "no 09:30 open bar"
    for led in LEDGERS:
        S.decide(f"{led}:{day}:{c}", led, TICKER, "NO DATA", [why], {}, "check", VERSION)
    store.kv_set(f"nbs:done:{day}", sorted(_ok(day) | {c}))


def _run():
    while not _state["stop"]:
        try:
            step()
            try:
                import health
                health.beat("v4trend", True, _state.get("status"), _state.get("step_s"))
            except Exception:
                pass
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {e}"[:200]
        time.sleep(5)


def start():
    if _state["thread"]:
        return False
    th = threading.Thread(target=_run, daemon=True, name="v4trend")
    _state["thread"] = th
    th.start()
    return True


def report_meta(ledger, trades=None):
    """Research page: evidence labels, the backtest numbers in the same unit (bp of notional per trade day)."""
    test = LEDGERS[ledger]["test"]
    out = {"label": LABEL, "status": "forward paper test (not promoted); promotion needs 40 forward trades (G5)",
           "backtest": {k: {"label": v["label"], **v[test]} for k, v in BACKTEST.items()}, "test": test,
           "notional": NOTIONAL, "exec_model": EXEC}
    tr = [t for t in trades or [] if (t.get("plan") or {}).get("notional")]
    if tr:
        by_day = {}
        for t in tr:
            by_day[t["date"]] = by_day.get(t["date"], 0.0) + float(t["realized"] or 0) / NOTIONAL * 1e4
        out["forward_bp_per_trade_day"] = round(float(np.mean(list(by_day.values()))), 2)
        out["forward_trade_days"] = len(by_day)
    return out


def status():
    day = core.now_et().date()
    return {"version": VERSION, "status": _state["status"], "last_error": _state["last_error"], "step_s": _state["step_s"],
            "switch": switch_on(), "prep": store.kv_get(_pk(day)), "open_0930": store.kv_get(f"nbs:open:{day}"),
            "checks_done": sorted(_ok(day)), "pending": {led: store.kv_get(_pend_key(led, day)) for led in LEDGERS},
            "open": [p["id"] for led in LEDGERS for p in _open(led)], "label": LABEL}
