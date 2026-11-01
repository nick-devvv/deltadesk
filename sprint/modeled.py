"""sprint/modeled.py - MODELED (BS, calibrated IV) 0DTE option tapes built from stock bars, for periods where Alpaca
has no option prices (HIST = 2016-01-04..2024-01-31, SPRINT_PLAN Amendment 5). Every number that comes from these
tapes is labeled "MODELED (BS, calibrated IV)". Research code only: no network, no orders.

IV proxy (known at the open, prior sessions only):
  sigma_1m  = realized volatility of regular-hours 1-minute log returns over the prior 20 sessions (at least 10
              needed): sqrt(sum of squared returns / minutes spanned). Each return is between consecutive bars of one
              session (no overnight return); a return over a missing minute counts the minutes between the bars.
              Early-close sessions use their bars before 13:00 only.
  IV proxy  = sigma_1m x sqrt(525,600): the engine's calendar-minute year (sprint/bs.t_years), so the proxy is on the
              same scale as the BS-EST implied vols the engine solves from real option prices.
Per (symbol, session, contract rule, side): IV = IV proxy x multiplier(rule, side). One IV for every strike, all day.

Modeled tapes (a generalization of tests/sprint_synth.option_bars):
  strikes   every $1 strike within +/- STRIKE_BAND (6%) of the underlying's close at the decision bar, built when
            the contract picker asks (so the strike set never depends on later bars)
  open      BS at the stock's open, minutes to the close at the bar's start
  close     BS at the stock's close, minutes to the close at the bar's end
  high/low  BS at the stock's high/low (calls; low/high for puts) at the bar's end, widened to include open and close
  rounding  to $0.01, with a $0.01 floor (a listed option never trades below one tick); no bar where the stock has none
  expiry    16:00, or 13:00 on early-close days (bars after the close are never built); r = 0, no dividends
The engine then runs as on real tapes (contract picker on the modeled prices, fills at the next bar's open +
half-spread, the same exits). Bars only, no trades: a stop fills at the stop price inside the bar, or at the open
when the bar gapped through it.

Calibration (tools/sprint_calibrate.py, on DEV where real option trades exist): ratio = iv_est (BS-EST IV solved from
the real option's price at the decision) / IV proxy, one row per (symbol, day, contract, signal bar); multiplier =
median ratio per "<contract rule>|<side>" (calls and puts far out of the money sit on opposite sides of the smile).
A key with fewer than MIN_CALIB trades has no multiplier and a run that needs it is refused.

Validation (pre-registered): a modeled DEV run passes when its expectancy has the same sign as the real-tape run's
and its PF is within +/-35% of the real PF. A strategy that fails has its HIST numbers labeled UNRELIABLE.

Idealizations (stated in every modeled report): a 0DTE contract every session (before Nov 2022 SPY/QQQ/IWM did not list
one every weekday); a flat smile and no intraday IV change; a price every minute; the 2% half-spread may be optimistic
for 2016-2019.

Next-expiry modeled tapes (round 8, SPRINT_PLAN Addendum 10.1/10.2: the HIST twins of n1d03-12t07, n1d40-55t45 and
n1d55-75t65 are MODELED and labeled NOT VALIDATED). The same model with the expiry at 16:00 of the NEXT NYSE session after
the day (`next_session`, from the sprint calendar), in line with the 0DTE model's "an expiry every session" idealization;
time to expiry = minutes to 16:00 today + 1440 x the calendar days to that session, exactly the convention the contract
picker (sprint/contracts.py) and the simulator use for real next-expiry contracts, so the picker's BS-EST IV recovers the
modeled IV. Bars are built only through today's close (13:00 on early-close days). The multiplier is run 4's calibration
key for the rule and side when it exists and has enough trades (n1d40-55t45|C does); otherwise (n1d40-55t45|P,
n1d03-12t07|C, n1d55-75t65|C/P have no key in run 4's file) the key of the same delta band on 0DTE ("d..." without the
"n1" prefix) is used and labeled as a fallback (`multiplier_for`). Literal reading: Amendment 10 prices HIST options with
run 4's calibration, which has no key for most next-expiry rules; refusing would leave the pre-registered HIST twins
without numbers.
"""
import json
import math
import statistics
from pathlib import Path

import numpy as np

