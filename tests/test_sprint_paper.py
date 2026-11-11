"""sprint_paper.py: the PAPER forward-test ledgers (fb_or = setups_v2-012, otm_put = otm_v1-011, otm_bounce =
otm_v1-042, otm_h = otm_v1-040 + f_rvol >= 1.06). Parity with the sprint engine (same bars -> same signals, same option prices -> same contract), no
look-ahead and finished bars only, restart safety, exits at sim.py's trigger prices, every otm filter on and off
(unknown VIXY -> no trade), the kill switch and quote-freshness rules, the isolated risk book, the wiring into
v4index / v4report / v4api, and that nothing can reach a real order path. Synthetic data only, no network."""
import csv
import io
import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import core
import fakes
import health
import marketdata
import sprint_paper as SP
import sprint_synth as SS
import store
import v4api
import v4exec
import v4index
import v4report
import v4risk
import v4store as S
from sprint import bs, contracts, data, engine, entries, sim
from sprint.spread import SpreadModel

ROOT = Path(__file__).resolve().parents[1]
ET = core.ET
WED = date(2026, 11, 4)                 # Wednesday, not an FOMC day, not a third Friday


# ================================================================ fakes
class Book(marketdata.Provider):
    """Executable option quotes from a dict, dated `lag` seconds before the fake clock."""
    name = "Schwab (sprint test book)"
    executable = True

    def __init__(self, clock, lag=0.5):
        self.clock, self.lag, self.q, self.missing = clock, lag, {}, set()

    def set(self, sym, bid, ask, delta=None):
        self.q[sym] = (bid, ask, delta)

    def option_quote(self, symbol):
        if symbol in self.missing or symbol not in self.q:
            return None, "no quote (test)"
        b, a, d = self.q[symbol]
        qt = pd.Timestamp(self.clock()) - pd.Timedelta(seconds=self.lag)
        return {"bid": b, "ask": a, "last": round((a + b) / 2, 2), "delta": d, "iv": 0.2, "quote_time": qt,
                "bid_size": 10, "ask_size": 10, "multiplier": 100, "src": self.name}, None


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    monkeypatch.setattr(health, "_feed", {"ok": None, "t": None, "why": None})
    clock = fakes.Clock(datetime(2026, 11, 4, 9, 30, tzinfo=ET))
    monkeypatch.setattr(core, "now_et", clock)
    book = Book(clock)
    marketdata.use(book)
    SP._cache.clear()
    monkeypatch.setattr(SP, "_state", {"last_error": None, "errors": 0})
    monkeypatch.setattr(SP, "vixy_source", lambda now: {"m1": None, "daily": None, "notes": ["test: no VIXY"]})
    yield clock, book
    marketdata.use(None)
    SP._cache.clear()


def at(clock, day, hhmm, sec=5):
    clock.t = datetime.combine(day, datetime.strptime(hhmm, "%H:%M").time(), ET).replace(second=sec)
    with marketdata._lock:
        marketdata._quotes.clear()                 # a price change in the test book is seen at once
    return clock.t


def weekdays_before(day, n):
    out, d = [], day
    while len(out) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return sorted(out)


def m1_market(day, closes, prior_days=6, px=600.0, prior_range=0.30, bars=None):
    """Engine-style bars (ET index, Open..Volume, 04:00-19:59): flat prior sessions at px +/- prior_range; today's closes
    follow `closes` (bar idx -> close, carried forward; premarket at the first value), bars {idx: (o, h, l, c)} override."""
    rows = []
    for d in weekdays_before(day, prior_days):
        for m in range(240, 1200):
            t = pd.Timestamp(datetime.combine(d, datetime.min.time())).tz_localize(ET) + pd.Timedelta(minutes=m)
            rows.append((t, px, px + prior_range, px - prior_range, px, 1000.0))
    cur = closes.get(0, px)
    for m in range(240, 1200):
        i = m - 570
        if 0 <= i and i in closes:
            cur = closes[i]
        o = c = cur
        h, l = c + 0.01, c - 0.01
        if bars and i in bars:
            o, h, l, c = bars[i]
            cur = c
        t = pd.Timestamp(datetime.combine(day, datetime.min.time())).tz_localize(ET) + pd.Timedelta(minutes=m)
        rows.append((t, o, h, l, c, 1000.0))
    df = pd.DataFrame(rows, columns=["ts", "Open", "High", "Low", "Close", "Volume"]).set_index("ts")
    return df


def upto(m1, now):
    """What the engine hands the ledger: finished bars only."""
    return m1[m1.index + pd.Timedelta(minutes=1) <= pd.Timestamp(now)]


def bs_chain(book, day, S0, minutes, iv, half=0.02):
    """Chain rows priced by Black-Scholes at S0 with `minutes` to 16:00; every row also quoted in the book."""
    def fn(ticker, side):
        rows = []
        for k in range(int(round(S0)) - 15, int(round(S0)) + 16):
            mid = round(bs.price(S0, float(k), bs.t_years(minutes), iv, side), 2)
            if mid < 0.02:
                continue
            sym = f"{ticker}{day:%y%m%d}{side}{k * 1000:08d}"
            bid, ask = round(mid - min(half, mid / 2), 2), round(mid + half, 2)
            book.set(sym, bid, ask, None)
            rows.append({"symbol": sym, "strike": float(k), "bid": bid, "ask": ask, "delta": None, "iv": iv, "ts": None})
        return rows, None
    return fn


def vixy_world(day, prior_close=20.0, now_close=20.0, pctl_rank="low", n=300, bars=True, daily=True):
    """A VIXY source: 1-minute bars (prior session flat at prior_close, today flat at now_close) and n daily closes ending
    at the prior session, whose last close ranks lowest ("low"), highest ("high") or in the middle ("mid")."""
    prior = weekdays_before(day, 1)[0]
    m = None
    if bars:
        m = m1_market(day, {0: now_close}, prior_days=1, px=prior_close, prior_range=0.01)
    d = None
    if daily:
        dates = [x.date() for x in pd.bdate_range(end=pd.Timestamp(prior), periods=n)]
        vals = list(np.linspace(30.0, 40.0, n - 1))
        last = {"low": 25.0, "high": 45.0, "mid": 36.0}[pctl_rank]
        d = pd.Series(vals + [last], index=dates)
    return lambda now: {"m1": m, "daily": d, "notes": ["test VIXY"]}


def decisions(ledger, kind="signal"):
    return [d for d in S.decisions(ledger=ledger, kind=kind, limit=5000)]


def no_errors():
    assert SP._state["last_error"] is None, SP._state["last_error"]


