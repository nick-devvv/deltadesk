"""sprint/ivdata.py - round 10's data step D-IV: daily 30-day and 90-day at-the-money implied vol per name (SPRINT_PLAN
Amendment 16, "Data step D-IV", pre-registered 2026-11-01 before any round-10 code, pull or run). Research only: reads the
cached option and stock bars that tools/sprint_pull10.py writes; no network, no orders. Every IV here is BS-EST (solved from
Alpaca trade prices with Black-Scholes, r = q = 0), never a quoted IV.

As written (Amendment 16):
  Universe   U-STK and U-ETF (sprint/universe.py), DEV sessions 2024-08-01..2026-06-30; never a locked date.
  Contracts  two expiries per name per day: the first expiry at least 21 calendar days out (the "30-day" expiry) and the
             expiry nearest 90 days within 60-120 (the "90-day" expiry).
  Price      each contract's last trade 15:45-16:00, matched to the stock's 1-minute close in the same minute; prints older
             than 30 minutes are dropped.
  ATM IV     BS IV of the two strikes bracketing spot, call and put averaged, interpolated in strike, r = q = 0 (labeled).
  Smoothing  a 5-session mean is used for sorting.
  Coverage   the share of name-days with an IV, and each name's median IV vs its 20-day realized vol.

Builder's reading (the most literal reading where the text is ambiguous or impossible with our data):
  * U-STK on day t = the names passing round 9's point-in-time filter on t (prior raw close > $5 and 20-session mean dollar
    volume > $50M, universe.Panel.eligible); U-ETF names are always in. SURVIVORSHIP-BIASED (U-STK is today's list).
  * "Listed" is not observable (the pull never reads a contract listing), so an expiry or strike counts only when one of its
    contracts printed in that day's 15:45-15:59 bars. The pull probes candidate expiries in order and stops at the first one
    with a print (plan_name): 30-day: the first Friday expiry >= t + 21 (Thursday when that Friday is an NYSE holiday), then
    the first monthly (third Friday) >= t + 21; U-ETF names also probe every session from t + 21 to that Friday first (index
    ETFs list Monday-Thursday expiries). 90-day: every Friday expiry and every quarter-end session in t + 60..t + 120, nearest
    90 days first (equal distance: both in one probe; the earlier wins). The chosen expiries are then read from the file:
    exp30 = the earliest printed expiry >= t + 21 days; exp90 = the printed expiry in 60-120 days nearest 90 (ties: earlier).
    If that expiry has no usable ATM IV the day has none for it (no fall-back to another expiry).
  * Strikes probed: for every plausible listing grid at the stock's price (catalyst.GRIDS: $0.5 ... $100), every grid strike
    from the one at or below the lowest 15:45-15:59 1-minute close to the one at or above the highest (usually 2 per grid,
    about 4-6 in all), calls and puts.
  * "Last trade 15:45-16:00" = the close of the contract's last 1-minute bar stamped 15:45..15:59 (Alpaca option bars; a
    bar's close is its last trade). The stock price is the stock's raw 1-minute close stamped in the same minute; a print
    with no stock bar in its minute is dropped. The 30-minute age rule (16:00 minus the bar's minute) is applied but cannot
    bite inside a 15:45-16:00 window.
  * Time to expiry = calendar minutes from the end of the print's minute to 16:00 on the expiry day / (365 x 24 x 60), as
    sprint/bs.py. IV solved by bisection on [0.01, 5.0] (iv_vec); a price at/below intrinsic or at/above the no-arbitrage
    bound has no IV.
  * A strike's IV = the mean of its call IV and put IV, both required ("call and put averaged"). Spot = the stock's last
    15:45-15:59 1-minute close. The bracketing strikes = the highest strike <= spot and the lowest strike >= spot among
    strikes with both IVs; IV = linear interpolation in strike (spot on a strike: that strike's IV). One side missing -> no
    IV (no extrapolation).
  * The 5-session mean at t = the mean over the last 5 DEV sessions t-4..t; all 5 must have an IV. Rules that sort "on data
    through the prior close" read it at t-1 (IVTable.prior).
  * 20-day realized vol (coverage report, information) = the sample standard deviation of the last 20 daily log returns of
    split-adjusted closes through t (each name's own bars, never across a locked gap) x sqrt(252).
Cache layout (data/alpaca unless --data; written by tools/sprint_pull10.py, read here):
  r10/opt/<day>/<HHMM-HHMM>.pNNNN.csv.gz      option 1-minute bars of one day and window, one append-only part per fetch
  r10/opt/<day>/<HHMM-HHMM>.json              the marker: every OCC symbol asked for and every one that printed (a part
                                             written before a crash but missing from the marker is re-asked and deduped)
  r10/opt/<day>/<tag>.done                   a provider finished that day (D-IV: "div.done")
  r10/stock15/<day>.csv.gz + .json           raw stock 1-minute bars 15:45-16:00 of that day (symbol column)
  r10/div/<day>.json                         this module's per-day result cache (rebuilt when the day's files change)
"""
import functools
import json
import math
import statistics
from collections import defaultdict, namedtuple
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import bs, periods
from . import universe as U
from .catalyst import GRIDS, occ, occ_root
from .data import parse_occ

