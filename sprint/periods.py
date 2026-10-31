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
"""
import hashlib
import subprocess
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

DEV = (date(2024, 8, 1), date(2026, 6, 30))
LOCKED = {"L1": (date(2026, 7, 1), date(2026, 10, 30)), "L2": (date(2024, 2, 1), date(2024, 7, 31))}
NOT_SEEN_BY_OA = (date(2024, 8, 1), date(2025, 10, 29))    # inside DEV; the part of it Option Alpha never saw
PERIODS = {"DEV": DEV, "NOT_SEEN_BY_OA": NOT_SEEN_BY_OA, **LOCKED}
for _k, (_a, _b) in PERIODS.items():                        # every named non-locked period lies inside DEV
    assert _k in LOCKED or (DEV[0] <= _a <= _b <= DEV[1]), _k
STRETCHES = [("Aug-Dec 2024", date(2024, 8, 1), date(2024, 12, 31)), ("2025", date(2025, 1, 1), date(2025, 12, 31)),
             ("Jan-Jun 2026", date(2026, 1, 1), date(2026, 6, 30))]


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


def holidays():
    import core
    return set(core.HOLIDAYS) | HOLIDAYS_2024_2025


def early_closes():
    import core
    return set(core.EARLY_CLOSE) | EARLY_2024_2025
