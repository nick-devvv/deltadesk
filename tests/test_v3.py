"""v3 rebuild tests (no network, no AI). Synthetic markets via tests/fakes.py; every number flows through marketdata."""
import json
import math
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import core  # noqa: E402
import engine  # noqa: E402
import exits  # noqa: E402
import fakes  # noqa: E402
import indicators as I  # noqa: E402
import marketdata  # noqa: E402
import optionmath  # noqa: E402
import paper  # noqa: E402
import store  # noqa: E402
import strategy  # noqa: E402

ET = core.ET
DAY = datetime(2026, 10, 28, tzinfo=ET)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    engine._cache.clear()
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")   # never touch the real calendar
    yield monkeypatch
    marketdata.use(None)


def at(clock, hh, mm):
    clock.t = DAY.replace(hour=hh, minute=mm)
    engine._cache.clear()


def run(clock, start, end):
    t = DAY.replace(hour=int(start[:2]), minute=int(start[3:]))
    stop = DAY.replace(hour=int(end[:2]), minute=int(end[3:]))
    while t <= stop:
        clock.t = t
        engine._cache.clear()
        engine.tick()
        t += timedelta(minutes=1)


def vm_path(ts):
    """Chop around VWAP, a push up (MACD cross), a pullback that taps VWAP, then a trend leg."""
    m = ts.hour * 60 + ts.minute
    if m < 570:
        return 599.8
    if m < 630:
        return 599.8 + 0.25 * math.sin((m - 570) / 4.0)
    if m < 646:
        return 599.8 + (m - 630) * 0.07
    if m < 656:
        return 600.92 - (m - 646) * 0.10
    if m < 720:
        return 599.92 + (m - 656) * 0.035
    return 602.26 + 0.1 * math.sin(m / 3)


# ================================================================ indicators
def _bars(n=300, seed=3, freq="2min"):
    rng = np.random.default_rng(seed)
    c = 600 + np.cumsum(rng.normal(0, 0.3, n))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0, .3, n)
    l = np.minimum(o, c) - rng.uniform(0, .3, n)
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1e5},
                        index=pd.date_range("2026-10-28 09:30", periods=n, freq=freq, tz=ET))


def test_indicators_match_talib_after_warmup():
    talib = pytest.importorskip("talib")
    b = _bars()
    h, l, c = b["High"].values, b["Low"].values, b["Close"].values
    near = lambda a, z: np.nanmax(np.abs(np.asarray(a)[-100:] - np.asarray(z)[-100:]))
    assert near(I.atr(b), talib.ATR(h, l, c, 14)) < 1e-9
    x, p, m = I.adx_di(b)
    assert near(x, talib.ADX(h, l, c, 14)) < 1e-3 and near(p, talib.PLUS_DI(h, l, c, 14)) < 1e-4
    M, S, H = I.macd(b["Close"])
    M2, S2, H2 = talib.MACD(c, 12, 26, 9)
    assert near(M, M2) < 1e-5 and near(H, H2) < 1e-5
    assert np.isnan(I.atr(b).values[:14]).all()          # warm-up stays undefined, never zero


def test_macd_cross_event_vs_state_and_three_changes_need_four_samples():
    m = pd.Series([-1.0, -0.5, 0.2, 0.4, 0.6])
    s = pd.Series([0.0, 0.0, 0.0, 0.0, 0.0])
    assert I.macd_cross(m.iloc[:3], s.iloc[:3]) == "up"           # crossed on this bar
    assert I.macd_cross(m, s) is None and I.macd_state(m, s) == "bull"   # later bars: state, not a new event
    h = pd.Series([0.5, 0.4, 0.3, 0.2])
    assert I.hist_fading(h, "C") is True and I.hist_fading(h.iloc[1:], "C") is None   # 3 changes need 4 values
    assert I.hist_fading(pd.Series([0.5, 0.4, 0.45, 0.2]), "C") is False
    assert I.hist_fading(pd.Series([-0.5, -0.4, -0.3, -0.2]), "P") is True             # puts: histogram rising = fading bearish
    assert I.hist_fading(pd.Series([0.5, np.nan, 0.3, 0.2]), "C") is None


