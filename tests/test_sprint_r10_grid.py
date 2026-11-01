"""Round 10's grid (sprint/r10grid.py; SPRINT_PLAN Amendment 15 + Amendment 16): the cell layout and trial counts, the one-pass
exits against an independent bar-by-bar reference (every variant: option / level / no stop, targets, gb50, time caps, R3,
R4), fixed-stop cells against the engine trade by trade (real and MODELED tapes), the batched contract picks against
contracts.pick, vwap_macd on N-minute bars, the frozen choice (2016-2019 only), no look-ahead, restart safety and the
locked-period refusal. Synthetic data only."""
import json
import math
from datetime import date, timedelta

import numpy as np
import pytest

import sprint_synth as SS
from sprint import book, contracts, data, engine, entries, features, periods, r10grid as G, shares
from sprint import modeled as MD
from sprint import spread as SP
from sprint.fills import FEE, MULT, OptionTape
from sprint.fills import pnl as fills_pnl
from sprint.sim import Costs, ExitCfg

DEV_DAYS = [date.fromisoformat(d) for d in book.sessions_between("2025-03-03", "2025-03-21")]
HIST_DAYS = [date.fromisoformat(d) for d in book.sessions_between("2019-10-14", "2019-11-29")]
KEYS = ("d40-55t45|C", "d40-55t45|P", "n1d40-55t45|C", "d20-30t25|C", "d20-30t25|P", "d55-70t60|C", "d55-70t60|P", "af153|C", "af153|P")
CALIB = {"min_n": 30, "keys": {k: {"n": 100, "median": 0.9, "ok": True} for k in KEYS}}


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    root = tmp_path_factory.mktemp("r10g")
    SS.write_cache(root, "SPY", DEV_DAYS, px0=500.0, seed=31, iv=0.18, band=0.03, next_expiry=True)
    SS.write_stock_only(root, "SPY", HIST_DAYS, px0=300.0, seed=41, vol=0.0007)
    return root


@pytest.fixture(scope="module")
def series(cache):
    return {("DEV", "SPY"): data.Series("SPY", data.read_stock("SPY", DEV_DAYS[0], DEV_DAYS[-1], cache)),
            ("HIST", "SPY"): data.Series("SPY", data.read_stock("SPY", HIST_DAYS[0], HIST_DAYS[-1], cache))}


@pytest.fixture(scope="module")
def chunks(cache, series):
    dev = G.compute_chunk(series[("DEV", "SPY")], "DEV", 2025, root=cache, do_r1=False, do_af=False)
    hist = G.compute_chunk(series[("HIST", "SPY")], "HIST", 2019, calib=CALIB, do_r1=False, do_af=False)
    return {"DEV": dev, "HIST": hist}


# ---------------------------------------------------------------- layout and trials
def test_cells_trials_and_order():
    assert G.NCELL == 1080 and len(G.ENTRIES) * G.NCELL == 7560 and G.NG == 180 and G.NV == 187
    assert [s for s, _x in G.STOPS] == ["s10", "s20", "s30", "s50", "level", "none"]          # Amendment 16 appends "none"
    assert [t for t, _x in G.TARGETS] == ["t20", "t30", "t50", "t100", "tnone"]
    assert G.CONTRACTS == ("d40-55t45", "d20-30t25", "n1d40-55t45") and G.R2_CONTRACT == "d55-70t60"
    assert contracts.RULES["d55-70t60"] == (0.55, 0.70, 0.60) and not contracts.is_next("d55-70t60")
    assert G.cell_id(0) == "s10.t20.none.m30.d40-55t45.off" and G.cell_id(G.NCELL - 1) == "none.tnone.gb50.1525.n1d40-55t45.on"
    k = G.cell_index("level", "t50", "gb50", "m60", "d20-30t25", "on")
    assert G.CELLS[k] == (4, 2, 1, 1, 1, 1) and G.cell_id(k) == "level.t50.gb50.m60.d20-30t25.on"
    assert G.VARIANTS[G.CELL_V[k]] == (4, 2, 1, 1) and G.CELL_C[k] == 1 and G.CELL_F[k]
    assert len({G.cell_id(i) for i in range(G.NCELL)}) == G.NCELL
    t = G.trials(17)
    assert t["this_build"] == 7587 == sum(t["parts"].values()) and t["round10_total"] == 7767 and t["total_for_dsr"] == 17 + 7767
    assert list(t["parts"].values()) == [7560, 3, 8, 7, 7, 2]


