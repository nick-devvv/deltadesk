#!/usr/bin/env python3
"""server.py - Nick's Desk backend + page. Runs the deterministic engine in the background (no AI).

  python3 server.py            -> http://localhost:8765  (public link via Tailscale Funnel + ?k=DESK_TOKEN)

Env: DESK_TOKEN (link secret), CHAT_WEBHOOK + CHAT_WEBHOOK_KEY (Chart's Grok webhook),
     ALPACA_KEY + ALPACA_SECRET (PAPER keys only), PORT (default 8765), QUIVER_KEY (optional, Quiver data),
     SCHWAB_APP_KEY + SCHWAB_APP_SECRET (+ SCHWAB_CALLBACK, default https://127.0.0.1) optional live market data.

Main endpoints:
  GET  /api/state?since=N    everything the page shows + new events (poll every 2 s)
  POST /api/command          {"text": "...", "ticker": "SPY"}  IN/OUT/confirm/check once/stop watch in code;
                             other questions go to Chart with a compact context (counted as AI calls)
  POST /api/reply            Chart posts its answer here (reply_to in the webhook payload)
  GET/POST /api/journal      daily journal (notes never overwritten by summaries)
  GET  /api/review           computed day review for the 4:20 PM job; POST /api/lessons stores PROPOSED lessons
  POST /api/events           {"date","events":[{"time":"08:30","name":"CPI"}]} from the 9 AM routine
  GET/POST /api/watchlist     other tickers: quotes, earnings date; {"add":"NVDA"} / {"remove":"NVDA"}
  GET  /api/alt?t=NVDA        optional Quiver data (QUIVER_KEY): congress trades, short volume, WSB, lobbying, contracts
  GET  /api/schwab/status|login, POST /api/schwab/connect   optional live Schwab market data (market data only)
  GET  /legacy               the old desk page (custom indicator chart)
  Legacy: /api/read /api/bars /api/last /api/plan /api/chat
Real money: only Nick, in Robinhood. The only orders this server sends are Alpaca PAPER orders.
"""
import json
import math
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import broker  # noqa: E402
import chartdata  # noqa: E402
import commands  # noqa: E402
import core  # noqa: E402
import engine  # noqa: E402
import store  # noqa: E402
import watchlist  # noqa: E402
import schwab  # noqa: E402
import altdata  # noqa: E402

PORT = int(os.environ.get("PORT", "8765"))
CHAT_WEBHOOK = os.environ.get("CHAT_WEBHOOK", "")
CHAT_WEBHOOK_KEY = os.environ.get("CHAT_WEBHOOK_KEY", "")
DESK_TOKEN = os.environ.get("DESK_TOKEN", "")
STARTED = store.ts()


def clean(v):
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items() if not str(k).startswith("_") and k != "m1"}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, float):
        return None if math.isnan(v) else round(v, 4)
    if hasattr(v, "item"):
        return clean(v.item())
    return v


def ai_calls_today():
    return store.kv_get(f"ai_calls:{core.now_et().strftime('%Y-%m-%d')}", 0)


