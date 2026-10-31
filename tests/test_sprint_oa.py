"""Option Alpha cross-check pieces (sprint/specs/oa_crosscheck_v1.json): the plain fixed premium stop/target exit with
the desk's fill rules and the OA-LIKE once-a-minute variant, the 20-day SMA side rule (no look-ahead), the FOMC/CPI
event calendar, the NOT_SEEN_BY_OA period tag, stress-run ids, and the three shipped specs."""
import csv
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import engine, events, fills, periods, runner
from sprint.data import Series
from sprint.entries import Signal
from sprint.sim import ExitCfg, simulate

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2025, 3, 12)
HS = 0.01
DEBIT = 1.0 + HS                       # entry at 1.00 + the half-spread
FX = ExitCfg(stop="fixed", tp="none", time="b", fixed_stop=0.20, fixed_target=0.60)
OA = ExitCfg(stop="fixed", tp="none", time="b", fixed_stop=0.20, fixed_target=0.60, mechanics="oa1m")


def go(ctx, tape, cfg, idx=20):
    s = Signal("orb60", "SPY", DAY, "C", idx, 500.0, None, {})
    return simulate(ctx, s, cfg, None, tape, {"symbol": tape.symbol, "px": 1.0, "iv": 0.2, "delta": 0.45})


# ---------------------------------------------------------------- the fixed exit, desk fills (base)
def test_fixed_target_and_stop_are_percent_of_the_debit():
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 40: 1.5}, opt_hl={40: (1.70, 1.49)})
    t = go(ctx, tape, FX)
    assert t["exit_reason"] == "FIXED TARGET +60%" and t["exit_idx"] == 40
    assert t["exit_basis"] == pytest.approx(DEBIT * 1.6, abs=1e-4)                # 1.616: inside the bar's range
    assert t["pnl"] == pytest.approx((DEBIT * 1.6 - HS - DEBIT) * 100 - 1.30, abs=0.01)
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 40: 0.85}, opt_hl={40: (0.86, 0.70)})
    t = go(ctx, tape, FX)
    assert t["exit_reason"] == "FIXED STOP -20%" and t["exit_basis"] == pytest.approx(DEBIT * 0.8, abs=1e-4)
    assert t["exit_is_stop"] and t["pnl_2x"] == pytest.approx((DEBIT * 0.8 - 4 * HS - (1.0 + 2 * HS)) * 100 - 1.30, abs=0.01)


def test_fixed_same_bar_stop_and_target_counts_as_the_stop_and_gaps_fill_at_the_open():
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 40: 1.0}, opt_hl={40: (1.80, 0.60)})
    t = go(ctx, tape, FX)
    assert t["exit_reason"] == "FIXED STOP -20%" and t["exit_idx"] == 40
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 40: 0.55})
    t = go(ctx, tape, FX)
    assert t["exit_basis"] == pytest.approx(0.55)                                # gapped through: the next real price


def test_fixed_has_no_breakeven_no_if_flat_no_time_tightening():
    # +15% (a breakeven trigger in the table) then back to -15%, flat for hours, through 11:30 and 14:00: still open
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 25: 1.15, 30: 0.87})
    t = go(ctx, tape, FX)
    assert t["exit_reason"] == "ALL OUT 15:25" and t["exit_idx"] == 355


# ---------------------------------------------------------------- OA-LIKE mechanics
def test_oa_like_checks_only_the_minute_close_and_fills_at_the_next_minutes_price():
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 40: 0.95}, opt_hl={40: (0.96, 0.60)})   # dips through the stop, closes above
    assert go(ctx, tape, OA)["exit_reason"] == "ALL OUT 15:25"
    assert go(ctx, tape, FX)["exit_reason"] == "FIXED STOP -20%"                      # the desk fills see the dip
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 40: 0.79, 41: 0.70})                    # closes below at 10:10
    t = go(ctx, tape, OA)
    assert t["exit_reason"].startswith("FIXED STOP -20% (OA-LIKE") and t["exit_idx"] == 41 and t["exit_basis"] == 0.70
    assert t["exit_is_stop"]
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 40: 1.62, 41: 1.80})
    t = go(ctx, tape, OA)
    assert t["exit_reason"].startswith("FIXED TARGET +60% (OA-LIKE") and t["exit_idx"] == 41 and t["exit_basis"] == 1.80
    assert not t["exit_is_stop"]
    ctx, tape = SS.make_ctx(DAY, {}, {0: 1.0, 40: 0.79, 43: 0.75}, no_print={41, 42})  # no print: waits for the next one
    assert go(ctx, tape, OA)["exit_idx"] == 43


