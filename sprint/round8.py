"""sprint/round8.py - round 8's readouts (SPRINT_PLAN Amendment 10 with Addenda 10.1, 10.2 and 10.3, pre-registered
2026-11-01 before any round-8 code or run). Research only: it reads trade files and the share / option-pass results, and
never trades. Every number is a BACKTEST; option numbers are labeled MODELED (HIST, BS with run 4's calibration) or REAL
(DEV, Alpaca option prices); share numbers are real stock bars throughout.

Sections and the exact pre-registered bars:
  Part A (shares): A1 noise_sh, A2 last30, A3 gapfade_vix; primary, long-only (own pass line) and the secondary variants
    (vol-sized A1, Gao A2, reported with the same checks as information); Part A's 7-item bar (sprint/shares.pass_bar);
    by year and symbol, months and weeks green, longest losing-month run, worst month, trades per day, daily correlation
    with FIN-H (every HIST + DEV session: sessions both could trade; HIST and DEV also shown apart).
  A3's option twins (Amendment 10 on 0DTE d55-75t65, Addendum 10.1 on n1d55-75t65) and A-opt (A1 on d55-75t65 /
    n1d55-75t65): DEV REAL, at least 40 trades, PF >= 1.25, PF 2x > 1.0, expectancy > 0 (10.1's A-opt bar; applied to the
    0DTE A3 twin too, labeled). HIST MODELED shown as information.
  Part B: FIN-H = run 7's otm_c_1100 (factory run 012) with f_rvol >= 1.06.
    B2 confidence sizing on the run-7 sleeves otm_c_1030 / otm_c_1100 / otm_c_1200 (factory runs 011/012/013) after
      f_rvol >= 1.06: sprint/learn's logit (Amendment 3 settings) walk-forward, 24 training months, on the 25 features;
      at each monthly refit the terciles of the TRAINING trades' predicted P(win) (numpy.quantile 1/3, 2/3); out of sample
      P <= lower cut -> skip, P >= upper cut -> 2 contracts, otherwise 1 (bottom checked first). Pass per sleeve, on DEV
      (REAL) and on 2018-01..2024-01 (MODELED), all of: (a) P/L per contract traded above the flat 1-contract rule's;
      (b) daily Sharpe (every session of the window, 0 on days without a trade, mean / sd x sqrt(252)) above the flat
      rule's; (c) PF 2x > 1.0. Both sides use the same trades (the out-of-sample ones in the window).
    B3 newhigh_c (engine runs, d03-12t07, -95% stop, all out 15:25): HIST 2016-2023 (MODELED) >= 60 trades, PF >= 1.25,
      PF 2x > 1.0, profitable in >= 5 of 8 years, positive without the best 5 trades; DEV (REAL) >= 40, PF >= 1.25, PF 2x >
      1.0. Beside FIN-H on the same days (days both traded): win rate, average loss, total without the best day.
    B4 FIN-H's entry (time_1100 calls, rvol >= 1.06) on n1d03-12t07 and d03-12t07 with exits (i) -95% stop, (ii) -50%,
      (iii) -50% + gb50, (iv) -50% + target +100%: B3's bars per variant; "steadier than FIN-H" on DEV REAL against FIN-H's
      0DTE exit (i) (this run's b4_d03_i) on the same days: more months green, total without the best day above FIN-H's
      (run 7's figure: +$57.82), smaller average loss.
  Part D: shares D1-D6 (Part A's bar; D5 also above every made-up-level seed's expectancy); option twins on d40-55t45 and
    n1d40-55t45: the 12-cell grid chosen per rule and contract on HIST 2016-01-04..2019-12-31 ONLY (the highest PF among
    cells with >= 60 discovery trades; ties: more trades, then the smaller stop, then the smaller target, none last; no
    cell with 60 trades = no choice), frozen, then holdout 1 = HIST 2020-01-01..2024-01-31 (MODELED: >= 60 trades, PF >=
    1.25, PF 2x > 1.0, profitable in >= 3 of 2020-2023 among years with 10+ trades, positive without the best 5 trades)
    and holdout 2 = DEV (REAL: >= 40 trades, PF >= 1.25, PF 2x > 1.0); survives when both pass. All 12 cells shown in
    every window with win rate and break-even win rate (|avg loss| / (avg win + |avg loss|)). The signal exit is reported
    with B3's bars. Matched random: shares by the random-direction test; options by the random-side twin (same exits).
  The book: FIN-H (1 contract), each Part B variant that passes (B2 sized sleeves, B3, B4) and each Part A rule whose
    primary (else long-only) variant passes (shares at $10,000 a trade). A Part A rule adds steadiness only if its daily
    P/L correlation with FIN-H is below 0.3. Windows: 2018-01-02..2024-01-31 (option sleeves MODELED, shares real), DEV
    REAL, and one line labeled "mixed". Reported: total and per year, max drawdown, months and weeks green, the longest
    losing-month run, the worst month, each sleeve's share of the total and the correlation matrix. Literal reading: the
    book was defined in Amendment 10 before Addenda 10.1-10.3, so D and A-opt survivors are reported, not booked.
  Trials: round 8 = 192 (Amendment 10's 13 + 10.1's 11 + 10.3's Part D 168). Deflated Sharpe (information) on DEV daily
    P/L with N = the run logs' row count + 192 (literal: the run logs already hold this round's engine runs, so N double-
    counts them; it only makes the haircut stricter) and the trial-Sharpe variance over every DEV variant scored here.
"""
import math
import statistics
from collections import defaultdict
from datetime import date

import numpy as np

from . import book, features, learn, periods, shares
from . import modeled as MD
from . import report as R
from .factory import clean, pf_of  # noqa: F401  (clean re-exported for the tool)

HIST_A, HIST_B = periods.HIST[0].isoformat(), periods.HIST[1].isoformat()
DEV_A, DEV_B = periods.DEV[0].isoformat(), periods.DEV[1].isoformat()
HIST_2023 = (HIST_A, "2023-12-31")
DISC = (HIST_A, "2019-12-31")
H1 = ("2020-01-01", HIST_B)
BOOK_HIST = ("2018-01-02", HIST_B)
B2_HIST = ("2018-01-02", HIST_B)
FINH_REF_WO_BEST_DAY = 57.82
TRAIN_MONTHS = 24
B2_SLEEVES = ("otm_c_1030", "otm_c_1100", "otm_c_1200")
B4_EXITS = {"i": "fixed -95% stop, no target (FIN-H's own)", "ii": "fixed -50% stop, no target",
            "iii": "fixed -50% stop + gb50 trail", "iv": "fixed -50% stop + fixed target +100%"}
B4_CONTRACTS = ("d03-12t07", "n1d03-12t07")
TRIALS = {"A shares (3 rules x 2 sides + 2 secondary)": 8, "A3 option twin": 1, "B2 (3 sleeves) + B3": 4,
          "B4 (4 exits x 2 contracts)": 8, "A-opt": 3, "D shares (6 rules x 2 sides)": 12,
          "D options (6 rules x 2 contracts x 13 exits)": 156}
assert sum(TRIALS.values()) == 192
YEARS = shares.YEARS
SRC_OF_YEAR = {n: ("HIST" if b <= HIST_B else "DEV") for n, a, b in YEARS}
LAB = {"HIST": "MODELED", "DEV": "REAL"}


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), n)


def _pfr(x):
    return -1.0 if x is None else (math.inf if isinstance(x, float) and math.isinf(x) else float(x))


def day_of(r):
    return str(r["day"])[:10]


def in_win(rows, a, b):
    return [r for r in rows if a <= day_of(r) <= b]


def ordered(rows):
    return sorted(rows, key=lambda r: (day_of(r), int(float(r.get("entry_idx") or 0)) if r.get("entry_idx") not in (None, "") else 0,
                                       str(r.get("symbol")), str(r.get("entry_time") or "")))


