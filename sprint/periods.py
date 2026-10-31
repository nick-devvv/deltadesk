"""sprint/periods.py - the sprint's data periods and the locked-period refusal rule (docs/research/SPRINT_PLAN.md,
"Periods").

  DEV = 2024-08-01 .. 2026-06-30   free to explore
  NOT_SEEN_BY_OA = 2024-08-01 .. 2025-10-29   the part of DEV Option Alpha never saw (its window began 2025-10-30);
                                   used to cross-check Option Alpha's rules in the desk engine
  L1  = 2026-07-01 .. 2026-10-30   locked
  L2  = 2024-02-01 .. 2024-07-31   locked

Rule: any date range that overlaps L1 or L2 is REFUSED, by the data puller and by the runner, unless the caller
passes `locked=<the period name(s) it overlaps>` AND `frozen=<sha256 of the spec file>`, and that spec file is
tracked by git, has no uncommitted change, and its committed blob at HEAD has exactly that sha256. So a locked run
can only happen on finalist rules that were frozen and committed first. The refusal is an exception (LockedPeriod),
never a warning.

DEV warm-up: July 2024 is inside L2, so it is never pulled for warm-up. The first sessions of August 2024 therefore
have partial history (no prior-day levels on 2024-08-01, no prior-week levels in the first week, no 14-session
averages until mid-August). Features that need missing history are None, never estimated.

HIST = 2016-01-04 .. 2024-01-31 (SPRINT_PLAN Amendment 5): the free long-history check. Alpaca has stock 1-minute
bars there but no option prices, so HIST runs use stock bars only (Layer 1) or MODELED option tapes (Layer 2,
sprint/modeled.py). It ends the day before L2 starts, so the guard never has to make an exception for it. Its
stock history starts at WARMUP["HIST"] = 2015-11-01 (prior-day levels, ATRs and the 20-session IV proxy on day one);
the VIXY daily file starts at HIST_DAILY_FROM = 2014-11-01 (252 closes before 2016-01-04 for the VIXY percentile).
Trades are only taken inside the period itself; warm-up sessions only feed indicators.
"""
import hashlib
import subprocess
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

DEV = (date(2024, 8, 1), date(2026, 6, 30))
LOCKED = {"L1": (date(2026, 7, 1), date(2026, 10, 30)), "L2": (date(2024, 2, 1), date(2024, 7, 31))}
NOT_SEEN_BY_OA = (date(2024, 8, 1), date(2025, 10, 29))    # inside DEV; the part of it Option Alpha never saw
HIST = (date(2016, 1, 4), date(2024, 1, 31))                # stock bars only (+ MODELED option tapes); before L2
WARMUP = {"HIST": date(2015, 11, 1)}                        # history loaded before the period (indicators only)
HIST_DAILY_FROM = date(2014, 11, 1)                         # VIXY daily bars: 252 closes before HIST starts
OPTIONS_START = date(2024, 2, 1)                            # Alpaca has no option prices before this date
PERIODS = {"DEV": DEV, "NOT_SEEN_BY_OA": NOT_SEEN_BY_OA, "HIST": HIST, **LOCKED}
for _k, (_a, _b) in PERIODS.items():                        # every named non-locked period lies inside DEV, or is HIST
    assert _k in LOCKED or (DEV[0] <= _a <= _b <= DEV[1]) or _k == "HIST", _k
assert HIST[1] < LOCKED["L2"][0] and WARMUP["HIST"] < HIST[0] and HIST_DAILY_FROM < WARMUP["HIST"]
STRETCHES = [("Aug-Dec 2024", date(2024, 8, 1), date(2024, 12, 31)), ("2025", date(2025, 1, 1), date(2025, 12, 31)),
             ("Jan-Jun 2026", date(2026, 1, 1), date(2026, 6, 30))]
HIST_YEARS = list(range(2016, 2024))                        # the 8 full years counted by the pre-registered readings
HIST_STRETCHES = ([(str(y), date(y, 1, 1), date(y, 12, 31)) for y in HIST_YEARS] +
                  [("Jan 2024", date(2024, 1, 1), date(2024, 1, 31)),
                   ("2018 Q1 vol spike", date(2018, 1, 1), date(2018, 3, 31)),
                   ("2020 Feb-May", date(2020, 2, 1), date(2020, 5, 31)),
                   ("2022 bear market", date(2022, 1, 3), date(2022, 10, 12))])


def stretches_for(a=None, b=None):
    """The stretches a report uses for a run over [a, b]: HIST's years and named stretches for a range inside HIST
    (warm-up included), DEV's otherwise."""
    if a is not None and b is not None and _d(b) <= HIST[1]:
        return HIST_STRETCHES
    return STRETCHES


class LockedPeriod(RuntimeError):
    pass


def _d(x):
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def overlaps(a, b):
    """Names of the locked periods that [a, b] touches."""
    a, b = _d(a), _d(b)
    if b < a:
        raise ValueError(f"empty range {a}..{b}")
    return [k for k, (x, y) in LOCKED.items() if a <= y and b >= x]


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True)


