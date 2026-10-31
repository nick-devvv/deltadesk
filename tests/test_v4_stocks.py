"""v4 stage 3: stock ledgers in shares (sip_orb5, sip_orb5_x, sip_orb15, earn_day) and their options shadows.
Published-rule edge cases, fills, sizing, no look-ahead, restart safety. Fake Schwab data only, no network."""
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
import fakes  # noqa: E402
import marketdata  # noqa: E402
import scanner  # noqa: E402
import sip_orb  # noqa: E402
import store  # noqa: E402
import v4store as S  # noqa: E402

ET = core.ET
DAY = datetime(2026, 11, 4, tzinfo=ET)


# ================================================================ fake world
class World:
    """Per ticker: price level, daily ATR, prior 09:30 5-min volume, today's first-5-min volume multiple and a path."""

    def __init__(self, clock, spec):
        self.clock, self.spec = clock, spec
        self.today = {t: self._today(t, s) for t, s in spec.items()}
        self.chain_rows = {}
        self.ready_ = True

    def _today(self, t, s):
        idx = pd.date_range(DAY.replace(hour=9, minute=30), DAY.replace(hour=15, minute=59), freq="1min")
        px = np.array([s["path"](i) for i in range(len(idx))], dtype=float)
        o = np.r_[s["open"], px[:-1]]
        hi, lo = np.maximum(o, px) + 0.01, np.minimum(o, px) - 0.01
        v = np.array([s["v5"] * s["rv"] / 5 if i < 5 else s["v5"] / 5 for i in range(len(idx))])
        if s.get("v15_rv"):
            v[5:15] = s["v5"] * s["v15_rv"] / 5
        return pd.DataFrame({"Open": o, "High": hi, "Low": lo, "Close": px, "Volume": v}, index=idx)

    # --- scanner fetcher API
    def ready(self):
        return self.ready_

    def daily(self, t):
        s = self.spec[t]
        days = pd.bdate_range(end=DAY.date() - timedelta(days=1), periods=40)
        return pd.DataFrame({"Open": s["open"], "High": s["open"] + s["atr"] / 2, "Low": s["open"] - s["atr"] / 2, "Close": s["open"],
                             "Volume": 5e6}, index=days)

    def m5(self, t, start, end):
        s = self.spec[t]
        rows, idx = [], []
        for d in pd.bdate_range(start.date(), end.date() - timedelta(days=1))[-s.get("hist", 21):]:
            for k in range(78):
                ts = pd.Timestamp(d.date()).tz_localize(ET) + timedelta(hours=9, minutes=30 + 5 * k)
                idx.append(ts)
                rows.append(s["v5"] if k == 0 else s["v5"] / 2)
        return pd.DataFrame({"Open": s["open"], "High": s["open"], "Low": s["open"], "Close": s["open"], "Volume": rows},
                            index=pd.DatetimeIndex(idx))

    def m1_today(self, t, day):
        return self.today[t][self.today[t].index <= pd.Timestamp(self.clock())]          # includes the forming bar

    def quotes(self, ts):
        out = {}
        now = pd.Timestamp(self.clock())
        for t in ts:
            m = self.today[t][self.today[t].index + pd.Timedelta(minutes=1) <= now]
            last = float(m["Close"].iloc[-1]) if len(m) else self.spec[t]["open"]
            out[t] = {"last": last, "bid": round(last - 0.01, 2), "ask": round(last + 0.01, 2), "volume": float(m["Volume"].sum()),
                      "open": self.spec[t]["open"], "quote_ms": (now - pd.Timedelta(seconds=0.5)).value // 10 ** 6}
        return out, None

    def movers(self, idx, sort):
        return [], None

    def chain(self, t, side, first, through, strikes):
        return self.chain_rows.get((t, side), []), None


class OptProv(marketdata.Provider):
    """Executable option quotes for the shadows: whatever the test puts in .q (bid, ask) at clock - 0.5 s."""
    name = "Schwab (fake options)"
    executable = True

    def __init__(self, clock):
        self.clock, self.q = clock, {}

    def option_quote(self, sym):
        if sym not in self.q:
            return None, "no quote"
        b, a = self.q[sym]
        return {"bid": b, "ask": a, "delta": 0.7, "quote_time": pd.Timestamp(self.clock()) - pd.Timedelta(seconds=0.5),
                "multiplier": 100, "src": self.name}, None

    def quote(self, t):
        return None


def path_up(level, cross_at=7, drop_at=None, drop_to=None):
    """Green first candle (open level, close level + 0.4), then above its high from bar `cross_at`."""
    def p(i):
        if i < 5:
            return level + (0.08, 0.16, 0.40, 0.30, 0.32)[i]          # high 50.41 on bar 3, close 50.32 > open
        if i < cross_at:
            return level + 0.30
        if drop_at is not None and i >= drop_at:
            return drop_to
        return level + 0.6
    return p


def path_down(level, cross_at=7):
    def p(i):
        if i < 5:
            return level - (0.08, 0.16, 0.40, 0.30, 0.32)[i]
        if i < cross_at:
            return level - 0.30
        return level - 0.6
    return p


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    monkeypatch.setattr(sip_orb, "_take_bar_token", lambda: True)
    sip_orb._state.update(bars={}, last_error=None)
    clock = fakes.Clock(DAY.replace(hour=8, minute=0))
    monkeypatch.setattr(core, "now_et", clock)
    prov = OptProv(clock)
    marketdata.use(prov)
    yield monkeypatch, clock, prov
    scanner.use(None)
    marketdata.use(None)


def make(env, spec):
    mp, clock, prov = env
    mp.setattr(scanner, "universe", lambda: list(spec))
    w = World(clock, spec)
    scanner.use(w)
    return w, clock, prov


def run(clock, a, b, step_s=60):
    t = DAY.replace(hour=int(a[:2]), minute=int(a[3:5]), second=int(a[6:]) if len(a) > 5 else 0)
    end = DAY.replace(hour=int(b[:2]), minute=int(b[3:5]), second=int(b[6:]) if len(b) > 5 else 0)
    while t <= end:
        clock.t = t
        sip_orb.step(t)
        t += timedelta(seconds=step_s)


BASE = {"open": 50.0, "atr": 1.5, "v5": 100_000.0}


# ================================================================ pure rules
def test_rank_applies_the_published_filters_and_counts_skips():
    spec = sip_orb.SPECS["sip_orb5"]
    rows = [{"ticker": f"T{i}", "price": 20.0, "avg_vol14": 2e6, "atr14": 1.0, "rv": 1.0 + i, "direction": "long"} for i in range(25)]
    rows += [{"ticker": "CHEAP", "price": 5.0, "avg_vol14": 2e6, "atr14": 1.0, "rv": 99, "direction": "long"},
             {"ticker": "THIN", "price": 20.0, "avg_vol14": 9e5, "atr14": 1.0, "rv": 99, "direction": "long"},
             {"ticker": "CALM", "price": 20.0, "avg_vol14": 2e6, "atr14": 0.5, "rv": 99, "direction": "long"},
             {"ticker": "LOWRV", "price": 20.0, "avg_vol14": 2e6, "atr14": 1.0, "rv": 0.99, "direction": "long"},
             {"ticker": "DOJI", "price": 20.0, "avg_vol14": 2e6, "atr14": 1.0, "rv": 99, "direction": None},
             {"ticker": "NOHIST", "price": 20.0, "avg_vol14": 2e6, "atr14": 1.0, "rv": None, "direction": "long"}]
    top, skips = sip_orb.rank(rows, spec)
    assert [r["ticker"] for r in top] == [f"T{i}" for i in range(24, 4, -1)]          # top 20 by RV, highest first
    assert skips["outside the top 20 by RV"] == 5 and skips["no 14-day opening-volume history"] == 1
    assert skips["price <= $5"] == 1 and skips["14-day average volume < 1M"] == 1 and skips["doji opening candle"] == 1
    assert skips["RV under 1x"] == 1 and any(k.startswith("ATR14 below") for k in skips)
    x, sx = sip_orb.rank(rows, sip_orb.SPECS["sip_orb5_x"])
    assert all(r["rv"] >= 5 for r in x) and not x                                     # ATR 1.0 < $2 for all
    e, _ = sip_orb.rank([dict(rows[0], atr14=3.0, rv=6.0, earnings=None), dict(rows[1], atr14=3.0, rv=6.0, earnings={"how": "x"})],
                        sip_orb.SPECS["earn_day"])
    assert [r["ticker"] for r in e] == ["T1"]


def test_candle_direction_doji_and_history_requirements():
    idx = pd.date_range(DAY.replace(hour=9, minute=30), periods=10, freq="1min")
    flat = pd.DataFrame({"Open": [10.0, 10.2, 10.1, 9.9, 10.05] * 2, "High": 10.3, "Low": 9.8, "Close": [10.2, 10.1, 9.9, 10.05, 10.0] * 2,
                         "Volume": 1000.0}, index=idx)
    c = sip_orb.candle(flat, 5)
    assert c["open"] == 10.0 and c["close"] == 10.0 and c["direction"] is None          # close == open: doji, no trade
    assert sip_orb.candle(flat.iloc[:4], 5) is None                                       # all 5 bars required
    m5 = pd.DataFrame({"Volume": [100.0, 50, 50]}, index=pd.DatetimeIndex(
        [pd.Timestamp("2026-11-03 09:30", tz=ET), pd.Timestamp("2026-11-03 09:35", tz=ET), pd.Timestamp("2026-11-03 09:40", tz=ET)]))
    h = sip_orb.open_volume_history(m5, DAY.date())
    assert h["open5"] == [100.0] and h["open15"] == [200.0]
    b = sip_orb.baseline(None, m5, DAY.date())
    assert b["open5_avg14"] is None and b["open5_n"] == 1                                 # fewer than 14 sessions: skipped


def test_size_and_stop_buckets():
    assert sip_orb.size(50.0, 0.15) == (666, 99.9)
    assert sip_orb.size(400.0, 0.05)[0] == 125                                            # notional cap $50,000
    assert sip_orb.stop_bucket(15) == "10-19c" and sip_orb.stop_bucket(250) == "200c+"


def test_shadow_contract_rules():
    now = DAY.replace(hour=9, minute=40)
    exp_ok, exp_far = (DAY.date() + timedelta(days=2)).isoformat(), (DAY.date() + timedelta(days=9)).isoformat()
    rows = [{"symbol": "NVDA261106C00175000", "strike": 175.0, "bid": 6.0, "ask": 6.2, "delta": 0.72, "exp": exp_ok},
            {"symbol": "NVDA261106C00170000", "strike": 170.0, "bid": 10.0, "ask": 10.3, "delta": 0.86, "exp": exp_ok},
            {"symbol": "NVDA261106C00178000", "strike": 178.0, "bid": 4.0, "ask": 4.9, "delta": 0.64, "exp": exp_ok},
            {"symbol": "NVDA261113C00175000", "strike": 175.0, "bid": 7.0, "ask": 7.2, "delta": 0.7, "exp": exp_far}]
    qual = ({"NVDA"}, {"abs_delta_min": 0.6, "abs_delta_max": 0.8, "abs_delta_target": 0.7, "dte_max": 7, "max_spread_pct_of_mid": 0.10})
    best, why = sip_orb.pick_shadow(rows, "long", now, "NVDA", spot=180.0, qual=qual)
    assert best["symbol"] == "NVDA261106C00175000" and why is None
    none, why = sip_orb.pick_shadow(rows, "long", now, "NVDA", spot=180.0, earnings_date=DAY.date().isoformat(), qual=qual)
    assert none is None and "earnings" in why
    none, why = sip_orb.pick_shadow(rows, "long", now, "AAA", spot=180.0, qual=qual)
    assert none is None and "qualifying" in why


# ================================================================ live ledgers
def test_sip_orb5_long_stop_entry_fill_size_and_stop_exit(env):
    w, clock, prov = make(env, {"AAA": dict(BASE, rv=4.0, path=path_up(50.0, cross_at=7, drop_at=20, drop_to=50.2))})
    run(clock, "08:30", "08:31")
    assert store.kv_get(f"v4sip_base:{DAY.date()}")["AAA"]["open5_avg14"] == pytest.approx(100_000.0)
    run(clock, "09:35:20", "09:36:20")
    rank = S.decisions(ledger="sip_orb5", kind="rank")[0]
    assert rank["data"]["top"][0]["ticker"] == "AAA" and rank["data"]["top"][0]["rv"] == pytest.approx(4.0)
    assert not S.positions(ledger="sip_orb5")                                             # 50.30 < high 50.41: no trigger yet
    run(clock, "09:37:20", "09:39:20")
    p = S.positions(ledger="sip_orb5")[0]
    lvl = p["plan"]["level"]
    assert p["side"] == "long" and p["entry_px"] >= lvl + 0.01                            # never better than the stop level
    assert p["plan"]["stop_dist"] == pytest.approx(0.15) and p["plan"]["stop"] == pytest.approx(p["entry_px"] - 0.15)
    assert p["qty"] == int(100 // 0.15) and p["risk_usd"] == pytest.approx(p["qty"] * 0.15, abs=0.01)
    assert pd.Timestamp(p["quote_t"]) > pd.Timestamp(p["signal_t"])
    run(clock, "09:50:20", "09:51:20")                                                    # drops to 50.20: below the stop
    c = S.get(p["id"])
    assert c["status"] == "CLOSED" and c["exit_reason"].startswith("STOP")
    assert c["exit_px"] == pytest.approx(50.19 - 0.01, abs=1e-6)                           # bid - $0.01
    assert c["r_mult"] == pytest.approx(c["realized"] / c["risk_usd"], abs=1e-3)
    assert not S.positions(ledger="sip_orb5_opt")                                          # AAA isn't on the qualifying list
    assert S.decisions(ledger="sip_orb5_opt")[0]["decision"] == "NO CONTRACT"


def test_sip_orb5_short_side_and_flat_at_1555(env):
    w, clock, prov = make(env, {"BBB": dict(BASE, rv=3.0, path=path_down(50.0))})
    run(clock, "08:30", "08:31")
    run(clock, "09:35:20", "09:40:20")
    p = S.positions(ledger="sip_orb5")[0]
    assert p["side"] == "short" and p["entry_px"] <= p["plan"]["level"] - 0.01 and p["plan"]["stop"] > p["entry_px"]
    run(clock, "15:55:05", "15:55:05")
    c = S.get(p["id"])
    assert c["status"] == "CLOSED" and c["exit_reason"].startswith("FLAT 15:55") and c["exit_px"] == pytest.approx(49.42, abs=1e-6)   # ask 49.41 + $0.01


def test_sip_orb5_x_enters_on_a_finished_close_at_the_next_quote_and_buckets_the_stop(env):
    spec = {"XXX": dict(BASE, atr=2.5, rv=6.0, path=path_up(50.0, cross_at=8)),
            "YYY": dict(BASE, atr=1.5, rv=6.0, path=path_up(50.0, cross_at=8))}           # ATR < $2: only sip_orb5
    w, clock, prov = make(env, spec)
    run(clock, "08:30", "08:31")
    run(clock, "09:35:20", "09:38:20")
    assert not S.positions(ledger="sip_orb5_x")                                           # bar 09:38 not finished yet
    run(clock, "09:39:00", "09:39:00")                                                    # quote at 09:38:59.5 is before the bar end + 1s
    assert not S.positions(ledger="sip_orb5_x")
    run(clock, "09:39:10", "09:39:10")
    xs = S.positions(ledger="sip_orb5_x")
    assert [p["ticker"] for p in xs] == ["XXX"]
    p = xs[0]
    assert p["signal_t"].startswith("2026-11-04T09:39:00") and p["entry_px"] == pytest.approx(50.62, abs=1e-6)   # ask 50.61 + $0.01
    assert p["plan"]["stop_cents"] == 25 and p["plan"]["stop_bucket"] == "20-29c"
    assert {x["ticker"] for x in S.positions(ledger="sip_orb5")} == {"XXX", "YYY"}


def test_sip_orb5_x_misses_when_no_quote_comes_in_time(env):
    w, clock, prov = make(env, {"XXX": dict(BASE, atr=2.5, rv=6.0, path=path_up(50.0, cross_at=8))})
    run(clock, "08:30", "08:31")
    run(clock, "09:35:20", "09:36:20")
    run(clock, "09:42:20", "09:42:20")                                                    # first look after the window
    assert not S.positions(ledger="sip_orb5_x")
    assert S.decisions(ledger="sip_orb5_x", kind="entry")[0]["decision"] == "MISSED"


def test_sip_orb15_uses_the_15_minute_candle(env):
    def p(i):
        if i < 15:
            return 50.0 + 0.03 * (i + 1)
        return 50.0 + (0.3 if i < 20 else 0.8)
    w, clock, prov = make(env, {"FFF": dict(BASE, rv=1.0, v15_rv=3.0, path=p)})
    run(clock, "08:30", "08:31")
    run(clock, "09:45:20", "09:46:20")
    r = S.decisions(ledger="sip_orb15", kind="rank")[0]
    assert r["data"]["top"][0]["ticker"] == "FFF" and r["data"]["minutes"] == 15
    run(clock, "09:50:20", "09:52:20")
    p15 = S.positions(ledger="sip_orb15")
    assert p15 and p15[0]["plan"]["candle"]["end"].startswith("2026-11-04T09:45")


def test_earn_day_needs_the_first_session_after_a_report(env):
    import earnings
    spec = {"ERN": dict(BASE, atr=3.0, rv=8.0, path=path_up(50.0, cross_at=8)),
            "NOE": dict(BASE, atr=3.0, rv=8.0, path=path_up(50.0, cross_at=8))}
    w, clock, prov = make(env, spec)
    earnings.mark_released("ERN", "2026-11-03T16:05:00-05:00", "https://www.sec.gov/Archives/x")
    run(clock, "08:30", "08:31")
    run(clock, "09:35:20", "09:40:20")
    assert [p["ticker"] for p in S.positions(ledger="earn_day")] == ["ERN"]
    assert S.positions(ledger="earn_day")[0]["book"] == "catalyst"
    assert sorted(p["ticker"] for p in S.positions(ledger="sip_orb5_x")) == ["ERN", "NOE"]


def test_options_shadow_tracks_the_share_trade(env):
    spec = {"NVDA": dict(BASE, open=180.0, atr=5.0, rv=4.0, path=lambda i: 180.0 + (0.1 * (i + 1) if i < 5 else 0.48 if i < 7 else 1.5))}
    w, clock, prov = make(env, spec)
    exp = (DAY.date() + timedelta(days=2)).isoformat()
    sym = "NVDA261106C00175000"
    w.chain_rows[("NVDA", "C")] = [{"symbol": sym, "strike": 175.0, "bid": 6.0, "ask": 6.2, "delta": 0.72, "exp": exp},
                                   {"symbol": "NVDA261106C00182000", "strike": 182.0, "bid": 1.0, "ask": 1.1, "delta": 0.45, "exp": exp}]
    prov.q[sym] = (6.4, 6.6)
    run(clock, "08:30", "08:31")
    run(clock, "09:35:20", "09:39:20")
    share = S.positions(ledger="sip_orb5")[0]
    opt = S.positions(ledger="sip_orb5_opt")[0]
    assert opt["parent_id"] == share["id"] and opt["legs"][0]["symbol"] == sym and opt["entry_px"] == 6.6 and opt["fees"] == 0.65
    prov.q[sym] = (7.0, 7.2)
    run(clock, "15:55:05", "15:55:05")
    o = S.get(opt["id"])
    assert S.get(share["id"])["status"] == "CLOSED" and o["status"] == "CLOSED"
    assert o["exit_px"] == 7.0 and o["realized"] == pytest.approx((7.0 - 6.6) * 100 - 1.30, abs=0.01)


def test_names_without_14_sessions_are_skipped_and_counted(env):
    w, clock, prov = make(env, {"NEW": dict(BASE, rv=9.0, hist=10, path=path_up(50.0)), "OLD": dict(BASE, rv=2.0, path=path_up(50.0))})
    run(clock, "08:30", "08:31")
    run(clock, "09:35:20", "09:36:20")
    r = S.decisions(ledger="sip_orb5", kind="rank")[0]["data"]
    assert [x["ticker"] for x in r["top"]] == ["OLD"]
    assert r["skips"]["no 14-day opening-volume history"] == 1 and r["no_open_history"] == 1


def test_ranking_and_triggers_ignore_future_bars(env):
    w, clock, prov = make(env, {"AAA": dict(BASE, rv=4.0, path=path_up(50.0, cross_at=30))})
    run(clock, "08:30", "08:31")
    run(clock, "09:35:20", "09:35:20")
    a = S.decisions(ledger="sip_orb5", kind="rank")[0]["data"]["top"]
    st_a = store.kv_get(f"v4sip:{DAY.date()}:sip_orb5:AAA")
    # rewrite everything after 09:35 in a fresh database: the 09:35 ranking and watch level must not change
    mp, clock2, prov2 = env
    mp.setattr(store, "DB", Path(str(store.DB) + "b"))
    mp.setattr(store, "_conn", None)
    sip_orb._state.update(bars={})
    w.today["AAA"].loc[w.today["AAA"].index >= pd.Timestamp(DAY.replace(hour=9, minute=35)), ["Open", "High", "Low", "Close"]] = 99.0
    run(clock, "08:30", "08:31")
    run(clock, "09:35:20", "09:35:20")
    b = S.decisions(ledger="sip_orb5", kind="rank")[0]["data"]["top"]
    st_b = store.kv_get(f"v4sip:{DAY.date()}:sip_orb5:AAA")
    assert a == b and st_a["level"] == st_b["level"] and st_a["dir"] == st_b["dir"]


def test_restart_never_enters_twice(env):
    w, clock, prov = make(env, {"AAA": dict(BASE, rv=4.0, path=path_up(50.0, cross_at=7))})
    run(clock, "08:30", "08:31")
    run(clock, "09:35:20", "09:39:20")
    assert len(S.positions(ledger="sip_orb5")) == 1
    sip_orb._state.update(bars={})                                                     # a restart: in-memory state gone
    S._ready["db"] = None
    st = store.kv_get(f"v4sip:{DAY.date()}:sip_orb5:AAA")
    store.kv_set(f"v4sip:{DAY.date()}:sip_orb5:AAA", dict(st, state="WAITING"))         # even a lost decision can't re-enter
    run(clock, "09:40:20", "09:42:20")
    assert len(S.positions(ledger="sip_orb5")) == 1


def test_no_entries_without_schwab_or_after_1530(env):
    w, clock, prov = make(env, {"AAA": dict(BASE, rv=4.0, path=path_up(50.0, cross_at=400))})
    run(clock, "08:30", "08:31")
    run(clock, "09:35:20", "09:35:20")
    run(clock, "15:15:20", "15:15:20")
    assert S.decisions(ledger="sip_orb5", kind="entry")[0]["decision"] == "EXPIRED"
    w.ready_ = False
    sip_orb.step(DAY.replace(hour=15, minute=31))
    assert "waiting for Schwab" in sip_orb._state["status"]
