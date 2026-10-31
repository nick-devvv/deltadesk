# Sprint results, run 2 (Chart's computer, 2026-10-31)

Code `eff94d1`, 105 sprint tests passed on Chart's computer. Reports: `docs/research/sprint_reports/2026-10-31_run2/`. All 182 new runs are logged in `docs/research/sprint_runs.csv`, which now holds 1,615 rows; the report counts 2,827 trials for the deflated Sharpe. Next-expiry bars pulled: 479 sessions per symbol, 186 MB.

**Labels:** every number is a BACKTEST on Alpaca 1-minute option prices with a MODELED spread (2% half-spread; `@s5` = 5%), $0.65 per contract per side, 1 contract.
- setups_v2 runs on DEV (Aug 2024 to Jun 2026, in-sample).
- oa_crosscheck_v2 runs on NOT_SEEN_BY_OA (Aug 2024 to Oct 29 2025).
- No locked period has been touched.

## 1. Failed-break deep dive (setups_v2, DEV)

| run | what changed | trades | exp $ | PF | PF 2x | exp @5% | failed checks |
|---|---|---|---|---|---|---|---|
| 001 | base (= v1-049) | 676 | 10.95 | 1.47 | 1.03 | 2.48 | Aug-Dec 2024, without best 5 |
| 034 | level stop instead of premium ceiling | 207 | 33.87 | 2.36 | 1.66 | 31.90 (34 trades) | Aug-Dec 2024 (-$272.58), without best 5 (-$376.92) |
| 008 | probe <= 0.25 ATR | 217 | 23.34 | 1.99 | 1.41 | 16.18 | Aug-Dec 2024, without best 5 (-$2,486) |
| 002 | SPY only | 257 | 19.55 | 1.79 | 1.26 | 13.94 | Aug-Dec 2024, without best 5 |
| 012 | opening-range lows only | 429 | 18.57 | 1.78 | 1.27 | 8.71 | **Aug-Dec 2024 only** (-$609, PF 0.71); positive without best 5 (+$688); 10 of 12 two-month blocks up |
| 005 | SPY+QQQ (in-sample choice) | 489 | 16.40 | 1.63 | 1.14 | 6.70 | **Aug-Dec 2024 only** (-$109, PF 0.96); positive without best 5 (+$232) |
| 054 | VIXY falling filter | 291 | 15.66 | 1.74 | 1.22 | 9.60 | **only "beats random day-skips"** (p = 0.30) |
| 047 | noise_trend filter | 29 | 108.89 | 4.69 | 3.31 | 98.68 | under 60 trades; beats random day-skips (p = 0.02) |
| 053 | VIXY percentile >= 60% | 53 | 49.61 | 2.47 | 1.76 | 43.62 | under 60 trades (p = 0.10) |

- **Exits, settled:** on failed-break, every exit that takes profit early loses money:
  - every trail: breakeven moves PF 0.60-1.05, profit-lock ladders 0.66-0.84, giveback 0.40-0.42;
  - the level targets B / C / E: PF 0.28-0.69;
  - the time table A: PF 0.88;
  - the far fixed targets: PF 0.82 at +100%, 0.98 at +200%.
- The money comes from a few calls held to 15:25 on days that run up. The best exit is a small stop and no target.
- **What hurt:**
  - the put mirror (failed_high): PF 0.59;
  - next-expiry contracts: PF 1.11 / 0.98;
  - higher delta: PF 1.23 / 1.39;
  - IWM: PF 0.79;
  - the bot risk rules: PF 1.22 / 1.25. They cut the trades that follow losses, and some of those are the big winners;
  - trend_only: no trades.
- **Status:** no run passes every robustness check, so under SPRINT_PLAN Amendment 2 nothing is frozen and the locked periods stay untouched.
  - Closest: 012 and 005 (each fails only Aug-Dec 2024) and 054 (fails only the random day-skip test).
  - Deflated Sharpe is 0.000 for all of them after 2,827 trials.

**Chart's loss analysis of v2-034** (Nick, 2026-10-31; in-sample, its own script):
- 186 of 207 trades lose about $28 within minutes; 21 winners held to 15:25 pay for everything. 2025-04-09 alone made $4,014.22.
- Winners are trend-up days.
- Skip candidates it found: prior day up > 0.3%, opening range < 0.4%, Fridays. Fit on 2025, they roughly doubled 2026 expectancy but didn't fix 2024. Without the best 5 trades, every year stays negative.
- These ideas go to the walk-forward learner in run 3. `f_prev_ret` (prior-day return) was added to the entry features for that.

## 2. Option Alpha's calm-market filters on unseen data (oa_crosscheck_v2, NOT_SEEN_BY_OA)

- SPY ORB60 calls 50/100 (OA's T1 shape): PF 0.93 with no filter. With the calm-market filters:
  - VIXY percentile <= 40%: PF 0.79;
  - VIXY not rising: 0.85;
  - small gap up: 0.78;
  - all three: 0.82.
- 20/60: PF 0.31-0.57.
- QQQ calls: worse.
- No filter makes the calls profitable. One (VIXY not rising, on 20/60) beat random day-skips (p = 0.01) but still lost money (PF 0.57).
- The "calm, risk-on" theme from Option Alpha's optimizer (OA-S1-087 and similar) does not hold on the 15 months OA never saw.
- Puts 50/100 with all three filters: 9 trades, too few to judge.

## 3. Next (run 3)

- `otm_v1`: Option Alpha's Top Backtests family, far OTM 0DTE options held.
- The walk-forward learner and the combined book (`tools/sprint_study.py auto`).
- An extra learner run on the base failed-break (v2-001, 676 trades) and the opening-range version (v2-012, 429 trades), where there are enough trades to learn from.
