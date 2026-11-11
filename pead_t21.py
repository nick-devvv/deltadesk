"""pead_t21.py - post-earnings drift on S&P 500 shares: PAPER (simulated fills on live Schwab quotes), multi-day holds.
REGISTERED 2026-11-11, before any forward trade. Not promoted. Never real money (there is no order path here).

Scope: Nick widened the desk to any holding period on 2026-11-11 and said "yes" to this paper ledger the same day. It
holds positions across sessions in its own isolated multi-day risk book ("pead", v4risk) and its own worker thread, and
it never calls v4exec.overnight(), so the day-trading ledgers' "close anything left from an earlier session" rule never
touches it.

Source and evidence (labels: BACKTEST = historical simulation, PAPER = this ledger's simulated fills)
  Rule family: Bernard & Thomas (1989); Chan, Jegadeesh & Lakonishok (1996); Brandt, Kishore, Santa-Clara &
  Venkatachalam (2008): stocks keep drifting after a big earnings-announcement return. Pre-registered as T21
  (TradingVault Research/2026-11-11-t21-t22-prereg, approved by Nick 2026-11-11, rules locked before any result).
  Data: WRDS CRSP daily (survivorship-free) + I/B/E/S announcement dates and times.
    BACKTEST research 1997-2021: 4,717 trades, +1.69%/trade after costs (2x costs +1.49%), 90% CI +1.23 to +2.16%,
      4/5 sub-periods positive (2007-11 -1.20%), random entries in the same stocks p90 +0.98%, win 59%, PF 1.57.
      $3k view (5 x $600): CAGR 6.1%, worst drop -28%.
    BACKTEST sealed 2022-2025 (out-of-sample, run once, pass criterion fixed before download): 852 trades,
      +1.24%/trade after costs, 90% CI +0.29 to +2.08%, random median +0.53%, PF 1.49. Market-adjusted -0.03%/trade
      (SPY over the same days +1.28%). $3k view: CAGR 7.95%, worst drop -15%.
  Trials counted for the deflated Sharpe: TradingVault Ledger/variants-tried.md (T21 = row 85; 36 WRDS trials).

Rules (frozen; any change ships as a new ledger version and the forward count starts over)
  Universe   S&P 500 members (config/sp500.json snapshot, as_of in the file). Long only.
  Event      an SEC 8-K (not 8-K/A) that lists Item 2.02 (results of operations), from EDGAR's submissions API.
             Reaction day = the filing's acceptance day if before 16:00 ET and a session, otherwise the next session
             (the backtest's I/B/E/S rule, with SEC acceptance time in place of the I/B/E/S announcement time).
  EAR        the stock's close-to-close return minus SPY's from the close 2 sessions before the reaction day to the
             close 1 session after it (3 days). Known at the close of reaction + 1 (the "signal day").
  Cutoff     the 90th percentile (numpy linear) of all S&P 500 EARs whose signal day falls in the 365 calendar days
             before this signal day (strictly before). Needs at least 200 of them, else no entry.
  Entry      if EAR >= cutoff: buy at the next open (the session after the signal day): the first executable quote
             dated at least the decision latency after 09:30:00 ET and under 20 s old, at ask + $0.01. No fill by
             09:40 -> MISSED (recorded).
  Exit       at the close of the 20th session after the entry day: the first fresh quote at or after 5 minutes before
             the close, sold at bid - $0.01. No fill by 30 s before the close -> the exit is PENDING and fills at the
             next open's first valid quote (LATE). No stop, no target.
  Positions  one per symbol; at most 5 open; same-day signals taken in ticker order (the backtest used permno order:
             also arbitrary). A position exiting at today's close still holds its slot at today's open (the
             backtest's portfolio credited a sale at the next open).
  Size       $600 notional per slot, cut so a 3-sigma one-day move (20-day close-to-close sigma) is at most $45
             (1.5% of $3,000, the approved risk framework's swing-book rule); fractional shares to 4 decimals.
  Risk       v4risk book "pead" (isolated, multi-day): book and per-symbol caps, the v4 kill switch, the emergency
             pause, and the daily stop (no new entries after -$90 today, realized + open marks measured from the
             previous session's last mark). Exits are never blocked. risk_usd = 3 x sigma20 x notional.
  Switch     config/v4.json "pead_t21": true/false. Off stops new entries only; open positions still exit by rule.
Known deviations from the backtest: SEC 8-K Item 2.02 acceptance time instead of I/B/E/S announcement date/time (a
company that files its 8-K a session after the release shifts the window by one day; a mid-quarter 2.02 filing counts as
an event); today's S&P 500 list for every event in the cutoff window (the backtest used membership on the reaction day);
Schwab daily closes (split-adjusted, no dividends) instead of CRSP total returns; class shares (BRK.B, BF.B) only if
Schwab serves that symbol; the first fresh quote after 09:30 instead of the official open; 5 minutes before the close
at the bid instead of the official close; the risk-framework size cap (the backtest always used $600); dividends are
not credited to paper P/L.
Promotion (CLAUDE.md step 5, gate G5): 40 forward paper trades whose fills match the backtest's cost assumption.

Take-profit twin `pead_t21_tp` (T23a; added 2026-11-11 after Nick asked for take-profits; REGISTERED before any trade)
  Same signals, entries, sizing and day-20 exit as pead_t21, in its own 5 slots, plus a take-profit: target = entry fill
  x (1 + sigma20 x sqrt(20)) (sigma20 as above, through the signal day). Once a day, on the first fresh quote in the
  5-minute window before the close (the entry day included), a bid at or above the target sells at bid - $0.01. The
  parent keeps running unchanged (CLAUDE.md: version, don't overwrite). Pre-registered as T23a (TradingVault
  Research/2026-11-11-t23-prereg; 39 WRDS trials).
    BACKTEST research 1997-2021 (same run as T21): +1.76%/trade after costs (T21 +1.69%), CI +1.31 to +2.21%, TP hit in
      15% of trades (average target +15%), random p90 +0.91%; $3k (5 x $600) $206/yr vs T21 $184/yr, worst drop -22%
      vs -28%.
    BACKTEST sealed 2022-2025 (run once): +1.21%/trade (T21 +1.24%), random median +0.39%; $3k $253/yr vs T21
      $239/yr, worst drop -15% (both). Passed: more dollars than T21 in both windows.
  Deviations (beyond the parent's): the bid in the last 5 minutes instead of the official close; the target is measured
  from the entry fill (ask + $0.01) instead of the official open.
"""
import json
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

