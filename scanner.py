"""scanner.py - the stocks-in-play scanner and the 'inplay' research ledger (paper only, Schwab data only).

Idea (Zarattini, Barbon & Aziz, "A Profitable Day Trading Strategy for the U.S. Equity Market", 2016-2023, SHARES):
the 5-minute opening-range breakout worked on "stocks in play" (the day's top 20 by opening relative volume), not on
the broad market. Their filters: price > $5, 14-day average volume >= 1M shares, 14-day ATR > $0.50, opening-range
relative volume >= 100%, top 20. Trade in the direction of the first 5-minute candle when price breaks that candle's
high (long) or low (short), stop 10% of ATR from the entry, otherwise flat at the close.
What is different here, on purpose and labeled:
  * the desk trades OPTIONS on paper. A share-based edge says nothing about an option edge after spreads and
    decay, so every trade records the stock move and the option result separately;
  * entries need a finished 1m close beyond the range (the desk's no-intrabar rule), not a resting stop order;
    like the paper they can start right after the 5-minute range (09:36), before the desk's own 09:45 SPY/QQQ start;
  * option liquidity is checked contract by contract across expirations (spread, quote age, volume, open interest,
    delta, time decay over the expected hold, earnings before expiry). The nearest expiry is not assumed;
  * the desk's 20% planned premium-loss ceiling and all-out 15:25 still apply; price >= $20 (single-stock option
    spreads are unusable on cheap names).
Passing is a valid result: if nothing qualifies, nothing is traded.

Data: Schwab only (quotes, movers, price history, option chains). When Schwab isn't connected the scanner waits and
says so; it never falls back to delayed data for decisions. Earnings dates come from Yahoo's calendar (unofficial,
labeled) because Schwab's market-data API has no earnings calendar.
API budget: one baseline pass before the open (2 calls per ticker), about 60 calls at 09:35, then one call per
watched name per minute, all inside the shared Schwab rate limit in schwab.py.
"""
import json
import math
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

import alerts
import core
import indicators as I
import marketdata
import paper
import store

VERSION = "2026-10-30.v3.1-inplay"
SCHEMA = """CREATE TABLE IF NOT EXISTS scan_rows(date TEXT, ticker TEXT, rank INTEGER, status TEXT, data TEXT, updated TEXT,
  PRIMARY KEY(date, ticker))"""
_state = {"thread": None, "stop": False, "status": "idle", "last_error": None, "cache": {}, "last_minute": None}
_lock = threading.RLock()


def cfg():
    return core.policy().get("scanner") or {}


def vcfg():
    return (core.policy().get("research_variants") or {}).get("inplay") or {}


def universe():
    try:
        return json.loads((core.HERE / cfg().get("universe_file", "config/universe.json")).read_text())["tickers"]
    except Exception:
        return []


# ---------------------------------------------------------------- data access (Schwab; tests inject a fake)
class SchwabFetch:
    """Market data only, through schwab.py (rate limited)."""

    def ready(self):
        import schwab
        return schwab.ready()

    def daily(self, t):
        import schwab
        return schwab.bars_daily(t)

    def m5(self, t, start, end):
        import schwab
        return schwab.bars_range(t, start, end, 5)

    def m1_today(self, t, day):
        import schwab
        s = datetime.combine(day, datetime.min.time(), core.ET).replace(hour=9, minute=30)
        return schwab.bars_range(t, s, s.replace(hour=16), 1)

    def quotes(self, ts):
        import schwab
        return schwab.quotes_full(ts)

    def m1_ext(self, t, day, now):
        """Today's 1m bars from 04:00 (pre-market included) to now: for the setups board."""
        import schwab
        s = datetime.combine(day, datetime.min.time(), core.ET).replace(hour=4)
        return schwab.bars_range(t, s, now + timedelta(minutes=1), 1, extended=True)

    def movers(self, index, sort):
        import schwab
        return schwab.movers(index, sort)

    def chain(self, t, side, first, through, strikes):
        import schwab
        return schwab.chain(t, side, first, through, strikes)

    def earnings(self, t):
        try:
            import watchlist
            e = watchlist.earnings(t)
            return (e or {}).get("date"), "Yahoo calendar (unofficial)"
        except Exception:
            return None, "unknown"


_fetch = SchwabFetch()


def use(fetcher):
    global _fetch
    _fetch = fetcher or SchwabFetch()
    with _lock:
        _state["cache"] = {}


