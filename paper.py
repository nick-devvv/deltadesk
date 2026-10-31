"""paper.py - INTERNAL simulated execution for the paper portfolios (no broker, no real money, no Schwab orders).

Fill model (all labeled 'sim'):
  buy  = the first executable option quote AFTER the signal (+ configured latency): ask + slippage, + fees
  sell = executable bid - slippage, - fees
  slippage = max(slippage_min, spread x slippage_spread_frac); fees per contract per side from policy.
  If the quote is missing, stale, crossed or the provider isn't executable: NO FILL. Entries are dropped with a
  reason; exits stay PENDING and retry, and the outage is recorded. A fill is never invented during a gap.
  Displayed size (when the provider sends it) caps the fill quantity.

Portfolios: 'paper' (main), 'research' (shadow), 'old' (frozen old-policy shadow), and the v3.1 research variants
'exit31' (research entries managed with the v3.1 exits), 'noise' (noise-band momentum on SPY/QQQ) and 'inplay'
(stocks-in-play opening-range breakouts from the scanner). Each position records its strategy version and the
underlying price at entry and exit, so the stock's move and the option result can be compared. Ideas are reserved atomically
(PRIMARY KEY portfolio+idea), so retries, restarts, reconnects or two detectors can't open the same idea twice,
and the main 4-ideas/day cap can't be exceeded by simultaneous entries.
"""
import json
import sqlite3

import core
import marketdata
import store

# v3.4 strategy lab: one paper ledger per strategy family (lab.py FAMILIES maps each family to one of these)
LAB_LEDGERS = ("lab_orb_break", "lab_orb_retest", "lab_orb_failed", "lab_lvl_break", "lab_lvl_retest", "lab_vwap_reclaim",
               "lab_vwap_reject", "lab_momo", "lab_pullback", "lab_v3", "lab_vwap_macd", "lab_orb15", "lab_orb15_rt",
               "lab_macd_video", "lab_noise")
PORTFOLIOS = ("paper", "research", "old", "exit31", "noise", "inplay", "gated", "earn_post", "earn_pre", "board") + LAB_LEDGERS
RESEARCH = ("research", "exit31", "noise", "inplay", "old", "gated", "earn_post", "earn_pre", "board") + LAB_LEDGERS   # experimental ledgers, never mixed into main paper


def underlying_px(ticker):
    """Last finished 1m close (or the quote's last) of the underlying, for stock-move vs option-result comparisons."""
    try:
        q = marketdata.quote(ticker) or {}
        if q.get("last"):
            return round(float(q["last"]), 4)
        df, _, _ = marketdata.bars(ticker, refresh=False)
        return round(float(df["Close"].iloc[-1]), 4) if df is not None and len(df) else None
    except Exception:
        return None


# v3.3 "strict" execution model (exec2), for the new ledgers only; legacy ledgers keep their recorded model so their
# results don't change meaning. exec2 starts from the quote's bid/ask (not the mid): buy at ask + $0.01, sell at
# bid - $0.01, $0.02 fees per contract per side, so the spread is counted once (half on the way in, half out).
STRICT = ("gated", "board", "earn_post", "router")
EXEC_MODEL = {"strict": "2026-10-30.exec2 (ask+0.01 in, bid-0.01 out, $0.02/side; final fill <= limit; latency enforced)",
              "legacy": "2026-10-29.exec1 (ask + max(0.01, half spread) in, bid - same out)"}


def is_strict(portfolio):
    return portfolio in STRICT or str(portfolio).startswith(("spec_", "lab_"))


def _ev_kind(portfolio, main_kind):
    """Lab ledgers log as one 'lab' kind (shown in the Markets lab box, kept out of the trade feed)."""
    return main_kind if portfolio == "paper" else ("lab" if str(portfolio).startswith("lab_") else portfolio)


def strict_costs():
    k = core.policy()["v3"]["contract"]
    return k["slippage_min"], k["fees_per_contract_side"]


def costs(spread):
    k = core.policy()["v3"]["contract"]
    return max(k["slippage_min"], (spread or 0) * k["slippage_spread_frac"]), k["fees_per_contract_side"]


