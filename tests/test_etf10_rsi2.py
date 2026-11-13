"""etf10_rsi2: the ETF RSI(2) swing ledger (paper, held overnight, swing risk book). Frozen T6 R2 rules, fills at the
open, slots, no look-ahead, restart safety, risk isolation, the daily stop measured across sessions, the kill switch and
the switch. Fake Schwab data only, no network."""
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
import etf10_rsi2 as E  # noqa: E402
import fakes  # noqa: E402
import marketdata  # noqa: E402
import scanner  # noqa: E402
import store  # noqa: E402
import v4common as C  # noqa: E402
import v4risk  # noqa: E402
import v4store as S  # noqa: E402

ET = core.ET
D1, D2, D3 = date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6)        # Wed, Thu, Fri


# ================================================================ fake data
def closes_signal(n=260):
    """A steady uptrend, then three down closes: close > SMA200, close < SMA5, RSI2 < 10 on the last bar."""
    c = [100 + 0.1 * i for i in range(n - 3)]
    return c + [c[-1] - 1.0, c[-1] - 2.0, c[-1] - 3.0]


def closes_flat_up(n=260):
    return [100 + 0.1 * i for i in range(n)]


def frame(closes, end):
    idx = pd.bdate_range(end=pd.Timestamp(end), periods=len(closes))
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"Open": c, "High": c + 0.5, "Low": c - 0.5, "Close": c, "Volume": 1e7}, index=idx)


def add_bar(df, day, close):
    row = pd.DataFrame({"Open": close, "High": close + 0.5, "Low": close - 0.5, "Close": close, "Volume": 1e7},
                       index=pd.DatetimeIndex([pd.Timestamp(day)]))
    return pd.concat([df, row])


class Prov(marketdata.Provider):
    """Executable provider; its equity quotes (used by the kill switch's close_now) come from the fake world."""
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
    """scanner fetcher API: daily bars per symbol, quotes at clock - 0.5 s around a settable last price."""

    def __init__(self, clock, daily):
        self.clock, self.d, self.px, self.dead, self.ready_ = clock, daily, {}, set(), True
        self.daily_calls = 0

    def ready(self):
        return self.ready_

    def daily(self, t):
        self.daily_calls += 1
        return self.d.get(t)

    def quotes(self, ts):
        now = pd.Timestamp(self.clock())
        out = {}
        for t in ts:
            if t in self.dead:
                continue
            last = self.px.get(t, float(self.d[t]["Close"].iloc[-1]))
            out[t] = {"last": last, "bid": round(last - 0.01, 2), "ask": round(last + 0.01, 2),
                      "quote_ms": (now - pd.Timedelta(seconds=0.5)).value // 10 ** 6}
        return out, None


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    import health
    monkeypatch.setitem(health._feed, "ok", None)
    E._state.update(status="idle", last_error=None, mark_t=None, plan_try=None)
    clock = fakes.Clock(datetime(2026, 11, 4, 8, 0, tzinfo=ET))
    monkeypatch.setattr(core, "now_et", clock)
    prov = Prov()
    marketdata.use(prov)
    yield monkeypatch, clock, prov
    scanner.use(None)
    marketdata.use(None)


def world(env, signal=("SPY",), end=date(2026, 11, 3)):
    mp, clock, prov = env
    d = {t: frame(closes_signal() if t in signal else closes_flat_up(), end) for t in E.SYMBOLS}
    f = Fake(clock, d)
    scanner.use(f)
    prov.world = f
    return f, clock


def run(clock, day, a, b, step_s=5):
    def at(s):
        hh, mm = int(s[:2]), int(s[3:5])
        ss = int(s[6:]) if len(s) > 5 else 0
        return datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=ET)
    t, end = at(a), at(b)
    while t <= end:
        clock.t = t
        E.step(t)
        t += timedelta(seconds=step_s)


def entry(day, t):
    r = [d for d in S.decisions(ledger=E.LEDGER, kind="entry") if d["id"] == f"{E.LEDGER}:{day}-{t}"]
    return r[0]["decision"] if r else None


# ================================================================ pure rules
def test_rsi_is_wilders_two_period_exactly_as_the_backtest():
    c = pd.Series([10.0, 11.0, 10.5, 10.0, 12.0, 11.0, 10.0, 9.5])
    d = c.diff()
    up, dn = [None], [None]
    ref = [np.nan]
    au = ad = None
    for x in d.iloc[1:]:                                     # hand-rolled Wilder (alpha 1/2) seeded with the first move
        u, w = max(x, 0.0), max(-x, 0.0)
        au = u if au is None else 0.5 * u + 0.5 * au
        ad = w if ad is None else 0.5 * w + 0.5 * ad
        ref.append(100.0 if ad == 0 else 100 - 100 / (1 + au / ad))
    got = E.rsi(c)
    assert np.allclose(got.iloc[1:].to_numpy(), np.array(ref[1:]), atol=1e-9)


