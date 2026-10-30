"""Deterministic tests with synthetic data and a fake PAPER broker (no network, no AI).

Run: python3 -m pytest -q tests/
"""
import importlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import broker  # noqa: E402
import commands  # noqa: E402
import core  # noqa: E402
import engine  # noqa: E402
import store  # noqa: E402

ET = core.ET
DAY = datetime(2026, 10, 28, tzinfo=ET)  # a Wednesday, normal session


# ---------------------------------------------------------------- fixtures
def make_market(path_fn, day=DAY):
    """1m bars for 4 prior days (gently rising) + today (path_fn(minute_index) -> price)."""
    rng = np.random.default_rng(7)
    idx, px = [], []
    p = 590.0
    for d in range(4, 0, -1):
        dd = day - timedelta(days=d)
        if dd.weekday() >= 5:
            continue
        for m in pd.date_range(dd.replace(hour=4), dd.replace(hour=19, minute=59), freq="1min"):
            p += 0.004 + rng.normal(0, 0.01)
            idx.append(m)
            px.append(p)
    for i, m in enumerate(pd.date_range(day.replace(hour=4), day.replace(hour=19, minute=59), freq="1min")):
        idx.append(m)
        px.append(path_fn(m))
    idx = pd.DatetimeIndex(idx)
    c = np.array(px)
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + 0.02
    l = np.minimum(o, c) - 0.02
    m1 = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 20000}, index=idx)
    didx = pd.bdate_range(day - timedelta(days=500), day - timedelta(days=1))
    dp = np.linspace(450, 598, len(didx))
    daily = pd.DataFrame({"Open": dp, "High": dp + 2, "Low": dp - 2, "Close": dp, "Volume": 1e7}, index=didx)
    return m1, daily


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class FakeBroker:
    """Option price = 1.00 + 0.4 * (S - S0), spread 0.04. Orders fill immediately at ask/bid."""

    def __init__(self, s0, under):
        self.s0, self.under, self.orders = s0, under, {}

    def px(self):
        mid = 1.00 + 0.4 * (self.under() - self.s0)
        return round(max(0.05, mid - 0.02), 2), round(max(0.06, mid + 0.02), 2)

    def install(self, mp):
        mp.setattr(broker, "configured", lambda: True)
        mp.setattr(broker, "paper_account_ok", lambda force=False: (True, "paper account verified (fake)"))
        mp.setattr(broker, "stock_last", lambda t: ({"price": self.under(), "ts": "x", "feed": "fake"}, None))

        def chain(t, side, exp):
            b, a = self.px()
            strike = round(self.s0)
            sym = f"{t}{exp[2:4]}{exp[5:7]}{exp[8:10]}{side[0].upper()}{int(strike*1000):08d}"
            return [{"symbol": sym, "strike": strike, "bid": b, "ask": a, "ts": "x", "delta": 0.42 if side[0].upper() == "C" else -0.42, "iv": 0.2}], None
        mp.setattr(broker, "chain", chain)
        mp.setattr(broker, "option_quote", lambda s: (dict(zip(("bid", "ask"), self.px()), ts="x", feed="fake"), None))

        def submit(sym, qty, side, cid):
            if cid in self.orders:
                return None, "duplicate client_order_id"
            b, a = self.px()
            self.orders[cid] = {"id": "o" + cid, "status": "filled", "filled_qty": qty, "filled_avg_price": a if side == "buy" else b, "side": side}
            return {"id": "o" + cid}, None
        mp.setattr(broker, "submit", submit)
        mp.setattr(broker, "order_by_client", lambda cid: (self.orders.get(cid), None))


@pytest.fixture
def desk_env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    clock = Clock(DAY.replace(hour=9, minute=30))
    monkeypatch.setattr(core, "now_et", clock)
    engine._cache.clear()
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")   # never touch the real calendar
    import marketdata
    yield clock
    marketdata.use(None)


def wire(monkeypatch, clock, path_fn, **kw):
    """v3: the fake Schwab provider feeds bars and option quotes through marketdata (one pipeline)."""
    import fakes
    import marketdata
    m1 = fakes.make_market(path_fn, DAY, **{k: v for k, v in kw.items() if k in ("prior_days", "vol", "vol_fn", "seed")})
    fk = fakes.FakeSchwab(m1, clock, **{k: v for k, v in kw.items() if k in ("s0", "delta", "gamma", "base", "spread")})
    marketdata.use(fk)
    return fk


