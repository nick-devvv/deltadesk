"""Round 10's data step D-IV (sprint/ivdata.py, SPRINT_PLAN Amendment 16): the IV solver round-trips Black-Scholes prices,
the probed expiries and strikes, the 30-day / 90-day expiry choice, the bracketing-strike ATM IV (call and put averaged,
interpolated in strike, matched to the stock's close in the print's minute), the 5-session mean with no look-ahead, realized
vol inside a segment or across the locked gap, the coverage report, the per-day cache and the pull's phase-by-phase plan.
Synthetic data only."""
import json
import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import sprint_synth  # noqa: F401  (puts the repo and tools/ on sys.path)
import pull_alpaca as PA
from sprint import bs, periods
from sprint import ivdata as IV
from sprint.catalyst import occ

ET = "America/New_York"


# ---------------------------------------------------------------- the solver
def test_iv_solver_round_trips_bs_prices():
    rng = np.random.default_rng(7)
    n = 3000
    S = rng.uniform(10, 800, n)
    K = S * rng.uniform(0.8, 1.2, n)
    T = rng.uniform(3, 150, n) / 365
    iv = rng.uniform(0.08, 1.5, n)
    call = rng.random(n) < 0.5
    px = np.array([bs.price(a, b, t, v, "C" if c else "P") for a, b, t, v, c in zip(S, K, T, iv, call)])
    vega = S * np.sqrt(T) * np.exp(-0.5 * ((np.log(S / K) + 0.5 * iv * iv * T) / (iv * np.sqrt(T))) ** 2) / math.sqrt(2 * math.pi)
    keep = vega > 0.5                                        # enough vega for a price to pin the vol down
    got = IV.iv_vec(px, S, K, T, call)
    assert np.isfinite(got[keep]).all()
    assert np.max(np.abs(got[keep] - iv[keep])) < 2e-4
    for k in np.flatnonzero(keep)[:50]:                       # agrees with the desk's scalar solver
        one = bs.implied_vol(px[k], S[k], K[k], T[k], "C" if call[k] else "P")
        assert one == pytest.approx(got[k], abs=2e-4)


def test_iv_solver_refuses_prices_outside_the_no_arbitrage_range():
    S, K, T = 100.0, 95.0, 30 / 365
    out = IV.iv_vec([4.99, 5.0, 0.0, 100.0, -1.0, np.nan], S, K, T, True)    # intrinsic 5: at/below it has no IV
    assert np.isnan(out).all()
    assert np.isnan(IV.iv_vec(95.0, S, K, T, False))                         # a put at its upper bound (K)
    assert np.isfinite(IV.iv_vec(6.0, S, K, T, True))


def test_delta_and_strike_for_delta_invert_each_other():
    for right, d in (("C", 0.20), ("C", 0.10), ("P", 0.20), ("P", 0.10), ("C", 0.55)):
        K = IV.strike_for_delta(250.0, 28 / 365, 0.45, d, right)
        got = float(IV.delta_vec(250.0, K, 28 / 365, 0.45, right == "C"))
        assert abs(abs(got) - d) < 1e-6
        assert (K > 250.0) == (right == "C" and d < 0.5)


# ---------------------------------------------------------------- the probed expiries and strikes
def test_30_day_probe_order_friday_then_monthly_and_etfs_every_session():
    d = date(2025, 3, 3)
    assert IV.exp30_phases(d) == ((date(2025, 3, 28),), (date(2025, 4, 17),))    # Good Friday 2025-04-18 -> Thursday
    etf = IV.exp30_phases(d, True)
    assert [p[0] for p in etf[:5]] == [date(2025, 3, 24), date(2025, 3, 25), date(2025, 3, 26), date(2025, 3, 27), date(2025, 3, 28)]
    assert all((p[0] - d).days >= 21 for p in etf)
    d2 = date(2025, 3, 21)                                    # first Friday >= d + 21 is the monthly itself
    assert IV.exp30_phases(d2) == ((date(2025, 4, 11),), (date(2025, 4, 17),))
    d3 = date(2025, 3, 27)
    assert IV.exp30_phases(d3) == ((date(2025, 4, 17),),)   # Good Friday's Thursday is both the weekly and the monthly


def test_90_day_probe_order_is_nearest_90_days_first():
    d = date(2025, 3, 3)
    ph = IV.exp90_phases(d)
    dist = [abs((p[0] - d).days - 90) for p in ph]
    assert dist == sorted(dist) and all(60 <= (e - d).days <= 120 for p in ph for e in p)
    flat = {e for p in ph for e in p}
    assert date(2025, 6, 30) in flat                          # a quarter-end session
    assert all(e.weekday() == 4 or e in IV.quarter_ends(e, e) or (e + timedelta(days=1)).isoformat() in periods.holidays() for e in flat)


