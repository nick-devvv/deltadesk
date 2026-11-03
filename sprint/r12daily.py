"""sprint/r12daily.py - round 12: daily-bar ETF rules on a longer, untouched history (SPRINT_PLAN "Round 12
pre-registration", written 2026-11-03 before any round-12 pull or run; vault note Research/2026-11-03-round12-prereg.md).
Research only: reads the daily files that tools/sprint_r12.py `fetch` wrote; no network, no orders. Every number is a
BACKTEST on free daily data (Yahoo Finance through yfinance), labeled as such. Multi-day holds: Nick asked for this round
in the 2026-11-03 conversation (CLAUDE.md scope note).

Data: per symbol, daily open/high/low/close as Yahoo serves them (split-adjusted) plus the dividend-adjusted close.
  Signals use the split-adjusted closes, as F1 does. Returns use dividend-adjusted prices (open/high/low/close each
  scaled by adj_close / close that day), so a hold earns its dividends. L1 and L2 are never requested, so the files have
  a gap where L2 was and end before L1. The sessions split into segments at any gap over GAP_DAYS calendar days. Each
  segment is simulated on its own: indicators restart (as universe.Panel does at the L2 gap) and every position is flat
  at a segment's end (a position still open at the last close before a gap is closed at that close, with costs).

Timing: signals on day t's close; orders fill at day t+1's open. Stops are checked against the day's (dividend-adjusted)
  low: an open at or below the stop fills at the open, otherwise at the stop. Costs per side on traded notional:
  1x = 5 bps, 2x = 10 bps; pass/fail uses 2x. Cash: uninvested capital earns the 3-month T-bill (DTB3, %/100/252 a day)
  on the average of the prior and current close's exposure; exposure above 1 (T7) pays the same rate.

Trials (13; added to the 11,284 before this round for the deflated Sharpe):
  T1 rsi2 (F1, Amendment 12, rules unchanged): long only; signal at the close: close > SMA(200), close < SMA(5), Wilder
     RSI(2) < 10; buy at the next open; exit at the next open after a close > SMA(5) (closes from the entry day on); no
     stop; one position per symbol. 10 ETFs: SPY QQQ IWM DIA XLF XLE XLV EEM GLD TLT, 1/10 of capital each (a symbol's
     share sits in cash while it is flat or before it exists).
  T2-T4 T1 plus a stop 3%, 5%, 8% below the entry fill, armed from the entry day on; a stopped symbol stays flat until a
     close above SMA(5).
  T5 trend (Faber 2007 style; 151 Trading Strategies s3.11): SPY while the close > SMA(200), else cash.
  T6 dual-momentum sector rotation (151 s4.1.2; Antonacci 2014): at the close of each month's last session, rank XLK XLY
     XLP XLI XLB XLU XLF XLE XLV by 252-session dividend-adjusted return; SPY close > SMA(200) -> the top 3 at 1/3 each,
     else TLT at 100% (cash while TLT has no data). Rebalanced at the next open; weights held fixed between rebalances.
  T7 volatility target (151 s6.5): w = min(1.5, 0.10 / (stdev of the last 20 SPY daily returns x sqrt(252))), changed
     only when |new - held| > 0.10; the rest in cash.
  T8 two moving averages with a 2% exit (151 s3.12): long SPY when SMA(10) > SMA(30); out after a close < 0.98 x the
     entry-signal close or SMA(10) <= SMA(30); after a 2% exit, flat until SMA(10) crosses below and back above SMA(30).
  T9 mix: 50% T5 + 50% T1, rebalanced to 50/50 every day; the rebalance trades pay the same cost per side.
  T10-T12 (Addendum 12.1, before any run) T1 plus a TRAILING stop 3%, 5%, 8% below the highest of the entry fill and
     every close since entry (through the prior close; it only rises), checked like T2-T4 against the day's low.
  T13 (Addendum 12.2, before any run) GLD Parabolic SAR, long only (Wilder 1978; the settings of the XAUUSD 4-hour
     strategy Nick sent: start 0.02, step 0.02, max 0.20, target 3R). SAR from GLD's daily high/low, restarting in each
     segment. Entry: at the next open after a close on which the SAR flipped from down to up. Stop: that day's SAR level
     (from bars before it; it follows price up), checked against the low; an open at or below it fills at the open.
     Target: entry fill + 3 x (entry fill - the entry day's SAR), checked against the high (an open above it fills at the
     open); stop first when both are touched the same day. An entry open at or below its SAR is skipped and counted.
     After any exit, flat until the next down-to-up flip. 100% of capital while long (the source's 1%-risk sizing needs
     leverage that shares don't have).

Windows: FRESH 2005-01-03..2015-12-31 decides pass/fail. SUPP 2000-01-03..2004-12-31, REPL_HIST = HIST and REPL_DEV = DEV
  are information only (rsi2 was already tested in HIST and DEV in rounds 9 and 11).

Pass (all four on FRESH at 2x costs): 1 one-sided p < 0.05 / 13 that the mean daily return over cash is > 0 (circular
  block bootstrap of the demeaned series, 21-session blocks, 10,000 draws, default_rng(12)); 2 max drawdown smaller than
  buy-and-hold SPY's (dividend-adjusted closes); 3 (trade-based trials: T1-T4, T10-T13) the mean net trade return beats the 95th percentile of
  1,000 random-entry draws (same symbol, same holding length in sessions, open-to-open, inside FRESH, default_rng(7));
  4 Sharpe over cash > 0. The deflated Sharpe (report.deflated_sharpe, N = 11,284 + 13, sr_var = the variance of round 12's
  thirteen FRESH per-session Sharpes) is reported, not a pass item. A pass earns a forward paper ledger at most.
"""
import math
import statistics
from datetime import date

