"""v3.1 tests: research variants (v3.1 exits, noise band), the stocks-in-play scanner and its options checks, live
market alerts, guidance on Nick's own trades, diagnostics. No network, no AI: fake Schwab data throughout."""
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
import alerts  # noqa: E402
import core  # noqa: E402
import diagnostics  # noqa: E402
import engine  # noqa: E402
import exits  # noqa: E402
import fakes  # noqa: E402
import marketdata  # noqa: E402
import noiseband  # noqa: E402
import paper  # noqa: E402
import scanner  # noqa: E402
import store  # noqa: E402
import test_v3 as T  # noqa: E402

ET = core.ET
DAY = T.DAY                      # Wed 2026-10-28


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    engine._cache.clear()
    yield monkeypatch
    marketdata.use(None)
    scanner.use(None)
    scanner._state.update(cache={}, last_minute=None, pulse={})


def alert_texts():
    return [e["text"] for e in store.q("SELECT text FROM events WHERE kind='alert' ORDER BY seq")]


# ================================================================ v3.1 exits (research variant exit31)
def _open31(clock, fk, qty=2, t1_px=600.5, t1_level=600.6, stop_px=599.0, ledger="exit31"):
    plan = {"symbol": "SPY261028C00600000", "label": "600C", "premium_stop": 1.64, "stop_px": stop_px, "t1": "PDH",
            "t1_level": t1_level, "t1_px": t1_px, "be_trigger": 2.27, "breakeven_net": 2.07, "family": "TEST",
            "exit_profile": "v31", "variant": "exit31", "policy_version": "2026-10-30.v3.1-exit31",
            "flat_by": (clock() + timedelta(minutes=15)).strftime("%H:%M")}
    idea = f"X31-{clock().strftime('%H%M%S')}"
    paper.reserve_idea(ledger, idea, "SPY", "C")
    pid, why = paper.buy(ledger, idea, "SPY", "C", plan, qty, clock().isoformat())
    assert pid, why
    return pid


def test_v31_exits_give_room_before_t1_then_sell_one_and_trail_the_runner(env):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    T.at(clock, 10, 0)
    pid = _open31(clock, fk)
    p = store.pos_get(pid)
    assert p["policy_version"] == "2026-10-30.v3.1-exit31" and p["plan"]["exit_profile"] == "v31" and p["ledger"] == "exit31"
    T.setpx(fk, clock, 600.3)                        # green, then flat for 12 minutes: v3 would stall-exit, v3.1 holds
    for mm in range(1, 13):
        T.at(clock, 10, mm)
        assert not exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"]), mm
    T.setpx(fk, clock, 600.6)                        # T1 reached on a 1m close
    T.at(clock, 10, 14)
    acts = exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
    p = store.pos_get(pid)
    assert acts and "sell 1 of 2, trail the rest (v3.1)" in acts[0][2] and p["qty_open"] == 1
    assert p["plan"]["runner"] and p["plan"]["premium_stop"] >= p["plan"]["breakeven_net"]
    T.setpx(fk, clock, 601.2)                        # the runner keeps going
    for mm in range(15, 18):
        T.at(clock, 10, mm)
        exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
    assert store.pos_get(pid)["status"] == "OPEN"
    T.setpx(fk, clock, 599.9)                        # a 1m close back through the trail
    T.at(clock, 10, 19)
    acts = exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
    assert acts and acts[0][2].startswith(("TRAIL (v3.1)", "BREAKEVEN STOP", "LOCKED-PROFIT STOP"))
    assert store.pos_get(pid)["status"] == "CLOSED"


