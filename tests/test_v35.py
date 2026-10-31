"""v3.5 tests: atomic paper lifecycle (C6), and the integrity fixes that follow it. No network, no AI."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import core  # noqa: E402
import engine  # noqa: E402
import fakes  # noqa: E402
import marketdata  # noqa: E402
import paper  # noqa: E402
import store  # noqa: E402

ET = core.ET
DAY = datetime(2026, 10, 28, tzinfo=ET)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    engine._cache.clear()
    monkeypatch.setattr(core, "EVENTS_FILE", tmp_path / "events.json")
    yield monkeypatch
    marketdata.use(None)


def _plan(side="C"):
    return {"symbol": f"SPY261028{side}00600000", "label": f"600{side}", "premium_stop": 1.64, "stop_px": 599.0, "t1": "PDH",
            "t1_level": 603.1, "t1_px": 603.0, "be_trigger": 2.27, "breakeven_net": 2.07, "family": "TEST",
            "premium_limit": 3.0, "flat_by": "23:59"}


def _world(env):
    clock, fk = fakes.install(env, lambda ts: 600.0, DAY, s0=600.0)
    clock.t = DAY.replace(hour=10, minute=0)
    engine._cache.clear()
    return clock, fk


def _counts(pid):
    return {"pos": len(store.q("SELECT id FROM positions WHERE id=?", (pid,))),
            "orders": len(store.q("SELECT client_id FROM orders WHERE position_id=?", (pid,))),
            "events": len(store.q("SELECT seq FROM events WHERE position_id=?", (pid,))) if _has_col("events", "position_id") else None,
            "filled": len(store.q("SELECT idea FROM ideas WHERE position_id=? AND status='FILLED'", (pid,)))}


def _has_col(table, col):
    return any(r["name"] == col for r in store.q(f"PRAGMA table_info({table})"))


# ================================================================ C6 atomic lifecycle
def test_tx_rolls_back_everything_on_a_crash(env):
    store.conn()
    with pytest.raises(RuntimeError):
        with store.tx():
            store.x("INSERT INTO kv(k, v) VALUES('a', '1')")
            with store.tx():                                               # nested joins the outer transaction
                store.x("INSERT INTO kv(k, v) VALUES('b', '2')")
            raise RuntimeError("crash between lifecycle steps")
    assert not store.q("SELECT k FROM kv WHERE k IN ('a','b')")
    with store.tx():
        store.x("INSERT INTO kv(k, v) VALUES('a', '1')")
    assert store.q("SELECT v FROM kv WHERE k='a'")[0]["v"] == "1"


def test_pos_insert_never_overwrites(env):
    store.conn()
    p = {"id": "paper:X", "ledger": "paper", "date": "2026-10-28", "ticker": "SPY", "contract": "600C", "symbol": "S",
         "side": "C", "qty_init": 1, "qty_open": 1, "fill": 2.0, "opened": "t", "closed": None, "status": "OPEN",
         "setup_id": "X", "grade": "A", "setup": "T", "plan": {}, "realized": 0, "mfe": 0, "mae": 0,
         "policy_version": "v", "verified": "", "notes": ""}
    store.pos_insert(p)
    with pytest.raises(Exception):
        store.pos_insert(dict(p, fill=9.0))
    assert store.pos_get("paper:X")["fill"] == 2.0


@pytest.mark.parametrize("crash_on", ["orders", "ideas", "event"])
def test_buy_crash_mid_lifecycle_then_retry_fills_exactly_once(env, crash_on):
    clock, fk = _world(env)
    paper.reserve_idea("paper", "I1", "SPY", "C")
    real_x, real_event = store.x, store.event
    state = {"armed": True}

    def x(sql, args=()):
        if state["armed"] and crash_on == "orders" and sql.lstrip().upper().startswith("INSERT INTO ORDERS"):
            state["armed"] = False
            raise RuntimeError("injected crash after the position insert")
        if state["armed"] and crash_on == "ideas" and "UPDATE ideas SET status='FILLED'" in sql:
            state["armed"] = False
            raise RuntimeError("injected crash after the order insert")
        return real_x(sql, args)

    def event(*a, **k):
        if state["armed"] and crash_on == "event":
            state["armed"] = False
            raise RuntimeError("injected crash before the event")
        return real_event(*a, **k)

    env.setattr(store, "x", x)
    env.setattr(store, "event", event)
    with pytest.raises(RuntimeError):
        paper.buy("paper", "I1", "SPY", "C", _plan(), 2, clock().isoformat())
    assert not store.q("SELECT id FROM positions")                             # nothing half-written
    assert not store.q("SELECT client_id FROM orders")
    assert store.q("SELECT status FROM ideas WHERE idea='I1'")[0]["status"] != "FILLED"
    pid, why = paper.buy("paper", "I1", "SPY", "C", _plan(), 2, clock().isoformat())     # the retry
    assert pid == "paper:I1", why
    pid2, why2 = paper.buy("paper", "I1", "SPY", "C", _plan(), 2, clock().isoformat())   # a duplicate retry
    assert pid2 is None and "never fills twice" in why2
    c = _counts(pid)
    assert c["pos"] == 1 and c["orders"] == 1 and c["filled"] == 1
    p = store.pos_get(pid)
    fee = p["plan"]["fees_side"]
    assert p["realized"] == round(-fee * 2, 2)                                   # the entry fee is counted once


def test_sell_crash_then_retry_exits_once_and_counts_fee_once(env):
    clock, fk = _world(env)
    paper.reserve_idea("paper", "I2", "SPY", "C")
    pid, why = paper.buy("paper", "I2", "SPY", "C", _plan(), 1, clock().isoformat())
    assert pid, why
    real_event = store.event
    state = {"armed": True}

    def event(kind, *a, **k):
        if state["armed"] and "exit" in kind:
            state["armed"] = False
            raise RuntimeError("injected crash after the exit order")
        return real_event(kind, *a, **k)

    env.setattr(store, "event", event)
    with pytest.raises(RuntimeError):
        paper.sell(store.pos_get(pid), 1, "test exit")
    p = store.pos_get(pid)
    assert p["status"] == "OPEN" and p["qty_open"] == 1                           # the exit rolled back whole
    assert len(store.q("SELECT client_id FROM orders WHERE position_id=? AND side='sell'", (pid,))) == 0
    stale = store.pos_get(pid)
    qty, px = paper.sell(stale, 1, "test exit")
    assert qty == 1
    again = paper.sell(stale, 1, "test exit")                                      # a retry with the stale copy
    assert again[0] == 0
    p = store.pos_get(pid)
    sells = store.q("SELECT client_id FROM orders WHERE position_id=? AND side='sell'", (pid,))
    assert p["status"] == "CLOSED" and p["qty_open"] == 0 and len(sells) == 1
    fee = p["plan"]["fees_side"]
    assert p["realized"] == round((px - p["fill"]) * 100 - 2 * fee, 2)            # one entry fee + one exit fee


def test_full_ledger_ids_are_unique_across_ledgers_with_the_same_prefix(env):
    clock, fk = _world(env)
    a, b = "lab_orb_break", "lab_vwap_macd"                                      # both used to be "LA-<idea>"
    for led in (a, b):
        paper.reserve_idea(led, "SAME", "SPY", "C")
    sig = (clock() - timedelta(seconds=5)).isoformat()                           # strict ledgers: decision latency
    pa, wa = paper.buy(a, "SAME", "SPY", "C", _plan(), 1, sig)
    pb, wb = paper.buy(b, "SAME", "SPY", "C", _plan(), 1, sig)
    assert pa and pb and pa != pb, (wa, wb)
    assert {store.pos_get(pa)["ledger"], store.pos_get(pb)["ledger"]} == {a, b}


def test_release_never_unfills_a_filled_idea(env):
    clock, fk = _world(env)
    paper.reserve_idea("paper", "I3", "SPY", "C")
    pid, _ = paper.buy("paper", "I3", "SPY", "C", _plan(), 1, clock().isoformat())
    paper.release_idea("paper", "I3", "late release")
    assert store.q("SELECT status FROM ideas WHERE idea='I3'")[0]["status"] == "FILLED"


def test_old_position_ids_still_load(env):
    store.conn()
    store.pos_save({"id": "PA-OLD", "ledger": "paper", "date": "2026-10-27", "ticker": "SPY", "contract": "600C", "symbol": "S",
                    "side": "C", "qty_init": 1, "qty_open": 0, "fill": 2.0, "opened": "t", "closed": "t", "status": "CLOSED",
                    "setup_id": "OLD", "grade": "A", "setup": "T", "plan": {"x": 1}, "realized": 5.0, "mfe": 0, "mae": 0,
                    "policy_version": "v", "verified": "", "notes": ""})
    assert store.pos_get("PA-OLD")["plan"] == {"x": 1}


def test_a_stale_copy_cannot_reopen_a_closed_trade(env):
    clock, fk = _world(env)
    paper.reserve_idea("paper", "I4", "SPY", "C")
    pid, _ = paper.buy("paper", "I4", "SPY", "C", _plan(), 1, clock().isoformat())
    stale = store.pos_get(pid)
    paper.sell(store.pos_get(pid), 1, "exit")
    stale["mfe"] = 12.5
    store.pos_save(stale)                                                       # e.g. a manager that loaded it earlier
    p = store.pos_get(pid)
    assert p["status"] == "CLOSED" and p["qty_open"] == 0 and p["mfe"] == 12.5


# ================================================================ C4 news as-of integrity
def _cat_env(env):
    import catalysts as C
    store.conn()
    env.setattr(C, "_price", lambda t: 100.0)
    env.setattr(core, "now_et", lambda: DAY.replace(hour=11))
    C._state.update(edgar_seen=set(), ciks=None, xai_calls=[], xai_cache={}, verify_calls=[])
    return C


def test_a_later_verification_never_leaks_into_an_earlier_signal(env):
    """The prompt's regression case: unverified at 10:00, signal at 10:05, verified source at 10:20."""
    import lab
    C = _cat_env(env)
    t0, sig, t2 = DAY.replace(hour=10), DAY.replace(hour=10, minute=5), DAY.replace(hour=10, minute=20)
    cid = C.ingest([{"tickers": ["AMD"], "headline": "AMD said to be in talks to buy chip startup Foo",
                     "sources": [{"url": "https://x.com/someone/status/1"}],
                     "sentiment": {"trader": {"lean": "bearish"}}}], "xAI search", t0)[0][0]
    C.ingest([{"tickers": ["AMD"], "headline": "AMD announces agreement to buy chip startup Foo",
               "sources": [{"url": "https://www.businesswire.com/news/amd-foo"}]}], "xAI search", t2)
    C.verify(cid, fetch=lambda u: "Advanced Micro Devices (NASDAQ: AMD) announces agreement to buy chip startup Foo",
             now=t2.replace(minute=21))
    assert C.feed("AMD")[0]["label"] == "confirmed" and C.feed("AMD")[0]["content_verified"]      # today's view moved on
    lab._state.update(cats=None, cats_at=0)
    cats = lab._xcats(DAY.replace(hour=11))                                                       # catch-up AFTER 10:20
    import pandas as pd
    c = lab.conditions("AMD", "C", {"hm": "10:05", "close": 160.0, "atr14": 3.0}, pd.Timestamp(sig), cats)
    assert c["x_id"] == cid and c["x_label"] == "unverified" and c["x_rev"] == 0 and c["x_verified"] is False
    assert c["x_lean"] == "X disagrees"                                                          # the 10:00 sentiment
    assert not C.entry_eligible(C.as_of(cid, sig)) and C.as_of(cid, sig)["label"] == "unverified"
    assert C.as_of(cid, t2)["label"] == "confirmed" and not C.as_of(cid, t2)["content_verified"]
    assert C.entry_eligible(C.as_of(cid, t2.replace(minute=22)))
    assert C.as_of(cid, t0.replace(minute=0, second=0) - __import__("datetime").timedelta(seconds=1)) is None
    late = C.known_at("AMD", sig)
    assert late["id"] == cid and late["_rev"] == 0


