"""sprint/scalp.py - round 9 Part S: the 1-minute option scalper (SPRINT_PLAN Amendment 13, pre-registered 2026-11-01 before
any Part S code or run). Research only: cached bars only, no network, no orders. Option results are DEV REAL (Alpaca
option prices); the underlying check is real stock bars. Every number is a BACKTEST.

Triggers (decisions at each finished 1-minute bar finishing 09:31-15:20, i.e. indices 0-349; SPY + QQQ; 0DTE):
  up trigger    the bar's close > session VWAP and > the highest close of the 5 prior bars;
  down trigger  the bar's close < session VWAP and < the lowest close of the 5 prior bars.
  S1 scalp_trend: down -> buy a put, up -> buy a call. S2 scalp_fade: the same triggers, the opposite option.
  Literal reading: "the 5 prior bars" are the five 1-minute bars of the same session right before the decision bar (bars
  i-5..i-1, all present), so the first possible decision is the bar finishing 09:36 (VWAP is the session's, from 09:30).
  One position at a time per symbol, rule, contract and exit cell: a trigger is taken when that cell's previous exit
  filled at or before the trigger bar ("no new trigger while a position is open").
Contracts (sprint/contracts.pick at the decision bar, BS-EST delta from the last price within 5 minutes): d45-55t50 and
  d20-30t25, from the day's 0DTE contracts (the existing +/-3% strike band of runs 1-3; no new pull). A pick that finds no
  strike in the band is counted per day and reported as the coverage gap.
Entry: the first option print in the 3 minutes after the decision bar (its open), as the engine.
Exits, a 6-cell grid: target +3%, +5% or +8% of the debit, crossed with stop -5% or -10% (debit = the entry fill, traded
  price + half-spread, fees excluded, as the sprint's fixed stops). Judged on each option bar's high/low from the entry bar
  on (desk fills: a bar touching both counts as the stop; a stop fills at the worse of the trigger and the next real price,
  a target at the better of the trigger and the bar's open). Max hold 5 minutes: bars e..e+4 are watched, then out at the
  next bar's open (the first print at or after e+5). All out 15:25 (12:50 on early-close days) the same way. No print to
  exit on = VOID (skipped, counted).
Costs: half-spread = sprint/spread.py's MEASURED-SPREAD from the desk's logged chains where a cell (underlying, premium
  bucket, time bucket, at least 50 rows) has data, else max($0.02, 0.5% of the premium) (ScalpSpread). Logged chains exist
  only for recent months, so applying them to 2024-2025 is an ASSUMPTION, labeled. Plus $0.65 per contract per side.
  Stress: 2x the half-spread on every fill (literal; the desk's "2x slippage" with 4 half-spreads on stops is shown as
  information). Robinhood-fee view: $0.03 per contract per side instead of $0.65 (information).
Choice: per signal and contract on 2024-08-01..2025-06-30, the highest PF among cells with at least 200 trades (ties: more
  trades, the smaller stop, the smaller target). Frozen. Test on 2025-07-01..2026-06-30: at least 200 trades; PF >= 1.20;
  PF at 2x spread > 1.0; positive in at least 4 of the 6 two-month blocks; beats random direction with p < 0.05.
  Random direction: the same entries and exits with a coin-flip side, 200 draws (default_rng(seed), seeds 31-230); for each
  trade the other side is the opposite option picked by the same contract rule at the same decision bar, with the same exit
  cell (the "exits" are the cell's rules, as round 8's random-side twins). A trade whose opposite option has no pick or fill
  is left out of the test (counted); p = the share of draws whose total is at or above the rule's total on the same trades.
S-size (Nick's sizing, on the chosen cell's test-half trades): 5 contracts when the trigger agrees with the day's direction
  (the decision bar's close vs the session's open) and f_rvol >= 1.06 (daytype rvol at the decision bar); otherwise 3.
  Literal reading: "the trigger" is the underlying move (up / down), so for S2 the size follows the trigger, not the option
  bought. Reported: P/L, worst losing streak in $, max drawdown (trade order); account view: each trade's debit x contracts
  as a % of $3,000 and the max drawdown as a % of $3,000. Pass: sized PF >= 1.20 and the sized max drawdown smaller than 50%
  of $3,000. Computed for every (signal, contract) chosen cell.
Underlying first (CLAUDE.md step 3, information only): the S1 / S2 triggers on SPY + QQQ 1-minute stock bars over HIST
  2016-01-04..2024-01-31 and DEV 2024-08-01..2026-06-30 (never L1/L2): entry at the next bar's open (within 3 minutes), the
  move to the open 5 minutes later (the first bar with an open at or after e+5), in the trade's direction, in bps, no costs;
  one position at a time (the next trigger after that exit). Hit rate and mean by year, against random direction (200
  draws, seeds 31-230; p = share of draws whose mean is at or above the rule's). S2 is S1's mirror by construction.
"""
import math
from array import array
from collections import Counter, defaultdict
from datetime import date