# ================================================================ rules
def test_rules_are_the_backtest_runs_read_from_the_pinned_specs():
    want = {"fb_or": ("setups_v2-012", "failed_break_or", "C", (), "d40-55t45", "premium"),
            "otm_put": ("otm_v1-011", "time_1030", "P", ("vixy_pctl_le40", "vixy_not_rising", "day_up", "wed_fri", "skip_opex"),
                        "d06-15t10", "fixed"),
            "otm_bounce": ("otm_v1-042", "time_1100", "C", ("vixy_pctl_ge60", "day_down", "skip_opex"), "d03-12t07", "fixed"),
            "otm_h": ("otm_v1-040", "time_1100", "C", (), "d03-12t07", "fixed")}
    for name, (rid, entry, side, fs, rule, stop) in want.items():
        r = SP.rules(name)
        assert (r["run_id"], r["entry"], r["side"], r["filters"], r["contract"], r["exit"]["stop"]) == (rid, entry, side, fs, rule, stop)
        assert r["exit"]["allout"] == "15:25" and r["exit"]["time"] == "b" and r["exit"]["tp"] == "none" and r["exit"]["trail"] == "none"
        spec = json.loads((ROOT / r["spec"]).read_text())
        run = [x for x in engine.expand(spec) if x["run_id"] == rid][0]
        assert run["exit"].as_dict() == r["exit"] and tuple(run["filters"]) == r["filters"]
    assert SP.rules("otm_put")["exit"]["fixed_stop"] == 0.95 and SP.rules("otm_put")["exit"]["fixed_target"] == 99.0
    assert set(v4index.LEDGERS) >= set(SP.LEDGERS) and all(v4index.LEDGERS[x] == "sprint" for x in SP.LEDGERS)
    assert SP.SYMBOLS == ("SPY", "QQQ") and SP.WINDOW_S == 180


def test_a_changed_spec_refuses_new_entries(env, monkeypatch, tmp_path):
    clock, book = env
    spec = tmp_path / "setups_v2.json"
    spec.write_text((ROOT / "sprint/specs/setups_v2.json").read_text() + "\n")
    monkeypatch.setattr(SP, "SPEC_DIR", tmp_path)
    SP.rules.cache_clear()
    try:
        assert "changed since the backtest" in SP.refusal("fb_or")
        m1 = m1_market(WED, {0: 600.0})
        now = at(clock, WED, "10:00")
        SP.tick("SPY", {"m1": upto(m1, now)}, lambda t, s: ([], None), now)
        d = S.decisions(ledger="fb_or", kind="day")
        assert d and d[0]["decision"] == "REFUSED" and not S.positions(ledger="fb_or")
    finally:
        SP.rules.cache_clear()


# ================================================================ parity with the sprint engine
@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    root = tmp_path_factory.mktemp("sprint_cache")
    days = SS.weekdays(date(2025, 3, 3), 12)
    stock = SS.write_cache(root, "SPY", days, seed=11)
    allb = pd.concat([stock[d] for d in days], ignore_index=True)
    m1 = allb.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"}).set_index("ts")[
        ["Open", "High", "Low", "Close", "Volume"]]
    series = data.Series("SPY", data.read_stock("SPY", days[0], days[-1], root))
    return root, days, m1, series


def _bt_ctx(synth, day):
    root, days, m1, series = synth
    return data.DayContext(series, day, data.read_option_day("SPY", day, root), SpreadModel())


def test_parity_same_bars_same_signals_same_contract(env, synth):
    clock, book = env
    root, days, m1, series = synth
    run = dict([r for r in engine.expand(json.loads((ROOT / "sprint/specs/setups_v2.json").read_text()))
                if r["run_id"] == "setups_v2-012"][0], symbols=("SPY",))
    w = engine.TradeWriter(None)
    engine.run_pass([run], days[0], days[-1], root, SpreadModel(), writer=w)
    bt_trades = {(t["day"], int(t["signal_idx"])): t for t in csv.DictReader(io.StringIO(w.buf.getvalue()))}
    checked = 0
    for day in (date(2025, 3, 5), date(2025, 3, 6), date(2025, 3, 17)):
        ctx_bt = _bt_ctx(synth, day)
        want = entries.signals(ctx_bt, "failed_break_or", "C")
        assert want
        tapes = {s: t for s, t in ctx_bt.tapes.items() if t.right == "C"}

        def chain(ticker, side, _day=day, _tapes=tapes):
            i = (clock().hour * 60 + clock().minute) - 570 - 1          # the latest finished bar
            rows = []
            for s, t in _tapes.items():
                px = t.last_close(i, 5)
                if px is not None:
                    rows.append({"symbol": s, "strike": t.strike, "bid": round(px - 0.01, 2), "ask": round(px + 0.01, 2),
                                 "delta": 0.5, "iv": 0.2, "ts": (pd.Timestamp(clock()) - pd.Timedelta(seconds=30)).isoformat()})
            return rows, None
        last = max(s.idx for s in want)
        for i in range(15, last + 5):
            now = at(clock, day, SP._hm(i + 1))
            for s, t in tapes.items():                                # live quotes follow the option's own prints
                px = t.last_close(i, 5)
                if px is not None:
                    book.set(s, round(px - 0.01, 2), round(px + 0.01, 2))
            SP.tick("SPY", {"m1": upto(m1, now)}, chain, now)
            no_errors()
            ctx_live, _ = SP.context("SPY", upto(m1, now), now)
            for sig in [x for x in want if x.idx <= i]:                 # the live pick, given the same option prices
                rows = [{"symbol": s, "strike": t.strike, "bid": round(t.last_close(sig.idx, 5) - 0.01, 2),
                         "ask": round(t.last_close(sig.idx, 5) + 0.01, 2), "ts": None}
                        for s, t in tapes.items() if t.last_close(sig.idx, 5) is not None]
                k, _ = SP.pick(ctx_live, sig, "d40-55t45", rows, SP.bar_end(day, sig.idx))
                _t, info = contracts.pick(ctx_bt, "C", sig.idx, "d40-55t45")
                if not isinstance(info, dict):
                    assert k is None
                    continue
                assert k["symbol"] == info["symbol"] and k["delta_bs_est"] == info["delta"]
                assert k["iv_bs_est"] == round(info["iv"], 4)
                checked += 1
        got = sorted((d["data"]["signal"]["idx"], d["data"]["signal"]["kind"], d["data"]["signal"]["level"])
                     for d in decisions("fb_or") if d["date"] == str(day))
        assert got == sorted((s.idx, s.info["kind"], s.info["level"]) for s in want)
        for d in decisions("fb_or"):
            if d["date"] != str(day) or "contract" not in d["data"]:
                continue
            idx = d["data"]["signal"]["idx"]
            _t, info = contracts.pick(ctx_bt, "C", idx, "d40-55t45")
            assert d["data"]["contract"]["symbol"] == info["symbol"]
            bt = bt_trades.get((str(day), idx))
            if bt:                                                     # the sprint engine traded it: same contract
                assert bt["contract"] == d["data"]["contract"]["symbol"]
                assert float(bt["delta_est"]) == d["data"]["contract"]["delta_bs_est"]
                checked += 1
        for p in S.positions(ledger="fb_or", status="OPEN"):             # flat at the end of each session
            S.close_position(p["id"], p["entry_px"], "test: end of session")
    assert checked >= 4
    assert any(d["decision"] == "ORDER" for d in decisions("fb_or"))


