"""v4 regression: the `noise` reference ledger must behave byte-for-byte the same after the v4 changes.

The golden file tests/fixtures/noise_golden_v35.json was generated from the v3.5 code (commit 62d0b15, before any v4
change) by running this exact fixture day through engine.tick() once per minute. The test replays the same day on the
current code, with the v4 retirements ACTIVE (production config), and compares every noise check (signal, bands,
VWAP, price), every noise fill, every exit and every order. Regenerate only on purpose:
    REGEN_NOISE_GOLDEN=1 python3 -m pytest -q tests/test_v4_noise_regression.py
"""
import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import core  # noqa: E402
import engine  # noqa: E402
import fakes  # noqa: E402
import marketdata  # noqa: E402
import store  # noqa: E402

ET = core.ET
DAY = datetime(2026, 10, 28, tzinfo=ET)                 # Wed
GOLDEN = ROOT / "tests" / "fixtures" / "noise_golden_v35.json"


def path(ts):
    """Up-trend from 09:35 (call signal at 10:00), a fade into VWAP (noise stop at a half-hour check), a slide below
    the lower band (put signal), then a flat afternoon into the 15:25 all-out."""
    m = ts.hour * 60 + ts.minute
    if ts.date() != DAY.date():
        return fakes.prior_path(ts.day, m, np.random.default_rng(ts.day))
    if m < 575:
        return 600.0
    if m < 660:                                         # 09:35-11:00 up 0.12/min
        return 600.0 + (m - 575) * 0.12
    if m < 690:                                         # 11:00-11:30 fade below VWAP
        return 610.2 - (m - 660) * 0.24
    if m < 780:                                         # 11:30-13:00 slide
        return 603.0 - (m - 690) * 0.078
    if m < 810:                                         # 13:00-13:30 push lower
        return 596.0 - (m - 780) * 0.05
    return 594.5 + 0.3 * math.sin((m - 810) / 9.0)      # flat afternoon


SCHEDULE = [("09:55", "10:05"), ("10:28", "10:33"), ("10:58", "11:03"), ("11:28", "11:35"), ("12:58", "13:05"),
            ("13:28", "13:33"), ("15:20", "15:31")]


def run_day(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    engine._cache.clear()
    clock, fk = fakes.install(monkeypatch, path, DAY, s0=600.0, prior_days=16, delta=0.6)
    for a, b in SCHEDULE:
        t = DAY.replace(hour=int(a[:2]), minute=int(a[3:]))
        stop = DAY.replace(hour=int(b[:2]), minute=int(b[3:]))
        while t <= stop:
            clock.t = t
            engine._cache.clear()
            engine.tick()
            t += timedelta(minutes=1)
    return snapshot()


def snapshot():
    pos = []
    for p in store.positions(ledger="noise"):
        pl = p["plan"]
        pos.append({k: p[k] for k in ("id", "ledger", "date", "ticker", "contract", "symbol", "side", "qty_init", "qty_open",
                                      "fill", "opened", "closed", "status", "setup_id", "setup", "realized", "mfe", "mae",
                                      "policy_version")}
                   | {"plan": {k: pl.get(k) for k in ("premium_stop", "stop_px", "entry_px", "noise_upper", "noise_lower",
                                                      "entry_premium", "exit_reason", "exit_px", "signal_t", "last_bid")}})
    ids = [p["id"] for p in pos]
    orders = [r for r in store.q("SELECT client_id, position_id, ts, side, qty, status, filled_qty, filled_price, reason "
                                 "FROM orders ORDER BY client_id") if r["position_id"] in ids]
    checks = {r["k"]: json.loads(r["v"]) for r in store.q("SELECT k, v FROM kv WHERE k LIKE 'noise:%' ORDER BY k")}
    ideas = store.q("SELECT portfolio, idea, date, ticker, side, created, status, position_id FROM ideas WHERE portfolio='noise' "
                    "ORDER BY idea")
    return json.loads(json.dumps({"positions": pos, "orders": orders, "checks": checks, "ideas": ideas}, default=str))


def test_noise_ledger_is_unchanged_on_a_fixture_day(monkeypatch, tmp_path):
    got = run_day(monkeypatch, tmp_path)
    marketdata.use(None)
    if os.environ.get("REGEN_NOISE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True))
        pytest.skip("golden regenerated")
    want = json.loads(GOLDEN.read_text())
    # the fixture day must exercise the paths that matter: a call and a put entry, a noise stop and the all-out
    reasons = " | ".join(str(p["plan"]["exit_reason"]) for p in want["positions"])
    assert {p["side"] for p in want["positions"]} == {"C", "P"}, reasons
    assert "NOISE STOP" in reasons and "ALL OUT" in reasons, reasons
    assert got["checks"] == want["checks"]
    assert got["positions"] == want["positions"]
    assert got["orders"] == want["orders"]
    assert got["ideas"] == want["ideas"]