import numpy as np

from . import contracts, data, periods, shares
from . import spread as SP
from .fills import ENTRY_WAIT, MULT
from .optpass import entry_fill
from .sim import ALLOUT, EARLY_ALLOUT, NO_NEW_AFTER

SIGNALS = ("scalp_trend", "scalp_fade")
SIG_LABEL = {"scalp_trend": "S1 scalp_trend", "scalp_fade": "S2 scalp_fade"}
CONTRACTS = ("d45-55t50", "d20-30t25")
TARGETS, STOPS = (0.03, 0.05, 0.08), (0.05, 0.10)
FIRST_DEC, LAST_DEC, LOOKBACK, MAX_HOLD = 0, 349, 5, 5
FEE, RH_FEE = 0.65, 0.03
FALLBACK_PCT, FALLBACK_MIN = 0.005, 0.02
CHOICE = ("2024-08-01", "2025-06-30")
TEST = ("2025-07-01", "2026-06-30")
MIN_TRADES, PF_MIN = 200, 1.20
BLOCKS = (("Jul-Aug 2025", "2025-07-01", "2025-08-31"), ("Sep-Oct 2025", "2025-09-01", "2025-10-31"),
          ("Nov-Dec 2025", "2025-11-01", "2025-12-31"), ("Jan-Feb 2026", "2026-01-01", "2026-02-28"),
          ("Mar-Apr 2026", "2026-03-01", "2026-04-30"), ("May-Jun 2026", "2026-05-01", "2026-06-30"))
RANDOM_SEEDS = tuple(range(31, 231))
SIZE_BIG, SIZE_BASE, SIZE_RVOL = 5, 3, 1.06
ACCOUNT = 3000.0
SYMBOLS = ("SPY", "QQQ")
REASONS = ("FIXED STOP", "FIXED TARGET", "MAX HOLD", "ALL OUT")


def cell_id(target, stop):
    return f"t{int(round(target * 100)):02d}_s{int(round(stop * 100)):02d}"


CELLS = [(cell_id(t, s), s, t) for t in TARGETS for s in STOPS]          # (id, stop, target)
CELL_IDS = [c[0] for c in CELLS]
assert len(CELLS) == 6


# ---------------------------------------------------------------- costs
class ScalpSpread(SP.SpreadModel):
    """MEASURED-SPREAD from logged chains where a cell has data, else max($0.02, 0.5% of premium) (Amendment 13)."""

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
            return ("Part S fallback everywhere: half-spread = max($0.02, 0.5% of premium) (no logged chains found: "
                    "MODELED-SPREAD)")
        cov = ", ".join(f"{u} {c['days']} days/{c['rows']} rows" for u, c in sorted(self.coverage.items()))
        return (f"MEASURED-SPREAD from logged chains ({cov}) where a cell has data (an ASSUMPTION for 2024-2025: the chains "
                f"are recent); else max($0.02, 0.5% of premium)")


def scalp_spread(chains_dir, unders=SYMBOLS):
    base = SP.from_chains(chains_dir, set(unders))
    return ScalpSpread(base.table, base.coverage)


def leg_pnl(b_in, hs_in, basis, hs_out, is_stop, k=1, fee=FEE, desk_stop=False):
    """$ P/L of one contract: buy at b_in + k x hs_in, sell at basis - k x hs_out (2k on a stop with desk_stop and k > 1)."""
    kk = 2 * k if (desk_stop and is_stop and k > 1) else k
    buy = b_in + k * hs_in
    sell = max(0.0, basis - kk * hs_out)
    return (sell - buy) * MULT - 2 * fee


