"""schwab.py - Schwab MARKET DATA only (live stock candles, live option chains with greeks, quotes).

Off until Nick adds SCHWAB_APP_KEY + SCHWAB_APP_SECRET to Chart's Secrets and connects once on the desk's
Rules page (he logs in on Schwab's own site himself; the desk never sees his password).

Safety: this client can only call /marketdata/v1/*, /v1/oauth/* and ONE read-only preferences call
(GET /trader/v1/userPreference), which Schwab requires to get the streaming address/IDs. Every other path
(accounts, positions, orders, trading) is refused in code, so the desk can never trade or read balances. Tokens stay in journal/schwab_token.json
on Chart's computer and are never sent to the browser or to Chart.

Schwab rules (checked Oct 29 2026 against the schwab-py v1.5.0 source, an UNOFFICIAL wrapper; confirm in the
official Trader API docs for your app): access token lasts 30 minutes
(refreshed automatically); the login (refresh token) lasts 7 days, then Nick reconnects (about 1 minute).
"""
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import core

API = "https://api.schwabapi.com"
AUTH_URL = API + "/v1/oauth/authorize"
TOKEN_URL = API + "/v1/oauth/token"
ALLOWED_PREFIXES = ("/marketdata/v1/", "/v1/oauth/")
STREAMER_PREFS = "/trader/v1/userPreference"   # read-only: streamer URL + IDs (the only /trader path allowed)
TOKEN_FILE = core.HERE / "journal" / "schwab_token.json"
REFRESH_LIFE_S = 7 * 24 * 3600
_lock = threading.Lock()
_cache = {}


def _keys():
    return os.environ.get("SCHWAB_APP_KEY", ""), os.environ.get("SCHWAB_APP_SECRET", "")


def callback():
    return os.environ.get("SCHWAB_CALLBACK", "https://127.0.0.1")


def configured():
    k, s = _keys()
    return bool(k and s)


def _load():
    try:
        return json.loads(TOKEN_FILE.read_text())
    except Exception:
        return None


def _save(tok):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tok))
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def status():
    """What the desk shows on the Rules page (never the tokens themselves)."""
    if not configured():
        return {"state": "off", "why": "add SCHWAB_APP_KEY and SCHWAB_APP_SECRET to Chart's Secrets"}
    t = _load()
    if not t or not t.get("refresh_token"):
        return {"state": "not connected", "why": "press Connect Schwab on the Rules page"}
    left = t.get("refresh_issued", 0) + REFRESH_LIFE_S - time.time()
    if left <= 0:
        return {"state": "expired", "why": "Schwab's 7-day login ran out: press Connect Schwab again"}
    return {"state": "connected", "days_left": round(left / 86400, 1), "last_error": t.get("last_error")}


def ready():
    return status()["state"] == "connected"


def login_url():
    k, _ = _keys()
    return AUTH_URL + "?" + urllib.parse.urlencode({"client_id": k, "redirect_uri": callback()})


