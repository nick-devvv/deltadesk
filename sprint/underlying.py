"""sprint/underlying.py - Layer 1 of the 2016-2023 history check (SPRINT_PLAN Amendment 5): the sprint's surviving entries
and filters on STOCK bars only, with no option model. Every number is a BACKTEST on Alpaca stock 1-minute bars (HIST =
2016-01-04..2024-01-31 unless a caller asks for another non-locked range). Research code: no network, no orders.

The strategies are hist_v1.json's blocks (the DEV runs' own entry, side and filters). Signals come from
sprint.entries.signals and filters from sprint.engine._filters_ok (VIXY 1-minute bars and VIXY daily closes as the
labeled VIX proxies), on stock-only DayContexts whose history starts before the period (indicators only). One position
at a time per strategy and symbol, as in the engine: a signal before the previous trade's exit bar is skipped (busy).

STOP strategies (fb, fb_or: calls, so a long stock position stands in; puts would be mirrored):
  entry   the open of the first bar after the signal bar (within ENTRY_WAIT = 3 minutes, else skipped) + $0.01
  stop    the signal's `invalid` level minus max($0.02, 0.05 x ATR(14, 1m) at the signal bar) (sim.stop_buffer), judged
          on finished 1-minute closes from the entry bar on; a close below it exits at the next bar's open - $0.01
  time    otherwise out at the close of the bar finishing at 15:25 (bar 354; 12:50 = bar 199 on early-close days)
          - $0.01; a signal at or after that bar is skipped
  R       entry fill - stop; R <= 0 (it opened at or below the stop) -> skipped and counted
  record  P/L in R and in %, MFE in R (best high from the entry bar through the exit decision bar, minus the entry
          fill, over R)
MOVE strategies (otm_put, otm_bounce and their twins; no stop):
  ref     the close of the signal bar (10:30 = bar 59, 11:00 = bar 89)
  moves   to the close at 15:25 (bar 354) and to the lowest low (puts) / highest high (calls) of bars ref+1..354, in %
          and in units of the remaining-day sigma = sigma_1m x sqrt(minutes from the end of the signal bar to 15:25),
          sigma_1m from sprint/modeled.sigma_1m (prior 20 sessions, at least 10); log moves
  large   z(15:25 close) <= -1.5 (puts) / >= +1.5 (calls). The extreme-based version is shown beside it.
Matched random entries: seeds 101-105, as sprint/engine._random_signals (same symbol, day and side; a random bar in the
setup's window; STOP strategies keep the signal's stop distance). Random day-skips (filtered MOVE strategies): drop as
many whole dates from the twin as the filter dropped, 2,000 draws; p = share of draws with a large-move rate >= the
filtered rate.
Pre-registered readings (SPRINT_PLAN Amendment 5):
  fb, fb_or    "signal holds": expectancy in R > 0 overall, > 0 in >= 6 of the 8 years 2016-2023, and above every one of
               the 5 matched-random seeds' expectancy
  otm_put      "tail holds": large-drop rate beats random day-skips (p < 0.10) and is above that year's twin rate in
               >= 5 of the 8 years (a year without filtered days is a miss)
  otm_bounce   "bounce holds": large-rise rate beats random day-skips (p < 0.10) and is above that year's twin rate in
               at least half of the years with >= 5 filtered days (at least 3 such years needed)
"""
import json
import math
import random
import statistics
import zlib
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from . import data, entries, report as R
from .engine import _filters_ok
from .modeled import sigma_1m
from .periods import HIST_STRETCHES, HIST_YEARS
from .sim import stop_buffer

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "sprint" / "specs" / "hist_v1.json"
HALF = 0.01
ENTRY_WAIT = 3
ALLOUT_BAR, EARLY_ALLOUT_BAR = 354, 199           # bars finishing at 15:25 / 12:50
LARGE = 1.5
SEEDS = (101, 102, 103, 104, 105)
SKIP_DRAWS, SKIP_SEED = 2000, 11
LABEL = "BACKTEST on Alpaca stock 1-minute bars (Layer 1: no option model)"


