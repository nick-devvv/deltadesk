"""v4exec.py - one exit implementation per position kind for every v4 ledger (paper, simulated fills only).

close_now(p, reason) closes at the current executable quote:
  shares        long: bid - $0.01, short: ask + $0.01
  option        the position's exec model (noise1 = as the noise ledger; bidask065 = at the bid, $0.65/contract)
  spread        close debit = short legs at the ask - long legs at the bid, $0.65/contract/side
With no valid quote nothing is invented: the exit is marked PENDING on the position (reason kept) and every manager
retries it on its next pass (retry_pending). Exits are never blocked by a risk limit or the kill switch.
"""
import core
import marketdata
import store
import v4store as S


def _q_ok(q):
    return bool(q and q.get("executable") and q.get("bid") is not None and q.get("ask") is not None and q["ask"] > 0
                and q["bid"] >= 0 and q["bid"] <= q["ask"])


def equity_quote(ticker, quotes=None):
    """Labeled equity quote: from a batch the caller already fetched (scanner-style dict with quote_ms) or marketdata."""
    if quotes and ticker in quotes:
        q = dict(quotes[ticker])
        if "quote_time" not in q and q.get("quote_ms"):
            import pandas as pd
            q["quote_time"] = pd.Timestamp(q["quote_ms"], unit="ms", tz="UTC").tz_convert(core.ET)
        if "executable" not in q:
            import pandas as pd
            qt = q.get("quote_time")
            age = (pd.Timestamp(core.now_et()) - pd.Timestamp(qt)).total_seconds() if qt is not None else None
            q["age_s"] = age
            q["executable"] = bool(age is not None and -5 <= age <= marketdata.MAX_EQ_QUOTE_AGE_S and marketdata.executable())
        return q
    return marketdata.quote(ticker)


def leg_quotes(p):
    syms = [l["symbol"] for l in p["legs"]]
    if len(syms) == 1:
        q, _ = marketdata.option_quote(syms[0])
        return {syms[0]: q} if q else {}
    got, _ = marketdata.option_quotes(syms)
    return got or {}


def exit_price(p, quotes=None):
    """(price, exit_fees, quote_t, why) for closing the whole position now; price None when no valid quote."""
    k = p["kind"]
    if k == "shares":
        q = equity_quote(p["ticker"], quotes)
        if not _q_ok(q):
            return None, 0.0, None, "no valid stock quote"
        px = S.share_sell(q) if p["side"] == "long" else S.share_buy(q)
        return px, 0.0, str(q.get("quote_time")), None
    qs = quotes if quotes is not None and all(l["symbol"] in quotes for l in p["legs"]) else leg_quotes(p)
    if not all(_q_ok(qs.get(l["symbol"])) for l in p["legs"]):
        bad = [l["symbol"] for l in p["legs"] if not _q_ok(qs.get(l["symbol"]))]
        return None, 0.0, None, f"no valid quote for {', '.join(bad)}"
    qt = max(str(qs[l["symbol"]].get("quote_time")) for l in p["legs"])
    if k == "spread":
        return S.spread_debit(p["legs"], qs), S.SPREAD_FEE * len(p["legs"]) * p["qty"], qt, None
    px, fee = S.option_sell(qs[p["legs"][0]["symbol"]], p.get("exec_model") or "bidask065")
    return px, fee * p["qty"], qt, None


def close_now(p, reason, quotes=None):
    """Close at the current quote, or mark the exit pending. Returns realized P/L or None."""
    px, fees, qt, why = exit_price(p, quotes)
    if px is None:
        pend = (p.get("plan") or {}).get("pending_exit")
        if not pend:
            S.update_plan(p["id"], pending_exit={"reason": reason, "since": store.ts(), "why": why})
            store.event("v4", f"{p['ledger'].upper()} EXIT PENDING {p['ticker']} ({reason}): {why}. No fill until a valid quote.",
                        p["ledger"], p["id"])
        return None
    pend = (p.get("plan") or {}).get("pending_exit")
    r, err = S.close_position(p["id"], px, (pend or {}).get("reason") or reason, fees, qt,
                              extra={"exit_quote_t": qt, "pending_since": (pend or {}).get("since")})
    return r


def overnight(p, now=None):
    """True if p is from an earlier session (the desk was down at the close). Shares and unexpired options are closed
    at the first valid quote with that label; an option that has expired is VOID (excluded from results, for review)."""
    now = now or core.now_et()
    if str(p.get("date")) >= now.strftime("%Y-%m-%d"):
        return False
    exp = [l.get("expiry") for l in p.get("legs") or [] if l.get("expiry")]
    if p["kind"] != "shares" and exp and min(exp) < now.strftime("%Y-%m-%d"):
        S.void(p["id"], f"opened {p['date']}, expired {min(exp)} while the desk was not running at the close: no honest exit price")
        return True
    close_now(p, f"OVERNIGHT: opened {p['date']}, not closed that session (desk down at the close); closed at the next valid quote")
    return True


def retry_pending(p, quotes=None):
    pend = (p.get("plan") or {}).get("pending_exit")
    if pend:
        return close_now(p, pend.get("reason") or "pending exit", quotes)
    return None
