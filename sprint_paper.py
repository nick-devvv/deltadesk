"""sprint_paper.py - v4 PAPER forward tests of sprint backtests (docs/STRATEGY_PLAN.md section 7).
Nick said yes (2026-10-31) to paper-only twins of the three near-miss runs, and (2026-11-01) to rule H (FIN-H) as a
fourth. Nothing here can place a real order: every fill is simulated at a live Schwab quote and recorded in the v4 paper
tables (v4store), like every other v4 ledger.

Ledgers (book "sprint"; SPY and QQQ, the symbols the engine ticks for the index book; 1 contract per trade):
  fb_or       = setups_v2-012  failed_break_or calls (OR15L / OR30L), BS-EST |delta| 0.40-0.55 nearest 0.45, premium
                               ceiling stop fixed at the entry window's value (09:45-11:30 20%, 11:30-14:00 12%,
                               14:00-15:30 10%; time rule b), no target, all out 15:25
  otm_put     = otm_v1-011     puts at the bar finishing 10:30, |delta| 0.06-0.15 nearest 0.10, filters vixy_pctl_le40 +
                               vixy_not_rising + day_up + wed_fri + skip_opex, fixed -95% stop (target +9900%), all out 15:25
  otm_bounce  = otm_v1-042     calls at the bar finishing 11:00, |delta| 0.03-0.12 nearest 0.07, filters vixy_pctl_ge60 +
                               day_down + skip_opex, same exit. WATCH-ONLY: its backtest is 44 trades from one episode.
  otm_h       = otm_v1-040     rule H (SPRINT_PLAN Amendments 6-7, FIN-H): calls at the bar finishing 11:00, |delta|
               + f_rvol >= 1.06 0.03-0.12 nearest 0.07, no engine filter, TAKEN ONLY when the entry feature f_rvol
                               (sprint.features / sprint.daytype: regular-hours volume so far / the mean of the same minutes
                               over up to 14 prior sessions, at least 10, rounded to 2 decimals) is >= 1.06 at the signal
                               bar; fixed -95% stop (target +9900%), all out 15:25. Unknown f_rvol -> no trade.
The fb_or / otm_put / otm_bounce backtests are IN-SAMPLE (DEV, Aug 2024-Jun 2026). Rule H was frozen on 2016-2019 and
passed both holdouts (2020-2023 MODELED; DEV REAL, out-of-sample for the rule); its locked-period exam has not run.
These ledgers are forward tests, NOT promoted: promotion still needs CLAUDE.md step 5 (out-of-sample pass + 40 forward
paper trades).

How live and backtest are kept identical (the rules are READ from the pinned spec, the signals COMPUTED by sprint code):
  * rules: sprint/specs/<spec>.json, sha256 pinned below, expanded with sprint.engine.expand; the run id must match.
    A changed spec or an exit this module does not implement -> the ledger refuses new entries (recorded).
  * signals: the engine's finished 1-minute bars (snap["m1"], ET, premarket included, several sessions) become a
    sprint.data.Series / DayContext, and sprint.entries.signals() runs on it. Only bars whose minute has ended count.
  * filters: sprint.engine._filters_ok on that context, with VIXY added the way the engine adds it (aux "VIXY" =
    VIXY's 1-minute Series, aux "VIXY_D" = its daily closes). Then FEATURE_RULES (otm_h only): the entry features
    sprint.features.entry_features stamps at the signal bar, compared with the frozen cut.
  * contract: sprint.contracts.pick on the live chain, each contract's price = the chain MID (the backtest used the last
    trade at or before the signal bar, at most 5 minutes old; a chain row whose quote is older than that is skipped).
    BS-EST delta from sprint.bs with the underlying's close at the signal bar and the minutes to 16:00 from its end.
  * entry: one decision per signal, in bar order. The fill needs an executable quote dated at least the decision
    latency after the signal bar finished (v4common.quote_after) inside the backtest's entry window
    (sprint.fills.ENTRY_WAIT = 3 minutes after the signal bar); after that the signal is MISSED (logged). Buy at the
    ask, $0.65 per contract per side (exec model bidask065). One position per symbol per ledger: a signal while busy
    is skipped and logged ("busy", as in sprint.engine.run_pass).
  * exits (every engine tick, on live quotes), costs as sprint/sim.py computes them:
      ceiling: cost C = ask + $0.65/100; stop when the proceeds of selling at the bid net of $0.65/100 fall to
               C x (1 - ceiling): the trigger bid = sim.Costs(...).trigger(C x (1 - ceiling)) with the live bid as the
               sell price (half-spread 0 because the bid already is the sell price).
      fixed:   debit = the entry fill (ask, fees excluded, as sim.py's debit); stop when the MID (sim.py triggers on the
               traded price, the mid proxy) <= debit x (1 - 0.95); target when the mid >= debit x (1 + 99).
      all out at the session's all-out time (15:25; 12:50 on 1 PM early-close days), as sim.py.
    Sells at the bid, $0.65/contract; with no valid quote the exit is PENDING and retried (v4exec).
  * restart safety: decision ids <ledger>:<ticker>:<day>:<bar idx>:<level or setup> and position ids are deterministic;
    a decided signal is never re-entered, a stored contract choice is reused, an opened position is never opened twice.
Deviations from the backtest (also listed in status() and docs/STRATEGY_PLAN.md section 7):
  * SPY + QQQ only (the backtests pooled SPY + QQQ + IWM; the engine has no IWM snapshot: config/policy.json is frozen).
  * Live bars come from Schwab (the backtests used Alpaca 1-minute bars); chain mids and live bid/ask replace last
    trades and the modeled 2% half-spread.
  * VIXY: Schwab 1-minute bars for "not rising" / the prior close and Schwab daily closes for the percentile; the last
    252 closes are used as they are (the backtest's daily file skipped the never-pulled locked months).
  * Indicators that need long history (daily ATR over 60 sessions) see only the ~30 days the engine keeps; they feed the
    stamped features only, never these entries or exits (ATR(14, 5m), which the probe rule uses, converges in a session).
  * The v4 risk layer (kill switch, sprint-book caps, sprint-book daily paper loss limit) can block an entry the
    backtest would take; every block is recorded.
  * On 1 PM early-close days the desk's 12:30 last entry is stricter than the backtest's 12:50.
  * otm_h's f_rvol uses Schwab volume for today and for the prior sessions (the backtest used Alpaca volume for both);
    it needs at least 10 prior sessions of bars in the engine's snapshot, otherwise the signal is FILTERED (recorded).
"""
import copy
import functools
import hashlib
import json
import time
from datetime import date, timedelta

