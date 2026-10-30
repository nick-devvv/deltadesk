"""exits.py - v3 position state machine (persisted in the position's plan; each action happens at most once).

Order of precedence each evaluation (only the FIRST matching full/partial action is taken this tick):
  1. session liquidation (all-out time, earlier on early-close days)
  2. hard protective premium stop (20% ceiling, or the raised breakeven / locked-profit stop)
  3. structural invalidation (finalized 1m underlying close beyond the stop level)
  4. full exits: momentum (GREEN only: 3 adverse 2m histogram changes or an opposing MACD cross),
     stall (GREEN only: no meaningful new premium high for stall_min), T1 rejection, old if-flat timer for
     trades that are NOT green (the 10-minute green timer never gives a loser more time)
  5. T1 reached: 2+ contracts -> sell 1; keep the rest only after a clean break (1m close beyond T1 + zone) with
     aligned momentum, otherwise close it. 1 contract -> full exit at T1.
  6. updates (no order): breakeven move, profit lock, runner trail. Stops only ratchet toward protection.
'green' = conservative liquidation value (bid - slippage - exit fees) above the remaining cost basis.
Stale or missing quotes never advance the stall timer, never count as a stall and never produce a fill.
For REAL positions nothing is executed: the desk alerts and waits for Nick's reported fill.
"""
from datetime import datetime, timedelta

import pandas as pd

import core
import indicators as I
import marketdata
import paper
import store


def _c():
    return core.policy()["v3"]["exits"]


