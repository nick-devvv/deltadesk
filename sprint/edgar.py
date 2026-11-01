"""sprint/edgar.py - SEC EDGAR 8-K events for round 9's Part G (SPRINT_PLAN Amendment 12, pre-registered 2026-11-01 before
any round-9 code, pull or run). Parsing, timing and the rate limiter; the network calls live in tools/sprint_pull9.py and
go through an injectable fetch function, so everything here is testable offline.

Source (Amendment 12 "Event source"): the EDGAR daily form indexes
  https://www.sec.gov/Archives/edgar/daily-index/<YYYY>/QTR<q>/form.<YYYYMMDD>.idx
plus each filing's index headers
  https://www.sec.gov/Archives/edgar/data/<CIK>/<accession without dashes>/<accession>-index-headers.html
which carry <ACCEPTANCE-DATETIME>YYYYMMDDHHMMSS (EDGAR's acceptance time, US Eastern) and one "ITEM INFORMATION:" line per
8-K item (the item's title; mapped to its number below), or <ITEMS>n.nn tags in the SGML form of the same header.
Fair access: at most 10 requests a second (Throttle: one request every 0.11 s or slower) with the desk's SEC_USER_AGENT
(catalysts.sec_headers); never a personal value written into code. A refused / rate-limited answer (403, 429, 503) backs
off 15, 30, 60, 120, 240 s and then stops with an error (the pull resumes on the next run).
Literal-reading choices:
  * "8-K filings" = form type exactly "8-K" (amendments 8-K/A are not events).
  * CIK -> tickers from SEC's company_tickers.json (today's map, saved once by the pull); a CIK with several U-STK tickers
    (share classes) gives an event to each.
  * Daily indexes are read from 2015-12-31 (the after-hours window of the first 2016 session) to 2026-06-30; days inside
    L1/L2 are never requested, so DEV's first session (2024-08-01) only sees filings accepted on 08-01 itself.
  * Header fetches are limited to 8-Ks of CIKs mapped to U-STK tickers that pass the U-STK point-in-time filter on the
    filing date's session or the next session (the only days such a filing can be an event on).
G1 window: an 8-K accepted between 16:00 of the session before t and 09:15 on t (both inclusive) is an event for t:
  t = the first session with acceptance <= t 09:15, kept only when acceptance >= 16:00 of the session before t.
G2 timing (Item 2.02 = "Results of Operations and Financial Condition"): accepted before 09:30 -> day t is that day and the
  straddle exits at the close of t-1; otherwise it exits at the close of t. t-k counts NYSE sessions back from t (t itself
  when it is a session). If t is not a session (e.g. Good Friday) the exit is the last close before t (t-1) and the hold is
  2 sessions. Entry = the close of t-3. Literal note: a 2.02 accepted 09:30-16:00 is held to that day's close, i.e. past
  its acceptance; those events are counted and shown apart in the report (the amendment says "always out before the
  report", which holds only for filings outside market hours).
  LOOK-AHEAD CAVEAT (labeled everywhere G2 is reported): the 8-K date is the realized date; companies usually announce it
  weeks ahead, but not always.
"""
import html
import json
import re
import time
from datetime import date, datetime, timedelta

from . import periods

LOOKAHEAD = ("LOOK-AHEAD CAVEAT: the earnings date is the realized 8-K Item 2.02 acceptance date; companies usually "
             "announce it weeks ahead, but not always")
