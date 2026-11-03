"""Round 12 (SPRINT_PLAN "Round 12 pre-registration"): the nine daily-bar trials in sprint/r12daily.py and the Chart tool
tools/sprint_r12.py. Rules and timing (next-open fills, stops on the low, gap fills at the open, stopped symbols wait for
a close above SMA(5)), costs, no look-ahead (changing later bars never changes earlier signals, weights or returns),
segments (no return across the L2 gap, indicators restart), the locked-period refusal (only SEGMENTS are ever requested),
a resumable fetch, the data check and its exclusion rule, and an end-to-end run with the zips. Synthetic data only."""
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

import sprint_r12 as T12  # noqa: E402
from sprint import ind5, periods  # noqa: E402
from sprint import r12daily as R  # noqa: E402

COST = 0.001


def bars(days, close, seed=0, spread=0.004, div_every=0, div=0.0):
    """OHLC around a close path; adj_close = close scaled down before each dividend (Yahoo style)."""
    rng = np.random.default_rng(seed)
    c = np.asarray(close, float)
    o = c * np.exp(rng.normal(0, spread / 2, len(c)))
    o[1:] = np.where(rng.random(len(c) - 1) < 0.5, c[:-1] * np.exp(rng.normal(0, spread, len(c) - 1)), o[1:])
    h = np.maximum(o, c) * (1 + abs(rng.normal(0, spread, len(c))))
    lo = np.minimum(o, c) * (1 - abs(rng.normal(0, spread, len(c))))
    divs = np.zeros(len(c))
    if div_every:
        divs[div_every::div_every] = div
    adj = T12.rebuild_adj_close(c, divs)
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "adj_close": adj}, index=pd.DatetimeIndex(days))


def walk(n, seed, drift=0.0003, vol=0.012, start=100.0):
    rng = np.random.default_rng(seed)
    return start * np.exp(np.cumsum(rng.normal(drift, vol, n)))


def calendar(a="1998-01-02", b="2026-06-30", cut_locked=True):
    d = pd.bdate_range(a, b)
    if cut_locked:
        for x, y in periods.LOCKED.values():
            d = d[(d < pd.Timestamp(x)) | (d > pd.Timestamp(y))]
    return d


def market_all(seed=1, a="1998-01-02", b="2026-06-30"):
    days = calendar(a, b)
    starts = {"GLD": "2004-11-18", "TLT": "2002-07-30", "EEM": "2003-04-14"}
    frames = {}
    for i, s in enumerate(R.SYMBOLS):
        f = bars(days, walk(len(days), seed + i, drift=0.0002 + 0.00005 * (i % 5)), seed + 100 + i, div_every=63, div=0.3)
        if s in starts:
            f = f[f.index >= starts[s]]
        frames[s] = f
    cash = pd.Series(2.0, index=days)
    return R.Market(frames, cash), frames, cash


def tiny_market(o, h, lo, c, start="2010-01-04"):
    days = pd.bdate_range(start, periods=len(c))
    f = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "adj_close": c}, index=days, dtype=float)
    return R.Market({"SPY": f}, pd.Series(0.0, index=days))


# ------------------------------------------------------------------ indicators and rules
def test_rsi_wilder_matches_desk_formula():
    x = walk(400, 3)
    assert np.allclose(R.rsi_wilder(x, 2), ind5.rsi_wilder(x, 2), equal_nan=True)


def test_rsi2_trades_follow_f1_timing():
    m, _, _ = market_all(seed=5, a="2003-01-02", b="2012-12-31")
    sig, ab = R.rsi2_signal(m, "SPY")
    r, ex, trades = R.sim_rsi2(m, "SPY", None, COST, sig, ab)
    assert len(trades) > 30
    for t in trades:
        e, x = t["entry_idx"], t["exit_idx"]
        assert sig[e - 1], "entry fills at the open after a signal close"
        assert t["entry_px"] == pytest.approx(m.o["SPY"][e])
        if t["exit"] == "signal":
            assert ab[x - 1] and not ab[e:x - 1].any(), "exit at the open after the FIRST close above SMA(5), from the entry day on"
            assert t["exit_px"] == pytest.approx(m.o["SPY"][x])
    assert set(np.unique(ex)) <= {0.0, 1.0}


