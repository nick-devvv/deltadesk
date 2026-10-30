"""chartfeed.py - data for the desk's own chart, built from the SAME snapshot the engine decides on.

Any ticker Schwab supports (SPY/QQQ, a scanner name, a searched symbol). Candles are Schwab 1m bars aggregated to
1/2/5/15 minutes on the 09:30 grid. Two sessions are sent (the previous one and today) so you can pan back.

What is real and what is provisional:
  * final candles: Schwab bars (stream CHART_EQUITY or REST pricehistory) whose minutes have ended;
  * forming candle: Schwab's own partial bar (REST), or, while streaming, a PROVISIONAL candle built from the trade
    prices the stream reported this minute. It has no volume (level-one data can't give honest per-minute volume)
    and its high/low can miss trades between updates. It is replaced by the real bar when that arrives.
  * VWAP is regular-session only (reset 09:30); extended-hours candles are shown without VWAP.
  * EMA 9/21 and MACD(12,26,9) are computed on the displayed timeframe's regular-session candles. The engine's
    decisions use MACD on 2m: the 2m chart matches it exactly, other timeframes are for reading only.
Times are Unix SECONDS (Lightweight Charts). `since` returns only candles/points at or after that time (live tail).
"""
import pandas as pd

import core
import engine
import indicators as I
import marketdata
import store

TFS = (1, 2, 5, 15)
LIVE_STATES = ("ORB FORMING", "OPEN", "NO NEW ENTRIES", "ALL OUT")


def _ts(t):
    return int(pd.Timestamp(t).timestamp())


def _orb(r1, n, now):
    import scanner_setups
    return scanner_setups.orb(r1, n, now)


def feed_status(ticker, meta, prov, sess_state, n_candles):
    """live / polling / delayed / stale / closed / unavailable, with a reason that separates a quiet market from a
    broken connection."""
    md = marketdata.status()
    p = marketdata.provider()
    sch = md.get("schwab") or {}
    bar_age = (meta or {}).get("bar_age_s")
    prov_age = None
    if prov:
        prov_age = round((marketdata.now() - pd.Timestamp(prov["last_trade"])).total_seconds(), 1)
    out = {"bar_age_s": bar_age, "trade_age_s": prov_age, "session": sess_state, "connection": sch.get("state"),
           "mode": md.get("mode"), "provider": p.name}
    if not n_candles:
        out.update(state="unavailable", why=(meta or {}).get("error") or "no bars")
        return out
    if not p.executable:
        out.update(state="delayed", why="Schwab isn't connected: delayed fallback bars, not tradable")
        return out
    if sess_state not in LIVE_STATES:
        quiet = "pre-market" if sess_state == "PREMARKET" else "after hours" if sess_state == "AFTER HOURS" else "market closed"
        out.update(state="closed", why=f"{quiet}: the regular session isn't trading" + (
            "" if sess_state in ("PREMARKET", "AFTER HOURS") else ", so no new candles is normal"))
        return out
    if sch.get("state") not in (None, "connected", "test"):
        out.update(state="stale", why=f"Schwab connection {sch.get('state')}: {sch.get('why') or ''}".strip())
        return out
    fresh_bar = bar_age is not None and bar_age <= marketdata.MAX_LIVE_BAR_AGE_S
    fresh_trade = prov_age is not None and prov_age <= 60
    if fresh_bar or fresh_trade:
        out.update(state="live" if md.get("mode") == "stream" else "polling",
                   why="streaming" if md.get("mode") == "stream" else "Schwab REST, refreshed every few seconds")
        return out
    out.update(state="stale", why=(f"no new bar for {bar_age:.0f}s while the connection is up: the symbol may be "
                                   "trading thinly, or its feed is lagging" if bar_age is not None else "no recent bars"))
    return out


