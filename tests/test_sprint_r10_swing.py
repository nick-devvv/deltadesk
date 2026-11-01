"""Round 10's swing families (sprint/r10swing.py, SPRINT_PLAN Amendment 16) on hand-built data: the trial count and the run-log
total, the monthly schedule and the 2.02 exit, the sort keys from prior-close data only, RV252 across the locked gap, the
straddle and the iron condor (legs, fills at mid / 50% / 100% of the spread, settlement, margin return), the random-name
benchmark and the pass bar, V3's dates, momentum cut, random dates and options twin, V4's book (signal, trailing stop, slots,
ties), its option twin's rolls, and no look-ahead anywhere. Synthetic data only."""
import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sprint_synth  # noqa: F401
import sprint_r10_swing as T10
from sprint import bs, edgar, periods
from sprint import spread_est as SE
from sprint import ivdata as IV
from sprint import r10swing as SW
from sprint import spread as SP
from sprint import universe as U
from sprint.catalyst import occ
from sprint.data import parse_occ

CAL = edgar.Calendar()


# ---------------------------------------------------------------- helpers
def _days(a, n):
    return U.sessions(date.fromisoformat(a), date(2026, 6, 30))[:n]


def _frame(days, c, o=None, h=None, lo=None, v=1_000_000.0):
    c = np.asarray(c, float)
    o = np.concatenate([[c[0]], c[:-1]]) if o is None else np.asarray(o, float)
    h = np.maximum(o, c) if h is None else np.asarray(h, float)
    lo = np.minimum(o, c) if lo is None else np.asarray(lo, float)
    v = np.full(len(c), v) if np.isscalar(v) else np.asarray(v, float)
    return pd.DataFrame({"o": o, "h": h, "l": lo, "c": c, "v": v}, index=list(days))


class Everything(set):
    def __contains__(self, x):
        return True


class FakeBars:
    def __init__(self, last=None, opens=None, first=None, stock=None, asked=None):
        self._last, self._opens, self._first, self._stock = last or {}, opens or {}, first or {}, stock or {}
        self._asked = asked if asked is not None else Everything()

    def last15(self, day):
        return self._last.get(day, {})

    def opens(self, day):
        f = self._opens
        return f(day) if callable(f) else f.get(day, {})

    def first_prints(self, day):
        f = self._first
        return f(day) if callable(f) else f.get(day, {})

    def stock_minutes(self, day):
        return self._stock.get(day)

    def asked(self, day, window):
        a = self._asked
        return a(day, window) if callable(a) else a

    def printed(self, day, window):
        return set()


# ---------------------------------------------------------------- trials and the run log
def test_trials_are_seven_and_the_run_log_total_follows_amendment_16():
    assert SW.SWING_TRIALS == 7 and sum(SW.TRIALS.values()) == 7 and SW.ROUND10_TOTAL == 7767
    assert [SW.TRIALS[k] for k in sorted(SW.TRIALS)] == [1, 1, 1, 2, 2]
    t = T10.trials(1801)
    assert t["r10swing"] == 7 and t["round10"] == 7767 and t["prior_in_run_logs"] == 1801 and t["total_for_dsr"] == 1801 + 7767
    plan = (Path(SW.__file__).resolve().parents[1] / "docs" / "research" / "SPRINT_PLAN.md").read_text()
    amd = plan[plan.index("## Amendment 16"):]
    assert re.search(r"\| V1, V2, V2-s \| 3 \|", amd) and re.search(r"\| V3 shares \+ options \| 2 \|", amd)
    assert re.search(r"\| V4 shares \+ options \| 2 \|", amd) and "**7,767**" in amd


# ---------------------------------------------------------------- the schedule and the report exit
def test_rebalance_days_and_holds():
    h, dropped = SW.holds()
    firsts = [t for t, _ in h]
    assert firsts[0] == date(2024, 8, 1) and h[0][1] == date(2024, 9, 3) and h[-1] == (date(2026, 5, 1), date(2026, 6, 1))
    assert len(h) == 22 and dropped == [(date(2026, 6, 1), date(2026, 7, 1), "the hold ends inside L1/L2 or after DEV")]
    for t, x in h:
        assert not periods.overlaps(t, x) and CAL.is_session(t)
        assert all(d.month != t.month for d in U.all_sessions_cal(date(t.year, t.month, 1), t - timedelta(days=1)))


@pytest.mark.parametrize("acc,want", [
    (None, date(2025, 4, 1)),
    (datetime(2025, 3, 13, 7, 0), date(2025, 3, 12)),       # before the open: out at the session before
    (datetime(2025, 3, 13, 16, 5), date(2025, 3, 13)),      # after the close: that day's 15:45 is before it
    (datetime(2025, 3, 13, 12, 0), date(2025, 3, 12)),      # during the session: before that day's 15:45? no -> the day before
    (datetime(2025, 3, 13, 15, 50), date(2025, 3, 13)),
    (datetime(2025, 3, 15, 10, 0), date(2025, 3, 14)),      # a Saturday filing
    (datetime(2025, 3, 3, 8, 0), date(2025, 4, 1)),         # before the entry: not inside the hold
    (datetime(2025, 4, 1, 15, 45), date(2025, 3, 31)),      # at the exit's 15:45: inside, out the session before
    (datetime(2025, 4, 1, 15, 50), date(2025, 4, 1)),       # after the exit's 15:45: outside the hold
    (datetime(2025, 3, 3, 16, 5), None),                    # right after the entry: no hold left
    (datetime(2025, 3, 4, 7, 0), None)])
