"""Round 8's option pass (sprint/optpass.py): the 12-cell grid evaluated in one pass per entry equals the engine's own fixed
stop/target runs trade by trade (one position per cell, real and MODELED tapes, 0DTE and next expiry); the signal exit and
its flip; A-opt's exits follow the share rule (band/VWAP stop, reversal); A3's twin holds to 15:25; modeled next-expiry
tapes and the calibration fallback; the new contract rules. Synthetic data only."""
from datetime import date

import numpy as np
import pytest

import sprint_synth as SS
from sprint import bs, contracts, data, engine, entries, ind5, optpass, periods, shares
from sprint import modeled as MD
from sprint import spread as SP
from sprint.fills import OptionTape
from sprint.sim import ExitCfg

DAY = date(2025, 3, 12)


def _sessions(a, n):
    return [d for d in SS.weekdays(a, n + 10) if d.isoformat() not in periods.holidays()][:n]


DAYS = _sessions(date(2025, 2, 3), 18)


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    root = tmp_path_factory.mktemp("r8opt")
    SS.write_cache(root, "SPY", DAYS, px0=500.0, seed=21, iv=0.18, band=0.03, next_expiry=True)
    return root


def _wrap(rule):
    def f(ctx, side="both"):
        return [entries.Signal(rule, ctx.sym, ctx.day, s["side"], s["idx"], s["price"], None, {})
                for s in ind5.signals(ctx, rule) if side in ("both", s["side"])]
    return f


CALIB = {"min_n": 30, "keys": {k: {"n": 100, "median": 0.6, "ok": True} for k in ("d40-55t45|C", "d40-55t45|P", "n1d40-55t45|C")}}


@pytest.mark.parametrize("mode,contract", [("real", "d40-55t45"), ("real", "n1d40-55t45"), ("modeled", "n1d40-55t45")])
def test_grid_cells_equal_the_engines_fixed_runs_trade_by_trade(cache, monkeypatch, mode, contract):
    monkeypatch.setitem(entries.SETUPS, "r8_ind_macd", _wrap("ind_macd"))
    runs = [{"run_id": cid, "block": cid, "entry": "r8_ind_macd", "side": "both", "symbols": ("SPY",), "filters": (),
             "exit": ExitCfg(stop="fixed", fixed_stop=s, fixed_target=optpass.NONE_TARGET if t is None else t, contract=contract, time="b")}
            for cid, s, t in optpass.GRID]
    a, b = DAYS[0], DAYS[-1]
    sp = SP.SpreadModel()
    kw = dict(tape_mode="modeled", calib=CALIB) if mode == "modeled" else {}
    res, _ = engine.run_pass(runs, a, b, cache, sp, **kw)
    ser = data.Series("SPY", data.read_stock("SPY", a, b, cache))
    st = optpass.expand_studies({"option_pass": {"studies": [{"name": "x", "entry": "ind_macd", "contract": contract, "exits": "grid12+signal"}]}})
    col = optpass.run({"SPY": ser}, st, a, b, mode, root=cache, calib=CALIB if mode == "modeled" else None, spread=sp)
    fr = col.frame()
    n = 0
    for cid, _s, _t in optpass.GRID:
        eng = sorted((t["day"], t["entry_idx"], t["exit_idx"], t["side"], t["pnl"], t["pnl_2x"]) for t in res[cid]["trades"])
        sub = fr[fr["exit"] == cid]
        mine = sorted(zip(sub["day"], sub["entry_idx"], sub["exit_idx"], sub["side"], sub["pnl"], sub["pnl_2x"]))
        assert [(d, e, x, s) for d, e, x, s, _, _ in mine] == [(d, e, x, s) for d, e, x, s, _, _ in eng], cid
        assert np.allclose([m[4] for m in mine], [x[4] for x in eng]) and np.allclose([m[5] for m in mine], [x[5] for x in eng])
        n += len(eng)
    assert n > 50 and len(set(fr["exit"])) == 13
    reasons = {t["exit_reason"].split(" ")[1] for c in res for t in res[c]["trades"]}
    assert {"STOP", "TARGET"} <= reasons or "OUT" in reasons


