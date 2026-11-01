"""sprint/optpass.py - round 8's option twins whose exits the engine has no run type for, evaluated in ONE pass per entry
over its option tape (SPRINT_PLAN Addendum 10.3 implementation note: "the 12 exits share each entry and its option tape.
Evaluate them in one pass per entry rather than as 12 separate engine runs"). Pre-registered 2026-11-01 before any round-8
run. Research only: cached bars only, no network, no orders.

What runs here (the "option_pass" section of sprint/specs/round8_{hist,dev}_v1.json; HIST tapes MODELED, DEV tapes REAL):
  D1-D6 option twins (Addenda 10.2/10.3) on 0DTE d40-55t45 and next-expiry n1d40-55t45, calls for longs, puts for shorts,
      each with 13 exit variants: the 12-cell grid (fixed stop -10/-20/-30/-50% of the debit x fixed target +30/+50%/none,
      "none" = +9900%, never reached, as FIN-H's own exit) and the signal exit (the opposite signal or the -20% stop).
      All out 15:25 (12:50 on early-close days).
  their matched-random twins: the same decisions (day and minute) with a seeded random side (sprint/ind5.random_side), the
      same 13 exits ("same days and times with a random side for options").
  A-opt (Addendum 10.1): A1 noise_sh on d55-75t65 and n1d55-75t65, exiting on the share rule's own band/VWAP stop and
      reversal at the half-hour checks, no premium line, all out 15:25; A3 gapfade_vix on n1d55-75t65 and its 0DTE twin
      d55-75t65 (Amendment 10), no stop, all out 15:25.
Mechanics: exactly the engine's (sprint/engine.run_pass + sim.simulate with stop="fixed", desk mechanics), so a grid cell
here equals an engine run of the same fixed stop / target (tests/test_sprint_round8_options.py checks it trade by trade):
  * a decision at 1-minute bar j (the 5-minute bar's last minute) enters at the first option print in j+1..j+3 (the next bar),
    paying traded price + half-spread + $0.65; no new trade after 15:30 or at / after the all-out;
  * contract: sprint/contracts.pick at bar j (BS-EST delta band), cached per (decision, side, contract rule);
  * fixed stop / target: triggers on the option's traded price at debit x (1 - stop) / debit x (1 + target), debit = entry fill
    without fees; inside the bar, the same-bar stop wins; a stop fills at the worse of the trigger and the next real price;
  * signal exits are decided on the finished bar and fill at the next option print (its open); a premium stop touched on
    the same bar wins; the all-out is decided at the end of the bar before 15:25 and fills at the next print; no print to
    exit on = VOID (skipped, counted);
  * P/L per contract at k = 1 and 2x slippage (k = 2, 4 half-spreads on stop exits) by sprint/fills.pnl.
One position at a time per study, exit variant and symbol, each with its own state (a cell that exits early can take the
next signal while another cell still holds): a signal is taken when that variant's previous exit filled at or before the
signal bar. Literal reading for the signal-type exits (D signal exit, A-opt): the opposite signal / the share rule's
reversal is both the exit and an entry decision of the rule ("calls carry longs, puts carry shorts"), so the option twin
FLIPS: the held contract is sold and the other side's contract bought at the next print after that same decision bar (the
engine's factory noise run did not flip; Amendment 9 said so explicitly for that run only).
Spread: the pre-registered MODELED-SPREAD (2% of premium, $0.005 floor) on both periods; logged 2026 chains are never read.
MODELED tapes (HIST): sprint/modeled with run 4's calibration; next-expiry tapes expire at the next NYSE session with
modeled.multiplier_for (labeled fallback where run 4 has no key): NOT VALIDATED against real prices.
"""
import gzip
import math
from array import array
from collections import Counter, defaultdict
from datetime import date

import numpy as np

from . import contracts, data, ind5, shares
from . import modeled as MD
from . import spread as SP
from .fills import ENTRY_WAIT, FEE, MULT, pnl
from .sim import ALLOUT, EARLY_ALLOUT, NO_NEW_AFTER, Costs

GRID_STOPS = (0.10, 0.20, 0.30, 0.50)
GRID_TARGETS = (0.30, 0.50, None)
NONE_TARGET = 99.0                       # +9900% of the debit: never reached (FIN-H's "no target")
SIGNAL_STOP = 0.20


