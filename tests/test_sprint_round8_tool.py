"""Round 8 end to end: the grid choice on 2016-2019 only (ties; 60 trades; nothing dated 2020 or later can change it), the
holdout bars, the twin specs (the pre-registered runs, studies, grid and the 192 trials), and tools/sprint_round8.py on
synthetic data (engine runs of the specs, then the tool: report, JSON, trade files, labels, refusals). Synthetic data only."""
import gzip
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import book, engine, ind5, optpass, periods, round8, runner, shares

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "sprint" / "specs"


# ---------------------------------------------------------------- the grid choice and the holdouts
def _st(n, pf):
    return {"trades": n, "pf": pf}


def test_choose_cell_tie_rules_and_the_60_trade_floor():
    cells = [("s10_t30", 0.10, 0.30, _st(80, 1.4)), ("s20_t30", 0.20, 0.30, _st(90, 1.4)), ("s10_tnone", 0.10, None, _st(90, 1.4)),
             ("s50_t50", 0.50, 0.50, _st(59, 9.0)), ("s30_t50", 0.30, 0.50, _st(90, 1.4))]
    assert round8.choose_cell(cells) == "s10_tnone"                         # equal PF and trades: smaller stop wins (none last only on ties)
    cells.append(("s10_t50", 0.10, 0.50, _st(90, 1.4)))
    assert round8.choose_cell(cells) == "s10_t50"                           # same stop: the smaller target, none last
    cells.append(("s30_t30", 0.30, 0.30, _st(61, math.inf)))
    assert round8.choose_cell(cells) == "s30_t30"                           # a PF with no losing trade ranks first
    assert round8.choose_cell([("a", 0.1, 0.3, _st(59, 5.0)), ("b", 0.2, None, _st(10, 2.0))]) is None
    assert round8.choose_cell([("a", 0.1, 0.3, _st(70, None))]) is None    # no PF at all (no trade won or lost)


def _frame(seed=1, edge_cell="s20_t50"):
    rng = np.random.default_rng(seed)
    rows = []
    hist = book.sessions_between("2016-01-04", "2024-01-31")[::6]
    dev = book.sessions_between("2024-08-01", "2026-06-30")[::4]
    for src, days in (("HIST", hist), ("DEV", dev)):
        for d in days:
            for cid, _s, _t in optpass.GRID + [("signal", 0.2, None)]:
                e = 12.0 if cid == edge_cell else 0.0
                p = float(rng.normal(-1.0 + e, 25))
                rows.append({"study": "d3_ind_ema_d40", "exit": cid, "symbol": "SPY", "day": d, "side": "C", "signal_idx": 54,
                             "entry_idx": 55, "exit_idx": 200, "pnl": round(p, 2), "pnl_2x": round(p - 1.5, 2), "exit_reason": "ALL OUT", "_src": src})
    df = pd.DataFrame(rows)
    return {"HIST": df[df["_src"] == "HIST"].drop(columns="_src"), "DEV": df[df["_src"] == "DEV"].drop(columns="_src")}


STUDY = [{"name": "d3_ind_ema_d40", "entry": "ind_ema", "contract": "d40-55t45", "exits": "grid12+signal", "random_seed": None,
          "family": "D", "rule": "ind_ema"}]


def test_grid_choice_uses_2016_2019_only_and_is_frozen():
    opt = _frame()
    res = round8.d_options(opt, STUDY, optpass.GRID)["d3_ind_ema_d40"]
    assert res["chosen"] == "s20_t50" and res["survives"] and res["holdout1"]["pass"] and res["holdout2"]["pass"]
    assert set(res["cells"]) == set(optpass.GRID_IDS)
    for c in res["cells"].values():                                         # every cell, every window, with the break-even win rate
        for w in ("discovery", "holdout1", "holdout2"):
            s = c[w]
            assert s["trades"] > 0 and s["be_win_rate"] == pytest.approx(abs(s["avg_loss"]) / (s["avg_win"] + abs(s["avg_loss"])), abs=0.002)
    disc = c["discovery"]
    assert disc["trades"] == len(book.sessions_between("2016-01-04", "2019-12-31")[::6]) or disc["trades"] > 0
    late = {k: v.copy() for k, v in opt.items()}
    h = late["HIST"]
    m = h["day"] >= "2020-01-01"
    h.loc[m, "pnl"] = np.where(h.loc[m, "exit"] == "s10_t30", 500.0, -500.0)  # 2020+ rewritten: s10_t30 would now look best
    late["DEV"]["pnl"] = -late["DEV"]["pnl"].abs()
    r2 = round8.d_options(late, STUDY, optpass.GRID)["d3_ind_ema_d40"]
    assert r2["chosen"] == "s20_t50" and r2["cells"]["s20_t50"]["discovery"] == res["cells"]["s20_t50"]["discovery"]
    assert not r2["survives"] and r2["why_not"].startswith("H1")
    early = {k: v.copy() for k, v in opt.items()}
    e = early["HIST"]
    mm = (e["day"] <= "2019-12-31") & (e["exit"] == "s50_t30")
    e.loc[mm, "pnl"] = e.loc[mm, "pnl"].abs() + 30
    assert round8.d_options(early, STUDY, optpass.GRID)["d3_ind_ema_d40"]["chosen"] == "s50_t30"   # but 2016-2019 data does matter


