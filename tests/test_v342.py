"""v3.4.2: each strategy's own exits in the lab, the 10-day minimum, the contract lab (12 contracts per live signal on
real quotes), best/worst prices on old-rules trades. Offline."""
import json
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import contract_lab as CL
import core
import lab
import matched_benchmarks as MB
import scanner_setups as SS
import store
import test_v31 as V
from test_v33 import world, _board_at  # noqa: F401
from test_v34 import _run, _reset_lab, _tape_row, lw  # noqa: F401

ET = core.ET


def _day(prices, start="2026-10-28 09:30"):
    idx = pd.date_range(start, periods=len(prices), freq="1min", tz=ET)
    c = np.array(prices, float)
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"Open": o, "High": np.maximum(o, c) + 0.02, "Low": np.minimum(o, c) - 0.02, "Close": c}, index=idx)


def test_own_exits_wait_for_a_close_and_fill_at_the_next_open():
    px = [100.0] * 20 + [100.2] * 5 + [99.0] + [98.0] + [99.5] * 40
    df = _day(px)
    a = MB.arrays(df)
    df.iloc[22, df.columns.get_loc("Low")] = 98.5                 # a wick through the stop, but the bar closes above it
    a = MB.arrays(df)
    o = MB.outcome_close_arrays(a, 21, "C", 1.0, target_r=2.0, cost_per_share=0.0)
    assert o["why"] == "stop (close)" and o["exit_i"] == 26              # the 99.0 close at bar 25, filled at bar 26's open
    assert o["r"] == pytest.approx((99.0 - 100.2) / 1.0)                # the gap past the stop is a real loss beyond -1R
    t = MB.outcome_close_arrays(a, 21, "C", 0.05, target_r=2.0, cost_per_share=0.0)
    assert t["why"] == "stop (close)"                                    # tiny risk: the same close stops it
    up = _day([100.0] * 10 + [100.5] * 3 + [101.5] * 10)
    u = MB.outcome_close_arrays(MB.arrays(up), 5, "C", 0.5, target_r=2.0, cost_per_share=0.0)
    assert u["why"] == "target (close)" and u["r"] > 2.0
    k = MB.outcome_close_arrays(a, 21, "C", 1.0, checks={30: (99.6, False)}, cost_per_share=0.0)
    assert k["why"] == "stop (check)" and k["exit_i"] == 31
    f = MB.outcome_close_arrays(a, 21, "C", 1.0, checks={24: (None, True)}, cost_per_share=0.0)
    assert f["why"] == "signal flipped"
    assert MB.outcome_close_arrays(a, 21, "C", 1.0, checks={}, cost_per_share=0.0) is None   # no bars to the flat time: unknown


def test_tape_scores_each_strategy_by_its_own_exits_too(lw):
    clock, f, prov = lw
    sigs, now, c = _run(lw, 10, 40)
    clock.t = V.DAY.replace(hour=15, minute=59, second=30)
    SS._state["bars"] = {t: (time.time(), f.m1_today(t, clock().date())) for t in f.m1s}
    lab.resolve(str(now.date()), clock(), c)
    done = store.q("SELECT family, r, r_own, own_why, ctl_own, exit_at, exit_own_at FROM lab_tape WHERE status='DONE'")
    assert done and all(r["exit_at"] for r in done if r["r"] is not None)
    own = [r for r in done if r["r_own"] is not None]
    assert own and all(r["ctl_own"] is not None for r in own)
    assert all(r["own_why"] in ("stop (close)", "target (close)", "time", "stop (check)", "signal flipped", "no path") for r in own)
    noise = [r for r in done if r["family"] == "noise" and r["r_own"] is not None]
    assert noise and all(r["own_why"] in ("stop (check)", "signal flipped", "time") for r in noise)   # no 2R target for noise
    w = lab.what_works("strategy", exits="own")
    assert w["exits"] == "own" and "OWN exits" in w["note"]


def test_one_busy_day_is_still_too_few(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "d.db")
    monkeypatch.setattr(store, "_conn", None)
    lab._schema()
    for i in range(120):                                             # 120 signals, all on one day
        _tape_row(i, "board_vwap_reject", "NVDA", "2026-10-30", 0.3, 0.1, {"group": "Semiconductors"})
    row = lab.what_works("strategy")["rows"][0]
    assert row["n"] == 120 and row["sessions"] == 1 and row["too_few"] and not row.get("both_halves")
    assert lab.what_works("strategy", min_days=1)["rows"][0]["too_few"] is False


