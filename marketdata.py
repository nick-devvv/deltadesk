"""marketdata.py - ONE normalized market-data pipeline for the whole desk (chart, levels, indicators, signals,
option quotes, positions, paper fills, risk, P&L).

Source of truth: Charles Schwab market data (streaming when available, REST otherwise). Every value carries
its provider, the provider's own timestamp, our receipt time and an age, so nothing keeps a LIVE label forever.

Fallback (Yahoo bars / Alpaca IEX + indicative options) exists ONLY when Schwab isn't connected, is labeled
"FALLBACK - not executable" everywhere, and is never used for simulated fills: `executable` is False, so the
paper engine refuses to fill and records a data outage instead. Yahoo/yfinance is an unofficial research
package; its bars are never merged with Schwab bars.

Bars are 1-minute OHLCV keyed by the bar's OPEN time (ET). A bar is FINAL once its minute has ended (plus a
small grace) or a later bar exists. Stream updates of the same minute replace the earlier copy (no double
counting). Volume = the provider's per-bar share volume (Schwab CHART_EQUITY field 6 / pricehistory candle).
"""
import threading
import time
from collections import deque
from datetime import timedelta

import pandas as pd

import core

FINAL_GRACE_S = 3          # a minute bar is final 3 s after its minute ends
MAX_LIVE_BAR_AGE_S = 90    # newest FINAL bar older than this during RTH -> STALE
MAX_EQ_QUOTE_AGE_S = 15
MAX_OPT_QUOTE_AGE_S = 20

_lock = threading.RLock()
_bars = {}        # ticker -> DataFrame (Open..Volume, src, recv) indexed by bar OPEN time (ET)
_quotes = {}      # symbol -> merged level-one dict (incremental updates merge; omitted fields stay as they were)
_lat = {"bar": deque(maxlen=500), "quote": deque(maxlen=500), "signal": deque(maxlen=500)}
_status = {"mode": "offline", "since": None, "last_msg": None, "last_error": None, "reconnects": 0, "gaps_filled": 0,
           "rest_calls": 0}
_provider = None
_frames = {}
_ver = {}         # ticker -> change counter
_deep_done = set()  # (ticker, day): deep history already requested
_rest_at = {}      # ticker -> time.time() of the last REST bar refresh (live Schwab only: keeps the call budget)
_prov = {}         # ticker -> provisional current-minute candle built from streamed TRADE prices (chart only, no volume)
REST_MIN_REFRESH_S = 4


# ---------------------------------------------------------------- provider selection
class Provider:
    name = "none"
    executable = False

    def bars_1m(self, ticker):
        return None

    def quote(self, ticker):
        return None

    def option_quote(self, symbol):
        return None, "no provider"

    def option_quotes(self, symbols):
        """{symbol: fields} for many contracts. Providers with a batch call override this (one request)."""
        out, err = {}, None
        for s in symbols:
            q, e = self.option_quote(s)
            if q:
                out[s] = q
            err = err or e
        return out, err

    def chain(self, ticker, side, first, through=None):
        return None, "no provider"