from . import bs
from .fills import OptionTape
from .periods import HIST_YEARS, early_closes

LABEL = "MODELED (BS, calibrated IV)"
N = 390
PROXY_DAYS, PROXY_MIN_DAYS = 20, 10
STRIKE_BAND = 0.06
MIN_CALIB = 30
VALIDATION_PF_TOL = 0.35
TICK = 0.01


# ---------------------------------------------------------------- realized volatility and the IV proxy
def _close_n(day):
    return 210 if day.isoformat() in early_closes() else N


def session_var(series, day):
    """(sum of squared 1-minute log returns, minutes spanned) of one session's regular-hours bars, or None (< 30 bars).
    Cached on the series."""
    cache = series.__dict__.setdefault("_rv_cache", {})
    if day in cache:
        return cache[day]
    g = series.rth.get(day)
    out = None
    if g is not None:
        c = g[:_close_n(day), 3]
        idx = np.where(~np.isnan(c) & (c > 0))[0]
        if len(idx) >= 30:
            r = np.diff(np.log(c[idx]))
            out = (float(np.sum(r * r)), int(np.sum(np.diff(idx))))
    cache[day] = out
    return out


def sigma_1m(series, day, n=PROXY_DAYS, min_days=PROXY_MIN_DAYS):
    """Per-minute realized volatility from the n sessions BEFORE `day` (needs min_days of them), or None."""
    if day not in series.rth:
        return None
    tot = mins = used = 0
    for d in series.prior_days(day, n):
        v = session_var(series, d)
        if v is None or v[1] <= 0:
            continue
        tot += v[0]
        mins += v[1]
        used += 1
    if used < min_days or mins <= 0:
        return None
    return math.sqrt(tot / mins)


def iv_proxy(series, day):
    """Annualized IV proxy known at `day`'s open (calendar-minute year, as sprint/bs.py), or None."""
    s = sigma_1m(series, day)
    return None if s is None else s * math.sqrt(bs.YEAR_MIN)


# ---------------------------------------------------------------- modeled tapes
def _cents(x):
    return np.maximum(np.round(x, 2), TICK)


def next_session(day):
    """The next NYSE session after `day` (weekday, not a holiday of the sprint calendar)."""
    from datetime import timedelta
    from .periods import holidays
    hol = holidays()
    d = day + timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in hol:
        d += timedelta(days=1)
    return d


class ModeledDay:
    """Modeled 0DTE tapes for one stock-only DayContext, built on demand and cached per (strike, right, iv).
    expiry: a later expiry date (next-expiry tapes; see the module docstring), default the day itself (0DTE)."""

    def __init__(self, ctx, expiry=None):
        self.ctx = ctx
        self.close_n = ctx.close_idx
        self.expiry = expiry if expiry is not None and expiry > ctx.day else ctx.day
        i = np.arange(N)
        if self.expiry > ctx.day:                                                # to 16:00 + calendar days (picker's convention)
            extra = 1440 * (self.expiry - ctx.day).days
            self.Ta = np.maximum(N - i + extra, bs.MIN_T_MIN) / bs.YEAR_MIN
            self.Tb = np.maximum(N - i - 1 + extra, bs.MIN_T_MIN) / bs.YEAR_MIN
        else:
            self.Ta = np.maximum(self.close_n - i, bs.MIN_T_MIN) / bs.YEAR_MIN   # minutes left at the bar's start
            self.Tb = np.maximum(self.close_n - i - 1, bs.MIN_T_MIN) / bs.YEAR_MIN   # ... at the bar's end
        o, h, l, c = (np.asarray(x, float) for x in (ctx.o, ctx.h, ctx.l, ctx.c))
        self.ok = ~(np.isnan(o) | np.isnan(h) | np.isnan(l) | np.isnan(c)) & (i < self.close_n)
        fill = lambda x: np.where(self.ok, x, 1.0)
        self.o, self.h, self.l, self.c = fill(o), fill(h), fill(l), fill(c)
        self._cache = {}

    def symbol(self, K, right):
        return f"{self.ctx.sym}{self.expiry:%y%m%d}{right}{int(round(K * 1000)):08d}"

    def _build(self, Ks, right, iv):
        """Tapes for several strikes at once (one array call per price series; the same formula per element)."""
        call = right == "C"
        K = np.asarray(Ks, float)[:, None]
        po = bs.price_v(self.o[None, :], K, self.Ta[None, :], iv, call)
        pc = bs.price_v(self.c[None, :], K, self.Tb[None, :], iv, call)
        ph = bs.price_v((self.h if call else self.l)[None, :], K, self.Tb[None, :], iv, call)
        pl = bs.price_v((self.l if call else self.h)[None, :], K, self.Tb[None, :], iv, call)
        o, c = _cents(po), _cents(pc)
        h = np.maximum(np.maximum(o, c), _cents(ph))
        lo = np.minimum(np.minimum(o, c), _cents(pl))
        m = self.ok[None, :]
        o, h, lo, c = (np.where(m, x, np.nan) for x in (o, h, lo, c))
        vol = np.where(self.ok, 1.0, np.nan)
        out = []
        for j, k in enumerate(np.asarray(Ks, float)):
            t = OptionTape(self.symbol(k, right), right, k, o[j], h[j], lo[j], c[j], vol)
            t.expiry = self.expiry
            t.modeled = True
            self._cache[(float(k), right, round(float(iv), 10))] = t
            out.append(t)
        return out

    def tape(self, K, right, iv):
        t = self._cache.get((float(K), right, round(float(iv), 10)))
        return t if t is not None else self._build([float(K)], right, iv)[0]

    def pool(self, S, side, iv, band=STRIKE_BAND):
        """{symbol: tape} of every $1 strike within +/- band of S, on one side (what contracts.pick reads)."""
        k0, k1 = int(math.floor(S * (1 - band))), int(math.ceil(S * (1 + band)))
        ks = [float(k) for k in range(max(k0, 1), k1 + 1)]
        miss = [k for k in ks if (k, side, round(float(iv), 10)) not in self._cache]
        if miss:
            self._build(miss, side, iv)
        out = {}
        for k in ks:
            t = self._cache[(k, side, round(float(iv), 10))]
            out[t.symbol] = t
        return out


