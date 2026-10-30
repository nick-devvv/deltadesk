"""schwab_stream.py - Schwab streaming market data (read-only) feeding marketdata.py.

Protocol (checked against schwab-py v1.5.0, an UNOFFICIAL community wrapper; Schwab's official Trader API docs
are authoritative for your app's entitlements):
  1. GET /trader/v1/userPreference -> streamerInfo (socket URL, customer/correl IDs, channel, function ID)
  2. websocket LOGIN: {"service":"ADMIN","command":"LOGIN","parameters":{"Authorization":<access token>, ...}}
  3. SUBS CHART_EQUITY (1m OHLCV: 0 key, 1 seq, 2 open, 3 high, 4 low, 5 close, 6 volume, 7 bar time ms, 8 day)
     SUBS LEVELONE_EQUITIES (1 bid, 2 ask, 3 last, 4/5 sizes, 8 total volume, 34 quote ms, 35 trade ms)
     SUBS/ADD LEVELONE_OPTIONS (2 bid, 3 ask, 4 last, 8 volume, 9 OI, 10 IV, 13 multiplier, 16/17 sizes,
     28 delta, 29 gamma, 30 theta, 31 vega, 35 underlying, 37 mark, 38 quote ms, 39 trade ms)
  Level-one messages are INCREMENTAL: a field that is missing means "unchanged", never zero.

Runs in its own thread with an asyncio loop. Handlers are non-blocking (they only merge into marketdata).
Subscription changes are queued and sent one at a time. On disconnect: exponential backoff (1 s .. 60 s),
re-login, resubscribe, then REST backfill of 1m bars so gaps are repaired, not erased. Needs the
`websockets` package (pinned in requirements.txt); without it the desk stays on Schwab REST polling.
Never logs the token. Exposes no trading functionality.
"""
import asyncio
import json
import queue
import threading
import time

import core
import marketdata
import schwab

EQ_FIELDS = "0,1,2,3,4,5,8,9,34,35"
OPT_FIELDS = "0,2,3,4,8,9,10,13,16,17,28,29,30,31,35,37,38,39"
CHART_FIELDS = "0,1,2,3,4,5,6,7,8"

_state = {"thread": None, "healthy": False, "want_opts": set(), "subscribed_opts": set(), "want_eq": set(), "subscribed_eq": set(),
          "stop": False, "gen": 0, "phase": "off", "detail": None, "since": None, "auth_failures": 0, "sessions": 0,
          "last_msg": None}
_ops = queue.Queue()
_life = threading.Lock()
MAX_AUTH_FAILURES = 3        # after this many refusals in a row the stream stops retrying until Nick reconnects


def _phase(p, detail=None):
    if _state["phase"] != p or detail != _state["detail"]:
        _state.update(phase=p, detail=detail, since=time.time())


def state():
    """Stream lifecycle for the UI: off / waiting / connecting / live / reconnecting / stopped (+ detail)."""
    return {"phase": _state["phase"], "detail": _state["detail"], "since": _state["since"], "healthy": healthy(),
            "sessions": _state["sessions"], "auth_failures": _state["auth_failures"], "generation": _state["gen"],
            "running": bool(_state["thread"] and _state["thread"].is_alive()),
            "equities": sorted(_state["subscribed_eq"]), "options": len(_state["subscribed_opts"])}


def available():
    try:
        import websockets  # noqa: F401
        return True
    except ImportError:
        return False


def healthy():
    return bool(_state["healthy"])


def stream_symbol(occ):
    """OCC 'SPY261028C00600000' -> Schwab 'SPY   261028C00600000' (root padded to 6)."""
    return occ[:-15].ljust(6) + occ[-15:]


def want_options(symbols):
    """Positions, candidates and plan contracts that need live quotes. Serialized through the op queue."""
    new = {s for s in symbols if s}
    add = new - _state["want_opts"]
    if add:
        _state["want_opts"] |= add
        _ops.put(("ADD", "LEVELONE_OPTIONS", sorted(add)))


