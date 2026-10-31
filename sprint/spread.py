"""sprint/spread.py - the half-spread model used by the fill rules (docs/research/SPRINT_PLAN.md, "Cost model").

Alpaca's option history has trades and bars but no quotes, so a fill is the traded price +/- k x half-spread. The
half-spread comes from:
  1. MEASURED-SPREAD: the desk's own logged chains (data/chains/<day>.csv[.gz], written by chain_logger.py) when
     present: 0DTE rows with a valid two-sided quote, median half-spread in dollars per underlying, by premium bucket
     (mid) and time-of-day bucket (09:30-10:00, 10:00-15:00, 15:00-16:00). A cell needs MIN_CELL rows, otherwise the
     premium-bucket median over all times is used, otherwise the default below.
  2. MODELED-SPREAD (default): 5% of the premium for SPY/QQQ/IWM (index ETFs), 10% for single stocks. Floor: half a
     $0.01 tick ($0.005), because a listed option spread can't be under one tick.
Every result carries its label, and the run log names the model used.
"""
import csv
import gzip
import io
import statistics
from pathlib import Path

INDEX_ETFS = {"SPY", "QQQ", "IWM", "DIA", "XSP", "SPX"}
DEFAULT_PCT_INDEX = 0.05
DEFAULT_PCT_STOCK = 0.10
TICK_HALF = 0.005
MIN_CELL = 50
PREMIUM_BUCKETS = (0.25, 0.5, 1.0, 2.0, 4.0)            # bucket edges on the mid
TIME_BUCKETS = (30, 330)                                # minutes after 09:30: [0,30), [30,330), [330,390)


def _pb(mid):
    for i, e in enumerate(PREMIUM_BUCKETS):
        if mid < e:
            return i
    return len(PREMIUM_BUCKETS)


def _tb(minute):
    return 0 if minute < TIME_BUCKETS[0] else 1 if minute < TIME_BUCKETS[1] else 2


class SpreadModel:
    def __init__(self, table=None, coverage=None):
        self.table = table or {}            # (under, pb, tb) -> median half-spread $, (under, pb, None) -> all times
        self.coverage = coverage or {}      # under -> {"days": n, "rows": n}

    @property
    def label(self):
        return "MEASURED-SPREAD" if self.table else "MODELED-SPREAD"

    def describe(self):
        if not self.table:
            return (f"MODELED-SPREAD: half-spread = {DEFAULT_PCT_INDEX:.0%} of premium (SPY/QQQ/IWM), "
                    f"{DEFAULT_PCT_STOCK:.0%} single stocks, floor ${TICK_HALF}")
        cov = ", ".join(f"{u} {c['days']} days/{c['rows']} rows" for u, c in sorted(self.coverage.items()))
        return f"MEASURED-SPREAD from logged chains ({cov}); MODELED-SPREAD default where a cell is thin"

    def half_spread(self, under, px, minute=None):
        """(half-spread in $, label) for an option of underlying `under` trading at `px`, `minute` after 09:30."""
        px = max(float(px), 0.0)
        if self.table:
            pb = _pb(px)
            if minute is not None:
                v = self.table.get((under, pb, _tb(minute)))
                if v is not None:
                    return max(v, TICK_HALF), "MEASURED-SPREAD"
            v = self.table.get((under, pb, None))
            if v is not None:
                return max(v, TICK_HALF), "MEASURED-SPREAD"
        pct = DEFAULT_PCT_INDEX if under in INDEX_ETFS else DEFAULT_PCT_STOCK
        return max(pct * px, TICK_HALF), "MODELED-SPREAD"

    def spread_ok(self, under, px, minute, cap=0.10):
        """Spread cap (~10% of price) applies only when the spread is MEASURED (a modeled spread is not a quote)."""
        hs, lab = self.half_spread(under, px, minute)
        if lab != "MEASURED-SPREAD" or px <= 0:
            return True
        return 2 * hs / px <= cap


def _rows(path):
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return csv.DictReader(io.StringIO(raw.decode()))


def from_chains(folder, unders=None):
    """Build a SpreadModel from data/chains/*.csv(.gz). Returns the default model if the folder is missing/empty."""
    folder = Path(folder)
    if not folder.exists():
        return SpreadModel()
    cells, days = {}, {}
    files = sorted(folder.glob("*.csv.gz")) + [p for p in sorted(folder.glob("*.csv"))
                                               if not (folder / (p.name + ".gz")).exists()]
    for f in files:
        day = f.name[:10]
        try:
            for r in _rows(f):
                u = (r.get("underlying") or "").lstrip("$")
                if unders and u not in unders:
                    continue
                if (r.get("expiry") or "")[:10] != day:
                    continue                                   # 0DTE only
                try:
                    bid, ask = float(r["bid"]), float(r["ask"])
                except (TypeError, ValueError, KeyError):
                    continue
                if bid <= 0 or ask <= bid:
                    continue
                t = str(r.get("logged_at") or "")
                try:
                    hh, mm = int(t[11:13]), int(t[14:16])
                except ValueError:
                    continue
                minute = hh * 60 + mm - 570
                if not 0 <= minute < 390:
                    continue
                mid, hs = (bid + ask) / 2, (ask - bid) / 2
                for key in ((u, _pb(mid), _tb(minute)), (u, _pb(mid), None)):
                    cells.setdefault(key, []).append(hs)
                days.setdefault(u, {"days": set(), "rows": 0})
                days[u]["days"].add(day)
                days[u]["rows"] += 1
        except (OSError, ValueError, EOFError):
            continue
    table = {k: statistics.median(v) for k, v in cells.items() if len(v) >= MIN_CELL}
    cov = {u: {"days": len(c["days"]), "rows": c["rows"]} for u, c in days.items()}
    return SpreadModel(table, cov)
