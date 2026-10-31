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
  GET  /api/schwab/status|login, POST /api/schwab/connect|disconnect|restart-stream   Schwab market data (market data only)
  GET/POST /api/news         Chart's news scan posts headlines {"items":[{headline,source,time,tickers,impact,direction,why}]}
  GET/POST /api/alerts       alert toggles (setups, moves, news); phone push via NTFY_TOPIC (ntfy app)
  GET  /api/chart?t=ANY&tf=1|2|5|15&ext=0|1&since=<unix s>  desk chart (since = live tail only)
  GET  /api/symbol?q=nvid    symbol search (Schwab instruments; desk lists as a labeled fallback)
  GET  /api/x/targets        v3.3: what Chart's free X scan should research now (earnings, movers, setups, your trades)
  GET  /api/setups           setups board: objective setups over the scanned universe, coverage and definitions
  GET  /api/chart?t=SPY&tf=1|2|5  desk chart from the SAME Schwab pipeline as the engine: candles, volume, VWAP,
                             EMA9/21, MACD, levels (with sources), entry/exit markers, feed + freshness
  GET  /api/data/status      provider, stream/REST/fallback mode, entitlements check, latency distributions, gaps
  GET  /api/candidates       every candidate with evidence, decision, rejection reasons, limit blocks (per portfolio)
  GET  /api/portfolios       real / main paper / research / old-policy results kept apart
  GET  /api/evaluation       the forward paper test scored against the criteria fixed in policy.json beforehand
  GET  /api/scanner          today's stocks-in-play ranking with every number and reason, scanner status, movers alerts
  GET  /api/research         every paper ledger side by side: expectancy, avg win/loss, drawdown, stock move vs option
  GET  /api/diagnostics      the latest diagnostics report from backtest.py
  GET  /legacy               the old desk page (custom indicator chart)
  GET  /api/lab[/report?by=&cond=&exits=|/signals|/contracts]  v3.4 strategy lab: signal tape, lab paper ledgers, what works
       where, and (3.4.2) which option contract converts the same signals
  Legacy: /api/read /api/bars /api/last /api/plan /api/chat
