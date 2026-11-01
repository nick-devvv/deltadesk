#!/usr/bin/env python3
"""tools/sprint_pull10.py - READ-ONLY option-bar pull for sprint round 10 (SPRINT_PLAN Amendment 16, "Data the next Chart run
needs"). Runs on Chart's computer in ~/sprint AFTER round 9's pull (tools/sprint_pull9.py: assets, daily, edgar_index,
edgar_headers); Claude's workspace can't reach Alpaca. Never trades: no orders, no account, no positions.

  python3 tools/sprint_pull10.py                      # every stage in order; safe to stop and re-run (finished work is skipped)
  python3 tools/sprint_pull10.py --estimate           # requests and hours from the universe size (no network)
  python3 tools/sprint_pull10.py --status             # what is done, what is left, disk used (no network)
  python3 tools/sprint_pull10.py --div-scope rebalance  # D-IV only on the sessions V1/V2/V2-s read (rebalance day + 5 before)
  python3 tools/sprint_pull10.py --providers div      # only some providers of the "needs" stage

Host: https://data.alpaca.markets only (via tools/pull_alpaca: its 180-a-minute limiter and host guard). Keys: ALPACA_KEY /
ALPACA_SECRET (the desk's paper key, market data); never printed. Network errors (connection drops, timeouts, DNS) and
429/5xx answers are retried with backoff 5, 15, 30, 60, 120, 300 s, then the stage stops with a message; re-running the same
command resumes.
Stages:
  stock15  raw 1-minute stock bars 15:45-16:00 of every D-IV name (U-ETF + the U-STK names passing round 9's filter that
           day) on every DEV session: data/alpaca/r10/stock15/<day>.csv.gz (+ .json marker). 100 symbols a request.
  needs    option 1-minute bars asked for by the registered "needs" providers, repeated until no provider needs more (a
           provider may ask in phases: D-IV probes the next expiry only where the last one had no print). Files:
           data/alpaca/r10/opt/<day>/<HHMM-HHMM>.pNNNN.csv.gz (append-only parts) + <HHMM-HHMM>.json (asked + printed).
           Providers on this branch: "div" (sprint/ivdata.py: D-IV, 15:45-16:00, 2 expiries x the strikes bracketing spot)
           and "r10swing" (sprint/r10swing.py: V1/V2 exit legs, V2-s condor legs, the V3 and V4 option twins).
The registry ("needs" providers): a provider is any function that returns the option contracts a round-10 part needs. Plug
one in with ONE line next to the two below, e.g.
      register("r10grid", r10grid.needed_option_contracts)
      register("r10credit", r10credit.needed_option_contracts, window=("09:30", "16:00"))
  * It is called with the pull's context: by parameter name (ctx, root, log, days, a, b, start, end, bars, universe) or, for a
    one-parameter function with another name, with ctx itself. Wrap anything else: register("x", lambda ctx: f(ctx.root)).
  * It may return: ivdata.Need tuples; dicts {"day", "symbols" (or "symbol" / "contracts"), optional "window" or
    "t0"/"t1"}; tuples (day, symbols), (day, symbols, window) or (day, symbol, t0, t1); or a mapping {day: [symbols]}. Days
    are dates or ISO strings; symbols are OCC option symbols; a window is ("HH:MM", "HH:MM") ET. Without a window the
    registration's window is used, else the whole session 09:30-16:00.
  * It is called again after each fetch round, so it can ask in phases from what is already on file (ctx.bars.asked /
    printed / last15 / opens / first_prints). Returning nothing new ends it.
Locked periods: every requested day is checked against L1 (2026-07-01..10-30) and L2 (2024-02-01..07-31) before any request;
a provider asking for a locked day is refused (counted and logged), never requested.
Estimate (estimate(); --estimate measures the universe from the cached daily bars): at about 1,000 U-STK names + 20 ETFs a
day over DEV's 479 sessions, about 208,000 requests = about 19 hours at 180 a minute (D-IV is about 190,000 of them);
--div-scope rebalance cuts D-IV to the 132 sessions V1/V2/V2-s read: about 70,000 requests, about 6.5 hours. Requests scale
linearly with the names a day. The rebalance windows are pulled first either way, so a stopped pull is still useful.
"""
import argparse
import inspect
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
import pull_alpaca as PA  # noqa: E402
from sprint import ivdata as IV  # noqa: E402
from sprint import periods  # noqa: E402
from sprint import r10swing as SW  # noqa: E402
from sprint import universe as U  # noqa: E402
from sprint.data import parse_occ  # noqa: E402

