"""sprint/engine.py - runs many sprint configurations over the cached data in one streaming pass.

A run = entry setup x side x symbols x exit configuration (sim.ExitCfg) x filters, plus optional research twists:
made-up levels (fake_seed) or matched random entries (random). Each (symbol, session) is loaded once; its entry
signals and contract picks are computed once and shared by every run that uses them, so exit variants differ only
in their exit rule.
One position at a time per run and symbol: a signal is taken only if the run is flat at the signal bar's end (the
previous trade's exit filled at or before that bar). A skipped signal is counted with its reason.
Filters (entry-level, pre-registered in SPRINT_PLAN "Day type"):
  after14      entries deciding at/after 14:00 need er30 >= 0.35, VWAP crosses (60) <= 2, overlap30 < 0.60, RVOL >= 1.2
  chop2        at most 2 trades on a day whose day_type is "chop" at the decision
  trend_only   only when daytype.trend_aligned at the decision
  noise_trend  only when the bar-computable noise_trend score says trade
  sma20_side   calls only when the prior session's close is above its 20-day SMA (closes ending at that close), puts
               only when below (the symbol's own daily closes; for SPY this is Option Alpha's SPY SMA(20) side rule)
  sma20_side_1pct  the same with a 1% margin: calls only when the prior close is at least 1% above the SMA, puts only
               when at least 1% below, no trade in between
  skip_fomc    no entries on an FOMC statement day (sprint/events.py)
  skip_fomc_cpi  no entries on an FOMC statement day or a CPI release day (sprint/events.py, sources listed there)
  vixy_falling "VIX falling" (Option Alpha optimizer lead on its run 023, in-sample there): at the decision, VIXY's last
               finished 1-minute close (at or before the signal bar) is below VIXY's prior regular-session close.
               PROXY: VIXY (Alpaca has no VIX index). Applied as stated to calls and puts alike (no mirror given).
  gap_side_075 open-gap side rule (the optimizer's second lead): calls only when today's 09:30 open vs the prior
               close is above 0% and at most +0.75%, puts only when below 0% and at least -0.75% (the symbol's own)
  vixy_pctl_le40 / vixy_pctl_ge60   "IV-rank proxy: VIXY percentile": the share of the 252 split-adjusted daily VIXY
               closes ending at the prior session's close that are <= that close is <= 40% (calm) / >= 60% (stressed).
               The window skips the locked months (never pulled), so early in NOT_SEEN it reaches back into 2023.
               VIXY decays over time (futures roll), so this percentile runs lower than a true IV rank: a labeled proxy.
  vixy_not_rising / vixy_rising_1pct   VIXY's last finished 1-minute close at the decision is <= its prior close x 1.01
               (VIX not rising) / >= its prior close x 1.01 (rising at least 1%). PROXY: VIXY.
Several filters on one run must all pass (oa_crosscheck_v2's "calm" regime = vixy_pctl_le40 + vixy_not_rising +
gap_side_075; the mirrored put regime = vixy_pctl_ge60 + vixy_rising_1pct).
An event day outside the calendar's coverage is not traded by these filters (counted as "event calendar unknown").
Specs may give a grid value as an object to set several fields together (e.g. a stop/target pair).
"""
import csv
import gzip
import io
import itertools
import json
import random
import time
import zlib
from collections import Counter, defaultdict
from dataclasses import replace

import numpy as np

from . import contracts, data, entries
from .sim import ExitCfg, simulate

LEAN = ("symbol", "day", "setup", "side", "entry_idx", "exit_idx", "entry_time", "exit_time", "pnl", "pnl_2x", "pct_peak_kept",
        "planned_rr_opt", "planned_rr_stock", "actual_rr", "exit_reason", "exit_is_stop", "opt_mfe_pct", "opt_mae_pct",
        "stock_mfe", "stock_mae", "peak_level", "minutes_held", "peak_profit", "tp_eff", "day_type", "signal_price",
        "stop_stock", "target_stock", "invalid")
TRADE_COLS = ["run_id", "symbol", "day", "setup", "side", "contract", "strike", "delta_est", "iv_est", "signal_idx", "signal_price",
              "entry_time", "entry_basis", "entry_hs", "entry_fill", "cost_basis", "stock_entry", "exit_time", "exit_basis",
              "exit_reason", "exit_is_stop", "stock_exit", "pnl", "pnl_2x", "opt_mfe_pct", "opt_mae_pct", "stock_mfe", "stock_mae",
              "peak_time", "peak_px", "peak_profit", "pct_peak_kept", "peak_level", "planned_rr_stock", "planned_rr_opt",
              "planned_risk", "actual_rr", "stop_stock", "target_stock", "target_level", "ceiling", "tp_eff", "trend_at_entry",
              "day_type", "rvol", "minutes_held", "legs"]


