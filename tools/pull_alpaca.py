#!/usr/bin/env python3
"""tools/pull_alpaca.py - READ-ONLY Alpaca market-data loader for the v4 backtests (runs on Chart's computer; Claude's
cloud workspace can't reach Alpaca). It only ever calls https://data.alpaca.markets (market data). It never calls
the trading API (paper-api / api.alpaca.markets): no orders, no account, no positions, not even contract listings.

  python3 tools/pull_alpaca.py stocks  --symbols SPY,QQQ --from 2016-01-01 --to 2026-10-30
  python3 tools/pull_alpaca.py options --underlying SPY,QQQ --from 2024-02-01 --to 2026-10-30 [--band 0.03] [--trades]
  python3 tools/pull_alpaca.py gaps    --symbols SPY,QQQ --from 2016-01-01 --to 2026-10-30

Keys: ALPACA_KEY / ALPACA_SECRET (the desk's paper key; market data only). Stock bars: 1-minute, raw (unadjusted),
feed "sip" by default (--feed iex if the plan refuses SIP).
Cache (data/ is gitignored):
  data/alpaca/stocks/<SYM>/<YYYY-MM>.csv.gz            one file per month, ET timestamps
  data/alpaca/options/<UNDER>/<YYYY-MM-DD>/bars.csv.gz  0DTE contracts for that day (and trades.csv.gz with --trades)
Resumable: a finished month/day writes a .done marker next to its file and is skipped next time (the current month and
today are never marked done). Option symbols are generated from the day's own stock range (every $1 strike within
--band of the open and the day's high/low, calls and puts, that day's expiry); contracts that didn't exist return no
data. The gap report lists weekdays with no bars and sessions with missing regular-hours minutes, plus the known Alpaca
option-data gaps (2024-02-26, 2024-03-15).
"""
import argparse
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import core  # noqa: E402

DATA_HOST = "https://data.alpaca.markets"
ROOT = HERE / "data" / "alpaca"
MAX_PER_MIN = 180                      # free plan allows 200 requests a minute
KNOWN_OPTION_GAPS = ("2024-02-26", "2024-03-15")
_calls = []


def _guard(url):
    if not url.startswith(DATA_HOST + "/"):
        raise RuntimeError(f"REFUSED: pull_alpaca only reads {DATA_HOST} (market data), never {url.split('?')[0]}")
    return url


def _default_http(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


_http = _default_http                  # tests replace this


def _throttle():
    now = time.time()
    while _calls and now - _calls[0] > 60:
        _calls.pop(0)
    if len(_calls) >= MAX_PER_MIN:
        time.sleep(max(0.0, 60 - (now - _calls[0])) + 0.05)
    _calls.append(time.time())


def get(path, params):
    """GET a market-data path with pagination; yields each page's JSON. Retries 429/5xx with backoff."""
    key, sec = os.environ.get("ALPACA_KEY"), os.environ.get("ALPACA_SECRET")
    if not key or not sec:
        raise RuntimeError("ALPACA_KEY / ALPACA_SECRET are not set (the desk's paper key, market data only)")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec, "Accept": "application/json"}
    token = None
    while True:
        p = dict(params, **({"page_token": token} if token else {}))
        url = _guard(f"{DATA_HOST}{path}?{urllib.parse.urlencode(p)}")
        for attempt in range(5):
            _throttle()
            try:
                j = _http(url, headers)
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise
        yield j
        token = j.get("next_page_token")
        if not token:
            return


def _frame(bars):
    if not bars:
        return pd.DataFrame(columns=["ts", "o", "h", "l", "c", "v", "n", "vw"])
    df = pd.DataFrame(bars).rename(columns={"t": "ts"})
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(core.ET)
    return df


def _write_gz(path, df):
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    if "ts" in out and len(out):
        out["ts"] = out["ts"].map(lambda t: t.isoformat())
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
        g.write(out.to_csv(index=False).encode())
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(buf.getvalue())
    tmp.replace(path)