# ---------------------------------------------------------------- an independent bar-by-bar reference
def ref_exit(tape, sc, e, A, b_in, hs_in, costs, side, stop_pct, stop_s, target, gb, cap):
    """sim.py-style loop: premium stop (option stop and/or gb50), then the level stop (next print), then the target; gb50 set
    at the end of each bar; the time cap / all-out at the next print. Returns (exit bar, basis, is_stop) or None."""
    up = side == "C"
    debit, C = b_in + hs_in, b_in + hs_in + FEE / MULT
    w = A if cap is None else min(e + cap, A)
    peak, gstop = -math.inf, -math.inf
    for i in range(e, w):
        has = not math.isnan(tape.o[i])
        lvl = -math.inf if stop_pct is None else debit * (1 - stop_pct)
        if gb:
            lvl = max(lvl, gstop)
        if has and lvl > -math.inf and tape.l[i] <= lvl:
            return i, tape.stop_basis(i, lvl)[0], True
        if stop_s is not None and not math.isnan(sc[i]) and ((sc[i] < stop_s) if up else (sc[i] > stop_s)):
            x = tape.next_print(i + 1)
            return None if x is None else (x, float(tape.o[x]), True)
        if target is not None and has and tape.h[i] >= debit * (1 + target):
            return i, tape.target_basis(i, debit * (1 + target))[0], False
        if has:
            peak = max(peak, float(tape.h[i]))
            prof = costs.proceeds(peak) - C
            if gb and prof > 0:
                gstop = max(gstop, costs.trigger(C + 0.5 * prof))
    x = tape.next_print(w)
    return None if x is None else (x, float(tape.o[x]), False)


def ref_r3(tape, sc, e, A, b_in, hs_in, costs, side, stop_pct, stop_s):
    up = side == "C"
    d, C = b_in + hs_in, b_in + hs_in + FEE / MULT
    legs, phase, peak, gstop = [], 0, -math.inf, -math.inf
    for i in range(e, A):
        has = not math.isnan(tape.o[i])
        lvl = (-math.inf if stop_pct is None else d * (1 - stop_pct)) if phase == 0 else d if phase == 1 else max(d, gstop)
        if has and lvl > -math.inf and tape.l[i] <= lvl:
            b = tape.stop_basis(i, lvl)[0]
            return legs + [(i, b, True)] * (3 - len(legs))
        if phase == 0 and stop_s is not None and not math.isnan(sc[i]) and ((sc[i] < stop_s) if up else (sc[i] > stop_s)):
            x = tape.next_print(i + 1)
            return None if x is None else legs + [(x, float(tape.o[x]), True)] * 3
        if phase == 0 and has and tape.h[i] >= 1.3 * d:
            legs.append((i, tape.target_basis(i, 1.3 * d)[0], False))
            phase = 1
        if phase == 1 and has and tape.h[i] >= 1.6 * d:
            legs.append((i, tape.target_basis(i, 1.6 * d)[0], False))
            phase = 2
        if has:
            peak = max(peak, float(tape.h[i]))
            prof = costs.proceeds(peak) - C
            if prof > 0:
                gstop = max(gstop, costs.trigger(C + 0.5 * prof))
    x = tape.next_print(A)
    return None if x is None else legs + [(x, float(tape.o[x]), False)] * (3 - len(legs))


