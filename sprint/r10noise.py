"""sprint/r10noise.py - round 10's noise band settings grid and loss-autopsy fixes (SPRINT_PLAN Addendum 15.1, "the noise
band's own settings", and Addendum 15.2, "noise band loss autopsy fixes"; both pre-registered 2026-11-01 before any
round-10 code or run), plus Amendment 16's compounding view for anything that passes. Research only: it reads cached
stock bars and never trades. Every number is a BACKTEST on real Alpaca stock 1-minute bars (shares; no option model).

NB-VOL (round 8's A1 secondary, sprint/shares.py: noise_sh_vol) was already read on the exam's locked period L2
(2024-02-01..07-31). A tuned version can never use L2 or L1 (2026-07-01..10-30): the share loader (shares.load_series)
refuses any range that touches them and drops any bar dated inside them, every window this module evaluates is guarded
(periods.guard), and the compounding view refuses locked rows. A tuned version is judged on its holdouts and on forward
paper trades only.

THE RULE (A1 noise_sh, vol-sized, as sprint/shares.py; Zarattini, Aziz & Barbon 2024), with the grid's settings:
  sigma(t)  the mean over the LB prior sessions (at least 10 with a bar at t) of |close(t) / that session's open - 1|.
  bands     UB(t) = max(open, prior close) x (1 + VM x sigma(t)); LB(t) = min(open, prior close) x (1 - VM x sigma(t)).
  checks    the bars finishing 10:00 and every CI minutes after it, through 15:30, that lie before the exit bar.
  flat      close > UB -> long; close < LB -> short.
  long      close < LB -> reverse to short; else close < the trailing stop -> flat. Short mirrored.
  trailing  "band_vwap" (the paper's): long max(UB, VWAP), short min(LB, VWAP); "vwap": VWAP; "band": UB / LB.
  sizing    notional = 10,000 x min(4, 0.02 / sd), sd = the sample sd of the 14 prior daily close-to-close returns.
  costs     fill at the open of the bar after the decision bar (within 3 minutes) -/+ $0.01 a share; 2x = $0.02.
  exit      the close of the bar finishing 15:59 (12:59 on early-close days); shares may trade to the close.

ADDENDUM 15.1, THE GRID (3 x 3 x 3 x 3 x 2 = 162 cells, in the listed order):
  VM 1.0 / 1.25 / 1.5; LB 10 / 14 / 20 sessions; CI 15 / 30 / 60 minutes; trailing stop max(band, VWAP) / VWAP only /
  band only; universe U3 = SPY + QQQ + IWM, or U7 = U3 + DIA, XLK, XLF, SMH (U-ETF subset; their 1-minute bars if present,
  else the three). The cell VM 1.0 / LB 14 / CI 30 / max(band, VWAP) / U3 IS NB-VOL.
  Choice: on 2016-01-04..2019-12-31 only, the highest Sharpe of daily P/L among cells with at least 1,000 trades.
  Holdout 1 = 2020-01-01..2024-01-31 and holdout 2 = DEV 2024-08-01..2026-06-30, each with Part A's 7-item bar.
  Reported: the full grid, and the share of cells with a positive holdout Sharpe. Trials: 162.
ADDENDUM 15.2, THE FIXES (NB-VOL's settings otherwise unchanged, U3, vol-sized):
  N1 one trade per symbol per day (after the first exit, no re-entry); N2 no new entry after the check finishing 12:00;
  N12 both. Holdout 1 and holdout 2, each with Part A's 7-item bar, against the unfixed NB-VOL on the same windows. A fix
  holds only if it beats the unfixed version's daily Sharpe in both holdouts. Trials: 3.
AMENDMENT 16, COMPOUNDING VIEW (information, not trials): for every cell or fix that passes, sprint/compound.simulate on a
  $3,000 account, 2,000 bootstrap paths of its holdout sessions, fixed-fractional risk 1%, 2% and 5% a trade.

Part A's 7-item bar (sprint/shares.pass_bar), per holdout window:
  1 at least 300 trades; 2 expectancy per trade > 0 at 2x costs; 3 the year/DEV item (see the readings); 4 the bootstrap 95%
  interval of the daily mean P/L above 0 (every session of the window, 0 on days without a trade, 2,000 draws, seed 29);
  5 positive without the best 5 days; 6 beats random direction, p < 0.05 (seeds 31-230); 7 at least 55% of months green.
Daily Sharpe = mean / sd (population) x sqrt(252) of the daily P/L over every NYSE session of the window, 0 on days
without a trade, all symbols of the universe summed (as round 8's B2 "daily Sharpe").

BUILDER'S READING (the text is ambiguous here; the most literal reading is taken and stated):
  R1 Lookback: only "14" in "the mean over the 14 prior sessions (at least 10)" changes; the "at least 10" minimum is part
     of A1's rules and stays, so LB 10 needs all 10 prior sessions to have a bar at t, and LB 20 at least 10 of 20.
     The vol sizing's 14 daily returns are the sizing rule, not the noise lookback, and stay 14 in every cell.
  R2 Check interval: A1's first check (the bar finishing 10:00, index 29) and its last bound (15:30, index 359) stay; the
     step changes. CI 15: 10:00, 10:15, ..., 15:30 (23 checks); CI 30: A1's 12 checks; CI 60: 10:00, 11:00, ..., 15:00 (6).
  R3 Trailing stop: only the flat-exit level changes; the reversal (close through the opposite band) stays in every
     variant. "VWAP only": long exits on close < VWAP, short on close > VWAP; "band only": long close < UB, short close > LB.
     Where VWAP is missing every variant falls back to the band (as shares.a1_day does).
  R4 VM scales sigma inside both bands (UB and LB), so it moves the entry, the reversal and the band stop together.
  R5 Universe: the U7 cells use DIA, XLK, XLF and SMH only when all four have 1-minute bars (data/alpaca/stocks/<SYM>/)
     on at least one session of each window the grid reads (2016-2019, holdout 1, DEV); otherwise every U7 cell runs on
     the three (and equals its U3 twin). The report says which was used, and warns when a symbol in use has bars on fewer
     than 95% of a window's NYSE sessions.
  R6 Choice ties (none written): the higher Sharpe, then more discovery trades, then the earlier cell in the listed order
     (VM, LB, CI, trailing stop, universe). No cell with 1,000 discovery trades = no choice (and no holdout test).
  R7 Part A's item 3 per holdout: inside holdout 1 the years of 2016-2023 are 2020-2023, so "6 of the 8 years" scales to
     the same 75%: profitable in at least 3 of the 4 years 2020-2023 (Jan 2024 is not a year); inside holdout 2 it is
     "profitable in DEV 2024-08..2026-06" (the DEV total > 0). Items 1, 2, 4-7 are computed on the window's trades and
     sessions with their written numbers (300 trades, seeds 29 and 31-230, 2,000 draws, 55%).
  R8 A grid cell passes only when its 7-item bar passes in both holdouts.
  R9 A fix "holds" when it passes the 7-item bar in both holdouts AND beats the unfixed NB-VOL's daily Sharpe in both
     ("holds only if" makes the Sharpe a requirement on top of the test's bar). Both parts are reported apart.
  R10 N1 and N2 block new positions, so a reversal signal they block closes the open position and does not open the
     opposite one (exit reason "NOISE REVERSAL signal, exit only"). N1 counts positions opened that day; N2 allows an
     entry at the 12:00 check (index 149) itself and none after it. Positions already open keep A1's exits.
  R11 Compounding: each holdout window is simulated on its own (its sessions are the path length). The risk of a trade
     is the paper's own risk unit, the position's one-day one-sd move: notional x sd (= 2% of $10,000 = $200 unless the 4x
     cap binds; $200 when sd = 0), so 1R = the move the vol sizing targets.
Every other number (costs, fills, exit time, sizing, 300 trades, seeds) is shares.py's / Part A's, unchanged.
"""
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from . import book, compound, data, features, periods, shares
from . import report as R