# ================================================================ no look-ahead, finished bars only
def _fb_market(day=WED):
    # OR15L = 599.99 (today's bars 600 +/- 0.01); close below at 09:50 (low 599.94), back above at 09:52 -> OR15L failed break
    return m1_market(day, {0: 600.0, 20: 599.95, 22: 600.05}, bars={20: (599.99, 599.99, 599.94, 599.95)})


def test_signals_use_finished_bars_only_and_never_change_with_later_bars(env):
    clock, book = env
    m1 = _fb_market()
    full_now = at(clock, WED, "15:20")
    ctx_full, _ = SP.context("SPY", m1, full_now)
    full = entries.signals(ctx_full, "failed_break_or", "C")
    assert [(s.idx, s.info["kind"]) for s in full] == [(22, "OR15L")]
    for i in range(16, 60):
        now = at(clock, WED, SP._hm(i + 1))
        ctx, _ = SP.context("SPY", m1, now)                            # the whole day handed in: only finished bars count
        got = [(s.idx, s.info["kind"], s.price) for s in SP.signals(ctx, SP.rules("fb_or"))]
        assert got == [(s.idx, s.info["kind"], s.price) for s in full if s.idx <= i]
        assert np.isnan(ctx.c[i + 1:]).all()
    # the 09:52 bar still forming at 09:52:30 (its minute has not ended): no signal yet
    forming = at(clock, WED, "09:52", sec=30)
    ctx, _ = SP.context("SPY", m1, forming)
    assert SP.signals(ctx, SP.rules("fb_or")) == []
    # scrambling every bar after the signal changes neither the signal nor the recorded decision
    now = at(clock, WED, "09:53")
    SP.tick("SPY", {"m1": upto(m1, now)}, _fb_chain(book), now)
    before = decisions("fb_or")
    assert [d["decision"] for d in before] == ["ORDER"]
    rng = np.random.default_rng(3)
    m2 = m1.copy()
    later = (m2.index.date == WED) & (m2.index > pd.Timestamp(now))
    m2.loc[later, "Close"] = 600 + rng.normal(0, 2, later.sum())
    m2.loc[later, "Low"] = m2.loc[later, "Close"] - 1.0
    SP._cache.clear()
    ctx2, _ = SP.context("SPY", m2, at(clock, WED, "15:20"))
    assert [(s.idx, s.price) for s in SP.signals(ctx2, SP.rules("fb_or")) if s.idx <= 22] == [(22, full[0].price)]
    SP.tick("SPY", {"m1": upto(m2, clock())}, lambda t, s: ([], None), clock())
    after = [d for d in decisions("fb_or") if d["id"] == before[0]["id"]]
    assert after[0]["decision"] == before[0]["decision"] and after[0]["data"] == before[0]["data"]
    no_errors()


# ================================================================ fb_or flow, restart safety, quote freshness
def _fb_chain(book, day=WED):
    return bs_chain(book, day, 600.05, 390 - 23, 0.18)                  # S at the 09:52 bar, 367 minutes to 16:00


def test_fb_or_enters_once_with_everything_stamped_and_survives_a_restart(env):
    clock, book = env
    m1 = _fb_market()
    chain = _fb_chain(book)
    now = at(clock, WED, "09:53")
    SP.tick("SPY", {"m1": upto(m1, now)}, chain, now)
    no_errors()
    pos = S.positions(ledger="fb_or")
    assert len(pos) == 1
    p = pos[0]
    pl = p["plan"]
    assert p["book"] == "sprint" and p["kind"] == "option" and p["exec_model"] == "bidask065" and p["qty"] == 1
    assert p["id"] == "fb_or:2026-11-04-SPY-C-0953-OR15L" and p["signal_t"].startswith("2026-11-04T09:53")
    k = pl["contract"]
    assert 0.40 <= abs(k["delta_bs_est"]) <= 0.55 and k["price_used"] == "chain mid" and k["rule"] == "d40-55t45"
    assert {"mid", "bid", "ask", "spread", "chain_delta", "iv_bs_est", "chain_iv"} <= set(k)
    assert p["entry_px"] == book.q[k["symbol"]][1] and p["fees"] == 0.65            # bought at the ask, $0.65
    assert pl["source_run"] == "setups_v2-012" and pl["label"] == "PAPER (simulated fills)" and "forward test" in pl["status"]
    assert pl["signal"]["kind"] == "OR15L" and pl["signal"]["level"] == pytest.approx(599.99)
    assert pl["features"]["f_minute"] == 23 and pl["features"]["f_weekday"] == 2
    assert pl["exit"]["kind"] == "ceiling" and pl["exit"]["ceiling"] == 0.20 and pl["exit"]["window"] == "09:45-11:30"
    d = decisions("fb_or")
    assert len(d) == 1 and d[0]["decision"] == "ORDER" and d[0]["data"]["position"] == p["id"]
    n_dec = len(S.decisions(limit=5000))
    # restart: module caches gone, a new DB connection, the same minute ticked again and the next ones
    SP._cache.clear()
    store._conn = None
    marketdata.use(book)
    for hm in ("09:53", "09:54", "09:55"):
        now = at(clock, WED, hm, sec=40)
        SP.tick("SPY", {"m1": upto(m1, now)}, chain, now)
    assert len(S.positions(ledger="fb_or")) == 1 and len(S.decisions(limit=5000)) == n_dec
    no_errors()


def test_restart_while_waiting_for_a_quote_fills_once_and_a_lost_decision_is_recovered(env):
    clock, book = env
    m1 = _fb_market()
    chain = _fb_chain(book)
    book.lag = 10.0                                   # quotes dated before the signal bar ended + latency: no fill yet
    now = at(clock, WED, "09:53", sec=5)
    SP.tick("SPY", {"m1": upto(m1, now)}, chain, now)
    assert not S.positions(ledger="fb_or") and not decisions("fb_or")
    did = "fb_or:SPY:2026-11-04:22:OR15L"
    k = store.kv_get(f"{did}:contract")
    assert k and store.kv_get(f"{did}:eval")
    SP._cache.clear()
    store._conn = None                                # restart
    book.lag = 0.5
    rows_called = []
    now = at(clock, WED, "09:53", sec=30)
    SP.tick("SPY", {"m1": upto(m1, now)}, lambda t, s: rows_called.append(1) or chain(t, s), now)
    assert not rows_called                            # the stored contract is reused, the chain is not re-read
    pos = S.positions(ledger="fb_or")
    assert len(pos) == 1 and pos[0]["legs"][0]["symbol"] == k["symbol"]
    # a crash between the fill and its decision record: the next tick records ORDER, never a second position
    store.x("DELETE FROM v4_decisions WHERE id=?", (did,))
    now = at(clock, WED, "09:54")
    SP.tick("SPY", {"m1": upto(m1, now)}, chain, now)
    d = decisions("fb_or")
    assert len(S.positions(ledger="fb_or")) == 1 and d[0]["decision"] == "ORDER" and "restart" in d[0]["data"]["note"]
    no_errors()


