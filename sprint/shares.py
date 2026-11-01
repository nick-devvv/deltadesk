"""sprint/shares.py - round 8's share tests (SPRINT_PLAN Amendment 10 Part A and Addenda 10.2/10.3 Part D shares),
pre-registered 2026-11-01 before any round-8 code or run. Every number is a BACKTEST on real Alpaca stock 1-minute bars
(SPY, QQQ, IWM) over HIST 2016-01-04..2024-01-31 (history from 2015-11-01 feeds indicators only) and DEV 2024-08-01..
2026-06-30. No option model. L1 / L2 are never read: `load_series` refuses a range that touches them and drops any bar
dated inside them. Research only: no network, no orders.

Costs, sizing, timing (Amendment 10 "Data and periods"):
  fills     at the open of the bar after the decision bar, +$0.01 a share for a buy and -$0.01 for a sell; "2x costs" =
            $0.02 a side. If that bar is missing, the first bar within 3 minutes after the decision (else the decision is
            skipped; SPY/QQQ/IWM regular-hours bars are rarely missing). No commission.
  sizing    $10,000 notional: shares = floor(10,000 / the decision bar's close). Results in $ and in bps of the entry
            notional (P/L / (shares x the entry bar's open) x 10,000). One position at a time per rule and symbol.
  exit      the close of the bar finishing 15:59 (index 389) -/+ $0.01, or 12:59 (index 209) on 1 PM early-close days
            (the last close at or before it if that bar is missing).
A1 noise_sh (Zarattini, Aziz & Barbon 2024, the paper's final version):
  sigma(t)  for minute index t: the mean over the 14 prior sessions (at least 10 with a bar at t) of
            |close(t) / that session's open - 1| (the open = the session's first regular-hours bar's open). Unlike
            noiseband.sigma_profile no ">= 300 bars" session filter: the amendment's text has none.
  bands     UB(t) = max(open, prior close) x (1 + sigma(t)); LB(t) = min(open, prior close) x (1 - sigma(t)).
  checks    the bars finishing 10:00, 10:30, ..., 15:30 (indices 29, 59, ..., 359) that lie before the exit bar (early-close
            days: through 12:30). flat: close > UB -> long, close < LB -> short. long: close < LB -> reverse to short, else
            close < max(UB, VWAP) -> flat. short mirrored. VWAP = regular-hours session VWAP from 09:30 (sprint/data).
  primary   long and short, $10,000. Secondary (vol-sized): notional = 10,000 x min(4, 0.02 / sd), sd = the sample sd of
            the 14 prior daily close-to-close returns (no trade without 15 prior closes).
A2 last30 (Baltussen et al. 2021 "rest of day"; Gao et al. 2018 first half-hour): r = close of index 359 / prior close - 1
  (secondary, Gao: close of index 29 / prior close - 1). r > 0 buy, r < 0 sell short, at the open of index 360; out at the
  close of 389. No trade on early-close days or when r = 0. Shares: floor(10,000 / the close of the signal bar, 359 or 29).
A3 gapfade_vix (falsifylab 2025, grade C, exploratory): g = open / prior close - 1; gap z = g / the sample sd of the gaps of
  the 60 prior sessions (at least 40). VIX proxy z = (VIXY's prior-session close - the mean of the 60 VIXY closes before it)
  / their sample sd. Trade when |gap z| > 1.0 and VIXY z > 0.5, against the gap, entering at the open of index 60 (after the
  bar finishing 10:30; shares from the close of index 59); no stop; out at the exit bar.
Long-only variants: the same rule where a short decision only closes a long (and never opens a short).
Part D shares (sprint/ind5.py decisions on 5-minute bars, same costs, notional and exit time):
  D1-D4     the opposite signal exits and reverses into it (Addendum 10.2); otherwise out at the exit bar.
  D5, D6    (Addendum 10.3) stop = D5's touched level -/+ 0.10 x ATR(14, 5m), D6's decision bar's low / high -/+ 0.10 x ATR,
            judged on finished 1-minute closes from the entry bar on, exiting at the next bar's open -/+ $0.01; no target;
            out at the exit bar. Literal reading: 10.3 lists only the stop and the exit time for these shares, so an
            opposite signal while a position is open is skipped (one position at a time), not a reversal; a decision
            on the bar whose close triggered a stop is skipped too (the position is still open until the next bar).
  D5 also runs on made-up levels (LevelMap.fake, seeds 1-5).
Part A pass bar (per rule, primary variant, SPY + QQQ + IWM pooled; the long-only variant gets its own line):
  1 at least 300 trades over the 2016-2026 windows; 2 expectancy per trade > 0 at 2x costs; 3 profitable in at least 6 of
  the 8 years 2016-2023 and in DEV 2024-08..2026-06; 4 the bootstrap 95% interval of the daily mean P/L above 0 (every
  session of HIST + DEV, 0 on days without a trade, resampled by session, 2,000 draws, numpy default_rng(29)); 5 positive
  without the best 5 days; 6 beats random direction, p < 0.05 (the same entries and exits with a coin-flip side, 200 draws,
  default_rng(seed) for seeds 31-230; p = share of draws whose total is at or above the rule's); 7 at least 55% of months
  green (months with at least one trade).
"""
import csv
import gzip
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

