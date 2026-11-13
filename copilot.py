"""copilot.py - build items B8 + B5 + B9 + B4 (2026-11-13, Nick: "build it ... and build all prior things" + "ye").

A live co-pilot for Nick's own SPY/QQQ 0DTE decisions. It reads the same finished 1-minute candles a chart is drawn from,
builds 5- and 15-minute candles, maps the day's levels, and runs the pattern library of claude/sweep11-alert-pattern-
library.md (123 YouTube transcripts, Monid, 2026-11-13). Each pattern that fires sends a phone alert (alerts.py, ntfy)
with the level, the checklist, a price-level stop and first target computed here, a 0DTE strike idea, the news/event
flags of the day (B5) and the alert lag. Nick decides and places any real trade himself.
Pushes: one per ticker per candle (the best alert, the rest listed under it, "MIXED" when long and short patterns fire
together), only when the best alert ticks at least 5 of the 7 checklist boxes (config "copilot_push_min"); the rest go
to the desk feed and the report card. On a FOMC / CPI / jobs / monthly-OPEX day one RISK push after 09:35 (B5).

Evidence labels: every pattern here is CONTEXT, not a tested edge. TESTED-FAIL = lost on SPY after costs in the desk's
own tests (T40 break-and-retest, T41 confluence, T43 chart-input model, T64 VWAP retest, T66 fair value gap); UNTESTED =
not yet tested alone. A pattern moves to a TRADE alert only after a pre-registered test passes (CLAUDE.md steps 2-5).

B9 (paper shadow): when config/v4.json "copilot_paper" is true, every alert also opens a $1,000 paper share position in
the "copilot" ledger at the next fresh quote (simulated fill, ask + $0.01 / bid - $0.01), managed to the alert's stop or
target on live quotes, flat by 15:55. "copilot_paper": false = watch-only (alerts, no paper trades). The v4 kill switch,
the KILL file and the pauses block new shadow entries; exits always run. Isolated "copilot" risk book; one open shadow
per ticker at a time (the best alert of the candle first), so overlapping alerts are graded by B4 labels only.
B4 (report card): after the close every alert of the day is labeled from the 1-minute bars (target first, stop first or
neither, R at 15:55), and GET /api/v4/copilot/score ranks patterns, checklist counts and Nick's took/skipped answers;
on Fridays one push sums up the week.
Never real money (there is no order path here).
"""
import math
import threading
import time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

import core
import store
import v4common as C
import v4exec
import v4risk
import v4store as S

VERSION = "2026-11-13.copilot-1"
LEDGER, BOOK = "copilot", "copilot"
TICKERS = ("SPY", "QQQ")
TOL = 0.0005                      # "at a level": within 0.05%
VOL_MULT, WICK_FRAC, ATR_N = 1.5, 0.6, 14
STEP_S, SHADOW_USD, FLAT_HM, LAST_ENTRY_HM = 15, 1000.0, "15:55", "15:30"
QUOTE_MAX_AGE_S = 20
PUSH_MIN = 5                      # phone push when the candle's best alert ticks >= 5 of the 7 boxes (config "copilot_push_min")
EVIDENCE = {
    "wick_reject": "UNTESTED", "engulfing": "TESTED-FAIL (part of T43's inputs)", "hammer": "UNTESTED",
    "shooting_star": "UNTESTED", "inside_break": "UNTESTED", "momentum": "UNTESTED", "star": "UNTESTED",
    "break_retest": "TESTED-FAIL (T40, T41)", "sweep": "UNTESTED (T72 planned)", "bos": "UNTESTED",
    "fvg": "TESTED-FAIL (T66)", "double": "UNTESTED", "flag": "UNTESTED"}
NAMES = {"wick_reject": "rejection wick", "engulfing": "engulfing candle", "hammer": "hammer", "shooting_star": "shooting star",
         "inside_break": "inside-bar break", "momentum": "momentum candle", "star": "morning/evening star",
         "break_retest": "break and retest", "sweep": "liquidity sweep", "bos": "break of structure", "fvg": "fair value gap",
         "double": "double top/bottom", "flag": "bull/bear flag"}
_state = {"status": "idle", "thread": None, "stop": False, "last_error": None, "step_s": None}
_lock = threading.RLock()


# ================================================================ candles and levels (pure)
def norm(df):
    """o/h/l/c/v columns from Schwab-style Open/High/Low/Close/Volume (or already lower-case)."""
    if df is None or not len(df):
        return pd.DataFrame(columns=["o", "h", "l", "c", "v"])
    m = {"Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v"}
    d = df.rename(columns=m)
    if "v" not in d:
        d["v"] = 0.0
    return d[["o", "h", "l", "c", "v"]].astype(float)


def resample(m1, minutes, day):
    """Finished `minutes` candles of the regular session, aligned to 09:30 ET (complete groups only)."""
    r = norm(m1)
    if not len(r):
        return r
    r = r[r.index.date == day].between_time("09:30", "15:59")
    if not len(r):
        return r
    origin = pd.Timestamp(datetime.combine(day, datetime.min.time()).replace(hour=9, minute=30), tz=r.index.tz)
    g = r.resample(f"{minutes}min", origin=origin, label="left", closed="left")
    out = g.agg({"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"}).dropna()
    n = g["c"].count().reindex(out.index)
    return out[n == minutes]


