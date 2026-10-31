"""Sprint metrics and robustness helpers (sprint/report.py), the spec expansion and nudges (sprint/engine.py)."""
import json
from pathlib import Path

import pytest

from sprint import engine, report as R
from sprint.sim import ExitCfg

ROOT = Path(__file__).resolve().parents[1]


def T(day, pnl, pnl2=None, side="C", sym="SPY", idx=30, **kw):
    return dict({"day": day, "pnl": pnl, "pnl_2x": pnl if pnl2 is None else pnl2, "side": side, "symbol": sym, "entry_idx": idx,
                 "exit_reason": "LEVEL TARGET", "opt_mfe_pct": 0.1, "opt_mae_pct": -0.05, "stock_mfe": 0.3, "peak_level": None,
                 "minutes_held": 10, "pct_peak_kept": None, "planned_rr_opt": None, "actual_rr": None}, **kw)


def test_metrics_by_hand():
    tr = [T("2025-01-02", 30), T("2025-01-03", -10), T("2025-01-06", -20), T("2025-01-07", 50), T("2025-01-08", -10)]
    m = R.metrics(tr)
    assert m == {"trades": 5, "net": 40, "win_rate": 0.4, "avg_win": 40, "avg_loss": pytest.approx(-13.33), "expectancy": 8,
                 "profit_factor": pytest.approx(2.0), "max_dd": -30}
    s = R.summarize(tr)
    assert s["without_best5"]["trades"] == 0 and s["sides"]["C"]["trades"] == 5
    assert R.without_best(tr, 1) == {"net": -10, "expectancy": -2.5, "trades": 4}
    st = R.by_stretch(tr + [T("2024-09-03", 5), T("2026-02-02", -1)])
    assert st["2025"]["trades"] == 5 and st["Aug-Dec 2024"]["net"] == 5 and st["Jan-Jun 2026"]["net"] == -1


def test_pf_at_2x_slippage_and_peak_kept():
    tr = [T("2025-01-02", 30, 20, pct_peak_kept=0.5, peak_profit=60, planned_rr_opt=2.0, actual_rr=1.5),
          T("2025-01-03", -10, -16, pct_peak_kept=-0.5, peak_profit=20, planned_rr_opt=1.0, actual_rr=-1.0),
          T("2025-01-06", -5, -6, peak_profit=-1.0)]
    s = R.summarize(tr)
    assert s["profit_factor"] == 2.0 and s["pf_2x_slip"] == pytest.approx(20 / 22, abs=1e-3)
    assert s["pct_peak_kept"] == pytest.approx(20 / 80) and s["pct_peak_kept_median"] == 0.0
    assert s["planned_rr"] == 1.5 and s["actual_rr"] == 0.25


def test_day_block_bootstrap_is_deterministic_and_brackets_the_mean():
    tr = [T(f"2025-01-{d:02d}", p) for d, p in zip(range(2, 28), [10, -5, 7, -3, 12, -8, 4, 6, -2, 9] * 3)]
    ses = sorted({t["day"] for t in tr} | {"2025-01-29", "2025-01-30"})
    a, b = R.bootstrap_ci(tr, ses), R.bootstrap_ci(tr, ses)
    assert a == b and a[0] < sum(t["pnl"] for t in tr) / len(tr) < a[1]


def test_deflated_sharpe_falls_with_more_trials():
    s = [1.0, -0.5, 0.8, -0.2, 1.2, -0.9, 0.4, 0.6, -0.3, 0.9] * 6
    one = R.deflated_sharpe(s, 1, 0.0)
    many = R.deflated_sharpe(s, 200, 0.01)
    assert 0 < many < one <= 1


def test_random_skip_test():
    unf = [T(f"2025-02-{d:02d}", p) for d, p in zip(range(1, 21), [5, -5] * 10)]
    filt = [t for t in unf if t["pnl"] > 0]                   # a perfect filter: keeps only the winners
    r = R.random_skip_test(filt, unf, paths=200)
    assert r["skipped_days"] == 10 and r["p_value"] == 0.0
    assert R.random_skip_test(unf, unf)["skipped_days"] == 0


def test_csv_row_has_exactly_the_run_log_columns():
    head = (ROOT / "docs" / "research" / "sprint_runs.csv").read_text().splitlines()[0].split(",")
    assert R.COLUMNS == head
    run = {"run_id": "x-001", "entry": "orb15", "side": "both", "symbols": ("SPY", "QQQ"), "filters": (),
           "exit": ExitCfg(stop="level", tp="B", rr_min=2.0)}
    row = R.csv_row(run, R.summarize([T("2025-01-02", 5)]), "2026-10-31T00:00", "DEV", "MODELED-SPREAD")
    assert list(row) == head and row["tool"] == "DeskEngine" and row["symbol"] == "SPY+QQQ" and "R:R >= 2" in row["tp_rule"]


def test_shipped_spec_expands_to_the_documented_runs_and_nudges():
    spec = json.loads((ROOT / "sprint" / "specs" / "orb_exits_v1.json").read_text())
    runs = engine.expand(spec)
    assert len(runs) == 195 and len({engine.run_key(r) for r in runs}) == 195
    from collections import Counter
    assert Counter(r["block"] for r in runs) == {"plain": 3, "A_current_plan": 6, "B_level_target": 90, "C_half_and_trail": 6,
                                                 "E_rejection_or_next_level": 6, "trails_on_B_base": 84}
    b = next(r for r in runs if r["exit"].tp == "B" and r["exit"].rr_min == 2.0 and r["entry"] == "orb30" and r["exit"].tp_buffer == "0.05%")
    got = {(w, v) for w, v, _ in engine.nudges(b)}
    assert got == {("entry", "orb15"), ("entry", "orb60"), ("tp_buffer", "$0.03"), ("tp_buffer", "0.1atr"), ("rr_min", 1.5),
                   ("rr_min", 2.5), ("allout", "15:50")}
    keys = {engine.run_key(r) for r in runs}
    inspec = [w for w, v, nr in engine.nudges(b) if engine.run_key(nr) in keys]
    assert sorted(inspec) == ["entry", "entry", "rr_min", "rr_min", "tp_buffer", "tp_buffer"]     # only allout is extra
