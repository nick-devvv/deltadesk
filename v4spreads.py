"""v4spreads.py - paper multi-leg option spreads for the v4 premium-selling ledgers (orb_credit, ic_20d).

Pricing is conservative and comes only from fresh Schwab quotes (no model):
  open credit  = short legs at the bid  - long legs at the ask
  close debit  = short legs at the ask  - long legs at the bid
  fees         = $0.65 per contract per side (every leg, on the way in and out)
  max loss     = (wing width - credit) x 100 x spreads + all fees (one side of a condor can lose, not both)
Every leg needs an executable quote dated at least the decision latency after the signal. Legs are chosen from the
live chain (listed strikes and deltas) and then re-quoted together. Nothing is filled when any leg is missing.

XSP: run only when Schwab returns a chain for $XSP that day; otherwise "not available" is recorded once per day and the
ledgers run on SPY and QQQ only. Its opening range comes from $XSP 1m bars, or from $SPX bars / 10 (labeled) if Schwab
has no $XSP bars.
"""
import pandas as pd

import core
import marketdata
import store
import v4common as C
import v4exec
import v4store as S

WIDTH = 2.0
ENTRY_WINDOW_MIN = 5
EXTRA = "XSP"
EXTRA_CHAIN = "$XSP"


def chain(sym, side, day):
    """Today's listed contracts for one side: [{symbol, strike, bid, ask, delta, exp, ts}] sorted by strike."""
    try:
        rows, err = marketdata.provider().chain(sym, side, day.isoformat() if hasattr(day, "isoformat") else str(day))
    except Exception as e:
        rows, err = None, type(e).__name__
    d = day.isoformat() if hasattr(day, "isoformat") else str(day)
    rows = [r for r in (rows or []) if (r.get("exp") or d) == d and r.get("strike") is not None]
    rows.sort(key=lambda r: r["strike"])
    return rows, err


def extra_available(now):
    """Is $XSP available today (one chain probe per day, result stored; 'not available' logged once)."""
    day = now.date()
    key = f"v4_xsp:{day}"
    hit = store.kv_get(key)
    if hit is not None:
        return bool(hit.get("available"))
    rows, err = chain(EXTRA_CHAIN, "C", day)
    ok = bool(rows)
    store.kv_set(key, {"available": ok, "why": None if ok else (err or "empty chain"), "at": store.ts()})
    S.decide(f"v4_xsp:{day}", "premium", EXTRA, "AVAILABLE" if ok else "NOT AVAILABLE",
             [] if ok else [f"Schwab returned no $XSP chain today ({err or 'empty'}): XSP skipped"], {}, "data", "v4spreads")
    if not ok:
        store.event("v4", f"XSP not available today ({err or 'empty chain'}): orb_credit / ic_20d run on SPY and QQQ only", "v4")
    return ok


def extra_bars(now):
    """(finished 1m bars for XSP, source label) or (None, why)."""
    try:
        m1, _, meta = marketdata.bars(EXTRA_CHAIN)
        if m1 is not None and len(m1):
            return C.finished(m1, now), "$XSP 1m bars"
    except Exception:
        pass
    try:
        m1, _, meta = marketdata.bars("$SPX")
        if m1 is not None and len(m1):
            m = C.finished(m1, now).copy()
            for col in ("Open", "High", "Low", "Close"):
                m[col] = m[col] / 10.0
            return m, "$SPX 1m bars / 10 (no $XSP bars)"
    except Exception:
        pass
    return None, "no $XSP or $SPX bars"


def chain_symbol(ticker):
    return EXTRA_CHAIN if ticker == EXTRA else ticker


def leg(row, action, right):
    return {"symbol": row["symbol"], "strike": float(row["strike"]), "right": right, "action": action, "qty": 1,
            "expiry": row.get("exp"), "label": f"{float(row['strike']):g}{right}", "delta_at_entry": row.get("delta")}


def by_strike(rows, k):
    for r in rows:
        if abs(float(r["strike"]) - k) < 1e-6:
            return r
    return None


def quote_legs(legs, signal_t):
    """(quotes, None) when every leg has an executable quote dated after the signal, else (None, why)."""
    got, err = marketdata.option_quotes([l["symbol"] for l in legs], max_age_s=2)
    for l in legs:
        ok, why = C.quote_after((got or {}).get(l["symbol"]), signal_t, marketdata.MAX_OPT_QUOTE_AGE_S)
        if not ok:
            return None, f"{l['label']}: {why or err}"
    return got, None


def open_spread(ledger, book, version, ticker, idea, legs, signal_t, direction, plan, now):
    """Price and open one paper spread. Returns (position_id, None) / (None, why) / (None, 'WAIT: why') for a retry."""
    qs, why = quote_legs(legs, signal_t)
    if not qs:
        return None, f"WAIT: {why}"
    credit = S.spread_credit(legs, qs)
    fees_in = S.SPREAD_FEE * len(legs)
    if credit <= 0:
        return None, f"no credit at the quote (shorts at bid - longs at ask = {credit:.2f})"
    width = max(abs(legs[i]["strike"] - legs[i + 1]["strike"]) for i in range(0, len(legs), 2))
    max_loss = round((width - credit) * 100 + 2 * fees_in, 2)
    debit_now = S.spread_debit(legs, qs)
    pid = f"{ledger}:{idea}"
    rec = {"id": pid, "ledger": ledger, "book": book, "kind": "spread", "date": now.strftime("%Y-%m-%d"), "ticker": ticker,
           "direction": direction, "side": plan.get("structure"), "qty": 1, "entry_px": credit, "entry_t": store.ts(),
           "signal_t": pd.Timestamp(signal_t).isoformat(), "quote_t": max(str(qs[l["symbol"]].get("quote_time")) for l in legs),
           "fees": fees_in, "risk_usd": max_loss, "max_loss": max_loss,
           "legs": [dict(l, bid=qs[l["symbol"]]["bid"], ask=qs[l["symbol"]]["ask"], delta=qs[l["symbol"]].get("delta")) for l in legs],
           "plan": dict(plan, credit=credit, width=width, debit_at_entry=debit_now, max_loss=max_loss,
                        pricing="shorts at bid - longs at ask; $0.65/contract/side"),
           "version": version, "exec_model": "spread065"}
    return S.open_position(rec, "credit spread open")


def manage_spread(p, now, stop_mult=None):
    """Pending exits, all out 15:25, and (ic_20d) the close-debit >= stop_mult x credit stop on live quotes."""
    if (p.get("plan") or {}).get("pending_exit"):
        return v4exec.retry_pending(p)
    sess = core.session_info(now)
    qs = v4exec.leg_quotes(p)
    ok = all(v4exec._q_ok(qs.get(l["symbol"])) for l in p["legs"])
    debit = S.spread_debit(p["legs"], qs) if ok else None
    if debit is not None:
        mtm = round((p["entry_px"] - debit) * 100 * p["qty"] - (p["fees"] or 0) - S.SPREAD_FEE * len(p["legs"]), 2)
        S.update_plan(p["id"], last_debit=debit, mtm=mtm, last_quote=store.ts())
        S.mark(p["id"], mtm, mtm)
    if now.strftime("%H:%M") >= sess["all_out"]:
        return v4exec.close_now(p, f"ALL OUT {sess['all_out']} (session rule)", qs if ok else None)
    if stop_mult and debit is not None and debit >= stop_mult * p["entry_px"]:
        return v4exec.close_now(p, f"STOP: close debit {debit:.2f} >= {stop_mult:g}x the credit {p['entry_px']:.2f} (live quotes)", qs)
    return None
