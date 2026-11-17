"""v4 UI refresh (index.html): the Today page, light/dark, phone layout. Static checks that nothing Nick had before was
dropped (every endpoint, panel id, label and switch), that the page gained no order control, no real-broker path and no
new external script, plus a headless-browser render against a small fake desk when Playwright is installed (skipped
otherwise: GitHub Actions and Chart's computer don't install it)."""
import json
import re
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
HTML = (ROOT / "index.html").read_text()

# Every endpoint the page called before the refresh, plus api/health (an existing endpoint the Today page now reads).
ENDPOINTS = [
    "api/state", "api/command", "api/chart", "api/chain", "api/watchlist", "api/news", "api/symbol", "api/alt", "api/alerts",
    "api/journal", "api/history", "api/trade_note", "api/export.csv", "api/calendar", "api/breakdown", "api/lessons",
    "api/portfolios", "api/candidates", "api/paper/pause", "api/scanner", "api/setups", "api/catalysts", "api/catalysts/search",
    "api/earnings", "api/assess", "api/autopilot", "api/markets/settings", "api/evaluation", "api/strategies", "api/lab", "api/lab/report",
    "api/lab/contracts", "api/research", "api/diagnostics", "api/learning", "api/learning/export", "api/research/registry",
    "api/policy", "api/knowledge", "api/kronos", "api/schwab/status", "api/schwab/login", "api/schwab/connect",
    "api/schwab/disconnect", "api/schwab/restart-stream", "api/v4?since=", "api/v4/positions", "api/v4/kill", "api/v4/enable",
    "api/v4/decisions", "api/health", "api/v4/rules",
]
# Every panel, number and control the page had (element ids), the old Research ids now on Today, and the Today page's own.
IDS = """otherPill sess sessLeft sessRing watchWrap watch realpl paperst clock streak bellBtn bellTxt voiceBtn banner bannerText
    mkTicker px biasLbl age dayType win aiCalls chain chTitle chSum chExp chSpot chToggle chMain chBody chPick chpName chpMeta chpAsk
    chpLog chNote chFeed wl wlSrc wlAdd wlInput pane-watch pane-feed pane-news muteBtn feed feedEmpty newsList feedBadge newsBadge
    chartFrame chartSym tfSeg feedChip srcSeg desk lgd tv goLive plan planAge rscroll posTitle simNote positions chat watchBtn
    sendForm msg sendBtn fillForm fillCancel sendStatus ledgers eq pauseBtn killBtn paperBroker paperOpen paperOpps paperHist
    scanStat scanTable scanAlerts scanOut symForm symIn symList mkHealth tzSeg mkSym mkTf mkExt mkChip mkStat mkDesk mkLgd mkLive
    mkReadT mkRead mkTickNews mkTickEarn setSum setStat setFilters fDir fKind fPx fRv fLiq fQ fWl fBest fSort setTable setCover
    setDefs setDefList catSum catF catList catCover earnList earnCover autoPause autoList mkSettings ruleCmp stratQ stratTable labQ
    labStat labLedgers wwCtl wwBy wwCondL wwCond wwFam wwT wwEx wwAll wwTable ctTable
    v4Risk v4Kill v4Track v4Books v4Open v4News v4Archive v4Retired labCards labSince labTable labOpen labCands labDiag
    jdate jtoday jsave calMonth calPrev calNext cal csvLink brk jReal jPaper qnForm qn qnList n-thesis n-exec n-emo n-mis n-les
    rvReal rvPaper rvLessons lnOrbx lnExport lnOpp lnShadow lnHyp lnReg polVer policy catalog alertBox schStatus dataSrc kxStatus
    kronos cards jarvis jvHands jvClose jvCore jvState jvTicker jvHeard jvReply jvHint tapeBar tape jBadge
    v-today v-trade v-scan v-markets v-paper v-journal v-review v-research v-learning
    tdWhen tdAlerts tdTiles tdChecks tdTrack tdTrackSub tdBooksSec tdPos tdPosYou tdPosV3 tdPlans tdDecSum tdDec tdDecV3
    tdSw tdSwRows v4On tdLimits tdHealth tdWorkers v4Note themeBtn""".split()
