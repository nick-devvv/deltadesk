"""sprint/r10grid.py - round 10's 0DTE option exit / entry grid and its add-ons (SPRINT_PLAN Amendment 15, Addendum 15.3,
Addendum 15.5 R1-R3 and the information-only regime features, Amendment 16's stop "none" and R4). Pre-registered 2026-11-01
before any round-10 code or run. Research only: cached bars only, no network, no orders. Every number is a BACKTEST: option
prices are MODELED (BS, calibrated IV; sprint/modeled.py) on HIST 2016-01-04..2024-01-31 and REAL (Alpaca option bars) on
DEV 2024-08-01..2026-06-30. L1 (2026-07-01..10-30) and L2 (2024-02-01..07-31) are never read: a day inside them is refused.

THE GRID (Amendment 15 + Amendment 16)
  Entries (7, sprint/entries.py as they stand): vwap_macd with MACD on 1-, 2- and 5-minute bars (vwap_macd1/2/5), orb15,
    orb30, failed_break (calls), pd_retest. SPY + QQQ + IWM pooled.
  Cells per entry: stop (option -10/-20/-30/-50% of the debit, the setup's level stop, none) x target (+20/+30/+50/+100%,
    none) x trail (none, gb50) x time cap (30 min, 60 min, all out 15:25) x contract (d40-55t45, d20-30t25, n1d40-55t45) x
    trend filter (off, on) = 6 x 5 x 2 x 3 x 3 x 2 = 1,080; 7,560 in all. Cell order = that listed order (CELLS).
  One pass per entry: each signal's contract is picked once per contract rule and every exit variant of that contract is
    evaluated together over its tape (Exits); then every cell keeps its own one-position-at-a-time state (replay).
  Mechanics (sprint/optpass.py / sim.py, desk fills, so a fixed-stop cell at 15:25 equals an engine run with stop="fixed"
    and the same trail, trade by trade): a decision at bar j enters at the first option print in j+1..j+3 (traded price +
    half-spread + $0.65); no entry when j+1 >= 15:30 or the all-out; debit = entry fill without fees.
    * option stop -X%: trigger debit x (1 - X) on the option's traded price inside the bar; same-bar stop beats target;
      fill at the worse of the trigger and the next real price (fills.OptionTape.stop_basis).
    * target +Y%: trigger debit x (1 + Y), fill at the better of the trigger and the bar's open.
    * gb50: sim.py's giveback trail: once green, a premium stop at the traded price whose proceeds keep 50% of the peak open
      profit (peak from bar highs since entry, after costs); set at the end of a bar, acts from the next bar; it and the
      option stop combine as the higher of the two.
    * level stop: sim.py's level stop: the signal's `invalid` -/+ max($0.02, 0.05 x ATR(14, 1m)) judged on finished 1-minute
      underlying closes from the entry bar on, exiting at the next option print.
    * time cap T minutes: bars e..e+T-1 are watched (e = the entry bar), then out at the first print at or after e+T (Part S's
      max-hold convention); all out 15:25 (12:50 on early-close days) the same way. VOID = no print to exit on (skipped).
    * same-bar order (sim.py): premium stop, then the level stop (pending to the next print), then the target.
    * trend filter "on": only trades whose side agrees with the close vs the open at the signal bar.
    * one position at a time per cell and symbol: a signal is taken when that cell's previous exit filled at or before the
      signal bar; a VOID or skipped trade leaves the cell flat.
  Costs: the pre-registered MODELED-SPREAD (2% of premium, $0.005 floor) on both periods, $0.65 per contract per side; PF 2x
    with 2 half-spreads (4 on stop exits), as optpass. Logged chains are never read.
  Choice (per entry, on HIST 2016-01-04..2019-12-31 MODELED ONLY): the highest PF among cells with at least 100 discovery
    trades; ties: more trades, then the cell listed first. Frozen into a JSON (write_frozen) before any holdout readout.
  Holdout 1 = HIST 2020-01-01..2024-01-31 (MODELED): Amendment 10.3's bar (>= 60 trades, PF >= 1.25, PF 2x > 1.0,
    profitable in >= 3 of 2020-2023 among years with 10+ trades, positive without the best 5 trades).
  Holdout 2 = DEV (REAL): >= 60 trades, PF >= 1.25, PF 2x > 1.0, above the same cell's random-side twin (seed 31).
  Reported: heat maps (stop x target), the share of cells with PF > 1 per window, the $3,000 account view.

ADD-ONS (each on an entry's frozen cell; the same entry, contract and trend filter unless stated)
  R2 (15.5): the frozen cell with the contract d55-70t60 (0DTE, |delta| 0.55-0.70 nearest 0.60); also 15.3's rules (as
    published, with the day gates) on d55-70t60. Holds when it passes Amendment 15's holdout bars and beats the original's PF
    in both holdouts.
  R3 (15.5): 3 contracts; until +30% the frozen cell's stop (its target, trail and time cap are replaced); sell 1 at +30%,
    then the stop on the other 2 moves to the entry price (debit); sell 1 at +60%; the last one trails gb50 (its stop is the
    higher of the entry price and the giveback); all out 15:25. P/L per 3-contract trade vs the frozen cell x 3. Holds when it
    passes Amendment 15's holdout bars and its P/L per 3-contract trade beats the frozen cell's x 3 in both holdouts.
  R4 (16): stop -50%; at +50% the stop moves to break-even; at +100% to +50%; from +150% a gb50 trail (with the +50% floor);
    all out 15:25. The same bars as R3 (expectancy above the frozen cell's, 1 contract each).
  The thresholds are reached on bar highs; a moved stop acts from the next bar (sim.py's end-of-bar updates).

ADDENDUM 15.3 AS CORRECTED BY ADDENDUM 16.2 (the alpaca-options-framework's live path; SPY decides, QQQ information; 16.2
  replaces 15.3's list, which is no longer run), with and without the day gates:
  decisions on finished 1-minute bars 09:45-12:00. A call needs close > session VWAP, EMA(5) > EMA(20) of 1-minute closes,
  5-bar ROC >= +0.03% and at least 3 consecutive green bars; a put mirrors each. ATR5 (the mean TRUE range of the last 5
  1-minute bars) >= $0.20. A 3-bar cooldown after a trade closes; one position at a time; premium $0.20-$10.00.
  Strike: the 0.60 x 5-day-ATR target (capped at $4.50, $1 grid) only sets the watched window (target +/- 5 strikes); the
  contract is the nearest out-of-the-money strike in that window within 0.3% of SPY's entry price; none = no trade.
  Exits (unchanged; no momentum-flip exit) on the option's 1-minute bars (desk mechanics, as the grid) plus SPY: stop at 50% of the entry price,
  target +50%, a trail armed at +20% exiting at 88% of the peak, an SPY stop max(0.75 x ATR5, $0.10) beyond the entry
  SPY price on finished 1-minute closes, all out 15:25. Day gates at the $150-risk sizing: no new entry after a day P/L of
  -$300 or +$125 or 3 wins in a row. Windows: HIST 2016-01..2024-01 MODELED and DEV REAL, B3's bars. Information: by hour,
  by exit reason, win rate vs break-even win rate.

R1 pm_inside_break (15.5; SPY, QQQ): the day qualifies when the premarket range (04:00-09:29 bars) lies inside the prior
  session's regular-hours range. Entry: the first finished 1-minute bar from 09:45 to 12:00 closing above the premarket high
  (call) or below the premarket low (put); one a day per symbol. Exit: a finished 5-minute bar (09:30-aligned) closing back
  inside the premarket range, else the time exit (shares: the close of the bar finishing 15:55; options: all out 15:25).
  The claim first (the share of break days whose session close is beyond the broken level, qualifying vs not), then shares
  ($10,000, Part A's costs, Part A's 7-item bar), then 0DTE options d40-55t45 and d55-70t60 (B3's bars), each beside the
  control on non-qualifying days and a random-side twin (seed 31).

INFORMATION ONLY: every grid signal carries features.entry_features and the four REGIME10 features (sprint/features.py);
  tercile tables on 2016-2019 only (each entry's frozen cell), and SPY vs QQQ P/L per entry by VIXY-percentile tercile.

TRIALS (TRIALS, written to the result the way round 9 does): the grid 7,560 + R1 3 + R2 8 + R3 7 + R4 7 + 15.3 2 = 7,587.
  The deflated Sharpe uses the run logs' count + 7,767 (round 10's total, Amendment 16).

BUILDER'S READING (literal readings where the text is open; nothing here comes from a result):
  1. vwap_macd on 1- and 5-minute bars: entries.vwap_macd's rule with "2-minute" read as "N-minute" everywhere (bars anchored
     at 09:30, finished only; MACD continuing from the two prior sessions' N-minute closes; arming bars start at or after
     09:44; the retest within 10 N-minute bars; signal bars finish by 15:15). vwap_macd2 is entries.vwap_macd itself, and
     vwap_macd_n(ctx, 2) reproduces it exactly (tested). entries.py is not edited.
  2. The level stop is sim.py's (the buffer included) without its time-of-day premium ceiling or the ceiling skip: the grid's
     stop dimension is one stop. A signal whose level stop is not beyond its price leaves only the level cells untaken.
  3. "Stop none": no stop at all (the trail, target, time cap and 15:25 still act). Amendment 16 appends it to the stop list.
  4. Time caps count from the entry bar (Part S's max-hold convention). The trend filter compares the signal bar's close
     with the session's open (the first regular-hours bar's open); equal = no agreement.
  5. "The simpler cell in the order listed" = the cell listed first (stop, target, trail, cap, contract, trend, each in the
     listed order). PF is compared exactly (integer cents), not rounded; a PF with no loss ranks first.
  6. "Above the random-side twin" = DEV expectancy per trade above the twin's. The twin: the same signals with a seeded
     side (crc32 of seed|symbol|day|bar, as ind5.random_side, seed 31), the same cell rules (its trend filter applies to the
     twin's side), the level stop keeping the signal's stop distance (engine's random entries).
  7. MODELED IV multipliers: run 4's calibration (data/sprint/calib_modeled.json) where it has the key (n1d40-55t45|P uses
     round 8's labeled fallback); d20-30t25, d55-70t60 and 15.3's contract have no key there, so they get Amendment 5's
     method (median iv_est / IV proxy per rule|side, >= 30 rows) on this round's DEV real picks (real signals that filled),
     labeled "round 10 DEV calibration"; HIST results on them are NOT VALIDATED. A key with < 30 rows refuses its HIST cells.
  8. R3: the frozen cell keeps its entry, contract, trend filter and stop until +30%; "entry price" = the debit. R4:
     "break-even" = sim.py's breakeven stop (the traded price whose proceeds after costs equal the cost); +50/+100/+150% are
     % of the debit on bar highs. R2 on the framework (16.2) swaps the strike rule (the watched window and the 0.3%
     out-of-the-money activation zone) for d55-70t60; 16.2 lists the premium band under Entry, so it stays ($0.20-$10.00 on the
     d55-70t60 price). Judged gated, as published; the ungated R2 is information.
  9. The framework (16.2; the published code read as data where the words are open): "entries 09:45-12:00" is the bot's
     wall-clock entry window, so decision bars 14..149 (bars finishing 09:45..12:00) with the fill no later than the 12:00
     bar. EMA(5) / EMA(20): momentum.py's EMA (seeded with its first price), preseeded with the prior session's last 30
     regular-hours closes (the live bot's preseed) and then every regular-hours bar of the day; without a prior session it
     seeds on the day's first close. Consecutive bars: momentum.py's counters (a doji leaves them; reset per session). ROC5
     and ATR5 over the bars received (a minute without a bar is skipped, as the bot never receives it); ATR5's true range uses
     the previous bar's close. VWAP = the session VWAP of sprint/data (bar HLC3 x volume from 09:30, the bot's formula). The
     5-day ATR = the mean high-low of the 5 prior daily bars; the target = Python round(S +/- offset) on the $1 grid; S = the
     decision bar's close (the bot's spy_price); "out of the money" = call K > S, put K < S; "within 0.3%" = |K - S| / S <=
     0.003; nearest = the smallest |K - S|; the premium band is checked on that one contract (no fallback to a farther
     strike). Sizing max(1, floor($150 / (0.5 x entry x 100))); the cooldown = the next decision at least 2 bars after the exit
     bar (entry 3 bars later); the SPY stop is max($0.10, 0.75 x ATR5 at the decision) beyond the decision bar's close; the
     trail peak from bar highs since entry. The momentum-flip exit is not used (main.py never calls check_exit).
 10. R1: "from 09:45 to 12:00" = signal bars 15..149 (the desk's ORB/entries convention); a 5-minute bar counts once it
     finishes at or after the entry bar; "inside" includes the edges; the claim uses the session's last regular-hours close.
     R1 has no written pass bar: the standing bars for a rule with no fitted parameter apply (shares: Part A's 7 items;
     options: B3's), with the control and the twin reported, not judged.
 11. Regime terciles: numpy.quantile 1/3, 2/3 over each entry's frozen-cell trades of 2016-2019 with a value; low <= lower
     cut, high >= upper cut, mid between. VIXY terciles are the fixed thirds of the 252-day percentile (f_vixy_pctl).
 12. Amendment 15 names no symbols: the grid pools SPY + QQQ + IWM, the sprint's standing set for these setups (Amendment 9,
     round 8's option twins); 15.3 and R1 name their own (SPY decides 15.3, QQQ information; R1 SPY + QQQ).
 13. Costs: Amendment 15 says "with sprint/optpass.py", so the grid keeps optpass's pre-registered MODELED-SPREAD on both
     periods (round 8's convention; HIST may never use 2026 chains, and DEV stays on the same model so the holdouts compare).
 14. Amendment 16's compounding view (information) lives in sprint/compound.py (round10/noise); tools/sprint_r10_grid.py
     calls it for every rule here that passes, on its holdout windows (the grid's frozen cells and R2-R4: holdout 1 MODELED and
     holdout 2 REAL; 15.3 and R1, which have no fitted parameter: HIST 2016-2023 MODELED and DEV REAL), each window apart,
     with risk = the debit per trade (x 3 for R3) for options and the $10,000 notional for R1's shares.
DATA: the existing DEV option pulls (0DTE and next expiry, every $1 strike within 3% of the open widened to the day's range)
  hold every round-10 contract on ordinary days (16.2's strike is within 0.3% of the price); needed_option_contracts() lists,
  per DEV day, the strikes a pick near a big-move day's high or low could reach beyond that band (d20-30t25's far edge). The
  round 10 pull exports them to options_r10/ and options_r10_next/, and the real tapes here merge both folders
  (read_option_day_r10: most prints wins, the existing cache wins a tie); sprint/data.py is unchanged. For the round
  10 pull tool. Without them such a pick finds no strike in its band and is skipped (counted in the report).
"""
import gzip
import hashlib
import json
import math
import time
import zlib
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

from . import bs, contracts, data, entries, features, periods, shares
from . import modeled as MD
from . import spread as SP
from .fills import ENTRY_WAIT, FEE, MULT
from .fills import pnl as fills_pnl
from .optpass import DayTapes
from .sim import ALLOUT, EARLY_ALLOUT, NO_NEW_AFTER, Costs, stop_buffer

# ---------------------------------------------------------------- the grid
ENTRIES = ("vwap_macd1", "vwap_macd2", "vwap_macd5", "orb15", "orb30", "failed_break", "pd_retest")
STOPS = (("s10", 0.10), ("s20", 0.20), ("s30", 0.30), ("s50", 0.50), ("level", None), ("none", None))
TARGETS = (("t20", 0.20), ("t30", 0.30), ("t50", 0.50), ("t100", 1.00), ("tnone", None))
TRAILS = ("none", "gb50")
CAPS = (("m30", 30), ("m60", 60), ("1525", None))
CONTRACTS = ("d40-55t45", "d20-30t25", "n1d40-55t45")
TRENDS = ("off", "on")
R2_CONTRACT = "d55-70t60"
EVAL_CONTRACTS = CONTRACTS + (R2_CONTRACT,)
GB = 0.50
SYMBOLS = ("SPY", "QQQ", "IWM")
TWIN_SEED = 31
MIN_DISC = 100
NG = 6 * 5 * 2 * 3                                   # 180 exit variants per contract
R3_BASE, R4_V = NG, NG + 6                            # R3 per frozen stop kind (180..185), R4 (186)
NV = NG + 7
VARIANTS = [(s, t, tr, cp) for s in range(6) for t in range(5) for tr in range(2) for cp in range(3)]
CELLS = [(s, t, tr, cp, c, f) for s in range(6) for t in range(5) for tr in range(2) for cp in range(3) for c in range(3)
         for f in range(2)]
