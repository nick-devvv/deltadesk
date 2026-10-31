# Sprint results, run 3 (Chart's computer, 2026-10-31)

Code `5b624e9`, 113 sprint tests passed on Chart's computer. Reports and study outputs: `docs/research/sprint_reports/2026-10-31_run3/`. 108 new runs are logged in `docs/research/sprint_runs.csv` (1,723 rows); the report counts 3,187 trials for the deflated Sharpe.

**Labels:** every number is a BACKTEST on DEV (Aug 2024 to Jun 2026, in-sample) with a MODELED spread (2%; `@s5` = 5%), 1 contract per signal. No locked period has been touched.

## 1. Option Alpha's Top Backtests family: far OTM 0DTE options held (otm_v1, 54 runs)

- **Unfiltered: about break-even to losing.** 10:30 puts PF 0.82-0.94, 10:30 calls 0.76-0.83, 11:00 calls 1.01-1.05, 11:00 puts 0.73-0.79 (1,310-1,420 trades each).
- **Early take-profits make it worse:** +300 / +500 / +1000% gave PF 0.50-0.70.
- **Put-hedge proxy filters on 10:30 puts** (VIXY percentile <= 40%, VIXY not up > 1%, at or above the prior close, Wed-Fri, skip third Friday): PF 1.65-2.15 and PF 2x 1.51-1.96 on 351-377 trades.
  - Best is otm_v1-008: 361 trades, +$15.96, PF 1.97, PF 2x 1.81, 5% stress PF 1.86.
  - The filter beats skipping the same number of random days (p 0.01-0.03). It beats matched random entries, and the one nudge tried (15:25) keeps PF > 1.1.
  - **Fails:** Jan-Jun 2026 lost (-$1,393, PF 0.35); only 3 of 11 two-month blocks were profitable (Oct-Nov 2025 alone made +$6,233); negative without the best 5 trades (-$1,101).
- The same filters on calls lose (PF 0.22-0.60). 11:00 puts with them: PF 1.15-1.62.
- **Call-bounce proxy on 11:00 calls** (VIXY percentile >= 60%, below the prior close, skip third Friday):
  - 43-44 trades, +$130-154 a trade, PF 8.7-10.8, PF 2x 7.9-9.9, 5% stress PF 10.2; beats random day-skips (p 0.002-0.008).
  - But **under 60 trades, and all in 2 two-month blocks**: VIXY's percentile was >= 60% only in a few high-volatility stretches, and April 2025 dominates. It's one market episode, not a sample.
- Bounce filters on puts, and hedge filters on 11:00 calls, lose.

## 2. Learner (walk-forward, scored only on months after its training)

No model passed its pre-registered check on any strategy:

| strategy (OOS trades) | base exp / PF | best model | its exp / PF / trades | beats random skips |
|---|---|---|---|---|
| setups_v2-034 (160) | 42.23 / 2.68 | logit | 75.39 / 4.23 / 29 | 79.5% (needs 95%) |
| setups_v2-012 (318) | 23.25 / 1.96 | logit | 47.16 / 2.87 / 88 | 76% |
| setups_v2-001 (357) | 20.17 / 1.74 | ridge | 44.80 / 2.41 / 129 | 86.5% |
| otm_v1-008 (253) | 15.79 / 1.92 | buckets | 15.97 / 1.91 / 237 | 33.5% |

- The models raise the average trade by skipping most trades. They don't beat skipping the same number of trades at random often enough to count.
- They hurt the far-OTM puts.
- The likely reason: these strategies earn from about 20-30 winning days in 23 months, which is too few for a model to learn from.
- One direction repeats across all three failed-break fits: a prior day that closed up is bad for the calls (`f_prev_ret` weight -0.50 to -1.25). That matches Chart's look at v2-034. The gap weight flips sign between fits. Not proven.

## 3. Combined book (study auto: best candidate per family)

| sleeve | trades | per session | exp $ | PF | PF 2x | total $ | max DD | Sharpe |
|---|---|---|---|---|---|---|---|---|
| setups_v2-034 (failed-break calls) | 207 | 0.43 | 33.87 | 2.36 | 1.66 | 7,010.60 | -1,217.78 | 1.10 |
| otm_v1-008 (10:30 hedge puts) | 361 | 0.75 | 15.96 | 1.97 | 1.81 | 5,761.05 | -1,532.11 | 0.75 |
| otm_v1-026 (11:00 hedge puts) | 351 | 0.73 | 7.28 | 1.62 | 1.46 | 2,555.06 | -1,628.91 | 0.45 |
| **book** | 919 | 1.92 | 16.68 | 2.00 | 1.66 | 15,326.71 | -2,199.57 | 1.09 |

- **Daily P/L correlation:** failed-break calls vs the hedge puts -0.01, so they diversify each other. The two put sleeves +0.78: one idea counted twice, with 310 overlapping trade pairs.
- The daily mean's 95% interval (-$3.99, +$76.13) still includes zero.
- A $150 desk daily stop skipped one entry and changed little.

## 4. Where this leaves the sprint

- Nothing has passed every pre-registered robustness check, so nothing is frozen and L1/L2 stay locked.
- **The near-misses share one failure: "positive without the best 5 trades".** That's built into the "small losses, big wins" shape. With about 23 months of option prices, such a strategy has only about 20-40 winning days, so five of them carry the result.
- Telling a real edge from luck needs more history (tastytrade's 10+ years, or SPX data elsewhere) or forward paper trades.
- Candidates for that next step:
  - v2-034 or v2-012 (failed-break calls);
  - otm_v1-008 (10:30 hedge puts);
  - otm_v1-039/042 (11:00 bounce calls), as a watch-only idea given its single episode.
