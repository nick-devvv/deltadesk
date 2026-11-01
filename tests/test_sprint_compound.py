"""Amendment 16's compounding view (sprint/compound.py): the input formats (per trade in dollars, per trade or per session in
risk units, list or DataFrame), sessions without a trade, the fixed-fractional arithmetic on hand-checkable paths, ruin,
halving, the seeded resampling by session (restart safety), and the refusals (bad risk, unknown days, L1/L2 rows).
Synthetic numbers only."""
import math

import numpy as np
import pandas as pd
import pytest

from sprint import book, compound as C, periods

DAYS = book.sessions_between("2025-01-02", "2025-03-31")


def _trades(seed=1, n_days=40, per_day=2):
    rng = np.random.default_rng(seed)
    out = []
    for d in DAYS[:n_days]:
        for _ in range(per_day):
            risk = float(rng.uniform(80, 250))
            out.append({"day": d, "pnl": float(rng.normal(0.1, 1.0)) * risk, "risk": risk})
    return out


def test_defaults_are_the_pre_registered_view():
    assert C.START == 3000.0 and C.FRACTIONS == (0.01, 0.02, 0.05) and C.PATHS == 2000 and C.HALVE == 0.5
    v = C.simulate(_trades(), DAYS)
    assert list(v["fractions"]) == ["1%", "2%", "5%"] and v["paths"] == 2000 and v["start"] == 3000.0 and v["halve_at"] == 1500.0
    for k in ("median_end", "p5_end", "worst_dd_pct", "p_halve"):
        assert all(k in f for f in v["fractions"].values())
    assert v["input"]["trades"] == 80 and v["input"]["sessions"] == len(DAYS) and v["input"]["sessions_with_trades"] == 40


def test_per_trade_dollars_per_trade_r_and_per_session_r_agree():
    tr = _trades(seed=3)
    a = C.simulate(tr, DAYS, paths=300)
    b = C.simulate([{"day": t["day"], "r": t["pnl"] / t["risk"]} for t in tr], DAYS, paths=300)
    by = {}
    for t in tr:
        by[t["day"]] = by.get(t["day"], 0.0) + t["pnl"] / t["risk"]
    c = C.simulate([{"day": d, "r": r} for d, r in by.items()], DAYS, paths=300)
    d = C.simulate(pd.DataFrame(tr), DAYS, paths=300)
    assert a["fractions"] == b["fractions"] == d["fractions"]
    for k, v in a["fractions"].items():                                    # session sums: equal up to float summation order
        for kk, x in v.items():
            assert c["fractions"][k][kk] == pytest.approx(x, rel=1e-9, abs=1e-6)


def test_session_r_counts_days_without_a_trade_as_zero():
    days, rs, n = C.session_r([{"day": DAYS[1], "pnl": 50.0, "risk": 100.0}, {"day": DAYS[1], "r": -0.25}], DAYS[:4])
    assert days == DAYS[:4] and list(rs) == [0.0, 0.25, 0.0, 0.0] and list(n) == [0, 2, 0, 0]
    d2, r2, _ = C.session_r([{"day": DAYS[1], "r": 1.0}])                   # no sessions: only days with a row
    assert d2 == [DAYS[1]] and list(r2) == [1.0]


def test_fixed_fraction_arithmetic_on_constant_paths():
    days = DAYS[:20]
    up = C.simulate([{"day": d, "r": 1.0} for d in days], days, paths=50)
    for f, k in ((0.01, "1%"), (0.02, "2%"), (0.05, "5%")):
        v = up["fractions"][k]
        assert v["median_end"] == pytest.approx(round(3000 * (1 + f) ** 20, 2)) and v["p5_end"] == v["median_end"]
        assert v["worst_dd_pct"] == 0.0 and v["p_halve"] == 0.0 and v["p_ruin"] == 0.0
    dn = C.simulate([{"day": d, "r": -1.0} for d in days], days, paths=50)
    v = dn["fractions"]["5%"]
    assert v["median_end"] == pytest.approx(round(3000 * 0.95 ** 20, 2))
    assert v["worst_dd_pct"] == pytest.approx(round((0.95 ** 20 - 1) * 100, 1))
    assert v["p_halve"] == (1.0 if 0.95 ** 20 <= 0.5 else 0.0) and v["p_end_below_start"] == 1.0
    two = C.simulate([{"day": d, "r": -1.0} for d in DAYS[:14]], DAYS[:14], paths=10)
    assert two["fractions"]["5%"]["p_halve"] == 1.0 and two["fractions"]["1%"]["p_halve"] == 0.0     # 0.95^14 = 0.49
    mix = C.simulate([{"day": DAYS[0], "r": 3.0}, {"day": DAYS[0], "r": -3.0}], DAYS[:1], paths=20)  # one session nets 0
    assert all(v["median_end"] == 3000.0 for v in mix["fractions"].values())


def test_a_session_losing_everything_ruins_the_path():
    v = C.simulate([{"day": DAYS[0], "r": -25.0}], DAYS[:1], paths=10)
    assert v["fractions"]["5%"]["median_end"] == 0.0 and v["fractions"]["5%"]["p_ruin"] == 1.0
    assert v["fractions"]["5%"]["worst_dd_pct"] == -100.0 and v["fractions"]["1%"]["median_end"] == pytest.approx(2250.0)


def test_resampling_is_by_session_and_seeded():
    tr = _trades(seed=5)
    a, b = C.simulate(tr, DAYS), C.simulate(tr, DAYS)
    assert a == b                                                           # restart safety: identical numbers on a re-run
    c = C.simulate(tr, DAYS, seed=30)
    assert c["fractions"] != a["fractions"] and c["seed"] == 30
    days, rs, _n = C.session_r(tr, DAYS)
    rng = np.random.default_rng(C.SEED)
    idx = rng.integers(0, len(days), size=(C.PATHS, len(days)))
    end = 3000 * np.prod(np.maximum(1 + 0.02 * rs[idx], 0.0), axis=1)
    assert a["fractions"]["2%"]["median_end"] == pytest.approx(round(float(np.median(end)), 2))
    assert a["fractions"]["2%"]["p5_end"] == pytest.approx(round(float(np.percentile(end, 5)), 2))


def test_refusals():
    with pytest.raises(ValueError):
        C.simulate([{"day": DAYS[0], "pnl": 10.0, "risk": 0.0}], DAYS)
    with pytest.raises(ValueError):
        C.simulate([{"day": DAYS[0], "pnl": 10.0}], DAYS)                     # no risk and no r
    with pytest.raises(ValueError):
        C.simulate([{"day": "2025-06-02", "r": 1.0}], DAYS)                   # a day outside the sessions given
    with pytest.raises(ValueError):
        C.simulate([], [])
    with pytest.raises(ValueError):
        C.session_r([], DAYS[:2] + DAYS[:1])                                 # a repeated session
    for d in ("2024-03-01", "2026-08-03"):                                    # L2, L1
        with pytest.raises(periods.LockedPeriod):
            C.simulate([{"day": d, "r": 1.0}])
    with pytest.raises(periods.LockedPeriod):
        C.simulate([], ["2024-07-01", "2024-08-01"])


def test_render_md_lists_every_fraction():
    md = "\n".join(C.render_md(C.simulate(_trades(), DAYS, paths=100), "x"))
    assert "| 1% |" in md and "| 2% |" in md and "| 5% |" in md and "chance of halving" in md
    assert C.render_md(None) == [] and math.isclose(C.simulate(_trades(), DAYS, paths=100)["input"]["years"], round(len(DAYS) / 252, 2))
