"""sprint/r14.py - round 14: five families from *151 Trading Strategies* plus a walk-forward learner (SPRINT_PLAN "Round 14
pre-registration", written 2026-11-04 before any round-14 code, pull or run; vault Research/2026-11-04-round14-prereg.md).
Research only: reads files tools/sprint_r14.py wrote; no network, no orders. Every number is a BACKTEST.

ETF family (Yahoo daily bars, sprint/r12daily.Market):
  Allocation engine (A, E, T6, the learner): dividend-adjusted close-to-close returns; weights decided at the close of day t
    are traded at the close of day t+1 and earn from day t+2; weights fixed between rebalances; COST per side on traded
    weight; uninvested weight earns cash; indicators restart per segment; no return across the L2 gap.
  A1-A3 multi-asset trend (151 s4.6), SPY EFA EEM TLT IEF GLD DBC VNQ, month-end: on = 252-session return > 0 and close >
    200-session SMA (adjusted closes). A1 1/8 per on asset. A2 slots w = (1/sigma63) / sum over assets with a sigma, off
    slots in cash. A3 among on assets w = (R252/sigma63) / sum, each capped at 0.5 (the excess in cash).
  E1 bond trend: month-end; TLT if its close > its 200-session SMA, else SHY. E2: IEF if its 252-session return > the
    T-bill's compounded over the same sessions, else cash. (Builder's reading: "while" = checked at month ends, as the rest
    of the allocation family.)
  C1-C3 IBS (151 s4.4), SPY QQQ IWM DIA at 1/4 each, IBS = (close - low) / (high - low): C1 IBS < 0.2 -> buy next open, sell
    that close. C2 IBS < 0.2 -> buy next open; sell at the open after the first close with IBS > 0.8 or once 5 sessions are
    held. C3 = C2 with close > 200-session SMA (split-adjusted) at the signal. A position open at a segment's last close is
    sold at that close. Daily returns are built from the trade list (entry day open->close, full days close->close, an
    exit at an open from the prior close).
  F1/F2 learner over candidates A1, C2, E1, T6 (round 12's rule on this engine) and RSI2 (Amendment 12's F1 on the round
    12 engine, 1/10 per ETF). Month-end: eligible = at least 24 calendar months since the candidate's first exposure; score
    = annualized Sharpe of its daily excess returns over the prior 36 calendar months (from its first exposure on); hold the
    top 2 at 1/2 (ties: candidate order); one session late; COST on switches. F2 = F1 x exposure x_t = min(1, 0.08 /
    (63-session stdev of F1 through t-1 x sqrt(252))), halved while F2's equity through t-1 is below 90% of its running
    peak until it is back to 95%; COST on exposure changes. Controls F0 (all eligible, equal weight) and F0r (F0 with F2's
    risk control) are information only.
French family (Ken French industries, sprint/r13ff.Data): B1 the 3 industries with the lowest stdev of daily returns over the
  prior 12 calendar months, month-end, one session late; B2 = B1 while round 13's trend filter is on, else T-bills.

Pass, A/C/E/F on PASS 2008-01-02..2024-01-31 at COST: 1 one-sided p < 0.05/12 for mean daily excess over cash > 0
  (r12daily.block_bootstrap); 2 max drawdown smaller than buy-and-hold SPY's; 3 A/E: Sharpe above the 95th percentile of
  1,000 versions with month-end decisions circularly shifted by a random 12+ months inside PASS; C: mean net trade return
  above the 95th percentile of 1,000 random-entry draws (same symbol, holding length and exit type); F: Sharpe above the
  95th percentile of 1,000 random selectors (2 random eligible candidates a month; F2's draws get F2's risk control); 4
  Sharpe over cash > 0 in at least 95% of 1,000 runs with random delays (A/E/F: each rebalance 0-3 extra sessions; C: each
  entry and exit 0-1 session later) and 0-20 bps extra cost per side for the run (F: on its switches and its candidates'
  traded weight); 5 keeps at least 50% of PASS excess return without its 10 best months (C: 50% of net trade P/L without
  its 10 best trades). B on 1927-07-01..1997-12-31: round 13's items with 0.05/12.
"""
import math
import statistics
from datetime import date

import numpy as np
import pandas as pd

from . import r12daily as R12
from . import r13ff as R13
from .report import deflated_sharpe

