#!/usr/bin/env python3
"""tools/sprint_r10_noise.py - SPRINT_PLAN Addendum 15.1 (the noise band's own settings, 162 cells) and Addendum 15.2 (the
loss-autopsy fixes N1, N2, N12), with Amendment 16's compounding view for anything that passes. Research only: reads cached
stock bars, never trades, no network.

  python3 tools/sprint_r10_noise.py                  # SPY/QQQ/IWM (+ DIA/XLK/XLF/SMH when present) 1-minute bars
  python3 tools/sprint_r10_noise.py --parts grid     # the grid alone (the fixes are reported as not run)
  python3 tools/sprint_r10_noise.py --bench          # the runtime estimate from a synthetic benchmark (reads no data)

Reads (data/alpaca unless --data) stocks/<SYM>/<YYYY-MM>.csv.gz for SPY, QQQ, IWM and, when present, DIA, XLK, XLF, SMH:
HIST from its 2015-11-01 warm-up to 2024-01-31 and DEV 2024-08-01..2026-06-30, through sprint/shares.load_series, which
refuses any range touching L1/L2 and drops any bar dated inside them. NB-VOL was read on L2 by the exam: nothing here reads
L1 or L2, and a trade row dated inside either aborts the run (exit code 2).
Runs sprint/r10noise.py: every symbol and segment once through the vectorized engine (all 81 settings + the 3 fixes at once),
an engine self-check against round 8's shares.a1_day and the scalar reference on the same bars, the grid's choice on
2016-2019, the holdouts' 7-item bars, the fixes against the unfixed NB-VOL, the compounding view for a pass, the trial
counts (165 here; round 10 = 7,767; N for the deflated Sharpe = the run logs' rows + 7,767) and the deflated Sharpe.
Writes data/sprint/r10noise_<date>.md and .json, trades_r10noise_grid_<date>.csv.gz (every trade of every distinct cell)
and trades_r10noise_fixes_<date>.csv.gz (NB-VOL unfixed, N1, N2, N12); prints the summary. Re-running with the same inputs
writes byte-identical files (gzip with mtime 0, no timings in the files).
"""
import argparse
import csv
import glob
import gzip
import io
import json
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from sprint import book, data, periods, runner, shares  # noqa: E402
from sprint import r10noise as R  # noqa: E402
from sprint.factory import clean  # noqa: E402

PARTS = ("grid", "fixes")
SAMPLE_CFGS = tuple(range(0, len(R.GRID_CFGS), 10))          # 9 settings spread over the grid, checked against cell_day
SEGMENTS = (("HIST", periods.WARMUP["HIST"], periods.HIST[1]), ("DEV", periods.DEV[0], periods.DEV[1]))
GRID_COLS = ["cell", "symbol", "day", "_src", "side", "decision_idx", "entry_idx", "exit_idx", "shares", "entry_ref", "exit_ref",
             "move", "pnl", "pnl_2x", "bps", "notional", "vol_sd", "exit_reason"]
FIX_COLS = ["variant", "symbol", "day", "_src", "side", "decision_idx", "entry_idx", "exit_idx", "entry_time", "exit_time", "shares",
            "entry_ref", "exit_ref", "entry", "exit", "move", "pnl", "pnl_2x", "bps", "notional", "i_vol_sd", "exit_reason"]


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


def check_arrays(t, what):
    """None, or why the trades are refused: a day inside L1/L2, or a HIST/DEV trade outside its own period."""
    for d in np.unique(t["day"]):
        hit = periods.overlaps(d, d)
        if hit:
            return f"REFUSED: a {what} trade on {d} is inside locked period {', '.join(hit)}"
    for src, (lo, hi) in (("HIST", periods.HIST), ("DEV", periods.DEV)):
        m = t["src"] == src
        if m.any():
            dd = np.unique(t["day"][m])
            if dd[0] < lo.isoformat() or dd[-1] > hi.isoformat():
                return f"REFUSED: a {what} {src} trade lies outside {src} {lo}..{hi}"
    return None


def _gz_bytes(chunks):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
        for c in chunks:
            g.write(c.encode())
    return buf.getvalue()


def write_gz(path, chunks):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(_gz_bytes(chunks))
    tmp.replace(path)
    return str(path)


