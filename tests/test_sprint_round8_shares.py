"""Round 8, Part A (SPRINT_PLAN Amendment 10): the share rules on hand-built bars (A1 noise_sh bands, checks, reversals and the
VWAP stop; A2 last30 and Gao; A3 gapfade_vix's gap z and VIXY z), costs ($0.01 a share a side, 2x = $0.02), sizing
($10,000 / the decision bar's close, the vol-sized A1), the exit bar and early close, long-only, no look-ahead, the locked-date
refusal, and the 7-item pass bar with its seeded bootstrap (29) and random-direction draws (31-230). Synthetic data only."""
import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import book, data, features, periods, shares

DAY = date(2025, 3, 12)
ET = "America/New_York"


def _ctx(path, early=False, px=100.0, prior_days=20):
    ctx, _ = SS.make_ctx(DAY, path, {0: 1.0}, prior_days=prior_days, px=px, early=early)
    return ctx


def _bands(monkeypatch, ub=101.0, lb=99.0):
    monkeypatch.setattr(shares, "a1_bands", lambda s, d: (np.full(390, ub), np.full(390, lb)))


# ---------------------------------------------------------------- A1 noise_sh
PATH = {0: 100.0, 29: 101.5, 59: 100.5, 89: 102.0, 119: 98.0, 149: 99.5, 179: 98.5, 389: 97.0}


def test_a1_entries_band_stop_reversal_and_close(monkeypatch):
    _bands(monkeypatch)
    ctx = _ctx(PATH)
    ctx.vwap[:] = 100.0
    tr = shares.a1_day(ctx, "DEV")
    assert [(t["side"], t["decision_idx"], t["entry_idx"], t["exit_idx"]) for t in tr] == [
        ("L", 29, 30, 60), ("L", 89, 90, 120), ("S", 119, 120, 150), ("S", 179, 180, 389)]
    a, b, c, d = tr
    assert a["shares"] == 98 and a["entry"] == 101.51 and a["exit"] == 100.49 and a["exit_reason"].startswith("NOISE STOP")
    assert a["pnl"] == pytest.approx(98 * (100.5 - 101.5 - 0.02)) and a["pnl_2x"] == pytest.approx(98 * (-1.0 - 0.04))
    assert b["exit_reason"] == "NOISE REVERSAL" and b["exit_ref"] == c["entry_ref"] == 98.0         # reverse at the same open
    assert c["shares"] == 102 and c["pnl"] == pytest.approx(102 * (98.0 - 99.5 - 0.02))
    assert d["shares"] == 101 and d["exit_reason"].startswith("CLOSE 15:59") and d["exit"] == 97.01
    assert d["pnl"] == pytest.approx(101 * (98.5 - 97.0 - 0.02)) and d["bps"] == pytest.approx(d["pnl"] / (101 * 98.5) * 1e4)
    lo = shares.a1_day(ctx, "DEV", "noise_sh_lo", long_only=True)
    assert [(t["side"], t["entry_idx"], t["exit_idx"]) for t in lo] == [("L", 30, 60), ("L", 90, 120)]   # a short never opens


def test_a1_vwap_side_of_the_stop_and_early_close(monkeypatch):
    _bands(monkeypatch)
    ctx = _ctx({0: 100.0, 29: 101.5, 59: 101.6, 389: 102.0})
    ctx.vwap[:] = 102.0                                                     # max(UB, VWAP) = 102: a close of 101.6 exits
    tr = shares.a1_day(ctx, "DEV")                                          # ... and above UB re-enters at the next check from flat
    assert [(t["entry_idx"], t["exit_idx"]) for t in tr] == [(30, 60), (90, 120), (150, 180), (210, 240), (270, 300), (330, 360)]
    ctx.vwap[:] = 100.0                                                     # max(UB, VWAP) = 101: 101.6 holds to the close
    assert [(t["entry_idx"], t["exit_idx"]) for t in shares.a1_day(ctx, "DEV")] == [(30, 389)]
    e = _ctx(PATH, early=True)
    e.vwap[:] = 100.0
    te = shares.a1_day(e, "DEV")
    assert max(t["decision_idx"] for t in te) <= 179 and te[-1]["exit_idx"] == 209 and te[-1]["exit_reason"].startswith("CLOSE 12:59")
    assert shares.CHECKS_A1 == tuple(range(29, 360, 30)) and len(shares.CHECKS_A1) == 12


