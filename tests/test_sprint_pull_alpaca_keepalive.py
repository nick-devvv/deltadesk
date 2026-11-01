"""tools/pull_alpaca's HTTP layer: one kept-alive connection per thread (no TLS handshake per request), a transparent
reconnect when the server closes a kept-alive connection, HTTP >= 400 as urllib's HTTPError, the proxy fallback, the host
guard, and the shared 180-a-minute throttle under threads. A local plain-HTTP server stands in for Alpaca."""
import json
import sys
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import http.client
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pull_alpaca as PA  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    conns, reqs, close_after = set(), [], None

    def log_message(self, *a):
        pass

    def do_GET(self):
        Handler.conns.add(self.client_address)
        Handler.reqs.append(self.path)
        code = 429 if "fail429" in self.path else 200
        body = json.dumps({"path": self.path, "next_page_token": None}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if Handler.close_after and len(Handler.reqs) % Handler.close_after == 0:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def server(monkeypatch):
    Handler.conns, Handler.reqs, Handler.close_after = set(), [], None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    port = srv.server_address[1]
    made = []

    def connect():
        made.append(1)
        return http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    monkeypatch.setattr(PA, "_connect", connect)
    monkeypatch.setattr(PA, "_proxied", lambda: False)
    PA._drop()
    yield made
    PA._drop()
    srv.shutdown()


URL = PA.DATA_HOST + "/v2/stocks/bars?symbols=SPY&page=%d"


def test_one_connection_serves_many_requests(server):
    for k in range(5):
        assert PA._default_http(URL % k, {"Accept": "application/json"})["path"] == f"/v2/stocks/bars?symbols=SPY&page={k}"
    assert len(server) == 1 and len(Handler.conns) == 1 and len(Handler.reqs) == 5


def test_a_closed_keepalive_connection_is_reopened_transparently(server):
    Handler.close_after = 2
    for k in range(6):
        PA._default_http(URL % k, {})
    assert len(Handler.reqs) == 6 and len(server) == 3


def test_http_errors_come_back_as_urllib_httperror_and_the_connection_stays_usable(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        PA._default_http(PA.DATA_HOST + "/v2/stocks/bars?fail429=1", {})
    assert e.value.code == 429
    PA._default_http(URL % 1, {})
    assert len(server) == 1


def test_each_thread_has_its_own_connection(server):
    out = []
    ts = [threading.Thread(target=lambda k=k: out.append(PA._default_http(URL % k, {}))) for k in range(3)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(out) == 3 and len(server) == 3


def test_only_the_market_data_host_and_the_proxy_fallback(monkeypatch):
    with pytest.raises(RuntimeError):
        PA._default_http("https://paper-api.alpaca.markets/v2/orders", {})
    seen = []
    monkeypatch.setattr(PA, "_proxied", lambda: True)
    monkeypatch.setattr(PA, "_urllib_get", lambda url, headers: seen.append(url) or {"ok": 1})
    assert PA._default_http(URL % 1, {}) == {"ok": 1} and seen == [URL % 1]


def test_the_throttle_is_shared_by_threads(monkeypatch):
    clock = {"t": 1000.0}
    lock = threading.Lock()

    class FakeTime:
        @staticmethod
        def time():
            return clock["t"]

        @staticmethod
        def sleep(s):
            with lock:
                clock["t"] += s
    monkeypatch.setattr(PA, "time", FakeTime)
    monkeypatch.setattr(PA, "_calls", [])
    monkeypatch.setattr(PA, "MAX_PER_MIN", 10)
    stamps = []

    def work():
        for _ in range(10):
            PA._throttle()
            stamps.append(clock["t"])
    ts = [threading.Thread(target=work) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    stamps.sort()
    assert len(stamps) == 40
    for i in range(len(stamps) - 10):
        assert stamps[i + 10] - stamps[i] >= 60 - 1e-6       # never more than 10 in any 60 s
