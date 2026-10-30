"""lab.py - v3.4 strategy lab: every strategy on every stock, every day, measured. Paper only: nothing here can send an
order anywhere. Real trades are Nick's, by hand, in Robinhood.

1. SIGNAL TAPE. Every detector runs on every newly FINISHED 1m bar of every symbol on the desk's list (the setups-board
   universe, SPY/QQQ, the watchlist, the stocks in play), in time order, so a signal only ever sees bars up to its own
   bar. Each signal is recorded once with its conditions at that moment (RVOL, trend, MACD, distance from VWAP, SPY,
   relative strength, gap, liquidity, sector, earnings phase and the X read KNOWN at that time). Detectors:
     * the setups board's rules (ORB 5/15/30 break / retest / failed, pre-market and prior-day levels, VWAP reclaim and
       rejection, momentum continuation, trend pullback);
     * the v3 rules (ORB break/retest, failed break, PDH/PDL retest, VWAP reclaim, VWAP + MACD) on every stock;
     * the ORB15 base and first-retest study definitions (research.py);
     * the MACD video rule (5m MACD crossing its signal beyond the zero line, on the 200 EMA's side, 2R);
     * the noise band (half-hour checks) on every stock with enough history.
   After the session, each in-window signal (decided 09:45-15:15) gets a uniform stock outcome in R: entered at the
   next bar's open, stop just beyond its invalidation (0.05 x daily ATR), 2R target, flat at 15:25, $0.04/share
   costs, the stop first on an ambiguous bar. Plus the move at 5 / 15 / 30 minutes and the mean of matched random
   entries (same stock, day, side, window, stop distance, target and costs; fixed seed per signal).

2. LAB PAPER LEDGERS (lab_*): one per strategy family, so one strategy can't crowd another out. A signal seen within
   max_signal_age_s of its bar can be paper traded: inside 09:45-15:15, through the shared anti-chasing gate (scoped
   to the ledger), a contract check, strict fills (paper exec2), 1 contract, the 20% planned premium line. Caps per
   ledger and in total, and a request budget so the lab never crowds the Schwab rate limit.

3. REPORT (what_works): strategy x stock, x stock group, x condition, with sample size, win rate, average R, the
   matched random entries and the edge over them with a session-clustered 95% interval, split into the earlier and
   later half of the sessions. Under min_n signals = "too few". No combination is promoted by this report.

Also: a daily 1m bar archive (journal/bars/<day>/<ticker>.csv.gz), backfilled from the morning history pull, so the
data keeps growing past what Schwab keeps.
"""
import gzip
import hashlib
import io
import json
import threading
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import core
import indicators as I
import matched_benchmarks as MB
import paper
import store

VERSION = "2026-10-30.v3.4-lab1"          # 3.4.1: whole-step time budget (signal rules unchanged)
ET = core.ET
ARCHIVE = core.HERE / "journal" / "bars"          # tests point this at a temporary folder
COLS = ["Open", "High", "Low", "Close", "Volume"]

DEFAULTS = {"enabled": True, "tape": True, "paper": True,
            "history_days": 30, "history_sessions": 16, "history_calls_per_min": 30,
            "max_bars_per_step": 40, "step_budget_s": 4, "v3_stocks": True, "macd_video_min_bars": 1000,
            "window": ["09:45", "15:15"], "max_signal_age_s": 150, "episode_gap_min": 10,
            "max_open_per_ledger": 2, "max_ideas_per_ledger": 6, "max_open_total": 20, "attempts_per_min": 8, "qty": 1,
            "target_r": 2.0, "flat": "15:25", "cost_per_share": 0.04, "stop_buffer_atr": 0.05,
            "controls_paths": 20, "resolve_after": "15:31", "archive_after": "16:06", "min_n": 30,
            "max_dte": 10, "limit_cents_over_ask": 0.03}

FAMILIES = {
    "board_orb_break": {"ledger": "lab_orb_break", "label": "ORB 5/15/30 break", "source": "setups board"},
    "board_orb_retest": {"ledger": "lab_orb_retest", "label": "ORB retest holding", "source": "setups board"},
    "board_orb_failed": {"ledger": "lab_orb_failed", "label": "Failed ORB, reversal confirmed", "source": "setups board"},
    "board_level_break": {"ledger": "lab_lvl_break", "label": "Pre-market / prior-day level break", "source": "setups board"},
    "board_level_retest": {"ledger": "lab_lvl_retest", "label": "Level retest holding", "source": "setups board"},
    "board_vwap_reclaim": {"ledger": "lab_vwap_reclaim", "label": "VWAP reclaim", "source": "setups board"},
    "board_vwap_reject": {"ledger": "lab_vwap_reject", "label": "VWAP rejection", "source": "setups board"},
    "board_momo": {"ledger": "lab_momo", "label": "Momentum continuation", "source": "setups board"},
    "board_pullback": {"ledger": "lab_pullback", "label": "Pullback in a trend", "source": "setups board"},
    "v3": {"ledger": "lab_v3", "label": "v3 rules (ORB, failed break, PDH/PDL, VWAP reclaim)", "source": "v3 rules",
           "main_has_own": True},
    "v3_vwap_macd": {"ledger": "lab_vwap_macd", "label": "v3 VWAP + MACD", "source": "v3 rules", "main_has_own": True},
    "orb15_base": {"ledger": "lab_orb15", "label": "ORB15 first completed break", "source": "study definition"},
    "orb15_retest": {"ledger": "lab_orb15_rt", "label": "ORB15 first retest", "source": "study definition"},
    "macd_video": {"ledger": "lab_macd_video", "label": "MACD video (5m cross beyond zero, 200 EMA side, 2R)",
                   "source": "video, causal adaptation"},
    "noise": {"ledger": "lab_noise", "label": "Noise band (half-hour checks)", "source": "Zarattini/Aziz/Barbon",
              "main_has_own": True},
}
LEDGER_OF = {f: v["ledger"] for f, v in FAMILIES.items()}
CONDITIONS = {"time_window": "Time of day", "rvol": "RVOL (time of day)", "trend": "5m trend (ADX >= 25, efficiency >= 0.4)",
              "macd2": "2m MACD histogram", "ema200": "5m 200 EMA", "vwap_dist": "Distance from VWAP", "spy": "SPY since the open",
              "gap": "Opening gap", "price": "Price", "liquidity": "Average volume", "group": "Stock group", "earnings": "Earnings",
              "x_lean": "X trader lean vs the trade", "x_label": "Best X / news label", "x_attention": "X attention",
              "extended": "Extended (setups board)", "qualifies": "Qualifies on the board"}
SCHEMA = ["""CREATE TABLE IF NOT EXISTS lab_tape(id TEXT PRIMARY KEY, day TEXT, ticker TEXT, family TEXT, setup TEXT, side TEXT,
            signal_bar TEXT, bar_end TEXT, observed_at TEXT, live INTEGER, level REAL, invalidation REAL, use_level INTEGER,
            price REAL, atr REAL, conditions TEXT, status TEXT, entry REAL, stop_dist REAL, r REAL, r_5m REAL, r_15m REAL,
            r_30m REAL, exit_why TEXT, ctl_r REAL, ctl_n INTEGER, resolved_at TEXT, paper TEXT, version TEXT)""",
          "CREATE INDEX IF NOT EXISTS lab_tape_day ON lab_tape(day, status)"]

_lock = threading.RLock()
_state = {"thread": None, "stop": False, "status": "idle", "last_error": None, "day": None, "hist": {}, "hist_at": {},
          "hist_tokens": 0.0, "hist_t": None, "last_bar": {}, "ep": {}, "noise_prev": {}, "att_tokens": 0.0, "att_t": None,
          "saved_at": 0.0, "counts": {}, "archived": None, "resolved_at": None, "step_s": None, "cats": None, "cats_at": 0.0}
