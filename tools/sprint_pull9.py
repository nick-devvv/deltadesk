#!/usr/bin/env python3
"""tools/sprint_pull9.py - READ-ONLY data pull for sprint round 9 (SPRINT_PLAN Amendments 12 and 13). Runs on Chart's computer
in ~/sprint; Claude's workspace can't reach Alpaca or SEC. Never trades: no orders, no account, no positions.

  python3 tools/sprint_pull9.py                 # every stage in order; safe to stop and re-run (finished work is skipped)
  python3 tools/sprint_pull9.py --status        # what is done, what is left, disk used (no network)
  python3 tools/sprint_pull9.py --only daily,edgar_headers

Hosts (each guarded; nothing else is ever requested):
  * https://data.alpaca.markets           market data (via tools/pull_alpaca.get: 180 requests a minute, under the free 200)
  * https://paper-api.alpaca.markets/v2/assets   ONE read-only listing of today's active US equities (U-STK needs "every
                                          US common stock Alpaca lists today as active and tradable, with listed options");
                                          no other trading-API path is ever called
  * https://www.sec.gov/                  EDGAR daily form indexes, filing index headers and company_tickers.json, at most
                                          10 requests a second (sprint/edgar.Throttle) with the desk's SEC_USER_AGENT
Keys: ALPACA_KEY / ALPACA_SECRET (the desk's paper key, market data). SEC_USER_AGENT from the environment, else ONLY its
line in the desk's env file ~/.config/deltadesk/deltadesk.env; never printed.
Stages (in order; each writes .done markers and resumes):
  assets         data/alpaca/universe/assets.json + ustk.json (U-STK list with every exclusion and its reason)
  daily          daily bars 2015-11-01..2026-06-30, L1/L2 cut out, raw and split-adjusted, U-ETF + U-STK:
                 data/alpaca/daily9/{raw,split}/<SYM>.csv.gz (100 symbols a request batch)
  fopt           F-opt (DEV only): for each F1/F2 U-ETF share trade in DEV, the entry day's 09:30-09:35 call bars of every
                 strike 85%-101% of the open, every listed expiry 30-60 days out, then the chosen call's exit-day bars:
                 data/alpaca/options_fopt/<SYM>/<day>/entry.csv.gz, exit.csv.gz
  weekly         Part I (DEV only): on each SPY/QQQ/IWM FIN-H signal day (11:00, relative volume >= 1.06), the call bars of
                 the first listed expiry 5-10 calendar days out (probed nearest first), every $1 strike from the day's low to
                 12% above its high:
                 data/alpaca/options_w5/<SYM>/<day>/bars.csv.gz
  edgar_index    EDGAR daily form indexes 2015-12-31..2026-06-30 (never an L1/L2 day): data/edgar/index/<day>.json (8-K
                 rows) + company_tickers.json
  edgar_headers  each U-STK 8-K's index headers (acceptance time, items), only for CIKs whose ticker passes the U-STK filter
                 on the first session on/after the filing date or the next one: data/edgar/headers.jsonl (append-only;
                 6 worker threads share the one 10-a-second throttle, to hide network latency)
  g1             G1 event-day 1-minute bars (split-adjusted, 09:30-16:00) for every G1 event: data/alpaca/g1_bars/<day>.csv.gz
  g2             G2 straddle option bars (DEV only), 15:30-16:00 of entry and exit days, for every Item 2.02 event and its 5
                 random non-earnings pool dates: data/alpaca/options_g2/<day>/entry.csv.gz, exit.csv.gz
Locked periods: every requested date and every multi-day window (F-opt and G2 entry..exit) is checked against L1 and L2
and refused before any request (counted as "refused"); the daily ranges are cut around them.
"""
import argparse
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
import pull_alpaca as PA  # noqa: E402
from sprint import catalyst as C  # noqa: E402
from sprint import contracts, periods  # noqa: E402
from sprint import data as D  # noqa: E402
from sprint import edgar as E  # noqa: E402
from sprint import multiday as M  # noqa: E402
from sprint import universe as U  # noqa: E402
from sprint import weekly as W  # noqa: E402

ET = "America/New_York"
TRADING_HOST = "https://paper-api.alpaca.markets"
ASSETS_URL = TRADING_HOST + "/v2/assets?status=active&asset_class=us_equity"
STAGES = ("assets", "daily", "fopt", "weekly", "edgar_index", "edgar_headers", "g1", "g2")
SEC_STAGES = ("edgar_index", "edgar_headers", "g1", "g2")   # g1/g2 need the 8-K headers
SEC_PROBE_URL = "https://www.sec.gov/robots.txt"


