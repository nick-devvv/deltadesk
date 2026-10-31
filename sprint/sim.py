"""sprint/sim.py - the sprint's trade simulator: one long 0DTE option per signal, managed minute by minute with the
exit variants pre-registered in docs/research/SPRINT_PLAN.md ("Exit variants"). Fills obey sprint/fills.py.

Units. "gain" = the option's liquidation value after costs vs its cost after costs, per contract:
    cost C       = entry fill (traded price + k x half-spread) + $0.65 / 100
    proceeds(px) = px - k x half-spread(px) - $0.65 / 100
    gain(px)     = proceeds(px) / C - 1
Every premium threshold (stop %, breakeven, T1, locks, giveback) is a gain level, so "costs included" always holds,
and is turned into a trigger on the option's TRADED price (the premium a bar must touch). Triggers use k = 1 (the
base cost model); the 2x-slippage result reuses the same decisions with worse fills (fills.stop_k).
Planning numbers (the ceiling check and R:R) are made at the decision time with the contract's last price (BS-EST
repricing at the stock target/stop with the implied vol at the decision, DECAY_MIN minutes later); the triggers are
then set from the actual entry fill.

Stop rules (`stop`):
  premium  the time-of-day ceiling (table below) as a premium stop, acting on the option's prices every minute.
  level    the entry's invalidation level (Signal.invalid) -/+ max($0.02, 0.05 x ATR(14, 1m)), judged on finished
           1-minute underlying closes. If the BS-EST loss at that stock price (costs included) exceeds the window's
           ceiling, the trade is SKIPPED. The ceiling also stays on as a hard premium stop.
  noise    the noise rules: at each half-hour check a close through max(upper, VWAP) / min(lower, VWAP) exits, a
           signal on the other side exits; the 20% ceiling acts every minute unless the signal is the no-cap twin.
Take profit (`tp`):
  none     stop + time only.
  A        fixed T1 by the time-of-day table (premium target on the option's prices).
  B        sell all just before the first key level: the first level L beyond the entry (levels known at the decision)
           with L - buffer beyond the underlying's price; target = L - buffer (calls) / L + buffer (puts). Buffers:
           "$0.03", "0.05%" (of the price), "0.1atr" (ATR(14, 1m)). A finished bar touching the target exits at the
           next option print.
  C        sell half at that first level, trail the rest (the run's trail; "lvl" when none is given). If a later
           finished close goes through L and a retest then holds (a bar's low within the buffer of L, closing beyond
           L), the rest targets the next level beyond L (minus the buffer).
  D        A, except on trend days (daytype.trend_aligned at the decision) or RVOL >= 1.5, where it uses C (news is
           unknown in the backtest and never triggers C).
  E        at the first level, exit only on a measurable rejection on the touching bar: an adverse wick >= 50% of the
           bar's range, volume >= 2x the mean of the prior 20 one-minute bars (today, at least 10), or the 1-minute
           MACD(12,26,9) histogram falling 2 bars in a row (rising for puts). Otherwise hold to the next level, and
           test again there.
Trails (`trail`, all start once the trade is green, i.e. proceeds at a bar high > C, except the breakeven move):
  be6/be8/be10/be15  stop to gain 0 (fill + costs) once gain at a bar high reaches +6/8/10/15%
  belevel            stop to gain 0 once a finished close is beyond the first level (the B target's level)
  L1/L2/L3           profit-lock ladders (gain at a bar high -> locked gain): L1 20->10, 30->20, 50->35;
                     L2 15->5, 30->15, 60->40; L3 25->10, 50->30, 100->70
  hl1m / hl5m        underlying stop under each confirmed 1-minute / 5-minute pivot low (a bar whose low is below the
                     bars on each side, confirmed by the next bar; pivot highs for puts) since the entry, minus the
                     stop buffer, raised only, judged on finished 1-minute closes
  lvl                underlying stop under the last level cleared (the highest level between the entry price and the
                     finished close, known at that bar), minus the stop buffer, raised only
  gb30/gb40/gb50     give back at most 30/40/50% of the peak open profit (peak from bar highs, in dollars after costs)
  vwap / ema9        on trend days only (trend_aligned at the decision): exit on a finished close beyond VWAP / the
                     1-minute EMA 9
Time of day (`time`), table = SPRINT_PLAN's (window: max stop, breakeven at, T1, if-flat minutes):
  09:45-11:30  20%, +10%, +20%, 5 | 11:30-14:00  12%, +8%, +15%, 3 | 14:00-15:30  10%, +6%, +12%, 3 | after 15:30 no
  new trades (times before 09:45 use the first window).
  a  the table as it is: ceiling, breakeven move, if-flat and (for A) T1 follow the current window.
  b  no time tightening: the entry window's ceiling for the whole trade; no table breakeven, no if-flat.
  c  levels set the target; time only tightens the ceiling and the if-flat clock (no table breakeven).
  d  as c, but on trend days (trend_aligned at the decision) time tightening is off (as b). News: unknown.
  Crossing into a new window never loosens anything: the ceiling, T1, breakeven trigger and if-flat deadline only
  ever move tighter. If-flat (the desk's rule): at the end of minute `flat` after the fill, a trade that is not green
  after costs at the bar's last price and never reached its breakeven trigger exits at the next print.
All out: "15:25" or "15:50" (12:50 on 1:00 PM early-close days): decided at the end of the prior minute, filled at
the open of that minute (the next print if it has none).
R:R minimum (`rr_min`): stock R:R = (target - price) / (price - stop) and option R:R = (proceeds at the target -
C) / (C - proceeds at the stop), BS-EST repriced DECAY_MIN minutes after the decision; both must reach the minimum.
With a premium stop the stock stop for the R:R is the BS-EST underlying price where the option hits the ceiling.
"""
import math
from dataclasses import asdict, dataclass, field

