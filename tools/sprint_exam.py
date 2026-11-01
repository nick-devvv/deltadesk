#!/usr/bin/env python3
"""tools/sprint_exam.py - the final locked-period exam (SPRINT_PLAN Amendment 11, extending Amendment 7). Research only: it
reads cached bars and trade files, pulls market data from data.alpaca.markets only (tools/pull_alpaca.py's host guard), and
never trades. Run it from the sprint checkout (~/sprint), never inside ~/desk. The rules are in sprint/exam.py.

  python3 tools/sprint_exam.py fit
      Stage E1 (on Chart, no locked data): fits FIN-L's logit once on all HIST 11:00-call trades (every data/sprint/
      trades_hist_v1_*.csv.gz file's hist_v1-005 rows, as holdout 2 read them; else the newest trades_factory_hist_v1_*'s
      factory_hist_v1-012 rows; the tool records which) and FIN-HS's two B2 models (L2: FIN-H trades through 2024-01-31,
      HIST; L1: through 2026-06-30, HIST + DEV; FIN-H = run 7's otm_c_1100 trades with f_rvol >= 1.06, the seven round-8
      features re-stamped from cached bars where missing), each with its tercile cuts. Writes sprint/specs/
      final_v2_models.json (deterministic bytes) and prints its sha256 and the source files. Refuses any trade row dated
      inside L1/L2; refuses to run once any locked read has happened (data/sprint/exam_log.jsonl records one, or
      data/alpaca_exam/ holds files); refuses to overwrite a models file git already tracks (the models are fit once).

  python3 tools/sprint_exam.py freeze
      (Claude's side, after the models file is committed) writes the exam spec again with the committed models file's
      sha256 and prints the spec's new sha256: the value --frozen takes once the spec is committed.

  python3 tools/sprint_exam.py run --locked L2 --frozen <sha256 of sprint/specs/final_v2_exam.json>
      Stage E2, one shot per period. Refuses unless: --locked names exactly one of L2 / L1; the exam spec is Amendment 11's
      (sprint/exam.canonical_spec), committed, unchanged and hashes to --frozen (periods.guard); no tracked file differs
      from HEAD and no untracked file sits in sprint/, tools/, tests/ or is a top-level .py; the spec carries the models
      sha256 and the committed, unchanged models file hashes to it; the exam log allows it (a re-run of a period needs the
      same spec sha256 and code commit) and the exam cache holds no data of the period without a logged start; the warm-up
      months are in the main cache; the Alpaca keys are set. Every check runs before any request. Then it logs the start (with the
      code commit), pulls the period into data/alpaca_exam/<period>/ (SPY/QQQ/IWM/VIXY 1-minute bars, the VIXY daily closes
      from the spec's vixy_daily_from, SPY/QQQ/IWM 0DTE option bars), runs the reference and FIN-H engine runs at the 2%
      half-spread and at 5% (information), NB-VOL in shares, applies Amendment 11's bars and writes
      data/sprint/exam_<period>_<date>.md/.json, data/sprint/trades_exam_<period>_<date>.csv.gz and
      trades_exam_<period>_shares_<date>.csv.gz (a re-run adds _rerun<N>), then logs the finish. When the other period's
      result exists (same spec), the report gives each finalist's verdict: holds / mixed / fails.
Keys: ALPACA_KEY / ALPACA_SECRET (the desk's paper key: market data only). Never printed.
"""
import argparse
import glob
import json
import os
import socket
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
import pull_alpaca as PA  # noqa: E402
import sprint_pull as SPULL  # noqa: E402
from sprint import data, engine, exam, features, periods, shares  # noqa: E402
from sprint import spread as SP  # noqa: E402

DATA = HERE / "data" / "alpaca"
EXAM_DATA = HERE / "data" / "alpaca_exam"
OUT = HERE / "data" / "sprint"


def say(s):
    print(s, flush=True)


def refuse(msg):
    print(msg if msg.startswith("REFUSED") else f"REFUSED: {msg}", file=sys.stderr, flush=True)
    return 2


def _host():
    import re
    return re.sub(r"[^A-Za-z0-9_.-]", "_", socket.gethostname() or "host")[:40]