def ref_r4(tape, e, A, b_in, hs_in, costs):
    d, C = b_in + hs_in, b_in + hs_in + FEE / MULT
    lvl, peak = 0.5 * d, -math.inf
    for i in range(e, A):
        has = not math.isnan(tape.o[i])
        if has and tape.l[i] <= lvl:
            return i, tape.stop_basis(i, lvl)[0], True
        if has:
            peak = max(peak, float(tape.h[i]))
            if peak >= 2.5 * d:
                lvl = max(lvl, 1.5 * d, costs.trigger(C + 0.5 * (costs.proceeds(peak) - C)))
            elif peak >= 2.0 * d:
                lvl = max(lvl, 1.5 * d)
            elif peak >= 1.5 * d:
                lvl = max(lvl, costs.trigger(C))
    x = tape.next_print(A)
    return None if x is None else (x, float(tape.o[x]), False)


def _rand_tape(rng, e, jump=False, gaps=0.08):
    """A random option tape (cent prices, some minutes without a print)."""
    o = np.full(390, np.nan)
    px = rng.uniform(0.6, 3.0)
    for i in range(390):
        px = max(0.01, px * math.exp(rng.normal(0.0, 0.06 if jump else 0.03)))
        o[i] = round(px, 2)
    h = np.round(o * (1 + np.abs(rng.normal(0, 0.03, 390))), 2)
    lo = np.maximum(np.round(o * (1 - np.abs(rng.normal(0, 0.03, 390))), 2), 0.01)
    c = np.round(np.clip(o * (1 + rng.normal(0, 0.01, 390)), lo, h), 2)
    miss = rng.random(390) < gaps
    miss[e] = False
    for a in (o, h, lo, c):
        a[miss] = np.nan
    return OptionTape("SPY250312C00500000", "C", 500.0, o, h, lo, c, np.where(np.isnan(o), np.nan, 5.0))


class _Ctx:
    def __init__(self, c):
        self.c = c


def _pnl(b_in, hs_in, costs, legs, mult=1):
    lg = [(1.0 / len(legs), b, costs.hs(b, x), st) for x, b, st in legs]
    return G.cents(fills_pnl(b_in, hs_in, lg, 1) * mult), G.cents(fills_pnl(b_in, hs_in, lg, 2) * mult)


@pytest.mark.parametrize("seed", range(12))
def test_every_exit_variant_matches_the_reference_loop(seed):
    rng = np.random.default_rng(seed)
    e = int(rng.integers(20, 300))
    A = 355
    tape = _rand_tape(rng, e, jump=seed % 3 == 0)
    side = "C" if seed % 2 == 0 else "P"
    sc = 500.0 + np.cumsum(rng.normal(0, 0.15, 390))
    sc[rng.random(390) < 0.03] = np.nan
    stop_s = (sc[e - 1] - 0.4) if side == "C" else (sc[e - 1] + 0.4)
    b_in = float(tape.o[e])
    costs = Costs(SP.SpreadModel(), "SPY", e, 1)
    hs_in = costs.hs(b_in, e)
    xv = G.Exits(_Ctx(sc), tape, e, A, b_in, hs_in, costs, side, stop_s)
    ex, rs, p1, p2 = xv.grid()
    n_kinds = set()
    for v, (s, t, tr, cp) in enumerate(G.VARIANTS):
        sname, spct = G.STOPS[s]
        ref = ref_exit(tape, sc, e, A, b_in, hs_in, costs, side, spct, stop_s if sname == "level" else None, G.TARGETS[t][1], tr == 1,
                       G.CAPS[cp][1])
        if ref is None:
            assert ex[v] == G.VOID, v
            continue
        x, basis, st = ref
        assert ex[v] == x, (v, G.VARIANTS[v], ex[v], x)
        assert (p1[v], p2[v]) == _pnl(b_in, hs_in, costs, [(x, basis, st)]), v
        n_kinds.add(G.REASONS[rs[v]])
    assert len(n_kinds) >= 3
    for sk in range(6):
        sname, spct = G.STOPS[sk]
        ref = ref_r3(tape, sc, e, A, b_in, hs_in, costs, side, spct, stop_s if sname == "level" else None)
        got = xv.r3(sk)
        if ref is None:
            assert got[0] == G.VOID
            continue
        assert got[0] == max(x for x, _b, _s in ref), sk
        assert (got[2], got[3]) == _pnl(b_in, hs_in, costs, ref, 3), sk
    ref = ref_r4(tape, e, A, b_in, hs_in, costs)
    got = xv.r4()
    assert got[0] == ref[0] and (got[2], got[3]) == _pnl(b_in, hs_in, costs, [ref])