from . import data, features, ind5, periods

HALF = 0.01
NOTIONAL = 10_000.0
ENTRY_WAIT = 3
EXIT_BAR, EARLY_EXIT_BAR = 389, 209
CHECKS_A1 = tuple(range(29, 360, 30))         # 10:00 ... 15:30
SIGMA_DAYS, SIGMA_MIN = 14, 10
VOL_DAYS, VOL_TARGET, VOL_CAP = 14, 0.02, 4.0
GAP_DAYS, GAP_MIN, VIX_DAYS = 60, 40, 60
GAP_Z, VIX_Z = 1.0, 0.5
SYMBOLS = ("SPY", "QQQ", "IWM")
BOOT_SEED, BOOT_DRAWS = 29, 2000
RANDOM_SEEDS = tuple(range(31, 231))
LABEL = "BACKTEST on real Alpaca stock 1-minute bars (shares, no option model)"
PART_A = ("noise_sh", "last30", "gapfade_vix")
SECONDARY = {"noise_sh": "noise_sh_vol", "last30": "last30_gao"}
FAKE_SEEDS = (1, 2, 3, 4, 5)


# ---------------------------------------------------------------- data
def load_series(sym, a, b, root=None):
    """data.Series for [a, b] after the locked-period guard (refuses L1/L2); bars dated inside L1/L2 are dropped too."""
    periods.guard(a, b)
    df = data.read_stock(sym, a, b, root)
    if df is not None and len(df):
        d = df["ts"].dt.date
        bad = np.zeros(len(df), bool)
        for x, y in periods.LOCKED.values():
            bad |= ((d >= x) & (d <= y)).to_numpy()
        df = df[~bad].reset_index(drop=True)
    return data.Series(sym, df)


def exit_bar(ctx):
    return EARLY_EXIT_BAR if ctx.early else EXIT_BAR


def fill_bar(ctx, i, last, wait=ENTRY_WAIT):
    """The first bar after decision bar i (within `wait` minutes, at most `last`) with an open, or None."""
    for k in range(i + 1, min(i + wait, last) + 1):
        if ctx.has_bar(k) and not math.isnan(ctx.o[k]):
            return k
    return None


def _close_out(ctx, xb, lo):
    """(index, close) of the exit bar, or the last close at or before it after bar lo."""
    for k in range(xb, lo, -1):
        if ctx.has_bar(k):
            return k, float(ctx.c[k])
    return None, None


def _t(i):
    m = 570 + i
    return f"{m // 60:02d}:{m % 60:02d}"


