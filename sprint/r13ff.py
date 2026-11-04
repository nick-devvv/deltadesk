"""sprint/r13ff.py - round 13: T6's rule (sector momentum with a market trend filter) on 70 untouched years of US
industry returns from the Kenneth R. French Data Library (SPRINT_PLAN "Round 13 pre-registration", written 2026-11-04
before any round-13 code, pull or run; vault note Research/2026-11-04-round13-prereg.md). Research only: reads the cleaned
files tools/sprint_r13.py wrote; no network, no orders. Every number is a BACKTEST on index-style portfolio returns.

Data: daily value-weighted returns of the 10 industry portfolios (NoDur Durbl Manuf Enrgy HiTec Telcm Shops Hlth Utils
  Other), the market (Mkt-RF + RF) and the T-bill (RF), as fractions per session, from 1926-07-01 to 2024-01-31 (later
  rows are dropped while the files are parsed: L2, L1 and after are never stored or used).

Rules (calendar months: the daily file holds Saturday sessions before 1952):
  R13 (the only trial that can pass): at the close of each month's last session, rank the 10 industries by total return
     over the prior 12 calendar months (month-end to month-end). If the market's total-return index at that month end is
     above the mean of its last 10 month-end values (this one included), hold the top 3 at 1/3 each; else T-bills.
     Ties: the higher return, then the file's column order.
  D1 momentum only (diagnostic): the same top 3, always invested.
  D2 trend only (diagnostic): all 10 at 1/10 when the trend filter is on, else T-bills.
  Execution: weights decided at the close of day t are traded at the close of day t+1 and earn returns from day t+2 on.
     Weights are held fixed between month ends. Costs per side on traded weight: 10 bps (pass), 50 bps (stress), charged
     on the trade day. Uninvested weight earns RF.
  Benchmarks (not trials): the market, held; the 10 industries at 1/10 each, held at fixed weights.

Windows: PASS 1927-07-01..1997-12-31; ERAS 1927-07-01..1949, 1950..1973, 1974..1997; SEEN 1998-01-02..2024-01-31
  (information). Annualizing uses each window's own sessions per calendar year.

Pass (R13 only, PASS window, 10 bps; all four): 1 R13's Sharpe over cash above the market's, one-sided p < 0.01 (paired
  circular block bootstrap of the two daily excess series, the same 21-session blocks for both, 10,000 draws,
  default_rng(13); p = share of draws where the centered difference is >= the observed one); 2 max drawdown smaller than the
  market's; 3 Sharpe above the market's in at least 2 of the 3 eras; 4 Sharpe over cash > 0 at 50 bps. Deflated Sharpe
  (report.deflated_sharpe, N = 11,297 + 3 = 11,300, sr_var = the variance of the three trials' PASS Sharpes) and CAPM
  alpha/beta are reported, not pass items.
Luck checks (Addendum 13.1, pass items 5-8 for R13, added before any run): 5 R13's PASS Sharpe above the 95th percentile of
  1,000 versions that pick 3 random industries each month (same trend filter, delay and costs; default_rng(131)); 6 above
  the 95th percentile of 1,000 versions whose month-end trend flags are circularly shifted by a random 12+ months inside
  PASS (default_rng(132)); 7 Sharpe above the market's in at least 95% of 1,000 noisy runs: every rebalance delayed 0-5
  extra sessions at random and 0-20 bps extra cost per side for the run (default_rng(133)); 8 without its 10 best months of
  excess return over cash, R13 keeps at least 50% of the PASS total (sum of monthly excess returns).
Also reported (information; Nick's request, added before any run): each trial and benchmark sized with hindsight so its
  worst PASS-window drop is DD_TARGET (-20%): the multiple k of its excess return over cash, the CAGR at that size and the
  exposure it needs (borrowing beyond 1x pays RF; real margin costs more).
"""
import math
import statistics
from datetime import date

import numpy as np
import pandas as pd

from .report import deflated_sharpe

INDUSTRIES = ("NoDur", "Durbl", "Manuf", "Enrgy", "HiTec", "Telcm", "Shops", "Hlth", "Utils", "Other")
LAST_DAY = date(2024, 1, 31)
WINDOWS = {"PASS": (date(1927, 7, 1), date(1997, 12, 31)), "SEEN": (date(1998, 1, 2), LAST_DAY)}
ERAS = {"1927-1949": (date(1927, 7, 1), date(1949, 12, 31)), "1950-1973": (date(1950, 1, 1), date(1973, 12, 31)),
        "1974-1997": (date(1974, 1, 1), date(1997, 12, 31))}
