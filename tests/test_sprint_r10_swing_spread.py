"""Addendum 16.1's ESTIMATED-SPREAD (sprint/spread_est.py): the Abdi-Ranaldo estimator recovers a known half-spread from
synthetic 1-minute bars with bid/ask bounce, pairs need consecutive minutes with trades, the pools (median, $0.005 floor,
fewer than 5 pairs -> the labeled 10% default, 0DTE left out), the calibration ratio on measured chains (clipping, the
200-contract-day fallback, locked and out-of-DEV chain files never opened), and no look-ahead: a later month never changes an
earlier month's cost, the estimate at a minute ignores later bars, and costs never change a decision. Synthetic data only."""
import json
import math
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

import sprint_synth  # noqa: F401  (puts the repo and tools/ on sys.path)
import pull_alpaca as PA
from sprint import edgar, periods
from sprint import ivdata as IV
from sprint import r10swing as SW
from sprint import spread as SP
from sprint import spread_est as SE
from sprint.catalyst import occ

ET = "America/New_York"
D1 = date(2025, 3, 3)


def _ts(day, minute):
    return (pd.Timestamp(f"{day} 09:30", tz=ET) + pd.Timedelta(minutes=int(minute))).isoformat()


def bounce_bars(sym, day, minutes, half, mid0=2.0, vol=0.0, trades=8, seed=1, both_sides=False):
    """1-minute bars of trades at the mid +/- `half` (bid/ask bounce) around an efficient mid that moves `vol` a trade."""
    rng = np.random.default_rng(seed)
    rows, mid = [], mid0
    for m in minutes:
        px = []
        for k in range(trades):
            mid *= math.exp(rng.normal(0, vol)) if vol else 1.0
            side = (1 if k % 2 == 0 else -1) if both_sides and k < 2 else rng.choice([-1, 1])
            px.append(mid + side * half)
        rng.shuffle(px) if both_sides else None
        rows.append({"ts": _ts(day, m), "o": px[0], "h": max(px), "l": min(px), "c": px[-1], "v": float(trades), "n": trades,
                     "symbol": sym})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- the estimator
def test_ar_recovers_the_half_spread_exactly_with_a_still_mid_and_both_sides_traded():
    df = bounce_bars("ABC250321C00050000", D1, range(30, 90), 0.05, both_sides=True, seed=3)
    pr = SE.pair_estimates(df, D1)
    assert len(pr) == 59 and (pr["hs"] > 0).all()
    want = 0.5 * math.log(2.05 / 1.95) * math.sqrt(2.05 * 1.95)
    assert np.allclose(pr["hs"], want) and abs(want - 0.05) < 1e-4
    assert np.allclose(pr["mid"], math.sqrt(2.05 * 1.95))


@pytest.mark.parametrize("half,vol", [(0.05, 0.0005), (0.10, 0.001), (0.02, 0.0002)])
def test_ar_median_recovers_a_known_spread_under_bid_ask_bounce_and_a_moving_mid(half, vol):
    df = pd.concat([bounce_bars(f"ABC250321C{50000 + 1000 * k:08d}", D1, range(0, 389), half, mid0=2.0 + 0.1 * k, vol=vol, seed=k)
                    for k in range(6)], ignore_index=True)
    pr = SE.pair_estimates(df, D1)
    assert len(pr) == 6 * 388
    assert float(np.median(pr["hs"])) == pytest.approx(half, rel=0.15)
    pools = SE.pool_pairs({D1: pr})
    est = SE.SpreadEst(pools, ratio=1.0)
    raw, lab = est.unfloored().half_spread("ABC", 2.2, 380, day=D1)
    assert lab == SE.RAW_LABEL and raw == pytest.approx(half, rel=0.2)
    hs, lab = est.half_spread("ABC", 2.2, 380, day=D1)
    assert lab == SE.LABEL and hs == pytest.approx(max(raw, SP.DEFAULT_PCT_INDEX * 2.2))


