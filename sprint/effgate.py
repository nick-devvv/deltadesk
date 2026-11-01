"""sprint/effgate.py - Part E, a pre-open predicted-efficiency gate (SPRINT_PLAN Amendment 14, part of round 9; pre-registered
2026-11-01 before any Part E code or run). Research only: it reads cached stock bars, VIXY daily closes and trade lists and never
trades. Every number is a BACKTEST: shares on real Alpaca bars, FIN-H on 2018-01..2024-01 MODELED (run 7), DEV REAL.

Target (per symbol and session). ER = |close(15:59) - open(09:30)| / the sum of |1-minute close-to-close moves| over regular
hours. The label is 1 when the day's ER is in the top tercile of the training window's days, per symbol.

Inputs, all known before 09:30 of day t (each from sessions before t only; day t's bars and later ones are never read):
  e_prev_er          the prior session's ER
  e_er5              the mean ER of the prior 5 sessions
  e_prev_co          the prior session's close vs its open, % (stands in for |gap|, which is not known before the open)
  e_prev_range_atr   the prior session's range (high - low) / ATR(14) through the prior session
  e_atr14_60         ATR(14) / ATR(60), both through the prior session
  e_ret1, e_ret5, e_ret20   1-, 5- and 20-session returns to the prior close, %
  e_vixy_pctl        VIXY's prior close percentile among 252 sessions (data.percentile_rank)
  e_vixy_chg1        VIXY's 1-day change at the prior close, % (features.vixy_prior)
  e_vixy_z20         VIXY's prior close, z vs the 20 closes before it (features.vixy_prior)
  e_prev_vwap_dist   the prior session's (close - VWAP) at its close / ATR(14) known before that session (the desk's f_vwap_dist
                     form, unsigned)
  e_prev_last_hour   the prior session's last-hour return, %: its close / the close 60 one-minute bars before its last bar - 1
  e_weekday          0 = Monday ... 4 = Friday
  e_event            FOMC/CPI day from sprint/events (1 / 0; empty where the calendar doesn't cover the date, as f_event)
  e_top5             the count of the prior 5 sessions with ER in the top tercile (the refit's per-symbol cut)

Model. sprint/learn's preprocessing (_prep_fit / _prep_apply: median fill, standardize, all-empty columns dropped) and its
fit (fit_logit: L2 lambda 1, class-balanced, Newton), on rows = (symbol, session), pooled over SPY, QQQ and IWM. Walk-forward:
refit at each calendar month m on all earlier sessions (every row dated before m's first day whose ER is known), only when they
span at least 24 calendar months; out of sample from 2018-01. Gate: skip (symbol, day) when its predicted P(top-tercile ER) is
in the bottom tercile of that refit's training predictions: p <= numpy.quantile(training predictions, 1/3) (round 8 B2's
tercile convention).

Applied, unchanged, to FIN-H (run 7's factory trades: 11:00 calls with f_rvol >= 1.06), NB-VOL (round 8's noise_sh_vol share
trades) and Part S's chosen cells (test half 2025-07-01..2026-06-30 only). A trade is skipped when the gate skips its
(symbol, day); a trade whose (symbol, day) has no prediction is kept and counted.

Pass, per strategy, on 2018-01..2024-01 (MODELED options / real shares) and on DEV 2024-08..2026-06 (REAL), all of:
  1. the gated expectancy (mean P/L per trade) above the ungated;
  2. the gated total above the 95th percentile (numpy, linear) of 200 random whole-day skips of the same count (seeds 31-230);
  3. gated PF 2x > 1.0.
Information: months green, max drawdown, the total without the best day, and the $3,000 account view (round9.account_view).
Trials: 3 (round 9 becomes 206).

Literal readings (each documented; none changes a rule, threshold, seed or count):
  - The amendment lists 16 inputs (2 + 1 + 2 + 3 + 3 + 1 + 1 + 1 + 1 + 1) and calls them "Fifteen". All 16 listed inputs are
    used (dropping one would be a choice made here); the trial count is unchanged.
  - ER: close = the last regular-hours bar's close (15:59; 12:59 on an early close), open = the first regular-hours bar's open
    (09:30 when it printed); the denominator sums |close-to-close| over the session's printed bars in order (a missing minute
    joins its neighbours). A session with fewer than 2 printed bars or no movement has no ER (no label, empty ER inputs).
  - Top tercile = ER >= numpy.quantile(that symbol's training ERs, 2/3). The same cut counts e_top5 (so e_top5 is recomputed at
    each refit, from ERs of sessions before t only); e_top5 and e_er5 are empty without 5 prior sessions with an ER.
  - "Per symbol pooled over SPY, QQQ and IWM": one logit per refit fit on all three symbols' rows; the label's cut is per symbol;
    the gate's cut is over that refit's pooled training predictions.
  - ATRs are Wilder (data._wilder) on the segment's daily regular-hours true ranges (the segment's first day: high - low).
  - Rolling windows never cross L2: features are built per segment (HIST from its 2015-11-01 warm-up, DEV from 2024-08-01, no
    warm-up since July 2024 is L2), and VIXY's closes are cut to the same segment (HIST from 2014-11-01). So DEV's first sessions
    have empty inputs (median-filled by learn's preprocessing), and DEV's VIXY percentile starts after 252 DEV closes.
  - FOMC/CPI: sprint/events covers FOMC 2024-08..2026-12 and CPI 2024-08..2025-12; elsewhere e_event is empty (median-filled;
    an all-empty training column is dropped), exactly as f_event.
  - Training rows start at HIST's first session (2016-01-04): warm-up sessions only feed inputs. The 24-month minimum counts
    calendar months with training rows; with HIST from 2016-01 it first holds for 2018-01, the written out-of-sample start.
  - "Random whole-day skips of the same count": the gate decides per (symbol, day), so the random control skips the same number
    of (symbol, day) units, drawn without replacement from the units the strategy traded in that window (all trades on a drawn
    unit are dropped). Seed s draws with numpy.random.default_rng(s).
  - Part S: only its test half exists, so its pass is judged on 2025-07-01..2026-06-30 alone; each chosen cell (signal x
    contract) is gated and judged; the written trial count (3) is kept.
"""
import math
from collections import defaultdict
from datetime import date