COSTS = {"10bps": 0.0010, "50bps": 0.0050}
PASS_COST, STRESS_COST = "10bps", "50bps"
TOP_K, MOM_MONTHS, SMA_MONTHS, LAG = 3, 12, 10, 1
ALPHA = 0.01
BOOT_DRAWS, BOOT_BLOCK, BOOT_SEED = 10_000, 21, 13
N_ROUND, N_PRIOR = 3, 11_297
TRIALS = ("R13", "D1_momentum_only", "D2_trend_only")
LABEL = "BACKTEST on Ken French industry portfolio returns (value-weighted, daily)"
DD_TARGET = -0.20
ROB_N, ROB_SEEDS = 1_000, {"picks": 131, "filter": 132, "noise": 133}
NOISE_MAX_DELAY, NOISE_MAX_EXTRA, NOISE_SHARE = 5, 0.0020, 0.95
OUTLIER_TOP, OUTLIER_KEEP, RANDOM_PCT = 10, 0.50, 95


class Data:
    """Aligned daily series. ind: (sessions, 10) fractions; mkt, rf: (sessions,) fractions."""

    def __init__(self, ind, fac):
        ind = ind.copy()
        fac = fac.copy()
        ind.index = pd.DatetimeIndex(ind.index).normalize()
        fac.index = pd.DatetimeIndex(fac.index).normalize()
        missing = [c for c in INDUSTRIES if c not in ind.columns]
        if missing or not {"Mkt-RF", "RF"} <= set(fac.columns):
            raise ValueError(f"missing columns: {missing or ['Mkt-RF/RF']}")
        cut = pd.Timestamp(LAST_DAY)
        j = ind[list(INDUSTRIES)].join(fac[["Mkt-RF", "RF"]], how="inner")
        j = j[j.index <= cut].sort_index()
        j = j[~j.index.duplicated(keep="last")].dropna()
        self.index = j.index
        self.days = [d.date() for d in j.index]
        self.n = len(j)
        self.ind = j[list(INDUSTRIES)].to_numpy(dtype=float, copy=True)
        self.rf = j["RF"].to_numpy(dtype=float, copy=True)
        self.mkt = j["Mkt-RF"].to_numpy(dtype=float, copy=True) + self.rf


def month_end_rows(d):
    """Row numbers of each calendar month's last session (the data's last row counts only if a later month exists)."""
    idx = d.index
    nxt = np.r_[(idx.year[1:] * 12 + idx.month[1:]) != (idx.year[:-1] * 12 + idx.month[:-1]), False]
    return np.flatnonzero(nxt)


def decisions(d):
    """[(row, momentum vector or None, trend bool or None)] at each month end."""
    tri = np.cumprod(1.0 + d.ind, axis=0)
    trm = np.cumprod(1.0 + d.mkt)
    me = month_end_rows(d)
    out = []
    for k, row in enumerate(me):
        mom = tri[row] / tri[me[k - MOM_MONTHS]] - 1.0 if k >= MOM_MONTHS else None
        trend = bool(trm[row] > trm[me[k - SMA_MONTHS + 1:k + 1]].mean()) if k >= SMA_MONTHS - 1 else None
        out.append((int(row), mom, trend))
    return out


def top_k(mom, k=TOP_K):
    order = sorted(range(len(mom)), key=lambda i: (-mom[i], i))
    return order[:k]


def weights(d, kind, dec=None, pick=None, flags=None, delays=None):
    """Target weights (sessions, 10) decided at month-end closes and held until the next month end. For the luck checks:
    pick(mom) replaces the top-3 choice, flags[j] replaces decision j's trend flag, delays[j] moves decision j later by that
    many sessions."""
    dec = decisions(d) if dec is None else dec
    W = np.zeros((d.n, len(INDUSTRIES)))
    cur = np.zeros(len(INDUSTRIES))
    last = 0
    for j, (row, mom, trend) in enumerate(dec):
        if flags is not None and trend is not None:
            trend = bool(flags[j])
        row = min(d.n - 1, row + (int(delays[j]) if delays is not None else 0))
        W[last:row] = cur
        new = np.zeros(len(INDUSTRIES))
        if mom is not None and trend is not None:
            chosen = list(pick(mom)) if pick else top_k(mom)
            if kind == "R13" and trend:
                new[chosen] = 1.0 / TOP_K
            elif kind == "D1_momentum_only":
                new[chosen] = 1.0 / TOP_K
            elif kind == "D2_trend_only" and trend:
                new[:] = 1.0 / len(INDUSTRIES)
        cur = new
        last = row
    W[last:] = cur
    return W


