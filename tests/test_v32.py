"""v3.2 tests: Schwab connection lifecycle, the live chart feed, symbol search, the setups scanner and plan states.
Everything runs offline: a fake Schwab HTTP server (schwab._urlopen) and a fake streaming websocket."""
import asyncio
import io
import json
import threading
import time
import urllib.error

import pytest

import schwab
import schwab_stream

TOKEN = "ACCESS-TOKEN-SECRET-123"


class FakeSchwab:
    """Answers the few Schwab calls the desk makes. Flip .quotes / .prefs / .refresh to an HTTP code to fail them."""

    def __init__(self):
        self.calls, self.quotes, self.prefs, self.refresh, self.token_requests = [], 200, 200, 200, 0

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.calls.append(url)
        if "/oauth/token" in url:
            self.token_requests += 1
            body = req.data.decode()
            if "refresh_token" in body and "grant_type=refresh_token" in body and self.refresh != 200:
                raise urllib.error.HTTPError(url, self.refresh, "bad", {}, io.BytesIO(b'{"error":"invalid_grant"}'))
            return _Resp({"access_token": TOKEN, "refresh_token": "REFRESH-SECRET", "expires_in": 1800})
        if "/trader/v1/userPreference" in url:
            if self.prefs != 200:
                raise urllib.error.HTTPError(url, self.prefs, "no", {}, io.BytesIO(b"{}"))
            return _Resp({"streamerInfo": [{"streamerSocketUrl": "wss://fake", "schwabClientCustomerId": "c",
                                            "schwabClientCorrelId": "x", "schwabClientChannel": "N", "schwabClientFunctionId": "A"}]})
        if "/marketdata/" in url:
            if self.quotes == "down":
                raise urllib.error.URLError("network down")
            if self.quotes != 200:
                raise urllib.error.HTTPError(url, self.quotes, "no", {}, io.BytesIO(b"{}"))
            return _Resp({"SPY": {"quote": {"lastPrice": 600.0}}})
        raise AssertionError("unexpected call " + url)


class _Resp:
    def __init__(self, j):
        self.b = json.dumps(j).encode()

    def read(self):
        return self.b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSockets:
    """Counts open streaming sockets, so a test can prove there is never more than one."""

    def __init__(self):
        self.open, self.max_open, self.opened, self.sent, self.login_code = 0, 0, 0, [], 0
        self.lock = threading.Lock()

    def __call__(self, url):
        return _WS(self)


class _WS:
    def __init__(self, f):
        self.f, self.n = f, 0

    async def __aenter__(self):
        with self.f.lock:
            self.f.open += 1
            self.f.opened += 1
            self.f.max_open = max(self.f.max_open, self.f.open)
        return self

    async def __aexit__(self, *a):
        with self.f.lock:
            self.f.open -= 1
        return False

    async def send(self, s):
        self.f.sent.append(json.loads(s))

    async def recv(self):
        self.n += 1
        if self.n == 1:
            return json.dumps({"response": [{"content": {"code": self.f.login_code}}]})
        await asyncio.sleep(0.2)
        return json.dumps({"notify": [{"heartbeat": str(int(time.time() * 1000))}]})


def _wait(pred, s=6.0):
    end = time.time() + s
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


@pytest.fixture
def live(monkeypatch):
    """Keys set, fake Schwab HTTP + fake stream, REST backfill skipped."""
    monkeypatch.setenv("SCHWAB_APP_KEY", "k")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "s")
    fake, socks = FakeSchwab(), FakeSockets()
    monkeypatch.setattr(schwab, "_urlopen", fake)
    monkeypatch.setattr(schwab_stream, "available", lambda: True)
    monkeypatch.setattr(schwab_stream, "_ws_connect", socks)
    monkeypatch.setattr(schwab_stream, "_backfill", lambda t: None)
    import marketdata
    marketdata.use(None)
    return fake, socks


def test_connect_disconnect_reconnect_repeatedly_one_stream(live):
    fake, socks = live
    assert schwab.status()["state"] == "disconnected"
    for i in range(3):
        schwab.login_url()
        assert schwab.status()["state"] == "connecting"
        ok, msg = schwab.connect(f"https://127.0.0.1/?code=CODE{i}%40&session=s")
        assert ok, msg
        st = schwab.status(verify=False)
        assert st["state"] == "connected" and st["verified_s_ago"] is not None
        assert _wait(lambda: schwab_stream.state()["phase"] == "live"), schwab_stream.state()
        assert socks.open == 1
        out = schwab.disconnect()
        assert "doesn't revoke" in out or "isn't told" in out
        assert not schwab.TOKEN_FILE.exists() and schwab.status()["state"] == "disconnected"
        assert schwab_stream.state()["phase"] == "off"
        assert _wait(lambda: socks.open == 0, 3), "the old socket must close on Disconnect"
    assert socks.max_open == 1 and socks.opened == 3
    logouts = [r for m in socks.sent for r in m["requests"] if r["command"] == "LOGOUT"]
    assert len(logouts) == 3


