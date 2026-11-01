"""The final locked-period exam (SPRINT_PLAN Amendment 11, extending Amendment 7): the frozen spec, stage E1's models (FIN-L
equals holdout 2's L-call learner, FIN-HS equals round 8's B2 refit and tiers), each finalist's bar on unrounded numbers,
the verdicts, the one-shot log policy, the dirty-tree check, the guard's refusals before any request, the exam's engine
pass against engine.run_pass, and no look-ahead in the finalists' decisions. Synthetic data only: no L1/L2 data is read or
made up (the end-to-end run on a synthetic "locked" fixture is tests/test_sprint_exam_e2e.py)."""
import hashlib
import json
import math
import subprocess
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import book, data, engine, exam, features, periods, round8, shares
from sprint import spread as SP

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "sprint" / "specs"


# ---------------------------------------------------------------- shared helpers (also used by test_sprint_exam_e2e.py)
def synth_rows(days, run_id, src, seed=1, new7=True, syms=("SPY", "QQQ", "IWM")):
    """Synthetic 11:00-call trade rows (the trade-file columns the exam reads) with a weak edge on f_rvol and f_range_atr."""
    rng = np.random.default_rng(seed)
    rows = []
    for d in days:
        d = str(d)[:10]
        for sym in syms:
            f = {n: round(float(rng.normal()), 4) for n in features.FEATURES18}
            f.update(f_minute=90, f_weekday=date.fromisoformat(d).weekday(), f_rvol=round(float(rng.uniform(0.6, 1.8)), 2),
                     f_trend_votes=int(rng.integers(0, 5)), f_noise_true=int(rng.integers(0, 4)),
                     f_event=None if src == "HIST" else int(rng.random() < 0.1), f_vixy_pctl=round(float(rng.uniform(0, 1)), 4))
            if new7:
                f.update({n: round(float(rng.normal()), 4) for n in features.NEW7})
                f["f_hod"] = int(rng.random() < 0.3)
            win = rng.random() < 0.15 + 0.2 * (f["f_rvol"] >= 1.06) + 0.1 * math.tanh(f["f_range_atr"])
            pnl = float(rng.uniform(20, 400)) if win else -float(rng.uniform(4, 40))
            rows.append(dict(f, run_id=run_id, symbol=sym, day=d, setup="time_1100", side="C", signal_idx=89, entry_idx=90,
                             entry_time="11:00", contract=f"{sym}{d[2:4]}{d[5:7]}{d[8:10]}C00500000", pnl=round(pnl, 2),
                             pnl_2x=round(pnl - 1.3, 2), _src=src))
    return rows


def hist_days(step=9, skip=()):
    return [d for d in book.sessions_between("2016-01-04", "2024-01-31")[::step] if not any(a <= d <= b for a, b in skip)]


def dev_days(step=5, skip=()):
    return [d for d in book.sessions_between("2024-08-01", "2026-06-30")[::step] if not any(a <= d <= b for a, b in skip)]


def synth_models(skip=(), seed=3):
    """A models dict from exam.fit_models on synthetic HIST/DEV rows (the shape stage E1 writes)."""
    fl = synth_rows(hist_days(7, skip), exam.HIST_V1_RUN, "HIST", seed=seed, new7=False)
    fh = [r for r in synth_rows(hist_days(5, skip), exam.FACTORY_RUN["HIST"], "HIST", seed=seed + 1) if exam.rvol_ok(r)]
    fd = [r for r in synth_rows(dev_days(3, skip), exam.FACTORY_RUN["DEV"], "DEV", seed=seed + 2) if exam.rvol_ok(r)]
    src = {"which": "synthetic", "run_id": exam.HIST_V1_RUN, "files": [], "rows": len(fl)}
    return exam.fit_models(fl, src, fh, fd, [{"src": "HIST", "file": "synthetic"}, {"src": "DEV", "file": "synthetic"}],
                           {"fit_commit": "synthetic"})


def git(repo, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True, capture_output=True)


def make_repo(path, models, msha_override=None):
    """A git repository holding the exam spec (with the models sha256) and the models file, committed. Returns
    (repo, exam spec sha256, models sha256)."""
    path = Path(path)
    (path / "sprint" / "specs").mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    mtext = exam.models_text(models)
    (path / exam.MODELS_REL).write_text(mtext)
    msha = exam.sha256_bytes(mtext.encode())
    (path / exam.SPEC_REL).write_text(exam.spec_text(exam.canonical_spec(msha_override or msha)))
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "freeze")
    return path, periods.sha256_file(path / exam.SPEC_REL), msha


def opt_row(day, pnl, pnl2=None, sym="SPY", c=None):
    return {"symbol": sym, "day": day, "pnl": float(pnl), "pnl_2x": float(pnl if pnl2 is None else pnl2), "entry_idx": 90,
            "signal_idx": 89, "contract": c or f"{sym}C", "f_rvol": 1.2}