def test_level_stop_is_skipped_when_not_beyond_the_price_and_r3_r4_shapes():
    rng = np.random.default_rng(5)
    tape = _rand_tape(rng, 40)
    sc = np.full(390, 500.0)
    costs = Costs(SP.SpreadModel(), "SPY", 40, 1)
    xv = G.Exits(_Ctx(sc), tape, 40, 355, float(tape.o[40]), costs.hs(float(tape.o[40]), 40), costs, "C", None)
    ex, _rs, _p1, _p2 = xv.grid()
    lev = [v for v, sp in enumerate(G.VSPEC) if sp[2]]
    assert len(lev) == 30 and all(ex[v] == G.LEVEL_BAD for v in lev) and all(ex[v] != G.LEVEL_BAD for v in range(180) if v not in lev)
    assert xv.r3(4)[0] == G.LEVEL_BAD and xv.r3(5)[0] >= 0


def test_gb50_trigger_vectorized_equals_costs_trigger():
    costs = Costs(SP.SpreadModel(), "SPY", 50, 1)
    t = np.array([-0.5, 0.0, 0.004, 0.1, 0.2385, 0.25, 1.0, 3.3, 17.0])
    assert list(G.trigger_v(costs, t)) == [costs.trigger(float(x)) for x in t]
    px = np.array([0.0, 0.01, 0.2, 0.25, 0.3, 5.0])
    assert list(G.proceeds_v(costs, px)) == [costs.proceeds(float(x)) for x in px]


# ---------------------------------------------------------------- against the engine, trade by trade
def _engine_cells(cache, series, period, rule, entry, contract):
    a, b = (DEV_DAYS[0], DEV_DAYS[-1]) if period == "DEV" else (HIST_DAYS[0], HIST_DAYS[-1])
    runs, cells = [], []
    for k, (s, t, tr, cp, c, f) in enumerate(G.CELLS):
        if s > 3 or cp != 2 or f != 0 or G.CONTRACTS[c] != contract or t not in (0, 3, 4):
            continue
        tg = 99.0 if G.TARGETS[t][1] is None else G.TARGETS[t][1]
        runs.append({"run_id": G.cell_id(k), "block": G.cell_id(k), "entry": entry, "side": "both", "symbols": ("SPY",), "filters": (),
                     "exit": ExitCfg(stop="fixed", fixed_stop=G.STOPS[s][1], fixed_target=tg, contract=contract, time="b",
                                     trail="gb50" if tr else "none")})
        cells.append(k)
    kw = dict(tape_mode="modeled", calib=CALIB) if period == "HIST" else {}
    res, _ = engine.run_pass(runs, a, b, cache, SP.SpreadModel(), **kw)
    return res, cells


@pytest.mark.parametrize("period,entry,contract", [("DEV", "orb15", "d40-55t45"), ("DEV", "pd_retest", "d20-30t25"),
                                                   ("DEV", "orb30", "n1d40-55t45"), ("HIST", "orb15", "d40-55t45"),
                                                   ("HIST", "orb15", "n1d40-55t45")])
def test_fixed_cells_equal_the_engines_runs_trade_by_trade(cache, series, chunks, period, entry, contract):
    res, cells = _engine_cells(cache, series, period, None, entry, contract)
    arrays = chunks[period][0]
    n = 0
    for k in cells:
        _s, _t, _tr, _cp, c, f = G.CELLS[k]
        mine = G.replay_one(arrays, "real_", G.ENTRIES.index(entry), c, int(G.CELL_V[k]), False, "SPY", "x")
        eng = sorted((t["day"], t["entry_idx"], t["exit_idx"], t["side"], t["pnl"], t["pnl_2x"]) for t in res[G.cell_id(k)]["trades"])
        got = sorted((r["day"], r["entry_idx"], r["exit_idx"], r["side"], r["pnl"], r["pnl_2x"]) for r in mine)
        assert [g[:4] for g in got] == [x[:4] for x in eng], G.cell_id(k)
        assert np.allclose([g[4] for g in got], [x[4] for x in eng], atol=0.0051) and \
            np.allclose([g[5] for g in got], [x[5] for x in eng], atol=0.0051), G.cell_id(k)
        n += len(eng)
    assert n > 20