NCELL = len(CELLS)
assert NG == len(VARIANTS) == 180 and NCELL == 1080
CELL_V = np.array([((s * 5 + t) * 2 + tr) * 3 + cp for s, t, tr, cp, c, f in CELLS], np.int64)
CELL_C = np.array([c for *_x, c, f in CELLS], np.int64)
CELL_F = np.array([f for *_x, f in CELLS], bool)
VSPEC = [(s if s < 4 else 4, tr, s == 4, t, cp) for s, t, tr, cp in VARIANTS]   # (premium-stop row, gb, level, target, cap)
VOID, LEVEL_BAD, NO_TRADE = -1, -2, -3
BIG = 1 << 30
R3_UP1, R3_UP2 = 0.30, 0.60
R4_STEPS = (0.50, 1.00, 1.50)
REASONS = ("FIXED STOP", "GIVEBACK STOP", "LEVEL STOP", "FIXED TARGET", "TIME CAP", "ALL OUT", "R3 ENTRY-PRICE STOP",
           "R3 GIVEBACK", "R4 STOP -50%", "R4 BREAKEVEN", "R4 LOCK +50%", "R4 GIVEBACK")
RS = {r: k for k, r in enumerate(REASONS)}
SKIPS = ("ok", "no new trades after 15:30", "signal after the all-out time", "no underlying close at the signal bar",
         "no contract picked", "no option print in the 3 minutes after the signal")


def cell_id(k):
    s, t, tr, cp, c, f = CELLS[k]
    return f"{STOPS[s][0]}.{TARGETS[t][0]}.{TRAILS[tr]}.{CAPS[cp][0]}.{CONTRACTS[c]}.{TRENDS[f]}"


def cell_text(k):
    s, t, tr, cp, c, f = CELLS[k]
    st = "the setup's level stop" if STOPS[s][0] == "level" else "no stop" if STOPS[s][0] == "none" else f"stop -{int(STOPS[s][1] * 100)}%"
    tg = "no target" if TARGETS[t][1] is None else f"target +{int(TARGETS[t][1] * 100)}%"
    cap = "all out 15:25" if CAPS[cp][1] is None else f"time cap {CAPS[cp][1]} min"
    return f"{st}, {tg}, trail {TRAILS[tr]}, {cap}, {CONTRACTS[c]}, trend filter {TRENDS[f]}"


def cell_index(stop, target, trail, cap, contract, trend):
    """Cell index from the six ids (e.g. "s20", "t50", "gb50", "m60", "d40-55t45", "on")."""
    s = [x[0] for x in STOPS].index(stop)
    t = [x[0] for x in TARGETS].index(target)
    return CELLS.index((s, t, TRAILS.index(trail), [x[0] for x in CAPS].index(cap), CONTRACTS.index(contract), TRENDS.index(trend)))


# ---------------------------------------------------------------- windows, buckets
HIST_A, HIST_B = periods.HIST[0].isoformat(), periods.HIST[1].isoformat()
DEV_A, DEV_B = periods.DEV[0].isoformat(), periods.DEV[1].isoformat()
DISC = (HIST_A, "2019-12-31")
H1 = ("2020-01-01", HIST_B)
H2 = (DEV_A, DEV_B)
WINDOWS = {"disc": DISC, "h1": H1, "h2": H2}
BUCKETS = [str(y) for y in range(2016, 2024)] + ["2024-01", "2024b", "2025", "2026"]
WIN_BUCKETS = {"disc": [0, 1, 2, 3], "h1": [4, 5, 6, 7, 8], "h2": [9, 10, 11]}
NB = len(BUCKETS)
NAGG = 7                                              # n, wins, losses, sum of wins, sum of losses (cents), same at 2x


def bucket_of(day_iso):
    y = day_iso[:4]
    if y == "2024":
        return 8 if day_iso <= HIST_B else 9
    return BUCKETS.index(y)


def check_day(d):
    hit = periods.overlaps(d, d)
    if hit:
        raise periods.LockedPeriod(f"REFUSED: {d} is inside locked period {', '.join(hit)}")
    if not (periods.HIST[0] <= d <= periods.HIST[1] or periods.DEV[0] <= d <= periods.DEV[1]):
        raise periods.LockedPeriod(f"REFUSED: {d} is outside HIST and DEV")


# ---------------------------------------------------------------- entries
def _bars_n(ctx, n):
    """Finished n-minute bars of the day anchored at 09:30: [(start, end, o, h, l, c)] (entries._bars2 for n = 2)."""
    nb = data.N // n
    C = np.asarray(ctx.c[:nb * n], float).reshape(nb, n)
    ok = ~np.isnan(C).any(axis=1)
    H = np.asarray(ctx.h[:nb * n], float).reshape(nb, n).max(axis=1)
    Lo = np.asarray(ctx.l[:nb * n], float).reshape(nb, n).min(axis=1)
    O = np.asarray(ctx.o[:nb * n], float).reshape(nb, n)[:, 0]
    return [(q * n, q * n + n - 1, float(O[q]), float(H[q]), float(Lo[q]), float(C[q, -1])) for q in np.nonzero(ok)[0]]


def vwap_macd_n(ctx, n, side="both"):
    """entries.vwap_macd with N-minute bars (Builder's reading 1)."""
    s, d = ctx.series, ctx.day
    prior = []
    nb = data.N // n
    for x in s.prior_days(d, 2):
        C = s.rth[x][:nb * n, 3].reshape(nb, n)
        prior += [float(v) for v in C[~np.isnan(C).any(axis=1), -1]]
    bars = _bars_n(ctx, n)
    if len(prior) + len(bars) < 40:
        return []
    M, S = entries._macd(np.array(prior + [x[5] for x in bars]))
    off = len(prior)
    armed, used, out = {}, set(), []
    for t, (b0, b1, o, h, l, c) in enumerate(bars):
        k = off + t
        vw = ctx.vwap[b1]
        if math.isnan(vw) or b1 > entries.DESK_LAST:
            continue
        z = entries._z(ctx, b1)
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
                if side in ("both", sd) and b1 >= entries.DESK_FIRST:
                    inv = min(l, vw - z) if sd == "C" else max(h, vw + z)
                    out.append(entries.Signal(f"vwap_macd{n}", ctx.sym, d, sd, b1, c, inv, {"vwap": vw}))
        if b0 >= 14:
            if up_x and c > vw + 0.01 and "C" not in used:
                armed["C"] = t
            if dn_x and c < vw - 0.01 and "P" not in used:
                armed["P"] = t
    return out


def entry_signals(ctx, entry):
    """The entry's signals on ctx's day, in bar order (stable)."""
    if entry == "vwap_macd2":
        sg = entries.vwap_macd(ctx)
    elif entry in ("vwap_macd1", "vwap_macd5"):
        sg = vwap_macd_n(ctx, int(entry[-1]))
    elif entry in ("orb15", "orb30", "failed_break", "pd_retest"):
        sg = entries.signals(ctx, entry)
    else:
        raise ValueError(f"unknown round-10 entry {entry}")
    return sorted(sg, key=lambda s: s.idx)


def twin_side(seed, sym, day, idx):
    """ind5.random_side's coin: crc32 of seed|symbol|day|bar, even -> call."""
    return "C" if zlib.crc32(f"{seed}|{sym}|{day}|{idx}".encode()) % 2 == 0 else "P"


def twin_signals(sigs, seed, sym, day):
    """The random-side twin: the same signals with a seeded side; a level keeps the signal's stop distance."""
    out = []
    for s in sigs:
        side = twin_side(seed, sym, day, s.idx)
        inv = s.invalid
        if inv is not None and side != s.side:
            dist = (s.price - inv) if s.side == "C" else (inv - s.price)
            inv = s.price - dist if side == "C" else s.price + dist
        out.append(entries.Signal(s.setup, s.symbol, s.day, side, s.idx, s.price, inv, dict(s.info, random_seed=seed, orig_side=s.side)))
    return out


def session_open(ctx):
    try:
        return float(ctx.series.daily.loc[ctx.day, "open"])
    except (KeyError, TypeError, ValueError):
        return math.nan


def agrees(ctx, side, j, o0=None):
    """Trend filter: the side agrees with the signal bar's close vs the session's open."""
    o0 = session_open(ctx) if o0 is None else o0
    cj = float(ctx.c[j])
    if math.isnan(o0) or math.isnan(cj):
        return False
    return cj > o0 if side == "C" else cj < o0


# ---------------------------------------------------------------- costs, vectorized (sim.Costs, exactly)
def _hs_v(costs, px):
    sp = costs.spread
    if isinstance(sp, SP.SpreadModel) and not sp.table:
        pct = sp.pct if sp.pct is not None else (SP.DEFAULT_PCT_INDEX if costs.sym in SP.INDEX_ETFS else SP.DEFAULT_PCT_STOCK)
        return np.maximum(pct * np.maximum(px, 0.0), SP.TICK_HALF)
    return np.array([costs.hs(float(p)) for p in np.ravel(px)]).reshape(np.shape(px))


def proceeds_v(costs, px):
    return px - costs.k * _hs_v(costs, px) - FEE / MULT


def trigger_v(costs, target):
    """Costs.trigger elementwise (the same bisection, so the same floats)."""
    target = np.asarray(target, float)
    lo = np.zeros_like(target)
    hi = np.maximum(4.0 * target + 1.0, 1.0)
    zero = proceeds_v(costs, lo) >= target
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        m = proceeds_v(costs, mid) < target
        lo = np.where(m, mid, lo)
        hi = np.where(m, hi, mid)
    return np.where(zero, 0.0, hi)


def _fh(mask, start=0):
    if start >= len(mask):
        return BIG
    m = mask[start:]
    k = int(m.argmax()) if len(m) else 0
    return start + k if len(m) and m[k] else BIG


def cents(p):
    return int(round(round(p, 2) * 100))


class Exits:
    """Every exit variant of one (signal, contract) over the tape segment [e, A) (A = the all-out bar)."""

    def __init__(self, ctx, tape, e, A, b_in, hs_in, costs, side, stop_s):
        self.ctx, self.tape, self.e, self.A = ctx, tape, e, A
        self.b_in, self.hs_in, self.costs = b_in, hs_in, costs
        self.debit = b_in + hs_in
        self.C = b_in + hs_in + FEE / MULT
        self.up = side == "C"
        self.L = A - e
        o = tape.o[e:A]
        self.has = ~np.isnan(o)
        self.lo = np.where(self.has, tape.l[e:A], np.inf)
        self.hi = np.where(self.has, tape.h[e:A], -np.inf)
        cm = np.maximum.accumulate(self.hi) if self.L else self.hi
        self.peak_prev = np.concatenate([[-np.inf], cm[:-1]]) if self.L else cm
        self.stop_s = stop_s
        self._G = None
        self._kls = None
        self._ev = {}

    # ---- shared pieces
    def G(self):
        """gb50 giveback stop level active in each bar (-inf until green)."""
        if self._G is None:
            G = np.full(self.L, -np.inf)
            pp = self.peak_prev
            fin = np.isfinite(pp)
            if fin.any():
                u, inv = np.unique(pp[fin], return_inverse=True)
                prof = proceeds_v(self.costs, u) - self.C
                lv = np.full(len(u), -np.inf)
                pos = prof > 0
                if pos.any():
                    lv[pos] = trigger_v(self.costs, self.C + (1 - GB) * prof[pos])
                G[fin] = lv[inv]
            self._G = G
        return self._G

    def kls(self):
        if self._kls is None:
            if self.stop_s is None:
                self._kls = BIG
            else:
                sc = self.ctx.c[self.e:self.A]
                ok = ~np.isnan(sc)
                self._kls = _fh(ok & ((sc < self.stop_s) if self.up else (sc > self.stop_s)))
        return self._kls

    def _legs_pnl(self, legs, mult=1):
        p1 = fills_pnl(self.b_in, self.hs_in, legs, 1) * mult
        p2 = fills_pnl(self.b_in, self.hs_in, legs, 2) * mult
        return cents(p1), cents(p2)

    def leg(self, x, basis, is_stop, q=1.0):
        return (q, float(basis), self.costs.hs(float(basis), x), is_stop)

    def stop_at(self, k, level):
        i = self.e + k
        return i, self.tape.stop_basis(i, level)[0]

    def target_at(self, k, level):
        i = self.e + k
        return i, self.tape.target_basis(i, level)[0]

    def next_open(self, i):
        x = self.tape.next_print(i)
        return (None, None) if x is None else (x, float(self.tape.o[x]))

    # ---- the 180 grid variants
    def grid(self):
        d, L = self.debit, self.L
        G = self.G()
        sps = [d * (1 - s) for _n, s in STOPS[:4]] + [-np.inf]
        lv = []
        kps = []
        for sp in sps:
            row, lrow = [], []
            for gb in (0, 1):
                lvl = np.maximum(sp, G) if gb else np.full(L, sp)
                lrow.append(lvl)
                row.append(_fh(self.lo <= lvl) if (gb or sp > -np.inf) else BIG)
            kps.append(row)
            lv.append(lrow)
        tgs = [d * (1 + t) for _n, t in TARGETS[:4]]
        ktg = [_fh(self.hi >= tg) for tg in tgs] + [BIG]
        W = [min(30, L), min(60, L), L]
        level_bad = self.stop_s is None
        kls = BIG if level_bad else self.kls()
        ex = np.empty(NG, np.int16)
        rs = np.zeros(NG, np.int8)
        p1 = np.zeros(NG, np.int32)
        p2 = np.zeros(NG, np.int32)
        ev = self._ev
        for v, (pr, gb, lsf, t, cp) in enumerate(VSPEC):
            if lsf and level_bad:
                ex[v] = LEVEL_BAD
                continue
            w = W[cp]
            kb, key = BIG, None
            a = kps[pr][gb]
            if a < w:
                kb, key = a, (0, pr, gb)
            if lsf and kls < w and kls < kb:
                kb, key = kls, (1,)
            b = ktg[t]
            if b < w and b < kb:
                kb, key = b, (2, t)
            if key is None:
                key = (3, cp)
            r = ev.get(key)
            if r is None:
                if key[0] == 0:
                    k = kps[pr][gb]
                    lvl = float(lv[pr][gb][k])
                    x, basis = self.stop_at(k, lvl)
                    why = "GIVEBACK STOP" if gb and G[k] > sps[pr] else "FIXED STOP"
                    r = (x, RS[why]) + self._legs_pnl([self.leg(x, basis, True)])
                elif key[0] == 1:
                    x, basis = self.next_open(self.e + kls + 1)
                    r = (VOID, 0, 0, 0) if x is None else (x, RS["LEVEL STOP"]) + self._legs_pnl([self.leg(x, basis, True)])
                elif key[0] == 2:
                    x, basis = self.target_at(ktg[key[1]], tgs[key[1]])
                    r = (x, RS["FIXED TARGET"]) + self._legs_pnl([self.leg(x, basis, False)])
                else:
                    x, basis = self.next_open(self.e + W[key[1]])
                    why = "ALL OUT" if W[key[1]] >= L else "TIME CAP"
                    r = (VOID, 0, 0, 0) if x is None else (x, RS[why]) + self._legs_pnl([self.leg(x, basis, False)])
                ev[key] = r
            ex[v], rs[v], p1[v], p2[v] = r
        return ex, rs, p1, p2

    # ---- R4 ratchet (Amendment 16)
    def r4(self):
        d, L = self.debit, self.L
        pp = self.peak_prev
        be = float(self.costs.trigger(self.C))
        g = np.maximum(R4_STEPS[0] * d + d, self.G())
        lvl = np.where(pp >= (1 + R4_STEPS[2]) * d, g, np.where(pp >= (1 + R4_STEPS[1]) * d, (1 + R4_STEPS[0]) * d,
                                                               np.where(pp >= (1 + R4_STEPS[0]) * d, be, 0.5 * d)))
        k = _fh(self.lo <= lvl)
        if k < L:
            x, basis = self.stop_at(k, float(lvl[k]))
            p = pp[k]
            why = ("R4 GIVEBACK" if p >= (1 + R4_STEPS[2]) * d and lvl[k] > (1 + R4_STEPS[0]) * d else
                   "R4 LOCK +50%" if p >= (1 + R4_STEPS[1]) * d else "R4 BREAKEVEN" if p >= (1 + R4_STEPS[0]) * d else "R4 STOP -50%")
            return (x, RS[why]) + self._legs_pnl([self.leg(x, basis, True)])
        x, basis = self.next_open(self.A)
        return (VOID, 0, 0, 0) if x is None else (x, RS["ALL OUT"]) + self._legs_pnl([self.leg(x, basis, False)])

    # ---- R3 scale-out (Addendum 15.5)
    def _r3_after(self, k30):
        """Contracts 2 and 3 after the +30% sale at bar k30: [(exit bar, basis, is_stop, reason)] x 2, or None (VOID)."""
        d, L = self.debit, self.L
        up2 = (1 + R3_UP2) * d
        legs = []
        if self.hi[k30] >= up2:
            x, basis = self.target_at(k30, up2)
            legs.append((x, basis, False, "FIXED TARGET"))
            kp2 = k30
        else:
            k60 = _fh(self.hi >= up2, k30 + 1)
            ks1 = _fh(self.lo <= d, k30 + 1)
            if min(k60, ks1) >= L:
                x, basis = self.next_open(self.A)
                return None if x is None else [(x, basis, False, "ALL OUT")] * 2
            if ks1 <= k60:
                x, basis = self.stop_at(ks1, d)
                return [(x, basis, True, "R3 ENTRY-PRICE STOP")] * 2
            x, basis = self.target_at(k60, up2)
            legs.append((x, basis, False, "FIXED TARGET"))
            kp2 = k60
        lvl2 = np.maximum(d, self.G())
        ks2 = _fh(self.lo <= lvl2, kp2 + 1)
        if ks2 < L:
            x, basis = self.stop_at(ks2, float(lvl2[ks2]))
            legs.append((x, basis, True, "R3 GIVEBACK" if lvl2[ks2] > d else "R3 ENTRY-PRICE STOP"))
        else:
            x, basis = self.next_open(self.A)
            if x is None:
                return None
            legs.append((x, basis, False, "ALL OUT"))
        return legs

    def r3(self, sk):
        """R3 with the frozen stop kind sk (0-3 option stop, 4 level, 5 none): (final exit bar, reason, P/L x 3 contracts)."""
        d, L = self.debit, self.L
        if sk == 4 and self.stop_s is None:
            return (LEVEL_BAD, 0, 0, 0)
        k30 = _fh(self.hi >= (1 + R3_UP1) * d)
        sp = d * (1 - STOPS[sk][1]) if sk < 4 else None
        ks0 = _fh(self.lo <= sp) if sp is not None else BIG
        kl0 = self.kls() if sk == 4 else BIG
        kb, typ = BIG, None
        if ks0 < L:
            kb, typ = ks0, 0
        if kl0 < L and kl0 < kb:
            kb, typ = kl0, 1
        if k30 < L and k30 < kb:
            kb, typ = k30, 2
        if typ is None:
            x, basis = self.next_open(self.A)
            if x is None:
                return (VOID, 0, 0, 0)
            return (x, RS["ALL OUT"]) + self._legs_pnl([self.leg(x, basis, False, 1 / 3)] * 3, 3)
        if typ == 0:
            x, basis = self.stop_at(ks0, sp)
            return (x, RS["FIXED STOP"]) + self._legs_pnl([self.leg(x, basis, True, 1 / 3)] * 3, 3)
        if typ == 1:
            x, basis = self.next_open(self.e + kl0 + 1)
            if x is None:
                return (VOID, 0, 0, 0)
            return (x, RS["LEVEL STOP"]) + self._legs_pnl([self.leg(x, basis, True, 1 / 3)] * 3, 3)
        key = ("r3after", k30)
        rest = self._ev.get(key, 0)
        if rest == 0:
            rest = self._r3_after(k30)
            self._ev[key] = rest
        if rest is None:
            return (VOID, 0, 0, 0)
        x1, b1 = self.target_at(k30, (1 + R3_UP1) * d)
        legs = [self.leg(x1, b1, False, 1 / 3)] + [self.leg(x, b, st, 1 / 3) for x, b, st, _w in rest]
        last = max(rest, key=lambda z: z[0])
        return (last[0], RS[last[3]]) + self._legs_pnl(legs, 3)


