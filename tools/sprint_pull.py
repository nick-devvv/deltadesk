#!/usr/bin/env python3
"""tools/sprint_pull.py - READ-ONLY Alpaca market-data puller for the strategy + exits sprint (runs on Chart's computer,
in a separate checkout such as ~/sprint; Claude's workspace and Nick's Mac can't reach Alpaca). Built on
tools/pull_alpaca.py: the same host guard (only https://data.alpaca.markets is ever called: no orders, no account,
no positions), the same throttle/retry, the same cache layout.

  python3 tools/sprint_pull.py --symbols SPY,QQQ,IWM --from 2024-08-01 --to 2026-06-30
  python3 tools/sprint_pull.py --symbols SPY,QQQ,IWM --from 2024-08-01 --to 2026-06-30 --trades     # + option trades
  python3 tools/sprint_pull.py --symbols SPY,QQQ,IWM --from 2024-08-01 --to 2026-06-30 --gaps-only
  (--stock-only VIXY is the default: VIXY 1-minute stock bars, no options, as the labeled proxy for VIX in the
   "VIX falling" filter of oa_crosscheck_v1; pass --stock-only "" to skip it)
  (--daily VIXY is the default: VIXY DAILY bars, split-adjusted, from --daily-from (2023-01-01) to --to, for the
   252-session "IV-rank proxy: VIXY percentile" of oa_crosscheck_v2. The locked periods L1/L2 are cut out of that
   range and never requested; pass --daily "" to skip it)

What it pulls for each symbol and date range:
  1. stock 1-minute bars 04:00-20:00 ET (raw, feed sip), month files, the range clipped to exactly [from, to] in ET
     (so nothing outside the requested dates is fetched);
  2. for each session: the 0DTE contracts on every $1 strike within --band (default 3%) of the open, widened to the
     day's high/low (pull_alpaca.symbols_for_day), calls and puts, their 1-minute bars; with --trades, also the
     individual trades of the contracts within --trades-band (default 1.5%) of the open (used for exact stop fills);
  3. a gap report: weekdays without bars (after NYSE holidays), short sessions (early closes listed apart), sessions
     without 0DTE option bars, and contracts per session; saved to data/sprint/gaps_<SYM>_<from>_<to>.json.
Resumable: a finished month/day writes a .done marker (.done_trades for trades) and is skipped next time; partial
months and today are never marked done. Locked periods (L1 2026-07-01..2026-10-30, L2 2024-02-01..2024-07-31) are
refused unless --locked <name> --frozen <spec sha256> --spec <file> (the same rule as the runner).
Keys: ALPACA_KEY / ALPACA_SECRET (the desk's paper key: market data only).
"""
import argparse
import json
import statistics
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
import pull_alpaca as PA  # noqa: E402
from sprint import data as D  # noqa: E402
from sprint import periods  # noqa: E402
from sprint import spread as SP  # noqa: E402

ET = "America/New_York"


def _utc(d, hhmm="00:00"):
    return pd.Timestamp(f"{d} {hhmm}", tz=ET).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def sessions(a, b):
    hol = periods.holidays()
    out, d = [], a
    while d <= b:
        if d.weekday() < 5 and d.isoformat() not in hol:
            out.append(d)
        d += timedelta(days=1)
    return out


def pull_stock(sym, a, b, feed="sip", today=None, log=print):
    """Month files, each request clipped to [a, b] in ET. Returns counts."""
    today = today or date.today()
    out = {"pulled": 0, "skipped": 0, "rows": 0}
    for m0, m1 in PA._months(a, b):
        s0, s1 = max(m0, a), min(m1, b)
        month_end = date(m0.year + (m0.month == 12), m0.month % 12 + 1, 1) - timedelta(days=1)
        f = PA.ROOT / "stocks" / sym / f"{m0:%Y-%m}.csv.gz"
        done = f.with_suffix(".done")
        if done.exists():
            out["skipped"] += 1
            continue
        bars = []
        for page in PA.get(f"/v2/stocks/{sym}/bars", {"timeframe": "1Min", "start": _utc(s0), "end": _utc(s1 + timedelta(days=1)),
                                                      "limit": 10000, "adjustment": "raw", "feed": feed, "sort": "asc"}):
            bars += page.get("bars") or []
        df = PA._frame(bars)
        if f.exists() and len(df):                       # a partial month pulled earlier: merge, newest wins
            old = PA.read_gz(f)
            df = pd.concat([old, df], ignore_index=True).drop_duplicates("ts", keep="last").sort_values("ts")
        PA._write_gz(f, df)
        out["pulled"] += 1
        out["rows"] += len(df)
        if s0 == m0 and s1 == month_end and month_end < today:
            done.write_text(json.dumps({"rows": len(df), "at": datetime.now().isoformat(timespec="seconds"), "feed": feed}))
        log(f"  {sym} {m0:%Y-%m}: {len(df)} bars")
    return out


