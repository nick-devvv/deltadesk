"""replay.py - reproducible replay of one trading day through the v3 engine, the frozen old policy, and the
original trades' exits under old vs new rules.

This is a REGRESSION CASE, not an untouched test: October 28 was used to design v3, so a good result here proves
nothing about the future. Forward paper trading (docs/EVALUATION.md) is the real test.

Run it in the desk folder (it never touches the live database, never alerts, never sends anything anywhere):

  python replay.py 2026-10-28                     # 1m bars from Schwab price history (Schwab must be connected)
  python replay.py 2026-10-28 --source yahoo      # research-only fallback, labeled as such in the report
  python replay.py 2026-10-28 --csv reports/replay_bars_2026-10-28_schwab.csv   # exact rerun from saved bars

  --db journal/desk.db   the desk's real database, read-only, for the original Oct 28 records (default)
  --iv 0.18              implied vol for the modeled option quotes when no fill to calibrate against
  --until 15:30          stop the day early (quick checks)

Outputs (reports/): replay_<date>.md (read this), replay_<date>.json, and the bars CSV with its sha256.

What is real and what is modeled:
  - Underlying 1m bars: real (Schwab, or Yahoo if you chose it). Saved so every rerun uses identical data.
  - Option quotes: MODELED. Schwab has no historical option bid/ask, so every option price here comes from
    Black-Scholes on the real underlying with a modeled spread. For the original trades the volatility is solved
    from the actual recorded fill, so the model starts where the real trade started. Every option P&L is MODELED.
  - Intrabar order is unknown. Two runs are reported: "close" (quotes at each finished 1m close) and "adverse"
    (the bid uses the worst price inside each minute, so stops are counted first when a bar touched both).
"""
import argparse
import contextlib
import copy
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
for k in ("NTFY_TOPIC", "CHAT_WEBHOOK", "GROK_WEBHOOK"):
    os.environ.pop(k, None)                       # a replay never pushes alerts

import pandas as pd  # noqa: E402

import core  # noqa: E402
import marketdata  # noqa: E402
import store  # noqa: E402

ET = core.ET
REPORTS = HERE / "reports"


# ---------------------------------------------------------------- option model
def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(spot, strike, iv, side, now):
    """Black-Scholes price/delta/gamma/theta(per minute) for a 0DTE option, r = 0. Time floored at 2 minutes."""
    close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    t = max((close - now).total_seconds(), 120) / (365 * 24 * 3600)
    sq = iv * math.sqrt(t)
    d1 = (math.log(spot / strike) + 0.5 * iv * iv * t) / sq
    d2 = d1 - sq
    pdf = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    if side == "C":
        px, delta = spot * _ncdf(d1) - strike * _ncdf(d2), _ncdf(d1)
    else:
        px, delta = strike * _ncdf(-d2) - spot * _ncdf(-d1), _ncdf(d1) - 1
    gamma = pdf / (spot * sq)
    theta_year = -spot * pdf * iv / (2 * math.sqrt(t))
    return max(px, 0.0), delta, gamma, theta_year / (365 * 24 * 60)


def model_spread(mid):
    """SPY/QQQ 0DTE near the money usually trade a few cents wide. Modeled, not observed."""
    return 0.02 if mid < 2 else 0.03 if mid < 5 else 0.05


