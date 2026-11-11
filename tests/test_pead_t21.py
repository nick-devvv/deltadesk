"""pead_t21: the post-earnings drift ledger (paper, multi-day, isolated "pead" risk book). Frozen T21 rules (8-K Item
2.02 events, the I/B/E/S-style reaction day, the 3-day EAR minus SPY, the trailing 365-day 90th percentile cutoff), fills
at the open, the 20-session exit at the close, the risk-framework size cap, no look-ahead, restart safety, risk
isolation and the switch. Fake Schwab and SEC data only, no network."""
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import core  # noqa: E402
import fakes  # noqa: E402
import marketdata  # noqa: E402
import pead_t21 as P  # noqa: E402
import scanner  # noqa: E402
import store  # noqa: E402
import v4risk  # noqa: E402
import v4store as S  # noqa: E402

ET = core.ET
FILED, REACT, SIG, ENTRY = date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4), date(2026, 11, 5)   # Mon..Thu
EXIT = date(2026, 12, 4)                       # the 20th session after Nov 5 (Thanksgiving Nov 26 skipped)


# ================================================================ fake data
def frame(closes, end):
    idx = pd.bdate_range(end=pd.Timestamp(end), periods=len(closes))
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"Open": c, "High": c + 0.5, "Low": c - 0.5, "Close": c, "Volume": 1e7}, index=idx)


def wiggle(n, base=100.0, amp=0.01, seed=1):
    """A random walk with small daily moves (sigma about amp)."""
    r = np.random.default_rng(seed).normal(0, amp, n)
    return list(base * np.cumprod(1 + r))


def with_jump(closes, idx, day, jump):
    """Multiply every close from `day` on by (1 + jump)."""
    c = np.array(closes, dtype=float)
    k = list(idx).index(pd.Timestamp(day))
    c[k:] *= 1 + jump
    return list(c)


def subs(rows):
    """EDGAR submissions JSON from [(form, acceptance, items)]."""
    return json.dumps({"filings": {"recent": {
        "form": [r[0] for r in rows], "filingDate": [r[1][:10] for r in rows], "acceptanceDateTime": [r[1] for r in rows],
        "items": [r[2] for r in rows], "accessionNumber": [f"0000-{i}" for i, _ in enumerate(rows)]}}})


class Prov(marketdata.Provider):
    name = "Schwab (fake for tests)"
    executable = True

    def __init__(self):
        self.world = None

    def quote(self, t):
        if self.world is None:
            return None
        q = self.world.quotes([t])[0].get(t)
        if not q:
            return None
        qt = pd.Timestamp(q["quote_ms"], unit="ms", tz="UTC").tz_convert(ET)
        return {"bid": q["bid"], "ask": q["ask"], "last": q["last"], "quote_time": qt, "src": self.name}