ET = "America/New_York"
STAGES = ("stock15", "needs")
BATCH = 100
NET_BACKOFF = (5, 15, 30, 60, 120, 300)
MAX_ROUNDS = 40
PROVIDERS = {}


class Refused(periods.LockedPeriod):
    pass


def check_window(a, b):
    hit = periods.overlaps(a, b)
    if hit:
        raise Refused(f"REFUSED: {a}..{b} touches locked period(s) {', '.join(hit)}")


def _utc(d, hhmm):
    return pd.Timestamp(f"{d} {hhmm}", tz=ET).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- the registry
def register(name, fn, window=None):
    """Add a "needs" provider (see the module docstring). Re-registering a name replaces it."""
    PROVIDERS[name] = {"fn": fn, "window": tuple(window) if window else None}
    return fn


register("div", IV.needed_option_contracts)
register("r10swing", SW.needed_option_contracts)
# Round 10 integrator: one line each, e.g.
#   from sprint import r10grid, r10credit
#   register("r10grid", r10grid.needed_option_contracts)
#   register("r10credit", r10credit.needed_option_contracts)

OFFERS = ("ctx", "root", "log", "days", "a", "b", "start", "end", "bars", "universe")


def call_provider(name, fn, ctx):
    """Call a provider with what its signature asks for (by name), or with ctx alone."""
    sig = inspect.signature(fn)
    ps = [p for p in sig.parameters.values() if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
    offer = ctx.offers()
    kw, pos = {}, []
    for k, p in enumerate(ps):
        if p.name in offer:
            if p.kind == p.POSITIONAL_ONLY:
                pos.append(offer[p.name])
            else:
                kw[p.name] = offer[p.name]
        elif p.default is not p.empty:
            continue
        elif k == 0 and len([q for q in ps if q.default is q.empty]) == 1:
            pos.append(ctx)
        else:
            raise TypeError(f"provider {name!r}: cannot fill parameter {p.name!r} (offered: {', '.join(OFFERS)}); register it "
                            f"with a lambda, e.g. register({name!r}, lambda ctx: fn(...))")
    return fn(*pos, **kw)


def _day(x):
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return date.fromisoformat(str(x)[:10])


def _win(w, default):
    if w is None:
        return tuple(default)
    if isinstance(w, str) and "-" in w and ":" not in w:                      # "1545-1600"
        a, b = w.split("-")
        return (f"{a[:2]}:{a[2:]}", f"{b[:2]}:{b[2:]}")
    a, b = w
    return (str(a)[:5], str(b)[:5])


def _syms(v):
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    return [str(s) for s in v]


def normalize(result, default_window, tag):
    """Any accepted provider return shape -> [ivdata.Need]; raises ValueError on a shape it cannot read."""
    dw = default_window or IV.W_DAY
    out = []
    if result is None:
        return out
    if isinstance(result, dict) and not ({"day"} <= set(result)):
        result = [(d, s) for d, s in result.items()]
    elif isinstance(result, dict):
        result = [result]
    for it in result:
        if isinstance(it, IV.Need):
            out.append(IV.need(_day(it.day), _win(it.window, dw), it.symbols, it.tag or tag, it.priority))
        elif isinstance(it, dict):
            syms = _syms(it.get("symbols", it.get("contracts", it.get("symbol"))))
            w = it.get("window") or ((it["t0"], it["t1"]) if "t0" in it else None)
            out.append(IV.need(_day(it["day"]), _win(w, dw), syms, tag, it.get("priority", 1)))
        elif hasattr(it, "day") and (hasattr(it, "symbols") or hasattr(it, "symbol")):
            syms = _syms(getattr(it, "symbols", None) or getattr(it, "symbol", None))
            out.append(IV.need(_day(it.day), _win(getattr(it, "window", None), dw), syms, tag, getattr(it, "priority", 1)))
        elif isinstance(it, (tuple, list)) and len(it) in (2, 3, 4):
            if len(it) == 4:
                out.append(IV.need(_day(it[0]), _win((it[2], it[3]), dw), _syms(it[1]), tag))
            else:
                out.append(IV.need(_day(it[0]), _win(it[2] if len(it) == 3 else None, dw), _syms(it[1]), tag))
        else:
            raise ValueError(f"provider {tag!r}: cannot read a need of type {type(it).__name__}: {it!r}"[:300])
    return out


# ---------------------------------------------------------------- Alpaca market data with network retries
def alpaca_get(path, params, sleep=None, log=None):
    """pull_alpaca.get's paging and host guard, plus retries on network errors (not only 429/5xx). Keys never printed."""
    sleep = sleep or time.sleep
    key, sec = os.environ.get("ALPACA_KEY"), os.environ.get("ALPACA_SECRET")
    if not key or not sec:
        raise RuntimeError("ALPACA_KEY / ALPACA_SECRET are not set (the desk's paper key, market data only)")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec, "Accept": "application/json"}
    token = None
    while True:
        p = dict(params, **({"page_token": token} if token else {}))
        url = PA._guard(f"{PA.DATA_HOST}{path}?{urllib.parse.urlencode(p)}")
        j = None
        for attempt in range(len(NET_BACKOFF) + 1):
            PA._throttle()
            try:
                j = PA._http(url, headers)
                break
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"Alpaca answered HTTP {e.code} for {path} (not retried)") from None
                why = f"HTTP {e.code}"
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                why = type(e).__name__
            if attempt >= len(NET_BACKOFF):
                raise ConnectionError(f"{why} on {path}: gave up after {len(NET_BACKOFF)} retries") from None
            if log:
                log(f"  {why} on {path}; retry {attempt + 1} of {len(NET_BACKOFF)} in {NET_BACKOFF[attempt]} s")
            sleep(NET_BACKOFF[attempt])
        yield j
        token = j.get("next_page_token")
        if not token:
            return


