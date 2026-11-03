#!/usr/bin/env python3
"""tools/sprint_r12.py - round 12 on Chart's computer: free daily history, a data check, the nine pre-registered trials
(sprint/r12daily.py; SPRINT_PLAN "Round 12 pre-registration") and the zips. Research only: market data reads only (Yahoo
Finance through yfinance; Stooq and FRED as plain CSV downloads); no orders, no account, no keys; never touches ~/desk.
  python3 tools/sprint_r12.py all            # fetch -> check -> run -> zip (about 5-15 minutes)
  python3 tools/sprint_r12.py fetch          # resumable: a finished file is skipped unless --force
  python3 tools/sprint_r12.py check          # data/r12/check.json + data/sprint/round12_data_check_<date>.md
  python3 tools/sprint_r12.py run            # data/sprint/round12_<date>.md/.json, trades, daily returns
  python3 tools/sprint_r12.py zip            # ~/sprint_results12.zip and ~/sprint_data12.zip
Locked periods: only SEGMENTS are ever requested (1998-01-02..2024-01-31 and 2024-08-01..2026-06-30); both avoid L1 and L2
(sprint/periods.py), checked before any request; rows inside L1/L2 in a response are dropped and counted.
Sources: Yahoo (primary: split-adjusted OHLC + the dividend-adjusted close), Stooq (cross-check of daily returns; the run
goes on as "single source" if Stooq is unreachable), FRED DTB3 (cash; Yahoo ^IRX as the fallback and cross-check).
Data rule (pre-registered with the round): a session where Yahoo's and Stooq's close-to-close returns differ by more than
3% is a mismatch (larger than any ex-dividend day of these ETFs); a symbol with more than 3 mismatches inside FRESH is
excluded from every trial; if SPY is excluded the run stops (exit 3).
Exit codes: 0 done; 1 failed (network or crash; re-running resumes); 2 a locked period was asked for; 3 a missing setting
or unusable data (not retried).
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import sys
import time
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from sprint import periods  # noqa: E402
from sprint import r12daily as R12  # noqa: E402

SEGMENTS = ((date(1998, 1, 2), date(2024, 1, 31)), (date(2024, 8, 1), date(2026, 6, 30)))
UA = "deltadesk-research/1.0"
MISMATCH_RET, MISMATCH_MAX = 0.03, 3
EXTREME_RET = 0.25


class Unusable(RuntimeError):
    """Missing setting or unusable data: exit 3, not retried."""


def check_segments(segs=SEGMENTS):
    for a, b in segs:
        hit = periods.overlaps(a, b)
        if hit:
            raise periods.LockedPeriod(f"segment {a}..{b} touches {', '.join(hit)}: refused")


def refuse_desk():
    cwd = Path.cwd().resolve()
    desk = (Path.home() / "desk").resolve()
    if cwd == desk or desk in cwd.parents:
        raise Unusable("REFUSED: this tool never runs inside ~/desk")


# ------------------------------------------------------------------ network (replaceable in tests)
def http_get(url, tries=3, wait=5.0):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - every network error is retried, then reported
            last = e
            if i < tries - 1:
                time.sleep(wait * (i + 1))
    raise ConnectionError(f"{url}: {last}")


def yahoo_history(sym, a, b):
    """Daily bars [a, b] from Yahoo through yfinance (split-adjusted OHLC, Adj Close, Dividends)."""
    import yfinance as yf
    df = yf.Ticker(sym).history(start=a.isoformat(), end=(b + timedelta(days=1)).isoformat(), interval="1d",
                                auto_adjust=False, actions=True)
    return normalize_yahoo(df)


def normalize_yahoo(df):
    """Columns open, high, low, close, adj_close, volume, dividends on a naive date index. Without an Adj Close column the
    dividend-adjusted close is rebuilt from Dividends the way Yahoo does it (each ex-date scales every earlier close by
    1 - dividend / the prior close)."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["open", "high", "low", "close", "adj_close", "volume", "dividends"])
    d = df.copy()
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = [c[0] for c in d.columns]
    idx = pd.DatetimeIndex(d.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    d.index = idx.normalize()
    ren = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Adj Close": "adj_close", "Volume": "volume",
           "Dividends": "dividends"}
    d = d.rename(columns=ren)
    if "dividends" not in d:
        d["dividends"] = 0.0
    if "volume" not in d:
        d["volume"] = np.nan
    if "adj_close" not in d:
        d["adj_close"] = rebuild_adj_close(d["close"].to_numpy(float), d["dividends"].fillna(0).to_numpy(float))
    d = d[["open", "high", "low", "close", "adj_close", "volume", "dividends"]].astype(float)
    d = d[~d.index.duplicated(keep="last")].sort_index()
    return d.dropna(subset=["open", "high", "low", "close", "adj_close"])