import pandas as pd

import core
import marketdata
import store
import v4common as C
import v4exec
import v4risk
import v4store as S
from sprint import VERSION as SPRINT_VERSION
from sprint import contracts as SC
from sprint import data as SD
from sprint import engine as SE
from sprint import entries as SN
from sprint import features as SF
from sprint import fills as SFI
from sprint import sim as SM
from sprint import spread as SSP

VERSION = "2026-11-02.v4-sprint_paper2"   # paper2: + otm_h (rule H); fb_or / otm_put / otm_bounce unchanged
BOOK = "sprint"
SYMBOLS = ("SPY", "QQQ")
EXEC_MODEL = "bidask065"
LABEL = "PAPER (simulated fills)"
STATUS = "forward test of an in-sample backtest (not promoted)"
SPEC_DIR = core.HERE / "sprint" / "specs"
WINDOW_S = SFI.ENTRY_WAIT * 60            # the backtest fills at the next option print within 3 minutes of the signal bar
FINAL_S = 15                              # the last ~15 s of that window: record MISSED rather than wait past it
VIXY_GRACE_S = 20                         # wait this long after the signal bar for VIXY's bar of the same minute
VIXY_RETRY_S = 120                        # Schwab VIXY daily closes: retry a failed fetch after 2 minutes
VIXY_WARM = ("09:46", "11:01")            # load VIXY (1-minute history, daily closes) before the 10:30 / 11:00 decisions
FIRST_TICK, LAST_TICK = "09:46", "15:30"  # the first signal bar (09:45) finishes 09:46; the last fill is by 15:18
DAY_DONE = "15:16"                        # after the last failed-break signal bar (finishing 15:15)
QTY = 1

# ledger -> (spec id, run id, sha256 of the spec file that produced the backtest, display label)
PINS = {
    "fb_or": ("setups_v2", "setups_v2-012", "2b3d90478447efffffb748223d893f71529c2565713379225e2d32f0e77a6f26",
              "Failed-break calls, opening-range lows"),
    "otm_put": ("otm_v1", "otm_v1-011", "ece0232e5457df44fbb15ada8d92e6aa3c2919e2cf61406d1fe1600ad3a31f7e",
                "Far-OTM 10:30 puts, calm up days"),
    "otm_bounce": ("otm_v1", "otm_v1-042", "ece0232e5457df44fbb15ada8d92e6aa3c2919e2cf61406d1fe1600ad3a31f7e",
                   "Far-OTM 11:00 calls, stressed down days (WATCH-ONLY)"),
    "otm_h": ("otm_v1", "otm_v1-040", "ece0232e5457df44fbb15ada8d92e6aa3c2919e2cf61406d1fe1600ad3a31f7e",
              "Far-OTM 11:00 calls, busy days (rule H)"),
}
LEDGERS = tuple(PINS)
# ledger -> ((feature, op, cut), ...): entry features (sprint.features) that must hold at the signal bar, all of them.
# otm_h = rule H, frozen in SPRINT_PLAN Amendment 6 (found on 2016-2019) and Amendment 7 (FIN-H): f_rvol >= 1.06.
FEATURE_RULES = {"otm_h": (("f_rvol", ">=", 1.06),)}
STATUS_BY = {"otm_h": "forward test of an out-of-sample-tested backtest (not promoted; locked-period exam not run)"}
WATCH_ONLY = {"otm_bounce": "44 backtest trades from one high-volatility episode (April 2025 dominates): watch only"}
BACKTEST = {   # docs/research/sprint_runs.csv, SPRINT_RESULTS_2.md / _3.md. BACKTEST, in-sample (DEV), MODELED 2% half-spread
    "fb_or": {"trades": 429, "win_rate": 10.5, "expectancy": 18.57, "profit_factor": 1.785, "pf_2x": 1.268, "max_dd": -1452.16,
              "symbols": "SPY+QQQ+IWM", "failed": "Aug-Dec 2024 stretch lost (-$609.27, PF 0.71); deflated Sharpe 0.000 (2,827 trials)"},
    "otm_put": {"trades": 375, "win_rate": 13.1, "expectancy": 10.20, "profit_factor": 1.655, "pf_2x": 1.52, "max_dd": -1690.48,
                "symbols": "SPY+QQQ+IWM", "failed": "Jan-Jun 2026 stretch lost (-$1,514.19, PF 0.29); negative without the best 5 "
                                                     "trades; 2 of 11 two-month blocks up; deflated Sharpe 0.000 (3,187 trials)"},
    "otm_bounce": {"trades": 44, "win_rate": 6.8, "expectancy": 130.48, "profit_factor": 10.341, "pf_2x": 9.443, "max_dd": -533.92,
                   "symbols": "SPY+QQQ+IWM", "failed": "under 60 trades, all in 2 two-month blocks (one high-volatility episode); "
                                                        "deflated Sharpe 0.000 (3,187 trials)"},
    # SPRINT_RESULTS_5.md holdout 2 / SPRINT_RESULTS_7.md (factory_dev_v1-012, rule kept): DEV REAL option prices
    "otm_h": {"trades": 485, "win_rate": 11.8, "expectancy": 13.22, "profit_factor": 2.352, "pf_2x": 2.102, "max_dd": -1278.32,
              "symbols": "SPY+QQQ+IWM", "label": "BACKTEST out-of-sample (rule frozen on 2016-2019; DEV REAL option prices), "
                                                 "2% half-spread",
              "failed": "negative without the best 5 trades (-$1,082.68); +$57.82 without 2025-04-09 (run 7 follow-up); "
                        "most months lose (8/23 green); deflated Sharpe 0.0 (3,742 trials); locked-period exam not run"},
}
DEVIATIONS = [
    "SPY + QQQ only: the backtests pooled SPY + QQQ + IWM, the engine ticks SPY and QQQ (config/policy.json is frozen)",
    "Schwab bars and live chain mids / bid-ask replace Alpaca bars, last trades and the modeled 2% half-spread",
    "VIXY from Schwab (1-minute bars; daily closes for the percentile, all of the last 252 used)",
    "Long-history features (daily ATR over 60 sessions) see ~30 days; they are stamped only, never used by these rules",
    "the v4 risk layer (kill switch, sprint-book caps, daily paper loss limit) can block an entry; blocks are recorded",
    "1 PM early-close days: the desk's 12:30 last entry is stricter than the backtest's 12:50",
    "otm_h: f_rvol from Schwab volume (today and prior sessions); fewer than 10 prior sessions in the snapshot -> FILTERED",
]