def sec_reachable(http=None, deadline=30.0):
    """One GET of www.sec.gov with a hard deadline (a thread, so even a connection that hangs past its socket timeout can't
    block the pull). True when SEC answers at all, except 403 (SEC refusing this computer); False on no answer (599) or no
    answer within the deadline."""
    import threading
    http = http or E.default_http
    box = {}
    t = threading.Thread(target=lambda: box.setdefault("r", http(SEC_PROBE_URL)), daemon=True)
    t.start()
    t.join(deadline)
    return bool(box.get("r")) and box["r"][0] not in (403, 599)
BATCH = 100
HEADER_WORKERS = 6
FOPT_BAND = (0.85, 1.01)
W5_ABOVE = 1.12
EDGAR_DIR = "edgar"


class Refused(periods.LockedPeriod):
    pass


def check_window(a, b):
    """Refuse a date or a multi-day window [a, b] that touches L1 or L2 (before any request)."""
    hit = periods.overlaps(a, b)
    if hit:
        raise Refused(f"REFUSED: {a}..{b} touches locked period(s) {', '.join(hit)}")


def _utc(d, hhmm="00:00"):
    return pd.Timestamp(f"{d} {hhmm}", tz=ET).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def edgar_root(root):
    return Path(root).parent / EDGAR_DIR


class Progress:
    """Counts, rate and time left for one stage; prints at most every `every` seconds (and at the end)."""

    def __init__(self, stage, total, log, every=30.0, root=None, clock=time.time):
        self.stage, self.total, self.log, self.every, self.root, self.clock = stage, max(int(total), 0), log, every, root, clock
        self.t0 = self.last = clock()
        self.done = 0
        self.log(f"[{stage}] {self.total} to do")

    def step(self, n=1, note=""):
        self.done += n
        now = self.clock()
        if now - self.last >= self.every or self.done >= self.total:
            self.last = now
            el = now - self.t0
            rate = self.done / el if el > 0 else 0.0
            left = (self.total - self.done) / rate if rate > 0 else None
            disk = f", {disk_mb(self.root)} MB on disk" if self.root else ""
            self.log(f"[{self.stage}] {self.done}/{self.total} ({100.0 * self.done / max(self.total, 1):.1f}%), "
                     f"{el / 60:.1f} min so far, about {left / 60:.0f} min left{disk}" if left is not None else
                     f"[{self.stage}] {self.done}/{self.total}{disk} {note}")


def disk_mb(root):
    if root is None:
        return 0.0
    tot = 0
    base = Path(root)
    for sub in ("universe", "daily9", "options_fopt", "options_w5", "g1_bars", "options_g2"):
        p = base / sub
        if p.exists():
            tot += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    e = edgar_root(base)
    if e.exists():
        tot += sum(f.stat().st_size for f in e.rglob("*") if f.is_file())
    return round(tot / 1e6, 1)


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj))
    tmp.replace(path)


def _read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------- the asset list (trading host, read-only, one path)
def _trading_http(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


trading_http = _trading_http                     # tests replace this


def get_assets():
    if not ASSETS_URL.startswith(TRADING_HOST + "/v2/assets?"):
        raise RuntimeError("REFUSED: only the asset list is ever read from the trading host")
    key, sec = os.environ.get("ALPACA_KEY"), os.environ.get("ALPACA_SECRET")
    if not key or not sec:
        raise RuntimeError("ALPACA_KEY / ALPACA_SECRET are not set (the desk's paper key)")
    PA._throttle()
    return trading_http(ASSETS_URL, {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec, "Accept": "application/json"})


def pull_assets(root, log):
    u = Path(root) / "universe"
    if (u / ".done").exists():
        log("[assets] done before (data/alpaca/universe/ustk.json)")
        return _read_json(u / "ustk.json")
    assets = get_assets()
    _write_json(u / "assets.json", assets)
    res = U.build_ustk(assets)
    _write_json(u / "ustk.json", res)
    (u / ".done").write_text(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "symbols": len(res["symbols"])}))
    log(f"[assets] {len(assets)} active US equities listed; U-STK: {len(res['symbols'])} common stocks with listed options "
        f"({U.SB}); {len(res['excluded'])} excluded (reasons saved in ustk.json)")
    return res


# ---------------------------------------------------------------- daily bars
FETCH_ERRORS = (PA.PagingError, urllib.error.URLError, TimeoutError, ConnectionError, OSError)
SINGLE_BACKOFF = (5, 15)                 # the single-symbol fallback's network retries (the batch already used the long ones)
SYMBOL_ERRORS = (PA.PagingError, urllib.error.HTTPError)   # errors that belong to one symbol's request, not to the network


