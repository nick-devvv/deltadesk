#!/usr/bin/env python3
"""tools/sprint_r10_credit.py - SPRINT_PLAN Addendum 15.4 (C1, C1-ctl, C1-ic, C2, C2-ctl) and Amendment 16 (C3, C3-ctl, C4): round
10's 0DTE credit spreads. PAPER RESEARCH ONLY (option selling; Nick's account can't trade spreads). Research only: reads cached
bars, never trades, no network.

  python3 tools/sprint_r10_credit.py                       # DEV REAL (SPY decides, QQQ information) + HIST MODELED (information)
  python3 tools/sprint_r10_credit.py --windows DEV         # DEV only
  python3 tools/sprint_r10_credit.py --needed 2025-04-07   # the contracts the eight structures need that day (SPY), vs on file

Reads (data/alpaca unless --data): stocks/SPY and stocks/QQQ (1-minute bars 04:00-20:00: the premarket gives C1's 08:30 price;
DEV, and HIST from its 2015-11-01 warm-up), options/<SYM>/<day>/bars.csv.gz (DEV 0DTE bars from runs 1-3) and options_r10/ (the
round 10 pull's extra strikes, when present; --option-subs), the logged chains (default data/chains: MEASURED-SPREAD where a
cell has data), and data/sprint/calib_modeled.json for HIST MODELED (without it HIST is skipped with a warning).
Writes data/sprint/r10credit_<date>.md and .json and data/sprint/trades_r10credit_<date>.csv.gz (every structure: rule, symbol,
day, window, prices, legs, credit, margin, P/L at 1x and 2x the half-spread, exit reason); prints the summary. Labels: BACKTEST,
PAPER RESEARCH ONLY, REAL (DEV) / MODELED (HIST), MEASURED-/MODELED-SPREAD, VIX PROXY. Refuses anything inside L1/L2.
The trials (8 here; round 10's tally 7,767) are recorded as round 9 records them: in the report's and the JSON's trial block,
with the deflated Sharpe's N = the run logs' rows + 7,767.
"""
import argparse
import csv
import glob
import gzip
import json
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from sprint import data, factory, periods, runner  # noqa: E402
from sprint import modeled as MD  # noqa: E402
from sprint import r10credit as RC  # noqa: E402

WINDOWS = ("DEV", "HIST")


def count_trials(out, patterns=None):
    """Rows in docs/research/sprint_runs.csv plus the run logs (default data/sprint/runs_*.csv), as round 9 counts them."""
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