def test_v31_if_flat_waits_15_minutes_and_one_contract_becomes_a_runner(env):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    T.at(clock, 10, 0)
    pid = _open31(clock, fk, qty=1)
    T.at(clock, 10, 6)                                # v3 would be out on if-flat by now
    assert not exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
    T.at(clock, 10, 15)
    acts = exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
    assert acts and "IF FLAT: never green" in acts[0][2]
    store.x("DELETE FROM ideas")
    T.at(clock, 10, 20)
    pid = _open31(clock, fk, qty=1)
    T.setpx(fk, clock, 600.6)
    T.at(clock, 10, 22)
    acts = exits.evaluate(store.pos_get(pid), engine.snapshot("SPY")["v3"])
    p = store.pos_get(pid)
    assert not acts and p["plan"]["runner"] and p["status"] == "OPEN"     # 1 contract: not sold at T1 in v3.1


def test_research_entries_are_mirrored_into_the_v31_exit_ledger(env):
    clock, fk = fakes.install(env, T.vm_path, DAY, s0=600.0)
    T.run(clock, "09:31", "10:20")
    res = store.positions(ledger="research")
    mir = store.positions(ledger="exit31")
    assert res and mir
    by_idea = {p["setup_id"]: p for p in res}
    for m in mir:
        r = by_idea[m["setup_id"]]
        assert m["symbol"] == r["symbol"] and m["fill"] == r["fill"] and m["opened"] == r["opened"]     # same entry
        assert m["plan"]["exit_profile"] == "v31" and m["policy_version"].endswith("v3.1-exit31")
    assert not [p for p in store.positions(ledger="paper") if p["plan"].get("exit_profile") == "v31"]    # main untouched


# ================================================================ noise band
def test_noise_band_math_matches_the_published_rules():
    idx, px = [], []
    days = pd.bdate_range("2026-10-06", "2026-10-28")
    for d in days:
        for i in range(390):
            ts = pd.Timestamp(d.date()).tz_localize(ET) + timedelta(hours=9, minutes=30 + i)
            idx.append(ts)
            px.append(100 + (0.5 if i >= 20 else 0.0) * (1 if d.day % 2 else -1))   # +-0.5% from the bar opened 09:50
    m1 = pd.DataFrame({"Open": px, "High": px, "Low": px, "Close": px, "Volume": 1000.0}, index=pd.DatetimeIndex(idx))
    day = days[-1].date()
    prof, n = noiseband.sigma_profile(m1, day, 14, 10)
    assert n == 14 and prof.loc[20] == pytest.approx(0.0) and prof.loc[21] == pytest.approx(0.005) and prof.loc[30] == pytest.approx(0.005)
    b = noiseband.bands(m1, day, pd.Timestamp(f"{day} 10:00", tz=ET))
    base = max(float(m1[m1.index.date == day]["Open"].iloc[0]), float(m1[m1.index.date == days[-2].date()]["Close"].iloc[-1]))
    assert b["upper"] == pytest.approx(base * (1 + 0.005), rel=1e-6) and b["sessions"] == 14
    assert [t.strftime("%H:%M") for t in noiseband.check_times(day)][:3] == ["10:00", "10:30", "11:00"]


def test_noise_ledger_trades_only_at_half_hour_checks_with_its_own_version(env):
    def path(ts):
        m = ts.hour * 60 + ts.minute
        if ts.date() != DAY.date():
            return fakes.prior_path(ts.day, m, np.random.default_rng(ts.day))
        return 600.0 if m < 575 else 600.0 + (m - 575) * 0.12       # a steady trend day from 09:35
    clock, fk = fakes.install(env, path, DAY, s0=600.0, prior_days=16, delta=0.6)     # a delta-0.60 contract exists
    T.run(clock, "09:31", "10:06")
    pos = store.positions(ledger="noise")
    assert pos and pos[0]["side"] == "C" and pos[0]["opened"][11:16] in ("10:00", "10:01")
    assert pos[0]["policy_version"] == noiseband.VERSION and pos[0]["setup"] == "NOISE_BAND"
    assert 0.55 <= abs(pos[0]["plan"]["delta_entry"] or 0.6) <= 0.75 or pos[0]["plan"]["delta_entry"] is None
    assert sorted(p["ticker"] for p in pos) == ["QQQ", "SPY"]      # one per ticker, no new entry between checks
    assert not store.positions(ledger="paper", status="OPEN") or all(p["setup"] != "NOISE_BAND" for p in store.positions(ledger="paper"))