def test_hold_exit_is_the_last_1545_before_the_report(acc, want):
    t, x = date(2025, 3, 3), date(2025, 4, 1)
    got, a = SW.hold_exit(t, x, [acc] if acc else [], CAL)
    assert got == want
    two, a2 = SW.hold_exit(t, x, [datetime(2025, 3, 20, 7, 0), datetime(2025, 3, 13, 16, 5)], CAL)
    assert two == date(2025, 3, 13) and a2 == datetime(2025, 3, 13, 16, 5)


# ---------------------------------------------------------------- the sort keys
def test_keys_use_five_session_means_through_the_prior_close_only():
    days = IV.dev_days()[100:110]
    names = [f"N{k:02d}" for k in range(12)]
    tab = IV.IVTable(days, names)
    for t, d in enumerate(days):
        for j, n in enumerate(names):
            tab.set(d, n, {"iv30": 0.30 + 0.01 * j, "iv90": 0.30 + 0.01 * j + (0.02 if j % 3 == 0 else 0.0) - 0.001 * t})
    t = days[7]
    rv = {n: 0.5 for n in names}
    k1 = SW.keys_on(t, tab, names, rv)
    m30 = np.mean([0.30 + 0.01 * 0] * 5)
    assert k1["ratio"]["N00"] == pytest.approx(math.log(0.5 / m30))
    assert k1["slope"]["N03"] == pytest.approx(0.02 - 0.001 * np.mean(range(2, 7)))
    for d in days[7:]:                                       # the decision day and later change: the keys do not
        for n in names:
            tab.set(d, n, {"iv30": 5.0, "iv90": 0.01})
    assert SW.keys_on(t, tab, names, rv) == k1
    top = SW.top(k1["slope"])
    assert set(top[:4]) == {"N00", "N03", "N06", "N09"} and len(top) == 10
    assert SW.top(k1["ratio"], bottom=True)[0] == "N11" and SW.top(k1["ratio"])[0] == "N00"
    assert SW.top({"B": 1.0, "A": 1.0, "C": 2.0}, n=2) == ["C", "A"]          # ties: symbol
    assert "N05" not in SW.keys_on(t, tab, names, {"N05": float("nan")})["ratio"]


def test_rv252_reaches_back_across_l2_without_the_gap_return_and_never_ahead():
    days = U.sessions(date(2023, 1, 3), date(2024, 9, 30))
    rng = np.random.default_rng(5)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, len(days))))
    p = SW.HLPanel(["SPY"], {"SPY": _frame(days, c)}, None, days)
    rv = SW.rv252_prior(p)[:, 0]
    k = days.index(date(2024, 8, 5))                         # decided with closes through 2024-08-02
    closes = c[k - 252:k]
    dd = days[k - 252:k]
    r = [math.log(b / a) for a, b, da, db in zip(closes, closes[1:], dd, dd[1:]) if not (da <= date(2024, 1, 31) and db >= date(2024, 8, 1))]
    assert len(r) == 250 and rv[k] == pytest.approx(np.std(r, ddof=1) * math.sqrt(252))
    c2 = c.copy()
    c2[k:] *= 3.0
    p2 = SW.HLPanel(["SPY"], {"SPY": _frame(days, c2)}, None, days)
    assert SW.rv252_prior(p2)[k, 0] == rv[k]


# ---------------------------------------------------------------- the straddle and the condor
E30 = date(2025, 3, 28)


def _pidx(sym, exp, strikes, rights, px=lambda k, r: 2.0, minute=385):
    return {sym: {(exp, float(k), r): (occ(sym, exp, r, k), minute, px(k, r)) for k in strikes for r in rights}}


def test_straddle_strike_needs_both_legs_and_is_nearest_spot():
    pidx = _pidx("ABC", E30, [100, 101], ["C", "P"])
    del pidx["ABC"][(E30, 101.0, "P")]
    pos, _ = SW.choose_straddle("ABC", pidx, 100.8, E30)
    assert pos["strike"] == 100.0 and [s for s, _ in pos["legs"]] == [occ("ABC", E30, "C", 100), occ("ABC", E30, "P", 100)]
    pidx = _pidx("ABC", E30, [100, 101], ["C", "P"])
    assert SW.choose_straddle("ABC", pidx, 100.5, E30)[0]["strike"] == 100.0          # tie -> lower
    assert SW.choose_straddle("ABC", pidx, 100.6, E30)[0]["strike"] == 101.0
    assert SW.choose_straddle("ABC", pidx, 100.6, None)[0] is None
    assert SW.choose_straddle("ABC", _pidx("ABC", E30, [100], ["C"]), 100.0, E30)[0] is None


