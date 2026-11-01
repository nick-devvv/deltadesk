"""Round 9 end to end on synthetic data: tools/sprint_pull9.py's stages against fake Alpaca / SEC servers, round 8's share
trades from the real share code, then tools/sprint_round9.py: the report, the JSON, the per-part trade files, the labels
(BACKTEST, REAL / MODELED, SURVIVORSHIP-BIASED, the look-ahead caveat), the trial count, determinism, and the refusal of
trade rows inside L1/L2. Synthetic data only."""
import gzip
import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import sprint_synth as SS
import sprint_synth9 as S9
import pull_alpaca as PA
import sprint_pull9 as P9
import sprint_round9 as T9
from sprint import book, data, periods, round9 as R9, shares, universe as U

TODAY = "2026-11-02"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("r9")
    root, out = base / "data" / "alpaca", base / "data" / "sprint"
    root.mkdir(parents=True)
    out.mkdir(parents=True)
    dev_days = [date.fromisoformat(d) for d in book.sessions_between("2025-06-16", "2025-07-14")]
    hist_days = [date.fromisoformat(d) for d in book.sessions_between("2019-11-01", "2019-12-31")]
    for k, sym in enumerate(("SPY", "QQQ")):
        SS.write_cache(root, sym, dev_days, px0=500.0 - 60 * k, seed=10 + k)
    SS.write_stock_only(root, "IWM", dev_days, px0=220.0, seed=13)
    for k, sym in enumerate(("SPY", "QQQ", "IWM")):
        SS.write_stock_only(root, sym, hist_days, px0=300.0 - 60 * k, seed=50 + k)
    SS.write_daily(root, "VIXY", date(2014, 11, 3), date(2026, 6, 30))
    m = S9.Market(cache_root=root)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PA, "_http", S9.FakeAlpaca(m))
        mp.setattr(PA, "MAX_PER_MIN", 10 ** 9)
        mp.setattr(PA, "ROOT", root)
        mp.setattr(P9, "trading_http", lambda url, h: m.assets())
        mp.setenv("ALPACA_KEY", "k")
        mp.setenv("ALPACA_SECRET", "s")
        P9.pull_assets(root, print)
        syms = list(U.U_ETF) + U.read_ustk(root)["symbols"]
        P9.pull_daily(syms, root, print)
        targets = P9.fopt_targets(root, print)
        P9.pull_fopt(root, print, targets=targets[:6])
        P9.pull_weekly(root, print, a=dev_days[0], b=dev_days[-1])
        sec = S9.FakeSEC(m)
        P9.pull_edgar_index(root, print, http=sec, throttle=S9.NoThrottle())
        panel = P9.ustk_panel(root, print)
        P9.pull_edgar_headers(root, print, http=sec, throttle=S9.NoThrottle(), panel=panel)
        P9.pull_g1(root, print, panel)
        P9.pull_g2(root, print, panel)
    series = {}
    for sym in ("SPY", "QQQ", "IWM"):
        series[("HIST", sym)] = shares.load_series(sym, periods.WARMUP["HIST"], periods.HIST[1], root)
        series[("DEV", sym)] = shares.load_series(sym, periods.DEV[0], periods.DEV[1], root)
    tr, _ = shares.run(series, data.read_daily("VIXY", root))
    shares.write_trades(out / "trades_round8_shares_2026-11-01.csv.gz", tr)
    rc = T9.main(["--data", str(root), "--out", str(out), "--today", TODAY, "--chains-dir", str(base / "no_chains")])
    return {"base": base, "root": root, "out": out, "rc": rc, "fopt_targets": targets}


