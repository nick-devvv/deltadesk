"""v4 stage 2: index ledgers noise_v2 / noise_trend and the paper credit-spread ledgers orb_credit / ic_20d.
Rules, edge cases, no look-ahead, restart without double entry. Fake Schwab data only, no network."""
import json
import math
import sys
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
import fakes  # noqa: E402
import ic_20d  # noqa: E402
import marketdata  # noqa: E402
import noise_trend  # noqa: E402
import noise_v2  # noqa: E402
import orb_credit  # noqa: E402
import store  # noqa: E402
import v4common as C  # noqa: E402
import v4index  # noqa: E402
import v4spreads as SP  # noqa: E402
import v4store as S  # noqa: E402

ET = core.ET
WED = datetime(2026, 11, 4, tzinfo=ET)          # not an FOMC day
FOMC = datetime(2026, 10, 28, tzinfo=ET)        # FOMC statement day (config/v4.json list)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    monkeypatch.setattr(noise_trend, "vix_source", lambda now: (None, None, "test: no VIX"))
    engine._cache.clear()
    yield monkeypatch
    marketdata.use(None)


def at(clock, day, hhmm, sec=0):
    clock.t = day.replace(hour=int(hhmm[:2]), minute=int(hhmm[3:]), second=sec)
    engine._cache.clear()
    return clock.t


# ================================================================ a chain fake with real-looking deltas
class ChainFake(fakes.FakeSchwab):
    """Strikes S0-20..S0+20 every $1; call delta = logistic((S-K)/2); mid = intrinsic + time value. Quotes are dated
    `lag` seconds before the clock. tv_mult scales time value (to push a condor's close debit up)."""

    def __init__(self, m1, clock, s0=600.0, lag=0.5):
        super().__init__(m1, clock, s0=s0)
        self.lag, self.tv_mult, self.missing = lag, 1.0, set()

    def _opt(self, side, k):
        s = self.spot()
        cd = 1 / (1 + math.exp(-(s - k) / 2.0))
        intr = max(0.0, s - k) if side == "C" else max(0.0, k - s)
        mid = intr + self.tv_mult * 1.6 * math.exp(-abs(k - s) / 3.0)
        b, a = max(0.01, round(mid - 0.02, 2)), round(mid + 0.02, 2)
        return b, a, (cd if side == "C" else cd - 1)

    def _q(self, symbol):
        side, k = symbol[-9], int(symbol[-8:]) / 1000
        b, a, d = self._opt(side, k)
        return {"bid": b, "ask": a, "last": round((a + b) / 2, 2), "delta": round(d, 3), "gamma": 0.05, "iv": 0.15,
                "quote_time": pd.Timestamp(self.clock()) - pd.Timedelta(seconds=self.lag), "bid_size": 10, "ask_size": 10,
                "multiplier": 100, "src": self.name}

    def option_quote(self, symbol):
        if symbol in self.missing:
            return None, "no quote (test)"
        return self._q(symbol), None

    def option_quotes(self, symbols):
        return {s: self._q(s) for s in symbols if s not in self.missing}, None

    def chain(self, ticker, side, first, through=None):
        root = ticker.replace("$", "")
        rows = []
        for k in range(int(self.s0) - 20, int(self.s0) + 21):
            sym = f"{root}{first[2:4]}{first[5:7]}{first[8:10]}{side[0].upper()}{int(k * 1000):08d}"
            b, a, d = self._opt(side[0].upper(), k)
            rows.append({"symbol": sym, "strike": float(k), "bid": b, "ask": a, "delta": round(d, 3), "exp": first,
                         "ts": (pd.Timestamp(self.clock()) - pd.Timedelta(seconds=self.lag)).isoformat()})
        return rows, None


def chain_world(env, path, day, xsp=False):
    clock = fakes.Clock(day.replace(hour=9, minute=30))
    env.setattr(core, "now_et", clock)
    m1 = fakes.make_market(path, day, prior_days=16)
    fk = ChainFake(m1, clock)
    if not xsp:
        real = fk.chain
        fk.chain = lambda t, side, first, through=None: (None, "empty chain") if t.startswith("$") else real(t, side, first, through)
    marketdata.use(fk)
    return clock, fk


