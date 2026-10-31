"""sip_orb.py - v4 stock ledgers in SHARES (docs/STRATEGY_PLAN.md section 4): sip_orb5, sip_orb5_x, sip_orb15,
earn_day, each with an options shadow ledger <name>_opt. PRE-REGISTERED 2026-10-31, unvalidated, paper only.

Source: Zarattini, Barbon & Aziz (2024), "A Profitable Day Trading Strategy for the U.S. Equity Market" (stocks in
play, 5-minute opening-range breakout; 2016-2023, Sharpe 2.81 claimed, 48.4% wins, +0.08R/trade for RV > 100%; no
slippage modeled). Published rules as implemented:
  * Universe: price > $5 (the first candle's close), 14-day average daily volume >= 1,000,000 shares, 14-day ATR
    (Wilder, daily) > $0.50. Candidates = the desk's scanner universe (config/universe.json) + Schwab's top movers
    ($SPX, $COMPX by volume) at the open. (The paper used every US stock; this is a smaller pool - a known limit.)
  * Relative volume RV = volume of the opening candle (09:30-09:35) / the average volume of the same 5 minutes over
    the prior 14 sessions (regular hours only, from Schwab 5-minute history). A symbol without 14 prior sessions of
    opening volume is SKIPPED and counted. Trade the top 20 by RV with RV >= 100%.
  * Direction from the first candle: green -> buy-stop at its high only; red -> sell-stop at its low only; doji
    (close == open to the cent) -> no trade.
  * Stop = 10% of the 14-day ATR from the fill. Otherwise flat at 15:55 ET. One trade per stock per ledger per day.
Ledgers:
  sip_orb5     the rules above (stop-entry, resting from 09:35; simulated on live quotes and finished-bar highs/lows).
  sip_orb5_x   RV >= 5x and ATR >= $2 (stop >= $0.20); entry on the first FINISHED 1m bar that closes beyond the
               candle, filled at the next quote dated after that bar (no resting stop); regular-hours bars only (no
               after-hours prints). Results bucketed by stop size in cents.
  sip_orb15    the paper's 15-minute alternate: candle 09:30-09:45, RV on the same 15 minutes, stop-entry.
  earn_day     sip_orb5_x restricted to the first regular session after an earnings report (an SEC 8-K Item 2.02
               acceptance time recorded by catalysts.py -> earnings.mark_released, or a confirmed date + timing).
Paper fills (shares): buy at the ask + $0.01, sell at the bid - $0.01; a stop-entry never fills better than its level
(buy = max(ask, level) + $0.01); a stop touched between polls (a finished bar's low/high) fills at min(stop, bid) - $0.01
(long). Size = $100 of risk at the stop (shares = floor(100 / stop distance), notional capped at $50,000); R recorded.
Entries until 15:15 ET (the desk's last entry; 12:30 on early-close days), flat 15:55 (12:55 on early-close days).
Every quote used for a fill is fresh (<= 15 s) and dated after the signal.
Options shadow (<ledger>_opt): at each share entry, a contract chosen by the stock-book option rules
(config/qualifying_options.json: qualifying-list names only, ITM |delta| 0.6-0.8, 0-7 DTE, spread <= 10% of mid,
never through a known earnings date; shortest expiry first, then delta nearest 0.70), bought at the ask and sold at the
bid when the share trade exits, $0.65/contract/side. If none qualifies, the reason is recorded.
"""
import json
import math
import threading
import time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

import core
import store
import v4common as C
import v4exec
import v4risk
import v4store as S

VERSION = "2026-11-02.v4-sip1"
SPECS = {
    "sip_orb5": {"book": "stocks", "minutes": 5, "rv_min": 1.0, "atr_min": 0.5, "entry": "stop", "earnings": False},
    "sip_orb5_x": {"book": "stocks", "minutes": 5, "rv_min": 5.0, "atr_min": 2.0, "entry": "close", "earnings": False},
    "sip_orb15": {"book": "stocks", "minutes": 15, "rv_min": 1.0, "atr_min": 0.5, "entry": "stop", "earnings": False},
    "earn_day": {"book": "catalyst", "minutes": 5, "rv_min": 5.0, "atr_min": 2.0, "entry": "close", "earnings": True},
}
UNIVERSE = {"min_price": 5.0, "min_avg_vol": 1_000_000, "min_atr": 0.5}
TOP_N, LOOKBACK, PRERANK_N, MOVERS_N = 20, 14, 60, 10
RISK_USD, STOP_ATR, NOTIONAL_CAP = 100.0, 0.10, 50_000.0
LAST_ENTRY, FLAT = "15:15", "15:55"          # desk session rule; early-close days use the session's times (see _times)
BARS_PER_MIN = 25
CLOSE_FILL_WINDOW_S = 120
QUAL_FILE = core.HERE / "config" / "qualifying_options.json"
_state = {"bars": {}, "bar_tokens": float(BARS_PER_MIN), "bar_t": None, "last_error": None, "status": "idle", "thread": None,
          "stop": False, "last_minute": None, "step_s": None}
