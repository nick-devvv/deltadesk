"""v3.4 strategy lab: the signal tape (every strategy on every stock, causal), outcomes vs matched random entries,
per-strategy paper ledgers with caps, exits, the what-works-where report, the bar archive. Offline, fake Schwab."""
import json
import time
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

import core
import lab
import matched_benchmarks as MB
import paper
import scanner_setups as SS
import store
import test_v31 as V
from test_v33 import world, _board_at  # noqa: F401


class Hist:
    def __init__(self, f):
        self.f, self.calls = f, 0

    def history(self, t, s, e):
        self.calls += 1
        m = self.f.m1s.get(t)
        return None if m is None else m[(m.index >= pd.Timestamp(s)) & (m.index < pd.Timestamp(e))]


def _reset_lab():
    lab._state.update(hist_tokens=1000, hist_t=time.time(), hist_at={}, hist={}, last_bar={}, ep={}, noise_prev={}, counts={},
                      att_tokens=0.0, att_t=None, cats=None, cats_at=0.0, agg={})
    lab._schema()
    store.x("DELETE FROM lab_tape")


def _run(world, hh, mm, mutate=None, **kw):
    clock, f, prov = world
    lab.use(Hist(f))
    if mutate:
        mutate(f)
    _board_at(clock, hh, mm)
    now = clock()
    SS._state["bars"] = {t: (time.time(), f.m1_today(t, now.date())) for t in f.m1s}
    _reset_lab()
    c = dict(lab.cfg(), max_bars_per_step=500, step_budget_s=999, paper=False, **kw)
    lab._pull_history(now, c)
    base = store.kv_get(f"scan_base:{now.date()}")
    return lab.scan(now, base, c), now, c


@pytest.fixture
def lw(world):
    lab.use(None)
    yield world
    lab.use(None)
    _reset_lab()


def test_the_tape_records_every_strategy_family_with_conditions(lw):
    sigs, now, c = _run(lw, 10, 40)
    fams = {s["family"] for s in sigs}
    for need in ("board_orb_break", "board_orb_retest", "v3", "macd_video", "noise", "orb15_base"):
        assert need in fams, (need, fams)
    for s in sigs:
        cd = s["conditions"]
        for k in ("time_window", "rvol", "trend", "macd2", "vwap_dist", "price", "liquidity", "group", "x_lean", "earnings"):
            assert k in cd
        assert s["b"] + pd.Timedelta(minutes=1) == s["bar_end"] and s["bar_end"] <= pd.Timestamp(now)
    rows = store.q("SELECT id FROM lab_tape")
    assert len(rows) == len(sigs)
    again = lab.scan(now, store.kv_get(f"scan_base:{now.date()}"), c)       # same bars again: nothing new
    assert again == [] and len(store.q("SELECT id FROM lab_tape")) == len(sigs)
    assert not store.q("SELECT seq FROM events WHERE kind='research' AND text LIKE 'VWAP+MACD%'")   # quiet replay
    assert not store.q("SELECT k FROM kv WHERE k LIKE 'vwmacd:%'")                                  # own namespace


def test_future_bars_never_change_earlier_signals(lw):
    cut = V.DAY.replace(hour=10, minute=10)
    a, _, _ = _run(lw, 10, 40)

    def mutate(f):
        for t, m in f.m1s.items():
            later = m.index >= pd.Timestamp(cut) + pd.Timedelta(minutes=1)
            f.m1s[t] = m.copy()
            f.m1s[t].loc[later, ["Open", "High", "Low", "Close"]] *= 0.9
    b, _, _ = _run(lw, 10, 40, mutate)
    early = lambda ss: {s["id"]: json.dumps({k: v for k, v in s["conditions"].items() if k != "n"}, sort_keys=True)
                        for s in ss if s["bar_end"] <= pd.Timestamp(cut) + pd.Timedelta(minutes=1)}
    assert early(a) and early(a) == early(b)


