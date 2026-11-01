"""sprint/ind5.py - 5-minute regular-hours bars, the textbook indicators and the D1-D6 decision rules of SPRINT_PLAN
Addenda 10.2 and 10.3 (round 8, pre-registered 2026-11-01 before any round-8 code or run). Research only: no network, no
orders. Shares (sprint/shares.py) and option twins (sprint/optpass.py) both take their decisions from here.

Bars. Each session's regular-hours 1-minute bars are cut into 5-minute bars aligned to 09:30: bar b covers minutes
5b..5b+4 and finishes at 09:35 + 5b (the first bar finishes 09:35). A 5-minute bar is built from the 1-minute bars that
exist in its five minutes (open = the first one's open, high / low = the extremes, close = the last one's close, volume =
the sum); a bar with no 1-minute bar at all is absent. (Literal reading: "built from the 1-minute bars"; sprint/data.Series
.b5 needs all five minutes, which would drop a whole 5-minute bar for one missing print.)

Indicators run on the continuous series of these 5-minute closes, prior sessions included (no reset at the open), from
the first loaded session: HIST loads from 2015-11-01 (warm-up), DEV from 2024-08-01 (July 2024 is locked, never read), so
DEV's indicators warm up in its first sessions, as the engine's do.
  RSI(14)       Wilder: the first average gain / loss = the mean of the first 14 close-to-close changes, then
                avg = (avg x 13 + change) / 14. RSI = 100 - 100 / (1 + gain / loss); 100 when loss = 0 < gain, 50 when both
                are 0. Valid from the 15th close.
  BB(20, 2)     middle = mean of the last 20 closes; bands = middle +/- 2 x their population sd (ddof 0). Valid from the 20th.
  EMA(n)        alpha = 2 / (n + 1), seeded with the first close (as sprint/data._ema). Valid from the n-th close.
  MACD(12,26,9) line = EMA12 - EMA26; signal = EMA9 of the line (seeded with its first value); histogram = line - signal.
                The line is valid from the 26th close, the signal and histogram from the 34th.
  ATR(14)       Wilder (sprint/data._wilder) of the true range max(H - L, |H - C_prev|, |L - C_prev|), C_prev = the previous
                5-minute close of the series (the prior session's last bar for a day's first bar); the first bar's TR is
                H - L. Valid from the 14th bar.
Decisions are taken at the close of a finished 5-minute bar finishing 09:45 to 15:00 (b = 2..65) whose next 1-minute bar
lies before the close (on 1:00 PM early-close days b <= 40). The decision's 1-minute index is 5b + 4 (the bar's last
minute); entries fill at the next 1-minute bar. A cross needs the indicator valid on this bar and on the previous bar of the
continuous series (the warm-up).

Rules (side "C" = long / calls, "P" = short / puts):
  D1 ind_rsi    RSI crosses up through 30 (previous <= 30 < now) -> long; down through 70 (previous >= 70 > now) -> short.
  D2 ind_bb     a close back above the lower band after the previous close was below it (prev close < prev lower and
                close > lower) -> long; mirrored at the upper band (prev close > prev upper and close < upper) -> short.
  D3 ind_ema    EMA(9) crosses above EMA(21) (prev EMA9 <= prev EMA21 and EMA9 > EMA21) -> long; below -> short.
  D4 ind_macd   the MACD line crosses above its signal (prev line <= prev signal and line > signal) -> long; below -> short.
  D5 conf_level_rsi (Addendum 10.3)  levels from sprint/levels.LevelMap known at the end of the decision minute 5b + 4.
                Support = PDL, PML, OR30L, VWAP-2, VAL, PWL; resistance = PDH, PMH, OR30H, VWAP+2, VAH, PWH.
                Long: the 5-minute bar's low <= level + 0.10 x ATR(14, 5m) (at, within, or traded through a support level),
                RSI(14) at that bar <= 30, and the bar closes above that level. Short: the bar's high >= level - 0.10 x ATR at
                a resistance level, RSI >= 70, close below it. Of several qualifying levels the one nearest the close counts
                (ties: the first in price order). Share stop: that level -/+ 0.10 x ATR.
                Made-up-levels benchmark: the same rule on LevelMap.fake(seed), seeds 1-5 (the kinds keep their labels).
  D6 conf_trend_pullback (Addendum 10.3)  Long: close > VWAP, EMA9 > EMA21, the bar's low within 0.10 x ATR of VWAP or of
                EMA21 (|low - VWAP| <= 0.10 ATR or |low - EMA21| <= 0.10 ATR: literal "at or within"; unlike D5 the text does
                not add "or traded through"), the MACD histogram above its value on the previous bar, and the close above
                both VWAP and EMA21. Short mirrored with the bar's high. VWAP = the session VWAP at the decision minute
                (sprint/data, from 09:30). Share stop: the bar's low - 0.10 x ATR (long) / high + 0.10 x ATR (short).
Signals are dicts {"idx", "side", "price", "info"}; info carries the share stop for D5/D6 and the level for D5.
The matched-random twin of the option variants (`random_side`) keeps every signal's day and minute and draws its side from
a fixed seed (CRC32 of seed|symbol|day|minute): "same days and times with a random side".
"""
import math
import zlib

