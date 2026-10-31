# Sprint report: hist_v1 (HIST), MODELED-SPREAD 5.0% (sensitivity), MODELED (BS, calibrated IV)

Generated 2026-10-31 16:11 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint2` in 3.3 min. Spec sha256 `7167aae6885071701288bd6aa1c957fdfb52bc6ac9c6d4d25755451e2caa624d`.

**Every number below is a BACKTEST HIST (2016-2023 history, never used to choose these rules), MODELED (BS, calibrated IV).** Stock prices are Alpaca 1-minute bars, 2016-01-04 to 2024-01-31 (history from 2015-11-01 feeds indicators only). **Option prices are not real**: every contract is priced with Black-Scholes from the stock's bars at one implied vol per day = the 20-session realized 1-minute volatility (prior sessions only) x a multiplier fitted on DEV's real option trades (`d03-12t07|C` x0.798, `d06-15t10|P` x1.041, `d40-55t45|C` x0.831; calibration sha256 `4d50070991c1`). Fills: modeled price +/- a half-spread, **MODELED-SPREAD 5.0% of premium for every symbol (a SENSITIVITY run, not the pre-registered 2% default), floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Nothing here is a live or paper fill.

Data: IWM: 2033 sessions, QQQ: 2033 sessions, SPY: 2033 sessions. Runs in this spec: 6. Trials counted for the deflated Sharpe: 3367 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Idealizations of the model (SPRINT_PLAN Amendment 5): a 0DTE contract is priced every session (before Nov 2022 SPY/QQQ/IWM did not list an expiry every weekday; see the Mon/Wed/Fri vs Tue/Thu lines); one flat IV per day (no smile, no intraday IV change: real puts gain extra value when IV jumps in a selloff, real calls lose some when IV falls in a rally); a price every minute; the 2% half-spread may be optimistic for thinner years (the 5% rerun is the check). Sessions without an IV proxy (fewer than 10 prior sessions) are skipped.

## Pre-registered HIST reading (MODELED (BS, calibrated IV))

**This is a cost stress run: the checks below are information only. The pre-registered reading is the base-cost run's.**

SPRINT_PLAN Amendment 5: "holds on HIST (MODELED)" needs every check below, and counts only for a strategy that passed its DEV validation (`/home/box/sprint/data/sprint/validation_hist_val_v1.json`).

### fb (hist_v1-001@s5): **does not hold**

1917 trades, win 4.1%, avg win 190.71, avg loss -15.82, expectancy -7.42, PF 0.51, PF 2x 0.24, max DD -15043.03, CI95 [-9.67, -4.83], without the best 5 -17478.41. Mon/Wed/Fri: n=1083 exp -6.87 PF 0.55; Tue/Thu: n=834 exp -8.14 PF 0.46 [MODELED (BS, calibrated IV)]

- [x] at least 60 trades
- [ ] expectancy > 0
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in at least 6 of the 8 years 2016-2023 (0 of 8)
- [ ] positive without its best 5 trades

### fb_or (hist_v1-002@s5): **does not hold**

1239 trades, win 4.9%, avg win 164.62, avg loss -16.65, expectancy -7.73, PF 0.51, PF 2x 0.24, max DD -10017.50, CI95 [-10.5, -4.7], without the best 5 -12239.47. Mon/Wed/Fri: n=689 exp -8.41 PF 0.48; Tue/Thu: n=550 exp -6.87 PF 0.56 [MODELED (BS, calibrated IV)]

- [x] at least 60 trades
- [ ] expectancy > 0
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in at least 6 of the 8 years 2016-2023 (0 of 8)
- [ ] positive without its best 5 trades

### otm_put_base (hist_v1-003@s5): **does not hold**

4731 trades, win 8.0%, avg win 97.29, avg loss -12.49, expectancy -3.70, PF 0.68, PF 2x 0.58, max DD -17528.33, CI95 [-5.52, -1.67], without the best 5 -20351.93. Mon/Wed/Fri: n=2800 exp -3.90 PF 0.66; Tue/Thu: n=1931 exp -3.39 PF 0.70 [MODELED (BS, calibrated IV)]

- [x] at least 60 trades
- [ ] expectancy > 0
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in at least 6 of the 8 years 2016-2023 (1 of 8)
- [ ] positive without its best 5 trades

### otm_put (hist_v1-004@s5): **does not hold**

988 trades, win 8.1%, avg win 110.92, avg loss -11.70, expectancy -1.77, PF 0.83, PF 2x 0.71, max DD -4384.76, CI95 [-6.17, 3.77], without the best 5 -4231.66. Mon/Wed/Fri: n=635 exp -3.30 PF 0.70; Tue/Thu: n=353 exp 0.99 PF 1.10 [MODELED (BS, calibrated IV)]

- [x] at least 60 trades
- [ ] expectancy > 0
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in at least 6 of the 8 years 2016-2023 (2 of 8)
- [ ] positive without its best 5 trades
- [ ] filter beats random day-skips of its twin, p <= 0.05 (p = 0.12)

### otm_bounce_base (hist_v1-005@s5): **does not hold**

5445 trades, win 8.1%, avg win 73.79, avg loss -5.70, expectancy 0.73, PF 1.14, PF 2x 0.91, max DD -4037.28, CI95 [-0.87, 2.46], without the best 5 725.72. Mon/Wed/Fri: n=3215 exp 1.49 PF 1.29; Tue/Thu: n=2230 exp -0.36 PF 0.93 [MODELED (BS, calibrated IV)]

- [x] at least 60 trades
- [x] expectancy > 0
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in at least 6 of the 8 years 2016-2023 (4 of 8)
- [x] positive without its best 5 trades

### otm_bounce (hist_v1-006@s5): **UNRELIABLE** (failed DEV validation): numbers shown, no verdict

211 trades, win 12.8%, avg win 107.81, avg loss -8.14, expectancy 6.70, PF 1.94, PF 2x 1.62, max DD -866.04, CI95 [-3.33, 20.93], without the best 5 -206.79. Mon/Wed/Fri: n=134 exp 8.63 PF 2.15; Tue/Thu: n=77 exp 3.33 PF 1.52 [MODELED (BS, calibrated IV)]

- [x] at least 60 trades
- [x] expectancy > 0
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in at least 6 of the 8 years 2016-2023 (2 of 8)
- [ ] positive without its best 5 trades
- [ ] filter beats random day-skips of its twin, p <= 0.05 (p = 0.086)

**Cost caveat:** MODELED-SPREAD 5.0% of premium for every symbol (a SENSITIVITY run, not the pre-registered 2% default), floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: SPRINT_PLAN Amendment 5, Layer 2 (pre-registered 2026-10-31, before any HIST pull or run): the sprint's six surviving runs, rules unchanged, on HIST = 2016-01-04..2024-01-31 (stock history from 2015-11-01 for indicators only; ends before L2). Alpaca has no option prices there, so every option is MODELED (BS, calibrated IV): Black-Scholes on the stock bars at IV = 20-session realized 1-minute vol x the DEV multiplier of the run's contract rule and side (data/sprint/calib_modeled.json). Each block's DEV validation (hist_val_v1) decides whether its numbers are RELIABLE or UNRELIABLE. Costs: 2% half-spread, $0.005 floor, $0.65/contract/side; PF at 2x slippage; the 5% rerun is the stress. 6 runs.

## Exit families side by side: current plan vs best level target vs best trail

Best of each family by expectancy among runs with at least 60 trades (else the best with any trades).

| family | run | config | trades | win% | avg win | avg loss | exp $ | PF | PF 2x | max DD | CI95 exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plain stop + time | hist_v1-001@s5 | failed_break prem tpnone tb 15:25 | 1917 | 4.10 | 190.71 | -15.82 | -7.42 | 0.51 | 0.24 | -15043.03 | -9.67..-4.83 |


## Fixed premium stop / target runs (MODELED (BS, calibrated IV))

Each row: a fixed stop/target of the debit on the modeled option price, desk fill rules (inside the bar, same-bar stop wins), all out at the run's time. `2m+` = profitable two-month blocks.

Regime filters: `vixy_pctl_le40` / `vixy_pctl_ge60` = IV-rank **proxy: VIXY percentile** (share of the 252 split-adjusted daily VIXY closes ending at the prior close that are at or below it; the window skips the locked months, and VIXY's decay biases it low next to a true IV rank); `vixy_not_rising` / `vixy_rising_1pct` = VIXY's last finished 1-minute close at the decision vs its prior close x 1.01 (**proxy: VIXY**); `gap_side_075` = open vs prior close in (0%, +0.75%] for calls, [-0.75%, 0%) for puts. A run with several filters needs all of them. In-sample leads from Option Alpha's optimizer, tested on data OA never saw.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hist_v1-003@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | - | 4731 | 8.00 | -3.70 | 0.68 | 0.58 | -17528.33 | 10/49 |  |
| hist_v1-004@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 988 | 8.10 | -1.77 | 0.83 | 0.71 | -4384.76 | 10/39 |  |
| hist_v1-005@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | - | 5445 | 8.10 | 0.73 | 1.14 | 0.91 | -4037.28 | 23/49 |  |
| hist_v1-006@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 211 | 12.80 | 6.70 | 1.94 | 1.62 | -866.04 | 4/11 |  |


## Robustness on the top 0 runs

## Filters vs random day-skips (every filtered run with its unfiltered twin)

| run | config | twin | days skipped | filtered exp | random-skip exp | p |
|---|---|---|---|---|---|---|
| hist_v1-004@s5 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | hist_v1-003@s5 | 1433 | -1.77 | -3.72 | 0.12 |
| hist_v1-006@s5 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | hist_v1-005@s5 | 1921 | 6.70 | 0.72 | 0.09 |


## All other runs (sorted by expectancy; fixed stop/target runs are in the cross-check table)

`sig` = signals seen, `skip%` = share not traded (no contract, level stop beyond the ceiling, R:R minimum, busy, no print); the top skip reasons per run are in the run log's notes.

| run | config | sig | skip% | n | win% | avg win | avg loss | exp | PF | PF2x | maxDD | kept | pRR | aRR | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hist_v1-001@s5 | failed_break prem tpnone tb 15:25 | 3994 | 52.00 | 1917 | 4.10 | 190.71 | -15.82 | -7.42 | 0.51 | 0.24 | -15043.03 | 0.04 | - | -0.55 | 0.00 |
| hist_v1-002@s5 | failed_break_or prem tpnone tb 15:25 | 2656 | 53.35 | 1239 | 4.90 | 164.62 | -16.65 | -7.73 | 0.51 | 0.24 | -10017.50 | 0.03 | - | -0.52 | 0.00 |


Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_hist_v1@s5_2026-10-31.csv.gz`.

Labels: BACKTEST HIST (2016-2023 history, never used to choose these rules), MODELED (BS, calibrated IV). Spread: MODELED-SPREAD 5.0% (sensitivity). No real option price was used. Not financial advice: evidence for Nick to decide.