class Fake:
    def __init__(self, clock, daily):
        self.clock, self.d, self.px, self.dead, self.ready_ = clock, daily, {}, set(), True

    def ready(self):
        return self.ready_

    def daily(self, t):
        return self.d.get(t)

    def quotes(self, ts):
        now = pd.Timestamp(self.clock())
        out = {}
        for t in ts:
            if t in self.dead or t not in self.d:
                continue
            last = self.px.get(t, float(self.d[t]["Close"].iloc[-1]))
            out[t] = {"last": last, "bid": round(last - 0.01, 2), "ask": round(last + 0.01, 2),
                      "quote_ms": (now - pd.Timedelta(seconds=0.5)).value // 10 ** 6}
        return out, None


UNI = [("AAA", 1), ("BBB", 2), ("CCC", 3)]
EDGAR = {1: [("8-K", "2026-11-02T16:10:05.000Z", "2.02,9.01"), ("8-K/A", "2026-11-03T08:00:00.000Z", "2.02")],
         2: [("8-K", "2026-11-03T07:30:00.000Z", "2.02,9.01"), ("8-K", "2026-10-01T12:00:00.000Z", "5.02")],
         3: [("8-K", "2026-08-05T07:00:00.000Z", "2.02")]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    import health
    monkeypatch.setitem(health._feed, "ok", None)
    P._state.update(status="idle", last_error=None, mark_t=None, plan_try=None, tz_mode=None)
    monkeypatch.setattr(P, "universe", lambda: list(UNI))
    monkeypatch.setattr(P, "EDGAR_PAUSE_S", 0)
    calls = []

    def sec(url):
        cik = int(url.split("CIK")[1][:10])
        calls.append(cik)
        return subs(EDGAR.get(cik, []))
    monkeypatch.setattr(P, "sec_get", sec)
    clock = fakes.Clock(datetime(2026, 11, 5, 5, 0, tzinfo=ET))
    monkeypatch.setattr(core, "now_et", clock)
    prov = Prov()
    marketdata.use(prov)
    yield monkeypatch, clock, prov, calls
    scanner.use(None)
    marketdata.use(None)


def history_ears(s_last=SIG, n=250, lo=-0.10, hi=0.10):
    """n stored EARs with signal days spread over the 300 days before s_last (all inside the 365-day window)."""
    vals = np.linspace(lo, hi, n)
    out = {}
    for i, v in enumerate(vals):
        s = s_last - timedelta(days=1 + (i % 300))
        out[f"H{i}|{s}"] = {"ticker": f"H{i}", "react": str(s), "s": str(s), "ear": float(v), "why": None}
    return out


def world(env, end=SIG, aaa_jump=0.12, bbb_jump=0.01):
    mp, clock, prov, calls = env
    n = 300
    idx = pd.bdate_range(end=pd.Timestamp(end), periods=n)
    spy = wiggle(n, 600, 0.004, seed=7)
    d = {"SPY": frame(spy, end),
         "AAA": frame(with_jump(wiggle(n, 50, 0.01, seed=2), idx, REACT, aaa_jump), end),
         "BBB": frame(with_jump(wiggle(n, 80, 0.01, seed=3), idx, REACT, bbb_jump), end),
         "CCC": frame(wiggle(n, 30, 0.01, seed=4), end)}
    f = Fake(clock, d)
    scanner.use(f)
    prov.world = f
    store.kv_set("pead:ears", history_ears())
    return f, clock


def run(clock, day, a, b, step_s=5):
    def at(s):
        hh, mm = int(s[:2]), int(s[3:5])
        ss = int(s[6:]) if len(s) > 5 else 0
        return datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=ET)
    t, end = at(a), at(b)
    while t <= end:
        clock.t = t
        P.step(t)
        t += timedelta(seconds=step_s)


def entry(day, t):
    r = [d for d in S.decisions(ledger=P.LEDGER, kind="entry") if d["id"] == f"{P.LEDGER}:{day}-{t}"]
    return r[0]["decision"] if r else None


# ================================================================ pure rules
def test_sessions_skip_weekends_and_holidays_and_the_exit_is_20_sessions_on():
    assert P.next_session(date(2026, 11, 6)) == date(2026, 11, 9)
    assert P.prev_session(date(2026, 11, 27)) == date(2026, 11, 25)          # Thanksgiving
    assert P.add_sessions(ENTRY, 20) == EXIT
    assert P.add_sessions(date(2026, 11, 2), 0) == date(2026, 11, 2)


def test_only_8k_item_202_filings_count_and_amendments_dont():
    raw = json.loads(subs([("8-K", "2026-11-02T16:10:05.000Z", "2.02,9.01"), ("8-K/A", "2026-11-03T08:00:00.000Z", "2.02"),
                           ("8-K", "2026-10-01T12:00:00.000Z", "5.02,9.01"), ("10-Q", "2026-11-02T16:30:00.000Z", ""),
                           ("8-K", "2025-01-02T07:00:00.000Z", "2.02")]))
    got = P.parse_filings(raw, date(2025, 8, 1))
    assert [g[0] for g in got] == ["2026-11-02T16:10:05.000Z"]
    assert P.parse_filings({}, date(2025, 1, 1)) == []
    assert P.parse_filings(json.loads(subs([("8-K", "2026-11-02T07:00:00.000Z", "12.02")])), date(2025, 1, 1)) == []   # not 2.02


def test_edgar_time_zone_is_detected_from_the_hours_and_the_reaction_day_follows_ibes():
    et_like = ["2026-11-02T07:01:00.000Z", "2026-11-02T08:30:00.000Z", "2026-11-02T16:05:00.000Z"]
    utc_like = ["2026-11-02T11:01:00.000Z", "2026-11-02T21:05:00.000Z", "2026-11-02T20:31:00.000Z"]
    assert P.tz_mode(et_like) == "ET" and P.tz_mode(utc_like) == "UTC" and P.tz_mode([]) == "ET"
    t = P.accept_et("2026-11-02T16:10:05.000Z", "ET")
    assert t.strftime("%Y-%m-%d %H:%M") == "2026-11-02 16:10" and P.react_day(t) == REACT       # after 16:00 -> next session
    assert P.react_day(P.accept_et("2026-11-02T15:59:00.000Z", "ET")) == date(2026, 11, 2)     # before 16:00 -> same day
    u = P.accept_et("2026-11-02T21:10:05.000Z", "UTC")                                          # 16:10 ET in true UTC
    assert u.strftime("%H:%M") == "16:10" and P.react_day(u) == REACT
    assert P.react_day(P.accept_et("2026-11-07T10:00:00.000Z", "ET")) == date(2026, 11, 9)     # Saturday -> Monday
    assert P.react_day(P.accept_et("2026-11-25T17:00:00.000Z", "ET")) == date(2026, 11, 27)    # skips Thanksgiving


def test_ear_is_the_3_day_return_minus_spy_known_at_the_signal_day():
    idx = pd.bdate_range("2026-10-26", "2026-11-06")
    stock = pd.DataFrame({"Close": np.linspace(100, 111, len(idx))}, index=idx)
    spy = pd.DataFrame({"Close": np.linspace(500, 511, len(idx))}, index=idx)
    x, s = P.ear(stock, spy, REACT)
    r2 = P.prev_session(P.prev_session(REACT))                                    # Oct 30
    exp = stock["Close"][pd.Timestamp(SIG)] / stock["Close"][pd.Timestamp(r2)] - spy["Close"][pd.Timestamp(SIG)] / spy["Close"][pd.Timestamp(r2)]
    assert s == SIG and r2 == date(2026, 10, 30) and x == pytest.approx(exp)
    assert P.ear(stock.drop(pd.Timestamp(r2)), spy, REACT)[0] is None             # a missing close: no EAR


def test_cutoff_is_the_90th_percentile_of_the_prior_365_days_strictly_before():
    ears = list(history_ears(SIG, n=250).values())
    cut, n = P.cutoff(ears, SIG)
    assert n == 250 and cut == pytest.approx(np.percentile(np.linspace(-0.1, 0.1, 250), 90))
    same_day = ears + [{"ear": 9.9, "s": str(SIG)}]                                 # same signal day: excluded
    old = ears + [{"ear": 9.9, "s": str(SIG - timedelta(days=366))}]               # older than 365 days: excluded
    assert P.cutoff(same_day, SIG)[0] == cut and P.cutoff(old, SIG)[0] == cut
    assert P.cutoff(ears[:199], SIG) == (None, 199)                                # fewer than 200: no cutoff


def test_size_caps_a_3_sigma_day_at_45_dollars():
    q, n = P.size(50.0, 0.01)                                     # 3 x 1% x $600 = $18: the $600 slot binds
    assert q == math.floor(600 / 50 * 1e4) / 1e4 and n <= 600
    q, n = P.size(50.0, 0.05)                                     # 3 x 5% x $600 = $90 > $45: cut to $300
    assert n == pytest.approx(300.0, abs=0.01) and 3 * 0.05 * n <= 45.0 + 1e-6
    assert P.size(50.0, None) == (0.0, 0.0) and P.size(0, 0.01) == (0.0, 0.0)


# ================================================================ live ledger
def test_full_cycle_signal_entry_at_the_open_and_exit_at_the_close_20_sessions_later(env):
    f, clock = world(env)
    run(clock, ENTRY, "05:00", "08:01", step_s=30)
    plan = store.kv_get(P._pkey(ENTRY))
    assert plan and plan["asof"] == str(SIG) and plan["tz_mode"] == "ET"
    assert plan["entries"] == ["AAA"]                                           # BBB's small reaction is below the cutoff
    rows = plan["rows"]
    assert rows["AAA"]["state"] == "SIGNAL" and rows["BBB"]["state"] == "NO SIGNAL" and "CCC" not in rows
    assert rows["AAA"]["react"] == str(REACT) and rows["BBB"]["react"] == str(REACT)
    assert plan["n_window"] >= 250 and plan["cutoff"] == pytest.approx(np.percentile(np.linspace(-0.1, 0.1, 250), 90), abs=0.02)
    run(clock, ENTRY, "09:30", "09:30:10")
    assert entry(ENTRY, "AAA") == "ORDER"
    p = S.positions(ledger=P.LEDGER, status="OPEN")[0]
    assert p["book"] == "pead" and p["plan"]["exit_day"] == str(EXIT) and p["entry_px"] == pytest.approx(
        round(round(float(f.d["AAA"]["Close"].iloc[-1]) + 0.01, 2) + 0.01, 4))
    assert p["plan"]["notional"] <= 600 and p["risk_usd"] <= 45.0 + 0.01
    # marks over the holding period, no exit before the 20th session
    run(clock, date(2026, 11, 12), "10:00", "15:59:55", step_s=600)
    assert S.get(p["id"])["status"] == "OPEN"
    # the exit day: the 15:55 window, sold at bid - 0.01
    f.px["AAA"] = 60.0
    assert P.due_exits(EXIT) == ([p["id"]], []) and P.due_exits(P.prev_session(EXIT)) == ([], [])
    run(clock, EXIT, "15:54:50", "15:55:10")                                    # no morning plan needed for an exit
    c = S.get(p["id"])
    assert c["status"] == "CLOSED" and c["exit_px"] == pytest.approx(59.98) and "20th session" in c["exit_reason"]


def test_no_lookahead_future_bars_and_todays_forming_bar_never_change_the_plan(env):
    f, clock = world(env)
    a = {k: v for k, v in f.d.items()}
    run(clock, ENTRY, "05:00", "08:01", step_s=30)
    plan1 = store.kv_get(P._pkey(ENTRY))
    # same world plus a forming bar for today and absurd future bars
    store.kv_set(P._pkey(ENTRY), None)
    store.kv_set("pead:ears", history_ears())
    for t, df in a.items():
        extra = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": [1.0, 999.0], "Volume": 1.0},
                             index=pd.DatetimeIndex([pd.Timestamp(ENTRY), pd.Timestamp(ENTRY + timedelta(days=1))]))
        f.d[t] = pd.concat([df, extra])
    P._state["plan_try"] = None
    run(clock, ENTRY, "08:02", "08:03", step_s=30)
    plan2 = store.kv_get(P._pkey(ENTRY))
    for k in ("entries", "cutoff", "n_window"):
        assert plan1[k] == plan2[k]
    for t in plan1["rows"]:
        assert plan1["rows"][t]["ear"] == plan2["rows"][t]["ear"]


