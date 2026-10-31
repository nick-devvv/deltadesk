# Sprint results 5: why the ideas lose in some years, and which days to skip (2026-10-31)

Pre-registered in SPRINT_PLAN Amendment 6: the rules were found on 2016-2019 only and frozen (commit `e3bf7e7`) before the 2020-2023 holdout was evaluated once. Data: run 4's HIST trade file. Option P/L is MODELED (BS, calibrated IV), 1 contract, 2% half-spread.

## What the 2016-2019 discovery set showed

- **Far-OTM 0DTE options** (10:30 puts, 11:00 calls) lose on quiet days and win on days that are already moving.
  - Range so far vs ATR, high tercile: PF 1.48 / 1.62. Low tercile: 0.28 / 0.34.
  - Relative volume, high tercile: PF 1.43 / 1.98.
- **Failed-break calls** lose in calm regimes (VIXY percentile low/mid: PF 0.17-0.56) and do better after a down prior day.

## Holdout 1: 2020-2023, never seen by the rules (MODELED)

| rule | trades | exp $ | PF | PF 2x | years green | without best 5 | p (random day-skips) | verdict |
|---|---|---|---|---|---|---|---|---|
| F 10:30 puts: range >= 0.52 ATR and rvol >= 1.05 | 722 | 5.17 | 1.44 | 1.30 | 3/4 | +1,121 | <0.001 | **PASS** |
| G 11:00 calls: range >= 0.61 ATR | 1,095 | 7.27 | 2.23 | 1.89 | 4/4 | +4,724 | 0.007 | **PASS** |
| H 11:00 calls: rvol >= 1.06 | 1,099 | 7.98 | 2.35 | 2.00 | 4/4 | +5,743 | 0.003 | **PASS** |
| I 11:00 calls: both | 708 | 11.79 | 3.11 | 2.63 | 4/4 | +5,324 | <0.001 | **PASS** |
| D / E (puts, one condition) | 1,181 / 1,095 | 0.58 / 2.15 | 1.05 / 1.17 | 0.95 / 1.06 | 2/4 | negative | | fail |
| A / B / C (failed-break calls) | 193 / 429 / 91 | 7.41 / 2.38 / 31.29 | 1.37 / 1.14 / 2.74 | 0.97 / 0.81 / 1.93 | 1-2 years with 10+ trades | | | fail |

Unfiltered on the same years: 10:30 puts PF 0.67 (-$13,458); 11:00 calls PF 1.34 (+$6,803); fb_or PF 0.88.

## The learner (walk-forward, retrained monthly, Amendment 3 settings, 24 training months)

| run | out-of-sample from | all trades | logit picks | verdict |
|---|---|---|---|---|
| 10:30 puts (hist_v1-003) | 2018-01 | 4,069 trades, PF 0.74, -$12,789 | 1,460 trades, PF 1.17, PF 2x 1.06, +$3,004; beats 100% of random skips | **PASS** |
| 11:00 calls (hist_v1-005) | 2018-01 | 4,168 trades, PF 1.24, +$5,975 | 1,513 trades, PF 2.15, PF 2x 1.82, +$10,128, max DD -$1,061 | **PASS** |
| fb_or (hist_v1-002) | 2018-02 | 1,124 trades, PF 0.85 | best: logit PF 0.94 | fail |

The learner's strongest weights repeat the rules: range so far, prior-day range, relative volume and the VIX proxy.

## Caveat, and the deciding test

The option model uses one flat IV per day. On days that are already moving, real 0DTE IV rises, so real options cost more than the model says. These rules buy exactly on those days, so MODELED results may flatter them.

**Holdout 2** decides it: the same frozen rules and a learner trained only on HIST, scored on DEV 2024-08 to 2026-06 with **real** option prices (`tools/sprint_regime.py`, Chart run 5). Failed-break calls are dropped: no rule or learner fixed them.