def _multi_bars(path, symbols, params, kind, net_backoff=None):
    """Multi-symbol stock bars, at most BATCH symbols a request (each request paginated by pull_alpaca.get)."""
    rows = []
    symbols = list(symbols)
    for i in range(0, len(symbols), BATCH):
        for page in PA.get(path, dict(params, symbols=",".join(symbols[i:i + BATCH])), net_backoff=net_backoff):
            for s, lst in (page.get(kind) or {}).items():
                rows += [dict(x, symbol=s) for x in lst or []]
    return PA._frame(rows)


def pull_daily(symbols, root, log, feed="sip", batch=BATCH):
    """Raw and split-adjusted daily bars for `symbols` over 2015-11-01..2026-06-30 minus L1/L2; per-symbol .done markers."""
    segs = U.locked_free_segments(U.DAILY_FROM, U.DAILY_TO)
    for a, b in segs:
        check_window(a, b)
    out = {"pulled": 0, "skipped": 0, "rows": 0, "failed": []}

    def fetch(part, adj, net_backoff=None):
        frames = []
        for a, b in segs:
            frames.append(_multi_bars("/v2/stocks/bars", part, {"timeframe": "1Day", "start": _utc(a), "end": _utc(b + timedelta(days=1)),
                                                               "limit": 10000, "adjustment": adj, "feed": feed, "sort": "asc"}, "bars",
                                      net_backoff=net_backoff))
        return pd.concat([f for f in frames if len(f)], ignore_index=True) if any(len(f) for f in frames) else PA._frame([])

    for adj in ("raw", "split"):
        folder = Path(root) / "daily9" / adj
        failed_before = [s for s in symbols if (folder / f"{s}.failed").exists() and not (folder / f"{s}.done").exists()]
        if failed_before:
            log(f"[daily {adj}] {len(failed_before)} symbol(s) failed on an earlier try and are left out: "
                f"{', '.join(failed_before[:20])}{' ...' if len(failed_before) > 20 else ''} (delete their .failed markers to retry)")
            out["failed"] += [f"{adj}:{s}" for s in failed_before]
        todo = [s for s in symbols if not (folder / f"{s}.done").exists() and not (folder / f"{s}.failed").exists()]
        out["skipped"] += len(symbols) - len(todo)
        pr = Progress(f"daily {adj}", len(todo), log, root=root)
        for i in range(0, len(todo), batch):
            part = todo[i:i + batch]
            bad = {}
            try:
                df = fetch(part, adj)
            except FETCH_ERRORS as e:
                # one stuck or refused request must not stop the whole stage: fetch the batch one symbol at a time with a short
                # retry budget, keep what comes back, and mark the symbols that still fail (left out, listed in the log)
                log(f"[daily {adj}] a batch of {len(part)} failed ({type(e).__name__}: {str(e)[:160]}); fetching them one by one")
                frames, net_only = [], True
                for s in part:
                    try:
                        frames.append(fetch([s], adj, net_backoff=SINGLE_BACKOFF))
                    except FETCH_ERRORS as e1:
                        bad[s] = f"{type(e1).__name__}: {str(e1)[:200]}"
                        net_only = net_only and not isinstance(e1, SYMBOL_ERRORS)
                if len(bad) == len(part) and net_only:
                    # every symbol failed on network errors alone: the network is down, not a bad symbol. Stop (the run
                    # retries later and resumes) instead of marking good symbols as failed.
                    raise ConnectionError(f"daily {adj}: every symbol of the batch failed on network errors ({next(iter(bad.values()))})")
                df = pd.concat([f for f in frames if len(f)], ignore_index=True) if any(len(f) for f in frames) else PA._frame([])
            for s, why in bad.items():
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"{s}.failed").write_text(json.dumps({"reason": why}))
                out["failed"].append(f"{adj}:{s}")
            if bad:
                log(f"[daily {adj}] left out after single-symbol tries: {', '.join(sorted(bad))}")
            for s in part:
                if s in bad:
                    continue
                g = df[df["symbol"] == s].drop(columns=["symbol"]) if len(df) else PA._frame([])
                if len(g):
                    g = g.drop_duplicates("ts").sort_values("ts")
                    keep = [not periods.overlaps(t.date(), t.date()) for t in g["ts"]]
                    g = g[keep]
                PA._write_gz(folder / f"{s}.csv.gz", g.reset_index(drop=True))
                (folder / f"{s}.done").write_text(json.dumps({"rows": int(len(g)), "segments": [f"{a}..{b}" for a, b in segs]}))
                out["rows"] += int(len(g))
            out["pulled"] += len(part)
            pr.step(len(part))
    return out