def ostats(rows, n_sessions=None):
    """Per-window option numbers (dollars per 1 contract), with the break-even win rate."""
    rows = ordered(rows)
    p = np.array([float(r["pnl"]) for r in rows])
    out = {"trades": len(rows), "per_session": round(len(rows) / n_sessions, 3) if n_sessions else None}
    if not len(rows):
        return out
    p2 = np.array([float(r.get("pnl_2x", r["pnl"])) for r in rows])
    w, lo = p[p > 0], p[p < 0]
    eq = np.cumsum(p)
    dd = float((eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min())
    aw, al = (float(w.mean()) if len(w) else None), (float(lo.mean()) if len(lo) else None)
    by_m, by_d = defaultdict(float), defaultdict(float)
    for r, x in zip(rows, p):
        by_m[day_of(r)[:7]] += x
        by_d[day_of(r)] += x
    dvals = sorted(by_d.values(), reverse=True)
    out.update({"win_rate": round(len(w) / len(p), 3), "avg_win": _r(aw), "avg_loss": _r(al),
                "be_win_rate": round(abs(al) / (aw + abs(al)), 3) if aw is not None and al is not None else None,
                "expectancy": _r(p.mean()), "pf": pf_of(p), "pf_2x": pf_of(p2), "total": _r(p.sum()), "total_2x": _r(p2.sum()),
                "max_dd": _r(min(dd, 0.0)), "without_best5": _r(p.sum() - np.sort(p)[::-1][:5].sum()),
                "without_best_day": _r(p.sum() - dvals[0]), "months_green": sum(1 for v in by_m.values() if v > 0),
                "months": len(by_m)})
    return out


def frame_groups(df):
    """{(study, exit): {"day": str array, "pnl", "pnl_2x"}} of an option-pass frame, each in trade order (day, entry bar,
    symbol). Arrays, not dicts: the HIST pass holds millions of rows."""
    if df is None or not len(df):
        return {}
    d = df.sort_values(["day", "entry_idx", "symbol"], kind="stable")
    out = {}
    for (st, ex), g in d.groupby(["study", "exit"], observed=True, sort=False):
        out[(str(st), str(ex))] = {"day": g["day"].astype(str).to_numpy().astype("U10"), "pnl": g["pnl"].to_numpy(float),
                                   "pnl_2x": g["pnl_2x"].to_numpy(float)}
    return out


EMPTY = {"day": np.array([], dtype="U10"), "pnl": np.zeros(0), "pnl_2x": np.zeros(0)}


def sub(a, lo, hi):
    a = a or EMPTY
    m = (a["day"] >= lo) & (a["day"] <= hi)
    return {k: v[m] for k, v in a.items()}


def ostats_a(a, n_sessions=None):
    """ostats on arrays (the same numbers as ostats on the same trades in the same order)."""
    a = a or EMPTY
    p, p2, day = a["pnl"], a["pnl_2x"], a["day"]
    out = {"trades": int(len(p)), "per_session": round(len(p) / n_sessions, 3) if n_sessions else None}
    if not len(p):
        return out
    w, lo = p[p > 0], p[p < 0]
    eq = np.cumsum(p)
    dd = float((eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min())
    aw, al = (float(w.mean()) if len(w) else None), (float(lo.mean()) if len(lo) else None)
    mk, mi = np.unique(day.astype("U7"), return_inverse=True)
    mnet = np.bincount(mi, weights=p, minlength=len(mk))
    dk, di = np.unique(day, return_inverse=True)
    dnet = np.bincount(di, weights=p, minlength=len(dk))
    out.update({"win_rate": round(len(w) / len(p), 3), "avg_win": _r(aw), "avg_loss": _r(al),
                "be_win_rate": round(abs(al) / (aw + abs(al)), 3) if aw is not None and al is not None else None,
                "expectancy": _r(p.mean()), "pf": pf_of(p), "pf_2x": pf_of(p2), "total": _r(p.sum()), "total_2x": _r(p2.sum()),
                "max_dd": _r(min(dd, 0.0)), "without_best5": _r(p.sum() - np.sort(p)[::-1][:5].sum()),
                "without_best_day": _r(p.sum() - dnet.max()), "months_green": int((mnet > 0).sum()), "months": int(len(mk))})
    return out


def years_net_a(a, years):
    a = a or EMPTY
    y = a["day"].astype("U4")
    out = {}
    for yr in years:
        m = y == str(yr)
        out[str(yr)] = {"trades": int(m.sum()), "net": _r(a["pnl"][m].sum()) if m.any() else 0.0}
    return out


def rows_to_a(rows):
    rows = ordered(rows)
    return {"day": np.array([day_of(r) for r in rows], dtype="U10"), "pnl": np.array([float(r["pnl"]) for r in rows]),
            "pnl_2x": np.array([float(r.get("pnl_2x", r["pnl"])) for r in rows])}


def years_net(rows, years):
    out = {}
    for y in years:
        ys = [r for r in rows if day_of(r)[:4] == str(y)]
        out[str(y)] = {"trades": len(ys), "net": _r(sum(float(r["pnl"]) for r in ys)) if ys else 0.0}
    return out


def _as_a(x):
    return x if isinstance(x, dict) and isinstance(x.get("pnl"), np.ndarray) else rows_to_a(x or [])


def b3_bar(rows_hist, rows_dev):
    """B3's bars (also B4's and the D signal exit's): HIST 2016-2023 MODELED and DEV REAL. Rows or arrays."""
    ah, ad = _as_a(rows_hist), _as_a(rows_dev)
    h = sub(ah, *HIST_2023)
    sh = ostats_a(h)
    yrs = years_net_a(h, range(2016, 2024))
    up = sum(1 for v in yrs.values() if (v["net"] or 0) > 0)
    ch = [("HIST: at least 60 trades", sh["trades"] >= 60), ("HIST: PF >= 1.25", _pfr(sh.get("pf")) >= 1.25),
          ("HIST: PF 2x > 1.0", _pfr(sh.get("pf_2x")) > 1.0), (f"HIST: profitable in at least 5 of 8 years ({up} of 8)", up >= 5),
          ("HIST: positive without the best 5 trades", (sh.get("without_best5") or 0) > 0)]
    sd = ostats_a(sub(ad, DEV_A, DEV_B))
    cd = [("DEV: at least 40 trades", sd["trades"] >= 40), ("DEV: PF >= 1.25", _pfr(sd.get("pf")) >= 1.25),
          ("DEV: PF 2x > 1.0", _pfr(sd.get("pf_2x")) > 1.0)]
    return {"hist": sh, "hist_years": yrs, "dev": sd, "checks": ch + cd, "pass": all(ok for _, ok in ch + cd),
            "jan2024": ostats_a(sub(ah, "2024-01-01", HIST_B))}


def first_fail(checks):
    for n, ok in checks:
        if not ok:
            return n
    return None


# ---------------------------------------------------------------- Part A
def part_a(sh_trades, finh_daily, sessions):
    out = {}
    hist_days = book.sessions_between(HIST_A, HIST_B)
    for rule in shares.PART_A:
        o = {}
        names = [rule, rule + "_lo"] + ([shares.SECONDARY[rule]] if rule in shares.SECONDARY else [])
        for v in names:
            tr = sh_trades.get(v, [])
            pb = shares.pass_bar(tr, sessions)
            d = shares.daily(tr, sessions)
            n_h = len(hist_days)
            o[v] = {"pass_bar": pb, "years": shares.years_table(tr),
                    "by_symbol": {s: shares.stats([t for t in tr if t["symbol"] == s]) for s in sorted({t["symbol"] for t in tr})},
                    "by_side": {s: shares.stats([t for t in tr if t["side"] == s]) for s in ("L", "S") if any(t["side"] == s for t in tr)},
                    "corr_finh": {"all": shares.corr(d, finh_daily), "HIST": shares.corr(d[:n_h], finh_daily[:n_h]),
                                  "DEV": shares.corr(d[n_h:], finh_daily[n_h:])},
                    "role": "primary" if v == rule else ("long-only" if v.endswith("_lo") else "secondary (information)")}
        out[rule] = o
    return out


# ---------------------------------------------------------------- option-pass frames
def opt_bar(rows):
    """A-opt's bar on DEV REAL: >= 40 trades, PF >= 1.25, PF 2x > 1.0, expectancy > 0. Rows or arrays."""
    s = ostats_a(sub(_as_a(rows), DEV_A, DEV_B))
    ch = [("DEV: at least 40 trades", s["trades"] >= 40), ("DEV: PF >= 1.25", _pfr(s.get("pf")) >= 1.25),
          ("DEV: PF 2x > 1.0", _pfr(s.get("pf_2x")) > 1.0), ("DEV: expectancy > 0", (s.get("expectancy") or 0) > 0)]
    return {"dev": s, "checks": ch, "pass": all(ok for _, ok in ch)}


def opt_exit(st):
    return "share_signal" if st["entry"] == "noise_sh" else "hold"


def a_opt(gh, gd, studies, sh_trades):
    """gh, gd: frame_groups of the HIST and DEV option-pass frames."""
    out = {}
    for st in studies:
        if st["family"] not in ("A-opt", "A3"):
            continue
        k = (st["name"], opt_exit(st))
        rule = "noise_sh" if st["entry"] == "noise_sh" else "gapfade_vix"
        out[st["name"]] = {"entry": st["entry"], "contract": st["contract"], "family": st["family"], "bar": opt_bar(gd.get(k, EMPTY)),
                           "hist_info": ostats_a(sub(gh.get(k), HIST_A, HIST_B)),
                           "shares_dev": shares.stats(in_win(sh_trades.get(rule, []), DEV_A, DEV_B)),
                           "shares_hist": shares.stats(in_win(sh_trades.get(rule, []), HIST_A, HIST_B))}
    return out


# ---------------------------------------------------------------- Part D options
def cell_key(cell):
    """Tie order for the grid choice: smaller stop first, then smaller target, none last."""
    s, t = cell[1], cell[2]
    return (s, math.inf if t is None else t)


def choose_cell(cells_disc, min_n=60):
    """cells_disc: [(cell id, stop, target, discovery stats)]. Highest PF among cells with >= min_n trades; ties: more trades,
    then the smaller stop, then the smaller target (none last). None when no cell has min_n trades."""
    elig = [c for c in cells_disc if c[3]["trades"] >= min_n and c[3].get("pf") is not None]
    if not elig:
        return None
    best = min(elig, key=lambda c: (-_pfr(c[3]["pf"]), -c[3]["trades"]) + cell_key(c))
    return best[0]


def holdout1_d(rows):
    a = _as_a(rows)
    s = ostats_a(a)
    yrs = years_net_a(a, (2020, 2021, 2022, 2023))
    green = sum(1 for v in yrs.values() if v["trades"] >= 10 and (v["net"] or 0) > 0)
    ch = [("H1: at least 60 trades", s["trades"] >= 60), ("H1: PF >= 1.25", _pfr(s.get("pf")) >= 1.25),
          ("H1: PF 2x > 1.0", _pfr(s.get("pf_2x")) > 1.0),
          (f"H1: profitable in at least 3 of 2020-2023, years with 10+ trades ({green} of 4)", green >= 3),
          ("H1: positive without the best 5 trades", (s.get("without_best5") or 0) > 0)]
    return {"stats": s, "years": yrs, "checks": ch, "pass": all(ok for _, ok in ch)}


def holdout2_d(rows):
    s = ostats_a(_as_a(rows))
    ch = [("H2: at least 40 trades", s["trades"] >= 40), ("H2: PF >= 1.25", _pfr(s.get("pf")) >= 1.25),
          ("H2: PF 2x > 1.0", _pfr(s.get("pf_2x")) > 1.0)]
    return {"stats": s, "checks": ch, "pass": all(ok for _, ok in ch)}


def d_options(opt, studies, grid, groups=None):
    """Per D study (rule x contract): all 12 cells in every window, the frozen choice (2016-2019 only) and its holdouts, the
    signal exit, and the matched random-side twin. opt: {"HIST", "DEV": option-pass frames} (or groups = (gh, gd) from
    frame_groups)."""
    gh, gd = groups if groups is not None else (frame_groups(opt.get("HIST")), frame_groups(opt.get("DEV")))
    out = {}
    rnd = {(s["rule"], s["contract"]): s["name"] for s in studies if s["family"] == "D" and s.get("random_seed") is not None}
    for st in studies:
        if st["family"] != "D" or st.get("random_seed") is not None:
            continue
        cells, win = [], {}
        for cid, s, t in grid:
            h, d = gh.get((st["name"], cid)), gd.get((st["name"], cid))
            win[cid] = {"stop": s, "target": t, "discovery": ostats_a(sub(h, *DISC)), "holdout1": ostats_a(sub(h, *H1)),
                        "holdout2": ostats_a(sub(d, DEV_A, DEV_B)), "_h1": sub(h, *H1), "_dev": sub(d, DEV_A, DEV_B)}
            cells.append((cid, s, t, win[cid]["discovery"]))
        chosen = choose_cell(cells)
        res = {"rule": st["rule"], "contract": st["contract"], "chosen": chosen,
               "cells": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in win.items()}}
        if chosen is None:
            res.update(survives=False, why_not="no cell kept 60 trades in 2016-2019")
        else:
            h1, h2 = holdout1_d(win[chosen]["_h1"]), holdout2_d(win[chosen]["_dev"])
            res.update(holdout1=h1, holdout2=h2, survives=h1["pass"] and h2["pass"],
                       why_not=None if h1["pass"] and h2["pass"] else (first_fail(h1["checks"]) if not h1["pass"] else first_fail(h2["checks"])))
        sh, sd = gh.get((st["name"], "signal"), EMPTY), gd.get((st["name"], "signal"), EMPTY)
        res["signal"] = b3_bar(sh, sd)
        rn = rnd.get((st["rule"], st["contract"]))
        if rn:
            rr = {}
            for cid in [g[0] for g in grid] + ["signal"]:
                rh, rd = gh.get((rn, cid)), gd.get((rn, cid))
                rr[cid] = {"hist": ostats_a(sub(rh, HIST_A, HIST_B)), "dev": ostats_a(sub(rd, DEV_A, DEV_B)), "disc": ostats_a(sub(rh, *DISC))}
            res["random"] = {"study": rn, "cells": rr}
        res["_signal_dev"] = sub(sd, DEV_A, DEV_B)
        res["_cells_dev"] = {cid: win[cid]["_dev"] for cid in win}
        out[st["name"]] = res
    return out


# ---------------------------------------------------------------- Part D shares
def d_shares(sh_trades, sessions):
    out = {}
    from . import ind5
    for rule in ind5.RULES:
        o = {}
        for v in (rule, rule + "_lo"):
            tr = sh_trades.get(v, [])
            o[v] = {"pass_bar": shares.pass_bar(tr, sessions), "years": shares.years_table(tr),
                    "by_symbol": {s: shares.stats([t for t in tr if t["symbol"] == s]) for s in sorted({t["symbol"] for t in tr})}}
        if rule == "conf_level_rsi":
            for v, base in ((rule, rule), (rule + "_lo", rule + "_lo")):
                real = o[v]["pass_bar"]["stats"].get("expectancy")
                fk = {}
                for sd in shares.FAKE_SEEDS:
                    name = f"conf_level_rsi_fake{sd}" if v == rule else f"conf_level_rsi_lo_fake{sd}"
                    fk[sd] = shares.stats(sh_trades.get(name, [])).get("expectancy")
                beat = real is not None and all(x is None or real > x for x in fk.values())
                o[v]["fake"] = {"expectancy": fk, "beats_all": bool(beat)}
                o[v]["pass_bar"]["checks"].append((f"beats every made-up-level seed's expectancy ({real} vs {fk})", bool(beat)))
                o[v]["pass_bar"]["pass"] = all(ok for _, ok in o[v]["pass_bar"]["checks"])
        out[rule] = o
    return out


# ---------------------------------------------------------------- Part B
def b2_sizing(rows, min_train_months=TRAIN_MONTHS):
    """Out-of-sample contracts (0/1/2) per trade for one sleeve's rule trades (HIST + DEV). Returns (rows with "contracts"
    for out-of-sample trades, info)."""
    names = features.FEATURES
    rows = sorted(rows, key=lambda r: (day_of(r), r.get("f_minute") or 0))
    mon = [day_of(r)[:7] for r in rows]
    months = sorted(set(mon))
    if len(months) <= min_train_months:
        return [], {"error": f"need more than {min_train_months} months with trades, have {len(months)}"}
    test_months = months[min_train_months:]
    X = features.matrix(rows, names)
    pnl = np.array([float(r["pnl"]) for r in rows])
    mon_a = np.array(mon)
    out, cuts = [], []
    for tm in test_months:
        tr = np.where(mon_a < tm)[0]
        te = np.where(mon_a == tm)[0]
        p = learn._prep_fit(X[tr])
        Ztr, Zte = learn._prep_apply(p, X[tr]), learn._prep_apply(p, X[te])
        if Ztr.shape[1] == 0:
            sizes = np.ones(len(te), int)
            q = (None, None)
        else:
            w, b = learn.fit_logit(Ztr, (pnl[tr] > 0).astype(float))
            ptr = 1.0 / (1.0 + np.exp(-np.clip(Ztr @ w + b, -30, 30)))
            pte = 1.0 / (1.0 + np.exp(-np.clip(Zte @ w + b, -30, 30)))
            q = tuple(float(x) for x in np.quantile(ptr, [1 / 3, 2 / 3]))
            sizes = np.where(pte <= q[0], 0, np.where(pte >= q[1], 2, 1))
        cuts.append({"month": tm, "lower": q[0], "upper": q[1], "train": len(tr), "test": len(te)})
        for i, sz in zip(te, sizes):
            out.append(dict(rows[i], contracts=int(sz)))
    return out, {"oos_from": test_months[0], "months": len(months), "refits": len(test_months), "cuts": cuts}


def _sharpe(d):
    d = np.asarray(d, float)
    return round(float(d.mean() / d.std() * math.sqrt(252)), 3) if len(d) > 1 and d.std() > 0 else None


def b2_window(sized, a, b):
    sel = [r for r in sized if a <= day_of(r) <= b]
    days = book.sessions_between(a, b)
    flat = [dict(r, pnl=float(r["pnl"]), pnl_2x=float(r.get("pnl_2x", r["pnl"]))) for r in sel]
    sz = [dict(r, pnl=float(r["pnl"]) * r["contracts"], pnl_2x=float(r.get("pnl_2x", r["pnl"])) * r["contracts"]) for r in sel if r["contracts"] > 0]
    n_c = sum(r["contracts"] for r in sel)
    per_c_sized = sum(r["pnl"] for r in sz) / n_c if n_c else None
    per_c_flat = sum(r["pnl"] for r in flat) / len(flat) if flat else None
    sh_s, sh_f = _sharpe(book._daily(sz, days)), _sharpe(book._daily(flat, days))
    pf2 = pf_of([r["pnl_2x"] for r in sz]) if sz else None
    ch = [(f"(a) P/L per contract traded above the flat rule's ({_r(per_c_sized)} vs {_r(per_c_flat)})",
           per_c_sized is not None and per_c_flat is not None and per_c_sized > per_c_flat),
          (f"(b) daily Sharpe above the flat rule's ({sh_s} vs {sh_f})", sh_s is not None and sh_f is not None and sh_s > sh_f),
          (f"(c) PF 2x > 1.0 ({pf2})", _pfr(pf2) > 1.0)]
    return {"window": f"{a}..{b}", "sessions": len(days), "trades": len(sel), "taken": len(sz), "contracts": n_c,
            "skipped": sum(1 for r in sel if r["contracts"] == 0), "doubled": sum(1 for r in sel if r["contracts"] == 2),
            "sized_total": _r(sum(r["pnl"] for r in sz)), "flat_total": _r(sum(r["pnl"] for r in flat)),
            "per_contract_sized": _r(per_c_sized), "per_contract_flat": _r(per_c_flat), "sharpe_sized": sh_s, "sharpe_flat": sh_f,
            "pf_2x_sized": pf2, "pf_2x_flat": pf_of([r["pnl_2x"] for r in flat]) if flat else None, "checks": ch,
            "pass": all(ok for _, ok in ch)}


def b2(sleeves):
    out, books = {}, {}
    for name, rows in sleeves.items():
        sized, info = b2_sizing(rows)
        if "error" in info:
            out[name] = {"error": info["error"], "pass": False}
            continue
        a_h = max(B2_HIST[0], info["oos_from"] + "-01")
        dev = b2_window([r for r in sized if r["_src"] == "DEV"], DEV_A, DEV_B)
        hst = b2_window([r for r in sized if r["_src"] == "HIST"], a_h, B2_HIST[1])
        out[name] = {"oos_from": info["oos_from"], "refits": info["refits"], "dev": dev, "hist": hst, "pass": dev["pass"] and hst["pass"],
                     "last_cuts": info["cuts"][-1] if info["cuts"] else None, "rule_trades": len(rows)}
        books[name] = [dict(r, pnl=float(r["pnl"]) * r["contracts"], pnl_2x=float(r.get("pnl_2x", r["pnl"])) * r["contracts"])
                       for r in sized if r["contracts"] > 0]
    return out, books


def same_days(a_rows, b_rows):
    days = {day_of(r) for r in a_rows} & {day_of(r) for r in b_rows}
    return [r for r in a_rows if day_of(r) in days], [r for r in b_rows if day_of(r) in days]


def b3(e8, finh):
    rows_h, rows_d = e8["HIST"].get("newhigh_c", []), e8["DEV"].get("newhigh_c", [])
    out = {"bar": b3_bar(rows_h, rows_d), "beside_finh": {}}
    for src, rows, fh in (("HIST", in_win(rows_h, *HIST_2023), in_win(finh["HIST"], *HIST_2023)),
                          ("DEV", in_win(rows_d, DEV_A, DEV_B), in_win(finh["DEV"], DEV_A, DEV_B))):
        a, b = same_days(rows, fh)
        out["beside_finh"][src] = {"newhigh_c": ostats(rows), "fin_h": ostats(fh), "newhigh_c_same_days": ostats(a),
                                   "fin_h_same_days": ostats(b), "common_days": len({day_of(r) for r in a})}
    return out


def b4(e8, finh):
    out = {}
    ref_h, ref_d = e8["HIST"].get("b4_d03_i", []), e8["DEV"].get("b4_d03_i", [])
    for c in B4_CONTRACTS:
        tag = "d03" if c == "d03-12t07" else "n1d03"
        for ex in B4_EXITS:
            blk = f"b4_{tag}_{ex}"
            h, d = e8["HIST"].get(blk, []), e8["DEV"].get(blk, [])
            bar = b3_bar(h, d)
            v, f = same_days(in_win(d, DEV_A, DEV_B), in_win(ref_d, DEV_A, DEV_B))
            sv, sf = ostats(v), ostats(f)
            ch = [(f"more months green than FIN-H 0DTE (i) on the same days ({sv.get('months_green')} vs {sf.get('months_green')})",
                   (sv.get("months_green") or 0) > (sf.get("months_green") or 0)),
                  (f"total without the best day above FIN-H's ({sv.get('without_best_day')} vs {sf.get('without_best_day')}; run 7: "
                   f"+{FINH_REF_WO_BEST_DAY})", sv.get("without_best_day") is not None and sf.get("without_best_day") is not None
                   and sv["without_best_day"] > sf["without_best_day"]),
                  (f"smaller average loss ({sv.get('avg_loss')} vs {sf.get('avg_loss')})",
                   sv.get("avg_loss") is not None and sf.get("avg_loss") is not None and abs(sv["avg_loss"]) < abs(sf["avg_loss"]))]
            out[blk] = {"contract": c, "exit": ex, "exit_text": B4_EXITS[ex], "bar": bar, "steadier": {"variant": sv, "fin_h": sf,
                        "checks": ch, "pass": bar["pass"] and all(ok for _, ok in ch), "common_days": len({day_of(r) for r in v})}}
    fh_dev = ostats(in_win(finh["DEV"], DEV_A, DEV_B))
    own = ostats(in_win(ref_d, DEV_A, DEV_B))
    out["_consistency"] = {"run7_finh_dev": fh_dev, "b4_d03_i_dev": own,
                           "same": fh_dev.get("trades") == own.get("trades") and fh_dev.get("total") == own.get("total")}
    return out


# ---------------------------------------------------------------- the book
def _weeks(days, d):
    bw = defaultdict(float)
    for x, v in zip(days, d):
        y, w, _ = date.fromisoformat(x).isocalendar()
        bw[f"{y}-W{w:02d}"] += v
    return bw


def wstats_x(rows, days):
    from .factory import wstats
    out = wstats(rows, days)
    d = book._daily(rows, days)
    bm = defaultdict(float)
    for x, v in zip(days, d):
        bm[x[:7]] += v
    run = best = 0
    for m in sorted(bm):
        run = run + 1 if bm[m] < 0 else 0
        best = max(best, run)
    bw = _weeks(days, d)
    out["weeks_green"] = f"{sum(1 for v in bw.values() if v > 0)}/{len(bw)}"
    out["longest_losing_months"] = best
    return out


def book_window(by_sleeve, days):
    dset = set(days)
    sub = {k: [r for r in v if day_of(r) in dset] for k, v in by_sleeve.items()}
    allr = [dict(r, run_id=k) for k, v in sub.items() for r in v]
    out = {"sessions": len(days), "sleeves": {k: wstats_x(v, days) for k, v in sub.items()}, "book": wstats_x(allr, days)}
    tot = out["book"].get("total") or 0.0
    for k, s in out["sleeves"].items():
        s["share_of_total"] = _r((s.get("total") or 0.0) / tot, 3) if tot else None
    keys = sorted(sub)
    M = np.array([book._daily(sub[k], days) for k in keys]) if keys else np.zeros((0, len(days)))
    with np.errstate(invalid="ignore", divide="ignore"):
        C = np.atleast_2d(np.corrcoef(M)) if len(keys) > 1 else np.ones((len(keys), len(keys)))
    out["corr"] = {k: {k2: (None if math.isnan(C[i, j]) else round(float(C[i, j]), 2)) for j, k2 in enumerate(keys)} for i, k in enumerate(keys)}
    return out


def book_views(by_sleeve, kinds):
    hist_days = book.sessions_between(*BOOK_HIST)
    dev_days = book.sessions_between(DEV_A, DEV_B)
    out = {"windows": {
        "hist": {"label": f"{BOOK_HIST[0]}..{BOOK_HIST[1]} (option sleeves MODELED, shares real)", "res": book_window(by_sleeve, hist_days)},
        "dev": {"label": f"{DEV_A}..{DEV_B} DEV, REAL", "res": book_window(by_sleeve, dev_days)},
        "mixed": {"label": "mixed: modeled 2018-2024 options + real 2024-2026 options (shares real throughout)",
                  "res": book_window(by_sleeve, hist_days + dev_days)}}, "years": {}, "kinds": kinds}
    for name, a, b in YEARS:
        if b < BOOK_HIST[0]:
            continue
        a2 = max(a, BOOK_HIST[0]) if b <= HIST_B else max(a, DEV_A)
        b2_ = min(b, HIST_B) if b <= HIST_B else min(b, DEV_B)
        days = book.sessions_between(a2, b2_)
        r = book_window(by_sleeve, days)
        out["years"][name] = {"prices": LAB[SRC_OF_YEAR[name]], "book": r["book"],
                              "sleeves": {k: {"total": v.get("total"), "trades": v.get("trades")} for k, v in r["sleeves"].items()}}
    return out


# ---------------------------------------------------------------- trials and the deflated Sharpe
def _daily_a(a, dev_days):
    a = _as_a(a)
    idx = {d: i for i, d in enumerate(dev_days)}
    v = np.zeros(len(dev_days))
    for d, p in zip(a["day"], a["pnl"]):
        i = idx.get(str(d))
        if i is not None:
            v[i] += p
    return [float(x) for x in v], len(a["pnl"])


def dsr_table(variants_dev, n_prior, dev_days):
    """variants_dev: {name: DEV rows or arrays}. Returns (table, sr_var, N), N = the run logs' rows + 192."""
    daily = {k: _daily_a(v, dev_days) for k, v in variants_dev.items()}
    srs = {k: R.sharpe(d) for k, (d, n) in daily.items()}
    vals = [x for x in srs.values() if x is not None]
    sr_var = statistics.pvariance(vals) if len(vals) > 1 else 0.0
    n = int(n_prior) + 192
    tab = {k: R.deflated_sharpe(d, n, sr_var) if cnt else None for k, (d, cnt) in daily.items()}
    return tab, round(sr_var, 6), n


# ---------------------------------------------------------------- everything
def run(sh_trades, finh, sleeves, e8, opt, studies, grid, n_prior=0):
    """sh_trades: {variant: [share trades]}; finh: {"HIST", "DEV": FIN-H rows}; sleeves: {B2 sleeve: rule rows with _src};
    e8: {"HIST"|"DEV": {block: rows}} (round-8 engine runs: B3, B4); opt: {"HIST"|"DEV": option-pass frame};
    studies: option-pass studies; grid: [(cell id, stop, target)]."""
    sessions = shares.all_sessions()
    finh_all = in_win(finh["HIST"], HIST_A, HIST_B) + in_win(finh["DEV"], DEV_A, DEV_B)
    finh_daily = book._daily(finh_all, sessions)
    gh, gd = frame_groups(opt.get("HIST")), frame_groups(opt.get("DEV"))
    res = {"part_a": part_a(sh_trades, finh_daily, sessions), "a_opt": a_opt(gh, gd, studies, sh_trades)}
    b2r, b2books = b2(sleeves)
    res["b2"], res["b3"], res["b4"] = b2r, b3(e8, finh), b4(e8, finh)
    res["d_shares"] = d_shares(sh_trades, sessions)
    dop = d_options(opt, studies, grid, groups=(gh, gd))
    res["finh"] = {"HIST": ostats(in_win(finh["HIST"], HIST_A, HIST_B)), "DEV": ostats(in_win(finh["DEV"], DEV_A, DEV_B))}
    # the book
    sleeves_b, kinds = {"FIN-H": finh_all}, {"FIN-H": "option (FIN-H, 1 contract)"}
    for k, v in b2r.items():
        if v.get("pass"):
            sleeves_b[f"B2 {k}"] = b2books[k]
            kinds[f"B2 {k}"] = "option (confidence-sized)"
    if res["b3"]["bar"]["pass"]:
        sleeves_b["B3 newhigh_c"] = e8["HIST"].get("newhigh_c", []) + e8["DEV"].get("newhigh_c", [])
        kinds["B3 newhigh_c"] = "option"
    for k, v in res["b4"].items():
        if not k.startswith("_") and v["bar"]["pass"]:
            sleeves_b[f"B4 {k}"] = e8["HIST"].get(k, []) + e8["DEV"].get(k, [])
            kinds[f"B4 {k}"] = "option"
    steady = {}
    for rule, o in res["part_a"].items():
        pick = rule if o[rule]["pass_bar"]["pass"] else (rule + "_lo" if o[rule + "_lo"]["pass_bar"]["pass"] else None)
        if pick:
            sleeves_b[f"A {pick}"] = sh_trades.get(pick, [])
            kinds[f"A {pick}"] = "shares ($10,000 a trade)"
            c = o[pick]["corr_finh"]["all"]
            steady[pick] = {"corr_finh": c, "adds_steadiness": c is not None and c < 0.3}
    res["book"] = book_views(sleeves_b, kinds)
    res["book"]["steadiness"] = steady
    # trials and the deflated Sharpe
    dev_days = book.sessions_between(DEV_A, DEV_B)
    var = {}
    for rule, o in res["part_a"].items():
        for v in o:
            var[f"A {v}"] = in_win(sh_trades.get(v, []), DEV_A, DEV_B)
    for rule, o in res["d_shares"].items():
        for v in o:
            var[f"D shares {v}"] = in_win(sh_trades.get(v, []), DEV_A, DEV_B)
    for k in res["a_opt"]:
        st = next(s for s in studies if s["name"] == k)
        var[f"opt {k}"] = sub(gd.get((k, opt_exit(st))), DEV_A, DEV_B)
    for k, v in b2books.items():
        var[f"B2 {k}"] = in_win(v, DEV_A, DEV_B)
    var["B3 newhigh_c"] = in_win(e8["DEV"].get("newhigh_c", []), DEV_A, DEV_B)
    for k in res["b4"]:
        if not k.startswith("_"):
            var[f"B4 {k}"] = in_win(e8["DEV"].get(k, []), DEV_A, DEV_B)
    for k, v in dop.items():
        for cid, rows in v["_cells_dev"].items():
            var[f"D {k} {cid}"] = rows
        var[f"D {k} signal"] = v["_signal_dev"]
    tab, sr_var, n = dsr_table(var, n_prior, dev_days)
    for k, v in dop.items():
        v["dsr_chosen"] = tab.get(f"D {k} {v['chosen']}") if v["chosen"] else None
        v["dsr_signal"] = tab.get(f"D {k} signal")
        for kk in ("_signal_dev", "_cells_dev"):
            v.pop(kk, None)
    res["d_options"] = dop
    res["trials"] = {"parts": TRIALS, "round8": 192, "prior_in_run_logs": int(n_prior), "total_for_dsr": n, "sr_var": sr_var,
                     "dev_variants_scored": len(var)}
    res["dsr"] = {k: v for k, v in tab.items() if not k.startswith("D ") or k.endswith(" signal")}
    res["dsr_d_chosen"] = {k: v["dsr_chosen"] for k, v in dop.items()}
    return res


# ---------------------------------------------------------------- the report
def _f(x, n=2):
    return R.fmt(x, n)


def _row(cells):
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _head(cols):
    return _row(cols) + "\n|" + "---|" * len(cols)


def _yn(ok):
    return "PASS" if ok else "fail"


def _checks(L, checks):
    for n_, ok in checks:
        L.append(f"- [{'x' if ok else ' '}] {n_}")


def _pct(x):
    return "-" if x is None else f"{100 * x:.1f}"


SH_COLS = ("window", "trades", "win %", "avg win $", "avg loss $", "exp $", "exp bps", "exp 2x $", "PF", "PF 2x", "total $", "max DD $")


def _sh_cells(name, s):
    return [name, s.get("trades", 0), _pct(s.get("win_rate")), _f(s.get("avg_win")), _f(s.get("avg_loss")), _f(s.get("expectancy")),
            _f(s.get("exp_bps"), 2), _f(s.get("expectancy_2x")), _f(s.get("pf"), 3), _f(s.get("pf_2x"), 3), _f(s.get("total")),
            _f(s.get("max_dd"))]


OP_COLS = ("trades", "win %", "BE win %", "avg win $", "avg loss $", "exp $", "PF", "PF 2x", "total $", "w/o best 5 $")


def _op_cells(s):
    return [s.get("trades", 0), _pct(s.get("win_rate")), _pct(s.get("be_win_rate")), _f(s.get("avg_win")), _f(s.get("avg_loss")),
            _f(s.get("expectancy")), _f(s.get("pf"), 3), _f(s.get("pf_2x"), 3), _f(s.get("total")), _f(s.get("without_best5"))]


def _share_variant_md(L, v, o):
    pb = o["pass_bar"]
    st = pb["steadiness"]
    L.append(f"**{v}** ({o.get('role', '')}): Part A bar **{_yn(pb['pass'])}**. {pb['stats']['trades']} trades "
             f"({_f(pb['stats'].get('per_session'), 3)} a session), expectancy ${_f(pb['stats'].get('expectancy'))} "
             f"({_f(pb['stats'].get('exp_bps'))} bps), at 2x costs ${_f(pb['stats'].get('expectancy_2x'))}, PF {_f(pb['stats'].get('pf'), 3)}, "
             f"total ${_f(pb['stats'].get('total'))}. Months green {st['months_green']}/{st['months']}, weeks green "
             f"{st['weeks_green']}/{st['weeks']}, longest losing-month run {st['longest_losing_months']}, worst month "
             f"{st['worst_month']}." + (f" Daily correlation with FIN-H: all {o['corr_finh']['all']}, HIST {o['corr_finh']['HIST']}, "
                                        f"DEV {o['corr_finh']['DEV']}." if "corr_finh" in o else "") + "\n")
    _checks(L, pb["checks"])
    L.append("")
    L.append(_head(SH_COLS))
    for k, s in o["years"].items():
        L.append(_row(_sh_cells(k, s)))
    for k, s in o.get("by_symbol", {}).items():
        L.append(_row(_sh_cells(f"symbol {k}", s)))
    for k, s in o.get("by_side", {}).items():
        L.append(_row(_sh_cells("longs" if k == "L" else "shorts", s)))
    L.append("")


def render(res, meta):
    tr = res["trials"]
    L = [f"# Round 8: steady share rules, a sharper big-day filter, indicators and levels ({meta.get('today')})\n",
         "SPRINT_PLAN Amendment 10 with Addenda 10.1, 10.2 and 10.3 (pre-registered 2026-11-01, before any round-8 code or run). "
         "Every number is a **BACKTEST**. Not financial advice: evidence for Nick to decide.\n",
         f"- **Shares** (Part A, Part D shares): real Alpaca stock 1-minute bars, HIST 2016-01-04..2024-01-31 and DEV 2024-08-01..2026-06-30; "
         "$10,000 notional a trade, fills at the next bar's open +/- $0.01 a share (2x = $0.02), out at the 15:59 bar's close (12:59 on "
         "early-close days). No option model.",
         f"- **Options, HIST 2016-2024: {MD.LABEL}** (run 4's calibration). Next-expiry HIST tapes are MODELED at the next NYSE session and "
         "**NOT VALIDATED** against real prices. **Options, DEV 2024-08..2026-06: REAL** Alpaca option prices. 1 contract, desk fills, 2% "
         "half-spread (MODELED-SPREAD, $0.005 floor), $0.65 per contract per side, all out 15:25.",
         "- 2024 is never one number for options: Jan 2024 is MODELED, Aug-Dec 2024 is REAL. L1 and L2 were never read.",
         f"- Files: {meta.get('files_note', '')}",
         f"- Specs: `{meta.get('hist_spec')}` (sha256 {str(meta.get('hist_sha', ''))[:12]}), `{meta.get('dev_spec')}` (sha256 "
         f"{str(meta.get('dev_sha', ''))[:12]}). Run log: {meta.get('runlog_note', '-')}",
         f"- **Trials:** round 8 adds {tr['round8']} (" + ", ".join(f"{k} {v}" for k, v in tr["parts"].items()) + f"). Deflated Sharpe "
         f"(information only) uses N = {tr['total_for_dsr']} (run logs {tr['prior_in_run_logs']} + 192) and the Sharpe variance of "
         f"{tr['dev_variants_scored']} DEV variants.",
         "- Nothing here is promoted: a pass still needs a new versioned paper ledger, Nick's yes and 40 forward paper trades "
         "(CLAUDE.md step 5).\n"]
    if meta.get("warnings"):
        L.append("**Warnings:** " + " ".join(meta["warnings"]) + "\n")
    L.append("## Summary\n")
    L.append(_head(("item", "variant", "verdict", "key numbers")))
    for rule, o in res["part_a"].items():
        for v, x in o.items():
            s = x["pass_bar"]["stats"]
            L.append(_row([f"A {rule}", f"{v} ({x['role']})", _yn(x["pass_bar"]["pass"]) if x["role"] != "secondary (information)" else
                           f"({_yn(x['pass_bar']['pass'])}, information)", f"{s['trades']} trades, exp ${_f(s.get('expectancy'))}, "
                           f"2x ${_f(s.get('expectancy_2x'))}, corr FIN-H {x['corr_finh']['all']}"]))
    for k, o in res["a_opt"].items():
        d = o["bar"]["dev"]
        L.append(_row([o["family"], f"{k} ({o['entry']}, {o['contract']})", _yn(o["bar"]["pass"]) + " (DEV REAL)",
                       f"DEV {d['trades']} trades, exp ${_f(d.get('expectancy'))}, PF {_f(d.get('pf'), 3)}, PF 2x {_f(d.get('pf_2x'), 3)}"]))
    for k, o in res["b2"].items():
        if "error" in o:
            L.append(_row(["B2", k, "fail", o["error"]]))
            continue
        L.append(_row(["B2", k, _yn(o["pass"]), f"DEV {_yn(o['dev']['pass'])}, 2018-2024 MODELED {_yn(o['hist']['pass'])}; DEV per contract "
                       f"{_f(o['dev']['per_contract_sized'])} vs flat {_f(o['dev']['per_contract_flat'])}"]))
    b3b = res["b3"]["bar"]
    L.append(_row(["B3", "newhigh_c", _yn(b3b["pass"]), f"HIST {b3b['hist']['trades']} / PF {_f(b3b['hist'].get('pf'), 3)}; DEV "
                   f"{b3b['dev']['trades']} / PF {_f(b3b['dev'].get('pf'), 3)}"]))
    for k, o in res["b4"].items():
        if k.startswith("_"):
            continue
        L.append(_row(["B4", f"{k} ({o['contract']}, {o['exit_text']})", _yn(o["bar"]["pass"]) + ("; steadier than FIN-H: YES" if
                       o["steadier"]["pass"] else "; steadier than FIN-H: no"),
                       f"HIST {o['bar']['hist']['trades']} / PF {_f(o['bar']['hist'].get('pf'), 3)}; DEV {o['bar']['dev']['trades']} / PF "
                       f"{_f(o['bar']['dev'].get('pf'), 3)}"]))
    for rule, o in res["d_shares"].items():
        for v, x in o.items():
            s = x["pass_bar"]["stats"]
            L.append(_row([f"D shares", v, _yn(x["pass_bar"]["pass"]), f"{s['trades']} trades, exp ${_f(s.get('expectancy'))}, random-direction "
                           f"p {x['pass_bar']['random_p']}"]))
    for k, o in res["d_options"].items():
        ch = o["chosen"] or "no choice"
        L.append(_row(["D options", f"{k} ({o['rule']}, {o['contract']})", ("SURVIVES" if o["survives"] else "fail") +
                       f"; signal exit {_yn(o['signal']['pass'])}", f"chosen on 2016-2019: {ch}" + (
                           f"; H1 {_yn(o['holdout1']['pass'])}, H2 {_yn(o['holdout2']['pass'])}" if o["chosen"] else "")]))
    bk = res["book"]["windows"]
    for w in ("hist", "dev", "mixed"):
        b = bk[w]["res"]["book"]
        L.append(_row(["Book", bk[w]["label"], "-", f"total ${_f(b.get('total'))}, per year ${_f(b.get('avg_per_year'))}, max DD "
                       f"${_f(b.get('max_dd'))}, months green {b['months_green']}"]))
    L.append("")
    _part_a_md(L, res)
    _aopt_md(L, res)
    _part_b_md(L, res)
    _d_shares_md(L, res)
    _d_options_md(L, res)
    _book_md(L, res)
    L.append("## Trials and the deflated Sharpe\n")
    L.append(f"Round 8 = {tr['round8']} trials: " + "; ".join(f"{k}: {v}" for k, v in tr["parts"].items()) + f". N for the deflated Sharpe = "
             f"{tr['total_for_dsr']} (the run logs' {tr['prior_in_run_logs']} rows + 192; the run logs already hold this round's engine "
             f"runs, so N counts them twice, which only makes the haircut stricter). Trial-Sharpe variance {tr['sr_var']} over "
             f"{tr['dev_variants_scored']} DEV variants. DEV daily P/L, every DEV session (0 on days without a trade). Information, not a "
             "pass bar.\n")
    L.append(_head(("variant", "deflated Sharpe (DEV)")))
    for k, v in sorted(res["dsr"].items()):
        L.append(_row([k, _f(v, 4)]))
    for k, v in res["dsr_d_chosen"].items():
        L.append(_row([f"D {k} (chosen cell)", _f(v, 4)]))
    L.append("\n## Limits\n")
    L += ["- HIST option prices are MODELED: one flat IV per day, no smile, no intraday IV change, a price every minute, an expiry every "
          "session (before Nov 2022 SPY/QQQ/IWM did not list one every weekday). Next-expiry HIST tapes expire at the next NYSE session "
          "and use run 4's 0DTE multiplier where run 4 has no next-expiry key (labeled fallback): NOT VALIDATED; DEV REAL decides.",
          "- The D option twins, A-opt and the A3 twins run in tools/sprint_round8.py's option pass (one pass per entry), with the "
          "engine's own fill rules; they are not rows in the engine's run log (their trials are counted in the 192).",
          "- Signal-type option exits flip (sell the held contract, buy the other side at the next print after the same decision); "
          "grid cells hold one position at a time and skip signals while open.",
          "- The matched-random option benchmark is one random-side path (seed in the spec) per rule and contract, with the same 13 exits.",
          "- A3 is source grade C (a ~2-year blog test): a pass is exploratory. D5/D6 are designed tests of Nick's idea with no source: "
          "D5 must also beat its made-up levels.",
          "- 2% half-spread may be optimistic for thinner 2016-2019 0DTE markets; share costs assume $0.01 a share each way.\n"]
    return "\n".join(L) + "\n"


def _part_a_md(L, res):
    L.append("## Part A: steady rules in shares (BACKTEST, real stock bars, no option model)\n")
    L.append("Part A's bar per rule (primary variant; the long-only variant has its own line; the secondary variants are trials shown with "
             "the same checks as information): 1 at least 300 trades; 2 expectancy > 0 at 2x costs; 3 profitable in at least 6 of 2016-2023 "
             "and in DEV; 4 bootstrap 95% interval of the daily mean above 0 (seed 29, 2,000 draws); 5 positive without the best 5 days; "
             "6 beats random direction, p < 0.05 (seeds 31-230); 7 at least 55% of months green.\n")
    for rule, o in res["part_a"].items():
        L.append(f"### {rule}\n")
        for v, x in o.items():
            _share_variant_md(L, v, x)


def _aopt_md(L, res):
    L.append("## A3's option twins and A-opt: the share rules carried by options (DEV REAL decides; HIST MODELED information)\n")
    L.append("Bar (Addendum 10.1): at least 40 trades, PF >= 1.25, PF 2x > 1.0, expectancy > 0, on DEV REAL. Calls carry longs, puts carry "
             "shorts. A-opt exits on the share rule's own band/VWAP stop and reversal (no premium line); A3's twins hold to 15:25.\n")
    L.append(_head(("study", "family", "contract", "DEV REAL") + OP_COLS + ("verdict", "HIST MODELED n / exp / PF", "shares DEV n / exp $")))
    for k, o in res["a_opt"].items():
        d, h, s = o["bar"]["dev"], o["hist_info"], o["shares_dev"]
        L.append(_row([k, o["family"], o["contract"], "REAL"] + _op_cells(d) + [_yn(o["bar"]["pass"]),
                       f"{h.get('trades', 0)} / {_f(h.get('expectancy'))} / {_f(h.get('pf'), 3)}", f"{s.get('trades', 0)} / {_f(s.get('expectancy'))}"]))
    L.append("")


def _part_b_md(L, res):
    L.append("## Part B: a sharper big-day filter for the far-OTM calls (FIN-H family)\n")
    f = res["finh"]
    L.append(f"FIN-H (run 7's otm_c_1100 with f_rvol >= 1.06): HIST MODELED {f['HIST']['trades']} trades, exp ${_f(f['HIST'].get('expectancy'))}, "
             f"PF {_f(f['HIST'].get('pf'), 3)}; DEV REAL {f['DEV']['trades']} trades, exp ${_f(f['DEV'].get('expectancy'))}, PF "
             f"{_f(f['DEV'].get('pf'), 3)}, total without the best day ${_f(f['DEV'].get('without_best_day'))}.\n")
    L.append("### B2: confidence sizing (walk-forward logit, terciles of the training predictions: skip / 1 / 2 contracts)\n")
    L.append(_head(("sleeve", "window", "trades", "skipped", "doubled", "contracts", "per contract sized $", "per contract flat $",
                    "Sharpe sized", "Sharpe flat", "PF 2x sized", "verdict")))
    for k, o in res["b2"].items():
        if "error" in o:
            L.append(_row([k, "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", o["error"]]))
            continue
        for w, lab in (("hist", "MODELED"), ("dev", "REAL")):
            x = o[w]
            L.append(_row([k, f"{x['window']} {lab}", x["trades"], x["skipped"], x["doubled"], x["contracts"], _f(x["per_contract_sized"]),
                           _f(x["per_contract_flat"]), _f(x["sharpe_sized"]), _f(x["sharpe_flat"]), _f(x["pf_2x_sized"], 3), _yn(x["pass"])]))
    L.append("")
    b3r = res["b3"]
    L.append(f"### B3: newhigh_c, wait for proof: **{_yn(b3r['bar']['pass'])}**\n")
    _checks(L, b3r["bar"]["checks"])
    L.append("\nBeside FIN-H on the same days (days both traded):\n")
    L.append(_head(("period", "common days", "newhigh_c win %", "FIN-H win %", "newhigh_c avg loss", "FIN-H avg loss",
                    "newhigh_c w/o best day", "FIN-H w/o best day", "newhigh_c all: n / PF", "FIN-H all: n / PF")))
    for src, x in b3r["beside_finh"].items():
        a, b = x["newhigh_c_same_days"], x["fin_h_same_days"]
        L.append(_row([f"{src} ({LAB[src]})", x["common_days"], _pct(a.get("win_rate")), _pct(b.get("win_rate")), _f(a.get("avg_loss")),
                       _f(b.get("avg_loss")), _f(a.get("without_best_day")), _f(b.get("without_best_day")),
                       f"{x['newhigh_c']['trades']} / {_f(x['newhigh_c'].get('pf'), 3)}", f"{x['fin_h']['trades']} / {_f(x['fin_h'].get('pf'), 3)}"]))
    L.append("")
    L.append("### B4: FIN-H's entry on next-expiry and 0DTE contracts, with exits that can sell early\n")
    L.append(_head(("variant", "contract", "exit", "HIST 2016-2023 MODELED n / exp / PF / PF 2x", "years +", "DEV REAL n / exp / PF / PF 2x",
                    "B3 bars", "steadier than FIN-H")))
    for k, o in res["b4"].items():
        if k.startswith("_"):
            continue
        h, d = o["bar"]["hist"], o["bar"]["dev"]
        up = sum(1 for v in o["bar"]["hist_years"].values() if (v["net"] or 0) > 0)
        L.append(_row([k, o["contract"], o["exit_text"], f"{h['trades']} / {_f(h.get('expectancy'))} / {_f(h.get('pf'), 3)} / {_f(h.get('pf_2x'), 3)}",
                       f"{up}/8", f"{d['trades']} / {_f(d.get('expectancy'))} / {_f(d.get('pf'), 3)} / {_f(d.get('pf_2x'), 3)}",
                       _yn(o["bar"]["pass"]), "YES" if o["steadier"]["pass"] else "no"]))
    for k, o in res["b4"].items():
        if k.startswith("_"):
            continue
        L.append(f"\n{k}: B3 bars {_yn(o['bar']['pass'])}" + (f" (first miss: {first_fail(o['bar']['checks'])})" if not o["bar"]["pass"] else "")
                 + f". Steadier than FIN-H 0DTE (i) on {o['steadier']['common_days']} common DEV days:")
        _checks(L, o["steadier"]["checks"])
    c = res["b4"].get("_consistency") or {}
    if c and not c.get("same"):
        L.append(f"\nNote: this run's b4_d03_i DEV ({c['b4_d03_i_dev'].get('trades')} trades, total {c['b4_d03_i_dev'].get('total')}) differs "
                 f"from run 7's FIN-H DEV ({c['run7_finh_dev'].get('trades')} trades, total {c['run7_finh_dev'].get('total')}).")
    L.append("")


def _d_shares_md(L, res):
    L.append("## Part D shares: indicator rules on 5-minute bars (BACKTEST, real stock bars)\n")
    L.append("D1-D4 exit on the opposite signal, which reverses; D5/D6 exit on their level/bar stop (1-minute closes) or at the close. Part A's "
             "bar; D5 also above every made-up-level seed (1-5).\n")
    for rule, o in res["d_shares"].items():
        L.append(f"### {rule}\n")
        for v, x in o.items():
            x = dict(x, role="long-only" if v.endswith("_lo") else "long and short")
            _share_variant_md(L, v, x)
            if "fake" in x:
                L.append(f"Made-up levels (expectancy by seed): {x['fake']['expectancy']}; real levels beat all: {x['fake']['beats_all']}.\n")


def _d_options_md(L, res):
    L.append("## Part D options: the stop/target grid, chosen on 2016-2019 only\n")
    L.append("Each D rule on 0DTE d40-55t45 and next-expiry n1d40-55t45 (calls carry longs, puts carry shorts), 12 cells (stop -10/-20/-30/-50% "
             "x target +30/+50%/none) all out 15:25. Choice per rule and contract on HIST 2016-2019 MODELED only (highest PF among cells with 60+ "
             "trades; ties: more trades, smaller stop, smaller target), frozen; holdout 1 = 2020-01..2024-01 MODELED, holdout 2 = DEV REAL. "
             "BE win % = |avg loss| / (avg win + |avg loss|). The random column is the matched random-side twin's expectancy.\n")
    for k, o in res["d_options"].items():
        L.append(f"### {k}: {o['rule']} on {o['contract']}: **{'SURVIVES' if o['survives'] else 'fail'}**"
                 + (f" (chosen {o['chosen']})" if o["chosen"] else " (no choice)") + "\n")
        rnd = (o.get("random") or {}).get("cells", {})
        for wkey, lab in (("discovery", "2016-2019 MODELED (discovery)"), ("holdout1", "2020-01..2024-01 MODELED (holdout 1)"),
                          ("holdout2", "DEV REAL (holdout 2)")):
            L.append(f"{lab}:\n")
            L.append(_head(("cell",) + OP_COLS + ("random-side exp $",)))
            for cid, c in o["cells"].items():
                rk = {"discovery": "disc", "holdout1": "hist", "holdout2": "dev"}[wkey]
                rexp = (rnd.get(cid) or {}).get(rk, {}).get("expectancy")
                L.append(_row([f"**{cid}**" if cid == o["chosen"] else cid] + _op_cells(c[wkey]) + [_f(rexp)]))
            L.append("")
        if o["chosen"]:
            L.append(f"Holdout 1: **{_yn(o['holdout1']['pass'])}**")
            _checks(L, o["holdout1"]["checks"])
            L.append(f"\nHoldout 2: **{_yn(o['holdout2']['pass'])}**")
            _checks(L, o["holdout2"]["checks"])
        else:
            L.append(f"No choice: {o['why_not']}.")
        sg = o["signal"]
        L.append(f"\nSignal exit (opposite signal, flips; -20% stop): B3 bars **{_yn(sg['pass'])}**; HIST {sg['hist']['trades']} trades exp "
                 f"${_f(sg['hist'].get('expectancy'))} PF {_f(sg['hist'].get('pf'), 3)}, DEV {sg['dev']['trades']} trades exp "
                 f"${_f(sg['dev'].get('expectancy'))} PF {_f(sg['dev'].get('pf'), 3)}, win {_pct(sg['dev'].get('win_rate'))}% vs break-even "
                 f"{_pct(sg['dev'].get('be_win_rate'))}%; random side: DEV exp ${_f((rnd.get('signal') or {}).get('dev', {}).get('expectancy'))}.\n")


def _book_md(L, res):
    bv = res["book"]
    L.append("## The book\n")
    L.append("Sleeves: " + "; ".join(f"{k} ({v})" for k, v in bv["kinds"].items()) + ". Every session counts (P/L 0 on days without a trade). "
             "Literal reading: Amendment 10's book (FIN-H, passing Part B variants, passing Part A rules); D and A-opt survivors are reported "
             "above, not booked.\n")
    if bv.get("steadiness"):
        L.append("Part A sleeves add steadiness only with a daily correlation with FIN-H below 0.3: " + "; ".join(
            f"{k} corr {v['corr_finh']} -> {'adds steadiness' if v['adds_steadiness'] else 'does not add steadiness'}" for k, v in bv["steadiness"].items()) + "\n")
    L.append(_head(("window", "sessions", "trades", "total $", "avg per year $", "max DD $", "worst month", "months green", "weeks green",
                    "longest losing months", "Sharpe")))
    for w in ("hist", "dev", "mixed"):
        b = bv["windows"][w]["res"]["book"]
        wm = b.get("worst_month")
        L.append(_row([bv["windows"][w]["label"], b["sessions"], b["trades"], _f(b.get("total")), _f(b.get("avg_per_year")), _f(b.get("max_dd")),
                       f"{wm[0]} {_f(wm[1])}" if wm else "-", b["months_green"], b["weeks_green"], b["longest_losing_months"], _f(b.get("sharpe"))]))
    L.append("\nPer year (option sleeves MODELED through Jan 2024, REAL from Aug 2024; shares real):\n")
    L.append(_head(("year", "options", "trades", "total $", "max DD $", "months green", "weeks green", "longest losing months")))
    for name, y in bv["years"].items():
        b = y["book"]
        L.append(_row([name, y["prices"], b["trades"], _f(b.get("total")), _f(b.get("max_dd")), b["months_green"], b["weeks_green"],
                       b["longest_losing_months"]]))
    for w in ("hist", "dev"):
        r = bv["windows"][w]["res"]
        L.append(f"\nBy sleeve, {bv['windows'][w]['label']}:\n")
        L.append(_head(("sleeve", "trades", "total $", "share of total", "max DD $", "months green", "weeks green", "Sharpe")))
        for k, s in r["sleeves"].items():
            L.append(_row([k, s["trades"], _f(s.get("total")), _f(s.get("share_of_total"), 3), _f(s.get("max_dd")), s["months_green"],
                           s["weeks_green"], _f(s.get("sharpe"))]))
        keys = list(r["corr"])
        if len(keys) > 1:
            L.append("\nCorrelation of daily P/L:\n")
            L.append(_head([""] + keys))
            for k in keys:
                L.append(_row([k] + ["" if r["corr"][k][k2] is None else f"{r['corr'][k][k2]:+.2f}" for k2 in keys]))
    L.append("")


def summary_lines(res):
    out = []
    for rule, o in res["part_a"].items():
        out.append(f"A {rule:<12} primary {_yn(o[rule]['pass_bar']['pass']):<4} long-only {_yn(o[rule + '_lo']['pass_bar']['pass']):<4} "
                   f"(n {o[rule]['pass_bar']['stats']['trades']}, exp ${_f(o[rule]['pass_bar']['stats'].get('expectancy'))}, corr FIN-H "
                   f"{o[rule]['corr_finh']['all']}) [BACKTEST, shares]")
    for k, o in res["a_opt"].items():
        d = o["bar"]["dev"]
        out.append(f"{o['family']:<5} {k:<22} {_yn(o['bar']['pass']):<4} DEV n {d['trades']} exp ${_f(d.get('expectancy'))} PF {_f(d.get('pf'), 3)} "
                   "[BACKTEST, REAL]")
    for k, o in res["b2"].items():
        out.append(f"B2 {k:<12} {_yn(o.get('pass', False))}" + (f" ({o['error']})" if "error" in o else
                   f" DEV {_yn(o['dev']['pass'])} 2018-2024 {_yn(o['hist']['pass'])} [BACKTEST, REAL / MODELED]"))
    out.append(f"B3 newhigh_c     {_yn(res['b3']['bar']['pass'])} [BACKTEST, MODELED / REAL]")
    for k, o in res["b4"].items():
        if not k.startswith("_"):
            out.append(f"B4 {k:<14} {_yn(o['bar']['pass']):<4} steadier than FIN-H: {'YES' if o['steadier']['pass'] else 'no'} "
                       f"(DEV n {o['bar']['dev']['trades']}, PF {_f(o['bar']['dev'].get('pf'), 3)}) [BACKTEST, MODELED / REAL]")
    for rule, o in res["d_shares"].items():
        out.append(f"D shares {rule:<20} {_yn(o[rule]['pass_bar']['pass']):<4} long-only {_yn(o[rule + '_lo']['pass_bar']['pass'])} [BACKTEST, shares]")
    for k, o in res["d_options"].items():
        out.append(f"D opt {k:<28} chosen {str(o['chosen']):<10} {'SURVIVES' if o['survives'] else 'fail':<8} signal exit "
                   f"{_yn(o['signal']['pass'])} [BACKTEST, MODELED / REAL]")
    for w in ("hist", "dev", "mixed"):
        b = res["book"]["windows"][w]["res"]["book"]
        out.append(f"book {res['book']['windows'][w]['label']}: total ${_f(b.get('total'))}, per year ${_f(b.get('avg_per_year'))}, max DD "
                   f"${_f(b.get('max_dd'))}, months green {b['months_green']} [BACKTEST]")
    return out
