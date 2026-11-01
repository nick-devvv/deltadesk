"""sprint/factory.py - the 10-year strategy factory (SPRINT_PLAN Amendment 9, pre-registered 2026-11-01 before any factory
run). Research only: it reads trade files written by the engine and never trades.

Input: the trades of the 21 factory runs on HIST (factory_hist_v1, option prices MODELED (BS, calibrated IV)) and on DEV
(factory_dev_v1, REAL Alpaca option prices). Each run is one strategy; its HIST and DEV runs have the same rules and the
same position in their specs. For each strategy:
  (a) all days: per period and per year (2024 split into Jan, MODELED, and Aug-Dec, REAL; never one number);
  (b) the rule: the best of 12 tercile candidates (6 features x keep top / keep bottom) by PF on 2016-2019 only (at least
      60 trades), frozen, then holdout 1 = 2020-01..2024-01 (MODELED) and holdout 2 = DEV (REAL) with Amendment 6's bars;
  (c) the learner: sprint/learn.walk_forward over HIST + DEV trades, 24 training months, models logit / ridge / buckets;
      a model survives with walk_forward's pass AND its DEV-only segment at >= 40 trades, PF >= 1.25, PF 2x > 1.0;
  (d) the verdict: the surviving variant with the highest DEV-real expectancy (ties: rule, logit, ridge, buckets), or none.
Then the book (sprint/book.py) of every survivor's chosen variant, and the "everything unfiltered" book for contrast,
over 2018-01..2024-01 (MODELED), DEV (REAL), each year, and one line labeled "mixed: modeled 2018-2024 + real 2024-2026".

walk_forward needs per-trade take/skip decisions here (per-year and DEV-only numbers), so `walk_forward_masks` re-runs
learn.walk_forward's monthly loop with learn's own functions on a feature matrix built once (learn.decide rebuilds it
every month, which is slow on 7,000-trade runs). tests/test_sprint_factory.py checks that the two agree exactly.
"""
import math
import statistics
from datetime import date

import numpy as np

from . import book, features, learn, periods
from . import modeled as MD
from . import report as R

FEATURES6 = ("f_rvol", "f_range_atr", "f_vixy_pctl", "f_prev_ret", "f_gap", "f_day_ret")
SIDES = ("top", "bottom")
MIN_DISCOVERY = 60
DISCOVERY = ("2016-01-04", "2019-12-31")
HOLDOUT1 = ("2020-01-01", "2024-01-31")
H1_YEARS = (2020, 2021, 2022, 2023)
H1_SEED, H2_SEED, SKIP_DRAWS = 17, 23, 2000
TRAIN_MONTHS = 24
MODELS = learn.MODELS                                   # logit, ridge, buckets
DAILY_STOP = 150.0
HIST_A, HIST_B = periods.HIST[0].isoformat(), periods.HIST[1].isoformat()
DEV_A, DEV_B = periods.DEV[0].isoformat(), periods.DEV[1].isoformat()
BOOK_HIST = ("2018-01-02", HIST_B)
LAB = {"HIST": MD.LABEL, "DEV": "REAL (Alpaca option prices)"}
SHORT = {"HIST": "MODELED", "DEV": "REAL"}
YEARS = ([(str(y), f"{y}-01-01", f"{y}-12-31", "HIST") for y in range(2016, 2024)] +
         [("Jan 2024", "2024-01-01", "2024-01-31", "HIST"), ("Aug-Dec 2024", "2024-08-01", "2024-12-31", "DEV"),
          ("2025", "2025-01-01", "2025-12-31", "DEV"), ("Jan-Jun 2026", "2026-01-01", "2026-06-30", "DEV")])
BOOK_YEARS = [w for w in YEARS if w[1] >= "2018"]
# Amendment 9 "Known before any result": strategies whose 2016-2023 and DEV numbers Amendment 6 / run 5 already used,
# and the run-4 validation of the MODELED tapes against real prices (SPRINT_RESULTS_4.md).
SEEN_BEFORE = {"failed_break": "hist_v1-001 / setups_v2-001", "otm_p_1030": "hist_v1-003 / otm_v1-010",
               "otm_c_1100": "hist_v1-005 / otm_v1-040"}
VALIDATED = {"failed_break": "PASS in run 4 (fb: modeled PF 1.61 vs real 1.47)",
             "otm_p_1030": "PASS in run 4 (otm_put_base: modeled PF 0.98 vs real 0.87)",
             "otm_c_1100": "PASS in run 4 (otm_bounce_base: modeled PF 1.33 vs real 1.01)"}
NOT_VALIDATED = "NOT VALIDATED: the MODELED tapes were never checked against real prices for this strategy; holdout 2 decides"


# ---------------------------------------------------------------- small helpers
def num(x):
    if x is None or x == "":
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def day_of(r):
    return str(r["day"])[:10]


def pf_of(p):
    p = np.asarray(p, float)
    if not len(p):
        return None
    loss, win = -p[p < 0].sum(), p[p > 0].sum()
    if loss > 0:
        return round(float(win / loss), 3)
    return math.inf if win > 0 else None


def _r2(x, n=2):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


def ordered(rows):
    return sorted(rows, key=lambda r: (day_of(r), str(r.get("entry_time") or ""), str(r.get("symbol"))))


def in_window(rows, a, b, src=None):
    return [r for r in rows if a <= day_of(r) <= b and (src is None or r["_src"] == src)]


def months_between(days):
    return sorted({d[:7] for d in days})


