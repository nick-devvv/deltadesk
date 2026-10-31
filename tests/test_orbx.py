"""v3.5: the corrected ORB (ORBX-15-5) state machine - sequencing, wicks, equality, reuse, premature/missing/failed
retests, gaps, expiry, resets, restart identity, next-quote entry and no look-ahead. Synthetic candles, no network."""
from datetime import datetime

import pandas as pd
import pytest

import core
import orb_retest as O
import store

ET = core.ET
D = "2026-10-28"


def bars(c5, start="09:30"):
    """5-minute candles [(o,h,l,c), ...] -> 1-minute bars whose 5m aggregate is exactly each candle."""
    rows, idx = [], []
    t = pd.Timestamp(f"{D} {start}", tz=ET)
    for o, h, l, c in c5:
        assert l <= min(o, c) and h >= max(o, c)
        for b in ((o, o, o, o), (o, h, min(o, h), h), (h, h, l, l), (l, max(l, c), l, c), (c, c, c, c)):
            idx.append(t)
            rows.append(b)
            t += pd.Timedelta(minutes=1)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx), columns=["Open", "High", "Low", "Close"]).assign(Volume=1000.0)


OR3 = [(100.5, 101.0, 100.2, 100.6), (100.6, 100.9, 100.0, 100.4), (100.4, 100.8, 100.1, 100.7)]     # OR 100.00 - 101.00
FLAT = (101.40, 101.60, 101.30, 101.50)


def ep_of(res, side="C", n=None):
    e = [x for x in res["episodes"] if x["side"] == side and (n is None or x["n"] == n)]
    return e[-1] if e else None


def test_bull_sequence_breakout_independent_candle_retest_entry():
    c5 = OR3 + [(100.85, 101.30, 100.80, 101.20),       # B 09:50: closes above, wick overlaps the range
                (101.2, 101.60, 101.05, 101.50),       # C 09:55: entirely above (low 101.05 > 101.00)
                FLAT,                                  # no touch
                (101.4, 101.45, 101.02, 101.30),       # R 10:05: touches the zone, closes back above
                FLAT]
    r = O.run(bars(c5), "SPY")
    assert r["or"]["high"] == 101.0 and r["or"]["low"] == 100.0
    e = ep_of(r)
    assert e["state"] == "ENTRY CONFIRMED" and r["stage"]["C"] == "ENTRY CONFIRMED"
    b, c, rr = (pd.Timestamp(e[k]["close_time"]) for k in ("B", "C", "R"))
    assert b < c < rr and e["B"]["close_time"].endswith("09:50:00-04:00") and e["R"]["close_time"].endswith("10:05:00-04:00")
    assert e["stop"] < 101.0 and e["entry_after"] > e["R"]["close_time"]
    assert [t["to"] for t in e["transitions"]] == ["WAITING FOR INDEPENDENT CANDLE", "WAITING FOR RETEST", "ENTRY CONFIRMED"]


def test_overlapping_and_equal_candles_are_not_independent():
    c5 = OR3 + [(100.85, 101.30, 100.80, 101.20),       # B
                (101.2, 101.50, 100.95, 101.40),       # closes above but its wick overlaps: not C
                (101.4, 101.60, 101.00, 101.50),       # low == boundary exactly: not C (strict)
                FLAT]                                  # 10:00-10:05 entirely above: the first real C
    e = ep_of(O.run(bars(c5), "SPY"))
    assert e["C"]["close_time"].endswith("10:05:00-04:00") and e["state"] == "WAITING FOR RETEST"


def test_a_gap_candle_is_the_breakout_only_never_also_the_confirmation():
    c5 = OR3 + [(101.5, 101.8, 101.4, 101.7),          # gap open above, entirely above: B only (flagged gap)
                (101.7, 101.9, 101.3, 101.6)]          # entirely above: THIS is C
    e = ep_of(O.run(bars(c5), "SPY"))
    assert e["gap"] and e["B"]["close_time"].endswith("09:50:00-04:00") and e["C"]["close_time"].endswith("09:55:00-04:00")


