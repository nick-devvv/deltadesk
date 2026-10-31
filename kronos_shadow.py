#!/usr/bin/env python3
"""kronos_shadow.py - Kronos forecast test for SPY/QQQ (shadow only: never trades, never gates a plan).

Runs as its own process (started by server.py when KRONOS=1) with broker keys and the desk token
removed from its environment. Every completed 5-minute bar during regular hours, it forecasts the
close 5/10/15 minutes ahead with Kronos-mini on CPU, and stores the forecast next to two simple
baselines (no-change, short momentum). Later bars score all three. /api/kronos shows the record.

Setup on Chart's computer (one time):
  git clone https://github.com/shiyu-coder/Kronos ~/Kronos && cd ~/Kronos && git checkout 67b630e
  pip install torch --index-url https://download.pytorch.org/whl/cpu
  pip install einops==0.8.1 huggingface_hub==0.33.1 safetensors==0.6.2 tqdm
  add KRONOS=1 (and KRONOS_DIR=~/Kronos if elsewhere) to the env watchdog.sh starts the server with.
Model: NeoQuasar/Kronos-mini + NeoQuasar/Kronos-Tokenizer-2k (MIT license), downloaded once by huggingface_hub.
"""
import json
import os
import sys
import time
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import core  # noqa: E402
import store  # noqa: E402

TICKERS = ("SPY", "QQQ")
HORIZONS = (5, 10, 15)          # minutes = 1, 2, 3 bars of 5m
LOOKBACK = 400                   # 5m bars (~5 sessions of RTH)
SAMPLES = 8                      # averaged by Kronos; this is a point forecast, not an interval
MODEL = "NeoQuasar/Kronos-mini"
TOKENIZER = "NeoQuasar/Kronos-Tokenizer-2k"
REV = "67b630e"

SCHEMA = """CREATE TABLE IF NOT EXISTS forecasts(id TEXT PRIMARY KEY, ticker TEXT, made_at TEXT, bar_ts TEXT,
  horizon INTEGER, target_ts TEXT, base REAL, pred REAL, pred_mom REAL, actual REAL, model TEXT, runtime_ms INTEGER,
  data_src TEXT)"""
YAHOO = "yahoo 5m (research input)"
SCHWAB = "schwab 1m->5m (desk archive)"
PRE_V3 = "yahoo (pre-v3)"           # forecasts made before the data migration have NULL data_src


def migrate():
    store.x(SCHEMA)
    try:
        store.x("ALTER TABLE forecasts ADD COLUMN data_src TEXT")
    except Exception:
        pass                                   # already there


def status(state, **kw):
    store.kv_set("kronos_status", dict(state=state, at=store.ts(), **kw))


def _archive_5m(ticker):
    """Schwab 1m bars the desk engine archives every tick, rebuilt into 09:30-anchored 5m RTH bars (complete ones only)."""
    import pandas as pd
    since = (core.now_et() - timedelta(days=10)).isoformat()
    rows = store.q("SELECT open, o, h, l, c, v FROM bars_archive WHERE ticker=? AND open>=? AND src LIKE 'Schwab%' ORDER BY open",
                   (ticker, since))
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["open"], utc=True).dt.tz_convert(core.ET)
    df = df.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})[["Open", "High", "Low", "Close", "Volume"]]
    df = df.between_time("09:30", "15:59")
    out = []
    for _, g in df.groupby(df.index.date):
        r = g.resample("5min", origin="start_day", offset="30min").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
        n = g["Close"].resample("5min", origin="start_day", offset="30min").count()
        out.append(r[n == 5])                                  # a 5m bar needs all five minutes: no partial bars
    return pd.concat(out) if out else None


def rth_5m(ticker):
    """(completed RTH 5m bars, source). One source per forecast, never mixed: the desk's Schwab archive once it holds
    enough history (about 5 sessions after v3 starts), Yahoo before that. The source is stored on every forecast so
    pre- and post-migration results stay separate."""
    now = core.now_et()
    a = _archive_5m(ticker)
    if a is not None and len(a) >= LOOKBACK - 10:
        return a[a.index + timedelta(minutes=5) <= now], SCHWAB
    import chartdata
    df = chartdata._dl(ticker, "7d", "5m", True)   # ~400 RTH bars; small request
    if df is None or df.empty:
        return None, YAHOO
    df = df.tz_convert(core.ET) if df.index.tz is not None else df.tz_localize(core.ET)
    df = df.between_time("09:30", "15:55")
    return df[df.index + timedelta(minutes=5) <= now], YAHOO   # completed bars only


