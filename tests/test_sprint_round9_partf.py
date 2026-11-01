"""Round 9 Part F and the universes (SPRINT_PLAN Amendment 12): U-STK's common-stock test, the panel's per-symbol rolling
windows and point-in-time filter, rsi2 and tom on hand-built bars (fills, costs, the cap, no look-ahead), the locked-period
rules for multi-day windows, the random-entry benchmark's determinism, the pass bar, and F-opt's pick and P/L. Synthetic
data only."""
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

import sprint_synth  # noqa: F401
from sprint import contracts, multiday as M, periods, shares, universe as U
from sprint import bs


# ---------------------------------------------------------------- U-STK's common-stock test
def _asset(sym, name, **kw):
    a = {"symbol": sym, "class": "us_equity", "status": "active", "tradable": True, "exchange": "NYSE", "attributes": ["has_options"],
         "name": name}
    a.update(kw)
    return a


@pytest.mark.parametrize("name,ok", [
    ("Apple Inc. Common Stock", True), ("Ultra Clean Holdings, Inc. Common Stock", True), ("Invesco Ltd Common Stock", True),
    ("WisdomTree, Inc. Common Stock", True), ("Amplify Energy Corp. Common Stock", True), ("Unity Software Inc.", True),
    ("Federal Realty Investment Trust Common Shares of Beneficial Interest", True),
    ("iShares Core S&P 500 ETF", False), ("Invesco QQQ Trust, Series 1", False), ("ProShares UltraPro QQQ", False),
    ("Permian Basin Royalty Trust Units of Beneficial Interest", False), ("Energy Transfer LP Common Units", False),
    ("Alibaba Group Holding Limited American Depositary Shares", False), ("Acme Corp 6.5% Series A Preferred", False),
    ("Acme Acquisition Corp Warrants", False), ("Acme Notes due 2030", False), ("Vanguard Growth Fund", False)])
def test_is_common_names(name, ok):
    assert U.is_common(_asset("ABCD", name))[0] is ok


def test_is_common_record_fields_and_build_list():
    assert U.is_common(_asset("ABC", "X Common Stock", attributes=[]))[1] == "no listed options"
    assert U.is_common(_asset("ABC", "X Common Stock", exchange="OTC"))[1] == "exchange OTC"
    assert U.is_common(_asset("ABC", "X Common Stock", tradable=False))[1] == "not tradable"
    assert U.is_common(_asset("SPY", "SPDR S&P 500 ETF Trust"))[1] == "U-ETF symbol"
    assert U.is_common(_asset("BRK.B", "Berkshire Hathaway Inc. Class B Common Stock"))[0]
    assert not U.is_common(_asset("AB-CD", "X Common Stock"))[0]
    res = U.build_ustk([_asset("AAA", "A Common Stock"), _asset("EEE", "E ETF"), _asset("AAA", "A Common Stock")])
    assert res["symbols"] == ["AAA"] and res["excluded"] == {"EEE": "fund: ETF/ETN"} and res["label"] == U.SB


# ---------------------------------------------------------------- hand-built panels
def _days(a="2017-01-03", n=260):
    out = [d for d in U.sessions(date.fromisoformat(a), date(2026, 6, 30))]
    return out[:n]


def _frame(days, closes, opens=None, vol=1_000_000.0):
    c = np.asarray(closes, float)
    o = np.concatenate([[c[0]], c[:-1]]) if opens is None else np.asarray(opens, float)
    df = pd.DataFrame({"o": o, "h": np.maximum(o, c), "l": np.minimum(o, c), "c": c, "v": np.full(len(c), vol)}, index=list(days))
    return df[np.isfinite(df["c"])]


def _rsi2_closes(n=260, at=220):
    """A steady uptrend, two down closes at `at`, `at`+1 (RSI(2) < 10 at `at`), then a close above SMA(5) at `at`+2."""
    c = 100 + 0.1 * np.arange(n)
    c[at] = c[at - 1] - 1.5
    c[at + 1] = c[at] + 0.6
    c[at + 2] = c[at] + 2.1
    c[at + 3:] = c[at + 2] + 0.1 * np.arange(1, n - at - 2)
    return c


def test_rsi2_entry_exit_fills_and_costs():
    days = _days()
    c = _rsi2_closes()
    p = U.Panel(["SPY"], {"SPY": _frame(days, c)}, None, days)
    r = p.rsi(2)[:, 0]
    assert r[219] == 100.0 and r[220] < 10 and not np.isnan(p.sma(200)[219, 0]) and np.isnan(p.sma(200)[198, 0])
    tr, info = M.rsi2(p, ["SPY"], "U-ETF")
    assert len(tr) == 1 and info["signals"] == 1
    t = tr[0]
    assert (t["signal_day"], t["entry_day"], t["exit_day"]) == (days[220].isoformat(), days[221].isoformat(), days[223].isoformat())
    sh = math.floor(10_000 / c[220])
    assert t["shares"] == sh and t["entry_ref"] == pytest.approx(c[220]) and t["exit_ref"] == pytest.approx(c[222])
    assert t["pnl"] == pytest.approx(sh * (c[222] - c[220]) - 2 * 0.01 * sh, abs=1e-3)
    assert t["pnl_2x"] == pytest.approx(sh * (c[222] - c[220]) - 4 * 0.01 * sh, abs=1e-3)
    assert t["day"] == t["exit_day"] and t["_src"] == "HIST" and t["hold"] == 2