def write_rows(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(dict.fromkeys(k for r in rows for k in r.keys())) if rows else ["day"]
    with gzip.open(path, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return str(path)


# ---------------------------------------------------------------- INTEGRATOR HOOK: the compounding view
def compounding_view(ev, trades, sessions=None):
    """Amendment 16's compounding view (information, not trials): a $3,000 account over 2,000 bootstrap paths of each passing
    rule's holdout trades (resampled by session), fixed-fractional risk 1%, 2% and 5% a trade; median and 5th-percentile ending
    balance, worst drawdown, chance of halving.
    Wired to sprint/compound.py (round10/noise) at integration: each passing SPY DEV rule's trades (RC.compounding_inputs), risk
    unit = max_loss, resampled over every DEV session."""
    inputs = RC.compounding_inputs(ev.get("DEV") or {}, trades)
    out = {"inputs": {k: len(v) for k, v in inputs.items()}, "result": None}
    if not inputs:
        out["note"] = "no credit-spread rule passed on SPY DEV REAL, so there is nothing to compound (Amendment 16: passing rules only)."
        return out
    try:
        from sprint import compound  # noqa: F401  (another builder's module)
    except ImportError:
        out["note"] = (f"NOT WIRED: sprint/compound.py is not in this checkout (another round 10 builder writes it); inputs ready for "
                       f"{', '.join(inputs)}.")
        return out
    # Wired by the integrator: each structure's risk unit is its max_loss (the most one structure can lose); sessions = every
    # DEV session, so no-trade days count as r = 0.
    sess = [str(d)[:10] for d in (sessions or [])]
    out["result"] = {}
    for rule, rows in inputs.items():
        rr = [{"day": r["day"], "pnl": r["pnl"], "risk": r["max_loss"]} for r in rows
              if r.get("pnl") is not None and (r.get("max_loss") or 0) > 0]
        if not rr:
            out["result"][rule] = {"note": "no rows with a positive max_loss"}
            continue
        days = set(str(r["day"])[:10] for r in rr)
        use = sess if sess and days <= set(sess) else None
        out["result"][rule] = compound.simulate(rr, sessions=use, label=f"{rule} SPY DEV REAL (paper research: option selling)")
    out["note"] = "compounding view: information, not trials (Amendment 16)."
    return out


# ---------------------------------------------------------------- --needed
def needed(day, sym, root, subs, log):
    periods.guard(day, day)
    df = data.read_stock(sym, day, day, root)
    if df is None or not len(df):
        log(f"{sym} {day}: no stock bars in the cache")
        return 1
    tapes = RC.read_tapes(sym, day, root, subs)
    need = RC.needed_option_contracts(day, df, sym, tapes=tapes)
    miss = [s for s in need if s not in tapes]
    ex = RC.existing_pull_strikes(df, day)
    print(json.dumps({"day": day.isoformat(), "symbol": sym, "reach": RC.needed_strikes(day, df, tapes), "needed": len(need),
                      "on_file": len(need) - len(miss), "runs_1_3_asked_strikes": ex, "missing": miss}, indent=1))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="SPRINT_PLAN 15.4 + Amendment 16 C3/C4: round 10's 0DTE credit spreads (paper research only)")
    ap.add_argument("--data", default=None, help="cache root (default data/alpaca)")
    ap.add_argument("--out", default=str(HERE / "data" / "sprint"))
    ap.add_argument("--today", default=None)
    ap.add_argument("--windows", default=",".join(WINDOWS))
    ap.add_argument("--symbols", default=",".join(RC.SYMBOLS))
    ap.add_argument("--chains-dir", default=str(HERE / "data" / "chains"), help="logged chains for MEASURED-SPREAD")
    ap.add_argument("--calib", default=None, help="HIST MODELED calibration (default <out>/calib_modeled.json)")
    ap.add_argument("--option-subs", default=",".join(RC.OPTION_SUBS), help="cache subfolders with 0DTE bars (same layout as options/)")
    ap.add_argument("--runs-csv", nargs="+", default=None)
    ap.add_argument("--limit-days", type=int, default=None, help="first N sessions per symbol and window (smoke test only)")
    ap.add_argument("--needed", default=None, help="a day: print the contracts the structures need (SPY unless --symbols) and exit")
    x = ap.parse_args(argv)
    t_all = time.time()
    root = Path(x.data) if x.data else data.ROOT
    out = Path(x.out)
    log = lambda s: print(s, flush=True)
    subs = tuple(s.strip() for s in x.option_subs.split(",") if s.strip())
    syms = [s.strip().upper() for s in x.symbols.split(",") if s.strip()]
    if x.needed:
        return needed(date.fromisoformat(x.needed), syms[0], root, subs, log)
    out.mkdir(parents=True, exist_ok=True)
    today = x.today or date.today().isoformat()
    wins = [w.strip().upper() for w in x.windows.split(",") if w.strip()]
    bad = [w for w in wins if w not in WINDOWS]
    if bad:
        ap.error(f"unknown window(s) {bad}")
    syms = sorted(syms, key=lambda s: (s != RC.DECIDES, s))          # SPY first: its 20-day vol is QQQ's VIX proxy
    cost = RC.credit_spread(x.chains_dir, syms)
    warnings, files, trades, skips, coverage = [], {}, [], {}, {}
    log(f"sprint_r10_credit: windows {', '.join(wins)}; symbols {', '.join(syms)}; cache {root}; every number is a BACKTEST; paper "
        f"research only; L1/L2 never read; {cost.describe()}")
    for w in wins:
        a, b, lab = RC.WINDOWS[w]
        mode = "real" if lab == "REAL" else "modeled"
        la = periods.WARMUP["HIST"] if w == "HIST" else periods.DEV[0]
        calib = None
        if mode == "modeled":
            cp = Path(x.calib) if x.calib else out / "calib_modeled.json"
            try:
                calib = MD.load_calib(cp)
                for s in ("C", "P"):
                    MD.multiplier(calib, RC.CALIB_RULE, s)
            except (FileNotFoundError, ValueError) as e:
                warnings.append(f"HIST MODELED not run: {e}")
                continue
            files["calib"] = str(cp)
        spy = None
        for sym in syms:
            t0 = time.time()
            ser, pm = RC.load(sym, la, b, root)
            n_days = sum(1 for d in ser.days if a <= d.isoformat() <= b)
            if not n_days:
                warnings.append(f"{w}: no {sym} stock bars in the cache ({root}/stocks/{sym}): not run.")
                continue
            if sym == "SPY":
                spy = ser
            elif spy is None:
                warnings.append(f"{w} {sym}: no SPY bars, so C2's VIX proxy (SPY's 20-day realized vol) uses {sym}'s own closes.")
            if mode == "real" and not RC.option_days(sym, root, subs):
                warnings.append(f"{w}: no {sym} 0DTE option files ({', '.join(subs)}): every {sym} structure is skipped.")
            cov = {} if mode == "real" else None
            tr, sk = RC.run(ser, pm, a, b, mode, root=root, calib=calib, cost=cost, spy=spy, progress=log, limit_days=x.limit_days,
                            subs=subs, coverage=cov, window=w)
            why = RC.check_rows(tr)
            if why:
                raise periods.LockedPeriod(why)
            trades += tr
            skips[f"{w} {sym}"] = {f"{r}|{k}": v for (r, k), v in sorted(sk.items())}
            if cov is not None:
                coverage[f"{w} {sym}"] = RC.coverage_summary(cov)
            log(f"  {w} {sym}: {len(tr)} structures over {n_days} sessions in {time.time() - t0:.0f}s")
    res = {"eval": RC.evaluate_all(trades, [w for w in wins if any(t["window"] == w for t in trades)], syms)}
    res["skips"] = {k: {tuple(kk.split("|", 1)): v for kk, v in d.items()} for k, d in skips.items()}
    res["coverage"] = coverage
    n_prior = count_trials(out, x.runs_csv)
    res["trials"] = RC.trials(n_prior)
    dev_days = RC.book.sessions_between(RC.DEV_A, RC.DEV_B)
    var = {r: [t for t in trades if t["window"] == "DEV" and t["symbol"] == RC.DECIDES and t["rule"] == r] for r in RC.RULES}
    res["dsr"], res["sr_var"], _n = RC.dsr_table(var, n_prior, dev_days)
    res["compounding"] = compounding_view(res["eval"], trades, sessions=dev_days)
    files["trades"] = write_rows(out / f"trades_r10credit_{today}.csv.gz", trades)
    meta = {"today": today, "windows": wins, "symbols": syms, "warnings": warnings, "files": files, "spread": cost.describe(),
            "files_note": "; ".join(f"{k} `{v}`" for k, v in files.items())}
    md = RC.render(res, meta)
    mp, jp = out / f"r10credit_{today}.md", out / f"r10credit_{today}.json"
    mp.write_text(md)
    js = dict(res, skips=skips)
    jp.write_text(json.dumps(factory.clean({"meta": meta, "result": js}), indent=1, default=str))
    print("ROUND 10 CREDIT SPREADS (BACKTEST; PAPER RESEARCH ONLY; DEV REAL decides on SPY; HIST MODELED information)")
    print("\n".join(RC.summary_lines(res)))
    for w in warnings:
        print(f"WARNING: {w}")
    print(f"r10 credit done in {(time.time() - t_all) / 60:.1f} min\nreport: {mp}\njson:   {jp}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except periods.LockedPeriod as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
