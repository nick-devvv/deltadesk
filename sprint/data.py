"""sprint/data.py - cached bar loader, per-symbol series and per-day context for the sprint engine. No network.

Cache layout (written by tools/sprint_pull.py, same as tools/pull_alpaca.py):
  data/alpaca/stocks/<SYM>/<YYYY-MM>.csv.gz              1-minute bars 04:00-20:00 ET (ts,o,h,l,c,v,...)
  data/alpaca/options/<SYM>/<YYYY-MM-DD>/bars.csv.gz     that day's 0DTE contracts, 1-minute bars (+ symbol)
  data/alpaca/options/<SYM>/<YYYY-MM-DD>/trades.csv.gz   optional: their trades (ts, p, s, ..., symbol)
Only dates inside the requested range are read (the runner passes a guarded range, see periods.guard).

Point-in-time convention: every per-minute array is indexed by the regular-hours bar index i (0 = the 09:30 bar,
389 = the 15:59 bar) and holds the value known at the END of bar i (bar i included, nothing later). Indicators that
continue across sessions (ATR 1m, EMA 9, MACD 1m, 5-minute ADX/DI and ATR) run on regular-hours bars only.
"""
import math
import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import fills
from .periods import early_closes

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "data" / "alpaca"
OCC_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")
N = 390


def parse_occ(sym):
    m = OCC_RE.match(str(sym))
    if not m:
        return None
    root, ymd, right, k = m.groups()
    return {"root": root, "expiry": date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6])), "right": right,
            "strike": int(k) / 1000.0}


def _read_gz(path):
    df = pd.read_csv(path, compression="gzip")
    if "ts" in df and len(df):
        df["ts"] = pd.to_datetime(df["ts"], utc=True, format="ISO8601").dt.tz_convert("America/New_York")
    return df


def _minutes(ts_str):
    """Minute index after 09:30 from the cache's ET ISO strings ('2024-08-01T09:31:00-04:00') without parsing dates."""
    s = ts_str.astype(str)
    return (s.str.slice(11, 13).astype(int) * 60 + s.str.slice(14, 16).astype(int)).to_numpy() - 570


def read_stock(sym, a, b, root=None):
    """1-minute stock bars for [a, b] from the monthly cache (only those months are opened)."""
    root = Path(root or ROOT)
    files = [p for p in sorted((root / "stocks" / sym).glob("*.csv.gz")) if a.strftime("%Y-%m") <= p.name[:7] <= b.strftime("%Y-%m")]
    parts = [_read_gz(p) for p in files]
    parts = [p for p in parts if len(p)]
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True)
    d = df["ts"].dt.date
    df = df[(d >= a) & (d <= b)].drop_duplicates("ts").sort_values("ts")
    return df.reset_index(drop=True)


# ---------------------------------------------------------------- indicator helpers on compact arrays
def _wilder(x, n):
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    prev = float(np.mean(x[:n]))
    out[n - 1] = prev
    for j in range(n, len(x)):
        prev = prev + (x[j] - prev) / n
        out[j] = prev
    return out


def _ema(x, n):
    out = np.empty(len(x))
    a = 2.0 / (n + 1)
    prev = np.nan
    for j, v in enumerate(x):
        prev = v if prev != prev else prev + a * (v - prev)
        out[j] = prev
    return out