def test_array_stats_equal_row_stats():
    rng = np.random.default_rng(8)
    days = book.sessions_between("2019-06-01", "2021-06-30")
    rows = [{"day": days[int(rng.integers(0, len(days)))], "entry_idx": int(rng.integers(15, 300)), "symbol": ("SPY", "QQQ")[k % 2],
             "pnl": round(float(rng.normal(1, 30)), 2), "pnl_2x": 0.0} for k in range(700)]
    for r in rows:
        r["pnl_2x"] = r["pnl"] - 2.0
    a = round8.rows_to_a(rows)
    assert round8.ostats_a(a) == round8.ostats(rows)
    assert round8.ostats_a(round8.sub(a, "2020-01-01", "2020-12-31")) == round8.ostats(round8.in_win(rows, "2020-01-01", "2020-12-31"))
    assert round8.years_net_a(a, (2019, 2020, 2021)) == round8.years_net(rows, (2019, 2020, 2021))
    assert round8.ostats_a(round8.EMPTY) == round8.ostats([]) == {"trades": 0, "per_session": None}


def test_d_holdout_bars():
    rows = [{"day": f"{y}-03-0{k % 5 + 1}", "pnl": (20.0 if k % 3 else -10.0), "pnl_2x": (18.0 if k % 3 else -12.0), "symbol": "SPY",
             "entry_idx": 55} for y in (2020, 2021, 2022, 2023) for k in range(20)]
    h1 = round8.holdout1_d(rows)
    assert h1["pass"] and len(h1["checks"]) == 5
    bad = [dict(r, pnl=-abs(r["pnl"])) if r["day"] >= "2022" else r for r in rows]
    g = round8.holdout1_d(bad)
    assert not g["pass"] and "(2 of 4)" in g["checks"][3][0]
    h2 = round8.holdout2_d(rows[:39])
    assert not h2["pass"] and h2["checks"][0] == ("H2: at least 40 trades", False)


# ---------------------------------------------------------------- the twin specs and the trial count
def test_round8_specs_are_the_preregistered_twins():
    import sprint_round8
    h, d = (json.loads((SPECS / f"{n}.json").read_text()) for n in ("round8_hist_v1", "round8_dev_v1"))
    assert sprint_round8.twin_check(h, d) is None
    assert h["period"] == "HIST" and h["tapes"] == "modeled" and d["period"] == "DEV" and d.get("tapes", "real") == "real"
    rh = engine.expand(h)
    runner.validate(rh)
    assert [r["block"] for r in rh] == ["newhigh_c"] + [f"b4_{c}_{e}" for c in ("d03", "n1d03") for e in ("i", "ii", "iii", "iv")]
    assert [r["run_id"] for r in rh] == [f"round8_hist_v1-{k:03d}" for k in range(1, 10)]
    nh = rh[0]
    assert (nh["entry"], nh["side"], nh["exit"].stop, nh["exit"].fixed_stop, nh["exit"].contract, nh["filters"]) == \
        ("newhigh_c", "C", "fixed", 0.95, "d03-12t07", ())
    want = {"i": (0.95, 99.0, "none"), "ii": (0.50, 99.0, "none"), "iii": (0.50, 99.0, "gb50"), "iv": (0.50, 1.0, "none")}
    for r in rh[1:]:
        x = r["exit"]
        tag, ex = r["block"].split("_")[1:]
        assert r["entry"] == "time_1100" and r["side"] == "C" and r["filters"] == ("rvol_ge106",) and x.allout == "15:25"
        assert x.contract == ("d03-12t07" if tag == "d03" else "n1d03-12t07") and (x.fixed_stop, x.fixed_target, x.trail) == want[ex]
        assert r["symbols"] == ("SPY", "QQQ", "IWM") and x.mechanics == "desk" and x.tp == "none"
    st = optpass.expand_studies(h)
    real_d = [s for s in st if s["family"] == "D" and s["random_seed"] is None]
    rnd_d = [s for s in st if s["family"] == "D" and s["random_seed"] is not None]
    assert [(s["rule"], s["contract"]) for s in real_d] == [(r, c) for r in ind5.RULES for c in ("d40-55t45", "n1d40-55t45")]
    assert [(s["rule"], s["contract"]) for s in rnd_d] == [(s["rule"], s["contract"]) for s in real_d] and {s["random_seed"] for s in rnd_d} == {31}
    assert all(s["exits"] == "grid12+signal" for s in real_d + rnd_d)
    other = [(s["name"], s["entry"], s["contract"], s["exits"]) for s in st if s["family"] in ("A-opt", "A3")]
    assert other == [("aopt_noise_sh_d55", "noise_sh", "d55-75t65", "share_signal"), ("aopt_noise_sh_n1d55", "noise_sh", "n1d55-75t65", "share_signal"),
                     ("a3_gapfade_vix_d55", "gapfade_vix", "d55-75t65", "hold"), ("a3_gapfade_vix_n1d55", "gapfade_vix", "n1d55-75t65", "hold")]
    assert sprint_round8.grid_of(h) == optpass.GRID and len(optpass.EXIT_SETS["grid12+signal"]) == 13
    assert len(real_d) * 13 == round8.TRIALS["D options (6 rules x 2 contracts x 13 exits)"] == 156
    assert sum(round8.TRIALS.values()) == 192 and round8.TRIALS["B4 (4 exits x 2 contracts)"] == len(rh) - 1
    assert len(shares.TRIAL_VARIANTS) == round8.TRIALS["A shares (3 rules x 2 sides + 2 secondary)"]
    assert len(shares.D_TRIAL_VARIANTS) == round8.TRIALS["D shares (6 rules x 2 sides)"]
    bad = json.loads(json.dumps(d))
    bad["option_pass"]["studies"] = bad["option_pass"]["studies"][::-1]
    assert "option pass" in sprint_round8.twin_check(h, bad)
    g = json.loads(json.dumps(h))
    g["option_pass"]["grid"]["stops"] = [0.1, 0.2, 0.3, 0.4]
    with pytest.raises(ValueError):
        sprint_round8.grid_of(g)


