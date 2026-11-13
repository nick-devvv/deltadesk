"""core_trend: the T47 trend core (paper, held, isolated "tcore" risk book) and the T47 account view. The trend state
machine, no look-ahead, near-close trading of each half, holding overnight, the trend exit, restart safety, missed fills,
the switch, the monthly rebalance, margin interest, risk isolation without a daily stop and the wiring. Fake Schwab
quotes and daily bars only, no network."""
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
import core_spy  # noqa: E402
import core_trend as K  # noqa: E402
import fakes  # noqa: E402
import marketdata  # noqa: E402
import scanner  # noqa: E402
import store  # noqa: E402
import v4risk  # noqa: E402
import v4store as S  # noqa: E402

ET = core.ET
D1, D2, D3 = date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 30)      # Mon, Tue, Mon (after Thanksgiving week)
REB = date(2026, 12, 1)                                                       # Tue: the first session of December


def sessions(last, n):
    out, d = [], last
    while len(out) < n:
        if core_spy.is_session(d):
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def daily(closes, last=date(2026, 12, 4)):
    days = sessions(last, len(closes))
    return pd.DataFrame({"Close": closes, "Open": closes}, index=pd.DatetimeIndex([pd.Timestamp(d) for d in days]))


def rising(n=320, a=500.0, b=700.0):
    return list(np.linspace(a, b, n))


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
    def __init__(self, clock):
        self.clock, self.px, self.dead, self.ready_ = clock, {"SSO": 100.0, "QLD": 100.0}, set(), True
        self.bars = {"SPY": daily(rising()), "QQQ": daily(rising(a=400.0, b=600.0))}

    def ready(self):
        return self.ready_

    def daily(self, t):
        return self.bars[t]

    def quotes(self, ts):
        now = pd.Timestamp(self.clock())
        out = {}
        for t in ts:
            if t in self.dead:
                continue
            last = self.px.get(t, 100.0)
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
    K._state.update(status="idle", last_error=None, mark_t=None, plan_try=None)
    monkeypatch.setattr(K, "switch_on", lambda: True)
    clock = fakes.Clock(datetime(2026, 11, 23, 8, 0, tzinfo=ET))
    monkeypatch.setattr(core, "now_et", clock)
    prov = Prov()
    marketdata.use(prov)
    f = Fake(clock)
    scanner.use(f)
    prov.world = f
    yield monkeypatch, clock, f
    scanner.use(None)
    marketdata.use(None)


def run(clock, day, a, b, step_s=5):
    def at(s):
        hh, mm = int(s[:2]), int(s[3:5])
        ss = int(s[6:]) if len(s) > 5 else 0
        return datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=ET)
    t, end = at(a), at(b)
    while t <= end:
        clock.t = t
        K.step(t)
        t += timedelta(seconds=step_s)


def decision(h, day):
    r = [d for d in S.decisions(ledger=K.LEDGER, kind="entry") if d["id"] == f"{K.LEDGER}:{h}:{day}"]
    return r[0] if r else None


def opens(ticker=None):
    return [p for p in S.positions(ledger=K.LEDGER, status="OPEN") if ticker is None or p["ticker"] == ticker]


def drop_after(closes_daily, from_day, factor):
    """Multiply closes dated on/after from_day by factor (a crash that turns the trend OUT)."""
    d = closes_daily.copy()
    d.loc[d.index >= pd.Timestamp(from_day), "Close"] *= factor
    return d


def sat(pid, ledger, day, status="OPEN", realized=0.0, mtm=0.0, qty=10.0, px=100.0, ticker="TLT"):
    S.open_position({"id": pid, "ledger": ledger, "book": "swing" if ledger == "etf10_rsi2" else "trend", "kind": "shares",
                     "date": str(day), "ticker": ticker, "direction": "long", "side": "long", "qty": qty, "entry_px": px,
                     "entry_t": f"{day}T09:31:00", "legs": [{"symbol": ticker, "action": "buy", "qty": qty}],
                     "plan": {"mtm": mtm, "last_mark": px}})
    if status == "CLOSED":
        S.close_position(pid, px + realized / qty, "test exit")


