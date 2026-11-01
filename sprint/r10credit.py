"""sprint/r10credit.py - round 10's 0DTE credit spreads (SPRINT_PLAN Addendum 15.4: C1 `morning_trend_vertical`, C1-ctl,
C1-ic, C2 `afternoon_condor`, C2-ctl; Amendment 16: C3 `gap_condor`, C3-ctl, C4 `dynamic_fly`; all pre-registered 2026-11-01
before any round-10 code, pull or run). PAPER RESEARCH ONLY: these are option SELLING structures; Nick's account is long options
only (no spread approval). Research code: cached bars only, no network, no orders. Every number is a BACKTEST.

The rules (SPY 0DTE stands in for SPX at 1/10 scale; QQQ runs the same eight rules on its own prices as information):
  C1 morning_trend_vertical (the r/options post): direction = SPY's 10:30 price vs its 08:30 premarket price; up -> sell a put
      vertical, down -> sell a call vertical. Short strike 1.25 x the 10:30 ATM straddle mid away from the spot (the nearest
      listed strike at or beyond); long strike $5 further out (SPX's $50 wing / 10). Entry 10:30, held to the close.
  C1-ctl  the same put vertical every day, no direction filter.            C1-ic  both sides every day (an iron condor).
  C2 afternoon_condor (commenter ThrockmortenMD): at 13:45 short the 30-delta call and put (BS-EST), wings $5 out, held to the
      close; only when SPY's close is above its 10-day SMA and VIX < 24. VIX history is not in our data, so the proxy is SPY's
      20-day realized vol (annualized) below 19% (labeled VIX PROXY).
  C2-ctl  the same condor every day, unfiltered.
  C3 gap_condor (the r/TastyBite bot): a 20-delta iron condor at 09:45, $5 wings, take profit at 25% of the credit, else held
      to the close; only on gap days >= +0.50% or flat days with |gap| <= 0.10% (thresholds ours; the post gives none).
  C3-ctl  the same condor every day.
  C4 dynamic_fly: at 10:00, if SPY is down more than 0.10% from the open, an iron fly (short ATM, $5 wings), else the 20-delta
      condor; take profit at 25%; time exit 13:00 (the post's 18:00 UK).
Settlement and costs (15.4; C3, C3-ctl and C4 use them too):
  * Settlement at the close at intrinsic value. SPY settles physically; after-hours assignment risk is ignored (labeled).
  * Each leg is filled at its 1-minute option price -/+ the half-spread: MEASURED (the desk's logged chains, sprint/spread) where
    a cell has data, else max($0.01, 2% of the premium); plus $0.65 per contract per leg per side. No exit cost when a leg
    expires worthless. Stress: 2x the half-spread.
Windows: DEV 2024-08-01..2026-06-30 on REAL Alpaca option bars decides. HIST 2016-01-04..2024-01-31 on MODELED tapes is
  information only (one flat IV per day and side misprices the skew a seller lives on). L1/L2 are never read (periods.guard).
Pass (SPY, DEV REAL), all of: at least 100 trades; PF >= 1.25 and PF at 2x the half-spread > 1.0; positive in at least 4 of the
  6 two-month blocks of 2025-07..2026-06; the filtered rule beats its own control's total.
Reported: max drawdown, worst day, April 2025 alone, the worst 5 days, months green, the return on the margin each spread ties
  up, the $3,000 account view, and each filtered rule beside its control (plus the bootstrap 95% interval and a random day-skip
  test of each filter against its control, CLAUDE.md's matched-random line, as information).
Trials: 5 (15.4) + 3 (Amendment 16) = 8. Round 10's tally is 7,767; the deflated Sharpe uses the run logs' count + 7,767.

Builder's reading (the text is ambiguous or not possible with our data; the most literal reading, chosen before any run):
  R1  Times. "At HH:MM" is a decision on the 1-minute bar that FINISHED at HH:MM (the bar starting a minute earlier: 09:44 for
      09:45, 09:59 for 10:00, 10:29 for 10:30, 13:44 for 13:45). Each leg fills at its first print in the 3 minutes after the
      decision bar (the next bar's open: the sprint's entry rule); a leg without a print there means no trade (counted). On
      early-close days (13:00 close) C2's 13:45 entry does not exist (no trade, counted).
  R2  C1's prices. "SPY's 10:30 price" = the 10:29 bar's close. "Its 08:30 premarket price" = the close of the last premarket
      bar (from 04:00) that finished by 08:30 (a bar starting 08:29 or earlier). No premarket bar -> no direction -> no trade.
      Up = 10:30 above 08:30, down = below; equal -> no trade.
  R3  Listed strikes = SPY's and QQQ's $1 grid. A leg whose contract has no bars on file is not priced: the structure is not
      traded that day (counted as a coverage gap); a leg is never moved to another strike.
  R4  C1's strikes. ATM = the $1 strike nearest the 10:30 price (ties: the lower). Straddle mid = the ATM call's plus the ATM
      put's last traded price at or before the decision bar, at most 5 minutes old (Alpaca has no quotes: the sprint's mid
      proxy). Short put = the largest $1 strike <= spot - 1.25 x straddle; short call = the smallest >= spot + 1.25 x straddle.
  R5  Deltas (C2 0.30; C3 and C4 0.20). BS-EST (sprint/bs, r = 0) from each contract's last price within 5 minutes and the
      decision bar's close, time to the actual close (13:00 on early-close days). The strike whose |delta| is nearest the target
      (ties: the lower premium), no band and no spread cap (the rules name neither); the strikes on file must bracket the target
      (one at or below it and one at or above it), else the day is not traded (coverage gap).
  R6  C2's filter. "SPY's close is above its 10-day SMA" = the prior session's close above the mean of the 10 closes ending
      there (data.Series.sma_side, known at the open). The VIX proxy = the sample standard deviation (n - 1) of the 20 daily log
      close-to-close returns before the day x sqrt(252) < 0.19. On QQQ (information) the SMA uses QQQ's closes and the VIX proxy
      stays SPY's (VIX is an S&P measure).
  R7  C3's gap = today's 09:30 bar open vs the prior session's last regular-hours close. Qualifying: gap >= +0.50% or |gap| <=
      0.10% (both inclusive). Down gaps of -0.50% or more do not qualify (the text names only up gaps).
  R8  C4. "Down more than 0.10% from the open" = the 10:00 price (the 09:59 bar's close) / the 09:30 bar's open - 1 < -0.10%.
      The fly's ATM = the $1 strike nearest the 10:00 price (ties: the lower); wings ATM +/- $5.
  R9  Take profit (C3, C3-ctl, C4) "at 25% of the credit" = buy the structure back when its mid-based cost falls to 75% of the
      credit received. Checked at the end of each finished minute from the last leg's entry bar: cost = the shorts' minus the
      longs' last traded prices (each at most 5 minutes old; a minute where a leg has none is not checked) <= 0.75 x the credit
      received (the base fills' net credit after half-spreads, per share, fees excluded). Each leg then closes at its first print
      after the decision bar (+/- the half-spread, + $0.65); a leg with no print before the close settles at intrinsic. The 2x
      stress keeps the same decisions (the sprint's fill rule: only the fill prices change).
  R10 C4's time exit 13:00 = a decision on the 12:59 bar, each leg at its next print; on early-close days (13:00 close) the
      structure settles at the close instead.
  R11 Settlement = the underlying's last regular-hours close (16:00; 13:00 on early-close days). A leg in the money pays the exit
      cost (intrinsic -/+ the half-spread on that value, + $0.65); a worthless leg pays nothing. Same in the 2x stress.
  R12 A structure whose net credit at the fills is <= 0 is not traded (counted), as the desk's v4 spreads.
  R13 Margin = $5 x 100 - the credit x 100 (a condor's or fly's two sides cannot both lose); return on margin = P/L / margin.
      Each trade also carries max_loss = margin + every leg's two fees (the risk a compounding view would size on).
  R14 Controls. Only C1, C2 and C3 have a pre-registered control (C1-ctl, C2-ctl, C3-ctl); "beats its own control's total" is
      not applicable to the controls themselves, to C1-ic, or to C4 (C4 trades every day with a pre-registered choice of
      structure; no control is written for it). The control's total is over the same window (it trades every day, including
      days on which the filter had no history yet).
  R15 HIST MODELED: sprint/modeled tapes, one flat IV per day and side = the IV proxy x run 4's calibration multiplier for
      d40-55t45 (the nearest calibrated band to the 20-30 delta shorts and the ATM straddle; a missing key means HIST is not
      run). Every needed $1 strike is built on demand; delta candidates within +/-6% of the spot (modeled.STRIKE_BAND). The
      measured spread cells (recent logged chains) apply where a cell has data, as on DEV (labeled).
  R16 Trials are recorded the way round 9 records them: the trial block in the report and the JSON, with the deflated Sharpe's
      N = the run logs' rows (docs/research/sprint_runs.csv + data/sprint/runs_*.csv) + round 10's 7,767. No rows are appended
      to the run logs.
  R17 Two-month blocks: Jul-Aug 2025, Sep-Oct 2025, Nov-Dec 2025, Jan-Feb 2026, Mar-Apr 2026, May-Jun 2026; "positive" = net
      P/L > 0 (a block without a trade is not positive). Months green count months with at least one trade (shares.steadiness).
  R18 QQQ is information: the pass bar is computed for SPY only (QQQ's checks are shown, labeled information).

Data needs (`needed_option_contracts`): the strikes these structures need can lie outside the strike window runs 1-3 pulled
for SPY/QQQ 0DTE on DEV (tools/sprint_pull.py: every $1 strike within +/-3% of the 09:30 open, widened to the day's high/low;
round 9's tools/sprint_pull9.py adds no 0DTE SPY/QQQ strikes). The function lists, per day, every $1 call and put strike within
each entry's reach (see its docstring); the round 10 pull tool fetches the ones not on file. Extra bars written under
data/alpaca/options_r10/<SYM>/<day>/bars.csv.gz (or merged into options/) are read too (`read_tapes`).

Compounding view (Amendment 16, information): sprint/compound.py is built by another round 10 builder; `compounding_inputs`
hands it each passing rule's DEV trades (day, pnl, max_loss). See the INTEGRATOR HOOK in tools/sprint_r10_credit.py.
"""
import math
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import book, bs, data, periods, shares
from . import modeled as MD
from . import report as R
from . import spread as SP
from .fills import OptionTape

