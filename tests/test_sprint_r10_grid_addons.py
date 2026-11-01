"""Round 10 add-ons (sprint/r10grid.py): Addendum 15.3's rules (entry conditions, strike, sizing, exits, cooldown, day gates),
R1 pm_inside_break (the qualifying day, the break, the 5-minute re-entry exit in shares and options, the claim), the
information-only regime features (sprint/features.py REGIME10), the round 10 calibration for rules run 4 lacks, and the tool end
to end (frozen choice, add-on verdicts, trial count, restart reproduces identical outputs, locked rows refused). Synthetic only."""
import gzip
import json
import math
import sys
import types
from datetime import date

import numpy as np
import pytest

import sprint_synth as SS
from sprint import book, data, features, periods, r10grid as G
from sprint import spread as SP
from sprint.fills import OptionTape
from sprint.sim import Costs

DAY = date(2025, 3, 12)


def _tape(prices, right="C", strike=503.0, lows=None, highs=None, skip=()):
    o = np.full(390, np.nan)
    cur = None
    for i in range(390):
        if i in prices:
            cur = prices[i]
        if cur is not None and i not in skip:
            o[i] = cur
    h, l = o + 0.005, o - 0.005
    for i, x in (lows or {}).items():
        l[i] = x
    for i, x in (highs or {}).items():
        h[i] = x
    return OptionTape(f"SPY{DAY:%y%m%d}{right}{int(strike * 1000):08d}", right, strike, o, h, l, o.copy(), np.where(np.isnan(o), np.nan, 9.0))


def _trend_bars(start, n, up=True, base=500.0, step=0.1, wick=0.1):
    """n trending bars from `start`: each opens at the prior close and closes `step` beyond it (green up, red down)."""
    bars, px = {}, base
    for i in range(start, start + n):
        o, c = px, round(px + (step if up else -step), 2)
        bars[i] = (o, max(o, c) + wick, min(o, c) - wick, c)
        px = c
    return bars


def _af_ctx(bars, prior_range=2.0):
    ctx, _ = SS.make_ctx(DAY, {0: 500.0}, {0: 1.0}, prior_days=6, prior_range=prior_range, stock_bars=bars)
    return ctx


# ---------------------------------------------------------------- the framework's live path (Addendum 16.2)
@pytest.mark.parametrize("up", [True, False])
def test_af_entry_needs_vwap_ema_roc_three_bars_and_true_range_atr(up):
    ctx = _af_ctx(_trend_bars(14, 20, up))
    side = "C" if up else "P"
    j = 22
    assert G.af_signal(ctx, j) == side and G.af_signal(ctx, 13) is None
    st = G.af_state(ctx)
    c, vw = float(ctx.c[j]), float(ctx.vwap[j])
    assert (c > vw if up else c < vw) and ((st["ema5"][j] > st["ema20"][j]) if up else (st["ema5"][j] < st["ema20"][j]))
    assert st["green" if up else "red"][j] == 9 and abs(st["roc5"][j]) >= G.AF_ROC
    for key, bad in (("green" if up else "red", 2), ("roc5", 0.0002 if up else -0.0002), ("atr5", 0.19),
                     ("ema5", st["ema20"][j] + (-0.01 if up else 0.01))):
        keep = st[key][j]
        st[key][j] = bad
        assert G.af_signal(ctx, j) is None, key                              # each condition is required
        st[key][j] = keep
    keep = ctx.vwap[j]
    ctx.vwap[j] = c + (0.01 if up else -0.01)                                # the close on the wrong side of VWAP
    assert G.af_signal(ctx, j) is None
    ctx.vwap[j] = keep
    assert G.af_signal(ctx, j) == side


