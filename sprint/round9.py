"""sprint/round9.py - round 9's readouts (SPRINT_PLAN Amendment 12, Parts F G H I, and Amendment 13, Part S; pre-registered
2026-11-01 before any round-9 code, pull or run). Research only: it reads trade lists and never trades. Every number is a
BACKTEST. Labels: share results are real Alpaca bars (U-STK ones SURVIVORSHIP-BIASED); option results are REAL (Alpaca
option prices, DEV) except FIN-H's 2016-2024 book line, which is MODELED (run 7, BS with run 4's calibration).

Part H, the honest tweak search (Amendment 12 "Part H"): run 7's per-strategy factory procedure (Amendment 9 (b)-(d),
sprint/factory.run_strategy, unchanged) on round 8's share trades: 12 tercile candidate rules on 6 features found on
2016-2019, holdout 1 = 2020-01..2024-01 and holdout 2 = DEV with the factory's bars, the walk-forward learner (24 training
months, logit / ridge / buckets) with the factory's survival rule, and the verdict. Trade-level features are the sprint
entry features at each share entry's decision bar (sprint/features.entry_features from cached bars; longs as "C", shorts
as "P", so side-signed features point in the trade's direction). Literal-reading note: the amendment's list names 12
strategies (noise_sh, noise_sh_vol, noise_sh_lo, last30, gapfade_vix, gapfade_vix_lo and D1-D6) while its count says 11
(11 x 15 = 165 trials). All 12 named strategies run (dropping one would be a choice made here); the trial count stays the
written 165 (round 9 = 203), and the deflated Sharpe is also shown at +15 trials as information.
Account view (information; Nick's real account is about $3,000), for every F / G / I / S result and the book, beside the
pre-registered numbers, never instead of them: P/L per $1,000 of capital (each trade's P/L x 1,000 / the capital it used:
the notional for shares, the debit for options, i.e. as if every trade used $1,000); max drawdown and worst month as a %
of $3,000 at the pre-registered size (daily equity curve, every session of the result's windows); share rules also scaled
to $3,000 notional (P/L x 3,000 / notional: costs scale with the shares, share rounding ignored); option rules: each
trade's debit as a % of $3,000.
The book (Amendment 12 "The book"): FIN-H (1 contract; run 7's otm_c_1100 with f_rvol >= 1.06) plus every round-9 survivor,
as Amendment 10's book (round8.book_views: 2018-01..2024-01 with option sleeves MODELED and shares real, DEV REAL, and a
labeled mixed line; total and per year, max drawdown, months and weeks green, the longest losing-month run, the worst
month, each sleeve's share of the total, the correlation matrix). Multi-day share trades count on their exit day. A
sleeve "adds steadiness" only if its daily P/L correlation with FIN-H is below 0.3, over the sessions both could trade
(the intersection of their windows). Survivors: a Part F rule/universe that passes (U-STK only with U-ETF passing), an
F-opt twin that passes, a G1 variant, G2, each Part H strategy whose verdict is not "none" (its chosen variant's trades),
Part I, and each Part S signal/contract whose frozen cell passes the test (1 contract; its trades over all of DEV, the
choice half labeled in-sample). S-size is a sizing overlay of the same trades and is reported, not booked twice.
Trials: F 6 + G 3 + H 165 + I 1 + S 28 = 203. Deflated Sharpe (information) on DEV daily P/L with N = the run logs' rows +
203 and the trial-Sharpe variance over every DEV variant scored here.
"""
import math
import statistics
from collections import defaultdict
from datetime import date

import numpy as np

from . import book, factory, features, periods, round8, shares
from . import report as R

HIST_A, HIST_B = periods.HIST[0].isoformat(), periods.HIST[1].isoformat()
DEV_A, DEV_B = periods.DEV[0].isoformat(), periods.DEV[1].isoformat()
TRIALS = {"F (2 rules x 2 universes + 2 option twins)": 6, "G (G1 2 sides + G2)": 3,
          "H (11 strategies x (12 rules + 3 learner models))": 165, "I (weekly expiry)": 1,
          "S (2 signals x 2 contracts x 6 cells + 2 underlying checks + 2 sized variants)": 28}
ROUND9 = 203
assert sum(TRIALS.values()) == ROUND9
H_STRATEGIES = ("noise_sh", "noise_sh_vol", "noise_sh_lo", "last30", "gapfade_vix", "gapfade_vix_lo",
                "ind_rsi", "ind_bb", "ind_ema", "ind_macd", "conf_level_rsi", "conf_trend_pullback")
