"""diagnostics.py - tests the suspected causes of the bad backtest BEFORE any rule is changed.

Input: a backtest database (the desk engine run day by day by backtest.py, every ledger and every candidate setup)
and the same 1m bars. Output: reports/diagnostics_<from>_<to>.md and .json.

What it checks (each is a hypothesis, not a conclusion):
  1. Coin-flip baseline: the same setups at the same times with the same exits, but a random direction (20 seeds),
     and the exact opposite direction. If random does as well as the signals, the problem is exits/costs, not signals.
  2. Exit breakdown from the real engine ledgers: count and P/L by exit rule, and how many losers were closed by the
     if-flat timer within ~5 minutes.
  3. Hold tests on the same entries: structure stop only (to 15:25), a VWAP trail after T1, and a v3.1-style runner,
     next to an approximation of the v3 exits.
  4. The stock's move vs the option result for the same trades (option P/L is MODELED here: delta/gamma/theta with
     the spread and fees, because no historical option quotes exist).
  5. Split halves by date (does a pattern show up in both?).
  6. Up vs down days for calls vs puts.
Counterfactual exits use 1m CLOSES (like the desk) and are an approximation of the live state machine. The live
paper ledgers (exits.py on Schwab quotes) are the authoritative record; this is for finding causes.
"""
import json
import math
import random
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import core
import indicators as I

HERE = Path(__file__).resolve().parent
DEFAULT_Q = {"bid": 2.00, "ask": 2.04, "delta": 0.45, "gamma": 0.05, "theta": -0.30}
POLICIES = ("v3_approx", "bracket", "hold", "vwap_trail", "v31_approx")


# ---------------------------------------------------------------- per-day features
FRAME_VERSION = "2026-10-30.diag2"     # v3.3: 2m features become available at the END of their bar (was: at its open)


def day_frame(m1, day, legacy=False):
    """1m regular-session frame with VWAP and the 2m MACD histogram as it was KNOWN at each 1m row.
    A 2m bar opening at 11:30 contains the 11:30 and 11:31 minutes, so its histogram exists only once the 11:31 minute
    has closed: it is placed on the 11:31 row (the row whose close is the decision time) and carried forward. The old
    version (legacy=True) placed it on the 11:30 row, one minute before it existed."""
    d = m1[m1.index.date == day].between_time("09:30", "15:59").copy()
    if not len(d):
        return None
    d["vwap"] = I.session_vwap(d).values
    b2, done = I.aggregate(d, 2, d.index[-1])
    M, S, H = I.macd(b2["Close"])
    if not len(H):
        d["hist2"] = float("nan")
        return d
    if legacy:
        d["hist2"] = H.reindex(d.index, method="ffill").values
        return d
    H = H[done.reindex(H.index).fillna(False).astype(bool).values]           # finished 2m bars only
    avail = H.copy()
    avail.index = H.index + pd.Timedelta(minutes=1)                         # last constituent minute of each 2m bar
    d["hist2"] = avail.reindex(d.index, method="ffill").values
    return d


def option_value(q, ds, minutes):
    """Modeled option bid after an underlying move ds (favorable > 0) and `minutes` of decay."""
    d = abs(q.get("delta") or 0.45)
    g = q.get("gamma") or 0.0
    th = abs(q.get("theta") or 0.0)
    return max(0.0, q["bid"] + d * ds + 0.5 * g * ds * ds - th * minutes / 390.0)


