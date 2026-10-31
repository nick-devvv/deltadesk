# Sprint report: oa_crosscheck_v2 (NOT_SEEN_BY_OA), MODELED-SPREAD

Generated 2026-10-31 12:22 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint1` in 1.3 min. Spec sha256 `1106a5b2fda02c9f91c39af6bb46ee507328066314a019d9afbda1dfc7ce76b1`.

**Every number below is a BACKTEST on the period Option Alpha never saw (inside DEV)** on Alpaca 1-minute bars, 2024-08-01 to 2025-10-29. Option fills are real traded prices +/- a half-spread: **MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Deltas are BS-EST (Black-Scholes from the option's price). Nothing here is a live or paper fill.

Data: IWM: 313 sessions, QQQ: 313 sessions, SPY: 313 sessions. Runs in this spec: 66. Trials counted for the deflated Sharpe: 2951 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Known limits: July 2024 is locked (L2), so early-August 2024 sessions have partial history; news and VIX are unknown in the backtest (rules that need them never fire); a contract needs BS-EST |delta| inside the band, so some signals have no contract (counted as skips).

**Cost caveat:** MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: Option Alpha's optimizer theme for breakout calls (calm, risk-on days; in-sample on OA's 19 positive runs: IV rank <= ~40 in 8, open change 0 to +0.75% in 4, VIX change <= ~1% in 4), pre-registered 2026-10-31 and tested on the period OA never saw (NOT_SEEN_BY_OA, 2024-08-01..2025-10-29). SPY, QQQ, IWM each on its own, ORB60 calls and puts, first breakout only, signal bars finishing by 12:00, desk fills, base cost (2% half-spread), all out 15:25, fixed stop/target as % of the debit: T1's 50/100 with the 0.50-delta contract (d45-60t50; OA's re-run OA-S1-088 on Nov 2025-Jun 2026: 75 trades, PF 1.55) and the Stage-1 survivor 20/60 with d40-55t45. Filters (every run with a filter has its unfiltered twin here; each filter is also tested against random day-skips): (1) vixy_pctl_le40, IV-rank proxy: VIXY percentile <= 40% (the share of the 252 split-adjusted daily VIXY closes ending at the prior session's close that are at or below that close; the window skips the locked months Feb-Jul 2024, which are never pulled, so early dates reach back into 2023; VIXY's decay biases this proxy low); (2) vixy_not_rising: VIXY's last finished 1-minute close at the decision <= its prior close x 1.01 (proxy: VIXY); (3) gap_side_075: open vs prior close in (0%, +0.75%] for calls, [-0.75%, 0%) for puts; (4) calm = all three. Calls and puts both run (1)-(4). Puts also run the mirrored regime: VIXY percentile >= 60% and VIXY's last 1-minute close >= its prior close x 1.01. 66 runs, all counted as trials.


## Fixed premium stop / target runs (Option Alpha's exit; the cross-check)

Each row: one symbol, one side, a fixed stop/target of the debit, all out 15:25. `desk` = SPRINT_PLAN's fill rules (inside the bar, same-bar stop wins); `oa1m` = OA-LIKE mechanics (checked once a minute on the close, filled at the next minute's print). `2m+` = profitable two-month blocks. `OA ref` = Option Alpha's own Stage-1 result for the same rule on SPY, Nov 2025-Jun 2026 (fills MODELED by OA, from docs/research/sprint_runs.csv); T1/T2 used OA's 1-year window. Different period, different fill model: a cross-check, not a replication.

Regime filters: `vixy_pctl_le40` / `vixy_pctl_ge60` = IV-rank **proxy: VIXY percentile** (share of the 252 split-adjusted daily VIXY closes ending at the prior close that are at or below it; the window skips the locked months, and VIXY's decay biases it low next to a true IV rank); `vixy_not_rising` / `vixy_rising_1pct` = VIXY's last finished 1-minute close at the decision vs its prior close x 1.01 (**proxy: VIXY**); `gap_side_075` = open vs prior close in (0%, +0.75%] for calls, [-0.75%, 0%) for puts. A run with several filters needs all of them. In-sample leads from Option Alpha's optimizer, tested on data OA never saw.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| oa_crosscheck_v2-006 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | - | 132 | 16.70 | -11.27 | 0.47 | 0.33 | -1487.93 | 1/8 | PF 1.33 (OA-S1-023) |
| oa_crosscheck_v2-001 | SPY | orb60 | C | 50/100 | desk | d45-60t50 | - | 131 | 37.40 | -3.02 | 0.93 | 0.78 | -1262.31 | 5/8 | PF 1.55 (OA-S1-088, Nov 2025-Jun 2026) |
| oa_crosscheck_v2-009 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | gap_side_075 | 69 | 13.00 | -13.76 | 0.31 | 0.22 | -949.34 | 1/8 |  |
| oa_crosscheck_v2-004 | SPY | orb60 | C | 50/100 | desk | d45-60t50 | gap_side_075 | 67 | 34.30 | -8.85 | 0.78 | 0.66 | -1087.79 | 4/8 |  |
| oa_crosscheck_v2-008 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | vixy_not_rising | 109 | 18.30 | -8.57 | 0.57 | 0.40 | -933.71 | 1/8 |  |
| oa_crosscheck_v2-003 | SPY | orb60 | C | 50/100 | desk | d45-60t50 | vixy_not_rising | 110 | 35.50 | -6.13 | 0.85 | 0.72 | -1273.33 | 4/8 |  |
| oa_crosscheck_v2-007 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | vixy_pctl_le40 | 99 | 14.10 | -13.48 | 0.34 | 0.24 | -1334.56 | 0/7 |  |
| oa_crosscheck_v2-002 | SPY | orb60 | C | 50/100 | desk | d45-60t50 | vixy_pctl_le40 | 98 | 35.70 | -8.53 | 0.79 | 0.67 | -1162.84 | 5/7 |  |
| oa_crosscheck_v2-010 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | vixy_pctl_le40+vixy_not_rising+gap_side_075 | 58 | 13.80 | -12.85 | 0.31 | 0.22 | -745.17 | 0/7 |  |
| oa_crosscheck_v2-005 | SPY | orb60 | C | 50/100 | desk | d45-60t50 | vixy_pctl_le40+vixy_not_rising+gap_side_075 | 55 | 34.50 | -6.85 | 0.82 | 0.70 | -750.60 | 4/7 |  |
| oa_crosscheck_v2-016 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | - | 124 | 21.80 | -8.56 | 0.66 | 0.46 | -1230.53 | 1/8 |  |
| oa_crosscheck_v2-011 | SPY | orb60 | P | 50/100 | desk | d45-60t50 | - | 122 | 36.90 | 0.56 | 1.01 | 0.86 | -1401.05 | 4/8 |  |
| oa_crosscheck_v2-019 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | gap_side_075 | 37 | 13.50 | -17.28 | 0.36 | 0.25 | -725.06 | 1/7 |  |
| oa_crosscheck_v2-014 | SPY | orb60 | P | 50/100 | desk | d45-60t50 | gap_side_075 | 32 | 37.50 | -17.36 | 0.73 | 0.62 | -971.57 | 3/7 |  |
| oa_crosscheck_v2-018 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | vixy_not_rising | 77 | 24.70 | -5.36 | 0.77 | 0.54 | -597.77 | 4/8 |  |
| oa_crosscheck_v2-013 | SPY | orb60 | P | 50/100 | desk | d45-60t50 | vixy_not_rising | 75 | 41.30 | 9.73 | 1.21 | 1.03 | -855.53 | 5/8 |  |
| oa_crosscheck_v2-062 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | vixy_pctl_ge60+vixy_rising_1pct | 4 | 25.00 | -12.26 | 0.80 | 0.56 | -246.47 | 0/1 |  |
| oa_crosscheck_v2-061 | SPY | orb60 | P | 50/100 | desk | d45-60t50 | vixy_pctl_ge60+vixy_rising_1pct | 4 | 50.00 | 41.21 | 1.33 | 1.14 | -499.39 | 1/1 |  |
| oa_crosscheck_v2-017 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | vixy_pctl_le40 | 96 | 21.90 | -7.83 | 0.63 | 0.44 | -826.80 | 0/7 |  |
| oa_crosscheck_v2-012 | SPY | orb60 | P | 50/100 | desk | d45-60t50 | vixy_pctl_le40 | 94 | 38.30 | 0.62 | 1.01 | 0.86 | -1097.70 | 4/7 |  |
| oa_crosscheck_v2-020 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | vixy_pctl_le40+vixy_not_rising+gap_side_075 | 12 | 25.00 | -0.67 | 0.96 | 0.67 | -113.87 | 2/4 |  |
| oa_crosscheck_v2-015 | SPY | orb60 | P | 50/100 | desk | d45-60t50 | vixy_pctl_le40+vixy_not_rising+gap_side_075 | 9 | 66.70 | 56.30 | 3.80 | 3.25 | -66.85 | 4/4 |  |
| oa_crosscheck_v2-026 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | - | 135 | 15.60 | -13.78 | 0.42 | 0.30 | -1859.69 | 1/8 |  |
| oa_crosscheck_v2-021 | QQQ | orb60 | C | 50/100 | desk | d45-60t50 | - | 134 | 32.10 | -10.63 | 0.78 | 0.66 | -2156.30 | 2/8 |  |
| oa_crosscheck_v2-029 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | gap_side_075 | 56 | 19.60 | -9.33 | 0.55 | 0.38 | -571.56 | 2/8 |  |
| oa_crosscheck_v2-024 | QQQ | orb60 | C | 50/100 | desk | d45-60t50 | gap_side_075 | 55 | 32.70 | -13.17 | 0.71 | 0.60 | -1030.68 | 3/8 |  |
| oa_crosscheck_v2-028 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | vixy_not_rising | 116 | 13.80 | -14.59 | 0.38 | 0.26 | -1692.34 | 1/8 |  |
| oa_crosscheck_v2-023 | QQQ | orb60 | C | 50/100 | desk | d45-60t50 | vixy_not_rising | 115 | 29.60 | -14.99 | 0.69 | 0.58 | -2144.92 | 1/8 |  |
| oa_crosscheck_v2-027 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | vixy_pctl_le40 | 103 | 15.50 | -12.91 | 0.42 | 0.30 | -1329.28 | 1/7 |  |
| oa_crosscheck_v2-022 | QQQ | orb60 | C | 50/100 | desk | d45-60t50 | vixy_pctl_le40 | 102 | 29.40 | -16.61 | 0.66 | 0.56 | -2112.20 | 2/7 |  |
| oa_crosscheck_v2-030 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | vixy_pctl_le40+vixy_not_rising+gap_side_075 | 46 | 19.60 | -8.82 | 0.55 | 0.39 | -454.45 | 2/7 |  |
| oa_crosscheck_v2-025 | QQQ | orb60 | C | 50/100 | desk | d45-60t50 | vixy_pctl_le40+vixy_not_rising+gap_side_075 | 45 | 31.10 | -11.86 | 0.74 | 0.63 | -840.24 | 2/7 |  |
| oa_crosscheck_v2-036 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | - | 111 | 23.40 | -3.87 | 0.85 | 0.59 | -904.07 | 3/8 |  |
| oa_crosscheck_v2-031 | QQQ | orb60 | P | 50/100 | desk | d45-60t50 | - | 110 | 36.40 | 4.97 | 1.09 | 0.93 | -1087.27 | 4/8 |  |
| oa_crosscheck_v2-039 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | gap_side_075 | 31 | 22.60 | -6.63 | 0.74 | 0.52 | -555.94 | 2/7 |  |
| oa_crosscheck_v2-034 | QQQ | orb60 | P | 50/100 | desk | d45-60t50 | gap_side_075 | 31 | 38.70 | 8.37 | 1.15 | 0.98 | -471.31 | 4/7 |  |
| oa_crosscheck_v2-038 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | vixy_not_rising | 65 | 23.10 | -6.64 | 0.73 | 0.51 | -670.75 | 4/8 |  |
| oa_crosscheck_v2-033 | QQQ | orb60 | P | 50/100 | desk | d45-60t50 | vixy_not_rising | 64 | 37.50 | -0.05 | 1.00 | 0.85 | -949.49 | 4/8 |  |
| oa_crosscheck_v2-064 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | vixy_pctl_ge60+vixy_rising_1pct | 3 | 66.70 | 113.77 | 8.71 | 6.07 | -44.26 | 1/1 |  |
| oa_crosscheck_v2-063 | QQQ | orb60 | P | 50/100 | desk | d45-60t50 | vixy_pctl_ge60+vixy_rising_1pct | 3 | 100.00 | 316.34 | inf | inf | 0.00 | 1/1 |  |
| oa_crosscheck_v2-037 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | vixy_pctl_le40 | 84 | 19.00 | -10.28 | 0.57 | 0.40 | -1118.78 | 1/7 |  |
| oa_crosscheck_v2-032 | QQQ | orb60 | P | 50/100 | desk | d45-60t50 | vixy_pctl_le40 | 83 | 37.30 | 0.98 | 1.02 | 0.87 | -618.20 | 3/7 |  |
| oa_crosscheck_v2-040 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | vixy_pctl_le40+vixy_not_rising+gap_side_075 | 13 | 30.80 | 6.79 | 1.36 | 0.95 | -154.99 | 2/5 |  |
| oa_crosscheck_v2-035 | QQQ | orb60 | P | 50/100 | desk | d45-60t50 | vixy_pctl_le40+vixy_not_rising+gap_side_075 | 13 | 46.20 | 22.91 | 1.53 | 1.31 | -195.94 | 4/5 |  |
| oa_crosscheck_v2-046 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | - | 67 | 19.40 | -5.27 | 0.60 | 0.42 | -461.67 | 2/8 |  |
| oa_crosscheck_v2-041 | IWM | orb60 | C | 50/100 | desk | d45-60t50 | - | 85 | 30.60 | -6.73 | 0.77 | 0.65 | -818.52 | 2/8 |  |
| oa_crosscheck_v2-049 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | gap_side_075 | 21 | 19.00 | -5.54 | 0.56 | 0.39 | -183.35 | 2/7 |  |
| oa_crosscheck_v2-044 | IWM | orb60 | C | 50/100 | desk | d45-60t50 | gap_side_075 | 24 | 37.50 | -7.28 | 0.75 | 0.64 | -191.87 | 3/7 |  |
| oa_crosscheck_v2-048 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | vixy_not_rising | 57 | 22.80 | -2.36 | 0.80 | 0.56 | -264.61 | 4/8 |  |
| oa_crosscheck_v2-043 | IWM | orb60 | C | 50/100 | desk | d45-60t50 | vixy_not_rising | 69 | 27.50 | -11.97 | 0.59 | 0.50 | -826.18 | 2/8 |  |
| oa_crosscheck_v2-047 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | vixy_pctl_le40 | 47 | 17.00 | -5.63 | 0.56 | 0.40 | -373.28 | 2/7 |  |
| oa_crosscheck_v2-042 | IWM | orb60 | C | 50/100 | desk | d45-60t50 | vixy_pctl_le40 | 62 | 24.20 | -13.89 | 0.56 | 0.48 | -1007.91 | 1/7 |  |
| oa_crosscheck_v2-050 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | vixy_pctl_le40+vixy_not_rising+gap_side_075 | 16 | 12.50 | -6.93 | 0.45 | 0.32 | -177.89 | 2/6 |  |
| oa_crosscheck_v2-045 | IWM | orb60 | C | 50/100 | desk | d45-60t50 | vixy_pctl_le40+vixy_not_rising+gap_side_075 | 19 | 31.60 | -13.67 | 0.57 | 0.49 | -260.00 | 2/5 |  |
| oa_crosscheck_v2-056 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | - | 89 | 20.20 | -6.60 | 0.55 | 0.39 | -619.29 | 3/8 |  |
| oa_crosscheck_v2-051 | IWM | orb60 | P | 50/100 | desk | d45-60t50 | - | 88 | 31.80 | -7.19 | 0.78 | 0.67 | -1093.90 | 3/8 |  |
| oa_crosscheck_v2-059 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | gap_side_075 | 23 | 17.40 | -8.80 | 0.38 | 0.27 | -224.98 | 2/8 |  |
| oa_crosscheck_v2-054 | IWM | orb60 | P | 50/100 | desk | d45-60t50 | gap_side_075 | 20 | 35.00 | -7.46 | 0.75 | 0.64 | -272.05 | 3/8 |  |
| oa_crosscheck_v2-058 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | vixy_not_rising | 52 | 25.00 | -3.27 | 0.75 | 0.53 | -249.41 | 4/8 |  |
| oa_crosscheck_v2-053 | IWM | orb60 | P | 50/100 | desk | d45-60t50 | vixy_not_rising | 51 | 33.30 | -5.07 | 0.83 | 0.71 | -480.43 | 4/8 |  |
| oa_crosscheck_v2-066 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | vixy_pctl_ge60+vixy_rising_1pct | 4 | 50.00 | 14.58 | 1.81 | 1.26 | -72.22 | 1/1 |  |
| oa_crosscheck_v2-065 | IWM | orb60 | P | 50/100 | desk | d45-60t50 | vixy_pctl_ge60+vixy_rising_1pct | 4 | 50.00 | 10.78 | 1.21 | 1.04 | -207.14 | 1/1 |  |
| oa_crosscheck_v2-057 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | vixy_pctl_le40 | 64 | 18.80 | -8.10 | 0.42 | 0.30 | -536.59 | 3/7 |  |
| oa_crosscheck_v2-052 | IWM | orb60 | P | 50/100 | desk | d45-60t50 | vixy_pctl_le40 | 64 | 32.80 | -7.19 | 0.75 | 0.64 | -826.57 | 4/7 |  |
| oa_crosscheck_v2-060 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | vixy_pctl_le40+vixy_not_rising+gap_side_075 | 9 | 33.30 | -3.58 | 0.73 | 0.52 | -61.71 | 2/6 |  |
| oa_crosscheck_v2-055 | IWM | orb60 | P | 50/100 | desk | d45-60t50 | vixy_pctl_le40+vixy_not_rising+gap_side_075 | 10 | 40.00 | -12.42 | 0.61 | 0.52 | -175.82 | 3/6 |  |


## Robustness on the top 5 runs

### oa_crosscheck_v2-013: SPY orb60 P fixed 50/100 desk d45-60t50 vixy_not_rising

Trades 75, win 41%, avg win 134.07, avg loss -77.87, expectancy **9.73** (2x slippage 1.68), PF 1.21 (2x 1.03), max DD -855.53, % of peak kept 0.14, planned R:R - vs actual 0.15, expectancy CI95 [-14.5, 34.89], deflated Sharpe 0.000 (N=2951).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [x] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 5 of 8 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries
- [ ] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 23 | 700.20 | 30.44 | 1.88 |
| 2025 (Jan 01-Oct 29) | 52 | 29.34 | 0.56 | 1.01 |
| 2m: Aug 2024-Sep 2024 | 12 | 347.21 | 28.93 | 1.70 |
| 2m: Oct 2024-Nov 2024 | 7 | 235.55 | 33.65 | 2.43 |
| 2m: Dec 2024-Jan 2025 | 8 | 77.87 | 9.73 | 1.24 |
| 2m: Feb 2025-Mar 2025 | 6 | -393.17 | -65.53 | 0.32 |
| 2m: Apr 2025-May 2025 | 11 | 285.03 | 25.91 | 1.40 |
| 2m: Jun 2025-Jul 2025 | 15 | -119.61 | -7.97 | 0.81 |
| 2m: Aug 2025-Sep 2025 | 11 | -45.48 | -4.13 | 0.90 |
| 2m: Oct 2025-Nov 2025 | 5 | 342.14 | 68.43 | 8.90 |


Sides: calls n=0 exp - PF -; puts n=75 exp 9.73 PF 1.21
Symbols: SPY n=75 exp 9.73 PF 1.21
Without the best 5 trades: net -508.52, expectancy -7.26.
One-step nudges: entry=orb30 n=113 PF 1.19 exp 8.62; allout=15:50 n=75 PF 1.14 exp 6.40; fixed_stop=0.4 n=75 PF 1.27 exp 10.90; fixed_stop=0.6 n=75 PF 1.16 exp 8.14; fixed_target=0.9 n=75 PF 1.20 exp 9.06; fixed_target=1.25 n=75 PF 1.07 exp 3.54
Matched random entries (5 paths): expectancy 37.12, 12.56, 20.84, 22.00, 10.64; the run beats 0% of paths.
Filter vs random day-skips (twin oa_crosscheck_v2-011, 47 days removed): p = 0.156 (filtered exp 9.73, random-skip mean 0.16).
Exit reasons: {'FIXED STOP': 42, 'FIXED TARGET': 29, 'ALL OUT': 4}.
Median option MFE 0.634, MAE -0.504; median stock MFE $1.380; median distance from the stock's price at the option's peak to the nearest level $0.103; median minutes held 67.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 48, no contract with BS-EST |delta| in 0.45-0.60 4, no VIXY prior close (VIX proxy) 1.

### oa_crosscheck_v2-031: QQQ orb60 P fixed 50/100 desk d45-60t50

Trades 110, win 36%, avg win 169.41, avg loss -89.00, expectancy **4.97** (2x slippage -4.41), PF 1.09 (2x 0.93), max DD -1087.27, % of peak kept 0.09, planned R:R - vs actual 0.02, expectancy CI95 [-18.66, 30.05], deflated Sharpe 0.000 (N=2951).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [x] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 4 of 8 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 39 | 493.93 | 12.66 | 1.25 |
| 2025 (Jan 01-Oct 29) | 71 | 52.43 | 0.74 | 1.01 |
| 2m: Aug 2024-Sep 2024 | 22 | 205.90 | 9.36 | 1.16 |
| 2m: Oct 2024-Nov 2024 | 12 | -76.49 | -6.37 | 0.87 |
| 2m: Dec 2024-Jan 2025 | 11 | 65.84 | 5.99 | 1.11 |
| 2m: Feb 2025-Mar 2025 | 13 | 89.18 | 6.86 | 1.09 |
| 2m: Apr 2025-May 2025 | 16 | 568.74 | 35.55 | 1.50 |
| 2m: Jun 2025-Jul 2025 | 12 | -23.11 | -1.93 | 0.95 |
| 2m: Aug 2025-Sep 2025 | 15 | -281.81 | -18.79 | 0.63 |
| 2m: Oct 2025-Nov 2025 | 9 | -1.89 | -0.21 | 0.99 |


Sides: calls n=0 exp - PF -; puts n=110 exp 4.97 PF 1.09
Symbols: QQQ n=110 exp 4.97 PF 1.09
Without the best 5 trades: net -1122.91, expectancy -10.69.
One-step nudges: entry=orb30 n=160 PF 0.82 exp -11.74; allout=15:50 n=110 PF 1.08 exp 4.37; fixed_stop=0.4 n=110 PF 1.10 exp 4.95; fixed_stop=0.6 n=110 PF 1.02 exp 1.24; fixed_target=0.9 n=110 PF 1.07 exp 3.88; fixed_target=1.25 n=110 PF 0.90 exp -6.04
Matched random entries (5 paths): expectancy 22.65, 5.09, 41.40, 12.03, 6.19; the run beats 0% of paths.
Exit reasons: {'FIXED STOP': 69, 'FIXED TARGET': 39, 'ALL OUT': 2}.
Median option MFE 0.622, MAE -0.505; median stock MFE $1.707; median distance from the stock's price at the option's peak to the nearest level $0.140; median minutes held 57.5.
Skipped signals: no contract with BS-EST |delta| in 0.45-0.60 2.

### oa_crosscheck_v2-032: QQQ orb60 P fixed 50/100 desk d45-60t50 vixy_pctl_le40

Trades 83, win 37%, avg win 137.72, avg loss -80.54, expectancy **0.98** (2x slippage -7.21), PF 1.02 (2x 0.87), max DD -618.20, % of peak kept 0.06, planned R:R - vs actual 0.04, expectancy CI95 [-21.5, 25.64], deflated Sharpe 0.000 (N=2951).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 3 of 7 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries
- [ ] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 38 | 257.28 | 6.77 | 1.13 |
| 2025 (Jan 01-Oct 29) | 45 | -175.82 | -3.91 | 0.92 |
| 2m: Aug 2024-Sep 2024 | 21 | -30.75 | -1.46 | 0.98 |
| 2m: Oct 2024-Nov 2024 | 12 | -76.49 | -6.37 | 0.87 |
| 2m: Dec 2024-Jan 2025 | 11 | 65.84 | 5.99 | 1.11 |
| 2m: Feb 2025-Mar 2025 | 6 | 189.60 | 31.60 | 1.63 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 9 | 216.96 | 24.11 | 1.79 |
| 2m: Aug 2025-Sep 2025 | 15 | -281.81 | -18.79 | 0.63 |
| 2m: Oct 2025-Nov 2025 | 9 | -1.89 | -0.21 | 0.99 |


Sides: calls n=0 exp - PF -; puts n=83 exp 0.98 PF 1.02
Symbols: QQQ n=83 exp 0.98 PF 1.02
Without the best 5 trades: net -980.36, expectancy -12.57.
One-step nudges: entry=orb30 n=127 PF 0.72 exp -16.86; allout=15:50 n=83 PF 1.00 exp 0.19; fixed_stop=0.4 n=83 PF 0.92 exp -3.69; fixed_stop=0.6 n=83 PF 1.01 exp 0.69; fixed_target=0.9 n=83 PF 0.97 exp -1.48; fixed_target=1.25 n=83 PF 0.91 exp -4.82
Matched random entries (5 paths): expectancy 17.80, 1.23, 36.17, -7.91, 8.21; the run beats 20% of paths.
Filter vs random day-skips (twin oa_crosscheck_v2-031, 27 days removed): p = 0.706 (filtered exp 0.98, random-skip mean 5.02).
Exit reasons: {'FIXED STOP': 51, 'FIXED TARGET': 30, 'ALL OUT': 2}.
Median option MFE 0.590, MAE -0.504; median stock MFE $1.620; median distance from the stock's price at the option's peak to the nearest level $0.120; median minutes held 58.
Skipped signals: VIXY percentile above 40% (not calm) 26, no contract with BS-EST |delta| in 0.45-0.60 2, VIXY percentile unknown (needs 252 daily closes up to the prior session) 1.

### oa_crosscheck_v2-012: SPY orb60 P fixed 50/100 desk d45-60t50 vixy_pctl_le40

Trades 94, win 38%, avg win 118.49, avg loss -72.54, expectancy **0.62** (2x slippage -6.61), PF 1.01 (2x 0.86), max DD -1097.70, % of peak kept 0.09, planned R:R - vs actual 0.08, expectancy CI95 [-18.2, 21.25], deflated Sharpe 0.000 (N=2951).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 4 of 7 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries
- [ ] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 40 | 670.52 | 16.76 | 1.40 |
| 2025 (Jan 01-Oct 29) | 54 | -612.08 | -11.33 | 0.76 |
| 2m: Aug 2024-Sep 2024 | 22 | 358.04 | 16.27 | 1.35 |
| 2m: Oct 2024-Nov 2024 | 12 | 223.40 | 18.62 | 1.52 |
| 2m: Dec 2024-Jan 2025 | 13 | -208.25 | -16.02 | 0.69 |
| 2m: Feb 2025-Mar 2025 | 7 | -346.37 | -49.48 | 0.33 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 13 | 28.65 | 2.20 | 1.06 |
| 2m: Aug 2025-Sep 2025 | 18 | -357.31 | -19.85 | 0.59 |
| 2m: Oct 2025-Nov 2025 | 9 | 360.28 | 40.03 | 2.73 |


Sides: calls n=0 exp - PF -; puts n=94 exp 0.62 PF 1.01
Symbols: SPY n=94 exp 0.62 PF 1.01
Without the best 5 trades: net -888.80, expectancy -9.99.
One-step nudges: entry=orb30 n=134 PF 1.04 exp 1.81; allout=15:50 n=94 PF 1.00 exp 0.01; fixed_stop=0.4 n=94 PF 0.99 exp -0.56; fixed_stop=0.6 n=94 PF 1.10 exp 4.85; fixed_target=0.9 n=94 PF 1.04 exp 1.54; fixed_target=1.25 n=94 PF 0.95 exp -2.34
Matched random entries (5 paths): expectancy 20.97, 11.35, 9.67, 2.74, 0.57; the run beats 20% of paths.
Filter vs random day-skips (twin oa_crosscheck_v2-011, 28 days removed): p = 0.502 (filtered exp 0.62, random-skip mean 0.56).
Exit reasons: {'FIXED STOP': 56, 'FIXED TARGET': 35, 'ALL OUT': 3}.
Median option MFE 0.497, MAE -0.504; median stock MFE $1.245; median distance from the stock's price at the option's peak to the nearest level $0.100; median minutes held 62.5.
Skipped signals: VIXY percentile above 40% (not calm) 27, no contract with BS-EST |delta| in 0.45-0.60 6, VIXY percentile unknown (needs 252 daily closes up to the prior session) 1.

### oa_crosscheck_v2-011: SPY orb60 P fixed 50/100 desk d45-60t50

Trades 122, win 37%, avg win 146.55, avg loss -84.76, expectancy **0.56** (2x slippage -8.07), PF 1.01 (2x 0.86), max DD -1401.05, % of peak kept 0.09, planned R:R - vs actual 0.03, expectancy CI95 [-20.66, 23.19], deflated Sharpe 0.000 (N=2951).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 4 of 8 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 41 | 875.83 | 21.36 | 1.52 |
| 2025 (Jan 01-Oct 29) | 81 | -807.62 | -9.97 | 0.83 |
| 2m: Aug 2024-Sep 2024 | 23 | 563.35 | 24.49 | 1.55 |
| 2m: Oct 2024-Nov 2024 | 12 | 223.40 | 18.62 | 1.52 |
| 2m: Dec 2024-Jan 2025 | 13 | -208.25 | -16.02 | 0.69 |
| 2m: Feb 2025-Mar 2025 | 13 | -478.35 | -36.80 | 0.56 |
| 2m: Apr 2025-May 2025 | 18 | 149.98 | 8.33 | 1.10 |
| 2m: Jun 2025-Jul 2025 | 16 | -184.89 | -11.56 | 0.74 |
| 2m: Aug 2025-Sep 2025 | 18 | -357.31 | -19.85 | 0.59 |
| 2m: Oct 2025-Nov 2025 | 9 | 360.28 | 40.03 | 2.73 |


Sides: calls n=0 exp - PF -; puts n=122 exp 0.56 PF 1.01
Symbols: SPY n=122 exp 0.56 PF 1.01
Without the best 5 trades: net -1506.70, expectancy -12.88.
One-step nudges: entry=orb30 n=170 PF 1.04 exp 2.35; allout=15:50 n=122 PF 0.97 exp -1.49; fixed_stop=0.4 n=122 PF 1.02 exp 0.91; fixed_stop=0.6 n=122 PF 1.11 exp 6.04; fixed_target=0.9 n=122 PF 1.09 exp 4.72; fixed_target=1.25 n=122 PF 0.98 exp -1.22
Matched random entries (5 paths): expectancy 31.15, 13.14, 14.96, 20.28, 7.38; the run beats 0% of paths.
Exit reasons: {'FIXED STOP': 75, 'FIXED TARGET': 43, 'ALL OUT': 4}.
Median option MFE 0.510, MAE -0.505; median stock MFE $1.310; median distance from the stock's price at the option's peak to the nearest level $0.100; median minutes held 60.0.
Skipped signals: no contract with BS-EST |delta| in 0.45-0.60 6.

## Filters vs random day-skips (every filtered run with its unfiltered twin)

| run | config | twin | days skipped | filtered exp | random-skip exp | p |
|---|---|---|---|---|---|---|
| oa_crosscheck_v2-002 | SPY orb60 C fixed 50/100 desk d45-60t50 vixy_pctl_le40 | oa_crosscheck_v2-001 | 33 | -8.53 | -2.94 | 0.86 |
| oa_crosscheck_v2-003 | SPY orb60 C fixed 50/100 desk d45-60t50 vixy_not_rising | oa_crosscheck_v2-001 | 21 | -6.13 | -2.93 | 0.82 |
| oa_crosscheck_v2-004 | SPY orb60 C fixed 50/100 desk d45-60t50 gap_side_075 | oa_crosscheck_v2-001 | 64 | -8.85 | -3.14 | 0.79 |
| oa_crosscheck_v2-005 | SPY orb60 C fixed 50/100 desk d45-60t50 vixy_pctl_le40+vixy_not_rising+gap_side_075 | oa_crosscheck_v2-001 | 76 | -6.85 | -3.23 | 0.64 |
| oa_crosscheck_v2-007 | SPY orb60 C fixed 20/60 desk d40-55t45 vixy_pctl_le40 | oa_crosscheck_v2-006 | 33 | -13.48 | -11.37 | 0.88 |
| oa_crosscheck_v2-008 | SPY orb60 C fixed 20/60 desk d40-55t45 vixy_not_rising | oa_crosscheck_v2-006 | 23 | -8.57 | -11.36 | 0.01 |
| oa_crosscheck_v2-009 | SPY orb60 C fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v2-006 | 63 | -13.76 | -11.26 | 0.80 |
| oa_crosscheck_v2-010 | SPY orb60 C fixed 20/60 desk d40-55t45 vixy_pctl_le40+vixy_not_rising+gap_side_075 | oa_crosscheck_v2-006 | 74 | -12.85 | -11.55 | 0.66 |
| oa_crosscheck_v2-012 | SPY orb60 P fixed 50/100 desk d45-60t50 vixy_pctl_le40 | oa_crosscheck_v2-011 | 28 | 0.62 | 0.56 | 0.50 |
| oa_crosscheck_v2-013 | SPY orb60 P fixed 50/100 desk d45-60t50 vixy_not_rising | oa_crosscheck_v2-011 | 47 | 9.73 | 0.16 | 0.16 |
| oa_crosscheck_v2-014 | SPY orb60 P fixed 50/100 desk d45-60t50 gap_side_075 | oa_crosscheck_v2-011 | 90 | -17.36 | 1.62 | 0.85 |
| oa_crosscheck_v2-015 | SPY orb60 P fixed 50/100 desk d45-60t50 vixy_pctl_le40+vixy_not_rising+gap_side_075 | oa_crosscheck_v2-011 | 113 | 56.30 | 0.95 | 0.09 |
| oa_crosscheck_v2-017 | SPY orb60 P fixed 20/60 desk d40-55t45 vixy_pctl_le40 | oa_crosscheck_v2-016 | 28 | -7.83 | -8.71 | 0.39 |
| oa_crosscheck_v2-018 | SPY orb60 P fixed 20/60 desk d40-55t45 vixy_not_rising | oa_crosscheck_v2-016 | 47 | -5.36 | -8.65 | 0.19 |
| oa_crosscheck_v2-019 | SPY orb60 P fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v2-016 | 87 | -17.28 | -8.37 | 0.91 |
| oa_crosscheck_v2-020 | SPY orb60 P fixed 20/60 desk d40-55t45 vixy_pctl_le40+vixy_not_rising+gap_side_075 | oa_crosscheck_v2-016 | 112 | -0.67 | -6.35 | 0.35 |
| oa_crosscheck_v2-022 | QQQ orb60 C fixed 50/100 desk d45-60t50 vixy_pctl_le40 | oa_crosscheck_v2-021 | 32 | -16.61 | -10.15 | 0.91 |
| oa_crosscheck_v2-023 | QQQ orb60 C fixed 50/100 desk d45-60t50 vixy_not_rising | oa_crosscheck_v2-021 | 19 | -14.99 | -10.61 | 0.92 |
| oa_crosscheck_v2-024 | QQQ orb60 C fixed 50/100 desk d45-60t50 gap_side_075 | oa_crosscheck_v2-021 | 79 | -13.17 | -10.16 | 0.65 |
| oa_crosscheck_v2-025 | QQQ orb60 C fixed 50/100 desk d45-60t50 vixy_pctl_le40+vixy_not_rising+gap_side_075 | oa_crosscheck_v2-021 | 89 | -11.86 | -10.96 | 0.54 |
| oa_crosscheck_v2-027 | QQQ orb60 C fixed 20/60 desk d40-55t45 vixy_pctl_le40 | oa_crosscheck_v2-026 | 32 | -12.91 | -13.69 | 0.32 |
| oa_crosscheck_v2-028 | QQQ orb60 C fixed 20/60 desk d40-55t45 vixy_not_rising | oa_crosscheck_v2-026 | 19 | -14.59 | -13.81 | 0.75 |
| oa_crosscheck_v2-029 | QQQ orb60 C fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v2-026 | 79 | -9.33 | -13.75 | 0.10 |
| oa_crosscheck_v2-030 | QQQ orb60 C fixed 20/60 desk d40-55t45 vixy_pctl_le40+vixy_not_rising+gap_side_075 | oa_crosscheck_v2-026 | 89 | -8.82 | -13.99 | 0.12 |
| oa_crosscheck_v2-032 | QQQ orb60 P fixed 50/100 desk d45-60t50 vixy_pctl_le40 | oa_crosscheck_v2-031 | 27 | 0.98 | 5.02 | 0.71 |
| oa_crosscheck_v2-033 | QQQ orb60 P fixed 50/100 desk d45-60t50 vixy_not_rising | oa_crosscheck_v2-031 | 46 | -0.05 | 5.96 | 0.70 |
| oa_crosscheck_v2-034 | QQQ orb60 P fixed 50/100 desk d45-60t50 gap_side_075 | oa_crosscheck_v2-031 | 79 | 8.37 | 5.06 | 0.46 |
| oa_crosscheck_v2-035 | QQQ orb60 P fixed 50/100 desk d45-60t50 vixy_pctl_le40+vixy_not_rising+gap_side_075 | oa_crosscheck_v2-031 | 97 | 22.91 | 3.46 | 0.28 |
| oa_crosscheck_v2-037 | QQQ orb60 P fixed 20/60 desk d40-55t45 vixy_pctl_le40 | oa_crosscheck_v2-036 | 27 | -10.28 | -3.79 | 0.98 |
| oa_crosscheck_v2-038 | QQQ orb60 P fixed 20/60 desk d40-55t45 vixy_not_rising | oa_crosscheck_v2-036 | 46 | -6.64 | -3.50 | 0.76 |
| oa_crosscheck_v2-039 | QQQ orb60 P fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v2-036 | 80 | -6.63 | -4.28 | 0.60 |
| oa_crosscheck_v2-040 | QQQ orb60 P fixed 20/60 desk d40-55t45 vixy_pctl_le40+vixy_not_rising+gap_side_075 | oa_crosscheck_v2-036 | 98 | 6.79 | -3.31 | 0.24 |
| oa_crosscheck_v2-042 | IWM orb60 C fixed 50/100 desk d45-60t50 vixy_pctl_le40 | oa_crosscheck_v2-041 | 23 | -13.89 | -6.85 | 0.96 |
| oa_crosscheck_v2-043 | IWM orb60 C fixed 50/100 desk d45-60t50 vixy_not_rising | oa_crosscheck_v2-041 | 16 | -11.97 | -6.66 | 0.97 |
| oa_crosscheck_v2-044 | IWM orb60 C fixed 50/100 desk d45-60t50 gap_side_075 | oa_crosscheck_v2-041 | 61 | -7.28 | -6.72 | 0.52 |
| oa_crosscheck_v2-045 | IWM orb60 C fixed 50/100 desk d45-60t50 vixy_pctl_le40+vixy_not_rising+gap_side_075 | oa_crosscheck_v2-041 | 66 | -13.67 | -6.32 | 0.73 |
| oa_crosscheck_v2-047 | IWM orb60 C fixed 20/60 desk d40-55t45 vixy_pctl_le40 | oa_crosscheck_v2-046 | 20 | -5.63 | -5.34 | 0.57 |
| oa_crosscheck_v2-048 | IWM orb60 C fixed 20/60 desk d40-55t45 vixy_not_rising | oa_crosscheck_v2-046 | 10 | -2.36 | -5.27 | 0.00 |
| oa_crosscheck_v2-049 | IWM orb60 C fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v2-046 | 46 | -5.54 | -5.55 | 0.48 |
| oa_crosscheck_v2-050 | IWM orb60 C fixed 20/60 desk d40-55t45 vixy_pctl_le40+vixy_not_rising+gap_side_075 | oa_crosscheck_v2-046 | 51 | -6.93 | -5.10 | 0.62 |
| oa_crosscheck_v2-052 | IWM orb60 P fixed 50/100 desk d45-60t50 vixy_pctl_le40 | oa_crosscheck_v2-051 | 24 | -7.19 | -7.34 | 0.50 |
| oa_crosscheck_v2-053 | IWM orb60 P fixed 50/100 desk d45-60t50 vixy_not_rising | oa_crosscheck_v2-051 | 37 | -5.07 | -6.97 | 0.37 |
| oa_crosscheck_v2-054 | IWM orb60 P fixed 50/100 desk d45-60t50 gap_side_075 | oa_crosscheck_v2-051 | 68 | -7.46 | -7.86 | 0.47 |
| oa_crosscheck_v2-055 | IWM orb60 P fixed 50/100 desk d45-60t50 vixy_pctl_le40+vixy_not_rising+gap_side_075 | oa_crosscheck_v2-051 | 78 | -12.42 | -6.87 | 0.60 |
| oa_crosscheck_v2-057 | IWM orb60 P fixed 20/60 desk d40-55t45 vixy_pctl_le40 | oa_crosscheck_v2-056 | 25 | -8.10 | -6.59 | 0.80 |
| oa_crosscheck_v2-058 | IWM orb60 P fixed 20/60 desk d40-55t45 vixy_not_rising | oa_crosscheck_v2-056 | 37 | -3.27 | -6.56 | 0.09 |
| oa_crosscheck_v2-059 | IWM orb60 P fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v2-056 | 66 | -8.80 | -7.02 | 0.62 |
| oa_crosscheck_v2-060 | IWM orb60 P fixed 20/60 desk d40-55t45 vixy_pctl_le40+vixy_not_rising+gap_side_075 | oa_crosscheck_v2-056 | 80 | -3.58 | -6.94 | 0.33 |
| oa_crosscheck_v2-061 | SPY orb60 P fixed 50/100 desk d45-60t50 vixy_pctl_ge60+vixy_rising_1pct | oa_crosscheck_v2-011 | 118 | 41.21 | -1.25 | 0.22 |
| oa_crosscheck_v2-062 | SPY orb60 P fixed 20/60 desk d40-55t45 vixy_pctl_ge60+vixy_rising_1pct | oa_crosscheck_v2-016 | 120 | -12.26 | -9.03 | 0.52 |
| oa_crosscheck_v2-063 | QQQ orb60 P fixed 50/100 desk d45-60t50 vixy_pctl_ge60+vixy_rising_1pct | oa_crosscheck_v2-031 | 107 | 316.34 | 4.02 | 0.00 |
| oa_crosscheck_v2-064 | QQQ orb60 P fixed 20/60 desk d40-55t45 vixy_pctl_ge60+vixy_rising_1pct | oa_crosscheck_v2-036 | 108 | 113.77 | -5.06 | 0.00 |
| oa_crosscheck_v2-065 | IWM orb60 P fixed 50/100 desk d45-60t50 vixy_pctl_ge60+vixy_rising_1pct | oa_crosscheck_v2-051 | 84 | 10.78 | -5.50 | 0.30 |
| oa_crosscheck_v2-066 | IWM orb60 P fixed 20/60 desk d40-55t45 vixy_pctl_ge60+vixy_rising_1pct | oa_crosscheck_v2-056 | 85 | 14.58 | -7.76 | 0.05 |



Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_oa_crosscheck_v2_2026-10-31.csv.gz`.

Labels: BACKTEST (in-sample on DEV). Spread: MODELED-SPREAD. Delta: BS-EST. Not financial advice: evidence for Nick to decide.