def frozen_check(spec_path, sha, repo=None):
    """None if `spec_path` is committed, unchanged since the commit, and its committed content hashes to `sha`.
    Otherwise the reason it is not frozen (a string)."""
    p = Path(spec_path).resolve()
    if not p.exists():
        return f"spec file {spec_path} does not exist"
    if not sha or len(sha) != 64:
        return "--frozen needs the spec file's full sha256 (64 hex characters)"
    actual = sha256_file(p)
    if actual != sha.lower():
        return f"spec file sha256 is {actual}, not the frozen {sha}"
    top = _git(["rev-parse", "--show-toplevel"], repo or p.parent)
    if top.returncode != 0:
        return "not inside a git repository: a locked run needs the spec committed first"
    root = Path(top.stdout.decode().strip())
    rel = p.relative_to(root).as_posix()
    if _git(["ls-files", "--error-unmatch", rel], root).returncode != 0:
        return f"{rel} is not committed (git does not track it)"
    if _git(["diff", "--quiet", "HEAD", "--", rel], root).returncode != 0:
        return f"{rel} changed after it was committed (uncommitted edits)"
    blob = _git(["show", f"HEAD:{rel}"], root)
    if blob.returncode != 0:
        return f"{rel} is not in HEAD"
    if hashlib.sha256(blob.stdout).hexdigest() != sha.lower():
        return f"the committed {rel} does not hash to {sha}"
    return None


def guard(a, b, locked=None, frozen=None, spec_path=None, repo=None):
    """Raise LockedPeriod unless [a, b] avoids L1/L2, or the caller named every overlapped period in `locked` and
    the spec is frozen (see frozen_check). Returns the list of locked periods allowed for this call."""
    hit = overlaps(a, b)
    if not hit:
        return []
    names = {x.strip().upper() for x in (locked or "").split(",") if x.strip()} if isinstance(locked, str) else \
        {x.upper() for x in (locked or [])}
    if not names:
        raise LockedPeriod(f"REFUSED: {_d(a)}..{_d(b)} overlaps locked period(s) {', '.join(hit)} "
                           f"({', '.join(f'{k} {LOCKED[k][0]}..{LOCKED[k][1]}' for k in hit)}). "
                           "Locked periods run once, on frozen finalists only (--locked <name> --frozen <spec sha256>).")
    missing = [k for k in hit if k not in names]
    if missing:
        raise LockedPeriod(f"REFUSED: the range overlaps {', '.join(missing)} but --locked names only {', '.join(sorted(names))}")
    if not spec_path:
        raise LockedPeriod("REFUSED: a locked run needs the spec file (its frozen sha256 is checked against git)")
    why = frozen_check(spec_path, frozen, repo)
    if why:
        raise LockedPeriod(f"REFUSED: spec not frozen: {why}")
    return hit


def period_range(name):
    name = name.upper()
    if name not in PERIODS:
        raise ValueError(f"unknown period {name} ({', '.join(PERIODS)})")
    return PERIODS[name]


# NYSE full holidays and 1:00 PM early closes for the sprint years (core.py lists 2026-2027 only).
# Source: NYSE holiday calendars as published for 2024 and 2025 (incl. the 2025-01-09 national day of mourning).
HOLIDAYS_2024_2025 = {
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27", "2024-06-19", "2024-07-04", "2024-09-02",
    "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19", "2025-07-04",
    "2025-09-01", "2025-11-27", "2025-12-25",
}
EARLY_2024_2025 = {"2024-07-03", "2024-11-29", "2024-12-24", "2025-07-03", "2025-11-28", "2025-12-24"}


# 2015 (warm-up) to 2023, for HIST. Source: NYSE holiday and early-close calendars as published for each year,
# including the 2018-12-05 national day of mourning (President G. H. W. Bush). The HIST gap report lists every
# short session, so a missing early close shows up there.
HOLIDAYS_2015_2023 = {
    "2015-11-26", "2015-12-25",
    "2016-01-01", "2016-01-18", "2016-02-15", "2016-03-25", "2016-05-30", "2016-07-04", "2016-09-05", "2016-11-24",
    "2016-12-26",
    "2017-01-02", "2017-01-16", "2017-02-20", "2017-04-14", "2017-05-29", "2017-07-04", "2017-09-04", "2017-11-23",
    "2017-12-25",
    "2018-01-01", "2018-01-15", "2018-02-19", "2018-03-30", "2018-05-28", "2018-07-04", "2018-09-03", "2018-11-22",
    "2018-12-05", "2018-12-25",
    "2019-01-01", "2019-01-21", "2019-02-18", "2019-04-19", "2019-05-27", "2019-07-04", "2019-09-02", "2019-11-28",
    "2019-12-25",
    "2020-01-01", "2020-01-20", "2020-02-17", "2020-04-10", "2020-05-25", "2020-07-03", "2020-09-07", "2020-11-26",
    "2020-12-25",
    "2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02", "2021-05-31", "2021-07-05", "2021-09-06", "2021-11-25",
    "2021-12-24",
    "2022-01-17", "2022-02-21", "2022-04-15", "2022-05-30", "2022-06-20", "2022-07-04", "2022-09-05", "2022-11-24",
    "2022-12-26",
    "2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29", "2023-06-19", "2023-07-04", "2023-09-04",
    "2023-11-23", "2023-12-25",
}
EARLY_2015_2023 = {"2015-11-27", "2015-12-24", "2016-11-25", "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23",
                   "2018-12-24", "2019-07-03", "2019-11-29", "2019-12-24", "2020-11-27", "2020-12-24", "2021-11-26",
                   "2022-11-25", "2023-07-03", "2023-11-24"}


def holidays():
    import core
    return set(core.HOLIDAYS) | HOLIDAYS_2024_2025 | HOLIDAYS_2015_2023


def early_closes():
    import core
    return set(core.EARLY_CLOSE) | EARLY_2024_2025 | EARLY_2015_2023
