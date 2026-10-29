"""optionmath.py - contract choice, structural risk, level-based T1, reward/risk and size for one idea.

Units are kept apart on purpose:
  underlying geometry : entry price, structural stop and T1 are UNDERLYING prices; R_u = (T1 - entry) / (entry - stop)
  option dollars      : per-contract $ = premium x multiplier (100); R_o = stressed net gain at T1 / stressed loss
Neither ratio is a promise: the option side is a MODEL (delta + gamma, minus time decay over the expected hold,
minus spread/slippage/fees), labeled as such. If delta is missing the option ratio is UNVERIFIED and the idea is
excluded from the main strategy. Main requires BOTH ratios >= min_reward_risk (2.0).

Ceiling: the modeled loss at the structural stop must fit inside the 20% planned premium-loss ceiling (costs
included). If it doesn't, try the next eligible contract; never move the stop inside the invalidation or invent a
farther target to make 2:1 work.
Size: floor(available $ risk / stressed $ loss per contract), then the grade cap and max contracts. 0 = no trade.
"""
import math

import core
import strategy


def c3():
    return core.policy()["v3"]


def costs(spread):
    k = c3()["contract"]
    slip = max(k["slippage_min"], (spread or 0) * k["slippage_spread_frac"])
    return round(slip, 4), k["fees_per_contract_side"]


def model_premium(q, dS, side, hold_min=None):
    """Modeled bid after an underlying move dS (signed in price units) from now. Delta-gamma, minus theta over the
    hold. Returns (value, label). None when delta is unknown."""
    d = q.get("delta")
    if d is None:
        return None, "unverified: no delta"
    g = q.get("gamma")
    k = c3()["contract"]
    hold = hold_min if hold_min is not None else k["hold_min_for_theta"]
    th = q.get("theta")  # per calendar day, negative for longs
    decay = abs(th) * hold / 390.0 if th is not None else 0.0   # trading-day fraction (approximation)
    move = d * dS + (0.5 * g * dS * dS if g is not None else 0.0)
    if g is None:
        move *= k["gamma_missing_haircut"] if move > 0 else 1.0
    val = max(0.0, (q["bid"] or 0) + move - decay)
    label = "model: delta" + ("+gamma" if g is not None else " only (gamma missing, gains haircut)") + \
            (f" - theta over {hold} min" if th is not None else " (no theta)")
    return round(val, 4), label


def pick_t1(snap, side, entry_px, stop_px):
    """Next meaningful OPPOSING level beyond entry (resistance for calls, support for puts), at least t1_min_atr
    ATR away. Returns (name, level, target_after_buffer) or None."""
    up = side == "C"
    atr5 = snap.get("atr5") or 0
    min_d = c3()["t1_min_atr"] * atr5
    z = snap.get("zone", 0)
    best = None
    for name, l in snap.get("levels", {}).items():
        v = l["value"]
        if name in ("PDC",):
            continue
        d = (v - entry_px) if up else (entry_px - v)
        if d > max(min_d, z) and (best is None or d < best[2]):
            best = (name, v, d)
    if not best:
        return None
    tgt = best[1] - z if up else best[1] + z     # approach buffer: exit just before the level
    return best[0], best[1], round(tgt, 2)


