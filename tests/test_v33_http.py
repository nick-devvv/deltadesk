"""v3.3: the page turns tunnel/proxy failures (Cloudflare 530 HTML), HTML 200, malformed JSON and auth/rate errors into
short messages instead of parsing or showing raw HTML. Runs the page's own readJson/explainHttp in node (skipped if
node is missing). Plus the server's structured error with a diagnostic id."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _fn_src():
    h = (ROOT / "index.html").read_text()
    a = h.index("function explainHttp(")
    b = h.index("async function api(path, body)")
    return h[a:b]


CF530 = ("<!doctype html> <!--[if lt IE 7]> <html class=\"no-js ie6 oldie\" lang=\"en-US\"> <![endif]--><head><title>"
         "Origin DNS error | example.trycloudflare.com | Cloudflare</title></head><body><h1>Error 1016</h1> Ray ID: 8a1b</body></html>")


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_page_reads_only_json_and_explains_failures():
    cases = [
        (200, "application/json", '{"ticker":"SPY","candles":[]}', "ok"),
        (530, "text/html; charset=UTF-8", CF530, "tunnel"),
        (200, "text/html", "<!doctype html><html><body>login</body></html>", "web page"),
        (200, "application/json", '{"ticker": "SPY", "candles": [', "malformed"),
        (401, "application/json", '{"error":"bad token"}', "refused"),
        (403, "text/plain", "forbidden", "refused"),
        (429, "text/plain", "slow down", "Too many"),
        (500, "application/json", '{"error":"the desk hit an internal error on /api/chart (KeyError)","diag_id":"ab12cd34"}', "ref ab12cd34"),
    ]
    js = _fn_src() + """
const cases = %s;
(async () => { const out = [];
  for (const [status, ctype, body, want] of cases) {
    const r = {ok: status >= 200 && status < 300, status, headers: {get: () => ctype}, text: async () => body};
    try { const d = await readJson(r); out.push(want === "ok" && d.ticker === "SPY" ? "pass" : "fail: parsed " + JSON.stringify(d)); }
    catch (e) { out.push(e.message.includes(want) && !/<html|doctype/i.test(e.message) ? "pass" : "fail: " + e.message); }
  }
  console.log(JSON.stringify(out)); })();""" % json.dumps(cases)
    res = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out == ["pass"] * len(cases), list(zip([c[0] for c in cases], out))


def test_server_errors_are_structured_with_a_diagnostic_id(capsys):
    import server

    class Fake(server.H):
        def __init__(self):
            self.sent = None

        def _json(self, obj, code=200):
            self.sent = (code, obj)
            return self.sent
    h = Fake()
    code, body = h._fail(KeyError("x"), "/api/chart")
    assert code == 500 and re.fullmatch(r"[0-9a-f]{8}", body["diag_id"]) and "KeyError" in body["error"]
    assert body["diag_id"] in capsys.readouterr().out          # the same id is in the server log for lookup