# ---------------------------------------------------------------- real tapes: the existing cache plus the round 10 pull's export
# The round 10 pull (tools/sprint_pull10.py) exports the extra contracts needed_option_contracts() lists into
# data/alpaca/options_r10/<U>/<day>/bars.csv.gz (0DTE) and options_r10_next/<U>/<day>/bars.csv.gz (next expiry), the same
# columns as options/ and options_next/. Round 10 reads both: a symbol found in several files keeps the tape with the most
# prints, and on a tie the existing cache (listed first) wins (the rule of sprint/r10credit.read_tapes). sprint/data.py's
# read_option_day is unchanged, so earlier rounds read exactly what they read before.
OPTION_SUBS = {"0dte": ("options", "options_r10"), "next": ("options_next", "options_r10_next")}


def _read_option_file(folder, day, want_trades=True, next_only=False):
    """data.read_option_day's parsing for one folder: {symbol: OptionTape} of the day's contracts that expire on `day` (0DTE)
    or, next_only, after it (every later expiry kept; the caller keeps the nearest)."""
    f = Path(folder) / "bars.csv.gz"
    if not f.exists():
        return {}
    import pandas as pd
    from .fills import OptionTape
    df = pd.read_csv(f, compression="gzip")
    if not len(df):
        return {}
    mi = data._minutes(df["ts"])
    keep = (mi >= 0) & (mi < data.N)
    df, mi = df[keep], mi[keep]
    trades = {}
    tf = Path(folder) / "trades.csv.gz"
    if want_trades and tf.exists():
        t = pd.read_csv(tf, compression="gzip")
        if len(t):
            tm = data._minutes(t["ts"])
            t = t.assign(_m=tm, _ns=pd.to_datetime(t["ts"], utc=True, format="ISO8601").astype("int64"))
            t = t.sort_values(["symbol", "_ns"], kind="stable")
            for s, g in t.groupby("symbol", sort=False):
                ok = (g["_m"] >= 0) & (g["_m"] < data.N)
                trades[s] = (g["_m"].to_numpy()[ok.to_numpy()], g["p"].to_numpy(float)[ok.to_numpy()])
    out = {}
    syms = df["symbol"].to_numpy()
    vals = df[["o", "h", "l", "c", "v"]].to_numpy(float)
    for s in pd.unique(syms):
        meta = data.parse_occ(s)
        if not meta or ((meta["expiry"] <= day) if next_only else (meta["expiry"] != day)):
            continue
        sel = syms == s
        grid = np.full((data.N, 5), np.nan)
        grid[mi[sel]] = vals[sel]
        out[s] = OptionTape(s, meta["right"], meta["strike"], *(grid[:, k] for k in range(5)), trades=trades.get(s))
        out[s].expiry = meta["expiry"]
    return out


def read_option_day_r10(under, day, root=None, want_trades=True, expiry="0dte", subs=None):
    """data.read_option_day over the existing cache and the round 10 export (OPTION_SUBS): the merged {symbol: OptionTape}.
    A symbol in several folders keeps the tape with the most prints; on a tie the folder listed first wins. expiry "next":
    only the nearest expiry after `day` among the merged contracts is kept (data.read_option_day's rule)."""
    check_day(day)
    subs = OPTION_SUBS[expiry] if subs is None else subs
    out = {}
    for sub in subs:
        got = _read_option_file(Path(root or data.ROOT) / sub / under / day.isoformat(), day, want_trades, expiry == "next")
        for s, t in got.items():
            if s not in out or int(np.sum(~np.isnan(t.o))) > int(np.sum(~np.isnan(out[s].o))):
                out[s] = t
    if expiry == "next" and out:
        nearest = min(t.expiry for t in out.values())
        out = {s: t for s, t in out.items() if t.expiry == nearest}
    return out


def option_days_r10(under, root=None, expiry="0dte", subs=None):
    """data.option_days over the existing cache and the round 10 export: the union of the days with a bars file."""
    out = set()
    for sub in (OPTION_SUBS[expiry] if subs is None else subs):
        folder = Path(root or data.ROOT) / sub / under
        if folder.exists():
            out |= {date.fromisoformat(p.name) for p in folder.iterdir() if p.is_dir() and (p / "bars.csv.gz").exists()}
    return out


# ---------------------------------------------------------------- tapes (optpass.DayTapes on the merged real tapes; a missing key refused politely)
class Tapes10(DayTapes):
    """optpass.DayTapes with round 10's real tapes (read_option_day_r10: options + options_r10, options_next +
    options_r10_next); MODELED tapes exactly as DayTapes."""

    def __init__(self, ctx, mode, root=None, odays=None, ndays=None, calib=None, ivp=None):
        self.ctx, self.mode, self.calib, self.ivp = ctx, mode, calib, ivp
        self.real0 = self.real1 = None
        if mode == "real":
            self.real0 = read_option_day_r10(ctx.sym, ctx.day, root) if (odays is None or ctx.day in odays) else {}
            self.root, self.ndays = root, ndays
        self.md0 = self.md1 = None
        self.mult = {}

    def pool(self, rule, side, S):
        if self.mode == "real" and contracts.is_next(rule) and self.real1 is None:
            ok = self.ndays is None or self.ctx.day in self.ndays
            self.real1 = read_option_day_r10(self.ctx.sym, self.ctx.day, self.root, want_trades=False, expiry="next") if ok else {}
        try:
            return super().pool(rule, side, S)
        except ValueError as exc:
            return f"MODELED: {exc}"

    def md_day(self):
        if self.md0 is None:
            self.md0 = MD.ModeledDay(self.ctx)
        return self.md0


def _iv_delta_batch(px, S, K, T, is_call, iters=60):
    """bs.iv_delta_v with per-element S and T: the same arithmetic per element, so one call solves many picks at once."""
    px, S, K, T = (np.asarray(x, float) for x in (px, S, K, T))
    is_call = np.asarray(is_call, bool)
    intrinsic = np.where(is_call, np.maximum(S - K, 0.0), np.maximum(K - S, 0.0))
    upper = np.where(is_call, S, K)
    ok = (px > intrinsic + 1e-9) & (px < upper) & (px > 0)
    lo = np.full(px.shape, bs.IV_LO)
    hi = np.full(px.shape, bs.IV_HI)
    ok &= bs.price_v(S, K, T, hi, is_call) >= px
    ok &= bs.price_v(S, K, T, lo, is_call) <= px
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        below = bs.price_v(S, K, T, mid, is_call) < px
        lo = np.where(below, mid, lo)
        hi = np.where(below, hi, mid)
    iv = 0.5 * (lo + hi)
    sq = iv * np.sqrt(T)
    d1 = (np.log(S / K) + 0.5 * iv * iv * T) / sq
    d = np.where(is_call, bs._ncdf_v(d1), bs._ncdf_v(d1) - 1.0)
    return np.where(ok, iv, np.nan), np.where(ok, d, np.nan)


def prefetch_picks(ctx, tapes, keys, picks):
    """contracts.pick for many (bar, side, rule) keys of one day with ONE implied-vol solve (the same candidates, prices,
    arithmetic and choice as contracts.pick; tests check them equal). Fills picks[key] = (tape, info) or (None, reason)."""
    reqs = []
    for key in sorted(k for k in keys if k not in picks):
        i, side, rule = key
        lo_, hi_, tgt = contracts.RULES[rule]
        S = float(ctx.c[i])
        if math.isnan(S):
            picks[key] = (None, "no underlying close at the signal bar")
            continue
        r = tapes.pool(rule, side, S)
        if r:
            picks[key] = (None, r)
            continue
        nxt = contracts.is_next(rule)
        pool = ctx.tapes_next if nxt else ctx.tapes
        cands = [t for t in pool.values() if t.right == side]
        if not cands:
            picks[key] = (None, f"no {'next-expiry' if nxt else '0DTE'} contracts on file for this side")
            continue
        px = np.array([t.last_close(i, contracts.MAX_AGE) or np.nan for t in cands], float)
        ok = ~np.isnan(px)
        if not ok.any():
            picks[key] = (None, "no contract traded in the 5 minutes before the signal")
            continue
        extra = 0
        if nxt:
            exp = getattr(cands[0], "expiry", None)
            if exp is None:
                picks[key] = (None, "next-expiry contract without an expiry date")
                continue
            extra = 1440 * (exp - ctx.day).days
        reqs.append((key, cands, px, ok, np.array([t.strike for t in cands], float), bs.t_years(390 - (i + 1) + extra), S))
    if not reqs:
        return picks
    PX = np.concatenate([np.where(ok, px, 1.0) for _k, _c, px, ok, _K, _T, _S in reqs])
    SS = np.concatenate([np.full(len(c), S) for _k, c, _p, _o, _K, _T, S in reqs])
    KK = np.concatenate([K for _k, _c, _p, _o, K, _T, _S in reqs])
    TT = np.concatenate([np.full(len(c), T) for _k, c, _p, _o, _K, T, _S in reqs])
    CC = np.concatenate([np.full(len(c), k[1] == "C") for k, c, _p, _o, _K, _T, _S in reqs])
    IV, D = _iv_delta_batch(PX, SS, KK, TT, CC)
    pos = 0
    for key, cands, px, ok, _K, _T, _S in reqs:
        i, side, rule = key
        lo_, hi_, tgt = contracts.RULES[rule]
        n = len(cands)
        iv, d = IV[pos:pos + n], D[pos:pos + n]
        pos += n
        best = None
        for j, t in enumerate(cands):
            if not ok[j] or math.isnan(d[j]):
                continue
            ad = abs(float(d[j]))
            if not lo_ <= ad <= hi_:
                continue
            if ctx.spread is not None and not ctx.spread.spread_ok(ctx.sym, float(px[j]), i + 1):
                continue
            k2 = (abs(ad - tgt), float(px[j]))
            if best is None or k2 < best[0]:
                best = (k2, t, {"symbol": t.symbol, "strike": t.strike, "right": t.right, "px": float(px[j]), "iv": float(iv[j]),
                                "delta": round(float(d[j]), 3), "delta_label": "BS-EST", "rule": rule,
                                "expiry": str(getattr(t, "expiry", ctx.day))})
        picks[key] = (None, f"no contract with BS-EST |delta| in {lo_:.2f}-{hi_:.2f}") if best is None else (best[1], best[2])
    return picks


def fill_at(ctx, j, tape, spread, allout_idx, last=None):
    """optpass.entry_fill with an optional latest fill bar."""
    dec = j + 1
    lim = min(j + ENTRY_WAIT, allout_idx - 1)
    if last is not None:
        lim = min(lim, last)
    e = tape.next_print(dec, lim)
    if e is None:
        return None
    costs = Costs(spread, ctx.sym, dec, 1)
    b_in = float(tape.o[e])
    hs_in = costs.hs(b_in, e)
    return e, b_in, hs_in, costs


# ---------------------------------------------------------------- per-signal evaluation (stage 1)
FEAT_COLS = list(features.FEATURES) + list(features.REGIME10)
NF = len(FEAT_COLS)


class Table:
    """One chunk's signals: meta, per-contract entry info and the (contract, variant) results."""

    META = (("entry", np.int8), ("day", np.int32), ("idx", np.int16), ("side", np.int8), ("oside", np.int8), ("agree", np.bool_),
            ("price", np.float64), ("invalid", np.float64))

    def __init__(self):
        self.meta = {k: [] for k, _t in self.META}
        self.feat, self.cinfo, self.ex, self.rs, self.p1, self.p2 = [], [], [], [], [], []

    def __len__(self):
        return len(self.meta["day"])

    def add(self, meta, feat, cinfo, ex, rs, p1, p2):
        for k, _t in self.META:
            self.meta[k].append(meta[k])
        self.feat.append(feat)
        self.cinfo.append(cinfo)
        self.ex.append(ex)
        self.rs.append(rs)
        self.p1.append(p1)
        self.p2.append(p2)

    def arrays(self, prefix):
        n = len(self)
        out = {f"{prefix}{k}": np.array(self.meta[k], t) for k, t in self.META}
        out[f"{prefix}feat"] = np.array(self.feat, np.float64).reshape(n, NF)
        out[f"{prefix}cinfo"] = np.array(self.cinfo, np.float64).reshape(n, len(EVAL_CONTRACTS), 6)
        out[f"{prefix}ex"] = np.array(self.ex, np.int16).reshape(n, len(EVAL_CONTRACTS), NV)
        out[f"{prefix}rs"] = np.array(self.rs, np.int8).reshape(n, len(EVAL_CONTRACTS), NV)
        out[f"{prefix}p1"] = np.array(self.p1, np.int32).reshape(n, len(EVAL_CONTRACTS), NV)
        out[f"{prefix}p2"] = np.array(self.p2, np.int32).reshape(n, len(EVAL_CONTRACTS), NV)
        return out


def _feat_row(ctx, j, side):
    f = features.entry_features(ctx, j, side)
    f.update(features.regime_features(ctx, j, side))
    return [np.nan if f.get(k) is None else float(f[k]) for k in FEAT_COLS]