import numpy as np

from . import data, events, learn, periods
from .features import vixy_prior

SYMBOLS = ("SPY", "QQQ", "IWM")
STATIC = ("e_prev_er", "e_er5", "e_prev_co", "e_prev_range_atr", "e_atr14_60", "e_ret1", "e_ret5", "e_ret20", "e_vixy_pctl",
          "e_vixy_chg1", "e_vixy_z20", "e_prev_vwap_dist", "e_prev_last_hour", "e_weekday", "e_event")
FEATURES = STATIC + ("e_top5",)
WRITTEN_FEATURE_COUNT = 15
LAM = 1.0
TRAIN_MONTHS = 24
OOS_FROM = "2018-01"
TOP = 2 / 3
GATE_Q = 1 / 3
SEEDS = tuple(range(31, 231))
N_RANDOM = 200
assert len(SEEDS) == N_RANDOM
HIST_A, HIST_B = periods.HIST[0].isoformat(), periods.HIST[1].isoformat()
DEV_A, DEV_B = periods.DEV[0].isoformat(), periods.DEV[1].isoformat()
E_HIST = ("2018-01-02", HIST_B)                     # 2018-01..2024-01 (the first session of 2018 is 01-02)
S_TEST = ("2025-07-01", "2026-06-30")               # Part S's test half (scalp.TEST)
SEGMENTS = {"HIST": ((periods.HIST_DAILY_FROM, periods.HIST[1]), periods.HIST[0]), "DEV": (periods.DEV, periods.DEV[0])}
LAST_HOUR = 60


def _f(x):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else float(x)


def _r(x, n=2):
    x = _f(x)
    return None if x is None else round(x, n)


def day_of(r):
    return str(r["day"])[:10]


# ---------------------------------------------------------------- one session, from its own bars only
def day_er(grid):
    """ER of one regular session: |last close - first open| / sum |close-to-close| over its printed bars; None if undefined."""
    s = day_summary(grid)
    return None if s is None else s["er"]