def test_stop_gap_fills_at_open_and_touch_fills_at_stop():
    n = 10
    c = np.full(n, 100.0)
    o, h, lo = c.copy(), c * 1.001, c * 0.999
    sig = np.zeros(n, bool)
    ab = np.zeros(n, bool)
    sig[2] = True                       # entry at the open of day 3
    o2, lo2 = o.copy(), lo.copy()
    o2[4], lo2[4] = 94.0, 93.0          # gap through the 5% stop (95)
    m = tiny_market(o2, h, lo2, c)
    r, ex, t = R.sim_rsi2(m, "SPY", 0.05, COST, sig, ab)
    assert t[0]["exit"] == "stop" and t[0]["exit_px"] == pytest.approx(94.0) and t[0]["entry_idx"] == 3
    assert r[4] == pytest.approx((94 / 100 - 1) + (94 / 94 - 1) - COST)
    o3, lo3 = o.copy(), lo.copy()
    o3[4], lo3[4] = 99.0, 94.0          # touched intraday: fills at the stop
    m = tiny_market(o3, h, lo3, c)
    r, ex, t = R.sim_rsi2(m, "SPY", 0.05, COST, sig, ab)
    assert t[0]["exit_px"] == pytest.approx(95.0)
    assert r[4] == pytest.approx((99 / 100 - 1) + (95 / 99 - 1) - COST)


def test_stopped_symbol_waits_for_a_close_above_sma5():
    n = 12
    c = np.full(n, 100.0)
    o, h, lo = c.copy(), c * 1.001, c * 0.999
    lo[4] = 90.0
    sig = np.zeros(n, bool)
    ab = np.zeros(n, bool)
    sig[2] = sig[5] = sig[8] = True     # day 5's signal comes while stopped out: ignored
    ab[6] = True                        # a close above SMA(5) re-arms; day 8's signal enters at 9
    m = tiny_market(o, h, lo, c)
    _, ex, t = R.sim_rsi2(m, "SPY", 0.03, COST, sig, ab)
    assert [x["entry_idx"] for x in t] == [3, 9]
    assert ex[6] == 0 and ex[9] == 1


def test_round_trip_costs_and_segment_end():
    n = 8
    c = np.full(n, 100.0)
    sig = np.zeros(n, bool)
    ab = np.zeros(n, bool)
    sig[1], ab[3] = True, True          # in at the open of 2, out at the open of 4
    m = tiny_market(c, c, c, c)
    r, _, t = R.sim_rsi2(m, "SPY", None, COST, sig, ab)
    assert r.sum() == pytest.approx(-2 * COST)
    sig2 = np.zeros(n, bool)
    sig2[5] = True                      # still open at the last session: closed at that close, with costs
    r, ex, t = R.sim_rsi2(m, "SPY", None, COST, sig2, np.zeros(n, bool))
    assert t[-1]["exit"] == "segment end" and ex[-1] == 0 and r.sum() == pytest.approx(-2 * COST)


def test_twoma_exit_and_rearm():
    x = np.r_[np.linspace(100, 140, 40), [120.0], np.linspace(121, 131, 10), np.linspace(130, 90, 30), np.linspace(91, 160, 50)]
    m = tiny_market(x, x, x, x)
    w = R.twoma_weights(m)
    assert w[39] == 1 and w[40] == 0, "a close below 0.98 x the entry-signal close exits"
    assert not w[41:51].any(), "no re-entry while SMA(10) stays above SMA(30)"
    assert w[120:].any(), "re-armed after SMA(10) crossed below and back above"


def test_voltarget_band_and_cap():
    m, _, _ = market_all(seed=2, a="2004-01-02", b="2008-12-31")
    w = R.voltarget_weights(m)
    assert w.max() <= R.VT_CAP + 1e-12
    ch = np.flatnonzero(np.diff(w))
    assert len(ch) > 3
    assert np.all(np.abs(np.diff(w)[ch]) > R.VT_BAND - 1e-12)


