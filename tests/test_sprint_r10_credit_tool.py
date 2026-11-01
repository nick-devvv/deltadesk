"""Round 10's credit-spread tool end to end on synthetic data (tools/sprint_r10_credit.py): DEV REAL for SPY (decides) and QQQ
(information), HIST MODELED (information), the report's labels and sections (paper research only, REAL / MODELED, VIX proxy,
the pass bar beside each control, April 2025, the worst 5 days, months green, return on margin, the $3,000 account view), the
JSON's trial block (8 = 5 + 3; the deflated Sharpe's N = run logs + 7,767), the trade file, the coverage of the needed strikes,
the compounding hook, determinism, --needed, and the refusal of L1/L2. Synthetic data only."""
import json
from datetime import date

import pandas as pd
import pytest

import test_sprint_r10_credit as T                                   # imports sprint_synth, which puts tools/ on sys.path
import sprint_r10_credit as TOOL
from sprint import periods
from sprint import r10credit as RC

TODAY = "2026-11-03"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("r10tool")
    root, out = base / "data" / "alpaca", base / "data" / "sprint"
    out.mkdir(parents=True)
    dev = T.sessions("2025-03-10", "2025-04-17")
    T.write_world(root, "SPY", dev, px0=400.0, seed=41, gaps={dev[24]: 0.007})
    T.write_world(root, "QQQ", dev, px0=350.0, seed=61)
    hist = T.sessions("2019-10-01", "2019-11-08")
    T.write_world(root, "SPY", hist, px0=300.0, seed=71, options=False)
    T.write_world(root, "QQQ", hist, px0=200.0, seed=81, options=False)
    (out / "calib_modeled.json").write_text(json.dumps(T.CALIB))
    rc = TOOL.main(["--data", str(root), "--out", str(out), "--today", TODAY, "--chains-dir", str(base / "no_chains")])
    return {"base": base, "root": root, "out": out, "rc": rc, "dev": dev, "hist": hist}


def _json(out):
    return json.loads((out / f"r10credit_{TODAY}.json").read_text())


def test_the_tool_writes_the_report_json_and_trade_file(world):
    out = world["out"]
    assert world["rc"] == 0
    md = (out / f"r10credit_{TODAY}.md").read_text()
    for lab in ("BACKTEST", "PAPER RESEARCH ONLY", "**REAL**", "**MODELED**", "VIX PROXY", "## DEV REAL", "### SPY (decides)",
                "### QQQ (information)", "## HIST MODELED", "April 2025 alone", "Worst 5 days", "Months green", "Return on margin",
                "Account view", "(control)", "beats its control C1-ctl's total", "Two-month blocks", "## Skips and data coverage",
                "## Deflated Sharpe", "## Compounding view", "## Builder's reading", "Not financial advice", "By year: 2019",
                "By year: 2025"):
        assert lab in md, lab
    js = _json(out)
    res = js["result"]
    tr = res["trials"]
    assert tr["r10_credit"] == 8 and tr["round10"] == 7767 and tr["total_for_dsr"] == tr["prior_in_run_logs"] + 7767
    assert sorted(tr["parts"].values()) == [3, 5]
    assert set(res["eval"]) == {"DEV", "HIST"} and set(res["eval"]["DEV"]) == {"SPY", "QQQ"} and set(res["eval"]["HIST"]) == {"SPY", "QQQ"}
    spy = res["eval"]["DEV"]["SPY"]
    assert set(spy) == set(RC.RULES)
    for rule in RC.RULES:
        pb = spy[rule]["pass_bar"]
        assert spy[rule]["decides"] is True and len(pb["checks"]) == (5 if rule in RC.CONTROL else 4)
        assert pb["pass"] is False                                              # a few weeks of synthetic data: under 100 trades
    assert res["eval"]["DEV"]["QQQ"]["C1"]["decides"] is False
    assert "pass_bar" not in res["eval"]["HIST"]["SPY"]["C1-ctl"] and "MODELED" in res["eval"]["HIST"]["SPY"]["C1-ctl"]["prices"]
    assert set(res["dsr"]) == set(RC.RULES)
    assert "no credit-spread rule passed" in res["compounding"]["note"] and res["compounding"]["result"] is None
    cov = res["coverage"]
    assert set(cov) == {"DEV SPY", "DEV QQQ"} and cov["DEV SPY"]["days"] == len(world["dev"])
    assert cov["DEV SPY"]["needed"] == cov["DEV SPY"]["on_file"] + cov["DEV SPY"]["asked_no_bars"] + cov["DEV SPY"]["outside_asked"]
    assert set(res["skips"]) == {"DEV SPY", "DEV QQQ", "HIST SPY", "HIST QQQ"}
    assert js["meta"]["spread"].startswith("MODELED-SPREAD everywhere")


