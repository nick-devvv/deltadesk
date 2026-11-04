"""Round 15 (SPRINT_PLAN "Round 15 pre-registration"): G1 sector trend-momentum picks, G2 Donchian states and fixed slots,
G3 alpha picks, the P1/P2 portfolios, no look-ahead, the L1 guard (refused without a frozen spec) and the L1 scoring, and
an end-to-end run. Synthetic data only."""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sprint_r15 as T15  # noqa: E402
import test_sprint_r14 as F14  # noqa: E402
from sprint import periods  # noqa: E402
from sprint import r12daily as R12  # noqa: E402
from sprint import r14 as R14  # noqa: E402
from sprint import r15 as R  # noqa: E402


@pytest.fixture(scope="module")
def mk():
    return F14.market(3, a="2004-01-02", b="2012-12-31")[0]


def test_g1_picks_top3_above_sma(mk):
    rows, vecs = R.g1_decisions(mk)
    assert np.allclose(vecs.sum(axis=1), np.count_nonzero(vecs, axis=1) / 3)
    assert (np.count_nonzero(vecs, axis=1) <= 3).all()
    j = len(rows) - 1
    d = rows[j]
    for i in np.flatnonzero(vecs[j]):
        s = R12.SECTORS[i]
        assert mk.c[s][d] > R12.sma(mk.c[s], R14.SMA_N)[d]


def test_g2_channel_on_off():
    days = F14.calendar("2010-01-04", "2011-12-30")
    n = len(days)
    c = np.r_[np.full(60, 100.0), np.linspace(100, 130, 40), np.linspace(130, 90, 60), np.full(n - 160, 90.0)]
    frames = {s: F14.bars_from_close(days, c, i) for i, s in enumerate(R14.SYMBOLS)}
    m = R12.Market(frames, pd.Series(1.0, index=days))
    st = R.g2_states(m)
    i = R14.MA_ASSETS.index("SPY")
    assert not st[:50, i].any()    # no channel before 50 prior closes
    assert st[70, i]               # rising: above the 50-session high
    assert not st[150, i]          # falling below the 25-session low turns it off


def test_g2_slot_fixed_at_entry(mk):
    st = R.g2_states(mk)
    _, V = R.g2_vecs(mk, st)
    i = R14.MA_ASSETS.index("SPY")
    runs = np.flatnonzero(np.diff(st[:, i].astype(int)) == 1) + 1
    t = runs[0]
    k = t
    while k < mk.n and st[k, i]:
        assert V[k, i] == V[t, i]
        k += 1
    assert (V[~st] == 0).all()


def test_g3_positive_alpha_only():
    days = F14.calendar("2010-01-04", "2012-12-31")
    _, frames = F14.synth_frames(5, a="2010-01-04", b="2012-12-31", drifts={s: -0.002 for s in R12.SECTORS})
    m = R12.Market(frames, pd.Series(1.0, index=days))
    _, vecs = R.g3_decisions(m)
    assert vecs.sum() == 0        # every sector bleeds: no positive alpha


def test_no_lookahead(mk):
    r1 = {n: R.g_trial(mk, n)[0] for n in ("G1", "G2", "G3")}
    _, frames = F14.synth_frames(3, a="2004-01-02", b="2012-12-31")
    cut = 1500
    for s in frames:
        f = frames[s].copy()
        f.iloc[cut:, :] = f.iloc[cut:, :].to_numpy() * 1.7
        frames[s] = f
    m2 = R12.Market(frames, pd.Series(1.5, index=frames["SPY"].index))
    for n in ("G1", "G2", "G3"):
        r2 = R.g_trial(m2, n)[0]
        assert np.allclose(r1[n][:cut], r2[:cut]), n


def test_p1_is_mean_and_p2_bounded(mk):
    cand = R.pool(mk)
    p1 = R.p_series(mk, cand)
    assert np.allclose(p1, (cand["T6"]["r"] + cand["A2"]["r"] + cand["RSI2"]["r"]) / 3)
    p2 = R.p_series(mk, cand, risk=True)
    assert np.isfinite(p2).all() and np.std(p2) <= np.std(p1) + 1e-9


def test_evaluate_runs_small():
    m = F14.market(2)[0]
    ev, series = R.evaluate(m, n_luck=5, boot_draws=50)
    assert set(ev["trials"]) == set(R.TRIALS)
    assert ev["trials"]["P1"]["luck"]["3"]["n"] == 20
    assert "# Round 15 results" in R.report_md(ev)


def test_confirm_refused_without_frozen(tmp_path):
    with pytest.raises(periods.LockedPeriod):
        T15.confirm(tmp_path, tmp_path, None, None)
    with pytest.raises(periods.LockedPeriod):
        T15.confirm(tmp_path, tmp_path, "L1", "0" * 64)


def test_confirm_scores_l1_only():
    days = pd.bdate_range("2024-08-01", "2026-10-30")
    rng = np.random.default_rng(9)
    frames = {s: F14.bars_from_close(days, 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(days)))), i)
              for i, s in enumerate(R14.SYMBOLS)}
    m = R12.Market(frames, pd.Series(1.0, index=days))
    c = R.confirm(m, periods.LOCKED["L1"])
    n_l1 = int(((days >= "2026-07-01") & (days <= "2026-10-30")).sum())
    assert all(r["sessions"] == n_l1 for r in c["rules"].values())
    assert {r.get("verdict") for k, r in c["rules"].items() if k != "SPY"} <= {"OK", "BROKE"}
    assert "L1 confirmation" in R.confirm_md(c)