def test_straddle_fills_at_mid_half_and_full_spread_and_settlement():
    pidx = _pidx("ABC", E30, [100], ["C", "P"], px=lambda k, r: 3.0 if r == "C" else 2.0)
    pos, _ = SW.choose_straddle("ABC", pidx, 100.0, E30)
    sp = SP.SpreadModel(pct=0.10)
    ex = {pos["legs"][0][0]: (388, 5.0), pos["legs"][1][0]: (388, 0.5)}
    res, labels = SW.price_position(pos, ex, None, "ABC", sp)
    for kn, k in (("mid", 0.0), ("50", 0.5), ("100", 1.0), ("2x", 2.0)):
        buy = 3.0 * (1 + 0.1 * k) + 2.0 * (1 + 0.1 * k)
        sell = 5.0 * (1 - 0.1 * k) + max(0.0, 0.5 - max(0.05, 0.005) * k)
        pnl = 100 * (sell - buy) - 4 * 0.65
        assert res[kn]["pnl"] == pytest.approx(pnl) and res[kn]["capital"] == pytest.approx(100 * buy + 2 * 0.65)
        assert res[kn]["ret"] == pytest.approx(pnl / (100 * buy + 2 * 0.65))
    assert labels == ["MODELED-SPREAD"]
    res, _ = SW.price_position(pos, None, 104.0, "ABC", sp)           # settled at intrinsic: no spread, no exit fee
    assert res["100"]["pnl"] == pytest.approx(100 * (4.0 - 3.3 - 2.2) - 2 * 0.65)


def _bs_pidx(sym, day, exp, spot, iv, strikes):
    T = bs.t_years(IV.t_minutes(day, 385, exp))
    out = {}
    for k in strikes:
        for r in ("C", "P"):
            out[(exp, float(k), r)] = (occ(sym, exp, r, k), 385, round(bs.price(spot, k, T, iv, r), 2))
    return {sym: out}


def test_condor_legs_at_20_and_10_delta_from_the_days_iv_and_return_on_margin():
    day, spot, iv = date(2025, 3, 3), 100.0, 0.40
    pidx = _bs_pidx("ABC", day, E30, spot, iv, range(70, 131))
    pos, why = SW.choose_condor("ABC", pidx, spot, E30, day, iv)
    assert why is None
    k = pos["strikes"]
    T = bs.t_years(IV.t_minutes(day, SW.DECISION_MIN, E30))
    for leg, right, tgt in (("sc", "C", 0.20), ("lc", "C", 0.10), ("sp", "P", 0.20), ("lp", "P", 0.10)):
        d = abs(float(IV.delta_vec(spot, k[leg], T, iv, right == "C")))
        assert abs(d - tgt) < 0.02 and pos["deltas"][leg] == pytest.approx(d, abs=1e-3)
    assert k["lp"] < k["sp"] < spot < k["sc"] < k["lc"] and pos["width"] == max(k["lc"] - k["sc"], k["sp"] - k["lp"])
    signs = dict(pos["legs"])
    assert signs[occ("ABC", E30, "C", k["sc"])] == -1 and signs[occ("ABC", E30, "P", k["lp"])] == 1
    sp = SP.SpreadModel(pct=0.10)
    exit_px = {s: (388, 0.05) for s, _ in pos["legs"]}
    res, _ = SW.price_position(pos, exit_px, None, "ABC", sp)
    e = {s: pos["entry"][s][1] for s, _ in pos["legs"]}
    for kn, kk in (("mid", 0.0), ("100", 1.0)):
        cash_in = sum(-sg * (max(0.0, e[s] - kk * max(0.1 * e[s], 0.005)) if sg < 0 else e[s] + kk * max(0.1 * e[s], 0.005)) * 100
                      for s, sg in pos["legs"])
        cash_out = sum(sg * max(0.0, 0.05 - sg * kk * 0.005) * 100 for s, sg in pos["legs"])
        pnl = cash_in + cash_out - 8 * 0.65
        margin = 100 * pos["width"] - (cash_in - 4 * 0.65)
        assert res[kn]["pnl"] == pytest.approx(pnl) and res[kn]["capital"] == pytest.approx(margin)
        assert res[kn]["ret"] == pytest.approx(pnl / margin)
    assert SW.choose_condor("ABC", pidx, spot, E30, day, float("nan"))[0] is None
    one_side = {"ABC": {kk: v for kk, v in pidx["ABC"].items() if kk[2] == "C"}}
    assert SW.choose_condor("ABC", one_side, spot, E30, day, iv)[0] is None


def _tab_one(day, name, exp, spot, iv=0.4):
    tab = IV.IVTable([day], [name])
    tab.set(day, name, {"iv30": iv, "exp30": exp.isoformat(), "spot": spot})
    return tab


def _panel_one(name, a, b, close=100.0):
    days = U.sessions(a, b)
    return {"all": SW.HLPanel([name], {name: _frame(days, np.full(len(days), close))}, None, days), "univ": {name: "U-STK"}}