# ---------------------------------------------------------------- the batched picks
@pytest.mark.parametrize("mode", ["real", "modeled"])
def test_prefetch_picks_equals_contracts_pick(cache, series, mode):
    ser = series[("DEV" if mode == "real" else "HIST", "SPY")]
    days = ser.days[-4:]
    odays, ndays = data.option_days("SPY", cache), data.option_days("SPY", cache, "next")
    n = 0
    for d in days:
        ctx = data.DayContext(ser, d, {}, SP.SpreadModel())
        ivp = MD.iv_proxy(ser, d) if mode == "modeled" else None
        if mode == "modeled" and ivp is None:
            continue
        keys = {(j, s, r) for j in (15, 44, 120, 230, 340) for s in ("C", "P") for r in G.EVAL_CONTRACTS}
        tp = G.Tapes10(ctx, mode, cache, odays, ndays, CALIB, ivp)
        got = G.prefetch_picks(ctx, tp, keys, {})
        for key in sorted(keys):
            j, s, r = key
            ctx2 = data.DayContext(ser, d, {}, SP.SpreadModel())
            tp2 = G.Tapes10(ctx2, mode, cache, odays, ndays, CALIB, ivp)
            why = tp2.pool(r, s, float(ctx2.c[j]))
            want = (None, why) if why else contracts.pick(ctx2, s, j, r)
            if want[0] is None:
                assert got[key][0] is None, key
            else:
                assert got[key][0].symbol == want[0].symbol and got[key][1] == want[1], key
                n += 1
    assert n > 20


# ---------------------------------------------------------------- entries
def test_vwap_macd_n_with_2_minutes_is_entries_vwap_macd_and_1_5_differ(series):
    ser = series[("DEV", "SPY")]
    seen = {1: 0, 2: 0, 5: 0}
    for d in ser.days[2:]:
        ctx = data.DayContext(ser, d, {}, None)
        a = [(s.side, s.idx, s.price, s.invalid) for s in entries.vwap_macd(ctx)]
        b = [(s.side, s.idx, s.price, s.invalid) for s in G.vwap_macd_n(ctx, 2)]
        assert a == b
        seen[2] += len(a)
        for n in (1, 5):
            sg = G.vwap_macd_n(ctx, n)
            seen[n] += len(sg)
            for s in sg:
                assert entries.DESK_FIRST <= s.idx <= entries.DESK_LAST and (s.idx + 1) % n == 0 and s.setup == f"vwap_macd{n}"
                assert (s.invalid < s.price) if s.side == "C" else (s.invalid > s.price)
    assert seen[1] > 0 and seen[5] >= 0 and seen[2] >= 0
    with pytest.raises(ValueError):
        G.entry_signals(data.DayContext(ser, ser.days[3], {}, None), "nope")


def test_twin_keeps_the_stop_distance_and_trend_filter():
    s = entries.Signal("orb15", "SPY", date(2025, 3, 5), "C", 40, 500.0, 499.2, {})
    tw = G.twin_signals([s] * 1, 31, "SPY", date(2025, 3, 5))[0]
    want = G.twin_side(31, "SPY", date(2025, 3, 5), 40)
    import zlib
    assert want == ("C" if zlib.crc32(b"31|SPY|2025-03-05|40") % 2 == 0 else "P")
    assert tw.side == want and tw.idx == 40 and tw.price == 500.0
    assert tw.invalid == pytest.approx(499.2 if want == "C" else 500.8)
    ctx, _ = SS.make_ctx(date(2025, 3, 12), {0: 500.0, 30: 501.0, 60: 499.0}, {0: 1.0}, prior_days=3)
    assert G.agrees(ctx, "C", 40) and not G.agrees(ctx, "P", 40) and G.agrees(ctx, "P", 70) and not G.agrees(ctx, "C", 70)
    assert not G.agrees(ctx, "C", 10) and not G.agrees(ctx, "P", 10)                 # close == open: no agreement


