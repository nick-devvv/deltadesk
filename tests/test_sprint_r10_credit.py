"""Round 10's 0DTE credit spreads (sprint/r10credit.py; SPRINT_PLAN Addendum 15.4 and Amendment 16 C3/C4): the rules (C1's
direction, straddle strikes and controls; C2's 10-day SMA and VIX-proxy filter; C3's gap filter; C4's fly-or-condor choice; the
BS-EST delta picks), leg pricing (+/- the half-spread, $0.65 per leg per side, MEASURED or max($0.01, 2%)), settlement at
intrinsic (no cost when worthless), the 25% take profit, the 13:00 time exit, the 2x stress, margin and return on margin, the
pass bar, the report numbers, the trial count and the deflated Sharpe's N, the data-needs function, no look-ahead (changing
bars after an entry changes neither the entry, its strikes nor the filters) and restart safety. Synthetic data only."""
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import book, bs, data, periods
from sprint import r10credit as RC
from sprint import spread as SP
from sprint.fills import OptionTape

ET = "America/New_York"


# ---------------------------------------------------------------- synthetic world (also used by test_sprint_r10_credit_tool.py)
def sessions(a, b):
    return [date.fromisoformat(d) for d in book.sessions_between(a, b)]


def rth_grid(df):
    m = (df["ts"].dt.hour * 60 + df["ts"].dt.minute).to_numpy() - 570
    keep = (m >= 0) & (m < 390)
    g = np.full((390, 5), np.nan)
    g[m[keep]] = df[["o", "h", "l", "c", "v"]].to_numpy(float)[keep]
    return g


def option_frame(day, under, g, iv=0.20, band=0.05, floor=0.01):
    """BS-priced 1-minute bars of every $1 strike within band of the open, calls and puts, a print EVERY minute with a $0.01
    floor (real 0DTE wings trade at a penny)."""
    i = np.arange(390)
    Ta = np.maximum(390 - i, bs.MIN_T_MIN) / bs.YEAR_MIN
    Tb = np.maximum(390 - i - 1, bs.MIN_T_MIN) / bs.YEAR_MIN
    o0 = float(g[0, 0])
    ks = np.arange(int(o0 * (1 - band)), int(o0 * (1 + band)) + 2, dtype=float)
    stamps = np.array([f"{day}T{(570 + k) // 60:02d}:{(570 + k) % 60:02d}:00-04:00" for k in i])
    frames = []
    for right in ("C", "P"):
        call = right == "C"
        po = np.maximum(np.round(bs.price_v(g[None, :, 0], ks[:, None], Ta[None, :], iv, call), 2), floor)
        pc = np.maximum(np.round(bs.price_v(g[None, :, 3], ks[:, None], Tb[None, :], iv, call), 2), floor)
        hi, lo = np.maximum(po, pc), np.minimum(po, pc)
        for n, k in enumerate(ks):
            frames.append(pd.DataFrame({"ts": stamps, "o": po[n], "h": hi[n], "l": lo[n], "c": pc[n], "v": 10.0,
                                        "symbol": RC.occ(under, day, right, k)}))
    return pd.concat(frames, ignore_index=True)


def write_world(root, under, days, px0=400.0, seed=1, iv=0.20, band=0.05, vol=0.00025, gaps=None, options=True, drift=0.00001):
    """Stock months (04:00-19:59 bars) + one 0DTE option file a day in the cache layout. gaps: {day: overnight move}; drift:
    per regular-hours minute (a steady rise keeps the prior close above its 10-day SMA, so C2 trades)."""
    import pull_alpaca as PA
    root = Path(root)
    frames, px = [], px0
    for n, d in enumerate(days):
        df = SS.stock_day(d, px * (1 + (gaps or {}).get(d, 0.0)), seed + n, drift=drift, vol=vol)
        frames.append(df)
        px = float(df["c"].iloc[-1])
        if options:
            ob = option_frame(d, under, rth_grid(df), iv=iv, band=band)
            f = root / "options" / under / d.isoformat() / "bars.csv.gz"
            f.parent.mkdir(parents=True, exist_ok=True)
            ob.to_csv(f, index=False, compression="gzip")
    allb = pd.concat(frames, ignore_index=True)
    for m, g in allb.groupby(allb["ts"].dt.strftime("%Y-%m")):
        PA._write_gz(root / "stocks" / under / f"{m}.csv.gz", g.reset_index(drop=True))


CALIB = {"min_n": 30, "keys": {k: {"n": 100, "median": 1.0, "ok": True} for k in ("d40-55t45|C", "d40-55t45|P")}}
DEV_DAYS = sessions("2025-03-03", "2025-04-11")
GAPS = {DEV_DAYS[23]: 0.008, DEV_DAYS[24]: 0.0, DEV_DAYS[26]: -0.009}


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("r10c") / "alpaca"
    write_world(root, "SPY", DEV_DAYS, px0=400.0, seed=31, gaps=GAPS)
    return root