HALF = shares.HALF
VMS = (1.0, 1.25, 1.5)
LOOKBACKS = (10, 14, 20)
INTERVALS = (15, 30, 60)
TRAILS = ("band_vwap", "vwap", "band")
TRAIL_TXT = {"band_vwap": "max(band, VWAP) (the paper's)", "vwap": "VWAP only", "band": "band only"}
STOP_TXT = {"band_vwap": "NOISE STOP: close through max/min(band, VWAP)", "vwap": "NOISE STOP: close through VWAP",
            "band": "NOISE STOP: close through the band"}
U3 = tuple(shares.SYMBOLS)
EXTRA = ("DIA", "XLK", "XLF", "SMH")
U7 = U3 + EXTRA
UNIVERSES = ("U3", "U7")
SYM_ORDER = tuple(sorted(U7))                      # integer rank == string order (shares.ordered sorts by the symbol)
CHECKS = {iv: tuple(range(29, 360, iv)) for iv in INTERVALS}
ALL_CHECKS = CHECKS[15]
assert CHECKS[30] == shares.CHECKS_A1 and set(CHECKS[60]) <= set(ALL_CHECKS) and len(ALL_CHECKS) == 23 and len(CHECKS[60]) == 6
N2_LAST_ENTRY = 149                                # the bar finishing 12:00
NO_CUTOFF = 999
MIN_DISC_TRADES = 1000
COVER_WARN = 0.95
DEV_A, DEV_B = shares.DEV_A, shares.DEV_B
DISC = (shares.HIST_A, "2019-12-31")
H1 = ("2020-01-01", shares.HIST_B)
H2 = (DEV_A, DEV_B)
WINDOWS = {"discovery": DISC, "holdout1": H1, "holdout2": H2}
HOLDOUTS = ("holdout1", "holdout2")
WINDOW_TXT = {"discovery": "2016-01-04..2019-12-31", "holdout1": "holdout 1 2020-01-01..2024-01-31",
              "holdout2": "holdout 2 DEV 2024-08-01..2026-06-30"}
for _a, _b in WINDOWS.values():
    assert not periods.overlaps(_a, _b), (_a, _b)
LABEL = "BACKTEST on real Alpaca stock 1-minute bars (shares, no option model)"
TRIALS = {"15.1 noise band grid (3 VM x 3 lookbacks x 3 check intervals x 3 trailing stops x 2 universes)": 162,
          "15.2 autopsy fixes (N1, N2, N12)": 3}
THIS_BUILD = 165
assert sum(TRIALS.values()) == THIS_BUILD
R10_TALLY = {"Amendment 15 (with stop none)": 7560, "15.1": 162, "15.2": 3, "15.3": 2, "15.4": 5, "15.5 (R1 3, R2 8, R3 7)": 18,
             "R4": 7, "C3, C3-ctl, C4": 3, "V1, V2, V2-s": 3, "V3 shares + options": 2, "V4 shares + options": 2}
ROUND10 = 7767
assert sum(R10_TALLY.values()) == ROUND10
STOP, REV, CLOSE, REVX = 0, 1, 2, 3
REVX_TXT = "NOISE REVERSAL signal, exit only (fix: no new entry)"


# ---------------------------------------------------------------- the settings
@dataclass(frozen=True)
class Cfg:
    vm: float = 1.0
    lookback: int = 14
    interval: int = 30
    trail: str = "band_vwap"
    one_trade: bool = False                      # N1
    last_entry: int = NO_CUTOFF                  # N2: N2_LAST_ENTRY

    @property
    def key(self):
        k = f"vm{self.vm:.2f}-lb{self.lookback}-i{self.interval}-{self.trail}"
        if self.one_trade:
            k += "-N1"
        if self.last_entry != NO_CUTOFF:
            k += f"-N2@{self.last_entry}"
        return k


BASE = Cfg()
FIXES = {"N1": Cfg(one_trade=True), "N2": Cfg(last_entry=N2_LAST_ENTRY), "N12": Cfg(one_trade=True, last_entry=N2_LAST_ENTRY)}
FIX_TXT = {"N1": "one trade per symbol per day", "N2": "no new entry after the 12:00 check", "N12": "N1 and N2 together"}
GRID_CFGS = tuple(Cfg(vm, lb, iv, tr) for vm in VMS for lb in LOOKBACKS for iv in INTERVALS for tr in TRAILS)
GRID = tuple((c, u) for c in GRID_CFGS for u in UNIVERSES)    # VM, lookback, interval, trail, universe: the listed order
assert len(GRID_CFGS) == 81 and len(GRID) == 162 and GRID_CFGS[0] == Cfg(1.0, 10, 15, "band_vwap") and BASE in GRID_CFGS


def cell_id(cfg, universe):
    return f"{cfg.key}-{universe}"


CELL_IDS = tuple(cell_id(c, u) for c, u in GRID)
BASE_ID = cell_id(BASE, "U3")
assert len(set(CELL_IDS)) == 162 and BASE_ID in CELL_IDS


# ---------------------------------------------------------------- the scalar reference (one symbol, one day)
def sigma(series, day, lookback=14):
    """sigma(t), t = 0..389, from the `lookback` sessions before `day` (NaN where fewer than 10 of them have a bar at t)."""
    pos, cs, cn = shares.a1_profile(series)
    k = pos.get(day)
    if k is None:
        return None
    a = max(0, k - lookback)
    s, c = cs[k] - cs[a], cn[k] - cn[a]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(c >= shares.SIGMA_MIN, s / np.maximum(c, 1), np.nan)


def bands(series, day, vm=1.0, lookback=14):
    """(UB, LB) over t = 0..389, or None (no prior close or no sigma)."""
    pos = features.day_pos(series)
    k = pos.get(day)
    if not k:
        return None
    o = float(series.daily["open"].iloc[k])
    pc = float(series.daily["close"].iloc[k - 1])
    sig = sigma(series, day, lookback)
    if sig is None or math.isnan(o):
        return None
    return max(o, pc) * (1 + vm * sig), min(o, pc) * (1 - vm * sig)


def vol_sd(series, day):
    """The sample sd of the 14 prior daily close-to-close returns (the vol sizing's sd), or None."""
    k = features.day_pos(series).get(day)
    if k is None or k < shares.VOL_DAYS + 1:
        return None
    c = series.daily["close"].to_numpy(float)[k - shares.VOL_DAYS - 1:k]
    return float(np.std(c[1:] / c[:-1] - 1, ddof=1))


def _stops(ub, lb, vw, trail):
    if trail == "band_vwap":
        return (max(ub, vw), min(lb, vw)) if not math.isnan(vw) else (ub, lb)
    if trail == "vwap":
        return (vw, vw) if not math.isnan(vw) else (ub, lb)
    return ub, lb


def cell_day(ctx, src, cfg, notional, variant="cell", sd=None):
    """One setting (and fix) on one (symbol, day): shares.a1_day with Addendum 15.1's settings and 15.2's fixes. The scalar
    reference the vectorized engine is tested against; with BASE it is shares.a1_day(..., notional=vol-sized)."""
    bk = shares.Book(ctx, variant, src)
    bd = bands(ctx.series, ctx.day, cfg.vm, cfg.lookback)
    if bd is None or notional is None:
        return bk.out
    UB, LB = bd
    xb = shares.exit_bar(ctx)
    pos, opened = 0, 0
    info = {"vol_sd": sd} if sd is not None else None
    for i in CHECKS[cfg.interval]:
        if i >= xb:
            break
        c, ub, lb = ctx.c[i], UB[i], LB[i]
        if math.isnan(c) or math.isnan(ub) or math.isnan(lb):
            continue
        stop_l, stop_s = _stops(ub, lb, ctx.vwap[i], cfg.trail)
        want = pos
        if pos == 0:
            want = 1 if c > ub else (-1 if c < lb else 0)
        elif pos == 1:
            if c < lb:
                want = -1
            elif c < stop_l:
                want = 0
        else:
            if c > ub:
                want = 1
            elif c > stop_s:
                want = 0
        blocked = False
        if want != pos and want != 0 and not ((not cfg.one_trade or opened == 0) and i <= cfg.last_entry):
            blocked, want = True, 0
        if want == pos:
            continue
        k = shares.fill_bar(ctx, i, xb)
        if k is None:
            continue
        if pos != 0:
            why = "NOISE REVERSAL" if want == -pos else (REVX_TXT if blocked else STOP_TXT[cfg.trail])
            bk.close(k, float(ctx.o[k]), why)
        pos = 0
        if want != 0:
            sh = shares._shares(notional, float(c))
            if sh > 0:
                bk.open(want, i, k, sh, notional, info)
                pos = want
                opened += 1
    bk.close_at_end()
    return bk.out