# ---------------------------------------------------------------- the choice, frozen on 2016-2019 only
def _agg(n, pos, neg):
    return np.array([n, 0, 0, pos, neg, pos, neg], np.int64)


def test_choose_highest_pf_with_100_trades_then_more_trades_then_listed_first():
    disc = np.zeros((G.NCELL, G.NAGG), np.int64)
    disc[5] = _agg(99, 10_000, -1)                  # huge PF but 99 trades: not eligible
    disc[7] = _agg(150, 3000, -2000)                # PF 1.5
    disc[9] = _agg(160, 300, -200)                  # PF 1.5, more trades -> wins the tie
    disc[11] = _agg(120, 2999, -2000)
    assert G.choose(disc) == 9
    disc[12] = _agg(160, 600, -400)                 # the same PF and trades, listed later -> 9 stays
    assert G.choose(disc) == 9
    disc[700] = _agg(100, 50, 0)                    # no loss: ranks first
    assert G.choose(disc) == 700
    disc[3] = _agg(100, 10, 0)
    assert G.choose(disc) == 3                      # two without a loss: more trades? equal (100) -> listed first
    assert G.choose(np.zeros((G.NCELL, G.NAGG), np.int64)) is None


def test_the_choice_reads_only_the_discovery_buckets_and_the_frozen_file_is_stable(tmp_path):
    rng = np.random.default_rng(3)
    A = np.zeros((G.NCELL, G.NB, G.NAGG), np.int64)
    A[:, :4, 0] = rng.integers(90, 140, (G.NCELL, 4)) // 4 + 25
    A[:, :4, 3] = rng.integers(1000, 5000, (G.NCELL, 4))
    A[:, :4, 4] = -rng.integers(1000, 5000, (G.NCELL, 4))
    k = G.choose(G.agg_window(A, "disc"))
    B = A.copy()
    B[:, 4:] = rng.integers(-10 ** 6, 10 ** 6, B[:, 4:].shape)          # 2020 on rewritten: same choice
    assert G.choose(G.agg_window(B, "disc")) == k and k is not None
    doc = G.frozen_doc({e: (k if e == "orb15" else None) for e in G.ENTRIES}, {e: {"trades": 1} for e in G.ENTRIES})
    p = tmp_path / "r10grid_frozen.json"
    sha = G.write_frozen(p, doc)
    assert G.write_frozen(p, doc) == sha
    j = json.loads(p.read_text())
    assert j["entries"]["orb15"]["cell"] == G.cell_id(k) and j["entries"]["pd_retest"]["cell"] is None and "2016-01-04..2019-12-31" in j["chosen_on"]
    doc2 = G.frozen_doc({e: 0 for e in G.ENTRIES}, {e: {} for e in G.ENTRIES})
    with pytest.raises(RuntimeError):
        G.write_frozen(p, doc2)


