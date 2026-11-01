#!/usr/bin/env python3
"""tools/sprint_r10_swing.py - SPRINT_PLAN Amendment 16's swing families for round 10: the D-IV data step, V1 term_slope, V2
rv_iv_gap, V2-s rv_iv_rich (paper research), V3 earn_runup (shares + options twin) and V4 new_high (shares + options twin).
Research only: reads cached bars, EDGAR records and option bars; never trades; no network.

  python3 tools/sprint_r10_swing.py                   # after tools/sprint_pull9.py and tools/sprint_pull10.py
  python3 tools/sprint_r10_swing.py --parts V3,V4     # a subset (the others are reported as not run)

Reads (data/alpaca unless --data): daily9/ and universe/ustk.json (round 9), ../edgar/ (headers.jsonl, company_tickers.json;
round 9), r10/ (round 10's stock15 and option bars; sprint/ivdata.py layout); the logged chains folder (default data/chains)
for the calibration of Addendum 16.1's ESTIMATED-SPREAD (sprint/spread_est.py: Abdi-Ranaldo half-spreads from round 10's
1-minute option bars, calibrated on the measured SPY/QQQ chains; V1, V2, V2-s and the V3/V4 twins are judged at 100% of it,
with mid, 50%, the 10% MODELED default and F-opt's 2% as sensitivities).
Parts: DIV (D-IV's table and coverage report), VOL (V1, V2 and V2-s together: they share the sort, the holds and the
benchmark), V3, V4. Writes data/sprint/r10swing_<date>.md and .json, the D-IV table data/sprint/r10_div_<date>.csv.gz and the
trade files data/sprint/trades_r10swing_{V1,V2,V2s,V3,V3opt,V3pool,V4,V4opt}_<date>.csv.gz; prints the summary. Labels:
BACKTEST, REAL (option prices) or real daily bars (shares), BS-EST (IVs and deltas), SURVIVORSHIP-BIASED (U-STK), the
LOOK-AHEAD CAVEAT (realized 8-K 2.02 dates) and PAPER RESEARCH ONLY (V2-s, option selling). Trials: 7 (V1 1, V2 1, V2-s 1,
V3 2, V4 2) of round 10's 7,767; the deflated Sharpe (information) uses the run logs' count + 7,767. Refuses any trade row
whose window touches L1 or L2.
"""
import argparse
import csv
import glob
import gzip
import json
import statistics
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from sprint import book, data, edgar as E, factory, ivdata as IV, multiday as M, periods, round8, runner, shares  # noqa: E402
from sprint import r10swing as SW, report as R, spread as SP, spread_est as SE, universe as U  # noqa: E402

PARTS = ("DIV", "VOL", "V3", "V4")


def check_rows(rows, what):
    """None, or why the rows are refused (a row whose entry..exit window touches L1/L2)."""
    for r in rows:
        a = date.fromisoformat(str(r.get("entry_day") or r["day"])[:10])
        b = date.fromisoformat(str(r.get("exit_day") or r["day"])[:10])
        hit = periods.overlaps(min(a, b), max(a, b))
        if hit:
            return f"REFUSED: a {what} row {a}..{b} touches locked period {', '.join(hit)}"
    return None


