"""The free 2016-2023 history check (SPRINT_PLAN Amendment 5), on synthetic data only (no network):
  * the HIST period ends before L2, its warm-up and daily ranges never touch L1/L2, and the guard refuses ranges that do;
  * hist_v1 / hist_val_v1 are the six DEV runs unchanged;
  * Layer 1 (sprint/underlying.py): entry at the next bar's open + $0.01, stop on finished closes with the next open as
    the fill, 15:25 (12:50) time exit, R and MFE, the remaining-day-sigma moves, no look-ahead, the readings;
  * Layer 2 (sprint/modeled.py): modeled tapes reproduce tests/sprint_synth.option_bars pricing, the IV proxy uses prior
    sessions only, the contract pick uses no later bar, the calibration recovers a planted multiplier, the validation
    bar and the HIST reading; the runner end to end with modeled tapes (calibration tool, validation, HIST run);
  * the puller's HIST mode asks for stock bars only and never for a locked date or an option before 2024-02."""
import copy
import csv
import gzip
import json
import math
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import bs, contracts, data, engine, entries, periods, runner
from sprint import modeled as MD
from sprint import underlying as U

ROOT = Path(__file__).resolve().parents[1]
ET = "America/New_York"


def _sessions(a, n):
    return [d for d in SS.weekdays(a, n + 12) if d.isoformat() not in periods.holidays()][:n]


WARM = _sessions(date(2015, 11, 2), 42)
HISTD = _sessions(date(2016, 1, 4), 30)
DEVD = _sessions(date(2025, 1, 6), 36)


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    root = tmp_path_factory.mktemp("hist_alpaca")
    SS.write_stock_only(root, "SPY", WARM + HISTD, px0=200.0, seed=7, vol=0.0005)
    SS.write_stock_only(root, "VIXY", WARM + HISTD, px0=20.0, seed=70, vol=0.002)
    SS.write_cache(root, "SPY", DEVD, px0=500.0, seed=11, iv=0.18, band=0.03)
    SS.write_stock_only(root, "VIXY", DEVD, px0=15.0, seed=71, vol=0.002)
    SS.write_daily(root, "VIXY", date(2014, 11, 3), date(2026, 6, 30), skip=[periods.LOCKED["L2"]])
    return root


# ---------------------------------------------------------------- the period and its guard
def test_hist_period_is_before_l2_and_the_guard_refuses_locked_ranges():
    a, b = periods.HIST
    assert (a, b) == (date(2016, 1, 4), date(2024, 1, 31)) and periods.period_range("HIST") == periods.HIST
    assert b < periods.LOCKED["L2"][0]
    assert periods.overlaps(periods.WARMUP["HIST"], b) == [] and periods.overlaps(periods.HIST_DAILY_FROM, b) == []
    assert periods.guard(periods.WARMUP["HIST"], b) == []
    for x, y in ((a, date(2024, 2, 1)), (date(2023, 12, 1), date(2024, 3, 1)), (a, date(2026, 7, 1))):
        with pytest.raises(periods.LockedPeriod, match="REFUSED"):
            periods.guard(x, y)
    hol, early = periods.holidays(), periods.early_closes()
    assert not hol & early
    assert all(date.fromisoformat(x).weekday() < 5 for x in periods.HOLIDAYS_2015_2023 | periods.EARLY_2015_2023)
    assert {"2018-12-05", "2020-04-10", "2022-06-20", "2021-12-24"} <= hol and {"2019-12-24", "2020-11-27", "2023-07-03"} <= early
    assert periods.stretches_for(a, b) is periods.HIST_STRETCHES and periods.stretches_for(*periods.DEV) is periods.STRETCHES
    assert all(date(2016, 1, 1) <= x <= y <= b for _, x, y in periods.HIST_STRETCHES)
    assert [n for n, _, _ in periods.HIST_STRETCHES][:8] == [str(y) for y in range(2016, 2024)]