def vwap(rth):
    r = norm(rth)
    if not len(r) or r["v"].sum() <= 0:
        return None
    tp = (r["h"] + r["l"] + r["c"]) / 3
    return float((tp * r["v"]).cumsum().iloc[-1] / r["v"].cumsum().iloc[-1])


def atr(b, n=ATR_N):
    if len(b) < 2:
        return float((b["h"] - b["l"]).mean()) if len(b) else 0.0
    pc = b["c"].shift(1)
    tr = pd.concat([b["h"] - b["l"], (b["h"] - pc).abs(), (b["l"] - pc).abs()], axis=1).max(axis=1)
    return float(tr.tail(n).mean())


def levels(daily, ext, rth, day):
    """The day's level map: [{"name", "px"}]. Prior day high/low/close, premarket high/low, 5- and 15-minute opening
    range, VWAP and round numbers ($1 near price, $5 marks) - all from finished data known at the time."""
    out = []
    d = norm(daily)
    prior = d[d.index.date < day] if len(d) else d
    if len(prior):
        p = prior.iloc[-1]
        out += [{"name": "PDH", "px": float(p["h"])}, {"name": "PDL", "px": float(p["l"])}, {"name": "PDC", "px": float(p["c"])}]
    e = norm(ext)
    if len(e):
        pre = e[(e.index.date == day)].between_time("04:00", "09:29")
        if len(pre):
            out += [{"name": "PMH", "px": float(pre["h"].max())}, {"name": "PML", "px": float(pre["l"].min())}]
    r = norm(rth)
    r = r[r.index.date == day].between_time("09:30", "15:59") if len(r) else r
    for n in (5, 15):
        if len(r) >= n:
            out += [{"name": f"OR{n}H", "px": float(r["h"].iloc[:n].max())}, {"name": f"OR{n}L", "px": float(r["l"].iloc[:n].min())}]
    vw = vwap(r) if len(r) else None
    if vw:
        out.append({"name": "VWAP", "px": round(vw, 4)})
    last = float(r["c"].iloc[-1]) if len(r) else (out[2]["px"] if len(out) > 2 else None)
    if last:
        for k in range(int(math.floor(last)) - 2, int(math.ceil(last)) + 3):
            out.append({"name": f"${k}" + (" (5s)" if k % 5 == 0 else ""), "px": float(k)})
    return out


def _near(px, lv, tol=TOL):
    best = None
    for L in lv:
        if abs(px - L["px"]) <= tol * L["px"] and (best is None or abs(px - L["px"]) < abs(px - best["px"])):
            best = L
    return best


def _key_levels(lv):
    return [L for L in lv if L["name"] in ("PDH", "PDL", "PMH", "PML", "OR5H", "OR5L", "OR15H", "OR15L", "PDC")]


# ================================================================ the pattern library (pure; last finished candle)
def _hit(pattern, side, level, stop, why):
    return {"pattern": pattern, "side": side, "level": level, "stop": round(float(stop), 2), "why": why}