# ================================================================ scanner (fake Schwab)
class StockProv(marketdata.Provider):
    """Executable fake for single-stock option quotes (whatever the test puts in .q)."""
    name = "Schwab (fake stocks)"
    executable = True

    def __init__(self, clock):
        self.clock, self.q, self.px = clock, {}, {}

    def bars_1m(self, t):
        return None

    def quote(self, t):
        return {"last": self.px.get(t, 100.0), "bid": None, "ask": None, "quote_time": pd.Timestamp(self.clock()), "src": self.name}

    def option_quote(self, sym):
        if sym not in self.q:
            return None, "no quote"
        b, a = self.q[sym]
        return {"bid": b, "ask": a, "delta": 0.6, "quote_time": pd.Timestamp(self.clock()) - pd.Timedelta(seconds=1),
                "src": self.name, "multiplier": 100}, None


def _stock_m1(day, level, today_fn, open_vol, normal_vol=50_000.0, days=14):
    idx, px, vol = [], [], []
    for d in pd.bdate_range(end=pd.Timestamp(day) - timedelta(days=1), periods=days):
        for i in range(390):
            idx.append(pd.Timestamp(d.date()).tz_localize(ET) + timedelta(hours=9, minutes=30 + i))
            px.append(level * (1 + 0.004 * math.sin(i / 30 + d.day)))
            vol.append(normal_vol * (3 if i < 5 else 1))
    for i in range(390):
        ts = pd.Timestamp(day.date()).tz_localize(ET) + timedelta(hours=9, minutes=30 + i)
        idx.append(ts)
        px.append(today_fn(i, level))
        vol.append(normal_vol * 3 * open_vol if i < 5 else normal_vol * (6 if 15 <= i < 20 else 1))
    c = np.array(px)
    o = np.r_[c[0], c[:-1]]
    di = pd.DatetimeIndex(idx)
    first = np.r_[True, di.date[1:] != di.date[:-1]]
    o[first] = c[first]                                  # each session opens where its first minute closes (no gap)
    return pd.DataFrame({"Open": o, "High": np.maximum(o, c) + 0.02, "Low": np.minimum(o, c) - 0.02, "Close": c, "Volume": vol},
                        index=di)


class FakeFetch:
    def __init__(self, clock, m1s, chains, earnings=None, movers=None):
        self.clock, self.m1s, self.chains, self.er, self.mv = clock, m1s, chains, earnings or {}, movers or {}
        self.ok = True

    def ready(self):
        return self.ok

    def daily(self, t):
        r = self.m1s[t].between_time("09:30", "15:59")
        d = r.resample("1D").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
        d.index = d.index.tz_localize(None)
        d = d[d.index.date < self.clock().date()]
        extra = pd.DataFrame({c: d[c].iloc[:1].values.repeat(20) for c in d.columns},
                             index=pd.date_range(end=d.index[0] - timedelta(days=1), periods=20))
        return pd.concat([extra, d])

    def m5(self, t, start, end):
        r = self.m1s[t].between_time("09:30", "15:59")
        r = r[r.index < end]
        return r.resample("5min").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()

    def m1_today(self, t, day):
        m = self.m1s[t]
        return m[(m.index.date == day) & (m.index + timedelta(minutes=1) <= pd.Timestamp(self.clock()))]

    def quotes(self, ts):
        out = {}
        for t in ts:
            m = self.m1_today(t, self.clock().date())
            if len(m):
                out[t] = {"last": float(m["Close"].iloc[-1]), "open": float(m["Open"].iloc[0]), "volume": float(m["Volume"].sum())}
        return out, None

    def movers(self, idx, sort):
        return self.mv.get(sort, []), None

    def chain(self, t, side, first, through, strikes):
        return [dict(r, ts=r.get("ts") or self.clock().isoformat()) for r in self.chains.get((t, side), [])], None

    def earnings(self, t):
        return self.er.get(t), "test calendar"


