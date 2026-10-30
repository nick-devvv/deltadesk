"""matched_benchmarks.py - is a strategy better than random entries that face the SAME constraints?

For every strategy signal, a control entry is drawn at a random eligible minute in the same session, ticker, side
and clock window, with the same risk geometry (stop distance in ATR, target multiple, flat time) and the same costs.
A random time must itself be admissible as of that time (inside the window, a bar exists, not after the last entry).
Fixed seeds make every control path reproducible. Comparisons are PAIRED BY SESSION, zero-trade sessions included,
and intervals resample whole sessions (trades on one day are not independent). Holm's method adjusts p-values over
every variant that was tried, not only the ones that look good.
"""
import random


def stock_outcome(m1_day, entry_i, side, stop_dist, target_r=2.0, horizon_min=None, flat="15:25", cost_per_share=0.04):
    """Underlying outcome in R from bar index `entry_i` (entered at that bar's OPEN). Conservative path rules: a gap
    through the stop fills at the open; if a bar touches both stop and target, the stop counts first; flat at the
    15:25 bar's open, or at the horizon. Returns {r, why, exit_i} or None if no path exists (recorded as unknown)."""
    if entry_i is None or entry_i >= len(m1_day) or stop_dist <= 0:
        return None
    up = side == "C"
    e = float(m1_day["Open"].iloc[entry_i])
    stop = e - stop_dist if up else e + stop_dist
    tgt = e + target_r * stop_dist if up else e - target_r * stop_dist
    t0 = m1_day.index[entry_i]
    for j in range(entry_i, len(m1_day)):
        row, ts = m1_day.iloc[j], m1_day.index[j]
        hm = ts.strftime("%H:%M")
        if hm >= flat or (horizon_min is not None and (ts - t0).total_seconds() >= horizon_min * 60):
            x = float(row["Open"])
            return {"r": round(((x - e) if up else (e - x)) / stop_dist - cost_per_share / stop_dist, 4), "why": "time", "exit_i": j}
        o = float(row["Open"])
        if j > entry_i and ((o <= stop) if up else (o >= stop)):
            return {"r": round(((o - e) if up else (e - o)) / stop_dist - cost_per_share / stop_dist, 4), "why": "stop gap", "exit_i": j}
        hit_stop = (row["Low"] <= stop) if up else (row["High"] >= stop)
        hit_tgt = (row["High"] >= tgt) if up else (row["Low"] <= tgt)
        if hit_stop:
            return {"r": round(-1 - cost_per_share / stop_dist, 4), "why": "stop" + (" (ambiguous bar)" if hit_tgt else ""), "exit_i": j}
        if hit_tgt:
            return {"r": round(target_r - cost_per_share / stop_dist, 4), "why": "target", "exit_i": j}
    return None


def random_controls(signals, days, paths=50, seed=11, window=("09:45", "15:15"), **outcome_kw):
    """signals: [{session, ticker, side, stop_dist, entry_i}]; days: {(ticker, session): m1_day}. For each path, one
    control per signal at a uniformly random admissible minute of the same day/ticker/side. Returns a list of paths,
    each a list of {session, r} (None outcomes are kept as unknown and counted)."""
    rnd = random.Random(seed)
    out = []
    for _ in range(paths):
        path = []
        for s in signals:
            d = days.get((s["ticker"], s["session"]))
            if d is None:
                continue
            idx = [i for i, t in enumerate(d.index) if window[0] <= t.strftime("%H:%M") <= window[1] and i + 1 < len(d)]
            if not idx:
                continue
            i = rnd.choice(idx) + 1                       # decided at a bar close, entered at the next bar's open
            o = stock_outcome(d, i, s["side"], s["stop_dist"], **outcome_kw)
            path.append({"session": s["session"], "r": o["r"] if o else None})
        out.append(path)
    return out


def _by_session(rows, sessions):
    m = {d: [] for d in sessions}
    for r in rows:
        if r.get("r") is not None and r["session"] in m:
            m[r["session"]].append(r["r"])
    return m


def paired_difference(strategy_rows, control_paths, sessions, boots=2000, seed=5):
    """Per-session mean R of the strategy minus the average control path, over EVERY listed session (no trades = 0).
    Returns {mean_diff, ci95, p_value (one-sided, diff <= 0), n_sessions}."""
    sessions = sorted(sessions)
    s = _by_session(strategy_rows, sessions)
    ctl = [_by_session(p, sessions) for p in control_paths] or [{d: [] for d in sessions}]
    diffs = []
    for d in sessions:
        sv = sum(s[d]) / len(s[d]) if s[d] else 0.0
        cv = [sum(c[d]) / len(c[d]) if c[d] else 0.0 for c in ctl]
        diffs.append(sv - sum(cv) / len(cv))
    if not diffs:
        return {"n_sessions": 0, "note": "no sessions"}
    rnd = random.Random(seed)
    sims = sorted(sum(rnd.choice(diffs) for _ in diffs) / len(diffs) for _ in range(boots))
    mean = sum(diffs) / len(diffs)
    p = sum(1 for x in sims if x <= 0) / boots
    return {"mean_diff": round(mean, 4), "ci95": [round(sims[int(0.025 * boots)], 4), round(sims[int(0.975 * boots) - 1], 4)],
            "p_value": round(p, 4), "n_sessions": len(diffs)}


def holm(pvalues):
    """Holm step-down adjustment. pvalues: {name: p}. Returns {name: adjusted p} (monotone, capped at 1)."""
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    m, run, out = len(items), 0.0, {}
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = round(run, 4)
    return out