def test_position_outcome_traded_exit_settled_expiry_and_report_exit():
    t, x = date(2025, 3, 3), date(2025, 4, 1)
    sp = SP.SpreadModel(pct=0.02)
    panels = _panel_one("ABC", date(2025, 1, 2), date(2025, 6, 30), close=104.0)
    late = date(2025, 4, 17)
    ent = _pidx("ABC", late, [100], ["C", "P"], px=lambda k, r: 3.0)
    ext = _pidx("ABC", late, [100], ["C", "P"], px=lambda k, r: 4.0 if r == "C" else 1.0)
    ctxd = {"bars": FakeBars(last={t: ent, x: ext}), "tab": _tab_one(t, "ABC", late, 100.0), "reports": {}, "cal": CAL,
            "panels": panels, "spread": sp}
    row, why = SW.position_outcome("ABC", t, x, "straddle", ctxd)
    assert why is None and row["exit_day"] == "2025-04-01" and not row["settled"] and row["day"] == "2025-04-01"
    assert row["pnl_mid"] == pytest.approx(100 * (5.0 - 6.0) - 4 * 0.65)
    # a weekly 30-day expiry before the next rebalance: settled at intrinsic on the expiry day's close (104)
    ctxd["tab"] = _tab_one(t, "ABC", E30, 100.0)
    ctxd["bars"] = FakeBars(last={t: _pidx("ABC", E30, [100], ["C", "P"], px=lambda k, r: 3.0)})
    row, _ = SW.position_outcome("ABC", t, x, "straddle", ctxd)
    assert row["settled"] and row["exit_day"] == E30.isoformat() and row["pnl_mid"] == pytest.approx(100 * (4.0 - 6.0) - 2 * 0.65)
    # a 2.02 inside the hold: out at the last 15:45 before it
    early = date(2025, 3, 12)
    ctxd["tab"] = _tab_one(t, "ABC", late, 100.0)
    ctxd["bars"] = FakeBars(last={t: ent, early: ext})
    ctxd["reports"] = {"ABC": [datetime(2025, 3, 13, 7, 0)]}
    row, _ = SW.position_outcome("ABC", t, x, "straddle", ctxd)
    assert row["exit_day"] == "2025-03-12" and row["report_exit"] == "2025-03-13 07:00:00" and row["scheduled_exit"] == "2025-04-01"
    # no exit print: not counted
    ctxd["bars"] = FakeBars(last={t: ent})
    assert SW.position_outcome("ABC", t, x, "straddle", ctxd) == (None, "no exit print 15:45-15:59 for every leg")


# ---------------------------------------------------------------- the benchmark and the pass bar
def _outs(n_names=30, good=0.15, rest=-0.02):
    outs = []
    for k, (t, x) in enumerate(SW.holds()[0]):
        names = [f"N{j:02d}" for j in range(n_names)]
        st = {}
        for j, nm in enumerate(names):
            r = good if j < 10 else rest
            if k % 7 == 3 and j < 10:
                r = -0.05
            st[nm] = {"symbol": nm, "day": x.isoformat(), "entry_day": t.isoformat(), "ret_100": r, "ret_mid": r + 0.02, "ret_50": r + 0.01,
                      "ret_2x": r - 0.02, "ret_m10": r - 0.05, "ret_m2": r, "pnl_100": 100 * r, "pnl_mid": 100 * r + 2,
                      "pnl_50": 100 * r + 1, "pnl_2x": 100 * r - 2, "pnl_m10": 100 * r - 5, "pnl_m2": 100 * r}
        keys = {"slope": {nm: -j for j, nm in enumerate(names)}, "ratio": {nm: -j for j, nm in enumerate(names)}}
        outs.append({"t": t, "x": x, "keys": keys, "eligible": {"V1": names, "V2": names, "V2-s": names},
                     "picks": {"V1": SW.top(keys["slope"]), "V2": SW.top(keys["ratio"]), "V2-s": SW.top(keys["ratio"], bottom=True)},
                     "straddle": st, "condor": st, "skips": {}})
    return outs


def test_benchmark_is_deterministic_and_the_pass_bar():
    outs = _outs()
    p1, m1 = SW.benchmark(outs, "V1")
    p2, m2 = SW.benchmark(outs, "V1")
    assert p1 == p2 and np.array_equal(m1, m2) and len(m1) == 200
    assert -0.02 < p1 < 0.15
    rows, sk = SW.rule_positions(outs, "V1")
    assert len(rows) == 220 and not sk and rows[0]["rank"] == 1 and rows[0]["variant"] == "term_slope"
    pb = SW.vol_pass(rows, p1)
    assert pb["pass"], pb["checks"]
    bad, _ = SW.rule_positions(outs, "V2-s")                  # the bottom 10: the losers
    assert not SW.vol_pass(bad, SW.benchmark(outs, "V2-s")[0])["pass"]
    assert not SW.vol_pass(rows[:99], p1)["pass"]             # fewer than 100 positions
    assert not SW.vol_pass(rows, 0.5)["pass"]                 # not above the random draws' 90th percentile
    res, rr = SW.vol_family(outs)
    res2, _ = SW.vol_family(outs)
    assert res == res2 and res["V1"]["pass"] and set(rr) == {"V1", "V2", "V2-s"}
    assert res["overlap_V1_V2"]["total_shared"] == 220 and res["overlap_V1_V2"]["share_of_v2_names_in_v1"] == 1.0
    b = SW.blocks(rows)
    assert list(b) == [x[0] for x in SW.BLOCKS] and all(v["positions"] for v in b.values())


# ---------------------------------------------------------------- V3
def test_v3_dates_are_5_sessions_before_and_out_before_the_report():
    assert SW.report_exit_entry(datetime(2025, 3, 13, 16, 5), CAL) == (date(2025, 3, 6), date(2025, 3, 13))
    assert SW.report_exit_entry(datetime(2025, 3, 13, 7, 0), CAL) == (date(2025, 3, 6), date(2025, 3, 12))
    assert SW.report_exit_entry(datetime(2025, 3, 13, 12, 0), CAL) == (date(2025, 3, 6), date(2025, 3, 12))
    assert SW.report_exit_entry(datetime(2025, 3, 15, 9, 0), CAL) == (date(2025, 3, 10), date(2025, 3, 14))


