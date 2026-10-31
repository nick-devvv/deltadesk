"""sprint/entries.py - entry signals for the sprint (docs/research/SPRINT_PLAN.md, "Entries tested").

Every signal is decided on a FINISHED 1-minute bar (index i = regular-hours bar, 0 = 09:30) and filled by the engine
at the next option print after it (sprint/fills.py). A Signal carries the side ("C" calls, "P" puts), the decision
bar, the underlying close at that bar and `invalid`: the underlying level that proves the idea wrong (used by the
level stop, judged on finished 1-minute closes with a buffer of max($0.02, 0.05 x ATR(14, 1m))).
Each definition below was written before the setup's first run (pre-registered 2026-10-31).

IMPLEMENTED
  orb{15,30,60}   ORB breakout, both sides. Range = high/low of the first N regular-hours minutes (all N bars must
                  exist). Calls: the FIRST finished 1-minute close above the range high; puts: the FIRST finished close
                  below the range low (first break only, per side). The signal bar must finish by 12:00 ET (last
                  signal bar 11:59). invalid = the broken edge (range high for calls, low for puts).
  noise           the `noise` ledger's band rules, reusing noiseband.sigma_profile (14 prior sessions with >= 300
                  regular-hours bars, at least 10) and noiseband's band formula: upper = max(open, prior close) x
                  (1 + sigma), lower = min(open, prior close) x (1 - sigma), checked only on the bars that finish at
                  HH:00 / HH:30 from 10:00 to 15:00. Calls above upper, puts below lower. invalid = upper (calls) /
                  lower (puts). Exits for this entry use sim's "noise" stop: at each check a close through
                  max(upper, VWAP) (calls) / min(lower, VWAP) (puts) exits, a signal from the other side exits
                  (reversal), the 20% premium ceiling acts every minute, all out 15:25.
  noise_nocap     the twin: identical, except the 20% premium ceiling is NOT checked every minute (band/VWAP and
                  reversal exits at the checks only, all out 15:25).
  vwap_macd       Nick's bot setup "VWAP + 2-minute MACD cross, entering on the VWAP retest":
                  2-minute bars anchored at 09:30 (finished only); MACD(12, 26, 9) on those 2-minute closes, continuing
                  from the two prior sessions' 2-minute closes. VWAP = session VWAP through the end of the 2-minute bar;
                  zone z = max($0.03, 0.10 x ATR(14, 1m)); tol = $0.01.
                  ARM (calls): a 2-minute bar starting at or after 09:44 closes above VWAP + tol AND MACD crosses above
                  its signal on that bar (M[t-1] <= S[t-1], M[t] > S[t]). Puts mirrored.
                  ENTER: a later 2-minute bar, within 10 bars of the arming bar, with low <= VWAP + z (the retest),
                  close > VWAP + tol, close > open, and MACD still above its signal. Puts mirrored.
                  CANCEL: a 2-minute close below VWAP - z, a MACD cross down, or 10 bars without a retest. One entry
                  per arming; at most one entry per side per day. Signal bars finish by 15:15.
                  invalid = min(retest bar low, VWAP - z) (calls) / max(retest bar high, VWAP + z) (puts).
  pd_retest       Prior-day high/low retest + 9 EMA pullback. EMA9 = 9-period EMA of 1-minute regular-hours closes
                  (continuing across sessions); z = max($0.03, 0.10 x ATR(14, 1m)).
                  ARM (calls): the first finished 1-minute close above PDH + $0.01 at or after 09:31.
                  ENTER: a later finished bar with low <= PDH + z (it came back to the level) AND low <= EMA9 + z (and
                  the EMA), closing above both PDH and EMA9 and above its own open. Puts mirrored on PDL.
                  CANCEL: a finished close below PDH - z before the entry (the break failed); no re-arm that day.
                  One entry per side per day; signal bars from 09:45, finishing by 15:15. invalid = PDH - z / PDL + z.
  failed_break    Failed-break calls (calls only). Support levels known at the time: PDL, PML, OR15L, OR30L.
                  BREAK: a finished 1-minute close below a support level by more than $0.01 (from 09:45).
                  SIGNAL: within the next 5 bars, a finished close back above that level, provided the lowest low since
                  the break stayed within 0.5 x ATR(14, 5m) of the level (a probe, not a collapse). One signal per
                  level per day, signal bars finishing by 15:15. invalid = the lowest low since the break.
  flush           Reversal after a flush, both sides. Calls: within the last 5 finished 1-minute bars the low fell at
                  least 1.5 x ATR(14, 5m) below the highest high of those 5 bars, the flush low is the session's low so
                  far, and at least one of the 5 bars had volume >= 2x the mean of the 20 bars before them. SIGNAL: the
                  first finished bar, within 5 bars after the flush low, that closes above the prior bar's high. Puts
                  mirrored (spike to a new session high, close below the prior bar's low). One per side per day; signal
                  bars from 09:45, finishing by 15:15. invalid = the flush low (calls) / spike high (puts).
"""
import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np

