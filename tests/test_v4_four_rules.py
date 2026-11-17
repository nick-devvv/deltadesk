"""2026-11-17: only the 4 rules (+ the reference noise band) trade, the 4 Rules tab, noise band phone alerts, and
expired options that were stuck OPEN become VOID. Runs with the production config/v4.json (nothing lifted)."""
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import alerts  # noqa: E402
import band_alerts  # noqa: E402
import core  # noqa: E402
import expiry_void  # noqa: E402
import fakes  # noqa: E402
import four_rules  # noqa: E402
import retire  # noqa: E402
import store  # noqa: E402
import v4report  # noqa: E402
import v4store as S  # noqa: E402

ET = core.ET
FOUR = ["nbs_spy_ls", "etf10_rsi2", "pead_t21_tp", "core_sso"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    clock = fakes.Clock(datetime(2026, 11, 17, 10, 40, tzinfo=ET))
    monkeypatch.setattr(core, "now_et", clock)
    pushed = []
    monkeypatch.setattr(alerts, "_push", lambda t, b, p: pushed.append((t, b, p)))
    yield {"clock": clock, "pushed": pushed}


def _shares(pid, led, day, px=100.0, book="trend"):
    return {"id": pid, "ledger": led, "book": book, "kind": "shares", "date": day, "ticker": "SPY", "direction": "long",
            "side": "long", "qty": 2, "entry_px": px, "entry_t": f"{day}T10:00:00-05:00", "legs": [], "plan": {}, "fees": 0.0,
            "risk_usd": 10.0}


def _noise(pid, day, contract="757P", sym="SPY   261105P00757000", status="OPEN", side="P", **kw):
    p = {"id": pid, "ledger": "noise", "date": day, "ticker": "SPY", "contract": contract, "symbol": sym, "side": side,
         "qty_init": 1, "qty_open": 1 if status == "OPEN" else 0, "fill": 3.93, "opened": f"{day}T10:31:00-05:00",
         "closed": None, "status": status, "setup_id": "", "grade": "", "setup": "noise", "realized": -0.02, "mfe": 0, "mae": 0,
         "policy_version": "test", "verified": "", "notes": "",
         "plan": {"stop_px": 743.44, "premium_stop": 3.18, "last_bid": 21.09}}
    p.update(kw)
    store.pos_insert(p)
    return p


# ------------------------------------------------------------------ which ledgers trade
def test_only_the_four_rules_and_the_reference_noise_band_trade():
    assert retire.cfg()["four_rules"] == FOUR
    for led in FOUR + ["noise", "real"]:
        assert not retire.is_retired(led), led
    for led in retire.STOPPED_2026_11_17:
        assert retire.is_retired(led), led
    assert retire.cfg()["four_rules_since"] == "2026-11-13"


def test_a_stopped_v4_ledger_opens_nothing_whatever_its_own_switch_says(env):
    assert retire.cfg()["sprint_paper"]["fb_or"] is True and retire.cfg()["pead_t21"] is True   # switches left as they were
    for led in ("fb_or", "pead_t21", "nbs_spy_long", "core_spy", "copilot", "noise_v2"):
        pid, why = S.open_position(_shares(f"{led}:1", led, "2026-11-17"))
        assert pid is None and why == retire.REASON, led
    assert S.open_position(_shares("nb:1", "nbs_spy_ls", "2026-11-17"))[0] == "nb:1"
    assert [p["id"] for p in S.positions()] == ["nb:1"]


@pytest.mark.parametrize("mod_name", ["core_spy", "core_trend"])
def test_a_stopped_core_sells_its_open_position_at_the_next_valid_quote(env, monkeypatch, mod_name):
    import importlib
    import v4exec
    mod = importlib.import_module(mod_name)
    retire._active_in_tests = frozenset({mod.LEDGER})            # let the old position exist, as it does on the desk
    S.open_position(_shares(f"{mod.LEDGER}:1", mod.LEDGER, "2026-11-12", book=mod.BOOK))
    retire._active_in_tests = frozenset()
    calls = []
    monkeypatch.setattr(v4exec, "close_now", lambda p, reason, quotes=None: calls.append((p["id"], reason)))
    monkeypatch.setattr(mod, "fetch", lambda: type("F", (), {"ready": lambda self: True})())
    monkeypatch.setattr(mod, "start_day", lambda: None)
    mod.step(datetime(2026, 11, 17, 9, 45, tzinfo=ET))
    assert calls == [(f"{mod.LEDGER}:1", mod.STOPPED)]
    assert "stopped 2026-11-17" in mod._state["status"]


# ------------------------------------------------------------------ expired contracts: VOID, not OPEN forever
def _daily(close):
    return pd.DataFrame({"Open": [close], "High": [close], "Low": [close], "Close": [close], "Volume": [1]},
                        index=pd.DatetimeIndex([pd.Timestamp("2026-11-05")]))


def test_an_expired_option_still_open_becomes_void_and_is_never_counted(env):
    p = _noise("nz:1", "2026-11-05")
    store.kv_set("pending_exit:nz:1", {"since": "2026-11-06T10:30:05-05:00", "reason": "NOISE STOP"})
    assert expiry_void.expiry(p) == "2026-11-05"
    assert expiry_void.void_if_expired(store.positions(status="OPEN")[0], "2026-11-17", _daily(752.0))
    v = store.positions(ledger="noise")[0]
    assert v["status"] == "VOID" and v["qty_open"] == 0 and v["closed"]
    assert v["plan"]["void"] == {"expiry": "2026-11-05", "value_modeled": 5.0, "underlying_close": 752.0,
                                 "version": expiry_void.VERSION}
    assert "MODELED" in v["plan"]["exit_reason"] and "excluded from results" in v["plan"]["exit_reason"]
    assert store.kv_get("pending_exit:nz:1") is None
    assert v4report._legacy_trades("noise", "2026-11-01") == []                     # no trade, no P/L
    assert store.positions(status="OPEN") == []
    assert store.q("SELECT text FROM events WHERE text LIKE '%VOID%'")
    stale = dict(p, status="OPEN", qty_open=1)                                     # a stale copy can't reopen it
    store.pos_save(stale)
    assert store.positions(ledger="noise")[0]["status"] == "VOID"
    assert expiry_void.void_if_expired(store.positions(ledger="noise")[0], "2026-11-17") is False   # once only


def test_void_without_a_close_price_and_unexpired_contracts_untouched(env):
    _noise("nz:2", "2026-11-05")
    _noise("nz:3", "2026-11-17", contract="680C", sym="SPY   261117C00680000", side="C")      # expires today: still live
    assert expiry_void.sweep("2026-11-17") == ["nz:2"]
    v = {p["id"]: p for p in store.positions(ledger="noise")}
    assert v["nz:2"]["status"] == "VOID" and v["nz:2"]["plan"]["void"]["value_modeled"] is None
    assert v["nz:3"]["status"] == "OPEN"
    assert expiry_void.expiry({"symbol": "SPY", "plan": {}}) is None                         # shares: never voided


def test_call_value_at_expiry_is_intrinsic():
    p = {"ticker": "QQQ", "symbol": "QQQ   261105C00660000"}
    assert expiry_void.expiry_value(p, "2026-11-05", _daily(671.4)) == (11.4, 671.4)
    assert expiry_void.expiry_value(p, "2026-11-05", _daily(650.0)) == (0.0, 650.0)
    assert expiry_void.expiry_value(p, "2026-11-06", _daily(650.0)) == (None, None)


# ------------------------------------------------------------------ phone alerts: the noise band only
def test_noise_band_entry_and_exit_reach_the_phone_once(env):
    assert alerts.phone_kinds() == ("band", "mytrades")
    _noise("nz:4", "2026-11-17", contract="680C", sym="SPY   261117C00680000", side="C",
           plan={"stop_px": 676.2, "premium_stop": 2.0})
    assert band_alerts.push() == 1
    t, b, pr = env["pushed"][-1]
    assert t == "Noise band: bought SPY 680C x1 (PAPER)" and pr == "high"
    assert "$3.93 at 10:31 ET" in b and "SPY back below 676.20" in b and "$2.00" in b and "T42" in b
    assert band_alerts.push() == 0                                                   # never twice
    p = store.positions(ledger="noise")[0]
    store.x("UPDATE positions SET status='CLOSED', qty_open=0, realized=?, closed=? WHERE id=?",
            (151.02, "2026-11-17T11:02:00-05:00", "nz:4"))
    store.x("INSERT INTO orders(client_id,position_id,ts,side,qty,status,broker_id,filled_qty,filled_price,reason) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)", ("nz:4-S0", "nz:4", "2026-11-17T11:02:00-05:00", "sell", 1, "FILLED", "sim", 1, 5.45, "x"))
    assert band_alerts.push() == 1
    t, b, _ = env["pushed"][-1]
    assert t == "Noise band: sold SPY 680C +$151.02 (PAPER)" and "Paper exit $5.45 at 11:02 ET" in b and "+151.02" in b
    assert band_alerts.push() == 0 and p["ledger"] == "noise"


def test_old_void_and_other_ledgers_never_alert(env):
    _noise("nz:5", "2026-11-14", contract="680C", sym="SPY   261114C00680000", side="C")       # an earlier day
    _noise("nz:6", "2026-11-17", status="VOID")
    store.pos_insert({"id": "old:1", "ledger": "old", "date": "2026-11-17", "ticker": "SPY", "contract": "690C",
                      "symbol": "SPY   261117C00690000", "side": "C", "qty_init": 1, "qty_open": 1, "fill": 1.0,
                      "opened": "2026-11-17T10:00:00-05:00", "status": "OPEN", "plan": {}})
    assert band_alerts.push() == 0 and env["pushed"] == []
    assert alerts.alert("copilot", "COPILOT SPY LONG", "body", "c-1") and env["pushed"] == []   # desk feed only now


# ------------------------------------------------------------------ the 4 Rules tab
def test_four_rules_view_counts_forward_paper_trades_from_the_start_date(env):
    S.open_position(_shares("nb:old", "nbs_spy_ls", "2026-11-12"))                   # before Nov 13: not counted
    S.close_position("nb:old", 101.0, "flat")
    S.open_position(_shares("nb:a", "nbs_spy_ls", "2026-11-13"))
    S.close_position("nb:a", 103.0, "flat")
    S.open_position(_shares("nb:b", "nbs_spy_ls", "2026-11-14"))
    S.close_position("nb:b", 99.0, "flat")
    rec = _shares("sso:1", "core_sso", "2026-11-13", book="score")
    rec["plan"] = {"mtm": 12.5}
    S.open_position(rec)
    _noise("nz:7", "2026-11-05", status="VOID", plan={"void": {"expiry": "2026-11-05", "value_modeled": 5.0}})
    d = four_rules.view()
    assert d["since"] == "2026-11-13" and d["needed"] == 40
    assert [r["ledger"] for r in d["rules"]] == FOUR and [r["n"] for r in d["rules"]] == [1, 2, 3, 4]
    nb = d["rules"][0]
    assert nb["trades"] == 2 and nb["net"] == 4.0 and nb["win_rate"] == 50.0 and nb["curve"] == [6.0, 4.0]
    assert nb["trading"] and nb["label"].startswith("PAPER")
    assert nb["backtest"]["line"].startswith("+2.18 bp a day") and "out-of-sample" in nb["backtest"]["label"]
    sso = d["rules"][3]
    assert sso["trades"] == 0 and sso["open_pl"] == 12.5 and sso["open"][0]["ticker"] == "SPY"
    assert "22.9% a year" in sso["backtest"]["line"]
    assert d["rules"][1]["backtest"]["line"].startswith("270 trades, 68% won")
    assert d["rules"][2]["backtest"]["line"].startswith("852 trades, 55% won, +1.21%")
    assert d["total_net"] == 4.0 and d["total_trades"] == 2
    nz = d["noise"]
    assert nz["trades"] == 0 and nz["void"][0]["value_modeled"] == 5.0 and "T42: FAIL" in nz["backtest"]["label"]
    assert "PAPER" in d["note"]


def test_rules_endpoint_is_wired():
    import v4api
    assert "/api/v4/rules" in v4api.__doc__
    assert '"/api/v4/rules"' in (ROOT / "v4api.py").read_text()
    html = (ROOT / "index.html").read_text()
    assert 'api("api/v4/rules")' in html and 'row("band", "Noise band trades"' in html
    assert json.loads((ROOT / "config/v4.json").read_text())["phone_alert_kinds"] == ["band", "mytrades"]