# ================================================================ pure rules
def test_trend_state_machine_band_and_start():
    c = pd.Series(rising(260))
    st, sma = K.trend_states(c)
    assert st.iloc[:199].isna().all() and st.iloc[199] == 1 and st.iloc[-1] == 1           # starts IN when SMA200 exists
    m = float(sma.iloc[-1])
    x = list(c) + [0.96 * m]                                                                 # below 0.97 x SMA -> OUT
    st2, sma2 = K.trend_states(pd.Series(x))
    assert st2.iloc[-1] == 0
    m2 = float(sma2.iloc[-1])
    st3, _ = K.trend_states(pd.Series(x + [1.02 * m2]))                                      # inside the band: stays OUT
    assert st3.iloc[-1] == 0
    st4, _ = K.trend_states(pd.Series(x + [1.02 * m2, 1.06 * m2]))                           # above 1.04 x SMA -> IN
    assert st4.iloc[-1] == 1


def test_signal_uses_finished_bars_only_and_ignores_the_future():
    d = daily(rising())
    s = K.signal(d, D2)
    assert s["asof"] == str(D1) and s["state"] == 1
    later = drop_after(d, D2, 0.5)                                                           # today's and future bars crash
    assert K.signal(later, D2) == s                                                          # no look-ahead
    assert K.signal(drop_after(d, D1, 0.5), D2)["state"] == 0                                # yesterday's close counts
    assert K.signal(daily(rising(150)), D2) is None                                          # < 200 closes: no signal


def test_targets_base_and_window():
    assert K.targets(3000.0, 1000.0, {"S": 1, "Q": 1}) == {"S": 1500.0, "Q": 1500.0}
    assert K.targets(3000.0, 1000.0, {"S": 1, "Q": 0}) == {"S": 1500.0, "Q": 0.0}
    assert K.targets(1800.0, 1000.0, {"S": 1, "Q": 1}) == {"S": 400.0, "Q": 400.0}          # under $2,000: no borrowing
    assert K.targets(3000.0, 0.0, {"S": None, "Q": 1})["S"] == 0.0
    a, b = K.window(D1, "16:00")
    assert a.strftime("%H:%M") == "15:50" and b.strftime("%H:%M") == "15:58"
    assert K.window(D1, "13:00")[0].strftime("%H:%M") == "12:50"


# ================================================================ live ledger
def test_buys_both_halves_near_the_close_and_holds_overnight(env):
    mp, clock, f = env
    run(clock, D1, "09:30", "09:31")
    run(clock, D1, "15:40", "15:49:55")
    assert not opens()                                                                       # nothing before 15:50
    run(clock, D1, "15:50", "15:51")
    ps = opens()
    assert sorted(p["ticker"] for p in ps) == ["QLD", "SSO"] and all(p["book"] == "tcore" for p in ps)
    for p in ps:
        assert p["entry_px"] == pytest.approx(100.02) and p["qty"] == math.floor(1500 / 100.02 * 1e4) / 1e4   # ask + $0.01
    assert decision("S", D1)["decision"] == "ORDER" and decision("Q", D1)["decision"] == "ORDER" and K.start_day() == str(D1)
    f.px["SSO"] = 103.0
    run(clock, D2, "09:30", "09:31")
    p = opens("SSO")[0]
    assert p["plan"]["mtm"] == pytest.approx(round((102.99 - 100.02) * p["qty"], 2))
    run(clock, D2, "15:50", "15:51")
    assert len(opens()) == 2 and decision("S", D2)["decision"] == "HOLD" and decision("Q", D2)["decision"] == "HOLD"


def test_trend_exit_sells_one_half_near_the_close_and_keeps_the_other(env):
    mp, clock, f = env
    run(clock, D1, "15:50", "15:51")
    f.bars["QQQ"] = drop_after(f.bars["QQQ"], D1, 0.8)                                       # D1's close crashes: OUT on D2
    run(clock, D2, "09:30", "15:49:55")
    assert len(opens()) == 2                                                                 # decided near the close only
    run(clock, D2, "15:50", "15:51")
    d = decision("Q", D2)
    assert d["decision"] == "EXIT" and not opens("QLD") and len(opens("SSO")) == 1
    q = [p for p in S.positions(ledger=K.LEDGER) if p["ticker"] == "QLD"][0]
    assert q["status"] == "CLOSED" and "trend OUT" in q["exit_reason"]
    run(clock, D3, "15:50", "15:51")
    assert decision("Q", D3)["decision"] == "OUT" and not opens("QLD")                       # stays in cash while OUT


def test_out_at_start_buys_only_the_in_half(env):
    mp, clock, f = env
    f.bars["SPY"] = drop_after(f.bars["SPY"], date(2026, 11, 16), 0.8)
    run(clock, D1, "15:50", "15:51")
    assert decision("S", D1)["decision"] == "OUT" and [p["ticker"] for p in opens()] == ["QLD"]
    assert opens("QLD")[0]["plan"]["target"] == pytest.approx(1500.0)