def test_the_tool_writes_the_report_json_and_trade_files(world):
    out = world["out"]
    assert world["rc"] == 0
    md = (out / f"round9_{TODAY}.md").read_text()
    for lab in ("BACKTEST", "REAL", "MODELED", "SURVIVORSHIP-BIASED", "LOOK-AHEAD CAVEAT", "## Part F", "## Part G", "## Part H",
                "## Part I", "## Part S", "## The book", "Account view"):
        assert lab in md, lab
    for part in ("F", "Fopt", "G1", "G2", "G2pool", "H", "I", "S"):
        assert (out / f"trades_round9_{part}_{TODAY}.csv.gz").exists(), part
    res = json.loads((out / f"round9_{TODAY}.json").read_text())["result"]
    assert set(res["F"]) >= {"rsi2|U-ETF", "rsi2|U-STK", "tom|U-ETF", "tom|U-STK", "fopt"}
    assert res["trials"]["round9"] == 206 and res["trials"]["total_for_dsr"] == res["trials"]["prior_in_run_logs"] + 206
    assert len(res["H"]["strategies"]) == 12 and set(res["S"]["evaluate"]) == {f"{s}|{c}" for s in ("scalp_trend", "scalp_fade")
                                                                               for c in ("d45-55t50", "d20-30t25")}
    assert res["I"]["rule"] == "w5-10d03-12t07" and "FIN-H" in res["book"]["kinds"]
    assert res["G"]["events"]["g1_events"] > 0 and res["G"]["G2"]["pass_bar"]["events"] > 0


def test_part_f_trades_and_labels(world):
    out = world["out"]
    f = pd.read_csv(out / f"trades_round9_F_{TODAY}.csv.gz", compression="gzip")
    assert set(f["variant"]) == {"rsi2", "tom"} and set(f["universe"]) == {"U-ETF", "U-STK"}
    assert (f[f["universe"] == "U-STK"]["label"] == U.SB).all()
    assert not f["symbol"].isin(["CCC"]).any()                       # never above $5: never in U-STK's filter
    for a, b in zip(f["entry_day"], f["exit_day"]):
        assert not periods.overlaps(date.fromisoformat(a), date.fromisoformat(b))
    assert set(f[(f["variant"] == "tom") & (f["universe"] == "U-ETF")]["symbol"]) <= set(U.TOM_ETF)
    fo = pd.read_csv(out / f"trades_round9_Fopt_{TODAY}.csv.gz", compression="gzip")
    assert len(fo) and (fo["day"] >= "2024-08-01").all() and fo["dte"].between(30, 60).all() and fo["delta_est"].between(0.6, 0.8).all()


def test_part_s_and_g_files(world):
    out = world["out"]
    s = pd.read_csv(out / f"trades_round9_S_{TODAY}.csv.gz", compression="gzip")
    from sprint import scalp
    assert len(s) and set(s["symbol"]) <= {"SPY", "QQQ"} and set(s["cell"]) <= set(scalp.CELL_IDS)
    assert s["signal_idx"].between(5, 349).all() and (s["exit_idx"] > s["signal_idx"]).all()
    g2 = pd.read_csv(out / f"trades_round9_G2_{TODAY}.csv.gz", compression="gzip")
    assert (g2["day"] >= "2024-08-01").all() and (g2["entry_day"] < g2["exit_day"]).all()
    g1 = pd.read_csv(out / f"trades_round9_G1_{TODAY}.csv.gz", compression="gzip")
    assert set(g1["variant"]) <= {"news_go", "news_go_lo"} and (g1[g1["variant"] == "news_go_lo"]["side"] == "L").all()


def test_parts_f_and_g_are_deterministic(world, tmp_path):
    out2 = tmp_path / "again"
    out2.mkdir()
    rc = T9.main(["--data", str(world["root"]), "--out", str(out2), "--today", TODAY, "--parts", "F,G", "--chains-dir", str(tmp_path / "x")])
    assert rc == 0
    a = json.loads((world["out"] / f"round9_{TODAY}.json").read_text())["result"]
    b = json.loads((out2 / f"round9_{TODAY}.json").read_text())["result"]
    assert a["F"] == b["F"] and a["G"] == b["G"]


def test_trade_rows_inside_l1_or_l2_are_refused(world, tmp_path):
    src = world["out"] / "trades_round8_shares_2026-11-01.csv.gz"
    df = pd.read_csv(src, compression="gzip")
    df.loc[df.index[0], "day"] = "2024-03-04"
    out = tmp_path / "bad"
    out.mkdir()
    bad = out / "trades_round8_shares_2026-11-01.csv.gz"
    with gzip.open(bad, "wt") as f:
        df.to_csv(f, index=False)
    with pytest.raises(periods.LockedPeriod):
        T9.main(["--data", str(world["root"]), "--out", str(out), "--today", TODAY, "--parts", "H", "--round8-shares", str(bad)])