def eval_signal(ctx, sg, tapes, spread, allout_idx, picks, skips=None, entry=None, used=None):
    """All contracts x all variants for one signal: (cinfo (4 x 6), ex, rs, p1, p2 (4 x NV each))."""
    nc = len(EVAL_CONTRACTS)
    ex = np.full((nc, NV), NO_TRADE, np.int16)
    rs = np.zeros((nc, NV), np.int8)
    p1 = np.zeros((nc, NV), np.int32)
    p2 = np.zeros((nc, NV), np.int32)
    cinfo = np.full((nc, 6), np.nan)
    cinfo[:, 0] = 0
    j, side = sg.idx, sg.side
    dec = j + 1
    code = 1 if dec >= NO_NEW_AFTER else 2 if dec >= allout_idx else 3 if math.isnan(ctx.c[j]) else 0
    if code:
        cinfo[:, 0] = code
        if skips is not None:
            for rule in EVAL_CONTRACTS:
                skips[(entry, rule, SKIPS[code])] += 1
        return cinfo, ex, rs, p1, p2
    up = side == "C"
    stop_s = None
    if sg.invalid is not None:
        a1 = ctx.atr1[j]
        stop_s = sg.invalid - (1.0 if up else -1.0) * stop_buffer(None if math.isnan(a1) else float(a1))
        if (stop_s >= sg.price) if up else (stop_s <= sg.price):
            stop_s = None
    for ci, rule in enumerate(EVAL_CONTRACTS):
        pk = (j, side, rule)
        if pk not in picks:
            r = tapes.pool(rule, side, float(ctx.c[j]))
            picks[pk] = (None, r) if r else contracts.pick(ctx, side, j, rule)
        tape, info = picks[pk]
        if tape is None:
            cinfo[ci, 0] = 4
            if skips is not None:
                skips[(entry, rule, str(info))] += 1
            continue
        f = fill_at(ctx, j, tape, spread, allout_idx)
        if f is None:
            cinfo[ci, 0] = 5
            if skips is not None:
                skips[(entry, rule, SKIPS[5])] += 1
            continue
        e, b_in, hs_in, costs = f
        if used is not None:
            used.add(pk)
        cinfo[ci] = [0, e, b_in, hs_in, info["strike"], info["delta"]]
        xv = Exits(ctx, tape, e, allout_idx, b_in, hs_in, costs, side, stop_s)
        a, b, c, d = xv.grid()
        ex[ci, :NG], rs[ci, :NG], p1[ci, :NG], p2[ci, :NG] = a, b, c, d
        if ci < len(CONTRACTS):
            for sk in range(6):
                ex[ci, R3_BASE + sk], rs[ci, R3_BASE + sk], p1[ci, R3_BASE + sk], p2[ci, R3_BASE + sk] = xv.r3(sk)
            ex[ci, R4_V], rs[ci, R4_V], p1[ci, R4_V], p2[ci, R4_V] = xv.r4()
    return cinfo, ex, rs, p1, p2


def grid_day(ctx, tapes, spread, ents=ENTRIES, tabs=None, skips=None, calib_rows=None, twin_seed=TWIN_SEED, feats=True,
             picks=None, extra_keys=()):
    """Every entry's signals (and their random-side twins when tabs has "twin") on one (symbol, day) into tabs. The day's
    contract picks (these signals' and extra_keys) are made first in one batch (prefetch_picks)."""
    allout_idx = EARLY_ALLOUT if ctx.early else ALLOUT["15:25"]
    picks = {} if picks is None else picks
    used = set()
    o0 = session_open(ctx)
    todo, keys = [], set(extra_keys)
    for entry in ents:
        sigs = entry_signals(ctx, entry)
        kinds = [("real", sigs)] + ([("twin", twin_signals(sigs, twin_seed, ctx.sym, ctx.day))] if "twin" in tabs else [])
        for kind, ss in kinds:
            for sg in ss:
                todo.append((entry, kind, sg))
                if sg.idx + 1 < min(NO_NEW_AFTER, allout_idx) and not math.isnan(ctx.c[sg.idx]):
                    keys.update((sg.idx, sg.side, r) for r in EVAL_CONTRACTS)
    prefetch_picks(ctx, tapes, keys, picks)
    fcache = {}
    for entry, kind, sg in todo:
        cinfo, ex, rs, p1, p2 = eval_signal(ctx, sg, tapes, spread, allout_idx, picks,
                                            skips if kind == "real" else None, entry, used if kind == "real" else None)
        oside = sg.info.get("orig_side", sg.side)
        meta = {"entry": ENTRIES.index(entry), "day": ctx.day.toordinal(), "idx": sg.idx, "side": 1 if sg.side == "C" else -1,
                "oside": 1 if oside == "C" else -1, "agree": agrees(ctx, sg.side, sg.idx, o0), "price": sg.price,
                "invalid": np.nan if sg.invalid is None else float(sg.invalid)}
        if feats and kind == "real":
            fk = (sg.idx, sg.side)
            if fk not in fcache:
                fcache[fk] = _feat_row(ctx, sg.idx, sg.side)
            ft = fcache[fk]
        else:
            ft = [np.nan] * NF
        tabs[kind].add(meta, ft, cinfo, ex, rs, p1, p2)
    if calib_rows is not None:
        for (j, side, rule) in sorted(used):
            tape, info = picks[(j, side, rule)]
            if rule in NEW_KEYS_RULES and tape is not None:
                calib_rows.append({"symbol": ctx.sym, "day": ctx.day.isoformat(), "contract": info["symbol"], "signal_idx": j,
                                   "side": side, "rule": rule, "iv_est": info["iv"], "setup": "r10grid"})


# ---------------------------------------------------------------- the calibration for rules run 4 lacks (Builder's reading 7)
AF_RULE = "af153"
NEW_KEYS_RULES = ("d20-30t25", "d55-70t60")


def needs_new_key(calib, rule, side):
    try:
        MD.multiplier_for(calib, rule, side)
        return False
    except ValueError:
        return True


def extend_calibration(run4, rows, proxy):
    """run 4's calibration plus Amendment 5's method on this round's DEV picks for every rule|side run 4 cannot price."""
    new = MD.calibrate(rows, proxy)
    out = json.loads(json.dumps(run4 or {"keys": {}, "min_n": MD.MIN_CALIB}))
    out.setdefault("keys", {})
    added = {}
    for rule in NEW_KEYS_RULES + (AF_RULE,):
        for side in ("C", "P"):
            k = MD.calib_key(rule, side)
            if not needs_new_key(out, rule, side):
                continue
            s = new["keys"].get(k)
            if s:
                out["keys"][k] = dict(s, source="round 10 DEV calibration (Amendment 5's method)")
                added[k] = out["keys"][k]
            else:
                added[k] = {"n": 0, "ok": False, "source": "round 10 DEV calibration: no rows"}
    out["r10_added"] = added
    out["r10_rows_used"] = new.get("rows_used")
    return out


# ---------------------------------------------------------------- Addendum 15.3 as corrected by Addendum 16.2 (the framework)
AF_FIRST, AF_LAST, AF_LAST_FILL = 14, 149, 150
AF_ROC, AF_ATR5_MIN, AF_CONSEC = 0.0003, 0.20, 3
AF_EMA_FAST, AF_EMA_SLOW, AF_PRESEED = 5, 20, 30
AF_ATR_MULT, AF_MAX_OFFSET, AF_ALTS, AF_ZONE = 0.60, 4.50, 5, 0.003
AF_PMIN, AF_PMAX = 0.20, 10.00
AF_STOP, AF_TP, AF_ARM, AF_TRAIL = 0.50, 1.50, 1.20, 0.88
AF_SPY_MULT, AF_SPY_FLOOR = 0.75, 0.10
AF_COOLDOWN = 2                                      # next decision bar >= exit bar + 2 (entry 3 bars after the exit)
AF_RISK, AF_LOSS, AF_PROFIT, AF_WINS = 150.0, 300.0, 125.0, 3
AF_SYMBOLS = ("SPY", "QQQ")
AF_REASONS = ("HARD STOP", "PEAK TRAIL", "SPY STOP", "TARGET +50%", "ALL OUT")


def af_atr5d(series, day):
    """The published 5-day ATR: the mean high - low of the 5 prior daily bars, or None (cached on the series)."""
    cache = series.__dict__.setdefault("_af_atr5d", {})
    if day not in cache:
        prior = series.prior_days(day, 5)
        if len(prior) < 5:
            cache[day] = None
        else:
            d = series.daily.loc[prior]
            cache[day] = float((d["high"] - d["low"]).mean())
    return cache[day]


def _af_ema(prev, price, period):
    """The framework's EMA step (momentum.py): seeded with the first price."""
    k = 2.0 / (period + 1)
    return price if prev is None else price * k + prev * (1 - k)


def af_state(ctx):
    """The framework's momentum state at the end of each regular-hours bar of the day (cached on ctx), arrays of 390:
    ema5 / ema20 (seeded with the prior session's last 30 regular-hours closes, the live bot's preseed, then every bar of
    the day), green / red (consecutive-bar counters, reset per session: a green bar adds to green and zeroes red, a red bar the
    reverse, a doji leaves both), roc5 (close / the close 5 received bars back - 1), atr5 (the mean TRUE range of the last 5
    received bars; true range with the previous received bar's close, high - low for the session's first bar). A minute
    without a bar is never received: its values stay NaN / 0 and no decision is made on it."""
    st = getattr(ctx, "_af_state", None)
    if st is not None:
        return st
    n = data.N
    out = {k: np.full(n, np.nan) for k in ("ema5", "ema20", "roc5", "atr5")}
    out["green"], out["red"] = np.zeros(n, int), np.zeros(n, int)
    e5 = e20 = None
    prev = ctx.series.prior_days(ctx.day, 1)
    if prev:
        pc = ctx.series.rth[prev[0]][:, 3]
        for x in pc[~np.isnan(pc)][-AF_PRESEED:]:
            e5, e20 = _af_ema(e5, float(x), AF_EMA_FAST), _af_ema(e20, float(x), AF_EMA_SLOW)
    o, h, l, c = (np.asarray(a, float) for a in (ctx.o, ctx.h, ctx.l, ctx.c))
    closes, trs = [], []
    g = r = 0
    for i in range(n):
        if math.isnan(c[i]) or math.isnan(o[i]):
            continue
        ci = float(c[i])
        e5, e20 = _af_ema(e5, ci, AF_EMA_FAST), _af_ema(e20, ci, AF_EMA_SLOW)
        if ci > o[i]:
            g, r = g + 1, 0
        elif ci < o[i]:
            g, r = 0, r + 1
        hl = float(h[i] - l[i])
        trs.append(hl if not closes else max(hl, abs(float(h[i]) - closes[-1]), abs(float(l[i]) - closes[-1])))
        closes.append(ci)
        out["ema5"][i], out["ema20"][i], out["green"][i], out["red"][i] = e5, e20, g, r
        if len(closes) >= 6 and closes[-6] != 0:
            out["roc5"][i] = (ci - closes[-6]) / closes[-6]
        if len(trs) >= 5:
            out["atr5"][i] = sum(trs[-5:]) / 5
    ctx._af_state = out
    return out


def af_signal(ctx, j):
    """"C" / "P" / None at decision bar j (Addendum 16.2's direction and volatility conditions). A call needs close > session
    VWAP, EMA(5) > EMA(20), ROC5 >= +0.03%, at least 3 consecutive green bars and ATR5 >= $0.20; a put mirrors them."""
    st = af_state(ctx)
    c, vw, a5 = ctx.c[j], ctx.vwap[j], st["atr5"][j]
    if math.isnan(c) or math.isnan(vw) or math.isnan(a5) or math.isnan(st["roc5"][j]) or a5 < AF_ATR5_MIN:
        return None
    e5, e20, roc = st["ema5"][j], st["ema20"][j], st["roc5"][j]
    if c > vw and e5 > e20 and roc >= AF_ROC and st["green"][j] >= AF_CONSEC:
        return "C"
    if c < vw and e5 < e20 and roc <= -AF_ROC and st["red"][j] >= AF_CONSEC:
        return "P"
    return None


def af_strike(S, atr5d, side):
    """The target strike: Python round(S +/- min(0.60 x the 5-day ATR, $4.50)) on the $1 grid (strikes.py)."""
    off = min(AF_ATR_MULT * atr5d, AF_MAX_OFFSET)
    return round(round((S + off if side == "C" else S - off) / 1.0) * 1.0, 2)


def af_strikes(S, atr5d, side):
    """(target, the qualifying strikes nearest first): the target +/- 5 strikes are watched; a strike qualifies when it is out
    of the money (call K > S, put K < S) and within 0.3% of S (the activation zone, |K - S| / S <= 0.003)."""
    target = af_strike(S, atr5d, side)
    win = [round(target + k * 1.0, 2) for k in range(-AF_ALTS, AF_ALTS + 1)]
    ok = [K for K in win if ((K > S) if side == "C" else (K < S)) and abs(K - S) / S <= AF_ZONE]
    return target, sorted(ok, key=lambda K: (abs(K - S), K))


def af_contract(ctx, tapes, side, j, atr5d):
    """16.2's contract at decision bar j: the nearest out-of-the-money strike of the watched window within 0.3% of S (the
    decision bar's close), with a premium of $0.20-$10.00: (tape, info) or (None, reason). No fallback to a farther strike."""
    S = float(ctx.c[j])
    if atr5d is None:
        return None, "no 5-day ATR"
    _target, ks = af_strikes(S, atr5d, side)
    if not ks:
        return None, "no out-of-the-money strike within 0.3% in the watched window"
    K = ks[0]
    if tapes.mode == "real":
        sym = f"{ctx.sym}{ctx.day:%y%m%d}{side}{int(round(K * 1000)):08d}"
        tape = (tapes.real0 or {}).get(sym)
        if tape is None:
            return None, "no 0DTE contract at the strike"
    else:
        if tapes.ivp is None:
            return None, "MODELED: no IV proxy"
        try:
            m = MD.multiplier_for(tapes.calib, AF_RULE, side)[0]
        except ValueError as exc:
            return None, f"MODELED: {exc}"
        tape = tapes.md_day().tape(K, side, tapes.ivp * m)
    px = tape.last_close(j, contracts.MAX_AGE)
    if px is None:
        return None, "no price in the 5 minutes before the decision"
    if not AF_PMIN <= px <= AF_PMAX:
        return None, "premium outside $0.20-$10.00"
    return tape, {"symbol": tape.symbol, "strike": K, "px": px, "S": S, "j": j, "side": side}


def af_iv(info):
    """BS-EST (iv, delta) of 15.3's contract at its decision (contracts.pick's convention), solved only for a taken trade."""
    if "iv" not in info:
        iv, dl = bs.iv_delta_v(np.array([info["px"]]), info["S"], np.array([info["strike"]]), bs.t_years(390 - (info["j"] + 1)),
                               np.array([info["side"] == "C"]))
        info["iv"], info["delta"] = float(iv[0]), round(float(dl[0]), 3)
    return info["iv"], info["delta"]


def af_exit(ctx, tape, e, A, b_in, hs_in, costs, side, spy_stop):
    """15.3's exits: (exit bar, reason, p1, p2) or None (VOID)."""
    xv = Exits(ctx, tape, e, A, b_in, hs_in, costs, side, None)
    d, L = xv.debit, xv.L
    pp = xv.peak_prev
    trail = np.where(pp >= AF_ARM * d, AF_TRAIL * pp, -np.inf)
    lvl = np.maximum(AF_STOP * d, trail)
    kps = _fh(xv.lo <= lvl)
    sc = ctx.c[e:A]
    kls = _fh(~np.isnan(sc) & ((sc < spy_stop) if side == "C" else (sc > spy_stop)))
    ktg = _fh(xv.hi >= AF_TP * d)
    kb, typ = BIG, None
    for k, t in ((kps, 0), (kls, 1), (ktg, 2)):
        if k < L and k < kb:
            kb, typ = k, t
    if typ == 0:
        x, basis = xv.stop_at(kps, float(lvl[kps]))
        why, st = ("PEAK TRAIL" if trail[kps] > AF_STOP * d else "HARD STOP"), True
    elif typ == 1:
        x, basis = xv.next_open(e + kls + 1)
        why, st = "SPY STOP", True
    elif typ == 2:
        x, basis = xv.target_at(ktg, AF_TP * d)
        why, st = "TARGET +50%", False
    else:
        x, basis = xv.next_open(A)
        why, st = "ALL OUT", False
    if x is None:
        return None
    c1, c2 = xv._legs_pnl([xv.leg(x, basis, st)])
    return x, why, c1 / 100.0, c2 / 100.0


def af_size(debit):
    return max(1, int(math.floor(AF_RISK / (debit * (1 - AF_STOP) * MULT))))


def af_signals(ctx):
    """{decision bar: "C" / "P"} of the day (af_signal on bars 14..149)."""
    out = {}
    for j in range(AF_FIRST, AF_LAST + 1):
        s = af_signal(ctx, j)
        if s is not None:
            out[j] = s
    return out


