"""v3.2 part 2: the anti-chasing entry gate, options market hours, paper realism (no capped losses, no closed-market
fills), catalysts (sources, rumors, duplicates, recycled stories, untrusted text) and earnings. Offline."""
from datetime import datetime, timedelta

import pandas as pd
import pytest

import core
import entrygate as G
import marketdata
import store

ET = core.ET
DAY = datetime(2026, 10, 28, tzinfo=ET)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    clock = Clock(DAY.replace(hour=10, minute=0))
    monkeypatch.setattr(core, "now_et", clock)
    monkeypatch.setattr(G, "cfg", lambda: dict(G.DEFAULTS, min_rr=2.0, zone_atr5=0.6))
    yield clock
    marketdata.use(None)


def snap(price, close1, t, atr5=1.0, spread=0.01, fresh=True):
    return {"price": price, "close1": close1, "t": t, "atr5": atr5, "spread": spread, "spread_pct": round(spread / price * 100, 3),
            "fresh": fresh, "bar_age_s": 5, "buf": 0.02}


def test_worked_example_latest_entry_and_late_entry_deterioration():
    assert G.rr(100.00, 101.00, 99.50, "C", 0) == 2.0
    assert G.rr(100.80, 101.00, 99.50, "C", 0) == pytest.approx(0.15, abs=0.01)      # $0.20 reward vs $1.30 risk
    le, by_rr = G.latest_entry(100.00, 101.00, 99.50, "C", 0.0, 1.0, dict(G.DEFAULTS, min_rr=2.0))
    assert by_rr == 100.0 and le == 100.0                                             # at 2:1 nothing past the trigger is acceptable
    assert G.rr(99.0, 98.0, 99.5, "P", 0) == 2.0                                      # puts mirror
    le_p, _ = G.latest_entry(99.0, 97.0, 99.5, "P", 0.0, 1.0, dict(G.DEFAULTS, min_rr=2.0))
    assert le_p == 98.67                                                               # (97 + 2 x 99.5) / 3: the 2:1 price


def test_states_watching_confirmation_met_extended_missed_invalidated(env):
    clock = env
    t0 = pd.Timestamp(DAY.replace(hour=9, minute=59))
    g = G.define("NVDA", "C", "orb_break", 100.0, 99.0, 103.0, "PDH", snap(99.0, 99.0, t0), "1m close above 100.00")
    assert G.evaluate(g, snap(99.0, 99.0, t0))["state"] == "WATCHING"
    assert G.evaluate(g, snap(99.95, 99.9, t0))["state"] == "CONFIRMATION NEEDED"
    t1 = pd.Timestamp(DAY.replace(hour=10, minute=0))
    r = G.evaluate(G._load(g["id"]), snap(100.2, 100.1, t1))
    assert r["state"] == "ENTRY CONDITIONS MET" and r["rr_now"] >= 2 and all(c["pass"] for c in r["checks"])
    clock.t = DAY.replace(hour=10, minute=1)
    r = G.evaluate(G._load(g["id"]), snap(100.75, 100.3, t1))                         # price ran past the zone (100.60)
    assert r["state"] == "TOO EXTENDED" and "Don't chase" in r["rejected"]
    t2 = pd.Timestamp(DAY.replace(hour=10, minute=1))
    r = G.evaluate(G._load(g["id"]), snap(100.8, 100.7, t2))                          # a finished close past it: missed
    assert r["state"] == "WAIT FOR RETEST" and "move already happened" in r["rejected"]
    again = G.define("NVDA", "C", "orb_break", 100.0, 99.0, 103.0, "PDH", snap(100.1, 100.1, t2), "x")
    assert G.evaluate(again, snap(100.1, 100.1, t2))["state"] == "WAIT FOR RETEST"   # coming back doesn't revive it
    assert again["latest_entry"] == g["latest_entry"] and again["invalidation"] == 99.0 and again["target"] == 103.0  # never edited
    g2 = G.define("AMD", "C", "vwap", 50.0, 49.5, 52.0, "PDH", snap(50.1, 50.1, t1), "x", confirmed_at=t1.isoformat())
    assert G.evaluate(g2, snap(49.4, 49.4, t2))["state"] == "INVALIDATED"


def test_entry_window_expires_after_confirmation(env):
    clock = env
    t1 = pd.Timestamp(DAY.replace(hour=10, minute=0))
    g = G.define("MSFT", "C", "orb_break", 400.0, 398.0, 410.0, "PDH", snap(400.2, 400.2, t1), "x", confirmed_at=t1.isoformat())
    clock.t = DAY.replace(hour=10, minute=11)                                         # window_min = 10
    r = G.evaluate(g, snap(400.3, 400.3, pd.Timestamp(DAY.replace(hour=10, minute=10))))
    assert r["state"] == "WAIT FOR RETEST" and "entry window closed" in r["rejected"]