def reserve_idea(portfolio, idea, ticker, side, cap=None):
    """Atomic reservation. Returns (ok, reason). With cap, counts today's reservations inside the same transaction."""
    day = core.now_et().strftime("%Y-%m-%d")
    with store._lock:
        c = store.conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            if cap is not None:
                n = c.execute("SELECT COUNT(*) FROM ideas WHERE portfolio=? AND date=? AND status!='RELEASED'", (portfolio, day)).fetchone()[0]
                if n >= cap:
                    c.execute("ROLLBACK")
                    return False, f"daily cap reached ({n}/{cap} ideas)"
            c.execute("INSERT INTO ideas(portfolio,idea,date,ticker,side,created,status) VALUES(?,?,?,?,?,?,?)",
                      (portfolio, idea, day, ticker, side, store.ts(), "RESERVED"))
            c.execute("COMMIT")
            return True, None
        except sqlite3.IntegrityError:
            c.execute("ROLLBACK")
            return False, "idea already taken (duplicate detector, retry or restart)"
        except Exception:
            try:
                c.execute("ROLLBACK")
            except Exception:
                pass
            raise


def release_idea(portfolio, idea, why):
    """An idea that never filled does not count toward the cap. A FILLED idea is never released (v3.5)."""
    store.x("UPDATE ideas SET status='RELEASED' WHERE portfolio=? AND idea=? AND status!='FILLED'", (portfolio, idea))


def ideas_today(portfolio):
    day = core.now_et().strftime("%Y-%m-%d")
    return store.q("SELECT COUNT(*) n FROM ideas WHERE portfolio=? AND date=? AND status!='RELEASED'", (portfolio, day))[0]["n"]


def sim_quote(symbol):
    import optionhours
    ok, why = optionhours.tradable(symbol)
    if not ok:
        return None, why                                  # never a simulated fill against a closed options market
    q, err = marketdata.option_quote(symbol)
    if not q:
        return None, err or "no quote"
    if not q.get("executable"):
        return None, "not executable: " + (", ".join(q.get("problems") or []) or q.get("provider", "?"))
    return q, None