import numpy as np
import pandas as pd

from . import periods
from .report import deflated_sharpe

RSI2_ETFS = ("SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLV", "EEM", "GLD", "TLT")
SECTORS = ("XLK", "XLY", "XLP", "XLI", "XLB", "XLU", "XLF", "XLE", "XLV")
SYMBOLS = tuple(sorted(set(RSI2_ETFS) | set(SECTORS)))
WINDOWS = {
    "FRESH": (date(2005, 1, 3), date(2015, 12, 31)),
    "SUPP": (date(2000, 1, 3), date(2004, 12, 31)),
    "REPL_HIST": periods.HIST,
    "REPL_DEV": periods.DEV,
}
PASS_WINDOW, PASS_COST = "FRESH", "2x"
COSTS = {"1x": 0.0005, "2x": 0.0010}
GAP_DAYS = 10
N_ROUND, N_PRIOR = 13, 11_284
ALPHA = 0.05 / N_ROUND
BOOT_DRAWS, BOOT_BLOCK, BOOT_SEED = 10_000, 21, 12
CTRL_DRAWS, CTRL_SEED, CTRL_PCT = 1_000, 7, 0.95
TRADE_BOOT_DRAWS, TRADE_BOOT_SEED = 2_000, 29
SMA_LONG, SMA_SHORT, RSI_MAX = 200, 5, 10.0
STOPS = {"T2_rsi2_stop3": 0.03, "T3_rsi2_stop5": 0.05, "T4_rsi2_stop8": 0.08,
         "T10_rsi2_trail3": 0.03, "T11_rsi2_trail5": 0.05, "T12_rsi2_trail8": 0.08}
TRAILING = {"T10_rsi2_trail3", "T11_rsi2_trail5", "T12_rsi2_trail8"}
VT_TARGET, VT_CAP, VT_BAND, VT_N = 0.10, 1.5, 0.10, 20
MOM_N, TOP_K = 252, 3
MA_FAST, MA_SLOW, MA_EXIT = 10, 30, 0.98
TRIALS = ("T1_rsi2", "T2_rsi2_stop3", "T3_rsi2_stop5", "T4_rsi2_stop8", "T5_trend200", "T6_sector_dualmom",
          "T7_voltarget", "T8_twoma_2pct", "T9_mix", "T10_rsi2_trail3", "T11_rsi2_trail5", "T12_rsi2_trail8",
          "T13_gld_psar_long")
RSI2_TRIALS = TRIALS[:4] + TRIALS[9:12]
TRADE_TRIALS = RSI2_TRIALS + ("T13_gld_psar_long",)
PSAR_START, PSAR_STEP, PSAR_MAX, PSAR_TARGET_R = 0.02, 0.02, 0.20, 3.0
LABEL = "BACKTEST on Yahoo daily bars (dividend-adjusted returns)"


# ------------------------------------------------------------------ data
class Market:
    """Every symbol on SPY's session calendar. Arrays are (sessions,), NaN before a symbol's first session."""

    def __init__(self, frames, cash):
        if "SPY" not in frames:
            raise ValueError("SPY is required: it is the session calendar and T5/T7/T8's asset")
        days = pd.DatetimeIndex(frames["SPY"].index).normalize()
        if days.has_duplicates or not days.is_monotonic_increasing:
            raise ValueError("SPY dates must be unique and increasing")
        self.index = days
        self.days = [d.date() for d in days]
        self.n = len(days)
        gaps = np.r_[0, np.diff(days.values).astype("timedelta64[D]").astype(int)]
        self.seg = np.cumsum(gaps > GAP_DAYS)
        self.split_c, self.o, self.h, self.l, self.c = {}, {}, {}, {}, {}
        for sym, df in frames.items():
            f = df.copy()
            f.index = pd.DatetimeIndex(f.index).normalize()
            f = f[~f.index.duplicated(keep="last")].sort_index().reindex(days)
            first = f["close"].first_valid_index()
            f = f.ffill()
            if first is not None:
                f.loc[f.index < first] = np.nan
            k = (f["adj_close"] / f["close"]).to_numpy(float)
            self.split_c[sym] = f["close"].to_numpy(float)
            self.o[sym] = f["open"].to_numpy(float) * k
            self.h[sym] = f["high"].to_numpy(float) * k
            self.l[sym] = f["low"].to_numpy(float) * k
            self.c[sym] = f["adj_close"].to_numpy(float)
        cs = pd.Series(cash, dtype=float) if cash is not None else pd.Series(dtype=float)
        cs.index = pd.DatetimeIndex(cs.index).normalize()
        cs = cs[~cs.index.duplicated(keep="last")].sort_index()
        self.cash = (cs.reindex(days.union(cs.index)).ffill().reindex(days) / 100.0 / 252.0).fillna(0.0).to_numpy(float)

    def has(self, sym):
        return sym in self.c

    def segments(self):
        """(start, end) index pairs, end exclusive."""
        cut = np.flatnonzero(np.diff(self.seg)) + 1
        bounds = np.r_[0, cut, self.n]
        return [(int(bounds[i]), int(bounds[i + 1])) for i in range(len(bounds) - 1)]


