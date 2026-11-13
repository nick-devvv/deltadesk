"""copilot (B8 + B5 + B9 + B4): pattern alerts on finished candles, event flags, paper shadows, labels and the report
card. Synthetic SPY day: flat 100.40 until 10:00, then a 5-minute candle that pokes above the prior-day high (101.00)
and closes back at 100.68, then a slide to 99.80. No network."""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import copilot as P  # noqa: E402
import core  # noqa: E402
import fakes  # noqa: E402
import scanner  # noqa: E402
import store  # noqa: E402
import v4risk  # noqa: E402
import v4store as S  # noqa: E402

ET = core.ET
DAY = date(2026, 11, 24)            # a Tuesday, not a holiday, not OPEX


def _ts(day, hh, mm):
    return pd.Timestamp(datetime(day.year, day.month, day.day, hh, mm), tz=ET)


def daily_bars(day, n=30):
    rows, idx, d = [], [], day
    while len(idx) < n:
        d = d - timedelta(days=1)
        if d.weekday() < 5:
            idx.append(pd.Timestamp(datetime(d.year, d.month, d.day), tz=ET))
            rows.append({"Open": 99.8, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 5e7})
    df = pd.DataFrame(rows[::-1], index=idx[::-1])
    return df


CANDLE = [(100.65, 100.75, 100.60, 100.72), (100.72, 100.90, 100.70, 100.88), (100.88, 101.05, 100.85, 100.95),
          (100.95, 100.96, 100.70, 100.75), (100.75, 100.78, 100.64, 100.68)]


def day_bars(day, slide=-0.04, after_px=None):
    """09:30-15:59 1-minute bars. after_px(minute_index) overrides the path after 10:05 (for the look-ahead test)."""
    rows, idx = [], []
    for m in pd.date_range(_ts(day, 9, 30), _ts(day, 15, 59), freq="1min"):
        k = (m.hour * 60 + m.minute) - 600                  # minutes after 10:00
        if k < 0:
            o, h, l, c, v = 100.40, 100.45, 100.35, 100.40, 1000.0
        elif k < 5:
            (o, h, l, c), v = CANDLE[k], 3000.0
        else:
            c0 = 100.68 + slide * (k - 4)
            c = max(99.80, c0) if after_px is None else after_px(k)
            o, h, l, v = c + 0.02, c + 0.03, c - 0.03, 1200.0
        rows.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": v})
        idx.append(m)
    return pd.DataFrame(rows, index=idx)


class Fake:
    """scanner-style fetcher: finished-or-not is the caller's job (copilot applies C.finished), like Schwab's live feed."""

    def __init__(self, clock, m1):
        self.clock, self.m1, self.calls = clock, m1, 0

    def ready(self):
        return True

    def daily(self, t):
        return daily_bars(DAY) if t == "SPY" else pd.DataFrame()

    def m1_today(self, t, day):
        return self.m1 if t == "SPY" else pd.DataFrame()

    def m1_ext(self, t, day, now):
        return self.m1_today(t, day)

    def quotes(self, ts):
        now = pd.Timestamp(self.clock())
        done = self.m1[self.m1.index + pd.Timedelta(minutes=1) <= now]
        last = float(done["Close"].iloc[-1]) if len(done) else 100.40
        return {"SPY": {"last": last, "bid": round(last - 0.01, 2), "ask": round(last + 0.01, 2), "executable": True,
                        "quote_time": now - pd.Timedelta(seconds=0.5)}}, None


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    import health
    monkeypatch.setitem(health._feed, "ok", None)
    P._state.update(status="idle", last_error=None, step_s=None)
    sw = {"on": True, "paper": True}
    monkeypatch.setattr(P, "switches", lambda: (sw["on"], sw["paper"]))
    pushed = []
    import alerts
    monkeypatch.setattr(alerts, "_push", lambda title, body, pr: pushed.append((title, body, pr)))
    clock = fakes.Clock(datetime(DAY.year, DAY.month, DAY.day, 9, 30, tzinfo=ET))
    monkeypatch.setattr(core, "now_et", clock)
    f = Fake(clock, day_bars(DAY))
    scanner.use(f)
    yield {"clock": clock, "f": f, "sw": sw, "pushed": pushed}
    scanner.use(None)