@pytest.mark.parametrize("case", ["early", "stale", "never"])
def test_fill_needs_a_fresh_quote_dated_after_the_signal_inside_the_backtest_window(env, case):
    clock, book = env
    m1 = _fb_market()
    chain = _fb_chain(book)
    book.lag = {"early": 4.5, "stale": 30.0, "never": 0.5}[case]    # 09:53:05 - 4.5 s is under 1 s after the bar ended
    if case == "never":
        book.option_quote = lambda s: (None, "no quote (test)")
    for sec in (5, 30):
        now = at(clock, WED, "09:53", sec=sec)
        if case == "early" and sec == 30:
            break
        SP.tick("SPY", {"m1": upto(m1, now)}, chain, now)
        assert not S.positions(ledger="fb_or") and not decisions("fb_or")      # waiting, nothing recorded yet
    if case == "early":
        book.lag = 0.5
        now = at(clock, WED, "09:54", sec=10)
        SP.tick("SPY", {"m1": upto(m1, now)}, chain, now)
        assert len(S.positions(ledger="fb_or")) == 1
        return
    now = at(clock, WED, "09:55", sec=50)                                  # 170 s after the bar: the window's last ticks
    SP.tick("SPY", {"m1": upto(m1, now)}, chain, now)
    d = decisions("fb_or")
    assert d and d[0]["decision"] == "MISSED" and not S.positions(ledger="fb_or")
    assert "fresh executable quote" in d[0]["reasons"][0]
    no_errors()


def test_a_signal_first_seen_after_the_window_is_missed_never_entered(env):
    clock, book = env
    m1 = _fb_market()
    now = at(clock, WED, "10:10")                                          # the desk starts 18 minutes after the signal
    SP.tick("SPY", {"m1": upto(m1, now)}, _fb_chain(book), now)
    d = decisions("fb_or")
    assert len(d) == 1 and d[0]["decision"] == "MISSED" and "first seen" in d[0]["reasons"][0]
    assert not S.positions(ledger="fb_or")


def test_busy_signal_is_skipped_and_logged(env):
    clock, book = env
    # OR15L failed break at 09:52, then an OR30L failed break at 10:20 while the first trade is still open
    closes = {0: 600.0, 20: 599.95, 22: 600.05, 30: 600.05, 48: 599.90, 50: 600.10}
    m1 = m1_market(WED, closes, bars={20: (599.99, 599.99, 599.94, 599.95), 48: (600.0, 600.0, 599.85, 599.90)})
    chain = bs_chain(book, WED, 600.05, 367, 0.18)
    for hm in ("09:53", "10:21"):
        now = at(clock, WED, hm)
        SP.tick("SPY", {"m1": upto(m1, now)}, chain, now)
    d = {x["data"]["signal"]["kind"]: x for x in decisions("fb_or")}
    assert d["OR15L"]["decision"] == "ORDER"
    assert d["OR30L"]["decision"] == "SKIP" and d["OR30L"]["reasons"] == ["busy: one position at a time (backtest rule)"]
    assert len(S.positions(ledger="fb_or")) == 1
    no_errors()


# ================================================================ exits: sim.py's triggers on live quotes
@pytest.mark.parametrize("idx,ceil,window", [(30, 0.20, "09:45-11:30"), (118, 0.20, "09:45-11:30"), (119, 0.12, "11:30-14:00"),
                                             (268, 0.12, "11:30-14:00"), (269, 0.10, "14:00-15:30"), (330, 0.10, "14:00-15:30")])
def test_ceiling_by_entry_window_at_the_sim_trigger_price(idx, ceil, window):
    sig = entries.Signal("failed_break_or", "SPY", WED, "C", idx, 600.0, 599.5, {})
    ex, txt, risk = SP.exit_plan(SP.rules("fb_or"), sig, 2.00, "SPY261104C00600000")
    assert ex["kind"] == "ceiling" and ex["ceiling"] == ceil and ex["window"] == window
    cost = 2.00 + 0.65 / 100
    assert ex["cost"] == pytest.approx(cost)
    assert ex["stop_bid"] == pytest.approx(cost * (1 - ceil) + 0.65 / 100, abs=1e-9)   # proceeds at the bid net of fees
    assert risk == pytest.approx(cost * ceil * 100, abs=0.01)
    # the sprint simulator, with a zero half-spread (live bid/ask are the fills), stops at exactly that price
    j = idx
    trig = ex["stop_bid"]
    ctx, tape = SS.make_ctx(WED, {0: 600.0}, {0: 2.00, j + 3: trig + 0.004}, prior_days=3, spread=SS.ConstSpread(0.0))
    out = sim.simulate(ctx, sig, sim.ExitCfg(stop="premium", time="b", tp="none", allout="15:25"), tape=tape,
                       cinfo={"px": 2.00, "iv": 0.2, "symbol": tape.symbol, "delta": 0.45})
    assert out["status"] == "TRADE" and out["entry_basis"] == 2.00 and out["exit_reason"] == "CEILING STOP"
    assert out["ceiling"] == ceil and out["legs"][0]["basis"] == pytest.approx(trig, abs=1e-9)


def _open(ledger, side="C", fill=2.0, idx=30, day=WED, sym=None):
    sym = sym or f"SPY{day:%y%m%d}{side}00600000"
    sig = entries.Signal("x", "SPY", day, side, idx, 600.0, None, {})
    ex, txt, risk = SP.exit_plan(SP.rules(ledger), sig, fill, sym)
    rec = {"id": f"{ledger}:t-{sym}", "ledger": ledger, "book": "sprint", "kind": "option", "date": day.isoformat(), "ticker": "SPY",
           "direction": "long" if side == "C" else "short", "side": side, "qty": 1, "entry_px": fill, "entry_t": "x", "fees": 0.65,
           "risk_usd": risk, "legs": [{"symbol": sym, "label": "600" + side, "right": side, "strike": 600.0, "expiry": day.isoformat(),
                                       "action": "buy", "qty": 1}],
           "plan": {"exit": ex, "exit_rule": txt, "source_run": SP.PINS[ledger][1], "label": SP.LABEL, "status": SP.STATUS,
                    "premium_stop": 0}, "version": SP.VERSION, "exec_model": "bidask065"}
    pid, why = S.open_position(rec)
    assert pid, why
    return pid, sym, ex


