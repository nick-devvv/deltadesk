"""Round 13 (SPRINT_PLAN "Round 13 pre-registration"): T6's rule on Ken French's daily industry returns, sprint/r13ff.py
and tools/sprint_r13.py. The French file format (only the value-weighted table is read; -99.99 is missing), rows after
2024-01-31 dropped while parsing and never saved, month-end decisions with 12-month momentum and a 10-month trend
filter, the one-session execution delay, costs, no look-ahead, the paired Sharpe test, the hindsight drawdown sizing, the
link lookup when the known file name fails, hand-downloaded zips, the locked-period refusal and an end-to-end run with the
zips. Synthetic data only."""
import gzip
import io
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

import sprint_r13 as T13  # noqa: E402
from sprint import periods  # noqa: E402
from sprint import r13ff as R  # noqa: E402

COLS = list(R.INDUSTRIES)


def synth(a="1926-07-01", b="2026-09-30", seed=1, drifts=None):
    days = pd.bdate_range(a, b)
    rng = np.random.default_rng(seed)
    n = len(days)
    drifts = np.linspace(0.0001, 0.0005, 10) if drifts is None else np.asarray(drifts)
    common = rng.normal(0, 0.008, n)
    ind = common[:, None] + rng.normal(0, 0.006, (n, 10)) + drifts[None, :]
    mkt = ind.mean(axis=1)
    rf = np.full(n, 0.0001)
    return days, ind, mkt, rf


def frames(days, ind, mkt, rf):
    i = pd.DataFrame(ind, index=days, columns=COLS)
    f = pd.DataFrame({"Mkt-RF": mkt - rf, "SMB": 0.0, "HML": 0.0, "RF": rf}, index=days)
    return i, f


def ind_text(days, ind):
    head = ",NoDur,Durbl,Manuf,Enrgy,HiTec,Telcm,Shops,Hlth ,Utils,Other"
    L = ["  This file was created by CMPT_IND_RETS using the 202609 CRSP database.",
         "  Missing data are indicated by -99.99 or -999.", "", "  Average Value Weighted Returns -- Daily", head]
    L += [f"{d:%Y%m%d}," + ",".join(f"{x * 100:8.4f}" for x in row) for d, row in zip(days, ind)]
    L += ["", "  Average Equal Weighted Returns -- Daily", head]
    L += [f"{d:%Y%m%d}," + ",".join(f"{x * 100 + 5:8.4f}" for x in row) for d, row in zip(days, ind)]
    return "\n".join(L) + "\n"


def fac_text(days, mkt, rf):
    L = ["This file was created by CMPT_ME_BEME_RETS_DAILY using the 202609 CRSP database.",
         "The 1-month TBill return is from Ibbotson and Associates Inc.", "", ",Mkt-RF,SMB,HML,RF"]
    L += [f"{d:%Y%m%d},{(m - r) * 100:9.4f},   0.00,   0.00,{r * 100:9.4f}" for d, m, r in zip(days, mkt, rf)]
    L += ["", "Copyright 2026 Kenneth R. French"]
    return "\n".join(L) + "\n"


def zipped(name, text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, text)
    return buf.getvalue()


def fake_site(seed=3, first_name_ok=False):
    days, ind, mkt, rf = synth(seed=seed)
    blobs = {"10_Industry_Portfolios_Daily_CSV.zip": zipped("10_Industry_Portfolios_Daily.csv", ind_text(days, ind)),
             "F-F_Research_Data_Factors_daily_CSV.zip": zipped("F-F_Research_Data_Factors_daily.CSV", fac_text(days, mkt, rf))}
    calls = []

    def get(url):
        calls.append(url)
        if url.endswith("data_library.html"):
            return b'<a href="ftp/10_Industry_Portfolios_Daily_CSV.zip">CSV</a> <a href="ftp/F-F_Research_Data_Factors_daily_CSV.zip">CSV</a>'
        name = url.rsplit("/", 1)[-1]
        if not first_name_ok and len([c for c in calls if c == url]) == 1:
            return b"<html>moved</html>"            # the first try at the known name fails: the page lookup must find it
        return blobs[name]

    return get, calls, (days, ind, mkt, rf), blobs


