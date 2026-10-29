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

_state = {"thread": None, "healthy": False, "want_opts": set(), "subscribed_opts": set(), "stop": False}
_ops = queue.Queue()


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


async def _session(info, tickers):
    import websockets
    async with websockets.connect(info["streamerSocketUrl"], ping_interval=20, max_size=2 ** 22) as ws:
        rid = 0
        tok = schwab.access_token()
        await ws.send(json.dumps({"requests": [_req(info, rid, "ADMIN", "LOGIN", {
            "Authorization": tok, "SchwabClientChannel": info["schwabClientChannel"],
            "SchwabClientFunctionId": info["schwabClientFunctionId"]})]}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), 20))
        code = (((resp.get("response") or [{}])[0]).get("content") or {}).get("code")
        if code not in (0, "0"):
            raise RuntimeError(f"stream LOGIN refused (code {code})")
        subs = [("CHART_EQUITY", ",".join(tickers), CHART_FIELDS), ("LEVELONE_EQUITIES", ",".join(tickers), EQ_FIELDS)]
        if _state["want_opts"]:
            subs.append(("LEVELONE_OPTIONS", ",".join(stream_symbol(s) for s in sorted(_state["want_opts"])), OPT_FIELDS))
        for svc, keys, fields in subs:
            rid += 1
            await ws.send(json.dumps({"requests": [_req(info, rid, svc, "SUBS", {"keys": keys, "fields": fields})]}))
        _state["subscribed_opts"] = set(_state["want_opts"])
        _state["healthy"] = True
        marketdata.set_mode("stream")
        _backfill(tickers)
        while not _state["stop"]:
            while not _ops.empty():
                cmd, svc, syms = _ops.get_nowait()
                syms = [s for s in syms if s not in _state["subscribed_opts"]]
                if syms:
                    rid += 1
                    await ws.send(json.dumps({"requests": [_req(info, rid, svc, cmd, {
                        "keys": ",".join(stream_symbol(s) for s in syms), "fields": OPT_FIELDS})]}))
                    _state["subscribed_opts"] |= set(syms)
            try:
                raw = await asyncio.wait_for(ws.recv(), 30)
            except asyncio.TimeoutError:
                raise RuntimeError("no stream message for 30 s")
            try:
                handle(json.loads(raw))
            except ValueError:
                continue


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


def _run(tickers):
    delay = 1
    while not _state["stop"]:
        if not schwab.ready():
            _state["healthy"] = False
            time.sleep(15)
            continue
        info, err = schwab.streamer_info()
        try:
            if not info:
                raise RuntimeError(err or "no streamer info")
            asyncio.run(_session(info, tickers))
            delay = 1
        except Exception as e:
            _state["healthy"] = False
            marketdata.set_mode("rest", f"stream: {type(e).__name__}: {str(e)[:120]}")
            marketdata._status["reconnects"] += 1
            time.sleep(delay)
            delay = min(60, delay * 2)


def start(tickers=None):
    if _state["thread"] or not available():
        return False
    tickers = tickers or core.policy()["instruments"]
    th = threading.Thread(target=_run, args=(tickers,), daemon=True, name="schwab-stream")
    _state["thread"] = th
    th.start()
    return True
