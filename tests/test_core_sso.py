"""core_sso: the T44 SSO trend core with the SGOV park (paper, held, isolated "score" risk book). Near-close trading,
the park swap in both directions (sale first), restart safety, the switch, risk isolation and the wiring. Fake Schwab
quotes and daily bars only, no network."""
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import core  # noqa: E402
import core_sso as K  # noqa: E402
import core_trend  # noqa: E402
import fakes  # noqa: E402
import marketdata  # noqa: E402
import scanner  # noqa: E402
import store  # noqa: E402
import v4risk  # noqa: E402
import v4store as S  # noqa: E402
from test_core_trend import Prov, daily, drop_after, rising  # noqa: E402

ET = core.ET
D1, D2, D3 = date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 30)


class Fake:
    def __init__(self, clock):
        self.clock, self.px, self.dead, self.ready_ = clock, {"SSO": 100.0, "SGOV": 100.0}, set(), True
        self.bars = {"SPY": daily(rising())}

    def ready(self):
        return self.ready_

    def daily(self, t):
        return self.bars[t]

    def quotes(self, ts):
        now = pd.Timestamp(self.clock())
        out = {}
        for t in ts:
            if t in self.dead:
                continue
            last = self.px.get(t, 100.0)
            out[t] = {"last": last, "bid": round(last - 0.01, 2), "ask": round(last + 0.01, 2),
                      "quote_ms": (now - pd.Timedelta(seconds=0.5)).value // 10 ** 6}
        return out, None


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    import health
    monkeypatch.setitem(health._feed, "ok", None)
    K._state.update(status="idle", last_error=None, mark_t=None, plan_try=None)
    monkeypatch.setattr(K, "switch_on", lambda: True)
    clock = fakes.Clock(datetime(2026, 11, 23, 8, 0, tzinfo=ET))
    monkeypatch.setattr(core, "now_et", clock)
    prov = Prov()
    marketdata.use(prov)
    f = Fake(clock)
    scanner.use(f)
    prov.world = f
    yield monkeypatch, clock, f
    scanner.use(None)
    marketdata.use(None)


def run(clock, day, a, b, step_s=5):
    def at(s):
        hh, mm = int(s[:2]), int(s[3:5])
        ss = int(s[6:]) if len(s) > 5 else 0
        return datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=ET)
    t, end = at(a), at(b)
    while t <= end:
        clock.t = t
        K.step(t)
        t += timedelta(seconds=step_s)


def decision(h, day):
    r = [d for d in S.decisions(ledger=K.LEDGER, kind="entry") if d["id"] == f"{K.LEDGER}:{h}:{day}"]
    return r[0] if r else None


def opens(ticker=None):
    return [p for p in S.positions(ledger=K.LEDGER, status="OPEN") if ticker is None or p["ticker"] == ticker]


def test_same_trend_rule_as_core_trend_and_targets():
    import numpy as np
    c = list(np.linspace(100, 200, 260)) + [150.0] * 5
    a, _ = K.trend_states(c)
    b, _ = core_trend.trend_states(c)
    assert a.dropna().tolist() == b.dropna().tolist()
    assert K.targets(3000.0, 500.0, {"S": 1, "P": 0}) == {"S": 3000.0, "P": 0.0}
    assert K.targets(3000.0, 500.0, {"S": 0, "P": 1}) == {"S": 0.0, "P": 2500.0}       # no T-bills on margin


def test_in_buys_sso_only_near_the_close_and_holds(env):
    mp, clock, f = env
    run(clock, D1, "15:40", "15:49:55")
    assert not opens()
    run(clock, D1, "15:50", "15:51")
    assert [p["ticker"] for p in opens()] == ["SSO"] and opens()[0]["book"] == "score"
    p = opens("SSO")[0]
    assert p["qty"] == math.floor(3000 / 100.02 * 1e4) / 1e4 and K.start_day() == str(D1)
    assert decision("S", D1)["decision"] == "ORDER" and decision("P", D1)["decision"] == "OUT"
    assert "no SGOV park needed" in decision("P", D1)["reasons"][0]
    run(clock, D2, "15:50", "15:51")
    assert decision("S", D2)["decision"] == "HOLD" and len(opens()) == 1