def test_ceiling_stop_acts_on_the_live_bid_and_exits_are_never_blocked(env):
    clock, book = env
    pid, sym, ex = _open("fb_or")
    assert ex["stop_bid"] == pytest.approx(1.6117, abs=1e-9)
    at(clock, WED, "10:05")
    book.set(sym, 1.62, 1.64)
    SP.manage(S.get(pid))
    assert S.get(pid)["status"] == "OPEN" and S.get(pid)["plan"]["mtm"] == pytest.approx(-38.65)
    store.kv_set("v4_enabled", False)                                     # kill switch off for entries: exits still run
    at(clock, WED, "10:06")
    book.set(sym, 1.61, 1.63)
    SP.manage(S.get(pid))
    p = S.get(pid)
    assert p["status"] == "CLOSED" and p["exit_px"] == 1.61 and p["exit_reason"].startswith("CEILING STOP 20%")
    assert p["realized"] == pytest.approx((1.61 - 2.00) * 100 - 1.30)


def test_fixed_stop_and_target_on_the_mid_like_sim(env):
    clock, book = env
    pid, sym, ex = _open("otm_put", side="P", fill=0.40)
    assert ex["debit"] == 0.40 and ex["stop_mid"] == pytest.approx(0.02) and ex["target_mid"] == pytest.approx(40.0)
    at(clock, WED, "12:00")
    book.set(sym, 0.0, 0.05)                                               # mid 0.025: above the -95% line
    SP.manage(S.get(pid))
    assert S.get(pid)["status"] == "OPEN"
    at(clock, WED, "12:01")
    book.set(sym, 0.0, 0.04)                                               # mid 0.02 <= 0.40 x 0.05
    SP.manage(S.get(pid))
    p = S.get(pid)
    assert p["status"] == "CLOSED" and p["exit_px"] == 0.0 and p["exit_reason"].startswith("FIXED STOP -95%")
    pid2, sym2, ex2 = _open("otm_bounce", side="C", fill=0.05, sym="SPY261104C00610000")
    at(clock, WED, "13:00")
    book.set(sym2, 4.96, 4.98)                                             # mid 4.97: under 0.05 x 100
    SP.manage(S.get(pid2))
    assert S.get(pid2)["status"] == "OPEN"
    at(clock, WED, "13:01")
    book.set(sym2, 5.00, 5.04)                                             # mid 5.02 >= 0.05 x 100
    SP.manage(S.get(pid2))
    p2 = S.get(pid2)
    assert p2["status"] == "CLOSED" and p2["exit_px"] == 5.00 and p2["exit_reason"].startswith("FIXED TARGET +9900%")
    # sim.py's fixed levels for the same debit (a zero half-spread makes the debit the fill)
    assert ex["stop_mid"] == pytest.approx(0.40 * (1 - 0.95)) and ex2["target_mid"] == pytest.approx(0.05 * (1 + 99.0))


def test_all_out_1525_and_a_pending_exit_without_a_quote(env):
    clock, book = env
    pid, sym, _ = _open("otm_put", side="P", fill=0.40)
    pid2, sym2, _ = _open("fb_or", sym="SPY261104C00601000")
    book.set(sym, 0.30, 0.34)
    book.missing.add(sym2)
    at(clock, WED, "15:24", sec=50)
    v4index.manage(clock())
    assert S.get(pid)["status"] == "OPEN" and S.get(pid2)["status"] == "OPEN"
    at(clock, WED, "15:25", sec=1)
    v4index.manage(clock())
    p = S.get(pid)
    assert p["status"] == "CLOSED" and p["exit_px"] == 0.30 and p["exit_reason"].startswith("ALL OUT 15:25")
    p2 = S.get(pid2)
    assert p2["status"] == "OPEN" and p2["plan"]["pending_exit"]["reason"].startswith("ALL OUT 15:25")
    book.missing.clear()
    book.set(sym2, 1.70, 1.74)
    at(clock, WED, "15:25", sec=20)
    v4index.manage(clock())
    p2 = S.get(pid2)
    assert p2["status"] == "CLOSED" and p2["exit_px"] == 1.70 and p2["exit_reason"].startswith("ALL OUT 15:25")


# ================================================================ the far-OTM ledgers and their filters
def _otm_world(env, monkeypatch, day, up=True, pctl="low", vix_now=20.0, vix_prev=20.0, vixy_bars=True, vixy_daily=True):
    clock, book = env
    px = 600.5 if up else 599.0
    m1 = m1_market(day, {0: px})
    monkeypatch.setattr(SP, "vixy_source", vixy_world(day, vix_prev, vix_now, pctl, bars=vixy_bars, daily=vixy_daily))
    return m1, bs_chain(book, day, px, 330, 0.15), bs_chain(book, day, px, 300, 0.30)


def _tick_at(clock, m1, chain, day, hm, sec=5):
    now = at(clock, day, hm, sec=sec)
    SP.tick("SPY", {"m1": upto(m1, now)}, chain, now)
    return now


@pytest.mark.parametrize("case,day,kw,want", [
    ("all pass", WED, {}, None),
    ("calm percentile above 40%", WED, {"pctl": "mid"}, "VIXY percentile above 40%"),
    ("VIXY up more than 1%", WED, {"vix_now": 20.25}, "up more than 1%"),
    ("VIXY up exactly 1% is not rising", WED, {"vix_now": 20.2}, None),
    ("down day", WED, {"up": False}, "day_up"),
    ("Monday", date(2026, 11, 2), {}, "wed_fri: Monday or Tuesday"),
    ("Tuesday", date(2026, 11, 3), {}, "wed_fri: Monday or Tuesday"),
    ("second Friday trades", date(2026, 11, 13), {}, None),
    ("third Friday", date(2026, 11, 20), {}, "monthly expiration (third Friday)"),
    ("no VIXY daily closes", WED, {"vixy_daily": False}, "VIXY percentile unknown"),
    ("no VIXY 1-minute bars", WED, {"vixy_bars": False}, "no VIXY bars for the day"),
])
def test_otm_put_filters(env, monkeypatch, case, day, kw, want):
    clock, book = env
    m1, put_chain, _ = _otm_world(env, monkeypatch, day, **kw)
    _tick_at(clock, m1, put_chain, day, "10:30", sec=25)
    no_errors()
    d = [x for x in decisions("otm_put")]
    assert len(d) == 1, case
    if want is None:
        assert d[0]["decision"] == "ORDER", (case, d[0]["reasons"])
        p = S.positions(ledger="otm_put")[0]
        k = p["plan"]["contract"]
        assert p["side"] == "P" and 0.06 <= abs(k["delta_bs_est"]) <= 0.15 and k["rule"] == "d06-15t10"
        assert p["plan"]["exit"]["kind"] == "fixed" and p["plan"]["filters"]["result"] == "pass"
        fi = p["plan"]["filters"]["inputs"]
        assert fi["vixy_pctl"] is not None and fi["vixy_pctl"] <= 0.40 and fi["day_up"] is True and fi["vixy_last_bar"] == "10:29"
        assert p["plan"]["features"]["f_vixy_pctl"] == pytest.approx(fi["vixy_pctl"], abs=1e-4)
    else:
        assert d[0]["decision"] == "FILTERED" and want in d[0]["reasons"][0], (case, d[0]["reasons"])
        assert not S.positions(ledger="otm_put")
        assert "filter_inputs" in d[0]["data"]