def test_catalyst_revisions_are_append_only(env):
    import sqlite3
    C = _cat_env(env)
    C.ingest([{"tickers": ["NVDA"], "headline": "NVIDIA wins a large contract with a utility",
               "sources": [{"url": "https://www.reuters.com/a"}]}], "xAI search", DAY.replace(hour=10))
    with pytest.raises(sqlite3.DatabaseError):
        store.x("UPDATE catalyst_revisions SET label='confirmed'")
    with pytest.raises(sqlite3.DatabaseError):
        store.x("DELETE FROM catalyst_revisions")
    assert len(store.q("SELECT rev FROM catalyst_revisions")) == 1


def test_content_check_needs_the_company_and_the_claim(env):
    C = _cat_env(env)
    ok, d = C.content_check("<p>Shares of a chip maker rose.</p>", ["AMD"], "AMD announces agreement to buy chip startup Foo")
    assert not ok
    ok, d = C.content_check("<script>AMD buy Foo</script><p>Weather today.</p>", ["AMD"], "AMD announces agreement to buy chip startup Foo")
    assert not ok                                                                   # script text is not article text
    ok, d = C.content_check("Ford recalls 100,000 trucks over a brake issue", ["F"], "Ford recalls 100,000 trucks over brake issue",
                            {"F": "FORD MOTOR CO"})
    assert ok and d["name_found"] == ["F"] and d["ticker_found"] == []            # 'F' alone never counts
    ok, d = C.content_check("F recalls trucks over brake issue", ["F"], "Ford recalls 100,000 trucks over brake issue")
    assert not ok
    ok, d = C.content_check("Ford Motor (NYSE: F) recalls 100,000 trucks over a brake issue", ["F"], "Ford recalls 100,000 trucks over brake issue")
    assert ok and d["ticker_found"] == ["F"]                                       # an exchange-qualified mention is unambiguous


def test_only_allowlisted_https_sources_are_fetched_and_failures_stay_observational(env):
    C = _cat_env(env)
    got = []
    cid = C.ingest([{"tickers": ["TSLA"], "headline": "Tesla wins large battery contract with a utility",
                     "sources": [{"url": "https://www.reuters.com/a"}, {"url": "https://randomblog.example/p"},
                                 {"url": "https://x.com/u/status/9"}]}], "xAI search", DAY.replace(hour=10))[0][0]

    def fetch(u):
        got.append(u)
        raise OSError("paywall")
    v = C.verify(cid, fetch=fetch, now=DAY.replace(hour=10, minute=1))
    assert got == ["https://www.reuters.com/a"] and v["status"] == "pending"            # one retry left
    v = C.verify(cid, fetch=fetch, now=DAY.replace(hour=10, minute=2))
    assert v["status"] == "failed" and len(got) == 2
    assert C.verify(cid, fetch=fetch, now=DAY.replace(hour=10, minute=3))["status"] == "failed" and len(got) == 2
    rec = C.feed("TSLA")[0]
    assert rec["label"] == "attributed" and not C.entry_eligible(rec) and "observational" in rec["eligibility"]
    h = C._NoOffsiteRedirect(("reuters.com",))
    with pytest.raises(Exception):
        h.redirect_request(None, None, 302, "Found", {}, "https://evil.example/x")