def test_runner_and_tools_refuse_locked_or_unmodeled_hist_runs(tmp_path, monkeypatch):
    import sprint.engine as E
    import sprint_hist
    monkeypatch.setattr(E, "run_pass", lambda *a, **k: (_ for _ in ()).throw(AssertionError("data was read")))
    spec = ROOT / "sprint" / "specs" / "hist_v1.json"
    with pytest.raises(periods.LockedPeriod):
        runner.run_spec(spec, date(2023, 12, 1), date(2024, 2, 15), out_dir=tmp_path)
    assert sprint_hist.main(["--from", "2023-12-01", "--to", "2024-03-01", "--out", str(tmp_path)]) == 2
    with pytest.raises(FileNotFoundError, match="calibration"):                # no calib file: refused before any data
        runner.run_spec(spec, out_dir=tmp_path)
    s = json.loads(spec.read_text())
    s["tapes"] = "real"
    p = tmp_path / "real_hist.json"
    p.write_text(json.dumps(s))
    with pytest.raises(ValueError, match="modeled"):
        runner.run_spec(p, out_dir=tmp_path)
    (tmp_path / "calib_modeled.json").write_text(json.dumps({"min_n": 30, "keys": {"d40-55t45|C": {"n": 5, "median": 0.6, "ok": False}}}))
    with pytest.raises(ValueError, match="only 5 trades|no calibration"):     # thin or missing keys: refused
        runner.run_spec(spec, out_dir=tmp_path)


def test_hist_specs_are_the_dev_runs_unchanged():
    ref = {}
    for n in ("setups_v2", "otm_v1"):
        for r in engine.expand(json.loads((ROOT / "sprint" / "specs" / f"{n}.json").read_text())):
            ref[r["run_id"]] = r
    key = lambda r: (r["entry"], r["side"], tuple(r["symbols"]), tuple(r["filters"]), r["exit"].as_dict())
    hist = json.loads((ROOT / "sprint" / "specs" / "hist_v1.json").read_text())
    val = json.loads((ROOT / "sprint" / "specs" / "hist_val_v1.json").read_text())
    assert hist["period"] == "HIST" and val["period"] == "DEV" and hist["tapes"] == val["tapes"] == "modeled"
    assert hist["validation"] == "hist_val_v1" and hist["dev_runs"] == val["validate_against"]
    assert val["validate_against"] == {"fb": "setups_v2-001", "fb_or": "setups_v2-012", "otm_put_base": "otm_v1-010",
                                       "otm_put": "otm_v1-011", "otm_bounce_base": "otm_v1-040", "otm_bounce": "otm_v1-042"}
    for spec in (hist, val):
        runs = engine.expand(spec)
        runner.validate(runs)
        assert [r["block"] for r in runs] == list(val["validate_against"])
        for r in runs:
            assert key(r) == key(ref[val["validate_against"][r["block"]]]), r["block"]


# ---------------------------------------------------------------- Layer 1 rules (hand-built days)
DAY = date(2025, 3, 4)


def _ctx(path, bars=None, early=False):
    ctx, _ = SS.make_ctx(DAY, path, {0: 1.0}, prior_days=20, stock_bars=bars, early=early)
    return ctx


def _sig(ctx, i, invalid, side="C"):
    return entries.Signal("failed_break", ctx.sym, ctx.day, side, i, float(ctx.c[i]), invalid, {})


def test_layer1_stop_entry_next_open_stop_on_close_and_mfe():
    bars = {101: (500.05, 500.10, 500.00, 500.06), 150: (500.50, 501.00, 500.40, 500.60),
            180: (500.0, 500.0, 499.40, 499.60),                 # the low pierces the stop, the close does not: no exit
            200: (499.6, 499.6, 499.38, 499.40),                 # close below the stop -> exit at the next open
            201: (499.30, 499.35, 499.25, 499.32)}
    ctx = _ctx({0: 500.0, 150: 500.6, 181: 499.6, 202: 499.32}, bars)
    t = U.sim_stop(ctx, _sig(ctx, 100, 499.50))
    assert t["status"] == "TRADE" and t["entry_idx"] == 101 and t["entry"] == pytest.approx(500.06)
    assert t["stop"] == pytest.approx(499.48)                    # invalid - max($0.02, 0.05 x ATR) with a tiny ATR
    assert t["exit_idx"] == 201 and t["exit"] == pytest.approx(499.29) and t["exit_reason"].startswith("STOP")
    R = 500.06 - 499.48
    assert t["risk"] == pytest.approx(R) and t["r"] == pytest.approx((499.29 - 500.06) / R, abs=1e-4)
    assert t["mfe_r"] == pytest.approx((501.00 - 500.06) / R, abs=1e-4)
    assert t["pct"] == pytest.approx((499.29 / 500.06 - 1) * 100, abs=1e-4)


