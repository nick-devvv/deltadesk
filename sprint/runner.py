"""sprint/runner.py - runs a sprint spec file end to end (used by tools/sprint_run.py; importable for tests).

  1. guard the period (DEV by default; L1/L2 only with --locked <name> --frozen <spec sha256>, see periods.guard)
  2. expand the spec into runs (entry x exit x params), validate every field
  3. pass 1: every run over the period (sprint/engine.py), all trades to data/sprint/trades_<spec>_<date>.csv.gz
  4. robustness on the top-K runs (by expectancy, at least `min_trades` trades): one-step nudges, matched random
     entries, made-up levels (level-based runs), plus random day-skips for every filtered run that has its
     unfiltered twin in the spec, by-stretch, without-best-5, both sides, day-block bootstrap CI, deflated Sharpe
  5. append one row per run to data/sprint/runs_<host>.csv (columns = docs/research/sprint_runs.csv), write
     data/sprint/report_<date>.md, print a compact summary table
Every number is a BACKTEST on cached Alpaca data with a MODELED (or MEASURED) spread; nothing here trades.
"""
import csv
import hashlib
import json
import math
import re
import socket
import statistics
import sys
import time
from collections import Counter
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from . import VERSION, contracts, engine, entries, periods, report as R, sim, spread as SP

REPO = Path(__file__).resolve().parents[1]
RUN_LOG = REPO / "docs" / "research" / "sprint_runs.csv"
VALID = {"stop": {"premium", "level", "noise", "fixed"}, "mechanics": {"desk", "oa1m"}, "tp": {"none", "A", "B", "C", "D", "E"}, "time": {"a", "b", "c", "d"},
         "allout": set(sim.ALLOUT), "tp_buffer": {"$0.03", "0.05%", "0.1atr"}, "contract": set(contracts.RULES),
         "trail": {"none", "be6", "be8", "be10", "be15", "belevel", "L1", "L2", "L3", "hl1m", "hl5m", "lvl", "gb20", "gb30", "gb40",
                   "gb50", "gb60", "vwap", "ema9"}, "side": {"both", "C", "P"},
         "filters": {"after14", "chop2", "trend_only", "noise_trend", "sma20_side", "sma20_side_1pct", "skip_fomc", "skip_fomc_cpi",
                     "vixy_falling", "gap_side_075", "vixy_pctl_le40", "vixy_pctl_ge60", "vixy_not_rising",
                     "vixy_rising_1pct"}}


def label_for(tag):
    if tag == "DEV":
        return "BACKTEST in-sample (DEV)"
    if tag.startswith("NOT_SEEN_BY_OA"):
        return "BACKTEST on the period Option Alpha never saw (inside DEV)"
    return f"BACKTEST {tag}"


def host():
    return re.sub(r"[^A-Za-z0-9_.-]", "_", socket.gethostname() or "host")[:40]


def validate(runs):
    for r in runs:
        if r["entry"] not in entries.SETUPS:
            raise ValueError(f"{r['run_id']}: unknown entry {r['entry']}")
        x = r["exit"]
        for k in ("stop", "tp", "time", "allout", "tp_buffer", "contract", "trail", "mechanics"):
            if getattr(x, k) not in VALID[k]:
                raise ValueError(f"{r['run_id']}: {k}={getattr(x, k)!r} not in {sorted(VALID[k])}")
        if r["side"] not in VALID["side"]:
            raise ValueError(f"{r['run_id']}: side {r['side']}")
        for f in r.get("filters") or ():
            if f not in VALID["filters"]:
                raise ValueError(f"{r['run_id']}: filter {f}")
        if x.rr_min is not None and not (0 < float(x.rr_min) < 20):
            raise ValueError(f"{r['run_id']}: rr_min {x.rr_min}")
        if x.stop == "noise" and not r["entry"].startswith("noise"):
            raise ValueError(f"{r['run_id']}: the noise stop needs a noise entry")
        if x.stop == "fixed":
            if not (x.fixed_stop and x.fixed_target and 0 < x.fixed_stop < 1 and 0 < x.fixed_target <= 10):
                raise ValueError(f"{r['run_id']}: the fixed stop needs fixed_stop in (0, 1) and fixed_target in (0, 10]")
            if x.tp != "none" or x.trail != "none":
                raise ValueError(f"{r['run_id']}: the fixed stop/target exit takes no other take-profit or trail")
        elif x.fixed_stop or x.fixed_target or x.mechanics != "desk":
            raise ValueError(f"{r['run_id']}: fixed_stop/fixed_target/mechanics need stop='fixed'")


