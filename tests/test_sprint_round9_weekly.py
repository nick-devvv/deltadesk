"""Round 9 Part I (SPRINT_PLAN Amendment 12): the weekly-expiry reader keeps the nearest expiry 5-10 calendar days out, FIN-H's
entry needs relative volume >= 1.06, the w5-10d03-12t07 pick and exit (i) on a synthetic DEV day, the DEV bar and the
"steadier than FIN-H" readout on the same days. Synthetic data only."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
import pull_alpaca as PA
from sprint import contracts, data, periods, weekly as W


def _setup(tmp_path, day=date(2025, 3, 4), vol_today=2.0):
    pre = SS.weekdays(day - timedelta(days=30), 25)
    pre = [d for d in pre if d < day][-14:]
    days = pre + [day]
    stock = SS.write_stock_only(tmp_path, "SPY", days, px0=500.0, seed=7)
    f = tmp_path / "stocks" / "SPY" / f"{day:%Y-%m}.csv.gz"
    df = PA.read_gz(f)
    m = df["ts"].dt.date == day
    df.loc[m, "v"] = df.loc[m, "v"] * vol_today              # today's volume x vol_today, so rvol at 11:00 is known
    PA._write_gz(f, df)
    stock[day] = df[m].reset_index(drop=True)
    PA._write_gz(tmp_path / "options" / "SPY" / day.isoformat() / "bars.csv.gz", SS.option_bars(day, stock[day], "SPY", band=0.03, seed=1))
    frames = []
    for exp in (day + timedelta(days=3), day + timedelta(days=7), day + timedelta(days=12)):
        ob = SS.option_bars(day, stock[day], "SPY", iv=0.18, band=0.05, seed=1, expiry=exp)
        frames.append(ob[ob["symbol"].str[-9] == "C"])
    PA._write_gz(tmp_path / "options_w5" / "SPY" / day.isoformat() / "bars.csv.gz", pd.concat(frames, ignore_index=True))
    ser = data.Series("SPY", data.read_stock("SPY", days[0], day, tmp_path))
    return ser, day


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    t = tmp_path_factory.mktemp("w5")
    return t, _setup(t)


def test_reader_keeps_the_nearest_expiry_5_to_10_days_out(built):
    tmp_path, (ser, day) = built
    tapes = W.read_weekly_day("SPY", day, tmp_path)
    exps = {t.expiry for t in tapes.values()}
    assert exps == {day + timedelta(days=7)}
    assert W.read_weekly_day("SPY", day + timedelta(days=1), tmp_path) == {}
    assert W.expiry_window(date(2025, 3, 4))[0] == date(2025, 3, 10) and W.expiry_window(date(2025, 3, 4))[-1] == date(2025, 3, 14)


def test_finh_entry_needs_rvol_and_weekly_pick_and_exit(built, tmp_path):
    root, (ser, day) = built
    ctx = data.DayContext(ser, day, {}, None)
    ok, rv = W.finh_signal(ctx)
    assert ok and rv >= 1.06
    ctx.tapes_weekly = W.read_weekly_day("SPY", day, root)
    ctx.tapes = data.read_option_day("SPY", day, root)
    from sprint import spread as SP
    sp = SP.SpreadModel()
    row, why = W.trade(ctx, W.WEEKLY_RULE, sp)
    assert why is None and row["signal_idx"] == 89 and row["exit_reason"] in ("ALL OUT", "FIXED STOP")
    assert row["expiry"] == (day + timedelta(days=7)).isoformat() and 0.03 <= row["delta_est"] <= 0.12
    assert row["exit_idx"] >= 355 or row["exit_reason"] == "FIXED STOP"
    ser2, _ = _setup(tmp_path / "low", vol_today=0.5)
    ok2, why2 = W.finh_signal(data.DayContext(ser2, day, {}, None))
    assert not ok2 and why2 == "rvol below 1.06"


def test_run_refuses_locked_ranges_and_reports(built):
    tmp_path, (ser, day) = built
    res, skips, cover = W.run({"SPY": ser}, a=day, b=day, root=tmp_path)
    assert len(res["weekly"]) == 1 and len(res["finh_0dte"]) == 1 and cover["SPY"]["weekly_files"] == 1
    with pytest.raises(periods.LockedPeriod):
        W.run({"SPY": ser}, a=date(2024, 7, 1), b=date(2024, 8, 30), root=tmp_path)


def _rows(days, pnls):
    return [{"symbol": "SPY", "day": d, "pnl": p, "pnl_2x": p - 1.0, "entry_idx": 90} for d, p in zip(days, pnls)]


def test_dev_bar_and_steadier_readout():
    days = [f"2025-{m:02d}-{d:02d}" for m in range(1, 7) for d in (3, 10, 17)] * 3
    days = sorted(days)[:45]
    wk = _rows(days, [20.0 if k % 3 else -8.0 for k in range(45)])
    fin = _rows(days, [60.0 if k % 9 == 0 else -15.0 for k in range(45)])
    res = W.part_i({"weekly": wk, "finh_0dte": fin})
    assert res["bar"]["pass"] and res["pass"]
    st = res["steadier"]
    assert st["common_days"] == len(set(days)) and st["steadier"]
    assert all(ok for _, ok in st["checks"])
    res2 = W.part_i({"weekly": wk[:30], "finh_0dte": fin})
    assert not res2["pass"]
