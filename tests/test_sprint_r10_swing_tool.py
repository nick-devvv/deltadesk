"""Round 10's swing families end to end on synthetic data: round 9's pull (assets, daily bars, EDGAR) and round 10's pull
(tools/sprint_pull10.py: stock15 + the D-IV and r10swing providers) against fake Alpaca / SEC servers for a short DEV span,
then tools/sprint_r10_swing.py: the report, the JSON, the D-IV table and trade files, the labels (BACKTEST, REAL, BS-EST,
SURVIVORSHIP-BIASED, LOOK-AHEAD CAVEAT, PAPER RESEARCH ONLY), the trial count written the way round 9 writes it, a resumed
pull that asks for nothing twice, determinism, and the refusal of trade rows touching L1/L2. Synthetic data only."""
import json
from datetime import date

import pandas as pd
import pytest

import sprint_synth9 as S9
import pull_alpaca as PA
import sprint_pull9 as P9
import sprint_pull10 as P10
import sprint_r10_swing as T10
from sprint import periods, r10swing as SW, universe as U

TODAY = "2026-11-02"
SPAN = ("2025-09-22", "2025-11-05")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("r10")
    root, out = base / "data" / "alpaca", base / "data" / "sprint"
    root.mkdir(parents=True)
    out.mkdir(parents=True)
    m = S9.Market()
    fa = S9.FakeAlpaca(m)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PA, "_http", fa)
        mp.setattr(PA, "MAX_PER_MIN", 10 ** 9)
        mp.setattr(PA, "ROOT", root)
        mp.setattr(P9, "trading_http", lambda url, h: m.assets())
        mp.setenv("ALPACA_KEY", "k")
        mp.setenv("ALPACA_SECRET", "s")
        quiet = lambda s: None
        P9.pull_assets(root, quiet)
        P9.pull_daily(list(U.U_ETF) + U.read_ustk(root)["symbols"], root, quiet)
        sec = S9.FakeSEC(m)
        P9.pull_edgar_index(root, quiet, http=sec, throttle=S9.NoThrottle())
        P9.pull_edgar_headers(root, quiet, http=sec, throttle=S9.NoThrottle(), panel=P9.ustk_panel(root, quiet))
        rc_pull = P10.main(["--from", SPAN[0], "--to", SPAN[1]])
        n_calls = len(fa.calls)
        rc_again = P10.main(["--from", SPAN[0], "--to", SPAN[1]])
        n_again = len(fa.calls)
    rc = T10.main(["--data", str(root), "--out", str(out), "--today", TODAY, "--chains-dir", str(base / "no_chains")])
    return {"base": base, "root": root, "out": out, "rc": rc, "rc_pull": (rc_pull, rc_again), "calls": (n_calls, n_again)}


def _res(out):
    return json.loads((out / f"r10swing_{TODAY}.json").read_text())["result"]


def test_the_pull_and_the_tool_run_and_a_second_pull_asks_for_nothing(world):
    assert world["rc_pull"] == (0, 0) and world["rc"] == 0
    a, b = world["calls"]
    assert a > 0 and b == a                                  # resumed: every stage skipped, no request
    root = world["root"]
    assert (root / "r10" / "stock15").exists() and list((root / "r10" / "opt").rglob("div.done"))


def test_report_json_labels_and_trade_files(world):
    out = world["out"]
    md = (out / f"r10swing_{TODAY}.md").read_text()
    for lab in ("BACKTEST", "REAL", "BS-EST", "SURVIVORSHIP-BIASED", "LOOK-AHEAD CAVEAT", "PAPER RESEARCH ONLY", "## D-IV",
                "## V1 term_slope", "## V3 earn_runup", "## V4 new_high", "Compounding view", "Deflated Sharpe", "Not financial advice"):
        assert lab in md, lab
    for f in ("V1", "V2", "V2s", "V3", "V3opt", "V3pool", "V4", "V4opt"):
        assert (out / f"trades_r10swing_{f}_{TODAY}.csv.gz").exists(), f
    assert (out / f"r10_div_{TODAY}.csv.gz").exists()
    res = _res(out)
    assert set(res) >= {"DIV", "VOL", "V3", "V4", "trials", "dsr", "compounding"}
    for v in ("V1", "V2", "V2-s"):
        o = res["VOL"][v]
        assert set(o["levels"]) == {"mid", "50", "100", "2x"} and len(o["pass_bar"]["checks"]) == 4 and o["random"]["draws"] == 200
    assert "PAPER RESEARCH ONLY" in res["VOL"]["V2-s"]["label"]
    assert len(res["V3"]["pass_bar"]["checks"]) == 7 and len(res["V4"]["pass_bar"]["checks"]) == 7
    assert len(res["V3"]["twin"]["bar"]["checks"]) == 5 and len(res["V4"]["twin"]["bar"]["checks"]) == 4
    assert set(res["V4"]["windows"]) == {"discovery 2016-2019", "holdout 2020-2023", "DEV"} and "share" in res["V4"]["top7"]