def test_layer1_time_exit_at_1525_and_1250_and_skips():
    ctx = _ctx({0: 500.0, 300: 502.0, 354: 503.0, 356: 490.0})
    t = U.sim_stop(ctx, _sig(ctx, 100, 499.50))
    assert t["exit_idx"] == U.ALLOUT_BAR == 354 and t["exit"] == pytest.approx(503.0 - 0.01) and t["exit_reason"] == "ALL OUT 15:25"
    ce = _ctx({0: 500.0, 199: 501.0, 205: 480.0}, early=True)
    t = U.sim_stop(ce, _sig(ce, 100, 499.50))
    assert t["exit_idx"] == 199 and t["exit"] == pytest.approx(501.0 - 0.01) and t["exit_reason"] == "ALL OUT 12:50"
    ctx = _ctx({0: 500.0}, {101: (499.40, 499.45, 499.35, 499.40)})       # opens below the stop: R <= 0
    assert U.sim_stop(ctx, _sig(ctx, 100, 499.50))["reason"] == "entry at or beyond the stop"
    assert U.sim_stop(ctx, _sig(ctx, 354, 499.50))["status"] == "SKIP"


def test_layer1_move_in_remaining_day_sigma():
    bars = {250: (494.0, 494.0, 491.5, 493.0)}
    ctx = _ctx({0: 500.0, 59: 500.0, 200: 495.0, 251: 493.0, 354: 492.0, 360: 510.0}, bars)
    sg = 0.0005
    t = U.measure_move(ctx, entries.Signal("time_1030", "SPY", DAY, "P", 59, 500.0, None, {}), sg)
    sd = sg * math.sqrt(295)
    assert t["minutes_left"] == 295 and t["close_1525"] == 492.0 and t["extreme"] == 491.5
    assert t["z_close"] == pytest.approx(math.log(492 / 500) / sd, abs=1e-3) and t["large"] is True
    assert t["z_ext"] == pytest.approx(math.log(491.5 / 500) / sd, abs=1e-3) and t["move_pct"] == pytest.approx(-1.6)
    c = U.measure_move(ctx, entries.Signal("time_1100", "SPY", DAY, "C", 89, float(ctx.c[89]), None, {}), sg)
    assert c["minutes_left"] == 265 and c["large"] is False                # a drop is not a large rise
    assert U.measure_move(ctx, entries.Signal("time_1030", "SPY", DAY, "P", 59, 500.0, None, {}), None)["status"] == "SKIP"


def test_layer1_day_skip_test_and_readings():
    twin = [{"day": f"2017-{m:02d}-{d:02d}", "large": (m * 31 + d) % 9 == 0} for m in range(1, 13) for d in range(1, 21)]
    rich = [t for t in twin if t["large"]] + [t for t in twin if not t["large"]][:15]
    t = U.day_skip_test(rich, twin)
    assert t["p_value"] < 0.01 and t["skipped_days"] == len(twin) - len(rich)
    t2 = U.day_skip_test(twin[::3], twin)
    assert 0.05 < t2["p_value"] < 0.95
    yr = lambda e: {str(y): {"trades": 10, "expectancy": e[y - 2016]} for y in range(2016, 2024)}
    o = {"overall": {"expectancy": 0.2}, "by_stretch": yr([1, 1, 1, 1, 1, 1, -1, -1]), "random": {"101": {"expectancy": 0.1}}}
    assert U.reading_stop(o)["verdict"] is True
    o["by_stretch"] = yr([1, 1, 1, 1, 1, -1, -1, -1])
    assert U.reading_stop(o)["verdict"] is False                            # 5 of 8 years
    o["by_stretch"], o["random"]["102"] = yr([1] * 8), {"expectancy": 0.25}
    assert U.reading_stop(o)["verdict"] is False                            # a random seed did better
    st = {str(y): {"n": 20, "large_rate": 0.2} for y in range(2016, 2024)}
    tw = {str(y): {"n": 200, "large_rate": 0.1} for y in range(2016, 2024)}
    mv = {"by_stretch": st, "twin_by_stretch": tw, "skip_test": {"p_value": 0.05}}
    assert U.reading_move(mv, "P")["verdict"] is True
    mv["skip_test"]["p_value"] = 0.12
    assert U.reading_move(mv, "P")["verdict"] is False
    st2 = {str(y): ({"n": 8, "large_rate": 0.3} if y in (2016, 2018, 2020) else {"n": 2, "large_rate": 0.0}) for y in range(2016, 2024)}
    mv = {"by_stretch": st2, "twin_by_stretch": tw, "skip_test": {"p_value": 0.01}}
    assert U.reading_move(mv, "C")["verdict"] is True                      # 3 eligible years, all above
    st2["2020"]["n"] = 4
    assert U.reading_move(mv, "C")["verdict"] is False                     # only 2 years with 5+ days