_lock = threading.RLock()


def fetch():
    import scanner
    return scanner._fetch


def _times(now):
    """(last entry, flat) for today: 15:15 / 15:55, or the session's early-close last entry / 12:55."""
    s = core.session_info(now)
    return (s["last_entry"], "12:55") if s.get("early_close") else (LAST_ENTRY, FLAT)


def qualifying():
    try:
        d = json.loads(QUAL_FILE.read_text())
        return set(d.get("tickers") or []), d.get("rules") or {}
    except (OSError, ValueError):
        return set(), {}


# ================================================================ pure calculations
def open_volume_history(m5, day, lookback=LOOKBACK):
    """Prior sessions' opening volume from REGULAR-HOURS 5-minute bars: 09:30 bar (5 min) and 09:30+09:35+09:40 (15 min).
    Only sessions before `day` with the needed bars count. Returns {"open5": [...], "open15": [...]} newest last."""
    out = {"open5": [], "open15": []}
    if m5 is None or not len(m5):
        return out
    r = m5[m5.index.date < day]
    for d in sorted(set(r.index.date)):
        g = r[r.index.date == d]
        hm = g.index.strftime("%H:%M")
        v = dict(zip(hm, g["Volume"].astype(float)))
        if "09:30" in v:
            out["open5"].append(v["09:30"])
            if "09:35" in v and "09:40" in v:
                out["open15"].append(v["09:30"] + v["09:35"] + v["09:40"])
    out["open5"], out["open15"] = out["open5"][-lookback:], out["open15"][-lookback:]
    return out


def baseline(daily, m5, day):
    """ATR14 / 14-day average volume / previous close (the scanner's own baseline code, prior days only) plus the 14-day
    AVERAGE opening volumes. A missing piece is None, never estimated."""
    import scanner
    b = scanner.baseline(daily, None, day, 10)
    h = open_volume_history(m5, day)
    out = {"atr14": b.get("atr14"), "avg_vol14": b.get("avg_vol14"), "prev_close": b.get("prev_close"),
           "open5_n": len(h["open5"]), "open15_n": len(h["open15"])}
    out["open5_avg14"] = float(np.mean(h["open5"])) if len(h["open5"]) >= LOOKBACK else None
    out["open15_avg14"] = float(np.mean(h["open15"])) if len(h["open15"]) >= LOOKBACK else None
    return out


def candle(m1_today, minutes, now=None):
    """The opening candle from finished regular-hours 1m bars (all `minutes` bars required)."""
    if m1_today is None or not len(m1_today):
        return None
    m = m1_today if now is None else C.finished(m1_today, now)
    d = m.index[0].date()
    s = pd.Timestamp(datetime.combine(d, datetime.min.time())).tz_localize(core.ET) + timedelta(hours=9, minutes=30)
    w = m[(m.index >= s) & (m.index < s + timedelta(minutes=minutes))]
    if len(w) < minutes:
        return None
    o, c = round(float(w["Open"].iloc[0]), 2), round(float(w["Close"].iloc[-1]), 2)
    return {"open": o, "close": c, "high": float(w["High"].max()), "low": float(w["Low"].min()), "volume": float(w["Volume"].sum()),
            "direction": None if c == o else ("long" if c > o else "short"), "end": (s + timedelta(minutes=minutes)).isoformat()}