def test_signal_needs_all_three_conditions_on_the_last_finished_bar():
    day = D1
    sig = E.indicators(frame(closes_signal(), D1 - timedelta(days=1)), day)
    last = sig.iloc[-1]
    assert bool(last["sig"]) and last["close"] > last["sma200"] and last["close"] < last["sma5"] and last["rsi2"] < 10
    assert not E.indicators(frame(closes_flat_up(), D1 - timedelta(days=1)), day).iloc[-1]["sig"]      # close above SMA5
    down = [200 - 0.1 * i for i in range(257)]
    down += [down[-1] - 1, down[-1] - 2, down[-1] - 3]
    x = E.indicators(frame(down, D1 - timedelta(days=1)), day).iloc[-1]
    assert x["rsi2"] < 10 and x["close"] < x["sma5"] and not x["sig"]                                   # below SMA200
    mild = closes_flat_up(258) + [125.0, 125.6]                                                         # one small dip
    m = E.indicators(frame(mild, D1 - timedelta(days=1)), day).iloc[-1]
    assert not m["sig"]
    assert E.indicators(frame(closes_signal(199), D1 - timedelta(days=1)), day) is None                 # SMA200 undefined


def test_todays_forming_bar_and_future_bars_never_change_a_signal():
    base = frame(closes_signal(), D1 - timedelta(days=1))
    a = E.indicators(base, D1)
    b = E.indicators(add_bar(add_bar(base, D1, 500.0), D2, 1.0), D1)                 # today's forming bar + tomorrow
    pd.testing.assert_frame_equal(a, b)
    full = E.indicators(add_bar(add_bar(base, D1, 500.0), D2, 1.0), D3)              # computed later, on more history
    pd.testing.assert_frame_equal(full.loc[a.index], a)                              # earlier rows are unchanged
    assert E.finished_daily(add_bar(base, D1, 500.0), D1).index[-1].date() == date(2026, 11, 3)


def test_exit_counts_the_entry_days_own_close_and_sizes_are_fractional():
    base = frame(closes_signal(), date(2026, 11, 3))
    ind = E.indicators(add_bar(base, D1, 130.0), D2)                                  # entry day D1 closes above SMA5
    assert E.exit_due(ind, D1)[0] == D1
    ind2 = E.indicators(add_bar(base, D1, 121.0), D2)
    assert E.exit_due(ind2, D1) is None
    q, n = E.size(683.17)
    assert q == math.floor(1000 / 683.17 * 1e4) / 1e4 and n <= 1000.0 and n == pytest.approx(q * 683.17, abs=0.01)
    assert E.prev_session(date(2026, 11, 27)) == date(2026, 11, 25)                   # Thanksgiving skipped
    assert E.prev_session(date(2026, 11, 9)) == date(2026, 11, 6)                     # Monday -> Friday


# ================================================================ live ledger
def test_buy_at_the_open_hold_overnight_and_exit_at_the_next_open(env):
    f, clock = world(env, signal=("SPY",))
    run(clock, D1, "08:00", "08:00")
    plan = store.kv_get(E._pkey(D1))
    assert plan["entries"] == ["SPY"] and plan["asof"] == "2026-11-03" and not plan["exits"]
    chk = {d["ticker"]: d for d in S.decisions(ledger=E.LEDGER, kind="check")}
    assert chk["SPY"]["decision"] == "SIGNAL" and chk["QQQ"]["decision"] == "NO SIGNAL" and "SMA5" in chk["QQQ"]["reasons"][0]
    run(clock, D1, "09:29:55", "09:30:00")
    assert not S.positions(ledger=E.LEDGER)                                            # no fill before a quote after the open
    run(clock, D1, "09:30:05", "09:30:05")
    p = S.positions(ledger=E.LEDGER)[0]
    last = float(f.d["SPY"]["Close"].iloc[-1])
    assert p["entry_px"] == pytest.approx(round(last + 0.01, 2) + 0.01) and p["book"] == "swing"   # ask + $0.01
    assert p["qty"] == E.size(p["entry_px"])[0] and pd.Timestamp(p["quote_t"]) > pd.Timestamp(p["signal_t"])
    sg = E.sigma20(f.d["SPY"], D1)
    assert p["risk_usd"] == pytest.approx(round(p["plan"]["notional"] * 3 * sg, 2))
    assert entry(D1, "SPY") == "ORDER"
    run(clock, D1, "15:55", "15:59:55", step_s=30)                                     # no 15:55 flat for the swing book
    assert S.get(p["id"])["status"] == "OPEN"
    import sip_orb
    import v4index
    nxt = datetime(2026, 11, 5, 9, 31, tzinfo=ET)
    clock.t = nxt
    sip_orb.manage(nxt, {})                                                            # the day ledgers' overnight sweeps
    v4index.manage(nxt)                                                                # never touch this ledger
    assert S.get(p["id"])["status"] == "OPEN"
    # Thursday: Wednesday's close is above SMA5 -> exit at Thursday's open
    f.d = {t: add_bar(v, D1, 130.0 if t == "SPY" else float(v["Close"].iloc[-1]) + 0.1) for t, v in f.d.items()}
    f.px["SPY"] = 130.5
    run(clock, D2, "08:00", "08:00")
    plan2 = store.kv_get(E._pkey(D2))
    assert [e["id"] for e in plan2["exits"]] == [p["id"]] and "close 130.00 > SMA5" in plan2["exits"][0]["reason"]
    run(clock, D2, "09:30:05", "09:30:05")
    c = S.get(p["id"])
    assert c["status"] == "CLOSED" and c["exit_px"] == pytest.approx(130.49 - 0.01) and c["exit_reason"].startswith("EXIT at the open")
    assert c["realized"] == pytest.approx(round((c["exit_px"] - c["entry_px"]) * c["qty"], 2))