def run(clock, a, b, step_s=30):
    t = datetime(DAY.year, DAY.month, DAY.day, *a, tzinfo=ET)
    end = datetime(DAY.year, DAY.month, DAY.day, *b, tzinfo=ET)
    while t <= end:
        clock.set(t) if hasattr(clock, "set") else setattr(clock, "t", t)
        P.step(t)
        t += timedelta(seconds=step_s)


# ---------------------------------------------------------------- pure parts
def test_resample_aligns_to_the_open_and_keeps_complete_candles_only():
    m1 = day_bars(DAY).iloc[:37]                                   # 09:30-10:06
    b5 = P.resample(m1, 5, DAY)
    assert b5.index[0] == _ts(DAY, 9, 30) and b5.index[-1] == _ts(DAY, 10, 0)   # 10:05 group has 2 bars: dropped
    c = b5.loc[_ts(DAY, 10, 0)]
    assert (c["o"], c["h"], c["l"], c["c"], c["v"]) == (100.65, 101.05, 100.60, 100.68, 15000.0)
    assert len(P.resample(m1, 15, DAY)) == 2


def test_levels_map():
    m1 = day_bars(DAY).iloc[:35]
    lv = {L["name"]: L["px"] for L in P.levels(daily_bars(DAY), m1, m1, DAY)}
    assert lv["PDH"] == 101.0 and lv["PDL"] == 99.0 and lv["PDC"] == 100.0
    assert lv["OR5H"] == 100.45 and lv["OR15L"] == 100.35 and "VWAP" in lv and lv["$101"] == 101.0


def test_rejection_wick_and_sweep_at_the_prior_day_high():
    m1 = day_bars(DAY).iloc[:35]
    b5 = P.resample(m1, 5, DAY)
    hits = P.detect(b5, P.levels(daily_bars(DAY), m1, m1, DAY))
    got = {(h["pattern"], h["side"]): h for h in hits}
    assert ("wick_reject", "short") in got and got[("wick_reject", "short")]["level"]["name"] == "PDH"
    assert got[("wick_reject", "short")]["stop"] == 101.06
    assert ("sweep", "short") in got


def test_patterns_on_hand_made_candles():
    def bars(rows):
        idx = pd.date_range(_ts(DAY, 10, 0), periods=len(rows), freq="5min")
        return pd.DataFrame(rows, columns=["o", "h", "l", "c", "v"], index=idx)
    lv = [{"name": "PDL", "px": 99.0}]
    eng = bars([[100.5, 100.6, 99.9, 100.0, 1], [100.0, 100.1, 99.5, 99.6, 1], [99.6, 99.7, 99.0, 99.1, 1],
                [99.05, 99.9, 98.98, 99.8, 1]])
    assert ("engulfing", "long") in {(h["pattern"], h["side"]) for h in P.detect(eng, lv)}
    ins = bars([[100, 101, 99, 100.5, 1], [100.5, 100.8, 99.5, 100.2, 1], [100.2, 101.4, 100.1, 101.3, 1]])
    assert ("inside_break", "long") in {(h["pattern"], h["side"]) for h in P.detect(ins, [])}
    gap = bars([[100, 100.2, 99.9, 100.1, 1], [100.1, 100.2, 100.0, 100.1, 1], [100.1, 100.2, 99.95, 100.1, 1],
                [100.1, 100.9, 100.1, 100.8, 1], [100.8, 101.2, 100.5, 101.1, 1]])
    assert ("fvg", "long") in {(h["pattern"], h["side"]) for h in P.detect(gap, [])}


def test_plan_targets_the_next_level_at_least_1r_away_else_2r():
    hit = {"side": "short", "stop": 101.06}
    lv = [{"name": "VWAP", "px": 100.45}, {"name": "PDC", "px": 100.0}]
    pl = P.plan(hit, 100.68, lv)
    assert pl["target"] == 100.0 and pl["target_name"] == "PDC" and pl["risk"] == 0.38 and pl["option"].startswith("0DTE 99P")
    pl2 = P.plan({"side": "long", "stop": 99.0}, 100.0, [])
    assert pl2["target"] == 102.0 and pl2["target_name"] == "2R" and "101C" in pl2["option"]
    assert P.plan({"side": "long", "stop": 100.0}, 100.0, []) is None


