"""v3.3: the stocks setups-board paper ledger, Chart's free X research list, sentiment pass-through, earnings
results and call notes. Offline."""
import json
import time

import pandas as pd
import pytest

import core
import engine
import marketdata
import scanner
import scanner_setups as SS
import store
import test_v31 as V


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    engine._cache.clear()
    clock, f, prov = V._scanner_world(monkeypatch)
    monkeypatch.setattr(SS, "tickers", lambda: ["NVDA", "AMD", "AAPL", "CHEAP", "TSLA"])
    f.m1_ext = lambda t, day, now: f.m1_today(t, day)
    scanner.prepare(clock().date())
    SS._state.update(day=None, rows={}, bars={}, quotes={}, quotes_at=None, last_step=None, budget=0.0)
    yield clock, f, prov
    scanner.use(None)
    marketdata.use(None)
    SS._state.update(day=None, rows={}, bars={}, quotes={}, quotes_at=None, last_step=None, budget=0.0)


def _board_at(clock, hh, mm):
    clock.t = V.DAY.replace(hour=hh, minute=mm, second=5)
    SS._state["last_step"] = time.time() - 600
    SS.step(clock())


def test_board_ledger_trades_stock_setups_through_the_gate_and_records_every_decision(world):
    import autopilot
    import catalysts
    clock, f, prov = world
    _board_at(clock, 10, 10)
    q = [r for r in SS.board()["rows"] if r["qualifies"] and r["ticker"] not in core.policy()["instruments"]]
    assert q, "the fixture should produce at least one qualifying stock setup"
    r0 = q[0]
    side = "C" if r0["direction"] == "long" else "P"
    sym = f"{r0['ticker']}261106{side}{int(round(r0['price'])) * 1000:08d}"
    f.chains[(r0["ticker"], side)] = [{"symbol": sym, "exp": "2026-11-06", "strike": float(round(r0["price"])), "bid": 2.00, "ask": 2.05,
                                       "delta": 0.58 if side == "C" else -0.58, "theta": -0.10, "iv": 0.4, "oi": 3000, "volume": 900, "ts": None}]
    prov.q[sym] = (2.00, 2.05)
    catalysts.ingest([{"tickers": [r0["ticker"]], "headline": f"{r0['ticker']} wins a large contract", "sources": [{"url": "https://www.reuters.com/x"}],
                       "sentiment": {"trader": {"lean": "bullish", "bull": ["contract size"], "bear": [], "sample": 25}}}], "Chart X scan")
    autopilot.board(clock())
    dec = store.q("SELECT ticker, decision, reasons, plan FROM candidates WHERE portfolio='board'")
    assert dec and all(d["decision"] in ("ORDER", "SKIP", "SKIP-GATE", "BLOCKED-LIMIT") for d in dec)
    assert all(json.loads(d["reasons"]) or d["decision"] == "ORDER" for d in dec)              # every skip says why
    pos = store.positions(ledger="board", status="OPEN")
    for p in pos:
        assert p["plan"]["gate"]["state"] == "ENTRY CONDITIONS MET" and p["qty_init"] == 1
        assert "x_read" in p["plan"] and p["plan"]["row"]["setup"]                             # recorded, never a trigger
    n = len(store.q("SELECT * FROM candidates WHERE portfolio='board'"))
    autopilot.board(clock())                                                                     # same minute again: no duplicates
    assert len(store.positions(ledger="board")) == len(pos)
    assert len(store.q("SELECT * FROM candidates WHERE portfolio='board'")) <= n + len(q)
    store.kv_set("paper_pause", {"at": "x", "by": "Nick"})
    assert autopilot.board(clock()) == []                                                        # emergency pause holds


def test_board_never_trades_spy_qqq_or_outside_its_window(world):
    import autopilot
    clock, f, prov = world
    _board_at(clock, 9, 50)
    assert autopilot.board(clock()) == []                                                        # before 10:00
    assert not store.q("SELECT * FROM candidates WHERE portfolio='board' AND ticker IN ('SPY','QQQ')")


def test_x_targets_put_earnings_first_and_explain_each(world, monkeypatch):
    import catalysts
    import earnings
    clock, f, prov = world
    _board_at(clock, 10, 10)
    monkeypatch.setattr(earnings, "cached_calendar", lambda days=14: [{"ticker": "AMD", "date": "2026-10-28", "timing": "after close"},
                                                                     {"ticker": "AAPL", "date": "2026-10-30", "timing": "after close"}])
    monkeypatch.setattr(earnings, "phase", lambda r, now=None: "RELEASE" if r["ticker"] == "AMD" else "PRE")
    d = catalysts.x_targets(clock())
    t = [x["ticker"] for x in d["targets"]]
    assert t[0] == "AMD" and t[1] == "AAPL" and "NVDA" in t
    assert all(x["why"] and x["focus"] for x in d["targets"]) and len(t) == len(set(t)) <= 12


def test_x_scan_sentiment_is_kept_separate_labeled_and_sampled(world):
    import catalysts
    clock, f, prov = world
    catalysts.ingest([{"tickers": ["NVDA"], "headline": "NVIDIA beats on data center revenue, guides above consensus",
                       "sources": [{"url": "https://x.com/someone/status/1"}, {"url": "https://nvidianews.nvidia.com/news/q3"}],
                       "sentiment": {"trader": {"lean": "bullish", "bull": ["guide above"], "bear": ["priced in"], "sample": 40},
                                     "consumer": {"lean": "neutral", "sample": 5}, "fundamentals": {"lean": "positive"}},
                       "attention": {"window": "last 2 h", "posts_sampled": 40, "unique_authors": 2, "top_author_share": 0.6}}], "Chart X scan")
    c = catalysts.feed("NVDA")[0]
    assert set(c["sentiment"]) == {"trader", "consumer", "fundamentals"} and c["sentiment"]["trader"]["lean"] == "bullish"
    assert c["attention"]["concentrated"] is True and "not a full count" in c["attention"]["note"]
    catalysts.ingest([{"tickers": ["AMD"], "headline": "AMD said to be in talks to buy a startup",
                       "sources": [{"url": "https://x.com/rumor/status/2"}]}], "Chart X scan")
    r = catalysts.feed("AMD")[0]
    assert r["label"] == "unverified" and not catalysts.entry_eligible(r)                       # posts only: watch, never an entry


def test_earnings_results_and_call_notes_need_sources(world):
    import earnings
    rec = earnings.record_results("NVDA", "2026-10-28", {"revenue": {"reported": 35.1, "expected": 33.2, "basis": "GAAP"},
                                                        "eps": {"reported": 0.81, "basis": "adjusted"}},
                                  "https://nvidianews.nvidia.com/news/q3", "LSEG via Reuters", "2026-10-28T16:00:00-04:00")
    m = rec["results"]["metrics"]
    assert m["revenue"]["surprise_pct"] == pytest.approx(5.72, abs=0.01) and m["eps"]["surprise_pct"] is None
    bad = earnings.record_call("NVDA", "2026-10-28", [{"text": "Demand exceeds supply"}], None)
    assert "error" in bad
    ok = earnings.record_call("NVDA", "2026-10-28", [{"text": "Demand exceeds supply into next year", "speaker": "CFO", "time": "17:22 ET"}],
                              "https://investor.nvidia.com/events")
    assert ok["call"][0]["statements"][0]["speaker"] == "CFO"
