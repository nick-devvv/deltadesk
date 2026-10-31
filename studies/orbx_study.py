"""ORBX-15-5 historical study (underlying only). v3.5.

    python3 studies/orbx_study.py BARS.csv [MORE.csv ...] --out docs/studies/ORBX_STUDY.md

What it does, exactly:
  * Every ticker-session that the existing ORB15 research admits (research.day_inputs: 15 prior sessions of warmup,
    average volume >= 1M, price >= $20) is run through orb_retest.run() on its completed 5-minute candles - the same
    function the live desk uses. Parameters are the module's PROVISIONAL defaults, fixed before this study; nothing
    is tuned here.
  * Each ENTRY CONFIRMED episode enters at the open of the first 1m bar after the retest candle closed (a proxy for the
    next quote; live entries need a real quote dated after R + latency) and is scored, in R of the initial stop, under
    five exits: swing trail, ATR trail, the desk's fixed 2R yardstick, an OR-midpoint stop with 1R (day-trader-skill),
    and hold-to-15:25. $0.04/share round-trip cost. A 1m bar touching stop and target counts as the stop.
  * Baselines on the SAME sessions: (a) the frozen ORB15 BASE signal (research.signals_for_day: first 1m close beyond
    the 15-minute range, next-bar entry) under the fixed 2R yardstick, (b) matched random controls: 20 random entries
    per signal, same session/ticker/side/stop distance, fixed 2R.
  * Uncertainty: a session-clustered bootstrap (trades on one day move together), 4,000 resamples, seed 7.
  * Split: earlier 2/3 of sessions vs the later 1/3, reported separately (nothing was fitted, so both are tests).
OPTIONS PROFITABILITY IS NOT MEASURED HERE (no historical option quotes). Stock R is not option P/L.
"""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import core  # noqa: E402
import matched_benchmarks as MB  # noqa: E402
import orb_retest as O  # noqa: E402
import research  # noqa: E402

COST = 0.04


def load(paths):
    frames = []
    for p in paths:
        d = pd.read_csv(p)
        d["ts"] = pd.to_datetime(d["ts"], utc=True).dt.tz_convert(core.ET)
        frames.append(d)
    d = pd.concat(frames)
    out = {}
    for t, g in d.groupby("ticker"):
        g = g.drop_duplicates("ts").set_index("ts").sort_index()[["Open", "High", "Low", "Close", "Volume"]]
        out[t] = g
    return out


def cluster_ci(rows, key="r", boots=4000, seed=7):
    by = {}
    for r in rows:
        if r.get(key) is not None:
            by.setdefault(r["session"], []).append(r[key])
    days = list(by)
    if not days:
        return None, None, None
    allv = [v for d in days for v in by[d]]
    mean = float(np.mean(allv))
    rng = random.Random(seed)
    ms = []
    for _ in range(boots):
        pick = [by[rng.choice(days)] for _ in days]
        flat = [v for p in pick for v in p]
        ms.append(float(np.mean(flat)))
    ms.sort()
    return round(mean, 3), round(ms[int(0.025 * boots)], 3), round(ms[int(0.975 * boots)], 3)


def max_dd(rs):
    eq, peak, dd = 0.0, 0.0, 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 2)


def summarize(rows, key="r"):
    vals = [r[key] for r in rows if r.get(key) is not None]
    missing = sum(1 for r in rows if r.get(key) is None)
    if not vals:
        return {"n": 0, "missing": missing}
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v <= 0]
    m, lo, hi = cluster_ci(rows, key)
    return {"n": len(vals), "missing": missing, "sessions": len({r["session"] for r in rows if r.get(key) is not None}),
            "win_pct": round(100 * len(wins) / len(vals), 1), "avg_r": m, "ci95": [lo, hi], "median_r": round(float(np.median(vals)), 3),
            "avg_win": round(float(np.mean(wins)), 3) if wins else None, "avg_loss": round(float(np.mean(losses)), 3) if losses else None,
            "sum_r": round(sum(vals), 2), "max_dd_r": max_dd([r[key] for r in sorted(rows, key=lambda x: (x["session"], x.get("t", ""))) if r.get(key) is not None])}