class Book:
    """Builds the trades of one variant on one (symbol, day)."""

    def __init__(self, ctx, variant, src):
        self.ctx, self.variant, self.src = ctx, variant, src
        self.out = []
        self.cur = None

    def open(self, sign, dec, k, shares, notional, info=None):
        self.cur = {"sign": sign, "dec": dec, "k": k, "ref": float(self.ctx.o[k]), "shares": int(shares), "notional": notional,
                    "info": info or {}}

    def close(self, k, ref, reason):
        c = self.cur
        self.cur = None
        sh, sg = c["shares"], c["sign"]
        move = float(ref) - c["ref"]
        pnl = sh * (sg * move - 2 * HALF)
        self.out.append({"variant": self.variant, "symbol": self.ctx.sym, "day": self.ctx.day.isoformat(), "_src": self.src,
                         "side": "L" if sg > 0 else "S", "sign": sg, "decision_idx": c["dec"], "entry_idx": c["k"],
                         "exit_idx": k, "entry_time": _t(c["k"]), "exit_time": _t(k), "shares": sh, "entry_ref": round(c["ref"], 4),
                         "exit_ref": round(float(ref), 4), "entry": round(c["ref"] + sg * HALF, 4), "exit": round(float(ref) - sg * HALF, 4),
                         "move": round(move, 6), "pnl": round(pnl, 4), "pnl_2x": round(sh * (sg * move - 4 * HALF), 4),
                         "bps": round(pnl / (sh * c["ref"]) * 1e4, 4) if sh and c["ref"] else None,
                         "notional": round(c["notional"], 2), "exit_reason": reason,
                         **{f"i_{a}": v for a, v in c["info"].items() if isinstance(v, (int, float, str))}})

    def close_at_end(self):
        if self.cur is None:
            return
        xb = exit_bar(self.ctx)
        k, px = _close_out(self.ctx, xb, self.cur["k"] - 1)
        if k is None:
            k, px = self.cur["k"], float(self.ctx.o[self.cur["k"]])
        self.close(k, px, f"CLOSE {'12:59' if self.ctx.early else '15:59'} bar")


def _shares(notional, px):
    return int(math.floor(notional / px)) if px and px > 0 and not math.isnan(px) else 0


# ---------------------------------------------------------------- A1 noise_sh
def a1_profile(series):
    """Cumulative sums for sigma(t) (cached on the series): (day position, cumulative |move| sums, cumulative counts)."""
    hit = series.__dict__.get("_a1prof")
    if hit is not None and hit[0] == len(series.days):
        return hit[1]
    n = len(series.days)
    M = np.full((n, data.N), np.nan)
    opens = series.daily["open"].to_numpy(float) if n else np.zeros(0)
    for k, d in enumerate(series.days):
        with np.errstate(invalid="ignore", divide="ignore"):
            M[k] = np.abs(series.rth[d][:, 3] / opens[k] - 1)
    ok = ~np.isnan(M)
    cs = np.vstack([np.zeros(data.N), np.cumsum(np.where(ok, M, 0.0), axis=0)])
    cn = np.vstack([np.zeros(data.N), np.cumsum(ok, axis=0)])
    prof = (features.day_pos(series), cs, cn)
    series.__dict__["_a1prof"] = (n, prof)
    return prof


def a1_sigma(series, day):
    """sigma(t), t = 0..389, from the 14 sessions before `day` (NaN where fewer than 10 of them have a bar at t)."""
    pos, cs, cn = a1_profile(series)
    k = pos.get(day)
    if k is None:
        return None
    a = max(0, k - SIGMA_DAYS)
    s, c = cs[k] - cs[a], cn[k] - cn[a]
    with np.errstate(invalid="ignore", divide="ignore"):
        sig = np.where(c >= SIGMA_MIN, s / np.maximum(c, 1), np.nan)
    return sig


def a1_bands(series, day):
    """(UB, LB) arrays over t = 0..389 for `day`, or None (no prior close, no open, or no sigma)."""
    pos = features.day_pos(series)
    k = pos.get(day)
    if not k:
        return None
    o = float(series.daily["open"].iloc[k])
    pc = float(series.daily["close"].iloc[k - 1])
    sig = a1_sigma(series, day)
    if sig is None or math.isnan(o):
        return None
    return max(o, pc) * (1 + sig), min(o, pc) * (1 - sig)


def a1_vol_notional(series, day):
    pos = features.day_pos(series)
    k = pos.get(day)
    if k is None or k < VOL_DAYS + 1:
        return None
    c = series.daily["close"].to_numpy(float)[k - VOL_DAYS - 1:k]
    r = c[1:] / c[:-1] - 1
    sd = float(np.std(r, ddof=1))
    return NOTIONAL * (VOL_CAP if sd <= 0 else min(VOL_CAP, VOL_TARGET / sd))