def af_day(ctx, tapes, spread, variant, gated, contract=AF_RULE, twin_seed=None, picks=None, calib_rows=None, sigs=None):
    """One symbol-day of the framework's bot (15.3 as corrected by 16.2): [trade rows]. contract AF_RULE (16.2's activation-zone
    strike) or "d55-70t60" (R2: the strike rule swapped, the premium band kept as an entry condition). sigs: af_signals(ctx)."""
    allout_idx = EARLY_ALLOUT if ctx.early else ALLOUT["15:25"]
    atr5d = af_atr5d(ctx.series, ctx.day)
    sigs = af_signals(ctx) if sigs is None else sigs
    rows = []
    next_ok, locked, day_pnl, wins = AF_FIRST, False, 0.0, 0
    for j in range(AF_FIRST, AF_LAST + 1):
        if locked or j + 1 >= allout_idx or j + 1 >= NO_NEW_AFTER:
            break
        if j < next_ok:
            continue
        rs = sigs.get(j)
        if rs is None:
            continue
        side = twin_side(twin_seed, ctx.sym, ctx.day, j) if twin_seed is not None else rs
        if contract == AF_RULE:
            tape, info = af_contract(ctx, tapes, side, j, atr5d)
        else:
            pk = (j, side, contract)
            if picks is not None and pk in picks:
                tape, info = picks[pk]
            else:
                r = tapes.pool(contract, side, float(ctx.c[j]))
                tape, info = (None, r) if r else contracts.pick(ctx, side, j, contract)
                if picks is not None:
                    picks[pk] = (tape, info)
        if tape is None or not AF_PMIN <= info["px"] <= AF_PMAX:          # 16.2: the premium band is an entry condition
            continue
        f = fill_at(ctx, j, tape, spread, allout_idx, last=AF_LAST_FILL)
        if f is None:
            continue
        e, b_in, hs_in, costs = f
        buf = max(AF_SPY_FLOOR, AF_SPY_MULT * float(af_state(ctx)["atr5"][j]))
        S = float(ctx.c[j])
        res = af_exit(ctx, tape, e, allout_idx, b_in, hs_in, costs, side, S - buf if side == "C" else S + buf)
        if res is None:
            continue
        x, why, p1, p2 = res
        debit = b_in + hs_in
        qty = af_size(debit)
        iv, dl = af_iv(info) if contract == AF_RULE else (info["iv"], info["delta"])
        if calib_rows is not None and contract == AF_RULE and twin_seed is None:
            calib_rows.append({"symbol": ctx.sym, "day": ctx.day.isoformat(), "contract": info["symbol"], "signal_idx": j, "side": side,
                               "rule": AF_RULE, "iv_est": iv, "setup": "r10 af153"})
        rows.append({"variant": variant, "symbol": ctx.sym, "day": ctx.day.isoformat(), "side": side, "signal_side": rs, "signal_idx": j,
                     "entry_idx": e, "exit_idx": x, "entry_time": _t(e), "exit_time": _t(x), "exit_reason": why, "pnl": p1, "pnl_2x": p2,
                     "qty": qty, "pnl_sized": round(p1 * qty, 2), "debit": round(debit * MULT + FEE, 2), "strike": info["strike"],
                     "contract": info["symbol"], "delta_est": dl, "gated": gated, "hour": f"{(570 + e) // 60:02d}:00"})
        next_ok = x + AF_COOLDOWN
        if gated:
            day_pnl += p1 * qty
            wins = wins + 1 if p1 * qty > 0 else 0
            if day_pnl <= -AF_LOSS or day_pnl >= AF_PROFIT or wins >= AF_WINS:
                locked = True
    return rows


def _t(i):
    m = 570 + int(i)
    return f"{m // 60:02d}:{m % 60:02d}"


# ---------------------------------------------------------------- R1 pm_inside_break (Addendum 15.5)
R1_FIRST, R1_LAST = entries.DESK_FIRST, entries.ORB_CUTOFF
R1_OUT, R1_EARLY_OUT = 384, 204
R1_SYMBOLS = ("SPY", "QQQ")
R1_CONTRACTS = ("d40-55t45", "d55-70t60")


def r1_setup(ctx):
    """{"qualifies", "pmh", "pml", "side", "idx", "price", "exits": [5-minute decision bars back inside]} or None."""
    pre = ctx.series.pre.get(ctx.day)
    prev = ctx.series.prev_day(ctx.day)
    if not pre or prev is None:
        return None
    pmh, pml = pre
    q = pmh <= prev["high"] and pml >= prev["low"]
    sig = None
    for j in range(R1_FIRST, min(R1_LAST, ctx.close_idx - 2) + 1):
        c = ctx.c[j]
        if math.isnan(c):
            continue
        if c > pmh:
            sig = ("C", j)
            break
        if c < pml:
            sig = ("P", j)
            break
    out = {"qualifies": bool(q), "pmh": float(pmh), "pml": float(pml), "side": None}
    if sig is None:
        return out
    side, j = sig
    inside = []
    b5 = ctx.b5
    if b5 is not None:
        for qd in range(78):
            m = 5 * qd + 4
            c5 = b5[qd, 3]
            if m > j and not math.isnan(c5) and pml <= c5 <= pmh:
                inside.append(m)
    last = ctx.c[:ctx.close_idx]
    ok = np.where(~np.isnan(last))[0]
    close = float(last[ok[-1]]) if len(ok) else math.nan
    beyond = (close > pmh) if side == "C" else (close < pml)
    out.update(side=side, idx=j, price=float(ctx.c[j]), exits=inside, day_close=close, beyond=bool(beyond))
    return out


def r1_shares(ctx, st, src):
    """R1 in shares (Part A's costs, $10,000, exit at the next bar's open or the close of the bar finishing 15:55)."""
    xb = R1_EARLY_OUT if ctx.early else R1_OUT
    j = st["idx"]
    if j >= xb:
        return None
    k = shares.fill_bar(ctx, j, xb)
    sh = shares._shares(shares.NOTIONAL, st["price"])
    if k is None or sh <= 0:
        return None
    bk = shares.Book(ctx, "r1_shares" if st["qualifies"] else "r1_shares_ctl", src)
    bk.open(1 if st["side"] == "C" else -1, j, k, sh, shares.NOTIONAL)
    for m in st["exits"]:
        if k <= m < xb:
            kx = shares.fill_bar(ctx, m, xb, wait=xb)
            if kx is not None:
                bk.close(kx, float(ctx.o[kx]), "PM RANGE RE-ENTRY (5-minute close)")
                return bk.out[0]
    kc, px = shares._close_out(ctx, xb, k - 1)
    if kc is None:
        kc, px = k, float(ctx.o[k])
    bk.close(kc, px, f"CLOSE {'12:55' if ctx.early else '15:55'} bar")
    return bk.out[0]


def r1_option(ctx, st, tapes, spread, rule, side, picks):
    """R1's option twin on one contract rule: a trade row or None."""
    from .optpass import signal_exit
    allout_idx = EARLY_ALLOUT if ctx.early else ALLOUT["15:25"]
    j = st["idx"]
    if j + 1 >= allout_idx or j + 1 >= NO_NEW_AFTER:
        return None
    pk = (j, side, rule)
    if pk not in picks:
        r = tapes.pool(rule, side, float(ctx.c[j]))
        picks[pk] = (None, r) if r else contracts.pick(ctx, side, j, rule)
    tape, info = picks[pk]
    if tape is None:
        return None
    f = fill_at(ctx, j, tape, spread, allout_idx)
    if f is None:
        return None
    e, b_in, hs_in, costs = f
    exits = {m: ("PM RANGE RE-ENTRY", False, False) for m in st["exits"] if m >= e}
    r = signal_exit(tape, j, e, allout_idx, b_in + hs_in, exits, None)
    if r is None:
        return None
    x, basis, why, is_stop, _flip = r
    legs = [(1.0, basis, costs.hs(basis, x), is_stop)]
    return {"symbol": ctx.sym, "day": ctx.day.isoformat(), "side": side, "signal_idx": j, "entry_idx": e, "exit_idx": x,
            "entry_time": _t(e), "exit_time": _t(x), "exit_reason": why, "pnl": round(fills_pnl(b_in, hs_in, legs, 1), 2),
            "pnl_2x": round(fills_pnl(b_in, hs_in, legs, 2), 2), "debit": round((b_in + hs_in) * MULT + FEE, 2),
            "contract": info["symbol"], "strike": info["strike"]}


def r1_day(ctx, tapes, spread, src, picks, twin_seed=TWIN_SEED):
    """R1 on one (symbol, day): {"claim": row or None, "shares": [rows], "options": [rows]}."""
    st = r1_setup(ctx)
    out = {"claim": None, "shares": [], "options": []}
    if st is None:
        return out
    out["claim"] = {"symbol": ctx.sym, "day": ctx.day.isoformat(), "_src": src, "qualifies": st["qualifies"], "break": st["side"],
                    "beyond": st.get("beyond")}
    if st["side"] is None:
        return out
    t = r1_shares(ctx, st, src)
    if t is not None:
        t["qualifies"] = st["qualifies"]
        out["shares"].append(t)
    group = "qual" if st["qualifies"] else "ctl"
    tw = twin_side(twin_seed, ctx.sym, ctx.day, st["idx"])
    for rule in R1_CONTRACTS:
        for kind, side in (("real", st["side"]), ("twin", tw)):
            r = r1_option(ctx, st, tapes, spread, rule, side, picks)
            if r is not None:
                r.update(variant=f"r1_{rule}_{group}" + ("_twin" if kind == "twin" else ""), rule=rule, group=group, kind=kind,
                         qualifies=st["qualifies"], _src=src)
                out["options"].append(r)
    return out


# ---------------------------------------------------------------- data needs (wired into the round 10 pull by the integrator)
NEED_REACH_PCT = 0.02          # >= the 0DTE |delta| 0.20 distance at a 60% IV from 09:45, and n1 |delta| 0.40 over 3 days
NEED_REACH_MIN = 2.0           # $2: two $1 strikes past the range for a low-priced underlying (16.2's strike is within 0.3%)


def needed_option_contracts(under, day, day_bars, band=0.03, expiry=None):
    """OCC symbols a round-10 pick on `day` could need that the existing pull (pull_alpaca.symbols_for_day with `band`: every
    $1 strike within band of the open widened to the day's range) does NOT fetch. day_bars: the day's stock 1-minute bars
    (ts, o, h, l, c; regular hours used). expiry: the contracts' expiry (default `day`, 0DTE; the next listed expiry for
    n1d40-55t45). Reach: every strike within max($2, 2% of the price) of the day's regular-hours range: a 0DTE |delta| 0.20
    strike (d20-30t25's far edge) sits 0.84 sd of the rest-of-day move from the price, under 2% for an IV up to about 85% from
    09:45; n1d40-55t45 (|delta| >= 0.40) stays within 2% over a 3-day weekend at that IV; d55-70t60 is nearer; the framework's
    strike (Addendum 16.2) is within 0.3% of the price. On a day whose range stays within about 1% of the open the list is
    empty (the +/-3% band holds every round-10 contract); on a big-move day it lists the few strikes beyond the day's extremes
    that a d20-30t25 pick near the high or low could need (without them such a pick finds no strike in its band and is
    skipped, counted). The round 10 pull tool calls it per DEV day and fetches what it returns."""
    import pull_alpaca as PA
    expiry = expiry or day
    t = day_bars["ts"]
    hm = t.dt.hour * 60 + t.dt.minute
    r = day_bars[(hm >= 570) & (hm < 960)]
    if not len(r):
        return []
    hi, lo = float(r["h"].max()), float(r["l"].min())
    reach = max(NEED_REACH_MIN, NEED_REACH_PCT * hi)
    have = {s[-9:] for s in PA.symbols_for_day(under, day, day_bars, band)}
    out = []
    for k in range(int(math.floor(lo - reach)), int(math.ceil(hi + reach)) + 1):
        if k <= 0:
            continue
        for side in ("C", "P"):
            tail = f"{side}{k * 1000:08d}"
            if tail not in have:
                out.append(f"{under}{expiry:%y%m%d}{tail}")
    return out


# ---------------------------------------------------------------- stage 1: chunks (resumable)
def code_version():
    root = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for name in ("r10grid.py", "entries.py", "contracts.py", "fills.py", "modeled.py", "optpass.py", "sim.py", "features.py",
                 "data.py", "bs.py", "spread.py", "daytype.py", "shares.py"):
        p = root / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def chunk_days(series, period, year):
    a, b = periods.HIST if period == "HIST" else periods.DEV
    out = [d for d in series.days if a <= d <= b and d.year == year]
    for d in out:
        check_day(d)
    return out


def chunk_years(period):
    a, b = periods.HIST if period == "HIST" else periods.DEV
    return list(range(a.year, b.year + 1))


def _pack_json(obj):
    return np.frombuffer(gzip.compress(json.dumps(obj, sort_keys=True, default=str).encode()), dtype=np.uint8)


def _unpack_json(arr):
    return json.loads(gzip.decompress(np.asarray(arr, np.uint8).tobytes()).decode())


def compute_chunk(series, period, year, root=None, calib=None, aux=None, spread=None, ents=ENTRIES, progress=None,
                  limit_days=None, do_r1=True, do_af=True):
    """One (period, symbol, year) chunk: the grid tables (real; DEV also the twin), R1 and 15.3 rows, DEV calibration rows."""
    spread = spread or SP.SpreadModel()
    mode = "modeled" if period == "HIST" else "real"
    if mode == "modeled" and calib is None:
        raise ValueError("HIST (MODELED) needs the calibration")
    sym = series.sym
    days = chunk_days(series, period, year)
    if limit_days:
        days = days[:limit_days]
    tabs = {"real": Table()}
    if period == "DEV":
        tabs["twin"] = Table()
    skips, calib_rows = Counter(), ([] if period == "DEV" else None)
    r1 = {"claim": [], "shares": [], "options": []}
    af = []
    odays = option_days_r10(sym, root) if mode == "real" else None
    ndays = option_days_r10(sym, root, "next") if mode == "real" else None
    t0 = time.time()
    for n, d in enumerate(days):
        ctx = data.DayContext(series, d, {}, spread, aux=aux)
        ivp = MD.iv_proxy(series, d) if mode == "modeled" else None
        tapes = Tapes10(ctx, mode, root, odays, ndays, calib, ivp)
        picks, extra = {}, set()
        if do_r1 and sym in R1_SYMBOLS:
            st = r1_setup(ctx)
            if st and st.get("side"):
                for rule in R1_CONTRACTS:
                    extra.add((st["idx"], st["side"], rule))
                    extra.add((st["idx"], twin_side(TWIN_SEED, sym, d, st["idx"]), rule))
        afs = af_signals(ctx) if (do_af and sym in AF_SYMBOLS) else {}
        for j, sd in afs.items():
            extra.add((j, sd, R2_CONTRACT))
            if period == "DEV":
                extra.add((j, twin_side(TWIN_SEED, sym, d, j), R2_CONTRACT))
        grid_day(ctx, tapes, spread, ents, tabs, skips, calib_rows, picks=picks, extra_keys=extra)
        if do_r1 and sym in R1_SYMBOLS:
            o = r1_day(ctx, tapes, spread, period, picks)
            if o["claim"]:
                r1["claim"].append(o["claim"])
            r1["shares"] += o["shares"]
            r1["options"] += o["options"]
        if do_af and sym in AF_SYMBOLS:
            for variant, gated, con, tw in (("af153", True, AF_RULE, None), ("af153_nogate", False, AF_RULE, None),
                                            ("af153_r2", True, R2_CONTRACT, None), ("af153_r2_nogate", False, R2_CONTRACT, None)) + \
                    ((("af153_twin", True, AF_RULE, TWIN_SEED), ("af153_r2_twin", True, R2_CONTRACT, TWIN_SEED)) if period == "DEV" else ()):
                af += af_day(ctx, tapes, spread, variant, gated, con, tw, picks, calib_rows if variant == "af153" else None, afs)
        if progress and (n % 50 == 0 or n == len(days) - 1):
            progress(f"  r10 grid {period} {sym} {year}: {d} ({n + 1}/{len(days)} sessions, {time.time() - t0:.0f}s)")
    for r in r1["shares"]:
        r["_src"] = period
    for r in af:
        r["_src"] = period
    arrays = {}
    for k, tb in tabs.items():
        arrays.update(tb.arrays(f"{k}_"))
    rows = {"r1": r1, "af": af, "calib": calib_rows or [], "skips": [[list(k), v] for k, v in sorted(skips.items())],
            "days": [d.isoformat() for d in days]}
    return arrays, rows


def chunk_path(cache, period, sym, year):
    return Path(cache) / f"{period}_{sym}_{year}.npz"


def chunk_meta(period, sym, year, calib_sha=None, spread=None, limit_days=None, ents=ENTRIES):
    return {"version": code_version(), "period": period, "symbol": sym, "year": year, "calib_sha": calib_sha if period == "HIST" else None,
            "spread": (spread or SP.SpreadModel()).label, "entries": list(ents), "contracts": list(EVAL_CONTRACTS), "nv": NV,
            "limit_days": limit_days}