def cell_id(stop, target):
    return f"s{int(round(stop * 100)):02d}_" + ("tnone" if target is None else f"t{int(round(target * 100))}")


GRID = [(cell_id(s, t), s, t) for s in GRID_STOPS for t in GRID_TARGETS]
GRID_IDS = [g[0] for g in GRID]
EXIT_SETS = {"grid12+signal": GRID_IDS + ["signal"], "share_signal": ["share_signal"], "hold": ["hold"]}
REASONS = ["FIXED STOP", "FIXED TARGET", "ALL OUT", "OPPOSITE SIGNAL", "NOISE STOP", "NOISE REVERSAL"]
ENTRY_KINDS = set(ind5.RULES) | {"noise_sh", "gapfade_vix"}


def expand_studies(spec):
    """The spec's option_pass section -> list of studies (dicts: name, entry, contract, exits, random_seed)."""
    op = spec.get("option_pass") or {}
    out = []
    for s in op.get("studies") or []:
        if s["entry"] not in ENTRY_KINDS:
            raise ValueError(f"option_pass study {s['name']}: unknown entry {s['entry']}")
        if s["contract"] not in contracts.RULES:
            raise ValueError(f"option_pass study {s['name']}: unknown contract {s['contract']}")
        if s["exits"] not in EXIT_SETS:
            raise ValueError(f"option_pass study {s['name']}: unknown exit set {s['exits']}")
        out.append({"name": s["name"], "entry": s["entry"], "contract": s["contract"], "exits": s["exits"],
                    "random_seed": s.get("random_seed"), "family": s.get("family"), "rule": s.get("rule", s["entry"])})
    names = [s["name"] for s in out]
    if len(set(names)) != len(names):
        raise ValueError("option_pass: duplicate study names")
    return out


def _exits_from(sigs):
    """Opposite-signal exits for every side: a long (C) exits at each P decision and vice versa (both flip)."""
    ex = {"C": {}, "P": {}}
    for s in sigs:
        ex["P" if s["side"] == "C" else "C"][s["idx"]] = ("OPPOSITE SIGNAL", False, True)
    return ex


def day_signals(ctx, entry, seed=None, cache=None):
    """Decisions of one entry on ctx's day (with their exits), cached per (entry, seed)."""
    key = (entry, seed)
    if cache is not None and key in cache:
        return cache[key]
    if entry == "noise_sh":
        sigs = shares.a1_option_signals(ctx)
    elif entry == "gapfade_vix":
        sigs = shares.a3_option_signals(ctx)
    else:
        base = day_signals(ctx, entry, None, cache) if seed is not None else None
        raw = ind5.signals(ctx, entry) if base is None else [dict(s) for s in base]
        if seed is not None:
            raw = ind5.random_side(raw, seed, ctx.sym, ctx.day)
        ex = _exits_from(raw)
        sigs = [dict(s, exits=ex) for s in raw]
    if cache is not None:
        cache[key] = sigs
    return sigs


