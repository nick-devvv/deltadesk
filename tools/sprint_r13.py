#!/usr/bin/env python3
"""tools/sprint_r13.py - round 13 on Chart's computer: Ken French's daily industry and factor files, a data check, the
three pre-registered trials (sprint/r13ff.py; SPRINT_PLAN "Round 13 pre-registration") and the zips. Research only: two
public CSV downloads from mba.tuck.dartmouth.edu; no orders, no account, no keys; never touches ~/desk.
  python3 tools/sprint_r13.py all                      # fetch -> check -> run -> zip (a few minutes)
  python3 tools/sprint_r13.py fetch [--from-dir DIR]    # DIR: the two zips downloaded by hand, if the site is blocked
  python3 tools/sprint_r13.py check | run | zip
Locked periods: the French files are whole-history downloads, so every row after 2024-01-31 is dropped while parsing and
the raw download is never saved; the cleaned files end before L2 (checked with sprint/periods.py).
Exit codes: 0 done; 1 failed (network or crash; re-running is safe); 2 a locked period in the cleaned data; 3 a missing
file or unusable data (not retried).
"""
import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import time
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from sprint import periods  # noqa: E402
from sprint import r13ff as R13  # noqa: E402

UA = "deltadesk-research/1.0"
BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/"
FILES = {"industries": "10_Industry_Portfolios_Daily_CSV.zip", "factors": "F-F_Research_Data_Factors_daily_CSV.zip"}
LOCAL_GLOBS = {"industries": "10_Industry_Portfolios_*aily*.zip", "factors": "F-F_Research_Data_Factors_*aily*.zip"}
PATTERNS = {"industries": r"ftp/(10_Industry_Portfolios_[Dd]aily_CSV\.zip)", "factors": r"ftp/(F-F_Research_Data_Factors_[Dd]aily_CSV\.zip)"}
MIN_ROWS = 20_000


class Unusable(RuntimeError):
    """Missing file or unusable data: exit 3, not retried."""


def refuse_desk():
    cwd = Path.cwd().resolve()
    desk = (Path.home() / "desk").resolve()
    if cwd == desk or desk in cwd.parents:
        raise Unusable("REFUSED: this tool never runs inside ~/desk")


def http_get(url, tries=3, wait=5.0):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - every network error is retried, then reported
            last = e
            if i < tries - 1:
                time.sleep(wait * (i + 1))
    raise ConnectionError(f"{url}: {last}")


def is_zip(blob):
    return isinstance(blob, (bytes, bytearray)) and blob[:2] == b"PK"


def download(kind, get=http_get, log=print):
    """The zip for `kind`: the known file name first, then a link found on the data library page."""
    url = BASE + "ftp/" + FILES[kind]
    try:
        blob = get(url)
        if is_zip(blob):
            return blob, url
        log(f"  {kind}: {url} did not return a zip; looking on the data library page")
    except ConnectionError as e:
        log(f"  {kind}: {e}; looking on the data library page")
    page = get(BASE + "data_library.html").decode("latin-1", "replace")
    m = re.search(PATTERNS[kind], page)
    if not m:
        raise ConnectionError(f"{kind}: no link matching {PATTERNS[kind]} on the data library page")
    url = BASE + "ftp/" + m.group(1)
    blob = get(url)
    if not is_zip(blob):
        raise ConnectionError(f"{kind}: {url} is not a zip")
    return blob, url


def zip_text(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))]
        if not names:
            raise Unusable("the zip holds no CSV file")
        return z.read(names[0]).decode("latin-1", "replace")


def parse_french(text):
    """The first table of a French data-library CSV (for the industry file: the value-weighted returns). Values are
    percent per day; -99.99 and -999 mean missing. Returns a frame of fractions on a date index."""
    lines = text.splitlines()
    head = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith(",") and re.search(r"[A-Za-z]", ln):
            head = i
            break
    if head is None:
        raise Unusable("no header row (a line starting with a comma) in the file")
    cols = [c.strip() for c in lines[head].split(",")[1:]]
    rows = []
    for ln in lines[head + 1:]:
        if not re.match(r"^\s*\d{8}\s*,", ln):
            if rows:
                break
            continue
        parts = [x.strip() for x in ln.split(",")]
        rows.append([parts[0]] + parts[1:1 + len(cols)])
    if not rows:
        raise Unusable("no daily rows after the header")
    df = pd.DataFrame(rows, columns=["date"] + cols)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df = df.set_index("date")
    df = df.apply(pd.to_numeric, errors="coerce")
    df = df.mask(df <= -99.99)
    return df / 100.0


