"""setups_v2 additions (pre-registered 2026-10-31): failed-break variants and its put mirror (rules, no look-ahead),
the bot risk pass (sprint/engine.bot_risk), next-expiry contracts (loader, picker, BS time to expiry), the
next-expiry puller (fallback to the next listed expiry, resumable) and an end-to-end runner check."""
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

import sprint_synth as SS
from sprint import bs, contracts, engine, entries, runner
from sprint.data import DayContext, Series, read_option_day
from test_sprint_entries import _ctx_from, _failed_break_ctx, _with_future_changed
from test_sprint_runner import FakeAlpaca


def _sig(ctx, name):
    return [(s.side, s.idx, s.info["kind"], round(s.invalid, 2)) for s in entries.signals(ctx, name)]


def _mirror_ctx():
    # PDH 500.30: close above at 09:50 (high 500.45), back below two bars later
    return _ctx_from({0: 500.0, 20: 500.40, 22: 500.20}, bars={20: (500.25, 500.45, 500.24, 500.40)}, prior_range=0.30)


def test_failed_break_base_is_unchanged_and_variants_move_one_number():
    ctx = _failed_break_ctx()                                   # probe 0.15 below PDL, ATR(14, 5m) ~0.45
    assert _sig(ctx, "failed_break") == [("C", 22, "PDL", 499.55)]
    assert _sig(ctx, "failed_break_p025") == []                 # 0.15 > 0.25 x 0.45
    assert _sig(ctx, "failed_break_p075") == _sig(ctx, "failed_break_p100") == [("C", 22, "PDL", 499.55)]
    assert _sig(ctx, "failed_break_pd") == [("C", 22, "PDL", 499.55)]
    assert _sig(ctx, "failed_break_or") == []                   # opening-range lows only: PDL is not one
    slow = _ctx_from({0: 500.0, 20: 499.60, 24: 499.80}, bars={20: (499.75, 499.76, 499.55, 499.60)}, prior_range=0.30)
    assert _sig(slow, "failed_break") == _sig(slow, "failed_break_w10") == [("C", 24, "PDL", 499.55)]
    assert _sig(slow, "failed_break_w3") == []                  # back above 4 bars later: outside a 3-bar window
    assert [s.setup for s in entries.signals(ctx, "failed_break_w3")] == ["failed_break_w3"]
    assert entries.signals(ctx, "failed_break", "P") == [] and entries.signals(ctx, "failed_high", "C") == []


def test_failed_high_mirrors_failed_break_for_puts():
    m = _mirror_ctx()
    assert _sig(m, "failed_high") == [("P", 22, "PDH", 500.45)]
    assert _sig(m, "failed_break") == []
    assert _sig(_failed_break_ctx(), "failed_high") == []
    deep = _ctx_from({0: 500.0, 20: 500.40, 22: 500.20}, bars={20: (500.25, 502.0, 500.24, 500.40)}, prior_range=0.30)
    assert _sig(deep, "failed_high") == []                      # went more than 0.5 ATR(5m) through: not a probe


@pytest.mark.parametrize("name,make", [("failed_high", _mirror_ctx), ("failed_break_w10", _failed_break_ctx),
                                       ("failed_break_p075", _failed_break_ctx), ("failed_break_pd", _failed_break_ctx)])
def test_v2_entries_have_no_look_ahead(name, make):
    ctx = make()
    full = entries.signals(ctx, name)
    assert full
    for cut in sorted({max(16, full[0].idx - 1), full[0].idx, full[0].idx + 1, 100, 260}):
        got = entries.signals(_with_future_changed(ctx, cut, seed=cut), name)
        assert [(s.side, s.idx, s.price) for s in got if s.idx <= cut] == [(s.side, s.idx, s.price) for s in full if s.idx <= cut]


def test_nudges_cover_the_failed_break_numbers():
    r = {"entry": "failed_break", "exit": engine.ExitCfg(stop="premium", time="b"), "symbols": ("SPY",), "side": "C", "filters": ()}
    got = {v for k, v, _ in engine.nudges(r) if k == "entry"}
    assert got == {"failed_break_w3", "failed_break_w10", "failed_break_p025", "failed_break_p075"}


def _t(day, sym, e, x, pnl, risk=30.0):
    return {"day": day, "symbol": sym, "entry_idx": e, "exit_idx": x, "pnl": pnl, "planned_risk": risk}