# ---------------------------------------------------------------- calibration
def calib_key(rule, side):
    return f"{rule}|{side}"


def _q(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _stats(xs):
    return {"n": len(xs), "median": round(statistics.median(xs), 4), "q1": round(_q(xs, 0.25), 4),
            "q3": round(_q(xs, 0.75), 4)} if xs else {"n": 0}


def calibrate(rows, proxy, min_n=MIN_CALIB):
    """rows: dicts with symbol, day (date or ISO), contract, signal_idx, side, rule, iv_est (and setup). proxy:
    callable (symbol, day ISO) -> IV proxy or None. One row per (symbol, day, contract, signal_idx) is used.
    Returns the calibration dict saved as data/sprint/calib_modeled.json (without file metadata)."""
    seen, ratios, skipped = set(), {}, {"duplicate": 0, "no iv_est": 0, "no IV proxy": 0, "no contract rule": 0}
    by_sym, by_setup, pooled = {}, {}, {}
    for r in rows:
        day = str(r["day"])[:10]
        k = (r["symbol"], day, r.get("contract"), str(r.get("signal_idx")))
        if k in seen:
            skipped["duplicate"] += 1
            continue
        seen.add(k)
        rule = r.get("rule")
        if not isinstance(rule, str) or not rule:
            skipped["no contract rule"] += 1
            continue
        try:
            iv = float(r.get("iv_est"))
        except (TypeError, ValueError):
            iv = math.nan
        if not (iv > 0) or math.isnan(iv):
            skipped["no iv_est"] += 1
            continue
        p = proxy(r["symbol"], day)
        if not p:
            skipped["no IV proxy"] += 1
            continue
        x = iv / p
        key = calib_key(rule, r["side"])
        ratios.setdefault(key, []).append(x)
        pooled.setdefault(rule, []).append(x)
        by_sym.setdefault(key, {}).setdefault(r["symbol"], []).append(x)
        fam = str(r.get("setup") or "?").split(":")[-1]
        by_setup.setdefault(key, {}).setdefault(fam, []).append(x)
    keys = {}
    for k, xs in sorted(ratios.items()):
        s = _stats(xs)
        s["ok"] = len(xs) >= min_n
        keys[k] = s
    return {"label": "calibration of " + LABEL, "method": "multiplier = median(iv_est / IV proxy) per contract rule|side",
            "min_n": min_n, "keys": keys, "pooled_by_rule": {k: _stats(v) for k, v in sorted(pooled.items())},
            "by_symbol": {k: {s: _stats(v)["median"] for s, v in sorted(d.items())} for k, d in sorted(by_sym.items())},
            "by_setup": {k: {s: dict(_stats(v)) for s, v in sorted(d.items())} for k, d in sorted(by_setup.items())},
            "skipped": skipped, "rows_used": sum(len(v) for v in ratios.values())}


def multiplier(calib, rule, side):
    """The calibrated multiplier for a contract rule and side ("C"/"P"). Raises ValueError when the key is missing or
    thin (fewer than MIN_CALIB trades)."""
    k = calib_key(rule, side)
    s = (calib or {}).get("keys", {}).get(k)
    if not s or not s.get("n"):
        raise ValueError(f"MODELED tapes: no calibration for {k} (run tools/sprint_calibrate.py on DEV first)")
    if not s.get("ok"):
        raise ValueError(f"MODELED tapes: calibration for {k} has only {s['n']} trades (needs {calib.get('min_n', MIN_CALIB)})")
    return float(s["median"])


def multiplier_for(calib, rule, side):
    """(multiplier, calibration key used) for a contract rule and side. Next-expiry rules ("n1...") use their own key when
    run 4's calibration has it with enough trades, else the same delta band's 0DTE key (labeled fallback; see the module
    docstring). Every other rule is exactly `multiplier` (a missing or thin key still refuses)."""
    try:
        return multiplier(calib, rule, side), calib_key(rule, side)
    except ValueError:
        if not str(rule).startswith("n1"):
            raise
    base = str(rule)[2:]
    return multiplier(calib, base, side), calib_key(base, side) + " (fallback for " + calib_key(rule, side) + ")"


def load_calib(path):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"{p} not found: MODELED runs need the DEV calibration first (tools/sprint_calibrate.py)")
    return json.loads(p.read_text())


