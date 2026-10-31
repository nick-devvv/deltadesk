"""noise_trend.py - v4 index ledger `noise_trend` (docs/STRATEGY_PLAN.md section 3.5). PRE-REGISTERED, unvalidated.

Same entries and exits as `noise` (half-hour band checks, max/min(band, VWAP) stop at the checks, reversal exit, the
20% premium line, all out 15:25), taken only when a trend-day score known AT THE CHECK says so. Thresholds frozen
2026-10-31, before testing (basis: Gao, Han, Li & Zhou 2018, JFE: intraday momentum is stronger on volatile, high-volume
and macro-news days):
  (a) VIX at the check above the median of its last 20 daily closes   (Schwab $VIX quote; unknown if unavailable)
  (b) 09:30-10:00 volume >= 1.5 x its 14-session average for that half hour
  (c) |09:30-10:00 return| above its 14-session average
  (d) FOMC, CPI or jobs-report day (config/events.json; FOMC also from config/v4.json; unknown if no calendar)
Trade when at least 2 of the KNOWN conditions are true (an unknown condition never counts as true or false). The score
is recorded on every check, traded or not, with each condition's inputs. Every input is from before the check: the
first check is 10:00, when the 09:30-09:59 bars have all finished.
"""
import statistics
import time

import pandas as pd

import noise_variants as NV
import store
import v4common as C

VERSION = "2026-11-02.v4-noise_trend"
LEDGER = "noise_trend"
VOL_MULT = 1.5
LOOKBACK = 14
VIX_MEDIAN_DAYS = 20
MIN_SCORE = 2
vix_source = None                        # tests: lambda now -> (vix_now or None, median or None, note)


def first_half_hour(m1, day):
    """(volume, return) of 09:30-09:59 on `day` from 1m bars, or (None, None) if any of the 30 bars is missing."""
    r = C.rth_day(m1, day)
    if r is None or not len(r):
        return None, None
    w = r[r.index.strftime("%H:%M") < "10:00"]
    if len(w) < 30:
        return None, None
    return float(w["Volume"].sum()), float(w["Close"].iloc[-1]) / float(w["Open"].iloc[0]) - 1


def history(m1, day, lookback=LOOKBACK):
    days = sorted({d for d in m1.index.date if d < day})
    vols, rets = [], []
    for d in reversed(days):
        v, r = first_half_hour(m1, d)
        if v is None:
            continue
        vols.append(v)
        rets.append(abs(r))
        if len(vols) >= lookback:
            break
    return vols, rets


def _vix_default(now):
    """Schwab $VIX: the live quote (<= 120 s old) and the median of the last 20 daily closes before today."""
    import marketdata
    vnow, med, notes = None, None, []
    try:
        q = marketdata.quote("$VIX")
        qt = (q or {}).get("quote_time") or (q or {}).get("trade_time")        # an index has trades, not always quotes
        if q and q.get("last") and qt is not None:
            age = (pd.Timestamp(now) - pd.Timestamp(qt)).total_seconds()
            if age <= 120:
                vnow = float(q["last"])
            else:
                notes.append(f"VIX quote {age:.0f}s old")
        else:
            notes.append("no VIX quote")
    except Exception as e:
        notes.append(f"VIX quote failed ({type(e).__name__})")
    key = f"v4_vix_hist:{now.date()}"
    hist = store.kv_get(key)
    if hist is None and marketdata._provider is None and time.time() - _state.get("vix_try", 0) > 600:
        _state["vix_try"] = time.time()
        try:
            import schwab
            d = schwab.bars_daily("$VIX")
            if d is not None and len(d):
                closes = [float(x) for i, x in zip(d.index, d["Close"]) if pd.Timestamp(i).date() < now.date()]
                hist = closes[-VIX_MEDIAN_DAYS:]
                store.kv_set(key, hist)
        except Exception as e:
            notes.append(f"VIX history failed ({type(e).__name__})")
    if hist and len(hist) >= VIX_MEDIAN_DAYS:
        med = float(statistics.median(hist[-VIX_MEDIAN_DAYS:]))
    elif hist is not None:
        notes.append(f"VIX history has {len(hist)} closes (needs {VIX_MEDIAN_DAYS})")
    else:
        notes.append("no VIX history")
    return vnow, med, "; ".join(notes)


_state = {}


def score(m1, day, now, cal=None):
    """The trend-day score at a check. Pure apart from the VIX source. Returns a dict with every input."""
    out = {"conditions": {}, "inputs": {}, "known": 0, "true": 0}
    vnow, vmed, note = (vix_source or _vix_default)(now)
    out["inputs"]["vix"] = {"now": vnow, "median20": vmed, "note": note}
    out["conditions"]["a_vix_above_median"] = (vnow > vmed) if (vnow is not None and vmed is not None) else None
    v_today, r_today = first_half_hour(m1, day)
    vols, rets = history(m1, day)
    ok_hist = len(vols) >= LOOKBACK
    out["inputs"]["first_half_hour"] = {"volume": v_today, "return": r_today, "sessions": len(vols),
                                        "avg_volume": (sum(vols) / len(vols)) if vols else None,
                                        "avg_abs_return": (sum(rets) / len(rets)) if rets else None}
    out["conditions"]["b_volume_1_5x"] = (v_today >= VOL_MULT * (sum(vols) / len(vols))) if (v_today is not None and ok_hist) else None
    out["conditions"]["c_abs_return_above_avg"] = (abs(r_today) > (sum(rets) / len(rets))) if (r_today is not None and ok_hist) else None
    cal = cal or C.calendar(now)
    md = C.macro_day(now)
    out["inputs"]["calendar"] = {"source": cal["source"], "fomc": cal["fomc"], "cpi": cal["cpi"], "jobs": cal["jobs"]}
    out["conditions"]["d_macro_day"] = md
    known = {k: v for k, v in out["conditions"].items() if v is not None}
    out["known"], out["true"] = len(known), sum(1 for v in known.values() if v)
    out["trade"] = out["true"] >= MIN_SCORE
    out["rule"] = f">= {MIN_SCORE} of the known conditions true"
    return out


class NoiseTrend(NV.Variant):
    ledger = LEDGER
    book = "index"
    version = VERSION
    reversal_exit = True

    def entry_filter(self, ticker, st, snap, t_end, now):
        s = score(snap.get("m1"), now.date(), now)
        return bool(s["trade"]), s


V = NoiseTrend()


def tick(ticker, snap, chain_rows_fn, now=None):
    return NV.tick(V, ticker, snap, chain_rows_fn, now)


def manage(p, now=None):
    return NV.manage(V, p, now)