def _series_from(days, opens, closes, early=()):
    """A Series whose day k opens at opens[k] and whose 1-minute closes are closes[k] (390 values, NaN = no bar)."""
    rows = []
    for d, o, cs in zip(days, opens, closes):
        for i in range(390):
            if math.isnan(cs[i]) or (d in early and i >= 210):
                continue
            op = o if i == 0 else cs[i - 1] if not math.isnan(cs[i - 1]) else cs[i]
            rows.append((pd.Timestamp(f"{d} {(570 + i) // 60:02d}:{(570 + i) % 60:02d}", tz=ET), op, max(op, cs[i]) + 0.01,
                         min(op, cs[i]) - 0.01, cs[i], 1000.0))
    return data.Series("SPY", pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"]))


def test_a1_sigma_is_the_mean_abs_move_of_14_prior_sessions_and_the_bands():
    days = SS.weekdays(date(2025, 1, 6), 17)
    opens = [100.0] * 17
    closes = [np.full(390, 100.0 * (1 + 0.001 * (k + 1))) for k in range(17)]
    closes[10] = closes[10].copy()
    closes[10][300:] = np.nan                                               # one prior session without bars after 14:30
    s = _series_from(days, opens, closes)
    d = days[16]
    sig = shares.a1_sigma(s, d)
    want100 = np.mean([0.001 * (k + 1) for k in range(2, 16)])               # sessions 2..15 (the 14 before day 16)
    want300 = np.mean([0.001 * (k + 1) for k in range(2, 16) if k != 10])    # 13 sessions have a bar at t = 300
    assert sig[100] == pytest.approx(want100) and sig[300] == pytest.approx(want300)
    assert np.isnan(shares.a1_sigma(s, days[9])[100])                      # 9 prior sessions: fewer than 10
    assert not np.isnan(shares.a1_sigma(s, days[10])[100])
    ub, lb = shares.a1_bands(s, d)
    pc = float(closes[15][-1])
    assert ub[100] == pytest.approx(max(100.0, pc) * (1 + want100)) and lb[100] == pytest.approx(min(100.0, pc) * (1 - want100))
    assert shares.a1_bands(s, days[0]) is None                             # no prior close
    n = shares.a1_vol_notional(s, d)
    c = s.daily["close"].to_numpy(float)[1:16]
    sd = float(np.std(c[1:] / c[:-1] - 1, ddof=1))
    assert n == pytest.approx(10_000 * min(4.0, 0.02 / sd)) and shares.a1_vol_notional(s, days[14]) is None


def test_a1_has_no_look_ahead(monkeypatch):
    rng = np.random.default_rng(2)
    path = {i: 100.0 + float(np.cumsum(rng.normal(0, 0.08, 390))[i]) for i in range(390)}
    ctx = _ctx(path)
    want = [(t["decision_idx"], t["side"], t["entry_idx"], t["entry_ref"]) for t in shares.a1_day(ctx, "DEV")]
    bands = shares.a1_bands(ctx.series, DAY)
    for cut in (120, 240):
        p2 = {i: (v if i <= cut else v * 1.05) for i, v in path.items()}
        c2 = _ctx(p2)
        got = [(t["decision_idx"], t["side"], t["entry_idx"], t["entry_ref"]) for t in shares.a1_day(c2, "DEV") if t["decision_idx"] < cut]
        assert got == [x for x in want if x[0] < cut]
        assert np.allclose(shares.a1_bands(c2.series, DAY)[0], bands[0], equal_nan=True)   # today's bands use the open + prior days


# ---------------------------------------------------------------- A2 last30
def test_a2_rest_of_day_and_gao():
    ctx = _ctx({0: 100.0, 29: 99.0, 359: 100.5, 360: 100.6, 389: 101.0})
    t = shares.a2_day(ctx, "DEV")
    assert len(t) == 1 and t[0]["side"] == "L" and (t[0]["decision_idx"], t[0]["entry_idx"], t[0]["exit_idx"]) == (359, 360, 389)
    assert t[0]["shares"] == 99 and t[0]["pnl"] == pytest.approx(99 * (101.0 - 100.6 - 0.02))
    g = shares.a2_day(ctx, "DEV", gao=True)                                # r1 at 10:00 is negative: short the same window
    assert g[0]["side"] == "S" and g[0]["variant"] == "last30_gao" and g[0]["shares"] == 101 and g[0]["entry_idx"] == 360
    assert shares.a2_day(ctx, "DEV", gao=True, long_only=True) == []
    flat = _ctx({0: 100.0, 359: 100.0, 389: 101.0})                         # r = 0: no trade
    assert shares.a2_day(flat, "DEV") == []
    assert shares.a2_day(_ctx({0: 100.0, 359: 100.5}, early=True), "DEV") == []       # no trade on early-close days


# ---------------------------------------------------------------- A3 gapfade_vix
def _gap_series(n=70, seed=5, last_gap=0.02):
    rng = np.random.default_rng(seed)
    days = SS.weekdays(date(2025, 1, 6), n)
    opens, closes, px = [], [], 100.0
    for k in range(n):
        g = last_gap if k == n - 1 else float(rng.normal(0, 0.004))
        o = px * (1 + g) if k else px
        cs = np.full(390, o)
        cs[60:] = o * 0.995
        opens.append(o)
        closes.append(cs)
        px = float(cs[-1])
    return days, _series_from(days, opens, closes)


def _vixy(days, spike=3.0):
    vals = [20.0 + 0.1 * math.sin(k) for k in range(len(days) + 80)]
    idx = [days[0] - timedelta(days=d) for d in range(80, 0, -1)] + list(days)
    s = pd.Series(vals, index=idx)
    s.iloc[-2] += spike                                                    # the prior session's close jumps
    return s


def test_a3_gap_z_vixy_z_and_the_trade():
    days, s = _gap_series()
    vd = _vixy(days)
    d = days[-1]
    side, info = shares.a3_signal(s, d, vd)
    g = shares.gap_table(s)
    k = len(days) - 1
    w = g[k - 60:k]
    assert info["gap"] == pytest.approx(round(g[k], 6)) and info["gap_z"] == pytest.approx(g[k] / np.std(w, ddof=1), abs=1e-4)
    v = vd.to_numpy()
    pk = list(vd.index).index(days[-2])
    assert info["vixy_z"] == pytest.approx((v[pk] - v[pk - 60:pk].mean()) / np.std(v[pk - 60:pk], ddof=1), abs=1e-4)
    assert side == "P"                                                     # a gap up is faded with a short
    ctx = data.DayContext(s, d, {}, None)
    t = shares.a3_day(ctx, "DEV", vd)
    assert len(t) == 1 and t[0]["side"] == "S" and (t[0]["decision_idx"], t[0]["entry_idx"], t[0]["exit_idx"]) == (59, 60, 389)
    assert t[0]["shares"] == math.floor(10_000 / float(ctx.c[59]))
    assert shares.a3_day(ctx, "DEV", vd, long_only=True) == []
    assert shares.a3_signal(s, d, _vixy(days, spike=0.0))[0] is None       # VIXY z <= 0.5: no trade
    days2, s2 = _gap_series(last_gap=-0.02)
    assert shares.a3_signal(s2, days2[-1], _vixy(days2))[0] == "C"
    days3, s3 = _gap_series(last_gap=0.001)
    assert shares.a3_signal(s3, days3[-1], _vixy(days3))[0] is None       # |gap z| <= 1
    assert shares.a3_signal(s, days[30], vd)[0] is None                    # fewer than 40 prior gaps
    sig = shares.a3_option_signals(data.DayContext(s, d, {}, None, aux={"VIXY_D": vd}))
    assert [(x["idx"], x["side"]) for x in sig] == [(59, "P")] and sig[0]["exits"] == {"C": {}, "P": {}}


# ---------------------------------------------------------------- guards
def test_share_loader_refuses_locked_ranges(tmp_path):
    for a, b in ((date(2024, 1, 2), date(2024, 2, 5)), (date(2026, 6, 1), date(2026, 7, 2))):
        with pytest.raises(periods.LockedPeriod):
            shares.load_series("SPY", a, b, tmp_path)
    assert shares.load_series("SPY", date(2024, 8, 1), date(2024, 8, 9), tmp_path).days == []


# ---------------------------------------------------------------- metrics and the pass bar
def _trades(n_every=5, win=0.8, move=0.5, seed=1, bad_years=()):
    rng = np.random.default_rng(seed)
    out = []
    for k, d in enumerate(shares.all_sessions()[::n_every]):
        m = move if rng.uniform() < win else -move
        if d[:4] in bad_years:
            m = -abs(move)
        sh = 100
        out.append({"variant": "x", "symbol": ("SPY", "QQQ")[k % 2], "day": d, "side": "L", "sign": 1, "entry_idx": 30, "exit_idx": 389,
                    "shares": sh, "move": m, "pnl": sh * (m - 0.02), "pnl_2x": sh * (m - 0.04), "bps": 1.0})
    return out


def test_pass_bar_items_and_their_seeds():
    tr = _trades()
    pb = shares.pass_bar(tr)
    assert pb["pass"] and len(pb["checks"]) == 7 and pb["random_p"] == 0.0
    assert shares.pass_bar(tr) == pb                                       # seeded: the same numbers every time
    ses = shares.all_sessions()
    d = shares.daily(tr, ses)
    assert pb["boot_ci"] == shares.bootstrap_daily(d, 29, 2000) != shares.bootstrap_daily(d, 30, 2000)
    rng = np.random.default_rng(29)
    means = np.concatenate([d[rng.integers(0, len(d), size=(250, len(d)))].mean(axis=1) for _ in range(8)])
    assert pb["boot_ci"] == pytest.approx(tuple(np.round(np.percentile(means, [2.5, 97.5]), 4)))
    p, tots = shares.random_direction(tr)
    assert len(tots) == 200
    f0 = np.random.default_rng(31).choice(np.array([-1.0, 1.0]), len(tr))
    o = shares.ordered(tr)
    assert tots[0] == pytest.approx(sum(t["shares"] * (s * t["move"] - 0.02) for t, s in zip(o, f0)))
    bad = shares.pass_bar(_trades(bad_years=("2016", "2017", "2018")))
    assert not bad["pass"] and not bad["checks"][2][1]                     # 5 of 8 years: item 3 fails
    thin = shares.pass_bar(_trades(n_every=10))
    assert not thin["checks"][0][1]                                        # fewer than 300 trades
    coin = shares.pass_bar(_trades(win=0.5, move=0.5, seed=4))
    assert not coin["checks"][5][1] and not coin["pass"]                    # no edge over random direction
    cheap = shares.pass_bar(_trades(win=0.51, move=0.03, seed=6))
    assert not cheap["checks"][1][1]                                        # gone at 2x costs


def test_steadiness_metrics():
    rows = [{"day": d, "pnl": p} for d, p in (("2025-01-06", 10.0), ("2025-01-07", -30.0), ("2025-02-03", -5.0), ("2025-03-03", -1.0),
                                              ("2025-04-01", 4.0), ("2025-05-05", -2.0))]
    st = shares.steadiness(rows)
    assert st["months"] == 5 and st["months_green"] == 1 and st["longest_losing_months"] == 3
    assert st["worst_month"] == ("2025-01", -20.0) and st["weeks"] == 5 and st["weeks_green"] == 1
    assert shares.corr([1, 2, 3, 4], [2, 4, 6, 8]) == 1.0 and shares.corr([1, 1, 1], [1, 2, 3]) is None
    yt = shares.years_table([dict(r, pnl_2x=r["pnl"], bps=1.0, entry_idx=1, symbol="SPY") for r in rows])
    assert list(yt) == [n for n, _, _ in shares.YEARS] and yt["2025"]["trades"] == 6
