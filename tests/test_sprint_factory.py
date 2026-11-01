"""SPRINT_PLAN Amendment 9, the 10-year strategy factory (sprint/factory.py, tools/sprint_factory.py): the new time entries
(rules, no look-ahead), the two specs, the rule selection (2016-2019 only, a planted edge is found, 2020+ data never
changes the rule), the holdout bars, the learner's decisions equal learn.walk_forward's, the survival and verdict logic,
the book's aggregation and labels, and the CLI end to end on synthetic trade files. Synthetic data only."""
import gzip
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
import sprint_regime as SR
from sprint import book, engine, entries, factory, features, learn, periods, runner
from sprint import modeled as MD

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2025, 3, 12)
SPECS = ROOT / "sprint" / "specs"


# ---------------------------------------------------------------- the new time entries
def _ctx(path, early=False):
    ctx, _ = SS.make_ctx(DAY, path, {0: 1.0}, prior_days=12, early=early)
    return ctx


def test_new_time_entries_fire_on_their_bar_every_session():
    assert {k: entries.TIME_ENTRIES[k] for k in ("time_1000", "time_1030", "time_1100", "time_1200", "time_1300", "time_1400")} == \
        {"time_1000": 29, "time_1030": 59, "time_1100": 89, "time_1200": 149, "time_1300": 209, "time_1400": 269}
    for name, idx in entries.TIME_ENTRIES.items():
        assert name in entries.SETUPS and entries.ENTRY_WINDOWS[name] == (entries.DESK_FIRST, entries.DESK_LAST)
        assert 570 + idx + 1 == int(name[5:7]) * 60 + int(name[7:9])                 # the bar FINISHES at the named time
    ctx = _ctx({0: 500.0, 29: 500.4, 149: 501.0, 209: 499.5, 269: 499.0})
    for name, idx, px in (("time_1000", 29, 500.4), ("time_1200", 149, 501.0), ("time_1300", 209, 499.5), ("time_1400", 269, 499.0)):
        s = entries.signals(ctx, name)
        assert [(x.setup, x.side, x.idx, x.price, x.invalid) for x in s] == [(name, "C", idx, px, None), (name, "P", idx, px, None)]
        assert [x.side for x in entries.signals(ctx, name, "P")] == ["P"]
    early = _ctx({0: 500.0}, early=True)                                                  # 1:00 PM close: no 13:00 / 14:00 signal
    assert early.close_idx == 210
    assert [x.idx for x in entries.signals(early, "time_1200", "C")] == [149]
    assert entries.signals(early, "time_1300") == [] and entries.signals(early, "time_1400") == []
    gap = _ctx({0: 500.0})
    gap.c[29] = np.nan                                                                    # no finished 10:00 bar: no signal
    assert entries.signals(gap, "time_1000") == []


def test_new_time_entries_have_no_look_ahead():
    base = {0: 500.0, 29: 500.4, 149: 501.0, 209: 499.5, 269: 499.0}
    full = _ctx(base)
    for name, idx in (("time_1000", 29), ("time_1200", 149), ("time_1300", 209), ("time_1400", 269)):
        want = [(x.side, x.idx, x.price) for x in entries.signals(full, name)]
        for cut in (idx, idx + 1, idx + 30):
            changed = dict(base)
            changed.update({cut + 1: 530.0, cut + 5: 470.0, 380: 520.0})                  # every later bar moves
            got = entries.signals(_ctx(changed), name)
            assert [(x.side, x.idx, x.price) for x in got if x.idx <= cut] == want


# ---------------------------------------------------------------- the two specs
EXPECT = {"noise": ("noise", "both", "noise", "d55-75t65"), "orb15": ("orb15", "both", "premium", "d40-55t45"),
          "orb30": ("orb30", "both", "premium", "d40-55t45"), "orb60": ("orb60", "both", "premium", "d40-55t45"),
          "vwap_macd": ("vwap_macd", "both", "premium", "d40-55t45"), "pd_retest": ("pd_retest", "both", "premium", "d40-55t45"),
          "flush": ("flush", "both", "premium", "d40-55t45"), "failed_break": ("failed_break", "C", "premium", "d40-55t45"),
          "failed_high": ("failed_high", "P", "premium", "d40-55t45")}
