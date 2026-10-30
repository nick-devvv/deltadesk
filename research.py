"""research.py - a reproducible SIGNAL study (stock moves only, no options) for registered experiments.

  python3 research.py --csv reports/backtest_inplay_bars_2026-09-22_2026-10-29.csv [--dev-end 2026-10-15] [--paths 50]

What it measures, for the registered definitions (config/specialists.json):
  BASE   ORB15 completed break: the first finished 1m close beyond the 09:30-09:44 range edge, decided at that bar's
         close (never before 09:45), entered at the NEXT bar's open; stop = the edge -/+ 0.05 x ATR14 (back inside);
         2R target; flat at 15:25. Also the move at 5 / 15 / 30 minutes.
  EXP-002 ORB15 first retest: after that break, the first bar that comes back within 0.05 ATR of the edge and closes
         beyond it again; same entry/stop/target rules.
Universe per day: symbols with >= 15 prior sessions, prior-14-day average volume >= 1M and price >= $20, known at
the open (point-in-time; the 125-name file itself is a fixed list, a survivorship/selection limitation reported).
Costs: $0.02 per share each way. Results are in R (risk = entry to stop). Ambiguous bars count the stop first.

Every result is compared with matched random entries (same ticker, day, side, window, stop distance, target and
costs; fixed seeds), paired by session with session-block intervals, and Holm-adjusted across the variants tried.
The Sep-Oct 2026 data was already used to design v3: both blocks are DEVELOPMENT/DIAGNOSTIC, not unseen evidence.
Each run is appended to the experiment attempt log. Writes reports/research_<label>.md and .json.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import core  # noqa: E402
import matched_benchmarks as MB  # noqa: E402
import walk_forward as WF  # noqa: E402

ET = core.ET
VERSION = "2026-10-30.research1"
ZONE_ATR = 0.05
COST = 0.04          # $ per share, round trip
HORIZONS = (5, 15, 30)


def load_csv(path):
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(ET)
    return {t: g.set_index("ts")[["Open", "High", "Low", "Close", "Volume"]].sort_index() for t, g in df.groupby("ticker")}


def _atr14(daily):
    if len(daily) < 15:
        return None
    h, l, c = daily["High"], daily["Low"], daily["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1).iloc[1:]
    a = tr.iloc[:14].mean()
    for x in tr.iloc[14:]:
        a = (a * 13 + x) / 14
    return float(a)


def day_inputs(m1):
    """Per session: the RTH 1m frame and point-in-time context from PRIOR sessions only."""
    r = m1.between_time("09:30", "15:59")
    days = sorted(set(r.index.date))
    daily = r.resample("1D").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
    daily.index = [d.date() for d in daily.index]
    out = {}
    for d in days:
        prior = daily[[x < d for x in daily.index]]
        if len(prior) < 15:
            out[d] = {"skip": "insufficient warmup (fewer than 15 prior sessions)"}
            continue
        atr = _atr14(prior.iloc[-30:])
        avgv = float(prior["Volume"].iloc[-14:].mean())
        px = float(prior["Close"].iloc[-1])
        if avgv < 1_000_000 or px < 20 or not atr:
            out[d] = {"skip": f"illiquid or cheap as of the open (avg vol {avgv:,.0f}, price {px:.2f})"}
            continue
        out[d] = {"m1": r[r.index.date == d], "atr": atr}
    return out


def _idx(m1d, hm):
    return next((i for i, t in enumerate(m1d.index) if t.strftime("%H:%M") >= hm), None)


def signals_for_day(m1d, atr):
    """BASE and RETEST signals for one ticker-day. Each: {kind, side, signal_i, entry_i, stop_dist, edge}."""
    rng = m1d[(m1d.index.strftime("%H:%M") >= "09:30") & (m1d.index.strftime("%H:%M") <= "09:44")]
    if len(rng) < 12:
        return [], "incomplete opening range (fewer than 12 of 15 minutes)"
    hi, lo = float(rng["High"].max()), float(rng["Low"].min())
    tol = ZONE_ATR * atr
    first = _idx(m1d, "09:44")                        # the 09:44 bar closes at 09:45: the first allowed decision
    last = _idx(m1d, "15:14")
    if first is None or last is None:
        return [], "no bars in the entry window"
    out = []
    brk = None
    for i in range(first, min(last + 1, len(m1d) - 1)):
        c = float(m1d["Close"].iloc[i])
        if c > hi or c < lo:
            side = "C" if c > hi else "P"
            brk = (i, side)
            break
    if not brk:
        return [], "no completed break in the window"
    i, side = brk
    edge = hi if side == "C" else lo
    stop = edge - tol if side == "C" else edge + tol
    e = float(m1d["Open"].iloc[i + 1])
    sd = (e - stop) if side == "C" else (stop - e)
    if sd > 0:
        out.append({"kind": "BASE", "side": side, "signal_i": i, "entry_i": i + 1, "stop_dist": sd, "edge": edge})
    for j in range(i + 1, min(last + 1, len(m1d) - 1)):
        row = m1d.iloc[j]
        back = (row["Low"] <= edge + tol) if side == "C" else (row["High"] >= edge - tol)
        inside = (row["Close"] < edge - tol) if side == "C" else (row["Close"] > edge + tol)
        if inside:
            break                                      # failed first: no retest of a broken break
        if back and ((row["Close"] > edge) if side == "C" else (row["Close"] < edge)):
            e2 = float(m1d["Open"].iloc[j + 1])
            sd2 = (e2 - stop) if side == "C" else (stop - e2)
            if sd2 > 0:
                out.append({"kind": "RETEST", "side": side, "signal_i": j, "entry_i": j + 1, "stop_dist": sd2, "edge": edge})
            break
    return out, None


def study(m1s, dev_end, paths=50, seed=11):
    rows, skipped, days_map = [], [], {}
    sessions = set()
    for t, m1 in m1s.items():
        for d, inp in day_inputs(m1).items():
            sessions.add(d)
            if "skip" in inp:
                skipped.append({"ticker": t, "session": str(d), "why": inp["skip"]})
                continue
            m1d = inp["m1"]
            days_map[(t, str(d))] = m1d
            sig, why = signals_for_day(m1d, inp["atr"])
            if why:
                skipped.append({"ticker": t, "session": str(d), "why": why})
            for s in sig:
                o = MB.stock_outcome(m1d, s["entry_i"], s["side"], s["stop_dist"], cost_per_share=COST)
                hz = {}
                for h in HORIZONS:
                    oh = MB.stock_outcome(m1d, s["entry_i"], s["side"], s["stop_dist"], target_r=1e9, horizon_min=h, cost_per_share=COST)
                    hz[f"r_{h}m"] = oh["r"] if oh else None
                rows.append(dict(s, ticker=t, session=str(d), signal_at=m1d.index[s["signal_i"]].strftime("%H:%M"),
                                 entry_at=m1d.index[s["entry_i"]].strftime("%H:%M"), r=o["r"] if o else None,
                                 why=o["why"] if o else "no price path (unknown, not imputed)", **hz))
    sess = sorted(str(x) for x in sessions)
    blocks = {"development": [d for d in sess if d <= dev_end], "later": [d for d in sess if d > dev_end]}
    res = {"version": VERSION, "dev_end": dev_end, "sessions": len(sess), "signals": len(rows), "skipped": len(skipped),
           "skip_reasons": _count(skipped), "variants": {}}
    pv = {}
    for kind in ("BASE", "RETEST"):
        kr = [r for r in rows if r["kind"] == kind]
        v = {}
        for bname, bs in blocks.items():
            br = [r for r in kr if r["session"] in bs]
            ctl = MB.random_controls([dict(r) for r in br], days_map, paths=paths, seed=seed, cost_per_share=COST)
            pd_ = MB.paired_difference(br, ctl, bs)
            v[bname] = {"n": len(br), "unknown": sum(1 for r in br if r["r"] is None), "summary": _summ(br),
                        "control": _summ([x for p in ctl for x in p]), "vs_control": pd_}
            if bname == "later" and pd_.get("p_value") is not None:
                pv[kind] = pd_["p_value"]
        v["walk_forward"] = WF.run(kr, lambda tr: {"fixed": True}, lambda te, p: _summ(te), test_size=5, min_train=10)
        res["variants"][kind] = v
    res["holm_later"] = MB.holm(pv) if pv else {}
    res["verdict"] = {k: ("NOT PROMOTED: no evidence of an edge over matched random entries" if
                          not (res["variants"][k]["later"]["vs_control"].get("ci95") and res["variants"][k]["later"]["vs_control"]["ci95"][0] > 0
                               and res["holm_later"].get(k, 1) < 0.05)
                          else "candidate for FORWARD paper testing only (this data is not unseen)") for k in res["variants"]}
    return res, rows, skipped


def _count(rows):
    out = {}
    for r in rows:
        k = r["why"].split(" (")[0]
        out[k] = out.get(k, 0) + 1
    return out


def _summ(rows):
    v = [r["r"] for r in rows if r.get("r") is not None]
    if not v:
        return {"n": 0, "note": "no outcomes: no win rate"}
    out = {"n": len(v), "avg_R": round(float(np.mean(v)), 3), "win_rate": round(100 * sum(1 for x in v if x > 0) / len(v), 1)}
    for h in HORIZONS:
        hv = [r[f"r_{h}m"] for r in rows if r.get(f"r_{h}m") is not None]
        if hv:
            out[f"avg_R_{h}m"] = round(float(np.mean(hv)), 3)
    return out


def markdown(res):
    L = [f"# Signal study ({res['version']})", "",
         f"{res['sessions']} sessions, {res['signals']} signals, {res['skipped']} ticker-days skipped. Stock moves in R after "
         f"${COST:.2f}/share costs; no options. Both blocks were already seen while designing v3: DIAGNOSTIC, not unseen.", "",
         "Skipped: " + ", ".join(f"{k} {n}" for k, n in res["skip_reasons"].items()), ""]
    for k, v in res["variants"].items():
        L.append(f"## {k}")
        for b in ("development", "later"):
            x = v[b]
            vc = x["vs_control"]
            L.append(f"- {b}: {x['summary']} | random control {x['control']} | paired vs control {vc}")
        L.append(f"- verdict: {res['verdict'][k]}")
        L.append("")
    L.append(f"Holm-adjusted p-values (later block, all variants tried in this run): {res['holm_later']}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--dev-end", default="2026-10-15")
    ap.add_argument("--paths", type=int, default=50)
    a = ap.parse_args(argv)
    m1s = load_csv(a.csv)
    res, rows, skipped = study(m1s, a.dev_end, a.paths)
    try:
        import strategy_registry as SR
        for k, eid in (("BASE", "INPLAY-ORB15-BASE-SIGNAL"), ("RETEST", "EXP-002-FIRST-RETEST")):
            SR.log_attempt(eid, "signal study", f"{min(r['session'] for r in rows) if rows else '-'}..{max(r['session'] for r in rows) if rows else '-'}",
                           {"dev_end": a.dev_end, "paths": a.paths, "zone_atr": ZONE_ATR, "cost": COST}, res["variants"].get(k))
    except Exception as e:
        print("attempt log failed:", e)
    out = HERE / "reports"
    out.mkdir(exist_ok=True)
    label = f"{date.today()}"
    (out / f"research_{label}.json").write_text(json.dumps({"result": res, "rows": rows, "skipped": skipped}, indent=1, default=str))
    (out / f"research_{label}.md").write_text(markdown(res))
    print(markdown(res))
    return res


if __name__ == "__main__":
    main()