# ---------------------------------------------------------------- Layer 1 on a synthetic history: no look-ahead
def _mem_series(days, seed, px0, vol, bump_last_after=None):
    frames, px = [], px0
    for n, d in enumerate(days):
        df = SS.stock_day(d, px, seed + n, vol=vol)
        px = float(df["c"].iloc[-1])
        frames.append(df)
    if bump_last_after is not None:
        df = frames[-1].copy()
        m = df["ts"].dt.hour * 60 + df["ts"].dt.minute - 570
        sel = m >= bump_last_after
        for c in ("o", "h", "l", "c"):
            df.loc[sel, c] = (df.loc[sel, c] * 0.97).round(2)
        frames[-1] = df
    return data.Series("SPY" if px0 > 50 else "VIXY", pd.concat(frames, ignore_index=True))


def test_layer1_future_bars_never_change_signals_or_earlier_results():
    days = WARM[-25:] + HISTD[:12]
    strats = U.strategies()
    vd = pd.Series(np.exp(np.linspace(3, 2, 400)), index=[date(2014, 11, 3) + timedelta(days=k) for k in range(400)])
    vd = vd[[d.weekday() < 5 for d in vd.index]]
    out = []
    for bump in (None, 200):
        ser = _mem_series(days, 5, 200.0, 0.0006, bump)
        aux = {"VIXY_D": vd, "VIXY": _mem_series(days, 50, 20.0, 0.002, bump)}
        res = U.run({"SPY": ser}, aux, HISTD[0], HISTD[-1], strats)
        ctx = data.DayContext(ser, days[-1], {}, None, aux=aux)
        sig = {s["name"]: [x.key for x in entries.signals(ctx, s["entry"], s["side"]) if x.idx < 199] for s in strats}
        out.append((res, sig, ser))
    (r1, s1, ser1), (r2, s2, ser2) = out
    last = days[-1].isoformat()
    assert s1 == s2
    n_before = 0
    for s in strats:
        a = [t for t in r1[s["name"]]["trades"] if t["day"] < last or t["exit_idx"] < 199]
        b = [t for t in r2[s["name"]]["trades"] if t["day"] < last or t["exit_idx"] < 199]
        assert a == b, s["name"]
        n_before += len(a)
        for sd in U.SEEDS:
            ra = [t for t in r1[s["name"]]["random"][sd] if t["day"] < last]
            rb = [t for t in r2[s["name"]]["random"][sd] if t["day"] < last]
            assert ra == rb
    assert n_before > 0
    assert MD.iv_proxy(ser1, days[-1]) == MD.iv_proxy(ser2, days[-1])       # the bumped day is not in its own proxy


# ---------------------------------------------------------------- Layer 2: the model
def _series(days, seed=3, px0=250.0, vol=0.0005):
    frames, px = [], px0
    for n, d in enumerate(days):
        df = SS.stock_day(d, px, seed + n, vol=vol)
        frames.append(df)
        px = float(df["c"].iloc[-1])
    return data.Series("SPY", pd.concat(frames, ignore_index=True)), frames


def test_iv_proxy_uses_prior_sessions_only():
    days = SS.weekdays(date(2018, 3, 1), 25)
    ser, frames = _series(days)
    assert MD.iv_proxy(ser, days[9]) is None and MD.iv_proxy(ser, days[10]) is not None   # needs 10 prior sessions
    p = MD.iv_proxy(ser, days[20])
    assert p == pytest.approx(0.0005 * math.sqrt(bs.YEAR_MIN), rel=0.05)
    f2 = [f.copy() for f in frames]
    f2[20] = SS.stock_day(days[20], float(frames[19]["c"].iloc[-1]), 999, vol=0.004)     # day 20 itself made 8x wilder
    ser2 = data.Series("SPY", pd.concat(f2, ignore_index=True))
    assert MD.iv_proxy(ser2, days[20]) == p
    assert MD.iv_proxy(ser2, days[21]) > 1.5 * MD.iv_proxy(ser, days[21])