@pytest.mark.parametrize("case,day,kw,want", [
    ("stressed down day", WED, {"up": False, "pctl": "high"}, None),
    ("up day", WED, {"up": True, "pctl": "high"}, "day_down"),
    ("not stressed", WED, {"up": False, "pctl": "mid"}, "VIXY percentile below 60%"),
    ("Monday trades (no weekday rule)", date(2026, 11, 2), {"up": False, "pctl": "high"}, None),
    ("third Friday", date(2026, 11, 20), {"up": False, "pctl": "high"}, "monthly expiration"),
    ("unknown VIXY", WED, {"up": False, "vixy_daily": False}, "VIXY percentile unknown"),
])
def test_otm_bounce_filters(env, monkeypatch, case, day, kw, want):
    clock, book = env
    m1, _, call_chain = _otm_world(env, monkeypatch, day, **kw)
    _tick_at(clock, m1, call_chain, day, "11:00")
    no_errors()
    d = decisions("otm_bounce")
    assert len(d) == 1, case
    if want is None:
        assert d[0]["decision"] == "ORDER", (case, d[0]["reasons"])
        p = S.positions(ledger="otm_bounce")[0]
        assert p["side"] == "C" and 0.03 <= abs(p["plan"]["contract"]["delta_bs_est"]) <= 0.12
        assert "watch only" in p["plan"]["watch_only"]
    else:
        assert d[0]["decision"] == "FILTERED" and want in d[0]["reasons"][0], (case, d[0]["reasons"])


def test_vixy_bar_of_the_signal_minute_is_awaited_briefly_then_the_last_one_counts(env, monkeypatch):
    clock, book = env
    m1, put_chain, _ = _otm_world(env, monkeypatch, WED)
    src = SP.vixy_source(None)
    vm = src["m1"]
    gap = vm[vm.index != pd.Timestamp(datetime(2026, 11, 4, 10, 29, tzinfo=ET))]
    monkeypatch.setattr(SP, "vixy_source", lambda now: dict(src, m1=gap))
    _tick_at(clock, m1, put_chain, WED, "10:30", sec=5)
    assert not decisions("otm_put")                                       # VIXY's 10:29 bar may still arrive
    _tick_at(clock, m1, put_chain, WED, "10:30", sec=25)
    d = decisions("otm_put")
    assert d[0]["decision"] == "ORDER" and S.positions(ledger="otm_put")[0]["plan"]["filters"]["inputs"]["vixy_last_bar"] == "10:28"


def test_time_entry_without_its_bar_records_no_signal(env, monkeypatch):
    clock, book = env
    m1, put_chain, _ = _otm_world(env, monkeypatch, WED)
    m1 = m1[m1.index != pd.Timestamp(datetime(2026, 11, 4, 10, 29, tzinfo=ET))]
    for hm in ("10:30", "10:34"):
        _tick_at(clock, m1, put_chain, WED, hm)
    d = decisions("otm_put")
    assert len(d) == 1 and d[0]["decision"] == "NO SIGNAL" and "10:29" in d[0]["reasons"][0]
    assert not S.positions(ledger="otm_put")


def test_kill_switch_and_config_switch_block_entries_only(env, monkeypatch):
    clock, book = env
    m1, put_chain, _ = _otm_world(env, monkeypatch, WED)
    v4risk.kill("test")
    _tick_at(clock, m1, put_chain, WED, "10:30", sec=25)
    d = decisions("otm_put")
    assert d[0]["decision"] == "BLOCKED-RISK" and "kill switch" in d[0]["reasons"][0] and not S.positions(ledger="otm_put")
    import retire
    cfg = dict(retire.cfg(), sprint_paper={"fb_or": True, "otm_put": True, "otm_bounce": False})
    monkeypatch.setattr(retire, "cfg", lambda: cfg)
    v4risk.enable(True)
    assert SP.enabled("fb_or") and not SP.enabled("otm_bounce")
    _tick_at(clock, m1, put_chain, WED, "11:00")
    assert [x["decision"] for x in S.decisions(ledger="otm_bounce", limit=50)] == ["DISABLED"]
    assert not S.positions(ledger="otm_bounce")
    pid, sym, _ = _open("otm_bounce", fill=0.10)                          # an open trade of a switched-off ledger still exits
    book.set(sym, 0.0, 0.01)
    at(clock, WED, "11:05")
    v4index.manage(clock())
    assert S.get(pid)["status"] == "CLOSED" and S.get(pid)["exit_reason"].startswith("FIXED STOP")


# ================================================================ risk book, wiring, report, API, no order path
def test_sprint_book_is_isolated_from_the_existing_ledgers_caps(env):
    for i, led in enumerate(SP.LEDGERS):
        _open(led, sym=f"SPY261104C0060{i}000")
    cap = v4risk.LIMITS["book_max_open"]["sprint"]
    for i in range(cap - len(SP.LEDGERS)):
        S.open_position({"id": f"fb_or:q{i}", "ledger": "fb_or", "book": "sprint", "kind": "option", "date": "2026-11-04",
                         "ticker": f"Q{i}", "direction": "long", "side": "C", "qty": 1, "entry_px": 1.0, "entry_t": "x",
                         "legs": [{"symbol": f"Q{i}", "action": "buy", "qty": 1}], "plan": {"mtm": -250.0}})
    assert v4risk.admit("noise_v2", "index", "SPY", "long") is None                 # 3 sprint SPY trades: index sees none
    assert v4risk.book_pnl_today("index") == 0.0
    assert "sprint book cap" in v4risk.admit("otm_put", "sprint", "QQQ", "short")
    assert "already has an open SPY" in v4risk.admit("fb_or", "sprint", "SPY", "long")
    for i in range(4):
        S.open_position({"id": f"noise_v2:x{i}", "ledger": "noise_v2" if i < 2 else "noise_trend", "book": "index", "kind": "option",
                         "date": "2026-11-04", "ticker": "QQQ" if i % 2 else "IWM", "direction": "long", "side": "C", "qty": 1,
                         "entry_px": 1.0, "entry_t": "x", "legs": [{"symbol": f"I{i}", "action": "buy", "qty": 1}], "plan": {}})
    assert "index book cap" in v4risk.admit("noise_v2", "index", "SPY", "long")
    st = v4risk.status()
    assert st["limits"]["isolated_books"] == ["sprint", "swing", "trend", "pead", "core"] and st["open"]["by_book"]["sprint"] == cap