_hist_fetch = None


def cfg():
    c = dict(DEFAULTS)
    c.update(core.policy().get("lab") or {})
    c.update(store.kv_get("lab_settings") or {})
    return c


def _schema():
    for s in SCHEMA:
        store.x(s)


def use(fetcher):
    """Tests: replace the history fetcher (object with .history(ticker, start, end) -> 1m DataFrame)."""
    global _hist_fetch
    _hist_fetch = fetcher


def _fetch():
    import scanner
    return scanner._fetch


def _history_fetch(t, start, end):
    if _hist_fetch is not None:
        return _hist_fetch.history(t, start, end)
    f = _fetch()
    if hasattr(f, "history"):
        return f.history(t, start, end)
    import schwab
    return schwab.bars_range(t, start, end, 1, extended=False)


def tickers():
    import scanner_setups as SS
    return SS.tickers()


def _groups():
    try:
        d = json.loads((core.HERE / "config" / "sectors.json").read_text())
        return d.get("groups") or {}, set(d.get("etfs") or [])
    except (OSError, ValueError):
        return {}, set()


# ================================================================ bars: today, history, archive
def _hm(ts):
    return ts.strftime("%H:%M")


def _rth(df):
    if df is None or not len(df):
        return df
    return df.between_time("09:30", "15:59")


def _today_bars(t, now):
    """Today's FINISHED 1m bars (pre-market included): the freshest of the setups board's rotation cache and the live
    pipeline (stream / REST for SPY/QQQ, the chart ticker and open trades)."""
    import marketdata
    import scanner_setups as SS
    day = now.date()
    best = None
    hit = SS._state["bars"].get(t)
    if hit and hit[1] is not None and len(hit[1]):
        b = hit[1]
        best = b[b.index.date == day][COLS]
    with marketdata._lock:
        full = marketdata._bars.get(t)
        full = full[COLS].copy() if full is not None and len(full) else None
    if full is not None:
        md = full[full.index.date == day]
        if len(md) and (best is None or not len(best) or md.index[-1] > best.index[-1]):
            best = md
    if best is None or not len(best):
        return None
    return best[best.index + pd.Timedelta(minutes=1) <= pd.Timestamp(now)].sort_index()


def _hist_for(t, day):
    """Prior regular sessions (oldest first) for indicators that continue across days. SPY/QQQ come from the live
    pipeline's deep history; other symbols from the morning history pull."""
    import marketdata
    if t in core.policy()["instruments"]:
        with marketdata._lock:
            full = marketdata._bars.get(t)
            full = full[COLS].copy() if full is not None and len(full) else None
        if full is not None:
            r = _rth(full[full.index.date < day])
            return r if len(r) else None
    return _state["hist"].get(t)


def archive_path(day, t):
    return ARCHIVE / str(day) / f"{t}.csv.gz"


def archive_read(day, t):
    p = archive_path(day, t)
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p, compression="gzip")
    except Exception:
        return None
    df.index = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(ET)
    return df[COLS].sort_index()


def archive_write(day, t, df):
    """Merge into the day's file (new rows win on the same minute). Writes atomically. Returns rows stored."""
    if df is None or not len(df):
        return 0
    df = df[df.index.date == day][COLS]
    if not len(df):
        return 0
    old = archive_read(day, t)
    if old is not None and len(old):
        df = pd.concat([old[~old.index.isin(df.index)], df]).sort_index()
    p = archive_path(day, t)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out.insert(0, "ts", out.index.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
        g.write(out.to_csv(index=False).encode())
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(buf.getvalue())
    tmp.replace(p)
    return len(df)


def archive_days():
    root = ARCHIVE
    if not root.exists():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir())


def _pull_history(now, c):
    """Prior sessions for every symbol, once per day, within a per-minute budget (they share Schwab's limit with
    everything else). Also back-fills the archive with any day that is missing or incomplete there."""
    day = now.date()
    t_now = time.time()
    last = _state["hist_t"] or t_now - 5
    _state["hist_t"] = t_now
    _state["hist_tokens"] = min(_state["hist_tokens"] + (t_now - last) * c["history_calls_per_min"] / 60, c["history_calls_per_min"])
    todo = [t for t in tickers() if t not in core.policy()["instruments"] and _state["hist_at"].get(t) != str(day)]
    pulled = 0
    while todo and _state["hist_tokens"] >= 1:
        t = todo.pop(0)
        _state["hist_tokens"] -= 1
        _state["hist_at"][t] = str(day)
        start = datetime.combine(day - timedelta(days=c["history_days"]), datetime.min.time(), ET)
        end = datetime.combine(day, datetime.min.time(), ET)
        try:
            df = _history_fetch(t, start, end)
        except Exception as e:
            _state["last_error"] = f"history {t}: {type(e).__name__}"
            df = None
        if df is None or not len(df):
            continue
        df = df.sort_index()
        df = df[df.index.date < day]
        r = _rth(df)
        sess = sorted(set(r.index.date))
        for d in sess:                                      # back-fill missing or partial archive days (RTH only)
            g = r[r.index.date == d]
            old = archive_read(d, t)
            if old is None or len(_rth(old)) < len(g):
                archive_write(d, t, g)
        keep = sess[-c["history_sessions"]:]
        with _lock:
            _state["hist"][t] = r[np.isin(r.index.date, keep)][COLS].astype(float)
        pulled += 1
    return pulled


def archive_today(now):
    """After the close: today's bars (pre-market included) for every symbol the desk has, into the archive."""
    day = now.date()
    n = 0
    for t in tickers():
        m1 = _today_bars(t, now)
        if m1 is not None and len(m1):
            n += 1 if archive_write(day, t, m1) else 0
    _state["archived"] = str(day)
    store.kv_set(f"lab_archived:{day}", {"symbols": n, "at": store.ts()})
    return n


# ================================================================ detectors (pure, on finished bars only)
def board_family(row):
    k, st = row.get("kind"), row.get("state")
    if k == "orb":
        return {"CLOSED BEYOND": "board_orb_break", "RETEST HOLDING": "board_orb_retest",
                "REVERSAL CONFIRMED": "board_orb_failed"}.get(st)
    if k in ("pm", "pd"):
        return {"CLOSED BEYOND": "board_level_break", "RETEST HOLDING": "board_level_retest"}.get(st)
    if k == "vwap":
        return {"RECLAIMED": "board_vwap_reclaim", "REJECTED": "board_vwap_reject"}.get(st)
    if k == "momo":
        return {"CONTINUATION": "board_momo", "PULLBACK": "board_pullback"}.get(st)
    return None


def macd_video_signal(b5_close, min_bars=1000):
    """The video rule on FINISHED 5m closes (continuous across sessions): MACD(12,26,9) crosses its signal while both
    are below zero and the close is above the 200 EMA -> long; mirrored for shorts. Returns (side, ema200, why) or
    (None, None, why). Stop: the 200 EMA at the signal, frozen."""
    if b5_close is None or len(b5_close) < min_bars:
        return None, None, f"warming up ({0 if b5_close is None else len(b5_close)} of {min_bars} 5m bars)"
    e200 = float(I.ema(b5_close, 200).iloc[-1])
    M, S, _ = I.macd(b5_close, 12, 26, 9)
    m0, m1, s0, s1 = float(M.iloc[-2]), float(M.iloc[-1]), float(S.iloc[-2]), float(S.iloc[-1])
    c = float(b5_close.iloc[-1])
    if m0 <= s0 and m1 > s1 and m1 < 0 and s1 < 0 and c > e200:
        return "C", e200, "MACD crossed up below zero, close above the 200 EMA"
    if m0 >= s0 and m1 < s1 and m1 > 0 and s1 > 0 and c < e200:
        return "P", e200, "MACD crossed down above zero, close below the 200 EMA"
    return None, e200, "no cross"


