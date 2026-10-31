"""sprint/report.py - metrics and robustness for sprint runs (docs/research/SPRINT_PLAN.md, "Robustness", "Logging").

Per run (all dollars per 1-contract unit, after spread and $0.65/contract/side; BACKTEST, DEV, MODELED-SPREAD unless
the run log says MEASURED-SPREAD):
  trades, win rate (pnl > 0), average win, average loss, expectancy, profit factor, PF at 2x slippage (k = 2, and 4
  half-spreads on stop exits), max drawdown (worst peak-to-trough of cumulative P/L in time order, negative), % of
  peak profit kept (over trades whose peak open profit after costs was > 0: total realized P/L / total peak open
  profit; the per-trade median is reported too), planned vs actual R:R (mean planned option R:R where a target
  existed; mean realized P/L / planned risk).
Robustness (SPRINT_PLAN's list):
  by stretch           Aug-Dec 2024, 2025, Jan-Jun 2026, each on its own
  without best 5       total and expectancy after removing the 5 best trades
  one-step nudges      each numeric parameter moved one step (engine re-runs them); min PF across nudges
  both sides           calls and puts separately
  matched random       same days, same side count, same exits, random entry minute in the setup's window, same stock
                       stop distance; paths x expectancy; share of paths the run beats
  random day-skips     a filtered run vs its unfiltered twin with the same number of random days removed
  real vs made-up      the same run on made-up levels (20 seeds); share of seeds the real levels beat
  bootstrap CI         day-block bootstrap (resample sessions with replacement, sessions without trades included)
                       of expectancy per trade, 95%
  deflated Sharpe      Bailey & Lopez de Prado (2014) on daily P/L (zero on sessions without a trade) with the run
                       count from the run log as the number of trials and the variance of the trial Sharpes
"""
import math
import random
import statistics
from collections import Counter, defaultdict
from datetime import date

from .periods import STRETCHES

COLUMNS = ["run_id", "timestamp", "tool", "period_tag", "symbol", "setup", "side", "stop_rule", "tp_rule", "trail",
           "time_rule", "trend_rule", "filters", "contract_rule", "slippage", "trades", "win_rate", "avg_win", "avg_loss",
           "expectancy", "profit_factor", "pf_2x_slip", "max_dd", "pct_peak_kept", "planned_rr", "actual_rr", "notes"]
EULER = 0.5772156649


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(x, n)


def metrics(trades, key="pnl"):
    p = [float(t[key]) for t in trades]
    n = len(p)
    if not n:
        return {"trades": 0}
    wins, losses = [x for x in p if x > 0], [x for x in p if x < 0]
    eq = peak = dd = 0.0
    for x in p:
        eq += x
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    gl = -sum(losses)
    return {"trades": n, "net": _r(sum(p)), "win_rate": _r(len(wins) / n, 3), "avg_win": _r(statistics.mean(wins)) if wins else None,
            "avg_loss": _r(statistics.mean(losses)) if losses else None, "expectancy": _r(sum(p) / n),
            "profit_factor": _r(sum(wins) / gl, 3) if gl > 0 else (None if not wins else float("inf")),
            "max_dd": _r(dd)}


def ordered(trades):
    return sorted(trades, key=lambda t: (t["day"], t.get("entry_idx", 0), t["symbol"]))