def a1_day(ctx, src, variant="noise_sh", long_only=False, notional=NOTIONAL):
    bands = a1_bands(ctx.series, ctx.day)
    bk = Book(ctx, variant, src)
    if bands is None or notional is None:
        return bk.out
    UB, LB = bands
    xb = exit_bar(ctx)
    pos = 0
    for i in CHECKS_A1:
        if i >= xb:
            break
        c = ctx.c[i]
        ub, lb = UB[i], LB[i]
        if math.isnan(c) or math.isnan(ub) or math.isnan(lb):
            continue
        vw = ctx.vwap[i]
        want = pos
        if pos == 0:
            want = 1 if c > ub else (-1 if c < lb and not long_only else 0)
        elif pos == 1:
            if c < lb:
                want = 0 if long_only else -1
            elif c < (max(ub, vw) if not math.isnan(vw) else ub):
                want = 0
        else:
            if c > ub:
                want = 1
            elif c > (min(lb, vw) if not math.isnan(vw) else lb):
                want = 0
        if want == pos:
            continue
        k = fill_bar(ctx, i, xb)
        if k is None:
            continue
        if pos != 0:
            why = "NOISE REVERSAL" if want == -pos else "NOISE STOP: close through max/min(band, VWAP)"
            bk.close(k, float(ctx.o[k]), why)
        pos = 0
        if want != 0:
            sh = _shares(notional, float(c))
            if sh > 0:
                bk.open(want, i, k, sh, notional)
                pos = want
    bk.close_at_end()
    return bk.out


def a1_option_signals(ctx):
    """noise_sh as option-twin signals (A-opt, Addendum 10.1): entries at the checks (close > UB -> calls, close < LB ->
    puts) and, per side, the share rule's own exits at every check: {"C": {idx: (reason, is_stop, flip)}, "P": {...}}."""
    bands = a1_bands(ctx.series, ctx.day)
    if bands is None:
        return []
    UB, LB = bands
    xb = exit_bar(ctx)
    ex = {"C": {}, "P": {}}
    sigs = []
    for i in CHECKS_A1:
        if i >= xb:
            break
        c, ub, lb = ctx.c[i], UB[i], LB[i]
        if math.isnan(c) or math.isnan(ub) or math.isnan(lb):
            continue
        vw = ctx.vwap[i]
        if c < lb:
            ex["C"][i] = ("NOISE REVERSAL", False, True)
        elif c < (max(ub, vw) if not math.isnan(vw) else ub):
            ex["C"][i] = ("NOISE STOP: close through max(band, VWAP)", True, False)
        if c > ub:
            ex["P"][i] = ("NOISE REVERSAL", False, True)
        elif c > (min(lb, vw) if not math.isnan(vw) else lb):
            ex["P"][i] = ("NOISE STOP: close through min(band, VWAP)", True, False)
        if c > ub:
            sigs.append({"idx": i, "side": "C", "price": float(c), "info": {"upper": float(ub), "lower": float(lb)}})
        elif c < lb:
            sigs.append({"idx": i, "side": "P", "price": float(c), "info": {"upper": float(ub), "lower": float(lb)}})
    for s in sigs:
        s["exits"] = ex
    return sigs


# ---------------------------------------------------------------- A2 last30
def a2_day(ctx, src, gao=False, long_only=False):
    variant = "last30_gao" if gao else "last30"
    bk = Book(ctx, variant, src)
    if ctx.early:
        return bk.out
    k0 = features.day_pos(ctx.series).get(ctx.day)
    if not k0:
        return bk.out
    pc = float(ctx.series.daily["close"].iloc[k0 - 1])
    j = 29 if gao else 359
    c = ctx.c[j]
    if math.isnan(c):
        return bk.out
    r = float(c) / pc - 1
    if r == 0 or (long_only and r < 0):
        return bk.out
    k = fill_bar(ctx, 359, EXIT_BAR)
    sh = _shares(NOTIONAL, float(c))
    if k is None or sh <= 0:
        return bk.out
    bk.open(1 if r > 0 else -1, j, k, sh, NOTIONAL, {"r": round(r, 6)})
    bk.close_at_end()
    return bk.out