def test_trials_are_written_the_way_round_9_writes_them(world):
    t = _res(world["out"])["trials"]
    assert t["r10swing"] == 7 and t["round10"] == 7767 and t["total_for_dsr"] == t["prior_in_run_logs"] + 7767
    assert t["parts"] == {"V1 term_slope": 1, "V2 rv_iv_gap": 1, "V2-s rv_iv_rich": 1, "V3 earn_runup (shares + options twin)": 2,
                          "V4 new_high (shares + options twin)": 2}
    md = (world["out"] / f"r10swing_{TODAY}.md").read_text()
    assert f"N = {t['total_for_dsr']}" in md


def test_div_table_recovers_the_synthetic_vols(world):
    df = pd.read_csv(world["out"] / f"r10_div_{TODAY}.csv.gz", compression="gzip")
    assert len(df) and (df["day"] >= SPAN[0]).all() and (df["day"] <= SPAN[1]).all()
    etf = df["symbol"].isin(U.U_ETF)
    assert (df[etf]["iv30"] - 0.18).abs().max() < 0.003 and (df[~etf]["iv30"] - 0.40).abs().max() < 0.003
    exp30 = pd.to_datetime(df["exp30"]) - pd.to_datetime(df["day"])
    exp90 = pd.to_datetime(df["exp90"]) - pd.to_datetime(df["day"])
    assert (exp30.dt.days >= 21).all() and exp90.dt.days.between(60, 120).all()


def test_option_rows_stay_in_dev_and_carry_every_spread_level(world):
    out = world["out"]
    for f in ("V1", "V2", "V2s"):
        df = pd.read_csv(out / f"trades_r10swing_{f}_{TODAY}.csv.gz", compression="gzip")
        assert len(df) and (df["entry_day"] >= "2024-08-01").all() and (df["exit_day"] <= "2026-06-30").all()
        for k in ("mid", "50", "100", "2x"):
            assert df[f"pnl_{k}"].notna().all()
        assert (df["pnl_mid"] >= df["pnl_100"] - 1e-9).all() and (df["pnl_100"] >= df["pnl_2x"] - 1e-9).all()
        assert (df["rank"].between(1, 10)).all()
    v2s = pd.read_csv(out / f"trades_r10swing_V2s_{TODAY}.csv.gz", compression="gzip")
    assert (v2s["k_lp"] < v2s["k_sp"]).all() and (v2s["k_sc"] < v2s["k_lc"]).all() and (v2s["margin"] > 0).all()
    for f in ("V3", "V4"):
        df = pd.read_csv(out / f"trades_r10swing_{f}_{TODAY}.csv.gz", compression="gzip")
        for a, b in zip(df["entry_day"], df["exit_day"]):
            assert not periods.overlaps(date.fromisoformat(a), date.fromisoformat(b))
    v4 = pd.read_csv(out / f"trades_r10swing_V4opt_{TODAY}.csv.gz", compression="gzip")
    assert len(v4) and (v4["delta_est"].between(0.60, 0.70)).all() and (v4["dte"].between(60, 120)).all()


def test_the_tool_is_deterministic(world, tmp_path):
    out2 = tmp_path / "again"
    out2.mkdir()
    rc = T10.main(["--data", str(world["root"]), "--out", str(out2), "--today", TODAY, "--chains-dir", str(tmp_path / "x")])
    assert rc == 0 and _res(out2) == _res(world["out"])


def test_trade_rows_touching_l1_or_l2_are_refused(world, tmp_path, monkeypatch):
    real = SW.v4_book

    def leaky(p, univ, slots=SW.V4_SLOTS):
        tr, info = real(p, univ, slots)
        bad = dict(tr[0], entry_day="2024-01-30", exit_day="2024-08-02", day="2024-08-02")
        return tr + [bad], info
    monkeypatch.setattr(SW, "v4_book", leaky)
    out = tmp_path / "bad"
    out.mkdir()
    with pytest.raises(periods.LockedPeriod):
        T10.main(["--data", str(world["root"]), "--out", str(out), "--today", TODAY, "--parts", "V4"])