# ---------------------------------------------------------------- the vectorized engine (one symbol, one segment, all cfgs)
class Prep:
    """One symbol over one loaded segment (HIST with its warm-up, or DEV): what every setting needs, at the 15-minute check
    grid (the 30- and 60-minute grids are subsets of it). Trades are taken only on the segment's own sessions (HIST
    2016-01-04..2024-01-31, DEV 2024-08-01..2026-06-30), never inside L1/L2; warm-up sessions feed sigma and sizing only."""

    def __init__(self, series, src):
        a, b = periods.HIST if src == "HIST" else periods.DEV
        self.sym, self.src = series.sym, src
        self.days = list(series.days)
        n = self.n = len(self.days)
        self.iso = np.array([d.isoformat() for d in self.days], dtype="U10")
        ec = periods.early_closes()
        self.early = np.array([s in ec for s in self.iso], bool)
        self.xb = np.where(self.early, shares.EARLY_EXIT_BAR, shares.EXIT_BAR)
        self.trade = np.array([a <= d <= b and not periods.overlaps(d, d) for d in self.days], bool)
        J = np.array(ALL_CHECKS)
        nj = len(J)
        if n == 0:
            self.C = self.VW = self.FO = np.zeros((0, nj))
            self.FK = np.zeros((0, nj), np.int64)
            self.LK, self.LC, self.hi, self.lo, self.nv, self.sd = (np.zeros(0) for _ in range(6))
            self.has_prior = np.zeros(0, bool)
            self.sig = {L: np.zeros((0, nj)) for L in LOOKBACKS}
            return
        G = np.stack([series.rth[d] for d in self.days])
        O1, C1 = G[:, :, 0], G[:, :, 3]
        self.C = C1[:, J].copy()
        self.VW = np.stack([series.vwap[d][J] for d in self.days])
        FK = np.full((n, nj), -1, np.int64)
        FO = np.full((n, nj), np.nan)
        for jj, i in enumerate(J):                              # shares.fill_bar: the first bar i+1..min(i+3, exit bar)
            for k in range(i + 1, i + shares.ENTRY_WAIT + 1):
                if k >= data.N:
                    break
                ok = (FK[:, jj] < 0) & (k <= self.xb) & ~np.isnan(C1[:, k]) & ~np.isnan(O1[:, k])
                FK[ok, jj] = k
                FO[ok, jj] = O1[ok, k]
        self.FK, self.FO = FK, FO
        t = np.arange(data.N)
        have = ~np.isnan(C1) & (t[None, :] <= self.xb[:, None])     # the last close at or before the exit bar
        anyb = have.any(axis=1)
        self.LK = np.where(anyb, data.N - 1 - np.argmax(have[:, ::-1], axis=1), -1)
        self.LC = np.where(anyb, C1[np.arange(n), np.maximum(self.LK, 0)], np.nan)
        dopen = series.daily["open"].to_numpy(float)
        dclose = series.daily["close"].to_numpy(float)
        pc = np.concatenate([[np.nan], dclose[:-1]])
        self.hi, self.lo = np.maximum(dopen, pc), np.minimum(dopen, pc)
        self.has_prior = np.arange(n) >= 1
        _pos, cs, cn = shares.a1_profile(series)
        kk = np.arange(n)
        self.sig = {}
        for L in LOOKBACKS:
            a0 = np.maximum(0, kk - L)
            s, c = cs[kk][:, J] - cs[a0][:, J], cn[kk][:, J] - cn[a0][:, J]
            with np.errstate(invalid="ignore", divide="ignore"):
                self.sig[L] = np.where(c >= shares.SIGMA_MIN, s / np.maximum(c, 1), np.nan)
        nv, sd = np.full(n, np.nan), np.full(n, np.nan)
        for k, d in enumerate(self.days):
            v = shares.a1_vol_notional(series, d)
            if v is not None:
                nv[k] = v
                sd[k] = vol_sd(series, d)
        self.nv, self.sd = nv, sd

    def coverage(self):
        """{window: sessions with bars} for the windows the grid reads."""
        return {w: int(((self.iso >= a) & (self.iso <= b) & self.trade).sum()) for w, (a, b) in WINDOWS.items()}


COLS = ("cfg", "sign", "dec", "k_in", "ref_in", "k_out", "ref_out", "sh", "why", "day", "sym", "src", "notional", "sd", "early",
        "move", "pnl", "pnl_2x", "bps", "dayint", "symrank")


def _empty():
    return {"cfg": np.zeros(0, np.int64), "sign": np.zeros(0, np.int64), "dec": np.zeros(0, np.int64), "k_in": np.zeros(0, np.int64),
            "ref_in": np.zeros(0), "k_out": np.zeros(0, np.int64), "ref_out": np.zeros(0), "sh": np.zeros(0, np.int64),
            "why": np.zeros(0, np.int64), "day": np.zeros(0, dtype="U10"), "sym": np.zeros(0, dtype="U4"), "src": np.zeros(0, dtype="U4"),
            "notional": np.zeros(0), "sd": np.zeros(0), "early": np.zeros(0, bool), "move": np.zeros(0), "pnl": np.zeros(0),
            "pnl_2x": np.zeros(0), "bps": np.zeros(0), "dayint": np.zeros(0, np.int64), "symrank": np.zeros(0, np.int64)}


def _round(a, n):
    return np.array([round(float(x), n) for x in a], float) if len(a) else np.zeros(0)