def test_fast_outcomes_match_the_reference_path_rules():
    rng = np.random.default_rng(4)
    idx = pd.date_range("2026-10-28 09:30", periods=390, freq="1min", tz=core.ET)
    for k in range(60):
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, 390)))
        o = np.r_[100, c[:-1]] + (rng.normal(0, 0.4, 390) if k % 4 == 0 else 0)
        df = pd.DataFrame({"Open": o, "High": np.maximum(o, c) + 0.03, "Low": np.minimum(o, c) - 0.03, "Close": c}, index=idx)
        a = MB.arrays(df)
        for _ in range(6):
            ei, side, sd = int(rng.integers(0, 395)), "C" if rng.random() < .5 else "P", float(rng.uniform(0.05, 1.5))
            hz = [None, 5, 15, 30][int(rng.integers(0, 4))]
            assert MB.stock_outcome(df, ei, side, sd, horizon_min=hz) == MB.outcome_arrays(a, ei, side, sd, horizon_min=hz)
    m1, s1 = MB.control_mean(a, "C", 0.5, paths=20, seed=9)
    m2, s2 = MB.control_mean(a, "C", 0.5, paths=20, seed=9)
    assert (m1, s1) == (m2, s2) and s1 > 0                                   # reproducible


def test_outcomes_wait_for_the_close_and_use_matched_random_entries(lw):
    clock, f, prov = lw
    sigs, now, c = _run(lw, 10, 40)
    day = str(now.date())
    assert lab.resolve(day, now, c) == 0                                     # bars don't reach 15:25 yet: rows wait
    clock.t = V.DAY.replace(hour=15, minute=59, second=30)
    SS._state["bars"] = {t: (time.time(), f.m1_today(t, clock().date())) for t in f.m1s}
    n = lab.resolve(day, clock(), c)
    rows = store.q("SELECT * FROM lab_tape")
    assert n == len(rows) and not [r for r in rows if r["status"] == "OPEN"]
    done = [r for r in rows if r["status"] == "DONE"]
    assert done and all(r["r"] is not None and r["ctl_r"] is not None and r["ctl_n"] > 0 for r in done)
    assert all(c["window"][0] <= r["bar_end"][11:16] <= c["window"][1] for r in done)
    assert all(r["status"] == "OUT OF WINDOW" for r in rows if r["bar_end"][11:16] < "09:45")
    first = {r["id"]: r["ctl_r"] for r in done}
    store.x("UPDATE lab_tape SET status='OPEN'")
    lab.resolve(day, clock(), c)
    assert {r["id"]: r["ctl_r"] for r in store.q("SELECT * FROM lab_tape WHERE status='DONE'")} == first   # fixed seeds


def _live_signal(world, ticker="NVDA", fam="board_orb_break", hh=10, mm=40):
    clock, f, prov = world
    _board_at(clock, hh, mm)
    clock.t = V.DAY.replace(hour=hh, minute=mm, second=5)
    now = clock()
    SS._state["bars"] = {t: (time.time(), f.m1_today(t, now.date())) for t in f.m1s}
    m1 = f.m1_today(ticker, now.date())
    b = m1.index[-1]
    close = float(m1["Close"].iloc[-1])
    f.quotes = lambda ts: ({t: {"last": close, "bid": round(close - 0.01, 2), "ask": round(close + 0.01, 2),
                                "quote_ms": time.time() * 1000} for t in ts}, None)
    lab._schema()
    nf = {"close": close, "atr14": 3.0, "hm": "10:40"}
    s = lab._record(ticker, fam, "ORB15 breakout", "C", b, b + pd.Timedelta(minutes=1), close - 0.05, close - 0.40, True, nf, {}, now)
    return s, now