def test_session_vwap_resets_each_session_and_zero_volume_is_unavailable():
    a = pd.DataFrame({"Open": 10.0, "High": 11.0, "Low": 9.0, "Close": 10.0, "Volume": 100.0},
                     index=pd.date_range("2026-10-27 09:30", periods=3, freq="1min", tz=ET))
    b = pd.DataFrame({"Open": 20.0, "High": 21.0, "Low": 19.0, "Close": 20.0, "Volume": [0.0, 100.0, 100.0]},
                     index=pd.date_range("2026-10-28 09:30", periods=3, freq="1min", tz=ET))
    v = I.session_vwap(pd.concat([a, b]))
    assert v.iloc[2] == pytest.approx(10.0) and math.isnan(v.iloc[3]) and v.iloc[4] == pytest.approx(20.0)


def test_two_minute_bars_complete_and_rvol_ignores_unfinished_candle(env):
    clock, fk = fakes.install(env, vm_path, DAY, s0=600.0)
    m1 = fk.m1[fk.m1.index <= DAY.replace(hour=10, minute=3)]
    r = I.rth(m1)
    b2, done = I.aggregate(r, 2, r.index[-1])                     # newest 1m bar opened 10:03 -> 10:02 2m bar complete
    assert bool(done.iloc[-1])
    b2b, done_b = I.aggregate(r.iloc[:-1], 2, r.index[-2])
    assert not bool(done_b.iloc[-1])                               # 10:02 2m bar with only its first minute
    rv, n = I.rvol_at_time(m1, pd.Timestamp(DAY.replace(hour=10, minute=0)), 5)
    assert rv is None and n == 0                                  # 10:00-10:05 interval not finished yet
    rv, n = I.rvol_at_time(m1, pd.Timestamp(DAY.replace(hour=9, minute=55)), 5)
    assert rv is not None and n >= 5
    rv, n = I.rvol_at_time(m1, pd.Timestamp(DAY.replace(hour=9, minute=55)), 5, min_sessions=50)
    assert rv is None                                             # not enough matching history -> unavailable


# ================================================================ levels, labels, setups
def test_levels_have_sources_and_orb_is_developing_until_done(env):
    clock, fk = fakes.install(env, vm_path, DAY, s0=600.0)
    at(clock, 9, 40)
    s = engine.snapshot("SPY")["v3"]
    lv = s["levels"]
    assert "prior RTH" in lv["PDH"]["source"] and lv["PDH"]["value"] > lv["PDL"]["value"]
    assert lv["ORB_H"]["complete"] is False and "DEVELOPING" in lv["ORB_H"]["source"]
    assert "premarket" in lv["PMH"]["source"]
    assert lv["POC"]["source"].count("APPROXIMATE") == 1
    at(clock, 9, 50)
    assert engine.snapshot("SPY")["v3"]["levels"]["ORB_H"]["complete"] is True
    assert strategy.detect_orb(engine.snapshot("SPY")["v3"]) is not None


def test_no_trend_day_from_seven_cents_above_the_opening_range(env):
    def path(ts):
        m = ts.hour * 60 + ts.minute
        if m < 585:
            return 600.0 + 0.3 * math.sin(m)
        return 600.37 + 0.02 * math.sin(m)      # sits ~7 cents above the ORB high
    clock, fk = fakes.install(env, path, DAY, s0=600.0)
    at(clock, 10, 30)
    s = engine.snapshot("SPY")["v3"]
    assert s["regime"]["label"] != "trend up", s["regime"]
    assert s["regime"]["evidence"]["accepted_above_orb"] is False