def buy(portfolio, idea, ticker, side, plan, qty, signal_t):
    """Simulated entry. Returns (position_id or None, reason)."""
    sym = plan["symbol"]
    if store.kv_get("paper_pause"):
        return None, "paper entries are paused (emergency pause on the Markets page)"
    q, err = sim_quote(sym)
    if not q:
        return None, f"no simulated fill: {err}"
    if qty <= 0:
        return None, "size 0"
    strict = is_strict(portfolio)
    size = q.get("ask_size")
    if strict:
        if size is not None and isinstance(size, (int, float)) and size <= 0:
            return None, "no size offered at the ask: no simulated fill"
        mult = q.get("multiplier")
        if mult not in (None, 100, 100.0):
            return None, f"non-standard contract multiplier {mult}: not simulated"
        lat = core.policy()["v3"]["contract"].get("latency_s", 1.0)
        qt = q.get("quote_time")
        try:
            from datetime import datetime as _dt
            sig = _dt.fromisoformat(str(signal_t))
            if qt is not None and (pd_ts(qt) - sig).total_seconds() < lat:
                return None, f"no quote yet at least {lat:.0f} s after the signal (decision latency): wait for the next quote"
        except (ValueError, TypeError):
            return None, "signal time unknown: no simulated fill"
    if size not in (None, 0) and isinstance(size, (int, float)):
        qty = min(qty, int(size))
    if strict:
        slip, fee = strict_costs()
    else:
        slip, fee = costs(q["ask"] - q["bid"])
    fill = round(q["ask"] + slip, 4)
    if strict:
        if plan.get("premium_limit") and fill > plan["premium_limit"] + 1e-9:
            return None, (f"final fill {fill:.2f} (ask {q['ask']:.2f} + {slip:.2f} slippage) is above the limit "
                          f"{plan['premium_limit']:.2f}: no chase")
        cap = core.policy()["risk"]["stop_cap_pct"]
        ceiling = core.cents_up(fill * (1 - cap) + slip + 2 * fee / 100)          # the 20% line from the ACTUAL fill
        if ceiling >= q["bid"] or ceiling >= fill:
            return None, f"the 20% planned-loss line {ceiling:.2f} would sit at or above the bid {q['bid']:.2f}: infeasible"
        if plan["premium_stop"] < ceiling:
            plan = dict(plan, premium_stop=ceiling)                                 # tighten to the actual 20% line
    elif plan.get("premium_limit") and q["ask"] > plan["premium_limit"]:
        return None, f"ask {q['ask']:.2f} above the limit {plan['premium_limit']:.2f}: no chase"
    pid = f"{portfolio}:{idea}"            # v3.5: the FULL ledger id (two-letter prefixes could collide); old ids stay
    st = {"v": plan.get("v", 3), "symbol": sym, "entry_premium": fill, "fees_side": fee, "slip_at_entry": slip,
          "premium_stop": plan["premium_stop"], "stop_px": plan["stop_px"], "t1": plan["t1"], "t1_level": plan["t1_level"],
          "t1_px": plan["t1_px"], "be_trigger": plan["be_trigger"], "breakeven_net": plan["breakeven_net"],
          "high_water": q["bid"], "high_water_t": store.ts(), "last_progress_t": store.ts(), "be_hit": False,
          "lock_hit": False, "t1_done": False, "runner": False, "trail": None, "last_bid": q["bid"], "last_ask": q["ask"],
          "quote_age_s": q.get("age_s"), "provider": q.get("provider"), "signal_t": signal_t, "family": plan.get("family"),
          "entry_mode": plan.get("entry_mode"), "stops": [{"t": store.ts(), "stop": plan["premium_stop"], "by": "desk",
                                                            "why": "initial 20% ceiling (costs reserved)"}],
          "actions_done": [], "flat_by": plan.get("flat_by"), "rr_option": plan.get("rr_option"),
          "rr_underlying": plan.get("rr_underlying"), "model": plan.get("model"),
          "exit_profile": plan.get("exit_profile", "v3"), "variant": plan.get("variant"),
          "entry_px": plan.get("entry_px") or underlying_px(ticker), "delta_entry": q.get("delta"),
          "fill_t": store.ts(), "quote_t": str(q.get("quote_time")) if q.get("quote_time") is not None else None,
          "latency_s": _latency(signal_t), "gate": plan.get("gate"), "catalyst_id": plan.get("catalyst_id"),
          "exec_model": EXEC_MODEL["strict" if strict else "legacy"], "x_read": plan.get("x_read"), "row": plan.get("row")}
    for k in ("noise_upper", "noise_lower", "orb_high", "orb_low", "atr14", "rvol", "contract_score", "scan_id", "expiry"):
        if plan.get(k) is not None:
            st[k] = plan[k]
    # v3.5: position, order, idea and event are ONE transaction; a retry of the same idea can't fill twice
    with store.tx():
        if store.q("SELECT id FROM positions WHERE id=?", (pid,)):
            return None, f"already filled as {pid} (a retry never fills twice)"
        store.pos_insert({"id": pid, "ledger": portfolio, "date": core.now_et().strftime("%Y-%m-%d"), "ticker": ticker,
                          "contract": plan["label"], "symbol": sym, "side": side, "qty_init": qty, "qty_open": qty, "fill": fill,
                          "opened": store.ts(), "closed": None, "status": "OPEN", "setup_id": idea, "grade": plan.get("grade"),
                          "setup": plan.get("family"), "plan": st, "realized": round(-fee * qty, 2), "mfe": 0, "mae": 0,
                          "policy_version": plan.get("policy_version") or core.policy()["version"],
                          "verified": f"sim fill on {q.get('provider')}", "notes": ""})
        store.x("INSERT INTO orders(client_id,position_id,ts,side,qty,status,broker_id,filled_qty,filled_price,reason) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)", (f"{pid}-B", pid, store.ts(), "buy", qty, "FILLED", "sim", qty, fill, plan.get("family")))
        store.x("UPDATE ideas SET status='FILLED', position_id=? WHERE portfolio=? AND idea=?", (pid, portfolio, idea))
        store.event(_ev_kind(portfolio, "paper_open"),
                    f"{_name(portfolio)} BUY {qty} {ticker} {plan['label']} sim fill ${fill:.2f} (ask {q['ask']:.2f} + {slip:.2f} slip) | "
                    f"stop {_px(plan.get('stop_px'))} underlying / ${plan['premium_stop']:.2f} premium | T1 {plan.get('t1') or 'none'} {_px(plan.get('t1_level'))}",
                    portfolio, pid, {"quote_age_s": q.get("age_s"), "provider": q.get("provider")})
    return pid, None


