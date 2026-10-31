"""sprint/learn.py - the desk learning WHEN a strategy works, from its own trades, scored only on trades it hasn't seen.
Pre-registered 2026-10-31 (sprint run 3), before any learner result. Research only: nothing here trades.

Input: one strategy's trades (a run's rows from data/sprint/trades_*.csv.gz, or later the paper journal's trades
stamped with the same entry features, sprint/features.py). Every feature is known at entry.

Walk-forward (no look-ahead): trades are grouped by calendar month. For each month m after the first
`min_train_months` months that have trades, each model is fit on ALL trades from earlier months only (expanding window)
and decides, for every trade in month m, take or skip. Only those out-of-sample (OOS) decisions are scored.
Preprocessing is fit on the training trades only (median fill for missing values, then standardize).

Three pre-registered models (all three count as trials for every strategy they are run on):
  logit    L2 logistic regression (lambda 1.0, class-balanced) on win = pnl > 0; take when P(win) >= 0.5.
  ridge    ridge regression (alpha 10) on pnl winsorized at the training 5th/95th percentiles; take when the prediction > 0.
  buckets  a readable rule table: time of day (before 10:30, 10:30-12:00, 12:00-14:00, 14:00 on) x day type (trend votes
           >= 3 trend, <= 1 chop, else neutral) = 12 cells; skip a cell when its training trades number >= 30 and their
           mean pnl < 0; otherwise take.

Scored on the OOS months only, against the same OOS trades taken without a model ("base"):
  trades, win rate, expectancy, profit factor, total, max drawdown, the same at 2x slippage (pnl_2x), and a random-skip
  control: skip the same NUMBER of OOS trades at random, 200 times (seed 7); the model's total is ranked among them.
PASS (pre-registered): taken trades >= 60, OOS expectancy above base, model total above the 95th percentile of the
random skips, PF at 2x slippage > 1.0. A pass is still in-sample to the DEV period (the trades came from DEV); a model
reaches the locked periods only as part of a frozen finalist.
"""
import math

import numpy as np

from .features import FEATURES, matrix

MODELS = ("logit", "ridge", "buckets")
TOD_EDGES = (60, 150, 270)               # f_minute: 10:30, 12:00, 14:00


def _months(days):
    return [str(d)[:7] for d in days]


def _prep_fit(X):
    med = np.nanmedian(np.where(np.isnan(X).all(axis=0), 0.0, X), axis=0) if len(X) else np.zeros(X.shape[1])
    keep = ~np.isnan(X).all(axis=0)
    Z = np.where(np.isnan(X), med, X)
    mu, sd = Z.mean(axis=0), Z.std(axis=0)
    keep &= sd > 1e-12
    return {"med": med, "mu": mu, "sd": np.where(sd > 1e-12, sd, 1.0), "keep": keep}


def _prep_apply(p, X):
    Z = np.where(np.isnan(X), p["med"], X)
    Z = (Z - p["mu"]) / p["sd"]
    return Z[:, p["keep"]]


def fit_logit(Z, y, lam=1.0, iters=50):
    """L2 logistic regression, class-balanced weights, Newton steps. Returns (w, b)."""
    n, k = Z.shape
    pos = max(1, int(y.sum()))
    neg = max(1, n - pos)
    sw = np.where(y > 0, n / (2.0 * pos), n / (2.0 * neg))
    A = np.hstack([Z, np.ones((n, 1))])
    w = np.zeros(k + 1)
    R = lam * np.eye(k + 1)
    R[-1, -1] = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(A @ w, -30, 30)))
        g = A.T @ (sw * (p - y)) + R @ w
        H = (A * (sw * p * (1 - p))[:, None]).T @ A + R + 1e-9 * np.eye(k + 1)
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w[:-1], w[-1]


def fit_ridge(Z, y, alpha=10.0):
    n, k = Z.shape
    A = np.hstack([Z, np.ones((n, 1))])
    R = alpha * np.eye(k + 1)
    R[-1, -1] = 0.0
    w = np.linalg.solve(A.T @ A + R, A.T @ y)
    return w[:-1], w[-1]