def detect(b, lv):
    """All patterns that fire on the LAST finished candle of `b` (o/h/l/c/v). Returns a list of hits."""
    hits = []
    if len(b) < 3:
        return hits
    o, h, l, c = (b[k].to_numpy() for k in ("o", "h", "l", "c"))
    i = len(b) - 1
    rng, body = h[i] - l[i], abs(c[i] - o[i])
    up, lo_w = h[i] - max(o[i], c[i]), min(o[i], c[i]) - l[i]
    a = atr(b.iloc[:-1]) or rng
    if rng > 0:
        # rejection wick through a level, close back on the other side
        for L in lv:
            if up >= WICK_FRAC * rng and h[i] >= L["px"] >= max(o[i], c[i]):
                hits.append(_hit("wick_reject", "short", L, h[i] + 0.01, f"upper wick {up / rng:.0%} of the candle through {L['name']}"))
                break
        for L in lv:
            if lo_w >= WICK_FRAC * rng and l[i] <= L["px"] <= min(o[i], c[i]):
                hits.append(_hit("wick_reject", "long", L, l[i] - 0.01, f"lower wick {lo_w / rng:.0%} of the candle through {L['name']}"))
                break
        # hammer / shooting star at a level, after a move into it
        if lo_w >= 2 * body and up <= 0.25 * rng and min(o[i], c[i]) >= l[i] + 2 / 3 * rng and c[i - 1] < c[max(0, i - 3)]:
            L = _near(l[i], lv, 2 * TOL)
            if L:
                hits.append(_hit("hammer", "long", L, l[i] - 0.01, f"hammer at {L['name']} after a drop"))
        if up >= 2 * body and lo_w <= 0.25 * rng and max(o[i], c[i]) <= h[i] - 2 / 3 * rng and c[i - 1] > c[max(0, i - 3)]:
            L = _near(h[i], lv, 2 * TOL)
            if L:
                hits.append(_hit("shooting_star", "short", L, h[i] + 0.01, f"shooting star at {L['name']} after a rally"))
        # momentum (displacement) candle
        if body >= 0.8 * rng and rng >= 1.5 * a:
            side = "long" if c[i] > o[i] else "short"
            hits.append(_hit("momentum", side, None, l[i] - 0.01 if side == "long" else h[i] + 0.01,
                             f"body {body / rng:.0%} of range, range {rng / a:.1f}x ATR"))
    # engulfing at a level
    pb = abs(c[i - 1] - o[i - 1])
    if c[i] > o[i] and c[i - 1] < o[i - 1] and body >= pb and o[i] <= c[i - 1] and c[i] >= o[i - 1]:
        L = _near(min(l[i], l[i - 1]), lv, 2 * TOL)
        if L:
            hits.append(_hit("engulfing", "long", L, min(l[i], l[i - 1]) - 0.01, f"bullish engulfing at {L['name']}"))
    if c[i] < o[i] and c[i - 1] > o[i - 1] and body >= pb and o[i] >= c[i - 1] and c[i] <= o[i - 1]:
        L = _near(max(h[i], h[i - 1]), lv, 2 * TOL)
        if L:
            hits.append(_hit("engulfing", "short", L, max(h[i], h[i - 1]) + 0.01, f"bearish engulfing at {L['name']}"))
    # inside bar, then a close through the mother bar
    if h[i - 1] <= h[i - 2] and l[i - 1] >= l[i - 2]:
        if c[i] > h[i - 2]:
            hits.append(_hit("inside_break", "long", None, l[i - 2] - 0.01, "close above the mother bar after an inside bar"))
        elif c[i] < l[i - 2]:
            hits.append(_hit("inside_break", "short", None, h[i - 2] + 0.01, "close below the mother bar after an inside bar"))
    # morning / evening star
    b3, b2 = abs(c[i - 2] - o[i - 2]), abs(c[i - 1] - o[i - 1])
    if b3 > 0 and b2 <= 0.3 * b3:
        mid = (o[i - 2] + c[i - 2]) / 2
        if c[i - 2] < o[i - 2] and c[i] > o[i] and c[i] > mid:
            hits.append(_hit("star", "long", None, min(l[i - 2:i + 1]) - 0.01, "morning star: drop, pause, strong close up"))
        if c[i - 2] > o[i - 2] and c[i] < o[i] and c[i] < mid:
            hits.append(_hit("star", "short", None, max(h[i - 2:i + 1]) + 0.01, "evening star: rally, pause, strong close down"))
    # break and retest of a key level (break within the last 12 candles, this candle retests and holds)
    for L in _key_levels(lv):
        p = L["px"]
        w = range(max(1, i - 12), i)
        if any(c[j] > p * (1 + TOL) and c[j - 1] <= p for j in w) and l[i] <= p * (1 + TOL) and c[i] > p and c[i] > o[i]:
            hits.append(_hit("break_retest", "long", L, l[i] - 0.01, f"broke {L['name']}, retested it and held"))
            break
        if any(c[j] < p * (1 - TOL) and c[j - 1] >= p for j in w) and h[i] >= p * (1 - TOL) and c[i] < p and c[i] < o[i]:
            hits.append(_hit("break_retest", "short", L, h[i] + 0.01, f"broke {L['name']}, retested it and failed"))
            break
    # liquidity sweep: poke past an obvious high/low by under 0.1%, close back inside
    swing_h = float(h[max(0, i - 20):i - 1].max()) if i >= 3 else None
    swing_l = float(l[max(0, i - 20):i - 1].min()) if i >= 3 else None
    cands = _key_levels(lv) + ([{"name": "swing high", "px": swing_h}] if swing_h else []) + ([{"name": "swing low", "px": swing_l}] if swing_l else [])
    for L in cands:
        p = L["px"]
        if c[i - 1] < p and h[i] > p and h[i] <= p * 1.001 and c[i] < p and L["name"] not in ("PDL", "PML", "OR5L", "OR15L", "swing low"):
            hits.append(_hit("sweep", "short", L, h[i] + 0.01, f"swept above {L['name']} and closed back below"))
            break
        if c[i - 1] > p and l[i] < p and l[i] >= p * 0.999 and c[i] > p and L["name"] not in ("PDH", "PMH", "OR5H", "OR15H", "swing high"):
            hits.append(_hit("sweep", "long", L, l[i] - 0.01, f"swept below {L['name']} and closed back above"))
            break
    # break of structure: close through the last swing high/low (2 candles each side, strictly above/below the left side)
    piv_h = [j for j in range(2, i - 1) if h[j] > max(h[j - 2:j]) and h[j] >= max(h[j + 1:j + 3])]
    piv_l = [j for j in range(2, i - 1) if l[j] < min(l[j - 2:j]) and l[j] <= min(l[j + 1:j + 3])]
    if piv_h and c[i] > h[piv_h[-1]] >= c[i - 1]:
        hits.append(_hit("bos", "long", None, l[i] - 0.01, f"closed above the last swing high {h[piv_h[-1]]:.2f}"))
    if piv_l and c[i] < l[piv_l[-1]] <= c[i - 1]:
        hits.append(_hit("bos", "short", None, h[i] + 0.01, f"closed below the last swing low {l[piv_l[-1]]:.2f}"))
    # fair value gap formed (3-candle gap around a displacement candle: middle range >= 1.5 ATR)
    disp = (h[i - 1] - l[i - 1]) >= 1.5 * a
    if disp and l[i] > h[i - 2]:
        hits.append(_hit("fvg", "long", None, h[i - 2] - 0.01, f"bullish gap {h[i - 2]:.2f}-{l[i]:.2f}"))
    elif disp and h[i] < l[i - 2]:
        hits.append(_hit("fvg", "short", None, l[i - 2] + 0.01, f"bearish gap {h[i]:.2f}-{l[i - 2]:.2f}"))
    # double top / bottom: two swing highs (lows) within 0.1%, at least 3 candles apart with a dip (bounce) of >= 1.5 ATR
    # between them, then a close through the neckline
    if len(piv_h) >= 2 and piv_h[-1] - piv_h[-2] >= 3 and abs(h[piv_h[-1]] - h[piv_h[-2]]) <= 0.001 * h[piv_h[-1]]:
        neck = float(l[piv_h[-2]:piv_h[-1] + 1].min())
        if min(h[piv_h[-1]], h[piv_h[-2]]) - neck >= 1.5 * a and c[i] < neck <= c[i - 1]:
            hits.append(_hit("double", "short", None, max(h[piv_h[-1]], h[piv_h[-2]]) + 0.01, f"double top, neckline {neck:.2f} broken"))
    if len(piv_l) >= 2 and piv_l[-1] - piv_l[-2] >= 3 and abs(l[piv_l[-1]] - l[piv_l[-2]]) <= 0.001 * l[piv_l[-1]]:
        neck = float(h[piv_l[-2]:piv_l[-1] + 1].max())
        if neck - max(l[piv_l[-1]], l[piv_l[-2]]) >= 1.5 * a and c[i] > neck >= c[i - 1]:
            hits.append(_hit("double", "long", None, min(l[piv_l[-1]], l[piv_l[-2]]) - 0.01, f"double bottom, neckline {neck:.2f} broken"))
    # bull / bear flag: an impulse >= 2 ATR, 3-8 candles retracing <= 50%, then a close through the flag
    for n in range(3, 9):
        s = i - n
        if s - 4 < 0:
            break
        imp_lo, imp_hi = float(l[s - 4:s + 1].min()), float(h[s - 4:s + 1].max())
        fh, fl = float(h[s + 1:i].max()), float(l[s + 1:i].min())
        if imp_hi - imp_lo >= 2 * a and c[s] > o[s - 4]:
            if fl >= imp_hi - 0.5 * (imp_hi - imp_lo) and fh <= imp_hi and c[i] > fh:
                hits.append(_hit("flag", "long", None, fl - 0.01, f"bull flag: {n} candles held above half the push"))
                break
        if imp_hi - imp_lo >= 2 * a and c[s] < o[s - 4]:
            if fh <= imp_lo + 0.5 * (imp_hi - imp_lo) and fl >= imp_lo and c[i] < fl:
                hits.append(_hit("flag", "short", None, fh + 0.01, f"bear flag: {n} candles held below half the drop"))
                break
    return hits