def status_of(name):
    return STATUS_BY.get(name, STATUS)
vixy_source = None        # tests: lambda now -> {"m1": DataFrame | None, "daily": pd.Series | None, "notes": [...]}
_state = {"last_error": None, "errors": 0}
_cache = {}               # ticker -> (key, ctx)


class RuleError(RuntimeError):
    pass


def _err(where, e):
    _state["errors"] += 1
    _state["last_error"] = f"{where}: {type(e).__name__}: {e}"[:200]


# ---------------------------------------------------------------- rules: read from the pinned sprint spec
def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@functools.lru_cache(maxsize=None)
def rules(name):
    """The ledger's rules from its backtest run (sprint.engine.expand on the pinned spec). Raises RuleError."""
    spec_id, run_id, sha, _label = PINS[name]
    path = SPEC_DIR / f"{spec_id}.json"
    got = _sha(path)
    if got != sha:
        raise RuleError(f"{path.name} changed since the backtest (sha256 {got[:12]}, pinned {sha[:12]}): rules no longer pinned")
    run = next((r for r in SE.expand(json.loads(path.read_text())) if r["run_id"] == run_id), None)
    if run is None:
        raise RuleError(f"run {run_id} not found in {path.name}")
    x = run["exit"]
    plain = x.tp == "none" and x.trail == "none" and not x.rr_min and x.risk == "none" and x.mechanics == "desk" \
        and x.allout == "15:25" and tuple(x.table) == tuple(SM.TABLE) and not run.get("random") and run.get("fake_seed") is None
    if not plain or not ((x.stop == "premium" and x.time == "b") or x.stop == "fixed"):
        raise RuleError(f"{run_id}: exit {x.as_dict()} is not one this live twin implements")
    if run["entry"] not in SN.SETUPS or x.contract not in SC.RULES or SC.is_next(x.contract):
        raise RuleError(f"{run_id}: entry {run['entry']} / contract {x.contract} not supported live")
    return {"name": name, "run_id": run_id, "spec": f"sprint/specs/{spec_id}.json", "spec_sha256": sha, "entry": run["entry"],
            "side": run["side"], "filters": tuple(run.get("filters") or ()), "contract": x.contract, "exit": x.as_dict(),
            "backtest_symbols": list(run["symbols"])}


def enabled(name):
    """config/v4.json "sprint_paper": {ledger: bool}. Default on (paper only). Off stops new entries, never exits."""
    import retire
    sw = retire.cfg().get("sprint_paper")
    if retire.is_retired(name):
        return False
    return True if not isinstance(sw, dict) else bool(sw.get(name, True))


def refusal(name):
    """Why the ledger takes no new entries today (None = it may)."""
    try:
        rules(name)
    except Exception as e:
        return f"rules unavailable: {e}"
    if not enabled(name):
        return "switched off in config/v4.json (sprint_paper)"
    return None