def run_engine(prep, cfgs):
    """Every cfg on every session of one Prep at once (vectorized over cfgs x days, stepping through the checks). Returns
    the trades as column arrays (COLS); `cfg` indexes `cfgs`. The same trades, in the same numbers, as cell_day."""
    cfgs = list(cfgs)
    m, n = len(cfgs), prep.n
    if m == 0 or n == 0:
        return _empty()
    vm = np.array([c.vm for c in cfgs], float)[:, None]
    li = np.array([LOOKBACKS.index(c.lookback) for c in cfgs])
    trail = np.array([TRAILS.index(c.trail) for c in cfgs])[:, None]
    one = np.array([c.one_trade for c in cfgs], bool)[:, None]
    last = np.array([c.last_entry for c in cfgs])[:, None]
    act_j = np.array([[i in set(CHECKS[c.interval]) for i in ALL_CHECKS] for c in cfgs], bool)
    SIG = np.stack([prep.sig[L] for L in LOOKBACKS])
    day_ok = prep.trade & prep.has_prior & ~np.isnan(prep.nv)
    pos = np.zeros((m, n), np.int64)
    opened = np.zeros((m, n), np.int64)
    e_sign, e_dec, e_k, e_sh = (np.zeros((m, n), np.int64) for _ in range(4))
    e_ref = np.zeros((m, n))
    with np.errstate(invalid="ignore", divide="ignore"):
        shv = np.where(prep.C > 0, np.floor(prep.nv[:, None] / prep.C), 0.0)
    shv = np.nan_to_num(shv, nan=0.0)
    rec = []
    for jj, i in enumerate(ALL_CHECKS):
        if not act_j[:, jj].any():
            continue
        c = prep.C[:, jj]
        sg = SIG[li, :, jj]
        ub = prep.hi[None, :] * (1 + vm * sg)
        lb = prep.lo[None, :] * (1 - vm * sg)
        valid = act_j[:, jj][:, None] & (day_ok & (i < prep.xb) & ~np.isnan(c))[None, :] & ~np.isnan(ub) & ~np.isnan(lb)
        if not valid.any():
            continue
        vw = prep.VW[:, jj][None, :]
        vnan = np.isnan(vw)
        with np.errstate(invalid="ignore"):
            stop_l = np.where(trail == 0, np.where(vnan, ub, np.maximum(ub, vw)), np.where(trail == 1, np.where(vnan, ub, vw), ub))
            stop_s = np.where(trail == 0, np.where(vnan, lb, np.minimum(lb, vw)), np.where(trail == 1, np.where(vnan, lb, vw), lb))
            cc = c[None, :]
            up, dn = cc > ub, cc < lb
            want = np.where(pos == 0, np.where(up, 1, np.where(dn, -1, 0)),
                            np.where(pos == 1, np.where(dn, -1, np.where(cc < stop_l, 0, 1)),
                                     np.where(up, 1, np.where(cc > stop_s, 0, -1))))
        allow = ~(one & (opened > 0)) & (i <= last)
        blocked = (want != pos) & (want != 0) & ~allow
        want = np.where(blocked, 0, want)
        has = (prep.FK[:, jj] >= 0)[None, :]
        act = valid & (want != pos) & has
        if not act.any():
            continue
        cl = act & (pos != 0)
        if cl.any():
            ci, di = np.nonzero(cl)
            p = pos[ci, di]
            why = np.where(want[ci, di] == -p, REV, np.where(blocked[ci, di], REVX, STOP))
            rec.append((ci, di, e_sign[ci, di], e_dec[ci, di], e_k[ci, di], e_ref[ci, di], e_sh[ci, di], prep.FK[di, jj],
                        prep.FO[di, jj], why))
        pos[act] = 0
        op = act & (want != 0) & (shv[:, jj] > 0)[None, :]
        if op.any():
            ci, di = np.nonzero(op)
            e_sign[ci, di] = want[ci, di]
            e_dec[ci, di] = i
            e_k[ci, di] = prep.FK[di, jj]
            e_ref[ci, di] = prep.FO[di, jj]
            e_sh[ci, di] = shv[di, jj].astype(np.int64)
            pos[ci, di] = want[ci, di]
            opened[ci, di] += 1
    ci, di = np.nonzero(pos != 0)
    if len(ci):
        rec.append((ci, di, e_sign[ci, di], e_dec[ci, di], e_k[ci, di], e_ref[ci, di], e_sh[ci, di], prep.LK[di], prep.LC[di],
                    np.full(len(ci), CLOSE)))
    if not rec:
        return _empty()
    cat = [np.concatenate([r[k] for r in rec]) for k in range(10)]
    ci, di = cat[0], cat[1]
    out = {"cfg": ci.astype(np.int64), "sign": cat[2].astype(np.int64), "dec": cat[3].astype(np.int64), "k_in": cat[4].astype(np.int64),
           "ref_in": cat[5].astype(float), "sh": cat[6].astype(np.int64), "k_out": cat[7].astype(np.int64), "ref_out": cat[8].astype(float),
           "why": cat[9].astype(np.int64)}
    out["day"] = prep.iso[di]
    out["sym"] = np.full(len(ci), prep.sym, dtype="U4")
    out["src"] = np.full(len(ci), prep.src, dtype="U4")
    out["notional"] = prep.nv[di]
    out["sd"] = prep.sd[di]
    out["early"] = prep.early[di]
    return finish(out)


def finish(t):
    """P/L columns (shares.Book's arithmetic and rounding) and the sort keys."""
    sh, sg = t["sh"].astype(float), t["sign"].astype(float)
    move = t["ref_out"] - t["ref_in"]
    pnl = sh * (sg * move - 2 * HALF)
    with np.errstate(invalid="ignore", divide="ignore"):
        bps = pnl / (sh * t["ref_in"]) * 1e4
    t["move"] = move
    t["pnl"] = _round(pnl, 4)
    t["pnl_2x"] = _round(sh * (sg * move - 4 * HALF), 4)
    t["bps"] = _round(bps, 4)
    t["dayint"] = np.array([int(d.replace("-", "")) for d in t["day"]], np.int64) if len(t["day"]) else np.zeros(0, np.int64)
    t["symrank"] = np.array([SYM_ORDER.index(s) if s in SYM_ORDER else len(SYM_ORDER) for s in t["sym"]], np.int64) \
        if len(t["sym"]) else np.zeros(0, np.int64)
    return t


def take(t, mask):
    return {k: v[mask] for k, v in t.items()}


def concat(parts):
    parts = [p for p in parts if p is not None and len(p["pnl"])]
    if not parts:
        return _empty()
    return {k: np.concatenate([p[k] for p in parts]) for k in COLS}


def ordered(t):
    """shares.ordered's order: day, entry bar, symbol, exit bar."""
    if not len(t["pnl"]):
        return t
    o = np.lexsort((t["k_out"], t["symrank"], t["k_in"], t["dayint"]))
    return {k: v[o] for k, v in t.items()}


def by_cfg(t, n_cfg):
    """[trades of cfg 0, cfg 1, ...]."""
    if not len(t["cfg"]):
        return [_empty() for _ in range(n_cfg)]
    o = np.argsort(t["cfg"], kind="stable")
    s = {k: v[o] for k, v in t.items()}
    cuts = np.searchsorted(s["cfg"], np.arange(n_cfg + 1))
    return [{k: v[cuts[j]:cuts[j + 1]] for k, v in s.items()} for j in range(n_cfg)]


def window(t, a, b):
    m = (t["day"] >= a) & (t["day"] <= b)
    return take(t, m)


def why_text(code, trail, early):
    if code == CLOSE:
        return f"CLOSE {'12:59' if early else '15:59'} bar"
    if code == REV:
        return "NOISE REVERSAL"
    if code == REVX:
        return REVX_TXT
    return STOP_TXT[trail]


def to_rows(t, variant, trail):
    """The trades as shares.Book dicts (the same keys and rounding as round 8's share trade file), plus i_vol_sd."""
    out = []
    for j in range(len(t["pnl"])):
        sg, sh = int(t["sign"][j]), int(t["sh"][j])
        ref, xref = float(t["ref_in"][j]), float(t["ref_out"][j])
        k, x = int(t["k_in"][j]), int(t["k_out"][j])
        move = xref - ref
        pnl = sh * (sg * move - 2 * HALF)
        sd = float(t["sd"][j])
        out.append({"variant": variant, "symbol": str(t["sym"][j]), "day": str(t["day"][j]), "_src": str(t["src"][j]),
                    "side": "L" if sg > 0 else "S", "sign": sg, "decision_idx": int(t["dec"][j]), "entry_idx": k, "exit_idx": x,
                    "entry_time": shares._t(k), "exit_time": shares._t(x), "shares": sh, "entry_ref": round(ref, 4),
                    "exit_ref": round(xref, 4), "entry": round(ref + sg * HALF, 4), "exit": round(xref - sg * HALF, 4),
                    "move": round(move, 6), "pnl": round(pnl, 4), "pnl_2x": round(sh * (sg * move - 4 * HALF), 4),
                    "bps": round(pnl / (sh * ref) * 1e4, 4) if sh and ref else None, "notional": round(float(t["notional"][j]), 2),
                    "exit_reason": why_text(int(t["why"][j]), trail, bool(t["early"][j])),
                    "i_vol_sd": None if math.isnan(sd) else sd})
    return out