# ---------------------------------------------------------------- F-opt
def fopt_targets(root, log):
    """[(symbol, entry day, exit day, raw open on the entry day, variant)] for the F1 / F2 U-ETF trades inside DEV."""
    p = U.Panel.load(U.U_ETF, root)
    r, _ = M.rsi2(p, U.U_ETF, "U-ETF")
    t, _ = M.tom(p, U.TOM_ETF, "U-ETF")
    out = []
    for tr in M.fopt_targets(r + t):
        e = date.fromisoformat(tr["entry_day"])
        j, k = p.col[tr["symbol"]], p.idx(e)
        out.append((tr["symbol"], e, date.fromisoformat(tr["exit_day"]), float(p.raw_o[k, j]), tr["variant"]))
    log(f"[fopt] {len(out)} DEV share trades to carry by a call (rsi2 U-ETF + tom SPY/QQQ/IWM/DIA)")
    return out


def fopt_symbols(under, day, S):
    """Calls, every listed-looking strike 85%-101% of the open ($0.5 grid under $100, else $1), every NYSE session 30-60
    calendar days out as a possible expiry (contracts that never existed return nothing)."""
    lo, hi = FOPT_BAND
    step = 0.5 if S < 100 else 1.0
    k0, k1 = int(S * lo / step), int(S * hi / step) + 1
    exps = U.all_sessions_cal(day + timedelta(days=30), day + timedelta(days=60))
    return [C.occ(under, e, "C", k * step) for e in exps for k in range(k0, k1 + 1)]


def _opt_bars(symbols, day, t0, t1):
    rows = []
    for i in range(0, len(symbols), BATCH):
        for page in PA.get("/v1beta1/options/bars", {"timeframe": "1Min", "symbols": ",".join(symbols[i:i + BATCH]),
                                                    "start": _utc(day, t0), "end": _utc(day, t1), "limit": 10000, "sort": "asc"}):
            for s, lst in (page.get("bars") or {}).items():
                rows += [dict(x, symbol=s) for x in lst or []]
    return PA._frame(rows)


def pull_fopt(root, log, targets=None):
    targets = fopt_targets(root, log) if targets is None else targets
    out = {"trades": len(targets), "entry_days": 0, "exit_days": 0, "refused": 0, "no_pick": 0, "skipped": 0}
    pr = Progress("fopt", len(targets), log, root=root)
    for sym, e, x, S, _v in targets:
        try:
            check_window(e, x)
        except Refused:
            out["refused"] += 1
            pr.step()
            continue
        folder = Path(root) / "options_fopt" / sym
        ef, xf = folder / e.isoformat() / "entry.csv.gz", folder / x.isoformat() / f"exit_{e.isoformat()}.csv.gz"
        if (ef.parent / ".done_entry").exists() and (xf.parent / f".done_exit_{e.isoformat()}").exists():
            out["skipped"] += 1
            pr.step()
            continue
        if not (ef.parent / ".done_entry").exists():
            df = _opt_bars(fopt_symbols(sym, e, S), e, "09:30", "09:35")
            PA._write_gz(ef, df)
            (ef.parent / ".done_entry").write_text(json.dumps({"bars": int(len(df))}))
            out["entry_days"] += 1
        ent = PA.read_gz(ef) if ef.exists() else None
        if ent is not None and len(ent):
            ent["ts"] = ent["ts"].map(lambda t: t.isoformat())
        info, why = contracts.pick_daily(M.candidates(ent), S, e, M.FOPT_RULE, "C")
        if info is None:
            out["no_pick"] += 1
            (xf.parent).mkdir(parents=True, exist_ok=True)
            (xf.parent / f".done_exit_{e.isoformat()}").write_text(json.dumps({"no_pick": why}))
            pr.step()
            continue
        df = _opt_bars([info["symbol"]], x, "09:30", "16:00")
        PA._write_gz(xf, df)
        (xf.parent / f".done_exit_{e.isoformat()}").write_text(json.dumps({"contract": info["symbol"], "bars": int(len(df))}))
        out["exit_days"] += 1
        pr.step()
    return out


# ---------------------------------------------------------------- Part I weekly expiry
def w5_symbols(under, exp, day_bars):
    r = day_bars[(day_bars["ts"].dt.strftime("%H:%M") >= "09:30") & (day_bars["ts"].dt.strftime("%H:%M") < "16:00")]
    if not len(r):
        return []
    o, hi, lo = float(r["o"].iloc[0]), float(r["h"].max()), float(r["l"].min())
    k0, k1 = int(min(o, lo)), int(max(o, hi) * W5_ABOVE) + 1
    return [C.occ(under, exp, "C", k) for k in range(k0, k1 + 1)]


