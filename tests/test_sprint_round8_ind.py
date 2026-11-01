"""Round 8, Part D (SPRINT_PLAN Addenda 10.2 and 10.3): 5-minute bars, the textbook indicators and their warm-up, the D1-D6
decision rules (crosses, D5's level touch and rejection, D6's conditions), the made-up-levels benchmark, no look-ahead, the
random-side twin, and the D share simulators (reversal, the D5/D6 stop on 1-minute closes, long-only, the exit bar and
early close, costs). Synthetic, hand-built data only."""
import copy
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import data, ind5, shares

DAY = date(2025, 3, 12)


def _ctx(path=None, prior_days=12, early=False, bars=None, px=500.0):
    ctx, _ = SS.make_ctx(DAY, path or {0: px}, {0: 1.0}, prior_days=prior_days, px=px, early=early, stock_bars=bars)
    return ctx


def _fresh(ctx):
    """An Ind5 whose arrays a test may overwrite (not the cached one)."""
    return ind5.Ind5(ctx.series)


# ---------------------------------------------------------------- bars and indicators
def test_five_minute_bars_from_the_minutes_that_exist():
    g = np.full((390, 5), np.nan)
    for i in range(10):
        g[i] = [100 + i, 101 + i, 99 + i, 100.5 + i, 10]
    g[7] = np.nan                                              # a missing minute inside bar 1
    b = ind5.bars5(g)
    assert b.shape == (78, 5)
    assert list(b[0]) == [100, 105, 99, 104.5, 50]
    assert list(b[1]) == [105, 110, 104, 109.5, 40]           # open = first existing minute, close = last, volume = sum
    assert np.isnan(b[2]).all()                                # no minute at all: no bar


def test_indicator_math_and_warm_up():
    c = np.arange(1.0, 41.0)
    r = ind5.rsi_wilder(c)
    assert np.isnan(r[:14]).all() and r[14] == 100.0 and np.all(r[14:] == 100.0)      # only gains
    assert ind5.rsi_wilder(c[::-1])[20] == 0.0
    alt = np.array([100.0 + (k % 2) for k in range(40)])                               # +1, -1, ...: equal averages
    assert ind5.rsi_wilder(alt)[14] == pytest.approx(50.0, abs=4) and ind5.rsi_wilder(np.full(30, 5.0))[20] == 50.0
    x = np.array([1.0, 2.0, 3.0, 4.0, 10.0] * 6)
    m, up, lo = ind5.bollinger(x, 5, 2.0)
    assert np.isnan(m[:4]).all() and m[4] == pytest.approx(4.0)
    assert up[4] == pytest.approx(4.0 + 2 * np.std([1, 2, 3, 4, 10])) and lo[4] == pytest.approx(4.0 - 2 * np.std([1, 2, 3, 4, 10]))
    ctx = _ctx({0: 500.0, 100: 501.0, 200: 499.0})
    ind = ind5.Ind5.of(ctx.series)
    assert ind is ind5.Ind5.of(ctx.series)                                             # cached per series
    n9 = np.isnan(ind.ema9)
    assert n9[:8].all() and not n9[8:].any() and np.isnan(ind.ema21[:20]).all() and not np.isnan(ind.ema21[20])
    assert np.isnan(ind.macd[:25]).all() and not np.isnan(ind.macd[25]) and np.isnan(ind.macd_sig[:33]).all()
    assert not np.isnan(ind.macd_hist[33]) and np.isnan(ind.atr[:13]).all() and not np.isnan(ind.atr[13])
    assert len(ind.C) == 78 * len(ctx.series.days)                                    # prior sessions included (continuous)
    k0 = ind.span[DAY][0]
    assert ind.day[k0] == DAY and ind.b[k0] == 0 and ind.span[ctx.series.days[0]][0] == 0