def test_reconnect_and_restart_never_duplicate_the_stream(live):
    fake, socks = live
    assert schwab.connect("https://127.0.0.1/?code=A")[0]
    assert _wait(lambda: schwab_stream.state()["phase"] == "live"), (schwab_stream.state(), schwab.status(verify=False), socks.opened)
    g0 = schwab_stream.state()["generation"]
    for i in range(4):
        schwab_stream.restart("test")
    assert schwab.connect("https://127.0.0.1/?code=B")[0]          # a fresh login while streaming = reconnect
    assert _wait(lambda: schwab_stream.state()["phase"] == "live" and socks.open == 1), (schwab_stream.state(), socks.open, socks.opened)
    assert socks.max_open == 1
    assert schwab_stream.state()["generation"] > g0
    subs = [r for m in socks.sent for r in m["requests"] if r["command"] == "SUBS" and r["service"] == "CHART_EQUITY"]
    assert all("SPY" in r["parameters"]["keys"] for r in subs)


def test_login_code_is_single_use(live):
    fake, _ = live
    url = "https://127.0.0.1/?code=SAME%40&session=s"
    assert schwab.connect(url)[0]
    n = fake.token_requests
    ok, msg = schwab.connect(url)
    assert fake.token_requests == n and "already used" in msg and ok      # harmless, and says the desk is connected
    assert schwab.connect("https://127.0.0.1/")[0] is False


def test_connected_needs_a_working_data_call(live):
    fake, _ = live
    schwab._save({"access_token": TOKEN, "refresh_token": "R", "expires_at": time.time() + 900, "refresh_issued": time.time()})
    st = schwab.status(verify=False)
    assert st["state"] == "connecting"                                  # a saved token alone is never "connected"
    fake.quotes = 401
    schwab._get("/marketdata/v1/quotes", {"symbols": "SPY"})
    st = schwab.status(verify=False)
    assert st["state"] == "error" and "Reconnect" in st["action"]
    fake.quotes = "down"
    schwab._get("/marketdata/v1/quotes", {"symbols": "SPY"})
    assert schwab.status(verify=False)["state"] == "reconnecting"
    fake.quotes = 200
    schwab._get("/marketdata/v1/quotes", {"symbols": "SPY"})
    assert schwab.status(verify=False)["state"] == "connected"


def test_expired_login_is_recoverable_without_restart(live):
    fake, socks = live
    old = time.time() - 8 * 86400
    schwab._save({"access_token": "OLD", "refresh_token": "R", "expires_at": 0, "refresh_issued": old})
    st = schwab.status(verify=False)
    assert st["state"] == "expired" and "log in again" in st["action"]
    # refresh rejected by Schwab (revoked / invalid_grant) -> expired, not an endless retry
    schwab._save({"access_token": "OLD", "refresh_token": "R", "expires_at": 0, "refresh_issued": time.time()})
    fake.refresh = 400
    assert schwab._get("/marketdata/v1/quotes", {"symbols": "SPY"}) == (None, "Schwab not connected")
    st = schwab.status(verify=False)
    assert st["state"] == "expired" and "rejected" in st["why"]
    n = fake.token_requests
    schwab._get("/marketdata/v1/quotes", {"symbols": "SPY"})
    assert fake.token_requests == n                                     # no hammering after a rejection
    assert not schwab.ready()
    fake.refresh = 200
    ok, msg = schwab.connect("https://127.0.0.1/?code=NEW")              # a new login fixes it in place
    assert ok and schwab.status(verify=False)["state"] == "connected" and schwab.ready()
    assert _wait(lambda: schwab_stream.state()["phase"] == "live")


def test_stream_refused_stops_retrying_and_says_what_to_do(live, monkeypatch):
    fake, socks = live
    monkeypatch.setattr(schwab_stream, "_sleep", lambda s, g: None)
    fake.prefs = 401
    assert schwab.connect("https://127.0.0.1/?code=X")[0]               # market data works ...
    assert _wait(lambda: schwab_stream.state()["phase"] == "stopped")   # ... the stream gives up after 3 refusals
    st = schwab_stream.state()
    assert st["auth_failures"] == schwab_stream.MAX_AUTH_FAILURES and "Reconnect" in st["detail"]
    assert socks.opened == 0
    fake.prefs = 200
    schwab_stream.restart("fixed")
    assert _wait(lambda: schwab_stream.state()["phase"] == "live")


def test_tokens_never_reach_the_page_or_logs(live, capsys):
    import server
    assert schwab.connect("https://127.0.0.1/?code=T")[0]
    view = json.dumps(server.schwab_view())
    assert TOKEN not in view and "REFRESH-SECRET" not in view and "k" != ""
    assert TOKEN not in capsys.readouterr().out
    assert _wait(lambda: schwab_stream.state()["phase"] == "live")
    assert TOKEN not in json.dumps(schwab_stream.state())


