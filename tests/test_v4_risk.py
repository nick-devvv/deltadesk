"""v4 stage 6: the shared risk layer (hard-coded limits) and the v4 kill switch. Exits are never blocked."""
import json
import sys
import threading
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import core  # noqa: E402
import fakes  # noqa: E402
import marketdata  # noqa: E402
import store  # noqa: E402
import v4common as C  # noqa: E402
import v4exec  # noqa: E402
import v4risk as R  # noqa: E402
import v4store as S  # noqa: E402
from test_v4_index import ChainFake, WED, FOMC, flat_path  # noqa: E402

ET = core.ET


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    clock = fakes.Clock(WED.replace(hour=10, minute=30))
    monkeypatch.setattr(core, "now_et", clock)
    fk = ChainFake(fakes.make_market(flat_path(WED), WED, prior_days=2), clock)
    marketdata.use(fk)
    yield monkeypatch, clock, fk
    marketdata.use(None)


def _pos(i, ledger="sip_orb5", book="stocks", ticker=None, direction="long", kind="shares", status="OPEN", realized=0.0,
         mtm=None, legs=None, entry=50.0, date="2026-11-04"):
    rec = {"id": f"{ledger}:{i}", "ledger": ledger, "book": book, "kind": kind, "date": date, "ticker": ticker or f"T{i}",
           "direction": direction, "side": direction if kind == "shares" else "C", "qty": 10, "entry_px": entry,
           "entry_t": f"{date}T10:00:00-05:00", "legs": legs or [{"symbol": ticker or f"T{i}", "action": "buy", "qty": 10}],
           "plan": {"mtm": mtm} if mtm is not None else {}, "fees": 0.0}
    S.open_position(rec)
    if status == "CLOSED":
        S.close_position(rec["id"], entry + realized / 10, "test")
    return rec["id"]


def test_one_position_per_symbol_per_ledger_and_symbol_cap(env):
    _pos(1, ticker="NVDA")
    assert "one per symbol per ledger" in R.admit("sip_orb5", "stocks", "NVDA", "long")
    assert R.admit("sip_orb15", "stocks", "NVDA", "long") is None
    for i, led in enumerate(("sip_orb15", "sip_orb5_x", "earn_day")):
        _pos(10 + i, ledger=led, book="catalyst" if led == "earn_day" else "stocks", ticker="NVDA")
    assert "NVDA cap" in R.admit("noise_v2", "index", "NVDA", "long")


def test_book_desk_and_same_direction_caps(env, monkeypatch):
    monkeypatch.setitem(R.LIMITS, "book_max_same_direction", dict(R.LIMITS["book_max_same_direction"], stocks=3))
    for i in range(3):
        _pos(i, direction="long")
    assert "same-direction cap" in R.admit("sip_orb15", "stocks", "NEW", "long")
    assert R.admit("sip_orb15", "stocks", "NEW", "short") is None                      # the other direction is fine
    monkeypatch.setitem(R.LIMITS, "book_max_open", dict(R.LIMITS["book_max_open"], stocks=4))
    _pos(3, direction="short")
    assert "stocks book cap" in R.admit("sip_orb15", "stocks", "NEW", "short")
    monkeypatch.setitem(R.LIMITS, "desk_max_open", 4)
    assert "v4 desk cap" in R.admit("noise_v2", "index", "SPY", "long")


def test_shadows_are_exempt_from_caps_but_not_from_the_kill_switch(env, monkeypatch):
    monkeypatch.setitem(R.LIMITS, "desk_max_open", 1)
    _pos(1)
    assert R.admit("sip_orb5_opt", "stocks", "T2", "long") is None
    store.kv_set("v4_enabled", False)
    assert "kill switch" in R.admit("sip_orb5_opt", "stocks", "T2", "long")


def test_daily_loss_limit_counts_realized_and_open_marks_and_stops_new_entries_only(env, monkeypatch):
    monkeypatch.setitem(R.LIMITS, "book_daily_loss_usd", dict(R.LIMITS["book_daily_loss_usd"], stocks=300.0))
    _pos(1, status="CLOSED", realized=-200.0)
    assert R.admit("sip_orb5", "stocks", "NEW", "long") is None
    pid = _pos(2, mtm=-150.0)
    assert R.book_pnl_today("stocks") == pytest.approx(-350.0)
    why = R.admit("sip_orb5", "stocks", "NEW", "long")
    assert why and "daily paper loss limit" in why
    assert R.admit("noise_v2", "index", "SPY", "long") is None                          # other books keep going
    _pos(3, ledger="sip_orb5_opt", mtm=-999.0)                                          # shadows never count toward the limit
    assert R.book_pnl_today("stocks") == pytest.approx(-350.0)
    q = {"T2": {"bid": 49.0, "ask": 49.02, "quote_time": pd.Timestamp(core.now_et()), "executable": True}}
    assert v4exec.close_now(S.get(pid), "exit after the limit", q) is not None           # exits are never blocked
    assert S.get(pid)["status"] == "CLOSED"


