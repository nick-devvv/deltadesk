"""v4 stage 4: the news_drift event logger (research only, never trades). Fake Schwab data, no network."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import catalysts  # noqa: E402
import core  # noqa: E402
import fakes  # noqa: E402
import marketdata  # noqa: E402
import news_drift as ND  # noqa: E402
import scanner  # noqa: E402
import store  # noqa: E402
import v4store as S  # noqa: E402
from test_v4_stocks import BASE, DAY, OptProv, World  # noqa: E402

ET = core.ET


def news_path(i):
    """Flat at 50 until 10:03, then a jump on the news (10:03 bar closes up), then drifting up."""
    if i < 33:
        return 50.0
    if i == 33:
        return 50.5
    return 50.5 + 0.01 * (i - 33)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    clock = fakes.Clock(DAY.replace(hour=10, minute=2, second=30))
    monkeypatch.setattr(core, "now_et", clock)
    marketdata.use(OptProv(clock))
    monkeypatch.setattr(scanner, "universe", lambda: ["ACME"])
    w = World(clock, {"ACME": dict(BASE, rv=1.0, path=news_path), "SPY": dict(BASE, rv=1.0, path=news_path)})
    w.today["ACME"].loc[w.today["ACME"].index >= pd.Timestamp(DAY.replace(hour=10, minute=3)), "Volume"] *= 6
    scanner.use(w)
    yield clock, w
    scanner.use(None)
    marketdata.use(None)


def _ingest(ticker, published, now, desk=True, url="https://www.sec.gov/Archives/edgar/data/1/x.htm"):
    return catalysts.ingest([{"tickers": [ticker], "headline": f"{ticker} filed an 8-K: 2.02 results of operations",
                              "category": "earnings", "published_at": published, "sources": [{"url": url, "published_at": published}]}],
                            "SEC EDGAR" if desk else "via Chart", now=now, retrieved_by_desk=desk)


def test_event_lifecycle_from_verified_catalyst_to_resolved_moves(env):
    clock, w = env
    _ingest("ACME", "2026-11-04T10:02:00-05:00", clock())
    ND.discover(clock())
    r = ND.rows()[0]
    assert r["status"] == "PENDING" and r["ticker"] == "ACME"
    assert r["t0"] == clock().isoformat() and r["news_t"].startswith("2026-11-04T10:02:00")     # t0 = when the desk knew
    clock.t = DAY.replace(hour=10, minute=4, second=5)                    # the 10:03 bar just finished: entry bar opening
    ND.step(clock())
    r = ND.rows()[0]
    assert r["status"] == "PENDING" and r["half_spread"] == pytest.approx(0.01)
    clock.t = DAY.replace(hour=10, minute=8, second=40)
    ND.step(clock())
    r = ND.rows()[0]
    assert r["status"] == "OBSERVED" and r["first_bar_t"].startswith("2026-11-04T10:03") and r["first_bar_dir"] == "up"
    assert r["entry_t"].startswith("2026-11-04T10:04") and r["entry_px"] == pytest.approx(50.5)
    assert r["rv5"] == pytest.approx(12.0, rel=0.01) and "5-minute grid" in r["rv5_basis"]   # 600k vs 50k per 5 min
    clock.t = DAY.replace(hour=16, minute=6)
    ND.step(clock())
    r = ND.rows()[0]
    assert r["status"] == "RESOLVED"
    m15 = r["moves"]["15"]
    want = w.today["ACME"].loc[pd.Timestamp(DAY.replace(hour=10, minute=18)), "Close"] / 50.5 - 1
    assert m15["raw"] == pytest.approx(want, abs=1e-6) and m15["net"] == pytest.approx(want - 0.01 / 50.5, abs=1e-6)
    assert set(r["moves"]) == {"15", "30", "60", "120"}
    assert not S.positions() and not store.q("SELECT id FROM positions")                # never a trade


def test_only_entry_eligible_company_catalysts_are_logged(env):
    clock, w = env
    _ingest("ACME", "2026-11-04T10:02:00-05:00", clock(), desk=False, url="https://x.com/someone/status/1")   # unverified
    _ingest("SPY", "2026-11-04T10:02:00-05:00", clock())                                                      # index
    ND.discover(clock())
    assert ND.rows() == []


def test_known_time_is_the_first_eligible_revision_never_earlier(env):
    clock, w = env
    _ingest("ACME", "2026-11-04T09:50:00-05:00", clock(), desk=False, url="https://www.reuters.com/markets/acme-results")
    cid = catalysts._all()[0]["id"]
    ND.discover(clock())
    assert ND.rows() == []                                              # attributed but content not verified yet
    clock.t = DAY.replace(hour=10, minute=20)
    c = catalysts._all()[0]
    c.update(content_verified=True, verification={"status": "verified", "by": "test", "at": clock().isoformat()})
    catalysts._save(c, clock(), "verified")
    ND.discover(clock())
    r = ND.rows()[0]
    assert r["id"] == cid and r["known_t"].startswith("2026-11-04T10:20") and r["t0"].startswith("2026-11-04T10:20")


def test_after_hours_news_is_anchored_to_the_next_open_and_discovery_is_idempotent(env):
    clock, w = env
    clock.t = DAY.replace(hour=16, minute=10)
    _ingest("ACME", "2026-11-04T16:05:00-05:00", clock())
    ND.discover(clock())
    ND.discover(clock())
    rs = ND.rows()
    assert len(rs) == 1 and rs[0]["t0"].startswith("2026-11-05T09:30") and "next open" in rs[0]["anchored"]


def test_late_first_look_records_no_half_spread(env):
    clock, w = env
    _ingest("ACME", "2026-11-04T10:02:00-05:00", clock())
    ND.discover(clock())
    clock.t = DAY.replace(hour=10, minute=12)
    ND.step(clock())
    r = ND.rows()[0]
    assert r["status"] == "OBSERVED" and r["half_spread"] is None and "no quote within 2 min" in r["reason"]


def test_moves_math_and_truncation():
    idx = pd.date_range(DAY.replace(hour=13, minute=30), DAY.replace(hour=15, minute=59), freq="1min")
    m1 = pd.DataFrame({"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": np.linspace(100, 101, len(idx)), "Volume": 1.0}, index=idx)
    mv = ND.moves(m1, pd.Timestamp(DAY.replace(hour=15, minute=0)), 100.0, "down", 0.05)
    assert mv["15"]["signed"] == pytest.approx(-mv["15"]["raw"]) and mv["15"]["net"] == pytest.approx(-mv["15"]["raw"] - 0.0005)
    assert mv["60"] is not None and mv["120"] is None                                   # 17:00 is past the close


def test_news_drift_api_over_real_http(env, monkeypatch):
    import json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    import server
    clock, w = env
    _ingest("ACME", "2026-11-04T10:02:00-05:00", clock())
    ND.discover(clock())
    monkeypatch.setattr(server, "DESK_TOKEN", "")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/api/v4/news_drift?day=2026-11-04") as r:
            d = json.loads(r.read())
        assert d["rows"][0]["ticker"] == "ACME" and d["summary"]["events"] == 0 and d["version"] == ND.VERSION
    finally:
        srv.shutdown()