def read_gz(path):
    df = pd.read_csv(path, compression="gzip")
    if "ts" in df and len(df):
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(core.ET)
    return df


def _months(a, b):
    m = date(a.year, a.month, 1)
    while m <= b:
        nxt = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
        yield m, min(b, nxt - timedelta(days=1))
        m = nxt


# ---------------------------------------------------------------- stocks
def pull_stock(sym, a, b, feed="sip", today=None):
    """1-minute bars for one symbol, month by month. Returns {"pulled": months, "skipped": months, "rows": n}."""
    today = today or date.today()
    out = {"pulled": 0, "skipped": 0, "rows": 0}
    for m0, m1 in _months(a, b):
        f = ROOT / "stocks" / sym / f"{m0:%Y-%m}.csv.gz"
        done = f.with_suffix(".done")
        if done.exists():
            out["skipped"] += 1
            continue
        bars = []
        for page in get(f"/v2/stocks/{sym}/bars", {"timeframe": "1Min", "start": f"{m0}T00:00:00Z",
                                                   "end": f"{m1 + timedelta(days=1)}T00:00:00Z", "limit": 10000,
                                                   "adjustment": "raw", "feed": feed, "sort": "asc"}):
            bars += page.get("bars") or []
        df = _frame(bars)
        _write_gz(f, df)
        out["pulled"] += 1
        out["rows"] += len(df)
        month_end = date(m0.year + (m0.month == 12), m0.month % 12 + 1, 1) - timedelta(days=1)
        if m1 == month_end and month_end < today:              # a whole month, fully in the past: never pulled again
            done.write_text(json.dumps({"rows": len(df), "at": datetime.now().isoformat(timespec="seconds"), "feed": feed}))
    return out


def load_stock(sym, a, b):
    parts = [read_gz(p) for p in sorted((ROOT / "stocks" / sym).glob("*.csv.gz"))
             if a.strftime("%Y-%m") <= p.name[:7] <= b.strftime("%Y-%m")]
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True)
    return df[(df["ts"].dt.date >= a) & (df["ts"].dt.date <= b)]


# ---------------------------------------------------------------- options
def occ(under, d, right, strike):
    return f"{under}{d:%y%m%d}{right}{int(round(strike * 1000)):08d}"


def symbols_for_day(under, d, day_bars, band=0.03):
    """0DTE OCC symbols for every $1 strike within `band` of the open and the day's high/low (from the day's bars)."""
    r = day_bars[(day_bars["ts"].dt.strftime("%H:%M") >= "09:30") & (day_bars["ts"].dt.strftime("%H:%M") < "16:00")]
    if not len(r):
        return []
    o, hi, lo = float(r["o"].iloc[0]), float(r["h"].max()), float(r["l"].min())
    k0, k1 = int(min(o * (1 - band), lo)), int(max(o * (1 + band), hi)) + 1
    return [occ(under, d, side, k) for k in range(k0, k1 + 1) for side in ("C", "P")]


def pull_options_day(under, d, syms, trades=False, today=None):
    today = today or date.today()
    folder = ROOT / "options" / under / d.isoformat()
    done = folder / ".done"
    if done.exists():
        return {"skipped": 1, "bars": 0, "trades": 0}
    res = {"skipped": 0, "bars": 0, "trades": 0}
    kinds = [("bars", "/v1beta1/options/bars", {"timeframe": "1Min"})] + ([("trades", "/v1beta1/options/trades", {})] if trades else [])
    for kind, path, extra in kinds:
        rows = []
        for i in range(0, len(syms), 100):
            part = syms[i:i + 100]
            for page in get(path, dict(extra, symbols=",".join(part), start=f"{d}T13:00:00Z", end=f"{d + timedelta(days=1)}T01:00:00Z",
                                       limit=10000, sort="asc")):
                for s, lst in (page.get(kind) or {}).items():
                    rows += [dict(x, symbol=s) for x in lst or []]
        df = _frame(rows)
        _write_gz(folder / f"{kind}.csv.gz", df)
        res[kind] = len(df)
    if d < today:
        done.write_text(json.dumps({**res, "symbols": len(syms), "at": datetime.now().isoformat(timespec="seconds")}))
    return res