# ---------------------------------------------------------------- the frozen spec
def test_shipped_spec_is_the_canonical_amendment_11_spec():
    p = SPECS / "final_v2_exam.json"
    spec = json.loads(p.read_text())
    canon = exam.canonical_spec()
    frozen = spec["models"]["sha256"]
    if frozen != exam.PENDING:                                             # after `freeze`: the committed models file's sha256
        assert frozen == hashlib.sha256((SPECS / "final_v2_models.json").read_bytes()).hexdigest()
        canon["models"]["sha256"] = frozen
    assert p.read_text() == exam.spec_text(canon)                          # byte for byte: freeze changes only the models sha256
    assert exam.check_spec(spec) is None
    assert spec["models"] == {"path": "sprint/specs/final_v2_models.json", "sha256": frozen}
    assert {k: (v["from"], v["to"]) for k, v in spec["periods"].items()} == {"L2": ("2024-02-01", "2024-07-31"),
                                                                             "L1": ("2026-07-01", "2026-10-30")}
    assert spec["periods"]["L2"]["warm_source"] == "HIST" and spec["periods"]["L1"]["warm_source"] == "DEV"
    assert spec["bars"]["FIN-H"] == spec["bars"]["FIN-L"] == {"min_trades": {"L2": 30, "L1": 20}, "pf_at_least": 1.25,
                                                               "pf_2x_above": 1.0, "expectancy_above": "reference"}
    assert spec["bars"]["NB-VOL"] == {"min_trades": {"L2": 100, "L1": 60}, "expectancy_2x_above": 0.0, "random_direction_p_below": 0.1}
    assert spec["seeds"]["nbvol_random_direction"] == {"seeds": [31, 230], "draws": 200, "rng": "numpy default_rng(seed)"}
    assert spec["finalists"]["FIN-L"]["features"] == features.FEATURES18 and spec["finalists"]["FIN-L"]["take_if_p_win_at_least"] == 0.5
    assert spec["finalists"]["FIN-HS"]["features"] == features.FEATURES and len(features.FEATURES) == 25
    assert spec["costs"]["information_rerun_half_spread_pct"] == 0.05
    # L2's warm-up and VIXY daily range touch no other locked period; the warm-up itself touches none
    for k, pd_ in spec["periods"].items():
        a, b = date.fromisoformat(pd_["from"]), date.fromisoformat(pd_["to"])
        assert periods.overlaps(min(date.fromisoformat(pd_["warm_from"]), date.fromisoformat(pd_["vixy_daily_from"])), b) == [k]
        assert periods.overlaps(date.fromisoformat(pd_["warm_from"]), a - timedelta(days=1)) == []
        assert len(book.sessions_between(pd_["vixy_daily_from"], a - timedelta(days=1))) >= 252 + 21   # percentile + z20 history
        assert len(book.sessions_between(pd_["warm_from"], a - timedelta(days=1))) >= 21               # 20-session features


def test_warm_months_are_months_with_warm_up_sessions(tmp_path):
    assert exam.warm_months(date(2023, 12, 1), date(2024, 2, 1)) == ["2023-12", "2024-01"]           # L2: HIST's last two months
    assert exam.warm_months(date(2026, 5, 1), date(2026, 7, 1)) == ["2026-05", "2026-06"]            # L1: DEV's
    assert exam.warm_months(date(2025, 9, 2), date(2025, 11, 3)) == ["2025-09", "2025-10"]           # Nov 1-2 is a weekend: no file
    assert exam.warm_months(date(2026, 7, 1), date(2026, 7, 1)) == []
    (tmp_path / "stocks" / "SPY").mkdir(parents=True)
    (tmp_path / "stocks" / "SPY" / "2023-12.csv.gz").write_bytes(b"")
    assert exam.missing_warmup(tmp_path, date(2023, 12, 1), date(2024, 2, 1), ("SPY",)) == [("SPY", "2024-01")]


def test_check_spec_refuses_any_change_but_the_models_sha():
    spec = exam.canonical_spec("a" * 64)
    assert exam.check_spec(spec) is None
    for path, val in ((("bars", "FIN-H", "pf_at_least"), 1.2), (("periods", "L1", "to"), "2026-10-29"),
                      (("finalists", "FIN-L", "take_if_p_win_at_least"), 0.45), (("seeds", "nbvol_random_direction", "draws"), 100),
                      (("engine", "defaults", "fixed_stop"), 0.5), (("symbols",), ["SPY", "QQQ"])):
        s = json.loads(json.dumps(spec))
        cur = s
        for k in path[:-1]:
            cur = cur[k]
        cur[path[-1]] = val
        assert exam.check_spec(s) is not None, path
    assert exam.check_spec([]) is not None