def test_af_state_preseed_counters_and_true_range():
    bars = {14: (500.0, 500.05, 499.95, 500.02), 15: (500.02, 500.06, 499.99, 500.02), 16: (500.02, 500.08, 500.0, 500.06),
            17: (500.06, 500.1, 500.03, 500.09), 18: (500.6, 500.64, 500.58, 500.62), 19: (500.62, 500.65, 500.5, 500.55)}
    ctx = _af_ctx(bars)
    st = G.af_state(ctx)
    assert [int(st["green"][i]) for i in (14, 15, 16, 17, 18, 19)] == [1, 1, 2, 3, 4, 0]     # a doji (15) leaves the count
    assert int(st["red"][19]) == 1
    e5 = e20 = None
    for x in [500.0] * 30 + [float(ctx.c[i]) for i in range(0, 20)]:          # preseed: the prior session's last 30 closes
        e5, e20 = G._af_ema(e5, x, 5), G._af_ema(e20, x, 20)
    assert st["ema5"][19] == e5 and st["ema20"][19] == e20
    tr18 = max(500.64 - 500.58, abs(500.64 - 500.09), abs(500.58 - 500.09))  # the gap counts: 0.55, not the 0.06 range
    assert tr18 == pytest.approx(0.55)
    trs = [max(ctx.h[i] - ctx.l[i], abs(ctx.h[i] - ctx.c[i - 1]), abs(ctx.l[i] - ctx.c[i - 1])) for i in range(15, 20)]
    assert st["atr5"][19] == pytest.approx(sum(trs) / 5) and st["atr5"][19] > 0.12
    assert st["roc5"][19] == pytest.approx((500.55 - float(ctx.c[14])) / float(ctx.c[14]))
    first = _af_ctx({})
    s2 = G.af_state(first)
    assert s2["ema5"][0] == pytest.approx(500.0) and np.isnan(s2["roc5"][4]) and not np.isnan(s2["roc5"][5])


def test_af_strike_is_the_nearest_otm_strike_within_0_3pct_in_the_window():
    assert G.af_strike(500.3, 4.0, "C") == 503.0 and G.af_strike(500.3, 4.0, "P") == 498.0      # 0.6 x 4.0 = 2.4
    assert G.af_strike(500.3, 10.0, "C") == 505.0                          # capped at $4.50: round(504.8)
    assert G.af_strike(500.5, 0.0, "C") == 500.0 and G.af_strike(499.5, 0.0, "C") == 500.0      # Python's round: .5 to even
    assert G.af_strikes(500.3, 4.0, "C") == (503.0, [501.0])               # 501 is 0.14% away; 502 is 0.34%
    assert G.af_strikes(500.3, 4.0, "P") == (498.0, [500.0, 499.0])         # nearest first
    assert G.af_strikes(500.0, 4.0, "C")[1] == [501.0] and G.af_strikes(500.0, 4.0, "P")[1] == [499.0]   # at the money: not OTM
    assert G.af_strikes(100.5, 1.0, "C")[1] == [] and G.af_strikes(100.9, 1.0, "C")[1] == [101.0]
    assert G.af_strikes(500.3, 30.0, "C") == (505.0, [501.0])               # the window (500..510) holds it
    assert G.af_size(1.0) == 3 and G.af_size(3.01) == 1 and G.af_size(0.25) == 12   # max(1, floor(150 / (0.5 x debit x 100)))
    ctx = _af_ctx(_trend_bars(14, 20))
    S = float(ctx.c[22])
    K = float(math.floor(S) + 1)

    class T:
        mode, real0 = "real", {}
    t = T()
    t.real0 = {f"SPY{DAY:%y%m%d}C{int(K * 1000):08d}": _tape({0: 0.9}, strike=K)}
    tape, info = G.af_contract(ctx, t, "C", 22, 4.0)
    assert tape is not None and info["strike"] == K and info["px"] == 0.9
    t.real0 = {f"SPY{DAY:%y%m%d}C{int((K + 1) * 1000):08d}": _tape({0: 0.9}, strike=K + 1)}
    assert G.af_contract(ctx, t, "C", 22, 4.0)[1] == "no 0DTE contract at the strike"   # never a farther strike
    t.real0 = {f"SPY{DAY:%y%m%d}C{int(K * 1000):08d}": _tape({0: 0.15}, strike=K)}
    assert G.af_contract(ctx, t, "C", 22, 4.0)[1] == "premium outside $0.20-$10.00"
    assert G.af_contract(ctx, t, "C", 22, None)[1] == "no 5-day ATR"
    assert G.af_atr5d(ctx.series, DAY) == pytest.approx(4.0)               # the mean high-low of the 5 prior daily bars