def simulate(d, W, cost, lag=LAG):
    """Daily portfolio returns. Holdings on day t = the weights decided at the close of day t - 1 - lag; the trade that
    changes holdings from day t to day t + 1 happens at the close of day t and pays cost x the traded weight."""
    H = np.zeros_like(W)
    s = lag + 1
    H[s:] = W[:-s]
    port = (H * d.ind).sum(axis=1) + (1.0 - H.sum(axis=1)) * d.rf
    traded = np.r_[np.abs(H[1:] - H[:-1]).sum(axis=1), 0.0]
    port = port - cost * traded
    return port, H


def run_trials(d, cost):
    out = {}
    for name in TRIALS:
        r, H = simulate(d, weights(d, name), cost)
        out[name] = {"r": r, "expo": H.sum(axis=1), "turnover": float(np.abs(np.diff(H, axis=0)).sum())}
    return out


# ------------------------------------------------------------------ statistics
def mask_for(d, a, b):
    return np.array([a <= x <= b for x in d.days])


def per_year(d, mk):
    days = [x for x, m in zip(d.days, mk) if m]
    yrs = (days[-1] - days[0]).days / 365.25
    return len(days) / yrs, yrs


def stats(d, r, mk):
    if mk.sum() < 100:
        return None
    x, rf = r[mk], d.rf[mk]
    spy, yrs = per_year(d, mk)
    ex = x - rf
    sd = float(np.std(ex, ddof=1))
    eq = np.cumprod(1.0 + x)
    return {"sessions": int(mk.sum()), "years": round(yrs, 2), "cagr": float(eq[-1] ** (1.0 / yrs) - 1.0),
            "vol": float(np.std(x, ddof=1) * math.sqrt(spy)), "sharpe": float(ex.mean() / sd * math.sqrt(spy)) if sd > 0 else None,
            "max_dd": float((eq / np.maximum.accumulate(eq) - 1.0).min()), "total": float(eq[-1] - 1.0)}