# ---------------------------------------------------------------- triggers
def triggers(ctx):
    """[(bar index, +1 up / -1 down)] on finished bars 0-349 (before the all-out decision window closes)."""
    c, vw = ctx.c, ctx.vwap
    out = []
    last = min(LAST_DEC, ctx.close_idx - 2)
    for i in range(max(FIRST_DEC, LOOKBACK), last + 1):
        ci, vi = c[i], vw[i]
        if math.isnan(ci) or math.isnan(vi):
            continue
        prior = c[i - LOOKBACK:i]
        if np.isnan(prior).any():
            continue
        if ci > vi and ci > prior.max():
            out.append((i, 1))
        elif ci < vi and ci < prior.min():
            out.append((i, -1))
    return out


def side_of(signal, d):
    if signal == "scalp_trend":
        return "C" if d > 0 else "P"
    return "P" if d > 0 else "C"


# ---------------------------------------------------------------- exits
def _first(mask):
    k = int(np.argmax(mask)) if len(mask) else 0
    return k if len(mask) and mask[k] else None


def scalp_exits(tape, e, allout_idx, debit, cells=CELLS, max_hold=MAX_HOLD):
    """One pass over bars e .. min(e + max_hold, all-out) - 1 for every cell: {cell id: (exit bar, basis, reason, is_stop)
    or None (VOID)}."""
    w = min(e + max_hold, allout_idx)
    seg = slice(e, w)
    has = ~np.isnan(tape.o[seg])
    lo, hi = tape.l[seg], tape.h[seg]
    x_t = None
    out = {}
    for cid, stop, target in cells:
        sp, tg = debit * (1 - stop), debit * (1 + target)
        ks, kt = _first(has & (lo <= sp)), _first(has & (hi >= tg))
        if ks is not None and (kt is None or ks <= kt):
            i = e + ks
            out[cid] = (i, tape.stop_basis(i, sp)[0], "FIXED STOP", True)
        elif kt is not None:
            i = e + kt
            out[cid] = (i, tape.target_basis(i, tg)[0], "FIXED TARGET", False)
        else:
            if x_t is None:
                x_t = tape.next_print(w)
                x_t = -1 if x_t is None else x_t
            out[cid] = None if x_t < 0 else (x_t, float(tape.o[x_t]), "MAX HOLD" if w < allout_idx else "ALL OUT", False)
    return out


def pick_both(ctx, side, i, rules=CONTRACTS):
    """contracts.pick for several 0DTE rules at once: the same candidates, prices, BS-EST solve, band, spread cap, key and
    tie order as contracts.pick (tests check they agree), with ONE implied-vol solve shared by the rules.
    Returns {rule: (tape, info) or (None, reason)}."""
    from . import bs
    out = {}
    S_ = ctx.c[i]
    if math.isnan(S_):
        return {r: (None, "no underlying close at the signal bar") for r in rules}
    cands = [t for t in ctx.tapes.values() if t.right == side]
    if not cands:
        return {r: (None, "no 0DTE contracts on file for this side") for r in rules}
    px = np.array([t.last_close(i, contracts.MAX_AGE) or np.nan for t in cands], float)
    K = np.array([t.strike for t in cands], float)
    ok = ~np.isnan(px)
    if not ok.any():
        return {r: (None, "no contract traded in the 5 minutes before the signal") for r in rules}
    T = bs.t_years(390 - (i + 1))
    iv, d = bs.iv_delta_v(np.where(ok, px, 1.0), float(S_), K, T, np.array([side == "C"] * len(cands)))
    for rule in rules:
        lo, hi, tgt = contracts.RULES[rule]
        best = None
        for j, t in enumerate(cands):
            if not ok[j] or math.isnan(d[j]):
                continue
            ad = abs(float(d[j]))
            if not lo <= ad <= hi:
                continue
            if ctx.spread is not None and not ctx.spread.spread_ok(ctx.sym, float(px[j]), i + 1):
                continue
            key = (abs(ad - tgt), float(px[j]))
            if best is None or key < best[0]:
                best = (key, t, {"symbol": t.symbol, "strike": t.strike, "right": t.right, "px": float(px[j]), "iv": float(iv[j]),
                                 "delta": round(float(d[j]), 3), "delta_label": "BS-EST", "rule": rule,
                                 "expiry": str(getattr(t, "expiry", ctx.day))})
        out[rule] = (None, f"no contract with BS-EST |delta| in {lo:.2f}-{hi:.2f}") if best is None else (best[1], best[2])
    return out