def test_trend_out_sells_sso_then_parks_in_sgov_and_back(env):
    mp, clock, f = env
    run(clock, D1, "15:50", "15:51")
    f.bars["SPY"] = drop_after(f.bars["SPY"], D1, 0.8)
    run(clock, D2, "15:50", "15:51")
    assert decision("S", D2)["decision"] == "EXIT" and decision("P", D2)["decision"] == "ORDER"
    assert [p["ticker"] for p in opens()] == ["SGOV"]
    sold = [p for p in S.positions(ledger=K.LEDGER) if p["ticker"] == "SSO"][0]
    assert sold["status"] == "CLOSED" and "trend OUT" in sold["exit_reason"]
    assert sold["exit_t"] <= opens("SGOV")[0]["entry_t"]                                      # sale first
    f.bars["SPY"] = daily(rising(a=500.0, b=900.0))                                          # strong uptrend again
    run(clock, D3, "15:50", "15:51")
    assert decision("P", D3)["decision"] == "EXIT" and decision("S", D3)["decision"] == "ORDER"
    assert [p["ticker"] for p in opens()] == ["SSO"]


def test_out_at_start_buys_only_sgov(env):
    mp, clock, f = env
    f.bars["SPY"] = drop_after(f.bars["SPY"], date(2026, 11, 16), 0.8)
    run(clock, D1, "15:50", "15:51")
    assert decision("S", D1)["decision"] == "OUT" and [p["ticker"] for p in opens()] == ["SGOV"]
    assert opens("SGOV")[0]["plan"]["target"] == pytest.approx(3000.0)


def test_restart_never_buys_twice(env):
    mp, clock, f = env
    run(clock, D1, "15:50", "15:50:05")
    K._state.update(status="idle", mark_t=None, plan_try=None)
    run(clock, D1, "15:50:10", "15:55")
    assert len(S.positions(ledger=K.LEDGER)) == 1


def test_switch_off_blocks_buys_but_exits_still_run(env):
    mp, clock, f = env
    run(clock, D1, "15:50", "15:51")
    mp.setattr(K, "switch_on", lambda: False)
    f.bars["SPY"] = drop_after(f.bars["SPY"], D1, 0.8)
    run(clock, D2, "15:50", "15:51")
    assert decision("S", D2)["decision"] == "EXIT" and decision("P", D2)["decision"] == "SWITCH OFF" and not opens()


def test_score_book_isolated_multi_day_no_daily_stop_and_kill(env):
    mp, clock, f = env
    lim = v4risk.LIMITS
    assert "score" in lim["isolated_books"] and "score" in lim["multi_day_books"] and "score" not in lim["book_daily_loss_usd"]
    assert lim["book_max_open"]["score"] == 2
    run(clock, D1, "15:50", "15:51")
    r = v4risk.kill("test")
    assert r["closed"] >= 1 and not opens()
    run(clock, D2, "15:50", "15:51")
    assert decision("S", D2)["decision"] == "BLOCKED-RISK"


def test_wiring_report_api_release_health_page_config(env):
    mp, clock, f = env
    run(clock, D1, "15:50", "15:51")
    import json
    import health
    import release
    import v4api
    import v4report
    d = v4report.overview("2026-11-02")
    row = {b["book"]: b for b in d["books"]}["score"]["ledgers"][0]
    assert row["ledger"] == "core_sso" and row["open"] == 1 and row["evidence"].startswith("PAPER")
    assert row["backtest"]["t44_2022_2025"]["label"].startswith("BACKTEST") and d["sso_core_account"]["start"] == str(D1)
    st = v4api.get("/api/v4/score", {})
    assert st["version"] == K.VERSION and st["signals"]["S"]["state"] == 1 and st["signals"]["P"]["state"] == 0
    assert release.component_versions()["core_sso.VERSION"] == K.VERSION and "v4-core-sso" in release.RELEASE_ID
    assert "v4score" in health.WORKERS and 'score: "SSO trend core"' in (ROOT / "index.html").read_text()
    cfg = json.loads((ROOT / "config" / "v4.json").read_text())
    assert cfg["core_sso"] is True and cfg["core_trend"] is False


def test_no_order_path_in_the_module():
    code = (ROOT / "core_sso.py").read_text().split('"""', 2)[2]
    assert "overnight(" not in code and "import broker" not in code and "alpaca" not in code.lower()
    assert "/trader" not in code and "place_order" not in code