def momentum(closes, h):
    """Baseline: continue the last 15 minutes' change, scaled to the horizon."""
    if len(closes) < 4:
        return float(closes[-1])
    return float(closes[-1] + (closes[-1] - closes[-4]) * h / 15)


def forecast(ticker, bars, predict_fn, model_name=MODEL, src=YAHOO):
    """bars: completed RTH 5m OHLCV DataFrame. predict_fn(x_df, x_ts, y_ts, n) -> list of predicted closes."""
    import pandas as pd
    if bars is None or len(bars) < 60:
        return []
    last_ts = bars.index[-1]
    key = f"{ticker}-{last_ts.isoformat()}"
    if store.q("SELECT 1 FROM forecasts WHERE id LIKE ?", (key + "%",)):
        return []                                              # already forecast this bar
    x = bars.dropna(subset=["Open", "High", "Low", "Close"]).iloc[-LOOKBACK:].copy()
    x["Volume"] = x["Volume"].fillna(0.0)            # Kronos rejects NaN
    x_df = pd.DataFrame({"open": x["Open"].values, "high": x["High"].values, "low": x["Low"].values,
                         "close": x["Close"].values, "volume": x["Volume"].values})
    n = max(HORIZONS) // 5
    y_ts = pd.Series([last_ts + timedelta(minutes=5 * (i + 1)) for i in range(n)])
    t0 = time.time()
    preds = predict_fn(x_df, pd.Series(x.index), y_ts, n)
    ms = int((time.time() - t0) * 1000)
    base = float(x["Close"].iloc[-1])
    closes = x["Close"].values
    rows = []
    for h in HORIZONS:
        i = h // 5 - 1
        tgt = last_ts + timedelta(minutes=5 * (i + 1))          # the bar starting here closes h minutes after base
        rid = f"{key}-{h}"
        store.x("INSERT OR IGNORE INTO forecasts(id,ticker,made_at,bar_ts,horizon,target_ts,base,pred,pred_mom,actual,model,runtime_ms,data_src) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, ticker, store.ts(), last_ts.isoformat(), h, tgt.isoformat(), base, float(preds[i]),
                 momentum(closes, h), None, model_name, ms, src))
        rows.append(rid)
    return rows


def score(ticker, bars, src=YAHOO):
    """Fill in the actual close for forecasts whose target bar has completed, from the SAME source they used."""
    if bars is None or bars.empty:
        return 0
    closes = {ts.isoformat(): float(c) for ts, c in bars["Close"].items()}
    n = 0
    cond = "(data_src=? OR data_src IS NULL)" if src == YAHOO else "data_src=?"
    for r in store.q(f"SELECT id, target_ts FROM forecasts WHERE ticker=? AND actual IS NULL AND {cond}", (ticker, src)):
        if r["target_ts"] in closes:
            store.x("UPDATE forecasts SET actual=? WHERE id=?", (closes[r["target_ts"]], r["id"]))
            n += 1
    return n


def metrics():
    """Per horizon: n, mean abs error (Kronos vs no-change vs momentum), direction hits vs momentum.
    Direction is scored only on bars that moved (flat outcomes excluded and counted). 'sources' shows how many
    scored forecasts came from each data source, so a data change can't hide inside one number."""
    out = {"sources": {(r["s"] or PRE_V3): r["n"] for r in
                       store.q("SELECT data_src s, COUNT(*) n FROM forecasts WHERE actual IS NOT NULL GROUP BY data_src")}}
    for h in HORIZONS:
        rs = store.q("SELECT base, pred, pred_mom, actual FROM forecasts WHERE horizon=? AND actual IS NOT NULL", (h,))
        if not rs:
            out[h] = {"n": 0}
            continue
        mae = lambda f: round(sum(abs(f(r) - r["actual"]) for r in rs) / len(rs), 4)
        moved = [r for r in rs if r["actual"] != r["base"]]
        hit = lambda f: (round(100 * sum(1 for r in moved if (f(r) - r["base"]) * (r["actual"] - r["base"]) > 0) / len(moved), 1)
                         if moved else None)
        out[h] = {"n": len(rs), "days": len({r["d"] for r in store.q("SELECT substr(bar_ts,1,10) d FROM forecasts WHERE horizon=? AND actual IS NOT NULL", (h,))}),
                  "mae_kronos": mae(lambda r: r["pred"]), "mae_nochange": mae(lambda r: r["base"]), "mae_momentum": mae(lambda r: r["pred_mom"]),
                  "dir_kronos": hit(lambda r: r["pred"]), "dir_momentum": hit(lambda r: r["pred_mom"])}
    return out