for _t in ("1000", "1030", "1100", "1200", "1300", "1400"):
    EXPECT[f"otm_c_{_t}"] = (f"time_{_t}", "C", "fixed", "d03-12t07")
for _t in ("1000", "1030", "1100", "1200", "1300", "1400"):
    EXPECT[f"otm_p_{_t}"] = (f"time_{_t}", "P", "fixed", "d06-15t10")


def test_factory_specs_are_the_preregistered_21_runs_in_the_same_order():
    h, d = (json.loads((SPECS / f"{n}.json").read_text()) for n in ("factory_hist_v1", "factory_dev_v1"))
    assert h["period"] == "HIST" and h["tapes"] == "modeled" and d["period"] == "DEV" and d.get("tapes", "real") == "real"
    assert h["robustness"]["top_k"] == 0 == d["robustness"]["top_k"]                     # no pass 2: the factory checks itself
    rh, rd = engine.expand(h), engine.expand(d)
    runner.validate(rh)
    runner.validate(rd)
    assert [r["block"] for r in rh] == list(EXPECT) == [r["block"] for r in rd]
    assert [engine.run_key(r) for r in rh] == [engine.run_key(r) for r in rd]
    assert [r["run_id"] for r in rh] == [f"factory_hist_v1-{k:03d}" for k in range(1, 22)]
    for r in rh:
        x = r["exit"]
        assert (r["entry"], r["side"], x.stop, x.contract) == EXPECT[r["block"]]
        assert r["symbols"] == ("SPY", "QQQ", "IWM") and r["filters"] == () and x.allout == "15:25" and x.time == "b"
        assert x.tp == "none" and x.trail == "none" and x.mechanics == "desk" and x.risk == "none" and x.rr_min is None
        if x.stop == "fixed":
            assert (x.fixed_stop, x.fixed_target) == (0.95, 99.0)
    calib = json.loads((ROOT / "docs/research/sprint_reports/2026-10-31_run4/calib_modeled.json").read_text())
    for r in rh:                                                                          # run 4's calibration has every key
        for sd in (("C", "P") if r["side"] == "both" else (r["side"],)):
            assert MD.multiplier(calib, r["exit"].contract, sd) > 0


# ---------------------------------------------------------------- synthetic trades
def _rows(name, seed, per_day=1, every=1, planted=None, src_only=None, edge=30.0, dev_edge=None):
    """Trade dicts for one strategy over HIST and DEV sessions. planted = (feature, "top"/"bottom", threshold): trades on
    that side of the threshold win `edge` more on average."""
    rng = np.random.default_rng(seed)
    out = []
    for src, a, b in (("HIST", factory.HIST_A, factory.HIST_B), ("DEV", factory.DEV_A, factory.DEV_B)):
        if src_only and src != src_only:
            continue
        for d in book.sessions_between(a, b)[::every]:
            for k in range(per_day):
                f = {n: float(rng.normal()) for n in features.FEATURES}
                f.update(f_minute=float(rng.integers(30, 330)), f_trend_votes=float(rng.integers(0, 6)),
                         f_rvol=float(np.exp(rng.normal(0, 0.3))), f_vixy_pctl=float(rng.uniform()))
                e = 0.0
                if planted:
                    v = f[planted[0]]
                    if (v >= planted[2]) if planted[1] == "top" else (v <= planted[2]):
                        e = edge if (src == "HIST" or dev_edge is None) else dev_edge
                pnl = float(rng.normal(-3 + e, 40))
                out.append(dict(f, run_id=f"syn-{name}", symbol=("SPY", "QQQ", "IWM")[k % 3], day=d, side="C" if k % 2 == 0 else "P",
                                signal_idx=60 + k, entry_time=f"{10 + k:02d}:{(7 * k) % 60:02d}", exit_time=f"{11 + k:02d}:30",
                                pnl=pnl, pnl_2x=pnl - 2.0, _src=src))
    return out


