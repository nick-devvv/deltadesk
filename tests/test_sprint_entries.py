"""Sprint entries (sprint/entries.py), day-type features (sprint/daytype.py) and the contract picker
(sprint/contracts.py, sprint/bs.py): rules, no look-ahead (changing future bars never changes an earlier signal or
feature), the noise band reusing noiseband's math, BS-EST deltas."""
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import bs, contracts, entries
from sprint.data import DayContext, Series

DAY = date(2025, 3, 12)


def _ctx_from(stock, stock_hl=None):
    """Context from a dict idx -> close (others carried), 12 flat prior days."""
    ctx, _ = SS.make_ctx(DAY, stock, {0: 1.0}, prior_days=12, stock_hl=stock_hl)
    return ctx


def _with_future_changed(ctx, after, seed=0):
    """A copy of ctx whose stock bars after index `after` are scrambled."""
    s = ctx.series
    s2 = Series("SPY", None)
    s2.__dict__.update({k: (dict(v) if isinstance(v, dict) else v) for k, v in s.__dict__.items()})
    g = s.rth[DAY].copy()
    rng = np.random.default_rng(seed)
    n = 389 - after
    g[after + 1:, 3] += rng.normal(0, 2, n)
    g[after + 1:, 0] = g[after + 1:, 3]
    g[after + 1:, 1] = g[after + 1:, 3] + 0.5
    g[after + 1:, 2] = g[after + 1:, 3] - 0.5
    g[after + 1:, 4] *= 5
    s2.rth = dict(s.rth)
    s2.rth[DAY] = g
    for name in ("atr1", "ema9", "hist1", "vwap", "vsd", "adx", "pdi", "mdi", "atr5"):
        d = dict(getattr(s, name))
        a = d[DAY].copy()
        a[after + 1:] = np.nan                               # anything computed from future bars is gone
        d[DAY] = a
        setattr(s2, name, d)
    s2.b5 = dict(s.b5)
    return DayContext(s2, DAY, ctx.tapes, ctx.spread, early_close=False)


def test_orb_first_finished_close_beyond_each_side_until_noon():
    stock = {0: 500.0, 5: 500.4, 10: 499.7, 14: 500.0, 20: 500.3, 21: 500.5, 30: 500.6, 40: 499.5, 45: 499.0}
    ctx = _ctx_from(stock)
    sig = entries.orb(ctx, 15)
    orh, orl = float(np.nanmax(ctx.h[:15])), float(np.nanmin(ctx.l[:15]))
    assert [(s.side, s.idx) for s in sig] == [("C", 21), ("P", 40)]          # 500.40 + 0.01 high; 500.3 close is not above it
    assert sig[0].invalid == orh and sig[1].invalid == orl and sig[0].price == 500.5
    assert [s.side for s in entries.orb(ctx, 15, "C")] == ["C"]
    late = _ctx_from({0: 500.0, 150: 501.0})                                 # first close beyond at the 12:00 bar
    assert entries.orb(late, 15) == []
    edge = _ctx_from({0: 500.0, 149: 501.0})                                 # the 11:59 bar finishes at 12:00
    assert [s.idx for s in entries.orb(edge, 15)] == [149]
    assert entries.orb(_ctx_from({0: 500.0, 10: 501.0}), 15) == []           # inside the forming range: no signal
    assert [s.setup for s in entries.signals(ctx, "orb30")] == ["orb30"] * len(entries.signals(ctx, "orb30"))


@pytest.mark.parametrize("setup", ["orb15", "orb30", "orb60", "vwap_macd", "pd_retest", "failed_break", "flush"])
def test_entries_have_no_look_ahead(setup):
    rng = np.random.default_rng(3)
    px, stock = 500.0, {}
    for i in range(390):
        px += rng.normal(0, 0.12) + (0.04 if 60 < i < 120 else -0.05 if 200 < i < 240 else 0)
        stock[i] = round(px, 2)
    ctx = _ctx_from(stock)
    full = entries.signals(ctx, setup)
    for cut in (40, 100, 180, 260):
        got = entries.signals(_with_future_changed(ctx, cut, seed=cut), setup)
        assert [(s.side, s.idx, s.price) for s in got if s.idx <= cut] == [(s.side, s.idx, s.price) for s in full if s.idx <= cut]


