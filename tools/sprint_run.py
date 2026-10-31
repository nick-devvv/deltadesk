#!/usr/bin/env python3
"""tools/sprint_run.py - run a sprint spec (docs/research/SPRINT_PLAN.md) on cached Alpaca data. Backtest only:
no network, no orders, no broker code. Run it from a SEPARATE checkout (e.g. ~/sprint), never inside ~/desk.

  python3 tools/sprint_run.py sprint/specs/orb_exits_v1.json              # DEV (2024-08-01..2026-06-30)
  python3 tools/sprint_run.py SPEC --from 2025-01-02 --to 2025-03-31      # a sub-range of DEV
  python3 tools/sprint_run.py SPEC --locked L2 --frozen <sha256 of SPEC>  # ONLY for frozen, committed finalists

Writes data/sprint/runs_<host>.csv (one row per run, the columns of docs/research/sprint_runs.csv),
data/sprint/report_<date>.md and data/sprint/trades_<spec>_<date>.csv.gz, and prints a summary table.
Any date range touching L1 (2026-07-01..2026-10-30) or L2 (2024-02-01..2024-07-31) is refused unless --locked names
it and --frozen matches the spec file's sha256 as committed in git (no uncommitted edits).
"""
import argparse
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from sprint import periods, runner  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sprint backtest runner (cached data only; never trades)")
    ap.add_argument("spec")
    ap.add_argument("--from", dest="a")
    ap.add_argument("--to", dest="b")
    ap.add_argument("--locked", help="L1 or L2: only for frozen finalists (needs --frozen)")
    ap.add_argument("--frozen", help="sha256 of the spec file as committed")
    ap.add_argument("--data", default=None, help="cache root (default data/alpaca)")
    ap.add_argument("--chains-dir", default=None, help="logged chains for the spread model (default data/chains)")
    ap.add_argument("--out", default=None, help="output folder (default data/sprint)")
    ap.add_argument("--host", default=None)
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--random-paths", type=int, default=None)
    ap.add_argument("--fake-seeds", type=int, default=None)
    ap.add_argument("--no-robust", action="store_true", help="skip pass 2 (nudges, random entries, made-up levels)")
    ap.add_argument("--limit-days", type=int, default=None, help="first N sessions per symbol only (smoke test)")
    ap.add_argument("--trials", type=int, default=None, help="override the trial count for the deflated Sharpe")
    ap.add_argument("--spread-pct", type=float, default=None,
                    help="SENSITIVITY only: half-spread = this share of premium for every symbol (labeled; default = the "
                         "pre-registered model)")
    x = ap.parse_args(argv)
    a = date.fromisoformat(x.a) if x.a else None
    b = date.fromisoformat(x.b) if x.b else None
    if (a is None) != (b is None):
        ap.error("--from and --to go together")
    try:
        runner.run_spec(x.spec, a, b, x.locked, x.frozen, x.data, x.chains_dir, x.out, x.host, x.top_k, x.random_paths, x.fake_seeds,
                        not x.no_robust, x.limit_days, x.trials, spread_pct=x.spread_pct)
    except periods.LockedPeriod as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