def test_seeding_computes_window_ears_from_bars_and_skips_missing_data(env):
    f, clock = world(env)
    store.kv_set("pead:ears", {})
    P.refresh_edgar(ENTRY)
    done, left = P.seed_ears(ENTRY)
    ears = store.kv_get("pead:ears")
    assert done and left == 0
    assert set(ears) == {f"AAA|{REACT}", f"BBB|{REACT}", "CCC|2026-08-05"}     # every event with a signal day before today
    assert ears[f"AAA|{REACT}"]["ear"] > 0.05 and ears[f"AAA|{REACT}"]["s"] == str(SIG)
    del f.d["CCC"]                                                              # no bars at all: stored as missing, not retried
    store.kv_set("pead:ears", {})
    P.seed_ears(ENTRY)
    assert store.kv_get("pead:ears")["CCC|2026-08-05"]["ear"] is None


def test_restart_reuses_the_plan_and_never_doubles_an_entry(env):
    f, clock = world(env)
    run(clock, ENTRY, "05:00", "08:01", step_s=30)
    run(clock, ENTRY, "09:30", "09:30:10")
    P._state.update(status="idle", last_error=None, mark_t=None, plan_try=None)  # a restart
    calls_before = len(env[3])
    run(clock, ENTRY, "09:30:15", "09:31")
    assert len(S.positions(ledger=P.LEDGER)) == 1 and entry(ENTRY, "AAA") == "ORDER"
    assert len(env[3]) == calls_before                                          # no new EDGAR refresh after the plan