def test_old_databases_get_the_new_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "d.db")
    monkeypatch.setattr(store, "_conn", None)
    store.x("CREATE TABLE lab_tape(id TEXT PRIMARY KEY, day TEXT, ticker TEXT, family TEXT, setup TEXT, side TEXT, signal_bar TEXT, "
            "bar_end TEXT, observed_at TEXT, live INTEGER, level REAL, invalidation REAL, use_level INTEGER, price REAL, atr REAL, "
            "conditions TEXT, status TEXT, entry REAL, stop_dist REAL, r REAL, r_5m REAL, r_15m REAL, r_30m REAL, exit_why TEXT, "
            "ctl_r REAL, ctl_n INTEGER, resolved_at TEXT, paper TEXT, version TEXT)")
    lab._schema()
    cols = {r["name"] for r in store.q("PRAGMA table_info(lab_tape)")}
    assert {"r_own", "own_why", "ctl_own", "exit_at", "exit_own_at"} <= cols


def _chain(now, spot=140.0):
    rows = []
    for dte in (0, 1, 3, 4, 7, 9, 14):
        exp = (now.date() + timedelta(days=dte)).isoformat()
        for k in range(-6, 7):
            strike = spot + k
            d = max(0.05, min(0.95, 0.5 - k * (0.11 if dte == 0 else 0.07 if dte <= 2 else 0.05)))
            mid = max(0.05, (spot - strike) * (d > 0.5) + 0.6 * (1 + dte) ** 0.5 * d * 2)
            rows.append({"symbol": f"NVDA{exp.replace('-', '')[2:]}C{int(strike * 1000):08d}", "exp": exp, "strike": strike,
                         "bid": round(mid - 0.02, 2), "ask": round(mid + 0.02, 2), "delta": round(d, 3), "ts": now.isoformat()})
    return rows


def test_contract_picks_cover_expiry_and_delta_with_reasons():
    now = datetime(2026, 10, 28, 10, 40, 5, tzinfo=ET)
    rows = _chain(now)
    picks = CL.pick(rows, "C", now.date(), now)
    assert len(picks) == 12
    got = {(b, tg): r for b, tg, r, why in picks}
    for b, lo, hi in CL.BUCKETS:
        for tg in CL.DELTAS:
            r = got[(b, tg)]
            assert r is not None and lo <= r["dte"] <= hi and abs(abs(r["delta"]) - tg) <= 0.10
    assert got[("3-5 days", 0.45)]["dte"] == 3                            # the nearest expiry inside the bucket
    stale = [dict(r, ts=(now - timedelta(minutes=5)).isoformat()) if r["exp"] == now.date().isoformat() else r for r in rows]
    p2 = {(b, tg): (r, why) for b, tg, r, why in CL.pick(stale, "C", now.date(), now)}
    assert p2[("0DTE", 0.45)][0] is None and "fresh" in p2[("0DTE", 0.45)][1]   # stale quotes are never used


class _Fetch:
    def __init__(self, rows):
        self.rows, self.calls = rows, 0

    def chain(self, t, side, first, through, strikes):
        self.calls += 1
        return self.rows, None


