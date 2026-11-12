"""nb_shares: the noise band on SPY shares (T12a long/short, T12b long only), paper, intraday. Frozen rules, finished
bars only, fills at the next fresh quote (ask / bid + $0.0035/share), flat at 15:59, restart safety, desk-down
checks, early close, dividend adjustment, switch, risk isolation, wiring. Fake Schwab data only, no network."""
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
import nb_shares as N  # noqa: E402
import scanner  # noqa: E402
import store  # noqa: E402
import v4risk  # noqa: E402
import v4store as S  # noqa: E402

ET = core.ET
D = date(2026, 11, 4)                                       # a Wednesday
LS, LO = "nbs_spy_ls", "nbs_spy_long"


def rth_minutes(day):
    s = pd.Timestamp(f"{day} 09:30", tz=ET)
    return pd.date_range(s, periods=390, freq="1min")


def bars(day, close_fn, open_=100.0):
    idx = rth_minutes(day)
    c = np.array([close_fn(i) for i in range(390)], dtype=float)
    o = np.r_[open_, c[:-1]]
    return pd.DataFrame({"Open": o, "High": c, "Low": c, "Close": c, "Volume": 1000.0}, index=idx)


def history(day, n=20):
    """n prior sessions: open 100, every bar closes at 100.1 -> sigma = 0.001 at every check."""
    out, d = [], day
    while len(out) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in core.HOLIDAYS:
            out.append(bars(d, lambda i: 100.1))
    return pd.concat(sorted(out, key=lambda x: x.index[0]))


class Prov(marketdata.Provider):
    name = "Schwab (fake for tests)"
    executable = True

    def __init__(self):
        self.world = None

    def quote(self, t):
        q = self.world.quotes([t])[0].get(t) if self.world else None
        if not q:
            return None
        return {"bid": q["bid"], "ask": q["ask"], "last": q["last"],
                "quote_time": pd.Timestamp(q["quote_ms"], unit="ms", tz="UTC").tz_convert(ET), "src": self.name}


