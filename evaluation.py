"""evaluation.py - the forward paper test, scored against the criteria fixed in policy.json -> evaluation
BEFORE any result existed. Read-only: it never changes a rule or a trade.

  python3 evaluation.py            # prints the scorecard
  GET /api/evaluation              # same, as JSON (the desk page and the 4:20 review can read it)
"""
import json
import random
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402
import store  # noqa: E402

MIN_SCHWAB_RTH_MIN = 375          # a "complete valid session": Schwab bars for at least 375 of 390 RTH minutes


def _closed(ledger, since, version):
    return store.q("SELECT id, date, setup_id, realized, opened, closed, verified, policy_version FROM positions "
                   "WHERE ledger=? AND date>=? AND status='CLOSED' AND (policy_version=? OR ?='')"
                   " ORDER BY closed", (ledger, since, version, version))


def valid_sessions(since):
    rows = store.q("SELECT substr(open,1,10) d, COUNT(*) n FROM bars_archive WHERE ticker='SPY' AND src LIKE 'Schwab%' "
                   "AND substr(open,12,5) >= '09:30' AND substr(open,12,5) < '16:00' AND open >= ? GROUP BY d", (since,))
    return sorted(r["d"] for r in rows if r["n"] >= MIN_SCHWAB_RTH_MIN)


def stats(pnls):
    n = len(pnls)
    if not n:
        return {"n": 0}
    wins = [x for x in pnls if x > 1]
    losses = [x for x in pnls if x < -1]
    eq, peak, dd = 0.0, 0.0, 0.0
    for x in pnls:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    rnd = random.Random(7)                              # fixed seed: the same trades always give the same interval
    boots = sorted(sum(rnd.choice(pnls) for _ in range(n)) / n for _ in range(2000))
    gl = -sum(losses)
    return {"n": n, "net": round(sum(pnls), 2), "expectancy": round(sum(pnls) / n, 2),
            "ci95": [round(boots[49], 2), round(boots[1949], 2)], "wins": len(wins), "losses": len(losses),
            "breakeven": n - len(wins) - len(losses), "win_rate": round(100 * len(wins) / n, 1),
            "profit_factor": round(sum(wins) / gl, 2) if gl > 0 else None,
            "max_drawdown": round(dd, 2), "avg_loss": round(sum(losses) / len(losses), 2) if losses else None}


def stats_v2(trades, sessions=None, seed=7, boots=2000):
    """v3.3 evaluation (eval2). trades: [{pnl, session, opened?, closed?}]. Differences from stats():
      * a win is pnl > 0 and a loss pnl < 0, with no +/-$1 band (exact zeros are listed as flat);
      * the 95% interval resamples whole SESSIONS (trades on one day are not independent), including sessions with
        no trades when `sessions` lists them;
      * concurrency (most positions open at once) and exposure (minutes held) are reported."""
    n = len(trades)
    out = {"n": n, "version": "eval2", "sessions": len(set(sessions or [t["session"] for t in trades]))}
    if not n:
        return dict(out, note="no trades: no win rate")
    p = [float(t["pnl"]) for t in trades]
    wins, losses = [x for x in p if x > 0], [x for x in p if x < 0]
    eq = peak = dd = 0.0
    for x in p:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    by = {}
    for t in trades:
        by.setdefault(t["session"], []).append(float(t["pnl"]))
    days = sorted(set(sessions or []) | set(by))
    rnd = random.Random(seed)
    sims = []
    for _ in range(boots):
        pick = [rnd.choice(days) for _ in days]
        tot = [x for d in pick for x in by.get(d, [])]
        sims.append(sum(tot) / len(tot) if tot else 0.0)
    sims.sort()
    conc, expo = 0, 0.0
    ev = []
    for t in trades:
        if t.get("opened") and t.get("closed"):
            a, b = datetime.fromisoformat(t["opened"]), datetime.fromisoformat(t["closed"])
            expo += (b - a).total_seconds() / 60
            ev += [(a, 1), (b, -1)]
    cur = 0
    for _, k in sorted(ev, key=lambda x: (x[0], x[1])):
        cur += k
        conc = max(conc, cur)
    top = sorted(p, reverse=True)[:5]
    out.update(net=round(sum(p), 2), expectancy=round(sum(p) / n, 2),
               ci95_session=[round(sims[int(0.025 * boots)], 2), round(sims[int(0.975 * boots) - 1], 2)],
               win_rate=round(100 * len(wins) / n, 1), wins=len(wins), losses=len(losses), flat=n - len(wins) - len(losses),
               avg_win=round(sum(wins) / len(wins), 2) if wins else None, avg_loss=round(sum(losses) / len(losses), 2) if losses else None,
               profit_factor=round(sum(wins) / -sum(losses), 2) if losses else None, max_drawdown=round(dd, 2),
               max_concurrent=conc, exposure_min=round(expo, 1),
               top5_share=round(sum(top) / sum(p), 2) if sum(p) > 0 else None, small_sample=n < 30)
    return out