def want_equities(symbols, base=True):
    """Extra stocks/ETFs to stream (Nick's open trades = base; the chart ticker goes through focus_equity)."""
    new = {s.upper() for s in symbols if s}
    if base:
        _state.setdefault("base_eq", set()).update(new)
    add = new - _state["want_eq"]
    if add:
        _state["want_eq"] |= add
        _ops.put(("ADD", "EQ", sorted(add)))


def focus_equity(symbol):
    """The chart's ticker. Switching charts unsubscribes the previous one unless something else still needs it
    (SPY/QQQ, an open trade, another want_equities caller)."""
    sym = (symbol or "").upper()
    prev = _state.get("chart_eq")
    if sym == prev:
        return
    _state["chart_eq"] = sym
    keep = set(core.policy()["instruments"]) | _state.setdefault("base_eq", set())
    if prev and prev not in keep and prev in _state["want_eq"]:
        _state["want_eq"].discard(prev)
        _ops.put(("UNSUBS", "EQ", [prev]))
    if sym:
        want_equities([sym], base=False)


def handle(msg):
    """Parse one decoded stream message into marketdata (also used by tests with recorded messages)."""
    for d in msg.get("data", []) or []:
        svc = d.get("service")
        for c in d.get("content", []) or []:
            key = c.get("key")
            if svc == "CHART_EQUITY":
                try:
                    marketdata.upsert_stream_bar(key, int(c["7"]), float(c["2"]), float(c["3"]), float(c["4"]),
                                                 float(c["5"]), float(c.get("6") or 0), c.get("1"))
                except (KeyError, TypeError, ValueError):
                    continue
            elif svc == "LEVELONE_EQUITIES":
                marketdata.merge_quote(key, {
                    "bid": _f(c.get("1")), "ask": _f(c.get("2")), "last": _f(c.get("3")),
                    "bid_size": c.get("4"), "ask_size": c.get("5"), "total_volume": c.get("8"),
                    "quote_time": marketdata._ms(c.get("34")), "trade_time": marketdata._ms(c.get("35"))}, "Schwab stream")
            elif svc == "LEVELONE_OPTIONS":
                sym = schwab.occ(key)
                marketdata.merge_quote(sym, {
                    "bid": _f(c.get("2")), "ask": _f(c.get("3")), "last": _f(c.get("4")), "volume": c.get("8"),
                    "oi": c.get("9"), "iv": marketdata._iv(_f(c.get("10"))), "multiplier": _f(c.get("13")),
                    "bid_size": c.get("16"), "ask_size": c.get("17"), "delta": _f(c.get("28")),
                    "gamma": _f(c.get("29")), "theta": _f(c.get("30")), "vega": _f(c.get("31")),
                    "underlying": _f(c.get("35")), "mark": _f(c.get("37")),
                    "quote_time": marketdata._ms(c.get("38")), "trade_time": marketdata._ms(c.get("39"))}, "Schwab stream")
    for n in msg.get("notify", []) or []:
        if "heartbeat" in n:
            marketdata._status["last_heartbeat"] = marketdata.now().isoformat(timespec="seconds")


def _f(v):
    v = schwab._num(v)
    return v


def _req(info, rid, service, command, params):
    return {"service": service, "requestid": str(rid), "command": command,
            "SchwabClientCustomerId": info["schwabClientCustomerId"], "SchwabClientCorrelId": info["schwabClientCorrelId"],
            "parameters": params}


def _ws_connect(url):
    """The websocket opener (tests swap in a fake server; nothing else ever changes it)."""
    import websockets
    return websockets.connect(url, ping_interval=20, max_size=2 ** 22)