class Collector:
    """Compact per-trade columns (typed arrays) for every (study, exit) of one period."""

    COLS = (("study", "h"), ("exit", "b"), ("sym", "b"), ("day", "i"), ("side", "b"), ("signal_idx", "h"), ("entry_idx", "h"),
            ("exit_idx", "h"), ("reason", "b"), ("pnl", "d"), ("pnl_2x", "d"), ("entry_basis", "d"), ("exit_basis", "d"))

    def __init__(self, studies, symbols):
        self.studies = [s["name"] for s in studies]
        self.exits = sorted({e for s in studies for e in EXIT_SETS[s["exits"]]}, key=lambda e: (e not in GRID_IDS, e))
        self.symbols = list(symbols)
        self._st = {k: i for i, k in enumerate(self.studies)}
        self._ex = {k: i for i, k in enumerate(self.exits)}
        self._sy = {k: i for i, k in enumerate(self.symbols)}
        self._rs = {k: i for i, k in enumerate(REASONS)}
        self.cols = {k: array(t) for k, t in self.COLS}
        self.skips = defaultdict(Counter)
        self.signals = Counter()

    def __len__(self):
        return len(self.cols["pnl"])

    def add(self, st, ex, sym, day, side, j, e, x, reason, p1, p2, b_in, b_out):
        c = self.cols
        c["study"].append(self._st[st])
        c["exit"].append(self._ex[ex])
        c["sym"].append(self._sy[sym])
        c["day"].append(day.toordinal())
        c["side"].append(1 if side == "C" else -1)
        c["signal_idx"].append(j)
        c["entry_idx"].append(e)
        c["exit_idx"].append(x)
        c["reason"].append(self._rs[reason])
        c["pnl"].append(p1)
        c["pnl_2x"].append(p2)
        c["entry_basis"].append(b_in)
        c["exit_basis"].append(b_out)

    def frame(self):
        import pandas as pd
        c = self.cols
        df = pd.DataFrame({k: np.frombuffer(v, dtype=v.typecode).copy() if len(v) else np.zeros(0) for k, v in c.items()})
        if not len(df):
            return pd.DataFrame(columns=["study", "exit", "symbol", "day", "side", "signal_idx", "entry_idx", "exit_idx", "exit_reason",
                                         "pnl", "pnl_2x", "entry_basis", "exit_basis"])
        out = pd.DataFrame({"study": pd.Categorical.from_codes(df["study"].astype(int), self.studies),
                            "exit": pd.Categorical.from_codes(df["exit"].astype(int), self.exits),
                            "symbol": pd.Categorical.from_codes(df["sym"].astype(int), self.symbols),
                            "day": [date.fromordinal(int(x)).isoformat() for x in df["day"]],
                            "side": np.where(df["side"] > 0, "C", "P"), "signal_idx": df["signal_idx"].astype(int),
                            "entry_idx": df["entry_idx"].astype(int), "exit_idx": df["exit_idx"].astype(int),
                            "exit_reason": pd.Categorical.from_codes(df["reason"].astype(int), REASONS),
                            "pnl": df["pnl"].round(2), "pnl_2x": df["pnl_2x"].round(2), "entry_basis": df["entry_basis"].round(4),
                            "exit_basis": df["exit_basis"].round(4)})
        return out


def _first(mask):
    k = int(np.argmax(mask)) if len(mask) else 0
    return k if len(mask) and mask[k] else None


def entry_fill(ctx, sig_idx, tape, spread, allout_idx):
    """(e, entry basis, entry half-spread, cost C, debit, costs) at the next print after the decision, or None."""
    dec = sig_idx + 1
    e = tape.next_print(dec, min(sig_idx + ENTRY_WAIT, allout_idx - 1))
    if e is None:
        return None
    costs = Costs(spread, ctx.sym, dec, 1)
    b_in = float(tape.o[e])
    hs_in = costs.hs(b_in, e)
    return e, b_in, hs_in, b_in + hs_in + FEE / MULT, b_in + hs_in, costs


def fixed_exits(tape, e, allout_idx, debit, cells):
    """One pass over the tape for several fixed (stop, target) cells: [(exit bar, basis, reason, is_stop) or None (VOID)]."""
    seg = slice(e, allout_idx)
    has = ~np.isnan(tape.o[seg])
    lo, hi = tape.l[seg], tape.h[seg]
    ks_cache, kt_cache = {}, {}
    x_all = None
    out = []
    for stop, target in cells:
        sp = debit * (1 - stop)
        tg = debit * (1 + (NONE_TARGET if target is None else target))
        if sp not in ks_cache:
            ks_cache[sp] = _first(has & (lo <= sp))
        if tg not in kt_cache:
            kt_cache[tg] = _first(has & (hi >= tg))
        ks, kt = ks_cache[sp], kt_cache[tg]
        if ks is not None and (kt is None or ks <= kt):
            i = e + ks
            out.append((i, tape.stop_basis(i, sp)[0], "FIXED STOP", True))
        elif kt is not None:
            i = e + kt
            out.append((i, tape.target_basis(i, tg)[0], "FIXED TARGET", False))
        else:
            if x_all is None:
                x_all = tape.next_print(allout_idx)
                x_all = -1 if x_all is None else x_all
            out.append(None if x_all < 0 else (x_all, float(tape.o[x_all]), "ALL OUT", False))
    return out