def _hist_agg(hist, minutes):
    """Complete N-minute bars of the prior sessions, computed once per history frame (they never change)."""
    if hist is None or not len(hist):
        return None
    key = (id(hist), len(hist), minutes)
    cache = _state.setdefault("agg", {})
    hit = cache.get(key)
    if hit is not None:
        return hit
    parts = []
    for d in sorted(set(hist.index.date)):
        g = hist[hist.index.date == d]
        bars, done = I.aggregate(g, minutes)
        parts.append(bars[done.values] if len(done) else bars)
    out = pd.concat(parts) if parts else None
    if len(cache) > 600:
        cache.clear()
    cache[key] = out
    return out


def _today_agg(rth_k, minutes, b):
    if rth_k is None or not len(rth_k):
        return None
    bars, done = I.aggregate(rth_k, minutes, b)
    return bars[done.values] if len(done) else bars


def _b5(hist, rth_k, b):
    parts = [x for x in (_hist_agg(hist, 5), _today_agg(rth_k, 5, b)) if x is not None and len(x)]
    return pd.concat(parts) if parts else None


def _b2(hist, rth_k, b):
    parts = [x for x in (_hist_agg(hist, 2), _today_agg(rth_k, 2, b)) if x is not None and len(x)]
    return pd.concat(parts) if parts else None


def _recent(hist, sessions=3):
    if hist is None or not len(hist):
        return hist
    keep = sorted(set(hist.index.date))[-sessions:]
    return hist[np.isin(hist.index.date, keep)]


# ================================================================ conditions (as known at the signal)
def _bucket(v, edges, labels):
    if v is None or v != v:
        return "unknown"
    for e, lab in zip(edges, labels):
        if v < e:
            return lab
    return labels[-1]


def _xcats(now):
    """Catalysts by ticker (DB read, cached 60 s). Only items FIRST DETECTED at or before a signal are used for it."""
    if _state["cats"] is not None and time.time() - _state["cats_at"] < 60:
        return _state["cats"]
    out = {}
    try:
        import catalysts
        for c in catalysts._all((now - timedelta(days=2)).isoformat(timespec="seconds")):
            for t in c.get("tickers") or []:
                out.setdefault(t, []).append(c)
    except Exception:
        out = {}
    _state["cats"], _state["cats_at"] = out, time.time()
    return out


def _x_read(t, bar_end, cats):
    best = None
    for c in cats.get(t, []):
        fd = c.get("first_detected_at")
        if not fd or fd > bar_end.isoformat(timespec="seconds"):
            continue                                        # not known yet at the signal
        if (bar_end - datetime.fromisoformat(fd)).total_seconds() > 24 * 3600:
            continue
        if best is None or fd > best["first_detected_at"]:
            best = c
    return best


def neutral_features(t, mk, b, bar_end, base, bench_k, hist, info=None):
    """Side-free features at the signal bar (computed once per ticker-bar)."""
    base = base or {}
    rk = mk[(mk.index.date == b.date())]
    rk = _rth(rk)
    f = {"hm": _hm(bar_end), "close": float(rk["Close"].iloc[-1]) if len(rk) else None}
    prev, atr = base.get("prev_close"), base.get("atr14")
    f["atr14"] = atr
    if len(rk):
        o = float(rk["Open"].iloc[0])
        f["day_pct"] = round((f["close"] / prev - 1) * 100, 2) if prev else None
        f["gap_pct"] = round((o / prev - 1) * 100, 2) if prev else None
        vw = I.session_vwap(rk)
        f["vwap"] = float(vw.iloc[-1]) if len(vw) and vw.iloc[-1] == vw.iloc[-1] else None
        f["ret_open"] = (f["close"] / o - 1) * 100
    if info and info.get("rvol") is not None:
        f["rvol"] = info.get("rvol")
    else:
        try:
            import scanner_setups as SS
            f["rvol"] = SS.tod_rvol(rk, base, bar_end)[0]
        except Exception:
            f["rvol"] = None
    if bench_k is not None and len(bench_k):
        br = _rth(bench_k[bench_k.index.date == b.date()])
        if br is not None and len(br):
            f["spy_ret"] = (float(br["Close"].iloc[-1]) / float(br["Open"].iloc[0]) - 1) * 100
    try:
        b5 = _b5(hist, rk, b)
        if b5 is not None and len(b5) >= 30:
            adx, pdi, mdi = I.adx_di(b5, 14)
            f["adx"], f["pdi"], f["mdi"] = I.last(adx), I.last(pdi), I.last(mdi)
            cl = b5["Close"]
            if len(cl) >= 13:
                ch = cl.diff().iloc[-12:]
                f["eff"] = abs(float(cl.iloc[-1] - cl.iloc[-13])) / float(ch.abs().sum()) if float(ch.abs().sum()) > 0 else None
            if len(cl) >= 200:
                f["ema200_5m"] = float(I.ema(cl, 200).iloc[-1])
            M, S, _ = I.macd(cl, 12, 26, 9)
            f["macd5"] = float(M.iloc[-1])
        b2 = _b2(hist, rk, b)
        if b2 is not None and len(b2) >= 35:
            M2, S2, H2 = I.macd(b2["Close"], 12, 26, 9)
            f["hist2"] = float(H2.iloc[-1])
    except Exception:
        pass
    f["avg_vol14"] = base.get("avg_vol14")
    return f


def conditions(t, side, nf, bar_end, cats, extra=None):
    """Side-aware condition labels for the report, plus the raw numbers."""
    up = side == "C"
    sg = 1 if up else -1
    groups, etfs = _groups()
    hm = nf.get("hm") or _hm(bar_end)
    c = {"time_window": "before 09:45" if hm < "09:45" else "09:45-11:30" if hm <= "11:30" else "11:30-14:00" if hm <= "14:00"
         else "14:00-15:15" if hm <= "15:15" else "after 15:15"}
    c["rvol"] = _bucket(nf.get("rvol"), [1, 2], ["under 1x", "1-2x", "2x or more"])
    adx, eff = nf.get("adx"), nf.get("eff")
    if adx is None:
        c["trend"] = "unknown"
    else:
        aligned = (nf.get("pdi") or 0) > (nf.get("mdi") or 0) if up else (nf.get("mdi") or 0) > (nf.get("pdi") or 0)
        strong = adx >= 25 and (eff or 0) >= 0.4
        c["trend"] = ("strong trend with the trade" if strong and aligned else "strong trend against the trade" if strong
                      else "no strong trend")
    h2 = nf.get("hist2")
    c["macd2"] = "unknown" if h2 is None else ("with the trade" if h2 * sg > 0 else "against the trade")
    e200, cl = nf.get("ema200_5m"), nf.get("close")
    c["ema200"] = "unknown" if e200 is None or cl is None else ("on the trade's side" if (cl - e200) * sg > 0 else "on the other side")
    vw, atr = nf.get("vwap"), nf.get("atr14")
    if vw is None or not atr or cl is None:
        c["vwap_dist"] = "unknown"
    else:
        d = (cl - vw) / atr * sg
        c["vwap_dist"] = _bucket(d, [0, 0.25, 0.75], ["wrong side of VWAP", "0-0.25 ATR", "0.25-0.75 ATR", "over 0.75 ATR"])
    sr = nf.get("spy_ret")
    c["spy"] = "unknown" if sr is None else ("SPY flat (under 0.1%)" if abs(sr) < 0.1 else
                                             "SPY with the trade" if sr * sg > 0 else "SPY against the trade")
    gp = nf.get("gap_pct")
    c["gap"] = "unknown" if gp is None else ("gap with the trade (over 1%)" if gp * sg > 1 else
                                             "gap against the trade (over 1%)" if gp * sg < -1 else "no big gap")
    c["price"] = _bucket(cl, [20, 50, 200], ["under $20", "$20-50", "$50-200", "$200+"])
    c["liquidity"] = _bucket(nf.get("avg_vol14"), [2e6, 10e6], ["under 2M shares/day", "2-10M", "10M+"])
    c["group"] = groups.get(t, "Other")
    c["etf"] = t in etfs
    er = _earn(t, bar_end)
    c["earnings"] = er
    x = _x_read(t, bar_end, cats)
    if not x:
        c.update(x_lean="no X read", x_label="none", x_attention="no X read")
    else:
        lean = (((x.get("sentiment") or {}).get("trader") or {}).get("lean") or "").lower()
        c["x_lean"] = ("X agrees" if (lean == "bullish" and up) or (lean == "bearish" and not up) else
                       "X disagrees" if lean in ("bullish", "bearish") else "X mixed or neutral" if lean else "X lean not given")
        c["x_label"] = x.get("label") or "none"
        at = x.get("attention") or {}
        c["x_attention"] = "rising" if at.get("accelerating") else "not rising" if at else "not measured"
        c["x_id"] = x.get("id")
        c["x_age_min"] = round((bar_end - datetime.fromisoformat(x["first_detected_at"])).total_seconds() / 60)
    if extra:
        c.update(extra)
    c["n"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in nf.items() if k != "hm"}
    return c