def orb_path(day, brk="up", brk_min=641):
    def p(ts):
        m = ts.hour * 60 + ts.minute
        if ts.date() != day.date():
            return fakes.prior_path(ts.day, m, np.random.default_rng(ts.day))
        if m < 570:
            return 600.0
        if m < 630:
            return 600.0 + 0.8 * math.sin((m - 570) / 5.0)
        if m < brk_min:
            return 600.2
        return 601.9 if brk == "up" else 598.1
    return p


def m1_now(fk):
    return fk.bars_1m("SPY")


# ================================================================ orb_credit
def test_orb_credit_put_spread_after_an_upside_break(env):
    clock, fk = chain_world(env, orb_path(WED), WED)
    at(clock, WED, "10:30", 5)
    assert orb_credit.tick("SPY", m1_now(fk), clock()) is None                  # range set, no break yet
    orr = orb_credit.opening_range(C.rth_day(m1_now(fk), WED.date()))
    assert orr and orr["width_pct"] >= 0.002
    at(clock, WED, "10:42", 0)                                                  # the 10:41 bar just finished
    assert orb_credit.tick("SPY", m1_now(fk), clock()) is None                  # quotes dated before signal+latency: wait
    at(clock, WED, "10:42", 30)
    assert orb_credit.tick("SPY", m1_now(fk), clock()) == "ORDER"
    p = S.positions(ledger="orb_credit")[0]
    short, long_ = p["legs"]
    assert short["action"] == "sell" and short["right"] == "P" and short["strike"] == math.floor(orr["low"])
    assert long_["strike"] == short["strike"] - 2 and p["direction"] == "long"
    assert p["entry_px"] == pytest.approx(short["bid"] - long_["ask"], abs=1e-6)          # shorts at bid - longs at ask
    assert p["fees"] == pytest.approx(1.30) and p["max_loss"] == pytest.approx((2 - p["entry_px"]) * 100 + 2.60, abs=0.01)
    assert p["signal_t"].startswith("2026-11-04T10:42")
    at(clock, WED, "11:30")                                                     # one trade per symbol per day
    assert orb_credit.tick("SPY", m1_now(fk), clock()) is None
    assert len(S.positions(ledger="orb_credit")) == 1
    at(clock, WED, "15:25", 2)
    orb_credit.manage(S.positions(ledger="orb_credit", status="OPEN")[0], clock())
    c = S.get(p["id"])
    qs = fk.option_quotes([l["symbol"] for l in p["legs"]])[0]
    debit = qs[short["symbol"]]["ask"] - qs[long_["symbol"]]["bid"]
    assert c["status"] == "CLOSED" and "ALL OUT" in c["exit_reason"] and c["exit_px"] == pytest.approx(debit, abs=1e-6)
    assert c["realized"] == pytest.approx((p["entry_px"] - debit) * 100 - 2.60, abs=0.01)


def test_orb_credit_call_spread_after_a_downside_break(env):
    clock, fk = chain_world(env, orb_path(WED, "down"), WED)
    at(clock, WED, "10:43")
    assert orb_credit.tick("SPY", m1_now(fk), clock()) == "ORDER"
    p = S.positions(ledger="orb_credit")[0]
    orr = orb_credit.opening_range(C.rth_day(m1_now(fk), WED.date()))
    assert p["legs"][0]["right"] == "C" and p["legs"][0]["strike"] == math.ceil(orr["high"])
    assert p["legs"][1]["strike"] == p["legs"][0]["strike"] + 2 and p["direction"] == "short"


