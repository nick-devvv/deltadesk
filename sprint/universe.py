"""sprint/universe.py - round 9's universes, the daily-bar panel and the locked-period rules for multi-day windows
(SPRINT_PLAN Amendment 12, pre-registered 2026-11-01 before any round-9 code, pull or run). Research only: no network.

Universes (Amendment 12 "Universes"):
  U-ETF  the 20 ETFs below (survivorship-free; all traded before 2016).
  U-STK  "all the stocks": every US common stock Alpaca lists today as active and tradable, with listed options. Alpaca's
         asset list (GET /v2/assets, read once by tools/sprint_pull9.py) has no security-type field, so "common stock" is
         decided from the asset record (is_common): class us_equity, status active, tradable, the "has_options" attribute,
         a listing exchange (NYSE, NASDAQ, AMEX, ARCA, BATS; OTC dropped), not a U-ETF symbol, a plain ticker shape, and a
         name that does not mark a fund or a non-common instrument (ETF, ETN, fund, index, trust units / units of beneficial
         interest, the ETF-only sponsors' brand names, leveraged/inverse products, warrants, rights, units, preferred /
         depositary shares, coupon securities, notes, American Depositary Shares/Receipts). Literal-reading notes:
           * ADRs are dropped (a depositary receipt is not common stock); foreign ordinary shares listed directly stay.
           * REITs' "common shares of beneficial interest" stay (they are the REIT's common equity); royalty-trust "units
             of beneficial interest" and MLP "common units" are dropped (units, not stock).
           * Brand names are only those of ETF-only sponsors (iShares, SPDR, ProShares, Direxion, ...). Sponsors that are
             also listed companies (Invesco, WisdomTree, Amplify Energy, ...) are not matched by brand; their funds are
             caught by "ETF"/"Fund"/"Trust ... Series" in the name instead.
           * An ADR or a fund whose Alpaca name says neither can slip through. Every exclusion and its reason is saved with
             the list (data/alpaca/universe/ustk.json) so it can be audited.
         The list is TODAY's survivors: SURVIVORSHIP-BIASED, labeled so everywhere.
  Point-in-time filter (U-STK, each day t): the prior close > $5 and the 20-session average dollar volume > $50 million,
         from RAW (unadjusted) daily bars of the sessions before t (a split-adjusted price would let a later split decide an
         earlier day). Trades use split-adjusted prices for signals and returns and the raw price for sizing
         (sprint/multiday.py), so a split during a holding window is neither a fake gain nor a fake loss.
Daily bars: data/alpaca/daily9/<raw|split>/<SYM>.csv.gz (tools/sprint_pull9.py), 2015-11-01..2026-06-30, L1/L2 cut out
         and never requested. Dividends are not credited (split-adjusted prices are price returns): conservative for the
         long-only Part F rules.
Rolling windows (SMA, RSI, the 20-session averages) run on each symbol's OWN bars: a session on which a symbol has no
         daily bar (no trade, or not listed yet) is skipped, not counted as zero. Literal reading of "SMA(200)" etc.: the
         last 200 bars of that symbol.
Locked periods and multi-day windows: a trade whose holding window [entry day, exit day] touches L1 or L2 is dropped
         entirely. The locked sessions are not in the panel, and no rolling window may reach across them: the panel is
         split into segments at L2 (2015-11..2024-01 and 2024-08..2026-06), and every window must lie inside one segment.
         An indicator whose look-back would need a locked session is undefined (NaN), never estimated from the sessions on
         the far side of the gap (the sprint's rule, sprint/periods.py). Consequence, stated before any run: SMA(200)
         exists in DEV only from its 200th session (about May 2025), and the U-STK filter from DEV's 21st session.
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
    (r"\bFund\b|\bFunds\b|\bIndex\b|\bPortfolio\b|\bTrust,? Series\b", "fund: fund/index/portfolio/trust series"),
    (r"\biShares\b|\bSPDR\b|ProShares|Direxion|VanEck|Global X|GraniteShares|Grayscale|Teucrium|\bYieldMax\b|\bRoundhill\b|"
     r"\bMicroSectors\b|CurrencyShares|\bUnited States (Oil|Natural Gas|Gasoline|Commodity|Brent|12 Month)\b", "fund: ETF sponsor/brand"),
    (r"\b(2x|3x|-1x|-2x|-3x|Leveraged|Inverse|Daily Bull|Daily Bear)\b", "fund: leveraged/inverse product"),
    (r"\bTrust Units?\b|\bUnits? of Beneficial Interest\b|\bRoyalty Trust\b", "trust units / royalty trust"),
    (r"\bWarrants?\b|\bRights?\b|\bUnits\b|\bUnit,? each\b|\bCommon Units?\b", "warrant / right / unit"),
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
    return [d for d in all_sessions_cal(a, b) if not periods.overlaps(d, d)]


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


def window_id(d):
    """0 = HIST, 1 = DEV, None = outside both (warm-up or locked)."""
    for k, (a, b) in enumerate(TRADE_WINDOWS):
        if a <= d <= b:
            return k
    return None


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
    """Date-indexed DataFrame o,h,l,c,v for one symbol, locked dates dropped (a second guard; they are never pulled)."""
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


def ever_eligible(raw):
    """False when a raw daily frame can never pass the U-STK filter (no close above $5 or no 20-bar mean dollar volume
    above $50M anywhere): such a symbol can never trade, so the panel need not hold it. A conservative prefilter."""
    if raw is None or len(raw) < DV_DAYS + 1:
        return False
    c, v = raw["c"].to_numpy(float), raw["v"].to_numpy(float)
    if not np.nanmax(c) > MIN_PRICE:
        return False
    dv = np.convolve(np.nan_to_num(c * v), np.ones(DV_DAYS) / DV_DAYS, mode="valid")
    return bool(len(dv) and dv.max() > MIN_DOLLAR_VOL)


def _segments(seg):
    """[(start, end)) index ranges of equal segment ids."""
    out, a = [], 0
    for k in range(1, len(seg) + 1):
        if k == len(seg) or seg[k] != seg[a]:
            out.append((a, k))
            a = k
    return out


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
            gap = any(self.days[k - 1] < x <= self.days[k] or self.days[k - 1] < y < self.days[k] for x, y in periods.LOCKED.values())
            self.seg[k] = self.seg[k - 1] + (1 if gap else 0)
        self.bounds = _segments(self.seg) if T else []
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
        self.missing = []
        self.skipped = []

    @classmethod
    def load(cls, symbols, root=None, days=None, log=None, prefilter=False):
        """prefilter=True (U-STK): symbols that can never pass the point-in-time filter are left out (they never trade)."""
        fa, fr, missing, skipped = {}, {}, [], []
        for n, s in enumerate(symbols):
            r = read_daily9(s, "raw", root)
            if prefilter and not ever_eligible(r):
                (missing if r is None else skipped).append(s)
                continue
            a = read_daily9(s, "split", root)
            if a is None:
                missing.append(s)
                continue
            fa[s], fr[s] = a, (r if r is not None else a)
            if log and n and n % 500 == 0:
                log(f"  daily bars: {n}/{len(symbols)} symbols read")
        p = cls([s for s in symbols if s in fa], fa, fr, days)
        p.missing, p.skipped = missing, skipped
        return p

    def idx(self, d):
        return self.pos.get(d)

    def same_seg(self, a, b):
        return self.seg[a] == self.seg[b]

    # ------------------------------------------------------------ per-symbol (compact) rolling windows
    def rolling_mean(self, X, n):
        """Mean of the symbol's last n bars ending at t (t's bar included), inside t's segment; NaN on days without a bar
        or with fewer than n earlier bars in the segment."""
        out = np.full(X.shape, np.nan)
        for a, b in self.bounds:
            blk = X[a:b]
            for j in range(X.shape[1]):
                col = blk[:, j]
                ix = np.flatnonzero(np.isfinite(col))
                if len(ix) < n:
                    continue
                cs = np.concatenate([[0.0], np.cumsum(col[ix])])
                out[a + ix[n - 1:], j] = (cs[n:] - cs[:-n]) / n
        return out

    def last_bar(self):
        """(T, N) index of the symbol's last bar at or before t inside t's segment (-1 if none)."""
        if "last" in self._cache:
            return self._cache["last"]
        T, N = self.adj_c.shape
        out = np.full((T, N), -1, dtype=np.int64)
        cur = np.full(N, -1, dtype=np.int64)
        fin = np.isfinite(self.raw_c) & np.isfinite(self.adj_c)
        for t in range(T):
            if t and self.seg[t] != self.seg[t - 1]:
                cur[:] = -1
            cur = np.where(fin[t], t, cur)
            out[t] = cur
        self._cache["last"] = out
        return out

    def prior_bar(self):
        """(T, N) index of the symbol's last bar strictly before t inside t's segment (-1 if none)."""
        if "prior" in self._cache:
            return self._cache["prior"]
        lb = self.last_bar()
        T = lb.shape[0]
        out = np.full(lb.shape, -1, dtype=np.int64)
        if T > 1:
            out[1:] = lb[:-1]
            out[1:][self.seg[1:] != self.seg[:-1]] = -1
        self._cache["prior"] = out
        return out

    def _at(self, X, ix):
        """X[ix[t, j], j] with NaN where ix < 0."""
        cols = np.arange(X.shape[1])[None, :]
        out = X[np.maximum(ix, 0), cols]
        return np.where(ix >= 0, out, np.nan)

    def sma(self, n):
        k = ("sma", n)
        if k not in self._cache:
            self._cache[k] = self.rolling_mean(self.adj_c, n)
        return self._cache[k]

    def rsi(self, n=2):
        """Wilder RSI(n) of split-adjusted closes on each symbol's own bars inside a segment: the first value averages the
        first n changes, then avg = (avg x (n - 1) + x) / n. avg loss 0 -> 100 (50 if the average gain is 0 too)."""
        k = ("rsi", n)
        if k in self._cache:
            return self._cache[k]
        C = self.adj_c
        T, N = C.shape
        out = np.full((T, N), np.nan)
        last = np.full(N, np.nan)
        cnt = np.zeros(N, int)
        sg, sl, ag, al = np.zeros(N), np.zeros(N), np.zeros(N), np.zeros(N)
        for t in range(T):
            if t and self.seg[t] != self.seg[t - 1]:
                last[:] = np.nan
                cnt[:] = 0
                sg[:] = sl[:] = ag[:] = al[:] = 0.0
            c = C[t]
            have = np.isfinite(c)
            ok = have & np.isfinite(last)
            ch = np.where(ok, c - np.where(np.isfinite(last), last, 0.0), 0.0)
            g, lo = np.maximum(ch, 0.0), np.maximum(-ch, 0.0)
            cnt = np.where(ok, cnt + 1, cnt)
            seeding = ok & (cnt <= n)
            sg = np.where(seeding, sg + g, sg)
            sl = np.where(seeding, sl + lo, sl)
            seed = ok & (cnt == n)
            more = ok & (cnt > n)
            ag = np.where(seed, sg / n, np.where(more, (ag * (n - 1) + g) / n, ag))
            al = np.where(seed, sl / n, np.where(more, (al * (n - 1) + lo) / n, al))
            with np.errstate(invalid="ignore", divide="ignore"):
                r = np.where(al > 0, 100.0 - 100.0 / (1.0 + ag / np.where(al > 0, al, 1.0)), np.where(ag > 0, 100.0, 50.0))
            out[t] = np.where(have & (cnt >= n), r, np.nan)
            last = np.where(have, c, last)
        self._cache[k] = out
        return out

    def eligible(self):
        """(T, N) bool: the U-STK point-in-time filter for day t: the symbol's last raw close before t > $5 and the mean raw
        dollar volume of its last 20 bars before t > $50M (both inside t's segment)."""
        if "elig" in self._cache:
            return self._cache["elig"]
        dv = self.rolling_mean(self.raw_c * self.raw_v, DV_DAYS)
        pb = self.prior_bar()
        pc, pdv = self._at(self.raw_c, pb), self._at(dv, pb)
        with np.errstate(invalid="ignore"):
            out = (pc > MIN_PRICE) & (pdv > MIN_DOLLAR_VOL)
        self._cache["elig"] = out
        return out

    def prior_close(self, adj=True):
        """(T, N) the symbol's last close before t (split-adjusted or raw), inside t's segment."""
        k = ("pc", adj)
        if k not in self._cache:
            self._cache[k] = self._at(self.adj_c if adj else self.raw_c, self.prior_bar())
        return self._cache[k]

    def adv_shares(self, n=20):
        """Mean split-adjusted daily volume of the symbol's last n bars before t (G1's RV15 denominator), NaN without them."""
        k = ("advs", n)
        if k not in self._cache:
            self._cache[k] = self._at(self.rolling_mean(self.adj_v, n), self.prior_bar())
        return self._cache[k]


def fnum(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x