def _bars(path, symbols, params, log=None, batch=BATCH):
    rows = []
    symbols = list(symbols)
    for i in range(0, len(symbols), batch):
        for page in alpaca_get(path, dict(params, symbols=",".join(symbols[i:i + batch])), log=log):
            for s, lst in (page.get("bars") or {}).items():
                rows += [dict(x, symbol=s) for x in lst or []]
    return PA._frame(rows)


def opt_bars(symbols, day, window, log=None):
    check_window(day, day)
    return _bars("/v1beta1/options/bars", symbols, {"timeframe": "1Min", "start": _utc(day, window[0]), "end": _utc(day, window[1]),
                                                    "limit": 10000, "sort": "asc"}, log)


def stock_bars(symbols, day, window, feed="sip", log=None):
    check_window(day, day)
    return _bars("/v2/stocks/bars", symbols, {"timeframe": "1Min", "start": _utc(day, window[0]), "end": _utc(day, window[1]),
                                              "limit": 10000, "adjustment": "raw", "feed": feed, "sort": "asc"}, log)


# ---------------------------------------------------------------- the store (write side; sprint/ivdata.py reads)
def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj))
    tmp.replace(path)


def merge_opt(root, day, window, symbols, fetch):
    """Fetch the symbols of `symbols` not yet asked for on (day, window) as a new part file, then update the marker (asked,
    printed). Returns the number of symbols fetched."""
    mk = IV.opt_marker(root, day, window)
    m = IV.read_marker(mk)
    asked, printed = set(m.get("asked") or []), set(m.get("printed") or [])
    miss = sorted(set(symbols) - asked)
    if not miss:
        return 0
    df = fetch(miss)
    parts = IV.opt_parts(root, day, window)
    n = 1 + max([int(p.name.split(".p")[1][:4]) for p in parts] or [0])
    if len(df):
        df = df.drop_duplicates(["symbol", "ts"]).sort_values(["symbol", "ts"]).reset_index(drop=True)
        PA._write_gz(IV.opt_dir(root, day) / f"{IV.wkey(window)}.p{n:04d}.csv.gz", df)
        printed |= set(df["symbol"].astype(str))
    _write_json(mk, {"window": list(window), "asked": sorted(asked | set(miss)), "printed": sorted(printed),
                     "rows": int(m.get("rows") or 0) + int(len(df)), "parts": n if len(df) else n - 1})
    return len(miss)