# ---------------------------------------------------------------- the sprint context from the engine's bars
def _frame(m1):
    """Engine bars (ET index, Open..Volume) -> the sprint cache layout (ts, o, h, l, c, v)."""
    m = m1[~m1.index.duplicated(keep="last")].sort_index()
    idx = pd.DatetimeIndex(m.index)
    idx = idx.tz_convert(core.ET) if idx.tz is not None else idx.tz_localize(core.ET)
    return pd.DataFrame({"ts": idx, "o": m["Open"].to_numpy(float), "h": m["High"].to_numpy(float), "l": m["Low"].to_numpy(float),
                         "c": m["Close"].to_numpy(float), "v": m["Volume"].to_numpy(float)})


def context(ticker, m1, now):
    """(DayContext of today from FINISHED bars only, None) or (None, why). Cached until a new or changed bar arrives."""
    fin = C.finished(m1, now)
    if fin is None or not len(fin):
        return None, "no finished bars"
    day = now.date()
    rth = C.rth_day(fin, day)
    if rth is None or not len(rth):
        return None, "no finished regular-hours bar today"
    key = (day, fin.index[-1], len(fin), float(rth["Close"].sum()), float(rth["Volume"].sum()))
    hit = _cache.get(ticker)
    if hit and hit[0] == key:
        return hit[1], None
    series = SD.Series(ticker, _frame(fin))
    if day not in series.rth:
        return None, "no regular-hours bar today"
    ctx = SD.DayContext(series, day, {}, SSP.SpreadModel())
    ctx._sp_sigs = {}
    _cache[ticker] = (key, ctx)
    return ctx, None


def signals(ctx, r):
    k = (r["entry"], r["side"])
    if k not in ctx._sp_sigs:
        ctx._sp_sigs[k] = SN.signals(ctx, r["entry"], r["side"])
    return ctx._sp_sigs[k]


def bar_end(day, idx):
    """When regular-hours bar idx finishes (09:30 + idx + 1 minutes, ET)."""
    return C.at(day, "09:30") + timedelta(minutes=idx + 1)


# ---------------------------------------------------------------- VIXY (the backtests' VIX proxy)
def _vixy_default(now):
    """Schwab VIXY: 1-minute bars through marketdata (finished only) and daily closes before today (cached per day in
    store.kv, retried at most every 2 minutes). Nothing is fetched with an injected provider (tests, replays)."""
    out = {"m1": None, "daily": None, "notes": [], "src": "Schwab"}
    if marketdata._provider is not None:
        out["notes"].append("injected market-data provider: VIXY not loaded")
        return out
    try:
        df, _forming, meta = marketdata.bars("VIXY")
        out["m1"] = df
        if df is None:
            out["notes"].append(f"no VIXY 1-minute bars ({meta.get('error')})")
    except Exception as e:
        out["notes"].append(f"VIXY bars failed ({type(e).__name__})")
    key = f"sprint_paper:vixy_daily:{now.date()}"
    hist = store.kv_get(key)
    if hist is None and time.time() - _state.get("vixy_try", 0) > VIXY_RETRY_S:
        _state["vixy_try"] = time.time()
        try:
            import schwab
            d = schwab.bars_daily("VIXY")
            if d is not None and len(d):
                hist = [[pd.Timestamp(i).date().isoformat(), float(x)] for i, x in zip(d.index, d["Close"])
                        if pd.Timestamp(i).date() < now.date()]
                if hist:
                    store.kv_set(key, hist)
        except Exception as e:
            out["notes"].append(f"VIXY daily failed ({type(e).__name__})")
    if hist:
        out["daily"] = pd.Series([float(x[1]) for x in hist], index=[date.fromisoformat(x[0]) for x in hist])
    else:
        out["notes"].append("no VIXY daily closes")
    return out


def _warm_vixy(now):
    """At most once a minute until the daily closes are cached: so the 10:30 / 11:00 decisions find VIXY ready."""
    if vixy_source is not None or marketdata._provider is not None:
        return
    minute = now.strftime("%Y-%m-%d %H:%M")
    if _state.get("warm_minute") == minute or store.kv_get(f"sprint_paper:vixy_daily:{now.date()}"):
        return
    _state["warm_minute"] = minute
    try:
        _vixy_default(now)
    except Exception as e:
        _err("VIXY warm-up", e)


def vixy(now):
    v = dict((vixy_source or _vixy_default)(now))
    v.setdefault("notes", [])
    d = v.get("daily")
    if d is not None and len(d) > 1:
        d = d[~d.index.duplicated(keep="last")].sort_index()
        r = (d / d.shift()).iloc[-253:].dropna()
        if len(r) and (r.max() > 2.0 or r.min() < 0.5):              # a reverse split the source did not adjust
            v["notes"].append("VIXY daily closes jump more than 2x in a day (unadjusted split?): percentile unknown")
            d = None
        v["daily"] = d
    m = v.get("m1")
    v["m1"] = C.finished(m, now) if m is not None and len(m) else None
    return v