class ReplayProvider(marketdata.Provider):
    executable = True    # inside the replay only: every fill is labeled MODELED in the report

    def __init__(self, m1s, clock, source, iv=0.18, mode="close"):
        self.m1s, self.clock, self.iv, self.mode = m1s, clock, iv, mode
        self.iv_by_symbol = {}
        self.name = f"REPLAY {source} bars + MODELED options ({mode})"

    def _finished(self, ticker):
        t = pd.Timestamp(self.clock())
        m = self.m1s.get(ticker)
        return m[m.index <= t - pd.Timedelta(minutes=1)] if m is not None else None

    def bars_1m(self, ticker):
        return self._finished(ticker)

    def _bar(self, ticker):
        b = self._finished(ticker)
        return b.iloc[-1] if b is not None and len(b) else None

    def quote(self, ticker):
        b = self._bar(ticker)
        if b is None:
            return None
        qt = pd.Timestamp(self.clock()) - pd.Timedelta(seconds=1)
        c = float(b["Close"])
        return {"bid": round(c - 0.01, 2), "ask": round(c + 0.01, 2), "last": c, "quote_time": qt, "trade_time": qt, "src": self.name}

    def _q(self, ticker, side, strike, symbol=None):
        b = self._bar(ticker)
        if b is None:
            return None
        now = self.clock()
        iv = self.iv_by_symbol.get(symbol, self.iv)
        mid, d, g, th = bs(float(b["Close"]), strike, iv, side, now)
        sp = model_spread(mid)
        bid, ask = mid - sp / 2, mid + sp / 2
        if self.mode == "adverse":       # the worst price inside the minute for a holder: stops count first
            worst = float(b["Low"] if side == "C" else b["High"])
            wmid = bs(worst, strike, iv, side, now)[0]
            bid = min(bid, wmid - sp / 2)
        return {"bid": round(max(bid, 0.01), 2), "ask": round(max(ask, 0.02), 2), "mid": round(mid, 3), "delta": round(d, 3),
                "gamma": round(g, 4), "theta": round(th * 60, 4), "iv": iv, "quote_time": pd.Timestamp(now) - pd.Timedelta(seconds=1),
                "bid_size": 100, "ask_size": 100, "multiplier": 100, "src": self.name}

    def option_quote(self, symbol):
        tk, side, strike = symbol[:-15], symbol[-9], int(symbol[-8:]) / 1000
        q = self._q(tk, side, strike, symbol)
        return (q, None) if q else (None, "no bar yet")

    def chain(self, ticker, side, first, through=None):
        b = self._bar(ticker)
        if b is None:
            return [], "no bar yet"
        s0 = round(float(b["Close"]))
        rows = []
        for k in range(s0 - 6, s0 + 7):
            sym = f"{ticker}{first[2:4]}{first[5:7]}{first[8:10]}{side[0].upper()}{int(k * 1000):08d}"
            q = self._q(ticker, side[0].upper(), float(k), sym)
            rows.append({"symbol": sym, "strike": float(k), "bid": q["bid"], "ask": q["ask"], "ts": None, "delta": q["delta"],
                         "gamma": q["gamma"], "theta": q["theta"], "iv": q["iv"], "exp": first, "feed": self.name})
        return rows, None


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


# ---------------------------------------------------------------- data
def load_bars(source, day, csv=None):
    if csv:
        df = pd.read_csv(csv)
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(ET)
        src = (Path(csv).stem.split("_")[-1] if "_" in Path(csv).stem else "csv")
        return {t: g.set_index("ts")[["Open", "High", "Low", "Close", "Volume"]].sort_index() for t, g in df.groupby("ticker")}, src
    start = datetime.combine(day - timedelta(days=21), datetime.min.time(), ET)
    end = datetime.combine(day, datetime.min.time(), ET).replace(hour=20)
    out = {}
    for t in core.policy()["instruments"]:
        if source == "schwab":
            import schwab
            if not schwab.ready():
                raise SystemExit("Schwab is not connected. Connect it on the Rules page, or use --source yahoo (research only) or --csv.")
            df = schwab.bars_1m_range(t, start, end)
        else:
            import yfinance as yf
            df = yf.Ticker(t).history(start=(day - timedelta(days=7)).isoformat(), end=(day + timedelta(days=1)).isoformat(),
                                      interval="1m", prepost=True, auto_adjust=False)
            if df is not None and len(df):
                df.index = df.index.tz_convert(ET)
                df = df[["Open", "High", "Low", "Close", "Volume"]]
        if df is None or not len(df):
            raise SystemExit(f"No 1m bars for {t} from {source}.")
        out[t] = df.sort_index()
    return out, source


