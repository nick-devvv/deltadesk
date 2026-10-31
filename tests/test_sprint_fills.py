"""Sprint fill rules (sprint/fills.py, docs/research/SPRINT_PLAN.md "Cost model and fills"): same-bar stop vs target,
stop gap-through fills at the next real price, first trade at/below a stop, no-print minutes, never a fill at an
unseen price, k=2 with the extra k on stops, fees. Synthetic data only, no network."""
import math
import random
from datetime import date

import numpy as np
import pytest

import sprint_synth as SS
from sprint import fills, sim
from sprint.entries import Signal
from sprint.sim import ExitCfg, simulate

DAY = date(2025, 3, 12)
HS = 0.01
F = fills.FEE / 100


def cinfo(tape, px=1.0):
    return {"symbol": tape.symbol, "px": px, "iv": 0.2, "delta": 0.45}


def sig(idx=20, side="C", price=500.0, invalid=None):
    return Signal("orb15", "SPY", DAY, side, idx, price, invalid, {})


def run(ctx, tape, cfg, s=None, px=1.0):
    return simulate(ctx, s or sig(), cfg, None, tape, cinfo(tape, px))


A_B = ExitCfg(stop="premium", tp="A", time="b")      # T1 +20% and a 20% ceiling, nothing else


def test_costs_hand_check():
    c = sim.Costs(SS.ConstSpread(HS), "SPY", 21)
    C = 1.00 + HS + F                                   # 1.0165
    assert c.cost(1.00) == pytest.approx(C)
    assert c.trigger(C * 0.8) == pytest.approx(C * 0.8 + HS + F, abs=1e-9)        # 0.8297
    assert c.trigger(C * 1.2) == pytest.approx(C * 1.2 + HS + F, abs=1e-9)        # 1.2363
    assert fills.stop_k(1) == 1 and fills.stop_k(2) == 4


def test_entry_is_the_next_bar_open_and_target_pnl_is_exact():
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.00, 30: 1.30})
    t = run(ctx, tape, A_B)
    assert t["status"] == "TRADE" and t["entry_idx"] == 21 and t["entry_basis"] == 1.00
    C = 1.0 + HS + F
    t1 = C * 1.2 + HS + F
    assert t["exit_reason"].startswith("T1") and t["exit_idx"] == 30
    assert t["exit_basis"] == pytest.approx(1.30)           # the bar opened above T1: filled at the open (a traded price)
    assert t["pnl"] == pytest.approx((1.30 - HS - (1.0 + HS)) * 100 - 1.30, abs=0.01)
    ctx2, tape2 = SS.make_ctx(DAY, {}, {0: 1.00, 30: 1.10}, opt_hl={30: (1.25, 1.09)})
    t2 = run(ctx2, tape2, A_B)
    assert t2["exit_basis"] == pytest.approx(t1, abs=1e-6)  # touched inside the bar: filled at the target price


def test_same_bar_stop_and_target_counts_as_the_stop():
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.00, 30: 1.00}, opt_hl={30: (1.40, 0.70)})
    t = run(ctx, tape, A_B)
    C = 1.0 + HS + F
    assert t["exit_reason"] == "CEILING STOP" and t["exit_idx"] == 30
    assert t["exit_basis"] == pytest.approx(C * 0.8 + HS + F, abs=1e-6)
    assert t["pnl"] == pytest.approx(-0.20 * C * 100, abs=0.01)                    # exactly the 20% ceiling, costs incl.


def test_same_bar_underlying_stop_beats_a_premium_target():
    cfg = ExitCfg(stop="level", tp="A", time="b")
    ctx, tape = SS.make_ctx(DAY, {0: 500.5, 30: 500.0}, {0: 1.00, 30: 1.00, 31: 0.95}, opt_hl={30: (1.40, 0.99)})
    t = run(ctx, tape, cfg, sig(price=500.5, invalid=500.3))
    assert t["status"] == "TRADE", t
    assert t["exit_reason"].startswith("LEVEL STOP") and t["exit_idx"] == 31 and t["exit_basis"] == pytest.approx(0.95)


def test_stop_gap_through_fills_at_the_next_real_price():
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.00, 30: 0.60})
    t = run(ctx, tape, A_B)
    assert t["exit_reason"] == "CEILING STOP" and t["exit_basis"] == pytest.approx(0.60)       # worse than the stop: the open
    assert t["pnl"] == pytest.approx((0.60 - HS - 1.01) * 100 - 1.30, abs=0.01)


def test_stop_uses_the_first_trade_at_or_below_it_when_trades_exist():
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.00, 30: 1.00}, opt_hl={30: (1.01, 0.70)})
    C = 1.0 + HS + F
    trig = C * 0.8 + HS + F
    tr_m = np.array([30, 30, 30, 30])
    tr_p = np.array([1.00, 0.90, 0.78, 0.85])              # first print below the 0.8297 stop is 0.78
    tape2 = fills.OptionTape(tape.symbol, "C", 500, tape.o, tape.h, tape.l, tape.c, tape.v, trades=(tr_m, tr_p))
    ctx.tapes = {tape2.symbol: tape2}
    t = run(ctx, tape2, A_B)
    assert t["exit_reason"] == "CEILING STOP" and t["exit_basis"] == pytest.approx(0.78) and 0.78 < trig
    assert tape2.stop_basis(30, 0.95)[0] == pytest.approx(0.90)                   # first trade at/below 0.95