def _earn(t, bar_end):
    try:
        import earnings
        store.x(earnings.SCHEMA)
        d0 = (bar_end.date() - timedelta(days=3)).isoformat()
        rows = store.q("SELECT data FROM earnings WHERE ticker=? AND date>=? ORDER BY date LIMIT 1", (t, d0))
        if not rows:
            return "no report near"
        rec = json.loads(rows[0]["data"])
        ph = earnings.phase(rec, bar_end)
        days = (datetime.fromisoformat(rec["date"]).date() - bar_end.date()).days
        if ph == "PRE":
            return "report within 3 days" if days <= 3 else "no report near"
        if ph in ("RELEASE", "CALL", "NEXT SESSION", "RELEASE?"):
            return "just reported"
        return "no report near"
    except Exception:
        return "unknown"


# ================================================================ the tape
def _sig_id(day, t, family, setup, side, b):
    return f"{day}|{t}|{family}|{setup}|{side}|{b.strftime('%H%M')}"


def _record(t, family, setup, side, b, bar_end, level, inval, use_level, nf, cats, now, extra=None):
    c = cfg()
    day = str(b.date())
    sid = _sig_id(day, t, family, setup, side, b)
    if store.q("SELECT id FROM lab_tape WHERE id=?", (sid,)):
        return None
    cond = conditions(t, side, nf, bar_end, cats, extra)
    live = (pd.Timestamp(now) - pd.Timestamp(bar_end)).total_seconds() <= c["max_signal_age_s"]
    store.x("INSERT OR IGNORE INTO lab_tape(id, day, ticker, family, setup, side, signal_bar, bar_end, observed_at, live, level, "
            "invalidation, use_level, price, atr, conditions, status, version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, day, t, family, setup, side, b.isoformat(), pd.Timestamp(bar_end).isoformat(), now.isoformat(timespec="seconds"),
             1 if live else 0, None if level is None else round(float(level), 4), None if inval is None else round(float(inval), 4),
             1 if use_level else 0, nf.get("close"), nf.get("atr14"), json.dumps(cond, default=str), "OPEN", VERSION))
    cnt = _state["counts"].setdefault(family, {"signals": 0, "live": 0})
    cnt["signals"] += 1
    cnt["live"] += 1 if live else 0
    return {"id": sid, "day": day, "ticker": t, "family": family, "setup": setup, "side": side, "b": b, "bar_end": pd.Timestamp(bar_end),
            "level": level, "invalidation": inval, "use_level": use_level, "close": nf.get("close"), "atr14": nf.get("atr14"),
            "live": live, "conditions": cond}


def _episode_new(key, b, gap_min):
    last = _state["ep"].get(key)
    _state["ep"][key] = b.isoformat()
    return last is None or (b - pd.Timestamp(last)).total_seconds() > gap_min * 60


def process_bar(t, mk, b, now, ctx):
    """Every detector on one finished bar (opened at b) of ticker t, using bars up to b only. Returns new signals."""
    import scanner_setups as SS
    c = ctx["cfg"]
    bar_end = b + pd.Timedelta(minutes=1)
    day = b.date()
    base = (ctx.get("base") or {}).get(t)
    bench = ctx.get("bench")
    bench_k = bench[bench.index <= b] if bench is not None and len(bench) else None
    hist = ctx["hist"].get(t)
    rk = _rth(mk[mk.index.date == day])
    out, nf = [], None

    def feats(info=None):
        nonlocal nf
        if nf is None:
            nf = neutral_features(t, mk, b, bar_end, base, bench_k, hist, info)
        return nf

    # --- setups-board rules (episodes: one signal per setup/side/state until it disappears for episode_gap_min)
    if base:
        try:
            info, setups = SS.evaluate(t, mk, base, None, bench_k, bar_end.to_pydatetime())
            rows = SS.rows_for(info, setups, {"ok": True})
        except Exception as e:
            rows, info = [], None
            _state["last_error"] = f"board {t}: {type(e).__name__}: {e}"[:200]
        for r in rows:
            fam = board_family(r)
            if not fam:
                continue
            side = "C" if r["direction"] == "long" else "P"
            if not _episode_new(f"{t}|{r['setup']}|{side}|{r['state']}", b, c["episode_gap_min"]):
                continue
            use_level = fam not in ("board_orb_failed", "board_momo")
            s = _record(t, fam, r["setup"], side, b, bar_end, r.get("level"), r.get("invalidation"), use_level, feats(info),
                        ctx["cats"], now, {"score": r.get("score"), "qualifies": "yes" if r.get("qualifies") else "no",
                                           "extended": "yes" if r.get("extended") else "no", "board_state": r["state"]})
            if s:
                out.append(s)
    # --- v3 rules on this symbol (namespaced state, no events)
    v3_bar = bar_end.minute % 2 == 0 or bar_end.minute % 5 == 0      # every v3 detector waits for a finished 2m or 5m bar
    if c["v3_stocks"] and v3_bar and (hist is not None and len(hist) >= 5 * 300 or t in core.policy()["instruments"]):
        try:
            import strategy
            h3 = ctx.setdefault("h3", {})
            if t not in h3:
                h3[t] = _recent(hist, 3)                    # 3 sessions warm MACD/ATR/ADX; keeps each bar cheap
            mh = pd.concat([h3[t], mk]) if h3[t] is not None and len(h3[t]) else mk
            snap = strategy.build_snapshot(t, m1=mh, meta={"ticker": t, "lab": True}, quote=False)
            if snap.get("ok"):
                snap["quiet"], snap["kv_ns"] = True, "lab:"
                for cd in strategy.detect_all(snap):
                    fam = "v3_vwap_macd" if cd["family"] == "VWAP_MACD" else "v3"
                    setup = cd["family"] + (f" ({cd['entry_mode']})" if cd.get("entry_mode") else "")
                    s = _record(t, fam, setup, cd["side"], b, bar_end, cd.get("level"), cd.get("invalidation"),
                                cd["family"] != "FAILED_BREAK", feats(), ctx["cats"], now, {"v3_kind": cd.get("kind")})
                    if s:
                        out.append(s)
        except Exception as e:
            _state["last_error"] = f"v3 {t}: {type(e).__name__}: {e}"[:200]
    # --- ORB15 study definitions
    atr = (base or {}).get("atr14")
    if atr and _hm(bar_end) >= "09:45" and len(rk) >= 12:
        try:
            import research
            sigs, _why = research.signals_for_day(rk, float(atr), live=True)
            for sg in sigs:
                if sg["signal_i"] != len(rk) - 1:
                    continue
                fam = "orb15_base" if sg["kind"] == "BASE" else "orb15_retest"
                s = _record(t, fam, "ORB15 " + sg["kind"].lower(), sg["side"], b, bar_end, sg["edge"], sg["stop"], True, feats(),
                            ctx["cats"], now)
                if s:
                    out.append(s)
        except Exception as e:
            _state["last_error"] = f"orb15 {t}: {type(e).__name__}: {e}"[:200]
    # --- MACD video rule at each finished 5m bar
    if bar_end.minute % 5 == 0 and hist is not None:
        try:
            b5 = _b5(hist, rk, b)
            if b5 is not None and len(b5) and b5.index[-1] + pd.Timedelta(minutes=5) == bar_end:
                side, e200, why = macd_video_signal(b5["Close"], c["macd_video_min_bars"])
                if side:
                    s = _record(t, "macd_video", "MACD video 5m", side, b, bar_end, None, e200, False, feats(), ctx["cats"], now,
                                {"why": why})
                    if s:
                        out.append(s)
        except Exception as e:
            _state["last_error"] = f"macd video {t}: {type(e).__name__}: {e}"[:200]
    # --- noise band at the half-hour checks
    hm = _hm(bar_end)
    if bar_end.minute in (0, 30) and "10:00" <= hm <= "15:00" and hist is not None:
        try:
            import noiseband
            st = noiseband.state_at(pd.concat([hist, rk]), day, bar_end)
            if st is not None:
                prev = _state["noise_prev"].get(t)
                _state["noise_prev"][t] = st["signal"]
                if st["signal"] and st["signal"] != prev:
                    up = st["signal"] == "C"
                    s = _record(t, "noise", "Noise band", st["signal"], b, bar_end, st["upper"] if up else st["lower"],
                                st["stop_long"] if up else st["stop_short"], True, feats(), ctx["cats"], now,
                                {"band": [st["lower"], st["upper"]], "sigma": st["sigma"]})
                    if s:
                        out.append(s)
        except Exception as e:
            _state["last_error"] = f"noise {t}: {type(e).__name__}: {e}"[:200]
    return out


