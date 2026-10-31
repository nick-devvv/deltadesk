"""v3.5 tests: atomic paper lifecycle (C6), and the integrity fixes that follow it. No network, no AI."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import core  # noqa: E402
import engine  # noqa: E402
import fakes  # noqa: E402
import marketdata  # noqa: E402
import paper  # noqa: E402
import store  # noqa: E402

ET = core.ET
DAY = datetime(2026, 10, 28, tzinfo=ET)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    engine._cache.clear()
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    yield monkeypatch
    marketdata.use(None)


def _plan(side="C"):
    return {"symbol": f"SPY261028{side}00600000", "label": f"600{side}", "premium_stop": 1.64, "stop_px": 599.0, "t1": "PDH",
            "t1_level": 603.1, "t1_px": 603.0, "be_trigger": 2.27, "breakeven_net": 2.07, "family": "TEST",
            "premium_limit": 3.0, "flat_by": "23:59"}


def _world(env):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    clock.t = DAY.replace(hour=10, minute=0)
    engine._cache.clear()
    return clock, fk


def _counts(pid):
    return {"pos": len(store.q("SELECT id FROM positions WHERE id=?", (pid,))),
            "orders": len(store.q("SELECT client_id FROM orders WHERE position_id=?", (pid,))),
            "events": len(store.q("SELECT seq FROM events WHERE position_id=?", (pid,))) if _has_col("events", "position_id") else None,
            "filled": len(store.q("SELECT idea FROM ideas WHERE position_id=? AND status='FILLED'", (pid,)))}


def _has_col(table, col):
    return any(r["name"] == col for r in store.q(f"PRAGMA table_info({table})"))


# ================================================================ C6 atomic lifecycle
def test_tx_rolls_back_everything_on_a_crash(env):
    store.conn()
    with pytest.raises(RuntimeError):
        with store.tx():
            store.x("INSERT INTO kv(k, v) VALUES('a', '1')")
            with store.tx():                                               # nested joins the outer transaction
                store.x("INSERT INTO kv(k, v) VALUES('b', '2')")
            raise RuntimeError("crash between lifecycle steps")
    assert not store.q("SELECT k FROM kv WHERE k IN ('a','b')")
    with store.tx():
        store.x("INSERT INTO kv(k, v) VALUES('a', '1')")
    assert store.q("SELECT v FROM kv WHERE k='a'")[0]["v"] == "1"


def test_pos_insert_never_overwrites(env):
    store.conn()
    p = {"id": "paper:X", "ledger": "paper", "date": "2026-10-28", "ticker": "SPY", "contract": "600C", "symbol": "S",
         "side": "C", "qty_init": 1, "qty_open": 1, "fill": 2.0, "opened": "t", "closed": None, "status": "OPEN",
         "setup_id": "X", "grade": "A", "setup": "T", "plan": {}, "realized": 0, "mfe": 0, "mae": 0,
         "policy_version": "v", "verified": "", "notes": ""}
    store.pos_insert(p)
    with pytest.raises(Exception):
        store.pos_insert(dict(p, fill=9.0))
    assert store.pos_get("paper:X")["fill"] == 2.0


@pytest.mark.parametrize("crash_on", ["orders", "ideas", "event"])
def test_buy_crash_mid_lifecycle_then_retry_fills_exactly_once(env, crash_on):
    clock, fk = _world(env)
    paper.reserve_idea("paper", "I1", "SPY", "C")
    real_x, real_event = store.x, store.event
    state = {"armed": True}

    def x(sql, args=()):
        if state["armed"] and crash_on == "orders" and sql.lstrip().upper().startswith("INSERT INTO ORDERS"):
            state["armed"] = False
            raise RuntimeError("injected crash after the position insert")
        if state["armed"] and crash_on == "ideas" and "UPDATE ideas SET status='FILLED'" in sql:
            state["armed"] = False
            raise RuntimeError("injected crash after the order insert")
        return real_x(sql, args)

    def event(*a, **k):
        if state["armed"] and crash_on == "event":
            state["armed"] = False
            raise RuntimeError("injected crash before the event")
        return real_event(*a, **k)

    env.setattr(store, "x", x)
    env.setattr(store, "event", event)
    with pytest.raises(RuntimeError):
        paper.buy("paper", "I1", "SPY", "C", _plan(), 2, clock().isoformat())
    assert not store.q("SELECT id FROM positions")                             # nothing half-written
    assert not store.q("SELECT client_id FROM orders")
    assert store.q("SELECT status FROM ideas WHERE idea='I1'")[0]["status"] != "FILLED"
    pid, why = paper.buy("paper", "I1", "SPY", "C", _plan(), 2, clock().isoformat())     # the retry
    assert pid == "paper:I1", why
    pid2, why2 = paper.buy("paper", "I1", "SPY", "C", _plan(), 2, clock().isoformat())   # a duplicate retry
    assert pid2 is None and "never fills twice" in why2
    c = _counts(pid)
    assert c["pos"] == 1 and c["orders"] == 1 and c["filled"] == 1
    p = store.pos_get(pid)
    fee = p["plan"]["fees_side"]
    assert p["realized"] == round(-fee * 2, 2)                                   # the entry fee is counted once


def test_sell_crash_then_retry_exits_once_and_counts_fee_once(env):
    clock, fk = _world(env)
    paper.reserve_idea("paper", "I2", "SPY", "C")
    pid, why = paper.buy("paper", "I2", "SPY", "C", _plan(), 1, clock().isoformat())
    assert pid, why
    real_event = store.event
    state = {"armed": True}

    def event(kind, *a, **k):
        if state["armed"] and "exit" in kind:
            state["armed"] = False
            raise RuntimeError("injected crash after the exit order")
        return real_event(kind, *a, **k)

    env.setattr(store, "event", event)
    with pytest.raises(RuntimeError):
        paper.sell(store.pos_get(pid), 1, "test exit")
    p = store.pos_get(pid)
    assert p["status"] == "OPEN" and p["qty_open"] == 1                           # the exit rolled back whole
    assert len(store.q("SELECT client_id FROM orders WHERE position_id=? AND side='sell'", (pid,))) == 0
    stale = store.pos_get(pid)
    qty, px = paper.sell(stale, 1, "test exit")
    assert qty == 1
    again = paper.sell(stale, 1, "test exit")                                      # a retry with the stale copy
    assert again[0] == 0
    p = store.pos_get(pid)
    sells = store.q("SELECT client_id FROM orders WHERE position_id=? AND side='sell'", (pid,))
    assert p["status"] == "CLOSED" and p["qty_open"] == 0 and len(sells) == 1
    fee = p["plan"]["fees_side"]
    assert p["realized"] == round((px - p["fill"]) * 100 - 2 * fee, 2)            # one entry fee + one exit fee


def test_full_ledger_ids_are_unique_across_ledgers_with_the_same_prefix(env):
    clock, fk = _world(env)
    a, b = "lab_orb_break", "lab_vwap_macd"                                      # both used to be "LA-<idea>"
    for led in (a, b):
        paper.reserve_idea(led, "SAME", "SPY", "C")
    sig = (clock() - timedelta(seconds=5)).isoformat()                           # strict ledgers: decision latency
    pa, wa = paper.buy(a, "SAME", "SPY", "C", _plan(), 1, sig)
    pb, wb = paper.buy(b, "SAME", "SPY", "C", _plan(), 1, sig)
    assert pa and pb and pa != pb, (wa, wb)
    assert {store.pos_get(pa)["ledger"], store.pos_get(pb)["ledger"]} == {a, b}


def test_release_never_unfills_a_filled_idea(env):
    clock, fk = _world(env)
    paper.reserve_idea("paper", "I3", "SPY", "C")
    pid, _ = paper.buy("paper", "I3", "SPY", "C", _plan(), 1, clock().isoformat())
    paper.release_idea("paper", "I3", "late release")
    assert store.q("SELECT status FROM ideas WHERE idea='I3'")[0]["status"] == "FILLED"


def test_old_position_ids_still_load(env):
    store.conn()
    store.pos_save({"id": "PA-OLD", "ledger": "paper", "date": "2026-10-27", "ticker": "SPY", "contract": "600C", "symbol": "S",
                    "side": "C", "qty_init": 1, "qty_open": 0, "fill": 2.0, "opened": "t", "closed": "t", "status": "CLOSED",
                    "setup_id": "OLD", "grade": "A", "setup": "T", "plan": {"x": 1}, "realized": 5.0, "mfe": 0, "mae": 0,
                    "policy_version": "v", "verified": "", "notes": ""})
    assert store.pos_get("PA-OLD")["plan"] == {"x": 1}


def test_a_stale_copy_cannot_reopen_a_closed_trade(env):
    clock, fk = _world(env)
    paper.reserve_idea("paper", "I4", "SPY", "C")
    pid, _ = paper.buy("paper", "I4", "SPY", "C", _plan(), 1, clock().isoformat())
    stale = store.pos_get(pid)
    paper.sell(store.pos_get(pid), 1, "exit")
    stale["mfe"] = 12.5
    store.pos_save(stale)                                                       # e.g. a manager that loaded it earlier
    p = store.pos_get(pid)
    assert p["status"] == "CLOSED" and p["qty_open"] == 0 and p["mfe"] == 12.5
