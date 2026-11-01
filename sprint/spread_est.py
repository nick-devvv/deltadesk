"""sprint/spread_est.py - Addendum 16.1's ESTIMATED-SPREAD: option half-spreads estimated from 1-minute trade bars with the
Abdi & Ranaldo (2017) close-high-low estimator, calibrated on the desk's measured SPY/QQQ chains (SPRINT_PLAN Addendum 16.1,
written after the round 10 build and before any round 10 run or result). Research only: reads cached bars and logged chains;
no network, no orders. The cost input for V1, V2, V2-s and the V3/V4 option twins (sprint/r10swing.py); not sprint/spread.py.

As written (Addendum 16.1):
  Estimate   each option contract's half-spread from its own 1-minute trade bars, on consecutive minutes that both have
             trades, inside the bars the round 10 pull fetches. Pool per symbol, per calendar month and per premium bucket
             (sprint/spread.py's buckets), take the median; floor $0.005. Fewer than 5 minute pairs in a pool: the 10% MODELED
             default, labeled.
  Calibrate  on the DEV days where data/chains holds measured SPY/QQQ spreads, the same estimator on the same contracts and
             the same minutes; the median ratio of measured to estimated half-spread, clipped to 0.5-3.0, scales every
             estimate. Fewer than 200 matched contract-days: a ratio of 1, labeled.
  Label      "ESTIMATED-SPREAD".

Builder's reading:
  S1  The estimator, per pair of bars t, t+1 of one contract stamped in consecutive minutes of one day (each bar exists only
      when the contract traded in that minute): in logs, c = ln close_t, eta_t = (ln high_t + ln low_t) / 2, eta_t+1 likewise;
      the relative full spread s = sqrt(max(4 (c - eta_t)(c - eta_t+1), 0)) (Abdi & Ranaldo's two-period estimate, negative
      products set to 0 as in the paper); half-spread in dollars = s / 2 x exp(eta_t) (the bar's geometric mid-range). The
      pair belongs to bar t's day, minute and premium bucket (sprint/spread.py's _pb on exp(eta_t)).
  S2  "Symbol" = the option's underlying (its OCC root): a single contract rarely has 5 pairs. "Inside the bars the round 10
      pull fetches" = every window file under data/alpaca/r10/opt/ on DEV days; contracts expiring on the bar's own day (0DTE:
      only the calibration provider fetches those) are left out of the pools.
  S3  A minute with one trade (high = low = close) gives a product of 0, so its pair estimates 0; such pairs stay in the pool
      (the median is taken over every pair, as written). The pool's median is floored at $0.005, multiplied by the
      calibration ratio, and floored at $0.005 again (no listed half-spread is below half a $0.01 tick).
  S4  Fallback (fewer than 5 pairs, or a fill with no day): sprint/spread.py's MODELED default for that name: 10% of premium
      for single stocks (and for ETFs outside SPY/QQQ/IWM/DIA), 2% for SPY/QQQ/IWM/DIA, floor $0.005, labeled
      "MODELED-SPREAD (fallback: fewer than 5 minute pairs)". Every U-ETF name is estimated the same way as a single stock:
      the addendum judges V1, V2, V2-s and the twins at 100% of the ESTIMATED-SPREAD, and those include ETF positions.
  S5  Calibration: chain files data/chains/<day>.csv(.gz) dated inside DEV only (a file dated in L1/L2 is never opened);
      rows of SPY/QQQ (a leading "$" dropped) with expiry = that day (0DTE), bid > 0 and ask > bid, logged 09:30-15:58 (minute
      m = the logged minute); measured half-spread = (ask - bid) / 2. The matching estimate is the pair (m, m+1) of the same
      contract (OCC symbol built from underlying, expiry, type and strike) from the existing 0DTE cache
      (data/alpaca/options/<U>/<day>/bars.csv.gz) or, where that lacks the contract, round 10's 09:30-16:00 file for it
      (tools/sprint_pull10.py's "spread_cal" provider). Per contract-day with at least one matched minute: the median measured
      / max(the median estimate, $0.005); the ratio = the median over contract-days, clipped to 0.5-3.0; fewer than 200
      matched contract-days: 1.0, labeled.
  S6  Pooling is by calendar month, as written, so a fill early in a month uses that month's later bars. This is a cost
      estimate, never a signal: no sort, selection, entry or exit reads it, and a later month never changes an earlier
      month's estimate (tested).
"""
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import ivdata as IV
from . import periods
from . import spread as SP
from .catalyst import occ, occ_root
from .data import parse_occ