class Outcomes:
    """Per (decision bar, side, contract rule): the pick, the entry fill and every cell's exit, computed once per day."""

    def __init__(self, ctx, spread):
        self.ctx, self.spread = ctx, spread
        self.allout = EARLY_ALLOUT if ctx.early else ALLOUT["15:25"]
        self.cache = {}
        self.pk = {}
        self.picks = Counter()

    def get(self, j, side, rule):
        k = (j, side, rule)
        if k in self.cache:
            return self.cache[k]
        ctx = self.ctx
        dec = j + 1
        res = None
        if dec >= NO_NEW_AFTER:
            res = "no new trades after 15:30"
        elif dec >= self.allout:
            res = "signal after the all-out time"
        else:
            if (j, side) not in self.pk:
                self.pk[(j, side)] = pick_both(ctx, side, j)
            tape, info = self.pk[(j, side)][rule]
            if tape is None:
                res = info
                self.picks["no pick: " + info] += 1
            else:
                self.picks["picked"] += 1
                f = entry_fill(ctx, j, tape, self.spread, self.allout)
                if f is None:
                    res = f"no option print in the {ENTRY_WAIT} minutes after the signal"
                else:
                    e, b_in, hs_in, _C, debit, costs = f
                    ex = scalp_exits(tape, e, self.allout, debit)
                    pn = {}
                    for cid, r in ex.items():
                        if r is None:
                            pn[cid] = None
                            continue
                        x, basis, reason, is_stop = r
                        hs = costs.hs(basis, x)
                        pn[cid] = (x, reason, leg_pnl(b_in, hs_in, basis, hs, is_stop, 1), leg_pnl(b_in, hs_in, basis, hs, is_stop, 2),
                                   leg_pnl(b_in, hs_in, basis, hs, is_stop, 2, desk_stop=True),
                                   leg_pnl(b_in, hs_in, basis, hs, is_stop, 1, fee=RH_FEE), basis)
                    lab = self.spread.half_spread(ctx.sym, b_in, e)[1]
                    res = {"e": e, "b_in": b_in, "hs_in": hs_in, "debit": round((b_in + hs_in) * MULT + FEE, 2), "cells": pn,
                           "contract": info["symbol"], "measured": lab == "MEASURED-SPREAD"}
        self.cache[k] = res
        return res


class Collector:
    """Typed per-trade columns for every (signal, contract, cell)."""

    COLS = (("signal", "b"), ("contract", "b"), ("cell", "b"), ("sym", "b"), ("day", "i"), ("side", "b"), ("trig", "b"),
            ("j", "h"), ("e", "h"), ("x", "h"), ("reason", "b"), ("pnl", "d"), ("pnl_2x", "d"), ("pnl_2x_desk", "d"),
            ("pnl_rh", "d"), ("debit", "d"), ("b_in", "d"), ("b_out", "d"), ("opp_pnl", "d"), ("opp_pnl_2x", "d"),
            ("day_dir", "b"), ("rvol", "d"), ("measured", "b"))

    def __init__(self, symbols):
        self.symbols = list(symbols)
        self.cols = {k: array(t) for k, t in self.COLS}
        self.skips = defaultdict(Counter)
        self.picks = defaultdict(Counter)            # (symbol, day) -> pick outcomes (coverage)
        self.triggers = Counter()

    def __len__(self):
        return len(self.cols["pnl"])

    def add(self, **kw):
        for k, _t in self.COLS:
            self.cols[k].append(kw[k])

    def frame(self):
        import pandas as pd
        c = {k: np.frombuffer(v, dtype=v.typecode).copy() if len(v) else np.zeros(0) for k, v in self.cols.items()}
        n = len(c["pnl"])
        if not n:
            return pd.DataFrame(columns=["signal", "contract", "cell", "symbol", "day"] + [k for k, _ in self.COLS[5:]])
        df = pd.DataFrame({"signal": pd.Categorical.from_codes(c["signal"].astype(int), SIGNALS),
                           "contract": pd.Categorical.from_codes(c["contract"].astype(int), CONTRACTS),
                           "cell": pd.Categorical.from_codes(c["cell"].astype(int), CELL_IDS),
                           "symbol": pd.Categorical.from_codes(c["sym"].astype(int), self.symbols),
                           "day": [date.fromordinal(int(x)).isoformat() for x in c["day"]],
                           "side": np.where(c["side"] > 0, "C", "P"), "trig": c["trig"].astype(int), "signal_idx": c["j"].astype(int),
                           "entry_idx": c["e"].astype(int), "exit_idx": c["x"].astype(int),
                           "exit_reason": pd.Categorical.from_codes(c["reason"].astype(int), REASONS)})
        for k in ("pnl", "pnl_2x", "pnl_2x_desk", "pnl_rh", "debit", "opp_pnl", "opp_pnl_2x"):
            df[k] = np.round(c[k], 2)
        df["entry_basis"], df["exit_basis"] = np.round(c["b_in"], 4), np.round(c["b_out"], 4)
        df["day_dir"] = c["day_dir"].astype(int)
        df["rvol"] = c["rvol"]
        df["measured_spread"] = c["measured"].astype(bool)
        return df