import numpy as np

from .data import _ema, _wilder

N = 390
FIRST_B, LAST_B = 2, 65                  # 5-minute bars finishing 09:45 .. 15:00
RSI_N, BB_N, BB_K = 14, 20, 2.0
ATR_N, NEAR_ATR = 14, 0.10
SUPPORT = ("PDL", "PML", "OR30L", "VWAP-2", "VAL", "PWL")
RESIST = ("PDH", "PMH", "OR30H", "VWAP+2", "VAH", "PWH")
RULES = ("ind_rsi", "ind_bb", "ind_ema", "ind_macd", "conf_level_rsi", "conf_trend_pullback")
LABELS = {"ind_rsi": "D1", "ind_bb": "D2", "ind_ema": "D3", "ind_macd": "D4", "conf_level_rsi": "D5",
          "conf_trend_pullback": "D6"}
STOP_RULES = ("conf_level_rsi", "conf_trend_pullback")      # shares: level/bar stop, no signal exit (Addendum 10.3)


def bars5(g):
    """(78, 5) O, H, L, C, V of one session's 5-minute bars from its (390, 5) 1-minute grid; NaN rows = absent bars."""
    w = g.reshape(78, 5, 5)
    ok = ~np.isnan(w[:, :, 3])
    has = ok.any(axis=1)
    out = np.full((78, 5), np.nan)
    if not has.any():
        return out
    first = np.argmax(ok, axis=1)
    last = 4 - np.argmax(ok[:, ::-1], axis=1)
    rows = np.where(has)[0]
    out[rows, 0] = w[rows, first[rows], 0]
    out[rows, 3] = w[rows, last[rows], 3]
    hi = np.where(ok, w[:, :, 1], -np.inf).max(axis=1)
    lo = np.where(ok, w[:, :, 2], np.inf).min(axis=1)
    out[rows, 1] = hi[rows]
    out[rows, 2] = lo[rows]
    out[rows, 4] = np.where(ok, np.nan_to_num(w[:, :, 4]), 0.0).sum(axis=1)[rows]
    return out


def rsi_wilder(c, n=RSI_N):
    out = np.full(len(c), np.nan)
    if len(c) <= n:
        return out
    d = np.diff(c)
    g, l = np.maximum(d, 0.0), np.maximum(-d, 0.0)
    ag, al = float(g[:n].mean()), float(l[:n].mean())

    def val(a, b):
        if b == 0:
            return 100.0 if a > 0 else 50.0
        return 100.0 - 100.0 / (1.0 + a / b)
    out[n] = val(ag, al)
    for k in range(n, len(d)):
        ag = (ag * (n - 1) + g[k]) / n
        al = (al * (n - 1) + l[k]) / n
        out[k + 1] = val(ag, al)
    return out