def locked_free_segments(a, b):
    """[a, b] with every locked period cut out: [(start, end), ...]."""
    segs = [(a, b)]
    for x, y in periods.LOCKED.values():
        nxt = []
        for s, e in segs:
            if e < x or s > y:
                nxt.append((s, e))
                continue
            if s < x:
                nxt.append((s, x - timedelta(days=1)))
            if e > y:
                nxt.append((y + timedelta(days=1), e))
        segs = nxt
    return segs


def pull_daily(sym, a, b, feed="sip", log=print):
    """Split-adjusted daily bars for [a, b] minus the locked periods, one file data/alpaca/daily/<SYM>.csv.gz."""
    rows = []
    segs = locked_free_segments(a, b)
    for s, e in segs:
        for page in PA.get(f"/v2/stocks/{sym}/bars", {"timeframe": "1Day", "start": _utc(s), "end": _utc(e + timedelta(days=1)),
                                                      "limit": 10000, "adjustment": "split", "feed": feed, "sort": "asc"}):
            rows += page.get("bars") or []
    df = PA._frame(rows)
    if len(df):
        df = df.drop_duplicates("ts").sort_values("ts")
    PA._write_gz(PA.ROOT / "daily" / f"{sym}.csv.gz", df)
    return {"rows": len(df), "segments": [f"{s}..{e}" for s, e in segs]}


def _fetch(path, syms, d, extra, kind):
    rows = []
    for i in range(0, len(syms), 100):
        for page in PA.get(path, dict(extra, symbols=",".join(syms[i:i + 100]), start=_utc(d, "09:00"), end=_utc(d, "16:30"),
                                      limit=10000, sort="asc")):
            for s, lst in (page.get(kind) or {}).items():
                rows += [dict(x, symbol=s) for x in lst or []]
    return PA._frame(rows)


def pull_options(under, a, b, band=0.03, trades=False, trades_band=0.015, today=None, log=print):
    """0DTE bars (and trades near the money) per session. Needs the stock bars in the cache first."""
    today = today or date.today()
    out = {"days": 0, "skipped": 0, "no_stock_bars": [], "bars": 0, "trades": 0, "contracts": 0}
    stock = D.read_stock(under, a, b, PA.ROOT)
    by_day = {d: g for d, g in stock.groupby(stock["ts"].dt.date)} if stock is not None else {}
    for n, d in enumerate(sessions(a, b)):
        g = by_day.get(d)
        if g is None or not len(g):
            out["no_stock_bars"].append(d.isoformat())
            continue
        folder = PA.ROOT / "options" / under / d.isoformat()
        syms = PA.symbols_for_day(under, d, g, band)
        did = False
        if not (folder / ".done").exists():
            df = _fetch("/v1beta1/options/bars", syms, d, {"timeframe": "1Min"}, "bars")
            PA._write_gz(folder / "bars.csv.gz", df)
            out["bars"] += len(df)
            out["contracts"] += int(df["symbol"].nunique()) if len(df) else 0
            if d < today:
                (folder / ".done").write_text(json.dumps({"bars": len(df), "symbols": len(syms), "at": datetime.now().isoformat(timespec="seconds")}))
            did = True
        if trades and not (folder / ".done_trades").exists():
            r = g[(g["ts"].dt.strftime("%H:%M") >= "09:30") & (g["ts"].dt.strftime("%H:%M") < "16:00")]
            o = float(r["o"].iloc[0]) if len(r) else None
            near = [s for s in syms if o and abs(int(s[-8:]) / 1000 - o) <= trades_band * o]
            tf = _fetch("/v1beta1/options/trades", near, d, {}, "trades")
            PA._write_gz(folder / "trades.csv.gz", tf)
            out["trades"] += len(tf)
            if d < today:
                (folder / ".done_trades").write_text(json.dumps({"trades": len(tf), "symbols": len(near)}))
            did = True
        out["days" if did else "skipped"] += 1
        if did and n % 20 == 0:
            log(f"  {under} options {d}: {out['days']} sessions pulled so far")
    return out


def gap_report(sym, a, b, out_dir=None, options=True):
    early = periods.early_closes()
    stock = D.read_stock(sym, a, b, PA.ROOT)
    by_day = {d: g for d, g in stock.groupby(stock["ts"].dt.date)} if stock is not None else {}
    rep = {"symbol": sym, "from": a.isoformat(), "to": b.isoformat(), "sessions": 0, "no_bars": [], "short_sessions": [],
           "early_closes": [], "no_option_bars": [], "contracts_per_session": None, "known_option_gaps": list(PA.KNOWN_OPTION_GAPS),
           "premarket_missing": []}
    counts = []
    for d in sessions(a, b):
        g = by_day.get(d)
        if g is None:
            rep["no_bars"].append(d.isoformat())
            continue
        rep["sessions"] += 1
        hm = g["ts"].dt.strftime("%H:%M")
        rth = int(((hm >= "09:30") & (hm < "16:00")).sum())
        if not ((hm >= "04:00") & (hm < "09:30")).any():
            rep["premarket_missing"].append(d.isoformat())
        if d.isoformat() in early:
            rep["early_closes"].append({"day": d.isoformat(), "rth_minutes": rth})
        elif rth < 390:
            rep["short_sessions"].append({"day": d.isoformat(), "rth_minutes": rth, "missing": 390 - rth})
        f = PA.ROOT / "options" / sym / d.isoformat() / "bars.csv.gz"
        if not options:
            continue
        if not f.exists():
            rep["no_option_bars"].append(d.isoformat())
            continue
        try:
            ob = pd.read_csv(f, compression="gzip")
        except (ValueError, OSError, EOFError):
            ob = pd.DataFrame()
        n = int(ob["symbol"].nunique()) if "symbol" in ob and len(ob) else 0
        if n == 0:
            rep["no_option_bars"].append(d.isoformat())
        counts.append(n)
    if counts:
        rep["contracts_per_session"] = {"min": min(counts), "median": statistics.median(counts), "max": max(counts)}
    if out_dir:
        p = Path(out_dir) / f"gaps_{sym}_{a}_{b}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rep, indent=1))
        rep["file"] = str(p)
    return rep