def _momentum_panel(n=12, length=320, a="2017-01-03"):
    days = _days(a, length)
    frames = {}
    for j in range(n):
        g = 0.0004 * (j - 5)
        c = 100 * np.exp(g * np.arange(length))
        frames[f"S{j:02d}"] = _frame(days, c, v=2_000_000.0)
    syms = sorted(frames)
    return SW.HLPanel(syms, frames, None, days), days


def test_v3_top_decile_by_12_1_return_and_the_trade():
    p, days = _momentum_panel()
    r = SW.ret_12_1(p)
    k = 300
    assert np.isnan(r[251, 0]) and r[k, 11] == pytest.approx(p.adj_c[k - 21, 11] / p.adj_c[k - 252, 11] - 1)
    rec = lambda sym, d: {"form": "8-K", "items": ["2.02"], "accepted": f"{d} 16:05:00", "cik": {"S11": 11, "S05": 5}[sym]}
    tmap = {11: ["S11"], 5: ["S05"]}
    d_rep = days[310]
    ev = SW.v3_events([rec("S11", d_rep), rec("S05", d_rep), rec("S11", d_rep)], tmap, CAL)
    assert len(ev) == 2 and ev[0]["entry"] == days[305] and ev[0]["exit"] == d_rep
    tr, info = SW.v3_trades(p, ev)
    assert [t["symbol"] for t in tr] == ["S11"] and info["dropped"] == {"not in the top 10% by 12-1 return": 1}
    t = tr[0]
    sh = math.floor(10_000 / p.raw_c[305, 11])
    move = p.raw_c[305, 11] * (p.adj_c[310, 11] / p.adj_c[305, 11]) - p.raw_c[305, 11]
    assert t["shares"] == sh and t["hold"] == 5 and t["entry_day"] == days[305].isoformat()
    assert t["pnl"] == pytest.approx(sh * move - 0.0005 * sh * (2 * p.raw_c[305, 11] + move), abs=1e-3)
    assert t["rank_share"] == 0.0 and t["label"].startswith(U.SB)


def test_v3_12_1_return_has_no_look_ahead_and_stays_in_its_segment():
    p, days = _momentum_panel()
    r1 = SW.ret_12_1(p)
    frames = {s: _frame(days, np.where(np.arange(len(days)) >= 290, p.adj_c[:, p.col[s]] * 2.0, p.adj_c[:, p.col[s]]), v=2_000_000.0)
              for s in p.symbols}
    p2 = SW.HLPanel(p.symbols, frames, None, days)
    assert np.array_equal(SW.ret_12_1(p2)[:290], r1[:290], equal_nan=True)
    dd = U.sessions(date(2023, 1, 3), date(2026, 6, 30))
    seg = SW.HLPanel(["X"], {"X": _frame(dd, np.linspace(10, 20, len(dd)))}, None, dd)
    rr = SW.ret_12_1(seg)[:, 0]
    k0 = dd.index(date(2024, 8, 1))
    assert np.isnan(rr[k0:k0 + 252]).all() and np.isfinite(rr[k0 + 252])


def test_v3_random_dates_stay_10_sessions_from_reports_and_are_deterministic():
    p, days = _momentum_panel()
    pos = lambda d: CAL.pos[d]
    reps = {"S11": np.array([pos(days[200]), pos(days[260])])}
    e = SW.v3_candidates(p, "S11", 5, reps["S11"], CAL)
    assert len(e)
    for k in e:
        for r in reps["S11"]:
            assert abs(pos(days[k]) - r) >= 10 and abs(pos(days[k + 5]) - r) >= 10
    assert 185 in e and 186 not in e and 190 not in e and 209 not in e and 210 in e        # entry AND exit 10+ sessions away
    tr = [{"symbol": "S11", "hold": 5, "pnl": 10.0}, {"symbol": "S11", "hold": 4, "pnl": -3.0}]
    a = SW.v3_random(p, tr, reps, CAL)
    b = SW.v3_random(p, tr, reps, CAL)
    assert a[0] == b[0] and np.array_equal(a[1], b[1]) and len(a[1]) == 200


def test_v3_twin_expiry_after_the_report_and_the_delta_pick():
    assert SW.expiry_after(datetime(2025, 3, 14, 7, 0)) == [[date(2025, 3, 14)], [date(2025, 3, 21)]]
    assert SW.expiry_after(datetime(2025, 3, 14, 16, 5)) == [[date(2025, 3, 21)]]
    assert SW.expiry_after(datetime(2025, 4, 16, 16, 5)) == [[date(2025, 4, 17)]]           # Good Friday -> Thursday
    day, exp, S = date(2025, 3, 7), date(2025, 3, 21), 100.0
    pidx = {"ABC": {(exp, float(k), "C"): (occ("ABC", exp, "C", k), 386, bs.price(S, k, bs.t_years(IV.t_minutes(day, 386, exp)), 0.5, "C"))
                    for k in np.arange(94, 103, 0.5)}}
    sm = {"ABC": {386: S}}
    info, why = SW.pick_last15("ABC", day, pidx, sm, [exp], SW.V3_BAND)
    assert why is None and 0.50 <= info["delta"] <= 0.60
    T = bs.t_years(IV.t_minutes(day, 386, exp))
    ds = {k: float(IV.delta_vec(S, k, T, 0.5, True)) for k in np.arange(94, 103, 0.5)}
    assert info["strike"] == min((k for k in ds if 0.5 <= ds[k] <= 0.6), key=lambda k: abs(ds[k] - 0.55))
    assert info["iv"] == pytest.approx(0.5, abs=1e-3)
    assert SW.pick_last15("ABC", day, pidx, {"ABC": {}}, [exp], SW.V3_BAND)[0] is None     # no stock bar in the print minute
    rows = [{"pnl": 50.0}, {"pnl": 30.0}]
    pool = [{"event": 0, "pnl": -10.0}, {"event": 0, "pnl": 5.0}, {"event": 1, "pnl": -20.0}]
    p, means, n = SW.twin_random(rows, pool)
    assert p == 0.0 and n == 2 and len(means) == 200 and SW.twin_random(rows, pool)[0] == p


