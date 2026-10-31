"""Read-only check of one day's paper P/L from the raw records (v3.5).

    python3 tools/verify_day.py 2026-10-30 noise        # one ledger
    python3 tools/verify_day.py 2026-10-30              # every ledger

Opens journal/desk.db READ-ONLY (sqlite URI mode=ro: nothing can be written), lists each position with its entry
fill, every sell order, the stored realized P/L and the P/L recomputed from the orders and the fee per side recorded
at entry, and flags any mismatch. These are SIMULATED paper fills on real quotes, not real-money results.
"""
import json
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "journal" / "desk.db"


def main():
    day = sys.argv[1]
    led = sys.argv[2] if len(sys.argv) > 2 else None
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    q = "SELECT * FROM positions WHERE date=?" + (" AND ledger=?" if led else "") + " ORDER BY ledger, opened"
    rows = c.execute(q, (day, led) if led else (day,)).fetchall()
    tot, tot_re = 0.0, 0.0
    for p in rows:
        plan = json.loads(p["plan"] or "{}")
        fee = plan.get("fees_side")
        sells = c.execute("SELECT ts, qty, filled_price, reason FROM orders WHERE position_id=? AND side='sell' ORDER BY ts", (p["id"],)).fetchall()
        re = None
        if fee is not None and p["status"] == "CLOSED":
            re = round(sum((s["filled_price"] - p["fill"]) * 100 * s["qty"] - fee * s["qty"] for s in sells) - fee * p["qty_init"], 2)
        flag = "" if re is None or abs(re - (p["realized"] or 0)) < 0.02 else "  <-- MISMATCH"
        print(f"{p['ledger']:<12} {p['id']:<40} {p['ticker']:<5} {p['contract']:<14} qty {p['qty_init']} fill {p['fill']:.2f} "
              f"opened {str(p['opened'])[11:19]} {p['status']:<6} stored {p['realized']:+.2f} recomputed {re if re is not None else 'n/a'}{flag}")
        for s in sells:
            print(f"{'':<14}sell {s['qty']} @ {s['filled_price']:.2f} {str(s['ts'])[11:19]} {s['reason']}")
        tot += p["realized"] or 0
        tot_re += re or 0
    print(f"\n{len(rows)} positions, stored realized total {tot:+.2f}, recomputed {tot_re:+.2f} "
          "(closed positions only; open ones have no final P/L). Simulated paper fills, not real money.")


if __name__ == "__main__":
    main()