RULES = ("C1", "C1-ctl", "C1-ic", "C2", "C2-ctl", "C3", "C3-ctl", "C4")
NAMES = {"C1": "morning_trend_vertical", "C1-ctl": "C1's put vertical, every day", "C1-ic": "C1's strikes, both sides, every day",
         "C2": "afternoon_condor", "C2-ctl": "C2's condor, every day", "C3": "gap_condor", "C3-ctl": "C3's condor, every day",
         "C4": "dynamic_fly"}
SOURCE = {"C1": "15.4", "C1-ctl": "15.4", "C1-ic": "15.4", "C2": "15.4", "C2-ctl": "15.4", "C3": "16", "C3-ctl": "16", "C4": "16"}
CONTROL = {"C1": "C1-ctl", "C2": "C2-ctl", "C3": "C3-ctl"}
TRIALS = {"Addendum 15.4 (C1, C1-ctl, C1-ic, C2, C2-ctl)": 5, "Amendment 16 (C3, C3-ctl, C4)": 3}
R10_CREDIT = 8
ROUND10 = 7767
assert sum(TRIALS.values()) == R10_CREDIT == len(RULES)

SYMBOLS = ("SPY", "QQQ")
DECIDES = "SPY"
WING = 5.0
C1_MULT = 1.25
C2_DELTA, C34_DELTA = 0.30, 0.20
TP_SHARE = 0.25                         # take profit at 25% of the credit: buy back at a mid cost <= 75% of it
C2_SMA, C2_RV_DAYS, C2_RV_MAX = 10, 20, 0.19
C3_GAP_UP, C3_FLAT = 0.005, 0.001
C4_DOWN = 0.001
FEE, MULT = 0.65, 100
MAX_AGE = 5                             # minutes: a last traded price older than this is no price
ENTRY_WAIT = 3                          # minutes after the decision bar in which every leg must print
N = 390
# decision bars (0 = the 09:30 bar): "at HH:MM" is the bar that finished at HH:MM (Builder's reading R1)
DEC = {"C3": 14, "C3-ctl": 14, "C4": 29, "C1": 59, "C1-ctl": 59, "C1-ic": 59, "C2": 254, "C2-ctl": 254}
TIME_EXIT = {"C4": 209}                 # 13:00: the 12:59 bar
TP_RULES = {"C3", "C3-ctl", "C4"}
PREMARKET_FROM, PREMARKET_AT = 240, 510  # 04:00 and 08:30, minutes after midnight ET
FALLBACK_PCT, FALLBACK_MIN = 0.02, 0.01
CALIB_RULE = "d40-55t45"
OPTION_SUBS = ("options", "options_r10")
DEV_A, DEV_B = periods.DEV[0].isoformat(), periods.DEV[1].isoformat()
HIST_A, HIST_B = periods.HIST[0].isoformat(), periods.HIST[1].isoformat()
WINDOWS = {"DEV": (DEV_A, DEV_B, "REAL"), "HIST": (HIST_A, HIST_B, "MODELED")}
BLOCKS = (("Jul-Aug 2025", "2025-07-01", "2025-08-31"), ("Sep-Oct 2025", "2025-09-01", "2025-10-31"),
          ("Nov-Dec 2025", "2025-11-01", "2025-12-31"), ("Jan-Feb 2026", "2026-01-01", "2026-02-28"),
          ("Mar-Apr 2026", "2026-03-01", "2026-04-30"), ("May-Jun 2026", "2026-05-01", "2026-06-30"))
APRIL_2025 = ("2025-04-01", "2025-04-30")
PASS_TRADES, PASS_PF, PASS_PF2X, PASS_BLOCKS = 100, 1.25, 1.0, 4
ACCOUNT = 3000.0
LABELS = {"REAL": "REAL (Alpaca option bars)", "MODELED": "MODELED (BS, one flat IV per day and side; information only)"}
# needed_option_contracts: the reach of each entry (see its docstring)
NEED_DEC = {"09:45": 14, "10:00": 29, "10:30": 59, "13:45": 254}
DELTA_FLOOR = 0.05
SKEW_PAD = 1.5
IV_FALLBACK = 0.60
EXISTING_BAND = 0.03


def _r(x, n=2):
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) else (x if math.isinf(x) else round(x, n))


def occ(under, day, right, K):
    return f"{under}{day:%y%m%d}{right}{int(round(float(K) * 1000)):08d}"


def hm(i):
    m = 570 + int(i)
    return f"{m // 60:02d}:{m % 60:02d}"


# ---------------------------------------------------------------- costs
class CreditSpread(SP.SpreadModel):
    """Half-spread per leg (15.4): MEASURED from the desk's logged chains where a cell has data, else max($0.01, 2% of premium)."""

    def half_spread(self, under, px, minute=None):
        px = max(float(px), 0.0)
        if self.table:
            pb = SP._pb(px)
            if minute is not None:
                v = self.table.get((under, pb, SP._tb(minute)))
                if v is not None:
                    return max(v, SP.TICK_HALF), "MEASURED-SPREAD"
            v = self.table.get((under, pb, None))
            if v is not None:
                return max(v, SP.TICK_HALF), "MEASURED-SPREAD"
        return max(FALLBACK_MIN, FALLBACK_PCT * px), "MODELED-SPREAD"

    def describe(self):
        if not self.table:
            return "MODELED-SPREAD everywhere: half-spread = max($0.01, 2% of the premium) (no logged chains found)"
        cov = ", ".join(f"{u} {c['days']} days/{c['rows']} rows" for u, c in sorted(self.coverage.items()))
        return (f"MEASURED-SPREAD from logged chains ({cov}) where a cell has data (an ASSUMPTION for earlier years: the chains are "
                f"recent); else max($0.01, 2% of the premium)")


def credit_spread(chains_dir, unders=SYMBOLS):
    base = SP.from_chains(chains_dir, set(unders))
    return CreditSpread(base.table, base.coverage)


# ---------------------------------------------------------------- data
def premarket_prices(df, at=PREMARKET_AT):
    """{day: the close of the last premarket bar (04:00 on) that finished by `at` (minutes after midnight ET)} from raw
    1-minute rows (ts, ..., c). A bar starting at m finishes at m + 1, so bars with 04:00 <= start < `at` count."""
    if df is None or not len(df):
        return {}
    ts = df["ts"]
    m = (ts.dt.hour * 60 + ts.dt.minute).to_numpy()
    sel = (m >= PREMARKET_FROM) & (m < at)
    if not sel.any():
        return {}
    sub = pd.DataFrame({"day": ts.dt.date.to_numpy()[sel], "m": m[sel], "c": df["c"].to_numpy(float)[sel]})
    sub = sub.sort_values(["day", "m"], kind="stable")
    last = sub.groupby("day", sort=False).tail(1)
    return {d: float(c) for d, c in zip(last["day"], last["c"]) if c == c}


