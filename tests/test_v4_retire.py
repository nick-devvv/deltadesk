"""v4 stage 1: retired ledgers refuse NEW entries at every entry point, keep managing open trades, Kronos is off by
default, and nothing new is retired by accident. These tests run with the production config/v4.json."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import core  # noqa: E402
import engine  # noqa: E402
import fakes  # noqa: E402
import marketdata  # noqa: E402
import paper  # noqa: E402
import retire  # noqa: E402
import store  # noqa: E402

ET = core.ET
DAY = datetime(2026, 10, 28, tzinfo=ET)
RETIRED = ["paper", "research", "exit31", "gated", "orbx_swing", "orbx_atr", "orbx_2r", "orbx_ormid", "old", "news_mom",
           "inplay", "board", "earn_post", "earn_pre", "lab_orb_break", "lab_noise", "lab_v3", "spec_x_family"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    engine._cache.clear()
    yield monkeypatch
    marketdata.use(None)


def _plan(side="C"):
    return {"symbol": f"SPY261028{side}00600000", "label": f"600{side}", "premium_stop": 1.64, "stop_px": 599.0, "t1": "PDH",
            "t1_level": 603.1, "t1_px": 603.0, "be_trigger": 2.27, "breakeven_net": 2.07, "family": "TEST",
            "premium_limit": 3.0, "flat_by": "23:59"}


def test_production_config_retires_exactly_the_planned_ledgers():
    assert retire.active()
    for led in RETIRED:
        assert retire.is_retired(led), led
    for led in ("noise", "noise_v2", "noise_trend", "orb_credit", "ic_20d", "sip_orb5", "sip_orb5_x", "sip_orb15", "earn_day",
                "sip_orb5_opt", "earn_day_opt", "real"):
        assert not retire.is_retired(led), led
    assert retire.kronos_enabled() is False


def test_missing_config_never_unretires(monkeypatch, tmp_path):
    monkeypatch.setattr(retire, "FILE", tmp_path / "nope.json")
    monkeypatch.setattr(retire, "_cache", {"mtime": None, "cfg": None})
    assert retire.is_retired("paper") and retire.is_retired("lab_momo") and not retire.is_retired("noise")


@pytest.mark.parametrize("led", RETIRED)
def test_paper_buy_refuses_every_retired_ledger(env, led):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    clock.t = DAY.replace(hour=10, minute=0)
    paper.reserve_idea(led, "I1", "SPY", "C")
    pid, why = paper.buy(led, "I1", "SPY", "C", _plan(), 1, clock().isoformat())
    assert pid is None and why == retire.REASON
    assert not store.q("SELECT id FROM positions")


def test_noise_reference_ledger_still_fills(env):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    clock.t = DAY.replace(hour=10, minute=0)
    paper.reserve_idea("noise", "N1", "SPY", "C")
    pid, why = paper.buy("noise", "N1", "SPY", "C", dict(_plan(), premium_limit=None), 1, clock().isoformat())
    assert pid == "noise:N1", why


def test_old_policy_shadow_and_scanner_and_news_refuse(env):
    import news_momentum
    import policy_old
    import scanner
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    clock.t = DAY.replace(hour=10, minute=0)
    assert policy_old._open("I", "SPY", {"side": "C", "invalidation": 599.0, "family": "X", "note": ""}, "A",
                            {"symbol": "SPY261028C00600000"}) is None
    assert news_momentum.live_step(clock()) == []

    class NoChain:
        def chain(self, *a, **k):
            raise AssertionError("a retired ledger must not request a chain")
    scanner.use(NoChain())
    try:
        r = {"ticker": "NVDA", "direction": "C", "or_high": 1.0, "or_low": 0.5, "atr14": 2.0, "rvol": 3.0}
        scanner._take(DAY.date(), clock(), r, (pd.Timestamp(clock()), 1.1))
        assert "retired" in r["status"]
    finally:
        scanner.use(None)
    assert not store.q("SELECT id FROM positions")


def test_lab_refuses_before_any_request(env):
    import lab
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    clock.t = DAY.replace(hour=10, minute=0)

    class Boom:
        def quotes(self, *a):
            raise AssertionError("no quote request for a retired lab ledger")
    env.setattr(lab, "_fetch", lambda: Boom())
    s = {"family": "board_orb_break", "ticker": "NVDA", "side": "C", "id": "tape1"}
    out = lab.paper_attempt(s, clock())
    assert out.startswith("SKIP") and "retired" in out


def test_autopilot_skips_retired_strategies(env, monkeypatch):
    import autopilot
    for fn in ("earn_post", "earn_pre", "board"):
        monkeypatch.setattr(autopilot, fn, lambda *a, **k: (_ for _ in ()).throw(AssertionError("retired strategy ran")))
    store.kv_set(f"earn_cal_refreshed:{DAY.date()}", True)      # no background calendar thread in this test
    autopilot.step(DAY.replace(hour=10, minute=0))


def test_engine_day_records_v3_candidates_but_fills_no_retired_ledger(env):
    import entrygate
    import test_v3 as T
    env.setattr(entrygate, "cfg", lambda: dict(entrygate.DEFAULTS, zone_atr5=3.0, min_rr=2.0))
    clock, fk = fakes.install(env, T.vm_path, DAY, s0=600.0)
    T.run(clock, "09:31", "10:20")
    pos = store.q("SELECT ledger FROM positions")
    assert not [p for p in pos if retire.is_retired(p["ledger"])], pos
    main = store.q("SELECT decision, limit_blocked FROM candidates WHERE portfolio IN ('paper','research')")
    assert main and not [m for m in main if m["decision"] == "ORDER"]
    assert any(retire.REASON == (m["limit_blocked"] or "") for m in main)


def test_open_trade_in_a_retired_ledger_is_still_managed_to_its_exit(env, monkeypatch):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    clock.t = DAY.replace(hour=10, minute=0)
    monkeypatch.setattr(retire, "_override", False)            # opened before v4 (retirement not yet active)
    paper.reserve_idea("paper", "OLD1", "SPY", "C")
    pid, why = paper.buy("paper", "OLD1", "SPY", "C", _plan(), 1, clock().isoformat())
    assert pid, why
    monkeypatch.setattr(retire, "_override", None)             # v4 deployed
    clock.t = DAY.replace(hour=15, minute=25, second=10)
    engine._cache.clear()
    engine._manage_open()
    p = store.pos_get(pid)
    assert p["status"] == "CLOSED" and "ALL OUT" in p["plan"]["exit_reason"]


def test_kronos_needs_the_config_flag(monkeypatch):
    import server
    monkeypatch.setenv("KRONOS", "1")
    assert server.start_kronos() is None