def test_engine_runs_are_otm_v1_040_and_fin_h():
    runs = exam.engine_runs(exam.canonical_spec())
    key = lambda r: engine.run_key(r)
    ref = {s: {r["run_id"]: r for r in engine.expand(json.loads((SPECS / f"{s}.json").read_text()))}
           for s in ("otm_v1", "factory_dev_v1", "factory_hist_v1", "hist_v1")}
    k0 = key(runs["reference"])
    assert k0 == key(ref["otm_v1"]["otm_v1-040"]) == key(ref["factory_dev_v1"][exam.FACTORY_RUN["DEV"]])
    assert k0 == key(ref["factory_hist_v1"][exam.FACTORY_RUN["HIST"]]) == key(ref["hist_v1"][exam.HIST_V1_RUN])
    assert ref["factory_hist_v1"][exam.FACTORY_RUN["HIST"]]["block"] == "otm_c_1100"
    assert key(runs["fin_h"]) == key(dict(runs["reference"], filters=("rvol_ge106",)))
    assert runs["reference"]["exit"].contract == "d03-12t07" and runs["reference"]["entry"] == "time_1100"


# ---------------------------------------------------------------- stage E1: FIN-L and FIN-HS
def test_fin_l_equals_holdout_2s_l_call_learner():
    import sprint_regime
    hist = synth_rows(hist_days(11), exam.HIST_V1_RUN, "HIST", seed=5, new7=False)     # hist_v1-005 rows have no round-8 columns
    dev = pd.DataFrame(synth_rows(dev_days(4), "otm_v1-040", "DEV", seed=6))
    m = exam.fit_logit_model(hist, exam.FIN_L_FEATURES)
    take = exam.model_probs(m, dev.to_dict("records")) >= 0.5
    want = sprint_regime.learner_mask(hist, dev).to_numpy()
    assert 0 < take.sum() < len(take)
    assert (take == want).all()
    assert m["used_features"] == [n for n in features.FEATURES18 if n not in ("f_minute", "f_event")]   # constant / empty: dropped


def test_fin_hs_equals_round_8s_b2_refit_and_tiers():
    rows = synth_rows(book.sessions_between("2021-01-04", "2023-03-31")[::2], "x", "HIST", seed=7)
    rows = [r for r in rows if exam.rvol_ok(r)]
    sized, info = round8.b2_sizing(rows)
    tm = info["oos_from"]
    train = sorted([r for r in rows if r["day"][:7] < tm], key=lambda r: (r["day"], r["f_minute"]))
    test = sorted([r for r in rows if r["day"][:7] == tm], key=lambda r: (r["day"], r["f_minute"]))
    m = exam.fit_logit_model(train, exam.FIN_HS_FEATURES, cuts=True)
    c0 = info["cuts"][0]
    assert c0["month"] == tm and c0["train"] == len(train)
    assert m["cuts"]["lower"] == pytest.approx(c0["lower"], abs=1e-12) and m["cuts"]["upper"] == pytest.approx(c0["upper"], abs=1e-12)
    want = [r["contracts"] for r in sized if r["day"][:7] == tm]
    got = exam.contracts_for(exam.model_probs(m, test), m["cuts"]).tolist()
    assert got == want and set(got) <= {0, 1, 2}
    assert m["train_sizes"]["skip"] + m["train_sizes"]["one"] + m["train_sizes"]["two"] == len(train)


def test_fin_hs_tiers_bottom_checked_first():
    cuts = {"lower": 0.4, "upper": 0.6}
    assert exam.contracts_for([0.1, 0.4, 0.40001, 0.5, 0.59999, 0.6, 0.9], cuts).tolist() == [0, 0, 1, 1, 1, 2, 2]
    assert exam.contracts_for([0.5, 0.49, 0.51], {"lower": 0.5, "upper": 0.5}).tolist() == [0, 0, 2]   # equal cuts: skip wins


def test_fit_models_windows_sources_and_deterministic_bytes():
    m1, m2 = synth_models(), synth_models()
    assert exam.models_text(m1) == exam.models_text(m2)
    assert exam.check_models(m1) is None
    l2, l1 = m1["fin_hs"]["L2"], m1["fin_hs"]["L1"]
    assert (l2["train_through"], l1["train_through"]) == ("2024-01-31", "2026-06-30")
    assert l2["train_sources"] == ["HIST"] and l1["train_sources"] == ["HIST", "DEV"]
    assert l2["last_day"] <= "2024-01-31" and l1["last_day"] > "2024-08-01" and l1["rows"] > l2["rows"]
    assert m1["fin_l"]["features"] == features.FEATURES18 and m1["fin_l"]["threshold"] == 0.5
    for m in (l2, l1):
        p = exam.model_probs(m, synth_rows(dev_days(20), "x", "DEV", seed=11))
        assert ((p > 0) & (p < 1)).all()
    bad = json.loads(json.dumps(m1))
    bad["fin_hs"]["L1"]["train_through"] = "2026-07-01"
    assert exam.check_models(bad) is not None
    bad = json.loads(json.dumps(m1))
    bad["fin_l"]["features"] = features.FEATURES
    assert exam.check_models(bad) is not None