def test_rsi2_ustk_costs_split_neutral_and_raw_sizing():
    days = _days()
    c = _rsi2_closes()
    raw = c * 4.0                                       # a later 4:1 split: raw prices are 4x the adjusted ones
    p = U.Panel(["AAA"], {"AAA": _frame(days, c)}, {"AAA": _frame(days, raw)}, days)
    tr, _ = M.rsi2(p, ["AAA"], "U-STK")
    t = tr[0]
    sh = math.floor(10_000 / raw[220])
    move = raw[220] * (c[222] / c[220]) - raw[220]
    assert t["shares"] == sh and t["label"] == U.SB
    assert t["pnl"] == pytest.approx(sh * move - 0.0005 * sh * (raw[220] + raw[220] + move), abs=1e-3)


def test_rsi2_no_look_ahead():
    days = _days()
    c = _rsi2_closes()
    p1 = U.Panel(["SPY"], {"SPY": _frame(days, c)}, None, days)
    c2 = c.copy()
    c2[230:] = c2[230:] * np.linspace(1.0, 0.7, len(c2) - 230)   # a crash after the trade
    p2 = U.Panel(["SPY"], {"SPY": _frame(days, c2)}, None, days)
    a, _ = M.rsi2(p1, ["SPY"], "U-ETF")
    b, _ = M.rsi2(p2, ["SPY"], "U-ETF")
    keep = lambda tr: [t for t in tr if t["exit_day"] <= days[229].isoformat()]
    assert keep(a) == keep(b) and len(keep(a)) == 1
    for x in ("sma", "rsi"):
        f1 = p1.sma(5) if x == "sma" else p1.rsi(2)
        f2 = p2.sma(5) if x == "sma" else p2.rsi(2)
        assert np.array_equal(f1[:230], f2[:230], equal_nan=True)


def test_ustk_cap_takes_the_ten_lowest_rsi2():
    days = _days()
    syms = [f"S{k:02d}" for k in range(12)]
    frames = {}
    for k, s in enumerate(syms):
        c = 100 + 0.1 * np.arange(260)
        c[220] = c[219] - (1.0 + 0.2 * k)               # deeper drops -> lower RSI(2)
        c[221] = c[220] + 3.0
        c[222:] = c[221] + 0.1 * np.arange(1, 39)
        frames[s] = _frame(days, c)
    p = U.Panel(syms, frames, None, days)
    tr, info = M.rsi2(p, syms, "U-STK", cap=10)
    assert len(tr) == 10 and sorted(t["symbol"] for t in tr) == syms[2:]
    assert info["dropped"]["U-STK daily cap (10 lowest RSI(2))"] == 2


def test_compact_rolling_skips_missing_bars_and_eligibility_is_point_in_time():
    days = _days(n=60)
    c = np.full(60, 10.0)
    c[30] = np.nan                                      # no trade that day
    v = np.full(60, 6_000_000.0)
    df = _frame(days, c, vol=6_000_000.0)
    p = U.Panel(["AAA"], {"AAA": df}, None, days)
    s5 = p.sma(5)[:, 0]
    assert np.isnan(s5[30]) and s5[31] == pytest.approx(10.0) and np.isnan(s5[3]) and s5[4] == pytest.approx(10.0)
    el = p.eligible()[:, 0]
    assert not el[:20].any() and el[20] and el[31]       # 20 bars of $60M before day 20; day 30's gap is skipped
    df2 = df.copy()
    df2.loc[days[40], "v"] = 0.0                         # day 40's own volume can't change day 40's filter
    df2.loc[days[40], "c"] = 1.0
    p2 = U.Panel(["AAA"], {"AAA": df2}, None, days)
    assert p2.eligible()[40, 0] == el[40] and not p2.eligible()[41, 0]
    assert v.sum() > 0


def test_panel_segments_never_cross_l2_and_tom_drops_locked_windows():
    days = U.sessions(date(2023, 1, 3), date(2024, 12, 31))
    assert date(2024, 3, 1) not in days
    p = U.Panel(["SPY"], {"SPY": _frame(days, 400 + np.arange(len(days)) * 0.1)}, None, days)
    k = p.idx(date(2024, 8, 1))
    assert p.seg[k] == 1 and p.seg[k - 1] == 0
    s20 = p.sma(20)[:, 0]
    assert np.isnan(s20[k:k + 19]).all() and not np.isnan(s20[k + 19])
    tr, info = M.tom(p, ["SPY"], "U-ETF")
    assert all(not U.touches_locked(date.fromisoformat(t["entry_day"]), date.fromisoformat(t["exit_day"])) for t in tr)
    assert not any(t["entry_day"] == "2024-01-31" for t in tr) and info["dropped"]["holding window touches L1/L2"] >= 6
    t = next(t for t in tr if t["entry_day"] == "2023-03-31")
    assert t["exit_day"] == "2023-04-05" and t["fill"] == "close"           # April 2023: 3, 4, 5 (Good Friday was April 7)