def test_event_flags():
    assert P.opex_day(date(2026, 11, 20)) and not P.opex_day(date(2026, 11, 27)) and not P.opex_day(date(2026, 11, 13))
    now = datetime(2026, 12, 9, 14, 1, tzinfo=ET)
    ev = P.events(now, {"fomc": True, "cpi": False, "jobs": False, "known": True})
    assert ev["news_window"] and any("FOMC" in n for n in ev["notes"])
    ev2 = P.events(datetime(2026, 11, 20, 10, 0, tzinfo=ET), {"fomc": False, "cpi": True, "jobs": None, "known": True})
    assert not ev2["news_window"] and ev2["opex"] and any("CPI" in n for n in ev2["notes"])


def test_label_target_stop_and_neither():
    a = {"side": "short", "plan": {"entry_ref": 100.68, "stop": 101.06, "target": 100.0}}
    m1 = day_bars(DAY)
    after = m1[m1.index >= _ts(DAY, 10, 5)]
    assert P.label(a, after) == {"outcome": "TARGET", "r": 1.79}
    up = day_bars(DAY, slide=+0.04)
    up = up[up.index >= _ts(DAY, 10, 5)]
    assert P.label(a, up)["outcome"] == "STOP"
    flat = day_bars(DAY, after_px=lambda k: 100.50)
    lab = P.label(a, flat[flat.index >= _ts(DAY, 10, 5)])
    assert lab["outcome"] == "NEITHER" and lab["r"] == round((100.68 - 100.50) / 0.38, 2)


# ---------------------------------------------------------------- the worker
def test_alert_push_shadow_target_label_and_report_card(env):
    run(env["clock"], (9, 35), (10, 4, 30))
    assert P.alerts_for(DAY) == [] and env["pushed"] == []            # flat morning: nothing fires
    run(env["clock"], (10, 5, 5), (10, 5, 5))
    al = P.alerts_for(DAY)
    ids = [a["id"] for a in al]
    assert "SPY|2026-11-24|10:00|5m|wick_reject|short" in ids
    w = next(a for a in al if a["pattern"] == "wick_reject")
    assert w["plan"]["stop"] == 101.06 and w["level"]["name"] == "PDH" and w["lag_s"] == 5.0
    assert w["evidence"] == "UNTESTED" and "context, not a tested edge" in w["body"]
    assert len(env["pushed"]) == 1                                    # one push per ticker per candle
    title, body, _ = env["pushed"][0]
    best = max(al, key=P.rank)
    assert title.startswith(best["title"]) and f"+{len(al) - 1} more" in title and "MIXED" in body and "Also:" in body
    assert best["pushed"] and not any(a.get("pushed") for a in al if a is not best)
    pos = S.positions(ledger="copilot")
    assert len(pos) == 1                                              # one shadow per ticker at a time
    p = pos[0]
    assert p["book"] == "copilot" and p["plan"]["alert"] == best["id"] and p["direction"] == best["side"]
    others = [store.q("SELECT decision, reasons FROM v4_decisions WHERE id=?", (f"copilot:{a['id']}",))[0] for a in al if a is not best]
    assert all(o["decision"] == "NO SHADOW" and "already has an open SPY" in o["reasons"] for o in others)
    run(env["clock"], (10, 5, 30), (10, 40))
    p = next(x for x in S.positions(ledger="copilot") if x["id"] == p["id"])
    assert p["status"] == "CLOSED"
    if p["direction"] == "long":                                     # inside-bar break long: stop 100.34 on the slide
        assert p["exit_reason"] == "stop 100.34" and p["realized"] < 0
    else:
        assert p["exit_reason"].startswith("target") and p["realized"] > 0
    run(env["clock"], (16, 1), (16, 1))                              # after the close: label the day
    lab = {a["id"]: a.get("label") for a in P.alerts_for(DAY)}
    assert lab["SPY|2026-11-24|10:00|5m|wick_reject|short"]["outcome"] == "TARGET"
    assert all(v for v in lab.values())
    assert P.feedback("SPY|2026-11-24|10:00|5m|wick_reject|short", True)["answer"] == "took"
    assert not P.feedback("nope", True)["ok"]
    sc = P.scorecard()
    assert sc["n"] == len(P.alerts_for(DAY)) and sc["by_pattern"]["wick_reject"]["target_first_pct"] == 100.0
    assert sc["by_pushed"]["pushed"]["n"] >= 1
    assert sc["by_answer"]["took"]["n"] == 1 and "no costs" in sc["label"]