def _scanner_world(env):
    clock = fakes.Clock(DAY.replace(hour=9, minute=35, second=25))
    env.setattr(core, "now_et", clock)
    up = lambda i, lv: lv * (1 + 0.0005 * i if i < 5 else 1.0025 + 0.0012 * (i - 5)) if i < 60 else lv * 1.07
    down = lambda i, lv: lv * (1 - 0.0005 * i if i < 5 else 0.9975 - 0.0002 * (i - 5))
    flat = lambda i, lv: lv * (1 + 0.0004 * math.sin(i))
    m1s = {"NVDA": _stock_m1(DAY, 140.0, up, open_vol=4.0), "AMD": _stock_m1(DAY, 160.0, down, open_vol=2.0),
           "AAPL": _stock_m1(DAY, 230.0, flat, open_vol=0.8), "CHEAP": _stock_m1(DAY, 9.0, up, open_vol=5.0, normal_vol=300_000),
           "TSLA": _stock_m1(DAY, 250.0, flat, open_vol=0.9)}
    row = lambda sym, exp, b, a, d, oi=2000, v=800, th=-0.25: {"symbol": sym, "exp": exp, "strike": float(sym[-8:]) / 1000, "bid": b, "ask": a,
                                                                "delta": d, "theta": th, "iv": 0.5, "oi": oi, "volume": v, "ts": None}
    chains = {("NVDA", "C"): [row("NVDA261030C00140000", "2026-10-30", 3.00, 3.30, 0.55),           # 2 DTE: spread 9.5% -> rejected
                              row("NVDA261106C00140000", "2026-11-06", 4.90, 5.00, 0.58),           # best
                              row("NVDA261106C00135000", "2026-11-06", 7.90, 8.10, 0.72),           # delta too high
                              row("NVDA261113C00140000", "2026-11-13", 6.00, 6.10, 0.57)],          # 16 DTE: outside 0-10
              ("AMD", "P"): [row("AMD261106P00160000", "2026-11-06", 4.00, 4.08, -0.55)]}           # expires after earnings
    f = FakeFetch(clock, m1s, chains, earnings={"AMD": "2026-11-04"})
    scanner.use(f)
    env.setattr(scanner, "universe", lambda: ["NVDA", "AMD", "AAPL", "CHEAP", "TSLA"])
    prov = StockProv(clock)
    marketdata.use(prov)
    return clock, f, prov


def test_scanner_ranks_stocks_in_play_with_reasons_and_alerts(env):
    clock, f, prov = _scanner_world(env)
    scanner.step(clock())
    rows = {r["ticker"]: r for r in scanner._rows(str(DAY.date()))}
    assert rows["NVDA"]["rank"] == 1 and rows["NVDA"]["rvol"] == pytest.approx(4.0, rel=0.05) and rows["NVDA"]["direction"] == "C"
    assert rows["AMD"]["rank"] == 2 and rows["AMD"]["direction"] == "P" and rows["AMD"]["earnings"] == "2026-11-04"
    assert "opening volume 0.8x normal" in rows["AAPL"]["status"]
    assert "price under $20" in rows["CHEAP"]["status"]
    assert any(a.startswith("IN PLAY 09:35: NVDA 4.0x") and "not validated setups" in a for a in alert_texts())
    f.ok = False
    scanner._state["status"] = ""
    scanner.step(clock())
    assert scanner._state["status"].startswith("waiting for Schwab")        # never scans on delayed data