def test_replay_one_position_per_cell_and_the_trend_filter():
    nc = len(G.EVAL_CONTRACTS)
    arr = {"real_entry": np.array([3, 3, 3], np.int8), "real_day": np.array([737000] * 3, np.int32), "real_idx": np.array([20, 40, 90], np.int16),
           "real_side": np.array([1, -1, 1], np.int8), "real_agree": np.array([True, False, True]),
           "real_ex": np.full((3, nc, G.NV), 60, np.int16), "real_rs": np.zeros((3, nc, G.NV), np.int8),
           "real_p1": np.full((3, nc, G.NV), 100, np.int32), "real_p2": np.full((3, nc, G.NV), 50, np.int32),
           "real_cinfo": np.zeros((3, nc, 6)), "real_feat": np.full((3, G.NF), np.nan)}
    arr["real_ex"][2] = 120
    off = G.replay_one(arr, "real_", 3, 0, 0, False, "SPY", "x")
    on = G.replay_one(arr, "real_", 3, 0, 0, True, "SPY", "x")
    assert [r["signal_idx"] for r in off] == [20, 90]          # the bar-40 signal is busy (the first exits at bar 60)
    assert [r["signal_idx"] for r in on] == [20, 90]
    arr["real_ex"][0] = G.VOID                                 # a VOID trade leaves the cell flat
    assert [r["signal_idx"] for r in G.replay_one(arr, "real_", 3, 0, 0, False, "SPY", "x")] == [40, 90]
    assert [r["signal_idx"] for r in G.replay_one(arr, "real_", 3, 0, 0, True, "SPY", "x")] == [90]   # bar 40 disagrees
    agg = {e: np.zeros((G.NCELL, G.NB, G.NAGG), np.int64) for e in G.ENTRIES}
    G.replay_all(arr, "real_", agg)
    a = agg["orb15"]
    off_k = [k for k in range(G.NCELL) if G.CELL_C[k] == 0 and G.CELL_V[k] == 0 and not G.CELL_F[k]][0]
    on_k = [k for k in range(G.NCELL) if G.CELL_C[k] == 0 and G.CELL_V[k] == 0 and G.CELL_F[k]][0]
    assert a[off_k].sum(axis=0)[0] == 2 and a[on_k].sum(axis=0)[0] == 1


# ---------------------------------------------------------------- no look-ahead, restart safety, locked periods
def _perturb(df, day, after_idx):
    df = df.copy()
    t = df["ts"]
    m = (t.dt.date == day) & ((t.dt.hour * 60 + t.dt.minute - 570) > after_idx)
    rng = np.random.default_rng(9)
    f = 1 + rng.normal(0, 0.01, int(m.sum()))
    for c in ("o", "h", "l", "c"):
        df.loc[m, c] = (df.loc[m, c] * f).round(2)
    df.loc[m, "h"] = df.loc[m, ["o", "h", "l", "c"]].max(axis=1)
    df.loc[m, "l"] = df.loc[m, ["o", "h", "l", "c"]].min(axis=1)
    df.loc[m, "v"] = df.loc[m, "v"] * 3
    return df


def test_no_look_ahead_signals_features_and_picks(cache):
    df = data.read_stock("SPY", DEV_DAYS[0], DEV_DAYS[-1], cache)
    day = DEV_DAYS[-2]
    cut = 200
    s1 = data.Series("SPY", df)
    s2 = data.Series("SPY", _perturb(df, day, cut))
    c1, c2 = data.DayContext(s1, day, {}, None), data.DayContext(s2, day, {}, None)
    assert not np.array_equal(np.nan_to_num(c1.c[cut + 1:]), np.nan_to_num(c2.c[cut + 1:]))
    n = 0
    for e in G.ENTRIES:
        a = [(s.side, s.idx, s.price, s.invalid) for s in G.entry_signals(c1, e) if s.idx <= cut]
        b = [(s.side, s.idx, s.price, s.invalid) for s in G.entry_signals(c2, e) if s.idx <= cut]
        assert a == b, e
        n += len(a)
    for j in (15, 60, 150, cut):
        for side in ("C", "P"):
            f1 = dict(features.entry_features(c1, j, side), **features.regime_features(c1, j, side))
            f2 = dict(features.entry_features(c2, j, side), **features.regime_features(c2, j, side))
            assert f1 == f2, j
            assert G.agrees(c1, side, j) == G.agrees(c2, side, j)
            assert G.af_signal(c1, j) == G.af_signal(c2, j)
    st1, st2 = G.r1_setup(c1), G.r1_setup(c2)
    if st1 and st1.get("side") and st1["idx"] <= cut:
        assert (st1["side"], st1["idx"], st1["qualifies"]) == (st2["side"], st2["idx"], st2["qualifies"])
        assert [m for m in st1["exits"] if m <= cut] == [m for m in st2["exits"] if m <= cut]
    keys = {(j, s, r) for j in (20, 100, cut) for s in ("C", "P") for r in G.EVAL_CONTRACTS}
    got = []
    for ser in (s1, s2):
        cx = data.DayContext(ser, day, {}, SP.SpreadModel())
        p = G.prefetch_picks(cx, G.Tapes10(cx, "real", cache), keys, {})
        got.append({k: (None if v[0] is None else v[0].symbol, v[1] if v[0] is not None else None) for k, v in p.items()})
    assert got[0] == got[1] and sum(1 for v in got[0].values() if v[0]) >= 6