def simulate(c, d, policy, flip=False):
    """One candidate through one exit policy. c: {t (decision ISO), side, entry, stop, t1, q, flat_min}."""
    side = c["side"]
    entry, stop, t1 = c["entry"], c["stop"], c["t1"]
    if flip:
        side = "P" if side == "C" else "C"
        stop = entry + (entry - stop)
        t1 = entry - (t1 - entry) if t1 is not None else None
    up = side == "C"
    sgn = 1 if up else -1
    t0 = pd.Timestamp(c["t"])
    after = d[d.index >= t0]                       # bars that OPEN at or after the decision time (no look-ahead)
    if not len(after):
        return None
    q = c.get("q") or DEFAULT_Q
    k = core.policy()["v3"]["contract"]
    spread = (q["ask"] - q["bid"])
    slip = max(k["slippage_min"], spread * k["slippage_spread_frac"])
    cost_move = (spread + 2 * slip + 2 * k["fees_per_contract_side"] / 100) / max(abs(q.get("delta") or 0.45), 0.1)
    best, best_t, green_t, t1_done, trail = 0.0, t0, None, False, None
    exit_px, exit_t, why = None, None, None
    flat_min = c.get("flat_min", 5)
    lows, highs = [], []
    for ts, row in after.iterrows():
        close = float(row["Close"])
        fav = (close - entry) * sgn
        lows.append(float(row["Low"]))
        highs.append(float(row["High"]))
        mins = (ts - t0).total_seconds() / 60 + 1
        if ts.strftime("%H:%M") >= "15:25":
            exit_px, exit_t, why = float(row["Open"]), ts, "all out 15:25"
            break
        if not t1_done and ((close < stop) if up else (close > stop)):
            exit_px, exit_t, why = close, ts, "structure stop"
            break
        if fav > best + 0.02:
            best, best_t = fav, ts
        if green_t is None and fav >= cost_move:
            green_t = ts
        if policy == "hold":
            continue
        t1_hit = t1 is not None and ((close >= t1) if up else (close <= t1))
        if policy == "bracket":
            if t1_hit:
                exit_px, exit_t, why = close, ts, "T1"
                break
            continue
        if policy in ("vwap_trail", "v31_approx"):
            if t1_hit and not t1_done:
                t1_done = True
                stop = entry                           # runner: stop to breakeven (underlying)
            if policy == "v31_approx" and not t1_done and green_t is None and mins >= 15:
                exit_px, exit_t, why = close, ts, "if-flat 15 min"
                break
            if t1_done:
                vw = float(row["vwap"])
                sw = (min(lows[-4:-1]) if up else max(highs[-4:-1])) if len(lows) >= 4 else None
                lvl = vw if policy == "vwap_trail" else (max(vw, sw) if (sw is not None and up) else min(vw, sw) if sw is not None else vw)
                trail = lvl if trail is None else (max(trail, lvl) if up else min(trail, lvl))
                if (close < trail) if up else (close > trail):
                    exit_px, exit_t, why = close, ts, "trail"
                    break
                if (close < entry) if up else (close > entry):
                    exit_px, exit_t, why = close, ts, "breakeven stop"
                    break
            continue
        # v3_approx
        h = row["hist2"]
        if t1_hit:
            exit_px, exit_t, why = close, ts, "T1"
            break
        if green_t is None and mins >= flat_min:
            exit_px, exit_t, why = close, ts, f"if-flat {flat_min} min"
            break
        if green_t is not None and (ts - best_t).total_seconds() >= 600:
            exit_px, exit_t, why = close, ts, "stall 10 min"
            break
        hs = after.loc[:ts, "hist2"].dropna().drop_duplicates().iloc[-4:]
        if green_t is not None and len(hs) == 4 and fav > cost_move:
            dif = hs.diff().iloc[1:]
            if ((dif < 0).all() if up else (dif > 0).all()):
                exit_px, exit_t, why = close, ts, "momentum fade"
                break
    if exit_px is None:
        last = after.iloc[-1]
        exit_px, exit_t, why = float(last["Close"]), after.index[-1], "end of data"
    move = (exit_px - entry) * sgn
    risk = abs(entry - c["stop"])
    minutes = (exit_t - t0).total_seconds() / 60
    e_prem = q["ask"] + slip
    x_prem = max(0.0, option_value(q, move, minutes) - slip)
    opt = (x_prem - e_prem) * 100 - 2 * k["fees_per_contract_side"]
    return {"exit_t": exit_t.strftime("%H:%M"), "why": why, "stock_move": round(move, 4), "R": round(move / risk, 3) if risk else None,
            "option_pnl": round(opt, 2), "minutes": round(minutes, 1)}