def evaluate(p, snap):
    """Returns the list of (kind, qty, reason) decided this tick (also applied for paper/research)."""
    pl = p["plan"]
    if pl.get("v") != 3 or pl.get("manual"):
        return []
    now = core.now_et()
    sess = core.session_info(now)
    up = p["side"] == "C"
    q, err = marketdata.option_quote(p["symbol"])
    fresh = bool(q and q.get("executable"))
    acts = []
    if fresh:
        bid = q["bid"]
        pl["last_bid"], pl["last_ask"], pl["quote_age_s"] = bid, q["ask"], q.get("age_s")
        move = (bid - p["fill"]) / p["fill"] * 100
        p["mfe"], p["mae"] = round(max(p["mfe"] or 0, move), 1), round(min(p["mae"] or 0, move), 1)
        noise = max(_c()["noise_min"], _c()["noise_pct"] * p["fill"])
        if bid > (pl.get("high_water") or 0) + noise:
            pl["high_water"], pl["high_water_t"], pl["last_progress_t"] = bid, store.ts(), store.ts()
        slip, fee = paper.costs(q["ask"] - bid)
        liq = (bid - slip) * 100 * p["qty_open"] - fee * p["qty_open"]
        basis = p["fill"] * 100 * p["qty_open"]
        green = liq > basis
    else:
        bid, green = None, False
        _once(p, "noquote", f"{_who(p)} {p['contract']}: no executable option quote ({err or ', '.join((q or {}).get('problems') or [])}); "
              "protection waits for a valid quote, no fill is invented", "error")
    pl["green"] = green
    b1 = snap["r1"] if snap.get("ok") else None
    c1 = float(b1["Close"].iloc[-1]) if b1 is not None and len(b1) else None
    z = snap.get("zone", 0.03)
    # 1. session
    if now.strftime("%H:%M") >= sess["all_out"]:
        acts.append(("exit", p["qty_open"], f"ALL OUT {sess['all_out']} (session rule)"))
    # 2. hard protective premium stop
    elif fresh and bid <= pl["premium_stop"]:
        kind = "LOCKED-PROFIT STOP" if pl.get("lock_hit") else "BREAKEVEN STOP" if pl.get("be_hit") else "PREMIUM STOP (20% ceiling)"
        acts.append(("exit", p["qty_open"], f"{kind} ${pl['premium_stop']:.2f} hit (bid {bid:.2f})"))
    # 3. structural invalidation on a finalized 1m close
    elif c1 is not None and pl.get("stop_px") is not None and ((c1 < pl["stop_px"]) if up else (c1 > pl["stop_px"])):
        acts.append(("exit", p["qty_open"], f"STRUCTURE BROKEN: 1m close {c1:.2f} beyond {pl['stop_px']:.2f}"))
    elif fresh and pl.get("exit_profile") == "v31":
        acts += _v31(p, pl, snap, now, up, bid, green, b1, c1)
    elif fresh:
        # 4. full exits
        H, M, S = snap.get("hist"), snap.get("macd"), snap.get("signal")
        fading = I.hist_fading(H, p["side"]) if H is not None and len(H) else None
        cross = I.macd_cross(M, S) if M is not None and len(M) else None
        opposing = cross == ("down" if up else "up")
        stall_min = _c()["stall_min"]
        since = datetime.fromisoformat(pl["last_progress_t"])
        stalled = (now - since) >= timedelta(minutes=stall_min)
        has_t1 = pl.get("t1_px") is not None
        t1_hit = has_t1 and c1 is not None and ((c1 >= pl["t1_px"]) if up else (c1 <= pl["t1_px"]))
        touched_t1 = pl.get("t1_touched")
        if has_t1 and b1 is not None and len(b1):
            hi, lo = float(b1["High"].iloc[-1]), float(b1["Low"].iloc[-1])
            if (hi >= pl["t1_px"]) if up else (lo <= pl["t1_px"]):
                pl["t1_touched"] = touched_t1 = True
        rejected = touched_t1 and not t1_hit and c1 is not None and ((c1 < pl["t1_px"] - z) if up else (c1 > pl["t1_px"] + z))
        if green and (fading or opposing):
            acts.append(("exit", p["qty_open"], "MOMENTUM EXIT while green: " +
                         ("MACD crossed against the trade" if opposing else "3 adverse 2m histogram changes")))
        elif green and stalled:
            acts.append(("exit", p["qty_open"], f"STALL EXIT: green but no new premium high for {stall_min} min "
                                                f"(best bid {pl['high_water']:.2f} at {pl['high_water_t'][11:16]})"))
        elif rejected and not pl.get("t1_done"):
            acts.append(("exit", p["qty_open"], f"T1 REJECTED at {pl['t1']} {pl['t1_level']:.2f}: 1m close back to {c1:.2f}"))
        elif not green and not pl.get("be_hit") and pl.get("flat_by") and now.strftime("%H:%M") >= pl["flat_by"]:
            acts.append(("exit", p["qty_open"], f"IF FLAT: not green by {pl['flat_by']} (old no-progress rule kept for losers)"))
        # 5. T1
        elif t1_hit and not pl.get("t1_done"):
            pl["t1_done"] = True
            if p["qty_open"] >= 2:
                acts.append(("exit", 1, f"T1 {pl['t1']} {pl['t1_level']:.2f} reached: sell 1 of {p['qty_open']}"))
                clean = (c1 >= pl["t1_level"] + z) if up else (c1 <= pl["t1_level"] - z)
                aligned = I.macd_state(M, S) == ("bull" if up else "bear") and not fading
                if clean and aligned:
                    pl["runner"] = True
                    pl["trail"] = _swing(b1, p["side"])
                    _ratchet(p, max(pl["premium_stop"], pl.get("breakeven_net", p["fill"])), "runner: stop to cost-aware breakeven")
                else:
                    pl["close_rest_reason"] = "no clean break of T1 with aligned momentum"
            else:
                acts.append(("exit", p["qty_open"], f"T1 {pl['t1']} {pl['t1_level']:.2f} reached: full exit (1 contract)"))
        elif pl.get("t1_done") and pl.get("close_rest_reason") and p["qty_open"] > 0:
            acts.append(("exit", p["qty_open"], f"close the rest after T1: {pl['close_rest_reason']}"))
        else:
            # 6. updates
            if not pl.get("be_hit") and bid >= pl["be_trigger"]:
                pl["be_hit"] = True
                _ratchet(p, pl["breakeven_net"], f"breakeven: bid {bid:.2f} reached the +{int(_c()['be_trigger_pct'] * 100)}% trigger")
            lock_t = p["fill"] * (1 + _c()["lock_trigger_pct"])
            if not pl.get("lock_hit") and bid >= lock_t:
                pl["lock_hit"] = True
                _ratchet(p, core.cents_up(p["fill"] * (1 + _c()["lock_keep_pct"])),
                         f"profit lock: +{int(_c()['lock_trigger_pct'] * 100)}% reached, lock +{int(_c()['lock_keep_pct'] * 100)}%")
            if pl.get("runner") and b1 is not None:
                sw = _swing(b1, p["side"])
                if sw is not None and (pl["trail"] is None or ((sw > pl["trail"]) if up else (sw < pl["trail"]))):
                    pl["trail"] = sw
                if pl["trail"] is not None and c1 is not None and ((c1 < pl["trail"]) if up else (c1 > pl["trail"])):
                    acts.append(("exit", p["qty_open"], f"TRAIL: 1m close {c1:.2f} through the swing {pl['trail']:.2f}"))
    if p["ledger"] == "real":
        prev = (pl.get("guidance") or {}).get("action")
        pl["guidance"] = guidance(p, acts, fresh, bid, green, c1, now)
        act = pl["guidance"]["action"]
        if act != prev and act not in ("HOLD",) and not (act == "NO DATA" and prev == "NO DATA"):
            try:
                import alerts
                alerts.alert("mytrades", f"YOUR {p['ticker']} {p['contract']}: {act}",
                             " | ".join(pl["guidance"]["why"][:3]) + f" | stop {pl['guidance']['plan']['stop']}"
                             " | advice only: you place the order in Robinhood", f"guide:{p['id']}:{act}:{now.strftime('%H%M')}",
                             "high" if act.startswith(("EXIT", "TAKE")) else "normal")
            except Exception:
                pass
    store.pos_save(p)
    res = _apply(p, acts)
    if acts and acts[0][2].startswith("T1") and not res:   # the partial didn't fill (no valid quote): try again next tick
        pl["t1_done"] = False
        pl["runner"] = False if pl.get("exit_profile") == "v31" else pl.get("runner")
        store.pos_save(p)
    return res