def test_pdh_retest_requires_an_actual_touch_of_the_zone(env):
    clock, fk = fakes.install(env, vm_path, DAY, s0=600.0)
    at(clock, 11, 1)                                              # 10:55 5m bar just completed
    s = engine.snapshot("SPY")["v3"]
    pdh = s["levels"]["PDH"]["value"]
    b5 = s["b5"].copy()
    # fake history: an earlier close above PDH, then a green bar whose low stays well above the zone
    b5.iloc[-3, b5.columns.get_loc("Close")] = pdh + 1.0
    b5.iloc[-2, b5.columns.get_loc("Close")] = pdh + 0.9
    last = b5.index[-1]
    b5.loc[last, ["Open", "High", "Low", "Close"]] = [pdh + 0.8, pdh + 1.2, pdh + 0.6, pdh + 1.1]
    s2 = dict(s, b5=b5)
    assert not [c for c in strategy.detect_prior_day(s2) if c["family"] == "PDH_RETEST"]
    b5.loc[last, ["Open", "High", "Low", "Close"]] = [pdh + 0.3, pdh + 1.2, pdh + 0.01, pdh + 1.1]   # now it taps the zone
    got = [c for c in strategy.detect_prior_day(dict(s, b5=b5)) if c["family"] == "PDH_RETEST"]
    assert got and got[0]["evidence"]["touch_low"] <= pdh + s["zone"] and got[0]["invalidation"] < pdh


def test_conflicting_calls_and_puts_skip_the_bar_and_same_side_merges():
    c1 = {"family": "ORB_RETEST", "side": "C", "confirm_rule": "a", "level": 1, "invalidation": 0}
    c2 = {"family": "VWAP_RECLAIM", "side": "C", "confirm_rule": "b", "level": 1, "invalidation": 0}
    p1 = {"family": "FAILED_BREAK", "side": "P", "confirm_rule": "c", "level": 1, "invalidation": 2}
    ideas, skipped = strategy.arbitrate([c2, c1, p1])
    assert ideas == [] and "both fired" in skipped["reason"] and len(skipped["candidates"]) == 3
    ideas, skipped = strategy.arbitrate([c2, c1])
    assert skipped is None and len(ideas) == 1 and ideas[0]["family"] == "ORB_RETEST" and ideas[0]["tags"] == ["ORB_RETEST", "VWAP_RECLAIM"]


def test_idea_reservation_is_atomic_and_the_four_cap_holds_under_threads(env):
    clock = fakes.Clock(DAY.replace(hour=10))
    env.setattr(core, "now_et", clock)
    ok, why = paper.reserve_idea("paper", "I1", "SPY", "C", 4)
    assert ok and not paper.reserve_idea("paper", "I1", "SPY", "C", 4)[0]      # duplicate detector / retry / restart
    res = []
    th = [threading.Thread(target=lambda i=i: res.append(paper.reserve_idea("paper", f"T{i}", "SPY", "C", 4)[0])) for i in range(10)]
    [t.start() for t in th]
    [t.join() for t in th]
    assert sum(res) == 3 and paper.ideas_today("paper") == 4
    assert paper.reserve_idea("research", "T9", "SPY", "C", None)[0]          # research is a separate ledger


# ================================================================ option math (units, ceiling, 2:1, size)
def _snap_for_math():
    return {"close1": 600.0, "atr5": 1.0, "zone": 0.10,
            "levels": {"PDH": {"value": 603.0}, "VWAP": {"value": 599.5}, "ORB_H": {"value": 600.05}}}


def test_option_math_keeps_units_apart_and_enforces_ceiling_and_two_to_one():
    snap = _snap_for_math()
    idea = {"side": "C", "invalidation": 599.0}
    rows = [{"symbol": "SPY261028C00600000", "strike": 600, "bid": 2.00, "ask": 2.04, "delta": 0.45, "gamma": 0.05, "theta": -0.3}]
    tp, why, diag = optionmath.plan_trade(idea, snap, rows, "A", None)
    assert tp is None and "20% ceiling" in why                        # 1.0 underlying risk x 0.45 delta > 20% of $2.04
    idea = {"side": "C", "invalidation": 599.6}
    tp, why, diag = optionmath.plan_trade(idea, snap, rows, "A", None)
    assert tp and tp["t1"] == "PDH" and tp["rr_underlying"] >= 2 and tp["rr_option"] >= 2
    assert tp["loss_per_contract"] <= tp["ceiling_per_contract"] and tp["qty"] == 2
    assert tp["rr_underlying"] == round((603.0 - 0.10 - 600.0) / (600.0 - 599.6), 2)    # underlying units only
    tp2, _, _ = optionmath.plan_trade(idea, snap, rows, "A", budget_left=tp["loss_per_contract"] * 1.5)
    assert tp2["qty"] == 1                                            # floor(budget / stressed loss)
    tp3, _, _ = optionmath.plan_trade(idea, snap, rows, "A", budget_left=1.0)
    assert tp3["qty"] == 0                                            # zero affordable contracts = no trade
    tp4, why4, _ = optionmath.plan_trade(idea, dict(snap, levels={"ORB_H": {"value": 600.3}}), rows, "A", None)
    assert tp4 is None and "need 2.0R" in why4                       # no credible room -> skip (never invent a target)