def test_v3_twin_row_costs_are_f_opts():
    day, x, exp = date(2025, 3, 7), date(2025, 3, 13), date(2025, 3, 14)
    S = 100.0
    T = bs.t_years(IV.t_minutes(day, 386, exp))
    pidx = {"ABC": {(exp, float(k), "C"): (occ("ABC", exp, "C", k), 386, bs.price(S, k, T, 0.6, "C")) for k in range(94, 104)}}
    it = {"kind": "event", "n": 0, "symbol": "ABC", "entry": day, "exit": x, "after": datetime(2025, 3, 13, 16, 5), "S": S}
    info, _ = SW.pick_last15("ABC", day, pidx, {"ABC": {386: S}}, [exp], SW.V3_BAND)
    out = {"ABC": {(exp, info["strike"], "C"): (info["symbol"], 388, info["px"] + 1.0)}}
    bars = FakeBars(last={day: pidx, x: out}, stock={day: {"ABC": {386: S}}})
    est = SE.SpreadEst()                                      # no pools: every fill falls back to the 10% default (labeled)
    row, why = SW.v3_twin_row(it, bars, est)
    b_in, b_out = info["px"], info["px"] + 1.0
    f = lambda pct, k: 100 * ((b_out - k * max(pct * b_out, 0.005)) - (b_in + k * max(pct * b_in, 0.005))) - 1.3
    assert why is None and row["pnl"] == pytest.approx(f(0.10, 1), abs=0.01) and row["pnl_2x"] == pytest.approx(f(0.10, 2), abs=0.01)
    assert row["pnl_m2"] == pytest.approx(f(0.02, 1), abs=0.01) == pytest.approx(SW.opt_leg(b_in, b_out), abs=0.01)
    assert row["pnl_mid"] == pytest.approx(100 * (b_out - b_in) - 1.3, abs=0.01) and row["pnl_m10"] == pytest.approx(row["pnl"], abs=0.01)
    assert row["debit"] == pytest.approx(100 * (b_in + max(0.1 * b_in, 0.005)) + 0.65, abs=0.01)
    assert row["spread_label"] == SE.FALLBACK and row["label"].startswith(SW.REAL)
    est = SE.SpreadEst({("ABC", "2025-03", SP._pb(b_in)): (0.01, 9), ("ABC", "2025-03", SP._pb(b_out)): (0.01, 9)}, ratio=2.0)
    row, _ = SW.v3_twin_row(it, bars, est)
    assert row["pnl"] == pytest.approx(100 * ((b_out - 0.02) - (b_in + 0.02)) - 1.3, abs=0.01) and row["spread_label"] == SE.LABEL
    assert SW.v3_twin_row(dict(it, exit=date(2025, 3, 12)), bars, est)[0] is None


# ---------------------------------------------------------------- V4
def test_atr_is_wilder_and_the_prior_high_excludes_today():
    days = _days("2017-01-03", 60)
    rng = np.random.default_rng(2)
    c = 100 + np.cumsum(rng.normal(0, 1, 60))
    h, lo = c + rng.uniform(0.2, 1.5, 60), c - rng.uniform(0.2, 1.5, 60)
    p = SW.HLPanel(["X"], {"X": _frame(days, c, h=h, lo=lo)}, None, days)
    atr = SW.atr_wilder(p, 20)[:, 0]
    tr = [max(h[k] - lo[k], abs(h[k] - c[k - 1]), abs(lo[k] - c[k - 1])) for k in range(1, 60)]
    want = np.mean(tr[:20])
    assert np.isnan(atr[19]) and atr[20] == pytest.approx(want)
    want = (want * 19 + tr[20]) / 20
    assert atr[21] == pytest.approx(want)
    hp = SW.high_prior(p, 10)[:, 0]
    assert np.isnan(hp[9]) and hp[10] == pytest.approx(c[:10].max()) and hp[30] == pytest.approx(c[20:30].max())


def _trend_path(n=330, at=260):
    c = 100 + 0.5 * np.sin(np.arange(n) / 5.0)
    c[at:] = c[at - 1] + 1.5 + 0.4 * np.arange(n - at)                    # a new 252-day high at `at`, then a rally
    c[at + 30:] = c[at + 29] - 0.8 * np.arange(1, n - at - 29)            # then a slide through the stop
    return c


