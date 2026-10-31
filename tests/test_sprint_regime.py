"""oa_crosscheck_v2's calm-regime filters: the IV-rank proxy (VIXY percentile over 252 split-adjusted daily closes,
no look-ahead, locked months never used), VIX not rising / rising (proxy: VIXY 1-minute bars), the combined regime,
the daily pull that cuts out the locked periods, and an end-to-end run. Synthetic data, fake HTTP, no network."""
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import data, engine, periods, runner
from sprint.data import Series
from sprint.entries import Signal

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2025, 3, 12)


def _daily(start=date(2023, 1, 2), end=date(2025, 6, 30), seed=0):
    days = [d for d in pd.bdate_range(start, end).date if not any(a <= d <= b for a, b in periods.LOCKED.values())]
    rng = np.random.default_rng(seed)
    return pd.Series(20 + np.cumsum(rng.normal(0, 0.3, len(days))), index=days)


def test_percentile_rank_uses_only_closes_up_to_the_prior_day():
    s = _daily()
    prior = date(2025, 3, 11)
    p = data.percentile_rank(s, prior)
    w = s[s.index <= prior].iloc[-252:]
    assert p == pytest.approx((w <= w.iloc[-1]).mean())
    later = s.copy()
    later[later.index > prior] = 999.0                                      # the future: no effect
    assert data.percentile_rank(later, prior) == p
    earlier = s.copy()
    earlier[earlier.index == w.index[0] - timedelta(days=1)] = 0.0          # outside the 252-close window: no effect
    assert data.percentile_rank(earlier, prior) == p
    assert data.percentile_rank(s, date(2023, 6, 1)) is None                 # fewer than 252 closes
    assert data.percentile_rank(s, date(2025, 3, 15)) is None                # a Saturday: no close that day
    lo = s.copy()
    lo[prior] = -100.0
    assert data.percentile_rank(lo, prior) == pytest.approx(1 / 252)
    # the window skips the locked months: early in NOT_SEEN it reaches back into 2023
    w2 = s[s.index <= date(2024, 9, 3)].iloc[-252:]
    assert w2.index[0].year == 2023 and not any(periods.LOCKED["L2"][0] <= d <= periods.LOCKED["L2"][1] for d in w2.index)


def test_read_daily_drops_locked_dates_even_if_present(tmp_path):
    import pull_alpaca as PA
    rows = [{"ts": pd.Timestamp(d, tz="America/New_York"), "o": 1, "h": 1, "l": 1, "c": float(k), "v": 1}
            for k, d in enumerate(["2024-01-31", "2024-03-01", "2024-07-31", "2024-08-01"])]
    PA._write_gz(tmp_path / "daily" / "VIXY.csv.gz", pd.DataFrame(rows))
    s = data.read_daily("VIXY", tmp_path)
    assert [d.isoformat() for d in s.index] == ["2024-01-31", "2024-08-01"]
    assert data.read_daily("NOPE", tmp_path) is None


def _ctx(vixy_today, vixy_prev=20.0, daily=None, spy_open=None):
    ctx, _ = SS.make_ctx(DAY, {0: spy_open} if spy_open else {}, {0: 1.0}, prior_days=2)
    prev = [d for d in SS.weekdays(DAY - timedelta(days=7), 10) if d < DAY][-1]
    rows = [SS.flat_day_df(prev, vixy_prev)]
    cur, today = vixy_prev, []
    for m in range(240, 960):
        if m - 570 in vixy_today:
            cur = vixy_today[m - 570]
        today.append((pd.Timestamp(f"{DAY} {m // 60:02d}:{m % 60:02d}", tz="America/New_York"), cur, cur, cur, cur, 100.0))
    rows.append(pd.DataFrame(today, columns=["ts", "o", "h", "l", "c", "v"]))
    ctx.aux = {"VIXY": Series("VIXY", pd.concat(rows, ignore_index=True)), "VIXY_D": daily}
    return ctx


def _sig(side="C", i=70):
    return Signal("orb60", "SPY", DAY, side, i, 500.0, None, {})