def _mask_head(x, k):
    x = np.array(x, float)
    x[:min(k, len(x))] = np.nan
    return x


def bollinger(c, n=BB_N, k=BB_K):
    m = np.full(len(c), np.nan)
    sd = np.full(len(c), np.nan)
    if len(c) >= n:
        from numpy.lib.stride_tricks import sliding_window_view
        win = sliding_window_view(c, n)
        m[n - 1:] = win.mean(axis=1)
        sd[n - 1:] = win.std(axis=1)                       # population sd (ddof 0)
    return m, m + k * sd, m - k * sd


class Ind5:
    """5-minute bars and indicators of one data.Series (all its sessions, continuous)."""

    def __init__(self, series):
        self.series = series
        parts, owner, bidx = [], [], []
        self.span = {}
        k = 0
        for d in series.days:
            b5 = bars5(series.rth[d])
            ok = np.where(~np.isnan(b5[:, 3]))[0]
            self.span[d] = (k, k + len(ok))
            parts.append(b5[ok])
            bidx.append(ok)
            owner += [d] * len(ok)
            k += len(ok)
        arr = np.concatenate(parts) if parts else np.zeros((0, 5))
        self.O, self.H, self.L, self.C, self.V = (arr[:, j] for j in range(5))
        self.b = np.concatenate(bidx) if bidx else np.zeros(0, int)
        self.day = owner
        c = self.C
        self.rsi = rsi_wilder(c)
        self.bb_mid, self.bb_up, self.bb_lo = bollinger(c)
        self.ema9 = _mask_head(_ema(c, 9), 8) if len(c) else c
        self.ema21 = _mask_head(_ema(c, 21), 20) if len(c) else c
        e12, e26 = (_ema(c, 12), _ema(c, 26)) if len(c) else (c, c)
        line = e12 - e26
        sig = _ema(line, 9) if len(c) else line
        self.macd = _mask_head(line, 25)
        self.macd_sig = _mask_head(sig, 33)
        self.macd_hist = _mask_head(line - sig, 33)
        pc = np.concatenate([[np.nan], c[:-1]])
        tr = np.maximum(self.H - self.L, np.maximum(np.abs(self.H - pc), np.abs(self.L - pc)))
        if len(tr):
            tr[0] = self.H[0] - self.L[0]
        self.atr = _wilder(tr, ATR_N) if len(tr) else tr

    @classmethod
    def of(cls, series):
        hit = series.__dict__.get("_ind5")
        if hit is None:
            hit = cls(series)
            series.__dict__["_ind5"] = hit
        return hit

    def decision_bars(self, day, close_n):
        """Continuous positions k of the day's decision bars (finishing 09:45..15:00, next minute before the close)."""
        a, z = self.span.get(day, (0, 0))
        return [k for k in range(a, z) if k >= 1 and FIRST_B <= self.b[k] <= LAST_B and 5 * self.b[k] + 5 < close_n]

    def minute(self, k):
        return int(5 * self.b[k] + 4)


def _ok(*xs):
    return not any(x is None or (isinstance(x, float) and math.isnan(x)) for x in xs)


def _sig(ind, k, side, info=None):
    return {"idx": ind.minute(k), "side": side, "price": float(ind.C[k]), "info": info or {}}


