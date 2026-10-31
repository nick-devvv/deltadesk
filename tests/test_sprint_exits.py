"""Sprint exit variants (sprint/sim.py) on small synthetic paths with hand-checked P/L: plan A (T1, breakeven, if-flat,
time-of-day tightening), B, C, D, E, trails (breakeven, ladders, giveback, 1m pivots, level, VWAP), all-out 15:25 vs
15:50, the R:R minimum, and the rule that crossing into a new window never loosens anything."""
from datetime import date

import pytest

import sprint_synth as SS
from sprint import bs, fills, sim
from sprint.entries import Signal
from sprint.sim import ExitCfg, simulate

DAY = date(2025, 3, 12)
HS = 0.01
F = fills.FEE / 100
K = 500.0


def opt_px(S, i, iv=0.2):
    return round(bs.price(S, K, bs.t_years(390 - i - 1), iv, "C"), 2)


def go(ctx, tape, cfg, idx=20, price=500.0, invalid=None, px=None):
    px = px if px is not None else tape.last_close(idx)
    iv = bs.implied_vol(px, price, K, bs.t_years(390 - idx - 1), "C") or 0.2
    s = Signal("orb15", "SPY", DAY, "C", idx, price, invalid, {})
    return simulate(ctx, s, cfg, None, tape, {"symbol": tape.symbol, "px": px, "iv": iv, "delta": 0.5})


def leg_pnl(e_basis, legs):
    return fills.pnl(e_basis, HS, [(q, b, HS, st) for q, b, st in legs], 1)


def cost(p):
    return p + HS + F


def trig(C, g):
    return C * (1 + g) + HS + F


# ---------------------------------------------------------------- plan A and the time table
def test_plan_a_breakeven_then_back_to_cost_is_a_zero_trade():
    C = cost(1.0)
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 23: 1.15, 24: 1.04, 25: 0.9}, opt_hl={24: (1.045, 0.99)})
    t = go(ctx, tape, ExitCfg(stop="premium", tp="A", time="a"))
    assert t["exit_reason"] == "BREAKEVEN STOP" and t["exit_idx"] == 24
    assert t["exit_basis"] == pytest.approx(trig(C, 0.0))
    assert t["pnl"] == pytest.approx(0.0, abs=1e-6)                          # fill + costs exactly


def test_plan_a_if_flat_exits_after_five_minutes_when_not_green():
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0})
    t = go(ctx, tape, ExitCfg(stop="premium", tp="A", time="a"))
    assert t["entry_idx"] == 21 and t["exit_reason"].startswith("IF FLAT") and t["exit_idx"] == 26
    assert t["pnl"] == pytest.approx((1.0 - HS - (1.0 + HS)) * 100 - 1.30)
    t = go(ctx, tape, ExitCfg(stop="premium", tp="A", time="b"))             # no if-flat in version (b)
    assert t["exit_reason"].startswith("ALL OUT")


def test_time_table_tightens_the_ceiling_when_a_window_is_crossed():
    C = cost(1.0)
    path = {0: 1.0, 112: 1.05, 130: 1.0, 140: 0.86}     # green at the if-flat check; then -14%: inside 20%, beyond 12%
    ctx, tape = SS.make_ctx(DAY, {}, path)
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="c"), idx=110)  # enters 10:41 (20% window), crosses 11:30
    assert t["exit_reason"] == "CEILING STOP" and t["exit_idx"] == 140
    assert t["exit_basis"] == pytest.approx(0.86)                            # gapped through the 12% line -> the open
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 112: 1.05, 130: 1.0, 140: 0.93}, opt_hl={140: (0.95, 0.88)})
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="c"), idx=110)
    assert t["exit_basis"] == pytest.approx(trig(C, -0.12), abs=1e-4)
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="b"), idx=110)  # (b): the entry window's 20% stays
    assert t["exit_reason"].startswith("ALL OUT")