LABEL = "BS-EST ATM IV (solved from Alpaca trade prices, r = q = 0)"
R10 = "r10"
W_LAST = ("15:45", "16:00")
W_OPEN = ("09:30", "09:35")
W_DAY = ("09:30", "16:00")
LAST_M0, LAST_M1 = 375, 389                   # 15:45 .. 15:59 (minutes after 09:30)
MAX_AGE = 30
DTE30_MIN = 21
DTE90_LO, DTE90_HI, DTE90_TGT = 60, 120, 90
MEAN_N = 5
RV_N = 20
DEV_A, DEV_B = periods.DEV

Need = namedtuple("Need", "day window symbols tag priority")


def need(day, window, symbols, tag="", priority=1):
    return Need(day, tuple(window), tuple(sorted(set(symbols))), tag, int(priority))


def wkey(window):
    return f"{window[0].replace(':', '')}-{window[1].replace(':', '')}"


def dev_days():
    return U.sessions(DEV_A, DEV_B)


# ---------------------------------------------------------------- cache layout (read side)
def opt_dir(root, day):
    return Path(root) / R10 / "opt" / day.isoformat()


def opt_marker(root, day, window):
    return opt_dir(root, day) / f"{wkey(window)}.json"


def opt_parts(root, day, window):
    return sorted(opt_dir(root, day).glob(f"{wkey(window)}.p*.csv.gz"))


def stock_path(root, day):
    return Path(root) / R10 / "stock15" / f"{day.isoformat()}.csv.gz"


def marker_path(path):
    p = Path(path)
    return p if p.suffix == ".json" else Path(str(p)[:-len(".csv.gz")] + ".json")


def read_marker(path):
    try:
        return json.loads(marker_path(path).read_text())
    except (OSError, ValueError):
        return {}


def read_frame(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p, compression="gzip")
    except (OSError, ValueError, EOFError):
        return None
    return df


def read_opt(root, day, window):
    """Every part of one day's option file for one window, deduplicated by (symbol, ts); None when there is none."""
    frames = [f for f in (read_frame(p) for p in opt_parts(root, day, window)) if f is not None and len(f)]
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    return df.drop_duplicates(["symbol", "ts"]).reset_index(drop=True)


def minutes(df):
    """Minutes after 09:30 from the cache's ET ISO strings ('2025-03-04T15:45:00-05:00')."""
    s = df["ts"].astype(str)
    return (s.str.slice(11, 13).astype(int) * 60 + s.str.slice(14, 16).astype(int)).to_numpy() - 570