def per_segment(m, x, fn):
    """Apply fn to each segment of x on its own (indicators restart at a gap)."""
    out = np.full(len(x), np.nan)
    for a, b in m.segments():
        out[a:b] = fn(np.asarray(x[a:b], float))
    return out


def sma(x, n):
    s = pd.Series(x)
    return s.rolling(n, min_periods=n).mean().to_numpy(float)


def rsi_wilder(c, n=2):
    """Wilder RSI(n), as universe.Panel.rsi / ind5.rsi_wilder: the first value averages the first n changes, then
    avg = (avg x (n - 1) + x) / n; average loss 0 -> 100 (50 if the average gain is 0 too). NaN closes (before a symbol
    exists) are skipped: the RSI starts with the first finite run."""
    out = np.full(len(c), np.nan)
    idx = np.flatnonzero(np.isfinite(c))
    if len(idx) <= n:
        return out
    start = idx[0]
    cc = c[start:]
    if not np.all(np.isfinite(cc)):
        return out
    d = np.diff(cc)
    g, lo = np.maximum(d, 0.0), np.maximum(-d, 0.0)
    ag, al = float(g[:n].mean()), float(lo[:n].mean())

    def val(a, b):
        if b == 0:
            return 100.0 if a > 0 else 50.0
        return 100.0 - 100.0 / (1.0 + a / b)

    out[start + n] = val(ag, al)
    for k in range(n, len(d)):
        ag = (ag * (n - 1) + g[k]) / n
        al = (al * (n - 1) + lo[k]) / n
        out[start + k + 1] = val(ag, al)
    return out


# ------------------------------------------------------------------ simulators
def _ends(m):
    """True on the last session of each segment."""
    e = np.zeros(m.n, bool)
    for _, b in m.segments():
        e[b - 1] = True
    return e


def sim_weights(m, sym, w, cost):
    """One asset held at target weight w (decided at each close, filled at the next open). Returns (daily return on
    total capital, excluding cash; exposure at each close)."""
    o, c = m.o[sym], m.c[sym]
    ends = _ends(m)
    r = np.zeros(m.n)
    expo = np.zeros(m.n)
    pos = 0.0
    for d in range(m.n):
        new_seg = d == 0 or m.seg[d] != m.seg[d - 1]
        live = np.isfinite(o[d]) and np.isfinite(c[d])
        if not new_seg and pos:
            r[d] += pos * (o[d] / c[d - 1] - 1.0)
        tgt = 0.0 if (new_seg or not live) else float(np.nan_to_num(w[d - 1]))
        r[d] -= abs(tgt - pos) * cost
        pos = tgt
        if pos:
            r[d] += pos * (c[d] / o[d] - 1.0)
        if ends[d] and pos:
            r[d] -= abs(pos) * cost
            pos = 0.0
        expo[d] = pos
    return r, expo


def rsi2_signal(m, sym):
    sc = m.split_c[sym]
    s200 = per_segment(m, sc, lambda x: sma(x, SMA_LONG))
    s5 = per_segment(m, sc, lambda x: sma(x, SMA_SHORT))
    r2 = per_segment(m, sc, lambda x: rsi_wilder(x, 2))
    with np.errstate(invalid="ignore"):
        sig = np.isfinite(sc) & np.isfinite(s200) & np.isfinite(s5) & np.isfinite(r2) & (sc > s200) & (sc < s5) & (r2 < RSI_MAX)
        above5 = np.isfinite(sc) & np.isfinite(s5) & (sc > s5)
    return sig, above5


