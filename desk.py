#!/usr/bin/env python3
"""desk.py - Nick's SPY/QQQ 0DTE desk calculator.

Code does the math, the bot explains. Uses free Yahoo Finance data (yfinance).
Usage:
  python desk.py SPY QQQ                 -> full read of each ticker + SPY/QQQ agreement
  python desk.py plan 1.45 10:15         -> stop / breakeven / T1 / if-flat for a fill at a time (ET)
Never places trades. Option prices must be checked on the live chain (Legend).
"""
import sys
from datetime import datetime, timedelta

try:
    import pandas as pd
    import yfinance as yf
except ImportError:
    print("Run: pip install yfinance pandas")
    sys.exit(1)

ET = "America/New_York"

# ---------------- time-of-day rules (multipliers of the fill) ----------------
WINDOWS = [  # name, start, end, stop, breakeven, t1_lo, t1_hi, flat_minutes
    ("MORNING", "09:45", "11:30", 0.85, 1.10, 1.20, 1.30, 5),
    ("MIDDAY", "11:30", "14:00", 0.88, 1.08, 1.15, 1.20, 3),
    ("AFTERNOON", "14:00", "15:30", 0.90, 1.06, 1.12, 1.15, 3),
]


def window_for(hhmm):
    for w in WINDOWS:
        if w[1] <= hhmm < w[2]:
            return w
    return None


def plan(fill, hhmm):
    w = window_for(hhmm)
    if w is None:
        if hhmm < "09:45":
            return "NO ENTRIES before 9:45 ET (ORB forming)."
        return "NO NEW TRADES after 3:30 ET. ALL OUT BY 3:50."
    name, _, _, s, be, lo, hi, flat = w
    t = datetime.strptime(hhmm, "%H:%M") + timedelta(minutes=flat)
    return (f"{name} | fill ${fill:.2f} | STOP ${fill*s:.2f} | BREAKEVEN when ${fill*be:.2f} "
            f"(stop to ${fill:.2f}) | T1 ${fill*lo:.2f}-${fill*hi:.2f} SELL ALL | "
            f"IF FLAT exit by {t.strftime('%H:%M')} | ALL OUT BY 15:50")


# ---------------- indicators ----------------
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, 1e-9))