class Bars:
    """Read side of the round-10 cache for one root: markers (asked / printed), each day's last 15:45-15:59 print per
    contract, first 09:30-09:34 prints, first regular-hours prints, and the stock's 15:45-15:59 closes. Small LRU caches;
    the pull calls invalidate() after it writes a file."""

    def __init__(self, root, keep=48):
        self.root = Path(root)
        self.keep = keep
        self._c = {}

    def _get(self, key, fn):
        if key in self._c:
            v = self._c.pop(key)
            self._c[key] = v
            return v
        v = fn()
        self._c[key] = v
        while len(self._c) > self.keep:
            self._c.pop(next(iter(self._c)))
        return v

    def invalidate(self, day, window=None):
        for k in [k for k in self._c if k[1] == day and (window is None or k[2] in (tuple(window), None))]:
            self._c.pop(k, None)

    def marker(self, day, window):
        return self._get(("marker", day, tuple(window)), lambda: read_marker(opt_marker(self.root, day, window)))

    def asked(self, day, window):
        return self._get(("asked", day, tuple(window)), lambda: set(self.marker(day, window).get("asked") or []))

    def printed(self, day, window):
        return self._get(("printed", day, tuple(window)), lambda: set(self.marker(day, window).get("printed") or []))

    def frame(self, day, window):
        return read_opt(self.root, day, window)

    def last15(self, day):
        """{root: {(expiry, strike, right): (occ, minute, close)}} from the day's 15:45-16:00 file."""
        def build():
            lp = last_prints(self.frame(day, W_LAST), day)
            out = defaultdict(dict)
            for sym, m, c, r, e, rt, k in lp[["symbol", "m", "c", "root", "expiry", "right", "strike"]].itertuples(index=False):
                if c > 0:
                    out[r][(e, float(k), rt)] = (sym, int(m), float(c))
            return out
        return self._get(("last15", day, tuple(W_LAST)), build)

    def opens(self, day):
        """{root: {(expiry, strike, right): (occ, minute, open)}}: each contract's first bar 09:30-09:34 (its open)."""
        def build():
            df = self.frame(day, W_OPEN)
            out = defaultdict(dict)
            if df is None or not len(df):
                return out
            m = minutes(df)
            ok = (m >= 0) & (m <= 4)
            f = pd.DataFrame({"symbol": df["symbol"].astype(str).to_numpy()[ok], "m": m[ok], "o": df["o"].to_numpy(float)[ok]})
            f = f.sort_values(["symbol", "m"], kind="stable").drop_duplicates("symbol", keep="first")
            for sym, mm, o in f.itertuples(index=False):
                meta = parse_occ(sym)
                if meta and o > 0:
                    out[meta["root"]][(meta["expiry"], float(meta["strike"]), meta["right"])] = (sym, int(mm), float(o))
            return out
        return self._get(("opens", day, tuple(W_OPEN)), build)

    def first_prints(self, day):
        """{occ: (minute, open)}: each contract's first regular-hours bar of the day (09:30-16:00 file)."""
        def build():
            df = self.frame(day, W_DAY)
            if df is None or not len(df):
                return {}
            m = minutes(df)
            ok = (m >= 0) & (m < 390)
            f = pd.DataFrame({"symbol": df["symbol"].astype(str).to_numpy()[ok], "m": m[ok], "o": df["o"].to_numpy(float)[ok]})
            f = f.sort_values(["symbol", "m"], kind="stable").drop_duplicates("symbol", keep="first")
            return {s: (int(mm), float(o)) for s, mm, o in f.itertuples(index=False) if o > 0}
        return self._get(("first", day, tuple(W_DAY)), build)

    def stock_minutes(self, day):
        """{name: {minute: close}} from the day's stock15 file, or None when that file was never written."""
        def build():
            p = stock_path(self.root, day)
            if not marker_path(p).exists():
                return None
            return dict(stock_minutes(read_frame(p)))
        return self._get(("stock", day, None), build)


# ---------------------------------------------------------------- the vectorized IV solver
def iv_vec(px, S, K, T, is_call, iters=64):
    """Black-Scholes implied vol (r = q = 0) for arrays (broadcast); NaN where the price has no IV in [0.01, 5.0]."""
    px, S, K, T = (np.asarray(x, float) for x in (px, S, K, T))
    is_call = np.asarray(is_call, bool)
    px, S, K, T, is_call = np.broadcast_arrays(px, S, K, T, is_call)
    with np.errstate(invalid="ignore", divide="ignore"):
        intrinsic = np.where(is_call, np.maximum(S - K, 0.0), np.maximum(K - S, 0.0))
        upper = np.where(is_call, S, K)
        ok = np.isfinite(px) & np.isfinite(S) & np.isfinite(K) & np.isfinite(T) & (px > 0) & (S > 0) & (K > 0) & (T > 0)
        ok &= (px > intrinsic + 1e-9) & (px < upper)
        Sx, Kx, Tx = np.where(ok, S, 1.0), np.where(ok, K, 1.0), np.where(ok, T, 1.0)
        lo = np.full(px.shape, bs.IV_LO)
        hi = np.full(px.shape, bs.IV_HI)
        ok &= bs.price_v(Sx, Kx, Tx, hi, is_call) >= px
        ok &= bs.price_v(Sx, Kx, Tx, lo, is_call) <= px
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            below = bs.price_v(Sx, Kx, Tx, mid, is_call) < px
            lo = np.where(below, mid, lo)
            hi = np.where(below, hi, mid)
    return np.where(ok, 0.5 * (lo + hi), np.nan)


def delta_vec(S, K, T, iv, is_call):
    """BS delta (r = q = 0) for arrays; NaN where undefined."""
    S, K, T, iv = (np.asarray(x, float) for x in (S, K, T, iv))
    with np.errstate(invalid="ignore", divide="ignore"):
        sq = iv * np.sqrt(T)
        d1 = (np.log(S / K) + 0.5 * iv * iv * T) / sq
        n = bs._ncdf_v(d1)
    return np.where(np.asarray(is_call, bool), n, n - 1.0)


