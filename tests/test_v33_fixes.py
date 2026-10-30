"""v3.3: regression tests for the defects found in the outside audit (A-H). Each fix lives in a new version; the legacy
behavior is kept only where a frozen ledger depends on it."""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import core
import engine
import entrygate
import fakes
import indicators as I
import marketdata
import paper
import store

ET = core.ET
DAY = datetime(2026, 10, 28, tzinfo=ET)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    engine._cache.clear()
    yield monkeypatch
    marketdata.use(None)


def _snap(px, c1, t, **kw):
    s = {"price": px, "close1": c1, "t": t, "atr5": 0.10 / 0.6, "spread": 0.01, "spread_pct": 0.01, "fresh": True, "bar_age_s": 5}
    s.update(kw)
    return s


# ---------------------------------------------------------------- A. both zone bounds, fail closed
def test_gate_requires_both_zone_bounds_for_calls_and_puts(db):
    clock = fakes.Clock(DAY.replace(hour=10, minute=0))
    db.setattr(core, "now_et", clock)
    g = entrygate.define("SPY", "C", "orb_break", 100.0, 99.50, 101.50, "PDH", _snap(100.05, 100.05, "t1"), "1m close > 100",
                         confirmed_at=clock().isoformat(), scope="test")
    assert g["zone"] == [100.0, 100.1] and g["latest_entry"] == 100.1
    assert entrygate.evaluate(g, _snap(100.05, 100.05, "t1"))["state"] == "ENTRY CONDITIONS MET"
    clock.t += timedelta(minutes=1)
    r = entrygate.evaluate(g, _snap(99.60, 99.62, "t2"))                      # the audit's case: below the trigger
    assert r["state"] == "WAIT FOR RETEST" and "back below the trigger" in r["rejected"]
    p = entrygate.define("SPY", "P", "orb_break", 100.0, 100.50, 98.50, "PDL", _snap(99.95, 99.95, "t1"), "1m close < 100",
                         confirmed_at=clock().isoformat(), scope="test")
    assert entrygate.evaluate(p, _snap(99.95, 99.95, "t1"))["state"] == "ENTRY CONDITIONS MET"
    assert entrygate.evaluate(p, _snap(100.40, 100.38, "t2"))["state"] == "WAIT FOR RETEST"   # mirrored


def test_gate_fails_closed_on_unknown_freshness_or_spread(db):
    clock = fakes.Clock(DAY.replace(hour=10, minute=0))
    db.setattr(core, "now_et", clock)
    g = entrygate.define("SPY", "C", "orb_break", 100.0, 99.50, 101.50, "PDH", _snap(100.05, 100.05, "t1"), "x",
                         confirmed_at=clock().isoformat(), scope="test2")
    s = _snap(100.05, 100.05, "t1")
    s.pop("fresh")
    assert entrygate.evaluate(g, s)["state"] == "NO TRADE" and "unknown" in entrygate.evaluate(g, s)["rejected"]
    assert "spread unknown" in entrygate.evaluate(g, _snap(100.05, 100.05, "t1", spread_pct=None))["rejected"]


def test_gate_state_never_leaks_between_scopes(db):
    clock = fakes.Clock(DAY.replace(hour=10, minute=0))
    db.setattr(core, "now_et", clock)
    a = entrygate.define("SPY", "C", "orb_break", 100.0, 99.5, 101.5, "PDH", _snap(100.05, 100.05, "t1"), "x", scope="gated")
    b = entrygate.define("SPY", "C", "orb_break", 100.0, 99.5, 101.5, "PDH", _snap(100.05, 100.05, "t1"), "x", scope="board")
    assert a["id"] != b["id"] and a["version"] == entrygate.VERSION


# ---------------------------------------------------------------- B. the gated ledger decides every candidate itself
def test_gated_ledger_decides_every_candidate_independently(db):
    import test_v3 as T
    clock, fk = fakes.install(db, T.vm_path, T.DAY, s0=600.0)
    T.run(clock, "09:31", "10:40")
    res = {r["id"][len("research-"):] for r in store.q("SELECT id, plan FROM candidates WHERE portfolio='research'")
           if r["plan"] and '"premium_limit"' in r["plan"]}
    gated = {r["id"][len("gated-"):] for r in store.q("SELECT id FROM candidates WHERE portfolio='gated'")}
    assert res and res <= gated, "every research candidate with a contract must get its own gated decision"
    assert "_mirror_gated(" not in open(core.HERE / "engine.py").read().split("def _mirror_gated")[0]


def test_each_ledger_counts_its_own_losing_streak(db):
    clock = fakes.Clock(DAY.replace(hour=11, minute=0))
    db.setattr(core, "now_et", clock)
    for i in range(3):
        store.pos_save({"id": f"R{i}", "ledger": "real", "date": "2026-10-28", "ticker": "SPY", "contract": "600C", "symbol": "SPY261028C00600000",
                        "side": "C", "qty_init": 1, "qty_open": 0, "fill": 2.0, "opened": f"2026-10-28T09:5{i}:00-04:00",
                        "closed": f"2026-10-28T09:5{i}:30-04:00", "status": "CLOSED", "setup_id": f"R{i}", "grade": "B", "setup": "X",
                        "plan": {}, "realized": -20.0, "mfe": 0, "mae": 0, "policy_version": "t", "verified": "t", "notes": ""})
    assert engine.discipline_gate("real", "A").startswith("STOP FOR TODAY")
    assert engine.discipline_gate("gated", "A") is None                     # Nick's losses don't stop the research ledger


