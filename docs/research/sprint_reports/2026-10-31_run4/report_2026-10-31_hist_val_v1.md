# Sprint report: hist_val_v1 (DEV), MODELED-SPREAD, MODELED (BS, calibrated IV)

Generated 2026-10-31 15:56 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint2` in 0.9 min. Spec sha256 `19efab941118101ce4ee91c47816c6a25c2dd7cd0b6a26737aca6c62b402e4aa`.

**Every number below is a BACKTEST in-sample (DEV), MODELED (BS, calibrated IV).** Stock prices are Alpaca 1-minute bars, 2024-08-01 to 2026-06-30. **Option prices are not real**: every contract is priced with Black-Scholes from the stock's bars at one implied vol per day = the 20-session realized 1-minute volatility (prior sessions only) x a multiplier fitted on DEV's real option trades (`d03-12t07|C` x0.798, `d06-15t10|P` x1.041, `d40-55t45|C` x0.831; calibration sha256 `4d50070991c1`). Fills: modeled price +/- a half-spread, **MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Nothing here is a live or paper fill.

Data: IWM: 479 sessions, QQQ: 479 sessions, SPY: 479 sessions. Runs in this spec: 6. Trials counted for the deflated Sharpe: 3355 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Idealizations of the model (SPRINT_PLAN Amendment 5): a 0DTE contract is priced every session (before Nov 2022 SPY/QQQ/IWM did not list an expiry every weekday; see the Mon/Wed/Fri vs Tue/Thu lines); one flat IV per day (no smile, no intraday IV change: real puts gain extra value when IV jumps in a selloff, real calls lose some when IV falls in a rally); a price every minute; the 2% half-spread may be optimistic for thinner years (the 5% rerun is the check). Sessions without an IV proxy (fewer than 10 prior sessions) are skipped.

## Validation on DEV: modeled vs real option prices (MODELED (BS, calibrated IV) vs real tapes)

Pre-registered bar: the same sign of expectancy as the real-tape run AND modeled PF within +/-35% of the real PF. The multiplier was fitted on the same DEV trades, so this checks the model's shape, not a prediction. A strategy that fails gets its HIST numbers labeled UNRELIABLE.

| strategy | real run | real n | real exp | real PF | modeled run | modeled n | modeled exp | modeled PF | PF ratio | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| fb | setups_v2-001 | 676 | 10.95 | 1.47 | hist_val_v1-001 | 646 | 12.55 | 1.61 | 1.09 | PASS |
| fb_or | setups_v2-012 | 429 | 18.57 | 1.78 | hist_val_v1-002 | 410 | 19.45 | 1.91 | 1.07 | PASS |
| otm_put_base | otm_v1-010 | 1408 | -2.17 | 0.87 | hist_val_v1-003 | 1404 | -0.43 | 0.98 | 1.12 | PASS |
| otm_put | otm_v1-011 | 375 | 10.20 | 1.66 | hist_val_v1-004 | 373 | 14.15 | 1.88 | 1.14 | PASS |
| otm_bounce_base | otm_v1-040 | 1418 | 0.08 | 1.01 | hist_val_v1-005 | 1402 | 2.93 | 1.33 | 1.32 | PASS |
| otm_bounce | otm_v1-042 | 44 | 130.48 | 10.34 | hist_val_v1-006 | 44 | 80.79 | 6.29 | 0.61 | FAIL |


**Cost caveat:** MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: SPRINT_PLAN Amendment 5, Layer 2 validation (pre-registered 2026-10-31): the six hist_v1 runs on DEV with MODELED (BS, calibrated IV) option tapes instead of the real Alpaca option prices, each compared with its real-tape run. Pre-registered bar: the same sign of expectancy and modeled PF within +/-35% of the real PF. No robustness pass (the comparison is the point). 6 runs.

## Exit families side by side: current plan vs best level target vs best trail

Best of each family by expectancy among runs with at least 60 trades (else the best with any trades).

| family | run | config | trades | win% | avg win | avg loss | exp $ | PF | PF 2x | max DD | CI95 exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plain stop + time | hist_val_v1-002 | failed_break_or prem tpnone tb 15:25 | 410 | 9.50 | 429.16 | -23.62 | 19.45 | 1.91 | 1.36 | -1511.19 | -1.69..48.98 |


## Fixed premium stop / target runs (MODELED (BS, calibrated IV))

Each row: a fixed stop/target of the debit on the modeled option price, desk fill rules (inside the bar, same-bar stop wins), all out at the run's time. `2m+` = profitable two-month blocks.

Regime filters: `vixy_pctl_le40` / `vixy_pctl_ge60` = IV-rank **proxy: VIXY percentile** (share of the 252 split-adjusted daily VIXY closes ending at the prior close that are at or below it; the window skips the locked months, and VIXY's decay biases it low next to a true IV rank); `vixy_not_rising` / `vixy_rising_1pct` = VIXY's last finished 1-minute close at the decision vs its prior close x 1.01 (**proxy: VIXY**); `gap_side_075` = open vs prior close in (0%, +0.75%] for calls, [-0.75%, 0%) for puts. A run with several filters needs all of them. In-sample leads from Option Alpha's optimizer, tested on data OA never saw.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hist_val_v1-003 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | - | 1404 | 8.00 | -0.43 | 0.98 | 0.90 | -6101.33 | 4/12 |  |
| hist_val_v1-004 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 373 | 10.70 | 14.15 | 1.88 | 1.73 | -1647.98 | 3/11 |  |
| hist_val_v1-005 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | - | 1402 | 8.00 | 2.93 | 1.33 | 1.17 | -2735.26 | 6/12 |  |
| hist_val_v1-006 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 44 | 13.60 | 80.79 | 6.29 | 5.78 | -589.60 | 1/2 |  |


## Robustness on the top 0 runs

## Filters vs random day-skips (every filtered run with its unfiltered twin)

| run | config | twin | days skipped | filtered exp | random-skip exp | p |
|---|---|---|---|---|---|---|
| hist_val_v1-004 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | hist_val_v1-003 | 316 | 14.15 | -0.20 | 0.04 |
| hist_val_v1-006 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | hist_val_v1-005 | 451 | 80.79 | 3.47 | 0.01 |


## All other runs (sorted by expectancy; fixed stop/target runs are in the cross-check table)

`sig` = signals seen, `skip%` = share not traded (no contract, level stop beyond the ceiling, R:R minimum, busy, no print); the top skip reasons per run are in the run log's notes.

| run | config | sig | skip% | n | win% | avg win | avg loss | exp | PF | PF2x | maxDD | kept | pRR | aRR | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hist_val_v1-002 | failed_break_or prem tpnone tb 15:25 | 619 | 33.76 | 410 | 9.50 | 429.16 | -23.62 | 19.45 | 1.91 | 1.36 | -1511.19 | 0.33 | - | 0.56 | 0.25 |
| hist_val_v1-001 | failed_break prem tpnone tb 15:25 | 930 | 30.54 | 646 | 8.00 | 411.93 | -22.41 | 12.55 | 1.61 | 1.14 | -2721.91 | 0.27 | - | 0.25 | 0.24 |


Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_hist_val_v1_2026-10-31.csv.gz`.

Labels: BACKTEST in-sample (DEV), MODELED (BS, calibrated IV). Spread: MODELED-SPREAD. No real option price was used. Not financial advice: evidence for Nick to decide.