def test_orb_credit_skips_narrow_ranges_late_breaks_and_fomc_days(env):
    def flat(ts):
        m = ts.hour * 60 + ts.minute
        if ts.date() != WED.date():
            return fakes.prior_path(ts.day, m, np.random.default_rng(ts.day))
        return 600.0 + (0.3 if m >= 700 else 0.0)              # width ~0.06 + 0.06 wicks: under 0.2%
    clock, fk = chain_world(env, flat, WED)
    at(clock, WED, "10:31")
    assert orb_credit.tick("SPY", m1_now(fk), clock()) == "SKIP"
    assert "under 0.2%" in S.decisions(ledger="orb_credit")[0]["reasons"][0]
    # a break that finishes after 12:00 is no signal
    env.setattr(store, "_conn", None)
    env.setattr(store, "DB", Path(str(store.DB) + "2"))
    clock2, fk2 = chain_world(env, orb_path(WED, "up", brk_min=721), WED)
    at(clock2, WED, "12:01", 10)
    assert orb_credit.tick("SPY", m1_now(fk2), clock2()) == "NO TRADE"
    # FOMC day: blocked by the risk layer
    env.setattr(store, "_conn", None)
    env.setattr(store, "DB", Path(str(store.DB) + "3"))
    clock3, fk3 = chain_world(env, orb_path(FOMC), FOMC)
    at(clock3, FOMC, "10:43")
    assert orb_credit.tick("SPY", m1_now(fk3), clock3()) == "BLOCKED-RISK"
    assert "FOMC" in S.decisions(ledger="orb_credit")[0]["reasons"][0]


def test_orb_credit_signal_ignores_future_bars(env):
    clock, fk = chain_world(env, orb_path(WED), WED)
    at(clock, WED, "10:50")
    m1 = m1_now(fk)
    today = C.rth_day(m1, WED.date())
    a = orb_credit.first_break(today, orb_credit.opening_range(today), clock())
    fut = fk.m1.copy()
    fut.loc[fut.index > pd.Timestamp(clock()), ["Open", "High", "Low", "Close"]] = 500.0     # rewrite the future
    fk.m1 = fut
    today2 = C.rth_day(m1_now(fk), WED.date())
    assert orb_credit.first_break(today2, orb_credit.opening_range(today2), clock()) == a


def test_orb_credit_restart_never_enters_twice(env):
    clock, fk = chain_world(env, orb_path(WED), WED)
    at(clock, WED, "10:43")
    assert orb_credit.tick("SPY", m1_now(fk), clock()) == "ORDER"
    S._ready["db"] = None                                     # a restart: fresh module state, same database
    engine._cache.clear()
    for sec in (0, 20, 40):
        at(clock, WED, "10:44", sec)
        orb_credit.tick("SPY", m1_now(fk), clock())
    assert len(S.positions(ledger="orb_credit")) == 1
    pid, why = S.open_position({"id": S.positions(ledger="orb_credit")[0]["id"], "ledger": "orb_credit", "kind": "spread"})
    assert pid is None and "never opens twice" in why


def test_orb_credit_waits_for_quotes_after_the_signal_then_records_missed(env):
    clock, fk = chain_world(env, orb_path(WED), WED)
    fk.lag = 600                                              # every quote is 10 minutes old
    for hhmm in ("10:42", "10:44", "10:46", "10:47"):
        at(clock, WED, hhmm, 0)
        orb_credit.tick("SPY", m1_now(fk), clock())
    assert not S.positions(ledger="orb_credit")
    d = S.decisions(ledger="orb_credit")[0]
    assert d["decision"] == "MISSED"


# ================================================================ ic_20d
def flat_path(day):
    def p(ts):
        m = ts.hour * 60 + ts.minute
        if ts.date() != day.date():
            return fakes.prior_path(ts.day, m, np.random.default_rng(ts.day))
        return 600.0 + 0.2 * math.sin(m / 7.0)
    return p