def _cell(minute, votes):
    t = 0 if minute is None or (isinstance(minute, float) and math.isnan(minute)) else int(np.searchsorted(TOD_EDGES, minute, side="right"))
    if votes is None or (isinstance(votes, float) and math.isnan(votes)):
        d = "neutral"
    else:
        d = "trend" if votes >= 3 else "chop" if votes <= 1 else "neutral"
    return (t, d)


TOD_LABELS = ("09:30-10:30", "10:30-12:00", "12:00-14:00", "14:00-close")


def fit_buckets(rows, min_n=30):
    cells = {}
    for r in rows:
        cells.setdefault(_cell(r.get("f_minute"), r.get("f_trend_votes")), []).append(float(r["pnl"]))
    skip = {c for c, v in cells.items() if len(v) >= min_n and np.mean(v) < 0}
    table = {c: (len(v), float(np.mean(v))) for c, v in cells.items()}
    return skip, table


def decide(model, train, test, names=None):
    """take (bool array) for the test rows, from a model fit on the train rows. Rows are dicts with features + pnl."""
    names = names or FEATURES
    if not test:
        return np.zeros(0, bool), None
    if model == "buckets":
        skip, table = fit_buckets(train)
        return np.array([_cell(r.get("f_minute"), r.get("f_trend_votes")) not in skip for r in test]), {"skip": skip, "table": table}
    Xtr, Xte = matrix(train, names), matrix(test, names)
    p = _prep_fit(Xtr)
    Ztr, Zte = _prep_apply(p, Xtr), _prep_apply(p, Xte)
    pnl = np.array([float(r["pnl"]) for r in train])
    if Ztr.shape[1] == 0:
        return np.ones(len(test), bool), None
    if model == "logit":
        w, b = fit_logit(Ztr, (pnl > 0).astype(float))
        prob = 1.0 / (1.0 + np.exp(-np.clip(Zte @ w + b, -30, 30)))
        info = {"coef": dict(zip([n for n, k in zip(names, p["keep"]) if k], np.round(w, 3)))}
        return prob >= 0.5, info
    if model == "ridge":
        lo, hi = np.percentile(pnl, [5, 95])
        w, b = fit_ridge(Ztr, np.clip(pnl, lo, hi))
        info = {"coef": dict(zip([n for n, k in zip(names, p["keep"]) if k], np.round(w, 3)))}
        return (Zte @ w + b) > 0, info
    raise ValueError(model)