def test_contracts_are_followed_and_scored_at_the_stock_exit(tmp_path, monkeypatch):
    import marketdata
    monkeypatch.setattr(store, "DB", tmp_path / "d.db")
    monkeypatch.setattr(store, "_conn", None)
    CL._state.update(tokens=0.0, t=None, tracked=None, last_sample={}, recent={})
    now = datetime(2026, 10, 28, 10, 40, 5, tzinfo=ET)
    monkeypatch.setattr(core, "now_et", lambda: now)
    rows = _chain(now)
    lab._schema()
    _tape_row(1, "board_orb_break", "NVDA", "2026-10-28", 1.5, 0.1, {"group": "Semiconductors"})
    sig = {"id": "x1", "ticker": "NVDA", "side": "C", "family": "board_orb_break"}
    f = _Fetch(rows)
    assert CL.start(sig, now, f) == 12 and f.calls == 1
    assert "same stock" in CL.start(dict(sig, id="x2"), now, f)          # no double-following of one move
    q = {r["symbol"]: r for r in rows}

    clk = {"t": now}

    def quotes(syms, max_age_s=5):                      # v3.5: real quotes carry the provider time and the receipt time
        return {s: {"bid": bids.get(s, q[s]["bid"]), "ask": q[s]["ask"], "executable": True,
                    "quote_time": pd.Timestamp(clk["t"]), "recv": pd.Timestamp(clk["t"])} for s in syms}, None
    monkeypatch.setattr(marketdata, "option_quotes", quotes)
    tracked = store.q("SELECT * FROM lab_contracts WHERE status='TRACKING'")
    zero = next(r for r in tracked if r["bucket"] == "0DTE" and r["target_delta"] == 0.45)
    week = next(r for r in tracked if r["bucket"] == "6-10 days" and r["target_delta"] == 0.45)
    bids = {zero["symbol"]: round(zero["line"] - 0.01, 2)}                 # 0DTE dips through its 20% line
    CL._state["last_sample"] = {}
    CL.poll(now)
    bids = {zero["symbol"]: zero["bid0"] + 0.30, week["symbol"]: week["bid0"] + 0.40}   # then both recover and gain
    later = now + timedelta(minutes=12)
    CL._state["last_sample"] = {}
    clk["t"] = later
    CL.poll(later)
    store.x("UPDATE lab_tape SET status='DONE', exit_at=? WHERE id='x1'", ((later - timedelta(seconds=30)).isoformat(),))
    CL.poll(later.replace(hour=15, minute=27))                          # stops following after 3:26 PM
    assert CL.resolve("2026-10-28") == 12
    z = store.q("SELECT * FROM lab_contracts WHERE id=?", (zero["id"],))[0]
    w = store.q("SELECT * FROM lab_contracts WHERE id=?", (week["id"],))[0]
    assert z["line_first"] == 1 and z["pnl_line"] < 0 < z["pnl_hold"]   # the 20% line cut a trade that came back
    assert w["line_first"] == 0 and w["pnl_line"] == w["pnl_hold"] > 0
    assert z["pnl_hold"] == pytest.approx(round((zero["bid0"] + 0.30 - 0.01 - zero["entry"]) * 100 - 0.04, 2))
    rep = CL.report()
    assert rep["signals"] == 1 and len(rep["rows"]) == 12 and all(r["too_few"] for r in rep["rows"])


def test_contract_lab_budget_and_capacity(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "d.db")
    monkeypatch.setattr(store, "_conn", None)
    now = datetime(2026, 10, 28, 10, 40, 5, tzinfo=ET)
    rows = _chain(now)
    f = _Fetch(rows)
    CL._state.update(tokens=0.0, t=None, tracked=None, last_sample={}, recent={})
    c = dict(CL.cfg(), starts_per_min=2)
    got = [CL.start({"id": f"s{i}", "ticker": f"T{i}", "side": "C", "family": "board_momo"}, now, f, c) for i in range(4)]
    assert got[:2] == [12, 12] and all("budget" in str(x) for x in got[2:])
    CL._state.update(tokens=10.0, t=time.time(), recent={})
    c = dict(CL.cfg(), max_tracked_signals=2)
    assert "maximum" in CL.start({"id": "s9", "ticker": "T9", "side": "C", "family": "board_momo"}, now, f, c)


def test_old_rules_now_record_best_and_worst_moves(monkeypatch):
    import policy_old
    monkeypatch.setattr(core, "now_et", lambda: datetime(2026, 10, 28, 10, 30, tzinfo=ET))
    monkeypatch.setattr(store, "pos_save", lambda p: None)
    p = {"id": "O-1", "ledger": "old", "symbol": "SPY", "side": "C", "fill": 1.00, "qty_open": 1, "mfe": 0, "mae": 0,
         "plan": {"invalidation": 590.0, "stop": 0.80, "be_hit": False, "t1_done": False, "flat_by": "11:30", "be_trigger": 1.30,
                  "t1": 1.60, "be_stop": 1.00, "lock_after_t1": 1.20}}
    for bid in (1.10, 0.90, 1.05):
        policy_old.manage(p, {"ok": False}, lambda s, b=bid: ({"bid": b, "ask": b + 0.02}, None))
    assert p["mfe"] == pytest.approx(10.0) and p["mae"] == pytest.approx(-10.0)    # recorded; exits unchanged
