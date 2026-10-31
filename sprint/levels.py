"""sprint/levels.py - the level map known at each minute (docs/research/SPRINT_PLAN.md, "Levels (known at entry)").

Exactly these levels, each computed only from bars FINISHED by the decision time (no look-ahead):
  PDH, PDL, PDC      prior regular session's high, low, close
  PMH, PML           premarket/overnight high and low from today's 04:00-09:29 ET bars (known from 09:30)
  OR5H/L ... OR60H/L opening-range high/low for 5, 15, 30, 60 minutes, once the range is complete
  VWAP, VWAP+1/-1, VWAP+2/-2   session VWAP (bar HLC3 x volume) and its 1 and 2 volume-weighted standard deviations
  POC, VAH, VAL      developing volume profile of today's regular-hours bars: $0.10 bins, each bar's volume spread
                     evenly over the bins its high-low covers (APPROXIMATE, bars carry no trade prices), POC = fullest
                     bin (ties: nearest the last close), value area grown from the POC to 70% of volume (the same
                     method as indicators.volume_profile)
  R1, R5             $1 and $5 round numbers within +/-2% of the last close (a $5 multiple is listed once, as R5)
  PWH, PWL           previous Monday-Friday week's regular-session high and low
  SWH, SWL           today's regular-hours 1-minute swing highs/lows: bar k's high (low) beats the 3 bars on each
                     side (strictly), confirmed when bar k+3 has finished
API (times are decision times: `levels_at(ts)` uses bars that finished by ts, i.e. opened before ts):
  LevelMap.at(i)                 levels known at the END of regular-hours bar i (i = -1: before the first bar ends)
  LevelMap.levels_at(ts)         sorted [(price, kind)]
  LevelMap.next_level_above(price, ts) / next_level_below(price, ts) -> (price, kind) or None (strictly beyond)
  LevelMap.fake(seed)            the "made-up levels" twin: each real level moved to a random point between its two
                                 neighbors in the sorted real list (at the ends, the one neighbor's gap is mirrored),
                                 with a fixed random fraction per (seed, symbol, day, level identity), so a made-up
                                 level keeps its place relative to its neighbors as the day develops.
"""
import math
import zlib
from datetime import datetime

import numpy as np

BIN = 0.10
VALUE_AREA = 0.70
ROUND_BAND = 0.02
OR_MINUTES = (5, 15, 30, 60)
SWING_N = 3
N = 390


def _idx_of(ts):
    """Decision time -> index of the last finished bar (bars that opened before ts)."""
    t = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
    return (t.hour * 60 + t.minute) - 570 - 1


