"""sprint/r10swing.py - round 10's swing families V1-V4 (SPRINT_PLAN Amendment 16, pre-registered 2026-11-01 before any
round-10 code, pull or run; background: docs/research/OPTIONS_STRATEGY_SURVEY.md families #2, #3, #4 and #6). Research only:
reads cached daily bars (sprint/universe.py), EDGAR 8-K records (round 9's pull), round 10's option and stock bars
(tools/sprint_pull10.py, layout in sprint/ivdata.py); no network, no orders. Every number is a BACKTEST: shares on real
Alpaca daily bars, options on REAL Alpaca option prices (DEV only). U-STK results are SURVIVORSHIP-BIASED.

Shared mechanics for V1, V2 and V2-s (as written):
  Rebalance  the first session of each month at 15:45, on data through the prior close.
  Hold       to the next rebalance's 15:45. If a realized 8-K Item 2.02 date falls inside the hold, exit at the last 15:45
             before it (LOOK-AHEAD CAVEAT, as G2: the 8-K date is the realized date).
  Fills      the 15:45-16:00 last trade +/- the measured half-spread, plus $0.65 per contract per side; every result at mid,
             50% and 100% of the measured spread; pass/fail judged at 100%.
  Benchmark  the same structure on 10 random eligible names on the same dates, 200 draws, seeds 31-230.
  Pass       (all at 100%): at least 100 positions; PF >= 1.2; mean return per position above the 90th percentile of the
             random draws; positive in at least 4 of the 6 two-month blocks of 2025-07..2026-06.
  V1 term_slope (Vasquez 2017): slope = 90-day IV - 30-day IV; buy the 30-day ATM straddle on the top 10 by slope.
  V2 rv_iv_gap (Goyal & Saretto 2009): ratio = log(RV252 / 30-day IV), RV252 from the last 252 daily closes in round 9's
             daily file, which skips the locked periods; buy the 30-day ATM straddle on the top 10 by ratio. V1/V2 overlap
             reported.
  V2-s rv_iv_rich (Temple-Stuart's vol-edge side; PAPER RESEARCH ONLY, needs Level 3): on the bottom 10 by V2's ratio, sell
             a 30-day iron condor, shorts at 20 delta, longs at 10 delta (BS from the day's IV); held as above; the return
             per position is on the margin (width minus credit).
V3 earn_runup (Aboody, Lehavy & Trueman 2010): shares, U-STK, the top 10% by 12-1 month return on the entry date; buy at the
   close 5 sessions before the realized 8-K 2.02 date, sell at the last close before the report. HIST 2016-2023, then DEV;
   Part F's 7-item bar and costs; the random-date benchmark uses dates at least 10 sessions from any report. Options twin
   (DEV REAL): a delta 0.50-0.60 call on the first expiry after the report, same entry and exit times (15:45-16:00 prints);
   pass: F-opt's bar plus the random-date twin.
V4 new_high (Zarattini, Pagani & Wilcox 2025): shares, U-STK + U-ETF: buy at the next open after a close at the highest close
   of the prior 252 sessions; exit at the next open after a close below a trailing stop = the highest close since entry
   minus 3 x ATR(20), raised daily, never lowered (3 x ATR(20) is the desk's frozen choice). $10,000 a position, at most 10
   open, ties to the higher 20-day dollar volume. Discovery 2016-2019, holdout 2020-2023, then DEV; Part F's bar; the share
   of profit from the top 7% of trades. Options twin (DEV REAL): a delta 0.60-0.70 call 60-120 days out, exited on the
   stock's stop and rolled at 30 days left; F-opt's bar.
Trials: V1 1, V2 1, V2-s 1, V3 2, V4 2 = 7 (round 10 = 7,767; the deflated Sharpe uses the run logs' count + 7,767).

Builder's reading (the most literal reading where the text is ambiguous or impossible with our data):
  R1  Universe for V1/V2/V2-s: D-IV's (U-ETF + U-STK names passing round 9's point-in-time filter on the rebalance day).
      Sort keys use 5-session means through the prior session (ivdata.IVTable.prior). Eligible = the key is defined. Ties:
      symbol. A selected name whose straddle (or condor) cannot be priced is not replaced; it is counted.
  R2  Rebalance days = the first NYSE session of each month in DEV. The first (2024-08-01) has no IV history (July 2024 is
      L2), so it opens nothing. The June 2026 hold would end at the July 2026 rebalance, inside L1: it is dropped (a holding
      window touching L1/L2 is dropped, Amendment 12).
  R3  The 30-day straddle = D-IV's 30-day expiry on the entry day; strike = the strike nearest the entry spot (D-IV's spot,
      the stock's last 15:45-15:59 close; ties: lower) among strikes whose call AND put printed 15:45-15:59. Fill basis = each
      leg's last 15:45-15:59 print (ivdata), the same window D-IV uses.
  R4  "Exit at the last 15:45 before it": the last session whose 15:45 is strictly before the 2.02 acceptance time. A 2.02
      accepted after the entry's 15:45 but before the next session's 15:45 leaves no hold: that position is dropped and
      counted. The hold window is (entry 15:45, scheduled exit 15:45].
  R5  A weekly 30-day expiry (21-27 days out) ends before the next rebalance. A position whose expiry is on or before its
      exit day is settled at intrinsic value from the stock's raw daily close on the expiry day (no spread, no fee: exercise
      or expiry). A leg without a 15:45-15:59 print on a traded exit day has no fill: the position is not counted, and
      counted as such (G2's rule).
  R6  "The measured half-spread" = sprint/spread.py's SpreadModel from the desk's logged chains (MEASURED-SPREAD where a cell
      of that underlying has data; the chains hold SPY/QQQ 0DTE rows), else its MODELED default (2% of premium for
      SPY/QQQ/IWM/DIA, 10% for every other name, $0.005 floor). Each row carries its label. Fill = print + s x k x half-
      spread, k = 0 (mid), 0.5 (50%), 1 (100%); s = +1 buying, -1 selling (sells floored at 0). The 2x line (k = 2) is
      information.
  R7  Return per straddle = P/L / debit (both legs' fills x 100 + entry fees). PF = sum of positive returns / |sum of negative
      returns| (equal weight per position, as G2). Two-month blocks by exit day; "positive" = mean return > 0.
  R8  Benchmark: for each draw (default_rng(seed), seeds 31-230), on each rebalance day in order, 10 names drawn without
      replacement from that day's eligible names (fewer if fewer); the draw's mean return per priced position at 100%. Pass
      needs the rule's mean above the 90th percentile of the 200 draw means.
  R9  RV252 = the sample std of the daily log returns among the last 252 split-adjusted closes of the name's file through the
      prior session x sqrt(252). The file has no locked dates, so near DEV's start the 252 closes reach back across L2; the
      one return that jumps the gap (2024-01-31 -> 2024-08-01) is left out (it is not a daily return).
  R10 Condor (V2-s): the day's IV = D-IV's 30-day ATM IV on the entry day (not the 5-session mean); delta = BS (r = 0) with
      that IV, the entry spot and the time from 15:45 to the 30-day expiry's 16:00. Short call/put = the printed OTM strike
      nearest |delta| 0.20; long call/put = the printed strike beyond the short nearest |delta| 0.10 (ties: lower strike).
      Margin = 100 x the wider wing - the credit after entry fees ("width minus credit"; only one wing can lose). Return =
      P/L / margin. The pull probes, per leg and per plausible grid, the two strikes bracketing the BS target strike and one
      more on each side (ivdata.near_strikes).
  R11 V3 dates: d = the 2.02 acceptance date. Exit = the last session whose 16:00 close is before the acceptance (d itself
      for a filing at/after 16:00 on a session, else the session before d). Entry = the close of the 5th session before d.
      One event per symbol and d (the earliest acceptance). The trade must enter and exit in one window (HIST or DEV) without
      touching L1/L2. "HIST 2016-2023" = round 9's HIST window 2016-01-04..2024-01-31, as Part F (Part F's item 3 still counts
      the years 2016-2023).
  R12 V3 12-1 return = close 21 bars back / close 252 bars back - 1 on the name's own split-adjusted bars inside one segment
      (round 9's panel rule: no window across L2, so DEV values exist from about August 2025). "Top 10%" = among U-STK
      names passing the filter on the entry day with a 12-1 value, fewer than 10% of them have a higher value.
  R13 V3 random dates: the same symbol and holding length, entry and exit both at least 10 sessions (NYSE calendar) from
      every one of that symbol's 2.02 report sessions (the first session on/after each acceptance date), the symbol passing
      the filter on the entry day, inside one window; Part F's item 6 draw (200 draws, seeds 31-230, p < 0.05).
  R14 V3 twin: "first expiry after the report" = the first Friday expiry (Thursday on a holiday Friday) whose 16:00 close is
      after the acceptance, else the first monthly after it (the earlier with any print among the probed calls). Calls with a
      15:45-15:59 print on the entry day, BS-EST delta (IV from the print, the stock's close in the print's minute) in
      0.50-0.60, nearest 0.55 (ties: lower premium, then symbol). Costs = F-opt's (2% half-spread, $0.005 floor, $0.65 a
      side; 2x = twice the half-spread); the measured-spread P/L is information. Random-date twin: G2's fixed pool, 5 random
      dates per twin event (default_rng(31)) drawn from R13's candidates inside DEV, expiry = the first one after the random
      exit day; 200 draws (seeds 31-230) each take one priced pool date per event; pass needs p < 0.05 on the mean P/L.
  R15 V4: "at the highest close of the prior 252 sessions" = the close >= the max of the name's previous 252 closes (own
      bars inside one segment, so DEV signals start about August 2025). ATR(20) = Wilder's (first value = the mean of the
      first 20 true ranges). Stop in force at a close = the highest value of (highest close since entry - 3 x ATR(20))
      over the closes from the entry day to the day before; the entry day's own close is not checked. Shares = floor(10,000
      / the signal close, raw); P/L from split-adjusted opens; U-STK names must pass the filter on the entry day, U-ETF
      names always can. A slot freed by an exit at an open can be refilled at that open. 20-day dollar volume = the mean raw
      close x volume of the last 20 bars through the signal close. Positions still open at the L2 gap or the data end are
      dropped (their exit would be in L2/L1). Windows by exit day: discovery 2016-01..2019-12, holdout 2020-01..2024-01
      (HIST's last month joins the holdout), DEV. Part F's 7-item bar on all trades; per-window numbers shown beside it.
      Random entry (item 6): Part F's draw per universe, the two draw totals added.
  R16 V4 twin: at the share entry's open, calls 60-120 calendar days out (probed: Friday expiries and quarter-end sessions),
      BS-EST delta 0.60-0.70 nearest 0.65 picked as F-opt picks (first print 09:30-09:34, S = the raw open). On the first
      session with 30 or fewer calendar days left (before the share exit), the call is sold at its first print of that
      session and a new call is bought by the same rule at that open. Out at the share exit's open (first print of that
      session). A missing print or no contract to roll into: the trade is not counted, and counted as such. Costs = F-opt's.
Compounding view: a hook for sprint/compound.py (another builder's module), see compounding_view().
"""
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import bs, edgar, periods, shares
from . import ivdata as IV
from . import multiday as M
from . import universe as U
from .catalyst import occ, occ_root