def clean(df):
    """Rows up to R13.LAST_DAY only (L2, L1 and later are never kept)."""
    keep = df[df.index <= pd.Timestamp(R13.LAST_DAY)]
    return keep, int(len(df) - len(keep))


def _write(path, df):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt") as fh:
        df.to_csv(fh, index_label="date")
    tmp.replace(path)


def _read(path):
    with gzip.open(path, "rt") as fh:
        return pd.read_csv(fh, parse_dates=["date"], index_col="date")


def fetch(root, get=http_get, from_dir=None, log=print):
    root = Path(root)
    status = {}
    for kind in FILES:
        if from_dir:
            cand = sorted(Path(from_dir).glob(LOCAL_GLOBS[kind]))
            if not cand:
                raise Unusable(f"{kind}: no file like {FILES[kind]} in {from_dir}")
            blob, src = cand[0].read_bytes(), str(cand[0])
            if not is_zip(blob):
                raise Unusable(f"{kind}: {src} is not a zip")
        else:
            blob, src = download(kind, get, log)
        df, dropped = clean(parse_french(zip_text(blob)))
        if kind == "industries":
            df.columns = [c.strip() for c in df.columns]
        _write(root / f"{kind}.csv.gz", df)
        status[kind] = {"source": src, "sha256_of_download": hashlib.sha256(blob).hexdigest(), "rows": int(len(df)),
                        "first": str(df.index[0].date()), "last": str(df.index[-1].date()), "rows_after_2024_01_31_dropped": dropped}
        log(f"  {kind}: {len(df)} rows {df.index[0].date()}..{df.index[-1].date()} ({dropped} later rows dropped, not saved)")
    (root / "fetch_status.json").write_text(json.dumps(status, indent=1))
    return status


def check(root, log=print):
    root = Path(root)
    if not (root / "industries.csv.gz").exists() or not (root / "factors.csv.gz").exists():
        raise Unusable("cleaned files missing: run fetch first")
    ind, fac = _read(root / "industries.csv.gz"), _read(root / "factors.csv.gz")
    first, last = min(ind.index[0], fac.index[0]).date(), max(ind.index[-1], fac.index[-1]).date()
    hit = periods.overlaps(first, last)
    if hit:
        raise periods.LockedPeriod(f"cleaned data {first}..{last} touch {', '.join(hit)}")
    try:
        d = R13.Data(ind, fac)
    except ValueError as e:
        raise Unusable(str(e)) from e
    rep = {"sessions": d.n, "first": d.days[0].isoformat(), "last": d.days[-1].isoformat(),
           "missing_values": {c: int(ind[c].isna().sum()) for c in R13.INDUSTRIES if c in ind},
           "sessions_per_year": {str(y): int(n) for y, n in pd.Series(1, index=d.index).groupby(d.index.year).sum().items()
                                 if y in (1927, 1940, 1951, 1953, 1970, 1997, 2023)},
           "market_year_returns": {}, "extreme_market_days": [], "rf_daily_max_pct": float(d.rf.max() * 100)}
    m = pd.Series(d.mkt, index=d.index)
    for y in (1929, 1930, 1931, 1932, 1933, 1974, 1987, 2008):
        g = m[m.index.year == y]
        if len(g):
            rep["market_year_returns"][str(y)] = float(np.prod(1 + g) - 1)
    big = m[m.abs() > 0.10]
    rep["extreme_market_days"] = [f"{x.date()} {v:+.1%}" for x, v in big.items()]
    problems = []
    if d.n < MIN_ROWS:
        problems.append(f"only {d.n} sessions")
    a, b = R13.WINDOWS["PASS"]
    if d.days[0] > date(1926, 12, 31) or d.days[-1] < b:
        problems.append(f"the data {d.days[0]}..{d.days[-1]} don't cover the PASS window with its warm-up")
    if any(v > 50 for v in rep["missing_values"].values()):
        problems.append("more than 50 missing values in an industry")
    rep["problems"] = problems
    (root / "check.json").write_text(json.dumps(rep, indent=1))
    if problems:
        raise Unusable("; ".join(problems))
    return rep


