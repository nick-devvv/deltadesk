#!/usr/bin/env python3
"""tools/sprint_round9.py - SPRINT_PLAN Amendments 12 and 13: round 9 (research only; reads cached bars, EDGAR records and trade
files; never trades; no network).

  python3 tools/sprint_round9.py                     # after tools/sprint_pull9.py
  python3 tools/sprint_round9.py --parts F,G         # a subset (the others are reported as not run)

Reads (data/alpaca unless --data): daily9/ (U-ETF + U-STK daily bars), universe/ustk.json, options_fopt/, ../edgar/
(headers.jsonl, company_tickers.json), g1_bars/, options_g2/, options_w5/, stocks/ (SPY, QQQ, IWM 1-minute bars: HIST
from its 2015-11-01 warm-up, DEV), options/ (DEV 0DTE bars), daily/VIXY.csv.gz; data/sprint/trades_round8_shares_*.csv.gz
(round 8's share trades, Part H); run 7's data/sprint/trades_factory_{hist,dev}_v1_*.csv.gz (FIN-H for the book); the
logged chains folder (default data/chains: MEASURED-SPREAD for Part S where a cell has data).
Runs Part F (sprint/multiday.py), Part G (sprint/catalyst.py), Part H (sprint/round9.part_h, the factory procedure), Part I
(sprint/weekly.py), Part S (sprint/scalp.py), then the book, the trials (203 + the run logs), the deflated Sharpe and the
account view. Writes data/sprint/round9_<date>.md and .json and the per-part trade files
data/sprint/trades_round9_{F,Fopt,G1,G2,G2pool,H,I,S}_<date>.csv.gz (H = round 8's share trades with the stamped entry
features; S = every Part S option trade of every cell, about a million rows on real data); prints the summary. Labels everything BACKTEST,
REAL / MODELED (options) and SURVIVORSHIP-BIASED (U-STK). Refuses any trade row dated inside L1 or L2.
"""
import argparse
import csv
import glob
import gzip
import json
import math
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from sprint import book, catalyst as C, data, edgar as E, engine, factory, multiday as M, periods, round8  # noqa: E402
from sprint import round9 as R9, runner, scalp as S, shares, universe as U, weekly as W  # noqa: E402

PARTS = ("F", "G", "H", "I", "S")
FIN_RVOL = 1.06


def newest(pattern):
    files = sorted(f for f in glob.glob(pattern) if "@" not in Path(f).name)
    return files[-1] if files else None


def check_rows(rows, what):
    """None, or the reason the rows are refused (a row inside L1/L2, or a window touching them)."""
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
    if not rows:
        cols = cols or ["day"]
    cols = cols or list(dict.fromkeys(k for r in rows for k in r.keys() if not k.startswith("_") or k == "_src"))
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


def sessions_iso(kind="hist+dev"):
    return R9.coverage_days(kind)