def save_bars(m1s, day, src):
    REPORTS.mkdir(exist_ok=True)
    rows = []
    for t, df in m1s.items():
        d = df.copy()
        d["ticker"] = t
        d["ts"] = d.index.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append(d[["ts", "ticker", "Open", "High", "Low", "Close", "Volume"]])
    path = REPORTS / f"replay_bars_{day}_{src}.csv"
    pd.concat(rows).to_csv(path, index=False)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def data_check(m1s, day):
    out = {}
    for t, df in m1s.items():
        today = df[df.index.date == day]
        rth = today.between_time("09:30", "15:59")
        exp = pd.date_range(datetime.combine(day, datetime.min.time(), ET).replace(hour=9, minute=30), periods=390, freq="1min")
        missing = [x.strftime("%H:%M") for x in exp if x not in rth.index]
        out[t] = {"bars_total": len(df), "sessions": len(set(df.index.date)), "rth_bars_today": len(rth), "missing_rth_minutes": missing[:20],
                  "missing_count": len(missing), "first": str(df.index[0]), "last": str(df.index[-1]),
                  "duplicates": int(df.index.duplicated().sum())}
    return out


# ---------------------------------------------------------------- sandbox
@contextlib.contextmanager
def sandbox(provider, clock):
    """Fresh temp database + replay provider + replay clock. Nothing touches the live desk."""
    import engine
    tmp = Path(tempfile.mkdtemp(prefix="replay_"))
    saved = (store.DB, store._conn, core.now_et, marketdata._provider, core.EVENTS_FILE)
    store.DB, store._conn = tmp / "replay.db", None
    core.EVENTS_FILE = tmp / "events.json"         # the replayed day's calendar wasn't recorded: state "unknown"
    core.now_et = clock
    marketdata.use(provider)
    engine._cache.clear()
    try:
        yield
    finally:
        try:
            if store._conn:
                store._conn.close()
        except Exception:
            pass
        store.DB, store._conn, core.now_et, core.EVENTS_FILE = saved[0], saved[1], saved[2], saved[4]
        marketdata.use(saved[3])
        engine._cache.clear()
        shutil.rmtree(tmp, ignore_errors=True)


def at(day, hhmm, sec=5):
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(day, datetime.min.time(), ET).replace(hour=h, minute=m, second=sec)