def _filter_inputs(ctx, sig):
    """The numbers the filters read, for the record (the decision itself is sprint.engine._filters_ok)."""
    i = sig.idx
    prev = ctx.series.prev_day(ctx.day)
    cl = float(ctx.c[i])
    out = {"weekday": ctx.day.weekday(), "third_friday": ctx.day.weekday() == 4 and 15 <= ctx.day.day <= 21,
           "close_at_signal": cl, "prior_day": str(prev["day"]) if prev else None, "prior_close": prev["close"] if prev else None,
           "day_up": (cl >= prev["close"]) if prev else None}
    vd = ctx.aux.get("VIXY_D")
    out["vixy_pctl"] = SD.percentile_rank(vd, prev["day"]) if (prev and vd is not None) else None
    out["vixy_daily_n"] = None if vd is None else int(len(vd))
    out["vixy_daily_last"] = None if vd is None or not len(vd) else [str(vd.index[-1]), float(vd.iloc[-1])]
    vx = ctx.aux.get("VIXY")
    if vx is not None and ctx.day in vx.rth:
        g = vx.rth[ctx.day][:i + 1, 3]
        ok = [k for k in range(len(g)) if g[k] == g[k]]
        pc = vx.prev_day(ctx.day)
        if ok:
            out["vixy_last"] = float(g[ok[-1]])
            out["vixy_last_bar"] = (C.at(ctx.day, "09:30") + timedelta(minutes=ok[-1])).strftime("%H:%M")
        if pc:
            out["vixy_prior_close"] = pc["close"]
            if ok:
                out["vixy_vs_prior"] = round(float(g[ok[-1]]) / pc["close"], 6)
    return out


# ---------------------------------------------------------------- contract choice on the live chain
class _ChainTape:
    """A live chain row in the place of sprint.fills.OptionTape inside sprint.contracts.pick: its price at the signal
    bar is the chain mid (None when the row has no two-sided quote or its quote is over 5 minutes older than the bar)."""

    def __init__(self, row, meta, mid):
        self.symbol, self.right, self.strike, self.expiry = row["symbol"], meta["right"], meta["strike"], meta["expiry"]
        self.row, self.mid = row, mid

    def last_close(self, i, max_age=5):
        return self.mid


def _row_mid(row, signal_end):
    bid, ask = row.get("bid"), row.get("ask")
    if bid is None or ask is None or ask <= 0 or bid < 0 or bid > ask:
        return None
    ts = row.get("ts")
    if ts:
        t = pd.Timestamp(ts)
        t = t.tz_localize(core.ET) if t.tzinfo is None else t
        if (pd.Timestamp(signal_end) - t).total_seconds() > SC.MAX_AGE * 60:
            return None
    return round((float(bid) + float(ask)) / 2, 4)


def pick(ctx, sig, rule, rows, signal_end):
    """(contract dict, None) or (None, why): sprint.contracts.pick with the chain mids as the contracts' prices."""
    tapes = {}
    for row in rows or []:
        meta = SD.parse_occ(row.get("symbol"))
        if not meta or meta["expiry"] != ctx.day or meta["right"] != sig.side:
            continue
        tapes[row["symbol"]] = _ChainTape(row, meta, _row_mid(row, signal_end))
    c2 = copy.copy(ctx)
    c2.tapes, c2.tapes_next = tapes, {}
    tape, info = SC.pick(c2, sig.side, sig.idx, rule)
    if tape is None:
        return None, f"{info} ({len(tapes)} {'calls' if sig.side == 'C' else 'puts'} on the chain)"
    r = tape.row
    k = dict(info, bid=r.get("bid"), ask=r.get("ask"), mid=tape.mid, spread=round(float(r["ask"]) - float(r["bid"]), 4),
             delta_bs_est=info["delta"], iv_bs_est=round(info["iv"], 4), chain_delta=r.get("delta"), chain_iv=r.get("iv"),
             chain_ts=str(r.get("ts")) if r.get("ts") else None, price_used="chain mid", candidates=len(tapes),
             underlying_at_signal=float(ctx.c[sig.idx]))
    return k, None


# ---------------------------------------------------------------- exits (sim.py's costs and triggers on live quotes)
class _AtQuote:
    """Half-spread 0: the live bid already is the sell price and the ask the buy price."""

    def half_spread(self, under, px, minute=None):
        return 0.0, "LIVE-QUOTE"


def exit_plan(r, sig, fill, sym):
    """(exit dict, rule text, planned risk $) for a fill at `fill` (the ask)."""
    x = r["exit"]
    dec = sig.idx + 1
    costs = SM.Costs(_AtQuote(), sym, dec)
    cost = costs.cost(fill)                                           # ask + $0.65 / 100
    if x["stop"] == "premium":
        w = SM.window(SM.TABLE, dec)
        ceil = w[2]
        trig = costs.trigger(cost * (1 - ceil))                       # bid whose proceeds net of $0.65 = cost x (1 - ceiling)
        lab = f"{_hm(w[0])}-{_hm(w[1])}"
        txt = (f"premium ceiling {ceil:.0%} (entry window {lab}, time rule b, fixed for the trade): exit when the bid net of "
               f"$0.65 falls to cost x {1 - ceil:.2f} (bid <= {trig:.4f}); no target; all out {x['allout']}")
        return {"kind": "ceiling", "ceiling": ceil, "window": lab, "cost": round(cost, 6), "stop_proceeds": round(cost * (1 - ceil), 6),
                "stop_bid": trig, "allout": x["allout"]}, txt, round(cost * ceil * SFI.MULT * QTY, 2)
    debit = fill                                                      # sim.py: entry fill, fees excluded
    stop, tgt = debit * (1 - x["fixed_stop"]), debit * (1 + x["fixed_target"])
    txt = (f"fixed stop -{x['fixed_stop']:.0%} of the debit (mid <= {stop:.4f}), target +{x['fixed_target']:.0%} "
           f"(mid >= {tgt:.2f}); all out {x['allout']}")
    return {"kind": "fixed", "debit": debit, "fixed_stop": x["fixed_stop"], "fixed_target": x["fixed_target"], "stop_mid": stop,
            "target_mid": tgt, "cost": round(cost, 6), "allout": x["allout"]}, txt, round((cost - costs.proceeds(stop)) * SFI.MULT * QTY, 2)


