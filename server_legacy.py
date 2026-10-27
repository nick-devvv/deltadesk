#!/usr/bin/env python3
"""server.py - runs Nick's Desk page.

  python3 server.py          -> open http://localhost:8765

Pages / endpoints:
  /             the desk page (index.html)
  /api/read     runs desk.py on SPY + QQQ, returns JSON (no AI credits used)
  /api/bars     ?t=SPY&tf=5&ext=1 -> candles + today's levels for the page's own chart
  /api/last     ?t=SPY -> latest trade price (Alpaca real-time IEX feed) to tick the last candle
  /api/paper    Alpaca PAPER account + journal stats (shadow.py)
  /api/plan     ?fill=0.85&time=10:15  -> stop / breakeven / T1 / exit times
  /api/chat     POST {"message": "..."} -> forwarded to your Grok bot (Chart)
  /api/reply    POST {"reply": "..."}   <- Chart posts its answer here (curl from its computer)
  /api/replies  ?since=N                -> page polls this to show Chart's answers

Set DESK_TOKEN to a long random secret; the link is then https://<host>/?k=<DESK_TOKEN>.
Set CHAT_WEBHOOK to the bot's webhook URL so the chat box talks to Chart:
  CHAT_WEBHOOK=http://... python3 server.py
Nick's REAL trades: only Nick, in Robinhood. Nothing here connects to Robinhood.
The only orders this server sends are bot.py's PAPER orders (Alpaca paper keys, fake money).
"""
import json
import math
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import desk  # noqa: E402
import shadow  # noqa: E402
import bot  # noqa: E402
import chartdata  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from datetime import datetime  # noqa: E402

PORT = int(os.environ.get("PORT", "8765"))
CHAT_WEBHOOK = os.environ.get("CHAT_WEBHOOK", "")
CHAT_WEBHOOK_KEY = os.environ.get("CHAT_WEBHOOK_KEY", "")  # sender key, if the webhook needs one
DESK_TOKEN = os.environ.get("DESK_TOKEN", "")  # secret in the link (?k=...) so only Nick can open the page
REPLIES = []  # bot answers posted back to /api/reply, shown in the page's chat box


def clean(v):
    """Make desk.py results JSON-safe."""
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items() if not str(k).startswith("_")}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, float):
        return None if math.isnan(v) else round(v, 2)
    if hasattr(v, "item"):  # numpy number
        return clean(v.item())
    return v


def do_read(tickers):
    res = []
    for t in tickers:
        try:
            r = desk.read(t)
        except Exception as e:  # keep the page alive if one ticker fails
            r = {"ticker": t, "error": str(e)}
        res.append(r)
    out = {"tickers": []}
    for r in res:
        d = clean(r)
        if "_lv" in r:
            d["levels"] = clean(r["_lv"])
        d["text"] = desk.fmt(r) if "error" not in r else r["error"]
        out["tickers"].append(d)
    good = [r for r in res if "error" not in r]
    out["agreement"] = desk.agreement(*good) if len(good) == 2 else ""
    return out


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def _ok(self, q):
        """Allow only requests carrying the secret (link ?k=... or the cookie it sets)."""
        if not DESK_TOKEN:
            return True
        if q.get("k", [""])[0] == DESK_TOKEN:
            return True
        return f"desk_k={DESK_TOKEN}" in (self.headers.get("Cookie") or "")

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._ok(q):
            return self._send(403, "Forbidden: open the full link Chart gave you (with ?k=...).", "text/plain")
        if u.path in ("/", "/index.html") and DESK_TOKEN and q.get("k", [""])[0] == DESK_TOKEN:
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Set-Cookie", f"desk_k={DESK_TOKEN}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax")
            self.end_headers()
            return self.wfile.write(data)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/api/read":
            tick = [t.strip().upper() for t in q.get("t", ["SPY,QQQ"])[0].split(",") if t.strip()]
            try:
                return self._send(200, json.dumps(do_read(tick)))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
        if u.path == "/api/bars":
            try:
                return self._send(200, json.dumps(chartdata.bars(q.get("t", ["SPY"])[0], q.get("tf", ["5"])[0],
                                                                 q.get("ext", ["1"])[0] == "1")))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
        if u.path == "/api/last":
            t = q.get("t", ["SPY"])[0].upper()
            j, err = shadow.api("GET", f"/v2/stocks/{t}/trades/latest?feed=iex", data=True)
            tr = (j or {}).get("trade") or {}
            return self._send(200, json.dumps({"price": tr.get("p"), "time": tr.get("t"), "error": err}))
        if u.path == "/api/paper":
            try:
                return self._send(200, json.dumps(shadow.status_json()))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
        if u.path == "/api/replies":
            since = int(q.get("since", ["0"])[0] or 0)
            return self._send(200, json.dumps({"replies": REPLIES[since:], "next": len(REPLIES)}))
        if u.path == "/api/plan":
            try:
                fill = float(q["fill"][0])
                return self._send(200, json.dumps({"plan": desk.plan(fill, q["time"][0])}))
            except Exception as e:
                return self._send(400, json.dumps({"error": f"need fill and time (HH:MM ET): {e}"}))
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        u = urlparse(self.path)
        path = u.path
        if not self._ok(parse_qs(u.query)):
            return self._send(403, json.dumps({"error": "forbidden"}))
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n) or b"{}"
        if path == "/api/reply":
            try:
                j = json.loads(body)
                REPLIES.append(str(j.get("reply") or j.get("text") or j.get("message") or ""))
            except ValueError:
                REPLIES.append(body.decode(errors="replace"))
            return self._send(200, json.dumps({"ok": True}))
        if path != "/api/chat":
            return self._send(404, json.dumps({"error": "not found"}))
        if not CHAT_WEBHOOK:
            return self._send(200, json.dumps({"reply": "Chat isn't connected to Chart yet (CHAT_WEBHOOK not set)."}))
        try:
            msg = json.loads(body).get("message", "")
        except ValueError:
            msg = body.decode(errors="replace")
        payload = json.dumps({"message": msg, "reply_to": f"http://127.0.0.1:{PORT}/api/reply" + (f"?k={DESK_TOKEN}" if DESK_TOKEN else "")}).encode()
        headers = {"Content-Type": "application/json"}
        if CHAT_WEBHOOK_KEY:
            headers["Authorization"] = f"Bearer {CHAT_WEBHOOK_KEY}"
        try:
            req = urllib.request.Request(CHAT_WEBHOOK, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode()
            try:
                j = json.loads(raw)
                reply = j.get("reply") if isinstance(j, dict) else None
            except ValueError:
                reply = None
            # Grok webhooks answer later via /api/reply, so the page waits for it.
            return self._send(200, json.dumps({"reply": reply} if reply else {"queued": True}))
        except Exception as e:
            return self._send(502, json.dumps({"reply": f"Couldn't reach Chart: {e}"}))

def bot_loop():
    """Every 10s during market hours: run the bot's exit rules on open paper trades (no AI credits)."""
    while True:
        try:
            t = datetime.now(shadow.ET)
            if t.weekday() < 5 and "09:30" <= t.strftime("%H:%M") <= "16:00":
                for m in bot.manage():
                    REPLIES.append(m)  # shows up in the page's chat box
                    print(m, flush=True)
        except Exception as e:
            print("bot loop error:", e, flush=True)
        time.sleep(10)


if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    print(f"Nick's Desk running: http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
