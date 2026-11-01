"""sprint/weekly.py - round 9 Part I: FIN-H on the weekly expiry (SPRINT_PLAN Amendment 12, pre-registered 2026-11-01 before
any round-9 code, pull or run). Research only: cached bars only, no network, no orders. DEV REAL only.

Rule `w5-10d03-12t07` (sprint/contracts.py): the nearest listed expiry 5-10 calendar days after the session, BS-EST |delta|
0.03-0.12 nearest 0.07, calls. FIN-H's entry and exit (i), unchanged:
  * entry: time_1100 (the bar finishing 11:00, index 89; none when that bar is missing or within 2 bars of the close), calls,
    SPY + QQQ + IWM, taken only when the relative volume at that bar (daytype rvol, the value stamped as f_rvol) is at least
    1.06 (unknown rvol is not traded), as the engine's rvol_ge106 filter;
  * exit (i): fixed -95% stop, no target (+9900%, never reached), all out 15:25 (12:50 on early-close days), desk mechanics
    (sprint/optpass.fixed_exits = the engine's fixed stop: triggers inside the bar, same-bar stop wins, a stop fills at the
    worse of the trigger and the next real price); entry at the first option print in the 3 minutes after the signal bar;
  * costs: the pre-registered 2% MODELED-SPREAD ($0.005 floor; logged chains are never read) + $0.65 per contract per side;
    PF 2x = the desk's 2x slippage (k = 2 on every fill, 4 half-spreads on stop exits; sprint/fills.pnl).
Tapes: data/alpaca/options_w5/<SYM>/<day>/bars.csv.gz (tools/sprint_pull9.py: every call strike from the day's low to 12%
above its high, of the first listed expiry 5-10 calendar days out; prices dated that session only, so an expiry that falls
in L1 reads nothing from L1). The reader keeps only the nearest expiry in [day + 5, day + 10].
Reference: FIN-H's own 0DTE contract (d03-12t07) with the same entry and exit, computed in the same pass on the same days
(the 0DTE tapes runs 1-3 pulled).
Pass: Addendum 10.1's DEV bar (at least 40 trades, PF >= 1.25, PF 2x > 1.0). Readout "steadier than FIN-H" (10.1), on DEV
REAL against FIN-H 0DTE exit (i) on the same days (days both traded): more months green, a total without the best day above
FIN-H's, a smaller average loss. Literal reading: the pass is the DEV bar; "steadier" is the readout reported beside it.
"""
import math
from collections import Counter
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import contracts, data, fills, periods, round8
from . import spread as SP
from .optpass import entry_fill, fixed_exits
from .sim import ALLOUT, EARLY_ALLOUT, NO_NEW_AFTER

WEEKLY_RULE, FINH_RULE = "w5-10d03-12t07", "d03-12t07"
SIG_BAR, RVOL_MIN, STOP, NONE_TARGET = 89, 1.06, 0.95, None
DTE = (5, 10)
SYMBOLS = ("SPY", "QQQ", "IWM")
LABEL = "BACKTEST, DEV REAL (Alpaca option prices), 2% MODELED-SPREAD"


def read_weekly_day(under, day, root=None):
    """{symbol: OptionTape} of the nearest expiry 5-10 calendar days after `day` (empty when the day has no file)."""
    f = Path(root or data.ROOT) / "options_w5" / under / day.isoformat() / "bars.csv.gz"
    if not f.exists():
        return {}
    df = pd.read_csv(f, compression="gzip")
    if not len(df):
        return {}
    mi = data._minutes(df["ts"])
    keep = (mi >= 0) & (mi < data.N)
    df, mi = df[keep], mi[keep]
    syms = df["symbol"].to_numpy()
    metas = {s: data.parse_occ(s) for s in pd.unique(syms)}
    exps = sorted({m["expiry"] for m in metas.values() if m and DTE[0] <= (m["expiry"] - day).days <= DTE[1]})
    if not exps:
        return {}
    nearest = exps[0]
    vals = df[["o", "h", "l", "c", "v"]].to_numpy(float)
    out = {}
    for s, meta in metas.items():
        if not meta or meta["expiry"] != nearest:
            continue
        sel = syms == s
        grid = np.full((data.N, 5), np.nan)
        grid[mi[sel]] = vals[sel]
        out[s] = fills.OptionTape(s, meta["right"], meta["strike"], *(grid[:, k] for k in range(5)))
        out[s].expiry = meta["expiry"]
    return out


def finh_signal(ctx):
    """(True, rvol) when FIN-H's entry fires on ctx's day, else (False, the reason)."""
    if SIG_BAR >= ctx.close_idx - 2 or math.isnan(ctx.c[SIG_BAR]):
        return False, "no 11:00 bar"
    rv = ctx.daytype()._rvol(SIG_BAR)
    if rv is None:
        return False, "rvol unknown"
    if rv < RVOL_MIN:
        return False, "rvol below 1.06"
    return True, rv