def sharpe_diff_test(a, b, draws=BOOT_DRAWS, block=BOOT_BLOCK, seed=BOOT_SEED):
    """Paired circular block bootstrap for SR(a) - SR(b) > 0 (per-session Sharpes of two excess series). Returns (one-sided
    p, observed difference, 95% CI of the difference)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    n = len(a)

    def sr(x, axis=None):
        return x.mean(axis=axis) / x.std(axis=axis, ddof=1)

    obs = float(sr(a) - sr(b))
    rng = np.random.default_rng(seed)
    nb = int(math.ceil(n / block))
    diffs = np.empty(draws)
    done, chunk = 0, 200
    while done < draws:
        k = min(chunk, draws - done)
        st = rng.integers(0, n, size=(k, nb))
        idx = ((st[:, :, None] + np.arange(block)[None, None, :]) % n).reshape(k, -1)[:, :n]
        diffs[done:done + k] = sr(a[idx], axis=1) - sr(b[idx], axis=1)
        done += k
    p = float(np.mean(diffs - obs >= obs))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return p, obs, (float(lo), float(hi))


def capm(d, r, mk):
    y = r[mk] - d.rf[mk]
    x = d.mkt[mk] - d.rf[mk]
    beta = float(np.cov(y, x, ddof=1)[0, 1] / np.var(x, ddof=1))
    alpha = float(y.mean() - beta * x.mean())
    spy, _ = per_year(d, mk)
    return {"beta": beta, "alpha_annual": alpha * spy}


def sized_to_dd(d, r, expo, mk, target=DD_TARGET):
    """Hindsight sizing, information only: k such that rf + k x (r - rf) has worst drop `target` inside the window."""
    rf, x, ex = d.rf[mk], r[mk], np.asarray(expo, float)[mk]
    _, yrs = per_year(d, mk)

    def run(k):
        eq = np.cumprod(1.0 + rf + k * (x - rf))
        return float((eq / np.maximum.accumulate(eq) - 1.0).min()), eq

    lo, hi = 0.01, 20.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if run(mid)[0] < target:
            hi = mid
        else:
            lo = mid
    dd, eq = run(lo)
    return {"k": lo, "cagr": float(eq[-1] ** (1.0 / yrs) - 1.0), "max_dd": dd, "max_exposure": float(lo * ex.max())}


def pass_sharpe(d, r, mk):
    ex = r[mk] - d.rf[mk]
    spy, _ = per_year(d, mk)
    return float(ex.mean() / ex.std(ddof=1) * math.sqrt(spy))


def monthly_excess(d, r, mk):
    ex = pd.Series(r[mk] - d.rf[mk], index=d.index[mk])
    return (1.0 + ex).groupby([ex.index.year, ex.index.month]).prod() - 1.0


def luck_checks(d, n=None, cost=None):
    """Pass items 5-8 for R13 (Addendum 13.1)."""
    n = ROB_N if n is None else n
    cost = COSTS[PASS_COST] if cost is None else cost
    pm = mask_for(d, *WINDOWS["PASS"])
    dec = decisions(d)
    base_r = simulate(d, weights(d, "R13", dec), cost)[0]
    base = pass_sharpe(d, base_r, pm)
    mkt = pass_sharpe(d, d.mkt, pm)
    g = np.random.default_rng(ROB_SEEDS["picks"])
    picks = np.array([pass_sharpe(d, simulate(d, weights(d, "R13", dec, pick=lambda mom: g.choice(len(mom), TOP_K, replace=False)), cost)[0], pm)
                      for _ in range(n)])
    flags0 = np.array([bool(t) if t is not None else False for _, _, t in dec])
    live = np.array([t is not None and pm[row] for row, _, t in dec])
    pos = np.flatnonzero(live)
    g = np.random.default_rng(ROB_SEEDS["filter"])
    shifted = []
    for _ in range(n):
        f = flags0.copy()
        f[pos] = np.roll(flags0[pos], int(g.integers(12, max(13, len(pos) - 12))))
        shifted.append(pass_sharpe(d, simulate(d, weights(d, "R13", dec, flags=f), cost)[0], pm))
    shifted = np.array(shifted)
    g = np.random.default_rng(ROB_SEEDS["noise"])
    noisy = np.array([pass_sharpe(d, simulate(d, weights(d, "R13", dec, delays=g.integers(0, NOISE_MAX_DELAY + 1, len(dec))),
                                                cost + g.uniform(0, NOISE_MAX_EXTRA))[0], pm) for _ in range(n)])
    mo = monthly_excess(d, base_r, pm)
    tot = float(mo.sum())
    kept = float((tot - mo.nlargest(OUTLIER_TOP).sum()) / tot) if tot > 0 else None
    return {"sharpe": base, "market_sharpe": mkt, "draws": n,
            "random_picks": {"p95": float(np.percentile(picks, RANDOM_PCT)), "median": float(np.median(picks)), "share_below": float(np.mean(picks < base))},
            "shifted_filter": {"p95": float(np.percentile(shifted, RANDOM_PCT)), "median": float(np.median(shifted)), "share_below": float(np.mean(shifted < base))},
            "noise": {"share_above_market": float(np.mean(noisy > mkt)), "median": float(np.median(noisy)), "worst": float(noisy.min())},
            "outliers": {"kept_without_best_10_months": kept, "months": int(len(mo))}}


def evaluate(d, res_by_cost):
    pm = mask_for(d, *WINDOWS["PASS"])
    out = {"label": LABEL, "alpha": ALPHA, "n_trials_total": N_PRIOR + N_ROUND,
           "data": {"first": d.days[0].isoformat(), "last": d.days[-1].isoformat(), "sessions": d.n},
           "windows": {k: [a.isoformat(), b.isoformat()] for k, (a, b) in {**WINDOWS, **ERAS}.items()},
           "benchmarks": {}, "trials": {}}
    masks = {**{w: mask_for(d, a, b) for w, (a, b) in WINDOWS.items()}, **{e: mask_for(d, a, b) for e, (a, b) in ERAS.items()}}
    ew = d.ind.mean(axis=1)
    for name, r in (("market", d.mkt), ("equal_weight_10", ew)):
        out["benchmarks"][name] = {w: stats(d, r, mk) for w, mk in masks.items()}
        out["benchmarks"][name]["sized_20dd_pass"] = sized_to_dd(d, r, np.ones(d.n), masks["PASS"])
    for name in TRIALS:
        row = {}
        for lvl, res in res_by_cost.items():
            row[lvl] = {w: stats(d, res[name]["r"], mk) for w, mk in masks.items()}
            row[lvl]["turnover_per_year"] = res[name]["turnover"] / max(per_year(d, np.ones(d.n, bool))[1], 1e-9)
        r = res_by_cost[PASS_COST][name]["r"]
        p, diff, ci = sharpe_diff_test(r[pm] - d.rf[pm], d.mkt[pm] - d.rf[pm])
        spy, _ = per_year(d, pm)
        row["sharpe_vs_market"] = {"p_one_sided": p, "diff_annual": diff * math.sqrt(spy),
                                   "ci95_annual": [ci[0] * math.sqrt(spy), ci[1] * math.sqrt(spy)]}
        row["capm_pass"] = capm(d, r, pm)
        row["exposure_mean_pass"] = float(res_by_cost[PASS_COST][name]["expo"][pm].mean())
        row["sized_20dd_pass"] = sized_to_dd(d, r, res_by_cost[PASS_COST][name]["expo"], pm)
        out["trials"][name] = row
    sh = {n: float(np.mean(res_by_cost[PASS_COST][n]["r"][pm] - d.rf[pm]) / np.std(res_by_cost[PASS_COST][n]["r"][pm] - d.rf[pm]))
          for n in TRIALS}
    sr_var = statistics.variance(sh.values())
    for n in TRIALS:
        out["trials"][n]["deflated_sharpe"] = deflated_sharpe(list(res_by_cost[PASS_COST][n]["r"][pm] - d.rf[pm]), N_PRIOR + N_ROUND, sr_var)
    out["sr_var"] = sr_var
    out["luck"] = luck_checks(d)
    out["verdict"] = verdict(out)
    return out


def verdict(ev):
    row = ev["trials"]["R13"]
    mk = ev["benchmarks"]["market"]
    f, m = row[PASS_COST]["PASS"], mk["PASS"]
    eras_won = [e for e in ERAS if row[PASS_COST][e] and mk[e] and (row[PASS_COST][e]["sharpe"] or -9) > (mk[e]["sharpe"] or 9)]
    items = {
        "1 Sharpe above the market's, p < 0.01": row["sharpe_vs_market"]["p_one_sided"] < ALPHA,
        "2 drawdown smaller than the market's": f["max_dd"] > m["max_dd"],
        "3 Sharpe above the market's in 2 of 3 eras": len(eras_won) >= 2,
        "4 Sharpe over cash > 0 at 50 bps": (row[STRESS_COST]["PASS"]["sharpe"] or 0) > 0,
    }
    lk = ev.get("luck")
    if lk:
        items["5 beats 95% of random industry picks"] = lk["sharpe"] > lk["random_picks"]["p95"]
        items["6 beats 95% of shifted trend filters"] = lk["sharpe"] > lk["shifted_filter"]["p95"]
        items["7 above the market's Sharpe in 95% of noisy runs"] = lk["noise"]["share_above_market"] >= NOISE_SHARE
        items["8 keeps 50% without its 10 best months"] = (lk["outliers"]["kept_without_best_10_months"] or 0) >= OUTLIER_KEEP
    ok = all(items.values())
    return {"pass": ok, "items": items, "eras_won": eras_won,
            "why": "all items hold" if ok else "failed: " + ", ".join(k for k, v in items.items() if not v)}


# ------------------------------------------------------------------ report
def _p(x, n=1):
    return "-" if x is None else f"{x * 100:.{n}f}%"


def _f(x, n=2):
    return "-" if x is None else f"{x:.{n}f}"


def luck_lines(ev):
    lk = ev.get("luck")
    if not lk:
        return ["- not run"]
    rp, sf, nz, ol = lk["random_picks"], lk["shifted_filter"], lk["noise"], lk["outliers"]
    return [f"- R13 Sharpe {_f(lk['sharpe'])} (market {_f(lk['market_sharpe'])}), {lk['draws']:,} draws each.",
            f"- Random industry picks: median {_f(rp['median'])}, 95th percentile {_f(rp['p95'])}; R13 beats {_p(rp['share_below'])} of them.",
            f"- Shifted trend filter: median {_f(sf['median'])}, 95th percentile {_f(sf['p95'])}; R13 beats {_p(sf['share_below'])} of them.",
            f"- Noise (delays 0-{NOISE_MAX_DELAY} sessions, 0-{NOISE_MAX_EXTRA * 1e4:.0f} bps extra): above the market's Sharpe in "
            f"{_p(nz['share_above_market'])} of runs; median {_f(nz['median'])}, worst {_f(nz['worst'])}.",
            f"- Without its {OUTLIER_TOP} best months (of {ol['months']}): keeps {_p(ol['kept_without_best_10_months'])} of its excess return."]


def report_md(ev, note=""):
    v = ev["verdict"]
    L = [f"# Round 13 result ({ev['label']})", "",
         f"Pre-registered in SPRINT_PLAN \"Round 13 pre-registration\" (2026-11-04). Pass/fail on PASS {ev['windows']['PASS'][0]}.."
         f"{ev['windows']['PASS'][1]} at 10 bps a side; only R13 can pass. Deflated Sharpe at N = {ev['n_trials_total']:,} is reported, not a pass item.", ""]
    if note:
        L += [note, ""]
    L += [f"## Verdict: R13 {'PASS' if v['pass'] else 'FAIL'}", ""]
    for k, ok in v["items"].items():
        L.append(f"- {'yes' if ok else 'NO'}: {k}")
    sv = ev["trials"]["R13"]["sharpe_vs_market"]
    L += ["", f"Sharpe difference vs the market (annualized): {_f(sv['diff_annual'])}, 95% CI {_f(sv['ci95_annual'][0])} to "
          f"{_f(sv['ci95_annual'][1])}, one-sided p {_f(sv['p_one_sided'], 4)}. Eras where R13 beat the market's Sharpe: "
          f"{', '.join(v['eras_won']) or 'none'}.", "",
          "## Luck checks (items 5-8)", ""] + luck_lines(ev) + ["",
          "## PASS window and eras (10 bps a side)", "", "| Series | Window | Years | CAGR | Sharpe | Max DD |", "|---|---|---|---|---|---|"]
    rows = [(n, ev["trials"][n]["10bps"]) for n in TRIALS] + [(f"benchmark: {k}", b) for k, b in ev["benchmarks"].items()]
    for name, per in rows:
        for w in ("PASS", *ERAS, "SEEN"):
            s = per.get(w)
            if s:
                L.append(f"| {name} | {w} | {s['years']} | {_p(s['cagr'])} | {_f(s['sharpe'])} | {_p(s['max_dd'])} |")
    L += ["", "## Costs, exposure, CAPM and deflated Sharpe (PASS)", "",
          "| Trial | Sharpe at 50 bps | Turnover a year | Mean exposure | Beta | Alpha a year | Deflated Sharpe |", "|---|---|---|---|---|---|---|"]
    for n in TRIALS:
        t = ev["trials"][n]
        L.append(f"| {n} | {_f(t['50bps']['PASS']['sharpe'])} | {_f(t['10bps']['turnover_per_year'])} | {_f(t['exposure_mean_pass'])} | "
                 f"{_f(t['capm_pass']['beta'])} | {_p(t['capm_pass']['alpha_annual'], 2)} | {_f(t['deflated_sharpe'], 4)} |")
    L += ["", "## Sized to the same worst drop (-20% on PASS; hindsight sizing, information only)", "",
          "| Series | Size k | Max exposure | CAGR at that size |", "|---|---|---|---|"]
    for name in TRIALS:
        z = ev["trials"][name]["sized_20dd_pass"]
        L.append(f"| {name} | {_f(z['k'])} | {_f(z['max_exposure'], 1)}x | {_p(z['cagr'])} |")
    for name, b in ev["benchmarks"].items():
        z = b["sized_20dd_pass"]
        L.append(f"| benchmark: {name} | {_f(z['k'])} | {_f(z['max_exposure'], 1)}x | {_p(z['cagr'])} |")
    L += ["", f"Every number above is a {ev['label']}. The portfolios were not tradable funds before the 1990s. Not financial advice; "
          "a pass earns a forward paper ledger for the ETF version (T6) at most."]
    return "\n".join(L) + "\n"
