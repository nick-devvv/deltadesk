#!/usr/bin/env python3
"""tools/sprint_round8.py - SPRINT_PLAN Amendment 10 with Addenda 10.1, 10.2 and 10.3: round 8 (research only; reads cached
bars and trade files, never trades, no network).

  python3 tools/sprint_round8.py              # after tools/sprint_run.py on sprint/specs/round8_{hist,dev}_v1.json

Reads:
  * the round-8 engine trade files (newest data/sprint/trades_round8_{hist,dev}_v1_*.csv.gz: B3 newhigh_c and B4);
  * run 7's factory trade files (newest data/sprint/trades_factory_{hist,dev}_v1_*.csv.gz): FIN-H (otm_c_1100, f_rvol >= 1.06)
    and the B2 sleeves (otm_c_1030 / otm_c_1100 / otm_c_1200 with f_rvol >= 1.06); the seven B1 features are re-stamped from
    cached bars where a row lacks them (trade P/L unchanged);
  * cached stock bars (SPY, QQQ, IWM; HIST from its 2015-11-01 warm-up, DEV from 2024-08-01; VIXY daily) for Part A and the
    Part D shares, and cached option bars (DEV real 0DTE + next expiry) or MODELED tapes (HIST, run 4's
    data/sprint/calib_modeled.json) for the option pass (D grids + random-side twins, A-opt, A3's twins).
Runs every part (sprint/shares.py, sprint/optpass.py, sprint/round8.py), then the book; counts the trials (192 + the run
logs) and the deflated Sharpe. Writes data/sprint/round8_<date>.md and .json, the share trade file
data/sprint/trades_round8_shares_<date>.csv.gz and the option-pass trade files
data/sprint/trades_round8_options_{hist,dev}_<date>.csv.gz, and prints the summary table. Every number is labeled BACKTEST and
MODELED / REAL (options) or real stock bars (shares). Refuses trade rows dated inside L1 or L2 and HIST/DEV rows outside
their period; the share loader refuses locked ranges.
"""
import argparse
import csv
import glob
import json
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from sprint import data, engine, features, optpass, periods, round8, runner, shares  # noqa: E402
from sprint import modeled as MD  # noqa: E402


def newest(pattern):
    files = sorted(f for f in glob.glob(pattern) if "@" not in Path(f).name)
    return files[-1] if files else None


def load_rows(path, ids, src):
    """{run_id: rows} from an engine trade file, only the given run ids (stress '@' runs dropped)."""
    df = pd.read_csv(path, compression="gzip", low_memory=False)
    df = df[df["run_id"].isin(ids) & ~df["run_id"].astype(str).str.contains("@")]
    df = df.drop_duplicates(subset=["run_id", "symbol", "day", "signal_idx", "entry_time"])
    out = {i: [] for i in ids}
    for r in df.to_dict("records"):
        r["_src"] = src
        r["day"] = str(r["day"])[:10]
        out[r["run_id"]].append(r)
    return out


def check_rows(rows):
    for r in rows:
        d = date.fromisoformat(r["day"])
        hit = periods.overlaps(d, d)
        if hit:
            return f"REFUSED: a trade on {d} is inside locked period {', '.join(hit)} ({r.get('run_id', '')})"
        lo, hi = periods.HIST if r["_src"] == "HIST" else periods.DEV
        if not lo <= d <= hi:
            return f"REFUSED: a {r['_src']} trade on {d} is outside {r['_src']} {lo}..{hi} ({r.get('run_id', '')})"
    return None


def run_log(patterns, ids):
    rows = {}
    for f in sorted({f for p in patterns for f in glob.glob(p)}):
        try:
            with open(f) as fh:
                for r in csv.DictReader(fh):
                    if r.get("run_id") in ids:
                        rows[r["run_id"]] = r
        except OSError:
            continue
    return rows


