"""noise_variants.py - shared machinery for the v4 noise-band variant ledgers (noise_v2.py, noise_trend.py).

Reuses noiseband.py's band math READ-ONLY (state_at, pick_contract, cfg): the same 14-session sigma profile, the same
bands, the same half-hour checks 10:00-15:00, the same delta 0.55-0.75 contract choice and quantity as the `noise`
ledger. noiseband.py itself is not modified, and the `noise` ledger keeps running unchanged beside these.

What a variant changes is declared in its own module: an entry filter (noise_trend) or the premium exit (noise_v2).
Fills use the noise ledger's exact execution model ("noise1": buy ask + max($0.01, half spread), sell bid - same,
$0.02/contract/side) so a variant differs from `noise` only in its rule. One v4 addition applies to every v4 ledger:
the fill needs an executable quote dated at least the decision latency AFTER the check (retried for up to 5 minutes
after the check, then recorded as missed).

Every half-hour check is recorded in v4_decisions (id <ledger>:<ticker>:<check time>), traded or not, with the bands,
the price, VWAP and the variant's own numbers (e.g. the trend score). A restart re-reads those ids: no check is
decided twice and no entry is taken twice (position id <ledger>:<day>-<ticker>-<side>-<HHMM>).
"""
from datetime import timedelta

import pandas as pd

import core
import marketdata
import noiseband
import store
import v4common as C
import v4exec
import v4risk
import v4store as S

ENTRY_WINDOW_MIN = 5


class Variant:
    ledger = "noise_variant"
    book = "index"
    version = "unset"
    model = "noise1"
    reversal_exit = True                 # noise exits on a signal from the other side at a check

    def entry_filter(self, ticker, st, snap, t_end, now):
        """(allow, info) evaluated at every check with information known at that check only."""
        return True, {}

    def premium_stop(self, fill, slip, fee):
        """Premium level (on the bid) that closes the trade between checks."""
        return core.cents_up(fill * (1 - core.policy()["risk"]["stop_cap_pct"]) + slip + 2 * fee / 100)

    def premium_stop_text(self):
        return "20% planned premium line"


def _check_time(now):
    c = noiseband.cfg()
    t_end = pd.Timestamp(now).floor("30min")
    if now - t_end.to_pydatetime() > timedelta(minutes=ENTRY_WINDOW_MIN) or t_end.strftime("%H:%M") < c.get("first_check", "10:00"):
        return None
    return t_end


def tick(v, ticker, snap, chain_rows_fn, now=None):
    """At each half-hour check: exits by the band rule, the variant's filter (recorded), then the entry attempt."""
    c = noiseband.cfg()
    if ticker not in c.get("tickers", ["SPY", "QQQ"]):
        return None
    now = now or core.now_et()
    t_end = _check_time(now)
    if t_end is None:
        return None
    key = f"{v.ledger}:{ticker}:{t_end.isoformat()}"
    m1 = snap.get("m1")
    if m1 is None or not len(m1):
        return None
    if not S.decided(key):
        st = noiseband.state_at(m1, now.date(), t_end)
        if st is None:
            if (t_end - timedelta(minutes=1)) not in m1.index:
                return None                                   # the check bar hasn't finished yet: next tick
            S.decide(key, v.ledger, ticker, "NO BAND", ["no noise band (needs 10+ full prior sessions)"], {}, "check", v.version)
            return None
        _exits_at_check(v, ticker, st, t_end)
        allow, info = v.entry_filter(ticker, st, snap, t_end, now)
        data = {"t": t_end.isoformat(), "price": st["price"], "upper": st["upper"], "lower": st["lower"], "vwap": st["vwap"],
                "signal": st["signal"], "sigma": st["sigma"], "filter": info, "allow": allow}
        S.decide(key, v.ledger, ticker, "SIGNAL" if st["signal"] else "NO SIGNAL", [], data, "check", v.version)
        store.kv_set(f"{key}:state", data)
    data = store.kv_get(f"{key}:state")
    if not data:
        return None
    _entry_attempt(v, ticker, data, t_end, chain_rows_fn, now)
    return data


def _exits_at_check(v, ticker, st, t_end):
    for p in S.positions(ledger=v.ledger, status="OPEN"):
        if p["ticker"] != ticker:
            continue
        up = p["side"] == "C"
        stop = st["stop_long"] if up else st["stop_short"]
        S.update_plan(p["id"], stop_px=round(stop, 2))
        if (st["price"] < stop) if up else (st["price"] > stop):
            v4exec.close_now(p, f"NOISE STOP at {t_end.strftime('%H:%M')} check: {st['price']:.2f} "
                                f"{'below max' if up else 'above min'}(band, VWAP) {stop:.2f}")
        elif v.reversal_exit and st["signal"] and st["signal"] != p["side"]:
            v4exec.close_now(p, f"NOISE REVERSAL at {t_end.strftime('%H:%M')}: price left the other side of the band")