def day_summary(grid):
    """{open, high, low, close, er, vwap, last_hour} of one session's (390, 5) O,H,L,C,V regular-hours grid (NaN = no bar).
    None with fewer than 2 printed bars. VWAP = the session's typical-price VWAP at its close (data.Series' formula)."""
    g = np.asarray(grid, float)
    c = g[:, 3]
    idx = np.where(~np.isnan(c))[0]
    if len(idx) < 2:
        return None
    first, last = int(idx[0]), int(idx[-1])
    o = float(g[first, 0]) if not math.isnan(g[first, 0]) else float(c[first])
    cl = float(c[last])
    path = float(np.abs(np.diff(c[idx])).sum())
    er = abs(cl - o) / path if path > 0 else None
    tp = np.nan_to_num((g[:, 1] + g[:, 2] + g[:, 3]) / 3.0)
    vol = np.nan_to_num(g[:, 4])
    vw = float((tp * vol).sum() / vol.sum()) if vol.sum() > 0 else None
    ref = idx[idx <= last - LAST_HOUR]
    lh = (cl / float(c[ref[-1]]) - 1) * 100 if len(ref) and c[ref[-1]] > 0 else None
    return {"open": o, "high": float(np.nanmax(g[:, 1])), "low": float(np.nanmin(g[:, 2])), "close": cl, "er": er, "vwap": vw,
            "last_hour": lh}


# ---------------------------------------------------------------- the pre-open inputs, per segment
def _vixy_segment(vd, seg):
    if vd is None:
        return None
    (a, b), _start = SEGMENTS[seg]
    idx = np.array(list(vd.index))
    keep = (idx >= a) & (idx <= b) if len(idx) else np.zeros(0, bool)
    return vd[keep]


def segment_rows(sym, seg, days, grids, vixy=None, row_from=None):
    """One row per session of one symbol and segment: ER (the label's source) and the 15 static inputs, each from the
    sessions before it only; plus "_p5" (the prior 5 sessions' ERs, for e_top5). days: sorted sessions; grids: {day: grid};
    vixy: VIXY daily closes already cut to the segment."""
    summ = [(d, day_summary(grids[d])) for d in days]
    days = [d for d, s in summ if s is not None]
    S = [s for _d, s in summ if s is not None]
    n = len(days)
    if not n:
        return []
    O, H, L, C = (np.array([s[k] for s in S], float) for k in ("open", "high", "low", "close"))
    ER = np.array([np.nan if s["er"] is None else s["er"] for s in S], float)
    VW = np.array([np.nan if s["vwap"] is None else s["vwap"] for s in S], float)
    LH = np.array([np.nan if s["last_hour"] is None else s["last_hour"] for s in S], float)
    pc = np.concatenate([[np.nan], C[:-1]])
    tr = np.where(np.isnan(pc), H - L, np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc))))
    a14, a60 = data._wilder(tr, 14), data._wilder(tr, 60)
    rows = []
    for k, d in enumerate(days):
        if row_from is not None and d < row_from:
            continue
        p = k - 1
        f = dict.fromkeys(STATIC)
        if k >= 1:
            f["e_prev_er"] = _f(ER[p])
            f["e_prev_co"] = (C[p] / O[p] - 1) * 100 if O[p] > 0 else None
            f["e_prev_range_atr"] = (H[p] - L[p]) / a14[p] if a14[p] > 0 else None
            f["e_atr14_60"] = a14[p] / a60[p] if a60[p] > 0 else None
            f["e_prev_last_hour"] = _f(LH[p])
            if vixy is not None:
                f["e_vixy_pctl"] = data.percentile_rank(vixy, days[p])
                _x, chg, z = vixy_prior(vixy, days[p], 20)
                f["e_vixy_chg1"], f["e_vixy_z20"] = chg, z
        if k >= 2:
            f["e_ret1"] = (C[p] / C[p - 1] - 1) * 100
            f["e_prev_vwap_dist"] = (C[p] - VW[p]) / a14[p - 1] if a14[p - 1] > 0 and not math.isnan(VW[p]) else None
        if k >= 6:
            f["e_ret5"] = (C[p] / C[p - 5] - 1) * 100
        if k >= 21:
            f["e_ret20"] = (C[p] / C[p - 20] - 1) * 100
        p5 = ER[k - 5:k] if k >= 5 else np.full(5, np.nan)
        if k >= 5 and not np.isnan(p5).any():
            f["e_er5"] = float(p5.mean())
        f["e_weekday"] = d.weekday()
        fo, cp = events.is_fomc(d), events.is_cpi(d)
        if fo is not None and cp is not None:
            f["e_event"] = int(bool(fo or cp))
        rows.append({"symbol": sym, "day": d.isoformat(), "seg": seg, "er": _f(ER[k]),
                     **{key: _f(v) for key, v in f.items()}, "_p5": p5.copy()})
    return rows