def test_three_slots_universe_order_and_exits_free_their_slot_first(env):
    f, clock = world(env, signal=("SPY", "QQQ", "IWM", "DIA", "XLF"))
    run(clock, D1, "08:00", "08:00")
    run(clock, D1, "09:30:05", "09:30:10")
    held = sorted(p["ticker"] for p in S.positions(ledger=E.LEDGER, status="OPEN"))
    assert held == ["IWM", "QQQ", "SPY"]                                               # first three in universe order
    assert entry(D1, "DIA") == "NO SLOT" and entry(D1, "XLF") == "NO SLOT"
    # Thursday: SPY exits at the open, XLE signals: it takes the freed slot at the same open
    new = {}
    for t, v in f.d.items():
        if t == "SPY":
            new[t] = add_bar(v, D1, 130.0)
        elif t in ("QQQ", "IWM"):
            new[t] = add_bar(v, D1, float(v["Close"].iloc[-1]) - 0.5)                 # still below SMA5: hold
        elif t == "XLE":
            new[t] = frame(closes_signal(), D1)                                         # signals on Wednesday's close
        else:
            new[t] = add_bar(v, D1, float(v["Close"].iloc[-1]) + 5.0)
    f.d = new
    run(clock, D2, "08:00", "08:00")
    plan = store.kv_get(E._pkey(D2))
    assert plan["entries"] == ["XLE"] and [e["ticker"] for e in plan["exits"]] == ["SPY"]
    run(clock, D2, "09:30:05", "09:30:10")
    held = sorted(p["ticker"] for p in S.positions(ledger=E.LEDGER, status="OPEN"))
    assert held == ["IWM", "QQQ", "XLE"] and entry(D2, "XLE") == "ORDER"


def test_no_fresh_quote_by_0940_is_missed_and_a_late_desk_exits_late(env):
    f, clock = world(env, signal=("SPY", "GLD"))
    f.dead.add("GLD")
    run(clock, D1, "08:00", "08:00")
    run(clock, D1, "09:30:05", "09:40:05", step_s=60)
    assert entry(D1, "SPY") == "ORDER" and entry(D1, "GLD") == "MISSED"
    p = S.positions(ledger=E.LEDGER)[0]
    # Thursday the desk is down all day; Friday it starts at 10:12 -> Wednesday's exit signal is LATE
    f.d = {t: add_bar(add_bar(v, D1, 130.0 if t == "SPY" else float(v["Close"].iloc[-1])), D2,
                      129.0 if t == "SPY" else float(v["Close"].iloc[-1])) for t, v in f.d.items()}
    run(clock, D3, "10:12", "10:12")
    c = S.get(p["id"])
    assert c["status"] == "CLOSED" and "LATE" in c["exit_reason"] and "2026-11-04" in c["exit_reason"]


