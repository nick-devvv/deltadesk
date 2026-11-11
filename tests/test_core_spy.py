"""core_spy: the T30b SPY core (paper, held, isolated "core" risk book) and the T30b account view. Calendar, sizing,
the first entry at the open, holding overnight, the monthly rebalance band, margin interest once per session (and the
morning catch-up), the $2,000 no-borrowing rule, the switch, the kill switch, risk isolation without a daily stop,
restart safety and the wiring. Fake Schwab quotes only, no network."""
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import core  # noqa: E402
import core_spy as K  # noqa: E402
import fakes  # noqa: E402
import marketdata  # noqa: E402
import scanner  # noqa: E402
import store  # noqa: E402
import v4risk  # noqa: E402
import v4store as S  # noqa: E402

ET = core.ET
D1, D2, D3 = date(2026, 11, 24), date(2026, 11, 25), date(2026, 11, 30)      # Tue, Wed (Thanksgiving next), Mon
REB = date(2026, 12, 1)                                                       # Tue: the first session of December


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
    def __init__(self, clock, px=600.0):
        self.clock, self.px, self.dead, self.ready_ = clock, {"SPY": px}, set(), True

    def ready(self):
        return self.ready_

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
    K._state.update(status="idle", last_error=None, mark_t=None)
    monkeypatch.setattr(K, "switch_on", lambda: True)
    clock = fakes.Clock(datetime(2026, 11, 24, 8, 0, tzinfo=ET))
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


def decision(day):
    r = [d for d in S.decisions(ledger=K.LEDGER, kind="entry") if d["id"] == f"{K.LEDGER}:open:{day}"]
    return r[0] if r else None


def sat(pid, ledger, day, status="OPEN", realized=0.0, mtm=0.0, qty=10.0, px=100.0, ticker="QQQ"):
    S.open_position({"id": pid, "ledger": ledger, "book": "swing" if ledger == "etf10_rsi2" else "trend", "kind": "shares",
                     "date": str(day), "ticker": ticker, "direction": "long", "side": "long", "qty": qty, "entry_px": px,
                     "entry_t": f"{day}T09:31:00", "legs": [{"symbol": ticker, "action": "buy", "qty": qty}],
                     "plan": {"mtm": mtm, "last_mark": px}})
    if status == "CLOSED":
        S.close_position(pid, px + realized / qty, "test exit")


# ================================================================ pure rules
def test_calendar_target_band_interest_and_size():
    assert K.rebalance_day(REB) and K.rebalance_day(date(2026, 11, 2)) and not K.rebalance_day(D3)
    assert K.rebalance_day(date(2027, 1, 4)) and not K.rebalance_day(date(2027, 1, 1))   # New Year's Day is a holiday
    assert K.next_session(D2) == date(2026, 11, 27) and K.prev_session(REB) == D3          # Thanksgiving skipped
    assert K.target(3500.0, 1000.0) == 3500.0                                               # 1x equity, borrowing allowed
    assert K.target(1800.0, 1000.0) == 800.0 and K.target(1500.0, 2000.0) == 0.0            # under $2,000: no borrowing
    assert not K.needs_rebalance(3000.0, 3100.0) and K.needs_rebalance(3000.0, 3600.0) and K.needs_rebalance(10.0, 0.0)
    assert K.interest(1000.0, 3) == round(1000 * 0.065 * 3 / 360, 4) and K.interest(-5.0, 1) == 0.0
    q, n = K.size(3000.0, 600.02)
    assert q == math.floor(3000 / 600.02 * 1e4) / 1e4 and n <= 3000.0


# ================================================================ live ledger
def test_buys_once_at_the_open_holds_overnight_and_marks(env):
    mp, clock, f = env
    run(clock, D1, "09:29", "09:31")
    ps = S.positions(ledger=K.LEDGER)
    assert len(ps) == 1 and ps[0]["status"] == "OPEN" and ps[0]["book"] == "core"
    p = ps[0]
    assert p["entry_px"] == pytest.approx(600.02) and p["qty"] == math.floor(3000 / 600.02 * 1e4) / 1e4
    assert decision(D1)["decision"] == "ORDER" and K.start_day() == str(D1)
    f.px["SPY"] = 606.0
    run(clock, D1, "15:58", "15:59")
    assert S.get(p["id"])["plan"]["mtm"] == pytest.approx(round((605.99 - 600.02) * p["qty"], 2))
    run(clock, D2, "09:29", "09:31")
    assert len(S.positions(ledger=K.LEDGER)) == 1 and S.get(p["id"])["status"] == "OPEN"   # held: no sweep, no new buy
    assert decision(D2)["decision"] == "HOLD"