def load(sym, a, b, root=None):
    """(data.Series over [a, b], {day: 08:30 premarket price}) after the locked-period guard (refuses L1/L2; bars dated inside
    them are dropped too, as shares.load_series)."""
    a, b = periods._d(a), periods._d(b)
    periods.guard(a, b)
    df = data.read_stock(sym, a, b, root)
    if df is not None and len(df):
        d = df["ts"].dt.date
        bad = np.zeros(len(df), bool)
        for x, y in periods.LOCKED.values():
            bad |= ((d >= x) & (d <= y)).to_numpy()
        df = df[~bad].reset_index(drop=True)
    return data.Series(sym, df), premarket_prices(df)


def _read_bars(path, day):
    """{occ symbol: OptionTape} of `day`'s 0DTE contracts in one bars.csv.gz (the layout data.read_option_day reads)."""
    df = pd.read_csv(path, compression="gzip")
    if not len(df):
        return {}
    mi = data._minutes(df["ts"])
    keep = (mi >= 0) & (mi < N)
    df, mi = df[keep], mi[keep]
    syms = df["symbol"].to_numpy()
    vals = df[["o", "h", "l", "c", "v"]].to_numpy(float)
    out = {}
    for s in pd.unique(syms):
        meta = data.parse_occ(s)
        if not meta or meta["expiry"] != day:
            continue
        sel = syms == s
        grid = np.full((N, 5), np.nan)
        grid[mi[sel]] = vals[sel]
        t = OptionTape(s, meta["right"], meta["strike"], *(grid[:, k] for k in range(5)))
        t.expiry = day
        out[s] = t
    return out


def read_tapes(under, day, root=None, subs=OPTION_SUBS):
    """The day's 0DTE tapes from data/alpaca/<sub>/<SYM>/<day>/bars.csv.gz for each sub (runs 1-3's options/ and the round 10
    pull's extra strikes); a symbol in several files keeps the tape with the most prints. Bars only (no trades)."""
    periods.guard(day, day)
    out = {}
    for sub in subs:
        f = Path(root or data.ROOT) / sub / under / day.isoformat() / "bars.csv.gz"
        if not f.exists():
            continue
        for s, t in _read_bars(f, day).items():
            if s not in out or np.sum(~np.isnan(t.o)) > np.sum(~np.isnan(out[s].o)):
                out[s] = t
    return out


def option_days(under, root=None, subs=OPTION_SUBS):
    out = set()
    for sub in subs:
        folder = Path(root or data.ROOT) / sub / under
        if folder.exists():
            out |= {date.fromisoformat(p.name) for p in folder.iterdir() if p.is_dir() and (p / "bars.csv.gz").exists()}
    return out


def rv20(series, day, n=C2_RV_DAYS):
    """SPY's realized vol known at `day`'s open: sample stdev of the n daily log close-to-close returns before the day x
    sqrt(252) (Builder's reading R6), or None with fewer than n + 1 prior closes."""
    if series is None or day not in series.rth:
        return None
    prior = series.prior_days(day, n + 1)
    if len(prior) < n + 1:
        return None
    c = series.daily.loc[prior, "close"].to_numpy(float)
    r = np.diff(np.log(c))
    return float(np.std(r, ddof=1) * math.sqrt(252))


def day_inputs(series, day, pm=None, spy=None):
    """What the filters read, all known before or at the decision (prior sessions, the premarket)."""
    prev = series.prev_day(day)
    v = spy if spy is not None else series
    return {"p0830": (pm or {}).get(day), "prev_close": prev["close"] if prev else None, "sma10_side": series.sma_side(day, C2_SMA),
            "rv20": rv20(v, day), "rv_from": v.sym}


# ---------------------------------------------------------------- the option chain of one day
class Chain:
    """One day's 0DTE contracts by (strike, right): REAL tapes (cached Alpaca bars) or MODELED tapes (sprint/modeled, built on
    demand with one flat IV per side)."""

    def __init__(self, ctx, label="REAL", tapes=None, md=None, ivs=None, why=None):
        self.ctx, self.label, self.md, self.ivs, self.why = ctx, label, md, ivs or {}, why
        self.by = {}
        for t in (tapes or {}).values():
            self.by[(round(float(t.strike), 3), t.right)] = t

    def __bool__(self):
        return bool(self.by) or (self.md is not None and bool(self.ivs))

    def get(self, K, right):
        if self.md is not None:
            iv = self.ivs.get(right)
            return None if iv is None else self.md.tape(float(K), right, iv)
        return self.by.get((round(float(K), 3), right))

    def side(self, right, S):
        if self.md is not None:
            iv = self.ivs.get(right)
            return list(self.md.pool(S, right, iv).values()) if iv else []
        return [t for (_k, r), t in self.by.items() if r == right]


def atm(S):
    """The $1 strike nearest S (ties: the lower)."""
    lo = math.floor(S)
    return float(lo if S - lo <= 0.5 else lo + 1)


def straddle_mid(chain, K, j):
    c, p = chain.get(K, "C"), chain.get(K, "P")
    if c is None or p is None:
        return None
    a, b = c.last_close(j, MAX_AGE), p.last_close(j, MAX_AGE)
    return None if a is None or b is None else a + b


def pick_delta(chain, ctx, right, j, target):
    """(tape, info) for the strike whose BS-EST |delta| at decision bar j is nearest `target` (ties: lower premium), or
    (None, reason). The strikes on file must bracket the target (Builder's reading R5)."""
    S = float(ctx.c[j])
    cands = chain.side(right, S)
    if not cands:
        return None, f"no {right} contracts on file"
    px = np.array([t.last_close(j, MAX_AGE) or np.nan for t in cands], float)
    ok = ~np.isnan(px)
    if not ok.any():
        return None, f"no {right} contract traded in the 5 minutes before the decision"
    K = np.array([t.strike for t in cands], float)
    T = bs.t_years(ctx.close_idx - (j + 1))
    iv, d = bs.iv_delta_v(np.where(ok, px, 1.0), S, K, T, np.array([right == "C"] * len(cands)))
    ad = np.abs(d)
    valid = ok & ~np.isnan(d)
    if not (valid & (ad <= target)).any() or not (valid & (ad >= target)).any():
        return None, f"the {right} strikes on file do not bracket |delta| {target:.2f} (pull)"
    best = None
    for k in np.where(valid)[0]:
        key = (abs(float(ad[k]) - target), float(px[k]), float(K[k]))
        if best is None or key < best[0]:
            best = (key, k)
    k = best[1]
    return cands[k], {"strike": float(K[k]), "delta": round(float(d[k]), 3), "iv": round(float(iv[k]), 4), "px": float(px[k])}


# ---------------------------------------------------------------- the entry decision (data known at the decision bar only)
def _leg(chain, K, right, q):
    t = chain.get(K, right)
    return None if t is None else {"K": float(K), "right": right, "q": q, "tape": t}


def _legs_text(legs):
    return " ".join(f"{'-' if L['q'] < 0 else '+'}{L['right']}{L['K']:g}" for L in legs)


