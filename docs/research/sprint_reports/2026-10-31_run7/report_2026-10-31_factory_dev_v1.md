# Sprint report: factory_dev_v1 (DEV), MODELED-SPREAD

Generated 2026-10-31 21:32 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint2` in 4.0 min. Spec sha256 `9765725b4f81fb85ea938af971578f046886cd125d88d281841a807c01d1281b`.

**Every number below is a BACKTEST in-sample (DEV)** on Alpaca 1-minute bars, 2024-08-01 to 2026-06-30. Option fills are real traded prices +/- a half-spread: **MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Deltas are BS-EST (Black-Scholes from the option's price). Nothing here is a live or paper fill.

Data: IWM: 479 sessions, QQQ: 479 sessions, SPY: 479 sessions. Runs in this spec: 21. Trials counted for the deflated Sharpe: 3427 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Known limits: July 2024 is locked (L2), so early-August 2024 sessions have partial history; news and VIX are unknown in the backtest (rules that need them never fire); a contract needs BS-EST |delta| inside the band, so some signals have no contract (counted as skips).

**Cost caveat:** MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: SPRINT_PLAN Amendment 9 (pre-registered 2026-11-01, before any factory run): the 10-year strategy factory. Every strategy with code, one run each, SPY+QQQ+IWM pooled, desk fills, 2% half-spread ($0.005 floor), $0.65/contract/side, 1 contract, one position at a time per run and symbol: noise (its own exit), orb15/30/60, vwap_macd, pd_retest, flush (both sides, plain exit), failed_break calls, failed_high puts (plain exit), far-OTM calls (d03-12t07) and puts (d06-15t10) at 10:00, 10:30, 11:00, 12:00, 13:00 and 14:00 (-95% stop, +9900% target, all out 15:25). 21 runs. No pass-2 robustness (tools/sprint_factory.py does its own checks). DEV = 2024-08-01..2026-06-30, REAL Alpaca option prices (run with an empty --chains-dir so the pre-registered 2% MODELED-SPREAD is used, never logged 2026 chains).

## Exit families side by side: current plan vs best level target vs best trail

Best of each family by expectancy among runs with at least 60 trades (else the best with any trades).

| family | run | config | trades | win% | avg win | avg loss | exp $ | PF | PF 2x | max DD | CI95 exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plain stop + time | factory_dev_v1-008 | failed_break prem tpnone tb 15:25 | 676 | 8.90 | 384.90 | -25.47 | 10.95 | 1.47 | 1.03 | -2122.93 | -2.8..28.57 |


## Fixed premium stop / target runs (Option Alpha's exit; the cross-check)

Each row: one symbol, one side, a fixed stop/target of the debit, all out 15:25. `desk` = SPRINT_PLAN's fill rules (inside the bar, same-bar stop wins); `oa1m` = OA-LIKE mechanics (checked once a minute on the close, filled at the next minute's print). `2m+` = profitable two-month blocks. `OA ref` = Option Alpha's own Stage-1 result for the same rule on SPY, Nov 2025-Jun 2026 (fills MODELED by OA, from docs/research/sprint_runs.csv); T1/T2 used OA's 1-year window. Different period, different fill model: a cross-check, not a replication.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| factory_dev_v1-010 | SPY+QQQ+IWM | time_1000 | C | 95/9900 | desk | d03-12t07 | - | 1410 | 8.90 | -3.67 | 0.65 | 0.57 | -5716.45 | 1/12 |  |
| factory_dev_v1-016 | SPY+QQQ+IWM | time_1000 | P | 95/9900 | desk | d06-15t10 | - | 1417 | 10.40 | -3.56 | 0.82 | 0.75 | -8501.69 | 4/12 |  |
| factory_dev_v1-011 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | - | 1423 | 7.70 | -2.26 | 0.76 | 0.67 | -5648.85 | 1/12 |  |
| factory_dev_v1-017 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | - | 1408 | 10.00 | -2.17 | 0.87 | 0.80 | -6273.39 | 5/12 |  |
| factory_dev_v1-012 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | - | 1418 | 8.70 | 0.08 | 1.01 | 0.89 | -4271.24 | 4/12 |  |
| factory_dev_v1-018 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | - | 1413 | 9.60 | -3.27 | 0.79 | 0.73 | -7134.10 | 4/12 |  |
| factory_dev_v1-013 | SPY+QQQ+IWM | time_1200 | C | 95/9900 | desk | d03-12t07 | - | 1387 | 8.70 | 0.25 | 1.03 | 0.90 | -3476.53 | 2/12 |  |
| factory_dev_v1-019 | SPY+QQQ+IWM | time_1200 | P | 95/9900 | desk | d06-15t10 | - | 1383 | 10.30 | -3.89 | 0.72 | 0.66 | -6806.93 | 4/12 |  |
| factory_dev_v1-014 | SPY+QQQ+IWM | time_1300 | C | 95/9900 | desk | d03-12t07 | - | 1367 | 9.70 | 0.67 | 1.10 | 0.94 | -3113.19 | 4/12 |  |
| factory_dev_v1-020 | SPY+QQQ+IWM | time_1300 | P | 95/9900 | desk | d06-15t10 | - | 1358 | 10.20 | -4.98 | 0.58 | 0.52 | -7164.55 | 2/12 |  |
| factory_dev_v1-015 | SPY+QQQ+IWM | time_1400 | C | 95/9900 | desk | d03-12t07 | - | 1349 | 10.50 | -3.17 | 0.44 | 0.36 | -4273.47 | 2/12 |  |
| factory_dev_v1-021 | SPY+QQQ+IWM | time_1400 | P | 95/9900 | desk | d06-15t10 | - | 1331 | 10.10 | -4.21 | 0.56 | 0.49 | -6511.02 | 2/12 |  |


## Robustness on the top 0 runs

## All other runs (sorted by expectancy; fixed stop/target runs are in the cross-check table)

`sig` = signals seen, `skip%` = share not traded (no contract, level stop beyond the ceiling, R:R minimum, busy, no print); the top skip reasons per run are in the run log's notes.

| run | config | sig | skip% | n | win% | avg win | avg loss | exp | PF | PF2x | maxDD | kept | pRR | aRR | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| factory_dev_v1-008 | failed_break prem tpnone tb 15:25 | 930 | 27.31 | 676 | 8.90 | 384.90 | -25.47 | 10.95 | 1.47 | 1.03 | -2122.93 | 0.27 | - | 0.04 | 0.00 |
| factory_dev_v1-005 | vwap_macd prem tpnone tb 15:25 | 733 | 18.96 | 594 | 6.90 | 251.78 | -21.08 | -2.24 | 0.89 | 0.61 | -4246.64 | 0.06 | - | -0.03 | 0.00 |
| factory_dev_v1-004 | orb60 prem tpnone tb 15:25 | 1197 | 13.53 | 1035 | 6.40 | 303.93 | -23.47 | -2.60 | 0.88 | 0.62 | -8526.74 | 0.06 | - | -0.16 | 0.00 |
| factory_dev_v1-003 | orb30 prem tpnone tb 15:25 | 1613 | 9.98 | 1452 | 7.20 | 275.04 | -26.36 | -4.56 | 0.81 | 0.58 | -7816.20 | 0.06 | - | -0.11 | 0.00 |
| factory_dev_v1-002 | orb15 prem tpnone tb 15:25 | 1895 | 8.13 | 1741 | 7.20 | 285.79 | -27.75 | -5.06 | 0.80 | 0.57 | -9058.89 | 0.03 | - | -0.14 | 0.00 |
| factory_dev_v1-007 | flush prem tpnone tb 15:25 | 1063 | 17.59 | 876 | 5.80 | 217.71 | -20.88 | -6.99 | 0.65 | 0.43 | -6513.95 | -0.02 | - | -0.46 | 0.00 |
| factory_dev_v1-001 | noise nois tpnone tb 15:25 d55-75t65 | 4396 | 53.05 | 2064 | 15.40 | 164.45 | -38.53 | -7.26 | 0.78 | 0.53 | -16823.47 | 0.04 | - | -0.18 | 0.00 |
| factory_dev_v1-009 | failed_high prem tpnone tb 15:25 | 1232 | 29.22 | 872 | 4.10 | 343.00 | -24.82 | -9.63 | 0.59 | 0.42 | -10125.18 | -0.06 | - | -0.39 | 0.00 |
| factory_dev_v1-006 | pd_retest prem tpnone tb 15:25 | 126 | 15.87 | 106 | 4.70 | 142.94 | -21.67 | -13.91 | 0.33 | 0.22 | -1664.91 | -0.18 | - | -0.57 | 0.00 |


Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_factory_dev_v1_2026-10-31.csv.gz`.

Labels: BACKTEST (in-sample on DEV). Spread: MODELED-SPREAD. Delta: BS-EST. Not financial advice: evidence for Nick to decide.