# ================================================================ checklist, events (B5) and the plan (pure)
def opex_day(d):
    """Monthly options expiration: the third Friday."""
    return d.weekday() == 4 and 15 <= d.day <= 21


def events(now, cal=None):
    """B5: today's flags {"fomc", "cpi", "jobs", "opex", "notes"} and whether entries are inside a news window now."""
    cal = cal if cal is not None else C.calendar(now)
    hm = now.strftime("%H:%M")
    notes = []
    if cal.get("fomc"):
        notes.append("FOMC day: statement 14:00, first move often fake")
    if cal.get("cpi"):
        notes.append("CPI day (08:30): IV crush after the release")
    if cal.get("jobs"):
        notes.append("jobs report day (08:30)")
    if opex_day(now.date()):
        notes.append("monthly OPEX: bigger swings and reversals")
    window = bool(cal.get("fomc")) and "13:55" <= hm <= "14:10"
    return {"fomc": cal.get("fomc"), "cpi": cal.get("cpi"), "jobs": cal.get("jobs"), "opex": opex_day(now.date()),
            "known": cal.get("known"), "notes": notes, "news_window": window}


def checklist(hit, b5, daily_close_ema20, price, vw, now, ev):
    """The boxes on each alert. Each is True/False (None = unknown)."""
    side = hit["side"]
    vol = b5["v"].to_numpy()
    vol_ok = bool(len(vol) > 5 and vol[-1] >= VOL_MULT * float(np.mean(vol[-21:-1]))) if len(vol) > 5 else None
    hm = now.strftime("%H:%M")
    bias = None if daily_close_ema20 is None else ((price > daily_close_ema20) == (side == "long"))
    return {"bias_1h": bias, "at_level": hit.get("level") is not None, "close_5m": True, "volume": vol_ok,
            "vwap_side": None if vw is None else ((price > vw) == (side == "long")),
            "time_ok": ("09:45" <= hm <= "11:30") or ("13:30" <= hm <= "15:30"), "news_clear": not ev["news_window"]}