def test_missing_delta_is_unverified_and_excluded():
    snap = _snap_for_math()
    rows = [{"symbol": "SPY261028C00600000", "strike": 600, "bid": 2.00, "ask": 2.04, "delta": None}]
    tp, why, diag = optionmath.plan_trade({"side": "C", "invalidation": 599.6}, snap, rows, "A", None)
    assert tp is None and "known delta" in why


# ================================================================ exits
def setpx(fk, clock, px):
    """From the current minute onward the fake market trades flat at px (next tick sees it)."""
    i = fk.m1.index >= pd.Timestamp(clock())
    fk.m1.loc[i, "Open"] = px
    fk.m1.loc[i, "Close"] = px
    fk.m1.loc[i, "High"] = px + 0.03
    fk.m1.loc[i, "Low"] = px - 0.03


def _open_paper(clock, fk, qty=2, side="C", stop_px=599.0, t1_px=603.0, t1_level=603.1):
    plan = {"symbol": f"SPY261028{side}00600000", "label": f"600{side}", "premium_stop": 1.64, "stop_px": stop_px, "t1": "PDH",
            "t1_level": t1_level, "t1_px": t1_px, "be_trigger": 2.27, "breakeven_net": 2.07, "family": "TEST",
            "premium_limit": 3.0, "flat_by": "23:59"}
    paper.reserve_idea("paper", "X", "SPY", side)
    pid, why = paper.buy("paper", "X", "SPY", side, plan, qty, clock().isoformat())
    assert pid, why
    return pid


def test_never_invents_a_fill_during_a_quote_outage(env):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    at(clock, 10, 0)
    pid = _open_paper(clock, fk)
    fk.broken = True
    at(clock, 15, 26)                                                # all-out time with no quote
    p = store.pos_get(pid)
    exits.evaluate(p, engine.snapshot("SPY")["v3"])
    assert store.pos_get(pid)["status"] == "OPEN"
    assert store.q("SELECT COUNT(*) n FROM events WHERE text LIKE '%EXIT PENDING%' OR text LIKE '%no executable option quote%'")[0]["n"] >= 1
    fk.broken = False
    exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
    assert store.pos_get(pid)["status"] == "CLOSED"                  # filled once a valid quote exists


def test_green_stall_exit_after_ten_minutes_and_stale_quotes_never_count(env):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    env.setattr(exits.I, "hist_fading", lambda h, side: False)      # isolate the stall rule (momentum tested separately)
    env.setattr(exits.I, "macd_cross", lambda m, s: None)
    at(clock, 10, 0)
    pid = _open_paper(clock, fk, qty=1)
    setpx(fk, clock, 600.7)                                              # goes green (premium up), then flat
    for mm in range(1, 9):
        at(clock, 10, mm)
        assert not exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
    fk.stale = True                                                  # stale quotes: no stall decision, no fill
    at(clock, 10, 14)
    assert not exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
    fk.stale = False
    at(clock, 10, 15)                                              # next poll brings a fresh quote
    acts = exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
    assert acts and "STALL EXIT" in acts[0][2] and store.pos_get(pid)["status"] == "CLOSED"


