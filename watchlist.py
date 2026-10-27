"""watchlist.py - other tickers Nick follows (earnings plays, swings). Quotes + next earnings, no AI.

SPY/QQQ stay the desk's main instruments (plans, paper engine, auto-management).
Watchlist tickers get quotes, an earnings date, the same market read for Chart, and journal-only trade logging.
"""
import json
import re
import threading
import time
from datetime import date, datetime

import core

WL_FILE = core.HERE / "config" / "watchlist.json"
DEFAULT = ["NVDA", "TSLA", "AAPL", "META", "MSFT", "AMD", "PLTR", "MU", "GOOGL", "AMZN", "GLD", "IWM"]
VALID = re.compile(r"^[A-Z][A-Z.\-]{0,5}$")
_lock = threading.Lock()
_q = {"at": 0, "rows": {}}
_er = {}  # ticker -> (fetched_at, info)


def valid(t):
    return bool(VALID.match(str(t or "").upper())) and str(t).upper() not in ("IN", "OUT", "AT", "ON", "OFF")


def tickers():
    try:
        t = json.loads(WL_FILE.read_text()).get("tickers")
        if isinstance(t, list):
            return [x for x in t if valid(x)][:40]
    except Exception:
        pass
    return list(DEFAULT)


def save(ts):
    WL_FILE.write_text(json.dumps({"tickers": ts}, indent=1))
    with _lock:
        _q["at"] = 0
    return ts


def add(t):
    t = t.upper()
    if not valid(t):
        raise ValueError("ticker must be 1-6 letters")
    ts = tickers()
    if t not in ts and t not in core.policy()["instruments"]:
        ts.append(t)
    return save(ts)


def remove(t):
    return save([x for x in tickers() if x != t.upper()])


def _download(ts, **kw):
    import pandas as pd
    import yfinance as yf
    df = yf.download(ts, progress=False, auto_adjust=False, group_by="ticker", threads=True, **kw)
    out = {}
    for t in ts:
        try:
            d = df[t] if isinstance(df.columns, pd.MultiIndex) else df
            out[t] = d.dropna(how="all")
        except Exception:
            out[t] = None
    return out


def earnings(t):
    """Next earnings date (Yahoo calendar), cached 12 h. Returns {"date": "YYYY-MM-DD", "days": n} or None."""
    hit = _er.get(t)
    if hit and time.time() - hit[0] < 12 * 3600:
        return hit[1]
    info = None
    try:
        import yfinance as yf
        cal = yf.Ticker(t).calendar
        ds = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if ds:
            d = ds[0] if isinstance(ds, (list, tuple)) else ds
            d = d.date() if isinstance(d, datetime) else d
            if isinstance(d, date):
                days = (d - core.now_et().date()).days
                if days >= -1:
                    info = {"date": d.isoformat(), "days": days}
    except Exception:
        info = None
    _er[t] = (time.time(), info)
    return info


def quotes(max_age=30):
    ts = tickers()
    with _lock:
        if time.time() - _q["at"] < max_age and set(_q["rows"]) == set(ts):
            return [_q["rows"][t] for t in ts]
    rows = {}
    try:
        daily = _download(ts, period="7d", interval="1d")
        intra = _download(ts, period="1d", interval="5m", prepost=True)
    except Exception as e:
        return [{"ticker": t, "error": f"quotes unavailable ({type(e).__name__})"} for t in ts]
    for t in ts:
        d, m = daily.get(t), intra.get(t)
        try:
            closes = d["Close"].dropna()
            last = float(m["Close"].dropna().iloc[-1]) if m is not None and len(m["Close"].dropna()) else float(closes.iloc[-1])
            today = core.now_et().date()
            prev = float(closes.iloc[-2]) if closes.index[-1].date() == today and len(closes) > 1 else float(closes.iloc[-1])
            spark = [round(float(x), 2) for x in (m["Close"].dropna().iloc[-48:] if m is not None else closes)]
            rows[t] = {"ticker": t, "last": round(last, 2), "chg_pct": round((last / prev - 1) * 100, 2),
                       "spark": spark, "earnings": earnings(t)}
        except Exception:
            rows[t] = {"ticker": t, "error": "no data"}
    with _lock:
        _q.update(at=time.time(), rows=rows)
    return [rows[t] for t in ts]


def quote(t):
    for r in quotes():
        if r["ticker"] == t.upper():
            return r
    return None