MA_ASSETS = ("SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ")
IBS_ETFS = ("SPY", "QQQ", "IWM", "DIA")
SYMBOLS = tuple(sorted(set(MA_ASSETS) | set(IBS_ETFS) | set(R12.RSI2_ETFS) | set(R12.SECTORS) | {"SHY"}))
PASS = (date(2008, 1, 2), date(2024, 1, 31))
INFO = {"EARLY": (date(2000, 1, 3), date(2007, 12, 31)), "DEV": (date(2024, 8, 1), date(2026, 6, 30))}
COST = 0.0010
N_ROUND, N_PRIOR = 12, 11_300
ALPHA = 0.05 / N_ROUND
TRIALS = ("A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "E1", "E2", "F1", "F2")
ETF_TRIALS = ("A1", "A2", "A3", "C1", "C2", "C3", "E1", "E2", "F1", "F2")
CANDIDATES = ("A1", "C2", "E1", "T6", "RSI2")
MOM_N, SMA_N, VOL_N, A3_CAP = 252, 200, 63, 0.5
IBS_LO, IBS_HI, IBS_MAX_HOLD = 0.2, 0.8, 5
LEARN_LOOKBACK_M, LEARN_MIN_M, LEARN_TOP = 36, 24, 2
F2_VOL, F2_BRAKE, F2_RELEASE = 0.08, 0.90, 0.95
LUCK_N, NOISE_SHARE, RANDOM_PCT = 1_000, 0.95, 95
NOISE_DELAY_ALLOC, NOISE_DELAY_TRADE, NOISE_EXTRA = 3, 1, 0.0020
OUTLIER_TOP, OUTLIER_KEEP = 10, 0.50
SEEDS = {"shift": 141, "noise": 142, "random": 143, "picks": 144, "filter": 145}
LABEL = "BACKTEST (Yahoo daily ETF bars; Ken French industry returns for B)"


# ------------------------------------------------------------------ shared helpers
def mask(m, a, b):
    return np.array([a <= x <= b for x in m.days])


def month_ends(m):
    return np.flatnonzero(R12.month_end_mask(m))


def ym(m):
    return np.array([x.year * 12 + x.month for x in m.days])


def cc_ret(m, sym):
    c = m.c[sym]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.r_[0.0, c[1:] / c[:-1] - 1.0]
    r[np.r_[True, m.seg[1:] != m.seg[:-1]]] = 0.0
    return np.nan_to_num(r)


def W_from(n, rows, vecs, delays=None):
    """Weights held from each decision row until the next one (decision j moved later by delays[j] sessions)."""
    W = np.zeros((n, vecs.shape[1]))
    cur = np.zeros(vecs.shape[1])
    last = 0
    for j, row in enumerate(rows):
        r = min(n - 1, int(row) + (int(delays[j]) if delays is not None else 0))
        r = max(r, last)
        W[last:r] = cur
        cur, last = vecs[j], r
    W[last:] = cur
    return W


def run_alloc(m, W, R, cost=COST, extra=0.0):
    """Holdings on day t = W[t - 2]; trades at the close of day t pay (cost + extra) x traded weight."""
    H = np.zeros_like(W)
    H[2:] = W[:-2]
    port = (H * R).sum(axis=1) + (1.0 - H.sum(axis=1)) * m.cash
    traded = np.r_[np.abs(H[1:] - H[:-1]).sum(axis=1), 0.0]
    return port - (cost + extra) * traded, H, traded


def sharpe(r, cash, mk):
    ex = r[mk] - cash[mk]
    sd = ex.std(ddof=1)
    return float(ex.mean() / sd * math.sqrt(252)) if sd > 0 else 0.0


def kept_without_best_months(r, cash, mk, index, top=OUTLIER_TOP):
    ex = pd.Series(r[mk] - cash[mk], index=index[mk])
    mo = (1.0 + ex).groupby([ex.index.year, ex.index.month]).prod() - 1.0
    tot = float(mo.sum())
    return float((tot - mo.nlargest(top).sum()) / tot) if tot > 0 else None


# ------------------------------------------------------------------ A: multi-asset trend
def rolling_vol(x, n=VOL_N):
    """Stdev of the last n daily returns (NaN until n returns exist)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.r_[np.nan, x[1:] / x[:-1] - 1.0]
    return pd.Series(r).rolling(n, min_periods=n).std().to_numpy(float)


def ma_inputs(m):
    out = {}
    for s in MA_ASSETS:
        if not m.has(s):
            continue
        c = m.c[s]
        out[s] = {"c": c, "mom": R12.per_segment(m, c, lambda x: R12._ret_n(x, MOM_N)),
                  "sma": R12.per_segment(m, c, lambda x: R12.sma(x, SMA_N)),
                  "vol": R12.per_segment(m, c, rolling_vol)}
    return out


def ma_decisions(m, kind, inp=None):
    inp = ma_inputs(m) if inp is None else inp
    rows = month_ends(m)
    vecs = np.zeros((len(rows), len(MA_ASSETS)))
    for j, d in enumerate(rows):
        on, vol, mom = np.zeros(len(MA_ASSETS), bool), np.full(len(MA_ASSETS), np.nan), np.full(len(MA_ASSETS), np.nan)
        for i, s in enumerate(MA_ASSETS):
            if s not in inp:
                continue
            x = inp[s]
            vol[i], mom[i] = x["vol"][d], x["mom"][d]
            on[i] = bool(np.isfinite(x["mom"][d]) and np.isfinite(x["sma"][d]) and x["mom"][d] > 0 and x["c"][d] > x["sma"][d])
        w = np.zeros(len(MA_ASSETS))
        if kind == "A1":
            w[on] = 1.0 / len(MA_ASSETS)
        elif kind == "A2":
            ok = np.isfinite(vol) & (vol > 0)
            if ok.any():
                b = np.zeros(len(MA_ASSETS))
                b[ok] = (1.0 / vol[ok]) / (1.0 / vol[ok]).sum()
                w = np.where(on, b, 0.0)
        elif kind == "A3":
            ok = on & np.isfinite(vol) & (vol > 0)
            if ok.any():
                sc = np.zeros(len(MA_ASSETS))
                sc[ok] = mom[ok] / vol[ok]
                w = np.minimum(A3_CAP, sc / sc.sum())
        vecs[j] = w
    return rows, vecs


def ma_returns(m):
    return np.column_stack([cc_ret(m, s) if m.has(s) else np.zeros(m.n) for s in MA_ASSETS])


# ------------------------------------------------------------------ E: bond trend
E_ASSETS = ("TLT", "SHY", "IEF")


def e_decisions(m, kind):
    rows = month_ends(m)
    vecs = np.zeros((len(rows), len(E_ASSETS)))
    if kind == "E1":
        c = m.c["TLT"]
        s = R12.per_segment(m, c, lambda x: R12.sma(x, SMA_N))
        for j, d in enumerate(rows):
            if np.isfinite(s[d]) and c[d] > s[d]:
                vecs[j, 0] = 1.0
            elif np.isfinite(s[d]) and m.has("SHY") and np.isfinite(m.c["SHY"][d]):
                vecs[j, 1] = 1.0
    else:
        c = m.c["IEF"]
        mom = R12.per_segment(m, c, lambda x: R12._ret_n(x, MOM_N))
        cash_idx = np.cumprod(1.0 + m.cash)
        cmom = R12.per_segment(m, cash_idx, lambda x: R12._ret_n(x, MOM_N))
        for j, d in enumerate(rows):
            if np.isfinite(mom[d]) and np.isfinite(cmom[d]) and mom[d] > cmom[d]:
                vecs[j, 2] = 1.0
    return rows, vecs


def e_returns(m):
    return np.column_stack([cc_ret(m, s) if m.has(s) else np.zeros(m.n) for s in E_ASSETS])


# ------------------------------------------------------------------ T6 on this engine (candidate)
T6_ASSETS = tuple(R12.SECTORS) + ("TLT",)


def t6_decisions(m):
    w = R12.rotation_weights(m)
    rows = month_ends(m)
    vecs = np.array([[w[s][d] if s in w else 0.0 for s in T6_ASSETS] for d in rows])
    return rows, vecs


def t6_returns(m):
    return np.column_stack([cc_ret(m, s) if m.has(s) else np.zeros(m.n) for s in T6_ASSETS])


# ------------------------------------------------------------------ C: IBS
def ibs_signals(m, sym, kind):
    h, lo, c = m.h[sym], m.l[sym], m.c[sym]
    with np.errstate(invalid="ignore", divide="ignore"):
        ibs = np.where(h > lo, (c - lo) / (h - lo), np.nan)
    with np.errstate(invalid="ignore"):
        enter = np.isfinite(ibs) & (ibs < IBS_LO)
        if kind == "C3":
            s200 = R12.per_segment(m, m.split_c[sym], lambda x: R12.sma(x, SMA_N))
            enter &= np.isfinite(s200) & (m.split_c[sym] > s200)
        strong = np.isfinite(ibs) & (ibs > IBS_HI)
    return enter, strong


def ibs_trades(m, sym, kind):
    """Trade list [(entry_idx, exit_idx, 'open'|'close')] for one symbol."""
    enter, strong = ibs_signals(m, sym, kind)
    o = m.o[sym]
    ends = R12._ends(m)
    out = []
    pos, e = False, -1
    pend_in = pend_out = False
    for d in range(m.n):
        new_seg = d == 0 or m.seg[d] != m.seg[d - 1]
        if new_seg:
            pend_in = pend_out = False
        else:
            if pos and pend_out:
                out.append((e, d, "open"))
                pos = False
            elif not pos and pend_in and np.isfinite(o[d]):
                if kind == "C1":
                    out.append((d, d, "close"))
                else:
                    pos, e = True, d
        pend_in = pend_out = False
        if pos and ends[d]:
            out.append((e, d, "close"))
            pos = False
        if pos:
            pend_out = bool(strong[d]) or (d - e + 1) >= IBS_MAX_HOLD
        elif not ends[d]:
            pend_in = bool(enter[d])
    return out


def trade_gross(m, sym, t):
    e, x, kind = t
    px = m.c[sym][x] if kind == "close" else m.o[sym][x]
    return px / m.o[sym][e] - 1.0


def series_from_trades(m, trades_by_sym, share, cost):
    """Daily return on total capital (excluding cash) and exposure from trade lists."""
    r = np.zeros(m.n)
    expo = np.zeros(m.n)
    traded = np.zeros(m.n)
    for sym, trades in trades_by_sym.items():
        o, c = m.o[sym], m.c[sym]
        with np.errstate(invalid="ignore", divide="ignore"):
            first = c / o - 1.0
            full = np.r_[0.0, c[1:] / c[:-1] - 1.0]
            gap_in = np.r_[0.0, o[1:] / c[:-1] - 1.0]
        ent = np.zeros(m.n)
        held = np.zeros(m.n)
        ex_open = np.zeros(m.n)
        ex_any = np.zeros(m.n)
        for e, x, kind in trades:
            ent[e] += 1
            ex_any[x] += 1
            if kind == "close":
                held[e + 1:x + 1] += 1
            else:
                held[e + 1:x] += 1
                ex_open[x] += 1
        rs = ent * np.nan_to_num(first) + held * np.nan_to_num(full) + ex_open * np.nan_to_num(gap_in) - cost * (ent + ex_any)
        r += share * rs
        hold_close = np.zeros(m.n)
        for e, x, kind in trades:
            hold_close[e:(x + 1 if kind == "close" else x)] = 1.0
            if kind == "close":
                hold_close[x] = 0.0
        expo += share * hold_close
        traded += share * (ent + ex_any)
    return r, expo, traded


def run_ibs(m, kind, cost=COST):
    trades = {s: ibs_trades(m, s, kind) for s in IBS_ETFS if m.has(s)}
    r, expo, traded = series_from_trades(m, trades, 1.0 / len(IBS_ETFS), cost)
    port = r + (1.0 - expo_prev(expo)) * m.cash
    return port, expo, traded, trades


def expo_prev(expo):
    return 0.5 * (np.r_[0.0, expo[:-1]] + expo)


# ------------------------------------------------------------------ candidates and the learner
def candidates(m, cost=COST):
    out = {}
    R = ma_returns(m)
    rows, vecs = ma_decisions(m, "A1")
    r, H, tr = run_alloc(m, W_from(m.n, rows, vecs), R, cost)
    out["A1"] = {"r": r, "expo": H.sum(axis=1), "traded": tr}
    r, ex, tr, _ = run_ibs(m, "C2", cost)
    out["C2"] = {"r": r, "expo": ex, "traded": tr}
    rows, vecs = e_decisions(m, "E1")
    r, H, tr = run_alloc(m, W_from(m.n, rows, vecs), e_returns(m), cost)
    out["E1"] = {"r": r, "expo": H.sum(axis=1), "traded": tr}
    rows, vecs = t6_decisions(m)
    r, H, tr = run_alloc(m, W_from(m.n, rows, vecs), t6_returns(m), cost)
    out["T6"] = {"r": r, "expo": H.sum(axis=1), "traded": tr}
    share = 1.0 / len(R12.RSI2_ETFS)
    rets, expos, trd = {}, {}, np.zeros(m.n)
    for s in R12.RSI2_ETFS:
        if not m.has(s):
            continue
        rets[s], expos[s], tl = R12.sim_rsi2(m, s, None, cost)
        for t in tl:
            trd[t["entry_idx"]] += share
            trd[t["exit_idx"]] += share
    r, ex = R12.combine(m, rets, expos, {s: share for s in rets})
    out["RSI2"] = {"r": r, "expo": ex, "traded": trd}
    return out


def learner_decisions(m, cand, select="top", rng=None):
    names = list(CANDIDATES)
    Rm = np.column_stack([cand[k]["r"] for k in names])
    E = np.column_stack([cand[k]["expo"] for k in names])
    months = ym(m)
    first = [int(np.flatnonzero(E[:, i] > 0)[0]) if (E[:, i] > 0).any() else m.n for i in range(len(names))]
    rows = month_ends(m)
    vecs = np.zeros((len(rows), len(names)))
    ex = Rm - m.cash[:, None]
    for j, d in enumerate(rows):
        elig = [i for i in range(len(names)) if first[i] < m.n and months[d] - months[first[i]] >= LEARN_MIN_M]
        if not elig:
            continue
        if select == "all":
            vecs[j, elig] = 1.0 / len(elig)
            continue
        if select == "random":
            pick = list(rng.choice(elig, size=min(LEARN_TOP, len(elig)), replace=False))
        else:
            lo = months[d] - LEARN_LOOKBACK_M
            win = (months > lo) & (np.arange(m.n) <= d)
            sc = []
            for i in elig:
                x = ex[win & (np.arange(m.n) >= first[i]), i]
                sd = x.std(ddof=1) if len(x) > 2 else 0.0
                sc.append((-(x.mean() / sd) if sd > 0 else 0.0, i))
            pick = [i for _, i in sorted(sc)[:LEARN_TOP]]
        vecs[j, pick] = 1.0 / LEARN_TOP
    return rows, vecs, Rm


def run_learner(m, cand, select="top", risk=False, rng=None, delays=None, extra=0.0, cost=COST, dec=None):
    """dec: precomputed learner_decisions (the rankings use past returns only, so delays and extra costs in the noise
    check do not change them)."""
    rows, vecs, Rm = dec if dec is not None else learner_decisions(m, cand, select, rng)
    W = W_from(m.n, rows, vecs, delays)
    r, H, traded = run_alloc(m, W, Rm, cost, extra)
    if extra:
        TR = np.column_stack([cand[k]["traded"] for k in CANDIDATES])
        r = r - extra * (H * TR).sum(axis=1)
    return risk_control(m, r, cost + extra) if risk else r


def risk_control(m, r, cost=COST):
    """F2's exposure: min(1, 8% / trailing 63-session vol through t-1), halved while equity through t-1 is below 90% of its
    peak (until back to 95%)."""
    vol = pd.Series(r).rolling(VOL_N, min_periods=VOL_N).std().to_numpy(float) * math.sqrt(252)
    out = np.zeros(m.n)
    eq, peak, braked, x_prev = 1.0, 1.0, False, 0.0
    for t in range(m.n):
        v = vol[t - 1] if t > 0 else np.nan
        x = min(1.0, F2_VOL / v) if np.isfinite(v) and v > 0 else 1.0
        if eq < F2_BRAKE * peak:
            braked = True
        elif braked and eq >= F2_RELEASE * peak:
            braked = False
        if braked:
            x *= 0.5
        out[t] = x * r[t] + (1.0 - x) * m.cash[t] - cost * abs(x - x_prev)
        x_prev = x
        eq *= 1.0 + out[t]
        peak = max(peak, eq)
    return out


# ------------------------------------------------------------------ B: low-volatility industries (French)
def fr_vols(d, dec):
    months = np.array([x.year * 12 + x.month for x in d.days])
    out = []
    for row, mom, trend in dec:
        if mom is None:
            out.append(None)
            continue
        win = (months > months[row] - 12) & (np.arange(d.n) <= row)
        out.append(d.ind[win].std(axis=0, ddof=1))
    return out


def fr_weights(d, kind, dec, vols, pick=None, flags=None, delays=None):
    W = np.zeros((d.n, len(R13.INDUSTRIES)))
    cur = np.zeros(len(R13.INDUSTRIES))
    last = 0
    for j, (row, mom, trend) in enumerate(dec):
        if flags is not None and trend is not None:
            trend = bool(flags[j])
        row = max(last, min(d.n - 1, row + (int(delays[j]) if delays is not None else 0)))
        W[last:row] = cur
        new = np.zeros(len(R13.INDUSTRIES))
        if vols[j] is not None and trend is not None and (kind == "B1" or trend):
            chosen = list(pick()) if pick else sorted(range(len(R13.INDUSTRIES)), key=lambda i: (vols[j][i], i))[:3]
            new[chosen] = 1.0 / 3
        cur, last = new, row
    W[last:] = cur
    return W


def evaluate_b(d, n_luck=None):
    n_luck = LUCK_N if n_luck is None else n_luck
    dec = R13.decisions(d)
    vols = fr_vols(d, dec)
    pm = R13.mask_for(d, *R13.WINDOWS["PASS"])
    eras = {e: R13.mask_for(d, a, b) for e, (a, b) in R13.ERAS.items()}
    mkt_sh = R13.pass_sharpe(d, d.mkt, pm)
    out = {}
    for kind in ("B1", "B2"):
        W = fr_weights(d, kind, dec, vols)
        r = R13.simulate(d, W, R13.COSTS["10bps"])[0]
        r50 = R13.simulate(d, W, R13.COSTS["50bps"])[0]
        p, diff, ci = R13.sharpe_diff_test(r[pm] - d.rf[pm], d.mkt[pm] - d.rf[pm])
        s = R13.stats(d, r, pm)
        g = np.random.default_rng(SEEDS["picks"])
        picks = np.array([R13.pass_sharpe(d, R13.simulate(d, fr_weights(d, kind, dec, vols, pick=lambda: g.choice(10, 3, replace=False)),
                                                           R13.COSTS["10bps"])[0], pm) for _ in range(n_luck)])
        shifted = None
        if kind == "B2":
            flags0 = np.array([bool(t) if t is not None else False for _, _, t in dec])
            pos = np.flatnonzero([t is not None and pm[row] for row, _, t in dec])
            g = np.random.default_rng(SEEDS["filter"])
            sh = []
            for _ in range(n_luck):
                f = flags0.copy()
                f[pos] = np.roll(flags0[pos], int(g.integers(12, max(13, len(pos) - 12))))
                sh.append(R13.pass_sharpe(d, R13.simulate(d, fr_weights(d, kind, dec, vols, flags=f), R13.COSTS["10bps"])[0], pm))
            shifted = np.array(sh)
        g = np.random.default_rng(SEEDS["noise"])
        noisy = np.array([R13.pass_sharpe(d, R13.simulate(d, fr_weights(d, kind, dec, vols, delays=g.integers(0, 6, len(dec))),
                                                           R13.COSTS["10bps"] + g.uniform(0, NOISE_EXTRA))[0], pm) for _ in range(n_luck)])
        mo = R13.monthly_excess(d, r, pm)
        tot = float(mo.sum())
        kept = float((tot - mo.nlargest(OUTLIER_TOP).sum()) / tot) if tot > 0 else None
        eras_won = [e for e, mk in eras.items() if R13.pass_sharpe(d, r, mk) > R13.pass_sharpe(d, d.mkt, mk)]
        items = {f"1 Sharpe above the market's, p < {ALPHA:.4f}": p < ALPHA,
                 "2 drawdown smaller than the market's": s["max_dd"] > R13.stats(d, d.mkt, pm)["max_dd"],
                 "3 Sharpe above the market's in 2 of 3 eras": len(eras_won) >= 2,
                 "4 Sharpe over cash > 0 at 50 bps": (R13.stats(d, r50, pm)["sharpe"] or 0) > 0,
                 "5 beats 95% of random industry picks": s["sharpe"] > float(np.percentile(picks, RANDOM_PCT)),
                 "7 above the market's Sharpe in 95% of noisy runs": float(np.mean(noisy > mkt_sh)) >= NOISE_SHARE,
                 "8 keeps 50% without its 10 best months": (kept or 0) >= OUTLIER_KEEP}
        if shifted is not None:
            items["6 beats 95% of shifted trend filters"] = s["sharpe"] > float(np.percentile(shifted, RANDOM_PCT))
        out[kind] = {"r": r, "stats": s, "eras_won": eras_won, "sharpe_vs_market": {"p": p, "diff_annual": diff * math.sqrt(R13.per_year(d, pm)[0]),
                     "ci95_annual": [c * math.sqrt(R13.per_year(d, pm)[0]) for c in ci]},
                     "luck": {"random_picks_p95": float(np.percentile(picks, RANDOM_PCT)), "random_picks_median": float(np.median(picks)),
                              "shifted_p95": None if shifted is None else float(np.percentile(shifted, RANDOM_PCT)),
                              "noise_share_above_market": float(np.mean(noisy > mkt_sh)), "noise_worst": float(noisy.min()),
                              "kept_without_best_10_months": kept},
                     "sized_20dd": R13.sized_to_dd(d, r, W.sum(axis=1), pm), "items": items, "pass": all(items.values())}
    out["market"] = {"stats": R13.stats(d, d.mkt, pm), "sized_20dd": R13.sized_to_dd(d, d.mkt, np.ones(d.n), pm)}
    return out


# ------------------------------------------------------------------ ETF family evaluation
def etf_trial(m, name, cand=None, cost=COST):
    """(daily returns, exposure, traded, rebuild(delays, extra, rng, shift) for the luck checks, trades or None)."""
    if name in ("A1", "A2", "A3", "E1", "E2"):
        if name[0] == "A":
            rows, vecs = ma_decisions(m, name)
            R = ma_returns(m)
        else:
            rows, vecs = e_decisions(m, name)
            R = e_returns(m)

        def rebuild(delays=None, extra=0.0, shift=None):
            v = vecs if shift is None else shift(vecs, rows)
            return run_alloc(m, W_from(m.n, rows, v, delays), R, cost, extra)[0]
        r, H, tr = run_alloc(m, W_from(m.n, rows, vecs), R, cost)
        return r, H.sum(axis=1), tr, rebuild, None
    if name[0] == "C":
        r, ex, tr, trades = run_ibs(m, name, cost)
        return r, ex, tr, None, trades
    risk = name == "F2"
    r = run_learner(m, cand, "top", risk, cost=cost, dec=cand.get("_dec_top"))
    return r, None, None, None, None


def shift_within(m, mk, k):
    def f(vecs, rows):
        idx = np.flatnonzero(mk[rows])
        v = vecs.copy()
        v[idx] = np.roll(vecs[idx], k, axis=0)
        return v
    return f


def evaluate_etf(m, n_luck=None, boot_draws=None):
    n_luck = LUCK_N if n_luck is None else n_luck
    pm = mask(m, *PASS)
    spy_r = cc_ret(m, "SPY")
    spy = R12.series_stats(spy_r, m.cash, pm)
    cand = candidates(m)
    dec_top = learner_decisions(m, cand, "top")
    out = {"benchmark_spy": spy, "candidates": {k: R12.series_stats(v["r"], m.cash, pm) for k, v in cand.items()}}
    cand["_dec_top"] = dec_top
    for ctrl, risk in (("F0", False), ("F0r", True)):
        out[ctrl] = R12.series_stats(run_learner(m, cand, "all", risk), m.cash, pm)
    rows = month_ends(m)
    n_pass_me = int(pm[rows].sum())
    for name in ETF_TRIALS:
        r, expo, traded, rebuild, trades = etf_trial(m, name, cand)
        ex = r[pm] - m.cash[pm]
        p, ci = R12.block_bootstrap(ex) if boot_draws is None else R12.block_bootstrap(ex, draws=boot_draws)
        st = R12.series_stats(r, m.cash, pm)
        row = {"r": r, "stats": st, "p": p, "info": {w: R12.series_stats(r, m.cash, mask(m, a, b)) for w, (a, b) in INFO.items()}}
        base = sharpe(r, m.cash, pm)
        if name[0] in "AE":
            g = np.random.default_rng(SEEDS["shift"])
            shifted = np.array([sharpe(rebuild(shift=shift_within(m, pm, int(g.integers(12, max(13, n_pass_me - 12))))), m.cash, pm)
                                for _ in range(n_luck)])
            luck3 = {"kind": "shifted decisions", "p95": float(np.percentile(shifted, RANDOM_PCT)), "median": float(np.median(shifted)),
                     "pass": base > float(np.percentile(shifted, RANDOM_PCT))}
            g = np.random.default_rng(SEEDS["noise"])
            noisy = np.array([sharpe(rebuild(delays=g.integers(0, NOISE_DELAY_ALLOC + 1, len(rows)), extra=g.uniform(0, NOISE_EXTRA)), m.cash, pm)
                              for _ in range(n_luck)])
            kept = kept_without_best_months(r, m.cash, pm, m.index)
        elif name[0] == "C":
            luck3, noisy, kept = c_luck(m, name, trades, pm, n_luck)
        else:
            risk = name == "F2"
            g = np.random.default_rng(SEEDS["random"])
            rnd = np.array([sharpe(run_learner(m, cand, "random", risk, rng=g), m.cash, pm) for _ in range(n_luck)])
            luck3 = {"kind": "random selectors", "p95": float(np.percentile(rnd, RANDOM_PCT)), "median": float(np.median(rnd)),
                     "pass": base > float(np.percentile(rnd, RANDOM_PCT))}
            g = np.random.default_rng(SEEDS["noise"])
            noisy = np.array([sharpe(run_learner(m, cand, "top", risk, delays=g.integers(0, NOISE_DELAY_ALLOC + 1, len(rows)),
                                                 extra=g.uniform(0, NOISE_EXTRA), dec=dec_top), m.cash, pm) for _ in range(n_luck)])
            kept = kept_without_best_months(r, m.cash, pm, m.index)
        items = {f"1 p < {ALPHA:.4f} vs cash": p < ALPHA,
                 "2 drawdown smaller than SPY's": st["max_dd"] > spy["max_dd"],
                 f"3 beats 95% of {luck3['kind']}": bool(luck3["pass"]),
                 "4 Sharpe > 0 in 95% of noisy runs": float(np.mean(noisy > 0)) >= NOISE_SHARE,
                 "5 keeps 50% without its 10 best " + ("trades" if name[0] == "C" else "months"): (kept or 0) >= OUTLIER_KEEP}
        row.update({"luck": {"3": luck3, "noise_share_above_0": float(np.mean(noisy > 0)), "noise_median": float(np.median(noisy)),
                             "noise_worst": float(noisy.min()), "kept": kept},
                    "items": items, "pass": all(items.values()),
                    "sized_20dd": sized_to_dd(m, r, pm)})
        if trades is not None:
            row["trades"] = c_trade_stats(m, trades, pm)
        out[name] = row
    return out, cand


def c_luck(m, name, trades, pm, n_luck):
    rows_t = [(s, t) for s, tl in trades.items() for t in tl if pm[t[0]] and pm[t[1]]]
    net = np.array([trade_gross(m, s, t) - 2 * COST for s, t in rows_t])
    g = np.random.default_rng(SEEDS["random"])
    idx = np.arange(m.n)
    groups = {}
    for s, t in rows_t:
        groups.setdefault((s, t[1] - t[0], t[2]), 0)
        groups[(s, t[1] - t[0], t[2])] += 1
    total = np.zeros(n_luck)
    for (s, hold, kind), k in sorted(groups.items()):
        o, c = m.o[s], m.c[s]
        e = idx[: m.n - hold]
        x = e + hold
        ok = pm[e] & pm[x] & (m.seg[e] == m.seg[x]) & np.isfinite(o[e]) & np.isfinite(o[x])
        valid = e[ok]
        if not len(valid):
            continue
        pick = g.choice(valid, size=(n_luck, k))
        px = c[pick + hold] if kind == "close" else o[pick + hold]
        total += (px / o[pick] - 1.0 - 2 * COST).sum(axis=1)
    means = total / max(len(rows_t), 1)
    obs = float(net.mean()) if len(net) else 0.0
    luck3 = {"kind": "random entries", "p95": float(np.percentile(means, RANDOM_PCT)), "median": float(np.median(means)),
             "observed": obs, "pass": obs > float(np.percentile(means, RANDOM_PCT))}
    g = np.random.default_rng(SEEDS["noise"])
    noisy = []
    for _ in range(n_luck):
        extra = g.uniform(0, NOISE_EXTRA)
        moved = {}
        for s, tl in trades.items():
            mv = []
            for e, x, kind in tl:
                de, dx = int(g.integers(0, NOISE_DELAY_TRADE + 1)), int(g.integers(0, NOISE_DELAY_TRADE + 1))
                e2 = min(e + de, m.n - 1)
                x2 = min(max(x + dx, e2), m.n - 1)
                if m.seg[e2] != m.seg[e] or m.seg[x2] != m.seg[e]:
                    e2, x2 = e, x
                mv.append((e2, x2, kind))
            moved[s] = mv
        rr, ex, _ = series_from_trades(m, moved, 1.0 / len(IBS_ETFS), COST + extra)
        noisy.append(sharpe(rr + (1.0 - expo_prev(ex)) * m.cash, m.cash, pm))
    best = np.sort(net)[::-1]
    kept = float((net.sum() - best[:OUTLIER_TOP].sum()) / net.sum()) if net.sum() > 0 else None
    return luck3, np.array(noisy), kept


def c_trade_stats(m, trades, pm):
    net = np.array([trade_gross(m, s, t) - 2 * COST for s, tl in trades.items() for t in tl if pm[t[0]] and pm[t[1]]])
    if not len(net):
        return {"trades": 0}
    w, lo = net[net > 0], net[net <= 0]
    return {"trades": int(len(net)), "win_rate": float(np.mean(net > 0)), "expectancy": float(net.mean()),
            "profit_factor": float(w.sum() / -lo.sum()) if lo.sum() < 0 else None}


def sized_to_dd(m, r, mk, target=-0.20):
    rf, x = m.cash[mk], r[mk]
    yrs = len(x) / 252.0

    def run(k):
        eq = np.cumprod(1.0 + rf + k * (x - rf))
        return float((eq / np.maximum.accumulate(eq) - 1.0).min()), eq
    lo, hi = 0.01, 20.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if run(mid)[0] < target:
            hi = mid
        else:
            lo = mid
    dd, eq = run(lo)
    return {"k": lo, "cagr": float(eq[-1] ** (1.0 / yrs) - 1.0), "max_dd": dd}


def evaluate(m, d, n_luck=None, boot_draws=None):
    etf, _ = evaluate_etf(m, n_luck, boot_draws)
    fr = evaluate_b(d, n_luck)
    ev = {"label": LABEL, "alpha": ALPHA, "n_trials_total": N_PRIOR + N_ROUND, "pass_window_etf": [PASS[0].isoformat(), PASS[1].isoformat()],
          "etf": {k: {kk: vv for kk, vv in v.items() if kk != "r"} if isinstance(v, dict) else v for k, v in etf.items()},
          "french": {k: {kk: vv for kk, vv in v.items() if kk != "r"} for k, v in fr.items()}}
    pm = mask(m, *PASS)
    srs = []
    for name in ETF_TRIALS:
        ex = etf[name]["r"][pm] - m.cash[pm]
        srs.append(float(ex.mean() / ex.std()))
    pf = R13.mask_for(d, *R13.WINDOWS["PASS"])
    for name in ("B1", "B2"):
        ex = fr[name]["r"][pf] - d.rf[pf]
        srs.append(float(ex.mean() / ex.std()))
    sr_var = statistics.variance(srs)
    ev["sr_var"] = sr_var
    for name in ETF_TRIALS:
        ev["etf"][name]["deflated_sharpe"] = deflated_sharpe(list(etf[name]["r"][pm] - m.cash[pm]), N_PRIOR + N_ROUND, sr_var)
    for name in ("B1", "B2"):
        ev["french"][name]["deflated_sharpe"] = deflated_sharpe(list(fr[name]["r"][pf] - d.rf[pf]), N_PRIOR + N_ROUND, sr_var)
    ev["verdicts"] = {n: (ev["etf"][n]["pass"] if n in ETF_TRIALS else ev["french"][n]["pass"]) for n in TRIALS}
    return ev, etf, fr


# ------------------------------------------------------------------ report
def _p(x, n=1):
    return "-" if x is None else f"{x * 100:.{n}f}%"


def _f(x, n=2):
    return "-" if x is None else f"{x:.{n}f}"


NAMES = {"A1": "multi-asset trend, equal slots", "A2": "multi-asset trend, risk-parity slots", "A3": "multi-asset trend, return/vol",
         "B1": "low-vol industries", "B2": "low-vol industries + trend filter", "C1": "IBS, one day", "C2": "IBS, hold to a strong close",
         "C3": "IBS above the 200-day", "E1": "TLT trend, else SHY", "E2": "IEF momentum vs T-bills", "F1": "learner (picks 2 of 5)",
         "F2": "learner + risk control"}


def report_md(ev, note=""):
    L = [f"# Round 14 result ({ev['label']})", "",
         f"Pre-registered in SPRINT_PLAN \"Round 14 pre-registration\" (2026-11-04). 12 trials; bar p < {ev['alpha']:.4f}. ETF PASS "
         f"{ev['pass_window_etf'][0]}..{ev['pass_window_etf'][1]}; French PASS 1927-07-01..1997-12-31; 10 bps a side.", ""]
    if note:
        L += [note, ""]
    L += ["## Verdicts", "", "| Trial | What | Verdict | p | Sharpe | CAGR | Max DD | Failed items |", "|---|---|---|---|---|---|---|---|"]
    for n in TRIALS:
        if n in ETF_TRIALS:
            t = ev["etf"][n]
            s, p = t["stats"], t["p"]
        else:
            t = ev["french"][n]
            s, p = t["stats"], t["sharpe_vs_market"]["p"]
        failed = ", ".join(k for k, v in t["items"].items() if not v)
        L.append(f"| {n} | {NAMES[n]} | {'PASS' if t['pass'] else 'FAIL'} | {_f(p, 4)} | {_f(s['sharpe'])} | {_p(s['cagr'])} | {_p(s['max_dd'])} | {failed} |")
    b, mk = ev["etf"]["benchmark_spy"], ev["french"]["market"]["stats"]
    L += ["", f"Buy-and-hold SPY on ETF PASS: Sharpe {_f(b['sharpe'])}, CAGR {_p(b['cagr'])}, max DD {_p(b['max_dd'])}. "
          f"French market on 1927-1997: Sharpe {_f(mk['sharpe'])}, CAGR {_p(mk['cagr'])}, max DD {_p(mk['max_dd'])}.", "",
          "## Luck checks", "", "| Trial | Item 3 (95th pct of the random set / what it got) | Noise: share of runs OK | Kept without best 10 |", "|---|---|---|---|"]
    for n in ETF_TRIALS:
        lk = ev["etf"][n]["luck"]
        l3 = lk["3"]
        got = l3.get("observed")
        got = _p(got, 3) if got is not None else _f(ev["etf"][n]["stats"]["sharpe"])
        p95 = _p(l3["p95"], 3) if l3["kind"] == "random entries" else _f(l3["p95"])
        L.append(f"| {n} | {l3['kind']}: {p95} / {got} | {_p(lk['noise_share_above_0'])} | {_p(lk['kept'])} |")
    for n in ("B1", "B2"):
        lk = ev["french"][n]["luck"]
        L.append(f"| {n} | random picks: {_f(lk['random_picks_p95'])} / {_f(ev['french'][n]['stats']['sharpe'])}"
                 + ("" if lk["shifted_p95"] is None else f"; shifted filter {_f(lk['shifted_p95'])}") +
                 f" | {_p(lk['noise_share_above_market'])} above market | {_p(lk['kept_without_best_10_months'])} |")
    L += ["", "## The learner's candidates and controls (ETF PASS)", "", "| Series | Sharpe | CAGR | Max DD |", "|---|---|---|---|"]
    for k, s in ev["etf"]["candidates"].items():
        L.append(f"| candidate {k} | {_f(s['sharpe'])} | {_p(s['cagr'])} | {_p(s['max_dd'])} |")
    for k in ("F0", "F0r"):
        s = ev["etf"][k]
        L.append(f"| control {k} ({'equal weight' if k == 'F0' else 'equal weight + risk control'}) | {_f(s['sharpe'])} | {_p(s['cagr'])} | {_p(s['max_dd'])} |")
    L += ["", "## Other windows (information) and sizing to a -20% worst drop (hindsight)", "",
          "| Trial | 2000-2007 Sharpe / CAGR | 2024-08..2026-06 Sharpe / CAGR | Size for -20% | CAGR at that size | Deflated Sharpe |", "|---|---|---|---|---|---|"]
    for n in ETF_TRIALS:
        t = ev["etf"][n]
        e, dv = t["info"]["EARLY"], t["info"]["DEV"]
        L.append(f"| {n} | {_f(e and e['sharpe'])} / {_p(e and e['cagr'])} | {_f(dv and dv['sharpe'])} / {_p(dv and dv['cagr'])} | "
                 f"{_f(t['sized_20dd']['k'])}x | {_p(t['sized_20dd']['cagr'])} | {_f(t['deflated_sharpe'], 4)} |")
    for n in ("B1", "B2"):
        t = ev["french"][n]
        L.append(f"| {n} | - | - | {_f(t['sized_20dd']['k'])}x | {_p(t['sized_20dd']['cagr'])} | {_f(t['deflated_sharpe'], 4)} |")
    L += ["", f"Every number above is a {ev['label']}. Deflated Sharpe at N = {ev['n_trials_total']:,} (unreliable when the trial spread "
          "comes from a few similar trials). Not financial advice; a pass earns an automated paper ledger at most."]
    return "\n".join(L) + "\n"