ORB_CUTOFF = 149                 # the 11:59 bar finishes at 12:00
DESK_FIRST, DESK_LAST = 15, 344  # 09:45 bar .. the bar finishing 15:15 (15:14)
CHECKS = tuple(range(29, 330, 30))   # bars finishing at 10:00, 10:30, ... 15:00


@dataclass
class Signal:
    setup: str
    symbol: str
    day: date
    side: str
    idx: int
    price: float
    invalid: float = None
    info: dict = field(default_factory=dict)

    @property
    def key(self):
        return f"{self.symbol}:{self.day}:{self.setup}:{self.side}:{self.idx}"


def _z(ctx, i):
    a = ctx.atr1[i] if i >= 0 else math.nan
    return max(0.03, 0.10 * (0.0 if math.isnan(a) else float(a)))


# ---------------------------------------------------------------- ORB
def orb(ctx, minutes, side="both"):
    o_h, o_l = ctx.h[:minutes], ctx.l[:minutes]
    if np.isnan(ctx.c[:minutes]).any():
        return []
    orh, orl = float(o_h.max()), float(o_l.min())
    out, done = [], set()
    last = min(ORB_CUTOFF, ctx.close_idx - 2)
    for i in range(minutes, last + 1):
        c = ctx.c[i]
        if math.isnan(c):
            continue
        if "C" not in done and c > orh:
            done.add("C")
            if side in ("both", "C"):
                out.append(Signal(f"orb{minutes}", ctx.sym, ctx.day, "C", i, float(c), orh, {"or_high": orh, "or_low": orl}))
        if "P" not in done and c < orl:
            done.add("P")
            if side in ("both", "P"):
                out.append(Signal(f"orb{minutes}", ctx.sym, ctx.day, "P", i, float(c), orl, {"or_high": orh, "or_low": orl}))
        if len(done) == 2:
            break
    return out


# ---------------------------------------------------------------- noise band (reuses noiseband's math)
def noise_bands(ctx):
    """{check bar index: (upper, lower)} for the day, from noiseband.sigma_profile on regular-hours bars."""
    import pandas as pd
    import noiseband
    s, d = ctx.series, ctx.day
    days = s.prior_days(d, 20) + [d]
    frames = []
    for x in days:
        g = s.rth[x]
        idx = pd.date_range(f"{x} 09:30", periods=390, freq="1min", tz="America/New_York")
        f = pd.DataFrame(g, index=idx, columns=["Open", "High", "Low", "Close", "Volume"]).dropna(subset=["Close"])
        frames.append(f)
    m1 = pd.concat(frames)
    prof, n = noiseband.sigma_profile(m1, d)
    prev = s.prev_day(d)
    if prof is None or prev is None or math.isnan(ctx.o[0]):
        return {}
    o, pc = float(ctx.o[0]), prev["close"]
    out = {}
    for i in CHECKS:
        m = i + 1                                     # minutes after 09:30 at the bar's end
        if m in prof.index:
            sig = float(prof.loc[m])
            out[i] = (round(max(o, pc) * (1 + sig), 4), round(min(o, pc) * (1 - sig), 4))
    return out


def noise(ctx, side="both", cap=True):
    b = noise_bands(ctx)
    out = []
    for i, (up, lo) in sorted(b.items()):
        if i >= ctx.close_idx - 1:
            break
        c = ctx.c[i]
        if math.isnan(c):
            continue
        sd = "C" if c > up else "P" if c < lo else None
        if sd and side in ("both", sd):
            out.append(Signal("noise" if cap else "noise_nocap", ctx.sym, ctx.day, sd, i, float(c), up if sd == "C" else lo,
                              {"bands": b, "cap": cap, "upper": up, "lower": lo}))
    return out


