"""sprint/universe.py - round 9's universes, the daily-bar panel and the locked-period rules for multi-day windows
(SPRINT_PLAN Amendment 12, pre-registered 2026-11-01 before any round-9 code, pull or run). Research only: no network.

Universes (Amendment 12 "Universes"):
  U-ETF  the 20 ETFs below (survivorship-free; all traded before 2016).
  U-STK  "all the stocks": every US common stock Alpaca lists today as active and tradable, with listed options. Alpaca's
         asset list has no security-type field, so "common stock" is decided from the asset record (build_ustk): class
         us_equity, status active, tradable, the "has_options" attribute, a listing exchange (NYSE, NASDAQ, AMEX, ARCA,
         BATS; OTC dropped), not a U-ETF symbol, and a name that does not mark a fund or a non-common instrument (ETF, ETN,
         fund, index, trust units, the big ETF sponsors' brand names, leveraged/inverse products, warrants, rights, units,
         preferred / depositary shares, notes, American Depositary Shares/Receipts). Literal-reading notes: ADRs are
         dropped because they are not US common stock; an ADR whose Alpaca name does not say so can slip through; a
         grantor trust named without a fund word can slip through. Every exclusion and its reason is saved with the list
         (data/alpaca/universe/ustk.json) so it can be audited. The list is TODAY's survivors: SURVIVORSHIP-BIASED.
  Point-in-time filter (U-STK, each day t): prior close > $5 and the 20-session average dollar volume > $50 million,
         both from RAW (unadjusted) daily bars of the sessions before t (a split-adjusted price would let a later split
         decide an earlier day). The trade itself uses split-adjusted prices for signals and returns and the raw price for
         sizing (sprint/multiday.py), so a split during a holding window is neither a fake gain nor a fake loss.
Daily bars: data/alpaca/daily9/<raw|split>/<SYM>.csv.gz (tools/sprint_pull9.py), 2015-11-01..2026-06-30, L1/L2 cut out
         and never requested. Dividends are not credited (split-adjusted prices are price returns): conservative for the
         long-only Part F rules.
Locked periods and multi-day windows: a trade whose holding window [entry day, exit day] touches L1 or L2 is dropped
         entirely. The locked sessions are not in the panel, so an indicator whose look-back would need a locked session
         is undefined (None/NaN), never estimated from the sessions on the far side of the gap (the sprint's rule, see
         sprint/periods.py). In practice: the panel is split into segments at L2 (2015-11..2024-01 and 2024-08..2026-06),
         and every rolling window (SMA, RSI, the 20-session filter) must lie inside one segment.
"""
import json
import math
import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import periods

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "data" / "alpaca"
U_ETF = ("SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "SMH", "XBI", "TLT", "GLD",
         "EEM", "EFA", "HYG")