def trade(ctx, rule, spread):
    """FIN-H's entry + exit (i) on `rule` for ctx's day: (row, None) or (None, reason). ctx.tapes / ctx.tapes_weekly set."""
    allout = EARLY_ALLOUT if ctx.early else ALLOUT["15:25"]
    if SIG_BAR + 1 >= min(NO_NEW_AFTER, allout):
        return None, "signal after the all-out time"
    tape, info = contracts.pick(ctx, "C", SIG_BAR, rule)
    if tape is None:
        return None, info
    f = entry_fill(ctx, SIG_BAR, tape, spread, allout)
    if f is None:
        return None, "no option print in the 3 minutes after the signal"
    e, b_in, hs_in, _C, debit, costs = f
    r = fixed_exits(tape, e, allout, debit, [(STOP, NONE_TARGET)])[0]
    if r is None:
        return None, "VOID: no option print to exit on before the close"
    x, basis, reason, is_stop = r
    hs = costs.hs(basis, x)
    legs = [(1.0, basis, hs, is_stop)]
    return {"symbol": ctx.sym, "day": ctx.day.isoformat(), "_src": "DEV", "rule": rule, "side": "C", "contract": info["symbol"],
            "strike": info["strike"], "expiry": info.get("expiry"), "delta_est": info["delta"], "signal_idx": SIG_BAR, "entry_idx": e,
            "exit_idx": x, "entry_time": _hm(e), "exit_time": _hm(x), "exit_reason": reason, "entry_basis": round(b_in, 4),
            "exit_basis": round(basis, 4), "debit": round((b_in + hs_in) * fills.MULT + fills.FEE, 2),
            "pnl": round(fills.pnl(b_in, hs_in, legs, 1), 2), "pnl_2x": round(fills.pnl(b_in, hs_in, legs, 2), 2),
            "label": "REAL (Alpaca option prices)"}, None


def _hm(i):
    m = 570 + int(i)
    return f"{m // 60:02d}:{m % 60:02d}"


def run(series_by_sym, a=periods.DEV[0], b=periods.DEV[1], root=None, progress=None):
    """Part I over DEV: ({"weekly": rows, "finh_0dte": rows}, {"weekly": Counter of skips, ...}, coverage)."""
    if periods.overlaps(a, b):
        raise periods.LockedPeriod(f"REFUSED: Part I range {a}..{b} touches a locked period")
    spread = SP.SpreadModel()                                # the pre-registered 2% MODELED-SPREAD, never logged chains
    out = {"weekly": [], "finh_0dte": []}
    skips = {"weekly": Counter(), "finh_0dte": Counter(), "signal": Counter()}
    cover = {}
    for sym in sorted(series_by_sym):
        ser = series_by_sym[sym]
        days = [d for d in ser.days if a <= d <= b and not periods.overlaps(d, d)]
        wdays = {d for d in days if (Path(root or data.ROOT) / "options_w5" / sym / d.isoformat() / "bars.csv.gz").exists()}
        cover[sym] = {"sessions": len(days), "weekly_files": len(wdays)}
        for n, d in enumerate(days):
            ctx = data.DayContext(ser, d, {}, spread)
            ok, why = finh_signal(ctx)
            if not ok:
                skips["signal"][why] += 1
                continue
            ctx.tapes_weekly = read_weekly_day(sym, d, root) if d in wdays else {}
            ctx.tapes = data.read_option_day(sym, d, root)
            for key, rule in (("weekly", WEEKLY_RULE), ("finh_0dte", FINH_RULE)):
                row, why = trade(ctx, rule, spread)
                if row is None:
                    skips[key][why] += 1
                else:
                    out[key].append(row)
            if progress and (n % 100 == 0 or n == len(days) - 1):
                progress(f"  Part I {sym} {d} ({n + 1}/{len(days)} sessions)")
    return out, {k: dict(v) for k, v in skips.items()}, cover


def dev_bar(rows):
    s = round8.ostats(round8.in_win(rows, round8.DEV_A, round8.DEV_B))
    ch = [(f"DEV: at least 40 trades ({s['trades']})", s["trades"] >= 40),
          (f"DEV: PF >= 1.25 ({s.get('pf')})", round8._pfr(s.get("pf")) >= 1.25),
          (f"DEV: PF 2x > 1.0 ({s.get('pf_2x')})", round8._pfr(s.get("pf_2x")) > 1.0)]
    return {"dev": s, "checks": ch, "pass": all(ok for _, ok in ch)}


def steadier(rows, ref):
    """10.1's readout on the same days (days both traded)."""
    v, f = round8.same_days(round8.in_win(rows, round8.DEV_A, round8.DEV_B), round8.in_win(ref, round8.DEV_A, round8.DEV_B))
    sv, sf = round8.ostats(v), round8.ostats(f)
    ch = [(f"more months green than FIN-H 0DTE (i) on the same days ({sv.get('months_green')} vs {sf.get('months_green')})",
           (sv.get("months_green") or 0) > (sf.get("months_green") or 0)),
          (f"total without the best day above FIN-H's ({sv.get('without_best_day')} vs {sf.get('without_best_day')})",
           sv.get("without_best_day") is not None and sf.get("without_best_day") is not None and sv["without_best_day"] > sf["without_best_day"]),
          (f"smaller average loss ({sv.get('avg_loss')} vs {sf.get('avg_loss')})",
           sv.get("avg_loss") is not None and sf.get("avg_loss") is not None and abs(sv["avg_loss"]) < abs(sf["avg_loss"]))]
    return {"variant": sv, "fin_h": sf, "common_days": len({round8.day_of(r) for r in v}), "checks": ch, "steadier": all(ok for _, ok in ch)}


def part_i(res):
    bar = dev_bar(res["weekly"])
    st = steadier(res["weekly"], res["finh_0dte"])
    return {"rule": WEEKLY_RULE, "bar": bar, "steadier": st, "finh_0dte_dev": round8.ostats(res["finh_0dte"]), "pass": bar["pass"],
            "label": LABEL}


def expiry_window(day):
    """The calendar dates 5-10 days after `day` that are NYSE sessions, nearest first (the pull probes them in order)."""
    hol = periods.holidays()
    out = []
    for k in range(DTE[0], DTE[1] + 1):
        d = day + timedelta(days=k)
        if d.weekday() < 5 and d.isoformat() not in hol:
            out.append(d)
    return out
