"""Sprint run 3 tools: entry features stamped on trades (no look-ahead), the walk-forward learner (sprint/learn.py:
out-of-sample only, learns a planted pattern, ignores noise, never uses later months), the combined book
(sprint/book.py: zero-trade sessions count, desk daily stop on closed trades only, correlation) and the study CLI."""
import gzip
import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import book, features, learn, runner
from test_sprint_entries import _failed_break_ctx, _random_ctx, _with_future_changed


def test_entry_features_are_known_at_entry():
    ctx = _random_ctx()
    for j, side in ((40, "C"), (120, "P"), (300, "C")):
        f = features.entry_features(ctx, j, side)
        assert set(f) == set(features.FEATURES) and f["f_minute"] == j + 1
        g = features.entry_features(_with_future_changed(ctx, j, seed=j), j, side)
        assert f == g                                            # scrambling later bars changes nothing
    c, p = features.entry_features(ctx, 120, "C"), features.entry_features(ctx, 120, "P")
    assert c["f_day_ret"] == pytest.approx(-p["f_day_ret"]) and c["f_minute"] == p["f_minute"]


def _trades(n_months=12, per_month=40, seed=3, planted=True):
    rng = np.random.default_rng(seed)
    rows, d0 = [], date(2024, 8, 1)
    for m in range(n_months):
        for k in range(per_month):
            day = (d0 + timedelta(days=31 * m + k % 28)).isoformat()
            minute = int(rng.integers(15, 345))
            votes = int(rng.integers(0, 6))
            edge = (25 if minute < 150 else -25) if planted else 0
            pnl = float(rng.normal(edge, 30))
            r = {f: float(rng.normal()) for f in features.FEATURES}
            r.update({"day": day, "f_minute": minute, "f_trend_votes": votes, "pnl": pnl, "pnl_2x": pnl - 4, "symbol": "SPY",
                      "side": "C", "entry_time": "10:00", "exit_time": "10:30"})
            rows.append(r)
    return rows


def test_learner_finds_a_planted_time_of_day_edge_out_of_sample():
    res = learn.walk_forward(_trades(), min_train_months=4)
    assert res["oos_from"] == "2024-12" and res["base"]["trades"] == 8 * 40
    for m, gain in (("logit", 10), ("ridge", 10), ("buckets", 5)):     # buckets are coarse: 4 time cells
        r = res["models"][m]
        assert r["pass"] and r["taken"]["expectancy"] > res["base"]["expectancy"] + gain, m
    bk = res["models"]["buckets"]["last_fit"]
    assert {(x["time"], x["skip"]) for x in bk if x["train_trades"] >= 30} >= {("12:00-14:00", True)}


def test_learner_does_not_pass_on_noise_and_never_uses_later_months():
    res = learn.walk_forward(_trades(planted=False, seed=5), min_train_months=4)
    assert not any(r["pass"] for r in res["models"].values())
    rows = _trades(seed=9)
    first_oos = [r for r in rows if r["day"][:7] == "2024-12"]
    train = [r for r in rows if r["day"][:7] < "2024-12"]
    for m in learn.MODELS:
        a, _ = learn.decide(m, train, first_oos)
        later = [dict(r, pnl=-r["pnl"]) if r["day"][:7] > "2024-12" else r for r in rows]
        b, _ = learn.decide(m, [r for r in later if r["day"][:7] < "2024-12"], first_oos)
        assert (a == b).all()
    assert "error" in learn.walk_forward(_trades(n_months=3), min_train_months=6)


def _t(day, rid, sym, e, x, pnl):
    return {"day": day, "run_id": rid, "symbol": sym, "side": "C", "entry_time": e, "exit_time": x, "pnl": pnl, "pnl_2x": pnl - 2}


def test_book_counts_every_session_and_applies_the_daily_stop_on_closed_trades():
    a = [_t("2025-02-03", "A", "SPY", "10:00", "10:20", -100), _t("2025-02-03", "A", "SPY", "11:00", "11:10", 50),
         _t("2025-02-05", "A", "SPY", "10:00", "10:05", 30)]
    b = [_t("2025-02-03", "B", "QQQ", "10:10", "10:40", -60),       # opened before A's loss closed: allowed
         _t("2025-02-03", "B", "QQQ", "10:45", "11:00", 80),        # closed losses -160 <= -150: skipped
         _t("2025-02-03", "B", "SPY", "10:15", "10:30", 10)]        # overlaps A's first SPY call
    res = book.combine({"A": a, "B": b}, "2025-02-03", "2025-02-07")
    assert res["sessions"] == 5 and res["book"]["trades"] == 6 and res["book"]["pct_sessions"] == 0.4
    assert res["book"]["total"] == pytest.approx(10.0) and res["overlaps"] == 1
    s = book.combine({"A": a, "B": b}, "2025-02-03", "2025-02-07", daily_stop=150)
    assert s["daily_stop"]["skipped"] == 2 and s["book"]["total"] == pytest.approx(-100 - 60 + 10 + 30)
    assert set(s["corr"]) == {"A", "B"} and s["corr"]["A"]["A"] == 1.0
    assert "BOOK (daily stop $150)" in book.report_md(s)