# ---------------------------------------------------------------- Part F
def part_f(root, log, warnings, panels):
    pe = panels.get("etf")
    if pe is None or not pe.symbols:
        warnings.append("Part F: no U-ETF daily bars (data/alpaca/daily9/): Part F not run.")
        return None, [], []
    ps = panels.get("stk")
    sess = shares.all_sessions()
    out, rows = {}, []
    specs = [("rsi2|U-ETF", pe, lambda: M.rsi2(pe, U.U_ETF, "U-ETF")), ("tom|U-ETF", pe, lambda: M.tom(pe, U.TOM_ETF, "U-ETF"))]
    if ps is not None and ps.symbols:
        specs += [("rsi2|U-STK", ps, lambda: M.rsi2(ps, ps.symbols, "U-STK", cap=M.CAP_USTK)),
                  ("tom|U-STK", ps, lambda: M.tom(ps, ps.symbols, "U-STK"))]
    else:
        warnings.append("Part F: no U-STK list or daily bars: the U-STK legs are not run.")
    for key, panel, fn in specs:
        t0 = time.time()
        trades, info = fn()
        why = check_rows(trades, key)
        if why:
            raise periods.LockedPeriod(why)
        univ = key.split("|")[1]
        rp, _tots, rinfo = M.random_entry(panel, trades, univ)
        pb = M.f_pass(trades, sess, rp)
        o = {"pass_bar": pb, "pass": pb["pass"], "years": shares.years_table(trades), "random_p": rp, "random_info": rinfo,
             "dropped": info.get("dropped"), "signals": info.get("signals"),
             "by_symbol": dict(sorted(((s, shares.stats([t for t in trades if t["symbol"] == s])) for s in sorted({t["symbol"] for t in trades})),
                                      key=lambda kv: -(kv[1].get("trades") or 0))[:25]),
             "account": R9.account_view(trades, "shares", sessions_iso())}
        out[key] = o
        rows += trades
        log(f"  Part F {key}: {len(trades)} trades, {'PASS' if pb['pass'] else 'fail'} ({time.time() - t0:.0f}s)")
    for rule in ("rsi2", "tom"):
        k = f"{rule}|U-STK"
        if k in out:
            etf_ok = out[f"{rule}|U-ETF"]["pass"]
            out[k]["pass_own"] = out[k]["pass"]
            out[k]["pass"] = out[k]["pass"] and etf_ok
            out[k]["note"] = f"own bar {'PASS' if out[k]['pass_own'] else 'fail'}; a U-STK pass needs U-ETF's {rule} to pass ({'PASS' if etf_ok else 'fail'})"
    # F-opt
    fopt_rows, fo = [], {}
    etf_trades = [t for t in rows if t["universe"] == "U-ETF"]
    targets = M.fopt_targets(etf_trades)
    skips = defaultdict(lambda: defaultdict(int))
    for tr in targets:
        e, x = tr["entry_day"], tr["exit_day"]
        base = Path(root) / "options_fopt" / tr["symbol"]
        ef, xf = base / e / "entry.csv.gz", base / x / f"exit_{e}.csv.gz"
        v = f"fopt_{tr['variant']}"
        if not ef.exists():
            skips[v]["no entry-day option file (pull stage fopt)"] += 1
            continue
        ent = pd.read_csv(ef, compression="gzip")
        exi = pd.read_csv(xf, compression="gzip") if xf.exists() else None
        j, k = pe.col[tr["symbol"]], pe.idx(date.fromisoformat(e))
        row, why = M.fopt_trade(tr, ent, exi, float(pe.raw_o[k, j]))
        if row is None:
            skips[v][why] += 1
        else:
            fopt_rows.append(row)
    for v in ("fopt_rsi2", "fopt_tom"):
        rs = [r for r in fopt_rows if r["variant"] == v]
        n_t = sum(1 for t in targets if f"fopt_{t['variant']}" == v)
        fo[v] = {"bar": M.fopt_bar(rs), "targets": n_t, "skips": dict(skips[v]), "late_exits": sum(1 for r in rs if r.get("exit_late")),
                 "account": R9.account_view(rs, "option", sessions_iso("dev"))}
    out["fopt"] = fo
    return out, rows, fopt_rows


# ---------------------------------------------------------------- Part G
def read_g1_day(root, d):
    f = Path(root) / "g1_bars" / f"{d.isoformat()}.csv.gz"
    if not f.exists():
        return None
    df = pd.read_csv(f, compression="gzip")
    return {s: g for s, g in df.groupby("symbol")} if len(df) else {}