def test_crossing_a_window_never_loosens_anything():
    loose = ((15, 120, 0.20, 0.10, 0.20, 5), (120, 270, 0.30, 0.20, 0.40, 9), (270, 360, 0.35, 0.25, 0.50, 9))
    C = cost(1.0)
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 102: 1.05, 130: 1.0, 150: 0.85}, opt_hl={150: (0.86, 0.75)})
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="c", table=loose), idx=100)
    assert t["exit_reason"] == "CEILING STOP" and t["exit_basis"] == pytest.approx(trig(C, -0.20), abs=1e-4)   # not 30%
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 102: 1.05, 150: 1.26})          # +24% after the cross: T1 stays +20%
    t = go(ctx, tape, ExitCfg(stop="premium", tp="A", time="a", table=loose), idx=100)
    assert t["exit_reason"] == "T1 +20%"
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 103: 1.14, 106: 1.05, 150: 1.04}, opt_hl={150: (1.045, 0.95)})   # breakeven kept
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="a"), idx=100)
    assert t["exit_reason"] == "BREAKEVEN STOP" and t["pnl"] == pytest.approx(0.0, abs=1e-6)


def test_all_out_1525_vs_1550():
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 300: 1.10, 356: 1.05, 381: 0.95})
    a = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="b"))
    b = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="b", allout="15:50"))
    assert (a["exit_idx"], a["exit_time"], a["exit_basis"]) == (355, "15:25", 1.10)
    assert (b["exit_idx"], b["exit_time"], b["exit_basis"]) == (380, "15:50", 1.05)
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0}, early=True)
    assert go(ctx, tape, ExitCfg(stop="premium", tp="none", time="b", allout="15:50"))["exit_time"] == "12:50"


# ---------------------------------------------------------------- level targets
def _level_day(extra_stock=None, extra_opt=None, stock_hl=None, vol=None, prior_days=2):
    """Stock flat at 500.00, jumps to 500.50 at the 09:50 signal bar; first level above = $501 (R1)."""
    sp = {0: 500.0, 20: 500.5}
    sp.update(extra_stock or {})
    p_in = opt_px(500.5, 20)
    op = {0: opt_px(500.0, 0), 20: p_in}
    op.update(extra_opt or {})
    ctx, tape = SS.make_ctx(DAY, sp, op, stock_hl=stock_hl, vol=vol, prior_days=prior_days)
    return ctx, tape, p_in


def test_b_sells_just_before_the_first_level_at_the_next_print():
    ctx, tape, p_in = _level_day(stock_hl={40: (501.0, 500.49)}, extra_opt={41: 3.10})
    t = go(ctx, tape, ExitCfg(stop="level", tp="B", time="b"), price=500.5, invalid=500.3)
    assert t["status"] == "TRADE", t
    assert t["target_level"] == {"level": 501.0, "kind": "R1"} and t["target_stock"] == pytest.approx(500.97)
    assert t["stop_stock"] == pytest.approx(500.28)                          # 500.30 - max($0.02, 0.05 ATR)
    assert t["exit_reason"] == "LEVEL TARGET" and t["exit_idx"] == 41 and t["exit_basis"] == 3.10
    assert t["pnl"] == pytest.approx((3.10 - HS - (p_in + HS)) * 100 - 1.30, abs=0.01)
    ctx, tape, _ = _level_day(stock_hl={40: (500.96, 500.49)}, extra_opt={41: 3.10})   # 1 cent short of the zone
    t = go(ctx, tape, ExitCfg(stop="level", tp="B", time="b"), price=500.5, invalid=500.3)
    assert t["exit_reason"].startswith("ALL OUT")


@pytest.mark.parametrize("buf,want", [("$0.03", 500.97), ("0.05%", 501 - 0.0005 * 500.5)])
def test_b_buffers(buf, want):
    ctx, tape, _ = _level_day()
    t = go(ctx, tape, ExitCfg(stop="level", tp="B", tp_buffer=buf, time="b"), price=500.5, invalid=500.3)
    assert t["target_stock"] == pytest.approx(want, abs=1e-4)