def pd_ts(v):
    import pandas as pd
    t = pd.Timestamp(v)
    return (t.tz_localize(core.ET) if t.tzinfo is None else t).to_pydatetime()


def _latency(signal_t):
    """Seconds from the signal (the decision time) to this simulated fill."""
    try:
        from datetime import datetime
        return round((core.now_et() - datetime.fromisoformat(str(signal_t))).total_seconds(), 1)
    except Exception:
        return None


def _px(v):
    return f"{v:.2f}" if isinstance(v, (int, float)) else "n/a"


def sell(p, qty, reason):
    """Simulated exit at the executable bid. Returns (filled_qty, price) or (0, why) - never invents a fill."""
    qty = min(qty, p["qty_open"])
    if qty <= 0:
        return 0, "nothing open"
    q, err = sim_quote(p["symbol"])
    if not q:
        key = f"pending_exit:{p['id']}"
        if not store.kv_get(key):
            store.kv_set(key, {"since": store.ts(), "reason": reason})
            store.event("error", f"{_name(p['ledger'])} EXIT PENDING {p['contract']} ({reason}): {err}. No fill until a valid quote.",
                        p["ledger"], p["id"])
        return 0, err
    store.kv_set(f"pending_exit:{p['id']}", None)
    slip, fee = strict_costs() if is_strict(p["ledger"]) else costs(q["ask"] - q["bid"])
    px = round(max(0.0, q["bid"] - slip), 4)
    pnl = round((px - p["fill"]) * 100 * qty - fee * qty, 2)
    ux = underlying_px(p["ticker"]) if p["qty_open"] - qty == 0 else None
    with store.tx():                               # v3.5: the exit, its order and its event commit together
        cur = store.q("SELECT qty_open, status, realized FROM positions WHERE id=?", (p["id"],))
        if cur and (cur[0]["status"] != "OPEN" or cur[0]["qty_open"] < qty):
            return 0, "already exited (a retry never sells twice)"
        if cur:
            p["realized"], p["qty_open"] = cur[0]["realized"], cur[0]["qty_open"]
        p["realized"] = round((p["realized"] or 0) + pnl, 2)
        p["qty_open"] -= qty
        if p["qty_open"] == 0:
            p.update(status="CLOSED", closed=store.ts())
            p["plan"]["exit_px"] = ux
            p["plan"]["exit_reason"] = reason
        store.pos_save(p)
        n = len(store.q("SELECT client_id FROM orders WHERE position_id=?", (p["id"],)))
        store.x("INSERT INTO orders(client_id,position_id,ts,side,qty,status,broker_id,filled_qty,filled_price,reason) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (f"{p['id']}-S{n}", p["id"], store.ts(), "sell", qty, "FILLED", "sim", qty, px, reason))
        store.event(_ev_kind(p["ledger"], "paper_exit"),
                    f"{_name(p['ledger'])} SELL {qty} {p['contract']} sim ${px:.2f} (bid {q['bid']:.2f} - {slip:.2f}): {reason} | "
                    f"trade P/L ${p['realized']:+.2f} net", p["ledger"], p["id"])
    return qty, px


def streak(portfolio, day=None):
    """Consecutive LOSING completed trades today (net of costs). Breakeven (|net| < $1) and wins reset it.
    A trade counts once (one idea = one position), however many partial sells it had."""
    day = day or core.now_et().strftime("%Y-%m-%d")
    closed = [p for p in store.positions(ledger=portfolio, day=day) if p["status"] == "CLOSED"]
    closed.sort(key=lambda p: p["closed"] or "")
    n = 0
    for p in reversed(closed):
        if (p["realized"] or 0) <= -1.0:
            n += 1
        else:
            break
    return n


def _name(portfolio):
    return {"paper": "PAPER", "research": "RESEARCH", "old": "OLD-POLICY", "exit31": "RESEARCH v3.1-EXITS",
            "noise": "RESEARCH NOISE-BAND", "inplay": "RESEARCH IN-PLAY"}.get(portfolio, portfolio.upper())