# ------------------------------------------------------------------ parsing and the cutoff
def test_parse_reads_only_the_value_weighted_table_and_marks_missing():
    days = pd.bdate_range("1926-07-01", periods=5)
    ind = np.full((5, 10), 0.01)
    txt = ind_text(days, ind).replace("  1.0000", "-99.9900", 1)
    df = T13.parse_french(txt)
    assert list(df.columns) == COLS, "header names are stripped ('Hlth ' -> 'Hlth')"
    assert len(df) == 5 and np.isnan(df.iloc[0, 0]) and df.iloc[1, 0] == pytest.approx(0.01)
    f = T13.parse_french(fac_text(days, np.full(5, 0.002), np.full(5, 0.0001)))
    assert list(f.columns) == ["Mkt-RF", "SMB", "HML", "RF"] and f["RF"].iloc[0] == pytest.approx(0.0001)


def test_rows_after_the_cutoff_are_dropped():
    days, ind, _, _ = synth(a="2023-06-01", b="2026-09-30")
    df, dropped = T13.clean(T13.parse_french(ind_text(days, ind)))
    assert df.index[-1].date() <= R.LAST_DAY and dropped > 0
    assert not periods.overlaps(df.index[0].date(), df.index[-1].date())


# ------------------------------------------------------------------ rules
def test_decisions_use_12_months_of_momentum_and_a_10_month_trend():
    days, ind, mkt, rf = synth(a="1990-01-01", b="1995-12-31", seed=5)
    d = R.Data(*frames(days, ind, mkt, rf))
    me = R.month_end_rows(d)
    assert all(d.index[r].month != d.index[r + 1].month for r in me)
    dec = R.decisions(d)
    tri, trm = np.cumprod(1 + d.ind, axis=0), np.cumprod(1 + d.mkt)
    k = 30
    row, mom, trend = dec[k]
    assert np.allclose(mom, tri[me[k]] / tri[me[k - 12]] - 1)
    assert trend == bool(trm[me[k]] > trm[me[k - 9:k + 1]].mean())
    assert dec[11][1] is None and dec[8][2] is None, "no decision before 12 months of history"


def test_weights_top3_or_cash_and_the_two_diagnostics():
    days = pd.bdate_range("1990-01-01", "1996-12-31")
    n = len(days)
    ind = np.tile(np.linspace(0.0001, 0.001, 10), (n, 1))        # Other > Utils > Hlth: the top 3 never change
    half = n // 2
    mkt = np.r_[np.full(half, 0.0005), np.full(n - half, -0.0015)]
    d = R.Data(*frames(days, ind, mkt, np.full(n, 0.0001)))
    me = R.month_end_rows(d)
    up = [r for r in me if 300 < r < half - 5]
    down = [r for r in me if r > half + 260]
    W, W1, W2 = R.weights(d, "R13"), R.weights(d, "D1_momentum_only"), R.weights(d, "D2_trend_only")
    for r in up:
        assert np.allclose(W[r], [0] * 7 + [1 / 3] * 3) and np.allclose(W2[r], 0.1)
    for r in down:
        assert W[r].sum() == 0 and W2[r].sum() == 0
        assert np.allclose(W1[r], [0] * 7 + [1 / 3] * 3), "momentum only stays invested"


def test_one_session_delay_and_costs():
    n = 12
    days = pd.bdate_range("1990-01-01", periods=n)
    d = R.Data(*frames(days, np.zeros((n, 10)), np.zeros(n), np.zeros(n)))
    W = np.zeros((n, 10))
    W[5:, :3] = 1 / 3                     # decided at the close of row 5
    d.ind[6, :3] = 0.5                    # a jump on row 6 must NOT be earned (the trade is at row 6's close)
    d.ind[7, :3] = 0.1                    # row 7 is the first one earned
    r, H = R.simulate(d, W, 0.001)
    assert H[6].sum() == 0 and np.allclose(H[7, :3], 1 / 3)
    assert r[6] == pytest.approx(-0.001), "the trade day pays 10 bps on a traded weight of 1"
    assert r[7] == pytest.approx(0.1)