# ---------------------------------------------------------------- validation and the HIST reading
def _f(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def validate(modeled, real, tol=VALIDATION_PF_TOL):
    """modeled / real: {"expectancy", "profit_factor", "trades"} of one strategy. Pre-registered bar: the same sign of
    expectancy and modeled PF within +/- tol of the real PF."""
    em, er = _f(modeled.get("expectancy")), _f(real.get("expectancy"))
    pm, pr = _f(modeled.get("profit_factor")), _f(real.get("profit_factor"))
    same = em is not None and er is not None and (em > 0) == (er > 0) and em != 0 and er != 0
    ratio = (pm / pr) if pm is not None and pr not in (None, 0) and not math.isinf(pm) and not math.isinf(pr) else None
    within = ratio is not None and (1 - tol) <= ratio <= (1 + tol)
    return {"real_trades": real.get("trades"), "real_exp": er, "real_pf": pr, "modeled_trades": modeled.get("trades"),
            "modeled_exp": em, "modeled_pf": pm, "pf_ratio": None if ratio is None else round(ratio, 3),
            "same_sign": bool(same), "pf_within": bool(within), "pass": bool(same and within)}


def hist_reading(s, rob, filtered, years=HIST_YEARS):
    """The pre-registered Layer-2 reading on HIST (SPRINT_PLAN Amendment 5) for one run: [(check, ok)], verdict."""
    st = s.get("stretches") or {}
    yrs = [str(y) for y in years]
    up = sum(1 for y in yrs if ((st.get(y) or {}).get("net") or 0) > 0)
    items = [("at least 60 trades", s.get("trades", 0) >= 60),
             ("expectancy > 0", (s.get("expectancy") or 0) > 0),
             ("PF >= 1.25", (s.get("profit_factor") or 0) >= 1.25),
             ("PF > 1.0 at 2x slippage", (s.get("pf_2x_slip") or 0) > 1.0),
             (f"profitable in at least 6 of the 8 years 2016-2023 ({up} of 8)", up >= 6),
             ("positive without its best 5 trades", ((s.get("without_best5") or {}).get("net") or 0) > 0)]
    if filtered:
        p = rob.get("skip_p")
        items.append((f"filter beats random day-skips of its twin, p <= 0.05 (p = {p})", p is not None and p <= 0.05))
    return items, all(ok for _, ok in items)