def strike_for_delta(S, T, iv, target, right):
    """The strike whose BS delta is `target` (|delta| for puts) at vol iv: K = S exp(-d1 iv sqrt(T) + iv^2 T / 2)."""
    z = statistics.NormalDist().inv_cdf(float(target))
    d1 = z if right == "C" else -z
    sq = iv * math.sqrt(T)
    return float(S * math.exp(-d1 * sq + 0.5 * iv * iv * T))


def t_minutes(day, minute, expiry):
    """Calendar minutes from the end of 1-minute bar `minute` on `day` to 16:00 on `expiry`."""
    return 390 - (int(minute) + 1) + 1440 * (expiry - day).days


# ---------------------------------------------------------------- expiries and strikes probed
@functools.lru_cache(maxsize=1)
def _hol():
    return frozenset(periods.holidays())


def _fri(d, hol):
    return d - timedelta(days=1) if d.isoformat() in hol else d


def friday_expiries(a, b):
    """Every Friday expiry in [a, b] (Thursday when that Friday is an NYSE holiday)."""
    hol = _hol()
    d = a + timedelta(days=(4 - a.weekday()) % 7)
    out = []
    while d <= b + timedelta(days=1):
        e = _fri(d, hol)
        if a <= e <= b:
            out.append(e)
        d += timedelta(days=7)
    return out


def third_friday(y, m):
    first = date(y, m, 1)
    return first + timedelta(days=(4 - first.weekday()) % 7 + 14)


def monthly_expiries(a, b):
    hol = _hol()
    out, y, m = [], a.year, a.month
    while date(y, m, 1) <= b:
        e = _fri(third_friday(y, m), hol)
        if a <= e <= b:
            out.append(e)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def quarter_ends(a, b):
    """The last NYSE session of March, June, September and December inside [a, b]."""
    cal = U.all_sessions_cal(a, b + timedelta(days=10))
    return [d for d, nxt in zip(cal, cal[1:]) if d.month in (3, 6, 9, 12) and nxt.month != d.month and a <= d <= b]


@functools.lru_cache(maxsize=4096)
def exp30_phases(day, etf=False):
    """Probe order for the 30-day expiry: ((expiry,), ...)."""
    lo = day + timedelta(days=DTE30_MIN)
    f = friday_expiries(lo, lo + timedelta(days=7))[0]
    m = monthly_expiries(lo, lo + timedelta(days=40))[0]
    out = [(s,) for s in U.all_sessions_cal(lo, f) if s != f] if etf else []
    out.append((f,))
    if m != f:
        out.append((m,))
    return tuple(out)


@functools.lru_cache(maxsize=4096)
def exp90_phases(day):
    """Probe order for the 90-day expiry: Friday expiries and quarter-end sessions in t+60..t+120, nearest 90 days first;
    equal distances share a phase."""
    a, b = day + timedelta(days=DTE90_LO), day + timedelta(days=DTE90_HI)
    c = sorted(set(friday_expiries(a, b)) | set(quarter_ends(a, b)))
    by = defaultdict(list)
    for e in c:
        by[abs((e - day).days - DTE90_TGT)].append(e)
    return tuple(tuple(sorted(by[k])) for k in sorted(by))


def grids_for(px):
    return [g for g, lo, hi in GRIDS if lo <= px < hi]


def bracket_strikes(lo_px, hi_px):
    """Every grid strike from the one at/below lo_px to the one at/above hi_px, on every plausible grid at that price."""
    out = set()
    for g in grids_for(0.5 * (lo_px + hi_px)):
        k0 = math.floor(lo_px / g + 1e-9) * g
        k1 = math.ceil(hi_px / g - 1e-9) * g
        k = k0
        while k <= k1 + 1e-9:
            if k > 0:
                out.add(round(k, 2))
            k += g
    return sorted(out)


def band_strikes(lo_px, hi_px, ref):
    """Every grid strike inside [lo_px, hi_px] on every plausible grid at price `ref`."""
    out = set()
    for g in grids_for(ref):
        k = math.ceil(lo_px / g - 1e-9) * g
        while k <= hi_px + 1e-9:
            if k > 0:
                out.add(round(k, 2))
            k += g
    return sorted(out)


def near_strikes(target, ref):
    """For every plausible grid at price `ref`: the two grid strikes bracketing `target` and one more on each side."""
    out = set()
    for g in grids_for(ref):
        k0 = math.floor(target / g + 1e-9) * g
        for k in (k0 - g, k0, k0 + g, k0 + 2 * g):
            if k > 0:
                out.add(round(k, 2))
    return sorted(out)


def contracts(name, expiries, strikes, rights=("C", "P")):
    return [occ(name, e, r, k) for e in expiries for k in strikes for r in rights]