def test_af_r2_keeps_the_premium_band(monkeypatch):
    ctx = _af_ctx({})
    monkeypatch.setattr(G, "af_exit", lambda c, t, e, A, b, h, co, s, ss: (e + 5, "X", 5.0, 4.0))
    tape = _tape({0: 1.0}, strike=500.0)
    for px, n in ((12.0, 0), (3.0, 1)):
        picks = {(20, "C", "d55-70t60"): (tape, {"symbol": tape.symbol, "strike": 500.0, "px": px, "iv": 0.2, "delta": 0.6})}
        rows = G.af_day(ctx, None, SP.SpreadModel(), "r2", True, "d55-70t60", picks=picks, sigs={20: "C"})
        assert len(rows) == n


@pytest.mark.parametrize("case", ["hard", "target", "trail", "spy", "allout"])
def test_af_exits(case):
    ctx, _ = SS.make_ctx(DAY, {0: 500.0, 60: 499.0 if case == "spy" else 500.0}, {0: 1.0}, prior_days=3)
    lows, highs = {}, {}
    if case == "hard":
        lows = {40: 0.40}
    elif case == "target":
        highs = {40: 1.60}
    elif case == "trail":
        highs, lows = {40: 1.30}, {44: 1.10}                              # armed at +20%: 0.88 x 1.30 = 1.144
    tape = _tape({30: 1.0, 40: 1.25} if case == "trail" else {30: 1.0}, lows=lows, highs=highs)
    costs = Costs(SP.SpreadModel(), "SPY", 30, 1)
    b_in = 1.0
    hs = costs.hs(b_in, 30)
    x, why, p1, p2 = G.af_exit(ctx, tape, 30, 355, b_in, hs, costs, "C", 499.5)
    want = {"hard": (40, "HARD STOP"), "target": (40, "TARGET +50%"), "trail": (44, "PEAK TRAIL"), "spy": (61, "SPY STOP"),
            "allout": (355, "ALL OUT")}[case]
    assert (x, why) == want
    if case == "trail":
        assert p1 > 0                                                      # 1.144 x (1 - 2%) - 1.02 > 0 after fees
    if case == "hard":
        assert p1 < -45 and p2 < p1


def test_af_day_cooldown_and_day_gates(monkeypatch):
    ctx, _ = SS.make_ctx(DAY, {0: 500.0}, {0: 1.0}, prior_days=6, prior_range=2.0)
    tape = _tape({0: 1.0})
    monkeypatch.setattr(G, "af_contract", lambda c, t, side, j, a: (tape, {"symbol": tape.symbol, "strike": 503.0, "px": 1.0, "S": 500.0,
                                                                           "j": j, "side": side, "iv": 0.2, "delta": 0.3}))
    sigs = {j: "C" for j in range(14, 150)}
    out = {}

    def run(pnl, gated):
        monkeypatch.setattr(G, "af_exit", lambda c, t, e, A, b, h, co, s, ss: (e + 5, "X", pnl, pnl))
        return G.af_day(ctx, None, SP.SpreadModel(), "v", gated, sigs=sigs)
    out["win_g"], out["win_u"] = run(10.0, True), run(10.0, False)
    out["loss_g"], out["big_g"] = run(-100.0, True), run(40.0, True)
    assert [r["signal_idx"] for r in out["win_u"][:3]] == [14, 22, 30]       # entry at j+1, exit e+5, next decision >= exit + 2
    assert all(r["entry_idx"] == r["signal_idx"] + 1 and r["exit_idx"] == r["entry_idx"] + 5 for r in out["win_u"])
    assert len(out["win_g"]) == 3 and len(out["win_u"]) > 10                 # 3 wins in a row lock new entries
    assert out["win_g"][0]["qty"] == 2                                        # debit 1.02 -> floor(150 / 51) = 2
    assert len(out["loss_g"]) == 2                                            # -200 then -400 <= -300 locks
    assert len(out["big_g"]) == 2                                             # +80 then +160 >= +125 locks
    assert all(r["entry_idx"] <= G.AF_LAST_FILL for r in out["win_u"]) and max(r["signal_idx"] for r in out["win_u"]) <= G.AF_LAST