def verdict(m):
    """Plain-English status. Needs >= 20 trading days and beating BOTH baselines on error at 15 min."""
    x = m.get(15, {})
    if not x.get("n"):
        return "collecting: no scored forecasts yet"
    if x.get("days", 0) < 20:
        return f"collecting: {x['days']} of 20 trading days scored"
    better = x["mae_kronos"] < x["mae_nochange"] and x["mae_kronos"] < x["mae_momentum"]
    return "beats both baselines so far (still shadow: Nick decides if it ever gets a say)" if better else \
           "not beating simple baselines: keep as research only"


def load_predictor():
    kdir = os.path.expanduser(os.environ.get("KRONOS_DIR", "~/Kronos"))
    sys.path.insert(0, kdir)
    from model import Kronos, KronosPredictor, KronosTokenizer
    import torch
    torch.manual_seed(7)
    tok = KronosTokenizer.from_pretrained(TOKENIZER)
    mdl = Kronos.from_pretrained(MODEL)
    mdl.eval()
    p = KronosPredictor(mdl, tok, device="cpu", max_context=2048)

    def predict_fn(x_df, x_ts, y_ts, n):
        torch.manual_seed(int(x_ts.iloc[-1].timestamp()) % (2 ** 31))
        df = p.predict(df=x_df, x_timestamp=x_ts.reset_index(drop=True), y_timestamp=y_ts, pred_len=n,
                       T=1.0, top_p=0.9, sample_count=SAMPLES, verbose=False)
        return [float(v) for v in df["close"].values[:n]]
    return predict_fn


LOCK = os.path.join(HERE, "journal", "kronos.lock")


def single_instance(path=LOCK):
    """v3.4.1: at most ONE Kronos process per desk. Returns the open lock file (keep it) or None if another copy
    already holds the lock. The lock is released by the OS when the process ends, however it ends."""
    import fcntl
    os.makedirs(os.path.dirname(path), exist_ok=True)
    f = open(path, "a+")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    return f


def parent_alive(ppid0):
    """True while the desk server that started this process is still our parent. When the server dies, the OS
    re-parents us (pid 1 / launchd), and this copy exits instead of living on as an orphan."""
    return os.getppid() == ppid0


def _sleep_watching(seconds, ppid0, step=5.0):
    end = time.time() + seconds
    while time.time() < end:
        if not parent_alive(ppid0):
            return False
        time.sleep(min(step, max(0.0, end - time.time())))
    return parent_alive(ppid0)


def _until_next_bar():
    """Wake once per 5-minute bar (20 s after it completes) instead of polling Yahoo every 30 s."""
    now = core.now_et()
    nxt = now.replace(second=0, microsecond=0) + timedelta(minutes=5 - now.minute % 5, seconds=20)
    return max(30, (nxt - now).total_seconds())


def main():
    ppid0 = os.getppid()
    try:
        os.nice(10)                          # v3.5: Kronos is optional research: lower CPU priority than the desk
    except (OSError, AttributeError):
        pass
    lock = single_instance()
    if lock is None:
        print("kronos_shadow: another copy is already running; this one exits", flush=True)
        return
    migrate()
    status("loading", model=MODEL, rev=REV, pid=os.getpid())
    try:
        predict_fn = load_predictor()
    except Exception as e:
        status("error", error=f"{type(e).__name__}: {e}"[:300], hint="see setup steps at the top of kronos_shadow.py")
        return
    status("running", model=MODEL, rev=REV, pid=os.getpid())
    while parent_alive(ppid0):
        sess = core.session_info()
        try:
            scoring_window = sess["state"] != "AFTER HOURS" or sess["time"] <= "16:30"
            if sess["state"] in ("OPEN", "NO NEW ENTRIES", "ALL OUT", "AFTER HOURS") and not sess["holiday"] and scoring_window:
                for t in TICKERS:
                    bars, src = rth_5m(t)
                    score(t, bars, src)
                    if sess["state"] != "AFTER HOURS" and bars is not None and len(bars) and bars.index[-1].date() == core.now_et().date():
                        forecast(t, bars, predict_fn, src=src)
            status("running", model=MODEL, rev=REV, verdict=verdict(metrics()))
        except Exception as e:
            status("running", model=MODEL, rev=REV, last_error=f"{type(e).__name__}: {e}"[:300])
        if not _sleep_watching(_until_next_bar(), ppid0):
            break
    status("stopped", why="the desk server that started it is gone; the next server starts a fresh copy")


if __name__ == "__main__":
    main()