def test_restart_never_enters_or_exits_twice(env):
    f, clock = world(env, signal=("SPY",))
    run(clock, D1, "08:00", "08:00")
    calls = f.daily_calls
    run(clock, D1, "09:30:05", "09:30:30")
    assert len(S.positions(ledger=E.LEDGER)) == 1
    E._state.update(mark_t=None, plan_try=None)                                        # a restart: in-memory state gone
    S._ready["db"] = None
    run(clock, D1, "09:31", "09:33")
    assert len(S.positions(ledger=E.LEDGER)) == 1 and f.daily_calls == calls          # the stored plan is reused
    store.x("DELETE FROM v4_decisions WHERE kind='entry'")                             # even a lost decision can't re-enter
    run(clock, D1, "09:34", "09:35")
    assert len(S.positions(ledger=E.LEDGER)) == 1 and S.decisions(ledger=E.LEDGER, kind="entry")[0]["decision"] == "SKIP"


def test_switch_off_stops_entries_but_not_exits(env, monkeypatch):
    f, clock = world(env, signal=("SPY",))
    run(clock, D1, "08:00", "09:30:05")
    p = S.positions(ledger=E.LEDGER)[0]
    monkeypatch.setattr(E, "switch_on", lambda: False)
    f.d = {t: add_bar(v, D1, 130.0 if t == "SPY" else float(v["Close"].iloc[-1])) for t, v in f.d.items()}
    f.d["QQQ"] = frame(closes_signal(), date(2026, 11, 4))
    run(clock, D2, "08:00", "08:00")
    run(clock, D2, "09:30:05", "09:30:05")
    assert S.get(p["id"])["status"] == "CLOSED" and entry(D2, "QQQ") == "SWITCH OFF"


def test_kill_switch_closes_swing_positions_and_blocks_new_entries(env):
    f, clock = world(env, signal=("SPY",))
    run(clock, D1, "08:00", "09:30:05")
    p = S.positions(ledger=E.LEDGER)[0]
    r = v4risk.kill("test")
    assert r["closed"] == 1 and S.get(p["id"])["status"] == "CLOSED" and "KILL SWITCH" in S.get(p["id"])["exit_reason"]
    f.d["QQQ"] = frame(closes_signal(), date(2026, 11, 4))
    f.d = {t: (v if t == "QQQ" else add_bar(v, D1, float(v["Close"].iloc[-1]))) for t, v in f.d.items()}
    run(clock, D2, "08:00", "09:30:05")
    assert entry(D2, "QQQ") == "BLOCKED-RISK" and "kill switch" in S.decisions(ledger=E.LEDGER, kind="entry")[0]["reasons"][0]


# ================================================================ risk book
def _swing(i, ticker, day="2026-11-04", mtm=None, plan=None, status="OPEN", exit_px=None, ledger="etf10_rsi2"):
    rec = {"id": f"{ledger}:{i}", "ledger": ledger, "book": "swing", "kind": "shares", "date": day, "ticker": ticker,
           "direction": "long", "side": "long", "qty": 10, "entry_px": 100.0, "entry_t": f"{day}T09:30:05-05:00",
           "legs": [{"symbol": ticker, "action": "buy", "qty": 10}], "plan": dict(plan or {}, **({"mtm": mtm} if mtm is not None else {})),
           "fees": 0.0}
    S.open_position(rec)
    if status == "CLOSED":
        S.close_position(rec["id"], exit_px, "test")
    return rec["id"]


def test_swing_book_is_isolated_both_ways(env, monkeypatch):
    mp, clock, _ = env
    clock.t = datetime(2026, 11, 5, 10, 0, tzinfo=ET)
    for i, t in enumerate(("SPY", "QQQ", "IWM")):
        _swing(i, t)
    assert v4risk.admit("sip_orb5", "stocks", "SPY", "long") is None                   # stocks never see swing positions
    monkeypatch.setitem(v4risk.LIMITS, "book_max_open", dict(v4risk.LIMITS["book_max_open"], swing=3))
    assert "swing book cap" in v4risk.admit(E.LEDGER, "swing", "DIA", "long")
    assert "already has an open SPY" in v4risk.admit(E.LEDGER, "swing", "SPY", "long")
    for i in range(4):
        S.open_position({"id": f"sip_orb5:x{i}", "ledger": "sip_orb5", "book": "stocks", "kind": "shares", "date": "2026-11-05",
                         "ticker": "DIA", "direction": "long", "side": "long", "qty": 1, "entry_px": 1.0, "entry_t": "x",
                         "legs": [{"symbol": "DIA", "action": "buy", "qty": 1}], "plan": {"mtm": -5000.0}})
    monkeypatch.setitem(v4risk.LIMITS, "book_max_open", dict(v4risk.LIMITS["book_max_open"], swing=10))
    assert v4risk.admit(E.LEDGER, "swing", "DIA", "long") is None                      # 4 DIA stock trades + a huge stocks loss
    assert v4risk.status()["limits"]["isolated_books"] == ["sprint", "swing", "trend", "pead", "core", "tcore", "score", "copilot"]