# ---------------------------------------------------------------- R1
def _r1_ctx(prior_range, path):
    ctx, _ = SS.make_ctx(DAY, path, {0: 1.0}, prior_days=3, prior_range=prior_range)
    return ctx


def test_r1_setup_shares_and_claim():
    path = {0: 500.0, 30: 500.5, 60: 500.0, 100: 499.0}
    q = G.r1_setup(_r1_ctx(0.5, path))
    assert q["qualifies"] and q["pmh"] == pytest.approx(500.01) and q["pml"] == pytest.approx(499.99)
    assert (q["side"], q["idx"]) == ("C", 30) and q["exits"][0] == 64 and q["beyond"] is False
    n = G.r1_setup(_r1_ctx(0.005, path))                                     # premarket wider than the prior range
    assert not n["qualifies"] and (n["side"], n["idx"]) == ("C", 30)
    t = G.r1_shares(_r1_ctx(0.5, path), q, "DEV")
    assert (t["entry_idx"], t["exit_idx"], t["side"]) == (31, 65, "L") and t["exit_reason"].startswith("PM RANGE")
    assert t["shares"] == int(10_000 // 500.5) and t["pnl"] == pytest.approx(t["shares"] * (500.0 - 500.5 - 0.02))
    held = G.r1_setup(_r1_ctx(0.5, {0: 500.0, 30: 500.5}))                   # never back inside: out at the 15:55 bar's close
    t2 = G.r1_shares(_r1_ctx(0.5, {0: 500.0, 30: 500.5}), held, "DEV")
    assert t2["exit_idx"] == G.R1_OUT and held["beyond"] is True
    early = G.r1_setup(_r1_ctx(0.5, {0: 500.0, 10: 500.5}))                  # the break before 09:45 is not taken, nor later ones
    assert early["idx"] == G.R1_FIRST


def test_r1_option_exit_and_twin(monkeypatch):
    ctx = _r1_ctx(0.5, {0: 500.0, 30: 500.5, 60: 500.0})
    st = G.r1_setup(ctx)
    tapes = {"C": _tape({0: 1.0}, "C", 500.0), "P": _tape({0: 1.0}, "P", 500.0)}
    monkeypatch.setattr(G.contracts, "pick", lambda c, side, j, rule: (tapes[side], {"symbol": tapes[side].symbol, "strike": 500.0,
                                                                                     "iv": 0.2, "delta": 0.5}))

    class P:
        def pool(self, rule, side, S):
            return None
    r = G.r1_option(ctx, st, P(), SS.ConstSpread(0.01), "d40-55t45", "C", {})
    assert (r["entry_idx"], r["exit_idx"], r["exit_reason"]) == (31, 65, "PM RANGE RE-ENTRY")
    assert r["pnl"] == pytest.approx(((1.0 - 0.01) - (1.0 + 0.01)) * 100 - 1.30)
    out = G.r1_day(ctx, P(), SS.ConstSpread(0.01), "DEV", {})
    kinds = sorted((o["rule"], o["kind"], o["group"]) for o in out["options"])
    assert kinds == [("d40-55t45", "real", "qual"), ("d40-55t45", "twin", "qual"), ("d55-70t60", "real", "qual"), ("d55-70t60", "twin", "qual")]
    tw = [o for o in out["options"] if o["kind"] == "twin"][0]
    assert tw["side"] == G.twin_side(31, "SPY", DAY, 30) and tw["exit_idx"] == 65
    assert out["claim"] == {"symbol": "SPY", "day": DAY.isoformat(), "_src": "DEV", "qualifies": True, "break": "C", "beyond": False}


# ---------------------------------------------------------------- regime features
def test_regime_features():
    rng = np.random.default_rng(1)
    rw = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, 100)))
    alt = 100 + 0.05 * (np.arange(100) % 2) + rng.normal(0, 0.002, 100)
    x = np.zeros(100)
    for i in range(1, 100):
        x[i] = 0.9 * x[i - 1] + rng.normal(0, 1)
    pers = 100 * np.exp(np.cumsum(0.0005 * x))
    h_rw, h_alt, h_pers = features.hurst_rs(rw), features.hurst_rs(alt), features.hurst_rs(pers)
    assert h_alt < h_rw < h_pers and 0.3 < h_rw < 0.8
    assert features.hurst_rs([100.0] * 100) is None and features.hurst_rs([1.0, 2.0]) is None
    bars = {i: ((500.0, 500.2, 499.8, 500.1) if i % 4 else (500.1, 500.2, 499.8, 500.0)) for i in range(40)}
    ctx, _ = SS.make_ctx(DAY, {0: 500.0}, {0: 1.0}, prior_days=60, prior_range=1.0, stock_bars=bars)
    f = features.regime_features(ctx, 39, "C")
    assert f["f_opp_share"] == pytest.approx(10 / 40) and features.regime_features(ctx, 39, "P")["f_opp_share"] == pytest.approx(30 / 40)
    assert f["f_atr9_50"] == pytest.approx(1.0) and f["f_hurst100"] is not None
    assert f["f_adx_d14"] is None                                              # flat prior days: no directional movement
    assert features.daily_atr_n(ctx.series, DAY, 14) == ctx.series.daily_atr(DAY)
    few, _ = SS.make_ctx(DAY, {0: 500.0}, {0: 1.0}, prior_days=20)
    g = features.regime_features(few, 39, "C")
    assert g["f_atr9_50"] is None and g["f_adx_d14"] is None
    import pandas as pd
    days = SS.weekdays(date(2025, 1, 6), 45)
    ser = data.Series("SPY", pd.concat([SS.stock_day(d, 500.0 + k, k, vol=0.001) for k, d in enumerate(days)], ignore_index=True))
    v = features.daily_adx(ser, days[-1])
    assert v is not None and 0 <= v <= 100 and features.daily_adx(ser, days[20]) is None    # 29 prior sessions needed
    assert features.daily_atr_n(ser, days[-1], 50) is None and features.daily_atr_n(ser, days[-1], 9) > 0
    assert set(features.REGIME10) == set(f) and not set(features.REGIME10) & set(features.FEATURES)


