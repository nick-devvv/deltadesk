"""Round 9 readouts (sprint/round9.py): Part H runs the factory procedure unchanged on share trades (a planted 2016-2019 edge
is found and checked on the holdouts; 2020+ data never changes the rule), share entry features are stamped at the decision
bar from cached bars, the account view's arithmetic, the book's "adds steadiness" rule (correlation with FIN-H below 0.3 over
the sessions both could trade), the trial count (203) and the deflated Sharpe's N. Synthetic data only."""
import math
from datetime import date

import numpy as np
import pytest

import sprint_synth as SS
from sprint import book, data, factory, features, round9 as R9


# ---------------------------------------------------------------- trials
def test_trials_are_203_and_the_dsr_uses_run_logs_plus_203():
    assert sum(R9.TRIALS.values()) == 203 == R9.ROUND9
    assert R9.TRIALS["S (2 signals x 2 contracts x 6 cells + 2 underlying checks + 2 sized variants)"] == 28
    t = R9.trials(1234)
    assert t["total_for_dsr"] == 1437 and "12 strategies" in t["h_note"] and "written count is 11" in t["h_note"]
    days = book.sessions_between("2024-08-01", "2026-06-30")
    rng = np.random.default_rng(1)
    var = {f"v{k}": [{"day": d, "pnl": float(rng.normal(0.5 * k, 10)), "pnl_2x": 0.0} for d in days[::2]] for k in range(4)}
    tab, sv, n = R9.dsr_table(var, 1234, days)
    tab2, _sv, n2 = R9.dsr_table(var, 1234, days, extra=15)
    assert n == 1437 and n2 == 1452 and sv > 0
    assert all(tab2[k] <= tab[k] for k in tab if tab[k] is not None)
    assert len(R9.H_STRATEGIES) == 12 and R9.H_WRITTEN_COUNT == 11


# ---------------------------------------------------------------- the account view
def test_account_view_shares_arithmetic():
    days = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-02-03"]
    rows = [{"day": "2025-01-02", "pnl": 100.0, "notional": 10_000.0}, {"day": "2025-01-03", "pnl": -300.0, "notional": 10_000.0},
            {"day": "2025-01-06", "pnl": -60.0, "notional": 5_000.0}, {"day": "2025-02-03", "pnl": 500.0, "notional": 10_000.0}]
    av = R9.account_view(rows, "shares", days)
    assert av["per_1000"]["total"] == pytest.approx(10 - 30 - 12 + 50) and av["per_1000"]["per_trade"] == pytest.approx(4.5)
    p = av["pre_registered_size"]
    assert p["max_dd"] == pytest.approx(-360.0) and p["max_dd_pct_3000"] == pytest.approx(-12.0)
    assert p["worst_month"] == "2025-01" and p["worst_month_net"] == pytest.approx(-260.0) and p["worst_month_pct_3000"] == pytest.approx(-8.7, abs=0.05)
    a3 = av["at_3000_notional"]
    assert a3["total"] == pytest.approx(30 - 90 - 36 + 150) and a3["max_dd"] == pytest.approx(-126.0) and a3["max_dd_pct_3000"] == pytest.approx(-4.2)


def test_account_view_options_debit_and_size():
    days = ["2025-03-03", "2025-03-04"]
    rows = [{"day": "2025-03-03", "pnl": 30.0, "debit": 300.0}, {"day": "2025-03-04", "pnl": -60.0, "debit": 600.0},
            {"day": "2025-03-04", "pnl": 5.0, "debit": None}]
    av = R9.account_view(rows, "option", days)
    assert av["per_1000"]["total"] == pytest.approx(100 - 100) and av["per_1000"]["trades_with_capital"] == 2
    assert av["debit_pct_3000"] == {"median": 15.0, "p90": 19.0, "max": 20.0, "over_100": 0}
    av5 = R9.account_view(rows[:2], "option", days, size=[5, 3])
    assert av5["pre_registered_size"]["max_dd"] == pytest.approx(-180.0) and av5["debit_pct_3000"]["max"] == pytest.approx(60.0)
    mixed = R9.account_view([{"day": "2025-03-03", "pnl": 10.0, "notional": 10_000.0}, rows[0]], "mixed", days)
    assert mixed["per_1000"]["total"] == pytest.approx(1 + 100)


