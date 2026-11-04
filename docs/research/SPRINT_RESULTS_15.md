# Sprint results, round 15 (BACKTEST)

Source: sprint_results15.zip from Chart (commit 048ef23). Claude recomputed p, Sharpe, CAGR and max DD from the daily file: 0 differences.
PASS 2008-01-02..2024-01-31, 10 bps per side, bar p < 0.01 plus items 2-5. SPY: Sharpe 0.52, CAGR 9.8%, max DD -51.9%.

**All 5 FAIL.**

| Trial | p | Sharpe | CAGR | Max DD | Failed | Kept w/o 10 best months | DEV Sharpe |
|---|---|---|---|---|---|---|---|
| G1 sector trend-momentum | 0.0051 | 0.53 | 8.1% | -22.3% | 3, 5 | 37% | 0.54 |
| G2 Donchian | 0.0090 | 0.55 | 3.5% | -7.4% | 5 | 17% | 0.36 |
| G3 alpha rotation | 0.0204 | 0.40 | 7.3% | -60.3% | 1, 2, 3, 5 | 27% | 0.84 |
| P1 T6+A2+RSI2 (in-sample pick) | 0.0006 | 0.65 | 5.7% | -12.4% | 3, 5 | 41% | 0.17 |
| P2 P1 + risk control (in-sample pick) | 0.0011 | 0.64 | 5.1% | -11.1% | 3, 5 | 41% | 0.17 |

Readings:
- P1/P2 clear the p bar, but item 3 says the pick is not special: 95% of random 3-of-6 mixes of the same pool reach 0.71. The
  real finding is that mixing these trend/defensive rules beats cash with a small drawdown; this mix is not better than others.
- Every rule fails item 5: the extra return sits in a few months (mostly crisis periods), so it is lumpy.
- 100% of noisy runs stayed above 0 for all five: delays and extra costs do not kill them.
- L1 stays locked (Nick, 2026-11-03).