def test_contract_scoring_checks_liquidity_across_expirations():
    now = DAY.replace(hour=10)
    ts = now.isoformat()
    mk = lambda exp, b, a, d, oi=2000, v=800, t=ts, th=-0.2: {"symbol": f"X{exp}{b}", "exp": exp, "bid": b, "ask": a, "delta": d, "theta": th,
                                                               "oi": oi, "volume": v, "ts": t}
    rows = [mk("2026-10-28", 2.00, 2.30, 0.6),                  # same day but 14% wide
            mk("2026-10-30", 3.00, 3.05, 0.6, th=-1.5),         # tight but heavy decay
            mk("2026-11-06", 4.00, 4.06, 0.6, th=-0.30),        # tight, slow decay -> best
            mk("2026-11-06", 4.00, 4.06, 0.6, oi=10),           # no open interest
            mk("2026-11-06", 4.00, 4.06, 0.6, t=(now - timedelta(minutes=5)).isoformat()),   # stale quote
            mk("2026-11-06", 4.00, 4.06, 0.85)]                 # delta outside 0.50-0.70
    best, top, rej = scanner.score_contracts(rows, "C", now)
    assert best["exp"] == "2026-11-06" and best["decay_pct"] < top[1]["decay_pct"]       # nearest expiry is not assumed
    assert rej == {"spread too wide": 1, "open interest too low": 1, "stale or missing quote time": 1, "delta outside range": 1}
    best, _, rej = scanner.score_contracts(rows, "C", now, earnings="2026-11-02")
    assert best["exp"] == "2026-10-30" and rej.get("expires after earnings", 0) >= 1                         # event risk


def test_inplay_breakout_trades_on_paper_with_live_quote_and_atr_stop(env):
    clock, f, prov = _scanner_world(env)
    scanner.step(clock())
    prov.q["NVDA261106C00140000"] = (4.90, 5.00)
    clock.t = DAY.replace(hour=9, minute=37, second=10)
    scanner.step(clock())
    pos = store.positions(ledger="inplay")
    assert len(pos) == 1 and pos[0]["symbol"] == "NVDA261106C00140000" and pos[0]["fill"] > 5.00
    p = pos[0]
    atr = scanner._rows(str(DAY.date()))[0]["atr14"]
    assert p["plan"]["stop_px"] == pytest.approx(p["plan"]["entry_px"] - 0.10 * atr, abs=0.02)
    assert p["policy_version"] == scanner.VERSION and p["setup"] == "INPLAY_ORB"
    amd = {r["ticker"]: r for r in scanner._rows(str(DAY.date()))}["AMD"]
    assert "no tradable contract" in amd["status"] and "expires after earnings" in amd["status"]
    assert any("IN PLAY NVDA calls" in a and "not a validated system setup" in a for a in alert_texts())
    # ORB stop on a finished 1m close; real quote for the exit
    scanner._state["cache"]["NVDA"]["m1"] = pd.DataFrame({"Close": [p["plan"]["stop_px"] - 0.05]},
                                                          index=pd.DatetimeIndex([pd.Timestamp(clock())]))
    prov.q["NVDA261106C00140000"] = (4.60, 4.70)
    scanner.manage(store.pos_get(p["id"]))
    p = store.pos_get(p["id"])
    assert p["status"] == "CLOSED" and p["plan"]["exit_reason"].startswith("ORB STOP")


def test_paused_paper_takes_no_scanner_trades_but_still_alerts(env):
    clock, f, prov = _scanner_world(env)
    store.kv_set("paper_enabled", False)
    scanner.step(clock())
    prov.q["NVDA261106C00140000"] = (4.90, 5.00)
    clock.t = DAY.replace(hour=9, minute=37, second=10)
    scanner.step(clock())
    assert not store.positions(ledger="inplay") and any(a.startswith("IN PLAY 09:35") for a in alert_texts())


