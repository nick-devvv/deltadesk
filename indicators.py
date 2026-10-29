"""indicators.py - deterministic indicators on validated, finalized UNDERLYING bars (no AI, no network).

Every function documents its formula, warm-up and missing-data behavior. Undefined values are None / NaN and
are never replaced by zero to let a trade pass. Bars are pandas DataFrames indexed by the bar's OPEN time
(America/New_York), columns Open/High/Low/Close/Volume. Volume = executed share volume as reported by the
provider for that bar (not dollar amount).

Smoothing conventions (checked against TA-Lib 0.8.3 in tests when it is installed):
  EMA  : alpha = 2/(n+1), seeded with the first value (pandas adjust=False). TA-Lib seeds with an SMA of the
         first n values, so early values differ; they converge after warm-up. MACD is marked unavailable for
         the first (slow + signal - 1) bars.
  ATR/ADX/DI : Wilder smoothing (alpha = 1/n) seeded with the simple mean of the first n values, like TA-Lib.
"""
import math

import numpy as np
import pandas as pd

RTH_OPEN, RTH_CLOSE = "09:30", "16:00"


# ---------------------------------------------------------------- sessions and bars
def rth(m1, day=None):
    """Regular-hours 1m bars (09:30 <= open < 16:00) for one day (default: the newest day in m1). Index slice (fast)."""
    if m1 is None or not len(m1):
        return m1
    d = day or m1.index[-1].date()
    tz = m1.index.tz
    a = pd.Timestamp(f"{d} 09:30", tz=tz)
    b = pd.Timestamp(f"{d} 15:59", tz=tz)
    return m1.loc[a:b]


_sess_cache = {}


def sessions(m1):
    """Distinct trading dates present in m1, oldest first (cached per frame shape)."""
    if m1 is None or not len(m1):
        return []
    k = (len(m1), m1.index[0], m1.index[-1])
    if k not in _sess_cache:
        if len(_sess_cache) > 64:
            _sess_cache.clear()
        _sess_cache[k] = sorted(set(pd.unique(m1.index.normalize()).date)) if hasattr(pd.unique(m1.index.normalize()), "date") \
            else sorted({t.date() for t in pd.unique(m1.index.normalize())})
    return _sess_cache[k]


def aggregate(m1_rth, minutes, last_complete_open=None):
    """N-minute bars anchored to the session open (09:30, 09:32, ... for N=2). Returns (bars, complete_flags).

    A bar is complete only when its last 1m bar has finished: bar_open + N minutes <= last completed 1m open + 1 min.
    `last_complete_open` = open time of the newest FINALIZED 1m bar (defaults to the last row of m1_rth).
    """
    if m1_rth is None or not len(m1_rth):
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]), pd.Series(dtype=bool)
    day0 = m1_rth.index[0].normalize() + pd.Timedelta(hours=9, minutes=30)
    b = m1_rth.resample(f"{minutes}min", label="left", closed="left", origin=day0).agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna(subset=["Close"])
    last = last_complete_open if last_complete_open is not None else m1_rth.index[-1]
    done_until = last + pd.Timedelta(minutes=1)
    complete = pd.Series([i + pd.Timedelta(minutes=minutes) <= done_until for i in b.index], index=b.index)
    return b, complete


_agg_cache = {}


def aggregate_multi(m1, minutes, last_complete_open=None):
    """N-minute RTH bars across every session in m1 (for indicators that continue across sessions, e.g. MACD)."""
    out, flags = [], []
    newest = m1.index[-1].date()
    for d in sessions(m1):
        r = rth(m1, d)
        if r is None or not len(r):
            continue
        key = (d, minutes, len(r), r.index[-1], float(r["Close"].iloc[-1]))
        if d != newest and key in _agg_cache:
            b, c = _agg_cache[key]
        else:
            b, c = aggregate(r, minutes, last_complete_open if d == newest else None)
            if d != newest:
                if len(_agg_cache) > 256:
                    _agg_cache.clear()
                _agg_cache[key] = (b, c)
        out.append(b)
        flags.append(c)
    if not out:
        return aggregate(None, minutes)
    return pd.concat(out), pd.concat(flags)