def pull_weekly(root, log, symbols=W.SYMBOLS, a=periods.DEV[0], b=periods.DEV[1]):
    """Only on FIN-H signal days (the 11:00 bar with relative volume >= 1.06, computed from the cached stock bars exactly as
    sprint/weekly.finh_signal): Part I trades no other day."""
    check_window(a, b)
    out = {"days": 0, "skipped": 0, "no_stock_bars": 0, "no_expiry_found": 0, "bars": 0, "no_finh_signal": 0}
    for sym in symbols:
        stock = D.read_stock(sym, periods.DEV[0], b, root)
        by_day = {d: g for d, g in stock.groupby(stock["ts"].dt.date)} if stock is not None else {}
        ser = D.Series(sym, stock)
        days = [d for d in U.sessions(a, b)]
        pr = Progress(f"weekly {sym}", len(days), log, root=root)
        for d in days:
            folder = Path(root) / "options_w5" / sym / d.isoformat()
            if (folder / ".done").exists():
                out["skipped"] += 1
                pr.step()
                continue
            g = by_day.get(d)
            if g is None or not len(g) or d not in ser.rth:
                out["no_stock_bars"] += 1
                pr.step()
                continue
            ok, _why = W.finh_signal(D.DayContext(ser, d, {}, None))
            if not ok:
                out["no_finh_signal"] += 1
                folder.mkdir(parents=True, exist_ok=True)
                (folder / ".done").write_text(json.dumps({"expiry": None, "no_finh_signal": _why}))
                pr.step()
                continue
            used, df = None, None
            for exp in W.expiry_window(d):
                df = _opt_bars(w5_symbols(sym, exp, g), d, "09:30", "16:00")
                if len(df):
                    used = exp
                    break
            folder.mkdir(parents=True, exist_ok=True)
            if used is None:
                out["no_expiry_found"] += 1
                (folder / ".done").write_text(json.dumps({"expiry": None}))
            else:
                PA._write_gz(folder / "bars.csv.gz", df)
                (folder / ".done").write_text(json.dumps({"expiry": used.isoformat(), "bars": int(len(df))}))
                out["days"] += 1
                out["bars"] += int(len(df))
            pr.step()
    return out


# ---------------------------------------------------------------- EDGAR
def index_days():
    """Weekdays 2015-12-31..2026-06-30 outside L1/L2 (EDGAR publishes no weekend index; a holiday answers 404)."""
    out, d = [], E.INDEX_FROM
    while d <= E.INDEX_TO:
        if d.weekday() < 5 and not periods.overlaps(d, d):
            out.append(d)
        d += timedelta(days=1)
    return out


def pull_edgar_index(root, log, http=None, throttle=None):
    er = edgar_root(root)
    http, throttle = http or E.default_http, throttle or E.Throttle()
    tk = er / "company_tickers.json"
    if not tk.exists():
        txt = E.fetch(E.tickers_url(), http, throttle)
        if txt is None:
            raise RuntimeError("SEC company_tickers.json not found")
        _write_json(tk, json.loads(txt))
    days = index_days()
    todo = [d for d in days if not (er / "index" / f"{d}.done").exists()]
    out = {"days": len(days), "fetched": 0, "skipped": len(days) - len(todo), "rows_8k": 0}
    pr = Progress("edgar index", len(todo), log, root=root)
    for d in todo:
        check_window(d, d)
        txt = E.fetch(E.index_url(d), http, throttle)
        rows = E.parse_form_index(txt) if txt else []
        _write_json(er / "index" / f"{d}.json", [{"form": r["form"], "cik": r["cik"], "filed": r["filed"].isoformat(), "acc": r["acc"]}
                                                 for r in rows])
        (er / "index" / f"{d}.done").write_text(json.dumps({"rows": len(rows), "found": txt is not None}))
        out["fetched"] += 1
        out["rows_8k"] += len(rows)
        pr.step()
    return out


def read_index(root):
    er = edgar_root(root)
    rows = []
    for f in sorted((er / "index").glob("*.json")):
        for r in _read_json(f, []) or []:
            r["filed"] = date.fromisoformat(r["filed"])
            rows.append(r)
    return rows


def read_tickers(root):
    j = _read_json(edgar_root(root) / "company_tickers.json")
    return E.tickers_map(j) if j else {}


def header_targets(rows, tmap, panel, cal):
    """8-K rows whose CIK maps to a U-STK ticker passing the filter on the first session on/after the filing date or the
    next session (the only sessions such a filing can be a G1 event on, or a G2 entry needs it on its own row)."""
    elig = panel.eligible()
    out = []
    for r in rows:
        if r.get("form") != "8-K" or not r.get("acc"):
            continue
        t0 = cal.first_on_or_after(r["filed"])
        if t0 is None:
            continue
        cands = [t0, cal.fwd(t0, 1)]
        ok = False
        for sym in tmap.get(int(r["cik"]), []):
            j = panel.col.get(sym)
            if j is None:
                continue
            for t in cands:
                k = panel.idx(t) if t is not None else None
                if k is not None and elig[k, j]:
                    ok = True
                    break
            if ok:
                break
        if ok:
            out.append(r)
    return out