def sim_rsi2(m, sym, stop, cost, sig=None, above5=None, trail=False):
    """F1 on one symbol, optionally with a stop: fixed (entry fill x (1 - stop)) or trailing (trail=True: the highest
    of the entry fill and every close since entry, through the prior close, x (1 - stop); it only rises). Returns (daily return on this symbol's capital slice, excluding
    cash; exposure at each close; trades)."""
    if sig is None or above5 is None:
        sig, above5 = rsi2_signal(m, sym)
    o, lo, c = m.o[sym], m.l[sym], m.c[sym]
    ends = _ends(m)
    r = np.zeros(m.n)
    expo = np.zeros(m.n)
    trades = []
    pos, entry, e_idx, peak = False, math.nan, -1, math.nan
    stopped = enter = leave = False

    def book(x_idx, px, why):
        trades.append({"symbol": sym, "entry_idx": e_idx, "exit_idx": x_idx, "entry_day": m.days[e_idx].isoformat(),
                       "exit_day": m.days[x_idx].isoformat(), "entry_px": round(entry, 6), "exit_px": round(px, 6),
                       "gross": px / entry - 1.0, "hold": x_idx - e_idx, "exit": why})

    for d in range(m.n):
        new_seg = d == 0 or m.seg[d] != m.seg[d - 1]
        if new_seg:
            stopped = enter = leave = False
        else:
            if pos:
                r[d] += o[d] / c[d - 1] - 1.0
            if pos and leave:
                r[d] -= cost
                book(d, o[d], "signal")
                pos = False
            elif not pos and enter and np.isfinite(o[d]):
                pos, entry, e_idx, peak = True, o[d], d, o[d]
                r[d] -= cost
        if pos:
            hit = None
            if stop is not None:
                sp = (peak if trail else entry) * (1.0 - stop)
                if o[d] <= sp:
                    hit = o[d]
                elif lo[d] <= sp:
                    hit = sp
            if hit is not None:
                r[d] += hit / o[d] - 1.0 - cost
                book(d, hit, "stop")
                pos, stopped = False, True
            else:
                r[d] += c[d] / o[d] - 1.0
                peak = max(peak, c[d])
        if pos and ends[d]:
            r[d] -= cost
            book(d, c[d], "segment end")
            pos = False
        if above5[d]:
            stopped = False
        leave = pos and bool(above5[d])
        enter = (not pos) and (not stopped) and bool(sig[d])
        expo[d] = 1.0 if pos else 0.0
    return r, expo, trades


def trend_weights(m, sym="SPY"):
    sc = m.split_c[sym]
    s200 = per_segment(m, sc, lambda x: sma(x, SMA_LONG))
    with np.errstate(invalid="ignore"):
        return np.where(np.isfinite(s200) & (sc > s200), 1.0, 0.0)


def voltarget_weights(m, sym="SPY"):
    c = m.c[sym]

    def one(x):
        ret = pd.Series(x).pct_change()
        sig = (ret.rolling(VT_N, min_periods=VT_N).std() * math.sqrt(252)).to_numpy(float)
        out = np.zeros(len(x))
        held = 0.0
        for i in range(len(x)):
            if np.isfinite(sig[i]) and sig[i] > 0:
                raw = min(VT_CAP, VT_TARGET / sig[i])
                if abs(raw - held) > VT_BAND:
                    held = raw
            out[i] = held
        return out

    return per_segment(m, c, one)


def twoma_weights(m, sym="SPY"):
    sc = m.split_c[sym]

    def one(x):
        f, s = sma(x, MA_FAST), sma(x, MA_SLOW)
        out = np.zeros(len(x))
        pos, p1, armed = 0, math.nan, True
        for i in range(len(x)):
            if not (np.isfinite(f[i]) and np.isfinite(s[i])):
                continue
            up = f[i] > s[i]
            if not up:
                armed = True
            if pos == 0 and armed and up:
                pos, p1, armed = 1, x[i], False
            elif pos == 1 and (x[i] < MA_EXIT * p1 or not up):
                pos = 0
            out[i] = pos
        return out

    return per_segment(m, sc, one)


def psar(h, lo, start=PSAR_START, step=PSAR_STEP, amax=PSAR_MAX):
    """Wilder's Parabolic SAR on one segment. Returns (level, trend): level[i] is the SAR in effect during bar i, computed
    from bars before i only (the stop a position holds through bar i); trend[i] is +1 / -1 after bar i (a bar whose low
    goes under an up-trend's level, or whose high goes over a down-trend's level, reverses it). NaN / 0 before two bars.
    The first trend is up if bar 1's midpoint is above bar 0's. On a reversal the new trend's SAR starts at the old
    trend's extreme point and the acceleration factor resets."""
    n = len(h)
    level = np.full(n, np.nan)
    trend = np.zeros(n, int)
    idx = np.flatnonzero(np.isfinite(h) & np.isfinite(lo))
    if len(idx) < 2:
        return level, trend
    s0 = idx[0]
    if not np.all(np.isfinite(h[s0:])) or not np.all(np.isfinite(lo[s0:])):
        return level, trend
    up = (h[s0 + 1] + lo[s0 + 1]) > (h[s0] + lo[s0])
    sar = lo[s0] if up else h[s0]
    ep = h[s0 + 1] if up else lo[s0 + 1]
    af = start
    level[s0 + 1] = sar
    trend[s0 + 1] = 1 if up else -1
    for i in range(s0 + 2, n):
        s = sar + af * (ep - sar)
        if up:
            s = min(s, lo[i - 1], lo[i - 2])
            level[i] = s
            if lo[i] <= s:
                up, s, ep, af = False, ep, lo[i], start
            elif h[i] > ep:
                ep, af = h[i], min(af + step, amax)
        else:
            s = max(s, h[i - 1], h[i - 2])
            level[i] = s
            if h[i] >= s:
                up, s, ep, af = True, ep, h[i], start
            elif lo[i] < ep:
                ep, af = lo[i], min(af + step, amax)
        sar = s
        trend[i] = 1 if up else -1
    return level, trend


def psar_segments(m, sym):
    level = np.full(m.n, np.nan)
    trend = np.zeros(m.n, int)
    for a, b in m.segments():
        level[a:b], trend[a:b] = psar(m.h[sym][a:b], m.l[sym][a:b])
    return level, trend