def build_rows(series, vixy_daily, symbols=SYMBOLS):
    """series: {(segment, symbol): object with .days and .rth (data.Series)}. Rows for HIST sessions from 2016-01-04 and every DEV
    session, sorted by (day, symbol)."""
    out = []
    for seg in ("HIST", "DEV"):
        vx = _vixy_segment(vixy_daily, seg)
        (_a, b), start = SEGMENTS[seg]
        for sym in symbols:
            ser = series.get((seg, sym))
            if ser is None or not ser.days:
                continue
            days = [d for d in ser.days if d <= b]
            out += segment_rows(sym, seg, days, ser.rth, vx, row_from=start)
    return sorted(out, key=lambda r: (r["day"], r["symbol"]))


# ---------------------------------------------------------------- the monthly walk-forward logit
def _arrays(rows):
    return {"day": np.array([r["day"] for r in rows]), "mon": np.array([r["day"][:7] for r in rows]),
            "sym": np.array([r["symbol"] for r in rows]),
            "er": np.array([np.nan if r.get("er") is None else float(r["er"]) for r in rows], float),
            "X": np.array([[np.nan if r.get(k) is None else float(r[k]) for k in STATIC] for r in rows], float).reshape(len(rows), len(STATIC)),
            "P5": np.array([np.asarray(r["_p5"], float) for r in rows], float).reshape(len(rows), 5)}