# ---------------------------------------------------------------- hand-built tapes: the signal exit and its flip
def _tape(prices, right="C", strike=500.0, lows=None, skip=()):
    o = np.full(390, np.nan)
    for i, p in prices.items():
        o[i] = p
    o = np.array(o)
    cur = np.nan
    for i in range(390):
        if not np.isnan(o[i]):
            cur = o[i]
        elif not np.isnan(cur) and i > min(prices):
            o[i] = cur
    for i in skip:
        o[i] = np.nan
    h, l, c = o + 0.005, o - 0.005, o.copy()
    for i, x in (lows or {}).items():
        l[i] = x
    return OptionTape(f"SPY250312{right}{int(strike * 1000):08d}", right, strike, o, h, l, c, np.where(np.isnan(o), np.nan, 10.0))


def test_signal_exit_flip_stop_first_void_and_all_out():
    t = _tape({30: 1.00})
    debit = 1.00 + 0.01
    ex = {59: ("OPPOSITE SIGNAL", False, True), 89: ("OPPOSITE SIGNAL", False, True)}
    assert optpass.signal_exit(t, 29, 30, 355, debit, ex, 0.20) == (60, 1.0, "OPPOSITE SIGNAL", False, 59)
    t2 = _tape({30: 1.00}, lows={45: 0.70})                                 # -20% touched before the opposite signal
    x, basis, why, stop, flip = optpass.signal_exit(t2, 29, 30, 355, debit, ex, 0.20)
    assert (x, why, stop, flip) == (45, "FIXED STOP", True, None) and basis == pytest.approx(debit * 0.8)
    t3 = _tape({30: 1.00}, lows={59: 0.70})                                 # the same bar: the premium stop wins
    assert optpass.signal_exit(t3, 29, 30, 355, debit, ex, 0.20)[2] == "FIXED STOP"
    assert optpass.signal_exit(t2, 29, 30, 355, debit, ex, None)[2] == "OPPOSITE SIGNAL"   # no premium line (A-opt)
    t4 = _tape({30: 1.00}, skip=range(60, 390))                             # no print after the decision: VOID
    assert optpass.signal_exit(t4, 29, 30, 355, debit, ex, None) is None
    assert optpass.signal_exit(t, 29, 30, 355, debit, {}, None) == (355, 1.0, "ALL OUT", False, None)       # held (A3's twin)
    assert optpass.signal_exit(t, 29, 30, 355, debit, {20: ("OPPOSITE SIGNAL", False, True)}, None)[2] == "ALL OUT"   # before entry
    cells = optpass.fixed_exits(_tape({30: 1.00}, lows={40: 0.85, 50: 0.60}), 30, 355, debit, [(0.10, None), (0.20, 0.30), (0.50, None)])
    assert [c[0] for c in cells] == [40, 50, 355] and [c[2] for c in cells] == ["FIXED STOP", "FIXED STOP", "ALL OUT"]   # -50%: 0.505


class _Pool:
    def pool(self, rule, side, S):
        return None


