# Sprint report: round8_hist_v1 (HIST), MODELED-SPREAD, MODELED (BS, calibrated IV)

Generated 2026-11-01 00:23 on `grok-bot-vm-510907181` by sprint engine `2026-11-01.sprint3` in 1.9 min. Spec sha256 `1647d70cd7870af032406bf554ff0bf1de5ef31df714d60680eb6c26ed3e4e4b`.

**Every number below is a BACKTEST HIST (2016-2023 history, never used to choose these rules), MODELED (BS, calibrated IV).** Stock prices are Alpaca 1-minute bars, 2016-01-04 to 2024-01-31 (history from 2015-11-01 feeds indicators only). **Option prices are not real**: every contract is priced with Black-Scholes from the stock's bars at one implied vol per day = the 20-session realized 1-minute volatility (prior sessions only) x a multiplier fitted on DEV's real option trades (`d03-12t07|C` x0.798, `n1d03-12t07|C` x0.798; calibration sha256 `4d50070991c1`). Fills: modeled price +/- a half-spread, **MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Nothing here is a live or paper fill.

Data: IWM: 2033 sessions, QQQ: 2033 sessions, SPY: 2033 sessions. Runs in this spec: 9. Trials counted for the deflated Sharpe: 3478 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Idealizations of the model (SPRINT_PLAN Amendment 5): a 0DTE contract is priced every session (before Nov 2022 SPY/QQQ/IWM did not list an expiry every weekday; see the Mon/Wed/Fri vs Tue/Thu lines); one flat IV per day (no smile, no intraday IV change: real puts gain extra value when IV jumps in a selloff, real calls lose some when IV falls in a rally); a price every minute; the 2% half-spread may be optimistic for thinner years (the 5% rerun is the check). Sessions without an IV proxy (fewer than 10 prior sessions) are skipped.

**Cost caveat:** MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: SPRINT_PLAN Amendment 10 with Addenda 10.1-10.3 (round 8, pre-registered 2026-11-01 before any round-8 run). Engine runs: B3 newhigh_c and B4 (FIN-H's entry, time_1100 calls with rvol >= 1.06, on d03-12t07 and n1d03-12t07 with exits (i) -95%, (ii) -50%, (iii) -50% + gb50, (iv) -50% + target +100%), SPY+QQQ+IWM pooled, desk fills, 2% half-spread ($0.005 floor), $0.65/contract/side, 1 contract, all out 15:25, one position at a time per run and symbol. 9 runs. No pass-2 robustness (tools/sprint_round8.py does its own checks). The option_pass section (D1-D6 grids, random-side twins, A-opt, A3 twins) is run by tools/sprint_round8.py, not by tools/sprint_run.py. HIST = 2016-01-04..2024-01-31 (history from 2015-11-01 for indicators only); option prices MODELED (BS, calibrated IV) with run 4's data/sprint/calib_modeled.json; next-expiry tapes MODELED at the next NYSE session, NOT VALIDATED. A-opt and A3's twins are decided on DEV; their HIST numbers are information.

## Exit families side by side: current plan vs best level target vs best trail

Best of each family by expectancy among runs with at least 60 trades (else the best with any trades).

| family | run | config | trades | win% | avg win | avg loss | exp $ | PF | PF 2x | max DD | CI95 exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| best trail | round8_hist_v1-008 | SPY+QQQ+IWM time_1100 C fixed 50/9900 tr:gb50 desk n1d03-12t07 rvol_ge106 | 2070 | 36.40 | 0.92 | -3.63 | -1.97 | 0.14 | 0.02 | -4074.09 | -2.2..-1.76 |


## Fixed premium stop / target runs (MODELED (BS, calibrated IV))

Each row: a fixed stop/target of the debit on the modeled option price, desk fill rules (inside the bar, same-bar stop wins), all out at the run's time. `2m+` = profitable two-month blocks.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| round8_hist_v1-001 | SPY+QQQ+IWM | newhigh_c | C | 95/9900 | desk | d03-12t07 | - | 817 | 9.90 | 3.07 | 1.68 | 1.36 | -506.38 | 18/49 |  |
| round8_hist_v1-003 | SPY+QQQ+IWM | time_1100 | C | 50/9900 | desk | d03-12t07 | rvol_ge106 | 1927 | 4.30 | 0.79 | 1.20 | 0.84 | -1380.36 | 16/49 |  |
| round8_hist_v1-004 | SPY+QQQ+IWM | time_1100 | C | 50/9900 | desk | d03-12t07 | rvol_ge106 | 1927 | 23.50 | -1.99 | 0.12 | 0.02 | -3829.41 | 0/49 |  |
| round8_hist_v1-007 | SPY+QQQ+IWM | time_1100 | C | 50/9900 | desk | n1d03-12t07 | rvol_ge106 | 2070 | 24.20 | 0.02 | 1.00 | 0.75 | -1088.93 | 20/49 |  |
| round8_hist_v1-008 | SPY+QQQ+IWM | time_1100 | C | 50/9900 | desk | n1d03-12t07 | rvol_ge106 | 2070 | 36.40 | -1.97 | 0.14 | 0.02 | -4074.09 | 0/49 |  |
| round8_hist_v1-002 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | rvol_ge106 | 1927 | 12.10 | 5.79 | 2.24 | 1.83 | -596.32 | 27/49 |  |
| round8_hist_v1-006 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | n1d03-12t07 | rvol_ge106 | 2070 | 31.00 | 1.08 | 1.21 | 0.99 | -763.71 | 23/49 |  |
| round8_hist_v1-005 | SPY+QQQ+IWM | time_1100 | C | 50/100 | desk | d03-12t07 | rvol_ge106 | 1927 | 24.60 | -1.84 | 0.36 | 0.19 | -3562.44 | 1/49 |  |
| round8_hist_v1-009 | SPY+QQQ+IWM | time_1100 | C | 50/100 | desk | n1d03-12t07 | rvol_ge106 | 2070 | 32.10 | -1.73 | 0.63 | 0.44 | -3625.42 | 7/49 |  |


## Robustness on the top 0 runs


Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_round8_hist_v1_2026-11-01.csv.gz`.

Labels: BACKTEST HIST (2016-2023 history, never used to choose these rules), MODELED (BS, calibrated IV). Spread: MODELED-SPREAD. No real option price was used. Not financial advice: evidence for Nick to decide.