def strategies(spec_path=SPEC):
    """hist_v1's blocks as Layer-1 strategies: name, entry, side, filters, symbols, kind ('stop' or 'move'), twin."""
    from .engine import expand
    spec = json.loads(Path(spec_path).read_text())
    out = []
    for r in expand(spec):
        kind = "move" if r["entry"] in entries.TIME_ENTRIES else "stop"
        out.append({"name": r["block"], "entry": r["entry"], "side": r["side"], "filters": tuple(r["filters"]),
                    "symbols": tuple(r["symbols"]), "kind": kind, "run_id": r["run_id"]})
    for s in out:
        s["twin"] = next((t["name"] for t in out if s["filters"] and not t["filters"] and t["entry"] == s["entry"]
                          and t["side"] == s["side"]), None)
    return out


def allout_bar(ctx):
    return EARLY_ALLOUT_BAR if ctx.early else ALLOUT_BAR


def _last_close(ctx, i, lo):
    for k in range(i, lo, -1):
        if ctx.has_bar(k):
            return float(ctx.c[k]), k
    return None, None


def sim_stop(ctx, sig):
    """One STOP-strategy trade on the stock. Returns a dict with status TRADE or SKIP (+ reason)."""
    j, ab = sig.idx, allout_bar(ctx)
    up = sig.side == "C"
    sg = 1.0 if up else -1.0
    base = {"symbol": ctx.sym, "day": ctx.day.isoformat(), "side": sig.side, "signal_idx": j, "signal_price": sig.price}
    if j >= ab:
        return dict(base, status="SKIP", reason="signal at or after the all-out bar")
    if sig.invalid is None:
        return dict(base, status="SKIP", reason="setup has no invalidation level")
    e = next((k for k in range(j + 1, min(j + ENTRY_WAIT, ab - 1) + 1) if ctx.has_bar(k) and not math.isnan(ctx.o[k])), None)
    if e is None:
        return dict(base, status="SKIP", reason="no stock bar to enter in the 3 minutes after the signal")
    entry = float(ctx.o[e]) + sg * HALF
    a1 = ctx.atr1[j]
    stop = float(sig.invalid) - sg * stop_buffer(None if math.isnan(a1) else float(a1))
    risk = sg * (entry - stop)
    if risk <= 0:
        return dict(base, status="SKIP", reason="entry at or beyond the stop")
    dec, fill_i, fill, why = None, None, None, None
    for i in range(e, ab):
        if ctx.has_bar(i) and sg * (float(ctx.c[i]) - stop) < 0:
            dec = i
            k = next((k for k in range(i + 1, ab + 1) if ctx.has_bar(k) and not math.isnan(ctx.o[k])), None)
            if k is not None:
                fill_i, fill, why = k, float(ctx.o[k]) - sg * HALF, "STOP (1m close through the level, next open)"
            break
    if fill is None:
        px, k = _last_close(ctx, ab, e - 1)
        if px is None:
            return dict(base, status="SKIP", reason="no stock bar to exit on")
        dec = dec if dec is not None else k
        fill_i, fill = ab, px - sg * HALF
        why = why or (f"ALL OUT {'12:50' if ctx.early else '15:25'}" if dec == k else "STOP (no later bar: all-out price)")
    seg = slice(e, dec + 1)
    best = np.nanmax(ctx.h[seg]) if up else np.nanmin(ctx.l[seg])
    return dict(base, status="TRADE", invalid=float(sig.invalid), entry_idx=e, entry=round(entry, 4), stop=round(stop, 4), risk=round(risk, 4),
                exit_idx=fill_i, exit=round(fill, 4), exit_reason=why, r=round(sg * (fill - entry) / risk, 4),
                pct=round(sg * (fill / entry - 1) * 100, 4), mfe_r=round(sg * (float(best) - entry) / risk, 4))


