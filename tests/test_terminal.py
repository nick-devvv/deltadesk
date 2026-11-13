"""terminal.html (B6): served behind the desk token, read-only API calls on the same origin, no CDN, no secrets."""
import json
import re
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import store  # noqa: E402


def _get(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(url, timeout=10)


def test_terminal_page_is_served_and_needs_the_token(tmp_path, monkeypatch):
    import server
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(server, "DESK_TOKEN", "t0ken-for-tests")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        try:
            _get(base + "/terminal")
            assert False, "served without the token"
        except urllib.error.HTTPError as e:
            assert e.code == 403
        with _get(base + "/terminal?k=t0ken-for-tests") as r:
            html = r.read().decode()
        assert "DELTADESK // TERMINAL" in html and all(f'id="{p}"' in html for p in ("mon", "eval", "trades", "news"))
        with _get(base + "/api/v4/copilot?k=t0ken-for-tests") as r:
            assert "alerts" in json.loads(r.read())
        with _get(base + "/api/v4/copilot/score?k=t0ken-for-tests") as r:
            assert "by_pattern" in json.loads(r.read())
    finally:
        srv.shutdown()


def test_terminal_uses_only_same_origin_read_apis_and_escapes():
    html = (ROOT / "terminal.html").read_text()
    assert not re.search(r"https?://", html)                                  # no CDN, no outside calls, no links with keys
    paths = set(re.findall(r'get\("([^"?]+)', html))
    assert paths == {"api/v4/risk", "api/health", "api/v4/tracking", "api/v4/copilot/score", "api/v4/positions", "api/v4/copilot", "api/news"}
    posts = re.findall(r'fetch\("([^"]+)", \{method: "POST"', html)
    assert posts == ["api/v4/copilot/feedback"]                               # the only write: took / skipped
    assert "DESK_TOKEN" not in html and "?k=" not in html and "esc(" in html
    assert "calibrain-harness (MIT License)" in html