def test_pairs_need_consecutive_minutes_that_both_traded():
    sym = "ABC250321C00050000"
    df = bounce_bars(sym, D1, [10, 11, 12, 14, 15, 20], 0.05, both_sides=True)
    pr = SE.pair_estimates(df, D1)
    assert list(pr["m"]) == [10, 11, 14]                       # 12 -> 14 and 15 -> 20 are not consecutive minutes
    out = pd.concat([df, pd.DataFrame([{"ts": _ts(D1, 390), "o": 9, "h": 9, "l": 9, "c": 9, "v": 1, "symbol": sym}])])
    assert len(SE.pair_estimates(out, D1)) == 3                # a 16:00 bar is outside the session
    other = df.assign(symbol="ABC250321P00050000").iloc[[3]]   # another contract's minute 14 does not pair with 15
    assert len(SE.pair_estimates(pd.concat([df.iloc[:4], other]), D1)) == 2


def test_single_trade_minutes_are_excluded_by_the_trade_count_or_high_equal_low():
    """Addendum 16.3: a pair counts only when both minutes have at least 2 trades (the bar's "n")."""
    sym = "ABC250321C00050000"
    df = bounce_bars(sym, D1, range(10, 20), 0.05, both_sides=True)
    df.loc[df.index[3], "n"] = 1                               # minute 13 had one trade: pairs 12-13 and 13-14 are out
    assert list(SE.pair_estimates(df, D1)["m"]) == [10, 11, 14, 15, 16, 17, 18]
    df.loc[df.index[5], "n"] = 2                               # 2 trades is enough
    assert 15 in list(SE.pair_estimates(df, D1)["m"])
    one = pd.DataFrame([{"ts": _ts(D1, m), "o": 2.0, "h": 2.0, "l": 2.0, "c": 2.0, "v": 1.0, "n": 1, "symbol": sym} for m in (5, 6)])
    assert len(SE.pair_estimates(one, D1)) == 0                # high = low = close: no bounce, no pair
    nocount = df.drop(columns=["n"])                           # a cache without a trade count: the high == low fallback
    flat = nocount.copy()
    flat.loc[flat.index[3], ["h", "l"]] = flat.loc[flat.index[3], "c"]
    assert list(SE.pair_estimates(nocount, D1)["m"]) == list(range(10, 19))
    assert list(SE.pair_estimates(flat, D1)["m"]) == [10, 11, 14, 15, 16, 17, 18]
    blank = df.copy()
    blank["n"] = np.nan                                        # a blank count falls back the same way
    assert list(SE.pair_estimates(blank, D1)["m"]) == list(range(10, 19))
    thin = pd.concat([bounce_bars(sym, D1, [m], 0.05, both_sides=True, trades=1) for m in range(30, 60)], ignore_index=True)
    assert len(SE.pair_estimates(thin, D1)) == 0               # a contract trading once a minute gives no pair at all


def test_the_2pct_floor_binds_on_a_thin_contract_and_the_unfloored_estimate_is_reported():
    """Addendum 16.3: pass/fail cost = max(calibrated estimate, 2% of premium, $0.005); the unfloored one is information."""
    assert SE.FLOOR_PCT == SP.DEFAULT_PCT_INDEX == 0.02
    sym = "ABC250321C00050000"
    pr = SE.pair_estimates(bounce_bars(sym, D1, range(0, 60), 0.004, mid0=1.5, both_sides=True), D1)
    pools = SE.pool_pairs({D1: pr})
    est = SE.SpreadEst(pools, ratio=1.25)
    raw, rl = est.unfloored().half_spread("ABC", 1.5, 300, day=D1)
    hs, lab = est.half_spread("ABC", 1.5, 300, day=D1)
    assert raw == pytest.approx(0.004 * 1.25, rel=0.02) and rl == SE.RAW_LABEL
    assert hs == pytest.approx(0.02 * 1.5) and lab == SE.LABEL and est.used["ESTIMATED-SPREAD: the 2% floor binds"] == 1
    wide = SE.SpreadEst({("ABC", "2025-03", SP._pb(1.5)): (0.08, 40)}, ratio=1.25)
    assert wide.half_spread("ABC", 1.5, 300, day=D1)[0] == pytest.approx(0.10)    # a wide estimate is not touched
    cheap = SE.SpreadEst({("ABC", "2025-03", SP._pb(0.1)): (0.0001, 40)})
    assert cheap.half_spread("ABC", 0.1, 300, day=D1)[0] == SE.FLOOR                # 2% of $0.10 < $0.005: the tick floor
    rows = SW.spread_set(est)
    assert set(rows) == {"est", "raw", "m10", "m2"} and not rows["raw"].floored and rows["est"].floored


