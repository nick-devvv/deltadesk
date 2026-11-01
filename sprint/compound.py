"""sprint/compound.py - the compounding view (SPRINT_PLAN Amendment 16, "Compounding view"; information, not trials).

Nick's "compound and scale" question, answered from the numbers: for a rule that passed its pre-registered bars, how would a
$3,000 account have done if every trade risked a fixed fraction (1%, 2% or 5%) of the account, over 2,000 bootstrap paths of
the rule's holdout results resampled by session? Every number it returns is a simulation built from BACKTEST results
(labeled so by the caller: REAL / MODELED options, real shares). Research only: no network, no orders.

INPUT (one call = one rule on one window; generic, so every round-10 part can call it):

  rows      The rule's results, as a list of dicts or a pandas DataFrame, in either form:
              per trade, in dollars:   {"day": session date, "pnl": $ P/L at the rule's pre-registered size,
                                        "risk": $ that trade put at risk at the same size (> 0)}
                  "risk" is the caller's pre-registered loss unit for that trade: the debit of a long option, the planned
                  loss at a stop, a spread's margin (width - credit), ... The trade's result in risk units is r = pnl / risk.
              per trade or per session, already in risk units:   {"day": session date, "r": P/L / risk}
                  (a per-session row is the sum of that session's trades' r).
            "day" is an ISO "YYYY-MM-DD" string (longer strings are cut to 10 characters) or a datetime.date. When a row has
            "r" it is used as given; otherwise "pnl" and "risk" are required. Several rows on one day are one session: their
            r are summed. Extra keys are ignored.
  sessions  Every session of the window (ISO strings or dates), INCLUDING the days the rule did not trade (r = 0 there).
            Strongly recommended: without it only the days with a trade are resampled, which overstates how often the rule
            trades. Every row's day must be in it (ValueError otherwise), and it may not repeat a day.
  start, fractions, paths, seed, halve: $3,000; (0.01, 0.02, 0.05); 2,000; 29; 0.5 (the pre-registered view; the seed is
            Part A's bootstrap seed, fixed so a re-run gives identical numbers).

MODEL
  * A path is len(sessions) sessions drawn with replacement from `sessions` (numpy default_rng(seed); one draw is shared by
    every fraction, so the fractions differ only in sizing).
  * Fixed-fractional risk f: every trade risks f x the balance at the START of its session (trades of one session can be
    open at the same time, so none is sized off another's result): balance_after = balance_before x (1 + f x r_session).
    Share or contract rounding is ignored (a $3,000 account cannot buy fractional contracts: information only).
  * A session that would take the balance to 0 or below ruins the path (the balance stays 0 from then on).
  * Balances are marked at session closes only; intraday swings are not modeled.

OUTPUT (a dict; JSON-safe) per fraction ("1%", "2%", "5%"):
  median_end, p5_end    the median and 5th-percentile ending balance;
  worst_dd_pct          the worst drawdown: the deepest peak-to-trough fall of any path's session-close balance, in % of its
                        running peak (the peak includes the $3,000 start), over all paths;
  p_halve               the chance of halving the account: the share of paths whose session-close balance is at or below
                        start x 0.5 ($1,500) at any session;
  and, as information: mean_end, median_dd_pct and p5_dd_pct (the median and 5th-percentile per-path max drawdown),
  p_end_below_start, p_ruin.
Plus "input": trades, sessions, sessions with a trade, years (sessions / 252), the mean r per trade and per session.

Rows dated inside the locked periods L1 (2026-07-01..10-30) or L2 (2024-02-01..07-31) are refused (periods.LockedPeriod).
"""
import math
from datetime import date

import numpy as np

from . import periods

START = 3000.0
FRACTIONS = (0.01, 0.02, 0.05)
PATHS = 2000
SEED = 29
HALVE = 0.5
YEAR = 252
LABEL = ("compounding view (information, not trials): fixed-fractional risk on a $3,000 account, 2,000 bootstrap paths of "
         "the holdout sessions, resampled by session")


def _day(x):
    if isinstance(x, date):
        return x.isoformat()
    s = str(x)[:10]
    date.fromisoformat(s)                                  # ValueError on a malformed day
    return s


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _records(rows):
    if hasattr(rows, "to_dict") and hasattr(rows, "columns"):
        return rows.to_dict("records")
    return list(rows or [])


def trade_r(row):
    """A row's result in risk units: its "r" if present, else pnl / risk (risk must be > 0)."""
    if "r" in row and _num(row.get("r")) is not None:
        return _num(row["r"])
    pnl, risk = _num(row.get("pnl")), _num(row.get("risk"))
    if pnl is None or risk is None:
        raise ValueError(f"a row needs 'r', or 'pnl' and 'risk' (day {row.get('day')}): {row}")
    if risk <= 0:
        raise ValueError(f"risk must be > 0 (day {row.get('day')}, risk {risk})")
    return pnl / risk