def _entry_attempt(v, ticker, data, t_end, chain_rows_fn, now):
    c = noiseband.cfg()
    ekey = f"{v.ledger}:{ticker}:{t_end.isoformat()}:entry"
    if S.decided(ekey):
        return
    side = data.get("signal")
    sess = core.session_info(now)

    def final(decision, why, extra=None):
        S.decide(ekey, v.ledger, ticker, decision, [why] if why else [], dict(data, **(extra or {})), "entry", v.version)
        return decision
    if not side:
        return final("NO ENTRY", "no signal at this check")
    if not data.get("allow"):
        return final("FILTERED", "the variant's filter said no (see the check record)")
    if not sess["entries_allowed"] or t_end.strftime("%H:%M") > c.get("last_check", "15:00"):
        return final("NO ENTRY", f"session {sess['state']} / after the last check")
    if [p for p in S.positions(ledger=v.ledger, status="OPEN") if p["ticker"] == ticker]:
        return final("NO ENTRY", "already holding this ticker in this ledger")
    why = v4risk.admit(v.ledger, v.book, ticker, "long" if side == "C" else "short", now)
    if why:
        return final("BLOCKED-RISK", why)
    expired = (pd.Timestamp(now) - t_end).total_seconds() >= ENTRY_WINDOW_MIN * 60 - 15     # the last tick of the window
    rows, err = chain_rows_fn(ticker, side)
    k = noiseband.pick_contract(rows, side)
    if not k:
        return final("SKIP", f"no contract fits delta {c.get('delta_min')}-{c.get('delta_max')} and the spread rule"
                     + (f" ({err})" if err else ""))
    q, qerr = marketdata.option_quote(k["symbol"])
    ok, qwhy = C.quote_after(q, t_end, marketdata.MAX_OPT_QUOTE_AGE_S)
    if not ok:
        if expired:
            return final("MISSED", f"no fresh quote within {ENTRY_WINDOW_MIN} min of the check: {qwhy or qerr}")
        return None                                            # try again next tick
    fill, fee = S.option_buy(q, v.model)
    slip = fill - q["ask"]
    qty = int(c.get("qty", 1))
    pstop = v.premium_stop(fill, slip, fee)
    if pstop >= q["bid"]:
        return final("SKIP", f"the {v.premium_stop_text()} {pstop:.2f} would sit at or above the bid {q['bid']:.2f}")
    pid = f"{v.ledger}:{now.strftime('%Y-%m-%d')}-{ticker}-{side}-{t_end.strftime('%H%M')}"
    rec = {"id": pid, "ledger": v.ledger, "book": v.book, "kind": "option", "date": now.strftime("%Y-%m-%d"), "ticker": ticker,
           "direction": "long" if side == "C" else "short", "side": side, "qty": qty, "entry_px": fill, "entry_t": store.ts(),
           "signal_t": t_end.isoformat(), "quote_t": str(q.get("quote_time")), "fees": round(fee * qty, 4),
           "risk_usd": round((fill - pstop) * 100 * qty + 2 * fee * qty, 2), "max_loss": round(fill * 100 * qty + 2 * fee * qty, 2),
           "legs": [{"symbol": k["symbol"], "label": f"{int(k['symbol'][-8:]) / 1000:g}{side}", "right": side,
                     "strike": int(k["symbol"][-8:]) / 1000, "expiry": now.strftime("%Y-%m-%d"), "action": "buy", "qty": qty}],
           "plan": {"premium_stop": pstop, "premium_stop_rule": v.premium_stop_text(),
                    "stop_px": round(data["upper"] if side == "C" else data["lower"], 2), "entry_underlying": data["price"],
                    "noise_upper": data["upper"], "noise_lower": data["lower"], "vwap": data["vwap"], "bid": q["bid"], "ask": q["ask"],
                    "delta": q.get("delta"), "slippage": round(slip, 4), "filter": data.get("filter"), "contract_delta": k.get("delta")},
           "version": v.version, "exec_model": v.model}
    got, bwhy = S.open_position(rec, f"noise check {t_end.strftime('%H:%M')}")
    return final("ORDER" if got else "SKIP", None if got else bwhy, {"position": got, "fill": fill})


def manage(v, p, now=None):
    """Every engine tick between checks: pending exits first, then all out 15:25, then the premium stop on the bid."""
    now = now or core.now_et()
    if (p.get("plan") or {}).get("pending_exit"):
        return v4exec.retry_pending(p)
    sess = core.session_info(now)
    q, _ = marketdata.option_quote(p["legs"][0]["symbol"])
    if q and q.get("executable") and q.get("bid") is not None:
        mv = (q["bid"] - p["entry_px"]) / p["entry_px"] * 100
        S.mark(p["id"], round(mv, 1), round(mv, 1))
        S.update_plan(p["id"], last_bid=q["bid"], mtm=round((q["bid"] - p["entry_px"]) * 100 * p["qty"] - (p["fees"] or 0), 2))
    if now.strftime("%H:%M") >= sess["all_out"]:
        return v4exec.close_now(p, f"ALL OUT {sess['all_out']} (session rule)")
    ps = (p.get("plan") or {}).get("premium_stop")
    if q and q.get("executable") and ps is not None and q["bid"] <= ps:
        return v4exec.close_now(p, f"PREMIUM STOP ({v.premium_stop_text()}) ${ps:.2f} hit (bid {q['bid']:.2f})")
    return None