def test_rotation_picks_top3_or_tlt():
    days = calendar("2003-01-02", "2007-12-31")
    n = len(days)
    frames = {}
    for i, s in enumerate(R.SECTORS):
        frames[s] = bars(days, 100 * np.exp(np.arange(n) * 0.0002 * (i + 1)), i)
    up = 100 * np.exp(np.arange(n) * 0.0005)
    down = up.copy()
    down[n // 2:] = up[n // 2] * np.exp(-np.arange(n - n // 2) * 0.002)
    frames["SPY"] = bars(days, down, 50)
    frames["TLT"] = bars(days, walk(n, 51), 51)
    m = R.Market(frames, pd.Series(1.0, index=days))
    w = R.rotation_weights(m)
    tot = sum(w.values())
    me = np.flatnonzero(R.month_end_mask(m))
    on = [d for d in me if 300 < d < n // 2 - 5]
    off = [d for d in me if d > n // 2 + 260]
    assert on and off
    top3 = ["XLF", "XLE", "XLV"]          # SECTORS[6:9] have the largest drifts
    for d in on:
        assert sorted(s for s in R.SECTORS if w[s][d] > 0) == sorted(top3)
        assert tot[d] == pytest.approx(1.0)
    for d in off:
        assert w["TLT"][d] == 1.0 and sum(w[s][d] for s in R.SECTORS) == 0


@pytest.mark.parametrize("fn", ["trend", "vol", "twoma", "rot", "rsi2"])
def test_no_lookahead(fn):
    m, frames, cash = market_all(seed=7, a="2002-01-02", b="2010-12-31")
    k = 1500

    def out(mm):
        if fn == "trend":
            return R.trend_weights(mm)
        if fn == "vol":
            return R.voltarget_weights(mm)
        if fn == "twoma":
            return R.twoma_weights(mm)
        if fn == "rot":
            return sum(R.rotation_weights(mm).values())
        return R.sim_rsi2(mm, "SPY", 0.05, COST)[0]

    base = out(m)
    rng = np.random.default_rng(3)
    changed = {}
    for s, f in frames.items():
        g = f.copy()
        mult = np.ones(len(g))
        later = g.index > m.index[k]
        mult[later] = np.exp(np.cumsum(rng.normal(0, 0.03, later.sum())))
        for col in ("open", "high", "low", "close", "adj_close"):
            g[col] = g[col] * mult
        changed[s] = g
    after = out(R.Market(changed, cash))
    assert np.allclose(base[: k + 1], after[: k + 1], equal_nan=True)
    assert not np.allclose(base, after, equal_nan=True) or fn == "rot"


def test_gap_segments_flatten_and_restart():
    m, _, _ = market_all(seed=9, a="2022-01-03", b="2025-06-30")
    segs = m.segments()
    assert len(segs) == 2, "the L2 gap splits the calendar"
    a2 = segs[1][0]
    assert m.days[a2 - 1] <= periods.HIST[1] and m.days[a2] >= periods.DEV[0]
    w = np.ones(m.n)
    r, ex = R.sim_weights(m, "SPY", w, COST)
    assert ex[a2 - 1] == 0, "flat at the last close before the gap"
    assert r[a2] == 0, "no return and no position on the first session after the gap"
    tw = R.trend_weights(m)
    assert not tw[a2:a2 + 199].any(), "SMA(200) restarts after the gap"


def test_mix_pays_rebalance_cost():
    m, _, _ = market_all(seed=4, a="2004-01-02", b="2007-12-31")
    res = R.run_trials(m, COST)
    a, b = res["T5_trend200"]["r"], res["T1_rsi2"]["r"]
    mix = 0.5 * a + 0.5 * b
    assert np.allclose(res["T9_mix"]["r"], mix - COST * 0.5 * np.abs(a - b) / (1 + mix))


def test_block_bootstrap_p_and_ci():
    rng = np.random.default_rng(0)
    p_pos, ci = R.block_bootstrap(rng.normal(0.002, 0.01, 2000), draws=2000)
    p_null, _ = R.block_bootstrap(rng.normal(0.0, 0.01, 2000), draws=2000)
    assert p_pos < 0.01 < p_null and ci[0] > 0


def test_evaluate_and_report(monkeypatch):
    monkeypatch.setattr(R, "BOOT_DRAWS", 500)
    m, _, _ = market_all(seed=11)
    res = {lvl: R.run_trials(m, c) for lvl, c in R.COSTS.items()}
    ev = R.evaluate(m, res)
    assert set(ev["verdicts"]) == set(R.TRIALS)
    for name in R.RSI2_TRIALS:
        assert "3 beats 95% of random entries" in ev["verdicts"][name]["items"]
        assert ev["trials"][name]["random_control"]["draws"] == R.CTRL_DRAWS
    assert ev["trials"]["T1_rsi2"]["2x"]["FRESH"]["trade_stats"]["trades"] > 0
    assert ev["n_trials_total"] == 11_293
    md = R.report_md(ev, "note")
    for name in R.TRIALS:
        assert name in md
    assert "BACKTEST" in md and "FRESH" in md
    again = R.evaluate(m, {lvl: R.run_trials(m, c) for lvl, c in R.COSTS.items()})
    assert json.dumps(T12._jsonable(again["verdicts"])) == json.dumps(T12._jsonable(ev["verdicts"])), "deterministic"


# ------------------------------------------------------------------ the Chart tool
def test_segments_never_touch_locked_periods():
    T12.check_segments()
    with pytest.raises(periods.LockedPeriod):
        T12.check_segments(((date(2023, 1, 1), date(2024, 3, 1)),))
    with pytest.raises(periods.LockedPeriod):
        T12.check_segments(((date(2026, 6, 1), date(2026, 8, 1)),))


def fake_sources(seed=21):
    days = calendar(cut_locked=False)
    full = {}
    for i, s in enumerate(R.SYMBOLS):
        full[s] = bars(days, walk(len(days), seed + i), seed + i, div_every=63, div=0.25)
    calls = []

    def history(sym, a, b):
        calls.append(("yahoo", sym, a, b))
        if sym == "^IRX":
            return pd.DataFrame({"close": 2.0}, index=days[(days >= pd.Timestamp(a)) & (days <= pd.Timestamp(b))])
        f = full[sym]
        f = f[(f.index >= pd.Timestamp(a)) & (f.index <= pd.Timestamp(b))]
        return T12.normalize_yahoo(f.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close",
                                                     "adj_close": "Adj Close"}))

    def get(url):
        calls.append(("url", url))
        if "stooq" in url:
            sym = url.split("s=")[1].split(".us")[0].upper()
            a = pd.Timestamp(url.split("d1=")[1][:8])
            b = pd.Timestamp(url.split("d2=")[1][:8])
            f = full[sym]
            f = f[(f.index >= a) & (f.index <= b)]
            return ("Date,Open,High,Low,Close,Volume\n" + "\n".join(
                f"{d.date()},{r.open},{r.high},{r.low},{r.close},1000" for d, r in f.iterrows())).encode()
        if "fred" in url:
            a = pd.Timestamp(url.split("cosd=")[1][:10])
            b = pd.Timestamp(url.split("coed=")[1][:10])
            dd = days[(days >= a) & (days <= b)]
            return ("observation_date,DTB3\n" + "\n".join(f"{d.date()},2.10" for d in dd)).encode()
        raise ConnectionError(url)

    return full, history, get, calls


def test_fetch_requests_only_segments_and_resumes(tmp_path):
    _, history, get, calls = fake_sources()
    st = T12.fetch(tmp_path / "r12", history=history, get=get, log=lambda *a: None)
    assert all(v == "fetched" for v in st["yahoo"].values())
    for c in calls:
        if c[0] == "yahoo":
            assert not periods.overlaps(c[2], c[3])
        else:
            u = c[1]
            a = u.split("d1=")[1][:8] if "d1=" in u else u.split("cosd=")[1][:10].replace("-", "")
            b = u.split("d2=")[1][:8] if "d2=" in u else u.split("coed=")[1][:10].replace("-", "")
            assert not periods.overlaps(date(int(a[:4]), int(a[4:6]), int(a[6:])), date(int(b[:4]), int(b[4:6]), int(b[6:])))
    spy = T12._read(tmp_path / "r12" / "yahoo" / "SPY.csv.gz")
    for x, y in periods.LOCKED.values():
        assert not ((spy.index >= pd.Timestamp(x)) & (spy.index <= pd.Timestamp(y))).any()
    n = len(calls)
    st2 = T12.fetch(tmp_path / "r12", history=history, get=get, log=lambda *a: None)
    assert all(v == "skipped" for v in st2["yahoo"].values()) and len(calls) == n, "a resumed fetch asks for nothing twice"


def test_stooq_unavailable_is_single_source(tmp_path):
    _, history, get, _ = fake_sources()

    def no_stooq(url):
        if "stooq" in url:
            return b"<html>Exceeded the daily hits limit</html>"
        return get(url)

    st = T12.fetch(tmp_path / "r12", history=history, get=no_stooq, log=lambda *a: None)
    assert all(str(v).startswith("unavailable") for v in st["stooq"].values())
    rep = T12.check(tmp_path / "r12", log=lambda *a: None)
    assert rep["cross_source"].startswith("UNAVAILABLE") and rep["excluded"] == []


def test_yahoo_errors_become_retryable_failures(tmp_path):
    _, history, get, _ = fake_sources()

    def flaky(sym, a, b):
        if sym == "QQQ":
            raise ValueError("Too Many Requests. Rate limited.")
        return history(sym, a, b)

    with pytest.raises(ConnectionError, match="yahoo QQQ"):
        T12.fetch(tmp_path / "r12", history=flaky, get=get, log=lambda *a: None)
    assert (tmp_path / "r12" / "yahoo" / "IWM.csv.done").exists(), "symbols before the failure are kept for the re-run"


def test_normalize_rebuilds_adj_close_and_parsers():
    idx = pd.bdate_range("2020-01-01", periods=5)
    df = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": [100, 100, 100, 100, 100.0],
                       "Dividends": [0, 0, 1.0, 0, 0]}, index=idx.tz_localize("America/New_York"))
    d = T12.normalize_yahoo(df)
    assert list(d["adj_close"]) == pytest.approx([99, 99, 100, 100, 100])
    assert d.index.tz is None
    for hdr in ("observation_date", "DATE"):
        s = T12.parse_fred(f"{hdr},DTB3\n2020-01-02,1.5\n2020-01-03,.\n".encode())
        assert len(s) == 1 and s.iloc[0] == 1.5
    with pytest.raises(ConnectionError):
        T12.parse_stooq(b"No data")