def run_key(r):
    return json.dumps({"entry": r["entry"], "side": r["side"], "symbols": list(r["symbols"]), "exit": r["exit"].as_dict(),
                       "filters": sorted(r.get("filters") or []), "fake": r.get("fake_seed"), "random": r.get("random_tag")},
                      sort_keys=True)


def expand(spec):
    """Spec JSON -> list of runs (dicts with an ExitCfg)."""
    d = dict(spec.get("defaults") or {})
    syms = tuple(spec.get("symbols") or ["SPY"])
    runs, seen = [], set()
    for blk in spec["blocks"]:
        grid = blk["grid"]
        keys = list(grid)
        for combo in itertools.product(*(grid[k] for k in keys)):
            cfg = dict(d)
            for k, v in zip(keys, combo):
                if isinstance(v, dict):
                    cfg.update(v)                                 # a combo: several fields that move together
                else:
                    cfg[k] = v
            r = {"block": blk["name"], "entry": cfg["entry"], "side": cfg.get("side", "both"), "symbols": tuple(cfg.get("symbols") or syms),
                 "filters": tuple(cfg.get("filters") or ()), "exit": ExitCfg.from_dict(cfg)}
            k = run_key(r)
            if k in seen:
                continue
            seen.add(k)
            r["run_id"] = f"{spec['spec_id']}-{len(runs) + 1:03d}"
            runs.append(r)
    return runs


def _filters_ok(r, ctx, sig, day_count):
    fs = r.get("filters") or ()
    if not fs:
        return None
    dt = ctx.daytype()
    f = dt.features(sig.idx)
    if "after14" in fs and sig.idx + 1 >= 270:
        if not ((f["er30"] or 0) >= 0.35 and f["vwap_x60"] is not None and f["vwap_x60"] <= 2 and f["overlap30"] is not None
                and f["overlap30"] < 0.60 and (f["rvol"] or 0) >= 1.2):
            return "after-14:00 filter"
    if "chop2" in fs and f["day_type"] == "chop" and day_count >= 2:
        return "chop day: 2 trades already"
    if "trend_only" in fs and not dt.trend_aligned(sig.idx, sig.side):
        return "not a trend day (trend_only)"
    if "noise_trend" in fs and not f["noise_trend"]["trade"]:
        return "noise_trend score < 2"
    for name, margin in (("sma20_side", 0.0), ("sma20_side_1pct", 0.01)):
        if name in fs:
            sd = ctx.series.sma_side(ctx.day, 20, margin)
            if sd is None:
                return "side rule: fewer than 20 prior sessions"
            if sd == 0 and margin:
                return "side rule: prior close within 1% of the 20-day SMA"
            if sd != (1 if sig.side == "C" else -1):
                return "side rule: prior close on the wrong side of the 20-day SMA"
    if "skip_fomc" in fs or "skip_fomc_cpi" in fs:
        from . import events
        fo = events.is_fomc(ctx.day)
        cp = events.is_cpi(ctx.day) if "skip_fomc_cpi" in fs else False
        if fo is None or cp is None:
            return "event calendar unknown for this date"
        if fo:
            return "FOMC day skipped"
        if cp:
            return "CPI day skipped"
    vix_1m = [f for f in ("vixy_falling", "vixy_not_rising", "vixy_rising_1pct") if f in fs]
    if vix_1m:
        vx = ctx.aux.get("VIXY")
        if vx is None or ctx.day not in vx.rth:
            return "no VIXY bars for the day (VIX proxy)"
        pc = vx.prev_day(ctx.day)
        if pc is None:
            return "no VIXY prior close (VIX proxy)"
        closes = vx.rth[ctx.day][:sig.idx + 1, 3]
        closes = closes[~np.isnan(closes)]
        if not len(closes):
            return "no VIXY bar yet today (VIX proxy)"
        last, prev = float(closes[-1]), pc["close"]
        if "vixy_falling" in fs and not last < prev:
            return "VIX proxy (VIXY) not below its prior close"
        if "vixy_not_rising" in fs and not last <= prev * 1.01:
            return "VIX proxy (VIXY) up more than 1% on its prior close"
        if "vixy_rising_1pct" in fs and not last >= prev * 1.01:
            return "VIX proxy (VIXY) not up 1% on its prior close"
    if "vixy_pctl_le40" in fs or "vixy_pctl_ge60" in fs:
        prev = ctx.series.prev_day(ctx.day)
        pr = data.percentile_rank(ctx.aux.get("VIXY_D"), prev["day"]) if prev else None
        if pr is None:
            return "VIXY percentile unknown (needs 252 daily closes up to the prior session)"
        if "vixy_pctl_le40" in fs and pr > 0.40:
            return "VIXY percentile above 40% (not calm)"
        if "vixy_pctl_ge60" in fs and pr < 0.60:
            return "VIXY percentile below 60%"
    if "gap_side_075" in fs:
        prev = ctx.series.prev_day(ctx.day)
        if prev is None or np.isnan(ctx.o[0]):
            return "no prior close or open for the gap rule"
        g = round(float(ctx.o[0]) / prev["close"] - 1, 10)        # exact at the 0.75% edge despite float noise
        if not ((0 < g <= 0.0075) if sig.side == "C" else (-0.0075 <= g < 0)):
            return "gap outside 0 to +/-0.75% for this side"
    return None