def count_trials(out, patterns=None):
    """Rows in docs/research/sprint_runs.csv plus the run logs (default data/sprint/runs_*.csv, as runner.count_prior_trials)."""
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


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def twin_check(h, d):
    """None when the HIST and DEV round-8 specs hold the same runs and the same option pass, else the reason."""
    rh, rd = engine.expand(h), engine.expand(d)
    runner.validate(rh)
    runner.validate(rd)
    strip = lambda r: json.loads(engine.run_key(r))
    if [strip(r) for r in rh] != [strip(r) for r in rd] or [r["block"] for r in rh] != [r["block"] for r in rd]:
        return "the HIST and DEV round-8 specs do not hold the same runs in the same order"
    if h.get("option_pass") != d.get("option_pass"):
        return "the HIST and DEV round-8 specs do not hold the same option pass"
    if str(h.get("period", "")).upper() != "HIST" or h.get("tapes") != "modeled" or \
            str(d.get("period", "DEV")).upper() != "DEV" or d.get("tapes", "real") != "real":
        return "the HIST spec must be HIST with modeled tapes and the DEV spec DEV with real tapes"
    return None


def grid_of(spec):
    g = (spec.get("option_pass") or {}).get("grid") or {}
    stops, targets = g.get("stops"), g.get("targets")
    if stops != list(optpass.GRID_STOPS) or targets != [0.30, 0.50, None] or g.get("signal_stop") != optpass.SIGNAL_STOP \
            or g.get("none_target") != optpass.NONE_TARGET or g.get("allout") != "15:25":
        raise ValueError("the spec's option_pass grid is not Addendum 10.3's (stops 10/20/30/50%, targets 30/50%/none, signal stop 20%)")
    return optpass.GRID


