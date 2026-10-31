# Sprint report: otm_v1 (DEV), MODELED-SPREAD

Generated 2026-10-31 13:03 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint1` in 3.8 min. Spec sha256 `ece0232e5457df44fbb15ada8d92e6aa3c2919e2cf61406d1fe1600ad3a31f7e`.

**Every number below is a BACKTEST in-sample (DEV)** on Alpaca 1-minute bars, 2024-08-01 to 2026-06-30. Option fills are real traded prices +/- a half-spread: **MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Deltas are BS-EST (Black-Scholes from the option's price). Nothing here is a live or paper fill.

Data: IWM: 479 sessions, QQQ: 479 sessions, SPY: 479 sessions. Runs in this spec: 54. Trials counted for the deflated Sharpe: 3187 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Known limits: July 2024 is locked (L2), so early-August 2024 sessions have partial history; news and VIX are unknown in the backtest (rules that need them never fire); a contract needs BS-EST |delta| inside the band, so some signals have no contract (counted as skips).

**Cost caveat:** MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: Far out-of-the-money 0DTE options bought at a fixed time and held (pre-registered 2026-10-31, before any run). Source: Option Alpha's Top Backtests (1.5M saved backtests; Moderate filter, last 30 days), whose top ranks are SPX/XSP 0DTE long puts at ~0.06-0.10 delta bought ~10:30 on calm up days ('0DTE Put Hedge': IV rank < 40, VIX not rising, day up, Wed-Fri, skip CPI/monthly expiration) and long calls at ~0.10 delta bought 11:00 on high-VIX days with negative dealer gamma ('Long Call Bounce': VIX >= 17, GEX < 0), both held to expiration with no exit. Those lists are the best of a huge number of user backtests, so their numbers are heavily selected. Here: SPY/QQQ/IWM pooled, 10:30 and 11:00 entries, calls and puts as separate runs, |delta| 0.03-0.12 (t 0.07) and 0.06-0.15 (t 0.10; bands wide enough for $1 strikes), held (a -95% stop, no target) until 15:50 (closest to expiration the desk allows) or 15:25, with no filter, the put-hedge PROXY filters (VIXY percentile <= 40%, VIXY not up > 1%, at or above the prior close, Wed-Fri, skip third Friday) and the call-bounce PROXY filters (VIXY percentile >= 60%, below the prior close, skip third Friday; GEX is not available, a down day stands in for it). Plus fixed take-profits of +300/+500/+1000% on the base 10:30 puts and 11:00 calls. Desk fills; the half-spread floor ($0.005) binds on these cheap options, so PF at 2x slippage is the key cost check. 54 runs.


## Fixed premium stop / target runs (Option Alpha's exit; the cross-check)

Each row: one symbol, one side, a fixed stop/target of the debit, all out 15:25. `desk` = SPRINT_PLAN's fill rules (inside the bar, same-bar stop wins); `oa1m` = OA-LIKE mechanics (checked once a minute on the close, filled at the next minute's print). `2m+` = profitable two-month blocks. `OA ref` = Option Alpha's own Stage-1 result for the same rule on SPY, Nov 2025-Jun 2026 (fills MODELED by OA, from docs/research/sprint_runs.csv); T1/T2 used OA's 1-year window. Different period, different fill model: a cross-check, not a replication.

Regime filters: `vixy_pctl_le40` / `vixy_pctl_ge60` = IV-rank **proxy: VIXY percentile** (share of the 252 split-adjusted daily VIXY closes ending at the prior close that are at or below it; the window skips the locked months, and VIXY's decay biases it low next to a true IV rank); `vixy_not_rising` / `vixy_rising_1pct` = VIXY's last finished 1-minute close at the decision vs its prior close x 1.01 (**proxy: VIXY**); `gap_side_075` = open vs prior close in (0%, +0.75%] for calls, [-0.75%, 0%) for puts. A run with several filters needs all of them. In-sample leads from Option Alpha's optimizer, tested on data OA never saw.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| otm_v1-013 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | - | 1361 | 6.80 | -1.95 | 0.81 | 0.71 | -5458.17 | 2/12 |  |
| otm_v1-016 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | - | 1423 | 7.70 | -2.26 | 0.76 | 0.67 | -5648.85 | 1/12 |  |
| otm_v1-019 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d06-15t10 | - | 1367 | 9.70 | -2.75 | 0.80 | 0.73 | -6258.35 | 2/12 |  |
| otm_v1-022 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d06-15t10 | - | 1404 | 11.50 | -2.26 | 0.83 | 0.75 | -5857.32 | 1/12 |  |
| otm_v1-015 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 44 | 9.10 | -1.57 | 0.92 | 0.85 | -587.85 | 0/2 |  |
| otm_v1-018 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 46 | 4.30 | 0.19 | 1.01 | 0.93 | -537.65 | 1/2 |  |
| otm_v1-021 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 46 | 10.90 | -4.22 | 0.83 | 0.77 | -728.23 | 0/2 |  |
| otm_v1-024 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 46 | 10.90 | -3.18 | 0.86 | 0.79 | -653.92 | 0/2 |  |
| otm_v1-014 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 353 | 7.10 | -7.06 | 0.22 | 0.19 | -2493.34 | 2/11 |  |
| otm_v1-017 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 374 | 8.80 | -6.44 | 0.26 | 0.22 | -2409.54 | 2/11 |  |
| otm_v1-020 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 357 | 10.90 | -8.30 | 0.34 | 0.30 | -3024.89 | 2/11 |  |
| otm_v1-023 | SPY+QQQ+IWM | time_1030 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 366 | 12.30 | -7.41 | 0.39 | 0.34 | -2713.84 | 2/11 |  |
| otm_v1-001 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d03-12t07 | - | 1313 | 6.50 | -0.80 | 0.94 | 0.86 | -4223.04 | 5/12 |  |
| otm_v1-004 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d03-12t07 | - | 1410 | 7.20 | -2.32 | 0.82 | 0.74 | -4888.85 | 5/12 |  |
| otm_v1-007 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | - | 1349 | 8.40 | -1.41 | 0.92 | 0.85 | -5760.44 | 5/12 |  |
| otm_v1-010 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | - | 1408 | 10.00 | -2.17 | 0.87 | 0.80 | -6273.39 | 5/12 |  |
| otm_v1-051 | SPY+QQQ+IWM | time_1030 | P | 95/1000 | desk | d03-12t07 | - | 1315 | 8.70 | -4.00 | 0.70 | 0.63 | -5957.57 | 3/12 |  |
| otm_v1-050 | SPY+QQQ+IWM | time_1030 | P | 95/500 | desk | d03-12t07 | - | 1316 | 12.50 | -4.69 | 0.63 | 0.57 | -6726.91 | 2/12 |  |
| otm_v1-049 | SPY+QQQ+IWM | time_1030 | P | 95/300 | desk | d03-12t07 | - | 1317 | 18.80 | -4.67 | 0.61 | 0.55 | -6304.72 | 0/12 |  |
| otm_v1-003 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 33 | 6.10 | -20.55 | 0.05 | 0.05 | -678.16 | 0/2 |  |
| otm_v1-006 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 38 | 5.30 | -10.93 | 0.44 | 0.41 | -499.61 | 0/2 |  |
| otm_v1-009 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 37 | 5.40 | -28.32 | 0.07 | 0.07 | -1047.88 | 0/2 |  |
| otm_v1-012 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 41 | 7.30 | -16.73 | 0.40 | 0.37 | -685.96 | 0/2 |  |
| otm_v1-002 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 351 | 7.70 | 14.44 | 2.15 | 1.96 | -1244.08 | 3/11 |  |
| otm_v1-005 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 377 | 8.50 | 7.72 | 1.67 | 1.51 | -1419.87 | 2/11 |  |
| otm_v1-008 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 361 | 10.00 | 15.96 | 1.97 | 1.81 | -1559.58 | 3/11 |  |
| otm_v1-011 | SPY+QQQ+IWM | time_1030 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 375 | 13.10 | 10.20 | 1.66 | 1.52 | -1690.48 | 2/11 |  |
| otm_v1-037 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | - | 1373 | 6.60 | 0.42 | 1.05 | 0.92 | -4528.89 | 4/12 |  |
| otm_v1-040 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | - | 1418 | 8.70 | 0.08 | 1.01 | 0.89 | -4271.24 | 4/12 |  |
| otm_v1-043 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d06-15t10 | - | 1353 | 10.00 | 0.20 | 1.02 | 0.92 | -4506.80 | 3/12 |  |
| otm_v1-046 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d06-15t10 | - | 1383 | 12.60 | 0.30 | 1.02 | 0.92 | -4038.10 | 3/12 |  |
| otm_v1-054 | SPY+QQQ+IWM | time_1100 | C | 95/1000 | desk | d03-12t07 | - | 1373 | 7.40 | -4.43 | 0.51 | 0.45 | -6225.36 | 2/12 |  |
| otm_v1-053 | SPY+QQQ+IWM | time_1100 | C | 95/500 | desk | d03-12t07 | - | 1374 | 10.60 | -4.13 | 0.53 | 0.46 | -5758.51 | 0/12 |  |
| otm_v1-052 | SPY+QQQ+IWM | time_1100 | C | 95/300 | desk | d03-12t07 | - | 1374 | 14.80 | -4.26 | 0.49 | 0.43 | -5975.03 | 0/12 |  |
| otm_v1-039 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 43 | 11.60 | 148.95 | 10.75 | 9.89 | -571.46 | 1/2 |  |
| otm_v1-042 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 44 | 6.80 | 130.48 | 10.34 | 9.44 | -533.92 | 1/2 |  |
| otm_v1-045 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 44 | 13.60 | 153.64 | 8.66 | 8.03 | -715.80 | 1/2 |  |
| otm_v1-048 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 44 | 9.10 | 137.88 | 8.58 | 7.93 | -678.24 | 1/2 |  |
| otm_v1-038 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 356 | 7.60 | -4.07 | 0.50 | 0.44 | -2163.66 | 1/11 |  |
| otm_v1-041 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 370 | 9.20 | -4.71 | 0.40 | 0.34 | -2250.38 | 1/11 |  |
| otm_v1-044 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 351 | 10.30 | -4.63 | 0.60 | 0.54 | -2528.25 | 3/11 |  |
| otm_v1-047 | SPY+QQQ+IWM | time_1100 | C | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 360 | 13.30 | -5.32 | 0.52 | 0.46 | -2594.37 | 2/11 |  |
| otm_v1-025 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d03-12t07 | - | 1328 | 6.20 | -2.64 | 0.79 | 0.71 | -5880.35 | 4/12 |  |
| otm_v1-028 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d03-12t07 | - | 1412 | 7.60 | -3.16 | 0.73 | 0.66 | -6309.94 | 4/12 |  |
| otm_v1-031 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | - | 1364 | 8.10 | -4.33 | 0.74 | 0.68 | -7884.99 | 4/12 |  |
| otm_v1-034 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | - | 1413 | 9.60 | -3.27 | 0.79 | 0.73 | -7134.10 | 4/12 |  |
| otm_v1-027 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 31 | 6.50 | -14.78 | 0.13 | 0.12 | -458.25 | 0/2 |  |
| otm_v1-030 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_ge60+day_down+skip_opex | 34 | 11.80 | -3.67 | 0.76 | 0.70 | -405.63 | 1/2 |  |
| otm_v1-033 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 33 | 6.10 | -23.77 | 0.13 | 0.12 | -784.56 | 0/2 |  |
| otm_v1-036 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_ge60+day_down+skip_opex | 36 | 11.10 | -9.97 | 0.61 | 0.56 | -561.09 | 1/2 |  |
| otm_v1-026 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 351 | 6.60 | 7.28 | 1.62 | 1.46 | -1634.21 | 2/11 |  |
| otm_v1-029 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d03-12t07 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 374 | 9.10 | 1.65 | 1.15 | 1.03 | -1481.17 | 2/11 |  |
| otm_v1-032 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 362 | 9.90 | 6.37 | 1.41 | 1.29 | -2148.20 | 2/11 |  |
| otm_v1-035 | SPY+QQQ+IWM | time_1100 | P | 95/9900 | desk | d06-15t10 | vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | 373 | 12.90 | 3.89 | 1.27 | 1.16 | -1764.84 | 4/11 |  |


## Robustness on the top 6 runs

### otm_v1-008: SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex

Trades 361, win 10%, avg win 325.81, avg loss -18.36, expectancy **15.96** (2x slippage 14.19), PF 1.97 (2x 1.81), max DD -1559.58, % of peak kept 0.30, planned R:R - vs actual 0.89, expectancy CI95 [-11.21, 49.34], deflated Sharpe 0.000 (N=3187).

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
| Aug-Dec 2024 | 91 | 1737.23 | 19.09 | 2.27 |
| 2025 | 173 | 5416.70 | 31.31 | 3.20 |
| Jan-Jun 2026 | 97 | -1392.88 | -14.36 | 0.35 |
| 2m: Aug 2024-Sep 2024 | 40 | -436.04 | -10.90 | 0.38 |
| 2m: Oct 2024-Nov 2024 | 36 | -250.76 | -6.97 | 0.48 |
| 2m: Dec 2024-Jan 2025 | 32 | 2452.00 | 76.62 | 6.71 |
| 2m: Feb 2025-Mar 2025 | 23 | -199.98 | -8.69 | 0.47 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 33 | -56.33 | -1.71 | 0.86 |
| 2m: Aug 2025-Sep 2025 | 39 | -556.42 | -14.27 | 0.03 |
| 2m: Oct 2025-Nov 2025 | 45 | 6233.01 | 138.51 | 10.61 |
| 2m: Dec 2025-Jan 2026 | 35 | -397.05 | -11.34 | 0.32 |
| 2m: Feb 2026-Mar 2026 | 16 | 95.81 | 5.99 | 1.23 |
| 2m: Apr 2026-May 2026 | 42 | -866.57 | -20.63 | 0.00 |
| 2m: Jun 2026-Jul 2026 | 20 | -256.62 | -12.83 | 0.48 |


Sides: calls n=0 exp - PF -; puts n=361 exp 15.96 PF 1.97
Symbols: IWM n=106 exp 8.63 PF 1.85; QQQ n=121 exp 17.37 PF 1.82; SPY n=134 exp 20.48 PF 2.18
Without the best 5 trades: net -1101.27, expectancy -3.09.
One-step nudges: allout=15:25 n=375 PF 1.66 exp 10.20
Matched random entries (5 paths): expectancy 1.80, 4.24, 10.80, 8.58, 6.02; the run beats 100% of paths.
Filter vs random day-skips (twin otm_v1-007, 327 days removed): p = 0.008 (filtered exp 15.96, random-skip mean -1.84).
Exit reasons: {'ALL OUT': 244, 'FIXED STOP': 115, 'FIXED TARGET': 2}.
Median option MFE 0.613, MAE -0.931; median stock MFE $1.850; median distance from the stock's price at the option's peak to the nearest level $0.060; median minutes held 320.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 354, day_up: below the prior close at the decision 280, wed_fri: Monday or Tuesday 232, VIXY percentile above 40% (not calm) 165, monthly expiration (third Friday) skipped 23, VOID 15, no VIXY prior close (VIX proxy) 3, no contract with BS-EST |delta| in 0.06-0.15 3, no option print 1.

### otm_v1-002: SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex

Trades 351, win 8%, avg win 350.55, avg loss -13.57, expectancy **14.44** (2x slippage 12.89), PF 2.15 (2x 1.96), max DD -1244.08, % of peak kept 0.36, planned R:R - vs actual 1.02, expectancy CI95 [-9.92, 44.61], deflated Sharpe 0.000 (N=3187).

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
| Aug-Dec 2024 | 88 | 1708.56 | 19.42 | 2.77 |
| 2025 | 169 | 4414.84 | 26.12 | 3.33 |
| Jan-Jun 2026 | 94 | -1056.24 | -11.24 | 0.32 |
| 2m: Aug 2024-Sep 2024 | 37 | -383.15 | -10.36 | 0.21 |
| 2m: Oct 2024-Nov 2024 | 35 | -271.00 | -7.74 | 0.18 |
| 2m: Dec 2024-Jan 2025 | 32 | 2304.71 | 72.02 | 7.81 |
| 2m: Feb 2025-Mar 2025 | 22 | -183.22 | -8.33 | 0.31 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 32 | -95.42 | -2.98 | 0.70 |
| 2m: Aug 2025-Sep 2025 | 40 | -463.97 | -11.60 | 0.00 |
| 2m: Oct 2025-Nov 2025 | 44 | 5329.49 | 121.12 | 11.59 |
| 2m: Dec 2025-Jan 2026 | 32 | -360.14 | -11.25 | 0.11 |
| 2m: Feb 2026-Mar 2026 | 16 | 130.32 | 8.14 | 1.45 |
| 2m: Apr 2026-May 2026 | 41 | -634.20 | -15.47 | 0.00 |
| 2m: Jun 2026-Jul 2026 | 20 | -306.26 | -15.31 | 0.18 |


Sides: calls n=0 exp - PF -; puts n=351 exp 14.44 PF 2.15
Symbols: IWM n=98 exp 8.96 PF 2.18; QQQ n=120 exp 16.84 PF 2.06; SPY n=133 exp 16.30 PF 2.25
Without the best 5 trades: net -833.60, expectancy -2.41.
One-step nudges: allout=15:25 n=377 PF 1.67 exp 7.72
Matched random entries (5 paths): expectancy 2.12, 3.63, 9.99, 8.57, 5.11; the run beats 100% of paths.
Filter vs random day-skips (twin otm_v1-001, 325 days removed): p = 0.006 (filtered exp 14.44, random-skip mean -1.18).
Exit reasons: {'ALL OUT': 316, 'FIXED STOP': 32, 'FIXED TARGET': 3}.
Median option MFE 0.520, MAE -0.913; median stock MFE $1.860; median distance from the stock's price at the option's peak to the nearest level $0.061; median minutes held 320.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 354, day_up: below the prior close at the decision 280, wed_fri: Monday or Tuesday 232, VIXY percentile above 40% (not calm) 165, VOID 27, monthly expiration (third Friday) skipped 23, no VIXY prior close (VIX proxy) 3, no option print 1, no contract with BS-EST |delta| in 0.03-0.12 1.

### otm_v1-011: SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex

Trades 375, win 13%, avg win 197.34, avg loss -17.93, expectancy **10.20** (2x slippage 8.60), PF 1.66 (2x 1.52), max DD -1690.48, % of peak kept 0.25, planned R:R - vs actual 0.58, expectancy CI95 [-9.79, 34.89], deflated Sharpe 0.000 (N=3187).

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
| Aug-Dec 2024 | 95 | 579.08 | 6.10 | 1.42 |
| 2025 | 177 | 4761.32 | 26.90 | 3.03 |
| Jan-Jun 2026 | 103 | -1514.19 | -14.70 | 0.29 |
| 2m: Aug 2024-Sep 2024 | 43 | -274.49 | -6.38 | 0.61 |
| 2m: Oct 2024-Nov 2024 | 37 | -261.22 | -7.06 | 0.47 |
| 2m: Dec 2024-Jan 2025 | 32 | 1329.24 | 41.54 | 4.22 |
| 2m: Feb 2025-Mar 2025 | 24 | -210.29 | -8.76 | 0.39 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 33 | -49.84 | -1.51 | 0.86 |
| 2m: Aug 2025-Sep 2025 | 41 | -545.93 | -13.32 | 0.05 |
| 2m: Oct 2025-Nov 2025 | 45 | 5398.68 | 119.97 | 9.92 |
| 2m: Dec 2025-Jan 2026 | 38 | -427.21 | -11.24 | 0.29 |
| 2m: Feb 2026-Mar 2026 | 17 | -61.79 | -3.63 | 0.84 |
| 2m: Apr 2026-May 2026 | 44 | -787.63 | -17.90 | 0.06 |
| 2m: Jun 2026-Jul 2026 | 21 | -283.31 | -13.49 | 0.44 |


Sides: calls n=0 exp - PF -; puts n=375 exp 10.20 PF 1.66
Symbols: IWM n=119 exp 3.38 PF 1.34; QQQ n=122 exp 14.11 PF 1.71; SPY n=134 exp 12.71 PF 1.76
Without the best 5 trades: net -1768.97, expectancy -4.78.
One-step nudges: allout=15:50 n=361 PF 1.97 exp 15.96
Matched random entries (5 paths): expectancy 0.07, 2.70, 6.95, 6.46, 4.25; the run beats 100% of paths.
Filter vs random day-skips (twin otm_v1-010, 324 days removed): p = 0.024 (filtered exp 10.2, random-skip mean -2.07).
Exit reasons: {'ALL OUT': 293, 'FIXED STOP': 82}.
Median option MFE 0.589, MAE -0.913; median stock MFE $1.690; median distance from the stock's price at the option's peak to the nearest level $0.060; median minutes held 295.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 354, day_up: below the prior close at the decision 280, wed_fri: Monday or Tuesday 232, VIXY percentile above 40% (not calm) 165, monthly expiration (third Friday) skipped 23, no VIXY prior close (VIX proxy) 3, no contract with BS-EST |delta| in 0.06-0.15 3, VOID 1, no option print 1.

### otm_v1-005: SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex

Trades 377, win 8%, avg win 227.07, avg loss -12.62, expectancy **7.72** (2x slippage 6.33), PF 1.67 (2x 1.51), max DD -1419.87, % of peak kept 0.28, planned R:R - vs actual 0.56, expectancy CI95 [-9.0, 28.81], deflated Sharpe 0.000 (N=3187).

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
| Aug-Dec 2024 | 96 | 373.43 | 3.89 | 1.37 |
| 2025 | 178 | 3768.66 | 21.17 | 3.08 |
| Jan-Jun 2026 | 103 | -1230.37 | -11.95 | 0.19 |
| 2m: Aug 2024-Sep 2024 | 44 | -300.77 | -6.84 | 0.43 |
| 2m: Oct 2024-Nov 2024 | 36 | -269.28 | -7.48 | 0.21 |
| 2m: Dec 2024-Jan 2025 | 33 | 1040.44 | 31.53 | 4.15 |
| 2m: Feb 2025-Mar 2025 | 24 | -188.40 | -7.85 | 0.26 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 34 | -128.88 | -3.79 | 0.56 |
| 2m: Aug 2025-Sep 2025 | 41 | -445.27 | -10.86 | 0.00 |
| 2m: Oct 2025-Nov 2025 | 45 | 4549.95 | 101.11 | 10.65 |
| 2m: Dec 2025-Jan 2026 | 38 | -385.00 | -10.13 | 0.12 |
| 2m: Feb 2026-Mar 2026 | 17 | -75.82 | -4.46 | 0.74 |
| 2m: Apr 2026-May 2026 | 44 | -618.13 | -14.05 | 0.00 |
| 2m: Jun 2026-Jul 2026 | 21 | -267.12 | -12.72 | 0.23 |


Sides: calls n=0 exp - PF -; puts n=377 exp 7.72 PF 1.67
Symbols: IWM n=121 exp 2.57 PF 1.35; QQQ n=122 exp 11.81 PF 1.80; SPY n=134 exp 8.66 PF 1.70
Without the best 5 trades: net -1760.14, expectancy -4.73.
One-step nudges: allout=15:50 n=351 PF 2.15 exp 14.44
Matched random entries (5 paths): expectancy -0.87, 1.40, 4.88, 4.42, 1.68; the run beats 100% of paths.
Filter vs random day-skips (twin otm_v1-004, 323 days removed): p = 0.03 (filtered exp 7.72, random-skip mean -2.34).
Exit reasons: {'ALL OUT': 349, 'FIXED STOP': 26, 'FIXED TARGET': 2}.
Median option MFE 0.478, MAE -0.895; median stock MFE $1.690; median distance from the stock's price at the option's peak to the nearest level $0.060; median minutes held 295.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 354, day_up: below the prior close at the decision 280, wed_fri: Monday or Tuesday 232, VIXY percentile above 40% (not calm) 165, monthly expiration (third Friday) skipped 23, no VIXY prior close (VIX proxy) 3, VOID 1, no option print 1, no contract with BS-EST |delta| in 0.03-0.12 1.

### otm_v1-026: SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex

Trades 351, win 7%, avg win 291.51, avg loss -12.65, expectancy **7.28** (2x slippage 5.89), PF 1.62 (2x 1.46), max DD -1634.21, % of peak kept 0.26, planned R:R - vs actual 0.36, expectancy CI95 [-10.57, 33.91], deflated Sharpe 0.000 (N=3187).

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
| Aug-Dec 2024 | 81 | 2706.76 | 33.42 | 4.03 |
| 2025 | 168 | 1117.95 | 6.65 | 1.62 |
| Jan-Jun 2026 | 102 | -1269.65 | -12.45 | 0.13 |
| 2m: Aug 2024-Sep 2024 | 33 | -228.93 | -6.94 | 0.50 |
| 2m: Oct 2024-Nov 2024 | 33 | -175.20 | -5.31 | 0.42 |
| 2m: Dec 2024-Jan 2025 | 34 | 3256.79 | 95.79 | 11.17 |
| 2m: Feb 2025-Mar 2025 | 19 | -203.77 | -10.72 | 0.07 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 33 | -201.02 | -6.09 | 0.30 |
| 2m: Aug 2025-Sep 2025 | 39 | -417.70 | -10.71 | 0.00 |
| 2m: Oct 2025-Nov 2025 | 43 | 1944.04 | 45.21 | 4.68 |
| 2m: Dec 2025-Jan 2026 | 32 | -336.60 | -10.52 | 0.00 |
| 2m: Feb 2026-Mar 2026 | 19 | -314.69 | -16.56 | 0.00 |
| 2m: Apr 2026-May 2026 | 48 | -628.05 | -13.08 | 0.03 |
| 2m: Jun 2026-Jul 2026 | 18 | -139.81 | -7.77 | 0.56 |


Sides: calls n=0 exp - PF -; puts n=351 exp 7.28 PF 1.62
Symbols: IWM n=99 exp 4.08 PF 1.55; QQQ n=122 exp 10.13 PF 1.68; SPY n=130 exp 7.03 PF 1.57
Without the best 5 trades: net -2822.30, expectancy -8.16.
One-step nudges: allout=15:25 n=374 PF 1.15 exp 1.65
Matched random entries (5 paths): expectancy 0.81, 3.40, 7.64, 8.11, 1.18; the run beats 60% of paths.
Filter vs random day-skips (twin otm_v1-025, 326 days removed): p = 0.046 (filtered exp 7.28, random-skip mean -2.33).
Exit reasons: {'ALL OUT': 328, 'FIXED STOP': 21, 'FIXED TARGET': 2}.
Median option MFE 0.440, MAE -0.905; median stock MFE $1.460; median distance from the stock's price at the option's peak to the nearest level $0.060; median minutes held 290.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 357, day_up: below the prior close at the decision 274, wed_fri: Monday or Tuesday 223, VIXY percentile above 40% (not calm) 183, VOID 24, monthly expiration (third Friday) skipped 19, no VIXY prior close (VIX proxy) 3, no option print 2, no contract with BS-EST |delta| in 0.03-0.12 1.

### otm_v1-032: SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex

Trades 362, win 10%, avg win 221.89, avg loss -17.43, expectancy **6.37** (2x slippage 4.84), PF 1.41 (2x 1.29), max DD -2148.20, % of peak kept 0.18, planned R:R - vs actual 0.18, expectancy CI95 [-13.01, 34.23], deflated Sharpe 0.000 (N=3187).

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
| Aug-Dec 2024 | 90 | 2279.65 | 25.33 | 2.76 |
| 2025 | 168 | 1559.53 | 9.28 | 1.65 |
| Jan-Jun 2026 | 104 | -1534.51 | -14.75 | 0.23 |
| 2m: Aug 2024-Sep 2024 | 38 | -65.72 | -1.73 | 0.90 |
| 2m: Oct 2024-Nov 2024 | 37 | -326.57 | -8.83 | 0.30 |
| 2m: Dec 2024-Jan 2025 | 35 | 2926.75 | 83.62 | 7.49 |
| 2m: Feb 2025-Mar 2025 | 20 | -292.56 | -14.63 | 0.11 |
| 2m: Apr 2025-May 2025 | 0 | - | - | - |
| 2m: Jun 2025-Jul 2025 | 32 | -247.62 | -7.74 | 0.33 |
| 2m: Aug 2025-Sep 2025 | 39 | -528.21 | -13.54 | 0.04 |
| 2m: Oct 2025-Nov 2025 | 43 | 2585.15 | 60.12 | 4.90 |
| 2m: Dec 2025-Jan 2026 | 33 | -476.24 | -14.43 | 0.00 |
| 2m: Feb 2026-Mar 2026 | 19 | -421.91 | -22.21 | 0.02 |
| 2m: Apr 2026-May 2026 | 48 | -767.53 | -15.99 | 0.10 |
| 2m: Jun 2026-Jul 2026 | 18 | -80.87 | -4.49 | 0.82 |


Sides: calls n=0 exp - PF -; puts n=362 exp 6.37 PF 1.41
Symbols: IWM n=107 exp 3.21 PF 1.33; QQQ n=124 exp 8.94 PF 1.45; SPY n=131 exp 6.51 PF 1.40
Without the best 5 trades: net -3314.77, expectancy -9.29.
One-step nudges: allout=15:25 n=373 PF 1.27 exp 3.89
Matched random entries (5 paths): expectancy 0.56, 3.87, 9.02, 7.78, 1.19; the run beats 60% of paths.
Filter vs random day-skips (twin otm_v1-031, 327 days removed): p = 0.048 (filtered exp 6.37, random-skip mean -4.7).
Exit reasons: {'ALL OUT': 274, 'FIXED STOP': 88}.
Median option MFE 0.472, MAE -0.926; median stock MFE $1.442; median distance from the stock's price at the option's peak to the nearest level $0.052; median minutes held 290.0.
Skipped signals: VIX proxy (VIXY) up more than 1% on its prior close 357, day_up: below the prior close at the decision 274, wed_fri: Monday or Tuesday 223, VIXY percentile above 40% (not calm) 183, monthly expiration (third Friday) skipped 19, VOID 12, no contract with BS-EST |delta| in 0.06-0.15 4, no VIXY prior close (VIX proxy) 3.

## Filters vs random day-skips (every filtered run with its unfiltered twin)

| run | config | twin | days skipped | filtered exp | random-skip exp | p |
|---|---|---|---|---|---|---|
| otm_v1-002 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-001 | 325 | 14.44 | -1.18 | 0.01 |
| otm_v1-003 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-001 | 462 | -20.55 | -0.58 | 1.00 |
| otm_v1-005 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-004 | 323 | 7.72 | -2.34 | 0.03 |
| otm_v1-006 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-004 | 462 | -10.93 | -1.79 | 0.60 |
| otm_v1-008 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-007 | 327 | 15.96 | -1.84 | 0.01 |
| otm_v1-009 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-007 | 461 | -28.32 | -0.76 | 1.00 |
| otm_v1-011 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-010 | 324 | 10.20 | -2.07 | 0.02 |
| otm_v1-012 | SPY+QQQ+IWM time_1030 P fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-010 | 461 | -16.73 | -1.59 | 0.79 |
| otm_v1-014 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-013 | 329 | -7.06 | -1.55 | 0.70 |
| otm_v1-015 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-013 | 460 | -1.57 | -2.19 | 0.13 |
| otm_v1-017 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-016 | 326 | -6.44 | -2.31 | 0.73 |
| otm_v1-018 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-016 | 461 | 0.19 | -2.70 | 0.14 |
| otm_v1-020 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-019 | 325 | -8.30 | -2.17 | 0.77 |
| otm_v1-021 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-019 | 461 | -4.22 | -3.25 | 0.26 |
| otm_v1-023 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-022 | 325 | -7.41 | -1.81 | 0.77 |
| otm_v1-024 | SPY+QQQ+IWM time_1030 C fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-022 | 461 | -3.18 | -2.72 | 0.28 |
| otm_v1-026 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-025 | 326 | 7.28 | -2.33 | 0.05 |
| otm_v1-027 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-025 | 460 | -14.78 | -3.78 | 0.94 |
| otm_v1-029 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-028 | 322 | 1.65 | -3.09 | 0.11 |
| otm_v1-030 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-028 | 461 | -3.67 | -3.29 | 0.29 |
| otm_v1-032 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-031 | 327 | 6.37 | -4.70 | 0.05 |
| otm_v1-033 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-031 | 461 | -23.77 | -4.76 | 1.00 |
| otm_v1-035 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-034 | 324 | 3.89 | -3.60 | 0.06 |
| otm_v1-036 | SPY+QQQ+IWM time_1100 P fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-034 | 461 | -9.97 | -3.36 | 0.50 |
| otm_v1-038 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-037 | 329 | -4.07 | 0.77 | 0.59 |
| otm_v1-039 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-037 | 461 | 148.95 | 0.35 | 0.01 |
| otm_v1-041 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d03-12t07 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-040 | 326 | -4.71 | 0.10 | 0.67 |
| otm_v1-042 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d03-12t07 vixy_pctl_ge60+day_down+skip_opex | otm_v1-040 | 461 | 130.48 | -0.12 | 0.00 |
| otm_v1-044 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-043 | 327 | -4.63 | 0.33 | 0.58 |
| otm_v1-045 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-043 | 461 | 153.64 | 0.47 | 0.01 |
| otm_v1-047 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d06-15t10 vixy_pctl_le40+vixy_not_rising+day_up+wed_fri+skip_opex | otm_v1-046 | 327 | -5.32 | 0.45 | 0.72 |
| otm_v1-048 | SPY+QQQ+IWM time_1100 C fixed 95/9900 desk d06-15t10 vixy_pctl_ge60+day_down+skip_opex | otm_v1-046 | 461 | 137.88 | 0.34 | 0.01 |



Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_otm_v1_2026-10-31.csv.gz`.

Labels: BACKTEST (in-sample on DEV). Spread: MODELED-SPREAD. Delta: BS-EST. Not financial advice: evidence for Nick to decide.