def rank(rows, spec):
    """rows: [{ticker, price, avg_vol14, atr14, rv, direction, earnings}] -> (top N by RV, skip counts by reason)."""
    ok, skips = [], {}

    def skip(why):
        skips[why] = skips.get(why, 0) + 1
    for r in rows:
        if r.get("rv") is None:
            skip("no 14-day opening-volume history")
            continue
        if (r.get("price") or 0) <= UNIVERSE["min_price"]:
            skip("price <= $5")
            continue
        if (r.get("avg_vol14") or 0) < UNIVERSE["min_avg_vol"]:
            skip("14-day average volume < 1M")
            continue
        if (r.get("atr14") or 0) <= UNIVERSE["min_atr"] or (r.get("atr14") or 0) < spec["atr_min"]:
            skip(f"ATR14 below ${max(UNIVERSE['min_atr'], spec['atr_min']):.2f}")
            continue
        if spec.get("earnings") and not r.get("earnings"):
            skip("not the first session after an earnings report")
            continue
        if r["rv"] < spec["rv_min"]:
            skip(f"RV under {spec['rv_min']:g}x")
            continue
        if not r.get("direction"):
            skip("doji opening candle")
            continue
        ok.append(r)
    ok.sort(key=lambda r: -r["rv"])
    if len(ok) > TOP_N:
        skips[f"outside the top {TOP_N} by RV"] = len(ok) - TOP_N
    return ok[:TOP_N], skips


def stop_bucket(cents):
    for lo, hi in ((0, 10), (10, 20), (20, 30), (30, 50), (50, 100), (100, 200)):
        if lo <= cents < hi:
            return f"{lo}-{hi - 1}c"
    return "200c+"