def merge_stock(root, day, symbols, fetch):
    path = IV.stock_path(root, day)
    mk = IV.marker_path(path)
    m = IV.read_marker(path)
    asked = set(m.get("asked") or [])
    miss = sorted(set(symbols) - asked)
    if not miss:
        return 0
    new = fetch(miss)
    old = PA.read_gz(path) if path.exists() else None
    frames = [x for x in (old, new) if x is not None and len(x)]
    df = pd.concat(frames, ignore_index=True) if frames else new
    if len(df):
        df = df.drop_duplicates(["symbol", "ts"]).sort_values(["symbol", "ts"]).reset_index(drop=True)
    PA._write_gz(path, df)
    _write_json(mk, {"asked": sorted(asked | set(miss)), "rows": int(len(df))})
    return len(miss)


# ---------------------------------------------------------------- the providers' context
def rebalance_window_days():
    """The DEV sessions V1/V2/V2-s read: each rebalance day and the 5 sessions before it (pulled first)."""
    dev = IV.dev_days()
    pos = {d: k for k, d in enumerate(dev)}
    out = set()
    for t, _x in SW.holds()[0]:
        k = pos.get(t)
        if k is not None:
            out |= set(dev[max(0, k - IV.MEAN_N):k + 1])
    return out


class Ctx:
    """What a provider sees: root, log, warn, bars (ivdata.Bars), days (D-IV's DEV sessions in scope), span (the pull's
    (first, last) day; providers stay inside it), universe(day),
    stock_minutes(day), asked/printed(day, window), is_done/mark_done(day, tag), div_result(day, names), priority(day),
    cache (a dict kept for the whole run), offers() (for the registry)."""

    def __init__(self, root, log, days, panels=None, span=None):
        self.root, self.log = Path(root), log
        self.bars = IV.Bars(root, keep=64)
        self.days = list(days)
        self.span = tuple(span) if span else (IV.DEV_A, IV.DEV_B)
        self.cache = {}
        self.warnings = []
        if panels is not None:
            self.cache["r10_panels"] = panels
        self._uni = None
        self._done = {}
        self._prio = rebalance_window_days()

    def warn(self, msg):
        if msg not in self.warnings:
            self.warnings.append(msg)
            self.log(f"WARNING: {msg}")

    def offers(self):
        a, b = self.span
        return {"ctx": self, "root": self.root, "log": self.log, "days": self.days, "a": a, "b": b, "start": a, "end": b,
                "bars": self.bars, "universe": self.universe}

    def panels(self):
        if "r10_panels" not in self.cache:
            self.cache["r10_panels"] = SW.load_panels(self.root, self.log)
        return self.cache["r10_panels"]

    def universe(self, day):
        if self._uni is None:
            self._uni = SW.Universe(self.panels())
        return self._uni.names(day)

    def stock_minutes(self, day):
        return self.bars.stock_minutes(day)

    def asked(self, day, window):
        return self.bars.asked(day, window)

    def printed(self, day, window):
        return self.bars.printed(day, window)

    def priority(self, day):
        return 0 if day in self._prio else 1

    def _done_path(self, day, tag):
        return IV.opt_dir(self.root, day) / f"{tag}.done"

    def is_done(self, day, tag):
        k = (day, tag)
        if k not in self._done:
            self._done[k] = self._done_path(day, tag).exists()
        return self._done[k]

    def mark_done(self, day, tag):
        p = self._done_path(day, tag)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"at": datetime.now().isoformat(timespec="seconds")}))
        self._done[(day, tag)] = True

    def div_result(self, day, names):
        return IV.day_result(self.root, day, names)