# ================================================================ setups board (pure rules)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import core  # noqa: E402
import scanner_setups as SS  # noqa: E402

DAY = pd.Timestamp("2026-10-30").date()


def _bars(path, start="09:30", vol=10_000, pre=None):
    """1m bars whose closes follow `path` (list of prices) from `start`; optional pre-market closes from 08:00."""
    rows, idx = [], []
    def put(t0, closes):
        t = pd.Timestamp(f"2026-10-30 {t0}", tz=core.ET)
        prev = closes[0]
        for c in closes:
            o = prev
            rows.append({"Open": o, "High": max(o, c) + 0.02, "Low": min(o, c) - 0.02, "Close": c, "Volume": float(vol)})
            idx.append(t)
            t += pd.Timedelta(minutes=1)
            prev = c
    if pre:
        put("08:00", pre)
    put(start, path)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


BASE = {"atr14": 2.0, "avg_vol14": 5_000_000, "prev_close": 100.0, "pdh": 103.0, "pdl": 98.0, "tod_cum": None, "tod_n": 0}


def _at(hm):
    return pd.Timestamp(f"2026-10-30 {hm}", tz=core.ET)


def _states(setups, prefix):
    return {s["state"] for s in setups if s["setup"].startswith(prefix)}


def test_orb_uses_the_regular_open_and_only_complete_ranges():
    m1 = _bars([100 + 0.01 * i for i in range(20)], pre=[105.0] * 30)        # pre-market high 105 must not leak in
    r1 = SS.rth_today(m1, DAY)
    o = SS.orb(r1, 15, _at("09:44"))
    assert o["complete"] is False                                          # 09:30 + 15 = 09:45: not done yet
    o = SS.orb(r1, 15, _at("09:45"))
    assert o["complete"] and o["high"] < 101 and o["bars"] == 15
    assert SS.orb(r1, 30, _at("09:50"))["complete"] is False
    info, setups = SS.evaluate("ABC", m1, BASE, {"last": 100.1, "prev": 100.0}, None, _at("09:44"))
    assert not [s for s in setups if s["setup"].startswith("ORB15")]       # no ORB15 setup before the range is complete


def test_orb_states_approach_break_close_retest_fail():
    c = SS.cfg()
    rng = [100.0, 100.5, 100.2, 100.8, 100.4]                               # ORB5 high = 100.8 + 0.02
    m1 = _bars(rng + [100.6, 100.7])
    now = _at("09:37")
    hi = SS.orb(SS.rth_today(m1, DAY), 5, now)["high"]
    _, st = SS.evaluate("ABC", m1, BASE, {"last": hi - 0.1, "prev": 100}, None, now, c)
    assert "APPROACHING" in _states(st, "ORB5 breakout")
    _, st = SS.evaluate("ABC", m1, BASE, {"last": hi + 0.05, "prev": 100}, None, now, c)
    assert "BREAKING" in _states(st, "ORB5 breakout")
    m1b = _bars(rng + [100.6, 101.3, 101.6, 101.9])
    _, st = SS.evaluate("ABC", m1b, BASE, {"last": 101.9, "prev": 100}, None, _at("09:39"), c)
    row = [s for s in st if s["setup"] == "ORB5 breakout"][0]
    assert row["state"] == "CLOSED BEYOND" and "09:36" in row["why"] and row["invalidation"] == round(hi, 2)
    assert {"name": "ORB5 high", "value": round(hi, 2)} in row["chart_levels"]
    m1c = _bars(rng + [100.6, 101.3, 100.85, 101.4])                        # came back to the edge, still above
    _, st = SS.evaluate("ABC", m1c, BASE, {"last": 101.4, "prev": 100}, None, _at("09:39"), c)
    assert "RETEST HOLDING" in _states(st, "ORB5 breakout")
    m1d = _bars(rng + [100.6, 101.3, 100.5])
    _, st = SS.evaluate("ABC", m1d, BASE, {"last": 100.5, "prev": 100}, None, _at("09:38"), c)
    f = [s for s in st if s["state"] == "FAILED" and s["setup"].startswith("ORB5")][0]
    assert f["direction"] == "short" and "back inside" in f["why"]


def test_extended_breakout_is_flagged_and_not_qualifying():
    m1 = _bars([100.0, 100.5, 100.2, 100.8, 100.4, 100.6, 101.3, 102.0, 102.6])
    info, st = SS.evaluate("ABC", m1, BASE, {"last": 102.6, "prev": 100, "bid": 102.59, "ask": 102.61}, None, _at("09:39"))
    row = [s for s in st if s["setup"] == "ORB5 breakout"][0]
    assert row["extended"] and "ATR past" in row["extended_why"]
    rows = SS.rows_for(info, st, {"ok": True})
    r = [x for x in rows if x["setup"] == "ORB5 breakout"][0]
    assert not r["qualifies"] and r["score_parts"]["extended"] == -2 and "extended" in r["flags"]