def test_edgar_items_are_desk_retrieved_and_eligible_at_once(env):
    C = _cat_env(env)
    r = C.ingest([{"tickers": ["NVDA"], "headline": "NVDA filed a 8-K: 2.02 Results of Operations",
                   "sources": [{"url": "https://www.sec.gov/Archives/edgar/data/1/x-index.htm"}]}], "SEC EDGAR", DAY.replace(hour=16),
                 retrieved_by_desk=True)
    rec = C.as_of(r[0][0], DAY.replace(hour=16))
    assert rec["content_verified"] and rec["sources"][0]["retrieval"] == "fetched_by_desk" and C.entry_eligible(rec)
    r2 = C.ingest([{"tickers": ["AAPL"], "headline": "Apple files an 8-K about a new buyback program",
                    "sources": [{"url": "https://www.sec.gov/Archives/edgar/data/2/y-index.htm"}]}], "Chart news routine", DAY.replace(hour=16))
    rec2 = C.as_of(r2[0][0], DAY.replace(hour=16))
    assert rec2["sources"][0]["retrieval"] == "supplied" and not C.entry_eligible(rec2)    # a pasted sec.gov link isn't proof


def test_pre_v35_catalysts_are_backfilled_as_reconstructed_revisions(env):
    C = _cat_env(env)
    store.x(C.SCHEMA)
    store.kv_set("catrev_backfilled", None)
    legacy = {"id": "N-OLD", "cluster": "N-OLD", "tickers": ["AMD"], "headline": "AMD to buy Foo", "category": "acquisition",
              "label": "attributed", "first_detected_at": "2026-10-28T10:00:00-04:00", "recycled": False,
              "sentiment": {"trader": {"lean": "bullish"}},
              "sources": [{"url": "https://x.com/a/status/1", "kind": "social", "retrieved_at": "2026-10-28T10:00:00-04:00"},
                          {"url": "https://www.reuters.com/x", "kind": "reporting", "retrieved_at": "2026-10-28T10:20:00-04:00"}],
              "history": [{"t": "2026-10-28T10:20:00-04:00", "what": "label unverified -> attributed"}]}
    store.x("INSERT INTO catalysts(id,cluster,tickers,headline,category,label,first_detected,updated,data) VALUES(?,?,?,?,?,?,?,?,?)",
            ("N-OLD", "N-OLD", "AMD", legacy["headline"], "acquisition", "attributed", legacy["first_detected_at"], "t", json.dumps(legacy)))
    C._schema()
    early = C.as_of("N-OLD", DAY.replace(hour=10, minute=5))
    assert early["label"] == "unverified" and early["_reconstructed"] and "sentiment" not in early
    assert C.as_of("N-OLD", DAY.replace(hour=10, minute=25))["label"] == "attributed"


# ================================================================ C3 contract lab timing and comparability
def _cl_env(env, tmp_path=None):
    import contract_lab as CL
    import lab
    store.conn()
    lab._schema()
    CL._schema()
    CL._state.update(tracked=None, last_sample={}, recent={}, rejects={})
    return CL, lab


def _cl_chain(now, ts=None, same_strike=False):
    rows = []
    spot = 140.0
    for dte in (0, 1, 3, 6):
        exp = (now.date() + __import__("datetime").timedelta(days=dte)).isoformat()
        for k in range(-6, 7):
            strike = spot + k
            d = 0.40 if same_strike else max(0.05, min(0.95, 0.5 - k * 0.07))
            if same_strike and k != 0:
                d = 0.05
            mid = 1.0 + 0.2 * dte + max(0, -k) * 0.5
            rows.append({"symbol": f"NVDA{exp.replace('-', '')[2:]}C{int(strike * 1000):08d}", "exp": exp, "strike": strike,
                         "bid": round(mid - 0.02, 2), "ask": round(mid + 0.02, 2), "delta": d, "ts": (ts or now).isoformat()})
    return rows


class _F:
    def __init__(self, rows):
        self.rows = rows

    def chain(self, *a):
        return self.rows, None


