"""tools/pull_alpaca.get: network errors (the exam's TLS handshake timeouts) are retried with NET_BACKOFF, then raised;
HTTP 429/5xx keep their own backoff; other HTTP errors are raised at once. No network: _http and _sleep are replaced."""
import ssl
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pull_alpaca as PA  # noqa: E402


@pytest.fixture()
def env(monkeypatch):
    waits = []
    monkeypatch.setattr(PA, "_sleep", waits.append)
    monkeypatch.setattr(PA, "MAX_PER_MIN", 10 ** 9)
    monkeypatch.setenv("ALPACA_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET", "s")
    return waits


def _flaky(errors, page=None):
    calls = []

    def http(url, headers):
        calls.append(url)
        if len(calls) <= len(errors):
            raise errors[len(calls) - 1]
        return page or {"bars": {"SPY": [1]}, "next_page_token": None}
    return http, calls


def test_network_errors_are_retried_then_the_page_is_returned(env, monkeypatch):
    errs = [urllib.error.URLError(ssl.SSLError("The handshake operation timed out")), TimeoutError("read timed out"),
            ConnectionResetError("reset by peer")]
    http, calls = _flaky(errs)
    monkeypatch.setattr(PA, "_http", http)
    pages = list(PA.get("/v2/stocks/bars", {"symbols": "SPY"}))
    assert pages == [{"bars": {"SPY": [1]}, "next_page_token": None}] and len(calls) == 4
    assert env == list(PA.NET_BACKOFF[:3])


def test_network_errors_give_up_after_the_last_wait(env, monkeypatch):
    http, calls = _flaky([urllib.error.URLError("timed out")] * 50)
    monkeypatch.setattr(PA, "_http", http)
    with pytest.raises(urllib.error.URLError):
        list(PA.get("/v2/stocks/bars", {"symbols": "SPY"}))
    assert env == list(PA.NET_BACKOFF) and len(calls) == len(PA.NET_BACKOFF) + 1


def test_http_429_keeps_its_own_backoff_and_403_is_raised_at_once(env, monkeypatch):
    e429 = urllib.error.HTTPError("u", 429, "slow down", {}, None)
    http, calls = _flaky([e429, e429])
    monkeypatch.setattr(PA, "_http", http)
    assert len(list(PA.get("/v2/stocks/bars", {"symbols": "SPY"}))) == 1 and env == [1, 2]
    env.clear()
    http, calls = _flaky([urllib.error.HTTPError("u", 403, "forbidden", {}, None)])
    monkeypatch.setattr(PA, "_http", http)
    with pytest.raises(urllib.error.HTTPError):
        list(PA.get("/v2/stocks/bars", {"symbols": "SPY"}))
    assert env == [] and len(calls) == 1


def test_only_the_market_data_host_is_ever_called(env, monkeypatch):
    http, calls = _flaky([])
    monkeypatch.setattr(PA, "_http", http)
    list(PA.get("/v2/stocks/bars", {"symbols": "SPY"}))
    assert all(u.startswith(PA.DATA_HOST + "/") for u in calls)
