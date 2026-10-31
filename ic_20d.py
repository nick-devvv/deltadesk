"""ic_20d.py - v4 premium ledger `ic_20d` (docs/STRATEGY_PLAN.md section 3.4). PRE-REGISTERED, unvalidated.

Source: tastytrade 0DTE SPX iron condor study (via StockWire X 2026-09-27): 20-delta shorts, $20 wings, about 72% wins
unmanaged; a 2x stop kept the win rate near 70% and cut CVaR about 13%. Rules frozen 2026-10-31, before any result:
  * At 10:00 ET sell the call and the put whose |delta| is nearest 0.20 (live chain deltas), buy wings $2 further out.
  * Close the whole condor when its cost to close (short legs at the ask - long legs at the bid) reaches 2x the credit
    received, checked on live quotes every engine tick; otherwise exit 15:25 ET.
  * Skip FOMC days (config/events.json, else the dated FOMC list in config/v4.json) - enforced by the risk layer.
  * 1 condor; fills by v4spreads pricing, every leg quoted after 10:00:00; retried until 10:05, then recorded missed.
Symbols: SPY, QQQ, and XSP when Schwab lists it that day.
"""
import pandas as pd

import core
import v4common as C
import v4risk
import v4spreads as SP
import v4store as S

VERSION = "2026-11-02.v4-ic_20d"
LEDGER = "ic_20d"
BOOK = "premium"
TARGET_DELTA = 0.20
STOP_MULT = 2.0
ENTRY_AT = "10:00"


def nearest_delta(rows, target=TARGET_DELTA):
    best = None
    for r in rows:
        d = r.get("delta")
        if d is None or not r.get("bid") or not r.get("ask"):
            continue
        k = abs(abs(d) - target)
        if best is None or k < best[0] or (k == best[0] and abs(d) < abs(best[1].get("delta"))):
            best = (k, r)
    return best[1] if best else None


def pick_legs(calls, puts):
    sc, sp = nearest_delta(calls), nearest_delta(puts)
    if not sc or not sp:
        return None, "no call/put with a usable delta and a two-sided quote"
    lc, lp = SP.by_strike(calls, float(sc["strike"]) + SP.WIDTH), SP.by_strike(puts, float(sp["strike"]) - SP.WIDTH)
    if not lc or not lp:
        return None, "a $2 wing strike is not listed"
    if float(sp["strike"]) >= float(sc["strike"]):
        return None, "the 20-delta put strike is not below the 20-delta call strike"
    return [SP.leg(sc, "sell", "C"), SP.leg(lc, "buy", "C"), SP.leg(sp, "sell", "P"), SP.leg(lp, "buy", "P")], None


def tick(ticker, now=None):
    now = now or core.now_et()
    day = now.date()
    hm = now.strftime("%H:%M")
    if hm < ENTRY_AT or hm >= "15:25":
        return None
    dkey = f"{LEDGER}:{ticker}:{day}"
    if S.decided(dkey):
        return None
    signal_t = pd.Timestamp(C.at(day, ENTRY_AT))

    def done(decision, why, data=None):
        S.decide(dkey, LEDGER, ticker, decision, [why] if why else [], data or {}, "day", VERSION)
        return decision
    late = (pd.Timestamp(now) - signal_t).total_seconds() >= SP.ENTRY_WINDOW_MIN * 60 - 15
    if (pd.Timestamp(now) - signal_t).total_seconds() > SP.ENTRY_WINDOW_MIN * 60 + 60:
        return done("MISSED", "the desk was not running at 10:00-10:05")
    why = v4risk.admit(LEDGER, BOOK, ticker, "neutral", now)
    if why:
        return done("BLOCKED-RISK", why)
    sym = SP.chain_symbol(ticker)
    calls, e1 = SP.chain(sym, "C", day)
    puts, e2 = SP.chain(sym, "P", day)
    if not calls or not puts:
        return done("MISSED", f"no chain ({e1 or e2})") if late else None
    legs, lwhy = pick_legs(calls, puts)
    if not legs:
        return done("SKIP", lwhy)
    plan = {"structure": "iron condor", "target_delta": TARGET_DELTA, "stop": f"close debit >= {STOP_MULT:g}x credit, else 15:25"}
    pid, owhy = SP.open_spread(LEDGER, BOOK, VERSION, ticker, f"{day}-{ticker}-IC20", legs, signal_t, "neutral", plan, now)
    if pid:
        return done("ORDER", None, {"position": pid, "legs": [l["label"] for l in legs]})
    if owhy and owhy.startswith("WAIT"):
        return done("MISSED", owhy[6:]) if late else None
    return done("SKIP", owhy)


def manage(p, now=None):
    return SP.manage_spread(p, now or core.now_et(), STOP_MULT)
