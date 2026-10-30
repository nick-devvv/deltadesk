"""v3.3: the experiment register, the restriction/router layer, walk-forward splits, matched random controls and the
signal-study runner. Offline; no profitability is tested here, only that the machinery can't fool us."""
import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import core
import fakes
import matched_benchmarks as MB
import store
import strategy_registry as SR
import strategy_router as RT
import walk_forward as WF

ET = core.ET
DAY = datetime(2026, 10, 28, tzinfo=ET)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    reg = json.loads(SR.FILE.read_text())
    f = tmp_path / "specialists.json"
    f.write_text(json.dumps(reg))
    monkeypatch.setattr(SR, "FILE", f)
    SR._cache.update(mtime=None, data=None)
    clock = fakes.Clock(DAY.replace(hour=10, minute=30))
    monkeypatch.setattr(core, "now_et", clock)
    yield monkeypatch, f, clock
    SR._cache.update(mtime=None, data=None)


def test_nothing_is_qualified_and_failed_strategies_are_research_only(db):
    t = SR.evidence_table()
    assert t["qualified"] == [] and "No strategy is PAPER QUALIFIED" in t["qualified_note"]
    assert SR.status_for("ORB_BREAK", "SPY")["status"] == "RESEARCH ONLY" and not SR.status_for("ORB_BREAK", "SPY")["actionable"]
    assert SR.status_for("SOMETHING_NEW", "NVDA")["status"] == "DRAFT"
    ids = {e["id"]: e for e in t["experiments"]}
    # v3.4 (Nick, Oct 30): nothing is retired yet; the earlier failures run again in the lab and stay research only
    assert ids["MACD-VIDEO-5M-2R"]["status"] == "RESEARCH ONLY" and ids["FILTER-TREND-ADX25"]["status"] == "RESEARCH ONLY"
    assert not [e for e in t["experiments"] if e["status"] == "RETIRED"]
    assert all(e["evidence"] or e["status"] in ("DRAFT", "RESEARCH ONLY") for e in t["experiments"])


def test_a_registered_spec_cannot_be_edited_quietly(db):
    mp, f, clock = db
    SR.experiments()                                                      # first sight stores each spec's hash
    reg = json.loads(f.read_text())
    e = next(x for x in reg["experiments"] if x["id"] == "NOISE-BAND-V31")
    e["status"] = "PAPER QUALIFIED"
    e["spec"]["windows"] = [["10:00", "11:00"]]                           # edited after its results were known
    f.write_text(json.dumps(reg))
    SR._cache.update(mtime=None, data=None)
    got = SR.get("NOISE-BAND-V31")
    assert got["spec_changed"] and got["status"] == "RESEARCH ONLY" and "new id" in got["status_note"]
    assert SR.qualified() == []


def test_router_shadows_research_only_and_rejects_with_reasons(db):
    mp, f, clock = db
    r = RT.route({"ticker": "SPY", "side": "C", "family": "ORB_BREAK", "fresh": True, "bar_complete": True, "setup_id": "a"})
    assert r["decision"] == "SHADOW" and r["reasons"][0].startswith("research-only status") and r["record"]["id"] == "LEGACY-V3-ORB_BREAK"
    assert RT.route({"ticker": "SPY", "side": "C", "family": "ORB_BREAK", "fresh": True, "bar_complete": True, "setup_id": "a"})["decision"] == "DUPLICATE"
    clock.t = DAY.replace(hour=15, minute=40)
    r2 = RT.route({"ticker": "SPY", "side": "C", "family": "ORB_BREAK", "fresh": False, "bar_complete": False, "setup_id": "b"})
    assert r2["decision"] == "REJECT"
    txt = " | ".join(r2["reasons"])
    assert "outside setup window" in txt and "stale data" in txt and "incomplete bar" in txt and "session closed" in txt


def test_a_qualified_specialist_still_obeys_shared_limits_and_versions_are_recorded(db):
    mp, f, clock = db
    real = SR.status_for
    mp.setattr(SR, "status_for", lambda fam, t: dict(real(fam, t), status="PAPER QUALIFIED", actionable=True))
    r = RT.route({"ticker": "NVDA", "side": "C", "family": "ORB_BREAK", "fresh": True, "bar_complete": True, "setup_id": "q1"})
    assert r["decision"] == "ADMIT" and r["versions"]["gate"] and r["versions"]["router"] == RT.VERSION
    for i in range(2):                                                    # two open positions in two DIFFERENT specialists
        store.pos_save({"id": f"S{i}", "ledger": f"spec_x{i}", "date": "2026-10-28", "ticker": "AMD", "contract": "1C", "symbol": "S",
                        "side": "C", "qty_init": 1, "qty_open": 1, "fill": 1.0, "opened": "2026-10-28T10:00:00-04:00", "closed": None,
                        "status": "OPEN", "setup_id": "x", "grade": "B", "setup": "X", "plan": {}, "realized": 0, "mfe": 0, "mae": 0,
                        "policy_version": "t", "verified": "t", "notes": ""})
    r2 = RT.route({"ticker": "NVDA", "side": "P", "family": "ORB_BREAK", "fresh": True, "bar_complete": True, "setup_id": "q2"})
    assert r2["decision"] == "REJECT" and "max open positions across specialists" in r2["reasons"][0]