def measure_move(ctx, sig, sigma):
    """One MOVE-strategy observation: moves from the signal bar's close to 15:25 and to the extreme, in % and sigma."""
    j, ab = sig.idx, allout_bar(ctx)
    up = sig.side == "C"
    base = {"symbol": ctx.sym, "day": ctx.day.isoformat(), "side": sig.side, "signal_idx": j, "signal_price": sig.price}
    if j >= ab:
        return dict(base, status="SKIP", reason="signal at or after the all-out bar")
    if sigma is None:
        return dict(base, status="SKIP", reason="no sigma_1m (fewer than 10 prior sessions)")
    ref = float(ctx.c[j])
    px, k = _last_close(ctx, ab, j)
    if px is None:
        return dict(base, status="SKIP", reason="no stock bar after the signal")
    seg = slice(j + 1, ab + 1)
    ext = float(np.nanmax(ctx.h[seg]) if up else np.nanmin(ctx.l[seg]))
    sd = sigma * math.sqrt(ab - j)
    zc, ze = math.log(px / ref) / sd, math.log(ext / ref) / sd
    large = zc >= LARGE if up else zc <= -LARGE
    large_ext = ze >= LARGE if up else ze <= -LARGE
    return dict(base, status="TRADE", entry_idx=j, exit_idx=ab, ref=round(ref, 4), close_1525=round(px, 4), extreme=round(ext, 4),
                minutes_left=ab - j, sigma_rem_pct=round(sd * 100, 4), move_pct=round((px / ref - 1) * 100, 4),
                ext_pct=round((ext / ref - 1) * 100, 4), z_close=round(zc, 4), z_ext=round(ze, 4), large=bool(large),
                large_ext=bool(large_ext))


def _random_signals(ctx, entry, matched, seed):
    """engine._random_signals for Layer 1: (side, dist) pairs -> random signals in the setup's window."""
    lo, hi = entries.ENTRY_WINDOWS.get(entry, (15, 344))
    out = []
    for n, (side, dist) in enumerate(matched):
        rnd = random.Random(zlib.crc32(f"{seed}|{ctx.sym}|{ctx.day}|{n}".encode()))
        i = rnd.randint(lo, hi)
        while i <= hi and not ctx.has_bar(i):
            i += 1
        if i > hi:
            continue
        px = float(ctx.c[i])
        inv = None if dist is None else (px - dist if side == "C" else px + dist)
        out.append(entries.Signal(f"random:{entry}", ctx.sym, ctx.day, side, i, px, inv, {}))
    return out


def run_day(ctx, strat, sigma, sigs=None):
    """All Layer-1 results of one strategy on one (symbol, day): (records, skips Counter). sigs: given signals
    (matched random entries; the strategy's filters still apply at the random bar, as in the engine's random runs)."""
    skips = Counter()
    if sigs is None:
        sigs = entries.signals(ctx, strat["entry"], strat["side"])
    out, last_exit, count = [], -1, 0
    rr = {"filters": strat["filters"]}
    for sig in sorted(sigs, key=lambda s: s.idx):
        if sig.idx < last_exit:
            skips["busy: one position at a time"] += 1
            continue
        why = _filters_ok(rr, ctx, sig, count)
        if why:
            skips[why] += 1
            continue
        t = sim_stop(ctx, sig) if strat["kind"] == "stop" else measure_move(ctx, sig, sigma)
        if t["status"] != "TRADE":
            skips[t["reason"]] += 1
            continue
        t["strategy"] = strat["name"]
        last_exit = t["exit_idx"]
        count += 1
        out.append(t)
    return out, skips


def run(series_by_sym, aux, a, b, strats, seeds=SEEDS, progress=None):
    """Layer 1 over [a, b] (trades only inside it). series_by_sym: {symbol: data.Series} with history before a.
    Returns {strategy: {"trades", "skips", "random": {seed: trades}, "sessions": [(symbol, day)]}}."""
    res = {s["name"]: {"trades": [], "skips": Counter(), "random": {sd: [] for sd in seeds}, "sessions": []} for s in strats}
    for sym, series in sorted(series_by_sym.items()):
        days = [d for d in series.days if a <= d <= b]
        for n, day in enumerate(days):
            ctx = data.DayContext(series, day, {}, None, aux=aux)
            sg = sigma_1m(series, day)
            for s in strats:
                if sym not in s["symbols"]:
                    continue
                res[s["name"]]["sessions"].append((sym, day.isoformat()))
                tr, sk = run_day(ctx, s, sg)
                res[s["name"]]["trades"] += tr
                res[s["name"]]["skips"].update(sk)
                if not tr:
                    continue
                matched = [(t["side"], abs(t["signal_price"] - t["invalid"]) if t.get("invalid") is not None else None) for t in tr]
                for sd in seeds:
                    rt, _ = run_day(ctx, s, sg, sigs=_random_signals(ctx, s["entry"], matched, sd))
                    res[s["name"]]["random"][sd] += rt
            if progress and (n % 250 == 0 or n == len(days) - 1):
                progress(f"  layer 1 {sym} {day} ({n + 1}/{len(days)} sessions)")
    return res