def test_vix_not_rising_and_rising_1pct():
    f = engine._filters_ok
    ctx = _ctx({0: 20.1, 60: 20.3})                                           # +0.5% then +1.5% from 10:30
    assert f({"filters": ("vixy_not_rising",)}, ctx, _sig(i=50), 0) is None
    assert "up more than 1%" in f({"filters": ("vixy_not_rising",)}, ctx, _sig(i=70), 0)
    assert "not up 1%" in f({"filters": ("vixy_rising_1pct",)}, ctx, _sig("P", 50), 0)
    assert f({"filters": ("vixy_rising_1pct",)}, ctx, _sig("P", 70), 0) is None
    edge = _ctx({0: 20.2})                                                    # exactly +1%: not rising AND rising 1%
    assert f({"filters": ("vixy_not_rising",)}, edge, _sig(), 0) is None and f({"filters": ("vixy_rising_1pct",)}, edge, _sig(), 0) is None


def test_percentile_filters_and_the_combined_regimes():
    f = engine._filters_ok
    prev = date(2025, 3, 11)
    base = _daily()
    calm_d = base.copy()
    calm_d[prev] = float(base[base.index <= prev].iloc[-252:].min()) - 1      # lowest close of the year: percentile 1/252
    storm_d = base.copy()
    storm_d[prev] = float(base[base.index <= prev].iloc[-252:].max()) + 1     # highest: percentile 100%
    calm = ("vixy_pctl_le40", "vixy_not_rising", "gap_side_075")
    ok = _ctx({0: 20.0}, daily=calm_d, spy_open=502.0)                        # calm VIX, flat VIXY, +0.4% gap
    assert f({"filters": calm}, ok, _sig("C"), 0) is None
    assert "gap outside" in f({"filters": calm}, ok, _sig("P"), 0)            # puts need a gap down
    assert "above 40%" in f({"filters": calm}, _ctx({0: 20.0}, daily=storm_d, spy_open=502.0), _sig("C"), 0)
    assert "up more than 1%" in f({"filters": calm}, _ctx({0: 21.0}, daily=calm_d, spy_open=502.0), _sig("C"), 0)
    storm = ("vixy_pctl_ge60", "vixy_rising_1pct")
    assert f({"filters": storm}, _ctx({0: 21.0}, daily=storm_d), _sig("P"), 0) is None
    assert "below 60%" in f({"filters": storm}, _ctx({0: 21.0}, daily=calm_d), _sig("P"), 0)
    assert "unknown" in f({"filters": ("vixy_pctl_le40",)}, _ctx({0: 20.0}, daily=None), _sig(), 0)


def test_daily_pull_cuts_out_locked_periods_and_is_split_adjusted(tmp_path, monkeypatch):
    import pull_alpaca as PA
    import sprint_pull as SPL
    calls = []

    def fake(url, headers):
        assert url.startswith("https://data.alpaca.markets/")
        calls.append(url)
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        a, b = pd.Timestamp(q["start"]).tz_convert("America/New_York").date(), pd.Timestamp(q["end"]).tz_convert("America/New_York").date()
        days = [d for d in pd.bdate_range(a, b - timedelta(days=1)).date]
        return {"bars": [{"t": pd.Timestamp(d, tz="America/New_York").tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
                          "o": 20, "h": 20, "l": 20, "c": 20.0, "v": 1} for d in days], "next_page_token": None}
    monkeypatch.setattr(PA, "_http", fake)
    monkeypatch.setattr(PA, "_calls", [])
    monkeypatch.setattr(PA, "ROOT", tmp_path / "alpaca")
    monkeypatch.setenv("ALPACA_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET", "s")
    assert SPL.main(["--symbols", "", "--stock-only", "", "--daily", "VIXY", "--daily-from", "2023-01-01",
                     "--from", "2024-08-01", "--to", "2025-10-29", "--root", str(tmp_path / "alpaca")]) == 0
    assert len(calls) == 2
    for c in calls:
        q = {k: v[0] for k, v in parse_qs(urlparse(c).query).items()}
        assert q["timeframe"] == "1Day" and q["adjustment"] == "split"
        a = pd.Timestamp(q["start"]).tz_convert("America/New_York").date()
        b = pd.Timestamp(q["end"]).tz_convert("America/New_York").date() - timedelta(days=1)
        assert periods.overlaps(a, b) == []                                    # never asks for a locked date
    s = data.read_daily("VIXY", tmp_path / "alpaca")
    assert s.index.min() <= date(2023, 1, 3) and s.index.max() == date(2025, 10, 29)
    assert not any(date(2024, 2, 1) <= d <= date(2024, 7, 31) for d in s.index)
    assert SPL.locked_free_segments(date(2023, 1, 1), date(2026, 12, 31)) == [
        (date(2023, 1, 1), date(2024, 1, 31)), (date(2024, 8, 1), date(2026, 6, 30)), (date(2026, 10, 31), date(2026, 12, 31))]