def test_choose_expiries():
    d = date(2025, 3, 3)
    ex = [date(2025, 3, 21), date(2025, 3, 24), date(2025, 3, 28), date(2025, 5, 30), date(2025, 6, 6), date(2025, 7, 18)]
    assert IV.choose_expiries(d, ex) == (date(2025, 3, 24), date(2025, 5, 30))      # 88 days beats 95
    assert IV.choose_expiries(d, [date(2025, 5, 31), date(2025, 6, 4)]) == (date(2025, 5, 31), date(2025, 5, 31))  # tie 89/93 -> nearer
    assert IV.choose_expiries(d, [date(2025, 5, 29), date(2025, 6, 4)]) == (date(2025, 5, 29), date(2025, 5, 29))  # 87 / 93: tie -> earlier
    assert IV.choose_expiries(d, [date(2025, 5, 28), date(2025, 6, 3)])[1] == date(2025, 6, 3)                      # 86 / 92 -> 92
    assert IV.choose_expiries(d, [date(2025, 3, 7)]) == (None, None)


def test_bracket_strikes_hold_the_strikes_around_spot_on_every_plausible_grid():
    ks = IV.bracket_strikes(49.6, 49.9)
    for g in (0.5, 1.0, 2.5, 5.0):
        assert any(k <= 49.6 and 49.6 - k < g + 1e-9 for k in ks if abs(k / g - round(k / g)) < 1e-9)
        assert any(k >= 49.9 and k - 49.9 < g + 1e-9 for k in ks if abs(k / g - round(k / g)) < 1e-9)
    assert ks == [45.0, 47.5, 49.0, 49.5, 50.0]
    assert IV.bracket_strikes(100.0, 100.0)[:1] and 100.0 in IV.bracket_strikes(100.0, 100.0)
    assert set(IV.near_strikes(107.9, 100.0)) >= {107.0, 108.0, 105.0, 110.0}
    assert all(94.0 <= k <= 102.0 for k in IV.band_strikes(94.0, 102.0, 100.0))


# ---------------------------------------------------------------- one day's ATM IV
def _ts(day, minute):
    return (pd.Timestamp(f"{day} 09:30", tz=ET) + pd.Timedelta(minutes=int(minute))).isoformat()


def _stock(day, closes, sym="ABC"):
    return pd.DataFrame([{"ts": _ts(day, m), "o": c, "h": c, "l": c, "c": c, "v": 100.0, "symbol": sym} for m, c in closes.items()])


def _chain(day, sym, expiries, strikes, stock, ivf, minutes=(380, 388), rights=("C", "P"), drop=()):
    rows = []
    for e in expiries:
        for k in strikes:
            for r in rights:
                s = occ(sym, e, r, k)
                if s in drop:
                    continue
                for m in minutes:
                    S = stock[m]
                    T = bs.t_years(IV.t_minutes(day, m, e))
                    px = bs.price(S, k, T, ivf(k, r, e), r)
                    rows.append({"ts": _ts(day, m), "o": px, "h": px, "l": px, "c": round(px, 6), "v": 5.0, "symbol": s})
    return pd.DataFrame(rows)


def test_day_ivs_recovers_the_vol_and_interpolates_between_the_bracketing_strikes():
    day = date(2025, 3, 3)
    stock = {m: 100.4 + 0.01 * (m - 375) for m in range(375, 390)}
    spot = stock[389]
    e30, e90 = date(2025, 3, 28), date(2025, 5, 30)
    ivf = lambda k, r, e: 0.30 + 0.01 * (k - 100.0) + (0.05 if e == e90 else 0.0)
    opt = _chain(day, "ABC", [date(2025, 3, 21), e30, e90], [99.0, 100.0, 101.0, 102.0], stock, ivf)
    res = IV.day_ivs(day, opt, _stock(day, stock), ["ABC"])["ABC"]
    assert res["exp30"] == "2025-03-28" and res["exp90"] == "2025-05-30" and res["spot"] == pytest.approx(spot)
    want = 0.30 + 0.01 * (spot - 100.0)
    assert res["iv30"] == pytest.approx(want, abs=3e-4) and res["k30"] == [100.0, 101.0]
    assert res["iv90"] == pytest.approx(want + 0.05, abs=3e-4)