def test_rule_search_finds_a_planted_edge_on_2016_2019_and_freezes_its_cut():
    rows = _rows("p", 1, per_day=2, planted=("f_gap", "bottom", -0.43))
    rule, cands, n_disc = factory.find_rule(rows)
    disc = [r for r in rows if r["_src"] == "HIST" and "2016-01-04" <= r["day"] <= "2019-12-31"]
    assert n_disc == len(disc) and len(cands) == 12
    assert [(c["feature"], c["side"]) for c in cands] == [(f, s) for f in factory.FEATURES6 for s in ("top", "bottom")]
    assert rule["feature"] == "f_gap" and rule["side"] == "bottom"
    assert rule["cut"] == pytest.approx(float(np.quantile([r["f_gap"] for r in disc], 1 / 3)))
    kept = factory.apply_rule(disc, rule)
    assert all(r["f_gap"] <= rule["cut"] for r in kept) and len(kept) >= 60
    top = [c for c in cands if c["feature"] == "f_rvol" and c["side"] == "top"][0]
    assert top["cut"] == pytest.approx(float(np.quantile([r["f_rvol"] for r in disc], 2 / 3)))
    assert factory.keep({"f_gap": None}, rule) is False and factory.keep({"f_gap": float("nan")}, rule) is False


def test_rule_never_changes_when_2020_and_later_data_change():
    rows = _rows("p", 2, per_day=2, planted=("f_rvol", "top", 1.15))
    rule, cands, _ = factory.find_rule(rows)
    rng = np.random.default_rng(5)
    later = []
    for r in rows:
        if r["day"] >= "2020-01-01":
            r = dict(r, pnl=float(rng.normal(50, 90)), f_rvol=float(rng.uniform(0, 9)), f_gap=float(rng.normal(3, 5)))
        later.append(r)
    later += [dict(r, day="2021-06-0" + str(1 + k % 4), pnl=-500.0) for k, r in enumerate(rows[:200])]
    later += [dict(r, _src="DEV", day="2025-02-03", pnl=900.0, f_rvol=0.1) for r in rows[:300]]
    rule2, cands2, _ = factory.find_rule(later)
    assert rule2 == rule and cands2 == cands
    early = [dict(r, pnl=-r["pnl"]) if r["day"] <= "2019-12-31" else r for r in rows]     # but 2016-2019 data does matter
    assert factory.find_rule(early)[0] != rule


def test_rule_ties_need_60_trades_and_break_on_trades_then_order():
    rows = _rows("thin", 3, every=12)                                                     # ~84 discovery trades: terciles < 60
    rule, cands, n = factory.find_rule(rows)
    assert rule is None and n < 180 and not any(c["eligible"] for c in cands)
    out, sleeve, _ = factory.run_strategy("thin", rows)
    assert out["rule"]["survives"] is False and "no candidate kept 60 trades" in out["rule"]["why_not"]
    assert factory._pf_rank(float("inf")) > factory._pf_rank(9.0) > factory._pf_rank(None)


def test_day_skip_p_is_sprint_regime_method():
    rng = np.random.default_rng(4)
    base = [{"day": f"2021-0{1 + i % 9}-1{i % 7}", "pnl": float(rng.normal(0, 20))} for i in range(300)]
    sel = [r for r in base if r["pnl"] > -5][:150]
    tot = sum(r["pnl"] for r in sel)
    for seed in (17, 23):
        assert factory.day_skip_p(base, tot, len(sel), seed) == SR.day_skip_p(pd.DataFrame(base), tot, len(sel), seed=seed)
    assert factory.day_skip_p(base, tot, len(base), 17) is None                           # nothing removed: no test


