# Sprint report: otm_v1 (DEV), MODELED-SPREAD 5.0% (sensitivity)

Generated 2026-10-31 13:06 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint1` in 3.9 min. Spec sha256 `ece0232e5457df44fbb15ada8d92e6aa3c2919e2cf61406d1fe1600ad3a31f7e`.

**Every number below is a BACKTEST in-sample (DEV)** on Alpaca 1-minute bars, 2024-08-01 to 2026-06-30. Option fills are real traded prices +/- a half-spread: **MODELED-SPREAD 5.0% of premium for every symbol (a SENSITIVITY run, not the pre-registered 2% default), floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Deltas are BS-EST (Black-Scholes from the option's price). Nothing here is a live or paper fill.

Data: IWM: 479 sessions, QQQ: 479 sessions, SPY: 479 sessions. Runs in this spec: 54. Trials counted for the deflated Sharpe: 3241 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Known limits: July 2024 is locked (L2), so early-August 2024 sessions have partial history; news and VIX are unknown in the backtest (rules that need them never fire); a contract needs BS-EST |delta| inside the band, so some signals have no contract (counted as skips).

**Cost caveat:** MODELED-SPREAD 5.0% of premium for every symbol (a SENSITIVITY run, not the pre-registered 2% default), floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: Far out-of-the-money 0DTE options bought at a fixed time and held (pre-registered 2026-10-31, before any run). Source: Option Alpha's Top Backtests (1.5M saved backtests; Moderate filter, last 30 days), whose top ranks are SPX/XSP 0DTE long puts at ~0.06-0.10 delta bought ~10:30 on calm up days ('0DTE Put Hedge': IV rank < 40, VIX not rising, day up, Wed-Fri, skip CPI/monthly expiration) and long calls at ~0.10 delta bought 11:00 on high-VIX days with negative dealer gamma ('Long Call Bounce': VIX >= 17, GEX < 0), both held to expiration with no exit. Those lists are the best of a huge number of user backtests, so their numbers are heavily selected. Here: SPY/QQQ/IWM pooled, 10:30 and 11:00 entries, calls and puts as separate runs, |delta| 0.03-0.12 (t 0.07) and 0.06-0.15 (t 0.10; bands wide enough for $1 strikes), held (a -95% stop, no target) until 15:50 (closest to expiration the desk allows) or 15:25, with no filter, the put-hedge PROXY filters (VIXY percentile <= 40%, VIXY not up > 1%, at or above the prior close, Wed-Fri, skip third Friday) and the call-bounce PROXY filters (VIXY percentile >= 60%, below the prior close, skip third Friday; GEX is not available, a down day stands in for it). Plus fixed take-profits of +300/+500/+1000% on the base 10:30 puts and 11:00 calls. Desk fills; the half-spread floor ($0.005) binds on these cheap options, so PF at 2x slippage is the key cost check. 54 runs.


## Fixed premium stop / target runs (Option Alpha's exit; the cross-check)

Each row: one symbol, one side, a fixed stop/target of the debit, all out 15:25. `desk` = SPRINT_PLAN's fill rules (inside the bar, same-bar stop wins); `oa1m` = OA-LIKE mechanics (checked once a minute on the close, filled at the next minute's print). `2m+` = profitable two-month blocks. `OA ref` = Option Alpha's own Stage-1 result for the same rule on SPY, Nov 2025-Jun 2026 (fills MODELED by OA, from docs/research/sprint_runs.csv); T1/T2 used OA's 1-year window. Different period, different fill model: a cross-check, not a replication.

Regime filters: `vixy_pctl_le40` / `vixy_pctl_ge60` = IV-rank **proxy: VIXY percentile** (share of the 252 split-adjusted daily VIXY closes ending at the prior close that are at or below it; the window skips the locked months, and VIXY's decay biases it low next to a true IV rank); `vixy_not_rising` / `vixy_rising_1pct` = VIXY's last finished 1-minute close at the decision vs its prior close x 1.01 (**proxy: VIXY**); `gap_side_075` = open vs prior close in (0%, +0.75%] for calls, [-0.75%, 0%) for puts. A run with several filters needs all of them. In-sample leads from Option Alpha's optimizer, tested on data OA never saw.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| otm_v1-013@s5 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | - | 1361 | 6.80 | -2.33 | 0.77 | 0.65 | -5667.37 | 2/12 |  |
| otm_v1-016@s5 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | - | 1423 | 7.60 | -2.61 | 0.73 | 0.61 | -5851.27 | 1/12 |  |
| otm_v1-019@s5 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d06-15t10 | - | 1367 | 9.60 | -3.43 | 0.76 | 0.65 | -6497.53 | 2/12 |  |
| otm_v1-022@s5 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d06-15t10 | - | 1404 | 11.40 | -2.94 | 0.78 | 0.67 | -6335.41 | 1/12 |  |
| otm_v1-015@s5 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 44 | 9.10 | -2.66 | 0.87 | 0.76 | -604.61 | 0/2 |  |
| otm_v1-018@s5 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 46 | 4.30 | -0.92 | 0.95 | 0.82 | -556.22 | 0/2 |  |
| otm_v1-021@s5 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 46 | 10.90 | -5.69 | 0.78 | 0.68 | -758.40 | 0/2 |  |
| otm_v1-024@s5 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 46 | 8.70 | -4.69 | 0.80 | 0.69 | -687.04 | 0/2 |  |
| otm_v1-014@s5 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 353 | 7.10 | -7.22 | 0.21 | 0.17 | -2547.77 | 2/11 |  |
| otm_v1-017@s5 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 374 | 8.60 | -6.60 | 0.24 | 0.20 | -2468.62 | 2/11 |  |
| otm_v1-020@s5 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 357 | 10.90 | -8.72 | 0.32 | 0.27 | -3112.86 | 1/11 |  |
| otm_v1-023@s5 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 366 | 12.00 | -7.83 | 0.36 | 0.30 | -2866.13 | 2/11 |  |
| otm_v1-001@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d03-12t07 | - | 1313 | 6.50 | -1.46 | 0.89 | 0.77 | -4366.77 | 4/12 |  |
| otm_v1-004@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d03-12t07 | - | 1410 | 7.20 | -2.90 | 0.78 | 0.67 | -5589.61 | 3/12 |  |
| otm_v1-007@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | - | 1349 | 8.20 | -2.42 | 0.87 | 0.75 | -6030.55 | 5/12 |  |
| otm_v1-010@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | - | 1408 | 9.70 | -3.16 | 0.82 | 0.71 | -6606.03 | 5/12 |  |
| otm_v1-051@s5 | SPY+QQQ+IWM | time_1030 | P | 95/1000 | desk | d03-12t07 | - | 1315 | 8.50 | -4.93 | 0.64 | 0.55 | -7122.70 | 3/12 |  |
| otm_v1-050@s5 | SPY+QQQ+IWM | time_1030 | P | 95/500 | desk | d03-12t07 | - | 1316 | 12.20 | -5.46 | 0.58 | 0.49 | -7415.95 | 1/12 |  |
| otm_v1-049@s5 | SPY+QQQ+IWM | time_1030 | P | 95/300 | desk | d03-12t07 | - | 1317 | 18.30 | -5.34 | 0.56 | 0.47 | -7166.06 | 0/12 |  |
| otm_v1-003@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 33 | 6.10 | -21.19 | 0.05 | 0.03 | -699.29 | 0/2 |  |
| otm_v1-006@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 38 | 5.30 | -11.72 | 0.41 | 0.36 | -509.27 | 0/2 |  |
| otm_v1-009@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 37 | 5.40 | -29.34 | 0.07 | 0.05 | -1085.74 | 0/2 |  |
| otm_v1-012@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 41 | 7.30 | -17.97 | 0.37 | 0.32 | -736.60 | 0/2 |  |
| otm_v1-002@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 351 | 7.70 | 13.33 | 2.04 | 1.77 | -1309.01 | 3/11 |  |
| otm_v1-005@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 377 | 8.50 | 6.85 | 1.58 | 1.36 | -1484.56 | 2/11 |  |
| otm_v1-008@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 361 | 9.40 | 14.58 | 1.86 | 1.61 | -1640.11 | 3/11 |  |
| otm_v1-011@s5 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 375 | 12.50 | 8.90 | 1.56 | 1.34 | -1769.80 | 2/11 |  |
| otm_v1-037@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | - | 1373 | 6.60 | 0.02 | 1.00 | 0.85 | -4623.39 | 4/12 |  |
| otm_v1-040@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | - | 1418 | 8.60 | -0.30 | 0.96 | 0.81 | -4459.52 | 3/12 |  |
| otm_v1-043@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d06-15t10 | - | 1353 | 9.80 | -0.50 | 0.96 | 0.82 | -4759.51 | 3/12 |  |
| otm_v1-046@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d06-15t10 | - | 1383 | 12.50 | -0.39 | 0.97 | 0.82 | -4364.03 | 3/12 |  |
| otm_v1-054@s5 | SPY+QQQ+IWM | time_1100 | C | 95/1000 | desk | d03-12t07 | - | 1373 | 7.40 | -4.62 | 0.49 | 0.41 | -6476.31 | 2/12 |  |
| otm_v1-053@s5 | SPY+QQQ+IWM | time_1100 | C | 95/500 | desk | d03-12t07 | - | 1374 | 10.50 | -4.38 | 0.51 | 0.42 | -6104.28 | 0/12 |  |
| otm_v1-052@s5 | SPY+QQQ+IWM | time_1100 | C | 95/300 | desk | d03-12t07 | - | 1374 | 14.70 | -4.51 | 0.47 | 0.38 | -6316.84 | 0/12 |  |
| otm_v1-039@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 43 | 11.60 | 143.44 | 10.21 | 8.92 | -585.75 | 1/2 |  |
| otm_v1-042@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 44 | 6.80 | 125.55 | 9.74 | 8.40 | -549.05 | 1/2 |  |
| otm_v1-045@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 44 | 13.60 | 147.53 | 8.17 | 7.16 | -740.54 | 1/2 |  |
| otm_v1-048@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 44 | 9.10 | 132.27 | 8.04 | 6.96 | -703.66 | 1/2 |  |
| otm_v1-038@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 356 | 7.60 | -4.27 | 0.48 | 0.40 | -2202.14 | 1/11 |  |
| otm_v1-041@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 370 | 9.20 | -4.88 | 0.38 | 0.31 | -2284.64 | 1/11 |  |
| otm_v1-044@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 351 | 10.00 | -5.10 | 0.57 | 0.48 | -2644.63 | 3/11 |  |
| otm_v1-047@s5 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 360 | 13.10 | -5.76 | 0.49 | 0.41 | -2707.31 | 1/11 |  |
| otm_v1-025@s5 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d03-12t07 | - | 1328 | 6.10 | -3.35 | 0.73 | 0.63 | -6175.21 | 4/12 |  |
| otm_v1-028@s5 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d03-12t07 | - | 1412 | 7.60 | -3.63 | 0.69 | 0.59 | -6851.70 | 3/12 |  |
| otm_v1-031@s5 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | - | 1364 | 8.00 | -5.17 | 0.70 | 0.61 | -8444.22 | 4/12 |  |
| otm_v1-034@s5 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | - | 1413 | 9.50 | -4.11 | 0.75 | 0.64 | -8138.84 | 4/12 |  |
| otm_v1-027@s5 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 31 | 6.50 | -15.29 | 0.12 | 0.10 | -474.02 | 0/2 |  |
| otm_v1-030@s5 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 34 | 11.80 | -4.44 | 0.72 | 0.62 | -412.92 | 1/2 |  |
| otm_v1-033@s5 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 33 | 6.10 | -24.72 | 0.12 | 0.10 | -815.77 | 0/2 |  |
| otm_v1-036@s5 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 36 | 11.10 | -11.23 | 0.57 | 0.49 | -574.26 | 1/2 |  |
| otm_v1-026@s5 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 351 | 6.60 | 5.71 | 1.48 | 1.27 | -1660.74 | 2/11 |  |
| otm_v1-029@s5 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 374 | 9.10 | 1.07 | 1.10 | 0.94 | -1511.89 | 2/11 |  |
| otm_v1-032@s5 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 362 | 9.90 | 5.25 | 1.33 | 1.15 | -2206.35 | 2/11 |  |
| otm_v1-035@s5 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 373 | 12.90 | 2.88 | 1.19 | 1.03 | -1834.25 | 3/11 |  |


## Robustness on the top 6 runs

### otm_v1-008@s5: SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex

Trades 361, win 9%, avg win 334.64, avg loss -18.70, expectancy **14.58** (2x slippage 11.29), PF 1.86 (2x 1.61), max DD -1640.11, % of peak kept 0.30, planned R:R - vs actual 0.81, expectancy CI95 [-11.89, 47.07], deflated Sharpe 0.000 (N=3241).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 3 of 11 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries
- [x] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 91 | 1599.52 | 17.58 | 2.15 |
| 2025 | 173 | 5142.60 | 29.73 | 3.04 |
| Jan-Jun 2026 | 97 | -1479.12 | -15.25 | 0.33 |
| 2m: Aug 2024-Sep 2024 | 40 | -468.72 | -11.72 | 0.35 |
| 2m: Oct 2024-Nov 2024 | 36 | -270.44 | -7.51 | 0.45 |
| 2m: Dec 2024-Jan 2025 | 32 | 2350.39 | 73.45 | 6.38 |
| 2m: Feb 2025-Mar 2025 | 23 | -217.85 | -9.47 | 0.44 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 33 | -76.20 | -2.31 | 0.81 |
| 2m: Aug 2025-Sep 2025 | 39 | -570.98 | -14.64 | 0.03 |
| 2m: Oct 2025-Nov 2025 | 45 | 6038.68 | 134.19 | 10.04 |
| 2m: Dec 2025-Jan 2026 | 35 | -416.43 | -11.90 | 0.30 |
| 2m: Feb 2026-Mar 2026 | 16 | 68.01 | 4.25 | 1.16 |
| 2m: Apr 2026-May 2026 | 42 | -886.77 | -21.11 | 0.00 |
| 2m: Jun 2026-Jul 2026 | 20 | -286.69 | -14.33 | 0.44 |


Sides: calls n=0 exp - PF -; puts n=361 exp 14.58 PF 1.86
Symbols: IWM n=106 exp 7.93 PF 1.77; QQQ n=121 exp 15.51 PF 1.71; SPY n=134 exp 19.00 PF 2.07
Without the best 5 trades: net -1429.25, expectancy -4.01.
One-step nudges: allout=15:25 n=375 PF 1.56 exp 8.90
Matched random entries (5 paths): expectancy 1.01, 3.37, 9.71, 7.59, 5.09; the run beats 100% of paths.
Filter vs random day-skips (twin otm_v1-007@s5, 327 days removed): p = 0.008 (filtered exp 14.58, random-skip mean -2.84).
Exit reasons: {'ALL OUT': 244, 'FIXED STOP': 115, 'FIXED TARGET': 2}.
Median option MFE 0.587, MAE -0.932; median stock MFE $1.850; median distance from the stock's price at the option's peak to the nearest level $0.060; median minutes held 320.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 354, day_up: below the prior close at the decision 280, wed_fri: Monday or Tuesday 232, VIXY percentile above 40% (not calm) 165, monthly expiration (third Friday) skipped 23, VOID 15, no VIXY prior close (VIX proxy) 3, no contract with BS-EST |delta| in 0.06-0.15 3, no option print 1.

### otm_v1-002@s5: SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex

Trades 351, win 8%, avg win 339.14, avg loss -13.82, expectancy **13.33** (2x slippage 10.71), PF 2.04 (2x 1.77), max DD -1309.01, % of peak kept 0.36, planned R:R - vs actual 0.94, expectancy CI95 [-10.24, 42.61], deflated Sharpe 0.000 (N=3241).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 3 of 11 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries
- [x] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 88 | 1608.99 | 18.28 | 2.65 |
| 2025 | 169 | 4186.70 | 24.77 | 3.19 |
| Jan-Jun 2026 | 94 | -1116.46 | -11.88 | 0.30 |
| 2m: Aug 2024-Sep 2024 | 37 | -397.52 | -10.74 | 0.19 |
| 2m: Oct 2024-Nov 2024 | 35 | -275.85 | -7.88 | 0.17 |
| 2m: Dec 2024-Jan 2025 | 32 | 2216.61 | 69.27 | 7.47 |
| 2m: Feb 2025-Mar 2025 | 22 | -190.95 | -8.68 | 0.29 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 32 | -105.45 | -3.30 | 0.67 |
| 2m: Aug 2025-Sep 2025 | 40 | -468.75 | -11.72 | 0.00 |
| 2m: Oct 2025-Nov 2025 | 44 | 5135.40 | 116.71 | 11.02 |
| 2m: Dec 2025-Jan 2026 | 32 | -367.40 | -11.48 | 0.10 |
| 2m: Feb 2026-Mar 2026 | 16 | 110.53 | 6.91 | 1.37 |
| 2m: Apr 2026-May 2026 | 41 | -644.89 | -15.73 | 0.00 |
| 2m: Jun 2026-Jul 2026 | 20 | -332.50 | -16.62 | 0.16 |


Sides: calls n=0 exp - PF -; puts n=351 exp 13.33 PF 2.04
Symbols: IWM n=98 exp 8.43 PF 2.11; QQQ n=120 exp 15.34 PF 1.94; SPY n=133 exp 15.13 PF 2.14
Without the best 5 trades: net -1036.67, expectancy -3.00.
One-step nudges: allout=15:25 n=377 PF 1.58 exp 6.85
Matched random entries (5 paths): expectancy 1.62, 3.07, 9.23, 7.86, 4.51; the run beats 100% of paths.
Filter vs random day-skips (twin otm_v1-001@s5, 325 days removed): p = 0.006 (filtered exp 13.33, random-skip mean -1.83).
Exit reasons: {'ALL OUT': 315, 'FIXED STOP': 33, 'FIXED TARGET': 3}.
Median option MFE 0.508, MAE -0.913; median stock MFE $1.860; median distance from the stock's price at the option's peak to the nearest level $0.061; median minutes held 320.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 354, day_up: below the prior close at the decision 280, wed_fri: Monday or Tuesday 232, VIXY percentile above 40% (not calm) 165, VOID 27, monthly expiration (third Friday) skipped 23, no VIXY prior close (VIX proxy) 3, no option print 1, no contract with BS-EST |delta| in 0.03-0.12 1.

### otm_v1-011@s5: SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex

Trades 375, win 12%, avg win 198.36, avg loss -18.25, expectancy **8.90** (2x slippage 5.98), PF 1.56 (2x 1.34), max DD -1769.80, % of peak kept 0.25, planned R:R - vs actual 0.51, expectancy CI95 [-10.5, 32.81], deflated Sharpe 0.000 (N=3241).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 2 of 11 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries
- [x] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 95 | 474.62 | 5.00 | 1.34 |
| 2025 | 177 | 4460.72 | 25.20 | 2.86 |
| Jan-Jun 2026 | 103 | -1599.10 | -15.53 | 0.27 |
| 2m: Aug 2024-Sep 2024 | 43 | -313.97 | -7.30 | 0.57 |
| 2m: Oct 2024-Nov 2024 | 37 | -280.99 | -7.59 | 0.44 |
| 2m: Dec 2024-Jan 2025 | 32 | 1262.39 | 39.45 | 4.00 |
| 2m: Feb 2025-Mar 2025 | 24 | -227.79 | -9.49 | 0.35 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 33 | -69.25 | -2.10 | 0.81 |
| 2m: Aug 2025-Sep 2025 | 41 | -561.53 | -13.70 | 0.04 |
| 2m: Oct 2025-Nov 2025 | 45 | 5183.19 | 115.18 | 9.28 |
| 2m: Dec 2025-Jan 2026 | 38 | -446.60 | -11.75 | 0.27 |
| 2m: Feb 2026-Mar 2026 | 17 | -84.89 | -4.99 | 0.79 |
| 2m: Apr 2026-May 2026 | 44 | -811.34 | -18.44 | 0.06 |
| 2m: Jun 2026-Jul 2026 | 21 | -312.98 | -14.90 | 0.40 |


Sides: calls n=0 exp - PF -; puts n=375 exp 8.90 PF 1.56
Symbols: IWM n=119 exp 2.84 PF 1.29; QQQ n=122 exp 12.28 PF 1.60; SPY n=134 exp 11.20 PF 1.65
Without the best 5 trades: net -2081.11, expectancy -5.62.
One-step nudges: allout=15:50 n=361 PF 1.86 exp 14.58
Matched random entries (5 paths): expectancy -0.63, 1.90, 6.01, 5.57, 3.39; the run beats 100% of paths.
Filter vs random day-skips (twin otm_v1-010@s5, 324 days removed): p = 0.024 (filtered exp 8.9, random-skip mean -3.06).
Exit reasons: {'ALL OUT': 293, 'FIXED STOP': 82}.
Median option MFE 0.543, MAE -0.913; median stock MFE $1.690; median distance from the stock's price at the option's peak to the nearest level $0.060; median minutes held 295.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 354, day_up: below the prior close at the decision 280, wed_fri: Monday or Tuesday 232, VIXY percentile above 40% (not calm) 165, monthly expiration (third Friday) skipped 23, no VIXY prior close (VIX proxy) 3, no contract with BS-EST |delta| in 0.06-0.15 3, VOID 1, no option print 1.

### otm_v1-005@s5: SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex

Trades 377, win 8%, avg win 219.42, avg loss -12.87, expectancy **6.85** (2x slippage 4.62), PF 1.58 (2x 1.36), max DD -1484.56, % of peak kept 0.28, planned R:R - vs actual 0.50, expectancy CI95 [-9.33, 27.35], deflated Sharpe 0.000 (N=3241).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 2 of 11 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries
- [x] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 96 | 311.43 | 3.24 | 1.30 |
| 2025 | 178 | 3559.60 | 20.00 | 2.93 |
| Jan-Jun 2026 | 103 | -1289.71 | -12.52 | 0.18 |
| 2m: Aug 2024-Sep 2024 | 44 | -319.92 | -7.27 | 0.40 |
| 2m: Oct 2024-Nov 2024 | 36 | -275.25 | -7.65 | 0.20 |
| 2m: Dec 2024-Jan 2025 | 33 | 991.00 | 30.03 | 3.96 |
| 2m: Feb 2025-Mar 2025 | 24 | -196.35 | -8.18 | 0.24 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 34 | -137.55 | -4.05 | 0.54 |
| 2m: Aug 2025-Sep 2025 | 41 | -450.20 | -10.98 | 0.00 |
| 2m: Oct 2025-Nov 2025 | 45 | 4379.40 | 97.32 | 10.06 |
| 2m: Dec 2025-Jan 2026 | 38 | -392.90 | -10.34 | 0.11 |
| 2m: Feb 2026-Mar 2026 | 17 | -89.42 | -5.26 | 0.70 |
| 2m: Apr 2026-May 2026 | 44 | -629.64 | -14.31 | 0.00 |
| 2m: Jun 2026-Jul 2026 | 21 | -297.85 | -14.18 | 0.20 |


Sides: calls n=0 exp - PF -; puts n=377 exp 6.85 PF 1.58
Symbols: IWM n=121 exp 2.23 PF 1.30; QQQ n=122 exp 10.45 PF 1.69; SPY n=134 exp 7.73 PF 1.61
Without the best 5 trades: net -1943.33, expectancy -5.22.
One-step nudges: allout=15:50 n=351 PF 2.04 exp 13.33
Matched random entries (5 paths): expectancy -1.26, 0.93, 4.31, 3.87, 1.20; the run beats 100% of paths.
Filter vs random day-skips (twin otm_v1-004@s5, 323 days removed): p = 0.03 (filtered exp 6.85, random-skip mean -2.92).
Exit reasons: {'ALL OUT': 348, 'FIXED STOP': 27, 'FIXED TARGET': 2}.
Median option MFE 0.472, MAE -0.895; median stock MFE $1.690; median distance from the stock's price at the option's peak to the nearest level $0.060; median minutes held 295.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 354, day_up: below the prior close at the decision 280, wed_fri: Monday or Tuesday 232, VIXY percentile above 40% (not calm) 165, monthly expiration (third Friday) skipped 23, no VIXY prior close (VIX proxy) 3, VOID 1, no option print 1, no contract with BS-EST |delta| in 0.03-0.12 1.

### otm_v1-026@s5: SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex

Trades 351, win 7%, avg win 269.88, avg loss -12.82, expectancy **5.71** (2x slippage 3.57), PF 1.48 (2x 1.27), max DD -1660.74, % of peak kept 0.25, planned R:R - vs actual 0.26, expectancy CI95 [-10.82, 30.19], deflated Sharpe 0.000 (N=3241).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 2 of 11 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries
- [x] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 81 | 2305.77 | 28.47 | 3.55 |
| 2025 | 168 | 1000.41 | 5.95 | 1.55 |
| Jan-Jun 2026 | 102 | -1302.34 | -12.77 | 0.12 |
| 2m: Aug 2024-Sep 2024 | 33 | -245.73 | -7.45 | 0.47 |
| 2m: Oct 2024-Nov 2024 | 33 | -180.45 | -5.47 | 0.41 |
| 2m: Dec 2024-Jan 2025 | 34 | 2864.60 | 84.25 | 9.86 |
| 2m: Feb 2025-Mar 2025 | 19 | -208.75 | -10.99 | 0.06 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 33 | -206.55 | -6.26 | 0.29 |
| 2m: Aug 2025-Sep 2025 | 39 | -421.85 | -10.82 | 0.00 |
| 2m: Oct 2025-Nov 2025 | 43 | 1855.71 | 43.16 | 4.45 |
| 2m: Dec 2025-Jan 2026 | 32 | -339.25 | -10.60 | 0.00 |
| 2m: Feb 2026-Mar 2026 | 19 | -320.25 | -16.86 | 0.00 |
| 2m: Apr 2026-May 2026 | 48 | -639.58 | -13.32 | 0.03 |
| 2m: Jun 2026-Jul 2026 | 18 | -154.06 | -8.56 | 0.53 |


Sides: calls n=0 exp - PF -; puts n=351 exp 5.71 PF 1.48
Symbols: IWM n=99 exp 3.69 PF 1.50; QQQ n=122 exp 9.13 PF 1.60; SPY n=130 exp 4.03 PF 1.32
Without the best 5 trades: net -2927.91, expectancy -8.46.
One-step nudges: allout=15:25 n=374 PF 1.10 exp 1.07
Matched random entries (5 paths): expectancy 0.36, 2.85, 6.96, 7.41, 0.71; the run beats 60% of paths.
Filter vs random day-skips (twin otm_v1-025@s5, 326 days removed): p = 0.05 (filtered exp 5.71, random-skip mean -3.06).
Exit reasons: {'ALL OUT': 329, 'FIXED STOP': 21, 'FIXED TARGET': 1}.
Median option MFE 0.429, MAE -0.905; median stock MFE $1.460; median distance from the stock's price at the option's peak to the nearest level $0.060; median minutes held 290.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 357, day_up: below the prior close at the decision 274, wed_fri: Monday or Tuesday 223, VIXY percentile above 40% (not calm) 183, VOID 24, monthly expiration (third Friday) skipped 19, no VIXY prior close (VIX proxy) 3, no option print 2, no contract with BS-EST |delta| in 0.03-0.12 1.

### otm_v1-032@s5: SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex

Trades 362, win 10%, avg win 214.11, avg loss -17.81, expectancy **5.25** (2x slippage 2.60), PF 1.33 (2x 1.15), max DD -2206.35, % of peak kept 0.19, planned R:R - vs actual 0.12, expectancy CI95 [-13.54, 32.28], deflated Sharpe 0.000 (N=3241).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 2 of 11 (info)
- [x] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries
- [x] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 90 | 2134.39 | 23.72 | 2.61 |
| 2025 | 168 | 1369.84 | 8.15 | 1.56 |
| Jan-Jun 2026 | 104 | -1603.89 | -15.42 | 0.21 |
| 2m: Aug 2024-Sep 2024 | 38 | -104.63 | -2.75 | 0.84 |
| 2m: Oct 2024-Nov 2024 | 37 | -340.35 | -9.20 | 0.28 |
| 2m: Dec 2024-Jan 2025 | 35 | 2810.33 | 80.30 | 7.13 |
| 2m: Feb 2025-Mar 2025 | 20 | -303.28 | -15.16 | 0.10 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 32 | -259.95 | -8.12 | 0.31 |
| 2m: Aug 2025-Sep 2025 | 39 | -540.47 | -13.86 | 0.04 |
| 2m: Oct 2025-Nov 2025 | 43 | 2458.17 | 57.17 | 4.60 |
| 2m: Dec 2025-Jan 2026 | 33 | -485.07 | -14.70 | 0.00 |
| 2m: Feb 2026-Mar 2026 | 19 | -433.33 | -22.81 | 0.02 |
| 2m: Apr 2026-May 2026 | 48 | -793.45 | -16.53 | 0.09 |
| 2m: Jun 2026-Jul 2026 | 18 | -107.63 | -5.98 | 0.76 |


Sides: calls n=0 exp - PF -; puts n=362 exp 5.25 PF 1.33
Symbols: IWM n=107 exp 2.68 PF 1.27; QQQ n=124 exp 7.37 PF 1.36; SPY n=131 exp 5.34 PF 1.32
Without the best 5 trades: net -3540.06, expectancy -9.92.
One-step nudges: allout=15:25 n=373 PF 1.19 exp 2.88
Matched random entries (5 paths): expectancy -0.17, 3.02, 8.00, 6.83, 0.40; the run beats 60% of paths.
Filter vs random day-skips (twin otm_v1-031@s5, 327 days removed): p = 0.048 (filtered exp 5.25, random-skip mean -5.53).
Exit reasons: {'ALL OUT': 274, 'FIXED STOP': 88}.
Median option MFE 0.446, MAE -0.927; median stock MFE $1.442; median distance from the stock's price at the option's peak to the nearest level $0.052; median minutes held 290.0.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 357, day_up: below the prior close at the decision 274, wed_fri: Monday or Tuesday 223, VIXY percentile above 40% (not calm) 183, monthly expiration (third Friday) skipped 19, VOID 12, no contract with BS-EST |delta| in 0.06-0.15 4, no VIXY prior close (VIX proxy) 3.

## Filters vs random day-skips (every filtered run with its unfiltered twin)

| run | config | twin | days skipped | filtered exp | random-skip exp | p |
|---|---|---|---|---|---|---|
| otm_v1-002@s5 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-001@s5 | 325 | 13.33 | -1.83 | 0.01 |
| otm_v1-003@s5 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-001@s5 | 462 | -21.19 | -1.25 | 1.00 |
| otm_v1-005@s5 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-004@s5 | 323 | 6.85 | -2.92 | 0.03 |
| otm_v1-006@s5 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-004@s5 | 462 | -11.72 | -2.39 | 0.64 |
| otm_v1-008@s5 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-007@s5 | 327 | 14.58 | -2.84 | 0.01 |
| otm_v1-009@s5 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-007@s5 | 461 | -29.34 | -1.78 | 1.00 |
| otm_v1-011@s5 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-010@s5 | 324 | 8.90 | -3.06 | 0.02 |
| otm_v1-012@s5 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-010@s5 | 461 | -17.97 | -2.60 | 0.83 |
| otm_v1-014@s5 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-013@s5 | 329 | -7.22 | -1.94 | 0.69 |
| otm_v1-015@s5 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-013@s5 | 460 | -2.66 | -2.55 | 0.15 |
| otm_v1-017@s5 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-016@s5 | 326 | -6.60 | -2.66 | 0.72 |
| otm_v1-018@s5 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-016@s5 | 461 | -0.92 | -3.03 | 0.16 |
| otm_v1-020@s5 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-019@s5 | 325 | -8.72 | -2.87 | 0.76 |
| otm_v1-021@s5 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-019@s5 | 461 | -5.69 | -3.92 | 0.28 |
| otm_v1-023@s5 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-022@s5 | 325 | -7.83 | -2.50 | 0.76 |
| otm_v1-024@s5 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-022@s5 | 461 | -4.69 | -3.39 | 0.32 |
| otm_v1-026@s5 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-025@s5 | 326 | 5.71 | -3.06 | 0.05 |
| otm_v1-027@s5 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-025@s5 | 460 | -15.29 | -4.38 | 0.95 |
| otm_v1-029@s5 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-028@s5 | 322 | 1.07 | -3.56 | 0.11 |
| otm_v1-030@s5 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-028@s5 | 461 | -4.44 | -3.76 | 0.30 |
| otm_v1-032@s5 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-031@s5 | 327 | 5.25 | -5.53 | 0.05 |
| otm_v1-033@s5 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-031@s5 | 461 | -24.72 | -5.58 | 1.00 |
| otm_v1-035@s5 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-034@s5 | 324 | 2.88 | -4.43 | 0.06 |
| otm_v1-036@s5 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-034@s5 | 461 | -11.23 | -4.19 | 0.53 |
| otm_v1-038@s5 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-037@s5 | 329 | -4.27 | 0.35 | 0.59 |
| otm_v1-039@s5 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-037@s5 | 461 | 143.44 | -0.04 | 0.01 |
| otm_v1-041@s5 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-040@s5 | 326 | -4.88 | -0.28 | 0.66 |
| otm_v1-042@s5 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-040@s5 | 461 | 125.55 | -0.49 | 0.00 |
| otm_v1-044@s5 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-043@s5 | 327 | -5.10 | -0.38 | 0.58 |
| otm_v1-045@s5 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-043@s5 | 461 | 147.53 | -0.24 | 0.01 |
| otm_v1-047@s5 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-046@s5 | 327 | -5.76 | -0.24 | 0.71 |
| otm_v1-048@s5 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-046@s5 | 461 | 132.27 | -0.34 | 0.01 |



Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_otm_v1@s5_2026-10-31.csv.gz`.

Labels: BACKTEST (in-sample on DEV). Spread: MODELED-SPREAD 5.0% (sensitivity). Delta: BS-EST. Not financial advice: evidence for Nick to decide.
