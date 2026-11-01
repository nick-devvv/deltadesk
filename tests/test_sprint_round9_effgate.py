"""Part E, the pre-open predicted-efficiency gate (SPRINT_PLAN Amendment 14, sprint/effgate.py): the daily ER label, every
pre-open input's no look-ahead (changing that day's or later bars, or VIXY's closes from that day on, never changes it), the
monthly walk-forward using only earlier sessions (24 months minimum, out of sample from 2018-01), the gate's tercile, the
random whole-day skips' determinism (seeds 31-230), the pass bar, and tools/sprint_round9.py --parts E end to end on synthetic
bars and trade files. Synthetic data only."""
import gzip
import json
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

import sprint_synth  # noqa: F401  (puts the repo and tools/ on sys.path)
import sprint_round9 as T9
from sprint import book, effgate as EG, learn, round9 as R9

N = 390


# ---------------------------------------------------------------- synthetic bars
class Stub:
    """The two attributes effgate reads from a data.Series."""

    def __init__(self, days, rth):
        self.days, self.rth = list(days), dict(rth)


def grid_from_closes(c, o0=None, vol=1000.0):
    c = np.asarray(c, float)
    g = np.full((N, 5), np.nan)
    n = len(c)
    o = np.concatenate([[c[0] if o0 is None else o0], c[:-1]])
    g[:n, 0], g[:n, 3] = o, c
    g[:n, 1], g[:n, 2] = np.maximum(o, c) + 0.01, np.minimum(o, c) - 0.01
    g[:n, 4] = vol
    return g


def random_grids(days, seed, px0=100.0):
    rng = np.random.default_rng(seed)
    out, px = {}, px0
    for d in days:
        drift = rng.normal(0, 0.0004)
        r = rng.normal(drift, 0.0008, N)
        c = px * np.exp(np.cumsum(r))
        g = grid_from_closes(c, o0=px * (1 + rng.normal(0, 0.002)), vol=float(rng.integers(500, 5000)))
        g[:, 4] = rng.integers(500, 5000, N)
        out[d] = g
        px = float(c[-1])
    return out


def vixy_series(a, b, seed=3):
    days = [date.fromisoformat(d) for d in book.sessions_between(a, b)]
    rng = np.random.default_rng(seed)
    return pd.Series(20 * np.exp(np.cumsum(rng.normal(0, 0.03, len(days)))), index=days)


# ---------------------------------------------------------------- the ER label
def test_er_of_one_session_by_hand():
    g = grid_from_closes([100.0, 101.0, 100.0, 102.0], o0=99.0)
    # |102 - 99| / (|101-100| + |100-101| + |102-100|) = 3 / 4
    assert EG.day_er(g) == pytest.approx(0.75)
    g2 = g.copy()
    g2[1] = np.nan                                                   # a missing minute joins its neighbours
    assert EG.day_er(g2) == pytest.approx(3 / 2)                     # |102-99| / (|100-100| + |102-100|)
    early = np.full((N, 5), np.nan)                                  # an early close: the last bar is 12:59
    early[:210] = grid_from_closes(np.linspace(100, 101, 210))[:210]
    assert EG.day_er(early) == pytest.approx(1.0)
    assert EG.day_er(grid_from_closes([100.0])) is None              # fewer than 2 bars
    assert EG.day_er(grid_from_closes([100.0, 100.0, 100.0])) is None   # no movement
    s = EG.day_summary(grid_from_closes(np.r_[np.full(329, 100.0), np.linspace(100, 101, 61)]))
    assert s["last_hour"] == pytest.approx(1.0)                      # 15:59 close vs the 14:59 close (the price at 15:00)