def stats(pnl, pnl2=None):
    pnl = np.asarray(pnl, float)
    if not len(pnl):
        return {"trades": 0}
    w, l = pnl[pnl > 0], pnl[pnl <= 0]
    eq = np.cumsum(pnl)
    dd = float((eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min())
    out = {"trades": len(pnl), "win_rate": round(len(w) / len(pnl), 3), "expectancy": round(float(pnl.mean()), 2),
           "total": round(float(pnl.sum()), 2), "pf": round(float(w.sum() / -l.sum()), 3) if l.sum() < 0 else None,
           "max_dd": round(min(dd, 0.0), 2)}
    if pnl2 is not None:
        p2 = np.asarray(pnl2, float)
        l2 = p2[p2 <= 0].sum()
        out["pf_2x"] = round(float(p2[p2 > 0].sum() / -l2), 3) if l2 < 0 else None
        out["total_2x"] = round(float(p2.sum()), 2)
    return out


def walk_forward(rows, min_train_months=6, models=MODELS, n_random=200, seed=7):
    """rows: one strategy's trades (dicts with day, pnl, pnl_2x and the f_* features). Returns the scored result."""
    rows = sorted(rows, key=lambda r: (str(r["day"]), r.get("f_minute") or 0))
    months = sorted(set(_months([r["day"] for r in rows])))
    if len(months) <= min_train_months:
        return {"error": f"need more than {min_train_months} months with trades, have {len(months)}"}
    test_months = months[min_train_months:]
    oos = [r for r in rows if str(r["day"])[:7] in test_months]
    base = stats([r["pnl"] for r in oos], [r.get("pnl_2x", r["pnl"]) for r in oos])
    res = {"months": len(months), "train_months_first": min_train_months, "oos_from": test_months[0], "base": base, "models": {}}
    rng = np.random.default_rng(seed)
    oos_pnl = np.array([float(r["pnl"]) for r in oos])
    for m in models:
        take = np.zeros(len(oos), bool)
        last = None
        k = 0
        for tm in test_months:
            tr = [r for r in rows if str(r["day"])[:7] < tm]
            te_idx = [i for i, r in enumerate(oos) if str(r["day"])[:7] == tm]
            t, info = decide(m, tr, [oos[i] for i in te_idx])
            take[te_idx] = t
            last = info or last
            k += 1
        sel = [r for r, t in zip(oos, take) if t]
        st = stats([r["pnl"] for r in sel], [r.get("pnl_2x", r["pnl"]) for r in sel])
        n_take = int(take.sum())
        rand = np.array([oos_pnl[rng.choice(len(oos), n_take, replace=False)].sum() for _ in range(n_random)]) if 0 < n_take < len(oos) else None
        pct = float((rand < st.get("total", 0)).mean()) if rand is not None else None
        ok = (st.get("trades", 0) >= 60 and st.get("expectancy", -1e9) > base.get("expectancy", 0) and pct is not None and pct >= 0.95
              and (st.get("pf_2x") or 0) > 1.0)
        res["models"][m] = {"taken": st, "skipped": len(oos) - n_take, "random_skip_pctl": None if pct is None else round(pct, 3),
                            "pass": bool(ok), "last_fit": _readable(m, last)}
    return res


def _readable(model, info):
    if not info:
        return None
    if model == "buckets":
        rows = []
        for (t, d), (n, mu) in sorted(info["table"].items()):
            rows.append({"time": TOD_LABELS[t], "day": d, "train_trades": n, "train_exp": round(mu, 2), "skip": (t, d) in info["skip"]})
        return rows
    co = info["coef"]
    return sorted(co.items(), key=lambda kv: -abs(kv[1]))[:8]


def report_md(run_id, res, n_trials=None):
    L = [f"### Learner: {run_id}\n"]
    if "error" in res:
        return L[0] + res["error"] + "\n"
    b = res["base"]
    L.append(f"Walk-forward: models refit each month on earlier months only; out-of-sample from {res['oos_from']} "
             f"({res['months']} months with trades, the first {res['train_months_first']} used only for training). "
             "BACKTEST, DEV, MODELED-SPREAD.\n")
    L.append("| | trades | win % | exp $ | PF | PF 2x | total $ | max DD | skipped | beats random skips | PASS |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    L.append(f"| no model (base) | {b['trades']} | {b.get('win_rate', 0) * 100:.1f} | {b.get('expectancy')} | {b.get('pf')} | {b.get('pf_2x')} | "
             f"{b.get('total')} | {b.get('max_dd')} | - | - | - |")
    for m, r in res["models"].items():
        s = r["taken"]
        L.append(f"| {m} | {s.get('trades', 0)} | {(s.get('win_rate') or 0) * 100:.1f} | {s.get('expectancy')} | {s.get('pf')} | "
                 f"{s.get('pf_2x')} | {s.get('total')} | {s.get('max_dd')} | {r['skipped']} | {r['random_skip_pctl']} | "
                 f"{'yes' if r['pass'] else 'no'} |")
    bk = res["models"].get("buckets", {}).get("last_fit")
    if bk:
        L.append("\nWhat the bucket rule learned (last fit, training trades only):\n")
        L.append("| time | day | train trades | train exp $ | skip |")
        L.append("|---|---|---|---|---|")
        for r in bk:
            L.append(f"| {r['time']} | {r['day']} | {r['train_trades']} | {r['train_exp']} | {'SKIP' if r['skip'] else ''} |")
    lg = res["models"].get("logit", {}).get("last_fit")
    if lg:
        L.append("\nStrongest logit weights (last fit; + = more likely a winner): " + ", ".join(f"{k} {v:+g}" for k, v in lg) + "\n")
    if n_trials:
        L.append(f"Trials so far (run log + these models): {n_trials}.\n")
    return "\n".join(L) + "\n"
