"""v4: the `old` ledger (policy_old.py, frozen 2026-10-28.3 rules) stays ACTIVE as a legacy forward test (not from a
published source). Its behavior must be byte-identical to the code before the v4 retirements.

The golden file tests/fixtures/old_golden_v35.json was generated from the v3.5 code (commit 3877798, before the v4
retirement stage) by replaying this fixture day through engine.tick() once per minute. The test replays the same day
on the current code with the production config/v4.json and compares every old-ledger candidate, fill, exit and order.
Regenerate only on purpose:  REGEN_OLD_GOLDEN=1 python3 -m pytest -q tests/test_v4_old_regression.py
"""
import json
import os
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
import store  # noqa: E402
import test_v3 as T  # noqa: E402

ET = core.ET
DAY = T.DAY                                             # Wed 2026-10-28
GOLDEN = ROOT / "tests" / "fixtures" / "old_golden_v35.json"


def run_day(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    engine._cache.clear()
    clock, fk = fakes.install(monkeypatch, T.vm_path, DAY, s0=600.0)
    t, stop = DAY.replace(hour=9, minute=31), DAY.replace(hour=15, minute=31)
    while t <= stop:
        clock.t = t
        engine._cache.clear()
        engine.tick()
        t += timedelta(minutes=1 if t.hour < 11 or t.strftime("%H:%M") >= "15:20" else 5)
    pos = []
    for p in store.positions(ledger="old"):
        pos.append({k: p[k] for k in ("id", "ledger", "date", "ticker", "contract", "symbol", "side", "qty_init", "qty_open", "fill",
                                      "opened", "closed", "status", "setup_id", "grade", "setup", "realized", "policy_version", "notes")}
                   | {"plan": {k: p["plan"].get(k) for k in ("stop", "invalidation", "be_hit", "t1_done", "entry_px", "window", "exit_reason")}})
    ids = [p["id"] for p in pos]
    orders = [r for r in store.q("SELECT client_id, position_id, ts, side, qty, status, filled_qty, filled_price, reason FROM orders "
                                 "ORDER BY client_id") if r["position_id"] in ids]
    cands = store.q("SELECT id, date, decision_t, ticker, side, family, decision, reasons, policy_version FROM candidates "
                    "WHERE portfolio='old' ORDER BY id")
    ideas = store.q("SELECT idea, ticker, side, created, status, position_id FROM ideas WHERE portfolio='old' ORDER BY idea")
    return json.loads(json.dumps({"positions": pos, "orders": orders, "candidates": cands, "ideas": ideas}, default=str))


def test_old_ledger_still_opens_trades_exactly_as_before(monkeypatch, tmp_path):
    got = run_day(monkeypatch, tmp_path)
    marketdata.use(None)
    if os.environ.get("REGEN_OLD_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True))
        pytest.skip("golden regenerated")
    want = json.loads(GOLDEN.read_text())
    assert want["positions"], "the fixture day must make the old ledger open at least one trade"
    assert got["candidates"] == want["candidates"]
    assert got["positions"] == want["positions"]
    assert got["orders"] == want["orders"]
    assert got["ideas"] == want["ideas"]


def test_old_is_not_retired_and_is_labeled_a_legacy_forward_test():
    import retire
    assert retire.active() and not retire.is_retired("old")
    assert retire.legacy_label("old") == "legacy forward test (not from a published source)"



def test_old_shadow_fetches_chains_only_when_it_needs_them(monkeypatch):
    import engine as E
    calls = []
    monkeypatch.setattr(E, "chain_rows", lambda t, side: (calls.append((t, side)), ([{"strike": 600}], None))[1])
    lc = E._LazyChains("SPY")
    assert calls == []                                          # nothing fetched until the scan reads a side
    assert lc.get("C") == [{"strike": 600}] and lc.get("C") == [{"strike": 600}] and calls == [("SPY", "C")]
    assert lc.get("P") and calls == [("SPY", "C"), ("SPY", "P")]
    src = (ROOT / "engine.py").read_text()
    assert 'policy_old.scan(t, s, _LazyChains(t))' in src
