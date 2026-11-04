"""Round 14 (SPRINT_PLAN "Round 14 pre-registration"): sprint/r14.py and tools/sprint_r14.py. Multi-asset trend weights (A1-A3),
bond trend (E1/E2), IBS trades (C1-C3) and the series built from them, the one-session allocation delay and costs, the
learner's past-only rankings, its risk control (volatility target and drawdown brake), low-volatility industry picks
(B1/B2), no look-ahead, and an end-to-end run with the zips. Synthetic data only."""
import gzip
import json
import sys
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sprint_r14 as T14  # noqa: E402
import sprint_r12 as T12  # noqa: E402
import test_sprint_r13 as F13  # noqa: E402
from sprint import periods  # noqa: E402
from sprint import r12daily as R12  # noqa: E402
from sprint import r13ff as R13  # noqa: E402
from sprint import r14 as R  # noqa: E402


def bars_from_close(days, c, seed=0, spread=0.004):
    rng = np.random.default_rng(seed)
    c = np.asarray(c, float)
    o = np.r_[c[0], c[:-1]] * np.exp(rng.normal(0, spread / 2, len(c)))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, spread, len(c))))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, spread, len(c))))
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "adj_close": c}, index=pd.DatetimeIndex(days))


def calendar(a="1998-01-02", b="2026-06-30"):
    d = pd.bdate_range(a, b)
    for x, y in periods.LOCKED.values():
        d = d[(d < pd.Timestamp(x)) | (d > pd.Timestamp(y))]
    return d


def synth_frames(seed=1, a="1998-01-02", b="2026-06-30", drifts=None, vols=None):
    days = calendar(a, b)
    rng = np.random.default_rng(seed)
    frames = {}
    for i, s in enumerate(R.SYMBOLS):
        mu = (drifts or {}).get(s, 0.0002 + 0.00003 * (i % 7))
        sd = (vols or {}).get(s, 0.004 if s == "SHY" else 0.011)
        frames[s] = bars_from_close(days, 100 * np.exp(np.cumsum(rng.normal(mu, sd, len(days)))), seed + i)
    return days, frames


def market(seed=1, **kw):
    days, frames = synth_frames(seed, **kw)
    return R12.Market(frames, pd.Series(1.5, index=days)), frames


def tiny(o, h, lo, c, start="2010-01-04", sym="SPY"):
    days = pd.bdate_range(start, periods=len(c))
    f = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "adj_close": c}, index=days, dtype=float)
    frames = {"SPY": f} if sym == "SPY" else {"SPY": f.copy(), sym: f}
    return R12.Market(frames, pd.Series(0.0, index=days))


# ------------------------------------------------------------------ allocation engine and rules
def test_allocation_delay_and_costs():
    m = tiny(*(np.full(12, 100.0),) * 4)
    rows = np.array([5])
    W = R.W_from(m.n, rows, np.array([[1.0]]))
    R_ = np.zeros((m.n, 1))
    R_[6, 0], R_[7, 0] = 0.5, 0.1          # decided at row 5's close: row 6 is NOT earned, row 7 is
    r, H, tr = R.run_alloc(m, W, R_, cost=0.001)
    assert H[6, 0] == 0 and H[7, 0] == 1
    assert r[6] == pytest.approx(-0.001) and r[7] == pytest.approx(0.1)