def count_prior_trials(out_dir):
    n = 0
    for p in [RUN_LOG] + sorted(Path(out_dir).glob("runs_*.csv")):
        try:
            with open(p) as f:
                n += max(0, sum(1 for _ in csv.reader(f)) - 1)
        except OSError:
            pass
    return n


def _twin(r, by_key):
    """The unfiltered twin of a filtered run (rr_min removed / filters removed), if the spec has it."""
    if r["exit"].rr_min:
        k = engine.run_key(dict(r, exit=replace(r["exit"], rr_min=None)))
        if k in by_key:
            return by_key[k]
    if r.get("filters"):
        k = engine.run_key(dict(r, filters=()))
        if k in by_key:
            return by_key[k]
    return None


def run_spec(spec_path, a=None, b=None, locked=None, frozen=None, data_root=None, chains_dir=None, out_dir=None, host_name=None,
             top_k=None, random_paths=None, fake_seeds=None, robust=True, limit_days=None, trials=None, log=print, today=None,
             spread_pct=None):
    spec_path = Path(spec_path)
    spec = json.loads(spec_path.read_text())
    sha = periods.sha256_file(spec_path)
    if locked:
        names = [x.strip().upper() for x in str(locked).split(",") if x.strip()]
        if len(names) != 1:
            raise periods.LockedPeriod("REFUSED: --locked takes exactly one period (L1 or L2), run once each")
        pa, pb = periods.period_range(names[0])
        a, b = a or pa, b or pb
        tag = names[0]
    else:
        pa, pb = periods.period_range(spec.get("period", "DEV"))
        a, b = a or pa, b or pb
        tag = spec.get("period", "DEV") if (a, b) == (pa, pb) else f"{spec.get('period', 'DEV')}[{a}..{b}]"
    periods.guard(a, b, locked, frozen, spec_path)
    out_dir = Path(out_dir or REPO / "data" / "sprint")
    out_dir.mkdir(parents=True, exist_ok=True)
    host_name = host_name or host()
    today = today or date.today()
    rob = dict(spec.get("robustness") or {})
    top_k = rob.get("top_k", 5) if top_k is None else top_k
    random_paths = rob.get("random_paths", 5) if random_paths is None else random_paths
    fake_seeds = rob.get("fake_seeds", 20) if fake_seeds is None else fake_seeds
    min_trades = rob.get("min_trades", 60)
    runs = engine.expand(spec)
    validate(runs)
    spread_pct = spread_pct if spread_pct is not None else spec.get("spread_pct")
    suffix = f"@s{float(spread_pct) * 100:g}" if spread_pct is not None else ""
    if suffix:                                                  # stress runs get their own run ids and files
        for r in runs:
            r["run_id"] += suffix
    syms = sorted({s for r in runs for s in r["symbols"]})
    spread = SP.SpreadModel(pct=float(spread_pct)) if spread_pct is not None else \
        SP.from_chains(chains_dir or REPO / "data" / "chains", unders=set(syms))
    log(f"sprint {VERSION}: spec {spec['spec_id']} ({len(runs)} runs, sha256 {sha[:12]}), period {tag} {a}..{b}, symbols "
        f"{','.join(syms)}, {spread.describe()}")
    t0 = time.time()
    writer = engine.TradeWriter(out_dir / f"trades_{spec['spec_id']}{suffix}_{today}.csv.gz")
    res, sessions = engine.run_pass(runs, a, b, data_root, spread, progress=log, writer=writer, limit_days=limit_days)
    writer.close()
    log(f"pass 1 done in {time.time() - t0:.0f}s")
    all_sessions = sorted({d for v in sessions.values() for d in v})
    summ = {r["run_id"]: R.summarize(res[r["run_id"]]["trades"], a, b) for r in runs}
    sr = {}
    for r in runs:
        tr = res[r["run_id"]]["trades"]
        ses = sorted({d for s in r["symbols"] for d in sessions.get(s, [])})
        sr[r["run_id"]] = R.sharpe(R.daily_pnl(tr, ses)) if tr else None
    srs = [x for x in sr.values() if x is not None]
    sr_var = statistics.pvariance(srs) if len(srs) > 1 else 0.0
    n_trials = trials or (count_prior_trials(out_dir) + len(runs))
    by_key = {engine.run_key(r): r for r in runs}
    robx = {r["run_id"]: {} for r in runs}
    for r in runs:
        tr = res[r["run_id"]]["trades"]
        ses = sorted({d for s in r["symbols"] for d in sessions.get(s, [])})
        robx[r["run_id"]]["ci95"] = R.bootstrap_ci(tr, ses)
        robx[r["run_id"]]["dsr"] = R.deflated_sharpe(R.daily_pnl(tr, ses), n_trials, sr_var) if tr else None
        tw = _twin(r, by_key)
        if tw is not None:
            t = R.random_skip_test(tr, res[tw["run_id"]]["trades"])
            if t:
                robx[r["run_id"]]["skip_test"] = dict(t, twin=tw["run_id"])
                robx[r["run_id"]]["skip_p"] = t.get("p_value")
    ranked = sorted((r for r in runs if summ[r["run_id"]].get("trades", 0) >= min_trades),
                    key=lambda r: -(summ[r["run_id"]].get("expectancy") or -1e9))
    top_note = None
    if not ranked:
        ranked = sorted((r for r in runs if summ[r["run_id"]].get("trades", 0) > 0), key=lambda r: -(summ[r["run_id"]].get("expectancy") or -1e9))
        top_note = f"no run reached {min_trades} trades: robustness ran on the best runs anyway (flagged)"
    top = ranked[:top_k] if robust else []
    jobs, job_meta = [], {}
    for r in top:
        rid = r["run_id"]
        for what, val, nr in engine.nudges(r):
            k = engine.run_key(nr)
            if k in by_key:
                job_meta.setdefault(rid, {}).setdefault("nudges", []).append((what, val, by_key[k]["run_id"], "spec"))
                continue
            nid = f"{rid}~n{what}={val}"
            jobs.append(dict(nr, run_id=nid, nudge=True))
            job_meta.setdefault(rid, {}).setdefault("nudges", []).append((what, val, nid, "extra"))
        for p in range(random_paths):
            j = engine.random_job(r, res[rid]["trades"], p)
            jobs.append(j)
            job_meta.setdefault(rid, {}).setdefault("random", []).append(j["run_id"])
        if engine.uses_levels(r):
            for sd in range(1, fake_seeds + 1):
                jobs.append(dict(r, run_id=f"{rid}~fake{sd}", fake_seed=sd))
                job_meta.setdefault(rid, {}).setdefault("fake", []).append(f"{rid}~fake{sd}")
    res2 = {}
    if jobs:
        log(f"pass 2 (robustness): {len(jobs)} jobs for the top {len(top)} runs")
        t1 = time.time()
        res2, _ = engine.run_pass(jobs, a, b, data_root, spread, progress=log, limit_days=limit_days)
        log(f"pass 2 done in {time.time() - t1:.0f}s")
    allres = dict(res, **res2)
    for r in top:
        rid = r["run_id"]
        m = job_meta.get(rid, {})
        exp = summ[rid].get("expectancy")
        nud = []
        for what, val, nid, src in m.get("nudges", []):
            s2 = R.metrics(R.ordered(allres[nid]["trades"]))
            nud.append({"param": what, "value": val, "run": nid, "src": src, "trades": s2.get("trades", 0),
                        "pf": s2.get("profit_factor"), "expectancy": s2.get("expectancy")})
        robx[rid]["nudges"] = nud
        pfs = [x["pf"] for x in nud if x["pf"] is not None]
        robx[rid]["nudge_min_pf"] = min(pfs) if pfs else None
        rnd = [R.metrics(allres[j]["trades"]).get("expectancy") for j in m.get("random", [])]
        rnd = [x for x in rnd if x is not None]
        robx[rid]["random_exp"] = rnd
        robx[rid]["random_beat"] = R.beat_share(exp, rnd)
        fk = [R.metrics(allres[j]["trades"]).get("expectancy") for j in m.get("fake", [])]
        fk = [x for x in fk if x is not None]
        robx[rid]["fake_exp"] = fk
        robx[rid]["fake_beat"] = R.beat_share(exp, fk)
    stamp = datetime.now().isoformat(timespec="seconds")
    csv_path = out_dir / f"runs_{host_name}.csv"
    new = not csv_path.exists()
    rows = []
    for r in runs:
        rid = r["run_id"]
        s, rb, sk = summ[rid], robx[rid], res[rid]["skips"]
        notes = [f"spec {spec['spec_id']} sha {sha[:12]}", f"host {host_name}", f"engine {VERSION}", label_for(tag),
                 spread.label, f"signals {res[rid]['signals']}"]
        bl = [v for v in (s.get("blocks_2m") or {}).values() if v.get("trades")]
        if bl:
            notes.append(f"2-month blocks profitable {sum(1 for v in bl if (v.get('net') or 0) > 0)}/{len(bl)}")
        if sk:
            notes.append("skips: " + ", ".join(f"{k} {v}" for k, v in sk.most_common(4)))
        if rb.get("ci95"):
            notes.append(f"exp CI95 {rb['ci95'][0]}..{rb['ci95'][1]}")
        if rb.get("dsr") is not None:
            notes.append(f"DSR {rb['dsr']} (N={n_trials})")
        if rb.get("skip_test"):
            notes.append(f"random day-skip p {rb['skip_test']['p_value']} vs {rb['skip_test']['twin']}")
        fl = set(r.get("filters") or ())
        if "vixy_falling" in fl:
            notes.append("VIX falling filter: proxy: VIXY (last 1m close below its prior close)")
        if fl & {"vixy_not_rising", "vixy_rising_1pct"}:
            notes.append("VIX rising/not rising: proxy: VIXY (last 1m close vs prior close x 1.01)")
        if fl & {"vixy_pctl_le40", "vixy_pctl_ge60"}:
            notes.append("IV-rank proxy: VIXY percentile (252 split-adjusted daily closes; VIXY decay biases it low)")
        if rid in [x["run_id"] for x in top]:
            if rb.get("nudge_min_pf") is not None:
                notes.append(f"nudge min PF {rb['nudge_min_pf']}")
            if rb.get("random_beat") is not None:
                notes.append(f"beats {rb['random_beat']:.0%} of random paths")
            if rb.get("fake_beat") is not None:
                notes.append(f"beats {rb['fake_beat']:.0%} of made-up-level seeds")
        rows.append(R.csv_row(r, s, stamp, tag, spread.label, "; ".join(notes)))
    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=R.COLUMNS, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerows(rows)
    md = render(spec, sha, tag, a, b, runs, summ, robx, res, sessions, top, top_note, spread, n_trials, host_name, csv_path,
                writer.path, time.time() - t0)
    rp = out_dir / f"report_{today}_{spec['spec_id']}{suffix}.md"
    if rp.exists():
        rp = out_dir / f"report_{today}_{spec['spec_id']}{suffix}_{datetime.now():%H%M%S}.md"
    rp.write_text(md)
    log(summary_table(runs, summ))
    log(f"\nrun log: {csv_path}\nreport:  {rp}\ntrades:  {writer.path}")
    return {"runs": runs, "summary": summ, "robust": robx, "csv": csv_path, "report": rp, "results": res, "sessions": sessions,
            "trials": n_trials}


