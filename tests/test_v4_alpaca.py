"""v4 stage 8: tools/pull_alpaca.py - read-only Alpaca market-data loader. Fake HTTP only, no network."""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import pull_alpaca as PA  # noqa: E402


def _bars_for(day, n=390, start="09:30", px=500.0):
    t0 = pd.Timestamp(f"{day} {start}", tz="America/New_York").tz_convert("UTC")      # DST-aware, like Alpaca's UTC stamps
    return [{"t": (t0 + pd.Timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ"), "o": px + i * 0.01, "h": px + i * 0.01 + 0.05,
             "l": px + i * 0.01 - 0.05, "c": px + i * 0.01, "v": 1000, "n": 10, "vw": px} for i in range(n)]


class FakeHTTP:
    """Serves stock bars for weekdays (with one short session and one missing day) in 2 pages, and option bars."""

    def __init__(self, missing=(), short=()):
        self.calls, self.missing, self.short = [], set(missing), set(short)

    def __call__(self, url, headers):
        assert url.startswith("https://data.alpaca.markets/") and headers["APCA-API-KEY-ID"] == "k"
        self.calls.append(url)
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if "/v2/stocks/" in u.path:
            a, b = date.fromisoformat(q["start"][:10]), date.fromisoformat(q["end"][:10])
            days = [a + timedelta(days=i) for i in range((b - a).days) if (a + timedelta(days=i)).weekday() < 5
                    and (a + timedelta(days=i)).isoformat() not in self.missing]
            bars = [x for d in days for x in _bars_for(d, 300 if d.isoformat() in self.short else 390)]
            half = len(bars) // 2
            if q.get("page_token") == "p2":
                return {"bars": bars[half:], "next_page_token": None}
            return {"bars": bars[:half], "next_page_token": "p2"}
        if u.path == "/v1beta1/options/bars":
            syms = q["symbols"].split(",")
            d = q["start"][:10]
            return {"bars": {s: _bars_for(d, 3, px=1.0) for s in syms[:2]}, "next_page_token": None}
        if u.path == "/v1beta1/options/trades":
            return {"trades": {q["symbols"].split(",")[0]: [{"t": f"{q['start'][:10]}T15:00:00Z", "p": 1.0, "s": 1, "x": "C"}]},
                    "next_page_token": None}
        raise AssertionError(u.path)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(PA, "ROOT", tmp_path / "alpaca")
    monkeypatch.setattr(PA, "_calls", [])
    monkeypatch.setenv("ALPACA_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET", "s")
    fake = FakeHTTP(missing={"2024-03-15"}, short={"2024-03-08"})
    monkeypatch.setattr(PA, "_http", fake)
    yield fake


def test_only_the_market_data_host_is_ever_called(env):
    for bad in ("https://paper-api.alpaca.markets/v2/orders", "https://api.alpaca.markets/v2/account",
                "https://data.alpaca.markets.evil.com/v2/stocks/SPY/bars"):
        with pytest.raises(RuntimeError, match="REFUSED"):
            PA._guard(bad)
    src = (ROOT / "tools" / "pull_alpaca.py").read_text()
    assert "paper-api" not in src.split('"""', 2)[2].replace("paper-api / api.alpaca.markets", "")
    assert "/v2/orders" not in src and "/v2/positions" not in src and "/v2/options/contracts" not in src


def test_stock_pull_paginates_caches_by_month_and_resumes(env):
    r = PA.pull_stock("SPY", date(2024, 2, 1), date(2024, 3, 31), today=date(2026, 10, 31))
    assert r["pulled"] == 2 and r["rows"] > 0
    assert any("page_token=p2" in c for c in env.calls)                              # pagination followed
    df = PA.load_stock("SPY", date(2024, 3, 1), date(2024, 3, 31))
    assert str(df["ts"].dt.tz) == "America/New_York" and df["ts"].dt.strftime("%H:%M").min() == "09:30"
    n = len(env.calls)
    r2 = PA.pull_stock("SPY", date(2024, 2, 1), date(2024, 3, 31), today=date(2026, 10, 31))
    assert r2 == {"pulled": 0, "skipped": 2, "rows": 0} and len(env.calls) == n          # resumable: nothing re-pulled


def test_partial_or_current_months_are_never_marked_done(env):
    PA.pull_stock("SPY", date(2024, 2, 1), date(2024, 2, 14), today=date(2026, 10, 31))
    assert not (PA.ROOT / "stocks" / "SPY" / "2024-02.csv.done").exists()
    PA.pull_stock("SPY", date(2026, 10, 1), date(2026, 10, 31), today=date(2026, 10, 31))
    assert not (PA.ROOT / "stocks" / "SPY" / "2026-10.csv.done").exists()


def test_gap_report_lists_missing_days_and_short_sessions(env):
    PA.pull_stock("SPY", date(2024, 3, 1), date(2024, 3, 31), today=date(2026, 10, 31))
    g = PA.gap_report("SPY", date(2024, 3, 1), date(2024, 3, 29), holidays={"2024-03-29"})
    assert "2024-03-15" in g["no_bars"] and g["short_sessions"] == [{"day": "2024-03-08", "rth_minutes": 300, "missing": 90}]
    assert g["sessions"] == 19 and "2024-02-26" in g["known_option_gaps"]


def test_option_pull_generates_0dte_symbols_from_the_day_range_and_resumes(env):
    PA.pull_stock("SPY", date(2024, 3, 1), date(2024, 3, 31), today=date(2026, 10, 31))
    day_bars = PA.load_stock("SPY", date(2024, 3, 4), date(2024, 3, 4))
    syms = PA.symbols_for_day("SPY", date(2024, 3, 4), day_bars, band=0.01)
    assert syms[0].startswith("SPY240304") and {s[-9] for s in syms} == {"C", "P"}
    strikes = sorted({int(s[-8:]) / 1000 for s in syms})
    assert strikes[0] <= 500 * 0.99 and strikes[-1] >= day_bars["h"].max() and all(b - a == 1 for a, b in zip(strikes, strikes[1:]))
    r = PA.pull_options("SPY", date(2024, 3, 4), date(2024, 3, 5), band=0.01, trades=True, today=date(2026, 10, 31))
    assert r["days"] == 2 and r["bars"] > 0 and r["trades"] == 2
    b = PA.read_gz(PA.ROOT / "options" / "SPY" / "2024-03-04" / "bars.csv.gz")
    assert set(b["symbol"]) <= set(syms) and len(b) == 6
    n = len(env.calls)
    r2 = PA.pull_options("SPY", date(2024, 3, 4), date(2024, 3, 5), band=0.01, trades=True, today=date(2026, 10, 31))
    assert r2["skipped"] == 2 and len(env.calls) == n
    r3 = PA.pull_options("SPY", date(2024, 3, 15), date(2024, 3, 15), today=date(2026, 10, 31))
    assert r3["no_stock_bars"] == ["2024-03-15"]


def test_missing_keys_refuse_to_run(env, monkeypatch):
    monkeypatch.delenv("ALPACA_KEY")
    with pytest.raises(RuntimeError, match="ALPACA_KEY"):
        PA.pull_stock("SPY", date(2024, 2, 1), date(2024, 2, 29), today=date(2026, 10, 31))
