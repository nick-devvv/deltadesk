"""chartfeed.py - data for the desk's own chart, built from the SAME snapshot the engine decides on.

Candles are finalized Schwab 1m bars (plus the forming bar, flagged), aggregated to 1/2/5 minutes anchored to the
09:30 open. Indicators are computed on the backend (session VWAP, EMA 9/21, MACD on 2m) and sent as values, so the
chart, the indicator panel and a signal's decision snapshot agree. Times are Unix SECONDS (Lightweight Charts).
"""
import pandas as pd

import core
import engine
import indicators as I
import marketdata
import store


def _ts(t):
    return int(pd.Timestamp(t).timestamp())


def build(ticker, tf=2):
    tf = int(tf) if str(tf) in ("1", "2", "5") else 2
    s = engine.snapshot(ticker)
    v3 = s.get("v3") or {}
    m1 = s.get("m1")
    out = {"ticker": ticker, "tf": tf, "meta": s.get("meta"), "data": marketdata.status().get("live_label"),
           "candles": [], "volume": [], "vwap": [], "ema9": [], "ema21": [], "macd": [], "signal": [], "hist": [],
           "levels": [], "markers": [], "decision": None}
    if m1 is None or not len(m1):
        out["error"] = (s.get("meta") or {}).get("error", "no bars")
        return out
    day = m1.index[-1].date()
    r1 = I.rth(m1, day)
    view = r1 if r1 is not None and len(r1) else m1[m1.index.date == day]
    f = s.get("forming")
    if f and r1 is not None and len(r1):
        fr = pd.DataFrame([{k: f[k] for k in ("Open", "High", "Low", "Close", "Volume")}], index=pd.DatetimeIndex([pd.Timestamp(f["open_time"]).tz_convert(view.index.tz)]))
        view = pd.concat([view, fr])
    b, done = I.aggregate(view, tf, view.index[-1]) if len(view) else (view, None)
    if f and len(b):
        done.iloc[-1] = False
    for ts, r in b.iterrows():
        t = _ts(ts)
        out["candles"].append({"time": t, "open": round(r["Open"], 2), "high": round(r["High"], 2), "low": round(r["Low"], 2),
                               "close": round(r["Close"], 2), "final": bool(done.loc[ts]) if done is not None else True})
        out["volume"].append({"time": t, "value": float(r["Volume"]), "color": "rgba(47,227,154,.35)" if r["Close"] >= r["Open"] else "rgba(255,90,78,.35)"})
    if r1 is not None and len(r1):
        vw = I.session_vwap(r1)
        vb = vw.reindex(b.index, method="ffill") if len(b) else vw
        out["vwap"] = [{"time": _ts(i), "value": round(float(v), 2)} for i, v in vb.items() if v == v]
        e9, e21 = I.ema(b["Close"], 9), I.ema(b["Close"], 21)
        out["ema9"] = [{"time": _ts(i), "value": round(float(v), 2)} for i, v in e9.items()]
        out["ema21"] = [{"time": _ts(i), "value": round(float(v), 2)} for i, v in e21.items()]
    if v3.get("ok"):
        M, S, H = v3["macd"], v3["signal"], v3["hist"]
        keep = M.index.date == day
        for i, m, sg, h in zip(M.index[keep], M[keep], S[keep], H[keep]):
            if m == m:
                out["macd"].append({"time": _ts(i), "value": round(float(m), 4)})
                out["signal"].append({"time": _ts(i), "value": round(float(sg), 4)})
                out["hist"].append({"time": _ts(i), "value": round(float(h), 4), "color": "rgba(47,227,154,.6)" if h >= 0 else "rgba(255,90,78,.6)"})
        out["levels"] = [{"name": k, "value": v["value"], "source": v["source"], "complete": v.get("complete")}
                         for k, v in v3["levels"].items() if k != "PDC"]
        out["decision"] = {"t": v3["t"].isoformat(), "vwap": v3.get("vwap"), "macd": I.last(M), "signal": I.last(S), "hist": I.last(H),
                           "atr5": v3.get("atr5"), "adx": v3.get("adx"), "regime": v3["regime"]["label"],
                           "last_final_close": v3["close1"]}
    # entry / exit markers for every ledger on this ticker today
    for o in store.q("SELECT o.ts, o.side, o.qty, o.filled_price, o.reason, p.ledger, p.contract FROM orders o JOIN positions p ON p.id=o.position_id "
                     "WHERE p.ticker=? AND p.date=? AND o.status='FILLED'", (ticker, str(day))):
        t = _ts(pd.Timestamp(o["ts"]).floor(f"{tf}min"))
        buy = o["side"] == "buy"
        out["markers"].append({"time": t, "position": "belowBar" if buy else "aboveBar", "shape": "arrowUp" if buy else "arrowDown",
                               "color": {"paper": "#FF5C78", "research": "#8E8597", "old": "#6C6375"}.get(o["ledger"], "#EEE8F0"),
                               # only main paper gets a label; research / old-rules fills are small unlabeled ticks (less clutter)
                               "text": f"{'Paper ' if buy else ''}{o['filled_price']:.2f}" if o["ledger"] == "paper" else "",
                               "size": 1 if o["ledger"] == "paper" else 0.5, "id": o["ledger"]})
    for p in store.positions(ledger="real", day=str(day)):
        if p["ticker"] == ticker:
            out["markers"].append({"time": _ts(pd.Timestamp(p["opened"]).floor(f"{tf}min")), "position": "belowBar", "shape": "circle",
                                   "color": "#2FE39A", "text": f"You {p['contract']} {p['fill']:.2f}"})
    out["markers"].sort(key=lambda m: m["time"])
    return out
