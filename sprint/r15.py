"""sprint/r15.py - round 15 (SPRINT_PLAN "Round 15 pre-registration", written 2026-11-04 before any round-15 code, pull or
run): G1 sector trend-momentum, G2 Donchian channel trend, G3 alpha rotation, P1 the near-winners (T6, A2, RSI2) as one
portfolio (SELECTED IN-SAMPLE), P2 = P1 with round 14's risk control; plus the one-time L1 confirmation
(docs/research/R15_L1_SPEC.md). Research only; reads files; no network, no orders. Every number is a BACKTEST.
"""
import itertools
import math

import numpy as np
import pandas as pd

from . import r12daily as R12
from . import r14 as R14
from .report import deflated_sharpe

TRIALS = ("G1", "G2", "G3", "P1", "P2")
N_ROUND, N_PRIOR = 5, 11_312
ALPHA = 0.05 / N_ROUND
COST = R14.COST
TOP, DON_IN, DON_OUT, ALPHA_N = 3, 50, 25, 252
POOL = ("A1", "A2", "C2", "E1", "T6", "RSI2")
L1_EXCESS_MIN, L1_DD_MIN = -0.02, -0.08
SEEDS = {"shift": 151, "noise": 152}
LABEL = "BACKTEST (Yahoo daily ETF bars)"
NAMES = {"G1": "sector trend-momentum", "G2": "Donchian channel trend", "G3": "sector alpha rotation",
         "P1": "T6 + A2 + RSI2 portfolio (SELECTED IN-SAMPLE)", "P2": "P1 with vol target and drawdown brake (SELECTED IN-SAMPLE)"}


def sec_returns(m):
    return np.column_stack([R14.cc_ret(m, s) if m.has(s) else np.zeros(m.n) for s in R12.SECTORS])


# ------------------------------------------------------------------ G1
def g1_decisions(m):
    rows = R14.month_ends(m)
    sma = {s: R12.per_segment(m, m.c[s], lambda x: R12.sma(x, R14.SMA_N)) for s in R12.SECTORS if m.has(s)}
    mom = {s: R12.per_segment(m, m.c[s], lambda x: R12._ret_n(x, R14.MOM_N)) for s in R12.SECTORS if m.has(s)}
    vecs = np.zeros((len(rows), len(R12.SECTORS)))
    for j, d in enumerate(rows):
        ok = [(-mom[s][d], i) for i, s in enumerate(R12.SECTORS) if s in sma and np.isfinite(sma[s][d]) and np.isfinite(mom[s][d])
              and m.c[s][d] > sma[s][d]]
        for _, i in sorted(ok)[:TOP]:
            vecs[j, i] = 1.0 / TOP
    return rows, vecs


# ------------------------------------------------------------------ G3
def g3_decisions(m):
    rows = R14.month_ends(m)
    R = sec_returns(m)
    spy = R14.cc_ret(m, "SPY")
    vecs = np.zeros((len(rows), len(R12.SECTORS)))
    for j, d in enumerate(rows):
        a = d - ALPHA_N + 1
        if a < 1 or m.seg[a - 1] != m.seg[d] or (a > 0 and m.seg[a] != m.seg[d]):
            continue
        x = spy[a:d + 1] - m.cash[a:d + 1]
        sc = []
        for i, s in enumerate(R12.SECTORS):
            if not m.has(s) or not np.isfinite(m.c[s][a - 1]):
                continue
            y = R[a:d + 1, i] - m.cash[a:d + 1]
            beta = np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1)
            alpha = y.mean() - beta * x.mean()
            if alpha > 0:
                sc.append((-alpha, i))
        for _, i in sorted(sc)[:TOP]:
            vecs[j, i] = 1.0 / TOP
    return rows, vecs