# ---------------------------------------------------------------- v3.1 exits (research variant 'exit31')
def _v31cfg():
    return (core.policy().get("research_variants") or {}).get("exit31") or {}


def _v31(p, pl, snap, now, up, bid, green, b1, c1):
    """v3.1 research exits. Before T1: only the hard stops (handled above), a 15-minute if-flat for trades that never
    went green, and the breakeven/lock ratchets. No stall or momentum exit before T1, so a trade gets room to work.
    At T1: 2+ contracts sell 1; the rest (or the single contract) becomes a runner with the stop at cost-aware
    breakeven. Runner: trails the tighter of the last 1m swing and VWAP, exits on a 1m close through it, an opposing
    2m MACD cross, or no new premium high for runner_stall_min. Session and premium stops still come first."""
    acts = []
    k = _v31cfg()
    M, S = snap.get("macd"), snap.get("signal")
    cross = I.macd_cross(M, S) if M is not None and len(M) else None
    opposing = cross == ("down" if up else "up")
    t1_hit = pl.get("t1_px") is not None and c1 is not None and ((c1 >= pl["t1_px"]) if up else (c1 <= pl["t1_px"]))
    if not pl.get("t1_done"):
        if t1_hit:
            pl["t1_done"], pl["runner"] = True, True
            pl["trail"] = _trail_level(b1, p["side"], snap.get("vwap"), None)
            _ratchet(p, max(pl["premium_stop"], pl.get("breakeven_net", p["fill"])), "v3.1 at T1: stop to cost-aware breakeven, the rest runs")
            if p["qty_open"] >= 2:
                acts.append(("exit", 1, f"T1 {pl['t1']} {pl['t1_level']:.2f} reached: sell 1 of {p['qty_open']}, trail the rest (v3.1)"))
        elif not green and not pl.get("be_hit") and pl.get("flat_by") and now.strftime("%H:%M") >= pl["flat_by"]:
            acts.append(("exit", p["qty_open"], f"IF FLAT: never green by {pl['flat_by']} (v3.1: {k.get('flat_min', 15)} min)"))
        else:
            _protect(p, pl, bid)
        return acts
    pl["trail"] = _trail_level(b1, p["side"], snap.get("vwap"), pl.get("trail"))
    stall = int(k.get("runner_stall_min", 15))
    stalled = (now - datetime.fromisoformat(pl["last_progress_t"])) >= timedelta(minutes=stall)
    if pl["trail"] is not None and c1 is not None and ((c1 < pl["trail"]) if up else (c1 > pl["trail"])):
        acts.append(("exit", p["qty_open"], f"TRAIL (v3.1): 1m close {c1:.2f} through {pl['trail']:.2f} (swing/VWAP)"))
    elif opposing:
        acts.append(("exit", p["qty_open"], "MOMENTUM EXIT (v3.1 runner): MACD crossed against the trade"))
    elif stalled:
        acts.append(("exit", p["qty_open"], f"STALL EXIT (v3.1 runner): no new premium high for {stall} min"))
    else:
        _protect(p, pl, bid)
    return acts


def _protect(p, pl, bid):
    if not pl.get("be_hit") and bid >= pl["be_trigger"]:
        pl["be_hit"] = True
        _ratchet(p, pl["breakeven_net"], f"breakeven: bid {bid:.2f} reached the +{int(_c()['be_trigger_pct'] * 100)}% trigger")
    lock_t = p["fill"] * (1 + _c()["lock_trigger_pct"])
    if not pl.get("lock_hit") and bid >= lock_t:
        pl["lock_hit"] = True
        _ratchet(p, core.cents_up(p["fill"] * (1 + _c()["lock_keep_pct"])),
                 f"profit lock: +{int(_c()['lock_trigger_pct'] * 100)}% reached, lock +{int(_c()['lock_keep_pct'] * 100)}%")