def test_time_of_day_rvol_and_the_labeled_approximation():
    m1 = _bars([100.0] * 30, vol=20_000)                                    # 09:30-09:59, 600k by 09:59
    r1 = SS.rth_today(m1, DAY)
    prof = {f"09:{m:02d}": 50_000.0 * (i + 1) for i, m in enumerate(range(30, 60, 5))}   # 09:55 slot -> 300k
    rv, how = SS.tod_rvol(r1, {"tod_cum": prof, "tod_n": 10}, _at("10:00"))
    assert rv == 2.0 and "time of day" in how and "10 sessions" in how
    rv2, how2 = SS.tod_rvol(r1, {"avg_vol14": 7_800_000}, _at("10:00"))
    assert "APPROXIMATE" in how2 and rv2 == round(600_000 / (7_800_000 * 6 / 78), 2)
    assert SS.tod_rvol(r1, {"tod_cum": prof}, _at("09:33"))[0] is None   # nothing before the first 5 minutes


def test_vwap_reclaim_and_premarket_and_previous_day_breaks():
    path = [100.0] * 5 + [99.0 - 0.05 * i for i in range(15)] + [99.5, 100.4, 100.6, 100.8]
    m1 = _bars(path, pre=[101.0, 101.4, 101.2] * 6)
    info, st = SS.evaluate("ABC", m1, BASE, {"last": 100.8, "prev": 100}, None, _at("09:54"))
    assert "RECLAIMED" in _states(st, "VWAP reclaim")
    m2 = _bars([101.0, 101.2, 101.3, 101.6, 101.9, 102.2, 102.5, 102.7], pre=[100.0, 101.4] * 10)
    _, st2 = SS.evaluate("ABC", m2, BASE, {"last": 102.7, "prev": 100}, None, _at("09:38"))
    pm = [s for s in st2 if s["setup"] == "PM high break"][0]
    assert pm["state"] == "CLOSED BEYOND" and pm["level"] == 101.42
    m3 = _bars([102.5, 102.8, 103.3, 103.4, 103.5])
    _, st3 = SS.evaluate("ABC", m3, BASE, {"last": 103.5, "prev": 100}, None, _at("09:35"))
    assert "CLOSED BEYOND" in _states(st3, "PD high break")


def test_flags_ranking_and_no_qualifying_setups():
    m1 = _bars([20.0 + 0.01 * i for i in range(40)], vol=500)
    thin = dict(BASE, avg_vol14=200_000, atr14=0.5, prev_close=19.0, pdh=30, pdl=10)
    info, st = SS.evaluate("THIN", m1, thin, {"last": 20.4, "prev": 19.0, "bid": 20.3, "ask": 20.5}, None, _at("10:10"))
    assert "illiquid" in info["flags"] and "wide spread" in info["flags"]
    rows = SS.rows_for(info, st, {"ok": True})
    assert rows and not any(r["qualifies"] for r in rows)
    assert all(r["score_parts"]["liquidity"] <= -2 for r in rows)
    stale = SS.rows_for(info, st, {"ok": False})
    assert all(r["score"] is None and "stale" in r["flags"] for r in stale)
    with SS._lock:
        SS._state["rows"] = {"THIN": {"info": info, "rows": rows, "at": "x"}}
    b = SS.board()
    assert b["qualifying"] == 0 and "No qualifying setups" in b["summary"] and "not the whole market" in " ".join(b["coverage"]["limits"]).lower()
    assert "not a probability" in b["definitions"]["score"]
    SS._state["rows"] = {}


def test_relative_strength_vs_spy():
    m1 = _bars([100.0 + 0.1 * i for i in range(30)])                          # +2.9% since the open
    spy = _bars([600.0] * 30)
    info, st = SS.evaluate("ABC", m1, BASE, {"last": 102.9, "prev": 100}, spy, _at("10:00"))
    rs = [s for s in st if s["kind"] == "rs"][0]
    assert rs["direction"] == "long" and "not beta" not in rs["why"] and info["rs_pts"] > 2


# ================================================================ live chart feed
from datetime import datetime as _dt  # noqa: E402

import fakes  # noqa: E402
import marketdata  # noqa: E402
import store  # noqa: E402

CDAY = _dt(2026, 10, 28, tzinfo=core.ET)


def _trend(m):
    return 600.0 + 0.01 * ((m.hour * 60 + m.minute) - 570)


@pytest.fixture
def chart_env(tmp_path, monkeypatch):
    import engine
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    engine._cache.clear()
    clock, fk = fakes.install(monkeypatch, _trend, CDAY, s0=600.0)
    yield clock, fk
    marketdata.use(None)


def _go(clock, hh, mm, ss=0):
    import engine
    clock.t = CDAY.replace(hour=hh, minute=mm, second=ss)
    engine._cache.clear()