# ---------------------------------------------------------------- the round 10 calibration (Builder's reading 7)
def test_extend_calibration_fills_only_what_run4_cannot_price():
    run4 = {"min_n": 30, "keys": {"d40-55t45|C": {"n": 90, "median": 0.8, "ok": True}, "d40-55t45|P": {"n": 90, "median": 0.9, "ok": True},
                                  "n1d40-55t45|C": {"n": 40, "median": 0.7, "ok": True}}}
    rows = [{"symbol": "SPY", "day": f"2025-03-{d:02d}", "contract": f"X{d}{k}", "signal_idx": k, "side": "C", "rule": "d20-30t25",
             "iv_est": 0.25} for d in range(3, 9) for k in range(8)]
    rows += [{"symbol": "SPY", "day": "2025-03-03", "contract": f"Y{k}", "signal_idx": k, "side": "P", "rule": "d55-70t60", "iv_est": 0.3}
             for k in range(10)]
    out = G.extend_calibration(run4, rows, lambda s, d: 0.2)
    assert out["keys"]["d40-55t45|C"] == run4["keys"]["d40-55t45|C"] and "n1d40-55t45|P" not in out["keys"]
    assert out["keys"]["d20-30t25|C"]["median"] == pytest.approx(1.25) and out["keys"]["d20-30t25|C"]["ok"]
    assert out["keys"]["d55-70t60|P"]["n"] == 10 and not out["keys"]["d55-70t60|P"]["ok"]
    assert out["r10_added"]["af153|C"]["n"] == 0 and "af153|C" not in out["keys"]
    from sprint import modeled as MD
    assert MD.multiplier_for(out, "d20-30t25", "C")[0] == pytest.approx(1.25)
    with pytest.raises(ValueError):
        MD.multiplier_for(out, "d55-70t60", "P")