def sim_psar_long(m, sym, cost, target_r=PSAR_TARGET_R):
    """T13 on one symbol, 100% of capital while long. Returns (daily return excluding cash, exposure, trades, skipped)."""
    level, trend = psar_segments(m, sym)
    flip_up = np.zeros(m.n, bool)
    flip_up[1:] = (trend[1:] == 1) & (trend[:-1] == -1) & (m.seg[1:] == m.seg[:-1])
    o, hi, lo, c = m.o[sym], m.h[sym], m.l[sym], m.c[sym]
    ends = _ends(m)
    r = np.zeros(m.n)
    expo = np.zeros(m.n)
    trades = []
    skipped = 0
    pos, entry, e_idx, target = False, math.nan, -1, math.nan
    enter = False

    def book(x_idx, px, why):
        trades.append({"symbol": sym, "entry_idx": e_idx, "exit_idx": x_idx, "entry_day": m.days[e_idx].isoformat(),
                       "exit_day": m.days[x_idx].isoformat(), "entry_px": round(entry, 6), "exit_px": round(px, 6),
                       "gross": px / entry - 1.0, "hold": x_idx - e_idx, "exit": why})

    for d in range(m.n):
        new_seg = d == 0 or m.seg[d] != m.seg[d - 1]
        if new_seg:
            enter = False
        else:
            if pos:
                r[d] += o[d] / c[d - 1] - 1.0
            if not pos and enter and np.isfinite(o[d]):
                if np.isfinite(level[d]) and o[d] > level[d]:
                    pos, entry, e_idx = True, o[d], d
                    target = entry + target_r * (entry - level[d])
                    r[d] -= cost
                else:
                    skipped += 1
        if pos:
            stop = level[d]
            fill = why = None
            if o[d] <= stop:
                fill, why = o[d], "stop"
            elif lo[d] <= stop:
                fill, why = stop, "stop"
            elif o[d] >= target:
                fill, why = o[d], "target"
            elif hi[d] >= target:
                fill, why = target, "target"
            if fill is not None:
                r[d] += fill / o[d] - 1.0 - cost
                book(d, fill, why)
                pos = False
            else:
                r[d] += c[d] / o[d] - 1.0
        if pos and ends[d]:
            r[d] -= cost
            book(d, c[d], "segment end")
            pos = False
        enter = (not pos) and bool(flip_up[d])
        expo[d] = 1.0 if pos else 0.0
    return r, expo, trades, skipped


def _ret_n(x, n=MOM_N):
    """Return over the last n sessions (NaN until n sessions exist)."""
    out = np.full(len(x), np.nan)
    if len(x) > n:
        with np.errstate(invalid="ignore", divide="ignore"):
            out[n:] = x[n:] / x[:-n] - 1.0
    return out


def month_end_mask(m):
    idx = m.index
    nxt = np.r_[idx.month[1:] != idx.month[:-1], True]
    return nxt


def rotation_weights(m):
    """T6 target weights {symbol: array}, decided at month-end closes and held until the next month end."""
    names = [s for s in SECTORS if m.has(s)]
    mom = {s: per_segment(m, m.c[s], _ret_n) for s in names}
    spy_s200 = per_segment(m, m.split_c["SPY"], lambda x: sma(x, SMA_LONG))
    me = month_end_mask(m)
    out = {s: np.zeros(m.n) for s in names + ["TLT"]}
    cur = {}
    for d in range(m.n):
        if d and m.seg[d] != m.seg[d - 1]:
            cur = {}
        if me[d]:
            cur = {}
            risk_on = np.isfinite(spy_s200[d]) and m.split_c["SPY"][d] > spy_s200[d]
            if risk_on:
                ranked = sorted(((mom[s][d], s) for s in names if np.isfinite(mom[s][d])), key=lambda t: (-t[0], t[1]))
                for _, s in ranked[:TOP_K]:
                    cur[s] = 1.0 / TOP_K
            elif m.has("TLT") and np.isfinite(m.c["TLT"][d]):
                cur["TLT"] = 1.0
        for s, v in cur.items():
            out[s][d] = v
    return out


def combine(m, rets, expos, shares):
    """Portfolio daily return: sum of share x asset return plus cash on the uninvested share (negative = borrowing)."""
    tot = np.zeros(m.n)
    ex = np.zeros(m.n)
    for k, s in shares.items():
        tot += s * rets[k]
        ex += s * expos[k]
    prev = np.r_[0.0, ex[:-1]]
    tot += (1.0 - 0.5 * (prev + ex)) * m.cash
    return tot, ex