def test_restart_never_repeats_an_alert_or_opens_twice(env):
    run(env["clock"], (10, 5, 5), (10, 5, 5))
    n_al, n_push = len(P.alerts_for(DAY)), len(env["pushed"])
    P._state.update(status="idle", last_error=None, step_s=None)     # a restart: module state gone, the db stays
    run(env["clock"], (10, 5, 5), (10, 6, 30), step_s=15)
    assert len(P.alerts_for(DAY)) == n_al and len(env["pushed"]) == n_push and len(S.positions(ledger="copilot")) == 1


def test_no_look_ahead_changing_future_bars_never_changes_earlier_alerts(env, tmp_path, monkeypatch):
    def early(rows):
        return [(a["id"], a["plan"], a["checklist"], a["why"]) for a in rows if a["at"] < "2026-11-24T10:21"]
    run(env["clock"], (9, 35), (10, 40))
    a1 = early(P.alerts_for(DAY))
    monkeypatch.setattr(store, "DB", tmp_path / "desk2.db")
    monkeypatch.setattr(store, "_conn", None)
    base = day_bars(DAY)
    alt = day_bars(DAY, after_px=lambda k: 101.5 - 0.3 * ((k // 2) % 3))       # a wild path ...
    alt[alt.index < _ts(DAY, 10, 21)] = base[base.index < _ts(DAY, 10, 21)]  # ... only from 10:21 on
    alt.loc[alt.index >= _ts(DAY, 10, 21), "Volume"] = 9e6
    env["f"].m1 = alt
    run(env["clock"], (9, 35), (10, 40))
    a2 = early(P.alerts_for(DAY))
    assert a1 and a1 == a2
    assert [a["id"] for a in P.alerts_for(DAY) if a["at"] >= "2026-11-24T10:21"]   # the changed bars do produce alerts later


def test_watch_only_alerts_without_paper_trades(env):
    env["sw"]["paper"] = False
    run(env["clock"], (10, 5, 5), (10, 5, 5))
    assert P.alerts_for(DAY) and env["pushed"] and S.positions(ledger="copilot") == []
    assert P.status()["watch_only"] is True


def test_kill_switch_blocks_shadows_not_alerts_and_switch_off_is_silent(env):
    store.kv_set("v4_enabled", False)
    run(env["clock"], (10, 5, 5), (10, 5, 5))
    assert P.alerts_for(DAY) and S.positions(ledger="copilot") == []
    d = store.q("SELECT decision, reasons FROM v4_decisions WHERE ledger='copilot'")
    assert d and all(x["decision"] == "NO SHADOW" and "kill switch" in x["reasons"] for x in d)
    store.kv_set("v4_enabled", True)
    env["sw"]["on"] = False
    store.kv_set(P._akey(str(DAY)), [])
    env["pushed"].clear()
    run(env["clock"], (10, 5, 20), (10, 5, 20))
    assert P.alerts_for(DAY) == [] and env["pushed"] == []


def test_flat_by_1555_and_overnight_leftover(env):
    env["f"].m1 = day_bars(DAY, after_px=lambda k: 100.60)            # never reaches stop 101.06 or target 100.0
    run(env["clock"], (10, 5, 5), (10, 6))
    p = S.positions(ledger="copilot", status="OPEN")
    assert len(p) == 1
    run(env["clock"], (15, 55), (15, 55))
    p = S.positions(ledger="copilot")[0]
    assert p["status"] == "CLOSED" and p["exit_reason"] == "flat by 15:55"


def test_wiring_and_no_order_path():
    import json
    import alerts
    import health
    import release
    import v4api
    c = json.loads((ROOT / "config/v4.json").read_text())
    assert c["copilot"] is True and c["copilot_paper"] is True
    lim = v4risk.LIMITS
    assert "copilot" in lim["isolated_books"] and "copilot" not in lim["multi_day_books"]
    assert lim["book_max_open"]["copilot"] == 2 and lim["book_daily_loss_usd"]["copilot"] == 150.0
    assert "copilot" in alerts.KINDS and "copilot" in health.WORKERS
    assert release.component_versions()["copilot.VERSION"] == P.VERSION
    assert "/api/v4/copilot/score" in v4api.__doc__ and "/api/v4/copilot/feedback" in v4api.__doc__
    assert "import copilot" in (ROOT / "server.py").read_text()
    code = (ROOT / "copilot.py").read_text().split('"""', 2)[2]
    assert "import broker" not in code and "place_order" not in code and "/trader" not in code
    assert set(P.EVIDENCE) == set(P.NAMES)