def _hm(minute):
    m = 570 + minute
    return f"{m // 60:02d}:{m % 60:02d}"


# ---------------------------------------------------------------- entries
def tick(ticker, snap, chain_rows_fn, now=None):
    """Per SPY/QQQ snapshot, every engine tick: each ledger's signals on the finished bars, decided once each."""
    if ticker not in SYMBOLS:
        return None
    now = now or core.now_et()
    sess = core.session_info(now)
    hm = now.strftime("%H:%M")
    if sess["holiday"] or hm < FIRST_TICK or hm >= LAST_TICK:
        return None
    if VIXY_WARM[0] <= hm < VIXY_WARM[1]:
        _warm_vixy(now)
    ctx, _why = context(ticker, (snap or {}).get("m1"), now)
    if ctx is None:
        return None
    out = {}
    for name in LEDGERS:
        try:
            out[name] = _run(name, ticker, ctx, chain_rows_fn, now)
        except Exception as e:
            _err(f"{name} {ticker}", e)
    return out


def _once(did, name, ticker, decision, why, data=None):
    if not S.decided(did):
        S.decide(did, name, ticker, decision, [why] if why else [], data or {}, "day", VERSION)


def _run(name, ticker, ctx, chain_rows_fn, now):
    day = ctx.day
    try:
        r = rules(name)
    except Exception as e:
        _once(f"{name}:{ticker}:{day}:refused", name, ticker, "REFUSED", f"rules unavailable: {e}", {"ledger": name})
        return "REFUSED"
    if not enabled(name):
        _once(f"{name}:{ticker}:{day}:disabled", name, ticker, "DISABLED", "switched off in config/v4.json (sprint_paper)",
              {"ledger": name, "run_id": r["run_id"]})
        return "DISABLED"
    got = []
    for sig in sorted(signals(ctx, r), key=lambda s: s.idx):            # stable: the engine's order within a bar
        d = evaluate(name, r, ticker, ctx, sig, chain_rows_fn, now)
        got.append(d)
        if d is None:
            break                                                     # waiting for this signal's fill: later ones wait
    if r["entry"] in SN.TIME_ENTRIES:
        idx = SN.TIME_ENTRIES[r["entry"]]
        did = _did(name, ticker, day, idx, r["entry"])
        if not S.decided(did) and (pd.Timestamp(now) - pd.Timestamp(bar_end(day, idx))).total_seconds() > WINDOW_S:
            S.decide(did, name, ticker, "NO SIGNAL", [f"no finished {_hm(idx)} bar today (the backtest has no signal then)"],
                     {"run_id": r["run_id"], "setup": r["entry"], "idx": idx}, "signal", VERSION)
    elif now.strftime("%H:%M") >= ("12:50" if ctx.early else DAY_DONE):
        sigs = signals(ctx, r)
        _once(f"{name}:{ticker}:{day}:day", name, ticker, "DAY", f"{len(sigs)} signal(s) today",
              {"run_id": r["run_id"], "signals": [{"idx": s.idx, "bar_end": bar_end(day, s.idx).strftime("%H:%M"),
                                                   "kind": s.info.get("kind"), "level": s.info.get("level")} for s in sigs]})
    return got


def _did(name, ticker, day, idx, tag):
    return f"{name}:{ticker}:{day}:{idx}:{tag}"


def _signal_data(r, ticker, sig, sig_end):
    return {"run_id": r["run_id"], "spec": r["spec"], "label": LABEL, "status": STATUS,
            "signal": {"setup": sig.setup, "side": sig.side, "idx": sig.idx, "bar": _hm(sig.idx), "signal_t": sig_end.isoformat(),
                       "price": sig.price, "invalid": sig.invalid, "level": sig.info.get("level"), "kind": sig.info.get("kind")}}