def stats(rows, n_sessions=None):
    """The factory's per-window numbers (dollars per 1 contract)."""
    rows = ordered(rows)
    p = np.array([float(r["pnl"]) for r in rows])
    p2 = np.array([float(r["pnl_2x"]) if num(r.get("pnl_2x")) is not None else float(r["pnl"]) for r in rows])
    out = {"trades": len(rows), "per_session": round(len(rows) / n_sessions, 3) if n_sessions else None}
    if not len(rows):
        return out
    w, lo = p[p > 0], p[p < 0]
    eq = np.cumsum(p)
    dd = float((eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min())
    by_m = {}
    for r, x in zip(rows, p):
        by_m[day_of(r)[:7]] = by_m.get(day_of(r)[:7], 0.0) + x
    out.update({"win_rate": round(len(w) / len(p), 3), "avg_win": _r2(w.mean()) if len(w) else None,
                "avg_loss": _r2(lo.mean()) if len(lo) else None, "expectancy": _r2(p.mean()), "pf": pf_of(p), "pf_2x": pf_of(p2),
                "total": _r2(p.sum()), "total_2x": _r2(p2.sum()), "max_dd": _r2(min(dd, 0.0)),
                "without_best5": _r2(p.sum() - np.sort(p)[::-1][:5].sum()),
                "months_green": f"{sum(1 for v in by_m.values() if v > 0)}/{len(by_m)}"})
    return out


def brief(rows):
    p = np.array([float(r["pnl"]) for r in rows])
    return {"trades": len(p), "expectancy": _r2(p.mean()) if len(p) else None, "pf": pf_of(p), "total": _r2(p.sum()) if len(p) else 0.0}


def window_table(rows):
    """Per period and per year (each with its price source), plus by symbol and by side per period."""
    out = {"periods": {}, "years": {}, "by_symbol": {}, "by_side": {}}
    for src, a, b in (("HIST", HIST_A, HIST_B), ("DEV", DEV_A, DEV_B)):
        sub = in_window(rows, a, b, src)
        out["periods"][src] = dict(stats(sub, len(book.sessions_between(a, b))), prices=SHORT[src], window=f"{a}..{b}")
        out["by_symbol"][src] = {s: brief([r for r in sub if r["symbol"] == s]) for s in sorted({r["symbol"] for r in sub})}
        out["by_side"][src] = {s: brief([r for r in sub if r["side"] == s]) for s in ("C", "P") if any(r["side"] == s for r in sub)}
    for name, a, b, src in YEARS:
        a2, b2 = max(a, HIST_A if src == "HIST" else DEV_A), min(b, HIST_B if src == "HIST" else DEV_B)
        out["years"][name] = dict(stats(in_window(rows, a2, b2, src), len(book.sessions_between(a2, b2))), prices=SHORT[src])
    return out


# ---------------------------------------------------------------- (b) the rule
def keep(r, rule):
    v = num(r.get(rule["feature"]))
    if v is None:
        return False
    return v >= rule["cut"] if rule["side"] == "top" else v <= rule["cut"]


def apply_rule(rows, rule):
    return [r for r in rows if keep(r, rule)]


def tercile_cuts(values):
    q = np.quantile(np.asarray(values, float), [1 / 3, 2 / 3])
    return float(q[0]), float(q[1])


def _pf_rank(x):
    return -1.0 if x is None else (math.inf if math.isinf(x) else x)


def find_rule(rows, min_n=MIN_DISCOVERY):
    """(chosen rule or None, all 12 candidates). Uses HIST trades dated 2016-01-04..2019-12-31 ONLY."""
    disc = in_window(rows, DISCOVERY[0], DISCOVERY[1], "HIST")
    cands = []
    for k, f in enumerate(FEATURES6):
        vals = [v for v in (num(r.get(f)) for r in disc) if v is not None]
        if not vals:
            for j, sd in enumerate(SIDES):
                cands.append({"feature": f, "side": sd, "cut": None, "n": 0, "pf": None, "expectancy": None, "total": 0.0,
                              "eligible": False, "order": 2 * k + j, "note": "no values in 2016-2019"})
            continue
        lo, hi = tercile_cuts(vals)
        for j, (sd, cut) in enumerate((("top", hi), ("bottom", lo))):
            rule = {"feature": f, "side": sd, "cut": cut}
            b = brief(apply_rule(disc, rule))
            cands.append(dict(rule, n=b["trades"], pf=b["pf"], expectancy=b["expectancy"], total=b["total"],
                              eligible=b["trades"] >= min_n and b["pf"] is not None, order=2 * k + j))
    elig = [c for c in cands if c["eligible"]]
    if not elig:
        return None, cands, len(disc)
    best = max(elig, key=lambda c: (_pf_rank(c["pf"]), c["n"], -c["order"]))
    return {"feature": best["feature"], "side": best["side"], "cut": best["cut"]}, cands, len(disc)


def day_skip_p(base_rows, sel_total, n_keep, seed, draws=SKIP_DRAWS):
    """tools/sprint_regime.day_skip_p on trade dicts: remove random whole sessions from the unfiltered trades until at
    least as many trades are gone as the rule removed; p = share of draws whose remaining total >= the rule's total."""
    by = {}
    for r in base_rows:
        d = by.setdefault(day_of(r), [0, 0.0])
        d[0] += 1
        d[1] += float(r["pnl"])
    keys = sorted(by)
    sz = np.array([by[k][0] for k in keys])
    sm = np.array([by[k][1] for k in keys])
    n_rm = len(base_rows) - n_keep
    if n_rm <= 0 or not len(keys):
        return None
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(draws):
        o = rng.permutation(len(keys))
        k = int(np.searchsorted(np.cumsum(sz[o]), n_rm)) + 1
        hits += (sm.sum() - sm[o[:k]].sum()) >= sel_total
    return round(hits / draws, 4)


def holdout1(rows, rule):
    base = in_window(rows, HOLDOUT1[0], HOLDOUT1[1], "HIST")
    sel = apply_rule(base, rule)
    s = stats(sel)
    yrs = {}
    for y in H1_YEARS:
        ys = [r for r in sel if day_of(r)[:4] == str(y)]
        yrs[str(y)] = {"trades": len(ys), "net": _r2(sum(float(r["pnl"]) for r in ys)) if ys else 0.0}
    green = sum(1 for v in yrs.values() if v["trades"] >= 10 and v["net"] > 0)
    p = day_skip_p(base, sum(float(r["pnl"]) for r in sel), len(sel), H1_SEED) if sel else None
    checks = [("at least 60 trades", s["trades"] >= 60),
              ("PF >= 1.25", _pf_rank(s.get("pf")) >= 1.25),
              ("PF 2x > 1.0", _pf_rank(s.get("pf_2x")) > 1.0),
              (f"profitable in at least 3 of 2020-2023, years with 10+ trades ({green} of 4)", green >= 3),
              ("positive without the best 5 trades", (s.get("without_best5") or 0) > 0),
              (f"beats random whole-day removal, p < 0.05 (p = {p})", p is not None and p < 0.05)]
    return {"stats": s, "base_trades": len(base), "base": brief(base), "years": yrs, "p_day_skip": p, "checks": checks,
            "pass": all(ok for _, ok in checks)}


def holdout2(rows, rule):
    base = in_window(rows, DEV_A, DEV_B, "DEV")
    sel = apply_rule(base, rule)
    s = stats(sel)
    p = day_skip_p(base, sum(float(r["pnl"]) for r in sel), len(sel), H2_SEED) if sel else None
    checks = [("at least 40 trades", s["trades"] >= 40),
              ("PF >= 1.25", _pf_rank(s.get("pf")) >= 1.25),
              ("PF 2x > 1.0", _pf_rank(s.get("pf_2x")) > 1.0),
              (f"beats random whole-day removal, p < 0.10 (p = {p})", p is not None and p < 0.10)]
    return {"stats": s, "base_trades": len(base), "base": brief(base), "p_day_skip": p, "checks": checks,
            "pass": all(ok for _, ok in checks)}


def first_fail(checks):
    for name, ok in checks:
        if not ok:
            return name
    return None


# ---------------------------------------------------------------- (c) the learner
def _decide(model, X, pnl, tr, te, rows_tr, rows_te, names):
    """learn.decide on precomputed matrices (same functions, same order of rows)."""
    if model == "buckets":
        return learn.decide("buckets", rows_tr, rows_te)
    Xtr, Xte = X[tr], X[te]
    p = learn._prep_fit(Xtr)
    Ztr, Zte = learn._prep_apply(p, Xtr), learn._prep_apply(p, Xte)
    ptr = pnl[tr]
    if Ztr.shape[1] == 0:
        return np.ones(len(te), bool), None
    kept = [n for n, k in zip(names, p["keep"]) if k]
    if model == "logit":
        w, b = learn.fit_logit(Ztr, (ptr > 0).astype(float))
        prob = 1.0 / (1.0 + np.exp(-np.clip(Zte @ w + b, -30, 30)))
        return prob >= 0.5, {"coef": dict(zip(kept, np.round(w, 3)))}
    if model == "ridge":
        lo, hi = np.percentile(ptr, [5, 95])
        w, b = learn.fit_ridge(Ztr, np.clip(ptr, lo, hi))
        return (Zte @ w + b) > 0, {"coef": dict(zip(kept, np.round(w, 3)))}
    raise ValueError(model)


def walk_forward_masks(rows, min_train_months=TRAIN_MONTHS, models=MODELS, n_random=200, seed=7):
    """learn.walk_forward's result for these rows, plus {model: [the out-of-sample rows it took]}."""
    names = features.FEATURES
    rows = sorted(rows, key=lambda r: (str(r["day"]), r.get("f_minute") or 0))
    mon = [str(r["day"])[:7] for r in rows]
    months = sorted(set(mon))
    if len(months) <= min_train_months:
        return {"error": f"need more than {min_train_months} months with trades, have {len(months)}"}, {}
    test_months = months[min_train_months:]
    tset = set(test_months)
    oos_pos = [i for i, m in enumerate(mon) if m in tset]
    oos = [rows[i] for i in oos_pos]
    base = learn.stats([r["pnl"] for r in oos], [r.get("pnl_2x", r["pnl"]) for r in oos])
    res = {"months": len(months), "train_months_first": min_train_months, "oos_from": test_months[0], "base": base, "models": {}}
    X = features.matrix(rows, names)
    pnl = np.array([float(r["pnl"]) for r in rows])
    mon_a = np.array(mon)
    rng = np.random.default_rng(seed)
    oos_pnl = pnl[oos_pos]
    oos_mon = mon_a[oos_pos]
    picks = {}
    for m in models:
        take = np.zeros(len(oos), bool)
        last = None
        for tm in test_months:
            tr = np.where(mon_a < tm)[0]
            te_o = np.where(oos_mon == tm)[0]
            te = np.asarray(oos_pos)[te_o]
            t, info = _decide(m, X, pnl, tr, te, [rows[i] for i in tr], [rows[i] for i in te], names)
            take[te_o] = t
            last = info or last
        sel = [r for r, t in zip(oos, take) if t]
        st = learn.stats([r["pnl"] for r in sel], [r.get("pnl_2x", r["pnl"]) for r in sel])
        n_take = int(take.sum())
        rand = np.array([oos_pnl[rng.choice(len(oos), n_take, replace=False)].sum() for _ in range(n_random)]) if 0 < n_take < len(oos) else None
        pct = float((rand < st.get("total", 0)).mean()) if rand is not None else None
        ok = (st.get("trades", 0) >= 60 and st.get("expectancy", -1e9) > base.get("expectancy", 0) and pct is not None and pct >= 0.95
              and (st.get("pf_2x") or 0) > 1.0)
        res["models"][m] = {"taken": st, "skipped": len(oos) - n_take, "random_skip_pctl": None if pct is None else round(pct, 3),
                            "pass": bool(ok), "last_fit": learn._readable(m, last)}
        picks[m] = sel
    res["oos_rows"] = len(oos)
    return res, picks


def wf_fail(res, m):
    r, b = res["models"][m], res["base"]
    st = r["taken"]
    if st.get("trades", 0) < 60:
        return f"walk-forward: {st.get('trades', 0)} trades taken (needs 60)"
    if not st.get("expectancy", -1e9) > b.get("expectancy", 0):
        return f"walk-forward: expectancy {st.get('expectancy')} not above taking every trade ({b.get('expectancy')})"
    if r["random_skip_pctl"] is None or r["random_skip_pctl"] < 0.95:
        return f"walk-forward: total beats only {r['random_skip_pctl']} of random skips (needs 0.95)"
    if not (st.get("pf_2x") or 0) > 1.0:
        return f"walk-forward: PF 2x {st.get('pf_2x')} (needs > 1.0)"
    return None


def dev_checks(s):
    return [("DEV-only at least 40 trades", s["trades"] >= 40), ("DEV-only PF >= 1.25", _pf_rank(s.get("pf")) >= 1.25),
            ("DEV-only PF 2x > 1.0", _pf_rank(s.get("pf_2x")) > 1.0)]


def learner(rows):
    res, picks = walk_forward_masks(rows)
    out = {"walk_forward": res, "models": {}}
    if "error" in res:
        return out, {}
    for m in MODELS:
        sel = picks[m]
        dev = stats(in_window(sel, DEV_A, DEV_B, "DEV"), len(book.sessions_between(DEV_A, DEV_B)))
        dc = dev_checks(dev)
        why = wf_fail(res, m) or first_fail(dc)
        yrs = {}
        for name, a, b, src in YEARS:
            a2, b2 = max(a, HIST_A if src == "HIST" else DEV_A), min(b, HIST_B if src == "HIST" else DEV_B)
            oos_here = b2 >= res["oos_from"]
            yrs[name] = dict(stats(in_window(sel, a2, b2, src), len(book.sessions_between(a2, b2))), prices=SHORT[src],
                             oos=oos_here)
        out["models"][m] = {"pass_walk_forward": res["models"][m]["pass"], "dev": dev, "dev_checks": dc,
                            "survives": why is None, "why_not": why, "years": yrs}
    return out, picks


# ---------------------------------------------------------------- one strategy
def run_strategy(name, rows):
    rows = [r for r in rows]
    out = {"name": name, "seen_before": SEEN_BEFORE.get(name), "model_check": VALIDATED.get(name, NOT_VALIDATED),
           "all_days": window_table(rows)}
    rule, cands, n_disc = find_rule(rows)
    rb = {"discovery_trades": n_disc, "candidates": cands, "rule": rule}
    rule_rows = []
    if rule is None:
        rb.update(survives=False, why_not=f"no candidate kept {MIN_DISCOVERY} trades in 2016-2019 ({n_disc} discovery trades)")
    else:
        h1, h2 = holdout1(rows, rule), holdout2(rows, rule)
        why = (("holdout 1: " + first_fail(h1["checks"])) if not h1["pass"] else
               ("holdout 2: " + first_fail(h2["checks"])) if not h2["pass"] else None)
        rule_rows = apply_rule(rows, rule)
        rb.update(holdout1=h1, holdout2=h2, survives=why is None, why_not=why, years=window_table(rule_rows)["years"])
    out["rule"] = rb
    ln, picks = learner(rows)
    out["learner"] = ln
    out["verdict"], out["verdict_why"] = choose(rb, ln)
    sleeve = rule_rows if out["verdict"] == "rule" else picks.get(out["verdict"], [])
    return out, sleeve, {"rule": rule_rows, **picks}


def choose(rb, ln):
    """(verdict, why): the surviving variant with the highest DEV-real expectancy; ties: rule, logit, ridge, buckets."""
    cand = []
    if rb.get("survives"):
        cand.append(("rule", rb["holdout2"]["stats"].get("expectancy"), 0))
    for k, m in enumerate(MODELS):
        g = (ln.get("models") or {}).get(m)
        if g and g["survives"]:
            cand.append((m, g["dev"].get("expectancy"), k + 1))
    if not cand:
        return "none", "no variant survived"
    best = max(cand, key=lambda c: (c[1] if c[1] is not None else -1e9, -c[2]))
    if len(cand) == 1:
        return best[0], f"{best[0]} is the only survivor"
    return best[0], f"{best[0]} has the highest DEV-real expectancy among the survivors (" + ", ".join(f"{c[0]} {c[1]}" for c in cand) + ")"


# ---------------------------------------------------------------- the book
def _daily_months(daily, days):
    by = {}
    for d, x in zip(days, daily):
        by[d[:7]] = by.get(d[:7], 0.0) + x
    return by


def wstats(rows, days, light=False):
    """book.sleeve_stats (every session counts) plus total, average per year, worst month and months green."""
    d = book._daily(rows, days)
    if light:
        eq = np.cumsum(d)
        dd = float((eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min()) if len(eq) else 0.0
        p = np.array([float(r["pnl"]) for r in rows])
        out = {"trades": len(rows), "per_session": round(len(rows) / len(days), 2) if days else None,
               "expectancy": _r2(p.mean()) if len(p) else None, "pf": pf_of(p), "total": _r2(p.sum()) if len(p) else 0.0,
               "max_dd": _r2(min(dd, 0.0)), "sharpe": round(float(d.mean() / d.std() * math.sqrt(252)), 2) if len(d) and d.std() > 0 else None}
    else:
        out = book.sleeve_stats(rows, days)
    bm = _daily_months(d, days)
    out["sessions"] = len(days)
    out["avg_per_year"] = _r2(float(d.sum()) / (len(days) / 252)) if days else None
    out["worst_month"] = (min(bm.items(), key=lambda kv: kv[1])[0], _r2(min(bm.values()))) if bm else None
    out["months_green"] = f"{sum(1 for v in bm.values() if v > 0)}/{len(bm)}"
    return out


def window_book(by_sleeve, days, daily_stop=None, light=False):
    """The book over `days` (ISO sessions; every one counts). With daily_stop: the book line only (sleeves are unchanged
    by the desk stop, so they are not recomputed)."""
    dset = set(days)
    sub = {k: [r for r in v if day_of(r) in dset] for k, v in by_sleeve.items()}
    out = {"sessions": len(days), "sleeves": {} if daily_stop else {k: wstats(v, days, light) for k, v in sub.items()}}
    allr = [dict(r, run_id=k) for k, v in sub.items() for r in v]
    if daily_stop:
        allr, sk = book.apply_daily_stop(allr, daily_stop)
        out["daily_stop"] = {"limit": daily_stop, "skipped": sk}
    out["book"] = wstats(allr, days, light)
    if not light and not daily_stop:
        keys = sorted(sub)
        M = np.array([book._daily(sub[k], days) for k in keys]) if keys else np.zeros((0, len(days)))
        with np.errstate(invalid="ignore", divide="ignore"):
            C = np.corrcoef(M) if len(keys) > 1 else np.ones((len(keys), len(keys)))
        C = np.atleast_2d(C)
        out["corr"] = {k: {k2: (None if math.isnan(C[i, j]) else round(float(C[i, j]), 2)) for j, k2 in enumerate(keys)}
                       for i, k in enumerate(keys)}
        out["overlaps"] = book.overlaps(sub)
    return out


def book_views(by_sleeve):
    hist_days = book.sessions_between(*BOOK_HIST)
    dev_days = book.sessions_between(DEV_A, DEV_B)
    src_ok = lambda src: {k: [r for r in v if r["_src"] == src] for k, v in by_sleeve.items()}
    out = {"windows": {}, "years": {}}
    for key, label, days, src in (("hist", f"{BOOK_HIST[0]}..{BOOK_HIST[1]} HIST, MODELED", hist_days, "HIST"),
                                  ("dev", f"{DEV_A}..{DEV_B} DEV, REAL", dev_days, "DEV")):
        bs = src_ok(src)
        out["windows"][key] = {"label": label, "plain": window_book(bs, days), "stop": window_book(bs, days, DAILY_STOP)}
    mixed = hist_days + dev_days
    out["windows"]["mixed"] = {"label": "mixed: modeled 2018-2024 + real 2024-2026", "plain": window_book(by_sleeve, mixed),
                               "stop": window_book(by_sleeve, mixed, DAILY_STOP)}
    for name, a, b, src in BOOK_YEARS:
        a2, b2 = max(a, BOOK_HIST[0] if src == "HIST" else DEV_A), min(b, HIST_B if src == "HIST" else DEV_B)
        out["years"][name] = dict(window_book(src_ok(src), book.sessions_between(a2, b2), light=True), prices=SHORT[src])
    return out


# ---------------------------------------------------------------- everything
def trial_parts(n_strategies):
    """Trials a factory pass adds (Amendment 9: 21 strategies -> 42 runs + 252 candidate rules + 63 learner models = 357)."""
    return {"runs": 2 * n_strategies, "rules": len(FEATURES6) * len(SIDES) * n_strategies, "learner": len(MODELS) * n_strategies}


def run(strategies, n_prior_trials=0):
    """strategies: [(name, rows)] in spec order; rows carry "_src" ("HIST"/"DEV"). Returns the full result."""
    res = {"strategies": {}, "order": [n for n, _ in strategies]}
    sleeves, everything, variants_dev = {}, {}, []
    dev_days = book.sessions_between(DEV_A, DEV_B)
    for name, rows in strategies:
        out, sleeve, pool = run_strategy(name, rows)
        res["strategies"][name] = out
        everything[name] = rows
        if out["verdict"] != "none":
            sleeves[name] = sleeve
        variants_dev.append(in_window(rows, DEV_A, DEV_B, "DEV"))
        for c in out["rule"]["candidates"]:
            if c["cut"] is not None:
                variants_dev.append(apply_rule(in_window(rows, DEV_A, DEV_B, "DEV"), c))
        for m in MODELS:
            if m in pool:
                variants_dev.append(in_window(pool[m], DEV_A, DEV_B, "DEV"))
        res["strategies"][name]["_chosen_dev"] = in_window(sleeve, DEV_A, DEV_B, "DEV") if out["verdict"] != "none" else None
    srs = [x for x in (R.sharpe(R.daily_pnl([{"day": day_of(r), "pnl": r["pnl"]} for r in v], dev_days)) for v in variants_dev) if x is not None]
    sr_var = statistics.pvariance(srs) if len(srs) > 1 else 0.0
    parts = trial_parts(len(strategies))
    n_trials = int(n_prior_trials) + parts["rules"] + parts["learner"]
    res["trials"] = {"new": sum(parts.values()), "new_parts": parts, "prior_in_run_logs": int(n_prior_trials),
                     "total_for_dsr": n_trials, "dev_variants_scored": len(variants_dev), "sr_var": round(sr_var, 6)}
    for name in res["order"]:
        ch = res["strategies"][name].pop("_chosen_dev")
        res["strategies"][name]["dsr_dev"] = (R.deflated_sharpe(R.daily_pnl([{"day": day_of(r), "pnl": r["pnl"]} for r in ch], dev_days),
                                                                n_trials, sr_var) if ch is not None else None)
    res["survivors"] = {k: res["strategies"][k]["verdict"] for k in sleeves}
    res["book"] = book_views(sleeves) if sleeves else None
    res["unfiltered"] = book_views(everything)
    return res


# ---------------------------------------------------------------- the report
def _f(x, n=2):
    return R.fmt(x, n)


def _rule_txt(rule):
    if not rule:
        return "-"
    return f"{rule['feature']} {'>=' if rule['side'] == 'top' else '<='} {rule['cut']:.4g} ({'top' if rule['side'] == 'top' else 'bottom'} tercile)"


def _variant_txt(s):
    v = s["verdict"]
    if v == "none":
        return "none"
    if v == "rule":
        return "rule: " + _rule_txt(s["rule"]["rule"])
    return f"learner: {v}"


STAT_COLS = ("trades", "per session", "win %", "avg win", "avg loss", "exp $", "PF", "PF 2x", "total $", "max DD", "w/o best 5", "months green")


def _stat_cells(s):
    return [str(s.get("trades", 0)), _f(s.get("per_session"), 3), _f(None if s.get("win_rate") is None else 100 * s["win_rate"], 1),
            _f(s.get("avg_win")), _f(s.get("avg_loss")), _f(s.get("expectancy")), _f(s.get("pf"), 3), _f(s.get("pf_2x"), 3),
            _f(s.get("total")), _f(s.get("max_dd")), _f(s.get("without_best5")), str(s.get("months_green", "-"))]


def _row(cells):
    return "| " + " | ".join(cells) + " |"


def _head(cols):
    return _row(list(cols)) + "\n|" + "---|" * len(cols)


def _book_md(L, bv, labels):
    L.append(_head(("window", "prices", "sessions", "trades", "per session", "total $", "avg per year $", "max DD $", "worst month",
                    "months green", "Sharpe", "PF", "total, $150 daily stop", "max DD, stop")))
    for key in ("hist", "dev", "mixed"):
        w = bv["windows"][key]
        b, s = w["plain"]["book"], w["stop"]["book"]
        wm = b.get("worst_month")
        L.append(_row([w["label"], "MODELED" if key == "hist" else "REAL" if key == "dev" else "MIXED (labeled)", str(b["sessions"]),
                       str(b["trades"]), _f(b.get("per_session")), _f(b.get("total")), _f(b.get("avg_per_year")), _f(b.get("max_dd")),
                       f"{wm[0]} {_f(wm[1])}" if wm else "-", b["months_green"], _f(b.get("sharpe")), _f(b.get("pf"), 3),
                       _f(s.get("total")), _f(s.get("max_dd"))]))
    L.append("\nPer year (2018-2019 are in-sample for rule sleeves: their discovery years):\n")
    L.append(_head(("year", "prices", "sessions", "trades", "per session", "total $", "max DD $", "worst month", "months green", "Sharpe")))
    for name, y in bv["years"].items():
        b = y["book"]
        wm = b.get("worst_month")
        L.append(_row([name, y["prices"], str(b["sessions"]), str(b["trades"]), _f(b.get("per_session")), _f(b.get("total")),
                       _f(b.get("max_dd")), f"{wm[0]} {_f(wm[1])}" if wm else "-", b["months_green"], _f(b.get("sharpe"))]))
    for key in ("hist", "dev", "mixed"):
        w = bv["windows"][key]["plain"]
        L.append(f"\nBy sleeve, {bv['windows'][key]['label']}:\n")
        L.append(_head(("sleeve", "variant", "trades", "per session", "exp $", "PF", "PF 2x", "total $", "avg per year $", "max DD $",
                        "worst month", "months green", "Sharpe")))
        for k, s in w["sleeves"].items():
            wm = s.get("worst_month")
            L.append(_row([k, labels.get(k, "unfiltered"), str(s["trades"]), _f(s.get("per_session")), _f(s.get("expectancy")),
                           _f(s.get("pf"), 3), _f(s.get("pf_2x"), 3), _f(s.get("total")), _f(s.get("avg_per_year")), _f(s.get("max_dd")),
                           f"{wm[0]} {_f(wm[1])}" if wm else "-", s["months_green"], _f(s.get("sharpe"))]))
        if key != "mixed":
            ds = bv["windows"][key]["stop"].get("daily_stop") or {}
            L.append(f"\nSame symbol and side held at the same time in two sleeves: {w['overlaps']} trade pairs. "
                     f"The $150 desk daily stop skipped {ds.get('skipped', 0)} entries.")
            keys = list(w["corr"])
            if 1 < len(keys) <= 12:
                L.append("\nCorrelation of daily P/L:\n")
                L.append(_head([""] + keys))
                for k in keys:
                    L.append(_row([k] + ["" if w["corr"][k][k2] is None else f"{w['corr'][k][k2]:+.2f}" for k2 in keys]))
            elif len(keys) > 12:
                vals = [w["corr"][a][b] for i, a in enumerate(keys) for b in keys[i + 1:] if w["corr"][a][b] is not None]
                if vals:
                    L.append(f"\nCorrelation of daily P/L across {len(keys)} sleeves: median {statistics.median(vals):+.2f}, "
                             f"max {max(vals):+.2f}, min {min(vals):+.2f} (full matrix in the JSON).")


def render(res, meta):
    tp = res["trials"]["new_parts"]
    L = [f"# The 10-year strategy factory ({meta.get('today')})\n",
         "SPRINT_PLAN Amendment 9 (pre-registered 2026-11-01, before any factory run). Every number is a **BACKTEST**, 1 contract per "
         "signal, desk fills, 2% half-spread (MODELED-SPREAD, $0.005 floor), $0.65 per contract per side.\n",
         f"- **HIST 2016-01-04..2024-01-31: option prices {MD.LABEL}.** Stock bars are real; the options are Black-Scholes at one flat "
         "IV per day. Labeled MODELED everywhere.",
         "- **DEV 2024-08-01..2026-06-30: REAL Alpaca option prices.** Labeled REAL everywhere.",
         "- 2024 is never one number: Jan 2024 is MODELED, Aug-Dec 2024 is REAL. L1 and L2 were never pulled or run.",
         f"- Trade files: HIST `{meta.get('hist_file')}`, DEV `{meta.get('dev_file')}`. Specs: `{meta.get('hist_spec')}` (sha256 "
         f"{meta.get('hist_sha', '')[:12]}), `{meta.get('dev_spec')}` (sha256 {meta.get('dev_sha', '')[:12]}).",
         f"- Run log: {meta.get('runlog_note', 'not found')}",
         f"- **Trials:** this amendment adds {res['trials']['new']} ({tp['runs']} runs + {tp['rules']} candidate rules + {tp['learner']} "
         f"learner models). Deflated Sharpe (information only) uses N = {res['trials']['total_for_dsr']} (run logs, which hold the "
         f"factory runs, {res['trials']['prior_in_run_logs']} + {tp['rules'] + tp['learner']}).",
         "- Not financial advice: evidence for Nick to decide. Nothing here is promoted; a survivor needs a new versioned paper "
         "ledger, Nick's yes and 40 forward paper trades (CLAUDE.md step 5).\n"]
    if meta.get("warnings"):
        L.append("**Warnings:** " + " ".join(meta["warnings"]) + "\n")
    L.append("## Summary\n")
    L.append(_head(("#", "strategy", "HIST MODELED n / PF / total $", "DEV REAL n / PF / total $", "rule (found on 2016-2019)",
                    "holdout 1 (MODELED)", "holdout 2 (REAL)", "learner survivors", "verdict", "DEV exp $ (chosen)", "note")))
    for i, name in enumerate(res["order"], 1):
        s = res["strategies"][name]
        hp, dp = s["all_days"]["periods"]["HIST"], s["all_days"]["periods"]["DEV"]
        rb = s["rule"]
        h1 = "-" if rb.get("rule") is None else ("PASS" if rb["holdout1"]["pass"] else "fail")
        h2 = "-" if rb.get("rule") is None else (("PASS" if rb["holdout2"]["pass"] else "fail") if rb["holdout1"]["pass"]
                                                  else ("(" + ("pass" if rb["holdout2"]["pass"] else "fail") + ", not counted)"))
        lm = [m for m in MODELS if (s["learner"]["models"].get(m) or {}).get("survives")]
        dexp = (rb["holdout2"]["stats"].get("expectancy") if s["verdict"] == "rule" else
                s["learner"]["models"][s["verdict"]]["dev"].get("expectancy") if s["verdict"] in MODELS else None)
        note = []
        if s["seen_before"]:
            note.append("seen before (Amendment 6)")
        if s["model_check"] == NOT_VALIDATED:
            note.append("model not validated")
        L.append(_row([str(i), name, f"{hp['trades']} / {_f(hp.get('pf'), 3)} / {_f(hp.get('total'))}",
                       f"{dp['trades']} / {_f(dp.get('pf'), 3)} / {_f(dp.get('total'))}", _rule_txt(rb.get("rule")), h1, h2,
                       ", ".join(lm) or "none", f"**{_variant_txt(s)}**" if s["verdict"] != "none" else "none", _f(dexp),
                       "; ".join(note) or "-"]))
    L.append("")
    for i, name in enumerate(res["order"], 1):
        _strategy_md(L, i, name, res["strategies"][name], meta)
    L.append("## The book: every survivor together\n")
    if res["book"] is None:
        L.append("**No strategy survived, so there is no book.** The unfiltered contrast below is what taking every signal of all 21 "
                 "runs would have done.\n")
    else:
        labels = {k: _variant_txt(res["strategies"][k]) for k in res["survivors"]}
        L.append("Sleeves: " + "; ".join(f"{k} ({v})" for k, v in labels.items()) + ". 1 contract per signal; every session counts "
                 "(P/L 0 on days without a trade). Rule sleeves trade their rule in every year (2018-2019 in-sample); learner sleeves "
                 "trade their out-of-sample picks only.\n")
        _book_md(L, res["book"], labels)
        L.append("")
    L.append("## Contrast: everything unfiltered (all 21 runs, every trade)\n")
    _book_md(L, res["unfiltered"], {})
    L.append("\n## Limits\n")
    L.append("- HIST option prices are MODELED: one flat IV per day, no smile, no intraday IV change, a price every minute, a 0DTE "
             "expiry every session (before Nov 2022 SPY/QQQ/IWM did not list one every weekday). On days that are already moving "
             "real 0DTE IV rises and the model's doesn't, which flattered far-OTM put rules before (Amendment 6, run 5).")
    L.append("- Only three of the 21 strategies had their MODELED tapes checked against real prices (run 4). The others are labeled "
             "NOT VALIDATED; holdout 2 on real DEV prices is the deciding test for every rule.")
    L.append("- The noise run uses the noise ledger's exit on modeled tapes: its every-minute 20% ceiling acts on modeled bar highs "
             "and lows. With both sides in one run, a reversal exits but does not open the other side (one position per symbol).")
    L.append("- failed_break, otm_p_1030 and otm_c_1100 were studied before (Amendment 6, run 5): their verdicts are not new evidence.")
    L.append("- Most DEV numbers of the unfiltered runs were seen in runs 1-3; only the rules are new on DEV.")
    L.append("- 2% half-spread may be optimistic for thinner 2016-2019 0DTE markets; no 5% stress in this run.\n")
    return "\n".join(L) + "\n"


def _strategy_md(L, i, name, s, meta):
    L.append(f"## {i}. {name}: verdict **{_variant_txt(s)}**\n")
    ids = meta.get("run_ids", {}).get(name, {})
    L.append(f"Runs `{ids.get('HIST', '?')}` (HIST, MODELED) and `{ids.get('DEV', '?')}` (DEV, REAL). {meta.get('configs', {}).get(name, '')}\n")
    L.append(f"Model check: {s['model_check']}." + (f" **Seen before** ({s['seen_before']}): Amendment 6 already used its 2016-2023 "
                                                     "terciles and holdouts, so this verdict is not new evidence." if s["seen_before"] else "") + "\n")
    a = s["all_days"]
    L.append("**(a) All days**\n")
    L.append(_head(("window", "prices") + STAT_COLS))
    for src in ("HIST", "DEV"):
        p = a["periods"][src]
        L.append(_row([("HIST 2016-01..2024-01" if src == "HIST" else "DEV 2024-08..2026-06"), p["prices"]] + _stat_cells(p)))
    for yname, y in a["years"].items():
        L.append(_row([yname, y["prices"]] + _stat_cells(y)))
    for src in ("HIST", "DEV"):
        L.append(f"\n{SHORT[src]} by symbol: " + "; ".join(f"{k} n={v['trades']} exp {_f(v['expectancy'])} PF {_f(v['pf'], 3)} total "
                                                          f"{_f(v['total'])}" for k, v in a["by_symbol"][src].items())
                 + ". By side: " + "; ".join(f"{'calls' if k == 'C' else 'puts'} n={v['trades']} exp {_f(v['expectancy'])} PF "
                                             f"{_f(v['pf'], 3)} total {_f(v['total'])}" for k, v in a["by_side"][src].items()) + ".")
    rb = s["rule"]
    L.append(f"\n**(b) Rule, found on 2016-2019 only** ({rb['discovery_trades']} discovery trades, MODELED)\n")
    L.append(_head(("feature", "keep", "cut", "discovery trades", "discovery PF", "exp $", "eligible (60+)")))
    for c in rb["candidates"]:
        L.append(_row([c["feature"], c["side"], "-" if c["cut"] is None else f"{c['cut']:.4g}", str(c["n"]), _f(c["pf"], 3),
                       _f(c["expectancy"]), "yes" if c["eligible"] else "no"]))
    if rb.get("rule") is None:
        L.append(f"\nNo rule: {rb['why_not']}.\n")
    else:
        L.append(f"\nChosen and frozen: **{_rule_txt(rb['rule'])}** (cut {rb['rule']['cut']!r}).\n")
        h1 = rb["holdout1"]
        s1 = h1["stats"]
        L.append(f"Holdout 1, 2020-01..2024-01 (MODELED): {s1['trades']} of {h1['base_trades']} trades, exp {_f(s1.get('expectancy'))}, "
                 f"PF {_f(s1.get('pf'), 3)}, PF 2x {_f(s1.get('pf_2x'), 3)}, total {_f(s1.get('total'))} (all trades: PF "
                 f"{_f(h1['base']['pf'], 3)}, total {_f(h1['base']['total'])}), without best 5 {_f(s1.get('without_best5'))}; years "
                 + ", ".join(f"{y} n={v['trades']} {_f(v['net'])}" for y, v in h1["years"].items()) + f". **{'PASS' if h1['pass'] else 'fail'}**\n")
        for n_, ok in h1["checks"]:
            L.append(f"- [{'x' if ok else ' '}] {n_}")
        h2 = rb["holdout2"]
        s2 = h2["stats"]
        L.append(f"\nHoldout 2, DEV (REAL){'' if h1['pass'] else ' (shown for information: it counts only after holdout 1)'}: "
                 f"{s2['trades']} of {h2['base_trades']} trades, exp {_f(s2.get('expectancy'))}, PF {_f(s2.get('pf'), 3)}, PF 2x "
                 f"{_f(s2.get('pf_2x'), 3)}, total {_f(s2.get('total'))} (all trades: PF {_f(h2['base']['pf'], 3)}, total "
                 f"{_f(h2['base']['total'])}), without best 5 {_f(s2.get('without_best5'))}. "
                 f"**{'PASS' if h2['pass'] and h1['pass'] else 'fail' if h1['pass'] else 'not counted'}**\n")
        for n_, ok in h2["checks"]:
            L.append(f"- [{'x' if ok else ' '}] {n_}")
        L.append("\nThe rule, every year (2016-2019 = its discovery years, in-sample):\n")
        L.append(_head(("window", "prices") + STAT_COLS))
        for yname, y in rb["years"].items():
            L.append(_row([yname + (" (in-sample)" if yname in ("2016", "2017", "2018", "2019") else ""), y["prices"]] + _stat_cells(y)))
    ln = s["learner"]
    wf = ln["walk_forward"]
    L.append("\n**(c) Learner** (sprint/learn.walk_forward, monthly refit on earlier months only, 24 training months; HIST trades "
             "MODELED, DEV trades REAL)\n")
    if "error" in wf:
        L.append(f"Not run: {wf['error']}.\n")
    else:
        b = wf["base"]
        L.append(f"Out-of-sample from {wf['oos_from']} ({wf['oos_rows']} trades). Taking every out-of-sample trade: n={b['trades']}, "
                 f"exp {b.get('expectancy')}, PF {b.get('pf')}, PF 2x {b.get('pf_2x')}, total {b.get('total')}.\n")
        L.append(_head(("model", "taken", "exp $", "PF", "PF 2x", "total $", "max DD", "beats random skips", "walk-forward pass",
                        "DEV-only n", "DEV exp $", "DEV PF", "DEV PF 2x", "survives")))
        for m in MODELS:
            r, g = wf["models"][m], ln["models"][m]
            t, d = r["taken"], g["dev"]
            L.append(_row([m, str(t.get("trades", 0)), _f(t.get("expectancy")), _f(t.get("pf"), 3), _f(t.get("pf_2x"), 3), _f(t.get("total")),
                           _f(t.get("max_dd")), _f(r["random_skip_pctl"], 3), "yes" if r["pass"] else "no", str(d["trades"]),
                           _f(d.get("expectancy")), _f(d.get("pf"), 3), _f(d.get("pf_2x"), 3),
                           "**yes**" if g["survives"] else f"no ({g['why_not']})"]))
        L.append("\nThe logit's picks, every year (out-of-sample years only):\n")
        L.append(_head(("window", "prices") + STAT_COLS))
        for yname, y in ln["models"]["logit"]["years"].items():
            if y.get("oos"):
                L.append(_row([yname, y["prices"]] + _stat_cells(y)))
        lg = wf["models"]["logit"].get("last_fit")
        if lg:
            L.append("\nStrongest logit weights (last fit; + = more likely a winner): " + ", ".join(f"{k} {v:+g}" for k, v in lg))
    L.append(f"\n**(d) Verdict: {_variant_txt(s)}.** {s['verdict_why']}.")
    why = []
    if not rb["survives"]:
        why.append(f"rule: {rb['why_not']}")
    for m in MODELS:
        g = ln["models"].get(m)
        if g and not g["survives"]:
            why.append(f"{m}: {g['why_not']}")
        elif not g:
            why.append(f"{m}: {wf.get('error', 'not run')}")
    if why:
        L.append("Dropped: " + "; ".join(why) + ".")
    if s.get("dsr_dev") is not None:
        L.append(f"Deflated Sharpe of the chosen variant on DEV (information): {s['dsr_dev']}.")
    L.append("")


def summary_lines(res):
    out = [f"{'#':>2} {'strategy':<13} {'HIST n':>6} {'HIST PF':>7} {'DEV n':>6} {'DEV PF':>6}  {'rule':<34} {'H1':<4} {'H2':<4} "
           f"{'learner':<14} verdict"]
    for i, name in enumerate(res["order"], 1):
        s = res["strategies"][name]
        hp, dp = s["all_days"]["periods"]["HIST"], s["all_days"]["periods"]["DEV"]
        rb = s["rule"]
        h1 = "-" if rb.get("rule") is None else ("PASS" if rb["holdout1"]["pass"] else "fail")
        h2 = "-" if rb.get("rule") is None or not rb["holdout1"]["pass"] else ("PASS" if rb["holdout2"]["pass"] else "fail")
        lm = ",".join(m for m in MODELS if (s["learner"]["models"].get(m) or {}).get("survives")) or "none"
        out.append(f"{i:>2} {name:<13} {hp['trades']:>6} {_f(hp.get('pf'), 2):>7} {dp['trades']:>6} {_f(dp.get('pf'), 2):>6}  "
                   f"{_rule_txt(rb.get('rule'))[:34]:<34} {h1:<4} {h2:<4} {lm:<14} {_variant_txt(s)}")
    for key, bv in (("survivors' book", res["book"]), ("everything unfiltered", res["unfiltered"])):
        if bv is None:
            out.append(f"{key}: no survivors")
            continue
        for w in ("hist", "dev", "mixed"):
            b = bv["windows"][w]["plain"]["book"]
            s = bv["windows"][w]["stop"]["book"]
            out.append(f"{key}, {bv['windows'][w]['label']}: {b['trades']} trades, total {_f(b.get('total'))}, per year "
                       f"{_f(b.get('avg_per_year'))}, max DD {_f(b.get('max_dd'))}, Sharpe {_f(b.get('sharpe'))}; with the $150 "
                       f"daily stop total {_f(s.get('total'))}")
    return out


def clean(o):
    """JSON-safe copy: inf -> "inf", NaN -> None, numpy scalars -> Python, tuples -> lists."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        x = float(o)
        return "inf" if math.isinf(x) and x > 0 else "-inf" if math.isinf(x) else None if math.isnan(x) else x
    if isinstance(o, date):
        return o.isoformat()
    return o