def save_chunk(path, meta, arrays, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, _meta=_pack_json(meta), _rows=_pack_json(rows), **arrays)
    tmp.replace(path)


def load_chunk(path, meta=None):
    """(meta, arrays, rows) or None when missing or made with other code / inputs."""
    path = Path(path)
    if not path.exists():
        return None
    with np.load(path, allow_pickle=False) as z:
        m = _unpack_json(z["_meta"])
        if meta is not None and m != meta:
            return None
        arrays = {k: z[k] for k in z.files if not k.startswith("_")}
        rows = _unpack_json(z["_rows"])
    return m, arrays, rows


def ensure_chunk(cache, series, period, year, calib_sha=None, log=None, **kw):
    """Load the chunk if it exists with the same meta, else compute and save it (restart-safe). Returns its path."""
    meta = chunk_meta(period, series.sym, year, calib_sha, kw.get("spread"), kw.get("limit_days"), kw.get("ents", ENTRIES))
    p = chunk_path(cache, period, series.sym, year)
    if p.exists():
        with np.load(p, allow_pickle=False) as z:
            if _unpack_json(z["_meta"]) == meta:
                if log:
                    log(f"  r10 grid {period} {series.sym} {year}: reused {p.name}")
                return p
    arrays, rows = compute_chunk(series, period, year, progress=log, **kw)
    save_chunk(p, meta, arrays, rows)
    return p


# ---------------------------------------------------------------- stage 2: replay
class Agg:
    """Per (entry, cell, bucket) aggregates, plus DEV daily P/L per cell."""

    def __init__(self, dev_days=None):
        self.a = {e: np.zeros((NCELL, NB, NAGG), np.int64) for e in ENTRIES}
        self.dev_idx = {d: i for i, d in enumerate(dev_days or [])}
        self.daily = {e: np.zeros((NCELL, len(self.dev_idx)), np.int64) for e in ENTRIES} if dev_days else None


def _add(agg, idx, b, c1, c2):
    a = agg[idx, b]
    a[:, 0] += 1
    a[:, 1] += c1 > 0
    a[:, 2] += c1 < 0
    a[:, 3] += np.where(c1 > 0, c1, 0)
    a[:, 4] += np.where(c1 < 0, c1, 0)
    a[:, 5] += np.where(c2 > 0, c2, 0)
    a[:, 6] += np.where(c2 < 0, c2, 0)
    agg[idx, b] = a


def replay_all(arrays, prefix, agg, daily=None, dev_idx=None):
    """Every cell of every entry over one chunk table (in place into agg {entry: (NCELL, NB, NAGG)})."""
    ent = arrays[f"{prefix}entry"]
    if not len(ent):
        return
    day, idx, agree = arrays[f"{prefix}day"], arrays[f"{prefix}idx"], arrays[f"{prefix}agree"]
    EX, P1, P2 = arrays[f"{prefix}ex"], arrays[f"{prefix}p1"], arrays[f"{prefix}p2"]
    for k, e in enumerate(ENTRIES):
        sel = np.nonzero(ent == k)[0]
        last = np.full(NCELL, -1, np.int64)
        cur = None
        A = agg[e]
        D = daily[e] if daily is not None else None
        for s in sel:
            d = int(day[s])
            if d != cur:
                cur = d
                last[:] = -1
                iso = date.fromordinal(d).isoformat()
                b = bucket_of(iso)
                di = dev_idx.get(iso) if dev_idx is not None else None
            exc = EX[s][CELL_C, CELL_V].astype(np.int64)
            ok = exc >= 0
            if not agree[s]:
                ok &= ~CELL_F
            take = np.nonzero(ok & (int(idx[s]) >= last))[0]
            if not len(take):
                continue
            last[take] = exc[take]
            c1 = P1[s][CELL_C[take], CELL_V[take]].astype(np.int64)
            c2 = P2[s][CELL_C[take], CELL_V[take]].astype(np.int64)
            _add(A, take, b, c1, c2)
            if D is not None and di is not None:
                D[take, di] += c1


def replay_one(arrays, prefix, entry_k, ci, vi, trend_on, sym, label, mult_debit=1):
    """One virtual cell (contract ci, variant vi, trend filter) over a chunk table: [trade rows]."""
    ent = arrays[f"{prefix}entry"]
    sel = np.nonzero(ent == entry_k)[0]
    day, idx, agree, side = arrays[f"{prefix}day"], arrays[f"{prefix}idx"], arrays[f"{prefix}agree"], arrays[f"{prefix}side"]
    EX, RSa, P1, P2 = arrays[f"{prefix}ex"], arrays[f"{prefix}rs"], arrays[f"{prefix}p1"], arrays[f"{prefix}p2"]
    CI, FT = arrays[f"{prefix}cinfo"], arrays[f"{prefix}feat"]
    out, last, cur = [], -1, None
    for s in sel:
        d = int(day[s])
        if d != cur:
            cur, last = d, -1
        x = int(EX[s, ci, vi])
        if x < 0 or (trend_on and not agree[s]) or int(idx[s]) < last:
            continue
        last = x
        ci_row = CI[s, ci]
        e = int(ci_row[1])
        row = {"variant": label, "entry": ENTRIES[entry_k], "symbol": sym, "day": date.fromordinal(d).isoformat(),
               "side": "C" if side[s] > 0 else "P", "signal_idx": int(idx[s]), "entry_idx": e, "exit_idx": x, "entry_time": _t(e),
               "exit_time": _t(x), "exit_reason": REASONS[int(RSa[s, ci, vi])], "pnl": int(P1[s, ci, vi]) / 100.0,
               "pnl_2x": int(P2[s, ci, vi]) / 100.0, "debit": round(((ci_row[2] + ci_row[3]) * MULT + FEE) * mult_debit, 2),
               "strike": float(ci_row[4]), "delta_est": float(ci_row[5]), "contract_rule": EVAL_CONTRACTS[ci]}
        for k, name in enumerate(FEAT_COLS):
            v = FT[s, k]
            row[name] = None if math.isnan(v) else float(v)
        out.append(row)
    return out


def agg_window(a, win):
    return a[..., WIN_BUCKETS[win], :].sum(axis=-2)


def _pf_c(pos, neg):
    if neg < 0:
        return round(pos / -neg, 3)
    return math.inf if pos > 0 else None


def agg_stats(v):
    """Stats of one aggregate vector (n, wins, losses, sum wins, sum losses, 2x sums) in dollars."""
    n, nw, nl, sp, sn, sp2, sn2 = (int(x) for x in v)
    out = {"trades": n}
    if not n:
        return out
    out.update({"win_rate": round(nw / n, 3), "avg_win": round(sp / nw / 100, 2) if nw else None,
                "avg_loss": round(sn / nl / 100, 2) if nl else None, "expectancy": round((sp + sn) / n / 100, 2),
                "pf": _pf_c(sp, sn), "pf_2x": _pf_c(sp2, sn2), "total": round((sp + sn) / 100, 2), "total_2x": round((sp2 + sn2) / 100, 2)})
    return out


def _pf_key(v):
    """Exact sort key for PF from integer cents: (no-loss rank, pos, -neg) comparisons through fractions."""
    sp, sn = int(v[3]), int(v[4])
    return (1, sp, 1) if sn == 0 and sp > 0 else (0, sp, -sn)


def _pf_gt(a, b):
    """PF(a) > PF(b) exactly (a, b from _pf_key)."""
    if a[0] != b[0]:
        return a[0] > b[0]
    if a[0] == 1:
        return False
    return a[1] * b[2] > b[1] * a[2]


def choose(disc):
    """disc: (NCELL, NAGG) discovery aggregates. The highest PF among cells with >= MIN_DISC trades (exact PF, a PF with no
    loss first); ties: more trades, then the cell listed first. Returns the cell index or None."""
    best = None
    for k in range(NCELL):
        v = disc[k]
        n = int(v[0])
        if n < MIN_DISC or (int(v[3]) == 0 and int(v[4]) == 0):
            continue
        pk = _pf_key(v)
        if best is None:
            best = (k, pk, n)
            continue
        bk, bpk, bn = best
        if _pf_gt(pk, bpk) or (not _pf_gt(bpk, pk) and n > bn):
            best = (k, pk, n)
    return None if best is None else best[0]


def frozen_doc(choices, disc_stats, inputs=None):
    return {"amendment": "SPRINT_PLAN Amendment 15 with Amendment 16's stop 'none' (1,080 cells per entry, 7,560 in all)",
            "inputs": inputs, "code_version": code_version(),
            "chosen_on": f"HIST {DISC[0]}..{DISC[1]} (MODELED) only",
            "rule": f"the highest PF among cells with at least {MIN_DISC} discovery trades (PF compared exactly; no loss ranks "
                    "first); ties: more trades, then the cell listed first",
            "grid": {"stops": [s for s, _x in STOPS], "targets": [t for t, _x in TARGETS], "trails": list(TRAILS),
                     "caps": [c for c, _x in CAPS], "contracts": list(CONTRACTS), "trend": list(TRENDS), "cells_per_entry": NCELL},
            "entries": {e: ({"cell": cell_id(k), "cell_index": int(k), "text": cell_text(k), "discovery": disc_stats[e]}
                            if k is not None else {"cell": None, "why": f"no cell kept {MIN_DISC} trades in {DISC[0]}..{DISC[1]}"})
                        for e, k in choices.items()}}


def write_frozen(path, doc):
    """Write the frozen choice JSON; an existing file must hold the same choice (restart safety)."""
    path = Path(path)
    text = json.dumps(doc, indent=1, sort_keys=True, default=str)
    if path.exists():
        old = json.loads(path.read_text())
        if old.get("inputs") is not None and doc.get("inputs") is not None and old["inputs"] != doc["inputs"]:
            raise RuntimeError(f"{path} was frozen from other inputs ({len(old['inputs'])} chunks: {', '.join(old['inputs'][:6])}...); "
                               "the choice is frozen (delete the file only to rebuild from scratch)")
        if {e: v.get("cell") for e, v in old.get("entries", {}).items()} != {e: v.get("cell") for e, v in doc["entries"].items()}:
            raise RuntimeError(f"{path} holds a different frozen choice; the choice is frozen (delete the file only to rebuild "
                               "from scratch)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")
    return hashlib.sha256((text + "\n").encode()).hexdigest()


# ---------------------------------------------------------------- readouts
def ostats(rows):
    from . import round8
    return round8.ostats_a(round8._as_a(rows))


def win_rows(rows, w):
    a, b = WINDOWS[w] if isinstance(w, str) else w
    return [r for r in rows if a <= str(r["day"])[:10] <= b]


def holdout1(rows):
    from . import round8
    return round8.holdout1_d(win_rows(rows, "h1"))


def holdout2(rows, twin_rows):
    s, t = ostats(win_rows(rows, "h2")), ostats(win_rows(twin_rows, "h2"))
    pfr = lambda x: -1.0 if x is None else float(x)
    se, te = s.get("expectancy"), t.get("expectancy")
    ch = [(f"H2: at least 60 trades ({s['trades']})", s["trades"] >= 60), (f"H2: PF >= 1.25 ({s.get('pf')})", pfr(s.get("pf")) >= 1.25),
          (f"H2: PF 2x > 1.0 ({s.get('pf_2x')})", pfr(s.get("pf_2x")) > 1.0),
          (f"H2: expectancy above the random-side twin's, seed {TWIN_SEED} ({se} vs {te})", se is not None and (te is None or se > te))]
    return {"stats": s, "twin": t, "checks": ch, "pass": all(ok for _n, ok in ch)}


def first_fail(checks):
    for n, ok in checks:
        if not ok:
            return n
    return None


def addon_verdict(name, rows, twin_rows, base_rows, kind):
    """R2 (kind "pf"), R3 / R4 (kind "exp", R3 against the frozen cell x 3): Amendment 15's bars plus the comparison."""
    h1, h2 = holdout1(rows), holdout2(rows, twin_rows)
    b1, b2 = ostats(win_rows(base_rows, "h1")), ostats(win_rows(base_rows, "h2"))
    m = 3 if name.startswith("R3") else 1
    ch = []
    for w, s, b in (("H1", h1["stats"], b1), ("H2", h2["stats"], b2)):
        if kind == "pf":
            x, y = s.get("pf"), b.get("pf")
            ok = x is not None and (y is None or float(x) > float(y))
            ch.append((f"{w}: PF above the original cell's ({x} vs {y})", ok))
        else:
            x, y = s.get("expectancy"), (None if b.get("expectancy") is None else round(b["expectancy"] * m, 2))
            ok = x is not None and (y is None or x > y)
            ch.append((f"{w}: P/L per trade above the frozen cell's{' x 3' if m == 3 else ''} ({x} vs {y})", ok))
    checks = h1["checks"] + h2["checks"] + ch
    return {"holdout1": h1, "holdout2": h2, "base_h1": b1, "base_h2": b2, "checks": checks, "pass": all(ok for _n, ok in checks),
            "why_not": first_fail(checks)}


def terciles(rows, feat):
    vals = np.array([r[feat] for r in rows if r.get(feat) is not None], float)
    if len(vals) < 3:
        return None
    lo, hi = (float(x) for x in np.quantile(vals, [1 / 3, 2 / 3]))
    g = {"low": [], "mid": [], "high": []}
    for r in rows:
        v = r.get(feat)
        if v is None:
            continue
        g["low" if v <= lo else "high" if v >= hi else "mid"].append(r)
    return {"cuts": [round(lo, 4), round(hi, 4)], "groups": {k: ostats(v) for k, v in g.items()}}


def vixy_split(rows):
    out = {}
    for sym in ("SPY", "QQQ"):
        g = {"low (<= 1/3)": [], "mid": [], "high (> 2/3)": [], "no VIXY": []}
        for r in rows:
            if r["symbol"] != sym:
                continue
            v = r.get("f_vixy_pctl")
            k = "no VIXY" if v is None else "low (<= 1/3)" if v <= 1 / 3 else "high (> 2/3)" if v > 2 / 3 else "mid"
            g[k].append(r)
        out[sym] = {k: ostats(v) for k, v in g.items()}
    return out


def share_pf_gt1(a2):
    """a2: (N, NAGG) aggregates of a set of cells: (cells with PF > 1, cells with trades)."""
    n_tr = int((a2[:, 0] > 0).sum())
    pos, neg = a2[:, 3], a2[:, 4]
    gt = int(((neg < 0) & (pos > -neg) | (neg == 0) & (pos > 0)).sum())
    return gt, n_tr


def grid_summary(A):
    """Per window: the share of cells with PF > 1 (all, by each dimension's level) and the stop x target heat map share."""
    out = {}
    for w in WINDOWS:
        a = agg_window(A, w)
        gt, n = share_pf_gt1(a)
        dims = {}
        for di, (name, levels) in enumerate((("stop", [s for s, _x in STOPS]), ("target", [t for t, _x in TARGETS]),
                                             ("trail", list(TRAILS)), ("cap", [c for c, _x in CAPS]), ("contract", list(CONTRACTS)),
                                             ("trend", list(TRENDS)))):
            dims[name] = {}
            for li, lv in enumerate(levels):
                sel = [k for k, c in enumerate(CELLS) if c[di] == li]
                g, nn = share_pf_gt1(a[sel])
                dims[name][lv] = [g, nn]
        heat = {}
        for s, (sn, _x) in enumerate(STOPS):
            heat[sn] = {}
            for t, (tn, _y) in enumerate(TARGETS):
                sel = [k for k, c in enumerate(CELLS) if c[0] == s and c[1] == t]
                g, nn = share_pf_gt1(a[sel])
                heat[sn][tn] = [g, nn]
        out[w] = {"pf_gt1": [gt, n], "by_dim": dims, "heat_share": heat}
    return out


def heat_at(A, k):
    """PF per stop x target at cell k's trail, cap, contract and trend, per window."""
    _s, _t, tr, cp, c, f = CELLS[k]
    out = {}
    for w in WINDOWS:
        a = agg_window(A, w)
        out[w] = {sn: {tn: agg_stats(a[CELLS.index((s, t, tr, cp, c, f))]).get("pf") for t, (tn, _y) in enumerate(TARGETS)}
                  for s, (sn, _x) in enumerate(STOPS)}
    return out


# ---------------------------------------------------------------- trials (written to the result as round 9 does)
TRIALS = {"Amendment 15 grid (7 entries x 1,080 cells; stop 'none' from Amendment 16)": 7560,
          "R1 pm_inside_break (shares, d40-55t45, d55-70t60)": 3,
          "R2 in-the-money d55-70t60 (7 frozen cells + 15.3)": 8,
          "R3 scale-out (7 frozen cells)": 7,
          "R4 ratchet (7 frozen cells)": 7,
          "Addendum 15.3 as corrected by 16.2 (with and without the day gates)": 2}
