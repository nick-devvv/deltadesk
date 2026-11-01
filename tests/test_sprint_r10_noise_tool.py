"""Round 10's noise band tool end to end on synthetic caches (tools/sprint_r10_noise.py): the report, the JSON, the trade files,
the universe rule (U3 fallback without DIA/XLK/XLF/SMH bars, U7 with them), the engine self-check, the trial counts written
with the run (165; round 10 = 7,767; N = the run logs' rows + 7,767), restart safety (a re-run writes byte-identical files),
the compounding view wired for a pass, the locked-period refusals and the runtime benchmark. Synthetic data only."""
import gzip
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sprint_synth  # noqa: F401  (puts tools/ on sys.path)
import sprint_r10_noise as T
import test_sprint_r10_noise as H
from sprint import book, periods, runner
from sprint import r10noise as R

TODAY = "2026-11-03"
HIST_DAYS = ("2019-10-01", "2020-03-31")
DEV_DAYS = ("2025-05-01", "2025-07-31")


def write_cache(root, sym, days, seed, px0=300.0):
    df = H.synth_df(days, px0=px0, seed=seed)
    df["ts"] = [t.isoformat() for t in df["ts"]]
    df["n"], df["vw"] = 10, df["c"]
    for m, g in df.groupby(df["ts"].str.slice(0, 7)):
        p = Path(root) / "stocks" / sym / f"{m}.csv.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(T._gz_bytes([g.to_csv(index=False)]))


def make_root(base, syms, hist=HIST_DAYS, dev=DEV_DAYS):
    root = base / "data" / "alpaca"
    hd, dd = H.sessions(*hist), H.sessions(*dev)
    for k, s in enumerate(syms):
        write_cache(root, s, hd, 20 + k, px0=300.0 - 20 * k)
        write_cache(root, s, dd, 40 + k, px0=420.0 - 20 * k)
    write_cache(root, "SPY", H.sessions("2024-03-01", "2024-03-29"), 99)         # L2 bars in the cache: never read
    return root


def run(root, out, *extra):
    out.mkdir(parents=True, exist_ok=True)
    return T.main(["--data", str(root), "--out", str(out), "--today", TODAY, *extra])


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("r10n")
    root = make_root(base, R.U3)
    o1 = base / "out1"
    rc1 = run(root, o1)
    snap = {p.name: p.read_bytes() for p in sorted(o1.iterdir())}
    rc2 = run(root, o1)                                                      # the same run again into the same folder
    return {"base": base, "root": root, "o1": o1, "snap": snap, "rc": (rc1, rc2)}


def _json(out):
    return json.loads((out / f"r10noise_{TODAY}.json").read_text())["result"]


def test_the_tool_writes_the_report_json_and_trade_files(world):
    o = world["o1"]
    assert world["rc"] == (0, 0)
    md = (o / f"r10noise_{TODAY}.md").read_text()
    for lab in ("BACKTEST", "real Alpaca stock 1-minute bars", "## Addendum 15.1", "## Addendum 15.2", "## Universe",
                "Used for the U7 cells: U3", "## Builder's readings", "R7 Part A's item 3", "## Engine self-check",
                "## Trials and the deflated Sharpe", "Share of cells with a positive holdout Sharpe", "L2", "tools/sprint_pull.py"):
        assert lab in md, lab
    res = _json(o)
    assert res["universe"]["used"] == "U3" and len(res["universe"]["missing"]) == 12
    g = res["grid"]
    assert len(g["rows"]) == 162 and [r["cell"] for r in g["rows"]] == list(R.CELL_IDS) and g["chosen"] is None
    assert "1,000" in g["choice_why"] and g["min_disc_trades"] == 1000
    assert all(r["discovery"]["trades"] > 0 and r["holdout1"]["trades"] > 0 and r["holdout2"]["trades"] > 0 for r in g["rows"])
    u3 = {r["cell"]: r for r in g["rows"] if r["universe"] == "U3"}
    for r in g["rows"]:
        if r["universe"] == "U7":                                         # fell back to the three: equal to the U3 twin
            twin = u3[r["cell"][:-2] + "U3"]
            assert r["universe_used"] == "U3" and r["holdout2"] == twin["holdout2"] and r["discovery"] == twin["discovery"]
    f = res["fixes"]
    assert set(f["fixes"]) == {"N1", "N2", "N12"} and set(f["NB-VOL"]["windows"]) == {"holdout1", "holdout2"}
    for fx in f["fixes"].values():
        assert len(fx["windows"]["holdout1"]["checks"]) == 7 and fx["holds"] is False
    sc = res["self_check"]
    assert sc["base_days"] > 150 and sc["base_mismatch"] == 0 and sc["sample_mismatch"] == 0 and sc["sample_days"] > 0