def study(m1s, universe_name):
    ep_rows, old_rows, states = [], [], {}
    sessions = set()
    for t, m1 in sorted(m1s.items()):
        inputs = research.day_inputs(m1)
        days = sorted(inputs)
        for d in days:
            inp = inputs[d]
            if "skip" in inp:
                continue
            m1d = inp["m1"]
            sessions.add(str(d))
            prior_days = [x for x in days if x < d][-2:]
            prior = []
            for pdd in prior_days:
                pm = m1[(m1.index.date == pdd)]
                if len(pm):
                    prior += O.candles(pm)
            res = O.run(m1d, t, prior_candles=prior)
            for e in res["episodes"]:
                states[e["state"]] = states.get(e["state"], 0) + 1
                if e["state"] != "ENTRY CONFIRMED":
                    continue
                i = O.entry_index(m1d, e)
                row = {"ticker": t, "session": str(d), "side": e["side"], "t": e["R"]["close_time"][11:16], "episode": e["id"],
                       "gap": e["gap"], "entry_i": i}
                ok, why = O.entry_check(e, float(m1d["Open"].iloc[i]), pd.Timestamp(e["entry_after"])) if i is not None else (False, "no bar")
                row["chase_ok"] = ok
                row["chase_why"] = why
                a = MB.arrays(m1d)
                for k in O.TRAILS:
                    o = O.trail_exit(m1d, i, e, k, cost_per_share=COST) if ok else None
                    row[k] = o["r"] if o else None
                    row[k + "_why"] = o["why"] if o else ("skipped: " + why if not ok else "no outcome")
                if ok:
                    sd = (float(m1d["Open"].iloc[i]) - e["stop"]) * (1 if e["side"] == "C" else -1)
                    row["stop_atr5"] = round(sd / e["atr"], 3) if e.get("atr") else None
                    row["cost_r"] = round(COST / sd, 3) if sd > 0 else None
                    seed = int(hashlib.sha1(e["id"].encode()).hexdigest()[:8], 16)
                    row["ctl"], row["ctl_n"] = MB.control_mean(a, e["side"], sd, paths=20, seed=seed, cost_per_share=COST)
                ep_rows.append(row)
            sig, _why = research.signals_for_day(m1d, inp["atr"])
            for s in sig:
                if s["kind"] != "BASE":
                    continue
                o = MB.stock_outcome(m1d, s["entry_i"], s["side"], s["stop_dist"], cost_per_share=COST)
                a = MB.arrays(m1d)
                ctl, n = MB.control_mean(a, s["side"], s["stop_dist"], paths=20, seed=int(hashlib.sha1(f"{t}|{d}".encode()).hexdigest()[:8], 16), cost_per_share=COST)
                old_rows.append({"ticker": t, "session": str(d), "side": s["side"], "t": m1d.index[s["signal_i"]].strftime("%H:%M"),
                                 "fixed2r": o["r"] if o else None, "ctl": ctl})
    ss = sorted(sessions)
    cut = ss[int(len(ss) * 2 / 3)] if ss else None
    traded = [r for r in ep_rows if r["chase_ok"]]
    out = {"universe": universe_name, "sessions": len(ss), "first": ss[0] if ss else None, "last": ss[-1] if ss else None,
           "split_at": cut, "episode_states": states, "entries_confirmed": len(ep_rows),
           "skipped_by_chase_gate": sum(1 for r in ep_rows if not r["chase_ok"]), "orbx": {}, "orbx_later_third": {},
           "orbx_vs_controls": {}, "old_orb15_base": summarize(old_rows, "fixed2r"),
           "old_orb15_controls": summarize(old_rows, "ctl")}
    for k in O.TRAILS:
        out["orbx"][k] = summarize(traded, k)
        out["orbx_later_third"][k] = summarize([r for r in traded if cut and r["session"] >= cut], k)
    out["orbx_controls_2r"] = summarize(traded, "ctl")
    sa = [r["stop_atr5"] for r in traded if r.get("stop_atr5") is not None]
    cr = [r["cost_r"] for r in traded if r.get("cost_r") is not None]
    out["stop_and_cost"] = {"median_stop_atr5": round(float(np.median(sa)), 3) if sa else None,
                            "median_cost_r": round(float(np.median(cr)), 3) if cr else None,
                            "stop_gap_losses": sum(1 for r in traded if str(r.get("fixed2r_why", "")).startswith("stop gap"))}
    diff = [dict(r, d=r["fixed2r"] - r["ctl"]) for r in traded if r.get("fixed2r") is not None and r.get("ctl") is not None]
    out["orbx_vs_controls"]["fixed2r_minus_controls"] = summarize(diff, "d")
    od = [dict(r, d=r["fixed2r"] - r["ctl"]) for r in old_rows if r.get("fixed2r") is not None and r.get("ctl") is not None]
    out["old_vs_controls"] = summarize(od, "d")
    return out, ep_rows, old_rows


