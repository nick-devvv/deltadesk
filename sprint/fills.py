"""sprint/fills.py - the sprint's fill rules for long options (docs/research/SPRINT_PLAN.md, "Cost model and fills").
These rules are the contract every simulated trade obeys; tests/test_sprint_fills.py checks each one.

Prices: Alpaca 1-minute option bars (open = first trade of the minute, high/low, close = last trade) and, when pulled,
the option's individual trades. There are no historical quotes, so:
  * BUY  (entry)  = traded price + k x half-spread
  * SELL (exit)   = traded price - k x half-spread                      (never below 0)
  * k = 1 is the base; "2x slippage" uses k = 2 on every fill and k = 2 x 2 = 4 on stop exits (the extra k on stops,
    mirroring Option Alpha's "+$0.06 on stops" at 2x). Decisions (which bar, which trigger) are identical in both
    cases: only the fill prices change, so one simulated path gives the base and the 2x result.
  * Fees: $0.65 per contract per side.
Timing:
  * ENTRY at the next bar after the signal: the open of the first option bar with a print in the ENTRY_WAIT minutes
    after the signal bar (no print in a minute -> no fill that minute; none in the window -> the entry is missed).
  * Exits decided on a FINISHED underlying bar (level stops on 1-minute closes, level targets, trails, if-flat,
    all-out) fill at the next option print after that bar (the open of the first later bar with a print).
  * Premium triggers (the % ceiling, breakeven and lock stops, giveback, plan A's T1) act on the option's own
    prices inside the bar, like live quotes:
      - STOP  (trigger S): the bar's low <= S. Fill basis = the WORSE of S and the next real price after the touch:
          open <= S (gapped through between prints) -> the open;
          trades pulled -> the first trade at or below S in that minute;
          bars only     -> S itself (the bar traded from above S down to its low, so S lies inside the bar's range).
      - TARGET (trigger T): the bar's high >= T. Fill basis = the open if it is already >= T, else T.
  * Same bar, stop and target both inside it -> the stop counts.
  * A fill basis is always a price inside the traded range [low, high] of an existing bar in the fill minute (or an
    actual trade): the engine never fills at a price the option did not trade, and never in a minute with no print.
"""
import math

import numpy as np

FEE = 0.65
ENTRY_WAIT = 3              # minutes after the signal bar in which the entry may fill
MULT = 100


def stop_k(k):
    """Half-spreads paid on a stop exit: k at base, 2k at 2x (the extra k on stops)."""
    return k if k <= 1 else 2 * k


def buy_px(basis, hs, k):
    return basis + k * hs


def sell_px(basis, hs, k):
    return max(0.0, basis - k * hs)


class OptionTape:
    """One option contract's minute bars for one session (index 0 = 09:30 bar ... 389 = 15:59 bar) plus, optionally,
    its trades (minute index, sequence, price)."""

    def __init__(self, symbol, right, strike, o, h, l, c, v, trades=None):
        self.symbol, self.right, self.strike = symbol, right, float(strike)
        self.o, self.h, self.l, self.c, self.v = (np.asarray(x, float) for x in (o, h, l, c, v))
        self.trades = trades                    # None or (minute_idx int array, price float array), time-sorted
        self._tidx = None
        if trades is not None and len(trades[0]):
            mi = np.asarray(trades[0], int)
            self._tidx = (np.searchsorted(mi, np.arange(391), side="left"), np.asarray(trades[1], float))

    def has_print(self, i):
        return 0 <= i < len(self.o) and not math.isnan(self.o[i])

    def next_print(self, i, last=None):
        """First minute >= i with a print (<= last), or None."""
        last = len(self.o) - 1 if last is None else min(last, len(self.o) - 1)
        for j in range(max(i, 0), last + 1):
            if not math.isnan(self.o[j]):
                return j
        return None

    def last_close(self, i, max_age=5):
        """The last traded price at or before bar i (within max_age minutes), as known at the END of bar i."""
        for j in range(i, max(-1, i - max_age - 1), -1):
            if 0 <= j < len(self.c) and not math.isnan(self.c[j]):
                return float(self.c[j])
        return None

    def minute_trades(self, i):
        if self._tidx is None:
            return None
        a, b = self._tidx[0][i], self._tidx[0][i + 1]
        return self._tidx[1][a:b] if b > a else None

    def stop_basis(self, i, trigger):
        """Fill basis for a premium stop touched in bar i (caller checked low <= trigger)."""
        o = float(self.o[i])
        if o <= trigger:
            return o, "gap through: next real price (bar open)"
        tr = self.minute_trades(i)
        if tr is not None:
            hit = tr[tr <= trigger + 1e-12]
            if len(hit):
                return float(min(trigger, hit[0])), "first trade at/below the stop"
        return float(trigger), "stop price (inside the bar's traded range)"

    def target_basis(self, i, trigger):
        o = float(self.o[i])
        if o >= trigger:
            return o, "opened beyond the target (bar open)"
        tr = self.minute_trades(i)
        if tr is not None:
            hit = tr[tr >= trigger - 1e-12]
            if len(hit):
                return float(max(trigger, hit[0])), "first trade at/above the target"
        return float(trigger), "target price (inside the bar's traded range)"


def pnl(entry_basis, entry_hs, legs, k):
    """P/L in dollars for one contract unit. legs: [(qty_fraction, basis, hs, is_stop)], fractions sum to 1."""
    e = buy_px(entry_basis, entry_hs, k)
    tot = -FEE
    for q, basis, hs, is_stop in legs:
        x = sell_px(basis, hs, stop_k(k) if is_stop else k)
        tot += q * ((x - e) * MULT - FEE)
    return tot