def test_daily_stop_counts_only_todays_change_across_sessions(env):
    mp, clock, _ = env
    clock.t = datetime(2026, 11, 5, 10, 0, tzinfo=ET)
    _swing(1, "SPY", day="2026-11-03", mtm=-200.0)                                    # down $200 since entry, all before today
    assert v4risk.book_pnl_today("swing") == 0.0 and v4risk.admit(E.LEDGER, "swing", "QQQ", "long") is None
    S.update_plan(f"{E.LEDGER}:1", day_base=-200.0, day_base_day="2026-11-05", mtm=-260.0)
    _swing(2, "IWM", day="2026-11-05", mtm=-35.0, plan={"day_base": 0.0, "day_base_day": "2026-11-05"})
    assert v4risk.book_pnl_today("swing") == pytest.approx(-95.0)                      # -60 today + -35 today
    assert "swing book daily paper loss limit" in v4risk.admit(E.LEDGER, "swing", "QQQ", "long")
    # a position entered yesterday and closed today counts from its last mark before today, not from its entry
    clock.t = datetime(2026, 11, 6, 10, 0, tzinfo=ET)
    _swing(3, "GLD", day="2026-11-05", mtm=-40.0)
    S.close_position(f"{E.LEDGER}:3", 100.0 - 5.0, "exit at the open")                 # realized -50, mark was -40
    pl = {p["id"]: p for p in S.positions(book="swing")}
    assert v4risk.day_base(pl[f"{E.LEDGER}:3"], "2026-11-06") == -40.0
    assert v4risk.book_pnl_today("swing") == pytest.approx(-10.0)                      # -50 realized vs a -40 mark; others 0
    assert v4risk.book_pnl_today("stocks") == 0.0                                       # single-day books unchanged


def test_marks_set_the_days_base_from_the_previous_session(env):
    f, clock = world(env, signal=("SPY",))
    run(clock, D1, "08:00", "09:30:05")
    p = S.positions(ledger=E.LEDGER)[0]
    f.px["SPY"] = p["entry_px"] - 2.0
    run(clock, D1, "15:59", "15:59")
    m1 = S.get(p["id"])["plan"]["mtm"]
    assert m1 == pytest.approx(round(((p["entry_px"] - 2.0 - 0.01) - p["entry_px"]) * p["qty"], 2))
    f.d = {t: add_bar(v, D1, 121.0 if t == "SPY" else float(v["Close"].iloc[-1])) for t, v in f.d.items()}
    f.px["SPY"] = p["entry_px"] - 3.0
    run(clock, D2, "08:00", "08:00")
    assert not store.kv_get(E._pkey(D2))["exits"]                                       # 121 < SMA5: hold
    run(clock, D2, "09:45", "09:45")
    assert S.get(p["id"])["status"] == "OPEN"                                          # held overnight: no sweep closed it
    q = S.get(p["id"])["plan"]
    assert q["day_base_day"] == "2026-11-05" and q["day_base"] == pytest.approx(m1)
    assert v4risk.book_pnl_today("swing") == pytest.approx(round(q["mtm"] - m1, 2))


# ================================================================ wiring
def test_report_view_and_api_label_the_swing_ledger(env):
    f, clock = world(env, signal=("SPY",))
    run(clock, D1, "08:00", "09:30:05")
    import v4api
    import v4report
    p = S.positions(ledger=E.LEDGER)[0]
    v = v4api.view(p)
    assert v["desc"] == f"long {p['qty']:g} sh" and "next open after a daily close > SMA(5)" in v["next"]
    d = v4report.overview("2026-11-02")
    sw = {b["book"]: b for b in d["books"]}["swing"]
    row = sw["ledgers"][0]
    assert row["ledger"] == "etf10_rsi2" and row["open"] == 1 and row["evidence"].startswith("PAPER")
    assert row["backtest"]["sealed_2022_2025"]["label"].startswith("BACKTEST") and "swing_worker" in d
    assert v4api.get("/api/v4/swing", {})["plan"]["entries"] == ["SPY"]
    import release
    assert release.component_versions()["etf10_rsi2.VERSION"] == E.VERSION
    import health
    assert "v4swing" in health.WORKERS


def test_no_order_path_and_no_overnight_sweep_in_the_module():
    src = (ROOT / "etf10_rsi2.py").read_text()
    code = src.split('"""', 2)[2]                                                       # skip the docstring
    assert "overnight(" not in code and "import broker" not in code and "alpaca" not in code.lower()
    assert "/trader" not in code and "place_order" not in code