def ustk_panel(root, log):
    us = U.read_ustk(root)
    if not us:
        raise RuntimeError("no U-STK list (run the assets stage first)")
    p = U.Panel.load(us["symbols"], root, log=log, prefilter=True)
    log(f"  U-STK panel: {len(p.symbols)} symbols that can pass the filter ({len(p.skipped)} never can, {len(p.missing)} without daily bars)")
    return p


def pull_edgar_headers(root, log, http=None, throttle=None, panel=None, workers=HEADER_WORKERS, chunk=2000):
    """Each target filing's index headers, fetched by `workers` threads that share ONE throttle (so the rate stays at most
    10 a second; the workers only hide the network latency). Records are appended by this thread as they complete."""
    from concurrent.futures import ThreadPoolExecutor
    er = edgar_root(root)
    http, throttle = http or E.default_http, throttle or E.Throttle()
    panel = panel or ustk_panel(root, log)
    cal = E.Calendar()
    targets = header_targets(read_index(root), read_tickers(root), panel, cal)
    hf = er / "headers.jsonl"
    have = {r.get("acc") for r in E.read_jsonl(hf)}
    todo = [r for r in targets if r["acc"] not in have]
    for r in todo:
        check_window(r["filed"], r["filed"])
    out = {"targets": len(targets), "skipped": len(targets) - len(todo), "fetched": 0, "missing": 0}
    pr = Progress("edgar headers", len(todo), log, root=root)
    hf.parent.mkdir(parents=True, exist_ok=True)

    def one(r):
        txt = E.fetch(E.header_url(r["cik"], r["acc"]), http, throttle)
        return E.header_record(r["cik"], r, E.parse_header(txt) if txt else None, None if txt else "404")

    with open(hf, "a") as f, ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
        for i in range(0, len(todo), chunk):
            for rec in ex.map(one, todo[i:i + chunk]):
                f.write(json.dumps(rec) + "\n")
                out["fetched"] += 1
                out["missing"] += 1 if rec.get("error") else 0
                pr.step()
            f.flush()
    return out


def read_headers(root):
    return E.read_jsonl(edgar_root(root) / "headers.jsonl")


# ---------------------------------------------------------------- G1 and G2 bars
def merge_day_file(path, marker, need, fetch):
    """Fetch the symbols in `need` not yet in the day file, merge, write; the marker lists every symbol asked for."""
    m = _read_json(marker, {}) or {}
    asked = set(m.get("asked", []))
    miss = sorted(set(need) - asked)
    if not miss:
        return 0
    new = fetch(miss)
    old = PA.read_gz(path) if path.exists() else None
    df = pd.concat([x for x in (old, new) if x is not None and len(x)], ignore_index=True) if (
        (old is not None and len(old)) or len(new)) else new
    if len(df):
        df = df.drop_duplicates(["symbol", "ts"]).sort_values(["symbol", "ts"])
    PA._write_gz(path, df.reset_index(drop=True))
    _write_json(marker, {"asked": sorted(asked | set(miss)), "rows": int(len(df))})
    return len(miss)


def g1_plan(root, log, panel=None):
    panel = panel or ustk_panel(root, log)
    ev = C.g1_events(read_headers(root), read_tickers(root), panel, E.Calendar())
    by = defaultdict(set)
    for e in ev:
        by[e["t"]].add(e["symbol"])
    log(f"[g1] {len(ev)} G1 events (8-Ks accepted 16:00..09:15 for U-STK names passing the filter) on {len(by)} days")
    return by


def pull_g1(root, log, panel=None, feed="sip"):
    by = g1_plan(root, log, panel)
    out = {"days": len(by), "asked": 0, "refused": 0}
    pr = Progress("g1 bars", len(by), log, root=root)
    for d in sorted(by):
        try:
            check_window(d, d)
        except Refused:
            out["refused"] += 1
            pr.step()
            continue
        fol = Path(root) / "g1_bars"
        f = lambda syms, d=d: _multi_bars("/v2/stocks/bars", syms, {"timeframe": "1Min", "start": _utc(d, "09:30"), "end": _utc(d, "16:00"),
                                                                   "limit": 10000, "adjustment": "split", "feed": feed, "sort": "asc"}, "bars")
        out["asked"] += merge_day_file(fol / f"{d}.csv.gz", fol / f"{d}.json", by[d], f)
        pr.step()
    return out