def test_walk_forward_never_lets_a_fold_see_its_future():
    rows = [{"session": f"2026-10-{d:02d}", "x": d} for d in range(1, 26) for _ in range(3)]
    seen = []

    def select(train):
        seen.append(max(r["session"] for r in train))
        return {"cut": max(r["x"] for r in train)}

    out = WF.run(rows, select, lambda te, p: {"min_test": min(r["session"] for r in te)}, test_size=5, min_train=10)
    assert out and all(f["params"]["cut"] < int(f["result"]["min_test"][-2:]) for f in out)
    assert all(s < f["result"]["min_test"] for s, f in zip(seen, out))
    rows2 = [dict(r, x=999) if r["session"] >= "2026-10-21" else r for r in rows]   # perturb only the last block
    out2 = WF.run(rows2, select, lambda te, p: {"min_test": min(r["session"] for r in te)}, test_size=5, min_train=10)
    assert out[0]["params"] == out2[0]["params"] and out[1]["params"] == out2[1]["params"]
    tr, va = WF.inner_split([f"d{i:02d}" for i in range(10)])
    assert max(tr) < min(va)


def _day(seed, start="2026-10-28 09:30"):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=390, freq="1min", tz=ET)
    c = 100 + np.cumsum(rng.normal(0, 0.05, 390))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"Open": o, "High": np.maximum(o, c) + 0.03, "Low": np.minimum(o, c) - 0.03, "Close": c, "Volume": 1e4}, index=idx)


def test_matched_controls_are_reproducible_admissible_and_paired_by_session():
    days = {("AAA", f"2026-10-{d}"): _day(d, f"2026-10-{d} 09:30") for d in (26, 27, 28)}
    sig = [{"session": "2026-10-26", "ticker": "AAA", "side": "C", "stop_dist": 0.2, "entry_i": 30}]
    a = MB.random_controls(sig, days, paths=20, seed=3)
    b = MB.random_controls(sig, days, paths=20, seed=3)
    assert a == b and len(a) == 20
    strat = [{"session": "2026-10-26", "r": 1.0}]
    d = MB.paired_difference(strat, a, ["2026-10-26", "2026-10-27", "2026-10-28"])
    assert d["n_sessions"] == 3                                              # zero-trade sessions stay in
    o = MB.stock_outcome(days[("AAA", "2026-10-26")], 30, "C", 0.2)
    assert o is None or o["why"] in ("target", "stop", "stop (ambiguous bar)", "stop gap", "time")
    assert MB.holm({"a": 0.01, "b": 0.04, "c": 0.03}) == {"a": 0.03, "c": 0.06, "b": 0.06}


def test_signal_study_is_causal_and_promotes_nothing_on_noise(tmp_path):
    import research
    m1s = {}
    for k, t in enumerate(("AAA", "BBB")):
        frames = []
        for i, d in enumerate(pd.bdate_range("2026-09-21", "2026-10-29")):
            f = _day(100 * k + i, f"{d.date()} 09:30")
            f["Volume"] = 5e4
            f[["Open", "High", "Low", "Close"]] += 20
            frames.append(f)
        m1s[t] = pd.concat(frames)
    res, rows, skipped = research.study(m1s, "2026-10-15", paths=5)
    assert rows and all(r["signal_at"] >= "09:44" and r["entry_at"] > r["signal_at"] for r in rows)
    assert all(v.startswith("NOT PROMOTED") for v in res["verdict"].values())   # random walk: no edge to find
    assert any(s["why"].startswith("insufficient warmup") for s in skipped)


def test_no_order_path_to_any_broker():
    import broker
    import schwab
    assert broker.submit("SPY", 1, "buy", "x")[0] is None
    with pytest.raises(RuntimeError):
        schwab._get("/trader/v1/accounts/123/orders", {})
    src = "".join(open(core.HERE / f).read() for f in ("paper.py", "engine.py", "autopilot.py", "strategy_router.py", "scanner.py"))
    assert "broker.submit" not in src and "/orders" not in src


def test_chart_context_carries_the_evidence_status(db):
    import commands
    b = commands._strategies_brief()
    assert b["qualified"] == [] and "No strategy is PAPER QUALIFIED" in b["note"]
    assert b["status"]["LEGACY-V3-VWAP_MACD"] == "RESEARCH ONLY" and b["status"]["MACD-VIDEO-5M-2R"] == "RESEARCH ONLY"
    assert len(json.dumps(b)) < 2500