def resample(df, rule):
    return df.resample(rule, label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()


def trend(df):
    """up / down / range from EMA stack + last swing structure."""
    if len(df) < 25:
        return "n/a"
    c = df["Close"]
    e9, e21 = ema(c, 9).iloc[-1], ema(c, 21).iloc[-1]
    hi, lo = df["High"].iloc[-6:], df["Low"].iloc[-6:]
    hh = hi.iloc[-3:].max() > hi.iloc[:3].max()
    hl = lo.iloc[-3:].min() > lo.iloc[:3].min()
    lh = hi.iloc[-3:].max() < hi.iloc[:3].max()
    ll = lo.iloc[-3:].min() < lo.iloc[:3].min()
    if c.iloc[-1] > e9 > e21 and (hh or hl):
        return "UP"
    if c.iloc[-1] < e9 < e21 and (lh or ll):
        return "DOWN"
    return "RANGE"


def entry_tf(hhmm):
    if hhmm < "10:00":
        return "2min"
    if hhmm < "11:00":
        return "5min"
    return "10min"


# ---------------- core read ----------------
def read(ticker, m1=None, daily=None):
    if m1 is None:
        m1 = yf.download(ticker, period="5d", interval="1m", prepost=True, progress=False, auto_adjust=False)
        daily = yf.download(ticker, period="2y", interval="1d", progress=False, auto_adjust=False)
    if isinstance(m1.columns, pd.MultiIndex):
        m1.columns = m1.columns.get_level_values(0)
    if isinstance(daily.columns, pd.MultiIndex):
        daily.columns = daily.columns.get_level_values(0)
    if m1.empty or daily.empty:
        return {"ticker": ticker, "error": "NO DATA (Yahoo blocked or market data unavailable)"}
    m1 = m1.tz_convert(ET) if m1.index.tz is not None else m1.tz_localize(ET)

    now = m1.index[-1]
    today = now.date()
    hhmm = now.strftime("%H:%M")
    td = m1[m1.index.date == today]
    rth = td.between_time("09:30", "15:59")
    pre = td.between_time("04:00", "09:29")
    price = float(m1["Close"].iloc[-1])
    out = {"ticker": ticker, "time": now.strftime("%Y-%m-%d %H:%M ET"), "price": round(price, 2)}

    # stale check: last bar older than 3 minutes during RTH
    age_min = (pd.Timestamp.now(tz=ET) - now).total_seconds() / 60
    out["stale"] = bool("09:30" <= hhmm <= "16:00" and age_min > 3)

    # prior day levels (last completed daily bar before today)
    d = daily[daily.index.date < today] if daily.index.tz is None else daily[daily.index.tz_convert(ET).date < today]
    pdh, pdl, pdc = float(d["High"].iloc[-1]), float(d["Low"].iloc[-1]), float(d["Close"].iloc[-1])
    lv = {"PDH": pdh, "PDL": pdl, "PDC": pdc}
    if not pre.empty:
        lv["PMH"], lv["PML"] = float(pre["High"].max()), float(pre["Low"].min())
    # weekly / swing levels
    wk = daily.resample("W").agg({"High": "max", "Low": "min"})
    if len(wk) > 1:
        lv["PWH"], lv["PWL"] = float(wk["High"].iloc[-2]), float(wk["Low"].iloc[-2])
    last6m = d.tail(126)
    lv["6M_HIGH"], lv["6M_LOW"] = float(last6m["High"].max()), float(last6m["Low"].min())

    # session
    orb = None
    if not rth.empty:
        lv["OPEN"] = float(rth["Open"].iloc[0])
        ob = rth.between_time("09:30", "09:44")
        if hhmm >= "09:45" and not ob.empty:
            orb = (float(ob["High"].max()), float(ob["Low"].min()))
            lv["ORB_H"], lv["ORB_L"] = orb
        tp = (rth["High"] + rth["Low"] + rth["Close"]) / 3
        vwap = (tp * rth["Volume"]).cumsum() / rth["Volume"].cumsum().replace(0, 1e-9)
        lv["VWAP"] = float(vwap.iloc[-1])
    else:
        vwap = None

    # moving averages on 5m (all data incl. prior days)
    m5 = resample(m1.between_time("09:30", "15:59"), "5min")
    c5 = m5["Close"]
    ma = {"EMA9": ema(c5, 9).iloc[-1], "EMA21": ema(c5, 21).iloc[-1],
          "EMA200": ema(c5, 200).iloc[-1], "SMA200": c5.rolling(200).mean().iloc[-1],
          "SMA400": c5.rolling(400).mean().iloc[-1]}
    for k, v in ma.items():
        if pd.notna(v):
            lv[k] = float(v)

    # round numbers
    step = 5 if price > 200 else 1
    lv["ROUND_UP"] = (int(price // step) + 1) * step
    lv["ROUND_DN"] = int(price // step) * step

    # timeframe trends
    reg = m1.between_time("09:30", "15:59")
    out["trend"] = {tf: trend(resample(reg, r)) for tf, r in
                    [("2m", "2min"), ("5m", "5min"), ("10m", "10min"), ("15m", "15min"), ("1H", "60min")]}
    out["trend"]["D"] = trend(daily)

    # entry timeframe momentum
    etf = resample(reg, entry_tf(hhmm) if "09:30" <= hhmm <= "16:00" else "5min")
    ce = etf["Close"]
    macd = ema(ce, 12) - ema(ce, 26)
    sig = ema(macd, 9)
    out["entry_tf"] = entry_tf(hhmm)
    out["rsi"] = round(float(rsi(ce).iloc[-1]), 1)
    out["macd"] = "BULL" if macd.iloc[-1] > sig.iloc[-1] else "BEAR"
    vol_avg = etf["Volume"].iloc[-21:-1].mean()
    out["rvol"] = round(float(etf["Volume"].iloc[-1] / vol_avg), 2) if vol_avg else None

    # chop: VWAP crosses in last 60 one-minute bars, EMA flatness
    chop = False
    if vwap is not None and len(rth) > 10:
        side = (rth["Close"] > vwap).astype(int)
        crosses = int((side.diff().abs().iloc[-60:]).sum())
        out["vwap_crosses_1h"] = crosses
        flat = abs(ma["EMA9"] - ma["EMA21"]) / price < 0.0003
        chop = crosses >= 3 or flat
    out["chop"] = chop

    # day type
    if orb:
        out["day_type"] = "TREND UP (above ORB)" if price > orb[0] else "TREND DOWN (below ORB)" if price < orb[1] else "CHOP (inside ORB)"
    else:
        out["day_type"] = "ORB forming" if "09:30" <= hhmm < "09:45" else "n/a"

    # side of key references
    out["vs_vwap"] = "ABOVE" if "VWAP" in lv and price > lv["VWAP"] else "BELOW" if "VWAP" in lv else "n/a"
    if "EMA200" in lv and "SMA200" in lv:
        out["vs_200s"] = ("ABOVE both" if price > max(lv["EMA200"], lv["SMA200"]) else
                          "BELOW both" if price < min(lv["EMA200"], lv["SMA200"]) else "BETWEEN")

    # nearest levels
    items = sorted(((k, round(v, 2)) for k, v in lv.items()), key=lambda x: x[1])
    out["above"] = [f"{k} {v}" for k, v in items if v > price][:4]
    out["below"] = [f"{k} {v}" for k, v in reversed(items) if v < price][:4]

    # simple setup detection on the entry timeframe
    setups = []
    if orb and len(etf) >= 3:
        last, prev = etf.iloc[-1], etf.iloc[-2]
        oh, ol = orb
        if prev["Close"] > oh and last["Low"] <= oh * 1.0005 and last["Close"] > oh:
            setups.append(f"ORB RETEST holding {oh:.2f} (calls)")
        elif last["Close"] > oh >= prev["Close"]:
            setups.append(f"ORB BREAKOUT close above {oh:.2f} (calls)")
        if prev["Close"] < ol and last["High"] >= ol * 0.9995 and last["Close"] < ol:
            setups.append(f"ORB RETEST rejecting {ol:.2f} (puts)")
        elif last["Close"] < ol <= prev["Close"]:
            setups.append(f"ORB BREAKDOWN close below {ol:.2f} (puts)")
        recent = etf.iloc[-6:-1]
        if (recent["Low"] < ol).any() and ol < last["Close"] < oh:
            setups.append(f"FAILED BREAKDOWN reclaim of ORB low {ol:.2f} (calls)")
        if (recent["High"] > oh).any() and ol < last["Close"] < oh:
            setups.append(f"FAILED BREAKOUT back under ORB high {oh:.2f} (puts)")
    if vwap is not None and len(etf) >= 3:
        v = lv["VWAP"]
        if etf["Close"].iloc[-2] < v < etf["Close"].iloc[-1]:
            setups.append(f"VWAP RECLAIM {v:.2f} (calls)")
        if etf["Close"].iloc[-2] > v > etf["Close"].iloc[-1]:
            setups.append(f"VWAP LOSS {v:.2f} (puts)")
    if len(etf) >= 5:
        b = etf.iloc[-5:-1]
        body = (b["Close"] - b["Open"])
        rng = (b["High"] - b["Low"]).replace(0, 1e-9)
        if (body / rng > 0.6).sum() >= 3 and (out["rvol"] or 0) >= 1.5:
            setups.append("MOMENTUM UP: look for 1m flag break (calls)")
        if (-body / rng > 0.6).sum() >= 3 and (out["rvol"] or 0) >= 1.5:
            setups.append("MOMENTUM DOWN: look for 1m flag break (puts)")
    out["setups"] = setups or ["none right now"]
    out["window"] = (window_for(hhmm) or ("CLOSED/NO ENTRY",))[0]

    # inside / outside day vs yesterday's range
    if not rth.empty:
        dh, dl = float(rth["High"].max()), float(rth["Low"].min())
        if price > pdh:
            out["daily"] = "OUTSIDE UP (above PDH)"
        elif price < pdl:
            out["daily"] = "OUTSIDE DOWN (below PDL)"
        elif dh <= pdh and dl >= pdl:
            out["daily"] = "INSIDE DAY (chop risk)"
        else:
            out["daily"] = "TESTED RANGE EDGE, back inside"
    else:
        out["daily"] = "n/a"

    # data kept for the dashboard picture
    sess = rth if not rth.empty else reg[reg.index.date == reg.index[-1].date()]
    out["_bars"] = resample(sess, "5min")
    tp_s = (sess["High"] + sess["Low"] + sess["Close"]) / 3
    out["_vwap"] = resample(((tp_s * sess["Volume"]).cumsum() / sess["Volume"].cumsum().replace(0, 1e-9)).to_frame("Close")
                            .assign(Open=lambda x: x.Close, High=lambda x: x.Close, Low=lambda x: x.Close, Volume=0), "5min")["Close"]
    e9s, e21s = ema(c5, 9), ema(c5, 21)
    out["_e9"], out["_e21"] = e9s.reindex(out["_bars"].index), e21s.reindex(out["_bars"].index)
    out["_lv"] = {k: v for k, v in lv.items() if k in
                  ("PDH", "PDL", "PDC", "PMH", "PML", "ORB_H", "ORB_L", "PWH", "PWL", "EMA200", "SMA200")}
    # the day's chart levels (rebuilt from scratch each day, like Nick's Legend lines)
    out["_draw"] = {k: round(v, 2) for k, v in lv.items() if k in
                    ("PDH", "PDL", "PDC", "PMH", "PML", "PWH", "PWL", "6M_HIGH", "6M_LOW", "ORB_H", "ORB_L", "OPEN")}
    out["levels_date"] = str(today)
    return out


def fmt(r):
    if "error" in r:
        return f"{r['ticker']}: {r['error']}"
    t = r["trend"]
    lines = [
        f"{r['ticker']} {r['price']} | read {r['time']}{' | STALE DATA' if r['stale'] else ''} | window {r['window']} | entry TF {r['entry_tf']}",
        f"DAILY: {r.get('daily', 'n/a')} | DAY: {r['day_type']} | VWAP: {r['vs_vwap']} | 200s: {r.get('vs_200s', 'n/a')} | CHOP: {'YES' if r['chop'] else 'no'} (VWAP crosses 1h: {r.get('vwap_crosses_1h', 'n/a')})",
        f"TREND 2m {t['2m']} | 5m {t['5m']} | 10m {t['10m']} | 15m {t['15m']} | 1H {t['1H']} | D {t['D']}",
        f"RSI {r['rsi']} | MACD {r['macd']} | RVOL {r['rvol']}",
        f"ABOVE: {', '.join(r['above'])}",
        f"BELOW: {', '.join(r['below'])}",
        f"SETUPS: {'; '.join(r['setups'])}",
    ]
    return "\n".join(lines)


def agreement(a, b):
    if "error" in a or "error" in b:
        return ""
    same_vwap = a["vs_vwap"] == b["vs_vwap"]
    same_day = a["day_type"].split()[0:2] == b["day_type"].split()[0:2]
    return "SPY/QQQ: AGREE (stronger)" if same_vwap and same_day else "SPY/QQQ: DIVERGE (choppier, lower grade)"


def dashboard(results, path):
    """Save a dark dashboard PNG: candles + levels for each ticker, plus a data panel."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    bg, panel, grid, txt, dim = "#0e1117", "#161b22", "#262c36", "#e6edf3", "#8b949e"
    up, dn = "#26a69a", "#ef5350"
    lvl_color = {"PDH": "#f2cc60", "PDL": "#f2cc60", "PDC": "#a0a0a0", "PMH": "#c297ff", "PML": "#c297ff",
                 "ORB_H": "#4fc3f7", "ORB_L": "#4fc3f7", "PWH": "#ff9e64", "PWL": "#ff9e64",
                 "EMA200": "#ffffff", "SMA200": "#9e9e9e"}
    good = [r for r in results if "error" not in r]
    n = max(len(good), 1)
    fig = plt.figure(figsize=(16, 4.6 * n + 0.6), facecolor=bg)
    gs = fig.add_gridspec(n, 2, width_ratios=[3.2, 1.25], hspace=0.28, wspace=0.04,
                          left=0.04, right=0.985, top=1 - 0.95 / (4.6 * n + 0.6), bottom=0.04)
    stamp = good[0]["time"] if good else datetime.now().strftime("%Y-%m-%d %H:%M")
    fig.text(0.04, 1 - 0.25 / (4.6 * n + 0.6), f"NICK'S DESK  |  {stamp}", color=txt, fontsize=15, weight="bold", va="center")
    if len(good) == 2:
        fig.text(0.985, 1 - 0.25 / (4.6 * n + 0.6), agreement(*good), color=up if "AGREE" in agreement(*good) else "#f2cc60",
                 fontsize=12, ha="right", va="center", weight="bold")

    for i, r in enumerate(good):
        ax = fig.add_subplot(gs[i, 0], facecolor=panel)
        b = r["_bars"]
        x = range(len(b))
        w = 0.6
        for j, (o, h, l, c) in enumerate(zip(b["Open"], b["High"], b["Low"], b["Close"])):
            col = up if c >= o else dn
            ax.vlines(j, l, h, color=col, linewidth=1)
            ax.add_patch(Rectangle((j - w / 2, min(o, c)), w, max(abs(c - o), 1e-6), color=col))
        ax.plot(x, r["_vwap"].reindex(b.index).values, color="#ffb74d", linewidth=1.6, label="VWAP")
        ax.plot(x, r["_e9"].values, color="#4dd0e1", linewidth=1.1, label="EMA9")
        ax.plot(x, r["_e21"].values, color="#5c6bc0", linewidth=1.1, label="EMA21")
        lo, hi = b["Low"].min(), b["High"].max()
        pad = (hi - lo) * 0.35 + 0.01
        for k, v in r["_lv"].items():
            if lo - pad <= v <= hi + pad:
                ax.axhline(v, color=lvl_color.get(k, dim), linewidth=0.9, linestyle="--", alpha=0.9)
                ax.text(len(b) - 0.5, v, f" {k} {v:.2f}", color=lvl_color.get(k, dim), fontsize=8, va="center")
        ax.axhline(r["price"], color=txt, linewidth=0.6, alpha=0.5)
        ax.set_xlim(-1, len(b) + 6)
        ax.set_ylim(lo - pad * 0.6, hi + pad * 0.6)
        step = max(1, len(b) // 8)
        ax.set_xticks(list(x)[::step])
        ax.set_xticklabels([t.strftime("%H:%M") for t in b.index[::step]], color=dim, fontsize=8)
        ax.tick_params(axis="y", colors=dim, labelsize=8)
        ax.grid(color=grid, linewidth=0.5)
        for s in ax.spines.values():
            s.set_color(grid)
        ax.set_title(f"{r['ticker']}  {r['price']:.2f}   (5m, ET)", color=txt, fontsize=13, loc="left", weight="bold")
        ax.legend(loc="upper left", fontsize=8, facecolor=panel, edgecolor=grid, labelcolor=txt)

        p = fig.add_subplot(gs[i, 1], facecolor=panel)
        p.axis("off")
        t = r["trend"]

        def col(v):
            return up if v in ("UP", "ABOVE", "BULL") or str(v).startswith(("TREND UP", "OUTSIDE UP", "ABOVE")) else \
                dn if v in ("DOWN", "BELOW", "BEAR") or str(v).startswith(("TREND DOWN", "OUTSIDE DOWN", "BELOW")) else "#f2cc60"
        rows = [("WINDOW", r["window"]), ("DAILY", r.get("daily", "n/a")), ("DAY", r["day_type"]),
                ("VWAP", r["vs_vwap"]), ("200s", r.get("vs_200s", "n/a")), ("CHOP", "YES" if r["chop"] else "no"),
                ("2m / 5m", f"{t['2m']} / {t['5m']}"), ("10m / 15m", f"{t['10m']} / {t['15m']}"),
                ("1H / D", f"{t['1H']} / {t['D']}"), ("RSI", r["rsi"]), ("MACD", r["macd"]), ("RVOL", r["rvol"])]
        y = 0.97
        for k, v in rows:
            c = col(v)
            if k == "CHOP":
                c = dn if v == "YES" else up
            if k == "RSI":
                c = "#f2cc60" if (v > 70 or v < 30) else txt
            if k in ("2m / 5m", "10m / 15m", "1H / D"):
                c = col(str(v).split(" / ")[0])
            p.text(0.03, y, k, color=dim, fontsize=9.5, transform=p.transAxes, va="top")
            p.text(0.36, y, str(v), color=c, fontsize=9.5, transform=p.transAxes, va="top", weight="bold")
            y -= 0.062
        p.text(0.03, y - 0.01, "SETUPS", color=dim, fontsize=9.5, transform=p.transAxes, va="top")
        y -= 0.07
        for s in r["setups"][:3]:
            p.text(0.03, y, "• " + s[:46], color=txt, fontsize=9, transform=p.transAxes, va="top")
            y -= 0.055
        if r.get("stale"):
            p.text(0.03, 0.02, "STALE DATA - re-check", color=dn, fontsize=10, transform=p.transAxes, weight="bold")

    fig.savefig(path, dpi=110, facecolor=bg)
    plt.close(fig)
    return path


if __name__ == "__main__":
    args = sys.argv[1:] or ["SPY", "QQQ"]
    if args[0].lower() == "dash":
        tick = [a.upper() for a in args[1:]] or ["SPY", "QQQ"]
        res = [read(t) for t in tick]
        for r in res:
            print(fmt(r))
            print()
        if len(res) == 2:
            print(agreement(*res))
        import os
        out = os.path.expanduser("~/desk/dashboard.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        print("DASHBOARD:", dashboard(res, out))
        sys.exit(0)
    if args[0].lower() == "plan":
        fill = float(args[1])
        hhmm = args[2] if len(args) > 2 else datetime.now().strftime("%H:%M")
        print(plan(fill, hhmm))
        sys.exit(0)
    results = [read(t.upper()) for t in args]
    for r in results:
        print(fmt(r))
        print()
    if len(results) == 2:
        print(agreement(*results))
