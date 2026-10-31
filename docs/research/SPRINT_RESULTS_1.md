# Sprint results, run 1 (Chart's computer, 2026-10-31)

Code `704455c`, sprint engine `2026-10-31.sprint1`, 87 sprint tests passed on Chart's computer. Full reports: `docs/research/sprint_reports/2026-10-31_run1/`. Every run is in `docs/research/sprint_runs.csv` (1,336 desk-engine rows added: 697 base runs plus their 5% half-spread stress reruns; 1,433 rows in all with the Option Alpha runs).

**Labels:** every number here is a BACKTEST on Alpaca 1-minute option trades with a MODELED spread (half-spread 2% of premium for SPY/QQQ/IWM; 5% as the stress run), $0.65 per contract per side, 1 contract. DEV = Aug 2024 to Jun 2026, in-sample. NOT_SEEN_BY_OA = Aug 2024 to Oct 29 2025, which Option Alpha never saw. No locked period (L1, L2) has been touched.

## 1. The exit question (ORB breakout, both sides, DEV)

| exit family | best run | trades | win % | exp $/trade | PF | PF 2x | max DD |
|---|---|---|---|---|---|---|---|
| plain: premium-ceiling stop, hold to 15:25 | orb_exits_v1-003 (ORB60) | 1035 | 6.4 | -2.60 | 0.88 | 0.62 | -8,527 |
| A: current fixed-% plan (~1:1) | orb_exits_v1-008 (ORB60) | 1035 | 21.5 | -6.01 | 0.47 | 0.23 | -6,243 |
| B: sell before the first level | orb_exits_v1-087 (ORB60, R:R >= 2.5) | 78 | 15.4 | -3.48 | 0.63 | 0.37 | -297 |
| best trail (breakeven at +8%) | orb_exits_v1-170 (ORB60) | 835 | 1.6 | -2.86 | 0.73 | 0.38 | -4,046 |
| best C/D/E | orb_exits_v1-106 (ORB15) | 1509 | 14.3 | -6.53 | 0.46 | 0.23 | -9,855 |

- No exit made the ORB breakout profitable on 0DTE options. All 195 runs lose.
- The current ~1:1 plan is the worst family. The less an exit cuts winners, the less it loses.
- Key levels did not prove themselves: in the level test, real levels beat made-up levels at the same distance in 10% of 20 seeds (run 176) and 80% (run 087, which still loses money).

## 2. Option Alpha's winners on data it never saw (Aug 2024 to Oct 2025)

- SPY ORB60 calls with a 1:3 stop/target (in-sample PF 1.30-1.33 on Option Alpha): PF 0.40-0.59 here. The calm-market optimizer filters did not rescue them.
- T1 (ORB60 calls, 50/100): PF 0.93-1.00.
- Best: ORB60 **puts** with a 50/100 stop/target. QQQ (run 080): 110 trades, +$10.12/trade, PF 1.17, PF 2x 1.01. SPY (run 024): 124 trades, +$8.36/trade, PF 1.18, PF 2x 1.02. Both **fail** the random-entry test: random put entries with the same exit made more (run 080 beats 60% of 5 random paths, run 024 beats 0%). Both are negative without their best 5 trades. The ORB signal adds nothing here; the exit and a few falling months did the work. Dropped.

## 3. Bot setups and the noise band (DEV)

- **Failed-break calls, plain exit (setups_v1-049)** is the only run of 697 with PF >= 1.25: 676 trades, win 8.9%, avg win $384.90, avg loss -$25.47, +$10.95/trade, PF 1.47, PF 2x 1.03, max DD -$2,123, expectancy CI95 -$2.80 to +$28.57. Beats all 5 matched random-entry paths (random: -$2.26 to -$10.04). Plateau on the one nudge tried (all out 15:50: PF 1.44).
  - Fails two robustness checks: lost money in Aug-Dec 2024 (146 trades, PF 0.94), and is negative without its best 5 trades (net -$384.57).
  - By symbol: SPY PF 1.79, QQQ PF 1.47, IWM PF 0.79.
  - The same entries with a 20/60 fixed stop/target lose (setups_v1-054: PF 0.77). The profit comes from a few calls held to 15:25.
  - Deflated Sharpe 0.000 after 1,424 trials. Status: **lead, not a finalist.**
- VWAP + 2-minute MACD puts, plain exit (setups_v1-019): 297 trades, PF 1.13, PF 2x 0.78. Fails.
- Noise band variants on these exits: PF 0.51-0.87. (The `noise` ledger itself is unchanged and keeps running.)
- Prior-day retest puts: PF 1.15-1.24 but only 16-47 trades and PF 2x at most 0.56. Prior-day retest calls and the flush reversal lose.
- setups_v1 was not rerun at the 5% stress spread; its PF 2x (double the 2% half-spread) is the cost check.

## 4. Totals

- 697 base runs in the desk engine (484 with at least 60 trades). Among those 484: PF > 1: 11; PF >= 1.25: 1; PF 2x > 1: 3. (Counting runs under 60 trades: 32, 7 and 7.)
- No run passed every robustness check, so nothing is frozen and the locked periods stay untouched.

## 5. Next

1. Failed-break deep dive (setups_v2): nudge its own numbers (re-close window, probe depth, which support levels), SPY/QQQ vs all three (labeled in-sample: chosen after seeing results), trails added one at a time on the plain exit, day-type filters vs random day-skips, the bot risk rules, and a weekly-expiry contract.
2. Step 5b (`oa_crosscheck_v2`, calm-regime filters on Option Alpha's call rules) is optional now: the base rules lost on unseen data at PF 0.40-0.59.