def test_the_trade_file(world):
    f = world["out"] / f"trades_r10credit_{TODAY}.csv.gz"
    df = pd.read_csv(f, compression="gzip")
    assert set(df["rule"]) == set(RC.RULES) and set(df["symbol"]) == {"SPY", "QQQ"} and set(df["window"]) == {"DEV", "HIST"}
    assert (df[df["window"] == "DEV"]["prices"] == "REAL").all() and (df[df["window"] == "HIST"]["prices"] == "MODELED").all()
    assert df.groupby(["rule", "symbol", "day"]).size().max() == 1
    for d in df["day"]:
        x = date.fromisoformat(d)
        assert not periods.overlaps(x, x)
    dev, hist = df[df["window"] == "DEV"], df[df["window"] == "HIST"]
    assert dev["day"].between(RC.DEV_A, RC.DEV_B).all() and hist["day"].between(RC.HIST_A, RC.HIST_B).all()
    assert (df["width"] == 5.0).all() and ((df["margin"] - (500 - 100 * df["credit"])).abs() < 0.011).all()
    assert (df["pnl_2x"] <= df["pnl"] + 1e-9).all() and (df["credit"] > 0).all()
    assert set(df["exit_reason"]) <= {"SETTLED", "TAKE PROFIT", "TIME EXIT 13:00"}
    assert set(df[df["rule"].isin(["C1", "C1-ctl", "C1-ic", "C2", "C2-ctl"])]["exit_reason"]) == {"SETTLED"}
    assert set(df[df["rule"] == "C4"]["structure"]) <= {"iron fly", "iron condor"}
    assert (df[df["rule"] == "C1-ctl"]["structure"] == "put vertical").all() and (df[df["rule"] == "C1-ic"]["structure"] == "iron condor").all()
    assert (df[df["rule"].isin(["C2", "C2-ctl"])]["entry_time"] >= "13:45").all()
    assert (df[df["rule"].isin(["C3", "C3-ctl"])]["entry_time"].between("09:45", "09:47")).all()
    assert (df[df["rule"] == "C2"]["rv20"] < 0.19).all() and (df[df["rule"] == "C2"]["sma10_side"] == 1).all()
    assert (df[(df["rule"] == "C2") & (df["symbol"] == "QQQ")]["rv_from"] == "SPY").all()


def test_dev_is_deterministic_and_does_not_depend_on_hist(world, tmp_path):
    out2 = tmp_path / "again"
    out2.mkdir()
    rc = TOOL.main(["--data", str(world["root"]), "--out", str(out2), "--today", TODAY, "--windows", "DEV",
                    "--chains-dir", str(tmp_path / "x")])
    assert rc == 0
    a, b = _json(world["out"])["result"], _json(out2)["result"]
    assert a["eval"]["DEV"] == b["eval"]["DEV"] and a["dsr"] == b["dsr"] and a["coverage"] == b["coverage"]
    assert set(b["eval"]) == {"DEV"}


def test_hist_without_the_calibration_is_skipped_with_a_warning(world, tmp_path):
    out2 = tmp_path / "nocal"
    out2.mkdir()
    rc = TOOL.main(["--data", str(world["root"]), "--out", str(out2), "--today", TODAY, "--windows", "HIST", "--symbols", "SPY",
                    "--chains-dir", str(tmp_path / "x")])
    js = _json(out2)
    assert rc == 0 and any(w.startswith("HIST MODELED not run") for w in js["meta"]["warnings"]) and js["result"]["eval"] == {}


def test_needed_prints_the_contracts_for_the_pull(world, capsys):
    d = world["dev"][5]
    assert TOOL.main(["--data", str(world["root"]), "--needed", d.isoformat(), "--symbols", "QQQ"]) == 0
    js = json.loads(capsys.readouterr().out)
    assert js["symbol"] == "QQQ" and js["needed"] >= js["on_file"] > 0 and set(js["reach"]) == {"09:45", "10:00", "10:30", "13:45"}
    assert all(s.startswith(f"QQQ{d:%y%m%d}") for s in js["missing"])
    with pytest.raises(periods.LockedPeriod):
        TOOL.main(["--data", str(world["root"]), "--needed", "2026-08-03"])


def test_a_trade_inside_l1_or_l2_is_refused(world, monkeypatch, tmp_path):
    real = RC.run

    def bad_run(*a, **k):
        tr, sk = real(*a, **k)
        return tr + [dict(tr[0], day="2024-03-04")] if tr else tr, sk

    monkeypatch.setattr(RC, "run", bad_run)
    out2 = tmp_path / "bad"
    out2.mkdir()
    with pytest.raises(periods.LockedPeriod):
        TOOL.main(["--data", str(world["root"]), "--out", str(out2), "--today", TODAY, "--windows", "DEV", "--symbols", "SPY",
                   "--chains-dir", str(tmp_path / "x")])
    assert not (out2 / f"r10credit_{TODAY}.md").exists()


def test_the_compounding_hook_hands_over_passing_rules_only():
    days = RC.book.sessions_between("2025-07-01", "2026-06-30")
    rows = [{"rule": "C3", "symbol": "SPY", "day": d, "pnl": 30.0 if k % 4 else -40.0, "pnl_2x": 20.0 if k % 4 else -45.0, "entry_idx": 15,
             "exit_reason": "SETTLED", "structure": "iron condor", "margin": 400.0, "max_loss": 405.2, "legs_itm_at_close": 0, "window": "DEV"}
            for k, d in enumerate(days)]
    rows += [dict(r, rule="C3-ctl", pnl=-1.0, pnl_2x=-1.5) for r in rows]
    ev = RC.evaluate_all(rows, ("DEV",), ("SPY",))
    assert ev["DEV"]["SPY"]["C3"]["pass_bar"]["pass"] and not ev["DEV"]["SPY"]["C3-ctl"]["pass_bar"]["pass"]
    inp = RC.compounding_inputs(ev["DEV"], rows)
    assert set(inp) == {"C3"} and len(inp["C3"]) == len(days)
    assert set(inp["C3"][0]) == {"day", "pnl", "pnl_2x", "max_loss", "margin"} and inp["C3"][0]["max_loss"] == 405.2
    view = TOOL.compounding_view(ev, rows)
    assert view["result"] is None and "NOT WIRED" in view["note"] and view["inputs"] == {"C3": len(days)}