def test_noise_band_reuses_noiseband_math():
    import noiseband
    days = SS.weekdays(date(2025, 2, 10), 23)
    frames = [SS.stock_day(d, 500.0 + k, seed=k) for k, d in enumerate(days)]
    s = Series("SPY", pd.concat(frames, ignore_index=True))
    d = days[-1]
    ctx = DayContext(s, d, {}, SS.ConstSpread(), early_close=False)
    b = entries.noise_bands(ctx)
    rows = []
    for x in s.days:
        g = s.rth[x]
        idx = pd.date_range(f"{x} 09:30", periods=390, freq="1min", tz="America/New_York")
        rows.append(pd.DataFrame(g, index=idx, columns=["Open", "High", "Low", "Close", "Volume"]))
    m1 = pd.concat(rows)
    for i in (29, 59, 179, 329):
        t_end = pd.Timestamp(f"{d} 09:30", tz="America/New_York") + pd.Timedelta(minutes=i + 1)
        ref = noiseband.bands(m1, d, t_end)
        assert b[i] == (pytest.approx(ref["upper"]), pytest.approx(ref["lower"]))
    sig = entries.noise(ctx)
    assert all(x.idx in entries.CHECKS for x in sig)
    assert all((x.price > b[x.idx][0]) if x.side == "C" else (x.price < b[x.idx][1]) for x in sig)


def test_daytype_features_are_point_in_time():
    stock = {i: 500 + 0.05 * i for i in range(390)}
    ctx = _ctx_from(stock)
    dt = ctx.daytype()
    f = dt.features(100)
    assert f["er30"] == pytest.approx(1.0) and f["vwap_x60"] == 0 and f["overlap30"] == 0.0
    assert f["day_type"] == "trend" and dt.trend_aligned(100, "C") and not dt.trend_aligned(100, "P")
    assert f["or_accept_up"] is True and f["or_accept_down"] is False
    assert f["rvol"] == pytest.approx(1.0, abs=0.01)
    for cut in (35, 100, 250):
        a = ctx.daytype().features(cut)
        b = _with_future_changed(ctx, cut).daytype().features(cut)
        assert {k: v for k, v in a.items() if k not in ("adx", "pdi", "mdi")} == {k: v for k, v in b.items() if k not in ("adx", "pdi", "mdi")}
    chop = _ctx_from({i: 500 + (0.1 if i % 2 else 0) for i in range(390)}, {i: (500.25, 499.85) for i in range(390)})
    fc = chop.daytype().features(120)
    assert fc["vwap_x60"] > 2 and fc["er30"] < 0.35 and fc["overlap30"] == 1.0 and fc["day_type"] == "chop"


def test_bs_iv_roundtrip_and_vector_delta():
    T = bs.t_years(200)
    for right in ("C", "P"):
        for K in (495.0, 500.0, 505.0):
            p = bs.price(500.0, K, T, 0.22, right)
            iv = bs.implied_vol(p, 500.0, K, T, right)
            assert iv == pytest.approx(0.22, abs=1e-4)
            ivv, dv = bs.iv_delta_v(np.array([p]), 500.0, np.array([K]), T, np.array([right == "C"]))
            assert ivv[0] == pytest.approx(0.22, abs=1e-4) and dv[0] == pytest.approx(bs.delta(500.0, K, T, 0.22, right), abs=1e-5)
    assert bs.implied_vol(0.5, 500.0, 495.0, T, "C") is None                 # below intrinsic: no IV, no delta


def test_contract_picker_uses_bs_est_delta_band_and_only_past_prices():
    days = SS.weekdays(date(2025, 3, 10), 3)
    st = SS.stock_day(days[-1], 500.0, seed=4)
    s = Series("SPY", st)
    ob = SS.option_bars(days[-1], st, "SPY", iv=0.18, band=0.01)
    from sprint.data import read_option_day
    import pull_alpaca as PA
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        PA._write_gz(Path(td) / "options" / "SPY" / days[-1].isoformat() / "bars.csv.gz", ob)
        tapes = read_option_day("SPY", days[-1], td)
    ctx = DayContext(s, days[-1], tapes, SS.ConstSpread(), early_close=False)
    tape, info = contracts.pick(ctx, "C", 60)
    assert tape is not None and info["delta_label"] == "BS-EST" and 0.40 <= info["delta"] <= 0.55
    assert info["px"] == tape.last_close(60)
    for t in tapes.values():                                                 # future prices don't matter
        t.c[61:] = t.c[61:] * 3
    tape2, info2 = contracts.pick(ctx, "C", 60)
    assert tape2.symbol == tape.symbol and info2["delta"] == info["delta"]
    t3, why = contracts.pick(ctx, "C", 60, "d55-75t65")
    if t3 is not None:
        assert 0.55 <= why["delta"] <= 0.75
    else:
        assert why.startswith("no contract")
    assert contracts.pick(ctx, "C", 0)[0] is None or contracts.pick(ctx, "C", 0)[1]["px"] == contracts.pick(ctx, "C", 0)[0].last_close(0)