def plan(rule, ctx, chain, inp):
    """The entry decision of `rule` on ctx's day: (plan, None) or (None, reason). Reads only the stock bars up to the decision
    bar, the option prices up to it, the premarket and prior sessions (inp: day_inputs)."""
    j = DEC[rule]
    if j >= ctx.close_idx - 1:
        return None, "early close: the entry time is at or after the close"
    if not ctx.has_bar(j):
        return None, "no underlying bar at the decision"
    S = float(ctx.c[j])
    info = {"spot_entry": S}
    if rule == "C1":
        p0 = inp.get("p0830")
        if p0 is None:
            return None, "no premarket bar by 08:30 (no direction)"
        info.update(p0830=p0, p1030=S)
        if S == p0:
            return None, "10:30 price equals the 08:30 price (no direction)"
        info["direction"] = "up" if S > p0 else "down"
    elif rule == "C2":
        side, rv = inp.get("sma10_side"), inp.get("rv20")
        info.update(sma10_side=side, rv20=_r(rv, 4), rv_from=inp.get("rv_from"))
        if side is None or rv is None:
            return None, "filter history missing (10-day SMA or the 20-day VIX proxy)"
        if side != 1:
            return None, "filter: prior close not above its 10-day SMA"
        if not rv < C2_RV_MAX:
            return None, "filter: VIX proxy (SPY 20-day realized vol) >= 19%"
    elif rule == "C3":
        pc = inp.get("prev_close")
        if pc is None or not ctx.has_bar(0) or math.isnan(ctx.o[0]):
            return None, "no prior close or no 09:30 open (gap unknown)"
        gap = round(float(ctx.o[0]) / pc - 1.0, 12)
        info["gap"] = round(gap, 6)
        if not (gap >= C3_GAP_UP or abs(gap) <= C3_FLAT):
            return None, "filter: not a gap-up (>= +0.50%) or flat (|gap| <= 0.10%) day"
    elif rule == "C4":
        if not ctx.has_bar(0) or math.isnan(ctx.o[0]):
            return None, "no 09:30 open"
        mv = round(S / float(ctx.o[0]) - 1.0, 12)                    # rounded as the gap: -0.10% exactly is not "more than"
        info["move"] = round(mv, 6)
    if not chain:
        return None, chain.why or "no 0DTE option data for the day"
    legs, extra = [], {}
    if rule in ("C1", "C1-ctl", "C1-ic"):
        K0 = atm(S)
        st = straddle_mid(chain, K0, j)
        if st is None:
            return None, "no ATM straddle price at the decision (pull)"
        dist = C1_MULT * st
        kp, kc = float(math.floor(S - dist + 1e-9)), float(math.ceil(S + dist - 1e-9))
        extra.update(atm=K0, straddle=round(st, 4))
        sides = {"C1": ("P",) if info.get("direction") == "up" else ("C",), "C1-ctl": ("P",), "C1-ic": ("P", "C")}[rule]
        for r in sides:
            ks = kp if r == "P" else kc
            legs += [(ks, r, -1), (ks - WING if r == "P" else ks + WING, r, +1)]
        structure = "iron condor" if len(sides) == 2 else ("put vertical" if sides == ("P",) else "call vertical")
    elif rule == "C4" and mv < -C4_DOWN:
        K0 = atm(S)
        legs = [(K0, "C", -1), (K0, "P", -1), (K0 + WING, "C", +1), (K0 - WING, "P", +1)]
        structure, extra["atm"] = "iron fly", K0
    else:
        target = C2_DELTA if rule in ("C2", "C2-ctl") else C34_DELTA
        picks = {}
        for r in ("C", "P"):
            t, why = pick_delta(chain, ctx, r, j, target)
            if t is None:
                return None, why
            picks[r] = why
        kc, kp = picks["C"]["strike"], picks["P"]["strike"]
        legs = [(kc, "C", -1), (kp, "P", -1), (kc + WING, "C", +1), (kp - WING, "P", +1)]
        structure = "iron condor"
        extra.update(delta_call=picks["C"]["delta"], delta_put=picks["P"]["delta"], iv_call=picks["C"]["iv"], iv_put=picks["P"]["iv"])
    out = []
    for K, r, q in legs:
        L = _leg(chain, K, r, q)
        if L is None:
            return None, f"{'short' if q < 0 else 'long'} {r} {K:g} not on file (pull)"
        out.append(L)
    return {"rule": rule, "decision_idx": j, "structure": structure, "legs": out, "tp": rule in TP_RULES,
            "time_exit_dec": TIME_EXIT.get(rule), **info, **extra}, None


# ---------------------------------------------------------------- fills, exits, settlement
def settle_price(ctx):
    """The underlying's last regular-hours close (16:00, or 13:00 on early-close days)."""
    c = ctx.c[:ctx.close_idx]
    ok = np.where(~np.isnan(c))[0]
    return float(c[ok[-1]]) if len(ok) else None


def intrinsic(S, K, right):
    return round(max(0.0, S - K) if right == "C" else max(0.0, K - S), 4)


def simulate(p, ctx, cost):
    """One structure from its plan: (trade row, None) or (None, reason). P/L in dollars per structure (1 contract per leg)
    at k = 1 and at 2x the half-spread (k = 2), the same decisions."""
    j, close_n = p["decision_idx"], ctx.close_idx
    legs = []
    for L in p["legs"]:
        t = L["tape"]
        e = t.next_print(j + 1, min(j + ENTRY_WAIT, close_n - 1))
        if e is None:
            return None, f"no print for {'-' if L['q'] < 0 else '+'}{L['right']}{L['K']:g} within {ENTRY_WAIT} minutes of the decision"
        b = float(t.o[e])
        hs, lab = cost.half_spread(ctx.sym, b, e)
        legs.append(dict(L, e=e, b_in=b, hs_in=hs, lab=lab))

    def credit(k):
        return sum(max(0.0, x["b_in"] - k * x["hs_in"]) if x["q"] < 0 else -(x["b_in"] + k * x["hs_in"]) for x in legs)

    c1 = credit(1)
    if c1 <= 0:
        return None, "no credit at the fills"
    e_last = max(x["e"] for x in legs)
    x_dec, reason = None, None
    te = p.get("time_exit_dec")
    if p.get("tp"):
        level = (1.0 - TP_SHARE) * c1
        last = close_n - 2 if te is None else min(te, close_n - 2)
        for k in range(e_last, last + 1):
            px = [x["tape"].last_close(k, MAX_AGE) for x in legs]
            if any(v is None for v in px):
                continue
            mid_cost = sum(-v if x["q"] > 0 else v for x, v in zip(legs, px))
            if mid_cost <= level + 1e-9:
                x_dec, reason = k, "TAKE PROFIT"
                break
    if x_dec is None and te is not None and te <= close_n - 2:
        x_dec, reason = te, f"TIME EXIT {hm(te + 1)}"
    S_close = settle_price(ctx)
    n_fill = n_itm = n_settled = 0
    x_bars = []
    for x in legs:
        xi = x["tape"].next_print(x_dec + 1, close_n - 1) if x_dec is not None else None
        if xi is not None:
            x["x"], x["b_out"] = xi, float(x["tape"].o[xi])
            x["hs_out"], lab = cost.half_spread(ctx.sym, x["b_out"], xi)
            x["kind"] = "fill"
            n_fill += 1
            x_bars.append(xi)
        else:
            n_settled += 1
            v = intrinsic(S_close, x["K"], x["right"]) if S_close is not None else 0.0
            x["x"], x_bars = close_n - 1, x_bars + [close_n - 1]
            if v > 0:
                x["b_out"] = v
                x["hs_out"], lab = cost.half_spread(ctx.sym, v, close_n - 1)
                x["kind"] = "settled ITM"
                n_itm += 1
            else:
                x["b_out"], x["hs_out"], x["kind"], lab = 0.0, 0.0, "expired worthless", None
        if lab == "MEASURED-SPREAD":
            x["lab"] = lab

    def pnl(k):
        tot = credit(k) * MULT - FEE * len(legs)
        for x in legs:
            if x["kind"] == "expired worthless":
                continue
            if x["q"] < 0:
                tot -= (x["b_out"] + k * x["hs_out"]) * MULT + FEE
            else:
                tot += max(0.0, x["b_out"] - k * x["hs_out"]) * MULT - FEE
        return tot

    p1, p2 = pnl(1), pnl(2)
    margin = WING * MULT - c1 * MULT
    margin = round(margin, 2) if margin > 0 else None
    row = {k: v for k, v in p.items() if k not in ("legs", "tp", "time_exit_dec", "rule")}
    row.update(name=NAMES[p["rule"]], legs=_legs_text(legs), credit=round(c1, 4), credit_2x=round(credit(2), 4), width=WING,
               margin=margin, max_loss=round(margin + 2 * FEE * len(legs), 2) if margin else None,
               pnl=round(p1, 2), pnl_2x=round(p2, 2), ret_margin=round(p1 / margin, 4) if margin else None,
               entry_idx=e_last, entry_time=hm(e_last), exit_idx=max(x_bars), exit_time=hm(max(x_bars) + (1 if n_settled else 0)),
               exit_reason=reason or "SETTLED", legs_filled_out=n_fill, legs_settled=n_settled, legs_itm_at_close=n_itm,
               spot_close=S_close, spread="MEASURED-SPREAD" if any(x["lab"] == "MEASURED-SPREAD" for x in legs) else "MODELED-SPREAD")
    for x in legs:
        nm = ("short_" if x["q"] < 0 else "long_") + ("call" if x["right"] == "C" else "put")
        row[nm] = x["K"]
    return row, None


# ---------------------------------------------------------------- one day, one window
def run_day(ctx, chain, inp, cost, rules=RULES):
    """Every rule on one (symbol, day): ([trade rows], [(rule, skip reason)])."""
    trades, skips = [], []
    for rule in rules:
        p, why = plan(rule, ctx, chain, inp)
        if p is None:
            skips.append((rule, why))
            continue
        t, why = simulate(p, ctx, cost)
        if t is None:
            skips.append((rule, why))
            continue
        t.update(rule=rule, symbol=ctx.sym, day=ctx.day.isoformat())
        trades.append(t)
    return trades, skips


