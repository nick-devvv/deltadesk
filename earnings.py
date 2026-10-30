"""earnings.py - earnings in three separate phases, each with its own records:

  A. PRE      before the announcement: date and timing (confirmed or estimated, with the source), the options expiry
              exposed to the event, ATM IV for that expiry vs the next one, spreads, and a rough ATM-straddle move proxy.
  B. RELEASE  after the results are out (detected from the SEC 8-K Item 2.02, or a confirmed catalyst): reported vs
              expected numbers ONLY when both come with sources (consensus is point-in-time as captured; Schwab has no
              estimates feed). GAAP and adjusted are kept apart. An EPS beat alone is not a trade signal.
  C. CALL     during / after the call: material statements with attribution and time, when an authorized source exists.
  NEXT        the first regular session after the release: the default paper strategy ("earn_post") waits for a
              post-release confirmation setup here, through the same entry gate as everything else.

Straddle proxy = (ATM call mid + ATM put mid) / spot, for the first expiry after the event, with the strikes, expiry,
quote time and formula shown. It is a rough pricing proxy: not a guaranteed range and not a 68% interval. Buying a
straddle also pays both premiums and loses to IV crush and theta; nothing here assumes it profits.

Dates: Schwab's market-data API has no earnings calendar. The desk uses Yahoo's calendar (unofficial) and labels it
ESTIMATED until a source confirms it (company release, IR page, or an attributed report), set via POST /api/earnings.
"""
import json
from datetime import date, datetime, timedelta

import core
import store

SCHEMA = "CREATE TABLE IF NOT EXISTS earnings(ticker TEXT, date TEXT, data TEXT, updated TEXT, PRIMARY KEY(ticker, date))"


def _get(ticker, d):
    store.x(SCHEMA)
    r = store.q("SELECT data FROM earnings WHERE ticker=? AND date=?", (ticker, d))
    return json.loads(r[0]["data"]) if r else None


def _put(rec):
    store.x(SCHEMA)
    store.x("INSERT OR REPLACE INTO earnings(ticker,date,data,updated) VALUES(?,?,?,?)",
            (rec["ticker"], rec["date"], json.dumps(rec, default=str), store.ts()))


def event(ticker, lookup=None):
    """The next (or just-passed) earnings event for a ticker, from the store or the calendar lookup."""
    store.x(SCHEMA)
    today = core.now_et().date()
    rows = store.q("SELECT data FROM earnings WHERE ticker=? AND date>=? ORDER BY date LIMIT 1", (ticker, (today - timedelta(days=3)).isoformat()))
    if rows:
        return json.loads(rows[0]["data"])
    info = None
    try:
        import watchlist
        info = (lookup or watchlist.earnings)(ticker)
    except Exception:
        info = None
    if not info or not info.get("date"):
        return None
    rec = {"ticker": ticker, "date": info["date"], "timing": info.get("timing") or "unknown (before open or after close?)",
           "status": "estimated", "date_source": "Yahoo calendar (unofficial)", "call_time": None, "released_at": None,
           "release_source": None, "results": None, "call_notes": []}
    _put(rec)
    return rec


def confirm(ticker, d, timing=None, source_url=None, call_time=None):
    """A sourced confirmation of the date / timing (only a primary or reporting source upgrades it)."""
    import catalysts
    rec = _get(ticker, d) or {"ticker": ticker, "date": d, "results": None, "call_notes": [], "released_at": None}
    kind = catalysts.source_kind(source_url) if source_url else None
    rec.update(timing=timing or rec.get("timing"), call_time=call_time or rec.get("call_time"))
    if kind in ("primary", "reporting"):
        rec.update(status="confirmed", date_source=source_url)
    else:
        rec.setdefault("status", "estimated")
        rec["date_note"] = "source not primary or identifiable reporting: still estimated"
    _put(rec)
    return rec


def mark_released(ticker, published_at, url):
    """Release detected (e.g. 8-K Item 2.02). Phase B starts; the published time is SEC's acceptance time."""
    d = str(published_at or core.now_et().isoformat())[:10]
    rec = _get(ticker, d) or event(ticker) or {"ticker": ticker, "date": d, "results": None, "call_notes": []}
    if rec.get("date") != d:
        rec = dict(rec, date=d)
    rec.update(released_at=published_at, release_source=url, status="confirmed" if "sec.gov" in str(url) else rec.get("status", "estimated"))
    _put(rec)
    return rec


def record_results(ticker, d, metrics, source_url, consensus_source=None, consensus_captured_at=None):
    """metrics: {"revenue": {"reported": x, "expected": y, "basis": "GAAP"|"adjusted"}, "eps": {...}, "guidance": {...}, ...}.
    Each comparison needs its own sourced expectation; without one, the comparison is not shown."""
    rec = _get(ticker, d) or {"ticker": ticker, "date": d}
    rows = {}
    for k, v in (metrics or {}).items():
        if not isinstance(v, dict) or v.get("reported") is None:
            continue
        exp = v.get("expected")
        rows[k] = {"reported": v["reported"], "expected": exp, "basis": v.get("basis") or "not stated",
                   "surprise_pct": round((v["reported"] / exp - 1) * 100, 2) if isinstance(exp, (int, float)) and exp else None,
                   "comparable": bool(exp is not None and consensus_source)}
    rec["results"] = {"metrics": rows, "source": source_url, "consensus_source": consensus_source,
                      "consensus_captured_at": consensus_captured_at, "recorded_at": store.ts(),
                      "note": "point-in-time expectations as captured; GAAP and adjusted never compared with each other; an EPS beat alone is not a trade signal"}
    _put(rec)
    return rec