def scan(now, base_all, c=None):
    """Process every new finished bar of every symbol, in time order (catch-up is bounded per step)."""
    c = c or cfg()
    _schema()
    day = now.date()
    ctx = {"cfg": c, "base": base_all, "hist": {}, "cats": _xcats(now)}
    bench = _today_bars("SPY", now)
    ctx["bench"] = bench
    new = []
    work = []
    for t in tickers():
        m1 = _today_bars(t, now)
        if m1 is None or not len(m1):
            continue
        ctx["hist"][t] = _hist_for(t, day)
        r = _rth(m1)
        last = _state["last_bar"].get(t)
        idx = list(r.index if last is None else r.index[r.index > pd.Timestamp(last)])
        if idx:
            work.append((len(idx), t, m1, idx))
    # symbols that are only a bar or three behind first (live signals); catch-up after a restart uses what time is left
    work.sort(key=lambda w: w[0])
    t_start = time.time()
    done_n = 0
    out_of_time = False
    for n_new, t, m1, idx in work:              # v3.4.1: ONE time budget for the whole step, live bars included
        for b in idx[:c["max_bars_per_step"]]:
            if done_n and time.time() - t_start > c.get("step_budget_s", 4):
                out_of_time = True
                break
            mk = m1[m1.index <= b]
            got = process_bar(t, mk, b, now, ctx)
            _state["last_bar"][t] = b.isoformat()
            done_n += 1
            new += got
        if out_of_time:
            break
        time.sleep(0)                           # let the desk's other threads run between symbols
    _state["behind"] = sum(max(0, w[0]) for w in work) - done_n
    for s in new:
        if s["live"] and c["paper"]:
            try:
                s["paper"] = paper_attempt(s, now, c)
            except Exception as e:
                s["paper"] = f"error {type(e).__name__}"
                _state["last_error"] = f"paper {s['ticker']}: {type(e).__name__}: {e}"[:200]
            store.x("UPDATE lab_tape SET paper=? WHERE id=?", (str(s["paper"])[:300], s["id"]))
    return new


# ================================================================ outcomes and matched random entries
def _day_bars(t, day, now=None):
    """Regular-session 1m bars for one past or current day: the archive first, then the live caches."""
    a = archive_read(day, t)
    if a is not None and len(a):
        return _rth(a)
    if now is not None and now.date() == day:
        m = _today_bars(t, now)
        return _rth(m) if m is not None else None
    return None


def resolve(day, now=None, c=None):
    """Outcomes for the day's open tape rows. Needs bars through the flat time; otherwise the row waits."""
    c = c or cfg()
    _schema()
    now = now or core.now_et()
    rows = store.q("SELECT * FROM lab_tape WHERE day=? AND status='OPEN'", (str(day),))
    if not rows:
        return 0
    lo, hi = c["window"]
    by_t = {}
    for r in rows:
        by_t.setdefault(r["ticker"], []).append(r)
    done = 0
    for t, rs in by_t.items():
        m1d = _day_bars(t, datetime.fromisoformat(str(day)).date() if isinstance(day, str) else day, now)
        if m1d is None or not len(m1d) or _hm(m1d.index[-1]) < c["flat"]:
            continue                                        # wait for the bars through the flat time
        a = MB.arrays(m1d)
        opens = {ts: i for i, ts in enumerate(m1d.index)}
        for r in rs:
            be = pd.Timestamp(r["bar_end"])
            hm = _hm(be)
            upd = {"status": "DONE", "resolved_at": store.ts()}
            ei = opens.get(be)
            if not (lo <= hm <= hi):
                upd["status"] = "OUT OF WINDOW"
            elif ei is None:
                upd["status"] = "NO ENTRY BAR"
            else:
                e = float(a["o"][ei])
                buf = c["stop_buffer_atr"] * (r["atr"] or 0) or 0.02
                inv = r["invalidation"]
                if inv is None:
                    upd["status"] = "NO INVALIDATION"
                else:
                    stop = inv - buf if r["side"] == "C" else inv + buf
                    sd = (e - stop) if r["side"] == "C" else (stop - e)
                    if sd <= max(0.01, 0.0002 * e):
                        upd["status"] = "ENTRY PAST THE STOP"
                    else:
                        kw = {"flat": c["flat"], "cost_per_share": c["cost_per_share"]}
                        o = MB.outcome_arrays(a, ei, r["side"], sd, target_r=c["target_r"], **kw)
                        upd.update(entry=e, stop_dist=round(sd, 4), r=o["r"] if o else None, exit_why=o["why"] if o else "no path")
                        for h in (5, 15, 30):
                            oh = MB.outcome_arrays(a, ei, r["side"], sd, target_r=1e9, horizon_min=h, **kw)
                            upd[f"r_{h}m"] = oh["r"] if oh else None
                        seed = int(hashlib.sha1(r["id"].encode()).hexdigest()[:8], 16)
                        upd["ctl_r"], upd["ctl_n"] = MB.control_mean(a, r["side"], sd, paths=c["controls_paths"], seed=seed,
                                                                     window=(lo, hi), target_r=c["target_r"], **kw)
            sets = ", ".join(f"{k}=?" for k in upd)
            store.x(f"UPDATE lab_tape SET {sets} WHERE id=?", tuple(upd.values()) + (r["id"],))
            done += 1
    _state["resolved_at"] = store.ts()
    return done