def plan(hit, price, lv):
    """Entry reference, price-level stop, first target (next level at least 1R away, else 2R), R and a 0DTE strike idea."""
    side, stop = hit["side"], hit["stop"]
    risk = abs(price - stop)
    if risk <= 0:
        return None
    sgn = 1 if side == "long" else -1
    beyond = sorted([L for L in lv if sgn * (L["px"] - price) >= risk], key=lambda L: abs(L["px"] - price))
    if beyond:
        tgt, tname = beyond[0]["px"], beyond[0]["name"]
    else:
        tgt, tname = price + sgn * 2 * risk, "2R"
    strike = math.ceil(price) + 1 if side == "long" else math.floor(price) - 1
    return {"entry_ref": round(price, 2), "stop": round(stop, 2), "target": round(tgt, 2), "target_name": tname,
            "risk": round(risk, 2), "r_to_target": round(abs(tgt - price) / risk, 2),
            "option": f"0DTE {strike}{'C' if side == 'long' else 'P'} (1 strike out of the money)"}


def text(t, tf, hit, pl, chk, ev, lag_s):
    yn = lambda v: "?" if v is None else ("Y" if v else "N")  # noqa: E731
    boxes = (f"bias {yn(chk['bias_1h'])} | level {yn(chk['at_level'])} | 5m close Y | volume {yn(chk['volume'])} | "
             f"VWAP {yn(chk['vwap_side'])} | time {yn(chk['time_ok'])} | news {yn(chk['news_clear'])}")
    score = sum(1 for v in chk.values() if v)
    lvl = f" @ {hit['level']['name']} {hit['level']['px']:.2f}" if hit.get("level") else ""
    title = f"COPILOT {t} {hit['side'].upper()}: {NAMES[hit['pattern']]}{lvl} ({tf})"
    body = "\n".join([f"Close {pl['entry_ref']:.2f} | stop {pl['stop']:.2f} | target {pl['target']:.2f} ({pl['target_name']}, {pl['r_to_target']}R)",
                      f"Checklist {score}/7: {boxes}", f"Why: {hit['why']}", f"Option idea: {t} {pl['option']}",
                      f"Evidence: {EVIDENCE[hit['pattern']]} - context, not a tested edge"]
                     + ([f"Today: {'; '.join(ev['notes'])}"] if ev["notes"] else []) + [f"lag {lag_s:.1f}s"])
    return title, body, score


# ================================================================ B4: labels and the report card (pure + store)
def label(alert, m1_after, flat_hm=FLAT_HM):
    """Outcome from the 1-minute candles after the alert's candle: TARGET / STOP first (both in one minute = STOP), else
    NEITHER with R at the flat time."""
    r = norm(m1_after)
    if not len(r):
        return None
    r = r.between_time("00:00", flat_hm)
    e, st, tg = alert["plan"]["entry_ref"], alert["plan"]["stop"], alert["plan"]["target"]
    long_ = alert["side"] == "long"
    risk = abs(e - st)
    for _, x in r.iterrows():
        hit_stop = x["l"] <= st if long_ else x["h"] >= st
        hit_tgt = x["h"] >= tg if long_ else x["l"] <= tg
        if hit_stop:
            return {"outcome": "STOP", "r": -1.0}
        if hit_tgt:
            return {"outcome": "TARGET", "r": round(abs(tg - e) / risk, 2)}
    last = float(r["c"].iloc[-1])
    return {"outcome": "NEITHER", "r": round(((last - e) if long_ else (e - last)) / risk, 2)}


def _akey(day):
    return f"{LEDGER}:alerts:{day}"


def alerts_for(day):
    return store.kv_get(_akey(str(day))) or []