class Series:
    """All regular-hours (and premarket summary) data of one symbol over a date range, with the cross-session
    indicators computed once."""

    def __init__(self, sym, df):
        self.sym = sym
        self.days = []
        self.rth = {}            # day -> (390, 5) O,H,L,C,V (NaN where no bar)
        self.pre = {}            # day -> (premarket high, low) from 04:00-09:29 bars, or None
        if df is None or not len(df):
            self.daily = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
            self._finish()
            return
        ts = df["ts"]
        mins = (ts.dt.hour * 60 + ts.dt.minute).to_numpy()
        dates = ts.dt.date.to_numpy()
        arr = df[["o", "h", "l", "c", "v"]].to_numpy(float)
        for d in sorted(set(dates)):
            sel = dates == d
            m = mins[sel]
            a = arr[sel]
            r = (m >= 570) & (m < 960)
            if not r.any():
                continue
            grid = np.full((N, 5), np.nan)
            grid[m[r] - 570] = a[r]
            self.rth[d] = grid
            p = (m >= 240) & (m < 570)
            self.pre[d] = (float(a[p, 1].max()), float(a[p, 2].min())) if p.any() else None
            self.days.append(d)
        rows = []
        for d in self.days:
            g = self.rth[d]
            ok = ~np.isnan(g[:, 3])
            rows.append({"day": d, "open": g[ok, 0][0], "high": np.nanmax(g[:, 1]), "low": np.nanmin(g[:, 2]),
                         "close": g[ok, 3][-1], "volume": np.nansum(g[:, 4]), "bars": int(ok.sum())})
        self.daily = pd.DataFrame(rows).set_index("day") if rows else pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        self._finish()

    def _finish(self):
        """Cross-session indicators on the compact regular-hours series (missing minutes skipped, then carried)."""
        self.atr1, self.ema9, self.hist1, self.vwap, self.vsd = {}, {}, {}, {}, {}
        self.adx, self.pdi, self.mdi, self.atr5, self.b5 = {}, {}, {}, {}, {}
        if not self.days:
            return
        H, L, C, V, owner, idx = [], [], [], [], [], []
        first = []
        for d in self.days:
            g = self.rth[d]
            ok = np.where(~np.isnan(g[:, 3]))[0]
            for k, i in enumerate(ok):
                H.append(g[i, 1]); L.append(g[i, 2]); C.append(g[i, 3]); V.append(g[i, 4])
                owner.append(d); idx.append(i); first.append(k == 0)
        H, L, C = np.array(H), np.array(L), np.array(C)
        pc = np.concatenate([[np.nan], C[:-1]])
        tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
        tr[np.array(first)] = (H - L)[np.array(first)]              # session reset: no overnight gap in the 1m ATR
        atr = _wilder(tr, 14)
        ema9 = _ema(C, 9)
        m = _ema(C, 12) - _ema(C, 26)
        s = _ema(m, 9)
        hist = m - s
        hist[:34] = np.nan                                            # warm-up (slow + signal - 1)
        for d in self.days:
            for name in ("atr1", "ema9", "hist1"):
                getattr(self, name)[d] = np.full(N, np.nan)
        for j, (d, i) in enumerate(zip(owner, idx)):
            self.atr1[d][i], self.ema9[d][i], self.hist1[d][i] = atr[j], ema9[j], hist[j]
        for d in self.days:                                           # carry the last known value over missing minutes
            for name in ("atr1", "ema9", "hist1"):
                a = getattr(self, name)[d]
                getattr(self, name)[d] = pd.Series(a).ffill().to_numpy()
            g = self.rth[d]
            tp = (g[:, 1] + g[:, 2] + g[:, 3]) / 3.0
            vol = np.nan_to_num(g[:, 4])
            tpz = np.nan_to_num(tp)
            cv = np.cumsum(vol)
            with np.errstate(invalid="ignore", divide="ignore"):
                vw = np.cumsum(tpz * vol) / cv
                var = np.cumsum(tpz * tpz * vol) / cv - vw * vw
            vw[cv <= 0] = np.nan
            self.vwap[d] = vw
            self.vsd[d] = np.sqrt(np.maximum(var, 0.0))
        # 5-minute bars anchored at 09:30, continuing ADX/DI(14) and ATR(14)
        b5_rows, owners = [], []
        for d in self.days:
            g = self.rth[d]
            bars = np.full((78, 5), np.nan)
            for b in range(78):
                w = g[b * 5:(b + 1) * 5]
                ok = ~np.isnan(w[:, 3])
                if ok.sum() == 5:                                     # a 5m bar needs all five minutes
                    bars[b] = [w[0, 0], w[:, 1].max(), w[:, 2].min(), w[4, 3], w[:, 4].sum()]
            self.b5[d] = bars
            for b in range(78):
                if not np.isnan(bars[b, 3]):
                    b5_rows.append(bars[b]); owners.append((d, b))
        if b5_rows:
            import indicators as I
            f = pd.DataFrame(b5_rows, columns=["Open", "High", "Low", "Close", "Volume"])
            adx, pdi, mdi = (x.to_numpy(float) for x in I.adx_di(f, 14))
            a5 = I.atr(f, 14).to_numpy(float)
            look = {o: j for j, o in enumerate(owners)}
            pos = 0
            for d in self.days:
                arrs = [np.full(N, np.nan) for _ in range(4)]
                while pos < len(owners) and owners[pos][0] < d:
                    pos += 1
                last = pos - 1 if pos > 0 else None                   # before today's first 5m bar: yesterday's last
                for i in range(N):
                    b = (i + 1) // 5 - 1                              # last 5m bar complete at the end of 1m bar i
                    if b >= 0 and (d, b) in look:
                        last = look[(d, b)]
                    if last is not None:
                        arrs[0][i], arrs[1][i], arrs[2][i], arrs[3][i] = adx[last], pdi[last], mdi[last], a5[last]
                self.adx[d], self.pdi[d], self.mdi[d], self.atr5[d] = arrs

    # ------------------------------------------------------------ prior-period lookups (strictly before `day`)
    def prev_day(self, day):
        k = self.days.index(day) if day in self.days else None
        if not k:
            return None
        p = self.days[k - 1]
        r = self.daily.loc[p]
        return {"day": p, "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])}

    def prev_week(self, day):
        """High/low of the previous Monday-Friday week's regular sessions (None if none in the data)."""
        monday = day - timedelta(days=day.weekday())
        a, b = monday - timedelta(days=7), monday - timedelta(days=1)
        w = self.daily[(self.daily.index >= a) & (self.daily.index <= b)] if len(self.daily) else self.daily
        if not len(w):
            return None
        return {"high": float(w["high"].max()), "low": float(w["low"].min())}

    def prior_days(self, day, n):
        k = self.days.index(day)
        return self.days[max(0, k - n):k]

    def sma_side(self, day, n=20, margin=0.0):
        """Side rule known before `day`'s open: +1 if the prior session's close is above the n-day SMA of closes
        ending at that close, -1 if below, 0 if equal (or, with a margin, if within +/-margin of the SMA; a close at
        least `margin` beyond it counts), None with fewer than n prior sessions."""
        prior = self.prior_days(day, n)
        if len(prior) < n:
            return None
        closes = self.daily.loc[prior, "close"].to_numpy(float)
        sma, last = float(closes.mean()), float(closes[-1])
        if margin:
            return 1 if last >= sma * (1 + margin) else -1 if last <= sma * (1 - margin) else 0
        return 1 if last > sma else -1 if last < sma else 0

    def daily_atr(self, day, n=14):
        """Wilder ATR(14) of daily regular-hours bars before `day` (None until 14 prior sessions)."""
        prior = self.prior_days(day, 60)
        if len(prior) < n + 1:
            return None
        d = self.daily.loc[prior]
        pc = d["close"].shift()
        tr = np.maximum(d["high"] - d["low"], np.maximum((d["high"] - pc).abs(), (d["low"] - pc).abs())).to_numpy()[1:]
        w = _wilder(tr, n)
        return float(w[-1]) if len(w) and not math.isnan(w[-1]) else None


class DayContext:
    """One symbol, one session: the stock arrays, indicators and that day's option tapes."""

    def __init__(self, series, day, tapes=None, spread=None, early_close=None, aux=None):
        self.series, self.sym, self.day = series, series.sym, day
        self.aux = aux or {}                                      # other symbols' Series (e.g. VIXY for the VIX proxy)
        g = series.rth[day]
        self.o, self.h, self.l, self.c, self.v = (g[:, k] for k in range(5))
        self.vwap, self.vsd = series.vwap[day], series.vsd[day]
        self.atr1, self.ema9, self.hist1 = series.atr1[day], series.ema9[day], series.hist1[day]
        self.adx, self.pdi, self.mdi, self.atr5 = (getattr(series, n).get(day, np.full(N, np.nan)) for n in ("adx", "pdi", "mdi", "atr5"))
        self.b5 = series.b5.get(day)
        self.tapes = tapes or {}
        self.spread = spread
        ec = early_closes() if early_close is None else ({day.isoformat()} if early_close else set())
        self.early = day.isoformat() in ec
        self.close_idx = 210 if self.early else N                   # 13:00 close -> 210 one-minute bars
        self._lv = None
        self._dt = None

    def has_bar(self, i):
        return 0 <= i < N and not math.isnan(self.c[i])

    def levels(self, fake_seed=None):
        from .levels import LevelMap
        if self._lv is None:
            self._lv = LevelMap.from_context(self)
        return self._lv if fake_seed is None else self._lv.fake(fake_seed)

    def daytype(self):
        from .daytype import DayType
        if self._dt is None:
            self._dt = DayType(self)
        return self._dt


# ---------------------------------------------------------------- options
def read_option_day(under, day, root=None, want_trades=True):
    """{symbol: OptionTape} for that day's 0DTE contracts (empty dict when the day has no option file)."""
    folder = Path(root or ROOT) / "options" / under / day.isoformat()
    f = folder / "bars.csv.gz"
    if not f.exists():
        return {}
    df = pd.read_csv(f, compression="gzip")
    if not len(df):
        return {}
    mi = _minutes(df["ts"])
    keep = (mi >= 0) & (mi < N)
    df, mi = df[keep], mi[keep]
    trades = {}
    tf = folder / "trades.csv.gz"
    if want_trades and tf.exists():
        t = pd.read_csv(tf, compression="gzip")
        if len(t):
            tm = _minutes(t["ts"])
            t = t.assign(_m=tm, _ns=pd.to_datetime(t["ts"], utc=True, format="ISO8601").astype("int64"))
            t = t.sort_values(["symbol", "_ns"], kind="stable")
            for s, g in t.groupby("symbol", sort=False):
                ok = (g["_m"] >= 0) & (g["_m"] < N)
                trades[s] = (g["_m"].to_numpy()[ok.to_numpy()], g["p"].to_numpy(float)[ok.to_numpy()])
    out = {}
    syms = df["symbol"].to_numpy()
    vals = df[["o", "h", "l", "c", "v"]].to_numpy(float)
    for s in pd.unique(syms):
        meta = parse_occ(s)
        if not meta or meta["expiry"] != day:
            continue
        sel = syms == s
        grid = np.full((N, 5), np.nan)
        grid[mi[sel]] = vals[sel]
        out[s] = fills.OptionTape(s, meta["right"], meta["strike"], *(grid[:, k] for k in range(5)), trades=trades.get(s))
    return out


def option_days(under, root=None):
    folder = Path(root or ROOT) / "options" / under
    if not folder.exists():
        return set()
    return {date.fromisoformat(p.name) for p in folder.iterdir() if p.is_dir() and (p / "bars.csv.gz").exists()}