# ---------------------------------------------------------------- A3 gapfade_vix
def gap_table(series):
    hit = series.__dict__.get("_gaps")
    if hit is not None and len(hit) == len(series.days):
        return hit
    o = series.daily["open"].to_numpy(float) if len(series.days) else np.zeros(0)
    c = series.daily["close"].to_numpy(float) if len(series.days) else np.zeros(0)
    g = np.full(len(o), np.nan)
    if len(o) > 1:
        g[1:] = o[1:] / c[:-1] - 1
    series.__dict__["_gaps"] = g
    return g


def a3_signal(series, day, vixy_daily):
    """("C" | "P" | None, info) for `day`: fade a gap with |gap z| > 1.0 when the VIXY z > 0.5. Known before the open."""
    pos = features.day_pos(series)
    k = pos.get(day)
    if not k:
        return None, {}
    g = gap_table(series)
    w = g[max(0, k - GAP_DAYS):k]
    w = w[~np.isnan(w)]
    if len(w) < GAP_MIN or math.isnan(g[k]):
        return None, {}
    sd = float(np.std(w, ddof=1))
    if sd <= 0:
        return None, {}
    gz = float(g[k]) / sd
    _x, _c, vz = features.vixy_prior(vixy_daily, series.days[k - 1], VIX_DAYS)
    info = {"gap": round(float(g[k]), 6), "gap_z": round(gz, 4), "vixy_z": None if vz is None else round(vz, 4)}
    if vz is None or not (abs(gz) > GAP_Z and vz > VIX_Z):
        return None, info
    return ("P" if g[k] > 0 else "C"), info


def a3_day(ctx, src, vixy_daily, long_only=False):
    bk = Book(ctx, "gapfade_vix", src)
    side, info = a3_signal(ctx.series, ctx.day, vixy_daily)
    if side is None or (long_only and side == "P") or math.isnan(ctx.c[59]):
        return bk.out
    xb = exit_bar(ctx)
    k = fill_bar(ctx, 59, xb)
    sh = _shares(NOTIONAL, float(ctx.c[59]))
    if k is None or sh <= 0:
        return bk.out
    bk.open(1 if side == "C" else -1, 59, k, sh, NOTIONAL, info)
    bk.close_at_end()
    return bk.out


def a3_option_signals(ctx):
    """gapfade_vix as an option-twin signal (calls for longs, puts for shorts) at bar 59; held to the all-out."""
    side, info = a3_signal(ctx.series, ctx.day, (ctx.aux or {}).get("VIXY_D"))
    if side is None or math.isnan(ctx.c[59]):
        return []
    return [{"idx": 59, "side": side, "price": float(ctx.c[59]), "info": info, "exits": {"C": {}, "P": {}}}]


# ---------------------------------------------------------------- Part D shares
def d_day(ctx, src, rule, sigs, variant=None, long_only=False):
    """One D rule's share trades on one (symbol, day) from its ind5 decisions."""
    bk = Book(ctx, variant or rule, src)
    xb = exit_bar(ctx)
    sigs = sorted(sigs, key=lambda s: s["idx"])
    if not sigs:
        return bk.out
    if rule not in ind5.STOP_RULES:                      # D1-D4: the opposite signal exits and reverses
        pos = 0
        for s in sigs:
            i = s["idx"]
            if i >= xb:
                break
            sd = 1 if s["side"] == "C" else -1
            if sd == pos or (long_only and sd < 0 and pos == 0):
                continue
            k = fill_bar(ctx, i, xb)
            if k is None:
                continue
            if pos != 0:
                bk.close(k, float(ctx.o[k]), "OPPOSITE SIGNAL" + ("" if long_only else " (reverse)"))
                pos = 0
            if long_only and sd < 0:
                continue
            sh = _shares(NOTIONAL, s["price"])
            if sh > 0:
                bk.open(sd, i, k, sh, NOTIONAL)
                pos = sd
        bk.close_at_end()
        return bk.out
    evs = {s["idx"]: s for s in sigs}                    # D5/D6: stop on 1-minute closes, no signal exit
    pos, busy_until, e_bar, stop = 0, -1, None, None
    for i in range(sigs[0]["idx"], xb + 1):
        if pos != 0 and e_bar <= i < xb:
            c = ctx.c[i]
            if not math.isnan(c) and ((c < stop) if pos > 0 else (c > stop)):
                k = fill_bar(ctx, i, xb, wait=xb)
                if k is not None:
                    bk.close(k, float(ctx.o[k]), f"STOP {stop:.2f}: 1m close {float(c):.2f}")
                    busy_until = k
                    pos = 0
        s = evs.get(i)
        if s is not None and pos == 0 and i >= busy_until and i < xb:
            sd = 1 if s["side"] == "C" else -1
            if long_only and sd < 0:
                continue
            k = fill_bar(ctx, i, xb)
            sh = _shares(NOTIONAL, s["price"])
            if k is not None and sh > 0:
                bk.open(sd, i, k, sh, NOTIONAL, {"stop": round(float(s["info"]["stop"]), 4)})
                stop, e_bar, pos = float(s["info"]["stop"]), k, sd
    bk.close_at_end()
    return bk.out