# ---------------------------------------------------------------- stages
class Progress:
    def __init__(self, stage, total, log, every=30.0, clock=time.time):
        self.stage, self.total, self.log, self.every, self.clock = stage, max(int(total), 0), log, every, clock
        self.t0 = self.last = clock()
        self.done = 0
        self.log(f"[{stage}] {self.total} to do")

    def step(self, n=1):
        self.done += n
        now = self.clock()
        if now - self.last >= self.every or self.done >= self.total:
            self.last = now
            el = now - self.t0
            rate = self.done / el if el > 0 else 0.0
            left = (self.total - self.done) / rate / 60 if rate > 0 else 0.0
            self.log(f"[{self.stage}] {self.done}/{self.total} ({100.0 * self.done / max(self.total, 1):.1f}%), {el / 60:.1f} min so "
                     f"far, about {left:.0f} min left")


def ordered_days(ctx, days):
    return sorted(days, key=lambda d: (ctx.priority(d), d))


def pull_stock15(ctx, feed="sip", days=None):
    """Raw 1-minute stock bars 15:45-16:00 of each day's D-IV names."""
    days = ordered_days(ctx, days if days is not None else IV.dev_days())
    out = {"days": len(days), "asked": 0, "refused": 0, "skipped": 0}
    pr = Progress("stock15", len(days), ctx.log)
    for d in days:
        try:
            check_window(d, d)
        except Refused:
            out["refused"] += 1
            pr.step()
            continue
        names = ctx.universe(d)
        n = merge_stock(ctx.root, d, names, lambda syms, d=d: stock_bars(syms, d, IV.W_LAST, feed, ctx.log))
        if n == 0 and IV.marker_path(IV.stock_path(ctx.root, d)).exists():
            out["skipped"] += 1
        out["asked"] += n
        ctx.bars.invalidate(d)
        pr.step()
    return out


def collect(ctx, names=None):
    """{(day, window): (symbols not yet asked, priority, tags)} from every provider, and the refused / error counts."""
    want = defaultdict(set)
    prio, tags = {}, defaultdict(set)
    refused, errors = defaultdict(int), {}
    for name, spec in PROVIDERS.items():
        if names and name not in names:
            continue
        try:
            res = normalize(call_provider(name, spec["fn"], ctx), spec["window"], name)
        except (TypeError, ValueError) as e:
            errors[name] = str(e)
            ctx.warn(f"provider {name}: {e}")
            continue
        for nd in res:
            if periods.overlaps(nd.day, nd.day):
                refused[name] += 1
                continue
            bad = [s for s in nd.symbols if parse_occ(s) is None]
            if bad:
                errors[name] = f"not OCC option symbols: {bad[:3]}"
            key = (nd.day, nd.window)
            want[key] |= {s for s in nd.symbols if parse_occ(s) is not None}
            prio[key] = min(prio.get(key, 9), nd.priority)
            tags[key].add(nd.tag or name)
    new = {}
    for key, syms in want.items():
        miss = syms - ctx.asked(*key)
        if miss:
            new[key] = (sorted(miss), prio[key], sorted(tags[key]))
    return new, dict(refused), errors


def pull_needs(ctx, providers=None, max_rounds=MAX_ROUNDS):
    """Rounds of collect -> fetch until no provider needs anything new."""
    out = {"rounds": 0, "day_windows": 0, "contracts": 0, "requests_est": 0, "refused": defaultdict(int), "errors": {}}
    for rnd in range(1, max_rounds + 1):
        new, refused, errors = collect(ctx, providers)
        for k, v in refused.items():
            if v:
                ctx.log(f"[needs] REFUSED {v} need(s) of provider {k} inside L1/L2 (never requested)")
            out["refused"][k] += v
        out["errors"].update(errors)
        if not new:
            break
        out["rounds"] = rnd
        n_c = sum(len(v[0]) for v in new.values())
        n_r = sum(math.ceil(len(v[0]) / BATCH) for v in new.values())
        ctx.log(f"[needs] round {rnd}: {len(new)} day-windows, {n_c} contracts, about {n_r} requests "
                f"(~{n_r / PA.MAX_PER_MIN:.0f} min at {PA.MAX_PER_MIN} a minute)")
        pr = Progress(f"needs round {rnd}", len(new), ctx.log)
        for (d, w), (syms, _p, _t) in sorted(new.items(), key=lambda kv: (kv[1][1], kv[0][0], kv[0][1])):
            check_window(d, d)
            merge_opt(ctx.root, d, w, syms, lambda s, d=d, w=w: opt_bars(s, d, w, ctx.log))
            ctx.bars.invalidate(d, w)
            out["contracts"] += len(syms)
            out["requests_est"] += math.ceil(len(syms) / BATCH)
            out["day_windows"] += 1
            pr.step()
    else:
        ctx.warn(f"needs: stopped after {max_rounds} rounds with providers still asking; re-run to continue")
    out["refused"] = dict(out["refused"])
    return out