def test_day_ivs_needs_both_legs_and_a_stock_bar_in_the_print_minute():
    day = date(2025, 3, 3)
    stock = {m: 100.4 for m in range(375, 390)}
    e30 = date(2025, 3, 28)
    ivf = lambda k, r, e: 0.30
    # the put at 101 never printed: the bracket moves out to 102 (still both sides of spot)
    opt = _chain(day, "ABC", [e30], [99.0, 100.0, 101.0, 102.0], stock, ivf, drop={occ("ABC", e30, "P", 101.0)})
    r = IV.day_ivs(day, opt, _stock(day, stock), ["ABC"])["ABC"]
    assert r["k30"] == [100.0, 102.0] and r["iv30"] == pytest.approx(0.30, abs=3e-4)
    # no strike above spot with both legs: no IV (no extrapolation)
    opt = _chain(day, "ABC", [e30], [99.0, 100.0, 101.0], stock, ivf, drop={occ("ABC", e30, "C", 101.0)})
    r = IV.day_ivs(day, opt, _stock(day, stock), ["ABC"])["ABC"]
    assert r["iv30"] is None and "one side" in r["why30"]
    # the stock has no bar in the options' print minutes: every print is dropped
    sparse = {m: 100.4 for m in range(375, 390) if m not in (380, 388)}
    opt = _chain(day, "ABC", [e30], [99.0, 100.0, 101.0, 102.0], stock, ivf)
    r = IV.day_ivs(day, opt, _stock(day, sparse), ["ABC"])["ABC"]
    assert r["iv30"] is None
    # no stock bar at all
    r = IV.day_ivs(day, opt, None, ["ABC"])["ABC"]
    assert r["iv30"] is None and "stock" in r["why30"]


def test_last_print_is_the_last_bar_stamped_1545_to_1559_matched_in_its_minute():
    day = date(2025, 3, 3)
    stock = {m: 100.0 + (2.0 if m == 388 else 0.0) for m in range(370, 391)}
    e30 = date(2025, 3, 28)
    ivf = lambda k, r, e: 0.30
    opt = _chain(day, "ABC", [e30], [100.0, 101.0, 102.0, 103.0], stock, ivf, minutes=(374, 388))
    junk = opt[opt["ts"] == _ts(day, 388)].copy()
    junk["ts"] = _ts(day, 390)                                # a 16:00 bar (after hours): outside the window
    junk["c"] = 99.0
    lp = IV.last_prints(pd.concat([opt, junk]), day)
    assert set(lp["m"]) == {388}
    r = IV.day_ivs(day, pd.concat([opt, junk]), _stock(day, {m: c for m, c in stock.items() if 375 <= m <= 389}), ["ABC"])["ABC"]
    assert r["iv30"] == pytest.approx(0.30, abs=3e-4)       # priced with S = 102 at 15:58, matched in the same minute


# ---------------------------------------------------------------- the 5-session mean and no look-ahead
def test_five_session_mean_needs_all_five_and_never_looks_ahead():
    days = IV.dev_days()[:12]
    tab = IV.IVTable(days, ["A", "B"])
    for k, d in enumerate(days):
        tab.set(d, "A", {"iv30": 0.20 + 0.01 * k, "iv90": 0.25})
        if k != 6:
            tab.set(d, "B", {"iv30": 0.40})
    m = tab.mean5("iv30")
    assert np.isnan(m[3, 0]) and m[4, 0] == pytest.approx(np.mean([0.20, 0.21, 0.22, 0.23, 0.24]))
    assert np.isnan(m[6:11, 1]).all() and m[11, 1] == pytest.approx(0.40)
    assert tab.prior("iv30", days[5])[0] == pytest.approx(m[4, 0]) and np.isnan(tab.prior("iv30", days[0])).all()
    before = tab.prior("iv30", days[8]).copy()
    for d in days[8:]:                                       # change the decision day and everything after it
        tab.set(d, "A", {"iv30": 9.0})
    assert np.array_equal(tab.prior("iv30", days[8]), before, equal_nan=True)


def test_realized_vol_inside_one_segment_or_across_the_locked_gap():
    rng = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 60)))
    segs = np.r_[np.zeros(30, int), np.ones(30, int)]
    seg_rv = IV.realized_vol(c, segs, 20)
    assert np.isnan(seg_rv[:20]).all() and np.isfinite(seg_rv[20:30]).all() and np.isnan(seg_rv[30:50]).all()
    r = np.diff(np.log(c))
    assert seg_rv[29] == pytest.approx(np.std(r[9:29], ddof=1) * math.sqrt(252))
    span = IV.realized_vol(c, segs, 20, span_locked=True)
    keep = np.r_[r[25:29], r[30:45]]                         # the 20 returns ending at bar 45, the gap return (29 -> 30) left out
    assert span[45] == pytest.approx(np.std(keep, ddof=1) * math.sqrt(252))
    c2 = c.copy()
    c2[46:] *= 1.5                                           # a later jump changes nothing before it
    assert np.array_equal(IV.realized_vol(c2, segs, 20, span_locked=True)[:46], span[:46], equal_nan=True)