def test_chart_timeframes_align_without_duplicates(chart_env):
    import chartfeed
    clock, fk = chart_env
    _go(clock, 11, 7, 30)
    one = chartfeed.build("SPY", 1)
    for tf in (1, 2, 5, 15):
        d = chartfeed.build("SPY", tf)
        ts = [c["time"] for c in d["candles"]]
        assert ts == sorted(set(ts)), "candle times must be unique and increasing"
        assert all(t % (tf * 60) == 0 for t in ts), f"{tf}m candles must sit on the 09:30 grid"
        assert all(not c["final"] for c in d["candles"][-1:]) or tf == 1
        assert {v["time"] for v in d["vwap"]} <= set(ts) and {v["time"] for v in d["ema9"]} <= set(ts)
        # volume of a finished 15m candle = the sum of its 1m bars
        if tf == 15:
            c = [x for x in d["candles"] if x["final"]][-1]
            v15 = [v["value"] for v in d["volume"] if v["time"] == c["time"]][0]
            v1 = sum(v["value"] for v in one["volume"] if c["time"] <= v["time"] < c["time"] + 900)
            assert v15 == pytest.approx(v1)
    days = {_dt.fromtimestamp(c["time"], core.ET).date() for c in one["candles"]}
    assert len(days) == 2                                                    # the prior session is there to pan back to


def test_new_candle_appears_when_the_next_minute_ends(chart_env):
    import chartfeed
    clock, fk = chart_env
    _go(clock, 10, 30, 10)
    a = chartfeed.build("SPY", 1)
    _go(clock, 10, 31, 10)
    b = chartfeed.build("SPY", 1)
    fa = [c for c in a["candles"] if c["final"]][-1]["time"]
    fb = [c for c in b["candles"] if c["final"]][-1]["time"]
    assert fb - fa == 60
    tail = chartfeed.build("SPY", 1, since=fa)
    assert tail["candles"][0]["time"] == fa and len(tail["candles"]) <= 3 and tail["tail"] == fa
    assert b["status"]["state"] in ("live", "polling") and b["status"]["last_update"]


def test_extended_hours_toggle_and_vwap_stays_regular_session(chart_env):
    import chartfeed
    clock, fk = chart_env
    _go(clock, 10, 0, 5)
    rth = chartfeed.build("SPY", 5)
    ext = chartfeed.build("SPY", 5, ext=1)
    open_t = int(CDAY.replace(hour=9, minute=30).timestamp())
    assert all(c["time"] >= open_t or _dt.fromtimestamp(c["time"], core.ET).date() < CDAY.date() for c in rth["candles"])
    pre = [c for c in ext["candles"] if c.get("ext") and c["time"] < open_t and c["time"] > open_t - 6 * 3600]
    assert pre and min(v["time"] for v in ext["vwap"] if v["time"] > open_t - 6 * 3600) >= open_t


def test_provisional_candle_from_streamed_trades_has_no_volume(chart_env):
    import chartfeed
    clock, fk = chart_env
    _go(clock, 10, 30, 40)
    marketdata.merge_quote("SPY", {"last": 601.5, "trade_time": CDAY.replace(hour=10, minute=30, second=20)}, "Schwab stream")
    marketdata.merge_quote("SPY", {"last": 601.9, "trade_time": CDAY.replace(hour=10, minute=30, second=35)}, "Schwab stream")
    fk_bars = fk.bars_1m
    d = chartfeed.build("SPY", 1)
    # the fake REST provider already delivers a forming bar? if so the provisional one is not used
    last = d["candles"][-1]
    assert last.get("provisional") and not last["final"] and last["time"] == int(CDAY.replace(hour=10, minute=30).timestamp())
    assert last["open"] == 601.5 and last["high"] == 601.9 and last["close"] == 601.9
    assert last["time"] not in {v["time"] for v in d["volume"]}            # no invented volume
    assert any("provisional" in n for n in d["notes"])
    _go(clock, 10, 31, 10)                                                 # the real 10:30 bar arrives and replaces it
    d2 = chartfeed.build("SPY", 1)
    c = [x for x in d2["candles"] if x["time"] == last["time"]][0]
    assert not c.get("provisional") and c["final"] and last["time"] in {v["time"] for v in d2["volume"]}
    assert fk_bars


def test_stale_closed_and_unknown_symbol_states(chart_env, monkeypatch):
    import chartfeed
    clock, fk = chart_env
    _go(clock, 10, 30, 5)
    full = fk.m1
    monkeypatch.setattr(fk, "bars_1m", lambda t: full[full.index <= CDAY.replace(hour=10, minute=22)])
    import engine
    engine._cache.clear()
    marketdata.use(fk)
    d = chartfeed.build("SPY", 1)
    assert d["status"]["state"] == "stale" and "connection is up" in d["status"]["why"]
    monkeypatch.setattr(fk, "bars_1m", lambda t: full[full.index <= clock.t - pd.Timedelta(minutes=1)])
    _go(clock, 17, 0, 5)
    marketdata.use(fk)
    d = chartfeed.build("SPY", 1)
    assert d["status"]["state"] == "closed" and "after hours" in d["status"]["why"]
    monkeypatch.setattr(fk, "bars_1m", lambda t: None if t == "ZZZZ" else full)
    monkeypatch.setattr(fk, "quote", lambda t: None)
    d = chartfeed.build("ZZZZ", 1)
    assert not d["candles"] and "no data for ZZZZ" in d["error"] and d["status"]["state"] == "unavailable"