# ---------------------------------------------------------------- the tool end to end
CAL = {"min_n": 30, "keys": {k: {"n": 100, "median": 0.9, "ok": True} for k in
                             ("d40-55t45|C", "d40-55t45|P", "n1d40-55t45|C", "d20-30t25|C", "d20-30t25|P", "d55-70t60|C", "d55-70t60|P",
                              "af153|C", "af153|P")}}


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    import sprint_r10_grid as T
    base = tmp_path_factory.mktemp("r10tool")
    root, out = base / "alpaca", base / "sprint"
    out.mkdir(parents=True)
    dev = [date.fromisoformat(d) for d in book.sessions_between("2025-06-02", "2025-06-13")]
    hist = [date.fromisoformat(d) for d in book.sessions_between("2019-11-18", "2020-01-10")]
    for k, sym in enumerate(("SPY", "QQQ")):
        SS.write_cache(root, sym, dev, px0=500.0 - 60 * k, seed=70 + k, next_expiry=True)
        SS.write_stock_only(root, sym, hist, px0=300.0 - 60 * k, seed=80 + k, vol=0.0008)
    SS.write_daily(root, "VIXY", date(2014, 11, 3), date(2026, 6, 30), skip=[periods.LOCKED["L2"], periods.LOCKED["L1"]])
    (out / "calib_modeled.json").write_text(json.dumps(CAL))
    args = ["--data", str(root), "--out", str(out), "--today", "2026-11-02", "--symbols", "SPY,QQQ"]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(G, "MIN_DISC", 1)
        rc1 = T.main(args)
        md1 = (out / "r10grid_2026-11-02.md").read_text()
        js1 = (out / "r10grid_2026-11-02.json").read_text()
        rc2 = T.main(args)                                                   # a re-run reuses every chunk
    return {"out": out, "root": root, "rc": (rc1, rc2), "md": (md1, (out / "r10grid_2026-11-02.md").read_text()),
            "json": (js1, (out / "r10grid_2026-11-02.json").read_text()), "args": args, "T": T}


