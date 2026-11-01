"""Round 9 Part G (SPRINT_PLAN Amendment 12): EDGAR index and header parsing on fixtures, the 8-K item numbers, the G1 event
window, G2's timing (the straddle is out before the report), the SEC rate limiter and back-off with a fake clock and fake
HTTP, the user agent read without printing it, G1's signal / stop / out bar / long-only, the random benchmarks'
determinism, and G2's expiries, strikes, choice, P/L, benchmark and pass bar. Synthetic data only."""
import math
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

import sprint_synth  # noqa: F401
from sprint import catalyst as C, edgar as E, periods

INDEX = """Description:           Daily Index of EDGAR Dissemination Feed by Form Type
Last Data Received:    March 4, 2025
Comments:              webmaster@sec.gov
Anonymous FTP:         ftp://ftp.sec.gov/edgar/




Form Type   Company Name                                                  CIK         Date Filed  File Name
---------------------------------------------------------------------------------------------------------------------------------------------
10-Q        SOME CORP                                                     12345       20250304    edgar/data/12345/0000012345-25-000010.txt
8-K         APPLE INC                                                     320193      20250304    edgar/data/320193/0000320193-25-000021.txt
8-K/A       OTHER INC                                                     55555       20250304    edgar/data/55555/0000055555-25-000002.txt
8-K         BIG BANK CORP /NY/                                            70858       2025-03-04  edgar/data/70858/0000070858-25-000101.txt
"""

HEADER_HTML = """<html><head><title>0000320193-25-000021.hdr.sgml</title></head><body><pre>
&lt;ACCEPTANCE-DATETIME&gt;20250304163012
ACCESSION NUMBER:		0000320193-25-000021
CONFORMED SUBMISSION TYPE:	8-K
PUBLIC DOCUMENT COUNT:		12
CONFORMED PERIOD OF REPORT:	20250304
ITEM INFORMATION:		Results of Operations and Financial Condition
ITEM INFORMATION:		Financial Statements and Exhibits
FILED AS OF DATE:		20250304
</pre></body></html>"""

HEADER_SGML = """<SEC-HEADER>
<ACCEPTANCE-DATETIME>20240105071500
<ACCESSION-NUMBER>0000070858-24-000001
<TYPE>8-K
<ITEMS>5.02
<ITEMS>9.01
</SEC-HEADER>"""


# ---------------------------------------------------------------- EDGAR parsing
def test_parse_form_index_keeps_8k_only_and_both_date_formats():
    rows = E.parse_form_index(INDEX)
    assert [r["cik"] for r in rows] == [320193, 70858]
    assert rows[0]["company"] == "APPLE INC" and rows[0]["filed"] == date(2025, 3, 4) and rows[0]["acc"] == "0000320193-25-000021"
    assert rows[1]["filed"] == date(2025, 3, 4) and rows[1]["company"] == "BIG BANK CORP /NY/"
    assert E.parse_form_index("no header here") == []


def test_parse_header_html_and_sgml():
    h = E.parse_header(HEADER_HTML)
    assert h["accepted"] == datetime(2025, 3, 4, 16, 30, 12) and h["form"] == "8-K" and h["acc"] == "0000320193-25-000021"
    assert h["items"] == ["2.02", "9.01"]
    s = E.parse_header(HEADER_SGML)
    assert s["accepted"] == datetime(2024, 1, 5, 7, 15) and s["items"] == ["5.02", "9.01"] and s["form"] == "8-K"


@pytest.mark.parametrize("title,item", [
    ("Results of Operations and Financial Condition", "2.02"), ("Regulation FD Disclosure", "7.01"), ("Other Events", "8.01"),
    ("Departure of Directors or Certain Officers; Election of Directors; Appointment of Certain Officers: Compensatory Arrangements", "5.02"),
    ("Entry into a Material Definitive Agreement", "1.01"), ("Submission of Matters to a Vote of Security Holders", "5.07"),
    ("Amendments to Articles of Incorporation or Bylaws; Change in Fiscal Year", "5.03"), ("Something new", None)])
