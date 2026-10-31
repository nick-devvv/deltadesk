"""news_drift.py - v4 news-drift EVENT LOGGER (docs/STRATEGY_PLAN.md section 4.5). Research only: no trading, no
orders, no paper positions. It builds the forward event study the ledger would later be judged on.

For every catalyst that catalysts.py marks entry-eligible (confirmed or attributed, content-verified by the desk's own
fetch, not resurfacing; company-specific, at most 3 tickers, not SPY/QQQ), one row in news_drift_events:
  news_t      the catalyst's own time: SEC acceptance / publication time if known, else when the desk first saw it
  known_t     when the desk could act on it: the first catalyst REVISION that was entry-eligible (as-of read, so a
              later verification can never move it earlier)
  t0          max(news_t, known_t), moved to the next regular-session minute if outside 09:30-15:59 (flagged)
  rv5         volume of the 5 finished 1m bars starting at/after t0 / the average volume of the same minutes over the prior
              sessions (exact 1m history when the desk has it, else the 5-minute grid, labeled)
  first bar   the first FINISHED 1m bar starting at/after t0: direction up / down / flat
  entry       the next bar's open (entry_t, entry_px); half_spread = (ask - bid) / 2 from a quote taken within 2 min
              of entry_t (None, labeled, when the desk only looked later)
After the close: the move from entry_px to the close of the bar ending entry_t + 15 / 30 / 60 / 120 minutes, raw and
signed by the first bar's direction, and net of the half spread (None if the horizon passes 16:00).
Holding time and any RV threshold are picked LATER on the first 2/3 of events and tested on the last 1/3 (plan 4.5).
"""
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

import core
import store

VERSION = "2026-11-02.v4-newsdrift1"
HORIZONS = (15, 30, 60, 120)
SCHEMA = """CREATE TABLE IF NOT EXISTS news_drift_events(id TEXT PRIMARY KEY, day TEXT, ticker TEXT, headline TEXT, category TEXT,
  label TEXT, news_t TEXT, known_t TEXT, t0 TEXT, anchored TEXT, rv5 REAL, rv5_basis TEXT, first_bar_t TEXT, first_bar_dir TEXT,
  entry_t TEXT, entry_px REAL, half_spread REAL, spread_quote_t TEXT, moves TEXT, status TEXT, reason TEXT, created TEXT,
  updated TEXT, version TEXT, data TEXT)"""
MAX_TICKERS = 3
_state = {"last_error": None}


def _schema():
    store.x(SCHEMA)


def _et(t):
    if t is None:
        return None
    d = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=core.ET)
    return d.astimezone(core.ET)


def anchor(t):
    """(t0, note): t itself in regular hours, else the next regular-session open minute."""
    hm = t.strftime("%H:%M")
    if "09:30" <= hm <= "15:58" and t.weekday() < 5 and t.strftime("%Y-%m-%d") not in core.HOLIDAYS:
        return t, None
    import earnings
    d = earnings.next_session_after(t)
    return datetime.combine(d, datetime.min.time(), core.ET).replace(hour=9, minute=30), "outside regular hours: anchored to the next open"


def known_time(cat_id, now):
    """The valid_from of the first entry-eligible revision of a catalyst (ET), or None."""
    import catalysts
    catalysts._schema()
    rows = store.q("SELECT rev, valid_from, data FROM catalyst_revisions WHERE cat_id=? AND valid_from<=? ORDER BY rev",
                   (cat_id, catalysts._utc(now)))
    for r in rows:
        if catalysts.entry_eligible(json.loads(r["data"])):
            return _et(r["valid_from"])
    return None


def first_bar(m1, t0, now):
    """(bar_open, direction) of the first finished 1m bar starting at/after t0, and the next bar (entry), or Nones."""
    if m1 is None or not len(m1):
        return None, None, None, None
    m = m1[(m1.index >= pd.Timestamp(t0).floor("1min")) & (m1.index + pd.Timedelta(minutes=1) <= pd.Timestamp(now))]
    m = m[m.index >= pd.Timestamp(t0)] if len(m) and m.index[0] < pd.Timestamp(t0) else m
    if not len(m):
        return None, None, None, None
    b = m.iloc[0]
    d = "up" if b["Close"] > b["Open"] else "down" if b["Close"] < b["Open"] else "flat"
    nxt = m1[m1.index > m.index[0]]
    return m.index[0], d, (nxt.index[0] if len(nxt) else None), (float(nxt["Open"].iloc[0]) if len(nxt) else None)