def test_quick_moves_and_movers_digest_alert_for_names_outside_paper_trades(env):
    clock, f, prov = _scanner_world(env)
    scanner.step(clock())
    clock.t = DAY.replace(hour=9, minute=50, second=10)            # NVDA: 6x volume from 09:45 with the trend
    scanner.on_minute(DAY.date(), clock())
    assert any(a.startswith("QUICK MOVE NVDA") and "not a validated setup" in a for a in alert_texts())
    day = str(DAY.date())
    base = store.kv_get(f"scan_base:{day}")
    t0 = DAY.replace(hour=10, minute=0)
    q0 = {"TSLA": {"last": 250.0, "volume": 1_000_000.0}}
    scanner.pulse(day, t0, q0)
    vol5 = base["TSLA"]["avg_vol14"] / 78 * 3
    q1 = {"TSLA": {"last": 254.0, "volume": 1_000_000.0 + vol5}}           # +1.6% in 5 min on 3x volume
    fired = scanner.pulse(day, t0 + timedelta(minutes=5), q1)
    assert fired == ["TSLA"] and any(a.startswith("QUICK MOVE TSLA +1.60%") for a in alert_texts())
    assert scanner.pulse(day, t0 + timedelta(minutes=6), {"TSLA": {"last": 256.0, "volume": 1_000_000.0 + 2 * vol5}}) == []   # cooldown
    f.mv = {"PERCENT_CHANGE_UP": [{"symbol": "SMCI", "change_pct": 9.1}], "PERCENT_CHANGE_DOWN": [{"symbol": "PFE", "change_pct": -4.2}]}
    assert scanner.movers_update(day, DAY.replace(hour=10, minute=30))
    assert any(a.startswith("TOP MOVERS 10:30") and "SMCI +9.1%" in a for a in alert_texts())


def test_scanner_backtest_day_reports_stock_and_modeled_option_results(env):
    clock, f, prov = _scanner_world(env)
    m1s = {t: f.m1s[t] for t in ("NVDA", "AMD", "AAPL")}
    base = {t: scanner.baseline(f.daily(t), f.m5(t, None, pd.Timestamp(DAY.replace(hour=0))), DAY.date()) for t in m1s}
    tr = scanner.backtest_day(DAY.date(), m1s, base, {"NVDA": 0.5})
    nv = [t for t in tr if t["ticker"] == "NVDA"][0]
    assert nv["side"] == "C" and nv["stock_R"] > 0 and nv["option_pnl_modeled"] > 0 and nv["iv_assumed"] == 0.5


# ================================================================ Nick's trades: guidance, origin, 20% cap
def test_guidance_on_your_trade_alerts_on_change_and_never_sells_for_you(env):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    T.at(clock, 10, 0)
    import commands
    r = commands.handle("IN SPY 600C 2 at 2.04", "SPY")
    p = r["position"]
    assert p["plan"]["origin"].startswith("your idea") and "not a validated system setup" in r["reply"]
    exits.evaluate(store.pos_get(p["id"]), engine.snapshot("SPY")["v3"])
    g = store.pos_get(p["id"])["plan"]["guidance"]
    assert g["action"] == "HOLD" and "20% of premium planned max (not a guaranteed fill)" == g["plan"]["max_loss_rule"]
    T.setpx(fk, clock, 597.0)                           # the option drops through the 20% ceiling
    T.at(clock, 10, 3)
    exits.evaluate(store.pos_get(p["id"]), engine.snapshot("SPY")["v3"])
    p2 = store.pos_get(p["id"])
    assert p2["plan"]["guidance"]["action"] == "EXIT" and p2["status"] == "OPEN"        # advice only
    assert any(a.startswith("YOUR SPY 600C: EXIT") and "you place the order" in a for a in alert_texts())


