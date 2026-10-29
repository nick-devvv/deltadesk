#!/usr/bin/env python3
"""server.py - DeltaDesk backend + page. Runs the deterministic engine in the background (no AI).

  python3 server.py            -> http://localhost:8765  (public link via Tailscale Funnel + ?k=DESK_TOKEN)

Env: DESK_TOKEN (link secret), CHAT_WEBHOOK + CHAT_WEBHOOK_KEY (Chart's Grok webhook),
     ALPACA_KEY + ALPACA_SECRET (PAPER keys only), PORT (default 8765), QUIVER_KEY (optional, Quiver data),
     SCHWAB_APP_KEY + SCHWAB_APP_SECRET (+ SCHWAB_CALLBACK, default https://127.0.0.1) optional live market data,
     NTFY_TOPIC (optional: phone alerts through the free ntfy app).

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
  GET/POST /api/news         Chart's news scan posts headlines {"items":[{headline,source,time,tickers,impact,direction,why}]}
  GET/POST /api/alerts       alert toggles (setups, moves, news); phone push via NTFY_TOPIC (ntfy app)
  GET  /api/chart?t=SPY&tf=1|2|5  desk chart from the SAME Schwab pipeline as the engine: candles, volume, VWAP,
                             EMA9/21, MACD, levels (with sources), entry/exit markers, feed + freshness
  GET  /api/data/status      provider, stream/REST/fallback mode, entitlements check, latency distributions, gaps
  GET  /api/candidates       every candidate with evidence, decision, rejection reasons, limit blocks (per portfolio)
  GET  /api/portfolios       real / main paper / research / old-policy results kept apart
  GET  /api/evaluation       the forward paper test scored against the criteria fixed in policy.json beforehand
  GET  /legacy               the old desk page (custom indicator chart)
  Legacy: /api/read /api/bars /api/last /api/plan /api/chat
Real money: only Nick, in Robinhood. This server sends NO orders anywhere: paper trading is simulated internally
on Schwab quotes. Schwab access is market data only (trading/account endpoints are refused in code).
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
import alerts  # noqa: E402
import altdata  # noqa: E402
import exits  # noqa: E402
import indicators  # noqa: E402
import marketdata  # noqa: E402
import paper  # noqa: E402

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


def unreviewed_list():
    day = core.now_et().strftime("%Y-%m-%d")
    out = []
    for p in store.positions(ledger="real", day=day):
        if p["status"] != "CLOSED":
            continue
        try:
            notes = json.loads(p.get("notes") or "{}") if isinstance(p.get("notes"), str) else (p.get("notes") or {})
        except ValueError:
            notes = {}
        if not any(notes.get(k) for k in store.REVIEW_FIELDS):
            out.append({"id": p["id"], "trade": f"{p['ticker']} {p['contract']}", "pnl": p.get("realized")})
    return out


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


def position_view(p):
    """Exact contract, actual fill, live bid/ask/spread, the P&L mark used, stops history, stall timer."""
    q, err = marketdata.option_quote(p["symbol"])
    pl = p.get("plan") or {}
    v = {"quote": None, "quote_error": err}
    if q:
        slip, fee = paper.costs((q.get("ask") or 0) - (q.get("bid") or 0)) if q.get("ask") and q.get("bid") is not None else (0.01, 0.02)
        bid = q.get("bid")
        v["quote"] = {k: q.get(k) for k in ("bid", "ask", "mid", "spread", "spread_pct", "age_s", "executable", "problems", "provider",
                                            "delta", "gamma", "iv")}
        if bid is not None:
            v["pnl_liquidation"] = round(((bid - slip) - p["fill"]) * 100 * p["qty_open"] - fee * p["qty_open"] + (p["realized"] or 0), 2)
        if q.get("mid") is not None:
            v["pnl_mid"] = round((q["mid"] - p["fill"]) * 100 * p["qty_open"] + (p["realized"] or 0), 2)
    v["stall_left_min"] = exits.stall_countdown(p) if pl.get("green") else None
    v["green"] = pl.get("green")
    return v


def counters():
    d = core.policy()["discipline"]
    lim = core.policy()["v3"]["limits"]
    return {"paper": {"ideas": paper.ideas_today("paper"), "cap": lim["main_ideas_per_day"], "streak": paper.streak("paper"),
                      "stop_after": d["stop_day_after_consecutive_losses"], "a_only_after": d["a_only_after_consecutive_losses"]},
            "research": {"ideas": paper.ideas_today("research"), "streak": paper.streak("research")},
            "old": {"ideas": paper.ideas_today("old"), "streak": paper.streak("old")},
            "real": {"streak": paper.streak("real")}}


def state(since):
    sess = core.session_info()
    pos = store.positions(status="OPEN") + store.positions(status="PENDING")
    for p in pos:
        try:
            p["view"] = position_view(p)
        except Exception as e:
            p["view"] = {"error": type(e).__name__}
    watches = [dict(w, plan=json.loads(w["plan"])) for w in store.q("SELECT * FROM watches WHERE status='ACTIVE'")]
    eng = engine._state
    paper_status = ("FAULT" if eng["errors"] >= 3 else "PAUSED" if not engine.paper_enabled()
                    else "RUNNING" if sess["entries_allowed"] else "IDLE (" + sess["state"] + ")")
    return clean({
        "now": store.ts(), "session": sess, "policy_version": core.policy()["version"],
        "engine": {"last_tick": eng["last_tick"], "errors": eng["errors"], "last_error": eng["last_error"], "started": STARTED},
        "paper": {"enabled": engine.paper_enabled(), "status": paper_status,
                  "broker": "internal simulator on Schwab quotes (no broker, no orders)"},
        "budget": {led: engine.ledger_budget(led) for led in ("real", "paper", "research", "old")},
        "counters": counters(),
        "regime": {t: (engine.snapshot(t).get("regime")) for t in core.policy()["instruments"]},
        "positions": pos, "watches": watches, "last_plan": store.kv_get("last_plan"),
        "events": store.events_since(since), "seq": store.last_seq(),
        "ai_calls_today": ai_calls_today(), "chat_connected": bool(CHAT_WEBHOOK),
        "data": dict(marketdata.status(), candles=engine.data_source(),
                     options=marketdata.provider().name),
        "unreviewed_today": unreviewed_today(), "unreviewed": unreviewed_list(),
        "day_wrap_done": bool((store.journal_get(core.now_et().strftime("%Y-%m-%d")).get("notes") or {}).get("wrap_done")),
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
        if u.path == "/vendor/lwc.js":            # TradingView Lightweight Charts 5.2.1 (Apache-2.0), served locally: no CDN needed
            with open(os.path.join(HERE, "vendor", "lightweight-charts-5.2.1.js"), "rb") as f:
                return self._send(200, f.read(), "application/javascript; charset=utf-8")
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
            if u.path == "/api/news":
                return self._json(alerts.recent_news(int(q.get("limit", ["20"])[0] or 20)))
            if u.path == "/api/alerts":
                return self._json(alerts.settings())
            if u.path == "/api/schwab/status":
                return self._json(dict(schwab.status(), callback=schwab.callback(), candles=engine.data_source()))
            if u.path == "/api/schwab/login":
                if not schwab.configured():
                    return self._send(400, "Add SCHWAB_APP_KEY and SCHWAB_APP_SECRET to Chart's Secrets first.", "text/plain")
                return self._send(302, b"", "text/plain", {"Location": schwab.login_url()})
            if u.path == "/api/kronos":
                import kronos_shadow
                kronos_shadow.migrate()
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
            if u.path == "/api/chain":  # view-only option chain; no order path exists here
                t = q.get("t", ["SPY"])[0].upper()
                if not (t in ("SPY", "QQQ") or watchlist.valid(t)):
                    return self._json({"error": "bad ticker"}, 400)
                exp = q.get("exp", [None])[0]
                if exp and not __import__("re").fullmatch(r"\d{4}-\d{2}-\d{2}", exp):
                    exp = None
                n = max(4, min(20, int(q.get("n", ["10"])[0] or 10)))
                res = engine.option_chain(t, q.get("side", ["C"])[0], exp, n)
                return self._json(clean({k: v for k, v in res.items() if not k.startswith("_")}))
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
                    v3 = s.get("v3") or {}
                    d["levels_v3"] = clean({k: {"value": v.get("value"), "source": v.get("source"), "complete": v.get("complete")}
                                            for k, v in (v3.get("levels") or {}).items()})   # the exact levels the engine uses
                    d["regime_v3"] = (v3.get("regime") or {}).get("label")
                    d["data"] = (s.get("meta") or {}).get("provider")
                    out["tickers"].append(d)
                return self._json(out)
            if u.path == "/api/chart":
                import chartfeed
                return self._json(clean(chartfeed.build(q.get("t", ["SPY"])[0].upper(), q.get("tf", ["2"])[0])))
            if u.path == "/api/data/status":
                return self._json(clean(marketdata.status()))
            if u.path == "/api/candidates":
                day = q.get("date", [core.now_et().strftime("%Y-%m-%d")])[0][:10]
                pf = q.get("portfolio", [None])[0]
                rows = store.q("SELECT * FROM candidates WHERE date=?" + (" AND portfolio=?" if pf else "") + " ORDER BY ts DESC LIMIT 300",
                               (day, pf) if pf else (day,))
                for r in rows:
                    for k in ("reasons", "evidence", "plan", "outcome"):
                        try:
                            r[k] = json.loads(r[k]) if r[k] else None
                        except ValueError:
                            pass
                return self._json(clean(rows))
            if u.path == "/api/evaluation":
                import evaluation
                return self._json(clean(evaluation.report()))
            if u.path == "/api/portfolios":
                since = q.get("since", [(core.now_et() - __import__("datetime").timedelta(days=30)).strftime("%Y-%m-%d")])[0][:10]
                out = {}
                for led in ("real", "paper", "research", "old"):
                    rows = store.q("SELECT realized, status, date FROM positions WHERE ledger=? AND date>=?", (led, since))
                    closed = [r for r in rows if r["status"] == "CLOSED"]
                    wins = [r["realized"] for r in closed if (r["realized"] or 0) > 1]
                    losses = [r["realized"] for r in closed if (r["realized"] or 0) <= -1]
                    gw, gl = sum(wins), -sum(losses)
                    out[led] = {"trades": len(closed), "sessions": len({r["date"] for r in rows}), "wins": len(wins), "losses": len(losses),
                                "breakeven": len(closed) - len(wins) - len(losses), "net": round(sum(r["realized"] or 0 for r in closed), 2),
                                "win_rate": round(100 * len(wins) / len(closed), 1) if closed else None,
                                "expectancy": round(sum(r["realized"] or 0 for r in closed) / len(closed), 2) if closed else None,
                                "profit_factor": round(gw / gl, 2) if gl > 0 else None,
                                "small_sample": len(closed) < 30}
                out["note"] = ("Ledgers are separate: real = your reported Robinhood fills; paper = v3 main; research = v3 shadow "
                               "(keeps going after main limits); old = frozen old policy. Small samples are not evidence of an edge.")
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
            if u.path == "/api/news":  # Chart's news-scan routine posts market-moving headlines here
                items = b.get("items") if isinstance(b.get("items"), list) else [b]
                return self._json({"added": len(alerts.add_news(items))})
            if u.path == "/api/alerts":
                return self._json(alerts.set_settings(b))
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
                core.EVENTS_FILE.write_text(json.dumps({"date": d, "events": evs}, indent=1))
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
    try:
        import schwab_stream
        print("Schwab stream:", "starting" if schwab_stream.start() else "not available (install websockets) - Schwab REST polling", flush=True)
    except Exception as e:
        print("Schwab stream not started:", e, flush=True)
    start_kronos()
    print(f"DeltaDesk running: http://localhost:{PORT}  policy {core.policy()['version']}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