# ---------------------------------------------------------------- summaries and the pre-registered readings
def _in(t, lo, hi):
    return lo.isoformat() <= t["day"] <= hi.isoformat()


def r_metrics(trades):
    """Metrics in R for STOP trades (R.metrics on the R multiple), plus % and MFE."""
    tr = sorted(trades, key=lambda t: (t["day"], t["entry_idx"], t["symbol"]))
    m = R.metrics(tr, "r")
    if not tr:
        return m
    m["exp_pct"] = round(statistics.mean(t["pct"] for t in tr), 4)
    mfe = [t["mfe_r"] for t in tr]
    m["mfe_r_median"] = round(statistics.median(mfe), 3)
    m["mfe_share"] = {f">= {k}R": round(sum(1 for x in mfe if x >= k) / len(mfe), 3) for k in (1, 2, 3)}
    m["exit_reasons"] = dict(Counter(t["exit_reason"].split(" (")[0] for t in tr).most_common())
    return m


def move_metrics(trades):
    if not trades:
        return {"n": 0}
    zc = [t["z_close"] for t in trades]
    return {"n": len(trades), "large_rate": round(sum(t["large"] for t in trades) / len(trades), 4),
            "large_ext_rate": round(sum(t["large_ext"] for t in trades) / len(trades), 4),
            "z_close_mean": round(statistics.mean(zc), 4), "move_pct_median": round(statistics.median(t["move_pct"] for t in trades), 4),
            "ext_pct_median": round(statistics.median(t["ext_pct"] for t in trades), 4),
            "sigma_rem_pct_median": round(statistics.median(t["sigma_rem_pct"] for t in trades), 4)}


def _split(trades, fn):
    out = {}
    for name, lo, hi in HIST_STRETCHES:
        out[name] = fn([t for t in trades if _in(t, lo, hi)])
    return out


def day_skip_test(filtered, twin, draws=SKIP_DRAWS, seed=SKIP_SEED):
    """Random day-skips for a filtered MOVE strategy: drop as many whole dates from the twin as the filter dropped;
    p = share of draws whose large-move rate is >= the filtered rate."""
    if not filtered or not twin:
        return None
    rate = sum(t["large"] for t in filtered) / len(filtered)
    by = defaultdict(list)
    for t in twin:
        by[t["day"]].append(bool(t["large"]))
    days = sorted(by)
    k = len(days) - len({t["day"] for t in filtered})
    if k <= 0:
        return {"skipped_days": 0, "p_value": None, "filtered_rate": round(rate, 4)}
    rnd = random.Random(seed)
    ge, rates = 0, []
    for _ in range(draws):
        drop = set(rnd.sample(days, k))
        xs = [x for d in days if d not in drop for x in by[d]]
        r = sum(xs) / len(xs) if xs else 0.0
        rates.append(r)
        ge += r >= rate - 1e-12
    return {"skipped_days": k, "p_value": round(ge / draws, 4), "filtered_rate": round(rate, 4),
            "random_skip_rate_mean": round(statistics.mean(rates), 4), "draws": draws}


def summarize(res, strats, seeds=SEEDS):
    """Per strategy: overall, by year / stretch / symbol, matched random, skip test and the pre-registered reading."""
    out = {}
    by_name = {s["name"]: s for s in strats}
    for s in strats:
        x = res[s["name"]]
        tr = x["trades"]
        o = {"kind": s["kind"], "entry": s["entry"], "side": s["side"], "filters": list(s["filters"]), "twin": s.get("twin"),
             "skips": dict(x["skips"].most_common()), "sessions": len(x["sessions"])}
        if s["kind"] == "stop":
            o["overall"] = r_metrics(tr)
            ses = sorted({d for _, d in x["sessions"]})
            o["overall"]["ci95_r"] = R.bootstrap_ci([{"day": t["day"], "pnl": t["r"]} for t in tr], ses) if tr else None
            o["by_stretch"] = _split(tr, r_metrics)
            o["by_symbol"] = {sym: r_metrics([t for t in tr if t["symbol"] == sym]) for sym in sorted({t["symbol"] for t in tr})}
            o["random"] = {str(sd): r_metrics(x["random"][sd]) for sd in seeds}
            o["reading"] = reading_stop(o)
        else:
            o["overall"] = move_metrics(tr)
            o["by_stretch"] = _split(tr, move_metrics)
            o["by_symbol"] = {sym: move_metrics([t for t in tr if t["symbol"] == sym]) for sym in sorted({t["symbol"] for t in tr})}
            o["random"] = {str(sd): move_metrics(x["random"][sd]) for sd in seeds}
            tw = s.get("twin")
            if tw:
                twin_tr = res[tw]["trades"]
                o["skip_test"] = day_skip_test(tr, twin_tr)
                o["twin_by_stretch"] = _split(twin_tr, move_metrics)
                o["reading"] = reading_move(o, s["side"])
        out[s["name"]] = o
    return out