def _random_signals(r, ctx):
    """Matched random entries for this (symbol, day): same sides, same stock stop distances, random minute."""
    spec = r["random"]
    out = []
    for n, (side, dist, lo, hi) in enumerate(spec["matched"].get(f"{ctx.sym}|{ctx.day.isoformat()}", [])):
        rnd = random.Random(zlib.crc32(f"{spec['seed']}|{ctx.sym}|{ctx.day}|{n}".encode()))
        i = rnd.randint(lo, hi)
        while i <= hi and not ctx.has_bar(i):
            i += 1
        if i > hi:
            continue
        px = float(ctx.c[i])
        inv = None if dist is None else (px - dist if side == "C" else px + dist)
        out.append(entries.Signal(f"random:{r['entry']}", ctx.sym, ctx.day, side, i, px, inv, {}))
    return out


class TradeWriter:
    def __init__(self, path):
        self.path = path
        self.buf = io.StringIO()
        self.w = csv.DictWriter(self.buf, fieldnames=TRADE_COLS, extrasaction="ignore", lineterminator="\n")
        self.w.writeheader()

    def add(self, run_id, t):
        row = dict(t, run_id=run_id)
        row["legs"] = ";".join(f"{x['qty']:g}@{x['basis']:.4f}@{x['idx']}:{x['reason']}" for x in t.get("legs") or [])
        for k in ("peak_level", "target_level"):
            if isinstance(row.get(k), dict):
                row[k] = json.dumps(row[k], sort_keys=True)
        self.w.writerow(row)

    def close(self):
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(self.path, "wt") as f:
                f.write(self.buf.getvalue())


def run_pass(runs, a, b, root=None, spread=None, progress=None, writer=None, limit_days=None, early_close=None):
    """Simulate every run over [a, b]. Returns ({run_id: {"trades", "skips", "signals"}}, {symbol: [sessions]})."""
    res = {r["run_id"]: {"trades": [], "skips": Counter(), "signals": 0} for r in runs}
    sessions = {}
    syms = sorted({s for r in runs for s in r["symbols"]})
    aux = {}
    used = {f for r in runs for f in (r.get("filters") or ())}
    if used & {"vixy_pctl_le40", "vixy_pctl_ge60"}:
        aux["VIXY_D"] = data.read_daily("VIXY", root)              # split-adjusted daily closes (proxy: VIXY percentile)
        if progress:
            n = None if aux["VIXY_D"] is None else len(aux["VIXY_D"])
            progress(f"  VIX percentile proxy: VIXY daily {'MISSING (percentile filters skip every signal)' if n is None else str(n) + ' closes'}")
    if used & {"vixy_falling", "vixy_not_rising", "vixy_rising_1pct"}:
        vdf = data.read_stock("VIXY", a, b, root)                 # the labeled VIX proxy (stock bars only)
        aux["VIXY"] = data.Series("VIXY", vdf) if vdf is not None else None
        if progress:
            progress(f"  VIX proxy: VIXY {'loaded, ' + str(len(aux['VIXY'].days)) + ' sessions' if aux['VIXY'] else 'MISSING (vixy_falling skips every signal)'}")
    t0 = time.time()
    for sym in syms:
        rs = [r for r in runs if sym in r["symbols"]]
        df = data.read_stock(sym, a, b, root)
        series = data.Series(sym, df)
        odays = data.option_days(sym, root)
        days = [d for d in series.days if a <= d <= b]
        if limit_days:
            days = days[:limit_days]
        sessions[sym] = [d.isoformat() for d in days]
        for n, day in enumerate(days):
            tapes = data.read_option_day(sym, day, root) if day in odays else {}
            ctx = data.DayContext(series, day, tapes, spread, early_close=None if early_close is None else day.isoformat() in early_close,
                                  aux=aux)
            sig_cache, pick_cache = {}, {}
            for r in rs:
                rid = r["run_id"]
                if r.get("random"):
                    sigs = _random_signals(r, ctx)
                else:
                    key = (r["entry"], r["side"])
                    if key not in sig_cache:
                        sig_cache[key] = entries.signals(ctx, r["entry"], r["side"])
                    sigs = sig_cache[key]
                if not sigs:
                    continue
                levels = ctx.levels(r.get("fake_seed"))
                last_exit, count = -1, 0
                for sig in sorted(sigs, key=lambda s: s.idx):
                    res[rid]["signals"] += 1
                    if sig.idx < last_exit:
                        res[rid]["skips"]["busy: one position at a time"] += 1
                        continue
                    why = _filters_ok(r, ctx, sig, count)
                    if why:
                        res[rid]["skips"][why] += 1
                        continue
                    if not tapes:
                        res[rid]["skips"]["no 0DTE option data for the day"] += 1
                        continue
                    pk = (sig.key, r["exit"].contract)
                    if pk not in pick_cache:
                        pick_cache[pk] = contracts.pick(ctx, sig.side, sig.idx, r["exit"].contract)
                    tape, info = pick_cache[pk]
                    if tape is None:
                        res[rid]["skips"][info] += 1
                        continue
                    out = simulate(ctx, sig, r["exit"], levels, tape, info)
                    if out["status"] != "TRADE":
                        res[rid]["skips"][_skip_key(out["reason"])] += 1
                        continue
                    last_exit = out["exit_idx"]
                    count += 1
                    if writer is not None and not r.get("random") and r.get("fake_seed") is None and not r.get("nudge"):
                        writer.add(rid, out)
                    res[rid]["trades"].append({k: out.get(k) for k in LEAN})
            if progress and (n % 50 == 0 or n == len(days) - 1):
                progress(f"  {sym} {day} ({n + 1}/{len(days)} sessions, {time.time() - t0:.0f}s)")
    return res, sessions