def test_the_calibration_ratio_is_computed_before_the_floor(tmp_path):
    """Measured 0.10 over estimated 0.02 (0.67% of a $3 premium, under the 2% floor): the ratio is 5 before clipping, never
    measured / the floored 0.06."""
    root, chains = tmp_path / "alpaca", tmp_path / "chains"
    write_cal(root, chains, CAL_DAYS, factor=5.0)
    r, info = SE.calibrate(root, chains)
    assert info["raw_median"] == pytest.approx(5.0, rel=0.02) and r == 3.0
    import sprint.spread_est as mod
    keep = mod.FLOOR_PCT
    try:
        mod.FLOOR_PCT = 0.50                                   # a different pass/fail floor changes nothing in the calibration
        assert SE.calibrate(root, chains) == (r, info)
    finally:
        mod.FLOOR_PCT = keep


# ---------------------------------------------------------------- the pools and the fills
def test_pools_median_floor_ratio_fallback_and_0dte_left_out():
    rows = [("ABC250321C00050000", 1.9, 0.03), ("ABC250321C00050000", 1.95, 0.05), ("ABC250321P00050000", 1.8, 0.07),
            ("ABC250321C00055000", 1.5, 0.04), ("ABC250321C00055000", 1.6, 0.06), ("ABC250303C00050000", 1.8, 9.0)]
    pr = pd.DataFrame([{"symbol": s, "m": k, "mid": mid, "hs": h} for k, (s, mid, h) in enumerate(rows)])
    pools = SE.pool_pairs({D1: pr})
    assert pools == {("ABC", "2025-03", SP._pb(1.9)): (0.05, 5)}          # the 0DTE contract (expiry = the day) is left out
    est = SE.SpreadEst(pools, ratio=1.6)
    hs, lab = est.half_spread("ABC", 1.7, 385, day=date(2025, 3, 20))
    assert lab == SE.LABEL and hs == pytest.approx(0.08)
    tiny = SE.SpreadEst({("ABC", "2025-03", SP._pb(1.9)): (0.0, 7)}, ratio=0.5)
    assert tiny.half_spread("ABC", 1.7, None, day=D1) == (pytest.approx(0.034), SE.LABEL)     # 16.3: 2% of the premium
    four = SE.SpreadEst({("ABC", "2025-03", SP._pb(1.9)): (0.05, 4)})
    assert four.half_spread("ABC", 1.7, None, day=D1) == (pytest.approx(0.17), SE.FALLBACK)  # fewer than 5 pairs: 10% default
    assert est.half_spread("SPY", 1.7, None, day=D1) == (pytest.approx(0.034), SE.FALLBACK)  # SPY's default is 2%
    assert est.half_spread("ABC", 1.7, None, day=date(2025, 4, 1))[1] == SE.FALLBACK         # another month: its own pool
    assert est.half_spread("ABC", 1.7, None)[1] == SE.FALLBACK                               # no fill day
    assert est.half_spread("ABC", 9.0, None, day=D1)[1] == SE.FALLBACK                       # another premium bucket
    assert est.half_spread("BRK.B", 1.7, None, day=D1)[1] == SE.FALLBACK
    assert est.summary()["fills"] == {SE.LABEL: 1, SE.FALLBACK: 5}
    assert SE.hs_of(SP.SpreadModel(pct=0.02), "ABC", 1.0, 3, D1) == (0.02, "MODELED-SPREAD")


# ---------------------------------------------------------------- calibration
CAL_DAYS = [date(2025, 3, 3), date(2025, 3, 4), date(2025, 3, 5), date(2025, 3, 6)]


def write_cal(root, chains, days, factor, n_strikes=26, measured=0.10, mid=3.0):
    """Chain files with a measured half-spread `measured` and 0DTE SPY bars whose bounce half-spread is measured / factor."""
    chains.mkdir(parents=True, exist_ok=True)
    for d in days:
        crow, bars = [], []
        for j, k in enumerate(range(500, 500 + n_strikes)):
            for r in ("C", "P"):
                sym = occ("SPY", d, r, k)
                bars.append(bounce_bars(sym, d, range(30, 61), measured / factor, mid0=mid, both_sides=True, seed=j))
                for m in range(30, 60):
                    t = (pd.Timestamp(f"{d} 09:30", tz=ET) + pd.Timedelta(minutes=m, seconds=5)).isoformat()
                    crow.append({"logged_at": t, "underlying": "SPY", "spot": 512.0, "symbol": sym, "type": r, "expiry": d.isoformat(),
                                 "strike": float(k), "bid": mid - measured, "ask": mid + measured, "last": mid})
        pd.DataFrame(crow).to_csv(chains / f"{d.isoformat()}.csv.gz", index=False, compression="gzip")
        b = pd.concat(bars, ignore_index=True)
        PA._write_gz(root / "options" / "SPY" / d.isoformat() / "bars.csv.gz", b.assign(ts=pd.to_datetime(b["ts"])))