import numpy as np

from . import bs, contracts
from .fills import ENTRY_WAIT, FEE, MULT, pnl

N = 390
DECAY_MIN = 15
TABLE = ((15, 120, 0.20, 0.10, 0.20, 5), (120, 270, 0.12, 0.08, 0.15, 3), (270, 360, 0.10, 0.06, 0.12, 3))
NO_NEW_AFTER = 360                       # 15:30 (minutes after 09:30)
LADDERS = {"L1": ((0.20, 0.10), (0.30, 0.20), (0.50, 0.35)), "L2": ((0.15, 0.05), (0.30, 0.15), (0.60, 0.40)),
           "L3": ((0.25, 0.10), (0.50, 0.30), (1.00, 0.70))}
ALLOUT = {"15:25": 355, "15:50": 380}
EARLY_ALLOUT = 200                       # 12:50


def hm_to_min(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m) - 570


@dataclass(frozen=True)
class ExitCfg:
    stop: str = "level"
    tp: str = "none"
    tp_buffer: str = "$0.03"
    rr_min: float = None
    trail: str = "none"
    time: str = "a"
    allout: str = "15:25"
    contract: str = "d40-55t45"
    table: tuple = TABLE

    @classmethod
    def from_dict(cls, d):
        keys = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        if "table" in keys and keys["table"] is not None:
            keys["table"] = tuple(tuple(x) for x in keys["table"])
        return cls(**keys)

    def as_dict(self):
        d = asdict(self)
        d.pop("table")
        return d


def window(table, minute):
    """The table row in force at `minute` (minutes after 09:30); before the first row -> the first row."""
    w = table[0]
    for row in table:
        if minute >= row[0]:
            w = row
    return w


def tp_buffer(kind, price, atr1):
    if kind == "$0.03":
        return 0.03
    if kind == "0.05%":
        return 0.0005 * price
    if kind == "0.1atr":
        return 0.1 * (atr1 or 0.0)
    raise ValueError(f"unknown tp buffer {kind}")


def stop_buffer(atr1):
    return max(0.02, 0.05 * (atr1 or 0.0))


def first_level(levels, i, price, side, buf, beyond=None):
    """(level, target) for the first level beyond `price` (and beyond `beyond` if given) with the buffer applied."""
    ref = price if beyond is None else beyond
    lv = levels.at(i)
    if side == "C":
        for px, k in lv:
            if px > ref + 1e-9 and px - buf > price + 1e-9:
                return (px, k), px - buf
    else:
        for px, k in reversed(lv):
            if px < ref - 1e-9 and px + buf < price - 1e-9:
                return (px, k), px + buf
    return None, None