# ================================================================ lab paper ledgers
def _rec(cid, t, side, family, ledger, decision, reasons, plan=None):
    sess = core.session_info()
    store.x("INSERT OR REPLACE INTO candidates(id,date,ts,decision_t,ticker,side,family,tags,portfolio,decision,reasons,limit_blocked,evidence,plan,policy_version,provider,outcome) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, sess["date"], store.ts(), store.ts(), t, side, family, family, ledger, decision, json.dumps(reasons), None, None,
             json.dumps(plan, default=str) if plan else None, VERSION, "lab", None))


def _lab_open():
    return [p for led in paper.LAB_LEDGERS for p in store.positions(ledger=led, status="OPEN")]


def _take_token(c):
    t_now = time.time()
    if _state["att_t"] is None:
        _state["att_tokens"] = float(c["attempts_per_min"])          # a full bucket at start
    last = _state["att_t"] or t_now
    _state["att_t"] = t_now
    _state["att_tokens"] = min(_state["att_tokens"] + (t_now - last) * c["attempts_per_min"] / 60, c["attempts_per_min"])
    if _state["att_tokens"] < 1:
        return False
    _state["att_tokens"] -= 1
    return True


def gate_target(close, inval, side, cost, slack=0.01):
    """The 2:1 point after estimated costs, measured from the signal's close plus one cent (the gate rounds to cents).
    The gate then refuses any entry worse than that: no chasing past the signal price."""
    sg = 1 if side == "C" else -1
    e = close + slack * sg
    r = abs(e - inval)
    return e + (2 * (r + cost) + cost) * sg


def paper_attempt(s, now, c=None):
    """One live signal -> the lab ledger for its family, through the same checks as every strict paper ledger."""
    import entrygate
    import scanner
    c = c or cfg()
    fam = FAMILIES[s["family"]]
    led = fam["ledger"]
    t, side = s["ticker"], s["side"]
    hm = now.strftime("%H:%M")
    sess = core.session_info(now)
    cid = f"lab-{s['id']}"

    def skip(decision, why, plan=None):
        _rec(cid, t, side, s["family"], led, decision, [why], plan)
        return f"{decision}: {why}"
    if store.kv_get("paper_pause") or not store.kv_get("paper_enabled", True):
        return skip("SKIP", "paper entries are paused or off")
    if fam.get("main_has_own") and t in core.policy()["instruments"]:
        return skip("SKIP", f"{t} already has its own ledgers for these rules")
    if not sess.get("entries_allowed") or not (c["window"][0] <= hm <= c["window"][1]):
        return skip("SKIP", f"outside the entry window ({hm}; {sess.get('state')})")
    if s.get("invalidation") is None:
        return skip("SKIP", "no invalidation level: no structural stop")
    if len(store.positions(ledger=led, status="OPEN")) >= c["max_open_per_ledger"]:
        return skip("BLOCKED-LIMIT", f"max {c['max_open_per_ledger']} open trades in this ledger")
    if paper.ideas_today(led) >= c["max_ideas_per_ledger"]:
        return skip("BLOCKED-LIMIT", f"max {c['max_ideas_per_ledger']} ideas today in this ledger")
    if len(_lab_open()) >= c["max_open_total"]:
        return skip("BLOCKED-LIMIT", f"max {c['max_open_total']} open lab trades in total")
    if not _take_token(c):
        return skip("SKIP", "lab request budget for this minute used (keeps Schwab calls in limits)")
    f = _fetch()
    qs, _err = f.quotes([t])
    q = (qs or {}).get(t) or {}
    px, bid, ask = q.get("last"), q.get("bid"), q.get("ask")
    qms = q.get("quote_ms")
    q_age = (time.time() - qms / 1000) if qms else None
    bar_age = (pd.Timestamp(now) - s["bar_end"]).total_seconds()
    m1 = _today_bars(t, now)
    atr5 = None
    if m1 is not None and len(m1) >= 30:
        b5, done = I.aggregate(_rth(m1), 5)
        b5 = b5[done.values] if len(done) else b5
        if len(b5) >= 3:
            atr5 = I.last(I.atr(b5, 14))
    atr5 = atr5 or (s.get("atr14") or 1) / 8
    spread = (ask - bid) if bid and ask and ask >= bid else None
    sn = {"price": px or s["close"], "close1": float(m1["Close"].iloc[-1]) if m1 is not None and len(m1) else s["close"],
          "t": str(s["bar_end"]), "atr5": atr5, "spread": spread, "spread_pct": round(spread / px * 100, 3) if spread is not None and px else None,
          "fresh": bool(px) and q_age is not None and q_age <= 15 and bar_age <= c["max_signal_age_s"],
          "bar_age_s": round(bar_age), "quote_age_s": round(q_age) if q_age is not None else None, "buf": 0.02}
    cost = (spread / 2 if spread else 0.0) + 0.01
    close, inval = float(s["close"]), float(s["invalidation"])
    if (close - inval) * (1 if side == "C" else -1) <= 0:
        return skip("SKIP", f"the invalidation {inval:.2f} is not on the losing side of the signal close {close:.2f}")
    trig = float(s["level"]) if s["use_level"] and s.get("level") is not None else close - 0.1 * atr5 * (1 if side == "C" else -1)
    if (trig - inval) * (1 if side == "C" else -1) < 0:
        trig = close - 0.1 * atr5 * (1 if side == "C" else -1)
    tgt = gate_target(close, inval, side, cost)
    g = entrygate.define(t, side, s["family"], trig, inval, tgt, "2:1 from the signal close after costs", sn,
                         f"{FAMILIES[s['family']]['label']}: {s['setup']}", confirmed_at=now.isoformat(timespec="seconds"), scope=led)
    ev = entrygate.evaluate(g, sn)
    if ev["state"] != "ENTRY CONDITIONS MET":
        return skip("SKIP-GATE", f"gate {ev['state']}: {ev['rejected']}", {"gate": ev})
    idea = f"{s['day']}-{t}-{s['family']}-{side}-{s['b'].strftime('%H%M')}"
    if store.q("SELECT idea FROM ideas WHERE portfolio=? AND idea=?", (led, idea)):
        return "already tried"
    rows_c, err = f.chain(t, side, now.date().isoformat(), (now.date() + timedelta(days=c["max_dte"])).isoformat(), 16)
    best, _, rej = scanner.score_contracts(rows_c, side, now, None)
    if not best:
        paper.reserve_idea(led, idea, t, side)
        return skip("SKIP", "valid stock signal, no valid option: " + (", ".join(f"{k} {n}" for k, n in rej.items()) or err or "empty chain"))
    ok, why = paper.reserve_idea(led, idea, t, side)
    if not ok:
        return f"not reserved: {why}"
    slip, fee = paper.strict_costs()
    plan = {"symbol": best["symbol"], "label": f"{best['strike']:g}{side} {best['exp'][5:]}", "family": s["family"],
            "premium_stop": core.cents_up(best["ask"] * (1 - core.policy()["risk"]["stop_cap_pct"]) + slip + 2 * fee / 100),
            "premium_limit": round(best["ask"] + c["limit_cents_over_ask"], 2),
            "stop_px": round(inval, 2), "t1": "2:1 target", "t1_level": round(tgt, 2), "t1_px": None, "be_trigger": None,
            "breakeven_net": core.cents_up(best["ask"] + slip + 2 * fee / 100), "flat_by": None, "exit_profile": "lab",
            "variant": led, "policy_version": VERSION, "entry_px": px or close, "expiry": best["exp"], "grade": "R", "v": 34,
            "gate": {k: ev.get(k) for k in ("state", "latest_entry", "rr_now", "id", "version")},
            "x_read": {k: s["conditions"].get(k) for k in ("x_lean", "x_label", "x_attention", "x_id")},
            "row": {"tape_id": s["id"], "setup": s["setup"], "conditions": {k: v for k, v in s["conditions"].items() if k != "n"}}}
    pid, bwhy = paper.buy(led, idea, t, side, plan, int(c["qty"]), pd.Timestamp(s["bar_end"]).isoformat())
    if not pid:
        paper.release_idea(led, idea, bwhy)
        return skip("SKIP", bwhy, plan)
    _rec(cid, t, side, s["family"], led, "ORDER", [], plan)
    return f"ORDER {pid}"