# ------------------------------------------------------------------ G2
def g2_states(m):
    """(sessions, 8) bool: on/off at each close (prior-window channels, restart per segment)."""
    st = np.zeros((m.n, len(R14.MA_ASSETS)), bool)
    for i, s in enumerate(R14.MA_ASSETS):
        if not m.has(s):
            continue
        c = m.c[s]
        for a, b in m.segments():
            x = pd.Series(c[a:b])
            hi = x.shift(1).rolling(DON_IN, min_periods=DON_IN).max().to_numpy()
            lo = x.shift(1).rolling(DON_OUT, min_periods=DON_OUT).min().to_numpy()
            on = False
            for k in range(b - a):
                v = x.iloc[k]
                if not on and np.isfinite(hi[k]) and v >= hi[k]:
                    on = True
                elif on and np.isfinite(lo[k]) and v <= lo[k]:
                    on = False
                st[a + k, i] = on
    return st


def g2_vecs(m, st):
    vol = np.column_stack([R12.per_segment(m, m.c[s], R14.rolling_vol) if m.has(s) else np.full(m.n, np.nan) for s in R14.MA_ASSETS])
    V = np.zeros(st.shape)
    cur = np.zeros(st.shape[1])
    for t in range(m.n):
        ok = np.isfinite(vol[t]) & (vol[t] > 0)
        slot = np.zeros(st.shape[1])
        if ok.any():
            slot[ok] = (1.0 / vol[t][ok]) / (1.0 / vol[t][ok]).sum()
        for i in range(st.shape[1]):
            if st[t, i] and cur[i] == 0:
                cur[i] = slot[i]
            elif not st[t, i]:
                cur[i] = 0.0
        V[t] = cur
    return np.arange(m.n), V


# ------------------------------------------------------------------ trials
def g_trial(m, name):
    if name == "G2":
        st = g2_states(m)
        rows, vecs = g2_vecs(m, st)
        R = R14.ma_returns(m)
    else:
        rows, vecs = (g1_decisions if name == "G1" else g3_decisions)(m)
        R = sec_returns(m)

    def rebuild(delays=None, extra=0.0, vecs_override=None):
        return R14.run_alloc(m, R14.W_from(m.n, rows, vecs if vecs_override is None else vecs_override, delays), R, COST, extra)[0]
    return rebuild(), rows, vecs, rebuild


def pool(m):
    cand = R14.candidates(m)
    rows, vecs = R14.ma_decisions(m, "A2")
    r, H, tr = R14.run_alloc(m, R14.W_from(m.n, rows, vecs), R14.ma_returns(m), COST)
    cand["A2"] = {"r": r, "expo": H.sum(axis=1), "traded": tr}
    return cand


def p_series(m, cand, names=("T6", "A2", "RSI2"), extra=0.0, risk=False):
    r = np.mean([cand[k]["r"] - extra * cand[k]["traded"] for k in names], axis=0)
    return R14.risk_control(m, r, COST + extra) if risk else r