TOM_ETF = ("SPY", "QQQ", "IWM", "DIA")
DAILY_FROM, DAILY_TO = date(2015, 11, 1), date(2026, 6, 30)
TRADE_WINDOWS = ((periods.HIST[0], periods.HIST[1]), (periods.DEV[0], periods.DEV[1]))
MIN_PRICE, MIN_DOLLAR_VOL, DV_DAYS = 5.0, 50e6, 20
SB = "SURVIVORSHIP-BIASED"
EXCHANGES = {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS", "NYSEARCA", "NYSEAMERICAN", "NYSEMKT"}
NOT_COMMON = [
    (r"\bETF\b|\bETFs\b|\bETN\b|\bETNs\b|Exchange[- ]Traded", "fund: ETF/ETN"),
    (r"\bFund\b|\bFunds\b|\bIndex\b|\bPortfolio\b", "fund: fund/index/portfolio"),
    (r"\biShares\b|\bSPDR\b|ProShares|Direxion|\bInvesco\b|Vanguard|WisdomTree|VanEck|Global X|GraniteShares|"
     r"\bARK\b|Grayscale|Teucrium|\bYieldMax\b|\bRoundhill\b|\bDefiance\b|\bTidal\b|\bAmplify\b|\bSchwab\b.*\b(ETF|Fund)\b|"
     r"\bMicroSectors\b|\bUnited States (Oil|Natural Gas|Gasoline|Commodity|Brent)\b", "fund: ETF sponsor/brand"),
    (r"\b(2x|3x|-1x|-2x|-3x|Ultra|UltraPro|Leveraged|Inverse|Daily Bull|Daily Bear)\b", "fund: leveraged/inverse product"),
    (r"\bTrust Units?\b|\bUnits? of Beneficial Interest\b|\bShares of Beneficial Interest\b", "trust units / beneficial interest"),
    (r"\bWarrants?\b|\bRights?\b|\bUnits?\b", "warrant / right / unit"),
    (r"\bPreferred\b|\bPfd\b|\bDepositary Shares?\b|\bSeries [A-Z]\b.*%|%", "preferred / depositary / coupon security"),
    (r"\bNotes?\b|\bDebentures?\b|\bBonds?\b", "notes / debt"),
    (r"American Depositary|\bADR\b|\bADS\b|\bADSs\b|\bADRs\b", "ADR (not US common stock)"),
]
_NOT_COMMON = [(re.compile(p, re.I), why) for p, why in NOT_COMMON]


# ---------------------------------------------------------------- the locked periods for multi-day windows
def touches_locked(a, b):
    """Names of the locked periods that the holding window [a, b] touches (entry day .. exit day, inclusive)."""
    return periods.overlaps(a, b)


def locked_free_segments(a, b):
    """[a, b] with every locked period cut out: [(start, end), ...] (as tools/sprint_pull.locked_free_segments)."""
    segs = [(a, b)]
    for x, y in periods.LOCKED.values():
        nxt = []
        for s, e in segs:
            if e < x or s > y:
                nxt.append((s, e))
                continue
            if s < x:
                nxt.append((s, x - timedelta(days=1)))
            if e > y:
                nxt.append((y + timedelta(days=1), e))
        segs = nxt
    return segs


def sessions(a=DAILY_FROM, b=DAILY_TO):
    """NYSE sessions in [a, b] (sprint/periods calendar), locked dates removed."""
    hol = periods.holidays()
    out, d = [], a
    while d <= b:
        if d.weekday() < 5 and d.isoformat() not in hol and not periods.overlaps(d, d):
            out.append(d)
        d += timedelta(days=1)
    return out


def all_sessions_cal(a, b):
    """NYSE sessions in [a, b] INCLUDING locked dates (for counting trading days across a window, never for reading)."""
    hol = periods.holidays()
    out, d = [], a
    while d <= b:
        if d.weekday() < 5 and d.isoformat() not in hol:
            out.append(d)
        d += timedelta(days=1)
    return out


def in_trade_window(d):
    return any(a <= d <= b for a, b in TRADE_WINDOWS)


# ---------------------------------------------------------------- U-STK from Alpaca's asset list
def is_common(asset):
    """(True, "") or (False, the reason) for one Alpaca asset record."""
    sym = str(asset.get("symbol") or "")
    if asset.get("class", "us_equity") != "us_equity":
        return False, "not us_equity"
    if asset.get("status") != "active":
        return False, "not active"
    if not asset.get("tradable"):
        return False, "not tradable"
    if "has_options" not in (asset.get("attributes") or []):
        return False, "no listed options"
    if str(asset.get("exchange") or "").upper() not in EXCHANGES:
        return False, f"exchange {asset.get('exchange')}"
    if sym in U_ETF:
        return False, "U-ETF symbol"
    if not re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", sym):
        return False, "symbol shape (not a plain common-stock ticker)"
    name = str(asset.get("name") or "")
    for rx, why in _NOT_COMMON:
        if rx.search(name):
            return False, why
    return True, ""


def build_ustk(assets):
    keep, excluded = [], {}
    for a in assets:
        ok, why = is_common(a)
        if ok:
            keep.append(a["symbol"])
        else:
            excluded[str(a.get("symbol"))] = why
    return {"symbols": sorted(set(keep)), "excluded": dict(sorted(excluded.items())), "n_assets": len(assets), "label": SB}


def read_ustk(root=None):
    f = Path(root or ROOT) / "universe" / "ustk.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


# ---------------------------------------------------------------- daily files and the panel
def daily_path(sym, adj="split", root=None):
    return Path(root or ROOT) / "daily9" / adj / f"{sym}.csv.gz"


def read_daily9(sym, adj="split", root=None):
    """{date-indexed DataFrame o,h,l,c,v} for one symbol, locked dates dropped (a second guard; they are never pulled)."""
    f = daily_path(sym, adj, root)
    if not f.exists():
        return None
    df = pd.read_csv(f, compression="gzip")
    if not len(df):
        return pd.DataFrame(columns=["o", "h", "l", "c", "v"])
    d = pd.to_datetime(df["ts"], utc=True, format="ISO8601").dt.tz_convert("America/New_York").dt.date
    df = df.assign(day=d).drop_duplicates("day", keep="last").set_index("day").sort_index()
    keep = [not periods.overlaps(x, x) for x in df.index]
    return df.loc[keep, ["o", "h", "l", "c", "v"]].astype(float)


class Panel:
    """Daily bars of many symbols on one session grid (locked sessions removed). Arrays are (sessions, symbols), NaN where
    a symbol has no bar. adj_* = split-adjusted, raw_* = unadjusted. seg[t] = the segment (0 before L2, 1 after)."""

    def __init__(self, symbols, frames_adj, frames_raw=None, days=None):
        self.symbols = list(symbols)
        self.col = {s: k for k, s in enumerate(self.symbols)}
        self.days = list(days or sessions())
        self.pos = {d: k for k, d in enumerate(self.days)}
        T, N = len(self.days), len(self.symbols)
        self.seg = np.zeros(T, int)
        for k in range(1, T):
            gap = any(self.days[k - 1] < x and y < self.days[k] or (self.days[k - 1] < x <= self.days[k])
                      for x, y in periods.LOCKED.values())
            self.seg[k] = self.seg[k - 1] + (1 if gap else 0)
        z = lambda: np.full((T, N), np.nan)
        self.adj_o, self.adj_c, self.adj_v, self.raw_o, self.raw_c, self.raw_v = z(), z(), z(), z(), z(), z()
        for s in self.symbols:
            j = self.col[s]
            for frames, (o_, c_, v_) in ((frames_adj, (self.adj_o, self.adj_c, self.adj_v)),
                                        (frames_raw if frames_raw is not None else frames_adj, (self.raw_o, self.raw_c, self.raw_v))):
                df = frames.get(s) if frames else None
                if df is None or not len(df):
                    continue
                idx = [self.pos.get(d) for d in df.index]
                ok = np.array([i is not None for i in idx])
                if not ok.any():
                    continue
                rows = np.array([i for i in idx if i is not None])
                o_[rows, j] = df["o"].to_numpy(float)[ok]
                c_[rows, j] = df["c"].to_numpy(float)[ok]
                v_[rows, j] = df["v"].to_numpy(float)[ok]
        self._cache = {}

    @classmethod
    def load(cls, symbols, root=None, days=None, log=None):
        fa, fr, missing = {}, {}, []
        for n, s in enumerate(symbols):
            a = read_daily9(s, "split", root)
            r = read_daily9(s, "raw", root)
            if a is None:
                missing.append(s)
                continue
            fa[s], fr[s] = a, (r if r is not None else a)
            if log and n and n % 500 == 0:
                log(f"  daily bars: {n}/{len(symbols)} symbols read")
        p = cls([s for s in symbols if s in fa], fa, fr, days)
        p.missing = missing
        return p

    def idx(self, d):
        return self.pos.get(d)

    def window_ok(self, n):
        """(T,) bool: the n sessions ending at t lie in one segment."""
        T = len(self.days)
        ok = np.zeros(T, bool)
        if n <= T:
            ok[n - 1:] = self.seg[n - 1:] == self.seg[:T - n + 1]
        return ok

    def rolling_mean(self, X, n):
        """Mean of the n values ending at t (t included); NaN unless all n are present and in one segment."""
        T = X.shape[0]
        V = np.isfinite(X)
        cs = np.vstack([np.zeros((1, X.shape[1])), np.cumsum(np.where(V, X, 0.0), axis=0)])
        cn = np.vstack([np.zeros((1, X.shape[1])), np.cumsum(V, axis=0)])
        out = np.full(X.shape, np.nan)
        if n > T:
            return out
        s = cs[n:] - cs[:-n]
        c = cn[n:] - cn[:-n]
        with np.errstate(invalid="ignore", divide="ignore"):
            m = np.where(c == n, s / n, np.nan)
        out[n - 1:] = m
        out[~self.window_ok(n)] = np.nan
        return out

    def sma(self, n):
        k = ("sma", n)
        if k not in self._cache:
            self._cache[k] = self.rolling_mean(self.adj_c, n)
        return self._cache[k]

    def rsi(self, n=2):
        """Wilder RSI(n) of split-adjusted closes: the first value averages the first n changes of a run of consecutive
        closes inside one segment, then avg = (avg x (n - 1) + x) / n. A missing close or a segment break restarts it.
        avg loss 0 -> 100 (50 if the average gain is 0 too)."""
        k = ("rsi", n)
        if k in self._cache:
            return self._cache[k]
        C = self.adj_c
        T, N = C.shape
        out = np.full((T, N), np.nan)
        ag, al, cnt = np.zeros(N), np.zeros(N), np.zeros(N, int)
        sg, sl = np.zeros(N), np.zeros(N)
        for t in range(1, T):
            ch = C[t] - C[t - 1]
            ok = np.isfinite(ch) & (self.seg[t] == self.seg[t - 1])
            cnt = np.where(ok, cnt + 1, 0)
            g, l = np.where(ok, np.maximum(ch, 0.0), 0.0), np.where(ok, np.maximum(-ch, 0.0), 0.0)
            sg = np.where(ok, np.where(cnt <= n, sg + g, sg), 0.0)
            sl = np.where(ok, np.where(cnt <= n, sl + l, sl), 0.0)
            seed = cnt == n
            ag = np.where(seed, sg / n, np.where(cnt > n, (ag * (n - 1) + g) / n, 0.0))
            al = np.where(seed, sl / n, np.where(cnt > n, (al * (n - 1) + l) / n, 0.0))
            have = cnt >= n
            with np.errstate(invalid="ignore", divide="ignore"):
                r = np.where(al > 0, 100.0 - 100.0 / (1.0 + ag / np.where(al > 0, al, 1.0)), np.where(ag > 0, 100.0, 50.0))
            out[t] = np.where(have, r, np.nan)
        self._cache[k] = out
        return out

    def eligible(self):
        """(T, N) bool: the U-STK point-in-time filter for day t (prior raw close > $5 and the mean raw dollar volume of the
        20 sessions before t > $50M; t-1 .. t-20 and t in one segment)."""
        if "elig" in self._cache:
            return self._cache["elig"]
        dv = self.rolling_mean(self.raw_c * self.raw_v, DV_DAYS)
        T = len(self.days)
        out = np.zeros(self.adj_c.shape, bool)
        if T > 1:
            same = np.concatenate([[False], self.seg[1:] == self.seg[:-1]])
            prev_c, prev_dv = np.vstack([np.full((1, out.shape[1]), np.nan), self.raw_c[:-1]]), np.vstack(
                [np.full((1, out.shape[1]), np.nan), dv[:-1]])
            with np.errstate(invalid="ignore"):
                out = (prev_c > MIN_PRICE) & (prev_dv > MIN_DOLLAR_VOL) & same[:, None]
        self._cache["elig"] = out
        return out

    def adv_shares(self, n=20):
        """Mean split-adjusted daily volume of the n sessions before t (G1's RV15 denominator), NaN without them."""
        k = ("advs", n)
        if k not in self._cache:
            m = self.rolling_mean(self.adj_v, n)
            prev = np.vstack([np.full((1, m.shape[1]), np.nan), m[:-1]])
            same = np.concatenate([[False], self.seg[1:] == self.seg[:-1]]) if len(self.days) > 1 else np.zeros(len(self.days), bool)
            prev[~same] = np.nan
            self._cache[k] = prev
        return self._cache[k]


def fnum(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x