def reading_stop(o):
    """fb / fb_or: 'signal holds' (SPRINT_PLAN Amendment 5)."""
    ov = o["overall"]
    exp = ov.get("expectancy")
    yrs = [str(y) for y in HIST_YEARS]
    up = sum(1 for y in yrs if ((o["by_stretch"].get(y) or {}).get("expectancy") or 0) > 0)
    rnd = [v.get("expectancy") for v in o["random"].values()]
    rnd_ok = exp is not None and bool(rnd) and all(r is not None and exp > r for r in rnd)
    items = [("expectancy in R > 0 overall", (exp or 0) > 0),
             (f"expectancy in R > 0 in at least 6 of the 8 years 2016-2023 ({up} of 8)", up >= 6),
             ("above every matched-random seed's expectancy (" + ", ".join(R.fmt(r, 3) for r in rnd) + ")", rnd_ok)]
    return {"name": "signal holds", "items": items, "verdict": all(ok for _, ok in items)}


def reading_move(o, side):
    """otm_put: 'tail holds'; otm_bounce (calls): 'bounce holds' (SPRINT_PLAN Amendment 5)."""
    st, tw = o["by_stretch"], o["twin_by_stretch"]
    p = (o.get("skip_test") or {}).get("p_value")
    yrs = [str(y) for y in HIST_YEARS]
    above = lambda y: (st.get(y) or {}).get("n", 0) > 0 and (st[y].get("large_rate") or 0) > ((tw.get(y) or {}).get("large_rate") or 0)
    if side == "P":
        n_up = sum(1 for y in yrs if above(y))
        items = [(f"large-drop rate beats random day-skips, p < 0.10 (p = {p})", p is not None and p < 0.10),
                 (f"above that year's twin rate in at least 5 of the 8 years ({n_up} of 8)", n_up >= 5)]
        name = "tail holds"
    else:
        elig = [y for y in yrs if (st.get(y) or {}).get("n", 0) >= 5]
        n_up = sum(1 for y in elig if above(y))
        items = [(f"large-rise rate beats random day-skips, p < 0.10 (p = {p})", p is not None and p < 0.10),
                 (f"at least 3 years with 5+ filtered days ({len(elig)}: {', '.join(elig) or 'none'})", len(elig) >= 3),
                 (f"above that year's twin rate in at least half of them ({n_up} of {len(elig)})", bool(elig) and 2 * n_up >= len(elig))]
        name = "bounce holds"
    return {"name": name, "items": items, "verdict": all(ok for _, ok in items)}