def test_no_cutoff_without_200_ears_and_the_switch_stops_entries_only(env):
    f, clock = world(env)
    store.kv_set("pead:ears", dict(list(history_ears().items())[:150]))
    run(clock, ENTRY, "05:00", "08:01", step_s=30)
    plan = store.kv_get(P._pkey(ENTRY))
    assert plan["entries"] == [] and plan["rows"]["AAA"]["state"] == "NO CUTOFF"
    env[0].setattr(P, "switch_on", lambda: False)
    store.kv_set(P._pkey(ENTRY), None)
    store.kv_set("pead:ears", history_ears())
    P._state["plan_try"] = None
    run(clock, ENTRY, "08:05", "08:06", step_s=30)
    run(clock, ENTRY, "09:30", "09:30:10")
    assert entry(ENTRY, "AAA") == "SWITCH OFF" and not S.positions(ledger=P.LEDGER)


def test_a_missed_close_exit_waits_for_the_next_open(env):
    f, clock = world(env)
    run(clock, ENTRY, "05:00", "08:01", step_s=30)
    run(clock, ENTRY, "09:30", "09:30:10")
    pid = S.positions(ledger=P.LEDGER, status="OPEN")[0]["id"]
    f.dead.add("AAA")
    run(clock, EXIT, "15:55", "15:59:55")
    p = S.get(pid)
    assert p["status"] == "OPEN" and p["plan"]["pending_exit"]["next_open"]
    f.dead.discard("AAA")
    run(clock, EXIT, "15:59:40", "15:59:55")                                    # a quote reappears before the close: still waits
    assert S.get(pid)["status"] == "OPEN"
    nxt = P.next_session(EXIT)
    run(clock, nxt, "09:30", "09:30:10")
    c = S.get(pid)
    assert c["status"] == "CLOSED" and "LATE" in c["exit_reason"]