def main(argv=None):
    ap = argparse.ArgumentParser(description="SPRINT_PLAN Amendment 10 + Addenda 10.1-10.3: round 8 (research only)")
    ap.add_argument("--hist", default=None, help="round-8 HIST engine trade file (default: newest trades_round8_hist_v1_*.csv.gz)")
    ap.add_argument("--dev", default=None, help="round-8 DEV engine trade file (default: newest trades_round8_dev_v1_*.csv.gz)")
    ap.add_argument("--factory-hist", default=None, help="run 7's HIST trade file (default: newest trades_factory_hist_v1_*.csv.gz)")
    ap.add_argument("--factory-dev", default=None, help="run 7's DEV trade file (default: newest trades_factory_dev_v1_*.csv.gz)")
    ap.add_argument("--hist-spec", default=str(HERE / "sprint" / "specs" / "round8_hist_v1.json"))
    ap.add_argument("--dev-spec", default=str(HERE / "sprint" / "specs" / "round8_dev_v1.json"))
    ap.add_argument("--factory-hist-spec", default=str(HERE / "sprint" / "specs" / "factory_hist_v1.json"))
    ap.add_argument("--factory-dev-spec", default=str(HERE / "sprint" / "specs" / "factory_dev_v1.json"))
    ap.add_argument("--data", default=None, help="cache root (default data/alpaca)")
    ap.add_argument("--calib", default=None, help="MODELED calibration (default data/sprint/calib_modeled.json)")
    ap.add_argument("--opt-hist", default=None, help="reuse an option-pass HIST trade file instead of running the pass")
    ap.add_argument("--opt-dev", default=None, help="reuse an option-pass DEV trade file instead of running the pass")
    ap.add_argument("--runs-csv", nargs="+", default=None, help="run logs (default data/sprint/runs_*.csv)")
    ap.add_argument("--symbols", default="SPY,QQQ,IWM")
    ap.add_argument("--out", default=str(HERE / "data" / "sprint"))
    ap.add_argument("--today", default=None)
    ap.add_argument("--limit-days", type=int, default=None, help="first N sessions per symbol in the option pass (smoke test only)")
    x = ap.parse_args(argv)
    t0 = time.time()
    out = Path(x.out)
    out.mkdir(parents=True, exist_ok=True)
    today = x.today or date.today().isoformat()
    log = lambda s: print(s, flush=True)
    specs = {k: json.loads(Path(p).read_text()) for k, p in (("HIST", x.hist_spec), ("DEV", x.dev_spec))}
    why = twin_check(specs["HIST"], specs["DEV"])
    if why:
        print(f"REFUSED: {why}", file=sys.stderr)
        return 2
    grid = grid_of(specs["HIST"])
    studies = optpass.expand_studies(specs["HIST"])
    runs = {k: engine.expand(s) for k, s in specs.items()}
    fspecs = {k: engine.expand(json.loads(Path(p).read_text())) for k, p in (("HIST", x.factory_hist_spec), ("DEV", x.factory_dev_spec))}
    files = {"HIST": x.hist or newest(str(out / f"trades_{specs['HIST']['spec_id']}_*.csv.gz")),
             "DEV": x.dev or newest(str(out / f"trades_{specs['DEV']['spec_id']}_*.csv.gz")),
             "FHIST": x.factory_hist or newest(str(out / "trades_factory_hist_v1_*.csv.gz")),
             "FDEV": x.factory_dev or newest(str(out / "trades_factory_dev_v1_*.csv.gz"))}
    for k, f in files.items():
        if not f or not Path(f).exists():
            print(f"no {k} trade file found (round 8 needs run 7's factory trade files and the round-8 engine runs: "
                  "tools/sprint_run.py on sprint/specs/round8_hist_v1.json and round8_dev_v1.json)", file=sys.stderr)
            return 2
    log(f"sprint_round8: round-8 HIST {files['HIST']}, DEV {files['DEV']}; run 7 HIST {files['FHIST']}, DEV {files['FDEV']}")
    e8, allrows = {}, []
    for src in ("HIST", "DEV"):
        ids = {r["run_id"]: r["block"] for r in runs[src]}
        got = load_rows(files[src], set(ids), src)
        e8[src] = {ids[i]: v for i, v in got.items()}
        allrows += [r for v in got.values() for r in v]
    fblk = {}
    for src, key in (("HIST", "FHIST"), ("DEV", "FDEV")):
        ids = {r["run_id"]: r["block"] for r in fspecs[src] if r["block"] in round8.B2_SLEEVES}
        got = load_rows(files[key], set(ids), src)
        fblk[src] = {ids[i]: v for i, v in got.items()}
        allrows += [r for v in got.values() for r in v]
    why = check_rows(allrows)
    if why:
        print(why, file=sys.stderr)
        return 2
    rv = lambda rows: [r for r in rows if (_num(r.get("f_rvol")) or 0) >= 1.06 and _num(r.get("f_rvol")) is not None]
    finh = {src: rv(fblk[src].get("otm_c_1100", [])) for src in ("HIST", "DEV")}
    sleeves = {s: rv(fblk["HIST"].get(s, [])) + rv(fblk["DEV"].get(s, [])) for s in round8.B2_SLEEVES}
    warnings = []
    for s in round8.B2_SLEEVES:
        if not sleeves[s]:
            warnings.append(f"run 7's {s} trades are missing from the factory trade files.")
    # stock bars (shares, B1 re-stamping, option pass)
    syms = [s.strip() for s in x.symbols.split(",") if s.strip()]
    series = {}
    for sym in syms:
        series[("HIST", sym)] = shares.load_series(sym, periods.WARMUP["HIST"], periods.HIST[1], x.data)
        series[("DEV", sym)] = shares.load_series(sym, periods.DEV[0], periods.DEV[1], x.data)
        log(f"  bars {sym}: HIST {len(series[('HIST', sym)].days)} sessions (with warm-up), DEV {len(series[('DEV', sym)].days)}")
    vd = data.read_daily("VIXY", x.data)
    log(f"  VIXY daily: {'MISSING (A3 and the VIXY features stay empty)' if vd is None else str(len(vd)) + ' closes'}")
    if vd is None:
        warnings.append("VIXY daily closes are missing: A3 never trades and f_vixy_chg1 / f_vixy_z20 are empty.")
    aux = {"VIXY_D": vd}
    old = lambda rows: sum(1 for r in rows if all(features.missing(r, [k]) for k in features.NEW7))
    n_old = sum(old(sleeves[s]) for s in round8.B2_SLEEVES)
    for s in round8.B2_SLEEVES:
        features.restamp(sleeves[s], series, aux, x.data)
    features.restamp(finh["HIST"] + finh["DEV"], series, aux, x.data)
    if n_old:
        warnings.append(f"{n_old} run-7 sleeve trades were written before the round-8 features (B1); re-stamped from cached bars "
                        "(P/L unchanged).")
    # Part A + Part D shares
    t1 = time.time()
    sh_trades, cover = shares.run(series, vd, progress=log)
    sp = out / f"trades_round8_shares_{today}.csv.gz"
    shares.write_trades(sp, sh_trades)
    log(f"shares done in {time.time() - t1:.0f}s: {sum(len(v) for v in sh_trades.values())} trades -> {sp}")
    # the option pass
    opt, opt_files = {}, {}
    for src, mode, arg in (("HIST", "modeled", x.opt_hist), ("DEV", "real", x.opt_dev)):
        if arg:
            opt[src] = pd.read_csv(arg, compression="gzip", low_memory=False)
            opt[src]["day"] = opt[src]["day"].astype(str).str[:10]
            opt_files[src] = arg
            log(f"option pass {src}: reused {arg} ({len(opt[src])} trades)")
            continue
        t2 = time.time()
        calib = None
        if mode == "modeled":
            cp = Path(x.calib) if x.calib else out / "calib_modeled.json"
            calib = MD.load_calib(cp)
            used = sorted({f"{st['contract']}|{sd} <- {MD.multiplier_for(calib, st['contract'], sd)[1]} x"
                           f"{MD.multiplier_for(calib, st['contract'], sd)[0]:.3f}" for st in studies for sd in ("C", "P")})
            log(f"  option pass HIST: {MD.LABEL}; calibration {cp} (sha256 {periods.sha256_file(cp)[:12]}); " + "; ".join(used))
        a, b = periods.HIST if src == "HIST" else periods.DEV
        col = optpass.run({s: series[(src, s)] for s in syms}, studies, a, b, mode, root=x.data, calib=calib, aux=aux, progress=log,
                          limit_days=x.limit_days)
        opt[src] = col.frame()
        op = out / f"trades_round8_options_{src.lower()}_{today}.csv.gz"
        optpass.write(op, opt[src])
        opt_files[src] = str(op)
        log(f"option pass {src} ({'MODELED' if mode == 'modeled' else 'REAL'}) done in {time.time() - t2:.0f}s: {len(opt[src])} trades -> {op}")
    # run logs and trials
    ids = {r["run_id"] for k in runs for r in runs[k]}
    logs = run_log(x.runs_csv or [str(out / "runs_*.csv")], ids)
    note = f"{len(logs)} of {len(ids)} round-8 engine runs found in the run logs" if logs else "no run-log rows found for the round-8 engine runs"
    for k in runs:
        for r in runs[k]:
            lg = logs.get(r["run_id"])
            n = len(e8[k].get(r["block"], []))
            if lg is not None and int(lg.get("trades") or 0) != n:
                warnings.append(f"{r['run_id']}: run log says {lg.get('trades')} trades, the trade file has {n}.")
            if lg is not None and ("MEASURED" in lg.get("slippage", "") or "sensitivity" in lg.get("slippage", "")):
                warnings.append(f"{r['run_id']} did not use the pre-registered 2% MODELED-SPREAD (see the run log).")
    n_prior = count_trials(out, x.runs_csv)
    res = round8.run(sh_trades, finh, sleeves, e8, opt, studies, grid, n_prior)
    meta = {"today": today, "hist_spec": x.hist_spec, "dev_spec": x.dev_spec, "hist_sha": periods.sha256_file(x.hist_spec),
            "dev_sha": periods.sha256_file(x.dev_spec), "runlog_note": note, "warnings": warnings, "files": files,
            "share_file": str(sp), "option_files": opt_files,
            "files_note": f"round-8 engine HIST `{files['HIST']}`, DEV `{files['DEV']}`; run 7 HIST `{files['FHIST']}`, DEV `{files['FDEV']}`; "
                          f"shares `{sp}`; option pass HIST `{opt_files.get('HIST')}`, DEV `{opt_files.get('DEV')}`",
            "coverage": {src: {s: len(v) for s, v in d.items()} for src, d in cover.items()}}
    md = round8.render(res, meta)
    mp, jp = out / f"round8_{today}.md", out / f"round8_{today}.json"
    mp.write_text(md)
    jp.write_text(json.dumps(round8.clean({"meta": meta, "result": res}), indent=1))
    print("\n".join(round8.summary_lines(res)))
    for w in warnings:
        print(f"WARNING: {w}")
    print(f"round 8 done in {time.time() - t0:.0f}s\nreport: {mp}\njson:   {jp}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