def modeled_ivs(series, day, calib):
    """{"C": iv, "P": iv}: the IV proxy known at the open x run 4's d40-55t45 multiplier per side, or None (no proxy)."""
    ivp = MD.iv_proxy(series, day)
    if ivp is None:
        return None
    return {s: ivp * MD.multiplier(calib, CALIB_RULE, s) for s in ("C", "P")}


def run(series, pm, a, b, mode, root=None, calib=None, cost=None, spy=None, rules=RULES, progress=None, limit_days=None,
        subs=OPTION_SUBS, coverage=None, window=None):
    """Every rule over the sessions of `series` inside [a, b]. mode "real" (DEV: cached Alpaca bars) or "modeled" (HIST: needs
    calib). spy: SPY's Series (the VIX proxy for QQQ). coverage: an optional dict filled with the needed-vs-on-file count per
    day (real mode). window: the tag stamped on each trade (default DEV for real, HIST for modeled).
    Returns (trades, Counter of (rule, reason) skips)."""
    if mode not in ("real", "modeled"):
        raise ValueError(mode)
    window = window or ("DEV" if mode == "real" else "HIST")
    if mode == "modeled":
        if calib is None:
            raise ValueError("MODELED credit spreads need the calibration (data/sprint/calib_modeled.json)")
        for s in ("C", "P"):
            MD.multiplier(calib, CALIB_RULE, s)               # refuse before the loop when the key is missing or thin
    a, b = periods._d(a), periods._d(b)
    periods.guard(a, b)
    cost = cost or CreditSpread()
    days = [d for d in series.days if a <= d <= b]
    if limit_days:
        days = days[:limit_days]
    odays = option_days(series.sym, root, subs) if mode == "real" else None
    trades, skips = [], Counter()
    for n, d in enumerate(days):
        ctx = data.DayContext(series, d, {}, None)
        inp = day_inputs(series, d, pm, spy)
        if mode == "real":
            tapes = read_tapes(series.sym, d, root, subs) if d in odays else {}
            chain = Chain(ctx, "REAL", tapes=tapes)
            if coverage is not None and tapes:
                coverage[d.isoformat()] = day_coverage(d, series.rth[d], series.sym, tapes, early=ctx.early)
        else:
            ivs = modeled_ivs(series, d, calib)
            chain = (Chain(ctx, "MODELED", md=MD.ModeledDay(ctx), ivs=ivs) if ivs else
                     Chain(ctx, "MODELED", why="MODELED: no IV proxy (fewer than 10 prior sessions)"))
        tr, sk = run_day(ctx, chain, inp, cost, rules)
        lab = "REAL" if mode == "real" else "MODELED"
        for t in tr:
            t["prices"], t["window"] = lab, window
        trades += tr
        for rule, why in sk:
            skips[(rule, why)] += 1
        if progress and (n % 100 == 0 or n == len(days) - 1):
            progress(f"  credit {mode} {series.sym} {d} ({n + 1}/{len(days)} sessions, {len(trades)} trades)")
    return trades, skips


# ---------------------------------------------------------------- data needs (for the round 10 pull)
def _rth_grid(spot_path, day=None):
    """A (390, 5) O,H,L,C,V regular-hours grid from an array (data.Series.rth[day]) or a DataFrame of 1-minute rows (ts in ET)."""
    if isinstance(spot_path, pd.DataFrame):
        ts = spot_path["ts"]
        if not hasattr(ts, "dt"):
            ts = pd.to_datetime(ts, utc=True, format="ISO8601").dt.tz_convert("America/New_York")
        elif ts.dt.tz is None:
            ts = ts.dt.tz_localize("America/New_York")
        else:
            ts = ts.dt.tz_convert("America/New_York")
        m = (ts.dt.hour * 60 + ts.dt.minute).to_numpy() - 570
        keep = (m >= 0) & (m < N)
        if day is not None:
            keep &= (ts.dt.date == day).to_numpy()
        g = np.full((N, 5), np.nan)
        vals = spot_path[["o", "h", "l", "c", "v"]].to_numpy(float) if "v" in spot_path else np.column_stack(
            [spot_path[["o", "h", "l", "c"]].to_numpy(float), np.zeros(len(spot_path))])
        g[m[keep]] = vals[keep]
        return g
    g = np.asarray(spot_path, float)
    if g.ndim == 1:                                                  # closes only
        out = np.full((N, 5), np.nan)
        out[:len(g), 3] = g[:N]
        out[:len(g), 0] = out[:len(g), 1] = out[:len(g), 2] = g[:N]
        return out
    return g


def _last_close(c, j):
    for i in range(j, max(-1, j - MAX_AGE - 1), -1):
        if 0 <= i < len(c) and not math.isnan(c[i]):
            return float(c[i])
    return None


def _index(tapes):
    by = {}
    for t in (tapes or {}).values():
        by[(round(float(t.strike), 3), t.right)] = t
    return by


def atm_iv(by, S, j, T):
    """The mean BS-EST IV of the ATM call and put from their last prices within 5 minutes of bar j, or None."""
    K = atm(S)
    ivs = []
    for r in ("C", "P"):
        t = by.get((K, r))
        px = t.last_close(j, MAX_AGE) if t is not None else None
        v = bs.implied_vol(px, S, K, T, r) if px is not None else None
        if v:
            ivs.append(v)
    return sum(ivs) / len(ivs) if ivs else None


def needed_strikes(day, spot_path, tapes=None, iv=None, early=None):
    """{entry time: (lowest, highest) $1 strike} the eight structures can need on `day` (see needed_option_contracts)."""
    periods.guard(day, day)
    g = _rth_grid(spot_path, day)
    if early is None:
        early = day.isoformat() in periods.early_closes()
    close_n = 210 if early else N
    by = _index(tapes)
    z = statistics.NormalDist().inv_cdf(1.0 - DELTA_FLOOR)
    out = {}
    for name, j in NEED_DEC.items():
        if j >= close_n - 1:
            continue
        S = _last_close(g[:, 3], j)
        if S is None:
            continue
        T = bs.t_years(close_n - (j + 1))
        sig = iv or atm_iv(by, S, j, T) or IV_FALLBACK
        se = sig * SKEW_PAD
        lo = S * math.exp(-z * se * math.sqrt(T) + 0.5 * se * se * T)
        hi = S * math.exp(z * se * math.sqrt(T) + 0.5 * se * se * T)
        lo, hi = min(lo, atm(S)), max(hi, atm(S))
        if j == DEC["C1"]:
            st = straddle_mid(Chain(None, tapes=tapes), atm(S), j) if by else None
            if st is None:
                st = 2.0 * bs.price(S, atm(S), T, se, "C")              # an envelope when the straddle is not on file
            lo, hi = min(lo, S - C1_MULT * st), max(hi, S + C1_MULT * st)
        out[name] = (int(math.floor(lo - WING - 1)), int(math.ceil(hi + WING + 1)))
    return out


def needed_option_contracts(day, spot_path, under="SPY", tapes=None, iv=None, early=None):
    """The 0DTE contracts (OCC symbols, calls and puts, sorted) that C1, C1-ctl, C1-ic, C2, C2-ctl, C3, C3-ctl and C4 can need
    on `day`, for the round 10 pull. Refuses a day inside L1/L2 (periods.LockedPeriod).

    spot_path: the day's 1-minute stock bars: a (390, 5) O,H,L,C,V regular-hours grid (data.Series.rth[day]) or a DataFrame of
      cached rows (ts in ET, o/h/l/c[/v]; premarket and after-hours rows are ignored).
    tapes: optional {occ symbol: OptionTape} already on file that day (data.read_option_day / read_tapes): the ATM IV and the
      10:30 straddle are then read from them (the values the rules use); without them the envelope uses `iv`, else 60%.
    iv: optional annualized IV that overrides the ATM IV.
    early: early-close day (default: the sprint calendar); then the 13:45 entry is dropped.
    Reach per entry decision bar (09:44, 09:59, 10:29, 13:44; the spot = that bar's close): every $1 strike from the strike
      at BS |delta| 0.05 on the put side to the one at 0.05 on the call side, at the ATM IV x 1.5 (a skew pad: 0DTE puts trade
      well above the ATM IV), so the 0.20 and 0.30 delta picks are bracketed with room; at 10:30 also spot +/- 1.25 x the
      straddle (C1's shorts); then $5 further for the wings and one more strike. The ATM strikes (C4's fly) are inside.
    Every leg is needed all day (the take-profit and time exits read each leg's bars until it exits), so whole-day bars are
    pulled, as tools/sprint_pull.py does (09:00-16:30)."""
    if not isinstance(day, date):
        day = date.fromisoformat(str(day))
    ks = set()
    for lo, hi in needed_strikes(day, spot_path, tapes, iv, early).values():
        ks |= set(range(max(lo, 1), hi + 1))
    return sorted(occ(under, day, r, k) for k in ks for r in ("C", "P"))