# ---------------------------------------------------------------- stage E1
def _dedup(df):
    return df.drop_duplicates(subset=["run_id", "symbol", "day", "signal_idx", "entry_time"])


def _rows(df, src):
    out = []
    for r in df.to_dict("records"):
        r["_src"] = src
        r["day"] = str(r["day"])[:10]
        out.append(r)
    return out


def _read(path, run_id):
    df = pd.read_csv(path, compression="gzip", low_memory=False)
    return df[df["run_id"].astype(str) == run_id]


def _newest(pattern):
    files = sorted(f for f in glob.glob(pattern) if "@" not in Path(f).name)
    return files[-1] if files else None


def _rel(p):
    try:
        return str(Path(p).resolve().relative_to(HERE))
    except ValueError:
        return str(p)


def _src(path, run_id, rows, src):
    return {"file": _rel(path), "sha256": periods.sha256_file(path), "run_id": run_id, "rows_used": rows, "src": src}


def factory_run_ids():
    """factory_{hist,dev}_v1's otm_c_1100 run ids, from the committed specs (must be run 012)."""
    out = {}
    for src, name in (("HIST", "factory_hist_v1"), ("DEV", "factory_dev_v1")):
        runs = engine.expand(json.loads((HERE / "sprint" / "specs" / f"{name}.json").read_text()))
        ids = [r["run_id"] for r in runs if r["block"] == "otm_c_1100"]
        if ids != [exam.FACTORY_RUN[src]]:
            raise exam.ExamRefused(f"REFUSED: {name}'s otm_c_1100 run is {ids}, not {exam.FACTORY_RUN[src]}")
        out[src] = ids[0]
    return out


def load_fin_l(hist_v1_patterns, factory_hist):
    """(rows, source record): every trades_hist_v1_* file's hist_v1-005 rows (deduplicated as tools/sprint_regime.load), else
    the factory HIST file's factory_hist_v1-012 rows."""
    files = sorted({f for p in hist_v1_patterns for f in glob.glob(p) if "@" not in Path(f).name})
    parts = [(f, _read(f, exam.HIST_V1_RUN)) for f in files]
    parts = [(f, d) for f, d in parts if len(d)]
    if parts:
        df = _dedup(pd.concat([d for _, d in parts], ignore_index=True))
        rows = _rows(df, "HIST")
        return rows, {"which": f"{exam.HIST_V1_RUN} (present: run 4's HIST trade file)", "run_id": exam.HIST_V1_RUN,
                      "files": [_src(f, exam.HIST_V1_RUN, len(d), "HIST") for f, d in parts], "rows": len(rows)}
    if not factory_hist or not Path(factory_hist).exists():
        raise exam.ExamRefused("REFUSED: no hist_v1-005 trades and no factory HIST trade file: FIN-L can't be fit")
    df = _dedup(_read(factory_hist, exam.FACTORY_RUN["HIST"]))
    if not len(df):
        raise exam.ExamRefused(f"REFUSED: {factory_hist} has no {exam.FACTORY_RUN['HIST']} trades: FIN-L can't be fit")
    rows = _rows(df, "HIST")
    return rows, {"which": f"{exam.FACTORY_RUN['HIST']} (hist_v1-005's trade file not found; run 7, the same run configuration)",
                  "run_id": exam.FACTORY_RUN["HIST"], "files": [_src(factory_hist, exam.FACTORY_RUN["HIST"], len(rows), "HIST")],
                  "rows": len(rows)}


def locked_read_happened(out_dir, exam_base):
    starts = [e for e in exam.read_log(Path(out_dir) / "exam_log.jsonl") if e.get("event") == "start"]
    if starts:
        return f"the exam log already records a locked read ({starts[0].get('period')} on {starts[0].get('at')})"
    eb = Path(exam_base)
    if eb.exists() and any(p.is_file() for p in eb.rglob("*")):
        return f"{eb} already holds locked-period data"
    return None


