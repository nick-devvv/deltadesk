"""v4 stage 5: the option-chain logger (research data, never trades). Fake providers only, no network."""
import csv
import gzip
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import chain_logger as CL  # noqa: E402
import core  # noqa: E402
import fakes  # noqa: E402
import marketdata  # noqa: E402
import schwab  # noqa: E402
import store  # noqa: E402
import v4store as S  # noqa: E402
from test_v4_index import ChainFake, WED, flat_path  # noqa: E402

ET = core.ET


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    monkeypatch.setattr(CL, "DIR", tmp_path / "chains")
    CL._state.update(rows_today={}, capped={}, last_minute=None, last_error=None)
    clock = fakes.Clock(WED.replace(hour=10, minute=0, second=5))
    monkeypatch.setattr(core, "now_et", clock)
    m1 = fakes.make_market(flat_path(WED), WED, prior_days=3)
    fk = ChainFake(m1, clock)
    fk.prio = []
    real = fk.chain

    def chain(t, side, first, through=None):
        fk.prio.append(schwab.current_priority())
        return real(t, side, first, through)
    fk.chain = chain
    marketdata.use(fk)
    yield monkeypatch, clock, fk
    marketdata.use(None)


def _rows(path):
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt") as f:
        return list(csv.DictReader(f))


def test_logs_spy_qqq_0dte_within_three_percent_in_the_research_budget(env):
    mp, clock, fk = env
    n = CL.step(clock())
    rows = _rows(CL.DIR / "2026-11-04.csv")
    assert n == len(rows) > 0
    spy = [r for r in rows if r["underlying"] == "SPY"]
    spot = float(spy[0]["spot"])
    assert all(abs(float(r["strike"]) - spot) <= 0.03 * spot + 1e-9 for r in rows)
    assert {r["type"] for r in spy} == {"C", "P"} and {r["expiry"] for r in spy} == {"2026-11-04"}
    assert {r["underlying"] for r in rows} >= {"SPY", "QQQ", "$XSP", "$SPX"}
    for k in ("bid", "ask", "delta", "quote_time", "strike", "symbol"):
        assert spy[0][k] not in (None, "")
    assert fk.prio and set(fk.prio) == {"research"}                                 # never the risk or normal class
    assert CL.step(clock()) == 0                                                    # once per minute


def test_unlisted_index_chains_are_skipped_and_logged_once(env):
    mp, clock, fk = env
    real = fk.chain
    fk.chain = lambda t, side, first, through=None: (None, "empty chain") if t.startswith("$") else real(t, side, first, through)
    CL.step(clock())
    clock.t = clock.t + timedelta(minutes=1)
    CL.step(clock())
    rows = _rows(CL.DIR / "2026-11-04.csv")
    assert {r["underlying"] for r in rows} == {"SPY", "QQQ"}
    assert len(store.q("SELECT seq FROM events WHERE text LIKE 'chain logger: $XSP not available%'")) == 1


def test_open_option_shadows_add_their_chain(env):
    mp, clock, fk = env
    exp = "2026-11-06"
    S.open_position({"id": "sip_orb5_opt:x", "ledger": "sip_orb5_opt", "book": "stocks", "kind": "option", "date": "2026-11-04",
                     "ticker": "NVDA", "direction": "long", "side": "C", "qty": 1, "entry_px": 5.0, "entry_t": store.ts(),
                     "legs": [{"symbol": "NVDA261106C00598000", "expiry": exp, "action": "buy", "qty": 1}]})
    assert ("NVDA", exp, exp) in CL.targets(clock())
    CL.step(clock())
    assert any(r["underlying"] == "NVDA" and r["expiry"] == exp for r in _rows(CL.DIR / "2026-11-04.csv"))


def test_size_cap_outside_hours_and_daily_export(env):
    mp, clock, fk = env
    clock.t = WED.replace(hour=9, minute=10)
    assert CL.step(clock()) == 0                                                    # before 09:30
    clock.t = WED.replace(hour=10, minute=0, second=5)
    first = CL.step(clock())
    mp.setattr(CL, "MAX_ROWS_DAY", first)
    clock.t = WED.replace(hour=10, minute=1, second=5)
    assert CL.step(clock()) == 0 and "row cap" in CL._state["capped"]["2026-11-04"]
    clock.t = WED.replace(hour=16, minute=6)
    CL.step(clock())
    assert not (CL.DIR / "2026-11-04.csv").exists()
    out = _rows(CL.DIR / "2026-11-04.csv.gz")
    assert len(out) == first and store.kv_get("v4_chains_export:2026-11-04")["rows"] == first


def test_leftover_days_are_exported_on_start(env):
    mp, clock, fk = env
    CL.DIR.mkdir(parents=True)
    (CL.DIR / "2026-11-03.csv").write_text(",".join(CL.FIELDS) + "\n" + ",".join(["x"] * len(CL.FIELDS)) + "\n")
    assert CL.export_leftovers(WED.date()) == 1
    assert (CL.DIR / "2026-11-03.csv.gz").exists() and not (CL.DIR / "2026-11-03.csv").exists()


def test_chain_all_parses_both_sides_with_one_market_data_request(monkeypatch):
    calls = []

    def fake_get(path, params):
        calls.append((path, params))
        leg = lambda k, t: [{"symbol": f"SPY   261104{t}00{k}000", "strikePrice": float(k), "bid": 1.0, "ask": 1.1, "last": 1.05,
                             "totalVolume": 5, "openInterest": 9, "delta": 0.5 if t == "C" else -0.5, "gamma": 0.1, "volatility": 15.0,
                             "quoteTimeInLong": 1793800000000}]
        return {"underlyingPrice": 600.0, "callExpDateMap": {"2026-11-04:0": {"600.0": leg(600, "C")}},
                "putExpDateMap": {"2026-11-04:0": {"600.0": leg(600, "P")}}}, None
    monkeypatch.setattr(schwab, "_get", fake_get)
    rows, err = schwab.chain_all("SPY", "2026-11-04")
    assert len(calls) == 1 and calls[0][0] == "/marketdata/v1/chains" and calls[0][1]["contractType"] == "ALL"
    assert {r["type"] for r in rows} == {"C", "P"} and rows[0]["underlying"] == 600.0 and rows[0]["iv"] == pytest.approx(0.15)


def test_chain_status_over_http(env, monkeypatch):
    import json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    import server
    mp, clock, fk = env
    CL.step(clock())
    monkeypatch.setattr(server, "DESK_TOKEN", "")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/api/v4/chains") as r:
            d = json.loads(r.read())
        assert d["rows_today"] > 0 and d["caps"]["rows_per_day"] == CL.MAX_ROWS_DAY and d["version"] == CL.VERSION
    finally:
        srv.shutdown()