def part_g(root, log, warnings, panels):
    ps = panels.get("stk")
    recs = E.read_jsonl(Path(root).parent / "edgar" / "headers.jsonl")
    tj = Path(root).parent / "edgar" / "company_tickers.json"
    if ps is None or not ps.symbols or not recs or not tj.exists():
        warnings.append("Part G: no U-STK panel, EDGAR headers or company tickers (pull stages daily, edgar_index, edgar_headers): "
                        "Part G not run.")
        return None, {}, []
    tmap = E.tickers_map(json.loads(tj.read_text()))
    cal = E.Calendar()
    early = periods.early_closes()
    ev1 = C.g1_events(recs, tmap, ps, cal)
    pc, adv = ps.prior_close(True), ps.adv_shares()
    by_day = defaultdict(list)
    for e in ev1:
        by_day[e["t"]].append(e)
    trades = {"news_go": [], "news_go_lo": []}
    pools = defaultdict(list)
    miss_days, reasons = 0, defaultdict(int)
    for n, d in enumerate(sorted(by_day)):
        bars = read_g1_day(root, d)
        if bars is None:
            miss_days += 1
            continue
        ec = d.isoformat() in early
        k = ps.idx(d)
        for e in by_day[d]:
            g0 = bars.get(e["symbol"])
            if g0 is None:
                reasons["no 1-minute bars for the event"] += 1
                continue
            g = C.day_grid(g0)
            pools[e["symbol"]].append(C.pool_entry(g, ec))
            j = ps.col[e["symbol"]]
            for v, lo in (("news_go", False), ("news_go_lo", True)):
                t, why = C.g1_trade(e, g, float(pc[k, j]), float(adv[k, j]), ec, variant=v, long_only=lo)
                if t is None:
                    if v == "news_go":
                        reasons["|gap| < 2%" if why.startswith("|gap|") else "RV15 < 3" if why.startswith("RV15") else why] += 1
                else:
                    trades[v].append(t)
        if n % 250 == 0:
            log(f"  Part G1 {d} ({n + 1}/{len(by_day)} event days)")
    if miss_days:
        warnings.append(f"Part G1: {miss_days} of {len(by_day)} event days have no 1-minute bar file (pull stage g1 unfinished?).")
    sess = shares.all_sessions()
    g1 = {}
    for v, tr in trades.items():
        why = check_rows(tr, v)
        if why:
            raise periods.LockedPeriod(why)
        rd_p, _ = C.random_direction(tr)
        re_p, _ = C.random_entry_g1(tr, pools)
        extra = [(f"beats random direction on the same events, p < 0.05 (p = {rd_p})", rd_p is not None and rd_p < 0.05)]
        pb = M.f_pass(tr, sess, re_p, extra_checks=extra)
        g1[v] = {"pass_bar": pb, "pass": pb["pass"], "years": shares.years_table(tr), "random_p": re_p, "random_direction_p": rd_p,
                 "account": R9.account_view(tr, "shares", sessions_iso())}
    # G2
    ev2 = C.g2_events(recs, tmap, ps, cal)
    pool = C.random_pool(ev2, ps, C.earnings_days(recs, tmap))
    cache = {}

    def day_map(d, kind):
        """The day's file read once: a price_map (entry) or a close_map (exit); None when the file is missing."""
        key = (d, kind)
        if key not in cache:
            f = Path(root) / "options_g2" / d.isoformat() / f"{kind}.csv.gz"
            df = pd.read_csv(f, compression="gzip") if f.exists() else None
            cache[key] = None if df is None else (C.price_map(df) if kind == "entry" else C.close_map(df))
        return cache[key]

    def straddle(it):
        j, k = ps.col.get(it["symbol"]), ps.idx(it["entry"])
        if j is None or k is None:
            return None, "no daily bar on the entry day"
        close = float(ps.raw_c[k, j])
        pm = day_map(it["entry"], "entry")
        if pm is None:
            return None, "no entry-day option file (pull stage g2)"
        ch, why = C.choose_straddle(None, it["symbol"], it["entry"], close, pmap=pm)
        if ch is None:
            return None, why
        cm = day_map(it["exit"], "exit")
        if cm is None:
            return None, "no exit-day option file (pull stage g2)"
        return C.straddle_trade(it, ch, cm)

    g2_rows, sk = [], defaultdict(int)
    for e in ev2:
        r, why = straddle(e)
        if r is None:
            sk[why] += 1
        else:
            g2_rows.append(r)
    pool_rets, pool_rows = defaultdict(list), []
    for q in pool:
        r, why = straddle(q)
        if r is not None:
            pool_rets[q["event"]].append(r["ret"])
            pool_rows.append(dict(r, variant="g2_pool", event=q["event"]))
    p95, _means, n_ev = C.g2_benchmark(g2_rows, pool_rets)
    g2 = {"pass_bar": C.g2_pass(g2_rows, p95), "skips": dict(sk), "pool_events": n_ev, "pool_dates": len(pool),
          "account": R9.account_view(g2_rows, "option", sessions_iso("dev"))} if ev2 else {"why": "no Item 2.02 events in DEV"}
    res = {"events": {"g1_events": len(ev1), "g1_event_days": len(by_day), "g1_no_signal": dict(reasons), "g2_events": len(ev2),
                      "g2_pool_dates": len(pool), "edgar_records": len(recs)}, "G1": g1, "G2": g2}
    return res, trades, (g2_rows, pool_rows)