def rv5(m1_today, t0, prior_1m=None, m5=None):
    """(rv, basis) for the 5 one-minute bars starting at/after t0 (needs those 5 bars finished)."""
    t0 = pd.Timestamp(t0).ceil("1min")
    w = m1_today[(m1_today.index >= t0) & (m1_today.index < t0 + pd.Timedelta(minutes=5))] if m1_today is not None else []
    if len(w) < 5:
        return None, "the 5 bars after t0 are not all there"
    v = float(w["Volume"].sum())
    mins = [(t0 + pd.Timedelta(minutes=i)).strftime("%H:%M") for i in range(5)]
    if prior_1m is not None and len(prior_1m):
        per = []
        for d in sorted(set(prior_1m.index.date))[-14:]:
            g = prior_1m[prior_1m.index.date == d]
            x = g[g.index.strftime("%H:%M").isin(mins)]
            if len(x) == 5:
                per.append(float(x["Volume"].sum()))
        if len(per) >= 5:
            return round(v / max(np.mean(per), 1.0), 3), f"exact 1m minutes, {len(per)} prior sessions"
    if m5 is not None and len(m5):
        slot = t0.floor("5min").strftime("%H:%M")
        nxt = (t0.floor("5min") + pd.Timedelta(minutes=5)).strftime("%H:%M")
        frac = (t0 - t0.floor("5min")).total_seconds() / 300
        per = []
        for d in sorted({x for x in m5.index.date if x < t0.date()})[-14:]:
            g = m5[m5.index.date == d]
            a = g[g.index.strftime("%H:%M") == slot]["Volume"]
            b = g[g.index.strftime("%H:%M") == nxt]["Volume"]
            if len(a) and (len(b) or frac == 0):
                per.append(float(a.iloc[0]) * (1 - frac) + (float(b.iloc[0]) * frac if len(b) else 0.0))
        if len(per) >= 5:
            return round(v / max(np.mean(per), 1.0), 3), f"5-minute grid approximation, {len(per)} prior sessions"
    return None, "no prior-session volume for those minutes"


def moves(m1, entry_t, entry_px, direction, half_spread):
    out = {}
    sg = 1 if direction == "up" else -1 if direction == "down" else 0
    for h in HORIZONS:
        end = pd.Timestamp(entry_t) + pd.Timedelta(minutes=h)
        if end.strftime("%H:%M") > "16:00" or end.date() != pd.Timestamp(entry_t).date():
            out[str(h)] = None
            continue
        bar = m1[m1.index == end - pd.Timedelta(minutes=1)]
        if not len(bar):
            out[str(h)] = None
            continue
        raw = float(bar["Close"].iloc[0]) / entry_px - 1
        net = (sg * raw - (half_spread / entry_px if half_spread is not None else 0.0)) if sg else None
        out[str(h)] = {"raw": round(raw, 6), "signed": round(sg * raw, 6) if sg else None, "net": round(net, 6) if net is not None else None,
                       "net_has_spread": half_spread is not None}
    return out


def _fetch():
    import scanner
    return scanner._fetch


def _save(row):
    _schema()
    row = dict(row, updated=store.ts(), version=VERSION)
    row.setdefault("created", store.ts())
    cols = list(row)
    store.x(f"INSERT OR REPLACE INTO news_drift_events({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
            [json.dumps(row[c], default=str) if isinstance(row[c], (dict, list)) else row[c] for c in cols])


def rows(day=None, status=None, limit=500):
    _schema()
    sql, a = "SELECT * FROM news_drift_events WHERE 1=1", []
    if day:
        sql += " AND day=?"
        a.append(day)
    if status:
        sql += " AND status=?"
        a.append(status)
    out = store.q(sql + " ORDER BY t0 DESC LIMIT ?", tuple(a) + (int(limit),))
    for r in out:
        for k in ("moves", "data"):
            r[k] = json.loads(r[k]) if r.get(k) else None
    return out


def _get(cid):
    r = rows_by_id(cid)
    return r


def rows_by_id(cid):
    _schema()
    r = store.q("SELECT * FROM news_drift_events WHERE id=?", (cid,))
    if not r:
        return None
    r = r[0]
    for k in ("moves", "data"):
        r[k] = json.loads(r[k]) if r.get(k) else None
    return r


def discover(now):
    """New entry-eligible catalysts (as known now) -> PENDING rows. Returns the ids added."""
    import catalysts
    view = catalysts.view_as_of(catalysts.revisions_between(now - timedelta(hours=30), now), now)
    added = []
    for c in view.values():
        tks = c.get("tickers") or []
        if not catalysts.entry_eligible(c) or not tks or len(tks) > MAX_TICKERS or tks[0] in core.policy()["instruments"]:
            continue
        if rows_by_id(c["id"]):
            continue
        kt = known_time(c["id"], now)
        nt = _et(c.get("published_at")) or _et(c.get("first_detected_at"))
        if kt is None or nt is None:
            continue
        t0, note = anchor(max(nt, kt))
        _save({"id": c["id"], "day": t0.strftime("%Y-%m-%d"), "ticker": tks[0], "headline": str(c.get("headline"))[:300],
               "category": c.get("category"), "label": c.get("label"), "news_t": nt.isoformat(), "known_t": kt.isoformat(),
               "t0": t0.isoformat(), "anchored": note, "status": "PENDING", "reason": None,
               "data": {"rev": c.get("_rev"), "sources": [s.get("domain") for s in c.get("sources") or []][:5]}})
        added.append(c["id"])
    return added