@pytest.mark.parametrize("name", R.TRIALS)
def test_no_lookahead(name):
    days, ind, mkt, rf = synth(a="1980-01-01", b="1990-12-31", seed=9)
    d = R.Data(*frames(days, ind, mkt, rf))
    k = 1500
    base = R.simulate(d, R.weights(d, name), 0.001)[0]
    ind2, mkt2 = ind.copy(), mkt.copy()
    rng = np.random.default_rng(2)
    ind2[k + 1:] += rng.normal(0, 0.02, ind2[k + 1:].shape)
    mkt2[k + 1:] = ind2[k + 1:].mean(axis=1)
    d2 = R.Data(*frames(days, ind2, mkt2, rf))
    after = R.simulate(d2, R.weights(d2, name), 0.001)[0]
    assert np.allclose(base[:k + 1], after[:k + 1])
    assert not np.allclose(base, after)


def test_sharpe_difference_test():
    rng = np.random.default_rng(0)
    b = rng.normal(0.0002, 0.01, 5000)
    better = b * 0.5 + 0.0004 + rng.normal(0, 0.002, 5000)
    p, diff, ci = R.sharpe_diff_test(better, b, draws=1000)
    assert p < 0.01 and diff > 0 and ci[0] > 0
    p_same, diff_same, _ = R.sharpe_diff_test(b, b, draws=500)
    assert diff_same == 0 and p_same > 0.4


def test_sized_to_the_same_drawdown():
    days, ind, mkt, rf = synth(a="1960-01-01", b="1975-12-31", seed=4)
    d = R.Data(*frames(days, ind, mkt, rf))
    mk = R.mask_for(d, date(1961, 1, 1), date(1975, 12, 31))
    z = R.sized_to_dd(d, d.mkt, np.ones(d.n), mk)
    assert z["max_dd"] == pytest.approx(-0.20, abs=1e-6) and z["k"] > 0


def test_luck_checks_find_a_planted_momentum_edge():
    days, ind, mkt, rf = synth(a="1926-07-01", b="1998-06-30", seed=6, drifts=np.linspace(-0.0004, 0.0008, 10))
    d = R.Data(*frames(days, ind, mkt, rf))
    lk = R.luck_checks(d, n=60)
    assert lk["random_picks"]["share_below"] > 0.95, "the top 3 by momentum beat random picks when momentum persists"
    assert lk["noise"]["share_above_market"] >= 0.95
    assert 0.0 < lk["outliers"]["kept_without_best_10_months"] < 1.0 and 840 <= lk["outliers"]["months"] <= 850


def test_luck_check_delays_move_each_rebalance():
    days, ind, mkt, rf = synth(a="1980-01-01", b="1985-12-31", seed=8)
    d = R.Data(*frames(days, ind, mkt, rf))
    dec = R.decisions(d)
    W0 = R.weights(d, "D1_momentum_only", dec)
    W3 = R.weights(d, "D1_momentum_only", dec, delays=np.full(len(dec), 3))
    first = int(np.flatnonzero(W0.sum(axis=1) > 0)[0])
    assert W3[first].sum() == 0 and np.allclose(W3[first + 3], W0[first])


# ------------------------------------------------------------------ the Chart tool
def test_fetch_finds_the_files_and_keeps_nothing_after_the_cutoff(tmp_path):
    get, calls, _, _ = fake_site()
    st = T13.fetch(tmp_path / "r13", get=get, log=lambda *a: None)
    assert any(c.endswith("data_library.html") for c in calls), "the page lookup ran after the known name failed"
    for kind in ("industries", "factors"):
        df = T13._read(tmp_path / "r13" / f"{kind}.csv.gz")
        assert df.index[-1].date() <= R.LAST_DAY and st[kind]["rows_after_2024_01_31_dropped"] > 0
    assert not list((tmp_path / "r13").glob("*.zip")), "the raw download is never saved"