# ---------------------------------------------------------------- C. features only after their bar has closed
def test_future_bars_never_change_earlier_features():
    import diagnostics
    idx = pd.date_range("2026-10-15 09:30", periods=180, freq="1min", tz=ET)
    c = 100 + np.cumsum(np.sin(np.arange(180) / 7.0) * 0.05)
    m1 = pd.DataFrame({"Open": c, "High": c + 0.02, "Low": c - 0.02, "Close": c, "Volume": 1000.0}, index=idx)
    a = diagnostics.day_frame(m1, idx[0].date())
    bumped = m1.copy()
    bumped.loc[pd.Timestamp("2026-10-15 11:31", tz=ET), "Close"] += 1.0          # the audit's SPY 11:31 bar
    b = diagnostics.day_frame(bumped, idx[0].date())
    t1130 = pd.Timestamp("2026-10-15 11:30", tz=ET)
    assert a.loc[t1130, "hist2"] == b.loc[t1130, "hist2"]                        # 11:30 can't know 11:31
    assert a.loc[pd.Timestamp("2026-10-15 11:31", tz=ET), "hist2"] != b.loc[pd.Timestamp("2026-10-15 11:31", tz=ET), "hist2"]
    la, lb = diagnostics.day_frame(m1, idx[0].date(), legacy=True), diagnostics.day_frame(bumped, idx[0].date(), legacy=True)
    assert la.loc[t1130, "hist2"] != lb.loc[t1130, "hist2"]                      # the old leak, kept only as legacy


# ---------------------------------------------------------------- D. theta units
def test_theta_is_per_calendar_day_everywhere():
    import optionmath
    import replay
    now = DAY.replace(hour=11, minute=0)
    px, d, g, th_min = replay.bs(600.0, 600.0, 0.18, "C", now)
    prov = replay.ReplayProvider({"SPY": fakes.make_market(lambda m: 600.0, DAY, prior_days=1)}, lambda: now, "csv")
    q = prov._q("SPY", "C", 600.0)
    assert q["theta"] == pytest.approx(round(th_min * 24 * 60, 4))
    v, label = optionmath.model_premium({"bid": 2.0, "delta": 0.5, "gamma": 0.0, "theta": -0.39}, 0.0, "C", hold_min=60)
    assert v == pytest.approx(2.0 - 0.39 * 60 / 390) and "theta over 60 min" in label


# ---------------------------------------------------------------- E. the stocks backtest fills after the signal
def test_inplay_backtest_v2_is_causal_and_fills_gaps_at_the_open():
    import scanner
    import test_v31 as V
    m1 = V._stock_m1(DAY, 140.0, lambda i, lv: lv * (1 + 0.001 * i) if i < 200 else lv * 0.9, open_vol=4.0)
    day = DAY.date()
    gap = pd.Timestamp(f"{day} 12:50", tz=ET)                                   # minute 200: the bar OPENS 10% lower (a gap)
    m1.loc[gap, "Open"] = m1.loc[gap, "Close"]
    m1.loc[gap, "High"] = m1.loc[gap, "Close"] + 0.02
    d = m1[m1.index.date < day].between_time("09:30", "15:59")
    daily = d.resample("1D").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
    daily.index = daily.index.tz_localize(None)
    extra = pd.DataFrame({k: daily[k].iloc[:1].values.repeat(20) for k in daily.columns}, index=pd.date_range(end=daily.index[0] - timedelta(days=1), periods=20))
    m5 = d.resample("5min").agg({"Volume": "sum"})
    base = {"NVDA": scanner.baseline(pd.concat([extra, daily]), m5, day)}
    r = scanner.backtest_day_v2(day, {"NVDA": m1}, base, {"NVDA": 0.5})
    assert r["trades"], r["rejected"]
    t = r["trades"][0]
    assert t["decision_at"] >= "09:45" and t["fill_at"] >= t["decision_at"]
    fill_bar = m1[m1.index == pd.Timestamp(f"{day} {t['fill_at']}", tz=ET)]
    assert t["entry_px"] == round(float(fill_bar["Open"].iloc[0]), 2)           # the next bar's open, not the signal close
    assert t["why"].startswith("stop gapped") and t["exit_px"] < t["stop"]       # the 10% drop gaps through the stop