class LevelMap:
    def __init__(self, sym, day, o, h, l, c, v, vwap, vsd, prev_day=None, pre=None, prev_week=None):
        self.sym, self.day = sym, day
        self.o, self.h, self.l, self.c, self.v = o, h, l, c, v
        self.vwap, self.vsd = vwap, vsd
        self.static = []
        if prev_day:
            self.static += [(prev_day["high"], "PDH"), (prev_day["low"], "PDL"), (prev_day["close"], "PDC")]
        if prev_week:
            self.static += [(prev_week["high"], "PWH"), (prev_week["low"], "PWL")]
        self.pre = pre
        self._cache = {}
        self._prof = None
        self._swings = self._find_swings()
        self.ref0 = prev_day["close"] if prev_day else (pre[0] if pre else None)

    @classmethod
    def from_context(cls, ctx):
        s = ctx.series
        return cls(ctx.sym, ctx.day, ctx.o, ctx.h, ctx.l, ctx.c, ctx.v, ctx.vwap, ctx.vsd,
                   s.prev_day(ctx.day), s.pre.get(ctx.day), s.prev_week(ctx.day))

    # ------------------------------------------------------------ pieces
    def _find_swings(self):
        """[(confirm_index, price, kind, k)] for every swing bar k (confirmed at the end of bar k+3)."""
        out = []
        h, l = self.h, self.l
        for k in range(SWING_N, N - SWING_N):
            wh = np.r_[h[k - SWING_N:k], h[k + 1:k + 1 + SWING_N]]
            wl = np.r_[l[k - SWING_N:k], l[k + 1:k + 1 + SWING_N]]
            if math.isnan(h[k]) or np.isnan(wh).any():
                continue
            if h[k] > wh.max():
                out.append((k + SWING_N, float(h[k]), "SWH", k))
            if l[k] < wl.min():
                out.append((k + SWING_N, float(l[k]), "SWL", k))
        return out

    def _profile_tables(self):
        lo_g = np.floor(np.where(np.isnan(self.l), np.inf, self.l) / BIN + 1e-6)
        hi_g = np.floor(np.where(np.isnan(self.h), -np.inf, self.h) / BIN + 1e-6)
        ok = ~np.isnan(self.c) & ~np.isnan(self.v)
        if not ok.any():
            return None
        gmin, gmax = int(lo_g[ok].min()), int(hi_g[ok].max())
        nb = gmax - gmin + 2
        add = np.zeros((N, nb))
        for j in np.where(ok)[0]:
            a, z = int(lo_g[j]) - gmin, int(hi_g[j]) - gmin
            add[j, a:z + 1] += self.v[j] / (z - a + 1)
        return gmin, np.cumsum(add, axis=0), lo_g, hi_g, ok

    def profile_at(self, i):
        """(POC, VAH, VAL) of bars 0..i, or None."""
        if i < 0:
            return None
        if self._prof is None:
            self._prof = self._profile_tables() or False
        if not self._prof:
            return None
        gmin, cum, lo_g, hi_g, ok = self._prof
        sel = ok[:i + 1]
        if not sel.any():
            return None
        vol_row = cum[i]
        if vol_row.sum() <= 0:
            return None
        b0 = int(lo_g[:i + 1][sel].min()) - gmin
        b1 = int(hi_g[:i + 1][sel].max()) - gmin
        vol = vol_row[b0:b1 + 1]
        last_close = float(self.c[:i + 1][sel][-1])
        base = (b0 + gmin) * BIN
        mx = vol.max()
        cands = np.where(np.isclose(vol, mx))[0]
        poc = int(min(cands, key=lambda k: abs(base + (k + 0.5) * BIN - last_close)))
        total, lo_i, hi_i, acc, nb = vol.sum(), poc, poc, vol[poc], len(vol)
        while acc < VALUE_AREA * total and (lo_i > 0 or hi_i < nb - 1):
            up = vol[hi_i + 1] if hi_i < nb - 1 else -1
            dn = vol[lo_i - 1] if lo_i > 0 else -1
            if up >= dn and up >= 0:
                hi_i += 1
                acc += up
            if dn >= up and dn >= 0:
                lo_i -= 1
                acc += dn
        return round(base + (poc + 0.5) * BIN, 2), round(base + (hi_i + 1) * BIN, 2), round(base + lo_i * BIN, 2)

    def _ref(self, i):
        for j in range(min(i, N - 1), -1, -1):
            if not math.isnan(self.c[j]):
                return float(self.c[j])
        return self.ref0

    # ------------------------------------------------------------ API
    def at(self, i):
        """Sorted [(price, kind)] known at the end of bar i (i = -1: before the first regular-hours bar ends)."""
        i = int(max(-1, min(i, N - 1)))
        hit = self._cache.get(i)
        if hit is not None:
            return hit
        out = list(self.static)
        if self.pre and i >= -1:
            out += [(self.pre[0], "PMH"), (self.pre[1], "PML")]
        for m in OR_MINUTES:
            if i >= m - 1:
                w = slice(0, m)
                if not np.isnan(self.h[w]).all():
                    out += [(float(np.nanmax(self.h[w])), f"OR{m}H"), (float(np.nanmin(self.l[w])), f"OR{m}L")]
        if i >= 0 and not math.isnan(self.vwap[i]):
            vw, sd = float(self.vwap[i]), float(self.vsd[i])
            out.append((vw, "VWAP"))
            if sd > 0:
                out += [(vw + sd, "VWAP+1"), (vw - sd, "VWAP-1"), (vw + 2 * sd, "VWAP+2"), (vw - 2 * sd, "VWAP-2")]
        p = self.profile_at(i)
        if p:
            out += [(p[0], "POC"), (p[1], "VAH"), (p[2], "VAL")]
        ref = self._ref(i)
        if ref:
            for k in range(int(math.floor(ref * (1 - ROUND_BAND))), int(math.ceil(ref * (1 + ROUND_BAND))) + 1):
                out.append((float(k), "R5" if k % 5 == 0 else "R1"))
        out += [(px, kind) for (ci, px, kind, _k) in self._swings if ci <= i]
        out = sorted((round(float(px), 4), kind) for px, kind in out)
        self._cache[i] = out
        return out

    def identities(self, i):
        """Same order as at(i): a stable identity per level (kind, plus price for rounds, bar for swings)."""
        sw = {(round(px, 4), kind): f"{kind}@{k}" for (ci, px, kind, k) in self._swings if ci <= i}
        return [(f"{k}:{px:g}" if k in ("R1", "R5") else sw.get((px, k), k)) for px, k in self.at(i)]

    def levels_at(self, ts):
        return self.at(_idx_of(ts))

    def next_above_i(self, price, i):
        for px, k in self.at(i):
            if px > price + 1e-9:
                return px, k
        return None

    def next_below_i(self, price, i):
        for px, k in reversed(self.at(i)):
            if px < price - 1e-9:
                return px, k
        return None

    def next_level_above(self, price, ts):
        return self.next_above_i(price, _idx_of(ts))

    def next_level_below(self, price, ts):
        return self.next_below_i(price, _idx_of(ts))

    def nearest_i(self, price, i):
        lv = self.at(i)
        if not lv:
            return None
        return min(lv, key=lambda x: abs(x[0] - price))

    def fake(self, seed):
        return FakeLevelMap(self, seed)


class FakeLevelMap(LevelMap):
    """Made-up levels: same count and same neighborhood as the real map, random positions (seeded)."""

    def __init__(self, real, seed):
        self.real, self.seed = real, seed
        self.sym, self.day = real.sym, real.day
        self._cache = {}

    def _u(self, ident):
        return zlib.crc32(f"{self.seed}|{self.sym}|{self.day}|{ident}".encode()) / 2 ** 32

    def at(self, i):
        i = int(max(-1, min(i, N - 1)))
        hit = self._cache.get(i)
        if hit is not None:
            return hit
        lv = self.real.at(i)
        ids = self.real.identities(i)
        n = len(lv)
        out = []
        for q, ((px, kind), ident) in enumerate(zip(lv, ids)):
            if n == 1:
                out.append((px, kind))
                continue
            lo = lv[q - 1][0] if q > 0 else px - (lv[q + 1][0] - px)
            hi = lv[q + 1][0] if q < n - 1 else px + (px - lv[q - 1][0])
            out.append((round(lo + self._u(ident) * (hi - lo), 4), kind))
        out.sort()
        self._cache[i] = out
        return out

    def identities(self, i):
        return [k for _, k in self.at(i)]

    def profile_at(self, i):
        return self.real.profile_at(i)