LEDGER, BOOK = "pead_t21", "pead"
TP_LEDGER = "pead_t21_tp"
LEDGERS = (LEDGER, TP_LEDGER)
VERSION = "2026-11-11.pead-t21-1"            # the parent's rules (unchanged)
TP_VERSION = "2026-11-11.pead-t21-tp-1"      # the take-profit twin (T23a)
TP_K = math.sqrt(20.0)
HOLD, PCT, MIN_N, WINDOW_DAYS = 20, 90.0, 200, 365
SLOTS, SLOT_USD, RISK_CAP_USD = 5, 600.0, 45.0
SIGMA_DAYS = 20
WORK_FROM, PLAN_FROM, OPEN, FILL_LATE = "05:00", "08:00", "09:30", "09:40"
EXIT_BEFORE_CLOSE_S, EXIT_GIVE_UP_S = 300, 30
QUOTE_MAX_AGE_S = 20
MARK_EVERY_S = 60
EDGAR_BATCH, EDGAR_PAUSE_S, EDGAR_KEEP_DAYS = 8, 0.15, 450
SEED_BATCH = 10
SP500_FILE = core.HERE / "config" / "sp500.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
LABEL = "PAPER (simulated fills); rules = T21, BACKTEST research 1997-2021 pass + sealed 2022-2025 pass (out-of-sample)"
TP_LABEL = "PAPER (simulated fills); rules = T23a (T21 + take-profit), BACKTEST research 1997-2021 pass + sealed 2022-2025 pass"
BACKTEST = {"research_1997_2021": {"label": "BACKTEST (research window)", "trades": 4717, "win_rate": 58.9,
                                   "mean_pct_after_costs": 1.69, "mean_pct_2x_cost": 1.49, "profit_factor": 1.57,
                                   "ci90_pct": [1.23, 2.16], "random_p90_pct": 0.98,
                                   "portfolio_5x600": {"cagr_pct": 6.1, "sharpe": 0.43, "max_dd_pct": -27.8}},
            "sealed_2022_2025": {"label": "BACKTEST (sealed, out-of-sample, run once)", "trades": 852, "win_rate": 54.7,
                                 "mean_pct_after_costs": 1.24, "mean_pct_2x_cost": 1.04, "profit_factor": 1.49,
                                 "ci90_pct": [0.29, 2.08], "random_median_pct": 0.53, "market_adjusted_pct": -0.03,
                                 "portfolio_5x600": {"cagr_pct": 7.95, "sharpe": 0.34, "max_dd_pct": -14.8}}}
TP_BACKTEST = {"research_1997_2021": {"label": "BACKTEST (research window, same run as T21)", "trades": 4717, "win_rate": 59.2,
                                      "mean_pct_after_costs": 1.76, "mean_pct_2x_cost": 1.56, "profit_factor": 1.59,
                                      "ci90_pct": [1.31, 2.21], "random_p90_pct": 0.91, "tp_hit_pct": 14.9,
                                      "portfolio_5x600": {"dollars_per_year": 206, "t21_dollars_per_year": 184, "max_dd_pct": -21.9}},
               "sealed_2022_2025": {"label": "BACKTEST (sealed, out-of-sample, run once)", "trades": 852, "win_rate": 54.9,
                                    "mean_pct_after_costs": 1.21, "mean_pct_2x_cost": 1.01, "profit_factor": 1.48,
                                    "ci90_pct": [0.30, 2.01], "random_median_pct": 0.39, "tp_hit_pct": 12.3,
                                    "portfolio_5x600": {"dollars_per_year": 253, "t21_dollars_per_year": 239, "max_dd_pct": -15.0}}}
_state = {"status": "idle", "last_error": None, "thread": None, "stop": False, "step_s": None, "mark_t": None,
          "plan_try": None, "edgar_pos": 0, "seed_pos": 0, "tz_mode": None}
_lock = threading.RLock()


def fetch():
    import scanner
    return scanner._fetch


def sec_get(url):
    """SEC EDGAR GET with the desk's SEC User-Agent (catalysts.sec_headers). Tests replace this."""
    import catalysts
    return catalysts._http(url, timeout=15)