def scorecard(days=None):
    """Labeled alerts by pattern, by checklist score and by Nick's answer: n, target-first rate, average R."""
    keys = [k for k in (days or [])] or sorted({r["k"] for r in store.q("SELECT k FROM kv WHERE k LIKE ?", (f"{LEDGER}:alerts:%",))})
    rows = []
    for k in keys:
        rows += store.kv_get(k if str(k).startswith(LEDGER) else _akey(k)) or []
    rows = [a for a in rows if a.get("label")]

    def agg(group):
        out = {}
        for a in rows:
            g = group(a)
            d = out.setdefault(g, {"n": 0, "target_first": 0, "r_sum": 0.0})
            d["n"] += 1
            d["target_first"] += a["label"]["outcome"] == "TARGET"
            d["r_sum"] += a["label"]["r"]
        return {g: {"n": d["n"], "target_first_pct": round(100 * d["target_first"] / d["n"], 1), "avg_r": round(d["r_sum"] / d["n"], 3)}
                for g, d in sorted(out.items(), key=lambda kv: -kv[1]["n"])}
    return {"label": "PAPER/BACKTEST-style labels from 1-minute bars (no costs): context for which alerts deserve a test",
            "n": len(rows), "by_pattern": agg(lambda a: a["pattern"]), "by_checklist": agg(lambda a: a["checklist_score"]),
            "by_answer": agg(lambda a: a.get("answer") or "no answer"), "by_ticker": agg(lambda a: a["ticker"]),
            "by_pushed": agg(lambda a: "pushed" if a.get("pushed") else "feed only")}


def feedback(aid, took):
    """Nick's answer for one alert: took it (True) or skipped it (False)."""
    day = str(aid).split("|")[1] if "|" in str(aid) else None
    if not day:
        return {"ok": False, "error": "bad id"}
    lst = alerts_for(day)
    for a in lst:
        if a["id"] == aid:
            a["answer"] = "took" if took else "skipped"
            store.kv_set(_akey(day), lst)
            return {"ok": True, "id": aid, "answer": a["answer"]}
    return {"ok": False, "error": "unknown alert"}


# ================================================================ the worker
def fetch():
    import scanner
    return scanner._fetch


def switches():
    import retire
    c = retire.cfg()
    return bool(c.get("copilot", False)), bool(c.get("copilot_paper", False))


def push_min():
    import retire
    try:
        return int(retire.cfg().get("copilot_push_min", PUSH_MIN))
    except (TypeError, ValueError):
        return PUSH_MIN


def rank(a):
    """Best alert of a candle first: more boxes ticked, at a level, not already TESTED-FAIL."""
    return (a["checklist_score"], a.get("level") is not None, not a["evidence"].startswith("TESTED-FAIL"))


def group_push(grp):
    """One phone push per ticker per candle: the best alert, the others listed under it, mixed signals flagged."""
    grp = sorted(grp, key=rank, reverse=True)
    top = grp[0]
    title = top["title"] + (f" +{len(grp) - 1} more" if len(grp) > 1 else "")
    extra = []
    if len({a["side"] for a in grp}) > 1:
        extra.append("MIXED: long and short patterns on the same candle")
    if len(grp) > 1:
        extra.append("Also: " + "; ".join(f"{NAMES[a['pattern']]} {a['side']} ({a['checklist_score']}/7)" for a in grp[1:]))
    return grp, title, "\n".join([top["body"]] + extra)


def briefing(now, ev):
    """B5 RISK tier: one push per day at the first co-pilot step after 09:35 when today has an event flag."""
    if not ev["notes"]:
        return False
    import alerts
    return alerts.alert("copilot", f"COPILOT RISK {now.date()}: event day", "\n".join(ev["notes"] + [
        "Smaller size; wait for the 5-minute close; first move after a release is often fake."]), f"copilot:brief:{now.date()}", "high")


def week_summary(day):
    """B4 weekly report card text for the Monday-Friday week of `day` (None if no labeled alerts)."""
    mon = day - timedelta(days=day.weekday())
    sc = scorecard([str(mon + timedelta(days=k)) for k in range(5)])
    if not sc["n"]:
        return None
    top = list(sc["by_pattern"].items())[:6]
    lines = [f"{NAMES.get(k, k)}: {v['n']} alerts, target first {v['target_first_pct']}%, avg {v['avg_r']}R" for k, v in top]
    ans = sc["by_answer"]
    if "took" in ans:
        lines.append(f"Ones you took: {ans['took']['n']}, avg {ans['took']['avg_r']}R")
    return f"COPILOT WEEK of {mon}: {sc['n']} alerts", "\n".join(lines + [sc["label"]])


def _ema20_daily(daily, price, day):
    """1-hour-bias stand-in: the daily EMA(20) of finished prior sessions plus today's price (no today's daily bar)."""
    d = norm(daily)
    d = d[d.index.date < day] if len(d) else d
    if len(d) < 20:
        return None
    s = pd.concat([d["c"], pd.Series([price])], ignore_index=True)
    return float(s.ewm(span=20, adjust=False).mean().iloc[-1])