def test_report_api_and_view_label_the_forward_tests(env):
    clock, book = env
    pid, sym, _ = _open("fb_or")
    at(clock, WED, "10:00")
    book.set(sym, 1.90, 1.94)
    S.close_position(pid, 1.90, "test", 0.65)
    d = v4report.overview("2026-11-02")
    books = {b["book"]: b for b in d["books"]}
    assert list(books) == ["index", "premium", "stocks", "catalyst", "sprint", "swing", "trend", "pead", "core"]
    rows = {r["ledger"]: r for r in books["sprint"]["ledgers"]}
    assert set(rows) == {"fb_or", "otm_put", "otm_bounce", "otm_h"}
    fb = rows["fb_or"]
    assert fb["evidence"] == "PAPER (simulated fills)" and "forward test of an in-sample backtest" in fb["status"]
    assert fb["source_run"] == "setups_v2-012" and fb["backtest"]["trades"] == 429 and fb["backtest"]["expectancy"] == 18.57
    assert fb["trades"] == 1 and fb["by_ticker"]["SPY"]["trades"] == 1 and "QQQ" in fb["by_ticker"]
    assert rows["otm_put"]["backtest"]["profit_factor"] == 1.655 and rows["otm_put"]["source_run"] == "otm_v1-011"
    assert rows["otm_bounce"]["watch_only"] and rows["otm_bounce"]["backtest"]["trades"] == 44
    api = v4api.get("/api/v4/sprint", {})
    assert set(api["ledgers"]) == set(SP.LEDGERS) and api["label"] == "PAPER (simulated fills)" and api["deviations"]
    assert api["ledgers"]["otm_bounce"]["rules"]["run_id"] == "otm_v1-042"
    pid2, sym2, _ = _open("otm_put", side="P", fill=0.4, sym="SPY261104P00590000")
    v = v4api.view(S.get(pid2))
    assert v["label"] == "PAPER (simulated fills)" and v["source_run"] == "otm_v1-011" and v["next"].startswith("fixed stop -95%")
    html = (ROOT / "index.html").read_text()
    assert "l.source_run" in html


def test_index_tick_runs_the_sprint_ledgers_after_the_others(env, monkeypatch):
    clock, book = env
    calls = []
    import ic_20d
    import noise_trend
    import noise_v2
    import orb_credit
    for name, mod in (("noise_v2", noise_v2), ("noise_trend", noise_trend), ("sprint", SP)):
        monkeypatch.setattr(mod, "tick", lambda t, snap, fn, now=None, _n=name: calls.append((_n, t)))
    monkeypatch.setattr(orb_credit, "tick", lambda t, m1, now=None: calls.append(("orb_credit", t)))
    monkeypatch.setattr(ic_20d, "tick", lambda t, now=None: calls.append(("ic_20d", t)))
    m1 = m1_market(WED, {0: 600.0})
    now = at(clock, WED, "10:30")
    v4index.tick("SPY", {"m1": upto(m1, now)}, lambda t, s: ([], None), now)
    assert calls == [("noise_v2", "SPY"), ("noise_trend", "SPY"), ("orb_credit", "SPY"), ("ic_20d", "SPY"), ("sprint", "SPY")]
    calls.clear()
    now = at(clock, WED, "15:20")                                          # no new entries for the others; the sprint
    v4index.tick("SPY", {"m1": upto(m1, now)}, lambda t, s: ([], None), now)   # ledgers still decide their own windows
    assert calls[-1] == ("sprint", "SPY") and ("orb_credit", "SPY") not in calls


def test_tick_ignores_symbols_the_engine_does_not_tick(env):
    clock, book = env
    m1 = _fb_market()
    now = at(clock, WED, "09:53")
    assert SP.tick("IWM", {"m1": upto(m1, now)}, _fb_chain(book), now) is None and not S.decisions(limit=50)


def test_nothing_reaches_a_real_order_path(env, monkeypatch):
    src = (ROOT / "sprint_paper.py").read_text()
    assert not re.search(r"\bimport broker\b|broker\.|/trader|submit\(|place_order|/orders", src)
    for f in sorted((ROOT / "sprint").glob("*.py")):
        assert not re.search(r"\bimport broker\b|broker\.submit|/trader|/orders", f.read_text()), f.name
    import broker
    import schwab

    def boom(*a, **k):
        raise AssertionError("a real order path was called")
    monkeypatch.setattr(broker, "submit", boom)
    monkeypatch.setattr(broker, "_req", boom)
    monkeypatch.setattr(schwab, "_urlopen", boom)
    clock, book = env
    m1 = _fb_market()
    now = at(clock, WED, "09:53")
    SP.tick("SPY", {"m1": upto(m1, now)}, _fb_chain(book), now)
    pos = S.positions(ledger="fb_or")
    assert len(pos) == 1
    at(clock, WED, "15:25")
    book.set(pos[0]["legs"][0]["symbol"], 3.0, 3.1)
    v4index.manage(clock())
    assert S.get(pos[0]["id"])["status"] == "CLOSED"
    no_errors()


def test_production_vixy_source_caches_daily_closes_guards_splits_and_warms_up(env, monkeypatch):
    clock, book = env
    import schwab
    monkeypatch.setattr(SP, "vixy_source", None)
    monkeypatch.setattr(marketdata, "_provider", None)                    # the production path (no injected provider)
    vm = m1_market(WED, {0: 20.0}, prior_days=1, px=20.0, prior_range=0.01)
    calls = {"bars": 0, "daily": 0}
    days = pd.bdate_range(end=pd.Timestamp("2026-11-04"), periods=300)          # includes today's partial candle

    def bars(t):
        calls["bars"] += 1
        assert t == "VIXY"
        return vm[vm.index + pd.Timedelta(minutes=1) <= pd.Timestamp(clock())], None, {}

    def daily(t):
        calls["daily"] += 1
        return pd.DataFrame({"Close": np.linspace(30, 40, len(days))}, index=days)
    monkeypatch.setattr(marketdata, "bars", bars)
    monkeypatch.setattr(schwab, "bars_daily", daily)
    monkeypatch.setitem(SP._state, "vixy_try", 0)
    now = at(clock, WED, "09:50")
    SP._warm_vixy(now)
    SP._warm_vixy(now)                                                     # once a minute at most
    assert calls == {"bars": 1, "daily": 1}
    hist = store.kv_get("sprint_paper:vixy_daily:2026-11-04")
    assert len(hist) == 299 and hist[-1][0] == "2026-11-03"                # closes before today only
    at(clock, WED, "09:51")
    SP._warm_vixy(clock())
    assert calls["daily"] == 1                                             # cached for the day: no more warm-up calls
    v = SP.vixy(clock())
    assert len(v["daily"]) == 299 and v["m1"].index[-1] == pd.Timestamp(datetime(2026, 11, 4, 9, 50, tzinfo=ET))
    split = [[x[0], x[1] * (4.0 if i < 200 else 1.0)] for i, x in enumerate(hist)]   # an unadjusted 1:4 reverse split
    store.kv_set("sprint_paper:vixy_daily:2026-11-04", split)
    v = SP.vixy(clock())
    assert v["daily"] is None and any("split" in n for n in v["notes"])