def test_a_live_signal_is_paper_traded_in_its_own_ledger_with_strict_fills(lw):
    clock, f, prov = lw
    lab._state.update(att_t=None)
    prov.q["NVDA261106C00140000"] = (4.90, 5.00)
    s, now = _live_signal(lw)
    assert s["live"]
    out = lab.paper_attempt(s, now, dict(lab.cfg()))
    assert out.startswith("ORDER"), out
    p = store.positions(ledger="lab_orb_break", status="OPEN")[0]
    assert p["qty_init"] == 1 and p["plan"]["exec_model"].startswith("2026-10-30.exec2") and p["fill"] == pytest.approx(5.01)
    assert p["plan"]["gate"]["state"] == "ENTRY CONDITIONS MET" and p["plan"]["row"]["tape_id"] == s["id"]
    assert p["plan"]["premium_stop"] >= round(p["fill"] * 0.8, 2) - 0.01                      # the 20% line from the fill
    assert lab.paper_attempt(s, now, dict(lab.cfg())) == "already tried"
    assert not store.q("SELECT seq FROM events WHERE kind='lab_orb_break'") and store.q("SELECT seq FROM events WHERE kind='lab'")
    st = __import__("server").state(0)
    assert not [x for x in st["positions"] if x["ledger"].startswith("lab_")]                  # not on the trade page


def test_lab_caps_budget_pause_and_main_ledgers(lw):
    clock, f, prov = lw
    prov.q["NVDA261106C00140000"] = (4.90, 5.00)
    s, now = _live_signal(lw)
    lab._state.update(att_t=None)
    c = dict(lab.cfg(), max_open_per_ledger=0)
    assert lab.paper_attempt(s, now, c).startswith("BLOCKED-LIMIT")
    c = dict(lab.cfg(), max_open_total=0)
    assert lab.paper_attempt(s, now, c).startswith("BLOCKED-LIMIT")
    lab._state.update(att_t=time.time(), att_tokens=0.0)
    assert "budget" in lab.paper_attempt(s, now, dict(lab.cfg()))
    lab._state.update(att_t=None)
    store.kv_set("paper_pause", {"by": "Nick"})
    assert "paused" in lab.paper_attempt(s, now, dict(lab.cfg()))
    store.kv_set("paper_pause", None)
    s2 = dict(s, ticker="SPY", family="v3")
    assert "own ledgers" in lab.paper_attempt(s2, now, dict(lab.cfg()))                      # SPY/QQQ keep the v3 ledgers
    late = dict(s, bar_end=s["bar_end"] - pd.Timedelta(minutes=10), live=False)
    lab._state.update(att_t=None)
    assert not lab.paper_attempt(late, now, dict(lab.cfg())).startswith("ORDER")             # stale: the gate fails closed
    skips = store.q("SELECT decision, reasons FROM candidates WHERE portfolio='lab_orb_break'")
    assert skips and all(json.loads(x["reasons"]) for x in skips if x["decision"] != "ORDER")


def test_lab_exits_target_stop_premium_and_all_out(lw):
    clock, f, prov = lw
    sym = "NVDA261106C00140000"
    prov.q[sym] = (4.90, 5.00)
    s, now = _live_signal(lw)
    lab._state.update(att_t=None)
    assert lab.paper_attempt(s, now, dict(lab.cfg())).startswith("ORDER")
    p = store.positions(ledger="lab_orb_break", status="OPEN")[0]
    assert lab.manage_all(now) == 0                                                            # nothing hit yet
    prov.q[sym] = (round(p["plan"]["premium_stop"] - 0.05, 2), round(p["plan"]["premium_stop"] + 0.05, 2))
    import marketdata
    marketdata._quotes.pop(sym, None)
    assert lab.manage_all(now) == 1
    p = store.q("SELECT status, plan FROM positions WHERE ledger='lab_orb_break'")[0]
    assert p["status"] == "CLOSED" and "20%" in json.loads(p["plan"])["exit_reason"]
    store.x("DELETE FROM ideas WHERE portfolio='lab_orb_break'")
    store.x("DELETE FROM gate_setups")
    prov.q[sym] = (4.90, 5.00)
    marketdata._quotes.pop(sym, None)
    s3 = dict(s, id=s["id"] + "b", b=s["b"])
    lab._state.update(att_t=None)
    assert lab.paper_attempt(s3, now, dict(lab.cfg())).startswith("ORDER")
    clock.t = V.DAY.replace(hour=15, minute=26)
    assert lab.manage_all(clock()) == 1
    assert "ALL OUT" in json.loads(store.q("SELECT plan FROM positions WHERE ledger='lab_orb_break' ORDER BY opened DESC")[0]["plan"])["exit_reason"]