LABEL = "ESTIMATED-SPREAD"
FALLBACK = "MODELED-SPREAD (fallback: fewer than 5 minute pairs)"
MIN_PAIRS = 5
MIN_CAL = 200
CLIP = (0.5, 3.0)
FLOOR = SP.TICK_HALF
CAL_UNDERS = ("SPY", "QQQ")
REPO = Path(__file__).resolve().parents[1]
CHAINS = REPO / "data" / "chains"


# ---------------------------------------------------------------- the estimator
def ar_half(c0, h0, l0, h1, l1):
    """Abdi-Ranaldo half-spread in dollars for arrays of bar pairs (t, t+1); NaN where a price is not positive (S1)."""
    c0, h0, l0, h1, l1 = (np.asarray(x, float) for x in (c0, h0, l0, h1, l1))
    ok = (c0 > 0) & (h0 > 0) & (l0 > 0) & (h1 > 0) & (l1 > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        c, e0, e1 = np.log(c0), 0.5 * (np.log(h0) + np.log(l0)), 0.5 * (np.log(h1) + np.log(l1))
        s = np.sqrt(np.maximum(4.0 * (c - e0) * (c - e1), 0.0))
        out = 0.5 * s * np.exp(e0)
    return np.where(ok, out, np.nan)


def pair_estimates(df, day=None):
    """DataFrame (symbol, m, mid, hs) of every consecutive-minute bar pair of each contract in one day's bars (df: symbol,
    ts, h, l, c). m = the first bar's minute after 09:30; mid = exp(eta_t)."""
    cols = ["symbol", "m", "mid", "hs"]
    if df is None or not len(df):
        return pd.DataFrame(columns=cols)
    f = pd.DataFrame({"symbol": df["symbol"].astype(str).to_numpy(), "m": IV.minutes(df), "h": df["h"].to_numpy(float),
                      "l": df["l"].to_numpy(float), "c": df["c"].to_numpy(float)})
    f = f[(f["m"] >= 0) & (f["m"] < 390)].drop_duplicates(["symbol", "m"], keep="last").sort_values(["symbol", "m"], kind="stable")
    if len(f) < 2:
        return pd.DataFrame(columns=cols)
    s, m = f["symbol"].to_numpy(), f["m"].to_numpy()
    nxt = (s[1:] == s[:-1]) & (m[1:] == m[:-1] + 1)
    i = np.flatnonzero(nxt)
    h, lo, c = f["h"].to_numpy(), f["l"].to_numpy(), f["c"].to_numpy()
    hs = ar_half(c[i], h[i], lo[i], h[i + 1], lo[i + 1])
    with np.errstate(invalid="ignore", divide="ignore"):
        mid = np.exp(0.5 * (np.log(h[i]) + np.log(lo[i])))
    out = pd.DataFrame({"symbol": s[i], "m": m[i], "mid": mid, "hs": hs})
    return out[np.isfinite(out["hs"]) & np.isfinite(out["mid"])].reset_index(drop=True)


def _month(d):
    return f"{d.year:04d}-{d.month:02d}"


def pool_pairs(pairs_by_day):
    """{(OCC root, "YYYY-MM", premium bucket): (median half-spread, pairs)} from {day: pair_estimates frame} (S2)."""
    acc = defaultdict(list)
    for d, pr in pairs_by_day.items():
        if pr is None or not len(pr):
            continue
        meta = [parse_occ(x) for x in pr["symbol"]]
        keep = np.array([mm is not None and mm["expiry"] != d for mm in meta])
        if not keep.any():
            continue
        p = pr[keep]
        roots = [mm["root"] for mm, k in zip(meta, keep) if k]
        pbs = [SP._pb(x) for x in p["mid"]]
        mo = _month(d)
        for r, b, v in zip(roots, pbs, p["hs"].to_numpy(float)):
            acc[(r, mo, b)].append(v)
    return {k: (float(np.median(v)), len(v)) for k, v in acc.items()}


def r10_pairs(root, days, log=None):
    """{day: pair_estimates of every round-10 window file of that day} (S2)."""
    out = {}
    for k, d in enumerate(days):
        frames = []
        folder = IV.opt_dir(root, d)
        if not folder.exists() or periods.overlaps(d, d):
            continue
        for wk in sorted({p.name.split(".p")[0] for p in folder.glob("*.p*.csv.gz")}):
            a, b = wk.split("-")
            df = IV.read_opt(root, d, (f"{a[:2]}:{a[2:]}", f"{b[:2]}:{b[2:]}"))
            if df is not None and len(df):
                frames.append(pair_estimates(df, d))
        if frames:
            out[d] = pd.concat(frames, ignore_index=True)
        if log and k and k % 100 == 0:
            log(f"  ESTIMATED-SPREAD: {k}/{len(days)} days of round-10 bars read")
    return out


# ---------------------------------------------------------------- the model used for fills
class SpreadEst:
    """half_spread(under, px, minute, day) -> (dollars, label): the calibrated ESTIMATED-SPREAD of the pool (under, the
    fill day's month, the premium bucket of px), else spread.py's MODELED default (S3, S4)."""

    estimated = True

    def __init__(self, pools=None, ratio=1.0, cal=None):
        self.pools = dict(pools or {})
        self.ratio = float(ratio)
        self.cal = cal or {"ratio": self.ratio, "label": "ratio 1 (no calibration run)"}
        self._default = SP.SpreadModel()
        self.used = defaultdict(int)

    def half_spread(self, under, px, minute=None, day=None):
        px = max(float(px), 0.0)
        if day is not None:
            p = self.pools.get((occ_root(under), _month(day), SP._pb(px)))
            if p is not None and p[1] >= MIN_PAIRS:
                self.used[LABEL] += 1
                return max(self.ratio * max(p[0], FLOOR), FLOOR), LABEL
        self.used[FALLBACK] += 1
        return self._default.half_spread(under, px, None)[0], FALLBACK

    def describe(self):
        n_ok = sum(1 for v in self.pools.values() if v[1] >= MIN_PAIRS)
        return (f"{LABEL}: Abdi-Ranaldo half-spread from 1-minute trade bars, median per underlying / month / premium bucket "
                f"({n_ok} of {len(self.pools)} pools with at least {MIN_PAIRS} minute pairs), floor ${FLOOR}, x calibration ratio "
                f"{self.ratio:.3f} ({self.cal.get('label')}); fallback {FALLBACK}: 10% of premium (2% SPY/QQQ/IWM/DIA)")

    def summary(self):
        n = [v[1] for v in self.pools.values()]
        med = [v[0] for v in self.pools.values() if v[1] >= MIN_PAIRS]
        return {"label": LABEL, "pools": len(self.pools), "pools_with_5_pairs": sum(1 for x in n if x >= MIN_PAIRS),
                "pairs": int(sum(n)), "median_pool_half_spread": round(float(np.median(med)), 4) if med else None,
                "calibration": self.cal, "fills": dict(self.used)}


# ---------------------------------------------------------------- calibration on the measured chains (S5)
def chain_files(chains_dir, days=None):
    """{day: path} of chain files dated inside DEV (never L1/L2), optionally only `days`."""
    folder = Path(chains_dir)
    out = {}
    if not folder.exists():
        return out
    want = set(days) if days is not None else None
    for p in sorted(folder.glob("*.csv*")):
        try:
            d = date.fromisoformat(p.name[:10])
        except ValueError:
            continue
        if periods.overlaps(d, d) or not (IV.DEV_A <= d <= IV.DEV_B) or (want is not None and d not in want):
            continue
        if p.suffix == ".csv" and (folder / (p.name + ".gz")).exists():
            continue
        out[d] = p
    return out


def chain_rows(path, day):
    """DataFrame (symbol, m, hs_meas) of one chain file's usable SPY/QQQ 0DTE rows (S5)."""
    cols = ["symbol", "m", "hs_meas"]
    try:
        df = pd.read_csv(path, compression="gzip" if str(path).endswith(".gz") else None, dtype=str)
    except (OSError, ValueError, EOFError):
        return pd.DataFrame(columns=cols)
    if not len(df):
        return pd.DataFrame(columns=cols)
    u = df["underlying"].astype(str).str.lstrip("$")
    ok = u.isin(CAL_UNDERS) & (df["expiry"].astype(str).str.slice(0, 10) == day.isoformat())
    df, u = df[ok], u[ok]
    if not len(df):
        return pd.DataFrame(columns=cols)
    bid, ask = pd.to_numeric(df["bid"], errors="coerce"), pd.to_numeric(df["ask"], errors="coerce")
    t = df["logged_at"].astype(str)
    m = pd.to_numeric(t.str.slice(11, 13), errors="coerce") * 60 + pd.to_numeric(t.str.slice(14, 16), errors="coerce") - 570
    k = pd.to_numeric(df["strike"], errors="coerce")
    rt = df["type"].astype(str).str.upper().str.slice(0, 1)
    good = (bid > 0) & (ask > bid) & (m >= 0) & (m < 389) & k.notna() & rt.isin(["C", "P"])
    out = pd.DataFrame({"symbol": [occ(a, day, r, float(x)) for a, r, x in zip(u[good], rt[good], k[good])],
                        "m": m[good].astype(int).to_numpy(), "hs_meas": ((ask - bid) / 2)[good].to_numpy(float)})
    return out.groupby(["symbol", "m"], as_index=False)["hs_meas"].median()


def cal_bars(root, day, under):
    """The day's 0DTE bars of one underlying: the existing cache plus round 10's 09:30-16:00 file."""
    frames = []
    f = Path(root) / "options" / under / day.isoformat() / "bars.csv.gz"
    if f.exists():
        try:
            frames.append(pd.read_csv(f, compression="gzip"))
        except (OSError, ValueError, EOFError):
            pass
    r = IV.read_opt(root, day, IV.W_DAY)
    if r is not None and len(r):
        frames.append(r[r["symbol"].astype(str).str.match(rf"^{under}\d{{6}}[CP]\d{{8}}$")])
    frames = [x for x in frames if x is not None and len(x)]
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    return df.drop_duplicates(["symbol", "ts"]).reset_index(drop=True)


def calibrate(root, chains_dir=CHAINS, days=None, log=None):
    """The calibration ratio and its readout (S5)."""
    ratios, n_rows, n_days = [], 0, 0
    for d, path in sorted(chain_files(chains_dir, days).items()):
        rows = chain_rows(path, d)
        if not len(rows):
            continue
        n_days += 1
        n_rows += len(rows)
        for u in CAL_UNDERS:
            sub = rows[rows["symbol"].str.match(rf"^{u}\d{{6}}[CP]\d{{8}}$")]
            if not len(sub):
                continue
            pr = pair_estimates(cal_bars(root, d, u), d)
            if not len(pr):
                continue
            j = sub.merge(pr[["symbol", "m", "hs"]], on=["symbol", "m"], how="inner")
            for _s, g in j.groupby("symbol"):
                est = max(float(np.median(g["hs"])), FLOOR)
                ratios.append(float(np.median(g["hs_meas"])) / est)
    info = {"chain_days": n_days, "chain_rows": n_rows, "matched_contract_days": len(ratios)}
    if len(ratios) < MIN_CAL:
        info.update(ratio=1.0, raw_median=round(statistics.median(ratios), 4) if ratios else None,
                    label=f"ratio 1: fewer than {MIN_CAL} matched contract-days ({len(ratios)})")
        return 1.0, info
    raw = float(np.median(ratios))
    r = float(min(max(raw, CLIP[0]), CLIP[1]))
    info.update(ratio=round(r, 4), raw_median=round(raw, 4),
                label=f"median measured / estimated over {len(ratios)} SPY/QQQ contract-days" + (" (clipped)" if r != raw else ""))
    return r, info


def build(root, chains_dir=CHAINS, days=None, log=None):
    """The SpreadEst for a run: pools from round 10's bars on DEV days, the calibration ratio from the chains."""
    days = list(days) if days is not None else IV.dev_days()
    pools = pool_pairs(r10_pairs(root, days, log))
    ratio, cal = calibrate(root, chains_dir, days, log)
    if log:
        log(f"  {LABEL}: {len(pools)} pools; calibration {cal}")
    return SpreadEst(pools, ratio, cal)


def hs_of(model, under, px, minute=None, day=None):
    """(half-spread, label) from an ESTIMATED-SPREAD model (with the fill day) or a sprint/spread.py model."""
    if getattr(model, "estimated", False):
        return model.half_spread(under, px, minute, day=day)
    return model.half_spread(under, px, minute)


# ---------------------------------------------------------------- the pull's calibration provider
def cal_needs(root, chains_dir, days):
    """{day: OCC symbols of usable chain rows that the existing 0DTE cache lacks}."""
    out = {}
    for d, path in sorted(chain_files(chains_dir, days).items()):
        rows = chain_rows(path, d)
        if not len(rows):
            continue
        have = set()
        for u in CAL_UNDERS:
            f = Path(root) / "options" / u / d.isoformat() / "bars.csv.gz"
            if f.exists():
                try:
                    have |= set(pd.read_csv(f, compression="gzip", usecols=["symbol"])["symbol"].astype(str))
                except (OSError, ValueError, EOFError):
                    pass
        miss = sorted(set(rows["symbol"]) - have)
        if miss:
            out[d] = miss
    return out


def needed_option_contracts(ctx):
    """"spread_cal" provider for tools/sprint_pull10.py: whole-session (09:30-16:00) bars of the chain-logged SPY/QQQ 0DTE
    contracts that the existing cache lacks, on DEV days inside the pull's span (S5)."""
    a, b = getattr(ctx, "span", None) or (IV.DEV_A, IV.DEV_B)
    days = [d for d in IV.dev_days() if a <= d <= b]
    chains = getattr(ctx, "chains_dir", None) or CHAINS
    return [IV.need(d, IV.W_DAY, syms, "spread_cal", 1) for d, syms in cal_needs(ctx.root, chains, days).items()]