def write_rows(path, rows, cols=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = cols or (list(dict.fromkeys(k for r in rows for k in r.keys() if not k.startswith("_") or k == "_src")) if rows else ["day"])
    with gzip.open(path, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return str(path)


def count_trials(out, patterns=None):
    if not patterns:
        return runner.count_prior_trials(out)
    n = 0
    for f in [runner.RUN_LOG] + sorted({f for p in patterns for f in glob.glob(p)}):
        try:
            with open(f) as fh:
                n += max(0, sum(1 for _ in csv.reader(fh)) - 1)
        except OSError:
            pass
    return n


def trials(n_prior):
    """The run-log entry for these parts, the way round 9 reports its trials."""
    return {"parts": dict(SW.TRIALS), "r10swing": SW.SWING_TRIALS, "round10": SW.ROUND10_TOTAL, "prior_in_run_logs": int(n_prior),
            "total_for_dsr": int(n_prior) + SW.ROUND10_TOTAL,
            "note": "these 7 are part of round 10's 7,767 (Amendment 16's tally); the deflated Sharpe uses the run logs' count + 7,767"}


def dsr_table(variants_dev, n_prior, dev_days):
    daily = {k: round8._daily_a(v, dev_days) for k, v in variants_dev.items()}
    srs = {k: R.sharpe(d) for k, (d, n) in daily.items()}
    vals = [x for x in srs.values() if x is not None]
    sr_var = statistics.pvariance(vals) if len(vals) > 1 else 0.0
    n = int(n_prior) + SW.ROUND10_TOTAL
    return {k: (R.deflated_sharpe(d, n, sr_var) if cnt else None) for k, (d, cnt) in daily.items()}, round(sr_var, 6), n


# ---------------------------------------------------------------- D-IV
def part_div(root, log, panels, uni, days):
    names_by_day = {d: uni.names(d) for d in days}
    tab = IV.IVTable.build(root, days, names_by_day, log)
    p = panels["all"]
    rv20 = {}
    rows = [p.idx(d) for d in days]
    for n in tab.names:
        j = p.col.get(n)
        if j is None:
            continue
        v = IV.realized_vol(p.adj_c[:, j], p.seg, IV.RV_N)
        rv20[n] = np.array([v[k] if k is not None else np.nan for k in rows])
    cov = IV.coverage(tab, names_by_day, rv20)
    log(f"  D-IV: {cov['name_days']} name-days, 30-day IV on {cov['with_iv30']} ({cov['share_iv30']}), 90-day on {cov['with_iv90']}")
    return tab, cov


# ---------------------------------------------------------------- V1 / V2 / V2-s
def part_vol(root, log, warnings, panels, uni, tab, spread, edgar_in):
    recs, tmap = edgar_in
    if not recs:
        warnings.append("V1/V2/V2-s: no EDGAR records (round 9's edgar stages): the 2.02 exits cannot be placed; not run.")
        return None, {}
    hl, dropped = SW.holds()
    rv = SW.rv252_prior(panels["all"])
    ctxd = {"bars": IV.Bars(root), "tab": tab, "reports": SW.report_times(recs, tmap), "cal": E.Calendar(), "panels": panels,
            "spread": spread, "universe": uni}
    outs = SW.vol_outcomes(hl, ctxd, lambda t, names: SW._rv_on(panels, rv, t, names), log)
    res, rows = SW.vol_family(outs)
    res["dropped_holds"] = [{"t": t.isoformat(), "x": x.isoformat(), "why": w} for t, x, w in dropped]
    res["spread"] = spread["est"].describe()
    for v, rr in rows.items():
        why = check_rows(rr, v)
        if why:
            raise periods.LockedPeriod(why)
    return res, rows


def twin_levels(rows):
    """F-opt's numbers (round8.ostats) of a twin's trades at every cost level (Addendum 16.1's sensitivities)."""
    out = {}
    for kn, _m, _k in SW.LEVELS:
        rr = [dict(r, pnl=r[f"pnl_{kn}"]) for r in rows]
        st = round8.ostats(rr)
        out[kn] = {k: st.get(k) for k in ("trades", "win_rate", "expectancy", "pf", "total", "max_dd")}
    return out


# ---------------------------------------------------------------- V3
def part_v3(root, log, warnings, panels, spread, edgar_in):
    recs, tmap = edgar_in
    p = panels["all"]
    if not recs or not any(v == "U-STK" for v in panels["univ"].values()):
        warnings.append("V3: no EDGAR records or no U-STK daily bars: V3 not run.")
        return None, [], [], []
    cal = E.Calendar()
    ev = SW.v3_events(recs, tmap, cal)
    tr, info = SW.v3_trades(p, ev, stk=SW.stk_mask(panels))
    why = check_rows(tr, "V3")
    if why:
        raise periods.LockedPeriod(why)
    reps = SW.report_positions(recs, tmap, cal)
    rp, _tots, rinfo = SW.v3_random(p, tr, reps, cal)
    pb = M.f_pass(tr, shares.all_sessions(), rp)
    items = SW.v3_twin_items(tr, p, reps, cal)
    bars = IV.Bars(root)
    rows, pool, skips = [], [], defaultdict(int)
    for it in items:
        r, w = SW.v3_twin_row(it, bars, spread)
        if r is None:
            skips[f"{it['kind']}: {w}"] += 1
        elif it["kind"] == "event":
            rows.append(r)
        else:
            pool.append(r)
    tp, _m, n_ev = SW.twin_random(rows, pool)
    fb = M.fopt_bar(rows)
    checks = fb["checks"] + [(f"beats the random-date twin, p < 0.05 on the mean P/L (p = {tp}; {n_ev} events with priced pool dates)",
                              tp is not None and tp < 0.05)]
    twin = {"bar": dict(fb, checks=checks, pass_=all(ok for _, ok in checks)), "pass": all(ok for _, ok in checks), "random_p": tp,
            "events": sum(1 for i in items if i["kind"] == "event"), "pool_dates": sum(1 for i in items if i["kind"] == "pool"),
            "skips": dict(skips), "levels": twin_levels(rows)}
    log(f"  V3: {len(ev)} 2.02 events, {len(tr)} share trades ({'PASS' if pb['pass'] else 'fail'}); twin {len(rows)} trades")
    res = {"events": len(ev), "info": info, "pass_bar": pb, "pass": pb["pass"], "years": shares.years_table(tr), "random_p": rp,
           "random_info": rinfo, "twin": twin}
    return res, tr, rows, pool


# ---------------------------------------------------------------- V4
def part_v4(root, log, warnings, panels, spread):
    p, univ = SW.v4_panel(panels)
    if not p.symbols:
        warnings.append("V4: no daily bars: V4 not run.")
        return None, [], []
    t0 = time.time()
    tr, info = SW.v4_book(p, univ)
    why = check_rows(tr, "V4")
    if why:
        raise periods.LockedPeriod(why)
    rp, _tots, rinfo = SW.v4_random(p, tr)
    pb = M.f_pass(tr, shares.all_sessions(), rp)
    bars = IV.Bars(root)
    sess = IV.dev_days()
    rows, skips, targets = [], defaultdict(int), 0
    for t in tr:
        if not (SW.DEV_A.isoformat() <= t["entry_day"] and t["exit_day"] <= SW.DEV_B.isoformat()):
            continue
        targets += 1
        kind, val = SW.v4_twin_walk(t, bars, SW.raw_open_fn(p, t["symbol"]), sess, spread)
        if kind == "row":
            rows.append(val)
        elif kind == "need":
            skips["option bars not pulled (tools/sprint_pull10.py)"] += 1
        else:
            skips[val] += 1
    fb = M.fopt_bar(rows)
    log(f"  V4: {len(tr)} share trades ({'PASS' if pb['pass'] else 'fail'}, {time.time() - t0:.0f}s); twin {len(rows)} of {targets}")
    res = {"info": info, "pass_bar": pb, "pass": pb["pass"], "windows": SW.v4_windows(tr), "top7": SW.top_share(tr), "random_p": rp,
           "random_info": rinfo, "years": shares.years_table(tr),
           "by_universe": {u: shares.stats([t for t in tr if t["universe"] == u]) for u in ("U-ETF", "U-STK")},
           "twin": {"bar": fb, "pass": fb["pass"], "targets": targets, "skips": dict(skips), "levels": twin_levels(rows),
                    "rolls": sum(int(r["rolls"]) for r in rows), "late_exits": sum(1 for r in rows if r.get("exit_late"))}}
    return res, tr, rows


# ---------------------------------------------------------------- the compounding view (R17)
def compounding(res, var, all_rows):
    """Amendment 16's compounding view for every rule that passes, through r10swing.compounding_view (sprint/compound.py)."""
    dev = [d.isoformat() for d in IV.dev_days()]
    hold = [d for d in book.sessions_between("2020-01-01", "2024-01-31")]
    out = {}
    V = res.get("VOL") or {}
    for v in ("V1", "V2", "V2-s"):
        if V.get(v, {}).get("pass"):
            how = "margin" if v == "V2-s" else "debit"
            out[f"{v} (DEV)"] = SW.compounding_view(v, var[f"{v} {SW.VARIANTS[v][0]}"], how, dev, f"{v} {SW.VARIANTS[v][0]}, DEV")
    for key, nm, how in (("V3", "earn_runup", "notional"), ("V4", "new_high", "stop")):
        o = res.get(key)
        if o and o["pass"]:
            sh = all_rows.get(f"{key} shares") or []
            out[f"{key} shares (DEV)"] = SW.compounding_view(f"{key} shares", sh, how, dev, f"{key} {nm} shares, DEV")
            if key == "V4":
                out["V4 shares (holdout 2020-2023)"] = SW.compounding_view("V4 shares", sh, how, hold,
                                                                           "V4 new_high shares, holdout 2020-01..2024-01")
        if o and o["twin"]["pass"]:
            out[f"{key} options (DEV)"] = SW.compounding_view(f"{key} options", var[f"{key} {nm} options"], "debit", dev,
                                                              f"{key} {nm} options twin, DEV")
    return out


# ---------------------------------------------------------------- the report
def _f(x, n=2):
    return R.fmt(x, n)


def _row(cells):
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _head(cols):
    return ["", _row(cols), _row(["---"] * len(cols))]


def _yn(ok):
    return "PASS" if ok else "fail"


def _checks(L, checks):
    for n, ok in checks:
        L.append(f"  - {'yes' if ok else 'NO'}: {n}")


def _first_fail(checks):
    return next((n for n, ok in checks if not ok), None)


def summary_lines(res):
    out = []
    D = res.get("DIV")
    if D:
        out.append(f"D-IV ({IV.LABEL}): 30-day IV on {_pct(D['share_iv30'])} of {D['name_days']} name-days, 90-day on {_pct(D['share_iv90'])}")
    V = res.get("VOL")
    for v in ("V1", "V2", "V2-s"):
        if not V:
            out.append(f"{v}: NOT RUN")
            continue
        o = V[v]
        s = o["levels"]["100"]
        out.append(f"{v} {o['name']} ({o['label']}): {_yn(o['pass'])}, {s.get('positions')} positions, mean return {_pct(s.get('mean_ret'))} "
                   f"at 100% of the ESTIMATED-SPREAD (mid {_pct(o['levels']['mid'].get('mean_ret'))}, 10% MODELED "
                   f"{_pct(o['levels']['m10'].get('mean_ret'))}), PF {s.get('pf_ret')}"
                   + ("" if o["pass"] else f" (first fail: {_first_fail(o['pass_bar']['checks'])})"))
    for key, nm in (("V3", "earn_runup"), ("V4", "new_high")):
        o = res.get(key)
        if not o:
            out.append(f"{key} {nm}: NOT RUN")
            continue
        s = o["pass_bar"]["stats"]
        out.append(f"{key} {nm} shares ({U.SB}): {_yn(o['pass'])}, {s.get('trades')} trades, exp ${s.get('expectancy')}, PF {s.get('pf')}"
                   + ("" if o["pass"] else f" (first fail: {_first_fail(o['pass_bar']['checks'])})"))
        tw = o["twin"]
        d = tw["bar"]["dev"]
        out.append(f"{key} {nm} options twin (REAL, DEV): {_yn(tw['pass'])}, {d.get('trades')} trades, exp ${d.get('expectancy')}, "
                   f"PF {d.get('pf')}, PF 2x {d.get('pf_2x')}")
    return out


def _pct(x):
    return "-" if x is None else f"{100 * float(x):.2f}%"


def render(res, meta):
    L = [f"# Sprint round 10: the swing families (D-IV, V1-V4), {meta['today']}", "",
         "SPRINT_PLAN Amendment 16, pre-registered 2026-11-01 before any round-10 code, pull or run. **Every number is a BACKTEST.** "
         "Shares: real Alpaca daily bars. Options: **REAL** Alpaca option prices on DEV 2024-08-01..2026-06-30; implied vols and "
         "deltas are **BS-EST** (solved from trade prices, r = q = 0). U-STK results are **SURVIVORSHIP-BIASED** (today's listed "
         "stocks only). L1 (2026-07-01..10-30) and L2 (2024-02-01..07-31) were never pulled or read; a trade touching them is dropped.",
         "", f"**{SW.LOOKAHEAD}** (V1/V2/V2-s exits and V3's dates).", "", f"Inputs: {meta.get('files_note', '')}", ""]
    if meta.get("warnings"):
        L += ["**Warnings:**"] + [f"- {w}" for w in meta["warnings"]] + [""]
    L += ["## Summary", ""] + [f"- {s}" for s in summary_lines(res)] + [""]
    t = res["trials"]
    L += [f"Trials: these parts = {t['r10swing']} ({', '.join(f'{k} {v}' for k, v in t['parts'].items())}), part of round 10's "
          f"{t['round10']}; the run logs hold {t['prior_in_run_logs']}; the deflated Sharpe uses N = {t['total_for_dsr']}.", ""]
    _div_md(L, res.get("DIV"))
    _vol_md(L, res.get("VOL"))
    _v3_md(L, res.get("V3"))
    _v4_md(L, res.get("V4"))
    _spread_md(L, res.get("spread"))
    L += ["## Compounding view (information)", ""]
    for k, v in (res.get("compounding") or {}).items():
        if v.get("md"):
            L += v["md"]
            L.append(f"  - risk unit: {v.get('risk')}; rows left out (outside the window or no positive risk): {v.get('skipped_rows')}.")
        else:
            L.append(f"- {k}: {v}")
    if not res.get("compounding"):
        L.append("- No rule passed, so there is nothing to compound (Amendment 16 runs the view only for passing rules).")
    L += ["", "## Deflated Sharpe (information, DEV daily P/L)", ""] + _head(("variant", f"DSR (N = {t['total_for_dsr']})"))
    for k, v in sorted((res.get("dsr") or {}).items()):
        L.append(_row([k, _f(v, 4)]))
    L += ["", "No rule, cut, threshold or seed changes after these results; a change is a new amendment, labeled in-sample. A pass "
          "is still research: it reaches paper trading only through a new versioned ledger after Nick's yes, and promotion needs "
          "CLAUDE.md step 5 (out-of-sample and 40 forward paper trades). V2-s is option selling: paper research only. Not "
          "financial advice."]
    return "\n".join(L) + "\n"


def _spread_md(L, S):
    L += ["## Option costs: the ESTIMATED-SPREAD (Addendum 16.1)", ""]
    if not S:
        L += ["NOT BUILT (no option part in this run).", ""]
        return
    c = S["calibration"]
    L.append(f"{S['describe']}.")
    L.append(f"- Pools: {S['pools']} (underlying x month x premium bucket), {S['pools_with_5_pairs']} with at least 5 minute pairs, "
             f"{S['pairs']} pairs in all; median pooled half-spread ${S['median_pool_half_spread']}.")
    L.append(f"- Calibration on the measured SPY/QQQ chains (DEV days only): ratio {c.get('ratio')} ({c.get('label')}); raw median "
             f"{c.get('raw_median')}; {c.get('chain_days')} chain days, {c.get('chain_rows')} usable chain rows, "
             f"{c.get('matched_contract_days')} matched contract-days.")
    L.append(f"- Fills priced (every level, judged model): {S['fills']}.")
    L.append("")


def _div_md(L, D):
    L += ["## D-IV: daily 30-day and 90-day ATM implied vol (DEV)", ""]
    if not D:
        L += ["NOT RUN.", ""]
        return
    L.append(f"{IV.LABEL}. Last 15:45-15:59 print per contract matched to the stock's close in the same minute; the two strikes "
             f"bracketing spot, call and put averaged, interpolated in strike; 5-session mean for sorting.")
    L.append(f"- Name-days in the universe: {D['name_days']}; with a 30-day IV {D['with_iv30']} ({_pct(D['share_iv30'])}), a 90-day "
             f"IV {D['with_iv90']} ({_pct(D['share_iv90'])}), both {D['with_both']} ({_pct(D['share_both'])}).")
    L.append(f"- Median of the names' median 30-day IV / median 20-day realized vol: {D['median_iv_over_rv20']}.")
    L.append(f"- Why a name-day has no IV (top reasons): {dict(list(D['why_missing'].items())[:8])}.")
    names = sorted(D["names"].items(), key=lambda kv: -kv[1]["days"])[:30]
    L += _head(("name", "days", "share with 30-day IV", "median IV30", "median IV90", "median RV20", "IV30 / RV20"))
    for n, v in names:
        L.append(_row([n, v["days"], v["share_iv30"], v["median_iv30"], v["median_iv90"], v["median_rv20"], v["iv30_over_rv20"]]))
    L.append("")


VOL_COLS = ("spread", "positions", "win %", "mean return", "avg win", "avg loss", "PF (returns)", "P/L $", "exp $", "PF $", "max DD $")


def _vol_md(L, V):
    L += ["## V1 term_slope, V2 rv_iv_gap, V2-s rv_iv_rich (DEV REAL)", ""]
    if not V:
        L += ["NOT RUN.", ""]
        return
    L.append(f"Monthly: the first session of each month at 15:45 on data through the prior close; held to the next rebalance's "
             f"15:45, out at the last 15:45 before a realized 8-K 2.02 (LOOK-AHEAD CAVEAT); expiries before the exit settle at "
             f"intrinsic value. Fills: the last 15:45-16:00 print +/- k x the half-spread ({V.get('spread')}), $0.65 per contract per "
             f"side. Holds dropped: {V.get('dropped_holds')}.")
    L.append("")
    for v in ("V1", "V2", "V2-s"):
        o = V[v]
        L.append(f"**{v} {o['name']}** ({o['label']}): **{_yn(o['pass'])}** (judged at 100% of the ESTIMATED-SPREAD)")
        _checks(L, o["pass_bar"]["checks"])
        L += _head(VOL_COLS)
        for kn, _m, _k in SW.LEVELS:
            s, lab = o["levels"][kn], SW.LEVEL_NAMES[kn]
            L.append(_row([lab, s.get("positions"), _f((s.get("win_rate") or 0) * 100, 1) if s.get("positions") else "-",
                           _pct(s.get("mean_ret")), _pct(s.get("avg_win_ret")), _pct(s.get("avg_loss_ret")), s.get("pf_ret"),
                           _f(s.get("pnl_total")), _f(s.get("expectancy")), s.get("pf_dollars"), _f(s.get("max_dd"))]))
        L.append(f"- Two-month blocks (mean return at 100%): {o['pass_bar']['blocks']}")
        L.append(f"- Random names (200 draws, seeds 31-230): mean {_pct(o['random']['mean'])}, 90th percentile {_pct(o['random']['p90'])}; "
                 f"bootstrap 95% CI of the mean return (by rebalance session) {o.get('boot_ci_100')}; selected but not priced: {o['skips'] or 'none'}.")
        L.append("")
    L.append(f"V1/V2 overlap: {V['overlap_V1_V2']}.")
    L.append("")


def _fpass(L, name, o):
    pb = o["pass_bar"]
    L.append(f"**{name}**: **{_yn(o['pass'])}**" + (f" (first failed check: {_first_fail(pb['checks'])})" if not o["pass"] else ""))
    _checks(L, pb["checks"])
    L += _head(("window", "trades", "win %", "exp $", "exp 2x $", "PF", "PF 2x", "total $", "max DD $"))
    for yn, s in (o.get("years") or {}).items():
        if s.get("trades"):
            L.append(_row([yn, s["trades"], _f((s.get("win_rate") or 0) * 100, 1), _f(s.get("expectancy")), _f(s.get("expectancy_2x")),
                           _f(s.get("pf")), _f(s.get("pf_2x")), _f(s.get("total")), _f(s.get("max_dd"))]))
    s = pb["stats"]
    L.append(_row(["all", s.get("trades"), _f((s.get("win_rate") or 0) * 100, 1) if s.get("trades") else "-", _f(s.get("expectancy")),
                   _f(s.get("expectancy_2x")), _f(s.get("pf")), _f(s.get("pf_2x")), _f(s.get("total")), _f(s.get("max_dd"))]))


def _twin(L, name, tw, extra=""):
    b = tw["bar"]
    L.append(f"**{name}**: **{_yn(tw['pass'])}**{extra}")
    _checks(L, b["checks"])
    d = b["dev"]
    L += _head(("trades", "win %", "exp $", "PF", "PF 2x", "total $", "max DD $"))
    L.append(_row([d.get("trades"), _f((d.get("win_rate") or 0) * 100, 1) if d.get("trades") else "-", _f(d.get("expectancy")),
                   _f(d.get("pf")), _f(d.get("pf_2x")), _f(d.get("total")), _f(d.get("max_dd"))]))
    L.append(f"- Not priced: {tw.get('skips') or 'none'}.")
    L += _head(("cost (sensitivities; judged at 100% of the ESTIMATED-SPREAD)", "trades", "win %", "exp $", "PF", "total $", "max DD $"))
    for kn, _m, _k in SW.LEVELS:
        x = (tw.get("levels") or {}).get(kn) or {}
        L.append(_row([SW.LEVEL_NAMES[kn], x.get("trades"), _f((x.get("win_rate") or 0) * 100, 1) if x.get("trades") else "-",
                       _f(x.get("expectancy")), _f(x.get("pf")), _f(x.get("total")), _f(x.get("max_dd"))]))


def _v3_md(L, V):
    L += ["## V3 earn_runup (U-STK shares, then the options twin)", ""]
    if not V:
        L += ["NOT RUN.", ""]
        return
    L.append(f"Top 10% by 12-1 month return; bought at the close 5 sessions before the realized 2.02, sold at the last close before "
             f"it; $10,000 a trade, 0.05% of the price per side. {U.SB}. Events: {V['events']}; dropped: {V['info']['dropped']}. Random "
             f"dates at least 10 sessions from any report: p = {V['random_p']} ({V['random_info']}).")
    _fpass(L, "V3 shares (Part F's 7-item bar)", V)
    L.append("")
    tw = V["twin"]
    _twin(L, "V3 options twin (delta 0.50-0.60 call, first expiry after the report; F-opt's bar at the ESTIMATED-SPREAD + the "
             "random-date twin; REAL)", tw, f"; {tw['events']} events, {tw['pool_dates']} random pool dates")
    L.append("")


def _v4_md(L, V):
    L += ["## V4 new_high (U-STK + U-ETF shares, then the options twin)", ""]
    if not V:
        L += ["NOT RUN.", ""]
        return
    L.append(f"Buy at the next open after a close at the highest close of the prior 252 sessions; out at the next open after a close "
             f"below the highest close since entry - 3 x ATR(20) (raised daily, never lowered); $10,000 a position, at most 10 open "
             f"(ties: higher 20-day dollar volume). U-STK legs {U.SB}. {V['info']}. Random entry p = {V['random_p']}.")
    _fpass(L, "V4 shares (Part F's 7-item bar)", V)
    L += _head(("window", "trades", "exp $", "PF", "PF 2x", "total $"))
    for k, s in V["windows"].items():
        L.append(_row([k, s.get("trades"), _f(s.get("expectancy")), _f(s.get("pf")), _f(s.get("pf_2x")), _f(s.get("total"))]))
    L.append(f"- Share of profit from the top 7% of trades: {V['top7']}. By universe: {V['by_universe']}.")
    L.append("")
    tw = V["twin"]
    _twin(L, "V4 options twin (delta 0.60-0.70 call 60-120 days, rolled at 30 days left, out on the stock's stop; F-opt's bar at "
             "the ESTIMATED-SPREAD; REAL)", tw,
          f"; {tw['targets']} DEV share trades to carry, {tw['rolls']} rolls, {tw['late_exits']} late exits")
    L.append("")


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="SPRINT_PLAN Amendment 16: round 10's swing families (research only)")
    ap.add_argument("--data", default=None, help="cache root (default data/alpaca)")
    ap.add_argument("--out", default=str(HERE / "data" / "sprint"))
    ap.add_argument("--today", default=None)
    ap.add_argument("--parts", default=",".join(PARTS))
    ap.add_argument("--chains-dir", default=str(HERE / "data" / "chains"),
                    help="logged chains: the ESTIMATED-SPREAD's calibration (Addendum 16.1)")
    ap.add_argument("--runs-csv", nargs="+", default=None)
    x = ap.parse_args(argv)
    t_all = time.time()
    root = Path(x.data) if x.data else data.ROOT
    out = Path(x.out)
    out.mkdir(parents=True, exist_ok=True)
    today = x.today or date.today().isoformat()
    parts = [p.strip().upper() for p in x.parts.split(",") if p.strip()]
    log = lambda s: print(s, flush=True)
    warnings, files, res, var, all_rows = [], {}, {}, {}, {}
    log(f"sprint_r10_swing: parts {', '.join(parts)}; cache {root}; every number is a BACKTEST; L1/L2 never read")
    panels = SW.load_panels(root, log)
    if not U.read_ustk(root):
        warnings.append("No U-STK list (data/alpaca/universe/ustk.json): U-ETF names only.")
    uni = SW.Universe(panels)
    days = IV.dev_days()
    spread = None
    if {"VOL", "V3", "V4"} & set(parts):
        est = SE.build(root, x.chains_dir, days, log)
        spread = {"est": est, "m10": SP.SpreadModel(pct=0.10), "m2": SP.SpreadModel(pct=0.02)}
        if est.cal.get("ratio") == 1.0 and "fewer than" in str(est.cal.get("label")):
            warnings.append(f"ESTIMATED-SPREAD calibration: {est.cal['label']}; ratio 1 used (labeled).")
    edgar_in = SW.load_edgar(root)
    tab = None
    if "DIV" in parts or "VOL" in parts:
        tab, cov = part_div(root, log, panels, uni, days)
        res["DIV"] = cov
        files["DIV"] = write_rows(out / f"r10_div_{today}.csv.gz", tab.rows())
        if not cov["with_iv30"]:
            warnings.append("D-IV: no 30-day IV anywhere (round 10's option pull, tools/sprint_pull10.py, not run yet?).")
    if "VOL" in parts:
        V, vrows = part_vol(root, log, warnings, panels, uni, tab, spread, edgar_in)
        res["VOL"] = V
        for v, rr in vrows.items():
            files[v] = write_rows(out / f"trades_r10swing_{v.replace('-', '')}_{today}.csv.gz", rr)
            var[f"{v} {SW.VARIANTS[v][0]}"] = rr
    if "V3" in parts:
        V3, tr, rows, pool = part_v3(root, log, warnings, panels, spread, edgar_in)
        res["V3"] = V3
        if V3:
            files["V3"] = write_rows(out / f"trades_r10swing_V3_{today}.csv.gz", tr)
            files["V3opt"] = write_rows(out / f"trades_r10swing_V3opt_{today}.csv.gz", rows)
            files["V3pool"] = write_rows(out / f"trades_r10swing_V3pool_{today}.csv.gz", pool)
            var["V3 earn_runup shares"] = round8.in_win(tr, SW.DEV_A.isoformat(), SW.DEV_B.isoformat())
            all_rows["V3 shares"] = tr
            var["V3 earn_runup options"] = rows
    if "V4" in parts:
        V4, tr, rows = part_v4(root, log, warnings, panels, spread)
        res["V4"] = V4
        if V4:
            files["V4"] = write_rows(out / f"trades_r10swing_V4_{today}.csv.gz", tr)
            files["V4opt"] = write_rows(out / f"trades_r10swing_V4opt_{today}.csv.gz", rows)
            var["V4 new_high shares"] = round8.in_win(tr, SW.DEV_A.isoformat(), SW.DEV_B.isoformat())
            all_rows["V4 shares"] = tr
            var["V4 new_high options"] = rows
    if spread is not None:
        res["spread"] = dict(spread["est"].summary(), describe=spread["est"].describe())
    res["compounding"] = compounding(res, var, all_rows)
    n_prior = count_trials(out, x.runs_csv)
    res["trials"] = trials(n_prior)
    dev_days = [d.isoformat() for d in days]
    res["dsr"], res["sr_var"], _n = dsr_table(var, n_prior, dev_days)
    meta = {"today": today, "parts": parts, "warnings": warnings, "files": files,
            "files_note": "; ".join(f"{k} `{v}`" for k, v in files.items())}
    md = render(res, meta)
    mp, jp = out / f"r10swing_{today}.md", out / f"r10swing_{today}.json"
    mp.write_text(md)
    jp.write_text(json.dumps(factory.clean({"meta": meta, "result": res}), indent=1, default=str))
    print("ROUND 10 SWING SUMMARY (BACKTEST; options REAL on DEV; IVs BS-EST; U-STK SURVIVORSHIP-BIASED)")
    print("\n".join(summary_lines(res)))
    for w in warnings:
        print(f"WARNING: {w}")
    print(f"done in {(time.time() - t_all) / 60:.1f} min\nreport: {mp}\njson:   {jp}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except periods.LockedPeriod as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
