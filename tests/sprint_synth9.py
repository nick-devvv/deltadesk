"""Synthetic market for the round-9 tests: deterministic daily and 1-minute stock bars, Black-Scholes option bars, an Alpaca
asset list and SEC EDGAR pages (form indexes, filing headers, company_tickers.json), served through fake HTTP functions in
the exact shapes tools/sprint_pull9.py reads. No network."""
import json
import math
import urllib.parse
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

import sprint_synth as SS  # noqa: F401  (puts the repo and tools/ on sys.path)
from sprint import bs, data, periods
from sprint import universe as U

ET = "America/New_York"
STOCKS = ("AAA", "BBB", "CCC", "DDD")                    # U-STK names (CCC is cheap: never passes the $5 filter)
NOT_COMMON = {"EEE": "Some Fund ETF", "FFF": "Big Corp Depositary Shares", "GGG": "Tiny Corp Warrants"}
CIK = {"AAA": 1001, "BBB": 1002, "CCC": 1003, "DDD": 1004}
ADJ = {"BBB": (date(2020, 6, 1), 4.0)}                   # a 4:1 split: raw prices before it are 4x the adjusted ones


def _seed(s):
    return sum((i + 1) * ord(c) for i, c in enumerate(s))


class Market:
    def __init__(self, a=date(2015, 11, 2), b=date(2026, 6, 30), cache_root=None):
        self.days = U.all_sessions_cal(a, b)
        self.pos = {d: k for k, d in enumerate(self.days)}
        self.cache_root = cache_root
        self._daily = {}
        self._minute = {}
        self.events = []                                 # (symbol, accepted datetime, items)
        self._build_events()

    # ------------------------------------------------------------ daily bars (split-adjusted; raw = adj x factor)
    def daily(self, sym):
        if sym in self._daily:
            return self._daily[sym]
        rng = np.random.default_rng(_seed(sym))
        n = len(self.days)
        px0 = 3.0 if sym == "CCC" else (40.0 + _seed(sym) % 200)
        r = rng.normal(0.0004, 0.012, n)
        gaps = np.zeros(n)
        if sym in STOCKS:
            gi = rng.choice(np.arange(30, n), size=n // 25, replace=False)
            gaps[gi] = rng.choice([-1.0, 1.0], len(gi)) * rng.uniform(0.03, 0.06, len(gi))
        c = np.empty(n)
        o = np.empty(n)
        prev = px0
        for k in range(n):
            o[k] = prev * (1 + gaps[k] + rng.normal(0, 0.002))
            c[k] = o[k] * (1 + r[k] + 0.6 * gaps[k])
            prev = c[k]
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.004, n)))
        lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.004, n)))
        v = rng.integers(2_000_000, 4_000_000, n).astype(float) * (1 + 3 * (gaps != 0))
        df = pd.DataFrame({"day": self.days, "o": o.round(2), "h": h.round(2), "l": lo.round(2), "c": c.round(2), "v": v, "gap": gaps})
        self._daily[sym] = df
        return df

    def factor(self, sym, d):
        sp = ADJ.get(sym)
        return sp[1] if sp and d < sp[0] else 1.0

    def daily_rows(self, sym, a, b, adj):
        df = self.daily(sym)
        sel = df[(df["day"] >= a) & (df["day"] <= b)]
        out = []
        for r in sel.itertuples():
            f = 1.0 if adj == "split" else self.factor(sym, r.day)
            out.append({"t": f"{r.day}T05:00:00Z" if not _dst(r.day) else f"{r.day}T04:00:00Z", "o": round(r.o * f, 2), "h": round(r.h * f, 2),
                        "l": round(r.l * f, 2), "c": round(r.c * f, 2), "v": float(r.v / f), "n": 100, "vw": round(r.c * f, 2)})
        return out

    # ------------------------------------------------------------ 1-minute bars (split-adjusted)
    def minute(self, sym, d):
        k = (sym, d)
        if k in self._minute:
            return self._minute[k]
        if self.cache_root is not None and sym in ("SPY", "QQQ", "IWM"):
            df = data.read_stock(sym, d, d, self.cache_root)
            if df is not None and len(df):
                m = (df["ts"].dt.hour * 60 + df["ts"].dt.minute).to_numpy() - 570
                keep = (m >= 0) & (m < 390)
                g = np.full((390, 5), np.nan)
                g[m[keep]] = df[["o", "h", "l", "c", "v"]].to_numpy(float)[keep]
                self._minute[k] = g
                return g
        dd = self.daily(sym)
        i = self.pos.get(d)
        row = dd.iloc[i]
        rng = np.random.default_rng(_seed(sym) * 1000 + i)
        o0, c1 = float(row.o), float(row.c)
        steps = rng.normal(0, 0.0006, 390)
        path = o0 * np.exp(np.cumsum(steps))
        path = path + (c1 - path[-1]) * np.linspace(0, 1, 390)
        if row.gap != 0:                                  # event days: the first 15 minutes move with the gap
            path[:15] = o0 * (1 + np.sign(row.gap) * np.linspace(0.001, 0.01, 15))
            path[15:] = path[15:] + (path[14] - path[15])
        op = np.concatenate([[o0], path[:-1]])
        g = np.empty((390, 5))
        g[:, 0], g[:, 3] = op, path
        g[:, 1] = np.maximum(op, path) * (1 + 0.0003)
        g[:, 2] = np.minimum(op, path) * (1 - 0.0003)
        vol = np.full(390, float(row.v) * 0.55 / 375)
        vol[:15] = float(row.v) * 0.03 if row.gap != 0 else float(row.v) * 0.003
        g[:, 4] = vol
        self._minute[k] = g
        return g

    def minute_rows(self, sym, d, m0, m1):
        g = self.minute(sym, d)
        out = []
        t0 = pd.Timestamp(f"{d} 09:30", tz=ET)
        for i in range(max(0, m0), min(390, m1)):
            if np.isnan(g[i, 3]):
                continue
            out.append({"t": (t0 + pd.Timedelta(minutes=i)).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), "o": round(g[i, 0], 2),
                        "h": round(g[i, 1], 2), "l": round(g[i, 2], 2), "c": round(g[i, 3], 2), "v": float(round(g[i, 4])), "n": 10,
                        "vw": round(g[i, 3], 2)})
        return out

    # ------------------------------------------------------------ options
    def option_rows(self, occ, d, m0, m1):
        meta = data.parse_occ(occ)
        if not meta or meta["expiry"] < d:
            return []
        under = meta["root"]
        if under not in ("SPY", "QQQ", "IWM", "DIA") and under not in STOCKS and under not in U.U_ETF:
            return []
        K = meta["strike"]
        g = self.minute(under, d)
        if np.isnan(g[:, 3]).all():
            return []
        ref = float(np.nanmean(g[:, 3]))
        grid = 1.0 if under in U.U_ETF else (2.5 if ref >= 25 else 0.5)
        if abs(K / grid - round(K / grid)) > 1e-6:
            return []
        if under not in U.U_ETF and meta["expiry"].weekday() != 4 and not _holiday_thursday(meta["expiry"]):
            return []
        iv = 0.18 if under in U.U_ETF else 0.40
        extra = 1440 * (meta["expiry"] - d).days
        i = np.arange(max(0, m0), min(390, m1))
        if not len(i):
            return []
        S0, S1 = g[i, 0], g[i, 3]
        ok = ~np.isnan(S1)
        i, S0, S1 = i[ok], S0[ok], S1[ok]
        Ta = np.maximum(390 - i + extra, bs.MIN_T_MIN) / bs.YEAR_MIN
        Tb = np.maximum(390 - i - 1 + extra, bs.MIN_T_MIN) / bs.YEAR_MIN
        call = meta["right"] == "C"
        po, pc = bs.price_v(S0, K, Ta, iv, call), bs.price_v(S1, K, Tb, iv, call)
        keep = np.maximum(po, pc) >= 0.01
        base = pd.Timestamp(f"{d} 09:30", tz=ET).tz_convert("UTC")
        out = []
        for ii, a, b in zip(i[keep], po[keep], pc[keep]):
            out.append({"t": (base + pd.Timedelta(minutes=int(ii))).strftime("%Y-%m-%dT%H:%M:%SZ"), "o": round(max(a, 0.01), 2),
                        "h": round(max(a, b) * 1.01, 2), "l": round(max(min(a, b) * 0.99, 0.01), 2), "c": round(max(b, 0.01), 2),
                        "v": 10.0, "n": 3, "vw": round(b, 2)})
        return out

    # ------------------------------------------------------------ EDGAR
    def _build_events(self):
        for sym in STOCKS:
            dd = self.daily(sym)
            for r in dd.itertuples():
                if r.gap != 0:
                    acc = datetime(r.day.year, r.day.month, r.day.day, 7, 5, 0)
                    self.events.append((sym, acc, ["8.01"]))
            for k, r in enumerate(dd.itertuples()):
                if periods.DEV[0] <= r.day <= periods.DEV[1] and k % 63 == 40:
                    self.events.append((sym, datetime(r.day.year, r.day.month, r.day.day, 16, 5, 0), ["2.02", "9.01"]))

    def filed(self, acc):
        d = acc.date()
        if (acc.hour, acc.minute) >= (17, 30) or d.weekday() >= 5:
            d += timedelta(days=1)
            while d.weekday() >= 5:
                d += timedelta(days=1)
        return d

    def index_text(self, d):
        rows = [(s, a, it) for s, a, it in self.events if self.filed(a) == d]
        if not rows and d.weekday() >= 5:
            return None
        L = ["Description:           Daily Index of EDGAR Dissemination Feed by Form Type", "", "",
             "Form Type   Company Name                                                  CIK         Date Filed  File Name",
             "-" * 140]
        for s, a, it in rows:
            acc = self.acc(s, a)
            L.append(f"{'8-K':<12}{s + ' CORP':<62}{CIK[s]:<12}{d:%Y%m%d}    edgar/data/{CIK[s]}/{acc}.txt")
        L.append(f"{'10-Q':<12}{'OTHER CORP':<62}{9999:<12}{d:%Y%m%d}    edgar/data/9999/0000009999-24-000001.txt")
        return "\n".join(L) + "\n"

    def acc(self, s, a):
        return f"{CIK[s]:010d}-{a:%y}-{a:%m%d%H}"[:20]

    def header_text(self, cik, acc):
        for s, a, it in self.events:
            if CIK[s] == cik and self.acc(s, a) == acc:
                titles = {"2.02": "Results of Operations and Financial Condition", "9.01": "Financial Statements and Exhibits",
                          "8.01": "Other Events"}
                lines = [f"&lt;ACCEPTANCE-DATETIME&gt;{a:%Y%m%d%H%M%S}", f"ACCESSION NUMBER:\t\t{acc}", "CONFORMED SUBMISSION TYPE:\t8-K"]
                lines += [f"ITEM INFORMATION:\t\t{titles[i]}" for i in it]
                return "<html><body><pre>\n" + "\n".join(lines) + "\n</pre></body></html>"
        return None

    def tickers(self):
        return {str(k): {"cik_str": CIK[s], "ticker": s, "title": s + " CORP"} for k, s in enumerate(STOCKS)}

    def assets(self):
        out = [{"symbol": s, "class": "us_equity", "status": "active", "tradable": True, "exchange": "NYSE",
                "attributes": ["has_options"], "name": f"{s} Corp Common Stock"} for s in STOCKS]
        out += [{"symbol": s, "class": "us_equity", "status": "active", "tradable": True, "exchange": "NASDAQ",
                 "attributes": ["has_options"], "name": n} for s, n in NOT_COMMON.items()]
        out += [{"symbol": "SPY", "class": "us_equity", "status": "active", "tradable": True, "exchange": "ARCA",
                 "attributes": ["has_options"], "name": "SPDR S&P 500 ETF Trust"},
                {"symbol": "HHH", "class": "us_equity", "status": "active", "tradable": True, "exchange": "NYSE", "attributes": [],
                 "name": "No Options Inc Common Stock"}]
        return out