def test_restart_never_buys_twice(env):
    mp, clock, f = env
    run(clock, D1, "09:30", "09:30:10")
    K._state.update(status="idle", mark_t=None)                                             # a restart
    run(clock, D1, "09:30:15", "09:35")
    assert len(S.positions(ledger=K.LEDGER)) == 1


def test_monthly_rebalance_only_outside_the_band(env):
    mp, clock, f = env
    run(clock, D1, "09:30", "09:31")
    first = S.positions(ledger=K.LEDGER)[0]
    run(clock, D3, "09:30", "09:31")
    assert decision(D3)["decision"] == "HOLD"                                               # not the first session
    sat("etf10_rsi2:x", "etf10_rsi2", D2, status="CLOSED", realized=600.0)                  # the account made $600
    run(clock, REB, "09:30", "09:31")
    d = decision(REB)
    assert d["decision"] == "REBALANCE" and S.get(first["id"])["status"] == "CLOSED"
    new = S.get(f"{K.LEDGER}:{REB}-rebal")
    a = K.account()
    assert new["status"] == "OPEN" and new["plan"]["target"] == pytest.approx(a["equity"], abs=0.5)
    assert new["qty"] * new["entry_px"] == pytest.approx(new["plan"]["target"], abs=1.0) and new["plan"]["target"] > 3500


def test_rebalance_holds_inside_the_band(env):
    mp, clock, f = env
    run(clock, D1, "09:30", "09:31")
    run(clock, REB, "09:30", "09:31")
    assert decision(REB)["decision"] == "HOLD" and "within 5%" in decision(REB)["reasons"][0]
    assert len(S.positions(ledger=K.LEDGER)) == 1


def test_margin_interest_once_per_session_and_the_morning_catch_up(env):
    mp, clock, f = env
    run(clock, D1, "09:30", "09:31")
    sat("etf10_rsi2:y", "etf10_rsi2", D1, qty=10.0, px=100.0)                               # $1,000 of swing overnight
    run(clock, D1, "16:10", "16:10:10")
    run(clock, D1, "16:30", "16:30")                                                        # again: recorded once
    log = store.kv_get("core:interest")
    assert list(log) == [str(D1)]
    rec = log[str(D1)]
    a_gross = rec["gross"]
    assert rec["days"] == 1 and rec["debit"] == pytest.approx(max(0.0, a_gross - rec["equity"]), abs=0.01)
    assert rec["debit"] > 900 and rec["interest"] == K.interest(rec["debit"], 1)
    # D2 evening missed (no step after the close); the next session's morning catches it up with 2 days (Thanksgiving)
    run(clock, D2, "09:30", "09:31")
    run(clock, date(2026, 11, 27), "08:00", "08:00")
    log = store.kv_get("core:interest")
    assert log[str(D2)]["days"] == 2 and K.account()["margin_interest"] == pytest.approx(
        round(log[str(D1)]["interest"] + log[str(D2)]["interest"], 2), abs=0.01)


def test_account_counts_only_t30b_ledgers_since_start_and_flags_margin(env):
    mp, clock, f = env
    sat("etf10_rsi2:old", "etf10_rsi2", date(2026, 11, 20), status="CLOSED", realized=-500.0)   # before START: excluded
    run(clock, D1, "09:30", "09:31")
    sat("nbs_spy_ls:a", "nbs_spy_ls", D1, status="CLOSED", realized=12.5, ticker="SPY")
    sat("nbs_spy_long:a", "nbs_spy_long", D1, status="CLOSED", realized=99.0, ticker="SPY")     # not part of T30b
    a = K.account()
    assert a["start"] == str(D1) and a["pnl_by_ledger"]["nbs_spy_ls"] == 12.5 and "nbs_spy_long" not in a["pnl_by_ledger"]
    assert a["pnl_by_ledger"]["etf10_rsi2"] == 0.0 and a["equity"] == pytest.approx(3000 + 12.5 + a["pnl_by_ledger"]["core_spy"])
    sat("etf10_rsi2:big", "etf10_rsi2", D1, qty=50.0, px=100.0, mtm=-1800.0)                 # deep loss + big swing book
    a = K.account()
    assert a["equity"] < 2000 and a["target"] == pytest.approx(max(0.0, a["equity"] - a["swing_notional"]), abs=0.01)
    assert a["margin_warning"] and a["equity_to_gross"] < K.WARN_RATIO