def test_e1_refuses_training_rows_inside_l1_or_l2():
    good = synth_rows(hist_days(30), "x", "HIST", seed=1)
    for d, src in (("2024-03-01", "DEV"), ("2026-08-03", "DEV"), ("2024-02-01", "HIST"), ("2026-10-30", None)):
        bad = good + [dict(good[0], day=d, _src=src)]
        assert "locked period" in exam.check_training_rows(bad)
        with pytest.raises(exam.ExamRefused, match="locked period"):
            exam.fit_logit_model(bad, exam.FIN_L_FEATURES)
    assert "outside DEV" in exam.check_training_rows(good + [dict(good[0], day="2024-01-10", _src="DEV")])
    assert exam.check_training_rows(good) is None


# ---------------------------------------------------------------- the bars (unrounded)
def _pf_rows(n, pf, pf2=None, day0="2024-02-01"):
    """n rows: one loss of -100, n-2 wins of 1.0 and one win of 100 x pf - (n - 2), so the wins sum to 100 x pf exactly in
    floating point for whole-dollar totals (pnl_2x: the same with PF pf2)."""
    pf2 = pf if pf2 is None else pf2
    days = book.sessions_between(day0, "2026-12-31")
    rows = [opt_row(days[0], -100.0, -100.0)] + [opt_row(days[k], 1.0, 1.0) for k in range(1, n - 1)]
    return rows + [opt_row(days[n - 1], 100.0 * pf - (n - 2), 100.0 * pf2 - (n - 2))]


def test_fin_bar_counts_pf_pf2x_and_reference():
    ref = [opt_row("2024-02-01", -5.0)] * 40
    assert exam.bar_fin("FIN-H", _pf_rows(30, 1.25, 1.01), ref, "L2")["pass"]
    assert not exam.bar_fin("FIN-H", _pf_rows(29, 2.0), ref, "L2")["pass"]                    # 30 needed on L2
    assert exam.bar_fin("FIN-H", _pf_rows(20, 2.0), ref, "L1")["pass"]                        # 20 on L1
    assert not exam.bar_fin("FIN-H", _pf_rows(19, 2.0), ref, "L1")["pass"]
    near = exam.bar_fin("FIN-H", _pf_rows(30, 1.2496), ref, "L2")
    assert not near["pass"] and near["exact"]["pf"] < 1.25 and round(near["exact"]["pf"], 3) == 1.25   # unrounded
    assert not exam.bar_fin("FIN-H", _pf_rows(30, 2.0, 1.0), ref, "L2")["pass"]               # PF 2x must be ABOVE 1.0
    rows = _pf_rows(30, 2.0)
    e = float(np.mean([r["pnl"] for r in rows]))
    assert not exam.bar_fin("FIN-H", rows, [opt_row("2024-02-01", e)], "L2")["pass"]         # equal expectancy: not above
    assert exam.bar_fin("FIN-H", rows, [opt_row("2024-02-01", e - 1e-9)], "L2")["pass"]
    assert not exam.bar_fin("FIN-L", [], ref, "L2")["pass"]
    allwin = [opt_row("2024-02-01", 5.0)] * 30
    assert exam.bar_fin("FIN-L", allwin, ref, "L2")["exact"]["pf"] == math.inf and exam.bar_fin("FIN-L", allwin, ref, "L2")["pass"]


def test_fin_hs_bar_counts_fin_h_trades_and_compares_per_contract():
    finh = _pf_rows(30, 1.5)
    sizes = [0] * 10 + [1] * 10 + [2] * 10
    v = exam.bar_fin_hs(finh, sizes, "L2")
    assert v["fin_h_trades"] == 30 and v["contracts"] == 30 and v["skipped"] == 10 and v["doubled"] == 10
    sized = exam.sized_rows(finh, sizes)
    assert len(sized) == 20 and v["exact"]["pnl_per_contract"] == pytest.approx(sum(r["pnl"] for r in sized) / 30)
    assert v["checks"][0][1]                                                                 # 30 FIN-H trades, 10 sized to 0
    # the loss (row 0) is skipped: sized PF is inf, per contract above FIN-H's
    assert v["exact"]["pf"] == math.inf and v["pass"]
    v = exam.bar_fin_hs(finh, [2] + [1] * 29, "L2")                                           # doubling the loser: worse per contract
    assert v["exact"]["pnl_per_contract"] < v["exact"]["fin_h_expectancy"] and not v["pass"]
    v = exam.bar_fin_hs(finh, [1] * 30, "L2")                                                 # flat sizing: equal, not above
    assert v["exact"]["pnl_per_contract"] == pytest.approx(v["exact"]["fin_h_expectancy"]) and not v["checks"][3][1]
    assert not exam.bar_fin_hs(_pf_rows(19, 3.0), [1] * 19, "L1")["pass"]
    assert not exam.bar_fin_hs(finh, [0] * 30, "L2")["pass"]
    with pytest.raises(ValueError):
        exam.bar_fin_hs(finh, [1] * 29, "L2")


def _share(day, sign, move, shares_=10, sym="SPY", k=0):
    pnl = shares_ * (sign * move - 0.02)
    return {"variant": "noise_sh_vol", "symbol": sym, "day": day, "sign": sign, "side": "L" if sign > 0 else "S", "entry_idx": 30 + k,
            "exit_idx": 389, "shares": shares_, "move": move, "pnl": round(pnl, 4), "pnl_2x": round(shares_ * (sign * move - 0.04), 4),
            "bps": 1.0}