def disk_mb(sym):
    tot = 0
    for p in (PA.ROOT / "stocks" / sym, PA.ROOT / "options" / sym):
        if p.exists():
            tot += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return round(tot / 1e6, 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read-only Alpaca puller for the sprint (data.alpaca.markets only)")
    ap.add_argument("--symbols", default="SPY,QQQ,IWM")
    ap.add_argument("--from", dest="a", required=True)
    ap.add_argument("--to", dest="b", required=True)
    ap.add_argument("--band", type=float, default=0.03)
    ap.add_argument("--trades", action="store_true")
    ap.add_argument("--trades-band", type=float, default=0.015)
    ap.add_argument("--feed", default="sip", choices=["sip", "iex"])
    ap.add_argument("--gaps-only", action="store_true")
    ap.add_argument("--stock-only", default="VIXY", help="symbols pulled as stock bars only, no options (default VIXY)")
    ap.add_argument("--daily", default="VIXY", help="symbols pulled as split-adjusted daily bars (default VIXY)")
    ap.add_argument("--daily-from", default="2023-01-01", help="first day of the daily pull (locked periods are cut out)")
    ap.add_argument("--root", default=None, help="cache root (default data/alpaca)")
    ap.add_argument("--locked")
    ap.add_argument("--frozen")
    ap.add_argument("--spec")
    x = ap.parse_args(argv)
    a, b = date.fromisoformat(x.a), date.fromisoformat(x.b)
    try:
        periods.guard(a, b, x.locked, x.frozen, x.spec)
    except periods.LockedPeriod as e:
        print(str(e), file=sys.stderr)
        return 2
    if x.root:
        PA.ROOT = Path(x.root)
    syms = [s.strip().upper() for s in x.symbols.split(",") if s.strip()]
    stock_only = [s.strip().upper() for s in (x.stock_only or "").split(",") if s.strip() and s.strip().upper() not in syms]
    out_dir = (Path(x.root).parent if x.root else HERE / "data") / "sprint"
    n_days = len(sessions(a, b))
    print(f"sprint_pull: {','.join(syms)} {a}..{b} ({n_days} sessions), band {x.band:.1%}, trades {'on' if x.trades else 'off'}, "
          f"stock bars only: {','.join(stock_only) or 'none'}, cache {PA.ROOT}", flush=True)
    for s in syms:
        if not x.gaps_only:
            print(s, "stocks", pull_stock(s, a, b, x.feed), flush=True)
            r = pull_options(s, a, b, x.band, x.trades, x.trades_band)
            print(s, "options", {k: (v if k != "no_stock_bars" else len(v)) for k, v in r.items()}, flush=True)
        g = gap_report(s, a, b, out_dir)
        print(f"{s}: {g['sessions']} sessions, {len(g['no_bars'])} weekdays without bars {g['no_bars'][:10]}, "
              f"{len(g['short_sessions'])} short sessions, {len(g['early_closes'])} early closes, "
              f"{len(g['no_option_bars'])} sessions without 0DTE bars {g['no_option_bars'][:10]}, contracts/session "
              f"{g['contracts_per_session']}, {disk_mb(s)} MB on disk -> {g.get('file')}", flush=True)
    for s in stock_only:
        if not x.gaps_only:
            print(s, "stocks (no options)", pull_stock(s, a, b, x.feed), flush=True)
        g = gap_report(s, a, b, out_dir, options=False)
        print(f"{s}: {g['sessions']} sessions, {len(g['no_bars'])} weekdays without bars {g['no_bars'][:10]}, "
              f"{len(g['short_sessions'])} short sessions, {disk_mb(s)} MB on disk -> {g.get('file')}", flush=True)
    for s in [x.strip().upper() for x in (x.daily or "").split(",") if x.strip()]:
        if not x.gaps_only:
            r = pull_daily(s, date.fromisoformat(x.daily_from), b, x.feed)
            print(f"{s}: {r['rows']} daily bars (split-adjusted) over {', '.join(r['segments'])} (locked periods cut out)", flush=True)
    sm = SP.from_chains(HERE / "data" / "chains", set(syms))
    print("spread model for the runner:", sm.describe(), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