def check_md(rep):
    L = ["# Round 13 data check", "", f"Sessions {rep['sessions']:,}, {rep['first']}..{rep['last']} (later rows dropped while parsing).",
         f"Missing values: {sum(rep['missing_values'].values())}. Largest daily T-bill return: {rep['rf_daily_max_pct']:.3f}%.",
         "Sessions per year (Saturdays before 1952): " + ", ".join(f"{y} {n}" for y, n in rep["sessions_per_year"].items()) + ".",
         "Market total return by year: " + ", ".join(f"{y} {v:+.1%}" for y, v in rep["market_year_returns"].items()) + ".",
         f"Market days beyond +/-10%: {len(rep['extreme_market_days'])} ({', '.join(rep['extreme_market_days'][:8])}).",
         f"Problems: {', '.join(rep['problems']) or 'none'}."]
    return "\n".join(L) + "\n"


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(float(x)) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def run(root, out_dir, log=print, today=None):
    root, out_dir = Path(root), Path(out_dir)
    rep = check(root, log)
    d = R13.Data(_read(root / "industries.csv.gz"), _read(root / "factors.csv.gz"))
    res = {lvl: R13.run_trials(d, c) for lvl, c in R13.COSTS.items()}
    ev = R13.evaluate(d, res)
    stamp = (today or date.today()).isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    note = (f"Data: Ken French Data Library, 10 industry portfolios (value-weighted, daily) and the daily factors, "
            f"{d.days[0]}..{d.days[-1]}, {d.n:,} sessions; rows after 2024-01-31 dropped while parsing.")
    (out_dir / f"round13_{stamp}.md").write_text(R13.report_md(ev, note))
    (out_dir / f"round13_{stamp}.json").write_text(json.dumps(_jsonable(ev), indent=1))
    (out_dir / f"round13_data_check_{stamp}.md").write_text(check_md(rep))
    daily = pd.DataFrame({"date": [x.isoformat() for x in d.days], "rf": d.rf, "market": d.mkt})
    for n in R13.TRIALS:
        daily[n] = res["10bps"][n]["r"]
        daily[n + "_expo"] = res["10bps"][n]["expo"]
    with gzip.open(out_dir / f"round13_daily_{stamp}.csv.gz", "wt") as fh:
        daily.to_csv(fh, index=False)
    v = ev["verdict"]
    log(f"round13 R13: {'PASS' if v['pass'] else 'FAIL'} ({v['why']})")
    for n in R13.TRIALS:
        s = ev["trials"][n]["10bps"]["PASS"]
        log(f"round13 {n}: Sharpe {s['sharpe']:.2f}, CAGR {s['cagr']:.1%}, max DD {s['max_dd']:.1%} (PASS, 10 bps)")
    mk = ev["benchmarks"]["market"]["PASS"]
    log(f"round13 market: Sharpe {mk['sharpe']:.2f}, CAGR {mk['cagr']:.1%}, max DD {mk['max_dd']:.1%} (PASS)")
    log(f"report: {out_dir / f'round13_{stamp}.md'}")
    return ev, stamp


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def make_zips(root, out_dir, zip_dir, stamp=None, log=print):
    root, out_dir, zip_dir = Path(root), Path(out_dir), Path(zip_dir)
    stamp = stamp or max((p.stem.split("_")[-1] for p in out_dir.glob("round13_*.json")), default=None)
    if not stamp:
        raise Unusable("no round 13 report to zip: run first")
    res_files = sorted(out_dir.glob(f"round13*{stamp}*")) + sorted((out_dir / "logs").glob("r13_*.log"))
    data_files = sorted(p for p in root.rglob("*") if p.is_file() and not p.name.endswith(".tmp"))
    zr, zd = zip_dir / "sprint_results13.zip", zip_dir / "sprint_data13.zip"
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
    ap.add_argument("--data", default="data/r13")
    ap.add_argument("--out", default="data/sprint")
    ap.add_argument("--zip-dir", default=str(Path.home()))
    ap.add_argument("--from-dir", default=None, help="folder with the two zips downloaded by hand")
    x = ap.parse_args(argv)
    refuse_desk()
    if x.step in ("fetch", "all"):
        fetch(x.data, from_dir=x.from_dir)
    if x.step in ("check", "all"):
        print(check_md(check(x.data)))
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
        print(f"FAILED (network; re-running is safe): {e}")
        sys.exit(1)
