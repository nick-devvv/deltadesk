"""v4 stage 7: the v4 lineup report (/api/v4) and the Research page. Metrics, grouping, SPY vs QQQ, shares vs options
shadow, matched random entries, the retired archive, the `old` legacy forward test, HTTP, and the page script."""
import json
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import core  # noqa: E402
import fakes  # noqa: E402
import store  # noqa: E402
import v4report as RP  # noqa: E402
import v4store as S  # noqa: E402

ET = core.ET


def _local_open(req):
    """Loopback requests only, never through an HTTP proxy from the environment."""
    import urllib.request
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=10)
DAY = datetime(2026, 11, 4, tzinfo=ET)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    clock = fakes.Clock(DAY.replace(hour=16, minute=20))
    monkeypatch.setattr(core, "now_et", clock)
    yield clock


def _closed(i, ledger, pnl, ticker="SPY", day="2026-11-04", kind="option", book="index", parent=None, plan=None, side="C"):
    entry = 100.0
    rec = {"id": f"{ledger}:{i}", "ledger": ledger, "book": book, "kind": kind, "date": day, "ticker": ticker, "direction": "long",
           "side": "long" if kind == "shares" else side, "qty": 1, "entry_px": entry, "entry_t": f"{day}T10:{i % 60:02d}:00-05:00",
           "legs": [{"symbol": ticker, "action": "buy", "qty": 1}], "plan": plan or {}, "fees": 0.0, "risk_usd": 50.0, "parent_id": parent}
    S.open_position(rec)
    S.close_position(rec["id"], entry + (pnl / 100 if kind != "shares" else pnl), "test")
    return rec["id"]


def test_metrics_block():
    tr = [{"date": d, "realized": x} for d, x in [("a", 100), ("a", -50), ("b", -50), ("c", 200), ("d", -100), ("e", 50)]]
    m = RP.metrics(tr)
    assert m["trades"] == 6 and m["win_rate"] == 50.0 and m["avg_win"] == pytest.approx(116.67, abs=0.01)
    assert m["avg_loss"] == pytest.approx(-66.67, abs=0.01) and m["expectancy"] == pytest.approx(25.0)
    assert m["profit_factor"] == pytest.approx(350 / 200) and m["max_drawdown"] == pytest.approx(100.0)
    assert m["net"] == 150.0 and m["small_sample"] and m["ci95"][0] <= 25.0 <= m["ci95"][1]
    assert RP.metrics([]) == {"trades": 0, "small_sample": True}


def test_overview_groups_books_splits_tickers_and_pairs_shadows(env):
    _closed(1, "noise_v2", 120.0, "SPY")
    _closed(2, "noise_v2", -40.0, "QQQ")
    sh = _closed(3, "sip_orb5", 30.0, "NVDA", kind="shares", book="stocks", plan={"stop_bucket": "20-29c"})
    _closed(4, "sip_orb5", -100.0, "AMD", kind="shares", book="stocks", plan={"stop_bucket": "50-99c"})
    _closed(5, "sip_orb5_opt", 55.0, "NVDA", book="stocks", parent=sh)
    S.decide("sip_orb5_opt:x", "sip_orb5_opt", "AMD", "NO CONTRACT", ["no qualifying contract: delta outside 0.6-0.8 3"], {}, "entry")
    d = RP.overview("2026-11-02")
    books = {b["book"]: b for b in d["books"]}
    assert list(books) == ["index", "premium", "stocks", "catalyst"]
    idx = {l["ledger"]: l for l in books["index"]["ledgers"]}
    assert set(idx) == {"noise", "noise_v2", "noise_trend", "old"}
    assert idx["noise_v2"]["by_ticker"]["SPY"]["net"] == 120.0 and idx["noise_v2"]["by_ticker"]["QQQ"]["net"] == -40.0
    assert idx["old"]["legacy"] == "legacy forward test (not from a published source)" and "legacy forward test" in idx["old"]["label"]
    st = {l["ledger"]: l for l in books["stocks"]["ledgers"]}["sip_orb5"]
    assert st["trades"] == 2 and st["shadow"]["trades"] == 1 and st["shadow"]["same_entries"]["shares"]["trades"] == 1
    assert st["shadow"]["same_entries"]["shares"]["net"] == 30.0 and st["shadow"]["same_entries"]["options"]["net"] == 55.0
    assert st["shadow"]["no_contract"] and set(st["by_stop_bucket"]) == {"20-29c", "50-99c"}
    for k in ("trades", "win_rate", "avg_win", "avg_loss", "expectancy", "profit_factor", "max_drawdown"):
        assert k in idx["noise_v2"]
    assert d["risk"]["limits"]["desk_max_open"] > 0


def test_legacy_noise_and_old_rows_read_the_v3_table(env):
    for i, (led, pnl) in enumerate((("noise", 50.0), ("old", -20.0), ("old", 10.0))):
        store.pos_save({"id": f"{led}:{i}", "ledger": led, "date": "2026-11-04", "ticker": "SPY", "contract": "600C", "symbol": "S",
                        "side": "C", "qty_init": 1, "qty_open": 0, "fill": 2.0, "opened": f"2026-11-04T10:0{i}:00-05:00",
                        "closed": f"2026-11-04T11:0{i}:00-05:00", "status": "CLOSED", "setup_id": str(i), "grade": "B", "setup": "X",
                        "plan": {}, "realized": pnl, "mfe": 0, "mae": 0, "policy_version": "v", "verified": "", "notes": ""})
    idx = {l["ledger"]: l for l in RP.overview("2026-11-02")["books"][0]["ledgers"]}
    assert idx["noise"]["net"] == 50.0 and idx["old"]["trades"] == 2 and idx["old"]["net"] == -10.0


