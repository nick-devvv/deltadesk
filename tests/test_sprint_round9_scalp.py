"""Round 9 Part S (SPRINT_PLAN Amendment 13): the S1/S2 triggers on finished 1-minute bars (no look-ahead), the 6-cell grid
exits with the 5-minute max hold and the 15:25 all-out (a bar touching both = the stop), the cost fallback and P/L, the
first-half choice rule, the test bar's two-month blocks and random direction (deterministic), S-size, the underlying check,
and one position at a time on a synthetic DEV run. Synthetic data only."""
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import book, contracts, data, scalp as S
from sprint import spread as SP
from sprint.fills import OptionTape

DAY = date(2025, 3, 4)


def _ctx(path, **kw):
    return SS.make_ctx(DAY, path, {0: 1.0}, prior_days=12, **kw)[0]


# ---------------------------------------------------------------- triggers
def test_triggers_up_down_and_first_decision_bar():
    path = {0: 500.0, 10: 500.5, 20: 499.0, 30: 499.0}
    ctx = _ctx(path)
    tr = S.triggers(ctx)
    assert (10, 1) in tr and (20, -1) in tr
    assert all(i >= 5 for i, _ in tr) and all(i <= 349 for i, _ in tr)
    assert not any(i == 11 for i, _ in tr)                 # equal to the highest prior close is not above it
    assert S.side_of("scalp_trend", 1) == "C" and S.side_of("scalp_trend", -1) == "P"
    assert S.side_of("scalp_fade", 1) == "P" and S.side_of("scalp_fade", -1) == "C"


def test_triggers_need_the_five_prior_bars_and_no_look_ahead():
    path = {0: 500.0, 6: 501.0, 40: 500.0, 41: 502.0, 100: 495.0}
    a = S.triggers(_ctx(path))
    b = S.triggers(_ctx({**path, 60: 480.0, 61: 520.0, 200: 470.0}))
    assert [t for t in a if t[0] <= 59] == [t for t in b if t[0] <= 59]
    path2 = {0: 500.0, 6: 501.0}
    ctx = SS.make_ctx(DAY, path2, {0: 1.0}, prior_days=12, stock_bars={3: (500.0, 500.0, 500.0, float("nan"))})[0]
    ctx.c[3] = np.nan
    assert not any(i in (4, 5, 6, 7, 8) for i, _ in S.triggers(ctx))   # bar 3 missing: bars 4-8 lack five prior closes


# ---------------------------------------------------------------- the grid exits
def _tape(n=390, px=1.0, bars=None, no_print=()):
    o, h, l, c, v = (np.full(n, np.nan) for _ in range(5))
    for i in range(n):
        if i in no_print:
            continue
        o[i] = c[i] = px
        h[i], l[i] = px + 0.001, px - 0.001
        v[i] = 1
    for i, (oo, hh, ll, cc) in (bars or {}).items():
        o[i], h[i], l[i], c[i] = oo, hh, ll, cc
    return OptionTape("SPY250304C00500000", "C", 500.0, o, h, l, c, v)


def test_bar_touching_both_counts_as_the_stop():
    t = _tape(bars={102: (1.0, 1.04, 0.94, 1.0)})
    ex = S.scalp_exits(t, 100, 355, 1.00)
    for cid in ("t03_s05", "t03_s10"):
        assert ex[cid][2] == "FIXED STOP" if cid == "t03_s05" else ex[cid][2] == "FIXED TARGET"
    assert ex["t03_s05"][:2] == (102, pytest.approx(0.95)) and ex["t03_s10"][:2] == (102, pytest.approx(1.03))
    assert ex["t05_s05"][2] == "FIXED STOP"                # the stop at 102 comes before a +5% that never trades


def test_target_and_max_hold_exit_at_the_next_bar_open():
    t = _tape(bars={103: (1.0, 1.035, 0.999, 1.0), 105: (1.01, 1.02, 1.0, 1.0)})
    ex = S.scalp_exits(t, 100, 355, 1.00)
    assert ex["t03_s05"] == (103, pytest.approx(1.03), "FIXED TARGET", False)
    assert ex["t05_s05"] == (105, pytest.approx(1.01), "MAX HOLD", False)     # bars 100-104 watched, out at 105's open
    t2 = _tape(no_print=(105, 106))
    assert S.scalp_exits(t2, 100, 355, 1.00)["t08_s10"][:3] == (107, pytest.approx(1.0), "MAX HOLD")
    t3 = _tape(bars={106: (1.0, 1.2, 0.5, 1.0)})                              # after the hold window: ignored
    assert S.scalp_exits(t3, 100, 355, 1.00)["t03_s05"][2] == "MAX HOLD"
    t4 = _tape(bars={101: (0.90, 0.91, 0.89, 0.9)})                           # gapped through the stop: fills at the open
    assert S.scalp_exits(t4, 100, 355, 1.00)["t03_s05"][:3] == (101, pytest.approx(0.90), "FIXED STOP")