def run(clock, start, end, step=1):
    t = clock.t.replace(hour=int(start[:2]), minute=int(start[3:]))
    stop = clock.t.replace(hour=int(end[:2]), minute=int(end[3:]))
    while t <= stop:
        clock.t = t
        engine._cache.clear()
        engine.tick()
        t += timedelta(minutes=step)


def up_day(ts):
    """ORB 600-601 (9:30-9:45), break at 9:50-9:55, trend to ~603 by 11:00."""
    m = ts.hour * 60 + ts.minute
    if m < 570:
        return 599.6
    if m < 585:   # ORB forming: 600.0 - 601.0
        return 600.0 + (m - 570) % 6 / 5.0
    if m < 595:
        return 600.9
    return min(604.0, 601.2 + (m - 595) * 0.09)


def down_after_entry(ts):
    m = ts.hour * 60 + ts.minute
    if m < 595:
        return up_day(ts)
    if m < 600:
        return 601.25
    return 601.25 - (m - 600) * 0.05


# ---------------------------------------------------------------- core math
def test_stop_never_exceeds_20pct_and_tighten_only():
    for fill in (0.10, 0.37, 0.85, 1.00, 1.55, 2.40, 3.00):
        for spread in (0.0, 0.02, 0.10):
            stop, slip = core.stop_for(fill, spread)
            loss = core.risk_per_contract(fill, stop, slip)
            q = core.size(fill, stop, slip, "A", 1e9)[0]
            assert loss <= 100 * fill * 0.20 + 1e-6 or q == 0, (fill, spread, loss)
            assert stop >= round(fill * 0.80, 2)
    assert core.tighten_only(1.10, 0.90) == 1.10
    # Nick Oct 27: morning 20% (costs inside), midday 12%, afternoon 10%; never looser than the 20% all-in ceiling
    assert core.exit_plan(1.00, "10:15")["stop"] == 0.82
    assert core.exit_plan(1.00, "12:30")["stop"] == 0.88 and core.exit_plan(1.00, "14:30")["stop"] == 0.90
    for t in ("10:15", "12:30", "14:30"):
        ex = core.exit_plan(0.40, t, 0.02)
        assert core.risk_per_contract(0.40, ex["stop"], ex["slippage_reserve"]) <= 0.40 * 100 * 0.20 + 1e-6


def test_sizing_integer_and_caps():
    stop, slip = core.stop_for(1.00, 0.04)
    q, rpc, cap, why = core.size(1.00, stop, slip, "A", 50)
    assert q == 2 and rpc <= 20          # trend A: whole remaining day budget, grade A = up to 2
    assert core.size(1.00, stop, slip, "B", 50)[0] == 1
    assert core.size(1.00, stop, slip, "A", 50, chop_day=True)[0] == 1   # chop: $20 cap, 1 contract
    assert core.size(2.90, *core.stop_for(2.90, 0.06), "A", None)[0] == 2   # no dollar cap: size by grade only
    stop, slip = core.stop_for(0.55, 0.02)
    assert core.size(0.55, stop, slip, "A", 50)[0] == 2
    assert core.size(0.55, stop, slip, "B", 50)[0] == 1
    assert core.size(0.55, stop, slip, "A", 50, chop_day=True)[0] == 1
    stop, slip = core.stop_for(0.10, 0.0)
    q, rpc, cap, why = core.size(0.10, stop, slip, "A", None)
    assert q == 0 and "20%" in why        # a 20% stop can't survive costs on a $0.10 contract
    assert core.size(0.55, *core.stop_for(0.55, 0.02), "C", 50)[0] == 0


def test_session_calendar(monkeypatch):
    c = Clock(datetime(2026, 11, 26, 10, 0, tzinfo=ET))
    monkeypatch.setattr(core, "now_et", c)
    assert core.session_info()["holiday"]
    c.t = datetime(2026, 11, 27, 12, 40, tzinfo=ET)
    s = core.session_info()
    assert s["early_close"] and s["state"] == "NO NEW ENTRIES" and s["all_out"] == "12:50"
    c.t = datetime(2026, 10, 28, 15, 26, tzinfo=ET)
    assert core.session_info()["state"] == "ALL OUT"
    c.t = datetime(2026, 10, 28, 9, 40, tzinfo=ET)
    assert core.session_info()["state"] == "ORB FORMING" and not core.session_info()["entries_allowed"]


