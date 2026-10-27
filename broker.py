"""broker.py - Alpaca PAPER only + market data. Refuses anything that is not the paper endpoint.

Safety: exact endpoint allowlist, paper key prefix, AND the account number must be a paper account (PA...).
No Robinhood code exists anywhere in this project.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

PAPER = "https://paper-api.alpaca.markets"
DATA = "https://data.alpaca.markets"
ALLOWED = {PAPER, DATA}
_acct_ok = {"checked": 0, "ok": False, "why": "not checked"}


def _keys():
    return os.environ.get("ALPACA_KEY", ""), os.environ.get("ALPACA_SECRET", "")


def configured():
    k, s = _keys()
    return bool(k and s)


def _req(method, base, path, body=None, timeout=12):
    if base not in ALLOWED:
        raise RuntimeError("REFUSED: non-paper endpoint")
    k, s = _keys()
    if not k or not s:
        return None, "Alpaca keys not set"
    if not k.startswith("PK"):
        return None, "REFUSED: not a paper key"
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return (json.loads(raw) if raw else {}), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def paper_account_ok(force=False):
    """Verify this really is a paper account before any order. Cached 10 minutes."""
    if not force and time.time() - _acct_ok["checked"] < 600:
        return _acct_ok["ok"], _acct_ok["why"]
    a, err = _req("GET", PAPER, "/v2/account")
    ok = bool(a) and str(a.get("account_number", "")).startswith("PA")
    _acct_ok.update(checked=time.time(), ok=ok,
                    why="paper account verified" if ok else (err or "account is not a paper (PA...) account"))
    return ok, _acct_ok["why"]


# ---------------- market data ----------------
def stock_last(ticker):
    j, err = _req("GET", DATA, f"/v2/stocks/{ticker}/trades/latest?feed=iex")
    t = (j or {}).get("trade") or {}
    return ({"price": t.get("p"), "ts": t.get("t"), "feed": "IEX (one exchange)"} if t.get("p") else None), err


def snapshots(tickers):
    """Last trade + today's and yesterday's daily bars for many tickers in ONE call (IEX, free with paper keys)."""
    syms = ",".join(tickers)
    j, err = _req("GET", DATA, f"/v2/stocks/snapshots?symbols={urllib.parse.quote(syms)}&feed=iex")
    if not j:
        return {}, err or "no snapshot data"
    out = {}
    for t, v in j.items():
        if not isinstance(v, dict):
            continue
        last = (v.get("latestTrade") or {}).get("p") or (v.get("dailyBar") or {}).get("c")
        prev = (v.get("prevDailyBar") or {}).get("c")
        out[t] = {"last": last, "prev": prev, "ts": (v.get("latestTrade") or {}).get("t")}
    return out, None


def bars_multi(tickers, start_iso, timeframe="15Min"):
    """Intraday bars for many tickers in one call: {ticker: [close, ...]} (IEX)."""
    q = urllib.parse.urlencode({"symbols": ",".join(tickers), "timeframe": timeframe, "start": start_iso,
                                "feed": "iex", "limit": 10000})
    j, err = _req("GET", DATA, f"/v2/stocks/bars?{q}")
    if not j:
        return {}, err
    return {t: [b["c"] for b in bs] for t, bs in (j.get("bars") or {}).items()}, None


def option_quote(symbol):
    j, err = _req("GET", DATA, f"/v1beta1/options/quotes/latest?symbols={symbol}&feed=indicative")
    qd = ((j or {}).get("quotes") or {}).get(symbol)
    if not qd:
        return None, err or "no quote"
    return {"bid": float(qd.get("bp") or 0), "ask": float(qd.get("ap") or 0), "ts": qd.get("t"),
            "feed": "indicative"}, None


def chain(ticker, side, expiry):
    """Today's snapshots for one side: [{symbol, strike, bid, ask, ts, delta, iv}] (delta may be None)."""
    typ = "call" if side.upper().startswith("C") else "put"
    out, token = [], None
    for _ in range(5):
        path = (f"/v1beta1/options/snapshots/{ticker}?feed=indicative&type={typ}&expiration_date={expiry}&limit=1000"
                + (f"&page_token={urllib.parse.quote(token)}" if token else ""))
        j, err = _req("GET", DATA, path)
        if not j:
            return out, err
        for sym, s in (j.get("snapshots") or {}).items():
            qd, g = s.get("latestQuote") or {}, s.get("greeks") or {}
            out.append({"symbol": sym, "strike": int(sym[-8:]) / 1000, "bid": float(qd.get("bp") or 0),
                        "ask": float(qd.get("ap") or 0), "ts": qd.get("t"),
                        "delta": g.get("delta"), "iv": s.get("impliedVolatility")})
        token = j.get("next_page_token")
        if not token:
            break
    return out, None


# ---------------- paper orders ----------------
def submit(symbol, qty, side, client_id):
    ok, why = paper_account_ok()
    if not ok:
        return None, f"REFUSED: {why}"
    body = {"symbol": symbol, "qty": str(qty), "side": side, "type": "market", "time_in_force": "day",
            "client_order_id": client_id}
    return _req("POST", PAPER, "/v2/orders", body)


def order_by_client(client_id):
    return _req("GET", PAPER, f"/v2/orders:by_client_order_id?client_order_id={urllib.parse.quote(client_id)}")


def open_positions():
    return _req("GET", PAPER, "/v2/positions")