def test_chart_orb_levels_respect_session_time(chart_env):
    import chartfeed
    clock, fk = chart_env
    _go(clock, 9, 50, 5)
    d = chartfeed.build("SPY", 1)
    lv = {l["name"]: l for l in d["levels"]}
    assert lv["ORB5_H"]["complete"] and lv["ORB15_H"]["complete"] and lv["ORB30_H"]["complete"] is False
    r = fk.m1[(fk.m1.index >= CDAY.replace(hour=9, minute=30)) & (fk.m1.index < CDAY.replace(hour=9, minute=45))]
    assert lv["ORB15_H"]["value"] == round(float(r["High"].max()), 2)


def test_any_ticker_plan_and_chart_beyond_spy_qqq(chart_env):
    import chartfeed
    import commands
    clock, fk = chart_env
    _go(clock, 10, 40, 5)
    d = chartfeed.build("NVDA", 2)
    assert d["ticker"] == "NVDA" and d["candles"]


# ================================================================ setups board end to end + row -> chart levels
def test_board_scans_the_universe_and_rows_link_to_chart_levels(tmp_path, monkeypatch):
    import engine
    import scanner
    import test_v31 as V
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    engine._cache.clear()
    try:
        clock, f, prov = V._scanner_world(monkeypatch)
        uni = ["NVDA", "AMD", "AAPL", "CHEAP", "TSLA"]
        monkeypatch.setattr(SS, "tickers", lambda: uni)
        f.m1_ext = lambda t, day, now: f.m1_today(t, day)
        scanner.prepare(clock().date())
        SS._state.update(day=None, rows={}, bars={}, quotes={}, quotes_at=None, last_step=None, budget=0.0)
        clock.t = V.DAY.replace(hour=10, minute=10, second=5)
        SS._state["last_step"] = time.time() - 600                       # a full minute of call budget
        SS.step(clock())
        b = SS.board(best_per_stock=False)
        assert b["coverage"]["universe"] == 5 and "Not the whole market" in b["coverage"]["limits"][0]
        nv = [r for r in b["rows"] if r["ticker"] == "NVDA" and r["setup"].startswith("ORB5 breakout")]
        assert nv and nv[0]["state"] in ("CLOSED BEYOND", "RETEST HOLDING") and nv[0]["fresh"]["ok"]
        m1 = f.m1_today("NVDA", clock().date())
        hi = round(float(m1.iloc[:5]["High"].max()), 2)
        assert {"name": "ORB5 high", "value": hi} in nv[0]["chart_levels"] and nv[0]["invalidation"] == hi
        for r in b["rows"]:                                              # the score is exactly its listed parts
            if r["score"] is not None:
                assert r["score"] == pytest.approx(sum(r["score_parts"].values()))
        assert [r["score"] for r in b["rows"]] == sorted([r["score"] for r in b["rows"]], reverse=True)
        # the same ORB level is what the chart draws for NVDA
        marketdata.use(V.StockProv(clock))
        monkeypatch.setattr(marketdata.provider(), "bars_1m", lambda t: f.m1s[t][f.m1s[t].index + pd.Timedelta(minutes=1) <= clock()])
        import chartfeed
        engine._cache.clear()
        d = chartfeed.build("NVDA", 1)
        assert {l["name"]: l["value"] for l in d["levels"]}["ORB5_H"] == hi
        f.ok = False
        SS.step(clock())
        assert SS._state["status"].startswith("waiting for Schwab")
    finally:
        scanner.use(None)
        marketdata.use(None)
        SS._state.update(day=None, rows={}, bars={}, quotes={}, quotes_at=None, last_step=None, budget=0.0)