def test_a_touch_before_the_independent_candle_is_not_the_retest():
    c5 = OR3 + [(100.85, 101.30, 100.80, 101.20),       # B
                (101.2, 101.40, 101.00, 101.30),       # touches 101.00 and closes above: but C hasn't formed -> nothing
                (101.3, 101.70, 101.10, 101.60),       # C
                FLAT, FLAT]
    e = ep_of(O.run(bars(c5), "SPY"))
    assert e["C"]["close_time"].endswith("10:00:00-04:00") and e["R"] is None and e["state"] == "WAITING FOR RETEST"


def test_missing_retest_expires_and_never_trades():
    run_up = [(101.5 + i * .3, 101.9 + i * .3, 101.45 + i * .3, 101.8 + i * .3) for i in range(12)]
    c5 = OR3 + [(100.85, 101.30, 100.80, 101.20), (101.2, 101.60, 101.05, 101.50)] + run_up
    r = O.run(bars(c5), "SPY")
    first = ep_of(r, n=1)
    assert first["state"] == "EXPIRED" and "no retest" in first["why"] and first["R"] is None
    assert not [x for x in r["episodes"] if x["state"] == "ENTRY CONFIRMED"]


@pytest.mark.parametrize("retest,why", [((101.4, 101.45, 100.60, 101.20), "wick"),     # 0.40 deep: past the fail limit
                                        ((101.4, 101.45, 100.97, 100.99), "closed back inside")])
def test_failed_retests_invalidate(retest, why):
    c5 = OR3 + [(100.85, 101.30, 100.80, 101.20), (101.2, 101.60, 101.05, 101.50), retest, FLAT]
    e = ep_of(O.run(bars(c5), "SPY"), n=1)
    assert e["state"] == "INVALIDATED" and why in e["why"] and e["R"] is None


def test_bearish_mirror():
    c5 = OR3 + [(100.3, 100.40, 99.70, 99.80),        # B below 100.00
                (99.8, 99.95, 99.40, 99.50),           # C: high 99.95 < 100.00
                (99.5, 99.60, 99.30, 99.40),
                (99.4, 99.98, 99.35, 99.70),           # R: touches from underneath, closes back below
                (99.7, 99.8, 99.5, 99.6)]
    e = ep_of(O.run(bars(c5), "SPY"), side="P")
    assert e["state"] == "ENTRY CONFIRMED" and e["stop"] > 100.0 and e["boundary"] == 100.0


def test_reset_needs_a_close_back_inside_and_a_new_breakout_and_is_limited():
    fail = (101.4, 101.45, 100.97, 100.99)               # failed retest, closes inside
    c5 = OR3 + [(100.85, 101.30, 100.80, 101.20), (101.2, 101.60, 101.05, 101.50), fail,        # episode 1 fails
                (100.99, 101.30, 100.90, 101.20), (101.2, 101.60, 101.05, 101.50), fail,       # episode 2 fails
                (100.99, 101.30, 100.90, 101.20), (101.2, 101.60, 101.05, 101.50), (101.4, 101.45, 101.02, 101.30)]
    r = O.run(bars(c5), "SPY")
    calls = [x for x in r["episodes"] if x["side"] == "C"]
    assert [x["n"] for x in calls] == [1, 2] and all(x["state"] == "INVALIDATED" for x in calls)
    assert r["stage"]["C"] == "DONE FOR THE DAY"                                              # max one reset


def test_no_new_entry_after_the_last_entry_time():
    c5 = OR3 + [FLAT[:0] or (100.5, 100.8, 100.3, 100.6)] * 63 + [(100.85, 101.30, 100.80, 101.20)]
    r = O.run(bars(c5), "SPY")
    assert not r["episodes"] or all(x["state"] != "ENTRY CONFIRMED" for x in r["episodes"])
    assert r["stage"]["C"] == "DONE FOR THE DAY"