def phase(rec, now=None):
    """PRE / RELEASE / CALL / NEXT SESSION / DONE / NONE for an earnings record."""
    if not rec:
        return "NONE"
    now = now or core.now_et()
    d = date.fromisoformat(rec["date"])
    if rec.get("released_at"):
        rel = datetime.fromisoformat(str(rec["released_at"]).replace("Z", "+00:00")).astimezone(core.ET)
        if rec.get("call_time"):
            ct = datetime.fromisoformat(rec["call_time"]).astimezone(core.ET)
            if ct <= now <= ct + timedelta(minutes=90):
                return "CALL"
        nxt = next_session_after(rel)
        if now.date() < nxt:
            return "RELEASE"
        if now.date() == nxt:
            return "NEXT SESSION"
        return "DONE"
    if now.date() <= d:
        return "PRE"
    return "DONE" if (now.date() - d).days > 2 else "RELEASE?"


def next_session_after(t):
    """First regular session that starts after time t (a release at 08:00 counts for the same day's session)."""
    d = t.date()
    if t.strftime("%H:%M") < "09:30" and _trading_day(d):
        return d
    d += timedelta(days=1)
    while not _trading_day(d):
        d += timedelta(days=1)
    return d


def _trading_day(d):
    return d.weekday() < 5 and d.isoformat() not in core.HOLIDAYS


def straddle(ticker, rec, chain=None, spot=None, now=None):
    """Rough ATM-straddle move proxy for the first expiry after the event, from the live Schwab chain."""
    import marketdata
    now = now or core.now_et()
    if not rec:
        return None
    ev = date.fromisoformat(rec["date"])
    after_close = "after" in str(rec.get("timing") or "").lower()
    first_exp = ev + timedelta(days=1) if after_close else ev
    p = marketdata.provider()
    out = {}
    for side in ("C", "P"):
        rows, err = (chain or p.chain)(ticker, side, first_exp.isoformat(), (first_exp + timedelta(days=10)).isoformat())
        out[side] = rows or []
    if not out["C"] or not out["P"]:
        return {"error": "no option chain for the event expiry"}
    spot = spot or ((marketdata.quote(ticker) or {}).get("last"))
    if not spot:
        return {"error": "no underlying price"}
    exp = min(r["exp"] for r in out["C"])
    calls = [r for r in out["C"] if r["exp"] == exp]
    puts = {r["strike"]: r for r in out["P"] if r["exp"] == exp}
    atm = min((r for r in calls if r["strike"] in puts), key=lambda r: abs(r["strike"] - spot), default=None)
    if not atm:
        return {"error": "no matching call/put strike"}
    put = puts[atm["strike"]]
    mid = lambda r: (r["bid"] + r["ask"]) / 2 if r.get("bid") is not None and r.get("ask") is not None else None
    cm, pm = mid(atm), mid(put)
    if cm is None or pm is None:
        return {"error": "missing bid/ask"}
    st = cm + pm
    return {"expiry": exp, "strike": atm["strike"], "call_mid": round(cm, 2), "put_mid": round(pm, 2), "straddle": round(st, 2),
            "spot": spot, "move_pct": round(st / spot * 100, 2), "move_usd": round(st, 2),
            "call_spread_pct": round((atm["ask"] - atm["bid"]) / atm["ask"] * 100, 1) if atm["ask"] else None,
            "put_spread_pct": round((put["ask"] - put["bid"]) / put["ask"] * 100, 1) if put["ask"] else None,
            "iv_call": atm.get("iv"), "iv_put": put.get("iv"), "quote_time": atm.get("ts") or now.isoformat(timespec="seconds"),
            "formula": "(ATM call mid + ATM put mid) / spot, first expiry after the event",
            "caveat": "rough pricing proxy only: not a guaranteed range and not a 68% interval; buying both legs pays both premiums and IV usually falls after the report"}


def calendar(tickers=None, days=14, lookup=None):
    import scanner
    tickers = tickers or list(dict.fromkeys(list(core.policy()["instruments"]) + scanner.universe()))
    today = core.now_et().date()
    out = []
    for t in tickers:
        rec = event(t, lookup)
        if not rec:
            continue
        d = date.fromisoformat(rec["date"])
        if -3 <= (d - today).days <= days:
            out.append(dict(rec, phase=phase(rec), days=(d - today).days))
    out.sort(key=lambda r: r["date"])
    return out


def prev_session(d):
    d -= timedelta(days=1)
    while not _trading_day(d):
        d -= timedelta(days=1)
    return d


def cached_calendar(days=14):
    """Calendar from the store only (no network); refresh_calendar() fills it in the background."""
    store.x(SCHEMA)
    today = core.now_et().date()
    rows = store.q("SELECT data FROM earnings WHERE date>=? AND date<=? ORDER BY date",
                   ((today - timedelta(days=3)).isoformat(), (today + timedelta(days=days)).isoformat()))
    out = []
    for r in rows:
        rec = json.loads(r["data"])
        out.append(dict(rec, phase=phase(rec), days=(date.fromisoformat(rec["date"]) - today).days))
    return out


def refresh_calendar():
    """Once a day, in the background: Yahoo dates (labeled estimated) for the universe + watchlist."""
    k = f"earn_cal_refreshed:{core.now_et().date()}"
    if store.kv_get(k):
        return False
    store.kv_set(k, True)
    calendar()
    return True