async def _session(info, tickers, gen):
    async with _ws_connect(info["streamerSocketUrl"]) as ws:
        rid = 0
        tok = schwab.access_token()
        await ws.send(json.dumps({"requests": [_req(info, rid, "ADMIN", "LOGIN", {
            "Authorization": tok, "SchwabClientChannel": info["schwabClientChannel"],
            "SchwabClientFunctionId": info["schwabClientFunctionId"]})]}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), 20))
        code = (((resp.get("response") or [{}])[0]).get("content") or {}).get("code")
        if code not in (0, "0"):
            raise PermissionError(f"Schwab refused the stream login (code {code})")
        eq = sorted(set(tickers) | _state["want_eq"])
        subs = [("CHART_EQUITY", ",".join(eq), CHART_FIELDS), ("LEVELONE_EQUITIES", ",".join(eq), EQ_FIELDS)]
        if _state["want_opts"]:
            subs.append(("LEVELONE_OPTIONS", ",".join(stream_symbol(s) for s in sorted(_state["want_opts"])), OPT_FIELDS))
        for svc, keys, fields in subs:
            rid += 1
            await ws.send(json.dumps({"requests": [_req(info, rid, svc, "SUBS", {"keys": keys, "fields": fields})]}))
        _state["subscribed_opts"] = set(_state["want_opts"])
        _state["subscribed_eq"] = set(eq)
        _state["healthy"] = True
        _state["auth_failures"] = 0
        _state["sessions"] += 1
        _state["last_msg"] = time.time()
        _phase("live")
        marketdata.set_mode("stream")
        _backfill(eq)
        while not _state["stop"] and gen == _state["gen"]:
            while not _ops.empty():
                cmd, svc, syms = _ops.get_nowait()
                if svc == "EQ" and cmd == "UNSUBS":
                    syms = [s for s in syms if s in _state["subscribed_eq"]]
                    for s2 in ("CHART_EQUITY", "LEVELONE_EQUITIES"):
                        if syms:
                            rid += 1
                            await ws.send(json.dumps({"requests": [_req(info, rid, s2, "UNSUBS", {"keys": ",".join(syms)})]}))
                    _state["subscribed_eq"] -= set(syms)
                    continue
                if svc == "EQ":
                    syms = [s for s in syms if s not in _state["subscribed_eq"]]
                    for s2, f2 in (("CHART_EQUITY", CHART_FIELDS), ("LEVELONE_EQUITIES", EQ_FIELDS)):
                        if syms:
                            rid += 1
                            await ws.send(json.dumps({"requests": [_req(info, rid, s2, cmd, {"keys": ",".join(syms), "fields": f2})]}))
                    _state["subscribed_eq"] |= set(syms)
                    continue
                syms = [s for s in syms if s not in _state["subscribed_opts"]]
                if syms:
                    rid += 1
                    await ws.send(json.dumps({"requests": [_req(info, rid, svc, cmd, {
                        "keys": ",".join(stream_symbol(s) for s in syms), "fields": OPT_FIELDS})]}))
                    _state["subscribed_opts"] |= set(syms)
            try:
                raw = await asyncio.wait_for(ws.recv(), 1)      # short waits so Disconnect/Reconnect close this socket within ~1 s
            except asyncio.TimeoutError:
                if time.time() - (_state["last_msg"] or 0) > 30:
                    raise RuntimeError("no stream message (not even a heartbeat) for 30 s")
                continue
            _state["last_msg"] = time.time()
            try:
                handle(json.loads(raw))
            except ValueError:
                continue
        try:                                                   # retired (Disconnect / Reconnect): log out politely
            rid += 1
            await ws.send(json.dumps({"requests": [_req(info, rid, "ADMIN", "LOGOUT", {})]}))
        except Exception:
            pass


def _backfill(tickers):
    """REST 1m history after (re)connect: repairs gaps instead of erasing them."""
    rest = marketdata.SchwabREST()
    for t in tickers:
        try:
            before = len(marketdata.gaps(marketdata.bars(t, refresh=False)[0]))
            marketdata.upsert_bars(t, rest.bars_1m(t), "Schwab REST backfill")
            after = len(marketdata.gaps(marketdata.bars(t, refresh=False)[0]))
            marketdata._status["gaps_filled"] += max(0, before - after)
        except Exception:
            pass


def _sleep(seconds, gen):
    end = time.time() + seconds
    while time.time() < end and not _state["stop"] and gen == _state["gen"]:
        time.sleep(0.5)