def signal_exit(tape, j, e, allout_idx, debit, exit_bars, stop=None):
    """A signal-type exit: (exit bar, basis, reason, is_stop, flip decision bar or None) or None (VOID).
    exit_bars: {decision bar: (reason, is_stop, flip)} for the held side; stop: fixed premium stop share of the debit."""
    ks = None
    sp = None
    if stop:
        sp = debit * (1 - stop)
        seg = slice(e, allout_idx)
        ks = _first(~np.isnan(tape.o[seg]) & (tape.l[seg] <= sp))
        ks = None if ks is None else e + ks
    kx = None
    for b in sorted(exit_bars):
        if j < b <= allout_idx - 1:
            kx = b
            break
    kx_eff = None if kx is None else max(kx, e)
    if ks is not None and (kx_eff is None or ks <= kx_eff):
        return ks, tape.stop_basis(ks, sp)[0], "FIXED STOP", True, None
    if kx_eff is not None:
        x = tape.next_print(kx_eff + 1)
        if x is None:
            return None
        reason, is_stop, flip = exit_bars[kx]
        return x, float(tape.o[x]), reason.split(":")[0], is_stop, (kx if flip else None)
    x = tape.next_print(allout_idx)
    return None if x is None else (x, float(tape.o[x]), "ALL OUT", False, None)


class DayTapes:
    """Option tapes of one (symbol, day): real (cached Alpaca bars, 0DTE and next expiry) or MODELED (built per pick)."""

    def __init__(self, ctx, mode, root=None, odays=None, ndays=None, calib=None, ivp=None):
        self.ctx, self.mode, self.calib, self.ivp = ctx, mode, calib, ivp
        self.real0 = self.real1 = None
        if mode == "real":
            self.real0 = data.read_option_day(ctx.sym, ctx.day, root) if (odays is None or ctx.day in odays) else {}
            self.real1 = None
            self.root, self.ndays = root, ndays
        self.md0 = self.md1 = None
        self.mult = {}

    def pool(self, rule, side, S):
        """Set ctx.tapes / ctx.tapes_next for the pick; returns a skip reason or None."""
        nxt = contracts.is_next(rule)
        if self.mode == "real":
            if nxt:
                if self.real1 is None:
                    ok = self.ndays is None or self.ctx.day in self.ndays
                    self.real1 = data.read_option_day(self.ctx.sym, self.ctx.day, self.root, want_trades=False, expiry="next") if ok else {}
                if not self.real1:
                    return "no next-expiry option data for the day"
                self.ctx.tapes_next = self.real1
            else:
                if not self.real0:
                    return "no 0DTE option data for the day"
                self.ctx.tapes = self.real0
            return None
        if self.ivp is None:
            return "MODELED: no IV proxy (fewer than 10 prior sessions)"
        k = (rule, side)
        if k not in self.mult:
            self.mult[k] = MD.multiplier_for(self.calib, rule, side)[0]
        iv = self.ivp * self.mult[k]
        if nxt:
            if self.md1 is None:
                self.md1 = MD.ModeledDay(self.ctx, expiry=MD.next_session(self.ctx.day))
            self.ctx.tapes_next = self.md1.pool(S, side, iv)
        else:
            if self.md0 is None:
                self.md0 = MD.ModeledDay(self.ctx)
            self.ctx.tapes = self.md0.pool(S, side, iv)
        return None