def test_tool_writes_everything_and_reproduces_itself(world):
    out = world["out"]
    assert world["rc"] == (0, 0)
    assert world["md"][0] == world["md"][1] and world["json"][0] == world["json"][1]
    md = world["md"][0]
    for lab in ("BACKTEST", "MODELED", "REAL", "## The grid", "Heat map", "## R2, R3, R4", "## Addendum 15.3", "## R1 pm_inside_break",
                "regime features", "Deflated Sharpe", "NOT VALIDATED"):
        assert lab in md, lab
    for f in ("r10grid_cells_2026-11-02.csv.gz", "trades_r10grid_2026-11-02.csv.gz", "trades_r10_af153_2026-11-02.csv.gz",
              "trades_r10_r1_shares_2026-11-02.csv.gz", "trades_r10_r1_options_2026-11-02.csv.gz", "r10grid_frozen.json"):
        assert (out / f).exists(), f
    res = json.loads(world["json"][0])["result"]
    t = res["trials"]
    assert t["this_build"] == 7587 and t["round10_total"] == 7767 and t["total_for_dsr"] == t["prior_in_run_logs"] + 7767
    assert t["prior_in_run_logs"] >= 1                                       # docs/research/sprint_runs.csv rows
    frozen = json.loads((out / "r10grid_frozen.json").read_text())
    chosen = {e: v["cell"] for e, v in frozen["entries"].items()}
    assert any(chosen.values()) and res["frozen"]["choices"] == chosen
    for e, c in chosen.items():
        g = res["grid"][e]
        assert set(g["summary"]) == {"disc", "h1", "h2"}
        if c:
            assert g["chosen"] == c and set(g["addons"]) == {"R2 d55-70t60", "R3 scale-out (3 contracts)", "R4 ratchet"}
            assert any("random-side twin" in n for n, _ok in g["holdout2"]["checks"])
            assert set(g["regime"]["terciles"]) == set(features.REGIME10)
    with gzip.open(out / "r10grid_cells_2026-11-02.csv.gz", "rt") as f:
        assert sum(1 for _ in f) == 7560 + 1
    assert res["af"] and set(res["af"]["variants"]) >= {"af153 SPY", "af153_nogate SPY", "af153 QQQ"}
    assert res["r1"] and set(res["r1"]["claim"]) == {"HIST 2016-2024", "DEV", "all"}
    cal = json.loads((out / "r10grid_cache" / "r10grid_calib.json").read_text())
    assert cal["keys"]["d20-30t25|C"] == CAL["keys"]["d20-30t25|C"]           # run 4 had it: never replaced


def test_frozen_choice_is_refused_when_it_would_change(world, monkeypatch):
    T = world["T"]
    out = world["out"]
    doc = json.loads((out / "r10grid_frozen.json").read_text())
    e = next(k for k, v in doc["entries"].items() if v["cell"])
    doc["entries"][e]["cell"] = "s10.t20.none.m30.d40-55t45.off" if doc["entries"][e]["cell"] != "s10.t20.none.m30.d40-55t45.off" else \
        "s20.t20.none.m30.d40-55t45.off"
    (out / "r10grid_frozen.json").write_text(json.dumps(doc))
    monkeypatch.setattr(G, "MIN_DISC", 1)
    with pytest.raises(RuntimeError):
        T.main(world["args"] + ["--stage", "analyze"])


# ---------------------------------------------------------------- the compounding hook (Amendment 16; sprint/compound.py)
def _fake_world():
    res = {"grid": {"orb15": {"survives": True, "chosen": "s20.t50.none.1525.d40-55t45.off",
                              "addons": {"R2 d55-70t60": {"pass": False}, "R3 scale-out (3 contracts)": {"pass": True},
                                         "R4 ratchet": {"pass": False}}},
                    "pd_retest": {"survives": False, "chosen": "x", "addons": {}}},
           "af": {"variants": {"af153 SPY": {"bar": {"pass": True}}, "af153_nogate SPY": {"bar": {"pass": False}}}, "r2": {"pass": False}},
           "r1": {"shares": {"bar": {"pass": True}}, "options": {"d40-55t45": {"bar": {"pass": False}}}}}
    trk = []
    for day in ("2019-03-04", "2021-06-01", "2025-02-03"):
        for var, kind, debit in (("frozen", "real", 120.65), ("frozen", "twin", 99.0), ("R3", "real", 361.95), ("R2", "real", 250.0)):
            trk.append({"entry": "orb15", "variant": var, "kind": kind, "day": day, "pnl": 10.0, "debit": debit})
    trades = {"tracked": trk,
              "af": [{"variant": v, "symbol": s, "day": d, "pnl": -5.0, "debit": 80.65} for v in ("af153", "af153_r2")
                     for s in ("SPY", "QQQ") for d in ("2018-05-01", "2025-03-03")],
              "r1_shares": [{"day": "2017-02-01", "pnl": 12.0, "notional": 9990.0, "qualifies": True},
                            {"day": "2017-02-02", "pnl": 1.0, "notional": 9990.0, "qualifies": False}],
              "r1_options": [{"variant": "r1_d40-55t45_qual", "day": "2025-01-02", "pnl": 3.0, "debit": 150.0}]}
    return res, trades