# ---------------------------------------------------------------- VWAP + 2m MACD retest
def _bars2(ctx):
    """Finished 2-minute bars of the day: list of (start_idx, end_idx, o, h, l, c)."""
    out = []
    for b in range(0, 390, 2):
        w = slice(b, b + 2)
        if np.isnan(ctx.c[w]).any():
            continue
        out.append((b, b + 1, float(ctx.o[b]), float(np.max(ctx.h[w])), float(np.min(ctx.l[w])), float(ctx.c[b + 1])))
    return out


def _macd(closes):
    def ema(x, n):
        a, prev, out = 2 / (n + 1), None, []
        for v in x:
            prev = v if prev is None else prev + a * (v - prev)
            out.append(prev)
        return np.array(out)
    m = ema(closes, 12) - ema(closes, 26)
    return m, ema(m, 9)


def vwap_macd(ctx, side="both"):
    s, d = ctx.series, ctx.day
    prior = []
    for x in s.prior_days(d, 2):
        g = s.rth[x]
        prior += [float(g[b + 1, 3]) for b in range(0, 390, 2) if not np.isnan(g[b:b + 2, 3]).any()]
    bars = _bars2(ctx)
    if len(prior) + len(bars) < 40:
        return []
    M, S = _macd(np.array(prior + [x[5] for x in bars]))
    off = len(prior)
    armed, used, out = {}, set(), []
    for t, (b0, b1, o, h, l, c) in enumerate(bars):
        k = off + t
        vw = ctx.vwap[b1]
        if math.isnan(vw) or b1 > DESK_LAST:
            continue
        z = _z(ctx, b1)
        up_x = M[k - 1] <= S[k - 1] and M[k] > S[k]
        dn_x = M[k - 1] >= S[k - 1] and M[k] < S[k]
        for sd in list(armed):
            a = armed[sd]
            if sd == "C" and (c < vw - z or dn_x) or sd == "P" and (c > vw + z or up_x) or t - a > 10:
                del armed[sd]
        for sd in ("C", "P"):
            if sd in used or sd not in armed or armed[sd] == t:
                continue
            if sd == "C" and l <= vw + z and c > vw + 0.01 and c > o and M[k] > S[k] or \
               sd == "P" and h >= vw - z and c < vw - 0.01 and c < o and M[k] < S[k]:
                used.add(sd)
                del armed[sd]
                if side in ("both", sd) and b1 >= DESK_FIRST:
                    inv = min(l, vw - z) if sd == "C" else max(h, vw + z)
                    out.append(Signal("vwap_macd", ctx.sym, d, sd, b1, c, inv, {"vwap": vw}))
        if b0 >= 14:
            if up_x and c > vw + 0.01 and "C" not in used:
                armed["C"] = t
            if dn_x and c < vw - 0.01 and "P" not in used:
                armed["P"] = t
    return out


# ---------------------------------------------------------------- prior-day high/low retest + 9 EMA
def pd_retest(ctx, side="both"):
    prev = ctx.series.prev_day(ctx.day)
    if prev is None:
        return []
    out = []
    for sd, lvl in (("C", prev["high"]), ("P", prev["low"])):
        if side not in ("both", sd):
            continue
        armed = False
        for i in range(1, min(DESK_LAST, ctx.close_idx - 2) + 1):
            c, o, l, h, e = ctx.c[i], ctx.o[i], ctx.l[i], ctx.h[i], ctx.ema9[i]
            if math.isnan(c) or math.isnan(e):
                continue
            z = _z(ctx, i)
            if not armed:
                if (c > lvl + 0.01) if sd == "C" else (c < lvl - 0.01):
                    armed = True
                continue
            if (c < lvl - z) if sd == "C" else (c > lvl + z):
                break                                             # the break failed: no re-arm today
            if i < DESK_FIRST:
                continue
            if sd == "C" and l <= lvl + z and l <= e + z and c > lvl and c > e and c > o or \
               sd == "P" and h >= lvl - z and h >= e - z and c < lvl and c < e and c < o:
                out.append(Signal("pd_retest", ctx.sym, ctx.day, sd, i, float(c), lvl - z if sd == "C" else lvl + z, {"level": lvl}))
                break
    return out


