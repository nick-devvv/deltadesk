"""sprint/daytype.py - day-type features, all point-in-time (docs/research/SPRINT_PLAN.md, "Day type").

Every feature at index i uses only bars finished by the end of regular-hours bar i (and earlier sessions):
  adx, pdi, mdi     ADX / +DI / -DI (14, Wilder) on 5-minute regular-hours bars continuing across sessions, from the
                    last 5-minute bar complete at the end of bar i
  er30              efficiency ratio of the last 30 one-minute closes: |c[i] - c[i-30]| / sum |c[j] - c[j-1]|
  vwap_x60          times the 1-minute close switched sides of VWAP in the last 60 bars
  overlap30         share of consecutive 1-minute bar pairs (last 30 bars) overlapping by > half the smaller range
  range_atr         today's regular-hours range so far / daily ATR(14) of prior sessions
  or_accept_up/down opening-range (30 min) acceptance: 3 consecutive 1-minute closes beyond the edge after the range
                    is complete, and the furthest close beyond the edge >= 0.5 x ATR(14, 5-minute)
  rvol              regular-hours volume so far / mean volume of the same minutes over up to 14 prior sessions (>= 10)
  noise_trend       noise_trend's score with the conditions computable from bars: (b) 09:30-10:00 volume >= 1.5x
                    its 14-session average, (c) |09:30-10:00 return| above its 14-session average, (d) FOMC day from
                    the dated list below (CPI/jobs unknown, so (d) is True on an FOMC day and unknown otherwise);
                    (a) VIX is unknown in the backtest (no VIX history in the Alpaca pull). Trade = >= 2 known true.
  news              unknown in the backtest (None): no point-in-time news archive for 2024-2026.
Pre-registered day-type rule (2026-10-31, before any run):
  trend  = at least 3 of 5 true: adx >= 25; er30 >= 0.35; vwap_x60 <= 2; overlap30 < 0.60; OR accepted either way
  chop   = at most 1 of the 5 true
  neutral otherwise
  trend_aligned(side) = trend and the close is on the trade's side of VWAP (calls above, puts below)
A feature without enough data is None and counts as not true.
"""
import math

import numpy as np

ADX_MIN, ER_MIN, VWAP_X_MAX, OVERLAP_MAX = 25.0, 0.35, 2, 0.60
# FOMC statement days. 2026 from config/v4.json; 2024-2025 from the Federal Reserve's published calendars (verify).
FOMC = {"2024-09-18", "2024-11-07", "2024-12-18", "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
        "2025-09-17", "2025-10-29", "2025-12-10"}


def _fomc_days():
    try:
        import json
        from pathlib import Path
        j = json.loads((Path(__file__).resolve().parents[1] / "config" / "v4.json").read_text())
        return FOMC | set(j.get("fomc_decision_days") or [])
    except (OSError, ValueError):
        return set(FOMC)


def efficiency(c, i, n=30):
    if i < n:
        return None
    w = c[i - n:i + 1]
    if np.isnan(w).any():
        w = w[~np.isnan(w)]
        if len(w) < n // 2:
            return None
    path = float(np.abs(np.diff(w)).sum())
    return None if path <= 0 else round(abs(float(w[-1] - w[0])) / path, 3)


def vwap_crosses(c, vw, i, n=60):
    if i < 1:
        return None
    d = (c[max(0, i - n + 1):i + 1] - vw[max(0, i - n + 1):i + 1])
    s = np.sign(d)
    s = s[~np.isnan(s) & (s != 0)]
    return int((np.abs(np.diff(s)) > 0).sum()) if len(s) else 0


def overlap(h, l, i, n=30):
    if i < n:
        return None
    hi, lo = h[i - n:i + 1], l[i - n:i + 1]
    k = 0
    for j in range(1, len(hi)):
        if math.isnan(hi[j]) or math.isnan(hi[j - 1]):
            continue
        ov = min(hi[j], hi[j - 1]) - max(lo[j], lo[j - 1])
        small = min(hi[j] - lo[j], hi[j - 1] - lo[j - 1])
        if small > 0 and ov > 0.5 * small:
            k += 1
    return round(k / (len(hi) - 1), 2)