def _sig(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def fit_month(A, m, lam=LAM):
    """The refit for month m: training = rows dated before m with a known ER. Returns a dict with the per-symbol cuts, the
    label, the fit, the training and test predictions and the gate cut, or None when there is no training row."""
    tr = (A["mon"] < m) & np.isfinite(A["er"])
    te = A["mon"] == m
    if not tr.any():
        return None
    thr = {s: float(np.quantile(A["er"][tr & (A["sym"] == s)], TOP)) for s in sorted(set(A["sym"][tr]))}
    t = np.array([thr.get(s, np.nan) for s in A["sym"]], float)
    with np.errstate(invalid="ignore"):
        y = (A["er"] >= t).astype(float)
        top5 = np.where(np.isnan(A["P5"]).any(axis=1) | np.isnan(t), np.nan, (A["P5"] >= t[:, None]).sum(axis=1))
    X = np.hstack([A["X"], top5[:, None]])
    p = learn._prep_fit(X[tr])
    Ztr, Zte = learn._prep_apply(p, X[tr]), learn._prep_apply(p, X[te])
    if Ztr.shape[1] == 0:
        w, b = np.zeros(0), 0.0
    else:
        w, b = learn.fit_logit(Ztr, y[tr], lam=lam)
    ptr, pte = _sig(Ztr @ w + b), _sig(Zte @ w + b)
    cut = float(np.quantile(ptr, GATE_Q))
    names = [k for k, keep in zip(FEATURES, p["keep"]) if keep]
    return {"month": m, "train": tr, "test": te, "thr": thr, "y": y, "top5": top5, "w": w, "b": float(b), "names": names,
            "ptr": ptr, "pte": pte, "cut": cut, "skip": pte <= cut,
            "train_months": int(len(set(A["mon"][tr])))}


def walk_forward(rows, train_months=TRAIN_MONTHS, oos_from=OOS_FROM, lam=LAM):
    """Monthly refits on all earlier sessions (at least `train_months` calendar months of them), out of sample from `oos_from`.
    Returns {"decisions": [per test row], "gate": {(symbol, day): decision}, "fits": [per refit], ...}."""
    rows = sorted(rows, key=lambda r: (r["day"], r["symbol"]))
    if not rows:
        return {"decisions": [], "gate": {}, "fits": [], "error": "no sessions"}
    A = _arrays(rows)
    dec, fits, last = [], [], None
    for m in sorted(set(A["mon"])):
        if m < oos_from:
            continue
        tr = (A["mon"] < m) & np.isfinite(A["er"])
        if len(set(A["mon"][tr])) < train_months:
            continue
        f = fit_month(A, m, lam)
        if f is None:
            continue
        last = f
        ti = np.where(f["test"])[0]
        for i, pr, sk in zip(ti, f["pte"], f["skip"]):
            r = rows[i]
            dec.append({"symbol": r["symbol"], "day": r["day"], "seg": r["seg"], "month": m, "er": r.get("er"),
                        "label_cut": _r(f["thr"].get(r["symbol"]), 6), "e_top5": _f(f["top5"][i]),
                        "p": round(float(pr), 6), "cut": round(f["cut"], 6), "skip": bool(sk),
                        **{k: r.get(k) for k in STATIC}})
        fits.append({"month": m, "train_rows": int(f["train"].sum()), "train_months": f["train_months"],
                     "label_cuts": {s: round(v, 6) for s, v in f["thr"].items()}, "label_rate": round(float(f["y"][f["train"]].mean()), 4),
                     "gate_cut": round(f["cut"], 6), "test_rows": int(f["test"].sum()), "skipped": int(f["skip"].sum())})
    gate = {(d["symbol"], d["day"]): d for d in dec}
    out = {"decisions": dec, "gate": gate, "fits": fits, "sessions": len(rows),
           "oos_from": fits[0]["month"] if fits else None, "refits": len(fits),
           "last_fit": (sorted(zip(last["names"], np.round(last["w"], 3).tolist()), key=lambda kv: -abs(kv[1]))[:8] if last else None)}
    if not fits:
        months = len(set(A["mon"][np.isfinite(A["er"])]))
        out["error"] = f"no out-of-sample month: a refit needs {train_months} calendar months of earlier sessions (have {months} months in all)"
    return out


# ---------------------------------------------------------------- the gate on a strategy's trades
def unit(r):
    return (str(r["symbol"]), day_of(r))


def _ordered(rows):
    return sorted(rows, key=lambda r: (day_of(r), str(r.get("entry_time") or ""), str(r["symbol"])))


def _pf(p):
    p = np.asarray(p, float)
    if not len(p):
        return None
    lo, w = -p[p < 0].sum(), p[p > 0].sum()
    if lo > 0:
        return round(float(w / lo), 3)
    return math.inf if w > 0 else None


def _pfr(x):
    return -1.0 if x is None else float(x)


def info(rows):
    """Months green (months with a trade), max drawdown (trade order), the total and the total without the best day."""
    rows = _ordered(rows)
    if not rows:
        return {"trades": 0}
    p = np.array([float(r["pnl"]) for r in rows])
    eq = np.cumsum(p)
    dd = float(min(0.0, (eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min()))
    bm, bd = defaultdict(float), defaultdict(float)
    for r, x in zip(rows, p):
        bm[day_of(r)[:7]] += x
        bd[day_of(r)] += x
    best = max(bd.items(), key=lambda kv: kv[1])
    return {"trades": len(rows), "months_green": sum(1 for v in bm.values() if v > 0), "months": len(bm), "max_dd": _r(dd),
            "total": _r(p.sum()), "best_day": best[0], "without_best_day": _r(p.sum() - best[1])}


def stats(rows):
    rows = _ordered(rows)
    p = np.array([float(r["pnl"]) for r in rows])
    p2 = np.array([float(r.get("pnl_2x", r["pnl"])) for r in rows])
    if not len(p):
        return {"trades": 0}
    w, lo = p[p > 0], p[p < 0]
    return {"trades": len(p), "win_rate": round(len(w) / len(p), 3), "avg_win": _r(w.mean()) if len(w) else None,
            "avg_loss": _r(lo.mean()) if len(lo) else None, "expectancy": _r(p.mean(), 4), "pf": _pf(p), "pf_2x": _pf(p2),
            "total": _r(p.sum()), "total_2x": _r(p2.sum())}


def random_skips(rows, n_skip, seeds=SEEDS):
    """Totals of `rows` after skipping n_skip random (symbol, day) units of the units they trade, one draw per seed
    (numpy.random.default_rng(seed), without replacement). Returns (totals array, number of units)."""
    units = sorted({unit(r) for r in rows})
    pos = {u: k for k, u in enumerate(units)}
    ut = np.zeros(len(units))
    for r in rows:
        ut[pos[unit(r)]] += float(r["pnl"])
    total = float(ut.sum())
    if n_skip <= 0 or not units:
        return np.full(len(seeds), total), len(units)
    k = min(int(n_skip), len(units))
    return np.array([total - float(ut[np.random.default_rng(s).choice(len(units), k, replace=False)].sum()) for s in seeds]), len(units)


def gate_window(rows, gate, a, b, seeds=SEEDS):
    """The pass bar on one window [a, b]: ungated vs gated (trades on gate-skipped (symbol, day) units dropped), the random
    whole-day skips of the same count, PF 2x, and the information readouts."""
    sel = _ordered([r for r in rows if a <= day_of(r) <= b])
    out = {"window": f"{a}..{b}", "trades": len(sel)}
    if not sel:
        out.update(checks=[("trades in the window", False)], pass_=False, ungated={"trades": 0}, gated={"trades": 0})
        return out
    units = sorted({unit(r) for r in sel})
    skip_u = {u for u in units if gate.get(u, {}).get("skip")}
    no_pred = sum(1 for u in units if u not in gate)
    kept = [r for r in sel if unit(r) not in skip_u]
    ug, gt = stats(sel), stats(kept)
    e_u = float(np.mean([float(r["pnl"]) for r in sel]))
    e_g = float(np.mean([float(r["pnl"]) for r in kept])) if kept else None
    tot_g = float(sum(float(r["pnl"]) for r in kept))
    rand, n_units = random_skips(sel, len(skip_u), seeds)
    p95 = float(np.percentile(rand, 95))
    pf2 = gt.get("pf_2x")
    checks = [(f"gated expectancy above the ungated ({_r(e_g, 4)} vs {_r(e_u, 4)})", e_g is not None and e_g > e_u),
              (f"gated total above the 95th percentile of {len(seeds)} random whole-day skips of the same count "
               f"({_r(tot_g)} vs {_r(p95)}; {len(skip_u)} of {n_units} symbol-days skipped)", tot_g > p95),
              (f"gated PF 2x > 1.0 ({pf2})", _pfr(pf2) > 1.0)]
    out.update(units=n_units, skipped_units=len(skip_u), skipped_trades=len(sel) - len(kept), no_prediction_units=no_pred,
               ungated=ug, gated=gt, random={"p95": _r(p95), "mean": _r(rand.mean()), "p_at_or_above": round(float((rand >= tot_g - 1e-9).mean()), 4),
                                             "seeds": f"{seeds[0]}-{seeds[-1]}" if len(seeds) else None},
               info={"ungated": info(sel), "gated": info(kept)}, checks=checks, pass_=all(ok for _, ok in checks),
               _kept=kept, _sel=sel)
    return out


def evaluate(name, rows, gate, windows, seeds=SEEDS):
    """windows: [(key, a, b, price label)]. The strategy passes when every window passes."""
    res = {"strategy": name, "windows": {}}
    for key, a, b, lab in windows:
        w = gate_window(rows, gate, a, b, seeds)
        w["prices"] = lab
        res["windows"][key] = w
    res["pass"] = bool(res["windows"]) and all(w["pass_"] for w in res["windows"].values())
    return res


def decision_rows(wf):
    """The gate decisions as flat rows (for the Part E file)."""
    return [{k: v for k, v in d.items()} for d in wf.get("decisions", [])]