def test_rr_minimum_on_the_stock_and_the_option():
    ctx, tape, _ = _level_day()
    base = go(ctx, tape, ExitCfg(stop="level", tp="B", time="b"), price=500.5, invalid=500.3)
    assert base["planned_rr_stock"] == pytest.approx((500.97 - 500.5) / (500.5 - 500.28), abs=1e-3)   # 2.136
    rr_o = base["planned_rr_opt"]
    assert rr_o is not None and 1.0 < rr_o < base["planned_rr_stock"]          # spread, fees and 15 min of decay cost R:R
    t = go(ctx, tape, ExitCfg(stop="level", tp="B", time="b", rr_min=round(rr_o - 0.05, 2)), price=500.5, invalid=500.3)
    assert t["status"] == "TRADE"
    t = go(ctx, tape, ExitCfg(stop="level", tp="B", time="b", rr_min=round(rr_o + 0.05, 2)), price=500.5, invalid=500.3)
    assert t["status"] == "SKIP" and t["reason"].startswith("R:R below")       # the stock passes (2.14), the option doesn't
    t = go(ctx, tape, ExitCfg(stop="level", tp="B", time="b", rr_min=2.5), price=500.5, invalid=500.3)
    assert t["status"] == "SKIP" and t["reason"].startswith("R:R below 2.5")


def test_level_stop_that_does_not_fit_the_ceiling_skips_the_trade():
    ctx, tape, _ = _level_day()
    t = go(ctx, tape, ExitCfg(stop="level", tp="B", time="b"), price=500.5, invalid=497.0)
    assert t["status"] == "SKIP" and "does not fit the 20% ceiling" in t["reason"]


def test_c_sells_half_at_the_level_and_trails_the_rest_under_the_level_cleared():
    ctx, tape, p_in = _level_day(extra_stock={41: 501.2, 60: 500.9}, stock_hl={40: (501.0, 500.49)},
                                 extra_opt={41: 3.10, 61: 2.50})
    t = go(ctx, tape, ExitCfg(stop="level", tp="C", time="b"), price=500.5, invalid=500.3)
    assert [(x["idx"], x["qty"]) for x in t["legs"]] == [(41, 0.5), (61, 0.5)]
    assert t["legs"][0]["reason"].startswith("LEVEL 1") and t["exit_reason"].startswith("LEVEL TRAIL")
    assert t["pnl"] == pytest.approx(leg_pnl(p_in, [(0.5, 3.10, False), (0.5, 2.50, True)]), abs=0.01)


def test_c_holds_the_rest_to_the_next_level_after_a_close_through_and_a_held_retest():
    ctx, tape, p_in = _level_day(extra_stock={41: 501.2, 45: 501.1, 70: 502.0},
                                 stock_hl={40: (501.0, 500.49), 45: (501.15, 501.02), 70: (502.0, 501.9)},
                                 extra_opt={41: 3.10, 71: 3.60})
    t = go(ctx, tape, ExitCfg(stop="level", tp="C", time="b"), price=500.5, invalid=500.3)
    assert t["legs"][-1]["reason"] == "LEVEL 2 (rest)" and t["exit_idx"] == 71
    assert t["pnl"] == pytest.approx(leg_pnl(p_in, [(0.5, 3.10, False), (0.5, 3.60, False)]), abs=0.01)


def test_d_uses_c_on_a_high_volume_day_and_a_otherwise():
    vol = {i: 2500.0 for i in range(390)}
    ctx, tape, _ = _level_day(vol=vol, prior_days=12)
    t = go(ctx, tape, ExitCfg(stop="level", tp="D", time="b"), price=500.5, invalid=500.3)
    assert t["rvol"] >= 1.5 and t["tp_eff"] == "C"
    ctx, tape, _ = _level_day(prior_days=12)
    t = go(ctx, tape, ExitCfg(stop="level", tp="D", time="b"), price=500.5, invalid=500.3)
    assert t["tp_eff"] == "A"


def test_e_exits_on_a_rejection_wick():
    ctx, tape, p_in = _level_day(stock_hl={40: (501.0, 500.40)}, extra_opt={41: 3.0})
    t = go(ctx, tape, ExitCfg(stop="level", tp="E", time="b"), price=500.5, invalid=500.3)
    assert t["exit_reason"].startswith("LEVEL REJECTION (wick") and t["exit_idx"] == 41