def test_item_numbers(title, item):
    assert E.item_number(title) == item


def test_urls_and_tickers_map():
    assert E.index_url(date(2025, 3, 4)) == "https://www.sec.gov/Archives/edgar/daily-index/2025/QTR1/form.20250304.idx"
    assert E.header_url(320193, "0000320193-25-000021").endswith("/320193/000032019325000021/0000320193-25-000021-index-headers.html")
    m = E.tickers_map({"0": {"cik_str": 1067983, "ticker": "BRK-B", "title": "x"}, "1": {"cik_str": 1067983, "ticker": "BRK-A", "title": "x"}})
    assert m == {1067983: ["BRK.B", "BRK.A"]}


# ---------------------------------------------------------------- timing
CAL = E.Calendar()


@pytest.mark.parametrize("acc,t", [
    (datetime(2025, 3, 4, 7, 0), date(2025, 3, 4)),          # premarket -> that day
    (datetime(2025, 3, 4, 9, 15), date(2025, 3, 4)),         # 09:15 is inside the window
    (datetime(2025, 3, 4, 9, 16), None),                     # 09:16-16:00: never an event
    (datetime(2025, 3, 4, 12, 0), None),
    (datetime(2025, 3, 4, 16, 0), date(2025, 3, 5)),         # 16:00 of the prior session
    (datetime(2025, 3, 7, 18, 0), date(2025, 3, 10)),        # Friday evening -> Monday
    (datetime(2025, 3, 8, 11, 0), date(2025, 3, 10)),        # Saturday -> Monday
    (datetime(2025, 4, 18, 10, 0), date(2025, 4, 21))])      # Good Friday (NYSE closed) -> Monday
def test_g1_window(acc, t):
    assert E.g1_day(acc, CAL) == t


def test_g2_timing_is_always_out_before_the_report():
    pre = E.g2_timing(datetime(2025, 3, 5, 7, 0), CAL)        # report before Wednesday's open
    assert (pre["t"], pre["exit"], pre["entry"], pre["hold"]) == (date(2025, 3, 5), date(2025, 3, 4), date(2025, 2, 28), 2)
    post = E.g2_timing(datetime(2025, 3, 5, 16, 5), CAL)      # after Wednesday's close
    assert (post["exit"], post["entry"], post["hold"], post["intraday"]) == (date(2025, 3, 5), date(2025, 2, 28), 3, False)
    for acc, tm in ((datetime(2025, 3, 5, 7, 0), pre), (datetime(2025, 3, 5, 16, 5), post)):
        close_of_exit = datetime(tm["exit"].year, tm["exit"].month, tm["exit"].day, 16, 0)
        assert close_of_exit <= acc                           # the exit is the close at or before the report
    intra = E.g2_timing(datetime(2025, 3, 5, 11, 0), CAL)     # the literal rule holds it to t's close (labeled)
    assert intra["intraday"] and intra["exit"] == date(2025, 3, 5)
    sat = E.g2_timing(datetime(2025, 3, 8, 10, 0), CAL)
    assert (sat["exit"], sat["entry"]) == (date(2025, 3, 7), date(2025, 3, 5))


# ---------------------------------------------------------------- the rate limiter, back-off and the user agent
class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def test_throttle_keeps_sec_under_ten_requests_a_second():
    ck = Clock()
    th = E.Throttle(clock=ck.now, sleep=ck.sleep)
    stamps = []
    for _ in range(50):
        th.wait()
        stamps.append(ck.t)
        ck.t += 0.01                                          # the request itself takes 10 ms
    gaps = np.diff(stamps)
    assert (gaps >= E.MIN_INTERVAL - 1e-9).all() and E.MIN_INTERVAL >= 0.1
    assert max(sum(1 for s in stamps if a <= s < a + 1.0) for a in stamps) <= 10


