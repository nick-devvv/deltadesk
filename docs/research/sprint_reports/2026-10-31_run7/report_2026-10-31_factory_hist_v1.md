# Sprint report: factory_hist_v1 (HIST), MODELED-SPREAD, MODELED (BS, calibrated IV)

Generated 2026-10-31 21:28 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint2` in 15.9 min. Spec sha256 `97a63d8026d7a1660e53638f14d05465da766280c6ca8542026738cdb2ca6c93`.

**Every number below is a BACKTEST HIST (2016-2023 history, never used to choose these rules), MODELED (BS, calibrated IV).** Stock prices are Alpaca 1-minute bars, 2016-01-04 to 2024-01-31 (history from 2015-11-01 feeds indicators only). **Option prices are not real**: every contract is priced with Black-Scholes from the stock's bars at one implied vol per day = the 20-session realized 1-minute volatility (prior sessions only) x a multiplier fitted on DEV's real option trades (`d03-12t07|C` x0.798, `d06-15t10|P` x1.041, `d40-55t45|C` x0.831, `d40-55t45|P` x0.956, `d55-75t65|C` x0.821, `d55-75t65|P` x1.025; calibration sha256 `4d50070991c1`). Fills: modeled price +/- a half-spread, **MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Nothing here is a live or paper fill.

Data: IWM: 2033 sessions, QQQ: 2033 sessions, SPY: 2033 sessions. Runs in this spec: 21. Trials counted for the deflated Sharpe: 3406 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Idealizations of the model (SPRINT_PLAN Amendment 5): a 0DTE contract is priced every session (before Nov 2022 SPY/QQQ/IWM did not list an expiry every weekday; see the Mon/Wed/Fri vs Tue/Thu lines); one flat IV per day (no smile, no intraday IV change: real puts gain extra value when IV jumps in a selloff, real calls lose some when IV falls in a rally); a price every minute; the 2% half-spread may be optimistic for thinner years (the 5% rerun is the check). Sessions without an IV proxy (fewer than 10 prior sessions) are skipped.

**Cost caveat:** MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: SPRINT_PLAN Amendment 9 (pre-registered 2026-11-01, before any factory run): the 10-year strategy factory. Every strategy with code, one run each, SPY+QQQ+IWM pooled, desk fills, 2% half-spread ($0.005 floor), $0.65/contract/side, 1 contract, one position at a time per run and symbol: noise (its own exit), orb15/30/60, vwap_macd, pd_retest, flush (both sides, plain exit), failed_break calls, failed_high puts (plain exit), far-OTM calls (d03-12t07) and puts (d06-15t10) at 10:00, 10:30, 11:00, 12:00, 13:00 and 14:00 (-95% stop, +9900% target, all out 15:25). 21 runs. No pass-2 robustness (tools/sprint_factory.py does its own checks). HIST = 2016-01-04..2024-01-31 (history from 2015-11-01 for indicators only); option prices MODELED (BS, calibrated IV) with run 4's data/sprint/calib_modeled.json.

## Exit families side by side: current plan vs best level target vs best trail

Best of each family by expectancy among runs with at least 60 trades (else the best with any trades).

| family | run | config | trades | win% | avg win | avg loss | exp $ | PF | PF 2x | max DD | CI95 exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plain stop + time | factory_hist_v1-008 | failed_break prem tpnone tb 15:25 | 1901 | 6.40 | 187.21 | -15.31 | -2.31 | 0.84 | 0.59 | -5932.14 | -5.25..1.11 |


## Fixed premium stop / target runs (MODELED (BS, calibrated IV))

Each row: a fixed stop/target of the debit on the modeled option price, desk fill rules (inside the bar, same-bar stop wins), all out at the run's time. `2m+` = profitable two-month blocks.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| factory_hist_v1-010 | SPY+QQQ+IWM | time_1000 | C | 95/9900 | desk | d03-12t07 | - | 5438 | 9.40 | 1.74 | 1.31 | 1.09 | -1763.69 | 27/49 |  |
| factory_hist_v1-016 | SPY+QQQ+IWM | time_1000 | P | 95/9900 | desk | d06-15t10 | - | 4869 | 8.60 | -1.48 | 0.87 | 0.78 | -7199.85 | 15/49 |  |
| factory_hist_v1-011 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | - | 5484 | 8.70 | 1.67 | 1.30 | 1.08 | -1697.49 | 29/49 |  |
| factory_hist_v1-017 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | - | 4731 | 8.10 | -3.26 | 0.71 | 0.64 | -15475.78 | 10/49 |  |
| factory_hist_v1-012 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | - | 5445 | 8.10 | 0.94 | 1.18 | 0.97 | -3559.86 | 23/49 |  |
| factory_hist_v1-018 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | - | 4670 | 7.80 | -3.28 | 0.70 | 0.63 | -15775.64 | 12/49 |  |
| factory_hist_v1-013 | SPY+QQQ+IWM | time_1200 | C | 95/9900 | desk | d03-12t07 | - | 5471 | 6.80 | -0.25 | 0.95 | 0.77 | -5583.64 | 16/49 |  |
| factory_hist_v1-019 | SPY+QQQ+IWM | time_1200 | P | 95/9900 | desk | d06-15t10 | - | 4427 | 7.30 | -3.60 | 0.65 | 0.57 | -16012.14 | 12/49 |  |
| factory_hist_v1-014 | SPY+QQQ+IWM | time_1300 | C | 95/9900 | desk | d03-12t07 | - | 5416 | 6.80 | -0.39 | 0.91 | 0.72 | -7708.90 | 14/49 |  |
| factory_hist_v1-020 | SPY+QQQ+IWM | time_1300 | P | 95/9900 | desk | d06-15t10 | - | 4053 | 8.40 | -2.95 | 0.67 | 0.58 | -12777.32 | 10/49 |  |
| factory_hist_v1-015 | SPY+QQQ+IWM | time_1400 | C | 95/9900 | desk | d03-12t07 | - | 5347 | 7.40 | -0.23 | 0.93 | 0.71 | -4745.70 | 18/49 |  |
| factory_hist_v1-021 | SPY+QQQ+IWM | time_1400 | P | 95/9900 | desk | d06-15t10 | - | 3607 | 9.10 | -2.42 | 0.68 | 0.58 | -9359.16 | 11/49 |  |


## Robustness on the top 0 runs

## All other runs (sorted by expectancy; fixed stop/target runs are in the cross-check table)

`sig` = signals seen, `skip%` = share not traded (no contract, level stop beyond the ceiling, R:R minimum, busy, no print); the top skip reasons per run are in the run log's notes.

| run | config | sig | skip% | n | win% | avg win | avg loss | exp | PF | PF2x | maxDD | kept | pRR | aRR | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| factory_hist_v1-008 | failed_break prem tpnone tb 15:25 | 3994 | 52.40 | 1901 | 6.40 | 187.21 | -15.31 | -2.31 | 0.84 | 0.59 | -5932.14 | 0.05 | - | -0.24 | 0.00 |
| factory_hist_v1-001 | noise nois tpnone tb 15:25 d55-75t65 | 19324 | 63.49 | 7056 | 13.30 | 115.53 | -20.99 | -2.80 | 0.85 | 0.58 | -20440.55 | 0.05 | - | -0.17 | 0.00 |
| factory_hist_v1-002 | orb15 prem tpnone tb 15:25 | 7956 | 37.41 | 4980 | 6.80 | 181.66 | -16.94 | -3.50 | 0.78 | 0.55 | -17431.25 | 0.03 | - | -0.17 | 0.00 |
| factory_hist_v1-005 | vwap_macd prem tpnone tb 15:25 | 3676 | 49.16 | 1869 | 4.90 | 171.19 | -13.12 | -4.05 | 0.68 | 0.46 | -7867.02 | 0.01 | - | -0.42 | 0.00 |
| factory_hist_v1-006 | pd_retest prem tpnone tb 15:25 | 824 | 53.76 | 381 | 5.00 | 144.11 | -11.87 | -4.09 | 0.64 | 0.44 | -2363.48 | -0.01 | - | -0.32 | 0.00 |
| factory_hist_v1-007 | flush prem tpnone tb 15:25 | 5107 | 49.74 | 2567 | 3.70 | 161.87 | -12.00 | -5.50 | 0.52 | 0.35 | -14438.81 | -0.06 | - | -0.56 | 0.00 |
| factory_hist_v1-003 | orb30 prem tpnone tb 15:25 | 6781 | 37.96 | 4207 | 5.70 | 175.77 | -16.47 | -5.55 | 0.64 | 0.46 | -23345.63 | -0.03 | - | -0.31 | 0.00 |
| factory_hist_v1-004 | orb60 prem tpnone tb 15:25 | 5080 | 40.47 | 3024 | 5.30 | 164.67 | -15.49 | -5.96 | 0.59 | 0.42 | -18025.74 | -0.05 | - | -0.37 | 0.00 |
| factory_hist_v1-009 | failed_high prem tpnone tb 15:25 | 4560 | 49.41 | 2307 | 5.00 | 202.40 | -17.06 | -6.02 | 0.63 | 0.44 | -13954.27 | -0.03 | - | -0.43 | 0.00 |


Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_factory_hist_v1_2026-10-31.csv.gz`.

Labels: BACKTEST HIST (2016-2023 history, never used to choose these rules), MODELED (BS, calibrated IV). Spread: MODELED-SPREAD. No real option price was used. Not financial advice: evidence for Nick to decide.