def g2_plan(root, log, panel=None):
    panel = panel or ustk_panel(root, log)
    recs, tmap = read_headers(root), read_tickers(root)
    cal = E.Calendar()
    ev = C.g2_events(recs, tmap, panel, cal)
    pool = C.random_pool(ev, panel, C.earnings_days(recs, tmap))
    items = [dict(e, kind="event", n=k) for k, e in enumerate(ev)] + [dict(q, kind="pool") for q in pool]
    log(f"[g2] {len(ev)} Item 2.02 events in DEV and {len(pool)} random non-earnings pool dates ({C.POOL_PER_EVENT} per event)")
    return items, panel


def pull_g2(root, log, panel=None):
    items, panel = g2_plan(root, log, panel)
    fol = Path(root) / "options_g2"
    out = {"items": len(items), "refused": 0, "entry_days": 0, "exit_days": 0, "no_choice": 0}
    ok_items = []
    for it in items:
        try:
            check_window(it["entry"], it["exit"])
            ok_items.append(it)
        except Refused:
            out["refused"] += 1
    by_entry = defaultdict(list)
    for it in ok_items:
        j, k = panel.col.get(it["symbol"]), panel.idx(it["entry"])
        close = float(panel.raw_c[k, j]) if j is not None and k is not None else float("nan")
        if close == close:
            by_entry[it["entry"]].append((it, close))
    pr = Progress("g2 entry days", len(by_entry), log, root=root)
    for d in sorted(by_entry):
        path, mk = fol / d.isoformat() / "entry.csv.gz", fol / d.isoformat() / "entry.json"
        first = {s for it, c in by_entry[d] for s in C.straddle_candidates(it["symbol"], d, c, "first")}
        merge_day_file(path, mk, first, lambda syms, d=d: _opt_bars(syms, d, "15:30", "16:00"))
        ent = PA.read_gz(path) if path.exists() else None
        printed = set(ent["symbol"]) if ent is not None and len(ent) else set()
        later = set()
        for it, c in by_entry[d]:
            if not printed & set(C.straddle_candidates(it["symbol"], d, c, "first")):
                later |= set(C.straddle_candidates(it["symbol"], d, c, "next"))
        if later:
            merge_day_file(path, mk, first | later, lambda syms, d=d: _opt_bars(syms, d, "15:30", "16:00"))
        out["entry_days"] += 1
        pr.step()
    by_exit = defaultdict(set)
    for d, lst in by_entry.items():
        path = fol / d.isoformat() / "entry.csv.gz"
        pm = C.price_map(pd.read_csv(path, compression="gzip")) if path.exists() else {}
        for it, c in lst:
            ch, why = C.choose_straddle(None, it["symbol"], d, c, pmap=pm)
            if ch is None:
                out["no_choice"] += 1
                continue
            by_exit[it["exit"]] |= {ch["call"], ch["put"]}
    pr = Progress("g2 exit days", len(by_exit), log, root=root)
    for d in sorted(by_exit):
        merge_day_file(fol / d.isoformat() / "exit.csv.gz", fol / d.isoformat() / "exit.json", by_exit[d],
                       lambda syms, d=d: _opt_bars(syms, d, "15:30", "16:00"))
        out["exit_days"] += 1
        pr.step()
    return out