def _trail_level(b1, side, vwap, prev):
    """Tighter of the last confirmed 1m swing and VWAP, and it only moves toward price."""
    sw = _swing(b1, side)
    cands = [x for x in (sw, vwap) if x is not None]
    if not cands:
        return prev
    lvl = max(cands) if side == "C" else min(cands)
    if prev is None:
        return round(lvl, 2)
    return round(max(prev, lvl), 2) if side == "C" else round(min(prev, lvl), 2)


# ---------------------------------------------------------------- guidance for Nick's own trades
def guidance(p, acts, fresh, bid, green, c1, now):
    """What Nick should do now: EXIT / TAKE PROFIT / TIGHTEN STOP / HOLD / NO DATA, with the reasons and the plan.
    Advice only: the desk can't place or guarantee anything; Nick places every order in Robinhood, and a fast market can
    move through a stop."""
    pl = p["plan"]
    up = p["side"] == "C"
    stop_txt = (f"{p['ticker']} 1m close {'below' if up else 'above'} {pl['stop_px']:.2f} or " if pl.get("stop_px") is not None else "") + \
               f"bid ${pl['premium_stop']:.2f}"
    plan_txt = {"stop": stop_txt, "max_loss_rule": "20% of premium planned max (not a guaranteed fill)",
                "t1": f"{pl['t1']} {pl['t1_level']:.2f}" if pl.get("t1_level") is not None else None,
                "take_profit": ("At T1 sell 1 if you have 2+ and trail the rest; with 1 contract sell at T1" if pl.get("t1_level") is not None
                                else "No level target: protect gains with breakeven at +10% and the lock at +25%"),
                "flat_by": pl.get("flat_by"), "origin": pl.get("origin", "discretionary")}
    if acts:
        kind, qty, why = acts[0]
        action = "EXIT" if qty >= p["qty_open"] else f"TAKE PROFIT: sell {qty}"
        return {"action": action, "why": [why], "at": now.strftime("%H:%M:%S"), "plan": plan_txt}
    if not fresh:
        return {"action": "NO DATA", "why": ["no live quote for this exact contract (check the expiry you logged)"],
                "at": now.strftime("%H:%M:%S"), "plan": plan_txt}
    why = []
    pnl = (bid - p["fill"]) / p["fill"] * 100
    why.append(f"bid {bid:.2f} ({pnl:+.0f}% vs your {p['fill']:.2f}, {'green after costs' if green else 'not green yet'})")
    if c1 is not None and pl.get("stop_px") is not None:
        why.append(f"{p['ticker']} {c1:.2f}, {abs(c1 - pl['stop_px']):.2f} from the stop level")
    if pl.get("t1_level") is not None and not pl.get("t1_done") and c1 is not None:
        why.append(f"{abs(pl['t1_level'] - c1):.2f} to T1 {pl['t1']}")
    recent = (pl.get("stops") or [])[-1:]
    if recent and recent[0].get("by") == "desk" and recent[0]["t"][11:16] == now.strftime("%H:%M") and len(pl.get("stops")) > 1:
        return {"action": f"TIGHTEN STOP to ${pl['premium_stop']:.2f}", "why": [recent[0]["why"]] + why,
                "at": now.strftime("%H:%M:%S"), "plan": plan_txt}
    if green and pl.get("last_progress_t"):
        left = _c()["stall_min"] - (now - datetime.fromisoformat(pl["last_progress_t"])).total_seconds() / 60
        why.append(f"stall timer {max(0, left):.0f} min")
    elif not green and pl.get("flat_by"):
        why.append(f"needs to be green by {pl['flat_by']}")
    return {"action": "HOLD", "why": why, "at": now.strftime("%H:%M:%S"), "plan": plan_txt}


def _ratchet(p, new_stop, why, by="desk"):
    """Stops move only toward protection. Every change is versioned with who/when/why."""
    pl = p["plan"]
    if new_stop is None or new_stop <= pl["premium_stop"]:
        return False
    pl["stops"] = (pl.get("stops") or []) + [{"t": store.ts(), "stop": round(new_stop, 2), "by": by, "why": why,
                                               "prev": pl["premium_stop"]}]
    pl["premium_stop"] = round(new_stop, 2)
    _once(p, f"stop{new_stop:.2f}", f"{_who(p)} {p['contract']}: stop up to ${new_stop:.2f} ({why})" +
          (" -> update your stop in Robinhood" if p["ledger"] == "real" else ""), "real_alert" if p["ledger"] == "real" else "note")
    return True


