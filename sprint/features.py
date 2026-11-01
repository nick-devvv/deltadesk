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
Round 8, B1 (SPRINT_PLAN Amendment 10, pre-registered 2026-11-01 before any round-8 run), appended at the END of FEATURES so
every earlier column keeps its position; each is known at the end of the decision bar j:
  f_ret5d          side-signed % return over the 5 sessions to the prior close: prior close / the close 5 sessions before it - 1
  f_dd20           prior close vs the highest close of the 20 prior sessions (the prior session included), in % (<= 0)
  f_vixy_chg1      VIXY's prior-session close / the VIXY close before it - 1, in % (VIXY split-adjusted daily file)
  f_vixy_z20       VIXY's prior-session close, z vs the 20 VIXY closes before it (their mean and sample sd, ddof 1)
  f_or30_atr       the 09:30-10:00 range (bars 0..29, high minus low) / daily ATR(14); empty before the bar finishing 10:00
  f_gap_abs        |gap| in %: |today's open / prior close - 1| x 100
  f_hod            1 if the decision bar's close is at or above every earlier high of the session (bars 0..j-1), else 0
A feature without enough history is empty, never estimated. `restamp` fills only these seven on trade rows written
before they existed (run 7's factory files), from cached bars, without touching anything else on the row.
Note: sprint/learn.py's default feature list is FEATURES, so a learner now also reads the seven new columns when a trade file
has them; on older trade files they are empty and learn._prep_fit drops all-empty columns, so older results are unchanged.
"""
import math

import numpy as np

FEATURES18 = ["f_minute", "f_weekday", "f_adx", "f_er30", "f_vwap_x60", "f_overlap30", "f_range_atr", "f_rvol", "f_trend_votes",
              "f_di", "f_noise_true", "f_gap", "f_day_ret", "f_vwap_dist", "f_prev_range", "f_prev_ret", "f_event", "f_vixy_pctl"]
NEW7 = ["f_ret5d", "f_dd20", "f_vixy_chg1", "f_vixy_z20", "f_or30_atr", "f_gap_abs", "f_hod"]      # round 8, B1
FEATURES = FEATURES18 + NEW7


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
    out.update(new_features(ctx, j, side))
    return out


# ---------------------------------------------------------------- round 8, B1
_VX = {}


def _vix_arrays(vd):
    """(position by date, closes array) of a VIXY daily close series (cached per object; the cache holds the object so
    its id is never reused while cached)."""
    hit = _VX.get(id(vd))
    if hit is not None and hit[0] is vd:
        return hit[1], hit[2]
    pos = {d: k for k, d in enumerate(vd.index)}
    vals = vd.to_numpy(float)
    _VX[id(vd)] = (vd, pos, vals)
    return pos, vals


def vixy_prior(vd, prior_day, n=20):
    """(close on prior_day, % change vs the close before it, z vs the n closes before it: mean and sample sd) from VIXY's
    daily closes; None for any value without enough history. Nothing after prior_day is read."""
    if vd is None or prior_day is None:
        return None, None, None
    pos, vals = _vix_arrays(vd)
    k = pos.get(prior_day)
    if k is None:
        return None, None, None
    x = float(vals[k])
    chg = (x / vals[k - 1] - 1) * 100 if k >= 1 and vals[k - 1] > 0 else None
    z = None
    if k >= n:
        w = vals[k - n:k]
        sd = float(np.std(w, ddof=1))
        z = (x - float(np.mean(w))) / sd if sd > 0 else None
    return x, chg, z


def day_pos(series):
    """{day: position in series.days} (cached on the series)."""
    pos = series.__dict__.get("_dpos")
    if pos is None or len(pos) != len(series.days):
        pos = {d: k for k, d in enumerate(series.days)}
        series.__dict__["_dpos"] = pos
    return pos


def _datr(series, day):
    cache = series.__dict__.setdefault("_datr_cache", {})
    if day not in cache:
        cache[day] = series.daily_atr(day)
    return cache[day]


def new_features(ctx, j, side):
    """The seven round-8 features at the end of decision bar j (SPRINT_PLAN Amendment 10, B1)."""
    sg = 1.0 if side == "C" else -1.0
    s, d = ctx.series, ctx.day
    out = dict.fromkeys(NEW7)
    k = day_pos(s).get(d)
    closes = s.daily["close"].to_numpy(float)[max(0, k - 20):k] if k else np.array([])
    if len(closes) >= 6:
        out["f_ret5d"] = _num(sg * (closes[-1] / closes[-6] - 1) * 100)
    if len(closes) >= 20:
        out["f_dd20"] = _num((closes[-1] / closes.max() - 1) * 100)
    prev_day = s.days[k - 1] if k else None
    vd = ctx.aux.get("VIXY_D") if ctx.aux else None
    if vd is not None and prev_day is not None:
        _x, chg, z = vixy_prior(vd, prev_day, 20)
        out["f_vixy_chg1"], out["f_vixy_z20"] = _num(chg), _num(z)
    if j >= 29:
        hi, lo = ctx.h[:30], ctx.l[:30]
        datr = _datr(s, d)
        if datr and not np.isnan(hi).all():
            out["f_or30_atr"] = _num((float(np.nanmax(hi)) - float(np.nanmin(lo))) / datr)
    o0 = float(ctx.o[0])
    if len(closes) and not math.isnan(o0):
        out["f_gap_abs"] = _num(abs(o0 / closes[-1] - 1) * 100)
    cj = float(ctx.c[j]) if 0 <= j < len(ctx.c) else math.nan
    if not math.isnan(cj):
        earlier = ctx.h[:j]
        out["f_hod"] = 1 if (j == 0 or np.isnan(earlier).all() or cj >= float(np.nanmax(earlier))) else 0
    return out


def missing(r, names):
    for k in names:
        v = r.get(k)
        if v is None or v == "" or (isinstance(v, float) and math.isnan(v)):
            return True
    return False


def restamp(rows, series=None, aux=None, root=None, names=None):
    """Fill the seven round-8 features (or `names`, a subset of NEW7) on rows that lack them, from cached bars, at each
    trade's signal bar. series: {(src, symbol): data.Series} already loaded (src "HIST" or "DEV"); a missing one is loaded
    from `root` (HIST with its warm-up from periods.WARMUP, DEV from its first day). Nothing else on a row changes (trade
    P/L included). Returns the number of rows filled."""
    from datetime import date
    from . import data
    from .periods import DEV, HIST, WARMUP
    names = list(names or NEW7)
    need = [r for r in rows if missing(r, names)]
    if not need:
        return 0
    series = series if series is not None else {}
    if aux is None:
        aux = {"VIXY_D": data.read_daily("VIXY", root)}
    ctxs = {}
    n = 0
    for r in need:
        d = date.fromisoformat(str(r["day"])[:10])
        src = r.get("_src") or ("HIST" if d <= HIST[1] else "DEV")
        key = (src, r["symbol"])
        if key not in series:
            a, b = (WARMUP["HIST"], HIST[1]) if src == "HIST" else DEV
            series[key] = data.Series(r["symbol"], data.read_stock(r["symbol"], a, b, root))
        ser = series[key]
        if d not in ser.rth:
            continue
        ck = (key, d)
        if ck not in ctxs:
            ctxs[ck] = data.DayContext(ser, d, {}, None, aux=aux)
        f = new_features(ctxs[ck], int(float(r["signal_idx"])), r["side"])
        r.update({k: f[k] for k in names})
        n += 1
    return n


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


# ---------------------------------------------------------------- round 10, information-only regime features (Addendum 15.5)
# SPRINT_PLAN Addendum 15.5 (pre-registered 2026-11-01 before any round-10 code or run): stamped on every round 10 grid trade
# as INFORMATION ONLY (no pass/fail, no trials; a later rule built on them counts its own trials). They are NOT added to
# FEATURES, so no learner reads them by default. Each is known at the end of the decision bar j:
#   f_atr9_50    daily ATR(9) / ATR(50): Wilder ATRs of the daily regular-hours bars of the sessions BEFORE the day (true
#                range with the prior close), each over the last max(60, 3n) prior sessions, seeded with the mean of the first
#                n true ranges (n = 14 over 60 sessions is exactly data.Series.daily_atr); empty with fewer than 51 prior
#                sessions.
#   f_adx_d14    daily ADX(14) (indicators.adx_di, Wilder) over the last 100 prior sessions' daily bars; empty with fewer
#                than 29.
#   f_hurst100   a 100-bar rescaled-range (R/S) Hurst exponent on 1-minute closes: the last 100 regular-hours 1-minute
#                closes at or before bar j (missing minutes skipped; the prior sessions' last closes fill in before 11:09),
#                their 99 log returns, R/S averaged over non-overlapping windows of 8, 16, 32 and 64 returns (R = max - min
#                of the cumulative mean-adjusted sum, S = the window's population sd; flat windows skipped), H = the OLS
#                slope of log(mean R/S) on log(window). Empty with fewer than 100 closes.
#   f_opp_share  the share of opposite-color 1-minute bars since 09:30 (commenter MRPguy's "trend day"): bars 0..j with an
#                open and a close; "opposite" = red (close < open) for a call, green (close > open) for a put; a doji is
#                never opposite. Side-signed by construction (low = the bars agree with the trade).
REGIME10 = ["f_atr9_50", "f_adx_d14", "f_hurst100", "f_opp_share"]
HURST_BARS = 100
HURST_WINDOWS = (8, 16, 32, 64)
ADX_LOOK = 100


def daily_atr_n(series, day, n):
    """Wilder ATR(n) of the daily bars before `day` over the last max(60, 3n) prior sessions (cached), or None."""
    cache = series.__dict__.setdefault("_datr_n_cache", {})
    key = (day, n)
    if key in cache:
        return cache[key]
    out = None
    if day in series.rth:
        prior = series.prior_days(day, max(60, 3 * n))
        if len(prior) >= n + 1:
            from .data import _wilder
            d = series.daily.loc[prior]
            pc = d["close"].shift()
            tr = np.maximum(d["high"] - d["low"], np.maximum((d["high"] - pc).abs(), (d["low"] - pc).abs())).to_numpy(float)[1:]
            w = _wilder(tr, n)
            out = float(w[-1]) if len(w) and not math.isnan(w[-1]) else None
    cache[key] = out
    return out


def daily_adx(series, day, n=14, look=ADX_LOOK):
    """Daily ADX(n) (indicators.adx_di) over the last `look` sessions before `day` (cached), or None."""
    cache = series.__dict__.setdefault("_dadx_cache", {})
    key = (day, n, look)
    if key in cache:
        return cache[key]
    out = None
    if day in series.rth:
        prior = series.prior_days(day, look)
        if len(prior) >= 2 * n + 1:
            import pandas as pd
            import indicators as I
            d = series.daily.loc[prior]
            f = pd.DataFrame({"High": d["high"].to_numpy(float), "Low": d["low"].to_numpy(float), "Close": d["close"].to_numpy(float)})
            adx, _p, _m = I.adx_di(f, n)
            v = float(adx.iloc[-1]) if len(adx) else math.nan
            out = None if math.isnan(v) else v
    cache[key] = out
    return out


def hurst_rs(closes, windows=HURST_WINDOWS):
    """Rescaled-range Hurst exponent of a close series (see REGIME10), or None."""
    c = np.asarray(closes, float)
    if len(c) < 3 or np.isnan(c).any() or (c <= 0).any():
        return None
    x = np.diff(np.log(c))
    pts = []
    for n in windows:
        rs = []
        for q in range(len(x) // n):
            s = x[q * n:(q + 1) * n]
            sd = float(s.std())
            if sd <= 0:
                continue
            y = np.cumsum(s - s.mean())
            rs.append((float(y.max()) - float(y.min())) / sd)
        if rs and float(np.mean(rs)) > 0:
            pts.append((math.log(n), math.log(float(np.mean(rs)))))
    if len(pts) < 2:
        return None
    X = np.array([p[0] for p in pts])
    Y = np.array([p[1] for p in pts])
    Xc = X - X.mean()
    return float((Xc * (Y - Y.mean())).sum() / (Xc * Xc).sum())


def last_closes(ctx, j, n=HURST_BARS):
    """The last n regular-hours 1-minute closes at or before bar j (prior sessions fill in), or None."""
    today = np.asarray(ctx.c[:j + 1], float)
    parts = [today[~np.isnan(today)]]
    have = len(parts[0])
    if have < n:
        for d in reversed(ctx.series.prior_days(ctx.day, 3)):
            g = ctx.series.rth[d][:, 3]
            g = g[~np.isnan(g)]
            take = g[-(n - have):]
            parts.insert(0, take)
            have += len(take)
            if have >= n:
                break
    if have < n:
        return None
    return np.concatenate(parts)[-n:]


def regime_features(ctx, j, side):
    """The four information-only regime features of round 10 at the end of decision bar j (REGIME10)."""
    s, d = ctx.series, ctx.day
    out = dict.fromkeys(REGIME10)
    a9, a50 = daily_atr_n(s, d, 9), daily_atr_n(s, d, 50)
    if a9 is not None and a50:
        out["f_atr9_50"] = _num(a9 / a50)
    out["f_adx_d14"] = _num(daily_adx(s, d))
    lc = last_closes(ctx, j)
    if lc is not None:
        out["f_hurst100"] = _num(hurst_rs(lc))
    o, c = np.asarray(ctx.o[:j + 1], float), np.asarray(ctx.c[:j + 1], float)
    ok = ~(np.isnan(o) | np.isnan(c))
    if ok.any():
        opp = (c[ok] < o[ok]) if side == "C" else (c[ok] > o[ok])
        out["f_opp_share"] = _num(float(opp.sum()) / int(ok.sum()))
    return out