def test_any_ticker_plan_uses_single_stock_contract_rules_and_says_whose_idea(env):
    clock, fk = fakes.install(env, T.vm_path, DAY, s0=600.0)
    T.at(clock, 10, 40)
    p = engine.build_plan("SPY", "C", None, "check")
    assert p["origin"].startswith(("system setup", "your idea"))
    assert engine.stock_cp()["abs_delta_min"] == 0.5 and engine.stock_cp()["premium_max"] == 8.0


# ================================================================ diagnostics
def test_diagnostics_simulator_baselines_and_stats():
    idx = pd.date_range("2026-10-28 09:30", periods=390, freq="1min", tz=ET)
    c = np.r_[np.full(30, 100.0), np.linspace(100.0, 102.0, 360)]
    d = pd.DataFrame({"Open": c, "High": c + 0.01, "Low": c - 0.01, "Close": c, "Volume": 1000.0}, index=idx)
    d = diagnostics.day_frame(d, idx[0].date())
    cand = {"t": idx[30].isoformat(), "side": "C", "entry": 100.0, "stop": 99.8, "t1": 100.6, "q": None, "flat_min": 5}
    r_br = diagnostics.simulate(cand, d, "bracket")
    r_hold = diagnostics.simulate(cand, d, "hold")
    r_flip = diagnostics.simulate(cand, d, "bracket", flip=True)
    assert r_br["why"] == "T1" and r_hold["why"] == "all out 15:25" and r_hold["R"] > r_br["R"] > 0
    assert r_flip["why"] == "structure stop" and r_flip["R"] < 0
    assert diagnostics.simulate(dict(cand, t=idx[-1].isoformat() if False else "2026-10-28T16:30:00-04:00"), d, "hold") is None
    st = diagnostics.stats([10, -5, -5, 20])
    assert st["win_rate"] == 50.0 and st["expectancy"] == 5.0 and st["profit_factor"] == 3.0 and st["max_drawdown"] == 10.0


def test_backtest_runs_the_engine_in_a_sandbox_and_writes_diagnostics(env, tmp_path):
    import backtest
    import replay
    env.setattr(replay, "REPORTS", tmp_path / "reports")
    live_db = store.DB
    m = fakes.make_market(T.vm_path, DAY, prior_days=16)
    m1s = {"SPY": m, "QQQ": m.copy()}
    db = tmp_path / "bt.db"
    summary = backtest.run_engine(m1s, [DAY.date()], "csv", "close", 0.18, "10:30", keep_db=db, progress=False)
    assert store.DB == live_db and db.exists() and set(summary) >= {"paper", "research", "exit31", "noise", "old"}
    res = diagnostics.run(db, m1s, tmp_path / "reports", seeds=3, label="t")
    md = (tmp_path / "reports" / "diagnostics_t.md").read_text()
    assert "Coin flip" in md and "MODELED" in md and res["candidates"] >= 1
    assert set(res["policies"]) == set(diagnostics.POLICIES)


# ================================================================ data plumbing
def test_schwab_rate_limit_waits_instead_of_bursting(monkeypatch):
    import schwab
    now = [1000.0]
    slept = []
    monkeypatch.setattr(schwab.time, "time", lambda: now[0])
    monkeypatch.setattr(schwab.time, "sleep", lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)))
    monkeypatch.setattr(schwab, "RATE_PER_MIN", 3)
    schwab._calls.clear()
    for _ in range(4):
        schwab._throttle()
    assert slept and sum(slept) >= 4.9                   # the 4th call waited (sleeps are capped at 5 s each)


def test_deep_history_is_requested_once_per_day(monkeypatch):
    import schwab
    calls = []
    marketdata.use(None)
    monkeypatch.setattr(schwab, "bars_1m_range", lambda t, s, e: calls.append("range") or None)
    monkeypatch.setattr(schwab, "bars_1m", lambda t, days=10: calls.append(f"recent{days}") or None)
    rest = marketdata.SchwabREST()
    rest.bars_1m("SPY")
    rest.bars_1m("SPY")
    assert calls == ["range", "recent2", "recent2"]