def versioned(led, since="2000-01-01"):
    """One ledger split by policy version AND execution model: old and corrected trades are never pooled."""
    import json as _j
    rows = store.q("SELECT date, realized, plan, policy_version, opened, closed FROM positions WHERE ledger=? AND date>=? AND status='CLOSED' "
                   "ORDER BY closed", (led, since))
    groups = {}
    for r in rows:
        try:
            pl = _j.loads(r["plan"]) if isinstance(r["plan"], str) else (r["plan"] or {})
        except ValueError:
            pl = {}
        k = (r["policy_version"] or "unversioned", pl.get("exec_model") or "exec1 (legacy)")
        groups.setdefault(k, []).append({"pnl": r["realized"] or 0, "session": r["date"], "opened": r["opened"], "closed": r["closed"]})
    return [{"policy_version": k[0], "exec_model": k[1], **stats_v2(v)} for k, v in sorted(groups.items())]


def violations(since, version):
    out = []
    for led in ("paper", "research"):
        ps = _closed(led, since, version)
        dup = store.q("SELECT setup_id, COUNT(*) n FROM positions WHERE ledger=? AND date>=? GROUP BY setup_id HAVING n > 1", (led, since))
        out += [f"{led}: idea {d['setup_id']} has {d['n']} positions" for d in dup]
        out += [f"{led}: {p['id']} filled on {p['verified']}" for p in ps if "Schwab" not in (p["verified"] or "")]
        for p in ps:
            day = core.session_info(__import__("datetime").datetime.fromisoformat(p["opened"]))
            if (p["closed"] or "")[11:16] > day["all_out"] and p["closed"][:10] == p["date"]:
                out.append(f"{led}: {p['id']} closed {p['closed'][11:16]}, after all out {day['all_out']}")
    return out


LEDGER_INFO = {
    "paper": ("Main paper", "v3 rules, frozen for the forward test"),
    "research": ("Research", "v3 setups without the daily limits"),
    "exit31": ("v3.1 exits", "the research entries with exits that let winners run"),
    "noise": ("Noise band", "SPY/QQQ half-hour momentum (Zarattini/Aziz/Barbon), with options"),
    "inplay": ("Stocks in play", "scanner ORB on the day's top-volume names, with options"),
    "old": ("Old rules", "frozen 20/12/10% stops"),
    "gated": ("Gated entries", "the research entries, only when the anti-chasing gate passes"),
    "board": ("Stocks: setups board", "v3.3: qualifying setups-board rows on stocks/ETFs, through the entry gate, 1 contract; X read recorded, never a trigger"),
    "earn_post": ("Earnings: after the release", "post-release confirmation setups on reporting names"),
    "earn_pre": ("Earnings: held through", "research only: an ATM straddle held through the report, sized by the full premium"),
    "real": ("You", "your reported trades"),
    # v3.5: new versioned research ledgers (the frozen main rules are untouched)
    "orbx_swing": ("ORB retest: swing trail", "v3.5 corrected ORB (break, independent candle, retest) on SPY/QQQ; trail = last 2 finished 5m candles after +1R"),
    "orbx_atr": ("ORB retest: ATR trail", "same entries; trail = best close - 2 x ATR5 after +1R"),
    "orbx_2r": ("ORB retest: fixed 2R", "same entries; the desk's shared 2R yardstick"),
    "orbx_ormid": ("ORB retest: OR-mid stop, 1R", "same entries; stop at the opening-range midpoint, 1R target (from day-trader-skill)"),
    "news_mom": ("News momentum (stocks)", "v3.5 verified catalyst + price/volume confirmation; calls up, puts down; research only"),
}
try:                                              # v3.4: one lab ledger per strategy family
    import lab as _lab
    for _f, _v in _lab.FAMILIES.items():
        LEDGER_INFO[_v["ledger"]] = ("Lab: " + _v["label"], f"v3.4 strategy lab, {_v['source']}: 1 contract, strict fills, research only")
