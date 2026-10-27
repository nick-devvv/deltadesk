"""chartdata.py - candles + the day's levels for the desk page's own chart (no AI credits)."""
import threading
import time

import pandas as pd
import yfinance as yf

import desk

ET = desk.ET
_cache, _lock = {}, threading.Lock()


def _dl(ticker, period, interval, prepost):
    key = (ticker, period, interval)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < (10 if interval == "1m" else 60):
            return hit[1]
    df = yf.download(ticker, period=period, interval=interval, prepost=prepost, progress=False, auto_adjust=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    with _lock:
        _cache[key] = (time.time(), df)
    return df


def _et_epoch(ts):
    """Lightweight-charts shows UTC, so shift each bar to ET wall-clock time."""
    return int(ts.timestamp() + ts.utcoffset().total_seconds())


def bars(ticker, tf="5", ext=True):
    ticker = ticker.upper()
    m1 = _dl(ticker, "5d", "1m", True)
    daily = _dl(ticker, "2y", "1d", False)
    if m1.empty or daily.empty:
        return {"error": "NO DATA from Yahoo"}
    r = desk.read(ticker, m1.copy(), daily.copy())
    if tf == "D":
        d = daily.copy()
        rows = [[int(pd.Timestamp(i.date()).timestamp()), *(float(x) for x in v)]
                for i, v in zip(d.index, d[["Open", "High", "Low", "Close", "Volume"]].values)]
    else:
        src = m1 if tf in ("1", "2", "5") else _dl(ticker, "60d", "5m", True)
        src = src.tz_convert(ET) if src.index.tz is not None else src.tz_localize(ET)
        if not ext:
            src = src.between_time("09:30", "15:59")
        df = src if tf == "1" else desk.resample(src, f"{int(tf)}min")
        rows = [[_et_epoch(i), *(float(x) for x in v)]
                for i, v in zip(df.index, df[["Open", "High", "Low", "Close", "Volume"]].values)]
    return {"ticker": ticker, "tf": tf, "bars": rows, "levels": r.get("_draw", {}),
            "levels_date": r.get("levels_date"), "price": r.get("price"), "setups": r.get("setups", []),
            "day_type": r.get("day_type"), "time": r.get("time")}