# ---------------------------------------------------------------- the estimate (no network)
def estimate(n_days, names_per_day, rebalances=22, v3_events=None, v4_trades=None, div_scope="all", per_min=None):
    """Requests and minutes, from the universe size. Assumptions (stated, not measured): about 5 strikes per expiry probe
    (2 per plausible grid, 3-4 grids, overlaps), 1.4 probes for the 30-day expiry and 2.5 for the 90-day one on average;
    V2-s probes about 4 strikes x 3 grids per condor leg; every probe or fetch of 100 contracts is one request (15 or 390
    one-minute bars each fit one page except whole-day windows of more than 25 contracts)."""
    per_min = per_min or PA.MAX_PER_MIN
    names = float(names_per_day)
    d_div = n_days if div_scope == "all" else min(n_days, rebalances * (IV.MEAN_N + 1))
    v3 = v3_events if v3_events is not None else int(0.10 * names * 4)
    v4 = v4_trades if v4_trades is not None else 60
    st = {"stock15": n_days * math.ceil(names / BATCH),
          "div": int(d_div * math.ceil(names * 2 * 5 * (1.4 + 2.5) / BATCH)),
          "v1_v2_v2s": int(rebalances * math.ceil(names * (4 * 10 + 6) / BATCH) + rebalances * 3),
          "v3_twin": int(v3 * (1 + SW.V3_POOL) * 1.3 * 0.5),
          "v4_twin": int(v4 * 6)}
    tot = sum(st.values())
    return {"days": n_days, "div_days": d_div, "names_per_day": round(names, 1), "requests": st, "total_requests": tot,
            "minutes": round(tot / per_min, 1), "hours": round(tot / per_min / 60, 1), "per_minute": per_min}


def estimate_from_cache(root, log, div_scope="all"):
    """The estimate with the universe measured from the cached daily bars when they exist, else 1,000 U-STK names a day."""
    days = IV.dev_days()
    avg, src = None, None
    if U.read_ustk(root):
        uni = SW.Universe(SW.load_panels(root, None))
        sample = days[::20]
        avg = sum(len(uni.names(d)) for d in sample) / max(len(sample), 1)
        src = f"the U-STK filter on {len(sample)} sampled DEV sessions"
    if not avg or avg <= len(U.U_ETF):
        avg, src = len(U.U_ETF) + 1000, "an assumed 1,000 U-STK names a day (no U-STK daily bars to measure)"
    e = estimate(len(days), avg, len(SW.holds()[0]), div_scope=div_scope)
    log(f"Estimate (no network): {len(days)} DEV sessions, about {e['names_per_day']} D-IV names a day (from {src}); "
        f"D-IV on {e['div_days']} sessions ({div_scope}).")
    for k, v in e["requests"].items():
        log(f"  {k:<10} about {v:>9,} requests  ({v / e['per_minute'] / 60:.1f} h)")
    log(f"  total      about {e['total_requests']:>9,} requests at {e['per_minute']} a minute = about {e['hours']} hours "
        f"(resumable; the rebalance windows are pulled first)")
    return e


# ---------------------------------------------------------------- status (no network)
def disk_mb(root):
    p = Path(root) / IV.R10
    return round(sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6, 1) if p.exists() else 0.0


