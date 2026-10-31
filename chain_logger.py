"""chain_logger.py - v4 research data: option-chain snapshots every 60 s, 09:30-16:00 ET, to measure real spreads and
greeks for the later option backtests (docs/STRATEGY_PLAN.md section 6). Market data only; never trades.

What is logged each minute (one CSV row per contract):
  * SPY and QQQ: today's expiry (0DTE), strikes within +/-3% of spot;
  * $XSP and $SPX the same way, only on days Schwab returns a chain for them (probed once a day, result kept);
  * every symbol with an open options-shadow trade (<ledger>_opt): the held contract's expiry, strikes within +/-3%.
Fields: logged_at, underlying, spot, symbol, type, expiry, strike, bid, ask, last, volume, open interest, delta, gamma,
IV, quote time.
Budget: every request runs in the "research" class of the shared Schwab rate budget (at most 70% of it, waits first),
so it can never delay the risk work that protects open positions. One request per symbol per minute (calls and puts
together) when the provider supports it.
Storage: data/chains/<day>.csv while the day runs, then a daily export to data/chains/<day>.csv.gz (atomic) after
16:05 (also on the next start for any day left uncompressed). data/ is gitignored. Size caps: MAX_ROWS_DAY rows a
day and MAX_DIR_MB for the folder; when a cap is reached logging stops for the day and the reason is shown.
"""
import csv
import gzip
import io
import threading
import time
from datetime import timedelta

import core
import marketdata
import store

VERSION = "2026-11-02.v4-chains1"
DIR = core.HERE / "data" / "chains"
INTERVAL_S = 60
BAND = 0.03
MAX_ROWS_DAY = 400_000
MAX_DIR_MB = 4000
FIELDS = ["logged_at", "underlying", "spot", "symbol", "type", "expiry", "strike", "bid", "ask", "last", "volume", "oi",
          "delta", "gamma", "iv", "quote_time"]
BASE = ("SPY", "QQQ")
EXTRA = ("$XSP", "$SPX")
_state = {"thread": None, "stop": False, "last_run": None, "last_error": None, "status": "idle", "rows_today": {}, "capped": {},
          "last_minute": None}


def _partial(day):
    return DIR / f"{day}.csv"


def _final(day):
    return DIR / f"{day}.csv.gz"


def dir_mb():
    if not DIR.exists():
        return 0.0
    return round(sum(p.stat().st_size for p in DIR.iterdir() if p.is_file()) / 1e6, 2)


def _spot(sym, rows):
    for r in rows or []:
        if r.get("underlying"):
            return float(r["underlying"])
    try:
        q = marketdata.quote(sym)
        if q and q.get("last"):
            return float(q["last"])
    except Exception:
        pass
    return None


def fetch_chain(sym, first, through=None):
    """Both sides for an expiry range: one request with chain_all when the provider has it, else two."""
    p = marketdata.provider()
    if hasattr(p, "chain_all"):
        rows, err = p.chain_all(sym, first, through)
        return rows or [], err
    out, err = [], None
    for side in ("C", "P"):
        rows, e = p.chain(sym, side, first, through)
        err = err or e
        for r in rows or []:
            out.append(dict(r, type=r.get("type") or side))
    return out, err


def extra_available(sym, day):
    key = f"v4_chain_avail:{sym}:{day}"
    hit = store.kv_get(key)
    if hit is not None:
        return bool(hit)
    rows, err = fetch_chain(sym, str(day))
    ok = bool(rows)
    store.kv_set(key, ok)
    if not ok:
        store.event("v4", f"chain logger: {sym} not available today ({err or 'empty chain'}), skipped", "v4")
    return ok


def targets(now):
    """[(underlying, expiry_from, expiry_to)] to log this minute."""
    day = now.date()
    out = [(s, str(day), None) for s in BASE]
    for s in EXTRA:
        if extra_available(s, day):
            out.append((s, str(day), None))
    try:
        import v4store as S
        for p in S.positions(status="OPEN"):
            if str(p["ledger"]).endswith("_opt") and p.get("legs"):
                exp = p["legs"][0].get("expiry") or str(day)
                if (p["ticker"], exp, exp) not in out:
                    out.append((p["ticker"], exp, exp))
    except Exception:
        pass
    return out


def snapshot(sym, first, through, now):
    rows, err = fetch_chain(sym, first, through)
    spot = _spot(sym, rows)
    if not rows or spot is None:
        return [], err or "no spot"
    lo, hi = spot * (1 - BAND), spot * (1 + BAND)
    keep = [r for r in rows if r.get("strike") is not None and lo <= float(r["strike"]) <= hi
            and (through is not None or (r.get("exp") or first) == first)]
    t = now.isoformat(timespec="seconds")
    return [{"logged_at": t, "underlying": sym, "spot": spot, "symbol": r.get("symbol"), "type": r.get("type"),
             "expiry": r.get("exp"), "strike": r.get("strike"), "bid": r.get("bid"), "ask": r.get("ask"), "last": r.get("last"),
             "volume": r.get("volume"), "oi": r.get("oi"), "delta": r.get("delta"), "gamma": r.get("gamma"), "iv": r.get("iv"),
             "quote_time": r.get("ts") or (str(r.get("quote_time")) if r.get("quote_time") is not None else None)} for r in keep], None