# ---------------------------------------------------------------- session VWAP
def session_vwap(m1_rth):
    """Session VWAP from bars: cumulative(HLC3 x volume) / cumulative(volume), reset at 09:30 each session.

    This is a BAR-BASED APPROXIMATION (typical price per bar, not every trade). It is recomputed from the bar
    store, so a corrected bar replaces its earlier contribution instead of adding volume twice. Zero cumulative
    volume -> NaN (unavailable), never price 0.
    """
    if m1_rth is None or not len(m1_rth):
        return pd.Series(dtype=float)
    tp = (m1_rth["High"] + m1_rth["Low"] + m1_rth["Close"]) / 3.0
    day = m1_rth.index.normalize()
    pv = (tp * m1_rth["Volume"]).groupby(day).cumsum()
    vv = m1_rth["Volume"].groupby(day).cumsum()
    return (pv / vv.where(vv > 0)).astype(float)


def vwap_at(m1_rth, ts):
    """Session VWAP using only bars that opened at or before ts."""
    v = session_vwap(m1_rth[m1_rth.index <= ts])
    return float(v.iloc[-1]) if len(v) and v.iloc[-1] == v.iloc[-1] else None


# ---------------------------------------------------------------- MACD
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def macd(close, fast=12, slow=26, signal=9):
    """MACD line = EMA(fast) - EMA(slow); signal = EMA(signal) of the line; histogram H = line - signal.
    The first (slow + signal - 1) values are set to NaN (warm-up)."""
    m = ema(close, fast) - ema(close, slow)
    s = ema(m, signal)
    h = m - s
    warm = slow + signal - 1
    if len(close) <= warm:
        nan = pd.Series(np.nan, index=close.index)
        return nan, nan.copy(), nan.copy()
    m.iloc[:warm] = np.nan
    s.iloc[:warm] = np.nan
    h.iloc[:warm] = np.nan
    return m, s, h


def macd_cross(m, s, i=-1, tol=0.0):
    """One-bar crossover EVENT at index i: 'up' if m[i-1] <= s[i-1] and m[i] > s[i] (+tol), 'down' mirrored.
    Different from the persistent STATE (macd_state)."""
    if len(m) < 2 or any(v != v for v in (m.iloc[i], s.iloc[i], m.iloc[i - 1], s.iloc[i - 1])):
        return None
    if m.iloc[i - 1] <= s.iloc[i - 1] and m.iloc[i] > s.iloc[i] + tol:
        return "up"
    if m.iloc[i - 1] >= s.iloc[i - 1] and m.iloc[i] < s.iloc[i] - tol:
        return "down"
    return None


def macd_state(m, s, i=-1):
    """Current side of MACD vs signal: 'bull' (m > s), 'bear' (m < s), 'flat' (equal) or None (warm-up)."""
    if not len(m) or m.iloc[i] != m.iloc[i] or s.iloc[i] != s.iloc[i]:
        return None
    return "bull" if m.iloc[i] > s.iloc[i] else "bear" if m.iloc[i] < s.iloc[i] else "flat"


def hist_fading(h, side, n_changes=3, tol=1e-6, i=-1):
    """Three ADVERSE changes need FOUR histogram observations.
    Calls: H[t] < H[t-1] < H[t-2] < H[t-3] (each step lower by more than tol). Puts: mirrored (rising).
    Returns True / False, or None when there aren't enough finite observations."""
    k = n_changes + 1
    end = len(h) + i + 1 if i < 0 else i + 1
    w = h.iloc[max(0, end - k):end]
    if len(w) < k or w.isna().any():
        return None
    d = np.diff(w.values)
    return bool((d < -tol).all()) if side == "C" else bool((d > tol).all())


def hist_rising(h, side, n=2, tol=1e-6, i=-1):
    """Momentum building FOR the trade: n consecutive favorable histogram changes (n+1 observations)."""
    k = n + 1
    end = len(h) + i + 1 if i < 0 else i + 1
    w = h.iloc[max(0, end - k):end]
    if len(w) < k or w.isna().any():
        return None
    d = np.diff(w.values)
    return bool((d > tol).all()) if side == "C" else bool((d < -tol).all())