def test_modeled_tapes_reproduce_option_bars_pricing():
    days = SS.weekdays(date(2018, 3, 1), 3)
    ser, frames = _series(days)
    ctx = data.DayContext(ser, days[-1], {}, None)
    md = MD.ModeledDay(ctx)
    ob = SS.option_bars(days[-1], frames[-1], "SPY", iv=0.18, band=0.02)
    ob["ts"] = pd.to_datetime(ob["ts"])
    n = 0
    for sym, g in ob.groupby("symbol"):
        t = md.tape(int(sym[-8:]) / 1000, sym[-9], 0.18)
        assert t.symbol == sym and t.expiry == days[-1]
        mi = (g["ts"].dt.hour * 60 + g["ts"].dt.minute - 570).to_numpy()
        for col in ("o", "c"):
            ref = g[col].to_numpy()
            ok = ref >= 0.01
            assert np.allclose(getattr(t, col)[mi][ok], ref[ok], atol=1e-9)
            n += ok.sum()
        assert np.all(t.h[mi] >= np.maximum(t.o[mi], t.c[mi])) and np.all(t.l[mi] <= np.minimum(t.o[mi], t.c[mi]))
        assert np.nanmin(t.l) >= 0.01
    assert n > 5000
    pool = MD.ModeledDay(ctx).pool(float(ctx.c[59]), "P", 0.21)            # built in one array call
    one = MD.ModeledDay(ctx)
    for sym, t in pool.items():                                             # == strike by strike
        u = one.tape(t.strike, "P", 0.21)
        assert u.symbol == sym and all(np.array_equal(getattr(t, f), getattr(u, f), equal_nan=True) for f in "ohlcv")


def test_modeled_tape_missing_bars_early_close_and_point_in_time_pick():
    days = SS.weekdays(date(2018, 3, 1), 3)
    ser, _ = _series(days)
    d = days[-1]
    ser.rth[d][100] = np.nan                                                # a minute the stock did not trade
    ctx = data.DayContext(ser, d, {}, None)
    t = MD.ModeledDay(ctx).tape(250, "C", 0.2)
    assert np.isnan(t.o[100]) and not t.has_print(100) and t.has_print(99)
    ce = data.DayContext(ser, d, {}, None, early_close=True)
    te = MD.ModeledDay(ce).tape(250, "P", 0.2)
    assert not te.has_print(210) and te.has_print(209)
    want = max(round(bs.price(float(ce.c[150]), 250.0, (210 - 151) / bs.YEAR_MIN, 0.2, "P"), 2), 0.01)
    assert te.c[150] == pytest.approx(want)                                # expiry at 13:00 on early-close days
    picks = []
    for bump in (False, True):
        s2 = copy.deepcopy(ser)
        if bump:
            s2.rth[d][60:, :4] *= 0.9                                       # every bar after the decision moves
        c2 = data.DayContext(s2, d, {}, None)
        c2.tapes = MD.ModeledDay(c2).pool(float(c2.c[59]), "P", 0.2)
        tape, info = contracts.pick(c2, "P", 59, "d03-12t07")
        picks.append((info["symbol"], info["px"], round(info["iv"], 6), info["delta"]))
    assert picks[0] == picks[1]


def test_calibration_recovers_a_planted_multiplier():
    rng = np.random.default_rng(5)
    prox = {("SPY", f"2025-02-{d:02d}"): 0.10 + 0.01 * d for d in range(1, 28)}
    keys = list(prox)
    rows = []
    for k in range(400):
        sym, day = keys[k % len(keys)]
        rows.append({"symbol": sym, "day": day, "contract": f"C{k}", "signal_idx": 59, "side": "P", "rule": "d06-15t10",
                     "setup": "time_1030", "iv_est": prox[(sym, day)] * 1.37 * float(np.exp(rng.normal(0, 0.2)))})
    rows += [dict(r) for r in rows[:50]]                                      # the same trade in another run's file
    rows += [{"symbol": "SPY", "day": "2025-02-03", "contract": f"X{k}", "signal_idx": 89, "side": "C", "rule": "d03-12t07",
              "setup": "time_1100", "iv_est": 0.2} for k in range(10)]
    rows += [{"symbol": "SPY", "day": "2025-02-03", "contract": "Y", "signal_idx": 9, "side": "C", "rule": float("nan"), "iv_est": 0.2},
             {"symbol": "SPY", "day": "2025-02-03", "contract": "Z", "signal_idx": 9, "side": "C", "rule": "d40-55t45", "iv_est": ""}]
    cal = MD.calibrate(rows, lambda s, d: prox.get((s, d)))
    k = cal["keys"]["d06-15t10|P"]
    assert k["n"] == 400 and k["ok"] and abs(k["median"] - 1.37) < 0.04 and k["q1"] < k["median"] < k["q3"]
    assert cal["skipped"]["duplicate"] == 50 and cal["skipped"]["no contract rule"] == 1 and cal["skipped"]["no iv_est"] == 1
    assert cal["keys"]["d03-12t07|C"]["ok"] is False
    assert MD.multiplier(cal, "d06-15t10", "P") == k["median"]
    with pytest.raises(ValueError, match="only 10 trades"):
        MD.multiplier(cal, "d03-12t07", "C")
    with pytest.raises(ValueError, match="no calibration"):
        MD.multiplier(cal, "d06-15t10", "C")