def run_day(ctx, studies, tapes, spread, col, cache=None):
    """Every study on one (symbol, day)."""
    cache = {} if cache is None else cache
    picks = {}
    allout_idx = EARLY_ALLOUT if ctx.early else ALLOUT["15:25"]
    for st in studies:
        sigs = day_signals(ctx, st["entry"], st["random_seed"], cache)
        if not sigs:
            continue
        evs = EXIT_SETS[st["exits"]]
        state = {ev: [-1, None] for ev in evs}                  # [last exit fill bar, flip decision bar]
        for sg in sorted(sigs, key=lambda s: s["idx"]):
            j, side = sg["idx"], sg["side"]
            col.signals[st["name"]] += 1
            flat = [ev for ev in evs if j >= state[ev][0] or (state[ev][1] is not None and j == state[ev][1])]
            for ev in evs:
                if ev not in flat:
                    col.skips[(st["name"], ev)]["busy: one position at a time"] += 1
            if not flat:
                continue
            dec = j + 1
            why = None
            if dec >= NO_NEW_AFTER:
                why = "no new trades after 15:30"
            elif dec >= allout_idx:
                why = "signal after the all-out time"
            tape = None
            if why is None:
                pk = (j, side, st["contract"])
                if pk not in picks:
                    if math.isnan(ctx.c[j]):
                        picks[pk] = (None, "no underlying close at the signal bar")
                    else:
                        r = tapes.pool(st["contract"], side, float(ctx.c[j]))
                        picks[pk] = (None, r) if r else contracts.pick(ctx, side, j, st["contract"])
                tape, info = picks[pk]
                if tape is None:
                    why = info
            fill = entry_fill(ctx, j, tape, spread, allout_idx) if why is None else None
            if why is None and fill is None:
                why = f"no option print in the {ENTRY_WAIT} minutes after the signal"
            if why is not None:
                for ev in flat:
                    col.skips[(st["name"], ev)][why] += 1
                continue
            e, b_in, hs_in, C, debit, costs = fill
            cells = [(ev, s, t) for ev, s, t in GRID if ev in flat]
            res = {}
            if cells:
                for (ev, _s, _t), r in zip(cells, fixed_exits(tape, e, allout_idx, debit, [(s, t) for _ev, s, t in cells])):
                    res[ev] = None if r is None else r + (None,)
            for ev in flat:
                if ev in res:
                    continue
                exits = (sg.get("exits") or {}).get(side) or {}
                if ev == "signal":
                    res[ev] = signal_exit(tape, j, e, allout_idx, debit, exits, SIGNAL_STOP)
                elif ev == "share_signal":
                    res[ev] = signal_exit(tape, j, e, allout_idx, debit, exits, None)
                elif ev == "hold":
                    res[ev] = signal_exit(tape, j, e, allout_idx, debit, {}, None)
            for ev in flat:
                r = res.get(ev)
                if r is None:
                    col.skips[(st["name"], ev)]["VOID: no option print to exit on before the close"] += 1
                    continue
                x, basis, reason, is_stop, flip = r
                hs = costs.hs(basis, x)
                legs = [(1.0, basis, hs, is_stop)]
                col.add(st["name"], ev, ctx.sym, ctx.day, side, j, e, x, reason, round(pnl(b_in, hs_in, legs, 1), 2),
                        round(pnl(b_in, hs_in, legs, 2), 2), b_in, basis)
                state[ev] = [x, flip]


def run(series_by_sym, studies, a, b, mode, root=None, calib=None, aux=None, spread=None, progress=None, limit_days=None):
    """The option pass over [a, b] for one period. mode "modeled" (HIST, needs calib) or "real" (DEV). Returns a Collector."""
    import time
    if mode not in ("modeled", "real"):
        raise ValueError(mode)
    if mode == "modeled" and calib is None:
        raise ValueError("MODELED option pass needs the calibration (data/sprint/calib_modeled.json)")
    spread = spread or SP.SpreadModel()
    col = Collector(studies, sorted(series_by_sym))
    t0 = time.time()
    for sym in sorted(series_by_sym):
        ser = series_by_sym[sym]
        days = [d for d in ser.days if a <= d <= b]
        if limit_days:
            days = days[:limit_days]
        odays = data.option_days(sym, root) if mode == "real" else None
        ndays = data.option_days(sym, root, "next") if mode == "real" else None
        for n, d in enumerate(days):
            ctx = data.DayContext(ser, d, {}, spread, aux=aux)
            ivp = MD.iv_proxy(ser, d) if mode == "modeled" else None
            tapes = DayTapes(ctx, mode, root, odays, ndays, calib, ivp)
            run_day(ctx, studies, tapes, spread, col)
            if progress and (n % 250 == 0 or n == len(days) - 1):
                progress(f"  option pass {mode} {sym} {d} ({n + 1}/{len(days)} sessions, {time.time() - t0:.0f}s)")
    return col


def write(path, frame):
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        frame.to_csv(f, index=False)