def evaluate(m, n_luck=None, boot_draws=None):
    n_luck = R14.LUCK_N if n_luck is None else n_luck
    pm = R14.mask(m, *R14.PASS)
    spy = R12.series_stats(R14.cc_ret(m, "SPY"), m.cash, pm)
    cand = pool(m)
    out = {"label": LABEL, "alpha": ALPHA, "n_trials_total": N_PRIOR + N_ROUND, "benchmark_spy": spy,
           "pool": {k: R12.series_stats(cand[k]["r"], m.cash, pm) for k in POOL}, "trials": {}}
    series = {}
    for name in TRIALS:
        if name[0] == "G":
            r, rows, vecs, rebuild = g_trial(m, name)
            base = R14.sharpe(r, m.cash, pm)
            g = np.random.default_rng(SEEDS["shift"])
            idx = np.flatnonzero(pm[rows])
            lo = 252 if name == "G2" else 12
            sh = []
            for _ in range(n_luck):
                v = vecs.copy()
                v[idx] = np.roll(vecs[idx], int(g.integers(lo, max(lo + 1, len(idx) - lo))), axis=0)
                sh.append(R14.sharpe(rebuild(vecs_override=v), m.cash, pm))
            luck3 = {"kind": "shifted decisions", "p95": float(np.percentile(sh, 95)), "median": float(np.median(sh))}
            g = np.random.default_rng(SEEDS["noise"])
            noisy = np.array([R14.sharpe(rebuild(delays=g.integers(0, R14.NOISE_DELAY_ALLOC + 1, len(rows)), extra=g.uniform(0, R14.NOISE_EXTRA)),
                                         m.cash, pm) for _ in range(n_luck)])
        else:
            risk = name == "P2"
            r = p_series(m, cand, risk=risk)
            base = R14.sharpe(r, m.cash, pm)
            combos = [R14.sharpe(p_series(m, cand, c, risk=risk), m.cash, pm) for c in itertools.combinations(POOL, 3)]
            luck3 = {"kind": "3-of-6 portfolios", "p95": float(np.percentile(combos, 95)), "median": float(np.median(combos)),
                     "n": len(combos)}
            g = np.random.default_rng(SEEDS["noise"])
            noisy = np.array([R14.sharpe(p_series(m, cand, extra=g.uniform(0, R14.NOISE_EXTRA), risk=risk), m.cash, pm)
                              for _ in range(n_luck)])
        luck3["pass"] = bool(base > luck3["p95"])
        ex = r[pm] - m.cash[pm]
        p, ci = R12.block_bootstrap(ex) if boot_draws is None else R12.block_bootstrap(ex, draws=boot_draws)
        st = R12.series_stats(r, m.cash, pm)
        kept = R14.kept_without_best_months(r, m.cash, pm, m.index)
        items = {f"1 p < {ALPHA:.4f} vs cash": p < ALPHA,
                 "2 drawdown smaller than SPY's": st["max_dd"] > spy["max_dd"],
                 f"3 beats 95% of {luck3['kind']}": luck3["pass"],
                 "4 Sharpe > 0 in 95% of noisy runs": float(np.mean(noisy > 0)) >= R14.NOISE_SHARE,
                 "5 keeps 50% without its 10 best months": (kept or 0) >= R14.OUTLIER_KEEP}
        out["trials"][name] = {"name": NAMES[name], "stats": st, "p": p,
                               "info": {w: R12.series_stats(r, m.cash, R14.mask(m, a, b)) for w, (a, b) in R14.INFO.items()},
                               "luck": {"3": luck3, "noise_share_above_0": float(np.mean(noisy > 0)), "noise_worst": float(noisy.min()),
                                        "kept": kept},
                               "items": items, "pass": all(items.values()), "sized_20dd": R14.sized_to_dd(m, r, pm)}
        series[name] = r
    srs = [float((series[n][pm] - m.cash[pm]).mean() / (series[n][pm] - m.cash[pm]).std()) for n in TRIALS]
    sr_var = float(np.var(srs, ddof=1))
    for n in TRIALS:
        out["trials"][n]["deflated_sharpe"] = deflated_sharpe(list(series[n][pm] - m.cash[pm]), N_PRIOR + N_ROUND, sr_var)
    out["verdicts"] = {n: out["trials"][n]["pass"] for n in TRIALS}
    return out, series


# ------------------------------------------------------------------ L1 confirmation
CONFIRM = ("T6", "A2", "RSI2", "P1", "P2")


def confirm(m, l1):
    """m: bars covering DEV + L1 as one segment; l1: (start, end). Scored on L1 only."""
    mk = R14.mask(m, *l1)
    cand = pool(m)
    ser = {"T6": cand["T6"]["r"], "A2": cand["A2"]["r"], "RSI2": cand["RSI2"]["r"],
           "P1": p_series(m, cand), "P2": p_series(m, cand, risk=True), "SPY": R14.cc_ret(m, "SPY")}
    out = {"label": "BACKTEST on L1 (out-of-sample, one-time)", "window": [str(l1[0]), str(l1[1])], "rules": {}}
    for k, r in ser.items():
        x, c = r[mk], m.cash[mk]
        eq = np.cumprod(1.0 + x)
        excess = float(eq[-1] / np.prod(1.0 + c) - 1.0)
        dd = float((eq / np.maximum.accumulate(eq) - 1.0).min())
        row = {"sessions": int(mk.sum()), "total": float(eq[-1] - 1.0), "excess_over_cash": excess, "max_dd": dd}
        if k != "SPY":
            row["verdict"] = "OK" if (excess > L1_EXCESS_MIN and dd > L1_DD_MIN) else "BROKE"
        out["rules"][k] = row
    return out