# ---------------------------------------------------------------- the stock's last 15 minutes
def stock_minutes(stock_df):
    """{name: {minute: raw close}} for minutes 15:45..15:59 from a stock15 day file."""
    out = defaultdict(dict)
    if stock_df is None or not len(stock_df):
        return out
    m = minutes(stock_df)
    ok = (m >= LAST_M0) & (m <= LAST_M1)
    for s, mm, c in zip(stock_df["symbol"].to_numpy()[ok], m[ok], stock_df["c"].to_numpy(float)[ok]):
        if np.isfinite(c) and c > 0:
            out[str(s)][int(mm)] = float(c)
    return out


def spot_of(mins):
    """The last 15:45-15:59 close (spot) of one name's minute map, or None."""
    return mins[max(mins)] if mins else None


# ---------------------------------------------------------------- the pull's plan for one name-day
def plan_name(name, day, mins, asked, printed, etf=False):
    """OCC symbols D-IV still needs for one name on one day ([] when finished). Probes the 30-day then the 90-day expiry
    phase by phase, stopping at the first phase with a print. mins: the name's 15:45-15:59 minute closes."""
    if not mins:
        return []
    v = list(mins.values())
    ks = bracket_strikes(min(v), max(v))
    if not ks:
        return []
    out = []
    for phases in (exp30_phases(day, etf), exp90_phases(day)):
        for ph in phases:
            syms = contracts(name, ph, ks)
            miss = [s for s in syms if s not in asked]
            if miss:
                out += miss
                break
            if any(s in printed for s in syms):
                break
    return out


# ---------------------------------------------------------------- one day's ATM IVs
def last_prints(opt_df, day):
    """DataFrame (symbol, m, c, root, expiry, right, strike) of each contract's last 15:45-15:59 bar."""
    cols = ["symbol", "m", "c", "root", "expiry", "right", "strike"]
    if opt_df is None or not len(opt_df):
        return pd.DataFrame(columns=cols)
    m = minutes(opt_df)
    ok = (m >= LAST_M0) & (m <= LAST_M1) & ((390 - m) <= MAX_AGE)
    if not ok.any():
        return pd.DataFrame(columns=cols)
    f = pd.DataFrame({"symbol": opt_df["symbol"].astype(str).to_numpy()[ok], "m": m[ok], "c": opt_df["c"].to_numpy(float)[ok]})
    f = f.sort_values(["symbol", "m"], kind="stable").drop_duplicates("symbol", keep="last")
    meta = [parse_occ(s) for s in f["symbol"]]
    keep = np.array([x is not None for x in meta])
    f = f[keep].copy()
    meta = [x for x in meta if x is not None]
    f["root"] = [x["root"] for x in meta]
    f["expiry"] = [x["expiry"] for x in meta]
    f["right"] = [x["right"] for x in meta]
    f["strike"] = [x["strike"] for x in meta]
    return f[cols].reset_index(drop=True)


def choose_expiries(day, expiries):
    """(exp30, exp90) from the expiries with a print: the earliest >= day + 21 days; the one in 60-120 days nearest 90
    (ties: the earlier)."""
    ex = sorted(set(expiries))
    e30 = next((e for e in ex if (e - day).days >= DTE30_MIN), None)
    c90 = [e for e in ex if DTE90_LO <= (e - day).days <= DTE90_HI]
    e90 = min(c90, key=lambda e: (abs((e - day).days - DTE90_TGT), e)) if c90 else None
    return e30, e90


def atm_from_strikes(strike_iv, S):
    """(iv, k_lo, k_hi) by linear interpolation between the strikes bracketing S; strike_iv: {K: iv}. (None, why) else."""
    if S is None or not strike_iv:
        return None, "no strike with both a call and a put IV"
    below = [k for k in strike_iv if k <= S + 1e-9]
    above = [k for k in strike_iv if k >= S - 1e-9]
    if not below or not above:
        return None, "no strike with both IVs on one side of spot"
    k0, k1 = max(below), min(above)
    if abs(k1 - k0) < 1e-9:
        return (float(strike_iv[k0]), k0, k1), None
    w = (S - k0) / (k1 - k0)
    return (float(strike_iv[k0] + w * (strike_iv[k1] - strike_iv[k0])), k0, k1), None