def test_pead_book_is_isolated_and_its_daily_stop_counts_only_todays_change(env):
    f, clock = world(env)
    for i in range(4):                                                          # a full stocks book with a big loss
        S.open_position({"id": f"s{i}", "ledger": "sip_orb5", "book": "stocks", "kind": "shares", "date": "2026-11-05",
                         "ticker": "AAA", "direction": "long", "side": "long", "qty": 1, "entry_px": 1.0, "entry_t": "x",
                         "legs": [{"symbol": "AAA", "action": "buy", "qty": 1}], "plan": {"mtm": -5000.0}})
    assert v4risk.admit(P.LEDGER, "pead", "AAA", "long") is None
    assert "pead" in v4risk.status()["limits"]["isolated_books"] and "pead" in v4risk.LIMITS["multi_day_books"]
    # an old position down $200 since entry, but only -$10 today: no stop; -$95 today: stop
    S.open_position({"id": "old", "ledger": P.LEDGER, "book": "pead", "kind": "shares", "date": "2026-11-02", "ticker": "CCC",
                     "direction": "long", "side": "long", "qty": 10, "entry_px": 30.0, "entry_t": "x",
                     "legs": [{"symbol": "CCC", "action": "buy", "qty": 10}],
                     "plan": {"mtm": -200.0, "day_base": -190.0, "day_base_day": "2026-11-05"}})
    assert v4risk.admit(P.LEDGER, "pead", "BBB", "long") is None
    S.update_plan("old", mtm=-285.0)
    assert "daily paper loss limit" in v4risk.admit(P.LEDGER, "pead", "BBB", "long")


def test_report_api_and_release_list_the_ledger(env):
    import release
    import v4api
    import v4report
    f, clock = world(env)
    run(clock, ENTRY, "05:00", "08:01", step_s=30)
    run(clock, ENTRY, "09:30", "09:30:10")
    d = v4report.overview("2026-11-02")
    books = {b["book"]: b for b in d["books"]}
    row = books["pead"]["ledgers"][0]
    assert row["ledger"] == "pead_t21" and row["open"] == 1 and row["evidence"].startswith("PAPER")
    st = v4api.get("/api/v4/pead", {})
    assert st["version"] == P.VERSION and st["data"]["universe"] == 3 and st["data"]["edgar_time_zone"] == "ET"
    assert release.component_versions()["pead_t21.VERSION"] == P.VERSION


def test_the_ledger_has_no_order_path_and_never_closes_for_being_overnight():
    src = (ROOT / "pead_t21.py").read_text()
    assert "broker" not in src.replace("broker.py", "") and "place_order" not in src and "submit_order" not in src
    assert "overnight(p" not in src and "overnight(" not in src.replace("v4exec.overnight()", "")
    cfg = json.loads((ROOT / "config" / "sp500.json").read_text())
    assert len(cfg["tickers"]) >= 495 and all(r["cik"] > 0 for r in cfg["tickers"])


def test_desk_down_on_the_exit_day_sells_at_the_next_open_late_and_frees_the_slot(env):
    f, clock = world(env)
    run(clock, ENTRY, "05:00", "08:01", step_s=30)
    run(clock, ENTRY, "09:30", "09:30:10")
    pid = S.positions(ledger=P.LEDGER, status="OPEN")[0]["id"]
    nxt = P.next_session(EXIT)                                                  # nothing ran on the exit day
    assert P.due_exits(nxt) == ([], [pid])
    run(clock, nxt, "09:30", "09:30:10")
    c = S.get(pid)
    assert c["status"] == "CLOSED" and "LATE" in c["exit_reason"]