# ---------------------------------------------------------------- the whole share pass
def variants():
    """Every share variant round 8 runs: name -> (family, long_only). Trials: Part A 8, Part D 12 (fakes are benchmarks)."""
    v = {}
    for r in PART_A:
        v[r] = (r, False)
        v[r + "_lo"] = (r, True)
    v["noise_sh_vol"] = ("noise_sh", False)
    v["last30_gao"] = ("last30", False)
    for r in ind5.RULES:
        v[r] = (r, False)
        v[r + "_lo"] = (r, True)
    for s in FAKE_SEEDS:
        v[f"conf_level_rsi_fake{s}"] = ("conf_level_rsi", False)
        v[f"conf_level_rsi_lo_fake{s}"] = ("conf_level_rsi", True)
    return v


TRIAL_VARIANTS = ("noise_sh", "noise_sh_lo", "noise_sh_vol", "last30", "last30_lo", "last30_gao", "gapfade_vix", "gapfade_vix_lo")
D_TRIAL_VARIANTS = tuple(x for r in ind5.RULES for x in (r, r + "_lo"))


def run_day(ctx, src, vixy_daily):
    """All share variants on one (symbol, day): {variant: [trades]}."""
    out = defaultdict(list)
    out["noise_sh"] += a1_day(ctx, src)
    out["noise_sh_lo"] += a1_day(ctx, src, "noise_sh_lo", long_only=True)
    out["noise_sh_vol"] += a1_day(ctx, src, "noise_sh_vol", notional=a1_vol_notional(ctx.series, ctx.day))
    out["last30"] += a2_day(ctx, src)
    out["last30_lo"] += [dict(t, variant="last30_lo") for t in a2_day(ctx, src, long_only=True)]
    out["last30_gao"] += a2_day(ctx, src, gao=True)
    out["gapfade_vix"] += a3_day(ctx, src, vixy_daily)
    out["gapfade_vix_lo"] += [dict(t, variant="gapfade_vix_lo") for t in a3_day(ctx, src, vixy_daily, long_only=True)]
    ind = ind5.Ind5.of(ctx.series)
    for r in ind5.RULES:
        sg = ind5.signals(ctx, r, ind=ind)
        out[r] += d_day(ctx, src, r, sg)
        out[r + "_lo"] += d_day(ctx, src, r, sg, r + "_lo", long_only=True)
    for s in FAKE_SEEDS:
        sg = ind5.signals(ctx, "conf_level_rsi", fake_seed=s, ind=ind)
        if sg:
            out[f"conf_level_rsi_fake{s}"] += d_day(ctx, src, "conf_level_rsi", sg, f"conf_level_rsi_fake{s}")
            out[f"conf_level_rsi_lo_fake{s}"] += d_day(ctx, src, "conf_level_rsi", sg, f"conf_level_rsi_lo_fake{s}", long_only=True)
    return out


def run(series_by_src, vixy_daily, progress=None):
    """series_by_src: {("HIST"|"DEV", symbol): data.Series}. Trades only inside HIST / DEV themselves (warm-up sessions feed
    indicators only). Returns ({variant: [trades]}, {src: {symbol: [sessions with bars]}})."""
    res = defaultdict(list)
    cover = defaultdict(dict)
    aux = {"VIXY_D": vixy_daily}
    for (src, sym), ser in sorted(series_by_src.items()):
        a, b = periods.HIST if src == "HIST" else periods.DEV
        days = [d for d in ser.days if a <= d <= b and not periods.overlaps(d, d)]
        cover[src][sym] = [d.isoformat() for d in days]
        for n, d in enumerate(days):
            ctx = data.DayContext(ser, d, {}, None, aux=aux)
            for k, v in run_day(ctx, src, vixy_daily).items():
                res[k] += v
            if progress and (n % 500 == 0 or n == len(days) - 1):
                progress(f"  shares {src} {sym} {d} ({n + 1}/{len(days)} sessions)")
    for k in variants():
        res.setdefault(k, [])
    return dict(res), dict(cover)