def cross_check(fl_rows, fl_src, finh_src_rows):
    """Information: FIN-L's source (hist_v1-005) against run 7's factory_hist_v1-012 (the same run configuration), by trade
    key (symbol, day, signal bar, contract) and P/L. None when FIN-L already reads the factory file."""
    if fl_src["run_id"] != exam.HIST_V1_RUN:
        return None
    key = lambda r: (r["symbol"], str(r["day"])[:10], int(float(r["signal_idx"])), str(r.get("contract")))
    a = {key(r): round(float(r["pnl"]), 4) for r in fl_rows}
    b = {key(r): round(float(r["pnl"]), 4) for r in finh_src_rows}
    common = set(a) & set(b)
    return {"hist_v1_005_trades": len(a), "factory_hist_v1_012_trades": len(b), "same_trades": len(common),
            "same_pnl": sum(1 for k in common if a[k] == b[k])}


def cmd_fit(x):
    t0 = time.time()
    why = locked_read_happened(x.out, x.exam_data)
    if why:
        return refuse(f"REFUSED: stage E1 fits the models BEFORE any L1/L2 pull (Amendment 11), but {why}.")
    mp = Path(x.models)
    if exam.is_tracked(mp):
        return refuse(f"REFUSED: {mp} is already committed (git tracks it): the models are fit once, and the committed file is "
                      "the frozen one.")
    try:
        ids = factory_run_ids()
        fh = x.factory_hist or _newest(str(Path(x.out) / "trades_factory_hist_v1_*.csv.gz"))
        fd = x.factory_dev or _newest(str(Path(x.out) / "trades_factory_dev_v1_*.csv.gz"))
        pats = x.hist_v1 or [str(Path(x.out) / "trades_hist_v1_*.csv.gz")]
        fl_rows, fl_src = load_fin_l(pats, fh)
        for k, f in (("factory HIST", fh), ("factory DEV", fd)):
            if not f or not Path(f).exists():
                return refuse(f"REFUSED: no {k} trade file (run 7's trades_factory_*_v1_*.csv.gz): FIN-HS can't be fit")
        hs, srcs, allf = {}, [], {}
        for src, f in (("HIST", fh), ("DEV", fd)):
            df = _dedup(_read(f, ids[src]))
            allf[src] = _rows(df, src)
            hs[src] = [r for r in allf[src] if exam.rvol_ok(r)]
            srcs.append(_src(f, ids[src], len(hs[src]), src))
        allrows = fl_rows + allf["HIST"] + allf["DEV"]
        why = exam.check_training_rows(allrows)
        if why:
            return refuse(why)
        cc = cross_check(fl_rows, fl_src, allf["HIST"])
        vd = data.read_daily("VIXY", x.data)
        n_old = sum(1 for r in hs["HIST"] + hs["DEV"] if features.missing(r, features.NEW7))
        n_fill = features.restamp(hs["HIST"] + hs["DEV"], {}, {"VIXY_D": vd}, x.data) if n_old else 0
        vfile = Path(x.data or DATA) / "daily" / "VIXY.csv.gz"
        try:
            rel_models = mp.resolve().relative_to(HERE).as_posix()
        except ValueError:
            rel_models = None
        tree = exam.dirty_reason(HERE, ignore=[rel_models] if rel_models else ())
        extra = {"fit_commit": exam.head_commit(HERE), "fit_tree": "clean" if tree is None else tree, "fit_engine": exam.VERSION,
                 "fin_l_vs_factory": cc,
                 "restamp": {"rows_missing_round8_features": n_old, "rows_filled": n_fill,
                             "vixy_daily": {"file": _rel(vfile), "sha256": periods.sha256_file(vfile) if vfile.exists() else None}}}
        models = exam.fit_models(fl_rows, fl_src, hs["HIST"], hs["DEV"], srcs, extra)
    except exam.ExamRefused as e:
        return refuse(str(e))
    why = exam.check_models(models)
    if why:
        return refuse(why)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(exam.models_text(models))
    sha = periods.sha256_file(mp)
    fl = models["fin_l"]
    say(f"sprint_exam fit (stage E1, no locked data) at commit {extra['fit_commit']}, engine {exam.VERSION}")
    if tree is not None:
        say(f"WARNING: {tree} (recorded in the models file)")
    say(f"FIN-L source: {fl_src['which']}")
    for s in fl_src["files"]:
        say(f"  {s['file']}  sha256 {s['sha256']}  {s['run_id']}: {s['rows_used']} trades")
    say(f"  FIN-L logit: {fl['rows']} trades {fl['first_day']}..{fl['last_day']}, {fl['wins']} winners, {len(fl['used_features'])} of "
        f"{len(fl['features'])} features used, take when P(win) >= {fl['threshold']}")
    if cc:
        say(f"  check: hist_v1-005 {cc['hist_v1_005_trades']} trades vs factory_hist_v1-012 {cc['factory_hist_v1_012_trades']} (same run "
            f"configuration): {cc['same_trades']} same trades, {cc['same_pnl']} with the same P/L (information)")
    say("FIN-HS sources (run 7, otm_c_1100 with f_rvol >= 1.06):")
    for s in srcs:
        say(f"  {s['file']}  sha256 {s['sha256']}  {s['run_id']}: {s['rows_used']} FIN-H trades ({s['src']})")
    if n_old:
        say(f"  {n_old} FIN-H trades lacked the seven round-8 features; {n_fill} re-stamped from cached bars (P/L unchanged); VIXY daily "
            f"{extra['restamp']['vixy_daily']['file']} sha256 {extra['restamp']['vixy_daily']['sha256']}")
    for k in ("L2", "L1"):
        m = models["fin_hs"][k]
        say(f"  FIN-HS {k}: {m['rows']} trades {m['first_day']}..{m['last_day']} ({'+'.join(m['train_sources'])}, through {m['train_through']}), "
            f"{len(m['used_features'])} features used, cuts P(win) {m['cuts']['lower']:.6f} / {m['cuts']['upper']:.6f}, training sizes "
            f"skip {m['train_sizes']['skip']} / 1 {m['train_sizes']['one']} / 2 {m['train_sizes']['two']}")
    say(f"models file: {_rel(mp)}")
    say(f"models sha256: {sha}")
    say(f"(for Claude: after `freeze` with this models file, the exam spec's sha256 will be "
        f"{exam.sha256_bytes(exam.spec_text(exam.canonical_spec(sha)).encode())})")
    say(f"done in {time.time() - t0:.0f}s [labels: HIST option P/L MODELED (BS, calibrated IV); DEV REAL Alpaca option prices]")
    return 0