except Exception:
    pass


def ledger_report(led, since="2000-01-01"):
    """Expectancy, average win vs loss, drawdown and sample size for one ledger, plus the stock's move next to the
    option result (from the underlying price recorded at entry and exit)."""
    import json as _j
    rows = store.q("SELECT id, date, side, fill, qty_init, realized, plan, policy_version, setup FROM positions "
                   "WHERE ledger=? AND date>=? AND status='CLOSED' ORDER BY closed", (led, since))
    pnls = [r["realized"] or 0 for r in rows]
    out = stats(pnls)
    moves, reasons = [], {}
    for r in rows:
        try:
            pl = _j.loads(r["plan"]) if isinstance(r["plan"], str) else (r["plan"] or {})
        except ValueError:
            pl = {}
        if pl.get("entry_px") and pl.get("exit_px"):
            mv = (pl["exit_px"] - pl["entry_px"]) * (1 if r["side"] == "C" else -1)
            moves.append(mv / pl["entry_px"] * 100)
        why = (pl.get("exit_reason") or "unknown").split(":")[0].split(" (")[0][:32]
        g = reasons.setdefault(why, {"n": 0, "net": 0.0})
        g["n"] += 1
        g["net"] = round(g["net"] + (r["realized"] or 0), 2)
    out["stock_move_avg_pct"] = round(sum(moves) / len(moves), 3) if moves else None
    out["stock_move_positive_pct"] = round(100 * sum(1 for m in moves if m > 0) / len(moves), 1) if moves else None
    out["exits"] = reasons
    out["versions"] = sorted({r["policy_version"] for r in rows if r["policy_version"]})
    out["avg_win"] = round(sum(x for x in pnls if x > 1) / max(1, sum(1 for x in pnls if x > 1)), 2) if any(x > 1 for x in pnls) else None
    out["small_sample"] = len(pnls) < 30
    out["name"], out["what"] = LEDGER_INFO.get(led, (led, ""))
    return out


RULE_GROUPS = (("reversal", ("failed", "reversal")), ("pullback / retest", ("retest", "pullback", "vwap_retest")),
               ("confirmed breakout", ("orb", "break", "level", "pdh", "pdl", "pmh", "pml", "vwap", "noise", "inplay")))


def _rule_group(kind):
    k = (kind or "").lower()
    for name, keys in RULE_GROUPS:
        if any(x in k for x in keys):
            return name
    return "other"


def rules_compare(since="2000-01-01"):
    """Entry rules side by side on the SAME sample of stored setups, including the ones that were never traded
    (missed, invalidated, too extended, no trade), so fewer trades can't hide missed opportunities.
    Results are paper P&L after modeled costs. "Early breakout" (entering before a finished close) is never traded by
    the gate, so it has no P&L here; it would need its own research ledger to be compared fairly."""
    import json as _j
    try:
        setups = store.q("SELECT id, kind, status, data FROM gate_setups WHERE date>=?", (since,))
    except Exception:
        setups = []
    pos = store.q("SELECT ledger, realized, plan, status FROM positions WHERE date>=? AND status='CLOSED'", (since,))
    by_gate = {}
    for r in pos:
        try:
            pl = _j.loads(r["plan"]) if isinstance(r["plan"], str) else (r["plan"] or {})
        except ValueError:
            pl = {}
        gid = (pl.get("gate") or {}).get("id") if isinstance(pl.get("gate"), dict) else pl.get("gate_id")
        if gid:
            by_gate.setdefault(gid, []).append(r["realized"] or 0)
    groups = {}
    for g in setups:
        name = _rule_group(g["kind"])
        x = groups.setdefault(name, {"setups": 0, "status": {}, "pnls": []})
        x["setups"] += 1
        x["status"][g["status"]] = x["status"].get(g["status"], 0) + 1
        x["pnls"] += by_gate.get(g["id"], [])
    out = {}
    for name, x in groups.items():
        st = stats(x["pnls"])
        out[name] = {"setups": x["setups"], "traded": len(x["pnls"]), "not_traded": x["setups"] - len(x["pnls"]),
                     "status": x["status"], "paper": st, "small_sample": len(x["pnls"]) < 30}
    return {"since": since, "groups": out, "early_breakout": "not traded by design (the gate needs a finished close)",
            "note": "Same-day paper sample after modeled costs. Under 30 trades a group is not evidence. Chronological, "
                    "out-of-sample comparison: candidate rules are versioned and judged only on sessions after they were fixed."}