def test_all_out_at_1525_and_void():
    t = _tape()
    ex = S.scalp_exits(t, 352, 355, 1.00)
    assert ex["t03_s05"][:3] == (355, pytest.approx(1.0), "ALL OUT")
    t2 = _tape(no_print=tuple(range(355, 390)))
    assert S.scalp_exits(t2, 352, 355, 1.00)["t03_s05"] is None


# ---------------------------------------------------------------- costs
def test_cost_fallback_measured_cells_and_pnl():
    sp = S.ScalpSpread()
    assert sp.half_spread("SPY", 2.0) == (0.02, "MODELED-SPREAD")
    assert sp.half_spread("SPY", 10.0) == (pytest.approx(0.05), "MODELED-SPREAD")
    m = S.ScalpSpread({("SPY", SP._pb(2.0), SP._tb(100)): 0.015, ("SPY", SP._pb(2.0), None): 0.025}, {"SPY": {"days": 5, "rows": 900}})
    assert m.half_spread("SPY", 2.0, 100) == (0.015, "MEASURED-SPREAD")
    assert m.half_spread("SPY", 2.0, 5) == (0.025, "MEASURED-SPREAD")
    assert m.half_spread("QQQ", 2.0, 100) == (0.02, "MODELED-SPREAD")
    assert "ASSUMPTION" in m.describe() and "max($0.02" in sp.describe()
    assert S.leg_pnl(1.00, 0.02, 1.03, 0.02, False) == pytest.approx((1.01 - 1.02) * 100 - 1.30)
    assert S.leg_pnl(1.00, 0.02, 0.95, 0.02, True, k=2) == pytest.approx((0.91 - 1.04) * 100 - 1.30)
    assert S.leg_pnl(1.00, 0.02, 0.95, 0.02, True, k=2, desk_stop=True) == pytest.approx((0.87 - 1.04) * 100 - 1.30)
    assert S.leg_pnl(1.00, 0.02, 1.03, 0.02, False, fee=S.RH_FEE) == pytest.approx((1.01 - 1.02) * 100 - 0.06)


# ---------------------------------------------------------------- the choice and the test
def _st(n, pf):
    return {"trades": n, "pf": pf}


def test_choice_rule_ties_and_the_200_trade_floor():
    cells = [("t03_s05", 0.05, 0.03, _st(250, 1.3)), ("t05_s05", 0.05, 0.05, _st(260, 1.3)), ("t08_s10", 0.10, 0.08, _st(199, 9.0)),
             ("t03_s10", 0.10, 0.03, _st(260, 1.3))]
    assert S.choose_cell(cells) == "t05_s05"               # equal PF: more trades; then the smaller stop
    cells.append(("t08_s05", 0.05, 0.08, _st(260, 1.3)))
    assert S.choose_cell(cells) == "t05_s05"               # same stop and trades: the smaller target
    cells.append(("t03_s05b", 0.05, 0.03, _st(201, math.inf)))
    assert S.choose_cell(cells) == "t03_s05b"
    assert S.choose_cell([("x", 0.05, 0.03, _st(199, 2.0))]) is None


def _frame(n=240, seed=1, edge=3.0):
    rng = np.random.default_rng(seed)
    days = book.sessions_between(*S.TEST)
    rows = []
    for k in range(n):
        p = float(rng.normal(edge, 10))
        rows.append({"day": days[(k * 7) % len(days)], "entry_idx": 100, "symbol": "SPY", "pnl": p, "pnl_2x": p - 2, "pnl_2x_desk": p - 3,
                     "pnl_rh": p + 1.2, "debit": 250.0, "opp_pnl": float(rng.normal(-edge, 10)), "opp_pnl_2x": 0.0,
                     "measured_spread": False, "trig": 1 if k % 2 else -1, "day_dir": 1, "rvol": 1.1 if k % 3 else 0.9})
    return pd.DataFrame(rows).sort_values(["day", "entry_idx"], kind="stable").reset_index(drop=True)


def test_test_bar_blocks_and_random_direction_is_deterministic():
    g = _frame()
    a, b = S.test_bar(g), S.test_bar(g)
    assert a["random_p"] == b["random_p"] and a["random_trades"] == 240 and len(a["checks"]) == 5
    assert set(a["blocks"]) == {x[0] for x in S.BLOCKS} and sum(v["trades"] for v in a["blocks"].values()) == 240
    assert a["pass"] and a["random_p"] < 0.05
    g2 = g.copy()
    g2.loc[:9, "opp_pnl"] = np.nan
    assert S.test_bar(g2)["random_left_out"] == 10
    assert not S.test_bar(_frame(n=150))["pass"]