def test_losing_trade_gets_no_extra_time_and_structure_stop_wins_precedence(env):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    at(clock, 10, 0)
    pid = _open_paper(clock, fk, qty=1, stop_px=599.5)
    p = store.pos_get(pid)
    p["plan"]["flat_by"] = "10:05"
    store.pos_save(p)
    setpx(fk, clock, 599.9)                                              # slightly red, never green
    at(clock, 10, 5)
    acts = exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
    assert acts and "IF FLAT" in acts[0][2]
    # precedence: session liquidation beats everything else
    store.x("DELETE FROM ideas")
    at(clock, 10, 10)
    pid3 = _open_paper(clock, fk, qty=1, stop_px=599.95)
    setpx(fk, clock, 599.0)                                              # structure broken AND it is all-out time
    at(clock, 15, 25)
    acts = exits.evaluate(store.pos_get(pid3), engine.snapshot("SPY")["v3"])
    assert acts and acts[0][2].startswith("ALL OUT")


def test_momentum_exit_fires_while_green_on_a_fading_histogram(env):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    at(clock, 10, 0)
    pid = _open_paper(clock, fk, qty=1)
    setpx(fk, clock, 600.7)                                          # jump green, then flat: 2m histogram fades
    acts = []
    for mm in range(1, 12):
        at(clock, 10, mm)
        acts = exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
        if acts:
            break
    assert acts and "MOMENTUM EXIT" in acts[0][2] and store.pos_get(pid)["realized"] > 0


def test_t1_partial_vs_one_contract(env):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    env.setattr(exits.I, "hist_fading", lambda h, side: False)
    env.setattr(exits.I, "macd_cross", lambda m, s: None)
    at(clock, 10, 0)
    pid = _open_paper(clock, fk, qty=2, t1_px=600.5, t1_level=600.6)
    setpx(fk, clock, 600.55)                                             # reaches T1 but no clean break
    at(clock, 10, 3)
    acts = exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
    assert acts and "sell 1 of 2" in acts[0][2] and store.pos_get(pid)["qty_open"] == 1
    at(clock, 10, 4)
    acts = exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
    assert acts and "close the rest" in acts[0][2] and store.pos_get(pid)["status"] == "CLOSED"
    store.x("DELETE FROM ideas")
    setpx(fk, clock, 600.0)
    at(clock, 10, 10)
    pid1 = _open_paper(clock, fk, qty=1, t1_px=600.5, t1_level=600.6)
    setpx(fk, clock, 600.55)
    at(clock, 10, 13)
    acts = exits.evaluate(store.pos_get(pid1), engine.snapshot("SPY")["v3"])
    assert acts and "full exit (1 contract)" in acts[0][2]


def test_stops_only_ratchet_toward_protection_and_widening_is_refused(env):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    at(clock, 10, 0)
    pid = _open_paper(clock, fk, qty=1)
    p = store.pos_get(pid)
    assert exits._ratchet(p, 1.50, "test lower") is False and p["plan"]["premium_stop"] == 1.64
    assert exits._ratchet(p, 1.90, "test higher") is True and p["plan"]["stops"][-1]["prev"] == 1.64
    import commands
    commands.handle("IN SPY 600C 1 at 2.00", "SPY")
    real = store.positions(ledger="real", status="OPEN")[0]
    floor = real["plan"]["ceiling_stop"]                               # the 20% max planned loss on the fill
    assert 1.60 <= floor <= 1.66
    r = commands.handle("STOP 1.80", "SPY")
    assert "recorded" in r["reply"]                                    # tightening is accepted
    r = commands.handle("STOP 1.70", "SPY")
    assert "REFUSED" in r["reply"]                                     # widening needs 'force'
    r = commands.handle("STOP 1.70 force", "SPY")
    assert "WIDENED" in r["reply"]                                     # recorded as a rule break, still inside 20%
    r = commands.handle("STOP 1.40 force", "SPY")
    assert "20% max planned loss" in r["reply"]                        # never past the 20% cap, even when forced
    real = store.positions(ledger="real", status="OPEN")[0]
    assert real["plan"]["premium_stop"] == 1.70 and real["plan"]["reported_stop"] == 1.40
    assert real["plan"]["stops"][-1]["by"] == "Nick (reported)"


