"""Sprint level map (sprint/levels.py): each pre-registered level, its availability time, no look-ahead (changing
future bars never changes levels_at(ts)), the made-up-levels generator, and the profile vs indicators.volume_profile."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint.data import DayContext, Series
from sprint.levels import LevelMap

ET = "America/New_York"


def _day_rows(d, rth, pre=None):
    rows = []
    for m in range(240, 570):
        p = pre[m - 240] if pre is not None else rth[0][0]
        rows.append((pd.Timestamp(f"{d} {m // 60:02d}:{m % 60:02d}", tz=ET), p, p + 0.02, p - 0.02, p, 100.0))
    for i, (o, h, l, c, v) in enumerate(rth):
        m = 570 + i
        rows.append((pd.Timestamp(f"{d} {m // 60:02d}:{m % 60:02d}", tz=ET), o, h, l, c, v))
    return rows


def _rand_rth(seed, px=500.0):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(390):
        o = px
        c = px + rng.normal(0, 0.08)
        h, l = max(o, c) + abs(rng.normal(0, 0.03)), min(o, c) - abs(rng.normal(0, 0.03))
        out.append((round(o, 2), round(h, 2), round(l, 2), round(c, 2), float(rng.integers(1000, 5000))))
        px = c
    return out


@pytest.fixture
def series():
    days = SS.weekdays(date(2025, 3, 3), 8)            # Mon Mar 3 .. Wed Mar 12
    rows = []
    for k, d in enumerate(days):
        rows += _day_rows(d, _rand_rth(k, 500 + k), pre=[499 + k + 0.001 * j for j in range(330)])
    df = pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"])
    return Series("SPY", df), days


def test_each_level_and_when_it_becomes_known(series):
    s, days = series
    d = days[-1]
    ctx = DayContext(s, d, {}, SS.ConstSpread())
    lm = ctx.levels()
    prev = s.rth[days[-2]]
    kinds = lambda i: {k: px for px, k in lm.at(i)}
    k20 = kinds(20)
    assert k20["PDH"] == pytest.approx(np.nanmax(prev[:, 1])) and k20["PDL"] == pytest.approx(np.nanmin(prev[:, 2]))
    assert k20["PDC"] == pytest.approx(prev[-1, 3])
    pre = s.pre[d]
    assert k20["PMH"] == pytest.approx(pre[0]) and k20["PML"] == pytest.approx(pre[1])
    wk = [x for x in days if x < d - timedelta(days=d.weekday()) and x >= d - timedelta(days=d.weekday() + 7)]
    assert k20["PWH"] == pytest.approx(max(np.nanmax(s.rth[x][:, 1]) for x in wk))
    assert "OR15H" not in kinds(13) and "OR15H" in kinds(14)                     # complete at the end of the 09:44 bar
    assert kinds(14)["OR15H"] == pytest.approx(np.nanmax(ctx.h[:15]))
    assert "OR60L" not in kinds(58) and kinds(59)["OR60L"] == pytest.approx(np.nanmin(ctx.l[:60]))
    assert k20["VWAP"] == pytest.approx(float(ctx.vwap[20]))
    assert {"VWAP+1", "VWAP-1", "VWAP+2", "VWAP-2", "POC", "VAH", "VAL"} <= set(k20)
    rounds = [px for px, k in lm.at(20) if k in ("R1", "R5")]
    ref = float(ctx.c[20])
    assert all(abs(px - ref) <= 0.02 * ref + 1 for px in rounds) and all(px == int(px) for px in rounds)
    assert all((k == "R5") == (int(px) % 5 == 0) for px, k in lm.at(20) if k in ("R1", "R5"))
    for ci, px, kind, k in lm._swings:                  # confirmed 3 bars after the swing bar
        assert ci == k + 3
        assert (px, kind) not in lm.at(ci - 1) or any(c2 <= ci - 1 and p2 == px for c2, p2, _, _ in lm._swings if c2 != ci)
        assert (round(px, 4), kind) in lm.at(ci)


def test_levels_have_no_look_ahead(series):
    s, days = series
    d = days[-1]
    base = DayContext(s, d, {}, SS.ConstSpread()).levels()
    for i in (5, 14, 29, 61, 150, 300):
        want = base.at(i)
        s2 = Series("SPY", None)
        s2.__dict__.update({k: (dict(v) if isinstance(v, dict) else v) for k, v in s.__dict__.items()})
        g = s.rth[d].copy()
        rng = np.random.default_rng(i)
        g[i + 1:, 1] += rng.uniform(0, 5, 389 - i)
        g[i + 1:, 2] -= rng.uniform(0, 5, 389 - i)
        g[i + 1:, 3] += rng.normal(0, 3, 389 - i)
        g[i + 1:, 4] *= 7
        s2.rth = dict(s.rth)
        s2.rth[d] = g
        s2.vwap, s2.vsd = dict(s.vwap), dict(s.vsd)
        tp = (g[:, 1] + g[:, 2] + g[:, 3]) / 3
        cv = np.cumsum(g[:, 4])
        s2.vwap[d] = np.cumsum(tp * g[:, 4]) / cv
        s2.vsd[d] = np.sqrt(np.maximum(np.cumsum(tp * tp * g[:, 4]) / cv - s2.vwap[d] ** 2, 0))
        got = DayContext(s2, d, {}, SS.ConstSpread()).levels().at(i)
        assert got == want, i


def test_levels_at_time_and_next_level(series):
    s, days = series
    lm = DayContext(s, days[-1], {}, SS.ConstSpread()).levels()
    ts = pd.Timestamp(f"{days[-1]} 10:00", tz=ET)
    assert lm.levels_at(ts) == lm.at(29)                                         # bars 09:30..09:59 finished by 10:00
    assert lm.levels_at(ts + pd.Timedelta(seconds=40)) == lm.at(29)
    lv = lm.at(29)
    mid = (lv[3][0] + lv[4][0]) / 2
    up, dn = lm.next_level_above(mid, ts), lm.next_level_below(mid, ts)
    assert up[0] > mid and dn[0] < mid
    assert not any(dn[0] < px < up[0] for px, _ in lv)
    assert lm.next_level_above(lv[-1][0], ts) is None


def test_made_up_levels_are_seeded_and_sit_between_neighbors(series):
    s, days = series
    lm = DayContext(s, days[-1], {}, SS.ConstSpread()).levels()
    real = lm.at(100)
    f1, f1b, f2 = lm.fake(1).at(100), lm.fake(1).at(100), lm.fake(2).at(100)
    assert f1 == f1b and f1 != f2 and len(f1) == len(real)
    assert [k for _, k in sorted(f1, key=lambda x: x[1])] == [k for _, k in sorted(real, key=lambda x: x[1])]
    lo, hi = real[0][0] - (real[1][0] - real[0][0]), real[-1][0] + (real[-1][0] - real[-2][0])
    assert all(lo - 1e-9 <= px <= hi + 1e-9 for px, _ in f1)
    fk = lm.fake(3)
    ids = lm.identities(100)
    for q in range(1, len(real) - 1):                   # each made-up level lies between its real neighbors
        u = fk._u(ids[q])
        x = real[q - 1][0] + u * (real[q + 1][0] - real[q - 1][0])
        assert real[q - 1][0] - 1e-9 <= x <= real[q + 1][0] + 1e-9
        assert round(x, 4) in [px for px, _ in fk.at(100)]


def test_profile_matches_the_desk_indicator_within_one_bin(series):
    import indicators as I
    s, days = series
    d = days[-1]
    ctx = DayContext(s, d, {}, SS.ConstSpread())
    lm = ctx.levels()
    for i in (30, 120, 389):
        idx = pd.date_range(f"{d} 09:30", periods=i + 1, freq="1min", tz=ET)
        df = pd.DataFrame({"Open": ctx.o[:i + 1], "High": ctx.h[:i + 1], "Low": ctx.l[:i + 1], "Close": ctx.c[:i + 1],
                           "Volume": ctx.v[:i + 1]}, index=idx)
        ref = I.volume_profile(df, bin_size=0.10, value_area=0.70)
        poc, vah, val = lm.profile_at(i)
        assert abs(poc - ref["poc"]) <= 0.1 + 1e-9 and abs(vah - ref["vah"]) <= 0.1 + 1e-9 and abs(val - ref["val"]) <= 0.1 + 1e-9