def test_a_bullish_score_cannot_bypass_the_gate(env, monkeypatch):
    """The gate has no sentiment input at all, and a plan with a glowing catalyst still can't become READY."""
    import inspect
    assert "sentiment" not in inspect.signature(G.evaluate).parameters
    import engine
    t1 = pd.Timestamp(DAY.replace(hour=10, minute=0))
    fake = {"v3": {"ok": True, "close1": 100.9, "t": t1, "atr5": 1.0, "levels": {}, "zone": 0.02, "buf": 0.02, "r1": None},
            "quote": {"last": 101.0, "spread": 0.01}, "bar_age_s": 5}
    plan = {"ticker": "NVDA", "side": "C", "state": "READY", "trigger_level": 100.0, "invalidation": 99.0, "setup": "ORB_BREAK",
            "trigger_rule": "1m close above 100", "exit": {"t1_level": 101.2, "t1_name": "PDH"},
            "catalyst": {"label": "confirmed", "sentiment": {"trader": "very bullish", "score": 0.99}}}
    g = G.for_plan(plan, fake)
    assert g["state"] in ("TOO EXTENDED", "WAIT FOR RETEST", "NO TRADE")
    monkeypatch.setattr(engine, "_build_plan", lambda *a, **k: dict(plan, objections=[], support=[], data={}, snap={}, session={"state": "OPEN"}))
    monkeypatch.setattr(engine, "snapshot", lambda t: fake)
    p = engine.build_plan("NVDA", "C")
    assert p["state"] != "READY" and p["assistant"]["state"] != "ENTRY CONDITIONS MET" and "entry gate" in p["reason"]


def test_a_qualified_retest_is_a_new_setup_with_its_own_risk(env):
    clock = env
    t1 = pd.Timestamp(DAY.replace(hour=10, minute=0))
    g = G.define("TSLA", "C", "orb_break", 100.0, 99.0, 104.0, "PDH", snap(100.2, 100.2, t1), "x", confirmed_at=t1.isoformat())
    clock.t = DAY.replace(hour=10, minute=2)
    G.evaluate(g, snap(101.2, 101.1, pd.Timestamp(DAY.replace(hour=10, minute=1))))
    missed = G._load(g["id"])
    assert missed["status"] == "MISSED"
    idx = pd.DatetimeIndex([DAY.replace(hour=10, minute=m) for m in range(2, 7)])
    r1 = pd.DataFrame({"Open": [101.0, 100.6, 100.2, 100.1, 100.2], "High": [101.1, 100.7, 100.3, 100.4, 100.6],
                       "Low": [100.6, 100.2, 100.05, 100.0, 100.15], "Close": [100.6, 100.2, 100.1, 100.2, 100.5], "Volume": 1000.0}, index=idx)
    clock.t = DAY.replace(hour=10, minute=7)
    new = G.retest_setup(missed, r1, snap(100.5, 100.5, idx[-1]))
    assert new and new["kind"] == "retest" and new["id"] != g["id"] and new["trigger"] == 100.6
    assert new["invalidation"] == pytest.approx(99.98) and new["rr_at_trigger"] is not None
    no = G.retest_setup(missed, r1.iloc[:2], snap(100.2, 100.2, idx[1]))                # no turn back up yet: no new setup
    assert no is None


# ================================================================ options hours and paper realism
def test_closed_options_market_never_gets_a_simulated_fill(env, monkeypatch):
    import optionhours
    import paper
    clock = env
    assert optionhours.session("SPY", DAY.replace(hour=16, minute=10))[0] is True        # late-close ETF class
    assert optionhours.session("NVDA", DAY.replace(hour=16, minute=10))[0] is False
    assert optionhours.session("NVDA", DAY.replace(hour=8, minute=0))[0] is False         # no extended-hours sim fills
    assert optionhours.session("NVDA", datetime(2026, 11, 27, 13, 5, tzinfo=ET))[0] is False   # half day
    assert optionhours.session("NVDA", datetime(2026, 11, 26, 11, 0, tzinfo=ET))[0] is False   # Thanksgiving
    called = []
    monkeypatch.setattr(marketdata, "option_quote", lambda s: (called.append(s), ({"bid": 1, "ask": 1.1, "executable": True}, None))[1])
    clock.t = DAY.replace(hour=17, minute=30)                                             # after-hours earnings move
    pid, why = paper.buy("earn_post", "x", "NVDA", "C", {"symbol": "NVDA261106C00140000", "label": "140C", "premium_stop": 0.8,
                                                         "stop_px": None, "t1": None, "t1_level": None, "t1_px": None,
                                                         "be_trigger": 1.2, "breakeven_net": 1.05}, 1, clock.t.isoformat())
    assert pid is None and "closed" in why and not called


def test_gap_exit_fills_at_the_real_bid_not_the_planned_stop(env, monkeypatch):
    """An overnight earnings gap through the 20% planned stop: the paper loss is the real (bigger) loss."""
    import paper
    clock = env
    q = {"bid": 2.00, "ask": 2.04, "executable": True, "age_s": 1}
    monkeypatch.setattr(marketdata, "option_quote", lambda s: (dict(q), None))
    clock.t = DAY.replace(hour=15, minute=0)
    plan = {"symbol": "NVDA261106C00140000", "label": "140C", "premium_stop": 1.64, "stop_px": None, "t1": None, "t1_level": None,
            "t1_px": None, "be_trigger": 2.3, "breakeven_net": 2.1}
    pid, _ = paper.buy("earn_pre", "gap", "NVDA", "C", plan, 1, clock.t.isoformat())
    p = store.pos_get(pid)
    q.update(bid=0.70, ask=0.76)                                                          # next morning, after the report
    clock.t = (DAY + timedelta(days=1)).replace(hour=9, minute=31)
    n, px = paper.sell(p, 1, "stop: premium below the planned 20% level at the open")
    p = store.pos_get(pid)
    assert n == 1 and px < plan["premium_stop"]
    loss_pct = (p["fill"] - px) / p["fill"]
    assert loss_pct > 0.5 and p["realized"] < -100                                       # not clipped to 20%


def test_emergency_pause_blocks_new_paper_entries(env, monkeypatch):
    import paper
    store.kv_set("paper_pause", {"at": "now", "by": "Nick"})
    pid, why = paper.buy("paper", "x", "SPY", "C", {"symbol": "SPY261028C00600000"}, 1, "t")
    assert pid is None and "paused" in why