def test_retired_archive_lists_retired_history(env):
    store.pos_save({"id": "research:1", "ledger": "research", "date": "2026-10-29", "ticker": "SPY", "contract": "600C", "symbol": "S",
                    "side": "C", "qty_init": 1, "qty_open": 0, "fill": 2.0, "opened": "2026-10-29T10:00:00-04:00",
                    "closed": "2026-10-29T10:30:00-04:00", "status": "CLOSED", "setup_id": "1", "grade": "B", "setup": "X",
                    "plan": {}, "realized": -12.0, "mfe": 0, "mae": 0, "policy_version": "v", "verified": "", "notes": ""})
    ret = RP.overview()["retired"]
    assert [r["ledger"] for r in ret["ledgers"]] == ["research"] and ret["ledgers"][0]["retired"] and ret["ledgers"][0]["net"] == -12.0
    assert "old" not in ret["list"]["ledgers"]


def test_matched_random_scores_use_one_yardstick_and_never_touch_pl(env):
    idx = pd.date_range(DAY.replace(hour=9, minute=30), DAY.replace(hour=15, minute=59), freq="1min")
    c = 50 + np.cumsum(np.r_[0, np.full(len(idx) - 1, 0.01)])
    m1 = pd.DataFrame({"Open": c, "High": c + 0.02, "Low": c - 0.02, "Close": c, "Volume": 1e4}, index=idx)
    pid = _closed(1, "sip_orb5", 40.0, "UPP", kind="shares", book="stocks", plan={"stop_dist": 0.15, "stop": 49.9})
    before = S.get(pid)
    assert RP.score_controls(DAY.date(), bars_fn=lambda t, d: m1) == 1
    after = S.get(pid)
    assert after["realized"] == before["realized"] and after["exit_px"] == before["exit_px"]
    assert after["plan"]["yard_r"] is not None and after["plan"]["ctl_n"] == 50
    assert RP.score_controls(DAY.date(), bars_fn=lambda t, d: m1) == 0                   # once per trade
    row = [l for l in RP.overview()["books"][2]["ledgers"] if l["ledger"] == "sip_orb5"][0]
    assert row["random"]["n"] == 1 and row["random"]["edge_r"] == pytest.approx(after["plan"]["yard_r"] - after["plan"]["ctl_r"], abs=1e-3)
    assert not S.annotate(pid, realized=999)                                             # annotations can't touch P/L


def test_v4_api_over_http(env, monkeypatch):
    import server
    _closed(1, "noise_v2", 120.0, "SPY")
    S.open_position({"id": "orb_credit:o", "ledger": "orb_credit", "book": "premium", "kind": "spread", "date": "2026-11-04",
                     "ticker": "QQQ", "direction": "short", "side": "call credit", "qty": 1, "entry_px": 0.4, "entry_t": store.ts(),
                     "max_loss": 162.6, "legs": [{"symbol": "QQQ261104C00500000", "label": "500C", "action": "sell"},
                                                 {"symbol": "QQQ261104C00502000", "label": "502C", "action": "buy"}],
                     "plan": {"exit_rule": "15:25, no stop, no target", "mtm": 12.0}})
    monkeypatch.setattr(server, "DESK_TOKEN", "")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with _local_open(base + "/api/v4?since=2026-11-02") as r:
            d = json.loads(r.read())
        assert [b["book"] for b in d["books"]] == ["index", "premium", "stocks", "catalyst"] and "retired" in d
        with _local_open(base + "/api/v4/positions?status=OPEN") as r:
            ps = json.loads(r.read())
        assert len(ps) == 1 and ps[0]["desc"] == "-500C / +502C" and ps[0]["mtm"] == 12.0 and "max loss" in ps[0]["next"]
        with _local_open(base + "/api/v4/decisions?day=2026-11-04") as r:
            assert isinstance(json.loads(r.read()), list)
    finally:
        srv.shutdown()


def test_research_page_shows_the_v4_lineup_with_a_collapsed_archive():
    html = (ROOT / "index.html").read_text()
    assert 'id="v4Books"' in html and 'id="v4Archive"' in html and 'api/v4?since=' in html
    arch = re.search(r'<details class="more" id="v4Archive"[^>]*>', html).group(0)
    assert " open" not in arch                                                           # collapsed by default
    for h in ("Trades", "Won", "Avg win", "Avg loss", "Per trade", "Profit factor", "Max DD", "vs random"):
        assert f">{h}</th>" in html
    assert "options shadow" in html and "api/v4/kill" in html


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_page_script_parses():
    html = (ROOT / "index.html").read_text()
    scripts = re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html, re.S)
    js = "\n".join(scripts)
    p = Path(ROOT / "tests" / "_v4_page_check.js")
    try:
        p.write_text(js)
        res = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True, timeout=60)
    finally:
        p.unlink(missing_ok=True)
    assert res.returncode == 0, res.stderr[:2000]