def switch_on(ledger=LEDGER):
    """config/v4.json "pead_t21" / "pead_t21_tp" (missing = off). Off stops new entries; exits always run."""
    import retire
    return bool(retire.cfg().get(ledger, False))


def universe():
    """[(ticker, cik)] from config/sp500.json."""
    try:
        d = json.loads(SP500_FILE.read_text())
        return [(r["ticker"].upper(), int(r["cik"])) for r in d["tickers"]]
    except Exception:
        return []


# ================================================================ pure rules (no network, no clock)
def is_session(d):
    return d.weekday() < 5 and d.isoformat() not in core.HOLIDAYS


def next_session(d):
    d = d + timedelta(days=1)
    while not is_session(d):
        d += timedelta(days=1)
    return d


def prev_session(d):
    d = d - timedelta(days=1)
    while not is_session(d):
        d -= timedelta(days=1)
    return d


def add_sessions(d, n):
    for _ in range(n):
        d = next_session(d)
    return d


def parse_filings(sub, since):
    """EDGAR submissions JSON -> [[acceptance (as given), items, accession]] for 8-K filings listing Item 2.02 and
    filed on or after `since` (date). 8-K/A amendments are not events."""
    rec = ((sub or {}).get("filings") or {}).get("recent") or {}
    out = []
    for form, fd, acc, items, an in zip(rec.get("form", []), rec.get("filingDate", []), rec.get("acceptanceDateTime", []),
                                         rec.get("items", []), rec.get("accessionNumber", [])):
        if form != "8-K" or "2.02" not in str(items or "").split(","):
            continue
        try:
            if date.fromisoformat(str(fd)[:10]) < since:
                continue
        except ValueError:
            continue
        out.append([str(acc), str(items), str(an)])
    return out


def tz_mode(accepts):
    """EDGAR's acceptanceDateTime ends in 'Z'. EDGAR accepts filings 06:00-22:00 ET only, so true UTC stamps put
    almost nothing at 06:00-09:59 and many after-close earnings filings at 20:00-01:59; Eastern stamps are the reverse.
    'UTC' if the late-hours count beats the early-hours count, else 'ET'."""
    early = late = 0
    for a in accepts:
        try:
            h = int(str(a)[11:13])
        except ValueError:
            continue
        if 6 <= h < 10:
            early += 1
        elif h >= 20 or h < 2:
            late += 1
    return "UTC" if late > early else "ET"


def accept_et(a, mode):
    """Acceptance time as an ET datetime."""
    t = pd.Timestamp(str(a).replace("Z", "").split(".")[0])
    if mode == "UTC":
        return t.tz_localize("UTC").tz_convert(core.ET).to_pydatetime()
    return t.tz_localize(core.ET).to_pydatetime()


def react_day(t_et):
    """The I/B/E/S-style reaction day: the acceptance day if it's a session and before 16:00 ET, else the next session."""
    d = t_et.date()
    if is_session(d) and t_et.strftime("%H:%M") < "16:00":
        return d
    return next_session(d)


def finished_daily(daily, day):
    """Daily bars dated strictly before `day` (finished sessions only), sorted, duplicates dropped."""
    if daily is None or not len(daily) or "Close" not in daily:
        return None
    d = daily.copy()
    d.index = pd.DatetimeIndex(d.index)
    if d.index.tz is not None:
        d.index = d.index.tz_convert(core.ET).tz_localize(None)
    d.index = d.index.normalize()
    d = d[~d.index.duplicated(keep="last")].sort_index()
    return d[d.index < pd.Timestamp(day)]


def ear(stock, spy, react):
    """(EAR, signal_day) from finished daily bars, or (None, signal_day) if a close is missing. EAR = close(r+1) /
    close(r-2) for the stock minus the same for SPY (the backtest: CRSP returns from the close of r-2 to r+1)."""
    s, r2 = next_session(react), prev_session(prev_session(react))
    try:
        a = float(stock["Close"].loc[pd.Timestamp(s)]) / float(stock["Close"].loc[pd.Timestamp(r2)])
        b = float(spy["Close"].loc[pd.Timestamp(s)]) / float(spy["Close"].loc[pd.Timestamp(r2)])
    except (KeyError, TypeError, ZeroDivisionError):
        return None, s
    if not (a == a and b == b) or a <= 0 or b <= 0:
        return None, s
    return a - b, s


def cutoff(ears, s):
    """(90th percentile or None, n): EARs (dicts with 'ear' and 's') whose signal day is in [s - 365 days, s)."""
    lo = s - timedelta(days=WINDOW_DAYS)
    vals = [e["ear"] for e in ears if e.get("ear") is not None and lo <= date.fromisoformat(e["s"]) < s]
    if len(vals) < MIN_N:
        return None, len(vals)
    return float(np.percentile(np.array(vals, dtype=float), PCT)), len(vals)


def sigma20(daily, day):
    d = finished_daily(daily, day)
    if d is None or len(d) < SIGMA_DAYS + 1:
        return None
    r = d["Close"].astype(float).pct_change().dropna().iloc[-SIGMA_DAYS:]
    s = float(r.std())
    return s if s == s and s > 0 else None