def latency(since="2000-01-01"):
    """Observed latencies: signal bar final -> simulated paper fill (configured decision latency included), and the
    catalyst publication -> first detection -> alert times. Observations from timestamps, not estimates."""
    import json as _j
    import statistics
    fills = []
    for r in store.q("SELECT plan FROM positions WHERE date>=? AND ledger != 'real'", (since,)):
        try:
            pl = _j.loads(r["plan"]) if isinstance(r["plan"], str) else (r["plan"] or {})
        except ValueError:
            continue
        if pl.get("latency_s") is not None:
            fills.append(float(pl["latency_s"]))
    def summ(v):
        return {"n": len(v), "median_s": round(statistics.median(v), 1), "p90_s": round(sorted(v)[int(0.9 * (len(v) - 1))], 1)} if v else {"n": 0}
    out = {"signal_to_paper_fill": summ(fills)}
    try:
        import catalysts
        out["catalysts"] = catalysts.metrics()
    except Exception as e:
        out["catalysts"] = {"error": type(e).__name__}
    out["note"] = "Measured on this desk. When other traders or professional feeds saw the same news is unknown."
    return out


def report():
    ev = core.policy().get("evaluation") or {}
    since, version = ev.get("start", "2026-10-30"), ev.get("policy_version", "")
    sess = valid_sessions(since)
    res = {"config": ev, "valid_sessions": len(sess), "session_days": sess, "ledgers": {}}
    for led in ("paper", "research", "old", "real"):
        res["ledgers"][led] = stats([r["realized"] or 0 for r in _closed(led, since, version if led in ("paper", "research") else "")])
    m = res["ledgers"]["paper"]
    v = violations(since, version)
    checks = {
        "sessions": len(sess) >= ev.get("min_sessions", 10),
        "enough_trades": m.get("n", 0) >= 20,
        "expectancy_positive": (m.get("expectancy") or 0) > 0,
        "profit_factor": (m.get("profit_factor") or 0) >= 1.2,
        "drawdown": m.get("n", 0) > 0 and m.get("avg_loss") is not None and m["max_drawdown"] < 3 * abs(m["avg_loss"]),
        "no_violations": not v,
    }
    res["checks"], res["violations"] = checks, v
    if not checks["sessions"]:
        res["verdict"] = f"running: {len(sess)} of {ev.get('min_sessions', 10)} valid sessions"
    elif not checks["enough_trades"]:
        res["verdict"] = f"not enough trades ({m.get('n', 0)} of 20): extend the test"
    else:
        res["verdict"] = "criteria met (paper only; Nick decides what happens next)" if all(checks.values()) else \
                         "criteria not met: " + ", ".join(k for k, ok in checks.items() if not ok)
    res["note"] = "Paper results with modeled costs. A pass is not permission for real-money automation or larger size."
    res["versioned"] = {led: versioned(led) for led in ("paper", "research", "gated", "board", "earn_post", "noise", "inplay", "exit31", "old", "real")}
    res["rules_compare"] = rules_compare()            # everything the gate has recorded (it started with v3.2)
    res["latency"] = latency()
    return res


if __name__ == "__main__":
    print(json.dumps(report(), indent=1, default=str))