def test_v2_spec_runs_end_to_end_with_the_proxies(tmp_path):
    import pull_alpaca as PA
    root = tmp_path / "alp"
    days = SS.weekdays(date(2025, 1, 6), 12)
    SS.write_cache(root, "SPY", days, band=0.01, trend={d: (65, 0.0002 if k % 2 else -0.0002) for k, d in enumerate(days)})
    vx = pd.concat([SS.stock_day(d, 20.0, 50 + k) for k, d in enumerate(days)], ignore_index=True)
    for m, g in vx.groupby(vx["ts"].dt.strftime("%Y-%m")):
        PA._write_gz(root / "stocks" / "VIXY" / f"{m}.csv.gz", g.reset_index(drop=True))
    dly = _daily(end=date(2025, 1, 31))
    PA._write_gz(root / "daily" / "VIXY.csv.gz", pd.DataFrame({"ts": [pd.Timestamp(d, tz="America/New_York") for d in dly.index],
                                                                "o": dly.values, "h": dly.values, "l": dly.values, "c": dly.values, "v": 1.0}))
    spec = json.loads((ROOT / "sprint" / "specs" / "oa_crosscheck_v2.json").read_text())
    spec["symbols"] = ["SPY"]
    for b in spec["blocks"]:
        b["grid"]["symbols"] = [["SPY"]]
    spec["robustness"] = {"top_k": 1, "random_paths": 1, "fake_seeds": 0, "min_trades": 1}
    p = tmp_path / "v2.json"
    p.write_text(json.dumps(spec))
    lines = []
    res = runner.run_spec(p, data_root=root, chains_dir=tmp_path / "none", out_dir=tmp_path / "o", host_name="h", log=lines.append,
                          today=date(2026, 10, 31))
    assert any("VIX percentile proxy: VIXY daily" in x for x in lines) and any("VIX proxy: VIXY loaded" in x for x in lines)
    rows = list(csv.DictReader(open(tmp_path / "o" / "runs_h.csv")))
    assert len(rows) == 22 and {r["period_tag"] for r in rows} == {"NOT_SEEN_BY_OA"}
    pct = [r for r in rows if "vixy_pctl_le40" in r["filters"]]
    assert pct and all("proxy: VIXY percentile" in r["notes"] for r in pct)
    for rid, v in res["results"].items():                                      # unknown only on the first session (no prior day)
        assert sum(n for k, n in v["skips"].items() if "percentile unknown" in k) <= 1, (rid, v["skips"])
    rep = (tmp_path / "o" / "report_2026-10-31_oa_crosscheck_v2.md").read_text()
    assert "proxy: VIXY percentile" in rep and "never saw" in rep


def test_v2_spec_shape():
    spec = json.loads((ROOT / "sprint" / "specs" / "oa_crosscheck_v2.json").read_text())
    runs = engine.expand(spec)
    runner.validate(runs)
    assert len(runs) == 66 and spec["period"] == "NOT_SEEN_BY_OA"
    by = {engine.run_key(r): r for r in runs}
    assert all(runner._twin(r, by) is not None for r in runs if r["filters"])
    assert {(r["exit"].fixed_stop, r["exit"].fixed_target, r["exit"].contract) for r in runs} == {
        (0.5, 1.0, "d45-60t50"), (0.2, 0.6, "d40-55t45")}
    assert {r["side"] for r in runs if "vixy_pctl_ge60" in r["filters"]} == {"P"}
    assert all(r["exit"].mechanics == "desk" for r in runs)