SB = U.SB
LOOKAHEAD = edgar.LOOKAHEAD
REAL = "REAL (Alpaca option prices)"
PAPER = "PAPER RESEARCH ONLY (option selling; needs Level 3)"
TRIALS = {"V1 term_slope": 1, "V2 rv_iv_gap": 1, "V2-s rv_iv_rich": 1, "V3 earn_runup (shares + options twin)": 2,
          "V4 new_high (shares + options twin)": 2}
SWING_TRIALS = 7
ROUND10_TOTAL = 7767
assert sum(TRIALS.values()) == SWING_TRIALS
TOP_N = 10
K_LEVELS = (("mid", 0.0), ("50", 0.5), ("100", 1.0), ("2x", 2.0))
FEE, MULT = 0.65, 100
RANDOM_SEEDS = tuple(range(31, 231))
BOOT_SEED, BOOT_DRAWS = 29, 2000
MIN_POSITIONS, PF_MIN, BENCH_PCT, BLOCKS_MIN = 100, 1.2, 90, 4
BLOCKS = (("2025-07..08", "2025-07-01", "2025-08-31"), ("2025-09..10", "2025-09-01", "2025-10-31"),
          ("2025-11..12", "2025-11-01", "2025-12-31"), ("2026-01..02", "2026-01-01", "2026-02-28"),
          ("2026-03..04", "2026-03-01", "2026-04-30"), ("2026-05..06", "2026-05-01", "2026-06-30"))
CONDOR_SHORT, CONDOR_LONG = 0.20, 0.10
DECISION_MIN = IV.LAST_M0 - 1                # t_minutes(day, 374, e) = minutes from 15:45 to 16:00 on e
RV_RETURNS = 251                             # the last 252 closes -> 251 returns
V3_BEFORE, V3_GAP, V3_TOP = 5, 10, 0.10
V3_BAND, V3_STRIKES = (0.50, 0.60, 0.55), (0.94, 1.02)
V3_POOL, V3_POOL_SEED = 5, 31
V4_LOOK, V4_ATR, V4_MULT, V4_SLOTS, V4_TOP = 252, 20, 3.0, 10, 0.07
V4_BAND, V4_DTE, V4_ROLL, V4_STRIKES = (0.60, 0.70, 0.65), (60, 120), 30, (0.80, 1.00)
OPT_HS, OPT_FLOOR = M.OPT_HS, M.OPT_FLOOR
DEV_A, DEV_B = periods.DEV
HIST_A, HIST_B = periods.HIST
WINDOWS_V4 = (("discovery 2016-2019", "2016-01-01", "2019-12-31"), ("holdout 2020-2023", "2020-01-01", "2024-01-31"),
              ("DEV", DEV_A.isoformat(), DEV_B.isoformat()))