def evaluate(name, r, ticker, ctx, sig, chain_rows_fn, now):
    """Decide one signal (once). Returns the decision, or None while it waits for a fresh quote (retried next tick)."""
    day = ctx.day
    sig_end = bar_end(day, sig.idx)
    tag = sig.info.get("kind") or sig.setup
    did = _did(name, ticker, day, sig.idx, tag)
    if S.decided(did):
        return "DECIDED"
    pid = f"{name}:{day}-{ticker}-{sig.side}-{sig_end.strftime('%H%M')}-{tag}"
    base = _signal_data(r, ticker, sig, sig_end)
    st = store.kv_get(f"{did}:eval") or {}

    def final(decision, why, extra=None):
        S.decide(did, name, ticker, decision, [why] if why else [], dict(base, **st, **(extra or {})), "signal", VERSION)
        return decision
    if S.get(pid):
        return final("ORDER", None, {"position": pid, "note": "position already open (recorded after a restart)"})
    dec = sig.idx + 1
    sess = core.session_info(now)
    allout_idx = SM.EARLY_ALLOUT if ctx.early else SM.ALLOUT[r["exit"]["allout"]]
    if dec >= SM.NO_NEW_AFTER:
        return final("SKIP", "no new trades after 15:30 (backtest rule)")
    if dec >= allout_idx:
        return final("SKIP", "signal after the all-out time (backtest rule)")
    if sig_end.strftime("%H:%M") > sess["last_entry"]:
        return final("SKIP", f"signal bar finished after the desk's last entry {sess['last_entry']}")
    late = (pd.Timestamp(now) - pd.Timestamp(sig_end)).total_seconds()
    if late > WINDOW_S:
        return final("MISSED", f"no fill within {SFI.ENTRY_WAIT} minutes of the signal bar" if st else
                     f"first seen {late:.0f}s after the signal bar finished (the backtest fills within {SFI.ENTRY_WAIT} minutes): "
                     f"the desk was not running or the bars were late")
    if [p for p in S.positions(ledger=name, status="OPEN") if p["ticker"] == ticker]:
        return final("SKIP", "busy: one position at a time (backtest rule)")
    if not st:
        st, wait = _evaluate_filters(name, r, ticker, ctx, sig, sig_end, now)
        if wait:
            return None
        store.kv_set(f"{did}:eval", st)
    if st.get("filter_fail"):
        return final("FILTERED", st["filter_fail"])
    why = v4risk.admit(name, BOOK, ticker, "long" if sig.side == "C" else "short", now)
    if why:
        return final("BLOCKED-RISK", why)
    k = store.kv_get(f"{did}:contract")                    # chosen once; retries only re-quote it
    if not k:
        rows, err = chain_rows_fn(ticker, sig.side)
        if not rows:
            return None if late < WINDOW_S - FINAL_S else final("MISSED", f"no {'call' if sig.side == 'C' else 'put'} chain ({err})")
        k, kwhy = pick(ctx, sig, r["contract"], rows, sig_end)
        if not k:
            return final("SKIP", kwhy)
        store.kv_set(f"{did}:contract", k)
    q, qerr = marketdata.option_quote(k["symbol"])
    ok, qwhy = C.quote_after(q, sig_end, marketdata.MAX_OPT_QUOTE_AGE_S)
    if not ok:
        if late >= WINDOW_S - FINAL_S:
            return final("MISSED", f"no fresh executable quote within {SFI.ENTRY_WAIT} minutes of the signal bar: {qwhy or qerr}",
                         {"contract": k})
        return None
    fill, fee = S.option_buy(q, EXEC_MODEL)
    ex, ex_txt, risk = exit_plan(r, sig, fill, k["symbol"])
    strike = float(k["strike"])
    plan = {"source_run": r["run_id"], "spec": r["spec"], "spec_sha256": r["spec_sha256"], "label": LABEL, "status": status_of(name),
            "watch_only": WATCH_ONLY.get(name), "sprint_version": SPRINT_VERSION, "rules": {k2: v for k2, v in r.items() if k2 != "name"},
            "signal": base["signal"], "contract": k, "exit": ex, "exit_rule": ex_txt,
            "premium_stop": round(ex["stop_bid"] if ex["kind"] == "ceiling" else ex["stop_mid"], 4),
            "premium_stop_rule": ("ceiling on the bid" if ex["kind"] == "ceiling" else f"-{ex['fixed_stop']:.0%} of the debit on the mid"),
            "fill_quote": {k2: (str(q.get(k2)) if k2 == "quote_time" else q.get(k2)) for k2 in ("bid", "ask", "mid", "delta", "iv", "quote_time", "age_s")},
            "features": st.get("features"), "filters": {"list": list(r["filters"]), "result": "pass", "inputs": st.get("filter_inputs"),
                                                        "vixy_notes": st.get("vixy_notes"), "feature_rule": st.get("feature_rule")},
            "entry_underlying": float(ctx.c[sig.idx]), "bid": q["bid"], "ask": q["ask"]}
    rec = {"id": pid, "ledger": name, "book": BOOK, "kind": "option", "date": day.isoformat(), "ticker": ticker,
           "direction": "long" if sig.side == "C" else "short", "side": sig.side, "qty": QTY, "entry_px": fill, "entry_t": store.ts(),
           "signal_t": sig_end.isoformat(), "quote_t": str(q.get("quote_time")), "fees": round(fee * QTY, 4), "risk_usd": risk,
           "max_loss": round(fill * 100 * QTY + 2 * fee * QTY, 2),
           "legs": [{"symbol": k["symbol"], "label": f"{strike:g}{sig.side}", "right": sig.side, "strike": strike,
                     "expiry": day.isoformat(), "action": "buy", "qty": QTY}],
           "plan": plan, "version": VERSION, "exec_model": EXEC_MODEL}
    got, bwhy = S.open_position(rec, f"{name} signal {sig_end.strftime('%H:%M')} ({r['run_id']} twin)")
    return final("ORDER" if got else "SKIP", None if got else bwhy, {"position": got, "fill": fill, "contract": k, "exit": ex})