def run_trials(m, cost):
    """All thirteen trials at one cost level. Returns {trial: {"r": daily returns, "expo": exposure, "trades": [...]}}."""
    out = {}
    sigs = {s: rsi2_signal(m, s) for s in RSI2_ETFS if m.has(s)}
    share = 1.0 / len(RSI2_ETFS)
    for name in RSI2_TRIALS:
        stop = STOPS.get(name)
        rets, expos, trades = {}, {}, []
        for s, (sig, ab) in sigs.items():
            rets[s], expos[s], t = sim_rsi2(m, s, stop, cost, sig, ab, trail=name in TRAILING)
            trades.extend(t)
        r, ex = combine(m, rets, expos, {s: share for s in sigs})
        out[name] = {"r": r, "expo": ex, "trades": trades}
    r5, e5 = sim_weights(m, "SPY", trend_weights(m), cost)
    out["T5_trend200"] = dict(zip(("r", "expo"), combine(m, {"SPY": r5}, {"SPY": e5}, {"SPY": 1.0})))
    w6 = rotation_weights(m)
    rets6, ex6 = {}, {}
    for s, w in w6.items():
        if m.has(s):
            rets6[s], ex6[s] = sim_weights(m, s, w, cost)
    out["T6_sector_dualmom"] = dict(zip(("r", "expo"), combine(m, rets6, ex6, {s: 1.0 for s in rets6})))
    r7, e7 = sim_weights(m, "SPY", voltarget_weights(m), cost)
    out["T7_voltarget"] = dict(zip(("r", "expo"), combine(m, {"SPY": r7}, {"SPY": e7}, {"SPY": 1.0})))
    r8, e8 = sim_weights(m, "SPY", twoma_weights(m), cost)
    out["T8_twoma_2pct"] = dict(zip(("r", "expo"), combine(m, {"SPY": r8}, {"SPY": e8}, {"SPY": 1.0})))
    a, b = out["T5_trend200"]["r"], out["T1_rsi2"]["r"]
    mix = 0.5 * a + 0.5 * b
    mix -= cost * 0.5 * np.abs(a - b) / (1.0 + mix)
    out["T9_mix"] = {"r": mix, "expo": 0.5 * out["T5_trend200"]["expo"] + 0.5 * out["T1_rsi2"]["expo"]}
    if m.has("GLD"):
        r13, e13, t13, sk13 = sim_psar_long(m, "GLD", cost)
        r13, e13 = combine(m, {"GLD": r13}, {"GLD": e13}, {"GLD": 1.0})
    else:                                   # GLD excluded by the data check: cash, no trades, the trial fails
        r13, e13 = combine(m, {}, {}, {})
        t13, sk13 = [], 0
    out["T13_gld_psar_long"] = {"r": r13, "expo": e13, "trades": t13, "skipped": sk13}
    for v in out.values():
        v.setdefault("trades", None)
    return out


# ------------------------------------------------------------------ statistics
def window_mask(m, name):
    a, b = WINDOWS[name]
    return np.array([a <= d <= b for d in m.days])


def series_stats(r, cash, mask):
    x = r[mask]
    if len(x) < 50:
        return None
    ex = x - cash[mask]
    sd = float(np.std(ex, ddof=1))
    eq = np.cumprod(1.0 + x)
    dd = float(np.min(eq / np.maximum.accumulate(eq) - 1.0))
    years = len(x) / 252.0
    return {"sessions": int(len(x)), "cagr": float(eq[-1] ** (1.0 / years) - 1.0), "vol": float(np.std(x, ddof=1) * math.sqrt(252)),
            "sharpe": float(np.mean(ex) / sd * math.sqrt(252)) if sd > 0 else None, "max_dd": dd, "total": float(eq[-1] - 1.0),
            "mean_excess_bps": float(np.mean(ex) * 1e4)}


def block_bootstrap(x, draws=BOOT_DRAWS, block=BOOT_BLOCK, seed=BOOT_SEED):
    """Circular block bootstrap of the mean. Returns (one-sided p for mean > 0 from the demeaned series, 95% CI of the
    mean from the raw series)."""
    x = np.asarray(x, float)
    n = len(x)
    obs = float(x.mean())
    rng = np.random.default_rng(seed)
    nb = int(math.ceil(n / block))
    means = np.empty(draws)
    done, chunk = 0, 500
    while done < draws:
        k = min(chunk, draws - done)
        st = rng.integers(0, n, size=(k, nb))
        idx = ((st[:, :, None] + np.arange(block)[None, None, :]) % n).reshape(k, -1)[:, :n]
        means[done:done + k] = x[idx].mean(axis=1)
        done += k
    p = float(np.mean(means - obs >= obs))
    lo, hi = np.percentile(means, [2.5, 97.5])
    return p, (float(lo), float(hi))


def trade_stats(trades, cost, m, mask):
    """F1-style trade metrics for trades that enter and exit inside the window, net of `cost` per side."""
    rows = [t for t in trades if mask[t["entry_idx"]] and mask[t["exit_idx"]]]
    if not rows:
        return {"trades": 0}
    net = np.array([t["gross"] - 2 * cost for t in rows])
    wins, losses = net[net > 0], net[net <= 0]
    gp, gl = float(wins.sum()), float(-losses.sum())
    days = np.array([t["entry_idx"] for t in rows])
    rng = np.random.default_rng(TRADE_BOOT_SEED)
    u = np.unique(days)
    groups = {d: net[days == d] for d in u}
    sums = np.array([groups[d].sum() for d in u])
    cnts = np.array([len(groups[d]) for d in u])
    bs = np.empty(TRADE_BOOT_DRAWS)
    for i in range(TRADE_BOOT_DRAWS):
        pick = rng.integers(0, len(u), len(u))
        bs[i] = sums[pick].sum() / cnts[pick].sum()
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return {"trades": int(len(rows)), "win_rate": float(np.mean(net > 0)), "avg_win": float(wins.mean()) if len(wins) else None,
            "avg_loss": float(losses.mean()) if len(losses) else None, "expectancy": float(net.mean()),
            "profit_factor": gp / gl if gl > 0 else None, "ci95": (float(lo), float(hi)),
            "stops": int(sum(1 for t in rows if t["exit"] == "stop")), "mean_hold": float(np.mean([t["hold"] for t in rows]))}