def test_validation_bar_and_the_hist_reading():
    real = {"expectancy": "18.57", "profit_factor": "1.785", "trades": "429"}
    assert MD.validate({"expectancy": 10.0, "profit_factor": 1.6, "trades": 300}, real)["pass"] is True
    assert MD.validate({"expectancy": 30.0, "profit_factor": 2.5, "trades": 300}, real)["pass"] is False      # PF +40%
    assert MD.validate({"expectancy": 1.0, "profit_factor": 1.785 * 1.35, "trades": 300}, real)["pass"] is True
    assert MD.validate({"expectancy": -1.0, "profit_factor": 1.7, "trades": 300}, real)["pass"] is False      # sign differs
    assert MD.validate({"expectancy": 1.0, "profit_factor": 1.7}, {})["pass"] is False                      # no real run
    yrs = {str(y): {"net": 10.0} for y in range(2016, 2024)}
    s = {"trades": 300, "expectancy": 5.0, "profit_factor": 1.4, "pf_2x_slip": 1.1, "stretches": yrs, "without_best5": {"net": 50.0}}
    items, ok = MD.hist_reading(s, {"skip_p": 0.04}, filtered=True)
    assert ok and len(items) == 7
    yrs["2016"]["net"] = yrs["2017"]["net"] = yrs["2018"]["net"] = -1.0
    assert MD.hist_reading(s, {}, filtered=False)[1] is False                # 5 of 8 years
    yrs["2018"]["net"] = 1.0
    assert MD.hist_reading(s, {}, filtered=False)[1] is True
    assert MD.hist_reading(s, {"skip_p": 0.2}, filtered=True)[1] is False


# ---------------------------------------------------------------- end to end: calibration, validation, HIST run
def _specs(folder):
    hist = json.loads((ROOT / "sprint" / "specs" / "hist_v1.json").read_text())
    base = {"symbols": ["SPY"], "blocks": hist["blocks"], "defaults": {}}
    real = dict(base, spec_id="hv_real", period="DEV", tapes="real", robustness={"top_k": 0, "min_trades": 1})
    ids = {r["block"]: r["run_id"] for r in engine.expand(real)}
    val = dict(base, spec_id="hv_val", period="DEV", tapes="modeled", validate_against=ids, robustness={"top_k": 0, "min_trades": 1})
    hst = dict(base, spec_id="hv_hist", period="HIST", tapes="modeled", validation="hv_val",
               robustness={"top_k": 2, "random_paths": 1, "fake_seeds": 0, "min_trades": 1})
    folder.mkdir(parents=True, exist_ok=True)
    for s in (real, val, hst):
        (folder / f"{s['spec_id']}.json").write_text(json.dumps(s))
    return folder