# ---------------------------------------------------------------- Part H
def part_h(out, log, warnings, series, vd, sh_file=None):
    f = sh_file or newest(str(Path(out) / "trades_round8_shares_*.csv.gz"))
    if not f or not Path(f).exists():
        warnings.append("Part H: no round-8 share trade file (data/sprint/trades_round8_shares_*.csv.gz): Part H not run.")
        return None, {}, {}, []
    df = pd.read_csv(f, compression="gzip", low_memory=False)
    df = df[df["variant"].isin(R9.H_STRATEGIES)]
    rows = df.to_dict("records")
    for r in rows:
        r["day"] = str(r["day"])[:10]
    why = check_rows(rows, "round-8 share")
    if why:
        raise periods.LockedPeriod(why)
    t0 = time.time()
    n = R9.stamp_share_features(rows, series, {"VIXY_D": vd}, progress=log)
    log(f"  Part H: {len(rows)} round-8 share trades from {f}; features stamped on {n} ({time.time() - t0:.0f}s)")
    by = defaultdict(list)
    for r in rows:
        by[r["variant"]].append(r)
    for s in R9.H_STRATEGIES:
        if not by.get(s):
            warnings.append(f"Part H: no {s} trades in {f}.")
    hres, sleeves, var = R9.part_h(by)
    hres["file"] = f
    return hres, sleeves, var, rows


# ---------------------------------------------------------------- FIN-H for the book
def load_finh(out, fh=None, fd=None):
    """{"HIST", "DEV": rows} of run 7's otm_c_1100 with f_rvol >= 1.06 (FIN-H), or None."""
    files = {"HIST": fh or newest(str(Path(out) / "trades_factory_hist_v1_*.csv.gz")),
             "DEV": fd or newest(str(Path(out) / "trades_factory_dev_v1_*.csv.gz"))}
    specs = {"HIST": HERE / "sprint" / "specs" / "factory_hist_v1.json", "DEV": HERE / "sprint" / "specs" / "factory_dev_v1.json"}
    res = {}
    for src in ("HIST", "DEV"):
        if not files[src] or not Path(files[src]).exists():
            return None, files
        runs = engine.expand(json.loads(specs[src].read_text()))
        ids = {r["run_id"] for r in runs if r["block"] == "otm_c_1100"}
        df = pd.read_csv(files[src], compression="gzip", low_memory=False)
        df = df[df["run_id"].isin(ids) & ~df["run_id"].astype(str).str.contains("@")]
        df = df.drop_duplicates(subset=["run_id", "symbol", "day", "signal_idx", "entry_time"])
        rows = []
        for r in df.to_dict("records"):
            rv = factory.num(r.get("f_rvol"))
            if rv is None or rv < FIN_RVOL:
                continue
            r["_src"], r["day"] = src, str(r["day"])[:10]
            ef = factory.num(r.get("entry_fill"))
            r["debit"] = round(ef * 100 + 0.65, 2) if ef is not None else None
            rows.append(r)
        lo, hi = (periods.HIST if src == "HIST" else periods.DEV)
        res[src] = [r for r in rows if lo.isoformat() <= r["day"] <= hi.isoformat()]
    return res, files