def _tape_row(i, fam, t, day, r, ctl, cond):
    store.x("INSERT INTO lab_tape(id, day, ticker, family, setup, side, signal_bar, bar_end, observed_at, live, level, invalidation, "
            "use_level, price, atr, conditions, status, r, r_15m, ctl_r, ctl_n, version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"x{i}", day, t, fam, "s", "C", f"{day}T10:00:00-04:00", f"{day}T10:01:00-04:00", "", 1, 1, 0.9, 1, 1, 1,
             json.dumps(cond), "DONE", r, r, ctl, 20, "t"))


def test_what_works_splits_by_stock_group_and_condition_against_random(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "d.db")
    monkeypatch.setattr(store, "_conn", None)
    lab._schema()
    days = [f"2026-10-{d:02d}" for d in range(5, 27) if pd.Timestamp(f"2026-10-{d:02d}").weekday() < 5][:12]
    i = 0
    for d in days:                                    # VWAP reclaim beats random only when X agrees; ORB break is noise
        for k in range(12):
            agree = k % 2 == 0
            _tape_row(i, "board_vwap_reclaim", "NVDA", d, 1.0 if agree else -0.5, 0.0, {"group": "Semiconductors", "x_lean": "X agrees" if agree else "no X read"})
            i += 1
            _tape_row(i, "board_orb_break", "AMD", d, -0.2, -0.2, {"group": "Semiconductors", "x_lean": "no X read"})
            i += 1
    _tape_row(i, "board_orb_break", "XYZ", days[0], 2.0, 0.0, {"group": "Fintech and crypto", "x_lean": "no X read"})
    w = lab.what_works("strategy")
    by = {r["key"][0]: r for r in w["rows"]}
    assert by["board_vwap_reclaim"]["edge"] == pytest.approx(0.25) and by["board_vwap_reclaim"]["edge_ci95"] is not None
    assert by["board_orb_break"]["n"] == 145 and by["board_orb_break"]["win_rate"] < 5
    w = lab.what_works("strategy_condition", cond="x_lean")
    xr = {tuple(r["key"]): r for r in w["rows"]}
    agree = xr[("board_vwap_reclaim", "X agrees")]
    assert agree["edge"] == pytest.approx(1.0) and agree["both_halves"] and not agree["too_few"]
    assert xr[("board_vwap_reclaim", "no X read")]["edge"] == pytest.approx(-0.5)
    w = lab.what_works("strategy_ticker")
    xyz = next(r for r in w["rows"] if r["key"] == ["board_orb_break", "XYZ"])
    assert xyz["too_few"] and xyz["group_level"]["n"] == 1 and xyz["all_stocks"]["n"] == 145    # the hierarchy is shown
    assert w["rows"][-1]["too_few"]                                                             # too-few rows sort last
    assert "Nothing here is promoted" in w["note"]


def test_x_read_is_only_what_was_known_at_the_signal(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "d.db")
    monkeypatch.setattr(store, "_conn", None)
    be = pd.Timestamp("2026-10-28 10:30", tz=core.ET)
    cats = {"NVDA": [{"id": "a", "first_detected_at": "2026-10-28T10:45:00-04:00", "label": "confirmed",
                      "sentiment": {"trader": {"lean": "bullish"}}},
                     {"id": "b", "first_detected_at": "2026-10-28T09:50:00-04:00", "label": "unverified",
                      "sentiment": {"trader": {"lean": "bearish"}}, "attention": {"accelerating": True}}]}
    c = lab.conditions("NVDA", "C", {"hm": "10:30", "close": 140.0, "atr14": 3.0}, be, cats)
    assert c["x_id"] == "b" and c["x_lean"] == "X disagrees" and c["x_label"] == "unverified" and c["x_attention"] == "rising"
    c = lab.conditions("NVDA", "P", {"hm": "10:30"}, be, cats)
    assert c["x_lean"] == "X agrees"
    assert lab.conditions("AMD", "C", {"hm": "10:30"}, be, cats)["x_lean"] == "no X read"