def manage_all(now=None):
    """Exits for every open lab trade with ONE batched option-quote request: all out at the session's all-out time,
    the 20% planned premium line, a finished 1m close past the invalidation, or the 2:1 target on a finished close.
    The noise ledger keeps its own rule: the band/VWAP stop is checked only at the half-hour marks."""
    import marketdata
    now = now or core.now_et()
    pos = _lab_open()
    if not pos:
        return 0
    marketdata.option_quotes([p["symbol"] for p in pos])
    sess = core.session_info(now)
    n = 0
    for p in pos:
        pl = p["plan"]
        q, _ = marketdata.option_quote_cached(p["symbol"])
        why = None
        if now.strftime("%H:%M") >= sess["all_out"]:
            why = f"ALL OUT {sess['all_out']} (session rule)"
        elif q and q.get("executable") and q.get("bid") is not None and q["bid"] <= pl["premium_stop"]:
            why = f"premium at/below the planned 20% level ${pl['premium_stop']:.2f} (bid {q['bid']:.2f})"
        else:
            m1 = _today_bars(p["ticker"], now)
            if m1 is not None and len(m1):
                c1 = float(m1["Close"].iloc[-1])
                up = p["side"] == "C"
                if p["ledger"] == "lab_noise":
                    t_end = pd.Timestamp(m1.index[-1]) + pd.Timedelta(minutes=1)
                    if t_end.minute in (0, 30) and pl.get("last_check") != t_end.isoformat():
                        pl["last_check"] = t_end.isoformat()
                        try:
                            import noiseband
                            hist = _hist_for(p["ticker"], now.date())
                            st = noiseband.state_at(pd.concat([hist, _rth(m1)]) if hist is not None else _rth(m1), now.date(), t_end)
                            if st:
                                pl["stop_px"] = round(st["stop_long"] if up else st["stop_short"], 2)
                                if (st["price"] < pl["stop_px"]) if up else (st["price"] > pl["stop_px"]):
                                    why = f"noise stop at the {t_end.strftime('%H:%M')} check"
                                elif st["signal"] and st["signal"] != p["side"]:
                                    why = f"noise reversal at the {t_end.strftime('%H:%M')} check"
                        except Exception:
                            pass
                        store.pos_save(p)
                elif pl.get("stop_px") is not None and ((c1 < pl["stop_px"]) if up else (c1 > pl["stop_px"])):
                    why = f"setup invalidated: 1m close {c1:.2f} beyond {pl['stop_px']:.2f}"
                elif pl.get("t1_level") is not None and ((c1 >= pl["t1_level"]) if up else (c1 <= pl["t1_level"])):
                    why = f"2:1 target {pl['t1_level']:.2f} reached on a finished close"
        if why:
            got, _px = paper.sell(p, p["qty_open"], why)
            n += 1 if got else 0
    return n


# ================================================================ the report
def _boot_ci(per_session, boots=1000, seed=3):
    vals = list(per_session.values())
    if len(vals) < 5:
        return None
    rnd = np.random.default_rng(seed)
    arr = np.array(vals)
    sims = np.sort([arr[rnd.integers(0, len(arr), len(arr))].mean() for _ in range(boots)])
    return [round(float(sims[int(0.025 * boots)]), 3), round(float(sims[int(0.975 * boots) - 1]), 3)]


def _summ(rows, min_n):
    v = [r for r in rows if r["r"] is not None]
    n = len(v)
    out = {"n": n, "signals": len(rows), "sessions": len({r["day"] for r in v})}
    if not n:
        return dict(out, too_few=True)
    rs = np.array([r["r"] for r in v])
    ctl = [r for r in v if r["ctl_r"] is not None]
    out.update(win_rate=round(100 * float((rs > 0).mean()), 1), avg_r=round(float(rs.mean()), 3),
               avg_r_15m=round(float(np.mean([r["r_15m"] for r in v if r["r_15m"] is not None])), 3) if any(r["r_15m"] is not None for r in v) else None)
    if ctl:
        out["ctl_avg_r"] = round(float(np.mean([r["ctl_r"] for r in ctl])), 3)
        diffs = {}
        for r in ctl:
            diffs.setdefault(r["day"], []).append(r["r"] - r["ctl_r"])
        per = {d: float(np.mean(x)) for d, x in diffs.items()}
        out["edge"] = round(float(np.mean([r["r"] - r["ctl_r"] for r in ctl])), 3)
        out["edge_ci95"] = _boot_ci(per)
        days = sorted(per)
        if len(days) >= 4:
            h = len(days) // 2
            early = [r["r"] - r["ctl_r"] for r in ctl if r["day"] in days[:h]]
            late = [r["r"] - r["ctl_r"] for r in ctl if r["day"] in days[h:]]
            out["edge_early"], out["edge_late"] = round(float(np.mean(early)), 3), round(float(np.mean(late)), 3)
            out["n_early"], out["n_late"] = len(early), len(late)
            out["both_halves"] = bool(out["edge_early"] > 0 and out["edge_late"] > 0 and len(early) >= min_n and len(late) >= min_n)
    out["too_few"] = n < min_n
    return out