def send_to_chart(message, context):
    """One Grok call. Chart answers later via /api/reply (Grok webhooks are async)."""
    if not CHAT_WEBHOOK:
        return "Chart isn't connected (CHAT_WEBHOOK not set). The plan above is still valid."
    k = f"ai_calls:{core.now_et().strftime('%Y-%m-%d')}"
    store.kv_set(k, store.kv_get(k, 0) + 1)
    payload = json.dumps({"message": message, "context": context,
                          "reply_to": f"http://127.0.0.1:{PORT}/api/reply" + (f"?k={DESK_TOKEN}" if DESK_TOKEN else "")},
                         default=str).encode()
    headers = {"Content-Type": "application/json"}
    if CHAT_WEBHOOK_KEY:
        headers["Authorization"] = f"Bearer {CHAT_WEBHOOK_KEY}"
    try:
        req = urllib.request.Request(CHAT_WEBHOOK, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        return None
    except Exception as e:
        return f"Couldn't reach Chart: {e}"


def unreviewed_today():
    day = core.now_et().strftime("%Y-%m-%d")
    n = 0
    for p in store.positions(ledger="real", day=day):
        if p["status"] != "CLOSED":
            continue
        try:
            notes = json.loads(p.get("notes") or "{}") if isinstance(p.get("notes"), str) else (p.get("notes") or {})
        except ValueError:
            notes = {}
        if not any(notes.get(k) for k in store.REVIEW_FIELDS):
            n += 1
    return n


def state(since):
    sess = core.session_info()
    pos = store.positions(status="OPEN") + store.positions(status="PENDING")
    watches = [dict(w, plan=json.loads(w["plan"])) for w in store.q("SELECT * FROM watches WHERE status='ACTIVE'")]
    eng = engine._state
    paper_status = ("FAULT" if eng["errors"] >= 3 else "PAUSED" if not engine.paper_enabled()
                    else "RUNNING" if sess["entries_allowed"] else "IDLE (" + sess["state"] + ")")
    return clean({
        "now": store.ts(), "session": sess, "policy_version": core.policy()["version"],
        "engine": {"last_tick": eng["last_tick"], "errors": eng["errors"], "last_error": eng["last_error"], "started": STARTED},
        "paper": {"enabled": engine.paper_enabled(), "status": paper_status,
                  "broker": broker.paper_account_ok()[1] if broker.configured() else "no Alpaca keys"},
        "budget": {"real": engine.ledger_budget("real"), "paper": engine.ledger_budget("paper")},
        "positions": pos, "watches": watches, "last_plan": store.kv_get("last_plan"),
        "events": store.events_since(since), "seq": store.last_seq(),
        "ai_calls_today": ai_calls_today(), "chat_connected": bool(CHAT_WEBHOOK),
        "data": {"candles": engine.data_source(), "options": "Schwab live" if schwab.ready() else "Alpaca indicative (delayed)",
                 "schwab": schwab.status()},
        "unreviewed_today": unreviewed_today(),
    })


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        return self._send(code, json.dumps(obj, default=str))

    def log_message(self, *a):
        pass

    def _ok(self, q):
        if not DESK_TOKEN:
            return True
        if q.get("k", [""])[0] == DESK_TOKEN:
            return True
        return f"desk_k={DESK_TOKEN}" in (self.headers.get("Cookie") or "")

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        if n > 200_000:
            return {}
        raw = self.rfile.read(n) or b"{}"
        try:
            return json.loads(raw)
        except ValueError:
            return {"text": raw.decode(errors="replace")}

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._ok(q):
            return self._send(403, "Forbidden: open the full link Chart gave you (with ?k=...).", "text/plain")
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                data = f.read()
            extra = {}
            if DESK_TOKEN and q.get("k", [""])[0] == DESK_TOKEN:
                extra["Set-Cookie"] = f"desk_k={DESK_TOKEN}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax"
            return self._send(200, data, "text/html; charset=utf-8", extra)
        if u.path in ("/legacy", "/legacy.html"):
            with open(os.path.join(HERE, "index_legacy.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        try:
            if u.path == "/api/state":
                return self._json(state(int(q.get("since", ["0"])[0] or 0)))
            if u.path == "/api/journal":
                d = q.get("date", [core.now_et().strftime("%Y-%m-%d")])[0]
                return self._json({"journal": store.journal_get(d), "live": clean(engine.day_summary(d))})
            if u.path == "/api/review":
                d = q.get("date", [core.now_et().strftime("%Y-%m-%d")])[0]
                return self._json(clean(engine.day_summary(d)))
            if u.path == "/api/lessons":
                return self._json(store.q("SELECT * FROM lessons ORDER BY created DESC"))
            if u.path == "/api/policy":
                return self._json(core.policy())
            if u.path == "/api/schwab/status":
                return self._json(dict(schwab.status(), callback=schwab.callback(), candles=engine.data_source()))
            if u.path == "/api/schwab/login":
                if not schwab.configured():
                    return self._send(400, "Add SCHWAB_APP_KEY and SCHWAB_APP_SECRET to Chart's Secrets first.", "text/plain")
                return self._send(302, b"", "text/plain", {"Location": schwab.login_url()})
            if u.path == "/api/kronos":
                import kronos_shadow
                store.x(kronos_shadow.SCHEMA)
                st = store.kv_get("kronos_status") or {"state": "off", "hint": "set KRONOS=1 in the server env (setup steps in kronos_shadow.py)"}
                m = kronos_shadow.metrics()
                last = store.q("SELECT ticker, bar_ts, horizon, base, pred, pred_mom, actual, runtime_ms FROM forecasts ORDER BY made_at DESC LIMIT 6")
                return self._json({"status": st, "metrics": m, "verdict": kronos_shadow.verdict(m), "last": last})
            if u.path == "/api/knowledge":
                return self._json(json.loads((core.HERE / "knowledge" / "cards.json").read_text()))
            if u.path == "/api/alt":
                t = q.get("t", ["NVDA"])[0].upper()
                if not watchlist.valid(t):
                    return self._json({"error": "bad ticker"}, 400)
                return self._json(altdata.ticker(t))
            if u.path == "/api/watchlist":
                return self._json({"tickers": watchlist.tickers(), "quotes": clean(watchlist.quotes())})
            if u.path == "/api/calendar":
                return self._json(store.calendar(q.get("ledger", ["real"])[0], q.get("month", [core.now_et().strftime("%Y-%m")])[0][:7]))
            if u.path == "/api/breakdown":
                return self._json(store.breakdown(q.get("ledger", ["real"])[0], q.get("since", ["2000-01-01"])[0][:10]))
            if u.path == "/api/export.csv":
                led = q.get("ledger", ["real"])[0]
                return self._send(200, store.export_csv(led), "text/csv; charset=utf-8",
                                  {"Content-Disposition": f'attachment; filename="desk-{led}-trades.csv"'})
            if u.path == "/api/history":
                led = q.get("ledger", ["paper"])[0]
                rows = store.q("SELECT id,date,ticker,contract,qty_init,fill,realized,status,setup,grade,mfe,mae,opened,closed,verified,notes "
                               "FROM positions WHERE ledger=? ORDER BY opened DESC LIMIT 200", (led,))
                return self._json(rows)
            if u.path == "/api/read":
                tick = [t.strip().upper() for t in q.get("t", ["SPY,QQQ"])[0].split(",") if t.strip()]
                out = {"tickers": []}
                for t in tick:
                    s = engine.snapshot(t)
                    d = clean(s.get("read", {}))
                    d.update(ticker=t, price=s.get("price"), stale=s.get("stale"), price_src=s.get("price_src"),
                             bar_age_s=s.get("bar_age_s"), levels=clean(s.get("levels", {})), error=s.get("error"))
                    out["tickers"].append(d)
                return self._json(out)
            if u.path == "/api/bars":
                return self._json(chartdata.bars(q.get("t", ["SPY"])[0], q.get("tf", ["5"])[0], q.get("ext", ["1"])[0] == "1"))
            if u.path == "/api/last":
                last, err = broker.stock_last(q.get("t", ["SPY"])[0].upper())
                return self._json({"price": (last or {}).get("price"), "time": (last or {}).get("ts"), "error": err})
            if u.path == "/api/plan":
                return self._json({"plan": core.exit_plan(float(q["fill"][0]), q["time"][0])})
        except Exception as e:
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        if not self._ok(parse_qs(u.query)):
            return self._json({"error": "forbidden"}, 403)
        b = self._body()
        try:
            if u.path == "/api/command":
                text = str(b.get("text", ""))[:2000]
                tick = str(b.get("ticker", "SPY")).upper()
                if not watchlist.valid(tick):
                    tick = "SPY"
                store.event("you", text, "real")
                r = commands.handle(text, tick)
                if r.get("reply"):
                    store.event("desk", r["reply"], "real", (r.get("plan") or {}).get("id", ""))
                note, asked = None, False
                if r.get("coach") and b.get("explain", True):
                    ctx = commands.coach_context(tick, text)
                    if r.get("plan"):
                        ctx["active_plan"] = r["plan"]
                    msg = text if not r["handled"] else f"Explain this plan in 2-4 lines using its numbers only: {text}"
                    note = send_to_chart(msg, ctx)
                    asked = note is None
                    if note:
                        store.event("system", note)
                return self._json({"reply": r.get("reply"), "plan": r.get("plan"), "coach_pending": asked, "review": r.get("review"),
                                   "seq": store.last_seq()})
            if u.path == "/api/reply":
                text = str(b.get("reply") or b.get("text") or b.get("message") or "")[:6000]
                store.event("chart", text, "")
                return self._json({"ok": True})
            if u.path == "/api/schwab/connect":
                ok, msg = schwab.connect(str(b.get("url", ""))[:2000])
                if ok:
                    store.event("system", "Schwab live data connected (renew every 7 days on the Rules page)")
                return self._json({"ok": ok, "message": msg, "status": schwab.status()}, 200 if ok else 400)
            if u.path == "/api/trade_note":
                r = store.trade_note(str(b.get("id", "")), b.get("fields") or {})
                return self._json({"ok": r is not None, "notes": r}, 200 if r is not None else 404)
            if u.path == "/api/journal" and b.get("intraday"):
                d = b.get("date") or core.now_et().strftime("%Y-%m-%d")
                cur = store.journal_get(d)["notes"]
                lst = cur.get("intraday_log") if isinstance(cur.get("intraday_log"), list) else []
                lst.append({"t": core.hm(core.now_et()), "note": str(b["intraday"])[:500]})
                return self._json(store.journal_set(d, notes={"intraday_log": lst[-200:]}))
            if u.path == "/api/journal":
                d = b.get("date") or core.now_et().strftime("%Y-%m-%d")
                notes = {k: str(v)[:5000] for k, v in (b.get("notes") or {}).items() if k != "intraday_log"}
                return self._json(store.journal_set(d, notes=notes))
            if u.path == "/api/watchlist":
                if b.get("add"):
                    watchlist.add(str(b["add"]))
                if b.get("remove"):
                    watchlist.remove(str(b["remove"]))
                return self._json({"tickers": watchlist.tickers()})
            if u.path == "/api/events":  # 9 AM routine: today's scheduled releases (CPI, Fed...) -> entry block
                import re as _re
                d = str(b.get("date") or core.now_et().strftime("%Y-%m-%d"))[:10]
                evs = [{"time": str(e.get("time", ""))[:5], "name": str(e.get("name", ""))[:80]}
                       for e in (b.get("events") or [])[:20] if _re.match(r"^\d{2}:\d{2}$", str(e.get("time", ""))[:5])]
                (core.HERE / "config" / "events.json").write_text(json.dumps({"date": d, "events": evs}, indent=1))
                store.event("system", f"Events for {d}: " + (", ".join(f"{e['name']} {e['time']}" for e in evs) or "none"))
                return self._json({"ok": True, "date": d, "events": evs})
            if u.path == "/api/lessons":
                lid = store.new_id("L")
                store.x("INSERT INTO lessons(id,created,status,text,evidence,setup,sample) VALUES(?,?,?,?,?,?,?)",
                        (lid, store.ts(), "PROPOSED", str(b.get("text", ""))[:1000], json.dumps(b.get("evidence", [])),
                         str(b.get("setup", "")), int(b.get("sample", 0))))
                return self._json({"id": lid, "status": "PROPOSED"})
            if u.path == "/api/chat":  # legacy chat box
                r = commands.handle(str(b.get("message", "")), "SPY")
                if r.get("handled") and not r.get("coach"):
                    return self._json({"reply": r["reply"]})
                note = send_to_chart(str(b.get("message", "")), commands.coach_context("SPY"))
                return self._json({"reply": note} if note else {"queued": True})
        except Exception as e:
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
        self._json({"error": "not found"}, 404)


def engine_loop():
    while True:
        engine.tick()
        time.sleep(5)


def start_kronos():
    """Kronos runs in its own process, without broker keys or the desk token, and can never block the desk."""
    if os.environ.get("KRONOS") != "1":
        return None
    import subprocess
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ALPACA", "DESK_TOKEN", "CHAT_WEBHOOK", "QUIVER", "SCHWAB"))}

    def run():
        while True:
            try:
                subprocess.run([sys.executable, os.path.join(HERE, "kronos_shadow.py")], env=env, cwd=HERE)
            except Exception:
                pass
            time.sleep(300)  # restart after a crash, slowly
    threading.Thread(target=run, daemon=True).start()
    return True


if __name__ == "__main__":
    store.conn()
    core.policy()
    threading.Thread(target=engine_loop, daemon=True).start()
    start_kronos()
    print(f"Nick's Desk running: http://localhost:{PORT}  policy {core.policy()['version']}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