class DayType:
    def __init__(self, ctx, or_minutes=30):
        self.ctx = ctx
        self.orm = or_minutes
        self._cache = {}
        s, d = ctx.series, ctx.day
        self.datr = s.daily_atr(d)
        prior = s.prior_days(d, 14)
        self.prior = prior
        self.cumv_prior = [np.nancumsum(s.rth[p][:, 4]) for p in prior if np.sum(~np.isnan(s.rth[p][:, 3])) >= 300]
        hh = []
        for p in prior:
            g = s.rth[p]
            w = g[:30]
            if np.isnan(w[:, 3]).any():
                continue
            hh.append((float(np.nansum(w[:, 4])), abs(float(w[-1, 3]) / float(w[0, 0]) - 1)))
        self.first_hh = hh
        self.fomc = d.isoformat() in _fomc_days()

    def features(self, i):
        hit = self._cache.get(i)
        if hit is not None:
            return hit
        c = self.ctx
        f = {"adx": _f(c.adx[i]), "pdi": _f(c.pdi[i]), "mdi": _f(c.mdi[i]), "er30": efficiency(c.c, i),
             "vwap_x60": vwap_crosses(c.c, c.vwap, i), "overlap30": overlap(c.h, c.l, i)}
        hi, lo = np.nanmax(c.h[:i + 1]) if i >= 0 else np.nan, np.nanmin(c.l[:i + 1]) if i >= 0 else np.nan
        f["range_atr"] = round(float(hi - lo) / self.datr, 2) if self.datr and not math.isnan(hi) else None
        f["or_accept_up"], f["or_accept_down"] = self._accept(i)
        f["rvol"] = self._rvol(i)
        f["noise_trend"] = self._noise_trend(i)
        f["news"] = None
        votes = [f["adx"] is not None and f["adx"] >= ADX_MIN, f["er30"] is not None and f["er30"] >= ER_MIN,
                 f["vwap_x60"] is not None and i >= 59 and f["vwap_x60"] <= VWAP_X_MAX,
                 f["overlap30"] is not None and f["overlap30"] < OVERLAP_MAX, bool(f["or_accept_up"] or f["or_accept_down"])]
        f["trend_votes"] = int(sum(votes))
        f["day_type"] = "trend" if f["trend_votes"] >= 3 else "chop" if f["trend_votes"] <= 1 else "neutral"
        self._cache[i] = f
        return f

    def _accept(self, i):
        c, m = self.ctx, self.orm
        if i < m or np.isnan(c.h[:m]).all():
            return False, False
        orh, orl = float(np.nanmax(c.h[:m])), float(np.nanmin(c.l[:m]))
        a5 = _f(c.atr5[i])
        if a5 is None:
            return False, False
        cl = c.c[m:i + 1]
        out = []
        for up in (True, False):
            beyond = (cl > orh) if up else (cl < orl)
            run, ok3 = 0, False
            for b in beyond:
                run = run + 1 if b else 0
                ok3 |= run >= 3
            far = (np.nanmax(cl) - orh) if up else (orl - np.nanmin(cl))
            out.append(bool(ok3 and far >= 0.5 * a5))
        return tuple(out)

    def _rvol(self, i):
        if len(self.cumv_prior) < 10 or i < 0:
            return None
        base = float(np.mean([cv[i] for cv in self.cumv_prior]))
        now = float(np.nansum(self.ctx.v[:i + 1]))
        return round(now / base, 2) if base > 0 else None

    def _noise_trend(self, i):
        out = {"a_vix": None, "b_volume_1_5x": None, "c_abs_return_above_avg": None, "d_macro_day": True if self.fomc else None}
        c = self.ctx
        if i >= 29 and not np.isnan(c.c[:30]).any() and len(self.first_hh) >= 14:
            v = float(np.nansum(c.v[:30]))
            r = abs(float(c.c[29]) / float(c.o[0]) - 1)
            out["b_volume_1_5x"] = v >= 1.5 * float(np.mean([x[0] for x in self.first_hh]))
            out["c_abs_return_above_avg"] = r > float(np.mean([x[1] for x in self.first_hh]))
        known = [x for x in out.values() if x is not None]
        out["known"], out["true"] = len(known), int(sum(known))
        out["trade"] = out["true"] >= 2
        return out

    def trend_aligned(self, i, side):
        f = self.features(i)
        c = self.ctx
        if f["day_type"] != "trend" or math.isnan(c.c[i]) or math.isnan(c.vwap[i]):
            return False
        return bool(c.c[i] > c.vwap[i]) if side == "C" else bool(c.c[i] < c.vwap[i])


def _f(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)