def day_ivs(day, opt_df, stock_df, names):
    """{name: {"iv30", "iv90", "exp30", "exp90", "spot", "k30", "k90", "why30", "why90"}} for one DEV day."""
    sm = stock_minutes(stock_df)
    roots = {occ_root(n): n for n in names}
    lp = last_prints(opt_df, day)
    out = {}
    if len(lp):
        lp = lp[lp["root"].isin(list(roots))].copy()
    if len(lp):
        lp["name"] = lp["root"].map(roots)
        S = np.array([sm.get(n, {}).get(int(m), np.nan) for n, m in zip(lp["name"], lp["m"])], float)
        T = np.array([bs.t_years(t_minutes(day, m, e)) for m, e in zip(lp["m"], lp["expiry"])], float)
        lp["S"] = S
        lp["iv"] = iv_vec(lp["c"].to_numpy(float), S, lp["strike"].to_numpy(float), T, (lp["right"] == "C").to_numpy())
        groups = {n: g for n, g in lp.groupby("name", sort=False)}
    else:
        groups = {}
    for n in names:
        spot = spot_of(sm.get(n, {}))
        rec = {"iv30": None, "iv90": None, "exp30": None, "exp90": None, "spot": spot, "k30": None, "k90": None}
        g = groups.get(n)
        if spot is None:
            rec["why30"] = rec["why90"] = "no stock 1-minute bar 15:45-15:59"
            out[n] = rec
            continue
        if g is None or not len(g):
            rec["why30"] = rec["why90"] = "no option print 15:45-15:59"
            out[n] = rec
            continue
        e30, e90 = choose_expiries(day, g["expiry"].tolist())
        for tag, e in (("30", e30), ("90", e90)):
            if e is None:
                rec[f"why{tag}"] = "no printed expiry " + (">= 21 days out" if tag == "30" else "60-120 days out")
                continue
            rec[f"exp{tag}"] = e.isoformat()
            ge = g[(g["expiry"] == e) & np.isfinite(g["iv"].to_numpy(float))]
            civ = dict(zip(ge[ge["right"] == "C"]["strike"], ge[ge["right"] == "C"]["iv"]))
            piv = dict(zip(ge[ge["right"] == "P"]["strike"], ge[ge["right"] == "P"]["iv"]))
            both = {float(k): 0.5 * (float(civ[k]) + float(piv[k])) for k in civ if k in piv}
            res, why = atm_from_strikes(both, spot)
            if res is None:
                rec[f"why{tag}"] = why
                continue
            rec[f"iv{tag}"] = round(res[0], 6)
            rec[f"k{tag}"] = [res[1], res[2]]
        out[n] = rec
    return out


def _sig(root, day):
    mo = read_marker(opt_marker(root, day, W_LAST))
    ms = read_marker(stock_path(root, day))
    return [len(mo.get("asked") or []), mo.get("rows"), len(ms.get("asked") or []), ms.get("rows")]


def day_result(root, day, names, cache=True):
    """day_ivs for one day from the cached files, with a per-day JSON cache rebuilt when the files change."""
    names = sorted(set(names))
    cf = Path(root) / R10 / "div" / f"{day.isoformat()}.json"
    sig = _sig(root, day)
    if cache and cf.exists():
        try:
            j = json.loads(cf.read_text())
            if j.get("sig") == sig and set(names) <= set(j.get("rows", {})):
                return {n: j["rows"][n] for n in names}
        except (OSError, ValueError):
            pass
    res = day_ivs(day, read_opt(root, day, W_LAST), read_frame(stock_path(root, day)), names)
    if cache and (sig[0] or sig[2]):
        cf.parent.mkdir(parents=True, exist_ok=True)
        tmp = cf.with_suffix(".tmp")
        tmp.write_text(json.dumps({"sig": sig, "rows": res}))
        tmp.replace(cf)
    return res