# ---------------------------------------------------------------- the book's steadiness rule
def test_steadiness_uses_the_sessions_both_could_trade():
    hist = book.sessions_between("2016-01-04", "2024-01-31")
    dev = book.sessions_between("2024-08-01", "2026-06-30")
    rng = np.random.default_rng(2)
    fin = [{"day": d, "pnl": float(rng.normal(0, 10)), "pnl_2x": 0.0} for d in hist + dev]
    twin = [dict(r, pnl=r["pnl"] * 2 + 1) for r in fin if r["day"] >= "2024-08-01"]
    indep = [{"day": d, "pnl": float(rng.normal(0, 10)), "pnl_2x": 0.0} for d in hist[::3] + dev[::3]]
    st = R9.steadiness({"FIN-H": fin, "twin": twin, "indep": indep}, {"FIN-H": "hist+dev", "twin": "dev", "indep": "hist+dev"})
    assert st["twin"]["sessions"] == len(dev) and st["twin"]["corr_finh"] > 0.99 and not st["twin"]["adds_steadiness"]
    assert st["indep"]["sessions"] == len(hist) + len(dev) and st["indep"]["adds_steadiness"]


# ---------------------------------------------------------------- Part H
def _share_rows(name, seed=3, edge=True):
    rng = np.random.default_rng(seed)
    hist = book.sessions_between("2016-01-04", "2024-01-31")
    dev = book.sessions_between("2024-08-01", "2026-06-30")
    rows = []
    for src, days in (("HIST", hist), ("DEV", dev)):
        for d in days[::2]:
            rv = float(rng.uniform(0.5, 2.0))
            p = float(rng.normal(25.0 if (edge and rv > 1.5) else -6.0, 20.0))
            r = {"variant": name, "symbol": "SPY", "day": d, "_src": src, "side": "L", "entry_time": "10:00", "exit_time": "15:59",
                 "pnl": round(p, 2), "pnl_2x": round(p - 2, 2), "decision_idx": 29}
            r.update({k: float(rng.normal()) for k in features.FEATURES})
            r["f_rvol"], r["f_minute"] = rv, 30
            rows.append(r)
    return rows


def test_part_h_runs_the_factory_procedure_on_share_trades():
    by = {"noise_sh": _share_rows("noise_sh"), "last30": _share_rows("last30", seed=4, edge=False)}
    res, sleeves, var = R9.part_h(by)
    s = res["strategies"]["noise_sh"]
    assert s["rule"]["rule"]["feature"] == "f_rvol" and s["rule"]["rule"]["side"] == "top"
    assert s["model_check"].startswith("shares") and "seen_before" not in s
    assert res["order"] == list(R9.H_STRATEGIES) and res["written_count"] == 11
    assert "ind_rsi" in res["strategies"] and res["strategies"]["ind_rsi"]["verdict"] == "none"
    if s["verdict"] != "none":
        assert "noise_sh" in sleeves
    assert any(k.startswith("H noise_sh f_rvol") for k in var) and "H noise_sh unfiltered" in var
    changed = [dict(r) for r in by["noise_sh"]]
    for r in changed:
        if r["day"] >= "2020-01-01":
            r["f_rvol"] = 0.1
            r["pnl"] = -50.0
    res2, _, _ = R9.part_h({"noise_sh": changed})
    assert res2["strategies"]["noise_sh"]["rule"]["rule"] == s["rule"]["rule"]       # 2020+ data never changes the rule


def test_share_features_are_stamped_at_the_decision_bar(tmp_path):
    day = date(2025, 3, 12)
    pre = SS.weekdays(date(2025, 2, 10), 23)
    SS.write_stock_only(tmp_path, "SPY", [d for d in pre if d <= day], px0=500.0, seed=9)
    ser = data.Series("SPY", data.read_stock("SPY", pre[0], day, tmp_path))
    rows = [{"variant": "noise_sh", "symbol": "SPY", "day": day.isoformat(), "_src": "DEV", "side": "L", "decision_idx": 59},
            {"variant": "noise_sh", "symbol": "SPY", "day": day.isoformat(), "_src": "DEV", "side": "S", "decision_idx": 59}]
    n = R9.stamp_share_features(rows, {("DEV", "SPY"): ser}, {"VIXY_D": None})
    ctx = data.DayContext(ser, day, {}, None, aux={"VIXY_D": None})
    want = features.entry_features(ctx, 59, "C")
    assert n == 2 and rows[0]["f_minute"] == 60 and rows[0]["f_day_ret"] == want["f_day_ret"]
    assert rows[1]["f_day_ret"] == pytest.approx(-want["f_day_ret"]) and rows[0]["f_rvol"] == rows[1]["f_rvol"]