def test_restart_never_buys_twice(env):
    mp, clock, f = env
    run(clock, D1, "15:50", "15:50:05")
    K._state.update(status="idle", mark_t=None, plan_try=None)                               # a restart
    run(clock, D1, "15:50:10", "15:55")
    assert len(opens()) == 2 and len(S.positions(ledger=K.LEDGER)) == 2


def test_missed_fill_is_recorded_and_retried_next_session(env):
    mp, clock, f = env
    f.dead.add("QLD")
    run(clock, D1, "15:50", "15:58:05")
    assert decision("Q", D1)["decision"] == "MISSED" and decision("S", D1)["decision"] == "ORDER" and not opens("QLD")
    f.dead.discard("QLD")
    run(clock, D2, "15:50", "15:51")
    assert decision("Q", D2)["decision"] == "ORDER" and len(opens("QLD")) == 1


def test_no_data_when_yesterdays_bar_never_arrives(env):
    mp, clock, f = env
    f.bars["QQQ"] = f.bars["QQQ"][f.bars["QQQ"].index < pd.Timestamp(date(2026, 11, 20))]
    run(clock, D1, "15:50", "15:58:05")
    assert decision("Q", D1)["decision"] == "NO DATA" and decision("S", D1)["decision"] == "ORDER"


def test_switch_off_blocks_buys_but_trend_exits_still_run(env):
    mp, clock, f = env
    run(clock, D1, "15:50", "15:51")
    mp.setattr(K, "switch_on", lambda: False)
    f.bars["QQQ"] = drop_after(f.bars["QQQ"], D1, 0.8)
    run(clock, D2, "15:50", "15:51")
    assert decision("Q", D2)["decision"] == "EXIT" and decision("S", D2)["decision"] == "HOLD"
    f.bars["QQQ"] = drop_after(f.bars["QQQ"], D1, 1.0 / 0.8 * 1.2)                           # back IN by D3
    run(clock, D3, "15:50", "15:51")
    assert decision("Q", D3)["decision"] == "SWITCH OFF" and not opens("QLD")


def test_monthly_rebalance_only_outside_the_band(env):
    mp, clock, f = env
    run(clock, D1, "15:50", "15:51")
    first = opens("SSO")[0]
    sat("etf10_rsi2:x", "etf10_rsi2", D2, status="CLOSED", realized=600.0)                  # the account made $600
    run(clock, D3, "15:50", "15:51")
    assert decision("S", D3)["decision"] == "HOLD"                                           # not the first session
    run(clock, REB, "15:50", "15:51")
    d = decision("S", REB)
    assert d["decision"] == "REBALANCE" and S.get(first["id"])["status"] == "CLOSED"
    new = S.get(f"{K.LEDGER}:{REB}-S-rebal")
    a = K.account(states={"S": 1, "Q": 1})
    assert new["status"] == "OPEN" and new["plan"]["target"] == pytest.approx(a["equity"] / 2, abs=0.5)


def test_rebalance_holds_inside_the_band(env):
    mp, clock, f = env
    run(clock, D1, "15:50", "15:51")
    run(clock, REB, "15:50", "15:51")
    assert decision("S", REB)["decision"] == "HOLD" and "within 5%" in decision("S", REB)["reasons"][0]
    assert len(opens()) == 2


def test_margin_interest_once_per_session_and_maintenance_warning(env):
    mp, clock, f = env
    run(clock, D1, "15:50", "15:51")
    sat("etf10_rsi2:y", "etf10_rsi2", D1, qty=10.0, px=100.0)                               # $1,000 of swing overnight
    run(clock, D1, "16:10", "16:10:10")
    run(clock, D1, "16:30", "16:30")
    log = store.kv_get("core_trend:interest")
    assert list(log) == [str(D1)]
    rec = log[str(D1)]
    assert rec["days"] == 1 and rec["debit"] == pytest.approx(max(0.0, rec["gross"] - rec["equity"]), abs=0.01)
    assert rec["debit"] > 900 and rec["interest"] == K.interest(rec["debit"], 1)
    a = K.account()
    assert a["maintenance_need"] == pytest.approx(0.5 * a["core_notional"] + 0.3 * a["swing_notional"], abs=0.01)
    assert not a["margin_warning"]
    sat("etf10_rsi2:big", "etf10_rsi2", D1, qty=20.0, px=100.0, mtm=-1500.0)                 # deep loss
    a = K.account()
    assert a["margin_warning"] and a["maintenance_to_equity"] > K.MAINT_WARN