# ---------------------------------------------------------------- 20-day SMA side rule
def _series(closes, start=date(2025, 1, 2)):
    days = SS.weekdays(start, len(closes))
    frames = [SS.flat_day_df(d, px) for d, px in zip(days, closes)]
    return Series("SPY", pd.concat(frames, ignore_index=True)), days


def test_sma_side_uses_prior_closes_only():
    closes = [500 + k for k in range(25)]                                            # rising: prior close above its SMA
    s, days = _series(closes)
    assert s.sma_side(days[19]) is None and s.sma_side(days[20]) == 1               # 20 prior sessions needed
    s2, _ = _series(closes[:22] + [400, 400, 400])                                   # crash from day 22 on
    assert s2.sma_side(days[22]) == 1                                                # the crash day itself isn't known yet
    assert s2.sma_side(days[23]) == -1
    s3, _ = _series(closes[:22] + [900, 100, 100])                                   # future days changed: day 22 unchanged
    assert s3.sma_side(days[22]) == s2.sma_side(days[22])
    flat, d2 = _series([500.0] * 22)
    assert flat.sma_side(d2[21]) == 0
    near, d3 = _series([500.0] * 21 + [504.0, 500.0])                                # prior close +0.76% above its SMA
    assert near.sma_side(d3[22]) == 1 and near.sma_side(d3[22], margin=0.01) == 0
    far, d4 = _series([500.0] * 21 + [510.0, 500.0])                                 # +1.9%: clears the 1% margin
    assert far.sma_side(d4[22], margin=0.01) == 1
    low, d5 = _series([500.0] * 21 + [490.0, 500.0])
    assert low.sma_side(d5[22], margin=0.01) == -1


def test_side_rule_filter_and_event_skips():
    class Ctx:
        def __init__(self, series, day):
            self.series, self.day = series, day

        def daytype(self):
            raise AssertionError("not needed")
    closes = [500 + k for k in range(25)]
    s, days = _series(closes)
    r = {"filters": ("sma20_side",)}
    sig = lambda side, d: Signal("orb60", "SPY", d, side, 60, 520.0, None, {})
    import sprint.engine as E
    E_ctx = Ctx(s, days[21])
    assert E._filters_ok(dict(r, filters=()), E_ctx, sig("C", days[21]), 0) is None
    E_ctx.daytype = lambda: type("D", (), {"features": lambda self, i: {}})()
    assert E._filters_ok(r, E_ctx, sig("C", days[21]), 0) is None
    assert "wrong side" in E._filters_ok(r, E_ctx, sig("P", days[21]), 0)
    r1 = {"filters": ("sma20_side_1pct",)}
    assert E._filters_ok(r1, E_ctx, sig("C", days[21]), 0) is None                     # steady climb: >1% above its SMA
    near, dn = _series([500.0] * 21 + [504.0, 500.0])
    cn = Ctx(near, dn[22])
    cn.daytype = E_ctx.daytype
    assert "within 1%" in E._filters_ok(r1, cn, sig("C", dn[22]), 0) and E._filters_ok(r, cn, sig("C", dn[22]), 0) is None
    early = Ctx(s, days[5])
    early.daytype = E_ctx.daytype
    assert "fewer than 20" in E._filters_ok(r, early, sig("C", days[5]), 0)
    ev = {"filters": ("skip_fomc_cpi",)}
    for d, want in ((date(2025, 1, 29), "FOMC"), (date(2025, 10, 24), "CPI"), (date(2025, 1, 30), None)):
        c = Ctx(s, d)
        c.daytype = E_ctx.daytype
        got = E._filters_ok(ev, c, sig("C", d), 0)
        assert (got is None) if want is None else (want in got)
    c = Ctx(s, date(2026, 3, 11))                                                    # CPI calendar not covered: not traded
    c.daytype = E_ctx.daytype
    assert "unknown" in E._filters_ok(ev, c, sig("C", c.day), 0)


def test_event_calendar_is_the_verified_list():
    assert events.is_fomc("2024-11-07") and events.is_fomc("2025-10-29") and not events.is_fomc("2025-08-22")   # notation vote
    assert events.is_cpi("2025-10-24") and not events.is_cpi("2025-10-15") and events.is_cpi("2024-08-14")
    assert events.is_cpi("2026-02-11") is None and events.is_fomc("2024-07-31") is None
    assert {d for d in events.FOMC if d >= "2026"} == set(json.loads((ROOT / "config" / "v4.json").read_text())["fomc_decision_days"])
    assert "bls.gov" in events.SOURCES["CPI"] and "federalreserve.gov" in events.SOURCES["FOMC"]