# ---------------------------------------------------------------- failed-break calls
def failed_break(ctx, side="both"):
    if side not in ("both", "C"):
        return []
    lv = ctx.levels()
    out, used = [], set()
    pending = {}
    for i in range(DESK_FIRST, min(DESK_LAST, ctx.close_idx - 2) + 1):
        c = ctx.c[i]
        if math.isnan(c):
            continue
        a5 = ctx.atr5[i]
        known = {k: px for px, k in lv.at(i - 1) if k in ("PDL", "PML", "OR15L", "OR30L")}
        for k, (lvl, i0, low) in list(pending.items()):
            low = min(low, float(ctx.l[i]))
            pending[k] = (lvl, i0, low)
            if c > lvl:
                del pending[k]
                used.add(k)
                if not math.isnan(a5) and lvl - low <= 0.5 * a5:
                    out.append(Signal("failed_break", ctx.sym, ctx.day, "C", i, float(c), low, {"level": lvl, "kind": k}))
            elif i - i0 >= 5:
                del pending[k]
                used.add(k)
        for k, lvl in known.items():
            if k not in used and k not in pending and c < lvl - 0.01:
                pending[k] = (lvl, i, float(ctx.l[i]))
    return out


# ---------------------------------------------------------------- reversal after a flush
def flush(ctx, side="both"):
    out, done = [], set()
    for sd in ("C", "P"):
        if side not in ("both", sd):
            continue
        flush_i = None
        for i in range(25, min(DESK_LAST, ctx.close_idx - 2) + 1):
            if math.isnan(ctx.c[i]) or sd in done:
                continue
            a5 = ctx.atr5[i]
            if flush_i is None and not math.isnan(a5):
                w = slice(i - 4, i + 1)
                vol20 = np.nanmean(ctx.v[i - 24:i - 4])
                spike = np.nanmax(ctx.v[w]) >= 2 * vol20 if vol20 > 0 else False
                if sd == "C":
                    lo = float(np.nanmin(ctx.l[w]))
                    if np.nanmax(ctx.h[w]) - lo >= 1.5 * a5 and lo <= np.nanmin(ctx.l[:i + 1]) and spike:
                        flush_i = i - 4 + int(np.nanargmin(ctx.l[w]))
                else:
                    hi = float(np.nanmax(ctx.h[w]))
                    if hi - np.nanmin(ctx.l[w]) >= 1.5 * a5 and hi >= np.nanmax(ctx.h[:i + 1]) and spike:
                        flush_i = i - 4 + int(np.nanargmax(ctx.h[w]))
                continue
            if flush_i is not None:
                if i - flush_i > 5:
                    flush_i = None
                    continue
                if i > flush_i and i >= DESK_FIRST and (ctx.c[i] > ctx.h[i - 1] if sd == "C" else ctx.c[i] < ctx.l[i - 1]):
                    ext = float(ctx.l[flush_i]) if sd == "C" else float(ctx.h[flush_i])
                    out.append(Signal("flush", ctx.sym, ctx.day, sd, i, float(ctx.c[i]), ext, {"flush_bar": flush_i}))
                    done.add(sd)
    return out


SETUPS = {
    "orb15": lambda ctx, side="both": orb(ctx, 15, side),
    "orb30": lambda ctx, side="both": orb(ctx, 30, side),
    "orb60": lambda ctx, side="both": orb(ctx, 60, side),
    "noise": lambda ctx, side="both": noise(ctx, side, cap=True),
    "noise_nocap": lambda ctx, side="both": noise(ctx, side, cap=False),
    "vwap_macd": vwap_macd,
    "pd_retest": pd_retest,
    "failed_break": failed_break,
    "flush": flush,
}
ENTRY_WINDOWS = {"orb15": (15, ORB_CUTOFF), "orb30": (30, ORB_CUTOFF), "orb60": (60, ORB_CUTOFF), "noise": (29, 329),
                 "noise_nocap": (29, 329), "vwap_macd": (DESK_FIRST, DESK_LAST), "pd_retest": (DESK_FIRST, DESK_LAST),
                 "failed_break": (DESK_FIRST, DESK_LAST), "flush": (DESK_FIRST, DESK_LAST)}


def signals(ctx, setup, side="both"):
    if setup not in SETUPS:
        raise ValueError(f"unknown setup {setup}")
    return SETUPS[setup](ctx, side)