def render(summ, a, b, meta):
    """The Layer-1 report (markdown)."""
    L = [f"# Layer 1: the stock signal on 2016-2023 history ({a} to {b})\n",
         f"Generated {meta.get('at')} on `{meta.get('host')}`. Code: sprint/underlying.py (SPRINT_PLAN Amendment 5). "
         f"Strategies: `{meta.get('spec')}` (sha256 `{meta.get('spec_sha', '')[:12]}`).\n",
         f"**Every number is a {LABEL}**, {a} to {b}: data these rules were never tuned on (they were chosen on DEV, Aug 2024 "
         "to Jun 2026). No option prices: fb/fb_or are measured as long stock with a stock stop (in R), the far "
         "out-of-the-money ideas as the stock's move after the entry time (in remaining-day sigmas). Costs: $0.01 per share "
         "each way. Not financial advice: evidence for Nick to decide.\n",
         f"Data: {meta.get('coverage')}. History from {meta.get('warm_from')} feeds indicators only.\n"]
    L.append("## Pre-registered readings\n")
    for name, o in summ.items():
        g = o.get("reading")
        if not g:
            continue
        L.append(f"### {name}: {g['name']}: **{'YES' if g['verdict'] else 'NO'}**\n")
        for nm, ok in g["items"]:
            L.append(f"- [{'x' if ok else ' '}] {nm}")
        L.append("")
    for name, o in summ.items():
        L.append(f"## {name} ({o['entry']}, {'calls' if o['side'] == 'C' else 'puts'}"
                 + (f", filters {'+'.join(o['filters'])}" if o["filters"] else "") + ")\n")
        if o["kind"] == "stop":
            ov = o["overall"]
            L.append(f"Overall: {ov.get('trades', 0)} trades, win {R.fmt(100 * (ov.get('win_rate') or 0), 1)}%, avg win "
                     f"{R.fmt(ov.get('avg_win'))}R, avg loss {R.fmt(ov.get('avg_loss'))}R, expectancy **{R.fmt(ov.get('expectancy'), 3)}R** "
                     f"({R.fmt(ov.get('exp_pct'), 3)}% a trade), PF {R.fmt(ov.get('profit_factor'))}, max DD {R.fmt(ov.get('max_dd'))}R, "
                     f"expectancy CI95 {ov.get('ci95_r')}R, median MFE {R.fmt(ov.get('mfe_r_median'))}R, MFE reached "
                     f"{ov.get('mfe_share')}. Exits: {ov.get('exit_reasons')}.\n")
            cols = [("stretch", lambda kv: kv[0]), ("trades", lambda kv: kv[1].get("trades")), ("win%", lambda kv: None if kv[1].get("win_rate") is None else 100 * kv[1]["win_rate"]),
                    ("avg win R", lambda kv: kv[1].get("avg_win")), ("avg loss R", lambda kv: kv[1].get("avg_loss")),
                    ("exp R", lambda kv: kv[1].get("expectancy")), ("PF", lambda kv: kv[1].get("profit_factor")),
                    ("max DD R", lambda kv: kv[1].get("max_dd")), ("median MFE R", lambda kv: kv[1].get("mfe_r_median"))]
            L.append(R.table(list(o["by_stretch"].items()) + [(f"symbol {k}", v) for k, v in o["by_symbol"].items()]
                             + [(f"random seed {k}", v) for k, v in o["random"].items()], cols))
        else:
            ov = o["overall"]
            word = "drop" if o["side"] == "P" else "rise"
            L.append(f"Overall: {ov.get('n', 0)} days, large {word} (15:25 close beyond 1.5 remaining-day sigma) "
                     f"**{R.fmt(100 * (ov.get('large_rate') or 0), 2)}%**, by the extreme {R.fmt(100 * (ov.get('large_ext_rate') or 0), 2)}%, "
                     f"mean z {R.fmt(ov.get('z_close_mean'), 3)}, median move {R.fmt(ov.get('move_pct_median'), 3)}%, median "
                     f"remaining-day sigma {R.fmt(ov.get('sigma_rem_pct_median'), 3)}%.\n")
            if o.get("skip_test"):
                t = o["skip_test"]
                L.append(f"Random day-skips of the twin `{o['twin']}` ({t['skipped_days']} dates dropped, {t.get('draws')} draws): "
                         f"p = {t['p_value']} (filtered rate {t['filtered_rate']}, random-skip mean {t.get('random_skip_rate_mean')}).\n")
            tw = o.get("twin_by_stretch") or {}
            cols = [("stretch", lambda kv: kv[0]), ("days", lambda kv: kv[1].get("n")),
                    (f"large {word} %", lambda kv: None if kv[1].get("large_rate") is None else 100 * kv[1]["large_rate"]),
                    ("by extreme %", lambda kv: None if kv[1].get("large_ext_rate") is None else 100 * kv[1]["large_ext_rate"]),
                    ("mean z", lambda kv: kv[1].get("z_close_mean")), ("median move %", lambda kv: kv[1].get("move_pct_median")),
                    ("twin large %", lambda kv: None if (tw.get(kv[0]) or {}).get("large_rate") is None else 100 * tw[kv[0]]["large_rate"])]
            L.append(R.table(list(o["by_stretch"].items()) + [(f"symbol {k}", v) for k, v in o["by_symbol"].items()]
                             + [(f"random minute, seed {k}", v) for k, v in o["random"].items()], cols))
        L.append(f"Skipped signals: {o['skips'] or 'none'}.\n")
    L.append(f"Labels: {LABEL}, HIST (never used to choose these rules). Not financial advice.\n")
    return "\n".join(L)