def pull_options(under, a, b, band=0.03, trades=False, today=None):
    """Needs the underlying's stock bars for those days in the cache (pull stocks first)."""
    out = {"days": 0, "skipped": 0, "no_stock_bars": [], "bars": 0, "trades": 0}
    stock = load_stock(under, a, b)
    d = a
    while d <= b:
        if d.weekday() < 5:
            day_bars = stock[stock["ts"].dt.date == d] if stock is not None else None
            if day_bars is None or not len(day_bars):
                out["no_stock_bars"].append(d.isoformat())
            else:
                r = pull_options_day(under, d, symbols_for_day(under, d, day_bars, band), trades, today)
                out["skipped"] += r["skipped"]
                out["days"] += 0 if r["skipped"] else 1
                out["bars"] += r["bars"]
                out["trades"] += r["trades"]
        d += timedelta(days=1)
    return out


# ---------------------------------------------------------------- gap report
def gap_report(sym, a, b, holidays=None):
    """Weekdays with no bars (holiday or data gap) and sessions missing regular-hours minutes. Early closes show as
    short sessions; holidays outside core.HOLIDAYS (before 2026) appear as 'no bars' and must be read with a calendar."""
    hol = set(holidays or core.HOLIDAYS)
    df = load_stock(sym, a, b)
    days = {} if df is None else {d: g for d, g in df.groupby(df["ts"].dt.date)}
    out = {"symbol": sym, "from": a.isoformat(), "to": b.isoformat(), "no_bars": [], "short_sessions": [], "sessions": 0,
           "known_option_gaps": list(KNOWN_OPTION_GAPS)}
    d = a
    while d <= b:
        if d.weekday() < 5 and d.isoformat() not in hol:
            g = days.get(d)
            if g is None:
                out["no_bars"].append(d.isoformat())
            else:
                out["sessions"] += 1
                rth = g[(g["ts"].dt.strftime("%H:%M") >= "09:30") & (g["ts"].dt.strftime("%H:%M") < "16:00")]
                if len(rth) < 390:
                    out["short_sessions"].append({"day": d.isoformat(), "rth_minutes": int(len(rth)), "missing": 390 - int(len(rth))})
        d += timedelta(days=1)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read-only Alpaca market-data loader (data.alpaca.markets only)")
    ap.add_argument("what", choices=["stocks", "options", "gaps"])
    ap.add_argument("--symbols", default="SPY,QQQ")
    ap.add_argument("--underlying", default="SPY,QQQ")
    ap.add_argument("--from", dest="a", required=True)
    ap.add_argument("--to", dest="b", required=True)
    ap.add_argument("--feed", default="sip", choices=["sip", "iex"])
    ap.add_argument("--band", type=float, default=0.03)
    ap.add_argument("--trades", action="store_true")
    x = ap.parse_args(argv)
    a, b = date.fromisoformat(x.a), date.fromisoformat(x.b)
    if x.what == "stocks":
        for s in x.symbols.split(","):
            print(s, pull_stock(s.strip().upper(), a, b, x.feed), flush=True)
    elif x.what == "options":
        for u in x.underlying.split(","):
            print(u, pull_options(u.strip().upper(), a, b, x.band, x.trades), flush=True)
    else:
        for s in x.symbols.split(","):
            r = gap_report(s.strip().upper(), a, b)
            print(json.dumps({k: (v if k not in ("no_bars", "short_sessions") else v[:50]) for k, v in r.items()}, indent=1),
                  f"\n{len(r['no_bars'])} weekdays without bars, {len(r['short_sessions'])} short sessions", flush=True)


if __name__ == "__main__":
    main()