def size(fill, sigma):
    """(qty, notional): $600 notional, cut so 3 x sigma x notional <= $45; fractional shares (4 decimals)."""
    if not fill or fill <= 0 or not sigma or sigma <= 0:
        return 0.0, 0.0
    usd = min(SLOT_USD, RISK_CAP_USD / (3.0 * sigma))
    q = math.floor(usd / fill * 10_000) / 10_000
    return q, round(q * fill, 2)


def tp_target(fill, sigma):
    """The take-profit price for pead_t21_tp: fill x (1 + sigma20 x sqrt(20)); None without a sigma."""
    if not fill or not sigma or sigma <= 0:
        return None
    return round(fill * (1 + sigma * TP_K), 4)


def _r(x, k=4):
    return None if x is None or (isinstance(x, float) and x != x) else round(float(x), k)


# ================================================================ stores (kv): EDGAR filings and computed EARs
def _edgar():
    return store.kv_get("pead:edgar") or {}


def _ears():
    return store.kv_get("pead:ears") or {}


def events(day):
    """[{'ticker', 'react', 'accept', 'acc'}] from the stored filings, acceptance times read in the detected zone."""
    eg = _edgar()
    allacc = [f[0] for v in eg.values() for f in v.get("f", [])]
    mode = tz_mode(allacc)
    _state["tz_mode"] = mode
    out = []
    for t, v in eg.items():
        for a, items, an in v.get("f", []):
            try:
                te = accept_et(a, mode)
            except Exception:
                continue
            out.append({"ticker": t, "react": react_day(te), "accept": te.isoformat(timespec="seconds"), "acc": an})
    # one event per ticker per reaction day
    seen, uniq = set(), []
    for e in sorted(out, key=lambda e: (e["ticker"], e["react"], e["accept"])):
        k = (e["ticker"], e["react"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq


def refresh_edgar(day, budget=EDGAR_BATCH):
    """One batch of EDGAR submissions refreshes (each ticker once per day). Returns True when every ticker is fresh."""
    uni = universe()
    eg = _edgar()
    todo = [(t, c) for t, c in uni if (eg.get(t) or {}).get("day") != str(day)]
    since = day - timedelta(days=EDGAR_KEEP_DAYS)
    for t, cik in todo[:budget]:
        try:
            raw = sec_get(SUBMISSIONS.format(cik=cik))
            fl = parse_filings(json.loads(raw), since)
            eg[t] = {"day": str(day), "f": fl}
        except Exception as e:
            eg[t] = {"day": str(day), "f": (eg.get(t) or {}).get("f", []), "err": type(e).__name__}
            _state["last_error"] = f"EDGAR {t}: {type(e).__name__}"
        if EDGAR_PAUSE_S:
            time.sleep(EDGAR_PAUSE_S)                     # SEC fair access: well under 10 requests a second
    store.kv_set("pead:edgar", eg)
    return len(todo) <= budget


def _ear_key(t, react):
    return f"{t}|{react}"


def seed_ears(day, budget=SEED_BATCH):
    """Compute and store EARs for events whose signal day is in the cutoff window (and before `day`) and that aren't
    stored yet, a few tickers per call. Returns (done, tickers_left)."""
    lo = day - timedelta(days=WINDOW_DAYS + 7)
    ev = [e for e in events(day) if lo <= next_session(e["react"]) < day]
    have = _ears()
    need = {}
    for e in ev:
        if _ear_key(e["ticker"], e["react"]) not in have:
            need.setdefault(e["ticker"], []).append(e)
    if not need:
        return True, 0
    f = fetch()
    spy = finished_daily(f.daily("SPY"), day)
    if spy is None:
        return False, len(need)
    for t in sorted(need)[:budget]:
        try:
            dly = finished_daily(f.daily(t), day)
        except Exception as e:
            dly = None
            _state["last_error"] = f"daily {t}: {type(e).__name__}"
        for e in need[t]:
            x, s = ear(dly, spy, e["react"]) if dly is not None else (None, next_session(e["react"]))
            if x is None and dly is not None and len(dly) and dly.index[-1] < pd.Timestamp(s):
                continue                                  # the signal day's bar isn't finished yet: try again later
            have[_ear_key(t, e["react"])] = {"ticker": t, "react": str(e["react"]), "s": str(s), "ear": _r(x, 6),
                                              "why": None if x is not None else "missing close (or no bars) for the EAR window"}
    store.kv_set("pead:ears", have)
    return len(need) <= budget, max(0, len(need) - budget)


def due_exits(day, ledger=LEDGER):
    """(ids exiting at today's close, ids past their exit day: sold at today's open, LATE). From each open position's
    stored exit day only, so an exit never waits for the morning plan or for market data."""
    opens = S.positions(ledger=ledger, status="OPEN")
    close_ids = [p["id"] for p in opens if (p.get("plan") or {}).get("exit_day") == str(day)]
    late_ids = [p["id"] for p in opens if (p.get("plan") or {}).get("exit_day", "9999") < str(day)]
    return close_ids, late_ids


# ================================================================ the morning plan (before the open)
def _pkey(day):
    return f"pead:plan:{day}"


def make_plan(day, now, final=False):
    """Signals (events whose signal day is the previous session) and exits due today. Stored once per day (a restart
    reuses it). Waits for today's EDGAR refresh, the EAR store and the previous session's daily bars; at `final` (the
    open) it plans with what it has and records what was missing."""
    have = store.kv_get(_pkey(day))
    if have:
        return have
    want = prev_session(day)
    eg = _edgar()
    uni = universe()
    fresh = sum(1 for t, _ in uni if (eg.get(t) or {}).get("day") == str(day))
    seeded, left = seed_ears(day, budget=0)
    if not final and (fresh < len(uni) or not seeded):
        _state["status"] = f"preparing: EDGAR {fresh}/{len(uni)} refreshed today, EARs {'ready' if seeded else f'{left} tickers to seed'}"
        return None
    f = fetch()
    spy = finished_daily(f.daily("SPY"), day)
    if (spy is None or not len(spy) or spy.index[-1].date() != want) and not final:
        _state["status"] = f"waiting for the {want} daily bars (SPY)"
        return None
    cand = [e for e in events(day) if next_session(e["react"]) == want]
    store_e = _ears()
    rows, stale = {}, []
    for e in sorted(cand, key=lambda e: e["ticker"]):
        t = e["ticker"]
        try:
            dly = finished_daily(f.daily(t), day)
        except Exception as ex:
            dly = None
            _state["last_error"] = f"daily {t}: {type(ex).__name__}"
        x, s = ear(dly, spy, e["react"]) if (dly is not None and spy is not None) else (None, want)
        if x is None and not final and dly is not None and len(dly) and dly.index[-1].date() < want:
            stale.append(t)                               # yesterday's bar not served yet: try again (no bars at all: NO DATA)
            continue
        rows[t] = {"react": str(e["react"]), "accept": e["accept"], "filing": e["acc"], "ear": _r(x, 6),
                   "sigma20": _r(sigma20(dly, day), 6) if dly is not None else None}
        store_e[_ear_key(t, e["react"])] = {"ticker": t, "react": str(e["react"]), "s": str(s), "ear": _r(x, 6),
                                            "why": None if x is not None else "missing close for the EAR window"}
    if stale:
        _state["status"] = f"waiting for {want} daily bars: {', '.join(stale[:8])}" + ("..." if len(stale) > 8 else "")
        return None
    cut, n = cutoff([v for v in store_e.values()], want)
    entries = []
    for t, row in rows.items():
        row["cutoff"], row["n_window"] = _r(cut, 6), n
        if row["ear"] is None:
            row["state"], why = "NO DATA", "missing a close for the EAR window"
        elif cut is None:
            row["state"], why = "NO CUTOFF", f"only {n} EARs in the 365-day window (needs {MIN_N})"
        elif row["ear"] >= cut:
            row["state"], why = "SIGNAL", f"EAR {row['ear']:+.4f} >= cutoff {cut:+.4f} (90th pct of {n})"
            entries.append(t)
        else:
            row["state"], why = "NO SIGNAL", f"EAR {row['ear']:+.4f} < cutoff {cut:+.4f} (90th pct of {n})"
        S.decide(f"{LEDGER}:check:{day}-{t}", LEDGER, t, row["state"], [why], row, "check", VERSION)
    store.kv_set("pead:ears", store_e)
    close_exits, late_exits = [], []
    for lg in LEDGERS:
        ce, le = due_exits(day, lg)
        close_exits += ce
        late_exits += le
        for pid in ce + le:
            p = S.get(pid)
            late = pid in le
            S.decide(f"{lg}:exit:{day}-{pid}", lg, p["ticker"], "EXIT DUE",
                     [f"20th session after {p['date']} is {(p.get('plan') or {}).get('exit_day')}: " +
                      ("LATE: exit at today's open" if late else "exit at today's close")], {"position": pid, "late": late},
                     "exit", VERSION if lg == LEDGER else TP_VERSION)
    plan = {"day": str(day), "asof": str(want), "made_at": now.isoformat(timespec="seconds"), "entries": entries,
            "close_exits": close_exits, "late_exits": late_exits, "rows": rows, "cutoff": _r(cut, 6), "n_window": n,
            "edgar_fresh": f"{fresh}/{len(uni)}", "ears_seeded": seeded, "tz_mode": _state.get("tz_mode"), "version": VERSION}
    store.kv_set(_pkey(day), plan)
    S.decide(f"{LEDGER}:plan:{day}", LEDGER, "*", "PLAN",
             [f"{len(cand)} event(s) with signal day {want}, {len(entries)} signal(s); cutoff {cut} from {n} EARs; "
              f"{len(close_exits)} exit(s) at the close, {len(late_exits)} late exit(s) at the open"],
             {k: plan[k] for k in ("entries", "close_exits", "late_exits", "cutoff", "n_window", "edgar_fresh", "tz_mode")}, "plan", VERSION)
    return plan


# ================================================================ at the open: late exits, then entries
def _equity_q(t, quotes):
    q = dict((quotes or {}).get(t) or {})
    if not q:
        return None
    if q.get("quote_time") is None and q.get("quote_ms"):
        q["quote_time"] = pd.Timestamp(q["quote_ms"], unit="ms", tz="UTC").tz_convert(core.ET)
    return v4exec.equity_quote(t, {t: q})


def _final_entry(day, t, decision, why=None, data=None, ledger=LEDGER):
    return S.decide(f"{ledger}:{day}-{t}", ledger, t, decision, [why] if why else [], data or {}, "entry",
                    VERSION if ledger == LEDGER else TP_VERSION)


def execute_open(day, now, quotes):
    """Late exits (both ledgers), then entries: each ledger takes the plan's signals in its own 5 slots."""
    plan = store.kv_get(_pkey(day))
    hm = now.strftime("%H:%M")
    open_t = C.at(day, OPEN)
    late = hm >= FILL_LATE
    late_by = {}
    for lg in LEDGERS:
        _, late_exits = due_exits(day, lg)
        late_by[lg] = set(late_exits)
        for pid in late_exits:
            p = S.get(pid)
            if p is None or p["status"] != "OPEN" or (p.get("plan") or {}).get("pending_exit"):
                continue
            q = _equity_q(p["ticker"], quotes)
            ok, why = C.quote_after(q, open_t, QUOTE_MAX_AGE_S)
            reason = f"EXIT (LATE): 20 sessions after {p['date']} ended {(p.get('plan') or {}).get('exit_day')}; sold at the open"
            if ok:
                v4exec.close_now(p, reason, {p["ticker"]: q})
            elif late:
                v4exec.close_now(p, reason + f" (no fresh quote by {FILL_LATE}: {why})", {p["ticker"]: q} if q else None)
    if not plan:
        return
    for lg in LEDGERS:
        _enter(lg, day, now, quotes, plan, open_t, late, late_by[lg] | set(plan.get("late_exits") or []))


def _enter(lg, day, now, quotes, plan, open_t, late, late_ids):
    on = switch_on(lg)
    tp = lg == TP_LEDGER
    for t in plan["entries"]:
        if S.decided(f"{lg}:{day}-{t}"):
            continue
        if not on:
            _final_entry(day, t, "SWITCH OFF", f'config/v4.json "{lg}" is off: no new entries (exits still run)', ledger=lg)
            continue
        held = [p for p in S.positions(ledger=lg, status="OPEN") if p["id"] not in late_ids]
        if any(p["ticker"] == t for p in held):
            _final_entry(day, t, "SKIP", f"{t} already held (one position per symbol)", ledger=lg)
            continue
        if len(held) >= SLOTS:
            _final_entry(day, t, "NO SLOT", f"all {SLOTS} slots in use ({', '.join(p['ticker'] for p in held)})",
                         {"held": [p["id"] for p in held]}, ledger=lg)
            continue
        q = _equity_q(t, quotes)
        ok, qwhy = C.quote_after(q, open_t, QUOTE_MAX_AGE_S)
        if not ok:
            if late:
                _final_entry(day, t, "MISSED", f"no fresh quote after the open by {FILL_LATE} ({qwhy})", ledger=lg)
            continue
        why = v4risk.admit(lg, BOOK, t, "long", now)
        if why:
            _final_entry(day, t, "BLOCKED-RISK", why, ledger=lg)
            continue
        row = plan["rows"].get(t) or {}
        sg = row.get("sigma20")
        fill = S.share_buy(q)
        qty, notional = size(fill, sg)
        if qty <= 0:
            _final_entry(day, t, "SKIP", f"size 0 (fill {fill}, sigma20 {sg})", ledger=lg)
            continue
        exit_day = add_sessions(day, HOLD)
        tpx = tp_target(fill, sg) if tp else None
        rule = f"sell 5 minutes before the close on {exit_day} (20th session after entry); no stop; held overnight"
        if tp:
            rule = f"take profit when the bid in the last 5 minutes is >= {tpx} (fill x (1 + sigma20 x sqrt(20))); else " + rule
        rec = {"id": f"{lg}:{day}-{t}", "ledger": lg, "book": BOOK, "kind": "shares", "date": str(day), "ticker": t,
               "direction": "long", "side": "long", "qty": qty, "entry_px": fill, "entry_t": store.ts(),
               "signal_t": open_t.isoformat(), "quote_t": str(q.get("quote_time")), "fees": 0.0,
               "risk_usd": round(notional * 3 * sg, 2), "max_loss": None,
               "legs": [{"symbol": t, "label": f"{qty:g} sh", "action": "buy", "qty": qty}],
               "plan": {"label": TP_LABEL if tp else LABEL, "status": "forward paper test (not promoted)", "signal": row,
                        "asof": plan["asof"], "bid": q["bid"], "ask": q["ask"], "notional": notional, "slot_usd": SLOT_USD,
                        "exit_day": str(exit_day), "tp_px": tpx, "exit_rule": rule,
                        "risk_rule": "notional = min($600, $45 / (3 x 20-day sigma)); risk_usd = 3 x sigma x notional",
                        "day_base": 0.0, "day_base_day": str(day), "late": late},
               "version": TP_VERSION if tp else VERSION, "exec_model": "shares1"}
        got, owhy = S.open_position(rec, f"{lg} entry at the open (paper, simulated fill)")
        if not got:
            _final_entry(day, t, "SKIP", owhy, ledger=lg)
            continue
        _final_entry(day, t, "ORDER", None, {"position": got, "fill": fill, "qty": qty, "notional": notional,
                                             "exit_day": str(exit_day), "tp_px": tpx, "quote_t": str(q.get("quote_time"))}, ledger=lg)


# ================================================================ at the close: the 20-session exits
def close_times(day, now=None):
    """(exit window start, give-up time) for `day`: 5 minutes and 30 seconds before the close (13:00 on early closes)."""
    sess = core.session_info(now or C.at(day, "12:00"))
    close_t = C.at(day, sess.get("close", "16:00"))
    return close_t - timedelta(seconds=EXIT_BEFORE_CLOSE_S), close_t - timedelta(seconds=EXIT_GIVE_UP_S)


def execute_close(day, now, quotes):
    """The last 5 minutes: day-20 exits for both ledgers; the take-profit check for pead_t21_tp (once a day per
    position, on its first fresh quote in the window)."""
    start, give_up = close_times(day, now)
    if now < start:
        return
    for lg in LEDGERS:
        for pid in due_exits(day, lg)[0]:
            p = S.get(pid)
            if p is None or p["status"] != "OPEN" or (p.get("plan") or {}).get("pending_exit"):
                continue
            q = _equity_q(p["ticker"], quotes)
            ok, why = C.quote_after(q, start, QUOTE_MAX_AGE_S)
            tpx = (p.get("plan") or {}).get("tp_px")
            reason = f"EXIT at the close: 20th session after {p['date']}" + \
                     (" (take-profit reached too)" if tpx and ok and q["bid"] >= tpx else "")
            if ok:
                v4exec.close_now(p, reason, {p["ticker"]: q})
            elif now >= give_up:
                S.update_plan(pid, pending_exit={"reason": reason + f" (no fresh quote before the close: {why}); filled at the next "
                                                          "open's first valid quote (LATE)", "since": store.ts(), "why": why,
                                                 "next_open": True, "day": str(day)})
                store.event("v4", f"{lg.upper()} EXIT PENDING {p['ticker']}: no fresh quote before the close ({why})", lg, pid)
    for p in S.positions(ledger=TP_LEDGER, status="OPEN"):
        pl = p.get("plan") or {}
        did = f"{TP_LEDGER}:tp:{day}-{p['id']}"
        if pl.get("pending_exit") or not pl.get("tp_px") or S.decided(did) or pl.get("exit_day") == str(day):
            continue
        q = _equity_q(p["ticker"], quotes)
        ok, why = C.quote_after(q, start, QUOTE_MAX_AGE_S)
        if not ok:
            if now >= give_up:
                S.decide(did, TP_LEDGER, p["ticker"], "TP NOT CHECKED", [f"no fresh quote before the close: {why}"],
                         {"position": p["id"], "tp_px": pl["tp_px"]}, "exit", TP_VERSION)
            continue
        hit = q["bid"] >= pl["tp_px"]
        S.decide(did, TP_LEDGER, p["ticker"], "TAKE PROFIT" if hit else "HOLD",
                 [f"bid {q['bid']} {'>=' if hit else '<'} target {pl['tp_px']}"], {"position": p["id"], "tp_px": pl["tp_px"],
                                                                                      "bid": q["bid"]}, "exit", TP_VERSION)
        if hit:
            v4exec.close_now(p, f"TAKE PROFIT: bid {q['bid']} >= target {pl['tp_px']} (fill x (1 + sigma20 x sqrt(20)))",
                             {p["ticker"]: q})


# ================================================================ during the session: marks and pending exits
def manage(now, quotes=None):
    """Open positions of this ledger only: retry a pending exit (after the open), mark to the bid. Never closes a
    position for being from an earlier session (no v4exec.overnight here: holding overnight is the rule)."""
    day = str(now.date())
    for p in S.positions(ledgers=LEDGERS, status="OPEN"):
        q = _equity_q(p["ticker"], quotes) if quotes else None
        pl = p.get("plan") or {}
        pend = pl.get("pending_exit")
        if pend:                                          # a close exit that missed waits for the next open
            wait = pend.get("next_open") and str(pend.get("day") or "") >= day
            if q and not wait and C.quote_after(q, C.at(now.date(), OPEN), QUOTE_MAX_AGE_S)[0]:
                v4exec.retry_pending(p, {p["ticker"]: q})
            continue
        if not (q and q.get("executable") and q.get("bid") is not None):
            continue
        if pl.get("day_base_day") != day:                 # the day's P/L starts from the previous session's last mark
            S.update_plan(p["id"], day_base=float(pl.get("mtm") or 0.0) if str(p["date"]) != day else 0.0, day_base_day=day)
        mtm = round(S.pnl(p, q["bid"]), 2)
        S.update_plan(p["id"], mtm=mtm, last_mark=q["bid"], mark_t=str(q.get("quote_time")))
        S.mark(p["id"], mtm, mtm)


# ================================================================ worker
def _prep(day, hm):
    """Off-hours data work: today's EDGAR refresh, then EAR seeding for the cutoff window."""
    eg = _edgar()
    uni = universe()
    if any((eg.get(t) or {}).get("day") != str(day) for t, _ in uni):
        refresh_edgar(day)
        return
    seed_ears(day)


def step(now=None):
    now = now or core.now_et()
    t0 = time.time()
    day = now.date()
    sess = core.session_info(now)
    if sess.get("holiday"):
        _state["status"] = "market closed"
        return
    f = fetch()
    if not f.ready():
        _state["status"] = "waiting for Schwab (no decisions on delayed data)"
        return
    import schwab
    hm = now.strftime("%H:%M")
    close = sess.get("close", "16:00")
    plan = store.kv_get(_pkey(day))
    if WORK_FROM <= hm < OPEN and not plan:
        try:
            with schwab.priority("normal"):
                _prep(day, hm)
        except Exception as e:
            _state["last_error"] = f"prep: {type(e).__name__}: {e}"[:200]
    last_try = _state.get("plan_try")
    if not plan and PLAN_FROM <= hm < close and (hm >= OPEN or last_try is None or last_try > now
                                                 or (now - last_try).total_seconds() >= 60):
        _state["plan_try"] = now
        with schwab.priority("normal"):
            plan = make_plan(day, now, final=hm >= OPEN)
    opens = S.positions(ledgers=LEDGERS, status="OPEN")
    if not (OPEN <= hm < close):
        _state["status"] = f"{len(opens)} open, plan {'ready' if plan else 'not made'} ({sess['state']})"
        return
    due = [due_exits(day, lg) for lg in LEDGERS]
    close_ids = [i for c, _ in due for i in c]
    late_ids = [i for _, l in due for i in l]
    at_open = hm < FILL_LATE or bool(late_ids) or any((p.get("plan") or {}).get("pending_exit") for p in opens) or \
        (plan and not all(S.decided(f"{lg}:{day}-{t}") for lg in LEDGERS for t in plan["entries"]))
    start, _ = close_times(day, now)
    at_close = now >= start and (bool(close_ids) or any(p["ledger"] == TP_LEDGER for p in opens))
    due_mark = _state["mark_t"] is None or (now - _state["mark_t"]).total_seconds() >= MARK_EVERY_S or _state["mark_t"] > now
    syms = sorted({p["ticker"] for p in opens} | (set(plan["entries"]) if plan and at_open else set()))
    quotes = {}
    if syms and (at_open or at_close or due_mark):
        _state["mark_t"] = now
        with schwab.priority("risk" if opens else "normal"):
            try:
                quotes, _ = f.quotes(syms)
            except Exception as e:
                _state["last_error"] = f"quotes: {type(e).__name__}"
    with schwab.priority("risk"):
        try:
            manage(now, quotes)
        except Exception as e:
            _state["last_error"] = f"manage: {type(e).__name__}: {e}"[:200]
    try:
        execute_open(day, now, quotes)
        execute_close(day, now, quotes)
    except Exception as e:
        _state["last_error"] = f"execute: {type(e).__name__}: {e}"[:200]
    _state["status"] = f"{len(S.positions(ledgers=LEDGERS, status='OPEN'))} open" + \
        (", at the open" if at_open else "") + (", exits at the close" if at_close else "")
    _state["step_s"] = round(time.time() - t0, 2)


def _run():
    while not _state["stop"]:
        try:
            step()
            try:
                import health
                health.beat("v4pead", True, _state.get("status"), _state.get("step_s"))
            except Exception:
                pass
        except Exception as e:
            _state["last_error"] = f"{type(e).__name__}: {e}"[:200]
        time.sleep(5)


def start():
    if _state["thread"]:
        return False
    th = threading.Thread(target=_run, daemon=True, name="v4pead")
    _state["thread"] = th
    th.start()
    return True


def report_meta(trades=None, ledger=LEDGER):
    """For the Research page: evidence labels, the backtest numbers, and the forward mean % per trade (same unit)."""
    tp = ledger == TP_LEDGER
    rules = ("8-K Item 2.02 -> EAR (3-day return minus SPY) >= trailing-365-day 90th pct -> buy next open; sell at the "
             "close 20 sessions later")
    out = {"label": TP_LABEL if tp else LABEL, "status": "forward paper test (not promoted); promotion needs 40 forward trades (G5)",
           "backtest": TP_BACKTEST if tp else BACKTEST,
           "rules": rules + ("; take profit near the close once the bid >= fill x (1 + sigma20 x sqrt(20))" if tp else ""),
           "slots": SLOTS, "slot_usd": SLOT_USD, "risk_cap_usd": RISK_CAP_USD, "universe": "S&P 500 (config/sp500.json)"}
    pct = [100.0 * float(t["realized"] or 0) / float((t.get("plan") or {}).get("notional") or 0)
           for t in trades or [] if (t.get("plan") or {}).get("notional")]
    if pct:
        out["forward_mean_pct"] = round(float(np.mean(pct)), 3)
        out["forward_trades"] = len(pct)
    return out


def status():
    day = core.now_et().date()
    eg = _edgar()
    uni = universe()
    ears = _ears()
    return {"version": VERSION, "tp_version": TP_VERSION, "status": _state["status"], "last_error": _state["last_error"],
            "step_s": _state["step_s"], "switch": {lg: switch_on(lg) for lg in LEDGERS}, "plan": store.kv_get(_pkey(day)),
            "open": {lg: [p["id"] for p in S.positions(ledger=lg, status="OPEN")] for lg in LEDGERS},
            "label": {LEDGER: LABEL, TP_LEDGER: TP_LABEL},
            "data": {"universe": len(uni), "edgar_fresh_today": sum(1 for t, _ in uni if (eg.get(t) or {}).get("day") == str(day)),
                     "events_stored": sum(len(v.get("f", [])) for v in eg.values()), "ears_stored": len(ears),
                     "ears_usable": sum(1 for v in ears.values() if v.get("ear") is not None),
                     "edgar_time_zone": _state.get("tz_mode")}}