# ---------------------------------------------------------------- the universe
def universe_choice(coverage):
    """coverage: {symbol: {window: sessions with bars}} (missing symbol = none). Returns ("U7" | "U3", missing pairs, warnings).
    U7 is used only when every extra symbol has bars in each window the grid reads (Builder's reading R5)."""
    missing = [(s, w) for s in EXTRA for w in WINDOWS if not (coverage.get(s) or {}).get(w)]
    used = "U7" if not missing else "U3"
    warn = []
    syms = U7 if used == "U7" else U3
    for s in syms:
        for w, (a, b) in WINDOWS.items():
            n_ses = len(book.sessions_between(a, b))
            got = (coverage.get(s) or {}).get(w, 0)
            if got < COVER_WARN * n_ses:
                warn.append(f"{s} has 1-minute bars on {got} of {n_ses} NYSE sessions of {WINDOW_TXT[w]} (under {COVER_WARN:.0%})")
    return used, missing, warn


# ---------------------------------------------------------------- metrics on arrays
def daily_sharpe(d):
    """mean / population sd x sqrt(252) (round 8's B2 daily Sharpe); None when undefined."""
    d = np.asarray(d, float)
    return round(float(d.mean() / d.std() * math.sqrt(252)), 3) if len(d) > 1 and d.std() > 0 else None


def daily_a(t, sessions):
    ses = np.array(sessions, dtype="U10")
    v = np.zeros(len(ses))
    if not len(t["pnl"]) or not len(ses):
        return v
    i = np.searchsorted(ses, t["day"])
    ok = (i < len(ses)) & (ses[np.minimum(i, len(ses) - 1)] == t["day"])
    np.add.at(v, i[ok], t["pnl"][ok])
    return v


def _pf(p):
    lo, w = -p[p < 0].sum(), p[p > 0].sum()
    if lo > 0:
        return round(float(w / lo), 3)
    return math.inf if w > 0 else None