class World:
    """Fetcher API used by nb_shares: ready, m1 (history), m1_today (finished + forming bars), daily, quotes, dividend."""

    def __init__(self, clock, path, day=D):
        self.clock, self.day, self.path = clock, day, path      # path(i) = close of the i-th RTH minute today
        self.hist = history(day)
        self.dead, self.div, self.ready_ = False, (None, None), True
        self.calls = {"m1": 0, "m1_today": 0}

    def ready(self):
        return self.ready_

    def m1(self, t, start, end):
        self.calls["m1"] += 1
        h = self.hist
        return h[(h.index >= pd.Timestamp(start)) & (h.index <= pd.Timestamp(end))]

    def m1_today(self, t, day):
        self.calls["m1_today"] += 1
        b = bars(day, self.path)
        now = pd.Timestamp(self.clock())
        return b[b.index <= now]                              # the forming bar is included (Schwab does that too)

    def daily(self, t):
        idx = pd.bdate_range(end=pd.Timestamp(self.day) - pd.Timedelta(days=1), periods=300)
        return pd.DataFrame({"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1e7}, index=idx)

    def price(self):
        now = pd.Timestamp(self.clock())
        i = int((now - pd.Timestamp(f"{self.day} 09:30", tz=ET)).total_seconds() // 60)
        return float(self.path(max(0, min(389, i))))

    def quotes(self, ts):
        if self.dead:
            return {}, None
        now = pd.Timestamp(self.clock())
        px = self.price()
        return {t: {"last": px, "bid": round(px - 0.01, 2), "ask": round(px + 0.01, 2),
                    "quote_ms": (now - pd.Timedelta(seconds=0.5)).value // 10 ** 6} for t in ts}, None

    def dividend(self, t):
        return self.div


def piecewise(points):
    """[(minute index from 09:30, close), ...] -> a step function."""
    pts = sorted(points)

    def f(i):
        v = pts[0][1]
        for m, p in pts:
            if i >= m:
                v = p
        return v
    return f


# 09:59 bar closes 100.30 (above the 100.10 band) -> long at 10:00; 10:29 bar back to 100.05 -> exit at 10:30;
# 12:59 bar 99.70 (below 99.90) -> short (long/short ledger only) at 13:00, held to the 15:59 flat.
PATH = piecewise([(0, 100.0), (29, 100.30), (59, 100.05), (209, 99.70)])


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    import health
    monkeypatch.setitem(health._feed, "ok", None)
    N._state.update(status="idle", last_error=None, mark_t=None)
    clock = fakes.Clock(datetime(2026, 11, 4, 8, 0, tzinfo=ET))
    monkeypatch.setattr(core, "now_et", clock)
    prov = Prov()
    marketdata.use(prov)
    yield monkeypatch, clock, prov
    scanner.use(None)
    marketdata.use(None)


def world(env, path=PATH, day=D):
    mp, clock, prov = env
    w = World(clock, path, day)
    scanner.use(w)
    prov.world = w
    return w


def at(day, hms):
    hh, mm = int(hms[:2]), int(hms[3:5])
    ss = int(hms[6:]) if len(hms) > 5 else 0
    return datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=ET)


def run(clock, day, a, b, step_s=5):
    t, end = at(day, a), at(day, b)
    while t <= end:
        clock.t = t
        N.step(t)
        t += timedelta(seconds=step_s)


def checks(led, day=D):
    return {d["id"].split(":")[-1] if d["id"].count(":") == 3 else d["id"]: d for d in S.decisions(ledger=led, kind="check")}


# ================================================================ pure rules
def test_actions_follow_the_backtest_order_stop_then_entry():
    A = N.actions
    assert A(0, 101.0, 100.5, 99.5, 100.0, True) == ["long"]
    assert A(0, 99.0, 100.5, 99.5, 100.0, True) == ["short"]
    assert A(0, 99.0, 100.5, 99.5, 100.0, False) == []                       # long-only ignores the short side
    assert A(1, 100.2, 100.5, 99.5, 100.0, True) == ["exit"]                 # long below max(upper, VWAP)
    assert A(1, 100.6, 100.5, 99.5, 100.7, True) == ["exit", "long"]         # above the band but under VWAP: out, back in
    assert A(1, 100.8, 100.5, 99.5, 100.7, True) == []                       # hold
    assert A(-1, 99.6, 100.5, 99.5, 100.0, True) == ["exit"]                 # short above min(lower, VWAP)
    assert A(-1, 99.0, 100.5, 99.5, 99.2, True) == []
    assert N.band(0.001, 100.0, 99.0) == pytest.approx((100.1, 99.0 * 0.999))
    assert N.CHECKS[0] == "10:00" and N.CHECKS[-1] == "15:30" and len(N.CHECKS) == 12 and N.check_minute("10:00") == 30


def test_profile_uses_14_full_sessions_and_skips_half_days():
    h = history(D, 20)
    prof, n = N.profile(h, D)
    assert n == 14 and all(v == pytest.approx(0.001) for v in prof.values())
    half = bars(D - timedelta(days=1), lambda i: 105.0).iloc[:210]           # a 13:00 close: not a "normal" session
    prof2, n2 = N.profile(pd.concat([h[h.index.date < (D - timedelta(days=1))], half]), D)
    assert n2 == 14 and all(v == pytest.approx(0.001) for v in prof2.values())
    assert N.profile(history(D, 9), D)[0] is None                           # fewer than 10 sessions: no band


def test_signal_uses_finished_bars_only_and_future_bars_change_nothing():
    b = bars(D, PATH)
    early = b[b.index <= pd.Timestamp(f"{D} 09:59", tz=ET)]                  # the 09:59 bar is the last finished one
    assert N.at_check(early, D, "10:00")[0] == pytest.approx(100.30)
    assert N.at_check(b[b.index < pd.Timestamp(f"{D} 09:59", tz=ET)], D, "10:00") is None    # not finished yet
    full = N.at_check(b, D, "10:00")
    weird = b.copy()
    weird.loc[weird.index > pd.Timestamp(f"{D} 09:59", tz=ET), ["Close", "High", "Low"]] = 500.0
    assert N.at_check(weird, D, "10:00") == full == N.at_check(early, D, "10:00")
    vw = (100.0 * 29 + 100.30) / 30
    assert full[1] == pytest.approx(vw)


# ================================================================ live ledger
def test_full_day_entries_exits_short_side_and_flat(env):
    w = world(env)
    mp, clock, _ = env
    run(clock, D, "08:00", "08:00")
    prep = store.kv_get(N._pk(D))
    assert prep["sessions"] == 14 and prep["prev_close_adj"] == 100.0 and prep["sigma"]["10:00"] == pytest.approx(0.001)
    run(clock, D, "09:31:10", "09:31:10")
    assert store.kv_get(f"nbs:open:{D}") == 100.0
    run(clock, D, "10:00:00", "10:00:15")
    for led in (LS, LO):
        p = S.positions(ledger=led)[0]
        assert p["side"] == "long" and p["entry_px"] == pytest.approx(100.31) and p["book"] == "trend"   # the ask
        assert p["qty"] == math.floor(3000 / 100.31 * 1e4) / 1e4 and p["fees"] == pytest.approx(round(0.0035 * p["qty"], 4))
        assert pd.Timestamp(p["quote_t"]) > pd.Timestamp(p["signal_t"]) and p["exec_model"] == "nbspy1"
    run(clock, D, "10:30:00", "10:30:15")
    for led in (LS, LO):
        p = S.positions(ledger=led)[0]
        assert p["status"] == "CLOSED" and p["exit_px"] == pytest.approx(100.04)                    # the bid
        assert p["realized"] == pytest.approx(round((100.04 - 100.31) * p["qty"] - 2 * 0.0035 * p["qty"], 2), abs=0.011)
    run(clock, D, "11:00:15", "12:30:15", step_s=60)
    run(clock, D, "13:00:00", "13:00:15")
    sh = [p for p in S.positions(ledger=LS) if p["status"] == "OPEN"]
    assert len(sh) == 1 and sh[0]["side"] == "short" and sh[0]["entry_px"] == pytest.approx(99.69)   # the bid
    assert not [p for p in S.positions(ledger=LO) if p["status"] == "OPEN"]                         # long only: nothing
    run(clock, D, "13:30:15", "15:58:15", step_s=60)
    assert S.get(sh[0]["id"])["status"] == "OPEN"
    run(clock, D, "15:59:00", "15:59:15")
    c = S.get(sh[0]["id"])
    assert c["status"] == "CLOSED" and c["exit_px"] == pytest.approx(99.71) and c["exit_reason"].startswith("FLAT")  # the ask
    ck = {d["id"]: d for d in S.decisions(ledger=LS, kind="check")}
    assert len(ck) == 12 and ck[f"{LS}:{D}:10:00"]["decision"] == "LONG" and ck[f"{LS}:{D}:10:30"]["decision"] == "EXIT"
    assert ck[f"{LS}:{D}:13:00"]["decision"] == "SHORT" and ck[f"{LS}:{D}:11:00"]["decision"] == "NO SIGNAL"
    assert ck[f"{LS}:{D}:15:30"]["decision"] == "HOLD" and not [c for c in ck.values() if c["decision"] == "NO DATA"]
    assert {d["id"]: d for d in S.decisions(ledger=LO, kind="check")}[f"{LO}:{D}:13:00"]["decision"] == "NO SIGNAL"


def test_no_fresh_quote_misses_the_entry_and_restart_never_duplicates(env):
    w = world(env)
    mp, clock, _ = env
    run(clock, D, "08:00", "09:31:10", step_s=600)
    w.dead = True
    run(clock, D, "10:00:00", "10:03:30", step_s=15)
    assert not S.positions(ledger=LS)
    miss = [d for d in S.decisions(ledger=LS, kind="entry")]
    assert miss and miss[0]["decision"] == "MISSED"
    w.dead = False
    N._state.update(mark_t=None, status="restart")                          # a restart: in-memory state gone
    S._ready["db"] = None
    run(clock, D, "10:03:40", "10:06:00", step_s=10)
    assert not S.positions(ledger=LS) and len([d for d in S.decisions(ledger=LS, kind="check")]) == 1
    calls = w.calls["m1"]
    run(clock, D, "10:30:00", "10:30:15")
    assert w.calls["m1"] == calls                                            # the stored prep is reused


def test_desk_down_checks_are_recorded_not_traded_late(env):
    w = world(env)
    mp, clock, _ = env
    run(clock, D, "11:10:00", "11:10:00")                                   # starts late: prep + open now
    ck = {d["id"]: d["decision"] for d in S.decisions(ledger=LS, kind="check")}
    assert ck[f"{LS}:{D}:10:00"] == "NO DATA" and ck[f"{LS}:{D}:11:00"] == "NO DATA" and not S.positions(ledger=LS)
    run(clock, D, "11:30:00", "11:30:15")
    assert {d["id"]: d["decision"] for d in S.decisions(ledger=LS, kind="check")}[f"{LS}:{D}:11:30"] in ("NO SIGNAL", "LONG", "SHORT", "HOLD")


def test_early_close_day_is_skipped_and_dividend_adjusts_the_prior_close(env):
    mp, clock, _ = env
    w = world(env)
    mp.setattr(core, "EARLY_CLOSE", set(core.EARLY_CLOSE) | {str(D)})
    run(clock, D, "08:00", "10:00:15")
    assert not store.kv_get(N._pk(D)) and not S.decisions(ledger=LS, kind="check")
    mp.setattr(core, "EARLY_CLOSE", set())
    w.div = (str(D), 1.85)
    run(clock, D, "08:01", "08:01")
    prep = store.kv_get(N._pk(D))
    assert prep["prev_close_adj"] == pytest.approx(100.0 - 1.85) and "ex-dividend" in prep["dividend_src"]


def test_switch_off_blocks_entries_and_exits_still_run(env):
    w = world(env)
    mp, clock, _ = env
    run(clock, D, "08:00", "09:31:10", step_s=600)
    run(clock, D, "10:00:00", "10:00:15")
    assert len([p for p in S.positions(ledger=LS) if p["status"] == "OPEN"]) == 1
    mp.setattr(N, "switch_on", lambda: False)
    run(clock, D, "10:30:00", "10:30:15")
    run(clock, D, "13:00:00", "13:00:15")
    assert not [p for p in S.positions(ledger=LS) if p["status"] == "OPEN"]
    assert [d for d in S.decisions(ledger=LS, kind="entry") if d["decision"] == "SWITCH OFF"]


def test_trend_book_is_isolated_kill_switch_closes_it_and_overnight_leftovers_close(env):
    w = world(env)
    mp, clock, _ = env
    run(clock, D, "08:00", "09:31:10", step_s=600)
    run(clock, D, "10:00:00", "10:00:15")
    assert v4risk.admit("sip_orb5", "stocks", "SPY", "long") is None          # stocks never count the trend book
    assert "trend book cap" in v4risk.admit("nbs_other", "trend", "QQQ", "long")
    assert v4risk.status()["limits"]["isolated_books"] == ["sprint", "swing", "trend", "pead", "core", "tcore"]
    r = v4risk.kill("test")
    assert r["closed"] == 2 and not [p for p in S.positions(status="OPEN") if p["book"] == "trend"]
    store.kv_set("v4_enabled", True)
    S.open_position({"id": f"{LS}:2026-11-03:15:30", "ledger": LS, "book": "trend", "kind": "shares", "date": "2026-11-03",
                     "ticker": "SPY", "direction": "long", "side": "long", "qty": 1.0, "entry_px": 100.0, "entry_t": "x",
                     "legs": [{"symbol": "SPY", "action": "buy", "qty": 1.0}], "plan": {}})
    run(clock, D, "10:00:20", "10:00:20")
    assert "OVERNIGHT" in S.get(f"{LS}:2026-11-03:15:30")["exit_reason"]


def test_report_api_and_wiring(env):
    w = world(env)
    mp, clock, _ = env
    run(clock, D, "08:00", "09:31:10", step_s=600)
    run(clock, D, "10:00:00", "10:00:15")
    import v4api
    import v4report
    d = v4report.overview("2026-11-02")
    tr = {b["book"]: b for b in d["books"]}["trend"]
    rows = {r["ledger"]: r for r in tr["ledgers"]}
    assert set(rows) == {LS, LO} and rows[LS]["evidence"].startswith("PAPER") and rows[LS]["test"] == "T12a"
    assert rows[LO]["backtest"]["sealed_2022_2025"]["label"].startswith("BACKTEST")
    st = v4api.get("/api/v4/trend", {})
    assert st["checks_done"] == ["10:00"] and len(st["open"]) == 2
    import health
    import release
    assert "v4trend" in health.WORKERS and release.component_versions()["nb_shares.VERSION"] == N.VERSION


def test_module_has_no_order_path_and_does_not_change_the_noise_reference():
    src = (ROOT / "nb_shares.py").read_text().split('"""', 2)[2]
    assert "import broker" not in src and "alpaca" not in src.lower() and "/trader" not in src
    import noiseband
    assert noiseband.VERSION == "2026-10-30.v3.1-noise"
