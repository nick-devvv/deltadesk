"""Test doubles: a deterministic market (1m bars for prior sessions + today) and a fake Schwab provider whose option
quotes follow a simple delta-gamma model with fresh provider timestamps. No network, no AI."""
from datetime import timedelta

import numpy as np
import pandas as pd

import core
import marketdata


def u_volume(t, base=20000.0):
    """Typical intraday U-shape: heavy open and close, light midday. Premarket/after hours light."""
    m = t.hour * 60 + t.minute
    if m < 570 or m >= 960:
        return base * 0.1
    x = (m - 570) / 390.0
    return base * (0.7 + 2.2 * (x - 0.5) ** 2 * 4 / 2.2 * 0.6 + (1.0 if m < 585 else 0.0))


def prior_path(day_i, m, rng):
    """Prior sessions oscillate around 600 (PDH near 602, PDL near 598)."""
    import math
    return 600.0 + 2.0 * math.sin((m - 570) / 390.0 * math.pi * 2 + day_i) + rng.normal(0, 0.02)


def make_market(path_fn, day, prior_days=12, vol=20000, vol_fn=None, seed=7):
    rng = np.random.default_rng(seed)
    idx, px, vv = [], [], []
    d = day
    days = []
    while len(days) < prior_days:
        d = d - timedelta(days=1)
        if d.weekday() < 5:
            days.append(d)
    for i, dd in enumerate(reversed(days)):
        for m in pd.date_range(dd.replace(hour=4, minute=0), dd.replace(hour=19, minute=59), freq="1min"):
            idx.append(m)
            px.append(prior_path(i, m.hour * 60 + m.minute, rng))
            vv.append(u_volume(m, vol))
    for m in pd.date_range(day.replace(hour=4, minute=0), day.replace(hour=19, minute=59), freq="1min"):
        idx.append(m)
        px.append(path_fn(m))
        vv.append(vol_fn(m) if vol_fn else u_volume(m, vol))
    idx = pd.DatetimeIndex(idx)
    c = np.array(px, dtype=float)
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + 0.03
    l = np.minimum(o, c) - 0.03
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": np.array(vv, dtype=float)}, index=idx)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class FakeSchwab(marketdata.Provider):
    """Executable fake. Option mid = intrinsic-ish model around strike K: base + delta*(S - S0) + 0.5*gamma*(S-S0)^2.
    Set .broken = True to simulate an outage (quotes missing), .stale = True for old timestamps."""
    name = "Schwab (fake for tests)"
    executable = True

    def __init__(self, m1, clock, s0=601.0, delta=0.45, gamma=0.05, base=2.00, spread=0.04):
        self.m1, self.clock, self.s0, self.delta, self.gamma, self.base, self.spread = m1, clock, s0, delta, gamma, base, spread
        self.broken = False
        self.stale = False
        self.calls = 0

    def spot(self):
        t = pd.Timestamp(self.clock())
        cut = self.m1[self.m1.index <= t - pd.Timedelta(minutes=1)]
        return float(cut["Close"].iloc[-1]) if len(cut) else self.s0

    def bars_1m(self, ticker):
        t = pd.Timestamp(self.clock())
        return self.m1[self.m1.index <= t - pd.Timedelta(minutes=1)]   # only FINISHED minutes are delivered

    def quote(self, ticker):
        s = self.spot()
        qt = pd.Timestamp(self.clock()) - pd.Timedelta(seconds=120 if self.stale else 1)
        return {"bid": round(s - 0.01, 2), "ask": round(s + 0.01, 2), "last": round(s, 2), "quote_time": qt, "trade_time": qt,
                "src": self.name}

    def _px(self, side, strike):
        s = self.spot()
        ds = (s - self.s0) if side == "C" else (self.s0 - s)
        mid = self.base + self.delta * ds + 0.5 * self.gamma * ds * ds - 0.03 * abs(strike - round(self.s0))
        mid = max(0.05, mid)
        return round(mid - self.spread / 2, 2), round(mid + self.spread / 2, 2)

    def option_quote(self, symbol):
        self.calls += 1
        if self.broken:
            return None, "outage (test)"
        side = symbol[-9]
        strike = int(symbol[-8:]) / 1000
        b, a = self._px(side, strike)
        qt = pd.Timestamp(self.clock()) - pd.Timedelta(seconds=120 if self.stale else 1)
        d = self.delta if side == "C" else -self.delta
        return {"bid": b, "ask": a, "last": round((a + b) / 2, 2), "delta": d, "gamma": self.gamma, "theta": -0.30,
                "iv": 0.18, "quote_time": qt, "bid_size": 50, "ask_size": 50, "multiplier": 100, "src": self.name}, None

    def chain(self, ticker, side, first, through=None):
        exp = first
        rows = []
        k0 = round(self.s0)
        for k in range(k0 - 3, k0 + 4):
            sym = f"{ticker}{exp[2:4]}{exp[5:7]}{exp[8:10]}{side[0].upper()}{int(k * 1000):08d}"
            b, a = self._px(side[0].upper(), k)
            d = self.delta if side[0].upper() == "C" else -self.delta
            rows.append({"symbol": sym, "strike": float(k), "bid": b, "ask": a, "ts": None, "delta": d if k == k0 else d * 0.7,
                         "gamma": self.gamma, "theta": -0.30, "iv": 0.18, "exp": exp, "feed": self.name})
        return rows, None


def install(monkeypatch, path_fn, day, **kw):
    clock = Clock(day.replace(hour=9, minute=30))
    monkeypatch.setattr(core, "now_et", clock)
    m1 = make_market(path_fn, day, **{k: v for k, v in kw.items() if k in ("prior_days", "vol", "vol_fn", "seed")})
    fk = FakeSchwab(m1, clock, **{k: v for k, v in kw.items() if k in ("s0", "delta", "gamma", "base", "spread")})
    marketdata.use(fk)
    return clock, fk
