"""Round 8, Part B (SPRINT_PLAN Amendment 10, Addendum 10.1): the seven B1 features (values, no look-ahead, re-stamping run-7
rows without touching P/L), B2 confidence sizing (terciles of the training predictions, out-of-sample only, walk-forward:
later months never change earlier decisions, the three checks), the B3 newhigh_c entry (window, strict new high, rvol >= 1.06,
one a day, early close, no look-ahead), B4's fixed stop + gb50 trail, the rvol_ge106 filter and the 'steadier than FIN-H'
readout. Synthetic data only."""
import copy
import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import book, data, engine, entries, features, learn, round8, runner
from sprint.sim import ExitCfg, simulate

DAY = date(2025, 3, 12)
ET = "America/New_York"


# ---------------------------------------------------------------- B1 features
def _daily_series(prices, day_path=None, opens=None):
    """A Series of len(prices) weekdays; day k's bars all sit at prices[k] (opening at opens[k] if given); the last day follows
    day_path (idx -> close, carried) when given."""
    days = SS.weekdays(date(2025, 1, 6), len(prices))
    rows = []
    for k, (d, p) in enumerate(zip(days, prices)):
        cur = (opens or {}).get(k, p)
        for i in range(390):
            if k == len(prices) - 1 and day_path is not None and i in day_path:
                cur = day_path[i]
            elif k != len(prices) - 1 or day_path is None:
                cur = p if i else (opens or {}).get(k, p)
            rows.append((pd.Timestamp(f"{d} {(570 + i) // 60:02d}:{(570 + i) % 60:02d}", tz=ET), cur, cur + 0.05, cur - 0.05, cur, 1000.0))
    return days, data.Series("SPY", pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"]))


def _vixy(days, vals):
    return pd.Series(vals, index=[days[0] - timedelta(days=len(vals) - len(days) - k) if k < len(vals) - len(days) else days[k - (len(vals) - len(days))]
                                  for k in range(len(vals))])


def test_b1_features_values():
    prices = [100.0 + k * 0.5 for k in range(24)]
    prices[10] = 120.0                                                      # the 20-session high
    path = {0: 113.0, 10: 113.6, 29: 112.8, 40: 114.0, 50: 113.9}
    days, s = _daily_series(prices, day_path=path)
    vals = [20.0 + 0.3 * k for k in range(40)]
    vd = _vixy(days, vals)
    d = days[-1]
    ctx = data.DayContext(s, d, {}, None, aux={"VIXY_D": vd})
    f = features.new_features(ctx, 40, "C")
    c = s.daily["close"].to_numpy(float)
    assert f["f_ret5d"] == pytest.approx(round((c[-2] / c[-7] - 1) * 100, 4))
    assert features.new_features(ctx, 40, "P")["f_ret5d"] == pytest.approx(-f["f_ret5d"])           # side-signed
    assert f["f_dd20"] == pytest.approx(round((c[-2] / max(c[-21:-1]) - 1) * 100, 4)) and f["f_dd20"] < 0
    assert f["f_gap_abs"] == pytest.approx(round(abs(113.0 / c[-2] - 1) * 100, 4))
    hi, lo = float(np.nanmax(ctx.h[:30])), float(np.nanmin(ctx.l[:30]))
    assert f["f_or30_atr"] == pytest.approx(round((hi - lo) / s.daily_atr(d), 4))
    assert features.new_features(ctx, 28, "C")["f_or30_atr"] is None                                # range not complete yet
    assert f["f_hod"] == 1 and features.new_features(ctx, 50, "C")["f_hod"] == 0                     # 113.9 < the 40 bar's high
    v = vd.to_numpy()
    p = list(vd.index).index(days[-2])
    assert f["f_vixy_chg1"] == pytest.approx(round((v[p] / v[p - 1] - 1) * 100, 4))
    assert f["f_vixy_z20"] == pytest.approx(round((v[p] - v[p - 20:p].mean()) / np.std(v[p - 20:p], ddof=1), 4))
    assert features.FEATURES[:18] == features.FEATURES18 and features.FEATURES[18:] == features.NEW7 and len(features.FEATURES) == 25
    full = features.entry_features(ctx, 40, "C")
    assert all(full[k] == f[k] for k in features.NEW7)                                               # stamped on every engine trade
    first = data.DayContext(s, days[3], {}, None, aux={"VIXY_D": vd})
    g = features.new_features(first, 40, "C")
    assert g["f_ret5d"] is None and g["f_dd20"] is None                                              # not enough history: empty


def test_b1_features_have_no_look_ahead():
    prices = [100.0 + math.sin(k) for k in range(26)]
    days, s = _daily_series(prices, day_path={0: 100.5, 20: 101.0, 60: 100.2})
    vd = _vixy(days, [20.0 + math.cos(k) for k in range(45)])
    want = features.new_features(data.DayContext(s, days[-1], {}, None, aux={"VIXY_D": vd}), 60, "C")
    s2 = copy.deepcopy(s)
    s2.rth[days[-1]][61:, :4] *= 1.07                                                                # every later bar moves
    vd2 = vd.copy()
    vd2.iloc[-1] *= 3.0                                                                              # today's VIXY close (not known yet)
    got = features.new_features(data.DayContext(s2, days[-1], {}, None, aux={"VIXY_D": vd2}), 60, "C")
    assert got == want


def test_b1_restamp_fills_only_the_missing_features_and_keeps_pnl():
    prices = [100.0 + 0.2 * k for k in range(26)]
    days, s = _daily_series(prices, day_path={0: 105.5, 89: 106.0})
    vd = _vixy(days, [20.0 + 0.1 * k for k in range(45)])
    rows = [{"symbol": "SPY", "day": days[-1].isoformat(), "signal_idx": 89, "side": "C", "pnl": -12.5, "_src": "DEV"},
            {"symbol": "SPY", "day": days[-2].isoformat(), "signal_idx": 89, "side": "C", "pnl": 40.0, "_src": "DEV",
             **{k: 7.0 for k in features.NEW7}}]
    n = features.restamp(rows, {("DEV", "SPY"): s}, {"VIXY_D": vd})
    assert n == 1 and rows[0]["pnl"] == -12.5 and rows[1] == dict(rows[1], **{k: 7.0 for k in features.NEW7})
    want = features.new_features(data.DayContext(s, days[-1], {}, None, aux={"VIXY_D": vd}), 89, "C")
    assert {k: rows[0][k] for k in features.NEW7} == want
    assert features.restamp(rows, {("DEV", "SPY"): s}, {"VIXY_D": vd}) == 0


# ---------------------------------------------------------------- B2 confidence sizing
def _sleeve(seed=3, edge=25.0, months=60):
    rng = np.random.default_rng(seed)
    out = []
    days = book.sessions_between("2016-01-04", "2024-01-31")[::4] + book.sessions_between("2024-08-01", "2026-06-30")[::4]
    for d in days:
        f = {k: float(rng.normal()) for k in features.FEATURES}
        f["f_minute"] = 90.0
        e = edge if f["f_rvol"] > 0.5 else 0.0
        pnl = float(rng.normal(-3 + e, 30))
        out.append(dict(f, symbol="SPY", day=d, side="C", signal_idx=89, entry_time="11:01", exit_time="15:25", pnl=pnl, pnl_2x=pnl - 2,
                        _src="HIST" if d <= "2024-01-31" else "DEV"))
    return out


def test_b2_sizes_from_terciles_of_the_training_predictions():
    rows = _sleeve()
    sized, info = round8.b2_sizing(rows)
    months = sorted({r["day"][:7] for r in rows})
    assert info["oos_from"] == months[24] and min(r["day"] for r in sized) >= months[24]
    assert len(sized) == sum(1 for r in rows if r["day"][:7] >= months[24]) and {r["contracts"] for r in sized} == {0, 1, 2}
    tm = months[40]                                                          # one month by hand, with learn's own functions
    ordered = sorted(rows, key=lambda r: (r["day"], r["f_minute"]))
    tr = [r for r in ordered if r["day"][:7] < tm]
    te = [r for r in ordered if r["day"][:7] == tm]
    X, Y = features.matrix(tr), features.matrix(te)
    p = learn._prep_fit(X)
    w, b = learn.fit_logit(learn._prep_apply(p, X), np.array([r["pnl"] > 0 for r in tr], float))
    ptr = 1 / (1 + np.exp(-np.clip(learn._prep_apply(p, X) @ w + b, -30, 30)))
    pte = 1 / (1 + np.exp(-np.clip(learn._prep_apply(p, Y) @ w + b, -30, 30)))
    q1, q2 = np.quantile(ptr, [1 / 3, 2 / 3])
    want = [0 if x <= q1 else 2 if x >= q2 else 1 for x in pte]
    assert [r["contracts"] for r in sized if r["day"][:7] == tm] == want
    c = next(x for x in info["cuts"] if x["month"] == tm)
    assert (c["lower"], c["upper"]) == pytest.approx((q1, q2))


def test_b2_later_months_never_change_earlier_decisions():
    rows = _sleeve(seed=5)
    sized, _ = round8.b2_sizing(rows)
    rng = np.random.default_rng(9)
    late = [dict(r, pnl=float(rng.normal(80, 50)), f_rvol=float(rng.normal(0, 9))) if r["day"] >= "2022-01-01" else r for r in rows]
    sized2, _ = round8.b2_sizing(late)
    a = [(r["day"], r["contracts"]) for r in sized if r["day"] < "2022-01-01"]
    assert a and a == [(r["day"], r["contracts"]) for r in sized2 if r["day"] < "2022-01-01"]


def test_b2_window_checks_and_a_planted_edge():
    rows = _sleeve(seed=7, edge=40.0)
    res, books = round8.b2({"otm_c_1100": rows})
    o = res["otm_c_1100"]
    for w in ("dev", "hist"):
        x = o[w]
        assert [n.split(" ")[0] for n, _ in x["checks"]] == ["(a)", "(b)", "(c)"]
        assert x["trades"] == x["taken"] + x["skipped"] and x["contracts"] == x["taken"] + x["doubled"]
    assert o["hist"]["window"].startswith("2018-01-02") and o["dev"]["window"] == "2024-08-01..2026-06-30"
    assert o["dev"]["per_contract_sized"] > o["dev"]["per_contract_flat"] and o["pass"]
    assert all(r["pnl"] != 0 for r in books["otm_c_1100"]) and all(r["contracts"] in (1, 2) for r in books["otm_c_1100"])
    few = round8.b2({"x": rows[:50]})[0]["x"]
    assert few["pass"] is False and "error" in few


# ---------------------------------------------------------------- B3 newhigh_c
def _ctx(path, vol=None, early=False, prior_days=14):
    ctx, _ = SS.make_ctx(DAY, path, {0: 1.0}, prior_days=prior_days, vol=vol, early=early)
    return ctx


HI = {i: 1100.0 for i in range(390)}


def test_newhigh_c_first_strict_new_high_in_window_with_rvol():
    s = entries.signals(_ctx({0: 500.0, 100: 501.0, 150: 502.0}, vol=HI), "newhigh_c")
    assert [(x.side, x.idx, x.price) for x in s] == [("C", 100, 501.0)] and s[0].info["rvol"] >= 1.06
    assert entries.signals(_ctx({0: 500.0, 100: 501.0}), "newhigh_c") == []                    # rvol 1.0 < 1.06
    assert entries.signals(_ctx({0: 500.0, 50: 501.0}, vol=HI), "newhigh_c") == []             # the high came before 11:00
    assert entries.signals(_ctx({0: 500.0, 280: 502.0}, vol=HI), "newhigh_c") == []            # after 14:00
    assert entries.signals(_ctx({0: 500.0, 100: 500.01}, vol=HI), "newhigh_c") == []           # equal to the high: not above
    late_vol = {i: (1000.0 if i < 120 else 4000.0) for i in range(390)}
    s = entries.signals(_ctx({0: 500.0, 100: 501.0, 150: 502.0}, vol=late_vol), "newhigh_c")
    assert [x.idx for x in s] == [150]                                                           # the first bar meeting both
    assert entries.signals(_ctx({0: 500.0, 100: 501.0}, vol=HI), "newhigh_c", "P") == []
    e = _ctx({0: 500.0, 208: 501.0}, vol=HI, early=True)
    assert entries.signals(e, "newhigh_c") == []                                                 # 1:00 PM close: stops at bar 207
    assert entries.ENTRY_WINDOWS["newhigh_c"] == (89, 269) and "newhigh_c" in entries.SETUPS


def test_newhigh_c_has_no_look_ahead():
    base = {0: 500.0, 95: 500.5, 130: 501.2, 200: 500.0}
    want = [(x.idx, x.price) for x in entries.signals(_ctx(base, vol=HI), "newhigh_c")]
    assert want == [(95, 500.5)]
    for cut in (95, 96, 130):
        p2 = {k: v for k, v in base.items() if k <= cut}
        p2.update({cut + 1: 490.0, cut + 9: 530.0})
        assert [(x.idx, x.price) for x in entries.signals(_ctx(p2, vol=HI), "newhigh_c") if x.idx <= cut] == want


# ---------------------------------------------------------------- B4: fixed stop + gb50, the filter, the readout
def test_fixed_stop_with_a_gb50_trail_gives_back_half_the_peak():
    path = {0: 1.00, 120: 1.50, 150: 2.00, 180: 1.80, 200: 1.55, 220: 1.45}
    ctx, tape = SS.make_ctx(DAY, {0: 500.0}, path, prior_days=3)
    sig = entries.Signal("time_1100", "SPY", DAY, "C", 89, 500.0, None, {})
    info = {"symbol": tape.symbol, "px": 1.0, "iv": 0.2, "delta": 0.07}
    gb = simulate(ctx, sig, ExitCfg(stop="fixed", fixed_stop=0.5, fixed_target=99.0, trail="gb50", contract="d03-12t07", time="b"),
                  None, tape, info)
    plain = simulate(ctx, sig, ExitCfg(stop="fixed", fixed_stop=0.5, fixed_target=99.0, contract="d03-12t07", time="b"), None, tape, info)
    C = 1.00 + 0.01 + 0.0065
    peak_profit = (2.005 - 0.01 - 0.0065) - C
    trig = C + 0.5 * peak_profit + 0.01 + 0.0065                                                  # the traded price giving back half
    assert gb["exit_reason"] == "GIVEBACK STOP" and gb["exit_idx"] == 220 and gb["legs"][0]["basis"] == pytest.approx(min(trig, 1.45), abs=1e-6)
    assert plain["exit_reason"].startswith("ALL OUT") and gb["pnl"] > 0
    stop = simulate(ctx, sig, ExitCfg(stop="fixed", fixed_stop=0.5, fixed_target=99.0, trail="gb50", contract="d03-12t07"), None,
                    SS.make_ctx(DAY, {0: 500.0}, {0: 1.00, 100: 0.45}, prior_days=3)[1], info)
    assert stop["exit_reason"].startswith("FIXED STOP -50%")                                       # the -50% stop still acts
    ok = [{"run_id": "x", "entry": "time_1100", "side": "C", "filters": ("rvol_ge106",),
           "exit": ExitCfg(stop="fixed", fixed_stop=0.5, fixed_target=99.0, trail="gb50", contract="n1d03-12t07")}]
    runner.validate(ok)
    for bad in (dict(trail="be10"), dict(trail="gb50", mechanics="oa1m"), dict(tp="A")):
        cfg = dict(stop="fixed", fixed_stop=0.5, fixed_target=99.0, contract="d03-12t07")
        cfg.update(bad)
        with pytest.raises(ValueError):
            runner.validate([dict(ok[0], exit=ExitCfg(**cfg))])


def test_rvol_ge106_filter():
    sig = entries.Signal("time_1100", "SPY", DAY, "C", 89, 500.0, None, {})
    r = {"filters": ("rvol_ge106",)}
    assert engine._filters_ok(r, _ctx({0: 500.0}, vol=HI), sig, 0) is None
    assert engine._filters_ok(r, _ctx({0: 500.0}), sig, 0) == "rvol below 1.06 (rvol_ge106)"
    assert engine._filters_ok(r, _ctx({0: 500.0}, prior_days=5), sig, 0) == "rvol unknown (rvol_ge106)"


def _opt_rows(days, pnls):
    return [{"symbol": "SPY", "day": d, "side": "C", "entry_idx": 90, "entry_time": "11:01", "pnl": p, "pnl_2x": p - 1.0, "_src": "DEV"}
            for d, p in zip(days, pnls)]


def test_b3_bars_and_b4_steadier_readout():
    dev = book.sessions_between("2024-08-01", "2026-06-30")
    hist = book.sessions_between("2016-01-04", "2023-12-31")
    finh_d = _opt_rows(dev[::5], [-30.0] * 90 + [900.0] + [-30.0] * (len(dev[::5]) - 91))
    steady = _opt_rows(dev[::5], [12.0 if k % 2 else -8.0 for k in range(len(dev[::5]))])
    hist_rows = [dict(r, _src="HIST") for r in _opt_rows(hist[::7], [15.0 if k % 3 else -9.0 for k in range(len(hist[::7]))])]
    e8 = {"HIST": {"b4_d03_i": hist_rows, "b4_n1d03_ii": hist_rows}, "DEV": {"b4_d03_i": finh_d, "b4_n1d03_ii": steady}}
    out = round8.b4(e8, {"HIST": hist_rows, "DEV": finh_d})
    v = out["b4_n1d03_ii"]
    assert v["bar"]["pass"] and v["steadier"]["pass"] and all(ok for _, ok in v["steadier"]["checks"])
    assert v["steadier"]["common_days"] == len(steady) and v["steadier"]["fin_h"]["without_best_day"] == pytest.approx(-30.0 * (len(finh_d) - 1))
    me = out["b4_d03_i"]
    assert not me["steadier"]["pass"] and out["_consistency"]["same"]                               # FIN-H is not steadier than itself
    assert "+57.82" in me["steadier"]["checks"][1][0]
    bar = round8.b3_bar(hist_rows, steady)
    assert [n.split(":")[0] for n, _ in bar["checks"]] == ["HIST"] * 5 + ["DEV"] * 3 and bar["pass"]
    thin = round8.b3_bar(hist_rows[:50], steady)
    assert not thin["pass"] and round8.first_fail(thin["checks"]) == "HIST: at least 60 trades"