def plan_trade(idea, snap, chain_rows, grade, budget_left=None, ledger="paper"):
    """Choose the contract and build the full risk plan, or return (None, reason, diagnostics)."""
    p = core.policy()
    k3, cp = c3(), p["contract"]
    side = idea["side"]
    up = side == "C"
    entry_px = snap["close1"]
    stop_px = idea["invalidation"]
    if (up and stop_px >= entry_px) or (not up and stop_px <= entry_px):
        return None, "invalidation is not on the losing side of price", {}
    t1 = pick_t1(snap, side, entry_px, stop_px)
    if not t1:
        return None, "no credible target: no opposing level far enough away", {}
    t1_name, t1_level, t1_px = t1
    risk_u = abs(entry_px - stop_px)
    rew_u = abs(t1_px - entry_px)
    rr_u = round(rew_u / risk_u, 2) if risk_u > 0 else None
    diag = {"entry_px": round(entry_px, 2), "stop_px": round(stop_px, 2), "t1": t1_name, "t1_level": t1_level,
            "t1_px": t1_px, "rr_underlying": rr_u, "tried": []}
    if rr_u is None or rr_u < k3["min_reward_risk"]:
        return None, (f"room to {t1_name} {t1_level:.2f} is {rew_u:.2f} vs {risk_u:.2f} risk to the invalidation "
                      f"({rr_u}R on the underlying, need {k3['min_reward_risk']}R)"), diag
    cands = []
    for c in chain_rows or []:
        bid, ask = c.get("bid") or 0, c.get("ask") or 0
        if bid <= 0 or not (cp["premium_min"] <= ask <= cp["premium_max"]):
            continue
        spread = ask - bid
        if spread / ask > cp["max_spread_pct"]:
            continue
        d = c.get("delta")
        if d is None and c.get("iv"):
            d = core.bs_delta(entry_px, c["strike"], c["iv"], side)
            c = dict(c, delta=d, delta_src="estimated (Black-Scholes from IV)")
        if d is None or not (cp["abs_delta_min"] <= abs(d) <= cp["abs_delta_max"]):
            continue
        cands.append((abs(abs(d) - cp.get("abs_delta_target", 0.45)), spread / ask, c))
    if not cands:
        return None, (f"no contract passes ${cp['premium_min']}-{cp['premium_max']}, spread <= "
                      f"{int(cp['max_spread_pct'] * 100)}% and delta {cp['abs_delta_min']}-{cp['abs_delta_max']} with known delta"), diag
    cands.sort(key=lambda z: (z[0], z[1]))
    ceiling = p["risk"]["stop_cap_pct"]
    for _, _, c in cands:
        slip, fee = costs(c["ask"] - c["bid"])
        entry_prem = c["ask"] + slip
        q = {"bid": c["bid"], "ask": c["ask"], "delta": c["delta"], "gamma": c.get("gamma"), "theta": c.get("theta")}
        dS_stop = (stop_px - entry_px)
        dS_t1 = (t1_px - entry_px)
        at_stop, lab = model_premium(q, dS_stop, side)
        at_t1, _ = model_premium(q, dS_t1, side)
        if at_stop is None or at_t1 is None:
            diag["tried"].append({"symbol": c["symbol"], "why": "unverified: no delta"})
            continue
        exit_stop = max(0.0, at_stop - slip)
        exit_t1 = max(0.0, at_t1 - slip)
        loss_c = round((entry_prem - exit_stop) * 100 + 2 * fee, 2)            # stressed $ loss per contract
        gain_c = round((exit_t1 - entry_prem) * 100 - 2 * fee, 2)               # modeled net $ gain at T1
        ceiling_c = round(ceiling * c["ask"] * 100, 2)
        rr_o = round(gain_c / loss_c, 2) if loss_c > 0 else None
        row = {"symbol": c["symbol"], "ask": c["ask"], "bid": c["bid"], "delta": c["delta"], "loss_c": loss_c,
               "gain_c": gain_c, "ceiling_c": ceiling_c, "rr_option": rr_o}
        diag["tried"].append(row)
        if loss_c > ceiling_c:
            row["why"] = f"structural stop costs ${loss_c:.2f}/contract, over the 20% ceiling ${ceiling_c:.2f}"
            continue
        if rr_o is None or rr_o < k3["min_reward_risk"]:
            row["why"] = f"option reward/risk {rr_o} < {k3['min_reward_risk']} after spread, fees and time decay"
            continue
        caps = p["sizing_by_grade"].get(grade, 0)
        caps = min(caps, p["risk"]["max_contracts"])
        afford = 10 ** 6 if budget_left is None else int(math.floor(budget_left / loss_c))
        qty = max(0, min(caps, afford))
        prem_stop = core.cents_up(c["ask"] * (1 - ceiling) + slip + 2 * fee / 100)   # hard 20% ceiling trigger
        struct_prem = round(exit_stop, 2)
        be_trigger = core.cents_up(entry_prem * (1 + k3["exits"]["be_trigger_pct"]) + 2 * fee / 100)
        return {
            "symbol": c["symbol"], "label": _label(c["symbol"]), "bid": c["bid"], "ask": c["ask"],
            "spread": round(c["ask"] - c["bid"], 2), "delta": c["delta"], "gamma": c.get("gamma"), "theta": c.get("theta"),
            "iv": c.get("iv"), "delta_src": c.get("delta_src", "provider"), "quote_ts": c.get("ts"), "feed": c.get("feed"),
            "qty": qty, "qty_note": None if qty else ("grade cap 0" if caps == 0 else "1 contract risks more than the budget left"),
            "entry_premium_est": round(entry_prem, 2), "premium_limit": core.cents_up(c["ask"] + max(0.02, slip)),
            "loss_per_contract": loss_c, "gain_per_contract": gain_c, "ceiling_per_contract": ceiling_c,
            "rr_option": rr_o, "rr_underlying": rr_u, "model": lab,
            "stop_px": round(stop_px, 2), "entry_px": round(entry_px, 2), "t1": t1_name, "t1_level": t1_level, "t1_px": t1_px,
            "premium_stop": prem_stop, "structural_premium_est": struct_prem, "be_trigger": be_trigger,
            "breakeven_net": core.cents_up(entry_prem + 2 * fee / 100),
            "slippage": slip, "fees_side": fee,
        }, None, diag
    last = diag["tried"][-1] if diag["tried"] else {}
    return None, last.get("why", "no contract fits the structural stop, the 20% ceiling and 2:1"), diag


def _label(sym):
    return f"{int(sym[-8:]) / 1000:g}{sym[-9]}"