def _tape(i, day, be, exit_at=None, status="OPEN"):
    store.x("INSERT INTO lab_tape(id, day, ticker, family, setup, side, signal_bar, bar_end, observed_at, live, level, invalidation, "
            "use_level, price, atr, conditions, status, r, exit_at, version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (i, day, "NVDA", "board_orb_break", "s", "C", be, be, be, 1, 1, 0.9, 1, 1, 1, "{}", status, 1.0, exit_at, "t"))


def test_future_dated_quotes_are_rejected_and_skew_is_recorded(env):
    CL, lab = _cl_env(env)
    now = DAY.replace(hour=10, minute=40)
    fut = CL.pick(_cl_chain(now, ts=now + timedelta(seconds=30)), "C", now.date(), now)
    assert all(r is None for _, _, r, _ in fut) and "future-dated" in fut[0][3]
    skew = CL.pick(_cl_chain(now, ts=now + timedelta(seconds=3)), "C", now.date(), now)
    got = [r for _, _, r, _ in skew if r]
    assert got and all(r["skew_s"] == -3.0 for r in got)                       # small clock skew: kept, recorded
    utc = CL.pick(_cl_chain(now, ts=now.astimezone(__import__("datetime").timezone.utc).replace(tzinfo=None)), "C", now.date(), now)
    assert all(r is None for _, _, r, _ in utc)                                  # a naive UTC time read as ET is 4 h stale, never fresh


def test_exit_needs_a_quote_inside_the_window_and_never_uses_an_earlier_one(env):
    CL, lab = _cl_env(env)
    q = [{"recv_t": "2026-10-28T10:50:00-04:00", "quote_t": "2026-10-28T10:50:00-04:00", "bid": 2.0, "ask": 2.1},
         {"recv_t": "2026-10-28T10:55:00-04:00", "quote_t": "2026-10-28T10:55:00-04:00", "bid": 2.5, "ask": 2.6}]
    x, gap = CL.exit_quote(q, "2026-10-28T10:51:00-04:00")
    assert x is None and gap == 240                                               # 4 min late: UNFILLED, gap kept
    x, gap = CL.exit_quote(q, "2026-10-28T10:54:00-04:00")
    assert x["bid"] == 2.5 and gap == 60
    stale = [dict(q[1], recv_t="2026-10-28T10:56:00-04:00")]                      # received 60 s after its quote time
    assert CL.exit_quote(stale, "2026-10-28T10:54:30-04:00")[0] is None
    assert CL.exit_quote(q, "2026-10-28T14:00:00Z")[0] is None                     # a UTC exit time is normalized (10:00 ET... before 10:50, gap > window)


def _follow(CL, now, sig_id="s1", bar_end=None, rows=None):
    sig = {"id": sig_id, "ticker": "NVDA", "side": "C", "family": "board_orb_break", "bar_end": (bar_end or now).isoformat()}
    return CL.start(sig, now, _F(rows or _cl_chain(now)))


def test_duplicate_contracts_are_marked_and_not_counted_twice_and_unfilled_rows_are_missing(env):
    import marketdata
    CL, lab = _cl_env(env)
    now = DAY.replace(hour=10, minute=40)
    _tape("s1", "2026-10-28", now.isoformat())
    assert _follow(CL, now, rows=_cl_chain(now, same_strike=True)) >= 3
    rows = store.q("SELECT * FROM lab_contracts WHERE tape_id='s1' AND symbol IS NOT NULL")
    by_sym = {}
    for r in rows:
        by_sym.setdefault((r["bucket"], r["symbol"]), []).append(r)
    dups = [r for r in rows if r["dup_of"]]
    assert dups and all(len(v) == 1 + sum(1 for x in v if x["dup_of"]) for v in by_sym.values())
    clk = {"t": now + timedelta(minutes=5)}
    env.setattr(marketdata, "option_quotes", lambda syms, max_age_s=5: ({s: {"bid": 1.5, "ask": 1.6, "executable": True,
                "quote_time": pd.Timestamp(clk["t"]), "recv": pd.Timestamp(clk["t"])} for s in syms}, None))
    CL.poll(clk["t"])
    store.x("UPDATE lab_tape SET status='DONE', exit_at=? WHERE id='s1'", ((now + timedelta(minutes=4, seconds=30)).isoformat(),))
    CL.resolve("2026-10-28")
    rep = CL.report()
    cells = {(r["bucket"], r["delta"]): r for r in rep["rows"]}
    dcell = next(r for r in rep["rows"] if r["duplicates"])
    assert dcell["n"] == 0 and dcell["duplicates"] == 1
    store.x("UPDATE lab_contracts SET status='TRACKED', resolved_at=NULL WHERE tape_id='s1' AND symbol IS NOT NULL")
    store.x("UPDATE lab_tape SET exit_at=? WHERE id='s1'", ((now + timedelta(minutes=10)).isoformat(),))
    CL.resolve("2026-10-28")
    un = store.q("SELECT status, exit_gap_s FROM lab_contracts WHERE tape_id='s1' AND symbol IS NOT NULL")
    assert all(u["status"].startswith("UNFILLED") for u in un)                    # no quote after 10:50: never an earlier one
    rep = CL.report()
    assert rep["signals"] == 0 and any(r["missing"].get("UNFILLED") for r in rep["rows"])
    assert pd is not None and cells


def test_report_reads_one_scorer_version(env):
    CL, lab = _cl_env(env)
    now = DAY.replace(hour=10, minute=40)
    _tape("old1", "2026-10-28", now.isoformat(), status="DONE")
    store.x("INSERT INTO lab_contracts(id, tape_id, day, ticker, family, side, bucket, target_delta, symbol, entry, status, pnl_line, "
            "pnl_hold, pct_line, pct_hold, line_first, version) VALUES('o|0DTE|0.45','old1','2026-10-28','NVDA','board_orb_break','C',"
            "'0DTE',0.45,'X',1.0,'DONE',50,50,50,50,0,?)", (CL.OLD_SCORERS[0],))
    rep = CL.report()
    assert rep["signals"] == 0 and rep["version"] == CL.SCORER and rep["other_versions"][0]["version"] == CL.OLD_SCORERS[0]
    assert "kept apart" in rep["note"]
    old = CL.report(scorer=CL.OLD_SCORERS[0])
    assert old["signals"] == 1


def test_contract_dedupe_and_budget_survive_a_restart_and_the_day_rollover(env):
    CL, lab = _cl_env(env)
    now = DAY.replace(hour=10, minute=40)
    assert _follow(CL, now) > 0
    CL._state.update(tracked=None, last_sample={}, recent={}, tokens=99.0)          # a restart forgets memory
    assert "same stock" in str(_follow(CL, now + timedelta(minutes=2), "s2"))
    assert "already followed" in str(CL.start({"id": "s1", "ticker": "AMD", "side": "C", "family": "f"}, now + timedelta(minutes=20), _F(_cl_chain(now))))
    c = dict(CL.cfg(), starts_per_min=1)
    assert "budget" in str(CL.start({"id": "s3", "ticker": "AMD", "side": "C", "family": "f"}, now + timedelta(seconds=30), _F(_cl_chain(now)), c))
    assert CL._tracked("2026-10-28")                                                 # today's cache filled
    nxt = DAY + timedelta(days=1)
    CL.poll(nxt.replace(hour=9, minute=50))                                          # next morning
    assert CL._tracked(str(nxt.date())) == []
    assert not store.q("SELECT 1 FROM lab_contracts WHERE day='2026-10-28' AND status='TRACKING'")


# ================================================================ C5 router: fail closed, eligibility vs authorization
def _qualified(env, family="ORB_BREAK"):
    import strategy_registry as SR
    real = SR.status_for
    env.setattr(SR, "status_for", lambda fam, t: dict(real(fam, t), status="PAPER QUALIFIED", actionable=True)
                if fam == family else real(fam, t))


def test_router_fails_closed_on_unknown_regime_bar_and_warmup(env):
    import strategy_router as RT
    import strategy_registry as SR
    store.conn()
    env.setattr(core, "now_et", lambda: DAY.replace(hour=10, minute=30))
    real = SR.status_for
    env.setattr(SR, "status_for", lambda fam, t: dict(real(fam, t), status="PAPER QUALIFIED", actionable=True, id="X-REQ"))
    env.setattr(SR, "get", lambda i: {"spec": {"requires": {"regime": ["trend"], "min_warmup_bars": 20}}})
    a = RT.admit("ORB_BREAK", "SPY", "C", None, {"fresh": True})
    txt = " | ".join(a["reasons"])
    assert not a["allowed"] and "regime unknown" in txt and "warmup (unknown" in txt and "bar state unknown" in txt
    a = RT.admit("ORB_BREAK", "SPY", "C", None, {"fresh": True, "bar_complete": True, "regime": "trend", "warmup_bars": 30})
    assert a["allowed"], a["reasons"]


def _e2e_world(env):
    import entrygate
    import strategy_router as RT
    clock, fk = _world(env)
    clock.t = DAY.replace(hour=10, minute=30)
    engine._cache.clear()
    _qualified(env)
    sn = entrygate.snap_from(engine.snapshot("SPY"))
    sn["bar_complete"] = True
    g = entrygate.define("SPY", "C", "orb_break", 599.95, 599.5, 602.0, "test level", sn, "1m close above 599.95",
                         confirmed_at=clock().isoformat(timespec="seconds"), scope="spec_test")
    return clock, fk, RT, sn, g


def test_end_to_end_candidate_to_paper_fill_only_through_authorize(env):
    import strategy_router as RT
    clock, fk, RT, sn, g = _e2e_world(env)
    r = RT.route({"ticker": "SPY", "side": "C", "family": "ORB_BREAK", "fresh": True, "bar_complete": True, "setup_id": "e2e"})
    assert r["decision"] == "ELIGIBLE" and not store.positions()                    # eligible is not an entry
    q, _ = marketdata.option_quote("SPY261028C00600000")
    plan = dict(_plan(), premium_stop=1.60, signal_t=(clock() - timedelta(seconds=5)).isoformat())
    out = RT.authorize(r["id"], g["id"], sn, q, plan, clock())
    assert out["decision"] == "AUTHORIZED", out["reasons"]
    assert out["gate"]["state"] == "ENTRY CONDITIONS MET" and out["ledger"].startswith("spec_")
    p = store.pos_get(out["position_id"])
    assert p["ledger"] == out["ledger"] and p["status"] == "OPEN" and p["qty_open"] == 1
    again = RT.authorize(r["id"], g["id"], sn, q, plan, clock())
    assert again["decision"] == "DUPLICATE" and len(store.positions()) == 1           # a retry never fills twice


def test_authorize_refuses_without_the_full_verified_sequence(env):
    import entrygate
    clock, fk, RT, sn, g = _e2e_world(env)
    q, _ = marketdata.option_quote("SPY261028C00600000")
    plan = dict(_plan(), premium_stop=1.60, signal_t=(clock() - timedelta(seconds=5)).isoformat())
    assert RT.authorize("R-none", g["id"], sn, q, plan, clock())["decision"] == "NOT AUTHORIZED"   # never routed
    r = RT.route({"ticker": "SPY", "side": "C", "family": "ORB_BREAK", "fresh": True, "bar_complete": True, "setup_id": "s1"})
    stale = dict(q, quote_time=pd.Timestamp(clock()) - pd.Timedelta(seconds=90))
    o1 = RT.authorize(r["id"], g["id"], sn, stale, plan, clock())
    assert o1["decision"] == "NOT AUTHORIZED" and any("stale" in x for x in o1["reasons"])
    r2 = RT.route({"ticker": "SPY", "side": "C", "family": "ORB_BREAK", "fresh": True, "bar_complete": True, "setup_id": "s2"})
    o2 = RT.authorize(r2["id"], g["id"], dict(sn, fresh=None), q, plan, clock())   # freshness unknown -> the gate says no
    assert o2["decision"] == "NOT AUTHORIZED" and o2["gate"]["state"] == "NO TRADE"
    r3 = RT.route({"ticker": "SPY", "side": "C", "family": "ORB_BREAK", "fresh": True, "bar_complete": True, "setup_id": "s3"})
    o3 = RT.authorize(r3["id"], g["id"], dict(sn, bar_complete=None), q, plan, clock())
    assert o3["decision"] == "NOT AUTHORIZED" and any("bar state unknown" in x for x in o3["reasons"])
    r4 = RT.route({"ticker": "SPY", "side": "C", "family": "ORB_BREAK", "fresh": True, "bar_complete": True, "setup_id": "s4"})
    o4 = RT.authorize(r4["id"], g["id"], sn, q, dict(plan, premium_stop=2.5), clock())
    assert o4["decision"] == "NOT AUTHORIZED" and any("20%" in x for x in o4["reasons"])
    r5 = RT.route({"ticker": "SPY", "side": "C", "family": "ORB_BREAK", "fresh": True, "bar_complete": True, "setup_id": "s5"})
    other = entrygate.define("SPY", "P", "orb_break", 600.05, 600.5, 598.0, "t", sn, "x", scope="spec_test")
    o5 = RT.authorize(r5["id"], other["id"], sn, q, plan, clock())
    assert o5["decision"] == "NOT AUTHORIZED" and any("different stock or side" in x for x in o5["reasons"])
    assert not store.positions()
    research = RT.route({"ticker": "SPY", "side": "C", "family": "VWAP_RECLAIM", "fresh": True, "bar_complete": True, "setup_id": "s6"})
    assert research["decision"] in ("SHADOW", "REJECT")
    o6 = RT.authorize(research["id"], g["id"], sn, q, plan, clock())
    assert o6["decision"] == "NOT AUTHORIZED" and not store.positions()


# ================================================================ C7 / hosting: health endpoints, token hygiene, CSRF
@pytest.fixture
def http(env, monkeypatch):
    import http.client
    import threading
    from http.server import ThreadingHTTPServer
    import server
    monkeypatch.setattr(server, "DESK_TOKEN", "tok-test-123")
    store.conn()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()

    def req(method, path, headers=None, body=None):
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        out = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return out
    yield req
    srv.shutdown()


def test_link_token_becomes_a_cookie_and_leaves_the_address_bar(http):
    st, h, _ = http("GET", "/?k=tok-test-123&tab=markets")
    assert st == 302 and h["Location"] == "/?tab=markets" and "tok-test-123" not in h["Location"]
    assert "desk_k=tok-test-123" in h["Set-Cookie"] and "HttpOnly" in h["Set-Cookie"]
    st, _, body = http("GET", "/", {"Cookie": "other=1; desk_k=tok-test-123"})
    assert st == 200 and b"<html" in body.lower()
    assert http("GET", "/", {"Cookie": "xdesk_k=tok-test-123"})[0] == 403                # a look-alike cookie is not the token
    assert http("GET", "/api/health")[0] == 403


def test_health_endpoints_need_no_token_and_leak_nothing(http):
    import health
    st, _, body = http("GET", "/healthz")
    assert st == 200 and json.loads(body) == {"alive": True}
    st, _, body = http("GET", "/readyz")
    d = json.loads(body)
    assert st in (200, 503) and set(d) == {"ready", "reasons"}
    health.beat("engine", True, "test", 0.1)
    st, _, body = http("GET", "/api/health", {"Cookie": "desk_k=tok-test-123"})
    d = json.loads(body)
    assert st == 200 and d["workers"]["engine"]["state"] == "ok" and "tok-test-123" not in body.decode()
    assert "schwab_rate" in d and "by_priority" in d["schwab_rate"]


def test_cross_site_posts_are_refused_but_tools_without_origin_work(http):
    ck = {"Cookie": "desk_k=tok-test-123", "Content-Type": "application/json"}
    st, _, _ = http("POST", "/api/reply", dict(ck, Origin="https://evil.example", Host="desk.example"), b'{"reply":"x"}')
    assert st == 403
    st, _, _ = http("POST", "/api/reply", dict(ck, Origin="https://desk.example", Host="desk.example"), b'{"reply":"x"}')
    assert st == 200
    st, _, _ = http("POST", "/api/reply?k=tok-test-123", {"Content-Type": "application/json"}, b'{"reply":"from Chart"}')
    assert st == 200


def test_risk_calls_keep_budget_when_research_has_used_its_share(env, monkeypatch):
    import schwab
    import time as _t
    monkeypatch.setattr(schwab, "_calls", [])
    monkeypatch.setattr(schwab, "RATE_PER_MIN", 10)
    sleeps = []
    monkeypatch.setattr(schwab.time, "sleep", lambda s: sleeps.append(s) or (_ for _ in ()).throw(TimeoutError()))
    with schwab.priority("research"):
        for _ in range(7):
            schwab._throttle()                                     # research may use 70%
        with pytest.raises(TimeoutError):
            schwab._throttle()                                     # the 8th research call would wait
    with schwab.priority("risk"):
        for _ in range(3):
            schwab._throttle()                                     # open-trade protection still gets through at once
    assert len(schwab._calls) == 10 and schwab.current_priority() == "normal"


def test_open_trades_are_managed_before_any_scan(env, monkeypatch):
    clock, fk = _world(env)
    order = []
    monkeypatch.setattr(engine, "_manage_open", lambda: order.append("manage") or [])
    monkeypatch.setattr(engine, "paper_scan", lambda t: order.append("scan"))
    monkeypatch.setattr(engine.noiseband, "tick", lambda *a: order.append("noise"))
    engine.tick()
    assert order and order[0] == "manage" and "scan" in order


def test_a_stale_feed_blocks_new_entries_but_not_exits(env):
    import health
    clock, fk = _world(env)
    paper.reserve_idea("paper", "S1", "SPY", "C")
    pid, _ = paper.buy("paper", "S1", "SPY", "C", _plan(), 1, clock().isoformat())
    health.set_feed(False, "SPY bars stale")
    try:
        paper.reserve_idea("paper", "S2", "SPY", "C")
        p2, why = paper.buy("paper", "S2", "SPY", "C", _plan(), 1, clock().isoformat())
        assert p2 is None and "stale" in why
        assert paper.sell(store.pos_get(pid), 1, "exit while stale")[0] == 1
    finally:
        health.set_feed(True)


def test_lab_protects_open_trades_before_slow_research(env, monkeypatch):
    """Worst case measured: a history pull that hangs for 0.6 s (a slow provider) no longer delays open-trade exits."""
    import time as _t
    import contract_lab
    import lab
    store.conn()
    lab._schema()
    now = DAY.replace(hour=10, minute=30)
    monkeypatch.setattr(core, "now_et", lambda: now)
    seen = []

    class F:
        def ready(self):
            return True
    t0 = _t.time()
    monkeypatch.setattr(lab, "_fetch", lambda: F())
    monkeypatch.setattr(lab, "manage_all", lambda n=None: seen.append(("manage", _t.time() - t0)) or 0)
    monkeypatch.setattr(contract_lab, "poll", lambda n=None: seen.append(("contracts", _t.time() - t0)) or 0)
    monkeypatch.setattr(lab, "_pull_history", lambda n, c: _t.sleep(0.6) or seen.append(("history", _t.time() - t0)))
    monkeypatch.setattr(lab, "scan", lambda *a: seen.append(("scan", _t.time() - t0)) or [])
    store.kv_set(f"scan_base:{now.date()}", {"SPY": {}})
    lab._state.update(day=None)
    lab.step(now)
    names = [s[0] for s in seen]
    assert names[0] == "manage" and names.index("history") > names.index("manage")
    assert seen[0][1] < 0.2 and lab._state["risk_s"] < 0.2 and lab._state["step_s"] >= 0.6
    import health
    assert health.workers()["lab"]["state"] == "ok"


# ================================================================ C2 chart sizing (static contract; the browser run is in docs/checks)
def test_both_chart_roots_share_one_bounded_sizing_contract():
    import re
    h = (ROOT / "index.html").read_text()
    css = re.search(r"\.chartbox>#desk,\.chartbox>#tv,\.chartbox>#mkDesk,\.chartbox>\.chartroot\{([^}]*)\}", h)
    assert css and "position:absolute" in css.group(1) and "inset:0" in css.group(1)
    box = re.search(r"\.chartbox\{([^}]*)\}", h).group(1)
    assert "contain:size" in box and "min-height:160px" in box and "overflow:hidden" in box
    assert 'id="mkDesk" class="chartroot"' in h and 'id="desk" class="chartroot"' in h


# ================================================================ ORBX live paper ledgers
def _orbx_day(offset=500.0, extra=()):
    import test_orbx as TO
    sh = lambda c: tuple(round(x + offset, 2) for x in c)
    c5 = [sh(c) for c in TO.OR3 + [(100.85, 101.30, 100.80, 101.20), (101.2, 101.60, 101.05, 101.50), TO.FLAT,
                                    (101.4, 101.45, 101.02, 101.30)] + list(extra)]
    return TO.bars(c5)


def test_orbx_live_entry_opens_each_exit_variant_once_and_manages_exits(env, monkeypatch):
    import orb_retest as O
    import scanner
    clock, fk = _world(env)
    now = DAY.replace(hour=10, minute=7)
    clock.t = now
    m1 = _orbx_day()
    best = {"symbol": "SPY261028C00600000", "strike": 600, "exp": "2026-10-28", "bid": 1.98, "ask": 2.02, "delta": 0.5}
    monkeypatch.setattr(scanner, "score_contracts", lambda rows, side, now, e: (best, [], {}))
    s = {"m1": m1, "quote": {"last": 601.32, "quote_time": pd.Timestamp(now) - pd.Timedelta(seconds=30), "age_s": 1.0}}
    out = O.live_step("SPY", s, now, fetch_chain=lambda t, side: ([], None))
    assert out and out[0][1] == "ORDER" and len(out[0][2]) == 4
    assert {p["ledger"] for p in store.positions(status="OPEN")} == set(O.LEDGERS)
    assert O.live_step("SPY", s, now + timedelta(seconds=5), fetch_chain=lambda t, side: ([], None)) == []   # never twice
    assert store.q("SELECT state FROM orbx_episodes")[0]["state"] == "POSITION OPEN"
    st = store.kv_get("orbx_stage:SPY")
    assert st["stage"]["C"] == "ENTRY CONFIRMED" and st["or"]["high"] == 601.0
    p = next(x for x in store.positions(status="OPEN") if x["ledger"] == "orbx_2r")
    s2 = dict(s, quote={"last": p["plan"]["stop_px"] - 0.01})
    O.manage(p, s2, now + timedelta(minutes=2))
    assert store.pos_get(p["id"])["status"] == "CLOSED" and "stop" in store.pos_get(p["id"])["plan"]["exit_reason"]


def test_orbx_too_extended_at_the_first_valid_quote_is_skipped_for_good(env, monkeypatch):
    import orb_retest as O
    import scanner
    clock, fk = _world(env)
    now = DAY.replace(hour=10, minute=7)
    clock.t = now
    monkeypatch.setattr(scanner, "score_contracts", lambda *a: ({"symbol": "SPY261028C00600000", "strike": 600, "exp": "2026-10-28",
                                                                   "bid": 1.98, "ask": 2.02}, [], {}))
    s = {"m1": _orbx_day(), "quote": {"last": 602.50, "quote_time": pd.Timestamp(now), "age_s": 1.0}}
    out = O.live_step("SPY", s, now, fetch_chain=lambda t, side: ([], None))
    assert out[0][1] == "SKIP" and "too extended" in out[0][2]
    s["quote"]["last"] = 601.30                                                     # price comes back later: still no chase
    assert O.live_step("SPY", s, now + timedelta(minutes=1), fetch_chain=lambda t, side: ([], None)) == []
    assert not store.positions()


# ================================================================ G3 learning journal
def test_decision_events_are_append_only_and_mirror_candidates(env):
    import sqlite3
    import learning
    store.conn()
    learning.migrate()
    for d in ("SKIP", "ORDER"):                                                 # INSERT OR REPLACE twice on one id
        store.x("INSERT OR REPLACE INTO candidates(id,date,ts,decision_t,ticker,side,family,tags,portfolio,decision,reasons,limit_blocked,"
                "evidence,plan,policy_version,provider,outcome) VALUES('c1','2026-10-28','2026-10-28T10:00:00-04:00',"
                "'2026-10-28T10:00:01-04:00','NVDA','C','board_orb','','board',?,'[\"x\"]',NULL,NULL,'{}','v',NULL,NULL)", (d,))
    ev = store.q("SELECT decision FROM decision_events WHERE source='candidates' ORDER BY seq")
    assert [e["decision"] for e in ev] == ["SKIP", "ORDER"]                      # history kept, not overwritten
    with pytest.raises(sqlite3.DatabaseError):
        store.x("UPDATE decision_events SET decision='X'")
    with pytest.raises(sqlite3.DatabaseError):
        store.x("DELETE FROM decision_events")
    eid = learning.record_decision("orbx_2r", "SPY", "C", "ORBX-15-5", "v", "SKIP", ["too extended"], opportunity="op1",
                                   snapshot={"px": 601.2, "iv": None}, now=DAY.replace(hour=10, minute=7))
    row = store.q("SELECT * FROM decision_events WHERE event_id=?", (eid,))[0]
    assert row["min_since_open"] == 37 and row["decision_t"].endswith("Z") is False and "+00:00" in row["decision_t"]
    assert json.loads(row["quality"])["missing"] == ["iv"]                       # missing is recorded, never filled


def test_hypotheses_are_preregistered_and_cannot_be_quietly_edited(env):
    import learning
    store.conn()
    learning.seed_hypotheses()
    assert {h["id"] for h in store.q("SELECT id FROM hypotheses")} >= {"H-ORBX-1", "H-NEWS-1", "H-REACH-1"}
    h = learning.INITIAL_HYPOTHESES[0]
    with pytest.raises(ValueError):
        learning.register_hypothesis(h[0], h[1], h[2], dict(h[3], min_trades=10), h[4], h[5], h[6])
    learning.set_status("H-ORBX-1", "VALIDATING", "forward data started", {"run": "M-x"})
    hist = store.q("SELECT status FROM hypothesis_events WHERE hypothesis_id='H-ORBX-1' ORDER BY seq")
    assert [x["status"] for x in hist] == ["OPEN", "VALIDATING"]


def test_shadow_outcomes_are_separate_idempotent_and_unknown_when_data_is_missing(env):
    import learning
    import test_orbx as TO
    store.conn()
    learning.migrate()
    now = DAY.replace(hour=10, minute=7)
    learning.record_decision("board", "NVDA", "C", "board_orb", "v", "SKIP-GATE", ["too extended"], opportunity="o1",
                             snapshot={"stop_dist": 0.30}, now=now)
    learning.record_decision("board", "AMD", "P", "board_orb", "v", "SKIP", ["no contract"], opportunity="o2", now=now)
    learning.record_decision("board", "TSLA", "C", "board_orb", "v", "ORDER", [], opportunity="o3", now=now)
    m = TO.bars(TO.OR3 + [(100.85, 101.30, 100.80, 101.20)] * 20)
    fn = lambda day, t: m if t == "NVDA" else None
    assert learning.shadow_eod("2026-10-28", fn) == 2
    assert learning.shadow_eod("2026-10-28", fn) == 0                            # idempotent
    rows = {r["ticker"]: r for r in store.q("SELECT * FROM shadow_outcomes")}
    assert set(rows) == {"NVDA", "AMD"} and rows["AMD"]["r"] is None and "unknown" in rows["AMD"]["why"]
    assert rows["NVDA"]["options"] == "unknown" and rows["NVDA"]["stop_dist"] == 0.3
    assert not store.positions()                                                  # nothing simulated as a fill


def test_backup_is_a_consistent_snapshot_and_eod_resumes(env, tmp_path):
    import sqlite3
    import learning
    store.conn()
    learning.migrate()
    store.kv_set("probe", 42)
    p, ok = learning.backup(tmp_path / "bk")
    assert ok == "ok" and sqlite3.connect(p).execute("SELECT v FROM kv WHERE k='probe'").fetchone()[0] == "42"
    env.setattr(core, "now_et", lambda: DAY.replace(hour=16, minute=15))
    env.setattr(learning, "backup", lambda: (tmp_path / "x.db", "ok"))
    d1 = learning.eod(bars_fn=lambda d, t: None)
    d2 = learning.eod(bars_fn=lambda d, t: (_ for _ in ()).throw(AssertionError("must not rerun")))
    assert d1["backup"] and d2 == d1
    assert "decision_t" in learning.export_csv("decisions") or learning.export_csv("decisions") == ""


def test_learning_view_keeps_ledgers_apart(env):
    import learning
    store.conn()
    env.setattr(core, "now_et", lambda: DAY.replace(hour=11))
    for i in range(3):
        learning.record_decision("board", "NVDA", "C", "board_orb", "v", "SKIP-GATE", ["waiting"], opportunity="same",
                                 now=DAY.replace(hour=10, minute=i))
    v = learning.view("2026-10-28")
    o = [x for x in v["opportunities"] if x["opportunity_id"] == "same"][0]
    assert o["evaluations"] == 3 and o["entered"] == 0                            # one opportunity, three checks
    assert "never summed" in v["note"] and v["shadow_rule"]["options"].startswith("unknown")


# ================================================================ G2 news momentum (pure evaluation on synthetic bars)
def _nm_day(day="2026-10-28", base=100.0, jump_at="09:50", jump=1.2, vol=1000.0, vol_after=5000.0, drift=0.04, until="10:06"):
    idx = pd.date_range(f"{day} 09:30", f"{day} {until}", freq="1min", tz=core.ET, inclusive="left")
    px, rows = base, []
    for t in idx:
        o = px
        if t.strftime("%H:%M") == jump_at:
            px += jump
        elif t.strftime("%H:%M") > jump_at:
            px += drift
        rows.append((o, max(o, px) + 0.02, min(o, px) - 0.02, px, vol_after if t.strftime("%H:%M") >= jump_at else vol))
    return pd.DataFrame(rows, index=idx, columns=["Open", "High", "Low", "Close", "Volume"])


def _nm_prior(n=10):
    out = []
    for k in range(n):
        d = (pd.Timestamp("2026-10-27") - pd.tseries.offsets.BDay(k)).date()
        idx = pd.date_range(f"{d} 09:30", f"{d} 16:00", freq="1min", tz=core.ET, inclusive="left")
        c = 100 + 0.4 * np.sin(np.arange(len(idx)) / 3)
        out.append(pd.DataFrame({"Open": c, "High": c + 0.12, "Low": c - 0.12, "Close": c, "Volume": 1000.0}, index=idx))
    return list(reversed(out))


def _cat(**kw):
    c = {"id": "N-1", "_rev": 2, "tickers": ["AMD"], "label": "confirmed", "category": "contract", "recycled": False,
         "content_verified": True, "first_detected_at": "2026-10-28T09:49:30-04:00", "published_at": "2026-10-28T09:48:00-04:00",
         "price_at_detect": 100.0, "headline": "AMD wins a large contract"}
    c.update(kw)
    return c


def test_news_momentum_needs_a_verified_catalyst_and_a_real_reaction():
    import news_momentum as N
    now = pd.Timestamp("2026-10-28 10:05", tz=core.ET)
    prior = _nm_prior()
    ev = N.evaluate(_cat(), _nm_day(), prior, now)
    assert ev["stage"] == "ENTRY CONFIRMED", (ev.get("why"), ev["numbers"])
    assert ev["side"] == "C" and ev["stop"] < ev["entry_ref"] and ev["numbers"]["rvol_time"] >= 2
    ev = N.evaluate(_cat(content_verified=False), _nm_day(), prior, now)
    assert ev["stage"] == "WATCHING" and "not verified" in ev["why"]                       # a URL alone is not proof
    ev = N.evaluate(_cat(tickers=["AMD", "NVDA", "INTC", "MU"]), _nm_day(), prior, now)
    assert ev["stage"] == "SKIP" and "company-specific" in ev["why"]
    ev = N.evaluate(_cat(), _nm_day(vol_after=1200.0), prior, now)
    assert ev["stage"] == "WATCHING" and "relative volume" in ev["why"]                    # sentiment alone never enters
    ev = N.evaluate(_cat(), _nm_day(jump=0.1, drift=0.0), prior, now)
    assert ev["stage"] == "WATCHING" and "reaction" in ev["why"]
    ev = N.evaluate(_cat(), _nm_day(jump=-1.2, drift=-0.04), prior, now)
    assert ev["stage"] == "ENTRY CONFIRMED" and ev["side"] == "P"                          # down move -> puts


def test_news_momentum_rejects_spikes_exhaustion_stale_news_and_missing_baselines():
    import news_momentum as N
    now = pd.Timestamp("2026-10-28 10:05", tz=core.ET)
    prior = _nm_prior()
    spike = _nm_day(jump=1.6, drift=-0.07)                                                # gave most of it back
    assert N.evaluate(_cat(), spike, prior, now)["stage"] in ("SKIP", "WATCHING")
    ev = N.evaluate(_cat(), _nm_day(jump=9.0), prior, now)
    assert ev["stage"] == "SKIP" and "exhausted" in ev["why"]
    ev = N.evaluate(_cat(first_detected_at="2026-10-28T08:00:00-04:00"), _nm_day(), prior, now)
    assert ev["stage"] == "EXPIRED"
    ev = N.evaluate(_cat(), _nm_day(), [], now)
    assert ev["stage"] == "WATCHING" and "fails closed" in ev["why"]
    ev = N.evaluate(_cat(first_detected_at="2026-10-28T10:00:00-04:00"), _nm_day(jump_at="10:00"), prior, now)
    assert ev["stage"] in ("CONFIRMING", "WATCHING")                                       # must survive 10 minutes
    late = N.evaluate(_cat(published_at="2026-10-28T08:40:00-04:00"), _nm_day(), prior, now)
    assert late.get("late_news") is True                                                   # received 60 min late: flagged


def test_loss_streak_spans_actionable_ledgers_chronologically(env):
    import strategy_router as RT
    store.conn()
    env.setattr(core, "now_et", lambda: DAY.replace(hour=13))

    def closed(i, led, t, pnl):
        store.pos_save({"id": f"S{i}", "ledger": led, "date": "2026-10-28", "ticker": "SPY", "contract": "1C", "symbol": "S", "side": "C",
                        "qty_init": 1, "qty_open": 0, "fill": 1.0, "opened": t, "closed": t, "status": "CLOSED", "setup_id": "x", "grade": "R",
                        "setup": "X", "plan": {}, "realized": pnl, "mfe": 0, "mae": 0, "policy_version": "t", "verified": "t", "notes": ""})
    closed(1, "spec_a", "2026-10-28T10:00:00-04:00", -20)
    closed(2, "spec_b", "2026-10-28T10:30:00-04:00", -15)                  # a different ledger does not reset the streak
    assert "A setups only" in RT.actionable_discipline(["spec_a", "spec_b"], "2026-10-28")
    closed(3, "spec_c", "2026-10-28T11:00:00-04:00", -10)
    assert "loss-streak stop: 3" in RT.portfolio_admission("2026-10-28")
    closed(4, "spec_a", "2026-10-28T11:30:00-04:00", 30)
    assert RT.actionable_discipline(["spec_a", "spec_b", "spec_c"], "2026-10-28") is None


# ================================================================ underlying-first helpers
def test_premium_trigger_is_the_exact_formula_rounded_to_a_protective_tick():
    import underlying_first as U
    t = U.premium_trigger(2.03, qty=2, bid=1.98)
    assert t["trigger_bid"] == 1.64 and t["feasible"]
    assert t["planned_loss_per_contract"] == round(100 * (2.03 - (1.64 - 0.01)) + 0.04, 2) <= t["budget_per_contract"]
    assert t["planned_loss_total"] == round(2 * t["planned_loss_per_contract"], 2)
    n = U.premium_trigger(4.20, bid=4.10, symbol_root="NVDA")
    assert n["tick"] == 0.05 and n["trigger_bid"] == 3.40 and n["planned_loss_per_contract"] <= n["budget_per_contract"]
    assert not U.premium_trigger(0.05, bid=0.04)["feasible"]
    assert not U.premium_trigger(2.00, bid=1.55)["feasible"]                         # trigger at/above the bid
    import contract_lab
    assert t["trigger_bid"] == contract_lab.line_for(2.03)                          # same line everywhere


def test_zero_dte_comes_from_the_chain_received_never_assumed():
    import underlying_first as U
    assert U.zero_dte([], "2026-10-28")[0] is None
    assert U.zero_dte([{"exp": "2026-10-30"}, {"exp": "2026-11-06"}], "2026-10-28")[0] is False
    assert U.zero_dte([{"exp": "2026-10-28"}], "2026-10-28")[0] is True


def test_reach_odds_are_reproducible_conservative_and_symmetric_on_a_random_walk():
    import underlying_first as U
    rng = np.random.default_rng(1)
    prior = []
    for k in range(20):
        d = (pd.Timestamp("2026-10-27") - pd.tseries.offsets.BDay(k)).date()
        idx = pd.date_range(f"{d} 09:30", f"{d} 16:00", freq="1min", tz=core.ET, inclusive="left")
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.0007, len(idx))))
        o = np.r_[100, c[:-1]]
        prior.append(pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.0002, "Low": np.minimum(o, c) * 0.9998, "Close": c}, index=idx))
    now = pd.Timestamp("2026-10-28 11:00", tz=core.ET)
    today = prior[0].copy()
    today.index = pd.date_range("2026-10-28 09:30", periods=len(today), freq="1min", tz=core.ET)
    a, _ = U.reach_odds(prior, today, 100.0, 99.5, 100.5, "C", now)
    b, _ = U.reach_odds(prior, today, 100.0, 99.5, 100.5, "C", now)
    assert a == b and abs(a["p_target"] - a["p_stop"]) < 0.08 and abs(a["p_target"] + a["p_stop"] + a["p_neither"] - 1) < 0.01
    far, _ = U.reach_odds(prior, today, 100.0, 99.5, 103.0, "C", now)
    assert far["p_target"] < a["p_target"]
    assert U.reach_odds(prior[:5], today, 100.0, 99.5, 100.5, "C", now)[0] is None      # too few sessions: no number