def test_bot_risk_rules():
    d1, d2 = date(2025, 3, 10), date(2025, 3, 11)
    tr = [_t(d1, "SPY", 20, 25, -10), _t(d1, "QQQ", 30, 35, -10),      # two losses, the second closes at 35
          _t(d1, "SPY", 40, 50, 50),                                  # inside the 10-minute cooldown -> skipped
          _t(d1, "QQQ", 46, 60, -10),                                 # cooldown over -> taken (third loss)
          _t(d1, "SPY", 70, 80, 99),                                  # 3 losses in a row -> done for the day
          _t(d2, "SPY", 20, 30, 5, risk=60.0),                        # planned loss above $50 -> skipped
          _t(d2, "SPY", 31, 32, 5), _t(d2, "QQQ", 33, 34, 5), _t(d2, "IWM", 35, 36, -5), _t(d2, "SPY", 37, 38, 5),
          _t(d2, "QQQ", 39, 40, 5)]                                   # the 5th of the day -> skipped
    kept, skips = engine.bot_risk(tr)
    assert [(t["day"].day, t["symbol"], t["entry_idx"]) for t in kept] == [
        (10, "SPY", 20), (10, "QQQ", 30), (10, "QQQ", 46), (11, "SPY", 31), (11, "QQQ", 33), (11, "IWM", 35), (11, "SPY", 37)]
    assert skips == {"risk: 10-minute cooldown after 2 losses": 1, "risk: 3 losses in a row, done for the day": 1,
                     "risk: planned loss > $50 at 1 contract": 1, "risk: 4 trades already today": 1}
    open_loss = [_t(d1, "SPY", 20, 25, -10), _t(d1, "QQQ", 22, 40, -10), _t(d1, "SPY", 30, 31, 1)]
    assert len(engine.bot_risk(open_loss)[0]) == 3              # a loss still open at the entry does not count yet


def test_next_expiry_loader_and_picker(tmp_path):
    import pull_alpaca as PA
    days = SS.weekdays(date(2025, 3, 10), 5)                    # Mon .. Fri
    fri = days[-1]
    st = SS.stock_day(fri, 500.0, seed=4)
    s = Series("SPY", pd.concat([SS.stock_day(d, 500.0, seed=k) for k, d in enumerate(days[:-1])] + [st], ignore_index=True))
    mon = fri + timedelta(days=3)
    nb = pd.concat([SS.option_bars(fri, st, "SPY", band=0.01, expiry=mon),
                    SS.option_bars(fri, st, "SPY", band=0.01, expiry=mon + timedelta(days=1))], ignore_index=True)
    PA._write_gz(tmp_path / "options_next" / "SPY" / fri.isoformat() / "bars.csv.gz", nb)
    PA._write_gz(tmp_path / "options" / "SPY" / fri.isoformat() / "bars.csv.gz", SS.option_bars(fri, st, "SPY", band=0.01))
    tn = read_option_day("SPY", fri, tmp_path, want_trades=False, expiry="next")
    assert tn and {t.expiry for t in tn.values()} == {mon}       # only the nearest later expiry
    t0 = read_option_day("SPY", fri, tmp_path)
    assert {t.expiry for t in t0.values()} == {fri}
    ctx = DayContext(s, fri, t0, SS.ConstSpread(), early_close=False, tapes_next=tn)
    tape, info = contracts.pick(ctx, "C", 60, "n1d40-55t45")
    assert tape is not None and tape.symbol in tn and info["expiry"] == mon.isoformat() and 0.40 <= info["delta"] <= 0.55
    assert info["iv"] == pytest.approx(0.18, abs=0.02)          # the 3 calendar days to Monday are in the BS time
    tape0, info0 = contracts.pick(ctx, "C", 60)
    assert tape0.symbol in t0 and info0["expiry"] == fri.isoformat()
    bare = DayContext(s, fri, t0, SS.ConstSpread(), early_close=False)
    assert contracts.pick(bare, "C", 60, "n1d40-55t45") == (None, "no next-expiry contracts on file for this side")


def test_next_expiry_puller_falls_back_and_resumes(tmp_path, monkeypatch):
    import pull_alpaca as PA
    import sprint_pull as SPL
    days = SS.weekdays(date(2025, 1, 27), 3)                    # Mon .. Wed
    stock = pd.concat([SS.stock_day(d, 500, k) for k, d in enumerate(days)], ignore_index=True)

    class OnlyWed(FakeAlpaca):                                  # Alpaca lists no Tuesday expiry: fall back to Wednesday
        def __call__(self, url, headers):
            q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
            if "/options/" in url and "250128" in q["symbols"]:
                self.calls.append(url)
                return {"bars": {}}
            return super().__call__(url, headers)

    fake = OnlyWed(stock)
    monkeypatch.setattr(PA, "_http", fake)
    monkeypatch.setattr(PA, "_calls", [])
    monkeypatch.setattr(PA, "ROOT", tmp_path / "alpaca")
    monkeypatch.setenv("ALPACA_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET", "s")
    SPL.pull_stock("SPY", days[0], days[-1], today=date(2026, 10, 31), log=lambda *x: None)
    r = SPL.pull_options_next("SPY", days[0], days[0], band=0.01, today=date(2026, 10, 31), log=lambda *x: None)
    assert r["days"] == 1 and r["bars"] > 0
    done = json.loads((PA.ROOT / "options_next" / "SPY" / days[0].isoformat() / ".done").read_text())
    assert done["expiry"] == "2025-01-29"
    got = pd.read_csv(PA.ROOT / "options_next" / "SPY" / days[0].isoformat() / "bars.csv.gz")
    assert set(got["symbol"].str[3:9]) == {"250129"} and set(got["ts"].str[:10]) == {days[0].isoformat()}
    n = len(fake.calls)
    assert SPL.pull_options_next("SPY", days[0], days[0], band=0.01, today=date(2026, 10, 31), log=lambda *x: None)["skipped"] == 1
    assert len(fake.calls) == n