# ---------------------------------------------------------------- F. strict paper fills
def test_strict_fill_checks_the_final_price_size_and_latency(db):
    clock, fk = fakes.install(db, lambda m: 600.0, DAY, s0=600.0)
    clock.t = DAY.replace(hour=10, minute=30, second=5)
    sym = "SPY261028C00600000"
    q = dict(fk.option_quote(sym)[0])
    plan = {"symbol": sym, "label": "600C", "premium_stop": 1.0, "stop_px": 599.0, "t1": "PDH", "t1_level": 602.0, "t1_px": None,
            "be_trigger": None, "breakeven_net": 2.1, "premium_limit": round(q["ask"] + 0.01, 2), "family": "X"}
    sig = DAY.replace(hour=10, minute=30).isoformat()
    pid, why = paper.buy("gated", "i1", "SPY", "C", dict(plan), 1, sig)
    assert pid, why                                                             # ask + 0.01 == limit: fills
    p = store.pos_get(pid)
    assert p["fill"] == pytest.approx(q["ask"] + 0.01) and p["plan"]["exec_model"].startswith("2026-10-30.exec2")
    assert p["plan"]["premium_stop"] >= core.cents_up(p["fill"] * 0.8)          # the 20% line from the actual fill
    pid2, why2 = paper.buy("gated", "i2", "SPY", "C", dict(plan, premium_limit=round(q["ask"], 2)), 1, sig)
    assert pid2 is None and "final fill" in why2                                # ask itself at the limit: slippage breaks it
    pid3, why3 = paper.buy("gated", "i3", "SPY", "C", dict(plan), 1, DAY.replace(hour=10, minute=30, second=5).isoformat())
    assert pid3 is None and "latency" in why3                                   # the quote predates signal + 1 s
    db.setattr(fk, "option_quote", lambda s: (dict(q, ask_size=0), None))
    marketdata._quotes.clear()
    pid4, why4 = paper.buy("gated", "i4", "SPY", "C", dict(plan), 1, sig)
    assert pid4 is None and "no size" in why4
    pid5, _ = paper.buy("research", "i5", "SPY", "C", dict(plan), 1, sig)       # legacy ledgers keep their recorded model
    assert pid5 and "exec1" in store.pos_get(pid5)["plan"]["exec_model"]


# ---------------------------------------------------------------- G. aggregate identity and completeness
def test_aggregate_cache_tracks_content_and_strict_completeness():
    I._agg_cache.clear()
    idx = pd.date_range("2026-10-27 09:30", periods=390, freq="1min", tz=ET).append(pd.date_range("2026-10-28 09:30", periods=60, freq="1min", tz=ET))
    c = np.full(len(idx), 100.0)
    a = pd.DataFrame({"Open": c, "High": c + 0.1, "Low": c - 0.1, "Close": c, "Volume": 10.0}, index=idx)
    b = a.copy()
    b.iloc[10, b.columns.get_loc("High")] = 105.0                             # same length, same last close, corrected bar
    ba, _ = I.aggregate_multi(a, 5)
    bb, _ = I.aggregate_multi(b, 5)
    assert ba["High"].max() == pytest.approx(100.1) and bb["High"].max() == pytest.approx(105.0)
    day = a[a.index.date == idx[-1].date()].drop(index=pd.Timestamp("2026-10-28 09:31", tz=ET))
    _, loose = I.aggregate(day, 5)
    _, strict = I.aggregate(day, 5, require_all=True)
    t0 = pd.Timestamp("2026-10-28 09:30", tz=ET)
    assert bool(loose[t0]) and not bool(strict[t0])                             # a missing minute is not a complete bar


# ---------------------------------------------------------------- H. honest evaluation
def test_eval2_uses_sessions_counts_every_win_and_splits_versions(db):
    import evaluation
    tr = [{"pnl": 0.5, "session": "d1"}, {"pnl": -0.5, "session": "d1"}, {"pnl": 0.0, "session": "d2"}, {"pnl": 30.0, "session": "d3"}]
    s = evaluation.stats_v2(tr, sessions=["d1", "d2", "d3", "d4"])
    assert s["wins"] == 2 and s["losses"] == 1 and s["flat"] == 1 and s["sessions"] == 4
    assert s["ci95_session"][0] <= s["expectancy"] <= s["ci95_session"][1] and s["small_sample"]
    assert evaluation.stats_v2([])["note"].startswith("no trades")
    for i, (ver, ex) in enumerate([("v1", None), ("v2", "2026-10-30.exec2")]):
        store.pos_save({"id": f"G{i}", "ledger": "gated", "date": "2026-10-28", "ticker": "SPY", "contract": "600C", "symbol": "S",
                        "side": "C", "qty_init": 1, "qty_open": 0, "fill": 2.0, "opened": "2026-10-28T10:00:00-04:00",
                        "closed": "2026-10-28T10:10:00-04:00", "status": "CLOSED", "setup_id": "x", "grade": "B", "setup": "X",
                        "plan": {"exec_model": ex} if ex else {}, "realized": 10.0, "mfe": 0, "mae": 0, "policy_version": ver,
                        "verified": "t", "notes": ""})
    v = evaluation.versioned("gated")
    assert len(v) == 2 and {x["policy_version"] for x in v} == {"v1", "v2"}