def scan(t, day, now, f, ev):
    """Run the library on the last finished 5- and 15-minute candles of `t`. Returns new alert records."""
    m1 = C.finished(f.m1_today(t, day), now)
    if m1 is None or not len(m1):
        return []
    try:
        ext = C.finished(f.m1_ext(t, day, now), now)
    except Exception:
        ext = None
    daily = f.daily(t)
    rth = norm(m1)
    lv = levels(daily, ext, rth, day)
    vw = vwap(rth[rth.index.date == day].between_time("09:30", "15:59"))
    seen = {a["id"] for a in alerts_for(day)}
    out = []
    for tf in (5, 15):
        b = resample(m1, tf, day)
        if len(b) < 3:
            continue
        bar_t = b.index[-1]
        bar_end = bar_t + pd.Timedelta(minutes=tf)
        if (pd.Timestamp(now) - bar_end).total_seconds() > 120:          # only the candle that just finished
            continue
        price = float(b["c"].iloc[-1])
        ema = _ema20_daily(daily, price, day)
        for hit in detect(b, lv):
            aid = f"{t}|{day}|{bar_t.strftime('%H:%M')}|{tf}m|{hit['pattern']}|{hit['side']}"
            if aid in seen:
                continue
            pl = plan(hit, price, lv)
            if pl is None:
                continue
            chk = checklist(hit, b, ema, price, vw, now, ev)
            lag = (pd.Timestamp(now) - bar_end).total_seconds()
            title, body, score = text(t, f"{tf}m", hit, pl, chk, ev, lag)
            out.append({"id": aid, "ticker": t, "tf": f"{tf}m", "bar_t": bar_t.isoformat(), "pattern": hit["pattern"],
                        "side": hit["side"], "level": hit.get("level"), "why": hit["why"], "plan": pl, "checklist": chk,
                        "checklist_score": score, "events": ev, "lag_s": round(lag, 1), "title": title, "body": body,
                        "evidence": EVIDENCE[hit["pattern"]], "at": now.isoformat(timespec="seconds"), "version": VERSION})
    return out


def _shadow(a, now, quotes):
    """B9: one paper share position per alert (simulated fill on a fresh quote after the candle closed)."""
    t = a["ticker"]
    q = v4exec.equity_quote(t, quotes)
    ok, why = C.quote_after(q, pd.Timestamp(a["bar_t"]) + pd.Timedelta(minutes=int(a["tf"][:-1])), QUOTE_MAX_AGE_S)
    if not ok:
        return None, f"no fresh quote ({why})"
    if now.strftime("%H:%M") > LAST_ENTRY_HM:
        return None, "after 15:30: no new shadow entries"
    blk = v4risk.admit(LEDGER, BOOK, t, a["side"], now)
    if blk:
        return None, blk
    long_ = a["side"] == "long"
    fill = S.share_buy(q) if long_ else S.share_sell(q)
    qty = math.floor(SHADOW_USD / fill * 1e4) / 1e4
    rec = {"id": f"{LEDGER}:{a['id']}", "ledger": LEDGER, "book": BOOK, "kind": "shares", "date": a["id"].split("|")[1], "ticker": t,
           "direction": a["side"], "side": a["side"], "qty": qty, "entry_px": fill, "entry_t": store.ts(), "signal_t": a["at"],
           "quote_t": str(q.get("quote_time")), "fees": 0.0, "risk_usd": round(qty * a["plan"]["risk"], 2), "max_loss": None,
           "legs": [{"symbol": t, "label": f"{qty:g} sh", "action": "buy" if long_ else "sell short", "qty": qty}],
           "plan": {"label": "PAPER (simulated fill) shadow of a co-pilot alert; CONTEXT pattern, not a tested edge",
                    "alert": a["id"], "pattern": a["pattern"], "stop": a["plan"]["stop"], "target": a["plan"]["target"],
                    "last_mark": fill, "mtm": 0.0, "exit_rule": f"stop {a['plan']['stop']}, target {a['plan']['target']}, flat {FLAT_HM}"},
           "version": VERSION, "exec_model": "shares1"}
    pid, err = S.open_position(rec, "co-pilot shadow (paper, simulated fill)")
    return pid, err or f"opened at {fill} (paper, simulated fill)"


def manage(now, quotes):
    """Shadow exits on live quotes: stop, target or the flat time. Exits always run."""
    for p in S.positions(ledger=LEDGER, status="OPEN"):
        if (p.get("plan") or {}).get("pending_exit"):
            v4exec.retry_pending(p, quotes)
            continue
        q = v4exec.equity_quote(p["ticker"], quotes)
        late = now.strftime("%H:%M") >= FLAT_HM or str(p["date"]) < str(now.date())
        if not (q and q.get("executable") and q.get("bid") is not None and q.get("ask") is not None):
            if late:
                v4exec.close_now(p, f"flat by {FLAT_HM}", {p["ticker"]: q} if q else None)   # pending until a valid quote
            continue
        pl = p.get("plan") or {}
        long_ = p["direction"] == "long"
        px = q["bid"] if long_ else q["ask"]
        mtm = round(S.pnl(p, px), 2)
        S.update_plan(p["id"], last_mark=px, mtm=mtm, mark_t=str(q.get("quote_time")))
        S.mark(p["id"], mtm, mtm)
        if late:
            v4exec.close_now(p, f"flat by {FLAT_HM}", {p["ticker"]: q})
        elif (long_ and px <= pl["stop"]) or (not long_ and px >= pl["stop"]):
            v4exec.close_now(p, f"stop {pl['stop']}", {p["ticker"]: q})
        elif (long_ and px >= pl["target"]) or (not long_ and px <= pl["target"]):
            v4exec.close_now(p, f"target {pl['target']}", {p["ticker"]: q})


