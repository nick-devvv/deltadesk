"""backtest.py - run the desk over many past days, then diagnose the results.

  python3 backtest.py --from 2026-09-22 --to 2026-10-29            # Schwab history (Schwab must be connected)
  python3 backtest.py --from 2026-09-22 --to 2026-10-29 --csv reports/backtest_bars_....csv   # exact rerun
  options: --no-inplay (skip the stocks-in-play part), --until 16:06, --iv 0.18

What runs, all in a sandbox (the live desk database, alerts and settings are never touched):
  * SPY/QQQ: the real engine minute by minute (main paper v3, research, the v3.1-exit mirror, noise band, old rules),
    on 1m bars with MODELED option quotes (Black-Scholes; Schwab has no historical option quotes).
  * Stocks in play: the scanner's rules on the universe's 1m history (scanner.backtest_day), stock result in R and
    a MODELED option result.
  * diagnostics.py on everything: coin-flip baseline, exit breakdown, hold tests, stock vs option, halves, up/down days.
Writes reports/backtest_<from>_<to>.md/.json, the sandbox database (for re-diagnosing) and the bars CSV + sha256.
Runtime on a laptop: roughly 1-2 minutes per day for SPY/QQQ, plus about 3 minutes to download the universe.
This is research on days that were partly used to design v3: in-sample. Forward paper results decide.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
for k in ("NTFY_TOPIC", "CHAT_WEBHOOK", "GROK_WEBHOOK"):
    os.environ.pop(k, None)

import pandas as pd  # noqa: E402

import core  # noqa: E402
import diagnostics  # noqa: E402
import replay  # noqa: E402
import store  # noqa: E402

ET = core.ET


def trading_days(m1s, d1, d2):
    days = set()
    for df in m1s.values():
        r = df.between_time("09:30", "15:59")
        days |= {d for d in set(r.index.date) if d1 <= d <= d2 and (r.index.date == d).sum() >= 200}
    return sorted(days)


def load(d1, d2, csv=None, tickers=None):
    if csv:
        df = pd.read_csv(csv)
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(ET)
        return {t: g.set_index("ts")[["Open", "High", "Low", "Close", "Volume"]].sort_index() for t, g in df.groupby("ticker")}
    import schwab
    if not schwab.ready():
        raise SystemExit("Schwab is not connected. Connect it on the Rules page, or pass --csv.")
    start = datetime.combine(d1 - timedelta(days=30), datetime.min.time(), ET)
    end = datetime.combine(d2, datetime.min.time(), ET).replace(hour=20)
    out = {}
    for t in tickers or core.policy()["instruments"]:
        # SPY/QQQ keep extended hours (premarket levels); the universe only needs regular hours (much smaller)
        df = schwab.bars_1m_range(t, start, end) if not tickers else schwab.bars_range(t, start, end, 1, extended=False)
        if df is not None and len(df):
            out[t] = df.sort_index()
    return out


def save(m1s, name):
    rows = []
    for t, df in m1s.items():
        d = df.copy()
        d["ticker"] = t
        d["ts"] = d.index.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append(d[["ts", "ticker", "Open", "High", "Low", "Close", "Volume"]])
    path = replay.REPORTS / name
    replay.REPORTS.mkdir(exist_ok=True)
    pd.concat(rows).to_csv(path, index=False)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def run_engine(m1s, days, src, mode="close", iv=0.18, until="16:06", keep_db=None, progress=True):
    """The real engine over each day in ONE sandbox, so ledgers, streaks and the research record accumulate."""
    import engine
    clock = replay.Clock(replay.at(days[0], "09:30"))
    prov = replay.ReplayProvider(m1s, clock, src, iv, mode)
    t_start = time.time()
    with replay.sandbox(prov, clock):
        store.kv_set("alert_settings", {k: False for k in ("setups", "moves", "news", "scanner", "movers", "mytrades")})
        for i, day in enumerate(days):
            t, stop = replay.at(day, "09:30"), replay.at(day, until)
            engine._cache.clear()
            while t <= stop:
                clock.t = t
                engine._cache.clear()
                engine.tick()
                t += timedelta(minutes=1)
            if progress:
                print(f"  {day}: done ({i + 1}/{len(days)}, {time.time() - t_start:.0f}s)", flush=True)
        summary = {}
        for led in ("paper", "research", "exit31", "noise", "old"):
            rows = store.q("SELECT realized FROM positions WHERE ledger=? AND status='CLOSED'", (led,))
            summary[led] = diagnostics.stats([r["realized"] or 0 for r in rows])
        if keep_db:
            store.conn().commit()
            shutil.copy(store.DB, keep_db)
    return summary


def inplay_history(d1, d2, csv=None):
    """Universe 1m history + daily bars for the in-play part (Schwab), or from a saved CSV."""
    import scanner
    if csv:
        m1s = load(d1, d2, csv)
        return m1s, None
    import schwab
    m1s, daily = load(d1, d2, None, scanner.universe()), {}
    for t in m1s:
        daily[t] = schwab.bars_daily(t)
    return m1s, daily


def run_inplay(m1s, daily, days, legacy=False):
    """bt2 (causal: decision at bar close, fill at the next bar's open, gap-through stops, 09:45 first entry) unless
    legacy=True (bt1, kept only to reproduce the old report)."""
    import scanner
    trades, rejected = [], []
    for day in days:
        base, iv = {}, {}
        for t, m1 in m1s.items():
            d = daily.get(t) if daily else None
            if d is None:                                   # from 1m history when daily bars weren't saved
                r = m1.between_time("09:30", "15:59")
                d = r.resample("1D").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
                d.index = d.index.tz_localize(None)
            m5 = m1.between_time("09:30", "15:59").resample("5min").agg({"Volume": "sum"})
            m5 = m5[m5["Volume"] > 0]
            base[t] = scanner.baseline(d, m5, day, core.policy()["scanner"].get("baseline_sessions", 10))
            closes = d[[pd.Timestamp(x).date() < day for x in d.index]]["Close"].iloc[-21:]
            rv = closes.pct_change().std() * (252 ** 0.5) if len(closes) > 5 else None
            iv[t] = round(float(rv) * 1.1, 3) if rv == rv and rv else None
        if legacy:
            trades += scanner.backtest_day(day, m1s, base, iv)
        else:
            r = scanner.backtest_day_v2(day, m1s, base, iv)
            trades += r["trades"]
            rejected += r["rejected"]
    run_inplay.rejected = rejected
    return trades


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d1", required=True)
    ap.add_argument("--to", dest="d2", required=True)
    ap.add_argument("--csv")
    ap.add_argument("--inplay-csv")
    ap.add_argument("--no-inplay", action="store_true")
    ap.add_argument("--until", default="16:06")
    ap.add_argument("--iv", type=float, default=0.18)
    a = ap.parse_args(argv)
    d1, d2 = datetime.strptime(a.d1, "%Y-%m-%d").date(), datetime.strptime(a.d2, "%Y-%m-%d").date()
    label = f"{d1}_{d2}"
    m1s = load(d1, d2, a.csv)
    src = "csv" if a.csv else "schwab"
    path, sha = (Path(a.csv), hashlib.sha256(Path(a.csv).read_bytes()).hexdigest()) if a.csv else save(m1s, f"backtest_bars_{label}_{src}.csv")
    days = trading_days(m1s, d1, d2)
    if not days:
        raise SystemExit("no complete trading days in that range")
    print(f"Backtest {d1} to {d2}: {len(days)} days, bars {path.name}", flush=True)
    db = replay.REPORTS / f"backtest_{label}.db"
    summary = run_engine(m1s, days, src, "close", a.iv, a.until, keep_db=db)
    diag = diagnostics.run(db, m1s, replay.REPORTS, label=label)
    inplay = None
    if not a.no_inplay:
        try:
            um1, udaily = inplay_history(d1, d2, a.inplay_csv)
            if not a.inplay_csv:
                save(um1, f"backtest_inplay_bars_{label}.csv")
            tr = run_inplay(um1, udaily, days)
            rnd = __import__("random").Random(7)
            inplay = {"trades": tr, "stock_R": diagnostics.stats([t["stock_R"] for t in tr if t["stock_R"] is not None]),
                      "option_modeled": diagnostics.stats([t["option_pnl_modeled"] for t in tr]),
                      "note": "shares rules from the paper, entries on 1m closes; option result MODELED (no historical quotes)"}
            _ = rnd
        except SystemExit as e:
            inplay = {"skipped": str(e)}
    res = {"from": str(d1), "to": str(d2), "days": len(days), "bars": path.name, "sha256": sha, "engine_ledgers": summary,
           "diagnostics": f"diagnostics_{label}.md", "inplay": inplay}
    (replay.REPORTS / f"backtest_{label}.json").write_text(json.dumps(res, indent=1, default=str))
    L = [f"# Backtest {d1} to {d2}", "", f"{len(days)} trading days. Bars `{path.name}` (sha256 `{sha[:16]}...`). "
         "Option prices are MODELED everywhere in this report. In-sample research: forward paper decides.", "",
         "## Engine ledgers (SPY/QQQ, modeled option quotes)", ""]
    for led, st in summary.items():
        L.append(f"- {led}: {diagnostics._s(st)}")
    L += ["", f"Diagnostics: see `diagnostics_{label}.md` (coin flip, exits, hold tests, halves, up/down days).", "",
          "## Stocks in play (scanner rules, shares rules + modeled options)", ""]
    if inplay and inplay.get("trades") is not None:
        L.append(f"- Stock, in R: {diagnostics._s(inplay['stock_R'])}")
        L.append(f"- Option (modeled): {diagnostics._s(inplay['option_modeled'])}")
    else:
        L.append(f"- {inplay}")
    (replay.REPORTS / f"backtest_{label}.md").write_text("\n".join(L))
    print("\n".join(L))
    print("\n" + diagnostics.markdown(diag))
    return res


if __name__ == "__main__":
    main()
