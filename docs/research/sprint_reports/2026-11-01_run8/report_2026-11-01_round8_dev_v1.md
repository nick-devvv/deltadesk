# Sprint report: round8_dev_v1 (DEV), MODELED-SPREAD

Generated 2026-11-01 00:25 on `grok-bot-vm-510907181` by sprint engine `2026-11-01.sprint3` in 1.3 min. Spec sha256 `76dfcdfbb3afd8e632b0b00195dd0f8397f1285073a00514a08daeee7475eec2`.

**Every number below is a BACKTEST in-sample (DEV)** on Alpaca 1-minute bars, 2024-08-01 to 2026-06-30. Option fills are real traded prices +/- a half-spread: **MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Deltas are BS-EST (Black-Scholes from the option's price). Nothing here is a live or paper fill.

Data: IWM: 479 sessions, QQQ: 479 sessions, SPY: 479 sessions. Runs in this spec: 9. Trials counted for the deflated Sharpe: 3487 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Known limits: July 2024 is locked (L2), so early-August 2024 sessions have partial history; news and VIX are unknown in the backtest (rules that need them never fire); a contract needs BS-EST |delta| inside the band, so some signals have no contract (counted as skips).

**Cost caveat:** MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: SPRINT_PLAN Amendment 10 with Addenda 10.1-10.3 (round 8, pre-registered 2026-11-01 before any round-8 run). Engine runs: B3 newhigh_c and B4 (FIN-H's entry, time_1100 calls with rvol >= 1.06, on d03-12t07 and n1d03-12t07 with exits (i) -95%, (ii) -50%, (iii) -50% + gb50, (iv) -50% + target +100%), SPY+QQQ+IWM pooled, desk fills, 2% half-spread ($0.005 floor), $0.65/contract/side, 1 contract, all out 15:25, one position at a time per run and symbol. 9 runs. No pass-2 robustness (tools/sprint_round8.py does its own checks). The option_pass section (D1-D6 grids, random-side twins, A-opt, A3 twins) is run by tools/sprint_round8.py, not by tools/sprint_run.py. DEV = 2024-08-01..2026-06-30, REAL Alpaca option prices (0DTE and next expiry; run with an empty --chains-dir so the pre-registered 2% MODELED-SPREAD is used, never logged 2026 chains).

## Exit families side by side: current plan vs best level target vs best trail

Best of each family by expectancy among runs with at least 60 trades (else the best with any trades).

| family | run | config | trades | win% | avg win | avg loss | exp $ | PF | PF 2x | max DD | CI95 exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| best trail | round8_dev_v1-004 | SPY+QQQ+IWM time_1100 C fixed 50/9900 tr:gb50 desk d03-12t07 rvol_ge106 | 485 | 29.10 | 1.94 | -4.52 | -2.64 | 0.18 | 0.05 | -1299.42 | -3.15..-2.12 |


## Fixed premium stop / target runs (Option Alpha's exit; the cross-check)

Each row: one symbol, one side, a fixed stop/target of the debit, all out 15:25. `desk` = SPRINT_PLAN's fill rules (inside the bar, same-bar stop wins); `oa1m` = OA-LIKE mechanics (checked once a minute on the close, filled at the next minute's print). `2m+` = profitable two-month blocks. `OA ref` = Option Alpha's own Stage-1 result for the same rule on SPY, Nov 2025-Jun 2026 (fills MODELED by OA, from docs/research/sprint_runs.csv); T1/T2 used OA's 1-year window. Different period, different fill model: a cross-check, not a replication.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| round8_dev_v1-001 | SPY+QQQ+IWM | newhigh_c | C | 95/9900 | desk | d03-12t07 | - | 203 | 13.30 | 11.97 | 2.55 | 2.23 | -490.04 | 5/12 |  |
| round8_dev_v1-003 | SPY+QQQ+IWM | time_1100 | C | 50/9900 | desk | d03-12t07 | rvol_ge106 | 485 | 7.20 | 13.35 | 2.94 | 2.27 | -956.59 | 6/12 |  |
| round8_dev_v1-004 | SPY+QQQ+IWM | time_1100 | C | 50/9900 | desk | d03-12t07 | rvol_ge106 | 485 | 29.10 | -2.64 | 0.18 | 0.05 | -1299.42 | 1/12 |  |
| round8_dev_v1-007 | SPY+QQQ+IWM | time_1100 | C | 50/9900 | desk | n1d03-12t07 | rvol_ge106 | 293 | 27.60 | 18.46 | 3.40 | 2.81 | -298.34 | 7/12 |  |
| round8_dev_v1-008 | SPY+QQQ+IWM | time_1100 | C | 50/9900 | desk | n1d03-12t07 | rvol_ge106 | 293 | 38.90 | -2.67 | 0.21 | 0.04 | -802.11 | 1/12 |  |
| round8_dev_v1-002 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | rvol_ge106 | 485 | 11.80 | 13.22 | 2.35 | 2.10 | -1278.32 | 6/12 |  |
| round8_dev_v1-006 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | n1d03-12t07 | rvol_ge106 | 293 | 29.40 | 17.58 | 3.03 | 2.70 | -359.10 | 7/12 |  |
| round8_dev_v1-005 | SPY+QQQ+IWM | time_1100 | C | 50/100 | desk | d03-12t07 | rvol_ge106 | 485 | 25.60 | -2.78 | 0.49 | 0.34 | -1386.75 | 2/12 |  |
| round8_dev_v1-009 | SPY+QQQ+IWM | time_1100 | C | 50/100 | desk | n1d03-12t07 | rvol_ge106 | 293 | 33.10 | -1.26 | 0.83 | 0.65 | -448.19 | 3/12 |  |


## Robustness on the top 0 runs


Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_round8_dev_v1_2026-11-01.csv.gz`.

Labels: BACKTEST (in-sample on DEV). Spread: MODELED-SPREAD. Delta: BS-EST. Not financial advice: evidence for Nick to decide.