def test_nbvol_bar_random_direction_p_and_counts():
    days = book.sessions_between("2024-02-01", "2024-07-31")
    rng = np.random.default_rng(0)
    good = [_share(days[k % len(days)], s, s * float(rng.uniform(0.2, 1.0)), k=k) for k, s in
            enumerate(rng.choice([-1, 1], 120))]                                             # always on the right side
    v = exam.bar_nbvol(good, "L2")
    assert v["random_direction"]["p"] == 0.0 and v["random_direction"]["draws"] == 200 and v["pass"]
    assert v["random_direction"]["seeds"] == [31, 230]
    assert not exam.bar_nbvol(good[:99], "L2")["pass"] and exam.bar_nbvol(good[:60], "L1")["pass"]
    assert not exam.bar_nbvol(good[:59], "L1")["pass"]
    bad = [dict(t, pnl=round(t["shares"] * (-abs(t["move"]) - 0.02), 4), pnl_2x=round(t["shares"] * (-abs(t["move"]) - 0.04), 4),
                move=-t["sign"] * abs(t["move"])) for t in good]                             # always on the wrong side
    vb = exam.bar_nbvol(bad, "L2")
    assert vb["random_direction"]["p"] == 1.0 and not vb["pass"]
    p, _ = shares.random_direction(good, exam.RANDOM_SEEDS)
    assert p == v["random_direction"]["p"] and exam.RANDOM_SEEDS == tuple(range(31, 231))
    tiny = [_share(days[k], 1, 0.03, k=k) for k in range(120)]                               # +$0.10 base, -$0.10 at 2x costs
    vt = exam.bar_nbvol(tiny, "L2")
    assert vt["exact"]["expectancy_2x"] < 0 and not vt["checks"][1][1]


def test_verdicts_and_void():
    assert exam.verdict({"L2": True, "L1": True}) == "holds"
    assert exam.verdict({"L2": True, "L1": False}) == "mixed" == exam.verdict({"L2": False, "L1": True})
    assert exam.verdict({"L2": False, "L1": False}) == "fails"
    assert exam.verdict({"L2": True, "L1": None}).startswith("pending")
    mk = lambda ok, void=None: {"finalists": {f: {"pass": ok, "void": void} for f in exam.FINALISTS}}
    c = exam.combined({"L2": mk(True), "L1": mk(False)})
    assert all(c[f]["verdict"] == "mixed" for f in exam.FINALISTS)
    c = exam.combined({"L2": mk(True), "L1": mk(True, "code changed")})
    assert all(c[f]["verdict"] == "VOID (L1)" for f in exam.FINALISTS)
    assert exam.combined({"L2": mk(True), "L1": None})["FIN-H"]["verdict"].startswith("pending")