def grid_frame(cid, t, trail):
    if not len(t["pnl"]):
        return pd.DataFrame(columns=GRID_COLS)
    return pd.DataFrame({"cell": cid, "symbol": t["sym"], "day": t["day"], "_src": t["src"], "side": np.where(t["sign"] > 0, "L", "S"),
                         "decision_idx": t["dec"], "entry_idx": t["k_in"], "exit_idx": t["k_out"], "shares": t["sh"],
                         "entry_ref": np.round(t["ref_in"], 4), "exit_ref": np.round(t["ref_out"], 4), "move": np.round(t["move"], 6),
                         "pnl": t["pnl"], "pnl_2x": t["pnl_2x"], "bps": t["bps"], "notional": np.round(t["notional"], 2),
                         "vol_sd": t["sd"], "exit_reason": [R.why_text(int(w), trail, bool(e)) for w, e in zip(t["why"], t["early"])]},
                        columns=GRID_COLS)


def write_grid(path, cells, used):
    def chunks():
        first = True
        for (c, u), cid in zip(R.GRID, R.CELL_IDS):
            if u == "U7" and used != "U7":
                continue                                            # identical to its U3 twin (Builder's reading R5)
            df = grid_frame(cid, cells[cid], c.trail)
            yield df.to_csv(index=False, header=first, lineterminator="\n")
            first = False
    return write_gz(path, chunks())


def write_rows(path, rows, cols):
    df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
    return write_gz(path, [df.to_csv(index=False, lineterminator="\n")])


# ---------------------------------------------------------------- the run
def load_all(root, log, warnings, with_fixes=True):
    """Every symbol and segment once: load, Prep, the engine on every setting (+ the fixes on U3), the self-check.
    Returns (trades {(sym, src): [per-cfg arrays]}, coverage {sym: {window: sessions}}, self-check totals, cfg lists)."""
    cfgs = list(R.GRID_CFGS)
    fixes = [R.FIXES[k] for k in R.FIXES]
    trades, coverage = {}, {}
    sc = {"base_days": 0, "base_mismatch": 0, "sample_days": 0, "sample_mismatch": 0, "first": None,
          "n_sample_cfgs": len(SAMPLE_CFGS) + (len(fixes) if with_fixes else 0)}
    for sym in R.U7:
        cov = {w: 0 for w in R.WINDOWS}
        msg = []
        for src, a, b in SEGMENTS:
            t0 = time.time()
            ser = shares.load_series(sym, a, b, root)
            if not ser.days:
                msg.append(f"{src} no bars")
                continue
            prep = R.Prep(ser, src)
            cl = cfgs + (fixes if (with_fixes and sym in R.U3) else [])
            tr = R.run_engine(prep, cl)
            sample = list(SAMPLE_CFGS) + (list(range(len(cfgs), len(cl))) if len(cl) > len(cfgs) else [])
            chk = R.self_check(ser, prep, tr, cl, sample=sample, every=25, base=sym in R.U3)
            for k in ("base_days", "base_mismatch", "sample_days", "sample_mismatch"):
                sc[k] += chk[k]
            sc["first"] = sc["first"] or chk["first"]
            trades[(sym, src)] = R.by_cfg(tr, len(cl))
            for w, n in prep.coverage().items():
                cov[w] += n
            msg.append(f"{src} {len(ser.days)} sessions (with warm-up), {len(tr['pnl'])} trades over {len(cl)} settings, "
                       f"{time.time() - t0:.0f}s")
            del ser, prep, tr
        coverage[sym] = cov
        log(f"  {sym}: " + "; ".join(msg))
    if sc["base_mismatch"] or sc["sample_mismatch"]:
        warnings.append(f"ENGINE SELF-CHECK MISMATCH: {sc['base_mismatch']} NB-VOL sessions and {sc['sample_mismatch']} sample "
                        f"sessions differ from the scalar code (first: {sc['first']}). Do not use these results.")
    return trades, coverage, sc, cfgs, fixes