def session_r(rows, sessions=None):
    """(sessions, r per session, trades per session): the rows summed by session, 0 on sessions without a row."""
    recs = _records(rows)
    by = {}
    cnt = {}
    for r in recs:
        d = _day(r["day"])
        hit = periods.overlaps(d, d)
        if hit:
            raise periods.LockedPeriod(f"REFUSED: a compounding row on {d} is inside locked period {', '.join(hit)}")
        by[d] = by.get(d, 0.0) + trade_r(r)
        cnt[d] = cnt.get(d, 0) + 1
    if sessions is None:
        days = sorted(by)
    else:
        days = [_day(s) for s in sessions]
        if len(set(days)) != len(days):
            raise ValueError("sessions repeats a day")
        known = set(days)
        miss = sorted(d for d in by if d not in known)
        if miss:
            raise ValueError(f"{len(miss)} row day(s) are not in sessions, e.g. {miss[:3]}")
        for d in days:
            hit = periods.overlaps(d, d)
            if hit:
                raise periods.LockedPeriod(f"REFUSED: session {d} is inside locked period {', '.join(hit)}")
    rs = np.array([by.get(d, 0.0) for d in days], float)
    n = np.array([cnt.get(d, 0) for d in days], int)
    return days, rs, n


def _r(x, n=2):
    return None if x is None or not math.isfinite(float(x)) else round(float(x), n)


def simulate(rows, sessions=None, start=START, fractions=FRACTIONS, paths=PATHS, seed=SEED, halve=HALVE, label=None):
    """The compounding view of one rule on one window (see the module docstring for the input format)."""
    days, rs, n = session_r(rows, sessions)
    S = len(days)
    if S == 0:
        raise ValueError("no sessions to resample")
    if paths < 1 or start <= 0:
        raise ValueError("paths must be >= 1 and start > 0")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, S, size=(paths, S))
    R = rs[idx]
    out = {"label": label or LABEL, "start": start, "paths": int(paths), "seed": int(seed), "halve_at": round(start * halve, 2),
           "input": {"trades": int(n.sum()), "sessions": S, "sessions_with_trades": int((n > 0).sum()), "years": round(S / YEAR, 2),
                     "first": days[0], "last": days[-1],
                     "mean_r_trade": _r(rs.sum() / n.sum(), 4) if n.sum() else None, "mean_r_session": _r(rs.mean(), 4),
                     "sd_r_session": _r(rs.std(), 4)},
           "fractions": {}}
    head = np.full((paths, 1), float(start))
    for f in fractions:
        g = np.maximum(1.0 + f * R, 0.0)
        bal = start * np.cumprod(g, axis=1)
        peak = np.maximum.accumulate(np.concatenate([head, bal], axis=1), axis=1)[:, 1:]
        dd = (bal / peak - 1.0).min(axis=1) * 100.0
        end = bal[:, -1]
        out["fractions"][f"{f * 100:g}%"] = {
            "risk_fraction": f, "median_end": _r(np.median(end)), "p5_end": _r(np.percentile(end, 5)), "worst_dd_pct": _r(dd.min(), 1),
            "p_halve": _r((bal <= start * halve).any(axis=1).mean(), 4), "mean_end": _r(end.mean()),
            "median_dd_pct": _r(np.median(dd), 1), "p5_dd_pct": _r(np.percentile(dd, 5), 1),
            "p_end_below_start": _r((end < start).mean(), 4), "p_ruin": _r((end <= 0).mean(), 4)}
    return out


def render_md(view, title="Compounding view"):
    """Markdown lines for one simulate() result."""
    if not view:
        return []
    i = view["input"]
    L = [f"- **{title}** ({view['label']}; {i['sessions']} sessions = {i['years']} years, {i['trades']} trades on "
         f"{i['sessions_with_trades']} sessions, mean r a trade {i['mean_r_trade']}, seed {view['seed']}):", "",
         "| risk a trade | median end $ | 5th pct end $ | worst drawdown % | chance of halving | mean end $ | median max DD % | "
         "ends below start | ruined |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in view["fractions"].items():
        L.append(f"| {k} | {v['median_end']} | {v['p5_end']} | {v['worst_dd_pct']} | {v['p_halve']} | {v['mean_end']} | "
                 f"{v['median_dd_pct']} | {v['p_end_below_start']} | {v['p_ruin']} |")
    L.append("")
    return L