def test_holdout_bars():
    rows = _rows("p", 6, per_day=2, planted=("f_rvol", "top", 1.15))
    rule, _, _ = factory.find_rule(rows)
    h1, h2 = factory.holdout1(rows, rule), factory.holdout2(rows, rule)
    assert h1["pass"] and h2["pass"] and h1["p_day_skip"] < 0.05 and h2["p_day_skip"] < 0.10
    assert h1["base_trades"] == len([r for r in rows if r["_src"] == "HIST" and "2020-01-01" <= r["day"] <= "2024-01-31"])
    assert len(h1["checks"]) == 6 and len(h2["checks"]) == 4
    # the same rule where the edge is gone after 2021: fails the "3 of 4 years" check
    gone = [dict(r, pnl=-abs(r["pnl"])) if r["day"] >= "2022-01-01" and r["_src"] == "HIST" else r for r in rows]
    g1 = factory.holdout1(gone, rule)
    assert not g1["pass"] and not dict(g1["checks"])[[k for k, _ in g1["checks"] if k.startswith("profitable in at least 3")][0]]
    # a DEV edge that vanishes: holdout 2 fails, and the strategy has no surviving rule
    dead = _rows("p", 6, per_day=2, planted=("f_rvol", "top", 1.15), dev_edge=0.0)
    out, _, _ = factory.run_strategy("dead", dead)
    assert out["rule"]["holdout1"]["pass"] and not out["rule"]["holdout2"]["pass"]
    assert out["rule"]["survives"] is False and out["rule"]["why_not"].startswith("holdout 2:")


# ---------------------------------------------------------------- the learner
def test_learner_decisions_equal_learn_walk_forward():
    rows = _rows("n", 7, every=3)
    want = learn.walk_forward(rows, min_train_months=24)
    got, picks = factory.walk_forward_masks(rows)
    assert got.pop("oos_rows") == want["base"]["trades"]
    assert got == want
    for m in factory.MODELS:
        p = picks[m]
        assert len(p) == want["models"][m]["taken"]["trades"]
        assert round(sum(r["pnl"] for r in p), 2) == want["models"][m]["taken"]["total"]
        assert min(r["day"] for r in p) >= want["oos_from"]
    few = [r for r in rows if r["day"] < "2017-06-01"]
    assert "error" in factory.walk_forward_masks(few)[0] and "error" in learn.walk_forward(few, 24)


def test_learner_survival_needs_walk_forward_pass_and_a_real_dev_segment():
    rows = _rows("p", 8, per_day=2, planted=("f_rvol", "top", 1.15))
    ln, picks = factory.learner(rows)
    lg = ln["models"]["logit"]
    assert lg["pass_walk_forward"] and lg["survives"] and lg["dev"]["trades"] >= 40
    assert lg["dev"]["trades"] == len([r for r in picks["logit"] if r["_src"] == "DEV"])
    assert all(not y["oos"] for k, y in lg["years"].items() if k in ("2016", "2017"))
    dead = _rows("p", 8, per_day=2, planted=("f_rvol", "top", 1.15), dev_edge=-20.0)       # works on HIST, loses on real prices
    ln2, _ = factory.learner(dead)
    g = ln2["models"]["logit"]
    assert g["pass_walk_forward"] and not g["survives"] and g["why_not"].startswith("DEV-only")
    s = {"trades": 39, "pf": 3.0, "pf_2x": 2.0}
    assert [ok for _, ok in factory.dev_checks(s)] == [False, True, True]


def test_verdict_picks_the_best_dev_expectancy_among_survivors():
    rb = {"survives": True, "holdout2": {"stats": {"expectancy": 5.0}}}
    ln = {"models": {"logit": {"survives": True, "dev": {"expectancy": 7.0}}, "ridge": {"survives": False, "dev": {"expectancy": 99.0}},
                     "buckets": {"survives": True, "dev": {"expectancy": 7.0}}}}
    assert factory.choose(rb, ln)[0] == "logit"                                           # tie with buckets: logit first
    assert factory.choose(rb, {"models": {}})[0] == "rule"
    assert factory.choose(dict(rb, holdout2={"stats": {"expectancy": 7.0}}), ln)[0] == "rule"
    assert factory.choose({"survives": False}, {"models": {}}) == ("none", "no variant survived")