# ---------------------------------------------------------------- full-day engine replay
def run_day(m1s, day, src, mode, iv, until="16:06"):
    import engine
    clock = Clock(at(day, "09:30"))
    prov = ReplayProvider(m1s, clock, src, iv, mode)
    with sandbox(prov, clock):
        t, stop = at(day, "09:30"), at(day, until)
        while t <= stop:
            clock.t = t
            engine._cache.clear()
            engine.tick()
            t += timedelta(minutes=1)
        res = {"mode": mode, "ledgers": {}, "candidates": {}, "conflicts": [], "events_tail": []}
        for led in ("paper", "research", "old"):
            pos = store.q("SELECT * FROM positions WHERE ledger=? ORDER BY opened", (led,))
            trades = []
            for p in pos:
                o = store.q("SELECT ts, side, qty, filled_price, reason FROM orders WHERE position_id=? ORDER BY ts", (p["id"],))
                pl = json.loads(p["plan"]) if isinstance(p["plan"], str) else p["plan"]
                trades.append({"id": p["id"], "ticker": p["ticker"], "contract": p["contract"], "qty": p["qty_init"], "fill": p["fill"],
                               "opened": p["opened"][11:16], "closed": (p["closed"] or "")[11:16], "status": p["status"],
                               "realized": round(p["realized"] or 0, 2), "setup": p["setup"], "grade": p["grade"],
                               "entry_mode": (pl or {}).get("entry_mode"), "mfe_pct": p["mfe"], "mae_pct": p["mae"],
                               "exits": [f"{x['ts'][11:16]} {x['side']} {x['qty']} @ {x['filled_price']:.2f} {x['reason'] or ''}" for x in o if x["side"] == "sell"]})
            closed = [x for x in trades if x["status"] == "CLOSED"]
            res["ledgers"][led] = {"trades": trades, "n": len(closed), "net": round(sum(x["realized"] for x in closed), 2),
                                   "wins": sum(1 for x in closed if x["realized"] > 1), "losses": sum(1 for x in closed if x["realized"] < -1)}
        rows = store.q("SELECT portfolio, decision, family, side, ticker, decision_t, reasons, limit_blocked FROM candidates ORDER BY decision_t")
        for r in rows:
            k = res["candidates"].setdefault(r["portfolio"], {"total": 0, "by_decision": {}, "by_family": {}, "reasons": {}})
            k["total"] += 1
            k["by_decision"][r["decision"]] = k["by_decision"].get(r["decision"], 0) + 1
            k["by_family"][r["family"]] = k["by_family"].get(r["family"], 0) + 1
            for why in (json.loads(r["reasons"] or "[]") + ([r["limit_blocked"]] if r["limit_blocked"] else [])):
                key = re.split(r"[:(]", why)[0].strip()[:60]
                k["reasons"][key] = k["reasons"].get(key, 0) + 1
            if r["decision"] == "SKIP-CONFLICT":
                res["conflicts"].append(f"{(r['decision_t'] or '')[11:16]} {r['ticker']} {r['family']} {r['side']}")
        res["events_tail"] = [f"{e['ts'][11:19]} {e['text'][:160]}" for e in store.q("SELECT ts, text FROM events WHERE kind IN ('opportunity','paper_open','paper_close','research','old','alert') ORDER BY seq")][-60:]
    return res


# ---------------------------------------------------------------- original records
def originals(db_path, day):
    if not db_path or not Path(db_path).exists():
        return None
    tmp = Path(tempfile.mkdtemp()) / "orig.db"
    shutil.copy(db_path, tmp)                      # read a copy: the live file is never opened for writing
    c = sqlite3.connect(tmp)
    c.row_factory = sqlite3.Row
    pos = [dict(r) for r in c.execute("SELECT * FROM positions WHERE date=? ORDER BY opened", (str(day),))]
    for p in pos:
        p["orders"] = [dict(r) for r in c.execute("SELECT * FROM orders WHERE position_id=? ORDER BY ts", (p["id"],))]
        try:
            p["plan"] = json.loads(p["plan"]) if p.get("plan") else {}
        except ValueError:
            p["plan"] = {}
    c.close()
    tot = {}
    for p in pos:
        if p["status"] == "CLOSED":
            t = tot.setdefault(p["ledger"], {"positions": 0, "contracts": 0, "net": 0.0, "wins": 0})
            t["positions"] += 1
            t["contracts"] += p["qty_init"] or 0
            t["net"] = round(t["net"] + (p["realized"] or 0), 2)
            t["wins"] += (p["realized"] or 0) > 0
    return {"positions": pos, "totals": tot}


def solve_iv(spot, strike, side, now, target_mid):
    lo, hi = 0.02, 3.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if bs(spot, strike, mid, side, now)[0] > target_mid:
            hi = mid
        else:
            lo = mid
    return round((lo + hi) / 2, 4)