# ================================================================ data pipeline
def test_fallback_data_is_labeled_and_never_fills(env):
    clock = fakes.Clock(DAY.replace(hour=10))
    env.setattr(core, "now_et", clock)

    class FB(marketdata.Fallback):
        def option_quote(self, s):
            return {"bid": 1.0, "ask": 1.05, "quote_time": pd.Timestamp(clock()), "src": "Alpaca indicative (delayed)"}, None
    marketdata.use(FB())
    q, _ = marketdata.option_quote("SPY261028C00600000")
    assert q["executable"] is False and "FALLBACK" in q["provider"]
    pid, why = paper.buy("paper", "F1", "SPY", "C", {"symbol": "SPY261028C00600000", "label": "600C"}, 1, clock().isoformat())
    assert pid is None and "not executable" in why


def test_stream_messages_merge_incrementally_and_bars_replace_not_double(env):
    import schwab_stream
    clock = fakes.Clock(DAY.replace(hour=10, minute=0, second=30))
    env.setattr(core, "now_et", clock)
    marketdata.use(marketdata.Provider())
    ms = int(pd.Timestamp(DAY.replace(hour=9, minute=59)).timestamp() * 1000)
    schwab_stream.handle({"data": [{"service": "LEVELONE_EQUITIES", "content": [{"key": "SPY", "1": 600.1, "2": 600.12, "3": 600.11, "34": ms}]}]})
    schwab_stream.handle({"data": [{"service": "LEVELONE_EQUITIES", "content": [{"key": "SPY", "3": 600.15}]}]})   # only last changed
    with marketdata._lock:
        q = dict(marketdata._quotes["SPY"])
    assert q["bid"] == 600.1 and q["ask"] == 600.12 and q["last"] == 600.15     # omitted fields stay, never zero
    bar = {"key": "SPY", "1": 5, "2": 600.0, "3": 600.2, "4": 599.9, "5": 600.1, "6": 1000, "7": ms, "8": 0}
    schwab_stream.handle({"data": [{"service": "CHART_EQUITY", "content": [bar]}]})
    schwab_stream.handle({"data": [{"service": "CHART_EQUITY", "content": [dict(bar, **{"6": 1200, "5": 600.15})]}]})  # correction
    df, forming, meta = marketdata.bars("SPY", refresh=False)
    assert len(df) == 1 and df["Volume"].iloc[0] == 1200 and df["Close"].iloc[0] == 600.15
    schwab_stream.handle({"data": [{"service": "LEVELONE_OPTIONS", "content": [{"key": "SPY   261028C00600000", "2": 1.1, "3": 1.14, "28": 0.47, "38": ms}]}]})
    with marketdata._lock:
        assert marketdata._quotes["SPY261028C00600000"]["delta"] == 0.47
    assert schwab_stream.stream_symbol("SPY261028C00600000") == "SPY   261028C00600000"


def test_schwab_allows_only_market_data_and_the_streamer_preferences_call(monkeypatch, tmp_path):
    import schwab
    monkeypatch.setenv("SCHWAB_APP_KEY", "k")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "s")
    monkeypatch.setattr(schwab, "TOKEN_FILE", tmp_path / "t.json")
    for bad in ("/trader/v1/accounts", "/trader/v1/accounts/123/orders", "/trader/v1/userPreference/x"):
        with pytest.raises(RuntimeError):
            schwab._get(bad, {})
    assert schwab._get("/trader/v1/userPreference", {}) == (None, "Schwab not connected")   # allowed path, no token yet


def test_early_close_deadline_and_eastern_time():
    s = core.session_info(datetime(2026, 11, 27, 12, 55, tzinfo=ET))
    assert s["early_close"] and s["all_out"] == "12:50" and s["state"] == "ALL OUT"
    s = core.session_info(datetime(2026, 11, 2, 15, 26, tzinfo=ET))     # after the DST change: still Eastern wall time
    assert s["state"] == "ALL OUT"


