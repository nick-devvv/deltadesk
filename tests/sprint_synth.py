"""Synthetic market data for the sprint tests: stock minute bars (04:00-20:00 ET) and Black-Scholes-priced 0DTE option
bars written in the exact cache layout tools/sprint_pull.py produces. No network, deterministic per seed."""
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from sprint import bs  # noqa: E402
from sprint.data import Series, DayContext  # noqa: E402
from sprint.fills import OptionTape  # noqa: E402

ET = "America/New_York"


def weekdays(a, n):
    out, d = [], a
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def stock_day(day, px0, seed, drift=0.0, vol=0.0005, trend_at=None):
    """Bars 04:00-19:59 for one day. drift is per-minute (fraction); trend_at=(start_idx, per-minute drift)."""
    rng = np.random.default_rng(seed)
    rows = []
    px = px0
    for m in range(240, 1200):
        r = rng.normal(0, vol * (0.3 if m < 570 or m >= 960 else 1.0)) + (drift if 570 <= m < 960 else 0.0)
        if trend_at and 570 + trend_at[0] <= m < 960:
            r += trend_at[1]
        o = px
        c = px * (1 + r)
        h = max(o, c) * (1 + abs(rng.normal(0, vol / 3)))
        l = min(o, c) * (1 - abs(rng.normal(0, vol / 3)))
        v = float(rng.integers(5_000, 20_000) * (1 if 570 <= m < 960 else 0.1))
        rows.append((pd.Timestamp(f"{day} {m // 60:02d}:{m % 60:02d}", tz=ET), round(o, 2), round(h, 2), round(l, 2), round(c, 2), v))
        px = c
    df = pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"])
    df["n"], df["vw"] = 100, df["c"]
    return df


def option_bars(day, stock, under, iv=0.18, band=0.03, skip=None, seed=0):
    """BS-priced 1-minute bars for $1 strikes within band of the open; skip = set of (symbol, minute_idx) with no print."""
    rng = np.random.default_rng(seed)
    mins = stock["ts"].dt.hour * 60 + stock["ts"].dt.minute
    r = stock[(mins >= 570) & (mins < 960)]
    S_o, S_c = r["o"].to_numpy(float), r["c"].to_numpy(float)
    o0 = float(S_o[0])
    i = np.arange(390)
    Ta = np.maximum(390 - i, bs.MIN_T_MIN) / bs.YEAR_MIN
    Tb = np.maximum(390 - i - 1, bs.MIN_T_MIN) / bs.YEAR_MIN
    t0 = pd.Timestamp(f"{day} 09:30", tz=ET)
    stamps = np.array([t0 + pd.Timedelta(minutes=int(k)) for k in i])
    frames = []
    for k in range(int(o0 * (1 - band)), int(o0 * (1 + band)) + 2):
        for right in ("C", "P"):
            sym = f"{under}{day:%y%m%d}{right}{k * 1000:08d}"
            call = right == "C"
            po = bs.price_v(S_o, float(k), Ta, iv, call)
            pc = bs.price_v(S_c, float(k), Tb, iv, call)
            keep = np.maximum(po, pc) >= 0.01
            if skip:
                keep &= np.array([(sym, int(m)) not in skip for m in i])
            h, l = np.maximum(po, pc) * 1.01, np.minimum(po, pc) * 0.99
            frames.append(pd.DataFrame({"ts": stamps[keep], "o": po[keep].round(2), "h": h[keep].round(2), "l": l[keep].round(2),
                                        "c": pc[keep].round(2), "v": rng.integers(1, 500, keep.sum()).astype(float), "n": 10,
                                        "vw": pc[keep].round(2), "symbol": sym}))
    return pd.concat(frames, ignore_index=True)