def test_ic_20d_legs_credit_and_two_x_stop(env):
    clock, fk = chain_world(env, flat_path(WED), WED)
    at(clock, WED, "10:00", 0)
    assert ic_20d.tick("SPY", clock()) is None                                  # quotes not yet after 10:00:01
    at(clock, WED, "10:00", 30)
    assert ic_20d.tick("SPY", clock()) == "ORDER"
    p = S.positions(ledger="ic_20d")[0]
    sc, lc, sp, lp = p["legs"]
    calls, _ = SP.chain("SPY", "C", WED.date())
    best = min((r for r in calls), key=lambda r: abs(abs(r["delta"]) - 0.20))
    assert sc["strike"] == best["strike"] and lc["strike"] == sc["strike"] + 2 and lp["strike"] == sp["strike"] - 2
    assert sc["action"] == sp["action"] == "sell" and lc["action"] == lp["action"] == "buy"
    assert p["entry_px"] == pytest.approx(sc["bid"] + sp["bid"] - lc["ask"] - lp["ask"], abs=1e-6)
    assert p["fees"] == pytest.approx(2.60) and p["direction"] == "neutral"
    at(clock, WED, "10:30")
    ic_20d.manage(p, clock())
    assert S.get(p["id"])["status"] == "OPEN"
    fk.tv_mult = 4.0                                                            # time value jumps: debit >= 2x credit
    at(clock, WED, "10:31")
    ic_20d.manage(S.get(p["id"]), clock())
    c = S.get(p["id"])
    assert c["status"] == "CLOSED" and c["exit_reason"].startswith("STOP: close debit") and c["exit_px"] >= 2 * p["entry_px"]


def test_ic_20d_fomc_skip_missed_window_and_all_out(env):
    clock, fk = chain_world(env, flat_path(FOMC), FOMC)
    at(clock, FOMC, "10:01")
    assert ic_20d.tick("SPY", clock()) == "BLOCKED-RISK"
    env.setattr(store, "_conn", None)
    env.setattr(store, "DB", Path(str(store.DB) + "2"))
    clock, fk = chain_world(env, flat_path(WED), WED)
    at(clock, WED, "10:20")
    assert ic_20d.tick("SPY", clock()) == "MISSED"
    env.setattr(store, "_conn", None)
    env.setattr(store, "DB", Path(str(store.DB) + "3"))
    clock, fk = chain_world(env, flat_path(WED), WED)
    at(clock, WED, "10:01")
    assert ic_20d.tick("SPY", clock()) == "ORDER"
    fk.missing = {S.positions(ledger="ic_20d")[0]["legs"][0]["symbol"]}         # one leg loses its quote at the close
    at(clock, WED, "15:25", 1)
    ic_20d.manage(S.positions(ledger="ic_20d", status="OPEN")[0], clock())
    p = S.positions(ledger="ic_20d")[0]
    assert p["status"] == "OPEN" and p["plan"]["pending_exit"]["reason"].startswith("ALL OUT")       # never invented
    fk.missing = set()
    at(clock, WED, "15:25", 30)
    ic_20d.manage(S.positions(ledger="ic_20d", status="OPEN")[0], clock())
    p = S.positions(ledger="ic_20d")[0]
    assert p["status"] == "CLOSED" and p["exit_reason"].startswith("ALL OUT")


# ================================================================ XSP availability
def test_xsp_not_available_is_logged_once_and_skipped(env):
    clock, fk = chain_world(env, flat_path(WED), WED, xsp=False)
    for hhmm in ("10:00", "10:01", "10:02"):
        at(clock, WED, hhmm, 30)
        v4index.tick_extra(clock())
    rows = [d for d in S.decisions() if d["ticker"] == "XSP"]
    assert len(rows) == 1 and rows[0]["decision"] == "NOT AVAILABLE"
    assert len(store.q("SELECT seq FROM events WHERE text LIKE 'XSP not available%'")) == 1
    assert not S.positions()


def test_xsp_runs_when_schwab_lists_it(env):
    clock, fk = chain_world(env, flat_path(WED), WED, xsp=True)
    at(clock, WED, "10:01")
    v4index.tick_extra(clock())
    p = S.positions(ledger="ic_20d")
    assert p and p[0]["ticker"] == "XSP" and p[0]["legs"][0]["symbol"].startswith("XSP")


# ================================================================ noise_v2 / noise_trend
def noise_world(env, path, day=WED):
    clock, fk = fakes.install(env, path, day, s0=600.0, prior_days=16, delta=0.6)
    return clock, fk