def rebuild_adj_close(close, div):
    n = len(close)
    f = np.ones(n)
    run = 1.0
    for i in range(n - 1, -1, -1):
        f[i] = run
        if i > 0 and div[i] > 0 and close[i - 1] > 0:
            run *= 1.0 - div[i] / close[i - 1]
    return close * f


def parse_stooq(raw):
    txt = raw.decode("utf-8", "replace").strip()
    if not txt.lower().startswith("date"):
        raise ConnectionError(f"stooq: not a CSV ({txt[:60]!r})")
    df = pd.read_csv(io.StringIO(txt))
    df.columns = [c.strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")[["open", "high", "low", "close"]].astype(float).sort_index()


def parse_fred(raw, sid="DTB3"):
    txt = raw.decode("utf-8", "replace").strip()
    df = pd.read_csv(io.StringIO(txt))
    dcol = "observation_date" if "observation_date" in df.columns else ("DATE" if "DATE" in df.columns else None)
    if dcol is None or sid not in df.columns:
        raise ConnectionError(f"fred: unexpected columns {list(df.columns)[:4]}")
    s = pd.to_numeric(df[sid], errors="coerce")
    s.index = pd.to_datetime(df[dcol])
    return s.dropna().sort_index()


# ------------------------------------------------------------------ fetch
def _drop_locked(df):
    keep = np.ones(len(df), bool)
    for a, b in periods.LOCKED.values():
        keep &= ~((df.index >= pd.Timestamp(a)) & (df.index <= pd.Timestamp(b)))
    return df[keep], int((~keep).sum())


def _write(path, df):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt") as fh:
        df.to_csv(fh, index_label="date")
    tmp.replace(path)


def _read(path):
    with gzip.open(path, "rt") as fh:
        df = pd.read_csv(fh, parse_dates=["date"], index_col="date")
    return df


def _done(path):
    return path.with_suffix(".done")


def fetch_one(path, pieces_fn, force=False, log=print):
    """Resumable: skip when the .done marker exists. pieces_fn(a, b) returns a frame for one segment."""
    if _done(path).exists() and path.exists() and not force:
        log(f"  {path.name}: done before, skipped")
        return "skipped"
    parts = []
    for a, b in SEGMENTS:
        df = pieces_fn(a, b)
        if df is None or len(df) == 0:
            continue
        df = df[(df.index >= pd.Timestamp(a)) & (df.index <= pd.Timestamp(b))]
        parts.append(df)
    if not parts:
        raise ConnectionError(f"{path.name}: no rows returned")
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df, dropped = _drop_locked(df)
    _write(path, df)
    _done(path).write_text(json.dumps({"rows": int(len(df)), "first": str(df.index[0].date()), "last": str(df.index[-1].date()),
                                       "locked_rows_dropped": dropped}))
    log(f"  {path.name}: {len(df)} rows {df.index[0].date()}..{df.index[-1].date()}" + (f" ({dropped} locked rows dropped)" if dropped else ""))
    return "fetched"


def fetch(root, force=False, stooq=True, history=None, get=None, log=print):
    check_segments()
    history = history or yahoo_history
    get = get or http_get
    root = Path(root)
    status = {"yahoo": {}, "stooq": {}, "cash": {}}
    def yahoo(s, a, b):
        try:
            return history(s, a, b)
        except ConnectionError:
            raise
        except Exception as e:  # noqa: BLE001 - yfinance raises its own types (rate limits, parse errors)
            raise ConnectionError(f"yahoo {s} {a}..{b}: {type(e).__name__}: {e}") from e

    for sym in R12.SYMBOLS:
        status["yahoo"][sym] = fetch_one(root / "yahoo" / f"{sym}.csv.gz", lambda a, b, s=sym: yahoo(s, a, b), force, log)
    if stooq:
        for sym in R12.SYMBOLS:
            try:
                status["stooq"][sym] = fetch_one(
                    root / "stooq" / f"{sym}.csv.gz",
                    lambda a, b, s=sym: parse_stooq(get(f"https://stooq.com/q/d/l/?s={s.lower()}.us&d1={a:%Y%m%d}&d2={b:%Y%m%d}&i=d")),
                    force, log)
            except ConnectionError as e:
                status["stooq"][sym] = f"unavailable: {e}"
                log(f"  stooq {sym}: unavailable ({e}); the check will say single source")
    try:
        status["cash"]["DTB3"] = fetch_one(
            root / "cash" / "DTB3.csv.gz",
            lambda a, b: parse_fred(get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3&cosd={a}&coed={b}")).to_frame("rate"),
            force, log)
    except ConnectionError as e:
        status["cash"]["DTB3"] = f"unavailable: {e}"
        log(f"  FRED DTB3 unavailable ({e}); falling back to Yahoo ^IRX")
    try:
        status["cash"]["IRX"] = fetch_one(root / "cash" / "IRX.csv.gz", lambda a, b: yahoo("^IRX", a, b)[["close"]].rename(columns={"close": "rate"}),
                                          force, log)
    except ConnectionError as e:
        status["cash"]["IRX"] = f"unavailable: {e}"
    (root / "fetch_status.json").write_text(json.dumps(status, indent=1))
    return status


# ------------------------------------------------------------------ check
def load_frames(root, sub="yahoo"):
    out = {}
    for sym in R12.SYMBOLS:
        p = Path(root) / sub / f"{sym}.csv.gz"
        if p.exists():
            out[sym] = _read(p)
    return out


def load_cash(root):
    for name in ("DTB3", "IRX"):
        p = Path(root) / "cash" / f"{name}.csv.gz"
        if p.exists():
            return _read(p)["rate"], name
    return None, None


def check(root, log=print):
    root = Path(root)
    ya, st = load_frames(root, "yahoo"), load_frames(root, "stooq")
    if "SPY" not in ya:
        raise Unusable("no Yahoo SPY file: run fetch first")
    cal = ya["SPY"].index
    fa, fb = (pd.Timestamp(x) for x in R12.WINDOWS["FRESH"])
    rep = {"symbols": {}, "excluded": [], "cross_source": "Stooq" if st else "UNAVAILABLE (single source)"}
    for sym in R12.SYMBOLS:
        d = ya.get(sym)
        if d is None:
            rep["symbols"][sym] = {"missing": True}
            rep["excluded"].append(sym)
            continue
        info = {"rows": int(len(d)), "first": str(d.index[0].date()), "last": str(d.index[-1].date())}
        mine = cal[(cal >= d.index[0]) & (cal <= d.index[-1])]
        holes = mine.difference(d.index)
        info["missing_sessions"] = int(len(holes))
        info["missing_examples"] = [str(x.date()) for x in holes[:5]]
        info["duplicates"] = int(d.index.duplicated().sum())
        bad = (d[["open", "high", "low", "close", "adj_close"]] <= 0).any(axis=1)
        info["non_positive_rows"] = int(bad.sum())
        lo_bad = d["low"] > d[["open", "close"]].min(axis=1) * 1.005
        hi_bad = d["high"] < d[["open", "close"]].max(axis=1) * 0.995
        info["ohlc_violations"] = int((lo_bad | hi_bad).sum())
        r = d["adj_close"].pct_change()
        big = r[r.abs() > EXTREME_RET]
        info["extreme_moves"] = [f"{x.date()} {v:+.1%}" for x, v in big.items()]
        yrs = []
        for y, g in d.groupby(d.index.year):
            if len(g) < 200:
                continue
            tr = g["adj_close"].iloc[-1] / g["adj_close"].iloc[0] - 1
            pr = g["close"].iloc[-1] / g["close"].iloc[0] - 1
            if not (-0.005 <= tr - pr <= 0.10):
                yrs.append(f"{y}: total {tr:+.1%} vs price {pr:+.1%}")
        info["dividend_flags"] = yrs
        s = st.get(sym)
        if s is not None:
            j = d[["close"]].join(s[["close"]].rename(columns={"close": "stooq"}), how="inner")
            ry, rs = j["close"].pct_change(), j["stooq"].pct_change()
            diff = (ry - rs).abs()
            mm = diff[diff > MISMATCH_RET]
            fresh_mm = mm[(mm.index >= fa) & (mm.index <= fb)]
            info["cross"] = {"common_sessions": int(len(j)), "corr": float(ry.corr(rs)) if len(j) > 10 else None,
                             "mismatches": int(len(mm)), "fresh_mismatches": int(len(fresh_mm)),
                             "examples": [f"{x.date()} {v:.1%}" for x, v in mm.head(5).items()]}
            if len(fresh_mm) > MISMATCH_MAX:
                rep["excluded"].append(sym)
        rep["symbols"][sym] = info
    cash, src = load_cash(root)
    rep["cash_source"] = src or "MISSING"
    dt, ir = (Path(root) / "cash" / "DTB3.csv.gz"), (Path(root) / "cash" / "IRX.csv.gz")
    if dt.exists() and ir.exists():
        j = _read(dt)["rate"].to_frame("dtb3").join(_read(ir)["rate"].to_frame("irx"), how="inner")
        rep["cash_cross"] = {"common": int(len(j)), "mean_abs_diff_pct_points": float((j["dtb3"] - j["irx"]).abs().mean())}
    rep["excluded"] = sorted(set(rep["excluded"]))
    (root / "check.json").write_text(json.dumps(rep, indent=1))
    return rep


def check_md(rep):
    L = ["# Round 12 data check", "", f"Cross-source: {rep['cross_source']}. Cash: {rep['cash_source']}"
         + (f" (DTB3 vs ^IRX mean gap {rep['cash_cross']['mean_abs_diff_pct_points']:.2f} points over {rep['cash_cross']['common']} days)"
            if rep.get("cash_cross") else "") + ".",
         f"Excluded (more than {MISMATCH_MAX} Yahoo/Stooq mismatches over {MISMATCH_RET:.0%} inside FRESH, or missing): "
         f"{', '.join(rep['excluded']) or 'none'}.", "",
         "| Symbol | Rows | First | Last | Missing sessions | OHLC flags | Extreme moves | Dividend flags | Stooq corr | Mismatches (FRESH) |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for sym, i in rep["symbols"].items():
        if i.get("missing"):
            L.append(f"| {sym} | missing | | | | | | | | |")
            continue
        cr = i.get("cross") or {}
        corr = "-" if cr.get("corr") is None else "%.4f" % cr["corr"]
        L.append(f"| {sym} | {i['rows']} | {i['first']} | {i['last']} | {i['missing_sessions']} | {i['ohlc_violations']} | "
                 f"{len(i['extreme_moves'])} | {len(i['dividend_flags'])} | {corr} | "
                 f"{cr.get('mismatches', '-')} ({cr.get('fresh_mismatches', '-')}) |")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ run
def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def run(root, out_dir, log=print, today=None):
    root, out_dir = Path(root), Path(out_dir)
    rep = json.loads((root / "check.json").read_text()) if (root / "check.json").exists() else check(root, log)
    if "SPY" in rep["excluded"]:
        raise Unusable("SPY failed the data check: the run stops (see the data check)")
    frames = {s: f for s, f in load_frames(root, "yahoo").items() if s not in rep["excluded"]}
    cash, src = load_cash(root)
    if cash is None:
        raise Unusable("no cash series (FRED DTB3 and Yahoo ^IRX both missing)")
    m = R12.Market(frames, cash)
    res = {lvl: R12.run_trials(m, c) for lvl, c in R12.COSTS.items()}
    ev = R12.evaluate(m, res)
    ev["data"] = {"source": "Yahoo (yfinance)", "cross_source": rep["cross_source"], "cash": src, "excluded": rep["excluded"],
                  "first_session": m.days[0].isoformat(), "last_session": m.days[-1].isoformat(), "segments": len(m.segments())}
    stamp = (today or date.today()).isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    note = (f"Data: Yahoo daily bars via yfinance, {m.days[0]}..{m.days[-1]} in {len(m.segments())} segments (L2 cut out, ends "
            f"before L1). Cross-source: {rep['cross_source']}. Cash: {src}. Excluded: {', '.join(rep['excluded']) or 'none'}.")
    (out_dir / f"round12_{stamp}.md").write_text(R12.report_md(ev, note))
    (out_dir / f"round12_{stamp}.json").write_text(json.dumps(_jsonable(ev), indent=1))
    (out_dir / f"round12_data_check_{stamp}.md").write_text(check_md(rep))
    daily = pd.DataFrame({"date": [d.isoformat() for d in m.days], "segment": m.seg, "cash": m.cash})
    for name in R12.TRIALS:
        daily[name] = res["2x"][name]["r"]
        daily[name + "_expo"] = res["2x"][name]["expo"]
    daily["SPY_bh"] = R12.buy_hold(m, np.ones(m.n, bool))[1]
    with gzip.open(out_dir / f"round12_daily_{stamp}.csv.gz", "wt") as fh:
        daily.to_csv(fh, index=False)
    for name in R12.RSI2_TRIALS:
        rows = res["2x"][name]["trades"]
        with gzip.open(out_dir / f"trades_round12_{name}_{stamp}.csv.gz", "wt", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["symbol", "entry_day", "exit_day", "entry_idx", "exit_idx", "entry_px", "exit_px",
                                               "gross", "hold", "exit"])
            w.writeheader()
            for t in rows:
                w.writerow(t)
    for name in R12.TRIALS:
        v = ev["verdicts"][name]
        log(f"round12 {name}: {'PASS' if v['pass'] else 'FAIL'} ({v['why']})")
    log(f"report: {out_dir / f'round12_{stamp}.md'}")
    return ev, stamp


# ------------------------------------------------------------------ zip
def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def make_zips(root, out_dir, zip_dir, stamp=None, log=print):
    root, out_dir, zip_dir = Path(root), Path(out_dir), Path(zip_dir)
    stamp = stamp or max((p.stem.split("_")[-1] for p in out_dir.glob("round12_*.json") if "check" not in p.name), default=None)
    if not stamp:
        raise Unusable("no round 12 report to zip: run first")
    res_files = sorted(out_dir.glob(f"*round12*{stamp}*")) + sorted((out_dir / "logs").glob("r12_*.log"))
    data_files = sorted(p for p in root.rglob("*") if p.is_file() and not p.name.endswith(".tmp"))
    zr, zd = zip_dir / "sprint_results12.zip", zip_dir / "sprint_data12.zip"
    for zpath, files, base in ((zr, res_files, out_dir.parent.parent), (zd, data_files, root.parent.parent)):
        man = {str(p): sha256(p) for p in files}
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for p in files:
                try:
                    arc = p.resolve().relative_to(base.resolve())
                except ValueError:
                    arc = p.name
                z.write(p, str(arc))
            z.writestr("MANIFEST_sha256.json", json.dumps(man, indent=1))
        log(f"zip: {zpath} ({len(files)} files, {zpath.stat().st_size / 1e6:.1f} MB)")
    return zr, zd


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("step", choices=["fetch", "check", "run", "zip", "all"])
    ap.add_argument("--data", default="data/r12")
    ap.add_argument("--out", default="data/sprint")
    ap.add_argument("--zip-dir", default=str(Path.home()))
    ap.add_argument("--force", action="store_true", help="re-download files already marked done")
    ap.add_argument("--no-stooq", action="store_true", help="skip the Stooq cross-check download")
    x = ap.parse_args(argv)
    refuse_desk()
    check_segments()
    if x.step in ("fetch", "all"):
        st = fetch(x.data, x.force, not x.no_stooq)
        bad = [s for s, v in st["yahoo"].items() if v not in ("fetched", "skipped")]
        if bad:
            raise ConnectionError(f"Yahoo failed for {bad}")
    if x.step in ("check", "all"):
        rep = check(x.data)
        print(check_md(rep))
    stamp = None
    if x.step in ("run", "all"):
        _, stamp = run(x.data, x.out)
    if x.step in ("zip", "all"):
        make_zips(x.data, x.out, x.zip_dir, stamp)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except periods.LockedPeriod as e:
        print(f"LOCKED: {e}")
        sys.exit(2)
    except Unusable as e:
        print(f"STOP: {e}")
        sys.exit(3)
    except ConnectionError as e:
        print(f"FAILED (network; re-run resumes): {e}")
        sys.exit(1)
