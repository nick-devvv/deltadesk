"""core.py - policy, market calendar/session, and risk math. Pure code, no AI, no network.

Everything that decides a stop, a size or a time limit lives here so the paper engine,
the real-trade plan, the UI and Chart all use the same numbers (policy version included).
"""
import json
import math
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HERE = Path(__file__).resolve().parent
POLICY_FILE = HERE / "config" / "policy.json"

# NYSE calendar (source: NYSE Group 2026-2028 holiday and early closings announcement, checked Oct 27 2026)
HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
    "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05",
    "2027-09-06", "2027-11-25", "2027-12-24",
}
EARLY_CLOSE = {"2026-11-27", "2026-12-24", "2027-11-26"}  # 1:00 PM ET close


# ---------------- policy ----------------
_POLICY = None


def policy(reload=False):
    global _POLICY
    if _POLICY is None or reload:
        p = json.loads(POLICY_FILE.read_text())
        validate_policy(p)
        _POLICY = p
    return _POLICY


def validate_policy(p):
    r = p["risk"]
    assert 0 < r["stop_cap_pct"] <= 0.20, "stop cap must be within (0, 20%] (Nick's ceiling)"
    for w in p["windows"]:
        assert 0 < w.get("stop_pct", r["stop_cap_pct"]) <= r["stop_cap_pct"], "window stop can't be looser than the cap"
    assert r["daily_loss_usd"] is None or r["daily_loss_usd"] > 0
    for k in ("trend_A", "trend_B", "chop"):
        v = r["per_trade_cap"][k]
        assert v is None or v > 0
    prev = "00:00"
    for w in p["windows"]:
        assert w["start"] >= prev and w["end"] > w["start"], "windows must be ordered"
        assert w["be"] > 1 and w["t1_hi"] >= w["t1_lo"] > w["be"], "BE < T1 lo <= T1 hi"
        prev = w["end"]
    s = p["session"]
    assert s["first_entry"] < s["last_entry"] < s["all_out"]
    return True


def now_et():
    return datetime.now(ET)


def hm(t):
    return t.strftime("%H:%M")


# ---------------- session ----------------
def session_info(t=None):
    """What the market/desk allows right now."""
    t = t or now_et()
    p = policy()["session"]
    d = t.strftime("%Y-%m-%d")
    early = d in EARLY_CLOSE
    out = {"date": d, "time": hm(t), "early_close": early, "holiday": d in HOLIDAYS or t.weekday() >= 5}
    close = "13:00" if early else "16:00"
    last_entry = p["early_close_last_entry"] if early else p["last_entry"]
    all_out = p["early_close_all_out"] if early else p["all_out"]
    out.update(close=close, last_entry=last_entry, all_out=all_out)
    x = hm(t)
    if out["holiday"]:
        state = "CLOSED (holiday/weekend)"
    elif x < "04:00" or x >= "20:00":
        state = "CLOSED"
    elif x < "09:30":
        state = "PREMARKET"
    elif x < p["orb_end"]:
        state = "ORB FORMING"
    elif x < last_entry:
        state = "OPEN"
    elif x < all_out:
        state = "NO NEW ENTRIES"
    elif x < close:
        state = "ALL OUT"
    else:
        state = "AFTER HOURS"
    out["state"] = state
    out["entries_allowed"] = state == "OPEN"
    out["window"] = window_for(x)["name"] if window_for(x) else None
    return out


def window_for(hhmm):
    for w in policy()["windows"]:
        if w["start"] <= hhmm < w["end"]:
            return w
    return None


# ---------------- risk math ----------------
def cents_up(x):
    return math.ceil(round(x * 100, 6)) / 100


def cents_down(x):
    return math.floor(round(x * 100, 6)) / 100


def stop_for(fill, spread=None, structural_stop=None, pct=None):
    """Initial premium stop under Nick's 20% planned-loss ceiling.

    Gross boundary = fill x 0.80. The trigger sits higher to reserve slippage s and fees C so that the
    stressed loss 100*(F - S + s) + C <= 20% of premium paid. A tighter structural stop wins.
    Returns (stop_trigger, slippage_reserve).
    """
    r = policy()["risk"]
    s = max(r["slippage_min"], (spread or 0) * r["slippage_spread_frac"])
    c = r["fees_per_contract_roundtrip"]
    stop = cents_up(fill * (1 - r["stop_cap_pct"]) + s + c / 100)      # 20% all-in ceiling (costs reserved)
    if pct is not None and pct < r["stop_cap_pct"]:
        stop = max(stop, cents_up(fill * (1 - pct)))                      # tighter time-of-day stop (gross % of fill)
    if structural_stop is not None and structural_stop > stop:
        stop = cents_up(structural_stop)
    return stop, round(s, 4)  # may be >= fill: then the trade cannot fit the 20% cap after costs (size -> 0)


def risk_per_contract(fill, stop, slip):
    return round(100 * (fill - stop + slip) + policy()["risk"]["fees_per_contract_roundtrip"], 2)


