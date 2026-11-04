#!/usr/bin/env python3
"""tools/sprint_r15.py - round 15 on Chart's computer. Uses round 14's data files (tools/sprint_r14.py fetch: only the
segments that avoid L1/L2), runs the 5 pre-registered trials (sprint/r15.py; SPRINT_PLAN "Round 15 pre-registration").
Research only; no orders, no keys; never ~/desk.
  python3 tools/sprint_r15.py fetch | run | all
  python3 tools/sprint_r15.py confirm --locked L1 --frozen <sha256 of docs/research/R15_L1_SPEC.md>   (ONE time, Nick's go only)
Exit codes: 0 done; 1 network; 2 a locked period refused; 3 a missing file or unusable data.
"""
import argparse
import gzip
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
import sprint_r12 as T12  # noqa: E402
import sprint_r13 as T13  # noqa: E402
import sprint_r14 as T14  # noqa: E402
from sprint import periods  # noqa: E402
from sprint import r12daily as R12  # noqa: E402
from sprint import r14 as R14  # noqa: E402
from sprint import r15 as R15  # noqa: E402

SPEC = HERE / "docs" / "research" / "R15_L1_SPEC.md"
CONFIRM_FROM = date(2024, 8, 1)


def run(root, out_dir, log=print, today=None, n_luck=None, boot_draws=None):
    root, out_dir = Path(root), Path(out_dir)
    T14.check(root, log)
    m, _, src, _ = T14.load(root)
    ev, series = R15.evaluate(m, n_luck, boot_draws)
    stamp = (today or date.today()).isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    note = f"Data: Yahoo daily bars, {m.days[0]}..{m.days[-1]} (L2 cut out, ends before L1), cash {src}."
    (out_dir / f"round15_{stamp}.md").write_text(R15.report_md(ev, note))
    (out_dir / f"round15_{stamp}.json").write_text(json.dumps(T13._jsonable(ev), indent=1))
    daily = pd.DataFrame({"date": [x.isoformat() for x in m.days], "cash": m.cash, **{n: series[n] for n in R15.TRIALS}})
    with gzip.open(out_dir / f"round15_daily_{stamp}.csv.gz", "wt") as fh:
        daily.to_csv(fh, index=False)
    for n, t in ev["trials"].items():
        s = t["stats"]
        failed = ", ".join(k.split(" ")[0] for k, v in t["items"].items() if not v)
        log(f"round15 {n}: {'PASS' if t['pass'] else 'FAIL'} p {t['p']:.4f} Sharpe {s['sharpe']:.2f} CAGR {s['cagr']:.1%} "
            f"max DD {s['max_dd']:.1%}" + (f" (failed items: {failed})" if failed else ""))
    log(f"report: {out_dir / f'round15_{stamp}.md'}")
    return ev, stamp


def confirm(root, out_dir, locked, frozen, history=None, log=print, today=None, spec=SPEC):
    l1 = periods.LOCKED["L1"]
    periods.guard(l1[0], l1[1], locked=locked, frozen=frozen, spec_path=spec)
    root, out_dir = Path(root), Path(out_dir)
    history = history or T12.yahoo_history
    frames = {}
    for s in R14.SYMBOLS:
        p = root / f"{s}.csv.gz"
        if not p.exists():
            df = history(s, CONFIRM_FROM, l1[1])
            if df is None or not len(df):
                raise ConnectionError(f"{s}: no rows")
            T12._write(p, df[(df.index >= pd.Timestamp(CONFIRM_FROM)) & (df.index <= pd.Timestamp(l1[1]))])
            log(f"  {s}: {len(df)} rows")
        frames[s] = T12._read(p)
    cp = root / "IRX.csv.gz"
    if not cp.exists():
        T12._write(cp, history("^IRX", CONFIRM_FROM, l1[1])[["close"]].rename(columns={"close": "rate"}))
    m = R12.Market(frames, T12._read(cp)["rate"])
    if m.seg.max() != 0:
        raise T12.Unusable("the DEV + L1 bars have a gap: they must be one segment")
    c = R15.confirm(m, l1)
    c["spec_sha256"] = frozen
    stamp = (today or date.today()).isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"round15_L1_{stamp}.md").write_text(R15.confirm_md(c))
    (out_dir / f"round15_L1_{stamp}.json").write_text(json.dumps(T13._jsonable(c), indent=1))
    for k, r in c["rules"].items():
        log(f"L1 {k}: {r.get('verdict', 'benchmark')} return {r['total']:.1%} excess {r['excess_over_cash']:.1%} max DD {r['max_dd']:.1%}")
    return c


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("step", choices=["fetch", "run", "all", "confirm"])
    ap.add_argument("--data", default="data/r14")
    ap.add_argument("--l1-data", default="data/r15_l1")
    ap.add_argument("--out", default="data/sprint")
    ap.add_argument("--locked")
    ap.add_argument("--frozen")
    x = ap.parse_args(argv)
    T12.refuse_desk()
    if x.step == "confirm":
        confirm(x.l1_data, x.out, x.locked, x.frozen)
        return 0
    if x.step in ("fetch", "all"):
        T14.fetch(x.data)
    if x.step in ("run", "all"):
        run(x.data, x.out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except periods.LockedPeriod as e:
        print(f"LOCKED: {e}")
        sys.exit(2)
    except (T12.Unusable, T13.Unusable) as e:
        print(f"STOP: {e}")
        sys.exit(3)
    except ConnectionError as e:
        print(f"FAILED (network; re-running resumes): {e}")
        sys.exit(1)