def test_v4_entry_at_the_next_open_trailing_stop_never_lowered_and_exit_at_the_next_open():
    days = _days("2017-01-03", 330)
    c = _trend_path()
    o = np.concatenate([[c[0]], c[:-1]]) + 0.05
    p = SW.HLPanel(["SPY"], {"SPY": _frame(days, c, o=o, h=np.maximum(o, c) + 0.3, lo=np.minimum(o, c) - 0.3)}, None, days)
    tr, info = SW.v4_book(p, {"SPY": "U-ETF"})
    t = tr[0]
    assert t["signal_day"] == days[260].isoformat() and t["entry_day"] == days[261].isoformat()
    atr = SW.atr_wilder(p)[:, 0]
    hc, stop, x_sig = -np.inf, -np.inf, None
    for k in range(261, 330):
        if k > 261 and c[k] < stop:
            x_sig = k
            break
        hc = max(hc, c[k])
        stop = max(stop, hc - 3 * atr[k])
    assert x_sig is not None and t["exit_day"] == days[x_sig + 1].isoformat() and t["stop_at_exit"] == pytest.approx(stop, abs=1e-3)
    sh = math.floor(10_000 / c[260])
    assert t["shares"] == sh and t["entry_ref"] == pytest.approx(o[261]) and t["exit_ref"] == pytest.approx(o[x_sig + 1])
    assert t["pnl"] == pytest.approx(sh * (o[x_sig + 1] - o[261]) - 2 * 0.01 * sh, abs=1e-3)


def test_v4_no_look_ahead():
    days = _days("2017-01-03", 330)
    c = _trend_path()
    p1 = SW.HLPanel(["SPY"], {"SPY": _frame(days, c)}, None, days)
    a, _ = SW.v4_book(p1, {"SPY": "U-ETF"})
    cut = date.fromisoformat(a[0]["exit_day"])
    k = days.index(cut)
    c2 = c.copy()
    c2[k + 1:] = c2[k + 1:] * 1.7
    b, _ = SW.v4_book(SW.HLPanel(["SPY"], {"SPY": _frame(days, c2)}, None, days), {"SPY": "U-ETF"})
    keep = lambda tr: [t for t in tr if t["exit_day"] <= cut.isoformat()]
    assert keep(a) == keep(b) and len(keep(a)) == 1
    assert np.array_equal(SW.high_prior(p1)[:k + 1], SW.high_prior(SW.HLPanel(["SPY"], {"SPY": _frame(days, c2)}, None, days))[:k + 1],
                          equal_nan=True)


def test_v4_ten_slots_go_to_the_higher_20_day_dollar_volume():
    days = _days("2017-01-03", 300)
    syms = [f"S{k:02d}" for k in range(12)]
    frames = {s: _frame(days, _trend_path(300, 260), v=1_000_000.0 * (k + 1)) for k, s in enumerate(syms)}
    p = SW.HLPanel(syms, frames, None, days)
    tr, info = SW.v4_book(p, {s: "U-STK" for s in syms})
    assert info["entries"] == 10 and info["no_slot"] >= 2              # counted on every day the book was full
    assert {t["symbol"] for t in tr} == set(syms[2:])                  # the two lowest dollar volumes never got a slot


def test_top_share_and_windows():
    tr = [{"pnl": float(x), "day": "2018-05-01"} for x in [100, 50, -10, -10, -10, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5]]
    s = SW.top_share(tr)
    assert s["top_n"] == 2 and s["top_pnl"] == 150.0 and s["share"] == pytest.approx(150 / 170, abs=1e-3)
    w = SW.v4_windows([dict(t, pnl_2x=t["pnl"], entry_idx=0, symbol="X", bps=1.0) for t in tr])
    assert w["discovery 2016-2019"]["trades"] == 15 and w["holdout 2020-2023"]["trades"] == 0


def _opens_fn(sym, S, iv):
    def f(day):
        a, b = day + timedelta(days=60), day + timedelta(days=120)
        out = {}
        for e in sorted(set(IV.friday_expiries(a, b)) | set(IV.quarter_ends(a, b))):
            T = bs.t_years(390 + 1440 * (e - day).days)
            for k in range(400, 501, 5):
                out[(e, float(k), "C")] = (occ(sym, e, "C", k), 0, round(bs.price(S, k, T, iv, "C"), 2))
        return {sym: out}
    return f


class _First:
    """first_prints(day) for any held call: its BS price at the open of `day` (S and iv fixed); `missing` never prints."""

    def __init__(self, S, iv, missing=()):
        self.S, self.iv, self.missing, self.day = S, iv, set(missing), None

    def __call__(self, day):
        self.day = day
        return self

    def get(self, sym):
        if sym in self.missing:
            return None
        m = parse_occ(sym)
        T = bs.t_years(390 + 1440 * max((m["expiry"] - self.day).days, 0))
        return (0, round(bs.price(self.S, m["strike"], T, self.iv, "C"), 2))