# ---------------------------------------------------------------- freeze (Claude's side)
def cmd_freeze(x):
    sp, mp = Path(x.spec), Path(x.models)
    if not mp.exists():
        return refuse(f"REFUSED: {mp} does not exist (run stage E1 and commit its models file first)")
    try:
        models = json.loads(mp.read_text())
    except ValueError as e:
        return refuse(f"REFUSED: {mp} is not JSON ({e})")
    why = exam.check_models(models)
    if why:
        return refuse(why)
    spec = json.loads(sp.read_text())
    why = exam.check_spec(spec)
    if why:
        return refuse(why)
    msha = periods.sha256_file(mp)
    why = periods.frozen_check(mp, msha)
    if why:
        return refuse(f"REFUSED: commit the models file first ({why})")
    sp.write_text(exam.spec_text(exam.canonical_spec(msha)))
    say(f"models sha256: {msha}")
    say(f"exam spec {sp} sha256: {periods.sha256_file(sp)}  (commit it; this is the value --frozen takes)")
    return 0


# ---------------------------------------------------------------- stage E2: the guarded pull
def pull_daily_locked(sym, a, b, period, feed="sip"):
    """Split-adjusted daily bars for [a, b] in ONE request into PA.ROOT/daily/<SYM>.csv.gz; [a, b] may touch only `period`
    (the caller has passed periods.guard for it)."""
    hit = periods.overlaps(a, b)
    if hit != [period]:
        raise exam.ExamRefused(f"REFUSED: the daily range {a}..{b} touches {hit or 'no locked period'}, not exactly {period}")
    rows = []
    for page in PA.get(f"/v2/stocks/{sym}/bars", {"timeframe": "1Day", "start": SPULL._utc(a), "end": SPULL._utc(b + timedelta(days=1)),
                                                  "limit": 10000, "adjustment": "split", "feed": feed, "sort": "asc"}):
        rows += page.get("bars") or []
    df = PA._frame(rows)
    if len(df):
        df = df.drop_duplicates("ts").sort_values("ts")
    PA._write_gz(PA.ROOT / "daily" / f"{sym}.csv.gz", df)
    return {"rows": int(len(df)), "range": f"{a}..{b}", "adjustment": "split"}