class SchwabREST(Provider):
    """Schwab REST (pricehistory / quotes / chains). Used for backfill always, and live when streaming is off."""
    name = "Schwab REST"
    executable = True

    def bars_1m(self, ticker):
        """Deep history once (about 30 calendar days: the noise band needs 14 full prior sessions, RVOL 10), then
        only the last 2 days on each refresh; upsert_bars merges them."""
        import schwab
        _status["rest_calls"] += 1
        with _lock:
            have = _bars.get(ticker)
            sessions = len(set(have.index.date)) if have is not None and len(have) else 0
        key = (ticker, now().date())
        if sessions < 16 and key not in _deep_done:
            _deep_done.add(key)                      # once per ticker per day, even if Schwab has less history
            end = now().to_pydatetime() + pd.Timedelta(minutes=1)
            df = schwab.bars_1m_range(ticker, end - pd.Timedelta(days=30), end)
            if df is not None and len(df):
                return df
        return schwab.bars_1m(ticker, days=2)

    def quote(self, ticker):
        import schwab
        j, err = schwab._get("/marketdata/v1/quotes", {"symbols": ticker.upper(), "fields": "quote"})
        q = ((j or {}).get(ticker.upper()) or {}).get("quote") or {}
        if not q:
            return None
        return {"bid": schwab._num(q.get("bidPrice")), "ask": schwab._num(q.get("askPrice")),
                "last": schwab._num(q.get("lastPrice")), "bid_size": q.get("bidSize"), "ask_size": q.get("askSize"),
                "quote_time": _ms(q.get("quoteTime")), "trade_time": _ms(q.get("tradeTime")),
                "total_volume": q.get("totalVolume"), "src": self.name}

    def option_quote(self, symbol):
        import schwab
        root = symbol[:-15]
        padded = root.ljust(6) + symbol[-15:]
        j, err = schwab._get("/marketdata/v1/quotes", {"symbols": padded, "fields": "quote"})
        q = ((j or {}).get(padded) or (j or {}).get(symbol) or {}).get("quote") or {}
        if not q:
            return None, err or "no quote"
        return self._opt_fields(q), None

    def option_quotes(self, symbols):
        """v3.4: up to 100 contracts per request (the lab's open trades in one call instead of one call each)."""
        import schwab
        out, err = {}, None
        syms = list(dict.fromkeys(symbols))
        for i in range(0, len(syms), 100):
            part = syms[i:i + 100]
            padded = {s[:-15].ljust(6) + s[-15:]: s for s in part}
            j, e = schwab._get("/marketdata/v1/quotes", {"symbols": ",".join(padded), "fields": "quote"})
            err = err or e
            for k, v in (j or {}).items():
                s = padded.get(k) or (k if k in part else None)
                q = (v or {}).get("quote") or {}
                if s and q:
                    out[s] = self._opt_fields(q)
        return out, err

    def _opt_fields(self, q):
        import schwab
        return {"bid": schwab._num(q.get("bidPrice")), "ask": schwab._num(q.get("askPrice")),
                "last": schwab._num(q.get("lastPrice")), "bid_size": q.get("bidSize"), "ask_size": q.get("askSize"),
                "delta": schwab._num(q.get("delta")), "gamma": schwab._num(q.get("gamma")),
                "theta": schwab._num(q.get("theta")), "iv": _iv(schwab._num(q.get("volatility"))),
                "quote_time": _ms(q.get("quoteTime")), "trade_time": _ms(q.get("tradeTime")),
                "multiplier": 100, "src": self.name}

    def chain(self, ticker, side, first, through=None):
        import schwab
        return schwab.chain(ticker, side, first, through)


class Fallback(Provider):
    """Only while Schwab is not connected. Labeled FALLBACK everywhere; never executable."""
    name = "FALLBACK (Yahoo bars / Alpaca IEX) - not executable"
    executable = False

    def bars_1m(self, ticker):
        import chartdata
        m1 = chartdata._dl(ticker, "5d", "1m", True)
        if m1 is None or m1.empty:
            return None
        return m1.tz_convert(core.ET) if m1.index.tz is not None else m1.tz_localize(core.ET)

    def quote(self, ticker):
        import broker
        if not broker.configured():
            return None
        last, _ = broker.stock_last(ticker)
        if not last or not last.get("price"):
            return None
        return {"last": float(last["price"]), "bid": None, "ask": None, "trade_time": _iso(last.get("ts")),
                "quote_time": None, "src": "Alpaca IEX (one exchange)"}

    def option_quote(self, symbol):
        import broker
        if not broker.configured():
            return None, "no fallback option source"
        q, err = broker.option_quote(symbol)
        if not q:
            return None, err
        return {"bid": q["bid"], "ask": q["ask"], "quote_time": _iso(q.get("ts")), "src": "Alpaca indicative (delayed)",
                "multiplier": 100}, None

    def chain(self, ticker, side, first, through=None):
        import broker
        return broker.chain(ticker, side, first, through) if through else broker.chain(ticker, side, first)


def use(provider):
    """Tests inject a fake provider; production picks Schwab when connected."""
    global _provider
    _provider = provider
    with _lock:
        _bars.clear()
        _quotes.clear()
        _frames.clear()
        _ver.clear()
        _deep_done.clear()
        _rest_at.clear()
        _prov.clear()


def provider():
    if _provider is not None:
        return _provider
    import schwab
    if not schwab.ready():
        return Fallback()
    p = SchwabREST()
    try:
        import schwab_stream
        p.streaming = schwab_stream.healthy()
    except Exception:
        p.streaming = False
    if p.streaming:
        p.name = "Schwab stream"
    return p