def what_works(by="strategy", cond=None, family=None, ticker=None, since=None, min_n=None, include_all=False, limit=300):
    """Grouped results from the resolved tape (stock outcomes in R), each next to its matched random entries.
    by: strategy | setup | ticker | strategy_ticker | strategy_group | strategy_condition (cond = a CONDITIONS key)."""
    _schema()
    c = cfg()
    min_n = int(min_n or c["min_n"])
    q = "SELECT id, day, ticker, family, setup, side, conditions, r, r_15m, ctl_r FROM lab_tape WHERE status='DONE'"
    args = []
    if since:
        q += " AND day>=?"
        args.append(since)
    if family:
        q += " AND family=?"
        args.append(family)
    if ticker:
        q += " AND ticker=?"
        args.append(ticker.upper())
    rows = store.q(q, tuple(args))
    for r in rows:
        r["cond"] = json.loads(r["conditions"] or "{}")
    if not include_all:                                        # the desk's own filters for board rows
        rows = [r for r in rows if r["cond"].get("qualifies", "yes") == "yes"]
    if by == "strategy_condition" and cond not in CONDITIONS:
        cond = "x_lean"

    def key(r):
        if by == "setup":
            return (r["family"], r["setup"])
        if by == "ticker":
            return (r["ticker"],)
        if by == "strategy_ticker":
            return (r["family"], r["ticker"])
        if by == "strategy_group":
            return (r["family"], r["cond"].get("group", "Other"))
        if by == "strategy_condition":
            return (r["family"], str(r["cond"].get(cond, "unknown")))
        return (r["family"],)
    groups = {}
    for r in rows:
        groups.setdefault(key(r), []).append(r)
    fam_all = {}
    grp_all = {}
    for r in rows:
        fam_all.setdefault(r["family"], []).append(r)
        grp_all.setdefault((r["family"], r["cond"].get("group", "Other")), []).append(r)
    out = []
    for k, rs in groups.items():
        s = _summ(rs, min_n)
        row = {"key": list(k), "strategy": k[0] if by != "ticker" else None,
               "label": FAMILIES.get(k[0], {}).get("label") if by != "ticker" else None, **s}
        if by == "strategy_ticker" and s["too_few"]:                 # the hierarchy: the stock's group, then all stocks
            t = k[1]
            g = rs[0]["cond"].get("group", "Other")
            row["group"] = g
            row["group_level"] = {kk: v for kk, v in _summ(grp_all.get((k[0], g), []), min_n).items()
                                  if kk in ("n", "win_rate", "avg_r", "edge", "too_few")}
            row["all_stocks"] = {kk: v for kk, v in _summ(fam_all.get(k[0], []), min_n).items()
                                 if kk in ("n", "win_rate", "avg_r", "edge", "too_few")}
            row["ticker"] = t
        out.append(row)
    out.sort(key=lambda x: (x["too_few"], -(x.get("edge") if x.get("edge") is not None else -9), -x["n"]))
    led = {}
    for f_, v in FAMILIES.items():
        rr = store.q("SELECT realized FROM positions WHERE ledger=? AND status='CLOSED'" + (" AND date>=?" if since else ""),
                     (v["ledger"], since) if since else (v["ledger"],))
        pn = [x["realized"] or 0 for x in rr]
        led[f_] = {"ledger": v["ledger"], "n": len(pn), "won": round(100 * sum(1 for x in pn if x > 0) / len(pn), 1) if pn else None,
                   "net": round(sum(pn), 2) if pn else 0.0, "per_trade": round(sum(pn) / len(pn), 2) if pn else None,
                   "open": len(store.positions(ledger=v["ledger"], status="OPEN"))}
    return {"by": by, "cond": cond, "cond_label": CONDITIONS.get(cond) if cond else None, "min_n": min_n, "rows": out[:limit],
            "groups": len(out), "signals": len(rows), "paper": led, "version": VERSION,
            "note": ("Stock outcomes in R (risk = entry to stop), one uniform yardstick for every strategy: next-bar entry, stop "
                     f"just past the signal's invalidation, {c['target_r']:g}R target, flat {c['flat']}, ${c['cost_per_share']:.2f}/share "
                     "costs. 'Random' = matched random entries on the same stock, day, side, window and stop. With hundreds of "
                     "combinations some will look good by luck: a combination counts only with enough signals, an interval above "
                     "zero AND a positive edge in both the earlier and the later half of the dates. Paper option results are "
                     "shown separately per ledger. Nothing here is promoted automatically.")}


def signals(day=None, ticker=None, family=None, limit=200):
    _schema()
    q, args = "SELECT * FROM lab_tape WHERE 1=1", []
    for k, v in (("day", day), ("ticker", ticker.upper() if ticker else None), ("family", family)):
        if v:
            q += f" AND {k}=?"
            args.append(v)
    rows = store.q(q + " ORDER BY bar_end DESC LIMIT ?", tuple(args) + (int(limit),))
    for r in rows:
        r["conditions"] = json.loads(r["conditions"] or "{}")
    return rows


def status():
    _schema()
    day = core.now_et().strftime("%Y-%m-%d")
    cnt = store.q("SELECT family, COUNT(*) n, SUM(live) live, SUM(CASE WHEN status='DONE' THEN 1 ELSE 0 END) done FROM lab_tape "
                  "WHERE day=? GROUP BY family", (day,))
    tot = store.q("SELECT COUNT(*) n, COUNT(DISTINCT day) days, SUM(CASE WHEN status='DONE' THEN 1 ELSE 0 END) done FROM lab_tape")[0]
    hist_n = sum(1 for t in tickers() if _hist_for(t, core.now_et().date()) is not None)
    return {"version": VERSION, "status": _state["status"], "last_error": _state["last_error"], "step_s": _state["step_s"],
            "bars_behind": _state.get("behind"),
            "symbols": len(tickers()), "with_history": hist_n, "today": {r["family"]: {"signals": r["n"], "live": r["live"] or 0,
                                                                                         "resolved": r["done"] or 0} for r in cnt},
            "total": {"signals": tot["n"], "days": tot["days"], "resolved": tot["done"] or 0},
            "archive_days": len(archive_days()), "archived_today": store.kv_get(f"lab_archived:{day}"),
            "families": {f: {"ledger": v["ledger"], "label": v["label"], "source": v["source"]} for f, v in FAMILIES.items()},
            "conditions": CONDITIONS, "open": [{k: p[k] for k in ("ledger", "ticker", "contract", "fill", "opened")} for p in _lab_open()],
            "recent": [{k: e[k] for k in ("ts", "text")} for e in store.q("SELECT ts, text FROM events WHERE kind='lab' ORDER BY seq DESC LIMIT 12")],
            "config": {k: cfg()[k] for k in ("window", "max_open_per_ledger", "max_ideas_per_ledger", "max_open_total", "attempts_per_min",
                                             "target_r", "flat", "min_n", "controls_paths")}}


# ================================================================ worker
def _persist(day):
    store.kv_set(f"lab_state:{day}", {"last_bar": _state["last_bar"], "ep": _state["ep"], "noise_prev": _state["noise_prev"]})
    _state["saved_at"] = time.time()


def step(now=None):
    c = cfg()
    if not c.get("enabled", True):
        _state["status"] = "off"
        return
    now = now or core.now_et()
    t0 = time.time()
    sess = core.session_info(now)
    day = now.date()
    if _state["day"] != day:
        saved = store.kv_get(f"lab_state:{day}") or {}
        with _lock:
            _state.update(day=day, last_bar=saved.get("last_bar") or {}, ep=saved.get("ep") or {}, noise_prev=saved.get("noise_prev") or {},
                          counts={}, cats=None, agg={})
    if sess.get("holiday") or now.weekday() >= 5:
        _state["status"] = "market closed"
        return
    f = _fetch()
    if not f.ready():
        _state["status"] = "waiting for Schwab (the lab never records delayed data)"
        return
    hm = now.strftime("%H:%M")
    if "04:00" <= hm <= "15:55":
        _pull_history(now, c)
    base_all = store.kv_get(f"scan_base:{day}")
    if c["tape"] and base_all and "09:31" <= hm <= "16:05":
        scan(now, base_all, c)
        _state["status"] = "recording"
    elif not base_all:
        _state["status"] = "waiting for the 08:30 baselines"
    manage_all(now)
    if hm >= c["resolve_after"] and time.time() - (_state.get("resolve_t") or 0) > 120:
        _state["resolve_t"] = time.time()
        resolve(str(day), now, c)
    if hm >= c["archive_after"] and _state["archived"] != str(day):
        archive_today(now)
    if time.time() - (_state.get("old_resolved") or 0) > 600:
        _state["old_resolved"] = time.time()
        for d in store.q("SELECT DISTINCT day FROM lab_tape WHERE status='OPEN' AND day<?", (str(day),)):
            resolve(d["day"], now, c)                                  # earlier days, from the archive (back-filled each morning)
    if time.time() - _state["saved_at"] > 60:
        _persist(day)
    _state["step_s"] = round(time.time() - t0, 2)


def _run():
    while not _state["stop"]:
        try:
            step()
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {e}"[:200]
        time.sleep(15)


def start():
    if _state["thread"] or not cfg().get("enabled", True):
        return False
    th = threading.Thread(target=_run, daemon=True, name="lab")
    _state["thread"] = th
    th.start()
    return True