def test_no_look_ahead_future_candles_cannot_change_earlier_episodes():
    c5 = OR3 + [(100.85, 101.30, 100.80, 101.20), (101.2, 101.60, 101.05, 101.50), FLAT, (101.4, 101.45, 101.02, 101.30), FLAT, FLAT]
    m = bars(c5)
    cut = pd.Timestamp(f"{D} 10:12", tz=ET)
    a = O.run(m, "SPY", now=cut)
    m2 = m.copy()
    m2.loc[m2.index >= cut, ["Open", "High", "Low", "Close"]] = 90.0                         # crash after the cut
    b = O.run(m2, "SPY", now=cut)
    assert ep_of(a) == ep_of(b) and ep_of(a)["state"] == "ENTRY CONFIRMED"
    early = O.run(m, "SPY", now=pd.Timestamp(f"{D} 09:40", tz=ET))
    assert early["stage"]["C"] == "OPENING RANGE FORMING" and not early["episodes"]
    holes = m.drop(m.index[3])                                                                # a missing range bar
    assert O.run(holes, "SPY")["stage"]["C"] == "NO RANGE (data missing)"


def test_entry_needs_a_quote_after_the_retest_and_inside_the_chase_limit():
    c5 = OR3 + [(100.85, 101.30, 100.80, 101.20), (101.2, 101.60, 101.05, 101.50), FLAT, (101.4, 101.45, 101.02, 101.30)]
    e = ep_of(O.run(bars(c5), "SPY"))
    ok, why = O.entry_check(e, 101.30, pd.Timestamp(e["R"]["close_time"]))
    assert not ok and "never a backfilled entry" in why
    after = pd.Timestamp(e["entry_after"]) + pd.Timedelta(seconds=2)
    assert O.entry_check(e, 101.30, after) == (True, None)
    ok, why = O.entry_check(e, e["max_entry"] + 0.05, after)
    assert not ok and "too extended" in why


def test_episode_identity_survives_a_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "d.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "now_et", lambda: datetime(2026, 10, 28, 10, 30, tzinfo=ET))
    c5 = OR3 + [(100.85, 101.30, 100.80, 101.20), (101.2, 101.60, 101.05, 101.50), FLAT, (101.4, 101.45, 101.02, 101.30)]
    r = O.run(bars(c5), "SPY")
    O.save(r)
    O.mark_open(ep_of(r)["id"], "orbx_swing:x")
    O.save(O.run(bars(c5), "SPY"))                                                           # a restart recomputes
    rows = store.q("SELECT id, state FROM orbx_episodes")
    assert len(rows) == 1 and rows[0]["state"] == "POSITION OPEN"


def test_trailing_exits_only_tighten_and_r_uses_the_initial_risk():
    c5 = OR3 + [(100.85, 101.30, 100.80, 101.20), (101.2, 101.60, 101.05, 101.50), FLAT, (101.4, 101.45, 101.02, 101.30)]
    up = [(101.3 + i * .2, 101.55 + i * .2, 101.25 + i * .2, 101.5 + i * .2) for i in range(8)]
    down = [(103.0, 103.05, 101.0, 101.1)]
    m = bars(c5 + up + down)
    e = ep_of(O.run(m, "SPY"))
    i = O.entry_index(m, e)
    assert m.index[i] == pd.Timestamp(e["R"]["close_time"])
    outs = {k: O.trail_exit(m, i, e, k) for k in O.TRAILS}
    assert outs["fixed2r"]["why"] == "target" and outs["fixed2r"]["r"] < 2
    assert outs["swing"]["why"] in ("trail", "trail gap") and outs["swing"]["r"] > 1
    assert outs["atr"]["r"] > 0 and isinstance(outs["atr"]["r"], float)
    assert outs["hold"] is None                     # this synthetic day has no bar at the cutoff: unknown, never a guess