def signals(ctx, rule, fake_seed=None, ind=None):
    """The rule's decisions on ctx's day, in time order. D5 reads ctx.levels(fake_seed) (the made-up levels for a seed)."""
    ind = ind or Ind5.of(ctx.series)
    ks = ind.decision_bars(ctx.day, ctx.close_idx)
    out = []
    if rule == "ind_rsi":
        r = ind.rsi
        for k in ks:
            r0, r1 = float(r[k - 1]), float(r[k])
            if not _ok(r0, r1):
                continue
            if r0 <= 30.0 < r1:
                out.append(_sig(ind, k, "C", {"rsi": r1}))
            elif r0 >= 70.0 > r1:
                out.append(_sig(ind, k, "P", {"rsi": r1}))
    elif rule == "ind_bb":
        C, up, lo = ind.C, ind.bb_up, ind.bb_lo
        for k in ks:
            if not _ok(float(lo[k - 1]), float(lo[k])):
                continue
            if C[k - 1] < lo[k - 1] and C[k] > lo[k]:
                out.append(_sig(ind, k, "C"))
            elif C[k - 1] > up[k - 1] and C[k] < up[k]:
                out.append(_sig(ind, k, "P"))
    elif rule in ("ind_ema", "ind_macd"):
        a, b = (ind.ema9, ind.ema21) if rule == "ind_ema" else (ind.macd, ind.macd_sig)
        for k in ks:
            a0, b0, a1, b1 = float(a[k - 1]), float(b[k - 1]), float(a[k]), float(b[k])
            if not _ok(a0, b0, a1, b1):
                continue
            if a0 <= b0 and a1 > b1:
                out.append(_sig(ind, k, "C"))
            elif a0 >= b0 and a1 < b1:
                out.append(_sig(ind, k, "P"))
    elif rule == "conf_level_rsi":
        lm = None
        for k in ks:
            r, atr = float(ind.rsi[k]), float(ind.atr[k])
            if not _ok(r, atr) or 30.0 < r < 70.0:
                continue
            lm = lm or ctx.levels(fake_seed)
            i = ind.minute(k)
            c, near = float(ind.C[k]), NEAR_ATR * atr
            if r <= 30.0:
                cands = [(px, kd) for px, kd in lm.at(i) if kd in SUPPORT and ind.L[k] <= px + near and c > px]
                if cands:
                    px, kd = min(cands, key=lambda x: abs(c - x[0]))
                    out.append(_sig(ind, k, "C", {"level": px, "kind": kd, "stop": px - near, "rsi": r, "atr": atr}))
            else:
                cands = [(px, kd) for px, kd in lm.at(i) if kd in RESIST and ind.H[k] >= px - near and c < px]
                if cands:
                    px, kd = min(cands, key=lambda x: abs(c - x[0]))
                    out.append(_sig(ind, k, "P", {"level": px, "kind": kd, "stop": px + near, "rsi": r, "atr": atr}))
    elif rule == "conf_trend_pullback":
        for k in ks:
            i = ind.minute(k)
            vw = _vwap_at(ctx, i)
            e9, e21, atr = float(ind.ema9[k]), float(ind.ema21[k]), float(ind.atr[k])
            h0, h1 = float(ind.macd_hist[k - 1]), float(ind.macd_hist[k])
            if not _ok(vw, e9, e21, atr, h0, h1):
                continue
            c, near = float(ind.C[k]), NEAR_ATR * atr
            lo, hi = float(ind.L[k]), float(ind.H[k])
            if c > vw and e9 > e21 and (abs(lo - vw) <= near or abs(lo - e21) <= near) and h1 > h0 and c > e21:
                out.append(_sig(ind, k, "C", {"stop": lo - near, "vwap": vw, "ema21": e21, "atr": atr}))
            elif c < vw and e9 < e21 and (abs(hi - vw) <= near or abs(hi - e21) <= near) and h1 < h0 and c < e21:
                out.append(_sig(ind, k, "P", {"stop": hi + near, "vwap": vw, "ema21": e21, "atr": atr}))
    else:
        raise ValueError(f"unknown indicator rule {rule}")
    return out


def _vwap_at(ctx, i):
    """Session VWAP known at the end of minute i (the last defined value at or before i)."""
    v = ctx.vwap
    for j in range(i, -1, -1):
        if not math.isnan(v[j]):
            return float(v[j])
    return math.nan


def random_side(sigs, seed, sym, day):
    """The matched-random twin: the same decisions (day, minute, price) with a seeded coin-flip side."""
    out = []
    for s in sigs:
        u = zlib.crc32(f"{seed}|{sym}|{day}|{s['idx']}".encode())
        out.append(dict(s, side="C" if u % 2 == 0 else "P", info=dict(s["info"], random_seed=seed)))
    return out