# ------------------------------------------------------------------ report
def _p(x, n=1):
    return "-" if x is None else f"{x * 100:.{n}f}%"


def _f(x, n=2):
    return "-" if x is None else f"{x:.{n}f}"


def report_md(ev, note=""):
    L = ["# Round 15 results", "", f"Label: {ev['label']}. {note}", "",
         f"Pass bar: p < {ev['alpha']:.4f} plus luck checks 2-5. Trials so far, all rounds: {ev['n_trials_total']:,}.", "",
         "| Trial | Rule | Verdict | p | Sharpe | CAGR | Max DD | Failed items |", "|---|---|---|---|---|---|---|---|"]
    for n, t in ev["trials"].items():
        s = t["stats"]
        failed = ", ".join(k.split(" ")[0] for k, v in t["items"].items() if not v) or "none"
        L.append(f"| {n} | {t['name']} | {'PASS' if t['pass'] else 'FAIL'} | {t['p']:.4f} | {_f(s['sharpe'])} | {_p(s['cagr'])} | "
                 f"{_p(s['max_dd'])} | {failed} |")
    b = ev["benchmark_spy"]
    L += ["", f"SPY buy-and-hold on PASS: Sharpe {_f(b['sharpe'])}, CAGR {_p(b['cagr'])}, max DD {_p(b['max_dd'])}.", "",
          "## Luck checks", "", "| Trial | Item 3 bar (95th pct) | Noisy runs with Sharpe > 0 | Kept without 10 best months | Sized to -20% DD: CAGR | Deflated Sharpe |",
          "|---|---|---|---|---|---|"]
    for n, t in ev["trials"].items():
        lk = t["luck"]
        L.append(f"| {n} | {_f(lk['3']['p95'])} ({lk['3']['kind']}) | {_p(lk['noise_share_above_0'], 0)} | {_p(lk['kept'], 0)} | "
                 f"{_p(t['sized_20dd']['cagr'])} at {t['sized_20dd']['k']:.2f}x | {_f(t['deflated_sharpe'], 3)} |")
    L += ["", "## Information windows (not used for pass)", "", "| Trial | EARLY Sharpe | EARLY max DD | DEV Sharpe | DEV max DD |", "|---|---|---|---|---|"]
    for n, t in ev["trials"].items():
        e, d = t["info"].get("EARLY"), t["info"].get("DEV")
        L.append(f"| {n} | {_f(e and e['sharpe'])} | {_p(e and e['max_dd'])} | {_f(d and d['sharpe'])} | {_p(d and d['max_dd'])} |")
    L += ["", "## Pool on PASS (for item 3 of P1/P2)", "", "| Rule | Sharpe | CAGR | Max DD |", "|---|---|---|---|"]
    for k, s in ev["pool"].items():
        L.append(f"| {k} | {_f(s['sharpe'])} | {_p(s['cagr'])} | {_p(s['max_dd'])} |")
    return "\n".join(L) + "\n"


def confirm_md(c):
    L = ["# Round 15 L1 confirmation", "", f"Label: {c['label']}. Window {c['window'][0]}..{c['window'][1]}. "
         "About 85 sessions: a does-it-break check, not proof.", "",
         "| Rule | Sessions | Return | Excess over cash | Max DD | Verdict |", "|---|---|---|---|---|---|"]
    for k, r in c["rules"].items():
        L.append(f"| {k} | {r['sessions']} | {_p(r['total'])} | {_p(r['excess_over_cash'])} | {_p(r['max_dd'])} | {r.get('verdict', 'benchmark')} |")
    return "\n".join(L) + "\n"
