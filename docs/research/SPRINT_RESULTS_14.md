# Sprint results, round 14 (BACKTEST)

Source: sprint_results14.zip and sprint_data14.zip from Chart (commit 1b35f0b). Claude re-ran every number from the raw
data: 0 differences. ETF PASS 2008-01-02..2024-01-31; French PASS 1927-07..1997-12; 10 bps per side.

**All 12 trials FAIL item 1** (p < 0.05/12 = 0.0042). SPY on ETF PASS: Sharpe 0.52, CAGR 9.8%, max DD -51.9%.

| Trial | p | Sharpe | CAGR | Max DD | Notes |
|---|---|---|---|---|---|
| A2 multi-asset risk parity | 0.0094 | 0.53 | 3.7% | -6.7% | closest; beat shifted versions; keeps 19% without its best 10 months |
| E2 IEF vs T-bills | 0.030 | 0.47 | 3.5% | -10.4% | edge sits in a few months |
| C2 IBS hold | 0.041 | 0.39 | 5.1% | -34.9% | beat random entries; fails noise (36%) |
| B2 low-vol + trend (French) | 0.081 vs market | 0.64 | 9.3% | -35.9% | passed every other item |
| B1 low-vol (French) | 0.045 vs market | 0.56 | 10.2% | -78.4% | |
| F1 learner | 0.075 | 0.29 | 3.4% | -17.8% | worse than random selectors (95th pct 0.61) |
| F2 learner + risk control | 0.22 | 0.17 | 1.8% | -12.2% | worse than random selectors |
| C1 IBS one day | 0.97 | -0.40 | -2.5% | -53.1% | loses |

A1, A3, C3 and E1 also failed item 1 (full table in the zip's round14 report).

Readings:
- The learner (pick by the last 36 months) chose worse than random: recent winners did not keep winning.
- Multi-asset trend gives very low drawdowns, but most of its extra return came from a few months.
- B2 is the most robust, but not significant against the market.

Next: round 15 (SPRINT_PLAN "Round 15 pre-registration").