# ---------------------------------------------------------------- hand-built days and tapes
def hand_series(day, prior_closes=(500.0, 500.0), path=None, bars=None, pre=None, sym="SPY", extra_after=None):
    """A Series: flat prior sessions at prior_closes, then `day` whose closes follow path {idx: px} (carried), bars {idx: (o, h,
    l, c)} overrides, premarket bars at `pre` (default: the first price). extra_after: [(day, px)] flat sessions after `day`."""
    prior = [d for d in sessions((day - timedelta(days=60)).isoformat(), (day - timedelta(days=1)).isoformat())][-len(prior_closes):]
    frames = [SS.flat_day_df(d, px) for d, px in zip(prior, prior_closes)]
    path = path or {0: 500.0}
    rows, cur = [], path.get(0, 500.0)
    for m in range(240, 960):
        i = m - 570
        if i < 0:
            p = cur if pre is None else pre
            rows.append((pd.Timestamp(f"{day} {m // 60:02d}:{m % 60:02d}", tz=ET), p, p + 0.01, p - 0.01, p, 1000.0))
            continue
        if i in path:
            cur = path[i]
        o, h, l, c = cur, cur + 0.01, cur - 0.01, cur
        if bars and i in bars:
            o, h, l, c = bars[i]
            cur = c
        rows.append((pd.Timestamp(f"{day} {m // 60:02d}:{m % 60:02d}", tz=ET), o, h, l, c, 1000.0))
    frames.append(pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"]))
    for d, px in extra_after or []:
        frames.append(SS.flat_day_df(d, px))
    df = pd.concat(frames, ignore_index=True)
    return data.Series(sym, df), RC.premarket_prices(df)


def tape(day, right, K, path, under="SPY", no_print=()):
    o = np.full(390, np.nan)
    cur = None
    for i in range(390):
        if i in path:
            cur = path[i]
        if cur is None or i in no_print:
            continue
        o[i] = cur
    t = OptionTape(RC.occ(under, day, right, K), right, K, o, o.copy(), o.copy(), o.copy(), np.where(np.isnan(o), np.nan, 10.0))
    t.expiry = day
    return t


def chain_of(ctx, tapes):
    return RC.Chain(ctx, "REAL", tapes={t.symbol: t for t in tapes})


DAY = date(2025, 3, 12)


def plan_of(rule, legs, j, tp=False, te=None, structure="x"):
    return {"rule": rule, "decision_idx": j, "structure": structure, "legs": legs, "tp": tp, "time_exit_dec": te, "spot_entry": 500.0}


def leg(t, q):
    return {"K": t.strike, "right": t.right, "q": q, "tape": t}


# ---------------------------------------------------------------- trials and the deflated Sharpe's N
def test_trials_are_8_and_the_dsr_uses_run_logs_plus_7767():
    assert RC.R10_CREDIT == 8 == sum(RC.TRIALS.values()) == len(RC.RULES)
    assert sorted(RC.TRIALS.values()) == [3, 5] and RC.ROUND10 == 7767
    assert set(RC.RULES) == {"C1", "C1-ctl", "C1-ic", "C2", "C2-ctl", "C3", "C3-ctl", "C4"}
    t = RC.trials(1801)
    assert t["r10_credit"] == 8 and t["round10"] == 7767 and t["total_for_dsr"] == 1801 + 7767 and t["prior_in_run_logs"] == 1801
    days = book.sessions_between("2024-08-01", "2026-06-30")
    rng = np.random.default_rng(3)
    var = {r: [{"day": d, "pnl": float(rng.normal(0.3 * k, 20))} for d in days[::2]] for k, r in enumerate(RC.RULES)}
    var["C4"] = []
    tab, sv, n = RC.dsr_table(var, 1801, days)
    assert n == 1801 + 7767 and sv > 0 and tab["C4"] is None and all(0 <= tab[r] <= 1 for r in RC.RULES if r != "C4")
    tab2, _sv, n2 = RC.dsr_table(var, 100, days)
    assert n2 == 7867 and all(tab2[r] >= tab[r] for r in RC.RULES if r != "C4")      # fewer trials: a laxer haircut


# ---------------------------------------------------------------- costs
def test_half_spread_is_measured_where_a_cell_has_data_else_max_one_cent_two_pct():
    c = RC.CreditSpread()
    assert c.half_spread("SPY", 0.30) == (0.01, "MODELED-SPREAD")             # 2% of $0.30 = $0.006 -> the $0.01 floor
    assert c.half_spread("SPY", 2.00) == (0.04, "MODELED-SPREAD")
    assert c.half_spread("QQQ", 0.0)[0] == 0.01
    m = RC.CreditSpread({("SPY", SP._pb(2.0), SP._tb(100)): 0.025, ("SPY", SP._pb(2.0), None): 0.03}, {"SPY": {"days": 5, "rows": 99}})
    assert m.half_spread("SPY", 2.0, 100) == (0.025, "MEASURED-SPREAD")
    assert m.half_spread("SPY", 2.0, 10) == (0.03, "MEASURED-SPREAD")         # time cell thin -> the premium bucket over all times
    assert m.half_spread("SPY", 0.3, 100) == (0.01, "MODELED-SPREAD")          # no cell -> the fallback
    assert m.half_spread("QQQ", 2.0, 100) == (0.04, "MODELED-SPREAD")
    assert "max($0.01, 2% of the premium)" in c.describe() and "MEASURED-SPREAD" in m.describe()
    assert isinstance(RC.credit_spread(Path("/nonexistent/chains")), RC.CreditSpread)


# ---------------------------------------------------------------- leg pricing, settlement, stress, margin
@pytest.mark.parametrize("close,pnl,pnl2,itm", [(500.0, 54.70, 50.70, 0), (492.0, -247.95, -253.95, 1), (480.0, -450.60, -458.60, 2)])
def test_put_vertical_held_to_the_close(close, pnl, pnl2, itm):
    ser, _pm = hand_series(DAY, path={0: 500.0, 389: close})
    ctx = data.DayContext(ser, DAY, {}, None)
    s, l = tape(DAY, "P", 495.0, {0: 1.00}), tape(DAY, "P", 490.0, {0: 0.40})
    t, why = RC.simulate(plan_of("C1-ctl", [leg(s, -1), leg(l, +1)], 59), ctx, SS.ConstSpread(0.02))
    assert why is None
    # entry at the 10:30 bar's open: short 1.00 - 0.02, long 0.40 + 0.02 -> credit 0.56; $0.65 per leg per side
    assert t["credit"] == pytest.approx(0.56) and t["credit_2x"] == pytest.approx(0.52)
    assert t["pnl"] == pytest.approx(pnl) and t["pnl_2x"] == pytest.approx(pnl2)
    assert t["margin"] == pytest.approx(444.0) and t["max_loss"] == pytest.approx(446.6)
    assert t["ret_margin"] == pytest.approx(round(pnl / 444.0, 4))
    assert t["exit_reason"] == "SETTLED" and t["legs_itm_at_close"] == itm and t["legs_settled"] == 2 and t["exit_time"] == "16:00"
    assert t["entry_idx"] == 60 and t["entry_time"] == "10:30" and t["short_put"] == 495.0 and t["long_put"] == 490.0


def test_take_profit_at_75_pct_of_the_credit_on_finished_minutes():
    ser, _pm = hand_series(DAY)
    ctx = data.DayContext(ser, DAY, {}, None)
    sc, sp_ = tape(DAY, "C", 505.0, {0: 1.00, 99: 0.58, 100: 0.57}), tape(DAY, "P", 495.0, {0: 1.00, 99: 0.60, 100: 0.60})
    lc, lp = tape(DAY, "C", 510.0, {0: 0.20, 99: 0.02, 100: 0.02}), tape(DAY, "P", 490.0, {0: 0.20, 99: 0.02, 100: 0.02})
    legs = [leg(sc, -1), leg(sp_, -1), leg(lc, +1), leg(lp, +1)]
    t, _ = RC.simulate(plan_of("C3-ctl", legs, 14, tp=True), ctx, SS.ConstSpread(0.02))
    # credit = 2 x 0.98 - 2 x 0.22 = 1.52; level = 0.75 x 1.52 = 1.14; minute 99 costs 1.18 - 0.04 = 1.14 -> take profit there
    assert t["credit"] == pytest.approx(1.52) and t["exit_reason"] == "TAKE PROFIT" and t["exit_idx"] == 100
    exp = 152 - 4 * 0.65 - (0.59 * 100 + 0.65) - (0.62 * 100 + 0.65) + 2 * (0.0 * 100 - 0.65)     # longs sell at max(0, 0.02 - 0.02)
    assert t["pnl"] == pytest.approx(exp) and t["legs_filled_out"] == 4
    # one cent above the level: no take profit, held to the close (all worthless at a 500 close)
    sc2 = tape(DAY, "C", 505.0, {0: 1.00, 99: 0.59})
    t2, _ = RC.simulate(plan_of("C3-ctl", [leg(sc2, -1), leg(tape(DAY, "P", 495.0, {0: 1.00, 99: 0.60}), -1), leg(lc, +1), leg(lp, +1)],
                                14, tp=True), ctx, SS.ConstSpread(0.02))
    assert t2["exit_reason"] == "SETTLED" and t2["pnl"] == pytest.approx(152 - 4 * 0.65)
    # a minute where a leg has no price within 5 minutes is not checked
    lc3 = tape(DAY, "C", 510.0, {0: 0.20, 99: 0.02}, no_print=set(range(90, 200)))
    t3, _ = RC.simulate(plan_of("C3-ctl", [leg(sc, -1), leg(sp_, -1), leg(lc3, +1), leg(lp, +1)], 14, tp=True), ctx, SS.ConstSpread(0.02))
    assert t3["exit_reason"] == "TAKE PROFIT" and t3["exit_idx"] > 200


def test_time_exit_at_13_and_early_close_settles():
    ser, _pm = hand_series(DAY)
    ctx = data.DayContext(ser, DAY, {}, None)
    legs = [leg(tape(DAY, "C", 500.0, {0: 1.0}), -1), leg(tape(DAY, "P", 500.0, {0: 1.0}), -1), leg(tape(DAY, "C", 505.0, {0: 0.2}), +1),
            leg(tape(DAY, "P", 495.0, {0: 0.2}), +1)]
    t, _ = RC.simulate(plan_of("C4", legs, 29, tp=True, te=RC.TIME_EXIT["C4"]), ctx, SS.ConstSpread(0.02))
    assert t["exit_reason"] == "TIME EXIT 13:00" and t["exit_idx"] == 210 and t["exit_time"] == "13:00"
    assert t["pnl"] == pytest.approx(152 - 2.6 - 2 * (102 + 0.65) + 2 * (18 - 0.65))
    assert t["pnl_2x"] == pytest.approx(144 - 2.6 - 2 * (104 + 0.65) + 2 * (16 - 0.65))
    early = date(2025, 11, 28)
    assert early.isoformat() in periods.early_closes()
    ser2, _ = hand_series(early)
    ctx2 = data.DayContext(ser2, early, {}, None)
    legs2 = [leg(tape(early, r, k, {0: p}), q) for r, k, p, q in (("C", 500.0, 1.0, -1), ("P", 500.0, 1.0, -1), ("C", 505.0, 0.2, 1),
                                                                    ("P", 495.0, 0.2, 1))]
    t2, _ = RC.simulate(plan_of("C4", legs2, 29, tp=True, te=209), ctx2, SS.ConstSpread(0.02))
    assert ctx2.close_idx == 210 and t2["exit_reason"] == "SETTLED" and t2["exit_time"] == "13:00"
    assert t2["pnl"] == pytest.approx(152 - 2.6)                               # all four worthless at 500: no exit cost


def test_no_credit_and_missing_prints_are_skipped():
    ser, _pm = hand_series(DAY)
    ctx = data.DayContext(ser, DAY, {}, None)
    t, why = RC.simulate(plan_of("C1-ctl", [leg(tape(DAY, "P", 495.0, {0: 0.30}), -1), leg(tape(DAY, "P", 490.0, {0: 0.29}), +1)], 59),
                         ctx, SS.ConstSpread(0.02))
    assert t is None and why == "no credit at the fills"
    gap = tape(DAY, "P", 490.0, {0: 0.10}, no_print={60, 61, 62})
    t, why = RC.simulate(plan_of("C1-ctl", [leg(tape(DAY, "P", 495.0, {0: 1.0}), -1), leg(gap, +1)], 59), ctx, SS.ConstSpread(0.02))
    assert t is None and why.startswith("no print for +P490 within 3 minutes")
    late = tape(DAY, "P", 490.0, {0: 0.40}, no_print={60, 61})                     # prints at 62: inside the 3-minute window
    t, _ = RC.simulate(plan_of("C1-ctl", [leg(tape(DAY, "P", 495.0, {0: 1.0}), -1), leg(late, +1)], 59), ctx, SS.ConstSpread(0.02))
    assert t["entry_idx"] == 62


# ---------------------------------------------------------------- the rules' entry decisions
def c1_chain(day, ctx, S=500.0, st=1.6):
    ks = [500.0, 496.0, 491.0, 504.0, 505.0, 509.0, 510.0]
    tl = [tape(day, r, k, {0: st if k == 500.0 else 0.3 if abs(k - S) < 7 else 0.1}) for k in ks for r in ("C", "P")]
    return chain_of(ctx, tl)


@pytest.mark.parametrize("pre,rule,structure,legs", [
    (499.0, "C1", "put vertical", "-P496 +P491"), (501.0, "C1", "call vertical", "-C504 +C509"),
    (501.0, "C1-ctl", "put vertical", "-P496 +P491"), (499.0, "C1-ic", "iron condor", "-P496 +P491 -C504 +C509")])
def test_c1_direction_straddle_strikes_and_controls(pre, rule, structure, legs):
    ser, pm = hand_series(DAY, pre=pre)
    ctx = data.DayContext(ser, DAY, {}, None)
    p, why = RC.plan(rule, ctx, c1_chain(DAY, ctx), RC.day_inputs(ser, DAY, pm))
    # straddle = 1.6 + 1.6 = 3.2; 1.25 x 3.2 = 4.0 -> short put floor(496.0) = 496, short call ceil(504.0) = 504, wings $5 out
    assert why is None and p["structure"] == structure and RC._legs_text(p["legs"]) == legs and p["straddle"] == pytest.approx(3.2)
    assert p["decision_idx"] == 59 and p["atm"] == 500.0
    if rule == "C1":
        assert p["p0830"] == pre and p["p1030"] == 500.0 and p["direction"] == ("up" if pre < 500 else "down")


def test_c1_rounds_to_the_listed_strike_at_or_beyond_and_needs_a_direction():
    ser, pm = hand_series(DAY, path={0: 500.3}, pre=499.0)
    ctx = data.DayContext(ser, DAY, {}, None)
    p, _ = RC.plan("C1-ic", ctx, c1_chain(DAY, ctx, S=500.3), RC.day_inputs(ser, DAY, pm))
    assert RC._legs_text(p["legs"]) == "-P496 +P491 -C505 +C510"               # floor(496.3), ceil(504.3); ATM = 500
    ser, pm = hand_series(DAY, pre=500.0)
    ctx = data.DayContext(ser, DAY, {}, None)
    assert RC.plan("C1", ctx, c1_chain(DAY, ctx), RC.day_inputs(ser, DAY, pm)) == (None, "10:30 price equals the 08:30 price (no direction)")
    assert RC.plan("C1", ctx, c1_chain(DAY, ctx), {"p0830": None})[1] == "no premarket bar by 08:30 (no direction)"
    ch = chain_of(ctx, [tape(DAY, r, k, {0: 1.6 if k == 500 else 0.3}) for k in (500.0, 496.0, 504.0, 509.0) for r in ("C", "P")])
    assert RC.plan("C1-ctl", ctx, ch, {})[1] == "long P 491 not on file (pull)"     # a missing leg skips; never another strike
    assert RC.atm(500.5) == 500.0 and RC.atm(500.51) == 501.0


def test_premarket_price_is_the_last_bar_finished_by_0830():
    rows = [(pd.Timestamp(f"{DAY} {h:02d}:{m:02d}", tz=ET), 1.0, 1.0, 1.0, float(h * 100 + m), 1.0)
            for h, m in ((4, 0), (7, 15), (8, 29), (8, 30), (9, 30))]
    df = pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"])
    assert RC.premarket_prices(df) == {DAY: 829.0}
    assert RC.premarket_prices(df[df["ts"].dt.hour != 8]) == {DAY: 715.0}
    assert RC.premarket_prices(df[df["ts"].dt.hour >= 9]) == {}


def _closes(n, start=500.0, step=0.0005, wiggle=0.0):
    return [start * (1 + step * k) * (1 + (wiggle if k % 2 else -wiggle)) for k in range(n)]


def test_c2_filter_sma10_and_the_vix_proxy():
    calm = _closes(22)
    ser, pm = hand_series(DAY, prior_closes=calm)
    ctx = data.DayContext(ser, DAY, {}, None)
    inp = RC.day_inputs(ser, DAY, pm)
    r = np.diff(np.log(np.array(calm[-21:])))
    assert inp["rv20"] == pytest.approx(float(np.std(r, ddof=1) * math.sqrt(252))) and inp["sma10_side"] == 1
    assert RC.plan("C2", ctx, RC.Chain(ctx), inp)[1] == "no 0DTE option data for the day"        # the filter passed
    wild = _closes(22, wiggle=0.012)
    ser_w, pm_w = hand_series(DAY, prior_closes=wild)
    inp_w = RC.day_inputs(ser_w, DAY, pm_w)
    assert inp_w["rv20"] > 0.19
    assert RC.plan("C2", data.DayContext(ser_w, DAY, {}, None), RC.Chain(ctx), inp_w)[1].startswith("filter: VIX proxy")
    down = _closes(22, step=-0.0005)
    ser_d, pm_d = hand_series(DAY, prior_closes=down)
    assert RC.plan("C2", data.DayContext(ser_d, DAY, {}, None), RC.Chain(ctx), RC.day_inputs(ser_d, DAY, pm_d))[1] == \
        "filter: prior close not above its 10-day SMA"
    short, pm_s = hand_series(DAY, prior_closes=calm[-12:])
    assert RC.day_inputs(short, DAY, pm_s)["rv20"] is None
    assert RC.plan("C2", data.DayContext(short, DAY, {}, None), RC.Chain(ctx), RC.day_inputs(short, DAY, pm_s))[1].startswith("filter history")
    assert RC.plan("C2-ctl", ctx, RC.Chain(ctx), inp_w)[1] == "no 0DTE option data for the day"     # the control has no filter
    # QQQ (information): its own SMA, SPY's 20-day vol as the VIX proxy
    q, qpm = hand_series(DAY, prior_closes=_closes(22, start=400.0, wiggle=0.02), sym="QQQ")
    qi = RC.day_inputs(q, DAY, qpm, spy=ser)
    assert qi["rv20"] == pytest.approx(inp["rv20"]) and qi["rv_from"] == "SPY" and qi["sma10_side"] == q.sma_side(DAY, 10)


@pytest.mark.parametrize("open_,ok", [(502.5, True), (502.4, False), (500.5, True), (499.5, True), (499.4, False), (497.5, False),
                                      (510.0, True)])
def test_c3_gap_filter(open_, ok):
    ser, pm = hand_series(DAY, prior_closes=(500.0, 500.0), bars={0: (open_, open_ + 0.1, open_ - 0.1, open_)})
    ctx = data.DayContext(ser, DAY, {}, None)
    p, why = RC.plan("C3", ctx, RC.Chain(ctx), RC.day_inputs(ser, DAY, pm))
    assert (why == "no 0DTE option data for the day") == ok
    if not ok:
        assert why.startswith("filter: not a gap-up")
    assert RC.plan("C3-ctl", ctx, RC.Chain(ctx), RC.day_inputs(ser, DAY, pm))[1] == "no 0DTE option data for the day"


def bs_chain(day, ctx, iv=0.2, ks=range(470, 531), j=None):
    S = float(ctx.c[0])
    out = []
    for k in ks:
        for r in ("C", "P"):
            px = {}
            for i in range(390):
                T = bs.t_years(390 - (i + 1))
                px[i] = max(round(bs.price(float(ctx.c[i]), float(k), T, iv, r), 2), 0.01)
            out.append(tape(day, r, float(k), px))
    assert S > 0
    return chain_of(ctx, out)


@pytest.fixture(scope="module")
def bsday():
    ser, pm = hand_series(DAY, prior_closes=(500.0, 500.0), path={0: 500.0, 29: 499.4, 30: 500.0})
    ctx = data.DayContext(ser, DAY, {}, None)
    return ser, pm, ctx, bs_chain(DAY, ctx)


def test_delta_picks_nearest_target_with_a_bracket(bsday):
    _ser, _pm, ctx, ch = bsday
    for target in (0.20, 0.30):
        for r in ("C", "P"):
            t, info = RC.pick_delta(ch, ctx, r, 14, target)
            T = bs.t_years(390 - 15)
            ds = {k: abs(bs.delta(500.0, float(k), T, bs.implied_vol(ch.get(k, r).last_close(14), 500.0, float(k), T, r), r))
                  for k in range(480, 521) if bs.implied_vol(ch.get(k, r).last_close(14), 500.0, float(k), T, r)}
            best = min(ds, key=lambda k: abs(ds[k] - target))
            assert t.strike == best and abs(info["delta"]) == pytest.approx(ds[best], abs=2e-3)
            assert (t.strike > 500) == (r == "C")
    near = chain_of(ctx, [ch.get(k, r) for k in range(498, 502) for r in ("C", "P")])        # no strike far enough out
    assert RC.pick_delta(near, ctx, "C", 14, 0.20) == (None, "the C strikes on file do not bracket |delta| 0.20 (pull)")


def test_c4_fly_when_down_more_than_010_pct_else_the_20_delta_condor(bsday):
    ser, pm, ctx, ch = bsday
    p, _ = RC.plan("C4", ctx, ch, RC.day_inputs(ser, DAY, pm))
    assert p["structure"] == "iron fly" and RC._legs_text(p["legs"]) == "-C499 -P499 +C504 +P494" and p["move"] == pytest.approx(-0.0012)
    assert p["tp"] and p["time_exit_dec"] == 209 and p["decision_idx"] == 29
    ser2, pm2 = hand_series(DAY, prior_closes=(500.0, 500.0), path={0: 500.0, 29: 499.5, 30: 500.0})
    ctx2 = data.DayContext(ser2, DAY, {}, None)
    p2, _ = RC.plan("C4", ctx2, bs_chain(DAY, ctx2, ks=range(485, 516)), RC.day_inputs(ser2, DAY, pm2))
    assert p2["structure"] == "iron condor" and p2["move"] == pytest.approx(-0.001)              # exactly -0.10%: not "more than"
    assert abs(p2["delta_call"]) == pytest.approx(0.2, abs=0.08) and abs(p2["delta_put"]) == pytest.approx(0.2, abs=0.08)
    k = {L["right"] + ("s" if L["q"] < 0 else "l"): L["K"] for L in p2["legs"]}
    assert k["Cl"] == k["Cs"] + 5 and k["Pl"] == k["Ps"] - 5


def test_c2_and_c3_pick_30_and_20_delta_condors(bsday):
    ser, pm, ctx, ch = bsday
    for rule, j, target in (("C2-ctl", 254, 0.30), ("C3-ctl", 14, 0.20)):
        p, _ = RC.plan(rule, ctx, ch, RC.day_inputs(ser, DAY, pm))
        assert p["decision_idx"] == j and p["structure"] == "iron condor" and p["tp"] == (rule == "C3-ctl")
        for r in ("C", "P"):
            t, info = RC.pick_delta(ch, ctx, r, j, target)
            assert p[f"delta_{'call' if r == 'C' else 'put'}"] == info["delta"]


# ---------------------------------------------------------------- no look-ahead
def _plan_key(p):
    return (p["structure"], RC._legs_text(p["legs"]), {k: v for k, v in p.items() if k not in ("legs",)})


def test_no_look_ahead_bars_after_an_entry_change_neither_the_entry_its_strikes_nor_the_filters(world):
    d = DEV_DAYS[23]
    cost = RC.CreditSpread()
    base_ser, pm = RC.load("SPY", DEV_DAYS[0], DEV_DAYS[-1], world)
    ctx = data.DayContext(base_ser, d, {}, None)
    tapes = RC.read_tapes("SPY", d, world)
    inp = RC.day_inputs(base_ser, d, pm)
    first = {}
    for rule in RC.RULES:
        p, why = RC.plan(rule, ctx, RC.Chain(ctx, tapes=tapes), inp)
        assert why is None, (rule, why)
        t, why = RC.simulate(p, ctx, cost)
        assert why is None, (rule, why)
        first[rule] = (_plan_key(p), t)
    changed = 0
    for rule in RC.RULES:
        j = RC.DEC[rule]
        ser, pm2 = RC.load("SPY", DEV_DAYS[0], DEV_DAYS[-1], world)
        g = ser.rth[d]
        g[j + 1 + RC.ENTRY_WAIT:, :4] *= 0.97                                      # the stock drops after the entry window
        tp = RC.read_tapes("SPY", d, world)
        for tt in tp.values():                                                      # and every option re-prices after it
            for arr in (tt.o, tt.h, tt.l, tt.c):
                arr[j + 1 + RC.ENTRY_WAIT:] = np.round(arr[j + 1 + RC.ENTRY_WAIT:] * (3.0 if tt.right == "C" else 0.2), 2)
        c2 = data.DayContext(ser, d, {}, None)
        p, why = RC.plan(rule, c2, RC.Chain(c2, tapes=tp), RC.day_inputs(ser, d, pm2))
        assert why is None and _plan_key(p) == first[rule][0], rule
        t, _ = RC.simulate(p, c2, cost)
        assert t["credit"] == first[rule][1]["credit"] and t["entry_idx"] == first[rule][1]["entry_idx"], rule
        changed += t["pnl"] != first[rule][1]["pnl"]
    assert changed >= 5                                                             # the exits did see the new bars


def test_no_look_ahead_later_sessions_never_change_a_days_filters(world):
    df = data.read_stock("SPY", DEV_DAYS[0], DEV_DAYS[-1], world)
    d = DEV_DAYS[23]
    base = data.Series("SPY", df)
    pm = RC.premarket_prices(df)
    ref = RC.day_inputs(base, d, pm)
    df2 = df.copy()
    later = df2["ts"].dt.date > d
    df2.loc[later, ["o", "h", "l", "c"]] *= 0.8
    ser2 = data.Series("SPY", df2)
    assert RC.day_inputs(ser2, d, RC.premarket_prices(df2)) == ref
    df3 = df.copy()
    same = (df3["ts"].dt.date == d) & ((df3["ts"].dt.hour * 60 + df3["ts"].dt.minute) >= 600)
    df3.loc[same, ["o", "h", "l", "c"]] *= 1.05                                      # today's bars from 10:00 on
    ser3 = data.Series("SPY", df3)
    r3 = RC.day_inputs(ser3, d, RC.premarket_prices(df3))
    assert r3 == ref                                                                # prior closes and the premarket only
    nxt = DEV_DAYS[24]
    assert RC.day_inputs(ser3, nxt, None)["prev_close"] != RC.day_inputs(base, nxt, None)["prev_close"]


# ---------------------------------------------------------------- restart safety
def test_restart_safety_runs_are_deterministic_and_resume_mid_window(world):
    a, b = DEV_DAYS[0], DEV_DAYS[-1]
    runs = []
    for _ in range(2):
        ser, pm = RC.load("SPY", a, b, world)
        tr, sk = RC.run(ser, pm, a, b, "real", root=world)
        runs.append((tr, sk))
    assert runs[0][0] == runs[1][0] and runs[0][1] == runs[1][1]
    tr = runs[0][0]
    assert {t["rule"] for t in tr} == set(RC.RULES) and all(t["prices"] == "REAL" and t["window"] == "DEV" for t in tr)
    assert len({(t["rule"], t["day"]) for t in tr}) == len(tr)                    # one structure per rule a day
    k = DEV_DAYS[15]
    ser, pm = RC.load("SPY", a, b, world)
    tail, _ = RC.run(ser, pm, k, b, "real", root=world)                             # a re-run from the middle (history loaded)
    assert tail == [t for t in tr if t["day"] >= k.isoformat()]
    assert all(t["exit_reason"] in ("SETTLED", "TAKE PROFIT", "TIME EXIT 13:00") for t in tr)
    assert {t["structure"] for t in tr if t["rule"] == "C1"} <= {"put vertical", "call vertical"}
    c3 = [t for t in tr if t["rule"] == "C3"]
    assert c3 and all(t["gap"] >= RC.C3_GAP_UP or abs(t["gap"]) <= RC.C3_FLAT for t in c3)
    assert DEV_DAYS[26].isoformat() not in {t["day"] for t in c3}                   # a -0.9% gap never qualifies


# ---------------------------------------------------------------- the pass bar and the report numbers
def _trades(rule, days, pnl, sym="SPY", margin=400.0):
    return [{"rule": rule, "symbol": sym, "day": d, "pnl": float(p), "pnl_2x": float(p) - 5.0, "entry_idx": 60, "exit_reason": "SETTLED",
             "structure": "iron condor", "margin": margin, "legs_itm_at_close": 0, "window": "DEV"} for d, p in zip(days, pnl)]


def test_pass_bar_blocks_and_control():
    days = book.sessions_between("2025-07-01", "2026-06-30")
    n = len(days)
    good = _trades("C3", days, [30.0 if k % 4 else -40.0 for k in range(n)])
    ctl = _trades("C3-ctl", days, [5.0] * n)
    ev, ec = RC.evaluate(good, RC.DEV_A, RC.DEV_B), RC.evaluate(ctl, RC.DEV_A, RC.DEV_B)
    pb = RC.pass_bar("C3", ev, ec)
    assert pb["pass"] and pb["blocks_green"] == 6 and pb["control"] == "C3-ctl" and len(pb["checks"]) == 5
    assert not RC.pass_bar("C3", ev, RC.evaluate(_trades("C3-ctl", days, [100.0] * n), RC.DEV_A, RC.DEV_B))["pass"]
    pc = RC.pass_bar("C3-ctl", ec)
    assert len(pc["checks"]) == 4 and pc["control"] is None and RC.pass_bar("C4", ev)["control"] is None
    assert RC.pass_bar("C1-ic", ev)["control"] is None
    # only 3 green blocks of 6
    pnl = [(-60.0 if d >= "2025-11-01" and d < "2026-05-01" else 30.0) for d in days]
    pnl = [p if k % 4 else -1.0 for k, p in enumerate(pnl)]
    ev3 = RC.evaluate(_trades("C2", days, pnl), RC.DEV_A, RC.DEV_B)
    pb3 = RC.pass_bar("C2", ev3, ec)
    assert pb3["blocks_green"] == 3 and not pb3["pass"]
    assert dict(pb3["checks"])["positive in at least 4 of the 6 two-month blocks of 2025-07..2026-06 (3 of 6)"] is False
    few = RC.evaluate(_trades("C1", days[:99], [10.0] * 99), RC.DEV_A, RC.DEV_B)
    ch = dict(RC.pass_bar("C1", few, ec)["checks"])
    assert ch["at least 100 trades (99)"] is False
    stress = RC.evaluate([dict(t, pnl_2x=-1.0) for t in good], RC.DEV_A, RC.DEV_B)
    assert not RC.pass_bar("C3", stress, ec)["pass"]


def test_evaluate_reports_worst_days_april_2025_months_and_margin():
    days = book.sessions_between("2025-03-03", "2025-05-30")
    pnl = [20.0] * len(days)
    worst = {"2025-04-04": -300.0, "2025-04-07": -450.0, "2025-04-08": -120.0, "2025-03-10": -80.0, "2025-05-01": -60.0}
    for k, d in enumerate(days):
        pnl[k] = worst.get(d, pnl[k])
    rows = _trades("C1-ic", days, pnl, margin=400.0)
    ev = RC.evaluate(rows, RC.DEV_A, RC.DEV_B)
    assert ev["worst_day"] == ("2025-04-07", -450.0) and [d for d, _ in ev["worst5"]] == ["2025-04-07", "2025-04-04", "2025-04-08",
                                                                                           "2025-03-10", "2025-05-01"]
    ap = ev["april_2025"]
    n_ap = sum(1 for d in days if d.startswith("2025-04"))
    assert ap["trades"] == n_ap and ap["total"] == pytest.approx(20.0 * (n_ap - 3) - 870.0) and ap["worst_day"] == -450.0
    assert ev["steadiness"]["months"] == 3 and ev["steadiness"]["months_green"] == 2
    assert ev["years"] == {"2025": {"trades": len(days), "total": pytest.approx(sum(pnl)), "pf": ev["stats"]["pf"],
                                    "pf_2x": ev["stats"]["pf_2x"], "max_dd": ev["stats"]["max_dd"]}}
    assert ev["margin"]["mean_ret"] == pytest.approx(np.mean(pnl) / 400.0, abs=1e-4)
    assert ev["margin"]["total_on_total_margin"] == pytest.approx(sum(pnl) / (400.0 * len(days)), abs=1e-4)
    lo, hi = ev["bootstrap_ci"]
    assert lo < np.mean(pnl) < hi
    av = RC.account_view(rows, book.sessions_between(RC.DEV_A, RC.DEV_B))
    assert av["per_1000"]["total"] == pytest.approx(sum(pnl) * 1000 / 400.0, abs=0.05)
    assert av["margin_pct_3000"]["median"] == pytest.approx(13.3) and av["fit_at_median_margin"] == 7
    assert av["pre_registered_size"]["worst_month"] == "2025-04"


# ---------------------------------------------------------------- data needs
def test_needed_option_contracts_cover_every_leg_and_refuse_locked_days(world):
    ser, pm = RC.load("SPY", DEV_DAYS[0], DEV_DAYS[-1], world)
    df = data.read_stock("SPY", DEV_DAYS[0], DEV_DAYS[-1], world)
    n_legs = 0
    for d in DEV_DAYS[20:]:
        ctx = data.DayContext(ser, d, {}, None)
        tapes = RC.read_tapes("SPY", d, world)
        need = set(RC.needed_option_contracts(d, ser.rth[d], "SPY", tapes=tapes))
        env = set(RC.needed_option_contracts(d, ser.rth[d], "SPY"))                 # no tapes: the 60% IV envelope
        assert need == set(RC.needed_option_contracts(d, df[df["ts"].dt.date == d], "SPY", tapes=tapes))   # a DataFrame works too
        for rule in RC.RULES:
            p, why = RC.plan(rule, ctx, RC.Chain(ctx, tapes=tapes), RC.day_inputs(ser, d, pm))
            if p is None:
                continue
            for L in p["legs"]:
                s = RC.occ("SPY", d, L["right"], L["K"])
                assert s in need and s in env, (rule, s)
                n_legs += 1
        assert all(s.startswith(f"SPY{d:%y%m%d}") for s in need) and need == {s for s in need if s[-9] in "CP"}
        cv = RC.day_coverage(d, ser.rth[d], "SPY", tapes)
        assert cv["needed"] == len(need) and cv["on_file"] + cv["asked_no_bars"] + cv["outside_asked"] == cv["needed"]
    assert n_legs > 40
    with pytest.raises(periods.LockedPeriod):
        RC.needed_option_contracts(date(2026, 8, 3), ser.rth[DEV_DAYS[0]], "SPY")
    with pytest.raises(periods.LockedPeriod):
        RC.needed_option_contracts(date(2024, 3, 4), ser.rth[DEV_DAYS[0]], "SPY")
    early = RC.needed_strikes(date(2025, 11, 28), ser.rth[DEV_DAYS[0]])
    assert "13:45" not in early and set(RC.needed_strikes(DEV_DAYS[0], ser.rth[DEV_DAYS[0]])) == {"09:45", "10:00", "10:30", "13:45"}
    wide = RC.needed_strikes(DEV_DAYS[0], ser.rth[DEV_DAYS[0]], iv=0.9)
    calm = RC.needed_strikes(DEV_DAYS[0], ser.rth[DEV_DAYS[0]], iv=0.1)
    assert wide["09:45"][0] < calm["09:45"][0] and wide["09:45"][1] > calm["09:45"][1]


def test_existing_pull_strikes_match_the_runs_1_3_puller(world):
    import pull_alpaca as PA
    df = data.read_stock("SPY", DEV_DAYS[0], DEV_DAYS[-1], world)
    for d in DEV_DAYS[:5]:
        g = df[df["ts"].dt.date == d]
        lo, hi = RC.existing_pull_strikes(g, d)
        ks = {int(s[-8:]) // 1000 for s in PA.symbols_for_day("SPY", d, g, 0.03)}
        assert ks == set(range(lo, hi + 1))
    summ = RC.coverage_summary({"2025-03-03": {"needed": 10, "on_file": 10, "asked_no_bars": 0, "outside_asked": 0},
                                "2025-03-04": {"needed": 12, "on_file": 8, "asked_no_bars": 1, "outside_asked": 3}})
    assert summ["days"] == 2 and summ["days_complete"] == 1 and summ["days_needing_pull"] == 1 and summ["outside_asked"] == 3
    assert summ["first_days_needing_pull"] == ["2025-03-04"]


# ---------------------------------------------------------------- windows, labels, locked periods
def test_load_and_run_refuse_l1_and_l2(world):
    with pytest.raises(periods.LockedPeriod):
        RC.load("SPY", "2024-07-01", "2024-08-30", world)
    with pytest.raises(periods.LockedPeriod):
        RC.read_tapes("SPY", date(2026, 7, 1), world)
    ser, pm = RC.load("SPY", DEV_DAYS[0], DEV_DAYS[-1], world)
    with pytest.raises(periods.LockedPeriod):
        RC.run(ser, pm, "2026-06-01", "2026-07-15", "real", root=world)
    assert RC.check_rows([{"day": "2026-07-02"}]).startswith("REFUSED") and RC.check_rows([{"day": "2025-07-02"}]) is None


def test_hist_runs_on_modeled_tapes_and_needs_the_calibration(tmp_path):
    days = sessions("2019-10-01", "2019-11-15")
    write_world(tmp_path, "SPY", days, px0=300.0, seed=5, options=False)
    ser, pm = RC.load("SPY", days[0], days[-1], tmp_path)
    tr, sk = RC.run(ser, pm, days[0], days[-1], "modeled", calib=CALIB)
    assert tr and all(t["prices"] == "MODELED" and t["window"] == "HIST" for t in tr) and {t["rule"] for t in tr} >= {"C1-ctl", "C3-ctl", "C4"}
    assert sk[("C1-ctl", "MODELED: no IV proxy (fewer than 10 prior sessions)")] == 10
    first = min(t["day"] for t in tr)
    assert first == days[10].isoformat()
    ct = [t for t in tr if t["rule"] == "C3-ctl"]
    assert ct and all(0.05 < abs(t["delta_call"]) < 0.40 and 0.05 < abs(t["delta_put"]) < 0.40 for t in ct)
    with pytest.raises(ValueError):
        RC.run(ser, pm, days[0], days[-1], "modeled", calib=None)
    with pytest.raises(ValueError):
        RC.run(ser, pm, days[0], days[-1], "modeled", calib={"min_n": 30, "keys": {}})
    tr2, _ = RC.run(ser, pm, days[0], days[-1], "modeled", calib=CALIB)
    assert tr2 == tr