# ---------------------------------------------------------------- the table and the 5-session mean
class IVTable:
    """30-day and 90-day ATM IV on the DEV session grid: arrays (days, names), NaN where none."""

    def __init__(self, days, names):
        self.days = list(days)
        self.names = list(names)
        self.pos = {d: k for k, d in enumerate(self.days)}
        self.col = {n: j for j, n in enumerate(self.names)}
        T, N = len(self.days), len(self.names)
        self.iv30, self.iv90, self.spot = np.full((T, N), np.nan), np.full((T, N), np.nan), np.full((T, N), np.nan)
        self.exp30, self.exp90 = {}, {}
        self.why = defaultdict(int)
        self._m = {}

    def set(self, day, name, rec):
        t, j = self.pos.get(day), self.col.get(name)
        if t is None or j is None:
            return
        for k in ("iv30", "iv90", "spot"):
            v = rec.get(k)
            getattr(self, k)[t, j] = np.nan if v is None else float(v)
        if rec.get("exp30"):
            self.exp30[(t, j)] = date.fromisoformat(rec["exp30"])
        if rec.get("exp90"):
            self.exp90[(t, j)] = date.fromisoformat(rec["exp90"])
        for tag in ("30", "90"):
            if rec.get(f"iv{tag}") is None and rec.get(f"why{tag}"):
                self.why[f"{tag}-day: {rec[f'why{tag}']}"] += 1
        self._m.clear()

    @classmethod
    def build(cls, root, days, names_by_day, log=None, cache=True):
        """names_by_day: {day: [names]} (the universe of that day)."""
        allnames = sorted({n for v in names_by_day.values() for n in v})
        tab = cls(days, allnames)
        for k, d in enumerate(tab.days):
            names = names_by_day.get(d) or []
            if not names:
                continue
            if not opt_marker(root, d, W_LAST).exists() and not marker_path(stock_path(root, d)).exists():
                tab.why["no D-IV files for the day (pull stage needs)"] += len(names)
                continue
            for n, rec in day_result(root, d, names, cache).items():
                tab.set(d, n, rec)
            if log and k and k % 50 == 0:
                log(f"  D-IV: {k}/{len(tab.days)} days read")
        return tab

    def mean5(self, which="iv30"):
        """(T, N) mean of the last 5 sessions t-4..t; NaN unless all 5 have an IV."""
        if which in self._m:
            return self._m[which]
        X = getattr(self, which)
        T = X.shape[0]
        out = np.full(X.shape, np.nan)
        if T >= MEAN_N:
            fin = np.isfinite(X)
            cs = np.concatenate([np.zeros((1, X.shape[1])), np.cumsum(np.where(fin, X, 0.0), axis=0)])
            cn = np.concatenate([np.zeros((1, X.shape[1]), int), np.cumsum(fin, axis=0)])
            s = cs[MEAN_N:] - cs[:-MEAN_N]
            n = cn[MEAN_N:] - cn[:-MEAN_N]
            with np.errstate(invalid="ignore"):
                out[MEAN_N - 1:] = np.where(n == MEAN_N, s / MEAN_N, np.nan)
        self._m[which] = out
        return out

    def prior(self, which, day):
        """The 5-session mean through the session before `day` (data through the prior close), per name; NaN row if none."""
        t = self.pos.get(day)
        if t is None or t == 0:
            return np.full(len(self.names), np.nan)
        return self.mean5(which)[t - 1]

    def rows(self):
        """One row per name-day with an IV: the day's IVs, their 5-session means through that day, expiries and spot."""
        out = []
        m30, m90 = self.mean5("iv30"), self.mean5("iv90")
        for t, d in enumerate(self.days):
            for j, n in enumerate(self.names):
                if np.isfinite(self.iv30[t, j]) or np.isfinite(self.iv90[t, j]):
                    out.append({"day": d.isoformat(), "symbol": n, "iv30": _r(self.iv30[t, j]), "iv90": _r(self.iv90[t, j]),
                                "iv30_mean5": _r(m30[t, j]), "iv90_mean5": _r(m90[t, j]),
                                "exp30": (self.exp30.get((t, j)) or "") and self.exp30[(t, j)].isoformat(),
                                "exp90": (self.exp90.get((t, j)) or "") and self.exp90[(t, j)].isoformat(),
                                "spot": _r(self.spot[t, j], 4), "label": LABEL})
        return out


def _r(x, n=6):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


# ---------------------------------------------------------------- realized vol (segment-bound) and the coverage report
def realized_vol(closes, segs, n_returns, span_locked=False):
    """(T,) annualized sample std of the last n_returns daily log returns through each bar, on one name's bars.
    closes: (T,) split-adjusted closes on the session grid (NaN = no bar); segs: (T,) segment ids. span_locked=False: the
    window must lie inside one segment (the panel rule). span_locked=True: the last n_returns + 1 closes on file, the
    return that jumps a locked gap left out (Amendment 16's RV252)."""
    c = np.asarray(closes, float)
    segs = np.asarray(segs)
    T = len(c)
    out = np.full(T, np.nan)
    ix = np.flatnonzero(np.isfinite(c) & (c > 0))
    if len(ix) <= n_returns:
        return out
    r = np.log(c[ix[1:]] / c[ix[:-1]])
    valid = segs[ix[1:]] == segs[ix[:-1]]
    rr = np.where(valid, r, 0.0)
    cs = np.concatenate([[0.0], np.cumsum(rr)])
    cq = np.concatenate([[0.0], np.cumsum(rr * rr)])
    cn = np.concatenate([[0], np.cumsum(valid.astype(int))])
    q = np.arange(n_returns, len(ix))
    a = q - n_returns                                        # returns a .. q-1 end at bars ix[a+1] .. ix[q]
    n = cn[q] - cn[a]
    s, sq = cs[q] - cs[a], cq[q] - cq[a]
    ok = n >= 2
    if not span_locked:
        ok &= (segs[ix[a]] == segs[ix[q]]) & (n == n_returns)
    with np.errstate(invalid="ignore", divide="ignore"):
        var = (sq - s * s / np.maximum(n, 1)) / np.maximum(n - 1, 1)
        v = np.sqrt(np.maximum(var, 0.0) * 252.0)
    out[ix[q[ok]]] = v[ok]
    return out