def random_control(trades, m, cost, mask, draws=CTRL_DRAWS, seed=CTRL_SEED):
    """Random entries: each window trade gets a random entry session of the same symbol with the same holding length
    (open-to-open, inside the window and one segment). Returns the observed mean, the draws' 95th percentile and the
    share of draws below the observed mean."""
    rows = [t for t in trades if mask[t["entry_idx"]] and mask[t["exit_idx"]]]
    if not rows:
        return None
    obs = float(np.mean([t["gross"] - 2 * cost for t in rows]))
    rng = np.random.default_rng(seed)
    total = np.zeros(draws)
    groups = {}
    for t in rows:
        groups.setdefault((t["symbol"], t["hold"]), 0)
        groups[(t["symbol"], t["hold"])] += 1
    idx = np.arange(m.n)
    for (sym, hold), k in sorted(groups.items()):
        o = m.o[sym]
        e = idx[: m.n - hold] if hold < m.n else idx[:0]
        x = e + hold
        ok = mask[e] & mask[x] & (m.seg[e] == m.seg[x]) & np.isfinite(o[e]) & np.isfinite(o[x])
        valid = e[ok]
        if not len(valid):
            continue
        pick = rng.choice(valid, size=(draws, k))
        total += (o[pick + hold] / o[pick] - 1.0 - 2 * cost).sum(axis=1)
    means = total / len(rows)
    return {"observed_mean": obs, "p95": float(np.percentile(means, 95)), "share_below": float(np.mean(means < obs)),
            "draws": draws, "trades": len(rows)}


def buy_hold(m, mask, sym="SPY"):
    c = m.c[sym]
    r = np.r_[0.0, c[1:] / c[:-1] - 1.0]
    r[np.r_[True, m.seg[1:] != m.seg[:-1]]] = 0.0
    r = np.nan_to_num(r)
    return series_stats(r, m.cash, mask), r


def evaluate(m, results_by_cost):
    """Statistics for every trial, window and cost level, the pass verdicts and the deflated Sharpe."""
    out = {"label": LABEL, "windows": {k: [a.isoformat(), b.isoformat()] for k, (a, b) in WINDOWS.items()},
           "alpha": ALPHA, "n_trials_total": N_PRIOR + N_ROUND, "trials": {}, "benchmark": {}}
    masks = {w: window_mask(m, w) for w in WINDOWS}
    for w, mk in masks.items():
        out["benchmark"][w] = buy_hold(m, mk)[0]
    out["benchmark_gld"] = {w: buy_hold(m, mk, "GLD")[0] for w, mk in masks.items()} if m.has("GLD") else {}
    fresh = masks[PASS_WINDOW]
    for name in TRIALS:
        row = {}
        for lvl, res in results_by_cost.items():
            tr = res[name]
            per = {}
            for w, mk in masks.items():
                s = series_stats(tr["r"], m.cash, mk)
                if s is not None and tr["trades"] is not None:
                    s["trade_stats"] = trade_stats(tr["trades"], COSTS[lvl], m, mk)
                per[w] = s
            row[lvl] = per
        res = results_by_cost[PASS_COST][name]
        ex = res["r"][fresh] - m.cash[fresh]
        p, ci = block_bootstrap(ex)
        row["pass_inputs"] = {"p_one_sided": p, "mean_excess_ci95_bps": [ci[0] * 1e4, ci[1] * 1e4]}
        if name in TRADE_TRIALS:
            row["random_control"] = random_control(res["trades"], m, COSTS[PASS_COST], fresh)
        if "skipped" in res:
            row["skipped_entries"] = int(res["skipped"])
        out["trials"][name] = row
    sh = {}
    for name in TRIALS:
        ex = results_by_cost[PASS_COST][name]["r"][fresh] - m.cash[fresh]
        sd = float(np.std(ex))
        sh[name] = float(np.mean(ex)) / sd if sd > 0 else 0.0
    sr_var = statistics.variance(sh.values()) if len(sh) > 1 else 0.0
    for name in TRIALS:
        ex = list(results_by_cost[PASS_COST][name]["r"][fresh] - m.cash[fresh])
        out["trials"][name]["deflated_sharpe"] = deflated_sharpe(ex, N_PRIOR + N_ROUND, sr_var)
    out["sr_var"] = sr_var
    out["verdicts"] = {name: verdict(name, out["trials"][name], out["benchmark"][PASS_WINDOW]) for name in TRIALS}
    return out