# ================================================================ assistant states, risk, any-ticker positions
def test_plan_states_observations_and_planned_risk(chart_env):
    import commands
    import engine
    clock, fk = chart_env
    _go(clock, 10, 40, 5)
    for side in ("C", "P"):
        p = engine.build_plan("SPY", side)
        a = p["assistant"]
        assert a["state"] in engine.ASSIST_STATES and a["at"] and a["why"]
        assert any(o.startswith("last finished 1m close") for o in a["observations"])
        assert all(not o.startswith(("for:", "against:")) for o in a["observations"])          # facts and readings kept apart
        if p.get("contract"):
            rk = a["risk"]
            assert rk["per_contract_usd"] == pytest.approx(round((p["premium_limit"] - p["exit"]["stop"]) * 100, 2))
            assert rk["total_usd"] == pytest.approx(rk["per_contract_usd"] * rk["qty"]) and "planned threshold" in rk["note"]
            assert rk["underlying_invalidation"].startswith("SPY 1m close")
            txt = commands.plan_text(p)
            assert "DESK READ" in txt and "PLANNED MAX LOSS" in txt and "planned threshold" in txt
        if a["state"] == "ENTRY CONDITIONS MET":
            assert len(a["conditions_met"]) >= 4
        if a["state"] == "SETUP FORMING":
            assert a["missing"]
    p = engine.build_plan("SPY", "C")
    c1 = engine.snapshot("SPY")["v3"]["close1"]
    bad = dict(p, state="READY", invalidation=round(c1 + 1, 2))
    bad.pop("gate", None)
    a = engine.assess(bad)
    assert a["state"] == "INVALIDATED" and "below the invalidation" in a["why"]
    pre = dict(p, state="WAIT", invalidation=round(c1 + 1, 2))                 # not triggered yet: not "invalidated"
    pre.pop("gate", None)
    assert engine.assess(pre)["state"] != "INVALIDATED"


def test_your_trade_on_any_ticker_tracks_the_exact_contract_and_planned_exposure(chart_env):
    import commands
    import engine
    import exits
    clock, fk = chart_env
    _go(clock, 10, 20, 5)
    r = commands.handle("IN NVDA 600C 11/06 2 at 2.04", "NVDA")
    p = r["position"]
    assert p["ticker"] == "NVDA" and p["symbol"] == "NVDA261106C00600000" and p["ledger"] == "real"
    exits.evaluate(store.pos_get(p["id"]), engine.snapshot("NVDA")["v3"])
    g = store.pos_get(p["id"])["plan"]["guidance"]
    ct, ex = g["plan"]["contract"], g["plan"]["exposure"]
    assert ct == {"symbol": "NVDA261106C00600000", "ticker": "NVDA", "label": p["contract"], "expiry": "2026-11-06", "strike": 600.0,
                  "type": "call", "entry": 2.04, "qty": 2}
    pl = store.pos_get(p["id"])["plan"]
    assert pl["premium_stop"] >= round(2.04 * 0.8, 2) - 0.01                                # never past the 20% planned max
    assert ex["per_contract_usd"] == pytest.approx(round((2.04 - pl["premium_stop"]) * 100, 2)) and ex["total_usd"] == pytest.approx(ex["per_contract_usd"] * 2)
    assert "planned" in ex["note"] and ex["underlying_invalidation"] is None or ex["underlying_invalidation"].startswith("NVDA")
    assert g["plan"]["monitoring"].startswith("live quote for this exact contract")
    assert g["state"] in ("HOLDING", "EXIT CONDITION MET", "INVALIDATED")
    fk.broken = True                                                                         # no quote for the contract
    _go(clock, 10, 21, 5)
    exits.evaluate(store.pos_get(p["id"]), engine.snapshot("NVDA")["v3"])
    g2 = store.pos_get(p["id"])["plan"]["guidance"]
    assert g2["action"] == "NO DATA" and g2["plan"]["monitoring"].startswith("NOT monitoring")
    assert store.pos_get(p["id"])["status"] == "OPEN"                                        # the desk never sells for you


def test_failed_breakout_is_a_watch_until_the_reversal_is_confirmed():
    rng = [100.0, 100.5, 100.2, 100.8, 100.4]                               # ORB5 100.0-100.8 (+/- wicks), mid ~100.4
    m1 = _bars(rng + [100.6, 101.3, 100.6])                                 # broke out, back inside, above the midpoint
    info, st = SS.evaluate("ABC", m1, BASE, {"last": 100.6, "prev": 100}, None, _at("09:38"))
    f = [s for s in st if s["setup"] == "ORB5 failed breakout"][0]
    rows = SS.rows_for(info, st, {"ok": True})
    assert f["state"] == "FAILED" and "midpoint" in f["missing"]
    assert not [r for r in rows if r["setup"] == "ORB5 failed breakout"][0]["qualifies"]   # a failed break alone: wait
    m2 = _bars(rng + [100.6, 101.3, 100.6, 100.1])                          # then a close through the midpoint, under VWAP
    info2, st2 = SS.evaluate("ABC", m2, BASE, {"last": 100.1, "prev": 100}, None, _at("09:39"))
    f2 = [s for s in st2 if s["setup"] == "ORB5 failed breakout"][0]
    assert f2["state"] == "REVERSAL CONFIRMED" and f2["direction"] == "short"
    assert any(l["name"] == "ORB5 mid" for l in f2["chart_levels"])