def test_the_trial_counts_are_written_with_the_run(world):
    res = _json(world["o1"])
    t = res["trials"]
    prior = runner.count_prior_trials(world["o1"])
    assert t["this_build"] == 165 and t["round10"] == 7767 and t["prior_in_run_logs"] == prior and t["total_for_dsr"] == prior + 7767
    assert sum(t["parts"].values()) == 165 and sum(t["round10_tally"].values()) == 7767
    md = (world["o1"] / f"r10noise_{TODAY}.md").read_text()
    assert f"N = {prior + 7767}" in md and "this build 165" in md and "round 10 = 7767" in md
    assert res["dsr_distinct"] <= 81 + 3 and R.BASE_ID in res["dsr"] and set(R.FIXES) <= set(res["dsr"])
    extra = world["base"] / "runs_x.csv"
    extra.write_text("run_id,x\na,1\nb,2\n")
    assert T.count_trials(world["o1"], [str(extra)]) == runner.count_prior_trials(world["base"] / "nowhere") + 2


def test_trade_files_stay_inside_their_periods(world):
    o = world["o1"]
    g = pd.read_csv(o / f"trades_r10noise_grid_{TODAY}.csv.gz", compression="gzip")
    assert g["cell"].nunique() == 81 and set(g["cell"]) == {c for c in R.CELL_IDS if c.endswith("U3")}   # U7 = U3: not repeated
    assert set(g["symbol"]) == set(R.U3)
    for d in g["day"].unique():
        assert not periods.overlaps(d, d)
    assert g[g["_src"] == "HIST"]["day"].between("2016-01-04", "2024-01-31").all() and g[g["_src"] == "DEV"]["day"].between("2024-08-01", "2026-06-30").all()
    fx = pd.read_csv(o / f"trades_r10noise_fixes_{TODAY}.csv.gz", compression="gzip")
    assert list(fx["variant"].unique()) == ["NB-VOL", "N1", "N2", "N12"]
    base = g[g["cell"] == R.BASE_ID]
    nb = fx[fx["variant"] == "NB-VOL"]
    assert len(base) == len(nb) and base["pnl"].sum() == pytest.approx(nb["pnl"].sum())
    n1 = fx[fx["variant"] == "N1"]
    assert n1.groupby(["symbol", "day"]).size().max() == 1                   # N1: one trade per symbol per day
    n2 = fx[fx["variant"] == "N2"]
    assert n2["decision_idx"].max() <= 149                                   # N2: no entry after the 12:00 check
    res = _json(o)
    rows = {r["cell"]: r for r in res["grid"]["rows"]}
    assert rows[R.BASE_ID]["holdout2"]["trades"] == int(base["day"].between(*R.H2).sum())


