"""Stuck requests can't stall a pull: pull_alpaca.get gives up on endless paging (page cap, repeated token) and says it is
still paging; a trickling response hits a total read deadline; round 9's daily stage falls back to one symbol at a time
and leaves out (and lists) only the symbols that still fail. No network."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "tools"))
sys.path.insert(0, str(HERE))
import pull_alpaca as PA  # noqa: E402
import sprint_pull9 as P9  # noqa: E402


@pytest.fixture()
def keys(monkeypatch):
    monkeypatch.setenv("ALPACA_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET", "s")
    monkeypatch.setattr(PA, "MAX_PER_MIN", 10 ** 9)
    monkeypatch.setattr(PA, "_sleep", lambda s: None)


def test_endless_paging_is_abandoned_with_a_heartbeat(keys, monkeypatch, capsys):
    n = {"k": 0}

    def http(url, headers):
        n["k"] += 1
        return {"bars": {}, "next_page_token": f"t{n['k']}"}          # a new token forever
    monkeypatch.setattr(PA, "_http", http)
    with pytest.raises(PA.PagingError):
        list(PA.get("/v2/stocks/bars", {"symbols": "ZZZ"}))
    assert n["k"] == PA.MAX_PAGES and "still paging /v2/stocks/bars (100 pages so far)" in capsys.readouterr().err


def test_a_repeated_page_token_is_abandoned_at_once(keys, monkeypatch):
    calls = []
    monkeypatch.setattr(PA, "_http", lambda url, headers: calls.append(url) or {"bars": {}, "next_page_token": "same"})
    with pytest.raises(PA.PagingError, match="same page token"):
        list(PA.get("/v2/stocks/bars", {"symbols": "ZZZ"}))
    assert len(calls) == 2


def test_normal_paging_still_works(keys, monkeypatch):
    pages = [{"bars": {"A": [1]}, "next_page_token": "p2"}, {"bars": {"A": [2]}, "next_page_token": "p3"},
             {"bars": {"A": [3]}, "next_page_token": None}]
    it = iter(pages)
    monkeypatch.setattr(PA, "_http", lambda url, headers: next(it))
    assert [p["bars"]["A"][0] for p in PA.get("/v2/stocks/bars", {"symbols": "A"})] == [1, 2, 3]


def test_a_trickling_response_hits_the_total_read_deadline(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(PA.time, "monotonic", lambda: clock["t"])

    class Trickle:
        def read(self, n):
            clock["t"] += 10.0                                            # 10 s per chunk, forever
            return b"x"
    with pytest.raises(TimeoutError):
        PA._read_all(Trickle())
    assert clock["t"] <= PA.READ_DEADLINE + 20

    class Fast:
        def __init__(self):
            self.parts = [b'{"a":', b" 1}", b""]

        def read(self, n):
            return self.parts.pop(0)
    assert PA._read_all(Fast()) == b'{"a": 1}'


def test_daily_stage_falls_back_to_single_symbols_and_lists_the_bad_one(tmp_path, monkeypatch):
    asked = []

    def fake_multi(path, symbols, params, kind, net_backoff=None):
        asked.append((tuple(symbols), params["adjustment"], net_backoff))
        if "BAD" in symbols and params["adjustment"] == "split":
            raise PA.PagingError("/v2/stocks/bars: more than 500 pages")
        ts = pd.Timestamp("2025-03-03 00:00", tz="America/New_York")
        return pd.DataFrame([{"ts": ts, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0, "symbol": s} for s in symbols])
    monkeypatch.setattr(P9, "_multi_bars", fake_multi)
    lines = []
    root = tmp_path / "alpaca"
    out = P9.pull_daily(["AAA", "BAD", "CCC"], root, lines.append, batch=100)
    split = root / "daily9" / "split"
    assert out["failed"] == ["split:BAD"] and (split / "BAD.failed").exists() and not (split / "BAD.done").exists()
    assert (split / "AAA.done").exists() and (split / "CCC.done").exists()
    assert json.loads((split / "BAD.failed").read_text())["reason"].startswith("PagingError")
    assert any("fetching them one by one" in l for l in lines) and any("left out after single-symbol tries: BAD" in l for l in lines)
    singles = [a for a in asked if len(a[0]) == 1 and a[1] == "split"]
    assert singles and all(a[2] == P9.SINGLE_BACKOFF for a in singles)
    asked.clear()
    lines.clear()
    out2 = P9.pull_daily(["AAA", "BAD", "CCC"], root, lines.append, batch=100)
    assert asked == [] and out2["failed"] == ["split:BAD"] and any("failed on an earlier try" in l for l in lines)


def test_a_missing_key_is_not_swallowed_by_the_fallback(tmp_path, monkeypatch):
    def fake_multi(path, symbols, params, kind, net_backoff=None):
        raise RuntimeError("ALPACA_KEY / ALPACA_SECRET are not set")
    monkeypatch.setattr(P9, "_multi_bars", fake_multi)
    with pytest.raises(RuntimeError):
        P9.pull_daily(["AAA"], tmp_path / "alpaca", print, batch=100)
    assert not list((tmp_path / "alpaca").rglob("*.failed"))


def test_a_network_outage_stops_the_stage_instead_of_marking_symbols(tmp_path, monkeypatch):
    def fake_multi(path, symbols, params, kind, net_backoff=None):
        raise ConnectionError("connection refused")
    monkeypatch.setattr(P9, "_multi_bars", fake_multi)
    with pytest.raises(ConnectionError, match="network errors"):
        P9.pull_daily(["AAA", "BBB"], tmp_path / "alpaca", print, batch=100)
    assert not list((tmp_path / "alpaca").rglob("*.failed"))


def test_a_symbol_that_hangs_alone_is_left_out_when_the_others_come_back(tmp_path, monkeypatch):
    def fake_multi(path, symbols, params, kind, net_backoff=None):
        if "BAD" in symbols:
            raise TimeoutError("response still arriving after 120 s")
        ts = pd.Timestamp("2025-03-03 00:00", tz="America/New_York")
        return pd.DataFrame([{"ts": ts, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0, "symbol": s} for s in symbols])
    monkeypatch.setattr(P9, "_multi_bars", fake_multi)
    out = P9.pull_daily(["AAA", "BAD"], tmp_path / "alpaca", print, batch=100)
    assert sorted(out["failed"]) == ["raw:BAD", "split:BAD"]


def test_sec_probe_needs_an_answer_and_is_bounded_by_its_deadline():
    import time as _t
    assert P9.sec_reachable(lambda u: (200, "ok")) is True
    assert P9.sec_reachable(lambda u: (404, "")) is True
    assert P9.sec_reachable(lambda u: (403, "")) is False
    assert P9.sec_reachable(lambda u: (599, "")) is False
    t0 = _t.time()
    assert P9.sec_reachable(lambda u: _t.sleep(5) or (200, ""), deadline=0.5) is False
    assert _t.time() - t0 < 2


def test_unreachable_sec_skips_the_8k_stages_and_finishes(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(P9, "sec_reachable", lambda *a, **k: False)
    monkeypatch.setattr(P9.E, "load_user_agent", lambda *a, **k: "env")
    called = []
    for fn in ("pull_edgar_index", "pull_edgar_headers", "pull_g1", "pull_g2"):
        monkeypatch.setattr(P9, fn, lambda *a, fn=fn, **k: called.append(fn))
    rc = P9.main(["--only", "edgar_index,edgar_headers,g1,g2", "--root", str(tmp_path / "alpaca")])
    out = capsys.readouterr().out
    assert rc == 0 and called == [] and out.count("WARNING: [") == 4 and "NOT reachable" in out
    assert "sprint_pull9 done" in out


def test_edgar_index_skips_holidays_missing_from_the_quarter_listing(tmp_path, monkeypatch):
    from datetime import date
    asked = []
    listing = {"directory": {"item": [{"name": "form.20160104.idx"}, {"name": "form.20160105.idx"}]}}

    def http(url):
        asked.append(url)
        if url.endswith("company_tickers.json"):
            return 200, json.dumps({"0": {"cik_str": 1, "ticker": "AAA", "title": "A"}})
        if url.endswith("QTR1/index.json"):
            return 200, json.dumps(listing)
        if url.endswith("form.20160101.idx"):
            return 403, ""                                      # SEC's answer for a holiday
        return 200, ""
    monkeypatch.setattr(P9, "index_days", lambda: [date(2016, 1, 1), date(2016, 1, 4), date(2016, 1, 5)])

    class NoT:
        def wait(self):
            pass
    out = P9.pull_edgar_index(tmp_path / "alpaca", print, http=http, throttle=NoT())
    assert out["not_published"] == 1 and out["fetched"] == 2
    assert not any(u.endswith("form.20160101.idx") for u in asked)
    assert sum(u.endswith("index.json") for u in asked) == 1