def assemble(trades, cfgs, used):
    """{cell id: arrays in shares.ordered order} for the 162 cells (U7 cells on the three when U7 is not used)."""
    cells = {}
    for (c, u), cid in zip(R.GRID, R.CELL_IDS):
        syms = R.U7 if (u == "U7" and used == "U7") else R.U3
        j = cfgs.index(c)
        cells[cid] = R.ordered(R.concat([trades[(s, src)][j] for s in syms for src, _a, _b in SEGMENTS if (s, src) in trades]))
    return cells


def main(argv=None):
    ap = argparse.ArgumentParser(description="SPRINT_PLAN Addenda 15.1 and 15.2: the noise band grid and fixes (research only)")
    ap.add_argument("--data", default=None, help="cache root (default data/alpaca)")
    ap.add_argument("--out", default=str(HERE / "data" / "sprint"))
    ap.add_argument("--today", default=None)
    ap.add_argument("--parts", default=",".join(PARTS))
    ap.add_argument("--runs-csv", nargs="+", default=None)
    ap.add_argument("--bench", action="store_true", help="print the runtime estimate from a synthetic benchmark and exit")
    ap.add_argument("--bench-days", type=int, default=126)
    x = ap.parse_args(argv)
    if x.bench:
        return bench(x.bench_days)
    t_all = time.time()
    root = Path(x.data) if x.data else data.ROOT
    out = Path(x.out)
    out.mkdir(parents=True, exist_ok=True)
    today = x.today or date.today().isoformat()
    parts = [p.strip().lower() for p in x.parts.split(",") if p.strip()]
    bad = [p for p in parts if p not in PARTS]
    if bad:
        ap.error(f"unknown part(s) {bad}; parts are {PARTS}")
    log = lambda s: print(s, flush=True)
    warnings, files = [], {}
    log(f"sprint_r10_noise: parts {', '.join(parts)}; cache {root}; every number is a BACKTEST on real stock bars; L1/L2 never read")
    trades, coverage, sc, cfgs, fixes = load_all(root, log, warnings, with_fixes="fixes" in parts)
    res = {"universe": None, "grid": None, "fixes": None, "self_check": sc}
    have_u3 = all((s, src) in trades for s in R.U3 for src, _a, _b in SEGMENTS)
    if not any((s, src) in trades for s in R.U3 for src, _a, _b in SEGMENTS):
        warnings.append("No SPY/QQQ/IWM stock bars: nothing run.")
    elif not have_u3:
        warnings.append("Some SPY/QQQ/IWM HIST or DEV bars are missing: " + ", ".join(f"{s} {src}" for s in R.U3 for src, _a, _b in SEGMENTS
                                                                                     if (s, src) not in trades) + ".")
    variants = {}
    if any((s, src) in trades for s in R.U3 for src, _a, _b in SEGMENTS):
        used, missing, cwarn = R.universe_choice(coverage)
        warnings += cwarn
        res["universe"] = {"used": used, "missing": missing, "coverage": coverage, "extra": list(R.EXTRA)}
        log(f"  universe for the U7 cells: {used}" + (f" (missing: {', '.join(f'{s} {w}' for s, w in missing)})" if missing else ""))
        cells = assemble(trades, cfgs, used)
        for cid, t in cells.items():
            why = check_arrays(t, cid)
            if why:
                raise periods.LockedPeriod(why)
        if "grid" in parts:
            t0 = time.time()
            G = R.evaluate_grid(cells, used)
            G.pop("_rows", None)
            res["grid"] = G
            files["grid"] = write_grid(out / f"trades_r10noise_grid_{today}.csv.gz", cells, used)
            log(f"  15.1 grid: chosen {G['chosen'] or 'none'} ({time.time() - t0:.0f}s)")
            variants.update(cells)
        if "fixes" in parts:
            t0 = time.time()
            fix_arr = {fx: R.ordered(R.concat([trades[(s, src)][len(cfgs) + j] for s in R.U3 for src, _a, _b in SEGMENTS
                                                if (s, src) in trades]))
                       for j, fx in enumerate(R.FIXES)}
            for fx, t in fix_arr.items():
                why = check_arrays(t, fx)
                if why:
                    raise periods.LockedPeriod(why)
            rows_by = {"NB-VOL": R.to_rows(cells[R.BASE_ID], "NB-VOL", R.BASE.trail)}
            rows_by.update({fx: R.to_rows(t, fx, R.FIXES[fx].trail) for fx, t in fix_arr.items()})
            res["fixes"] = R.evaluate_fixes(rows_by)
            files["fixes"] = write_rows(out / f"trades_r10noise_fixes_{today}.csv.gz",
                                        [r for k in ("NB-VOL",) + tuple(R.FIXES) for r in rows_by[k]], FIX_COLS)
            log(f"  15.2 fixes: " + ", ".join(f"{fx} {'holds' if o['holds'] else 'does not hold'}" for fx, o in res["fixes"]["fixes"].items())
                + f" ({time.time() - t0:.0f}s)")
            variants.setdefault(R.BASE_ID, cells[R.BASE_ID])
            variants.update(fix_arr)
    n_prior = count_trials(out, x.runs_csv)
    res["trials"] = R.trials(n_prior)
    if variants:
        tab, sr_var, _n, ndist = R.dsr_table(variants, n_prior)
        res["dsr"], res["sr_var"], res["dsr_distinct"] = tab, sr_var, ndist
    meta = {"today": today, "parts": parts, "warnings": warnings, "files": files,
            "files_note": "; ".join(f"{k} `{v}`" for k, v in files.items()) or "none written"}
    md = R.render(res, meta)
    mp, jp = out / f"r10noise_{today}.md", out / f"r10noise_{today}.json"
    mp.write_text(md)
    jp.write_text(json.dumps(clean({"meta": meta, "result": res}), indent=1, default=str))
    print("ROUND 10 NOISE BAND SUMMARY (BACKTEST, real stock bars, shares)")
    print("\n".join(R.summary_lines(res)))
    for w in warnings:
        print(f"WARNING: {w}")
    print(f"r10 noise done in {(time.time() - t_all) / 60:.1f} min\nreport: {mp}\njson:   {jp}", flush=True)
    return 0