def test_multi_asset_trend_weights():
    up = {s: 0.0006 for s in ("SPY", "EFA", "TLT", "GLD")}
    down = {s: -0.0006 for s in ("EEM", "IEF", "DBC", "VNQ")}
    vols = {"SPY": 0.012, "EFA": 0.012, "TLT": 0.006, "GLD": 0.006}
    m, _ = market(seed=3, a="1998-01-02", b="2006-12-29", drifts={**up, **down}, vols=vols)
    inp = R.ma_inputs(m)
    rows, v1 = R.ma_decisions(m, "A1", inp)
    _, v2 = R.ma_decisions(m, "A2", inp)
    _, v3 = R.ma_decisions(m, "A3", inp)
    checked = 0
    for j in range(len(rows) - 24, len(rows)):
        d = rows[j]
        mom = np.array([inp[s]["mom"][d] for s in R.MA_ASSETS])
        sma = np.array([inp[s]["sma"][d] for s in R.MA_ASSETS])
        c = np.array([inp[s]["c"][d] for s in R.MA_ASSETS])
        vol = np.array([inp[s]["vol"][d] for s in R.MA_ASSETS])
        on = (mom > 0) & (c > sma)
        assert np.allclose(v1[j], np.where(on, 1 / 8, 0)), "A1: 1/8 per on asset"
        b = (1 / vol) / (1 / vol).sum()
        assert np.allclose(v2[j], np.where(on, b, 0)), "A2: risk-parity slots, off slots in cash"
        if on.any():
            sc = np.where(on, mom / vol, 0)
            assert np.allclose(v3[j], np.minimum(R.A3_CAP, sc / sc.sum())), "A3: return/vol, capped at 0.5"
        checked += int(on.any()) + int((~on).any())
    assert checked > 24, "the scenario has both on and off assets"
    assert v1[-24:, [R.MA_ASSETS.index(s) for s in down]].sum() < v1[-24:, [R.MA_ASSETS.index(s) for s in up]].sum()


def test_bond_trend_rules():
    m, _ = market(seed=4, a="2000-01-03", b="2006-12-29", drifts={"TLT": 0.0008, "IEF": -0.0004})
    rows, v = R.e_decisions(m, "E1")
    assert v[-2][0] == 1 and v[-2][1] == 0, "TLT above its 200-day average"
    rows, v = R.e_decisions(m, "E2")
    assert v[-2].sum() == 0, "IEF losing to T-bills: cash"


# ------------------------------------------------------------------ IBS
def test_ibs_trade_rules():
    n = 14
    c = np.full(n, 100.0)
    o, h, lo = c.copy(), c + 1, c - 1               # IBS 0.5 every day
    lo[2], c[2] = 99.0, 99.1                         # day 2 closes near its low: IBS 0.05
    h[5], c[5] = 101.0, 100.9                        # day 5 closes near its high: IBS 0.95
    m = tiny(o, h, lo, c)
    assert R.ibs_trades(m, "SPY", "C1") == [(3, 3, "close")]
    assert R.ibs_trades(m, "SPY", "C2") == [(3, 6, "open")], "out at the open after the strong close"
    h2, c2 = h.copy(), c.copy()
    h2[5], c2[5] = 101.0, 100.0                      # no strong close: out after 5 sessions held (days 3-7) at the open of 8
    m = tiny(o, h2, lo, c2)
    assert R.ibs_trades(m, "SPY", "C2") == [(3, 8, "open")]
    assert R.ibs_trades(m, "SPY", "C3") == [], "no 200-day average yet: C3 never enters"


def test_series_from_trades_matches_the_fills():
    days = pd.bdate_range("2010-01-04", periods=6)
    o = np.array([100, 101, 102, 103, 104, 105.0])
    c = np.array([100.5, 101.5, 102.5, 103.5, 104.5, 105.5])
    m = R12.Market({"SPY": pd.DataFrame({"open": o, "high": c + 1, "low": o - 1, "close": c, "adj_close": c}, index=days)},
                   pd.Series(0.0, index=days))
    r, ex, tr = R.series_from_trades(m, {"SPY": [(1, 4, "open")]}, 1.0, 0.001)
    assert r[1] == pytest.approx(101.5 / 101 - 1 - 0.001)
    assert r[2] == pytest.approx(102.5 / 101.5 - 1) and r[3] == pytest.approx(103.5 / 102.5 - 1)
    assert r[4] == pytest.approx(104 / 103.5 - 1 - 0.001)
    assert np.prod(1 + r[1:5]) == pytest.approx((104 / 101) * (1 - 0.001) ** 2, rel=1e-3)
    assert list(ex) == [0, 1, 1, 1, 0, 0]