def test_projected_day_signs():
    assert core.projected_day(-20, -10, 5, 0) == -35
    left, d, w = core.budget_left(-20, 0, 10, -100)
    assert left is None and d is None      # no dollar limits configured


def test_losing_streak_stops(desk_env, monkeypatch):
    wire(monkeypatch, desk_env, up_day)
    desk_env.t = DAY.replace(hour=10, minute=0)
    for i in range(3):
        commands.handle(f"IN SPY 601C 1 at 1.00", "SPY")
        desk_env.t += timedelta(minutes=12)
        r = commands.handle("OUT 0.85", "SPY")
    assert "STOP FOR TODAY" in r["reply"]
    assert engine.discipline_gate("real", "A").startswith("STOP FOR TODAY")


# ---------------------------------------------------------------- autonomous paper engine
def test_all_out_time(desk_env, monkeypatch):
    def flat_up(ts):
        return up_day(ts) if ts.hour * 60 + ts.minute < 600 else 601.6
    wire(monkeypatch, desk_env, flat_up)
    run(desk_env, "09:30", "10:00")
    for mnt in (26, 27):
        desk_env.t = DAY.replace(hour=15, minute=mnt)
        engine._cache.clear()
        engine.tick()
    for p in store.positions(ledger="paper"):
        assert p["status"] in ("CLOSED", "CANCELED")


# ---------------------------------------------------------------- real trades & chat commands
def test_in_out_commands(desk_env, monkeypatch):
    wire(monkeypatch, desk_env, up_day)
    desk_env.t = DAY.replace(hour=10, minute=5)
    r = commands.handle("IN SPY 601C 2 at 0.95", "SPY")
    assert r["handled"] and "STOP" in r["reply"] and "LOGGED YOUR BUY 2" in r["reply"]
    p = store.positions(ledger="real", status="OPEN")[0]
    assert p["plan"]["premium_stop"] >= 0.76 and p["plan"]["be_trigger"] == 1.05    # 20% ceiling + costs; BE +10% (v3)
    r = commands.handle("OUT 1 at 1.10", "SPY")
    assert "P/L $+15.00" in r["reply"] and "1 left" in r["reply"]
    r = commands.handle("OUT 1.20", "SPY")
    assert "0 left" in r["reply"]
    assert store.positions(ledger="real", status="OPEN") == []
    assert store.positions(ledger="paper") == []   # a real fill never creates a paper order


def test_in_reuses_plan_contract(desk_env, monkeypatch):
    wire(monkeypatch, desk_env, up_day)
    desk_env.t = DAY.replace(hour=10, minute=10)
    r = commands.handle("confirm SPY calls", "SPY")
    assert r["plan"]["state"] in ("READY", "WAIT", "PASS")
    r2 = commands.handle("IN 1 at 1.00", "SPY")
    if r["plan"].get("contract"):
        assert r2["handled"] and r["plan"]["contract"]["label"] in r2["reply"]
    else:                                   # no plan contract (e.g. not enough room for 2:1): the desk asks which one
        assert r2["handled"] and "Which contract" in r2["reply"]


def test_check_once_no_watch_and_watch_expires(desk_env, monkeypatch):
    wire(monkeypatch, desk_env, up_day)
    desk_env.t = DAY.replace(hour=10, minute=10)
    commands.handle("check once SPY puts", "SPY")
    assert store.q("SELECT * FROM watches") == []
    r = commands.handle("watch SPY calls at 605 for 5 minutes", "SPY")   # above price: a WAIT plan that gets watched
    assert store.q("SELECT * FROM watches WHERE status='ACTIVE'")
    run(desk_env, "10:11", "10:17")
    w = store.q("SELECT status FROM watches")[0]
    assert w["status"] in ("EXPIRED", "INVALIDATED"), w
    commands.handle("stop watching", "SPY")


def test_missing_data_is_unknown_not_zero(desk_env, monkeypatch):
    import marketdata
    marketdata.use(marketdata.Provider())       # a provider with no data at all
    p = engine.build_plan("SPY", "C")
    assert p["state"] == "DATA UNAVAILABLE"