# ---------------------------------------------------------------- the tool end to end
def _sess(a, n):
    return [d for d in SS.weekdays(a, n + 30) if d.isoformat() not in periods.holidays()][:n]


def _setup(tmp):
    cache, out, sp = tmp / "alpaca", tmp / "out", tmp / "specs"
    warm, hist, dev = _sess(date(2015, 11, 2), 42), _sess(date(2016, 1, 4), 25), _sess(date(2025, 1, 6), 25)
    SS.write_stock_only(cache, "SPY", warm + hist, px0=200.0, seed=7, vol=0.0006)
    SS.write_cache(cache, "SPY", dev, px0=500.0, seed=11, iv=0.18, band=0.03, next_expiry=True)
    SS.write_daily(cache, "VIXY", date(2014, 11, 3), date(2026, 6, 30), skip=[periods.LOCKED["L2"]])
    out.mkdir(parents=True)
    sp.mkdir(parents=True)
    keys = ("d03-12t07|C", "d40-55t45|C", "d40-55t45|P", "d55-75t65|C", "d55-75t65|P", "n1d40-55t45|C")
    (out / "calib_modeled.json").write_text(json.dumps({"min_n": 30, "keys": {k: {"n": 100, "median": 0.5, "ok": True} for k in keys}}))
    for n in ("round8_hist_v1", "round8_dev_v1"):
        s = json.loads((SPECS / f"{n}.json").read_text())
        s["symbols"] = ["SPY"]
        (sp / f"{n}.json").write_text(json.dumps(s))
    for n, nn in (("factory_hist_v1", "fx_hist"), ("factory_dev_v1", "fx_dev")):
        s = json.loads((SPECS / f"{n}.json").read_text())
        s.update(spec_id=nn, symbols=["SPY"], blocks=[b for b in s["blocks"] if b["name"] in round8.B2_SLEEVES])
        (sp / f"{nn}.json").write_text(json.dumps(s))
    kw = dict(data_root=cache, chains_dir=tmp / "nochains", out_dir=out, host_name="t", today=date(2026, 11, 2), log=lambda *a: None)
    for n, a, b in (("round8_hist_v1", hist[0], hist[-1]), ("round8_dev_v1", dev[0], dev[-1]), ("fx_hist", hist[0], hist[-1]),
                    ("fx_dev", dev[0], dev[-1])):
        runner.run_spec(sp / f"{n}.json", a, b, **kw)
    args = ["--hist-spec", str(sp / "round8_hist_v1.json"), "--dev-spec", str(sp / "round8_dev_v1.json"),
            "--factory-hist", str(out / "trades_fx_hist_2026-11-02.csv.gz"), "--factory-dev", str(out / "trades_fx_dev_2026-11-02.csv.gz"),
            "--factory-hist-spec", str(sp / "fx_hist.json"), "--factory-dev-spec", str(sp / "fx_dev.json"), "--data", str(cache),
            "--out", str(out), "--today", "2026-11-02", "--symbols", "SPY", "--runs-csv", str(out / "runs_*.csv")]
    return out, args