def test_v4_twin_asks_first_then_rolls_at_30_days_left():
    tr = {"symbol": "SPY", "entry_day": "2025-03-03", "exit_day": "2025-05-15", "pnl": 10.0}
    sess = IV.dev_days()
    S = 500.0
    need = SW.v4_twin_walk(tr, FakeBars(asked=set()), lambda d: S, sess)
    assert need[0] == "need" and need[1][0] == date(2025, 3, 3) and need[1][1] == IV.W_OPEN
    assert set(need[1][2]) == set(SW.v4_probe("SPY", date(2025, 3, 3), S))
    kind, row = SW.v4_twin_walk(tr, FakeBars(opens=_opens_fn("SPY", S, 0.2), first=_First(S, 0.2)), lambda d: S, sess)
    assert kind == "row", row
    legs = json.loads(row["legs"])
    assert row["rolls"] == len(legs) - 1 >= 1
    for g in legs:
        assert 60 <= g["dte"] <= 120 and 0.60 <= g["delta"] <= 0.70
    for g, nxt in zip(legs, legs[1:]):
        exp = parse_occ(g["contract"])["expiry"]
        sell = date.fromisoformat(g["sell_day"])
        assert (exp - sell).days <= 30 and nxt["buy_day"] == g["sell_day"]
        prev = [d for d in sess if date.fromisoformat(g["buy_day"]) < d < sell]
        assert all((exp - d).days > 30 for d in prev)
    assert legs[-1]["sell_day"] == "2025-05-15"
    assert row["pnl_m2"] == pytest.approx(sum(SW.opt_leg(g["buy"], g["sell"]) for g in legs), abs=0.02)
    assert row["pnl"] == pytest.approx(sum(SW.opt_leg(g["buy"], g["sell"], pct=0.02) for g in legs), abs=0.02)  # SPY's 2% default
    kind, r2 = SW.v4_twin_walk(tr, FakeBars(opens=_opens_fn("SPY", S, 0.2), first=_First(S, 0.2)), lambda d: S, sess,
                               {"est": SP.SpreadModel(pct=0.05), "m10": SP.SpreadModel(pct=0.10), "m2": SP.SpreadModel(pct=0.02)})
    assert r2["pnl"] == pytest.approx(sum(SW.opt_leg(g["buy"], g["sell"], pct=0.05) for g in legs), abs=0.02)
    assert r2["pnl_2x"] == pytest.approx(sum(SW.opt_leg(g["buy"], g["sell"], pct=0.05, k=2.0) for g in legs), abs=0.02)
    miss = _First(S, 0.2, missing={legs[0]["contract"]})
    kind, why = SW.v4_twin_walk(tr, FakeBars(opens=_opens_fn("SPY", S, 0.2), first=miss), lambda d: S, sess)
    assert kind == "skip" and "no print of the held call" in why


def test_compounding_view_is_a_marked_hook_until_compound_py_is_merged(monkeypatch):
    import sys
    monkeypatch.delitem(sys.modules, "sprint.compound", raising=False)
    import sprint
    if hasattr(sprint, "compound"):
        monkeypatch.delattr(sprint, "compound")
    try:
        import sprint.compound  # noqa: F401
        pytest.skip("sprint/compound.py is on this branch (merged): the stub test below covers the call")
    except ImportError:
        pass
    v = SW.compounding_view("V1", [{"day": "2025-03-03", "pnl": 1.0, "debit": 100.0}], "debit", ["2025-03-03"])
    assert "sprint/compound.py" in v["hook"] and v["rule"] == "V1"


class _StubCompound:
    """compound.simulate / render_md with round10/noise's interface (sprint/compound.py at 6bb13f3), recording the call."""
    LABEL = "compounding view (information, not trials)"

    def __init__(self):
        self.calls = []

    def simulate(self, rows, sessions=None, start=3000.0, fractions=(0.01, 0.02, 0.05), paths=2000, seed=29, halve=0.5, label=None):
        days = [str(d)[:10] for d in sessions]
        for r in rows:
            assert set(r) >= {"day", "pnl", "risk"} and r["risk"] > 0 and r["day"] in days
        self.calls.append({"rows": rows, "sessions": days, "label": label})
        return {"label": label, "input": {"trades": len(rows), "sessions": len(days)}, "fractions": {"1%": {"median_end": 3000.0}}}

    def render_md(self, view, title="Compounding view"):
        return [f"- **{title}**", ""]


def test_compounding_view_calls_compound_simulate_with_risk_and_every_session(monkeypatch):
    import sys
    import types
    import sprint
    stub = _StubCompound()
    mod = types.ModuleType("sprint.compound")
    mod.LABEL, mod.simulate, mod.render_md = stub.LABEL, stub.simulate, stub.render_md
    monkeypatch.setitem(sys.modules, "sprint.compound", mod)
    monkeypatch.setattr(sprint, "compound", mod, raising=False)
    sess = ["2025-03-03", "2025-03-04", "2025-03-05"]
    rows = [{"day": "2025-03-04", "pnl": 50.0, "debit": 200.0}, {"day": "2025-03-05", "pnl": -20.0, "debit": 0.0},
            {"day": "2025-06-02", "pnl": 10.0, "debit": 100.0}]
    v = SW.compounding_view("V1", rows, "debit", sess, "V1 term_slope, DEV")
    c = stub.calls[0]
    assert c["sessions"] == sess and c["rows"] == [{"day": "2025-03-04", "pnl": 50.0, "risk": 200.0}]
    assert v["skipped_rows"] == 2 and v["md"][0] == "- **V1 term_slope, DEV**" and "debit" in v["risk"] and "V1" in c["label"]
    sh = [{"day": "2025-03-04", "pnl": 30.0, "shares": 100, "risk_per_share": 1.5, "notional": 10_000.0}]
    SW.compounding_view("V4 shares", sh, "stop", sess)
    SW.compounding_view("V3 shares", sh, "notional", sess)
    SW.compounding_view("V2-s", [{"day": "2025-03-03", "pnl": 5.0, "margin": 400.0}], "margin", sess)
    assert [c["rows"][0]["risk"] for c in stub.calls[1:]] == [150.0, 10_000.0, 400.0]