def summarize(trades, a=None, b=None):
    tr = ordered(trades)
    m = metrics(tr)
    if not tr:
        return m
    m["pf_2x_slip"] = metrics(tr, "pnl_2x")["profit_factor"]
    m["expectancy_2x"] = metrics(tr, "pnl_2x")["expectancy"]
    pk = [(float(t["pnl"]), float(t["peak_profit"])) for t in tr if t.get("peak_profit") is not None and float(t["peak_profit"]) > 0]
    m["pct_peak_kept"] = _r(sum(x for x, _ in pk) / sum(y for _, y in pk), 3) if pk else None
    kept = [t["pct_peak_kept"] for t in tr if t.get("pct_peak_kept") is not None]
    m["pct_peak_kept_median"] = _r(statistics.median(kept), 3) if kept else None
    prr = [t["planned_rr_opt"] for t in tr if t.get("planned_rr_opt") is not None]
    arr = [t["actual_rr"] for t in tr if t.get("actual_rr") is not None]
    m["planned_rr"] = _r(statistics.mean(prr), 2) if prr else None
    m["actual_rr"] = _r(statistics.mean(arr), 2) if arr else None
    m["sides"] = {s: metrics([t for t in tr if t["side"] == s]) for s in ("C", "P")}
    m["symbols"] = {s: metrics([t for t in tr if t["symbol"] == s]) for s in sorted({t["symbol"] for t in tr})}
    m["exit_reasons"] = dict(Counter(_reason(t["exit_reason"]) for t in tr).most_common())
    m["stretches"] = by_stretch(tr, a, b)
    m["blocks_2m"] = two_month_blocks(tr, a, b)
    m["without_best5"] = without_best(tr, 5)
    mfe = [t["opt_mfe_pct"] for t in tr]
    mae = [t["opt_mae_pct"] for t in tr]
    m["opt_mfe_median"], m["opt_mae_median"] = _r(statistics.median(mfe), 3), _r(statistics.median(mae), 3)
    sm = [t["stock_mfe"] for t in tr]
    m["stock_mfe_median"] = _r(statistics.median(sm), 3)
    d = [abs(t["peak_level"]["dist"]) for t in tr if t.get("peak_level")]
    m["peak_to_level_median"] = _r(statistics.median(d), 3) if d else None
    m["minutes_held_median"] = statistics.median([t["minutes_held"] for t in tr])
    return m


def _reason(s):
    s = str(s)
    for k in ("FIXED STOP", "FIXED TARGET", "CEILING STOP", "BREAKEVEN STOP", "LOCK STOP", "GIVEBACK STOP", "LEVEL STOP", "1M PIVOT TRAIL", "5M PIVOT TRAIL",
              "LEVEL TRAIL", "VWAP TRAIL", "EMA9 TRAIL", "NOISE STOP", "NOISE REVERSAL", "T1", "LEVEL TARGET", "LEVEL 1",
              "LEVEL 2", "LEVEL REJECTION", "IF FLAT", "ALL OUT"):
        if s.startswith(k):
            return k
    return s[:30]


def by_stretch(trades, a=None, b=None):
    """SPRINT_PLAN's stretches, clipped to the run's period [a, b] (a stretch outside the period is left out)."""
    out = {}
    for name, x, y in STRETCHES:
        if a is not None and (y < a or x > b):
            continue
        lo, hi = max(x, a) if a else x, min(y, b) if b else y
        sel = [t for t in trades if lo.isoformat() <= t["day"] <= hi.isoformat()]
        out[name if (lo, hi) == (x, y) else f"{name} ({lo:%b %d}-{hi:%b %d})"] = metrics(sel)
    return out


def two_month_blocks(trades, a=None, b=None):
    """Consecutive two-calendar-month blocks from the period's first month (Option Alpha's '3 of 4 blocks' test)."""
    if not trades and a is None:
        return {}
    days = sorted(t["day"] for t in trades)
    a = a or date.fromisoformat(days[0])
    b = b or date.fromisoformat(days[-1])
    out, y, m = {}, a.year, a.month
    while date(y, m, 1) <= b:
        y2, m2 = (y + (m + 1 > 12), (m + 1 - 1) % 12 + 1)
        end_y, end_m = (y2 + (m2 + 1 > 12), (m2 + 1 - 1) % 12 + 1)
        lo, hi = date(y, m, 1).isoformat(), date(end_y, end_m, 1).isoformat()
        out[f"{date(y, m, 1):%b %Y}-{date(y2, m2, 1):%b %Y}"] = metrics([t for t in trades if lo <= t["day"] < hi])
        y, m = end_y, end_m
    return out


def without_best(trades, k=5):
    p = sorted((float(t["pnl"]) for t in trades), reverse=True)[k:]
    return {"net": _r(sum(p)), "expectancy": _r(sum(p) / len(p)) if p else None, "trades": len(p)}


def daily_pnl(trades, sessions):
    by = defaultdict(float)
    for t in trades:
        by[t["day"]] += float(t["pnl"])
    return [by.get(d, 0.0) for d in sorted(sessions)]