H_WRITTEN_COUNT = 11
ACCOUNT = 3000.0
STEADY_CORR = 0.3
SB = "SURVIVORSHIP-BIASED"


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), n)


def day_of(r):
    return str(r["day"])[:10]


# ---------------------------------------------------------------- Part H
def stamp_share_features(trades, series, aux, progress=None):
    """Stamp sprint entry features on round 8 share trades at their decision bar, from cached bars (in place).
    series: {(src, symbol): data.Series}. Returns the number of trades stamped."""
    from . import data
    by = defaultdict(list)
    for t in trades:
        by[(t["_src"], t["symbol"], day_of(t))].append(t)
    n = 0
    for k, (key, rows) in enumerate(sorted(by.items())):
        src, sym, d = key
        ser = series.get((src, sym))
        day = date.fromisoformat(d)
        if ser is None or day not in ser.rth:
            continue
        ctx = data.DayContext(ser, day, {}, None, aux=aux)
        for t in rows:
            j = int(float(t["decision_idx"]))
            side = "C" if str(t["side"]) == "L" else "P"
            t.update(features.entry_features(ctx, j, side))
            n += 1
        if progress and k % 2000 == 0:
            progress(f"  Part H features: {k}/{len(by)} symbol-days")
    return n


def part_h(rows_by_strategy):
    """factory.run_strategy on each strategy's share trades (rows carry _src, day, pnl, pnl_2x, entry_time, f_*)."""
    out, sleeves, variants_dev = {}, {}, {}
    for name in H_STRATEGIES:
        rows = [dict(r) for r in rows_by_strategy.get(name, [])]
        res, sleeve, pool = factory.run_strategy(name, rows)
        res.pop("seen_before", None)
        res["model_check"] = "shares: real stock bars in every year (no option model)"
        out[name] = res
        if res["verdict"] != "none":
            sleeves[name] = sleeve
        variants_dev[f"H {name} unfiltered"] = factory.in_window(rows, DEV_A, DEV_B, "DEV")
        for c in res["rule"]["candidates"]:
            if c["cut"] is not None:
                variants_dev[f"H {name} {c['feature']} {c['side']}"] = factory.apply_rule(factory.in_window(rows, DEV_A, DEV_B, "DEV"), c)
        for m in factory.MODELS:
            if m in pool:
                variants_dev[f"H {name} learner {m}"] = factory.in_window(pool[m], DEV_A, DEV_B, "DEV")
    return {"strategies": out, "order": list(H_STRATEGIES), "written_count": H_WRITTEN_COUNT,
            "survivors": {k: out[k]["verdict"] for k in sleeves}}, sleeves, variants_dev


# ---------------------------------------------------------------- the account view
def _daily_equity(rows, days, key="pnl", scale=None):
    v = np.zeros(len(days))
    idx = {d: i for i, d in enumerate(days)}
    for k, r in enumerate(rows):
        i = idx.get(day_of(r))
        if i is not None:
            v[i] += float(r[key]) * (scale[k] if scale is not None else 1.0)
    return v