def test_no_print_minutes_never_fill():
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.00, 22: 1.05}, no_print={21})
    t = run(ctx, tape, A_B)
    assert t["entry_idx"] == 22 and t["entry_basis"] == 1.05                      # 21 had no print
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.00}, no_print={21, 22, 23})
    t = run(ctx, tape, A_B)
    assert t["status"] == "SKIP" and "no option print" in t["reason"]
    # an underlying-decided exit waits for the next print
    cfg = ExitCfg(stop="level", tp="none", time="b")
    ctx, tape = SS.make_ctx(DAY, {0: 500.5, 30: 500.0}, {0: 1.00, 33: 0.90}, no_print={31, 32})
    t = run(ctx, tape, cfg, sig(price=500.5, invalid=500.3))
    assert t["exit_idx"] == 33 and t["exit_basis"] == pytest.approx(0.90)


def test_k2_and_the_extra_k_on_stop_exits():
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.00, 30: 0.60})
    t = run(ctx, tape, A_B)
    assert t["pnl_2x"] == pytest.approx((0.60 - 4 * HS - (1.00 + 2 * HS)) * 100 - 1.30, abs=0.01)
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.00, 30: 1.30})
    t = run(ctx, tape, A_B)
    assert t["pnl_2x"] == pytest.approx((1.30 - 2 * HS - (1.00 + 2 * HS)) * 100 - 1.30, abs=0.01)   # a target: k = 2


def test_fees_are_065_per_contract_per_side_and_half_legs_add_up():
    legs = [(0.5, 1.2, 0.01, False), (0.5, 0.9, 0.01, True)]
    p = fills.pnl(1.0, 0.01, legs, 1)
    assert p == pytest.approx(0.5 * (1.19 - 1.01) * 100 + 0.5 * (0.89 - 1.01) * 100 - 0.65 - 0.65, abs=1e-9)


@pytest.mark.parametrize("seed", range(6))
def test_never_fills_at_a_price_the_option_did_not_trade(seed):
    rnd = random.Random(seed)
    path, hl, gaps = {}, {}, set()
    px = 1.0
    for i in range(0, 390):
        px = max(0.05, px * (1 + rnd.gauss(0, 0.04)))
        path[i] = round(px, 2)
        hl[i] = (round(px * (1 + abs(rnd.gauss(0, 0.03))), 2), round(px * (1 - abs(rnd.gauss(0, 0.03))), 2))
        if rnd.random() < 0.15:
            gaps.add(i)
    stock = {i: 500 + 0.02 * (i % 37) - 0.3 * (i % 11 == 0) for i in range(390)}
    ctx, tape = SS.make_ctx(DAY, stock, path, opt_hl=hl, no_print=gaps)
    for cfg in (A_B, ExitCfg(stop="premium", tp="A", time="a"), ExitCfg(stop="level", tp="B", time="c"),
                ExitCfg(stop="level", tp="C", time="a"), ExitCfg(stop="level", tp="none", trail="gb30", time="c"),
                ExitCfg(stop="level", tp="E"), ExitCfg(stop="premium", tp="none", trail="L2", allout="15:50")):
        for j in (16, 40, 90, 200):
            s = sig(idx=j, price=float(ctx.c[j]), invalid=float(ctx.c[j]) - 0.3)
            t = simulate(ctx, s, cfg, None, tape, cinfo(tape, tape.last_close(j) or 1.0))
            if t["status"] != "TRADE":
                continue
            e = t["entry_idx"]
            assert tape.has_print(e) and t["entry_basis"] == pytest.approx(tape.o[e])
            for leg in t["legs"]:
                i = leg["idx"]
                assert tape.has_print(i), (cfg, leg)
                assert tape.l[i] - 1e-9 <= leg["basis"] <= tape.h[i] + 1e-9, (cfg, leg, tape.l[i], tape.h[i])
            assert sum(x["qty"] for x in t["legs"]) == pytest.approx(1.0)


def test_spread_model_default_measured_from_chains_and_sensitivity(tmp_path):
    import csv as _csv
    import gzip as _gz
    from sprint import spread as SP
    m = SP.SpreadModel()
    assert m.half_spread("SPY", 2.0) == (pytest.approx(0.10), "MODELED-SPREAD")          # 5% of premium
    assert m.half_spread("NVDA", 2.0)[0] == pytest.approx(0.20)                          # 10% single stocks
    assert m.half_spread("SPY", 0.05)[0] == SP.TICK_HALF and m.label == "MODELED-SPREAD"
    assert SP.from_chains(tmp_path / "missing").label == "MODELED-SPREAD"
    rows = []
    for k in range(120):
        rows.append({"logged_at": f"2026-11-02T10:{k % 60:02d}:00-05:00", "underlying": "SPY", "spot": 600, "symbol": f"S{k}", "type": "C",
                     "expiry": "2026-11-02", "strike": 600, "bid": 1.20, "ask": 1.22, "last": 1.21, "volume": 1, "oi": 1, "delta": 0.5,
                     "gamma": 0.1, "iv": 0.2, "quote_time": ""})
    rows.append(dict(rows[0], expiry="2026-11-03", bid=1.0, ask=2.0))                    # not 0DTE: ignored
    with _gz.open(tmp_path / "2026-11-02.csv.gz", "wt") as f:
        w = _csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    mm = SP.from_chains(tmp_path, {"SPY"})
    assert mm.label == "MEASURED-SPREAD" and mm.coverage["SPY"] == {"days": 1, "rows": 120}
    assert mm.half_spread("SPY", 1.21, 60) == (pytest.approx(0.01), "MEASURED-SPREAD")
    assert mm.half_spread("QQQ", 1.21, 60)[1] == "MODELED-SPREAD"                        # no QQQ rows: the default
    assert mm.spread_ok("SPY", 1.21, 60) and not SP.SpreadModel({("SPY", 3, 1): 0.2, ("SPY", 3, None): 0.2}).spread_ok("SPY", 1.5, 60)
    s = SP.SpreadModel(pct=0.01)
    assert s.half_spread("SPY", 2.0)[0] == pytest.approx(0.02) and "sensitivity" in s.label
