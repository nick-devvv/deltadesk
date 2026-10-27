"""altdata.py - optional Quiver Quantitative data for watchlist tickers (earnings plays, swings).

Off unless QUIVER_KEY is set (Nick pastes it into Chart's Secrets himself). Read-only research data:
congress trades, off-exchange short volume, WallStreetBets chatter, lobbying, government contracts.
Uses the official `quiverquant` Python package. Every call is cached 6 h and fails soft: missing data
shows as unavailable, never as zero.
"""
import os
import threading
import time

_cache, _lock = {}, threading.Lock()
TTL = 6 * 3600
DATASETS = {  # method on quiverquant.quiver -> label shown on the desk
    "congress_trading": "Congress trades",
    "offexchange": "Off-exchange short volume",
    "wallstreetbets": "WallStreetBets mentions",
    "lobbying": "Lobbying",
    "gov_contracts": "Gov contracts",
}


def enabled():
    return bool(os.environ.get("QUIVER_KEY"))


def _client():
    import quiverquant  # pip install quiverquant
    return quiverquant.quiver(os.environ["QUIVER_KEY"])


def _rows(df, n=5):
    try:
        recs = df.head(n).to_dict("records") if hasattr(df, "head") else list(df)[:n]
    except Exception:
        return []
    out = []
    for r in recs:
        out.append({str(k): (str(v)[:40] if v is not None else None) for k, v in list(r.items())[:6]})
    return out


def ticker(t):
    """{"enabled": bool, "data": {label: {"rows": [...], "count": n} | {"error": "..."}}}"""
    t = t.upper()
    if not enabled():
        return {"enabled": False, "note": "add QUIVER_KEY to Secrets to turn on congress/insider-style data"}
    with _lock:
        hit = _cache.get(t)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
    data = {}
    try:
        q = _client()
    except Exception as e:
        return {"enabled": True, "error": f"quiverquant unavailable ({type(e).__name__})"}
    for meth, label in DATASETS.items():
        try:
            df = getattr(q, meth)(t)
            data[label] = {"count": int(len(df)) if hasattr(df, "__len__") else None, "rows": _rows(df)}
        except Exception as e:
            data[label] = {"error": f"{type(e).__name__}"}
    res = {"enabled": True, "ticker": t, "source": "Quiver Quantitative", "fetched": time.strftime("%Y-%m-%d %H:%M"), "data": data}
    with _lock:
        _cache[t] = (time.time(), res)
    return res