def trend_path(day, fade=True):
    def p(ts):
        m = ts.hour * 60 + ts.minute
        if ts.date() != day.date():
            return fakes.prior_path(ts.day, m, np.random.default_rng(ts.day))
        if m < 575:
            return 600.0
        if m < 601:
            return 600.0 + (m - 575) * 0.12                    # 602.9 at 10:00 (above the band)
        if not fade:
            return 603.1
        if m < 615:
            return 603.1 - (m - 601) * 0.12                    # 601.4 by 10:14: noise's 20% line is hit
        return max(599.0, 601.4 - (m - 615) * 0.15)            # 599 by 10:31: below -50% on the bid
    return p


def run_engine(clock, day, a, b):
    t = day.replace(hour=int(a[:2]), minute=int(a[3:]))
    stop = day.replace(hour=int(b[:2]), minute=int(b[3:]))
    while t <= stop:
        clock.t = t
        engine._cache.clear()
        engine.tick()
        t += timedelta(minutes=1)


def test_noise_v2_takes_noise_entries_and_holds_through_the_20pct_line(env):
    clock, fk = noise_world(env, trend_path(WED))
    run_engine(clock, WED, "09:58", "10:17")
    noise = store.positions(ledger="noise")
    v2 = S.positions(ledger="noise_v2", ticker=None) if False else S.positions(ledger="noise_v2")
    assert noise and v2 and {p["ticker"] for p in v2} == {"SPY", "QQQ"}
    spy_n = [p for p in noise if p["ticker"] == "SPY"][0]
    spy_2 = [p for p in v2 if p["ticker"] == "SPY"][0]
    assert spy_2["side"] == spy_n["side"] == "C" and spy_2["legs"][0]["symbol"] == spy_n["symbol"]
    assert spy_2["entry_px"] == spy_n["fill"] and spy_2["exec_model"] == "noise1"             # same fill model as noise
    assert spy_n["status"] == "CLOSED" and "PREMIUM STOP" in spy_n["plan"]["exit_reason"]      # noise: 20% line
    assert spy_2["status"] == "OPEN" and spy_2["plan"]["premium_stop"] == core.cents_down(spy_2["entry_px"] * 0.5)
    run_engine(clock, WED, "10:18", "10:29")
    spy_2 = S.get(spy_2["id"])
    assert spy_2["status"] == "CLOSED" and "-50% disaster stop" in spy_2["exit_reason"]


def test_noise_v2_exits_at_the_check_only(env):
    def p(ts):
        m = ts.hour * 60 + ts.minute
        if ts.date() != WED.date():
            return fakes.prior_path(ts.day, m, np.random.default_rng(ts.day))
        if m < 575:
            return 600.0
        if m < 601:
            return 600.0 + (m - 575) * 0.12
        return 602.2                                             # between the bands' stop and the 20% line
    clock, fk = noise_world(env, p)
    run_engine(clock, WED, "09:58", "10:03")
    pos = S.positions(ledger="noise_v2", status="OPEN")
    assert pos
    data = store.kv_get(f"noise_v2:SPY:{pd.Timestamp(WED.replace(hour=10, minute=30)).isoformat()}:state")
    assert data is None                                         # no check decided yet at 10:03
    run_engine(clock, WED, "10:29", "10:31")
    st = store.kv_get(f"noise_v2:SPY:{pd.Timestamp(WED.replace(hour=10, minute=30)).isoformat()}:state")
    spy = [x for x in S.positions(ledger="noise_v2") if x["ticker"] == "SPY"][0]
    stop = max(st["upper"], st["vwap"])
    assert (spy["status"] == "CLOSED") == (st["price"] < stop)
    if spy["status"] == "CLOSED":
        assert spy["exit_reason"].startswith("NOISE STOP at 10:30")