def size(fill, stop, slip, grade, budget_left, chop_day=False):
    """Contracts that fit: grade cap, per-trade $ cap, remaining daily/weekly budget. Never rounds up."""
    p = policy()
    r, d = p["risk"], p["discipline"]
    rpc = risk_per_contract(fill, stop, slip)
    cap = float("inf") if budget_left is None else budget_left
    pc = per_trade_cap(grade, chop_day)
    if pc is not None:
        cap = min(cap, pc)
    by_grade = p["sizing_by_grade"].get(grade, 0)
    if chop_day:
        by_grade = min(by_grade, d["chop_day_max_contracts"])
    by_grade = min(by_grade, r["max_contracts"])
    if stop >= fill or rpc > 100 * fill * r["stop_cap_pct"] + 1e-9:
        return 0, rpc, round(cap, 2), "can't fit the 20% loss cap after spread/fees at this price"
    fit = (10 ** 6 if cap == float("inf") else int(cap // rpc)) if rpc > 0 else 0
    q = max(0, min(by_grade, fit))
    why = None
    if q == 0:
        why = ("grade C: watch only" if by_grade == 0 else
               f"1 contract risks ${rpc:.2f}, over the ${cap:.2f} allowed (per-trade cap/remaining budget)")
    return q, rpc, (None if cap == float("inf") else round(cap, 2)), why


def per_trade_cap(grade, chop_day):
    c = policy()["risk"]["per_trade_cap"]
    return c["chop"] if chop_day else c["trend_A"] if grade == "A" else c["trend_B"]


def exit_plan(fill, t_entry_hhmm, spread=None, structural_stop=None):
    """All fill-based management numbers for one trade."""
    w = window_for(t_entry_hhmm) or policy()["windows"][-1]
    stop, slip = stop_for(fill, spread, structural_stop, w.get("stop_pct"))
    pick = policy()["exit_profile"]["t1_pick"]
    t1m = w["t1_lo"] if pick == "low" else (w["t1_lo"] + w["t1_hi"]) / 2
    flat_by = (datetime.strptime(t_entry_hhmm, "%H:%M") + timedelta(minutes=w["flat_min"])).strftime("%H:%M")
    return {
        "window": w["name"], "fill": round(fill, 2), "stop": stop, "slippage_reserve": slip,
        "stop_pct": w.get("stop_pct", policy()["risk"]["stop_cap_pct"]),
        "gross_20pct_boundary": round(fill * (1 - policy()["risk"]["stop_cap_pct"]), 2),
        "be_trigger": cents_up(fill * w["be"]), "be_stop": round(fill, 2),
        "t1": cents_up(fill * t1m), "t1_range": [cents_up(fill * w["t1_lo"]), cents_up(fill * w["t1_hi"])],
        "lock_after_t1": cents_up(fill * w["be"]),
        "flat_by": flat_by, "all_out": session_info()["all_out"],
        "reward_risk_at_t1": round((fill * t1m - fill) / max(fill - stop, 0.01), 2),
        "policy_version": policy()["version"],
    }


def tighten_only(old_stop, new_stop):
    """Stops never move down (never widen a losing trade)."""
    return max(old_stop or 0, new_stop)


# ---------------- budget accounting ----------------
def projected_day(realized, unrealized, extra_open_loss, pending_reserved):
    """Projected day P&L = R + U - E - P (signed). Must stay above -daily limit."""
    return round(realized + unrealized - extra_open_loss - pending_reserved, 2)


def budget_left(realized_day, unrealized, open_risk, realized_week):
    """No dollar limits by default (None). If a daily/weekly $ limit is configured, it applies."""
    r = policy()["risk"]
    day_left = None if r["daily_loss_usd"] is None else round(r["daily_loss_usd"] + projected_day(realized_day, unrealized, open_risk, 0), 2)
    week_left = None if r["weekly_loss_usd"] is None else round(r["weekly_loss_usd"] + realized_week + unrealized - open_risk, 2)
    lims = [v for v in (day_left, week_left) if v is not None]
    return (round(max(0.0, min(lims)), 2) if lims else None), day_left, week_left


def week_start(d=None):
    d = d or now_et().date()
    return (d - timedelta(days=d.weekday())).isoformat()


# ---------------- greeks fallback ----------------
def bs_delta(spot, strike, iv, side, now=None, r=0.04):
    """Black-Scholes delta, used ONLY when the broker sends no delta but does send implied volatility.
    Time = minutes left to the 4:00 PM close (0DTE), floored at 5 minutes. Labeled 'estimated' everywhere."""
    if not (spot and strike and iv) or iv <= 0:
        return None
    now = now or now_et()
    close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    t = max((close - now).total_seconds(), 300) / (365 * 24 * 3600)
    d1 = (math.log(spot / strike) + (r + iv * iv / 2) * t) / (iv * math.sqrt(t))
    nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    return round(nd1 if side.upper().startswith("C") else nd1 - 1, 3)


def time_bucket(hhmm):
    """Time-of-day bucket for journal breakdowns."""
    if hhmm < "10:30":
        return "Open 9:30-10:30"
    if hhmm < "12:00":
        return "Morning 10:30-12"
    if hhmm < "14:00":
        return "Midday 12-2"
    if hhmm < "15:00":
        return "Afternoon 2-3"
    return "Power hour 3-close"