def test_study_cli_auto_picks_one_run_per_family_and_reports(tmp_path, monkeypatch):
    import sprint_study as ST
    rows = _trades(n_months=10, seed=11)
    cols = ["run_id", "symbol", "day", "side", "signal_idx", "entry_time", "exit_time", "pnl", "pnl_2x"] + features.FEATURES
    df = pd.DataFrame([dict(r, run_id=rid, signal_idx=30) for rid in ("s-001", "s-002", "s-003") for r in rows])
    df.loc[df.run_id == "s-003", "pnl"] *= -1
    with gzip.open(tmp_path / "trades_s_2026-10-31.csv.gz", "wt") as f:
        df[cols].to_csv(f, index=False)
    log = pd.DataFrame([{"run_id": "s-001", "tool": "DeskEngine", "period_tag": "DEV", "setup": "failed_break", "trades": 400,
                         "expectancy": 5.0, "profit_factor": 1.3, "pf_2x_slip": 1.05},
                        {"run_id": "s-002", "tool": "DeskEngine", "period_tag": "DEV", "setup": "failed_break_w10", "trades": 400,
                         "expectancy": 6.0, "profit_factor": 1.4, "pf_2x_slip": 1.1},
                        {"run_id": "s-003", "tool": "DeskEngine", "period_tag": "DEV", "setup": "vwap_macd", "trades": 400,
                         "expectancy": -5.0, "profit_factor": 0.8, "pf_2x_slip": 0.6},
                        {"run_id": "s-002@s5", "tool": "DeskEngine", "period_tag": "DEV", "setup": "failed_break_w10", "trades": 400,
                         "expectancy": 9.0, "profit_factor": 2.0, "pf_2x_slip": 1.5}])
    log.to_csv(tmp_path / "runs_t.csv", index=False)
    rc = ST.main(["auto", "--trades", str(tmp_path / "trades_*.csv.gz"), "--runs-csv", str(tmp_path / "runs_*.csv"),
                  "--out", str(tmp_path / "out"), "--from", "2024-08-01", "--to", "2025-06-30", "--min-train-months", "4"])
    assert rc == 0
    js = json.loads(next((tmp_path / "out").glob("study_auto_*.json")).read_text())
    assert js["candidates"] == ["s-002"]                            # best of the failed_break family; vwap_macd: none held up
    md = next((tmp_path / "out").glob("study_auto_*.md")).read_text()
    assert "| vwap_macd | none held up" in md and "Learner: s-002" in md and "Combined book" in md
    assert ST.main(["book", "--from", "2024-07-15", "--to", "2024-09-01", "--out", str(tmp_path / "x")]) == 2   # locked period


def test_runner_trade_files_carry_the_features(tmp_path):
    days = SS.weekdays(date(2025, 1, 6), 8)
    root = tmp_path / "alpaca"
    SS.write_cache(root, "SPY", days, band=0.01, trend={d: (35, 0.00012 if k % 2 else -0.00012) for k, d in enumerate(days)})
    spec = {"spec_id": "ft", "period": "DEV", "symbols": ["SPY"], "description": "features",
            "defaults": {"side": "both", "contract": "d40-55t45", "allout": "15:25", "time": "b", "stop": "premium", "tp": "none",
                         "tp_buffer": "$0.03", "rr_min": None, "trail": "none", "filters": []},
            "blocks": [{"name": "a", "grid": {"entry": ["orb15"]}}], "robustness": {"top_k": 0, "min_trades": 1}}
    p = tmp_path / "ft.json"
    p.write_text(json.dumps(spec))
    runner.run_spec(p, days[0], days[-1], data_root=root, chains_dir=tmp_path / "nc", out_dir=tmp_path / "out", host_name="t",
                    log=lambda *x: None, today=date(2026, 10, 31))
    tf = next((tmp_path / "out").glob("trades_ft_*.csv.gz"))
    df = pd.read_csv(tf)
    assert len(df) and set(features.FEATURES) <= set(df.columns) and df["f_minute"].notna().all()
    rows = df.to_dict("records")
    old = [{k: v for k, v in r.items() if not k.startswith("f_")} for r in rows]
    features.recompute(old, root)
    same = lambda a, b: (a is None or (isinstance(a, float) and np.isnan(a))) == (b is None or (isinstance(b, float) and np.isnan(b))) and (
        a is None or (isinstance(a, float) and np.isnan(a)) or a == pytest.approx(b))
    for r, o in zip(rows, old):
        assert all(same(o[k], r[k]) for k in features.FEATURES), [(k, o[k], r[k]) for k in features.FEATURES if not same(o[k], r[k])]