def replay_trade(rec, m1s, day, src, mode):
    """Re-manage one original entry (same contract, time, fill, size) under the frozen old exits and the v3 exits."""
    import engine
    import exits
    import optionmath
    import paper
    import policy_old
    tk, sym, side = rec["ticker"], rec["symbol"], rec["side"]
    if tk not in m1s or not sym:
        return {"id": rec["id"], "skipped": f"no bars loaded for {tk}" if tk not in m1s else "no contract symbol recorded"}
    opened = datetime.fromisoformat(rec["opened"]).astimezone(ET)
    t0 = opened.replace(second=5, microsecond=0) + (timedelta(minutes=1) if opened.second > 5 else timedelta(0))
    clock = Clock(t0)
    prov = ReplayProvider(m1s, clock, src, 0.18, mode)
    strike = int(sym[-8:]) / 1000
    out = {"id": rec["id"], "ledger": rec["ledger"], "contract": rec["contract"], "symbol": sym, "qty": rec["qty_init"],
           "fill": rec["fill"], "opened": opened.strftime("%H:%M:%S"), "recorded_realized": rec["realized"], "mode": mode}
    with sandbox(prov, clock):
        b = prov._bar(tk)
        spot = float(b["Close"])
        sp = model_spread(rec["fill"])
        iv = solve_iv(spot, strike, side, t0, rec["fill"] - sp / 2 - 0.01)
        prov.iv_by_symbol[sym] = iv
        out["iv_solved_from_fill"] = iv
        snap = engine.snapshot(tk)
        v3 = snap.get("v3") or {}
        inv = (rec["plan"] or {}).get("invalidation")
        if inv is None and v3.get("ok"):                   # no recorded structure: v3 would use the nearest level behind entry
            lv = sorted([l["value"] for l in v3["levels"].values() if l.get("value") is not None and
                         ((l["value"] < spot) if side == "C" else (l["value"] > spot))], key=lambda v: abs(v - spot))
            inv = (lv[0] - v3["buf"]) if (lv and side == "C") else (lv[0] + v3["buf"]) if lv else None
            out["invalidation_note"] = "none recorded: used the nearest level behind the entry"
        out["invalidation"] = round(inv, 2) if inv is not None else None
        q, _ = prov.option_quote(sym)
        row = {"symbol": sym, "strike": strike, "bid": q["bid"], "ask": q["ask"], "delta": q["delta"], "gamma": q["gamma"],
               "theta": q["theta"], "iv": iv}
        tp, why, diag = (optionmath.plan_trade({"side": side, "invalidation": inv}, v3, [row], "A") if inv is not None and v3.get("ok")
                         else (None, "no invalidation or no snapshot", {}))
        out["v3_entry_verdict"] = "would qualify (R/R and 20% ceiling pass)" if tp else f"v3 would SKIP this entry: {why}"
        if diag.get("tried"):
            out["v3_entry_math"] = {k: diag["tried"][-1].get(k) for k in ("loss_c", "gain_c", "ceiling_c", "rr_option")} | {"rr_underlying": diag.get("rr_underlying")}
        if not tp:                                          # still show how v3 EXITS would have managed it
            t1 = optionmath.pick_t1(v3, side, spot, inv) if v3.get("ok") and inv is not None else None
            fee = paper.costs(q["ask"] - q["bid"])[1]
            tp = {"symbol": sym, "label": rec["contract"], "premium_stop": core.cents_up(rec["fill"] * 0.8 + 2 * fee / 100),
                  "stop_px": inv, "t1": t1[0] if t1 else None, "t1_level": t1[1] if t1 else None, "t1_px": t1[2] if t1 else None,
                  "be_trigger": core.cents_up(rec["fill"] * 1.10 + 2 * fee / 100), "breakeven_net": core.cents_up(rec["fill"] + 2 * fee / 100)}
        plan = dict(tp, family=rec.get("setup"), flat_by=(t0 + timedelta(minutes=(core.window_for(core.hm(t0)) or {"flat_min": 5})["flat_min"])).strftime("%H:%M"))
        paper.reserve_idea("paper", "NEW", tk, side)
        pid_new, err = paper.buy("paper", "NEW", tk, side, plan, rec["qty_init"], t0.isoformat())
        pn = store.pos_get(pid_new)
        pn["fill"] = rec["fill"]
        pn["plan"]["entry_premium"] = rec["fill"]
        pn["plan"]["t1_px"] = pn["plan"].get("t1_px")
        store.pos_save(pn)
        ex = policy_old.exit_plan(rec["fill"], core.hm(t0), q["ask"] - q["bid"])
        pold = {"id": "OL-ORIG", "ledger": "old", "date": str(day), "ticker": tk, "contract": rec["contract"], "symbol": sym, "side": side,
                "qty_init": rec["qty_init"], "qty_open": rec["qty_init"], "fill": rec["fill"], "opened": t0.isoformat(), "closed": None,
                "status": "OPEN", "setup_id": "ORIG", "grade": rec.get("grade"), "setup": rec.get("setup"),
                "plan": dict(ex, v=2, invalidation=inv if inv is not None else (0 if side == "C" else 10 ** 6), be_hit=False, t1_done=False, trail=None, last_bid=q["bid"]),
                "realized": 0.0, "mfe": 0, "mae": 0, "policy_version": "old", "verified": "replay", "notes": ""}
        store.pos_save(pold)
        peak = {"bid": q["bid"], "bid_t": t0.strftime("%H:%M"), "mid": q["mid"], "mid_t": t0.strftime("%H:%M")}
        t = t0
        while t <= at(day, "15:27"):
            clock.t = t
            engine._cache.clear()
            q, _ = prov.option_quote(sym)
            if q and q["bid"] > peak["bid"]:
                peak.update(bid=q["bid"], bid_t=t.strftime("%H:%M"))
            if q and q["mid"] > peak["mid"]:
                peak.update(mid=q["mid"], mid_t=t.strftime("%H:%M"))
            s = engine.snapshot(tk)
            for pid in (pid_new, "OL-ORIG"):
                p = store.pos_get(pid)
                if p and p["status"] == "OPEN":
                    if pid == pid_new:
                        exits.evaluate(p, s.get("v3") or {})
                    else:
                        policy_old.manage(p, s, lambda x: prov.option_quote(x))
            if all(store.pos_get(x)["status"] != "OPEN" for x in (pid_new, "OL-ORIG")):
                break
            t += timedelta(minutes=1)
        out["peak_executable_bid"] = peak["bid"]
        out["peak_bid_time"] = peak["bid_t"]
        out["peak_marked_mid"] = round(peak["mid"], 2)
        out["peak_mid_time"] = peak["mid_t"]
        out["mfe_pct_executable"] = round((peak["bid"] / rec["fill"] - 1) * 100, 1)
        for key, pid in (("old_rules", "OL-ORIG"), ("v3_rules", pid_new)):
            p = store.pos_get(pid)
            sells = store.q("SELECT ts, qty, filled_price, reason FROM orders WHERE position_id=? AND side='sell' ORDER BY ts", (pid,))
            fee = paper.costs(0.02)[1]
            gross = sum((x["filled_price"] - rec["fill"]) * 100 * x["qty"] for x in sells)
            costs = round(fee * (rec["qty_init"] + sum(x["qty"] for x in sells)), 2)
            best = (peak["bid"] - rec["fill"]) * 100 * rec["qty_init"]
            out[key] = {"exits": [f"{x['ts'][11:16]} sell {x['qty']} @ {x['filled_price']:.2f}: {x['reason']}" for x in sells],
                        "status": p["status"], "pnl_modeled": round(gross - costs, 2), "costs": costs,
                        "giveback_from_peak": round(best - gross, 2) if sells else None,
                        "runner_contribution": (round(sum((x["filled_price"] - rec["fill"]) * 100 * x["qty"] for x in sells[1:]), 2)
                                                if (p["plan"] or {}).get("runner") and len(sells) > 1 else None)}
            if key == "old_rules":
                out[key]["old_plan"] = {k: ex.get(k) for k in ("window", "stop", "be_trigger", "t1", "flat_by")}
    return out