def verdict(name, row, bench):
    f = row[PASS_COST][PASS_WINDOW]
    if f is None or bench is None:
        return {"pass": False, "items": {}, "why": "no FRESH data"}
    items = {
        f"1 p < 0.05/{N_ROUND}": row["pass_inputs"]["p_one_sided"] < ALPHA,
        "2 drawdown smaller than SPY": f["max_dd"] > bench["max_dd"],
        "4 Sharpe over cash > 0": (f["sharpe"] or 0) > 0,
    }
    if name in TRADE_TRIALS:
        rc = row.get("random_control")
        items["3 beats 95% of random entries"] = bool(rc) and rc["observed_mean"] > rc["p95"]
    ok = all(items.values())
    return {"pass": ok, "items": items, "why": "all items hold" if ok else "failed: " + ", ".join(k for k, v in items.items() if not v)}


# ------------------------------------------------------------------ report
def _pct(x, n=1):
    return "-" if x is None else f"{x * 100:.{n}f}%"


def _f(x, n=2):
    return "-" if x is None else f"{x:.{n}f}"


def report_md(ev, data_note=""):
    L = [f"# Round 12 result ({ev['label']})", "",
         "Pre-registered in SPRINT_PLAN \"Round 12 pre-registration\" (2026-11-03). Pass/fail on FRESH "
         f"{ev['windows']['FRESH'][0]}..{ev['windows']['FRESH'][1]} at 2x costs (10 bps a side). "
         f"Deflated Sharpe at N = {ev['n_trials_total']:,} is reported, not a pass item.", ""]
    if data_note:
        L += [data_note, ""]
    b = ev["benchmark"]["FRESH"]
    L += ["## Verdicts (FRESH, 2x costs)", "",
          f"| Trial | Verdict | p (need < {ALPHA:.4f}) | Sharpe | CAGR | Max DD | Deflated Sharpe | Failed items |",
          "|---|---|---|---|---|---|---|---|"]
    for name in TRIALS:
        row, v = ev["trials"][name], ev["verdicts"][name]
        f = row["2x"]["FRESH"] or {}
        L.append(f"| {name} | {'PASS' if v['pass'] else 'FAIL'} | {_f(row['pass_inputs']['p_one_sided'], 4)} | {_f(f.get('sharpe'))} | "
                 f"{_pct(f.get('cagr'))} | {_pct(f.get('max_dd'))} | {_f(row['deflated_sharpe'], 4)} | "
                 f"{'' if v['pass'] else v['why'].replace('failed: ', '')} |")
    if b:
        L += ["", f"Buy-and-hold SPY on FRESH: Sharpe {_f(b['sharpe'])}, CAGR {_pct(b['cagr'])}, max DD {_pct(b['max_dd'])}."]
    g = (ev.get("benchmark_gld") or {}).get("FRESH")
    if g:
        L += [f"Buy-and-hold GLD on FRESH (information, for T13): Sharpe {_f(g['sharpe'])}, CAGR {_pct(g['cagr'])}, max DD {_pct(g['max_dd'])}."]
    L += ["", "## Every window (2x costs; information except FRESH)", "",
          "| Trial | Window | Sessions | CAGR | Sharpe | Max DD | Trades | Expectancy/trade | PF | Trade CI 95% |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name in TRIALS:
        for w in WINDOWS:
            s = ev["trials"][name]["2x"][w]
            if s is None:
                continue
            ts = s.get("trade_stats") or {}
            ci = ts.get("ci95")
            L.append(f"| {name} | {w} | {s['sessions']} | {_pct(s['cagr'])} | {_f(s['sharpe'])} | {_pct(s['max_dd'])} | "
                     f"{ts.get('trades', '-')} | {_pct(ts.get('expectancy'), 3)} | {_f(ts.get('profit_factor'))} | "
                     f"{'-' if not ci else _pct(ci[0], 3) + ' to ' + _pct(ci[1], 3)} |")
    L += ["", "| Benchmark SPY | Window | Sessions | CAGR | Sharpe | Max DD |", "|---|---|---|---|---|---|"]
    for w, s in ev["benchmark"].items():
        if s:
            L.append(f"| buy and hold | {w} | {s['sessions']} | {_pct(s['cagr'])} | {_f(s['sharpe'])} | {_pct(s['max_dd'])} |")
    L += ["", "## Random-entry control (trade-based trials: T1-T4, T10-T13; FRESH, 2x costs)", "", "| Trial | Trades | Mean net/trade | Random 95th pct | Share of draws below |",
          "|---|---|---|---|---|"]
    for name in TRADE_TRIALS:
        rc = ev["trials"][name].get("random_control")
        if rc:
            L.append(f"| {name} | {rc['trades']} | {_pct(rc['observed_mean'], 3)} | {_pct(rc['p95'], 3)} | {_f(rc['share_below'], 3)} |")
    L += ["", "## 1x costs (5 bps a side), FRESH", "", "| Trial | Sharpe | CAGR | Max DD |", "|---|---|---|---|"]
    for name in TRIALS:
        s = ev["trials"][name]["1x"]["FRESH"] or {}
        L.append(f"| {name} | {_f(s.get('sharpe'))} | {_pct(s.get('cagr'))} | {_pct(s.get('max_dd'))} |")
    L += ["", f"Every number above is a {ev['label']}. Not financial advice; a pass earns a forward paper ledger at most."]
    return "\n".join(L) + "\n"