def bootstrap_ci(trades, sessions, boots=2000, seed=7):
    """95% day-block bootstrap of expectancy per trade (sessions without trades are part of the resample)."""
    by = defaultdict(list)
    for t in trades:
        by[t["day"]].append(float(t["pnl"]))
    days = sorted(set(sessions) | set(by))
    if not trades or not days:
        return None
    rnd = random.Random(seed)
    sims = []
    for _ in range(boots):
        tot = n = 0
        for _d in days:
            x = by.get(days[rnd.randrange(len(days))])
            if x:
                tot += sum(x)
                n += len(x)
        sims.append(tot / n if n else 0.0)
    sims.sort()
    return [_r(sims[int(0.025 * boots)]), _r(sims[int(0.975 * boots) - 1])]


def sharpe(series):
    if len(series) < 3:
        return None
    sd = statistics.pstdev(series)
    return None if sd == 0 else statistics.mean(series) / sd


def deflated_sharpe(series, n_trials, sr_var):
    """Probability that the true Sharpe exceeds the best expected under N trials (per-session units)."""
    sr = sharpe(series)
    T = len(series)
    if sr is None or T < 10:
        return None
    mu = statistics.mean(series)
    sd = statistics.pstdev(series)
    g3 = sum((x - mu) ** 3 for x in series) / T / sd ** 3
    g4 = sum((x - mu) ** 4 for x in series) / T / sd ** 4
    nd = statistics.NormalDist()
    n = max(int(n_trials or 1), 1)
    sr0 = 0.0
    if n > 1 and sr_var and sr_var > 0:
        sr0 = math.sqrt(sr_var) * ((1 - EULER) * nd.inv_cdf(1 - 1 / n) + EULER * nd.inv_cdf(1 - 1 / (n * math.e)))
    den = 1 - g3 * sr + (g4 - 1) / 4 * sr * sr
    if den <= 0:
        return None
    return _r(nd.cdf((sr - sr0) * math.sqrt(T - 1) / math.sqrt(den)), 4)


def random_skip_test(filtered, unfiltered, paths=500, seed=11):
    """Share of random day-skip subsets of the unfiltered twin whose expectancy is >= the filtered run's.
    The number of days removed = unfiltered trading days - filtered trading days."""
    if not filtered or not unfiltered:
        return None
    fe = sum(t["pnl"] for t in filtered) / len(filtered)
    days = sorted({t["day"] for t in unfiltered})
    k = len(days) - len({t["day"] for t in filtered})
    if k <= 0:
        return {"skipped_days": 0, "p_value": None, "filtered_exp": _r(fe)}
    rnd = random.Random(seed)
    ge = 0
    exps = []
    for _ in range(paths):
        drop = set(rnd.sample(days, k))
        sel = [t["pnl"] for t in unfiltered if t["day"] not in drop]
        e = sum(sel) / len(sel) if sel else 0.0
        exps.append(e)
        ge += e >= fe
    return {"skipped_days": k, "p_value": _r(ge / paths, 3), "filtered_exp": _r(fe), "random_skip_exp_mean": _r(statistics.mean(exps))}


def beat_share(value, others):
    if value is None or not others:
        return None
    return _r(sum(1 for x in others if value > x) / len(others), 3)


# ---------------------------------------------------------------- run log row
def describe(run):
    x = run["exit"]
    if x.stop == "fixed":
        mech = ("desk fills: inside the bar, same-bar -> stop" if x.mechanics == "desk" else
                "OA-LIKE: checked once a minute on the close (mid proxy), filled at the next minute's print")
        tp = f"fixed +{x.fixed_target:.0%} of debit"
        time = f"none (no tightening, no breakeven, no if-flat); all out {x.allout}"
        return f"fixed -{x.fixed_stop:.0%} of debit; {mech}", tp, time, "none"
    stop = {"premium": "premium ceiling by time table (costs incl.)",
            "level": "setup level -/+ max($0.02,0.05ATR1m) on 1m close; skip if > ceiling; ceiling stays as premium stop",
            "noise": "noise checks max/min(band,VWAP) + reversal" + ("" if run["entry"].endswith("nocap") else " + 20% ceiling every minute")}[x.stop]
    tp = {"none": "none", "A": "A fixed T1 by time table", "B": f"B first level, buffer {x.tp_buffer}",
          "C": f"C half at first level (buffer {x.tp_buffer}), trail rest", "D": f"D: A, C on trend/RVOL1.5 days (buffer {x.tp_buffer})",
          "E": f"E first level, exit on rejection else next level (buffer {x.tp_buffer})"}[x.tp]
    if x.rr_min:
        tp += f"; R:R >= {x.rr_min:g} (stock and option)"
    time = {"a": "(a) table as is", "b": "(b) no time tightening", "c": "(c) time tightens ceiling + if-flat only",
            "d": "(d) = c, off on trend days"}[x.time] + f"; all out {x.allout}"
    trend = "D: trend_aligned or RVOL>=1.5 -> C" if x.tp == "D" else ("time off on trend days" if x.time == "d" else
            ("trail only on trend days" if x.trail in ("vwap", "ema9") else "none"))
    return stop, tp, time, trend