def test_noise_trend_score_records_every_check_and_needs_two_known_true(env):
    clock, fk = noise_world(env, trend_path(WED, fade=False))
    run_engine(clock, WED, "09:58", "10:02")
    chk = [d for d in S.decisions(ledger="noise_trend", kind="check")]
    assert {d["ticker"] for d in chk} == {"SPY", "QQQ"}
    f = chk[0]["data"]["filter"]
    assert f["conditions"]["a_vix_above_median"] is None                         # unknown, never counted
    assert f["conditions"]["d_macro_day"] is None          # no events.json: not FOMC (2026 list) but CPI/jobs unknown
    assert f["known"] == 2
    assert f["trade"] == (f["true"] >= 2)
    ent = [d for d in S.decisions(ledger="noise_trend", kind="entry")]
    assert ent and all(d["decision"] in ("ORDER", "FILTERED") for d in ent)
    assert bool([d for d in ent if d["decision"] == "ORDER"]) == f["trade"]


def test_noise_trend_conditions_and_unknowns(env, tmp_path):
    clock, fk = noise_world(env, trend_path(WED, fade=False))
    at(clock, WED, "10:00", 30)
    m1 = engine.snapshot("SPY")["m1"]
    noise_trend.vix_source = lambda now: (30.0, 20.0, "test")
    try:
        s = noise_trend.score(m1, WED.date(), clock())
        assert s["conditions"]["a_vix_above_median"] is True
        core.EVENTS_FILE.write_text(json.dumps({"date": "2026-11-04", "events": [{"time": "08:30", "name": "CPI"}]}))
        s2 = noise_trend.score(m1, WED.date(), clock())
        assert s2["conditions"]["d_macro_day"] is True and s2["true"] >= 2 and s2["trade"]
        noise_trend.vix_source = lambda now: (15.0, 20.0, "test")
        core.EVENTS_FILE.write_text(json.dumps({"date": "2026-11-04", "events": []}))
        s3 = noise_trend.score(m1, WED.date(), clock())
        assert s3["conditions"]["a_vix_above_median"] is False and s3["conditions"]["d_macro_day"] is False
        assert s3["known"] == 4
    finally:
        noise_trend.vix_source = lambda now: (None, None, "test: no VIX")


def test_noise_trend_score_has_no_look_ahead(env):
    clock, fk = noise_world(env, trend_path(WED, fade=False))
    at(clock, WED, "10:00", 30)
    m1 = engine.snapshot("SPY")["m1"]
    a = noise_trend.score(m1, WED.date(), clock())
    full = fk.m1.copy()
    full.loc[full.index >= pd.Timestamp(WED.replace(hour=10, minute=0)), "Volume"] *= 50     # change everything after 10:00
    full.loc[full.index >= pd.Timestamp(WED.replace(hour=10, minute=0)), ["Open", "High", "Low", "Close"]] += 9
    b = noise_trend.score(full, WED.date(), clock())
    assert a["conditions"] == b["conditions"] and a["inputs"]["first_half_hour"] == b["inputs"]["first_half_hour"]


def test_noise_variants_restart_without_double_entry(env):
    clock, fk = noise_world(env, trend_path(WED, fade=False))
    run_engine(clock, WED, "09:58", "10:02")
    n = len(S.positions(ledger="noise_v2"))
    assert n == 2
    S._ready["db"] = None
    for sec in (0, 15, 45):
        at(clock, WED, "10:02", sec)
        v4index.tick("SPY", engine.snapshot("SPY"), engine.chain_rows, clock())
    assert len(S.positions(ledger="noise_v2")) == n
    assert len([d for d in S.decisions(ledger="noise_v2", kind="check") if d["ticker"] == "SPY"]) == 1


def test_entry_retries_requote_legs_without_refetching_chains(env):
    clock, fk = chain_world(env, orb_path(WED), WED)
    calls = []
    real = fk.chain
    fk.chain = lambda t, side, first, through=None: (calls.append((t, side)), real(t, side, first, through))[1]
    fk.lag = 600                                              # quotes too old: the entry keeps waiting
    for sec in (0, 10, 20, 30, 40):
        at(clock, WED, "10:42", sec)
        orb_credit.tick("SPY", m1_now(fk), clock())
    assert len(calls) == 1                                    # legs picked once, then only re-quoted
    fk.lag = 0.5
    at(clock, WED, "10:43", 0)
    assert orb_credit.tick("SPY", m1_now(fk), clock()) == "ORDER" and len(calls) == 1