def test_account_counts_only_t47_ledgers_since_start(env):
    mp, clock, f = env
    sat("etf10_rsi2:old", "etf10_rsi2", date(2026, 11, 20), status="CLOSED", realized=-500.0)   # before START: excluded
    run(clock, D1, "15:50", "15:51")
    sat("nbs_spy_ls:a", "nbs_spy_ls", D1, status="CLOSED", realized=12.5, ticker="SPY")
    sat("core_spy:a", "core_spy", D1, status="CLOSED", realized=77.0, ticker="SPY")             # not part of T47
    a = K.account()
    assert a["start"] == str(D1) and a["pnl_by_ledger"]["nbs_spy_ls"] == 12.5 and "core_spy" not in a["pnl_by_ledger"]
    assert a["equity"] == pytest.approx(3000 + 12.5 + a["pnl_by_ledger"]["core_trend"])
    assert set(a["notional_by_half"]) == {"S", "Q"} and a["notional_by_half"]["S"] > 1400


# ================================================================ risk book
def test_tcore_book_is_isolated_multi_day_and_has_no_daily_stop(env):
    mp, clock, f = env
    clock.t = datetime(2026, 11, 23, 10, 0, tzinfo=ET)
    lim = v4risk.LIMITS
    assert "tcore" in lim["isolated_books"] and "tcore" in lim["multi_day_books"] and "tcore" not in lim["book_daily_loss_usd"]
    assert lim["book_max_open"]["tcore"] == 2
    S.open_position({"id": "core_trend:t", "ledger": K.LEDGER, "book": "tcore", "kind": "shares", "date": "2026-11-23",
                     "ticker": "SSO", "direction": "long", "side": "long", "qty": 15, "entry_px": 100.0, "entry_t": "x",
                     "legs": [{"symbol": "SSO", "action": "buy", "qty": 15}], "plan": {"mtm": -5000.0}})
    assert "already has an open SSO" in v4risk.admit(K.LEDGER, "tcore", "SSO", "long")
    assert v4risk.admit(K.LEDGER, "tcore", "QLD", "long") is None
    assert v4risk.admit("core_spy", "core", "SPY", "long") is None                           # other books never count it
    S.close_position("core_trend:t", 100.0 - 1000.0 / 15, "test: a $1,000 loss today")
    assert v4risk.book_pnl_today("tcore") < -900 and v4risk.admit(K.LEDGER, "tcore", "SSO", "long") is None   # no daily stop


def test_kill_switch_closes_both_halves_and_blocks_new_buys(env):
    mp, clock, f = env
    run(clock, D1, "15:50", "15:51")
    r = v4risk.kill("test")
    assert r["closed"] >= 2 and not opens()
    run(clock, D2, "15:50", "15:51")
    assert decision("S", D2)["decision"] == "BLOCKED-RISK" and "kill switch" in decision("S", D2)["reasons"][0]


# ================================================================ wiring
def test_report_api_release_health_page_and_switch(env):
    mp, clock, f = env
    run(clock, D1, "15:50", "15:51")
    import v4api
    import v4report
    d = v4report.overview("2026-11-02")
    row = {b["book"]: b for b in d["books"]}["tcore"]["ledgers"][0]
    assert row["ledger"] == "core_trend" and row["open"] == 2 and row["evidence"].startswith("PAPER")
    assert row["backtest"]["t47_2022_2025"]["label"].startswith("BACKTEST") and row["account"]["start"] == str(D1)
    assert d["trend_core_account"]["equity"] == pytest.approx(row["account"]["equity"])
    st = v4api.get("/api/v4/tcore", {})
    assert st["version"] == K.VERSION and len(st["open"]) == 2 and st["signals"]["S"]["state"] == 1
    v = v4api.view(opens("SSO")[0])
    assert "200-day average" in v["next"]
    import release
    assert release.component_versions()["core_trend.VERSION"] == K.VERSION
    import health
    assert "v4tcore" in health.WORKERS
    assert 'tcore: "Trend core"' in (ROOT / "index.html").read_text()
    import json
    cfg = json.loads((ROOT / "config" / "v4.json").read_text())
    assert cfg["core_trend"] is False and cfg["core_spy"] is True and cfg["core_sso"] is True   # B2 (2026-11-13): no new buys


def test_no_order_path_and_no_overnight_sweep_in_the_module():
    src = (ROOT / "core_trend.py").read_text()
    code = src.split('"""', 2)[2]
    assert "overnight(" not in code and "import broker" not in code and "alpaca" not in code.lower()
    assert "/trader" not in code and "place_order" not in code