def label_day(day, f):
    """B4: label every alert of `day` from the 1-minute bars after its candle (once, after the close)."""
    lst = alerts_for(day)
    if not lst or all(a.get("label") for a in lst):
        return 0
    n = 0
    for t in {a["ticker"] for a in lst}:
        m1 = norm(f.m1_today(t, day))
        for a in lst:
            if a["ticker"] != t or a.get("label"):
                continue
            end = pd.Timestamp(a["bar_t"]) + pd.Timedelta(minutes=int(a["tf"][:-1]))
            lab = label(a, m1[m1.index >= end])
            if lab:
                a["label"] = lab
                n += 1
    store.kv_set(_akey(str(day)), lst)
    return n


def step(now=None):
    now = now or core.now_et()
    t0 = time.time()
    day = now.date()
    sess = core.session_info(now)
    on, paper = switches()
    hm = now.strftime("%H:%M")
    f = fetch()
    if sess.get("holiday") or now.weekday() >= 5:
        _state["status"] = "market closed"
        return
    quotes = {}
    if f.ready() and (S.positions(ledger=LEDGER, status="OPEN") or "09:35" <= hm < sess.get("close", "16:00")):
        try:
            quotes, _ = f.quotes(list(TICKERS))
        except Exception as e:
            _state["last_error"] = f"quotes: {type(e).__name__}"
    if hm >= "09:30":
        with _lock:
            manage(now, quotes or {})
    if hm >= sess.get("close", "16:00"):
        if f.ready() and not store.kv_get(f"{LEDGER}:labeled:{day}"):
            n = label_day(day, f)
            store.kv_set(f"{LEDGER}:labeled:{day}", {"n": n, "at": now.isoformat(timespec="seconds")})
            if day.weekday() == 4 and on:
                w = week_summary(day)
                if w:
                    import alerts
                    alerts.alert("copilot", w[0], w[1], f"copilot:week:{day}", "normal")
        _state["status"] = "closed; alerts labeled"
        return
    if hm < "09:35" or not f.ready():
        _state["status"] = "waiting for the session / Schwab"
        return
    with _lock:
        if not on:
            _state["status"] = 'config/v4.json "copilot" is off'
            return
        ev = events(now)
        briefing(now, ev)
        new = []
        for t in TICKERS:
            try:
                new += scan(t, day, now, f, ev)
            except Exception as e:
                _state["last_error"] = f"scan {t}: {type(e).__name__}: {e}"[:200]
        if new:
            groups, pmin = {}, push_min()
            for a in new:
                groups.setdefault((a["ticker"], a["tf"], a["bar_t"]), []).append(a)
            plan_ = []
            for grp in groups.values():
                grp, title, body = group_push(grp)
                top = grp[0]
                top["pushed"] = top["checklist_score"] >= pmin
                plan_.append((grp, title, body))
            store.kv_set(_akey(str(day)), alerts_for(day) + new)
            import alerts
            for grp, title, body in plan_:
                top = grp[0]
                if top["pushed"]:
                    alerts.alert("copilot", title, body, top["id"], "high" if top["checklist_score"] >= 6 else "normal")
                else:
                    store.event("copilot", f"{title} | {top['checklist_score']}/7 boxes, below the push bar ({pmin})", "", top["id"])
                for a in grp:
                    if paper:
                        got, why = _shadow(a, now, quotes)
                        S.decide(f"{LEDGER}:{a['id']}", LEDGER, a["ticker"], "SHADOW" if got else "NO SHADOW", [why],
                                 {"alert": a["id"]}, "entry", VERSION)
    _state["status"] = f"watching {', '.join(TICKERS)} ({len(alerts_for(day))} alerts today)"
    _state["step_s"] = round(time.time() - t0, 2)


def _run():
    import health
    while not _state["stop"]:
        try:
            step()
            health.beat("copilot", True, _state.get("status"), _state.get("step_s"))
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {e}"[:200]
            health.beat("copilot", False, _state["last_error"], None)
        time.sleep(STEP_S)


def start():
    if _state["thread"] and _state["thread"].is_alive():
        return True
    on, _ = switches()
    if not on:
        return False
    _state["stop"] = False
    th = threading.Thread(target=_run, daemon=True, name="copilot")
    _state["thread"] = th
    th.start()
    return True


def status(day=None):
    day = day or str(core.now_et().date())
    on, paper = switches()
    return {"version": VERSION, "status": _state["status"], "last_error": _state["last_error"], "step_s": _state["step_s"],
            "switch": on, "paper_shadow": paper, "watch_only": on and not paper, "tickers": list(TICKERS), "push_min": push_min(),
            "alerts": alerts_for(day), "open": [p["id"] for p in S.positions(ledger=LEDGER, status="OPEN")],
            "evidence": EVIDENCE, "label": "CONTEXT alerts (not tested edges); shadow trades are PAPER (simulated fills)"}