def test_switch_off_blocks_the_entry_and_rebalances_but_keeps_the_core(env):
    mp, clock, f = env
    mp.setattr(K, "switch_on", lambda: False)
    run(clock, D1, "09:30", "09:31")
    assert not S.positions(ledger=K.LEDGER) and decision(D1)["decision"] == "SWITCH OFF"
    mp.setattr(K, "switch_on", lambda: True)
    run(clock, D2, "09:30", "09:31")
    p = S.positions(ledger=K.LEDGER, status="OPEN")[0]
    sat("etf10_rsi2:z", "etf10_rsi2", D2, status="CLOSED", realized=900.0)
    mp.setattr(K, "switch_on", lambda: False)
    run(clock, REB, "09:30", "09:31")
    assert decision(REB)["decision"] == "SWITCH OFF" and S.get(p["id"])["status"] == "OPEN"


def test_missed_open_is_recorded_and_retried_next_session(env):
    mp, clock, f = env
    f.dead.add("SPY")
    run(clock, D1, "09:30", "09:41")
    assert decision(D1)["decision"] == "MISSED" and not S.positions(ledger=K.LEDGER)
    f.dead.discard("SPY")
    run(clock, D2, "09:30", "09:31")
    assert decision(D2)["decision"] == "ORDER" and K.start_day() == str(D2)


# ================================================================ risk book
def test_core_book_is_isolated_multi_day_and_has_no_daily_stop(env):
    mp, clock, f = env
    clock.t = datetime(2026, 11, 24, 10, 0, tzinfo=ET)
    lim = v4risk.LIMITS
    assert "core" in lim["isolated_books"] and "core" in lim["multi_day_books"] and "core" not in lim["book_daily_loss_usd"]
    assert lim["book_max_open"]["core"] == 1
    S.open_position({"id": "core_spy:t", "ledger": K.LEDGER, "book": "core", "kind": "shares", "date": "2026-11-24",
                     "ticker": "SPY", "direction": "long", "side": "long", "qty": 5, "entry_px": 600.0, "entry_t": "x",
                     "legs": [{"symbol": "SPY", "action": "buy", "qty": 5}], "plan": {"mtm": -5000.0}})
    assert "already has an open SPY" in v4risk.admit(K.LEDGER, "core", "SPY", "long")
    assert v4risk.admit("etf10_rsi2", "swing", "SPY", "long") is None                       # other books never count it
    assert v4risk.admit("nbs_spy_ls", "trend", "SPY", "long") is None
    S.close_position("core_spy:t", 600.0 - 1000.0 / 5, "test: a $1,000 loss today")
    assert v4risk.book_pnl_today("core") < -900 and v4risk.admit(K.LEDGER, "core", "SPY", "long") is None   # no daily stop


def test_kill_switch_closes_the_core_and_blocks_the_entry(env):
    mp, clock, f = env
    run(clock, D1, "09:30", "09:31")
    p = S.positions(ledger=K.LEDGER)[0]
    r = v4risk.kill("test")
    assert r["closed"] >= 1 and S.get(p["id"])["status"] == "CLOSED" and "KILL SWITCH" in S.get(p["id"])["exit_reason"]
    run(clock, D2, "09:30", "09:31")
    assert decision(D2)["decision"] == "BLOCKED-RISK" and "kill switch" in decision(D2)["reasons"][0]


# ================================================================ wiring
def test_report_api_release_health_page_and_switch(env):
    mp, clock, f = env
    run(clock, D1, "09:30", "09:31")
    import v4api
    import v4report
    d = v4report.overview("2026-11-02")
    row = {b["book"]: b for b in d["books"]}["core"]["ledgers"][0]
    assert row["ledger"] == "core_spy" and row["open"] == 1 and row["evidence"].startswith("PAPER")
    assert row["backtest"]["2022_2025"]["label"].startswith("BACKTEST") and row["account"]["start"] == str(D1)
    assert d["core_account"]["equity"] == pytest.approx(row["account"]["equity"])
    st = v4api.get("/api/v4/core", {})
    assert st["version"] == K.VERSION and st["open"] and st["account"]["target"] > 0
    v = v4api.view(S.positions(ledger=K.LEDGER)[0])
    assert "rebalanced" in v["next"]
    import release
    assert release.component_versions()["core_spy.VERSION"] == K.VERSION and release.RELEASE_ID.endswith("v4-core")
    import health
    assert "v4core" in health.WORKERS
    assert 'core: "SPY core"' in (ROOT / "index.html").read_text()
    import json
    assert json.loads((ROOT / "config" / "v4.json").read_text())["core_spy"] is True


def test_no_order_path_and_no_overnight_sweep_in_the_module():
    src = (ROOT / "core_spy.py").read_text()
    code = src.split('"""', 2)[2]
    assert "overnight(" not in code and "import broker" not in code and "alpaca" not in code.lower()
    assert "/trader" not in code and "place_order" not in code