def test_run_day_flips_on_the_opposite_signal_and_grid_cells_hold_one_position(monkeypatch):
    ctx, _ = SS.make_ctx(DAY, {0: 500.0}, {0: 1.0}, prior_days=3)
    tapes = {"C": _tape({0: 1.00}, "C"), "P": _tape({0: 1.00}, "P")}
    monkeypatch.setattr(optpass.contracts, "pick", lambda c, side, j, rule: (tapes[side], {"px": 1.0, "iv": 0.2}))
    sigs = [{"idx": 29, "side": "C", "price": 500.0, "info": {}}, {"idx": 59, "side": "P", "price": 500.0, "info": {}},
            {"idx": 89, "side": "C", "price": 500.0, "info": {}}]
    ex = optpass._exits_from(sigs)
    monkeypatch.setattr(optpass, "day_signals", lambda c, e, s=None, cache=None: [dict(x, exits=ex) for x in sigs])
    st = optpass.expand_studies({"option_pass": {"studies": [{"name": "x", "entry": "ind_ema", "contract": "d40-55t45", "exits": "grid12+signal"}]}})
    col = optpass.Collector(st, ["SPY"])
    optpass.run_day(ctx, st, _Pool(), SS.ConstSpread(0.01), col)
    fr = col.frame()
    sg = fr[fr["exit"] == "signal"]
    assert list(zip(sg["side"], sg["signal_idx"], sg["entry_idx"], sg["exit_idx"], sg["exit_reason"])) == [
        ("C", 29, 30, 60, "OPPOSITE SIGNAL"), ("P", 59, 60, 90, "OPPOSITE SIGNAL"), ("C", 89, 90, 355, "ALL OUT")]
    g = fr[fr["exit"] == "s50_tnone"]                                        # holds to 15:25: the later signals are busy
    assert list(zip(g["signal_idx"], g["exit_idx"])) == [(29, 355)]
    assert col.skips[("x", "s50_tnone")]["busy: one position at a time"] == 2
    p = sg.iloc[0]
    assert p["pnl"] == pytest.approx(((1.0 - 0.01) - (1.0 + 0.01)) * 100 - 1.30)


def test_a_opt_exits_follow_the_share_rule(monkeypatch):
    monkeypatch.setattr(shares, "a1_bands", lambda s, d: (np.full(390, 101.0), np.full(390, 99.0)))
    path = {0: 100.0, 29: 101.5, 59: 100.5, 89: 102.0, 119: 98.0, 149: 99.5, 179: 98.5, 389: 97.0}
    ctx, _ = SS.make_ctx(DAY, path, {0: 1.0}, prior_days=20, px=100.0)
    ctx.vwap[:] = 100.0
    sigs = shares.a1_option_signals(ctx)
    assert [(s["idx"], s["side"]) for s in sigs] == [(29, "C"), (89, "C"), (119, "P"), (179, "P"), (209, "P"), (239, "P"), (269, "P"),
                                                     (299, "P"), (329, "P"), (359, "P")]
    ex = sigs[0]["exits"]
    assert ex["C"][59][0].startswith("NOISE STOP") and ex["C"][59][1:] == (True, False)
    assert ex["C"][119] == ("NOISE REVERSAL", False, True) and ex["P"][149][0].startswith("NOISE STOP")
    shr = shares.a1_day(ctx, "DEV")
    tapes = {"C": _tape({0: 1.00}, "C"), "P": _tape({0: 1.00}, "P")}
    monkeypatch.setattr(optpass.contracts, "pick", lambda c, side, j, rule: (tapes[side], {"px": 1.0, "iv": 0.2}))
    st = optpass.expand_studies({"option_pass": {"studies": [{"name": "a", "entry": "noise_sh", "contract": "d55-75t65", "exits": "share_signal"}]}})
    col = optpass.Collector(st, ["SPY"])
    optpass.run_day(ctx, st, _Pool(), SS.ConstSpread(0.01), col)
    fr = col.frame()
    got = list(zip(fr["side"], fr["entry_idx"], fr["exit_idx"]))
    want = [("C" if t["side"] == "L" else "P", t["entry_idx"], min(t["exit_idx"], 355)) for t in shr]
    assert got == want                                                       # the option twin follows the shares (15:25 all-out)
    assert list(fr["exit_reason"]) == ["NOISE STOP", "NOISE REVERSAL", "NOISE STOP", "ALL OUT"]