def observe(r, now, quote_fn=None):
    """PENDING -> OBSERVED. As soon as the first post-news bar has finished (the entry bar is opening): the half spread
    from a quote taken then (only if within 2 min of the entry bar's open). Once t0 + 6 min has passed: rv5, the first
    bar's direction and the entry bar's open price."""
    t0 = _et(r["t0"])
    if now < t0 + timedelta(minutes=1):
        return False
    day = t0.date()
    f = _fetch()
    try:
        m1 = f.m1_today(r["ticker"], day)
    except Exception as e:
        m1 = None
        _state["last_error"] = f"bars {r['ticker']}: {type(e).__name__}"
    if m1 is None or not len(m1):
        if now - t0 > timedelta(hours=2):
            _save(dict(r, status="SKIPPED", reason="no 1m bars for the symbol"))
        return False
    m1 = m1[m1.index.date == day].between_time("09:30", "15:59")
    fb, d, et, epx = first_bar(m1, t0, now)
    if fb is None:
        return False
    entry_t = pd.Timestamp(fb) + pd.Timedelta(minutes=1)
    if r.get("half_spread") is None and not r.get("spread_quote_t"):
        late = (pd.Timestamp(now) - entry_t).total_seconds()
        hs, qt = None, None
        if late <= 120:
            try:
                qs, _ = (quote_fn or f.quotes)([r["ticker"]])
                q = (qs or {}).get(r["ticker"]) or {}
                if q.get("bid") and q.get("ask") and q["ask"] >= q["bid"]:
                    hs = round((q["ask"] - q["bid"]) / 2, 4)
                    qt = pd.Timestamp(q["quote_ms"], unit="ms", tz="UTC").tz_convert(core.ET).isoformat() if q.get("quote_ms") else store.ts()
            except Exception:
                pass
        r = dict(r, half_spread=hs, spread_quote_t=qt or f"none: first look {late:.0f}s after the entry bar opened")
        _save(r)
    if pd.Timestamp(now) < pd.Timestamp(t0).ceil("1min") + pd.Timedelta(minutes=5) or et is None:
        return False
    prior = None
    try:
        import lab
        prior = lab._hist_for(r["ticker"], day)
    except Exception:
        prior = None
    m5 = None
    if prior is None:
        try:
            end = datetime.combine(day, datetime.min.time(), core.ET)
            m5 = f.m5(r["ticker"], end - timedelta(days=30), end)
        except Exception:
            m5 = None
    rv, basis = rv5(m1, t0, prior, m5)
    hs = r.get("half_spread")
    _save(dict(r, status="OBSERVED", rv5=rv, rv5_basis=basis, first_bar_t=pd.Timestamp(fb).isoformat(), first_bar_dir=d,
               entry_t=pd.Timestamp(et).isoformat(), entry_px=epx,
               reason=None if hs is not None else "half spread unknown: no quote within 2 min of the entry bar's open"))
    return True


def resolve(r, now):
    """OBSERVED -> RESOLVED after the close: the +15/30/60/120-minute moves."""
    if now.strftime("%H:%M") < "16:05" and now.date() == _et(r["t0"]).date():
        return False
    day = _et(r["t0"]).date()
    try:
        m1 = _fetch().m1_today(r["ticker"], day)
    except Exception:
        return False
    if m1 is None or not len(m1):
        return False
    m1 = m1[m1.index.date == day].between_time("09:30", "15:59")
    mv = moves(m1, r["entry_t"], r["entry_px"], r["first_bar_dir"], r["half_spread"])
    _save(dict(r, status="RESOLVED", moves=mv))
    return True


def step(now=None):
    """Called from the v4 stock worker (research priority): discover, observe, resolve. Never trades."""
    now = now or core.now_et()
    import schwab
    with schwab.priority("research"):
        try:
            discover(now)
        except Exception as e:
            _state["last_error"] = f"discover: {type(e).__name__}: {e}"[:200]
        for r in rows(status="PENDING", limit=50):
            try:
                observe(r, now)
            except Exception as e:
                _state["last_error"] = f"observe {r['id']}: {type(e).__name__}: {e}"[:200]
        if now.strftime("%H:%M") >= "16:05":
            for r in rows(status="OBSERVED", limit=100):
                try:
                    resolve(r, now)
                except Exception as e:
                    _state["last_error"] = f"resolve {r['id']}: {type(e).__name__}: {e}"[:200]


def summary(since=None):
    rs = [r for r in rows(status="RESOLVED", limit=5000) if not since or r["day"] >= since]
    out = {"events": len(rs), "version": VERSION, "by_horizon": {}}
    for h in HORIZONS:
        net = [r["moves"][str(h)]["net"] for r in rs if r.get("moves") and r["moves"].get(str(h)) and r["moves"][str(h)]["net"] is not None]
        out["by_horizon"][str(h)] = {"n": len(net), "mean_net": round(float(np.mean(net)), 6) if net else None,
                                     "hit_rate": round(float(np.mean([x > 0 for x in net])), 3) if net else None}
    out["note"] = ("Event study only (no trades). Net = the move in the first bar's direction minus the half spread at entry. "
                   "The holding time is chosen on the first 2/3 of events and tested on the last 1/3; nothing is promoted here.")
    return out