def test_passing_rules_pick_only_what_passed_with_its_windows_and_risk():
    res, trades = _fake_world()
    jobs = {name: (rows, key, wins) for name, rows, key, wins in G.passing_rules(res, trades)}
    assert set(jobs) == {"grid orb15 s20.t50.none.1525.d40-55t45.off", "orb15 R3 scale-out (3 contracts)", "15.3/16.2 af153 SPY", "R1 shares"}
    rows, key, wins = jobs["grid orb15 s20.t50.none.1525.d40-55t45.off"]
    assert len(rows) == 3 and key == "debit" and [w[0] for w in wins] == ["holdout 1", "holdout 2"]
    assert all(r["kind"] == "real" and r["variant"] == "frozen" for r in rows)
    assert jobs["orb15 R3 scale-out (3 contracts)"][0][0]["debit"] == 361.95
    assert [w[0] for w in jobs["15.3/16.2 af153 SPY"][2]] == ["HIST", "DEV"] and all(r["symbol"] == "SPY" for r in jobs["15.3/16.2 af153 SPY"][0])
    assert jobs["R1 shares"][1] == "notional" and len(jobs["R1 shares"][0]) == 1
    h1 = G.compounding_inputs(rows, "debit", *G.H1)
    assert h1 == [{"day": "2021-06-01", "pnl": 10.0, "risk": 120.65}]


def test_the_tool_calls_compound_for_every_passing_rule_and_window(monkeypatch):
    import sprint
    import sprint_r10_grid as T
    calls = []
    stub = types.ModuleType("sprint.compound")
    stub.LABEL = "stub view"

    def simulate(rows, sessions=None, label=None, **kw):
        calls.append((rows, list(sessions), label))
        return {"label": label, "input": {"trades": len(rows)}, "fractions": {}}
    stub.simulate = simulate
    stub.render_md = lambda v, title="": [f"- {title}"]
    monkeypatch.setitem(sys.modules, "sprint.compound", stub)
    monkeypatch.setattr(sprint, "compound", stub, raising=False)
    res, trades = _fake_world()
    warnings = []
    out, md = T.compounding(res, trades, warnings)
    assert not warnings and set(out) == {"grid orb15 s20.t50.none.1525.d40-55t45.off", "orb15 R3 scale-out (3 contracts)",
                                         "15.3/16.2 af153 SPY", "R1 shares"}
    assert out["R1 shares"]["DEV"] is None and out["R1 shares"]["HIST"]["input"]["trades"] == 1
    for rows, sessions, label in calls:
        assert rows and all(r["day"] in sessions for r in rows) and len(sessions) == len(set(sessions))
        assert all(set(r) == {"day", "pnl", "risk"} and r["risk"] > 0 for r in rows)
        assert ("REAL" in label) == (sessions[0] >= G.DEV_A)
    h2 = [c for c in calls if c[0][0]["risk"] == 120.65 and c[1][0] == G.DEV_A][0]
    assert h2[1] == book.sessions_between(G.DEV_A, G.DEV_B)                  # every session of the window, trade or not
    assert any("R1 shares, HIST" in line for line in md) and md[0].startswith("## Compounding view")
    monkeypatch.setitem(sys.modules, "sprint.compound", None)                  # not on this branch yet: skipped with a warning
    monkeypatch.delattr(sprint, "compound", raising=False)
    out2, md2 = T.compounding(res, trades, warnings)
    assert out2 is None and warnings and "NOT RUN" in " ".join(md2)


def test_tool_refuses_rows_in_locked_periods():
    import sprint_r10_grid as T
    assert T.check_rows([{"day": "2024-03-05"}], "x").startswith("REFUSED")
    assert T.check_rows([{"day": "2026-08-03"}], "x").startswith("REFUSED")
    assert T.check_rows([{"day": "2025-03-05"}, {"day": "2019-03-05"}], "x") is None