THIS_BUILD = 7587
ROUND10 = 7767
assert sum(TRIALS.values()) == THIS_BUILD and len(ENTRIES) * NCELL == 7560


def trials(n_prior):
    return {"parts": TRIALS, "this_build": THIS_BUILD, "round10_total": ROUND10, "prior_in_run_logs": int(n_prior),
            "total_for_dsr": int(n_prior) + ROUND10,
            "note": "This build's trials (grid, R1-R4, 15.3) are 7,587 of round 10's 7,767 (Amendment 16's tally); the deflated "
                    "Sharpe uses the run logs' count + 7,767, the whole round."}


def dsr_table(daily_by_name, n_prior, extra_srs=()):
    """{name: deflated Sharpe} on DEV daily P/L (dollars, every DEV session) with N = the run logs + 7,767 and the trial-Sharpe
    variance over every DEV variant scored (extra_srs: the per-session Sharpes of the other scored variants)."""
    from . import report as R
    srs = list(extra_srs)
    for v in daily_by_name.values():
        s = R.sharpe(list(v))
        if s is not None:
            srs.append(s)
    sr_var = float(np.var(np.array(srs, float))) if len(srs) > 1 else 0.0
    n = int(n_prior) + ROUND10
    return {k: R.deflated_sharpe(list(v), n, sr_var) for k, v in daily_by_name.items()}, round(sr_var, 6), n, len(srs)


def cell_sharpes(D):
    """Per-session Sharpe (mean / population sd, report.sharpe's) of each row of a DEV daily matrix (cents)."""
    x = D.astype(float) / 100.0
    sd = x.std(axis=1)
    m = x.mean(axis=1)
    ok = sd > 0
    return list(m[ok] / sd[ok])


def daily_vec(rows, days):
    idx = {d: i for i, d in enumerate(days)}
    v = np.zeros(len(days))
    for r in rows:
        i = idx.get(str(r["day"])[:10])
        if i is not None:
            v[i] += float(r["pnl"])
    return v


# ---------------------------------------------------------------- the report
def _f(x, n=2):
    from . import report as R
    return R.fmt(x, n)


def _row(cells):
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _head(cols):
    return ["", _row(cols), _row(["---"] * len(cols))]


def _yn(ok):
    return "PASS" if ok else "fail"


def _checks(L, checks):
    for n, ok in checks:
        L.append(f"  - {'yes' if ok else 'NO'}: {n}")


OP_COLS = ("window", "prices", "trades", "win %", "BE win %", "avg win $", "avg loss $", "exp $", "PF", "PF 2x", "total $",
           "w/o best 5 $", "max DD $")
PRICES = {"disc": "MODELED", "h1": "MODELED", "h2": "REAL"}


def _op(name, prices, s):
    if not s or not s.get("trades"):
        return _row([name, prices, s.get("trades", 0) if s else 0] + ["-"] * (len(OP_COLS) - 3))
    return _row([name, prices, s["trades"], _f((s.get("win_rate") or 0) * 100, 1),
                 _f((s.get("be_win_rate") or 0) * 100, 1) if s.get("be_win_rate") is not None else "-", _f(s.get("avg_win")),
                 _f(s.get("avg_loss")), _f(s.get("expectancy")), _f(s.get("pf"), 3), _f(s.get("pf_2x"), 3), _f(s.get("total")),
                 _f(s.get("without_best5")), _f(s.get("max_dd"))])


def _acc(L, av, title):
    from .round9 import _account_md
    _account_md(L, av, title)


def render(res, meta):
    t = res["trials"]
    L = [f"# Round 10: the 0DTE exit / entry grid and its add-ons ({meta.get('today')})", "",
         "SPRINT_PLAN Amendment 15 (with Amendment 16's stop 'none' and R4), Addendum 15.3 and Addendum 15.5 (R1, R2, R3, the regime "
         "features), pre-registered 2026-11-01 before any round-10 code or run. **Every number is a BACKTEST.** Options: **MODELED** "
         f"({MD.LABEL}) on HIST 2016-01-04..2024-01-31 and **REAL** Alpaca option prices on DEV 2024-08-01..2026-06-30; 1 contract "
         "unless stated, desk fills, 2% half-spread (MODELED-SPREAD, $0.005 floor), $0.65 per contract per side. Shares (R1): real "
         "stock bars, $10,000 a trade, $0.01 a share a side. L1 and L2 were never read. Not financial advice: evidence for Nick to "
         "decide.", "",
         f"- MODELED multipliers: {meta.get('calib_note', '-')}",
         f"- Frozen choice: `{meta.get('frozen_path')}` (sha256 {str(meta.get('frozen_sha', ''))[:12]}), written before any holdout "
         "readout.",
         f"- Inputs: {meta.get('files_note', '')}",
         f"- **Trials:** this build {t['this_build']} ({', '.join(f'{k}: {v}' for k, v in t['parts'].items())}); round 10 = "
         f"{t['round10_total']}; the run logs hold {t['prior_in_run_logs']}; the deflated Sharpe uses N = {t['total_for_dsr']} "
         f"(trial-Sharpe variance {res.get('sr_var')} over {res.get('dev_variants_scored')} DEV variants).",
         "- Nothing here is promoted: a pass still needs a new versioned paper ledger, Nick's yes and 40 forward paper trades "
         "(CLAUDE.md step 5).", ""]
    if meta.get("warnings"):
        L += ["**Warnings:**"] + [f"- {w}" for w in meta["warnings"]] + [""]
    L += ["## Summary", ""] + [f"- {s}" for s in summary_lines(res)] + [""]
    _grid_md(L, res)
    _addons_md(L, res)
    _af_md(L, res.get("af"))
    _r1_md(L, res.get("r1"))
    _regime_md(L, res)
    L += ["## Deflated Sharpe (information, DEV daily P/L)", ""] + _head(("variant", f"DSR (N = {t['total_for_dsr']})"))
    for k, v in sorted((res.get("dsr") or {}).items()):
        L.append(_row([k, _f(v, 4)]))
    L += ["", "No rule, cut, threshold or seed changes after these results; a change is a new amendment, labeled in-sample."]
    return "\n".join(L) + "\n"


def _grid_md(L, res):
    G = res.get("grid") or {}
    L += ["## The grid (Amendment 15 + stop 'none')", "",
          f"Cells per entry: {NCELL} (stop {len(STOPS)} x target {len(TARGETS)} x trail 2 x cap 3 x contract 3 x trend 2); "
          f"chosen per entry on {DISC[0]}..{DISC[1]} (MODELED) only; holdout 1 {H1[0]}..{H1[1]} (MODELED), holdout 2 DEV (REAL)."]
    for e in ENTRIES:
        g = G.get(e)
        if not g:
            L += ["", f"### {e}", "", "NOT RUN (no trade tables)."]
            continue
        L += ["", f"### {e}", ""]
        if g.get("chosen") is None:
            L.append(f"- No choice: {g.get('why_not')}.")
        else:
            L.append(f"- Frozen cell: `{g['chosen']}` ({g['chosen_text']}). Verdict: **{'SURVIVES' if g['survives'] else 'fails'}**"
                     + (f" (first failed check: {g['why_not']})" if not g["survives"] else "") + ".")
            L.append("- Holdout 1 (MODELED):")
            _checks(L, g["holdout1"]["checks"])
            L.append("- Holdout 2 (REAL):")
            _checks(L, g["holdout2"]["checks"])
            L += _head(OP_COLS)
            for w in WINDOWS:
                L.append(_op(w, PRICES[w], g["chosen_stats"][w]))
            L.append(_op("h2 twin", "REAL", g["holdout2"]["twin"]))
            for w, av in (g.get("account") or {}).items():
                _acc(L, av, f"{w} account view (information, $3,000 account, {PRICES[w]})")
        sm = g["summary"]
        L.append("- Cells with PF > 1: " + "; ".join(f"{w} {sm[w]['pf_gt1'][0]}/{sm[w]['pf_gt1'][1]}" for w in WINDOWS)
                 + " (cells with trades).")
        for w in WINDOWS:
            L += ["", f"Heat map, {w} ({PRICES[w]}): cells with PF > 1 / cells with trades, by stop (rows) x target (columns)"]
            L += _head(["stop"] + [tn for tn, _x in TARGETS])
            for sn, row in sm[w]["heat_share"].items():
                L.append(_row([sn] + [f"{a}/{b}" for a, b in row.values()]))
            L.append("By dimension (PF > 1 / with trades): " + "; ".join(
                f"{dn}: " + ", ".join(f"{lv} {a}/{b}" for lv, (a, b) in d.items()) for dn, d in sm[w]["by_dim"].items()))
        if g.get("heat_frozen"):
            for w in WINDOWS:
                L += ["", f"PF at the frozen cell's trail / cap / contract / trend, {w} ({PRICES[w]}):"]
                L += _head(["stop"] + [tn for tn, _x in TARGETS])
                for sn, row in g["heat_frozen"][w].items():
                    L.append(_row([sn] + [_f(v, 3) for v in row.values()]))
        sk = g.get("skips")
        if sk:
            L.append("- Skips (real signals): " + "; ".join(f"{k}: {v}" for k, v in sk.items()) + ".")
    L.append("")


def _addons_md(L, res):
    L += ["## R2, R3, R4 on each frozen cell", ""]
    for e in ENTRIES:
        g = (res.get("grid") or {}).get(e) or {}
        ad = g.get("addons")
        if not ad:
            continue
        for name, o in ad.items():
            L.append(f"**{e} {name}**: **{_yn(o['pass'])}**" + (f" (first failed check: {o['why_not']})" if not o["pass"] else ""))
            _checks(L, o["checks"])
            L += _head(OP_COLS)
            L.append(_op("h1", "MODELED", o["holdout1"]["stats"]))
            L.append(_op("h2", "REAL", o["holdout2"]["stats"]))
            L.append(_op("h2 twin", "REAL", o["holdout2"]["twin"]))
            L.append("")


def _af_md(L, af):
    L += ["## Addendum 15.3 as corrected by Addendum 16.2: the alpaca-options-framework's live path (SPY decides; QQQ information)",
          "", "VWAP and EMA(5)/EMA(20) direction, ROC5, 3 consecutive bars, ATR5 (true range) >= $0.20; the nearest out-of-the-money "
          "strike within 0.3% of SPY in the watched window; 15.3's list-only version is not run.", ""]
    if not af:
        L += ["NOT RUN.", ""]
        return
    for v, o in af["variants"].items():
        L.append(f"**{v}** ({o['label']}): B3's bars **{_yn(o['bar']['pass'])}**" if o.get("bar") else f"**{v}** ({o['label']})")
        if o.get("bar"):
            _checks(L, o["bar"]["checks"])
        L += _head(OP_COLS)
        for k, s in o["stats"].items():
            L.append(_op(k, "REAL" if "DEV" in k else "MODELED", s))
        if o.get("by_reason"):
            L.append("- By exit reason (all windows): " + "; ".join(f"{k} {s.get('trades')} trades, exp {_f(s.get('expectancy'))}"
                                                                     for k, s in o["by_reason"].items()))
        if o.get("by_hour"):
            L.append("- By entry hour: " + "; ".join(f"{k} {s.get('trades')} trades, exp {_f(s.get('expectancy'))}, win "
                                                     f"{_f((s.get('win_rate') or 0) * 100, 1)}% vs BE {_f((s.get('be_win_rate') or 0) * 100, 1)}%"
                                                     for k, s in o["by_hour"].items()))
        if o.get("sized_total") is not None:
            L.append(f"- At the published $150-risk sizing (information): total {_f(o['sized_total'])}.")
        L.append("")
    r2 = af.get("r2")
    if r2:
        L.append(f"**R2 on 15.3 (d55-70t60, gated as published)**: **{_yn(r2['pass'])}**")
        _checks(L, r2["checks"])
        L.append("")


def _r1_md(L, r1):
    L += ["## R1 pm_inside_break (Addendum 15.5)", ""]
    if not r1:
        L += ["NOT RUN.", ""]
        return
    L += ["The claim: of break days, the share whose session close is beyond the broken level."]
    L += _head(("window", "group", "break days", "close beyond", "share"))
    for w, g in r1["claim"].items():
        for k, v in g.items():
            L.append(_row([w, k, v["days"], v["beyond"], _f(v["share"], 3)]))
    sh = r1.get("shares")
    if sh:
        L += ["", f"**Shares** (qualifying days): Part A's bar **{_yn(sh['bar']['pass'])}**"]
        _checks(L, sh["bar"]["checks"])
        L.append(f"- Control (non-qualifying days): {sh['control']}; random-side twin seed {TWIN_SEED}: total {sh['twin_total']}.")
    for rule, o in (r1.get("options") or {}).items():
        L += ["", f"**Options {rule}** (qualifying days): B3's bars **{_yn(o['bar']['pass'])}**"]
        _checks(L, o["bar"]["checks"])
        L += _head(OP_COLS)
        for k, s in o["stats"].items():
            L.append(_op(k, "REAL" if "DEV" in k else "MODELED", s))
    L.append("")


def _regime_md(L, res):
    L += ["## Information only: regime features (2016-2019) and SPY vs QQQ by VIXY tercile", ""]
    for e in ENTRIES:
        g = (res.get("grid") or {}).get(e) or {}
        rg = g.get("regime")
        if not rg:
            continue
        L.append(f"**{e}** (frozen cell, 2016-2019 MODELED trades):")
        for feat, tt in rg["terciles"].items():
            if not tt:
                L.append(f"- {feat}: not enough values.")
                continue
            L.append(f"- {feat} (cuts {tt['cuts']}): " + "; ".join(
                f"{k} {s.get('trades')} trades, PF {_f(s.get('pf'), 3)}, exp {_f(s.get('expectancy'))}" for k, s in tt["groups"].items()))
        for w, vs in rg["vixy"].items():
            L.append(f"- SPY vs QQQ by VIXY tercile, {w} ({PRICES.get(w, '')}): " + "; ".join(
                f"{sym} {k} {s.get('trades')} trades, total {_f(s.get('total'))}" for sym, d in vs.items() for k, s in d.items() if s.get("trades")))
        L.append("")


def summary_lines(res):
    out = []
    for e in ENTRIES:
        g = (res.get("grid") or {}).get(e)
        if not g:
            continue
        if g.get("chosen") is None:
            out.append(f"{e}: no cell with {MIN_DISC} discovery trades.")
            continue
        h2 = g["holdout2"]["stats"]
        out.append(f"{e}: frozen `{g['chosen']}` -> {'SURVIVES' if g['survives'] else 'fails'} (DEV REAL {h2.get('trades')} trades, PF "
                   f"{_f(h2.get('pf'), 3)}, exp {_f(h2.get('expectancy'))})" + "".join(
                       f"; {k} {'PASS' if v['pass'] else 'fail'}" for k, v in (g.get("addons") or {}).items()))
    af = res.get("af")
    if af:
        for v in ("af153", "af153_nogate"):
            o = af["variants"].get(f"{v} SPY")
            if o and o.get("bar"):
                d = o["bar"]["dev"]
                out.append(f"15.3 {v}: {'PASS' if o['bar']['pass'] else 'fail'} (B3's bars, SPY; DEV REAL {d.get('trades')} trades, PF "
                           f"{_f(d.get('pf'), 3)}, exp {_f(d.get('expectancy'))}).")
        if af.get("r2"):
            out.append(f"R2 on 15.3: {'PASS' if af['r2']['pass'] else 'fail'}.")
    r1 = res.get("r1")
    if r1:
        if r1.get("shares"):
            out.append(f"R1 shares: {'PASS' if r1['shares']['bar']['pass'] else 'fail'} (Part A's bar).")
        for rule, o in (r1.get("options") or {}).items():
            out.append(f"R1 options {rule}: {'PASS' if o['bar']['pass'] else 'fail'} (B3's bars).")
    return out


