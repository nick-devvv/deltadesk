"""Round 9 pull (tools/sprint_pull9.py) with fake HTTP: every L1/L2 date and multi-day window is refused before any request,
stages resume from their .done markers (a dropped connection then a re-run gives the same files), every Alpaca request goes
through the rate limiter and every SEC request through the 10-a-second throttle, only the asset list is ever read from the
trading host, and the SEC user agent is never printed. Synthetic data only."""
import gzip
import json
import os
from datetime import date

import pandas as pd
import pytest

import sprint_synth9 as S9
import pull_alpaca as PA
import sprint_pull9 as P9
from sprint import edgar as E, periods, universe as U


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = tmp_path / "data" / "alpaca"
    root.mkdir(parents=True)
    m = S9.Market()
    fa = S9.FakeAlpaca(m)
    monkeypatch.setattr(PA, "_http", fa)
    monkeypatch.setattr(PA, "MAX_PER_MIN", 10 ** 9)
    monkeypatch.setattr(PA, "ROOT", root)
    monkeypatch.setenv("ALPACA_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET", "s")
    seen = []
    monkeypatch.setattr(P9, "trading_http", lambda url, h: (seen.append(url), m.assets())[1])
    return root, m, fa, seen


def test_check_window_refuses_locked_dates_and_windows():
    P9.check_window(date(2024, 1, 2), date(2024, 1, 31))
    P9.check_window(date(2024, 8, 1), date(2026, 6, 30))
    for a, b in ((date(2024, 1, 29), date(2024, 2, 2)), (date(2024, 7, 31), date(2024, 8, 2)), (date(2026, 6, 29), date(2026, 7, 1)),
                 (date(2024, 3, 1), date(2024, 3, 1)), (date(2023, 12, 1), date(2024, 9, 1))):
        with pytest.raises(periods.LockedPeriod):
            P9.check_window(a, b)
    days = P9.index_days()
    assert days[0] == E.INDEX_FROM and days[-1] == E.INDEX_TO and not any(periods.overlaps(d, d) for d in days)
    assert all(d.weekday() < 5 for d in days)


def test_assets_and_daily_resume_and_never_touch_locked_dates(env):
    root, m, fa, seen = env
    us = P9.pull_assets(root, print)
    assert us["symbols"] == ["AAA", "BBB", "CCC", "DDD"] and set(us["excluded"]) == {"EEE", "FFF", "GGG", "SPY", "HHH"}
    assert seen == [P9.ASSETS_URL] and P9.pull_assets(root, print)["symbols"] == us["symbols"] and len(seen) == 1
    syms = ["SPY", "AAA", "BBB"]
    calls0 = len(fa.calls)
    res = P9.pull_daily(syms, root, print, batch=2)
    assert res["pulled"] == 6 and len(fa.calls) > calls0          # FakeAlpaca asserts no locked date was asked for
    df = U.read_daily9("BBB", "raw", root)
    adj = U.read_daily9("BBB", "split", root)
    d0 = date(2018, 3, 1)
    assert df.loc[d0, "c"] == pytest.approx(adj.loc[d0, "c"] * 4.0, rel=1e-3)   # raw before the split, adjusted after
    assert not any(periods.overlaps(d, d) for d in df.index) and df.index.min() >= U.DAILY_FROM
    n = len(fa.calls)
    assert P9.pull_daily(syms, root, print, batch=2)["skipped"] == 6 and len(fa.calls) == n


def test_daily_interrupted_then_resumed_gives_the_same_files(env, tmp_path, monkeypatch):
    root, m, fa, _ = env
    syms = ["AAA", "BBB", "DDD", "SPY"]
    ref = P9.pull_daily(syms, root, print, batch=1)
    good = {s: U.read_daily9(s, "split", root) for s in syms}
    root2 = tmp_path / "second" / "alpaca"
    flaky = S9.FakeAlpaca(m, fail_after=5)
    monkeypatch.setattr(PA, "_http", flaky)
    monkeypatch.setattr(PA.time, "sleep", lambda s: None)
    with pytest.raises(ConnectionError):
        P9.pull_daily(syms, root2, print, batch=1)
    done = list((root2 / "daily9" / "raw").glob("*.done"))
    assert 0 < len(done) < 4
    monkeypatch.setattr(PA, "_http", S9.FakeAlpaca(m))
    P9.pull_daily(syms, root2, print, batch=1)
    for s in syms:
        pd.testing.assert_frame_equal(U.read_daily9(s, "split", root2), good[s])
    assert ref["pulled"] == 8


def test_every_alpaca_request_goes_through_the_rate_limiter(env, monkeypatch):
    root, m, fa, _ = env
    n = {"k": 0}
    real = PA._throttle
    monkeypatch.setattr(PA, "_throttle", lambda: (n.__setitem__("k", n["k"] + 1), real())[1])
    P9.pull_daily(["AAA", "SPY"], root, print, batch=1)
    assert n["k"] == len(fa.calls) > 0
    import re
    src = open(PA.__file__).read()
    assert int(re.search(r"^MAX_PER_MIN = (\d+)", src, re.M).group(1)) <= 200   # the real limiter stays under the free 200 a minute