# ---------------------------------------------------------------- the book
def test_book_windows_count_every_session_and_never_mix_sources_unlabeled():
    a = _rows("a", 9, every=5)
    b = _rows("b", 10, every=7)
    bv = factory.book_views({"a": a, "b": b})
    w = bv["windows"]
    hist_days, dev_days = book.sessions_between(*factory.BOOK_HIST), book.sessions_between(factory.DEV_A, factory.DEV_B)
    assert w["hist"]["plain"]["book"]["sessions"] == len(hist_days) and w["dev"]["plain"]["book"]["sessions"] == len(dev_days)
    assert w["mixed"]["plain"]["book"]["sessions"] == len(hist_days) + len(dev_days)
    assert not any("2024-02-01" <= d <= "2024-07-31" for d in hist_days + dev_days)       # the locked L2 gap is never a session
    assert w["mixed"]["label"] == "mixed: modeled 2018-2024 + real 2024-2026"
    tot = lambda rows, lo, hi: round(sum(r["pnl"] for r in rows if lo <= r["day"] <= hi), 2)
    for key, lo, hi in (("hist", factory.BOOK_HIST[0], factory.HIST_B), ("dev", factory.DEV_A, factory.DEV_B)):
        bk = w[key]["plain"]
        assert bk["sleeves"]["a"]["total"] == tot(a, lo, hi) and bk["sleeves"]["b"]["total"] == tot(b, lo, hi)
        assert bk["book"]["total"] == pytest.approx(tot(a, lo, hi) + tot(b, lo, hi), abs=0.02)
        assert bk["book"]["avg_per_year"] == pytest.approx(bk["book"]["total"] / (bk["book"]["sessions"] / 252), abs=0.02)
        assert set(bk["corr"]) == {"a", "b"} and isinstance(bk["overlaps"], int)
    months = sorted({d[:7] for d in hist_days})
    assert w["hist"]["plain"]["book"]["months_green"].endswith(f"/{len(months)}")
    assert list(bv["years"]) == ["2018", "2019", "2020", "2021", "2022", "2023", "Jan 2024", "Aug-Dec 2024", "2025", "Jan-Jun 2026"]
    assert [bv["years"][k]["prices"] for k in ("2023", "Jan 2024", "Aug-Dec 2024", "2025")] == ["MODELED", "MODELED", "REAL", "REAL"]
    jan = bv["years"]["Jan 2024"]["book"]
    assert jan["total"] == pytest.approx(tot(a, "2024-01-01", "2024-01-31") + tot(b, "2024-01-01", "2024-01-31"), abs=0.02)
    dev_only = factory.book_views({"a": [dict(r, _src="DEV") for r in a if r["_src"] == "HIST"]})
    assert dev_only["windows"]["dev"]["plain"]["book"]["trades"] == 0                    # a HIST row never lands in the DEV window


def test_book_daily_stop_view_skips_entries_after_a_closed_loss():
    rows = [{"day": "2025-03-12", "symbol": "SPY", "side": "C", "entry_time": "10:00", "exit_time": "10:30", "pnl": -160.0, "pnl_2x": -165.0,
             "_src": "DEV"},
            {"day": "2025-03-12", "symbol": "QQQ", "side": "C", "entry_time": "11:00", "exit_time": "11:30", "pnl": 80.0, "pnl_2x": 75.0,
             "_src": "DEV"}]
    days = book.sessions_between("2025-03-10", "2025-03-14")
    plain, stop = factory.window_book({"x": rows}, days), factory.window_book({"x": rows}, days, daily_stop=150.0)
    assert plain["book"]["total"] == -80.0 and stop["book"]["total"] == -160.0 and stop["daily_stop"]["skipped"] == 1
    assert plain["book"]["sessions"] == 5 and plain["book"]["months_green"] == "0/1" and plain["book"]["worst_month"] == ("2025-03", -80.0)


# ---------------------------------------------------------------- the CLI end to end
def _small_specs(folder):
    """Three of the factory's runs, as a HIST/DEV spec pair (the CLI's checks are the same for 21)."""
    h, d = (json.loads((SPECS / f"{n}.json").read_text()) for n in ("factory_hist_v1", "factory_dev_v1"))
    keep = {"noise", "orb30", "otm_c_1100"}
    for s, n in ((h, "fx_hist"), (d, "fx_dev")):
        s.update(spec_id=n, blocks=[b for b in s["blocks"] if b["name"] in keep])
        (folder / f"{n}.json").write_text(json.dumps(s))
    return folder / "fx_hist.json", folder / "fx_dev.json"


def _write_trades(path, spec_path, rows_by_block):
    runs = engine.expand(json.loads(Path(spec_path).read_text()))
    out = []
    for r in runs:
        for t in rows_by_block[r["block"]]:
            out.append({k: v for k, v in dict(t, run_id=r["run_id"]).items() if k != "_src"})
    with gzip.open(path, "wt") as f:
        pd.DataFrame(out).to_csv(f, index=False)