class Costs:
    """Cost model for one trade (k = 1 planning), triggers solved on the traded price."""

    def __init__(self, spread, sym, minute, k=1):
        self.spread, self.sym, self.minute, self.k = spread, sym, minute, k

    def hs(self, px, minute=None):
        return self.spread.half_spread(self.sym, px, self.minute if minute is None else minute)[0]

    def cost(self, px):
        return px + self.k * self.hs(px) + FEE / MULT

    def proceeds(self, px):
        return px - self.k * self.hs(px) - FEE / MULT

    def trigger(self, target):
        """Traded price whose proceeds equal `target` (bisection; proceeds is increasing)."""
        lo, hi = 0.0, max(4.0 * target + 1.0, 1.0)
        if self.proceeds(lo) >= target:
            return lo
        for _ in range(50):
            mid = 0.5 * (lo + hi)
            if self.proceeds(mid) < target:
                lo = mid
            else:
                hi = mid
        return hi


def _f(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def simulate(ctx, sig, cfg, levels=None, tape=None, cinfo=None, k_plan=1):
    """Simulate one signal under one exit configuration. Returns a dict with status TRADE or SKIP (+ reason)."""
    side, j = sig.side, sig.idx
    up = side == "C"
    sgn = 1.0 if up else -1.0
    dec = j + 1
    base = {"symbol": ctx.sym, "day": ctx.day.isoformat(), "setup": sig.setup, "side": side, "signal_idx": j}
    if dec >= NO_NEW_AFTER:
        return dict(base, status="SKIP", reason="no new trades after 15:30")
    allout_idx = EARLY_ALLOUT if ctx.early else ALLOUT[cfg.allout]
    if dec >= allout_idx:
        return dict(base, status="SKIP", reason="signal after the all-out time")
    levels = levels or ctx.levels()
    dt = ctx.daytype()
    if tape is None:
        tape, cinfo = contracts.pick(ctx, side, j, cfg.contract)
        if tape is None:
            return dict(base, status="SKIP", reason=cinfo)
    S = sig.price
    atr1 = _f(ctx.atr1[j])
    costs = Costs(ctx.spread, ctx.sym, dec, k_plan)
    px_dec, iv = cinfo["px"], cinfo["iv"]
    C_plan = costs.cost(px_dec)
    T_plan = bs.t_years(390 - dec - DECAY_MIN)
    K = tape.strike
    reprice = lambda s: bs.price(s, K, T_plan, iv, side)
    trend = dt.trend_aligned(j, side)
    feats = dt.features(j)
    noise_mode = cfg.stop == "noise"
    w0 = window(cfg.table, dec)
    no_tight = cfg.time == "b" or (cfg.time == "d" and trend) or noise_mode
    ceiling = (0.20 if sig.info.get("cap", True) else None) if noise_mode else w0[2]
    tp = cfg.tp
    if tp == "D":
        use_c = trend or ((feats.get("rvol") or 0) >= 1.5)
        tp = "C" if use_c else "A"
    trail = cfg.trail
    if tp == "C" and trail == "none":
        trail = "lvl"
    out = dict(base, invalid=sig.invalid, contract=cinfo["symbol"], strike=K, delta_est=cinfo["delta"], iv_est=round(iv, 4), tp_eff=tp,
               trend_at_entry=trend, day_type=feats["day_type"], rvol=feats.get("rvol"))
    # ---------------- planning at the decision time
    buf_s = stop_buffer(atr1)
    stop_s = None
    if cfg.stop == "level":
        if sig.invalid is None:
            return dict(out, status="SKIP", reason="setup has no invalidation level")
        stop_s = sig.invalid - sgn * buf_s
        if (stop_s >= S) if up else (stop_s <= S):
            return dict(out, status="SKIP", reason="level stop is not beyond the entry price")
        est = costs.proceeds(reprice(stop_s))
        loss = 1 - est / C_plan
        out["est_loss_at_stop"] = round(loss, 4)
        if ceiling is not None and loss > ceiling:
            return dict(out, status="SKIP", reason=f"level stop does not fit the {ceiling:.0%} ceiling (BS-EST loss {loss:.0%})")
    lvl1, tgt_s = None, None
    buf_t = tp_buffer(cfg.tp_buffer, S, atr1)
    if tp in ("B", "C", "E") or cfg.rr_min or trail == "belevel":
        lvl1, tgt_s = first_level(levels, j, S, side, buf_t)
    rr_s = rr_o = None
    risk_o = None
    if tgt_s is not None:
        stop_for_rr = stop_s
        if stop_for_rr is None and ceiling is not None:
            stop_for_rr = bs.stock_for_price(costs.trigger(C_plan * (1 - ceiling)), K, T_plan, iv, side, S)
        if stop_for_rr is not None and abs(S - stop_for_rr) > 0:
            rr_s = sgn * (tgt_s - S) / (sgn * (S - stop_for_rr))
            risk_o = C_plan - costs.proceeds(reprice(stop_for_rr))
            reward_o = costs.proceeds(reprice(tgt_s)) - C_plan
            rr_o = reward_o / risk_o if risk_o > 0 else None
    if cfg.rr_min:
        if tgt_s is None:
            return dict(out, status="SKIP", reason="no target level for the R:R check")
        if rr_s is None or rr_o is None or rr_s < cfg.rr_min or rr_o < cfg.rr_min:
            return dict(out, status="SKIP", reason=f"R:R below {cfg.rr_min:g} (stock {rr_s if rr_s is None else round(rr_s, 2)}, "
                                                   f"option {rr_o if rr_o is None else round(rr_o, 2)})", planned_rr_stock=rr_s, planned_rr_opt=rr_o)
    # ---------------- entry fill
    e = tape.next_print(dec, min(j + ENTRY_WAIT, allout_idx - 1))
    if e is None:
        return dict(out, status="SKIP", reason=f"no option print in the {ENTRY_WAIT} minutes after the signal")
    b_in = float(tape.o[e])
    hs_in = costs.hs(b_in, e)
    C = b_in + k_plan * hs_in + FEE / MULT
    S_in = float(ctx.o[e]) if not math.isnan(ctx.o[e]) else S
    trig = lambda g: costs.trigger(C * (1 + g))
    if risk_o is None and ceiling is not None:
        risk_o = C * ceiling
    planned_risk = (risk_o if risk_o is not None else (C - costs.proceeds(reprice(stop_s)) if stop_s is not None else None))
    # ---------------- state
    prem = {}
    if ceiling is not None:
        prem["CEILING STOP"] = trig(-ceiling)
    ceil_now = ceiling
    stock_stops = {}
    if stop_s is not None:
        stock_stops["LEVEL STOP"] = stop_s
    t1 = w0[4] if tp == "A" else None
    prem_tgt = trig(t1) if t1 is not None else None
    be_list = []
    if cfg.time == "a" and not noise_mode:
        be_list.append(w0[3])
    if trail.startswith("be") and trail[2:].isdigit():
        be_list.append(int(trail[2:]) / 100)
    be_pct = min(be_list) if be_list else None
    use_flat = not noise_mode and (cfg.time in ("a", "c") or (cfg.time == "d" and not trend))
    flat_idx = e + w0[5] - 1 if use_flat else None
    stock_tgt = tgt_s if tp in ("B", "C", "E") else None
    c_state = None
    legs = []
    qty = 1.0
    pending = None
    be_hit = green_ever = False
    peak, peak_i = -1e9, e
    hi_opt, lo_opt = -1e9, 1e9
    s_hi, s_lo = -1e9, 1e9
    pivots = []
    exit_i = None
    bands = sig.info.get("bands") if noise_mode else None
    hist = ctx.hist1

    def leg(q, basis, i, why, is_stop):
        legs.append({"qty": q, "basis": float(basis), "hs": costs.hs(basis, i), "idx": i, "reason": why, "stop": is_stop})

    i = e
    while i < N:
        has = tape.has_print(i)
        if pending is not None:
            if not has:
                i += 1
                continue
            q, why, st = pending
            leg(q, tape.o[i], i, why, st)
            qty -= q
            pending = None
            if qty <= 1e-9:
                exit_i = i
                break
        if has:
            hi_opt, lo_opt = max(hi_opt, float(tape.h[i])), min(lo_opt, float(tape.l[i]))
            if tape.h[i] > peak:
                peak, peak_i = float(tape.h[i]), i
        sok = ctx.has_bar(i)
        if sok:
            s_hi, s_lo = max(s_hi, float(ctx.h[i])), min(s_lo, float(ctx.l[i]))
        # ---- premium events inside the bar
        stop_name, stop_px = (max(prem.items(), key=lambda kv: kv[1]) if prem else (None, None))
        p_stop = has and stop_px is not None and tape.l[i] <= stop_px
        p_tgt = has and prem_tgt is not None and tape.h[i] >= prem_tgt
        # ---- underlying events on the finished bar
        s_stop = None
        if sok:
            c_i = float(ctx.c[i])
            for nm, lv in stock_stops.items():
                if (c_i < lv) if up else (c_i > lv):
                    s_stop = f"{nm} {lv:.2f}: 1m close {c_i:.2f}"
                    break
            if s_stop is None and green_ever and trail in ("vwap", "ema9") and trend:
                ref = ctx.vwap[i] if trail == "vwap" else ctx.ema9[i]
                if not math.isnan(ref) and ((c_i < ref) if up else (c_i > ref)):
                    s_stop = f"{trail.upper()} TRAIL {ref:.2f}: 1m close {c_i:.2f}"
            if s_stop is None and noise_mode and bands and i in bands:
                upb, lob = bands[i]
                vw = ctx.vwap[i]
                lvl = max(upb, vw) if up else min(lob, vw)
                if (c_i < lvl) if up else (c_i > lvl):
                    s_stop = f"NOISE STOP at check: 1m close {c_i:.2f} through {'max' if up else 'min'}(band, VWAP) {lvl:.2f}"
        s_tgt = sok and stock_tgt is not None and ((ctx.h[i] >= stock_tgt) if up else (ctx.l[i] <= stock_tgt))
        if p_stop:
            basis, _how = tape.stop_basis(i, stop_px)
            leg(qty, basis, i, stop_name, True)
            qty = 0.0
            exit_i = i
            break
        if s_stop:
            pending = (qty, s_stop, True)
            i += 1
            continue
        if p_tgt:
            basis, _how = tape.target_basis(i, prem_tgt)
            leg(qty, basis, i, f"T1 +{t1:.0%}", False)
            qty = 0.0
            exit_i = i
            break
        if noise_mode and bands and sok and i in bands:
            upb, lob = bands[i]
            if (ctx.c[i] < lob) if up else (ctx.c[i] > upb):
                pending = (qty, "NOISE REVERSAL: signal on the other side", False)
                i += 1
                continue
        if s_tgt:
            if tp == "B" or (tp == "C" and c_state is not None and c_state["phase"] == 2):
                pending = (qty, "LEVEL TARGET" if tp == "B" else "LEVEL 2 (rest)", False)
                i += 1
                continue
            if tp == "C" and c_state is None:
                pending = (0.5, f"LEVEL 1 {lvl1[1]} {lvl1[0]:.2f} (half)", False)
                c_state = {"L": lvl1[0], "phase": 0}
                stock_tgt = None
            elif tp == "E":
                rej = _rejection(ctx, i, up)
                if rej:
                    pending = (qty, f"LEVEL REJECTION ({rej})", False)
                    i += 1
                    continue
                cur = stock_tgt + sgn * buf_t
                nxt, nt = first_level(levels, i, max(float(ctx.c[i]), cur) if up else min(float(ctx.c[i]), cur), side, buf_t, beyond=cur)
                stock_tgt = nt
        # ---- end-of-bar updates
        if has:
            gain_hi = costs.proceeds(float(tape.h[i])) / C - 1
            green_ever |= gain_hi > 0
            last_px = float(tape.c[i])
        else:
            gain_hi = None
            last_px = tape.last_close(i, 390)
        mnow = i + 1
        if not no_tight:
            w = window(cfg.table, mnow)
            if ceil_now is not None and w[2] < ceil_now:
                ceil_now = w[2]
                prem["CEILING STOP"] = max(prem.get("CEILING STOP", 0.0), trig(-ceil_now))
            if t1 is not None and cfg.time == "a" and w[4] < t1:
                t1 = w[4]
                prem_tgt = min(prem_tgt, trig(t1))
            if cfg.time == "a" and be_pct is not None and w[3] < be_pct:
                be_pct = w[3]
            if flat_idx is not None:
                flat_idx = min(flat_idx, e + w[5] - 1)
        if gain_hi is not None:
            if be_pct is not None and not be_hit and gain_hi >= be_pct:
                be_hit = True
                prem["BREAKEVEN STOP"] = max(prem.get("BREAKEVEN STOP", 0.0), trig(0.0))
            if trail in LADDERS:
                for tr, lock in LADDERS[trail]:
                    if gain_hi >= tr:
                        prem["LOCK STOP"] = max(prem.get("LOCK STOP", 0.0), trig(lock))
            if trail.startswith("gb") and green_ever:
                g = int(trail[2:]) / 100
                peak_profit = costs.proceeds(peak) - C
                if peak_profit > 0:
                    prem["GIVEBACK STOP"] = max(prem.get("GIVEBACK STOP", 0.0), costs.trigger(C + (1 - g) * peak_profit))
        if sok:
            c_i = float(ctx.c[i])
            if trail == "belevel" and lvl1 is not None and not be_hit and ((c_i > lvl1[0]) if up else (c_i < lvl1[0])):
                be_hit = True
                prem["BREAKEVEN STOP"] = max(prem.get("BREAKEVEN STOP", 0.0), trig(0.0))
            if green_ever and trail == "hl1m" and i - 1 > e and i >= 2 and ctx.has_bar(i - 1) and ctx.has_bar(i - 2):
                a, b, c3 = (ctx.l[i - 2], ctx.l[i - 1], ctx.l[i]) if up else (ctx.h[i - 2], ctx.h[i - 1], ctx.h[i])
                if (b < a and b < c3) if up else (b > a and b > c3):
                    _raise(stock_stops, "1M PIVOT TRAIL", float(b) - sgn * buf_s, up)
            if green_ever and trail == "hl5m" and (i + 1) % 5 == 0 and ctx.b5 is not None:
                bq = (i + 1) // 5 - 1
                if bq >= 2 and (bq - 1) * 5 >= e - 4:
                    col = 2 if up else 1
                    a, b, c3 = ctx.b5[bq - 2, col], ctx.b5[bq - 1, col], ctx.b5[bq, col]
                    if not np.isnan([a, b, c3]).any() and ((b < a and b < c3) if up else (b > a and b > c3)):
                        _raise(stock_stops, "5M PIVOT TRAIL", float(b) - sgn * buf_s, up)
            if green_ever and trail == "lvl":
                cl = [px for px, _k in levels.at(i) if ((S < px < c_i) if up else (c_i < px < S))]
                if cl:
                    _raise(stock_stops, "LEVEL TRAIL", (max(cl) if up else min(cl)) - sgn * buf_s, up)
            if c_state is not None:
                L = c_state["L"]
                beyond = (c_i > L) if up else (c_i < L)
                if c_state["phase"] == 0 and beyond:
                    c_state["phase"] = 1
                elif c_state["phase"] == 1:
                    touched = (ctx.l[i] <= L + buf_t) if up else (ctx.h[i] >= L - buf_t)
                    if touched and beyond:
                        _l2, t2 = first_level(levels, i, c_i, side, buf_t, beyond=L)
                        if t2 is not None:
                            stock_tgt = t2
                            c_state["phase"] = 2
                    elif not beyond:
                        c_state["phase"] = 3
        if flat_idx is not None and i >= flat_idx:
            flat_idx = None
            if not be_hit and (last_px is None or costs.proceeds(last_px) <= C):
                pending = (qty, "IF FLAT: not green after costs", False)
        if i + 1 >= allout_idx and (pending is None or pending[0] < qty - 1e-9):
            pending = (qty, f"ALL OUT {'12:50' if ctx.early else cfg.allout}", False)
        i += 1
    if exit_i is None:
        return dict(out, status="SKIP", reason="VOID: no option print to exit on before the close", entry_idx=e)
    return _record(out, ctx, levels, sig, cfg, costs, e, b_in, hs_in, C, S_in, legs, exit_i, peak, peak_i, hi_opt, lo_opt,
                   s_hi, s_lo, up, rr_s, rr_o, planned_risk, stop_s, tgt_s, lvl1, ceiling)


def _raise(stops, name, lv, up):
    old = stops.get(name)
    if old is None or ((lv > old) if up else (lv < old)):
        stops[name] = lv


def _rejection(ctx, i, up):
    o, h, l, c, v = ctx.o[i], ctx.h[i], ctx.l[i], ctx.c[i], ctx.v[i]
    why = []
    rng = h - l
    if rng > 0:
        wick = (h - max(o, c)) if up else (min(o, c) - l)
        if wick >= 0.5 * rng:
            why.append("wick")
    prior = ctx.v[max(0, i - 20):i]
    prior = prior[~np.isnan(prior)]
    if len(prior) >= 10 and v >= 2 * float(prior.mean()):
        why.append("volume 2x")
    hs = ctx.hist1
    if i >= 2 and not np.isnan(hs[i - 2:i + 1]).any():
        if (hs[i] < hs[i - 1] < hs[i - 2]) if up else (hs[i] > hs[i - 1] > hs[i - 2]):
            why.append("MACD histogram fading")
    return ", ".join(why)


def _t(i):
    m = 570 + i
    return f"{m // 60:02d}:{m % 60:02d}"


def _record(out, ctx, levels, sig, cfg, costs, e, b_in, hs_in, C, S_in, legs, exit_i, peak, peak_i, hi_opt, lo_opt,
            s_hi, s_lo, up, rr_s, rr_o, planned_risk, stop_s, tgt_s, lvl1, ceiling):
    lg = [(x["qty"], x["basis"], x["hs"], x["stop"]) for x in legs]
    p1, p2 = pnl(b_in, hs_in, lg, 1), pnl(b_in, hs_in, lg, 2)
    e1 = b_in + hs_in
    peak_profit = ((peak - costs.hs(peak)) - e1) * MULT - 2 * FEE
    sgn = 1 if up else -1
    s_mfe = (s_hi - S_in) if up else (S_in - s_lo)
    s_mae = (s_lo - S_in) if up else (S_in - s_hi)
    nl = None
    if ctx.has_bar(peak_i):
        sp = float(ctx.h[peak_i]) if up else float(ctx.l[peak_i])
        near = levels.nearest_i(sp, peak_i)
        if near:
            nl = {"level": near[0], "kind": near[1], "dist": round(sp - near[0], 4)}
    exit_basis = sum(x["qty"] * x["basis"] for x in legs)
    last = legs[-1]
    return dict(out, status="TRADE", entry_idx=e, entry_time=_t(e), entry_basis=round(b_in, 4), entry_hs=round(hs_in, 4),
                entry_fill=round(e1, 4), cost_basis=round(C, 4), stock_entry=round(S_in, 4), signal_price=sig.price,
                exit_idx=exit_i, exit_time=_t(exit_i), exit_basis=round(exit_basis, 4), exit_reason=last["reason"],
                exit_is_stop=bool(last["stop"]), legs=legs, stock_exit=_f(ctx.o[exit_i]) if not math.isnan(ctx.o[exit_i]) else _f(ctx.c[exit_i - 1]),
                pnl=round(p1, 2), pnl_2x=round(p2, 2), opt_mfe_pct=round(hi_opt / e1 - 1, 4), opt_mae_pct=round(lo_opt / e1 - 1, 4),
                stock_mfe=round(s_mfe, 4), stock_mae=round(s_mae, 4), peak_time=_t(peak_i), peak_px=round(peak, 4),
                peak_profit=round(peak_profit, 2), pct_peak_kept=round(p1 / peak_profit, 4) if peak_profit > 0 else None,
                peak_level=nl, planned_rr_stock=None if rr_s is None else round(rr_s, 3),
                planned_rr_opt=None if rr_o is None else round(rr_o, 3),
                planned_risk=None if planned_risk is None else round(planned_risk * MULT, 2),
                actual_rr=round(p1 / (planned_risk * MULT), 3) if planned_risk else None,
                stop_stock=None if stop_s is None else round(stop_s, 4), target_stock=None if tgt_s is None else round(tgt_s, 4),
                target_level=None if lvl1 is None else {"level": lvl1[0], "kind": lvl1[1]}, ceiling=ceiling,
                minutes_held=exit_i - e)