def _dd_month(daily, days):
    eq = np.cumsum(daily)
    dd = float(min(0.0, (eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min())) if len(eq) else 0.0
    bm = defaultdict(float)
    for d, x in zip(days, daily):
        bm[d[:7]] += x
    worst = min(bm.items(), key=lambda kv: kv[1]) if bm else None
    return dd, worst


def account_view(rows, kind, days, account=ACCOUNT, size=None):
    """kind "shares" (capital = row notional) or "option" (capital = row debit). size: optional per-row multiplier (the
    pre-registered size, e.g. S-size contracts). days: every session of the result's windows (ISO strings)."""
    rows = list(rows)
    mult = np.ones(len(rows)) if size is None else np.asarray(size, float)

    def capital(r):
        v = r.get("notional") if kind == "shares" else r.get("debit") if kind == "option" else (r.get("debit") or r.get("notional"))
        try:
            v = float(v)
        except (TypeError, ValueError):
            return np.nan
        return v if v == v else np.nan

    p = np.array([float(r["pnl"]) for r in rows]) * mult if rows else np.zeros(0)
    cap = np.array([capital(r) for r in rows]) * mult if rows else np.zeros(0)
    ok = np.isfinite(cap) & (cap > 0)
    per1000 = p[ok] * 1000.0 / cap[ok]
    daily = _daily_equity(rows, days, scale=mult)
    dd, worst = _dd_month(daily, days)
    out = {"kind": kind, "trades": len(rows), "per_1000": {"total": _r(per1000.sum()) if len(per1000) else None,
                                                             "per_trade": _r(per1000.mean(), 3) if len(per1000) else None,
                                                             "trades_with_capital": int(ok.sum())},
           "pre_registered_size": {"max_dd": _r(dd), "max_dd_pct_3000": _r(dd / account * 100, 1),
                                   "worst_month": worst[0] if worst else None, "worst_month_net": _r(worst[1]) if worst else None,
                                   "worst_month_pct_3000": _r(worst[1] / account * 100, 1) if worst else None}}
    if kind == "shares":
        sc = np.where(ok, account / np.where(ok, cap, 1.0), 0.0)
        d3 = _daily_equity(rows, days, scale=sc * mult)
        dd3, w3 = _dd_month(d3, days)
        out["at_3000_notional"] = {"total": _r(float((p * sc).sum())), "max_dd": _r(dd3), "max_dd_pct_3000": _r(dd3 / account * 100, 1),
                                   "worst_month": w3[0] if w3 else None, "worst_month_net": _r(w3[1]) if w3 else None,
                                   "worst_month_pct_3000": _r(w3[1] / account * 100, 1) if w3 else None}
    elif kind == "option":
        pct = cap[ok] / account * 100
        out["debit_pct_3000"] = ({"median": _r(float(np.median(pct)), 1), "p90": _r(float(np.percentile(pct, 90)), 1),
                                  "max": _r(float(pct.max()), 1), "over_100": int((pct > 100).sum())} if len(pct) else None)
    return out


# ---------------------------------------------------------------- the book
def coverage_days(kind):
    """Sessions a sleeve could trade: "hist+dev" (2016-01-04..2024-01-31 + DEV) or "dev" (DEV only)."""
    dev = book.sessions_between(DEV_A, DEV_B)
    return dev if kind == "dev" else book.sessions_between(HIST_A, HIST_B) + dev


def steadiness(by_sleeve, cover):
    """Each non-FIN-H sleeve's daily correlation with FIN-H over the sessions both could trade; adds steadiness when < 0.3."""
    out = {}
    fin = by_sleeve.get("FIN-H", [])
    fdays = set(coverage_days(cover.get("FIN-H", "hist+dev")))
    for k, rows in by_sleeve.items():
        if k == "FIN-H":
            continue
        days = [d for d in coverage_days(cover.get(k, "hist+dev")) if d in fdays]
        a, b = book._daily(rows, days), book._daily(fin, days)
        c = shares.corr(a, b)
        out[k] = {"corr_finh": c, "sessions": len(days), "adds_steadiness": c is not None and c < STEADY_CORR}
    return out


def run_book(by_sleeve, kinds, cover):
    res = round8.book_views(by_sleeve, kinds)
    res["steadiness"] = steadiness(by_sleeve, cover)
    res["cover"] = cover
    return res


# ---------------------------------------------------------------- trials and the deflated Sharpe
def dsr_table(variants_dev, n_prior, dev_days, extra=0):
    """{name: deflated Sharpe} on DEV daily P/L, N = the run logs' rows + 203 (+ extra), the trial-Sharpe variance over
    every DEV variant given. Returns (table, sr_var, N)."""
    daily = {k: round8._daily_a(v, dev_days) for k, v in variants_dev.items()}
    srs = {k: R.sharpe(d) for k, (d, n) in daily.items()}
    vals = [x for x in srs.values() if x is not None]
    sr_var = statistics.pvariance(vals) if len(vals) > 1 else 0.0
    n = int(n_prior) + ROUND9 + int(extra)
    tab = {k: (R.deflated_sharpe(d, n, sr_var) if cnt else None) for k, (d, cnt) in daily.items()}
    return tab, round(sr_var, 6), n


def trials(n_prior):
    return {"parts": TRIALS, "round9": ROUND9, "prior_in_run_logs": int(n_prior), "total_for_dsr": int(n_prior) + ROUND9,
            "h_note": f"Part H's list names {len(H_STRATEGIES)} strategies; its written count is {H_WRITTEN_COUNT} (165 trials). "
                      f"All {len(H_STRATEGIES)} run; the deflated Sharpe uses the written count, and is also shown at +15 trials."}


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
    for n, ok in checks:
        if not ok:
            return n
    return None


SH_COLS = ("window", "trades", "win %", "avg win $", "avg loss $", "exp $", "exp bps", "exp 2x $", "PF", "PF 2x", "total $", "max DD $")


def _sh_cells(name, s):
    return [name, s.get("trades", 0), _f((s.get("win_rate") or 0) * 100, 1) if s.get("trades") else "-", _f(s.get("avg_win")),
            _f(s.get("avg_loss")), _f(s.get("expectancy")), _f(s.get("exp_bps"), 2), _f(s.get("expectancy_2x")), _f(s.get("pf")),
            _f(s.get("pf_2x")), _f(s.get("total")), _f(s.get("max_dd"))]


OP_COLS = ("trades", "win %", "BE win %", "avg win $", "avg loss $", "exp $", "PF", "PF 2x", "total $", "w/o best 5 $", "max DD $")


def _op_cells(s):
    if not s or not s.get("trades"):
        return [s.get("trades", 0) if s else 0] + ["-"] * (len(OP_COLS) - 1)
    return [s["trades"], _f((s.get("win_rate") or 0) * 100, 1), _f((s.get("be_win_rate") or 0) * 100, 1) if s.get("be_win_rate") is not None else "-",
            _f(s.get("avg_win")), _f(s.get("avg_loss")), _f(s.get("expectancy")), _f(s.get("pf")), _f(s.get("pf_2x")), _f(s.get("total")),
            _f(s.get("without_best5")), _f(s.get("max_dd"))]


def _account_md(L, av, title="Account view (information, $3,000 account)"):
    if not av:
        return
    p = av["pre_registered_size"]
    line = (f"- {title}: P/L per $1,000 of capital {_f(av['per_1000']['total'])} in total ({_f(av['per_1000']['per_trade'], 3)} a "
            f"trade); at the pre-registered size max drawdown {_f(p['max_dd'])} ({_f(p['max_dd_pct_3000'], 1)}% of $3,000), worst month "
            f"{p['worst_month']} {_f(p['worst_month_net'])} ({_f(p['worst_month_pct_3000'], 1)}% of $3,000)")
    if "at_3000_notional" in av:
        a = av["at_3000_notional"]
        line += (f"; at $3,000 notional a trade: total {_f(a['total'])}, max drawdown {_f(a['max_dd'])} ({_f(a['max_dd_pct_3000'], 1)}%), "
                 f"worst month {_f(a['worst_month_net'])} ({_f(a['worst_month_pct_3000'], 1)}%)")
    if av.get("debit_pct_3000"):
        d = av["debit_pct_3000"]
        line += (f"; each trade's debit as a % of $3,000: median {_f(d['median'], 1)}%, 90th pct {_f(d['p90'], 1)}%, max {_f(d['max'], 1)}%"
                 f" ({d['over_100']} trades above 100%)")
    L.append(line + ".")


def _fpass_md(L, name, o, label):
    pb = o.get("pass_bar")
    if pb is None:
        L.append(f"- **{name}**: NOT RUN ({o.get('why', 'no input')}).")
        return
    L.append(f"**{name}** ({label}): **{_yn(o['pass'])}**" + (f" (first failed check: {_first_fail(pb['checks'])})" if not o["pass"] else "")
             + (f"; {o['note']}" if o.get("note") else ""))
    _checks(L, pb["checks"])
    L += _head(SH_COLS)
    for yn, s in o.get("years", {}).items():
        if s.get("trades"):
            L.append(_row(_sh_cells(yn, s)))
    L.append(_row(_sh_cells("all (2016-2026 windows)", pb["stats"])))
    st = pb["steadiness"]
    L.append(f"- Months green {st['months_green']}/{st['months']}, weeks green {st['weeks_green']}/{st['weeks']}, longest losing-month "
             f"run {st['longest_losing_months']}, worst month {st['worst_month']}; random-entry p {o.get('random_p')}; dropped trades: "
             f"{o.get('dropped') or 'none'}.")
    _account_md(L, o.get("account"))
    L.append("")


def render(res, meta):
    L = [f"# Sprint round 9: steadier money (multi-day, all-stock catalysts, the honest tweak search, weekly expiries, the 1-minute "
         f"scalper), {meta['today']}", "",
         "SPRINT_PLAN Amendments 12 and 13, pre-registered 2026-11-01 before any round-9 code, pull or run. **Every number is a "
         "BACKTEST.** Shares: real Alpaca bars. Options: **REAL** Alpaca option prices on DEV 2024-08-01..2026-06-30 (FIN-H's "
         "2018-2024 book line is **MODELED**, run 7). U-STK results are **SURVIVORSHIP-BIASED** (today's listed stocks only). "
         "L1 (2026-07-01..10-30) and L2 (2024-02-01..07-31) were never pulled or read; a multi-day trade touching them is dropped.",
         "", f"Inputs: {meta.get('files_note', '')}", ""]
    if meta.get("warnings"):
        L += ["**Warnings:**"] + [f"- {w}" for w in meta["warnings"]] + [""]
    L += ["## Summary", ""] + [f"- {s}" for s in summary_lines(res)] + [""]
    t = res["trials"]
    L.append(f"Trials: round 9 = {t['round9']} ({', '.join(f'{k}: {v}' for k, v in t['parts'].items())}); the run logs hold "
             f"{t['prior_in_run_logs']}; the deflated Sharpe uses N = {t['total_for_dsr']} (sr variance {res.get('sr_var')} over "
             f"{res.get('dev_variants_scored')} DEV variants). {t['h_note']}")
    L.append("")
    _part_f_md(L, res.get("F"))
    _part_g_md(L, res.get("G"))
    _part_h_md(L, res.get("H"), res.get("dsr", {}))
    _part_i_md(L, res.get("I"))
    _part_s_md(L, res.get("S"))
    _book_md(L, res.get("book"))
    L += ["## Deflated Sharpe (information, DEV daily P/L)", ""] + _head(("variant", f"DSR (N = {t['total_for_dsr']})", "DSR (N + 15)"))
    for k, v in sorted((res.get("dsr") or {}).items()):
        L.append(_row([k, _f(v, 4), _f((res.get("dsr_plus15") or {}).get(k), 4)]))
    L += ["", "No rule, cut, threshold or seed changes after these results; a change is a new amendment, labeled in-sample. A pass "
          "is still research: it reaches paper trading only through a new versioned ledger after Nick's yes, and promotion needs "
          "CLAUDE.md step 5 (out-of-sample and 40 forward paper trades). Not financial advice."]
    return "\n".join(L) + "\n"


def _part_f_md(L, F):
    L += ["## Part F: multi-day rules in shares (daily bars, 2016-01..2026-06, never L1/L2)", ""]
    if not F:
        L += ["NOT RUN (no daily bars found).", ""]
        return
    L.append("Rules: F1 `rsi2` (Connors & Alvarez 2008) and F2 `tom` (Lakonishok & Smidt 1988; McConnell & Xu 2008); $10,000 a "
             "trade; costs per side $0.01 a share (U-ETF) or 0.05% of the price (U-STK); booked on the exit day. SMA(200) needs 200 "
             "bars inside one segment, so DEV rsi2 signals start about May 2025 (L2 is never read).")
    L.append("")
    for k in ("rsi2|U-ETF", "rsi2|U-STK", "tom|U-ETF", "tom|U-STK"):
        o = F.get(k)
        if o is not None:
            _fpass_md(L, k, o, ("BACKTEST, real daily bars" + (f", {SB}" if "U-STK" in k else "")))
    L += ["### F-opt (DEV REAL)", ""]
    for k, o in (F.get("fopt") or {}).items():
        if o.get("bar") is None:
            L.append(f"- **{k}**: NOT RUN ({o.get('why')}).")
            continue
        L.append(f"**{k}** (calls 30-60 days, BS-EST delta 0.60-0.80 nearest 0.70; REAL Alpaca option prices): **{_yn(o['bar']['pass'])}**; "
                 f"{o.get('targets')} share trades to carry, not priced: {o.get('skips') or 'none'}; late exits (first print after 09:34): "
                 f"{o.get('late_exits', 0)}.")
        _checks(L, o["bar"]["checks"])
        L += _head(OP_COLS)
        L.append(_row(_op_cells(o["bar"]["dev"])))
        _account_md(L, o.get("account"))
        L.append("")


def _part_g_md(L, G):
    L += ["## Part G: news and catalysts on all stocks (U-STK, SURVIVORSHIP-BIASED)", ""]
    if not G:
        L += ["NOT RUN (no EDGAR records or bars found).", ""]
        return
    ev = G.get("events", {})
    L.append(f"EDGAR 8-K events (acceptance timestamps from each filing's index headers): {ev}.")
    L.append("")
    for k, o in (G.get("G1") or {}).items():
        _fpass_md(L, f"G1 {k}", o, f"BACKTEST, real 1-minute bars, {SB}")
    g2 = G.get("G2")
    L += ["### G2 pre_earn_straddle (DEV REAL)", ""]
    if not g2 or g2.get("pass_bar") is None:
        L += [f"NOT RUN ({(g2 or {}).get('why', 'no input')}).", ""]
        return
    from .edgar import LOOKAHEAD
    pb = g2["pass_bar"]
    L.append(f"**{LOOKAHEAD}.**")
    L.append(f"**G2** (ATM straddle of the first expiry 10-60 days out, bought at the close of t-3, out before the report; 5% "
             f"half-spread per leg per side, $0.65 per contract per side; REAL Alpaca option prices, {SB}): **{_yn(pb['pass'])}**")
    _checks(L, pb["checks"])
    L.append(f"- Events {pb['events']}; mean return per straddle {_f(pb['mean_ret'], 4)} (2x half-spread {_f(pb['mean_ret_2x'], 4)}); "
             f"PF on returns {pb['pf_ret']}; random-date benchmark 95th percentile {_f(pb['p95_random'], 4)} ({g2.get('pool_events')} events "
             f"with priced pool dates); $ per straddle {pb['dollars']}; half-years {pb['half_years']}.")
    L.append(f"- Accepted during market hours (held past the acceptance by the literal rule): {pb['intraday_events']}; without them "
             f"(information): {pb['without_intraday']}. Events not priced: {g2.get('skips') or 'none'}.")
    _account_md(L, g2.get("account"))
    L.append("")


def _part_h_md(L, H, dsr):
    L += ["## Part H: the honest tweak search (run 7's factory procedure on round 8's share trades)", ""]
    if not H:
        L += ["NOT RUN (no round-8 share trade file found).", ""]
        return
    L.append(f"Shares on real stock bars in every year (HIST 2016-2024 and DEV 2024-2026; no option model). The rule is found on "
             f"2016-2019 only and frozen; holdout 1 = 2020-01..2024-01, holdout 2 = DEV. {len(H['order'])} strategies run (the "
             f"written count is {H['written_count']}).")
    L.append("")
    L += _head(("strategy", "HIST trades", "HIST PF", "DEV trades", "DEV PF", "rule (2016-2019)", "holdout 1", "holdout 2", "learner survivors",
                "verdict", "DSR"))
    for name in H["order"]:
        s = H["strategies"][name]
        ph, pd_ = s["all_days"]["periods"]["HIST"], s["all_days"]["periods"]["DEV"]
        rb = s["rule"]
        rule = factory._rule_txt(rb["rule"]) if rb.get("rule") else "none"
        h1 = _yn(rb["holdout1"]["pass"]) if rb.get("holdout1") else "-"
        h2 = _yn(rb["holdout2"]["pass"]) if rb.get("holdout2") else "-"
        ls = [m for m, g in (s["learner"].get("models") or {}).items() if g["survives"]]
        L.append(_row([name, ph.get("trades"), _f(ph.get("pf")), pd_.get("trades"), _f(pd_.get("pf")), rule, h1, h2, ", ".join(ls) or "none",
                       s["verdict"], _f(dsr.get(f"H {name} chosen"), 4)]))
    L.append("")
    for name in H["order"]:
        s = H["strategies"][name]
        rb = s["rule"]
        L.append(f"**{name}**: verdict {s['verdict']} ({s['verdict_why']}); rule: {rb.get('why_not') or 'survives'}.")
        if rb.get("holdout1"):
            _checks(L, [("holdout 1: " + n, ok) for n, ok in rb["holdout1"]["checks"]])
            _checks(L, [("holdout 2: " + n, ok) for n, ok in rb["holdout2"]["checks"]])
        for m, g in (s["learner"].get("models") or {}).items():
            L.append(f"  - learner {m}: {'survives' if g['survives'] else g['why_not']}")
        if s["learner"].get("walk_forward", {}).get("error"):
            L.append(f"  - learner: {s['learner']['walk_forward']['error']}")
    L.append("")


def _part_i_md(L, I):
    L += ["## Part I: FIN-H on the weekly expiry (w5-10d03-12t07, DEV REAL)", ""]
    if not I:
        L += ["NOT RUN (no weekly option files found).", ""]
        return
    L.append(f"FIN-H's entry (11:00 calls, relative volume >= 1.06) and exit (i) (-95% stop, no target, all out 15:25) on the nearest "
             f"expiry 5-10 calendar days out, |delta| 0.03-0.12 nearest 0.07. 2% MODELED-SPREAD + $0.65 a side. **{_yn(I['pass'])}** "
             f"(Addendum 10.1's DEV bar); steadier than FIN-H: **{'yes' if I['steadier']['steadier'] else 'no'}**.")
    _checks(L, I["bar"]["checks"])
    _checks(L, [("steadier: " + n, ok) for n, ok in I["steadier"]["checks"]])
    L += _head(("variant",) + OP_COLS)
    L.append(_row(["weekly (w5-10d03-12t07)"] + _op_cells(I["bar"]["dev"])))
    L.append(_row(["FIN-H 0DTE (d03-12t07), same pass"] + _op_cells(I["finh_0dte_dev"])))
    L.append(f"- Same days ({I['steadier']['common_days']}): weekly {I['steadier']['variant'].get('total')} vs FIN-H "
             f"{I['steadier']['fin_h'].get('total')}. Skips: {I.get('skips')}. Files: {I.get('cover')}.")
    _account_md(L, I.get("account"))
    L.append("")


def _part_s_md(L, S):
    L += ["## Part S: the 1-minute option scalper (SPY + QQQ 0DTE, DEV REAL)", ""]
    if not S:
        L += ["NOT RUN (no DEV option or stock bars found).", ""]
        return
    L.append(f"Costs: {S.get('spread')}. Plus $0.65 per contract per side; stress = 2x the half-spread on every fill; Robinhood view "
             f"$0.03 a side (information). Cell chosen on {S['choice']} (highest PF among cells with 200+ trades), frozen, tested on "
             f"{S['test']}.")
    L.append(f"Strike coverage of the existing +/-3% band (pick attempts that found no strike in the delta band): {S.get('coverage')}.")
    L.append("")
    for key, r in S["evaluate"].items():
        sig, rule = key.split("|")
        head = f"**{sig} on {rule}**: chosen cell {r['chosen'] or 'none'}; test **{_yn(r['pass_'])}**"
        L.append(head + (f" (first failed check: {r['why_not']})" if r.get("why_not") else ""))
        L += _head(("cell", "half") + OP_COLS + ("PF 2x desk", "PF RH fees"))
        for cid, c in r["cells"].items():
            for half in ("choice", "test"):
                s = c[half]
                L.append(_row([cid + (" (chosen)" if cid == r["chosen"] else ""), half] + _op_cells(s) + [_f(s.get("pf_2x_desk")), _f(s.get("pf_rh"))]))
        if r.get("test"):
            _checks(L, r["test"]["checks"])
            L.append(f"- Two-month blocks: {r['test']['blocks']}")
            sz = r["s_size"]
            L.append(f"- S-size (5 contracts when the trigger agrees with the day and rvol >= 1.06, else 3): **{_yn(sz['pass'])}**; P/L "
                     f"{_f(sz['pnl'])}, PF {sz['pf']}, worst losing streak {_f(sz['worst_losing_streak'])}, max drawdown {_f(sz['max_dd'])} "
                     f"({sz['account']['max_dd_pct_3000']}% of $3,000); {sz['five']} trades at 5, {sz['three']} at 3; debit x contracts as "
                     f"% of $3,000 {sz['account']['debit_pct_3000']}.")
            _checks(L, sz["checks"])
            _account_md(L, r.get("account"))
        L.append("")
    L += ["### Underlying first (information only): the next 5-minute move after each trigger, SPY + QQQ stock bars", ""]
    for name, u in (S.get("underlying") or {}).items():
        L += [f"**{name}**"] + _head(("year", "trades", "hit rate", "mean bps", "random mean bps", "random 95th pct", "random hit rate", "p"))
        for y, s in u["by_year"].items():
            L.append(_row([y, s.get("trades"), s.get("hit_rate"), s.get("mean_bps"), s.get("random_mean_bps"), s.get("random_p95_bps"),
                           s.get("random_hit_rate"), s.get("p")]))
        L.append("")


def _book_md(L, B):
    L += ["## The book: FIN-H plus every round-9 survivor", ""]
    if not B:
        L += ["NOT RUN.", ""]
        return
    L.append("Sleeves: " + ", ".join(f"{k} ({v})" for k, v in B["kinds"].items()) + ".")
    for key in ("hist", "dev", "mixed"):
        w = B["windows"][key]
        b = w["res"]["book"]
        L.append(f"- **{w['label']}**: total {_f(b.get('total'))}, average a year {_f(b.get('avg_per_year'))}, max drawdown {_f(b.get('max_dd'))}, "
                 f"months green {b.get('months_green')}, weeks green {b.get('weeks_green')}, longest losing-month run "
                 f"{b.get('longest_losing_months')}, worst month {b.get('worst_month')}, Sharpe {_f(b.get('sharpe'))}.")
        L.append("  - shares of the total: " + ", ".join(f"{k} {v.get('share_of_total')}" for k, v in w["res"]["sleeves"].items()))
    L.append("- Correlation matrix (DEV): " + str(B["windows"]["dev"]["res"].get("corr")))
    for k, v in (B.get("steadiness") or {}).items():
        L.append(f"- {k}: daily correlation with FIN-H {v['corr_finh']} over {v['sessions']} sessions -> "
                 f"{'adds steadiness' if v['adds_steadiness'] else 'does not add steadiness'} (needs < 0.3).")
    L += ["", "Per year:"] + _head(("year", "prices", "total", "max DD", "months green", "Sharpe"))
    for y, v in B["years"].items():
        b = v["book"]
        L.append(_row([y, v["prices"], _f(b.get("total")), _f(b.get("max_dd")), b.get("months_green"), _f(b.get("sharpe"))]))
    _account_md(L, B.get("account"), "Book account view (information, $3,000 account, DEV REAL)")
    L.append("")


def summary_lines(res):
    out = []
    F = res.get("F") or {}
    for k in ("rsi2|U-ETF", "rsi2|U-STK", "tom|U-ETF", "tom|U-STK"):
        o = F.get(k)
        if o is None or o.get("pass_bar") is None:
            out.append(f"F {k}: NOT RUN")
            continue
        s = o["pass_bar"]["stats"]
        out.append(f"F {k}{' (' + SB + ')' if 'U-STK' in k else ''}: {_yn(o['pass'])}, {s.get('trades')} trades, exp ${s.get('expectancy')}, "
                   f"PF {s.get('pf')}, PF 2x {s.get('pf_2x')}" + ("" if o["pass"] else f" (first fail: {_first_fail(o['pass_bar']['checks'])})"))
    for k, o in (F.get("fopt") or {}).items():
        if o.get("bar") is None:
            out.append(f"F-opt {k}: NOT RUN")
        else:
            d = o["bar"]["dev"]
            out.append(f"F-opt {k} (REAL): {_yn(o['bar']['pass'])}, {d.get('trades')} trades, exp ${d.get('expectancy')}, PF {d.get('pf')}, PF 2x {d.get('pf_2x')}")
    G = res.get("G") or {}
    for k, o in (G.get("G1") or {}).items():
        if o.get("pass_bar") is None:
            out.append(f"G1 {k}: NOT RUN")
        else:
            s = o["pass_bar"]["stats"]
            out.append(f"G1 {k} ({SB}): {_yn(o['pass'])}, {s.get('trades')} trades, exp ${s.get('expectancy')}, PF {s.get('pf')}"
                       + ("" if o["pass"] else f" (first fail: {_first_fail(o['pass_bar']['checks'])})"))
    g2 = G.get("G2")
    if g2 and g2.get("pass_bar"):
        pb = g2["pass_bar"]
        out.append(f"G2 pre_earn_straddle (REAL, {SB}, LOOK-AHEAD CAVEAT): {_yn(pb['pass'])}, {pb['events']} events, mean return "
                   f"{_f(pb['mean_ret'], 4)}, PF {pb['pf_ret']}, benchmark p95 {_f(pb['p95_random'], 4)}")
    elif G:
        out.append("G2 pre_earn_straddle: NOT RUN")
    H = res.get("H")
    if H:
        for name in H["order"]:
            s = H["strategies"][name]
            out.append(f"H {name} (shares, real bars): verdict {s['verdict']}")
    I = res.get("I")
    if I:
        d = I["bar"]["dev"]
        out.append(f"I w5-10d03-12t07 (REAL): {_yn(I['pass'])}, {d.get('trades')} trades, exp ${d.get('expectancy')}, PF {d.get('pf')}, "
                   f"PF 2x {d.get('pf_2x')}; steadier than FIN-H: {'yes' if I['steadier']['steadier'] else 'no'}")
    S = res.get("S")
    if S:
        for key, r in S["evaluate"].items():
            t = (r.get("test") or {}).get("stats") or {}
            sz = r.get("s_size") or {}
            out.append(f"S {key} (REAL): cell {r['chosen'] or 'none'}, test {_yn(r['pass_'])}, {t.get('trades', 0)} trades, PF {t.get('pf')}, "
                       f"PF 2x {t.get('pf_2x')}; S-size {_yn(sz.get('pass')) if sz else '-'}")
    B = res.get("book")
    if B:
        b = B["windows"]["dev"]["res"]["book"]
        out.append(f"Book (DEV REAL, {len(B['kinds'])} sleeves): total {_f(b.get('total'))}, max DD {_f(b.get('max_dd'))}, months green "
                   f"{b.get('months_green')}; adds steadiness: " +
                   (", ".join(k for k, v in (B.get("steadiness") or {}).items() if v["adds_steadiness"]) or "none"))
    return out
