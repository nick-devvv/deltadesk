# Sprint report: hist_v1 (HIST), MODELED-SPREAD, MODELED (BS, calibrated IV)

Generated 2026-10-31 16:07 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint2` in 11.7 min. Spec sha256 `7167aae6885071701288bd6aa1c957fdfb52bc6ac9c6d4d25755451e2caa624d`.

**Every number below is a BACKTEST HIST (2016-2023 history, never used to choose these rules), MODELED (BS, calibrated IV).** Stock prices are Alpaca 1-minute bars, 2016-01-04 to 2024-01-31 (history from 2015-11-01 feeds indicators only). **Option prices are not real**: every contract is priced with Black-Scholes from the stock's bars at one implied vol per day = the 20-session realized 1-minute volatility (prior sessions only) x a multiplier fitted on DEV's real option trades (`d03-12t07|C` x0.798, `d06-15t10|P` x1.041, `d40-55t45|C` x0.831; calibration sha256 `4d50070991c1`). Fills: modeled price +/- a half-spread, **MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Nothing here is a live or paper fill.

Data: IWM: 2033 sessions, QQQ: 2033 sessions, SPY: 2033 sessions. Runs in this spec: 6. Trials counted for the deflated Sharpe: 3361 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Idealizations of the model (SPRINT_PLAN Amendment 5): a 0DTE contract is priced every session (before Nov 2022 SPY/QQQ/IWM did not list an expiry every weekday; see the Mon/Wed/Fri vs Tue/Thu lines); one flat IV per day (no smile, no intraday IV change: real puts gain extra value when IV jumps in a selloff, real calls lose some when IV falls in a rally); a price every minute; the 2% half-spread may be optimistic for thinner years (the 5% rerun is the check). Sessions without an IV proxy (fewer than 10 prior sessions) are skipped.

## Pre-registered HIST reading (MODELED (BS, calibrated IV))

SPRINT_PLAN Amendment 5: "holds on HIST (MODELED)" needs every check below, and counts only for a strategy that passed its DEV validation (`/home/box/sprint/data/sprint/validation_hist_val_v1.json`).

### fb (hist_v1-001): **does not hold**

1901 trades, win 6.4%, avg win 187.21, avg loss -15.31, expectancy -2.31, PF 0.84, PF 2x 0.59, max DD -5932.14, CI95 [-5.25, 1.11], without the best 5 -8063.15. Mon/Wed/Fri: n=1075 exp -1.51 PF 0.90; Tue/Thu: n=826 exp -3.36 PF 0.77 [MODELED (BS, calibrated IV)]

- [x] at least 60 trades
- [ ] expectancy > 0
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in at least 6 of the 8 years 2016-2023 (1 of 8)
- [ ] positive without its best 5 trades

### fb_or (hist_v1-002): **does not hold**

1235 trades, win 7.3%, avg win 175.88, avg loss -16.12, expectancy -2.13, PF 0.86, PF 2x 0.60, max DD -3837.67, CI95 [-6.1, 2.34], without the best 5 -5861.56. Mon/Wed/Fri: n=688 exp -2.54 PF 0.83; Tue/Thu: n=547 exp -1.62 PF 0.89 [MODELED (BS, calibrated IV)]

- [x] at least 60 trades
- [ ] expectancy > 0
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in at least 6 of the 8 years 2016-2023 (1 of 8)
- [ ] positive without its best 5 trades

### otm_put_base (hist_v1-003): **does not hold**

4731 trades, win 8.1%, avg win 100.13, avg loss -12.34, expectancy -3.26, PF 0.71, PF 2x 0.64, max DD -15475.78, CI95 [-5.14, -1.17], without the best 5 -18390.98. Mon/Wed/Fri: n=2800 exp -3.48 PF 0.69; Tue/Thu: n=1931 exp -2.95 PF 0.74 [MODELED (BS, calibrated IV)]

- [x] at least 60 trades
- [ ] expectancy > 0
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in at least 6 of the 8 years 2016-2023 (1 of 8)
- [ ] positive without its best 5 trades

### otm_put (hist_v1-004): **does not hold**

988 trades, win 8.1%, avg win 114.99, avg loss -11.57, expectancy -1.33, PF 0.88, PF 2x 0.78, max DD -4315.52, CI95 [-5.85, 4.39], without the best 5 -3875.29. Mon/Wed/Fri: n=635 exp -2.91 PF 0.73; Tue/Thu: n=353 exp 1.52 PF 1.15 [MODELED (BS, calibrated IV)]

- [x] at least 60 trades
- [ ] expectancy > 0
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in at least 6 of the 8 years 2016-2023 (2 of 8)
- [ ] positive without its best 5 trades
- [ ] filter beats random day-skips of its twin, p <= 0.05 (p = 0.126)

### otm_bounce_base (hist_v1-005): **does not hold**

5445 trades, win 8.1%, avg win 76.28, avg loss -5.69, expectancy 0.94, PF 1.18, PF 2x 0.97, max DD -3559.86, CI95 [-0.71, 2.73], without the best 5 1764.08. Mon/Wed/Fri: n=3215 exp 1.73 PF 1.33; Tue/Thu: n=2230 exp -0.18 PF 0.96 [MODELED (BS, calibrated IV)]

- [x] at least 60 trades
- [x] expectancy > 0
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in at least 6 of the 8 years 2016-2023 (4 of 8)
- [x] positive without its best 5 trades

### otm_bounce (hist_v1-006): **UNRELIABLE** (failed DEV validation): numbers shown, no verdict

211 trades, win 12.8%, avg win 111.43, avg loss -8.10, expectancy 7.19, PF 2.02, PF 2x 1.75, max DD -851.23, CI95 [-3.17, 21.87], without the best 5 -154.49. Mon/Wed/Fri: n=134 exp 9.21 PF 2.24; Tue/Thu: n=77 exp 3.68 PF 1.57 [MODELED (BS, calibrated IV)]

- [x] at least 60 trades
- [x] expectancy > 0
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in at least 6 of the 8 years 2016-2023 (2 of 8)
- [ ] positive without its best 5 trades
- [ ] filter beats random day-skips of its twin, p <= 0.05 (p = 0.084)

**Cost caveat:** MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: SPRINT_PLAN Amendment 5, Layer 2 (pre-registered 2026-10-31, before any HIST pull or run): the sprint's six surviving runs, rules unchanged, on HIST = 2016-01-04..2024-01-31 (stock history from 2015-11-01 for indicators only; ends before L2). Alpaca has no option prices there, so every option is MODELED (BS, calibrated IV): Black-Scholes on the stock bars at IV = 20-session realized 1-minute vol x the DEV multiplier of the run's contract rule and side (data/sprint/calib_modeled.json). Each block's DEV validation (hist_val_v1) decides whether its numbers are RELIABLE or UNRELIABLE. Costs: 2% half-spread, $0.005 floor, $0.65/contract/side; PF at 2x slippage; the 5% rerun is the stress. 6 runs.

## Exit families side by side: current plan vs best level target vs best trail

Best of each family by expectancy among runs with at least 60 trades (else the best with any trades).

| family | run | config | trades | win% | avg win | avg loss | exp $ | PF | PF 2x | max DD | CI95 exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plain stop + time | hist_v1-002 | failed_break_or prem tpnone tb 15:25 | 1235 | 7.30 | 175.88 | -16.12 | -2.13 | 0.86 | 0.60 | -3837.67 | -6.1..2.34 |


## Fixed premium stop / target runs (MODELED (BS, calibrated IV))

Each row: a fixed stop/target of the debit on the modeled option price, desk fill rules (inside the bar, same-bar stop wins), all out at the run's time. `2m+` = profitable two-month blocks.

Regime filters: `vixy_pctl_le40` / `vixy_pctl_ge60` = IV-rank **proxy: VIXY percentile** (share of the 252 split-adjusted daily VIXY closes ending at the prior close that are at or below it; the window skips the locked months, and VIXY's decay biases it low next to a true IV rank); `vixy_not_rising` / `vixy_rising_1pct` = VIXY's last finished 1-minute close at the decision vs its prior close x 1.01 (**proxy: VIXY**); `gap_side_075` = open vs prior close in (0%, +0.75%] for calls, [-0.75%, 0%) for puts. A run with several filters needs all of them. In-sample leads from Option Alpha's optimizer, tested on data OA never saw.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hist_v1-003 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | - | 4731 | 8.10 | -3.26 | 0.71 | 0.64 | -15475.78 | 10/49 |  |
| hist_v1-004 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 988 | 8.10 | -1.33 | 0.88 | 0.78 | -4315.52 | 10/39 |  |
| hist_v1-005 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | - | 5445 | 8.10 | 0.94 | 1.18 | 0.97 | -3559.86 | 23/49 |  |
| hist_v1-006 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 211 | 12.80 | 7.19 | 2.02 | 1.75 | -851.23 | 4/11 |  |


## Robustness on the top 6 runs

### hist_v1-006: SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex

Trades 211, win 13%, avg win 111.43, avg loss -8.10, expectancy **7.19** (2x slippage 5.94), PF 2.02 (2x 1.75), max DD -851.23, % of peak kept 0.25, planned R:R - vs actual 1.03, expectancy CI95 [-3.17, 21.87], deflated Sharpe 0.000 (N=3361).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 4 of 11 (info)
- [x] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries
- [ ] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| 2016 (Jan 04-Dec 31) | 0 | - | - | - |
| 2017 | 0 | - | - | - |
| 2018 | 60 | 416.00 | 6.93 | 2.43 |
| 2019 | 21 | -146.30 | -6.97 | 0.00 |
| 2020 | 127 | 1265.73 | 9.97 | 2.22 |
| 2021 | 0 | - | - | - |
| 2022 | 3 | -17.90 | -5.97 | 0.00 |
| 2023 | 0 | - | - | - |
| Jan 2024 | 0 | - | - | - |
| 2018 Q1 vol spike | 3 | -19.90 | -6.63 | 0.00 |
| 2020 Feb-May | 76 | -23.53 | -0.31 | 0.97 |
| 2022 bear market | 3 | -17.90 | -5.97 | 0.00 |


Sides: calls n=211 exp 7.19 PF 2.02; puts n=0 exp - PF -
Symbols: IWM n=72 exp 0.51 PF 1.09; QQQ n=68 exp 11.56 PF 2.72; SPY n=71 exp 9.78 PF 2.12
Weekdays: Mon/Wed/Fri n=134 exp 9.21 PF 2.24; Tue/Thu n=77 exp 3.68 PF 1.57
Without the best 5 trades: net -154.49, expectancy -0.75.
One-step nudges: allout=15:50 n=211 PF 2.33 exp 9.56
Matched random entries (5 paths): expectancy 2.87, 7.44, 6.99, 3.58, 10.36; the run beats 60% of paths.
Filter vs random day-skips (twin hist_v1-005, 1921 days removed): p = 0.084 (filtered exp 7.19, random-skip mean 0.93).
Exit reasons: {'ALL OUT': 208, 'FIXED STOP': 3}.
Median option MFE 0.778, MAE -0.846; median stock MFE $1.370; median distance from the stock's price at the option's peak to the nearest level $0.058; median minutes held 265.
Skipped signals: VIXY percentile below 60% 4824, VIXY percentile unknown (needs 252 daily closes up to the prior session) 755, day_down: at or above the prior close at the decision 296, monthly expiration (third Friday) skipped 7, no contract with BS-EST |delta| in 0.03-0.12 5.

### hist_v1-005: SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d03-12t07

Trades 5445, win 8%, avg win 76.28, avg loss -5.69, expectancy **0.94** (2x slippage -0.16), PF 1.18 (2x 0.97), max DD -3559.86, % of peak kept 0.21, planned R:R - vs actual 0.08, expectancy CI95 [-0.71, 2.73], deflated Sharpe 0.000 (N=3361).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [x] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 23 of 49 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| 2016 (Jan 04-Dec 31) | 605 | 393.92 | 0.65 | 1.23 |
| 2017 | 672 | -1226.98 | -1.83 | 0.29 |
| 2018 | 606 | 605.20 | 1.00 | 1.24 |
| 2019 | 563 | -1433.58 | -2.55 | 0.39 |
| 2020 | 713 | -685.96 | -0.96 | 0.86 |
| 2021 | 752 | 267.64 | 0.36 | 1.06 |
| 2022 | 752 | 5063.40 | 6.73 | 1.81 |
| 2023 | 719 | 1812.82 | 2.52 | 1.44 |
| Jan 2024 | 63 | 345.46 | 5.48 | 2.19 |
| 2018 Q1 vol spike | 165 | -94.32 | -0.57 | 0.86 |
| 2020 Feb-May | 233 | -699.88 | -3.00 | 0.66 |
| 2022 bear market | 587 | 2814.12 | 4.79 | 1.57 |


Sides: calls n=5445 exp 0.94 PF 1.18; puts n=0 exp - PF -
Symbols: IWM n=1736 exp -0.47 PF 0.89; QQQ n=1880 exp 1.02 PF 1.19; SPY n=1829 exp 2.22 PF 1.38
Weekdays: Mon/Wed/Fri n=3215 exp 1.73 PF 1.33; Tue/Thu n=2230 exp -0.18 PF 0.96
Without the best 5 trades: net 1764.08, expectancy 0.32.
One-step nudges: allout=15:50 n=5443 PF 1.25 exp 1.36
Matched random entries (5 paths): expectancy 0.50, 0.23, -0.26, 0.43, 0.50; the run beats 100% of paths.
Exit reasons: {'ALL OUT': 5428, 'FIXED STOP': 9, 'FIXED TARGET': 8}.
Median option MFE 0.481, MAE -0.714; median stock MFE $0.760; median distance from the stock's price at the option's peak to the nearest level $0.030; median minutes held 265.
Skipped signals: no contract with BS-EST |delta| in 0.03-0.12 623, MODELED: no IV proxy (fewer than 10 prior sessions) 30.

### hist_v1-004: SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex

Trades 988, win 8%, avg win 114.99, avg loss -11.57, expectancy **-1.33** (2x slippage -2.51), PF 0.88 (2x 0.78), max DD -4315.52, % of peak kept 0.09, planned R:R - vs actual -0.11, expectancy CI95 [-5.85, 4.39], deflated Sharpe 0.000 (N=3361).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 10 of 39 (info)
- [x] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries
- [ ] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| 2016 (Jan 04-Dec 31) | 0 | - | - | - |
| 2017 | 98 | -99.96 | -1.02 | 0.80 |
| 2018 | 70 | -484.00 | -6.91 | 0.01 |
| 2019 | 147 | -802.22 | -5.46 | 0.29 |
| 2020 | 71 | -311.41 | -4.39 | 0.57 |
| 2021 | 227 | -1516.71 | -6.68 | 0.48 |
| 2022 | 140 | 1724.45 | 12.32 | 1.81 |
| 2023 | 214 | 355.14 | 1.66 | 1.15 |
| Jan 2024 | 21 | -175.46 | -8.36 | 0.14 |
| 2018 Q1 vol spike | 21 | -158.30 | -7.54 | 0.00 |
| 2020 Feb-May | 15 | 177.42 | 11.83 | 2.71 |
| 2022 bear market | 101 | 2390.85 | 23.67 | 2.63 |


Sides: calls n=0 exp - PF -; puts n=988 exp -1.33 PF 0.88
Symbols: IWM n=300 exp -0.75 PF 0.92; QQQ n=314 exp -4.57 PF 0.62; SPY n=374 exp 0.93 PF 1.08
Weekdays: Mon/Wed/Fri n=635 exp -2.91 PF 0.73; Tue/Thu n=353 exp 1.52 PF 1.15
Without the best 5 trades: net -3875.29, expectancy -3.94.
One-step nudges: allout=15:50 n=988 PF 1.13 exp 1.38
Matched random entries (5 paths): expectancy 1.80, 0.86, 1.20, 0.07, 1.84; the run beats 0% of paths.
Filter vs random day-skips (twin hist_v1-003, 1433 days removed): p = 0.126 (filtered exp -1.33, random-skip mean -3.29).
Exit reasons: {'ALL OUT': 931, 'FIXED STOP': 56, 'FIXED TARGET': 1}.
Median option MFE 0.467, MAE -0.895; median stock MFE $0.850; median distance from the stock's price at the option's peak to the nearest level $0.040; median minutes held 295.0.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 1623, day_up: below the prior close at the decision 1025, wed_fri: Monday or Tuesday 860, VIXY percentile above 40% (not calm) 720, VIXY percentile unknown (needs 252 daily closes up to the prior session) 545, no contract with BS-EST |delta| in 0.06-0.15 248, monthly expiration (third Friday) skipped 86, no VIXY prior close (VIX proxy) 3.

### hist_v1-002: failed_break_or prem tpnone tb 15:25

Trades 1235, win 7%, avg win 175.88, avg loss -16.12, expectancy **-2.13** (2x slippage -8.03), PF 0.86 (2x 0.60), max DD -3837.67, % of peak kept 0.05, planned R:R - vs actual -0.21, expectancy CI95 [-6.1, 2.34], deflated Sharpe 0.000 (N=3361).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 17 of 49 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| 2016 (Jan 04-Dec 31) | 68 | 231.61 | 3.41 | 1.55 |
| 2017 | 41 | -171.52 | -4.18 | 0.17 |
| 2018 | 136 | -425.25 | -3.13 | 0.72 |
| 2019 | 107 | -394.73 | -3.69 | 0.60 |
| 2020 | 215 | 957.03 | 4.45 | 1.25 |
| 2021 | 181 | -1213.75 | -6.71 | 0.55 |
| 2022 | 281 | -883.61 | -3.14 | 0.85 |
| 2023 | 189 | -830.13 | -4.39 | 0.71 |
| Jan 2024 | 17 | 97.17 | 5.72 | 1.44 |
| 2018 Q1 vol spike | 33 | 63.01 | 1.91 | 1.17 |
| 2020 Feb-May | 89 | 1608.32 | 18.07 | 1.89 |
| 2022 bear market | 229 | -476.59 | -2.08 | 0.90 |


Sides: calls n=1235 exp -2.13 PF 0.86; puts n=0 exp - PF -
Symbols: IWM n=361 exp -3.90 PF 0.66; QQQ n=403 exp 1.75 PF 1.11; SPY n=471 exp -4.10 PF 0.76
Weekdays: Mon/Wed/Fri n=688 exp -2.54 PF 0.83; Tue/Thu n=547 exp -1.62 PF 0.89
Without the best 5 trades: net -5861.56, expectancy -4.77.
One-step nudges: allout=15:50 n=1235 PF 0.86 exp -2.09
Matched random entries (5 paths): expectancy -4.58, -4.45, -7.51, -7.65, -7.92; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 1143, 'ALL OUT': 92}.
Median option MFE 0.141, MAE -0.199; median stock MFE $0.250; median distance from the stock's price at the option's peak to the nearest level $0.030; median minutes held 5.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 1034, busy: one position at a time 371, MODELED: no IV proxy (fewer than 10 prior sessions) 16.

### hist_v1-001: failed_break prem tpnone tb 15:25

Trades 1901, win 6%, avg win 187.21, avg loss -15.31, expectancy **-2.31** (2x slippage -8.04), PF 0.84 (2x 0.59), max DD -5932.14, % of peak kept 0.05, planned R:R - vs actual -0.24, expectancy CI95 [-5.25, 1.11], deflated Sharpe 0.000 (N=3361).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 15 of 49 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| 2016 (Jan 04-Dec 31) | 93 | 274.01 | 2.95 | 1.48 |
| 2017 | 75 | -238.39 | -3.18 | 0.34 |
| 2018 | 219 | -578.29 | -2.64 | 0.76 |
| 2019 | 167 | -537.88 | -3.22 | 0.64 |
| 2020 | 306 | 194.62 | 0.64 | 1.04 |
| 2021 | 281 | -1831.69 | -6.52 | 0.55 |
| 2022 | 430 | -1724.02 | -4.01 | 0.79 |
| 2023 | 309 | -3.92 | -0.01 | 1.00 |
| Jan 2024 | 21 | 47.89 | 2.28 | 1.18 |
| 2018 Q1 vol spike | 59 | 147.35 | 2.50 | 1.24 |
| 2020 Feb-May | 126 | 1140.70 | 9.05 | 1.47 |
| 2022 bear market | 357 | -1271.84 | -3.56 | 0.82 |


Sides: calls n=1901 exp -2.31 PF 0.84; puts n=0 exp - PF -
Symbols: IWM n=557 exp -3.28 PF 0.70; QQQ n=618 exp 3.28 PF 1.21; SPY n=726 exp -6.33 PF 0.61
Weekdays: Mon/Wed/Fri n=1075 exp -1.51 PF 0.90; Tue/Thu n=826 exp -3.36 PF 0.77
Without the best 5 trades: net -8063.15, expectancy -4.25.
One-step nudges: entry=failed_break_w3 n=1778 PF 0.82 exp -2.63; entry=failed_break_w10 n=1936 PF 0.84 exp -2.30; entry=failed_break_p025 n=651 PF 1.16 exp 2.29; entry=failed_break_p075 n=2547 PF 0.83 exp -2.35; allout=15:50 n=1901 PF 0.83 exp -2.44
Matched random entries (5 paths): expectancy -4.71, -4.84, -7.78, -7.93, -8.27; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 1777, 'ALL OUT': 124}.
Median option MFE 0.128, MAE -0.197; median stock MFE $0.230; median distance from the stock's price at the option's peak to the nearest level $0.030; median minutes held 4.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 1587, busy: one position at a time 473, MODELED: no IV proxy (fewer than 10 prior sessions) 33.

### hist_v1-003: SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10

Trades 4731, win 8%, avg win 100.13, avg loss -12.34, expectancy **-3.26** (2x slippage -4.44), PF 0.71 (2x 0.64), max DD -15475.78, % of peak kept -0.00, planned R:R - vs actual -0.18, expectancy CI95 [-5.14, -1.17], deflated Sharpe 0.000 (N=3361).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 10 of 49 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| 2016 (Jan 04-Dec 31) | 352 | -1642.98 | -4.67 | 0.23 |
| 2017 | 310 | -996.34 | -3.21 | 0.37 |
| 2018 | 546 | 2139.55 | 3.92 | 1.47 |
| 2019 | 540 | -1471.41 | -2.72 | 0.66 |
| 2020 | 693 | -626.75 | -0.90 | 0.94 |
| 2021 | 754 | -2835.51 | -3.76 | 0.70 |
| 2022 | 752 | -4141.88 | -5.51 | 0.67 |
| 2023 | 722 | -5189.64 | -7.19 | 0.41 |
| Jan 2024 | 62 | -663.78 | -10.71 | 0.06 |
| 2018 Q1 vol spike | 128 | 997.18 | 7.79 | 1.91 |
| 2020 Feb-May | 230 | -766.31 | -3.33 | 0.82 |
| 2022 bear market | 587 | -1830.21 | -3.12 | 0.81 |


Sides: calls n=0 exp - PF -; puts n=4731 exp -3.26 PF 0.71
Symbols: IWM n=1508 exp -4.20 PF 0.55; QQQ n=1545 exp -3.42 PF 0.73; SPY n=1678 exp -2.28 PF 0.81
Weekdays: Mon/Wed/Fri n=2800 exp -3.48 PF 0.69; Tue/Thu n=1931 exp -2.95 PF 0.74
Without the best 5 trades: net -18390.98, expectancy -3.89.
One-step nudges: allout=15:50 n=4730 PF 0.79 exp -2.46
Matched random entries (5 paths): expectancy -3.21, -3.84, -2.71, -3.02, -3.70; the run beats 40% of paths.
Exit reasons: {'ALL OUT': 4309, 'FIXED STOP': 417, 'FIXED TARGET': 5}.
Median option MFE 0.569, MAE -0.895; median stock MFE $0.960; median distance from the stock's price at the option's peak to the nearest level $0.045; median minutes held 295.
Skipped signals: no contract with BS-EST |delta| in 0.06-0.15 1337, MODELED: no IV proxy (fewer than 10 prior sessions) 30.

## Filters vs random day-skips (every filtered run with its unfiltered twin)

| run | config | twin | days skipped | filtered exp | random-skip exp | p |
|---|---|---|---|---|---|---|
| hist_v1-004 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | hist_v1-003 | 1433 | -1.33 | -3.29 | 0.13 |
| hist_v1-006 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | hist_v1-005 | 1921 | 7.19 | 0.93 | 0.08 |


## All other runs (sorted by expectancy; fixed stop/target runs are in the cross-check table)

`sig` = signals seen, `skip%` = share not traded (no contract, level stop beyond the ceiling, R:R minimum, busy, no print); the top skip reasons per run are in the run log's notes.

| run | config | sig | skip% | n | win% | avg win | avg loss | exp | PF | PF2x | maxDD | kept | pRR | aRR | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hist_v1-002 | failed_break_or prem tpnone tb 15:25 | 2656 | 53.50 | 1235 | 7.30 | 175.88 | -16.12 | -2.13 | 0.86 | 0.60 | -3837.67 | 0.05 | - | -0.21 | 0.00 |
| hist_v1-001 | failed_break prem tpnone tb 15:25 | 3994 | 52.40 | 1901 | 6.40 | 187.21 | -15.31 | -2.31 | 0.84 | 0.59 | -5932.14 | 0.05 | - | -0.24 | 0.00 |


Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_hist_v1_2026-10-31.csv.gz`.

Labels: BACKTEST HIST (2016-2023 history, never used to choose these rules), MODELED (BS, calibrated IV). Spread: MODELED-SPREAD. No real option price was used. Not financial advice: evidence for Nick to decide.