def test_fomc_blackout_applies_only_to_the_selling_ledgers(env):
    mp, clock, fk = env
    clock.t = FOMC.replace(hour=10, minute=30)
    assert "FOMC" in R.admit("orb_credit", "premium", "SPY", "long")
    assert "FOMC" in R.admit("ic_20d", "premium", "QQQ", "neutral")
    assert R.admit("noise_v2", "index", "SPY", "long") is None
    core.EVENTS_FILE.write_text(json.dumps({"date": "2026-11-04", "events": [{"time": "14:00", "name": "FOMC rate decision"}]}))
    clock.t = WED.replace(hour=10, minute=30)
    assert C.is_fomc_day()[0] is True and "FOMC" in R.admit("ic_20d", "premium", "SPY", "neutral")


def test_pause_and_stale_feed_block_new_entries(env):
    import health
    store.kv_set("paper_pause", True)
    assert "paused" in R.admit("sip_orb5", "stocks", "X", "long")
    store.kv_set("paper_pause", False)
    health.set_feed(False, "SPY bars stale")
    try:
        assert "stale" in R.admit("sip_orb5", "stocks", "X", "long")
    finally:
        health.set_feed(True)


def test_kill_switch_closes_every_kind_and_turns_entries_off(env):
    mp, clock, fk = env
    day = "2026-11-04"
    sym = lambda k, t: f"SPY261104{t}{int(k * 1000):08d}"
    S.open_position({"id": "noise_v2:k1", "ledger": "noise_v2", "book": "index", "kind": "option", "date": day, "ticker": "SPY",
                     "direction": "long", "side": "C", "qty": 1, "entry_px": 2.0, "entry_t": store.ts(), "fees": 0.02,
                     "legs": [{"symbol": sym(600, "C"), "action": "buy", "qty": 1, "expiry": day}], "exec_model": "noise1"})
    S.open_position({"id": "orb_credit:k2", "ledger": "orb_credit", "book": "premium", "kind": "spread", "date": day, "ticker": "SPY",
                     "direction": "long", "side": "put credit", "qty": 1, "entry_px": 0.5, "entry_t": store.ts(), "fees": 1.3,
                     "legs": [{"symbol": sym(598, "P"), "action": "sell", "qty": 1, "expiry": day},
                              {"symbol": sym(596, "P"), "action": "buy", "qty": 1, "expiry": day}], "exec_model": "spread065"})
    S.open_position({"id": "sip_orb5:k3", "ledger": "sip_orb5", "book": "stocks", "kind": "shares", "date": day, "ticker": "SPY",
                     "direction": "long", "side": "long", "qty": 10, "entry_px": 599.0, "entry_t": store.ts(), "fees": 0.0,
                     "legs": [{"symbol": "SPY", "action": "buy", "qty": 10}], "exec_model": "shares1"})
    out = R.kill("test")
    assert out["closed"] == 3 and out["pending"] == 0
    assert all(p["status"] == "CLOSED" and "KILL SWITCH" in p["exit_reason"] for p in S.positions())
    assert C.enabled() is False and "kill switch" in R.admit("noise_v2", "index", "QQQ", "long")
    R.enable(True)
    assert R.admit("noise_v2", "index", "QQQ", "long") is None


def test_kill_switch_never_touches_legacy_ledgers_and_runs_over_http(env, monkeypatch):
    import paper
    import retire
    import server
    mp, clock, fk = env
    monkeypatch.setattr(retire, "_override", False)
    paper.reserve_idea("noise", "N1", "SPY", "C")
    plan = {"symbol": "SPY261104C00600000", "label": "600C", "premium_stop": 0.5, "stop_px": 599.0, "t1": None, "t1_level": None,
            "t1_px": None, "be_trigger": None, "breakeven_net": None, "family": "NOISE_BAND", "flat_by": None}
    clock.t = WED.replace(hour=10, minute=30, second=5)
    pid, why = paper.buy("noise", "N1", "SPY", "C", plan, 1, WED.replace(hour=10, minute=30).isoformat())
    assert pid, why
    _pos(1)
    monkeypatch.setattr(server, "DESK_TOKEN", "")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/v4/kill", data=b'{"reason":"test"}',
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as r:
            d = json.loads(r.read())
        assert d["ok"] and d["closed"] + d["pending"] == 1
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/api/v4/risk") as r:
            st = json.loads(r.read())
        assert st["v4_enabled"] is False and st["limits"]["desk_max_open"] == R.LIMITS["desk_max_open"]
    finally:
        srv.shutdown()
    assert store.pos_get(pid)["status"] == "OPEN"                                       # the noise reference ledger untouched
    assert store.kv_get("paper_enabled", True) is True


def test_limits_are_code_not_config():
    src = (ROOT / "v4risk.py").read_text()
    assert "LIMITS = {" in src and "json.load" not in src and "kv_get(\"v4_limits" not in src