def astats(t, key):
    """A window's numbers from the arrays (trades in shares.ordered's order)."""
    a, b = WINDOWS[key]
    periods.guard(a, b)
    w = ordered(window(t, a, b))
    sessions = book.sessions_between(a, b)
    p, p2 = w["pnl"], w["pnl_2x"]
    out = {"trades": int(len(p)), "per_session": round(len(p) / len(sessions), 3) if sessions else None,
           "sharpe": daily_sharpe(daily_a(w, sessions))}
    if not len(p):
        return out
    eq = np.cumsum(p)
    dd = float((eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min())
    mk, mi = np.unique(np.array([d[:7] for d in w["day"]]), return_inverse=True)
    mnet = np.bincount(mi, weights=p, minlength=len(mk))
    out.update({"win_rate": round(float((p > 0).mean()), 3), "expectancy": round(float(p.mean()), 2),
                "expectancy_2x": round(float(p2.mean()), 2), "pf": _pf(p), "pf_2x": _pf(p2), "total": round(float(p.sum()), 2),
                "max_dd": round(min(dd, 0.0), 2), "months_green": int((mnet > 0).sum()), "months": int(len(mk))})
    return out


# ---------------------------------------------------------------- Part A's 7-item bar on one holdout window
def years_in(a, b):
    return [y for y in range(2016, 2024) if a <= f"{y}-01-01" and f"{y}-12-31" <= b]


def window_bar(rows, key, seeds=shares.RANDOM_SEEDS, boot_seed=shares.BOOT_SEED, draws=shares.BOOT_DRAWS):
    """Part A's 7-item bar on one window ("holdout1", "holdout2" or an (a, b) pair) with Builder's reading R7 for item 3.
    Refuses a window touching L1/L2."""
    a, b = WINDOWS[key] if isinstance(key, str) else key
    periods.guard(a, b)
    sessions = book.sessions_between(a, b)
    tr = shares.ordered([r for r in rows if a <= r["day"] <= b])
    s = shares.stats(tr, len(sessions))
    d = shares.daily(tr, sessions)
    yl = years_in(a, b)
    yrs = {str(y): round(sum(float(t["pnl"]) for t in tr if t["day"][:4] == str(y)), 2) for y in yl}
    up = sum(1 for v in yrs.values() if v > 0)
    total = round(float(sum(float(t["pnl"]) for t in tr)), 2)
    in_dev = a >= DEV_A
    parts, ok3 = [], True
    if yl:
        need = math.ceil(6 / 8 * len(yl))
        ok3 = ok3 and up >= need
        parts.append(f"profitable in at least {need} of the {len(yl)} years {yl[0]}-{yl[-1]} ({up} of {len(yl)})")
    if in_dev:
        ok3 = ok3 and total > 0
        parts.append(f"profitable in DEV 2024-08..2026-06 ({total:.2f})")
    if not parts:
        parts.append(f"profitable over the window ({total:.2f})")
        ok3 = total > 0
    ci = shares.bootstrap_daily(d, boot_seed, draws)
    wb5 = float(d.sum() - np.sort(d)[::-1][:5].sum()) if len(d) else 0.0
    p, _ = shares.random_direction(tr, seeds)
    st = shares.steadiness(tr)
    checks = [(f"at least 300 trades ({s['trades']})", s["trades"] >= 300),
              (f"expectancy per trade > 0 at 2x costs ({s.get('expectancy_2x')})", (s.get("expectancy_2x") or -1) > 0),
              ("; ".join(parts), ok3),
              (f"bootstrap 95% interval of the daily mean P/L above 0 ({ci})", ci is not None and ci[0] > 0),
              (f"positive without the best 5 days ({wb5:.2f})", wb5 > 0),
              (f"beats random direction, p < 0.05 (p = {p})", p is not None and p < 0.05),
              (f"at least 55% of months green ({st['months_green']}/{st['months']})",
               bool(st["months"]) and st["months_green"] / st["months"] >= 0.55)]
    return {"window": f"{a}..{b}", "sessions": len(sessions), "stats": s, "sharpe": daily_sharpe(d), "years": yrs, "total": total,
            "boot_ci": ci, "without_best5_days": round(wb5, 2), "random_p": p, "steadiness": st, "checks": checks,
            "pass": all(ok for _, ok in checks)}


# ---------------------------------------------------------------- 15.1: the grid, the choice, the holdouts
def grid_table(cells, used):
    """cells: {cell id: arrays}. One row per cell in the listed order with its three windows' numbers."""
    rows = []
    for n, ((c, u), cid) in enumerate(zip(GRID, CELL_IDS)):
        t = cells.get(cid) or _empty()
        rows.append({"cell": cid, "order": n, "vm": c.vm, "lookback": c.lookback, "interval": c.interval, "trail": c.trail,
                     "universe": u, "universe_used": used if u == "U7" else "U3",
                     **{w: astats(t, w) for w in WINDOWS}})
    return rows


def choose(rows, min_trades=None):
    """The highest discovery Sharpe among cells with at least `min_trades` (default MIN_DISC_TRADES = 1,000) discovery
    trades (ties: more trades, then the listed order). Reads only the rows' discovery numbers. Returns (cell id or None, why)."""
    min_trades = MIN_DISC_TRADES if min_trades is None else min_trades
    elig = [r for r in rows if r["discovery"]["trades"] >= min_trades and r["discovery"]["sharpe"] is not None]
    if not elig:
        return None, f"no cell has {min_trades:,} discovery trades with a defined Sharpe"
    best = max(elig, key=lambda r: (r["discovery"]["sharpe"], r["discovery"]["trades"], -r["order"]))
    return best["cell"], f"highest 2016-2019 daily Sharpe ({best['discovery']['sharpe']}) of {len(elig)} cells with {min_trades:,}+ trades"


def share_positive(rows):
    n = len(rows)
    out = {}
    for w in HOLDOUTS:
        k = sum(1 for r in rows if (r[w]["sharpe"] or 0) > 0)
        out[w] = {"cells": k, "of": n, "share": round(k / n, 3) if n else None}
    k = sum(1 for r in rows if all((r[w]["sharpe"] or 0) > 0 for w in HOLDOUTS))
    out["both"] = {"cells": k, "of": n, "share": round(k / n, 3) if n else None}
    return out


def by_setting(rows):
    """Per setting value: the share of its cells with a positive Sharpe in each window and the mean Sharpe (information)."""
    out = {}
    for dim, vals in (("vm", VMS), ("lookback", LOOKBACKS), ("interval", INTERVALS), ("trail", TRAILS), ("universe", UNIVERSES)):
        out[dim] = {}
        for v in vals:
            rs = [r for r in rows if r[dim] == v]
            if not rs:
                continue
            o = {}
            for w in WINDOWS:
                sh = [r[w]["sharpe"] for r in rs if r[w]["sharpe"] is not None]
                o[w] = {"positive": round(sum(1 for x in sh if x > 0) / len(rs), 3), "mean_sharpe": round(float(np.mean(sh)), 3) if sh else None}
            out[dim][str(v)] = o
    return out


def compounding(rows, key):
    """Amendment 16's view of one passing rule on one holdout window (risk per trade: Builder's reading R11)."""
    a, b = WINDOWS[key]
    periods.guard(a, b)
    sel = []
    for r in rows:
        if a <= r["day"] <= b:
            sd = r.get("i_vol_sd")
            risk = float(r["notional"]) * float(sd) if sd not in (None, "") and float(sd) > 0 else shares.VOL_TARGET * shares.NOTIONAL
            sel.append({"day": r["day"], "pnl": float(r["pnl"]), "risk": risk})
    return compound.simulate(sel, book.sessions_between(a, b),
                             label=f"{compound.LABEL}; {WINDOW_TXT[key]}; risk a trade = notional x the 14-day sd (R11)")


def evaluate_grid(cells, used, min_trades=None):
    min_trades = MIN_DISC_TRADES if min_trades is None else min_trades
    rows = grid_table(cells, used)
    chosen, why = choose(rows, min_trades)
    res = {"rows": rows, "chosen": chosen, "choice_why": why, "share_positive": share_positive(rows), "by_setting": by_setting(rows),
           "universe_used": used, "min_disc_trades": min_trades}
    if chosen:
        c, _u = GRID[CELL_IDS.index(chosen)]
        tr = to_rows(cells[chosen], chosen, c.trail)
        hb = {w: window_bar(tr, w) for w in HOLDOUTS}
        res["holdouts"] = hb
        res["pass"] = all(hb[w]["pass"] for w in HOLDOUTS)
        res["compounding"] = {w: compounding(tr, w) for w in HOLDOUTS} if res["pass"] else None
        res["_rows"] = tr
    else:
        res["holdouts"], res["pass"], res["compounding"] = None, False, None
    return res


# ---------------------------------------------------------------- 15.2: the fixes
def evaluate_fixes(rows_by):
    """rows_by: {"NB-VOL": rows, "N1": rows, "N2": rows, "N12": rows} (U3). Each holdout's 7-item bar and daily Sharpe; a fix
    holds when it passes the bar in both holdouts and beats NB-VOL's daily Sharpe in both (Builder's reading R9)."""
    base = {w: window_bar(rows_by.get("NB-VOL", []), w) for w in HOLDOUTS}
    out = {"NB-VOL": {"windows": base, "pass": all(base[w]["pass"] for w in HOLDOUTS)}, "fixes": {}}
    for fx in FIXES:
        rs = rows_by.get(fx, [])
        wb = {w: window_bar(rs, w) for w in HOLDOUTS}
        beats = {w: (wb[w]["sharpe"] is not None and base[w]["sharpe"] is not None and wb[w]["sharpe"] > base[w]["sharpe"])
                 for w in HOLDOUTS}
        bar_ok = all(wb[w]["pass"] for w in HOLDOUTS)
        holds = bar_ok and all(beats.values())
        out["fixes"][fx] = {"what": FIX_TXT[fx], "windows": wb, "beats_sharpe": beats, "bar_both": bar_ok, "holds": holds,
                            "compounding": {w: compounding(rs, w) for w in HOLDOUTS} if holds else None}
    return out


# ---------------------------------------------------------------- trials and the deflated Sharpe
def trials(n_prior):
    """The trial counts written with the run (round 9's way): this build's 165, round 10's 7,767 (Amendment 16's tally)
    and the run logs' rows; the deflated Sharpe uses N = the run logs' rows + 7,767."""
    return {"parts": dict(TRIALS), "this_build": THIS_BUILD, "round10": ROUND10, "round10_tally": dict(R10_TALLY),
            "prior_in_run_logs": int(n_prior), "total_for_dsr": int(n_prior) + ROUND10,
            "note": "15.1 counts its 162 cells even when U7 falls back to the three (the cells were pre-registered); "
                    "the compounding view is information, not trials."}


def dsr_table(variants, n_prior):
    """{name: deflated Sharpe} on DEV daily P/L (every DEV session, 0 on days without a trade), N = run logs + 7,767, the
    trial-Sharpe variance over the distinct DEV series given (a U7 cell that fell back to the three is its U3 twin's
    series and counted once)."""
    days = book.sessions_between(DEV_A, DEV_B)
    daily = {k: [float(x) for x in daily_a(t, days)] for k, t in variants.items()}
    distinct, seen = {}, set()
    for k, d in daily.items():
        sig = tuple(d)
        if sig not in seen:
            seen.add(sig)
            distinct[k] = d
    srs = [R.sharpe(d) for d in distinct.values()]
    srs = [x for x in srs if x is not None]
    sr_var = statistics.pvariance(srs) if len(srs) > 1 else 0.0
    n = int(n_prior) + ROUND10
    tab = {k: (R.deflated_sharpe(d, n, sr_var) if len(variants[k]["pnl"]) else None) for k, d in daily.items()}
    return tab, round(sr_var, 6), n, len(distinct)


# ---------------------------------------------------------------- the self-check on real bars (scalar vs vectorized)
NORM_DROP = ("variant",)


def _norm(rows):
    return [{k: v for k, v in r.items() if k not in NORM_DROP and not k.startswith("i_")} for r in rows]


def self_check(series, prep, trades, cfgs, sample=None, every=25, base=True):
    """Compare the vectorized trades of one Prep with the scalar code on the same bars: BASE (index of BASE in cfgs) with
    shares.a1_day (round 8's noise_sh_vol) on every trade session, and the cfg indexes in `sample` with cell_day on every
    `every`-th trade session. Returns counts and the first mismatch."""
    per = by_cfg(trades, len(cfgs))
    idx_by = []
    for t in per:
        d = defaultdict(list)
        for j, day in enumerate(t["day"]):
            d[str(day)].append(j)
        idx_by.append(d)
    days = [d for k, d in enumerate(prep.days) if prep.trade[k]]
    out = {"base_days": 0, "base_mismatch": 0, "sample_days": 0, "sample_mismatch": 0, "first": None}

    def got(ci, day):
        t = per[ci]
        j = idx_by[ci].get(day.isoformat(), [])
        sub = {k: v[j] for k, v in t.items()}
        return shares.ordered(to_rows(ordered(sub), "x", cfgs[ci].trail))

    if base and BASE in cfgs:
        bi = cfgs.index(BASE)
        for d in days:
            ctx = data.DayContext(series, d, {}, None)
            want = shares.ordered(shares.a1_day(ctx, prep.src, "noise_sh_vol", notional=shares.a1_vol_notional(series, d)))
            out["base_days"] += 1
            if _norm(want) != _norm(got(bi, d)):
                out["base_mismatch"] += 1
                out["first"] = out["first"] or f"{prep.sym} {d} base"
    for ci in (sample or []):
        for d in days[::every]:
            ctx = data.DayContext(series, d, {}, None)
            want = shares.ordered(cell_day(ctx, prep.src, cfgs[ci], shares.a1_vol_notional(series, d)))
            out["sample_days"] += 1
            if _norm(want) != _norm(got(ci, d)):
                out["sample_mismatch"] += 1
                out["first"] = out["first"] or f"{prep.sym} {d} {cfgs[ci].key}"
    return out


# ---------------------------------------------------------------- the report
def _f(x, n=2):
    return R.fmt(x, n)


def _row(cells):
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _head(cols):
    return ["", _row(cols), _row(["---"] * len(cols))]


def _yn(ok):
    return "PASS" if ok else "fail"


def _first_fail(checks):
    for n, ok in checks:
        if not ok:
            return n
    return None


def _checks(L, checks, pre=""):
    for n, ok in checks:
        L.append(f"  - {'yes' if ok else 'NO'}: {pre}{n}")


def cell_txt(cid):
    if cid is None:
        return "none"
    c, u = GRID[CELL_IDS.index(cid)]
    return f"VM {c.vm:g}, lookback {c.lookback}, every {c.interval} min, stop {TRAIL_TXT[c.trail]}, {u}"


def _bar_line(name, wb):
    s = wb["stats"]
    st = wb["steadiness"]
    return _row([name, wb["window"], s.get("trades", 0), _f((s.get("win_rate") or 0) * 100, 1) if s.get("trades") else "-",
                 _f(s.get("expectancy")), _f(s.get("expectancy_2x")), _f(s.get("pf")), _f(s.get("total")), _f(wb["sharpe"], 3),
                 f"{st['months_green']}/{st['months']}", wb["random_p"], _yn(wb["pass"])])


BAR_COLS = ("variant", "window", "trades", "win %", "exp $", "exp 2x $", "PF", "total $", "daily Sharpe", "months green", "random p",
            "7-item bar")


def render(res, meta):
    L = [f"# Sprint round 10: the noise band's own settings and its loss-autopsy fixes, {meta['today']}", "",
         "SPRINT_PLAN Addendum 15.1 (the 162-cell settings grid) and Addendum 15.2 (fixes N1, N2, N12), pre-registered "
         "2026-11-01 before any round-10 code or run, with Amendment 16's compounding view. **Every number is a BACKTEST on "
         "real Alpaca stock 1-minute bars (shares, no option model).** NB-VOL was already read on the exam's locked period L2, "
         "so no tuned version touches L2 (2024-02-01..07-31) or L1 (2026-07-01..10-30): they were never read, and a tuned "
         "version is judged on its holdouts and on forward paper trades only.", "",
         f"Inputs: {meta.get('files_note', '')}", ""]
    if meta.get("warnings"):
        L += ["**Warnings:**"] + [f"- {w}" for w in meta["warnings"]] + [""]
    L += ["## Summary", ""] + [f"- {s}" for s in summary_lines(res)] + [""]
    u = res.get("universe") or {}
    L += ["## Universe", "",
          f"**Used for the U7 cells: {u.get('used', '-')}.** "
          + ("DIA, XLK, XLF and SMH have 1-minute bars in every window, so the U7 cells trade 7 symbols." if u.get("used") == "U7" else
             "DIA, XLK, XLF and SMH 1-minute bars are not all present (missing: " + _missing_txt(u.get("missing", []))
             + "), so, as written, every U7 cell runs on SPY + QQQ + IWM and equals its U3 twin. To test U7 later: "
               "`python3 tools/sprint_pull.py --period HIST --symbols DIA,XLK,XLF,SMH` and "
               "`python3 tools/sprint_pull.py --symbols DIA,XLK,XLF,SMH --from 2024-08-01 --to 2026-06-30 --stock-bars-only`."), ""]
    L += _head(("symbol",) + tuple(WINDOW_TXT[w] for w in WINDOWS))
    for s, cv in (u.get("coverage") or {}).items():
        L.append(_row([s] + [cv.get(w, 0) for w in WINDOWS]))
    L.append("")
    L += ["## Builder's readings (stated before any run)", ""] + [f"- {x}" for x in BUILDER_READINGS] + [""]
    _grid_md(L, res.get("grid"))
    _fixes_md(L, res.get("fixes"))
    sc = res.get("self_check")
    if sc:
        L += ["## Engine self-check on the real bars", "",
              f"The vectorized grid engine against the scalar code on the same bars: NB-VOL's cell against round 8's "
              f"shares.a1_day (noise_sh_vol) on {sc['base_days']} symbol-sessions, {sc['base_mismatch']} mismatches; "
              f"{sc['n_sample_cfgs']} sample settings against cell_day on {sc['sample_days']} symbol-sessions, "
              f"{sc['sample_mismatch']} mismatches" + (f" (first: {sc['first']})" if sc.get("first") else "") + ".", ""]
    t = res["trials"]
    L += ["## Trials and the deflated Sharpe (information)", "",
          f"Trials: this build {t['this_build']} ({', '.join(f'{k}: {v}' for k, v in t['parts'].items())}); round 10 = {t['round10']} "
          f"(Amendment 16's tally); the run logs hold {t['prior_in_run_logs']}; the deflated Sharpe uses N = {t['total_for_dsr']} "
          f"(sr variance {res.get('sr_var')} over {res.get('dsr_distinct')} distinct DEV series). {t['note']}"]
    dsr = res.get("dsr") or {}
    ch = (res.get("grid") or {}).get("chosen")
    names = ([(f"chosen {ch}", ch)] if ch else []) + [("NB-VOL (unfixed)", BASE_ID)] + [(fx, fx) for fx in FIXES]
    L += _head(("variant", f"DSR on DEV (N = {t['total_for_dsr']})"))
    for label, key in names:
        if key in dsr:
            L.append(_row([label, _f(dsr.get(key), 4)]))
    L += ["", "No rule, cut, threshold or seed changes after these results; a change is a new amendment, labeled in-sample. A "
          "pass is still research: it reaches paper trading only through a new versioned ledger after Nick's yes, and "
          "promotion needs CLAUDE.md step 5 (out-of-sample and 40 forward paper trades). Not financial advice."]
    return "\n".join(L) + "\n"


def _missing_txt(missing):
    by = defaultdict(list)
    for s, w in missing:
        by[s].append(w)
    return "; ".join(f"{s} in {'every window' if len(ws) == len(WINDOWS) else ', '.join(WINDOW_TXT[w] for w in ws)}"
                     for s, ws in by.items())


def _grid_md(L, G):
    L += ["## Addendum 15.1: the noise band's own settings (162 cells)", ""]
    if not G:
        L += ["NOT RUN (no SPY/QQQ/IWM stock bars).", ""]
        return
    L.append(f"Chosen on 2016-01-04..2019-12-31 only: the highest daily Sharpe among cells with at least {G['min_disc_trades']:,} "
             f"trades. **Chosen: {G['chosen'] or 'none'}** ({cell_txt(G['chosen'])}): {G['choice_why']}.")
    if G["chosen"]:
        L.append(f"**Holdouts (Part A's 7-item bar each): {_yn(G['pass'])}** (a cell passes only when both holdouts pass).")
        L += _head(BAR_COLS)
        for w in HOLDOUTS:
            L.append(_bar_line(G["chosen"], G["holdouts"][w]))
        L.append("")
        for w in HOLDOUTS:
            L.append(f"- {WINDOW_TXT[w]}: **{_yn(G['holdouts'][w]['pass'])}**")
            _checks(L, G["holdouts"][w]["checks"])
        L.append("")
        if G.get("compounding"):
            L.append("**Compounding view (Amendment 16; information, not trials)** for the chosen cell:")
            L.append("")
            for w in HOLDOUTS:
                L += compound.render_md(G["compounding"][w], f"{G['chosen']}, {WINDOW_TXT[w]}")
        else:
            L += ["Compounding view: not shown (only for a cell that passes).", ""]
    sp = G["share_positive"]
    L.append(f"**Share of cells with a positive holdout Sharpe:** holdout 1 {sp['holdout1']['cells']}/{sp['holdout1']['of']} "
             f"({_f(sp['holdout1']['share'] * 100, 1)}%), holdout 2 {sp['holdout2']['cells']}/{sp['holdout2']['of']} "
             f"({_f(sp['holdout2']['share'] * 100, 1)}%), both {sp['both']['cells']}/{sp['both']['of']} ({_f(sp['both']['share'] * 100, 1)}%).")
    L += ["", "By setting (share of that setting's cells with a positive daily Sharpe; mean Sharpe in brackets):"]
    L += _head(("setting", "value") + tuple(WINDOW_TXT[w] for w in WINDOWS))
    for dim, vals in G["by_setting"].items():
        for v, o in vals.items():
            L.append(_row([dim, TRAIL_TXT.get(v, v)] + [f"{_f(o[w]['positive'] * 100, 1)}% ({_f(o[w]['mean_sharpe'], 3)})" for w in WINDOWS]))
    L += ["", "The full grid (daily Sharpe annualized; exp = expectancy per trade, $; vol-sized shares, base costs):"]
    cols = ("#", "cell", "U used")
    for w in ("disc", "H1", "H2"):
        cols += (f"{w} trades", f"{w} Sharpe", f"{w} exp $", f"{w} PF")
    L += _head(cols)
    for r in G["rows"]:
        cells = [r["order"] + 1, r["cell"] + (" **(chosen)**" if r["cell"] == G["chosen"] else "") + (" (NB-VOL)" if r["cell"] == BASE_ID else ""),
                 r["universe_used"]]
        for w in WINDOWS:
            s = r[w]
            cells += [s["trades"], _f(s.get("sharpe"), 3), _f(s.get("expectancy")), _f(s.get("pf"))]
        L.append(_row(cells))
    L.append("")


def _fixes_md(L, F):
    L += ["## Addendum 15.2: the loss-autopsy fixes on NB-VOL (U3, vol-sized)", ""]
    if not F:
        L += ["NOT RUN (no SPY/QQQ/IWM stock bars).", ""]
        return
    L.append("A fix holds when it passes Part A's 7-item bar in both holdouts and beats the unfixed NB-VOL's daily Sharpe in both "
             "(Builder's reading R9; both parts shown).")
    L += _head(BAR_COLS)
    for w in HOLDOUTS:
        L.append(_bar_line("NB-VOL (unfixed)", F["NB-VOL"]["windows"][w]))
    for fx, o in F["fixes"].items():
        for w in HOLDOUTS:
            L.append(_bar_line(f"{fx} ({o['what']})", o["windows"][w]))
    L.append("")
    for fx, o in F["fixes"].items():
        L.append(f"**{fx}** ({o['what']}): **{'holds' if o['holds'] else 'does not hold'}**; beats NB-VOL's daily Sharpe: "
                 + ", ".join(f"{WINDOW_TXT[w]} {'yes' if o['beats_sharpe'][w] else 'no'} ({_f(o['windows'][w]['sharpe'], 3)} vs "
                             f"{_f(F['NB-VOL']['windows'][w]['sharpe'], 3)})" for w in HOLDOUTS)
                 + f"; 7-item bar in both holdouts: {'yes' if o['bar_both'] else 'no'}.")
        for w in HOLDOUTS:
            _checks(L, o["windows"][w]["checks"], f"{WINDOW_TXT[w]}: ")
        if o.get("compounding"):
            L.append("")
            for w in HOLDOUTS:
                L += compound.render_md(o["compounding"][w], f"{fx}, {WINDOW_TXT[w]}")
        L.append("")
    L.append("NB-VOL (unfixed) for reference:")
    for w in HOLDOUTS:
        _checks(L, F["NB-VOL"]["windows"][w]["checks"], f"{WINDOW_TXT[w]}: ")
    L.append("")


def summary_lines(res):
    out = []
    u = res.get("universe") or {}
    G = res.get("grid")
    if G:
        sp = G["share_positive"]
        ran = "U7" if u.get("used") == "U7" else "the three (no DIA/XLK/XLF/SMH bars)"
        line = f"15.1 grid ({LABEL}; the U7 cells ran on {ran}): chosen {G['chosen'] or 'none'}"
        if G["chosen"]:
            hb = G["holdouts"]
            line += (f", holdout 1 {_yn(hb['holdout1']['pass'])} (Sharpe {hb['holdout1']['sharpe']}), holdout 2 "
                     f"{_yn(hb['holdout2']['pass'])} (Sharpe {hb['holdout2']['sharpe']}) -> {'PASSES' if G['pass'] else 'does not pass'}")
            if not G["pass"]:
                ff = [f"{w}: {_first_fail(hb[w]['checks'])}" for w in HOLDOUTS if not hb[w]["pass"]]
                line += f" (first fails: {'; '.join(ff)})"
        line += (f"; positive holdout Sharpe in {sp['holdout1']['cells']}/162 cells (holdout 1), {sp['holdout2']['cells']}/162 "
                 f"(holdout 2), {sp['both']['cells']}/162 (both)")
        out.append(line)
    else:
        out.append("15.1 grid: NOT RUN")
    F = res.get("fixes")
    if F:
        b = F["NB-VOL"]["windows"]
        out.append(f"NB-VOL unfixed: daily Sharpe holdout 1 {b['holdout1']['sharpe']}, holdout 2 {b['holdout2']['sharpe']}; 7-item bar "
                   f"{_yn(b['holdout1']['pass'])} / {_yn(b['holdout2']['pass'])}")
        for fx, o in F["fixes"].items():
            w = o["windows"]
            out.append(f"15.2 {fx} ({o['what']}): {'HOLDS' if o['holds'] else 'does not hold'}; Sharpe {w['holdout1']['sharpe']} / "
                       f"{w['holdout2']['sharpe']}, beats NB-VOL {o['beats_sharpe']['holdout1']} / {o['beats_sharpe']['holdout2']}, 7-item bar "
                       f"{_yn(w['holdout1']['pass'])} / {_yn(w['holdout2']['pass'])}")
    else:
        out.append("15.2 fixes: NOT RUN")
    return out


BUILDER_READINGS = [
    "R1 lookback: only the 14 changes; A1's 'at least 10' sessions with a bar at t stays in every cell (LB 10 needs all 10); "
    "the vol sizing's 14 daily returns stay 14.",
    "R2 check interval: the first check stays the bar finishing 10:00 and the last bound 15:30; CI 15 = 10:00, 10:15, ..., 15:30 "
    "(23 checks), CI 30 = A1's 12, CI 60 = 10:00, 11:00, ..., 15:00 (6).",
    "R3 trailing stop: only the flat-exit level changes (VWAP only: long close < VWAP, short close > VWAP; band only: long close < "
    "UB, short close > LB); the reversal through the opposite band stays; a missing VWAP falls back to the band.",
    "R4 VM multiplies sigma in both bands, so it moves the entry, the reversal and the band stop together.",
    "R5 universe: U7 only when DIA, XLK, XLF and SMH all have 1-minute bars in each window (2016-2019, holdout 1, DEV); "
    "otherwise every U7 cell runs on the three; a warning when a symbol in use covers under 95% of a window's sessions.",
    "R6 choice ties: higher Sharpe, then more discovery trades, then the listed order; no cell with 1,000 trades = no choice.",
    "R7 Part A's item 3 per holdout: holdout 1 = profitable in at least 3 of the 4 years 2020-2023 (6 of 8 scaled; Jan 2024 "
    "is not a year); holdout 2 = the DEV total > 0. The other six items use the window's trades and sessions as written.",
    "R8 a grid cell passes only when its 7-item bar passes in both holdouts.",
    "R9 a fix holds when it passes the 7-item bar in both holdouts and beats the unfixed NB-VOL's daily Sharpe in both.",
    "R10 N1 / N2 block new positions: a blocked reversal closes the position without opening the other side; N1 counts "
    "positions opened that day; N2 allows an entry at the 12:00 check (index 149) and none after it.",
    "R11 compounding: each holdout window on its own; a trade's risk = notional x the 14-day sd (the vol sizing's own "
    "one-day one-sd move, $200 unless the 4x cap binds; $200 when sd = 0).",
]