def test_runner_end_to_end_with_v2_options(tmp_path):
    days = SS.weekdays(date(2025, 1, 6), 12)
    root = tmp_path / "alpaca"
    SS.write_cache(root, "SPY", days, band=0.01, next_expiry=True,
                   trend={d: (35, 0.00012 if k % 2 else -0.00012) for k, d in enumerate(days)})
    spec = {"spec_id": "v2t", "period": "DEV", "symbols": ["SPY"], "description": "v2 options",
            "defaults": {"side": "both", "contract": "d40-55t45", "allout": "15:25", "time": "b", "stop": "premium", "tp": "none",
                         "tp_buffer": "$0.03", "rr_min": None, "trail": "none", "filters": []},
            "blocks": [{"name": "c", "grid": {"entry": ["orb15"], "contract": ["d40-55t45", "n1d40-55t45"], "risk": ["none", "bot"]}},
                       {"name": "m", "grid": {"entry": ["failed_high"], "side": ["P"]}}],
            "robustness": {"top_k": 1, "random_paths": 1, "fake_seeds": 1, "min_trades": 1}}
    p = tmp_path / "v2t.json"
    p.write_text(json.dumps(spec))
    res = runner.run_spec(p, days[0], days[-1], data_root=root, chains_dir=tmp_path / "nochains", out_dir=tmp_path / "out",
                          host_name="t", log=lambda *x: None, today=date(2026, 10, 31))
    rows = {r["run_id"]: r for r in pd.read_csv(res["csv"], keep_default_na=False).to_dict("records")}
    assert len(rows) == 5
    # grid order: contract x risk -> 001 0DTE, 002 0DTE + risk, 003 next expiry, 004 next expiry + risk
    assert rows["v2t-003"]["contract_rule"].startswith("n1d40-55t45") and rows["v2t-002"]["filters"] == "risk:bot"
    n0, n1 = rows["v2t-001"]["trades"], rows["v2t-003"]["trades"]
    assert n0 > 0 and n1 > 0                                    # both expiries traded on the same signals
    assert rows["v2t-002"]["trades"] <= n0 and rows["v2t-004"]["trades"] <= n1
    with pytest.raises(ValueError):
        runner.validate(engine.expand({"spec_id": "bad", "blocks": [{"name": "x", "grid": {"entry": ["failed_break"], "risk": ["max"]}}]}))


def test_time_entries_and_day_filters():
    ctx = _ctx_from({0: 500.0, 50: 500.6})                     # Wednesday 2025-03-12, flat prior days at 500
    s = entries.signals(ctx, "time_1030")
    assert [(x.side, x.idx, x.invalid) for x in s] == [("C", 59, None), ("P", 59, None)]
    assert [x.idx for x in entries.signals(ctx, "time_1100", "P")] == [89]
    g = _with_future_changed(ctx, 59, seed=1)
    assert [(x.side, x.idx, x.price) for x in entries.signals(g, "time_1030")] == [(x.side, x.idx, x.price) for x in s]
    r = lambda fs: {"filters": tuple(fs)}
    sig = s[1]
    assert engine._filters_ok(r(["day_up", "wed_fri"]), ctx, sig, 0) is None
    assert engine._filters_ok(r(["day_down"]), ctx, sig, 0).startswith("day_down")
    assert engine._filters_ok(r(["skip_opex"]), ctx, sig, 0) is None
    fri, _ = SS.make_ctx(date(2025, 3, 21), {0: 500.0}, {0: 1.0}, prior_days=12)       # third Friday
    assert engine._filters_ok(r(["skip_opex"]), fri, sig, 0).startswith("monthly expiration")
    mon, _ = SS.make_ctx(date(2025, 3, 10), {0: 500.0}, {0: 1.0}, prior_days=12)
    assert engine._filters_ok(r(["wed_fri"]), mon, sig, 0).startswith("wed_fri")


def test_far_otm_contract_rules(tmp_path):
    import pull_alpaca as PA
    days = SS.weekdays(date(2025, 3, 10), 3)
    st = SS.stock_day(days[-1], 500.0, seed=4)
    s = Series("SPY", st)
    PA._write_gz(tmp_path / "options" / "SPY" / days[-1].isoformat() / "bars.csv.gz", SS.option_bars(days[-1], st, "SPY", band=0.03))
    ctx = DayContext(s, days[-1], read_option_day("SPY", days[-1], tmp_path), SS.ConstSpread(), early_close=False)
    for rule, lo, hi in (("d03-12t07", 0.03, 0.12), ("d06-15t10", 0.06, 0.15)):
        for side in ("C", "P"):
            tape, info = contracts.pick(ctx, side, 59, rule)
            assert tape is not None and lo <= abs(info["delta"]) <= hi, (rule, side, info)