# ------------------------------------------------------------------ the learner
def fake_cand(m, drifts, seed=0):
    rng = np.random.default_rng(seed)
    out = {}
    for k in R.CANDIDATES:
        r = m.cash + rng.normal(drifts.get(k, 0.0), 0.006, m.n)
        out[k] = {"r": r, "expo": np.ones(m.n), "traded": np.zeros(m.n)}
    return out


def test_learner_picks_the_best_recent_candidates_and_waits_24_months():
    m, _ = market(seed=5, a="2000-01-03", b="2008-12-31")
    cand = fake_cand(m, {"E1": 0.001, "T6": 0.0008, "A1": -0.0005, "C2": -0.0005, "RSI2": 0.0})
    rows, vecs, _ = R.learner_decisions(m, cand)
    first_live = np.flatnonzero(vecs.sum(axis=1) > 0)[0]
    assert (R.ym(m)[rows[first_live]] - R.ym(m)[0]) >= 24
    late = vecs[-5:]
    assert np.allclose(late[:, R.CANDIDATES.index("E1")], 0.5) and np.allclose(late[:, R.CANDIDATES.index("T6")], 0.5)


def test_learner_uses_past_data_only():
    m, _ = market(seed=6, a="2000-01-03", b="2010-12-31")
    cand = fake_cand(m, {"E1": 0.0004})
    rows, v0, _ = R.learner_decisions(m, cand)
    k = len(rows) // 2
    cut = rows[k]
    cand2 = {kk: dict(vv) for kk, vv in cand.items()}
    for kk in cand2:
        r = cand2[kk]["r"].copy()
        r[cut + 1:] = np.random.default_rng(9).normal(0.003 if kk == "C2" else -0.003, 0.006, m.n - cut - 1)
        cand2[kk]["r"] = r
    _, v1, _ = R.learner_decisions(m, cand2)
    assert np.allclose(v0[:k + 1], v1[:k + 1]), "decisions up to the cut see only data up to the cut"
    assert not np.allclose(v0, v1)


def test_risk_control_vol_target_and_drawdown_brake():
    days = pd.bdate_range("2010-01-04", periods=400)
    m = R12.Market({"SPY": bars_from_close(days, np.full(400, 100.0))}, pd.Series(0.0, index=days))
    r = np.full(400, 0.0001)
    r[100:110] = -0.02                      # a 18% fall
    out = R.risk_control(m, r, cost=0.0)
    x = np.divide(out, r, out=np.full(400, np.nan), where=r != 0)
    assert x[50] == pytest.approx(1.0), "calm: full exposure"
    assert x[115] < 0.5 + 1e-9, "after a >10% drawdown the exposure is halved (and the vol target cuts it too)"
    assert np.nanmax(x[300:]) <= 1.0 + 1e-9


# ------------------------------------------------------------------ B: low-volatility industries
def test_low_vol_picks_the_three_calmest():
    days = pd.bdate_range("1960-01-01", "1964-12-31")
    rng = np.random.default_rng(2)
    sd = np.linspace(0.004, 0.02, 10)
    ind = rng.normal(0.0003, 1, (len(days), 10)) * sd
    d = R13.Data(*F13.frames(days, ind, ind.mean(axis=1), np.full(len(days), 0.0001)))
    dec = R13.decisions(d)
    vols = R.fr_vols(d, dec)
    W = R.fr_weights(d, "B1", dec, vols)
    row = dec[-2][0]
    assert np.allclose(W[row, :3], 1 / 3) and W[row, 3:].sum() == 0