def test_restart_safety_a_rerun_writes_identical_files(world):
    names = [f"r10noise_{TODAY}.md", f"r10noise_{TODAY}.json", f"trades_r10noise_grid_{TODAY}.csv.gz", f"trades_r10noise_fixes_{TODAY}.csv.gz"]
    assert sorted(world["snap"]) == sorted(names)
    for n in names:
        assert (world["o1"] / n).read_bytes() == world["snap"][n], n
    with gzip.open(world["o1"] / names[2], "rt") as fh:
        assert fh.readline().startswith("cell,symbol,day,_src")


def test_u7_is_used_when_the_four_extra_symbols_have_bars(tmp_path):
    root = make_root(tmp_path, R.U7, hist=("2019-11-01", "2020-01-31"), dev=("2025-06-02", "2025-06-30"))
    assert run(root, tmp_path / "o", "--parts", "grid") == 0
    res = _json(tmp_path / "o")
    assert res["universe"]["used"] == "U7" and res["universe"]["missing"] == [] and res["fixes"] is None
    rows = {r["cell"]: r for r in res["grid"]["rows"]}
    u7, u3 = rows[R.BASE_ID[:-2] + "U7"], rows[R.BASE_ID]
    assert u7["universe_used"] == "U7" and u7["discovery"]["trades"] > u3["discovery"]["trades"]
    g = pd.read_csv(tmp_path / "o" / f"trades_r10noise_grid_{TODAY}.csv.gz", compression="gzip")
    assert g["cell"].nunique() == 162 and set(g[g["cell"].str.endswith("U7")]["symbol"]) == set(R.U7)
    md = (tmp_path / "o" / f"r10noise_{TODAY}.md").read_text()
    assert "Used for the U7 cells: U7" in md and "Addendum 15.2" in md and "NOT RUN" in md


def test_a_pass_gets_the_compounding_view(world, tmp_path, monkeypatch):
    real = R.window_bar
    monkeypatch.setattr(R, "MIN_DISC_TRADES", 40)
    monkeypatch.setattr(R, "window_bar", lambda rows, key: dict(real(rows, key), **{"pass": True}))
    assert run(world["root"], tmp_path / "o", "--parts", "grid,fixes") == 0
    res = _json(tmp_path / "o")
    g = res["grid"]
    assert g["chosen"] in R.CELL_IDS and g["pass"] and set(g["compounding"]) == {"holdout1", "holdout2"}
    assert g["compounding"]["holdout2"]["input"]["sessions"] == len(book.sessions_between(*R.H2))
    md = (tmp_path / "o" / f"r10noise_{TODAY}.md").read_text()
    assert "Compounding view" in md and "| 5% |" in md and "chance of halving" in md and "(chosen)" in md


def test_locked_rows_are_refused():
    t = {"day": np.array(["2024-08-05", "2024-03-04"], dtype="U10"), "src": np.array(["DEV", "DEV"], dtype="U4")}
    assert "locked period L2" in T.check_arrays(t, "x")
    t2 = {"day": np.array(["2024-02-01"], dtype="U10"), "src": np.array(["HIST"], dtype="U4")}
    assert "L2" in T.check_arrays(t2, "x")
    t3 = {"day": np.array(["2015-12-01"], dtype="U10"), "src": np.array(["HIST"], dtype="U4")}
    assert "outside HIST" in T.check_arrays(t3, "x")
    t4 = {"day": np.array(["2019-05-01", "2025-01-02"], dtype="U10"), "src": np.array(["HIST", "DEV"], dtype="U4")}
    assert T.check_arrays(t4, "x") is None


def test_no_bars_reports_not_run(tmp_path):
    assert run(tmp_path / "empty", tmp_path / "o") == 0
    md = (tmp_path / "o" / f"r10noise_{TODAY}.md").read_text()
    assert "No SPY/QQQ/IWM stock bars" in md and md.count("NOT RUN") >= 2


def test_the_runtime_benchmark(capsys):
    assert T.bench(n_days=25) == 0
    txt = capsys.readouterr().out
    assert "ESTIMATE: about" in txt and "17584 symbol-sessions" in txt and "load + prep + engine" in txt