def pull_period(spec, name, exam_root, guard, today=None, log=say):
    """The guarded pull of one locked period into its own cache root. guard = (locked, frozen, spec_path, repo)."""
    p = spec["periods"][name]
    a, b = date.fromisoformat(p["from"]), date.fromisoformat(p["to"])
    d0 = date.fromisoformat(p["vixy_daily_from"])
    periods.guard(min(d0, date.fromisoformat(p["warm_from"])), b, *guard)
    pu = spec["pull"]
    old = PA.ROOT
    PA.ROOT = Path(exam_root)
    out, gaps = {}, {}
    try:
        for s in pu["stock_1m"]:
            out[f"{s} 1-minute bars"] = SPULL.pull_stock(s, a, b, pu["feed"], today=today, log=log, adjustment=p["stock_adjustment"])
            log(f"  {s} 1-minute bars {a}..{b} ({p['stock_adjustment']}): {out[f'{s} 1-minute bars']}")
        for s in pu["options_0dte"]:
            r = SPULL.pull_options(s, a, b, pu["band"], trades=bool(pu["option_trades"]), today=today, log=log)
            out[f"{s} 0DTE option bars"] = {k: (v if not isinstance(v, list) else len(v)) for k, v in r.items()}
            log(f"  {s} 0DTE option bars: {out[f'{s} 0DTE option bars']}")
        out["VIXY daily"] = pull_daily_locked("VIXY", d0, b, name, pu["feed"])
        log(f"  VIXY daily closes: {out['VIXY daily']}")
        for s in pu["stock_1m"]:
            g = SPULL.gap_report(s, a, b, None, options=s in pu["options_0dte"])
            gaps[s] = {"sessions": g["sessions"], "no_bars": g["no_bars"], "short_sessions": [z["day"] for z in g["short_sessions"]],
                       "early_closes": [z["day"] for z in g["early_closes"]], "no_option_bars": g["no_option_bars"] if s in pu["options_0dte"] else None,
                       "contracts_per_session": g["contracts_per_session"]}
    finally:
        PA.ROOT = old
    return out, gaps


# ---------------------------------------------------------------- stage E2: the exam
def _other_result(out_dir, other, spec_sha):
    best = None
    for f in sorted(Path(out_dir).glob(f"exam_{other}_*.json")):
        try:
            j = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        m = j.get("meta") or {}
        if m.get("spec_sha") == spec_sha and m.get("finished") and (best is None or m["finished"] > best[0]["meta"]["finished"]):
            best = (j, f)
    return (best[0]["result"], str(best[1])) if best else (None, None)