def test_e_holds_to_the_next_level_without_a_rejection_then_exits_on_a_volume_spike():
    ctx, tape, p_in = _level_day(extra_stock={40: 501.0, 60: 502.0}, stock_hl={40: (501.005, 500.5), 60: (502.0, 501.9)},
                                 vol={60: 9000.0}, extra_opt={41: 3.0, 61: 3.70})
    t = go(ctx, tape, ExitCfg(stop="level", tp="E", time="b"), price=500.5, invalid=500.3)
    assert t["exit_idx"] == 61 and "volume 2x" in t["exit_reason"]
    assert t["pnl"] == pytest.approx((3.70 - HS - (p_in + HS)) * 100 - 1.30, abs=0.01)


# ---------------------------------------------------------------- trails
def test_breakeven_trail_triggers_at_its_own_percentage():
    C = cost(1.0)
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 23: 1.0 + 0.07 * C + 0.03, 24: 1.04, 25: 0.98}, opt_hl={24: (1.045, 0.99)})
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="b", trail="be6"))
    assert t["exit_reason"] == "BREAKEVEN STOP" and t["pnl"] == pytest.approx(0.0, abs=1e-6)
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="b", trail="be10"))
    assert t["exit_reason"].startswith("ALL OUT")


def test_profit_lock_ladder_l1():
    C = cost(1.0)
    up = trig(C, 0.31)
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 30: up, 31: 1.10})
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="b", trail="L1"))
    assert t["exit_reason"] == "LOCK STOP" and t["exit_idx"] == 31
    assert t["exit_basis"] == pytest.approx(1.10)                            # opened below the +20% lock: the open
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 30: up, 31: 1.25}, opt_hl={31: (1.26, 1.10)})
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="b", trail="L1"))
    assert t["exit_basis"] == pytest.approx(trig(C, 0.20)) and t["pnl"] == pytest.approx(20 * C, abs=1e-6)


def test_giveback_trail_keeps_70_percent_of_the_peak():
    C = cost(1.0)
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 30: 1.50, 31: 1.40}, opt_hl={30: (1.50, 1.49), 31: (1.45, 1.20)})
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="b", trail="gb30"))
    peak_profit = (1.50 - HS - F) - C
    assert t["exit_reason"] == "GIVEBACK STOP" and t["exit_idx"] == 31
    assert t["pnl"] == pytest.approx(0.7 * peak_profit * 100, abs=1e-4)


def test_one_minute_pivot_trail():
    sp = {0: 500.0, 20: 500.5, 25: 500.8, 26: 500.7, 27: 500.9, 28: 501.0, 35: 500.6}
    ctx, tape = SS.make_ctx(DAY, sp, {0: 1.0, 22: 1.4, 36: 1.2})
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="b", trail="hl1m"), price=500.5)
    assert t["exit_reason"].startswith("1M PIVOT TRAIL") and t["exit_idx"] == 36
    assert "500.67" in t["exit_reason"]                                     # pivot low 500.69 - $0.02 buffer


def test_level_trail_under_the_last_level_cleared():
    ctx, tape, p_in = _level_day(extra_stock={30: 501.3, 50: 500.95}, extra_opt={30: 3.0, 51: 2.6})
    t = go(ctx, tape, ExitCfg(stop="level", tp="none", time="b", trail="lvl"), price=500.5, invalid=500.3)
    lm = ctx.levels()
    want = max(max(px for px, _ in lm.at(i) if 500.5 < px < 501.3) for i in range(30, 50)) - 0.02
    assert want >= 501.0 - 0.02                                               # at least the $501 round number was cleared
    assert t["exit_reason"].startswith(f"LEVEL TRAIL {want:.2f}") and t["exit_idx"] == 51
    assert t["pnl"] == pytest.approx((2.6 - HS - (p_in + HS)) * 100 - 1.30, abs=0.01)


def test_vwap_trail_only_on_trend_days():
    sp = {i: 500 + 0.05 * i for i in range(150)}
    sp[150] = 501.0
    op = {i: max(0.5, round(1 + 0.02 * (i - 70), 2)) for i in range(0, 150)}
    op[151] = 2.0
    ctx, tape = SS.make_ctx(DAY, sp, op)
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="b", trail="vwap"), idx=70, price=sp[70])
    assert t["trend_at_entry"] is True
    assert t["exit_reason"].startswith("VWAP TRAIL") and t["exit_idx"] == 151
    flat = {i: 500 + 0.05 * (i % 4) for i in range(390)}                      # a choppy day: the trail never arms
    ctx, tape = SS.make_ctx(DAY, flat, {0: 1.0, 100: 1.3})
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="b", trail="vwap"), idx=70, price=flat[70])
    assert t["trend_at_entry"] is False and t["exit_reason"].startswith("ALL OUT")