# ---------------------------------------------------------------- the runtime estimate (synthetic benchmark)
REAL_SESSIONS = {"HIST": 2033, "DEV": 479}                    # round 8's logged counts (HIST with its warm-up)


def synth_month_files(root, sym, days, seed, px0=300.0, ext=True):
    """Synthetic 1-minute bars in the cache layout (04:00-19:59 when ext, else 09:30-15:59), one gz file per month."""
    rng = np.random.default_rng(seed)
    ec = periods.early_closes()
    px, by_month = px0, {}
    for d in days:
        n_rth = 210 if d.isoformat() in ec else 390
        mins = np.arange(240, 1200) if ext else np.arange(570, 570 + n_rth)
        mins = mins[(mins < 570 + n_rth) | (mins >= 960)]              # no regular-hours bars after an early close
        n = len(mins)
        r = rng.normal(rng.normal(0, 0.00012), 0.0009, n)
        c = px * np.exp(np.cumsum(r))
        o = np.concatenate([[px], c[:-1]])
        h, lo = np.maximum(o, c) * 1.0002, np.minimum(o, c) * 0.9998
        ts = pd.Timestamp(f"{d} 00:00", tz="America/New_York") + pd.to_timedelta(mins, unit="min")
        df = pd.DataFrame({"ts": [t.isoformat() for t in ts], "o": o.round(2), "h": h.round(2), "l": lo.round(2), "c": c.round(2),
                           "v": rng.integers(100, 9000, n).astype(float), "n": 10, "vw": c.round(2)})
        by_month.setdefault(d.strftime("%Y-%m"), []).append(df)
        px = float(c[-1])
    for mth, fr in by_month.items():
        p = Path(root) / "stocks" / sym / f"{mth}.csv.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(_gz_bytes([pd.concat(fr, ignore_index=True).to_csv(index=False)]))