def _evaluate_filters(name, r, ticker, ctx, sig, sig_end, now):
    """(state, wait). sprint.engine._filters_ok on the context plus VIXY; features stamped from sprint.features."""
    fs = r["filters"]
    need_1m = any(f in fs for f in ("vixy_falling", "vixy_not_rising", "vixy_rising_1pct"))
    vx = vixy(now)
    m = vx.get("m1")
    if need_1m:
        have = m is not None and (m.index == pd.Timestamp(sig_end) - pd.Timedelta(minutes=1)).any()
        if not have and (pd.Timestamp(now) - pd.Timestamp(sig_end)).total_seconds() < VIXY_GRACE_S:
            return None, True                                          # VIXY's bar of the signal minute may still arrive
    aux = {"VIXY_D": vx.get("daily")}
    if m is not None and len(m):
        aux["VIXY"] = SD.Series("VIXY", _frame(m))
    c2 = copy.copy(ctx)
    c2.aux = aux
    n_today = len([p for p in S.positions(ledger=name, day=ctx.day.isoformat()) if p["ticker"] == ticker])
    fail = SE._filters_ok({"filters": fs}, c2, sig, n_today)
    feats = SF.entry_features(c2, sig.idx, sig.side)
    frule = feature_rule(name, feats)
    if not fail and frule and frule["fail"]:
        fail = frule["fail"]
    return {"filter_fail": fail, "filter_inputs": _filter_inputs(c2, sig), "features": feats, "feature_rule": frule,
            "vixy_notes": vx.get("notes")}, False


def feature_rule(name, feats):
    """FEATURE_RULES[name] on the stamped entry features: {"rules": [...], "values": {...}, "fail": None | why}."""
    rs = FEATURE_RULES.get(name)
    if not rs:
        return None
    vals, fail = {}, None
    for feat, op, cut in rs:
        v = (feats or {}).get(feat)
        vals[feat] = v
        if fail:
            continue
        if v is None:
            fail = f"{feat} unknown (needs 10+ prior sessions of bars): rule {feat} {op} {cut} cannot be checked"
        elif not {">=": v >= cut, "<=": v <= cut}[op]:
            fail = f"{feat} {v:g} fails rule {feat} {op} {cut:g}"
    return {"rules": [f"{f} {o} {c:g}" for f, o, c in rs], "values": vals, "fail": fail}


# ---------------------------------------------------------------- management (every engine tick, risk priority)
def manage(p, now=None):
    """Pending exits first, then all out, then the ledger's own stop on live quotes. Never blocked by any switch."""
    now = now or core.now_et()
    pl = p.get("plan") or {}
    if pl.get("pending_exit"):
        return v4exec.retry_pending(p)
    sess = core.session_info(now)
    sym = p["legs"][0]["symbol"]
    q, _ = marketdata.option_quote(sym)
    ok = v4exec._q_ok(q)
    if ok:
        mid = (q["bid"] + q["ask"]) / 2
        mv = round((q["bid"] - p["entry_px"]) / p["entry_px"] * 100, 1) if p["entry_px"] else 0.0
        S.mark(p["id"], mv, mv)
        S.update_plan(p["id"], last_bid=q["bid"], last_mid=round(mid, 4),
                      mtm=round((q["bid"] - p["entry_px"]) * 100 * p["qty"] - (p["fees"] or 0), 2))
    if now.strftime("%H:%M") >= sess["all_out"]:
        return v4exec.close_now(p, f"ALL OUT {sess['all_out']} (backtest all-out time; 12:50 on early-close days)")
    if not ok:
        return None
    ex = pl.get("exit") or {}
    if ex.get("kind") == "ceiling" and q["bid"] <= ex["stop_bid"]:
        return v4exec.close_now(p, f"CEILING STOP {ex['ceiling']:.0%} ({ex['window']} window): bid {q['bid']:.2f} <= {ex['stop_bid']:.4f}, "
                                   f"proceeds net of fees <= cost x {1 - ex['ceiling']:.2f}", quotes={sym: q})
    if ex.get("kind") == "fixed":
        if mid <= ex["stop_mid"]:
            return v4exec.close_now(p, f"FIXED STOP -{ex['fixed_stop']:.0%}: mid {mid:.4f} <= {ex['stop_mid']:.4f}", quotes={sym: q})
        if mid >= ex["target_mid"]:
            return v4exec.close_now(p, f"FIXED TARGET +{ex['fixed_target']:.0%}: mid {mid:.4f} >= {ex['target_mid']:.4f}", quotes={sym: q})
    return None


# ---------------------------------------------------------------- views
def report_meta(name):
    spec_id, run_id, _sha, label = PINS[name]
    bt = dict(BACKTEST[name])
    bt.setdefault("label", "BACKTEST in-sample (DEV), MODELED spread")
    return {"evidence": LABEL, "status": status_of(name), "source_run": run_id, "label": label, "watch_only": WATCH_ONLY.get(name),
            "enabled": enabled(name), "refusal": refusal(name), "backtest": bt, "feature_rules": [f"{f} {o} {c:g}" for f, o, c in
                                                                                                  FEATURE_RULES.get(name, ())],
            "symbols": list(SYMBOLS)}


def status():
    out = {"version": VERSION, "sprint_version": SPRINT_VERSION, "book": BOOK, "symbols": list(SYMBOLS), "label": LABEL, "status": STATUS,
           "exec_model": S.EXEC[EXEC_MODEL], "entry_window_s": WINDOW_S, "deviations": DEVIATIONS,
           "last_error": _state["last_error"], "errors": _state["errors"], "ledgers": {}}
    for name in LEDGERS:
        try:
            rr = rules(name)
        except Exception as e:
            rr = {"error": str(e)}
        out["ledgers"][name] = dict(report_meta(name), rules=rr)
    return out
