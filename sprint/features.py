"""sprint/features.py - the conditions at entry, stamped on every sprint trade (pre-registered 2026-10-31, sprint run 3).

Every value is known at the END of the decision bar j (the signal bar), from that session's finished bars and earlier
sessions only, so the learner (sprint/learn.py) can use them without look-ahead. "side-signed" values are multiplied
by +1 for calls and -1 for puts, so a positive number always means "in the trade's direction".

  f_minute         minutes since 09:30 at the decision bar's end (j + 1)
  f_weekday        0 = Monday ... 4 = Friday
  f_adx, f_er30, f_vwap_x60, f_overlap30, f_range_atr, f_rvol, f_trend_votes   sprint/daytype.py features at j
  f_di             side-signed (+DI - -DI), 14-period on 5-minute bars
  f_noise_true     how many noise_trend conditions are true (0-4; unknown ones count as not true)
  f_gap            side-signed open vs prior close, in %
  f_day_ret        side-signed close at j vs the open, in %
  f_vwap_dist      side-signed (close at j - VWAP) / daily ATR
  f_prev_range     prior session's high - low / daily ATR
  f_prev_ret       side-signed prior session's close vs the close before it, in % (added before run 3, after Chart's
                   in-sample look at v2-034 found "prior day up > 0.3%" days losing; the learner tests it walk-forward)
  f_event          1 on an FOMC statement or CPI release day, 0 otherwise, empty if the calendar doesn't cover the date
  f_vixy_pctl      VIX proxy: VIXY's percentile among 252 daily closes up to the prior session (empty when not loaded)
"""
import math

import numpy as np

FEATURES = ["f_minute", "f_weekday", "f_adx", "f_er30", "f_vwap_x60", "f_overlap30", "f_range_atr", "f_rvol", "f_trend_votes",
            "f_di", "f_noise_true", "f_gap", "f_day_ret", "f_vwap_dist", "f_prev_range", "f_prev_ret", "f_event", "f_vixy_pctl"]


def _num(x, nd=4):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else round(x, nd)


def entry_features(ctx, j, side):
    sg = 1.0 if side == "C" else -1.0
    dt = ctx.daytype()
    f = dt.features(j)
    prev = ctx.series.prev_day(ctx.day)
    datr = dt.datr or None
    o0, cj, vw = float(ctx.o[0]), float(ctx.c[j]), float(ctx.vwap[j])
    pdi, mdi = f.get("pdi"), f.get("mdi")
    out = {"f_minute": j + 1, "f_weekday": ctx.day.weekday(), "f_adx": _num(f.get("adx")), "f_er30": _num(f.get("er30")),
           "f_vwap_x60": _num(f.get("vwap_x60")), "f_overlap30": _num(f.get("overlap30")), "f_range_atr": _num(f.get("range_atr")),
           "f_rvol": _num(f.get("rvol")), "f_trend_votes": f.get("trend_votes"),
           "f_di": _num(sg * (pdi - mdi)) if pdi is not None and mdi is not None else None,
           "f_noise_true": (f.get("noise_trend") or {}).get("true"),
           "f_gap": _num(sg * (o0 / prev["close"] - 1) * 100) if prev and not math.isnan(o0) else None,
           "f_day_ret": _num(sg * (cj / o0 - 1) * 100) if not (math.isnan(o0) or math.isnan(cj)) else None,
           "f_vwap_dist": _num(sg * (cj - vw) / datr) if datr and not (math.isnan(cj) or math.isnan(vw)) else None,
           "f_prev_range": _num((prev["high"] - prev["low"]) / datr) if prev and datr else None,
           "f_prev_ret": None, "f_event": None, "f_vixy_pctl": None}
    pp = ctx.series.prev_day(prev["day"]) if prev else None
    if pp and pp.get("close"):
        out["f_prev_ret"] = _num(sg * (prev["close"] / pp["close"] - 1) * 100)
    from . import events
    fo, cp = events.is_fomc(ctx.day), events.is_cpi(ctx.day)
    if fo is not None and cp is not None:
        out["f_event"] = int(bool(fo or cp))
    vd = ctx.aux.get("VIXY_D") if ctx.aux else None
    if vd is not None and prev:
        from . import data
        out["f_vixy_pctl"] = _num(data.percentile_rank(vd, prev["day"]))
    return out


def matrix(rows, names=None):
    """rows (list of dicts / DataFrame records) -> float matrix with NaN for missing values."""
    names = names or FEATURES
    return np.array([[np.nan if r.get(k) in (None, "") else float(r.get(k)) for k in names] for r in rows], float)


def recompute(rows, root=None):
    """Fill the f_* features for trades from files written before features were stamped (sprint run 1/2), from the
    cached bars: the same DayContext the engine builds, at each trade's signal bar. Rows are updated in place."""
    from datetime import date
    from . import data
    need = [r for r in rows if r.get("f_minute") in (None, "") or (isinstance(r.get("f_minute"), float) and math.isnan(r["f_minute"]))]
    if not need:
        return rows
    aux = {"VIXY_D": data.read_daily("VIXY", root)}
    by_sym = {}
    for r in need:
        by_sym.setdefault(r["symbol"], []).append(r)
    for sym, rs in by_sym.items():
        days = sorted({date.fromisoformat(str(r["day"])) for r in rs})
        from .periods import DEV
        start = DEV[0] if days[0] >= DEV[0] else date(days[0].year, days[0].month, 1)   # the engine's own history start
        df = data.read_stock(sym, start, days[-1], root)
        series = data.Series(sym, df)
        ctxs = {}
        for r in rs:
            d = date.fromisoformat(str(r["day"]))
            if d not in series.rth:
                continue
            if d not in ctxs:
                ctxs[d] = data.DayContext(series, d, {}, None, aux=aux)
            r.update(entry_features(ctxs[d], int(r["signal_idx"]), r["side"]))
    return rows