def _append(day, rows):
    DIR.mkdir(parents=True, exist_ok=True)
    p = _partial(day)
    new = not p.exists()
    with open(p, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in FIELDS})


def _rows_in(day):
    if str(day) in _state["rows_today"]:
        return _state["rows_today"][str(day)]
    p = _partial(day)
    n = 0
    if p.exists():
        with open(p) as f:
            n = max(0, sum(1 for _ in f) - 1)
    _state["rows_today"][str(day)] = n
    return n


def export(day):
    """Compress the day's CSV to <day>.csv.gz atomically and remove the plain file. Returns rows exported."""
    p = _partial(day)
    if not p.exists():
        return 0
    raw = p.read_bytes()
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
        g.write(raw)
    out = _final(day)
    if out.exists():                                            # a second export the same day appends a new gz member
        buf = io.BytesIO(out.read_bytes() + buf.getvalue())
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(buf.getvalue())
    tmp.replace(out)
    p.unlink()
    n = max(0, raw.count(b"\n") - 1)
    store.kv_set(f"v4_chains_export:{day}", {"rows": n, "bytes": out.stat().st_size, "at": store.ts()})
    return n


def export_leftovers(today):
    if not DIR.exists():
        return 0
    n = 0
    for p in DIR.glob("*.csv"):
        if p.stem < str(today):
            n += export(p.stem)
    return n


def step(now=None):
    now = now or core.now_et()
    day = now.date()
    sess = core.session_info(now)
    hm = now.strftime("%H:%M")
    if sess.get("holiday"):
        _state["status"] = "market closed"
        return 0
    if hm >= "16:05" and _partial(day).exists():
        export(day)
    if not ("09:30" <= hm < "16:00"):
        _state["status"] = "outside 09:30-16:00"
        return 0
    if not marketdata.executable():
        _state["status"] = "waiting for live Schwab data"
        return 0
    minute = now.strftime("%Y-%m-%d %H:%M")
    if _state["last_minute"] == minute:
        return 0
    if _state["capped"].get(str(day)):
        _state["status"] = _state["capped"][str(day)]
        return 0
    if _rows_in(day) >= MAX_ROWS_DAY:
        _state["capped"][str(day)] = f"daily row cap {MAX_ROWS_DAY:,} reached: logging stopped for today"
        return 0
    if dir_mb() >= MAX_DIR_MB:
        _state["capped"][str(day)] = f"folder cap {MAX_DIR_MB} MB reached: logging stopped (export or move old files)"
        return 0
    _state["last_minute"] = minute
    import schwab
    total = 0
    with schwab.priority("research"):
        for sym, first, through in targets(now):
            try:
                rows, err = snapshot(sym, first, through, now)
            except Exception as e:
                rows, err = [], type(e).__name__
            if err and not rows:
                _state["last_error"] = f"{sym}: {err}"
            if rows:
                _append(day, rows)
                total += len(rows)
    _state["rows_today"][str(day)] = _rows_in(day) + total
    _state.update(last_run=store.ts(), status=f"logging ({total} rows this minute)")
    return total


def _run():
    try:
        export_leftovers(core.now_et().date())
    except Exception as e:
        _state["last_error"] = f"export: {type(e).__name__}"
    while not _state["stop"]:
        try:
            step()
            import health
            health.beat("chains", True, _state.get("status"))
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {e}"[:200]
        time.sleep(5)


def start():
    if _state["thread"]:
        return False
    th = threading.Thread(target=_run, daemon=True, name="chains")
    _state["thread"] = th
    th.start()
    return True


def _rel(p):
    try:
        return str(p.relative_to(core.HERE))
    except ValueError:
        return str(p)


def status():
    day = core.now_et().date()
    files = sorted(p.name for p in DIR.iterdir()) if DIR.exists() else []
    return {"version": VERSION, "status": _state["status"], "last_run": _state["last_run"], "last_error": _state["last_error"],
            "rows_today": _state["rows_today"].get(str(day), 0), "dir": _rel(DIR), "dir_mb": dir_mb(),
            "caps": {"rows_per_day": MAX_ROWS_DAY, "dir_mb": MAX_DIR_MB}, "capped": _state["capped"].get(str(day)),
            "files": files[-10:], "last_export": store.kv_get(f"v4_chains_export:{day - timedelta(days=1)}")}