# ---------------------------------------------------------------- Wilder-smoothed: ATR, ADX, DI
def _wilder(x, n):
    """Wilder RMA seeded with the mean of the first n finite values (TA-Lib style). NaN before the seed."""
    x = pd.Series(x, dtype=float)
    out = pd.Series(np.nan, index=x.index)
    vals = x.values
    first = np.argmax(~np.isnan(vals)) if (~np.isnan(vals)).any() else None
    if first is None or len(vals) - first < n:
        return out
    seed_end = first + n
    prev = float(np.mean(vals[first:seed_end]))
    out.iloc[seed_end - 1] = prev
    for j in range(seed_end, len(vals)):
        v = vals[j]
        prev = prev if v != v else prev + (v - prev) / n
        out.iloc[j] = prev
    return out


def true_range(b):
    pc = b["Close"].shift()
    tr = pd.concat([b["High"] - b["Low"], (b["High"] - pc).abs(), (b["Low"] - pc).abs()], axis=1).max(axis=1)
    tr.iloc[0] = np.nan  # the first bar has no previous close (TA-Lib convention)
    return tr


def atr(b, n=14):
    """Average True Range (Wilder, n bars). Volatility only, no direction. NaN until n+1 bars."""
    if b is None or len(b) < n + 1:
        return pd.Series(np.nan, index=b.index if b is not None else None)
    return _wilder(true_range(b), n)


def adx_di(b, n=14):
    """ADX (trend STRENGTH, direction-free) with +DI / -DI (direction). Wilder smoothing.
    Returns (adx, plus_di, minus_di) Series; NaN during warm-up (needs about 2n bars for ADX)."""
    nan = pd.Series(np.nan, index=b.index if b is not None else None)
    if b is None or len(b) < 2 * n + 1:
        return nan, nan.copy(), nan.copy()
    up, dn = b["High"].diff(), -b["Low"].diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    mdm = dn.where((dn > up) & (dn > 0), 0.0)
    pdm.iloc[0] = mdm.iloc[0] = np.nan
    tr = _wilder(true_range(b), n)
    pdi = 100 * _wilder(pdm, n) / tr
    mdi = 100 * _wilder(mdm, n) / tr
    den = (pdi + mdi)
    dx = 100 * (pdi - mdi).abs() / den.where(den > 0)
    return _wilder(dx, n), pdi, mdi


def last(series, i=-1):
    if series is None or not len(series):
        return None
    v = series.iloc[i]
    return None if v != v else float(v)


# ---------------------------------------------------------------- relative volume at time
def rvol_at_time(m1, bar_open, minutes, lookback=10, min_sessions=5, stat="median"):
    """Volume of the COMPLETED N-minute bar that opened at bar_open, divided by the median (or mean) volume of
    the same clock interval on up to `lookback` prior sessions. Needs >= min_sessions valid prior intervals.
    Returns (rvol or None, n_sessions_used). Never compares an unfinished candle with complete history."""
    end = bar_open + pd.Timedelta(minutes=minutes)
    cur = m1[(m1.index >= bar_open) & (m1.index < end)]
    if len(cur) < minutes:  # the interval is not finished (or has missing minutes): unavailable
        return None, 0
    v_now = float(cur["Volume"].sum())
    hist = []
    for d in reversed([d for d in sessions(m1) if d < bar_open.date()]):
        s = bar_open.replace(year=d.year, month=d.month, day=d.day)
        w = m1[(m1.index >= s) & (m1.index < s + pd.Timedelta(minutes=minutes))]
        if len(w) == minutes:
            hist.append(float(w["Volume"].sum()))
        if len(hist) >= lookback:
            break
    if len(hist) < min_sessions:
        return None, len(hist)
    base = float(np.median(hist)) if stat == "median" else float(np.mean(hist))
    return (round(v_now / base, 2) if base > 0 else None), len(hist)


# ---------------------------------------------------------------- chop / structure features
def efficiency(close, lookback=20):
    """Directional efficiency = |close[t] - close[t-L]| / sum(|close[i] - close[i-1]|) over L bars.
    1.0 = straight line, near 0 = back-and-forth. None when there aren't L+1 bars or the path length is 0."""
    if close is None or len(close) < lookback + 1:
        return None
    w = close.iloc[-lookback - 1:]
    path = float(w.diff().abs().sum())
    if path <= 0:
        return None
    return round(abs(float(w.iloc[-1] - w.iloc[0])) / path, 3)