# ---------------------------------------------------------------- one shot: the log policy, the dirty tree
def test_log_policy_one_shot_rerun_and_void(tmp_path):
    repo = tmp_path / "r"
    (repo / "sprint").mkdir(parents=True)
    git(repo, "init", "-q")
    (repo / "sprint" / "a.py").write_text("x = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "a")
    c1 = exam.head_commit(repo)
    assert exam.log_policy([], "L2", "s" * 64, c1, repo) == ("first", None)
    log = [{"event": "start", "period": "L2", "spec_sha": "s" * 64, "commit": c1, "at": "t"}]
    assert exam.log_policy(log, "L2", "s" * 64, c1, repo) == ("rerun", None)
    with pytest.raises(exam.ExamRefused, match="already read"):
        exam.log_policy(log, "L2", "t" * 64, c1, repo)
    with pytest.raises(exam.ExamRefused, match="same frozen spec"):
        exam.log_policy(log, "L1", "t" * 64, c1, repo)
    (repo / "docs").mkdir()
    (repo / "docs" / "notes.md").write_text("results\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "docs")
    c2 = exam.head_commit(repo)
    assert exam.log_policy(log, "L1", "s" * 64, c2, repo) == ("first", None)                  # docs only: not void
    with pytest.raises(exam.ExamRefused, match="already read"):
        exam.log_policy(log, "L2", "s" * 64, c2, repo)                                        # a period already read: same commit only
    (repo / "sprint" / "a.py").write_text("x = 2\n")
    git(repo, "commit", "-q", "-am", "code")
    kind, void = exam.log_policy(log, "L1", "s" * 64, exam.head_commit(repo), repo)
    assert kind == "first" and "VOID" in void and "sprint/a.py" in void and "notes.md" not in void
    assert exam.code_changes(["docs/x.md", "README.md", "sprint/exam.py", "sprint/specs/a.json"]) == ["sprint/exam.py", "sprint/specs/a.json"]


def test_dirty_reason(tmp_path):
    repo = tmp_path / "r"
    for d in ("sprint", "tools", "tests", "docs"):
        (repo / d).mkdir(parents=True)
    git(repo, "init", "-q")
    (repo / "sprint" / "a.py").write_text("x = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "a")
    assert exam.dirty_reason(repo) is None
    (repo / "notes.txt").write_text("n")                    # untracked, not code
    (repo / "docs" / "x.py").write_text("n")                # untracked .py outside the code folders and below the top level
    (repo / ".venv" / "lib").mkdir(parents=True)
    (repo / ".venv" / "lib" / "site.py").write_text("n")    # the sprint's Python environment (not ignored by .gitignore)
    assert exam.dirty_reason(repo) is None
    (repo / "stray.py").write_text("n")
    assert "stray.py" in exam.dirty_reason(repo)
    (repo / "stray.py").unlink()
    (repo / "tools" / "new.py").write_text("n")
    assert "tools/new.py" in exam.dirty_reason(repo)
    assert exam.dirty_reason(repo, ignore=["tools/new.py"]) is None
    (repo / "tools" / "new.py").unlink()
    (repo / "sprint" / "a.py").write_text("x = 2\n")
    assert "sprint/a.py" in exam.dirty_reason(repo)
    git(repo, "add", "sprint/a.py")
    assert "sprint/a.py" in exam.dirty_reason(repo)         # staged, not committed
    assert exam.is_tracked(repo / "sprint" / "a.py") and not exam.is_tracked(repo / "notes.txt")
    assert not exam.is_tracked(tmp_path / "elsewhere.json")


# ---------------------------------------------------------------- the guard: every refusal before any request
@pytest.fixture
def frozen_repo(tmp_path, monkeypatch):
    import pull_alpaca as PA

    def boom(*a, **k):
        raise AssertionError("no request may be made before every check passed")
    monkeypatch.setattr(PA, "_http", boom)
    models = synth_models()
    repo, ssha, msha = make_repo(tmp_path / "repo", models)
    main = tmp_path / "alpaca"
    for sym in ("SPY", "QQQ", "IWM"):
        for m in ("2023-12", "2024-01", "2026-05", "2026-06"):
            (main / "stocks" / sym).mkdir(parents=True, exist_ok=True)
            (main / "stocks" / sym / f"{m}.csv.gz").write_bytes(b"")
    monkeypatch.setenv("ALPACA_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET", "s")
    return {"repo": repo, "ssha": ssha, "msha": msha, "main": main, "models": models, "tmp": tmp_path}


def _run(fx, locked="L2", frozen=None, **kw):
    import sprint_exam as T
    args = dict(main_root=fx["main"], exam_base=fx["tmp"] / "exam", out_dir=fx["tmp"] / "out", repo=fx["repo"], today="2026-11-01",
                log=lambda s: None)
    args.update(kw)
    return T.run_exam(None, locked, fx["ssha"] if frozen is None else frozen, **args)


def test_guard_refuses_without_frozen_wrong_sha_or_bad_locked(frozen_repo):
    fx = frozen_repo
    with pytest.raises(exam.ExamRefused, match="--frozen"):
        _run(fx, frozen="")
    with pytest.raises(periods.LockedPeriod, match="not the frozen"):
        _run(fx, frozen="0" * 64)
    with pytest.raises(periods.LockedPeriod, match="64 hex"):
        _run(fx, frozen=fx["ssha"][:12])
    for bad in (None, "", "L3", "L1,L2", "HIST"):
        with pytest.raises(exam.ExamRefused, match="exactly one period"):
            _run(fx, locked=bad)
    assert not (fx["tmp"] / "out" / "exam_log.jsonl").exists() and not (fx["tmp"] / "exam").exists()


def test_guard_refuses_a_dirty_tree_and_an_uncommitted_spec(frozen_repo):
    fx = frozen_repo
    (fx["repo"] / "sprint" / "x.py").write_text("print(1)\n")                 # untracked code
    with pytest.raises(exam.ExamRefused, match="dirty"):
        _run(fx)
    (fx["repo"] / "sprint" / "x.py").unlink()
    (fx["repo"] / "README.md").write_text("a\n")
    git(fx["repo"], "add", "README.md")
    git(fx["repo"], "commit", "-q", "-m", "readme")
    (fx["repo"] / "README.md").write_text("b\n")                              # a tracked file edited
    with pytest.raises(exam.ExamRefused, match="dirty"):
        _run(fx)
    git(fx["repo"], "checkout", "-q", "README.md")
    spec = fx["repo"] / exam.SPEC_REL
    spec.write_text(spec.read_text() + " ")                                   # the spec edited after the commit
    with pytest.raises(periods.LockedPeriod, match="not frozen"):
        _run(fx, frozen=periods.sha256_file(spec))


def test_guard_refuses_a_models_sha_mismatch_or_pending(frozen_repo, tmp_path):
    fx = frozen_repo
    mp = fx["repo"] / exam.MODELS_REL
    m = json.loads(mp.read_text())
    m["fin_l"]["b"] += 0.5
    mp.write_text(exam.models_text(m))
    git(fx["repo"], "commit", "-q", "-am", "models changed, spec not re-frozen")
    with pytest.raises(exam.ExamRefused, match="models file is not the frozen one"):
        _run(fx)
    repo2, ssha2, _ = make_repo(tmp_path / "repo2", fx["models"], msha_override=exam.PENDING)
    with pytest.raises(exam.ExamRefused, match="no models sha256"):
        _run(dict(fx, repo=repo2, ssha=ssha2))


def test_guard_refuses_missing_keys_missing_warmup_and_a_deleted_log(frozen_repo, monkeypatch):
    fx = frozen_repo
    monkeypatch.delenv("ALPACA_SECRET")
    with pytest.raises(exam.ExamRefused, match="ALPACA_KEY / ALPACA_SECRET"):
        _run(fx)
    monkeypatch.setenv("ALPACA_SECRET", "s")
    (fx["main"] / "stocks" / "QQQ" / "2026-05.csv.gz").unlink()
    with pytest.raises(exam.ExamRefused, match="warm-up month files missing"):
        _run(fx, locked="L1")
    stale = fx["tmp"] / "exam" / "L2" / "stocks" / "SPY"
    stale.mkdir(parents=True)
    (stale / "2024-02.csv.gz").write_bytes(b"x")
    with pytest.raises(exam.ExamRefused, match="records no L2 run"):
        _run(fx)
    assert not (fx["tmp"] / "out" / "exam_log.jsonl").exists()


def test_fit_refuses_after_a_locked_read_and_over_a_tracked_models_file(tmp_path, capsys):
    import sprint_exam as T
    out = tmp_path / "out"
    out.mkdir()
    exam.append_log(out / "exam_log.jsonl", {"event": "start", "period": "L2", "at": "t"})
    assert T.main(["fit", "--out", str(out), "--exam-data", str(tmp_path / "ex"), "--models", str(tmp_path / "m.json")]) == 2
    assert "BEFORE any L1/L2 pull" in capsys.readouterr().err
    out2 = tmp_path / "out2"
    (tmp_path / "ex2" / "L1" / "daily").mkdir(parents=True)
    (tmp_path / "ex2" / "L1" / "daily" / "VIXY.csv.gz").write_bytes(b"x")
    assert T.main(["fit", "--out", str(out2), "--exam-data", str(tmp_path / "ex2"), "--models", str(tmp_path / "m.json")]) == 2
    assert "already holds locked-period data" in capsys.readouterr().err
    repo, _, _ = make_repo(tmp_path / "repo", synth_models())
    assert T.main(["fit", "--out", str(tmp_path / "o3"), "--exam-data", str(tmp_path / "ex3"),
                   "--models", str(repo / exam.MODELS_REL)]) == 2
    assert "already committed" in capsys.readouterr().err


# ---------------------------------------------------------------- the engine pass, no look-ahead
@pytest.fixture(scope="module")
def dev_cache(tmp_path_factory):
    root = tmp_path_factory.mktemp("exam_cache")
    days = SS.weekdays(date(2025, 3, 3), 22)
    SS.write_cache(root, "SPY", days, px0=500.0, seed=21)
    SS.write_cache(root, "IWM", days, px0=200.0, seed=41)
    SS.write_daily(root, "VIXY", date(2024, 1, 1), date(2025, 4, 30))
    return root, days


def _exam_runs(syms=("SPY", "IWM")):
    spec = exam.canonical_spec()
    spec["engine"] = dict(spec["engine"], symbols=list(syms))
    runs = exam.engine_runs(spec)
    return [runs["reference"], runs["fin_h"]]


def test_engine_pass_equals_engine_run_pass(dev_cache):
    root, days = dev_cache
    runs = _exam_runs()
    a, b = days[15], days[-1]
    want, ws = engine.run_pass(runs, a, b, root, SP.SpreadModel(), warm_from=days[0])
    series = {s: data.Series(s, data.read_stock(s, days[0], b, root)) for s in ("SPY", "IWM")}
    got, gs = exam.engine_pass(runs, series, a, b, root, SP.SpreadModel(), {"VIXY_D": data.read_daily("VIXY", root)})
    assert ws == gs
    js = lambda x: json.dumps(x, sort_keys=True, default=str)          # NaN-safe equality
    for r in runs:
        rid = r["run_id"]
        assert js(got[rid]["trades"]) == js(want[rid]["trades"]) and got[rid]["signals"] == want[rid]["signals"]
        assert dict(got[rid]["skips"]) == dict(want[rid]["skips"])
        assert js([{k: x.get(k) for k in engine.LEAN} for x in got[rid]["rows"]]) == js(got[rid]["trades"])
    ref, fh = runs[0]["run_id"], runs[1]["run_id"]
    assert got[ref]["trades"], "the synthetic days must produce reference trades"
    chk = exam.finh_consistency(got[ref]["rows"], got[fh]["rows"])
    assert chk["match"] and chk["fin_h_run"] == sum(1 for t in got[ref]["rows"] if exam.rvol_ok(t))
    with pytest.raises(ValueError):
        exam.engine_pass([dict(runs[0], fake_seed=1)], series, a, b, root, SP.SpreadModel(), {})


def test_finalists_decisions_do_not_look_ahead(dev_cache, tmp_path):
    """Changing every stock and option bar after the decision (from 11:02 on) changes no entry feature, so no FIN-L or FIN-HS
    decision (P/L may change)."""
    import shutil
    import pull_alpaca as PA
    src, days = dev_cache
    root = tmp_path / "c"
    shutil.copytree(src, root)
    runs = _exam_runs(("SPY",))
    models = synth_models()
    aux = {"VIXY_D": data.read_daily("VIXY", root)}

    def run(a, b):
        s = {"SPY": data.Series("SPY", data.read_stock("SPY", days[0], b, root))}
        res, _ = exam.engine_pass(runs, s, a, b, root, SP.SpreadModel(), aux)
        return res[runs[0]["run_id"]]["rows"]
    traded = run(days[15], days[-1])
    assert traded, "the synthetic days must produce reference trades"
    day = date.fromisoformat(traded[-1]["day"])
    before = run(day, day)
    assert len(before) == 1
    mf = root / "stocks" / "SPY" / f"{day:%Y-%m}.csv.gz"
    df = PA.read_gz(mf)
    late = (df["ts"].dt.date == day) & ((df["ts"].dt.hour * 60 + df["ts"].dt.minute) >= 570 + 92)
    for c in ("o", "h", "l", "c"):
        df.loc[late, c] = df.loc[late, c] * 1.004
    PA._write_gz(mf, df)
    of = root / "options" / "SPY" / day.isoformat() / "bars.csv.gz"
    ob = PA.read_gz(of)
    lo = (ob["ts"].dt.hour * 60 + ob["ts"].dt.minute) >= 570 + 92
    for c in ("o", "h", "l", "c"):
        ob.loc[lo, c] = (ob.loc[lo, c] * 3.0).round(2)
    PA._write_gz(of, ob)
    after = run(day, day)
    assert len(after) == 1
    f0 = {k: before[0][k] for k in features.FEATURES}
    assert f0 == {k: after[0][k] for k in features.FEATURES}
    assert before[0]["contract"] == after[0]["contract"] and before[0]["pnl"] != after[0]["pnl"]
    for m in (models["fin_l"], models["fin_hs"]["L1"]):
        assert exam.model_probs(m, before).tolist() == exam.model_probs(m, after).tolist()


def test_evaluate_and_render_on_synthetic_rows():
    """evaluate() is pure: on synthetic option and share rows it applies every bar, the FIN-L / FIN-HS models and the
    breakdowns, and the report carries the labels."""
    models = synth_models()
    days = book.sessions_between("2026-07-01", "2026-10-30")
    rng = np.random.default_rng(4)
    ref = []
    for k, d in enumerate(days):
        for sym in ("SPY", "QQQ"):
            r = synth_rows([d], "ref", "L1", seed=k * 7 + len(sym), syms=(sym,))[0]
            r.update(entry_idx=90, exit_idx=355, signal_idx=89)
            ref.append(r)
    finh = [r for r in ref if exam.rvol_ok(r)]
    nb = [_share(days[k % len(days)], s, s * float(rng.uniform(-0.5, 1.0)), sym=("SPY", "IWM")[k % 2], k=k)
          for k, s in enumerate(rng.choice([-1, 1], 90))]
    out = exam.evaluate("L1", ref, finh, models, nb, days[0], days[-1], ref, finh, None)
    f = out["finalists"]
    assert out["fin_h_check"]["match"]
    assert f["FIN-H"]["stats"]["trades"] == len(finh) and f["FIN-L"]["taken"] + f["FIN-L"]["skipped"] == len(ref)
    assert f["FIN-HS"]["fin_h_trades"] == len(finh) and f["FIN-HS"]["skipped"] + f["FIN-HS"]["one"] + f["FIN-HS"]["doubled"] == len(finh)
    assert set(f["FIN-H"]["stats"]["by_symbol"]) == {"SPY", "QQQ"} and len(f["FIN-H"]["stats"]["by_month"]) == 4
    assert f["NB-VOL"]["stats"]["trades"] == 90 and "without_best_day" in f["NB-VOL"]["stats"]
    assert out["info_5pct"]["FIN-H"]["trades"] == len(finh)
    for v in f.values():
        assert v["period_pass"] == v["pass"] and v["void"] is None
    md = exam.render(out, {"kind": "first", "commit": "c", "combined": exam.combined({"L1": out, "L2": None})})
    assert "BACKTEST on the locked period L1" in md and "Information only: 5% half-spread rerun" in md and "pending" in md
    j = json.dumps(exam.clean(out))
    assert "NaN" not in j
    void = exam.evaluate("L1", ref, finh, models, nb, days[0], days[-1], void="code changed")
    assert all(v["period_pass"] is None and v["void"] == "code changed" for v in void["finalists"].values())