# ---------------------------------------------------------------- stage 1 orchestration
def build_chunks(series, cache, run4_calib, root=None, aux=None, spread=None, log=None, limit_days=None, symbols=None,
                 periods_=("DEV", "HIST"), ents=ENTRIES):
    """series: {("HIST"|"DEV", symbol): data.Series}. DEV first (its real picks give the round 10 calibration), then HIST.
    Each (period, symbol, year) chunk is saved under `cache` and reused on a re-run with the same code and inputs.
    Returns (chunk paths, the merged calibration, its sha256)."""
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    syms = sorted({s for (_p, s) in series} if symbols is None else symbols)
    files = []
    kw = dict(root=root, aux=aux, spread=spread, limit_days=limit_days, ents=ents)
    if "DEV" in periods_:
        for sym in syms:
            ser = series.get(("DEV", sym))
            if ser is None or not ser.days:
                continue
            for y in chunk_years("DEV"):
                if chunk_days(ser, "DEV", y):
                    files.append(ensure_chunk(cache, ser, "DEV", y, None, log, **kw))
    rows = []
    for f in files:
        rows += load_chunk(f)[2]["calib"]
    proxies = {}

    def proxy(sym, day_iso):
        ser = series.get(("DEV", sym))
        if ser is None:
            return None
        k = (sym, day_iso)
        if k not in proxies:
            d = date.fromisoformat(day_iso)
            proxies[k] = MD.iv_proxy(ser, d) if d in ser.rth else None
        return proxies[k]

    calib = extend_calibration(run4_calib, rows, proxy) if run4_calib is not None else None
    sha = hashlib.sha256(json.dumps(calib, sort_keys=True).encode()).hexdigest() if calib is not None else None
    if calib is not None:
        (cache / "r10grid_calib.json").write_text(json.dumps(calib, indent=1, sort_keys=True) + "\n")
    if "HIST" in periods_:
        if calib is None:
            if log:
                log("  r10 grid: no run 4 calibration: HIST (MODELED) not run")
        else:
            for sym in syms:
                ser = series.get(("HIST", sym))
                if ser is None or not ser.days:
                    continue
                for y in chunk_years("HIST"):
                    if chunk_days(ser, "HIST", y):
                        files.append(ensure_chunk(cache, ser, "HIST", y, sha, log, calib=calib, **kw))
    return files, calib, sha


# ---------------------------------------------------------------- stage 2: the analysis
ADDON_LABELS = {"R2": "R2 d55-70t60", "R3": "R3 scale-out (3 contracts)", "R4": "R4 ratchet"}


def _tracked_specs(k):
    s, _t, _tr, _cp, c, f = CELLS[k]
    v = int(CELL_V[k])
    return [("frozen", c, v, 1, f), ("R2", len(CONTRACTS), v, 1, f), ("R3", c, R3_BASE + s, 3, f), ("R4", c, R4_V, 1, f)]


def _chunks_sorted(files):
    order = {"HIST": 0, "DEV": 1}
    files = [Path(p) for p in files if not Path(p).name.endswith(".tmp.npz")]
    return sorted(files, key=lambda p: (order.get(p.name.split("_")[0], 9), p.name))


def check_chunks(files):
    """The chunks must come from this code, one per (period, symbol, year), with the same entries and smoke setting."""
    seen, vers = set(), set()
    cur = code_version()
    for f in files:
        with np.load(f, allow_pickle=False) as z:
            m = _unpack_json(z["_meta"])
        key = (m.get("period"), m.get("symbol"), m.get("year"))
        if key in seen:
            raise ValueError(f"two chunks for {key}")
        seen.add(key)
        vers.add((m.get("version"), m.get("limit_days"), tuple(m.get("entries") or ())))
        if m.get("version") != cur:
            raise ValueError(f"{Path(f).name} was made by other code ({m.get('version')} vs {cur}): re-run stage 1")
    if len(vers) > 1:
        raise ValueError(f"the chunks mix settings: {sorted(vers, key=str)}")
    return sorted(f"{p}_{s}_{y}" for p, s, y in seen)


def analyze(files, frozen_path, n_prior=0, log=None):
    """Stage 2 over the saved chunks: replay every cell, choose and freeze on 2016-2019 only, then the holdouts, the add-ons,
    15.3, R1, the information tables, the trials and the deflated Sharpe. Returns (result, trade rows by kind, cells table)."""
    from . import book, round9
    files = _chunks_sorted(files)
    inputs = check_chunks(files)
    dev_days = book.sessions_between(DEV_A, DEV_B)
    real = Agg(dev_days)
    twin = Agg()
    skips = defaultdict(Counter)
    r1 = {"claim": [], "shares": [], "options": []}
    af = []
    for f in files:
        m, arr, rows = load_chunk(f)
        dev = m["period"] == "DEV"
        replay_all(arr, "real_", real.a, real.daily if dev else None, real.dev_idx)
        if dev and "twin_entry" in arr:
            replay_all(arr, "twin_", twin.a)
        for (e, rule, why), n in ((tuple(k), v) for k, v in rows["skips"]):
            skips[e][f"{rule}: {why}"] += n
        for k in ("claim", "shares", "options"):
            r1[k] += rows["r1"][k]
        af += rows["af"]
    # ---- the choice, on 2016-2019 only, frozen before any holdout readout
    choices, disc_stats = {}, {}
    for e in ENTRIES:
        disc = agg_window(real.a[e], "disc")
        k = choose(disc)
        choices[e] = k
        disc_stats[e] = agg_stats(disc[k]) if k is not None else None
    frozen_sha = write_frozen(frozen_path, frozen_doc(choices, disc_stats, inputs))
    if log:
        log("  r10 grid: frozen " + "; ".join(f"{e} {cell_id(k) if k is not None else '-'}" for e, k in choices.items()))
    # ---- tracked cells (the frozen cells and their add-ons), real and twin
    tracked = defaultdict(list)
    for f in files:
        m, arr, _rows = load_chunk(f)
        for ek, e in enumerate(ENTRIES):
            k = choices[e]
            if k is None:
                continue
            for label, ci, vi, md, fl in _tracked_specs(k):
                tracked[(e, label, "real")] += [dict(r, _src=m["period"]) for r in
                                                 replay_one(arr, "real_", ek, ci, vi, fl == 1, m["symbol"], label, md)]
                if m["period"] == "DEV" and "twin_entry" in arr:
                    tracked[(e, label, "twin")] += [dict(r, _src="DEV") for r in
                                                     replay_one(arr, "twin_", ek, ci, vi, fl == 1, m["symbol"], label, md)]
    res = {"grid": {}}
    cells_table = []
    for e in ENTRIES:
        A, T = real.a[e], twin.a[e]
        k = choices[e]
        g = {"summary": grid_summary(A), "skips": dict(sorted(skips[e].items()))}
        for c in range(NCELL):
            row = {"entry": e, "cell": cell_id(c), "cell_index": c}
            for w in WINDOWS:
                s = agg_stats(agg_window(A[c], w))
                for kk in ("trades", "win_rate", "expectancy", "pf", "pf_2x", "total"):
                    row[f"{w}_{kk}"] = s.get(kk)
            st = agg_stats(agg_window(T[c], "h2"))
            for kk in ("trades", "expectancy", "pf", "total"):
                row[f"h2twin_{kk}"] = st.get(kk)
            cells_table.append(row)
        if k is None:
            g.update(chosen=None, survives=False, why_not=f"no cell kept {MIN_DISC} trades in {DISC[0]}..{DISC[1]}")
            res["grid"][e] = g
            continue
        fr, ft = tracked[(e, "frozen", "real")], tracked[(e, "frozen", "twin")]
        h1, h2 = holdout1(fr), holdout2(fr, ft)
        g.update(chosen=cell_id(k), chosen_index=int(k), chosen_text=cell_text(k), holdout1=h1, holdout2=h2,
                 survives=h1["pass"] and h2["pass"], why_not=None if h1["pass"] and h2["pass"] else
                 (first_fail(h1["checks"]) if not h1["pass"] else first_fail(h2["checks"])),
                 chosen_stats={w: ostats(win_rows(fr, w)) for w in WINDOWS}, heat_frozen=heat_at(A, k),
                 account={w: round9.account_view(win_rows(fr, w), "option", book.sessions_between(*WINDOWS[w]))
                          for w in WINDOWS if win_rows(fr, w)})
        g["addons"] = {ADDON_LABELS[lab]: addon_verdict(lab, tracked[(e, lab, "real")], tracked[(e, lab, "twin")], fr,
                                                        "pf" if lab == "R2" else "exp") for lab in ("R2", "R3", "R4")}
        dr = win_rows(fr, "disc")
        g["regime"] = {"terciles": {f: terciles(dr, f) for f in features.REGIME10},
                       "vixy": {w: vixy_split(win_rows(fr, w)) for w in WINDOWS}}
        res["grid"][e] = g
    res["af"] = af_readout(af)
    res["r1"] = r1_readout(r1)
    # ---- trials and the deflated Sharpe
    res["trials"] = trials(n_prior)
    srs = []
    for e in ENTRIES:
        srs += cell_sharpes(real.daily[e])
    named = {}
    for (e, lab, kind), rows in tracked.items():
        if kind == "real":
            named[f"{e} {lab}"] = daily_vec(win_rows(rows, "h2"), dev_days)
    for v in ("af153", "af153_nogate", "af153_r2"):
        named[f"15.3 {v} SPY"] = daily_vec([r for r in af if r["variant"] == v and r["symbol"] == "SPY" and r["_src"] == "DEV"], dev_days)
    named["R1 shares"] = daily_vec([r for r in r1["shares"] if r.get("qualifies") and r["_src"] == "DEV"], dev_days)
    for rule in R1_CONTRACTS:
        named[f"R1 {rule}"] = daily_vec([r for r in r1["options"] if r["variant"] == f"r1_{rule}_qual" and r["_src"] == "DEV"], dev_days)
    tab, sr_var, n, cnt = dsr_table(named, n_prior, srs)
    res["dsr"], res["sr_var"], res["dev_variants_scored"] = tab, sr_var, cnt
    res["frozen"] = {"path": str(frozen_path), "sha256": frozen_sha, "choices": {e: (cell_id(k) if k is not None else None)
                                                                                 for e, k in choices.items()}}
    trk = []
    for key in sorted(tracked):
        for r in sorted(tracked[key], key=lambda z: (z["day"], z["entry_idx"], z["symbol"])):
            trk.append(dict(r, kind=key[2]))
    trades = {"tracked": trk, "af": af, "r1_shares": r1["shares"], "r1_options": r1["options"], "r1_claim": r1["claim"]}
    return res, trades, cells_table


# ---------------------------------------------------------------- the compounding view's inputs (Amendment 16; sprint/compound.py)
HOLDOUT_WINDOWS = (("holdout 1", H1[0], H1[1], "MODELED"), ("holdout 2", H2[0], H2[1], "REAL"))
PERIOD_WINDOWS = (("HIST", HIST_A, HIST_B, "MODELED"), ("DEV", DEV_A, DEV_B, "REAL"))


def passing_rules(res, trades):
    """Every rule of this build that passed its pre-registered bars, for the compounding view: [(name, rows, risk key,
    windows)]. rows carry day and pnl at the pre-registered size; the risk key names each row's risk unit ("debit": the
    option's cost per trade, x 3 for R3; "notional": R1's $10,000 in shares). Windows: the holdouts for a chosen rule (the grid's
    frozen cells, R2-R4, R2 on 15.3), the HIST and DEV periods for a rule with no fitted parameter (15.3, R1)."""
    out = []
    trk = trades.get("tracked") or []
    for e in ENTRIES:
        g = (res.get("grid") or {}).get(e) or {}
        if g.get("survives"):
            out.append((f"grid {e} {g['chosen']}", [r for r in trk if r["entry"] == e and r["variant"] == "frozen" and r["kind"] == "real"],
                        "debit", HOLDOUT_WINDOWS))
        for lab, name in ADDON_LABELS.items():
            if ((g.get("addons") or {}).get(name) or {}).get("pass"):
                out.append((f"{e} {name}", [r for r in trk if r["entry"] == e and r["variant"] == lab and r["kind"] == "real"],
                            "debit", HOLDOUT_WINDOWS))
    af = res.get("af") or {}
    for v in ("af153", "af153_nogate"):
        if (((af.get("variants") or {}).get(f"{v} SPY") or {}).get("bar") or {}).get("pass"):
            out.append((f"15.3/16.2 {v} SPY", [r for r in trades.get("af") or [] if r["variant"] == v and r["symbol"] == "SPY"],
                        "debit", PERIOD_WINDOWS))
    if (af.get("r2") or {}).get("pass"):
        out.append(("R2 on 15.3/16.2 SPY", [r for r in trades.get("af") or [] if r["variant"] == "af153_r2" and r["symbol"] == "SPY"],
                    "debit", HOLDOUT_WINDOWS))
    r1 = res.get("r1") or {}
    if ((r1.get("shares") or {}).get("bar") or {}).get("pass"):
        out.append(("R1 shares", [r for r in trades.get("r1_shares") or [] if r.get("qualifies")], "notional", PERIOD_WINDOWS))
    for rule, o in (r1.get("options") or {}).items():
        if (o.get("bar") or {}).get("pass"):
            out.append((f"R1 {rule}", [r for r in trades.get("r1_options") or [] if r["variant"] == f"r1_{rule}_qual"], "debit",
                        PERIOD_WINDOWS))
    return out


def compounding_inputs(rows, risk_key, a, b):
    """compound.simulate's rows for one window: {"day", "pnl", "risk"} (risk > 0 only)."""
    out = []
    for r in rows:
        d = str(r["day"])[:10]
        if a <= d <= b:
            risk = float(r[risk_key])
            if risk > 0:
                out.append({"day": d, "pnl": float(r["pnl"]), "risk": risk})
    return out


# ---------------------------------------------------------------- 15.3 and R1 readouts
AF_LABELS = {"af153": "15.3 / 16.2 with the day gates", "af153_nogate": "15.3 / 16.2 without the day gates",
             "af153_r2": "R2: 15.3 / 16.2 on d55-70t60, gates on", "af153_r2_nogate": "R2 on 15.3 / 16.2 without the gates (information)"}
AF_STAT_WINDOWS = (("HIST 2016-2023 (MODELED)", HIST_A, "2023-12-31"), ("Jan 2024 (MODELED)", "2024-01-01", HIST_B),
                   ("DEV (REAL)", DEV_A, DEV_B))


def af_readout(rows):
    from . import round8
    if not rows:
        return None
    out = {"variants": {}}
    for v, lab in AF_LABELS.items():
        for sym in AF_SYMBOLS:
            rs = [r for r in rows if r["variant"] == v and r["symbol"] == sym]
            o = {"label": f"{lab}; {sym}" + (" (decides)" if sym == "SPY" else " (information)"),
                 "stats": {n: ostats([r for r in rs if a <= r["day"] <= b]) for n, a, b in AF_STAT_WINDOWS}}
            if sym == "SPY" and v in ("af153", "af153_nogate"):
                o["bar"] = round8.b3_bar([r for r in rs if r["day"] <= HIST_B], [r for r in rs if r["day"] >= DEV_A])
                by_r, by_h = defaultdict(list), defaultdict(list)
                for r in rs:
                    by_r[r["exit_reason"]].append(r)
                    by_h[r["hour"]].append(r)
                o["by_reason"] = {k: ostats(x) for k, x in sorted(by_r.items())}
                o["by_hour"] = {k: ostats(x) for k, x in sorted(by_h.items())}
                o["sized_total"] = round(sum(r["pnl_sized"] for r in rs), 2)
            out["variants"][f"{v} {sym}"] = o
    spy = lambda v: [r for r in rows if r["variant"] == v and r["symbol"] == "SPY"]
    r2 = addon_verdict("R2", spy("af153_r2"), spy("af153_r2_twin"), spy("af153"), "pf")
    out["r2"] = r2
    return out


def r1_readout(r1):
    if not r1 or not r1.get("claim"):
        return None
    out = {"claim": {}}
    for wn, a, b in (("HIST 2016-2024", HIST_A, HIST_B), ("DEV", DEV_A, DEV_B), ("all", HIST_A, DEV_B)):
        g = {}
        for grp, q in (("qualifying", True), ("non-qualifying", False)):
            rs = [r for r in r1["claim"] if r["break"] and r["qualifies"] == q and a <= r["day"] <= b]
            n, y = len(rs), sum(1 for r in rs if r.get("beyond"))
            g[grp] = {"days": n, "beyond": y, "share": round(y / n, 4) if n else None}
        out["claim"][wn] = g
    qual = [r for r in r1["shares"] if r.get("qualifies")]
    ctl = [r for r in r1["shares"] if not r.get("qualifies")]
    if qual:
        bar = shares.pass_bar(qual)
        _p, tots = shares.random_direction(qual, (TWIN_SEED,))
        out["shares"] = {"bar": bar, "control": shares.stats(ctl), "twin_total": round(float(tots[0]), 2) if len(tots) else None,
                         "years": shares.years_table(qual)}
    from . import round8
    out["options"] = {}
    for rule in R1_CONTRACTS:
        q = [r for r in r1["options"] if r["variant"] == f"r1_{rule}_qual"]
        stats = {}
        for nm, var in (("qualifying", f"r1_{rule}_qual"), ("control", f"r1_{rule}_ctl"), ("twin", f"r1_{rule}_qual_twin")):
            rs = [r for r in r1["options"] if r["variant"] == var]
            for wn, a, b in AF_STAT_WINDOWS:
                stats[f"{nm} {wn}"] = ostats([r for r in rs if a <= r["day"] <= b])
        out["options"][rule] = {"bar": round8.b3_bar([r for r in q if r["day"] <= HIST_B], [r for r in q if r["day"] >= DEV_A]),
                                "stats": stats}
    return out