Real money: only Nick, in Robinhood. This server sends NO orders anywhere: paper trading is simulated internally
on Schwab quotes. Schwab access is market data only (trading/account endpoints are refused in code).
"""
import hmac
import json
import math
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

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
if not DESK_TOKEN and os.environ.get("CREDENTIALS_DIRECTORY"):      # v3.5: systemd LoadCredential=deltadesk-token
    try:
        with open(os.path.join(os.environ["CREDENTIALS_DIRECTORY"], "deltadesk-token")) as _f:
            DESK_TOKEN = _f.read().strip()
    except OSError:
        pass
_FAILS = {}                                                          # v3.5: failed-auth rate limit per client
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


def schwab_view():
    """Connection + stream + feed state for the Rules page and the top bar. Never contains a token."""
    st = schwab.status()
    try:
        import schwab_stream
        stream = schwab_stream.state()
    except Exception as e:
        stream = {"phase": "off", "detail": type(e).__name__}
    md = marketdata.status()
    return dict(st, stream=stream, feed=md.get("live_label"), mode=md.get("mode"), last_msg_age_s=md.get("last_msg_age_s"),
                api={k: v for k, v in schwab.STATS.items()}, candles=engine.data_source())


SETTINGS_KEYS = {"catalyst_settings": {"xai_enabled": bool, "xai_daily_budget_usd": float, "xai_max_calls_per_hour": int,
                                        "edgar_enabled": bool, "alert_min_gap_min": int},
                  "setups_settings": {"enabled": bool, "quotes_every_s": int, "bars_calls_per_min": int, "mover_pct": float,
                                      "rvol_unusual": float}}
LIMITS = {"xai_daily_budget_usd": (0, 50), "xai_max_calls_per_hour": (0, 60), "quotes_every_s": (30, 600),
          "bars_calls_per_min": (0, 40), "alert_min_gap_min": (0, 120), "mover_pct": (0.5, 20), "rvol_unusual": (1, 10)}


def markets_settings(b=None):
    """Scan schedule, universe sizing, alert pacing and spending limits (validated, clamped; never secrets)."""
    import catalysts
    import scanner_setups
    if b:
        for key, spec in SETTINGS_KEYS.items():
            cur = store.kv_get(key) or {}
            for k, typ in spec.items():
                if k in b:
                    v = typ(b[k]) if typ is not bool else bool(b[k])
                    if k in LIMITS:
                        v = max(LIMITS[k][0], min(LIMITS[k][1], v))
                    cur[k] = v
            store.kv_set(key, cur)
    c, s2 = catalysts.cfg(), scanner_setups.cfg()
    return {"catalysts": {k: c[k] for k in SETTINGS_KEYS["catalyst_settings"]}, "setups": {k: s2[k] for k in SETTINGS_KEYS["setups_settings"]},
            "xai_key_set": bool(os.environ.get("XAI_API_KEY")), "sec_user_agent_set": bool(os.environ.get("SEC_USER_AGENT")),
            "spend_today": catalysts._spend_today(), "limits": LIMITS,
            "prices": {"grok-4.7 input per 1M tokens": 2.0, "grok-4.7 output per 1M tokens": 6.0, "x_search per 1k posts": 5.0,
                       "web_search per 1k calls": 5.0, "checked": "docs.x.ai pricing page, updated Oct 10 2026"}}


def state(since):
    sess = core.session_info()
    pos = [p for p in store.positions(status="OPEN") + store.positions(status="PENDING")
           if not str(p["ledger"]).startswith("lab_")]           # v3.4: lab trades are on /api/lab (Markets)
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

    def _fail(self, e, path):
        """A structured error with a diagnostic id; the traceback goes to the server log only (never tokens: the
        query string, which carries k=, is not logged)."""
        import traceback
        import uuid
        diag = uuid.uuid4().hex[:8]
        print(f"[error {diag}] {path}: {type(e).__name__}: {str(e)[:200]}\n" + "".join(traceback.format_exc(limit=6)), flush=True)
        return self._json({"error": f"the desk hit an internal error on {path} ({type(e).__name__})", "diag_id": diag}, 500)

    def _json(self, obj, code=200):
        return self._send(code, json.dumps(obj, default=str))

    def log_message(self, *a):
        pass

    def _client(self):
        xff = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return xff or self.client_address[0]

    def _proxied(self):
        return any(self.headers.get(h) for h in ("X-Forwarded-For", "X-Forwarded-Host", "Cf-Connecting-Ip", "Tailscale-Funnel-Request",
                                                  "Forwarded"))

    def _ok(self, q):
        if not DESK_TOKEN:
            # v3.5: with no token set, only direct local requests are served. Anything that came through a tunnel or
            # proxy (Funnel, cloudflared, ngrok all connect from 127.0.0.1) is refused, so a missing token can never
            # publish the desk to the internet.
            return not self._proxied()
        k = self._client()
        f = _FAILS.get(k)
        if f and f[0] >= 20 and time.time() - f[1] < 600:
            return False                                             # too many bad tries from this client: 10 min pause
        if hmac.compare_digest(q.get("k", [""])[0].encode(), DESK_TOKEN.encode()):
            return True
        for part in (self.headers.get("Cookie") or "").split(";"):          # v3.5: a real cookie parse, constant-time compare
            ck, _, v = part.strip().partition("=")
            if ck == "desk_k" and hmac.compare_digest(v.encode(), DESK_TOKEN.encode()):
                return True
        if q.get("k") or "desk_k=" in (self.headers.get("Cookie") or ""):    # a WRONG token was offered: count it
            n, t0 = _FAILS.get(k, (0, time.time()))
            _FAILS[k] = (n + 1, t0 if time.time() - t0 < 600 else time.time())
            if len(_FAILS) > 5000:
                _FAILS.clear()
        return False

    def _same_origin(self):
        """v3.5: a browser POST must come from this desk's own page (CSRF). Tools with no Origin header (Chart's API
        calls, curl) are unaffected; they still need the token."""
        o = self.headers.get("Origin")
        if not o or o == "null":
            return o is None
        host = (self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").split(",")[0].strip()
        return urlparse(o).netloc == host

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
        if u.path == "/healthz":                  # v3.5: liveness for an uptime checker - no data, no token needed
            return self._json({"alive": True})
        if u.path == "/readyz":                   # readiness: yes/no + short reasons, nothing secret or personal
            import health
            ready, why = health.readiness()
            return self._json({"ready": ready, "reasons": why}, 200 if ready else 503)
        if not self._ok(q):
            return self._send(403, "Forbidden: open the full link Chart gave you (with ?k=...).", "text/plain")
        if u.path in ("/", "/index.html"):
            if DESK_TOKEN and "k" in q:           # v3.5: swap the link's token for a cookie and drop it from the address bar
                rest = urlencode([(k, v) for k, vs in q.items() if k != "k" for v in vs])
                return self._send(302, b"", "text/plain", {
                    "Set-Cookie": f"desk_k={DESK_TOKEN}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax"
                                  + ("; Secure" if (self.headers.get("X-Forwarded-Proto") or "") == "https" else ""),
                    "Location": "/" + (f"?{rest}" if rest else "")})
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                data = f.read()
            return self._send(200, data, "text/html; charset=utf-8")
        if u.path == "/vendor/lwc.js":            # TradingView Lightweight Charts 5.2.1 (Apache-2.0), served locally: no CDN needed
            with open(os.path.join(HERE, "vendor", "lightweight-charts-5.2.1.js"), "rb") as f:
                return self._send(200, f.read(), "application/javascript; charset=utf-8")
        if u.path in ("/legacy", "/legacy.html"):
            with open(os.path.join(HERE, "index_legacy.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        try:
            if u.path == "/api/health":            # v3.5: workers, feed, clock skew, rate budget, memory (no secrets)
                import health
                return self._json(clean(health.summary()))
            if u.path == "/api/learning":          # v3.5: opportunities, decisions, shadow outcomes, hypotheses, ORBX stages
                import learning
                return self._json(clean(learning.view(q.get("day", [None])[0])))
            if u.path == "/api/learning/export":   # CSV: decisions | shadow | opportunities | hypotheses
                import learning
                what = q.get("what", ["decisions"])[0]
                if what not in ("decisions", "shadow", "opportunities", "hypotheses"):
                    return self._json({"error": "unknown export"}, 400)
                return self._send(200, learning.export_csv(what, q.get("from", [None])[0], q.get("to", [None])[0]), "text/csv; charset=utf-8",
                                  {"Content-Disposition": f"attachment; filename=deltadesk-{what}.csv"})
            if u.path == "/api/research/registry":  # v3.5: the GitHub/paper research registry (docs/research)
                pth = os.path.join(HERE, "docs", "research", "strategy_registry.json")
                if not os.path.exists(pth):
                    return self._json({"entries": [], "note": "no registry file yet"})
                with open(pth) as f:
                    return self._json(json.load(f))
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
                return self._json(clean(schwab_view()))
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
                rows = store.q("SELECT id,ledger,date,ticker,contract,qty_init,fill,realized,status,setup,grade,mfe,mae,opened,closed,verified,notes,policy_version "
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
                t = q.get("t", ["SPY"])[0].upper().strip()
                if not watchlist.valid(t):
                    return self._json({"ticker": t, "error": "That isn't a valid ticker symbol.", "candles": [],
                                       "status": {"state": "unavailable", "why": "invalid symbol"}})
                return self._json(clean(chartfeed.build(t, q.get("tf", ["2"])[0], q.get("ext", ["0"])[0], q.get("since", [None])[0])))
            if u.path == "/api/symbol":
                return self._json(clean(schwab.search(q.get("q", [""])[0])))
            if u.path == "/api/lab":
                import lab
                return self._json(clean(lab.status()))
            if u.path == "/api/lab/report":
                import lab
                g = lambda k, d=None: (q.get(k) or [d])[0]
                return self._json(clean(lab.what_works(by=g("by", "strategy"), cond=g("cond"), family=g("family"), ticker=g("t"),
                                                       since=(g("since") or "")[:10] or None, min_n=g("min_n"),
                                                       include_all=g("all") == "1", exits=g("exits", "shared"))))
            if u.path == "/api/lab/contracts":
                import contract_lab
                g = lambda k, d=None: (q.get(k) or [d])[0]
                return self._json(clean(contract_lab.report(family=g("family") or None, since=(g("since") or "")[:10] or None)))
            if u.path == "/api/lab/signals":
                import lab
                g = lambda k, d=None: (q.get(k) or [d])[0]
                return self._json(clean({"rows": lab.signals(day=g("day"), ticker=g("t"), family=g("family"),
                                                             limit=min(500, int(g("limit", "200") or 200)))}))
            if u.path == "/api/strategies":
                import strategy_registry
                import strategy_router
                return self._json(clean(dict(strategy_registry.evidence_table(), routed_today=strategy_router.today(80))))
            if u.path == "/api/x/targets":
                import catalysts
                return self._json(clean(catalysts.x_targets()))
            if u.path == "/api/catalysts":
                import catalysts
                return self._json(clean({"items": catalysts.feed(q.get("t", [None])[0], q.get("label", [None])[0] or None),
                                         "metrics": catalysts.metrics()}))
            if u.path == "/api/earnings":
                import earnings
                t = q.get("t", [None])[0]
                if t:
                    rec = earnings.event(t.upper())
                    return self._json(clean({"event": dict(rec, phase=earnings.phase(rec)) if rec else None,
                                             "straddle": earnings.straddle(t.upper(), rec) if rec and earnings.phase(rec) == "PRE" else None}))
                return self._json(clean({"calendar": earnings.cached_calendar()}))
            if u.path == "/api/assess":
                t = q.get("t", ["SPY"])[0].upper()
                if not watchlist.valid(t):
                    return self._json({"error": "invalid symbol"}, 400)
                p = engine.build_plan(t, q.get("side", ["C"])[0].upper()[:1], None, "check")
                return self._json(clean({"plan": p, "text": commands.plan_text(p)}))
            if u.path == "/api/autopilot":
                import autopilot
                return self._json(clean({"decisions": autopilot.today(), "status": autopilot._state["status"],
                                         "last_error": autopilot._state["last_error"], "paused": store.kv_get("paper_pause"),
                                         "gate_setups": __import__("entrygate").today()[-40:]}))
            if u.path == "/api/markets/settings":
                return self._json(clean(markets_settings()))
            if u.path == "/api/setups":
                import scanner_setups
                return self._json(clean(scanner_setups.board(best_per_stock=q.get("all", ["0"])[0] != "1")))
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
            if u.path == "/api/scanner":
                import scanner
                day = q.get("date", [core.now_et().strftime("%Y-%m-%d")])[0][:10]
                ev = store.q("SELECT ts, text FROM events WHERE kind='alert' AND substr(ts,1,10)=? AND "
                             "(text LIKE 'IN PLAY%' OR text LIKE 'TOP MOVERS%' OR text LIKE 'QUICK MOVE%') ORDER BY seq DESC LIMIT 40", (day,))
                return self._json(clean({"status": scanner.status(), "rows": scanner._rows(day), "alerts": ev,
                                         "config": core.policy().get("scanner")}))
            if u.path == "/api/research":
                import evaluation
                since = q.get("since", ["2026-10-30"])[0][:10]
                import retire
                return self._json(clean({"since": since, "ledgers": {led: dict(evaluation.ledger_report(led, since), retired=retire.is_retired(led))
                                                                      for led in ("paper", "research", "exit31", "noise", "inplay", "old", "real")},
                                         "retired": retire.retired_list(),
                                         "variants": core.policy().get("research_variants"),
                                         "note": "Each ledger is separate. Under 30 trades is not evidence. Option results of the variants are "
                                                 "simulated fills on live Schwab quotes; replays and backtests use MODELED option prices."}))
            if u.path == "/api/diagnostics":
                files = sorted((core.HERE / "reports").glob("diagnostics_*.json")) if (core.HERE / "reports").exists() else []
                return self._json(json.loads(files[-1].read_text()) if files else {"none": "no diagnostics run yet: python3 backtest.py --from ... --to ..."})
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
            return self._fail(e, u.path)
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        if not self._ok(parse_qs(u.query)):
            return self._json({"error": "forbidden"}, 403)
        if not self._same_origin():
            return self._json({"error": "forbidden: cross-site request"}, 403)
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
                import catalysts                  # also into the catalyst store: label from the URL, "via Chart"
                cat = catalysts.ingest([{"tickers": [x for x in str(i.get("tickers", "")).replace(",", " ").split() if x],
                                         "headline": i.get("headline"), "summary": i.get("why"), "category": i.get("category"),
                                         "published_at": i.get("published_at") or None, "event_time": i.get("event_time") or None,
                                         "opinion": bool(i.get("opinion")), "attention": i.get("attention"),
                                         "sentiment": i.get("sentiment"), "claims": i.get("claims"),
                                         "sources": [{"url": i.get("url")}] + [{"url": u2} for u2 in (i.get("source_urls") or [])]}
                                        for i in items if isinstance(i, dict)], "Chart X scan" if b.get("via") == "x_scan" else "Chart news routine")
                return self._json({"added": len(alerts.add_news(items)), "catalysts": cat})
            if u.path == "/api/earnings/results":       # Chart: reported vs expected, each with its own source
                import earnings
                t = str(b.get("ticker", "")).upper()
                if not watchlist.valid(t):
                    return self._json({"error": "invalid symbol"}, 400)
                return self._json(clean(earnings.record_results(t, str(b.get("date", ""))[:10], b.get("metrics") or {}, b.get("source_url"),
                                                                b.get("consensus_source"), b.get("consensus_captured_at"))))
            if u.path == "/api/earnings/call":          # Chart: attributed statements from the call
                import earnings
                t = str(b.get("ticker", "")).upper()
                if not watchlist.valid(t):
                    return self._json({"error": "invalid symbol"}, 400)
                return self._json(clean(earnings.record_call(t, str(b.get("date", ""))[:10], b.get("statements"), b.get("source_url"),
                                                             b.get("source_kind") or "transcript")))
            if u.path == "/api/catalysts/search":
                import catalysts
                t = str(b.get("ticker", "")).upper()
                if not watchlist.valid(t):
                    return self._json({"error": "invalid symbol"}, 400)
                return self._json(clean(catalysts.xai_search([t], "Nick asked")))
            if u.path == "/api/earnings":
                import earnings
                return self._json(clean(earnings.confirm(str(b.get("ticker", "")).upper(), str(b.get("date", ""))[:10], b.get("timing"),
                                                         b.get("source_url"), b.get("call_time"))))
            if u.path == "/api/paper/pause":
                on = bool(b.get("on"))
                store.kv_set("paper_pause", {"at": store.ts(), "by": "Nick"} if on else None)
                store.event("note", "PAPER entries PAUSED by Nick (emergency pause)" if on else "Paper entries resumed", "paper")
                return self._json({"paused": on})
            if u.path == "/api/markets/settings":
                return self._json(clean(markets_settings(b)))
            if u.path == "/api/alerts":
                return self._json(alerts.set_settings(b))
            if u.path == "/api/schwab/connect":
                ok, msg = schwab.connect(str(b.get("url", ""))[:2000])
                if ok:
                    store.event("system", "Schwab connected: market data verified (log in again every 7 days on the Rules page)")
                return self._json(clean({"ok": ok, "message": msg, "status": schwab_view()}), 200 if ok else 400)
            if u.path == "/api/schwab/disconnect":
                msg = schwab.disconnect()
                store.event("system", "Schwab disconnected by Nick: " + msg)
                return self._json(clean({"ok": True, "message": msg, "status": schwab_view()}))
            if u.path == "/api/schwab/restart-stream":
                import schwab_stream
                if not schwab.ready():
                    return self._json({"ok": False, "message": "No working Schwab login: press Connect Schwab first."}, 400)
                started = schwab_stream.restart("restarted by Nick")
                return self._json(clean({"ok": bool(started), "message": "Stream restarting (one clean connection)." if started
                                         else "The stream can't start: the websockets package isn't installed (REST polling continues).",
                                         "status": schwab_view()}))
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
            return self._fail(e, u.path)
        self._json({"error": "not found"}, 404)


def engine_loop():
    while True:
        engine.tick()
        time.sleep(5)


def kronos_orphans(ps_out=None):
    """v3.4.1: kronos_shadow.py copies of THIS desk whose server is gone (their parent is pid 1 / launchd, or isn't a
    server.py). Copies started by a live server are left alone. Returns [(pid, ppid)]."""
    import subprocess
    if ps_out is None:
        try:
            ps_out = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True, timeout=10).stdout
        except Exception:
            return []
    script = os.path.join(HERE, "kronos_shadow.py")
    procs = {}
    for line in ps_out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            procs[int(parts[0])] = (int(parts[1]), parts[2])
    out = []
    for pid, (ppid, cmd) in procs.items():
        if script not in cmd or pid == os.getpid():
            continue
        parent_cmd = procs.get(ppid, (None, ""))[1]
        if ppid <= 1 or "server.py" not in parent_cmd:
            out.append((pid, ppid))
    return out


def stop_kronos_orphans():
    import signal
    killed = []
    for pid, _ppid in kronos_orphans():
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except OSError:
            pass
    if killed:
        time.sleep(3)
        for pid in killed:
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)               # still there after SIGTERM
            except OSError:
                pass
    return killed


def start_kronos():
    """Kronos runs in its own process, without broker keys or the desk token, and can never block the desk.
    v3.4.1: leftover copies from earlier servers are stopped first, the child holds a lock (one copy at most) and
    exits when this server dies, so restarts can't pile copies up."""
    import retire
    if os.environ.get("KRONOS") != "1" or not retire.kronos_enabled():     # v4: off by default (config/v4.json)
        return None
    import subprocess
    try:
        k = stop_kronos_orphans()
        if k:
            print(f"Kronos: stopped {len(k)} leftover copies from earlier servers: {k}", flush=True)
    except Exception as e:
        print("Kronos: leftover check failed:", e, flush=True)
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