def run_exam(spec_path, locked, frozen, main_root=None, exam_base=None, out_dir=None, repo=None, today=None, log=say, limit_days=None):
    """Stage E2 for one period. Raises exam.ExamRefused / periods.LockedPeriod before reading any locked data when a check fails."""
    t0 = time.time()
    names = [s.strip().upper() for s in str(locked or "").split(",") if s.strip()]
    if len(names) != 1 or names[0] not in ("L1", "L2"):
        raise exam.ExamRefused("REFUSED: --locked takes exactly one period, L2 or L1 (each runs once)")
    name = names[0]
    if not frozen:
        raise exam.ExamRefused("REFUSED: --frozen <sha256 of sprint/specs/final_v2_exam.json as committed> is required")
    frozen = frozen.strip().lower()
    repo = Path(repo or exam.REPO).resolve()
    spec_path = Path(spec_path or repo / exam.SPEC_REL).resolve()
    main_root = Path(main_root or DATA)
    exam_root = Path(exam_base or EXAM_DATA) / name
    out_dir = Path(out_dir or OUT)
    try:
        spec_path.relative_to(repo)
    except ValueError:
        raise exam.ExamRefused(f"REFUSED: the exam spec {spec_path} is not inside the code repository {repo}")
    if not spec_path.exists():
        raise exam.ExamRefused(f"REFUSED: {spec_path} does not exist")
    try:
        spec = json.loads(spec_path.read_text())
    except ValueError as e:
        raise exam.ExamRefused(f"REFUSED: the exam spec is not JSON ({e})")
    why = exam.check_spec(spec)
    if why:
        raise exam.ExamRefused(f"REFUSED: {why}")
    p = spec["periods"][name]
    a, b = date.fromisoformat(p["from"]), date.fromisoformat(p["to"])
    warm, d0 = date.fromisoformat(p["warm_from"]), date.fromisoformat(p["vixy_daily_from"])
    guard = (name, frozen, spec_path, repo)
    periods.guard(min(warm, d0), b, *guard)                 # the spec is committed, unchanged and hashes to --frozen
    why = exam.dirty_reason(repo)
    if why:
        raise exam.ExamRefused(f"REFUSED: {why}")
    commit = exam.head_commit(repo)
    msha = (spec.get("models") or {}).get("sha256")
    if not exam.models_sha_ready(msha):
        raise exam.ExamRefused("REFUSED: the exam spec has no models sha256 yet (stage E1, commit the models file, then freeze)")
    mpath = repo / spec["models"]["path"]
    why = periods.frozen_check(mpath, msha, repo)
    if why:
        raise exam.ExamRefused(f"REFUSED: the models file is not the frozen one: {why}")
    models = json.loads(mpath.read_text())
    why = exam.check_models(models)
    if why:
        raise exam.ExamRefused(f"REFUSED: {why}")
    log_path = out_dir / "exam_log.jsonl"
    prior = exam.read_log(log_path)
    kind, void = exam.log_policy(prior, name, frozen, commit, repo)
    if kind == "first" and exam_root.exists() and any(q.is_file() for q in exam_root.rglob("*")):
        raise exam.ExamRefused(f"REFUSED: {exam_root} already holds {name} data but {log_path} records no {name} run (was the exam "
                               "log deleted or moved?). One shot: nothing was read; tell Nick.")
    miss = exam.missing_warmup(main_root, warm, a, spec["symbols"])
    if miss:
        raise exam.ExamRefused(f"REFUSED: warm-up month files missing from {main_root}: {miss[:6]} (they come from "
                               f"{p['warm_source']}; nothing locked was read)")
    if not (os.environ.get("ALPACA_KEY") and os.environ.get("ALPACA_SECRET")):
        raise exam.ExamRefused("REFUSED: ALPACA_KEY / ALPACA_SECRET are not set (the desk's paper key, market data only)")
    n_same = sum(1 for e in prior if e.get("event") == "start" and e.get("period") == name)
    suffix = f"_rerun{n_same}" if kind == "rerun" else ""
    today = today or date.today().isoformat()
    host = _host()
    started = exam.stamp()
    exam.append_log(log_path, {"event": "start", "period": name, "spec_sha": frozen, "models_sha": msha, "commit": commit, "kind": kind,
                               "void": void, "at": started, "host": host, "engine": exam.VERSION})
    log(f"sprint_exam run: {name} {a}..{b} ({'FIRST READ' if kind == 'first' else 're-run, same frozen spec and commit'}); commit "
        f"{commit}; exam spec sha256 {frozen}; models sha256 {msha}; engine {exam.VERSION}" + (f"; VOID: {void}" if void else ""))
    pulled, gaps = pull_period(spec, name, exam_root, guard, today=date.fromisoformat(today), log=log)
    syms = spec["symbols"]
    series = {s: exam.load_period_series(s, warm, a, b, main_root, exam_root) for s in syms}
    vd = exam.read_exam_daily(exam_root / "daily" / "VIXY.csv.gz", d0, b, name)
    aux = {"VIXY_D": vd}
    warnings = []
    if vd is None or not len(vd):
        warnings.append("no VIXY daily closes: f_vixy_pctl / f_vixy_chg1 / f_vixy_z20 are empty (median-filled by the models)")
    runs = exam.engine_runs(spec)
    rl = [runs["reference"], runs["fin_h"]]
    log(f"engine: {len(rl)} runs at the 2% half-spread, then at 5% (information)")
    res, sessions = exam.engine_pass(rl, series, a, b, exam_root, SP.SpreadModel(), aux, progress=log, limit_days=limit_days)
    res5, _ = exam.engine_pass(rl, series, a, b, exam_root, SP.SpreadModel(pct=exam.INFO_SPREAD_PCT), aux, limit_days=limit_days)
    rid = {k: runs[k]["run_id"] for k in ("reference", "fin_h")}
    if limit_days:
        b_eff = max(date.fromisoformat(max(v)) for v in sessions.values() if v) if any(sessions.values()) else b
        nb = exam.nbvol_trades({s: series[s] for s in syms}, a, b_eff, aux, name)
    else:
        nb = exam.nbvol_trades({s: series[s] for s in syms}, a, b, aux, name)
    out = exam.evaluate(name, res[rid["reference"]]["rows"], res[rid["fin_h"]]["rows"], models, nb, a, b,
                        res5[rid["reference"]]["rows"], res5[rid["fin_h"]]["rows"], void)
    if not out["fin_h_check"]["match"]:
        warnings.append(f"FIN-H's engine run differs from the reference's trades with f_rvol >= 1.06: {out['fin_h_check']}")
    other = "L1" if name == "L2" else "L2"
    other_res, other_file = _other_result(out_dir, other, frozen)
    comb = exam.combined({name: out, other: other_res})
    n_exp = len(exam.book.sessions_between(a, b))
    cov = {}
    for s in spec["pull"]["stock_1m"]:
        g = gaps.get(s, {})
        txt = f"{g.get('sessions', 0)} of {n_exp} NYSE sessions with 1-minute bars"
        if g.get("no_option_bars") is not None:
            txt += f", {g.get('sessions', 0) - len(g['no_option_bars'])} with 0DTE option bars"
            if g["no_option_bars"]:
                txt += f" (none on {', '.join(g['no_option_bars'][:8])}{' ...' if len(g['no_option_bars']) > 8 else ''})"
        if g.get("early_closes"):
            txt += f", early closes {', '.join(g['early_closes'])}"
        if g.get("short_sessions"):
            txt += f", short sessions {', '.join(g['short_sessions'][:5])}"
        cov[s] = txt
        if g.get("sessions", 0) == 0:
            warnings.append(f"{s}: no 1-minute bars in {name}")
    cov["VIXY daily"] = f"{0 if vd is None else len(vd)} closes {d0}..{b} (split-adjusted)"
    finished = exam.stamp()
    out_dir.mkdir(parents=True, exist_ok=True)
    tp = out_dir / f"trades_exam_{name}_{today}{suffix}.csv.gz"
    sp_ = out_dir / f"trades_exam_{name}_shares_{today}{suffix}.csv.gz"
    exam.write_option_trades(tp, [("reference", "MODELED-SPREAD 2%", res[rid["reference"]]["rows"], models, name),
                                  ("fin_h", "MODELED-SPREAD 2%", res[rid["fin_h"]]["rows"], models, name),
                                  ("reference", "MODELED-SPREAD 5% (information)", res5[rid["reference"]]["rows"], None, name),
                                  ("fin_h", "MODELED-SPREAD 5% (information)", res5[rid["fin_h"]]["rows"], None, name)])
    shares.write_trades(sp_, {"noise_sh_vol": nb})
    meta = {"period": name, "from": a.isoformat(), "to": b.isoformat(), "kind": kind, "void": void, "commit": commit, "spec_path": exam.SPEC_REL,
            "spec_sha": frozen, "models_path": spec["models"]["path"], "models_sha": msha, "engine": exam.VERSION, "host": host,
            "started": started, "finished": finished, "minutes": round((time.time() - t0) / 60, 1), "coverage": cov,
            "warm": f"1-minute bars {warm}..{a - timedelta(days=1)} from the main cache ({p['warm_source']}, {p['stock_adjustment']}); VIXY daily "
                    f"from {d0}", "pulled": pulled, "gaps": gaps, "sessions": {k: len(v) for k, v in sessions.items()},
            "skips": {k: res[runs[k]["run_id"]]["skips"].most_common() for k in ("reference", "fin_h")},
            "signals": {k: res[runs[k]["run_id"]]["signals"] for k in ("reference", "fin_h")}, "warnings": warnings,
            "combined": comb, "other_file": other_file, "trade_files": f"`{tp}` (options, 2% and 5%), `{sp_}` (NB-VOL shares)",
            "log": str(log_path), "limit_days": limit_days}
    mp = out_dir / f"exam_{name}_{today}{suffix}.md"
    jp = out_dir / f"exam_{name}_{today}{suffix}.json"
    mp.write_text(exam.render(out, meta))
    jp.write_text(json.dumps(exam.clean({"meta": meta, "result": out}), indent=1))
    exam.append_log(log_path, {"event": "done", "period": name, "spec_sha": frozen, "commit": commit, "kind": kind, "void": void,
                               "at": finished, "report": str(mp), "json": str(jp)})
    for line in exam.summary_lines(out, comb):
        log(line)
    for w in warnings:
        log(f"WARNING: {w}")
    log(f"exam {name} done in {time.time() - t0:.0f}s\nreport: {mp}\njson:   {jp}\ntrades: {tp}\nshares: {sp_}")
    return {"result": out, "meta": meta, "md": mp, "json": jp}