def csv_row(run, s, ts, period_tag, spread_label, notes=""):
    stop, tp, time, trend = describe(run)
    return {"run_id": run["run_id"], "timestamp": ts, "tool": "DeskEngine", "period_tag": period_tag,
            "symbol": "+".join(run["symbols"]), "setup": run["entry"], "side": run["side"], "stop_rule": stop, "tp_rule": tp,
            "trail": run["exit"].trail, "time_rule": time, "trend_rule": trend, "filters": "+".join(run.get("filters") or []) or "none",
            "contract_rule": run["exit"].contract + " (BS-EST delta)",
            "slippage": f"k=1 x half-spread ({spread_label}); 2x: k=2, stops 4", "trades": s.get("trades", 0),
            "win_rate": s.get("win_rate"), "avg_win": s.get("avg_win"), "avg_loss": s.get("avg_loss"), "expectancy": s.get("expectancy"),
            "profit_factor": s.get("profit_factor"), "pf_2x_slip": s.get("pf_2x_slip"), "max_dd": s.get("max_dd"),
            "pct_peak_kept": s.get("pct_peak_kept"), "planned_rr": s.get("planned_rr"), "actual_rr": s.get("actual_rr"), "notes": notes}


# ---------------------------------------------------------------- pass/fail against SPRINT_PLAN's robustness list
def checklist(s, rob):
    st = s.get("stretches") or {}
    bl = [v for v in (s.get("blocks_2m") or {}).values() if v.get("trades")]
    items = [("at least 60 trades", s.get("trades", 0) >= 60),
             ("PF >= 1.25", (s.get("profit_factor") or 0) >= 1.25),
             ("PF > 1.0 at 2x slippage", (s.get("pf_2x_slip") or 0) > 1.0),
             ("profitable in each stretch", all((v.get("net") or 0) > 0 for v in st.values()) if st else False),
             ("positive without best 5", ((s.get("without_best5") or {}).get("net") or 0) > 0),
             ("both sides profitable (sides traded)", all((v.get("net") or 0) > 0 for v in (s.get("sides") or {}).values() if v.get("trades"))),
             (f"profitable two-month blocks: {sum(1 for v in bl if (v.get('net') or 0) > 0)} of {len(bl)} (info)", True)]
    if rob.get("nudge_min_pf") is not None:
        items.append(("every one-step nudge keeps PF > 1.1", rob["nudge_min_pf"] > 1.1))
    if rob.get("random_beat") is not None:
        items.append(("beats matched random entries", rob["random_beat"] >= 0.95))
    if rob.get("skip_p") is not None:
        items.append(("filter beats random day-skips", rob["skip_p"] <= 0.05))
    if rob.get("fake_beat") is not None:
        items.append(("real levels beat made-up levels", rob["fake_beat"] >= 0.95))
    return items


def fmt(x, n=2):
    if x is None:
        return "-"
    if isinstance(x, float):
        if math.isinf(x):
            return "inf"
        return f"{x:.{n}f}"
    return str(x)


def table(rows, cols):
    head = "| " + " | ".join(c for c, _ in cols) + " |\n|" + "---|" * len(cols) + "\n"
    return head + "".join("| " + " | ".join(fmt(f(r)) if not isinstance(f(r), str) else f(r) for _, f in cols) + " |\n" for r in rows)