def _lab(r):
    x = r["exit"]
    if x.stop == "fixed":
        f = "+".join(r["filters"])
        return (f"{'+'.join(r['symbols'])} {r['entry']} {r['side']} fixed {x.fixed_stop * 100:g}/{x.fixed_target * 100:g} {x.mechanics} "
                f"{x.contract}" + (f" {f}" if f else ""))
    s = f"{r['entry']} {x.stop[:4]} tp{x.tp}"
    if x.tp in ("B", "C", "D", "E"):
        s += f"/{x.tp_buffer}"
    if x.rr_min:
        s += f" rr{x.rr_min:g}"
    if x.trail != "none":
        s += f" tr:{x.trail}"
    return s + f" t{x.time} {x.allout}"


def summary_table(runs, summ, limit=None):
    rows = sorted(runs, key=lambda r: -(summ[r["run_id"]].get("expectancy") if summ[r["run_id"]].get("expectancy") is not None else -1e9))
    lines = [f"{'run':<18} {'config':<48} {'n':>5} {'win%':>5} {'exp$':>7} {'PF':>5} {'PF2x':>5} {'maxDD$':>8}"]
    for r in rows[:limit] if limit else rows:
        s = summ[r["run_id"]]
        wr = s.get("win_rate")
        lines.append(f"{r['run_id'][-18:]:<18} {_lab(r)[:48]:<48} {s.get('trades', 0):>5} {('-' if wr is None else f'{100 * wr:.0f}'):>5} "
                     f"{R.fmt(s.get('expectancy')):>7} {R.fmt(s.get('profit_factor')):>5} {R.fmt(s.get('pf_2x_slip')):>5} {R.fmt(s.get('max_dd'), 0):>8}")
    return "\n".join(lines)