def user_stop(p, new_stop, force=False):
    """Nick reports a stop change on a REAL trade. Widening is refused unless forced, and recorded either way.
    Never below the 20% max planned loss: the desk keeps that level as the plan's stop even if Nick reports a wider
    one (recorded as a rule break), because a wider stop only keeps a losing trade alive."""
    pl = p["plan"]
    floor = pl.get("ceiling_stop")
    if floor is not None and new_stop < floor:
        pl["reported_stop"] = round(new_stop, 2)
        pl["stops"] = (pl.get("stops") or []) + [{"t": store.ts(), "stop": round(new_stop, 2), "by": "Nick (reported)",
                                                   "why": "beyond the 20% max planned loss: not accepted as the plan's stop", "prev": pl.get("premium_stop")}]
        store.pos_save(p)
        store.event("real", f"STOP ${new_stop:.2f} on {p['contract']} is past your 20% max planned loss (${floor:.2f}). "
                    f"The plan keeps ${max(floor, pl.get('premium_stop') or floor):.2f}; if the bid gets there the desk says EXIT."
                    + (" Your reported stop is logged as a rule break." if force else ""), "real", p["id"])
        return False, "beyond the 20% max planned loss"
    old = pl.get("premium_stop") or pl.get("stop")
    if old is not None and new_stop < old and not force:
        store.event("real", f"STOP CHANGE REFUSED on {p['contract']}: ${new_stop:.2f} would WIDEN the stop from ${old:.2f}. "
                    "Say 'STOP {:.2f} force' if you really moved it (it will be recorded as a widened stop).".format(new_stop), "real", p["id"])
        return False, "widening refused"
    key = "premium_stop" if "premium_stop" in pl else "stop"
    pl["stops"] = (pl.get("stops") or []) + [{"t": store.ts(), "stop": round(new_stop, 2), "by": "Nick (reported)",
                                               "why": "widened (forced)" if old is not None and new_stop < old else "tightened", "prev": old}]
    pl[key] = round(new_stop, 2)
    store.pos_save(p)
    store.event("real", f"YOUR STOP on {p['contract']} recorded: ${new_stop:.2f} (was ${old:.2f})" +
                (" - WIDENED, logged as a rule break" if old is not None and new_stop < old else ""), "real", p["id"])
    return True, None


def _apply(p, acts):
    done = []
    for kind, qty, why in acts[:1]:            # one decision per tick, in precedence order
        key = f"{kind}:{why.split(':')[0][:28]}:{p['qty_open']}"
        if key in (p["plan"].get("actions_done") or []):
            continue
        if p["ledger"] == "real":
            _once(p, key, f"YOUR {p['ticker']} {p['contract']}: {why} -> do it in Robinhood, then log OUT (the desk can't sell for you)",
                  "real_alert")
            p["plan"]["actions_done"] = (p["plan"].get("actions_done") or []) + [key]
            store.pos_save(p)
            done.append((kind, qty, why))
            continue
        n, px = paper.sell(p, qty, why)
        if n:
            p["plan"]["actions_done"] = (p["plan"].get("actions_done") or []) + [key]
            store.pos_save(p)
            done.append((kind, n, why))
    return done


def _swing(b1, side):
    if b1 is None or len(b1) < 3:
        return None
    lows, highs = b1["Low"].values, b1["High"].values
    for i in range(len(b1) - 2, 0, -1):
        if side == "C" and lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            return float(lows[i])
        if side == "P" and highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            return float(highs[i])
    return None


def _once(p, key, text, kind="note"):
    k = f"once:{p['id']}:{key}"
    if store.kv_get(k):
        return
    store.kv_set(k, True)
    store.event(kind, text, p["ledger"], p["id"])


def _who(p):
    return {"real": "YOUR", "paper": "PAPER", "research": "RESEARCH"}.get(p["ledger"], p["ledger"].upper())


def stall_countdown(p):
    """For the UI: minutes left on the green-stall timer (None when not green or not v3)."""
    pl = p.get("plan") or {}
    if pl.get("v") != 3 or not pl.get("last_progress_t"):
        return None
    left = _c()["stall_min"] - (core.now_et() - datetime.fromisoformat(pl["last_progress_t"])).total_seconds() / 60
    return round(max(0.0, left), 1)