def test_hand_downloaded_zips_with_browser_names(tmp_path):
    _, _, _, blobs = fake_site()
    man = tmp_path / "manual"
    man.mkdir()
    (man / "10_Industry_Portfolios_Daily_CSV (1).zip").write_bytes(blobs["10_Industry_Portfolios_Daily_CSV.zip"])
    (man / "F-F_Research_Data_Factors_daily_CSV.zip").write_bytes(blobs["F-F_Research_Data_Factors_daily_CSV.zip"])
    st = T13.fetch(tmp_path / "r13", from_dir=man, log=lambda *a: None)
    assert st["industries"]["source"].endswith("(1).zip")
    with pytest.raises(T13.Unusable):
        T13.fetch(tmp_path / "x", from_dir=tmp_path / "empty_dir_that_does_not_exist", log=lambda *a: None)


def test_check_refuses_locked_dates(tmp_path):
    get, _, _, _ = fake_site()
    T13.fetch(tmp_path / "r13", get=get, log=lambda *a: None)
    p = tmp_path / "r13" / "factors.csv.gz"
    f = T13._read(p)
    extra = f.iloc[-5:].copy()
    extra.index = pd.bdate_range("2024-03-01", periods=5)
    T13._write(p, pd.concat([f, extra]))
    with pytest.raises(periods.LockedPeriod):
        T13.check(tmp_path / "r13", log=lambda *a: None)


def test_end_to_end_run_and_zips(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "BOOT_DRAWS", 300)
    monkeypatch.setattr(R, "ROB_N", 40)
    get, _, _, _ = fake_site(seed=11)
    data, out = tmp_path / "data" / "r13", tmp_path / "data" / "sprint"
    T13.fetch(data, get=get, log=lambda *a: None)
    lines = []
    ev, stamp = T13.run(data, out, log=lines.append, today=date(2026, 11, 4))
    assert set(ev["verdict"]["items"]) == {"1 Sharpe above the market's, p < 0.01", "2 drawdown smaller than the market's",
                                           "3 Sharpe above the market's in 2 of 3 eras", "4 Sharpe over cash > 0 at 50 bps",
                                           "5 beats 95% of random industry picks", "6 beats 95% of shifted trend filters",
                                           "7 above the market's Sharpe in 95% of noisy runs", "8 keeps 50% without its 10 best months"}
    assert ev["luck"]["draws"] == 40
    assert ev["n_trials_total"] == 11_300 and ev["data"]["last"] <= "2024-01-31"
    md = (out / "round13_2026-11-04.md").read_text()
    assert "Round 13 result" in md and "Sized to the same worst drop" in md and "BACKTEST" in md and "## Luck checks" in md
    with gzip.open(out / "round13_daily_2026-11-04.csv.gz", "rt") as fh:
        daily = pd.read_csv(fh)
    assert {"R13", "D1_momentum_only", "D2_trend_only", "market", "rf"} <= set(daily.columns)
    assert lines[0].startswith("round13 R13: ") and sum(1 for x in lines if x.startswith("round13 ")) == 5
    zr, zd = T13.make_zips(data, out, tmp_path, stamp, log=lambda *a: None)
    with zipfile.ZipFile(zr) as z:
        assert "data/sprint/round13_2026-11-04.md" in z.namelist() and "MANIFEST_sha256.json" in z.namelist()
    with zipfile.ZipFile(zd) as z:
        assert "data/r13/industries.csv.gz" in z.namelist()
    json.loads((out / "round13_2026-11-04.json").read_text())


def test_refuses_to_run_inside_desk(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "desk" / "x").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(home / "desk" / "x")
    with pytest.raises(T13.Unusable):
        T13.refuse_desk()