# ================================================================ otm_h: rule H (otm_v1-040 taken only when f_rvol >= 1.06)
def _h_world(env, day=WED, vol=1.5, prior_days=12, after=None):
    """Calls at 11:00 with f_rvol controlled by today's volume: every regular-hours bar today trades vol x the prior
    sessions' volume (rvol = vol, rounded to 2 decimals). `after` multiplies today's volume from 11:00 on (bars the
    11:00 decision must never see)."""
    clock, book = env
    px = 600.5
    m1 = m1_market(day, {0: px}, prior_days=prior_days)
    t0 = pd.Timestamp(datetime.combine(day, datetime.min.time())).tz_localize(ET)
    rth = (m1.index >= t0 + pd.Timedelta(hours=9, minutes=30)) & (m1.index < t0 + pd.Timedelta(hours=16))
    m1.loc[rth, "Volume"] = m1.loc[rth, "Volume"] * vol
    if after is not None:
        late = rth & (m1.index >= t0 + pd.Timedelta(hours=11))
        m1.loc[late, "Volume"] = m1.loc[late, "Volume"] * after
    return m1, bs_chain(book, day, px, 300, 0.30)


@pytest.mark.parametrize("case,kw,want", [
    ("busy day", {"vol": 1.5}, None),
    ("exactly at the cut", {"vol": 1.06}, None),
    ("just under the cut", {"vol": 1.05}, "f_rvol 1.05 fails rule f_rvol >= 1.06"),
    ("quiet day", {"vol": 0.8}, "fails rule f_rvol >= 1.06"),
    ("too little history", {"vol": 1.5, "prior_days": 6}, "f_rvol unknown"),
])
def test_otm_h_takes_only_busy_days(env, case, kw, want):
    clock, book = env
    m1, chain = _h_world(env, **kw)
    _tick_at(clock, m1, chain, WED, "11:00")
    no_errors()
    d = decisions("otm_h")
    assert len(d) == 1, case
    if want is None:
        assert d[0]["decision"] == "ORDER", (case, d[0]["reasons"])
        p = S.positions(ledger="otm_h")[0]
        k = p["plan"]["contract"]
        assert p["side"] == "C" and 0.03 <= abs(k["delta_bs_est"]) <= 0.12 and k["rule"] == "d03-12t07"
        assert p["plan"]["exit"]["kind"] == "fixed" and p["plan"]["exit"]["fixed_stop"] == 0.95
        fr = p["plan"]["filters"]["feature_rule"]
        assert fr["rules"] == ["f_rvol >= 1.06"] and fr["fail"] is None
        assert fr["values"]["f_rvol"] == p["plan"]["features"]["f_rvol"] == pytest.approx(kw["vol"])
        assert p["plan"]["source_run"] == "otm_v1-040" and "out-of-sample" in p["plan"]["status"]
    else:
        assert d[0]["decision"] == "FILTERED" and want in d[0]["reasons"][0], (case, d[0]["reasons"])
        assert not S.positions(ledger="otm_h")
        assert d[0]["data"]["feature_rule"]["fail"] == d[0]["reasons"][0]


def test_otm_h_rvol_never_sees_bars_after_the_signal(env, monkeypatch, tmp_path):
    """Same bars through 11:00, very different volume afterwards, all of it handed to the ledger: the decision and the
    stamped f_rvol are identical (only finished bars up to the signal bar count). Each world gets a fresh desk."""
    clock, book = env
    got = []
    for k, after in enumerate((None, 0.01, 50.0)):
        monkeypatch.setattr(store, "DB", tmp_path / f"desk{k}.db")
        monkeypatch.setattr(store, "_conn", None)
        SP._cache.clear()
        m1, chain = _h_world(env, vol=1.03, after=after)
        now = at(clock, WED, "11:00")
        SP.tick("SPY", {"m1": m1}, chain, now)                           # full day, future bars included
        d = decisions("otm_h")
        assert len(d) == 1
        got.append((d[0]["decision"], d[0]["data"]["features"]["f_rvol"]))
    assert got == [("FILTERED", 1.03)] * 3


def test_otm_h_other_ledgers_unchanged_and_report_labels(env):
    assert SP.FEATURE_RULES == {"otm_h": (("f_rvol", ">=", 1.06),)}
    for name in ("fb_or", "otm_put", "otm_bounce"):
        assert SP.feature_rule(name, {"f_rvol": 0.1}) is None and SP.status_of(name) == SP.STATUS
    meta = SP.report_meta("otm_h")
    assert meta["source_run"] == "otm_v1-040" and meta["feature_rules"] == ["f_rvol >= 1.06"]
    assert meta["backtest"]["trades"] == 485 and meta["backtest"]["profit_factor"] == 2.352
    assert meta["backtest"]["label"].startswith("BACKTEST out-of-sample")
    assert SP.report_meta("fb_or")["backtest"]["label"] == "BACKTEST in-sample (DEV), MODELED spread"
    assert v4index.LEDGERS["otm_h"] == "sprint" and "otm_h" in v4index.SPRINT and "otm_h" in v4api.SPRINT
    assert "otm_h" in v4report.SPRINT_LEDGERS and "rule H" in v4report.LABELS["otm_h"]
    cfg = json.loads((ROOT / "config/v4.json").read_text())
    assert cfg["sprint_paper"]["otm_h"] is True


def test_otm_h_restart_after_the_decision_never_enters_twice(env):
    clock, book = env
    m1, chain = _h_world(env, vol=1.5)
    _tick_at(clock, m1, chain, WED, "11:00")
    assert len(S.positions(ledger="otm_h")) == 1
    SP._cache.clear()                                                     # a restart: caches gone, the database stays
    for hm, sec in (("11:00", 40), ("11:01", 10), ("11:02", 30)):
        _tick_at(clock, m1, chain, WED, hm, sec=sec)
    assert len(S.positions(ledger="otm_h")) == 1 and len(decisions("otm_h")) == 1