INDEX_FROM, INDEX_TO = date(2015, 12, 31), date(2026, 6, 30)
WIN_OPEN, WIN_CLOSE = (16, 0), (9, 15)
MIN_INTERVAL = 0.11
BACKOFF = (15, 30, 60, 120, 240)
ITEMS = {
    "1.01": "Entry into a Material Definitive Agreement", "1.02": "Termination of a Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership", "1.04": "Mine Safety", "1.05": "Material Cybersecurity Incidents",
    "2.01": "Completion of Acquisition or Disposition of Assets", "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation", "2.04": "Triggering Events That Accelerate or Increase",
    "2.05": "Costs Associated with Exit or Disposal Activities", "2.06": "Material Impairments",
    "3.01": "Notice of Delisting or Failure to Satisfy", "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders", "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements", "5.01": "Changes in Control of Registrant",
    "5.02": "Departure of Directors or Certain Officers", "5.03": "Amendments to Articles of Incorporation or Bylaws",
    "5.04": "Temporary Suspension of Trading Under Registrant's Employee Benefit Plans",
    "5.05": "Amendments to the Registrant's Code of Ethics", "5.06": "Change in Shell Company Status",
    "5.07": "Submission of Matters to a Vote of Security Holders", "5.08": "Shareholder Director Nominations",
    "6.01": "ABS Informational and Computational Material", "6.02": "Change of Servicer or Trustee",
    "6.03": "Change in Credit Enhancement or Other External Support", "6.04": "Failure to Make a Required Distribution",
    "6.05": "Securities Act Updating Disclosure", "7.01": "Regulation FD Disclosure", "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}
_NORM = re.compile(r"[^a-z0-9]+")


def _norm(s):
    return _NORM.sub(" ", str(s).lower().replace("’", "'")).strip()


_TITLES = sorted(((_norm(t), k) for k, t in ITEMS.items()), key=lambda x: -len(x[0]))


def item_number(title):
    """The 8-K item number for an "ITEM INFORMATION:" title (a prefix match on the normalized text), or None."""
    n = _norm(title)
    if not n:
        return None
    for t, k in _TITLES:
        if n.startswith(t) or t.startswith(n) and len(n) >= 12:
            return k
    for t, k in _TITLES:                                     # minor wording changes ("Amendment" vs "Amendments")
        if n[:24] and t[:24] == n[:24]:
            return k
    return None


# ---------------------------------------------------------------- URLs
def index_url(d):
    return f"https://www.sec.gov/Archives/edgar/daily-index/{d.year}/QTR{(d.month - 1) // 3 + 1}/form.{d:%Y%m%d}.idx"


def accession_of(file_name):
    m = re.search(r"(\d{10}-\d{2}-\d{6})", str(file_name))
    return m.group(1) if m else None


def header_url(cik, acc):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index-headers.html"


def tickers_url():
    return "https://www.sec.gov/files/company_tickers.json"


# ---------------------------------------------------------------- parsing
def parse_form_index(text, forms=("8-K",)):
    """Rows of a daily form index: [{"form", "company", "cik", "filed" (date), "file", "acc"}] for the given form types.
    Column positions come from the header line; CIK, date and file name are the last three fields of each row."""
    lines = text.splitlines()
    hdr, start = None, None
    for k, ln in enumerate(lines):
        if ln.startswith("Form Type") and "Company Name" in ln:
            hdr = ln
        elif hdr is not None and ln.startswith("---"):
            start = k + 1
            break
    if hdr is None or start is None:
        return []
    w_form = hdr.index("Company Name")
    want = set(forms) if forms else None
    out = []
    for ln in lines[start:]:
        if not ln.strip():
            continue
        parts = ln.rsplit(None, 3)
        if len(parts) < 4:
            continue
        left, cik, filed, fname = parts
        form = ln[:w_form].strip()
        if want is not None and form not in want:
            continue
        if not cik.isdigit() or not re.fullmatch(r"\d{8}", filed):
            continue
        out.append({"form": form, "company": left[w_form:].strip() if len(left) > w_form else "", "cik": int(cik),
                    "filed": date(int(filed[:4]), int(filed[4:6]), int(filed[6:])), "file": fname, "acc": accession_of(fname)})
    return out


def parse_header(text):
    """{"accepted": naive ET datetime or None, "form", "acc", "items": ["2.02", ...], "item_titles": [...]} from an
    -index-headers.html page (HTML-escaped) or the SGML header (<ITEMS> tags)."""
    t = html.unescape(str(text))
    out = {"accepted": None, "form": None, "acc": None, "items": [], "item_titles": []}
    m = re.search(r"<ACCEPTANCE-DATETIME>\s*(\d{14})", t)
    if m:
        s = m.group(1)
        out["accepted"] = datetime(int(s[:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), int(s[10:12]), int(s[12:14]))
    m = re.search(r"CONFORMED SUBMISSION TYPE:\s*(\S+)", t) or re.search(r"<TYPE>\s*(\S+)", t)
    if m:
        out["form"] = m.group(1)
    m = re.search(r"ACCESSION NUMBER:\s*(\d{10}-\d{2}-\d{6})", t) or re.search(r"<ACCESSION-NUMBER>\s*(\d{10}-\d{2}-\d{6})", t)
    if m:
        out["acc"] = m.group(1)
    items = []
    for ln in re.findall(r"ITEM INFORMATION:\s*([^\r\n<]+)", t):
        title = ln.strip()
        out["item_titles"].append(title)
        k = item_number(title)
        if k and k not in items:
            items.append(k)
    for k in re.findall(r"<ITEMS>\s*(\d+\.\d+)", t):
        if k not in items:
            items.append(k)
    out["items"] = items
    return out


def tickers_map(j):
    """{cik: [tickers]} from company_tickers.json's content (dict of {cik_str, ticker, title})."""
    out = {}
    rows = j.values() if isinstance(j, dict) else j
    for r in rows:
        try:
            c, tk = int(r["cik_str"]), str(r["ticker"]).upper().replace("-", ".")
        except (KeyError, TypeError, ValueError):
            continue
        out.setdefault(c, [])
        if tk not in out[c]:
            out[c].append(tk)
    return out


# ---------------------------------------------------------------- timing
class Calendar:
    """NYSE sessions (sprint/periods calendar, locked dates INCLUDED: they are days on the calendar even though nothing
    inside them is read) for counting t-k and finding the session before t."""

    def __init__(self, a=date(2015, 10, 1), b=date(2026, 8, 31)):
        hol = periods.holidays()
        self.days, d = [], a
        while d <= b:
            if d.weekday() < 5 and d.isoformat() not in hol:
                self.days.append(d)
            d += timedelta(days=1)
        self.pos = {d: k for k, d in enumerate(self.days)}

    def is_session(self, d):
        return d in self.pos

    def first_on_or_after(self, d):
        import bisect
        k = bisect.bisect_left(self.days, d)
        return self.days[k] if k < len(self.days) else None

    def back(self, t, k):
        """t-k in sessions: k = 0 -> t if a session; k >= 1 -> the k-th session before t (t itself not counted)."""
        import bisect
        if k == 0:
            return t if t in self.pos else None
        j = bisect.bisect_left(self.days, t) - k
        return self.days[j] if j >= 0 else None

    def fwd(self, d, k):
        j = self.pos.get(d)
        if j is None or j + k >= len(self.days):
            return None
        return self.days[j + k]


def g1_day(accepted, cal):
    """The session t for which an 8-K accepted at `accepted` (naive ET) is a G1 event, or None."""
    if accepted is None:
        return None
    t = cal.first_on_or_after(accepted.date())
    while t is not None and accepted > datetime(t.year, t.month, t.day, *WIN_CLOSE):
        t = cal.fwd(t, 1)
    if t is None:
        return None
    p = cal.back(t, 1)
    if p is None or accepted < datetime(p.year, p.month, p.day, *WIN_OPEN):
        return None
    return t


def g2_timing(accepted, cal):
    """{"t", "entry", "exit", "hold", "intraday"} for an Item 2.02 8-K, or None. See the module docstring."""
    if accepted is None:
        return None
    t = accepted.date()
    before_open = (accepted.hour, accepted.minute) < (9, 30)
    if before_open or not cal.is_session(t):
        ex = cal.back(t, 1)
        hold = 2
    else:
        ex = t
        hold = 3
    entry = cal.back(t, 3) if cal.is_session(t) else cal.back(t, 3)
    if ex is None or entry is None:
        return None
    intraday = cal.is_session(t) and (9, 30) <= (accepted.hour, accepted.minute) < (16, 0)
    return {"t": t, "entry": entry, "exit": ex, "hold": hold, "intraday": bool(intraday), "before_open": bool(before_open)}


# ---------------------------------------------------------------- the rate limiter and the fetcher
class Throttle:
    """At most one request every `min_interval` seconds (0.11 s -> at most ~9 a second, under SEC's 10)."""

    def __init__(self, min_interval=MIN_INTERVAL, clock=time.monotonic, sleep=time.sleep):
        self.min_interval, self.clock, self.sleep = float(min_interval), clock, sleep
        self.last = None
        self.calls = 0

    def wait(self):
        now = self.clock()
        if self.last is not None:
            gap = now - self.last
            if gap < self.min_interval:
                self.sleep(self.min_interval - gap)
                now = self.clock()
        self.last = now
        self.calls += 1


class RateLimited(RuntimeError):
    pass


def fetch(url, http, throttle, sleep=time.sleep, backoff=BACKOFF):
    """GET via http(url) -> (status, text). Returns the text, or None on 404. Retries 403/429/5xx with backoff; raises
    RateLimited after the last wait. Only https://www.sec.gov/ is ever requested."""
    if not url.startswith("https://www.sec.gov/"):
        raise RuntimeError(f"REFUSED: sprint/edgar only reads https://www.sec.gov/, never {url.split('?')[0]}")
    for k in range(len(backoff) + 1):
        throttle.wait()
        status, text = http(url)
        if status == 200:
            return text
        if status == 404:
            return None
        if status in (403, 429, 500, 502, 503, 504) and k < len(backoff):
            sleep(backoff[k])
            continue
        raise RateLimited(f"SEC answered {status} for {url} after {k} retries")
    return None


def header_record(cik, row, parsed, error=None):
    a = parsed.get("accepted") if parsed else None
    return {"acc": row["acc"], "cik": int(cik), "form": row["form"], "filed": row["filed"].isoformat(),
            "accepted": a.isoformat(sep=" ") if a else None, "items": parsed.get("items") if parsed else [],
            "error": error}


def read_jsonl(path):
    """Records of a JSON-lines file; a torn last line (an interrupted write) is skipped."""
    out = []
    try:
        with open(path) as f:
            for ln in f:
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    continue
    except OSError:
        pass
    return out