def stats(pnls):
    n = len(pnls)
    if not n:
        return {"n": 0}
    w = [x for x in pnls if x > 0.5]
    l_ = [x for x in pnls if x < -0.5]
    eq = peak = dd = 0.0
    for x in pnls:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return {"n": n, "win_rate": round(100 * len(w) / n, 1), "avg_win": round(sum(w) / len(w), 2) if w else None,
            "avg_loss": round(sum(l_) / len(l_), 2) if l_ else None, "expectancy": round(sum(pnls) / n, 2),
            "net": round(sum(pnls), 2), "profit_factor": round(sum(w) / -sum(l_), 2) if l_ and sum(l_) < 0 else None,
            "max_drawdown": round(dd, 2), "small_sample": n < 30}


# ---------------------------------------------------------------- loading
def load_candidates(db, portfolio="research"):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute("SELECT * FROM candidates WHERE portfolio=? ORDER BY decision_t", (portfolio,))]
    c.close()
    out = []
    for r in rows:
        try:
            pl = json.loads(r["plan"]) if r["plan"] else {}
        except ValueError:
            pl = {}
        dg = pl.get("diagnostics") or pl
        entry = pl.get("entry_px") or dg.get("entry_px")
        stop = pl.get("stop_px") or dg.get("stop_px")
        t1 = pl.get("t1_px") or dg.get("t1_px")
        if entry is None or stop is None or not r["decision_t"]:
            continue
        q = {k: pl[k] for k in ("bid", "ask", "delta", "gamma", "theta") if pl.get(k) is not None}
        q = q if {"bid", "ask", "delta"} <= set(q) else None
        t = datetime.fromisoformat(r["decision_t"])
        win = core.window_for(t.strftime("%H:%M")) or {"flat_min": 5}
        out.append({"t": r["decision_t"], "day": r["date"], "ticker": r["ticker"], "side": r["side"], "family": r["family"],
                    "decision": r["decision"], "entry": float(entry), "stop": float(stop), "t1": float(t1) if t1 else None,
                    "q": q, "q_modeled_default": q is None, "flat_min": win["flat_min"]})
    return out


def ledger_exits(db):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    out = {}
    for r in c.execute("SELECT ledger, side, fill, realized, opened, closed, plan, setup FROM positions WHERE status='CLOSED'"):
        try:
            pl = json.loads(r["plan"]) if r["plan"] else {}
        except ValueError:
            pl = {}
        why = (pl.get("exit_reason") or "unknown")
        key = why.split(":")[0].split(" (")[0].split(" $")[0][:30]
        g = out.setdefault(r["ledger"], {"by_exit": defaultdict(lambda: {"n": 0, "net": 0.0}), "flat_losers_5min": 0, "losers": 0,
                                          "stock_vs_option": []})
        e = g["by_exit"][key]
        e["n"] += 1
        e["net"] = round(e["net"] + (r["realized"] or 0), 2)
        if (r["realized"] or 0) < -0.5:
            g["losers"] += 1
            try:
                held = (datetime.fromisoformat(r["closed"]) - datetime.fromisoformat(r["opened"])).total_seconds() / 60
            except Exception:
                held = None
            if key.startswith("IF FLAT") and held is not None and held <= 6:
                g["flat_losers_5min"] += 1
        if pl.get("entry_px") and pl.get("exit_px"):
            mv = (pl["exit_px"] - pl["entry_px"]) * (1 if r["side"] == "C" else -1)
            g["stock_vs_option"].append({"stock_move": round(mv, 3), "option": r["realized"]})
    c.close()
    for g in out.values():
        g["by_exit"] = {k: dict(v) for k, v in g["by_exit"].items()}
        sv = g["stock_vs_option"]
        g["stock_up_option_down"] = sum(1 for x in sv if x["stock_move"] > 0 and (x["option"] or 0) < 0)
        g["stock_moves_favorable_pct"] = round(100 * sum(1 for x in sv if x["stock_move"] > 0) / len(sv), 1) if sv else None
        g["stock_vs_option"] = sv[:200]
    return out