def test_check_excludes_a_symbol_with_mismatches(tmp_path):
    full, history, get, _ = fake_sources()
    T12.fetch(tmp_path / "r12", history=history, get=get, log=lambda *a: None)
    p = tmp_path / "r12" / "stooq" / "XLK.csv.gz"
    s = T12._read(p)
    bad = s.index[(s.index >= "2008-01-01")][:40:8]
    s.loc[bad, "close"] *= 1.2
    T12._write(p, s)
    rep = T12.check(tmp_path / "r12", log=lambda *a: None)
    assert "XLK" in rep["excluded"] and "SPY" not in rep["excluded"]
    assert rep["symbols"]["XLK"]["cross"]["fresh_mismatches"] > T12.MISMATCH_MAX
    assert "XLK" in T12.check_md(rep)


def test_end_to_end_run_and_zips(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "BOOT_DRAWS", 300)
    _, history, get, _ = fake_sources(seed=33)
    data, out = tmp_path / "data" / "r12", tmp_path / "data" / "sprint"
    T12.fetch(data, history=history, get=get, log=lambda *a: None)
    T12.check(data, log=lambda *a: None)
    lines = []
    ev, stamp = T12.run(data, out, log=lines.append, today=date(2026, 11, 3))
    assert stamp == "2026-11-03"
    md = (out / "round12_2026-11-03.md").read_text()
    assert "Round 12 result" in md and "Cross-source: Stooq" in md
    js = json.loads((out / "round12_2026-11-03.json").read_text())
    assert set(js["verdicts"]) == set(R.TRIALS)
    with gzip.open(out / "round12_daily_2026-11-03.csv.gz", "rt") as fh:
        daily = pd.read_csv(fh)
    assert {"T1_rsi2", "T9_mix", "SPY_bh", "cash"} <= set(daily.columns)
    assert sum(1 for x in lines if x.startswith("round12 ")) == 9
    zr, zd = T12.make_zips(data, out, tmp_path, stamp, log=lambda *a: None)
    with zipfile.ZipFile(zr) as z:
        names = z.namelist()
        assert "data/sprint/round12_2026-11-03.md" in names and "MANIFEST_sha256.json" in names
        assert any(n.startswith("data/sprint/trades_round12_T1_rsi2") for n in names)
    with zipfile.ZipFile(zd) as z:
        assert "data/r12/yahoo/SPY.csv.gz" in z.namelist()


def test_spy_excluded_or_no_cash_stops(tmp_path):
    _, history, get, _ = fake_sources()
    data = tmp_path / "r12"
    T12.fetch(data, history=history, get=get, log=lambda *a: None)
    rep = T12.check(data, log=lambda *a: None)
    rep["excluded"] = ["SPY"]
    (data / "check.json").write_text(json.dumps(rep))
    with pytest.raises(T12.Unusable):
        T12.run(data, tmp_path / "out", log=lambda *a: None)


def test_refuses_to_run_inside_desk(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "desk" / "x").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(home / "desk" / "x")
    with pytest.raises(T12.Unusable):
        T12.refuse_desk()
    monkeypatch.chdir(tmp_path)
    T12.refuse_desk()