def _r(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


# ---------------------------------------------------------------- inputs (daily panels, EDGAR, universe)
class HLPanel(U.Panel):
    """universe.Panel plus split-adjusted highs and lows (V4's ATR)."""

    def __init__(self, symbols, frames_adj, frames_raw=None, days=None):
        super().__init__(symbols, frames_adj, frames_raw, days)
        T, N = len(self.days), len(self.symbols)
        self.adj_h, self.adj_l = np.full((T, N), np.nan), np.full((T, N), np.nan)
        for s in self.symbols:
            df = (frames_adj or {}).get(s)
            if df is None or not len(df):
                continue
            idx = [self.pos.get(d) for d in df.index]
            ok = np.array([i is not None for i in idx])
            if not ok.any():
                continue
            rows = np.array([i for i in idx if i is not None])
            j = self.col[s]
            self.adj_h[rows, j] = df["h"].to_numpy(float)[ok]
            self.adj_l[rows, j] = df["l"].to_numpy(float)[ok]


def load_panels(root, log=None, ustk=None):
    """{"all": one HLPanel with the U-ETF columns and the U-STK names that can ever pass the filter, "univ": {symbol:
    "U-ETF" / "U-STK"}, "ustk": the U-STK list}. One panel serves D-IV's universe, RV252, V3 and V4 (no second copy)."""
    fa, fr, univ = {}, {}, {}
    for s in U.U_ETF:
        a = U.read_daily9(s, "split", root)
        if a is not None:
            r = U.read_daily9(s, "raw", root)
            fa[s], fr[s], univ[s] = a, (r if r is not None else a), "U-ETF"
    us = ustk if ustk is not None else (U.read_ustk(root) or {}).get("symbols")
    skipped, missing = [], []
    for n, s in enumerate(us or []):
        if s in univ:
            continue
        r = U.read_daily9(s, "raw", root)
        if not U.ever_eligible(r):
            (missing if r is None else skipped).append(s)
            continue
        a = U.read_daily9(s, "split", root)
        if a is None:
            missing.append(s)
            continue
        fa[s], fr[s], univ[s] = a, r, "U-STK"
        if log and n and n % 500 == 0:
            log(f"  daily bars: {n}/{len(us)} U-STK symbols read")
    syms = [s for s in U.U_ETF if s in fa] + [s for s in (us or []) if univ.get(s) == "U-STK"]
    allp = HLPanel(syms, fa, fr)
    allp.skipped, allp.missing = skipped, missing
    return {"all": allp, "univ": univ, "ustk": list(us or [])}


def stk_mask(panels):
    p = panels["all"]
    return np.array([panels["univ"].get(s) == "U-STK" for s in p.symbols], bool)


class Universe:
    """D-IV's universe on a day: every U-ETF name plus the U-STK names passing the point-in-time filter."""

    def __init__(self, panels):
        self.p = panels["all"]
        self.etf = [s for s in U.U_ETF if s in self.p.col]
        self.stk = stk_mask(panels)
        self.elig = self.p.eligible() & self.stk[None, :] if self.p.symbols else None

    def names(self, day):
        out = list(self.etf)
        k = self.p.idx(day)
        if self.elig is not None and k is not None:
            out += [self.p.symbols[j] for j in np.flatnonzero(self.elig[k])]
        return out


def load_edgar(root):
    """(records, tmap) from round 9's EDGAR cache (headers.jsonl, company_tickers.json), or ([], {})."""
    er = Path(root).parent / "edgar"
    recs = edgar.read_jsonl(er / "headers.jsonl")
    tj = er / "company_tickers.json"
    tmap = edgar.tickers_map(json.loads(tj.read_text())) if tj.exists() else {}
    return recs, tmap


def report_times(records, tmap):
    """{symbol: sorted acceptance datetimes of its Item 2.02 8-Ks}."""
    out = defaultdict(set)
    for r in records:
        if r.get("form") != "8-K" or "2.02" not in (r.get("items") or []) or not r.get("accepted"):
            continue
        a = r["accepted"] if isinstance(r["accepted"], datetime) else datetime.fromisoformat(str(r["accepted"]))
        for sym in tmap.get(int(r["cik"]), []):
            out[sym].add(a)
    return {k: sorted(v) for k, v in out.items()}


def raw_close(panels, name, day):
    """The name's raw daily close on its last bar at or before `day` (None if none)."""
    import bisect
    p = panels["all"]
    j = p.col.get(name)
    if j is None:
        return None
    k = bisect.bisect_right(p.days, day) - 1
    while k >= 0 and not np.isfinite(p.raw_c[k, j]):
        k -= 1
    return float(p.raw_c[k, j]) if k >= 0 else None


# ---------------------------------------------------------------- the monthly schedule and the report exit
def rebalance_days(a=DEV_A, b=DEV_B):
    """The first NYSE session of each month in [a, b], plus the first one after b (to close the last hold)."""
    cal = U.all_sessions_cal(date(a.year, a.month, 1), b + timedelta(days=40))
    first = [d for k, d in enumerate(cal) if k == 0 or cal[k - 1].month != d.month]
    out = [d for d in first if a <= d <= b]
    nxt = [d for d in first if d > b]
    return out + nxt[:1]


def holds(a=DEV_A, b=DEV_B):
    """([(entry day, scheduled exit day)], [(entry, exit, why dropped)])."""
    f = rebalance_days(a, b)
    out, dropped = [], []
    for t, x in zip(f, f[1:]):
        if not a <= t <= b:
            continue
        if U.touches_locked(t, x) or x > b:
            dropped.append((t, x, "the hold ends inside L1/L2 or after DEV"))
            continue
        out.append((t, x))
    return out, dropped


def hold_exit(t, x, accepts, cal):
    """(exit day, the 2.02 acceptance that moved it or None). Exit = x, or the last session whose 15:45 is before the first
    2.02 acceptance inside (t 15:45, x 15:45]; (None, acceptance) when that leaves no hold."""
    t0, x0 = datetime(t.year, t.month, t.day, 15, 45), datetime(x.year, x.month, x.day, 15, 45)
    inside = [a for a in accepts or () if t0 < a <= x0]
    if not inside:
        return x, None
    a = min(inside)
    d = a.date()
    s = d if (cal.is_session(d) and (a.hour, a.minute, a.second) > (15, 45, 0)) else cal.back(d, 1)
    if s is None or s <= t:
        return None, a
    return s, a


# ---------------------------------------------------------------- V1 / V2 / V2-s keys
def rv252_prior(panel):
    """(T, N) RV252 through the name's last close before session t (R9): spanning the locked gap, the gap's return out."""
    T, N = panel.adj_c.shape
    out = np.full((T, N), np.nan)
    for j in range(N):
        v = IV.realized_vol(panel.adj_c[:, j], panel.seg, RV_RETURNS, span_locked=True)
        s = pd.Series(v).ffill().to_numpy()
        out[1:, j] = s[:-1]
    return out


def keys_on(day, tab, names, rv):
    """{"slope": {name: v}, "ratio": {name: v}} on a rebalance day from data through the prior close. rv: {name: RV252}."""
    m30, m90 = tab.prior("iv30", day), tab.prior("iv90", day)
    slope, ratio = {}, {}
    for n in names:
        j = tab.col.get(n)
        if j is None:
            continue
        a, b = m30[j], m90[j]
        if np.isfinite(a) and np.isfinite(b):
            slope[n] = float(b - a)
        r = rv.get(n)
        if np.isfinite(a) and a > 0 and r is not None and np.isfinite(r) and r > 0:
            ratio[n] = float(math.log(r / a))
    return {"slope": slope, "ratio": ratio}


def top(keys, n=TOP_N, bottom=False):
    """The n names with the highest (bottom=True: lowest) key; ties: symbol."""
    items = sorted(keys.items(), key=lambda kv: ((kv[1] if bottom else -kv[1]), kv[0]))
    return [k for k, _ in items[:n]]


# ---------------------------------------------------------------- option positions
def choose_straddle(name, pidx, spot, exp30):
    """The 30-day ATM straddle: {"legs": [(call occ, +1), (put occ, +1)], ...} or (None, why). pidx: Bars.last15(day)."""
    if exp30 is None or spot is None:
        return None, "no 30-day expiry with a print on the entry day"
    px = pidx.get(occ_root(name), {})
    both = sorted({k for (e, k, r) in px if e == exp30 and r == "C" and (e, k, "P") in px})
    if not both:
        return None, "no strike of the 30-day expiry with both legs printed 15:45-15:59"
    k = min(both, key=lambda x: (abs(x - spot), x))
    c, p = px[(exp30, k, "C")], px[(exp30, k, "P")]
    return {"kind": "straddle", "expiry": exp30, "strike": k, "legs": [(c[0], 1), (p[0], 1)],
            "entry": {c[0]: (c[1], c[2]), p[0]: (p[1], p[2])}}, None


def condor_targets(spot, exp30, day, iv_day):
    """{(right, delta): target strike} for the four condor legs (R10)."""
    T = bs.t_years(IV.t_minutes(day, DECISION_MIN, exp30))
    return {(r, d): IV.strike_for_delta(spot, T, iv_day, d, r) for r in ("C", "P") for d in (CONDOR_SHORT, CONDOR_LONG)}


def condor_probe(name, spot, exp30, day, iv_day):
    """OCC symbols the pull asks for: per leg and plausible grid, the strikes around the BS target (R10)."""
    out = set()
    for (r, _d), k in condor_targets(spot, exp30, day, iv_day).items():
        out |= {occ(name, exp30, r, x) for x in IV.near_strikes(k, spot)}
    return sorted(out)


def choose_condor(name, pidx, spot, exp30, day, iv_day):
    """The 20/10-delta iron condor from printed strikes, or (None, why) (R10)."""
    if exp30 is None or spot is None:
        return None, "no 30-day expiry with a print on the entry day"
    if iv_day is None or not np.isfinite(iv_day) or iv_day <= 0:
        return None, "no D-IV 30-day IV on the entry day"
    px = pidx.get(occ_root(name), {})
    T = bs.t_years(IV.t_minutes(day, DECISION_MIN, exp30))
    calls = sorted(k for (e, k, r) in px if e == exp30 and r == "C" and k > spot)
    puts = sorted(k for (e, k, r) in px if e == exp30 and r == "P" and k < spot)

    def nearest(ks, tgt, right):
        if not ks:
            return None
        d = np.abs(IV.delta_vec(spot, np.array(ks, float), T, iv_day, right == "C"))
        return min(zip(ks, d), key=lambda z: (abs(z[1] - tgt), z[0]))

    sc = nearest(calls, CONDOR_SHORT, "C")
    sp = nearest(puts, CONDOR_SHORT, "P")
    if sc is None or sp is None:
        return None, "no printed OTM call or put for a short leg"
    lc = nearest([k for k in calls if k > sc[0]], CONDOR_LONG, "C")
    lp = nearest([k for k in puts if k < sp[0]], CONDOR_LONG, "P")
    if lc is None or lp is None:
        return None, "no printed strike beyond a short leg for its long leg"
    legs, entry = [], {}
    for (k, d), right, sign in ((sc, "C", -1), (lc, "C", 1), (sp, "P", -1), (lp, "P", 1)):
        s, m, c = px[(exp30, k, right)]
        legs.append((s, sign))
        entry[s] = (m, c)
    return {"kind": "condor", "expiry": exp30, "strikes": {"sc": sc[0], "lc": lc[0], "sp": sp[0], "lp": lp[0]},
            "deltas": {"sc": _r(sc[1], 3), "lc": _r(lc[1], 3), "sp": _r(sp[1], 3), "lp": _r(lp[1], 3)},
            "width": float(max(lc[0] - sc[0], sp[0] - lp[0])), "legs": legs, "entry": entry, "iv_day": float(iv_day)}, None


def intrinsic(sym, S):
    from .data import parse_occ
    m = parse_occ(sym)
    return max(0.0, S - m["strike"]) if m["right"] == "C" else max(0.0, m["strike"] - S)


def price_position(pos, exit_px, settle_S, name, spread):
    """P/L at every k (R6). pos: choose_straddle / choose_condor; exit_px: {occ: (minute, price)} for a traded exit, or
    None with settle_S = the stock's expiry-day close. Returns {k name: {pnl, ret, capital}} and the spread labels."""
    labels = set()
    out = {}
    for kn, k in K_LEVELS:
        cash_in, fees, cash_out = 0.0, 0.0, 0.0
        for sym, s in pos["legs"]:
            m, p = pos["entry"][sym]
            hs, lab = spread.half_spread(name, p, m)
            labels.add(lab)
            fill = p + s * k * hs if s > 0 else max(0.0, p + s * k * hs)
            cash_in += -s * fill * MULT
            fees += FEE
            if exit_px is None:
                cash_out += s * intrinsic(sym, settle_S) * MULT
            else:
                mx, px = exit_px[sym]
                hx, lab = spread.half_spread(name, px, mx)
                labels.add(lab)
                fx = max(0.0, px - s * k * hx)
                cash_out += s * fx * MULT
                fees += FEE
        n_in = len(pos["legs"]) * FEE
        pnl = cash_in + cash_out - fees
        if pos["kind"] == "straddle":
            cap = -cash_in + n_in
        else:
            credit = cash_in - n_in
            cap = MULT * pos["width"] - credit
        out[kn] = {"pnl": pnl, "capital": cap, "ret": pnl / cap if cap > 0 else None}
    return out, sorted(labels)


def position_outcome(name, t, x, kind, ctxd):
    """One name's straddle or condor over the hold (t, x): (row, None) or (None, why). ctxd: {"bars", "tab", "reports",
    "cal", "panels", "spread"}."""
    tab, bars = ctxd["tab"], ctxd["bars"]
    tt, j = tab.pos.get(t), tab.col.get(name)
    if tt is None or j is None:
        return None, "not in the D-IV table"
    exp30 = tab.exp30.get((tt, j))
    spot = tab.spot[tt, j]
    spot = float(spot) if np.isfinite(spot) else None
    pidx = bars.last15(t)
    if kind == "straddle":
        pos, why = choose_straddle(name, pidx, spot, exp30)
    else:
        pos, why = choose_condor(name, pidx, spot, exp30, t, tab.iv30[tt, j])
    if pos is None:
        return None, why
    xe, acc = hold_exit(t, x, ctxd["reports"].get(name), ctxd["cal"])
    if xe is None:
        return None, "2.02 report right after the entry's 15:45 (no hold left)"
    exp = pos["expiry"]
    settle = None
    if exp <= xe:
        settle = raw_close(ctxd["panels"], name, exp)
        if settle is None:
            return None, "no daily close on the expiry day"
        exit_px = None
    else:
        px = bars.last15(xe).get(occ_root(name), {})
        by_sym = {v[0]: (v[1], v[2]) for v in px.values()}
        if not all(s in by_sym for s, _ in pos["legs"]):
            return None, "no exit print 15:45-15:59 for every leg"
        exit_px = {s: by_sym[s] for s, _ in pos["legs"]}
    res, labels = price_position(pos, exit_px, settle, name, ctxd["spread"])
    out_day = exp if settle is not None else xe
    row = {"symbol": name, "day": out_day.isoformat(), "entry_day": t.isoformat(),
           "exit_day": out_day.isoformat(), "scheduled_exit": x.isoformat(), "report_exit": str(acc) if acc else "",
           "settled": settle is not None, "expiry": exp.isoformat(), "dte": (exp - t).days, "_src": "DEV", "entry_idx": 0,
           "legs": " ".join(f"{'+' if s > 0 else '-'}{sym}" for sym, s in pos["legs"]),
           "entry_px": " ".join(f"{pos['entry'][sym][1]:.2f}" for sym, _ in pos["legs"]),
           "exit_px": " ".join(f"{exit_px[sym][1]:.2f}" for sym, _ in pos["legs"]) if exit_px else f"settled at {settle:.2f}",
           "spread_label": "+".join(labels), "label": f"{REAL}; DEV; {LOOKAHEAD}" + (f"; {SB}" if name not in U.U_ETF else "")}
    if kind == "straddle":
        row["strike"] = pos["strike"]
    else:
        row.update({f"k_{k}": v for k, v in pos["strikes"].items()})
        row.update({f"delta_{k}": v for k, v in pos["deltas"].items()})
        row["width"], row["iv_day"] = pos["width"], _r(pos["iv_day"], 4)
    for kn, v in res.items():
        row[f"pnl_{kn}"] = round(v["pnl"], 2)
        row[f"ret_{kn}"] = _r(v["ret"], 6)
        row[f"capital_{kn}"] = round(v["capital"], 2)
    row["pnl"], row["pnl_2x"], row["ret"] = row["pnl_100"], row["pnl_2x"], row["ret_100"]
    row["debit" if kind == "straddle" else "margin"] = row["capital_100"]
    return row, None


def vol_outcomes(hold_list, ctxd, rv_by_day, log=None):
    """Everything V1, V2 and V2-s need, per hold: eligible names, keys, picks and every eligible name's outcome."""
    tab = ctxd["tab"]
    res = []
    for n, (t, x) in enumerate(hold_list):
        names = [nm for nm in ctxd["universe"].names(t) if nm in tab.col]
        k = keys_on(t, tab, names, rv_by_day(t, names))
        el1, el2 = sorted(k["slope"]), sorted(k["ratio"])
        st, cd, why = {}, {}, defaultdict(int)
        for nm in sorted(set(el1) | set(el2)):
            row, w = position_outcome(nm, t, x, "straddle", ctxd)
            st[nm] = row
            if row is None:
                why[f"straddle: {w}"] += 1
        for nm in el2:
            row, w = position_outcome(nm, t, x, "condor", ctxd)
            cd[nm] = row
            if row is None:
                why[f"condor: {w}"] += 1
        res.append({"t": t, "x": x, "keys": k, "eligible": {"V1": el1, "V2": el2, "V2-s": el2},
                    "picks": {"V1": top(k["slope"]), "V2": top(k["ratio"]), "V2-s": top(k["ratio"], bottom=True)},
                    "straddle": st, "condor": cd, "skips": dict(why)})
        if log:
            log(f"  V1/V2 hold {t}..{x}: {len(el1)} names with a slope, {len(el2)} with a ratio")
    return res


VARIANTS = {"V1": ("term_slope", "straddle", "slope"), "V2": ("rv_iv_gap", "straddle", "ratio"),
            "V2-s": ("rv_iv_rich", "condor", "ratio")}


def rule_positions(outs, v):
    """The rule's priced positions and the selected names it could not price."""
    name, kind, key = VARIANTS[v]
    rows, skips = [], defaultdict(int)
    for o in outs:
        for rank, nm in enumerate(o["picks"][v], 1):
            r = o[kind].get(nm)
            if r is None:
                skips["selected name not priced"] += 1
                continue
            rows.append(dict(r, variant=name, rank=rank, key=_r(o["keys"][key][nm], 6)))
    return rows, dict(skips)


def benchmark(outs, v, seeds=RANDOM_SEEDS, k="100"):
    """R8: (90th percentile, draw means)."""
    _n, kind, _key = VARIANTS[v]
    means = []
    for s in seeds:
        rng = np.random.default_rng(s)
        vals = []
        for o in outs:
            el = o["eligible"][v]
            if not el:
                continue
            pick = rng.choice(len(el), size=min(TOP_N, len(el)), replace=False)
            for i in sorted(int(z) for z in pick):
                r = o[kind].get(el[i])
                if r is not None and r.get(f"ret_{k}") is not None:
                    vals.append(float(r[f"ret_{k}"]))
        if vals:
            means.append(float(np.mean(vals)))
    means = np.array(means)
    return (round(float(np.percentile(means, BENCH_PCT)), 6) if len(means) else None), means


def pf_ret(r):
    r = np.asarray([x for x in r if x is not None], float)
    lo, w = -r[r < 0].sum(), r[r > 0].sum()
    return round(float(w / lo), 3) if lo > 0 else (math.inf if w > 0 else None)


def kstats(rows, k):
    rets = [float(r[f"ret_{k}"]) for r in rows if r.get(f"ret_{k}") is not None]
    pnl = np.array([float(r[f"pnl_{k}"]) for r in rows]) if rows else np.zeros(0)
    if not rows:
        return {"positions": 0}
    eq = np.cumsum(pnl[np.argsort([r["day"] for r in rows], kind="stable")])
    dd = float((eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min()) if len(eq) else 0.0
    w = [x for x in rets if x > 0]
    lo = [x for x in rets if x < 0]
    return {"positions": len(rows), "win_rate": round(len(w) / len(rets), 3) if rets else None, "mean_ret": _r(np.mean(rets), 6) if rets else None,
            "avg_win_ret": _r(np.mean(w), 4) if w else None, "avg_loss_ret": _r(np.mean(lo), 4) if lo else None,
            "pf_ret": pf_ret(rets), "pnl_total": round(float(pnl.sum()), 2), "expectancy": round(float(pnl.mean()), 2),
            "pf_dollars": shares._pf(pnl), "max_dd": round(min(dd, 0.0), 2)}


def boot_ci(rows, k="100", seed=BOOT_SEED, draws=BOOT_DRAWS):
    """Bootstrap 95% CI of the mean return per position, resampling rebalance sessions (information)."""
    by = defaultdict(list)
    for r in rows:
        if r.get(f"ret_{k}") is not None:
            by[r["entry_day"]].append(float(r[f"ret_{k}"]))
    keys = sorted(by)
    if len(keys) < 2:
        return None
    rng = np.random.default_rng(seed)
    sums = np.array([sum(by[d]) for d in keys])
    cnts = np.array([len(by[d]) for d in keys])
    means = np.empty(draws)
    for i in range(draws):
        ix = rng.integers(0, len(keys), len(keys))
        means[i] = sums[ix].sum() / max(cnts[ix].sum(), 1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return round(float(lo), 5), round(float(hi), 5)


def blocks(rows, k="100"):
    out = {}
    for name, a, b in BLOCKS:
        sub = [float(r[f"ret_{k}"]) for r in rows if a <= r["day"] <= b and r.get(f"ret_{k}") is not None]
        out[name] = {"positions": len(sub), "mean_ret": _r(np.mean(sub), 6) if sub else None}
    return out


def vol_pass(rows, p90):
    s = kstats(rows, "100")
    bl = blocks(rows)
    green = sum(1 for v in bl.values() if v["mean_ret"] is not None and v["mean_ret"] > 0)
    pf = s.get("pf_ret")
    pfr = -1.0 if pf is None else pf
    mean = s.get("mean_ret")
    checks = [(f"at least {MIN_POSITIONS} positions ({s['positions']})", s["positions"] >= MIN_POSITIONS),
              (f"PF >= {PF_MIN} at 100% of the spread (on returns: {pf})", pfr >= PF_MIN),
              (f"mean return per position above the random draws' 90th percentile ({_pct(mean)} vs {_pct(p90)})",
               mean is not None and p90 is not None and mean > p90),
              (f"positive in at least {BLOCKS_MIN} of the 6 two-month blocks of 2025-07..2026-06 ({green} of 6)", green >= BLOCKS_MIN)]
    return {"checks": checks, "pass": all(ok for _, ok in checks), "blocks": bl, "p90_random": p90}


def _pct(x):
    return "-" if x is None else f"{100 * x:.2f}%"


def overlap(outs):
    per, tot, n = {}, 0, 0
    for o in outs:
        a, b = set(o["picks"]["V1"]), set(o["picks"]["V2"])
        if a or b:
            per[o["t"].isoformat()] = len(a & b)
            tot += len(a & b)
            n += len(b)
    return {"per_rebalance": per, "total_shared": tot, "share_of_v2_names_in_v1": round(tot / n, 3) if n else None}


def vol_family(outs, seeds=RANDOM_SEEDS):
    """V1, V2 and V2-s results from vol_outcomes."""
    res, rows_all = {}, {}
    for v in VARIANTS:
        rows, sk = rule_positions(outs, v)
        p90, means = benchmark(outs, v, seeds)
        pb = vol_pass(rows, p90)
        res[v] = {"name": VARIANTS[v][0], "kind": VARIANTS[v][1], "levels": {kn: kstats(rows, kn) for kn, _ in K_LEVELS},
                  "pass_bar": pb, "pass": pb["pass"], "skips": sk, "boot_ci_100": boot_ci(rows),
                  "random": {"draws": int(len(means)), "mean": _r(np.mean(means), 6) if len(means) else None, "p90": p90},
                  "label": (PAPER + "; " if v == "V2-s" else "") + f"{REAL}; return on " + ("margin" if v == "V2-s" else "debit")}
        rows_all[v] = rows
    res["overlap_V1_V2"] = overlap(outs)
    res["holds"] = [{"t": o["t"].isoformat(), "x": o["x"].isoformat(), "eligible_V1": len(o["eligible"]["V1"]),
                     "eligible_V2": len(o["eligible"]["V2"]), "skips": o["skips"]} for o in outs]
    return res, rows_all


# ---------------------------------------------------------------- V3 earn_runup (shares)
def ret_12_1(panel):
    """(T, N) close 21 bars back / close 252 bars back - 1, each name's own bars inside one segment (R12)."""
    C = panel.adj_c
    out = np.full(C.shape, np.nan)
    for a, b in panel.bounds:
        blk = C[a:b]
        for j in range(C.shape[1]):
            ix = np.flatnonzero(np.isfinite(blk[:, j]))
            if len(ix) <= 252:
                continue
            q = np.arange(252, len(ix))
            with np.errstate(invalid="ignore", divide="ignore"):
                out[a + ix[q], j] = blk[ix[q - 21], j] / blk[ix[q - 252], j] - 1.0
    return out


def report_exit_entry(a, cal):
    """(entry session, exit session) for a 2.02 accepted at `a` (R11), or None."""
    d = a.date()
    x = d if (cal.is_session(d) and (a.hour, a.minute) >= (16, 0)) else cal.back(d, 1)
    e = cal.back(d, V3_BEFORE)
    if x is None or e is None or e >= x:
        return None
    return e, x


def v3_events(records, tmap, cal):
    """[{"symbol", "accepted", "d", "entry", "exit"}]: one per symbol and acceptance date (the earliest)."""
    best = {}
    for sym, acc in report_times(records, tmap).items():
        for a in acc:
            key = (sym, a.date())
            if key not in best or a < best[key]:
                best[key] = a
    out = []
    for (sym, d), a in sorted(best.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        ex = report_exit_entry(a, cal)
        if ex is None:
            continue
        out.append({"symbol": sym, "accepted": a, "d": d, "entry": ex[0], "exit": ex[1]})
    return out


def v3_trades(panel, events, r121=None, stk=None):
    """V3 share trades and info. panel: the combined panel; stk: bool mask of its U-STK columns (default: every column not in
    U-ETF). Only U-STK names trade and rank."""
    r121 = ret_12_1(panel) if r121 is None else r121
    stk = np.array([s not in U.U_ETF for s in panel.symbols], bool) if stk is None else stk
    elig = panel.eligible() & stk[None, :]
    out, dropped = [], defaultdict(int)
    for ev in events:
        j = panel.col.get(ev["symbol"])
        if j is None or not stk[j]:
            dropped["not a U-STK name in the panel"] += 1
            continue
        e, x = panel.idx(ev["entry"]), panel.idx(ev["exit"])
        if e is None or x is None or U.touches_locked(ev["entry"], ev["exit"]) or not M.ok_window(panel, e, x):
            dropped["window touches L1/L2 or leaves its trade window"] += 1
            continue
        if not elig[e, j]:
            dropped["fails the U-STK filter on the entry day"] += 1
            continue
        v = r121[e, j]
        if not np.isfinite(v):
            dropped["no 12-1 return on the entry day"] += 1
            continue
        vals = r121[e][elig[e] & np.isfinite(r121[e])]
        better = int((vals > v).sum())
        if not better < V3_TOP * len(vals):
            dropped["not in the top 10% by 12-1 return"] += 1
            continue
        ce, cx, rc = panel.adj_c[e, j], panel.adj_c[x, j], panel.raw_c[e, j]
        if not (np.isfinite(ce) and np.isfinite(cx) and np.isfinite(rc)):
            dropped["no close on the entry or exit day"] += 1
            continue
        tr = M.make_trade("earn_runup", "U-STK", ev["symbol"], panel, e, x, float(rc), float(rc), float(cx / ce), "close",
                          f"5 sessions before the 2.02 accepted {ev['accepted']}; out at the last close before it",
                          {"signal_day": ev["entry"].isoformat(), "accepted": str(ev["accepted"]), "report_date": ev["d"].isoformat(),
                           "ret_12_1": _r(v, 5), "rank_share": round(better / len(vals), 4), "universe_n": int(len(vals)),
                           "label": f"{SB}; {LOOKAHEAD}"})
        if tr:
            out.append(tr)
    return out, {"events": len(events), "dropped": dict(dropped)}


def report_positions(records, tmap, cal):
    """{symbol: sorted calendar positions of its report sessions} (first session on/after each 2.02 acceptance date)."""
    out = {}
    for sym, acc in report_times(records, tmap).items():
        ps = set()
        for a in acc:
            s = cal.first_on_or_after(a.date())
            if s is not None:
                ps.add(cal.pos[s])
        out[sym] = np.array(sorted(ps), int)
    return out


def _far(cal_pos, reps, gap=V3_GAP):
    """bool array: each calendar position at least `gap` sessions from every report position."""
    cal_pos = np.asarray(cal_pos, int)
    if reps is None or not len(reps):
        return np.ones(len(cal_pos), bool)
    i = np.searchsorted(reps, cal_pos)
    lo = np.where(i > 0, np.abs(cal_pos - reps[np.maximum(i - 1, 0)]), 10 ** 9)
    hi = np.where(i < len(reps), np.abs(reps[np.minimum(i, len(reps) - 1)] - cal_pos), 10 ** 9)
    return np.minimum(lo, hi) >= gap


def v3_candidates(panel, sym, h, reps, cal, dev_only=False):
    """Panel indices e of random entries (R13) for one symbol and holding length h (sessions)."""
    j = panel.col.get(sym)
    T = len(panel.days)
    if j is None or h <= 0 or h >= T:
        return np.zeros(0, int)
    e = np.arange(0, T - h)
    x = e + h
    win = np.array([-1 if U.window_id(d) is None else U.window_id(d) for d in panel.days])
    ok = (panel.seg[e] == panel.seg[x]) & (win[e] >= 0) & (win[e] == win[x])
    if dev_only:
        ok &= win[e] == 1
    ok &= np.isfinite(panel.adj_c[e, j]) & np.isfinite(panel.adj_c[x, j]) & np.isfinite(panel.raw_c[e, j])
    ok &= panel.eligible()[e, j]
    cp = np.array([cal.pos.get(d, -10 ** 6) for d in panel.days])
    ok &= _far(cp[e], reps, V3_GAP) & _far(cp[x], reps, V3_GAP)
    return e[ok]


def v3_random(panel, trades, reps, cal, seeds=RANDOM_SEEDS):
    """Part F's item 6 for V3 with R13's dates: (p, totals, info)."""
    if not trades:
        return None, np.zeros(0), {}
    groups = defaultdict(int)
    for t in trades:
        groups[(t["symbol"], int(t["hold"]))] += 1
    vecs, ns, empty = [], [], 0
    for key in sorted(groups):
        sym, h = key
        e = v3_candidates(panel, sym, h, reps.get(sym), cal)
        if not len(e):
            empty += groups[key]
            continue
        j = panel.col[sym]
        ri = panel.raw_c[e, j]
        xr = ri * panel.adj_c[e + h, j] / panel.adj_c[e, j]
        sh = np.floor(M.NOTIONAL / ri)
        vecs.append(sh * (xr - ri) - M.STK_PCT * sh * (ri + xr))
        ns.append(groups[key])
    if not vecs:
        return None, np.zeros(0), {"trades_without_random_days": empty}
    lens = np.array([len(v) for v in vecs])
    offs = np.concatenate([[0], np.cumsum(lens)[:-1]])
    allv = np.concatenate(vecs)
    ro, rl = np.repeat(offs, ns), np.repeat(lens, ns)
    actual = sum(float(t["pnl"]) for t in trades)
    tots = np.empty(len(seeds))
    for k, s in enumerate(seeds):
        u = np.random.default_rng(s).random(len(ro))
        tots[k] = allv[ro + np.minimum((u * rl).astype(np.int64), rl - 1)].sum()
    return round(float((tots >= actual - 1e-9).mean()), 4), tots, {"groups": len(vecs), "trades_without_random_days": empty}


# ---------------------------------------------------------------- V3 options twin
def expiry_after(dt):
    """[[first Friday expiry whose 16:00 is after dt], [the first monthly after dt]] (R14)."""
    def ok(e):
        return datetime(e.year, e.month, e.day, 16, 0) > dt
    a = dt.date()
    f = next(e for e in IV.friday_expiries(a, a + timedelta(days=14)) if ok(e))
    m = next(e for e in IV.monthly_expiries(a, a + timedelta(days=70)) if ok(e))
    return [[f]] + ([[m]] if m != f else [])


def v3_twin_items(trades, panel, reps, cal, seed=V3_POOL_SEED, per=V3_POOL):
    """The twin's events (DEV share trades) and G2-style fixed pool of random dates: [{"kind", "n", "symbol", "entry",
    "exit", "after" (datetime the expiry must follow), "S"}]."""
    ev = [t for t in sorted(trades, key=lambda t: (t["entry_day"], t["symbol"]))
          if DEV_A.isoformat() <= t["entry_day"] and t["exit_day"] <= DEV_B.isoformat()]
    items = []
    rng = np.random.default_rng(seed)
    for n, t in enumerate(ev):
        e, x = date.fromisoformat(t["entry_day"]), date.fromisoformat(t["exit_day"])
        items.append({"kind": "event", "n": n, "symbol": t["symbol"], "entry": e, "exit": x,
                      "after": datetime.fromisoformat(t["accepted"]), "S": float(t["entry_ref"])})
        c = v3_candidates(panel, t["symbol"], int(t["hold"]), reps.get(t["symbol"]), cal, dev_only=True)
        if not len(c):
            continue
        pick = rng.choice(len(c), size=min(per, len(c)), replace=False)
        j = panel.col[t["symbol"]]
        for i in sorted(int(z) for z in pick):
            k = int(c[i])
            ee, xx = panel.days[k], panel.days[k + int(t["hold"])]
            items.append({"kind": "pool", "n": n, "symbol": t["symbol"], "entry": ee, "exit": xx,
                          "after": datetime(xx.year, xx.month, xx.day, 16, 0), "S": float(panel.raw_c[k, j])})
    return items


def v3_probe(it):
    lo, hi = V3_STRIKES
    ks = IV.band_strikes(lo * it["S"], hi * it["S"], it["S"])
    return [[occ(it["symbol"], e, "C", k) for e in ph for k in ks] for ph in expiry_after(it["after"])]


def pick_last15(name, day, pidx, sm, expiries, band):
    """Calls of the first expiry in `expiries` with a 15:45-15:59 print: BS-EST delta in band, nearest the target (ties:
    lower premium, then symbol). (info, None) or (None, why)."""
    lo, hi, tgt = band
    px = pidx.get(occ_root(name), {})
    mins = (sm or {}).get(name) or {}
    for e in expiries:
        cs = [(k, v) for (ee, k, r), v in px.items() if ee == e and r == "C"]
        if not cs:
            continue
        S = np.array([mins.get(v[1], np.nan) for _k, v in cs], float)
        K = np.array([k for k, _ in cs], float)
        P = np.array([v[2] for _, v in cs], float)
        T = np.array([bs.t_years(IV.t_minutes(day, v[1], e)) for _, v in cs], float)
        iv = IV.iv_vec(P, S, K, T, True)
        d = IV.delta_vec(S, K, T, iv, True)
        best = None
        for (k, v), dd, vv in zip(cs, d, iv):
            if not np.isfinite(dd) or not lo <= dd <= hi:
                continue
            key = (abs(dd - tgt), v[2], v[0])
            if best is None or key < best[0]:
                best = (key, {"symbol": v[0], "strike": k, "expiry": e.isoformat(), "px": v[2], "minute": v[1],
                              "delta": round(float(dd), 3), "iv": round(float(vv), 4), "dte": (e - day).days})
        if best is None:
            return None, f"first expiry after the report ({e}): no call with BS-EST delta in {lo:.2f}-{hi:.2f}"
        return best[1], None
    return None, "no call of the first expiry after the report printed 15:45-15:59"


def opt_leg(b_in, b_out, pct=OPT_HS, k=1.0):
    hi, ho = max(pct * b_in, OPT_FLOOR), max(pct * b_out, OPT_FLOOR)
    return MULT * (max(0.0, b_out - k * ho) - (b_in + k * hi)) - 2 * FEE


def v3_twin_row(it, bars, spread):
    """(row, None) or (None, why) for one twin event or pool item."""
    sm = bars.stock_minutes(it["entry"])
    if sm is None:
        return None, "no stock15 file on the entry day (pull stage stock15)"
    exps = [e for ph in expiry_after(it["after"]) for e in ph]
    info, why = pick_last15(it["symbol"], it["entry"], bars.last15(it["entry"]), sm, exps, V3_BAND)
    if info is None:
        return None, why
    px = bars.last15(it["exit"]).get(occ_root(it["symbol"]), {})
    out = {v[0]: v for v in px.values()}
    if info["symbol"] not in out:
        return None, "no print of the chosen call 15:45-15:59 on the exit day"
    b_in, b_out, mx = info["px"], out[info["symbol"]][2], out[info["symbol"]][1]
    h_in, _ = spread.half_spread(it["symbol"], b_in, info["minute"])
    h_out, lab = spread.half_spread(it["symbol"], b_out, mx)
    meas = MULT * (max(0.0, b_out - h_out) - (b_in + h_in)) - 2 * FEE
    return {"variant": "earn_runup_opt" if it["kind"] == "event" else "earn_runup_opt_pool", "event": it["n"],
            "symbol": it["symbol"], "day": it["exit"].isoformat(), "entry_day": it["entry"].isoformat(),
            "exit_day": it["exit"].isoformat(), "_src": "DEV", "side": "C", "contract": info["symbol"], "strike": info["strike"],
            "expiry": info["expiry"], "dte": info["dte"], "delta_est": info["delta"], "iv_est": info["iv"],
            "entry_basis": b_in, "exit_basis": b_out, "debit": round(MULT * (b_in + max(OPT_HS * b_in, OPT_FLOOR)) + FEE, 2),
            "pnl": round(opt_leg(b_in, b_out), 2), "pnl_2x": round(opt_leg(b_in, b_out, k=2.0), 2),
            "pnl_spread_model": round(meas, 2), "spread_model_label": lab, "entry_idx": 0, "entry_time": "15:45",
            "label": f"{REAL}; {SB}; {LOOKAHEAD}"}, None


def twin_random(rows, pool_rows, seeds=RANDOM_SEEDS):
    """R14: p = the share of draws whose mean P/L per event is at or above the twin's (one priced pool date per event)."""
    by = defaultdict(list)
    for r in pool_rows:
        by[int(r["event"])].append(float(r["pnl"]))
    keys = sorted(k for k, v in by.items() if v)
    if not rows or not keys:
        return None, np.zeros(0), len(keys)
    actual = float(np.mean([float(r["pnl"]) for r in rows]))
    means = np.empty(len(seeds))
    for i, s in enumerate(seeds):
        rng = np.random.default_rng(s)
        means[i] = np.mean([by[k][int(rng.integers(0, len(by[k])))] for k in keys])
    return round(float((means >= actual - 1e-9).mean()), 4), means, len(keys)


# ---------------------------------------------------------------- V4 new_high (shares)
def atr_wilder(panel, n=V4_ATR):
    """(T, N) Wilder ATR(n) of split-adjusted bars, each name's own bars inside one segment."""
    H, L, C = panel.adj_h, panel.adj_l, panel.adj_c
    T, N = C.shape
    out = np.full((T, N), np.nan)
    last = np.full(N, np.nan)
    cnt, ssum, atr = np.zeros(N, int), np.zeros(N), np.full(N, np.nan)
    for t in range(T):
        if t and panel.seg[t] != panel.seg[t - 1]:
            last[:] = np.nan
            cnt[:] = 0
            ssum[:] = 0.0
            atr[:] = np.nan
        h, lo, c = H[t], L[t], C[t]
        have = np.isfinite(h) & np.isfinite(lo) & np.isfinite(c)
        ok = have & np.isfinite(last)
        pc = np.where(np.isfinite(last), last, 0.0)
        tr = np.maximum(h - lo, np.maximum(np.abs(h - pc), np.abs(lo - pc)))
        tr = np.where(ok, tr, 0.0)
        cnt = np.where(ok, cnt + 1, cnt)
        ssum = np.where(ok & (cnt <= n), ssum + tr, ssum)
        atr = np.where(ok & (cnt == n), ssum / n, np.where(ok & (cnt > n), (atr * (n - 1) + tr) / n, atr))
        out[t] = np.where(have & (cnt >= n), atr, np.nan)
        last = np.where(have, c, last)
    return out


def high_prior(panel, n=V4_LOOK):
    """(T, N) the max of the name's previous n closes (own bars inside one segment), NaN with fewer than n."""
    C = panel.adj_c
    out = np.full(C.shape, np.nan)
    for a, b in panel.bounds:
        blk = C[a:b]
        for j in range(C.shape[1]):
            ix = np.flatnonzero(np.isfinite(blk[:, j]))
            if len(ix) <= n:
                continue
            mx = pd.Series(blk[ix, j]).rolling(n).max().shift(1).to_numpy()
            out[a + ix[n:], j] = mx[n:]
    return out


def v4_book(panel, univ_of, slots=V4_SLOTS):
    """V4 share trades on one HLPanel holding U-ETF and U-STK columns. univ_of: {symbol: "U-ETF" / "U-STK"}."""
    C, T = panel.adj_c, len(panel.days)
    hp, atr = high_prior(panel), atr_wilder(panel)
    dv = panel.rolling_mean(panel.raw_c * panel.raw_v, 20)
    elig = panel.eligible()
    is_stk = np.array([univ_of.get(s) == "U-STK" for s in panel.symbols])
    with np.errstate(invalid="ignore"):
        sig = np.isfinite(C) & np.isfinite(hp) & (C >= hp)
    held = {}                                 # j -> {"e", "t", "sp", "hc", "stop"}
    out, dropped = [], defaultdict(int)
    info = {"signals": int(sig.sum()), "entries": 0, "no_slot": 0}
    for t in range(T):
        if t and panel.seg[t] != panel.seg[t - 1]:
            if held:
                dropped["still open at the L2 gap (exit would be in L2)"] += len(held)
            held = {}
        exiting = []
        for j, h in list(held.items()):
            if t < h["e"]:
                continue
            c = C[t, j]
            if t > h["e"] and np.isfinite(c) and np.isfinite(h["stop"]) and c < h["stop"]:
                x = M._next_open(panel, j, t)
                exiting.append(j)
                del held[j]
                if x is None:
                    dropped["exit after the segment / data end (would touch a locked period)"] += 1
                    continue
                if not M.ok_window(panel, h["e"], x):
                    dropped["holding window touches L1/L2 or leaves its window"] += 1
                    continue
                univ = univ_of[panel.symbols[j]]
                tr = M.make_trade("new_high", univ, panel.symbols[j], panel, h["e"], x, h["sp"], float(panel.raw_o[h["e"], j]),
                                  float(panel.adj_o[x, j] / panel.adj_o[h["e"], j]), "open",
                                  f"close {c:.2f} < stop {h['stop']:.2f} on {panel.days[t]}: out at the next open",
                                  {"signal_day": panel.days[h["t"]].isoformat(), "stop_at_exit": round(float(h["stop"]), 4),
                                   "high_since_entry": round(float(h["hc"]), 4)})
                if tr:
                    out.append(tr)
                continue
            if np.isfinite(c):
                h["hc"] = max(h["hc"], c) if np.isfinite(h["hc"]) else c
                if np.isfinite(atr[t, j]):
                    cand = h["hc"] - V4_MULT * atr[t, j]
                    h["stop"] = max(h["stop"], cand) if np.isfinite(h["stop"]) else cand
        cand = np.flatnonzero(sig[t])
        if not len(cand):
            continue
        picks = []
        for j in cand:
            if j in held:
                continue
            e = M._next_open(panel, j, t)
            if e is None or not U.in_trade_window(panel.days[e]):
                continue
            if is_stk[j] and not elig[e, j]:
                continue
            picks.append((-(dv[t, j] if np.isfinite(dv[t, j]) else -np.inf), panel.symbols[j], j, e))
        picks.sort()
        free = slots - len(held)
        if len(picks) > free:
            info["no_slot"] += len(picks) - max(free, 0)
        for _d, _s, j, e in picks[:max(free, 0)]:
            held[j] = {"e": e, "t": t, "sp": float(panel.raw_c[t, j]), "hc": np.nan, "stop": np.nan}
            info["entries"] += 1
    if held:
        dropped["still open when the data end (exit would be in L1)"] += len(held)
    info["dropped"] = dict(dropped)
    return out, info


def top_share(trades, frac=V4_TOP):
    """Share of the total P/L made by the top `frac` of trades (by P/L)."""
    p = np.sort(np.array([float(t["pnl"]) for t in trades]))[::-1]
    if not len(p):
        return {"trades": 0}
    k = max(1, int(math.ceil(frac * len(p))))
    tot = float(p.sum())
    return {"trades": int(len(p)), "top_n": k, "top_pnl": round(float(p[:k].sum()), 2), "total": round(tot, 2),
            "share": round(float(p[:k].sum()) / tot, 3) if tot > 0 else None}


def v4_windows(trades):
    return {name: shares.stats([t for t in trades if a <= t["day"] <= b]) for name, a, b in WINDOWS_V4}


def v4_panel(panels):
    """The combined panel (U-ETF and U-STK columns; the book trades both) and each column's universe."""
    return panels["all"], panels["univ"]


def v4_random(panel, trades):
    """Part F's item 6 per universe, the draw totals added (R15)."""
    tots, info, actual = None, {}, 0.0
    for univ in ("U-ETF", "U-STK"):
        tr = [t for t in trades if t["universe"] == univ]
        if not tr:
            continue
        p, t_, inf = M.random_entry(panel, tr, univ)
        info[univ] = dict(inf, p=p)
        if not len(t_):
            continue
        tots = t_ if tots is None else tots + t_
        actual += sum(float(t["pnl"]) for t in tr)
    if tots is None:
        return None, np.zeros(0), info
    return round(float((tots >= actual - 1e-9).mean()), 4), tots, info


# ---------------------------------------------------------------- V4 options twin
def v4_probe(sym, day, S):
    a, b = day + timedelta(days=V4_DTE[0]), day + timedelta(days=V4_DTE[1])
    exps = sorted(set(IV.friday_expiries(a, b)) | set(IV.quarter_ends(a, b)))
    ks = IV.band_strikes(V4_STRIKES[0] * S, V4_STRIKES[1] * S, S)
    return [occ(sym, e, "C", k) for e in exps for k in ks]


def pick_open(name, day, opens, S, band=V4_BAND, dte=V4_DTE):
    """F-opt's pick (contracts.pick_daily) with V4's band and DTE: (info, None) or (None, why)."""
    lo, hi, tgt = band
    px = opens.get(occ_root(name), {})
    cs = [(e, k, v) for (e, k, r), v in px.items() if r == "C" and dte[0] <= (e - day).days <= dte[1]]
    if not cs or not (S and S > 0):
        return None, f"no call {dte[0]}-{dte[1]} days out with a print at the open"
    best = None
    for e in sorted({c[0] for c in cs}):
        grp = [c for c in cs if c[0] == e]
        T = bs.t_years(390 + 1440 * (e - day).days)
        iv, d = bs.iv_delta_v(np.array([c[2][2] for c in grp], float), float(S), np.array([c[1] for c in grp], float), T,
                              np.ones(len(grp), bool))
        for (ee, k, v), vv, dd in zip(grp, iv, d):
            if not np.isfinite(dd) or not lo <= dd <= hi:
                continue
            key = (abs(dd - tgt), v[2], ee, v[0])
            if best is None or key < best[0]:
                best = (key, {"symbol": v[0], "strike": k, "expiry": ee, "px": v[2], "delta": round(float(dd), 3),
                              "iv": round(float(vv), 4), "dte": (ee - day).days})
    if best is None:
        return None, f"no call with BS-EST delta in {lo:.2f}-{hi:.2f}"
    return best[1], None


def v4_twin_walk(tr, bars, raw_open, sessions):
    """Walk one V4 share trade's call twin (R16). Returns ("need", (day, window, symbols)) for the first missing file
    part, ("skip", why), or ("row", row). raw_open(day) -> the stock's raw open; sessions: DEV sessions (dates)."""
    sym = tr["symbol"]
    e, x = date.fromisoformat(tr["entry_day"]), date.fromisoformat(tr["exit_day"])

    def cands(day):
        S = raw_open(day)
        if S is None:
            return None, "no stock open"
        want = v4_probe(sym, day, S)
        miss = [s for s in want if s not in bars.asked(day, IV.W_OPEN)]
        if miss:
            return ("need", (day, IV.W_OPEN, miss)), None
        return pick_open(sym, day, bars.opens(day), S)

    info, why = cands(e)
    if isinstance(info, tuple):
        return info
    if info is None:
        return "skip", f"entry: {why}"
    legs = [{"buy_day": e.isoformat(), "contract": info["symbol"], "buy": info["px"], "delta": info["delta"], "dte": info["dte"]}]
    held = info
    for s in [d for d in sessions if e < d <= x]:
        if s != x and (held["expiry"] - s).days > V4_ROLL:
            continue
        if held["symbol"] not in bars.asked(s, IV.W_DAY):
            return "need", (s, IV.W_DAY, [held["symbol"]])
        fp = bars.first_prints(s).get(held["symbol"])
        if fp is None:
            return "skip", f"no print of the held call on {s}"
        legs[-1].update({"sell_day": s.isoformat(), "sell": fp[1], "sell_minute": fp[0], "late": fp[0] > 4})
        if s == x:
            break
        nxt, why = cands(s)
        if isinstance(nxt, tuple):
            return nxt
        if nxt is None:
            return "skip", f"roll on {s}: {why}"
        legs.append({"buy_day": s.isoformat(), "contract": nxt["symbol"], "buy": nxt["px"], "delta": nxt["delta"], "dte": nxt["dte"]})
        held = nxt
    if "sell" not in legs[-1]:
        return "skip", "the exit day is not a DEV session on file"
    pnl = sum(opt_leg(g["buy"], g["sell"]) for g in legs)
    pnl2 = sum(opt_leg(g["buy"], g["sell"], k=2.0) for g in legs)
    return "row", {"variant": "new_high_opt", "symbol": sym, "day": x.isoformat(), "entry_day": e.isoformat(), "exit_day": x.isoformat(),
                   "_src": "DEV", "side": "C", "contract": legs[0]["contract"], "rolls": len(legs) - 1, "legs": json.dumps(legs),
                   "delta_est": legs[0]["delta"], "dte": legs[0]["dte"],
                   "debit": round(MULT * (legs[0]["buy"] + max(OPT_HS * legs[0]["buy"], OPT_FLOOR)) + FEE, 2),
                   "pnl": round(pnl, 2), "pnl_2x": round(pnl2, 2), "share_pnl": tr["pnl"], "entry_idx": 0, "entry_time": "09:30",
                   "exit_late": any(g.get("late") for g in legs), "label": REAL + ("" if sym in U.U_ETF else f"; {SB}")}


# ---------------------------------------------------------------- the compounding view (hook)
def compounding_view(name, rows, kind):
    """HOOK (round 10 integrator): Amendment 16's compounding view ($3,000 account, 2,000 bootstrap paths of the holdout
    trades resampled by session; fixed-fractional risk 1%, 2% and 5%) lives in sprint/compound.py, built by another builder.
    This calls compound.view(rows, kind=..., name=...) when that module exists; until then it returns a marked placeholder."""
    try:
        from . import compound  # noqa: F401  (another builder's module; absent on this branch)
    except ImportError:
        return {"hook": "sprint/compound.py is not on this branch yet; the integrator wires compounding_view()", "rule": name,
                "trades": len(rows)}
    fn = getattr(compound, "view", None)
    if fn is None:
        return {"hook": "sprint/compound.py has no view(); the integrator adapts compounding_view()", "rule": name}
    try:
        return fn(rows, kind=kind, name=name)
    except TypeError as e:
        return {"hook": f"sprint/compound.view signature differs ({e}); the integrator adapts compounding_view()", "rule": name}


# ---------------------------------------------------------------- the pull's provider (tools/sprint_pull10.py)
def _memo(ctx, key, fn):
    if key not in ctx.cache:
        ctx.cache[key] = fn()
    return ctx.cache[key]


def _inputs(ctx):
    return _memo(ctx, "r10_panels", lambda: load_panels(ctx.root, ctx.log))


def _edgar_in(ctx):
    return _memo(ctx, "r10_edgar", lambda: load_edgar(ctx.root))


def needs_vol(ctx):
    """V1/V2/V2-s: condor legs on each rebalance day, then every eligible name's exit legs. Waits until D-IV has finished
    the rebalance day and the 5 sessions before it."""
    recs, tmap = _edgar_in(ctx)
    if not recs:
        ctx.warn("V1/V2/V2-s: no EDGAR records (round 9's edgar stages): the 2.02 exits cannot be placed; nothing pulled")
        return []
    panels = _inputs(ctx)
    reports = _memo(ctx, "r10_reports", lambda: report_times(recs, tmap))
    cal = _memo(ctx, "r10_cal", edgar.Calendar)
    rvp = _memo(ctx, "r10_rv", lambda: rv252_prior(panels["all"]) if panels["all"].symbols else None)
    days = IV.dev_days()
    pos = {d: k for k, d in enumerate(days)}
    scope = set(ctx.days)
    out = []
    a, b = _span(ctx)
    for t, x in holds()[0]:
        k = pos.get(t)
        if not a <= t <= b or t not in scope or k is None or k < IV.MEAN_N or not all(ctx.is_done(d, "div") for d in days[k - IV.MEAN_N:k + 1]):
            continue
        names = ctx.universe(t)
        res = {d: ctx.div_result(d, names) for d in days[k - IV.MEAN_N:k + 1]}
        tab = IV.IVTable(days[k - IV.MEAN_N:k + 1], names)
        for d, rr in res.items():
            for n, rec in rr.items():
                tab.set(d, n, rec)
        keys = keys_on(t, tab, names, _rv_on(panels, rvp, t, names))
        el = sorted(set(keys["slope"]) | set(keys["ratio"]))
        pidx = ctx.bars.last15(t)
        cond_need, exit_need = set(), defaultdict(set)
        for n in el:
            rec = res[t].get(n) or {}
            exp30 = date.fromisoformat(rec["exp30"]) if rec.get("exp30") else None
            spot = rec.get("spot")
            positions = []
            p1, _ = choose_straddle(n, pidx, spot, exp30)
            if p1:
                positions.append(p1)
            if n in keys["ratio"] and exp30 and rec.get("iv30"):
                probe = condor_probe(n, spot, exp30, t, rec["iv30"])
                miss = [s for s in probe if s not in ctx.bars.asked(t, IV.W_LAST)]
                if miss:
                    cond_need |= set(miss)
                else:
                    p2, _ = choose_condor(n, pidx, spot, exp30, t, rec["iv30"])
                    if p2:
                        positions.append(p2)
            if not positions:
                continue
            xe, _a = hold_exit(t, x, reports.get(n), cal)
            if xe is None:
                continue
            for p in positions:
                if p["expiry"] > xe and xe <= b:
                    exit_need[xe] |= {s for s, _ in p["legs"]}
        if cond_need:
            out.append(IV.need(t, IV.W_LAST, cond_need, "r10swing:condor", ctx.priority(t)))
        for d, syms in exit_need.items():
            out.append(IV.need(d, IV.W_LAST, syms, "r10swing:exit", ctx.priority(t)))
    return out


def _span(ctx):
    """The pull's date range (--from/--to), DEV by default."""
    return getattr(ctx, "span", None) or (DEV_A, DEV_B)


def _rv_on(panels, rvp, day, names):
    """{name: RV252 through the prior close} on `day` from rv252_prior's array."""
    p = panels["all"]
    k = p.idx(day)
    if rvp is None or k is None:
        return {}
    return {n: float(rvp[k, p.col[n]]) for n in names if n in p.col}


def _v3_items(ctx):
    def build():
        recs, tmap = _edgar_in(ctx)
        panels = _inputs(ctx)
        ps = panels["all"]
        if not recs or not ps.symbols:
            return []
        cal = _memo(ctx, "r10_cal", edgar.Calendar)
        tr, _ = v3_trades(ps, v3_events(recs, tmap, cal), stk=stk_mask(panels))
        return v3_twin_items(tr, ps, report_positions(recs, tmap, cal), cal)
    return _memo(ctx, "r10_v3_items", build)


def needs_v3(ctx):
    out = defaultdict(set)
    a, b = _span(ctx)
    for it in _v3_items(ctx):
        if not (max(a, DEV_A) <= it["entry"] and it["exit"] <= min(b, DEV_B)):
            continue
        asked = ctx.bars.asked(it["entry"], IV.W_LAST)
        printed = ctx.bars.printed(it["entry"], IV.W_LAST)
        done = False
        for ph in v3_probe(it):
            miss = [s for s in ph if s not in asked]
            if miss:
                out[it["entry"]] |= set(miss)
                done = True
                break
            if any(s in printed for s in ph):
                break
        if done:
            continue
        if ctx.bars.stock_minutes(it["entry"]) is None:
            continue
        exps = [e for ph in expiry_after(it["after"]) for e in ph]
        info, _ = pick_last15(it["symbol"], it["entry"], ctx.bars.last15(it["entry"]), ctx.bars.stock_minutes(it["entry"]), exps, V3_BAND)
        if info and info["symbol"] not in ctx.bars.asked(it["exit"], IV.W_LAST):
            out[it["exit"]].add(info["symbol"])
    return [IV.need(d, IV.W_LAST, s, "r10swing:v3", ctx.priority(d)) for d, s in sorted(out.items())]


def _v4_dev_trades(ctx):
    def build():
        p, univ = v4_panel(_inputs(ctx))
        tr, _ = v4_book(p, univ)
        return p, [t for t in tr if DEV_A.isoformat() <= t["entry_day"] and t["exit_day"] <= DEV_B.isoformat()]
    return _memo(ctx, "r10_v4", build)


def raw_open_fn(panel, sym):
    j = panel.col.get(sym)

    def f(day):
        k = panel.idx(day)
        if j is None or k is None or not np.isfinite(panel.raw_o[k, j]):
            return None
        return float(panel.raw_o[k, j])
    return f


def needs_v4(ctx):
    p, trades = _v4_dev_trades(ctx)
    sess = IV.dev_days()
    a, b = _span(ctx)
    out = defaultdict(set)
    for tr in trades:
        if not (a.isoformat() <= tr["entry_day"] and tr["exit_day"] <= b.isoformat()):
            continue
        kind, val = v4_twin_walk(tr, ctx.bars, raw_open_fn(p, tr["symbol"]), sess)
        if kind == "need":
            d, w, syms = val
            out[(d, tuple(w))] |= set(syms)
    return [IV.need(d, w, s, "r10swing:v4", ctx.priority(d)) for (d, w), s in sorted(out.items())]


def needed_option_contracts(ctx):
    """The swing families' provider for tools/sprint_pull10.py's registry: [ivdata.Need]. ctx: root, log, warn, bars
    (ivdata.Bars), days, universe(day), is_done(day, tag), div_result(day, names), priority(day), cache."""
    return needs_vol(ctx) + needs_v3(ctx) + needs_v4(ctx)
