"""replay.py on a synthetic day: reproducible, sandboxed (live DB untouched), modeled labels, old vs new exits."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import fakes  # noqa: E402
import replay  # noqa: E402
import store  # noqa: E402
import test_v3 as T  # noqa: E402


def test_replay_is_sandboxed_reproducible_and_labeled(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "REPORTS", tmp_path / "reports")
    live_db = store.DB
    m = fakes.make_market(T.vm_path, T.DAY)
    import pandas as pd
    rows = []
    for tk in ("SPY", "QQQ"):
        d = m.copy()
        d["ticker"] = tk
        d["ts"] = d.index.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append(d[["ts", "ticker", "Open", "High", "Low", "Close", "Volume"]])
    csv = tmp_path / "replay_bars_2026-10-28_synthetic.csv"
    pd.concat(rows).to_csv(csv, index=False)
    # an original database with one paper trade (like SPY 770C) and one real trade without a symbol
    db = tmp_path / "orig.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE positions(id TEXT, ledger TEXT, date TEXT, ticker TEXT, contract TEXT, symbol TEXT, side TEXT, qty_init INT, qty_open INT,"
              " fill REAL, opened TEXT, closed TEXT, status TEXT, setup_id TEXT, grade TEXT, setup TEXT, plan TEXT, realized REAL, mfe REAL, mae REAL,"
              " policy_version TEXT, verified TEXT, notes TEXT)")
    c.execute("CREATE TABLE orders(client_id TEXT, position_id TEXT, ts TEXT, side TEXT, qty INT, status TEXT, broker_id TEXT, filled_qty INT, filled_price REAL, reason TEXT)")
    c.execute("INSERT INTO positions VALUES('PA-1','paper','2026-10-28','SPY','600C','SPY261028C00600000','C',1,0,2.10,'2026-10-28T10:06:30-04:00',"
              "'2026-10-28T10:20:00-04:00','CLOSED','x','A','FAILED_BREAK',?,24.0,21,0,'old','alpaca','')", (json.dumps({"invalidation": 599.6}),))
    c.execute("INSERT INTO positions VALUES('RE-1','real','2026-10-28','MU','1015C',NULL,'C',1,0,1.00,'2026-10-28T11:00:00-04:00',"
              "'2026-10-28T11:20:00-04:00','CLOSED','y',NULL,'manual','{}',-23.0,0,0,'old','reported','')")
    c.commit()
    c.close()
    days, trades = replay.main(["2026-10-28", "--csv", str(csv), "--db", str(db), "--until", "11:00", "--modes", "close"])
    assert store.DB == live_db                                    # the sandbox restored the live database path
    md = (tmp_path / "reports" / "replay_2026-10-28.md").read_text()
    assert "MODELED" in md and "Regression case only" in md and "sha256" in md
    assert "paper: 1 closed positions" in md and "real: 1 closed positions" in md
    spy = [t for t in trades if t.get("contract") == "600C"][0]
    assert spy["iv_solved_from_fill"] > 0 and spy["old_rules"]["exits"] and spy["v3_rules"]["exits"]
    assert "v3 would" in spy["v3_entry_verdict"]
    assert [t for t in trades if t.get("skipped")]                # MU: no bars loaded, reported instead of invented
    assert "paper" in days[0]["ledgers"] and "old" in days[0]["ledgers"]
    days2, _ = replay.main(["2026-10-28", "--csv", str(csv), "--until", "11:00", "--modes", "close", "--db", ""])
    assert json.dumps(days2[0]["ledgers"], sort_keys=True) == json.dumps(days[0]["ledgers"], sort_keys=True)   # same bars -> same result