# ---------------------------------------------------------------- modeled next-expiry tapes and the calibration fallback
def test_modeled_next_expiry_tapes_and_picker(cache):
    ser = data.Series("SPY", data.read_stock("SPY", DAYS[0], DAYS[-1], cache))
    d = DAYS[4]
    ctx = data.DayContext(ser, d, {}, None)
    nx = MD.next_session(d)
    assert nx > d and nx.weekday() < 5 and MD.next_session(date(2025, 4, 17)) == date(2025, 4, 21)   # Good Friday + weekend
    md = MD.ModeledDay(ctx, expiry=nx)
    t = md.tape(500.0, "C", 0.2)
    extra = 1440 * (nx - d).days
    assert t.expiry == nx and t.symbol == f"SPY{nx:%y%m%d}C00500000"
    want = max(round(bs.price(float(ctx.c[100]), 500.0, (390 - 101 + extra) / bs.YEAR_MIN, 0.2, "C"), 2), 0.01)
    assert t.c[100] == pytest.approx(want)
    assert md.tape(500.0, "C", 0.2).c[100] > MD.ModeledDay(ctx).tape(500.0, "C", 0.2).c[100]          # more time value
    ctx.tapes_next = md.pool(float(ctx.c[89]), "C", 0.2)
    tape, info = contracts.pick(ctx, "C", 89, "n1d40-55t45")
    assert tape is not None and info["expiry"] == str(nx) and abs(info["iv"] - 0.2) < 0.02 and 0.40 <= abs(info["delta"]) <= 0.55
    m, key = MD.multiplier_for(CALIB, "n1d40-55t45", "C")
    assert key == "n1d40-55t45|C"                                              # run 4 has this key: it is used
    m, key = MD.multiplier_for(CALIB, "n1d40-55t45", "P")
    assert m == 0.6 and key.startswith("d40-55t45|P (fallback")
    with pytest.raises(ValueError):
        MD.multiplier_for(CALIB, "d55-75t65", "C")                            # a 0DTE rule never falls back
    with pytest.raises(ValueError):
        MD.multiplier_for(CALIB, "n1d55-75t65", "C")                          # nor when the 0DTE key is missing too


def test_restart_safety_the_passes_are_deterministic(cache):
    """Re-running the option pass and the share pass on the same cache gives the same trades (Chart can re-run a step)."""
    a, b = DAYS[0], DAYS[-1]
    vd = None
    st = optpass.expand_studies({"option_pass": {"studies": [
        {"name": "x", "entry": "ind_bb", "contract": "d40-55t45", "exits": "grid12+signal"},
        {"name": "rx", "entry": "ind_bb", "contract": "d40-55t45", "exits": "grid12+signal", "random_seed": 31},
        {"name": "n", "entry": "noise_sh", "contract": "d55-75t65", "exits": "share_signal"}]}})
    runs = []
    for _ in range(2):
        ser = data.Series("SPY", data.read_stock("SPY", a, b, cache))
        fr = optpass.run({"SPY": ser}, st, a, b, "real", root=cache, aux={"VIXY_D": vd})
        sh, _cov = shares.run({("DEV", "SPY"): ser}, vd)
        runs.append((fr.frame(), {k: shares.ordered(v) for k, v in sh.items()}))
    assert runs[0][0].equals(runs[1][0]) and len(runs[0][0]) > 0
    assert runs[0][1] == runs[1][1] and sum(len(v) for v in runs[0][1].values()) > 0


def test_new_contract_rules():
    assert contracts.RULES["n1d03-12t07"] == contracts.RULES["d03-12t07"] == (0.03, 0.12, 0.07)
    assert contracts.RULES["n1d55-75t65"] == contracts.RULES["d55-75t65"] == (0.55, 0.75, 0.65)
    assert contracts.is_next("n1d03-12t07") and contracts.is_next("n1d55-75t65") and not contracts.is_next("d55-75t65")
    assert optpass.GRID_IDS == ["s10_t30", "s10_t50", "s10_tnone", "s20_t30", "s20_t50", "s20_tnone", "s30_t30", "s30_t50", "s30_tnone",
                                "s50_t30", "s50_t50", "s50_tnone"]
    with pytest.raises(ValueError):
        optpass.expand_studies({"option_pass": {"studies": [{"name": "x", "entry": "nope", "contract": "d40-55t45", "exits": "hold"}]}})