def test_fetch_backoff_404_and_host_guard():
    ck = Clock()
    seq = [(429, ""), (503, ""), (599, ""), (200, "ok")]
    http = lambda url: seq.pop(0)
    th = E.Throttle(clock=ck.now, sleep=ck.sleep)
    assert E.fetch("https://www.sec.gov/x", http, th, sleep=ck.sleep) == "ok"
    assert ck.sleeps[-3:] == [15, 30, 60] or ck.sleeps.count(15) == 1
    assert E.fetch("https://www.sec.gov/x", lambda u: (404, ""), th, sleep=ck.sleep) is None
    with pytest.raises(E.RateLimited):
        E.fetch("https://www.sec.gov/x", lambda u: (403, ""), th, sleep=lambda s: None)
    with pytest.raises(RuntimeError):
        E.fetch("https://example.com/x", http, th)


def test_user_agent_from_the_desk_env_file_is_never_printed(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    f = tmp_path / "deltadesk.env"
    f.write_text("PORT=8765\nDESK_TOKEN=secret-token\nSEC_USER_AGENT=\"Research Bot contact-at-example\"\n")
    assert E.load_user_agent(str(f)) == "file"
    import os
    assert os.environ["SEC_USER_AGENT"] == "Research Bot contact-at-example" and "DESK_TOKEN" not in os.environ
    out = capsys.readouterr()
    assert "Research Bot" not in out.out + out.err
    assert E.load_user_agent(str(f)) == "env"
    monkeypatch.delenv("SEC_USER_AGENT")
    assert E.load_user_agent(str(tmp_path / "missing.env")) is None


# ---------------------------------------------------------------- G1
def _grid(o0=105.0, move=0.5, vol0=300_000.0, volr=20_000.0, path=None):
    g = np.full((5, 390), np.nan)
    c = np.full(390, o0 + move) if path is None else np.asarray(path, float)
    c[:15] = np.linspace(o0 + move / 15, o0 + move, 15) if path is None else c[:15]
    o = np.concatenate([[o0], c[:-1]])
    g[0], g[3] = o, c
    g[1], g[2] = np.maximum(o, c) + 0.02, np.minimum(o, c) - 0.02
    g[4] = volr
    g[4, :15] = vol0 / 15
    return g


EV = {"symbol": "AAA", "t": date(2025, 3, 5), "acc": "x", "accepted": datetime(2025, 3, 5, 7, 0)}


def test_g1_signal_conditions():
    g = _grid()
    side, info = C.g1_signal(g, 100.0, 1_000_000.0)          # gap +5%, move up, RV15 = 300k / 100k = 3.0
    assert side == 1 and info["rv15"] == pytest.approx(3.0) and info["gap"] == pytest.approx(0.05)
    assert C.g1_signal(g, 104.0, 1_000_000.0)[0] is None     # |gap| < 2%
    assert C.g1_signal(g, 100.0, 1_100_000.0)[0] is None     # RV15 < 3
    assert C.g1_signal(_grid(move=-0.5), 100.0, 1_000_000.0)[0] is None   # moved against the gap
    s, _ = C.g1_signal(_grid(o0=95.0, move=-0.5), 100.0, 1_000_000.0)
    assert s == -1


def test_g1_trade_out_at_1555_and_costs():
    g = _grid()
    t, why = C.g1_trade(EV, g, 100.0, 1_000_000.0)
    assert why is None and t["entry_idx"] == 15 and t["exit_idx"] == 384 and t["exit_time"] == "15:54"
    sh = math.floor(10_000 / g[3, 14])
    assert t["shares"] == sh and t["exit_reason"].startswith("OUT at the 15:55")
    mv = g[3, 384] - g[0, 15]
    assert t["pnl"] == pytest.approx(sh * mv - 0.0005 * sh * (g[0, 15] + g[3, 384]), abs=1e-3)
    assert t["pnl_2x"] == pytest.approx(sh * mv - 0.001 * sh * (g[0, 15] + g[3, 384]), abs=1e-3)
    te, _ = C.g1_trade(EV, g, 100.0, 1_000_000.0, early=True)
    assert te["exit_idx"] == 204


def test_g1_signal_has_no_look_ahead():
    g = _grid()
    a = C.g1_signal(g, 100.0, 1_000_000.0)
    g2 = g.copy()
    g2[:, 15:] = g2[:, 15:] * 0.5                          # every bar after the decision bar changes
    assert C.g1_signal(g2, 100.0, 1_000_000.0) == a
    t1, _ = C.g1_trade(EV, g, 100.0, 1_000_000.0)
    g3 = g.copy()
    g3[:, 200:] = g3[:, 200:] + 1.0                         # later bars move the exit, never the entry or the stop
    t3, _ = C.g1_trade(EV, g3, 100.0, 1_000_000.0)
    assert (t1["entry_idx"], t1["entry_ref"], t1["stop"], t1["shares"]) == (t3["entry_idx"], t3["entry_ref"], t3["stop"], t3["shares"])


def test_g1_stop_on_closes_and_entry_window():
    path = np.full(390, 105.5)
    path[:15] = np.linspace(105.05, 105.5, 15)
    path[100] = 104.0                                        # a close below the 09:30-09:45 low -> out at bar 101's open
    g = _grid(path=path)
    t, _ = C.g1_trade(EV, g, 100.0, 1_000_000.0)
    assert t["exit_idx"] == 101 and t["exit_reason"].startswith("STOP") and t["stop"] == pytest.approx(float(np.nanmin(g[2, :15])))
    g2 = _grid()
    g2[0, 15] = g2[0, 16] = np.nan
    assert C.g1_trade(EV, g2, 100.0, 1_000_000.0)[0]["entry_idx"] == 17
    g2[0, 17] = np.nan
    assert C.g1_trade(EV, g2, 100.0, 1_000_000.0)[0] is None   # no open in 15-17
    lo, why = C.g1_trade(EV, _grid(o0=95.0, move=-0.5), 100.0, 1_000_000.0, long_only=True)
    assert lo is None and "long-only" in why


def test_g1_random_benchmarks_are_deterministic():
    rng = np.random.default_rng(5)
    trades, pools = [], {}
    for k in range(40):
        g = _grid(o0=105 + rng.normal(0, 1), move=0.5)
        g[3, 15:] = g[3, 14] + np.cumsum(rng.normal(0, 0.05, 375))
        g[0, 15:] = np.concatenate([[g[3, 14]], g[3, 15:-1]])
        t, _ = C.g1_trade(dict(EV, symbol=f"S{k % 4}"), g, 100.0, 1_000_000.0)
        trades.append(t)
        pools.setdefault(t["symbol"], []).append(C.pool_entry(g, False))
    a, b = C.random_direction(trades), C.random_direction(trades)
    assert a[0] == b[0] and np.array_equal(a[1], b[1]) and len(a[1]) == 200
    x, y = C.random_entry_g1(trades, pools), C.random_entry_g1(trades, pools)
    assert x[0] == y[0] and np.array_equal(x[1], y[1])
    assert 0.0 <= x[0] <= 1.0


# ---------------------------------------------------------------- G2
def test_g2_expiries_and_strikes():
    assert C.g2_expiries(date(2025, 3, 3)) == [date(2025, 3, 14), date(2025, 3, 21)]
    assert C.g2_expiries(date(2025, 4, 4)) == [date(2025, 4, 17)]       # Good Friday -> Thursday, also the monthly
    ks = C.g2_strikes(101.3)
    assert {101.0, 102.0, 100.0, 102.5, 100.5, 101.5, 105.0} <= set(ks)
    assert {600.0, 625.0} <= set(C.g2_strikes(612.4))
    first = C.straddle_candidates("BRK.B", date(2025, 3, 3), 480.0, "first")
    assert all(s.startswith("BRKB250314") for s in first) and len(first) == 2 * len(C.g2_strikes(480.0))
    assert all(s.startswith("BRKB250321") for s in C.straddle_candidates("BRK.B", date(2025, 3, 3), 480.0, "next"))


def _legs(day, legs):
    rows = []
    for sym, px, minute in legs:
        hh, mm = divmod(570 + minute, 60)
        rows.append({"ts": f"{day}T{hh:02d}:{mm:02d}:00-05:00", "o": px, "h": px, "l": px, "c": px, "v": 3.0, "symbol": sym})
    return pd.DataFrame(rows)


def test_g2_choice_pnl_and_return():
    ent = _legs("2025-03-03", [("AAA250314C00100000", 3.0, 385), ("AAA250314P00100000", 2.0, 389), ("AAA250314C00102500", 2.0, 380),
                               ("AAA250314C00101000", 2.4, 380), ("AAA250321C00101000", 4.0, 380), ("AAA250321P00101000", 4.0, 380),
                               ("AAA250314P00101000", 2.9, 300)])          # 101 put printed only before 15:30
    ch, why = C.choose_straddle(ent, "AAA", date(2025, 3, 3), 101.2)
    assert why is None and ch["strike"] == 100.0 and ch["expiry"] == "2025-03-14" and (ch["call_px"], ch["put_px"]) == (3.0, 2.0)
    exi = _legs("2025-03-05", [("AAA250314C00100000", 4.5, 389), ("AAA250314P00100000", 1.0, 370)])
    ev = {"symbol": "AAA", "entry": date(2025, 3, 3), "exit": date(2025, 3, 5), "hold": 2, "t": date(2025, 3, 6), "intraday": False}
    t, why = C.straddle_trade(ev, ch, exi)
    hs = lambda p: max(0.05 * p, 0.01)
    buy = 3.0 + hs(3.0) + 2.0 + hs(2.0)
    sell = 4.5 - hs(4.5) + 1.0 - hs(1.0)
    assert t["pnl"] == pytest.approx(100 * (sell - buy) - 4 * 0.65, abs=0.01)
    assert t["debit"] == pytest.approx(100 * buy + 2 * 0.65, abs=0.01) and t["ret"] == pytest.approx(t["pnl"] / t["debit"], abs=1e-5)
    assert C.straddle_trade(ev, ch, exi.iloc[:1])[0] is None


def test_g2_benchmark_and_pass_bar():
    rows = []
    days = pd.bdate_range("2024-08-05", "2026-06-25")
    for k in range(120):
        d = days[k * 3].date().isoformat()
        r = 0.08 if k % 3 else -0.05
        rows.append({"day": d, "ret": r, "ret_2x": r - 0.02, "pnl": 100 * r, "debit": 100.0, "intraday": k == 0})
    pool = {k: [0.0, -0.01, 0.01] for k in range(120)}
    p95, means, n = C.g2_benchmark(rows, pool)
    p95b, meansb, _ = C.g2_benchmark(rows, pool)
    assert p95 == p95b and np.array_equal(means, meansb) and n == 120 and len(means) == 200
    res = C.g2_pass(rows, p95)
    assert res["pass"] and res["events"] == 120 and res["intraday_events"] == 1 and res["without_intraday"]["events"] == 119
    assert not C.g2_pass(rows[:99], p95)["pass"]
    assert not C.g2_pass(rows, 0.5)["pass"]


def test_random_pool_avoids_earnings_windows_and_is_deterministic():
    from sprint import universe as U
    days = U.sessions(date(2024, 8, 1), date(2025, 6, 30))
    p = U.Panel(["AAA"], {"AAA": pd.DataFrame({"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0}, index=days)}, None, days)
    ev = [{"symbol": "AAA", "entry": days[100], "exit": days[103], "hold": 3}]
    earn = {"AAA": {days[k] for k in range(0, len(days), 10)}}
    a, b = C.random_pool(ev, p, earn), C.random_pool(ev, p, earn)
    assert a == b and len(a) == C.POOL_PER_EVENT
    for q in a:
        k = days.index(q["entry"])
        assert not any(days[k + i] in earn["AAA"] for i in range(0, 5)) and q["exit"] == days[k + 3]
