#!/usr/bin/env python3
"""tools/sprint_r14.py - round 14 on Chart's computer: Yahoo daily bars for 21 ETFs (tools/sprint_r12.py's fetch: only the
two segments that avoid L1/L2 are requested), Yahoo ^IRX / FRED DTB3 for cash, the Ken French files (tools/sprint_r13.py's
fetch: rows after 2024-01-31 dropped while parsing), a data check, the 12 pre-registered trials and their luck checks
(sprint/r14.py; SPRINT_PLAN "Round 14 pre-registration") and the zips. Research only; no orders, no keys; never ~/desk.
  python3 tools/sprint_r14.py fetch | check | run | zip | all
Exit codes: 0 done; 1 failed (network or crash; re-running resumes); 2 a locked period; 3 a missing file or unusable data.
"""
import argparse
import gzip
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
import sprint_r12 as T12  # noqa: E402
import sprint_r13 as T13  # noqa: E402
from sprint import periods  # noqa: E402
from sprint import r12daily as R12  # noqa: E402
from sprint import r13ff as R13  # noqa: E402
from sprint import r14 as R14  # noqa: E402

Unusable = T12.Unusable


def fetch(root, history=None, get=None, french_get=None, log=print):
    T12.check_segments()
    history = history or T12.yahoo_history
    get = get or T12.http_get
    root = Path(root)

    def yahoo(s, a, b):
        try:
            return history(s, a, b)
        except ConnectionError:
            raise
        except Exception as e:  # noqa: BLE001 - yfinance raises its own types
            raise ConnectionError(f"yahoo {s} {a}..{b}: {type(e).__name__}: {e}") from e

    st = {"yahoo": {}, "cash": {}}
    for s in R14.SYMBOLS:
        st["yahoo"][s] = T12.fetch_one(root / "yahoo" / f"{s}.csv.gz", lambda a, b, s=s: yahoo(s, a, b), False, log)
    try:
        st["cash"]["DTB3"] = T12.fetch_one(root / "cash" / "DTB3.csv.gz",
                                           lambda a, b: T12.parse_fred(get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3&cosd={a}&coed={b}")).to_frame("rate"),
                                           False, log)
    except ConnectionError as e:
        st["cash"]["DTB3"] = f"unavailable: {e}"
        log(f"  FRED DTB3 unavailable ({e}); using Yahoo ^IRX")
    st["cash"]["IRX"] = T12.fetch_one(root / "cash" / "IRX.csv.gz", lambda a, b: yahoo("^IRX", a, b)[["close"]].rename(columns={"close": "rate"}), False, log)
    st["french"] = T13.fetch(root / "french", get=french_get or T13.http_get, log=log)
    (root / "fetch_status.json").write_text(json.dumps(st, indent=1, default=str))
    return st


def load(root):
    root = Path(root)
    frames = {}
    for s in R14.SYMBOLS:
        p = root / "yahoo" / f"{s}.csv.gz"
        if p.exists():
            frames[s] = T12._read(p)
    missing = [s for s in R14.SYMBOLS if s not in frames]
    if missing:
        raise Unusable(f"missing Yahoo files: {missing}")
    cash, src = T12.load_cash(root)
    if cash is None:
        raise Unusable("no cash series")
    m = R12.Market(frames, cash)
    d = R13.Data(T13._read(root / "french" / "industries.csv.gz"), T13._read(root / "french" / "factors.csv.gz"))
    return m, d, src, frames


def check(root, log=print):
    root = Path(root)
    m, d, src, frames = load(root)
    cal = frames["SPY"].index
    rep = {"cash": src, "symbols": {}, "french": T13.check(root / "french", log)}
    for s, f in frames.items():
        mine = cal[(cal >= f.index[0]) & (cal <= f.index[-1])]
        r = f["adj_close"].pct_change()
        rep["symbols"][s] = {"rows": int(len(f)), "first": str(f.index[0].date()), "last": str(f.index[-1].date()),
                             "missing_sessions": int(len(mine.difference(f.index))),
                             "extreme_moves": [f"{x.date()} {v:+.1%}" for x, v in r[r.abs() > 0.25].items()]}
        hit = periods.overlaps(f.index[0].date(), f.index[-1].date())
        locked = [x for x in f.index if any(a <= x.date() <= b for a, b in periods.LOCKED.values())]
        if locked:
            raise periods.LockedPeriod(f"{s} has {len(locked)} rows inside {', '.join(hit)}")
    late = [s for s in R14.MA_ASSETS if rep["symbols"][s]["first"] > "2007-01-31"]
    rep["problems"] = [f"{s} starts after 2007-01 (needs 12 months before PASS)" for s in late]
    (root / "check.json").write_text(json.dumps(rep, indent=1, default=str))
    if rep["problems"]:
        raise Unusable("; ".join(rep["problems"]))
    return rep


def check_md(rep):
    L = ["# Round 14 data check", "", f"Cash: {rep['cash']}. Problems: {', '.join(rep['problems']) or 'none'}.", "",
         "| Symbol | Rows | First | Last | Missing sessions | Moves over 25% |", "|---|---|---|---|---|---|"]
    for s, i in rep["symbols"].items():
        L.append(f"| {s} | {i['rows']} | {i['first']} | {i['last']} | {i['missing_sessions']} | {len(i['extreme_moves'])} |")
    L += ["", T13.check_md(rep["french"])]
    return "\n".join(L) + "\n"


def run(root, out_dir, log=print, today=None, n_luck=None, boot_draws=None):
    root, out_dir = Path(root), Path(out_dir)
    rep = check(root, log)
    m, d, src, _ = load(root)
    ev, etf, fr = R14.evaluate(m, d, n_luck, boot_draws)
    stamp = (today or date.today()).isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    note = (f"Data: Yahoo daily bars for {len(R14.SYMBOLS)} ETFs, {m.days[0]}..{m.days[-1]} (L2 cut out, ends before L1), cash {src}; "
            f"Ken French industries {d.days[0]}..{d.days[-1]}.")
    (out_dir / f"round14_{stamp}.md").write_text(R14.report_md(ev, note))
    (out_dir / f"round14_{stamp}.json").write_text(json.dumps(T13._jsonable(ev), indent=1))
    (out_dir / f"round14_data_check_{stamp}.md").write_text(check_md(rep))
    daily = pd.DataFrame({"date": [x.isoformat() for x in m.days], "cash": m.cash, "SPY": R14.cc_ret(m, "SPY")})
    for n in R14.ETF_TRIALS:
        daily[n] = etf[n]["r"]
    with gzip.open(out_dir / f"round14_daily_{stamp}.csv.gz", "wt") as fh:
        daily.to_csv(fh, index=False)
    fd = pd.DataFrame({"date": [x.isoformat() for x in d.days], "rf": d.rf, "market": d.mkt, "B1": fr["B1"]["r"], "B2": fr["B2"]["r"]})
    with gzip.open(out_dir / f"round14_french_daily_{stamp}.csv.gz", "wt") as fh:
        fd.to_csv(fh, index=False)
    for n in R14.TRIALS:
        t = ev["etf"][n] if n in R14.ETF_TRIALS else ev["french"][n]
        s = t["stats"]
        failed = ", ".join(k for k, v in t["items"].items() if not v)
        log(f"round14 {n}: {'PASS' if t['pass'] else 'FAIL'} Sharpe {s['sharpe']:.2f} CAGR {s['cagr']:.1%} max DD {s['max_dd']:.1%}"
            + (f" (failed: {failed})" if failed else ""))
    log(f"report: {out_dir / f'round14_{stamp}.md'}")
    return ev, stamp


def make_zips(root, out_dir, zip_dir, stamp=None, log=print):
    root, out_dir, zip_dir = Path(root), Path(out_dir), Path(zip_dir)
    stamp = stamp or max((p.stem.split("_")[-1] for p in out_dir.glob("round14_2*.json")), default=None)
    if not stamp:
        raise Unusable("no round 14 report to zip: run first")
    res = sorted(out_dir.glob(f"round14*{stamp}*")) + sorted((out_dir / "logs").glob("r14_*.log"))
    dat = sorted(p for p in root.rglob("*") if p.is_file() and not p.name.endswith(".tmp"))
    out = []
    for name, files, base in (("sprint_results14.zip", res, out_dir.parent.parent), ("sprint_data14.zip", dat, root.parent.parent)):
        z = zip_dir / name
        T12_zip(z, files, base)
        log(f"zip: {z} ({len(files)} files, {z.stat().st_size / 1e6:.1f} MB)")
        out.append(z)
    return out


def T12_zip(zpath, files, base):
    import zipfile
    man = {str(p): T12.sha256(p) for p in files}
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            try:
                arc = p.resolve().relative_to(Path(base).resolve())
            except ValueError:
                arc = p.name
            z.write(p, str(arc))
        z.writestr("MANIFEST_sha256.json", json.dumps(man, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("step", choices=["fetch", "check", "run", "zip", "all"])
    ap.add_argument("--data", default="data/r14")
    ap.add_argument("--out", default="data/sprint")
    ap.add_argument("--zip-dir", default=str(Path.home()))
    x = ap.parse_args(argv)
    T12.refuse_desk()
    if x.step in ("fetch", "all"):
        fetch(x.data)
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
    except (Unusable, T13.Unusable) as e:
        print(f"STOP: {e}")
        sys.exit(3)
    except ConnectionError as e:
        print(f"FAILED (network; re-running resumes): {e}")
        sys.exit(1)