def run_day(ctx, spread, col):
    """Every (signal, contract, cell) on one (symbol, day)."""
    trig = triggers(ctx)
    col.triggers[ctx.sym] += len(trig)
    if not trig:
        return
    oc = Outcomes(ctx, spread)
    o0 = next((float(x) for x in ctx.o if not math.isnan(x)), math.nan)
    dt = None
    rv_cache = {}
    sym_i = col.symbols.index(ctx.sym)
    for si, signal in enumerate(SIGNALS):
        for ci, rule in enumerate(CONTRACTS):
            state = {cid: -1 for cid in CELL_IDS}
            for j, d in trig:
                flat = [cid for cid in CELL_IDS if j >= state[cid]]
                for cid in CELL_IDS:
                    if cid not in flat:
                        col.skips[(signal, rule, cid)]["busy: one position at a time"] += 1
                if not flat:
                    continue
                side = side_of(signal, d)
                r = oc.get(j, side, rule)
                if not isinstance(r, dict):
                    for cid in flat:
                        col.skips[(signal, rule, cid)][r] += 1
                    continue
                opp = oc.get(j, "P" if side == "C" else "C", rule)
                if j not in rv_cache:
                    if dt is None:
                        dt = ctx.daytype()
                    rv = dt._rvol(j)
                    rv_cache[j] = math.nan if rv is None else float(rv)
                cj = float(ctx.c[j])
                day_dir = 0 if math.isnan(o0) or cj == o0 else (1 if cj > o0 else -1)
                for cid in flat:
                    p = r["cells"][cid]
                    if p is None:
                        col.skips[(signal, rule, cid)]["VOID: no option print to exit on before the close"] += 1
                        continue
                    x, reason, p1, p2, p2d, prh, b_out = p
                    op = opp["cells"].get(cid) if isinstance(opp, dict) else None
                    col.add(signal=si, contract=ci, cell=CELL_IDS.index(cid), sym=sym_i, day=ctx.day.toordinal(),
                            side=1 if side == "C" else -1, trig=d, j=j, e=r["e"], x=x, reason=REASONS.index(reason), pnl=p1,
                            pnl_2x=p2, pnl_2x_desk=p2d, pnl_rh=prh, debit=r["debit"], b_in=r["b_in"], b_out=b_out,
                            opp_pnl=op[2] if op else math.nan, opp_pnl_2x=op[3] if op else math.nan, day_dir=day_dir,
                            rvol=rv_cache[j], measured=1 if r["measured"] else 0)
                    state[cid] = x
    key = (ctx.sym, ctx.day.isoformat())
    for k, v in oc.picks.items():
        col.picks[key][k] += v