def test_decision_bars_are_0945_to_1500_and_stop_before_an_early_close():
    ctx = _ctx()
    ind = ind5.Ind5.of(ctx.series)
    ks = ind.decision_bars(DAY, ctx.close_idx)
    mins = [ind.minute(k) for k in ks]
    assert mins[0] == 14 and mins[-1] == 329 and len(mins) == 64                          # 09:45 .. 15:00 bar ends
    assert all(570 + m + 1 in range(585, 901, 5) for m in mins)
    e = _ctx(early=True)
    ie = ind5.Ind5.of(e.series)
    me = [ie.minute(k) for k in ie.decision_bars(DAY, e.close_idx)]
    assert me[-1] == 204 and e.close_idx == 210                                         # the next minute (205) is before 13:00


# ---------------------------------------------------------------- D1-D4 crosses
def _inject(ctx, **arrays):
    ind = _fresh(ctx)
    for k, v in arrays.items():
        setattr(ind, k, np.asarray(v, float))
    return ind


def _k(ind, b):
    a, _ = ind.span[DAY]
    return a + b


def test_rsi_crosses_up_through_30_and_down_through_70():
    ctx = _ctx()
    ind = _fresh(ctx)
    r = np.full(len(ind.C), 50.0)
    k1, k2, k3, k4 = _k(ind, 10), _k(ind, 20), _k(ind, 30), _k(ind, 65)                # b=65 is the last decision bar
    r[k1 - 1], r[k1] = 29.0, 31.0
    r[k2 - 1], r[k2] = 71.0, 69.0
    r[k3 - 1], r[k3] = 30.0, 30.0001                                                    # prev <= 30 < now: a cross
    r[k4 - 1], r[k4] = 29.0, 30.0                                                       # 30 is not above 30: no cross
    ind.rsi = r
    s = ind5.signals(ctx, "ind_rsi", ind=ind)
    assert [(x["idx"], x["side"]) for x in s] == [(54, "C"), (104, "P"), (154, "C")]
    assert all(x["price"] == float(ind.C[_k(ind, (x["idx"] - 4) // 5)]) for x in s)
    r[k1 - 1] = np.nan                                                                  # warm-up: no previous value, no cross
    assert [(x["idx"], x["side"]) for x in ind5.signals(ctx, "ind_rsi", ind=ind)] == [(104, "P"), (154, "C")]


def test_bollinger_ema_and_macd_crosses():
    ctx = _ctx()
    ind = _fresh(ctx)
    n = len(ind.C)
    C, lo, up = np.full(n, 100.0), np.full(n, 99.0), np.full(n, 101.0)
    k = _k(ind, 12)
    C[k - 1], C[k] = 98.5, 99.5                                                         # back above the lower band
    k2 = _k(ind, 30)
    C[k2 - 1], C[k2] = 101.5, 100.5                                                     # back below the upper band
    ind.C, ind.bb_lo, ind.bb_up = C, lo, up
    assert [(x["idx"], x["side"]) for x in ind5.signals(ctx, "ind_bb", ind=ind)] == [(64, "C"), (154, "P")]
    e9, e21 = np.full(n, 1.0), np.full(n, 2.0)
    k3 = _k(ind, 20)
    e9[k3:] = 3.0                                                                       # 9 crosses above 21 at b=20
    k4 = _k(ind, 50)
    e9[k4:] = 1.0                                                                       # and below at b=50
    ind.ema9, ind.ema21 = e9, e21
    assert [(x["idx"], x["side"]) for x in ind5.signals(ctx, "ind_ema", ind=ind)] == [(104, "C"), (254, "P")]
    ind.macd, ind.macd_sig = e9.copy(), e21.copy()
    assert [(x["idx"], x["side"]) for x in ind5.signals(ctx, "ind_macd", ind=ind)] == [(104, "C"), (254, "P")]
    eq = np.full(n, 2.0)
    eq[k3:] = 3.0
    ind.macd = eq                                                                       # touching (prev ==) then above: a cross
    assert [x["idx"] for x in ind5.signals(ctx, "ind_macd", ind=ind)] == [104]
    ind.macd_sig = np.where(np.arange(n) < k3, np.nan, 2.0)                             # warm-up at k-1: none
    assert ind5.signals(ctx, "ind_macd", ind=ind) == []


# ---------------------------------------------------------------- D5 and D6
class _Levels:
    def __init__(self, lv):
        self.lv = sorted(lv)

    def at(self, i):
        return self.lv


def test_d5_level_touch_rejection_and_nearest_level():
    ctx = _ctx()
    ind = _fresh(ctx)
    n = len(ind.C)
    ind.rsi, ind.atr = np.full(n, 50.0), np.full(n, 1.0)
    ind.C, ind.L, ind.H = np.full(n, 100.0), np.full(n, 99.5), np.full(n, 100.5)
    k = _k(ind, 10)
    ind.rsi[k] = 28.0
    ind.L[k], ind.C[k] = 98.95, 99.4                                                    # within 0.10 x ATR above PDL 98.9? no: below 99.0
    ctx.levels = lambda fake_seed=None: _Levels([(99.0, "PDL"), (99.3, "VWAP-2"), (98.0, "PWL"), (99.35, "R1"), (101.0, "PDH")])
    s = ind5.signals(ctx, "conf_level_rsi", ind=ind)
    assert len(s) == 1 and s[0]["side"] == "C" and s[0]["idx"] == 54
    assert s[0]["info"]["kind"] == "VWAP-2" and s[0]["info"]["level"] == 99.3             # nearest qualifying level to the close
    assert s[0]["info"]["stop"] == pytest.approx(99.3 - 0.1)                            # level - 0.10 x ATR; R1 is not a support kind
    ind.C[k] = 99.25                                                                    # closes below VWAP-2: only PDL qualifies
    s = ind5.signals(ctx, "conf_level_rsi", ind=ind)
    assert s[0]["info"]["kind"] == "PDL"
    ind.C[k], ind.L[k] = 99.4, 99.45                                                    # low 0.15 above every support: too far
    assert ind5.signals(ctx, "conf_level_rsi", ind=ind) == []
    ind.L[k], ind.rsi[k] = 99.1, 31.0                                                   # within 0.10 of 99.0, but RSI > 30
    assert ind5.signals(ctx, "conf_level_rsi", ind=ind) == []
    ind.rsi[k] = 72.0
    ind.H[k], ind.C[k] = 101.05, 100.8                                                  # resistance touched, close back below
    s = ind5.signals(ctx, "conf_level_rsi", ind=ind)
    assert s[0]["side"] == "P" and s[0]["info"]["kind"] == "PDH" and s[0]["info"]["stop"] == pytest.approx(101.1)
    ind.C[k] = 101.2                                                                    # closed above it: no rejection
    assert ind5.signals(ctx, "conf_level_rsi", ind=ind) == []


def test_d5_runs_on_real_and_made_up_levels():
    rng = np.random.default_rng(3)
    path = {i: 500.0 + float(np.cumsum(rng.normal(0, 0.15, 390))[i]) for i in range(390)}
    ctx = _ctx(path, prior_days=15)
    ind = _fresh(ctx)
    ind.rsi = np.where(np.arange(len(ind.C)) % 3 == 0, 20.0, 80.0)                       # extreme RSI everywhere
    ind.atr = np.full(len(ind.C), 5.0)                                                  # wide touch zone
    real = ind5.signals(ctx, "conf_level_rsi", ind=ind)
    fakes = {sd: ind5.signals(ctx, "conf_level_rsi", fake_seed=sd, ind=ind) for sd in (1, 2, 3, 4, 5)}
    assert real and any(f != real for f in fakes.values())
    lm = ctx.levels()
    for s in real:
        kinds = ind5.SUPPORT if s["side"] == "C" else ind5.RESIST
        assert s["info"]["kind"] in kinds and (s["info"]["level"], s["info"]["kind"]) in lm.at(s["idx"])
    fk = ctx.levels(2)
    for s in fakes[2]:
        assert (s["info"]["level"], s["info"]["kind"]) in fk.at(s["idx"])


def test_d6_trend_pullback_conditions():
    ctx = _ctx()
    ind = _fresh(ctx)
    n = len(ind.C)
    k = _k(ind, 20)
    m = ind.minute(k)
    ctx.vwap[:] = 100.0
    ind.C, ind.L, ind.H = np.full(n, 101.0), np.full(n, 100.5), np.full(n, 101.5)
    ind.ema9, ind.ema21, ind.atr = np.full(n, 100.8), np.full(n, 100.6), np.full(n, 1.0)
    ind.macd_hist = np.full(n, 0.0)
    ind.macd_hist[k] = 0.1                                                             # rising on this bar only
    ind.L[k] = 100.65                                                                  # 0.05 above EMA21: a pullback
    s = ind5.signals(ctx, "conf_trend_pullback", ind=ind)
    assert [(x["idx"], x["side"]) for x in s] == [(m, "C")]
    assert s[0]["info"]["stop"] == pytest.approx(100.65 - 0.1)
    ind.L[k] = 100.4                                                                   # 0.20 below EMA21 and 0.40 above VWAP: too far
    assert ind5.signals(ctx, "conf_trend_pullback", ind=ind) == []
    ind.L[k] = 100.05                                                                  # within 0.10 of VWAP
    assert len(ind5.signals(ctx, "conf_trend_pullback", ind=ind)) == 1
    ind.ema9[k] = 100.5                                                                # EMA9 below EMA21: no trend
    assert ind5.signals(ctx, "conf_trend_pullback", ind=ind) == []
    ind.ema9[k] = 100.8
    ind.macd_hist[k:] = -0.1                                                           # histogram falling, then flat
    assert ind5.signals(ctx, "conf_trend_pullback", ind=ind) == []
    ind.macd_hist = np.full(n, 0.0)
    ind.C, ind.L, ind.H = np.full(n, 99.0), np.full(n, 98.5), np.full(n, 99.5)          # the mirror: puts
    ind.ema9, ind.ema21 = np.full(n, 99.2), np.full(n, 99.4)
    ind.H[k], ind.macd_hist[k] = 99.35, -0.1
    s = ind5.signals(ctx, "conf_trend_pullback", ind=ind)
    assert [(x["idx"], x["side"]) for x in s] == [(m, "P")] and s[0]["info"]["stop"] == pytest.approx(99.45)


# ---------------------------------------------------------------- no look-ahead and the random side
def _random_series(days, seed=4):
    rng = np.random.default_rng(seed)
    frames, px = [], 400.0
    for d in days:
        df = SS.stock_day(d, px, int(rng.integers(1, 1e6)), vol=0.0008)
        frames.append(df)
        px = float(df["c"].iloc[-1])
    return pd.concat(frames, ignore_index=True)


def test_d_rules_have_no_look_ahead():
    days = SS.weekdays(date(2025, 2, 3), 14)
    df = _random_series(days)
    day = days[10]
    base = data.Series("SPY", df)
    ctx = data.DayContext(base, day, {}, None)
    want = {r: ind5.signals(ctx, r) for r in ind5.RULES}
    assert sum(len(v) for v in want.values()) > 5
    for cut in (100, 200, 300):
        df2 = df.copy()
        ts = df2["ts"]
        later = (ts.dt.date > day) | ((ts.dt.date == day) & ((ts.dt.hour * 60 + ts.dt.minute - 570) > cut))
        for c in ("o", "h", "l", "c"):
            df2.loc[later, c] = df2.loc[later, c] * 1.03
        df2.loc[later, "v"] *= 5
        c2 = data.DayContext(data.Series("SPY", df2), day, {}, None)
        for r in ind5.RULES:
            got = [(x["idx"], x["side"], round(x["price"], 6)) for x in ind5.signals(c2, r) if x["idx"] <= cut]
            assert got == [(x["idx"], x["side"], round(x["price"], 6)) for x in want[r] if x["idx"] <= cut], (r, cut)


def test_random_side_keeps_days_and_minutes_and_is_seeded():
    sigs = [{"idx": 14 + 5 * k, "side": "C", "price": 1.0, "info": {}} for k in range(40)]
    a = ind5.random_side(sigs, 31, "SPY", DAY)
    b = ind5.random_side(sigs, 31, "SPY", DAY)
    c = ind5.random_side(sigs, 32, "SPY", DAY)
    assert a == b and [x["idx"] for x in a] == [x["idx"] for x in sigs] and a != c
    assert 10 < sum(x["side"] == "P" for x in a) < 30 and all(x["info"]["random_seed"] == 31 for x in a)


# ---------------------------------------------------------------- D share simulators
def _sig(i, side, px=100.0, stop=None):
    return {"idx": i, "side": side, "price": px, "info": {} if stop is None else {"stop": stop}}


def test_d1_d4_shares_reverse_on_the_opposite_signal_and_close_at_1559():
    path = {0: 100.0, 15: 101.0, 55: 103.0, 105: 102.0, 300: 99.0, 389: 98.0}
    ctx = _ctx(path, px=100.0)
    sigs = [_sig(14, "C", 100.0), _sig(54, "C", 101.0), _sig(104, "P", 103.0)]
    tr = shares.d_day(ctx, "DEV", "ind_ema", sigs)
    assert [(t["side"], t["entry_idx"], t["exit_idx"]) for t in tr] == [("L", 15, 105), ("S", 105, 389)]
    a, b = tr
    assert a["shares"] == 100 and a["entry"] == 101.01 and a["exit"] == 101.99            # next open +/- $0.01
    assert a["pnl"] == pytest.approx(100 * (102.0 - 101.0 - 0.02)) and a["pnl_2x"] == pytest.approx(100 * (1.0 - 0.04))
    assert b["shares"] == 97 and b["exit_reason"].startswith("CLOSE 15:59") and b["exit_ref"] == 98.0
    assert b["pnl"] == pytest.approx(97 * (102.0 - 98.0 - 0.02)) and a["exit_reason"].startswith("OPPOSITE SIGNAL")
    assert a["bps"] == pytest.approx(a["pnl"] / (100 * 101.0) * 1e4)
    lo = shares.d_day(ctx, "DEV", "ind_ema", sigs, "ind_ema_lo", long_only=True)
    assert [(t["side"], t["entry_idx"], t["exit_idx"]) for t in lo] == [("L", 15, 105)]   # a short signal only closes the long
    e = _ctx(path, early=True, px=100.0)
    te = shares.d_day(e, "DEV", "ind_ema", sigs)
    assert te[-1]["exit_idx"] == 209 and te[-1]["exit_reason"].startswith("CLOSE 12:59")


def test_d5_d6_shares_stop_on_one_minute_closes_and_skip_signals_while_open():
    path = {0: 100.0, 20: 100.5, 40: 99.0, 45: 99.5, 60: 100.0, 389: 101.0}
    ctx = _ctx(path, px=100.0)
    sigs = [_sig(14, "C", 100.0, stop=99.2), _sig(39, "P", 99.6, stop=100.4), _sig(40, "C", 99.0, stop=98.0),
            _sig(54, "C", 99.5, stop=98.5)]
    tr = shares.d_day(ctx, "DEV", "conf_level_rsi", sigs)
    t0 = tr[0]
    assert (t0["side"], t0["entry_idx"], t0["exit_idx"]) == ("L", 15, 41)               # close 99.0 < 99.2 at bar 40 -> next open
    assert t0["exit_reason"].startswith("STOP 99.20") and t0["exit"] == round(99.0 - 0.01, 4)
    # the P signal at 39 came while long (skipped, no reversal); the C at 40 is on the stop bar (still open): skipped
    assert [(t["side"], t["entry_idx"]) for t in tr[1:]] == [("L", 55)] and tr[1]["exit_idx"] == 389
    lo = shares.d_day(ctx, "DEV", "conf_level_rsi", [_sig(14, "P", 100.0, stop=100.6), _sig(24, "C", 100.5, stop=99.6)],
                      "x", long_only=True)
    assert [(t["side"], t["entry_idx"]) for t in lo] == [("L", 25)]                     # long-only: the short never opens


def test_share_variants_and_trial_names():
    v = shares.variants()
    assert set(shares.TRIAL_VARIANTS) <= set(v) and len(shares.TRIAL_VARIANTS) == 8
    assert len(shares.D_TRIAL_VARIANTS) == 12 and all(x in v for x in shares.D_TRIAL_VARIANTS)
    assert [x for x in v if "fake" in x] == [f"conf_level_rsi{s}_fake{k}" for k in range(1, 6) for s in ("", "_lo")]