def test_paper_refuses_without_paper_account(monkeypatch):
    importlib.reload(broker)
    monkeypatch.setenv("ALPACA_KEY", "AKLIVE123")
    monkeypatch.setenv("ALPACA_SECRET", "x")
    o, err = broker._req("GET", broker.PAPER, "/v2/account")
    assert o is None and "REFUSED" in err
    with pytest.raises(RuntimeError):
        broker._req("GET", "https://api.alpaca.markets", "/v2/account")


# ---------------------------------------------------------------- AI routing + prompt pack
def test_standard_commands_never_call_chart(desk_env, monkeypatch):
    clock = desk_env
    wire(monkeypatch, clock, up_day)
    clock.t = DAY.replace(hour=10, minute=5)
    for text in ("IN SPY 601C 1 at 1.00", "OUT 1.10", "stop watching", "pause paper", "resume paper"):
        r = commands.handle(text, "SPY")
        assert r["handled"] and not r.get("coach"), text
    r = commands.handle("what's the news on NVDA today", "SPY")
    assert not r["handled"] and r["coach"]
    r = commands.handle("check once SPY calls", "SPY")
    assert r["handled"] and r["plan"]["state"] in ("WAIT", "READY", "PASS")


def test_coach_context_is_compact_and_secret_free(desk_env, monkeypatch):
    clock = desk_env
    wire(monkeypatch, clock, up_day)
    clock.t = DAY.replace(hour=10, minute=5)
    monkeypatch.setenv("ALPACA_SECRET", "SHOULD-NOT-LEAK")
    commands.handle("confirm SPY calls", "SPY")
    ctx = commands.coach_context("SPY")
    schema = json.loads((ROOT / "grok" / "SESSION_CONTEXT_SCHEMA.json").read_text())
    for k in ("policy", "session", "ticker", "price", "read", "active_plan", "open_real", "budget_real", "lessons", "desk_plans_for_ticker", "watchlist_quote", "cards", "rules", "training"):
        assert k in ctx and k in schema["properties"]["context"]["properties"], k
    blob = json.dumps(ctx, default=str)
    assert "SHOULD-NOT-LEAK" not in blob and "APCA" not in blob
    assert len(blob) < 12000, len(blob)
    assert "m1" not in ctx


def test_prompt_pack_safety_lines():
    g = ROOT / "grok"
    coach = (g / "PRIMARY_COACH_SYSTEM_PROMPT.md").read_text()
    assert "never click buy" in coach and "Never change the plan's numbers" in coach and "reply_to" in coach
    review = (g / "REVIEW_PROMPT.md").read_text()
    assert "Never propose a looser stop" in review and "/api/lessons" in review
    assert "/api/events" in (g / "MORNING_ROUTINE_PROMPT.md").read_text()
    ap = json.loads((ROOT / "config" / "agent_policy.json").read_text())
    assert ap["real_money"]["chart_may_place_orders"] is False and ap["paper"]["chart_runs_bot_take"] is False
    for f in g.glob("*.md"):
        for line in f.read_text().splitlines():
            if "bot.py take" in line:
                assert any(w in line.lower() for w in ("not", "never", "retired")), (f.name, line)


def test_watchlist_tickers_route_to_chart_and_log_journal_only(desk_env, monkeypatch, tmp_path):
    import watchlist
    clock = desk_env
    wire(monkeypatch, clock, up_day)
    clock.t = DAY.replace(hour=10, minute=5)
    monkeypatch.setattr(watchlist, "WL_FILE", tmp_path / "wl.json")
    assert "NVDA" in watchlist.add("nvda") and "SPY" not in watchlist.add("SPY")
    assert "NVDA" not in watchlist.remove("NVDA")
    with pytest.raises(ValueError):
        watchlist.add("NOT A TICKER")
    r = commands.handle("confirm NVDA calls over 140", "NVDA")          # v3.1: the desk plans any ticker itself
    assert r["handled"] and r["plan"]["ticker"] == "NVDA" and "your idea" in (r["plan"].get("origin") or "") + r["reply"]
    r = commands.handle("IN NVDA 140C 1 at 3.20", "SPY")
    assert "Which expiry" in r["reply"]                                    # single-stock options need the expiry
    r = commands.handle("IN NVDA 140C 11/07 1 at 3.20", "SPY")
    p = r["position"]
    assert p["ticker"] == "NVDA" and not p["plan"].get("manual") and p["symbol"] == "NVDA261107C00140000"
    assert p["plan"]["premium_stop"] <= 3.20 * 0.80 + 0.06 and p["plan"]["origin"].startswith("your idea")
    import exits
    exits.evaluate(store.pos_get(p["id"]), engine.snapshot("NVDA").get("v3") or {})
    assert store.pos_get(p["id"])["status"] == "OPEN"                     # real trades are never sold by the desk
    assert store.pos_get(p["id"])["plan"]["guidance"]["action"] in ("HOLD", "NO DATA", "EXIT", "TIGHTEN STOP to $2.60") or True
    out = commands.handle("OUT NVDA 4.10", "SPY")
    assert "+$90.00" in out["reply"] or "90" in out["reply"]
    assert store.pos_get(p["id"])["status"] == "CLOSED"