def run(series_by_sym, spread, a=periods.DEV[0], b=periods.DEV[1], root=None, progress=None, limit_days=None):
    """Part S over [a, b] (DEV only): a Collector."""
    import time
    if periods.overlaps(a, b) or a < periods.DEV[0] or b > periods.DEV[1]:
        raise periods.LockedPeriod(f"REFUSED: Part S runs on DEV {periods.DEV[0]}..{periods.DEV[1]} only, not {a}..{b}")
    col = Collector(sorted(series_by_sym))
    t0 = time.time()
    for sym in sorted(series_by_sym):
        ser = series_by_sym[sym]
        days = [d for d in ser.days if a <= d <= b and not periods.overlaps(d, d)]
        if limit_days:
            days = days[:limit_days]
        odays = data.option_days(sym, root)
        for n, d in enumerate(days):
            ctx = data.DayContext(ser, d, {}, spread)
            if d not in odays:
                col.skips[("all", "all", "all")]["no 0DTE option data for the day"] += 1
                continue
            ctx.tapes = data.read_option_day(sym, d, root)
            run_day(ctx, spread, col)
            if progress and (n % 50 == 0 or n == len(days) - 1):
                progress(f"  Part S {sym} {d} ({n + 1}/{len(days)} sessions, {len(col)} trades, {time.time() - t0:.0f}s)")
    return col


# ---------------------------------------------------------------- readouts
def _pf(p):
    p = np.asarray(p, float)
    lo, w = -p[p < 0].sum(), p[p > 0].sum()
    if lo > 0:
        return round(float(w / lo), 3)
    return math.inf if w > 0 else None


def _pfr(x):
    return -1.0 if x is None else float(x)


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), n)