def md(res_list, variations):
    L = ["# ORBX-15-5 study (underlying only, provisional parameters)", "",
         "Stock moves in R of the initial stop, $0.04/share round trip, session-clustered 95% intervals. Options profit is "
         "NOT measured (no historical option quotes). Parameters were fixed in orb_retest.py before this run; "
         f"{variations} exit variations and 1 entry definition were evaluated, nothing was tuned.", ""]
    for r in res_list:
        L += [f"## {r['universe']}: {r['sessions']} sessions ({r['first']} to {r['last']}), later third from {r['split_at']}", "",
              f"Episodes by final state: {json.dumps(r['episode_states'])}. ENTRY CONFIRMED {r['entries_confirmed']}, "
              f"skipped by the anti-chasing check at the entry proxy {r['skipped_by_chase_gate']}.", "",
              "| Exit | n | win % | avg R [95% CI] | median R | avg win | avg loss | sum R | max DD (R) | later third avg R (n) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for k in O.TRAILS:
            s, s2 = r["orbx"][k], r["orbx_later_third"][k]
            if not s.get("n"):
                L.append(f"| {k} | 0 | | | | | | | | |")
                continue
            L.append(f"| {k} | {s['n']} | {s['win_pct']} | {s['avg_r']} [{s['ci95'][0]}, {s['ci95'][1]}] | {s['median_r']} | {s['avg_win']} | "
                     f"{s['avg_loss']} | {s['sum_r']} | {s['max_dd_r']} | {s2.get('avg_r')} ({s2.get('n', 0)}) |")
        c, d = r["orbx_controls_2r"], r["orbx_vs_controls"]["fixed2r_minus_controls"]
        o, oc, od = r["old_orb15_base"], r["old_orb15_controls"], r["old_vs_controls"]
        sc = r.get("stop_and_cost") or {}
        L += ["", f"Initial stop: median {sc.get('median_stop_atr5')} x ATR5 from the entry; the $0.04 round-trip cost is a median "
              f"{sc.get('median_cost_r')} R per trade; {sc.get('stop_gap_losses')} fixed-2R losses gapped through the stop on a 1m open. "
              "Average losses exceed 1R mainly because the cost is charged in R (a tight stop makes $0.04 a large share of R), "
              "and partly from those gaps.",
              f"Matched random controls for the ORBX entries (fixed 2R): avg R {c.get('avg_r')} (n {c.get('n', 0)}). "
              f"ORBX fixed-2R minus its controls: {d.get('avg_r')} [{(d.get('ci95') or [None, None])[0]}, {(d.get('ci95') or [None, None])[1]}].",
              f"Frozen ORB15 BASE on the same sessions (fixed 2R): n {o.get('n', 0)}, win {o.get('win_pct')}%, avg R {o.get('avg_r')} "
              f"{o.get('ci95')}; its controls {oc.get('avg_r')}; difference {od.get('avg_r')} {od.get('ci95')}.", ""]
    L += ["## How to read this", "",
          "An interval that includes 0 means the sample can't tell the strategy from zero (or from its random controls). "
          "Small n per exit is expected: the sequence (break, independent candle, retest) is rare by design. None of this "
          "qualifies ORBX for anything; it starts as a separate paper-research ledger and needs forward, later-dated "
          "evidence that beats matched controls after costs."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--out", default=str(ROOT / "docs" / "studies" / "ORBX_STUDY.md"))
    ap.add_argument("--core", default="SPY,QQQ")
    a = ap.parse_args()
    m1s = load(a.csv)
    core_t = set(a.core.split(","))
    res = []
    for name, sel in (("SPY and QQQ (the ORBX paper ledger's instruments)", {t: m for t, m in m1s.items() if t in core_t}),
                      ("Individual stocks (signal-only observation: ORB never authorizes a stock entry without news)",
                       {t: m for t, m in m1s.items() if t not in core_t})):
        if sel:
            r, rows, old = study(sel, name)
            res.append(r)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(md(res, len(O.TRAILS)))
    import release
    man, src = release.manifest("orbx_study", {"params": O.DEFAULTS, "inputs": [Path(x).name for x in a.csv],
                                               "input_sha256": {Path(x).name: release.sha256_file(Path(x)) for x in a.csv}})
    Path(a.out).with_suffix(".json").write_text(json.dumps({"version": O.VERSION, "params": O.DEFAULTS, "manifest": man,
                                                            "source_sha256": src, "results": res}, indent=1, default=str))
    with open(a.out, "a") as f:
        f.write(f"\nRun manifest {man['manifest_id']} (release {man['release']}, source digest {man['source_digest'][:16]}, "
                f"inputs {', '.join(Path(x).name for x in a.csv)}).\n")
    print(json.dumps([{k: r[k] for k in ("universe", "sessions", "entries_confirmed", "episode_states")} for r in res], indent=1))


if __name__ == "__main__":
    main()