def test_modeled_runner_end_to_end(tmp_path, cache):
    import sprint_calibrate
    specs, out = _specs(tmp_path / "specs"), tmp_path / "out"
    kw = dict(data_root=cache, chains_dir=tmp_path / "nochains", out_dir=out, host_name="t", today=date(2026, 10, 31), log=lambda *a: None)
    r_real = runner.run_spec(specs / "hv_real.json", DEVD[0], DEVD[-1], **kw)
    assert sum(v.get("trades", 0) for v in r_real["summary"].values()) > 0
    assert sprint_calibrate.main(["--trades", str(out), "--specs", str(specs), "--data", str(cache), "--out",
                                  str(out / "calib_modeled.json"), "--min-n", "3"]) == 0
    cal = json.loads((out / "calib_modeled.json").read_text())
    k = cal["keys"]["d06-15t10|P"]
    assert k["ok"] and 0.4 < k["median"] < 0.6                       # synthetic tapes at IV 0.18 / proxy ~0.36
    need = {MD.calib_key(r["exit"].contract, r["side"]) for r in r_real["runs"]}
    assert need <= {x for x, v in cal["keys"].items() if v["ok"]}      # the seeded fixture trades every rule|side
    lines = []
    r_val = runner.run_spec(specs / "hv_val.json", DEVD[0], DEVD[-1], **dict(kw, log=lines.append))
    vf = json.loads((out / "validation_hv_val.json").read_text())
    assert set(vf["blocks"]) == {r["block"] for r in r_val["runs"]} and all(v["real_found"] for v in vf["blocks"].values())
    assert any(ln.startswith("validation otm_put_base: ") and "MODELED (BS, calibrated IV)" in ln for ln in lines)
    real = runner.real_runs(out)
    for blk, v in vf["blocks"].items():                                  # the verdict is the pre-registered bar on these numbers
        s = r_val["summary"][v["run"]]
        assert v["pass"] == MD.validate(s, real[v["real_run"]])["pass"] and v["modeled_trades"] == s.get("trades", 0)
    rep = r_val["report"].read_text()
    assert "Validation on DEV" in rep and "MODELED (BS, calibrated IV)" in rep
    r_h = runner.run_spec(specs / "hv_hist.json", HISTD[0], HISTD[-1], **kw)
    rows = [r for r in csv.DictReader(open(out / "runs_t.csv")) if r["run_id"].startswith("hv_hist")]
    assert len(rows) == 6 and all(r["tool"] == "DeskEngine" and r["period_tag"].startswith("HIST") for r in rows)
    assert all("MODELED (BS, calibrated IV)" in r["notes"] and ("RELIABLE" in r["notes"]) for r in rows)
    assert sum(int(r["trades"]) for r in rows) > 0
    rep = r_h["report"].read_text()
    assert "Pre-registered HIST reading" in rep and "Option prices are not real" in rep and "Mon/Wed/Fri" in rep
    for r in r_h["runs"]:
        g = r_h["modeled"]["readings"][r["run_id"]]
        assert g["reliable"] == vf["blocks"][r["block"]]["pass"]
    assert r_h["sessions"]["SPY"][0] == HISTD[0].isoformat()             # warm-up sessions feed indicators only
    with gzip.open(out / "trades_hv_hist_2026-10-31.csv.gz", "rt") as f:
        tr = list(csv.DictReader(f))
    assert tr and min(t["day"] for t in tr) >= HISTD[0].isoformat()
    again = runner.run_spec(specs / "hv_hist.json", HISTD[0], HISTD[-1], **dict(kw, robust=False))
    assert {k: v.get("expectancy") for k, v in again["summary"].items()} == {k: v.get("expectancy") for k, v in r_h["summary"].items()}
    assert sprint_calibrate.main(["--trades", str(out), "--specs", str(specs), "--data", str(cache), "--out",
                                  str(out / "calib2.json"), "--min-n", "3"]) == 0
    c2 = json.loads((out / "calib2.json").read_text())
    assert any("MODELED" in v for k, v in c2["files_skipped"].items() if k.startswith("trades_hv_"))
    assert c2["keys"] == cal["keys"]                                     # modeled trade files never feed the calibration


def test_layer1_tool_end_to_end(tmp_path, cache):
    import sprint_hist
    out = tmp_path / "l1"
    assert sprint_hist.main(["--from", HISTD[0].isoformat(), "--to", HISTD[-1].isoformat(), "--data", str(cache), "--out", str(out),
                             "--today", "2026-10-31"]) == 0
    md = (out / "hist_layer1_2026-10-31.md").read_text()
    js = json.loads((out / "hist_layer1_2026-10-31.json").read_text())
    assert "Pre-registered readings" in md and "no option model" in md and "signal holds" in md and "tail holds" in md
    assert set(js["strategies"]) == {"fb", "fb_or", "otm_put_base", "otm_put", "otm_bounce_base", "otm_bounce"}
    assert js["strategies"]["otm_put_base"]["overall"]["n"] == len(HISTD)
    assert js["meta"]["warm_from"] == periods.WARMUP["HIST"].isoformat()
    with gzip.open(out / "hist_layer1_2026-10-31_trades.csv.gz", "rt") as f:
        assert min(r["day"] for r in csv.DictReader(f)) >= HISTD[0].isoformat()