def test_switching_chart_tickers_unsubscribes_the_old_one(live):
    fake, socks = live
    assert schwab.connect("https://127.0.0.1/?code=SUB")[0]
    assert _wait(lambda: schwab_stream.state()["phase"] == "live")
    schwab_stream.want_equities(["TSLA"])                        # an open trade: base subscription
    schwab_stream.focus_equity("NVDA")
    assert _wait(lambda: "NVDA" in schwab_stream.state()["equities"] and "TSLA" in schwab_stream.state()["equities"])
    schwab_stream.focus_equity("AMD")
    assert _wait(lambda: "AMD" in schwab_stream.state()["equities"] and "NVDA" not in schwab_stream.state()["equities"])
    unsubs = [r for m in socks.sent for r in m["requests"] if r["command"] == "UNSUBS"]
    assert {r["service"] for r in unsubs} == {"CHART_EQUITY", "LEVELONE_EQUITIES"} and all(r["parameters"]["keys"] == "NVDA" for r in unsubs)
    schwab_stream.focus_equity("TSLA")
    schwab_stream.focus_equity("MSFT")
    time.sleep(1.5)
    assert "TSLA" in schwab_stream.state()["equities"]            # still needed by the open trade: kept


def test_twenty_percent_example_is_a_planned_threshold_not_a_cap(chart_env):
    """$2.00 premium -> $1.60 threshold; 3 contracts x 100 -> $120 before fees and slippage; $600 is the full premium."""
    import commands
    import engine
    import exits
    clock, fk = chart_env
    _go(clock, 10, 20, 5)
    p = commands.handle("IN SPY 600C 3 at 2.00", "SPY")["position"]
    exits.evaluate(store.pos_get(p["id"]), engine.snapshot("SPY")["v3"])
    ex = store.pos_get(p["id"])["plan"]["guidance"]["plan"]["exposure"]
    assert ex["threshold_20pct"] == 1.60 and ex["threshold_loss_usd"] == 120.0 and ex["multiplier"] == 100.0
    assert ex["full_premium_usd"] == 600.0 and "not a loss cap" in ex["note"]
    assert ex["premium_stop"] >= 1.60                                   # the alert level includes fees, never wider
    assert "can't see or place" in ex["broker_stop"]


def test_rule_comparison_keeps_untraded_setups_and_latency_is_observed(chart_env):
    import json as _j
    import entrygate
    import evaluation
    store.x(entrygate.SCHEMA)
    rows = [("G1", "orb_break", "TRADED"), ("G2", "orb_break", "MISSED"), ("G3", "orb_retest", "INVALIDATED"), ("G4", "orb_failed", "NO TRADE")]
    for gid, kind, st in rows:
        store.x("INSERT INTO gate_setups(id,date,ticker,side,kind,version,status,created,updated,data) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (gid, "2026-10-28", "SPY", "C", kind, "t", st, "x", "x", "{}"))
    store.pos_save({"id": "P1", "ledger": "gated", "date": "2026-10-28", "ticker": "SPY", "contract": "600C", "symbol": "SPY261028C00600000",
                    "side": "C", "qty_init": 1, "qty_open": 0, "fill": 2.0, "opened": "2026-10-28T10:00:00-04:00", "closed": "2026-10-28T10:20:00-04:00",
                    "status": "CLOSED", "setup_id": "G1", "grade": "B", "setup": "ORB", "plan": {"gate": {"id": "G1"}, "latency_s": 2.5},
                    "realized": 35.0, "mfe": 0, "mae": 0, "policy_version": "t", "verified": "t", "notes": ""})
    r = evaluation.rules_compare("2026-10-01")["groups"]
    assert r["confirmed breakout"]["setups"] == 2 and r["confirmed breakout"]["traded"] == 1 and r["confirmed breakout"]["not_traded"] == 1
    assert r["confirmed breakout"]["status"]["MISSED"] == 1 and r["pullback / retest"]["traded"] == 0 and r["reversal"]["setups"] == 1
    lat = evaluation.latency("2026-10-01")
    assert lat["signal_to_paper_fill"]["n"] == 1 and lat["signal_to_paper_fill"]["median_s"] == 2.5


def test_stream_interruption_reconnects_with_one_socket(live, monkeypatch):
    fake, socks = live
    monkeypatch.setattr(schwab_stream, "_sleep", lambda s, g: time.sleep(0.05))
    assert schwab.connect("https://127.0.0.1/?code=DROP")[0]
    assert _wait(lambda: schwab_stream.state()["phase"] == "live")
    orig = _WS.recv
    dropped = {"n": 0}

    async def flaky(self):
        if self.n >= 2 and dropped["n"] == 0:
            dropped["n"] = 1
            raise ConnectionError("socket dropped (test)")
        return await orig(self)
    monkeypatch.setattr(_WS, "recv", flaky)
    assert _wait(lambda: schwab_stream.state()["sessions"] >= 2 and schwab_stream.state()["phase"] == "live", 8), schwab_stream.state()
    assert socks.max_open == 1 and socks.open == 1 and dropped["n"] == 1