def write_trades(path, by_variant):
    cols = ["variant", "symbol", "day", "_src", "side", "decision_idx", "entry_idx", "exit_idx", "entry_time", "exit_time", "shares",
            "entry_ref", "exit_ref", "entry", "exit", "move", "pnl", "pnl_2x", "bps", "notional", "exit_reason"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for k in sorted(by_variant):
            for t in ordered(by_variant[k]):
                w.writerow(t)


# ---------------------------------------------------------------- metrics and the pass bar
HIST_A, HIST_B = periods.HIST[0].isoformat(), periods.HIST[1].isoformat()
DEV_A, DEV_B = periods.DEV[0].isoformat(), periods.DEV[1].isoformat()
YEARS = ([(str(y), f"{y}-01-01", f"{y}-12-31") for y in range(2016, 2024)] +
         [("Jan 2024", "2024-01-01", "2024-01-31"), ("Aug-Dec 2024", "2024-08-01", "2024-12-31"),
          ("2025", "2025-01-01", "2025-12-31"), ("Jan-Jun 2026", "2026-01-01", "2026-06-30")])


def ordered(trades):
    return sorted(trades, key=lambda t: (t["day"], t["entry_idx"], t["symbol"], t.get("exit_idx", 0)))


def all_sessions():
    from .book import sessions_between
    return sessions_between(HIST_A, HIST_B) + sessions_between(DEV_A, DEV_B)


def daily(trades, sessions, key="pnl"):
    idx = {d: i for i, d in enumerate(sessions)}
    v = np.zeros(len(sessions))
    for t in trades:
        i = idx.get(t["day"])
        if i is not None:
            v[i] += float(t[key])
    return v


def _pf(p):
    p = np.asarray(p, float)
    lo, w = -p[p < 0].sum(), p[p > 0].sum()
    if lo > 0:
        return round(float(w / lo), 3)
    return math.inf if w > 0 else None


def stats(trades, n_sessions=None):
    tr = ordered(trades)
    p = np.array([float(t["pnl"]) for t in tr])
    out = {"trades": len(tr), "per_session": round(len(tr) / n_sessions, 3) if n_sessions else None}
    if not len(tr):
        return out
    p2 = np.array([float(t["pnl_2x"]) for t in tr])
    bps = np.array([float(t["bps"]) for t in tr if t.get("bps") is not None])
    w, lo = p[p > 0], p[p < 0]
    eq = np.cumsum(p)
    dd = float((eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min())
    out.update({"win_rate": round(len(w) / len(p), 3), "avg_win": round(float(w.mean()), 2) if len(w) else None,
                "avg_loss": round(float(lo.mean()), 2) if len(lo) else None, "expectancy": round(float(p.mean()), 2),
                "exp_bps": round(float(bps.mean()), 3) if len(bps) else None, "expectancy_2x": round(float(p2.mean()), 2),
                "pf": _pf(p), "pf_2x": _pf(p2), "total": round(float(p.sum()), 2), "total_2x": round(float(p2.sum()), 2),
                "max_dd": round(min(dd, 0.0), 2)})
    return out


def steadiness(trades):
    """Months / weeks green (with at least one trade), the longest run of losing months, the worst month."""
    bm, bw = defaultdict(float), defaultdict(float)
    for t in trades:
        bm[t["day"][:7]] += float(t["pnl"])
        y, w, _ = date.fromisoformat(t["day"]).isocalendar()
        bw[f"{y}-W{w:02d}"] += float(t["pnl"])
    months = sorted(bm)
    run = best = 0
    for m in months:
        run = run + 1 if bm[m] < 0 else 0
        best = max(best, run)
    worst = min(bm.items(), key=lambda kv: kv[1]) if bm else None
    return {"months": len(bm), "months_green": sum(1 for v in bm.values() if v > 0),
            "months_green_pct": round(sum(1 for v in bm.values() if v > 0) / len(bm), 3) if bm else None,
            "weeks": len(bw), "weeks_green": sum(1 for v in bw.values() if v > 0),
            "weeks_green_pct": round(sum(1 for v in bw.values() if v > 0) / len(bw), 3) if bw else None,
            "longest_losing_months": best, "worst_month": (worst[0], round(worst[1], 2)) if worst else None}


def bootstrap_daily(d, seed=BOOT_SEED, draws=BOOT_DRAWS):
    """95% interval of the mean daily P/L, resampling sessions with replacement (iid), numpy default_rng(seed)."""
    d = np.asarray(d, float)
    if len(d) < 2:
        return None
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    step = 250
    for a in range(0, draws, step):
        m = min(step, draws - a)
        means[a:a + m] = d[rng.integers(0, len(d), size=(m, len(d)))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return round(float(lo), 4), round(float(hi), 4)


def random_direction(trades, seeds=RANDOM_SEEDS):
    """p = share of coin-flip-side draws (same entries and exits, base costs) whose total is at or above the rule's."""
    tr = ordered(trades)
    if not tr:
        return None, []
    sh = np.array([float(t["shares"]) for t in tr])
    mv = np.array([float(t["move"]) for t in tr])
    cost = 2 * HALF * sh
    actual = float(sum(float(t["pnl"]) for t in tr))
    tots = []
    for s in seeds:
        flips = np.random.default_rng(s).choice(np.array([-1.0, 1.0]), len(tr))
        tots.append(float((sh * flips * mv - cost).sum()))
    tots = np.array(tots)
    return round(float((tots >= actual - 1e-9).mean()), 4), tots


def years_table(trades):
    out = {}
    for name, a, b in YEARS:
        sub = [t for t in trades if a <= t["day"] <= b]
        out[name] = stats(sub)
    return out


def pass_bar(trades, sessions=None, seeds=RANDOM_SEEDS, boot_seed=BOOT_SEED, draws=BOOT_DRAWS):
    """Part A's 7-item bar. Returns {"checks": [(name, ok)], "pass": bool, and the numbers}."""
    sessions = sessions or all_sessions()
    tr = ordered(trades)
    s = stats(tr, len(sessions))
    d = daily(tr, sessions)
    yrs = {str(y): sum(float(t["pnl"]) for t in tr if t["day"][:4] == str(y) and t["day"] <= HIST_B) for y in range(2016, 2024)}
    up = sum(1 for v in yrs.values() if v > 0)
    dev = sum(float(t["pnl"]) for t in tr if DEV_A <= t["day"] <= DEV_B)
    ci = bootstrap_daily(d, boot_seed, draws)
    wb5 = float(d.sum() - np.sort(d)[::-1][:5].sum()) if len(d) else 0.0
    p, _ = random_direction(tr, seeds)
    st = steadiness(tr)
    checks = [(f"at least 300 trades over the 2016-2026 windows ({s['trades']})", s["trades"] >= 300),
              (f"expectancy per trade > 0 at 2x costs ({s.get('expectancy_2x')})", (s.get("expectancy_2x") or -1) > 0),
              (f"profitable in at least 6 of the 8 years 2016-2023 ({up} of 8) and in DEV 2024-08..2026-06 ({dev:.2f})",
               up >= 6 and dev > 0),
              (f"bootstrap 95% interval of the daily mean P/L above 0 ({ci})", ci is not None and ci[0] > 0),
              (f"positive without the best 5 days ({wb5:.2f})", wb5 > 0),
              (f"beats random direction, p < 0.05 (p = {p})", p is not None and p < 0.05),
              (f"at least 55% of months green ({st['months_green']}/{st['months']})",
               bool(st["months"]) and st["months_green"] / st["months"] >= 0.55)]
    return {"stats": s, "years_2016_2023": {k: round(v, 2) for k, v in yrs.items()}, "dev_total": round(dev, 2), "boot_ci": ci,
            "without_best5_days": round(wb5, 2), "random_p": p, "steadiness": st, "checks": checks,
            "pass": all(ok for _, ok in checks)}


def corr(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return None
    return round(float(np.corrcoef(a, b)[0, 1]), 3)
