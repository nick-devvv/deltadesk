# Sprint report: oa_crosscheck_v1 (NOT_SEEN_BY_OA), MODELED-SPREAD

Generated 2026-10-31 06:24 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint1` in 2.7 min. Spec sha256 `e11178369dd70a6d53dd9e86209345e9e2665e564b732844e1ff3be39ba19b37`.

**Every number below is a BACKTEST on the period Option Alpha never saw (inside DEV)** on Alpaca 1-minute bars, 2024-08-01 to 2025-10-29. Option fills are real traded prices +/- a half-spread: **MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Deltas are BS-EST (Black-Scholes from the option's price). Nothing here is a live or paper fill.

Data: IWM: 313 sessions, QQQ: 313 sessions, SPY: 313 sessions. Runs in this spec: 444. Trials counted for the deflated Sharpe: 922 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Known limits: July 2024 is locked (L2), so early-August 2024 sessions have partial history; news and VIX are unknown in the backtest (rules that need them never fire); a contract needs BS-EST |delta| inside the band, so some signals have no contract (counted as skips).

**Cost caveat:** MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: Cross-check of Option Alpha's Stage-1 candidate (SPY ORB60 long calls, fixed premium stop/target at 1:3: 20/60, 15/45, 10/30; PF 1.30-1.33 on Nov 2025-Jun 2026) and of OA's T1 (50/100, 0.50 delta) in the desk engine, on the part of DEV that Option Alpha never saw: 2024-08-01 to 2025-10-29 (period tag NOT_SEEN_BY_OA). OA rules: 0DTE, first breakout only per side (finished 1-minute close beyond the range), signal bars finishing by 12:00, next-bar entry, fixed stop and target as % of the debit on the option's price, nothing else (no breakeven, no if-flat, no time tightening), all out 15:25 (OA: 35 min before close). Calls and puts run separately, per symbol (SPY is the OA candidate; QQQ and IWM are context). Two exit mechanics: 'desk' = SPRINT_PLAN's fill rules (the base) and 'oa1m' = OA-LIKE (checked once a minute on the close, filled at the next minute's print). Contract: d40-55t45 (BS-EST delta 0.40-0.55 nearest 0.45; OA took the closest delta to 0.45 with no band, so band misses are skipped here and counted). 444 runs. Side rule pre-registered in two forms (no margin, and a 1% margin around the 20-day SMA), see the side_rule block. Two optimizer leads (VIX falling with proxy: VIXY, and the 0 to +/-0.75% open-gap side rule) in the optimizer_leads block; VIXY 1-minute stock bars come from tools/sprint_pull.py (stock bars only, no options). Not tuned: every pair and filter comes from the OA Stage-1 list.


## Fixed premium stop / target runs (Option Alpha's exit; the cross-check)

Each row: one symbol, one side, a fixed stop/target of the debit, all out 15:25. `desk` = SPRINT_PLAN's fill rules (inside the bar, same-bar stop wins); `oa1m` = OA-LIKE mechanics (checked once a minute on the close, filled at the next minute's print). `2m+` = profitable two-month blocks. `OA ref` = Option Alpha's own Stage-1 result for the same rule on SPY, Nov 2025-Jun 2026 (fills MODELED by OA, from docs/research/sprint_runs.csv); T1/T2 used OA's 1-year window. Different period, different fill model: a cross-check, not a replication.

`vixy_falling` = OA's "VIX falling" optimizer lead with **proxy: VIXY** (Alpaca has no VIX index): VIXY's last finished 1-minute close at the decision is below its prior close. `gap_side_075` = open vs prior close in (0%, +0.75%] for calls, [-0.75%, 0%) for puts. Both are in-sample leads from OA's optimizer on its run 023, tested here on data OA never saw.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| oa_crosscheck_v1-007 | SPY | orb60 | C | 15/45 | desk | d40-55t45 | - | 132 | 17.40 | -9.94 | 0.41 | 0.26 | -1312.19 | 0/8 | PF 1.33 (OA-S1-024) |
| oa_crosscheck_v1-008 | SPY | orb60 | C | 15/45 | oa1m | d40-55t45 | - | 132 | 19.70 | -10.42 | 0.49 | 0.33 | -1375.90 | 0/8 | PF 1.33 (OA-S1-024) |
| oa_crosscheck_v1-009 | SPY | orb60 | C | 10/30 | desk | d40-55t45 | - | 132 | 17.40 | -7.33 | 0.40 | 0.21 | -999.82 | 0/8 | PF 1.30 (OA-S1-025) |
| oa_crosscheck_v1-010 | SPY | orb60 | C | 10/30 | oa1m | d40-55t45 | - | 132 | 24.20 | -6.86 | 0.54 | 0.33 | -976.34 | 0/8 | PF 1.30 (OA-S1-025) |
| oa_crosscheck_v1-005 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | - | 132 | 16.70 | -11.27 | 0.47 | 0.33 | -1487.93 | 1/8 | PF 1.33 (OA-S1-023) |
| oa_crosscheck_v1-006 | SPY | orb60 | C | 20/60 | oa1m | d40-55t45 | - | 132 | 18.90 | -9.76 | 0.59 | 0.43 | -1288.68 | 1/8 | PF 1.33 (OA-S1-023) |
| oa_crosscheck_v1-003 | SPY | orb60 | C | 20/40 | desk | d40-55t45 | - | 132 | 27.30 | -8.27 | 0.56 | 0.38 | -1122.28 | 0/8 | PF 1.04 (OA-S1-022) |
| oa_crosscheck_v1-004 | SPY | orb60 | C | 20/40 | oa1m | d40-55t45 | - | 132 | 27.30 | -9.67 | 0.56 | 0.39 | -1275.94 | 0/8 | PF 1.04 (OA-S1-022) |
| oa_crosscheck_v1-011 | SPY | orb60 | C | 50/100 | desk | d40-55t45 | - | 132 | 34.80 | -2.45 | 0.93 | 0.79 | -1082.07 | 2/8 | PF 1.44 (T1, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-012 | SPY | orb60 | C | 50/100 | oa1m | d40-55t45 | - | 132 | 36.40 | -1.32 | 0.96 | 0.82 | -1049.12 | 3/8 | PF 1.44 (T1, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-073 | SPY | orb60 | C | 50/100 | desk | d45-60t50 | - | 131 | 37.40 | -3.02 | 0.93 | 0.78 | -1262.31 | 5/8 | PF 1.44 (T1, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-074 | SPY | orb60 | C | 50/100 | oa1m | d45-60t50 | - | 131 | 39.70 | 0.07 | 1.00 | 0.85 | -976.76 | 4/8 | PF 1.44 (T1, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-001 | SPY | orb60 | C | 20/20 | desk | d40-55t45 | - | 132 | 45.50 | -5.50 | 0.60 | 0.34 | -768.72 | 1/8 | PF 0.86 (OA-S1-021) |
| oa_crosscheck_v1-002 | SPY | orb60 | C | 20/20 | oa1m | d40-55t45 | - | 132 | 46.20 | -4.48 | 0.71 | 0.45 | -747.72 | 1/8 | PF 0.86 (OA-S1-021) |
| oa_crosscheck_v1-338 | SPY | orb60 | C | 15/45 | desk | d40-55t45 | gap_side_075 | 69 | 17.40 | -9.15 | 0.40 | 0.25 | -631.49 | 1/8 |  |
| oa_crosscheck_v1-340 | SPY | orb60 | C | 15/45 | oa1m | d40-55t45 | gap_side_075 | 69 | 18.80 | -11.32 | 0.41 | 0.28 | -801.20 | 1/8 |  |
| oa_crosscheck_v1-342 | SPY | orb60 | C | 10/30 | desk | d40-55t45 | gap_side_075 | 69 | 14.50 | -8.23 | 0.28 | 0.15 | -600.09 | 0/8 |  |
| oa_crosscheck_v1-344 | SPY | orb60 | C | 10/30 | oa1m | d40-55t45 | gap_side_075 | 69 | 23.20 | -6.79 | 0.50 | 0.31 | -574.90 | 0/8 |  |
| oa_crosscheck_v1-334 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | gap_side_075 | 69 | 13.00 | -13.76 | 0.31 | 0.22 | -949.34 | 1/8 |  |
| oa_crosscheck_v1-336 | SPY | orb60 | C | 20/60 | oa1m | d40-55t45 | gap_side_075 | 69 | 15.90 | -14.32 | 0.37 | 0.27 | -1045.22 | 1/8 |  |
| oa_crosscheck_v1-330 | SPY | orb60 | C | 20/40 | desk | d40-55t45 | gap_side_075 | 69 | 27.50 | -7.66 | 0.55 | 0.36 | -644.18 | 1/8 |  |
| oa_crosscheck_v1-332 | SPY | orb60 | C | 20/40 | oa1m | d40-55t45 | gap_side_075 | 69 | 26.10 | -11.68 | 0.44 | 0.31 | -822.76 | 0/8 |  |
| oa_crosscheck_v1-326 | SPY | orb60 | C | 20/20 | desk | d40-55t45 | gap_side_075 | 69 | 43.50 | -5.52 | 0.56 | 0.32 | -487.30 | 1/8 |  |
| oa_crosscheck_v1-328 | SPY | orb60 | C | 20/20 | oa1m | d40-55t45 | gap_side_075 | 69 | 44.90 | -5.86 | 0.61 | 0.39 | -633.80 | 1/8 |  |
| oa_crosscheck_v1-271 | SPY | orb60 | C | 15/45 | desk | d40-55t45 | skip_fomc_cpi | 119 | 16.80 | -10.13 | 0.41 | 0.26 | -1217.11 | 0/8 | PF 1.35 (OA-S1-079) |
| oa_crosscheck_v1-272 | SPY | orb60 | C | 15/45 | oa1m | d40-55t45 | skip_fomc_cpi | 119 | 20.20 | -10.10 | 0.51 | 0.35 | -1214.62 | 0/8 | PF 1.35 (OA-S1-079) |
| oa_crosscheck_v1-273 | SPY | orb60 | C | 10/30 | desk | d40-55t45 | skip_fomc_cpi | 119 | 16.00 | -7.80 | 0.37 | 0.19 | -973.16 | 0/8 |  |
| oa_crosscheck_v1-274 | SPY | orb60 | C | 10/30 | oa1m | d40-55t45 | skip_fomc_cpi | 119 | 24.40 | -6.80 | 0.55 | 0.33 | -895.10 | 1/8 |  |
| oa_crosscheck_v1-269 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | skip_fomc_cpi | 119 | 16.80 | -10.86 | 0.49 | 0.34 | -1310.24 | 1/8 | PF 1.32 (OA-S1-073) |
| oa_crosscheck_v1-270 | SPY | orb60 | C | 20/60 | oa1m | d40-55t45 | skip_fomc_cpi | 119 | 19.30 | -9.01 | 0.62 | 0.45 | -1092.12 | 1/8 | PF 1.32 (OA-S1-073) |
| oa_crosscheck_v1-267 | SPY | orb60 | C | 20/40 | desk | d40-55t45 | skip_fomc_cpi | 119 | 27.70 | -7.68 | 0.59 | 0.39 | -949.20 | 0/8 |  |
| oa_crosscheck_v1-268 | SPY | orb60 | C | 20/40 | oa1m | d40-55t45 | skip_fomc_cpi | 119 | 28.60 | -8.70 | 0.59 | 0.42 | -1042.14 | 1/8 |  |
| oa_crosscheck_v1-265 | SPY | orb60 | C | 20/20 | desk | d40-55t45 | skip_fomc_cpi | 119 | 43.70 | -6.15 | 0.57 | 0.32 | -759.43 | 1/8 |  |
| oa_crosscheck_v1-266 | SPY | orb60 | C | 20/20 | oa1m | d40-55t45 | skip_fomc_cpi | 119 | 45.40 | -4.39 | 0.72 | 0.46 | -642.88 | 1/8 |  |
| oa_crosscheck_v1-157 | SPY | orb60 | C | 15/45 | desk | d40-55t45 | sma20_side | 89 | 16.90 | -8.86 | 0.41 | 0.26 | -788.51 | 0/8 | PF 1.40 (OA-S1-078) |
| oa_crosscheck_v1-159 | SPY | orb60 | C | 15/45 | oa1m | d40-55t45 | sma20_side | 89 | 19.10 | -7.80 | 0.54 | 0.37 | -694.06 | 2/8 | PF 1.40 (OA-S1-078) |
| oa_crosscheck_v1-161 | SPY | orb60 | C | 10/30 | desk | d40-55t45 | sma20_side | 89 | 16.90 | -6.80 | 0.37 | 0.20 | -619.08 | 0/8 |  |
| oa_crosscheck_v1-163 | SPY | orb60 | C | 10/30 | oa1m | d40-55t45 | sma20_side | 89 | 23.60 | -5.36 | 0.57 | 0.34 | -490.84 | 1/8 |  |
| oa_crosscheck_v1-153 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | sma20_side | 89 | 14.60 | -11.21 | 0.41 | 0.29 | -998.09 | 1/8 | PF 1.31 (OA-S1-072) |
| oa_crosscheck_v1-155 | SPY | orb60 | C | 20/60 | oa1m | d40-55t45 | sma20_side | 89 | 16.90 | -11.26 | 0.47 | 0.34 | -1001.78 | 0/8 | PF 1.31 (OA-S1-072) |
| oa_crosscheck_v1-149 | SPY | orb60 | C | 20/40 | desk | d40-55t45 | sma20_side | 89 | 25.80 | -8.28 | 0.51 | 0.34 | -783.60 | 0/8 |  |
| oa_crosscheck_v1-151 | SPY | orb60 | C | 20/40 | oa1m | d40-55t45 | sma20_side | 89 | 25.80 | -8.54 | 0.56 | 0.39 | -779.44 | 0/8 |  |
| oa_crosscheck_v1-145 | SPY | orb60 | C | 20/20 | desk | d40-55t45 | sma20_side | 89 | 44.90 | -4.72 | 0.61 | 0.35 | -472.51 | 3/8 |  |
| oa_crosscheck_v1-147 | SPY | orb60 | C | 20/20 | oa1m | d40-55t45 | sma20_side | 89 | 43.80 | -4.14 | 0.70 | 0.45 | -453.72 | 2/8 |  |
| oa_crosscheck_v1-158 | SPY | orb60 | C | 15/45 | desk | d40-55t45 | sma20_side_1pct | 60 | 16.70 | -8.44 | 0.43 | 0.27 | -506.51 | 0/8 |  |
| oa_crosscheck_v1-160 | SPY | orb60 | C | 15/45 | oa1m | d40-55t45 | sma20_side_1pct | 60 | 20.00 | -6.44 | 0.61 | 0.42 | -386.42 | 1/8 |  |
| oa_crosscheck_v1-162 | SPY | orb60 | C | 10/30 | desk | d40-55t45 | sma20_side_1pct | 60 | 16.70 | -6.67 | 0.38 | 0.20 | -403.72 | 0/8 |  |
| oa_crosscheck_v1-164 | SPY | orb60 | C | 10/30 | oa1m | d40-55t45 | sma20_side_1pct | 60 | 23.30 | -5.44 | 0.56 | 0.33 | -331.58 | 0/8 |  |
| oa_crosscheck_v1-154 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | sma20_side_1pct | 60 | 11.70 | -12.84 | 0.34 | 0.24 | -770.42 | 0/8 |  |
| oa_crosscheck_v1-156 | SPY | orb60 | C | 20/60 | oa1m | d40-55t45 | sma20_side_1pct | 60 | 13.30 | -13.19 | 0.39 | 0.29 | -791.16 | 0/8 |  |
| oa_crosscheck_v1-150 | SPY | orb60 | C | 20/40 | desk | d40-55t45 | sma20_side_1pct | 60 | 23.30 | -8.90 | 0.48 | 0.32 | -592.41 | 0/8 |  |
| oa_crosscheck_v1-152 | SPY | orb60 | C | 20/40 | oa1m | d40-55t45 | sma20_side_1pct | 60 | 25.00 | -8.97 | 0.54 | 0.38 | -550.80 | 1/8 |  |
| oa_crosscheck_v1-146 | SPY | orb60 | C | 20/20 | desk | d40-55t45 | sma20_side_1pct | 60 | 45.00 | -3.87 | 0.67 | 0.38 | -264.88 | 3/8 |  |
| oa_crosscheck_v1-148 | SPY | orb60 | C | 20/20 | oa1m | d40-55t45 | sma20_side_1pct | 60 | 43.30 | -3.35 | 0.75 | 0.48 | -298.96 | 2/8 |  |
| oa_crosscheck_v1-337 | SPY | orb60 | C | 15/45 | desk | d40-55t45 | vixy_falling | 91 | 16.50 | -9.35 | 0.41 | 0.26 | -851.02 | 0/8 |  |
| oa_crosscheck_v1-339 | SPY | orb60 | C | 15/45 | oa1m | d40-55t45 | vixy_falling | 91 | 19.80 | -9.64 | 0.49 | 0.34 | -877.46 | 1/8 |  |
| oa_crosscheck_v1-341 | SPY | orb60 | C | 10/30 | desk | d40-55t45 | vixy_falling | 91 | 15.40 | -7.53 | 0.35 | 0.19 | -717.42 | 0/8 |  |
| oa_crosscheck_v1-343 | SPY | orb60 | C | 10/30 | oa1m | d40-55t45 | vixy_falling | 91 | 26.40 | -4.81 | 0.64 | 0.39 | -544.26 | 1/8 |  |
| oa_crosscheck_v1-333 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | vixy_falling | 91 | 18.70 | -8.22 | 0.57 | 0.40 | -748.02 | 1/8 |  |
| oa_crosscheck_v1-335 | SPY | orb60 | C | 20/60 | oa1m | d40-55t45 | vixy_falling | 91 | 20.90 | -7.28 | 0.67 | 0.49 | -690.28 | 1/8 |  |
| oa_crosscheck_v1-329 | SPY | orb60 | C | 20/40 | desk | d40-55t45 | vixy_falling | 91 | 28.60 | -6.36 | 0.63 | 0.42 | -672.04 | 2/8 |  |
| oa_crosscheck_v1-331 | SPY | orb60 | C | 20/40 | oa1m | d40-55t45 | vixy_falling | 91 | 29.70 | -7.78 | 0.61 | 0.44 | -707.62 | 1/8 |  |
| oa_crosscheck_v1-325 | SPY | orb60 | C | 20/20 | desk | d40-55t45 | vixy_falling | 91 | 47.30 | -3.96 | 0.68 | 0.39 | -440.00 | 3/8 |  |
| oa_crosscheck_v1-327 | SPY | orb60 | C | 20/20 | oa1m | d40-55t45 | vixy_falling | 91 | 47.30 | -3.44 | 0.76 | 0.49 | -486.88 | 2/8 |  |
| oa_crosscheck_v1-019 | SPY | orb60 | P | 15/45 | desk | d40-55t45 | - | 124 | 22.60 | -8.27 | 0.58 | 0.37 | -1094.47 | 1/8 | PF 0.88 (OA-S1-029) |
| oa_crosscheck_v1-020 | SPY | orb60 | P | 15/45 | oa1m | d40-55t45 | - | 124 | 24.20 | -7.64 | 0.68 | 0.47 | -1058.68 | 2/8 | PF 0.88 (OA-S1-029) |
| oa_crosscheck_v1-021 | SPY | orb60 | P | 10/30 | desk | d40-55t45 | - | 124 | 24.20 | -5.02 | 0.63 | 0.33 | -622.45 | 1/8 | PF 1.00 (OA-S1-030) |
| oa_crosscheck_v1-022 | SPY | orb60 | P | 10/30 | oa1m | d40-55t45 | - | 124 | 23.40 | -7.54 | 0.59 | 0.36 | -945.02 | 1/8 | PF 1.00 (OA-S1-030) |
| oa_crosscheck_v1-017 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | - | 124 | 21.80 | -8.56 | 0.66 | 0.46 | -1230.53 | 1/8 | PF 0.88 (OA-S1-028) |
| oa_crosscheck_v1-018 | SPY | orb60 | P | 20/60 | oa1m | d40-55t45 | - | 124 | 23.40 | -9.33 | 0.68 | 0.51 | -1612.72 | 2/8 | PF 0.88 (OA-S1-028) |
| oa_crosscheck_v1-015 | SPY | orb60 | P | 20/40 | desk | d40-55t45 | - | 124 | 30.60 | -7.16 | 0.68 | 0.46 | -976.45 | 2/8 | PF 0.87 (OA-S1-027) |
| oa_crosscheck_v1-016 | SPY | orb60 | P | 20/40 | oa1m | d40-55t45 | - | 124 | 30.60 | -9.02 | 0.67 | 0.48 | -1392.16 | 3/8 | PF 0.87 (OA-S1-027) |
| oa_crosscheck_v1-023 | SPY | orb60 | P | 50/100 | desk | d40-55t45 | - | 124 | 38.70 | 6.14 | 1.14 | 0.97 | -1158.06 | 4/8 | PF 0.73 (T2, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-024 | SPY | orb60 | P | 50/100 | oa1m | d40-55t45 | - | 124 | 37.10 | 8.36 | 1.18 | 1.02 | -1302.98 | 4/8 | PF 0.73 (T2, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-075 | SPY | orb60 | P | 50/100 | desk | d45-60t50 | - | 122 | 36.90 | 0.56 | 1.01 | 0.86 | -1401.05 | 4/8 | PF 0.73 (T2, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-076 | SPY | orb60 | P | 50/100 | oa1m | d45-60t50 | - | 122 | 36.10 | 0.95 | 1.02 | 0.88 | -1591.60 | 4/8 | PF 0.73 (T2, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-013 | SPY | orb60 | P | 20/20 | desk | d40-55t45 | - | 124 | 47.60 | -5.56 | 0.67 | 0.38 | -717.68 | 1/8 | PF 0.91 (OA-S1-026) |
| oa_crosscheck_v1-014 | SPY | orb60 | P | 20/20 | oa1m | d40-55t45 | - | 124 | 46.80 | -4.00 | 0.80 | 0.52 | -673.88 | 3/8 | PF 0.91 (OA-S1-026) |
| oa_crosscheck_v1-358 | SPY | orb60 | P | 15/45 | desk | d40-55t45 | gap_side_075 | 37 | 16.20 | -11.71 | 0.43 | 0.27 | -495.73 | 2/7 |  |
| oa_crosscheck_v1-360 | SPY | orb60 | P | 15/45 | oa1m | d40-55t45 | gap_side_075 | 37 | 16.20 | -15.57 | 0.39 | 0.27 | -660.62 | 2/7 |  |
| oa_crosscheck_v1-362 | SPY | orb60 | P | 10/30 | desk | d40-55t45 | gap_side_075 | 37 | 24.30 | -4.02 | 0.69 | 0.36 | -221.66 | 3/7 |  |
| oa_crosscheck_v1-364 | SPY | orb60 | P | 10/30 | oa1m | d40-55t45 | gap_side_075 | 37 | 16.20 | -12.65 | 0.36 | 0.22 | -562.62 | 2/7 |  |
| oa_crosscheck_v1-354 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | gap_side_075 | 37 | 13.50 | -17.28 | 0.36 | 0.25 | -725.06 | 1/7 |  |
| oa_crosscheck_v1-356 | SPY | orb60 | P | 20/60 | oa1m | d40-55t45 | gap_side_075 | 37 | 13.50 | -22.51 | 0.34 | 0.25 | -938.94 | 1/7 |  |
| oa_crosscheck_v1-350 | SPY | orb60 | P | 20/40 | desk | d40-55t45 | gap_side_075 | 37 | 18.90 | -17.40 | 0.32 | 0.21 | -692.67 | 1/7 |  |
| oa_crosscheck_v1-352 | SPY | orb60 | P | 20/40 | oa1m | d40-55t45 | gap_side_075 | 37 | 16.20 | -23.46 | 0.29 | 0.21 | -951.68 | 1/7 |  |
| oa_crosscheck_v1-346 | SPY | orb60 | P | 20/20 | desk | d40-55t45 | gap_side_075 | 37 | 43.20 | -8.87 | 0.51 | 0.29 | -373.98 | 2/7 |  |
| oa_crosscheck_v1-348 | SPY | orb60 | P | 20/20 | oa1m | d40-55t45 | gap_side_075 | 37 | 37.80 | -11.12 | 0.53 | 0.35 | -482.50 | 2/7 |  |
| oa_crosscheck_v1-281 | SPY | orb60 | P | 15/45 | desk | d40-55t45 | skip_fomc_cpi | 113 | 23.90 | -6.58 | 0.65 | 0.41 | -849.80 | 3/8 |  |
| oa_crosscheck_v1-282 | SPY | orb60 | P | 15/45 | oa1m | d40-55t45 | skip_fomc_cpi | 113 | 25.70 | -5.06 | 0.77 | 0.53 | -817.24 | 2/8 |  |
| oa_crosscheck_v1-283 | SPY | orb60 | P | 10/30 | desk | d40-55t45 | skip_fomc_cpi | 113 | 25.70 | -3.89 | 0.70 | 0.36 | -501.58 | 1/8 |  |
| oa_crosscheck_v1-284 | SPY | orb60 | P | 10/30 | oa1m | d40-55t45 | skip_fomc_cpi | 113 | 24.80 | -6.08 | 0.66 | 0.40 | -720.88 | 1/8 |  |
| oa_crosscheck_v1-279 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | skip_fomc_cpi | 113 | 23.00 | -6.41 | 0.73 | 0.51 | -959.18 | 2/8 |  |
| oa_crosscheck_v1-280 | SPY | orb60 | P | 20/60 | oa1m | d40-55t45 | skip_fomc_cpi | 113 | 24.80 | -6.71 | 0.76 | 0.56 | -1329.82 | 2/8 |  |
| oa_crosscheck_v1-277 | SPY | orb60 | P | 20/40 | desk | d40-55t45 | skip_fomc_cpi | 113 | 32.70 | -4.47 | 0.78 | 0.52 | -735.67 | 2/8 |  |
| oa_crosscheck_v1-278 | SPY | orb60 | P | 20/40 | oa1m | d40-55t45 | skip_fomc_cpi | 113 | 32.70 | -6.01 | 0.76 | 0.55 | -1143.58 | 3/8 |  |
| oa_crosscheck_v1-275 | SPY | orb60 | P | 20/20 | desk | d40-55t45 | skip_fomc_cpi | 113 | 48.70 | -4.20 | 0.72 | 0.41 | -533.72 | 2/8 |  |
| oa_crosscheck_v1-276 | SPY | orb60 | P | 20/20 | oa1m | d40-55t45 | skip_fomc_cpi | 113 | 48.70 | -1.77 | 0.90 | 0.59 | -542.28 | 3/8 |  |
| oa_crosscheck_v1-177 | SPY | orb60 | P | 15/45 | desk | d40-55t45 | sma20_side | 31 | 25.80 | -10.11 | 0.64 | 0.40 | -456.98 | 2/6 |  |
| oa_crosscheck_v1-179 | SPY | orb60 | P | 15/45 | oa1m | d40-55t45 | sma20_side | 31 | 32.30 | -4.18 | 0.87 | 0.59 | -434.68 | 3/6 |  |
| oa_crosscheck_v1-181 | SPY | orb60 | P | 10/30 | desk | d40-55t45 | sma20_side | 31 | 29.00 | -5.16 | 0.73 | 0.38 | -344.94 | 2/6 |  |
| oa_crosscheck_v1-183 | SPY | orb60 | P | 10/30 | oa1m | d40-55t45 | sma20_side | 31 | 32.30 | -4.65 | 0.80 | 0.47 | -298.44 | 2/6 |  |
| oa_crosscheck_v1-173 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | sma20_side | 31 | 32.30 | -0.02 | 1.00 | 0.70 | -426.63 | 3/6 |  |
| oa_crosscheck_v1-175 | SPY | orb60 | P | 20/60 | oa1m | d40-55t45 | sma20_side | 31 | 32.30 | -2.22 | 0.95 | 0.71 | -509.16 | 3/6 |  |
| oa_crosscheck_v1-169 | SPY | orb60 | P | 20/40 | desk | d40-55t45 | sma20_side | 31 | 38.70 | -1.87 | 0.94 | 0.62 | -350.64 | 3/6 |  |
| oa_crosscheck_v1-171 | SPY | orb60 | P | 20/40 | oa1m | d40-55t45 | sma20_side | 31 | 35.50 | -11.76 | 0.70 | 0.51 | -599.34 | 3/6 |  |
| oa_crosscheck_v1-165 | SPY | orb60 | P | 20/20 | desk | d40-55t45 | sma20_side | 31 | 58.10 | -2.20 | 0.90 | 0.51 | -378.39 | 3/6 |  |
| oa_crosscheck_v1-167 | SPY | orb60 | P | 20/20 | oa1m | d40-55t45 | sma20_side | 31 | 58.10 | -1.17 | 0.95 | 0.62 | -417.86 | 3/6 |  |
| oa_crosscheck_v1-178 | SPY | orb60 | P | 15/45 | desk | d40-55t45 | sma20_side_1pct | 24 | 25.00 | -12.37 | 0.59 | 0.37 | -426.21 | 2/5 |  |
| oa_crosscheck_v1-180 | SPY | orb60 | P | 15/45 | oa1m | d40-55t45 | sma20_side_1pct | 24 | 33.30 | -3.72 | 0.89 | 0.61 | -434.68 | 3/5 |  |
| oa_crosscheck_v1-182 | SPY | orb60 | P | 10/30 | desk | d40-55t45 | sma20_side_1pct | 24 | 29.20 | -5.78 | 0.72 | 0.37 | -322.82 | 2/5 |  |
| oa_crosscheck_v1-184 | SPY | orb60 | P | 10/30 | oa1m | d40-55t45 | sma20_side_1pct | 24 | 33.30 | -5.56 | 0.78 | 0.46 | -295.52 | 2/5 |  |
| oa_crosscheck_v1-174 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | sma20_side_1pct | 24 | 33.30 | 0.47 | 1.01 | 0.70 | -426.63 | 3/5 |  |
| oa_crosscheck_v1-176 | SPY | orb60 | P | 20/60 | oa1m | d40-55t45 | sma20_side_1pct | 24 | 33.30 | -2.91 | 0.93 | 0.69 | -509.16 | 3/5 |  |
| oa_crosscheck_v1-170 | SPY | orb60 | P | 20/40 | desk | d40-55t45 | sma20_side_1pct | 24 | 41.70 | 0.44 | 1.01 | 0.68 | -350.64 | 2/5 |  |
| oa_crosscheck_v1-172 | SPY | orb60 | P | 20/40 | oa1m | d40-55t45 | sma20_side_1pct | 24 | 33.30 | -15.57 | 0.64 | 0.46 | -570.58 | 2/5 |  |
| oa_crosscheck_v1-166 | SPY | orb60 | P | 20/20 | desk | d40-55t45 | sma20_side_1pct | 24 | 62.50 | -0.50 | 0.98 | 0.56 | -350.64 | 3/5 |  |
| oa_crosscheck_v1-168 | SPY | orb60 | P | 20/20 | oa1m | d40-55t45 | sma20_side_1pct | 24 | 58.30 | -1.56 | 0.94 | 0.60 | -417.86 | 3/5 |  |
| oa_crosscheck_v1-357 | SPY | orb60 | P | 15/45 | desk | d40-55t45 | vixy_falling | 46 | 21.70 | -8.54 | 0.57 | 0.36 | -392.65 | 3/8 |  |
| oa_crosscheck_v1-359 | SPY | orb60 | P | 15/45 | oa1m | d40-55t45 | vixy_falling | 46 | 19.60 | -11.73 | 0.53 | 0.36 | -539.48 | 3/8 |  |
| oa_crosscheck_v1-361 | SPY | orb60 | P | 10/30 | desk | d40-55t45 | vixy_falling | 46 | 21.70 | -5.62 | 0.60 | 0.32 | -258.71 | 2/8 |  |
| oa_crosscheck_v1-363 | SPY | orb60 | P | 10/30 | oa1m | d40-55t45 | vixy_falling | 46 | 19.60 | -10.92 | 0.44 | 0.26 | -502.24 | 1/8 |  |
| oa_crosscheck_v1-353 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | vixy_falling | 46 | 21.70 | -9.43 | 0.63 | 0.44 | -512.19 | 3/8 |  |
| oa_crosscheck_v1-355 | SPY | orb60 | P | 20/60 | oa1m | d40-55t45 | vixy_falling | 46 | 28.30 | -4.02 | 0.85 | 0.63 | -472.44 | 4/8 |  |
| oa_crosscheck_v1-349 | SPY | orb60 | P | 20/40 | desk | d40-55t45 | vixy_falling | 46 | 32.60 | -5.01 | 0.77 | 0.51 | -352.64 | 4/8 |  |
| oa_crosscheck_v1-351 | SPY | orb60 | P | 20/40 | oa1m | d40-55t45 | vixy_falling | 46 | 32.60 | -8.83 | 0.67 | 0.47 | -442.06 | 4/8 |  |
| oa_crosscheck_v1-345 | SPY | orb60 | P | 20/20 | desk | d40-55t45 | vixy_falling | 46 | 50.00 | -2.81 | 0.82 | 0.46 | -145.55 | 4/8 |  |
| oa_crosscheck_v1-347 | SPY | orb60 | P | 20/20 | oa1m | d40-55t45 | vixy_falling | 46 | 47.80 | -1.01 | 0.94 | 0.61 | -186.28 | 3/8 |  |
| oa_crosscheck_v1-098 | SPY | orb15 | C | 15/45 | desk | d40-55t45 | - | 211 | 23.20 | -3.38 | 0.81 | 0.51 | -1044.56 | 2/8 |  |
| oa_crosscheck_v1-099 | SPY | orb15 | C | 10/30 | desk | d40-55t45 | - | 211 | 19.90 | -5.91 | 0.57 | 0.30 | -1318.62 | 1/8 |  |
| oa_crosscheck_v1-097 | SPY | orb15 | C | 20/60 | desk | d40-55t45 | - | 211 | 22.70 | -5.61 | 0.76 | 0.53 | -1350.84 | 1/8 |  |
| oa_crosscheck_v1-096 | SPY | orb15 | C | 20/40 | desk | d40-55t45 | - | 211 | 32.70 | -3.09 | 0.85 | 0.57 | -939.13 | 2/8 |  |
| oa_crosscheck_v1-095 | SPY | orb15 | C | 20/20 | desk | d40-55t45 | - | 211 | 47.40 | -5.44 | 0.67 | 0.38 | -1413.62 | 2/8 |  |
| oa_crosscheck_v1-103 | SPY | orb15 | P | 15/45 | desk | d40-55t45 | - | 205 | 21.00 | -8.01 | 0.62 | 0.39 | -1642.70 | 1/8 |  |
| oa_crosscheck_v1-104 | SPY | orb15 | P | 10/30 | desk | d40-55t45 | - | 205 | 21.00 | -7.50 | 0.51 | 0.27 | -1536.97 | 0/8 |  |
| oa_crosscheck_v1-102 | SPY | orb15 | P | 20/60 | desk | d40-55t45 | - | 205 | 22.40 | -7.38 | 0.72 | 0.50 | -1513.53 | 1/8 |  |
| oa_crosscheck_v1-101 | SPY | orb15 | P | 20/40 | desk | d40-55t45 | - | 205 | 31.20 | -5.52 | 0.76 | 0.51 | -1135.68 | 1/8 |  |
| oa_crosscheck_v1-100 | SPY | orb15 | P | 20/20 | desk | d40-55t45 | - | 205 | 48.30 | -5.27 | 0.70 | 0.40 | -1079.72 | 0/8 |  |
| oa_crosscheck_v1-088 | SPY | orb30 | C | 15/45 | desk | d40-55t45 | - | 186 | 19.90 | -7.81 | 0.57 | 0.36 | -1477.02 | 1/8 |  |
| oa_crosscheck_v1-089 | SPY | orb30 | C | 10/30 | desk | d40-55t45 | - | 186 | 18.80 | -6.61 | 0.50 | 0.26 | -1228.86 | 2/8 |  |
| oa_crosscheck_v1-087 | SPY | orb30 | C | 20/60 | desk | d40-55t45 | - | 186 | 19.90 | -8.71 | 0.62 | 0.43 | -1821.90 | 1/8 |  |
| oa_crosscheck_v1-086 | SPY | orb30 | C | 20/40 | desk | d40-55t45 | - | 186 | 30.10 | -6.34 | 0.69 | 0.46 | -1290.02 | 2/8 |  |
| oa_crosscheck_v1-085 | SPY | orb30 | C | 20/20 | desk | d40-55t45 | - | 186 | 43.00 | -7.98 | 0.53 | 0.30 | -1484.64 | 1/8 |  |
| oa_crosscheck_v1-093 | SPY | orb30 | P | 15/45 | desk | d40-55t45 | - | 170 | 19.40 | -9.40 | 0.55 | 0.35 | -1772.79 | 0/8 |  |
| oa_crosscheck_v1-094 | SPY | orb30 | P | 10/30 | desk | d40-55t45 | - | 170 | 22.40 | -6.36 | 0.56 | 0.29 | -1135.28 | 1/8 |  |
| oa_crosscheck_v1-092 | SPY | orb30 | P | 20/60 | desk | d40-55t45 | - | 170 | 20.00 | -11.81 | 0.56 | 0.39 | -2266.71 | 0/8 |  |
| oa_crosscheck_v1-091 | SPY | orb30 | P | 20/40 | desk | d40-55t45 | - | 170 | 29.40 | -7.88 | 0.66 | 0.44 | -1496.88 | 0/8 |  |
| oa_crosscheck_v1-090 | SPY | orb30 | P | 20/20 | desk | d40-55t45 | - | 170 | 45.30 | -6.87 | 0.62 | 0.35 | -1168.36 | 0/8 |  |
| oa_crosscheck_v1-031 | QQQ | orb60 | C | 15/45 | desk | d40-55t45 | - | 135 | 15.60 | -10.99 | 0.41 | 0.26 | -1484.18 | 1/8 |  |
| oa_crosscheck_v1-032 | QQQ | orb60 | C | 15/45 | oa1m | d40-55t45 | - | 135 | 17.80 | -11.40 | 0.48 | 0.33 | -1577.50 | 1/8 |  |
| oa_crosscheck_v1-033 | QQQ | orb60 | C | 10/30 | desk | d40-55t45 | - | 135 | 17.80 | -8.14 | 0.39 | 0.21 | -1162.02 | 1/8 |  |
| oa_crosscheck_v1-034 | QQQ | orb60 | C | 10/30 | oa1m | d40-55t45 | - | 135 | 22.20 | -8.83 | 0.49 | 0.29 | -1307.54 | 1/8 |  |
| oa_crosscheck_v1-029 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | - | 135 | 15.60 | -13.78 | 0.42 | 0.30 | -1859.69 | 1/8 |  |
| oa_crosscheck_v1-030 | QQQ | orb60 | C | 20/60 | oa1m | d40-55t45 | - | 135 | 16.30 | -15.69 | 0.43 | 0.32 | -2118.54 | 1/8 |  |
| oa_crosscheck_v1-027 | QQQ | orb60 | C | 20/40 | desk | d40-55t45 | - | 135 | 23.70 | -10.95 | 0.49 | 0.33 | -1519.78 | 1/8 |  |
| oa_crosscheck_v1-028 | QQQ | orb60 | C | 20/40 | oa1m | d40-55t45 | - | 135 | 26.70 | -10.83 | 0.55 | 0.39 | -1490.28 | 0/8 |  |
| oa_crosscheck_v1-035 | QQQ | orb60 | C | 50/100 | desk | d40-55t45 | - | 135 | 30.40 | -8.99 | 0.79 | 0.67 | -1812.85 | 1/8 |  |
| oa_crosscheck_v1-036 | QQQ | orb60 | C | 50/100 | oa1m | d40-55t45 | - | 135 | 31.10 | -9.89 | 0.78 | 0.67 | -1779.28 | 2/8 |  |
| oa_crosscheck_v1-077 | QQQ | orb60 | C | 50/100 | desk | d45-60t50 | - | 134 | 32.10 | -10.63 | 0.78 | 0.66 | -2156.30 | 2/8 |  |
| oa_crosscheck_v1-078 | QQQ | orb60 | C | 50/100 | oa1m | d45-60t50 | - | 134 | 32.10 | -11.93 | 0.77 | 0.66 | -2291.98 | 2/8 |  |
| oa_crosscheck_v1-025 | QQQ | orb60 | C | 20/20 | desk | d40-55t45 | - | 135 | 37.00 | -10.40 | 0.42 | 0.24 | -1418.65 | 0/8 |  |
| oa_crosscheck_v1-026 | QQQ | orb60 | C | 20/20 | oa1m | d40-55t45 | - | 135 | 37.00 | -10.44 | 0.50 | 0.32 | -1426.72 | 1/8 |  |
| oa_crosscheck_v1-378 | QQQ | orb60 | C | 15/45 | desk | d40-55t45 | gap_side_075 | 56 | 17.90 | -8.66 | 0.47 | 0.30 | -519.95 | 2/8 |  |
| oa_crosscheck_v1-380 | QQQ | orb60 | C | 15/45 | oa1m | d40-55t45 | gap_side_075 | 56 | 21.40 | -8.02 | 0.58 | 0.39 | -566.40 | 2/8 |  |
| oa_crosscheck_v1-382 | QQQ | orb60 | C | 10/30 | desk | d40-55t45 | gap_side_075 | 56 | 25.00 | -4.18 | 0.62 | 0.33 | -352.02 | 1/8 |  |
| oa_crosscheck_v1-384 | QQQ | orb60 | C | 10/30 | oa1m | d40-55t45 | gap_side_075 | 56 | 28.60 | -3.05 | 0.78 | 0.47 | -445.72 | 3/8 |  |
| oa_crosscheck_v1-374 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | gap_side_075 | 56 | 19.60 | -9.33 | 0.55 | 0.38 | -571.56 | 2/8 |  |
| oa_crosscheck_v1-376 | QQQ | orb60 | C | 20/60 | oa1m | d40-55t45 | gap_side_075 | 56 | 17.90 | -13.58 | 0.47 | 0.35 | -760.72 | 2/8 |  |
| oa_crosscheck_v1-370 | QQQ | orb60 | C | 20/40 | desk | d40-55t45 | gap_side_075 | 56 | 30.40 | -4.84 | 0.72 | 0.48 | -501.92 | 4/8 |  |
| oa_crosscheck_v1-372 | QQQ | orb60 | C | 20/40 | oa1m | d40-55t45 | gap_side_075 | 56 | 32.10 | -6.44 | 0.69 | 0.50 | -506.48 | 2/8 |  |
| oa_crosscheck_v1-366 | QQQ | orb60 | C | 20/20 | desk | d40-55t45 | gap_side_075 | 56 | 42.90 | -7.08 | 0.52 | 0.29 | -513.65 | 2/8 |  |
| oa_crosscheck_v1-368 | QQQ | orb60 | C | 20/20 | oa1m | d40-55t45 | gap_side_075 | 56 | 42.90 | -6.51 | 0.64 | 0.42 | -548.62 | 4/8 |  |
| oa_crosscheck_v1-291 | QQQ | orb60 | C | 15/45 | desk | d40-55t45 | skip_fomc_cpi | 122 | 16.40 | -10.59 | 0.43 | 0.27 | -1292.46 | 1/8 |  |
| oa_crosscheck_v1-292 | QQQ | orb60 | C | 15/45 | oa1m | d40-55t45 | skip_fomc_cpi | 122 | 18.00 | -11.33 | 0.49 | 0.33 | -1421.16 | 1/8 |  |
| oa_crosscheck_v1-293 | QQQ | orb60 | C | 10/30 | desk | d40-55t45 | skip_fomc_cpi | 122 | 18.00 | -8.15 | 0.40 | 0.21 | -1057.71 | 1/8 |  |
| oa_crosscheck_v1-294 | QQQ | orb60 | C | 10/30 | oa1m | d40-55t45 | skip_fomc_cpi | 122 | 23.00 | -8.58 | 0.50 | 0.31 | -1145.52 | 1/8 |  |
| oa_crosscheck_v1-289 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | skip_fomc_cpi | 122 | 15.60 | -13.90 | 0.42 | 0.30 | -1695.32 | 1/8 |  |
| oa_crosscheck_v1-290 | QQQ | orb60 | C | 20/60 | oa1m | d40-55t45 | skip_fomc_cpi | 122 | 14.80 | -16.79 | 0.40 | 0.29 | -2048.44 | 0/8 |  |
| oa_crosscheck_v1-287 | QQQ | orb60 | C | 20/40 | desk | d40-55t45 | skip_fomc_cpi | 122 | 24.60 | -10.41 | 0.51 | 0.34 | -1318.56 | 0/8 |  |
| oa_crosscheck_v1-288 | QQQ | orb60 | C | 20/40 | oa1m | d40-55t45 | skip_fomc_cpi | 122 | 26.20 | -10.75 | 0.55 | 0.39 | -1354.26 | 0/8 |  |
| oa_crosscheck_v1-285 | QQQ | orb60 | C | 20/20 | desk | d40-55t45 | skip_fomc_cpi | 122 | 37.70 | -10.16 | 0.43 | 0.24 | -1255.07 | 0/8 |  |
| oa_crosscheck_v1-286 | QQQ | orb60 | C | 20/20 | oa1m | d40-55t45 | skip_fomc_cpi | 122 | 36.90 | -10.28 | 0.50 | 0.32 | -1265.16 | 0/8 |  |
| oa_crosscheck_v1-197 | QQQ | orb60 | C | 15/45 | desk | d40-55t45 | sma20_side | 89 | 15.70 | -9.38 | 0.44 | 0.28 | -870.56 | 1/8 |  |
| oa_crosscheck_v1-199 | QQQ | orb60 | C | 15/45 | oa1m | d40-55t45 | sma20_side | 89 | 19.10 | -8.63 | 0.56 | 0.38 | -855.18 | 1/8 |  |
| oa_crosscheck_v1-201 | QQQ | orb60 | C | 10/30 | desk | d40-55t45 | sma20_side | 89 | 16.90 | -7.68 | 0.38 | 0.20 | -747.28 | 1/8 |  |
| oa_crosscheck_v1-203 | QQQ | orb60 | C | 10/30 | oa1m | d40-55t45 | sma20_side | 89 | 21.30 | -8.09 | 0.47 | 0.29 | -798.64 | 2/8 |  |
| oa_crosscheck_v1-193 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | sma20_side | 89 | 15.70 | -12.12 | 0.44 | 0.31 | -1217.13 | 1/8 |  |
| oa_crosscheck_v1-195 | QQQ | orb60 | C | 20/60 | oa1m | d40-55t45 | sma20_side | 89 | 18.00 | -12.29 | 0.50 | 0.37 | -1241.30 | 1/8 |  |
| oa_crosscheck_v1-189 | QQQ | orb60 | C | 20/40 | desk | d40-55t45 | sma20_side | 89 | 21.30 | -11.26 | 0.44 | 0.29 | -1038.89 | 1/8 |  |
| oa_crosscheck_v1-191 | QQQ | orb60 | C | 20/40 | oa1m | d40-55t45 | sma20_side | 89 | 25.80 | -10.40 | 0.54 | 0.38 | -960.04 | 1/8 |  |
| oa_crosscheck_v1-185 | QQQ | orb60 | C | 20/20 | desk | d40-55t45 | sma20_side | 89 | 37.10 | -9.30 | 0.42 | 0.24 | -833.31 | 1/8 |  |
| oa_crosscheck_v1-187 | QQQ | orb60 | C | 20/20 | oa1m | d40-55t45 | sma20_side | 89 | 37.10 | -9.54 | 0.50 | 0.32 | -923.56 | 1/8 |  |
| oa_crosscheck_v1-198 | QQQ | orb60 | C | 15/45 | desk | d40-55t45 | sma20_side_1pct | 61 | 16.40 | -8.54 | 0.47 | 0.30 | -564.18 | 1/8 |  |
| oa_crosscheck_v1-200 | QQQ | orb60 | C | 15/45 | oa1m | d40-55t45 | sma20_side_1pct | 61 | 19.70 | -7.89 | 0.58 | 0.40 | -593.44 | 2/8 |  |
| oa_crosscheck_v1-202 | QQQ | orb60 | C | 10/30 | desk | d40-55t45 | sma20_side_1pct | 61 | 19.70 | -6.58 | 0.43 | 0.23 | -453.63 | 2/8 |  |
| oa_crosscheck_v1-204 | QQQ | orb60 | C | 10/30 | oa1m | d40-55t45 | sma20_side_1pct | 61 | 23.00 | -6.99 | 0.51 | 0.30 | -483.92 | 2/8 |  |
| oa_crosscheck_v1-194 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | sma20_side_1pct | 61 | 16.40 | -11.41 | 0.46 | 0.32 | -834.96 | 2/8 |  |
| oa_crosscheck_v1-196 | QQQ | orb60 | C | 20/60 | oa1m | d40-55t45 | sma20_side_1pct | 61 | 21.30 | -8.92 | 0.62 | 0.46 | -687.52 | 2/8 |  |
| oa_crosscheck_v1-190 | QQQ | orb60 | C | 20/40 | desk | d40-55t45 | sma20_side_1pct | 61 | 23.00 | -9.92 | 0.48 | 0.32 | -666.43 | 2/8 |  |
| oa_crosscheck_v1-192 | QQQ | orb60 | C | 20/40 | oa1m | d40-55t45 | sma20_side_1pct | 61 | 29.50 | -8.43 | 0.60 | 0.43 | -593.44 | 2/8 |  |
| oa_crosscheck_v1-186 | QQQ | orb60 | C | 20/20 | desk | d40-55t45 | sma20_side_1pct | 61 | 41.00 | -7.40 | 0.50 | 0.28 | -517.57 | 3/8 |  |
| oa_crosscheck_v1-188 | QQQ | orb60 | C | 20/20 | oa1m | d40-55t45 | sma20_side_1pct | 61 | 42.60 | -7.26 | 0.58 | 0.38 | -572.90 | 2/8 |  |
| oa_crosscheck_v1-377 | QQQ | orb60 | C | 15/45 | desk | d40-55t45 | vixy_falling | 95 | 14.70 | -10.89 | 0.40 | 0.25 | -1034.90 | 0/8 |  |
| oa_crosscheck_v1-379 | QQQ | orb60 | C | 15/45 | oa1m | d40-55t45 | vixy_falling | 95 | 15.80 | -12.43 | 0.42 | 0.28 | -1270.24 | 0/8 |  |
| oa_crosscheck_v1-381 | QQQ | orb60 | C | 10/30 | desk | d40-55t45 | vixy_falling | 95 | 16.80 | -8.28 | 0.37 | 0.19 | -813.41 | 1/8 |  |
| oa_crosscheck_v1-383 | QQQ | orb60 | C | 10/30 | oa1m | d40-55t45 | vixy_falling | 95 | 20.00 | -8.47 | 0.47 | 0.28 | -910.24 | 0/8 |  |
| oa_crosscheck_v1-373 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | vixy_falling | 95 | 13.70 | -15.27 | 0.36 | 0.25 | -1450.54 | 1/8 |  |
| oa_crosscheck_v1-375 | QQQ | orb60 | C | 20/60 | oa1m | d40-55t45 | vixy_falling | 95 | 14.70 | -16.98 | 0.38 | 0.28 | -1613.18 | 0/8 |  |
| oa_crosscheck_v1-369 | QQQ | orb60 | C | 20/40 | desk | d40-55t45 | vixy_falling | 95 | 21.10 | -11.85 | 0.44 | 0.30 | -1204.21 | 0/8 |  |
| oa_crosscheck_v1-371 | QQQ | orb60 | C | 20/40 | oa1m | d40-55t45 | vixy_falling | 95 | 26.30 | -10.42 | 0.55 | 0.39 | -1079.14 | 0/8 |  |
| oa_crosscheck_v1-365 | QQQ | orb60 | C | 20/20 | desk | d40-55t45 | vixy_falling | 95 | 34.70 | -10.74 | 0.39 | 0.22 | -1089.27 | 1/8 |  |
| oa_crosscheck_v1-367 | QQQ | orb60 | C | 20/20 | oa1m | d40-55t45 | vixy_falling | 95 | 34.70 | -10.68 | 0.48 | 0.31 | -1064.44 | 0/8 |  |
| oa_crosscheck_v1-043 | QQQ | orb60 | P | 15/45 | desk | d40-55t45 | - | 111 | 22.50 | -6.34 | 0.69 | 0.43 | -854.70 | 1/8 |  |
| oa_crosscheck_v1-044 | QQQ | orb60 | P | 15/45 | oa1m | d40-55t45 | - | 111 | 25.20 | -4.89 | 0.80 | 0.55 | -896.42 | 3/8 |  |
| oa_crosscheck_v1-045 | QQQ | orb60 | P | 10/30 | desk | d40-55t45 | - | 111 | 18.00 | -8.34 | 0.47 | 0.24 | -988.31 | 0/8 |  |
| oa_crosscheck_v1-046 | QQQ | orb60 | P | 10/30 | oa1m | d40-55t45 | - | 111 | 24.30 | -6.40 | 0.68 | 0.42 | -803.06 | 2/8 |  |
| oa_crosscheck_v1-041 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | - | 111 | 23.40 | -3.87 | 0.85 | 0.59 | -904.07 | 3/8 |  |
| oa_crosscheck_v1-042 | QQQ | orb60 | P | 20/60 | oa1m | d40-55t45 | - | 111 | 23.40 | -4.21 | 0.86 | 0.63 | -1069.82 | 3/8 |  |
| oa_crosscheck_v1-039 | QQQ | orb60 | P | 20/40 | desk | d40-55t45 | - | 111 | 34.20 | -1.70 | 0.92 | 0.62 | -598.59 | 4/8 |  |
| oa_crosscheck_v1-040 | QQQ | orb60 | P | 20/40 | oa1m | d40-55t45 | - | 111 | 34.20 | -0.25 | 0.99 | 0.71 | -680.08 | 4/8 |  |
| oa_crosscheck_v1-047 | QQQ | orb60 | P | 50/100 | desk | d40-55t45 | - | 111 | 36.00 | 5.07 | 1.10 | 0.94 | -932.81 | 3/8 |  |
| oa_crosscheck_v1-048 | QQQ | orb60 | P | 50/100 | oa1m | d40-55t45 | - | 111 | 34.20 | 5.31 | 1.10 | 0.95 | -1054.24 | 4/8 |  |
| oa_crosscheck_v1-079 | QQQ | orb60 | P | 50/100 | desk | d45-60t50 | - | 110 | 36.40 | 4.97 | 1.09 | 0.93 | -1087.27 | 4/8 |  |
| oa_crosscheck_v1-080 | QQQ | orb60 | P | 50/100 | oa1m | d45-60t50 | - | 110 | 36.40 | 10.12 | 1.17 | 1.01 | -1120.28 | 6/8 |  |
| oa_crosscheck_v1-037 | QQQ | orb60 | P | 20/20 | desk | d40-55t45 | - | 111 | 51.40 | -1.26 | 0.92 | 0.52 | -528.96 | 3/8 |  |
| oa_crosscheck_v1-038 | QQQ | orb60 | P | 20/20 | oa1m | d40-55t45 | - | 111 | 47.70 | -1.57 | 0.92 | 0.60 | -582.84 | 4/8 |  |
| oa_crosscheck_v1-398 | QQQ | orb60 | P | 15/45 | desk | d40-55t45 | gap_side_075 | 31 | 29.00 | 0.65 | 1.04 | 0.65 | -248.11 | 3/7 |  |
| oa_crosscheck_v1-400 | QQQ | orb60 | P | 15/45 | oa1m | d40-55t45 | gap_side_075 | 31 | 25.80 | -10.14 | 0.62 | 0.43 | -578.82 | 3/7 |  |
| oa_crosscheck_v1-402 | QQQ | orb60 | P | 10/30 | desk | d40-55t45 | gap_side_075 | 31 | 19.40 | -5.45 | 0.62 | 0.33 | -305.59 | 1/7 |  |
| oa_crosscheck_v1-404 | QQQ | orb60 | P | 10/30 | oa1m | d40-55t45 | gap_side_075 | 31 | 32.30 | -2.93 | 0.84 | 0.52 | -332.84 | 3/7 |  |
| oa_crosscheck_v1-394 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | gap_side_075 | 31 | 22.60 | -6.63 | 0.74 | 0.52 | -555.94 | 2/7 |  |
| oa_crosscheck_v1-396 | QQQ | orb60 | P | 20/60 | oa1m | d40-55t45 | gap_side_075 | 31 | 22.60 | -10.01 | 0.68 | 0.50 | -705.24 | 2/7 |  |
| oa_crosscheck_v1-390 | QQQ | orb60 | P | 20/40 | desk | d40-55t45 | gap_side_075 | 31 | 32.30 | -2.46 | 0.89 | 0.59 | -310.36 | 3/7 |  |
| oa_crosscheck_v1-392 | QQQ | orb60 | P | 20/40 | oa1m | d40-55t45 | gap_side_075 | 31 | 29.00 | -9.44 | 0.66 | 0.47 | -523.94 | 3/7 |  |
| oa_crosscheck_v1-386 | QQQ | orb60 | P | 20/20 | desk | d40-55t45 | gap_side_075 | 31 | 48.40 | -4.01 | 0.76 | 0.43 | -281.06 | 2/7 |  |
| oa_crosscheck_v1-388 | QQQ | orb60 | P | 20/20 | oa1m | d40-55t45 | gap_side_075 | 31 | 41.90 | -7.92 | 0.64 | 0.42 | -465.78 | 3/7 |  |
| oa_crosscheck_v1-301 | QQQ | orb60 | P | 15/45 | desk | d40-55t45 | skip_fomc_cpi | 101 | 22.80 | -6.62 | 0.67 | 0.42 | -783.42 | 1/8 |  |
| oa_crosscheck_v1-302 | QQQ | orb60 | P | 15/45 | oa1m | d40-55t45 | skip_fomc_cpi | 101 | 24.80 | -5.73 | 0.76 | 0.52 | -903.90 | 2/8 |  |
| oa_crosscheck_v1-303 | QQQ | orb60 | P | 10/30 | desk | d40-55t45 | skip_fomc_cpi | 101 | 18.80 | -7.77 | 0.48 | 0.25 | -869.25 | 0/8 |  |
| oa_crosscheck_v1-304 | QQQ | orb60 | P | 10/30 | oa1m | d40-55t45 | skip_fomc_cpi | 101 | 24.80 | -6.24 | 0.68 | 0.43 | -746.90 | 2/8 |  |
| oa_crosscheck_v1-299 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | skip_fomc_cpi | 101 | 22.80 | -4.54 | 0.81 | 0.57 | -911.12 | 3/8 |  |
| oa_crosscheck_v1-300 | QQQ | orb60 | P | 20/60 | oa1m | d40-55t45 | skip_fomc_cpi | 101 | 22.80 | -4.88 | 0.83 | 0.61 | -1084.08 | 3/8 |  |
| oa_crosscheck_v1-297 | QQQ | orb60 | P | 20/40 | desk | d40-55t45 | skip_fomc_cpi | 101 | 32.70 | -4.20 | 0.81 | 0.54 | -709.60 | 2/8 |  |
| oa_crosscheck_v1-298 | QQQ | orb60 | P | 20/40 | oa1m | d40-55t45 | skip_fomc_cpi | 101 | 33.70 | -1.34 | 0.95 | 0.68 | -585.60 | 3/8 |  |
| oa_crosscheck_v1-295 | QQQ | orb60 | P | 20/20 | desk | d40-55t45 | skip_fomc_cpi | 101 | 47.50 | -4.26 | 0.74 | 0.42 | -616.22 | 3/8 |  |
| oa_crosscheck_v1-296 | QQQ | orb60 | P | 20/20 | oa1m | d40-55t45 | skip_fomc_cpi | 101 | 44.60 | -4.29 | 0.80 | 0.53 | -595.24 | 3/8 |  |
| oa_crosscheck_v1-217 | QQQ | orb60 | P | 15/45 | desk | d40-55t45 | sma20_side | 30 | 16.70 | -11.68 | 0.58 | 0.36 | -504.42 | 1/7 |  |
| oa_crosscheck_v1-219 | QQQ | orb60 | P | 15/45 | oa1m | d40-55t45 | sma20_side | 30 | 26.70 | -1.07 | 0.96 | 0.65 | -476.52 | 2/7 |  |
| oa_crosscheck_v1-221 | QQQ | orb60 | P | 10/30 | desk | d40-55t45 | sma20_side | 30 | 10.00 | -14.53 | 0.32 | 0.17 | -462.66 | 0/7 |  |
| oa_crosscheck_v1-223 | QQQ | orb60 | P | 10/30 | oa1m | d40-55t45 | sma20_side | 30 | 23.30 | -6.59 | 0.74 | 0.46 | -444.02 | 2/7 |  |
| oa_crosscheck_v1-213 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | sma20_side | 30 | 23.30 | 0.78 | 1.02 | 0.71 | -451.34 | 2/7 |  |
| oa_crosscheck_v1-215 | QQQ | orb60 | P | 20/60 | oa1m | d40-55t45 | sma20_side | 30 | 30.00 | 13.07 | 1.39 | 1.02 | -538.26 | 2/7 |  |
| oa_crosscheck_v1-209 | QQQ | orb60 | P | 20/40 | desk | d40-55t45 | sma20_side | 30 | 33.30 | 1.05 | 1.04 | 0.69 | -308.28 | 2/7 |  |
| oa_crosscheck_v1-211 | QQQ | orb60 | P | 20/40 | oa1m | d40-55t45 | sma20_side | 30 | 43.30 | 14.31 | 1.53 | 1.09 | -285.98 | 2/7 |  |
| oa_crosscheck_v1-205 | QQQ | orb60 | P | 20/20 | desk | d40-55t45 | sma20_side | 30 | 53.30 | 1.67 | 1.09 | 0.62 | -248.74 | 3/7 |  |
| oa_crosscheck_v1-207 | QQQ | orb60 | P | 20/20 | oa1m | d40-55t45 | sma20_side | 30 | 53.30 | 3.11 | 1.14 | 0.74 | -252.16 | 3/7 |  |
| oa_crosscheck_v1-218 | QQQ | orb60 | P | 15/45 | desk | d40-55t45 | sma20_side_1pct | 22 | 18.20 | -13.27 | 0.53 | 0.34 | -365.98 | 1/4 |  |
| oa_crosscheck_v1-220 | QQQ | orb60 | P | 15/45 | oa1m | d40-55t45 | sma20_side_1pct | 22 | 27.30 | -3.61 | 0.88 | 0.59 | -346.72 | 2/4 |  |
| oa_crosscheck_v1-222 | QQQ | orb60 | P | 10/30 | desk | d40-55t45 | sma20_side_1pct | 22 | 9.10 | -17.42 | 0.23 | 0.12 | -410.02 | 0/4 |  |
| oa_crosscheck_v1-224 | QQQ | orb60 | P | 10/30 | oa1m | d40-55t45 | sma20_side_1pct | 22 | 27.30 | -5.13 | 0.80 | 0.50 | -305.56 | 2/4 |  |
| oa_crosscheck_v1-214 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | sma20_side_1pct | 22 | 22.70 | -4.44 | 0.87 | 0.60 | -351.46 | 2/4 |  |
| oa_crosscheck_v1-216 | QQQ | orb60 | P | 20/60 | oa1m | d40-55t45 | sma20_side_1pct | 22 | 31.80 | 13.54 | 1.41 | 1.03 | -410.42 | 2/4 |  |
| oa_crosscheck_v1-210 | QQQ | orb60 | P | 20/40 | desk | d40-55t45 | sma20_side_1pct | 22 | 36.40 | 1.17 | 1.04 | 0.70 | -177.94 | 2/4 |  |
| oa_crosscheck_v1-212 | QQQ | orb60 | P | 20/40 | oa1m | d40-55t45 | sma20_side_1pct | 22 | 50.00 | 21.15 | 1.89 | 1.33 | -165.72 | 3/4 |  |
| oa_crosscheck_v1-206 | QQQ | orb60 | P | 20/20 | desk | d40-55t45 | sma20_side_1pct | 22 | 54.50 | 2.30 | 1.13 | 0.64 | -180.93 | 2/4 |  |
| oa_crosscheck_v1-208 | QQQ | orb60 | P | 20/20 | oa1m | d40-55t45 | sma20_side_1pct | 22 | 59.10 | 9.97 | 1.51 | 0.98 | -143.48 | 2/4 |  |
| oa_crosscheck_v1-397 | QQQ | orb60 | P | 15/45 | desk | d40-55t45 | vixy_falling | 43 | 18.60 | -10.16 | 0.53 | 0.34 | -436.72 | 2/7 |  |
| oa_crosscheck_v1-399 | QQQ | orb60 | P | 15/45 | oa1m | d40-55t45 | vixy_falling | 43 | 18.60 | -12.87 | 0.53 | 0.36 | -645.30 | 3/7 |  |
| oa_crosscheck_v1-401 | QQQ | orb60 | P | 10/30 | desk | d40-55t45 | vixy_falling | 43 | 16.30 | -9.92 | 0.39 | 0.20 | -466.93 | 2/7 |  |
| oa_crosscheck_v1-403 | QQQ | orb60 | P | 10/30 | oa1m | d40-55t45 | vixy_falling | 43 | 18.60 | -10.71 | 0.47 | 0.28 | -460.48 | 2/7 |  |
| oa_crosscheck_v1-393 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | vixy_falling | 43 | 20.90 | -8.32 | 0.69 | 0.48 | -442.74 | 3/7 |  |
| oa_crosscheck_v1-395 | QQQ | orb60 | P | 20/60 | oa1m | d40-55t45 | vixy_falling | 43 | 20.90 | -9.36 | 0.70 | 0.51 | -494.38 | 2/7 |  |
| oa_crosscheck_v1-389 | QQQ | orb60 | P | 20/40 | desk | d40-55t45 | vixy_falling | 43 | 34.90 | -2.95 | 0.87 | 0.58 | -287.03 | 3/7 |  |
| oa_crosscheck_v1-391 | QQQ | orb60 | P | 20/40 | oa1m | d40-55t45 | vixy_falling | 43 | 30.20 | -5.65 | 0.79 | 0.56 | -372.80 | 2/7 |  |
| oa_crosscheck_v1-385 | QQQ | orb60 | P | 20/20 | desk | d40-55t45 | vixy_falling | 43 | 60.50 | 5.53 | 1.48 | 0.84 | -133.20 | 4/7 |  |
| oa_crosscheck_v1-387 | QQQ | orb60 | P | 20/20 | oa1m | d40-55t45 | vixy_falling | 43 | 53.50 | 2.78 | 1.16 | 0.75 | -174.48 | 3/7 |  |
| oa_crosscheck_v1-118 | QQQ | orb15 | C | 15/45 | desk | d40-55t45 | - | 207 | 16.90 | -11.98 | 0.46 | 0.29 | -2480.68 | 0/8 |  |
| oa_crosscheck_v1-119 | QQQ | orb15 | C | 10/30 | desk | d40-55t45 | - | 207 | 16.90 | -9.13 | 0.42 | 0.22 | -1890.91 | 0/8 |  |
| oa_crosscheck_v1-117 | QQQ | orb15 | C | 20/60 | desk | d40-55t45 | - | 207 | 24.20 | -6.67 | 0.74 | 0.52 | -1430.98 | 1/8 |  |
| oa_crosscheck_v1-116 | QQQ | orb15 | C | 20/40 | desk | d40-55t45 | - | 207 | 30.90 | -7.08 | 0.70 | 0.47 | -1568.86 | 1/8 |  |
| oa_crosscheck_v1-115 | QQQ | orb15 | C | 20/20 | desk | d40-55t45 | - | 207 | 44.90 | -8.68 | 0.55 | 0.31 | -1823.63 | 0/8 |  |
| oa_crosscheck_v1-123 | QQQ | orb15 | P | 15/45 | desk | d40-55t45 | - | 197 | 20.30 | -10.49 | 0.56 | 0.35 | -2287.93 | 2/8 |  |
| oa_crosscheck_v1-124 | QQQ | orb15 | P | 10/30 | desk | d40-55t45 | - | 197 | 18.80 | -9.57 | 0.45 | 0.23 | -1931.86 | 0/8 |  |
| oa_crosscheck_v1-122 | QQQ | orb15 | P | 20/60 | desk | d40-55t45 | - | 197 | 20.80 | -11.87 | 0.60 | 0.42 | -2403.05 | 1/8 |  |
| oa_crosscheck_v1-121 | QQQ | orb15 | P | 20/40 | desk | d40-55t45 | - | 197 | 25.90 | -12.81 | 0.54 | 0.36 | -2694.57 | 1/8 |  |
| oa_crosscheck_v1-120 | QQQ | orb15 | P | 20/20 | desk | d40-55t45 | - | 197 | 43.10 | -9.63 | 0.55 | 0.31 | -1939.44 | 0/8 |  |
| oa_crosscheck_v1-108 | QQQ | orb30 | C | 15/45 | desk | d40-55t45 | - | 181 | 16.00 | -11.11 | 0.47 | 0.29 | -2010.72 | 0/8 |  |
| oa_crosscheck_v1-109 | QQQ | orb30 | C | 10/30 | desk | d40-55t45 | - | 181 | 19.30 | -7.40 | 0.49 | 0.26 | -1367.39 | 1/8 |  |
| oa_crosscheck_v1-107 | QQQ | orb30 | C | 20/60 | desk | d40-55t45 | - | 181 | 19.90 | -10.03 | 0.61 | 0.43 | -1843.23 | 0/8 |  |
| oa_crosscheck_v1-106 | QQQ | orb30 | C | 20/40 | desk | d40-55t45 | - | 181 | 28.70 | -8.44 | 0.63 | 0.42 | -1571.24 | 1/8 |  |
| oa_crosscheck_v1-105 | QQQ | orb30 | C | 20/20 | desk | d40-55t45 | - | 181 | 42.50 | -9.51 | 0.50 | 0.28 | -1720.79 | 0/8 |  |
| oa_crosscheck_v1-113 | QQQ | orb30 | P | 15/45 | desk | d40-55t45 | - | 159 | 20.10 | -8.36 | 0.62 | 0.39 | -1561.20 | 2/8 |  |
| oa_crosscheck_v1-114 | QQQ | orb30 | P | 10/30 | desk | d40-55t45 | - | 159 | 20.10 | -7.69 | 0.53 | 0.28 | -1269.18 | 1/8 |  |
| oa_crosscheck_v1-112 | QQQ | orb30 | P | 20/60 | desk | d40-55t45 | - | 159 | 19.50 | -12.69 | 0.56 | 0.39 | -2145.88 | 1/8 |  |
| oa_crosscheck_v1-111 | QQQ | orb30 | P | 20/40 | desk | d40-55t45 | - | 159 | 25.80 | -11.58 | 0.57 | 0.38 | -2024.75 | 1/8 |  |
| oa_crosscheck_v1-110 | QQQ | orb30 | P | 20/20 | desk | d40-55t45 | - | 159 | 43.40 | -9.03 | 0.56 | 0.32 | -1484.92 | 1/8 |  |
| oa_crosscheck_v1-055 | IWM | orb60 | C | 15/45 | desk | d40-55t45 | - | 67 | 13.40 | -7.52 | 0.33 | 0.21 | -582.69 | 1/8 |  |
| oa_crosscheck_v1-056 | IWM | orb60 | C | 15/45 | oa1m | d40-55t45 | - | 67 | 19.40 | -6.92 | 0.45 | 0.30 | -543.72 | 1/8 |  |
| oa_crosscheck_v1-057 | IWM | orb60 | C | 10/30 | desk | d40-55t45 | - | 67 | 16.40 | -5.24 | 0.35 | 0.19 | -403.12 | 0/8 |  |
| oa_crosscheck_v1-058 | IWM | orb60 | C | 10/30 | oa1m | d40-55t45 | - | 67 | 16.40 | -7.33 | 0.31 | 0.19 | -547.04 | 0/8 |  |
| oa_crosscheck_v1-053 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | - | 67 | 19.40 | -5.27 | 0.60 | 0.42 | -461.67 | 2/8 |  |
| oa_crosscheck_v1-054 | IWM | orb60 | C | 20/60 | oa1m | d40-55t45 | - | 67 | 19.40 | -8.48 | 0.47 | 0.35 | -637.04 | 2/8 |  |
| oa_crosscheck_v1-051 | IWM | orb60 | C | 20/40 | desk | d40-55t45 | - | 67 | 28.40 | -5.26 | 0.56 | 0.38 | -420.23 | 1/8 |  |
| oa_crosscheck_v1-052 | IWM | orb60 | C | 20/40 | oa1m | d40-55t45 | - | 67 | 31.30 | -5.85 | 0.58 | 0.41 | -470.22 | 2/8 |  |
| oa_crosscheck_v1-059 | IWM | orb60 | C | 50/100 | desk | d40-55t45 | - | 67 | 22.40 | -15.20 | 0.46 | 0.39 | -1109.30 | 1/8 |  |
| oa_crosscheck_v1-060 | IWM | orb60 | C | 50/100 | oa1m | d40-55t45 | - | 67 | 23.90 | -13.94 | 0.52 | 0.45 | -1034.16 | 2/8 |  |
| oa_crosscheck_v1-081 | IWM | orb60 | C | 50/100 | desk | d45-60t50 | - | 85 | 30.60 | -6.73 | 0.77 | 0.65 | -818.52 | 2/8 |  |
| oa_crosscheck_v1-082 | IWM | orb60 | C | 50/100 | oa1m | d45-60t50 | - | 85 | 31.80 | -8.92 | 0.71 | 0.60 | -758.06 | 2/8 |  |
| oa_crosscheck_v1-049 | IWM | orb60 | C | 20/20 | desk | d40-55t45 | - | 67 | 41.80 | -5.73 | 0.42 | 0.24 | -402.79 | 1/8 |  |
| oa_crosscheck_v1-050 | IWM | orb60 | C | 20/20 | oa1m | d40-55t45 | - | 67 | 41.80 | -7.30 | 0.41 | 0.26 | -518.24 | 1/8 |  |
| oa_crosscheck_v1-418 | IWM | orb60 | C | 15/45 | desk | d40-55t45 | gap_side_075 | 21 | 14.30 | -6.31 | 0.39 | 0.25 | -181.97 | 0/7 |  |
| oa_crosscheck_v1-420 | IWM | orb60 | C | 15/45 | oa1m | d40-55t45 | gap_side_075 | 21 | 28.60 | -2.22 | 0.78 | 0.53 | -109.10 | 3/7 |  |
| oa_crosscheck_v1-422 | IWM | orb60 | C | 10/30 | desk | d40-55t45 | gap_side_075 | 21 | 14.30 | -5.02 | 0.34 | 0.18 | -137.14 | 0/7 |  |
| oa_crosscheck_v1-424 | IWM | orb60 | C | 10/30 | oa1m | d40-55t45 | gap_side_075 | 21 | 19.00 | -5.20 | 0.41 | 0.24 | -139.52 | 1/7 |  |
| oa_crosscheck_v1-414 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | gap_side_075 | 21 | 19.00 | -5.54 | 0.56 | 0.39 | -183.35 | 2/7 |  |
| oa_crosscheck_v1-416 | IWM | orb60 | C | 20/60 | oa1m | d40-55t45 | gap_side_075 | 21 | 19.00 | -10.94 | 0.33 | 0.24 | -229.82 | 1/7 |  |
| oa_crosscheck_v1-410 | IWM | orb60 | C | 20/40 | desk | d40-55t45 | gap_side_075 | 21 | 38.10 | -2.31 | 0.77 | 0.52 | -95.23 | 4/7 |  |
| oa_crosscheck_v1-412 | IWM | orb60 | C | 20/40 | oa1m | d40-55t45 | gap_side_075 | 21 | 38.10 | -3.80 | 0.69 | 0.49 | -124.82 | 3/7 |  |
| oa_crosscheck_v1-406 | IWM | orb60 | C | 20/20 | desk | d40-55t45 | gap_side_075 | 21 | 42.90 | -5.81 | 0.39 | 0.22 | -148.69 | 2/7 |  |
| oa_crosscheck_v1-408 | IWM | orb60 | C | 20/20 | oa1m | d40-55t45 | gap_side_075 | 21 | 47.60 | -5.34 | 0.51 | 0.33 | -153.08 | 2/7 |  |
| oa_crosscheck_v1-311 | IWM | orb60 | C | 15/45 | desk | d40-55t45 | skip_fomc_cpi | 62 | 12.90 | -7.34 | 0.31 | 0.20 | -487.73 | 0/8 |  |
| oa_crosscheck_v1-312 | IWM | orb60 | C | 15/45 | oa1m | d40-55t45 | skip_fomc_cpi | 62 | 19.40 | -6.60 | 0.44 | 0.30 | -436.34 | 1/8 |  |
| oa_crosscheck_v1-313 | IWM | orb60 | C | 10/30 | desk | d40-55t45 | skip_fomc_cpi | 62 | 16.10 | -5.05 | 0.34 | 0.18 | -335.06 | 0/8 |  |
| oa_crosscheck_v1-314 | IWM | orb60 | C | 10/30 | oa1m | d40-55t45 | skip_fomc_cpi | 62 | 16.10 | -7.45 | 0.29 | 0.18 | -481.80 | 0/8 |  |
| oa_crosscheck_v1-309 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | skip_fomc_cpi | 62 | 19.40 | -4.76 | 0.61 | 0.43 | -340.82 | 1/8 |  |
| oa_crosscheck_v1-310 | IWM | orb60 | C | 20/60 | oa1m | d40-55t45 | skip_fomc_cpi | 62 | 19.40 | -8.21 | 0.46 | 0.34 | -509.08 | 1/8 |  |
| oa_crosscheck_v1-307 | IWM | orb60 | C | 20/40 | desk | d40-55t45 | skip_fomc_cpi | 62 | 29.00 | -4.40 | 0.60 | 0.40 | -299.38 | 2/8 |  |
| oa_crosscheck_v1-308 | IWM | orb60 | C | 20/40 | oa1m | d40-55t45 | skip_fomc_cpi | 62 | 32.30 | -5.11 | 0.60 | 0.43 | -342.26 | 2/8 |  |
| oa_crosscheck_v1-305 | IWM | orb60 | C | 20/20 | desk | d40-55t45 | skip_fomc_cpi | 62 | 41.90 | -5.34 | 0.42 | 0.24 | -331.04 | 1/8 |  |
| oa_crosscheck_v1-306 | IWM | orb60 | C | 20/20 | oa1m | d40-55t45 | skip_fomc_cpi | 62 | 43.50 | -6.12 | 0.46 | 0.29 | -390.28 | 2/8 |  |
| oa_crosscheck_v1-237 | IWM | orb60 | C | 15/45 | desk | d40-55t45 | sma20_side | 36 | 11.10 | -7.84 | 0.28 | 0.18 | -328.67 | 1/8 |  |
| oa_crosscheck_v1-239 | IWM | orb60 | C | 15/45 | oa1m | d40-55t45 | sma20_side | 36 | 19.40 | -6.30 | 0.48 | 0.33 | -281.38 | 2/8 |  |
| oa_crosscheck_v1-241 | IWM | orb60 | C | 10/30 | desk | d40-55t45 | sma20_side | 36 | 11.10 | -6.17 | 0.24 | 0.13 | -251.67 | 1/8 |  |
| oa_crosscheck_v1-243 | IWM | orb60 | C | 10/30 | oa1m | d40-55t45 | sma20_side | 36 | 13.90 | -7.53 | 0.26 | 0.16 | -307.44 | 1/8 |  |
| oa_crosscheck_v1-233 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | sma20_side | 36 | 16.70 | -6.65 | 0.48 | 0.34 | -363.53 | 2/8 |  |
| oa_crosscheck_v1-235 | IWM | orb60 | C | 20/60 | oa1m | d40-55t45 | sma20_side | 36 | 13.90 | -9.92 | 0.36 | 0.27 | -474.44 | 2/8 |  |
| oa_crosscheck_v1-229 | IWM | orb60 | C | 20/40 | desk | d40-55t45 | sma20_side | 36 | 27.80 | -5.36 | 0.53 | 0.36 | -265.73 | 1/8 |  |
| oa_crosscheck_v1-231 | IWM | orb60 | C | 20/40 | oa1m | d40-55t45 | sma20_side | 36 | 27.80 | -6.44 | 0.52 | 0.37 | -333.64 | 2/8 |  |
| oa_crosscheck_v1-225 | IWM | orb60 | C | 20/20 | desk | d40-55t45 | sma20_side | 36 | 41.70 | -5.08 | 0.45 | 0.25 | -230.19 | 3/8 |  |
| oa_crosscheck_v1-227 | IWM | orb60 | C | 20/20 | oa1m | d40-55t45 | sma20_side | 36 | 33.30 | -8.65 | 0.32 | 0.20 | -346.06 | 1/8 |  |
| oa_crosscheck_v1-238 | IWM | orb60 | C | 15/45 | desk | d40-55t45 | sma20_side_1pct | 23 | 17.40 | -5.30 | 0.47 | 0.30 | -177.62 | 2/6 |  |
| oa_crosscheck_v1-240 | IWM | orb60 | C | 15/45 | oa1m | d40-55t45 | sma20_side_1pct | 23 | 26.10 | -2.68 | 0.75 | 0.51 | -130.44 | 2/6 |  |
| oa_crosscheck_v1-242 | IWM | orb60 | C | 10/30 | desk | d40-55t45 | sma20_side_1pct | 23 | 17.40 | -4.39 | 0.41 | 0.22 | -135.14 | 2/6 |  |
| oa_crosscheck_v1-244 | IWM | orb60 | C | 10/30 | oa1m | d40-55t45 | sma20_side_1pct | 23 | 21.70 | -5.07 | 0.45 | 0.27 | -153.96 | 2/6 |  |
| oa_crosscheck_v1-234 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | sma20_side_1pct | 23 | 21.70 | -4.36 | 0.64 | 0.45 | -179.45 | 2/6 |  |
| oa_crosscheck_v1-236 | IWM | orb60 | C | 20/60 | oa1m | d40-55t45 | sma20_side_1pct | 23 | 17.40 | -8.05 | 0.45 | 0.33 | -253.92 | 1/6 |  |
| oa_crosscheck_v1-230 | IWM | orb60 | C | 20/40 | desk | d40-55t45 | sma20_side_1pct | 23 | 34.80 | -3.01 | 0.71 | 0.48 | -113.73 | 3/6 |  |
| oa_crosscheck_v1-232 | IWM | orb60 | C | 20/40 | oa1m | d40-55t45 | sma20_side_1pct | 23 | 34.80 | -3.88 | 0.68 | 0.48 | -148.08 | 2/6 |  |
| oa_crosscheck_v1-226 | IWM | orb60 | C | 20/20 | desk | d40-55t45 | sma20_side_1pct | 23 | 47.80 | -3.15 | 0.61 | 0.34 | -113.73 | 3/6 |  |
| oa_crosscheck_v1-228 | IWM | orb60 | C | 20/20 | oa1m | d40-55t45 | sma20_side_1pct | 23 | 39.10 | -6.90 | 0.40 | 0.25 | -177.48 | 1/6 |  |
| oa_crosscheck_v1-417 | IWM | orb60 | C | 15/45 | desk | d40-55t45 | vixy_falling | 46 | 13.00 | -6.75 | 0.36 | 0.23 | -406.18 | 1/8 |  |
| oa_crosscheck_v1-419 | IWM | orb60 | C | 15/45 | oa1m | d40-55t45 | vixy_falling | 46 | 21.70 | -4.64 | 0.57 | 0.39 | -311.50 | 2/8 |  |
| oa_crosscheck_v1-421 | IWM | orb60 | C | 10/30 | desk | d40-55t45 | vixy_falling | 46 | 17.40 | -4.31 | 0.42 | 0.23 | -262.65 | 1/8 |  |
| oa_crosscheck_v1-423 | IWM | orb60 | C | 10/30 | oa1m | d40-55t45 | vixy_falling | 46 | 17.40 | -5.81 | 0.38 | 0.23 | -341.28 | 1/8 |  |
| oa_crosscheck_v1-413 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | vixy_falling | 46 | 19.60 | -4.35 | 0.64 | 0.45 | -330.04 | 2/8 |  |
| oa_crosscheck_v1-415 | IWM | orb60 | C | 20/60 | oa1m | d40-55t45 | vixy_falling | 46 | 21.70 | -6.45 | 0.55 | 0.41 | -365.54 | 2/8 |  |
| oa_crosscheck_v1-409 | IWM | orb60 | C | 20/40 | desk | d40-55t45 | vixy_falling | 46 | 30.40 | -3.65 | 0.66 | 0.44 | -256.85 | 2/8 |  |
| oa_crosscheck_v1-411 | IWM | orb60 | C | 20/40 | oa1m | d40-55t45 | vixy_falling | 46 | 34.80 | -3.15 | 0.73 | 0.52 | -242.90 | 3/8 |  |
| oa_crosscheck_v1-405 | IWM | orb60 | C | 20/20 | desk | d40-55t45 | vixy_falling | 46 | 43.50 | -4.90 | 0.46 | 0.26 | -263.82 | 1/8 |  |
| oa_crosscheck_v1-407 | IWM | orb60 | C | 20/20 | oa1m | d40-55t45 | vixy_falling | 46 | 47.80 | -4.19 | 0.58 | 0.36 | -241.92 | 2/8 |  |
| oa_crosscheck_v1-067 | IWM | orb60 | P | 15/45 | desk | d40-55t45 | - | 89 | 22.50 | -4.10 | 0.64 | 0.41 | -374.32 | 1/8 |  |
| oa_crosscheck_v1-068 | IWM | orb60 | P | 15/45 | oa1m | d40-55t45 | - | 89 | 23.60 | -5.23 | 0.62 | 0.43 | -547.48 | 3/8 |  |
| oa_crosscheck_v1-069 | IWM | orb60 | P | 10/30 | desk | d40-55t45 | - | 89 | 19.10 | -4.93 | 0.42 | 0.22 | -466.00 | 2/8 |  |
| oa_crosscheck_v1-070 | IWM | orb60 | P | 10/30 | oa1m | d40-55t45 | - | 89 | 21.30 | -5.58 | 0.49 | 0.30 | -517.62 | 1/8 |  |
| oa_crosscheck_v1-065 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | - | 89 | 20.20 | -6.60 | 0.55 | 0.39 | -619.29 | 3/8 |  |
| oa_crosscheck_v1-066 | IWM | orb60 | P | 20/60 | oa1m | d40-55t45 | - | 89 | 23.60 | -4.77 | 0.70 | 0.52 | -645.44 | 4/8 |  |
| oa_crosscheck_v1-063 | IWM | orb60 | P | 20/40 | desk | d40-55t45 | - | 89 | 30.30 | -4.75 | 0.63 | 0.43 | -423.12 | 2/8 |  |
| oa_crosscheck_v1-064 | IWM | orb60 | P | 20/40 | oa1m | d40-55t45 | - | 89 | 30.30 | -5.17 | 0.65 | 0.47 | -563.50 | 3/8 |  |
| oa_crosscheck_v1-071 | IWM | orb60 | P | 50/100 | desk | d40-55t45 | - | 89 | 31.50 | -7.02 | 0.75 | 0.65 | -963.51 | 2/8 |  |
| oa_crosscheck_v1-072 | IWM | orb60 | P | 50/100 | oa1m | d40-55t45 | - | 89 | 31.50 | -6.75 | 0.77 | 0.67 | -1093.78 | 2/8 |  |
| oa_crosscheck_v1-083 | IWM | orb60 | P | 50/100 | desk | d45-60t50 | - | 88 | 31.80 | -7.19 | 0.78 | 0.67 | -1093.90 | 3/8 |  |
| oa_crosscheck_v1-084 | IWM | orb60 | P | 50/100 | oa1m | d45-60t50 | - | 88 | 31.80 | -6.58 | 0.81 | 0.70 | -1145.60 | 3/8 |  |
| oa_crosscheck_v1-061 | IWM | orb60 | P | 20/20 | desk | d40-55t45 | - | 89 | 43.80 | -5.14 | 0.50 | 0.28 | -461.07 | 0/8 |  |
| oa_crosscheck_v1-062 | IWM | orb60 | P | 20/20 | oa1m | d40-55t45 | - | 89 | 43.80 | -3.86 | 0.67 | 0.43 | -456.04 | 3/8 |  |
| oa_crosscheck_v1-438 | IWM | orb60 | P | 15/45 | desk | d40-55t45 | gap_side_075 | 23 | 21.70 | -4.05 | 0.60 | 0.38 | -108.92 | 4/8 |  |
| oa_crosscheck_v1-440 | IWM | orb60 | P | 15/45 | oa1m | d40-55t45 | gap_side_075 | 23 | 17.40 | -9.35 | 0.31 | 0.21 | -235.72 | 2/8 |  |
| oa_crosscheck_v1-442 | IWM | orb60 | P | 10/30 | desk | d40-55t45 | gap_side_075 | 23 | 17.40 | -4.64 | 0.41 | 0.22 | -106.70 | 4/8 |  |
| oa_crosscheck_v1-444 | IWM | orb60 | P | 10/30 | oa1m | d40-55t45 | gap_side_075 | 23 | 21.70 | -3.98 | 0.53 | 0.30 | -96.62 | 3/8 |  |
| oa_crosscheck_v1-434 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | gap_side_075 | 23 | 17.40 | -8.80 | 0.38 | 0.27 | -224.98 | 2/8 |  |
| oa_crosscheck_v1-436 | IWM | orb60 | P | 20/60 | oa1m | d40-55t45 | gap_side_075 | 23 | 13.00 | -13.40 | 0.25 | 0.18 | -308.22 | 1/8 |  |
| oa_crosscheck_v1-430 | IWM | orb60 | P | 20/40 | desk | d40-55t45 | gap_side_075 | 23 | 26.10 | -6.25 | 0.49 | 0.33 | -154.20 | 2/8 |  |
| oa_crosscheck_v1-432 | IWM | orb60 | P | 20/40 | oa1m | d40-55t45 | gap_side_075 | 23 | 21.70 | -10.38 | 0.36 | 0.26 | -289.20 | 1/8 |  |
| oa_crosscheck_v1-426 | IWM | orb60 | P | 20/20 | desk | d40-55t45 | gap_side_075 | 23 | 34.80 | -7.81 | 0.30 | 0.17 | -179.56 | 2/8 |  |
| oa_crosscheck_v1-428 | IWM | orb60 | P | 20/20 | oa1m | d40-55t45 | gap_side_075 | 23 | 34.80 | -7.82 | 0.40 | 0.26 | -194.16 | 2/8 |  |
| oa_crosscheck_v1-321 | IWM | orb60 | P | 15/45 | desk | d40-55t45 | skip_fomc_cpi | 79 | 24.10 | -3.09 | 0.71 | 0.46 | -272.99 | 1/8 |  |
| oa_crosscheck_v1-322 | IWM | orb60 | P | 15/45 | oa1m | d40-55t45 | skip_fomc_cpi | 79 | 25.30 | -4.14 | 0.69 | 0.49 | -453.88 | 3/8 |  |
| oa_crosscheck_v1-323 | IWM | orb60 | P | 10/30 | desk | d40-55t45 | skip_fomc_cpi | 79 | 20.30 | -4.23 | 0.47 | 0.25 | -361.86 | 2/8 |  |
| oa_crosscheck_v1-324 | IWM | orb60 | P | 10/30 | oa1m | d40-55t45 | skip_fomc_cpi | 79 | 24.10 | -4.36 | 0.58 | 0.36 | -365.36 | 2/8 |  |
| oa_crosscheck_v1-319 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | skip_fomc_cpi | 79 | 22.80 | -4.67 | 0.66 | 0.47 | -484.08 | 3/8 |  |
| oa_crosscheck_v1-320 | IWM | orb60 | P | 20/60 | oa1m | d40-55t45 | skip_fomc_cpi | 79 | 26.60 | -2.33 | 0.85 | 0.63 | -499.40 | 4/8 |  |
| oa_crosscheck_v1-317 | IWM | orb60 | P | 20/40 | desk | d40-55t45 | skip_fomc_cpi | 79 | 32.90 | -3.18 | 0.73 | 0.50 | -302.46 | 2/8 |  |
| oa_crosscheck_v1-318 | IWM | orb60 | P | 20/40 | oa1m | d40-55t45 | skip_fomc_cpi | 79 | 32.90 | -3.43 | 0.76 | 0.54 | -432.28 | 4/8 |  |
| oa_crosscheck_v1-315 | IWM | orb60 | P | 20/20 | desk | d40-55t45 | skip_fomc_cpi | 79 | 46.80 | -3.66 | 0.60 | 0.34 | -292.64 | 1/8 |  |
| oa_crosscheck_v1-316 | IWM | orb60 | P | 20/20 | oa1m | d40-55t45 | skip_fomc_cpi | 79 | 46.80 | -2.02 | 0.81 | 0.53 | -271.44 | 3/8 |  |
| oa_crosscheck_v1-257 | IWM | orb60 | P | 15/45 | desk | d40-55t45 | sma20_side | 36 | 27.80 | -1.07 | 0.91 | 0.60 | -176.09 | 1/5 |  |
| oa_crosscheck_v1-259 | IWM | orb60 | P | 15/45 | oa1m | d40-55t45 | sma20_side | 36 | 30.60 | -1.69 | 0.89 | 0.63 | -299.36 | 1/5 |  |
| oa_crosscheck_v1-261 | IWM | orb60 | P | 10/30 | desk | d40-55t45 | sma20_side | 36 | 22.20 | -4.32 | 0.52 | 0.28 | -168.85 | 1/5 |  |
| oa_crosscheck_v1-263 | IWM | orb60 | P | 10/30 | oa1m | d40-55t45 | sma20_side | 36 | 25.00 | -5.28 | 0.57 | 0.35 | -202.44 | 1/5 |  |
| oa_crosscheck_v1-253 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | sma20_side | 36 | 22.20 | -4.53 | 0.72 | 0.52 | -370.94 | 2/5 |  |
| oa_crosscheck_v1-255 | IWM | orb60 | P | 20/60 | oa1m | d40-55t45 | sma20_side | 36 | 25.00 | -4.27 | 0.77 | 0.58 | -432.78 | 2/5 |  |
| oa_crosscheck_v1-249 | IWM | orb60 | P | 20/40 | desk | d40-55t45 | sma20_side | 36 | 36.10 | -1.38 | 0.90 | 0.61 | -189.73 | 1/5 |  |
| oa_crosscheck_v1-251 | IWM | orb60 | P | 20/40 | oa1m | d40-55t45 | sma20_side | 36 | 33.30 | -5.39 | 0.68 | 0.49 | -373.84 | 2/5 |  |
| oa_crosscheck_v1-245 | IWM | orb60 | P | 20/20 | desk | d40-55t45 | sma20_side | 36 | 50.00 | -2.70 | 0.73 | 0.41 | -139.42 | 1/5 |  |
| oa_crosscheck_v1-247 | IWM | orb60 | P | 20/20 | oa1m | d40-55t45 | sma20_side | 36 | 52.80 | -1.98 | 0.82 | 0.52 | -120.90 | 3/5 |  |
| oa_crosscheck_v1-258 | IWM | orb60 | P | 15/45 | desk | d40-55t45 | sma20_side_1pct | 27 | 29.60 | 0.84 | 1.07 | 0.68 | -117.39 | 1/5 |  |
| oa_crosscheck_v1-260 | IWM | orb60 | P | 15/45 | oa1m | d40-55t45 | sma20_side_1pct | 27 | 33.30 | 0.75 | 1.05 | 0.73 | -227.16 | 2/5 |  |
| oa_crosscheck_v1-262 | IWM | orb60 | P | 10/30 | desk | d40-55t45 | sma20_side_1pct | 27 | 18.50 | -5.66 | 0.44 | 0.23 | -155.15 | 0/5 |  |
| oa_crosscheck_v1-264 | IWM | orb60 | P | 10/30 | oa1m | d40-55t45 | sma20_side_1pct | 27 | 22.20 | -4.84 | 0.59 | 0.35 | -130.64 | 0/5 |  |
| oa_crosscheck_v1-254 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | sma20_side_1pct | 27 | 22.20 | -3.03 | 0.81 | 0.57 | -295.04 | 1/5 |  |
| oa_crosscheck_v1-256 | IWM | orb60 | P | 20/60 | oa1m | d40-55t45 | sma20_side_1pct | 27 | 25.90 | -2.55 | 0.86 | 0.64 | -361.92 | 2/5 |  |
| oa_crosscheck_v1-250 | IWM | orb60 | P | 20/40 | desk | d40-55t45 | sma20_side_1pct | 27 | 37.00 | -0.27 | 0.98 | 0.66 | -123.58 | 1/5 |  |
| oa_crosscheck_v1-252 | IWM | orb60 | P | 20/40 | oa1m | d40-55t45 | sma20_side_1pct | 27 | 33.30 | -5.42 | 0.69 | 0.49 | -297.72 | 2/5 |  |
| oa_crosscheck_v1-246 | IWM | orb60 | P | 20/20 | desk | d40-55t45 | sma20_side_1pct | 27 | 44.40 | -4.82 | 0.59 | 0.33 | -130.40 | 0/5 |  |
| oa_crosscheck_v1-248 | IWM | orb60 | P | 20/20 | oa1m | d40-55t45 | sma20_side_1pct | 27 | 48.10 | -4.19 | 0.69 | 0.44 | -135.42 | 1/5 |  |
| oa_crosscheck_v1-437 | IWM | orb60 | P | 15/45 | desk | d40-55t45 | vixy_falling | 31 | 22.60 | -1.89 | 0.81 | 0.52 | -156.14 | 2/7 |  |
| oa_crosscheck_v1-439 | IWM | orb60 | P | 15/45 | oa1m | d40-55t45 | vixy_falling | 31 | 22.60 | -4.52 | 0.67 | 0.47 | -165.84 | 1/7 |  |
| oa_crosscheck_v1-441 | IWM | orb60 | P | 10/30 | desk | d40-55t45 | vixy_falling | 31 | 19.40 | -3.91 | 0.51 | 0.28 | -128.07 | 3/7 |  |
| oa_crosscheck_v1-443 | IWM | orb60 | P | 10/30 | oa1m | d40-55t45 | vixy_falling | 31 | 19.40 | -6.57 | 0.40 | 0.24 | -209.32 | 1/7 |  |
| oa_crosscheck_v1-433 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | vixy_falling | 31 | 22.60 | -3.41 | 0.74 | 0.52 | -169.91 | 2/7 |  |
| oa_crosscheck_v1-435 | IWM | orb60 | P | 20/60 | oa1m | d40-55t45 | vixy_falling | 31 | 22.60 | -5.12 | 0.68 | 0.51 | -202.90 | 2/7 |  |
| oa_crosscheck_v1-429 | IWM | orb60 | P | 20/40 | desk | d40-55t45 | vixy_falling | 31 | 29.00 | -3.22 | 0.73 | 0.49 | -145.59 | 2/7 |  |
| oa_crosscheck_v1-431 | IWM | orb60 | P | 20/40 | oa1m | d40-55t45 | vixy_falling | 31 | 25.80 | -7.17 | 0.53 | 0.38 | -237.20 | 0/7 |  |
| oa_crosscheck_v1-425 | IWM | orb60 | P | 20/20 | desk | d40-55t45 | vixy_falling | 31 | 45.20 | -4.35 | 0.55 | 0.31 | -162.14 | 3/7 |  |
| oa_crosscheck_v1-427 | IWM | orb60 | P | 20/20 | oa1m | d40-55t45 | vixy_falling | 31 | 35.50 | -7.62 | 0.42 | 0.27 | -236.10 | 1/7 |  |
| oa_crosscheck_v1-138 | IWM | orb15 | C | 15/45 | desk | d40-55t45 | - | 141 | 27.00 | -1.26 | 0.88 | 0.56 | -549.56 | 3/8 |  |
| oa_crosscheck_v1-139 | IWM | orb15 | C | 10/30 | desk | d40-55t45 | - | 141 | 32.60 | -0.20 | 0.97 | 0.52 | -233.73 | 4/8 |  |
| oa_crosscheck_v1-137 | IWM | orb15 | C | 20/60 | desk | d40-55t45 | - | 141 | 21.30 | -4.47 | 0.70 | 0.49 | -882.86 | 2/8 |  |
| oa_crosscheck_v1-136 | IWM | orb15 | C | 20/40 | desk | d40-55t45 | - | 141 | 32.60 | -3.03 | 0.76 | 0.51 | -666.47 | 3/8 |  |
| oa_crosscheck_v1-135 | IWM | orb15 | C | 20/20 | desk | d40-55t45 | - | 141 | 51.80 | -2.19 | 0.76 | 0.43 | -447.20 | 3/8 |  |
| oa_crosscheck_v1-143 | IWM | orb15 | P | 15/45 | desk | d40-55t45 | - | 155 | 27.10 | -2.66 | 0.77 | 0.49 | -513.82 | 2/8 |  |
| oa_crosscheck_v1-144 | IWM | orb15 | P | 10/30 | desk | d40-55t45 | - | 155 | 25.20 | -3.07 | 0.64 | 0.34 | -508.85 | 0/8 |  |
| oa_crosscheck_v1-142 | IWM | orb15 | P | 20/60 | desk | d40-55t45 | - | 155 | 23.90 | -4.36 | 0.71 | 0.50 | -815.48 | 2/8 |  |
| oa_crosscheck_v1-141 | IWM | orb15 | P | 20/40 | desk | d40-55t45 | - | 155 | 32.30 | -3.61 | 0.73 | 0.49 | -621.71 | 1/8 |  |
| oa_crosscheck_v1-140 | IWM | orb15 | P | 20/20 | desk | d40-55t45 | - | 155 | 52.30 | -2.07 | 0.78 | 0.44 | -413.15 | 3/8 |  |
| oa_crosscheck_v1-128 | IWM | orb30 | C | 15/45 | desk | d40-55t45 | - | 112 | 25.90 | -2.42 | 0.77 | 0.49 | -412.24 | 3/8 |  |
| oa_crosscheck_v1-129 | IWM | orb30 | C | 10/30 | desk | d40-55t45 | - | 112 | 27.70 | -2.06 | 0.73 | 0.39 | -329.51 | 3/8 |  |
| oa_crosscheck_v1-127 | IWM | orb30 | C | 20/60 | desk | d40-55t45 | - | 112 | 23.20 | -3.62 | 0.73 | 0.52 | -585.82 | 3/8 |  |
| oa_crosscheck_v1-126 | IWM | orb30 | C | 20/40 | desk | d40-55t45 | - | 112 | 34.80 | -2.64 | 0.78 | 0.52 | -446.79 | 3/8 |  |
| oa_crosscheck_v1-125 | IWM | orb30 | C | 20/20 | desk | d40-55t45 | - | 112 | 52.70 | -2.92 | 0.67 | 0.38 | -428.65 | 3/8 |  |
| oa_crosscheck_v1-133 | IWM | orb30 | P | 15/45 | desk | d40-55t45 | - | 128 | 27.30 | -2.28 | 0.79 | 0.51 | -333.97 | 2/8 |  |
| oa_crosscheck_v1-134 | IWM | orb30 | P | 10/30 | desk | d40-55t45 | - | 128 | 21.90 | -3.80 | 0.56 | 0.30 | -485.96 | 0/8 |  |
| oa_crosscheck_v1-132 | IWM | orb30 | P | 20/60 | desk | d40-55t45 | - | 128 | 27.30 | -2.11 | 0.85 | 0.60 | -402.19 | 3/8 |  |
| oa_crosscheck_v1-131 | IWM | orb30 | P | 20/40 | desk | d40-55t45 | - | 128 | 32.00 | -3.81 | 0.71 | 0.48 | -488.20 | 1/8 |  |
| oa_crosscheck_v1-130 | IWM | orb30 | P | 20/20 | desk | d40-55t45 | - | 128 | 46.10 | -4.16 | 0.59 | 0.34 | -609.30 | 1/8 |  |


## Robustness on the top 5 runs

### oa_crosscheck_v1-080: QQQ orb60 P fixed 50/100 oa1m d45-60t50

Trades 110, win 36%, avg win 191.42, avg loss -93.48, expectancy **10.12** (2x slippage 0.75), PF 1.17 (2x 1.01), max DD -1120.28, % of peak kept 0.13, planned R:R - vs actual 0.09, expectancy CI95 [-15.81, 37.73], deflated Sharpe 0.000 (N=922).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [x] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 6 of 8 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 39 | 654.38 | 16.78 | 1.31 |
| 2025 (Jan 01-Oct 29) | 71 | 458.84 | 6.46 | 1.10 |
| 2m: Aug 2024-Sep 2024 | 22 | 253.80 | 11.54 | 1.19 |
| 2m: Oct 2024-Nov 2024 | 12 | -24.28 | -2.02 | 0.96 |
| 2m: Dec 2024-Jan 2025 | 11 | 126.98 | 11.54 | 1.20 |
| 2m: Feb 2025-Mar 2025 | 13 | 72.72 | 5.59 | 1.07 |
| 2m: Apr 2025-May 2025 | 16 | 692.90 | 43.31 | 1.58 |
| 2m: Jun 2025-Jul 2025 | 12 | 38.42 | 3.20 | 1.07 |
| 2m: Aug 2025-Sep 2025 | 15 | -227.76 | -15.18 | 0.71 |
| 2m: Oct 2025-Nov 2025 | 9 | 180.44 | 20.05 | 1.46 |


Sides: calls n=0 exp - PF -; puts n=110 exp 10.12 PF 1.17
Symbols: QQQ n=110 exp 10.12 PF 1.17
Without the best 5 trades: net -689.10, expectancy -6.56.
One-step nudges: entry=orb30 n=160 PF 0.86 exp -9.35; allout=15:50 n=110 PF 1.16 exp 9.49; fixed_stop=0.4 n=110 PF 1.18 exp 9.33; fixed_stop=0.6 n=110 PF 1.13 exp 8.37; fixed_target=0.9 n=110 PF 1.04 exp 2.24; fixed_target=1.25 n=110 PF 0.85 exp -10.10
Matched random entries (5 paths): expectancy 26.31, 9.58, 43.54, 10.03, 8.43; the run beats 60% of paths.
Exit reasons: {'FIXED STOP': 69, 'FIXED TARGET': 39, 'ALL OUT': 2}.
Median option MFE 0.640, MAE -0.515; median stock MFE $1.830; median distance from the stock's price at the option's peak to the nearest level $0.145; median minutes held 62.5.
Skipped signals: no contract with BS-EST |delta| in 0.45-0.60 2.

### oa_crosscheck_v1-024: SPY orb60 P fixed 50/100 oa1m d40-55t45

Trades 124, win 37%, avg win 149.01, avg loss -74.59, expectancy **8.36** (2x slippage 0.96), PF 1.18 (2x 1.02), max DD -1302.98, % of peak kept 0.18, planned R:R - vs actual 0.10, expectancy CI95 [-11.71, 30.65], deflated Sharpe 0.000 (N=922).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [x] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 4 of 8 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 43 | 742.52 | 17.27 | 1.45 |
| 2025 (Jan 01-Oct 29) | 81 | 293.50 | 3.62 | 1.07 |
| 2m: Aug 2024-Sep 2024 | 22 | 507.20 | 23.05 | 1.52 |
| 2m: Oct 2024-Nov 2024 | 14 | 198.34 | 14.17 | 1.46 |
| 2m: Dec 2024-Jan 2025 | 14 | -274.12 | -19.58 | 0.59 |
| 2m: Feb 2025-Mar 2025 | 14 | -186.92 | -13.35 | 0.80 |
| 2m: Apr 2025-May 2025 | 18 | 856.36 | 47.58 | 1.73 |
| 2m: Jun 2025-Jul 2025 | 16 | -337.52 | -21.10 | 0.53 |
| 2m: Aug 2025-Sep 2025 | 17 | -210.92 | -12.41 | 0.71 |
| 2m: Oct 2025-Nov 2025 | 9 | 483.60 | 53.73 | 3.33 |


Sides: calls n=0 exp - PF -; puts n=124 exp 8.36 PF 1.18
Symbols: SPY n=124 exp 8.36 PF 1.18
Without the best 5 trades: net -643.78, expectancy -5.41.
One-step nudges: entry=orb30 n=170 PF 1.00 exp 0.21; allout=15:50 n=124 PF 1.17 exp 7.77; fixed_stop=0.4 n=124 PF 1.21 exp 8.88; fixed_stop=0.6 n=124 PF 1.17 exp 8.74; fixed_target=0.9 n=124 PF 1.21 exp 9.45; fixed_target=1.25 n=124 PF 1.00 exp -0.07
Matched random entries (5 paths): expectancy 39.61, 18.20, 16.56, 20.36, 10.71; the run beats 0% of paths.
Exit reasons: {'FIXED STOP': 75, 'FIXED TARGET': 44, 'ALL OUT': 5}.
Median option MFE 0.541, MAE -0.513; median stock MFE $1.342; median distance from the stock's price at the option's peak to the nearest level $0.109; median minutes held 58.0.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 4.

### oa_crosscheck_v1-023: SPY orb60 P fixed 50/100 desk d40-55t45

Trades 124, win 39%, avg win 130.44, avg loss -72.37, expectancy **6.14** (2x slippage -1.30), PF 1.14 (2x 0.97), max DD -1158.06, % of peak kept 0.16, planned R:R - vs actual 0.08, expectancy CI95 [-11.87, 26.42], deflated Sharpe 0.000 (N=922).

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
| Aug-Dec 2024 | 43 | 704.32 | 16.38 | 1.47 |
| 2025 (Jan 01-Oct 29) | 81 | 56.81 | 0.70 | 1.01 |
| 2m: Aug 2024-Sep 2024 | 22 | 556.54 | 25.30 | 1.65 |
| 2m: Oct 2024-Nov 2024 | 14 | 113.89 | 8.14 | 1.26 |
| 2m: Dec 2024-Jan 2025 | 14 | -260.68 | -18.62 | 0.59 |
| 2m: Feb 2025-Mar 2025 | 14 | -221.20 | -15.80 | 0.75 |
| 2m: Apr 2025-May 2025 | 18 | 701.57 | 38.98 | 1.61 |
| 2m: Jun 2025-Jul 2025 | 16 | -203.83 | -12.74 | 0.68 |
| 2m: Aug 2025-Sep 2025 | 17 | -226.35 | -13.31 | 0.68 |
| 2m: Oct 2025-Nov 2025 | 9 | 301.19 | 33.47 | 2.45 |


Sides: calls n=0 exp - PF -; puts n=124 exp 6.14 PF 1.14
Symbols: SPY n=124 exp 6.14 PF 1.14
Without the best 5 trades: net -742.30, expectancy -6.24.
One-step nudges: entry=orb30 n=170 PF 1.06 exp 2.80; allout=15:50 n=124 PF 1.12 exp 5.53; fixed_stop=0.4 n=124 PF 1.06 exp 2.43; fixed_stop=0.6 n=124 PF 1.10 exp 5.05; fixed_target=0.9 n=124 PF 1.23 exp 9.29; fixed_target=1.25 n=124 PF 0.97 exp -1.42
Matched random entries (5 paths): expectancy 33.24, 14.63, 12.50, 18.74, 5.29; the run beats 20% of paths.
Exit reasons: {'FIXED STOP': 75, 'FIXED TARGET': 47, 'ALL OUT': 2}.
Median option MFE 0.502, MAE -0.505; median stock MFE $1.275; median distance from the stock's price at the option's peak to the nearest level $0.100; median minutes held 52.0.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 4.

### oa_crosscheck_v1-048: QQQ orb60 P fixed 50/100 oa1m d40-55t45

Trades 111, win 34%, avg win 168.12, avg loss -79.44, expectancy **5.31** (2x slippage -2.68), PF 1.10 (2x 0.95), max DD -1054.24, % of peak kept 0.09, planned R:R - vs actual 0.02, expectancy CI95 [-16.0, 29.66], deflated Sharpe 0.000 (N=922).

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
| Aug-Dec 2024 | 39 | 272.86 | 7.00 | 1.14 |
| 2025 (Jan 01-Oct 29) | 72 | 316.72 | 4.40 | 1.08 |
| 2m: Aug 2024-Sep 2024 | 22 | 67.60 | 3.07 | 1.05 |
| 2m: Oct 2024-Nov 2024 | 12 | 35.26 | 2.94 | 1.07 |
| 2m: Dec 2024-Jan 2025 | 11 | -87.68 | -7.97 | 0.84 |
| 2m: Feb 2025-Mar 2025 | 13 | -107.42 | -8.26 | 0.88 |
| 2m: Apr 2025-May 2025 | 16 | 746.92 | 46.68 | 1.73 |
| 2m: Jun 2025-Jul 2025 | 13 | -45.10 | -3.47 | 0.92 |
| 2m: Aug 2025-Sep 2025 | 15 | -211.04 | -14.07 | 0.70 |
| 2m: Oct 2025-Nov 2025 | 9 | 191.04 | 21.23 | 1.55 |


Sides: calls n=0 exp - PF -; puts n=111 exp 5.31 PF 1.10
Symbols: QQQ n=111 exp 5.31 PF 1.10
Without the best 5 trades: net -1080.88, expectancy -10.20.
One-step nudges: entry=orb30 n=159 PF 0.85 exp -8.75; allout=15:50 n=111 PF 1.09 exp 4.73; fixed_stop=0.4 n=111 PF 1.12 exp 5.57; fixed_stop=0.6 n=111 PF 1.07 exp 4.37; fixed_target=0.9 n=111 PF 1.02 exp 1.03; fixed_target=1.25 n=111 PF 0.96 exp -2.21
Matched random entries (5 paths): expectancy 25.28, 3.64, 38.58, 11.12, 9.31; the run beats 20% of paths.
Exit reasons: {'FIXED STOP': 72, 'FIXED TARGET': 37, 'ALL OUT': 2}.
Median option MFE 0.627, MAE -0.516; median stock MFE $1.620; median distance from the stock's price at the option's peak to the nearest level $0.130; median minutes held 57.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 1.

### oa_crosscheck_v1-047: QQQ orb60 P fixed 50/100 desk d40-55t45

Trades 111, win 36%, avg win 147.74, avg loss -75.31, expectancy **5.07** (2x slippage -2.96), PF 1.10 (2x 0.94), max DD -932.81, % of peak kept 0.09, planned R:R - vs actual 0.01, expectancy CI95 [-15.11, 26.98], deflated Sharpe 0.000 (N=922).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [x] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 3 of 8 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 39 | 201.36 | 5.16 | 1.11 |
| 2025 (Jan 01-Oct 29) | 72 | 361.12 | 5.02 | 1.10 |
| 2m: Aug 2024-Sep 2024 | 22 | 69.43 | 3.16 | 1.06 |
| 2m: Oct 2024-Nov 2024 | 12 | -25.63 | -2.14 | 0.95 |
| 2m: Dec 2024-Jan 2025 | 11 | 104.28 | 9.48 | 1.23 |
| 2m: Feb 2025-Mar 2025 | 13 | -69.58 | -5.35 | 0.92 |
| 2m: Apr 2025-May 2025 | 16 | 839.53 | 52.47 | 1.97 |
| 2m: Jun 2025-Jul 2025 | 13 | -97.05 | -7.47 | 0.82 |
| 2m: Aug 2025-Sep 2025 | 15 | -256.52 | -17.10 | 0.63 |
| 2m: Oct 2025-Nov 2025 | 9 | -1.98 | -0.22 | 0.99 |


Sides: calls n=0 exp - PF -; puts n=111 exp 5.07 PF 1.10
Symbols: QQQ n=111 exp 5.07 PF 1.10
Without the best 5 trades: net -878.39, expectancy -8.29.
One-step nudges: entry=orb30 n=159 PF 0.86 exp -7.63; allout=15:50 n=111 PF 1.09 exp 4.52; fixed_stop=0.4 n=111 PF 0.90 exp -4.48; fixed_stop=0.6 n=111 PF 1.04 exp 2.10; fixed_target=0.9 n=111 PF 0.99 exp -0.46; fixed_target=1.25 n=111 PF 0.96 exp -1.99
Matched random entries (5 paths): expectancy 27.05, 1.61, 29.76, 7.34, 7.10; the run beats 20% of paths.
Exit reasons: {'FIXED STOP': 70, 'FIXED TARGET': 39, 'ALL OUT': 2}.
Median option MFE 0.627, MAE -0.503; median stock MFE $1.560; median distance from the stock's price at the option's peak to the nearest level $0.120; median minutes held 42.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 1.

## Filters vs random day-skips (every filtered run with its unfiltered twin)

| run | config | twin | days skipped | filtered exp | random-skip exp | p |
|---|---|---|---|---|---|---|
| oa_crosscheck_v1-145 | SPY orb60 C fixed 20/20 desk d40-55t45 sma20_side | oa_crosscheck_v1-001 | 43 | -4.72 | -5.48 | 0.30 |
| oa_crosscheck_v1-146 | SPY orb60 C fixed 20/20 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-001 | 72 | -3.87 | -5.50 | 0.20 |
| oa_crosscheck_v1-147 | SPY orb60 C fixed 20/20 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-002 | 43 | -4.14 | -4.53 | 0.41 |
| oa_crosscheck_v1-148 | SPY orb60 C fixed 20/20 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-002 | 72 | -3.35 | -4.56 | 0.31 |
| oa_crosscheck_v1-149 | SPY orb60 C fixed 20/40 desk d40-55t45 sma20_side | oa_crosscheck_v1-003 | 43 | -8.28 | -8.30 | 0.50 |
| oa_crosscheck_v1-150 | SPY orb60 C fixed 20/40 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-003 | 72 | -8.90 | -8.25 | 0.59 |
| oa_crosscheck_v1-151 | SPY orb60 C fixed 20/40 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-004 | 43 | -8.54 | -9.75 | 0.29 |
| oa_crosscheck_v1-152 | SPY orb60 C fixed 20/40 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-004 | 72 | -8.97 | -9.82 | 0.39 |
| oa_crosscheck_v1-153 | SPY orb60 C fixed 20/60 desk d40-55t45 sma20_side | oa_crosscheck_v1-005 | 43 | -11.21 | -11.39 | 0.50 |
| oa_crosscheck_v1-154 | SPY orb60 C fixed 20/60 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-005 | 72 | -12.84 | -11.33 | 0.67 |
| oa_crosscheck_v1-155 | SPY orb60 C fixed 20/60 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-006 | 43 | -11.26 | -9.91 | 0.70 |
| oa_crosscheck_v1-156 | SPY orb60 C fixed 20/60 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-006 | 72 | -13.19 | -9.88 | 0.78 |
| oa_crosscheck_v1-157 | SPY orb60 C fixed 15/45 desk d40-55t45 sma20_side | oa_crosscheck_v1-007 | 43 | -8.86 | -10.01 | 0.21 |
| oa_crosscheck_v1-158 | SPY orb60 C fixed 15/45 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-007 | 72 | -8.44 | -9.99 | 0.26 |
| oa_crosscheck_v1-159 | SPY orb60 C fixed 15/45 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-008 | 43 | -7.80 | -10.58 | 0.07 |
| oa_crosscheck_v1-160 | SPY orb60 C fixed 15/45 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-008 | 72 | -6.44 | -10.57 | 0.10 |
| oa_crosscheck_v1-161 | SPY orb60 C fixed 10/30 desk d40-55t45 sma20_side | oa_crosscheck_v1-009 | 43 | -6.80 | -7.38 | 0.28 |
| oa_crosscheck_v1-162 | SPY orb60 C fixed 10/30 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-009 | 72 | -6.67 | -7.40 | 0.34 |
| oa_crosscheck_v1-163 | SPY orb60 C fixed 10/30 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-010 | 43 | -5.36 | -6.87 | 0.15 |
| oa_crosscheck_v1-164 | SPY orb60 C fixed 10/30 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-010 | 72 | -5.44 | -6.98 | 0.24 |
| oa_crosscheck_v1-165 | SPY orb60 P fixed 20/20 desk d40-55t45 sma20_side | oa_crosscheck_v1-013 | 93 | -2.20 | -4.85 | 0.30 |
| oa_crosscheck_v1-166 | SPY orb60 P fixed 20/20 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-013 | 100 | -0.50 | -5.20 | 0.18 |
| oa_crosscheck_v1-167 | SPY orb60 P fixed 20/20 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-014 | 93 | -1.17 | -3.44 | 0.36 |
| oa_crosscheck_v1-168 | SPY orb60 P fixed 20/20 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-014 | 100 | -1.56 | -3.94 | 0.37 |
| oa_crosscheck_v1-169 | SPY orb60 P fixed 20/40 desk d40-55t45 sma20_side | oa_crosscheck_v1-015 | 93 | -1.87 | -6.22 | 0.28 |
| oa_crosscheck_v1-170 | SPY orb60 P fixed 20/40 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-015 | 100 | 0.44 | -6.84 | 0.16 |
| oa_crosscheck_v1-171 | SPY orb60 P fixed 20/40 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-016 | 93 | -11.76 | -8.00 | 0.69 |
| oa_crosscheck_v1-172 | SPY orb60 P fixed 20/40 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-016 | 100 | -15.57 | -9.18 | 0.74 |
| oa_crosscheck_v1-173 | SPY orb60 P fixed 20/60 desk d40-55t45 sma20_side | oa_crosscheck_v1-017 | 93 | -0.02 | -7.41 | 0.14 |
| oa_crosscheck_v1-174 | SPY orb60 P fixed 20/60 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-017 | 100 | 0.47 | -8.34 | 0.17 |
| oa_crosscheck_v1-175 | SPY orb60 P fixed 20/60 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-018 | 93 | -2.22 | -8.35 | 0.23 |
| oa_crosscheck_v1-176 | SPY orb60 P fixed 20/60 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-018 | 100 | -2.91 | -9.30 | 0.27 |
| oa_crosscheck_v1-177 | SPY orb60 P fixed 15/45 desk d40-55t45 sma20_side | oa_crosscheck_v1-019 | 93 | -10.11 | -7.52 | 0.69 |
| oa_crosscheck_v1-178 | SPY orb60 P fixed 15/45 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-019 | 100 | -12.37 | -8.13 | 0.74 |
| oa_crosscheck_v1-179 | SPY orb60 P fixed 15/45 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-020 | 93 | -4.18 | -6.66 | 0.37 |
| oa_crosscheck_v1-180 | SPY orb60 P fixed 15/45 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-020 | 100 | -3.72 | -7.77 | 0.32 |
| oa_crosscheck_v1-181 | SPY orb60 P fixed 10/30 desk d40-55t45 sma20_side | oa_crosscheck_v1-021 | 93 | -5.16 | -4.75 | 0.54 |
| oa_crosscheck_v1-182 | SPY orb60 P fixed 10/30 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-021 | 100 | -5.78 | -4.62 | 0.59 |
| oa_crosscheck_v1-183 | SPY orb60 P fixed 10/30 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-022 | 93 | -4.65 | -7.10 | 0.32 |
| oa_crosscheck_v1-184 | SPY orb60 P fixed 10/30 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-022 | 100 | -5.56 | -7.36 | 0.39 |
| oa_crosscheck_v1-185 | QQQ orb60 C fixed 20/20 desk d40-55t45 sma20_side | oa_crosscheck_v1-025 | 46 | -9.30 | -10.43 | 0.24 |
| oa_crosscheck_v1-186 | QQQ orb60 C fixed 20/20 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-025 | 74 | -7.40 | -10.37 | 0.09 |
| oa_crosscheck_v1-187 | QQQ orb60 C fixed 20/20 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-026 | 46 | -9.54 | -10.43 | 0.31 |
| oa_crosscheck_v1-188 | QQQ orb60 C fixed 20/20 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-026 | 74 | -7.26 | -10.35 | 0.14 |
| oa_crosscheck_v1-189 | QQQ orb60 C fixed 20/40 desk d40-55t45 sma20_side | oa_crosscheck_v1-027 | 46 | -11.26 | -10.88 | 0.59 |
| oa_crosscheck_v1-190 | QQQ orb60 C fixed 20/40 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-027 | 74 | -9.92 | -10.85 | 0.36 |
| oa_crosscheck_v1-191 | QQQ orb60 C fixed 20/40 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-028 | 46 | -10.40 | -10.68 | 0.46 |
| oa_crosscheck_v1-192 | QQQ orb60 C fixed 20/40 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-028 | 74 | -8.43 | -10.70 | 0.27 |
| oa_crosscheck_v1-193 | QQQ orb60 C fixed 20/60 desk d40-55t45 sma20_side | oa_crosscheck_v1-029 | 46 | -12.12 | -13.67 | 0.25 |
| oa_crosscheck_v1-194 | QQQ orb60 C fixed 20/60 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-029 | 74 | -11.41 | -13.72 | 0.25 |
| oa_crosscheck_v1-195 | QQQ orb60 C fixed 20/60 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-030 | 46 | -12.29 | -15.52 | 0.10 |
| oa_crosscheck_v1-196 | QQQ orb60 C fixed 20/60 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-030 | 74 | -8.92 | -15.66 | 0.04 |
| oa_crosscheck_v1-197 | QQQ orb60 C fixed 15/45 desk d40-55t45 sma20_side | oa_crosscheck_v1-031 | 46 | -9.38 | -10.95 | 0.17 |
| oa_crosscheck_v1-198 | QQQ orb60 C fixed 15/45 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-031 | 74 | -8.54 | -10.89 | 0.17 |
| oa_crosscheck_v1-199 | QQQ orb60 C fixed 15/45 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-032 | 46 | -8.63 | -11.29 | 0.12 |
| oa_crosscheck_v1-200 | QQQ orb60 C fixed 15/45 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-032 | 74 | -7.89 | -11.29 | 0.14 |
| oa_crosscheck_v1-201 | QQQ orb60 C fixed 10/30 desk d40-55t45 sma20_side | oa_crosscheck_v1-033 | 46 | -7.68 | -8.15 | 0.34 |
| oa_crosscheck_v1-202 | QQQ orb60 C fixed 10/30 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-033 | 74 | -6.58 | -8.02 | 0.22 |
| oa_crosscheck_v1-203 | QQQ orb60 C fixed 10/30 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-034 | 46 | -8.09 | -8.81 | 0.35 |
| oa_crosscheck_v1-204 | QQQ orb60 C fixed 10/30 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-034 | 74 | -6.99 | -8.62 | 0.25 |
| oa_crosscheck_v1-205 | QQQ orb60 P fixed 20/20 desk d40-55t45 sma20_side | oa_crosscheck_v1-037 | 81 | 1.67 | -1.10 | 0.31 |
| oa_crosscheck_v1-206 | QQQ orb60 P fixed 20/20 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-037 | 89 | 2.30 | -1.09 | 0.30 |
| oa_crosscheck_v1-207 | QQQ orb60 P fixed 20/20 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-038 | 81 | 3.11 | -1.43 | 0.25 |
| oa_crosscheck_v1-208 | QQQ orb60 P fixed 20/20 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-038 | 89 | 9.97 | -1.76 | 0.08 |
| oa_crosscheck_v1-209 | QQQ orb60 P fixed 20/40 desk d40-55t45 sma20_side | oa_crosscheck_v1-039 | 81 | 1.05 | -1.65 | 0.33 |
| oa_crosscheck_v1-210 | QQQ orb60 P fixed 20/40 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-039 | 89 | 1.17 | -1.82 | 0.34 |
| oa_crosscheck_v1-211 | QQQ orb60 P fixed 20/40 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-040 | 81 | 14.31 | -0.23 | 0.05 |
| oa_crosscheck_v1-212 | QQQ orb60 P fixed 20/40 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-040 | 89 | 21.15 | -0.45 | 0.03 |
| oa_crosscheck_v1-213 | QQQ orb60 P fixed 20/60 desk d40-55t45 sma20_side | oa_crosscheck_v1-041 | 81 | 0.78 | -3.67 | 0.31 |
| oa_crosscheck_v1-214 | QQQ orb60 P fixed 20/60 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-041 | 89 | -4.44 | -3.95 | 0.49 |
| oa_crosscheck_v1-215 | QQQ orb60 P fixed 20/60 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-042 | 81 | 13.07 | -4.27 | 0.06 |
| oa_crosscheck_v1-216 | QQQ orb60 P fixed 20/60 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-042 | 89 | 13.54 | -4.31 | 0.10 |
| oa_crosscheck_v1-217 | QQQ orb60 P fixed 15/45 desk d40-55t45 sma20_side | oa_crosscheck_v1-043 | 81 | -11.68 | -6.28 | 0.81 |
| oa_crosscheck_v1-218 | QQQ orb60 P fixed 15/45 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-043 | 89 | -13.27 | -6.42 | 0.81 |
| oa_crosscheck_v1-219 | QQQ orb60 P fixed 15/45 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-044 | 81 | -1.07 | -4.95 | 0.33 |
| oa_crosscheck_v1-220 | QQQ orb60 P fixed 15/45 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-044 | 89 | -3.61 | -5.00 | 0.43 |
| oa_crosscheck_v1-221 | QQQ orb60 P fixed 10/30 desk d40-55t45 sma20_side | oa_crosscheck_v1-045 | 81 | -14.53 | -8.23 | 0.96 |
| oa_crosscheck_v1-222 | QQQ orb60 P fixed 10/30 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-045 | 89 | -17.42 | -8.54 | 0.98 |
| oa_crosscheck_v1-223 | QQQ orb60 P fixed 10/30 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-046 | 81 | -6.59 | -6.29 | 0.51 |
| oa_crosscheck_v1-224 | QQQ orb60 P fixed 10/30 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-046 | 89 | -5.13 | -6.67 | 0.39 |
| oa_crosscheck_v1-225 | IWM orb60 C fixed 20/20 desk d40-55t45 sma20_side | oa_crosscheck_v1-049 | 31 | -5.08 | -5.80 | 0.34 |
| oa_crosscheck_v1-226 | IWM orb60 C fixed 20/20 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-049 | 44 | -3.15 | -5.56 | 0.17 |
| oa_crosscheck_v1-227 | IWM orb60 C fixed 20/20 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-050 | 31 | -8.65 | -7.42 | 0.71 |
| oa_crosscheck_v1-228 | IWM orb60 C fixed 20/20 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-050 | 44 | -6.90 | -7.10 | 0.49 |
| oa_crosscheck_v1-229 | IWM orb60 C fixed 20/40 desk d40-55t45 sma20_side | oa_crosscheck_v1-051 | 31 | -5.36 | -5.42 | 0.49 |
| oa_crosscheck_v1-230 | IWM orb60 C fixed 20/40 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-051 | 44 | -3.01 | -4.95 | 0.28 |
| oa_crosscheck_v1-231 | IWM orb60 C fixed 20/40 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-052 | 31 | -6.44 | -5.99 | 0.57 |
| oa_crosscheck_v1-232 | IWM orb60 C fixed 20/40 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-052 | 44 | -3.88 | -5.45 | 0.36 |
| oa_crosscheck_v1-233 | IWM orb60 C fixed 20/60 desk d40-55t45 sma20_side | oa_crosscheck_v1-053 | 31 | -6.65 | -5.43 | 0.67 |
| oa_crosscheck_v1-234 | IWM orb60 C fixed 20/60 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-053 | 44 | -4.36 | -4.95 | 0.45 |
| oa_crosscheck_v1-235 | IWM orb60 C fixed 20/60 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-054 | 31 | -9.92 | -8.62 | 0.66 |
| oa_crosscheck_v1-236 | IWM orb60 C fixed 20/60 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-054 | 44 | -8.05 | -8.07 | 0.48 |
| oa_crosscheck_v1-237 | IWM orb60 C fixed 15/45 desk d40-55t45 sma20_side | oa_crosscheck_v1-055 | 31 | -7.84 | -7.61 | 0.55 |
| oa_crosscheck_v1-238 | IWM orb60 C fixed 15/45 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-055 | 44 | -5.30 | -7.37 | 0.24 |
| oa_crosscheck_v1-239 | IWM orb60 C fixed 15/45 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-056 | 31 | -6.30 | -7.04 | 0.38 |
| oa_crosscheck_v1-240 | IWM orb60 C fixed 15/45 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-056 | 44 | -2.68 | -6.71 | 0.11 |
| oa_crosscheck_v1-241 | IWM orb60 C fixed 10/30 desk d40-55t45 sma20_side | oa_crosscheck_v1-057 | 31 | -6.17 | -5.32 | 0.76 |
| oa_crosscheck_v1-242 | IWM orb60 C fixed 10/30 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-057 | 44 | -4.39 | -5.17 | 0.34 |
| oa_crosscheck_v1-243 | IWM orb60 C fixed 10/30 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-058 | 31 | -7.53 | -7.43 | 0.52 |
| oa_crosscheck_v1-244 | IWM orb60 C fixed 10/30 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-058 | 44 | -5.07 | -7.17 | 0.19 |
| oa_crosscheck_v1-245 | IWM orb60 P fixed 20/20 desk d40-55t45 sma20_side | oa_crosscheck_v1-061 | 53 | -2.70 | -4.99 | 0.14 |
| oa_crosscheck_v1-246 | IWM orb60 P fixed 20/20 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-061 | 62 | -4.82 | -5.06 | 0.46 |
| oa_crosscheck_v1-247 | IWM orb60 P fixed 20/20 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-062 | 53 | -1.98 | -3.63 | 0.30 |
| oa_crosscheck_v1-248 | IWM orb60 P fixed 20/20 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-062 | 62 | -4.19 | -3.84 | 0.56 |
| oa_crosscheck_v1-249 | IWM orb60 P fixed 20/40 desk d40-55t45 sma20_side | oa_crosscheck_v1-063 | 53 | -1.38 | -4.49 | 0.16 |
| oa_crosscheck_v1-250 | IWM orb60 P fixed 20/40 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-063 | 62 | -0.27 | -4.58 | 0.12 |
| oa_crosscheck_v1-251 | IWM orb60 P fixed 20/40 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-064 | 53 | -5.39 | -4.89 | 0.54 |
| oa_crosscheck_v1-252 | IWM orb60 P fixed 20/40 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-064 | 62 | -5.42 | -5.03 | 0.52 |
| oa_crosscheck_v1-253 | IWM orb60 P fixed 20/60 desk d40-55t45 sma20_side | oa_crosscheck_v1-065 | 53 | -4.53 | -6.51 | 0.29 |
| oa_crosscheck_v1-254 | IWM orb60 P fixed 20/60 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-065 | 62 | -3.03 | -6.33 | 0.21 |
| oa_crosscheck_v1-255 | IWM orb60 P fixed 20/60 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-066 | 53 | -4.27 | -4.37 | 0.51 |
| oa_crosscheck_v1-256 | IWM orb60 P fixed 20/60 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-066 | 62 | -2.55 | -4.41 | 0.35 |
| oa_crosscheck_v1-257 | IWM orb60 P fixed 15/45 desk d40-55t45 sma20_side | oa_crosscheck_v1-067 | 53 | -1.07 | -3.92 | 0.15 |
| oa_crosscheck_v1-258 | IWM orb60 P fixed 15/45 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-067 | 62 | 0.84 | -4.04 | 0.05 |
| oa_crosscheck_v1-259 | IWM orb60 P fixed 15/45 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-068 | 53 | -1.69 | -5.04 | 0.17 |
| oa_crosscheck_v1-260 | IWM orb60 P fixed 15/45 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-068 | 62 | 0.75 | -5.18 | 0.07 |
| oa_crosscheck_v1-261 | IWM orb60 P fixed 10/30 desk d40-55t45 sma20_side | oa_crosscheck_v1-069 | 53 | -4.32 | -4.87 | 0.37 |
| oa_crosscheck_v1-262 | IWM orb60 P fixed 10/30 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-069 | 62 | -5.66 | -4.97 | 0.64 |
| oa_crosscheck_v1-263 | IWM orb60 P fixed 10/30 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-070 | 53 | -5.28 | -5.39 | 0.47 |
| oa_crosscheck_v1-264 | IWM orb60 P fixed 10/30 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-070 | 62 | -4.84 | -5.62 | 0.41 |
| oa_crosscheck_v1-265 | SPY orb60 C fixed 20/20 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-001 | 13 | -6.15 | -5.49 | 0.86 |
| oa_crosscheck_v1-266 | SPY orb60 C fixed 20/20 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-002 | 13 | -4.39 | -4.52 | 0.43 |
| oa_crosscheck_v1-267 | SPY orb60 C fixed 20/40 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-003 | 13 | -7.68 | -8.28 | 0.24 |
| oa_crosscheck_v1-268 | SPY orb60 C fixed 20/40 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-004 | 13 | -8.70 | -9.75 | 0.16 |
| oa_crosscheck_v1-269 | SPY orb60 C fixed 20/60 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-005 | 13 | -10.86 | -11.33 | 0.32 |
| oa_crosscheck_v1-270 | SPY orb60 C fixed 20/60 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-006 | 13 | -9.01 | -9.87 | 0.27 |
| oa_crosscheck_v1-271 | SPY orb60 C fixed 15/45 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-007 | 13 | -10.13 | -9.99 | 0.57 |
| oa_crosscheck_v1-272 | SPY orb60 C fixed 15/45 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-008 | 13 | -10.10 | -10.49 | 0.36 |
| oa_crosscheck_v1-273 | SPY orb60 C fixed 10/30 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-009 | 13 | -7.80 | -7.32 | 0.84 |
| oa_crosscheck_v1-274 | SPY orb60 C fixed 10/30 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-010 | 13 | -6.80 | -6.91 | 0.45 |
| oa_crosscheck_v1-275 | SPY orb60 P fixed 20/20 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-013 | 11 | -4.20 | -5.60 | 0.03 |
| oa_crosscheck_v1-276 | SPY orb60 P fixed 20/20 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-014 | 11 | -1.77 | -4.04 | 0.01 |
| oa_crosscheck_v1-277 | SPY orb60 P fixed 20/40 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-015 | 11 | -4.47 | -7.24 | 0.01 |
| oa_crosscheck_v1-278 | SPY orb60 P fixed 20/40 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-016 | 11 | -6.01 | -9.10 | 0.01 |
| oa_crosscheck_v1-279 | SPY orb60 P fixed 20/60 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-017 | 11 | -6.41 | -8.64 | 0.04 |
| oa_crosscheck_v1-280 | SPY orb60 P fixed 20/60 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-018 | 11 | -6.71 | -9.45 | 0.05 |
| oa_crosscheck_v1-281 | SPY orb60 P fixed 15/45 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-019 | 11 | -6.58 | -8.35 | 0.03 |
| oa_crosscheck_v1-282 | SPY orb60 P fixed 15/45 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-020 | 11 | -5.06 | -7.71 | 0.01 |
| oa_crosscheck_v1-283 | SPY orb60 P fixed 10/30 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-021 | 11 | -3.89 | -5.07 | 0.04 |
| oa_crosscheck_v1-284 | SPY orb60 P fixed 10/30 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-022 | 11 | -6.08 | -7.62 | 0.04 |
| oa_crosscheck_v1-285 | QQQ orb60 C fixed 20/20 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-025 | 13 | -10.16 | -10.37 | 0.41 |
| oa_crosscheck_v1-286 | QQQ orb60 C fixed 20/20 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-026 | 13 | -10.28 | -10.39 | 0.48 |
| oa_crosscheck_v1-287 | QQQ orb60 C fixed 20/40 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-027 | 13 | -10.41 | -10.95 | 0.29 |
| oa_crosscheck_v1-288 | QQQ orb60 C fixed 20/40 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-028 | 13 | -10.75 | -10.80 | 0.52 |
| oa_crosscheck_v1-289 | QQQ orb60 C fixed 20/60 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-029 | 13 | -13.90 | -13.80 | 0.56 |
| oa_crosscheck_v1-290 | QQQ orb60 C fixed 20/60 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-030 | 13 | -16.79 | -15.67 | 0.84 |
| oa_crosscheck_v1-291 | QQQ orb60 C fixed 15/45 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-031 | 13 | -10.59 | -11.03 | 0.33 |
| oa_crosscheck_v1-292 | QQQ orb60 C fixed 15/45 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-032 | 13 | -11.33 | -11.44 | 0.51 |
| oa_crosscheck_v1-293 | QQQ orb60 C fixed 10/30 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-033 | 13 | -8.15 | -8.12 | 0.55 |
| oa_crosscheck_v1-294 | QQQ orb60 C fixed 10/30 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-034 | 13 | -8.58 | -8.83 | 0.40 |
| oa_crosscheck_v1-295 | QQQ orb60 P fixed 20/20 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-037 | 10 | -4.26 | -1.26 | 1.00 |
| oa_crosscheck_v1-296 | QQQ orb60 P fixed 20/20 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-038 | 10 | -4.29 | -1.55 | 0.99 |
| oa_crosscheck_v1-297 | QQQ orb60 P fixed 20/40 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-039 | 10 | -4.20 | -1.63 | 0.95 |
| oa_crosscheck_v1-298 | QQQ orb60 P fixed 20/40 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-040 | 10 | -1.34 | -0.17 | 0.74 |
| oa_crosscheck_v1-299 | QQQ orb60 P fixed 20/60 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-041 | 10 | -4.54 | -3.81 | 0.68 |
| oa_crosscheck_v1-300 | QQQ orb60 P fixed 20/60 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-042 | 10 | -4.88 | -4.13 | 0.68 |
| oa_crosscheck_v1-301 | QQQ orb60 P fixed 15/45 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-043 | 10 | -6.62 | -6.32 | 0.64 |
| oa_crosscheck_v1-302 | QQQ orb60 P fixed 15/45 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-044 | 10 | -5.73 | -4.81 | 0.72 |
| oa_crosscheck_v1-303 | QQQ orb60 P fixed 10/30 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-045 | 10 | -7.77 | -8.37 | 0.22 |
| oa_crosscheck_v1-304 | QQQ orb60 P fixed 10/30 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-046 | 10 | -6.24 | -6.41 | 0.49 |
| oa_crosscheck_v1-305 | IWM orb60 C fixed 20/20 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-049 | 5 | -5.34 | -5.73 | 0.22 |
| oa_crosscheck_v1-306 | IWM orb60 C fixed 20/20 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-050 | 5 | -6.12 | -7.30 | 0.03 |
| oa_crosscheck_v1-307 | IWM orb60 C fixed 20/40 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-051 | 5 | -4.40 | -5.28 | 0.10 |
| oa_crosscheck_v1-308 | IWM orb60 C fixed 20/40 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-052 | 5 | -5.11 | -5.86 | 0.19 |
| oa_crosscheck_v1-309 | IWM orb60 C fixed 20/60 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-053 | 5 | -4.76 | -5.29 | 0.33 |
| oa_crosscheck_v1-310 | IWM orb60 C fixed 20/60 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-054 | 5 | -8.21 | -8.49 | 0.41 |
| oa_crosscheck_v1-311 | IWM orb60 C fixed 15/45 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-055 | 5 | -7.34 | -7.55 | 0.45 |
| oa_crosscheck_v1-312 | IWM orb60 C fixed 15/45 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-056 | 5 | -6.60 | -6.95 | 0.33 |
| oa_crosscheck_v1-313 | IWM orb60 C fixed 10/30 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-057 | 5 | -5.05 | -5.26 | 0.34 |
| oa_crosscheck_v1-314 | IWM orb60 C fixed 10/30 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-058 | 5 | -7.45 | -7.36 | 0.61 |
| oa_crosscheck_v1-315 | IWM orb60 P fixed 20/20 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-061 | 10 | -3.66 | -5.13 | 0.01 |
| oa_crosscheck_v1-316 | IWM orb60 P fixed 20/20 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-062 | 10 | -2.02 | -3.84 | 0.01 |
| oa_crosscheck_v1-317 | IWM orb60 P fixed 20/40 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-063 | 10 | -3.18 | -4.76 | 0.03 |
| oa_crosscheck_v1-318 | IWM orb60 P fixed 20/40 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-064 | 10 | -3.43 | -5.12 | 0.03 |
| oa_crosscheck_v1-319 | IWM orb60 P fixed 20/60 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-065 | 10 | -4.67 | -6.56 | 0.02 |
| oa_crosscheck_v1-320 | IWM orb60 P fixed 20/60 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-066 | 10 | -2.33 | -4.66 | 0.01 |
| oa_crosscheck_v1-321 | IWM orb60 P fixed 15/45 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-067 | 10 | -3.09 | -4.11 | 0.09 |
| oa_crosscheck_v1-322 | IWM orb60 P fixed 15/45 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-068 | 10 | -4.14 | -5.17 | 0.15 |
| oa_crosscheck_v1-323 | IWM orb60 P fixed 10/30 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-069 | 10 | -4.23 | -4.95 | 0.05 |
| oa_crosscheck_v1-324 | IWM orb60 P fixed 10/30 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-070 | 10 | -4.36 | -5.60 | 0.02 |
| oa_crosscheck_v1-325 | SPY orb60 C fixed 20/20 desk d40-55t45 vixy_falling | oa_crosscheck_v1-001 | 41 | -3.96 | -5.47 | 0.12 |
| oa_crosscheck_v1-326 | SPY orb60 C fixed 20/20 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-001 | 63 | -5.52 | -5.38 | 0.52 |
| oa_crosscheck_v1-327 | SPY orb60 C fixed 20/20 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-002 | 41 | -3.44 | -4.48 | 0.28 |
| oa_crosscheck_v1-328 | SPY orb60 C fixed 20/20 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-002 | 63 | -5.86 | -4.39 | 0.72 |
| oa_crosscheck_v1-329 | SPY orb60 C fixed 20/40 desk d40-55t45 vixy_falling | oa_crosscheck_v1-003 | 41 | -6.36 | -8.27 | 0.13 |
| oa_crosscheck_v1-330 | SPY orb60 C fixed 20/40 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-003 | 63 | -7.66 | -8.23 | 0.41 |
| oa_crosscheck_v1-331 | SPY orb60 C fixed 20/40 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-004 | 41 | -7.78 | -9.59 | 0.18 |
| oa_crosscheck_v1-332 | SPY orb60 C fixed 20/40 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-004 | 63 | -11.68 | -9.67 | 0.75 |
| oa_crosscheck_v1-333 | SPY orb60 C fixed 20/60 desk d40-55t45 vixy_falling | oa_crosscheck_v1-005 | 41 | -8.22 | -11.20 | 0.06 |
| oa_crosscheck_v1-334 | SPY orb60 C fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-005 | 63 | -13.76 | -11.26 | 0.80 |
| oa_crosscheck_v1-335 | SPY orb60 C fixed 20/60 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-006 | 41 | -7.28 | -9.67 | 0.18 |
| oa_crosscheck_v1-336 | SPY orb60 C fixed 20/60 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-006 | 63 | -14.32 | -9.80 | 0.89 |
| oa_crosscheck_v1-337 | SPY orb60 C fixed 15/45 desk d40-55t45 vixy_falling | oa_crosscheck_v1-007 | 41 | -9.35 | -9.92 | 0.33 |
| oa_crosscheck_v1-338 | SPY orb60 C fixed 15/45 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-007 | 63 | -9.15 | -9.93 | 0.35 |
| oa_crosscheck_v1-339 | SPY orb60 C fixed 15/45 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-008 | 41 | -9.64 | -10.42 | 0.34 |
| oa_crosscheck_v1-340 | SPY orb60 C fixed 15/45 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-008 | 63 | -11.32 | -10.49 | 0.61 |
| oa_crosscheck_v1-341 | SPY orb60 C fixed 10/30 desk d40-55t45 vixy_falling | oa_crosscheck_v1-009 | 41 | -7.53 | -7.35 | 0.55 |
| oa_crosscheck_v1-342 | SPY orb60 C fixed 10/30 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-009 | 63 | -8.23 | -7.35 | 0.71 |
| oa_crosscheck_v1-343 | SPY orb60 C fixed 10/30 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-010 | 41 | -4.81 | -6.81 | 0.08 |
| oa_crosscheck_v1-344 | SPY orb60 C fixed 10/30 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-010 | 63 | -6.79 | -6.85 | 0.50 |
| oa_crosscheck_v1-345 | SPY orb60 P fixed 20/20 desk d40-55t45 vixy_falling | oa_crosscheck_v1-013 | 78 | -2.81 | -5.57 | 0.23 |
| oa_crosscheck_v1-346 | SPY orb60 P fixed 20/20 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-013 | 87 | -8.87 | -5.45 | 0.77 |
| oa_crosscheck_v1-347 | SPY orb60 P fixed 20/20 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-014 | 78 | -1.01 | -3.94 | 0.25 |
| oa_crosscheck_v1-348 | SPY orb60 P fixed 20/20 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-014 | 87 | -11.12 | -3.75 | 0.92 |
| oa_crosscheck_v1-349 | SPY orb60 P fixed 20/40 desk d40-55t45 vixy_falling | oa_crosscheck_v1-015 | 78 | -5.01 | -7.10 | 0.32 |
| oa_crosscheck_v1-350 | SPY orb60 P fixed 20/40 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-015 | 87 | -17.40 | -6.88 | 0.97 |
| oa_crosscheck_v1-351 | SPY orb60 P fixed 20/40 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-016 | 78 | -8.83 | -8.75 | 0.51 |
| oa_crosscheck_v1-352 | SPY orb60 P fixed 20/40 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-016 | 87 | -23.46 | -8.64 | 0.98 |
| oa_crosscheck_v1-353 | SPY orb60 P fixed 20/60 desk d40-55t45 vixy_falling | oa_crosscheck_v1-017 | 78 | -9.43 | -8.38 | 0.58 |
| oa_crosscheck_v1-354 | SPY orb60 P fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-017 | 87 | -17.28 | -8.37 | 0.91 |
| oa_crosscheck_v1-355 | SPY orb60 P fixed 20/60 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-018 | 78 | -4.02 | -9.16 | 0.21 |
| oa_crosscheck_v1-356 | SPY orb60 P fixed 20/60 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-018 | 87 | -22.51 | -9.09 | 0.96 |
| oa_crosscheck_v1-357 | SPY orb60 P fixed 15/45 desk d40-55t45 vixy_falling | oa_crosscheck_v1-019 | 78 | -8.54 | -8.19 | 0.53 |
| oa_crosscheck_v1-358 | SPY orb60 P fixed 15/45 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-019 | 87 | -11.71 | -8.13 | 0.77 |
| oa_crosscheck_v1-359 | SPY orb60 P fixed 15/45 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-020 | 78 | -11.73 | -7.34 | 0.79 |
| oa_crosscheck_v1-360 | SPY orb60 P fixed 15/45 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-020 | 87 | -15.57 | -7.49 | 0.89 |
| oa_crosscheck_v1-361 | SPY orb60 P fixed 10/30 desk d40-55t45 vixy_falling | oa_crosscheck_v1-021 | 78 | -5.62 | -4.88 | 0.61 |
| oa_crosscheck_v1-362 | SPY orb60 P fixed 10/30 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-021 | 87 | -4.02 | -4.97 | 0.39 |
| oa_crosscheck_v1-363 | SPY orb60 P fixed 10/30 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-022 | 78 | -10.92 | -7.40 | 0.83 |
| oa_crosscheck_v1-364 | SPY orb60 P fixed 10/30 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-022 | 87 | -12.65 | -7.23 | 0.88 |
| oa_crosscheck_v1-365 | QQQ orb60 C fixed 20/20 desk d40-55t45 vixy_falling | oa_crosscheck_v1-025 | 40 | -10.74 | -10.41 | 0.59 |
| oa_crosscheck_v1-366 | QQQ orb60 C fixed 20/20 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-025 | 79 | -7.08 | -10.32 | 0.09 |
| oa_crosscheck_v1-367 | QQQ orb60 C fixed 20/20 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-026 | 40 | -10.68 | -10.47 | 0.55 |
| oa_crosscheck_v1-368 | QQQ orb60 C fixed 20/20 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-026 | 79 | -6.51 | -10.37 | 0.09 |
| oa_crosscheck_v1-369 | QQQ orb60 C fixed 20/40 desk d40-55t45 vixy_falling | oa_crosscheck_v1-027 | 40 | -11.85 | -11.00 | 0.66 |
| oa_crosscheck_v1-370 | QQQ orb60 C fixed 20/40 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-027 | 79 | -4.84 | -10.89 | 0.02 |
| oa_crosscheck_v1-371 | QQQ orb60 C fixed 20/40 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-028 | 40 | -10.42 | -10.77 | 0.45 |
| oa_crosscheck_v1-372 | QQQ orb60 C fixed 20/40 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-028 | 79 | -6.44 | -10.80 | 0.12 |
| oa_crosscheck_v1-373 | QQQ orb60 C fixed 20/60 desk d40-55t45 vixy_falling | oa_crosscheck_v1-029 | 40 | -15.27 | -13.76 | 0.76 |
| oa_crosscheck_v1-374 | QQQ orb60 C fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-029 | 79 | -9.33 | -13.75 | 0.10 |
| oa_crosscheck_v1-375 | QQQ orb60 C fixed 20/60 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-030 | 40 | -16.98 | -15.67 | 0.71 |
| oa_crosscheck_v1-376 | QQQ orb60 C fixed 20/60 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-030 | 79 | -13.58 | -15.71 | 0.30 |
| oa_crosscheck_v1-377 | QQQ orb60 C fixed 15/45 desk d40-55t45 vixy_falling | oa_crosscheck_v1-031 | 40 | -10.89 | -11.00 | 0.49 |
| oa_crosscheck_v1-378 | QQQ orb60 C fixed 15/45 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-031 | 79 | -8.66 | -10.95 | 0.20 |
| oa_crosscheck_v1-379 | QQQ orb60 C fixed 15/45 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-032 | 40 | -12.43 | -11.32 | 0.71 |
| oa_crosscheck_v1-380 | QQQ orb60 C fixed 15/45 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-032 | 79 | -8.02 | -11.34 | 0.18 |
| oa_crosscheck_v1-381 | QQQ orb60 C fixed 10/30 desk d40-55t45 vixy_falling | oa_crosscheck_v1-033 | 40 | -8.28 | -8.15 | 0.56 |
| oa_crosscheck_v1-382 | QQQ orb60 C fixed 10/30 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-033 | 79 | -4.18 | -8.10 | 0.02 |
| oa_crosscheck_v1-383 | QQQ orb60 C fixed 10/30 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-034 | 40 | -8.47 | -8.87 | 0.40 |
| oa_crosscheck_v1-384 | QQQ orb60 C fixed 10/30 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-034 | 79 | -3.05 | -8.75 | 0.02 |
| oa_crosscheck_v1-385 | QQQ orb60 P fixed 20/20 desk d40-55t45 vixy_falling | oa_crosscheck_v1-037 | 68 | 5.53 | -1.13 | 0.05 |
| oa_crosscheck_v1-386 | QQQ orb60 P fixed 20/20 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-037 | 80 | -4.01 | -1.52 | 0.70 |
| oa_crosscheck_v1-387 | QQQ orb60 P fixed 20/20 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-038 | 68 | 2.78 | -1.51 | 0.21 |
| oa_crosscheck_v1-388 | QQQ orb60 P fixed 20/20 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-038 | 80 | -7.92 | -1.75 | 0.86 |
| oa_crosscheck_v1-389 | QQQ orb60 P fixed 20/40 desk d40-55t45 vixy_falling | oa_crosscheck_v1-039 | 68 | -2.95 | -1.39 | 0.60 |
| oa_crosscheck_v1-390 | QQQ orb60 P fixed 20/40 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-039 | 80 | -2.46 | -2.00 | 0.50 |
| oa_crosscheck_v1-391 | QQQ orb60 P fixed 20/40 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-040 | 68 | -5.65 | 0.04 | 0.78 |
| oa_crosscheck_v1-392 | QQQ orb60 P fixed 20/40 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-040 | 80 | -9.44 | -0.81 | 0.82 |
| oa_crosscheck_v1-393 | QQQ orb60 P fixed 20/60 desk d40-55t45 vixy_falling | oa_crosscheck_v1-041 | 68 | -8.32 | -3.69 | 0.74 |
| oa_crosscheck_v1-394 | QQQ orb60 P fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-041 | 80 | -6.63 | -4.28 | 0.60 |
| oa_crosscheck_v1-395 | QQQ orb60 P fixed 20/60 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-042 | 68 | -9.36 | -4.17 | 0.73 |
| oa_crosscheck_v1-396 | QQQ orb60 P fixed 20/60 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-042 | 80 | -10.01 | -5.11 | 0.67 |
| oa_crosscheck_v1-397 | QQQ orb60 P fixed 15/45 desk d40-55t45 vixy_falling | oa_crosscheck_v1-043 | 68 | -10.16 | -6.06 | 0.79 |
| oa_crosscheck_v1-398 | QQQ orb60 P fixed 15/45 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-043 | 80 | 0.65 | -6.42 | 0.14 |
| oa_crosscheck_v1-399 | QQQ orb60 P fixed 15/45 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-044 | 68 | -12.87 | -4.65 | 0.88 |
| oa_crosscheck_v1-400 | QQQ orb60 P fixed 15/45 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-044 | 80 | -10.14 | -5.45 | 0.74 |
| oa_crosscheck_v1-401 | QQQ orb60 P fixed 10/30 desk d40-55t45 vixy_falling | oa_crosscheck_v1-045 | 68 | -9.92 | -8.16 | 0.70 |
| oa_crosscheck_v1-402 | QQQ orb60 P fixed 10/30 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-045 | 80 | -5.45 | -8.25 | 0.24 |
| oa_crosscheck_v1-403 | QQQ orb60 P fixed 10/30 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-046 | 68 | -10.71 | -6.19 | 0.83 |
| oa_crosscheck_v1-404 | QQQ orb60 P fixed 10/30 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-046 | 80 | -2.93 | -6.35 | 0.27 |
| oa_crosscheck_v1-405 | IWM orb60 C fixed 20/20 desk d40-55t45 vixy_falling | oa_crosscheck_v1-049 | 21 | -4.90 | -5.74 | 0.25 |
| oa_crosscheck_v1-406 | IWM orb60 C fixed 20/20 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-049 | 46 | -5.81 | -6.00 | 0.46 |
| oa_crosscheck_v1-407 | IWM orb60 C fixed 20/20 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-050 | 21 | -4.19 | -7.31 | 0.02 |
| oa_crosscheck_v1-408 | IWM orb60 C fixed 20/20 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-050 | 46 | -5.34 | -7.60 | 0.26 |
| oa_crosscheck_v1-409 | IWM orb60 C fixed 20/40 desk d40-55t45 vixy_falling | oa_crosscheck_v1-051 | 21 | -3.65 | -5.25 | 0.18 |
| oa_crosscheck_v1-410 | IWM orb60 C fixed 20/40 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-051 | 46 | -2.31 | -5.63 | 0.17 |
| oa_crosscheck_v1-411 | IWM orb60 C fixed 20/40 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-052 | 21 | -3.15 | -5.86 | 0.09 |
| oa_crosscheck_v1-412 | IWM orb60 C fixed 20/40 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-052 | 46 | -3.80 | -6.15 | 0.29 |
| oa_crosscheck_v1-413 | IWM orb60 C fixed 20/60 desk d40-55t45 vixy_falling | oa_crosscheck_v1-053 | 21 | -4.35 | -5.27 | 0.33 |
| oa_crosscheck_v1-414 | IWM orb60 C fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-053 | 46 | -5.54 | -5.55 | 0.48 |
| oa_crosscheck_v1-415 | IWM orb60 C fixed 20/60 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-054 | 21 | -6.45 | -8.46 | 0.19 |
| oa_crosscheck_v1-416 | IWM orb60 C fixed 20/60 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-054 | 46 | -10.94 | -8.50 | 0.67 |
| oa_crosscheck_v1-417 | IWM orb60 C fixed 15/45 desk d40-55t45 vixy_falling | oa_crosscheck_v1-055 | 21 | -6.75 | -7.56 | 0.27 |
| oa_crosscheck_v1-418 | IWM orb60 C fixed 15/45 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-055 | 46 | -6.31 | -7.75 | 0.30 |
| oa_crosscheck_v1-419 | IWM orb60 C fixed 15/45 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-056 | 21 | -4.64 | -6.93 | 0.08 |
| oa_crosscheck_v1-420 | IWM orb60 C fixed 15/45 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-056 | 46 | -2.22 | -7.24 | 0.07 |
| oa_crosscheck_v1-421 | IWM orb60 C fixed 10/30 desk d40-55t45 vixy_falling | oa_crosscheck_v1-057 | 21 | -4.31 | -5.27 | 0.14 |
| oa_crosscheck_v1-422 | IWM orb60 C fixed 10/30 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-057 | 46 | -5.02 | -5.44 | 0.42 |
| oa_crosscheck_v1-423 | IWM orb60 C fixed 10/30 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-058 | 21 | -5.81 | -7.35 | 0.08 |
| oa_crosscheck_v1-424 | IWM orb60 C fixed 10/30 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-058 | 46 | -5.20 | -7.57 | 0.19 |
| oa_crosscheck_v1-425 | IWM orb60 P fixed 20/20 desk d40-55t45 vixy_falling | oa_crosscheck_v1-061 | 58 | -4.35 | -5.18 | 0.35 |
| oa_crosscheck_v1-426 | IWM orb60 P fixed 20/20 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-061 | 66 | -7.81 | -5.28 | 0.79 |
| oa_crosscheck_v1-427 | IWM orb60 P fixed 20/20 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-062 | 58 | -7.62 | -3.94 | 0.86 |
| oa_crosscheck_v1-428 | IWM orb60 P fixed 20/20 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-062 | 66 | -7.82 | -4.15 | 0.85 |
| oa_crosscheck_v1-429 | IWM orb60 P fixed 20/40 desk d40-55t45 vixy_falling | oa_crosscheck_v1-063 | 58 | -3.22 | -4.92 | 0.31 |
| oa_crosscheck_v1-430 | IWM orb60 P fixed 20/40 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-063 | 66 | -6.25 | -4.94 | 0.61 |
| oa_crosscheck_v1-431 | IWM orb60 P fixed 20/40 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-064 | 58 | -7.17 | -5.29 | 0.67 |
| oa_crosscheck_v1-432 | IWM orb60 P fixed 20/40 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-064 | 66 | -10.38 | -5.36 | 0.86 |
| oa_crosscheck_v1-433 | IWM orb60 P fixed 20/60 desk d40-55t45 vixy_falling | oa_crosscheck_v1-065 | 58 | -3.41 | -6.89 | 0.19 |
| oa_crosscheck_v1-434 | IWM orb60 P fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-065 | 66 | -8.80 | -7.02 | 0.62 |
| oa_crosscheck_v1-435 | IWM orb60 P fixed 20/60 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-066 | 58 | -5.12 | -4.85 | 0.53 |
| oa_crosscheck_v1-436 | IWM orb60 P fixed 20/60 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-066 | 66 | -13.40 | -5.10 | 0.94 |
| oa_crosscheck_v1-437 | IWM orb60 P fixed 15/45 desk d40-55t45 vixy_falling | oa_crosscheck_v1-067 | 58 | -1.89 | -4.31 | 0.21 |
| oa_crosscheck_v1-438 | IWM orb60 P fixed 15/45 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-067 | 66 | -4.05 | -4.24 | 0.48 |
| oa_crosscheck_v1-439 | IWM orb60 P fixed 15/45 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-068 | 58 | -4.52 | -5.50 | 0.42 |
| oa_crosscheck_v1-440 | IWM orb60 P fixed 15/45 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-068 | 66 | -9.35 | -5.44 | 0.79 |
| oa_crosscheck_v1-441 | IWM orb60 P fixed 10/30 desk d40-55t45 vixy_falling | oa_crosscheck_v1-069 | 58 | -3.91 | -4.93 | 0.28 |
| oa_crosscheck_v1-442 | IWM orb60 P fixed 10/30 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-069 | 66 | -4.64 | -5.01 | 0.42 |
| oa_crosscheck_v1-443 | IWM orb60 P fixed 10/30 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-070 | 58 | -6.57 | -5.74 | 0.61 |
| oa_crosscheck_v1-444 | IWM orb60 P fixed 10/30 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-070 | 66 | -3.98 | -5.82 | 0.29 |



Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_oa_crosscheck_v1_2026-10-31.csv.gz`.

Labels: BACKTEST (in-sample on DEV). Spread: MODELED-SPREAD. Delta: BS-EST. Not financial advice: evidence for Nick to decide.