def test_restart_safety_chunks_are_reused_and_reproduce_identical_outputs(cache, series, tmp_path):
    ser = {("DEV", "SPY"): series[("DEV", "SPY")]}
    logs = []
    f1, _c, _s = G.build_chunks(ser, tmp_path / "c", None, root=cache, log=logs.append, limit_days=4, periods_=("DEV",))
    b1 = f1[0].read_bytes()
    f2, _c, _s = G.build_chunks(ser, tmp_path / "c", None, root=cache, log=logs.append, limit_days=4, periods_=("DEV",))
    assert any("reused" in s for s in logs) and f2[0].read_bytes() == b1
    m1, a1, r1 = G.load_chunk(f1[0])
    f1[0].unlink()
    f3, _c, _s = G.build_chunks(ser, tmp_path / "c", None, root=cache, log=None, limit_days=4, periods_=("DEV",))
    m3, a3, r3 = G.load_chunk(f3[0])
    assert m1 == m3 and r1 == r3 and set(a1) == set(a3) and all(np.array_equal(a1[k], a3[k], equal_nan=True) for k in a1)
    bad = dict(m1, version="other")
    assert G.load_chunk(f3[0], bad) is None


def test_locked_periods_are_refused_and_no_new_option_pull_is_needed(cache):
    for d in (date(2024, 2, 1), date(2024, 7, 31), date(2026, 7, 1), date(2026, 10, 30)):
        with pytest.raises(periods.LockedPeriod):
            G.check_day(d)
    with pytest.raises(periods.LockedPeriod):
        G.check_day(date(2015, 12, 1))                         # warm-up only: never a trade day
    G.check_day(DEV_DAYS[0])
    with pytest.raises(periods.LockedPeriod):
        shares.load_series("SPY", date(2024, 1, 1), date(2024, 8, 30), cache)
    import pull_alpaca as PA
    d0 = DEV_DAYS[0]
    quiet = SS.flat_day_df(d0, 500.0)                          # a quiet day: the +/-3% band holds everything
    assert G.needed_option_contracts("SPY", d0, quiet) == []
    df = data.read_stock("SPY", d0, d0, cache)
    rth = df[(df["ts"].dt.hour * 60 + df["ts"].dt.minute >= 570) & (df["ts"].dt.hour * 60 + df["ts"].dt.minute < 960)]
    hi, lo = float(rth["h"].max()), float(rth["l"].min())
    reach = max(G.NEED_REACH_MIN, G.NEED_REACH_PCT * hi)
    have = {s[-9:] for s in PA.symbols_for_day("SPY", d0, df)}
    want = [f"SPY{d0:%y%m%d}{sd}{k * 1000:08d}" for k in range(int(math.floor(lo - reach)), int(math.ceil(hi + reach)) + 1)
            for sd in ("C", "P") if f"{sd}{k * 1000:08d}" not in have]
    assert G.needed_option_contracts("SPY", d0, df) == want
    low = df.copy()
    for c in ("o", "h", "l", "c"):
        low[c] = low[c] / 5.0                                   # a $100 underlying: 15.3's $4.50 reach exceeds 3%
    need = G.needed_option_contracts("ABC", d0, low, expiry=d0 + timedelta(days=1))
    assert need and all(s.startswith(f"ABC{d0 + timedelta(days=1):%y%m%d}") for s in need)
    assert G.chunk_years("DEV") == [2024, 2025, 2026] and G.chunk_years("HIST")[0] == 2016