# ---------------------------------------------------------------- period tag, stress ids, specs
def test_not_seen_by_oa_is_inside_dev_and_still_refuses_l2():
    a, b = periods.period_range("NOT_SEEN_BY_OA")
    assert (a, b) == (date(2024, 8, 1), date(2025, 10, 29)) and periods.DEV[0] <= a and b < date(2025, 10, 30)
    assert periods.guard(a, b) == []
    with pytest.raises(periods.LockedPeriod):
        periods.guard(a - timedelta(days=1), b)


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    root = tmp_path_factory.mktemp("alp")
    SS.write_cache(root, "SPY", SS.weekdays(date(2025, 1, 6), 12), band=0.01, trend={})
    return root


def test_runner_tags_rows_not_seen_by_oa_and_stress_runs_get_their_own_ids(tmp_path, cache):
    spec = {"spec_id": "oa_t", "period": "NOT_SEEN_BY_OA", "symbols": ["SPY"],
            "defaults": {"stop": "fixed", "tp": "none", "time": "b", "contract": "d40-55t45", "side": "C"},
            "blocks": [{"name": "x", "grid": {"entry": ["orb15"], "side": ["C", "P"],
                                              "pair": [{"fixed_stop": 0.2, "fixed_target": 0.6}], "mechanics": ["desk", "oa1m"]}}],
            "robustness": {"top_k": 1, "random_paths": 1, "fake_seeds": 0, "min_trades": 1}}
    p = tmp_path / "oa_t.json"
    p.write_text(json.dumps(spec))
    kw = dict(data_root=cache, chains_dir=tmp_path / "none", out_dir=tmp_path / "o", host_name="h", log=lambda *a: None,
              today=date(2026, 10, 31))
    res = runner.run_spec(p, **kw)
    res5 = runner.run_spec(p, spread_pct=0.05, robust=False, **kw)
    rows = list(csv.DictReader(open(tmp_path / "o" / "runs_h.csv")))
    assert len(rows) == 8 and {r["period_tag"] for r in rows} == {"NOT_SEEN_BY_OA"}
    assert [r["run_id"] for r in rows[4:]] == [f"oa_t-{i:03d}@s5" for i in range(1, 5)]
    assert all("Option Alpha never saw" in r["notes"] for r in rows) and "5.0%" in rows[4]["slippage"]
    assert "fixed -20% of debit" in rows[0]["stop_rule"] and "OA-LIKE" in rows[1]["stop_rule"]
    rep = (tmp_path / "o" / "report_2026-10-31_oa_t.md").read_text()
    assert "Fixed premium stop / target runs" in rep and "never saw" in rep and "Exit families" not in rep
    assert "All runs" not in rep and "All other runs" not in rep                      # no duplicate table
    assert (tmp_path / "o" / "report_2026-10-31_oa_t@s5.md").exists()
    assert (tmp_path / "o" / "trades_oa_t@s5_2026-10-31.csv.gz").exists()


def test_shipped_specs_expand_and_validate():
    want = {"orb_exits_v1": (195, "DEV"), "oa_crosscheck_v1": (444, "NOT_SEEN_BY_OA"), "setups_v1": (58, "DEV")}
    for name, (n, period) in want.items():
        spec = json.loads((ROOT / "sprint" / "specs" / f"{name}.json").read_text())
        runs = engine.expand(spec)
        runner.validate(runs)
        assert len(runs) == n and spec["period"] == period and len({engine.run_key(r) for r in runs}) == n
    oa = engine.expand(json.loads((ROOT / "sprint" / "specs" / "oa_crosscheck_v1.json").read_text()))
    pairs = {(r["exit"].fixed_stop, r["exit"].fixed_target) for r in oa}
    assert pairs == {(0.2, 0.2), (0.2, 0.4), (0.2, 0.6), (0.15, 0.45), (0.1, 0.3), (0.5, 1.0)}
    t1 = [r for r in oa if (r["exit"].fixed_stop, r["exit"].fixed_target) == (0.5, 1.0) and r["entry"] == "orb60"]
    assert {r["exit"].contract for r in t1} == {"d40-55t45", "d45-60t50"} and len(t1) == 24
    spy_c = next(r for r in oa if r["symbols"] == ("SPY",) and r["side"] == "C" and r["exit"].fixed_target == 0.6 and not r["filters"]
                 and r["exit"].mechanics == "desk" and r["entry"] == "orb60")
    got = {(w, v) for w, v, _ in engine.nudges(spy_c)}
    assert ("fixed_stop", 0.15) in got and ("fixed_stop", 0.25) in got and ("fixed_target", 0.45) in got and ("fixed_target", 0.75) in got
    st = engine.expand(json.loads((ROOT / "sprint" / "specs" / "setups_v1.json").read_text()))
    assert {r["entry"] for r in st} == {"noise", "noise_nocap", "vwap_macd", "pd_retest", "failed_break", "flush"}
    assert {r["side"] for r in st if r["entry"] == "failed_break"} == {"C"}
    assert all(r["exit"].stop == "noise" for r in st if r["entry"] == "noise_nocap")