def _singleton():
    """v3.5: one desk process per folder. A second copy (a restart overlapping the old one, or a supervisor plus the
    old watchdog) exits BEFORE starting any worker, so two engines can never trade the same ledgers at once."""
    import fcntl
    path = os.path.join(HERE, "journal", "server.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    f = open(path, "a+")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Another DeltaDesk server is already running from this folder: exiting without starting workers.", flush=True)
        sys.exit(3)
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    return f


def _graceful(signum, frame):
    print(f"DeltaDesk stopping (signal {signum}): open positions stay in the database and are managed again on restart.", flush=True)
    try:
        import health
        health.beat("server", True, "stopping")
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    _LOCK = _singleton()
    import signal
    signal.signal(signal.SIGTERM, _graceful)
    store.conn()
    core.policy()
    threading.Thread(target=engine_loop, daemon=True).start()
    try:
        import schwab_stream
        print("Schwab stream:", "starting" if schwab_stream.start() else "not available (install websockets) - Schwab REST polling", flush=True)
    except Exception as e:
        print("Schwab stream not started:", e, flush=True)
    try:
        import scanner
        print("Scanner:", "started" if scanner.start() else "off", flush=True)
        import scanner_setups
        print("Setups board:", "started" if scanner_setups.start() else "off", flush=True)
        import autopilot
        import catalysts
        import earnings
        print("Catalysts:", "started" if catalysts.start() else "off", "| Autopilot (paper):", "started" if autopilot.start() else "off", flush=True)
        threading.Thread(target=earnings.refresh_calendar, daemon=True, name="earnings-calendar").start()
        import lab
        print("Strategy lab (signal tape + lab paper ledgers):", "started" if lab.start() else "off", flush=True)
        import sip_orb
        print("v4 stock ledgers (sip_orb5, sip_orb5_x, sip_orb15, earn_day + options shadows):",
              "started" if sip_orb.start() else "off", flush=True)
    except Exception as e:
        print("Scanner not started:", e, flush=True)
    try:                                           # v3.5: journal/learning tables + the preregistered hypotheses
        import learning
        learning.migrate()
        learning.seed_hypotheses()
        import release
        print("Release", release.RELEASE_ID, flush=True)
    except Exception as e:
        print("Learning journal not ready:", e, flush=True)
    start_kronos()
    print(f"DeltaDesk running: http://localhost:{PORT}  policy {core.policy()['version']}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