def vwap_crossings(close, vwap, lookback=60, tol=0.0):
    """Number of times the close switched sides of VWAP in the last `lookback` bars (closes within tol of VWAP
    don't count as a side)."""
    if close is None or vwap is None or not len(close):
        return None
    d = (close - vwap).iloc[-lookback:]
    side = np.sign(d.where(d.abs() > tol, 0.0)).replace(0, np.nan).ffill().dropna()
    return int((side.diff().abs() > 0).sum())


def overlap_ratio(b, lookback=10):
    """Share of consecutive bar pairs whose ranges overlap by more than half of the smaller range (chop)."""
    if b is None or len(b) < lookback + 1:
        return None
    w = b.iloc[-lookback - 1:]
    hi, lo = w["High"].values, w["Low"].values
    n = 0
    for j in range(1, len(w)):
        ov = min(hi[j], hi[j - 1]) - max(lo[j], lo[j - 1])
        small = min(hi[j] - lo[j], hi[j - 1] - lo[j - 1])
        if small > 0 and ov > 0.5 * small:
            n += 1
    return round(n / (len(w) - 1), 2)


def range_atr_ratio(b, atr_series, i=-1):
    a = last(atr_series, i - 1 if i < 0 else i)  # compare with ATR known BEFORE this bar
    if a is None or a <= 0:
        return None
    return round(float(b["High"].iloc[i] - b["Low"].iloc[i]) / a, 2)


# ---------------------------------------------------------------- developing volume profile (APPROXIMATE)
def volume_profile(m1_rth_until, bin_size=0.05, value_area=0.70):
    """Developing session profile from 1m OHLCV bars only up to the decision time.

    APPROXIMATION: each bar's volume is spread evenly over the price bins its High-Low range covers (bars carry
    no trade-by-trade prices). Bin size is a setting (default $0.05). POC = bin with the most volume; ties go to
    the bin nearest the last close. Value area starts at the POC and repeatedly adds the next bin above or below
    with more volume (both on a tie) until >= value_area of total volume (70% is the conventional starting
    setting, not an optimized value). Returns None when there is no volume.
    """
    if m1_rth_until is None or not len(m1_rth_until) or float(m1_rth_until["Volume"].sum()) <= 0:
        return None
    lo_all, hi_all = float(m1_rth_until["Low"].min()), float(m1_rth_until["High"].max())
    base = math.floor(lo_all / bin_size) * bin_size
    nb = max(1, int(round((hi_all - base) / bin_size)) + 1)
    vol = np.zeros(nb)
    for h, l, v in zip(m1_rth_until["High"].values, m1_rth_until["Low"].values, m1_rth_until["Volume"].values):
        a = int(math.floor((l - base) / bin_size + 1e-9))
        z = int(math.floor((h - base) / bin_size + 1e-9))
        a, z = max(0, min(a, nb - 1)), max(0, min(z, nb - 1))
        vol[a:z + 1] += v / (z - a + 1)
    total = vol.sum()
    last_close = float(m1_rth_until["Close"].iloc[-1])
    mx = vol.max()
    cands = np.where(np.isclose(vol, mx))[0]
    poc = int(min(cands, key=lambda k: abs(base + (k + 0.5) * bin_size - last_close)))
    lo_i = hi_i = poc
    acc = vol[poc]
    while acc < value_area * total and (lo_i > 0 or hi_i < nb - 1):
        up = vol[hi_i + 1] if hi_i < nb - 1 else -1
        dn = vol[lo_i - 1] if lo_i > 0 else -1
        if up >= dn and up >= 0:
            hi_i += 1
            acc += up
        if dn >= up and dn >= 0:
            lo_i -= 1
            acc += dn
    mid = lambda k: round(base + (k + 0.5) * bin_size, 2)
    return {"poc": mid(poc), "vah": round(base + (hi_i + 1) * bin_size, 2), "val": round(base + lo_i * bin_size, 2),
            "bin": bin_size, "value_area": value_area, "total_volume": float(total),
            "approximate": True, "method": "bar range spread (1m OHLCV), not trade-by-trade",
            "as_of": m1_rth_until.index[-1].isoformat()}