# ---------------------------------------------------------------- the report
def run(db, m1s, out_dir=None, seeds=20, label=None):
    out_dir = Path(out_dir or HERE / "reports")
    out_dir.mkdir(exist_ok=True)
    cands = load_candidates(db)
    frames = {}
    for c in cands:
        key = (c["ticker"], c["day"])
        if key not in frames:
            m1 = m1s.get(c["ticker"])
            frames[key] = day_frame(m1, datetime.fromisoformat(c["day"]).date()) if m1 is not None else None
    days = sorted({c["day"] for c in cands})
    mid = days[len(days) // 2] if days else None
    res = {"candidates": len(cands), "days": len(days), "from": days[0] if days else None, "to": days[-1] if days else None,
           "modeled_default_contract": sum(1 for c in cands if c["q_modeled_default"]), "policies": {}, "baselines": {},
           "by_family": {}, "halves": {}, "up_down": {}, "ledger_exits": ledger_exits(db),
           "notes": ["Counterfactual exits run on 1m closes and approximate the live exit rules.",
                     "Option P/L is MODELED (delta/gamma/theta + spread + fees); there is no historical option-quote data.",
                     "October 28 and the days used to design v3 are in-sample; read every pattern as a hypothesis."]}
    sims = {p: [] for p in POLICIES}
    for c in cands:
        d = frames.get((c["ticker"], c["day"]))
        if d is None:
            continue
        for p in POLICIES:
            r = simulate(c, d, p)
            if r:
                sims[p].append((c, r))
    for p, lst in sims.items():
        res["policies"][p] = {"option_modeled": stats([r["option_pnl"] for _, r in lst]),
                              "stock_R": stats([r["R"] for _, r in lst if r["R"] is not None]),
                              "exits": dict(pd.Series([r["why"] for _, r in lst]).value_counts()) if lst else {}}
    base = []
    for s in range(seeds):
        rnd = random.Random(1000 + s)
        pn = []
        for c in cands:
            d = frames.get((c["ticker"], c["day"]))
            if d is None:
                continue
            r = simulate(c, d, "v3_approx", flip=rnd.random() < 0.5)
            if r:
                pn.append(r["option_pnl"])
        base.append(stats(pn))
    wr = [b["win_rate"] for b in base if b.get("n")]
    ex = [b["expectancy"] for b in base if b.get("n")]
    res["baselines"]["coin_flip_v3_approx"] = {"seeds": seeds, "win_rate_mean": round(sum(wr) / len(wr), 1) if wr else None,
                                               "win_rate_sd": round(pd.Series(wr).std(), 1) if len(wr) > 1 else None,
                                               "expectancy_mean": round(sum(ex) / len(ex), 2) if ex else None}
    opp = []
    for c in cands:
        d = frames.get((c["ticker"], c["day"]))
        r = simulate(c, d, "v3_approx", flip=True) if d is not None else None
        if r:
            opp.append(r["option_pnl"])
    res["baselines"]["opposite_v3_approx"] = stats(opp)
    fam = defaultdict(list)
    for c, r in sims["v3_approx"]:
        fam[f"{c['family']} {'calls' if c['side'] == 'C' else 'puts'}"].append(r["option_pnl"])
    res["by_family"] = {k: stats(v) for k, v in sorted(fam.items())}
    for p in ("v3_approx", "hold"):
        h1 = [r["option_pnl"] for c, r in sims[p] if mid and c["day"] < mid]
        h2 = [r["option_pnl"] for c, r in sims[p] if mid and c["day"] >= mid]
        res["halves"][p] = {"first": stats(h1), "second": stats(h2), "split_at": mid}
    fam_h = {}
    for c, r in sims["v3_approx"]:
        k = f"{c['family']} {'calls' if c['side'] == 'C' else 'puts'}"
        fam_h.setdefault(k, {"first": [], "second": []})["first" if c["day"] < mid else "second"].append(r["option_pnl"])
    res["halves"]["by_family"] = {k: {"first": stats(v["first"]).get("expectancy"), "second": stats(v["second"]).get("expectancy"),
                                      "n": (len(v["first"]), len(v["second"]))} for k, v in fam_h.items()}
    dd = {}
    for (tk, day), d in frames.items():
        if d is not None and len(d):
            dd[(tk, day)] = "up" if float(d["Close"].iloc[-1]) > float(d["Open"].iloc[0]) else "down"
    ud = defaultdict(list)
    for c, r in sims["v3_approx"]:
        ud[f"{dd.get((c['ticker'], c['day']), '?')} day, {'calls' if c['side'] == 'C' else 'puts'}"].append(r["option_pnl"])
    res["up_down"] = {k: stats(v) for k, v in sorted(ud.items())}
    res["up_down_days"] = dict(pd.Series(list(dd.values())).value_counts()) if dd else {}
    label = label or f"{res['from']}_{res['to']}"
    (out_dir / f"diagnostics_{label}.json").write_text(json.dumps(res, indent=1, default=str))
    (out_dir / f"diagnostics_{label}.md").write_text(markdown(res))
    return res


def _s(st):
    if not st or not st.get("n"):
        return "no trades"
    return (f"{st['n']} trades, {st['win_rate']}% won, avg win {st['avg_win']}, avg loss {st['avg_loss']}, "
            f"expectancy {st['expectancy']}, PF {st['profit_factor']}, max DD {st['max_drawdown']}" + (" (small sample)" if st["small_sample"] else ""))


def markdown(r):
    L = [f"# Diagnostics {r['from']} to {r['to']}", "",
         f"{r['candidates']} setups on {r['days']} days. Option results are MODELED ({r['modeled_default_contract']} setups had no contract "
         "quote and use a default delta-0.45 contract). Exits are counterfactual on 1m closes.",
         f"These {r['candidates']} are diagnostic SETUPS, not paper executions, and the default-contract quotes are modeled, "
         f"not observed options data. Frame {FRAME_VERSION}: 2m features are used only after their bar has closed.", "",
         "## 1. Signals vs a coin flip (same setups, same times, v3-style exits)", ""]
    b = r["baselines"]
    L.append(f"- Signals: {_s(r['policies']['v3_approx']['option_modeled'])}")
    cf = b["coin_flip_v3_approx"]
    L.append(f"- Coin flip ({cf['seeds']} seeds): win rate {cf['win_rate_mean']}% (sd {cf['win_rate_sd']}), expectancy {cf['expectancy_mean']}")
    L.append(f"- Opposite direction: {_s(b['opposite_v3_approx'])}")
    L.append("- Reading: if the coin flip wins about as often as the signals, the low win rate comes from the exits and costs, not the direction.")
    L += ["", "## 2. Same entries, different exits", "", "| Exits | Option (modeled) | Stock, in R | Exit reasons |", "|---|---|---|---|"]
    for p, v in r["policies"].items():
        top = ", ".join(f"{k} {n}" for k, n in list(v["exits"].items())[:4])
        L.append(f"| {p} | {_s(v['option_modeled'])} | {_s(v['stock_R'])} | {top} |")
    L += ["", "## 3. Live engine ledgers: what closed the trades", ""]
    for led, g in r["ledger_exits"].items():
        parts = ", ".join(f"{k}: {v['n']} ({v['net']:+.0f})" for k, v in sorted(g["by_exit"].items(), key=lambda z: -z[1]["n"]))
        L.append(f"- **{led}**: {parts}. Losers closed by if-flat within ~5 min: {g['flat_losers_5min']} of {g['losers']}. "
                 f"Stock moved the right way on {g['stock_moves_favorable_pct']}% of trades; stock right but option lost: {g['stock_up_option_down']}.")
    L += ["", "## 4. By setup (v3-style exits)", ""]
    for k, v in r["by_family"].items():
        L.append(f"- {k}: {_s(v)}")
    L += ["", "## 5. Split halves (split at " + str(r["halves"].get("v3_approx", {}).get("split_at")) + ")", ""]
    for p in ("v3_approx", "hold"):
        h = r["halves"].get(p) or {}
        L.append(f"- {p}: first half {_s(h.get('first'))}; second half {_s(h.get('second'))}")
    for k, v in (r["halves"].get("by_family") or {}).items():
        L.append(f"  - {k}: expectancy {v['first']} then {v['second']} (n {v['n'][0]} / {v['n'][1]})")
    L += ["", "## 6. Up and down days", "", f"Days: {r.get('up_down_days')}"]
    for k, v in r["up_down"].items():
        L.append(f"- {k}: {_s(v)}")
    L += ["", "## Notes", ""] + [f"- {n}" for n in r["notes"]]
    return "\n".join(L)