LABELS = ["4 Rules", "Today", "My trades", "Scanner", "Markets", "v3 Paper", "Journal", "Review", "Research", "Learning",  # the views
          "Desk P/L today", "Since the fresh start", "Open positions", "Decisions today", "Errors and blocks", "Engine and data",
          "Your P/L today", "Session checklist", "Fresh start", "Books and ledgers", "Switches and risk", "News drift",
          "Retired ledgers (archive)", "Full table", "options shadow", "vs random", "Source backtest", "source run",
          "Daily loss limit", "v4 kill switch", "Kill switch", "Pause paper entries", "Open Legend",
          'class="chip paper">PAPER', 'class="chip bt">BACKTEST', 'class="chip mod">MODELED', 'class="chip live">LIVE']


def test_every_endpoint_the_page_had_is_still_called():
    for e in ENDPOINTS:
        assert e in HTML, e
    used = set(re.findall(r"api/[a-z0-9_/.\-]+[a-z0-9]", HTML))
    allowed = {e.split("?")[0] for e in ENDPOINTS} | {"api/v4"}
    extra = {u for u in used if u not in allowed and not u.startswith(("api/v4-", "api/health."))}
    assert not extra, f"endpoints not in the inventory: {sorted(extra)}"          # nothing new (an order path) slipped in


def test_every_panel_label_and_switch_is_still_there():
    ids = set(re.findall(r'\bid="([^"$]+)"', HTML))
    missing = [i for i in IDS if i not in ids]
    assert not missing, missing
    assert len(re.findall(r'\bid="v4Books"', HTML)) == 1 and len(re.findall(r'\bid="v4Open"', HTML)) == 1   # no duplicate ids
    for lab in LABELS:
        assert lab in HTML, lab
    for f in ("l.source_run", "l.evidence", "l.status", "l.backtest", "l.watch_only", "l.enabled", "l.refusal", "l.risk_blocks",
              "l.by_ticker", "l.shadow", "l.random", "t.desk", "r.entries_blocked", "r.v4_enabled", "book_daily_loss_usd"):
        assert f in HTML, f                                 # the sprint/fresh-start/risk fields the cards and alerts read


def test_four_rules_is_the_landing_page_and_the_old_research_link_still_works():
    """Nick, 2026-11-17: track the 4 rules like the v3 page. The 4 Rules tab is first and opens by default."""
    assert 'const VIEWS = ["rules","today",' in HTML and 'v = VIEWS.includes(v) ? v : "rules"' in HTML
    assert re.search(r'VIEW_ALIAS = \{lab: \["today", "tdBooksSec"\]\}', HTML)
    assert re.search(r'<a href="#rules" aria-current="page" data-v="rules"', HTML)
    assert re.search(r'<section class="view page rules" id="v-rules" aria-label="4 Rules">', HTML)
    assert re.search(r'<section class="view page" id="v-today" hidden aria-label="Today">', HTML)
    assert re.search(r'<section class="view trade" id="v-trade" hidden', HTML)
    arch = re.search(r'<details class="more" id="v4Archive"[^>]*>', HTML).group(0)
    assert " open" not in arch                                                  # the archive stays collapsed by default


def test_no_order_button_and_no_path_to_a_real_broker():
    texts = [re.sub(r"<[^>]+>", "", t).strip().lower() for t in re.findall(r"<button[^>]*>(.*?)</button>", HTML, re.S)]
    texts += [re.sub(r"<[^>]+>", "", t).strip().lower() for t in re.findall(r"<a [^>]*>(.*?)</a>", HTML, re.S)]
    bad = re.compile(r"\b(buy|sell|place|submit|send) ?(order|it|now)?\b|\border\b|\bexecute\b|\btrade now\b")
    assert not [t for t in texts if bad.search(t)], [t for t in texts if bad.search(t)]
    low = HTML.lower()
    for s in ("/trader", "api/order", "api/broker", "place_order", "place_stock_order", "/orders", "alpaca.markets", "robinhood.com/api"):
        assert s not in low, s
    urls = set(re.findall(r"https?://[^\s\"'`)<>]+", HTML))
    ok = ("https://fonts.googleapis.com", "https://fonts.gstatic.com", "https://s3.tradingview.com/tv.js", "https://robinhood.com/legend",
          "https://127.0.0.1")
    assert all(u.startswith(ok) for u in urls), sorted(u for u in urls if not u.startswith(ok))