def test_verify_day_recomputes_paper_pnl_read_only(env, capsys, monkeypatch):
    import importlib.util
    clock, fk = _world(env)
    paper.reserve_idea("noise", "N1", "SPY", "C")
    pid, _ = paper.buy("noise", "N1", "SPY", "C", _plan(), 2, clock().isoformat())
    paper.sell(store.pos_get(pid), 1, "partial")
    paper.sell(store.pos_get(pid), 1, "rest")
    spec = importlib.util.spec_from_file_location("verify_day", ROOT / "tools" / "verify_day.py")
    vd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vd)
    monkeypatch.setattr(vd, "DB", store.DB)
    monkeypatch.setattr(sys, "argv", ["verify_day.py", "2026-10-28", "noise"])
    vd.main()
    out = capsys.readouterr().out
    assert "MISMATCH" not in out and "recomputed" in out and "not real money" in out
    with pytest.raises(Exception):
        import sqlite3
        sqlite3.connect(f"file:{store.DB}?mode=ro", uri=True).execute("DELETE FROM positions")


def test_no_token_never_publishes_the_desk_through_a_tunnel(env, monkeypatch):
    import http.client
    import threading
    from http.server import ThreadingHTTPServer
    import server
    monkeypatch.setattr(server, "DESK_TOKEN", "")
    store.conn()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def get(path, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
        c.request("GET", path, headers=headers or {})
        r = c.getresponse()
        r.read()
        return r.status
    try:
        assert get("/api/health") == 200                                           # local, no proxy headers
        assert get("/api/health", {"X-Forwarded-For": "203.0.113.9"}) == 403        # through a tunnel: refused
        assert get("/healthz", {"X-Forwarded-For": "203.0.113.9"}) == 200           # liveness carries no data
    finally:
        srv.shutdown()


def test_repeated_wrong_tokens_are_paused(http, monkeypatch):
    import server
    monkeypatch.setattr(server, "_FAILS", {})
    for _ in range(20):
        assert http("GET", "/api/health?k=wrong", {"X-Forwarded-For": "198.51.100.7"})[0] == 403
    assert http("GET", "/api/health?k=tok-test-123", {"X-Forwarded-For": "198.51.100.7"})[0] == 403   # paused even with the right one
    assert http("GET", "/api/health?k=tok-test-123", {"X-Forwarded-For": "198.51.100.8"})[0] == 200