def coverage(tab, names_by_day, rv20=None):
    """Share of name-days with an IV and each name's median IV vs its median 20-day realized vol (information).
    rv20: {name: (T,) array on tab.days} or None."""
    nd = n30 = n90 = nb = 0
    per = defaultdict(lambda: {"days": 0, "iv30": [], "iv90": [], "rv20": []})
    for t, d in enumerate(tab.days):
        for n in names_by_day.get(d) or []:
            j = tab.col.get(n)
            nd += 1
            per[n]["days"] += 1
            if j is None:
                continue
            a, b = tab.iv30[t, j], tab.iv90[t, j]
            n30 += bool(np.isfinite(a))
            n90 += bool(np.isfinite(b))
            nb += bool(np.isfinite(a) and np.isfinite(b))
            if np.isfinite(a):
                per[n]["iv30"].append(float(a))
                rv = (rv20 or {}).get(n)
                if rv is not None and np.isfinite(rv[t]):
                    per[n]["rv20"].append(float(rv[t]))
            if np.isfinite(b):
                per[n]["iv90"].append(float(b))
    names = {}
    for n, v in sorted(per.items()):
        m30 = float(np.median(v["iv30"])) if v["iv30"] else None
        mr = float(np.median(v["rv20"])) if v["rv20"] else None
        names[n] = {"days": v["days"], "days_iv30": len(v["iv30"]), "days_iv90": len(v["iv90"]),
                    "share_iv30": round(len(v["iv30"]) / v["days"], 3) if v["days"] else None,
                    "median_iv30": None if m30 is None else round(m30, 4),
                    "median_iv90": round(float(np.median(v["iv90"])), 4) if v["iv90"] else None,
                    "median_rv20": None if mr is None else round(mr, 4),
                    "iv30_over_rv20": round(m30 / mr, 3) if m30 is not None and mr else None}
    ratios = [x["iv30_over_rv20"] for x in names.values() if x["iv30_over_rv20"] is not None]
    return {"name_days": nd, "with_iv30": n30, "with_iv90": n90, "with_both": nb,
            "share_iv30": round(n30 / nd, 4) if nd else None, "share_iv90": round(n90 / nd, 4) if nd else None,
            "share_both": round(nb / nd, 4) if nd else None, "names": names,
            "median_iv_over_rv20": round(float(np.median(ratios)), 3) if ratios else None,
            "why_missing": dict(sorted(tab.why.items(), key=lambda kv: -kv[1])), "label": LABEL}


# ---------------------------------------------------------------- the pull's D-IV provider
def plan_day(ctx, day):
    """D-IV's missing OCC symbols on `day` ([] when finished, None when the day's stock15 file is not pulled yet). Names
    already finished are remembered in ctx.cache; a finished day is marked done (ctx.mark_done) so later runs skip it."""
    if ctx.is_done(day, "div"):
        return []
    sm = ctx.stock_minutes(day)
    if sm is None:
        return None
    fin = ctx.cache.setdefault("div_finished", {}).setdefault(day, set())
    asked, printed = ctx.asked(day, W_LAST), ctx.printed(day, W_LAST)
    etf = set(U.U_ETF)
    syms = []
    for n in ctx.universe(day):
        if n in fin:
            continue
        s = plan_name(n, day, sm.get(n), asked, printed, etf=n in etf)
        if s:
            syms += s
        else:
            fin.add(n)
    if not syms:
        ctx.mark_done(day, "div")
    return syms


def needed_option_contracts(ctx):
    """D-IV's provider for tools/sprint_pull10.py: [Need] of the 15:45-16:00 option bars still missing, phase by phase.
    ctx: days (DEV sessions in scope), universe(day) -> names, stock_minutes(day) -> {name: {minute: close}} or None,
    asked(day, window), printed(day, window), priority(day), cache (dict), is_done(day, tag), mark_done(day, tag)."""
    out = []
    for d in ctx.days:
        syms = plan_day(ctx, d)
        if syms:
            out.append(need(d, W_LAST, syms, "div", ctx.priority(d)))
    return out


def div_done(ctx, day):
    """True when D-IV needs nothing more on `day`."""
    return plan_day(ctx, day) == []
