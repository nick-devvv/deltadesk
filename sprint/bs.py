"""sprint/bs.py - Black-Scholes helpers for 0DTE options, used because Alpaca's option bars carry no greeks.

Conventions (labeled BS-EST wherever a number comes from here):
  * r = 0 and no dividends (0DTE: the carry over a few hours is negligible next to the spread).
  * Time to expiry = calendar minutes to 16:00 ET / (365 x 24 x 60), floored at 2 minutes (as replay.py does).
  * Implied vol is solved per minute from the option's own traded price (bar close, a proxy for the mid) and the
    underlying's price at the same minute, by bisection on [0.01, 5.0]. A price at or below intrinsic value, or above
    the no-arbitrage bound, has no implied vol (None): the contract then has no delta and is never picked.
Scalar functions use math.erf; the vectorized ones (for the contract picker) use numpy with the Abramowitz-Stegun
7.1.26 erf (max error 1.5e-7, far below anything that changes a pick).
"""
import math

import numpy as np

YEAR_MIN = 365.0 * 24 * 60
MIN_T_MIN = 2.0
IV_LO, IV_HI = 0.01, 5.0


def t_years(minutes_to_close):
    return max(float(minutes_to_close), MIN_T_MIN) / YEAR_MIN


def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def price(S, K, T, iv, right):
    if T <= 0 or iv <= 0:
        return max(0.0, S - K) if right == "C" else max(0.0, K - S)
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * iv * iv * T) / sq
    d2 = d1 - sq
    if right == "C":
        return max(0.0, S * _ncdf(d1) - K * _ncdf(d2))
    return max(0.0, K * _ncdf(-d2) - S * _ncdf(-d1))


def delta(S, K, T, iv, right):
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * iv * iv * T) / sq
    return _ncdf(d1) if right == "C" else _ncdf(d1) - 1.0


def implied_vol(px, S, K, T, right, iters=60):
    """Implied vol from a traded option price, or None when the price is outside the no-arbitrage range."""
    if px is None or not (px > 0) or S <= 0 or K <= 0:
        return None
    intrinsic = max(0.0, S - K) if right == "C" else max(0.0, K - S)
    upper = S if right == "C" else K
    if px <= intrinsic + 1e-9 or px >= upper:
        return None
    lo, hi = IV_LO, IV_HI
    if price(S, K, T, hi, right) < px or price(S, K, T, lo, right) > px:
        return None
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if price(S, K, T, mid, right) < px:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------- vectorized (contract picker)
def _erf_v(x):
    s = np.sign(x)
    a = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * a)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-a * a)
    return s * y


def _ncdf_v(x):
    return 0.5 * (1.0 + _erf_v(x / math.sqrt(2.0)))


def price_v(S, K, T, iv, is_call):
    sq = iv * np.sqrt(T)
    d1 = (np.log(S / K) + 0.5 * iv * iv * T) / sq
    d2 = d1 - sq
    c = S * _ncdf_v(d1) - K * _ncdf_v(d2)
    p = K * _ncdf_v(-d2) - S * _ncdf_v(-d1)
    return np.maximum(np.where(is_call, c, p), 0.0)


def iv_delta_v(px, S, K, T, is_call, iters=60):
    """Vectorized implied vol and BS delta. px, K, is_call: arrays; S, T: scalars. NaN where undefined."""
    px = np.asarray(px, float)
    K = np.asarray(K, float)
    is_call = np.asarray(is_call, bool)
    intrinsic = np.where(is_call, np.maximum(S - K, 0.0), np.maximum(K - S, 0.0))
    upper = np.where(is_call, S, K)
    ok = (px > intrinsic + 1e-9) & (px < upper) & (px > 0)
    lo = np.full(px.shape, IV_LO)
    hi = np.full(px.shape, IV_HI)
    ok &= price_v(S, K, T, hi, is_call) >= px
    ok &= price_v(S, K, T, lo, is_call) <= px
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        below = price_v(S, K, T, mid, is_call) < px
        lo = np.where(below, mid, lo)
        hi = np.where(below, hi, mid)
    iv = 0.5 * (lo + hi)
    sq = iv * math.sqrt(T)
    d1 = (np.log(S / K) + 0.5 * iv * iv * T) / sq
    d = np.where(is_call, _ncdf_v(d1), _ncdf_v(d1) - 1.0)
    return np.where(ok, iv, np.nan), np.where(ok, d, np.nan)


def stock_for_price(target_px, K, T, iv, right, S_ref):
    """The underlying price at which the BS price equals target_px (same iv and T), by bisection around S_ref.
    Used to translate a premium stop into a stock level for the R:R filter. None if out of range."""
    lo, hi = S_ref * 0.5, S_ref * 1.5
    f = lambda s: price(s, K, T, iv, right) - target_px
    flo, fhi = f(lo), f(hi)
    if right == "P":
        flo, fhi = -flo, -fhi
        g = lambda s: -(price(s, K, T, iv, right) - target_px)
    else:
        g = f
    if flo > 0 or fhi < 0:
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if g(mid) < 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