def test_calibration_ratio_is_the_median_measured_over_estimated(tmp_path):
    root, chains = tmp_path / "alpaca", tmp_path / "chains"
    write_cal(root, chains, CAL_DAYS, factor=1.5)
    r, info = SE.calibrate(root, chains)
    assert info["matched_contract_days"] == 4 * 52 >= 200 and info["chain_days"] == 4
    assert r == pytest.approx(1.5, rel=0.01) and "median measured / estimated" in info["label"]


@pytest.mark.parametrize("factor,want", [(5.0, 3.0), (0.2, 0.5)])
def test_calibration_ratio_is_clipped_to_half_and_three(tmp_path, factor, want):
    root, chains = tmp_path / "alpaca", tmp_path / "chains"
    write_cal(root, chains, CAL_DAYS, factor=factor)
    r, info = SE.calibrate(root, chains)
    assert r == want and info["raw_median"] == pytest.approx(factor, rel=0.02) and "clipped" in info["label"]


def test_calibration_falls_back_to_one_under_200_contract_days_and_never_opens_locked_files(tmp_path):
    root, chains = tmp_path / "alpaca", tmp_path / "chains"
    write_cal(root, chains, CAL_DAYS[:3], factor=1.5)          # 156 contract-days
    r, info = SE.calibrate(root, chains)
    assert r == 1.0 and info["matched_contract_days"] == 156 and "fewer than 200" in info["label"]
    assert info["raw_median"] == pytest.approx(1.5, rel=0.01)
    for bad in ("2024-03-04", "2026-07-06", "2026-11-02", "2024-01-03"):     # L2, L1, after DEV, before DEV
        (chains / f"{bad}.csv.gz").write_bytes(b"not a gzip file")
    assert set(SE.chain_files(chains)) == set(CAL_DAYS[:3])
    assert SE.calibrate(root, chains)[1]["chain_days"] == 3
    assert SE.calibrate(root, tmp_path / "no_chains") == (1.0, {"chain_days": 0, "chain_rows": 0, "matched_contract_days": 0,
                                                                "ratio": 1.0, "raw_median": None,
                                                                "label": "ratio 1: fewer than 200 matched contract-days (0)"})


def test_calibration_reads_round10s_whole_session_file_where_the_cache_lacks_a_contract(tmp_path):
    root, chains = tmp_path / "alpaca", tmp_path / "chains"
    write_cal(root, chains, CAL_DAYS, factor=2.0)
    d = CAL_DAYS[0]
    f = root / "options" / "SPY" / d.isoformat() / "bars.csv.gz"
    b = PA.read_gz(f)
    gone = occ("SPY", d, "C", 500)
    PA._write_gz(f, b[b["symbol"] != gone])
    assert SE.cal_needs(root, chains, CAL_DAYS) == {d: [gone]}
    assert SE.calibrate(root, chains)[1]["matched_contract_days"] == 207
    part = b[b["symbol"] == gone]
    PA._write_gz(IV.opt_dir(root, d) / f"{IV.wkey(IV.W_DAY)}.p0001.csv.gz", part)
    IV.opt_marker(root, d, IV.W_DAY).write_text(json.dumps({"asked": [gone], "printed": [gone]}))
    assert SE.calibrate(root, chains)[1]["matched_contract_days"] == 208