def test_s_size_rule_and_account_view():
    g = _frame(n=12)
    n = S.sizes(g)
    exp = np.where((g["trig"] == g["day_dir"]) & (g["rvol"] >= 1.06), 5, 3)
    assert np.array_equal(n, exp)
    g0 = g.copy()
    g0["day_dir"] = 0
    assert (S.sizes(g0) == 3).all()
    sz = S.s_size(g)
    assert sz["five"] + sz["three"] == 12 and sz["pnl"] == pytest.approx(float((g["pnl"] * n).sum()), abs=0.01)
    assert sz["account"]["debit_pct_3000"]["max"] == pytest.approx(250 * 5 / 3000 * 100, abs=0.1)
    assert S.worst_streak([5, -2, -3, 4, -10, 1]) == -10 and S.worst_streak([1, 2]) == 0.0
    assert S.max_dd(np.array([10.0, -5, -20, 30, -1])) == pytest.approx(-25.0)
    bad = g.copy()
    bad["pnl"] = -400.0
    assert not S.s_size(bad)["pass"]


# ---------------------------------------------------------------- the underlying check
def test_underlying_one_position_and_five_minute_move():
    path = {0: 500.0, 10: 501.0, 11: 501.5, 12: 502.0, 13: 502.5, 14: 503.0, 15: 503.5, 16: 504.0, 30: 499.0}
    ctx = _ctx(path)
    rows = S.underlying_day(ctx)
    assert rows[0][1] == 1                                   # the up trigger at bar 10
    e, x = 11, 16                                           # entry at bar 11's open, out at bar 16's open
    assert rows[0][0] == pytest.approx((ctx.o[x] / ctx.o[e] - 1) * 1e4)
    trig = S.triggers(ctx)
    taken = [j for j, _ in trig if j in (10, 30)]
    assert len(rows) <= len(trig) and taken == [10, 30]
    u = S._ustats(np.array([5.0, -2.0, 3.0, 1.0]))
    assert u == S._ustats(np.array([5.0, -2.0, 3.0, 1.0])) and u["hit_rate"] == 0.75 and u["mean_bps"] == 1.75


# ---------------------------------------------------------------- the shared pick equals contracts.pick
def test_pick_both_equals_contracts_pick(tmp_path):
    day = date(2025, 3, 4)
    SS.write_cache(tmp_path, "SPY", [day], px0=500.0, seed=6)
    ser = data.Series("SPY", data.read_stock("SPY", day, day, tmp_path))
    for sp in (S.ScalpSpread(), S.ScalpSpread({("SPY", 2, 1): 0.30}, {"SPY": {"days": 1, "rows": 60}})):
        ctx = data.DayContext(ser, day, data.read_option_day("SPY", day, tmp_path), sp)
        n = 0
        for i in range(5, 350, 7):
            for side in ("C", "P"):
                both = S.pick_both(ctx, side, i)
                for rule in S.CONTRACTS:
                    a, b = both[rule], contracts.pick(ctx, side, i, rule)
                    assert (a[0] is b[0]) and a[1] == b[1]
                    n += a[0] is not None
        assert n > 0


# ---------------------------------------------------------------- one position at a time on a synthetic run
def test_run_one_position_per_cell_and_coverage(tmp_path):
    days = [date(2025, 3, 3), date(2025, 3, 4), date(2025, 3, 5)]
    pre = SS.weekdays(date(2025, 2, 10), 15)
    SS.write_cache(tmp_path, "SPY", pre + days, px0=500.0, seed=4)
    ser = data.Series("SPY", data.read_stock("SPY", pre[0], days[-1], tmp_path))
    col = S.run({"SPY": ser}, S.ScalpSpread(), a=days[0], b=days[-1], root=tmp_path)
    df = col.frame()
    assert len(df) and set(df["cell"].astype(str)) <= set(S.CELL_IDS)
    for (sig, con, cell, d), g in df.groupby(["signal", "contract", "cell", "day"], observed=True):
        g = g.sort_values("signal_idx")
        assert (g["signal_idx"].to_numpy()[1:] >= g["exit_idx"].to_numpy()[:-1]).all()
        assert (g["exit_idx"] - g["entry_idx"] <= 6).all() or (g["exit_reason"].astype(str) != "MAX HOLD").all()
    assert set(df["exit_reason"].astype(str)) <= set(S.REASONS)
    t1 = df[(df["signal"] == "scalp_trend")]
    assert ((t1["trig"] > 0) == (t1["side"] == "C")).all()
    t2 = df[(df["signal"] == "scalp_fade")]
    assert ((t2["trig"] > 0) == (t2["side"] == "P")).all()
    cov = S.coverage(col)
    assert cov["SPY"]["days"] == 3 and cov["SPY"]["picked"] > 0
    with pytest.raises(Exception):
        S.run({"SPY": ser}, S.ScalpSpread(), a=date(2026, 6, 1), b=date(2026, 7, 2), root=tmp_path)
