"""Round 10, the noise band's own settings and its autopsy fixes (SPRINT_PLAN Addenda 15.1 and 15.2, sprint/r10noise.py):
the 162-cell grid in the listed order, each setting's rule (lookback with A1's 10-session minimum, VM in both bands, the
check interval, the three trailing stops), the fixes N1 / N2 / N12 (a blocked reversal only exits), the vectorized engine
equal to the scalar reference for every setting and fix (and NB-VOL's cell equal to round 8's shares.a1_day), no look-ahead
(future bars change neither earlier signals nor the 2016-2019 choice), the choice and its ties, Part A's 7-item bar per
holdout with the item-3 reading, the fix verdict, the universe rule, the locked-period refusals, the compounding wiring
and the trial counts (165; round 10 = 7,767). Synthetic data only."""
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import book, data, periods, shares
from sprint import r10noise as R

ET = "America/New_York"
DAY = date(2025, 3, 12)


# ---------------------------------------------------------------- synthetic bars
def synth_df(days, px0=300.0, seed=1, vol=0.0009, missing=0.003, v_share=0.35, bump=None):
    """Regular-hours 1-minute bars for `days` (early closes stop at 12:59), a random walk with a per-day drift, some
    V-shaped days (an up leg then a sharper down leg, or the mirror) so reversals happen, and a few missing minutes.
    bump: (first day, factor) multiplies every price from that day on (a change to the future)."""
    rng = np.random.default_rng(seed)
    ec = periods.early_closes()
    frames, px = [], px0
    for d in days:
        n = 210 if d.isoformat() in ec else 390
        o0 = px * (1 + rng.normal(0, 0.004))
        r = rng.normal(rng.normal(0, 0.00012), vol, n)
        if rng.uniform() < v_share:
            a = int(rng.integers(20, 150))
            b = int(rng.integers(a + 30, min(n, a + 200)))
            sg = 1 if rng.uniform() < 0.5 else -1
            r[a:b] += sg * 0.0006
            r[b:min(n, b + 150)] -= sg * 0.0009
        c = o0 * np.exp(np.cumsum(r))
        o = np.concatenate([[o0], c[:-1]])
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, vol / 3, n)))
        lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, vol / 3, n)))
        keep = rng.uniform(size=n) >= missing
        keep[0] = True
        f = 1.0
        if bump and d >= bump[0]:
            f = bump[1]
        ts = pd.Timestamp(f"{d} 09:30", tz=ET) + pd.to_timedelta(np.arange(n), unit="min")
        df = pd.DataFrame({"ts": ts, "o": (o * f).round(2), "h": (h * f).round(2), "l": (lo * f).round(2), "c": (c * f).round(2),
                           "v": rng.integers(1000, 9000, n).astype(float)})
        frames.append(df[keep])
        px = float(c[-1])
    return pd.concat(frames, ignore_index=True)


def sessions(a, b):
    return [date.fromisoformat(d) for d in book.sessions_between(a, b)]