def _skip_key(reason):
    r = str(reason)
    for k in ("R:R below", "level stop does not fit", "no option print", "VOID", "no target level", "level stop is not beyond",
              "no new trades after", "signal after the all-out"):
        if r.startswith(k):
            return k
    return r[:60]


# ---------------------------------------------------------------- robustness job builders
NUDGE_STEPS = {
    "entry": ["orb15", "orb30", "orb60"],
    "tp_buffer": ["$0.03", "0.05%", "0.1atr"],
    "rr_min": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
    "be": ["be6", "be8", "be10", "be15"],
    "gb": ["gb20", "gb30", "gb40", "gb50", "gb60"],
    "hl": ["hl1m", "hl5m"],
    "allout": ["15:25", "15:50"],
    "fixed_stop": [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60],
    "fixed_target": [0.20, 0.30, 0.40, 0.45, 0.60, 0.75, 0.90, 1.00, 1.25],
}


def _neighbors(lst, v):
    if v not in lst:
        return []
    i = lst.index(v)
    return [lst[j] for j in (i - 1, i + 1) if 0 <= j < len(lst)]


def nudges(r):
    """One-step neighbors of a run (each numeric parameter moved one step, one at a time)."""
    out = []
    x = r["exit"]
    for e in _neighbors(NUDGE_STEPS["entry"], r["entry"]):
        out.append(("entry", e, dict(r, entry=e)))
    if x.tp in ("B", "C", "D", "E") or x.trail == "belevel":
        for v in _neighbors(NUDGE_STEPS["tp_buffer"], x.tp_buffer):
            out.append(("tp_buffer", v, dict(r, exit=replace(x, tp_buffer=v))))
    if x.rr_min:
        for v in _neighbors(NUDGE_STEPS["rr_min"], float(x.rr_min)):
            out.append(("rr_min", v, dict(r, exit=replace(x, rr_min=v))))
    for fam in ("be", "gb", "hl"):
        for v in _neighbors(NUDGE_STEPS[fam], x.trail):
            out.append(("trail", v, dict(r, exit=replace(x, trail=v))))
    for v in _neighbors(NUDGE_STEPS["allout"], x.allout):
        out.append(("allout", v, dict(r, exit=replace(x, allout=v))))
    if x.stop == "fixed":
        for k in ("fixed_stop", "fixed_target"):
            for v in _neighbors(NUDGE_STEPS[k], round(float(getattr(x, k)), 2)):
                out.append((k, v, dict(r, exit=replace(x, **{k: v}))))
    return out


def uses_levels(r):
    x = r["exit"]
    return x.tp in ("B", "C", "D", "E") or x.trail in ("lvl", "belevel") or bool(x.rr_min)


def random_job(r, trades, path, seed=101):
    lo, hi = entries.ENTRY_WINDOWS.get(r["entry"], (15, 344))
    matched = defaultdict(list)
    for t in trades:
        dist = abs(float(t["signal_price"]) - float(t["invalid"])) if t.get("invalid") is not None else None
        matched[f"{t['symbol']}|{t['day']}"].append((t["side"], dist, lo, hi))
    return dict(r, run_id=f"{r['run_id']}~rnd{path}", random={"seed": seed + path, "matched": dict(matched)},
                random_tag=f"{seed + path}", exit=replace(r["exit"]), random_of=r["run_id"])