def test_archive_roundtrip_backfill_and_history_budget(lw, tmp_path, monkeypatch):
    clock, f, prov = lw
    assert str(lab.ARCHIVE).startswith(str(tmp_path))                     # the test harness keeps the real archive clean
    m = f.m1s["NVDA"]
    d0 = sorted(set(m.index.date))[0]
    g = m[m.index.date == d0]
    assert lab.archive_write(d0, "NVDA", g.iloc[:100]) == 100
    assert lab.archive_write(d0, "NVDA", g) == len(g)                      # merged, not duplicated
    back = lab.archive_read(d0, "NVDA")
    assert len(back) == len(g) and np.allclose(back["Close"].values, g["Close"].values)
    h = Hist(f)
    lab.use(h)
    _board_at(clock, 9, 0)
    lab._state.update(hist_at={}, hist={}, hist_t=time.time(), hist_tokens=2.0)
    assert lab._pull_history(clock(), dict(lab.cfg(), history_calls_per_min=2)) == 2 and h.calls == 2    # the budget holds
    assert len(lab.archive_days()) >= 10                                                       # earlier sessions back-filled
    t = next(iter(lab._state["hist"]))
    assert lab._state["hist"][t].index.max().date() < clock().date()                          # prior sessions only


def test_registry_keeps_everything_running_and_nothing_is_qualified():
    import strategy_registry as SR
    SR._cache.update(mtime=None, data=None)
    reg = json.loads(SR.FILE.read_text())
    assert reg["version"] == "2026-10-30.registry2" and reg["qualified"] == []
    st = {e["id"]: e for e in reg["experiments"]}
    assert not [e for e in reg["experiments"] if e["status"] in ("RETIRED", "PAPER QUALIFIED")]
    assert st["MACD-VIDEO-5M-2R"]["previous_status"] == "RETIRED"
    assert st["INPLAY-ORB15-BASE-SIGNAL"]["status"] == "DRAFT" and st["EXP-002-FIRST-RETEST"]["status"] == "DRAFT"   # Nick: no verdict yet
    for fam in lab.FAMILIES:
        assert st["LAB-" + fam.upper().replace("_", "-")]["spec"]["ledger"] == lab.LEDGER_OF[fam]
    assert set(lab.LEDGER_OF.values()) == set(paper.LAB_LEDGERS) and all(paper.is_strict(x) for x in paper.LAB_LEDGERS)


def test_batched_option_quotes_use_one_request(monkeypatch):
    import marketdata
    import schwab
    calls = []

    def fake_get(path, params):
        calls.append(params["symbols"])
        syms = params["symbols"].split(",")
        return {s: {"quote": {"bidPrice": 1.0, "askPrice": 1.1, "quoteTime": int(time.time() * 1000)}} for s in syms}, None
    monkeypatch.setattr(schwab, "_get", fake_get)
    monkeypatch.setattr(marketdata, "_provider", marketdata.SchwabREST())
    syms = [f"NVDA261106C0014{i:04d}" for i in range(12)]
    for s in syms:
        marketdata._quotes.pop(s, None)
    got, err = marketdata.option_quotes(syms)
    assert len(calls) == 1 and set(got) == set(syms) and all(q["bid"] == 1.0 for q in got.values())
    marketdata.option_quotes(syms)
    assert len(calls) == 1                                                  # fresh quotes are not fetched again
    monkeypatch.setattr(marketdata, "_provider", None)


def test_kill_switch_closes_lab_trades_and_lab_has_no_order_path(lw):
    clock, f, prov = lw
    prov.q["NVDA261106C00140000"] = (4.90, 5.00)
    s, now = _live_signal(lw)
    lab._state.update(att_t=None)
    assert lab.paper_attempt(s, now, dict(lab.cfg())).startswith("ORDER")
    import engine
    engine.kill_paper("test")
    assert not store.positions(ledger="lab_orb_break", status="OPEN")
    src = open(core.HERE / "lab.py").read()
    assert "broker" not in src and "/orders" not in src and "/trader" not in src