def size(fill, stop_dist):
    """(shares, risk_usd): $100 of risk at the stop, notional capped at $50,000."""
    if not stop_dist or stop_dist <= 0 or not fill:
        return 0, 0.0
    q = int(RISK_USD // stop_dist)
    q = min(q, int(NOTIONAL_CAP // fill))
    return q, round(q * stop_dist, 2)


def pick_shadow(rows, direction, now, ticker, spot=None, earnings_date=None, qual=None):
    """Contract for the options shadow, or (None, why)."""
    names, rules = qual if qual is not None else qualifying()
    if ticker not in names:
        return None, "not on the qualifying-options list (config/qualifying_options.json)"
    side = "C" if direction == "long" else "P"
    dmin, dmax, tgt = rules.get("abs_delta_min", 0.6), rules.get("abs_delta_max", 0.8), rules.get("abs_delta_target", 0.7)
    rej, ok = {}, []

    def r_(why):
        rej[why] = rej.get(why, 0) + 1
    for r in rows or []:
        bid, ask, d = r.get("bid") or 0, r.get("ask") or 0, r.get("delta")
        if bid <= 0 or ask <= 0 or ask < bid:
            r_("no two-sided quote")
            continue
        if d is None:
            r_("no delta")
            continue
        if not (dmin <= abs(d) <= dmax):
            r_("delta outside 0.6-0.8")
            continue
        if spot is not None and ((side == "C" and r["strike"] >= spot) or (side == "P" and r["strike"] <= spot)):
            r_("not in the money")
            continue
        exp = date.fromisoformat(r["exp"])
        dte = (exp - now.date()).days
        if not (rules.get("dte_min", 0) <= dte <= rules.get("dte_max", 7)):
            r_("expiry outside 0-7 days")
            continue
        mid = (bid + ask) / 2
        if (ask - bid) / mid > rules.get("max_spread_pct_of_mid", 0.10):
            r_("spread > 10% of mid")
            continue
        if earnings_date and exp >= date.fromisoformat(earnings_date):
            r_("expires on/after the next earnings date")
            continue
        ok.append(dict(r, dte=dte, mid=round(mid, 4), spread_pct=round((ask - bid) / mid, 4)))
    if not ok:
        return None, "no qualifying contract: " + (", ".join(f"{k} {n}" for k, n in sorted(rej.items(), key=lambda z: -z[1])) or "empty chain")
    ok.sort(key=lambda r: (r["dte"], abs(abs(r["delta"]) - tgt)))
    return ok[0], None


def earn_names(day):
    """Tickers whose first regular session after an earnings report is `day` (store only, no network)."""
    import earnings
    out = {}
    try:
        for rec in earnings.cached_calendar():
            t = rec.get("ticker")
            if rec.get("released_at"):
                rel = datetime.fromisoformat(str(rec["released_at"]).replace("Z", "+00:00")).astimezone(core.ET)
                if earnings.next_session_after(rel) == day:
                    out[t] = {"how": "release time (SEC 8-K Item 2.02 / confirmed)", "released_at": rec["released_at"]}
            elif rec.get("status") == "confirmed" and rec.get("timing"):
                tm = str(rec["timing"]).lower()
                d = date.fromisoformat(rec["date"])
                if ("after" in tm and earnings.next_session_after(datetime.combine(d, datetime.min.time(), core.ET).replace(hour=16)) == day) \
                        or ("before" in tm and d == day):
                    out[t] = {"how": f"confirmed date {rec['date']} ({rec['timing']})"}
    except Exception:
        pass
    return out


def next_earnings(ticker, day):
    import earnings
    try:
        for rec in earnings.cached_calendar(days=30):
            if rec.get("ticker") == ticker and rec.get("date") and date.fromisoformat(rec["date"]) > day:
                return rec["date"]
    except Exception:
        pass
    return None


# ================================================================ live: data
def _quote_time(q):
    if q.get("quote_time") is not None:
        return pd.Timestamp(q["quote_time"])
    if q.get("quote_ms"):
        return pd.Timestamp(q["quote_ms"], unit="ms", tz="UTC").tz_convert(core.ET)
    return None


def prepare(day):
    """Before the open: baselines for the scanner universe from Schwab history (prior days only, research priority)."""
    import scanner
    import schwab
    f = fetch()
    base, end = {}, datetime.combine(day, datetime.min.time(), core.ET)
    with schwab.priority("research"):
        for t in scanner.universe():
            if _state["stop"]:
                break
            try:
                base[t] = baseline(f.daily(t), f.m5(t, end - timedelta(days=30), end), day)
            except Exception as e:
                base[t] = {"error": type(e).__name__}
    store.kv_set(f"v4sip_base:{day}", base)
    S.decide(f"sip:base:{day}", "sip", "*", "PREPARED", [], {"tickers": len(base),
             "with_open5_history": sum(1 for b in base.values() if b.get("open5_avg14")),
             "with_open15_history": sum(1 for b in base.values() if b.get("open15_avg14"))}, "data", VERSION)
    return base


def _take_bar_token():
    t = time.time()
    last = _state["bar_t"] or t
    _state["bar_t"] = t
    _state["bar_tokens"] = min(_state["bar_tokens"] + (t - last) * BARS_PER_MIN / 60.0, float(BARS_PER_MIN))
    if _state["bar_tokens"] < 1:
        return False
    _state["bar_tokens"] -= 1
    return True


def bars_today(t, day, now, force=False):
    """Today's finished regular-hours 1m bars, refreshed at most once per minute per symbol (within the bar budget)."""
    minute = now.strftime("%H:%M")
    with _lock:
        hit = _state["bars"].get(t)
    if hit and hit[0] == (str(day), minute) and not force:
        return hit[1]
    if not force and not _take_bar_token():
        return hit[1] if hit else None
    try:
        m1 = fetch().m1_today(t, day)
    except Exception as e:
        _state["last_error"] = f"bars {t}: {type(e).__name__}"
        m1 = None
    if m1 is not None and len(m1):
        m1 = C.finished(m1[m1.index.date == day].between_time("09:30", "15:59"), now)
    with _lock:
        _state["bars"][t] = ((str(day), minute), m1)
    return m1


# ================================================================ live: ranking at the open
def _watch_keys(day):
    return store.kv_get(f"v4sip_watch:{day}") or []


def _wkey(day, led, t):
    return f"v4sip:{day}:{led}:{t}"


def rank_open(day, now, minutes):
    """Rank the stocks in play for every ledger using an opening candle of `minutes` and put them on watch."""
    import schwab
    f = fetch()
    base = store.kv_get(f"v4sip_base:{day}") or {}
    specs = {k: v for k, v in SPECS.items() if v["minutes"] == minutes}
    with schwab.priority("normal"):
        movers = []
        for idx in ("$SPX", "$COMPX"):
            try:
                rows, _ = f.movers(idx, "VOLUME")
                movers += [r["symbol"] for r in rows or [] if r.get("symbol") and r["symbol"] not in base and r["symbol"] not in movers]
            except Exception:
                pass
        end = datetime.combine(day, datetime.min.time(), core.ET)
        for t in movers[:MOVERS_N]:                       # movers outside the universe get a baseline on the fly
            try:
                base[t] = dict(baseline(f.daily(t), f.m5(t, end - timedelta(days=30), end), day), mover=True)
            except Exception as e:
                base[t] = {"error": type(e).__name__, "mover": True}
        tickers = list(base)
        qs, _ = f.quotes(tickers)
        earn = earn_names(day)
        pre = sorted(((float((qs.get(t) or {}).get("volume") or 0) / base[t]["avg_vol14"], t) for t in tickers
                      if (qs.get(t) or {}).get("last") and (base[t] or {}).get("avg_vol14")), reverse=True)
        pick = list(dict.fromkeys([t for _, t in pre[:PRERANK_N]] + [t for t in earn if t in base]))
        rows = []
        avg_key = "open5_avg14" if minutes == 5 else "open15_avg14"
        for t in pick:
            m1 = bars_today(t, day, now, force=True)
            cd = candle(m1, minutes, now)
            b = base.get(t) or {}
            if cd is None:
                continue
            rows.append({"ticker": t, "price": cd["close"], "avg_vol14": b.get("avg_vol14"), "atr14": b.get("atr14"),
                         "rv": round(cd["volume"] / b[avg_key], 3) if b.get(avg_key) else None, "direction": cd["direction"],
                         "candle": cd, "earnings": earn.get(t), "mover": bool(b.get("mover"))})
    store.kv_set(f"v4sip_base:{day}", base)
    keys = _watch_keys(day)
    out = {}
    for led, spec in specs.items():
        top, skips = rank(rows, spec)
        skips["not pre-ranked (outside the top 60 by volume so far)"] = max(0, len(tickers) - len(pick))
        no_hist = sum(1 for t in tickers if not (base.get(t) or {}).get(avg_key))
        S.decide(f"{led}:rank:{day}", led, "*", "RANKED", [], {"minutes": minutes, "universe": len(tickers), "measured": len(rows),
                 "no_open_history": no_hist, "skips": skips, "top": [{k: r.get(k) for k in ("ticker", "rv", "direction", "price", "atr14")}
                                                                   for r in top], "at": now.isoformat()}, "rank", VERSION)
        for i, r in enumerate(top):
            cd = r["candle"]
            st = {"ledger": led, "ticker": r["ticker"], "state": "WAITING", "dir": r["direction"],
                  "level": cd["high"] if r["direction"] == "long" else cd["low"], "candle": cd, "atr14": r["atr14"], "rv": r["rv"],
                  "rank": i + 1, "since": cd["end"], "earnings": r.get("earnings"), "entry": spec["entry"]}
            store.kv_set(_wkey(day, led, r["ticker"]), st)
            if [led, r["ticker"]] not in keys:
                keys.append([led, r["ticker"]])
        out[led] = top
    store.kv_set(f"v4sip_watch:{day}", keys)
    store.kv_set(f"v4sip_ranked:{day}:{minutes}", now.isoformat())
    return out


# ================================================================ live: entries
def _final(day, st, decision, why=None, extra=None):
    st = dict(st, state=decision, why=why, decided_at=store.ts(), **(extra or {}))
    store.kv_set(_wkey(day, st["ledger"], st["ticker"]), st)
    S.decide(f"{st['ledger']}:{day}-{st['ticker']}", st["ledger"], st["ticker"], decision, [why] if why else [],
             {k: st.get(k) for k in ("dir", "level", "rv", "rank", "atr14", "candle", "trigger", "position", "fill")}, "entry", VERSION,
             replace=True)
    return decision


def _equity_q(t, quotes):
    q = dict((quotes or {}).get(t) or {})
    if not q:
        return None
    q["quote_time"] = _quote_time(q)
    q = v4exec.equity_quote(t, {t: q})
    return q


def try_entry(day, now, st, quotes):
    """One watched name in one ledger: detect the trigger, then fill (or record why not)."""
    led, t, spec = st["ledger"], st["ticker"], SPECS[st["ledger"]]
    hm = now.strftime("%H:%M")
    last_entry = _times(now)[0]
    if hm >= last_entry:
        return _final(day, st, "EXPIRED", f"no trigger by {last_entry}")
    m1 = bars_today(t, day, now)
    since = pd.Timestamp(st["since"])
    after = m1[m1.index >= since] if m1 is not None and len(m1) else None
    q = _equity_q(t, quotes)
    up = st["dir"] == "long"
    lvl = st["level"]
    trig = None
    if spec["entry"] == "stop":
        if after is not None and len(after):
            hit = after[after["High"] >= lvl] if up else after[after["Low"] <= lvl]
            if len(hit):
                trig = {"how": "finished bar touched the level", "bar": hit.index[0].isoformat(), "t": (hit.index[0] + pd.Timedelta(minutes=1)).isoformat()}
        if trig is None and q and q.get("last") is not None and ((q["last"] >= lvl) if up else (q["last"] <= lvl)):
            trig = {"how": "last trade at/through the level", "t": str(q.get("quote_time"))}
        if trig is None:
            return None
        signal_t = since
    else:
        if after is None or not len(after):
            return None
        hit = after[after["Close"] > lvl] if up else after[after["Close"] < lvl]
        if not len(hit):
            return None
        bar = hit.index[0]
        signal_t = bar + pd.Timedelta(minutes=1)
        trig = {"how": "finished 1m close beyond the candle", "bar": bar.isoformat(), "close": float(hit["Close"].iloc[0]),
                "t": signal_t.isoformat()}
        if (pd.Timestamp(now) - signal_t).total_seconds() > CLOSE_FILL_WINDOW_S:
            return _final(day, st, "MISSED", f"no fill within {CLOSE_FILL_WINDOW_S}s of the signal bar", {"trigger": trig})
    why = v4risk.admit(led, spec["book"], t, st["dir"], now)
    if why:
        return _final(day, st, "BLOCKED-RISK", why, {"trigger": trig})
    ok, qwhy = C.quote_after(q, signal_t, 15)
    if not ok:
        st["trigger"] = trig
        store.kv_set(_wkey(day, led, t), dict(st, state="TRIGGERED", why=qwhy))
        return None                                                   # wait for a fresh quote dated after the signal
    if spec["entry"] == "stop":
        fill = round(max(q["ask"], lvl) + 0.01, 4) if up else round(min(q["bid"], lvl) - 0.01, 4)
    else:
        fill = S.share_buy(q) if up else S.share_sell(q)
    dist = round(STOP_ATR * st["atr14"], 4)
    qty, risk = size(fill, dist)
    if qty < 1:
        return _final(day, st, "SKIP", f"size 0 (stop distance {dist:.2f})", {"trigger": trig})
    stop = round(fill - dist, 4) if up else round(fill + dist, 4)
    cents = int(round(dist * 100))
    pid = f"{led}:{day}-{t}"
    rec = {"id": pid, "ledger": led, "book": spec["book"], "kind": "shares", "date": str(day), "ticker": t, "direction": st["dir"],
           "side": st["dir"], "qty": qty, "entry_px": fill, "entry_t": store.ts(), "signal_t": pd.Timestamp(signal_t).isoformat(),
           "quote_t": str(q.get("quote_time")), "fees": 0.0, "risk_usd": risk, "max_loss": None,
           "legs": [{"symbol": t, "label": f"{qty} sh", "action": "buy" if up else "sell_short", "qty": qty}],
           "plan": {"stop": stop, "stop_dist": dist, "stop_cents": cents, "stop_bucket": stop_bucket(cents), "level": lvl,
                    "entry_rule": spec["entry"], "trigger": trig, "rv": st["rv"], "rank": st["rank"], "atr14": st["atr14"],
                    "candle": st["candle"], "bid": q["bid"], "ask": q["ask"], "notional": round(fill * qty, 2), "earnings": st.get("earnings")},
           "version": VERSION, "exec_model": "shares1"}
    got, owhy = S.open_position(rec, f"{led} entry ({trig['how']})")
    if not got:
        return _final(day, st, "SKIP", owhy, {"trigger": trig})
    _final(day, st, "ORDER", None, {"trigger": trig, "position": got, "fill": fill})
    try:
        open_shadow(day, now, S.get(got))
    except Exception as e:
        S.decide(f"{led}_opt:{day}-{t}", f"{led}_opt", t, "ERROR", [f"{type(e).__name__}: {e}"[:200]], {}, "entry", VERSION)
    return "ORDER"


def open_shadow(day, now, parent):
    """The options shadow of one share entry (or the recorded reason it has none)."""
    import marketdata
    led, t = f"{parent['ledger']}_opt", parent["ticker"]
    did = f"{led}:{day}-{t}"
    qual = qualifying()
    if t not in qual[0]:
        return S.decide(did, led, t, "NO CONTRACT", ["not on the qualifying-options list (config/qualifying_options.json)"],
                        {"parent": parent["id"]}, "entry", VERSION)
    side = "C" if parent["direction"] == "long" else "P"
    rows, err = fetch().chain(t, side, day.isoformat(), (day + timedelta(days=7)).isoformat(), 20)
    best, why = pick_shadow(rows, parent["direction"], now, t, spot=parent["entry_px"], earnings_date=next_earnings(t, day), qual=qual)
    if not best:
        return S.decide(did, led, t, "NO CONTRACT", [why + (f" ({err})" if err and not rows else "")], {"parent": parent["id"]}, "entry", VERSION)
    q, qerr = marketdata.option_quote(best["symbol"])
    ok, qwhy = C.quote_after(q, parent["signal_t"], marketdata.MAX_OPT_QUOTE_AGE_S)
    if not ok:
        return S.decide(did, led, t, "NO FILL", [f"{best['symbol']}: {qwhy or qerr}"], {"parent": parent["id"]}, "entry", VERSION)
    fill, fee = S.option_buy(q, "bidask065")
    rec = {"id": f"{led}:{day}-{t}", "ledger": led, "book": parent["book"], "kind": "option", "date": str(day), "ticker": t,
           "direction": parent["direction"], "side": side, "qty": 1, "entry_px": fill, "entry_t": store.ts(),
           "signal_t": parent["signal_t"], "quote_t": str(q.get("quote_time")), "fees": fee, "risk_usd": round(fill * 100 + 2 * fee, 2),
           "max_loss": round(fill * 100 + 2 * fee, 2), "parent_id": parent["id"],
           "legs": [{"symbol": best["symbol"], "label": f"{best['strike']:g}{side} {best['exp'][5:]}", "right": side, "strike": best["strike"],
                     "expiry": best["exp"], "action": "buy", "qty": 1}],
           "plan": {"delta": q.get("delta") if q.get("delta") is not None else best.get("delta"), "dte": best["dte"], "bid": q["bid"],
                    "ask": q["ask"], "spread_pct_of_mid": best["spread_pct"], "share_entry": parent["entry_px"], "share_qty": parent["qty"]},
           "version": VERSION, "exec_model": "bidask065"}
    got, owhy = S.open_position(rec, "options shadow of the share entry")
    return S.decide(did, led, t, "ORDER" if got else "SKIP", [] if got else [owhy], {"parent": parent["id"], "position": got}, "entry", VERSION)


# ================================================================ live: exits
def _close_share_at(p, px, reason, qt):
    return S.close_position(p["id"], px, reason, 0.0, qt, extra={"exit_quote_t": qt})


def manage(now, quotes=None):
    """Open share positions and their shadows: pending exits, the stop on live quotes (and on finished-bar touches),
    flat 15:55. Shadows exit when their share trade exits."""
    day = now.date()
    hm = now.strftime("%H:%M")
    flat = _times(now)[1]
    share_leds = list(SPECS)
    for p in S.positions(status="OPEN", ledgers=share_leds):
        q = _equity_q(p["ticker"], quotes) if quotes else None
        if v4exec.overnight(p, now):
            continue
        if (p.get("plan") or {}).get("pending_exit"):
            v4exec.retry_pending(p, {p["ticker"]: q} if q else None)
            continue
        if hm >= flat:
            v4exec.close_now(p, f"FLAT {flat} (session rule)", {p["ticker"]: q} if q else None)
            continue
        pl, up = p["plan"], p["side"] == "long"
        stop = pl["stop"]
        if q and q.get("executable"):
            mark = q["bid"] if up else q["ask"]
            mtm = round(S.pnl(p, mark), 2)
            S.update_plan(p["id"], mtm=mtm, last_mark=mark)
            S.mark(p["id"], mtm, mtm)
            if (q["bid"] <= stop) if up else (q["ask"] >= stop):
                v4exec.close_now(p, f"STOP {stop:.2f} (10% ATR) on the live quote (bid {q['bid']:.2f} / ask {q['ask']:.2f})", {p["ticker"]: q})
                continue
        with _lock:
            hit = _state["bars"].get(p["ticker"])
        m1 = hit[1] if hit else None
        if m1 is not None and len(m1) and q and q.get("executable"):
            after = m1[m1.index + pd.Timedelta(minutes=1) > pd.Timestamp(p["entry_t"])]
            if len(after) and ((after["Low"].min() <= stop) if up else (after["High"].max() >= stop)):
                px = round(min(stop, q["bid"]) - 0.01, 4) if up else round(max(stop, q["ask"]) + 0.01, 4)
                _close_share_at(p, px, f"STOP {stop:.2f} (10% ATR) touched by a finished 1m bar between quotes", str(q.get("quote_time")))
    for p in S.positions(status="OPEN", ledgers=[f"{x}_opt" for x in share_leds]):
        if v4exec.overnight(p, now):
            continue
        if (p.get("plan") or {}).get("pending_exit"):
            v4exec.retry_pending(p)
            continue
        par = S.get(p.get("parent_id")) if p.get("parent_id") else None
        if par is None or par["status"] != "OPEN":
            v4exec.close_now(p, f"share trade exited ({(par or {}).get('exit_reason') or 'parent missing'})")
        elif hm >= flat:
            v4exec.close_now(p, f"FLAT {flat} (session rule)")
        else:
            import marketdata
            q, _ = marketdata.option_quote(p["legs"][0]["symbol"])
            if q and q.get("executable"):
                mtm = round((q["bid"] - p["entry_px"]) * 100 * p["qty"] - (p["fees"] or 0) - 0.65 * p["qty"], 2)
                S.update_plan(p["id"], mtm=mtm, last_bid=q["bid"])
                S.mark(p["id"], mtm, mtm)


# ================================================================ worker
def watching(day):
    out = []
    for led, t in _watch_keys(day):
        st = store.kv_get(_wkey(day, led, t))
        if st and st.get("state") in ("WAITING", "TRIGGERED"):
            out.append(st)
    return out


def step(now=None):
    now = now or core.now_et()
    t0 = time.time()
    day = now.date()
    sess = core.session_info(now)
    if sess.get("holiday") or now.weekday() >= 5:
        _state["status"] = "market closed"
        return
    f = fetch()
    if not f.ready():
        _state["status"] = "waiting for Schwab (no decisions on delayed data)"
        return
    import schwab
    hm = now.strftime("%H:%M")
    opens = S.positions(status="OPEN", ledgers=list(SPECS))
    w = watching(day) if "09:35" <= hm < "16:00" else []
    syms = sorted({p["ticker"] for p in opens} | {s["ticker"] for s in w})
    quotes = {}
    last_q = _state.get("q_t")
    if syms and not opens and last_q is not None and 0 <= (now - last_q).total_seconds() < 9:
        syms = []                                                   # watch-only: quotes every 10 s (rate budget)
    if syms:
        _state["q_t"] = now
        with schwab.priority("risk" if opens else "normal"):
            try:
                quotes, _ = f.quotes(syms)
            except Exception as e:
                _state["last_error"] = f"quotes: {type(e).__name__}"
    with schwab.priority("risk"):                                    # protect open trades first
        try:
            manage(now, quotes)
        except Exception as e:
            _state["last_error"] = f"manage: {type(e).__name__}: {e}"[:200]
    if "08:30" <= hm < "15:30" and not store.kv_get(f"v4sip_base:{day}"):
        _state["status"] = "preparing baselines"
        prepare(day)
    if sess["state"] not in ("ORB FORMING", "OPEN", "NO NEW ENTRIES"):
        _state["status"] = sess["state"]
        return
    for minutes, due, late in ((5, "09:35", "09:50"), (15, "09:45", "10:00")):
        if store.kv_get(f"v4sip_ranked:{day}:{minutes}") or hm < due or (hm == due and now.second < 20):
            continue
        if hm >= late:
            for led in [k for k, v in SPECS.items() if v["minutes"] == minutes]:
                S.decide(f"{led}:rank:{day}", led, "*", "NOT RANKED", [f"the desk was not ready by {late}"], {}, "rank", VERSION)
            store.kv_set(f"v4sip_ranked:{day}:{minutes}", "skipped")
            continue
        if store.kv_get(f"v4sip_base:{day}"):
            _state["status"] = f"ranking ({minutes}-minute candle)"
            rank_open(day, now, minutes)
    with schwab.priority("normal"):
        w = sorted(watching(day), key=lambda s: (s["entry"] != "close", s["rank"]))      # bar-close entries first
        for st in w:
            try:
                try_entry(day, now, st, quotes)
            except Exception as e:
                _state["last_error"] = f"entry {st['ledger']} {st['ticker']}: {type(e).__name__}: {e}"[:200]
    _state["status"] = "watching" if w else "running"
    _state["step_s"] = round(time.time() - t0, 2)


def _run():
    while not _state["stop"]:
        try:
            step()
            try:
                import health
                health.beat("v4stocks", True, _state.get("status"), _state.get("step_s"))
            except Exception:
                pass
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {e}"[:200]
        try:                                       # v4 news-drift event logger (research priority, never trades)
            import news_drift
            if core.session_info()["state"] not in ("CLOSED", "CLOSED (holiday/weekend)"):
                news_drift.step()
        except Exception as e:
            _state["last_error"] = f"news_drift: {type(e).__name__}: {e}"[:200]
        time.sleep(5)


def start():
    if _state["thread"]:
        return False
    th = threading.Thread(target=_run, daemon=True, name="v4stocks")
    _state["thread"] = th
    th.start()
    return True


def status():
    day = core.now_et().date()
    return {"version": VERSION, "status": _state["status"], "last_error": _state["last_error"], "step_s": _state["step_s"],
            "prepared": bool(store.kv_get(f"v4sip_base:{day}")), "ranked_5": store.kv_get(f"v4sip_ranked:{day}:5"),
            "ranked_15": store.kv_get(f"v4sip_ranked:{day}:15"), "watching": len(watching(day)), "specs": SPECS,
            "qualifying": sorted(qualifying()[0])}