def _dst(d):
    return pd.Timestamp(f"{d} 12:00", tz=ET).utcoffset() == pd.Timedelta(hours=-4)


def _holiday_thursday(d):
    return d.weekday() == 3 and (d + timedelta(days=1)).isoformat() in periods.holidays()


def _et(ts):
    return pd.Timestamp(ts).tz_convert(ET)


class FakeAlpaca:
    """Replaces pull_alpaca._http: serves /v2/stocks/bars (1Day / 1Min, multi-symbol) and /v1beta1/options/bars."""

    def __init__(self, market, fail_after=None):
        self.m, self.calls, self.fail_after = market, [], fail_after

    def __call__(self, url, headers):
        assert url.startswith("https://data.alpaca.markets/"), url
        self.calls.append(url)
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise ConnectionError("simulated drop")
        u = urllib.parse.urlparse(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        a, b = _et(q["start"]), _et(q["end"])
        for d in pd.date_range(a.normalize(), b.normalize()):
            hit = periods.overlaps(d.date(), d.date())
            assert not hit or (d.date() == b.date() and b.hour == 0 and b.minute == 0), f"locked date requested: {url}"
        syms = q["symbols"].split(",")
        out = {}
        if u.path == "/v2/stocks/bars" and q["timeframe"] == "1Day":
            for s in syms:
                out[s] = self.m.daily_rows(s, a.date(), (b - pd.Timedelta(minutes=1)).date(), q.get("adjustment", "raw"))
        elif u.path == "/v2/stocks/bars":
            d = a.date()
            m0 = a.hour * 60 + a.minute - 570
            m1 = b.hour * 60 + b.minute - 570
            for s in syms:
                out[s] = self.m.minute_rows(s, d, m0, m1)
        elif u.path == "/v1beta1/options/bars":
            d = a.date()
            m0 = a.hour * 60 + a.minute - 570
            m1 = b.hour * 60 + b.minute - 570
            for s in syms:
                rows = self.m.option_rows(s, d, m0, m1)
                if rows:
                    out[s] = rows
        else:
            raise AssertionError(url)
        return {"bars": out, "next_page_token": None}


class FakeSEC:
    """http(url) -> (status, text) for the EDGAR URLs sprint/edgar builds."""

    def __init__(self, market, fail_codes=None):
        self.m, self.calls, self.fail_codes = market, [], list(fail_codes or [])

    def __call__(self, url):
        self.calls.append(url)
        if self.fail_codes:
            return self.fail_codes.pop(0), ""
        if url.endswith("company_tickers.json"):
            return 200, json.dumps(self.m.tickers())
        if "/daily-index/" in url and url.endswith("/index.json"):
            return 404, ""                                  # no quarter listing: the pull asks for every weekday, as before
        if "/daily-index/" in url:
            d = datetime.strptime(url.rsplit("form.", 1)[1][:8], "%Y%m%d").date()
            assert not periods.overlaps(d, d), url
            t = self.m.index_text(d)
            return (200, t) if t else (404, "")
        if url.endswith("-index-headers.html"):
            parts = url.split("/")
            cik, acc = int(parts[-3]), parts[-1].replace("-index-headers.html", "")
            t = self.m.header_text(cik, acc)
            return (200, t) if t else (404, "")
        return 404, ""


class NoThrottle:
    def __init__(self):
        self.calls = 0

    def wait(self):
        self.calls += 1