# ---------------------------------------------------------------- no look-ahead
def test_a_later_month_never_changes_an_earlier_months_cost_and_later_bars_never_change_an_estimate():
    mar, apr = date(2025, 3, 20), date(2025, 4, 8)
    a = bounce_bars("ABC250516C00050000", mar, range(0, 60), 0.05, vol=0.0005, seed=4)
    b = bounce_bars("ABC250516C00050000", apr, range(0, 60), 0.05, vol=0.0005, seed=5)
    p1 = SE.pool_pairs({mar: SE.pair_estimates(a, mar), apr: SE.pair_estimates(b, apr)})
    b2 = bounce_bars("ABC250516C00050000", apr, range(0, 60), 0.30, vol=0.01, seed=6)
    p2 = SE.pool_pairs({mar: SE.pair_estimates(a, mar), apr: SE.pair_estimates(b2, apr)})
    assert {k: v for k, v in p1.items() if k[1] == "2025-03"} == {k: v for k, v in p2.items() if k[1] == "2025-03"}
    assert p1 != p2
    pr = SE.pair_estimates(a, mar).set_index("m")["hs"]
    a2 = a.copy()
    a2.loc[a2.index[30:], ["h", "l", "c"]] *= 3.0             # change every bar from minute 30 on
    pr2 = SE.pair_estimates(a2, mar).set_index("m")["hs"]
    assert pr.loc[:28].equals(pr2.loc[:28])                   # the pair (t, t+1) reads bars t and t+1 only


def test_costs_never_change_a_decision():
    """The same straddle, exit day and legs under three different cost models; only the P/L moves."""
    t, x, exp = date(2025, 3, 3), date(2025, 4, 1), date(2025, 4, 17)
    pidx = lambda px: {"ABC": {(exp, 100.0, r): (occ("ABC", exp, r, 100), 385, px) for r in ("C", "P")}}

    class Bars:
        def last15(self, day):
            return {t: pidx(3.0), date(2025, 3, 12): pidx(4.0)}.get(day, {})
    tab = IV.IVTable([t], ["ABC"])
    tab.set(t, "ABC", {"iv30": 0.4, "exp30": exp.isoformat(), "spot": 100.2})
    panels = {"all": SW.HLPanel(["ABC"], {}, None, [t]), "univ": {"ABC": "U-STK"}}
    base = {"bars": Bars(), "tab": tab, "reports": {"ABC": [datetime(2025, 3, 13, 7, 0)]}, "cal": edgar.Calendar(), "panels": panels}
    keep = ("strike", "exit_day", "legs", "entry_px", "exit_px", "report_exit", "settled")
    rows = []
    pools = {("ABC", "2025-03", SP._pb(3.0)): (0.5, 50), ("ABC", "2025-03", SP._pb(4.0)): (0.5, 50)}
    for model in (SP.SpreadModel(pct=0.01), SP.SpreadModel(pct=0.20), SE.SpreadEst(pools)):
        r, why = SW.position_outcome("ABC", t, x, "straddle", dict(base, spread=model))
        assert why is None
        rows.append(r)
    assert all({k: r[k] for k in keep} == {k: rows[0][k] for k in keep} for r in rows)
    assert len({r["pnl_100"] for r in rows}) == 3 and all(r["pnl_mid"] == rows[0]["pnl_mid"] for r in rows)
    assert rows[2]["spread_label"] == SE.LABEL and rows[0]["pnl_m10"] == rows[2]["pnl_m10"]


# ---------------------------------------------------------------- the pools from round 10's files
def test_build_reads_round10_window_files_and_labels_an_uncalibrated_ratio(tmp_path):
    root = tmp_path / "alpaca"
    d = date(2025, 3, 3)
    df = bounce_bars("ABC250321C00050000", d, range(375, 390), 0.05, both_sides=True)
    zero = bounce_bars("ABC250303C00050000", d, range(375, 390), 0.5, both_sides=True)     # 0DTE: never pooled
    PA._write_gz(IV.opt_dir(root, d) / f"{IV.wkey(IV.W_LAST)}.p0001.csv.gz", pd.concat([df, zero]).assign(ts=lambda f: pd.to_datetime(f["ts"])))
    IV.opt_marker(root, d, IV.W_LAST).write_text(json.dumps({"asked": [], "printed": []}))
    est = SE.build(root, tmp_path / "no_chains", [d, date(2025, 3, 4)])
    assert est.ratio == 1.0 and "fewer than 200" in est.cal["label"]
    assert list(est.pools.values()) == [(pytest.approx(0.05, abs=1e-3), 14)]
    assert est.half_spread("ABC", 1.99, 380, day=d) == (pytest.approx(0.05, abs=1e-3), SE.LABEL)
    assert "ESTIMATED-SPREAD" in est.describe() and est.summary()["pools_with_5_pairs"] == 1
    assert periods.overlaps(date(2024, 3, 4), date(2024, 3, 4))                              # (L2 days are never in DEV's list)
    assert not SE.r10_pairs(root, [date(2024, 3, 4)])