def test_rsi2_position_open_at_the_l2_gap_is_dropped():
    days = U.sessions(date(2023, 1, 3), date(2024, 9, 30))
    k = days.index(date(2024, 1, 30))
    c = 100 + 0.1 * np.arange(len(days))
    c[k] = c[k - 1] - 2.0                               # signal on 2024-01-30, entry 2024-01-31, no exit before L2
    c[k + 1] = c[k] - 0.5
    p = U.Panel(["SPY"], {"SPY": _frame(days, c)}, None, days)
    tr, info = M.rsi2(p, ["SPY"], "U-ETF")
    assert not any(t["entry_day"] == "2024-01-31" for t in tr)
    assert info["dropped"]["still open at the L2 gap (exit would be in L2)"] == 1
    assert all(t["entry_day"] >= "2024-08-01" or t["exit_day"] <= "2024-01-31" for t in tr)


def test_random_entry_is_deterministic_and_matches_the_rule_shape():
    days = _days(n=400)
    rng = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0006, 0.012, 400)))
    p = U.Panel(["SPY"], {"SPY": _frame(days, c)}, None, days)
    tr, _ = M.rsi2(p, ["SPY"], "U-ETF")
    assert tr
    a = M.random_entry(p, tr, "U-ETF")
    b = M.random_entry(p, tr, "U-ETF")
    assert a[0] == b[0] and np.array_equal(a[1], b[1]) and len(a[1]) == 200 and 0.0 <= a[0] <= 1.0


def test_f_pass_items():
    sess = shares.all_sessions()
    rows = []
    for k, d in enumerate(sess[::3]):
        p = 10.0 if k % 4 else -5.0
        rows.append({"symbol": "SPY", "day": d, "entry_idx": 0, "pnl": p, "pnl_2x": p - 1, "bps": p, "side": "L"})
    res = M.f_pass(rows, sess, rnd_p=0.01)
    assert res["pass"] and len(res["checks"]) == 7
    res = M.f_pass(rows, sess, rnd_p=0.2)
    assert not res["pass"] and not res["checks"][5][1]
    res = M.f_pass(rows[:150], sess, rnd_p=0.01)
    assert not res["checks"][0][1]


# ---------------------------------------------------------------- F-opt
def _chain(day, S, iv=0.2):
    rows = []
    for exp in (date(2025, 3, 21), date(2025, 4, 17), date(2025, 5, 16)):
        T = bs.t_years(390 + 1440 * (exp - day).days)
        for k in range(int(S * 0.85), int(S * 1.01) + 1):
            px = round(bs.price(S, k, T, iv, "C"), 2)
            rows.append({"ts": f"{day}T09:31:00-05:00", "o": px, "h": px, "l": px, "c": px, "v": 5.0,
                         "symbol": f"SPY{exp:%y%m%d}C{k * 1000:08d}"})
    return pd.DataFrame(rows)


def test_fopt_pick_dte_and_delta_band_and_pnl():
    day = date(2025, 2, 18)
    S = 600.0
    ent = _chain(day, S)
    info, why = contracts.pick_daily(M.candidates(ent), S, day, M.FOPT_RULE, "C")
    assert why is None and 30 <= info["dte"] <= 60 and 0.60 <= info["delta"] <= 0.80 and info["expiry"] == "2025-03-21"
    assert abs(info["delta"] - 0.70) <= 0.03
    tr = {"variant": "rsi2", "symbol": "SPY", "entry_day": day.isoformat(), "exit_day": "2025-02-21", "pnl": 1.0}
    exi = pd.DataFrame([{"ts": "2025-02-21T09:30:00-05:00", "o": info["px"] + 1.0, "h": 0, "l": 0, "c": 0, "v": 1, "symbol": info["symbol"]}])
    row, why = M.fopt_trade(tr, ent, exi, S)
    hs_in, hs_out = max(0.02 * info["px"], 0.005), max(0.02 * (info["px"] + 1.0), 0.005)
    assert row["pnl"] == pytest.approx(100 * ((info["px"] + 1.0 - hs_out) - (info["px"] + hs_in)) - 1.30, abs=0.01)
    assert row["pnl_2x"] == pytest.approx(100 * ((info["px"] + 1.0 - 2 * hs_out) - (info["px"] + 2 * hs_in)) - 1.30, abs=0.01)
    assert not row["exit_late"]
    row, why = M.fopt_trade(tr, ent, exi.iloc[0:0], S)
    assert row is None and "no print" in why
    bad = dict(tr, exit_day="2026-07-02")
    assert M.fopt_trade(bad, ent, exi, S) == (None, "holding window touches L1/L2")


def test_fopt_bar():
    rows = [{"day": "2025-03-01", "pnl": 30.0 if k % 3 else -20.0, "pnl_2x": 25.0 if k % 3 else -25.0, "entry_idx": 0, "symbol": "SPY"}
            for k in range(45)]
    assert M.fopt_bar(rows)["pass"]
    assert not M.fopt_bar(rows[:39])["pass"]