def test_no_new_external_script_or_stylesheet():
    assert re.findall(r'<script[^>]*\bsrc="([^"]+)"', HTML) == ["vendor/lwc.js", "https://s3.tradingview.com/tv.js"]
    sheets = re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"|<link[^>]*href="([^"]+)"[^>]*rel="stylesheet"', HTML)
    assert all((a or b).startswith("https://fonts.googleapis.com/") for a, b in sheets) and len(sheets) == 1
    assert "import(" not in HTML and "@import" not in HTML


def test_light_and_dark_tokens_and_the_theme_button():
    css = re.search(r"<style>(.*?)</style>", HTML, re.S).group(1)
    assert ":root{\n  color-scheme: light;" in css
    assert '@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){' in css and ':root[data-theme="dark"]{' in css
    for t in ("--bg", "--glass", "--ink", "--ink-3", "--up", "--down", "--warn", "--info", "--violet", "--c-up", "--c-down", "--c-text"):
        assert css.count(t + ":") >= 3, t                     # light, dark (system) and dark (button)
    assert 'document.documentElement.dataset.theme = th' in HTML.split("</head>")[0]   # applied before the first paint
    assert 'id="themeBtn"' in HTML and 'store.set("theme", t)' in HTML and "Theme.on(retheme)" in HTML
    body_css = css.split("*{box-sizing")[1]                    # outside the token blocks, colors come from tokens
    assert not re.findall(r"rgba\(255,255,255", body_css) and not re.findall(r"rgba\(0,0,0,", body_css)


def test_numbers_carry_their_sign_and_keep_it_on_the_same_line():
    assert 'const money = v => v == null || isNaN(v) ? "—" : (v < 0 ? "−\\u2060$" : v > 0 ? "+\\u2060$" : "$") + n2s(v);' in HTML
    assert "const pc2 = v =>" in HTML and 'toLocaleString("en-US"' in HTML


# ---------------------------------------------------------------- headless render (Playwright, optional)
def _seed_four_rules(S, store):
    """Paper trades for the 4 Rules tab (test fixtures, not desk results): closed and open v4 trades, and in the v3
    table one closed noise band trade and one VOID (expired while open)."""
    def sh(pid, led, book, day, side, px, exit_px=None, mtm=None, ticker="SPY", plan=None):
        rec = {"id": pid, "ledger": led, "book": book, "kind": "shares", "date": day, "ticker": ticker, "direction": side,
               "side": side, "qty": 4, "entry_px": px, "entry_t": f"{day}T10:00:00-05:00", "legs": [], "fees": 0.0, "risk_usd": 30.0,
               "plan": dict(plan or {}, **({"mtm": mtm} if mtm is not None else {}))}
        assert S.open_position(rec)[0], pid
        if exit_px is not None:
            S.close_position(pid, exit_px, "flat at the close")
    sh("nb:1", "nbs_spy_ls", "trend", "2026-11-13", "long", 680.0, 681.55)
    sh("nb:2", "nbs_spy_ls", "trend", "2026-11-14", "short", 679.0, 679.80)
    sh("nb:3", "nbs_spy_ls", "trend", "2026-11-16", "long", 675.0, 677.85)
    sh("rsi:1", "etf10_rsi2", "swing", "2026-11-13", "long", 52.0, 52.9, ticker="XLF")
    sh("rsi:2", "etf10_rsi2", "swing", "2026-11-16", "long", 88.0, mtm=3.2, ticker="XLE", plan={"exit_rule": "next open after a close above SMA(5)"})
    sh("pead:1", "pead_t21_tp", "pead", "2026-11-14", "long", 140.0, mtm=-6.4, ticker="NVDA", plan={"exit_rule": "20 sessions or the take-profit"})
    sh("sso:1", "core_sso", "score", "2026-11-13", "long", 101.0, mtm=45.1, ticker="SSO", plan={"exit_rule": "SPY below 0.97 x SMA200 -> SGOV"})
    base = {"symbol": "SPY   261114C00680000", "side": "C", "qty_init": 1, "grade": "", "setup": "noise", "setup_id": "", "mfe": 0, "mae": 0,
            "policy_version": "test", "verified": "", "notes": ""}
    store.pos_insert(dict(base, id="nz:1", ledger="noise", date="2026-11-14", ticker="SPY", contract="680C", qty_open=0, fill=2.5,
                          opened="2026-11-14T10:31:00-05:00", closed="2026-11-14T15:25:00-05:00", status="CLOSED", realized=-50.04,
                          plan={"exit_reason": "ALL OUT 15:25 (session rule)"}))
    store.pos_insert(dict(base, id="nz:2", ledger="noise", date="2026-11-05", ticker="SPY", contract="757P", symbol="SPY   261105P00757000",
                          side="P", qty_open=0, fill=3.93, opened="2026-11-05T10:31:00-05:00", closed="2026-11-17T09:30:00-05:00",
                          status="VOID", realized=-0.02, plan={"void": {"expiry": "2026-11-05", "value_modeled": 4.1}}))


def _fake_world(tmp_path):
    """/api/v4, positions and decisions from the desk's own code on a throwaway database; a hand-made /api/state."""
    import core
    import fakes
    import store
    import v4api
    import v4report as RP
    import v4store as S
    store.DB, store._conn = tmp_path / "desk.db", None
    core.EVENTS_FILE = tmp_path / "events.json"
    core.now_et = fakes.Clock(datetime(2026, 11, 4, 11, 42, tzinfo=core.ET))
    for i, (led, book, pnl) in enumerate([("fb_or", "sprint", 42.5), ("otm_h", "sprint", -18.0), ("noise_v2", "index", 64.0)]):
        rec = {"id": f"{led}:{i}", "ledger": led, "book": book, "kind": "option", "date": "2026-11-04", "ticker": "SPY", "direction": "long",
               "side": "C", "qty": 1, "entry_px": 1.0, "entry_t": f"2026-11-04T10:0{i}:00-05:00", "legs": [{"symbol": "SPY", "action": "buy", "qty": 1}],
               "plan": {}, "fees": 0.0, "risk_usd": 50.0}
        S.open_position(rec)
        S.close_position(rec["id"], 1.0 + pnl / 100, "test")
    S.decide("d1", "otm_h", "SPY", "FILTERED", ["f_rvol 0.91 < 1.06"], {}, "day", "test")
    _seed_four_rules(S, store)
    now = "2026-11-04T11:42:10-05:00"
    state = {"now": now, "session": {"date": "2026-11-04", "time": "11:42", "early_close": False, "holiday": False, "close": "16:00",
                                     "last_entry": "15:15", "all_out": "15:25", "state": "OPEN", "entries_allowed": True, "window": "MIDDAY"},
             "engine": {"last_tick": "2026-11-04T11:42:08-05:00", "errors": 0, "last_error": None},
             "paper": {"enabled": True, "status": "RUNNING"}, "budget": {k: {"trades_today": 0, "realized_day": 0.0} for k in ("real", "paper", "research", "old")},
             "counters": {}, "positions": [], "watches": [], "last_plan": None, "events": [], "seq": 1, "ai_calls_today": 0, "chat_connected": False,
             "data": {"executable": True, "mode": "stream", "live_label": "LIVE (Schwab stream)", "schwab": {"state": "connected", "days_left": 5}, "stream": {"phase": "live"}},
             "unreviewed_today": 0, "unreviewed": [], "day_wrap_done": False}
    return {"/api/state": state, "/api/v4": RP.overview("2026-11-02"), "/api/v4/positions": v4api.get("/api/v4/positions", {"status": ["OPEN"]}),
            "/api/v4/decisions": v4api.get("/api/v4/decisions", {"day": ["2026-11-04"]}), "/api/candidates": [],
            "/api/v4/rules": v4api.get("/api/v4/rules", {}),
            "/api/health": {"ready": True, "reasons": [], "workers": {"engine": {"state": "ok", "age_s": 1.0, "errors": 0}}, "uptime_s": 60}}


def test_today_renders_on_a_phone_without_sideways_scroll(tmp_path, monkeypatch):
    sync = pytest.importorskip("playwright.sync_api")
    import core
    import store
    for mod, attr in ((store, "DB"), (store, "_conn"), (core, "EVENTS_FILE"), (core, "now_et")):
        monkeypatch.setattr(mod, attr, getattr(mod, attr))      # restored after the test
    routes = json.loads(json.dumps(_fake_world(tmp_path), default=str))
    posts = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            p = urlparse(self.path).path
            if p in ("/", "/index.html"):
                return self._send(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
            if p == "/vendor/lwc.js":
                return self._send(200, (ROOT / "vendor" / "lightweight-charts-5.2.1.js").read_bytes(), "application/javascript")
            if p in routes:
                return self._send(200, json.dumps(routes[p]).encode(), "application/json")
            return self._send(404, b'{"error": "not in the fake desk"}', "application/json")

        def do_POST(self):
            posts.append(self.path)
            return self._send(200, b"{}", "application/json")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    errors = []
    try:
        with sync.sync_playwright() as p:
            try:
                br = p.chromium.launch()
            except Exception as e:                                 # no browser binary on this machine
                pytest.skip(f"no headless browser: {type(e).__name__}")
            for scheme in ("light", "dark"):
                ctx = br.new_context(viewport={"width": 360, "height": 780}, color_scheme=scheme)
                ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base) else r.abort())
                pg = ctx.new_page()
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.goto(base + "#today")
                pg.wait_for_selector("#tdTiles .tile:nth-child(8)", timeout=15000)
                pg.wait_for_function("() => document.querySelectorAll('#v4Books .lcard').length > 10", timeout=15000)
                tiles = pg.eval_on_selector_all("#tdTiles .tile", "els => els.map(e => e.innerText)")
                assert "PAPER" in tiles[0] and "Desk P/L today" in tiles[0] and "LIVE" in tiles[6]
                assert pg.locator("#v-today").is_visible() and not pg.locator("#v-trade").is_visible()
                assert not pg.locator("#v4Books").is_visible()                # the ledger list starts folded
                pg.click("#tdBooksMore > summary")
                sprint = pg.inner_text("section.book[aria-label='Sprint forward tests']")
                assert "source run setups_v2-012" in sprint and "PAPER" in sprint
                pg.click("details[data-k='l:otm_h'] > summary")
                det = pg.inner_text("details[data-k='l:otm_h']")
                assert "BACKTEST" in det and "out-of-sample" in det          # otm_h's own label, never called in-sample
                pg.wait_for_timeout(2500)                                      # a state poll later it is still open
                assert pg.evaluate("() => document.querySelector(\"details[data-k='l:otm_h']\").open")
                wide = pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
                assert wide <= 0, f"{scheme}: {wide}px of sideways scroll at 360px"
                bg = pg.evaluate("() => getComputedStyle(document.body).backgroundColor")
                assert (bg == "rgb(13, 9, 14)") == (scheme == "dark")
                ctx.close()
            br.close()
    finally:
        srv.shutdown()
    assert not errors, errors
    assert not posts                                                          # looking at Today sends nothing to the desk


def test_decluttered_nav_and_the_news_page():
    """Nick, 2026-11-16: "remove all the unnecessary things ... the news tab is so small". Six main views (seven with
    the 4 Rules tab, 2026-11-17), the rest under More (nothing removed); News is its own page; the small left box keeps
    Watchlist and Feed."""
    nav = re.search(r'<nav aria-label="Views">(.*?)</nav>', HTML, re.S).group(1)
    main_nav = nav.split('<details class="navmore"')[0]
    assert re.findall(r'data-v="([a-z]+)"', main_nav) == ["rules", "today", "trade", "news", "markets", "scan", "journal"]
    more = nav.split('<details class="navmore"')[1]
    assert re.findall(r'data-v="([a-z]+)"', more) == ["review", "research", "learning", "paper"]
    assert 'const VIEWS = ["rules","today","trade","news",' in HTML and 'id="v-news"' in HTML
    assert re.findall(r'data-tab="([a-z]+)"', HTML) == ["watch", "feed"]          # no tiny news tab any more
    news = re.search(r'<section class="view page" id="v-news".*?</section>', HTML, re.S).group(0)
    assert 'id="newsList"' in news and 'data-nf="key"' in news and 'data-nf="all"' in news
    assert "function sameStory(a, b)" in HTML and "newsStories(n || [])" in HTML       # repeats collapse on the page too
    assert 'x.impact === "high" || x.impact === "medium"' in HTML                    # Key = high and medium impact
    for folded in ('id="tdBooksMore"', 'id="mkResearch"'):
        tag = re.search(r'<details class="more" ' + folded + r'[^>]*>', HTML).group(0)
        assert " open" not in tag
    assert 'class="more legendline"' not in HTML


def test_four_rules_tab_renders_on_a_phone(tmp_path, monkeypatch):
    """Nick, 2026-11-17: one card per rule (paper trades out of 40, P/L, open trades, backtest line) and the noise band
    card his phone alerts follow, with VOID trades shown and not counted. No sideways scroll on a 360px phone."""
    sync = pytest.importorskip("playwright.sync_api")
    import core
    import store
    for mod, attr in ((store, "DB"), (store, "_conn"), (core, "EVENTS_FILE"), (core, "now_et")):
        monkeypatch.setattr(mod, attr, getattr(mod, attr))
    routes = json.loads(json.dumps(_fake_world(tmp_path), default=str))
    rules = routes["/api/v4/rules"]
    assert [r["ledger"] for r in rules["rules"]] == ["nbs_spy_ls", "etf10_rsi2", "pead_t21_tp", "core_sso"]
    nb = rules["rules"][0]
    assert nb["trades"] == 3 and nb["needed"] == 40 and nb["win_rate"] == 66.7 and nb["backtest"]["label"].startswith("BACKTEST")
    assert rules["noise"]["trades"] == 1 and len(rules["noise"]["void"]) == 1          # the VOID trade is listed, not counted

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            p = urlparse(self.path).path
            body, ctype = ((ROOT / "index.html").read_bytes(), "text/html; charset=utf-8") if p in ("/", "/index.html") else \
                (json.dumps(routes[p]).encode(), "application/json") if p in routes else (b"{}", "application/json")
            self.send_response(200 if p in ("/", "/index.html") or p in routes else 404)
            self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_POST(self):
            self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"{}")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    errors = []
    try:
        with sync.sync_playwright() as p:
            try:
                br = p.chromium.launch()
            except Exception as e:
                pytest.skip(f"no headless browser: {type(e).__name__}")
            ctx = br.new_context(viewport={"width": 360, "height": 780})
            ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base) else r.abort())
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base)                                                     # lands on the 4 Rules tab
            pg.wait_for_selector("#frCards .rcard:nth-child(4)", timeout=15000)
            assert pg.locator("#v-rules").is_visible() and not pg.locator("#v-today").is_visible()
            cards = pg.eval_on_selector_all("#frCards .rcard", "els => els.map(e => e.innerText)")
            assert "Noise band, SPY shares" in cards[0] and "3 of 40 paper trades" in cards[0] and "BACKTEST" in cards[0]
            assert "2 of 3 (66.7%)" in cards[0]
            assert "SSO trend core" in cards[3] and "1 (+$45.10)" in cards[3].replace("⁠", "")
            noise = pg.inner_text("#frNoise")
            assert "Noise band, 0DTE options" in noise and "T42: FAIL" in noise
            pg.click("#frNoise details.more > summary")
            assert "VOID" in pg.inner_text("#frNoise") and "Not counted" in pg.inner_text("#frNoise")
            assert "PAPER" in pg.inner_text("#frNote")
            wide = pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
            assert wide <= 0, f"{wide}px of sideways scroll at 360px"
            ctx.close()
            br.close()
    finally:
        srv.shutdown()
    assert not errors, errors