# ---------------------------------------------------------------- status (no network)
def status(root, log):
    root = Path(root)
    er = edgar_root(root)
    us = U.read_ustk(root)
    n_us = len(us["symbols"]) if us else None
    log(f"assets: {'done' if (root / 'universe' / '.done').exists() else 'not yet'}"
        + (f" (U-STK {n_us} symbols, {U.SB})" if n_us else ""))
    for adj in ("raw", "split"):
        n = len(list((root / "daily9" / adj).glob("*.done"))) if (root / "daily9" / adj).exists() else 0
        log(f"daily {adj}: {n} symbols done" + (f" of {n_us + len(U.U_ETF)}" if n_us else ""))
    n_idx = len(list((er / "index").glob("*.done"))) if (er / "index").exists() else 0
    log(f"edgar index: {n_idx} of {len(index_days())} days done")
    log(f"edgar headers: {len(read_headers(root))} filings read")
    for sub in ("options_fopt", "options_w5", "g1_bars", "options_g2"):
        p = root / sub
        n = sum(1 for _ in p.rglob("*.csv.gz")) if p.exists() else 0
        log(f"{sub}: {n} files")
    log(f"disk used by round 9: {disk_mb(root)} MB")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read-only data pull for sprint round 9 (Alpaca market data, one asset list, SEC EDGAR)")
    ap.add_argument("--only", default=None, help="comma-separated stages: " + ",".join(STAGES))
    ap.add_argument("--root", default=None, help="cache root (default data/alpaca)")
    ap.add_argument("--feed", default="sip", choices=["sip", "iex"])
    ap.add_argument("--status", action="store_true", help="show what is done and the disk used (no network)")
    ap.add_argument("--sec-env-file", default=E.DESK_ENV, help="where SEC_USER_AGENT is read when it is not in the environment")
    x = ap.parse_args(argv)
    if x.root:
        PA.ROOT = Path(x.root)
    root = PA.ROOT
    log = lambda s: print(s, flush=True)
    if x.status:
        status(root, log)
        return 0
    stages = [s.strip() for s in (x.only or ",".join(STAGES)).split(",") if s.strip()]
    bad = [s for s in stages if s not in STAGES]
    if bad:
        ap.error(f"unknown stage(s) {bad}")
    log(f"sprint_pull9: stages {', '.join(stages)}; cache {root}; L1 {periods.LOCKED['L1'][0]}..{periods.LOCKED['L1'][1]} and "
        f"L2 {periods.LOCKED['L2'][0]}..{periods.LOCKED['L2'][1]} are never requested")
    t0 = time.time()
    panel = None
    rc = 0
    sec_ok, ua_src = None, None
    for st in stages:
        ts = time.time()
        if st in SEC_STAGES:
            if ua_src is None:
                ua_src = E.load_user_agent(x.sec_env_file)
            if sec_ok is None and ua_src is not None:
                sec_ok = sec_reachable()
                log(f"[sec] www.sec.gov {'reachable' if sec_ok else 'NOT reachable from this computer (no answer within 30 s, or refused)'}")
            if sec_ok is False:
                log(f"WARNING: [{st}] skipped: SEC EDGAR can't be reached from this computer, so the 8-K stages (edgar_index, "
                    "edgar_headers, g1, g2) are left out of this run. Round 9 Part G and round 10's earnings rules will say so. "
                    "Re-run them later from a computer that reaches www.sec.gov.")
                continue
        try:
            if st == "assets":
                pull_assets(root, log)
            elif st == "daily":
                us = U.read_ustk(root)
                if not us:
                    raise RuntimeError("no U-STK list: run the assets stage first")
                syms = list(U.U_ETF) + [s for s in us["symbols"] if s not in U.U_ETF]
                n_req = -(-len(syms) // BATCH) * 2 * 27              # 100 symbols x ~2,550 sessions / 10,000 bars a page
                log(f"[daily] {len(syms)} symbols (U-ETF 20 + U-STK {len(us['symbols'])}) x raw and split-adjusted; at most about "
                    f"{n_req} requests (about {n_req / 180:.0f} min at 180 a minute)")
                log(f"[daily] {pull_daily(syms, root, log, x.feed)}")
            elif st == "fopt":
                log(f"[fopt] {pull_fopt(root, log)}")
            elif st == "weekly":
                log(f"[weekly] {pull_weekly(root, log)}")
            elif st in ("edgar_index", "edgar_headers"):
                src = ua_src if ua_src is not None else E.load_user_agent(x.sec_env_file)
                if src is None:
                    log(f"[{st}] SEC_USER_AGENT is not set (not in the environment, not in {x.sec_env_file}): SEC asks every "
                        "automated client for a contact; stage skipped. Tell Nick.")
                    rc = 3
                    continue
                log(f"[{st}] SEC user agent: set (from {'the environment' if src == 'env' else 'the desk env file'}; not shown)")
                if st == "edgar_index":
                    log(f"[edgar index] {pull_edgar_index(root, log)}")
                else:
                    panel = panel or ustk_panel(root, log)
                    log(f"[edgar headers] {pull_edgar_headers(root, log, panel=panel)}")
            elif st == "g1":
                panel = panel or ustk_panel(root, log)
                log(f"[g1] {pull_g1(root, log, panel, x.feed)}")
            elif st == "g2":
                panel = panel or ustk_panel(root, log)
                log(f"[g2] {pull_g2(root, log, panel)}")
        except periods.LockedPeriod as e:
            log(f"[{st}] {e}")
            return 2
        except E.RateLimited as e:
            log(f"[{st}] SEC kept refusing ({e}); re-run the same command later to resume")
            return 4
        log(f"[{st}] finished in {(time.time() - ts) / 60:.1f} min; {disk_mb(root)} MB on disk for round 9")
    log(f"sprint_pull9 done in {(time.time() - t0) / 60:.1f} min")
    return rc


if __name__ == "__main__":
    sys.exit(main())