def existing_pull_strikes(spot_path, day=None, band=EXISTING_BAND):
    """(lowest, highest) $1 strike runs 1-3 asked Alpaca for (pull_alpaca.symbols_for_day: +/- band of the 09:30 open, widened
    to the day's regular-hours high/low), or None without bars."""
    g = _rth_grid(spot_path, day)
    ok = ~np.isnan(g[:, 3])
    if not ok.any():
        return None
    o = float(g[np.where(ok)[0][0], 0])
    hi, lo = float(np.nanmax(g[:, 1])), float(np.nanmin(g[:, 2]))
    return int(min(o * (1 - band), lo)), int(max(o * (1 + band), hi)) + 1


def day_coverage(day, spot_path, under, tapes, early=None):
    """Needed vs on file for one day: needed contracts, those on file, those runs 1-3 asked for but that have no bars (never
    traded that day: nothing to pull), and those outside the asked strikes (the round 10 pull fetches them)."""
    need = needed_option_contracts(day, spot_path, under, tapes=tapes, early=early)
    have = set(tapes or {})
    ex = existing_pull_strikes(spot_path, day)
    miss = [s for s in need if s not in have]
    asked = [s for s in miss if ex and ex[0] <= int(s[-8:]) / 1000 <= ex[1]]
    return {"needed": len(need), "on_file": len(need) - len(miss), "asked_no_bars": len(asked), "outside_asked": len(miss) - len(asked)}


def coverage_summary(cov):
    """Totals over days of day_coverage results."""
    if not cov:
        return {"days": 0}
    v = list(cov.values())
    out = {k: int(sum(x[k] for x in v)) for k in ("needed", "on_file", "asked_no_bars", "outside_asked")}
    days_out = sorted(d for d, x in cov.items() if x["outside_asked"])
    out.update(days=len(v), days_complete=sum(1 for x in v if x["on_file"] == x["needed"]), days_needing_pull=len(days_out),
               first_days_needing_pull=days_out[:15])
    return out


# ---------------------------------------------------------------- evaluation
def in_win(rows, a, b):
    return [r for r in rows if a <= str(r["day"])[:10] <= b]


def daily_pnl(rows, days, key="pnl"):
    idx = {d: i for i, d in enumerate(days)}
    v = np.zeros(len(days))
    for r in rows:
        i = idx.get(str(r["day"])[:10])
        if i is not None:
            v[i] += float(r[key])
    return v


def blocks(rows):
    out = {}
    for name, a, b in BLOCKS:
        s = [float(r["pnl"]) for r in in_win(rows, a, b)]
        out[name] = {"trades": len(s), "net": _r(sum(s)) if s else 0.0}
    return out


def bootstrap_ci(rows, days, boots=2000, seed=7):
    """95% interval of the expectancy per trade, resampling sessions with replacement (sessions without a trade included), as
    report.bootstrap_ci, vectorized (numpy default_rng(seed))."""
    if not rows or not days:
        return None
    idx = {d: i for i, d in enumerate(days)}
    tot, cnt = np.zeros(len(days)), np.zeros(len(days))
    for r in rows:
        i = idx.get(str(r["day"])[:10])
        if i is not None:
            tot[i] += float(r["pnl"])
            cnt[i] += 1
    rng = np.random.default_rng(seed)
    sims = np.empty(boots)
    for a0 in range(0, boots, 200):
        m = min(200, boots - a0)
        k = rng.integers(0, len(days), size=(m, len(days)))
        s, n = tot[k].sum(1), cnt[k].sum(1)
        sims[a0:a0 + m] = np.where(n > 0, s / np.maximum(n, 1), 0.0)
    return [_r(float(np.percentile(sims, 2.5))), _r(float(np.percentile(sims, 97.5)))]


def margin_stats(rows):
    m = [(float(r["pnl"]), float(r["margin"])) for r in rows if r.get("margin")]
    if not m:
        return {"trades_with_margin": 0}
    rr = [p / g for p, g in m]
    return {"trades_with_margin": len(m), "mean_ret": _r(statistics.mean(rr), 4), "median_ret": _r(statistics.median(rr), 4),
            "total_on_total_margin": _r(sum(p for p, _ in m) / sum(g for _, g in m), 4),
            "median_margin": _r(statistics.median(g for _, g in m)), "max_margin": _r(max(g for _, g in m))}


def evaluate(rows, a, b):
    """The 15.4 report for one rule, symbol and window."""
    rows = in_win(rows, a, b)
    days = book.sessions_between(a, b)
    s = shares.stats(rows, len(days))
    out = {"stats": s, "window": f"{a}..{b}"}
    if not rows:
        return out
    dv = daily_pnl(rows, days)
    by_day = defaultdict(float)
    for r in rows:
        by_day[str(r["day"])[:10]] += float(r["pnl"])
    worst5 = sorted(by_day.items(), key=lambda kv: kv[1])[:5]
    ap = in_win(rows, *APRIL_2025)
    years = {}
    for y in sorted({str(r["day"])[:4] for r in rows}):
        sy = shares.stats([r for r in rows if str(r["day"]).startswith(y)])
        years[y] = {k: sy.get(k) for k in ("trades", "total", "pf", "pf_2x", "max_dd")}
    out.update(worst_day=(worst5[0][0], _r(worst5[0][1])), worst5=[(d, _r(v)) for d, v in worst5], years=years,
               april_2025=dict(shares.stats(ap), worst_day=_r(min((by_day[str(r["day"])[:10]] for r in ap), default=None))) if ap else {"trades": 0},
               steadiness=shares.steadiness([dict(r, day=str(r["day"])[:10]) for r in rows]), blocks=blocks(rows),
               margin=margin_stats(rows), without_best5=R.without_best([dict(r, day=str(r["day"])[:10]) for r in rows], 5),
               bootstrap_ci=bootstrap_ci(rows, days),
               reasons=dict(Counter(str(r["exit_reason"]) for r in rows).most_common()),
               structures=dict(Counter(str(r["structure"]) for r in rows).most_common()),
               itm_at_close=sum(1 for r in rows if int(r.get("legs_itm_at_close") or 0) > 0),
               daily_max_dd=_r(float(min(0.0, (np.cumsum(dv) - np.maximum.accumulate(np.concatenate([[0.0], np.cumsum(dv)]))[1:]).min()))))
    return out


def _pfv(x):
    return -1.0 if x is None else float(x)


def pass_bar(rule, ev, ctl_ev=None):
    """15.4's pass bar on one rule's DEV REAL evaluation (SPY decides). ctl_ev: its control's evaluation (C1, C2, C3)."""
    s = ev.get("stats") or {}
    n = s.get("trades", 0)
    bl = ev.get("blocks") or blocks([])
    green = sum(1 for v in bl.values() if (v.get("net") or 0) > 0)
    ch = [(f"at least {PASS_TRADES} trades ({n})", n >= PASS_TRADES),
          (f"PF >= {PASS_PF} ({s.get('pf')})", _pfv(s.get("pf")) >= PASS_PF),
          (f"PF at 2x the half-spread > {PASS_PF2X:g} ({s.get('pf_2x')})", _pfv(s.get("pf_2x")) > PASS_PF2X),
          (f"positive in at least {PASS_BLOCKS} of the 6 two-month blocks of 2025-07..2026-06 ({green} of 6)", green >= PASS_BLOCKS)]
    ctl = CONTROL.get(rule)
    if ctl:
        t, tc = s.get("total") or 0.0, ((ctl_ev or {}).get("stats") or {}).get("total") or 0.0
        ch.append((f"beats its control {ctl}'s total ({_r(t)} vs {_r(tc)})", t > tc))
    return {"checks": ch, "pass": all(ok for _, ok in ch), "blocks_green": green, "control": ctl}