def test_coverage_report():
    days = IV.dev_days()[:4]
    tab = IV.IVTable(days, ["A", "B"])
    tab.set(days[0], "A", {"iv30": 0.3, "iv90": 0.32})
    tab.set(days[1], "A", {"iv30": 0.5})
    tab.set(days[1], "B", {"iv90": 0.2, "why30": "no option print 15:45-15:59"})
    nb = {d: ["A", "B"] for d in days}
    cov = IV.coverage(tab, nb, {"A": np.array([0.2, 0.2, np.nan, np.nan])})
    assert cov["name_days"] == 8 and cov["with_iv30"] == 2 and cov["with_iv90"] == 2 and cov["with_both"] == 1
    assert cov["names"]["A"]["median_iv30"] == pytest.approx(0.4) and cov["names"]["A"]["iv30_over_rv20"] == pytest.approx(2.0)
    assert cov["names"]["B"]["median_iv30"] is None and cov["share_iv30"] == 0.25
    assert any("no option print" in k for k in cov["why_missing"])


# ---------------------------------------------------------------- the cache and the pull's plan
def _write_part(root, day, window, df, asked, n=1):
    PA._write_gz(IV.opt_dir(root, day) / f"{IV.wkey(window)}.p{n:04d}.csv.gz", df.assign(ts=pd.to_datetime(df["ts"])))
    m = IV.read_marker(IV.opt_marker(root, day, window))
    a = set(m.get("asked") or []) | set(asked)
    p = set(m.get("printed") or []) | set(df["symbol"])
    IV.opt_marker(root, day, window).write_text(json.dumps({"asked": sorted(a), "printed": sorted(p), "rows": len(df)}))


def test_day_result_reads_every_part_and_rebuilds_its_cache_when_files_change(tmp_path):
    day = date(2025, 3, 3)
    stock = {m: 100.4 for m in range(375, 390)}
    ivf = lambda k, r, e: 0.30
    PA._write_gz(IV.stock_path(tmp_path, day), _stock(day, stock).assign(ts=lambda d: pd.to_datetime(d["ts"])))
    IV.marker_path(IV.stock_path(tmp_path, day)).write_text(json.dumps({"asked": ["ABC"], "rows": 15}))
    a = _chain(day, "ABC", [date(2025, 3, 28)], [100.0, 101.0], stock, ivf)
    _write_part(tmp_path, day, IV.W_LAST, a, set(a["symbol"]), 1)
    r1 = IV.day_result(tmp_path, day, ["ABC"])
    assert r1["ABC"]["iv30"] == pytest.approx(0.30, abs=3e-4) and r1["ABC"]["iv90"] is None
    assert (tmp_path / "r10" / "div" / f"{day}.json").exists() and IV.day_result(tmp_path, day, ["ABC"]) == r1
    b = _chain(day, "ABC", [date(2025, 6, 6)], [100.0, 101.0], stock, lambda k, r, e: 0.35)
    _write_part(tmp_path, day, IV.W_LAST, b, set(b["symbol"]), 2)     # a second part: the cache is rebuilt
    r2 = IV.day_result(tmp_path, day, ["ABC"])
    assert r2["ABC"]["iv90"] == pytest.approx(0.35, abs=3e-4) and r2["ABC"]["iv30"] == r1["ABC"]["iv30"]
    bars = IV.Bars(tmp_path)
    assert bars.asked(day, IV.W_LAST) == set(a["symbol"]) | set(b["symbol"])
    assert set(bars.last15(day)["ABC"]) >= {(date(2025, 3, 28), 100.0, "C"), (date(2025, 6, 6), 101.0, "P")}
    assert bars.stock_minutes(day)["ABC"][389] == 100.4 and bars.stock_minutes(date(2025, 3, 4)) is None


def test_plan_name_probes_phase_by_phase_and_stops_at_the_first_print():
    day = date(2025, 3, 3)
    mins = {375: 100.2, 389: 100.6}
    ks = IV.bracket_strikes(100.2, 100.6)
    p30, p90 = IV.exp30_phases(day), IV.exp90_phases(day)
    first = IV.plan_name("ABC", day, mins, set(), set())
    assert set(first) == set(IV.contracts("ABC", p30[0], ks)) | set(IV.contracts("ABC", p90[0], ks))
    asked = set(first)
    second = IV.plan_name("ABC", day, mins, asked, set())            # nothing printed: the next phase of each
    assert set(second) == set(IV.contracts("ABC", p30[1], ks)) | set(IV.contracts("ABC", p90[1], ks))
    printed = {IV.contracts("ABC", p30[0], ks)[0], IV.contracts("ABC", p90[0], ks)[3]}
    assert IV.plan_name("ABC", day, mins, asked, printed) == []       # both expiries found in phase 1
    assert IV.plan_name("ABC", day, {}, set(), set()) == []           # no stock bars: nothing to ask
    every = set()
    for ph in list(p30) + list(p90):
        every |= set(IV.contracts("ABC", ph, ks))
    assert IV.plan_name("ABC", day, mins, every, set()) == []         # every phase asked, none printed: finished