# ---------------------------------------------------------------- the puller's HIST mode
def test_puller_hist_mode_is_stock_only_and_never_requests_locked_dates(tmp_path, monkeypatch):
    import pull_alpaca as PA
    import sprint_pull as SPL
    calls = []

    def fake(url, headers):
        assert url.startswith("https://data.alpaca.markets/")
        calls.append(url)
        return {"bars": [], "next_page_token": None}
    monkeypatch.setattr(PA, "_http", fake)
    monkeypatch.setattr(PA, "_throttle", lambda: None)
    monkeypatch.setattr(PA, "ROOT", tmp_path / "alpaca")
    monkeypatch.setenv("ALPACA_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET", "s")
    assert SPL.main(["--period", "HIST", "--root", str(tmp_path / "alpaca")]) == 0
    assert calls and not any("/options/" in u for u in calls)
    span = lambda u: tuple(pd.Timestamp(parse_qs(urlparse(u).query)[k][0]).tz_convert(ET) for k in ("start", "end"))
    for u in calls:
        s, e = span(u)
        last = (e - pd.Timedelta(minutes=1)).date()
        assert s.date() <= last and periods.overlaps(s.date(), last) == [], u
    q = lambda u: {k: v[0] for k, v in parse_qs(urlparse(u).query).items()}
    minute = [u for u in calls if q(u)["timeframe"] == "1Min"]
    assert {urlparse(u).path.split("/")[3] for u in minute} == {"SPY", "QQQ", "IWM", "VIXY"}
    assert all(q(u)["adjustment"] == "split" for u in calls)
    assert min(span(u)[0] for u in minute).date() == periods.WARMUP["HIST"]
    assert max((span(u)[1] - pd.Timedelta(minutes=1)).date() for u in minute) == periods.HIST[1]
    daily = sorted(span(u) for u in calls if q(u)["timeframe"] == "1Day")
    assert [(s.date(), (e - pd.Timedelta(minutes=1)).date()) for s, e in daily] == [
        (periods.HIST_DAILY_FROM, date(2024, 1, 31)), (date(2024, 8, 1), periods.DEV[1])]
    n = len(calls)
    assert SPL.main(["--period", "HIST", "--root", str(tmp_path / "alpaca")]) == 0
    assert all(q(u)["timeframe"] == "1Day" for u in calls[n:])            # resumable: finished months are not pulled again
    r = SPL.pull_options("SPY", date(2016, 1, 4), date(2016, 1, 8), log=lambda *a: None)
    assert r["before_option_history"] == 5 and r["days"] == 0 and len(calls) == n + 2
    assert SPL.pull_options_next("SPY", date(2016, 1, 4), date(2016, 1, 8), log=lambda *a: None)["days"] == 0
    assert len(calls) == n + 2


def test_new_hist_code_has_no_order_path():
    for f in ("sprint/modeled.py", "sprint/underlying.py", "tools/sprint_hist.py", "tools/sprint_calibrate.py", "tools/sprint_pull.py"):
        src = (ROOT / f).read_text()
        for bad in ("paper-api", "/v2/orders", "/v2/positions", "import broker", "api.alpaca.markets/v2/"):
            assert bad not in src, (f, bad)


def test_series_day_grouping_is_unchanged_by_the_linear_rewrite():
    """data.Series groups bars by day with one stable sort (HIST loads ~2,000 sessions); the grids must equal the old
    per-day boolean-mask grouping, including shuffled rows and duplicate minutes (the later row wins in both)."""
    days = SS.weekdays(date(2018, 3, 1), 6)
    df = pd.concat([SS.stock_day(d, 250.0, k) for k, d in enumerate(days)], ignore_index=True)
    dup = df.iloc[[700, 1700]].copy()
    dup["c"] += 1.0
    df = pd.concat([df, dup], ignore_index=True).sample(frac=1.0, random_state=3).reset_index(drop=True)
    ser = data.Series("SPY", df)
    ts = df["ts"]
    mins = (ts.dt.hour * 60 + ts.dt.minute).to_numpy()
    dates = ts.dt.date.to_numpy()
    arr = df[["o", "h", "l", "c", "v"]].to_numpy(float)
    assert ser.days == sorted(set(dates))
    for d in sorted(set(dates)):                                          # the old grouping, row for row
        sel = dates == d
        m, a = mins[sel], arr[sel]
        r = (m >= 570) & (m < 960)
        grid = np.full((390, 5), np.nan)
        grid[m[r] - 570] = a[r]
        assert np.array_equal(grid, ser.rth[d], equal_nan=True)
        p = (m >= 240) & (m < 570)
        assert ser.pre[d] == ((float(a[p, 1].max()), float(a[p, 2].min())) if p.any() else None)