def random_skip(rule, rows, ctl_rows):
    """Information (CLAUDE.md's matched random): the filtered rule's expectancy vs its control with the same number of random
    days removed (report.random_skip_test, 500 paths, seed 11)."""
    if rule not in CONTROL or not rows or not ctl_rows:
        return None
    f = [dict(r, day=str(r["day"])[:10]) for r in rows]
    u = [dict(r, day=str(r["day"])[:10]) for r in ctl_rows]
    return R.random_skip_test(f, u)


def account_view(rows, days, account=ACCOUNT):
    """The $3,000 account view with capital = the margin each spread ties up (round 9's account view arithmetic)."""
    from . import round9 as R9
    rr = [dict(r, debit=r.get("margin"), day=str(r["day"])[:10]) for r in rows]
    av = R9.account_view(rr, "option", days, account)
    av["margin_pct_3000"] = av.pop("debit_pct_3000", None)
    m = [float(r["margin"]) for r in rows if r.get("margin")]
    av["fit_at_median_margin"] = int(account // statistics.median(m)) if m and statistics.median(m) > 0 else None
    return av


def evaluate_all(trades, windows=("DEV", "HIST"), symbols=SYMBOLS):
    """{window: {symbol: {rule: evaluation (+ pass bar on DEV)}}}."""
    out = {}
    for w in windows:
        a, b, lab = WINDOWS[w]
        out[w] = {}
        days = book.sessions_between(a, b)
        for sym in symbols:
            rows = [t for t in trades if t["symbol"] == sym and t.get("window", w) == w]
            if not rows:
                continue
            by = {rule: [t for t in rows if t["rule"] == rule] for rule in RULES}
            res = {}
            for rule in RULES:
                ev = evaluate(by[rule], a, b)
                ev["prices"] = LABELS[lab]
                if ev["stats"].get("trades"):
                    ev["account"] = account_view(in_win(by[rule], a, b), days)
                res[rule] = ev
            for rule in RULES:
                if w == "DEV":
                    res[rule]["pass_bar"] = pass_bar(rule, res[rule], res.get(CONTROL.get(rule)))
                    res[rule]["decides"] = sym == DECIDES
                if rule in CONTROL:
                    res[rule]["random_skip"] = random_skip(rule, in_win(by[rule], a, b), in_win(by[CONTROL[rule]], a, b))
            out[w][sym] = res
    return out


# ---------------------------------------------------------------- trials, the deflated Sharpe, the compounding hook
def trials(n_prior):
    return {"parts": TRIALS, "r10_credit": R10_CREDIT, "round10": ROUND10, "prior_in_run_logs": int(n_prior),
            "total_for_dsr": int(n_prior) + ROUND10,
            "note": "Recorded as round 9 records its trials (this block in the report and the JSON); the deflated Sharpe's N is the run "
                    "logs' rows + round 10's full tally (Amendment 16: 7,767), of which these eight are 5 (15.4) + 3 (C3, C3-ctl, C4)."}


def dsr_table(variants_dev, n_prior, dev_days):
    """{name: deflated Sharpe} on DEV daily P/L (0 on days without a trade), N = run logs + 7,767, the trial-Sharpe variance
    over the variants given. Returns (table, sr_var, N)."""
    daily = {k: [float(x) for x in daily_pnl(v, dev_days)] for k, v in variants_dev.items()}
    srs = {k: R.sharpe(d) for k, d in daily.items()}
    vals = [x for x in srs.values() if x is not None]
    sr_var = statistics.pvariance(vals) if len(vals) > 1 else 0.0
    n = int(n_prior) + ROUND10
    tab = {k: (R.deflated_sharpe(d, n, sr_var) if variants_dev[k] else None) for k, d in daily.items()}
    return tab, round(sr_var, 6), n


def compounding_inputs(ev_dev, trades, symbol=DECIDES):
    """INTEGRATOR HOOK (Amendment 16's compounding view; sprint/compound.py is another builder's): {rule: rows (day, pnl,
    pnl_2x, max_loss, margin)} of every rule that passes on `symbol`'s DEV REAL trades. The fixed-fractional sizes there (1%,
    2%, 5% of a $3,000 account a trade) divide by max_loss, the most one structure can lose."""
    out = {}
    for rule, ev in (ev_dev.get(symbol) or {}).items():
        if (ev.get("pass_bar") or {}).get("pass"):
            out[rule] = [{k: t.get(k) for k in ("day", "pnl", "pnl_2x", "max_loss", "margin")}
                         for t in in_win(trades, DEV_A, DEV_B) if t["rule"] == rule and t["symbol"] == symbol]
    return out


def check_rows(rows):
    """None, or the reason the rows are refused (a trade dated inside L1/L2)."""
    for r in rows:
        d = periods._d(str(r["day"])[:10])
        hit = periods.overlaps(d, d)
        if hit:
            return f"REFUSED: a credit-spread trade on {d} is inside locked period {', '.join(hit)}"
    return None


# ---------------------------------------------------------------- the report
def _f(x, n=2):
    return R.fmt(x, n)


def _row(cells):
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _head(cols):
    return ["", _row(cols), _row(["---"] * len(cols))]


def _yn(ok):
    return "PASS" if ok else "fail"


COLS = ("rule", "trades", "win %", "avg win $", "avg loss $", "exp $", "exp 2x $", "PF", "PF 2x", "total $", "total 2x $", "max DD $",
        "worst day $", "w/o best 5 $", "months green", "ret on margin (mean)")


def _cells(rule, ev):
    s = ev.get("stats") or {}
    if not s.get("trades"):
        return [rule, 0] + ["-"] * (len(COLS) - 2)
    st, m, w = ev.get("steadiness") or {}, ev.get("margin") or {}, ev.get("worst_day")
    return [rule, s["trades"], _f((s.get("win_rate") or 0) * 100, 1), _f(s.get("avg_win")), _f(s.get("avg_loss")), _f(s.get("expectancy")),
            _f(s.get("expectancy_2x")), _f(s.get("pf")), _f(s.get("pf_2x")), _f(s.get("total")), _f(s.get("total_2x")), _f(s.get("max_dd")),
            f"{_f(w[1])} ({w[0]})" if w else "-", _f((ev.get("without_best5") or {}).get("net")),
            f"{st.get('months_green')}/{st.get('months')}" if st else "-", _f((m.get("mean_ret") or 0) * 100, 2) + "%" if m.get("mean_ret") is not None else "-"]


def _account_md(L, av):
    if not av:
        return
    p = av["pre_registered_size"]
    line = (f"  - Account view (information, $3,000 account, 1 structure a trade, capital = the margin it ties up): P/L per $1,000 of "
            f"margin {_f(av['per_1000']['total'])} in total ({_f(av['per_1000']['per_trade'], 3)} a trade); max drawdown {_f(p['max_dd'])} "
            f"({_f(p['max_dd_pct_3000'], 1)}% of $3,000), worst month {p['worst_month']} {_f(p['worst_month_net'])} "
            f"({_f(p['worst_month_pct_3000'], 1)}% of $3,000)")
    d = av.get("margin_pct_3000")
    if d:
        line += (f"; each structure's margin as a % of $3,000: median {_f(d['median'], 1)}%, 90th pct {_f(d['p90'], 1)}%, max "
                 f"{_f(d['max'], 1)}% ({d['over_100']} above 100%); structures that fit at the median margin: {av.get('fit_at_median_margin')}")
    L.append(line + ".")


def _detail_md(L, rule, ev, show_pass=True):
    s = ev.get("stats") or {}
    if not s.get("trades"):
        L.append(f"- **{rule}**: no trades.")
        return
    pb = ev.get("pass_bar")
    head = f"- **{rule}** `{NAMES[rule]}`"
    if pb and show_pass:
        head += f": **{_yn(pb['pass'])}**" if ev.get("decides") else f": {_yn(pb['pass'])} (information: QQQ does not decide)"
    L.append(head)
    if pb:
        for n, ok in pb["checks"]:
            L.append(f"  - {'yes' if ok else 'NO'}: {n}")
    if show_pass:                                                    # DEV only: April 2025 and the 2025-07..2026-06 blocks
        ap = ev.get("april_2025") or {}
        L.append(f"  - April 2025 alone: {ap.get('trades', 0)} trades, total {_f(ap.get('total'))}, PF {_f(ap.get('pf'))}, worst day "
                 f"{_f(ap.get('worst_day'))}." if ap.get("trades") else "  - April 2025 alone: no trades.")
    L.append("  - Worst 5 days: " + ", ".join(f"{d} {_f(v)}" for d, v in ev.get("worst5") or []) + ".")
    if show_pass:
        bl = ev.get("blocks") or {}
        L.append("  - Two-month blocks (2025-07..2026-06): " + ", ".join(f"{k} {_f(v['net'])} ({v['trades']})" for k, v in bl.items()) + ".")
    L.append("  - By year: " + ", ".join(f"{y} {_f(v['total'])} ({v['trades']} trades, PF {_f(v['pf'])})"
                                         for y, v in (ev.get("years") or {}).items()) + ".")
    m = ev.get("margin") or {}
    if m.get("trades_with_margin"):
        L.append(f"  - Return on margin ($5 x 100 - credit): mean {_f(m['mean_ret'] * 100, 2)}%, median {_f(m['median_ret'] * 100, 2)}% a "
                 f"trade; total P/L / total margin {_f(m['total_on_total_margin'] * 100, 2)}%; median margin ${_f(m['median_margin'])}, max "
                 f"${_f(m['max_margin'])}.")
    st = ev.get("steadiness") or {}
    L.append(f"  - Months green {st.get('months_green')}/{st.get('months')} (worst month {st.get('worst_month')}); max drawdown on the "
             f"daily curve {_f(ev.get('daily_max_dd'))}; bootstrap 95% interval of expectancy (by session) {ev.get('bootstrap_ci')}; "
             f"exits {ev.get('reasons')}; structures {ev.get('structures')}; trades with a leg in the money at the close "
             f"{ev.get('itm_at_close')}.")
    rs = ev.get("random_skip")
    if rs and not rs.get("skipped_days"):
        L.append(f"  - Filter vs random day-skips of {CONTROL[rule]} (information): not applicable, the filter skips no days (it "
                 f"picks the side).")
    elif rs:
        L.append(f"  - Filter vs random day-skips of {CONTROL[rule]} (information): {rs.get('skipped_days')} days removed, filtered "
                 f"expectancy {_f(rs.get('filtered_exp'))}, random mean {_f(rs.get('random_skip_exp_mean'))}, p {rs.get('p_value')}.")
    _account_md(L, ev.get("account"))


PAIRS = (("C1", "C1-ctl"), ("C1-ic",), ("C2", "C2-ctl"), ("C3", "C3-ctl"), ("C4",))


def _window_md(L, title, res, show_pass):
    L += [f"### {title}", ""]
    if not res:
        L += ["NOT RUN (no trades: see the warnings and the skip reasons).", ""]
        return
    for grp in PAIRS:
        L += _head(COLS)
        for rule in grp:
            L.append(_row(_cells(rule + (" (control)" if rule in CONTROL.values() else ""), res.get(rule, {}))))
        L.append("")
        for rule in grp:
            _detail_md(L, rule, res.get(rule, {}), show_pass)
        L.append("")


def summary_lines(res):
    out = []
    ev = ((res.get("eval") or {}).get("DEV") or {}).get(DECIDES) or {}
    for rule in RULES:
        e = ev.get(rule)
        if not e or not (e.get("stats") or {}).get("trades"):
            out.append(f"{rule} {NAMES[rule]} (SPY, DEV REAL): NOT RUN or no trades")
            continue
        s, pb, w = e["stats"], e["pass_bar"], e.get("worst_day") or ("-", None)
        first = next((n for n, ok in pb["checks"] if not ok), None)
        out.append(f"{rule} {NAMES[rule]} (SPY, DEV REAL): {_yn(pb['pass'])}, {s['trades']} trades, win {_f((s.get('win_rate') or 0) * 100, 1)}%, "
                   f"exp ${s.get('expectancy')}, PF {s.get('pf')}, PF 2x {s.get('pf_2x')}, total ${s.get('total')}, max DD "
                   f"${s.get('max_dd')}, worst day ${w[1]} on {w[0]}" + (f" (first fail: {first})" if first else ""))
    return out


def render(res, meta):
    L = [f"# Sprint round 10: 0DTE credit spreads (C1-C4 and controls), {meta['today']}", "",
         "SPRINT_PLAN Addendum 15.4 (C1 `morning_trend_vertical`, C1-ctl, C1-ic, C2 `afternoon_condor`, C2-ctl) and Amendment 16 "
         "(C3 `gap_condor`, C3-ctl, C4 `dynamic_fly`), pre-registered 2026-11-01 before any round-10 code, pull or run. "
         "**PAPER RESEARCH ONLY**: option selling; Nick's account is long options only and can't trade spreads. **Every number is a "
         "BACKTEST.** DEV 2024-08-01..2026-06-30 on **REAL** Alpaca option bars decides (SPY; QQQ is information). HIST "
         "2016-01-04..2024-01-31 is **MODELED** (BS, one flat IV per day and side; a 0DTE expiry every session) and information only: "
         "a flat IV misprices the skew a seller lives on. L1 (2026-07-01..10-30) and L2 (2024-02-01..07-31) were never read.",
         "", f"Costs: {meta.get('spread')}; plus $0.65 per contract per leg per side; no exit cost when a leg expires worthless; settlement "
             f"at intrinsic at the close (SPY settles physically: after-hours assignment risk is ignored). Stress = 2x the half-spread. "
             f"C2's VIX < 24 uses a **VIX PROXY**: SPY's 20-day realized vol < 19%.", "",
         f"Inputs: {meta.get('files_note', '')}", ""]
    if meta.get("warnings"):
        L += ["**Warnings:**"] + [f"- {w}" for w in meta["warnings"]] + [""]
    L += ["## Summary (SPY, DEV REAL decides)", ""] + [f"- {s}" for s in summary_lines(res)] + [""]
    t = res["trials"]
    L.append(f"Trials: {t['r10_credit']} here ({', '.join(f'{k}: {v}' for k, v in t['parts'].items())}); round 10's tally {t['round10']}; "
             f"the run logs hold {t['prior_in_run_logs']}; the deflated Sharpe uses N = {t['total_for_dsr']} (sr variance "
             f"{res.get('sr_var')}). {t['note']}")
    L.append("")
    ev = res.get("eval") or {}
    L += ["## DEV REAL: the pass bar and each filtered rule beside its control", ""]
    L.append("Pass, all of: at least 100 trades; PF >= 1.25; PF at 2x the half-spread > 1.0; positive in at least 4 of the 6 two-month "
             "blocks of 2025-07..2026-06; the filtered rule (C1, C2, C3) beats its own control's total. Dollars per structure (one "
             "contract per leg). Reported with it: max drawdown, worst day, April 2025 alone, the worst 5 days, months green, the return "
             "on margin and the $3,000 account view.")
    L.append("")
    _window_md(L, "SPY (decides)", (ev.get("DEV") or {}).get("SPY"), True)
    _window_md(L, "QQQ (information)", (ev.get("DEV") or {}).get("QQQ"), True)
    L += ["## HIST MODELED (information only, never a pass)", ""]
    for sym in SYMBOLS:
        _window_md(L, f"{sym} HIST 2016-01-04..2024-01-31 (MODELED)", (ev.get("HIST") or {}).get(sym), False)
    L += ["## Skips and data coverage", ""]
    for key, sk in (res.get("skips") or {}).items():
        L.append(f"- {key}: " + ("; ".join(f"{r}: {why} x{n}" for (r, why), n in sorted(sk.items())) if sk else "none"))
    for key, cv in (res.get("coverage") or {}).items():
        L.append(f"- Strike coverage {key} (needed_option_contracts vs on file, REAL days): {cv}")
    L += ["", "## Deflated Sharpe (information, SPY DEV daily P/L)", ""] + _head(("rule", f"DSR (N = {t['total_for_dsr']})"))
    for k, v in (res.get("dsr") or {}).items():
        L.append(_row([k, _f(v, 4)]))
    cp = res.get("compounding") or {}
    L += ["", "## Compounding view (Amendment 16, information)", "", f"- {cp.get('note', 'not run')}"]
    L += ["", "## Builder's reading", "", "See sprint/r10credit.py's module docstring (R1-R18): times are decisions on the bar that "
          "finished at the stated time, legs filled at their next prints; listed strikes = the $1 grid and a missing leg skips the day; "
          "C2's close = the prior session's close; the VIX proxy = SPY's 20-day sample stdev x sqrt(252); C3's gap = the 09:30 open vs "
          "the prior close; the take profit is checked on finished minutes at the shorts' minus the longs' last prices <= 75% of the "
          "base credit; an in-the-money leg at the close pays the exit cost; controls exist only for C1, C2 and C3.", "",
          "No rule, threshold, window or bar changes after these results; a change is a new amendment, labeled in-sample. A pass is still "
          "paper research: Nick's account can't trade spreads, and nothing reaches a ledger without CLAUDE.md step 5 and Nick's yes. "
          "Not financial advice."]
    return "\n".join(L) + "\n"
