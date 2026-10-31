"""noise_v2.py - v4 index ledger `noise_v2` (docs/STRATEGY_PLAN.md section 3.2). PRE-REGISTERED, unvalidated.

Rules (frozen 2026-10-31, before any result):
  * Entries: exactly the `noise` ledger's entries (Zarattini, Aziz & Barbon 2024 noise area; half-hour checks
    10:00-15:00; price above the upper band -> calls, below the lower band -> puts; delta 0.55-0.75, 1 contract).
  * Exit ONLY on a half-hour (HH:00 / HH:30) close through max(upper band, VWAP) for calls or min(lower band, VWAP) for
    puts, as in the paper (a move to the other side of the band is also through that stop, so no separate reversal rule).
  * A disaster stop at -50% of the premium, on the bid, replaces the 20% premium line.
  * All out 15:25 ET (desk rule; the paper holds to the close).
  * Fills: the noise ledger's execution model (noise1), quote dated after the check. SPY and QQQ reported separately.
Pass/fail is decided by docs/STRATEGY_PLAN.md section 5 (pre-registration in docs/research/STRATEGY_REGISTRY.md).
"""
import core
import noise_variants as NV

VERSION = "2026-11-02.v4-noise_v2"
LEDGER = "noise_v2"
DISASTER_PCT = 0.50


class NoiseV2(NV.Variant):
    ledger = LEDGER
    book = "index"
    version = VERSION
    reversal_exit = False

    def premium_stop(self, fill, slip, fee):
        return core.cents_down(fill * (1 - DISASTER_PCT))

    def premium_stop_text(self):
        return "-50% disaster stop"


V = NoiseV2()


def tick(ticker, snap, chain_rows_fn, now=None):
    return NV.tick(V, ticker, snap, chain_rows_fn, now)


def manage(p, now=None):
    return NV.manage(V, p, now)