def main(argv=None):
    ap = argparse.ArgumentParser(description="SPRINT_PLAN Amendments 12-13: round 9 (research only)")
    ap.add_argument("--data", default=None, help="cache root (default data/alpaca)")
    ap.add_argument("--out", default=str(HERE / "data" / "sprint"))
    ap.add_argument("--today", default=None)
    ap.add_argument("--parts", default=",".join(PARTS))
    ap.add_argument("--round8-shares", default=None, help="round 8's share trade file (default: newest trades_round8_shares_*.csv.gz)")
    ap.add_argument("--factory-hist", default=None)
    ap.add_argument("--factory-dev", default=None)
    ap.add_argument("--chains-dir", default=str(HERE / "data" / "chains"), help="logged chains for Part S's MEASURED-SPREAD")
    ap.add_argument("--runs-csv", nargs="+", default=None)
    ap.add_argument("--limit-days", type=int, default=None, help="Part S: first N sessions per symbol (smoke test only)")
    x = ap.parse_args(argv)
    t_all = time.time()
    root = Path(x.data) if x.data else data.ROOT
    out = Path(x.out)
    out.mkdir(parents=True, exist_ok=True)
    today = x.today or date.today().isoformat()
    parts = [p.strip().upper() for p in x.parts.split(",") if p.strip()]
    log = lambda s: print(s, flush=True)
    warnings, files = [], {}
    log(f"sprint_round9: parts {', '.join(parts)}; cache {root}; every number is a BACKTEST; L1/L2 never read")
    res = {}
    by_sleeve, kinds, cover, var = {}, {}, {}, {}
    dev_days = sessions_iso("dev")
    # panels (Parts F and G)
    panels = {}
    if "F" in parts or "G" in parts:
        panels["etf"] = U.Panel.load(U.U_ETF, root)
        us = U.read_ustk(root)
        if us:
            panels["stk"] = U.Panel.load(us["symbols"], root, log=log, prefilter=True)
            log(f"  U-STK panel ({U.SB}): {len(panels['stk'].symbols)} symbols can pass the filter, {len(panels['stk'].skipped)} never "
                f"can, {len(panels['stk'].missing)} without daily bars")
    # stock 1-minute series (H, I, S)
    series = {}
    need = {"H": ("SPY", "QQQ", "IWM"), "I": W.SYMBOLS, "S": S.SYMBOLS}
    syms = sorted({s for p in parts if p in need for s in need[p]})
    for sym in syms:
        for src, (a, b) in (("HIST", (periods.WARMUP["HIST"], periods.HIST[1])), ("DEV", periods.DEV)):
            if src == "HIST" and not ({"H", "S"} & set(parts)):
                continue
            ser = shares.load_series(sym, a, b, root)
            if ser.days:
                series[(src, sym)] = ser
        log(f"  bars {sym}: " + ", ".join(f"{k[0]} {len(v.days)} sessions" for k, v in series.items() if k[1] == sym))
    vd = data.read_daily("VIXY", root)
    # ---- F
    if "F" in parts:
        F, f_rows, fo_rows = part_f(root, log, warnings, panels)
        res["F"] = F
        if F:
            files["F"] = write_rows(out / f"trades_round9_F_{today}.csv.gz", f_rows)
            files["Fopt"] = write_rows(out / f"trades_round9_Fopt_{today}.csv.gz", fo_rows)
            for k in ("rsi2|U-ETF", "rsi2|U-STK", "tom|U-ETF", "tom|U-STK"):
                if k not in F:
                    continue
                rule, univ = k.split("|")
                tr = [t for t in f_rows if t["variant"] == rule and t["universe"] == univ]
                var[f"F {k}"] = round8.in_win(tr, R9.DEV_A, R9.DEV_B)
                if F[k]["pass"]:
                    by_sleeve[f"F {k}"], kinds[f"F {k}"], cover[f"F {k}"] = tr, f"shares ($10,000 a trade){', ' + U.SB if univ == 'U-STK' else ''}", "hist+dev"
            for v, o in F["fopt"].items():
                rs = [r for r in fo_rows if r["variant"] == v]
                var[f"F-opt {v}"] = rs
                if o["bar"]["pass"]:
                    by_sleeve[f"F-opt {v}"], kinds[f"F-opt {v}"], cover[f"F-opt {v}"] = rs, "option (REAL, 1 call)", "dev"
    # ---- G
    if "G" in parts:
        G, g1_trades, g2 = part_g(root, log, warnings, panels)
        res["G"] = G
        if G:
            files["G1"] = write_rows(out / f"trades_round9_G1_{today}.csv.gz", g1_trades["news_go"] + g1_trades["news_go_lo"])
            files["G2"] = write_rows(out / f"trades_round9_G2_{today}.csv.gz", g2[0])
            files["G2pool"] = write_rows(out / f"trades_round9_G2pool_{today}.csv.gz", g2[1])
            for v, tr in g1_trades.items():
                var[f"G1 {v}"] = round8.in_win(tr, R9.DEV_A, R9.DEV_B)
                if G["G1"][v]["pass"]:
                    by_sleeve[f"G1 {v}"], kinds[f"G1 {v}"], cover[f"G1 {v}"] = tr, f"shares ($10,000 a trade), {U.SB}", "hist+dev"
            var["G2 pre_earn_straddle"] = g2[0]
            if G["G2"].get("pass_bar", {}).get("pass"):
                by_sleeve["G2 pre_earn_straddle"], kinds["G2 pre_earn_straddle"], cover["G2 pre_earn_straddle"] = g2[0], f"option straddle (REAL), {U.SB}", "dev"
    # ---- H
    if "H" in parts:
        H, hsleeves, hvar, hrows = part_h(out, log, warnings, series, vd, x.round8_shares)
        res["H"] = H
        if H:
            files["H"] = write_rows(out / f"trades_round9_H_{today}.csv.gz", hrows)
            var.update(hvar)
            for name, rows in hsleeves.items():
                var[f"H {name} chosen"] = round8.in_win(rows, R9.DEV_A, R9.DEV_B)
                by_sleeve[f"H {name}"], kinds[f"H {name}"], cover[f"H {name}"] = rows, f"shares ({H['strategies'][name]['verdict']})", "hist+dev"
    # ---- I
    if "I" in parts:
        ser = {s: series[("DEV", s)] for s in W.SYMBOLS if ("DEV", s) in series}
        if not ser or not (root / "options_w5").exists():
            warnings.append("Part I: no DEV stock bars or no weekly option files (pull stage weekly): Part I not run.")
            res["I"] = None
        else:
            ri, sk, cv = W.run(ser, root=root, progress=log)
            I = W.part_i(ri)
            I.update(skips=sk, cover=cv, account=R9.account_view(ri["weekly"], "option", dev_days))
            res["I"] = I
            files["I"] = write_rows(out / f"trades_round9_I_{today}.csv.gz", ri["weekly"] + ri["finh_0dte"])
            var["I w5-10d03-12t07"] = ri["weekly"]
            res["_finh_in_pass"] = ri["finh_0dte"]
            if I["pass"]:
                by_sleeve["I w5-10d03-12t07"], kinds["I w5-10d03-12t07"], cover["I w5-10d03-12t07"] = ri["weekly"], "option (REAL, 1 contract)", "dev"
    # ---- S
    if "S" in parts:
        ser = {s: series[("DEV", s)] for s in S.SYMBOLS if ("DEV", s) in series}
        if not ser:
            warnings.append("Part S: no DEV stock bars for SPY/QQQ: Part S not run.")
            res["S"] = None
        else:
            sp = S.scalp_spread(x.chains_dir)
            t0 = time.time()
            col = S.run(ser, sp, root=root, progress=log, limit_days=x.limit_days)
            df = col.frame()
            log(f"  Part S option pass: {len(df)} trades in {time.time() - t0:.0f}s")
            files["S"] = str(out / f"trades_round9_S_{today}.csv.gz")
            with gzip.open(files["S"], "wt") as fh:
                df.to_csv(fh, index=False)
            ev = S.evaluate(df)
            und = S.underlying({k: v for k, v in series.items() if k[1] in S.SYMBOLS}, progress=log)
            for key, r in ev.items():
                g = r.pop("_test_rows", None)
                cells_dev = df[(df["signal"] == r["signal"]) & (df["contract"] == r["contract"])] if len(df) else df
                for cid in S.CELL_IDS:
                    gg = cells_dev[cells_dev["cell"] == cid] if len(cells_dev) else cells_dev
                    var[f"S {key} {cid}"] = ({"day": gg["day"].astype(str).to_numpy().astype("U10"), "pnl": gg["pnl"].to_numpy(float),
                                              "pnl_2x": gg["pnl_2x"].to_numpy(float)} if len(gg) else [])
                if g is not None:
                    rows = [dict(rr, _src="DEV", entry_time=f"{(570 + int(rr['entry_idx'])) // 60:02d}:{(570 + int(rr['entry_idx'])) % 60:02d}")
                            for rr in g.to_dict("records")]
                    r["account"] = R9.account_view(rows, "option", sessions_iso("dev"))
                if r["pass_"] and r["chosen"]:
                    allc = cells_dev[cells_dev["cell"] == r["chosen"]]
                    rows = [dict(rr, _src="DEV", entry_time=f"{(570 + int(rr['entry_idx'])) // 60:02d}:{(570 + int(rr['entry_idx'])) % 60:02d}",
                                 exit_time=f"{(570 + int(rr['exit_idx'])) // 60:02d}:{(570 + int(rr['exit_idx'])) % 60:02d}")
                            for rr in allc.to_dict("records")]
                    nm = f"S {key} {r['chosen']}"
                    by_sleeve[nm], kinds[nm], cover[nm] = rows, f"option (REAL, 1 contract; before {S.TEST[0]} in-sample)", "dev"
            res["S"] = {"evaluate": ev, "underlying": und, "coverage": S.coverage(col), "spread": sp.describe(), "choice": f"{S.CHOICE[0]}..{S.CHOICE[1]}",
                        "test": f"{S.TEST[0]}..{S.TEST[1]}", "skips": {f"{a}|{b}|{c}": dict(v) for (a, b, c), v in col.skips.items()}}
    # ---- FIN-H and the book
    finh, ffiles = load_finh(out, x.factory_hist, x.factory_dev)
    files["factory"] = ffiles
    if finh is not None:
        fin_rows = finh["HIST"] + finh["DEV"]
        cover["FIN-H"], kinds["FIN-H"] = "hist+dev", "option (FIN-H, 1 contract; 2016-2024 MODELED, DEV REAL)"
    elif res.get("_finh_in_pass") is not None:
        fin_rows = res["_finh_in_pass"]
        cover["FIN-H"], kinds["FIN-H"] = "dev", "option (FIN-H 0DTE from Part I's pass, DEV REAL only)"
        warnings.append("Run 7's factory trade files were not found: FIN-H in the book is Part I's same-pass 0DTE FIN-H, DEV only.")
    else:
        fin_rows = []
        cover["FIN-H"], kinds["FIN-H"] = "dev", "option (FIN-H: no trades found)"
        warnings.append("No FIN-H trades found (run 7's factory files or Part I): the book has no FIN-H sleeve.")
    res.pop("_finh_in_pass", None)
    by_sleeve = {"FIN-H": fin_rows, **by_sleeve}
    kinds = {"FIN-H": kinds["FIN-H"], **{k: v for k, v in kinds.items() if k != "FIN-H"}}
    for k, rows in by_sleeve.items():
        why = check_rows(rows, f"book sleeve {k}")
        if why:
            raise periods.LockedPeriod(why)
    res["book"] = R9.run_book(by_sleeve, kinds, cover)
    acc_rows = [r for rows in by_sleeve.values() for r in round8.in_win(rows, R9.DEV_A, R9.DEV_B)]
    res["book"]["account"] = R9.account_view(acc_rows, "mixed", dev_days) if acc_rows else None
    var["FIN-H"] = round8.in_win(fin_rows, R9.DEV_A, R9.DEV_B)
    # ---- trials and the deflated Sharpe
    n_prior = count_trials(out, x.runs_csv)
    res["trials"] = R9.trials(n_prior)
    tab, sr_var, n = R9.dsr_table(var, n_prior, dev_days)
    tab15, _sv, _n = R9.dsr_table(var, n_prior, dev_days, extra=15)
    res["dsr"], res["dsr_plus15"], res["sr_var"], res["dev_variants_scored"] = tab, tab15, sr_var, len(var)
    meta = {"today": today, "parts": parts, "warnings": warnings, "files": files,
            "files_note": "; ".join(f"{k} `{v}`" for k, v in files.items() if isinstance(v, str))}
    md = R9.render(res, meta)
    mp, jp = out / f"round9_{today}.md", out / f"round9_{today}.json"
    mp.write_text(md)
    jp.write_text(json.dumps(factory.clean({"meta": meta, "result": res}), indent=1, default=str))
    print("ROUND 9 SUMMARY (BACKTEST; options REAL on DEV unless MODELED; U-STK SURVIVORSHIP-BIASED)")
    print("\n".join(R9.summary_lines(res)))
    for w in warnings:
        print(f"WARNING: {w}")
    print(f"round 9 done in {(time.time() - t_all) / 60:.1f} min\nreport: {mp}\njson:   {jp}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except periods.LockedPeriod as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