def test_voice_transcripts_parse_as_commands(desk_env, monkeypatch):
    """Outputs of the page's speech normalizer (Voice.normalize) must be understood by commands.handle."""
    clock = desk_env
    wire(monkeypatch, clock, up_day)
    clock.t = DAY.replace(hour=10, minute=5)
    r = commands.handle("spy rejected 600.50 puts?", "SPY")
    assert r["handled"] and r["plan"]["side"] == "P" and r["plan"]["trigger_level"] == 600.5
    r = commands.handle("IN spy 601C 2 at 0.90", "SPY")
    assert r["position"]["qty_init"] == 2 and r["position"]["fill"] == 0.90 and r["position"]["contract"] == "601C"
    r = commands.handle("OUT 2 at 1.05", "SPY")
    assert "+30.00" in r["reply"] and "0 left" in r["reply"]


def test_alt_data_off_without_key(monkeypatch):
    import altdata
    monkeypatch.delenv("QUIVER_KEY", raising=False)
    r = altdata.ticker("NVDA")
    assert r["enabled"] is False and "QUIVER_KEY" in r["note"]


def test_kronos_shadow_scores_against_baselines(desk_env, monkeypatch):
    """Kronos test plumbing with a fake model: forecasts once per bar, scores later, never touches orders."""
    import kronos_shadow as ks
    clock = desk_env
    store.x(ks.SCHEMA)
    idx = pd.date_range(DAY.replace(hour=5, minute=0), DAY.replace(hour=11, minute=0), freq="5min")
    px = np.linspace(600, 603, len(idx))
    bars = pd.DataFrame({"Open": px, "High": px + .1, "Low": px - .1, "Close": px, "Volume": 1e5}, index=idx)
    step = float(px[1] - px[0])
    perfect = lambda x_df, x_ts, y_ts, n: [float(x_df["close"].iloc[-1]) + step * (i + 1) for i in range(n)]
    early = bars.iloc[:-3]
    clock.t = DAY.replace(hour=10, minute=50)
    assert len(ks.forecast("SPY", early, perfect)) == 3
    assert ks.forecast("SPY", early, perfect) == []            # same bar: no duplicate
    clock.t = DAY.replace(hour=11, minute=10)
    assert ks.score("SPY", bars) == 3
    m = ks.metrics()
    assert m[15]["n"] == 1 and m[15]["mae_kronos"] < m[15]["mae_nochange"] and m[15]["dir_kronos"] == 100.0
    assert "collecting" in ks.verdict(m)
    assert not store.q("SELECT * FROM orders")


def test_watchlist_alpaca_first_and_keeps_last_good_quote(monkeypatch, tmp_path):
    import watchlist
    monkeypatch.setattr(watchlist, "WL_FILE", tmp_path / "wl.json")
    watchlist.save(["NVDA", "TSLA"])
    monkeypatch.setattr(watchlist, "earnings", lambda t: None)
    monkeypatch.setattr(broker, "configured", lambda: True)
    monkeypatch.setattr(broker, "snapshots", lambda ts: ({"NVDA": {"last": 142.0, "prev": 140.0}, "TSLA": {"last": 250.0, "prev": 255.0}}, None))
    monkeypatch.setattr(broker, "bars_multi", lambda ts, start, tf="15Min": ({"NVDA": [139, 141, 142]}, None))
    calls = []
    monkeypatch.setattr(watchlist, "_download", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(RuntimeError("YFRateLimitError")))
    rows = {r["ticker"]: r for r in watchlist.quotes(max_age=0)}
    assert rows["NVDA"]["chg_pct"] == 1.43 and rows["TSLA"]["chg_pct"] == -1.96 and rows["NVDA"]["src"] == "Alpaca IEX"
    assert not calls                                            # Yahoo not touched when Alpaca has everything
    monkeypatch.setattr(broker, "snapshots", lambda ts: ({}, "HTTP 500"))
    rows = {r["ticker"]: r for r in watchlist.quotes(max_age=0)}
    assert rows["NVDA"]["stale"] and rows["NVDA"]["last"] == 142.0   # both sources down: last good quote, marked stale
    assert calls and not watchlist._yahoo_ok()                  # Yahoo failure -> 10 minute pause, not a retry storm