def _ref_key(r):
    x = r["exit"]
    return f"{'+'.join(r['symbols'])}|{r['entry']}|{r['side']}|{x.fixed_stop * 100:g}/{x.fixed_target * 100:g}|{'+'.join(r['filters']) or '-'}"


def _blocks(s):
    bl = [v for v in (s.get("blocks_2m") or {}).values() if v.get("trades")]
    return f"{sum(1 for v in bl if (v.get('net') or 0) > 0)}/{len(bl)}" if bl else "-"


def _best(runs, summ, pred, min_n):
    c = [r for r in runs if pred(r) and summ[r["run_id"]].get("trades", 0) >= min_n]
    if not c:
        c = [r for r in runs if pred(r) and summ[r["run_id"]].get("trades", 0) > 0]
    return max(c, key=lambda r: summ[r["run_id"]].get("expectancy") or -1e9) if c else None


def render(spec, sha, tag, a, b, runs, summ, robx, res, sessions, top, top_note, spread, n_trials, host_name, csv_path, trades_path, secs):
    min_n = (spec.get("robustness") or {}).get("min_trades", 60)
    L = []
    L.append(f"# Sprint report: {spec['spec_id']} ({tag}), {spread.label}\n")
    L.append(f"Generated {datetime.now():%Y-%m-%d %H:%M} on `{host_name}` by sprint engine `{VERSION}` in {secs / 60:.1f} min. "
             f"Spec sha256 `{sha}`.\n")
    L.append(f"**Every number below is a {label_for(tag)}** on Alpaca 1-minute "
             f"bars, {a} to {b}. Option fills are real traded prices +/- a half-spread: **{spread.describe()}**. "
             "Fees $0.65 per contract per side. P/L is per 1-contract unit. Deltas are BS-EST (Black-Scholes from the option's "
             "price). Nothing here is a live or paper fill.\n")
    cov = ", ".join(f"{s}: {len(v)} sessions" for s, v in sorted(sessions.items()))
    L.append(f"Data: {cov}. Runs in this spec: {len(runs)}. Trials counted for the deflated Sharpe: {n_trials} "
             f"(docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).\n")
    L.append("Known limits: July 2024 is locked (L2), so early-August 2024 sessions have partial history; news and VIX are "
             "unknown in the backtest (rules that need them never fire); a contract needs BS-EST |delta| inside the band, "
             "so some signals have no contract (counted as skips).\n")
    if spread.label != "MEASURED-SPREAD":
        L.append(f"**Cost caveat:** {spread.describe()}. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended "
                 "from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% "
                 "rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, "
                 "small fixed targets) are the most sensitive to it.\n")
    if spec.get("description"):
        L.append(f"Spec: {spec['description']}\n")
    # first answer
    nf = lambda r: r["exit"].stop != "fixed"
    plain = _best(runs, summ, lambda r: nf(r) and r["exit"].tp == "none" and r["exit"].trail == "none", min_n)
    A = _best(runs, summ, lambda r: r["exit"].tp == "A" and r["exit"].trail == "none", min_n)
    B = _best(runs, summ, lambda r: r["exit"].tp == "B" and r["exit"].trail == "none", min_n)
    T = _best(runs, summ, lambda r: r["exit"].trail != "none", min_n)
    O = _best(runs, summ, lambda r: r["exit"].tp in ("C", "D", "E") and r["exit"].trail == "none", min_n)
    picks = [("plain stop + time", plain), ("A: current fixed-% plan", A), ("B: best level target", B), ("best trail", T),
             ("best C/D/E", O)]
    picks = [(n, r) for n, r in picks if r is not None]
    if picks:
        L.append("## Exit families side by side: current plan vs best level target vs best trail\n")
        L.append(f"Best of each family by expectancy among runs with at least {min_n} trades (else the best with any trades).\n")
        L.append(R.table(picks, [("family", lambda p: p[0]), ("run", lambda p: p[1]["run_id"]), ("config", lambda p: _lab(p[1])),
                                 ("trades", lambda p: summ[p[1]["run_id"]].get("trades")),
                                 ("win%", lambda p: None if summ[p[1]["run_id"]].get("win_rate") is None else 100 * summ[p[1]["run_id"]]["win_rate"]),
                                 ("avg win", lambda p: summ[p[1]["run_id"]].get("avg_win")), ("avg loss", lambda p: summ[p[1]["run_id"]].get("avg_loss")),
                                 ("exp $", lambda p: summ[p[1]["run_id"]].get("expectancy")), ("PF", lambda p: summ[p[1]["run_id"]].get("profit_factor")),
                                 ("PF 2x", lambda p: summ[p[1]["run_id"]].get("pf_2x_slip")), ("max DD", lambda p: summ[p[1]["run_id"]].get("max_dd")),
                                 ("CI95 exp", lambda p: "-" if not robx[p[1]["run_id"]].get("ci95") else f"{robx[p[1]['run_id']]['ci95'][0]}..{robx[p[1]['run_id']]['ci95'][1]}")]))
    L.append("")
    fx = [r for r in runs if r["exit"].stop == "fixed"]
    if fx:
        ref = spec.get("oa_reference") or {}
        order_sym = {x: k for k, x in enumerate(spec.get("symbols") or [])}
        fx.sort(key=lambda r: (order_sym.get(r["symbols"][0], 9), r["entry"] != "orb60", r["entry"], r["side"], "+".join(r["filters"]),
                               -r["exit"].fixed_target / r["exit"].fixed_stop, r["exit"].fixed_stop, r["exit"].contract, r["exit"].mechanics))
        L.append("## Fixed premium stop / target runs (Option Alpha's exit; the cross-check)\n")
        L.append("Each row: one symbol, one side, a fixed stop/target of the debit, all out 15:25. `desk` = SPRINT_PLAN's fill "
                 "rules (inside the bar, same-bar stop wins); `oa1m` = OA-LIKE mechanics (checked once a minute on the close, "
                 "filled at the next minute's print). `2m+` = profitable two-month blocks. `OA ref` = Option Alpha's own "
                 "Stage-1 result for the same rule on SPY, Nov 2025-Jun 2026 (fills MODELED by OA, from docs/research/"
                 "sprint_runs.csv); T1/T2 used OA's 1-year window. Different period, different fill model: a cross-check, "
                 "not a replication.\n")
        if any(set(r["filters"]) & {"vixy_pctl_le40", "vixy_pctl_ge60", "vixy_not_rising", "vixy_rising_1pct"} for r in fx):
            L.append("Regime filters: `vixy_pctl_le40` / `vixy_pctl_ge60` = IV-rank **proxy: VIXY percentile** (share of the 252 "
                     "split-adjusted daily VIXY closes ending at the prior close that are at or below it; the window skips the "
                     "locked months, and VIXY's decay biases it low next to a true IV rank); `vixy_not_rising` / `vixy_rising_1pct` = "
                     "VIXY's last finished 1-minute close at the decision vs its prior close x 1.01 (**proxy: VIXY**); "
                     "`gap_side_075` = open vs prior close in (0%, +0.75%] for calls, [-0.75%, 0%) for puts. A run with several "
                     "filters needs all of them. In-sample leads from Option Alpha's optimizer, tested on data OA never saw.\n")
        if any("vixy_falling" in r["filters"] for r in fx):
            L.append("`vixy_falling` = OA's \"VIX falling\" optimizer lead with **proxy: VIXY** (Alpaca has no VIX index): VIXY's last "
                     "finished 1-minute close at the decision is below its prior close. `gap_side_075` = open vs prior close in "
                     "(0%, +0.75%] for calls, [-0.75%, 0%) for puts. Both are in-sample leads from OA's optimizer on its run 023, "
                     "tested here on data OA never saw.\n")
        L.append(R.table(fx, [("run", lambda r: r["run_id"]), ("sym", lambda r: "+".join(r["symbols"])), ("entry", lambda r: r["entry"]),
                              ("side", lambda r: r["side"]), ("stop/tgt", lambda r: f"{r['exit'].fixed_stop * 100:g}/{r['exit'].fixed_target * 100:g}"),
                              ("mech", lambda r: r["exit"].mechanics), ("contract", lambda r: r["exit"].contract),
                              ("filter", lambda r: "+".join(r["filters"]) or "-"), ("n", lambda r: summ[r["run_id"]].get("trades")),
                              ("win%", lambda r: None if summ[r["run_id"]].get("win_rate") is None else 100 * summ[r["run_id"]]["win_rate"]),
                              ("exp $", lambda r: summ[r["run_id"]].get("expectancy")), ("PF", lambda r: summ[r["run_id"]].get("profit_factor")),
                              ("PF 2x", lambda r: summ[r["run_id"]].get("pf_2x_slip")), ("max DD", lambda r: summ[r["run_id"]].get("max_dd")),
                              ("2m+", lambda r: _blocks(summ[r["run_id"]])), ("OA ref", lambda r: ref.get(_ref_key(r), ""))]))
        L.append("")
    # top-K robustness
    L.append(f"## Robustness on the top {len(top)} runs\n")
    if top_note:
        L.append(f"**{top_note}**\n")
    for r in top:
        rid = r["run_id"]
        s, rb = summ[rid], robx[rid]
        L.append(f"### {rid}: {_lab(r)}\n")
        L.append(f"Trades {s.get('trades')}, win {R.fmt(100 * (s.get('win_rate') or 0), 0)}%, avg win {R.fmt(s.get('avg_win'))}, avg loss "
                 f"{R.fmt(s.get('avg_loss'))}, expectancy **{R.fmt(s.get('expectancy'))}** (2x slippage {R.fmt(s.get('expectancy_2x'))}), "
                 f"PF {R.fmt(s.get('profit_factor'))} (2x {R.fmt(s.get('pf_2x_slip'))}), max DD {R.fmt(s.get('max_dd'))}, "
                 f"% of peak kept {R.fmt(s.get('pct_peak_kept'))}, planned R:R {R.fmt(s.get('planned_rr'))} vs actual {R.fmt(s.get('actual_rr'))}, "
                 f"expectancy CI95 {rb.get('ci95')}, deflated Sharpe {R.fmt(rb.get('dsr'), 3)} (N={n_trials}).\n")
        L.append("Checklist (SPRINT_PLAN robustness):\n")
        for name, ok in R.checklist(s, rb):
            L.append(f"- [{'x' if ok else ' '}] {name}")
        L.append("")
        st = dict(s.get("stretches") or {})
        st.update({f"2m: {k}": v for k, v in (s.get("blocks_2m") or {}).items()})
        L.append(R.table(list(st.items()), [("stretch / two-month block", lambda kv: kv[0]), ("trades", lambda kv: kv[1].get("trades")),
                                            ("net $", lambda kv: kv[1].get("net")), ("exp $", lambda kv: kv[1].get("expectancy")),
                                            ("PF", lambda kv: kv[1].get("profit_factor"))]))
        sides = s.get("sides") or {}
        L.append("\nSides: " + "; ".join(f"{'calls' if k == 'C' else 'puts'} n={v.get('trades')} exp {R.fmt(v.get('expectancy'))} "
                                          f"PF {R.fmt(v.get('profit_factor'))}" for k, v in sides.items()))
        L.append("Symbols: " + "; ".join(f"{k} n={v.get('trades')} exp {R.fmt(v.get('expectancy'))} PF {R.fmt(v.get('profit_factor'))}"
                                          for k, v in (s.get("symbols") or {}).items()))
        wb = s.get("without_best5") or {}
        L.append(f"Without the best 5 trades: net {R.fmt(wb.get('net'))}, expectancy {R.fmt(wb.get('expectancy'))}.")
        if rb.get("nudges"):
            L.append("One-step nudges: " + "; ".join(f"{x['param']}={x['value']} n={x['trades']} PF {R.fmt(x['pf'])} exp {R.fmt(x['expectancy'])}"
                                                    for x in rb["nudges"]))
        if rb.get("random_exp"):
            L.append(f"Matched random entries ({len(rb['random_exp'])} paths): expectancy {', '.join(R.fmt(x) for x in rb['random_exp'])}; "
                     f"the run beats {R.fmt(100 * (rb.get('random_beat') or 0), 0)}% of paths.")
        if rb.get("fake_exp"):
            L.append(f"Made-up levels ({len(rb['fake_exp'])} seeds): mean expectancy {R.fmt(statistics.mean(rb['fake_exp']))}; "
                     f"real levels beat {R.fmt(100 * (rb.get('fake_beat') or 0), 0)}% of seeds.")
        if rb.get("skip_test"):
            t = rb["skip_test"]
            L.append(f"Filter vs random day-skips (twin {t['twin']}, {t['skipped_days']} days removed): p = {t['p_value']} "
                     f"(filtered exp {t['filtered_exp']}, random-skip mean {t.get('random_skip_exp_mean')}).")
        L.append(f"Exit reasons: {s.get('exit_reasons')}.")
        L.append(f"Median option MFE {R.fmt(s.get('opt_mfe_median'), 3)}, MAE {R.fmt(s.get('opt_mae_median'), 3)}; median stock MFE "
                 f"${R.fmt(s.get('stock_mfe_median'), 3)}; median distance from the stock's price at the option's peak to the nearest "
                 f"level ${R.fmt(s.get('peak_to_level_median'), 3)}; median minutes held {s.get('minutes_held_median')}.")
        sk = res[rid]["skips"]
        if sk:
            L.append("Skipped signals: " + ", ".join(f"{k} {v}" for k, v in sk.most_common()) + ".")
        L.append("")
    # filters vs random day-skips (all filtered runs)
    sk_rows = [r for r in runs if robx[r["run_id"]].get("skip_test")]
    if sk_rows:
        L.append("## Filters vs random day-skips (every filtered run with its unfiltered twin)\n")
        L.append(R.table(sk_rows, [("run", lambda r: r["run_id"]), ("config", _lab), ("twin", lambda r: robx[r["run_id"]]["skip_test"]["twin"]),
                                   ("days skipped", lambda r: robx[r["run_id"]]["skip_test"]["skipped_days"]),
                                   ("filtered exp", lambda r: robx[r["run_id"]]["skip_test"]["filtered_exp"]),
                                   ("random-skip exp", lambda r: robx[r["run_id"]]["skip_test"].get("random_skip_exp_mean")),
                                   ("p", lambda r: robx[r["run_id"]]["skip_test"]["p_value"])]))
        L.append("")
    # all runs (fixed stop/target runs are already listed in the cross-check table)
    rest = [r for r in runs if r["exit"].stop != "fixed"]
    if rest:
        L.append("## All runs (sorted by expectancy)\n" if len(rest) == len(runs) else
                 "## All other runs (sorted by expectancy; fixed stop/target runs are in the cross-check table)\n")
    order = sorted(rest, key=lambda r: -(summ[r["run_id"]].get("expectancy") if summ[r["run_id"]].get("expectancy") is not None else -1e9))
    sk_share = lambda r: None if not res[r["run_id"]]["signals"] else 100 * (1 - summ[r["run_id"]].get("trades", 0) / res[r["run_id"]]["signals"])
    if rest:
        L.append("`sig` = signals seen, `skip%` = share not traded (no contract, level stop beyond the ceiling, R:R minimum, busy, "
             "no print); the top skip reasons per run are in the run log's notes.\n")
        L.append(R.table(order, [("run", lambda r: r["run_id"]), ("config", _lab), ("sig", lambda r: res[r["run_id"]]["signals"]),
                                 ("skip%", sk_share), ("n", lambda r: summ[r["run_id"]].get("trades")),
                                 ("win%", lambda r: None if summ[r["run_id"]].get("win_rate") is None else 100 * summ[r["run_id"]]["win_rate"]),
                                 ("avg win", lambda r: summ[r["run_id"]].get("avg_win")), ("avg loss", lambda r: summ[r["run_id"]].get("avg_loss")),
                                 ("exp", lambda r: summ[r["run_id"]].get("expectancy")), ("PF", lambda r: summ[r["run_id"]].get("profit_factor")),
                                 ("PF2x", lambda r: summ[r["run_id"]].get("pf_2x_slip")), ("maxDD", lambda r: summ[r["run_id"]].get("max_dd")),
                                 ("kept", lambda r: summ[r["run_id"]].get("pct_peak_kept")), ("pRR", lambda r: summ[r["run_id"]].get("planned_rr")),
                                 ("aRR", lambda r: summ[r["run_id"]].get("actual_rr")), ("DSR", lambda r: robx[r["run_id"]].get("dsr"))]))
    L.append("")
    L.append(f"Run log rows appended to `{csv_path}`; every trade in `{trades_path}`.\n")
    L.append("Labels: BACKTEST (in-sample on DEV). Spread: " + spread.label + ". Delta: BS-EST. Not financial advice: evidence for Nick to decide.\n")
    return "\n".join(L)