def write_cache(root, under, days, px0=500.0, seed=1, iv=0.18, drifts=None, trend=None, band=0.03):
    """Write stock months + option days for `days`. Returns {day: stock_df}."""
    import pull_alpaca as PA
    root = Path(root)
    frames, px, out = [], px0, {}
    for n, d in enumerate(days):
        df = stock_day(d, px, seed + n, drift=(drifts or {}).get(d, 0.0), trend_at=(trend or {}).get(d))
        out[d] = df
        frames.append(df)
        px = float(df["c"].iloc[-1])
        ob = option_bars(d, df, under, iv=iv, seed=seed + n, band=band)
        PA._write_gz(root / "options" / under / d.isoformat() / "bars.csv.gz", ob)
    allb = pd.concat(frames, ignore_index=True)
    for m, g in allb.groupby(allb["ts"].dt.strftime("%Y-%m")):
        PA._write_gz(root / "stocks" / under / f"{m}.csv.gz", g.reset_index(drop=True))
    return out


class ConstSpread:
    """A fixed half-spread (for hand-checked P/L)."""
    label = "CONST"

    def __init__(self, hs=0.01):
        self.hs = hs

    def half_spread(self, under, px, minute=None):
        return self.hs, "CONST"

    def spread_ok(self, *a, **k):
        return True

    def describe(self):
        return f"constant half-spread ${self.hs}"


# ---------------------------------------------------------------- hand-built contexts for exit tests
def flat_day_df(day, px=500.0, pre_hi=None, pre_lo=None, rng=0.01):
    rows = []
    for m in range(240, 960):
        p = px
        hi, lo = p + rng, p - rng
        if m < 570 and pre_hi is not None:
            hi, lo = pre_hi, pre_lo
        rows.append((pd.Timestamp(f"{day} {m // 60:02d}:{m % 60:02d}", tz=ET), p, hi, lo, p, 1000.0))
    return pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"])


def make_ctx(day, stock_path, opt_path, prior_days=2, px=500.0, spread=None, strike=500.0, right="C", vol=None,
             stock_hl=None, opt_hl=None, no_print=(), early=False, stock_bars=None, prior_range=0.01):
    """A DayContext whose regular-hours stock closes follow stock_path (dict idx -> close, carried forward) and a single
    option tape whose prices follow opt_path (dict idx -> price, carried forward). stock_hl / opt_hl: {idx: (high, low)}
    overrides; stock_bars: {idx: (open, high, low, close)} full overrides (the close carries forward); no_print: option
    minutes without a bar; prior_range: +/- range of the flat prior days' bars."""
    days = weekdays(day - timedelta(days=7 * (prior_days // 5 + 2)), 10 * (prior_days // 5 + 2))
    prior = [d for d in days if d < day][-prior_days:]
    frames = [flat_day_df(d, px, rng=prior_range) for d in prior]
    rows = []
    cur = px
    for m in range(240, 960):
        i = m - 570
        if 0 <= i and i in stock_path:
            cur = stock_path[i]
        o = c = cur
        hi, lo = c + 0.01, c - 0.01
        if stock_hl and i in stock_hl:
            hi, lo = stock_hl[i]
        if stock_bars and i in stock_bars:
            o, hi, lo, c = stock_bars[i]
            cur = c
        v = (vol or {}).get(i, 1000.0)
        rows.append((pd.Timestamp(f"{day} {m // 60:02d}:{m % 60:02d}", tz=ET), o, hi, lo, c, v))
    frames.append(pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"]))
    df = pd.concat(frames, ignore_index=True)
    s = Series("SPY", df)
    o, h, l, c, v = (np.full(390, np.nan) for _ in range(5))
    cur = None
    for i in range(390):
        if i in opt_path:
            cur = opt_path[i]
        if cur is None or i in no_print:
            continue
        o[i] = c[i] = cur
        h[i], l[i] = cur + 0.005, cur - 0.005
        if opt_hl and i in opt_hl:
            h[i], l[i] = opt_hl[i]
        v[i] = 10
    sym = f"SPY{day:%y%m%d}{right}{int(strike * 1000):08d}"
    tape = OptionTape(sym, right, strike, o, h, l, c, v)
    ctx = DayContext(s, day, {sym: tape}, spread or ConstSpread(0.01), early_close=early)
    return ctx, tape