def test_no_new_trades_after_1530():
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0})
    t = go(ctx, tape, ExitCfg(stop="premium", tp="none", time="b"), idx=360)
    assert t["status"] == "SKIP"


# ---------------------------------------------------------------- noise exits and the put side
def _noise_sig(cap=True):
    bands = {29: (501.0, 499.0), 59: (501.0, 499.0), 89: (501.2, 498.8)}
    return Signal("noise" if cap else "noise_nocap", "SPY", DAY, "C", 29, 501.5, 501.0, {"bands": bands, "cap": cap})


def test_noise_stop_at_the_half_hour_check_and_the_20pct_ceiling_only_with_the_cap():
    cfg = ExitCfg(stop="noise", tp="none", contract="d55-75t65")
    ctx, tape = SS.make_ctx(DAY, {0: 500.0, 29: 501.5, 40: 501.6, 59: 500.9}, {0: 1.0, 61: 0.95})
    info = {"symbol": tape.symbol, "px": 1.0, "iv": 0.2, "delta": 0.65}
    t = simulate(ctx, _noise_sig(), cfg, None, tape, info)
    assert t["exit_reason"].startswith("NOISE STOP at check") and t["exit_idx"] == 60 and t["exit_is_stop"]
    ctx, tape = SS.make_ctx(DAY, {0: 500.0, 29: 501.5, 40: 501.6, 59: 500.9}, {0: 1.0, 45: 0.70, 61: 0.95})
    t = simulate(ctx, _noise_sig(True), cfg, None, tape, info)
    assert t["exit_reason"] == "CEILING STOP" and t["exit_idx"] == 45 and t["exit_basis"] == 0.70
    t = simulate(ctx, _noise_sig(False), cfg, None, tape, info)
    assert t["exit_reason"].startswith("NOISE STOP") and t["exit_idx"] == 60          # the twin has no 20% line
    ctx, tape = SS.make_ctx(DAY, {0: 500.0, 29: 501.5}, {0: 1.0})
    t = simulate(ctx, _noise_sig(), cfg, None, tape, info)
    assert t["exit_reason"] == "ALL OUT 15:25"


def test_b_on_the_put_side():
    p_in = round(bs.price(499.5, K, bs.t_years(390 - 21), 0.2, "P"), 2)
    ctx, tape = SS.make_ctx(DAY, {0: 500.0, 20: 499.5}, {0: 2.0, 20: p_in, 41: 3.2}, right="P", stock_hl={40: (499.51, 499.0)})
    iv = bs.implied_vol(p_in, 499.5, K, bs.t_years(390 - 21), "P")
    s = Signal("orb15", "SPY", DAY, "P", 20, 499.5, 499.7, {})
    t = simulate(ctx, s, ExitCfg(stop="level", tp="B", time="b"), None, tape, {"symbol": tape.symbol, "px": p_in, "iv": iv, "delta": -0.5})
    assert t["status"] == "TRADE", t
    assert t["target_level"] == {"level": 499.0, "kind": "R1"} and t["target_stock"] == pytest.approx(499.03)
    assert t["stop_stock"] == pytest.approx(499.72) and t["exit_reason"] == "LEVEL TARGET" and t["exit_idx"] == 41
    assert t["pnl"] == pytest.approx((3.2 - HS - (p_in + HS)) * 100 - 1.30, abs=0.01)
    ctx, tape = SS.make_ctx(DAY, {0: 500.0, 20: 499.5, 30: 499.8}, {0: 2.0, 20: p_in, 31: 1.0}, right="P")
    t = simulate(ctx, s, ExitCfg(stop="level", tp="B", time="b"), None, tape, {"symbol": tape.symbol, "px": p_in, "iv": iv, "delta": -0.5})
    assert t["exit_reason"].startswith("LEVEL STOP 499.72") and t["exit_idx"] == 31