def test_round8_tool_end_to_end(tmp_path, capsys):
    import sprint_round8
    out, args = _setup(tmp_path)
    assert sprint_round8.main(args) == 0
    printed = capsys.readouterr().out
    md = (out / "round8_2026-11-02.md").read_text()
    js = json.loads((out / "round8_2026-11-02.json").read_text())
    res = js["result"]
    for h in ("## Summary", "## Part A: steady rules in shares", "## A3's option twins and A-opt", "## Part B:", "### B2:", "### B3:",
              "### B4:", "## Part D shares", "## Part D options", "## The book", "## Trials and the deflated Sharpe", "## Limits"):
        assert h in md, h
    assert "BACKTEST" in md and "MODELED (BS, calibrated IV)" in md and "REAL" in md and "NOT VALIDATED" in md
    assert "mixed: modeled 2018-2024 options + real 2024-2026 options" in md
    assert set(res["part_a"]) == {"noise_sh", "last30", "gapfade_vix"} and set(res["part_a"]["noise_sh"]) == {"noise_sh", "noise_sh_lo", "noise_sh_vol"}
    assert len(res["d_options"]) == 12 and set(res["d_shares"]) == set(ind5.RULES) and len(res["a_opt"]) == 4
    for o in res["d_options"].values():
        assert set(o["cells"]) == set(optpass.GRID_IDS) and "signal" in o and "random" in o
    assert res["trials"]["round8"] == 192 and res["trials"]["total_for_dsr"] == res["trials"]["prior_in_run_logs"] + 192
    assert res["trials"]["prior_in_run_logs"] >= 18                           # this round's 18 engine rows are in the run log
    assert set(res["b4"]) >= {f"b4_{c}_{e}" for c in ("d03", "n1d03") for e in ("i", "ii", "iii", "iv")}
    assert "FIN-H" in res["book"]["windows"]["dev"]["res"]["sleeves"]
    assert "[BACKTEST" in printed and "round 8 done" in printed
    with gzip.open(out / "trades_round8_shares_2026-11-02.csv.gz", "rt") as f:
        sh = pd.read_csv(f)
    assert set(sh["variant"]) >= {"noise_sh", "last30", "ind_macd"} and sh["day"].min() >= "2016-01-04"
    assert not sh["day"].between("2024-02-01", "2024-07-31").any()
    for src in ("hist", "dev"):
        op = pd.read_csv(out / f"trades_round8_options_{src}_2026-11-02.csv.gz")
        assert len(op) > 0 and set(op["exit"]) <= set(optpass.GRID_IDS) | {"signal", "share_signal", "hold"}
    # reuse the option-pass files: the same result without re-running the pass
    a2 = args + ["--opt-hist", str(out / "trades_round8_options_hist_2026-11-02.csv.gz"),
                 "--opt-dev", str(out / "trades_round8_options_dev_2026-11-02.csv.gz"), "--today", "2026-11-03"]
    assert sprint_round8.main(a2) == 0
    r2 = json.loads((out / "round8_2026-11-03.json").read_text())["result"]
    assert {k: v["chosen"] for k, v in r2["d_options"].items()} == {k: v["chosen"] for k, v in res["d_options"].items()}
    # refusals: a trade inside L2, the specs out of twin
    fx = pd.read_csv(out / "trades_fx_dev_2026-11-02.csv.gz")
    fx.loc[fx.index[:1], "day"] = "2024-03-01"
    bad = tmp_path / "bad.csv.gz"
    fx.to_csv(bad, index=False, compression="gzip")
    i = args.index("--factory-dev")
    assert sprint_round8.main(args[:i + 1] + [str(bad)] + args[i + 2:]) == 2
    other = json.loads(Path(args[3]).read_text())
    other["blocks"] = other["blocks"][::-1]
    (tmp_path / "d2.json").write_text(json.dumps(other))
    assert sprint_round8.main(args[:3] + [str(tmp_path / "d2.json")] + args[4:]) == 2


def test_round8_code_has_no_order_path():
    for f in ("sprint/round8.py", "sprint/shares.py", "sprint/ind5.py", "sprint/optpass.py", "tools/sprint_round8.py"):
        src = (ROOT / f).read_text()
        for bad in ("paper-api", "/v2/orders", "/v2/positions", "import broker", "api.alpaca.markets", "urllib", "requests"):
            assert bad not in src, (f, bad)