# ================================================================ strategy flow end to end
def test_vwap_macd_one_strategy_retest_entry_full_plan_and_no_duplicates(env):
    import entrygate
    env.setattr(entrygate, "cfg", lambda: dict(entrygate.DEFAULTS, zone_atr5=3.0, min_rr=2.0))   # this test is about the v3 flow, not the gate
    clock, fk = fakes.install(env, vm_path, DAY, s0=600.0)
    run(clock, "09:31", "10:20")
    c = store.q("SELECT * FROM candidates WHERE family='VWAP_MACD' AND portfolio='paper' AND decision='ORDER'")
    assert c, store.q("SELECT decision_t, family, portfolio, decision, reasons FROM candidates")
    plan = json.loads(c[0]["plan"])
    assert plan["entry_mode"] in ("VWAP retest", "early: strong trend") and plan["rr_option"] >= 2 and plan["rr_underlying"] >= 2
    assert plan["loss_per_contract"] <= plan["ceiling_per_contract"]
    ideas = store.q("SELECT idea FROM ideas WHERE portfolio='paper' AND status='FILLED'")
    assert len(ideas) == len({i["idea"] for i in ideas})
    pos = store.positions(ledger="paper")
    assert all(p["verified"].startswith("sim fill") for p in pos)
    assert store.q("SELECT COUNT(*) n FROM events WHERE kind='chart'")[0]["n"] == 0            # no AI in the loop
    alerts = [e["text"] for e in store.q("SELECT text FROM events WHERE kind='alert'")]
    assert any("STOP:" in a and "T1" in a and "R/R" in a for a in alerts)
    armed = [e["text"] for e in store.q("SELECT text FROM events WHERE text LIKE 'VWAP+MACD%ARMED%'")]
    assert armed and not any("VWAP_MACD" in e["text"] and "early" in e["text"] and "retest" in e["text"]
                             for e in store.q("SELECT text FROM events WHERE kind='opportunity'"))


def test_strong_trend_offers_early_entry_but_one_idea_per_arming(env):
    clock, fk = fakes.install(env, vm_path, DAY, s0=600.0)
    at(clock, 10, 39)
    s = engine.snapshot("SPY")["v3"]
    cands = [c for c in strategy.detect_vwap_macd(s)]
    again = strategy.detect_vwap_macd(s)                              # same bar asked twice (plan request): same answer
    assert cands == again
    for c in cands:
        assert c["entry_mode"] in ("early: strong trend", "VWAP retest") and c.get("idea_hint")


def test_research_keeps_observing_after_the_main_streak_stop(env):
    clock, fk = fakes.install(env, vm_path, DAY, s0=600.0)
    at(clock, 9, 35)
    for i in range(3):                                                # three main-paper losses today
        store.pos_save({"id": f"L{i}", "ledger": "paper", "date": "2026-10-28", "ticker": "SPY", "contract": "600C",
                        "symbol": "SPY261028C00600000", "side": "C", "qty_init": 1, "qty_open": 0, "fill": 2.0, "opened": f"2026-10-28T09:3{i}:00-04:00",
                        "closed": f"2026-10-28T09:3{i}:30-04:00", "status": "CLOSED", "setup_id": f"L{i}", "grade": "B", "setup": "X",
                        "plan": {}, "realized": -20.0, "mfe": 0, "mae": 0, "policy_version": "t", "verified": "t", "notes": ""})
    assert engine.discipline_gate("paper", "A").startswith("STOP FOR TODAY")
    run(clock, "09:40", "10:20")
    main = store.q("SELECT decision, limit_blocked FROM candidates WHERE portfolio='paper' AND decision IN ('ORDER','BLOCKED-LIMIT')")
    res = store.q("SELECT decision FROM candidates WHERE portfolio='research' AND decision='ORDER'")
    assert not [m for m in main if m["decision"] == "ORDER"]
    assert any("STOP FOR TODAY" in (m["limit_blocked"] or "") for m in main)
    assert res                                                         # research still took the setup in its own ledger
    assert not store.positions(ledger="paper", status="OPEN")