def _rows_for_label(seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for d in book.sessions_between("2016-01-04", "2018-02-28"):
        for sym, scale in (("SPY", 0.2), ("QQQ", 0.5)):
            r = {"symbol": sym, "day": d, "seg": "HIST", "er": float(rng.uniform(0, scale)), "_p5": rng.uniform(0, scale, 5)}
            r.update({k: float(rng.normal()) for k in EG.STATIC})
            rows.append(r)
    return rows


def test_label_is_the_top_tercile_of_the_training_window_per_symbol():
    rows = _rows_for_label()
    A = EG._arrays(rows)
    f = EG.fit_month(A, "2018-02")
    tr = f["train"]
    assert tr.sum() == sum(1 for r in rows if r["day"] < "2018-02-01")
    for sym in ("SPY", "QQQ"):
        m = tr & (A["sym"] == sym)
        cut = np.quantile(A["er"][m], 2 / 3)
        assert f["thr"][sym] == pytest.approx(cut)
        assert np.array_equal(f["y"][m], (A["er"][m] >= cut).astype(float))
        assert abs(f["y"][m].mean() - 1 / 3) < 0.01
    assert f["thr"]["QQQ"] > 2 * f["thr"]["SPY"]                     # per symbol, not pooled
    # e_top5 counts the prior 5 sessions' ERs at or above the refit's per-symbol cut
    i = int(np.where(f["test"] & (A["sym"] == "SPY"))[0][0])
    assert f["top5"][i] == (np.asarray(rows[i]["_p5"]) >= f["thr"]["SPY"]).sum()


# ---------------------------------------------------------------- no look-ahead, per input
@pytest.fixture(scope="module")
def seg():
    days = [date.fromisoformat(d) for d in book.sessions_between("2015-11-02", "2017-03-31")]
    grids = random_grids(days, 7)
    vx = vixy_series("2014-11-03", "2017-12-29")
    return days, grids, vx


def _build(days, grids, vx):
    return EG.build_rows({("HIST", "SPY"): Stub(days, grids)}, vx, symbols=("SPY",))


@pytest.mark.parametrize("feature", list(EG.STATIC) + ["_p5"])
def test_each_input_ignores_that_day_and_later(seg, feature):
    days, grids, vx = seg
    base = {r["day"]: r for r in _build(days, grids, vx)}
    rng = np.random.default_rng(11)
    for k in (60, 200, len(days) - 3):
        d = days[k]
        g2 = dict(grids)
        for j in range(k, len(days)):                                 # day t and every later day changed
            g2[days[j]] = g2[days[j]] * np.r_[rng.uniform(0.5, 1.5, 4), 3.0][None, :]
        vx2 = vx.copy()
        vx2[vx2.index >= d] = vx2[vx2.index >= d] * 5.0               # VIXY's close on day t and later changed
        new = {r["day"]: r for r in _build(days, g2, vx2)}
        a, b = base[d.isoformat()][feature], new[d.isoformat()][feature]
        if feature == "_p5":
            assert np.array_equal(a, b, equal_nan=True)
        else:
            assert a == b, (feature, d)
        assert base[d.isoformat()]["er"] != new[d.isoformat()]["er"]   # the label did change
    if feature not in ("e_event",):                                   # the calendar doesn't cover 2016-2017
        assert base[days[200].isoformat()][feature] is not None


def test_top5_ignores_that_day_and_later(seg):
    days, grids, vx = seg
    rows = _build(days, grids, vx)
    k = next(i for i, r in enumerate(rows) if r["day"] >= "2017-03-01")
    g2 = dict(grids)
    for j in range(days.index(date.fromisoformat(rows[k]["day"])), len(days)):
        g2[days[j]] = g2[days[j]] * 2.0 + 1.0
    rows2 = _build(days, g2, vx)
    f1, f2 = EG.fit_month(EG._arrays(rows), "2017-03"), EG.fit_month(EG._arrays(rows2), "2017-03")
    assert f1["top5"][k] == f2["top5"][k] and not math.isnan(f1["top5"][k])
    assert f1["cut"] == f2["cut"] and np.allclose(f1["w"], f2["w"])


def test_features_never_cross_l2():
    days_h = [date.fromisoformat(d) for d in book.sessions_between("2023-10-02", "2024-01-31")]
    days_d = [date.fromisoformat(d) for d in book.sessions_between("2024-08-01", "2024-09-30")]
    ser = {("HIST", "SPY"): Stub(days_h, random_grids(days_h, 1)), ("DEV", "SPY"): Stub(days_d, random_grids(days_d, 2))}
    vx = vixy_series("2014-11-03", "2026-06-30")
    vx = vx[[not (date(2024, 2, 1) <= d <= date(2024, 7, 31)) for d in vx.index]]
    rows = [r for r in EG.build_rows(ser, vx, symbols=("SPY",)) if r["seg"] == "DEV"]
    first = rows[0]
    assert first["day"] == "2024-08-01" and all(first[k] is None for k in EG.STATIC if k not in ("e_weekday", "e_event"))
    assert rows[1]["e_prev_er"] is not None and rows[1]["e_vixy_chg1"] is None    # VIXY's change never spans the L2 gap
    assert all(r["e_vixy_pctl"] is None for r in rows)                            # 252 DEV closes not yet there
    assert all(r["e_ret20"] is None for r in rows[:21]) and rows[21]["e_ret20"] is not None


# ---------------------------------------------------------------- the walk-forward
def test_walk_forward_starts_2018_01_and_uses_only_earlier_sessions():
    rows = _rows_for_label(5)
    wf = EG.walk_forward(rows)
    assert wf["oos_from"] == "2018-01" and [f["month"] for f in wf["fits"]] == ["2018-01", "2018-02"]
    assert wf["fits"][0]["train_months"] == 24 and wf["fits"][0]["train_rows"] == sum(1 for r in rows if r["day"] < "2018-01-01")
    assert {d["month"] for d in wf["decisions"]} == {"2018-01", "2018-02"}
    # change every label of 2018-02 and every input after 2018-02-01: January's decisions and February's refit stay
    rows2 = [dict(r) for r in rows]
    rng = np.random.default_rng(9)
    for r in rows2:
        if r["day"] >= "2018-02-01":
            r["er"] = float(rng.uniform(0, 1))
        if r["day"] > "2018-02-01":
            r.update({k: float(rng.normal(5, 3)) for k in EG.STATIC})
    wf2 = EG.walk_forward(rows2)
    jan = lambda w: [d for d in w["decisions"] if d["month"] == "2018-01"]
    assert jan(wf) == jan(wf2)
    assert wf["fits"][1]["gate_cut"] == wf2["fits"][1]["gate_cut"] and wf["fits"][1]["label_cuts"] == wf2["fits"][1]["label_cuts"]
    first_feb = lambda w: [{k: v for k, v in d.items() if k != "er"} for d in w["decisions"] if d["day"] == "2018-02-01"]
    assert first_feb(wf) == first_feb(wf2) and len(first_feb(wf)) == 2
    # fewer than 24 months of earlier sessions: no refit (2016-03..2018-01 is 23 months before 2018-02)
    late = EG.walk_forward([r for r in rows if r["day"] >= "2016-03-01"])
    assert late["fits"] == [] and late["oos_from"] is None and "24 calendar months" in late["error"]


def test_walk_forward_uses_learn_preprocessing_and_fit():
    rows = _rows_for_label(2)
    A = EG._arrays(rows)
    f = EG.fit_month(A, "2018-01")
    tr = f["train"]
    X = np.hstack([A["X"], f["top5"][:, None]])
    p = learn._prep_fit(X[tr])
    w, b = learn.fit_logit(learn._prep_apply(p, X[tr]), f["y"][tr], lam=1.0)
    assert np.allclose(w, f["w"]) and b == pytest.approx(f["b"])


# ---------------------------------------------------------------- the gate tercile
def test_gate_skips_the_bottom_tercile_of_the_refits_training_predictions():
    rows = _rows_for_label(3)
    A = EG._arrays(rows)
    f = EG.fit_month(A, "2018-02")
    assert f["cut"] == pytest.approx(np.quantile(f["ptr"], 1 / 3))
    assert abs((f["ptr"] <= f["cut"]).mean() - 1 / 3) <= 1.0 / len(f["ptr"]) + 1e-12
    assert np.array_equal(f["skip"], f["pte"] <= f["cut"])
    wf = EG.walk_forward(rows)
    for d in wf["decisions"]:
        assert d["skip"] == (d["p"] <= d["cut"])
    assert 0 < sum(d["skip"] for d in wf["decisions"]) < len(wf["decisions"])


def test_gate_window_drops_trades_on_skipped_symbol_days_only():
    gate = {("SPY", "2024-08-01"): {"skip": True}, ("SPY", "2024-08-02"): {"skip": False}, ("QQQ", "2024-08-01"): {"skip": False}}
    tr = [{"symbol": "SPY", "day": "2024-08-01", "pnl": -10.0, "pnl_2x": -12.0, "entry_time": "10:00"},
          {"symbol": "SPY", "day": "2024-08-01", "pnl": -5.0, "pnl_2x": -6.0, "entry_time": "11:00"},
          {"symbol": "QQQ", "day": "2024-08-01", "pnl": 4.0, "pnl_2x": 3.0, "entry_time": "10:00"},
          {"symbol": "SPY", "day": "2024-08-02", "pnl": 6.0, "pnl_2x": 5.0, "entry_time": "10:00"},
          {"symbol": "IWM", "day": "2024-08-05", "pnl": -1.0, "pnl_2x": -2.0, "entry_time": "10:00"}]
    w = EG.gate_window(tr, gate, "2024-08-01", "2024-08-30")
    assert w["skipped_units"] == 1 and w["skipped_trades"] == 2 and w["no_prediction_units"] == 1 and w["units"] == 4
    assert w["gated"]["total"] == 9.0 and w["ungated"]["total"] == -6.0
    assert w["gated"]["pf_2x"] == pytest.approx(8 / 2)
    assert w["checks"][0][1] and w["checks"][2][1]
    assert w["info"]["gated"]["without_best_day"] == pytest.approx(9.0 - 6.0)   # best day 2024-08-02 (+6) vs 08-01 (+4)
    assert w["info"]["ungated"]["months_green"] == 0


# ---------------------------------------------------------------- random whole-day skips
def test_random_skips_are_deterministic_seeds_31_to_230():
    rng = np.random.default_rng(4)
    tr = [{"symbol": s, "day": d, "pnl": float(rng.normal(0, 10))} for d in book.sessions_between("2024-08-01", "2024-12-31")
          for s in ("SPY", "QQQ") if rng.uniform() < 0.8]
    a, n = EG.random_skips(tr, 25)
    b, _n = EG.random_skips(list(reversed(tr)), 25)
    assert EG.SEEDS == tuple(range(31, 231)) and len(a) == 200 and np.array_equal(a, b)
    units = sorted({(t["symbol"], t["day"]) for t in tr})
    ut = np.array([sum(t["pnl"] for t in tr if (t["symbol"], t["day"]) == u) for u in units])
    manual = [ut.sum() - ut[np.random.default_rng(s).choice(len(units), 25, replace=False)].sum() for s in range(31, 231)]
    assert n == len(units) and np.allclose(a, manual)
    gate = {u: {"skip": k % 4 == 0} for k, u in enumerate(units)}
    w1, w2 = EG.gate_window(tr, gate, "2024-08-01", "2024-12-31"), EG.gate_window(tr, gate, "2024-08-01", "2024-12-31")
    assert w1["random"] == w2["random"] and w1["checks"] == w2["checks"]
    rs, _ = EG.random_skips(tr, w1["skipped_units"])
    assert w1["random"]["p95"] == round(float(np.percentile(rs, 95)), 2)
    z, _ = EG.random_skips(tr, 0)
    assert np.allclose(z, ut.sum())


def test_part_e_pass_needs_every_window_and_reports_the_account_view():
    rng = np.random.default_rng(8)
    days = book.sessions_between("2025-07-01", "2026-06-30")
    tr, gate = [], {}
    for d in days:
        good = rng.uniform() < 0.6
        gate[("QQQ", d)] = {"skip": not good}
        for _ in range(3):
            p = float(rng.normal(3 if good else -4, 5))
            tr.append({"symbol": "QQQ", "day": d, "pnl": p, "pnl_2x": p - 1.0, "debit": 450.0, "entry_time": "10:00"})
    wf = {"gate": gate, "fits": [], "sessions": len(days), "refits": 12, "oos_from": "2018-01", "last_fit": None}
    res, dev = R9.part_e(wf, {"Part S scalp_trend|d20-30t25 t5s5": {"rows": tr, "kind": "option", "label": "x",
                                                                   "windows": [("test half",) + EG.S_TEST + ("REAL options",)]},
                              "NB-VOL": {"why": "no file"}})
    ev = res["strategies"]["Part S scalp_trend|d20-30t25 t5s5"]
    assert ev["pass"] and ev["windows"]["test half"]["pass_"]
    assert ev["windows"]["test half"]["account"]["gated"]["debit_pct_3000"]["median"] == 15.0
    assert res["strategies"]["NB-VOL"] == {"why": "no file"}
    assert list(dev) == ["E Part S scalp_trend|d20-30t25 t5s5 gated (test half)"]
    L = []
    R9._part_e_md(L, res)
    md = "\n".join(L)
    assert "## Part E" in md and "PASS" in md and "NOT RUN (no file)" in md and "account view" in md
    # one failing window fails the strategy
    res2, _ = R9.part_e(wf, {"S": {"rows": tr, "kind": "option", "windows": [("a",) + EG.S_TEST + ("REAL",), ("b", "2024-08-01", "2024-12-31", "REAL")]}})
    assert not res2["strategies"]["S"]["pass"]


def test_trials_include_part_e():
    assert R9.TRIALS["E (the efficiency gate on FIN-H, NB-VOL and Part S)"] == 3
    assert R9.ROUND9 == 206 == sum(R9.TRIALS.values())
    assert R9.trials(10)["total_for_dsr"] == 216 and "Part E" in R9.trials(10)["e_note"]
    assert len(EG.FEATURES) == 16 and EG.WRITTEN_FEATURE_COUNT == 15


# ---------------------------------------------------------------- end to end: tools/sprint_round9.py --parts E
def _write_bars(root, sym, days, seed, px0):
    """Regular-hours 1-minute bars in the cache layout (stocks/<SYM>/<YYYY-MM>.csv.gz)."""
    rng = np.random.default_rng(seed)
    hm = [f"{(570 + i) // 60:02d}:{(570 + i) % 60:02d}:00" for i in range(N)]
    by_month, px = {}, px0
    for d in days:
        off = pd.Timestamp(f"{d} 12:00", tz="America/New_York").strftime("%z")
        off = off[:3] + ":" + off[3:]
        r = rng.normal(rng.normal(0, 0.0004), 0.0008, N)
        c = px * np.exp(np.cumsum(r))
        o = np.r_[px, c[:-1]]
        df = pd.DataFrame({"ts": [f"{d}T{t}{off}" for t in hm], "o": o.round(2), "h": (np.maximum(o, c) * 1.0002).round(2),
                           "l": (np.minimum(o, c) * 0.9998).round(2), "c": c.round(2), "v": rng.integers(1000, 9000, N).astype(float)})
        by_month.setdefault(str(d)[:7], []).append(df)
        px = float(c[-1])
    folder = root / "stocks" / sym
    folder.mkdir(parents=True, exist_ok=True)
    for m, parts in by_month.items():
        with gzip.open(folder / f"{m}.csv.gz", "wt") as f:
            pd.concat(parts).to_csv(f, index=False)


def _write_csv(path, rows):
    with gzip.open(path, "wt") as f:
        pd.DataFrame(rows).to_csv(f, index=False)


@pytest.fixture(scope="module")
def e2e(tmp_path_factory):
    import sprint_synth as SS
    base = tmp_path_factory.mktemp("r9e")
    root, out = base / "data" / "alpaca", base / "data" / "sprint"
    out.mkdir(parents=True)
    hist = book.sessions_between("2015-11-02", "2018-03-30")
    dev = book.sessions_between("2024-08-01", "2024-09-30")
    for k, sym in enumerate(EG.SYMBOLS):
        _write_bars(root, sym, hist, 20 + k, 200.0 + 50 * k)
        _write_bars(root, sym, dev, 30 + k, 400.0 + 50 * k)
    SS.write_daily(root, "VIXY", date(2014, 11, 3), date(2026, 6, 30), skip=[(date(2024, 2, 1), date(2024, 7, 31))])
    rng = np.random.default_rng(1)
    nb, fh, fd = [], [], []
    for d in [x for x in hist if x >= "2016-01-04"] + dev:
        for sym in EG.SYMBOLS:
            if rng.uniform() < 0.5:
                p = float(rng.normal(1, 30))
                nb.append({"variant": "noise_sh_vol", "symbol": sym, "day": d, "_src": "HIST" if d < "2024" else "DEV", "side": "L",
                           "decision_idx": 30, "entry_idx": 31, "exit_idx": 300, "entry_time": "10:01", "exit_time": "14:30",
                           "shares": 20, "move": p / 20, "pnl": p, "pnl_2x": p - 0.4, "bps": p, "notional": 9000.0})
            if rng.uniform() < 0.2:
                p = float(rng.choice([-40.0, 150.0], p=[0.8, 0.2]))
                row = {"symbol": sym, "day": d, "signal_idx": 89, "entry_time": "11:01", "f_rvol": float(rng.uniform(0.9, 1.5)),
                       "entry_fill": 0.4, "pnl": p, "pnl_2x": p - 2.0}
                (fh if d < "2024" else fd).append(dict(row, run_id="factory_hist_v1-012" if d < "2024" else "factory_dev_v1-012"))
    nb.append(dict(nb[0], variant="noise_sh"))                       # other variants are not NB-VOL
    _write_csv(out / "trades_round8_shares_2026-11-01.csv.gz", nb)
    _write_csv(out / "trades_factory_hist_v1_2026-11-01.csv.gz", fh)
    _write_csv(out / "trades_factory_dev_v1_2026-11-01.csv.gz", fd)
    rc = T9.main(["--data", str(root), "--out", str(out), "--today", "2026-11-03", "--parts", "E", "--chains-dir", str(base / "x")])
    return {"rc": rc, "out": out, "root": root, "base": base, "nb": nb, "fh": fh, "fd": fd}


def test_tool_part_e_end_to_end(e2e):
    out = e2e["out"]
    assert e2e["rc"] == 0
    md = (out / "round9_2026-11-03.md").read_text()
    assert "## Part E" in md and "BACKTEST" in md and "MODELED" in md and "REAL" in md
    res = json.loads((out / "round9_2026-11-03.json").read_text())["result"]
    E = res["E"]
    assert E["model"]["oos_from"] == "2018-01" and E["model"]["refits"] == 5      # 2018-01..03 + 2024-08..09
    assert [f["month"] for f in E["fits"]] == ["2018-01", "2018-02", "2018-03", "2024-08", "2024-09"]
    assert E["strategies"]["Part S"]["why"].startswith("Part S not in this run")
    for name in ("FIN-H", "NB-VOL"):
        ev = E["strategies"][name]
        assert set(ev["windows"]) == {"2018-01..2024-01", "DEV"}
        for key, w in ev["windows"].items():
            assert w["trades"] > 0 and len(w["checks"]) == 3 and w["random"]["seeds"] == "31-230"
            assert w["gated"]["trades"] == w["trades"] - w["skipped_trades"]
    nb_hist = [r for r in e2e["nb"] if r["variant"] == "noise_sh_vol" and "2018-01-02" <= r["day"] <= "2024-01-31"]
    assert E["strategies"]["NB-VOL"]["windows"]["2018-01..2024-01"]["trades"] == len(nb_hist)
    fin_hist = [r for r in e2e["fh"] if r["f_rvol"] >= 1.06 and r["day"] >= "2018-01-02"]
    assert E["strategies"]["FIN-H"]["windows"]["2018-01..2024-01"]["trades"] == len(fin_hist)
    assert res["trials"]["round9"] == 206
    dec = pd.read_csv(out / "trades_round9_E_2026-11-03.csv.gz", compression="gzip")
    assert set(dec["symbol"]) == set(EG.SYMBOLS) and dec["month"].min() == "2018-01" and set(dec["seg"]) == {"HIST", "DEV"}
    assert (dec["skip"] == (dec["p"] <= dec["cut"])).all()
    assert abs(dec["skip"].mean() - 1 / 3) < 0.15
    assert any(s.startswith("E gate on NB-VOL") for s in R9.summary_lines(res))
    # deterministic
    out2 = e2e["base"] / "again"
    out2.mkdir()
    for f in out.glob("trades_*_2026-11-01.csv.gz"):
        (out2 / f.name).write_bytes(f.read_bytes())
    assert T9.main(["--data", str(e2e["root"]), "--out", str(out2), "--today", "2026-11-03", "--parts", "E",
                    "--chains-dir", str(e2e["base"] / "x")]) == 0
    res2 = json.loads((out2 / "round9_2026-11-03.json").read_text())["result"]
    assert res2["E"] == E