# ------------------------------------------------------------------ no look-ahead
@pytest.mark.parametrize("name", ["A1", "A3", "E1", "C2", "T6"])
def test_no_lookahead(name):
    days, frames = synth_frames(seed=8, a="2000-01-03", b="2009-12-31")
    k = 1500

    def series(fr):
        m = R12.Market(fr, pd.Series(1.0, index=days))
        if name == "T6":
            rows, vecs = R.t6_decisions(m)
            return R.run_alloc(m, R.W_from(m.n, rows, vecs), R.t6_returns(m))[0]
        if name[0] == "C":
            return R.run_ibs(m, name)[0]
        rows, vecs = R.ma_decisions(m, name) if name[0] == "A" else R.e_decisions(m, name)
        Rr = R.ma_returns(m) if name[0] == "A" else R.e_returns(m)
        return R.run_alloc(m, R.W_from(m.n, rows, vecs), Rr)[0]

    base = series(frames)
    rng = np.random.default_rng(1)
    changed = {}
    for s, f in frames.items():
        g = f.copy()
        mult = np.ones(len(g))
        later = g.index > days[k]
        mult[later] = np.exp(np.cumsum(rng.normal(0, 0.03, later.sum())))
        for col in ("open", "high", "low", "close", "adj_close"):
            g[col] = g[col] * mult
        changed[s] = g
    after = series(changed)
    assert np.allclose(base[:k + 1], after[:k + 1])
    assert not np.allclose(base, after)


# ------------------------------------------------------------------ the tool, end to end
def fake_yahoo(seed=31):
    days = calendar("1998-01-02", "2026-06-30")
    full = calendar("1998-01-02", "2026-06-30").union(pd.bdate_range("2024-02-01", "2024-07-31"))
    rng = np.random.default_rng(seed)
    data = {}
    for i, s in enumerate(R.SYMBOLS):
        c = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.004 if s == "SHY" else 0.011, len(full))))
        data[s] = bars_from_close(full, c, seed + i)

    def history(sym, a, b):
        if sym == "^IRX":
            dd = full[(full >= pd.Timestamp(a)) & (full <= pd.Timestamp(b))]
            return pd.DataFrame({"close": 1.5}, index=dd)
        f = data[sym]
        f = f[(f.index >= pd.Timestamp(a)) & (f.index <= pd.Timestamp(b))]
        return T12.normalize_yahoo(f.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "adj_close": "Adj Close"}))

    return history


def test_end_to_end_run_and_zips(tmp_path):
    history = fake_yahoo()
    french_get, _, _, _ = F13.fake_site(seed=12, first_name_ok=True)

    def no_fred(url):
        raise ConnectionError("fred timed out")

    data, out = tmp_path / "data" / "r14", tmp_path / "data" / "sprint"
    T14.fetch(data, history=history, get=no_fred, french_get=french_get, log=lambda *a: None)
    spy = T12._read(data / "yahoo" / "SPY.csv.gz")
    for x, y in periods.LOCKED.values():
        assert not ((spy.index >= pd.Timestamp(x)) & (spy.index <= pd.Timestamp(y))).any(), "L1/L2 never requested"
    lines = []
    ev, stamp = T14.run(data, out, log=lines.append, today=date(2026, 11, 4), n_luck=15, boot_draws=200)
    assert set(ev["verdicts"]) == set(R.TRIALS) and ev["n_trials_total"] == 11_312
    assert sum(1 for x in lines if x.startswith("round14 ")) == 12
    md = (out / "round14_2026-11-04.md").read_text()
    for part in ("## Verdicts", "## Luck checks", "## The learner's candidates and controls", "BACKTEST"):
        assert part in md
    for n in R.ETF_TRIALS:
        assert len(ev["etf"][n]["items"]) == 5
    assert len(ev["french"]["B2"]["items"]) == 8 and len(ev["french"]["B1"]["items"]) == 7
    with gzip.open(out / "round14_daily_2026-11-04.csv.gz", "rt") as fh:
        assert set(R.ETF_TRIALS) <= set(pd.read_csv(fh).columns)
    zr, zd = T14.make_zips(data, out, tmp_path, stamp, log=lambda *a: None)
    with zipfile.ZipFile(zr) as z:
        assert "data/sprint/round14_2026-11-04.md" in z.namelist()
    with zipfile.ZipFile(zd) as z:
        assert "data/r14/yahoo/SPY.csv.gz" in z.namelist() and "data/r14/french/industries.csv.gz" in z.namelist()
    json.loads((out / "round14_2026-11-04.json").read_text())