def _token_request(form):
    k, s = _keys()
    basic = base64.b64encode(f"{k}:{s}".encode()).decode()
    req = urllib.request.Request(TOKEN_URL, data=urllib.parse.urlencode(form).encode(), method="POST",
                                 headers={"Authorization": f"Basic {basic}",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def connect(redirected_url):
    """Nick pastes the address Schwab sent him to (https://127.0.0.1/?code=...). Exchange the code for tokens."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(redirected_url.strip()).query)
    code = (q.get("code") or [""])[0]
    if not code:
        return False, "That address has no ?code= in it. Copy the whole address after logging in."
    try:
        tok = _token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": callback()})
    except urllib.error.HTTPError as e:
        return False, f"Schwab said HTTP {e.code}: {e.read().decode()[:160]} (codes expire in about 30 seconds; try again quickly)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    now = time.time()
    _save({"access_token": tok.get("access_token"), "refresh_token": tok.get("refresh_token"),
           "expires_at": now + int(tok.get("expires_in", 1800)) - 60, "refresh_issued": now})
    return True, "connected"


def _access():
    with _lock:
        t = _load()
        if not t or not t.get("refresh_token"):
            return None
        if time.time() < t.get("expires_at", 0) and t.get("access_token"):
            return t["access_token"]
        try:
            new = _token_request({"grant_type": "refresh_token", "refresh_token": t["refresh_token"]})
        except Exception as e:
            t["last_error"] = f"refresh failed: {type(e).__name__}"
            _save(t)
            return None
        t.update(access_token=new.get("access_token"), expires_at=time.time() + int(new.get("expires_in", 1800)) - 60,
                 last_error=None)
        if new.get("refresh_token"):
            t["refresh_token"] = new["refresh_token"]
        _save(t)
        return t["access_token"]


# Schwab's documented limit for the market-data API is about 120 requests a minute per app. The scanner adds
# many calls, so every call goes through one shared budget (default 100/min) and waits rather than getting 429s.
RATE_PER_MIN = 100
_calls = []
_rate_lock = threading.Lock()
STATS = {"calls": 0, "waited_s": 0.0, "http_errors": 0}


def _throttle():
    while True:
        with _rate_lock:
            now = time.time()
            while _calls and now - _calls[0] > 60:
                _calls.pop(0)
            if len(_calls) < RATE_PER_MIN:
                _calls.append(now)
                STATS["calls"] += 1
                return
            wait = 60 - (now - _calls[0]) + 0.05
        STATS["waited_s"] += wait
        time.sleep(min(wait, 5))


def _get(path, params):
    if not (path.startswith(ALLOWED_PREFIXES[0]) or path == STREAMER_PREFS):
        raise RuntimeError("REFUSED: the desk only reads Schwab market data")
    tok = _access()
    if not tok:
        return None, "Schwab not connected"
    _throttle()
    url = API + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        STATS["http_errors"] += 1
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, f"{type(e).__name__}"


def access_token():
    """For the streamer LOGIN only (sent to Schwab's own websocket, never to the browser, Chart or logs)."""
    return _access()


def streamer_info():
    """{streamerSocketUrl, schwabClientCustomerId, schwabClientCorrelId, schwabClientChannel, schwabClientFunctionId}."""
    j, err = _get(STREAMER_PREFS, {})
    info = ((j or {}).get("streamerInfo") or [None])[0]
    return (info, None) if info else (None, err or "no streamerInfo (is Market Data/Trader API enabled for the app?)")


def _cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    v = fn()
    if v is not None:
        _cache[key] = (time.time(), v)
    return v


# ---------------- market data ----------------
def _frame(candles):
    import pandas as pd
    if not candles:
        return None
    idx = pd.to_datetime([c["datetime"] for c in candles], unit="ms", utc=True).tz_convert(core.ET)
    return pd.DataFrame({"Open": [c["open"] for c in candles], "High": [c["high"] for c in candles],
                         "Low": [c["low"] for c in candles], "Close": [c["close"] for c in candles],
                         "Volume": [c.get("volume", 0) for c in candles]}, index=idx)


def bars_1m(ticker, days=10):
    """1-minute candles incl. extended hours (consolidated volume), ET index. None if unavailable."""
    def f():
        j, _ = _get("/marketdata/v1/pricehistory", {"symbol": ticker.upper(), "periodType": "day", "period": days,
                                                     "frequencyType": "minute", "frequency": 1,
                                                     "needExtendedHoursData": "true", "needPreviousClose": "false"})
        return _frame((j or {}).get("candles"))
    return _cached(("1m", ticker, days), 8, f)


def bars_1m_range(ticker, start, end):
    """1-minute candles between two datetimes (Schwab keeps roughly the last 48 days of 1m history). Used by replay.py.
    Market data only, same pricehistory endpoint. Returns an ET-indexed frame or None."""
    j, err = _get("/marketdata/v1/pricehistory", {"symbol": ticker.upper(), "periodType": "day", "frequencyType": "minute",
                                                   "frequency": 1, "startDate": int(start.timestamp() * 1000),
                                                   "endDate": int(end.timestamp() * 1000), "needExtendedHoursData": "true",
                                                   "needPreviousClose": "false"})
    return _frame((j or {}).get("candles"))


def bars_daily(ticker):
    def f():
        j, _ = _get("/marketdata/v1/pricehistory", {"symbol": ticker.upper(), "periodType": "year", "period": 2,
                                                     "frequencyType": "daily", "frequency": 1})
        df = _frame((j or {}).get("candles"))
        if df is not None:
            df.index = df.index.tz_localize(None).normalize()
        return df
    return _cached(("1d", ticker), 3600, f)


def occ(sym):
    """Schwab 'SPY   261028C00600000' -> OCC 'SPY261028C00600000' (same format Alpaca paper uses)."""
    return (sym or "").replace(" ", "")


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if v <= -999 or v != v else v      # Schwab sends -999 when a greek isn't available


def chain(ticker, side, expiry, through=None, strike_count=None):
    """Live chain for one side: [{symbol, strike, exp, bid, ask, ts, delta, iv, last, prev, volume, oi, feed}] like broker.chain.
    expiry alone = that day only; with through = every expiry from expiry to through. strike_count limits strikes
    around the money (smaller payloads for the scanner)."""
    typ = "CALL" if side.upper().startswith("C") else "PUT"
    params = {"symbol": ticker.upper(), "contractType": typ, "fromDate": expiry,
              "toDate": through or expiry, "strategy": "SINGLE", "includeUnderlyingQuote": "false"}
    if strike_count:
        params["strikeCount"] = int(strike_count)
    j, err = _get("/marketdata/v1/chains", params)
    if not j:
        return None, err
    m = j.get("callExpDateMap" if typ == "CALL" else "putExpDateMap") or {}
    rows = []
    for exp_key, strikes in m.items():
        if not through and not exp_key.startswith(expiry):
            continue
        for k, lst in strikes.items():
            for o in lst or []:
                bid, ask = _num(o.get("bid")), _num(o.get("ask"))
                if bid is None or ask is None:
                    continue
                iv = _num(o.get("volatility"))
                rows.append({"symbol": occ(o.get("symbol")), "strike": float(o.get("strikePrice") or k), "bid": bid, "ask": ask,
                             "ts": datetime.fromtimestamp((o.get("quoteTimeInLong") or 0) / 1000, core.ET).isoformat() if o.get("quoteTimeInLong") else None,
                             "delta": _num(o.get("delta")), "gamma": _num(o.get("gamma")), "theta": _num(o.get("theta")),
                             "vega": _num(o.get("vega")), "iv": iv / 100 if iv and iv > 3 else iv,
                             "bid_size": o.get("bidSize"), "ask_size": o.get("askSize"), "multiplier": o.get("multiplier") or 100,
                             "exp": exp_key[:10], "last": _num(o.get("last")), "prev": _num(o.get("closePrice")),
                             "volume": o.get("totalVolume"), "oi": o.get("openInterest"), "feed": "Schwab live"})
    return rows, None if rows else "empty chain"


def option_quote(symbol):
    """Live bid/ask for one OCC option symbol. Schwab wants the padded 21-char form."""
    root = symbol[:-15]
    padded = root.ljust(6) + symbol[-15:]
    j, err = _get("/marketdata/v1/quotes", {"symbols": padded, "fields": "quote"})
    q = ((j or {}).get(padded) or (j or {}).get(symbol) or {}).get("quote") or {}
    bid, ask = _num(q.get("bidPrice")), _num(q.get("askPrice"))
    if bid is None or ask is None:
        return None, err or "no quote"
    return {"bid": bid, "ask": ask, "ts": q.get("quoteTime"), "feed": "Schwab live"}, None


def quotes(tickers):
    """{ticker: {last, prev}} for the watchlist, one call."""
    j, err = _get("/marketdata/v1/quotes", {"symbols": ",".join(tickers), "fields": "quote"})
    out = {}
    for t, v in (j or {}).items():
        q = (v or {}).get("quote") or {}
        last, prev = _num(q.get("lastPrice")), _num(q.get("closePrice"))
        if last:
            out[t] = {"last": last, "prev": prev}
    return out, err


def quotes_full(tickers):
    """{ticker: {last, open, prev, high, low, volume, bid, ask, quote_ms}} for up to ~100 symbols per call (scanner)."""
    out, err = {}, None
    for i in range(0, len(tickers), 100):
        j, e = _get("/marketdata/v1/quotes", {"symbols": ",".join(tickers[i:i + 100]), "fields": "quote"})
        err = err or e
        for t, v in (j or {}).items():
            q = (v or {}).get("quote") or {}
            last = _num(q.get("lastPrice"))
            if last:
                out[t] = {"last": last, "open": _num(q.get("openPrice")), "prev": _num(q.get("closePrice")),
                          "high": _num(q.get("highPrice")), "low": _num(q.get("lowPrice")), "volume": q.get("totalVolume"),
                          "bid": _num(q.get("bidPrice")), "ask": _num(q.get("askPrice")), "quote_ms": q.get("quoteTime")}
    return out, err


def movers(index="$SPX", sort="VOLUME"):
    """Schwab's top movers for an index ($DJI, $COMPX, $SPX, NYSE, NASDAQ, ...): [{symbol, last, change_pct, volume}].
    Schwab returns about ten names. Market data only."""
    j, err = _get(f"/marketdata/v1/movers/{index}", {"sort": sort})
    rows = []
    for m in (j or {}).get("screeners") or []:
        rows.append({"symbol": m.get("symbol"), "last": _num(m.get("lastPrice")), "change_pct": _num(m.get("netPercentChange")),
                     "volume": m.get("volume"), "description": m.get("description")})
    return rows, err


def bars_range(ticker, start, end, minutes=1, extended=False):
    """N-minute candles (1, 5, 10, 15, 30) between two datetimes. The scanner uses 5-minute history for baselines."""
    j, err = _get("/marketdata/v1/pricehistory", {"symbol": ticker.upper(), "periodType": "day", "frequencyType": "minute",
                                                   "frequency": int(minutes), "startDate": int(start.timestamp() * 1000),
                                                   "endDate": int(end.timestamp() * 1000),
                                                   "needExtendedHoursData": "true" if extended else "false",
                                                   "needPreviousClose": "false"})
    return _frame((j or {}).get("candles"))
