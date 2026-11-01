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
  failed_break_* (setups_v2 deep dive, pre-registered 2026-10-31 after setups_v1, before any v2 run): the same rule with
                  ONE number changed. _w3 / _w10: the close back above must come within 3 / 10 bars (base 5).
                  _p025 / _p075 / _p100: the probe may reach 0.25 / 0.75 / 1.0 x ATR(14, 5m) below the level (base 0.5).
                  _pd: prior-day and premarket lows only (PDL, PML). _or: opening-range lows only (OR15L, OR30L).
  failed_high     The mirror, puts only: a finished close above a resistance level (PDH, PMH, OR15H, OR30H) by more
                  than $0.01, then within 5 bars a finished close back below it, the highest high since the break
                  within 0.5 x ATR(14, 5m) of the level. invalid = the highest high since the break. Tests whether
                  the failed-break idea works on both sides (SPRINT_PLAN robustness: "works on both sides").
  time_1030 / time_1100   (otm_v1, pre-registered 2026-10-31 from Option Alpha's Top Backtests list, where far
                  out-of-the-money 0DTE SPX/XSP long puts at 10:30 and long calls at 11:00 fill the top ranks): a signal on
                  the bar that finishes at 10:30 (index 59) / 11:00 (index 89), on the side(s) the run asks for, every
                  session. invalid = none (these runs use a fixed premium exit). The edge, if any, comes from the
                  contract (far OTM) and the day filters, not from the timing.
  time_1000 / time_1200 / time_1300 / time_1400   (SPRINT_PLAN Amendment 9, the strategy factory, pre-registered
                  2026-11-01 before any run): the same rule on the bar that finishes at 10:00 (index 29), 12:00 (149),
                  13:00 (209) and 14:00 (269). No signal when that bar is missing or within 2 bars of the close (so no
                  13:00 or 14:00 signal on a 1:00 PM early-close day).
  newhigh_c       (round 8, SPRINT_PLAN Amendment 10 B3 "wait for proof", pre-registered 2026-11-01 before any round-8 run;
                  calls only) the FIRST finished bar with index 89-269 (finishing 11:00-14:00) whose close is strictly above
                  every earlier high of the session (bars 0..i-1) AND whose relative volume at that bar (daytype rvol, the
                  value stamped as f_rvol) is at least 1.06 (FIN-H's frozen cut). Both conditions qualify the same bar
                  (literal reading: the first bar meeting all of them, not the first new high checked once). One signal per
                  day and symbol; none within 2 bars of the close (early-close days stop at bar 207). invalid = none (the
                  run uses a fixed premium exit: d03-12t07, -95% stop, all out 15:25).
  flush           Reversal after a flush, both sides. Calls: within the last 5 finished 1-minute bars the low fell at
                  least 1.5 x ATR(14, 5m) below the highest high of those 5 bars, that high came BEFORE the low (a drop),
                  the flush low is the session's low so far, and at least one of the 5 bars had volume >= 2x the mean of
                  the 20 bars before them. The flush low moves down while the drop continues (a lower low resets it).
                  SIGNAL: the first finished bar, within 5 bars after the flush low, that closes above the prior bar's
                  high. Puts mirrored (a spike up to a new session high, then a close below the prior bar's low). One
                  per side per day; signal bars from 09:45, finishing by 15:15. invalid = the flush low (calls) / spike
                  high (puts).
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
    """{check bar index: (upper, lower)} for the day, from noiseband.sigma_profile on regular-hours bars (cached per day)."""
    hit = getattr(ctx, "_noise_bands", None)
    if hit is not None:
        return hit
    ctx._noise_bands = _noise_bands(ctx)
    return ctx._noise_bands


def _noise_bands(ctx):
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


# ---------------------------------------------------------------- failed-break calls (and the v2 variants)
FB_LOW = ("PDL", "PML", "OR15L", "OR30L")
FB_HIGH = ("PDH", "PMH", "OR15H", "OR30H")


def _failed_break(ctx, setup, up=True, window=5, probe=0.5, kinds=None):
    """Failed break of a support (up=True -> calls) or resistance (up=False -> puts) level. See the module docstring."""
    kinds = tuple(kinds or (FB_LOW if up else FB_HIGH))
    prev, pre = ctx.series.prev_day(ctx.day), ctx.series.pre.get(ctx.day)
    base = {}                                                     # the same values the level map lists as PDL/PML (PDH/PMH)
    if prev:
        base["PDL" if up else "PDH"] = prev["low"] if up else prev["high"]
    if pre:
        base["PML" if up else "PMH"] = pre[1] if up else pre[0]
    ext = np.nanmin if up else np.nanmax
    orx = {m: float(ext(ctx.l[:m] if up else ctx.h[:m])) for m in (15, 30)
           if not np.isnan(ctx.l[:m] if up else ctx.h[:m]).all()}
    out, used = [], set()
    pending = {}
    for i in range(DESK_FIRST, min(DESK_LAST, ctx.close_idx - 2) + 1):
        c = ctx.c[i]
        if math.isnan(c):
            continue
        a5 = ctx.atr5[i]
        known = {k: v for k, v in base.items() if k in kinds}    # levels known at the end of bar i - 1
        for m, v in orx.items():
            k = f"OR{m}{'L' if up else 'H'}"
            if k in kinds and i - 1 >= m - 1:
                known[k] = v
        for k, (lvl, i0, ext_px) in list(pending.items()):
            ext_px = min(ext_px, float(ctx.l[i])) if up else max(ext_px, float(ctx.h[i]))
            pending[k] = (lvl, i0, ext_px)
            if (c > lvl) if up else (c < lvl):
                del pending[k]
                used.add(k)
                depth = (lvl - ext_px) if up else (ext_px - lvl)
                if not math.isnan(a5) and depth <= probe * a5:
                    out.append(Signal(setup, ctx.sym, ctx.day, "C" if up else "P", i, float(c), ext_px, {"level": lvl, "kind": k}))
            elif i - i0 >= window:
                del pending[k]
                used.add(k)
        for k, lvl in known.items():
            if k not in used and k not in pending and ((c < lvl - 0.01) if up else (c > lvl + 0.01)):
                pending[k] = (lvl, i, float(ctx.l[i]) if up else float(ctx.h[i]))
    return out


FB_VARIANTS = {                                   # name -> (up, window, probe, kinds); pre-registered 2026-10-31 (setups_v2)
    "failed_break": (True, 5, 0.5, None),
    "failed_break_w3": (True, 3, 0.5, None),
    "failed_break_w10": (True, 10, 0.5, None),
    "failed_break_p025": (True, 5, 0.25, None),
    "failed_break_p075": (True, 5, 0.75, None),
    "failed_break_p100": (True, 5, 1.0, None),
    "failed_break_pd": (True, 5, 0.5, ("PDL", "PML")),
    "failed_break_or": (True, 5, 0.5, ("OR15L", "OR30L")),
    "failed_high": (False, 5, 0.5, None),
}


def failed_break(ctx, side="both", setup="failed_break"):
    up, window, probe, kinds = FB_VARIANTS[setup]
    if side not in ("both", "C" if up else "P"):
        return []
    return _failed_break(ctx, setup, up, window, probe, kinds)


# ---------------------------------------------------------------- fixed-time entries (otm_v1)
def time_entry(ctx, side, idx, setup):
    if idx >= ctx.close_idx - 2 or math.isnan(ctx.c[idx]):
        return []
    sides = ("C", "P") if side == "both" else (side,)
    return [Signal(setup, ctx.sym, ctx.day, s, idx, float(ctx.c[idx]), None, {}) for s in sides]


# ---------------------------------------------------------------- round 8, B3: wait for proof (calls)
NEWHIGH_FIRST, NEWHIGH_LAST, NEWHIGH_RVOL = 89, 269, 1.06


def newhigh_c(ctx, side="both"):
    if side not in ("both", "C"):
        return []
    dt = ctx.daytype()
    for i in range(NEWHIGH_FIRST, min(NEWHIGH_LAST, ctx.close_idx - 3) + 1):
        c = ctx.c[i]
        if math.isnan(c):
            continue
        earlier = ctx.h[:i]
        if np.isnan(earlier).all() or not c > float(np.nanmax(earlier)):
            continue
        rv = dt.features(i).get("rvol")
        if rv is not None and rv >= NEWHIGH_RVOL:
            return [Signal("newhigh_c", ctx.sym, ctx.day, "C", i, float(c), None, {"rvol": rv})]
    return []


# ---------------------------------------------------------------- reversal after a flush
def flush(ctx, side="both"):
    out, done = [], set()
    run_lo = np.fmin.accumulate(np.where(np.isnan(ctx.l), np.inf, ctx.l))
    run_hi = np.fmax.accumulate(np.where(np.isnan(ctx.h), -np.inf, ctx.h))
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
                k_hi, k_lo = int(np.nanargmax(ctx.h[w])), int(np.nanargmin(ctx.l[w]))
                if sd == "C":
                    lo = float(np.nanmin(ctx.l[w]))
                    if np.nanmax(ctx.h[w]) - lo >= 1.5 * a5 and k_hi < k_lo and lo <= run_lo[i] and spike:
                        flush_i = i - 4 + k_lo
                else:
                    hi = float(np.nanmax(ctx.h[w]))
                    if hi - np.nanmin(ctx.l[w]) >= 1.5 * a5 and k_lo < k_hi and hi >= run_hi[i] and spike:
                        flush_i = i - 4 + k_hi
                continue
            if flush_i is not None:
                if (ctx.l[i] < ctx.l[flush_i]) if sd == "C" else (ctx.h[i] > ctx.h[flush_i]):
                    flush_i = i                                   # the flush extends: its extreme moves with it
                    continue
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
    "flush": flush,
    "newhigh_c": newhigh_c,                                     # round 8, B3
}
for _n in FB_VARIANTS:
    SETUPS[_n] = (lambda n: lambda ctx, side="both": failed_break(ctx, side, n))(_n)
TIME_ENTRIES = {"time_1030": 59, "time_1100": 89}
TIME_ENTRIES.update({"time_1000": 29, "time_1200": 149, "time_1300": 209, "time_1400": 269})   # Amendment 9
for _n, _i in TIME_ENTRIES.items():
    SETUPS[_n] = (lambda n, i: lambda ctx, side="both": time_entry(ctx, side, i, n))(_n, _i)
ENTRY_WINDOWS = {"orb15": (15, ORB_CUTOFF), "orb30": (30, ORB_CUTOFF), "orb60": (60, ORB_CUTOFF), "noise": (29, 329),
                 "noise_nocap": (29, 329), "vwap_macd": (DESK_FIRST, DESK_LAST), "pd_retest": (DESK_FIRST, DESK_LAST),
                 "flush": (DESK_FIRST, DESK_LAST)}
ENTRY_WINDOWS.update({_n: (DESK_FIRST, DESK_LAST) for _n in FB_VARIANTS})
ENTRY_WINDOWS.update({_n: (DESK_FIRST, DESK_LAST) for _n in TIME_ENTRIES})
ENTRY_WINDOWS["newhigh_c"] = (NEWHIGH_FIRST, NEWHIGH_LAST)


def signals(ctx, setup, side="both"):
    if setup not in SETUPS:
        raise ValueError(f"unknown setup {setup}")
    return SETUPS[setup](ctx, side)
