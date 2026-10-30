"""alerts.py - live notifications: setups and move alerts (code, free) + news from Chart's news-scan routine.

Every alert becomes an 'alert' event (desk feed + browser pop-up + sound) and, if NTFY_TOPIC is set, a phone push
through the free ntfy app. Alerts are heads-ups only: they never trade and never change a plan.
"""
from datetime import datetime
import hashlib
import json
import os
import re
import threading
import urllib.request

import core
import store

KINDS = ("setups", "moves", "news", "scanner", "movers", "mytrades")
NEWS_SCHEMA = """CREATE TABLE IF NOT EXISTS news(id TEXT PRIMARY KEY, ts TEXT, at TEXT, headline TEXT, source TEXT,
  url TEXT, tickers TEXT, impact TEXT, direction TEXT, why TEXT)"""


def settings():
    s = store.kv_get("alert_settings") or {}
    return {k: s.get(k, True) for k in KINDS} | {"phone": bool(os.environ.get("NTFY_TOPIC"))}


def set_settings(d):
    cur = store.kv_get("alert_settings") or {}
    cur.update({k: bool(v) for k, v in d.items() if k in KINDS})
    store.kv_set("alert_settings", cur)
    return settings()


def _push(title, body, priority):
    topic = os.environ.get("NTFY_TOPIC", "")
    if not re.match(r"^[A-Za-z0-9_-]{8,64}$", topic):
        return

    def go():
        try:
            req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode()[:1000], method="POST",
                                         headers={"Title": title[:120].encode("ascii", "ignore").decode(),
                                                  "Priority": priority, "Tags": "chart_with_upwards_trend"})
            urllib.request.urlopen(req, timeout=8).read()
        except Exception:
            pass
    threading.Thread(target=go, daemon=True).start()


def alert(kind, title, body, ref, level="normal"):
    """kind in KINDS. ref de-duplicates (one alert per setup bar / candle pair / headline)."""
    if not settings().get(kind, True):
        return False
    k = f"alert:{ref}"
    if store.kv_get(k):
        return False
    store.kv_set(k, True)
    store.event("alert", f"{title} | {body}", "", ref, {"kind": kind, "level": level})
    _push(title, body, "high" if level == "high" else "default")
    return True


# ---------------- setups (called by the paper engine scan) ----------------
def setup(ticker, st, grade, decision, reason, brief=None):
    if grade not in ("A", "B"):
        return False
    side = "calls" if st["side"] == "C" else "puts"
    body = (brief + f" | {st['note']}") if brief else (f"{st['note']} | level {st['level']:.2f}, invalid {st['invalidation']:.2f} | paper: {decision}" + (f" ({reason})" if reason else ""))
    return alert("setups", f"{ticker} {st['family'].replace('_', ' ')} {side} ({grade})", body,
                 f"setup:{ticker}:{st['family']}:{st['side']}:{st['bar']}", "high" if grade == "A" else "normal")


# ---------------- move alert (Playbook: 2 heavy 5m candles in a row) ----------------
def move_check(ticker, b5):
    """Two completed 5m candles in a row, same direction, strong bodies (>= 60% of range), volume >= 1.5x
    the prior 20-candle average."""
    if b5 is None or len(b5) < 22:
        return False
    a, b = b5.iloc[-2], b5.iloc[-1]
    vavg = float(b5["Volume"].iloc[-22:-2].mean() or 0)
    if vavg <= 0:
        return False

    def strong(c, up):
        rng = float(c["High"] - c["Low"])
        body = float(c["Close"] - c["Open"])
        return rng > 0 and (body / rng >= 0.6 if up else -body / rng >= 0.6) and float(c["Volume"]) >= 1.5 * vavg
    last = store.kv_get(f"move_last:{ticker}")
    if last and (b5.index[-1].to_pydatetime() - datetime.fromisoformat(last)).total_seconds() < 15 * 60:
        return False  # one move alert per ticker per 15 minutes, even in a strong trend
    for up in (True, False):
        if strong(a, up) and strong(b, up):
            store.kv_set(f"move_last:{ticker}", b5.index[-1].isoformat())
            move = float(b["Close"] - a["Open"])
            return alert("moves", f"MOVE ALERT {ticker} {'UP' if up else 'DOWN'}",
                         f"2 heavy 5m candles, {move:+.2f} since {b5.index[-2].strftime('%H:%M')}, volume {float(b['Volume']) / vavg:.1f}x",
                         f"move:{ticker}:{b5.index[-1].isoformat()}", "high")
    return False


# ---------------- news (posted by Chart's news-scan routine) ----------------
def _nid(headline):
    norm = re.sub(r"[^a-z0-9 ]", "", headline.lower())
    norm = " ".join(w for w in norm.split() if len(w) > 2)[:140]
    return hashlib.sha1(norm.encode()).hexdigest()[:16]


def add_news(items):
    store.x(NEWS_SCHEMA)
    added = []
    for it in (items or [])[:20]:
        h = str(it.get("headline", "")).strip()[:300]
        if len(h) < 8:
            continue
        nid = _nid(h)
        if store.q("SELECT id FROM news WHERE id=?", (nid,)):
            continue
        impact = str(it.get("impact", "medium")).lower()
        impact = impact if impact in ("high", "medium", "low") else "medium"
        direction = str(it.get("direction", "unclear")).lower()[:12]
        tickers = ",".join(t for t in re.findall(r"[A-Z]{1,5}", str(it.get("tickers", "")).upper()))[:60]
        row = (nid, store.ts(), str(it.get("time", ""))[:20], h, str(it.get("source", ""))[:80], str(it.get("url", ""))[:300],
               tickers, impact, direction, str(it.get("why", ""))[:300])
        store.x("INSERT INTO news(id,ts,at,headline,source,url,tickers,impact,direction,why) VALUES(?,?,?,?,?,?,?,?,?,?)", row)
        added.append(nid)
        if impact in ("high", "medium"):
            tag = {"bullish": "▲", "bearish": "▼"}.get(direction, "•")
            alert("news", f"NEWS {tag} {h[:90]}", f"{it.get('source', '')}{' | ' + tickers if tickers else ''}{' | ' + str(it.get('why'))[:160] if it.get('why') else ''}",
                  f"news:{nid}", "high" if impact == "high" else "normal")
    return added


def recent_news(limit=20):
    store.x(NEWS_SCHEMA)
    return store.q("SELECT at, ts, headline, source, url, tickers, impact, direction, why FROM news ORDER BY ts DESC LIMIT ?", (limit,))