def bench(n_days=126, log=print):
    """Time each stage on synthetic bars (one symbol, `n_days` sessions, extended hours like the real cache) and extrapolate
    to the real run: 7 symbols x (2,033 HIST sessions with warm-up + 479 DEV), the 162-cell evaluation and the files."""
    days = [date.fromisoformat(d) for d in book.sessions_between("2018-01-02", "2019-12-31")][:n_days]
    cfgs = list(R.GRID_CFGS) + [R.FIXES[k] for k in R.FIXES]
    with tempfile.TemporaryDirectory() as tmp:
        synth_month_files(tmp, "SPY", days, 7)
        t0 = time.time()
        ser = shares.load_series("SPY", days[0], days[-1], tmp)
        t_load = time.time() - t0
        t0 = time.time()
        prep = R.Prep(ser, "HIST")
        t_prep = time.time() - t0
        t0 = time.time()
        tr = R.run_engine(prep, cfgs)
        t_eng = time.time() - t0
        t0 = time.time()
        R.self_check(ser, prep, tr, cfgs, sample=list(SAMPLE_CFGS) + [81, 82, 83], every=25)
        t_chk = time.time() - t0
    per_ses = (t_load + t_prep + t_eng) / n_days
    n_real = 7 * (REAL_SESSIONS["HIST"] + REAL_SESSIONS["DEV"])
    n_u3 = 3 * (REAL_SESSIONS["HIST"] + REAL_SESSIONS["DEV"])
    trades_per_cfg_ses = len(tr["pnl"]) / len(cfgs) / n_days
    # the evaluation: 162 cells of the projected size (7 symbols) + the bars and to_rows of the chosen cell and 4 fix variants
    n_cell = int(trades_per_cfg_ses * 7 * (REAL_SESSIONS["HIST"] - 40 + REAL_SESSIONS["DEV"]))
    rng = np.random.default_rng(1)
    ses = np.array(book.sessions_between(shares.HIST_A, shares.HIST_B) + book.sessions_between(shares.DEV_A, shares.DEV_B), dtype="U10")
    one = R.concat([p for p in R.by_cfg(tr, len(cfgs)) if len(p["pnl"])][:1])
    reps = int(np.ceil(n_cell / max(1, len(one["pnl"]))))
    big = R.concat([one] * reps)
    big = {k: v[:n_cell] for k, v in big.items()}
    big["day"] = np.sort(rng.choice(ses, n_cell))
    big["src"] = np.where(big["day"] <= shares.HIST_B, "HIST", "DEV").astype("U4")
    big = R.finish(big)
    t0 = time.time()
    for w in R.WINDOWS:
        R.astats(big, w)
    t_stats = (time.time() - t0) * 162
    t0 = time.time()
    rows = R.to_rows(big, "x", "band_vwap")
    for w in R.HOLDOUTS:
        R.window_bar(rows, w)
    t_bar = (time.time() - t0) * 5
    t0 = time.time()
    for w in R.HOLDOUTS:
        R.compounding(rows, w)
    t_comp = (time.time() - t0) * 5
    with tempfile.TemporaryDirectory() as tmp:
        t0 = time.time()
        write_gz(Path(tmp) / "x.csv.gz", [grid_frame("x", big, "band_vwap").to_csv(index=False)])
        t_write = (time.time() - t0) * 162
    est = {"load + prep + engine (84 settings at once)": per_ses * n_real,
           "self-check (NB-VOL every session on U3, 12 settings every 25th session)": t_chk / n_days * (n_u3 + 4 * n_real / 3),
           "162-cell window stats": t_stats, "7-item bars + to_rows (chosen cell + 4 fix variants)": t_bar,
           "compounding (worst case: 5 passing variants)": t_comp, "grid trade file": t_write}
    log(f"benchmark on {n_days} synthetic sessions (one symbol, 04:00-20:00 bars): load {t_load:.2f}s, prep {t_prep:.2f}s, "
        f"engine {t_eng:.2f}s for {len(cfgs)} settings ({len(tr['pnl'])} trades, {trades_per_cfg_ses:.2f} a setting a session), "
        f"self-check {t_chk:.2f}s")
    log(f"projected: {n_real} symbol-sessions (7 symbols x {REAL_SESSIONS['HIST']} HIST with warm-up + {REAL_SESSIONS['DEV']} DEV), "
        f"about {n_cell:,} trades per U7 cell")
    for k, v in est.items():
        log(f"  {k}: {v / 60:.1f} min")
    log(f"ESTIMATE: about {sum(est.values()) / 60:.0f} minutes on this machine for the full 162-cell grid + fixes "
        f"(per-session cost is linear: 3 symbols instead of 7 takes about {3 / 7:.0%} of the load/engine part)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except periods.LockedPeriod as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