def status(root, log, days=None):
    days = days or IV.dev_days()
    root = Path(root)
    n_st = sum(1 for d in days if IV.marker_path(IV.stock_path(root, d)).exists())
    n_div = sum(1 for d in days if (IV.opt_dir(root, d) / "div.done").exists())
    n_files = len(list((root / IV.R10 / "opt").rglob("*.json"))) if (root / IV.R10 / "opt").exists() else 0
    log(f"stock15: {n_st} of {len(days)} DEV sessions")
    log(f"D-IV: {n_div} of {len(days)} DEV sessions finished (div.done)")
    log(f"option day-windows on file: {n_files}")
    log(f"providers registered: {', '.join(PROVIDERS)}")
    log(f"disk used by round 10: {disk_mb(root)} MB")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read-only option-bar pull for sprint round 10 (Alpaca market data only)")
    ap.add_argument("--only", default=None, help="comma-separated stages: " + ",".join(STAGES))
    ap.add_argument("--providers", default=None, help="comma-separated providers for the needs stage (default: all registered)")
    ap.add_argument("--root", default=None, help="cache root (default data/alpaca)")
    ap.add_argument("--feed", default="sip", choices=["sip", "iex"])
    ap.add_argument("--div-scope", default="all", choices=["all", "rebalance"],
                    help="D-IV on every DEV session (default) or only on the rebalance days and the 5 sessions before each")
    ap.add_argument("--from", dest="a", default=None, help="first DEV session (default 2024-08-01)")
    ap.add_argument("--to", dest="b", default=None, help="last DEV session (default 2026-06-30)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--estimate", action="store_true")
    x = ap.parse_args(argv)
    if x.root:
        PA.ROOT = Path(x.root)
    root = PA.ROOT
    log = lambda s: print(s, flush=True)
    a = date.fromisoformat(x.a) if x.a else IV.DEV_A
    b = date.fromisoformat(x.b) if x.b else IV.DEV_B
    try:
        check_window(a, b)
    except Refused as e:
        log(str(e))
        return 2
    days = [d for d in IV.dev_days() if a <= d <= b]
    if x.status:
        status(root, log, days)
        return 0
    if x.estimate:
        estimate_from_cache(root, log, x.div_scope)
        return 0
    stages = [s.strip() for s in (x.only or ",".join(STAGES)).split(",") if s.strip()]
    bad = [s for s in stages if s not in STAGES]
    if bad:
        ap.error(f"unknown stage(s) {bad}")
    provs = [p.strip() for p in x.providers.split(",")] if x.providers else None
    if provs and [p for p in provs if p not in PROVIDERS]:
        ap.error(f"unknown provider(s) {[p for p in provs if p not in PROVIDERS]} (registered: {', '.join(PROVIDERS)})")
    if not U.read_ustk(root):
        log("sprint_pull10: no U-STK list (data/alpaca/universe/ustk.json): run round 9's pull first "
            "(python3 tools/sprint_pull9.py). Only U-ETF names will be pulled.")
    log(f"sprint_pull10: stages {', '.join(stages)}; cache {root}; DEV {days[0] if days else '-'}..{days[-1] if days else '-'}; "
        f"L1 {periods.LOCKED['L1'][0]}..{periods.LOCKED['L1'][1]} and L2 {periods.LOCKED['L2'][0]}..{periods.LOCKED['L2'][1]} are "
        f"never requested; providers {', '.join(provs or PROVIDERS)}")
    win = rebalance_window_days()
    div_days = days if x.div_scope == "all" else [d for d in days if d in win]
    ctx = Ctx(root, log, div_days, span=(a, b))
    t0 = time.time()
    try:
        for st in stages:
            ts = time.time()
            if st == "stock15":
                log(f"[stock15] {pull_stock15(ctx, x.feed, days)}")
            elif st == "needs":
                log(f"[needs] {pull_needs(ctx, provs)}")
            log(f"[{st}] finished in {(time.time() - ts) / 60:.1f} min; {disk_mb(root)} MB on disk for round 10")
    except periods.LockedPeriod as e:
        log(str(e))
        return 2
    except ConnectionError as e:
        log(f"network kept failing ({e}); re-run the same command later to resume")
        return 4
    except RuntimeError as e:
        log(f"stopped: {e}")
        return 3
    for w in ctx.warnings:
        log(f"WARNING: {w}")
    log(f"sprint_pull10 done in {(time.time() - t0) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