# ---------------------------------------------------------------- pure calculations (shared with the backtest)
def baseline(daily, m5, day, sessions=10):
    """ATR14 (Wilder), 14-day average volume, previous close, and the median first-5-minute volume over the last
    `sessions` sessions. Only data from BEFORE `day` is used."""
    out = {"atr14": None, "avg_vol14": None, "prev_close": None, "open5_med": None, "open5_n": 0,
           "pdh": None, "pdl": None, "tod_cum": None, "tod_n": 0}
    if daily is not None and len(daily):
        d = daily[[pd.Timestamp(x).date() < day for x in daily.index]]
        if len(d):
            out["pdh"], out["pdl"] = float(d["High"].iloc[-1]), float(d["Low"].iloc[-1])
            out["prev_close"] = float(d["Close"].iloc[-1])
        if len(d) >= 15:
            a = I.atr(d, 14)
            out["atr14"] = round(float(a.iloc[-1]), 4) if a.iloc[-1] == a.iloc[-1] else None
            out["avg_vol14"] = float(d["Volume"].iloc[-14:].mean())
    if m5 is not None and len(m5):
        first = m5[(m5.index.hour == 9) & (m5.index.minute == 30) & (m5.index.date < day)]
        vols = list(first["Volume"].iloc[-sessions:])
        out["open5_n"] = len(vols)
        if len(vols) >= max(5, sessions // 2):
            out["open5_med"] = float(np.median(vols))
        out["tod_cum"], out["tod_n"] = tod_profile(m5, day, sessions)
    return out


def tod_profile(m5, day, sessions=10):
    """Time-of-day volume profile: for each 5-minute slot of the regular session, the MEDIAN cumulative volume from
    09:30 through the end of that slot over the last `sessions` prior sessions. {"09:30": v, "09:35": v, ...}."""
    r = m5[(m5.index.date < day)]
    r = r[[("09:30" <= i.strftime("%H:%M") <= "15:55") for i in r.index]]
    days = sorted(set(r.index.date))[-sessions:]
    if len(days) < max(5, sessions // 2):
        return None, len(days)
    cums = []
    for d in days:
        x = r[r.index.date == d]["Volume"]
        x.index = [i.strftime("%H:%M") for i in x.index]
        cums.append(x.cumsum())
    df = pd.DataFrame(cums)
    return {k: float(np.median(df[k].dropna())) for k in df.columns if df[k].notna().sum() >= max(3, len(days) // 2)}, len(days)


def opening_range(m1_day, minutes=5):
    """First N minutes of the session (all N bars required): high, low, volume, direction of the candle."""
    if m1_day is None or not len(m1_day):
        return None
    d = m1_day.index[0].date()
    s = pd.Timestamp(datetime.combine(d, datetime.min.time()), tz=core.ET) + timedelta(hours=9, minutes=30)
    w = m1_day[(m1_day.index >= s) & (m1_day.index < s + timedelta(minutes=minutes))]
    if len(w) < minutes:
        return None
    o, c = float(w["Open"].iloc[0]), float(w["Close"].iloc[-1])
    hi, lo = float(w["High"].max()), float(w["Low"].min())
    doji = abs(c - o) < 0.05 * max(hi - lo, 1e-9)
    return {"high": hi, "low": lo, "open": o, "close": c, "volume": float(w["Volume"].sum()),
            "direction": None if doji else ("C" if c > o else "P"), "end": (s + timedelta(minutes=minutes)).isoformat()}


def rank_in_play(rows, c=None):
    """rows: [{ticker, price, avg_vol14, atr14, rvol, ...}] -> (qualified top N sorted by RVOL, rejected with reasons)."""
    c = c or cfg()
    ok, bad = [], []
    for r in rows:
        why = []
        if (r.get("price") or 0) < c.get("min_price", 20):
            why.append(f"price under ${c.get('min_price', 20)}")
        if (r.get("avg_vol14") or 0) < c.get("min_avg_vol", 1_000_000):
            why.append("average volume under 1M")
        if (r.get("atr14") or 0) < c.get("min_atr", 0.5):
            why.append("daily range (ATR) under $0.50")
        if r.get("rvol") is None:
            why.append("no opening-volume baseline")
        elif r["rvol"] < c.get("rvol_min", 1.0):
            why.append(f"opening volume {r['rvol']:.1f}x normal (needs {c.get('rvol_min', 1.0):.1f}x)")
        if not r.get("direction"):
            why.append("first candle had no direction (doji)")
        (bad if why else ok).append(dict(r, reasons=why))
    ok.sort(key=lambda r: -r["rvol"])
    top = ok[:c.get("top_n", 20)]
    for r in ok[c.get("top_n", 20):]:
        bad.append(dict(r, reasons=[f"not in the top {c.get('top_n', 20)} by opening volume"]))
    return top, bad


def score_contracts(rows, side, now, earnings=None, c=None):
    """Every contract checked on spread, quote age, volume, open interest, delta, premium, expiry and time decay over
    the expected hold. Returns (best or None, top 5, rejection counts). Lower cost = better."""
    c = c or cfg().get("contract") or {}
    out, rej = [], Counter()
    today = now.date()
    for r in rows or []:
        bid, ask, d = r.get("bid") or 0, r.get("ask") or 0, r.get("delta")
        if bid <= 0 or ask <= 0 or ask < bid:
            rej["no two-sided quote"] += 1
            continue
        mid = (bid + ask) / 2
        if d is None:
            rej["no delta"] += 1
            continue
        if not (c.get("delta_min", 0.5) <= abs(d) <= c.get("delta_max", 0.7)):
            rej["delta outside range"] += 1
            continue
        if not (c.get("premium_min", 0.3) <= mid <= c.get("premium_max", 8.0)):
            rej["premium outside range"] += 1
            continue
        sp = (ask - bid) / mid
        if sp > c.get("max_spread_pct", 0.05):
            rej["spread too wide"] += 1
            continue
        ts = r.get("ts")
        age = (now - datetime.fromisoformat(ts)).total_seconds() if ts else None
        if age is None or age > c.get("max_quote_age_s", 20):
            rej["stale or missing quote time"] += 1
            continue
        if (r.get("oi") or 0) < c.get("min_oi", 500):
            rej["open interest too low"] += 1
            continue
        if (r.get("volume") or 0) < c.get("min_volume", 100):
            rej["too little volume today"] += 1
            continue
        exp = date.fromisoformat(r["exp"])
        dte = (exp - today).days
        if dte < 0 or dte > c.get("max_dte", 10):
            rej["expiry outside 0-10 days"] += 1
            continue
        if earnings and exp >= date.fromisoformat(earnings):
            rej["expires after earnings"] += 1
            continue
        th = abs(r.get("theta") or 0)
        decay = th * c.get("hold_min_est", 120) / 390.0 / mid       # approximation: daily theta spread over the session
        out.append(dict(r, mid=round(mid, 3), spread_pct=round(sp, 4), quote_age_s=round(age, 1), dte=dte,
                        decay_pct=round(decay, 4), cost=round(sp + decay, 4)))
    out.sort(key=lambda x: (x["cost"], -(x.get("oi") or 0)))
    return (out[0] if out else None), out[:5], dict(rej)


def orb_trigger(m1_day, orr, now_bar_end, side):
    """First finished 1m close beyond the opening range in the first candle's direction, after the range ends.
    Returns (bar_open_ts, close) or None. Looks only at bars that have finished by now_bar_end."""
    if orr is None or not side:
        return None
    w = m1_day[(m1_day.index >= pd.Timestamp(orr["end"])) & (m1_day.index + timedelta(minutes=1) <= now_bar_end)]
    hit = w[w["Close"] > orr["high"]] if side == "C" else w[w["Close"] < orr["low"]]
    return (hit.index[0], float(hit["Close"].iloc[0])) if len(hit) else None


def quick_move(m1_day, atr14, avg_vol14, c=None):
    """A sharp 5-minute move on heavy volume: |move| >= atr_frac x ATR14 and volume >= vol_mult x a normal 5 minutes."""
    c = (c or cfg()).get("quick_move") or {}
    if m1_day is None or len(m1_day) < 6 or not atr14 or not avg_vol14:
        return None
    if m1_day.index[-1].strftime("%H:%M") < c.get("from", "09:45"):
        return None                                   # the opening minutes are always heavy: no quick-move alerts yet
    w = m1_day.iloc[-5:]
    mv = float(w["Close"].iloc[-1] - m1_day["Close"].iloc[-6])
    vol = float(w["Volume"].sum())
    normal = avg_vol14 / 78.0
    pct = abs(mv) / float(m1_day["Close"].iloc[-6]) * 100
    if abs(mv) >= c.get("atr_frac", 0.25) * atr14 and vol >= c.get("vol_mult", 2.0) * normal and pct >= c.get("pct_min", 1.0) / 2:
        return {"move": round(mv, 2), "pct": round(mv / float(m1_day["Close"].iloc[-6]) * 100, 2), "vol_x": round(vol / normal, 1),
                "since": m1_day.index[-6].strftime("%H:%M")}
    return None


def idea_for(m1_day, orr):
    """Plain-words idea for an alert (NOT a validated setup): where price sits vs VWAP and the opening range."""
    if m1_day is None or not len(m1_day):
        return "no data"
    px = float(m1_day["Close"].iloc[-1])
    vw = I.last(I.session_vwap(m1_day))
    if orr and vw is not None:
        if px > vw and px > orr["high"]:
            return f"trending up above VWAP {vw:.2f} and the opening range: idea = long on a pullback that holds VWAP"
        if px < vw and px < orr["low"]:
            return f"trending down below VWAP {vw:.2f} and the opening range: idea = short on a bounce that fails at VWAP"
        return f"inside its range around VWAP {vw:.2f}: idea = wait for a clean break"
    return "no opening range yet"


# ---------------------------------------------------------------- live workflow
def _rows(day):
    store.x(SCHEMA)
    return [dict(json.loads(r["data"]), rank=r["rank"], status=r["status"], updated=r["updated"])
            for r in store.q("SELECT * FROM scan_rows WHERE date=? ORDER BY rank", (day,))]


def _save_row(day, r):
    store.x(SCHEMA)
    store.x("INSERT OR REPLACE INTO scan_rows(date,ticker,rank,status,data,updated) VALUES(?,?,?,?,?,?)",
            (day, r["ticker"], r.get("rank", 999), r.get("status", ""), json.dumps(r, default=str), store.ts()))


def prepare(day):
    """Before the open: baselines for the universe from Schwab history (prior days only)."""
    base = {}
    end = datetime.combine(day, datetime.min.time(), core.ET)
    start = end - timedelta(days=21)
    for t in universe():
        if _state["stop"]:
            break
        try:
            b = baseline(_fetch.daily(t), _fetch.m5(t, start, end), day, cfg().get("baseline_sessions", 10))
        except Exception as e:
            b = {"error": type(e).__name__}
        base[t] = b
    store.kv_set(f"scan_base:{day}", base)
    store.event("scanner", f"SCANNER ready for {day}: baselines for {sum(1 for b in base.values() if b.get('open5_med'))} "
                f"of {len(base)} tickers", "scanner")
    return base


def scan(day, now):
    """09:35: rank today's stocks in play. Saves every considered ticker with its numbers and reasons."""
    c = cfg()
    base = store.kv_get(f"scan_base:{day}") or prepare(day)
    tickers = list(base)
    extra = []
    for idx in c.get("movers_indexes", ["$SPX", "$COMPX"]):
        try:
            rows, _ = _fetch.movers(idx, "VOLUME")
            extra += [r["symbol"] for r in rows or [] if r.get("symbol") and r["symbol"] not in tickers]
        except Exception:
            pass
    for t in extra[:10]:                                # movers outside the list get a baseline on the fly
        end = datetime.combine(day, datetime.min.time(), core.ET)
        try:
            base[t] = baseline(_fetch.daily(t), _fetch.m5(t, end - timedelta(days=21), end), day, c.get("baseline_sessions", 10))
            tickers.append(t)
        except Exception:
            pass
    qs, _ = _fetch.quotes(tickers)
    pre = []
    for t in tickers:
        q, b = qs.get(t) or {}, base.get(t) or {}
        if not q.get("last") or not b.get("avg_vol14"):
            continue
        pre.append((float(q.get("volume") or 0) / b["avg_vol14"], t))
    pre.sort(reverse=True)
    rows = []
    for _, t in pre[:c.get("prerank_n", 60)]:
        b, q = base[t], qs[t]
        m1 = _fetch.m1_today(t, day)
        orr = opening_range(m1, vcfg().get("or_min", 5))
        rvol = round(orr["volume"] / b["open5_med"], 2) if orr and b.get("open5_med") else None
        rows.append({"ticker": t, "price": q["last"], "gap_pct": round((q["open"] / b["prev_close"] - 1) * 100, 2) if q.get("open") and b.get("prev_close") else None,
                     "change_pct": round((q["last"] / b["prev_close"] - 1) * 100, 2) if b.get("prev_close") else None,
                     "atr14": b.get("atr14"), "avg_vol14": b.get("avg_vol14"), "rvol": rvol, "direction": (orr or {}).get("direction"),
                     "or_high": (orr or {}).get("high"), "or_low": (orr or {}).get("low"), "or_end": (orr or {}).get("end"),
                     "mover": t in extra, "prev_close": b.get("prev_close")})
        with _lock:
            _state["cache"][t] = {"m1": m1, "orr": orr, "base": b}
    top, bad = rank_in_play(rows, c)
    for i, r in enumerate(top):
        e, src = _fetch.earnings(r["ticker"])
        r.update(rank=i + 1, status="watching", earnings=e, earnings_src=src)
        _save_row(day, r)
    for r in bad[:40]:
        r.update(rank=900, status="not in play: " + "; ".join(r["reasons"][:2]))
        _save_row(day, r)
    store.kv_set(f"scan_done:{day}", now.isoformat())
    if top:
        alerts.alert("movers", f"IN PLAY {now.strftime('%H:%M')}: " + ", ".join(f"{r['ticker']} {r['rvol']:.1f}x" for r in top[:5]),
                     " | ".join(f"{r['ticker']} {'up' if r['direction'] == 'C' else 'down'} first 5 min, range {r['or_low']:.2f}-{r['or_high']:.2f}, "
                                f"{'gap ' + format(r['gap_pct'], '+.1f') + '%' if r.get('gap_pct') is not None else ''}" for r in top[:5]) +
                     " | scanner ideas, not validated setups", f"inplay:{day}")
    else:
        store.event("scanner", f"SCANNER {now.strftime('%H:%M')}: nothing in play passed the filters today. Passing is fine.", "scanner")
    return top, bad


def pulse(day, now, qs=None):
    """Every minute, the whole universe in 2 batched quote calls: a QUICK MOVE alert when a name moves
    >= quick_move.pct_min % and >= atr_frac x its ATR in about 5 minutes on >= vol_mult x normal 5-minute volume.
    Covers names that weren't in play at 09:35. Uses the change in Schwab's cumulative day volume between snapshots."""
    c = cfg().get("quick_move") or {}
    base = store.kv_get(f"scan_base:{day}") or {}
    if qs is None:
        qs, _ = _fetch.quotes(list(base))
    if now.strftime("%H:%M") < c.get("from", "09:45"):
        return []
    hist = _state.setdefault("pulse", {})
    watched = {r["ticker"] for r in _rows(day) if r["status"].startswith(("watching", "triggered", "traded"))}
    fired = []
    for t, q in (qs or {}).items():
        if not q.get("last") or q.get("volume") is None:
            continue
        h = hist.setdefault(t, [])
        h.append((now, float(q["last"]), float(q["volume"])))
        while h and (now - h[0][0]).total_seconds() > 6 * 60:
            h.pop(0)
        if t in watched or len(h) < 2 or (now - h[0][0]).total_seconds() < 4 * 60:
            continue                                   # watched names use their 1m bars in on_minute
        b = base.get(t) or {}
        t0, p0, v0 = h[0]
        mv, dv = h[-1][1] - p0, h[-1][2] - v0
        normal = (b.get("avg_vol14") or 0) / 78.0
        if not b.get("atr14") or normal <= 0:
            continue
        pct = mv / p0 * 100
        if abs(pct) >= c.get("pct_min", 1.0) and abs(mv) >= c.get("atr_frac", 0.25) * b["atr14"] and dv >= c.get("vol_mult", 2.0) * normal:
            last = store.kv_get(f"qm_last:{t}")
            if last and (now - datetime.fromisoformat(last)).total_seconds() < c.get("cooldown_min", 20) * 60:
                continue
            store.kv_set(f"qm_last:{t}", now.isoformat())
            fired.append(t)
            alerts.alert("moves", f"QUICK MOVE {t} {pct:+.2f}% in {round((now - t0).total_seconds() / 60)} min",
                         f"{mv:+.2f} to {h[-1][1]:.2f} on {dv / normal:.1f}x normal volume | not in this morning's in-play list | "
                         f"idea: wait for the first pullback to hold, or ask Chart for a plan | scanner idea, not a validated setup",
                         f"qm:{t}:{now.strftime('%H%M')}")
    return fired


def on_minute(day, now):
    """Each minute after the scan: refresh watched names, alert quick moves, take qualified ORB triggers on paper."""
    v = vcfg()
    try:
        pulse(day, now)
    except Exception as e:
        _state["last_error"] = f"pulse: {type(e).__name__}"
    sess = core.session_info(now)
    end_ts = pd.Timestamp(now).floor("1min")
    for r in [x for x in _rows(day) if x["status"].startswith(("watching", "triggered", "traded"))]:
        t = r["ticker"]
        m1 = _fetch.m1_today(t, day)
        if m1 is None or not len(m1):
            continue
        m1 = m1[m1.index + timedelta(minutes=1) <= end_ts]      # finished bars only
        if len(m1):
            last = float(m1["Close"].iloc[-1])
            prev = r.get("prev_close")
            r["price"], r["change_pct"] = round(last, 2), (round((last / prev - 1) * 100, 2) if prev else r.get("change_pct"))
            _save_row(day, r)
        with _lock:
            ent = _state["cache"].setdefault(t, {})
            ent.update(m1=m1)
        qm = quick_move(m1, r.get("atr14"), r.get("avg_vol14"))
        if qm and not store.kv_get(f"qm:{t}:{day}:{qm['since']}"):
            last = store.kv_get(f"qm_last:{t}")
            if not last or (now - datetime.fromisoformat(last)).total_seconds() > cfg().get("quick_move", {}).get("cooldown_min", 20) * 60:
                store.kv_set(f"qm_last:{t}", now.isoformat())
                store.kv_set(f"qm:{t}:{day}:{qm['since']}", True)
                alerts.alert("moves", f"QUICK MOVE {t} {qm['pct']:+.2f}% in 5 min",
                             f"{qm['move']:+.2f} since {qm['since']}, volume {qm['vol_x']}x a normal 5 minutes | "
                             f"{idea_for(m1, (ent or {}).get('orr'))} | scanner idea, not a validated setup", f"qm:{t}:{now.strftime('%H%M')}")
        hm = now.strftime("%H:%M")
        window = sess["state"] in ("ORB FORMING", "OPEN") and v.get("first_entry", "09:36") <= hm <= v.get("last_entry", "15:15")
        if not r["status"].startswith("watching") or not window or not store.kv_get("paper_enabled", True) or not v.get("enabled", True):
            continue
        orr = {"high": r["or_high"], "low": r["or_low"], "end": r["or_end"]} if r.get("or_high") else None
        trig = orb_trigger(m1, orr, end_ts, r.get("direction"))
        if not trig:
            continue
        _take(day, now, r, trig)


def _take(day, now, r, trig):
    v, side, t = vcfg(), r["direction"], r["ticker"]
    import retire
    if retire.is_retired("inplay"):                    # v4: retired; the scanner still ranks and alerts
        r.update(status=f"triggered {trig[0].strftime('%H:%M')}, not traded: inplay ledger retired in v4")
        _save_row(day, r)
        return
    bar_ts, px = trig
    e = r.get("earnings")
    if e and date.fromisoformat(e) < day:
        e = None                    # a report that already happened is why it's in play, not a future event risk
    rows, err = _fetch.chain(t, side, day.isoformat(), (day + timedelta(days=cfg().get("contract", {}).get("max_dte", 10))).isoformat(),
                             cfg().get("contract", {}).get("strike_count", 16))
    best, top5, rej = score_contracts(rows, side, now, e)
    r["contracts_checked"] = len(rows or [])
    r["contract_rejections"] = rej
    if not best:
        r.update(status="triggered, no tradable contract: " + (", ".join(f"{k} {n}" for k, n in sorted(rej.items(), key=lambda z: -z[1])[:3]) or err or "empty chain"))
        _save_row(day, r)
        return
    r["contract"] = {k: best.get(k) for k in ("symbol", "exp", "strike", "bid", "ask", "mid", "delta", "theta", "iv", "oi", "volume",
                                             "spread_pct", "quote_age_s", "dte", "decay_pct", "cost")}
    opens = store.positions(ledger="inplay", status="OPEN")
    if len(opens) >= v.get("max_open", 6):
        r.update(status=f"triggered {bar_ts.strftime('%H:%M')}, limit: {len(opens)} in-play trades already open")
        _save_row(day, r)
        return
    stop_px = round(px - v.get("stop_atr_frac", 0.10) * r["atr14"] if side == "C" else px + v.get("stop_atr_frac", 0.10) * r["atr14"], 2)
    slip, fee = paper.costs(best["ask"] - best["bid"])
    idea = f"{day}-{t}-{side}-INPLAY"
    ok, why = paper.reserve_idea("inplay", idea, t, side)
    if not ok:
        return
    plan = {"symbol": best["symbol"], "label": f"{best['strike']:g}{side} {best['exp'][5:]}", "family": "INPLAY_ORB",
            "premium_stop": core.cents_up(best["ask"] * (1 - core.policy()["risk"]["stop_cap_pct"]) + slip + 2 * fee / 100),
            "stop_px": stop_px, "t1": None, "t1_level": None, "t1_px": None, "be_trigger": None,
            "breakeven_net": core.cents_up(best["ask"] + slip + 2 * fee / 100), "flat_by": None, "exit_profile": "inplay",
            "variant": "inplay", "policy_version": VERSION, "entry_px": px, "orb_high": r["or_high"], "orb_low": r["or_low"],
            "atr14": r["atr14"], "rvol": r["rvol"], "contract_score": best["cost"], "expiry": best["exp"], "grade": "R", "v": 31}
    pid, bwhy = paper.buy("inplay", idea, t, side, plan, int(v.get("qty", 1)), bar_ts.isoformat())
    if not pid:
        paper.release_idea("inplay", idea, bwhy)
        r.update(status=f"triggered, no fill: {bwhy}")
        _save_row(day, r)
        return
    r.update(status=f"traded {bar_ts.strftime('%H:%M')} (paper)", position_id=pid)
    _save_row(day, r)
    alerts.alert("scanner", f"IN PLAY {t} {'calls' if side == 'C' else 'puts'}: {'above' if side == 'C' else 'below'} the opening range",
                 f"1m close {px:.2f} {'over' if side == 'C' else 'under'} {r['or_high'] if side == 'C' else r['or_low']:.2f} | opening volume {r['rvol']:.1f}x | "
                 f"stop {stop_px:.2f} (10% of ATR) | contract {t} {best['strike']:g}{side} exp {best['exp']} delta {abs(best['delta']):.2f}, "
                 f"bid {best['bid']:.2f}/ask {best['ask']:.2f} (spread {best['spread_pct'] * 100:.1f}%), OI {best.get('oi')} | "
                 f"paper research trade, not a validated system setup", f"inplay-take:{idea}", "high")


def manage(p):
    """In-play paper positions: all out 15:25, the 20% premium ceiling, the 10%-ATR stop on a finished 1m close."""
    now = core.now_et()
    sess = core.session_info(now)
    pl = p["plan"]
    q, err = marketdata.option_quote(p["symbol"])
    if q and q.get("executable"):
        pl["last_bid"] = q["bid"]
        mv = (q["bid"] - p["fill"]) / p["fill"] * 100
        p["mfe"], p["mae"] = round(max(p["mfe"] or 0, mv), 1), round(min(p["mae"] or 0, mv), 1)
        store.pos_save(p)
    if now.strftime("%H:%M") >= sess["all_out"]:
        return paper.sell(p, p["qty_open"], f"ALL OUT {sess['all_out']} (session rule)")
    if q and q.get("executable") and q["bid"] <= pl["premium_stop"]:
        return paper.sell(p, p["qty_open"], f"PREMIUM STOP (20% ceiling) ${pl['premium_stop']:.2f} hit (bid {q['bid']:.2f})")
    with _lock:
        m1 = (_state["cache"].get(p["ticker"]) or {}).get("m1")
    if m1 is not None and len(m1):
        c1 = float(m1["Close"].iloc[-1])
        if (c1 < pl["stop_px"]) if p["side"] == "C" else (c1 > pl["stop_px"]):
            return paper.sell(p, p["qty_open"], f"ORB STOP: 1m close {c1:.2f} beyond {pl['stop_px']:.2f} (10% of ATR)")
    return None


def movers_update(day, now):
    """Scheduled top-movers alert: Schwab's movers plus the watched in-play names, with plain-words ideas."""
    parts = []
    for r in [x for x in _rows(day) if x["rank"] < 900][:5]:
        with _lock:
            ent = _state["cache"].get(r["ticker"]) or {}
        m1 = ent.get("m1")
        if m1 is not None and len(m1) and r.get("or_high"):
            chg = (float(m1["Close"].iloc[-1]) / (r["price"] / (1 + (r.get("change_pct") or 0) / 100)) - 1) * 100 if r.get("price") else 0
            parts.append(f"{r['ticker']} {chg:+.1f}%: {idea_for(m1, {'high': r['or_high'], 'low': r['or_low']})}")
    try:
        mv, _ = _fetch.movers("$SPX", "PERCENT_CHANGE_UP")
        dn, _ = _fetch.movers("$SPX", "PERCENT_CHANGE_DOWN")
        lead = [f"{m['symbol']} {m['change_pct']:+.1f}%" for m in (mv or [])[:3] + (dn or [])[:3] if m.get("change_pct") is not None]
    except Exception:
        lead = []
    if not parts and not lead:
        return False
    key = ",".join(sorted(m.split(" ")[0] for m in lead[:6]))
    if store.kv_get(f"movers_last:{day}") == key and not parts:
        return False                                   # nothing new since the last digest: stay quiet
    store.kv_set(f"movers_last:{day}", key)
    return alerts.alert("movers", f"TOP MOVERS {now.strftime('%H:%M')}", (("S&P leaders/laggards: " + ", ".join(lead) + " | ") if lead else "") +
                        " | ".join(parts) + " | ideas, not validated setups; ask Chart about any of them", f"movers:{day}:{now.strftime('%H%M')}")


def status():
    day = core.now_et().date()
    rows = _rows(str(day))
    return {"state": _state["status"], "last_error": _state["last_error"], "prepared": bool(store.kv_get(f"scan_base:{day}")),
            "scanned_at": store.kv_get(f"scan_done:{day}"), "watching": sum(1 for r in rows if r["status"].startswith("watching")),
            "traded": sum(1 for r in rows if r["status"].startswith("traded")), "universe": len(universe()),
            "api": __import__("schwab").STATS, "version": VERSION}


def step(now=None):
    """One pass of the scanner schedule (the worker thread calls this every ~15 s; tests call it directly)."""
    c = cfg()
    if not c.get("enabled", True):
        _state["status"] = "off"
        return
    now = now or core.now_et()
    sess = core.session_info(now)
    day = now.date()
    if sess.get("holiday") or now.weekday() >= 5:
        _state["status"] = "market closed"
        return
    if not _fetch.ready():
        _state["status"] = "waiting for Schwab (no scanning on delayed data)"
        return
    hm = now.strftime("%H:%M")
    if hm >= c.get("prepare_from", "08:30") and not store.kv_get(f"scan_base:{day}") and hm < "15:30":
        _state["status"] = "preparing baselines"
        prepare(day)
    scan_at = c.get("scan_at", "09:35")
    due = (hm == scan_at and now.second >= 20) or hm > scan_at      # 20 s after 09:35 so the 09:34 bar is final
    if due and hm < "15:15" and not store.kv_get(f"scan_done:{day}"):
        _state["status"] = "scanning"
        scan(day, now)
    if store.kv_get(f"scan_done:{day}") and sess["state"] in ("ORB FORMING", "OPEN", "NO NEW ENTRIES", "ALL OUT"):
        minute = now.strftime("%Y-%m-%d %H:%M")
        if _state["last_minute"] != minute and now.second >= 5:
            _state["last_minute"] = minute
            on_minute(day, now)
        for t_up in c.get("movers_updates", ["10:30", "12:00", "14:00"]):
            if hm >= t_up and not store.kv_get(f"movers_done:{day}:{t_up}") and hm < "15:30":
                store.kv_set(f"movers_done:{day}:{t_up}", True)
                movers_update(day, now)
        _state["status"] = "watching"


def _run():
    while not _state["stop"]:
        try:
            step()
            _state["last_error"] = None
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {e}"[:200]
        time.sleep(15)


def start():
    """Background worker so a slow scan never delays position management in the engine loop."""
    if _state["thread"] or not cfg().get("enabled", True):
        return False
    th = threading.Thread(target=_run, daemon=True, name="scanner")
    _state["thread"] = th
    th.start()
    return True


# ---------------------------------------------------------------- offline research (backtest.py)
def _bs(spot, k, iv, t_years, side):
    t = max(t_years, 1e-5)
    sq = iv * math.sqrt(t)
    d1 = (math.log(spot / k) + 0.5 * iv * iv * t) / sq
    n = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    if side == "C":
        return spot * n(d1) - k * n(d1 - sq), n(d1)
    return k * n(-(d1 - sq)) - spot * n(-d1), n(d1) - 1


def backtest_day(day, m1_by_ticker, base_by_ticker, iv_by_ticker=None):
    """The in-play rules over one past day, from finished 1m bars. Stock result per share and in R; the option result
    is MODELED (Black-Scholes, IV from 20-day realized volatility x 1.1, a delta-0.60 strike on the next Friday at
    least 2 days out, spread max($0.02, 3% of mid)): there is no historical option-quote data."""
    c, v = cfg(), vcfg()
    rows = []
    for t, m1 in m1_by_ticker.items():
        b = base_by_ticker.get(t) or {}
        d = m1[m1.index.date == day].between_time("09:30", "15:59")
        orr = opening_range(d, v.get("or_min", 5))
        if not orr or not b.get("open5_med"):
            continue
        rows.append({"ticker": t, "price": orr["close"], "avg_vol14": b.get("avg_vol14"), "atr14": b.get("atr14"),
                     "rvol": round(orr["volume"] / b["open5_med"], 2), "direction": orr["direction"], "orr": orr, "m1": d})
    top, _ = rank_in_play(rows, c)
    trades = []
    for r in top:
        t = r["ticker"]
        d, orr, side = r["m1"], r["orr"], r["direction"]
        end = pd.Timestamp(f"{day} {v.get('last_entry', '15:15')}", tz=core.ET)
        trig = orb_trigger(d, orr, end + timedelta(minutes=1), side)
        if not trig:
            continue
        ts, px = trig
        risk = v.get("stop_atr_frac", 0.10) * r["atr14"]
        stop = px - risk if side == "C" else px + risk
        after = d[d.index > ts]
        exit_px, exit_ts, why = None, None, "all out 15:25"
        for i, row in after.iterrows():
            if i.strftime("%H:%M") >= "15:25":
                exit_px, exit_ts = float(row["Open"]), i
                break
            if (row["Low"] <= stop) if side == "C" else (row["High"] >= stop):
                exit_px, exit_ts, why = stop, i, "stop (10% ATR)"
                break
        if exit_px is None:
            if not len(after):
                continue
            exit_px, exit_ts = float(after["Close"].iloc[-1]), after.index[-1]
        move = (exit_px - px) if side == "C" else (px - exit_px)
        iv = (iv_by_ticker or {}).get(t) or 0.45
        exp = pd.Timestamp(day) + timedelta(days=((4 - pd.Timestamp(day).weekday()) % 7) or 7)
        if (exp.date() - day).days < 2:
            exp += timedelta(days=7)
        ty = lambda when: ((pd.Timestamp(exp.date()) + timedelta(hours=16)) - pd.Timestamp(when).tz_localize(None)).total_seconds() / (365 * 86400)
        strikes = np.arange(round(px * 0.85), round(px * 1.15) + 1, 1.0 if px < 200 else 5.0)
        k = min(strikes, key=lambda s: abs(abs(_bs(px, s, iv, ty(ts), side)[1]) - 0.60))
        e_mid = _bs(px, k, iv, ty(ts), side)[0]
        x_mid = _bs(exit_px, k, iv, ty(exit_ts), side)[0]
        sp = lambda m: max(0.02, 0.03 * m)
        fee = core.policy()["v3"]["contract"]["fees_per_contract_side"]
        e_fill, x_fill = e_mid + sp(e_mid) / 2, max(0.0, x_mid - sp(x_mid) / 2)
        opt = (x_fill - e_fill) * 100 - 2 * fee
        trades.append({"day": str(day), "ticker": t, "side": side, "rvol": r["rvol"], "entry_t": ts.strftime("%H:%M"), "entry_px": round(px, 2),
                       "stop": round(stop, 2), "exit_t": exit_ts.strftime("%H:%M"), "exit_px": round(exit_px, 2), "why": why,
                       "stock_move": round(move, 3), "stock_R": round(move / risk, 2) if risk else None,
                       "option_pnl_modeled": round(float(opt), 2), "option_entry_modeled": round(float(e_fill), 2), "strike": float(k),
                       "expiry": str(exp.date()), "iv_assumed": round(iv, 3)})
    return trades


BACKTEST_VERSION = "2026-10-30.inplay-bt2"


def backtest_day_v2(day, m1_by_ticker, base_by_ticker, iv_by_ticker=None, latency_min=1):
    """bt2: the in-play rules replayed causally (the audit found bt1 filled at the signal bar's close with the bar's
    OPEN timestamp and assumed ideal stop fills through gaps).
      * the signal is known when its 1m bar CLOSES (decision_at = bar open + 1 min), never earlier than the session's
        first entry (09:45 by policy);
      * the entry is the OPEN of the first bar starting at decision_at + latency (an executable proxy for the stock;
        options are still MODELED from it);
      * a stop that the price gaps through fills at that bar's open, not at the stop price;
      * all out at the 15:25 bar's open.
    bt1 (backtest_day) is kept unchanged as the labeled legacy diagnostic."""
    c, v = cfg(), vcfg()
    first = core.policy()["session"]["first_entry"]
    rows = []
    for t, m1 in m1_by_ticker.items():
        b = base_by_ticker.get(t) or {}
        d = m1[m1.index.date == day].between_time("09:30", "15:59")
        orr = opening_range(d, v.get("or_min", 5))
        if not orr or not b.get("open5_med"):
            continue
        rows.append({"ticker": t, "price": orr["close"], "avg_vol14": b.get("avg_vol14"), "atr14": b.get("atr14"),
                     "rvol": round(orr["volume"] / b["open5_med"], 2), "direction": orr["direction"], "orr": orr, "m1": d})
    top, _ = rank_in_play(rows, c)
    trades, rejected = [], []
    fee = core.policy()["v3"]["contract"]["fees_per_contract_side"]
    for r in top:
        t, d, orr, side = r["ticker"], r["m1"], r["orr"], r["direction"]
        end = pd.Timestamp(f"{day} {v.get('last_entry', '15:15')}", tz=core.ET)
        start = pd.Timestamp(f"{day} {first}", tz=core.ET) - timedelta(minutes=1)        # bar whose close is 09:45
        lvl = orr["high"] if side == "C" else orr["low"]
        cand = d[(d.index >= start) & (d.index < end)]
        hit = cand[(cand["Close"] > lvl) if side == "C" else (cand["Close"] < lvl)]
        if not len(hit):
            rejected.append({"ticker": t, "why": f"no finished 1m close beyond the range between {first} and {v.get('last_entry', '15:15')}"})
            continue
        sig_open = hit.index[0]
        decision_at = sig_open + timedelta(minutes=1)
        nxt = d[d.index >= decision_at + timedelta(minutes=latency_min - 1 if latency_min > 0 else 0)]
        nxt = nxt[nxt.index >= decision_at]
        if not len(nxt):
            rejected.append({"ticker": t, "why": "no bar after the decision"})
            continue
        fill_at, px = nxt.index[0], float(nxt["Open"].iloc[0])
        risk = v.get("stop_atr_frac", 0.10) * r["atr14"]
        stop = px - risk if side == "C" else px + risk
        after = d[d.index > fill_at]
        exit_px, exit_ts, why = None, None, "all out 15:25"
        for i, row in after.iterrows():
            if i.strftime("%H:%M") >= "15:25":
                exit_px, exit_ts = float(row["Open"]), i
                break
            o = float(row["Open"])
            if (o <= stop) if side == "C" else (o >= stop):
                exit_px, exit_ts, why = o, i, "stop gapped: filled at the bar open"
                break
            if (row["Low"] <= stop) if side == "C" else (row["High"] >= stop):
                exit_px, exit_ts, why = stop, i, "stop (10% ATR)"
                break
        if exit_px is None:
            if not len(after):
                continue
            exit_px, exit_ts = float(after["Close"].iloc[-1]), after.index[-1]
        move = (exit_px - px) if side == "C" else (px - exit_px)
        iv = (iv_by_ticker or {}).get(t) or 0.45
        exp = pd.Timestamp(day) + timedelta(days=((4 - pd.Timestamp(day).weekday()) % 7) or 7)
        if (exp.date() - day).days < 2:
            exp += timedelta(days=7)
        ty = lambda when: ((pd.Timestamp(exp.date()) + timedelta(hours=16)) - pd.Timestamp(when).tz_localize(None)).total_seconds() / (365 * 86400)
        strikes = np.arange(round(px * 0.85), round(px * 1.15) + 1, 1.0 if px < 200 else 5.0)
        k = min(strikes, key=lambda s_: abs(abs(_bs(px, s_, iv, ty(fill_at), side)[1]) - 0.60))
        e_mid = _bs(px, k, iv, ty(fill_at), side)[0]
        x_mid = _bs(exit_px, k, iv, ty(exit_ts), side)[0]
        sp = lambda m: max(0.02, 0.03 * m)
        e_fill, x_fill = e_mid + sp(e_mid) / 2 + 0.01, max(0.0, x_mid - sp(x_mid) / 2 - 0.01)     # exec2 costs
        opt = (x_fill - e_fill) * 100 - 2 * fee
        trades.append({"day": str(day), "ticker": t, "side": side, "rvol": r["rvol"], "signal_bar": sig_open.strftime("%H:%M"),
                       "decision_at": decision_at.strftime("%H:%M"), "fill_at": fill_at.strftime("%H:%M"), "entry_px": round(px, 2),
                       "stop": round(stop, 2), "exit_t": exit_ts.strftime("%H:%M"), "exit_px": round(exit_px, 2), "why": why,
                       "stock_move": round(move, 3), "stock_R": round(move / risk, 2) if risk else None,
                       "option_pnl_modeled": round(float(opt), 2), "option_entry_modeled": round(float(e_fill), 2),
                       "strike": float(k), "expiry": str(exp.date()), "iv_assumed": round(iv, 3), "version": BACKTEST_VERSION})
    return {"trades": trades, "rejected": [dict(x, day=str(day)) for x in rejected], "version": BACKTEST_VERSION}