def executable():
    return bool(provider().executable)


# ---------------------------------------------------------------- helpers
def _ms(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return pd.Timestamp(v, unit="ms", tz="UTC").tz_convert(core.ET) if v > 0 else None


def _iso(v):
    try:
        return pd.Timestamp(v).tz_convert(core.ET) if v else None
    except Exception:
        return None


def _iv(v):
    return None if v is None else (v / 100 if v > 3 else v)


def now():
    return pd.Timestamp(core.now_et())


def record_latency(kind, seconds):
    if seconds is not None and seconds == seconds:
        _lat[kind].append(float(seconds))


def latency_stats():
    out = {}
    for k, d in _lat.items():
        if d:
            s = sorted(d)
            out[k] = {"n": len(s), "p50_s": round(s[len(s) // 2], 3), "p95_s": round(s[int(len(s) * 0.95) - 1 if len(s) > 1 else 0], 3),
                      "max_s": round(s[-1], 3)}
    return out


# ---------------------------------------------------------------- bar store
COLS = ["Open", "High", "Low", "Close", "Volume"]


def _norm_index(df):
    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_convert(core.ET) if idx.tz is not None else idx.tz_localize(core.ET)
    out = df[COLS].astype(float).copy()
    out.index = idx
    return out


def upsert_bars(ticker, df, src):
    """Merge provider bars. A bar for the same minute REPLACES the stored one (corrections, stream updates)."""
    if df is None or not len(df):
        return 0
    t = now()
    with _lock:
        old = _bars.get(ticker)
        if old is not None and len(old) and old.attrs.get("src") == src:
            df = df[df.index >= old.index[-1] - pd.Timedelta(minutes=3)]   # same source: only the newest rows can change
        new = _norm_index(df)
        new["src"], new["recv"] = src, t
        if old is None or not len(old):
            merged = new
        else:
            merged = pd.concat([old[~old.index.isin(new.index)], new]).sort_index()
        merged.attrs["src"] = src
        _bars[ticker] = merged
        _ver[ticker] = _ver.get(ticker, 0) + 1
    return len(new)


def upsert_stream_bar(ticker, open_ms, o, h, l, c, v, seq=None):
    ts = pd.Timestamp(open_ms, unit="ms", tz="UTC").tz_convert(core.ET)
    t = now()
    row = pd.DataFrame({"Open": [o], "High": [h], "Low": [l], "Close": [c], "Volume": [float(v or 0)]}, index=pd.DatetimeIndex([ts]))
    with _lock:
        old = _bars.get(ticker)
        row["src"], row["recv"] = "Schwab stream", t
        merged = row if old is None or not len(old) else pd.concat([old[old.index != ts], row]).sort_index()
        merged.attrs["src"] = "Schwab stream"
        _bars[ticker] = merged
        _ver[ticker] = _ver.get(ticker, 0) + 1
    record_latency("bar", (t - (ts + pd.Timedelta(minutes=1))).total_seconds())
    _status["last_msg"] = t


def bars(ticker, refresh=True):
    """(final_1m_df, forming_bar_dict_or_None, meta). Pulls from the provider on demand (REST/fallback/fake)."""
    p = provider()
    if refresh and _needs_rest(ticker, p):
        try:
            df = p.bars_1m(ticker)
            if df is not None and len(df):
                upsert_bars(ticker, df, p.name)
        except Exception as e:
            _status["last_error"] = f"bars {ticker}: {type(e).__name__}"
    with _lock:
        full = _bars.get(ticker)
    if full is None or not len(full):
        return None, None, {"ticker": ticker, "provider": p.name, "executable": p.executable, "error": "no bars"}
    t = now()
    newest = full.index[-1]
    df = full[COLS]
    forming = None
    if newest + pd.Timedelta(minutes=1) + pd.Timedelta(seconds=FINAL_GRACE_S) > t:
        forming = dict(full.iloc[-1][COLS].to_dict(), open_time=newest.isoformat(), src=full["src"].iloc[-1])
        df = df.iloc[:-1]
    srcs = sorted(set(full["src"].iloc[-30:]))
    last_final = df.index[-1] if len(df) else None
    age = (t - (last_final + pd.Timedelta(minutes=1))).total_seconds() if last_final is not None else None
    meta = {"ticker": ticker, "provider": p.name, "sources": srcs, "executable": p.executable,
            "last_final_open": last_final.isoformat() if last_final is not None else None,
            "bar_age_s": round(age, 1) if age is not None else None, "forming": bool(forming),
            "gaps_rth_today": gaps(df)}
    return df, forming, meta


def _needs_rest(ticker, p):
    """REST refresh unless the stream already carries this ticker with fresh bars. Any ticker the stream doesn't
    carry (a scanner name, a searched symbol) still gets REST bars, at most every REST_MIN_REFRESH_S seconds."""
    if _provider is not None:                        # tests / replay: the injected provider decides
        return not getattr(p, "streaming", False)
    if getattr(p, "streaming", False):
        try:
            import schwab_stream
            carried = ticker in schwab_stream._state["subscribed_eq"]
        except Exception:
            carried = False
        with _lock:
            have = _bars.get(ticker)
        fresh = have is not None and len(have) and (now() - have.index[-1]).total_seconds() < 180
        if carried and fresh:
            return False
        if carried and time.time() - _rest_at.get(ticker, 0) < 30:     # streamed but quiet (thin name): check now and then
            return False
    last = _rest_at.get(ticker, 0)
    if time.time() - last < REST_MIN_REFRESH_S:
        return False
    _rest_at[ticker] = time.time()
    return True


def _prov_update(symbol, price, trade_time):
    """Provisional candle for the minute in progress, from trade prices the stream reported. High/low can miss
    trades between updates, and there is NO volume (level-one data can't give per-minute volume honestly)."""
    if price is None or trade_time is None or any(ch.isdigit() for ch in symbol):
        return
    b = pd.Timestamp(trade_time).floor("1min")
    with _lock:
        c = _prov.get(symbol)
        if c is None or c["open_time"] != b:
            if c is not None and b < c["open_time"]:
                return                                     # an out-of-order older trade never rewinds the candle
            _prov[symbol] = {"open_time": b, "Open": price, "High": price, "Low": price, "Close": price, "updates": 1,
                             "last_trade": trade_time}
        else:
            c.update(High=max(c["High"], price), Low=min(c["Low"], price), Close=price, updates=c["updates"] + 1,
                     last_trade=trade_time)


def provisional(ticker):
    """The provisional candle if no provider bar exists yet for that minute (and it is recent), else None."""
    with _lock:
        c = dict(_prov.get(ticker) or {})
        have = _bars.get(ticker)
    if not c:
        return None
    if have is not None and len(have) and have.index[-1] >= c["open_time"]:
        return None                                    # the real bar has arrived: it replaces the provisional one
    if (now() - c["open_time"]).total_seconds() > 150:
        return None
    return c


def gaps(df):
    """Missing minutes inside today's regular session so far (never silently filled)."""
    if df is None or not len(df):
        return []
    d = df.index[-1].date()
    r = df[(df.index.date == d)].between_time("09:30", "15:59")
    if len(r) < 2:
        return []
    full = pd.date_range(r.index[0], r.index[-1], freq="1min")
    miss = full.difference(r.index)
    return [m.strftime("%H:%M") for m in miss[:20]]


# ---------------------------------------------------------------- quotes
def merge_quote(symbol, fields, src):
    """Incremental level-one update: only the fields present change (omitted != zero)."""
    t = now()
    with _lock:
        q = _quotes.setdefault(symbol, {})
        q.update({k: v for k, v in fields.items() if v is not None})
        q["src"], q["recv"] = src, t
    if "stream" in str(src) and fields.get("last") is not None and fields.get("trade_time") is not None:
        _prov_update(symbol, fields["last"], fields["trade_time"])
    qt = fields.get("quote_time")
    if qt is not None:
        record_latency("quote", (t - qt).total_seconds())
    _status["last_msg"] = t


def quote(ticker):
    """Underlying quote with freshness. Stream copy if fresh, else a provider call."""
    p = provider()
    with _lock:
        q = dict(_quotes.get(ticker, {}))
    if not q or (now() - q.get("recv", now() - timedelta(days=1))).total_seconds() > 5:
        try:
            fq = p.quote(ticker)
        except Exception:
            fq = None
        if fq:
            merge_quote(ticker, fq, fq.get("src", p.name))
            with _lock:
                q = dict(_quotes.get(ticker, {}))
    return _label(q, MAX_EQ_QUOTE_AGE_S, p) if q else None


def option_quote(symbol):
    """Option quote with bid/ask/sizes/greeks when the source sends them, plus validity flags."""
    p = provider()
    with _lock:
        q = dict(_quotes.get(symbol, {}))
    if not q or (now() - q.get("recv", now() - timedelta(days=1))).total_seconds() > 5:
        try:
            fq, err = p.option_quote(symbol)
        except Exception as e:
            fq, err = None, type(e).__name__
        if fq:
            merge_quote(symbol, fq, fq.get("src", p.name))
            with _lock:
                q = dict(_quotes.get(symbol, {}))
        elif not q:
            return None, err
    return _label(q, MAX_OPT_QUOTE_AGE_S, p), None


def option_quotes(symbols, max_age_s=5):
    """v3.4: refresh every listed contract whose cached quote is older than max_age_s with ONE provider call, then
    return {symbol: labeled quote}. Streamed quotes that are fresh are used as they are."""
    p = provider()
    t = now()
    with _lock:
        stale = [s for s in symbols if (t - _quotes.get(s, {}).get("recv", t - timedelta(days=1))).total_seconds() > max_age_s]
    err = None
    if stale:
        try:
            got, err = p.option_quotes(stale)
        except Exception as e:
            got, err = {}, type(e).__name__
        for s, fq in (got or {}).items():
            merge_quote(s, fq, fq.get("src", p.name))
    out = {}
    with _lock:
        snap = {s: dict(_quotes[s]) for s in symbols if s in _quotes}
    for s, q in snap.items():
        out[s] = _label(q, MAX_OPT_QUOTE_AGE_S, p)
    return out, err


def option_quote_cached(symbol):
    """The last known quote, labeled, with no provider request (for page views of many paper trades)."""
    p = provider()
    with _lock:
        q = dict(_quotes.get(symbol, {}))
    return (_label(q, MAX_OPT_QUOTE_AGE_S, p), None) if q else (None, "no quote yet")


def _label(q, max_age, p):
    t = now()
    qt = q.get("quote_time")
    age = (t - qt).total_seconds() if qt is not None else None
    bid, ask = q.get("bid"), q.get("ask")
    problems = []
    if bid is None or ask is None:
        problems.append("missing bid/ask")
    elif bid < 0 or ask <= 0:
        problems.append("invalid price")
    elif bid > ask:
        problems.append("crossed (bid > ask)")
    if age is None:
        problems.append("no provider timestamp")
    elif age > max_age and core.session_info()["state"] in ("OPEN", "ORB FORMING", "NO NEW ENTRIES", "ALL OUT"):
        problems.append(f"stale ({age:.0f}s old)")
    out = dict(q)
    out.update(age_s=round(age, 1) if age is not None else None,
               executable=bool(p.executable and not problems and "FALLBACK" not in str(q.get("src", ""))),
               problems=problems, provider=p.name)
    if bid is not None and ask is not None and ask > 0 and bid <= ask:
        out["mid"] = round((bid + ask) / 2, 4)
        out["spread"] = round(ask - bid, 4)
        out["spread_pct"] = round((ask - bid) / ask * 100, 1)
    return out


# ---------------------------------------------------------------- status for the UI and Chart
def set_mode(mode, error=None):
    if _status["mode"] != mode:
        _status.update(mode=mode, since=now().isoformat(timespec="seconds"))
    if error:
        _status["last_error"] = error


def status():
    p = provider()
    import schwab
    st = dict(_status)
    st.update(provider=p.name, executable=p.executable, schwab=schwab.status() if _provider is None else {"state": "test"},
              stream=__import__("schwab_stream").state() if _provider is None else {"phase": "test"},
              latency=latency_stats())
    if st.get("last_msg") is not None:
        st["last_msg_age_s"] = round((now() - st["last_msg"]).total_seconds(), 1)
        st["last_msg"] = st["last_msg"].isoformat(timespec="seconds")
    st["live_label"] = ("LIVE (Schwab stream)" if st["mode"] == "stream" and p.executable else
                        "Schwab REST polling" if p.executable else "FALLBACK - not executable")
    return st