# ---------------------------------------------------------------- optimizer leads: VIX falling (proxy: VIXY) and the gap rule
def _ctx_with_vixy(vixy_prev_close, vixy_today, day=DAY, spy_open=None, spy_prev=500.0):
    """A SPY context plus a VIXY Series: VIXY's prior day flat at vixy_prev_close, today's closes from vixy_today."""
    ctx, tape = SS.make_ctx(day, {0: spy_open} if spy_open else {}, {0: 1.0}, prior_days=2, px=spy_prev)
    prev = [d for d in SS.weekdays(day - timedelta(days=7), 10) if d < day][-1]
    rows = SS.flat_day_df(prev, vixy_prev_close)
    cur = vixy_prev_close
    today = []
    for m in range(240, 960):
        i = m - 570
        if i in vixy_today:
            cur = vixy_today[i]
        today.append((pd.Timestamp(f"{day} {m // 60:02d}:{m % 60:02d}", tz="America/New_York"), cur, cur + 0.01, cur - 0.01, cur, 100.0))
    vdf = pd.concat([rows, pd.DataFrame(today, columns=["ts", "o", "h", "l", "c", "v"])], ignore_index=True)
    ctx.aux = {"VIXY": Series("VIXY", vdf)}
    return ctx


def test_vixy_falling_uses_the_last_finished_vixy_close_vs_its_prior_close():
    import sprint.engine as E
    r = {"filters": ("vixy_falling",)}
    sig = lambda side, i: Signal("orb60", "SPY", DAY, side, i, 500.0, None, {})
    ctx = _ctx_with_vixy(20.0, {0: 20.2, 50: 19.8, 90: 20.5})          # above, then below from 10:20, then above from 11:00
    assert "not below" in E._filters_ok(r, ctx, sig("C", 40), 0)
    assert E._filters_ok(r, ctx, sig("C", 60), 0) is None and E._filters_ok(r, ctx, sig("P", 60), 0) is None   # both sides
    assert "not below" in E._filters_ok(r, ctx, sig("C", 95), 0)
    later = _ctx_with_vixy(20.0, {0: 20.2, 50: 19.8, 61: 30.0})        # VIXY spikes after the decision: no effect
    assert E._filters_ok(r, later, sig("C", 60), 0) is None
    none = _ctx_with_vixy(20.0, {0: 19.0})
    none.aux = {}
    assert "no VIXY" in E._filters_ok(r, none, sig("C", 60), 0)


def test_gap_side_rule_both_sides():
    import sprint.engine as E
    r = {"filters": ("gap_side_075",)}
    sig = lambda side: Signal("orb60", "SPY", DAY, side, 70, 503.0, None, {})
    for open_px, c_ok, p_ok in ((502.0, True, False), (503.75, True, False), (504.0, False, False), (500.0, False, False),
                                (498.0, False, True), (496.25, False, True), (495.0, False, False)):
        ctx = _ctx_with_vixy(20.0, {}, spy_open=open_px)
        assert (E._filters_ok(r, ctx, sig("C"), 0) is None) == c_ok, open_px
        assert (E._filters_ok(r, ctx, sig("P"), 0) is None) == p_ok, open_px


def test_puller_pulls_vixy_as_stock_bars_only(tmp_path, monkeypatch):
    import pull_alpaca as PA
    import sprint_pull as SPL
    from test_sprint_runner import FakeAlpaca
    days = SS.weekdays(date(2025, 3, 3), 3)
    fake = FakeAlpaca(pd.concat([SS.stock_day(d, 500, k) for k, d in enumerate(days)], ignore_index=True))
    monkeypatch.setattr(PA, "_http", fake)
    monkeypatch.setattr(PA, "_calls", [])
    monkeypatch.setattr(PA, "ROOT", PA.ROOT)
    monkeypatch.setenv("ALPACA_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET", "s")
    assert SPL.main(["--symbols", "SPY", "--from", "2025-03-03", "--to", "2025-03-05", "--band", "0.005",
                     "--root", str(tmp_path / "alpaca")]) == 0
    assert any("/v2/stocks/VIXY/bars" in c for c in fake.calls)
    assert not any("VIXY" in c for c in fake.calls if "/options/" in c)
    assert (tmp_path / "alpaca" / "stocks" / "VIXY" / "2025-03.csv.gz").exists()
    assert not (tmp_path / "alpaca" / "options" / "VIXY").exists()
    assert (tmp_path / "sprint" / "gaps_VIXY_2025-03-03_2025-03-05.json").exists()     # reports next to the cache, not in the repo