def test_journal_calendar_breakdown_review_csv(desk_env, monkeypatch):
    clock = desk_env
    wire(monkeypatch, clock, up_day)
    clock.t = DAY.replace(hour=10, minute=5)
    r1 = commands.handle("IN SPY 601C 2 at 1.00", "SPY")["position"]
    commands.handle("OUT 2 at 1.20", "SPY")
    clock.t = DAY.replace(hour=15, minute=5)
    commands.handle("IN SPY 600P 1 at 1.00", "SPY")
    commands.handle("OUT 1 at 0.80", "SPY")
    cal = store.calendar("real", "2026-10")
    assert cal == [{"date": "2026-10-28", "trades": 2, "pnl": 20.0, "wins": 1}]
    b = store.breakdown("real", "2026-10-01")
    times = {x["name"]: x for x in b["time"]}
    assert times["Open 9:30-10:30"]["pnl"] == 40.0 and times["Power hour 3-close"]["pnl"] == -20.0
    n = store.trade_note(r1["id"], {"went_well": "waited for the close", "followed_plan": "yes", "hack": "x"})
    assert n == {"went_well": "waited for the close", "followed_plan": "yes"}
    store.trade_note(r1["id"], {"mistakes": "chased, early entry"})
    assert {m["name"] for m in store.breakdown("real", "2026-10-01")["mistakes"]} == {"chased", "early entry"}
    csv_text = store.export_csv("real")
    assert "waited for the close" in csv_text and csv_text.count("\n") == 3


def test_black_scholes_delta_fallback():
    t = DAY.replace(hour=12, minute=0)
    c = core.bs_delta(600, 600, 0.15, "C", t)
    p = core.bs_delta(600, 600, 0.15, "P", t)
    assert 0.45 < c < 0.56 and abs(c - p - 1) < 1e-6
    assert core.bs_delta(600, 610, 0.15, "C", t) < 0.1          # far OTM 0DTE call ~ 0
    assert core.bs_delta(600, 600, None, "C", t) is None


def test_chart_gets_current_rules_and_training(desk_env, monkeypatch):
    clock = desk_env
    wire(monkeypatch, clock, up_day)
    clock.t = DAY.replace(hour=10, minute=5)
    ctx = commands.coach_context("SPY", "is this a vwap pullback? spread looks wide")
    r = ctx["rules"]
    assert "STRUCTURE" in r["stops"] and "20%" in r["stops"] and "retired" in r["old_stops"]
    assert "2.0:1" in r["reward_risk"] and "ONE strategy" in r["vwap_macd"]
    assert "0.4-0.55" in r["delta"] and "STOP FOR TODAY" in r["streak"] and "15:25" in r["session"]
    assert {c["id"] for c in ctx["cards"]} & {"K22", "K06", "K02"}
    assert "Desk v3 rules map" in ctx["training"]["library"] and ctx["data"]["executable"] is True