# ---------------------------------------------------------------- report
def fmt_money(v):
    return "n/a" if v is None else (f"+${v:.2f}" if v > 0 else f"-${abs(v):.2f}" if v < 0 else "$0.00")


def report(day, src, sha, path, check, orig, days, trades):
    L = [f"# Replay {day}", "",
         "Regression case only. This day was used to design v3, so it cannot show that v3 works. The forward paper test does that.", "",
         "## Data", "",
         f"- Underlying 1m bars: **{src}**" + (" (research-only fallback: Yahoo is not an executable broker feed)" if src == "yahoo" else ""),
         f"- Saved as `{path.name}`, sha256 `{sha[:16]}...`. Rerun with `--csv` for identical numbers.",
         "- Option quotes: **MODELED** (Black-Scholes on the real underlying, modeled spread). No historical option bid/ask exist here, so no option P&L below is an observed fill.",
         "- Two runs: **close** (quotes at each finished 1m close) and **adverse** (bid at the worst price inside each minute, so a bar that touched both stop and target counts as the stop).", ""]
    for t, c in check.items():
        L.append(f"- {t}: {c['rth_bars_today']}/390 regular-session bars, {c['missing_count']} missing" +
                 (f" ({', '.join(c['missing_rth_minutes'][:8])}...)" if c["missing_count"] else "") + f", {c['sessions']} sessions loaded, {c['duplicates']} duplicates")
    L += ["", "## Original records (from the desk database)", ""]
    if not orig:
        L.append("Not available: pass `--db` with the desk database to compare against what actually happened.")
    else:
        L += ["| Ledger | Opened | Contract | Symbol | Qty | Fill | Realized | Setup | Orders |", "|---|---|---|---|---|---|---|---|---|"]
        for p in orig["positions"]:
            L.append(f"| {p['ledger']} | {(p['opened'] or '')[11:16]} | {p['contract']} | {p.get('symbol') or ''} | {p['qty_init']} | {p['fill']} | "
                     f"{fmt_money(p['realized'])} | {p.get('setup') or ''} | {len(p['orders'])} |")
        L.append("")
        for led, t in orig["totals"].items():
            L.append(f"- {led}: {t['positions']} closed positions, {t['contracts']} contracts, {t['wins']} wins, net {fmt_money(t['net'])}")
    for d in days:
        L += ["", f"## v3 engine over the day ({d['mode']} quotes)", ""]
        for led, name in (("paper", "Main paper"), ("research", "Research"), ("old", "Old rules (frozen)")):
            g = d["ledgers"][led]
            L.append(f"**{name}**: {g['n']} closed trades, {g['wins']} wins, {g['losses']} losses, net {fmt_money(g['net'])} (MODELED)")
            for x in g["trades"]:
                L.append(f"- {x['opened']} {x['ticker']} {x['contract']} x{x['qty']} @ {x['fill']:.2f} {x['setup']} {x['grade'] or ''}"
                         f"{' (' + x['entry_mode'] + ')' if x.get('entry_mode') else ''} -> {fmt_money(x['realized'])}; " + "; ".join(x["exits"]))
            L.append("")
        for pf, k in d["candidates"].items():
            top = sorted(k["reasons"].items(), key=lambda z: -z[1])[:6]
            L.append(f"- {pf} candidates: {k['total']} ({', '.join(f'{a} {b}' for a, b in k['by_decision'].items())}); top reasons: " +
                     "; ".join(f"{a} ({b})" for a, b in top))
        if d["conflicts"]:
            L.append(f"- Bars skipped because calls and puts fired together: {', '.join(d['conflicts'][:10])}")
    L += ["", "## Original entries re-managed: old exits vs v3 exits", "",
          "Same contract, time, size and fill as the record. Volatility solved from the actual fill. All option prices MODELED.", ""]
    for r in trades:
        if r.get("skipped"):
            L.append(f"- {r['id']}: not replayed ({r['skipped']})")
            continue
        L += [f"### {r['ledger']} {r['contract']} x{r['qty']} at {r['fill']:.2f}, {r['opened']} ({r['mode']} quotes)", "",
              f"- Recorded result: {fmt_money(r['recorded_realized'])}. IV solved from the fill: {r['iv_solved_from_fill']}.",
              f"- {r['v3_entry_verdict']}" + (f" (stressed loss ${r['v3_entry_math']['loss_c']}, ceiling ${r['v3_entry_math']['ceiling_c']}, "
                                               f"option R/R {r['v3_entry_math']['rr_option']}, stock R/R {r['v3_entry_math']['rr_underlying']})" if r.get("v3_entry_math") else ""),
              f"- Invalidation used: {r['invalidation']}" + (f" ({r['invalidation_note']})" if r.get("invalidation_note") else ""),
              f"- Peak executable bid {r['peak_executable_bid']:.2f} at {r['peak_bid_time']} (+{r['mfe_pct_executable']}%), peak marked mid {r['peak_marked_mid']:.2f} at {r['peak_mid_time']}"]
        for key, name in (("old_rules", "Old rules"), ("v3_rules", "v3 rules")):
            g = r[key]
            gb = g["giveback_from_peak"]
            L.append(f"- {name}: {fmt_money(g['pnl_modeled'])} after ${g['costs']:.2f} costs"
                     + (f", gave back ${gb:.2f} of the best executable value" if gb is not None and gb > 0 else "")
                     + (f", runner {fmt_money(g['runner_contribution'])}" if g["runner_contribution"] is not None else ", no runner kept")
                     + ". " + ("; ".join(g["exits"]) or "no exit"))
        L.append("")
    L += ["## Limits", "",
          "- One day, overlapping setups, used for design: not evidence of an edge.",
          "- Option prices are modeled; the real spread, IV changes and fills on the day are unknown.",
          "- Decisions run once per finished minute; anything that happened inside a minute is only seen through the adverse run.",
          "- News/event state was not recorded for the replayed day, so it is treated as unknown (the desk asks for caution then)."]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("date")
    ap.add_argument("--source", choices=["schwab", "yahoo"], default="schwab")
    ap.add_argument("--csv")
    ap.add_argument("--db", default=str(HERE / "journal" / "desk.db"))
    ap.add_argument("--iv", type=float, default=0.18)
    ap.add_argument("--until", default="16:06")
    ap.add_argument("--modes", default="close,adverse")
    a = ap.parse_args(argv)
    day = datetime.strptime(a.date, "%Y-%m-%d").date()
    orig = originals(a.db, day) if a.db else None
    m1s, src = load_bars(a.source, day, a.csv)
    path, sha = save_bars(m1s, day, src) if not a.csv else (Path(a.csv), hashlib.sha256(Path(a.csv).read_bytes()).hexdigest())
    check = data_check(m1s, day)
    modes = [m for m in a.modes.split(",") if m]
    days = [run_day(m1s, day, src, m, a.iv, a.until) for m in modes]
    trades = []
    for p in (orig or {}).get("positions", []):
        if p["ledger"] in ("paper", "real") and p.get("fill"):
            for m in modes:
                trades.append(replay_trade(copy.deepcopy(p), m1s, day, src, m))
    md = report(day, src, sha, path, check, orig, days, trades)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"replay_{day}.md").write_text(md)
    (REPORTS / f"replay_{day}.json").write_text(json.dumps({"day": str(day), "source": src, "sha256": sha, "data": check,
                                                             "original": {"totals": (orig or {}).get("totals")}, "days": days, "trades": trades},
                                                            indent=1, default=str))
    print(md)
    print(f"\nWrote {REPORTS / f'replay_{day}.md'}")
    return days, trades


if __name__ == "__main__":
    main()