def build(ticker, tf=2, ext=False, since=None):
    tf = int(tf) if str(tf).isdigit() and int(tf) in TFS else 2
    ext = str(ext) in ("1", "true", "True")
    try:
        since = int(since) if since not in (None, "", "0") else None
    except ValueError:
        since = None
    if marketdata._provider is None:
        try:
            import schwab_stream
            schwab_stream.focus_equity(ticker)             # stream the chart ticker; the previous one is unsubscribed
        except Exception:
            pass
    s = engine.snapshot(ticker)
    v3 = s.get("v3") or {}
    m1 = s.get("m1")
    sess = core.session_info()["state"]
    out = {"ticker": ticker, "tf": tf, "ext": ext, "meta": s.get("meta"), "data": marketdata.status().get("live_label"),
           "candles": [], "volume": [], "vwap": [], "ema9": [], "ema21": [], "macd": [], "signal": [], "hist": [],
           "levels": [], "markers": [], "decision": None, "session": sess, "macd_tf": tf, "notes": []}
    if m1 is None or not len(m1):
        err = (s.get("meta") or {}).get("error", "no bars")
        if marketdata.executable() and marketdata.quote(ticker) is None:
            err = f"Schwab has no data for {ticker}. Check the symbol (it may be delisted, an index, or not supported)."
        out["error"] = err
        out["status"] = feed_status(ticker, s.get("meta"), None, sess, 0)
        return out
    day = m1.index[-1].date()
    days = I.sessions(m1)
    keep = [d for d in days if d <= day][-2:]
    view_days = []
    for d in keep:
        dv = m1[m1.index.date == d]
        if not ext:
            r = I.rth(m1, d)
            dv = r if r is not None and len(r) else (dv if d == day else dv.iloc[0:0])
            if d == day and (r is None or not len(r)) and len(dv):
                out["notes"].append("The regular session hasn't opened: showing today's pre-market candles.")
        view_days.append(dv)
    view = pd.concat([x for x in view_days if len(x)]) if any(len(x) for x in view_days) else m1.iloc[0:0]
    f = s.get("forming")
    prov = marketdata.provisional(ticker) if not f else None
    extra = None
    if f:
        extra = {k: f[k] for k in ("Open", "High", "Low", "Close", "Volume")}
        ft = pd.Timestamp(f["open_time"]).tz_convert(core.ET)
    elif prov:
        extra = {"Open": prov["Open"], "High": prov["High"], "Low": prov["Low"], "Close": prov["Close"], "Volume": 0.0}
        ft = pd.Timestamp(prov["open_time"]).tz_convert(core.ET)
    if extra and (ext or "09:30" <= ft.strftime("%H:%M") <= "15:59") and (not len(view) or ft > view.index[-1]):
        view = pd.concat([view, pd.DataFrame([extra], index=pd.DatetimeIndex([ft]))])
    else:
        extra, prov = None, None
    last_final = pd.Timestamp(s["meta"]["last_final_open"]) if (s.get("meta") or {}).get("last_final_open") else None
    parts = []
    for d in keep:
        dv = view[view.index.date == d]
        if len(dv):
            b, done = I.aggregate(dv, tf, last_final)
            parts.append((b, done))
    if not parts:
        out["error"] = "no candles for this view"
        out["status"] = feed_status(ticker, s.get("meta"), None, sess, 0)
        return out
    b = pd.concat([p[0] for p in parts])
    done = pd.concat([p[1] for p in parts])
    if extra is not None and len(b):
        done.iloc[-1] = False
    prov_bucket = None
    if prov is not None:
        prov_bucket = b.index[-1]
    for ts, r in b.iterrows():
        t = _ts(ts)
        c = {"time": t, "open": round(r["Open"], 2), "high": round(r["High"], 2), "low": round(r["Low"], 2),
             "close": round(r["Close"], 2), "final": bool(done.loc[ts])}
        rth = "09:30" <= ts.strftime("%H:%M") <= "15:59"
        if not rth:
            c["ext"] = True
        if prov_bucket is not None and ts == prov_bucket:
            c["provisional"] = True
        out["candles"].append(c)
        if prov_bucket is not None and ts == prov_bucket and tf == 1:
            continue                                         # no volume bar for a trades-only provisional minute
        out["volume"].append({"time": t, "value": float(r["Volume"]),
                              "color": ("rgba(47,227,154,.35)" if r["Close"] >= r["Open"] else "rgba(255,90,78,.35)") if rth
                              else "rgba(142,133,151,.25)"})
    if prov is not None:
        out["notes"].append("The last candle is provisional: built from streamed trade prices, without volume. "
                            "Schwab's real bar replaces it when the minute closes.")
    # regular-session indicators on the displayed timeframe
    rb = b[[("09:30" <= i.strftime("%H:%M") <= "15:59") for i in b.index]]
    if len(rb):
        rm1 = view[[("09:30" <= i.strftime("%H:%M") <= "15:59") for i in view.index]]
        vw = I.session_vwap(rm1)
        vb = vw.reindex(rb.index, method="ffill")
        out["vwap"] = [{"time": _ts(i), "value": round(float(v), 2)} for i, v in vb.items() if v == v]
        e9, e21 = I.ema(rb["Close"], 9), I.ema(rb["Close"], 21)
        out["ema9"] = [{"time": _ts(i), "value": round(float(v), 2)} for i, v in e9.items()]
        out["ema21"] = [{"time": _ts(i), "value": round(float(v), 2)} for i, v in e21.items()]
    if tf == 2 and v3.get("ok"):
        M, S, H = v3["macd"], v3["signal"], v3["hist"]
        keep_idx = [i.date() in keep for i in M.index]
        M, S, H = M[keep_idx], S[keep_idx], H[keep_idx]
    else:
        mb, _ = I.aggregate_multi(m1, tf, last_final)
        M, S, H = I.macd(mb["Close"]) if len(mb) else (pd.Series(dtype=float),) * 3
        sel = [i.date() in keep for i in M.index]
        M, S, H = M[sel], S[sel], H[sel]
        out["notes"].append(f"MACD here is on {tf}m for reading; the engine decides on 2m MACD.") if tf != 2 else None
    for i, m, sg, h in zip(M.index, M, S, H):
        if m == m:
            out["macd"].append({"time": _ts(i), "value": round(float(m), 4)})
            out["signal"].append({"time": _ts(i), "value": round(float(sg), 4)})
            out["hist"].append({"time": _ts(i), "value": round(float(h), 4), "color": "rgba(47,227,154,.6)" if h >= 0 else "rgba(255,90,78,.6)"})
    if v3.get("ok"):
        out["levels"] = [{"name": k, "value": v["value"], "source": v["source"], "complete": v.get("complete")}
                         for k, v in v3["levels"].items() if k != "PDC"]
        out["decision"] = {"t": v3["t"].isoformat(), "vwap": v3.get("vwap"), "macd": I.last(v3["macd"]), "signal": I.last(v3["signal"]),
                           "hist": I.last(v3["hist"]), "atr5": v3.get("atr5"), "adx": v3.get("adx"), "regime": v3["regime"]["label"],
                           "last_final_close": v3["close1"]}
    r1 = I.rth(m1, day)
    if r1 is not None and len(r1):
        now = core.now_et()
        for n in (5, 15, 30):
            o = _orb(r1, n, now)
            if o:
                src = f"opening range 09:30 + {n} min" + ("" if o["complete"] else " (forming)")
                out["levels"] += [{"name": f"ORB{n}_H", "value": round(o["high"], 2), "source": src, "complete": o["complete"]},
                                  {"name": f"ORB{n}_L", "value": round(o["low"], 2), "source": src, "complete": o["complete"]}]
    # entry / exit markers for every ledger on this ticker today
    for o in store.q("SELECT o.ts, o.side, o.qty, o.filled_price, o.reason, p.ledger, p.contract FROM orders o JOIN positions p ON p.id=o.position_id "
                     "WHERE p.ticker=? AND p.date=? AND o.status='FILLED'", (ticker, str(day))):
        t = _ts(pd.Timestamp(o["ts"]).floor(f"{tf}min"))
        buy = o["side"] == "buy"
        out["markers"].append({"time": t, "position": "belowBar" if buy else "aboveBar", "shape": "arrowUp" if buy else "arrowDown",
                               "color": {"paper": "#FF5C78", "research": "#8E8597", "old": "#6C6375"}.get(o["ledger"], "#EEE8F0"),
                               "text": f"{'Paper ' if buy else ''}{o['filled_price']:.2f}" if o["ledger"] == "paper" else "",
                               "size": 1 if o["ledger"] == "paper" else 0.5, "id": o["ledger"]})
    for p in store.positions(ledger="real", day=str(day)):
        if p["ticker"] == ticker:
            out["markers"].append({"time": _ts(pd.Timestamp(p["opened"]).floor(f"{tf}min")), "position": "belowBar", "shape": "circle",
                                   "color": "#2FE39A", "text": f"You {p['contract']} {p['fill']:.2f}"})
    out["markers"].sort(key=lambda m: m["time"])
    out["status"] = feed_status(ticker, s.get("meta"), prov, sess, len(out["candles"]))
    lu = [x for x in (marketdata._bars.get(ticker), ) if x is not None and len(x)]
    out["status"]["last_update"] = (pd.Timestamp(lu[0]["recv"].iloc[-1]).isoformat(timespec="seconds") if lu else None)
    if prov:
        out["status"]["last_update"] = max(out["status"]["last_update"] or "", pd.Timestamp(prov["last_trade"]).isoformat(timespec="seconds"))
    out["notes"] = [n for n in out["notes"] if n]
    if since:
        for k in ("candles", "volume", "vwap", "ema9", "ema21", "macd", "signal", "hist"):
            out[k] = [x for x in out[k] if x["time"] >= since]
        out["markers"] = [m for m in out["markers"] if m["time"] >= since]
        out["tail"] = since
    return out