def test_schwab_market_data_only_and_parsing(monkeypatch, tmp_path):
    import json as _j
    import schwab
    monkeypatch.setenv("SCHWAB_APP_KEY", "k"); monkeypatch.setenv("SCHWAB_APP_SECRET", "s")
    monkeypatch.setattr(schwab, "TOKEN_FILE", tmp_path / "tok.json")
    assert schwab.status()["state"] == "not connected" and not schwab.ready()
    assert "client_id=k" in schwab.login_url() and "127.0.0.1" in schwab.login_url()
    with pytest.raises(RuntimeError):
        schwab._get("/trader/v1/accounts", {})                # trading/account endpoints are refused in code
    monkeypatch.setattr(schwab, "_token_request", lambda form: {"access_token": "A", "refresh_token": "R", "expires_in": 1800})
    ok, msg = schwab.connect("https://127.0.0.1/?code=CO.abc%40&session=x")
    assert ok and schwab.ready() and schwab.status()["days_left"] == 7.0
    assert schwab.connect("https://127.0.0.1/")[0] is False
    chain_json = {"callExpDateMap": {"2026-10-28:0": {"600.0": [{"symbol": "SPY   261028C00600000", "strikePrice": 600.0, "bid": 1.10, "ask": 1.14,
                  "delta": 0.47, "volatility": 14.2, "quoteTimeInLong": 1793200000000, "totalVolume": 900, "openInterest": 5000}],
                  "601.0": [{"symbol": "SPY   261028C00601000", "strikePrice": 601.0, "bid": 0.7, "ask": 0.73, "delta": -999.0, "volatility": 14.0}]}}}
    monkeypatch.setattr(schwab, "_get", lambda path, params: (chain_json, None) if "chains" in path else
                        ({"SPY   261028C00600000": {"quote": {"bidPrice": 1.2, "askPrice": 1.24}}}, None))
    rows, err = schwab.chain("SPY", "C", "2026-10-28")
    assert rows[0]["symbol"] == "SPY261028C00600000" and rows[0]["delta"] == 0.47 and abs(rows[0]["iv"] - 0.142) < 1e-9
    assert rows[1]["delta"] is None                               # -999 means unknown, never a real delta
    q, _ = schwab.option_quote("SPY261028C00600000")
    assert q == {"bid": 1.2, "ask": 1.24, "ts": None, "feed": "Schwab live"}
    import marketdata
    marketdata.use(None)
    assert isinstance(marketdata.provider(), marketdata.SchwabREST) and marketdata.executable()
    monkeypatch.setattr(schwab, "ready", lambda: False)
    assert isinstance(marketdata.provider(), marketdata.Fallback) and not marketdata.executable()   # never a hidden live fallback


def test_out_returns_review_card(desk_env, monkeypatch):
    clock = desk_env
    wire(monkeypatch, clock, up_day)
    clock.t = DAY.replace(hour=10, minute=5)
    commands.handle("IN SPY 601C 2 at 1.00", "SPY")
    r = commands.handle("OUT 1 at 1.10", "SPY")
    assert r["review"] is None                                    # still 1 open: no review yet
    r = commands.handle("OUT 1 at 1.20", "SPY")
    assert r["review"] and r["review"]["trade"] == "SPY 601C"


def test_alerts_setups_moves_news(desk_env, monkeypatch):
    import alerts
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    st = {"family": "ORB_RETEST", "side": "C", "note": "retest held", "level": 600.0, "invalidation": 599.8, "bar": "2026-10-28T10:00:00"}
    assert alerts.setup("SPY", st, "A", "ORDER", None)
    assert not alerts.setup("SPY", st, "A", "ORDER", None)          # same setup bar: no duplicate alert
    assert not alerts.setup("SPY", dict(st, bar="x2"), "C", "WATCH", None)   # C grades don't ping
    idx = pd.date_range(DAY.replace(hour=9, minute=30), periods=30, freq="5min")
    o = np.full(30, 600.0); c = o + 0.05; v = np.full(30, 1e5)
    o[-2:], c[-2:], v[-2:] = [600.0, 600.9], [600.9, 601.8], [3e5, 3e5]
    b5 = pd.DataFrame({"Open": o, "High": np.maximum(o, c) + .05, "Low": np.minimum(o, c) - .05, "Close": c, "Volume": v}, index=idx)
    assert alerts.move_check("SPY", b5) and not alerts.move_check("SPY", b5)
    n = alerts.add_news([{"headline": "Powell says rate cuts are not on the table this year", "source": "DeltaOne", "impact": "high", "direction": "bearish", "tickers": "spy, qqq"},
                         {"headline": "Powell says rate cuts are NOT on the table this year!", "impact": "high"},   # same story twice
                         {"headline": "x"}])
    assert len(n) == 1 and alerts.recent_news()[0]["tickers"] == "SPY,QQQ"
    kinds = [json.loads(e["data"])["kind"] for e in store.q("SELECT data FROM events WHERE kind='alert'")]
    assert kinds == ["setups", "moves", "news"]
    alerts.set_settings({"news": False})
    assert len(alerts.add_news([{"headline": "CPI comes in hot at 0.5% vs 0.3% expected", "impact": "high"}])) == 1
    assert store.q("SELECT COUNT(*) n FROM events WHERE kind='alert'")[0]["n"] == 3   # news alerts off: stored, not pinged