def test_multi_symbol_requests_are_batched_by_100(env):
    root, m, fa, _ = env
    n = len(fa.calls)
    syms = [f"Z{k:03d}" for k in range(250)]
    P9._multi_bars("/v2/stocks/bars", syms, {"timeframe": "1Min", "start": P9._utc(date(2025, 3, 4), "09:30"),
                                             "end": P9._utc(date(2025, 3, 4), "09:35"), "limit": 10000}, "bars")
    new = fa.calls[n:]
    assert len(new) == 3 and all(len(u.split("symbols=")[1].split("&")[0].split("%2C")) <= 100 for u in new)


def test_trading_host_is_used_for_the_asset_list_only(env, monkeypatch):
    root, m, fa, seen = env
    assert P9.ASSETS_URL.startswith("https://paper-api.alpaca.markets/v2/assets?")
    with pytest.raises(RuntimeError):
        PA._guard("https://paper-api.alpaca.markets/v2/orders")
    monkeypatch.setattr(P9, "ASSETS_URL", "https://paper-api.alpaca.markets/v2/orders?x=1")
    with pytest.raises(RuntimeError):
        P9.get_assets()
    assert seen == []


def test_edgar_index_and_headers_throttled_resumable_and_unlocked(env):
    root, m, fa, _ = env
    P9.pull_assets(root, print)
    P9.pull_daily(list(U.U_ETF[:1]) + ["AAA", "BBB", "CCC", "DDD"], root, print)
    sec, th = S9.FakeSEC(m), S9.NoThrottle()
    r = P9.pull_edgar_index(root, print, http=sec, throttle=th)
    assert th.calls == len(sec.calls) and r["fetched"] == len(P9.index_days()) and r["rows_8k"] > 0
    n = len(sec.calls)
    assert P9.pull_edgar_index(root, print, http=sec, throttle=th)["fetched"] == 0 and len(sec.calls) == n
    panel = P9.ustk_panel(root, print)
    assert "CCC" not in panel.symbols                               # never above $5: never eligible
    h = P9.pull_edgar_headers(root, print, http=sec, throttle=th, panel=panel)
    assert h["fetched"] == h["targets"] > 0 and h["missing"] == 0
    recs = P9.read_headers(root)
    assert all(r["accepted"] and r["form"] == "8-K" for r in recs)
    assert not any(r["cik"] == S9.CIK["CCC"] for r in recs)
    with open(P9.edgar_root(root) / "headers.jsonl", "a") as f:
        f.write('{"acc": "torn')                                    # an interrupted write
    assert len(P9.read_headers(root)) == len(recs)
    n = len(sec.calls)
    assert P9.pull_edgar_headers(root, print, http=sec, throttle=th, panel=panel)["fetched"] == 0 and len(sec.calls) == n


def test_fopt_and_g2_refuse_windows_touching_locked_periods(env):
    root, m, fa, _ = env
    n = len(fa.calls)
    r = P9.pull_fopt(root, print, targets=[("SPY", date(2024, 1, 30), date(2024, 8, 2), 480.0, "rsi2"),
                                            ("SPY", date(2026, 6, 29), date(2026, 7, 1), 600.0, "tom")])
    assert r["refused"] == 2 and len(fa.calls) == n
    syms = P9.fopt_symbols("SPY", date(2025, 3, 3), 600.0)
    exps = {s[3:9] for s in syms}
    assert all(s[9] == "C" for s in syms) and "250402" in exps and "250502" in exps and "250401" not in exps
    with pytest.raises(periods.LockedPeriod):
        P9.pull_weekly(root, print, a=date(2024, 7, 1), b=date(2024, 8, 5))


def test_main_status_and_missing_user_agent(env, monkeypatch, capsys, tmp_path):
    root, m, fa, _ = env
    assert P9.main(["--root", str(root), "--status"]) == 0
    assert len(fa.calls) == 0
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    rc = P9.main(["--root", str(root), "--only", "edgar_index", "--sec-env-file", str(tmp_path / "none.env")])
    out = capsys.readouterr().out
    assert rc == 3 and "SEC_USER_AGENT is not set" in out
    f = tmp_path / "desk.env"
    f.write_text("SEC_USER_AGENT=Desk Research contact-at-example\n")
    monkeypatch.setattr(E, "default_http", S9.FakeSEC(m))
    monkeypatch.setattr(E, "Throttle", S9.NoThrottle)
    rc = P9.main(["--root", str(root), "--only", "edgar_index", "--sec-env-file", str(f)])
    out = capsys.readouterr().out
    assert rc == 0 and "SEC user agent: set (from the desk env file; not shown)" in out and "Desk Research" not in out
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