def _series_from(days, opens, closes):
    rows = []
    for d, o, cs in zip(days, opens, closes):
        for i in range(390):
            if math.isnan(cs[i]):
                continue
            op = o if i == 0 else cs[i - 1] if not math.isnan(cs[i - 1]) else cs[i]
            rows.append((pd.Timestamp(f"{d} {(570 + i) // 60:02d}:{(570 + i) % 60:02d}", tz=ET), op, max(op, cs[i]) + 0.01,
                         min(op, cs[i]) - 0.01, cs[i], 1000.0))
    return data.Series("SPY", pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"]))


def _ctx(path, early=False):
    ctx, _ = SS.make_ctx(DAY, path, {0: 1.0}, prior_days=20, px=100.0, early=early)
    return ctx


def _bands(monkeypatch, ub=101.0, lb=99.0):
    monkeypatch.setattr(R, "bands", lambda s, d, vm=1.0, lookback=14: (np.full(390, ub), np.full(390, lb)))


def _sig(trades):
    return [(t["side"], t["decision_idx"], t["entry_idx"], t["exit_idx"]) for t in trades]


@pytest.fixture(scope="module")
def hist_world():
    days = sessions("2019-09-03", "2020-01-31")                    # includes the 2019-11-29 early close
    ser = data.Series("SPY", synth_df(days, seed=5))
    prep = R.Prep(ser, "HIST")
    cfgs = list(R.GRID_CFGS) + list(R.FIXES.values())
    tr = R.run_engine(prep, cfgs)
    return {"days": days, "ser": ser, "prep": prep, "cfgs": cfgs, "tr": tr, "per": R.by_cfg(tr, len(cfgs))}


# ---------------------------------------------------------------- the grid and the trials
def test_the_grid_is_162_cells_in_the_listed_order():
    assert (R.VMS, R.LOOKBACKS, R.INTERVALS, R.TRAILS, R.UNIVERSES) == ((1.0, 1.25, 1.5), (10, 14, 20), (15, 30, 60),
                                                                         ("band_vwap", "vwap", "band"), ("U3", "U7"))
    assert len(R.GRID) == 162 == len(set(R.CELL_IDS)) and len(R.GRID_CFGS) == 81
    assert R.GRID[0] == (R.Cfg(1.0, 10, 15, "band_vwap"), "U3") and R.GRID[1] == (R.Cfg(1.0, 10, 15, "band_vwap"), "U7")
    assert R.GRID[2][0].trail == "vwap" and R.GRID[6][0].interval == 30 and R.GRID[18][0].lookback == 14 and R.GRID[54][0].vm == 1.25
    assert R.GRID[-1] == (R.Cfg(1.5, 20, 60, "band"), "U7")
    assert R.BASE == R.Cfg(1.0, 14, 30, "band_vwap") and R.BASE_ID == "vm1.00-lb14-i30-band_vwap-U3" and R.BASE_ID in R.CELL_IDS
    assert R.U3 == ("SPY", "QQQ", "IWM") and R.U7 == ("SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "SMH")
    assert set(R.FIXES) == {"N1", "N2", "N12"} and R.FIXES["N12"] == R.Cfg(one_trade=True, last_entry=149)


def test_trials_are_165_round10_is_7767_and_the_dsr_uses_run_logs_plus_7767():
    assert sum(R.TRIALS.values()) == 165 == R.THIS_BUILD and sorted(R.TRIALS.values()) == [3, 162]
    assert sum(R.R10_TALLY.values()) == 7767 == R.ROUND10 and R.R10_TALLY["15.1"] == 162 and R.R10_TALLY["15.2"] == 3
    t = R.trials(1234)
    assert t["this_build"] == 165 and t["round10"] == 7767 and t["prior_in_run_logs"] == 1234 and t["total_for_dsr"] == 9001
    days = book.sessions_between(R.DEV_A, R.DEV_B)
    rng = np.random.default_rng(1)
    var = {}
    for k in range(3):
        dd = np.array(days[::3], dtype="U10")
        var[f"v{k}"] = {"day": dd, "pnl": rng.normal(0.5 * k, 10, len(dd))}
    var["dup"] = var["v1"]                                                   # a U7 cell that fell back to its U3 twin
    tab, sv, n, distinct = R.dsr_table(var, 1234)
    assert n == 9001 and distinct == 3 and sv > 0 and tab["dup"] == tab["v1"] and set(tab) == set(var)


def test_check_grids_and_the_n2_cutoff():
    assert R.CHECKS[30] == shares.CHECKS_A1 and R.CHECKS[15][:3] == (29, 44, 59) and R.CHECKS[15][-1] == 359
    assert R.CHECKS[60] == (29, 89, 149, 209, 269, 329) and len(R.CHECKS[15]) == 23
    assert R.N2_LAST_ENTRY == 149 and shares._t(R.N2_LAST_ENTRY + 1) == "12:00"     # the check bar 149 finishes at 12:00


# ---------------------------------------------------------------- the settings, one by one
def test_sigma_lookbacks_keep_the_at_least_10_minimum_and_vm_scales_both_bands():
    days = SS.weekdays(date(2025, 1, 6), 23)
    opens = [100.0] * 23
    closes = [np.full(390, 100.0 * (1 + 0.001 * (k + 1))) for k in range(23)]
    closes[18] = closes[18].copy()
    closes[18][300:] = np.nan                                               # one prior session without bars after 14:30
    s = _series_from(days, opens, closes)
    d = days[22]
    for lb in (10, 14, 20):
        prior = list(range(22 - lb, 22))
        assert R.sigma(s, d, lb)[100] == pytest.approx(np.mean([0.001 * (k + 1) for k in prior]))
        with_bar = [k for k in prior if k != 18]
        got = R.sigma(s, d, lb)[300]
        if lb == 10:
            assert np.isnan(got)                                            # 9 of 10 have a bar at t: under the minimum of 10
        else:
            assert got == pytest.approx(np.mean([0.001 * (k + 1) for k in with_bar]))
    assert np.allclose(R.sigma(s, d, 14), shares.a1_sigma(s, d), equal_nan=True)
    assert np.isnan(R.sigma(s, days[9], 20)[100]) and not np.isnan(R.sigma(s, days[10], 20)[100])   # 10 prior sessions suffice
    sig = R.sigma(s, d, 14)
    pc = float(closes[21][-1])
    for vm in R.VMS:
        ub, lb_ = R.bands(s, d, vm, 14)
        assert ub[100] == pytest.approx(max(100.0, pc) * (1 + vm * sig[100])) and lb_[100] == pytest.approx(min(100.0, pc) * (1 - vm * sig[100]))
    ub0, lb0 = shares.a1_bands(s, d)
    ub1, lb1 = R.bands(s, d, 1.0, 14)
    assert np.array_equal(ub0, ub1, equal_nan=True) and np.array_equal(lb0, lb1, equal_nan=True)


PATH = {0: 100.0, 29: 101.5, 59: 100.5, 89: 102.0, 119: 98.0, 149: 99.5, 179: 98.5, 389: 97.0}


def test_base_cell_is_round8_noise_sh_vol_on_a_hand_path(monkeypatch):
    _bands(monkeypatch)
    monkeypatch.setattr(shares, "a1_bands", lambda s, d: (np.full(390, 101.0), np.full(390, 99.0)))
    ctx = _ctx(PATH)
    ctx.vwap[:] = 100.0
    a = shares.a1_day(ctx, "DEV", "noise_sh_vol", notional=12_345.0)
    b = R.cell_day(ctx, "DEV", R.BASE, 12_345.0, "noise_sh_vol")
    assert a == b and _sig(a) == [("L", 29, 30, 60), ("L", 89, 90, 120), ("S", 119, 120, 150), ("S", 179, 180, 389)]
    c = R.cell_day(ctx, "DEV", R.BASE, 12_345.0, "x", sd=0.01)
    assert all(t["i_vol_sd"] == 0.01 for t in c) and R._norm(c) == R._norm(a)


def test_the_three_trailing_stops(monkeypatch):
    _bands(monkeypatch)                                                    # UB 101, LB 99
    ctx = _ctx({0: 100.0, 29: 101.5, 59: 100.5, 389: 100.5})
    ctx.vwap[:] = 100.2
    got = {tr: _sig(R.cell_day(ctx, "DEV", R.Cfg(trail=tr), 10_000.0)) for tr in R.TRAILS}
    assert got["band_vwap"][0] == ("L", 29, 30, 60) and got["band"][0] == ("L", 29, 30, 60)   # 100.5 < max(UB, VWAP) = UB = 101
    assert got["vwap"] == [("L", 29, 30, 389)]                                               # 100.5 > VWAP 100.2: hold
    ctx2 = _ctx({0: 100.0, 29: 101.5, 59: 101.4, 389: 101.4})
    ctx2.vwap[:] = 101.8
    got2 = {tr: _sig(R.cell_day(ctx2, "DEV", R.Cfg(trail=tr), 10_000.0)) for tr in R.TRAILS}
    assert got2["band_vwap"][0] == ("L", 29, 30, 60) and got2["vwap"][0] == ("L", 29, 30, 60)   # 101.4 < VWAP 101.8
    assert got2["band"] == [("L", 29, 30, 389)]                                              # 101.4 > UB 101: hold
    ctx3 = _ctx({0: 100.0, 29: 98.5, 59: 99.5, 389: 99.5})                                     # shorts mirror
    ctx3.vwap[:] = 99.8
    got3 = {tr: _sig(R.cell_day(ctx3, "DEV", R.Cfg(trail=tr), 10_000.0)) for tr in R.TRAILS}
    assert got3["band_vwap"][0] == ("S", 29, 30, 60) and got3["band"][0] == ("S", 29, 30, 60) and got3["vwap"] == [("S", 29, 30, 389)]
    assert "VWAP" in R.cell_day(ctx2, "DEV", R.Cfg(trail="vwap"), 10_000.0)[0]["exit_reason"]
    ctx.vwap[:] = np.nan                                                   # no VWAP: every variant falls back to the band
    assert {tr: _sig(R.cell_day(ctx, "DEV", R.Cfg(trail=tr), 10_000.0))[0] for tr in R.TRAILS} == {tr: ("L", 29, 30, 60) for tr in R.TRAILS}


def test_the_check_interval_decides_only_at_its_checks(monkeypatch):
    _bands(monkeypatch)
    ctx = _ctx({0: 100.0, 40: 101.5, 389: 101.5})
    ctx.vwap[:] = 100.0
    first = {iv: _sig(R.cell_day(ctx, "DEV", R.Cfg(interval=iv), 10_000.0))[0] for iv in R.INTERVALS}
    assert first == {15: ("L", 44, 45, 389), 30: ("L", 59, 60, 389), 60: ("L", 89, 90, 389)}
    e = _ctx({0: 100.0, 29: 101.5, 59: 100.5, 89: 102.0, 194: 102.0}, early=True)
    e.vwap[:] = 100.0
    for iv in R.INTERVALS:
        tr = R.cell_day(e, "DEV", R.Cfg(interval=iv), 10_000.0)
        assert max(t["decision_idx"] for t in tr) < 209 and tr[-1]["exit_idx"] == 209 and tr[-1]["exit_reason"] == "CLOSE 12:59 bar"


def test_fixes_n1_n2_n12_and_blocked_reversals(monkeypatch):
    _bands(monkeypatch)
    ctx = _ctx(PATH)
    ctx.vwap[:] = 100.0
    got = {fx: _sig(R.cell_day(ctx, "DEV", c, 10_000.0)) for fx, c in R.FIXES.items()}
    assert got["N1"] == [("L", 29, 30, 60)]                                         # after the first exit, no re-entry
    assert got["N2"] == [("L", 29, 30, 60), ("L", 89, 90, 120), ("S", 119, 120, 150)]  # no entry at 12:30 (179)
    assert got["N12"] == [("L", 29, 30, 60)]
    rv = _ctx({0: 100.0, 29: 101.5, 59: 98.0, 389: 97.0})                           # the first trade reverses at 10:30
    rv.vwap[:] = 100.0
    base = R.cell_day(rv, "DEV", R.BASE, 10_000.0)
    assert _sig(base) == [("L", 29, 30, 60), ("S", 59, 60, 389)] and base[0]["exit_reason"] == "NOISE REVERSAL"
    n1 = R.cell_day(rv, "DEV", R.FIXES["N1"], 10_000.0)
    assert _sig(n1) == [("L", 29, 30, 60)] and n1[0]["exit_reason"] == R.REVX_TXT     # a blocked reversal only exits
    late = _ctx({0: 100.0, 149: 101.5, 179: 98.0, 389: 97.0})                       # entry at the 12:00 check itself is allowed
    late.vwap[:] = 100.0
    n2 = R.cell_day(late, "DEV", R.FIXES["N2"], 10_000.0)
    assert _sig(n2) == [("L", 149, 150, 180)] and n2[0]["exit_reason"] == R.REVX_TXT
    assert _sig(R.cell_day(late, "DEV", R.BASE, 10_000.0)) == [("L", 149, 150, 180), ("S", 179, 180, 389)]


# ---------------------------------------------------------------- the vectorized engine
def _engine_rows(world, ci, d):
    t = world["per"][ci]
    j = np.nonzero(t["day"] == d.isoformat())[0]
    return shares.ordered(R.to_rows(R.ordered({k: v[j] for k, v in t.items()}), "x", world["cfgs"][ci].trail))


def test_engine_equals_the_scalar_reference_for_every_setting_and_fix(hist_world):
    w = hist_world
    ser, prep = w["ser"], w["prep"]
    days = [d for k, d in enumerate(prep.days) if prep.trade[k]]
    assert days[0] == date(2019, 9, 3) and date(2019, 11, 29) in days        # HIST trade days; an early close inside
    whys = set(w["tr"]["why"].tolist())
    assert {R.STOP, R.REV, R.CLOSE, R.REVX} <= whys                          # stops, reversals, closes and blocked reversals
    n = 0
    for ci, cfg in enumerate(w["cfgs"]):
        for d in days[::2]:
            ctx = data.DayContext(ser, d, {}, None)
            want = shares.ordered(R.cell_day(ctx, "HIST", cfg, shares.a1_vol_notional(ser, d), sd=R.vol_sd(ser, d)))
            assert R._norm(want) == R._norm(_engine_rows(w, ci, d)), (cfg.key, d)
            n += 1
    assert n == len(w["cfgs"]) * len(days[::2]) > 4000
    bi = w["cfgs"].index(R.BASE)
    for d in days:                                                           # NB-VOL's cell is round 8's noise_sh_vol
        ctx = data.DayContext(ser, d, {}, None)
        a1 = shares.ordered(shares.a1_day(ctx, "HIST", "noise_sh_vol", notional=shares.a1_vol_notional(ser, d)))
        assert R._norm(a1) == R._norm(_engine_rows(w, bi, d))
    sc = R.self_check(ser, prep, w["tr"], w["cfgs"], sample=[0, 40, 80, 81, 82, 83], every=7)
    assert sc["base_mismatch"] == 0 and sc["sample_mismatch"] == 0 and sc["base_days"] == len(days) and sc["sample_days"] > 0


def test_to_rows_has_round8s_trade_columns(hist_world):
    w = hist_world
    bi = w["cfgs"].index(R.BASE)
    rows = R.to_rows(R.by_cfg(w["tr"], len(w["cfgs"]))[bi], "NB-VOL", "band_vwap")
    d = date.fromisoformat(rows[0]["day"])
    a1 = shares.a1_day(data.DayContext(w["ser"], d, {}, None), "HIST", "noise_sh_vol", notional=shares.a1_vol_notional(w["ser"], d))
    assert set(rows[0]) == set(a1[0]) | {"i_vol_sd"} and rows[0]["variant"] == "NB-VOL"
    assert rows[0]["i_vol_sd"] == pytest.approx(R.vol_sd(w["ser"], d))
    assert rows[0]["notional"] == pytest.approx(10_000 * min(4, 0.02 / rows[0]["i_vol_sd"]), abs=0.01)


def test_the_engine_has_no_look_ahead():
    days = sessions("2019-10-01", "2019-12-31")
    D = days[50]
    base = synth_df(days, seed=9)
    cfgs = list(R.GRID_CFGS) + list(R.FIXES.values())
    t0 = R.run_engine(R.Prep(data.Series("SPY", base), "HIST"), cfgs)
    for cut in (120, 240):
        alt = base.copy()
        mins = alt["ts"].dt.hour * 60 + alt["ts"].dt.minute - 570
        later = (alt["ts"].dt.date > D) | ((alt["ts"].dt.date == D) & (mins > cut))
        for col in ("o", "h", "l", "c"):
            alt.loc[later, col] = (alt.loc[later, col] * 1.04).round(2)
        t1 = R.run_engine(R.Prep(data.Series("SPY", alt), "HIST"), cfgs)
        for a, b in ((t0, t1),):
            ka = {(int(c), str(d), int(i), int(k), float(r), int(s)) for c, d, i, k, r, s in
                  zip(a["cfg"], a["day"], a["dec"], a["k_in"], a["ref_in"], a["sign"]) if d < D.isoformat() or (d == D.isoformat() and i < cut)}
            kb = {(int(c), str(d), int(i), int(k), float(r), int(s)) for c, d, i, k, r, s in
                  zip(b["cfg"], b["day"], b["dec"], b["k_in"], b["ref_in"], b["sign"]) if d < D.isoformat() or (d == D.isoformat() and i < cut)}
            assert ka == kb and len(ka) > 100
        full_a = {(int(c), str(d), int(i), int(x), float(p)) for c, d, i, x, p in zip(t0["cfg"], t0["day"], t0["dec"], t0["k_out"], t0["pnl"])
                  if d < D.isoformat()}
        full_b = {(int(c), str(d), int(i), int(x), float(p)) for c, d, i, x, p in zip(t1["cfg"], t1["day"], t1["dec"], t1["k_out"], t1["pnl"])
                  if d < D.isoformat()}
        assert full_a == full_b                                              # earlier days' trades, exits and P/L unchanged


def test_trades_only_inside_their_own_period():
    days = sessions("2024-06-24", "2024-07-31") + sessions("2024-08-01", "2024-09-30")   # July 2024 is L2
    ser = data.Series("SPY", synth_df(days, seed=3))
    prep = R.Prep(ser, "DEV")
    tr = R.run_engine(prep, [R.BASE])
    assert len(tr["pnl"]) and min(tr["day"]) >= "2024-08-01" and (prep.trade == np.array([d >= date(2024, 8, 1) for d in days])).all()
    h = R.Prep(data.Series("SPY", synth_df(sessions("2015-11-02", "2016-02-29"), seed=4)), "HIST")
    th = R.run_engine(h, [R.BASE])
    assert len(th["pnl"]) and min(th["day"]) >= "2016-01-04"                # the warm-up feeds sigma and sizing only


# ---------------------------------------------------------------- the choice
def _crow(cid, order, sh, n, h1=0.1, h2=0.1):
    return {"cell": cid, "order": order, "discovery": {"trades": n, "sharpe": sh}, "holdout1": {"sharpe": h1}, "holdout2": {"sharpe": h2}}


def test_choice_needs_1000_trades_and_breaks_ties():
    rows = [_crow("a", 0, 1.5, 999), _crow("b", 1, 0.9, 1500), _crow("c", 2, 1.2, 1000), _crow("d", 3, 1.2, 1200), _crow("e", 4, 1.2, 1200)]
    assert R.choose(rows)[0] == "d"                                         # 'a' has 999 trades; tie at 1.2 -> more trades -> order
    assert R.choose(rows, min_trades=1600)[0] is None and "no cell" in R.choose(rows, min_trades=1600)[1]
    assert R.choose([_crow("x", 0, None, 5000)])[0] is None
    assert R.MIN_DISC_TRADES == 1000


def test_the_choice_never_reads_2020_or_later(hist_world):
    w = hist_world
    per = R.by_cfg(w["tr"], len(w["cfgs"]))
    cells = {cid: R.ordered(per[w["cfgs"].index(c)]) for (c, _u), cid in zip(R.GRID, R.CELL_IDS)}
    g0 = R.evaluate_grid(cells, "U3", min_trades=50)
    assert g0["chosen"] is not None and g0["rows"][0]["discovery"]["trades"] > 0 and g0["rows"][0]["holdout1"]["trades"] > 0
    alt = synth_df(w["days"], seed=5, bump=(date(2020, 1, 2), 1.07))       # every price from 2020 on changes
    alt.loc[alt["ts"].dt.date >= date(2020, 1, 2), "c"] *= 1.0
    rng = np.random.default_rng(0)
    m = (alt["ts"].dt.date >= date(2020, 1, 2)).to_numpy()
    alt.loc[m, "c"] = (alt.loc[m, "c"] * (1 + rng.normal(0, 0.002, m.sum()))).round(2)
    ser2 = data.Series("SPY", alt)
    tr2 = R.run_engine(R.Prep(ser2, "HIST"), w["cfgs"])
    per2 = R.by_cfg(tr2, len(w["cfgs"]))
    cells2 = {cid: R.ordered(per2[w["cfgs"].index(c)]) for (c, _u), cid in zip(R.GRID, R.CELL_IDS)}
    g1 = R.evaluate_grid(cells2, "U3", min_trades=50)
    assert [r["discovery"] for r in g0["rows"]] == [r["discovery"] for r in g1["rows"]] and g0["chosen"] == g1["chosen"]
    assert [r["holdout1"] for r in g0["rows"]] != [r["holdout1"] for r in g1["rows"]]   # the change did reach 2020


# ---------------------------------------------------------------- Part A's 7-item bar per holdout
def _wtrades(a, b, n_every=2, win=0.8, move=0.5, seed=1, bad_years=()):
    rng = np.random.default_rng(seed)
    out = []
    for k, d in enumerate(book.sessions_between(a, b)[::n_every]):
        for s in ("SPY", "QQQ"):
            m = move if rng.uniform() < win else -move
            if d[:4] in bad_years:
                m = -abs(move)
            out.append({"variant": "x", "symbol": s, "day": d, "side": "L", "sign": 1, "entry_idx": 30, "exit_idx": 389, "shares": 100,
                        "move": m, "pnl": 100 * (m - 0.02), "pnl_2x": 100 * (m - 0.04), "bps": 1.0, "notional": 10_000.0, "i_vol_sd": 0.01})
    return out


def test_window_bar_item3_reading_and_the_other_items():
    good = R.window_bar(_wtrades(*R.H1), "holdout1")
    assert good["pass"] and len(good["checks"]) == 7 and "3 of the 4 years 2020-2023" in good["checks"][2][0]
    assert set(good["years"]) == {"2020", "2021", "2022", "2023"} and good["window"] == "2020-01-01..2024-01-31"
    one_bad = R.window_bar(_wtrades(*R.H1, bad_years=("2021",)), "holdout1")
    assert one_bad["checks"][2][1]                                          # 3 of 4 years is enough
    two_bad = R.window_bar(_wtrades(*R.H1, bad_years=("2021", "2022")), "holdout1")
    assert not two_bad["checks"][2][1] and not two_bad["pass"]
    dev = R.window_bar(_wtrades(*R.H2), "holdout2")
    assert dev["pass"] and "profitable in DEV" in dev["checks"][2][0] and dev["years"] == {}
    lose = R.window_bar(_wtrades(*R.H2, win=0.3), "holdout2")
    assert not lose["checks"][2][1]
    thin = R.window_bar(_wtrades(*R.H2, n_every=12), "holdout2")
    assert not thin["checks"][0][1]                                          # fewer than 300 trades
    coin = R.window_bar(_wtrades(*R.H1, win=0.5, seed=4), "holdout1")
    assert not coin["checks"][5][1]                                          # no edge over random direction
    assert R.window_bar(_wtrades(*R.H1), "holdout1") == good                 # seeded: identical on a re-run
    rows = _wtrades(*R.H1) + _wtrades(*R.H2)
    assert R.window_bar(rows, "holdout1")["stats"]["trades"] == good["stats"]["trades"]   # only the window's own trades
    assert good["sharpe"] == R.daily_sharpe(shares.daily(shares.ordered(_wtrades(*R.H1)), book.sessions_between(*R.H1)))


def test_windows_never_touch_the_locked_periods():
    for a, b in R.WINDOWS.values():
        assert not periods.overlaps(a, b)
    with pytest.raises(periods.LockedPeriod):
        R.window_bar([], ("2024-01-02", "2024-03-01"))                         # L2
    with pytest.raises(periods.LockedPeriod):
        R.window_bar([], ("2026-06-01", "2026-07-15"))                         # L1
    with pytest.raises(periods.LockedPeriod):
        shares.load_series("SPY", date(2024, 1, 2), date(2024, 2, 5))


# ---------------------------------------------------------------- the universe and the verdicts
def test_universe_rule():
    full = {s: {w: len(book.sessions_between(*R.WINDOWS[w])) for w in R.WINDOWS} for s in R.U7}
    used, missing, warn = R.universe_choice(full)
    assert used == "U7" and missing == [] and warn == []
    part = dict(full, SMH={"discovery": 0, "holdout1": 500, "holdout2": 400})
    used, missing, _w = R.universe_choice(part)
    assert used == "U3" and missing == [("SMH", "discovery")]
    used, missing, _w = R.universe_choice({s: full[s] for s in R.U3})
    assert used == "U3" and len(missing) == 12
    thin = dict(full, XLF=dict(full["XLF"], holdout2=10))
    used, _m, warn = R.universe_choice(thin)
    assert used == "U7" and len(warn) == 1 and "XLF" in warn[0]


def _fake_bar(table):
    def wb(rows, key):
        name = rows[0]["variant"] if rows else "?"
        sh, ok = table[name][key]
        return {"sharpe": sh, "pass": ok, "checks": [("x", ok)], "stats": {}, "window": key}
    return wb


def test_a_fix_holds_only_with_the_bar_and_a_better_sharpe_in_both_holdouts(monkeypatch):
    table = {"NB-VOL": {"holdout1": (0.5, False), "holdout2": (0.4, False)},
             "N1": {"holdout1": (0.9, True), "holdout2": (0.6, True)},            # holds
             "N2": {"holdout1": (0.9, True), "holdout2": (0.3, True)},            # bar both, Sharpe only in holdout 1
             "N12": {"holdout1": (0.9, True), "holdout2": (0.8, False)}}          # Sharpe both, bar fails holdout 2
    monkeypatch.setattr(R, "window_bar", _fake_bar(table))
    monkeypatch.setattr(R, "compounding", lambda rows, key: {"window": key})
    rows = {k: [{"variant": k, "day": "2020-01-02", "pnl": 1.0}] for k in table}
    out = R.evaluate_fixes(rows)
    f = out["fixes"]
    assert f["N1"]["holds"] and f["N1"]["compounding"] == {"holdout1": {"window": "holdout1"}, "holdout2": {"window": "holdout2"}}
    assert not f["N2"]["holds"] and f["N2"]["bar_both"] and f["N2"]["beats_sharpe"] == {"holdout1": True, "holdout2": False}
    assert not f["N12"]["holds"] and not f["N12"]["bar_both"] and f["N12"]["beats_sharpe"] == {"holdout1": True, "holdout2": True}
    assert f["N2"]["compounding"] is None and not out["NB-VOL"]["pass"]


def test_the_compounding_view_is_wired_only_for_a_pass(hist_world, monkeypatch):
    w = hist_world
    per = R.by_cfg(w["tr"], len(w["cfgs"]))
    cells = {cid: R.ordered(per[w["cfgs"].index(c)]) for (c, _u), cid in zip(R.GRID, R.CELL_IDS)}
    g = R.evaluate_grid(cells, "U3", min_trades=50)
    assert not g["pass"] and g["compounding"] is None                        # synthetic: far fewer than 300 trades
    real = R.window_bar
    monkeypatch.setattr(R, "window_bar", lambda rows, key: dict(real(rows, key), pass_=True, **{"pass": True}))
    g2 = R.evaluate_grid(cells, "U3", min_trades=50)
    assert g2["pass"] and set(g2["compounding"]) == {"holdout1", "holdout2"}
    v = g2["compounding"]["holdout1"]
    assert list(v["fractions"]) == ["1%", "2%", "5%"] and v["input"]["sessions"] == len(book.sessions_between(*R.H1))
    assert v["input"]["trades"] == g2["holdouts"]["holdout1"]["stats"]["trades"] and "notional x the 14-day sd" in v["label"]
    rows = g2["_rows"]
    h1 = [r for r in rows if R.H1[0] <= r["day"] <= R.H1[1]]
    r0 = h1[0]
    assert v["input"]["mean_r_trade"] == pytest.approx(round(np.mean([r["pnl"] / (r["notional"] * r["i_vol_sd"]) for r in h1]), 4), abs=1e-4)
    assert r0["notional"] * r0["i_vol_sd"] == pytest.approx(200.0, rel=1e-3) or r0["notional"] == pytest.approx(40_000.0)


def test_grid_table_share_positive_and_by_setting(hist_world):
    w = hist_world
    per = R.by_cfg(w["tr"], len(w["cfgs"]))
    cells = {cid: R.ordered(per[w["cfgs"].index(c)]) for (c, _u), cid in zip(R.GRID, R.CELL_IDS)}
    g = R.evaluate_grid(cells, "U3")
    assert g["chosen"] is None and "1,000" in g["choice_why"] and g["holdouts"] is None
    rows = g["rows"]
    assert [r["cell"] for r in rows] == list(R.CELL_IDS) and all(r["universe_used"] == "U3" for r in rows)
    sp = g["share_positive"]
    assert sp["holdout1"]["of"] == 162 and sp["holdout1"]["cells"] == sum(1 for r in rows if (r["holdout1"]["sharpe"] or 0) > 0)
    assert set(g["by_setting"]) == {"vm", "lookback", "interval", "trail", "universe"} and list(g["by_setting"]["trail"]) == list(R.TRAILS)
    b = rows[R.CELL_IDS.index(R.BASE_ID)]["discovery"]
    t = R.window(cells[R.BASE_ID], *R.DISC)
    assert b["trades"] == len(t["pnl"]) and b["total"] == pytest.approx(round(float(t["pnl"].sum()), 2))
    assert b["sharpe"] == R.daily_sharpe(R.daily_a(t, book.sessions_between(*R.DISC)))