def cstats(g):
    """Numbers of one cell's trades (a frame slice in trade order)."""
    p = g["pnl"].to_numpy(float)
    out = {"trades": int(len(p))}
    if not len(p):
        return out
    p2, p2d, prh = (g[k].to_numpy(float) for k in ("pnl_2x", "pnl_2x_desk", "pnl_rh"))
    w, lo = p[p > 0], p[p < 0]
    eq = np.cumsum(p)
    dd = float((eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min())
    aw, al = (float(w.mean()) if len(w) else None), (float(lo.mean()) if len(lo) else None)
    out.update({"win_rate": round(len(w) / len(p), 3), "avg_win": _r(aw), "avg_loss": _r(al),
                "be_win_rate": round(abs(al) / (aw + abs(al)), 3) if aw is not None and al is not None else None,
                "expectancy": _r(p.mean()), "pf": _pf(p), "pf_2x": _pf(p2), "pf_2x_desk": _pf(p2d), "total": _r(p.sum()),
                "total_2x": _r(p2.sum()), "max_dd": _r(min(dd, 0.0)), "pf_rh": _pf(prh), "total_rh": _r(prh.sum()),
                "expectancy_rh": _r(prh.mean()), "avg_debit": _r(g["debit"].mean()),
                "measured_share": _r(g["measured_spread"].mean(), 3) if "measured_spread" in g else None})
    return out


def ordered(df):
    return df.sort_values(["day", "entry_idx", "symbol"], kind="stable")


def win(df, a, b):
    return df[(df["day"] >= a) & (df["day"] <= b)]


def choose_cell(cells_choice, min_n=MIN_TRADES):
    """cells_choice: [(cell id, stop, target, stats)]. Highest PF among cells with >= min_n trades; ties: more trades, the
    smaller stop, the smaller target. None when no cell has min_n trades."""
    elig = [c for c in cells_choice if c[3]["trades"] >= min_n and c[3].get("pf") is not None]
    if not elig:
        return None
    return min(elig, key=lambda c: (-(math.inf if math.isinf(c[3]["pf"]) else c[3]["pf"]), -c[3]["trades"], c[1], c[2]))[0]


def blocks(g):
    out = {}
    for name, a, b in BLOCKS:
        s = win(g, a, b)["pnl"]
        out[name] = {"trades": int(len(s)), "net": _r(float(s.sum())) if len(s) else 0.0}
    return out


def random_direction(g, seeds=RANDOM_SEEDS):
    """(p, totals, trades used, trades left out) on trades with a priced opposite side."""
    ok = np.isfinite(g["opp_pnl"].to_numpy(float))
    p, q = g["pnl"].to_numpy(float)[ok], g["opp_pnl"].to_numpy(float)[ok]
    if not len(p):
        return None, np.zeros(0), 0, int((~ok).sum())
    actual = float(p.sum())
    tots = np.array([float(np.where(np.random.default_rng(s).choice(np.array([-1.0, 1.0]), len(p)) > 0, p, q).sum()) for s in seeds])
    return round(float((tots >= actual - 1e-9).mean()), 4), tots, int(len(p)), int((~ok).sum())


def test_bar(g):
    s = cstats(g)
    bl = blocks(g)
    green = sum(1 for v in bl.values() if (v["net"] or 0) > 0)
    p, tots, used, left = random_direction(g)
    ch = [(f"at least {MIN_TRADES} trades ({s['trades']})", s["trades"] >= MIN_TRADES),
          (f"PF >= {PF_MIN} ({s.get('pf')})", _pfr(s.get("pf")) >= PF_MIN),
          (f"PF at 2x spread > 1.0 ({s.get('pf_2x')})", _pfr(s.get("pf_2x")) > 1.0),
          (f"positive in at least 4 of the 6 two-month blocks ({green} of 6)", green >= 4),
          (f"beats random direction, p < 0.05 (p = {p}, {used} trades, {left} without an opposite)", p is not None and p < 0.05)]
    return {"stats": s, "blocks": bl, "random_p": p, "random_median": _r(float(np.median(tots))) if len(tots) else None,
            "random_trades": used, "random_left_out": left, "checks": ch, "pass": all(ok for _, ok in ch)}


def sizes(g):
    """S-size contracts per trade: 5 when the trigger agrees with the day's direction and rvol >= 1.06, else 3."""
    agree = (g["trig"].to_numpy(int) == g["day_dir"].to_numpy(int)) & (g["day_dir"].to_numpy(int) != 0)
    rv = g["rvol"].to_numpy(float)
    big = agree & np.isfinite(rv) & (rv >= SIZE_RVOL)
    return np.where(big, SIZE_BIG, SIZE_BASE)


def worst_streak(p):
    """The most negative sum over a run of consecutive losing trades (0 if none lost)."""
    worst = run = 0.0
    for x in p:
        run = run + x if x < 0 else 0.0
        worst = min(worst, run)
    return worst


def max_dd(p):
    if not len(p):
        return 0.0
    eq = np.cumsum(p)
    return float(min(0.0, (eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min()))


def s_size(g):
    n = sizes(g)
    p = g["pnl"].to_numpy(float) * n
    p2 = g["pnl_2x"].to_numpy(float) * n
    deb = g["debit"].to_numpy(float) * n
    dd = max_dd(p)
    pf = _pf(p) if len(p) else None
    ch = [(f"sized PF >= {PF_MIN} ({pf})", _pfr(pf) >= PF_MIN),
          (f"sized max drawdown smaller than 50% of $3,000 ({_r(dd)} = {_r(dd / ACCOUNT * 100, 1)}% of $3,000)", -dd < 0.5 * ACCOUNT)]
    return {"trades": int(len(p)), "five": int((n == SIZE_BIG).sum()), "three": int((n == SIZE_BASE).sum()), "pnl": _r(p.sum()),
            "pnl_2x": _r(p2.sum()), "pf": pf, "pf_2x": _pf(p2) if len(p) else None, "worst_losing_streak": _r(worst_streak(p)),
            "max_dd": _r(dd), "account": {"max_dd_pct_3000": _r(dd / ACCOUNT * 100, 1),
                                         "debit_pct_3000": debit_pct(deb), "flat_debit_pct_3000": debit_pct(g["debit"].to_numpy(float))},
            "checks": ch, "pass": all(ok for _, ok in ch)}


def debit_pct(deb):
    deb = np.asarray(deb, float)
    if not len(deb):
        return None
    pct = deb / ACCOUNT * 100
    return {"median": _r(float(np.median(pct)), 1), "p90": _r(float(np.percentile(pct, 90)), 1), "max": _r(float(pct.max()), 1),
            "over_100": int((pct > 100).sum())}


def evaluate(df):
    """Every (signal, contract): all 6 cells in each half, the frozen choice, its test, S-size."""
    out = {}
    df = ordered(df) if len(df) else df
    for signal in SIGNALS:
        for rule in CONTRACTS:
            g0 = df[(df["signal"] == signal) & (df["contract"] == rule)] if len(df) else df
            cells, table = [], {}
            for cid, stop, target in CELLS:
                g = g0[g0["cell"] == cid] if len(g0) else g0
                ch_s, te_s = cstats(win(g, *CHOICE)), cstats(win(g, *TEST))
                table[cid] = {"stop": stop, "target": target, "choice": ch_s, "test": te_s}
                cells.append((cid, stop, target, ch_s))
            chosen = choose_cell(cells)
            res = {"signal": signal, "contract": rule, "cells": table, "chosen": chosen}
            if chosen is None:
                res.update(test=None, s_size=None, pass_=False, why_not=f"no cell kept {MIN_TRADES} trades in {CHOICE[0]}..{CHOICE[1]}")
            else:
                g = win(g0[g0["cell"] == chosen], *TEST)
                tb = test_bar(g)
                res.update(test=tb, s_size=s_size(g), pass_=tb["pass"],
                           why_not=None if tb["pass"] else next(n for n, ok in tb["checks"] if not ok))
                res["_test_rows"] = g
            out[f"{signal}|{rule}"] = res
    return out


def coverage(col):
    """Pick outcomes per symbol: days with any pick failing for lack of a strike in the delta band (the coverage gap)."""
    out = defaultdict(lambda: {"days": 0, "days_with_band_gap": 0, "picked": 0, "no_strike_in_band": 0, "no_recent_price": 0, "other": 0})
    for (sym, _d), cnt in col.picks.items():
        o = out[sym]
        o["days"] += 1
        gap = 0
        for k, v in cnt.items():
            if k == "picked":
                o["picked"] += v
            elif "BS-EST |delta|" in k:
                o["no_strike_in_band"] += v
                gap += v
            elif "5 minutes" in k:
                o["no_recent_price"] += v
            else:
                o["other"] += v
        o["days_with_band_gap"] += 1 if gap else 0
    return dict(out)


# ---------------------------------------------------------------- the underlying check
def underlying_day(ctx):
    """[(move in bps in the S1 direction, trigger direction)] with one position at a time and a 5-minute hold."""
    out = []
    busy = -1
    for j, d in triggers(ctx):
        if j < busy:
            continue
        e = shares.fill_bar(ctx, j, data.N - 1)
        if e is None:
            continue
        x = next((k for k in range(e + MAX_HOLD, data.N) if ctx.has_bar(k) and not math.isnan(ctx.o[k])), None)
        if x is None:
            continue
        out.append((d * (float(ctx.o[x]) / float(ctx.o[e]) - 1) * 1e4, d))
        busy = x
    return out


def underlying(series_by_src, progress=None):
    """{"S1 scalp_trend": {...}, "S2 scalp_fade": {...}}: by year and overall, hit rate and mean bps vs random direction."""
    year, mv, sym = [], [], []
    for (src, s), ser in sorted(series_by_src.items()):
        a, b = periods.HIST if src == "HIST" else periods.DEV
        days = [d for d in ser.days if a <= d <= b and not periods.overlaps(d, d)]
        for n, d in enumerate(days):
            ctx = data.DayContext(ser, d, {}, None)
            for m, _d in underlying_day(ctx):
                year.append(d.year)
                mv.append(m)
                sym.append(s)
            if progress and (n % 500 == 0 or n == len(days) - 1):
                progress(f"  Part S underlying {src} {s} {d} ({n + 1}/{len(days)} sessions, {len(mv)} trades)")
    year, mv = np.array(year, int), np.array(mv, float)
    out = {}
    for name, sign in (("S1 scalp_trend", 1.0), ("S2 scalp_fade", -1.0)):
        m = sign * mv
        rows = {"all": _ustats(m)}
        for y in sorted(set(year.tolist())):
            rows[str(y)] = _ustats(m[year == y])
        out[name] = {"by_year": rows, "symbols": sorted(set(sym))}
    return out


def _ustats(m, seeds=RANDOM_SEEDS):
    if not len(m):
        return {"trades": 0}
    means, hits = [], []
    for s in seeds:
        f = np.random.default_rng(s).choice(np.array([-1.0, 1.0]), len(m))
        means.append(float((f * m).mean()))
        hits.append(float(((f * m) > 0).mean()))
    means = np.array(means)
    act = float(m.mean())
    return {"trades": int(len(m)), "hit_rate": round(float((m > 0).mean()), 3), "mean_bps": round(act, 3),
            "random_mean_bps": round(float(means.mean()), 3), "random_p95_bps": round(float(np.percentile(means, 95)), 3),
            "random_hit_rate": round(float(np.mean(hits)), 3), "p": round(float((means >= act - 1e-12).mean()), 4)}