def _run(tickers, gen):
    """One worker per generation. A newer generation (restart) or stop() ends this one cleanly, so there is never more
    than one stream. Auth refusals (HTTP 401/403, LOGIN refused) are counted; after MAX_AUTH_FAILURES the worker stops
    retrying and asks for a reconnect instead of hammering Schwab."""
    delay = 1
    while not _state["stop"] and gen == _state["gen"]:
        st = schwab.status()
        if st["state"] in ("disconnected", "expired") or (st["state"] == "connecting" and st.get("days_left") is None):
            _state["healthy"] = False
            _phase("waiting", f"waiting for a Schwab login ({st['state']})")
            _sleep(5, gen)
            continue
        _phase("connecting" if _state["sessions"] == 0 else "reconnecting", None)
        info, err = schwab.streamer_info()
        try:
            if not info:
                if err and err.startswith(("HTTP 401", "HTTP 403")):
                    raise PermissionError(f"Schwab refused the streaming preferences call ({err})")
                raise RuntimeError(err or "no streamer info")
            asyncio.run(_session(info, tickers, gen))
            delay = 1
        except PermissionError as e:
            _state["healthy"] = False
            _state["auth_failures"] += 1
            marketdata._status["reconnects"] += 1
            if _state["auth_failures"] >= MAX_AUTH_FAILURES:
                why = (f"{e}. Market data keeps working through REST polling. Fix: the Schwab app needs Accounts and "
                       "Trading Production, then press Reconnect Schwab on the Rules page (a login made before the product "
                       "was added can't open the stream).")
                _phase("stopped", why)
                marketdata.set_mode("rest", "stream stopped: " + str(e)[:120])
                return
            _phase("reconnecting", str(e))
            marketdata.set_mode("rest", f"stream: {str(e)[:120]}")
            _sleep(delay, gen)
            delay = min(60, delay * 2)
        except Exception as e:
            _state["healthy"] = False
            marketdata.set_mode("rest", f"stream: {type(e).__name__}: {str(e)[:120]}")
            marketdata._status["reconnects"] += 1
            _phase("reconnecting", f"{type(e).__name__}: {str(e)[:120]}")
            _sleep(delay, gen)
            delay = min(60, delay * 2)
    if gen == _state["gen"]:
        _state["healthy"] = False


def start(tickers=None):
    """Start the stream worker if it isn't running. Safe to call repeatedly (never two workers)."""
    with _life:
        if not available():
            _phase("off", "websockets package not installed: Schwab REST polling")
            return False
        if _state["thread"] and _state["thread"].is_alive() and not _state["stop"]:
            return False
        _state["stop"] = False
        _state["gen"] += 1
        tickers = tickers or core.policy()["instruments"]
        th = threading.Thread(target=_run, args=(tickers, _state["gen"]), daemon=True, name=f"schwab-stream-{_state['gen']}")
        _state["thread"] = th
        th.start()
        return True


def stop(reason="stopped"):
    """Stop streaming and cancel reconnect attempts. The worker notices within a second and exits."""
    with _life:
        _state["stop"] = True
        _state["gen"] += 1                       # any sleeping/running worker sees a stale generation and quits
        _state["healthy"] = False
        _state["subscribed_opts"], _state["subscribed_eq"] = set(), set()
        old_thread, _state["thread"] = _state["thread"], None
        _phase("off", reason)
        while not _ops.empty():
            _ops.get_nowait()
    if old_thread and old_thread.is_alive() and old_thread is not threading.current_thread():
        old_thread.join(timeout=3)              # the old socket closes before a new one opens (no two streams)
    marketdata.set_mode("rest" if schwab.status()["state"] == "connected" else "offline")
    return True


def restart(reason="reconnect"):
    """A clean new worker (used after Connect / Reconnect). Counters reset; old subscriptions are re-sent once."""
    stop(reason)
    _state["auth_failures"], _state["sessions"] = 0, 0
    return start()
