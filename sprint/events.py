"""sprint/events.py - pre-registered macro event calendar for the sprint's event-skip filters (no network).

FOMC statement days (the second day of each scheduled meeting). Source: Federal Reserve, "Meeting calendars,
statements, and minutes (2021-2027)", federalreserve.gov/monetarypolicy/fomccalendars.htm, read 2026-10-31:
  2024: Sep 17-18, Nov 6-7, Dec 17-18 (earlier 2024 meetings fall before DEV)
  2025: Jan 28-29, Mar 18-19, May 6-7, Jun 17-18, Jul 29-30, Sep 16-17, Oct 28-29, Dec 9-10
        (Aug 22, 2025 was a notation vote, not a meeting: not listed)
  2026: Jan 27-28, Mar 17-18, Apr 28-29, Jun 16-17, Jul 28-29, Sep 15-16, Oct 27-28, Dec 8-9 (same as config/v4.json)
CPI release days (8:30 AM ET). Source: BLS release calendars, bls.gov/schedule/2024/home.htm and
bls.gov/schedule/2025, read 2026-10-31. September 2025 CPI moved to Oct 24, 2025 (2025 lapse in appropriations);
no October 2025 CPI was published.
  2024: Aug 14, Sep 11, Oct 10, Nov 13, Dec 11
  2025: Jan 15, Feb 12, Mar 12, Apr 10, May 13, Jun 11, Jul 15, Aug 12, Sep 11, Oct 24, Dec 18
Coverage: CPI dates are listed for 2024-08-01..2025-12-31 only (2026 CPI dates were not read from BLS). On a date
outside that window the CPI state is UNKNOWN (None) and a CPI-skip filter does not trade that day (counted).
"""
from datetime import date

FOMC = frozenset({"2024-09-18", "2024-11-07", "2024-12-18",
                  "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
                  "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"})
FOMC_COVERAGE = (date(2024, 8, 1), date(2026, 12, 31))
CPI = frozenset({"2024-08-14", "2024-09-11", "2024-10-10", "2024-11-13", "2024-12-11",
                 "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10", "2025-05-13", "2025-06-11", "2025-07-15", "2025-08-12",
                 "2025-09-11", "2025-10-24", "2025-12-18"})
CPI_COVERAGE = (date(2024, 8, 1), date(2025, 12, 31))
SOURCES = {"FOMC": "federalreserve.gov/monetarypolicy/fomccalendars.htm (read 2026-10-31)",
           "CPI": "bls.gov/schedule/2024/home.htm and bls.gov/schedule/2025 (read 2026-10-31)"}


def _state(day, days, cov):
    d = day if isinstance(day, date) else date.fromisoformat(str(day))
    if not cov[0] <= d <= cov[1]:
        return None
    return d.isoformat() in days


def is_fomc(day):
    """True / False, or None outside the calendar's coverage."""
    return _state(day, FOMC, FOMC_COVERAGE)


def is_cpi(day):
    return _state(day, CPI, CPI_COVERAGE)