def test_chart_feed_matches_the_decision_snapshot(env):
    import chartfeed
    clock, fk = fakes.install(env, vm_path, DAY, s0=600.0)
    at(clock, 10, 30)
    d = chartfeed.build("SPY", 2)
    s = engine.snapshot("SPY")["v3"]
    assert d["decision"]["macd"] == pytest.approx(I.last(s["macd"])) and d["decision"]["last_final_close"] == s["close1"]
    assert d["candles"] and isinstance(d["candles"][0]["time"], int) and d["candles"][0]["time"] < 2_000_000_000   # unix seconds
    assert d["macd"][-1]["value"] == pytest.approx(round(I.last(s["macd"]), 4))
    assert {l["name"] for l in d["levels"]} >= {"PDH", "ORB_H", "VWAP"}


def test_kronos_has_no_trading_path():
    src = (ROOT / "kronos_shadow.py").read_text()
    for bad in ("import broker", "import paper", "import exits", "submit(", "reserve_idea"):
        assert bad not in src


def test_kronos_forecasts_are_tagged_by_data_source_and_use_the_schwab_archive(env):
    import kronos_shadow as ks
    clock = fakes.Clock(DAY.replace(hour=10, minute=50))
    env.setattr(core, "now_et", clock)
    store.x("CREATE TABLE IF NOT EXISTS forecasts(id TEXT PRIMARY KEY, ticker TEXT, made_at TEXT, bar_ts TEXT, horizon INTEGER, "
            "target_ts TEXT, base REAL, pred REAL, pred_mom REAL, actual REAL, model TEXT, runtime_ms INTEGER)")   # a pre-v3 table
    store.x("INSERT INTO forecasts VALUES('old-1','SPY','t','2026-10-27T10:00:00-04:00',5,'x',600,601,600.5,600.8,'m',1)")
    ks.migrate()
    m = ks.metrics()
    assert m["sources"] == {ks.PRE_V3: 1}                         # old rows stay labeled as pre-migration
    # an archive with < 5 sessions -> Yahoo (tagged); with enough Schwab history -> the archive, complete 5m bars only
    env.setattr(ks, "LOOKBACK", 20)
    idx = pd.date_range(DAY.replace(hour=9, minute=30), DAY.replace(hour=10, minute=48), freq="1min")
    for i, ts in enumerate(idx):
        store.x("INSERT INTO bars_archive(ticker,open,o,h,l,c,v,src) VALUES(?,?,?,?,?,?,?,?)",
                ("SPY", ts.isoformat(), 600 + i * .01, 600.1 + i * .01, 599.9 + i * .01, 600 + i * .01, 1000, "Schwab stream"))
    bars, src = ks.rth_5m("SPY")
    assert src == ks.SCHWAB and bars.index[-1].strftime("%H:%M") == "10:40"    # 10:45 bar has only 4 minutes: left out
    assert bars["Volume"].iloc[0] == 5000


def test_forward_evaluation_uses_the_predefined_criteria(env):
    import evaluation
    clock = fakes.Clock(datetime(2026, 11, 2, 17, 0, tzinfo=ET))
    env.setattr(core, "now_et", clock)
    r = evaluation.report()
    assert r["config"]["min_sessions"] == 10 and r["verdict"].startswith("running: 0 of 10")
    for i in range(3):
        store.pos_save({"id": f"PA-E{i}", "ledger": "paper", "date": "2026-11-02", "ticker": "SPY", "contract": "600C",
                        "symbol": "SPY261102C00600000", "side": "C", "qty_init": 1, "qty_open": 0, "fill": 2.0,
                        "opened": "2026-11-02T10:00:00-05:00", "closed": "2026-11-02T15:40:00-05:00" if i == 0 else "2026-11-02T10:20:00-05:00",
                        "status": "CLOSED", "setup_id": "E" if i < 2 else "F", "grade": "B", "setup": "X", "plan": {}, "realized": [30.0, -12.0, 5.0][i],
                        "mfe": 0, "mae": 0, "policy_version": core.policy()["version"], "verified": "sim fill on Schwab stream", "notes": ""})
    r = evaluation.report()
    m = r["ledgers"]["paper"]
    assert m["n"] == 3 and m["net"] == 23.0 and m["ci95"][0] <= m["expectancy"] <= m["ci95"][1]
    assert any("has 2 positions" in v for v in r["violations"]) and any("after all out" in v for v in r["violations"])