def cmd_run(x):
    try:
        run_exam(x.spec, x.locked, x.frozen, x.data, x.exam_data, x.out, today=x.today, limit_days=x.limit_days)
    except (exam.ExamRefused, periods.LockedPeriod) as e:
        return refuse(str(e))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="SPRINT_PLAN Amendment 11: the final locked-period exam (research only, never trades)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit", help="stage E1: fit FIN-L and FIN-HS's models (no locked data)")
    f.add_argument("--hist-v1", nargs="+", default=None, help="run 4's HIST trade files (default data/sprint/trades_hist_v1_*.csv.gz)")
    f.add_argument("--factory-hist", default=None, help="run 7's HIST trade file (default: newest trades_factory_hist_v1_*.csv.gz)")
    f.add_argument("--factory-dev", default=None, help="run 7's DEV trade file (default: newest trades_factory_dev_v1_*.csv.gz)")
    f.add_argument("--data", default=None, help="main cache root (default data/alpaca)")
    f.add_argument("--exam-data", default=str(EXAM_DATA), help="the exam's locked cache (must not exist yet)")
    f.add_argument("--out", default=str(OUT))
    f.add_argument("--models", default=str(HERE / exam.MODELS_REL))
    z = sub.add_parser("freeze", help="write the models sha256 into the exam spec and print the spec's sha256 (Claude's side)")
    z.add_argument("--spec", default=str(HERE / exam.SPEC_REL))
    z.add_argument("--models", default=str(HERE / exam.MODELS_REL))
    r = sub.add_parser("run", help="stage E2: the one-shot exam of one locked period")
    r.add_argument("--locked", required=False, help="L2 or L1")
    r.add_argument("--frozen", required=False, help="sha256 of sprint/specs/final_v2_exam.json as committed")
    r.add_argument("--spec", default=None, help=argparse.SUPPRESS)
    r.add_argument("--data", default=None, help=argparse.SUPPRESS)
    r.add_argument("--exam-data", default=None, help=argparse.SUPPRESS)
    r.add_argument("--out", default=None, help=argparse.SUPPRESS)
    r.add_argument("--today", default=None, help=argparse.SUPPRESS)
    r.add_argument("--limit-days", type=int, default=None, help=argparse.SUPPRESS)
    x = ap.parse_args(argv)
    return {"fit": cmd_fit, "freeze": cmd_freeze, "run": cmd_run}[x.cmd](x)


if __name__ == "__main__":
    sys.exit(main())