def test_factory_cli_end_to_end(tmp_path):
    import sprint_factory
    hs, ds = _small_specs(tmp_path)
    blocks = {"noise": _rows("noise", 11, per_day=2, planted=("f_rvol", "top", 1.15)), "orb30": _rows("orb30", 12, every=4),
              "otm_c_1100": _rows("otm", 13, every=6)}
    _write_trades(tmp_path / "h.csv.gz", hs, {k: [r for r in v if r["_src"] == "HIST"] for k, v in blocks.items()})
    _write_trades(tmp_path / "d.csv.gz", ds, {k: [r for r in v if r["_src"] == "DEV"] for k, v in blocks.items()})
    out = tmp_path / "out"
    args = ["--hist", str(tmp_path / "h.csv.gz"), "--dev", str(tmp_path / "d.csv.gz"), "--hist-spec", str(hs), "--dev-spec", str(ds),
            "--out", str(out), "--today", "2026-11-02", "--runs-csv", str(tmp_path / "none_*.csv")]
    assert sprint_factory.main(args) == 0
    md = (out / "factory_2026-11-02.md").read_text()
    js = json.loads((out / "factory_2026-11-02.json").read_text())
    res = js["result"]
    assert res["order"] == ["noise", "orb30", "otm_c_1100"]
    for i, n in enumerate(res["order"], 1):
        assert f"## {i}. {n}: verdict" in md
    assert "## The book: every survivor together" in md and "## Contrast: everything unfiltered" in md
    assert "mixed: modeled 2018-2024 + real 2024-2026" in md and "MODELED (BS, calibrated IV)" in md and "REAL" in md
    assert "Jan 2024 | MODELED" in md and "Aug-Dec 2024 | REAL" in md
    nz = res["strategies"]["noise"]
    assert nz["verdict"] != "none" and nz["rule"]["rule"]["feature"] == "f_rvol" and "noise" in res["survivors"]
    assert res["strategies"]["otm_c_1100"]["seen_before"] and res["strategies"]["orb30"]["model_check"] == factory.NOT_VALIDATED
    assert res["trials"]["new"] == 17 * 3 and set(res["unfiltered"]["windows"]["dev"]["plain"]["sleeves"]) == set(res["order"])
    assert res["trials"]["new_parts"] == {"runs": 6, "rules": 36, "learner": 9}
    assert factory.trial_parts(21) == {"runs": 42, "rules": 252, "learner": 63}             # Amendment 9's 357
    assert js["meta"]["run_ids"]["noise"] == {"HIST": "fx_hist-001", "DEV": "fx_dev-001"}
    # refusals: a trade inside L2, a HIST trade outside HIST, specs that differ
    bad = _rows("x", 14, every=50, src_only="DEV")
    _write_trades(tmp_path / "bad.csv.gz", ds, {k: [dict(bad[0], day="2024-03-01")] + bad for k in blocks})
    assert sprint_factory.main(args[:2] + ["--dev", str(tmp_path / "bad.csv.gz")] + args[4:]) == 2
    _write_trades(tmp_path / "bad2.csv.gz", hs, {k: [dict(r, day="2025-03-03") for r in bad[:2]] for k in blocks})
    assert sprint_factory.main(["--hist", str(tmp_path / "bad2.csv.gz")] + args[2:]) == 2
    other = json.loads(ds.read_text())
    other["blocks"] = other["blocks"][::-1]
    (tmp_path / "fx_dev2.json").write_text(json.dumps(other))
    assert sprint_factory.main(args[:6] + ["--dev-spec", str(tmp_path / "fx_dev2.json")] + args[8:]) == 2


def test_factory_code_has_no_order_path():
    for p in (ROOT / "sprint" / "factory.py", ROOT / "tools" / "sprint_factory.py"):
        src = p.read_text()
        for bad in ("paper-api", "/v2/orders", "/v2/positions", "import broker", "api.alpaca.markets", "urllib", "requests"):
            assert bad not in src, (p.name, bad)
