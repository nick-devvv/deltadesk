"""v3.5 tests: atomic paper lifecycle (C6), and the integrity fixes that follow it. No network, no AI."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

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
