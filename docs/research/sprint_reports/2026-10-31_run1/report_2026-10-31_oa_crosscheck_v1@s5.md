# Sprint report: oa_crosscheck_v1 (NOT_SEEN_BY_OA), MODELED-SPREAD 5.0% (sensitivity)

Generated 2026-10-31 06:27 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint1` in 2.7 min. Spec sha256 `e11178369dd70a6d53dd9e86209345e9e2665e564b732844e1ff3be39ba19b37`.

**Every number below is a BACKTEST on the period Option Alpha never saw (inside DEV)** on Alpaca 1-minute bars, 2024-08-01 to 2025-10-29. Option fills are real traded prices +/- a half-spread: **MODELED-SPREAD 5.0% of premium for every symbol (a SENSITIVITY run, not the pre-registered 2% default), floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Deltas are BS-EST (Black-Scholes from the option's price). Nothing here is a live or paper fill.

Data: IWM: 313 sessions, QQQ: 313 sessions, SPY: 313 sessions. Runs in this spec: 444. Trials counted for the deflated Sharpe: 1366 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Known limits: July 2024 is locked (L2), so early-August 2024 sessions have partial history; news and VIX are unknown in the backtest (rules that need them never fire); a contract needs BS-EST |delta| inside the band, so some signals have no contract (counted as skips).

**Cost caveat:** MODELED-SPREAD 5.0% of premium for every symbol (a SENSITIVITY run, not the pre-registered 2% default), floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: Cross-check of Option Alpha's Stage-1 candidate (SPY ORB60 long calls, fixed premium stop/target at 1:3: 20/60, 15/45, 10/30; PF 1.30-1.33 on Nov 2025-Jun 2026) and of OA's T1 (50/100, 0.50 delta) in the desk engine, on the part of DEV that Option Alpha never saw: 2024-08-01 to 2025-10-29 (period tag NOT_SEEN_BY_OA). OA rules: 0DTE, first breakout only per side (finished 1-minute close beyond the range), signal bars finishing by 12:00, next-bar entry, fixed stop and target as % of the debit on the option's price, nothing else (no breakeven, no if-flat, no time tightening), all out 15:25 (OA: 35 min before close). Calls and puts run separately, per symbol (SPY is the OA candidate; QQQ and IWM are context). Two exit mechanics: 'desk' = SPRINT_PLAN's fill rules (the base) and 'oa1m' = OA-LIKE (checked once a minute on the close, filled at the next minute's print). Contract: d40-55t45 (BS-EST delta 0.40-0.55 nearest 0.45; OA took the closest delta to 0.45 with no band, so band misses are skipped here and counted). 444 runs. Side rule pre-registered in two forms (no margin, and a 1% margin around the 20-day SMA), see the side_rule block. Two optimizer leads (VIX falling with proxy: VIXY, and the 0 to +/-0.75% open-gap side rule) in the optimizer_leads block; VIXY 1-minute stock bars come from tools/sprint_pull.py (stock bars only, no options). Not tuned: every pair and filter comes from the OA Stage-1 list.


## Fixed premium stop / target runs (Option Alpha's exit; the cross-check)

Each row: one symbol, one side, a fixed stop/target of the debit, all out 15:25. `desk` = SPRINT_PLAN's fill rules (inside the bar, same-bar stop wins); `oa1m` = OA-LIKE mechanics (checked once a minute on the close, filled at the next minute's print). `2m+` = profitable two-month blocks. `OA ref` = Option Alpha's own Stage-1 result for the same rule on SPY, Nov 2025-Jun 2026 (fills MODELED by OA, from docs/research/sprint_runs.csv); T1/T2 used OA's 1-year window. Different period, different fill model: a cross-check, not a replication.

`vixy_falling` = OA's "VIX falling" optimizer lead with **proxy: VIXY** (Alpaca has no VIX index): VIXY's last finished 1-minute close at the decision is below its prior close. `gap_side_075` = open vs prior close in (0%, +0.75%] for calls, [-0.75%, 0%) for puts. Both are in-sample leads from OA's optimizer on its run 023, tested here on data OA never saw.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| oa_crosscheck_v1-007@s5 | SPY | orb60 | C | 15/45 | desk | d40-55t45 | - | 132 | 12.90 | -16.07 | 0.23 | 0.08 | -2121.51 | 0/8 | PF 1.33 (OA-S1-024) |
| oa_crosscheck_v1-008@s5 | SPY | orb60 | C | 15/45 | oa1m | d40-55t45 | - | 132 | 15.90 | -16.78 | 0.29 | 0.12 | -2215.45 | 0/8 | PF 1.33 (OA-S1-024) |
| oa_crosscheck_v1-009@s5 | SPY | orb60 | C | 10/30 | desk | d40-55t45 | - | 132 | 12.10 | -13.43 | 0.17 | 0.04 | -1796.98 | 0/8 | PF 1.30 (OA-S1-025) |
| oa_crosscheck_v1-010@s5 | SPY | orb60 | C | 10/30 | oa1m | d40-55t45 | - | 132 | 14.40 | -15.55 | 0.20 | 0.06 | -2053.00 | 0/8 | PF 1.30 (OA-S1-025) |
| oa_crosscheck_v1-005@s5 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | - | 132 | 13.60 | -17.85 | 0.29 | 0.13 | -2356.56 | 0/8 | PF 1.33 (OA-S1-023) |
| oa_crosscheck_v1-006@s5 | SPY | orb60 | C | 20/60 | oa1m | d40-55t45 | - | 132 | 14.40 | -17.77 | 0.38 | 0.19 | -2345.60 | 1/8 | PF 1.33 (OA-S1-023) |
| oa_crosscheck_v1-003@s5 | SPY | orb60 | C | 20/40 | desk | d40-55t45 | - | 132 | 22.00 | -15.31 | 0.33 | 0.13 | -2038.89 | 0/8 | PF 1.04 (OA-S1-022) |
| oa_crosscheck_v1-004@s5 | SPY | orb60 | C | 20/40 | oa1m | d40-55t45 | - | 132 | 22.70 | -17.01 | 0.36 | 0.16 | -2245.85 | 0/8 | PF 1.04 (OA-S1-022) |
| oa_crosscheck_v1-011@s5 | SPY | orb60 | C | 50/100 | desk | d40-55t45 | - | 132 | 31.10 | -11.93 | 0.70 | 0.47 | -1705.70 | 1/8 | PF 1.44 (T1, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-012@s5 | SPY | orb60 | C | 50/100 | oa1m | d40-55t45 | - | 132 | 32.60 | -9.87 | 0.75 | 0.51 | -1581.30 | 2/8 | PF 1.44 (T1, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-073@s5 | SPY | orb60 | C | 50/100 | desk | d45-60t50 | - | 131 | 33.60 | -11.65 | 0.75 | 0.49 | -2045.19 | 2/8 | PF 1.44 (T1, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-074@s5 | SPY | orb60 | C | 50/100 | oa1m | d45-60t50 | - | 131 | 34.40 | -11.29 | 0.76 | 0.50 | -1730.75 | 2/8 | PF 1.44 (T1, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-001@s5 | SPY | orb60 | C | 20/20 | desk | d40-55t45 | - | 132 | 36.40 | -12.83 | 0.30 | 0.03 | -1727.97 | 0/8 | PF 0.86 (OA-S1-021) |
| oa_crosscheck_v1-002@s5 | SPY | orb60 | C | 20/20 | oa1m | d40-55t45 | - | 132 | 40.90 | -11.31 | 0.43 | 0.11 | -1573.05 | 0/8 | PF 0.86 (OA-S1-021) |
| oa_crosscheck_v1-338@s5 | SPY | orb60 | C | 15/45 | desk | d40-55t45 | gap_side_075 | 69 | 11.60 | -14.96 | 0.20 | 0.07 | -1032.08 | 0/8 |  |
| oa_crosscheck_v1-340@s5 | SPY | orb60 | C | 15/45 | oa1m | d40-55t45 | gap_side_075 | 69 | 14.50 | -16.89 | 0.24 | 0.10 | -1165.20 | 0/8 |  |
| oa_crosscheck_v1-342@s5 | SPY | orb60 | C | 10/30 | desk | d40-55t45 | gap_side_075 | 69 | 14.50 | -11.35 | 0.20 | 0.04 | -807.49 | 0/8 |  |
| oa_crosscheck_v1-344@s5 | SPY | orb60 | C | 10/30 | oa1m | d40-55t45 | gap_side_075 | 69 | 15.90 | -13.05 | 0.25 | 0.08 | -900.15 | 0/8 |  |
| oa_crosscheck_v1-334@s5 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | gap_side_075 | 69 | 11.60 | -17.69 | 0.23 | 0.10 | -1220.56 | 0/8 |  |
| oa_crosscheck_v1-336@s5 | SPY | orb60 | C | 20/60 | oa1m | d40-55t45 | gap_side_075 | 69 | 11.60 | -20.09 | 0.25 | 0.13 | -1423.90 | 1/8 |  |
| oa_crosscheck_v1-330@s5 | SPY | orb60 | C | 20/40 | desk | d40-55t45 | gap_side_075 | 69 | 21.70 | -13.77 | 0.33 | 0.12 | -1022.51 | 0/8 |  |
| oa_crosscheck_v1-332@s5 | SPY | orb60 | C | 20/40 | oa1m | d40-55t45 | gap_side_075 | 69 | 21.70 | -18.06 | 0.27 | 0.12 | -1245.95 | 0/8 |  |
| oa_crosscheck_v1-326@s5 | SPY | orb60 | C | 20/20 | desk | d40-55t45 | gap_side_075 | 69 | 34.80 | -12.08 | 0.28 | 0.03 | -916.58 | 0/8 |  |
| oa_crosscheck_v1-328@s5 | SPY | orb60 | C | 20/20 | oa1m | d40-55t45 | gap_side_075 | 69 | 39.10 | -11.66 | 0.38 | 0.10 | -976.15 | 1/8 |  |
| oa_crosscheck_v1-271@s5 | SPY | orb60 | C | 15/45 | desk | d40-55t45 | skip_fomc_cpi | 119 | 12.60 | -16.12 | 0.23 | 0.08 | -1925.55 | 0/8 | PF 1.35 (OA-S1-079) |
| oa_crosscheck_v1-272@s5 | SPY | orb60 | C | 15/45 | oa1m | d40-55t45 | skip_fomc_cpi | 119 | 16.00 | -16.66 | 0.30 | 0.13 | -1992.45 | 0/8 | PF 1.35 (OA-S1-079) |
| oa_crosscheck_v1-273@s5 | SPY | orb60 | C | 10/30 | desk | d40-55t45 | skip_fomc_cpi | 119 | 11.80 | -13.67 | 0.16 | 0.04 | -1666.36 | 0/8 |  |
| oa_crosscheck_v1-274@s5 | SPY | orb60 | C | 10/30 | oa1m | d40-55t45 | skip_fomc_cpi | 119 | 13.40 | -16.02 | 0.19 | 0.06 | -1906.60 | 0/8 |  |
| oa_crosscheck_v1-269@s5 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | skip_fomc_cpi | 119 | 13.40 | -17.78 | 0.29 | 0.13 | -2129.09 | 0/8 | PF 1.32 (OA-S1-073) |
| oa_crosscheck_v1-270@s5 | SPY | orb60 | C | 20/60 | oa1m | d40-55t45 | skip_fomc_cpi | 119 | 15.10 | -16.92 | 0.41 | 0.21 | -2013.95 | 1/8 | PF 1.32 (OA-S1-073) |
| oa_crosscheck_v1-267@s5 | SPY | orb60 | C | 20/40 | desk | d40-55t45 | skip_fomc_cpi | 119 | 21.80 | -15.13 | 0.34 | 0.13 | -1817.74 | 0/8 |  |
| oa_crosscheck_v1-268@s5 | SPY | orb60 | C | 20/40 | oa1m | d40-55t45 | skip_fomc_cpi | 119 | 23.50 | -16.41 | 0.38 | 0.17 | -1952.20 | 0/8 |  |
| oa_crosscheck_v1-265@s5 | SPY | orb60 | C | 20/20 | desk | d40-55t45 | skip_fomc_cpi | 119 | 34.50 | -13.49 | 0.28 | 0.03 | -1627.87 | 0/8 |  |
| oa_crosscheck_v1-266@s5 | SPY | orb60 | C | 20/20 | oa1m | d40-55t45 | skip_fomc_cpi | 119 | 41.20 | -10.94 | 0.45 | 0.12 | -1394.05 | 0/8 |  |
| oa_crosscheck_v1-157@s5 | SPY | orb60 | C | 15/45 | desk | d40-55t45 | sma20_side | 89 | 12.40 | -13.88 | 0.24 | 0.09 | -1235.55 | 0/8 | PF 1.40 (OA-S1-078) |
| oa_crosscheck_v1-159@s5 | SPY | orb60 | C | 15/45 | oa1m | d40-55t45 | sma20_side | 89 | 15.70 | -13.81 | 0.32 | 0.13 | -1229.15 | 0/8 | PF 1.40 (OA-S1-078) |
| oa_crosscheck_v1-161@s5 | SPY | orb60 | C | 10/30 | desk | d40-55t45 | sma20_side | 89 | 12.40 | -11.62 | 0.18 | 0.04 | -1041.36 | 0/8 |  |
| oa_crosscheck_v1-163@s5 | SPY | orb60 | C | 10/30 | oa1m | d40-55t45 | sma20_side | 89 | 14.60 | -13.30 | 0.21 | 0.07 | -1183.55 | 0/8 |  |
| oa_crosscheck_v1-153@s5 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | sma20_side | 89 | 12.40 | -15.77 | 0.29 | 0.13 | -1403.63 | 0/8 | PF 1.31 (OA-S1-072) |
| oa_crosscheck_v1-155@s5 | SPY | orb60 | C | 20/60 | oa1m | d40-55t45 | sma20_side | 89 | 13.50 | -16.56 | 0.34 | 0.17 | -1474.25 | 0/8 | PF 1.31 (OA-S1-072) |
| oa_crosscheck_v1-149@s5 | SPY | orb60 | C | 20/40 | desk | d40-55t45 | sma20_side | 89 | 19.10 | -15.56 | 0.26 | 0.10 | -1385.24 | 0/8 |  |
| oa_crosscheck_v1-151@s5 | SPY | orb60 | C | 20/40 | oa1m | d40-55t45 | sma20_side | 89 | 22.50 | -14.53 | 0.37 | 0.16 | -1292.80 | 0/8 |  |
| oa_crosscheck_v1-145@s5 | SPY | orb60 | C | 20/20 | desk | d40-55t45 | sma20_side | 89 | 33.70 | -12.16 | 0.27 | 0.03 | -1107.14 | 0/8 |  |
| oa_crosscheck_v1-147@s5 | SPY | orb60 | C | 20/20 | oa1m | d40-55t45 | sma20_side | 89 | 38.20 | -9.97 | 0.44 | 0.12 | -941.60 | 0/8 |  |
| oa_crosscheck_v1-158@s5 | SPY | orb60 | C | 15/45 | desk | d40-55t45 | sma20_side_1pct | 60 | 15.00 | -12.29 | 0.31 | 0.11 | -737.62 | 0/8 |  |
| oa_crosscheck_v1-160@s5 | SPY | orb60 | C | 15/45 | oa1m | d40-55t45 | sma20_side_1pct | 60 | 16.70 | -12.21 | 0.38 | 0.16 | -732.45 | 0/8 |  |
| oa_crosscheck_v1-162@s5 | SPY | orb60 | C | 10/30 | desk | d40-55t45 | sma20_side_1pct | 60 | 11.70 | -11.75 | 0.17 | 0.04 | -705.08 | 0/8 |  |
| oa_crosscheck_v1-164@s5 | SPY | orb60 | C | 10/30 | oa1m | d40-55t45 | sma20_side_1pct | 60 | 15.00 | -13.24 | 0.22 | 0.07 | -794.20 | 0/8 |  |
| oa_crosscheck_v1-154@s5 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | sma20_side_1pct | 60 | 11.70 | -15.95 | 0.28 | 0.13 | -956.97 | 0/8 |  |
| oa_crosscheck_v1-156@s5 | SPY | orb60 | C | 20/60 | oa1m | d40-55t45 | sma20_side_1pct | 60 | 10.00 | -18.46 | 0.28 | 0.14 | -1107.70 | 0/8 |  |
| oa_crosscheck_v1-150@s5 | SPY | orb60 | C | 20/40 | desk | d40-55t45 | sma20_side_1pct | 60 | 18.30 | -15.75 | 0.26 | 0.10 | -944.97 | 0/8 |  |
| oa_crosscheck_v1-152@s5 | SPY | orb60 | C | 20/40 | oa1m | d40-55t45 | sma20_side_1pct | 60 | 21.70 | -14.20 | 0.38 | 0.17 | -861.05 | 1/8 |  |
| oa_crosscheck_v1-146@s5 | SPY | orb60 | C | 20/20 | desk | d40-55t45 | sma20_side_1pct | 60 | 31.70 | -12.33 | 0.27 | 0.03 | -739.84 | 0/8 |  |
| oa_crosscheck_v1-148@s5 | SPY | orb60 | C | 20/20 | oa1m | d40-55t45 | sma20_side_1pct | 60 | 36.70 | -9.82 | 0.44 | 0.12 | -615.85 | 1/8 |  |
| oa_crosscheck_v1-337@s5 | SPY | orb60 | C | 15/45 | desk | d40-55t45 | vixy_falling | 91 | 11.00 | -15.86 | 0.20 | 0.07 | -1443.39 | 0/8 |  |
| oa_crosscheck_v1-339@s5 | SPY | orb60 | C | 15/45 | oa1m | d40-55t45 | vixy_falling | 91 | 16.50 | -15.31 | 0.31 | 0.13 | -1392.85 | 0/8 |  |
| oa_crosscheck_v1-341@s5 | SPY | orb60 | C | 10/30 | desk | d40-55t45 | vixy_falling | 91 | 12.10 | -12.71 | 0.17 | 0.04 | -1180.52 | 0/8 |  |
| oa_crosscheck_v1-343@s5 | SPY | orb60 | C | 10/30 | oa1m | d40-55t45 | vixy_falling | 91 | 13.20 | -15.06 | 0.19 | 0.06 | -1370.05 | 0/8 |  |
| oa_crosscheck_v1-333@s5 | SPY | orb60 | C | 20/60 | desk | d40-55t45 | vixy_falling | 91 | 14.30 | -15.98 | 0.32 | 0.14 | -1453.90 | 1/8 |  |
| oa_crosscheck_v1-335@s5 | SPY | orb60 | C | 20/60 | oa1m | d40-55t45 | vixy_falling | 91 | 16.50 | -14.05 | 0.46 | 0.24 | -1288.85 | 1/8 |  |
| oa_crosscheck_v1-329@s5 | SPY | orb60 | C | 20/40 | desk | d40-55t45 | vixy_falling | 91 | 23.10 | -12.55 | 0.40 | 0.15 | -1214.56 | 1/8 |  |
| oa_crosscheck_v1-331@s5 | SPY | orb60 | C | 20/40 | oa1m | d40-55t45 | vixy_falling | 91 | 24.20 | -14.85 | 0.39 | 0.17 | -1351.05 | 1/8 |  |
| oa_crosscheck_v1-325@s5 | SPY | orb60 | C | 20/20 | desk | d40-55t45 | vixy_falling | 91 | 38.50 | -10.43 | 0.35 | 0.04 | -1013.33 | 1/8 |  |
| oa_crosscheck_v1-327@s5 | SPY | orb60 | C | 20/20 | oa1m | d40-55t45 | vixy_falling | 91 | 42.90 | -8.70 | 0.51 | 0.13 | -901.85 | 1/8 |  |
| oa_crosscheck_v1-019@s5 | SPY | orb60 | P | 15/45 | desk | d40-55t45 | - | 124 | 16.10 | -17.84 | 0.29 | 0.10 | -2212.14 | 0/8 | PF 0.88 (OA-S1-029) |
| oa_crosscheck_v1-020@s5 | SPY | orb60 | P | 15/45 | oa1m | d40-55t45 | - | 124 | 18.50 | -16.13 | 0.42 | 0.18 | -1999.55 | 0/8 | PF 0.88 (OA-S1-029) |
| oa_crosscheck_v1-021@s5 | SPY | orb60 | P | 10/30 | desk | d40-55t45 | - | 124 | 17.70 | -13.67 | 0.27 | 0.06 | -1694.49 | 0/8 | PF 1.00 (OA-S1-030) |
| oa_crosscheck_v1-022@s5 | SPY | orb60 | P | 10/30 | oa1m | d40-55t45 | - | 124 | 21.00 | -13.53 | 0.39 | 0.13 | -1677.50 | 0/8 | PF 1.00 (OA-S1-030) |
| oa_crosscheck_v1-017@s5 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | - | 124 | 17.70 | -16.73 | 0.44 | 0.20 | -2162.44 | 0/8 | PF 0.88 (OA-S1-028) |
| oa_crosscheck_v1-018@s5 | SPY | orb60 | P | 20/60 | oa1m | d40-55t45 | - | 124 | 20.20 | -16.29 | 0.52 | 0.27 | -2124.60 | 1/8 | PF 0.88 (OA-S1-028) |
| oa_crosscheck_v1-015@s5 | SPY | orb60 | P | 20/40 | desk | d40-55t45 | - | 124 | 25.00 | -16.97 | 0.39 | 0.15 | -2159.86 | 0/8 | PF 0.87 (OA-S1-027) |
| oa_crosscheck_v1-016@s5 | SPY | orb60 | P | 20/40 | oa1m | d40-55t45 | - | 124 | 26.60 | -16.98 | 0.47 | 0.21 | -2199.65 | 1/8 | PF 0.87 (OA-S1-027) |
| oa_crosscheck_v1-023@s5 | SPY | orb60 | P | 50/100 | desk | d40-55t45 | - | 124 | 35.50 | -3.46 | 0.93 | 0.63 | -1502.09 | 3/8 | PF 0.73 (T2, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-024@s5 | SPY | orb60 | P | 50/100 | oa1m | d40-55t45 | - | 124 | 37.10 | 1.25 | 1.02 | 0.71 | -1456.00 | 4/8 | PF 0.73 (T2, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-075@s5 | SPY | orb60 | P | 50/100 | desk | d45-60t50 | - | 122 | 34.40 | -10.45 | 0.82 | 0.55 | -2280.09 | 2/8 | PF 0.73 (T2, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-076@s5 | SPY | orb60 | P | 50/100 | oa1m | d45-60t50 | - | 122 | 35.20 | -7.43 | 0.88 | 0.60 | -2303.60 | 3/8 | PF 0.73 (T2, 0.50 delta, OA 1y window) |
| oa_crosscheck_v1-013@s5 | SPY | orb60 | P | 20/20 | desk | d40-55t45 | - | 124 | 43.50 | -11.87 | 0.41 | 0.04 | -1495.02 | 1/8 | PF 0.91 (OA-S1-026) |
| oa_crosscheck_v1-014@s5 | SPY | orb60 | P | 20/20 | oa1m | d40-55t45 | - | 124 | 38.70 | -14.26 | 0.45 | 0.13 | -1811.90 | 1/8 | PF 0.91 (OA-S1-026) |
| oa_crosscheck_v1-358@s5 | SPY | orb60 | P | 15/45 | desk | d40-55t45 | gap_side_075 | 37 | 10.80 | -20.92 | 0.19 | 0.07 | -827.70 | 1/7 |  |
| oa_crosscheck_v1-360@s5 | SPY | orb60 | P | 15/45 | oa1m | d40-55t45 | gap_side_075 | 37 | 10.80 | -22.94 | 0.23 | 0.09 | -914.10 | 1/7 |  |
| oa_crosscheck_v1-362@s5 | SPY | orb60 | P | 10/30 | desk | d40-55t45 | gap_side_075 | 37 | 16.20 | -14.39 | 0.23 | 0.05 | -596.46 | 1/7 |  |
| oa_crosscheck_v1-364@s5 | SPY | orb60 | P | 10/30 | oa1m | d40-55t45 | gap_side_075 | 37 | 10.80 | -20.99 | 0.15 | 0.04 | -851.40 | 0/7 |  |
| oa_crosscheck_v1-354@s5 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | gap_side_075 | 37 | 13.50 | -21.58 | 0.30 | 0.13 | -875.30 | 1/7 |  |
| oa_crosscheck_v1-356@s5 | SPY | orb60 | P | 20/60 | oa1m | d40-55t45 | gap_side_075 | 37 | 13.50 | -26.30 | 0.29 | 0.15 | -1060.40 | 1/7 |  |
| oa_crosscheck_v1-350@s5 | SPY | orb60 | P | 20/40 | desk | d40-55t45 | gap_side_075 | 37 | 18.90 | -21.70 | 0.26 | 0.10 | -842.98 | 0/7 |  |
| oa_crosscheck_v1-352@s5 | SPY | orb60 | P | 20/40 | oa1m | d40-55t45 | gap_side_075 | 37 | 16.20 | -27.69 | 0.23 | 0.11 | -1089.85 | 1/7 |  |
| oa_crosscheck_v1-346@s5 | SPY | orb60 | P | 20/20 | desk | d40-55t45 | gap_side_075 | 37 | 37.80 | -14.98 | 0.32 | 0.03 | -591.29 | 1/7 |  |
| oa_crosscheck_v1-348@s5 | SPY | orb60 | P | 20/20 | oa1m | d40-55t45 | gap_side_075 | 37 | 32.40 | -18.73 | 0.34 | 0.10 | -778.85 | 1/7 |  |
| oa_crosscheck_v1-281@s5 | SPY | orb60 | P | 15/45 | desk | d40-55t45 | skip_fomc_cpi | 113 | 16.80 | -16.80 | 0.30 | 0.11 | -1898.51 | 0/8 |  |
| oa_crosscheck_v1-282@s5 | SPY | orb60 | P | 15/45 | oa1m | d40-55t45 | skip_fomc_cpi | 113 | 19.50 | -14.63 | 0.46 | 0.20 | -1653.10 | 0/8 |  |
| oa_crosscheck_v1-283@s5 | SPY | orb60 | P | 10/30 | desk | d40-55t45 | skip_fomc_cpi | 113 | 19.50 | -11.97 | 0.32 | 0.07 | -1352.40 | 0/8 |  |
| oa_crosscheck_v1-284@s5 | SPY | orb60 | P | 10/30 | oa1m | d40-55t45 | skip_fomc_cpi | 113 | 22.10 | -12.21 | 0.43 | 0.14 | -1379.50 | 0/8 |  |
| oa_crosscheck_v1-279@s5 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | skip_fomc_cpi | 113 | 18.60 | -14.74 | 0.47 | 0.21 | -1754.35 | 0/8 |  |
| oa_crosscheck_v1-280@s5 | SPY | orb60 | P | 20/60 | oa1m | d40-55t45 | skip_fomc_cpi | 113 | 21.20 | -13.88 | 0.57 | 0.29 | -1780.10 | 2/8 |  |
| oa_crosscheck_v1-277@s5 | SPY | orb60 | P | 20/40 | desk | d40-55t45 | skip_fomc_cpi | 113 | 26.50 | -14.61 | 0.43 | 0.16 | -1706.49 | 0/8 |  |
| oa_crosscheck_v1-278@s5 | SPY | orb60 | P | 20/40 | oa1m | d40-55t45 | skip_fomc_cpi | 113 | 28.30 | -14.16 | 0.52 | 0.24 | -1742.55 | 2/8 |  |
| oa_crosscheck_v1-275@s5 | SPY | orb60 | P | 20/20 | desk | d40-55t45 | skip_fomc_cpi | 113 | 45.10 | -10.02 | 0.46 | 0.05 | -1155.56 | 1/8 |  |
| oa_crosscheck_v1-276@s5 | SPY | orb60 | P | 20/20 | oa1m | d40-55t45 | skip_fomc_cpi | 113 | 41.60 | -10.63 | 0.54 | 0.16 | -1294.00 | 1/8 |  |
| oa_crosscheck_v1-177@s5 | SPY | orb60 | P | 15/45 | desk | d40-55t45 | sma20_side | 31 | 16.10 | -27.37 | 0.26 | 0.09 | -928.57 | 1/6 |  |
| oa_crosscheck_v1-179@s5 | SPY | orb60 | P | 15/45 | oa1m | d40-55t45 | sma20_side | 31 | 25.80 | -13.50 | 0.62 | 0.25 | -575.20 | 1/6 |  |
| oa_crosscheck_v1-181@s5 | SPY | orb60 | P | 10/30 | desk | d40-55t45 | sma20_side | 31 | 16.10 | -21.92 | 0.21 | 0.05 | -728.40 | 0/6 |  |
| oa_crosscheck_v1-183@s5 | SPY | orb60 | P | 10/30 | oa1m | d40-55t45 | sma20_side | 31 | 25.80 | -14.78 | 0.50 | 0.15 | -531.65 | 1/6 |  |
| oa_crosscheck_v1-173@s5 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | sma20_side | 31 | 25.80 | -12.31 | 0.69 | 0.31 | -547.78 | 1/6 |  |
| oa_crosscheck_v1-175@s5 | SPY | orb60 | P | 20/60 | oa1m | d40-55t45 | sma20_side | 31 | 29.00 | -9.05 | 0.80 | 0.41 | -614.15 | 2/6 |  |
| oa_crosscheck_v1-169@s5 | SPY | orb60 | P | 20/40 | desk | d40-55t45 | sma20_side | 31 | 32.30 | -17.85 | 0.52 | 0.20 | -613.81 | 2/6 |  |
| oa_crosscheck_v1-171@s5 | SPY | orb60 | P | 20/40 | oa1m | d40-55t45 | sma20_side | 31 | 35.50 | -18.64 | 0.57 | 0.25 | -752.55 | 2/6 |  |
| oa_crosscheck_v1-165@s5 | SPY | orb60 | P | 20/20 | desk | d40-55t45 | sma20_side | 31 | 58.10 | -8.65 | 0.64 | 0.07 | -445.25 | 3/6 |  |
| oa_crosscheck_v1-167@s5 | SPY | orb60 | P | 20/20 | oa1m | d40-55t45 | sma20_side | 31 | 54.80 | -10.31 | 0.66 | 0.18 | -478.10 | 3/6 |  |
| oa_crosscheck_v1-178@s5 | SPY | orb60 | P | 15/45 | desk | d40-55t45 | sma20_side_1pct | 24 | 12.50 | -33.27 | 0.18 | 0.07 | -813.73 | 1/5 |  |
| oa_crosscheck_v1-180@s5 | SPY | orb60 | P | 15/45 | oa1m | d40-55t45 | sma20_side_1pct | 24 | 25.00 | -15.64 | 0.59 | 0.24 | -527.90 | 1/5 |  |
| oa_crosscheck_v1-182@s5 | SPY | orb60 | P | 10/30 | desk | d40-55t45 | sma20_side_1pct | 24 | 12.50 | -26.04 | 0.16 | 0.04 | -682.65 | 0/5 |  |
| oa_crosscheck_v1-184@s5 | SPY | orb60 | P | 10/30 | oa1m | d40-55t45 | sma20_side_1pct | 24 | 25.00 | -16.82 | 0.47 | 0.14 | -475.65 | 1/5 |  |
| oa_crosscheck_v1-174@s5 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | sma20_side_1pct | 24 | 29.20 | -10.12 | 0.75 | 0.34 | -486.86 | 2/5 |  |
| oa_crosscheck_v1-176@s5 | SPY | orb60 | P | 20/60 | oa1m | d40-55t45 | sma20_side_1pct | 24 | 29.20 | -10.37 | 0.79 | 0.41 | -587.40 | 2/5 |  |
| oa_crosscheck_v1-170@s5 | SPY | orb60 | P | 20/40 | desk | d40-55t45 | sma20_side_1pct | 24 | 33.30 | -18.80 | 0.53 | 0.20 | -570.70 | 2/5 |  |
| oa_crosscheck_v1-172@s5 | SPY | orb60 | P | 20/40 | oa1m | d40-55t45 | sma20_side_1pct | 24 | 33.30 | -23.08 | 0.52 | 0.23 | -723.75 | 2/5 |  |
| oa_crosscheck_v1-166@s5 | SPY | orb60 | P | 20/20 | desk | d40-55t45 | sma20_side_1pct | 24 | 62.50 | -7.43 | 0.69 | 0.08 | -400.13 | 3/5 |  |
| oa_crosscheck_v1-168@s5 | SPY | orb60 | P | 20/20 | oa1m | d40-55t45 | sma20_side_1pct | 24 | 58.30 | -8.67 | 0.72 | 0.20 | -478.10 | 3/5 |  |
| oa_crosscheck_v1-357@s5 | SPY | orb60 | P | 15/45 | desk | d40-55t45 | vixy_falling | 46 | 15.20 | -18.86 | 0.27 | 0.10 | -867.43 | 2/8 |  |
| oa_crosscheck_v1-359@s5 | SPY | orb60 | P | 15/45 | oa1m | d40-55t45 | vixy_falling | 46 | 15.20 | -19.71 | 0.33 | 0.14 | -906.55 | 2/8 |  |
| oa_crosscheck_v1-361@s5 | SPY | orb60 | P | 10/30 | desk | d40-55t45 | vixy_falling | 46 | 13.00 | -15.98 | 0.20 | 0.04 | -735.04 | 1/8 |  |
| oa_crosscheck_v1-363@s5 | SPY | orb60 | P | 10/30 | oa1m | d40-55t45 | vixy_falling | 46 | 17.40 | -17.00 | 0.27 | 0.08 | -782.10 | 1/8 |  |
| oa_crosscheck_v1-353@s5 | SPY | orb60 | P | 20/60 | desk | d40-55t45 | vixy_falling | 46 | 17.40 | -17.91 | 0.41 | 0.18 | -823.74 | 2/8 |  |
| oa_crosscheck_v1-355@s5 | SPY | orb60 | P | 20/60 | oa1m | d40-55t45 | vixy_falling | 46 | 21.70 | -13.66 | 0.59 | 0.30 | -684.35 | 3/8 |  |
| oa_crosscheck_v1-349@s5 | SPY | orb60 | P | 20/40 | desk | d40-55t45 | vixy_falling | 46 | 23.90 | -18.53 | 0.35 | 0.13 | -852.47 | 1/8 |  |
| oa_crosscheck_v1-351@s5 | SPY | orb60 | P | 20/40 | oa1m | d40-55t45 | vixy_falling | 46 | 26.10 | -17.81 | 0.44 | 0.20 | -820.20 | 3/8 |  |
| oa_crosscheck_v1-345@s5 | SPY | orb60 | P | 20/20 | desk | d40-55t45 | vixy_falling | 46 | 45.70 | -9.36 | 0.50 | 0.06 | -430.42 | 2/8 |  |
| oa_crosscheck_v1-347@s5 | SPY | orb60 | P | 20/20 | oa1m | d40-55t45 | vixy_falling | 46 | 37.00 | -13.97 | 0.45 | 0.13 | -642.45 | 2/8 |  |
| oa_crosscheck_v1-098@s5 | SPY | orb15 | C | 15/45 | desk | d40-55t45 | - | 211 | 17.10 | -13.14 | 0.43 | 0.16 | -2858.68 | 0/8 |  |
| oa_crosscheck_v1-099@s5 | SPY | orb15 | C | 10/30 | desk | d40-55t45 | - | 211 | 13.70 | -13.81 | 0.26 | 0.06 | -2920.24 | 0/8 |  |
| oa_crosscheck_v1-097@s5 | SPY | orb15 | C | 20/60 | desk | d40-55t45 | - | 211 | 19.40 | -12.88 | 0.54 | 0.24 | -2852.69 | 0/8 |  |
| oa_crosscheck_v1-096@s5 | SPY | orb15 | C | 20/40 | desk | d40-55t45 | - | 211 | 28.00 | -10.68 | 0.57 | 0.21 | -2498.13 | 0/8 |  |
| oa_crosscheck_v1-095@s5 | SPY | orb15 | C | 20/20 | desk | d40-55t45 | - | 211 | 41.20 | -12.47 | 0.39 | 0.04 | -2776.61 | 0/8 |  |
| oa_crosscheck_v1-103@s5 | SPY | orb15 | P | 15/45 | desk | d40-55t45 | - | 205 | 17.10 | -15.80 | 0.38 | 0.14 | -3238.56 | 1/8 |  |
| oa_crosscheck_v1-104@s5 | SPY | orb15 | P | 10/30 | desk | d40-55t45 | - | 205 | 13.20 | -16.27 | 0.21 | 0.05 | -3335.68 | 0/8 |  |
| oa_crosscheck_v1-102@s5 | SPY | orb15 | P | 20/60 | desk | d40-55t45 | - | 205 | 18.00 | -16.59 | 0.47 | 0.21 | -3400.73 | 0/8 |  |
| oa_crosscheck_v1-101@s5 | SPY | orb15 | P | 20/40 | desk | d40-55t45 | - | 205 | 24.40 | -16.72 | 0.42 | 0.16 | -3427.98 | 1/8 |  |
| oa_crosscheck_v1-100@s5 | SPY | orb15 | P | 20/20 | desk | d40-55t45 | - | 205 | 42.90 | -13.26 | 0.40 | 0.04 | -2717.36 | 0/8 |  |
| oa_crosscheck_v1-088@s5 | SPY | orb30 | C | 15/45 | desk | d40-55t45 | - | 186 | 15.60 | -14.27 | 0.36 | 0.13 | -2653.40 | 0/8 |  |
| oa_crosscheck_v1-089@s5 | SPY | orb30 | C | 10/30 | desk | d40-55t45 | - | 186 | 14.50 | -13.24 | 0.25 | 0.06 | -2462.65 | 0/8 |  |
| oa_crosscheck_v1-087@s5 | SPY | orb30 | C | 20/60 | desk | d40-55t45 | - | 186 | 16.10 | -16.56 | 0.40 | 0.18 | -3190.18 | 0/8 |  |
| oa_crosscheck_v1-086@s5 | SPY | orb30 | C | 20/40 | desk | d40-55t45 | - | 186 | 23.70 | -14.96 | 0.41 | 0.15 | -2805.04 | 0/8 |  |
| oa_crosscheck_v1-085@s5 | SPY | orb30 | C | 20/20 | desk | d40-55t45 | - | 186 | 35.50 | -15.38 | 0.28 | 0.03 | -2860.40 | 0/8 |  |
| oa_crosscheck_v1-093@s5 | SPY | orb30 | P | 15/45 | desk | d40-55t45 | - | 170 | 17.10 | -16.32 | 0.35 | 0.13 | -2889.61 | 0/8 |  |
| oa_crosscheck_v1-094@s5 | SPY | orb30 | P | 10/30 | desk | d40-55t45 | - | 170 | 14.70 | -14.81 | 0.25 | 0.06 | -2542.54 | 0/8 |  |
| oa_crosscheck_v1-092@s5 | SPY | orb30 | P | 20/60 | desk | d40-55t45 | - | 170 | 16.50 | -19.68 | 0.38 | 0.17 | -3447.06 | 0/8 |  |
| oa_crosscheck_v1-091@s5 | SPY | orb30 | P | 20/40 | desk | d40-55t45 | - | 170 | 23.50 | -17.84 | 0.38 | 0.14 | -3062.08 | 0/8 |  |
| oa_crosscheck_v1-090@s5 | SPY | orb30 | P | 20/20 | desk | d40-55t45 | - | 170 | 39.40 | -14.84 | 0.34 | 0.04 | -2522.95 | 0/8 |  |
| oa_crosscheck_v1-031@s5 | QQQ | orb60 | C | 15/45 | desk | d40-55t45 | - | 135 | 14.10 | -15.96 | 0.29 | 0.10 | -2154.98 | 0/8 |  |
| oa_crosscheck_v1-032@s5 | QQQ | orb60 | C | 15/45 | oa1m | d40-55t45 | - | 135 | 14.80 | -18.80 | 0.29 | 0.12 | -2537.85 | 1/8 |  |
| oa_crosscheck_v1-033@s5 | QQQ | orb60 | C | 10/30 | desk | d40-55t45 | - | 135 | 12.60 | -14.42 | 0.18 | 0.04 | -1955.82 | 0/8 |  |
| oa_crosscheck_v1-034@s5 | QQQ | orb60 | C | 10/30 | oa1m | d40-55t45 | - | 135 | 16.30 | -15.79 | 0.26 | 0.08 | -2146.80 | 0/8 |  |
| oa_crosscheck_v1-029@s5 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | - | 135 | 12.60 | -20.37 | 0.28 | 0.12 | -2750.61 | 0/8 |  |
| oa_crosscheck_v1-030@s5 | QQQ | orb60 | C | 20/60 | oa1m | d40-55t45 | - | 135 | 14.10 | -22.01 | 0.30 | 0.15 | -2972.00 | 0/8 |  |
| oa_crosscheck_v1-027@s5 | QQQ | orb60 | C | 20/40 | desk | d40-55t45 | - | 135 | 20.00 | -17.56 | 0.32 | 0.12 | -2374.51 | 0/8 |  |
| oa_crosscheck_v1-028@s5 | QQQ | orb60 | C | 20/40 | oa1m | d40-55t45 | - | 135 | 23.00 | -17.07 | 0.39 | 0.17 | -2305.10 | 0/8 |  |
| oa_crosscheck_v1-035@s5 | QQQ | orb60 | C | 50/100 | desk | d40-55t45 | - | 135 | 28.90 | -15.71 | 0.66 | 0.44 | -2197.87 | 1/8 |  |
| oa_crosscheck_v1-036@s5 | QQQ | orb60 | C | 50/100 | oa1m | d40-55t45 | - | 135 | 30.40 | -15.98 | 0.66 | 0.45 | -2223.50 | 1/8 |  |
| oa_crosscheck_v1-077@s5 | QQQ | orb60 | C | 50/100 | desk | d45-60t50 | - | 134 | 30.60 | -16.99 | 0.68 | 0.45 | -2586.52 | 2/8 |  |
| oa_crosscheck_v1-078@s5 | QQQ | orb60 | C | 50/100 | oa1m | d45-60t50 | - | 134 | 31.30 | -18.40 | 0.66 | 0.45 | -2701.85 | 2/8 |  |
| oa_crosscheck_v1-025@s5 | QQQ | orb60 | C | 20/20 | desk | d40-55t45 | - | 135 | 30.40 | -17.77 | 0.21 | 0.02 | -2398.73 | 0/8 |  |
| oa_crosscheck_v1-026@s5 | QQQ | orb60 | C | 20/20 | oa1m | d40-55t45 | - | 135 | 34.10 | -16.21 | 0.33 | 0.08 | -2193.20 | 0/8 |  |
| oa_crosscheck_v1-378@s5 | QQQ | orb60 | C | 15/45 | desk | d40-55t45 | gap_side_075 | 56 | 14.30 | -14.76 | 0.27 | 0.10 | -854.37 | 0/8 |  |
| oa_crosscheck_v1-380@s5 | QQQ | orb60 | C | 15/45 | oa1m | d40-55t45 | gap_side_075 | 56 | 16.10 | -16.58 | 0.30 | 0.12 | -949.15 | 1/8 |  |
| oa_crosscheck_v1-382@s5 | QQQ | orb60 | C | 10/30 | desk | d40-55t45 | gap_side_075 | 56 | 17.90 | -10.53 | 0.29 | 0.07 | -645.14 | 1/8 |  |
| oa_crosscheck_v1-384@s5 | QQQ | orb60 | C | 10/30 | oa1m | d40-55t45 | gap_side_075 | 56 | 21.40 | -11.07 | 0.40 | 0.13 | -749.70 | 1/8 |  |
| oa_crosscheck_v1-374@s5 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | gap_side_075 | 56 | 14.30 | -17.19 | 0.31 | 0.14 | -962.50 | 1/8 |  |
| oa_crosscheck_v1-376@s5 | QQQ | orb60 | C | 20/60 | oa1m | d40-55t45 | gap_side_075 | 56 | 16.10 | -17.55 | 0.37 | 0.19 | -982.55 | 1/8 |  |
| oa_crosscheck_v1-370@s5 | QQQ | orb60 | C | 20/40 | desk | d40-55t45 | gap_side_075 | 56 | 26.80 | -10.92 | 0.48 | 0.18 | -700.94 | 2/8 |  |
| oa_crosscheck_v1-372@s5 | QQQ | orb60 | C | 20/40 | oa1m | d40-55t45 | gap_side_075 | 56 | 25.00 | -14.39 | 0.42 | 0.18 | -893.50 | 1/8 |  |
| oa_crosscheck_v1-366@s5 | QQQ | orb60 | C | 20/20 | desk | d40-55t45 | gap_side_075 | 56 | 37.50 | -12.71 | 0.30 | 0.03 | -788.81 | 1/8 |  |
| oa_crosscheck_v1-368@s5 | QQQ | orb60 | C | 20/20 | oa1m | d40-55t45 | gap_side_075 | 56 | 41.10 | -10.64 | 0.47 | 0.14 | -737.70 | 1/8 |  |
| oa_crosscheck_v1-291@s5 | QQQ | orb60 | C | 15/45 | desk | d40-55t45 | skip_fomc_cpi | 122 | 14.80 | -15.71 | 0.30 | 0.11 | -1916.15 | 0/8 |  |
| oa_crosscheck_v1-292@s5 | QQQ | orb60 | C | 15/45 | oa1m | d40-55t45 | skip_fomc_cpi | 122 | 15.60 | -18.44 | 0.31 | 0.13 | -2249.75 | 1/8 |  |
| oa_crosscheck_v1-293@s5 | QQQ | orb60 | C | 10/30 | desk | d40-55t45 | skip_fomc_cpi | 122 | 12.30 | -14.71 | 0.17 | 0.04 | -1804.20 | 0/8 |  |
| oa_crosscheck_v1-294@s5 | QQQ | orb60 | C | 10/30 | oa1m | d40-55t45 | skip_fomc_cpi | 122 | 17.20 | -15.55 | 0.28 | 0.08 | -1912.85 | 0/8 |  |
| oa_crosscheck_v1-289@s5 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | skip_fomc_cpi | 122 | 12.30 | -20.82 | 0.27 | 0.12 | -2540.32 | 0/8 |  |
| oa_crosscheck_v1-290@s5 | QQQ | orb60 | C | 20/60 | oa1m | d40-55t45 | skip_fomc_cpi | 122 | 12.30 | -23.60 | 0.27 | 0.13 | -2879.60 | 0/8 |  |
| oa_crosscheck_v1-287@s5 | QQQ | orb60 | C | 20/40 | desk | d40-55t45 | skip_fomc_cpi | 122 | 20.50 | -17.34 | 0.33 | 0.12 | -2119.33 | 0/8 |  |
| oa_crosscheck_v1-288@s5 | QQQ | orb60 | C | 20/40 | oa1m | d40-55t45 | skip_fomc_cpi | 122 | 22.10 | -17.55 | 0.38 | 0.16 | -2141.45 | 0/8 |  |
| oa_crosscheck_v1-285@s5 | QQQ | orb60 | C | 20/20 | desk | d40-55t45 | skip_fomc_cpi | 122 | 30.30 | -17.94 | 0.21 | 0.02 | -2189.25 | 0/8 |  |
| oa_crosscheck_v1-286@s5 | QQQ | orb60 | C | 20/20 | oa1m | d40-55t45 | skip_fomc_cpi | 122 | 33.60 | -16.32 | 0.33 | 0.08 | -1996.30 | 0/8 |  |
| oa_crosscheck_v1-197@s5 | QQQ | orb60 | C | 15/45 | desk | d40-55t45 | sma20_side | 89 | 14.60 | -13.77 | 0.32 | 0.11 | -1225.21 | 1/8 |  |
| oa_crosscheck_v1-199@s5 | QQQ | orb60 | C | 15/45 | oa1m | d40-55t45 | sma20_side | 89 | 15.70 | -15.67 | 0.34 | 0.14 | -1397.70 | 1/8 |  |
| oa_crosscheck_v1-201@s5 | QQQ | orb60 | C | 10/30 | desk | d40-55t45 | sma20_side | 89 | 13.50 | -12.51 | 0.21 | 0.05 | -1122.14 | 0/8 |  |
| oa_crosscheck_v1-203@s5 | QQQ | orb60 | C | 10/30 | oa1m | d40-55t45 | sma20_side | 89 | 15.70 | -14.18 | 0.27 | 0.08 | -1269.20 | 0/8 |  |
| oa_crosscheck_v1-193@s5 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | sma20_side | 89 | 14.60 | -16.74 | 0.33 | 0.15 | -1577.70 | 1/8 |  |
| oa_crosscheck_v1-195@s5 | QQQ | orb60 | C | 20/60 | oa1m | d40-55t45 | sma20_side | 89 | 16.90 | -17.02 | 0.38 | 0.19 | -1616.20 | 1/8 |  |
| oa_crosscheck_v1-189@s5 | QQQ | orb60 | C | 20/40 | desk | d40-55t45 | sma20_side | 89 | 18.00 | -17.16 | 0.28 | 0.11 | -1527.67 | 1/8 |  |
| oa_crosscheck_v1-191@s5 | QQQ | orb60 | C | 20/40 | oa1m | d40-55t45 | sma20_side | 89 | 23.60 | -14.73 | 0.41 | 0.18 | -1310.80 | 1/8 |  |
| oa_crosscheck_v1-185@s5 | QQQ | orb60 | C | 20/20 | desk | d40-55t45 | sma20_side | 89 | 31.50 | -15.33 | 0.23 | 0.02 | -1364.11 | 1/8 |  |
| oa_crosscheck_v1-187@s5 | QQQ | orb60 | C | 20/20 | oa1m | d40-55t45 | sma20_side | 89 | 33.70 | -14.40 | 0.34 | 0.09 | -1286.30 | 1/8 |  |
| oa_crosscheck_v1-198@s5 | QQQ | orb60 | C | 15/45 | desk | d40-55t45 | sma20_side_1pct | 61 | 16.40 | -11.96 | 0.37 | 0.13 | -748.90 | 1/8 |  |
| oa_crosscheck_v1-200@s5 | QQQ | orb60 | C | 15/45 | oa1m | d40-55t45 | sma20_side_1pct | 61 | 16.40 | -14.62 | 0.36 | 0.15 | -914.20 | 1/8 |  |
| oa_crosscheck_v1-202@s5 | QQQ | orb60 | C | 10/30 | desk | d40-55t45 | sma20_side_1pct | 61 | 14.80 | -11.91 | 0.22 | 0.05 | -740.67 | 1/8 |  |
| oa_crosscheck_v1-204@s5 | QQQ | orb60 | C | 10/30 | oa1m | d40-55t45 | sma20_side_1pct | 61 | 18.00 | -12.53 | 0.31 | 0.09 | -764.45 | 1/8 |  |
| oa_crosscheck_v1-194@s5 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | sma20_side_1pct | 61 | 16.40 | -14.79 | 0.38 | 0.17 | -1016.84 | 2/8 |  |
| oa_crosscheck_v1-196@s5 | QQQ | orb60 | C | 20/60 | oa1m | d40-55t45 | sma20_side_1pct | 61 | 19.70 | -14.21 | 0.46 | 0.23 | -990.20 | 2/8 |  |
| oa_crosscheck_v1-190@s5 | QQQ | orb60 | C | 20/40 | desk | d40-55t45 | sma20_side_1pct | 61 | 19.70 | -15.45 | 0.32 | 0.12 | -979.13 | 1/8 |  |
| oa_crosscheck_v1-192@s5 | QQQ | orb60 | C | 20/40 | oa1m | d40-55t45 | sma20_side_1pct | 61 | 26.20 | -12.92 | 0.46 | 0.20 | -836.30 | 2/8 |  |
| oa_crosscheck_v1-186@s5 | QQQ | orb60 | C | 20/20 | desk | d40-55t45 | sma20_side_1pct | 61 | 36.10 | -12.77 | 0.29 | 0.03 | -815.99 | 1/8 |  |
| oa_crosscheck_v1-188@s5 | QQQ | orb60 | C | 20/20 | oa1m | d40-55t45 | sma20_side_1pct | 61 | 37.70 | -12.80 | 0.36 | 0.09 | -839.75 | 1/8 |  |
| oa_crosscheck_v1-377@s5 | QQQ | orb60 | C | 15/45 | desk | d40-55t45 | vixy_falling | 95 | 12.60 | -16.18 | 0.26 | 0.09 | -1537.57 | 0/8 |  |
| oa_crosscheck_v1-379@s5 | QQQ | orb60 | C | 15/45 | oa1m | d40-55t45 | vixy_falling | 95 | 13.70 | -18.20 | 0.28 | 0.11 | -1729.20 | 0/8 |  |
| oa_crosscheck_v1-381@s5 | QQQ | orb60 | C | 10/30 | desk | d40-55t45 | vixy_falling | 95 | 11.60 | -14.37 | 0.17 | 0.04 | -1365.09 | 0/8 |  |
| oa_crosscheck_v1-383@s5 | QQQ | orb60 | C | 10/30 | oa1m | d40-55t45 | vixy_falling | 95 | 14.70 | -15.21 | 0.25 | 0.08 | -1518.70 | 0/8 |  |
| oa_crosscheck_v1-373@s5 | QQQ | orb60 | C | 20/60 | desk | d40-55t45 | vixy_falling | 95 | 10.50 | -21.57 | 0.23 | 0.10 | -2048.78 | 0/8 |  |
| oa_crosscheck_v1-375@s5 | QQQ | orb60 | C | 20/60 | oa1m | d40-55t45 | vixy_falling | 95 | 11.60 | -23.82 | 0.23 | 0.11 | -2263.10 | 0/8 |  |
| oa_crosscheck_v1-369@s5 | QQQ | orb60 | C | 20/40 | desk | d40-55t45 | vixy_falling | 95 | 20.00 | -16.27 | 0.34 | 0.13 | -1617.26 | 0/8 |  |
| oa_crosscheck_v1-371@s5 | QQQ | orb60 | C | 20/40 | oa1m | d40-55t45 | vixy_falling | 95 | 22.10 | -16.66 | 0.38 | 0.16 | -1656.45 | 0/8 |  |
| oa_crosscheck_v1-365@s5 | QQQ | orb60 | C | 20/20 | desk | d40-55t45 | vixy_falling | 95 | 28.40 | -17.74 | 0.20 | 0.02 | -1715.02 | 0/8 |  |
| oa_crosscheck_v1-367@s5 | QQQ | orb60 | C | 20/20 | oa1m | d40-55t45 | vixy_falling | 95 | 31.60 | -16.10 | 0.32 | 0.08 | -1565.25 | 0/8 |  |
| oa_crosscheck_v1-043@s5 | QQQ | orb60 | P | 15/45 | desk | d40-55t45 | - | 111 | 14.40 | -18.16 | 0.32 | 0.12 | -2015.96 | 0/8 |  |
| oa_crosscheck_v1-044@s5 | QQQ | orb60 | P | 15/45 | oa1m | d40-55t45 | - | 111 | 19.80 | -15.40 | 0.50 | 0.22 | -1756.30 | 1/8 |  |
| oa_crosscheck_v1-045@s5 | QQQ | orb60 | P | 10/30 | desk | d40-55t45 | - | 111 | 12.60 | -15.95 | 0.23 | 0.05 | -1775.21 | 0/8 |  |
| oa_crosscheck_v1-046@s5 | QQQ | orb60 | P | 10/30 | oa1m | d40-55t45 | - | 111 | 18.00 | -16.53 | 0.36 | 0.12 | -1835.30 | 0/8 |  |
| oa_crosscheck_v1-041@s5 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | - | 111 | 19.80 | -11.25 | 0.62 | 0.28 | -1533.77 | 2/8 |  |
| oa_crosscheck_v1-042@s5 | QQQ | orb60 | P | 20/60 | oa1m | d40-55t45 | - | 111 | 19.80 | -14.16 | 0.59 | 0.30 | -1858.90 | 2/8 |  |
| oa_crosscheck_v1-039@s5 | QQQ | orb60 | P | 20/40 | desk | d40-55t45 | - | 111 | 28.80 | -10.76 | 0.59 | 0.23 | -1427.23 | 0/8 |  |
| oa_crosscheck_v1-040@s5 | QQQ | orb60 | P | 20/40 | oa1m | d40-55t45 | - | 111 | 27.90 | -12.94 | 0.59 | 0.26 | -1716.05 | 1/8 |  |
| oa_crosscheck_v1-047@s5 | QQQ | orb60 | P | 50/100 | desk | d40-55t45 | - | 111 | 33.30 | -4.50 | 0.92 | 0.62 | -1180.21 | 2/8 |  |
| oa_crosscheck_v1-048@s5 | QQQ | orb60 | P | 50/100 | oa1m | d40-55t45 | - | 111 | 32.40 | -2.52 | 0.95 | 0.67 | -1165.60 | 3/8 |  |
| oa_crosscheck_v1-079@s5 | QQQ | orb60 | P | 50/100 | desk | d45-60t50 | - | 110 | 34.50 | -2.65 | 0.96 | 0.65 | -1270.48 | 2/8 |  |
| oa_crosscheck_v1-080@s5 | QQQ | orb60 | P | 50/100 | oa1m | d45-60t50 | - | 110 | 33.60 | -7.18 | 0.89 | 0.62 | -1422.15 | 1/8 |  |
| oa_crosscheck_v1-037@s5 | QQQ | orb60 | P | 20/20 | desk | d40-55t45 | - | 111 | 42.30 | -11.87 | 0.44 | 0.05 | -1400.88 | 0/8 |  |
| oa_crosscheck_v1-038@s5 | QQQ | orb60 | P | 20/20 | oa1m | d40-55t45 | - | 111 | 39.60 | -11.78 | 0.55 | 0.17 | -1453.00 | 1/8 |  |
| oa_crosscheck_v1-398@s5 | QQQ | orb60 | P | 15/45 | desk | d40-55t45 | gap_side_075 | 31 | 16.10 | -15.03 | 0.40 | 0.14 | -604.58 | 1/7 |  |
| oa_crosscheck_v1-400@s5 | QQQ | orb60 | P | 15/45 | oa1m | d40-55t45 | gap_side_075 | 31 | 22.60 | -16.35 | 0.47 | 0.21 | -757.35 | 2/7 |  |
| oa_crosscheck_v1-402@s5 | QQQ | orb60 | P | 10/30 | desk | d40-55t45 | gap_side_075 | 31 | 16.10 | -11.72 | 0.37 | 0.09 | -422.79 | 1/7 |  |
| oa_crosscheck_v1-404@s5 | QQQ | orb60 | P | 10/30 | oa1m | d40-55t45 | gap_side_075 | 31 | 22.60 | -12.46 | 0.47 | 0.16 | -489.45 | 2/7 |  |
| oa_crosscheck_v1-394@s5 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | gap_side_075 | 31 | 22.60 | -11.23 | 0.61 | 0.27 | -658.88 | 2/7 |  |
| oa_crosscheck_v1-396@s5 | QQQ | orb60 | P | 20/60 | oa1m | d40-55t45 | gap_side_075 | 31 | 22.60 | -15.46 | 0.56 | 0.28 | -807.70 | 2/7 |  |
| oa_crosscheck_v1-390@s5 | QQQ | orb60 | P | 20/40 | desk | d40-55t45 | gap_side_075 | 31 | 29.00 | -11.12 | 0.57 | 0.22 | -499.08 | 3/7 |  |
| oa_crosscheck_v1-392@s5 | QQQ | orb60 | P | 20/40 | oa1m | d40-55t45 | gap_side_075 | 31 | 25.80 | -20.98 | 0.39 | 0.17 | -806.75 | 3/7 |  |
| oa_crosscheck_v1-386@s5 | QQQ | orb60 | P | 20/20 | desk | d40-55t45 | gap_side_075 | 31 | 41.90 | -12.62 | 0.41 | 0.04 | -473.09 | 2/7 |  |
| oa_crosscheck_v1-388@s5 | QQQ | orb60 | P | 20/20 | oa1m | d40-55t45 | gap_side_075 | 31 | 35.50 | -17.06 | 0.38 | 0.10 | -657.15 | 2/7 |  |
| oa_crosscheck_v1-301@s5 | QQQ | orb60 | P | 15/45 | desk | d40-55t45 | skip_fomc_cpi | 101 | 14.90 | -17.43 | 0.32 | 0.11 | -1760.79 | 0/8 |  |
| oa_crosscheck_v1-302@s5 | QQQ | orb60 | P | 15/45 | oa1m | d40-55t45 | skip_fomc_cpi | 101 | 20.80 | -14.60 | 0.51 | 0.22 | -1597.15 | 2/8 |  |
| oa_crosscheck_v1-303@s5 | QQQ | orb60 | P | 10/30 | desk | d40-55t45 | skip_fomc_cpi | 101 | 12.90 | -15.43 | 0.22 | 0.05 | -1563.09 | 0/8 |  |
| oa_crosscheck_v1-304@s5 | QQQ | orb60 | P | 10/30 | oa1m | d40-55t45 | skip_fomc_cpi | 101 | 18.80 | -15.69 | 0.37 | 0.13 | -1584.95 | 0/8 |  |
| oa_crosscheck_v1-299@s5 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | skip_fomc_cpi | 101 | 19.80 | -11.86 | 0.59 | 0.26 | -1571.35 | 2/8 |  |
| oa_crosscheck_v1-300@s5 | QQQ | orb60 | P | 20/60 | oa1m | d40-55t45 | skip_fomc_cpi | 101 | 19.80 | -14.61 | 0.57 | 0.28 | -1861.25 | 1/8 |  |
| oa_crosscheck_v1-297@s5 | QQQ | orb60 | P | 20/40 | desk | d40-55t45 | skip_fomc_cpi | 101 | 28.70 | -11.09 | 0.57 | 0.22 | -1326.52 | 1/8 |  |
| oa_crosscheck_v1-298@s5 | QQQ | orb60 | P | 20/40 | oa1m | d40-55t45 | skip_fomc_cpi | 101 | 27.70 | -13.04 | 0.57 | 0.26 | -1577.20 | 2/8 |  |
| oa_crosscheck_v1-295@s5 | QQQ | orb60 | P | 20/20 | desk | d40-55t45 | skip_fomc_cpi | 101 | 39.60 | -13.78 | 0.37 | 0.04 | -1457.50 | 0/8 |  |
| oa_crosscheck_v1-296@s5 | QQQ | orb60 | P | 20/20 | oa1m | d40-55t45 | skip_fomc_cpi | 101 | 37.60 | -13.09 | 0.50 | 0.16 | -1461.45 | 2/8 |  |
| oa_crosscheck_v1-217@s5 | QQQ | orb60 | P | 15/45 | desk | d40-55t45 | sma20_side | 30 | 10.00 | -25.43 | 0.28 | 0.10 | -827.11 | 0/7 |  |
| oa_crosscheck_v1-219@s5 | QQQ | orb60 | P | 15/45 | oa1m | d40-55t45 | sma20_side | 30 | 23.30 | -12.13 | 0.68 | 0.30 | -774.75 | 2/7 |  |
| oa_crosscheck_v1-221@s5 | QQQ | orb60 | P | 10/30 | desk | d40-55t45 | sma20_side | 30 | 10.00 | -20.75 | 0.23 | 0.05 | -638.78 | 0/7 |  |
| oa_crosscheck_v1-223@s5 | QQQ | orb60 | P | 10/30 | oa1m | d40-55t45 | sma20_side | 30 | 13.30 | -22.20 | 0.34 | 0.11 | -699.30 | 0/7 |  |
| oa_crosscheck_v1-213@s5 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | sma20_side | 30 | 23.30 | -5.47 | 0.85 | 0.38 | -541.00 | 2/7 |  |
| oa_crosscheck_v1-215@s5 | QQQ | orb60 | P | 20/60 | oa1m | d40-55t45 | sma20_side | 30 | 23.30 | -7.76 | 0.82 | 0.41 | -697.60 | 2/7 |  |
| oa_crosscheck_v1-209@s5 | QQQ | orb60 | P | 20/40 | desk | d40-55t45 | sma20_side | 30 | 30.00 | -8.93 | 0.72 | 0.28 | -440.65 | 2/7 |  |
| oa_crosscheck_v1-211@s5 | QQQ | orb60 | P | 20/40 | oa1m | d40-55t45 | sma20_side | 30 | 30.00 | -12.66 | 0.67 | 0.29 | -669.30 | 2/7 |  |
| oa_crosscheck_v1-205@s5 | QQQ | orb60 | P | 20/20 | desk | d40-55t45 | sma20_side | 30 | 36.70 | -18.48 | 0.38 | 0.04 | -575.47 | 2/7 |  |
| oa_crosscheck_v1-207@s5 | QQQ | orb60 | P | 20/20 | oa1m | d40-55t45 | sma20_side | 30 | 43.30 | -9.88 | 0.67 | 0.18 | -505.50 | 3/7 |  |
| oa_crosscheck_v1-218@s5 | QQQ | orb60 | P | 15/45 | desk | d40-55t45 | sma20_side_1pct | 22 | 9.10 | -29.84 | 0.20 | 0.07 | -690.69 | 0/4 |  |
| oa_crosscheck_v1-220@s5 | QQQ | orb60 | P | 15/45 | oa1m | d40-55t45 | sma20_side_1pct | 22 | 22.70 | -17.98 | 0.54 | 0.23 | -615.85 | 2/4 |  |
| oa_crosscheck_v1-222@s5 | QQQ | orb60 | P | 10/30 | desk | d40-55t45 | sma20_side_1pct | 22 | 9.10 | -23.72 | 0.16 | 0.04 | -538.11 | 0/4 |  |
| oa_crosscheck_v1-224@s5 | QQQ | orb60 | P | 10/30 | oa1m | d40-55t45 | sma20_side_1pct | 22 | 13.60 | -22.78 | 0.33 | 0.11 | -534.45 | 0/4 |  |
| oa_crosscheck_v1-214@s5 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | sma20_side_1pct | 22 | 22.70 | -10.76 | 0.72 | 0.32 | -400.49 | 2/4 |  |
| oa_crosscheck_v1-216@s5 | QQQ | orb60 | P | 20/60 | oa1m | d40-55t45 | sma20_side_1pct | 22 | 27.30 | -2.39 | 0.94 | 0.46 | -453.05 | 2/4 |  |
| oa_crosscheck_v1-210@s5 | QQQ | orb60 | P | 20/40 | desk | d40-55t45 | sma20_side_1pct | 22 | 31.80 | -10.26 | 0.69 | 0.26 | -335.04 | 1/4 |  |
| oa_crosscheck_v1-212@s5 | QQQ | orb60 | P | 20/40 | oa1m | d40-55t45 | sma20_side_1pct | 22 | 31.80 | -12.84 | 0.66 | 0.28 | -495.20 | 2/4 |  |
| oa_crosscheck_v1-206@s5 | QQQ | orb60 | P | 20/20 | desk | d40-55t45 | sma20_side_1pct | 22 | 36.40 | -20.11 | 0.35 | 0.04 | -492.36 | 0/4 |  |
| oa_crosscheck_v1-208@s5 | QQQ | orb60 | P | 20/20 | oa1m | d40-55t45 | sma20_side_1pct | 22 | 45.50 | -6.88 | 0.75 | 0.21 | -369.75 | 2/4 |  |
| oa_crosscheck_v1-397@s5 | QQQ | orb60 | P | 15/45 | desk | d40-55t45 | vixy_falling | 43 | 11.60 | -20.92 | 0.25 | 0.09 | -899.49 | 1/7 |  |
| oa_crosscheck_v1-399@s5 | QQQ | orb60 | P | 15/45 | oa1m | d40-55t45 | vixy_falling | 43 | 14.00 | -22.82 | 0.30 | 0.13 | -981.45 | 1/7 |  |
| oa_crosscheck_v1-401@s5 | QQQ | orb60 | P | 10/30 | desk | d40-55t45 | vixy_falling | 43 | 9.30 | -18.63 | 0.15 | 0.03 | -836.52 | 1/7 |  |
| oa_crosscheck_v1-403@s5 | QQQ | orb60 | P | 10/30 | oa1m | d40-55t45 | vixy_falling | 43 | 16.30 | -20.04 | 0.24 | 0.07 | -861.75 | 1/7 |  |
| oa_crosscheck_v1-393@s5 | QQQ | orb60 | P | 20/60 | desk | d40-55t45 | vixy_falling | 43 | 16.30 | -18.08 | 0.44 | 0.20 | -857.33 | 2/7 |  |
| oa_crosscheck_v1-395@s5 | QQQ | orb60 | P | 20/60 | oa1m | d40-55t45 | vixy_falling | 43 | 18.60 | -18.18 | 0.50 | 0.24 | -872.15 | 2/7 |  |
| oa_crosscheck_v1-389@s5 | QQQ | orb60 | P | 20/40 | desk | d40-55t45 | vixy_falling | 43 | 25.60 | -15.05 | 0.47 | 0.18 | -697.34 | 1/7 |  |
| oa_crosscheck_v1-391@s5 | QQQ | orb60 | P | 20/40 | oa1m | d40-55t45 | vixy_falling | 43 | 23.30 | -18.80 | 0.45 | 0.20 | -888.30 | 0/7 |  |
| oa_crosscheck_v1-385@s5 | QQQ | orb60 | P | 20/20 | desk | d40-55t45 | vixy_falling | 43 | 48.80 | -7.48 | 0.59 | 0.07 | -344.61 | 1/7 |  |
| oa_crosscheck_v1-387@s5 | QQQ | orb60 | P | 20/20 | oa1m | d40-55t45 | vixy_falling | 43 | 44.20 | -7.43 | 0.69 | 0.21 | -402.30 | 2/7 |  |
| oa_crosscheck_v1-118@s5 | QQQ | orb15 | C | 15/45 | desk | d40-55t45 | - | 207 | 15.90 | -17.28 | 0.34 | 0.12 | -3576.75 | 0/8 |  |
| oa_crosscheck_v1-119@s5 | QQQ | orb15 | C | 10/30 | desk | d40-55t45 | - | 207 | 13.50 | -16.44 | 0.21 | 0.05 | -3403.35 | 0/8 |  |
| oa_crosscheck_v1-117@s5 | QQQ | orb15 | C | 20/60 | desk | d40-55t45 | - | 207 | 17.90 | -18.33 | 0.42 | 0.19 | -3793.99 | 0/8 |  |
| oa_crosscheck_v1-116@s5 | QQQ | orb15 | C | 20/40 | desk | d40-55t45 | - | 207 | 23.70 | -17.97 | 0.39 | 0.15 | -3805.85 | 0/8 |  |
| oa_crosscheck_v1-115@s5 | QQQ | orb15 | C | 20/20 | desk | d40-55t45 | - | 207 | 37.70 | -16.91 | 0.30 | 0.03 | -3502.01 | 0/8 |  |
| oa_crosscheck_v1-123@s5 | QQQ | orb15 | P | 15/45 | desk | d40-55t45 | - | 197 | 16.20 | -19.30 | 0.34 | 0.12 | -3863.05 | 0/8 |  |
| oa_crosscheck_v1-124@s5 | QQQ | orb15 | P | 10/30 | desk | d40-55t45 | - | 197 | 13.20 | -18.33 | 0.20 | 0.05 | -3642.95 | 0/8 |  |
| oa_crosscheck_v1-122@s5 | QQQ | orb15 | P | 20/60 | desk | d40-55t45 | - | 197 | 18.80 | -19.00 | 0.45 | 0.20 | -3782.73 | 1/8 |  |
| oa_crosscheck_v1-121@s5 | QQQ | orb15 | P | 20/40 | desk | d40-55t45 | - | 197 | 24.40 | -19.17 | 0.41 | 0.15 | -3913.96 | 1/8 |  |
| oa_crosscheck_v1-120@s5 | QQQ | orb15 | P | 20/20 | desk | d40-55t45 | - | 197 | 35.50 | -19.49 | 0.29 | 0.03 | -3873.79 | 0/8 |  |
| oa_crosscheck_v1-108@s5 | QQQ | orb30 | C | 15/45 | desk | d40-55t45 | - | 181 | 13.80 | -17.60 | 0.30 | 0.11 | -3185.66 | 0/8 |  |
| oa_crosscheck_v1-109@s5 | QQQ | orb30 | C | 10/30 | desk | d40-55t45 | - | 181 | 11.60 | -16.26 | 0.19 | 0.04 | -2942.98 | 0/8 |  |
| oa_crosscheck_v1-107@s5 | QQQ | orb30 | C | 20/60 | desk | d40-55t45 | - | 181 | 16.00 | -18.42 | 0.40 | 0.18 | -3333.57 | 0/8 |  |
| oa_crosscheck_v1-106@s5 | QQQ | orb30 | C | 20/40 | desk | d40-55t45 | - | 181 | 22.10 | -17.87 | 0.37 | 0.14 | -3235.05 | 0/8 |  |
| oa_crosscheck_v1-105@s5 | QQQ | orb30 | C | 20/20 | desk | d40-55t45 | - | 181 | 34.80 | -17.91 | 0.26 | 0.03 | -3241.84 | 0/8 |  |
| oa_crosscheck_v1-113@s5 | QQQ | orb30 | P | 15/45 | desk | d40-55t45 | - | 159 | 16.40 | -17.24 | 0.38 | 0.14 | -2802.91 | 0/8 |  |
| oa_crosscheck_v1-114@s5 | QQQ | orb30 | P | 10/30 | desk | d40-55t45 | - | 159 | 14.50 | -15.86 | 0.26 | 0.06 | -2554.03 | 0/8 |  |
| oa_crosscheck_v1-112@s5 | QQQ | orb30 | P | 20/60 | desk | d40-55t45 | - | 159 | 15.10 | -22.24 | 0.36 | 0.16 | -3588.19 | 0/8 |  |
| oa_crosscheck_v1-111@s5 | QQQ | orb30 | P | 20/40 | desk | d40-55t45 | - | 159 | 21.40 | -20.29 | 0.37 | 0.14 | -3377.26 | 0/8 |  |
| oa_crosscheck_v1-110@s5 | QQQ | orb30 | P | 20/20 | desk | d40-55t45 | - | 159 | 33.30 | -20.44 | 0.26 | 0.03 | -3284.85 | 0/8 |  |
| oa_crosscheck_v1-055@s5 | IWM | orb60 | C | 15/45 | desk | d40-55t45 | - | 67 | 11.90 | -10.28 | 0.23 | 0.09 | -757.09 | 0/8 |  |
| oa_crosscheck_v1-056@s5 | IWM | orb60 | C | 15/45 | oa1m | d40-55t45 | - | 67 | 14.90 | -11.36 | 0.26 | 0.10 | -827.55 | 0/8 |  |
| oa_crosscheck_v1-057@s5 | IWM | orb60 | C | 10/30 | desk | d40-55t45 | - | 67 | 11.90 | -8.39 | 0.19 | 0.04 | -602.47 | 0/8 |  |
| oa_crosscheck_v1-058@s5 | IWM | orb60 | C | 10/30 | oa1m | d40-55t45 | - | 67 | 16.40 | -10.28 | 0.22 | 0.07 | -730.65 | 0/8 |  |
| oa_crosscheck_v1-053@s5 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | - | 67 | 13.40 | -11.37 | 0.30 | 0.13 | -859.94 | 0/8 |  |
| oa_crosscheck_v1-054@s5 | IWM | orb60 | C | 20/60 | oa1m | d40-55t45 | - | 67 | 16.40 | -11.27 | 0.35 | 0.17 | -815.05 | 1/8 |  |
| oa_crosscheck_v1-051@s5 | IWM | orb60 | C | 20/40 | desk | d40-55t45 | - | 67 | 17.90 | -11.56 | 0.25 | 0.09 | -826.78 | 0/8 |  |
| oa_crosscheck_v1-052@s5 | IWM | orb60 | C | 20/40 | oa1m | d40-55t45 | - | 67 | 26.90 | -8.93 | 0.41 | 0.17 | -654.65 | 1/8 |  |
| oa_crosscheck_v1-059@s5 | IWM | orb60 | C | 50/100 | desk | d40-55t45 | - | 67 | 20.90 | -18.80 | 0.38 | 0.26 | -1345.55 | 1/8 |  |
| oa_crosscheck_v1-060@s5 | IWM | orb60 | C | 50/100 | oa1m | d40-55t45 | - | 67 | 23.90 | -16.79 | 0.45 | 0.31 | -1215.95 | 1/8 |  |
| oa_crosscheck_v1-081@s5 | IWM | orb60 | C | 50/100 | desk | d45-60t50 | - | 85 | 29.40 | -11.26 | 0.63 | 0.42 | -1090.91 | 2/8 |  |
| oa_crosscheck_v1-082@s5 | IWM | orb60 | C | 50/100 | oa1m | d45-60t50 | - | 85 | 30.60 | -12.25 | 0.62 | 0.41 | -1040.85 | 2/8 |  |
| oa_crosscheck_v1-049@s5 | IWM | orb60 | C | 20/20 | desk | d40-55t45 | - | 67 | 29.90 | -11.34 | 0.17 | 0.01 | -774.95 | 0/8 |  |
| oa_crosscheck_v1-050@s5 | IWM | orb60 | C | 20/20 | oa1m | d40-55t45 | - | 67 | 34.30 | -10.31 | 0.26 | 0.06 | -710.55 | 1/8 |  |
| oa_crosscheck_v1-418@s5 | IWM | orb60 | C | 15/45 | desk | d40-55t45 | gap_side_075 | 21 | 14.30 | -8.41 | 0.31 | 0.11 | -221.98 | 0/7 |  |
| oa_crosscheck_v1-420@s5 | IWM | orb60 | C | 15/45 | oa1m | d40-55t45 | gap_side_075 | 21 | 23.80 | -7.13 | 0.45 | 0.18 | -194.65 | 1/7 |  |
| oa_crosscheck_v1-422@s5 | IWM | orb60 | C | 10/30 | desk | d40-55t45 | gap_side_075 | 21 | 9.50 | -8.04 | 0.18 | 0.04 | -196.63 | 0/7 |  |
| oa_crosscheck_v1-424@s5 | IWM | orb60 | C | 10/30 | oa1m | d40-55t45 | gap_side_075 | 21 | 19.00 | -7.63 | 0.31 | 0.10 | -196.55 | 0/7 |  |
| oa_crosscheck_v1-414@s5 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | gap_side_075 | 21 | 19.00 | -7.58 | 0.46 | 0.21 | -222.28 | 1/7 |  |
| oa_crosscheck_v1-416@s5 | IWM | orb60 | C | 20/60 | oa1m | d40-55t45 | gap_side_075 | 21 | 14.30 | -13.47 | 0.23 | 0.11 | -282.80 | 1/7 |  |
| oa_crosscheck_v1-410@s5 | IWM | orb60 | C | 20/40 | desk | d40-55t45 | gap_side_075 | 21 | 28.60 | -6.50 | 0.48 | 0.18 | -176.15 | 2/7 |  |
| oa_crosscheck_v1-412@s5 | IWM | orb60 | C | 20/40 | oa1m | d40-55t45 | gap_side_075 | 21 | 28.60 | -7.04 | 0.48 | 0.20 | -184.20 | 2/7 |  |
| oa_crosscheck_v1-406@s5 | IWM | orb60 | C | 20/20 | desk | d40-55t45 | gap_side_075 | 21 | 38.10 | -8.49 | 0.25 | 0.01 | -199.61 | 1/7 |  |
| oa_crosscheck_v1-408@s5 | IWM | orb60 | C | 20/20 | oa1m | d40-55t45 | gap_side_075 | 21 | 38.10 | -8.17 | 0.33 | 0.08 | -201.20 | 1/7 |  |
| oa_crosscheck_v1-311@s5 | IWM | orb60 | C | 15/45 | desk | d40-55t45 | skip_fomc_cpi | 62 | 11.30 | -9.94 | 0.21 | 0.08 | -641.93 | 0/8 |  |
| oa_crosscheck_v1-312@s5 | IWM | orb60 | C | 15/45 | oa1m | d40-55t45 | skip_fomc_cpi | 62 | 14.50 | -11.01 | 0.24 | 0.10 | -704.70 | 1/8 |  |
| oa_crosscheck_v1-313@s5 | IWM | orb60 | C | 10/30 | desk | d40-55t45 | skip_fomc_cpi | 62 | 11.30 | -8.10 | 0.17 | 0.04 | -516.16 | 0/8 |  |
| oa_crosscheck_v1-314@s5 | IWM | orb60 | C | 10/30 | oa1m | d40-55t45 | skip_fomc_cpi | 62 | 16.10 | -10.17 | 0.20 | 0.06 | -643.90 | 0/8 |  |
| oa_crosscheck_v1-309@s5 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | skip_fomc_cpi | 62 | 12.90 | -11.02 | 0.28 | 0.12 | -722.08 | 0/8 |  |
| oa_crosscheck_v1-310@s5 | IWM | orb60 | C | 20/60 | oa1m | d40-55t45 | skip_fomc_cpi | 62 | 16.10 | -10.93 | 0.34 | 0.17 | -677.95 | 1/8 |  |
| oa_crosscheck_v1-307@s5 | IWM | orb60 | C | 20/40 | desk | d40-55t45 | skip_fomc_cpi | 62 | 17.70 | -10.87 | 0.25 | 0.09 | -688.92 | 0/8 |  |
| oa_crosscheck_v1-308@s5 | IWM | orb60 | C | 20/40 | oa1m | d40-55t45 | skip_fomc_cpi | 62 | 27.40 | -8.16 | 0.42 | 0.18 | -517.55 | 1/8 |  |
| oa_crosscheck_v1-305@s5 | IWM | orb60 | C | 20/20 | desk | d40-55t45 | skip_fomc_cpi | 62 | 30.60 | -10.28 | 0.18 | 0.01 | -637.09 | 0/8 |  |
| oa_crosscheck_v1-306@s5 | IWM | orb60 | C | 20/20 | oa1m | d40-55t45 | skip_fomc_cpi | 62 | 35.50 | -9.25 | 0.28 | 0.06 | -573.45 | 2/8 |  |
| oa_crosscheck_v1-237@s5 | IWM | orb60 | C | 15/45 | desk | d40-55t45 | sma20_side | 36 | 8.30 | -10.95 | 0.17 | 0.06 | -436.99 | 1/8 |  |
| oa_crosscheck_v1-239@s5 | IWM | orb60 | C | 15/45 | oa1m | d40-55t45 | sma20_side | 36 | 13.90 | -11.05 | 0.25 | 0.10 | -442.45 | 1/8 |  |
| oa_crosscheck_v1-241@s5 | IWM | orb60 | C | 10/30 | desk | d40-55t45 | sma20_side | 36 | 5.60 | -9.49 | 0.10 | 0.02 | -367.82 | 0/8 |  |
| oa_crosscheck_v1-243@s5 | IWM | orb60 | C | 10/30 | oa1m | d40-55t45 | sma20_side | 36 | 13.90 | -9.97 | 0.18 | 0.05 | -387.35 | 0/8 |  |
| oa_crosscheck_v1-233@s5 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | sma20_side | 36 | 11.10 | -11.78 | 0.25 | 0.11 | -483.36 | 1/8 |  |
| oa_crosscheck_v1-235@s5 | IWM | orb60 | C | 20/60 | oa1m | d40-55t45 | sma20_side | 36 | 13.90 | -11.29 | 0.32 | 0.16 | -508.20 | 2/8 |  |
| oa_crosscheck_v1-229@s5 | IWM | orb60 | C | 20/40 | desk | d40-55t45 | sma20_side | 36 | 19.40 | -10.23 | 0.28 | 0.11 | -405.42 | 0/8 |  |
| oa_crosscheck_v1-231@s5 | IWM | orb60 | C | 20/40 | oa1m | d40-55t45 | sma20_side | 36 | 27.80 | -7.99 | 0.44 | 0.18 | -365.70 | 1/8 |  |
| oa_crosscheck_v1-225@s5 | IWM | orb60 | C | 20/20 | desk | d40-55t45 | sma20_side | 36 | 27.80 | -10.98 | 0.16 | 0.01 | -410.30 | 0/8 |  |
| oa_crosscheck_v1-227@s5 | IWM | orb60 | C | 20/20 | oa1m | d40-55t45 | sma20_side | 36 | 30.60 | -10.79 | 0.22 | 0.04 | -418.90 | 0/8 |  |
| oa_crosscheck_v1-238@s5 | IWM | orb60 | C | 15/45 | desk | d40-55t45 | sma20_side_1pct | 23 | 13.00 | -8.94 | 0.28 | 0.10 | -253.34 | 2/6 |  |
| oa_crosscheck_v1-240@s5 | IWM | orb60 | C | 15/45 | oa1m | d40-55t45 | sma20_side_1pct | 23 | 17.40 | -9.35 | 0.34 | 0.14 | -266.75 | 2/6 |  |
| oa_crosscheck_v1-242@s5 | IWM | orb60 | C | 10/30 | desk | d40-55t45 | sma20_side_1pct | 23 | 8.70 | -8.34 | 0.17 | 0.04 | -218.16 | 2/6 |  |
| oa_crosscheck_v1-244@s5 | IWM | orb60 | C | 10/30 | oa1m | d40-55t45 | sma20_side_1pct | 23 | 21.70 | -7.62 | 0.30 | 0.09 | -203.60 | 1/6 |  |
| oa_crosscheck_v1-234@s5 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | sma20_side_1pct | 23 | 17.40 | -8.37 | 0.42 | 0.19 | -251.92 | 1/6 |  |
| oa_crosscheck_v1-236@s5 | IWM | orb60 | C | 20/60 | oa1m | d40-55t45 | sma20_side_1pct | 23 | 17.40 | -9.43 | 0.41 | 0.20 | -276.75 | 1/6 |  |
| oa_crosscheck_v1-230@s5 | IWM | orb60 | C | 20/40 | desk | d40-55t45 | sma20_side_1pct | 23 | 26.10 | -7.35 | 0.43 | 0.16 | -206.25 | 1/6 |  |
| oa_crosscheck_v1-232@s5 | IWM | orb60 | C | 20/40 | oa1m | d40-55t45 | sma20_side_1pct | 23 | 34.80 | -5.67 | 0.56 | 0.23 | -175.10 | 1/6 |  |
| oa_crosscheck_v1-226@s5 | IWM | orb60 | C | 20/20 | desk | d40-55t45 | sma20_side_1pct | 23 | 34.80 | -9.06 | 0.23 | 0.01 | -223.30 | 0/6 |  |
| oa_crosscheck_v1-228@s5 | IWM | orb60 | C | 20/20 | oa1m | d40-55t45 | sma20_side_1pct | 23 | 39.10 | -8.48 | 0.32 | 0.07 | -215.00 | 1/6 |  |
| oa_crosscheck_v1-417@s5 | IWM | orb60 | C | 15/45 | desk | d40-55t45 | vixy_falling | 46 | 13.00 | -8.93 | 0.28 | 0.10 | -498.98 | 1/8 |  |
| oa_crosscheck_v1-419@s5 | IWM | orb60 | C | 15/45 | oa1m | d40-55t45 | vixy_falling | 46 | 17.40 | -9.09 | 0.33 | 0.13 | -507.45 | 2/8 |  |
| oa_crosscheck_v1-421@s5 | IWM | orb60 | C | 10/30 | desk | d40-55t45 | vixy_falling | 46 | 13.00 | -7.24 | 0.23 | 0.05 | -388.55 | 1/8 |  |
| oa_crosscheck_v1-423@s5 | IWM | orb60 | C | 10/30 | oa1m | d40-55t45 | vixy_falling | 46 | 17.40 | -8.65 | 0.26 | 0.08 | -462.80 | 1/8 |  |
| oa_crosscheck_v1-413@s5 | IWM | orb60 | C | 20/60 | desk | d40-55t45 | vixy_falling | 46 | 15.20 | -9.24 | 0.37 | 0.17 | -547.55 | 1/8 |  |
| oa_crosscheck_v1-415@s5 | IWM | orb60 | C | 20/60 | oa1m | d40-55t45 | vixy_falling | 46 | 19.60 | -8.59 | 0.45 | 0.22 | -455.00 | 2/8 |  |
| oa_crosscheck_v1-409@s5 | IWM | orb60 | C | 20/40 | desk | d40-55t45 | vixy_falling | 46 | 19.60 | -9.67 | 0.30 | 0.12 | -521.77 | 1/8 |  |
| oa_crosscheck_v1-411@s5 | IWM | orb60 | C | 20/40 | oa1m | d40-55t45 | vixy_falling | 46 | 30.40 | -5.62 | 0.57 | 0.24 | -339.30 | 2/8 |  |
| oa_crosscheck_v1-405@s5 | IWM | orb60 | C | 20/20 | desk | d40-55t45 | vixy_falling | 46 | 32.60 | -9.52 | 0.21 | 0.01 | -468.89 | 0/8 |  |
| oa_crosscheck_v1-407@s5 | IWM | orb60 | C | 20/20 | oa1m | d40-55t45 | vixy_falling | 46 | 41.30 | -6.92 | 0.39 | 0.08 | -360.20 | 2/8 |  |
| oa_crosscheck_v1-067@s5 | IWM | orb60 | P | 15/45 | desk | d40-55t45 | - | 89 | 15.70 | -9.13 | 0.34 | 0.12 | -812.87 | 0/8 |  |
| oa_crosscheck_v1-068@s5 | IWM | orb60 | P | 15/45 | oa1m | d40-55t45 | - | 89 | 19.10 | -9.63 | 0.41 | 0.18 | -881.15 | 1/8 |  |
| oa_crosscheck_v1-069@s5 | IWM | orb60 | P | 10/30 | desk | d40-55t45 | - | 89 | 15.70 | -8.27 | 0.23 | 0.05 | -751.39 | 1/8 |  |
| oa_crosscheck_v1-070@s5 | IWM | orb60 | P | 10/30 | oa1m | d40-55t45 | - | 89 | 19.10 | -8.73 | 0.33 | 0.10 | -780.45 | 0/8 |  |
| oa_crosscheck_v1-065@s5 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | - | 89 | 16.90 | -10.56 | 0.38 | 0.18 | -944.86 | 1/8 |  |
| oa_crosscheck_v1-066@s5 | IWM | orb60 | P | 20/60 | oa1m | d40-55t45 | - | 89 | 23.60 | -7.21 | 0.60 | 0.30 | -767.75 | 3/8 |  |
| oa_crosscheck_v1-063@s5 | IWM | orb60 | P | 20/40 | desk | d40-55t45 | - | 89 | 28.10 | -7.88 | 0.47 | 0.18 | -701.02 | 0/8 |  |
| oa_crosscheck_v1-064@s5 | IWM | orb60 | P | 20/40 | oa1m | d40-55t45 | - | 89 | 29.20 | -7.87 | 0.53 | 0.24 | -773.90 | 2/8 |  |
| oa_crosscheck_v1-071@s5 | IWM | orb60 | P | 50/100 | desk | d40-55t45 | - | 89 | 31.50 | -10.25 | 0.66 | 0.45 | -1229.03 | 2/8 |  |
| oa_crosscheck_v1-072@s5 | IWM | orb60 | P | 50/100 | oa1m | d40-55t45 | - | 89 | 29.20 | -11.59 | 0.64 | 0.45 | -1402.55 | 2/8 |  |
| oa_crosscheck_v1-083@s5 | IWM | orb60 | P | 50/100 | desk | d45-60t50 | - | 88 | 31.80 | -10.85 | 0.68 | 0.46 | -1385.88 | 2/8 |  |
| oa_crosscheck_v1-084@s5 | IWM | orb60 | P | 50/100 | oa1m | d45-60t50 | - | 88 | 31.80 | -10.99 | 0.69 | 0.48 | -1473.95 | 2/8 |  |
| oa_crosscheck_v1-061@s5 | IWM | orb60 | P | 20/20 | desk | d40-55t45 | - | 89 | 38.20 | -8.85 | 0.29 | 0.02 | -787.23 | 0/8 |  |
| oa_crosscheck_v1-062@s5 | IWM | orb60 | P | 20/20 | oa1m | d40-55t45 | - | 89 | 42.70 | -6.95 | 0.47 | 0.13 | -693.75 | 1/8 |  |
| oa_crosscheck_v1-438@s5 | IWM | orb60 | P | 15/45 | desk | d40-55t45 | gap_side_075 | 23 | 8.70 | -12.32 | 0.12 | 0.04 | -283.35 | 2/8 |  |
| oa_crosscheck_v1-440@s5 | IWM | orb60 | P | 15/45 | oa1m | d40-55t45 | gap_side_075 | 23 | 17.40 | -11.01 | 0.25 | 0.10 | -264.60 | 2/8 |  |
| oa_crosscheck_v1-442@s5 | IWM | orb60 | P | 10/30 | desk | d40-55t45 | gap_side_075 | 23 | 17.40 | -6.88 | 0.29 | 0.07 | -158.18 | 2/8 |  |
| oa_crosscheck_v1-444@s5 | IWM | orb60 | P | 10/30 | oa1m | d40-55t45 | gap_side_075 | 23 | 17.40 | -8.03 | 0.27 | 0.07 | -184.80 | 2/8 |  |
| oa_crosscheck_v1-434@s5 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | gap_side_075 | 23 | 8.70 | -14.72 | 0.14 | 0.07 | -338.47 | 2/8 |  |
| oa_crosscheck_v1-436@s5 | IWM | orb60 | P | 20/60 | oa1m | d40-55t45 | gap_side_075 | 23 | 13.00 | -14.44 | 0.23 | 0.11 | -332.05 | 2/8 |  |
| oa_crosscheck_v1-430@s5 | IWM | orb60 | P | 20/40 | desk | d40-55t45 | gap_side_075 | 23 | 21.70 | -9.62 | 0.34 | 0.13 | -228.30 | 2/8 |  |
| oa_crosscheck_v1-432@s5 | IWM | orb60 | P | 20/40 | oa1m | d40-55t45 | gap_side_075 | 23 | 21.70 | -12.25 | 0.28 | 0.12 | -316.60 | 1/8 |  |
| oa_crosscheck_v1-426@s5 | IWM | orb60 | P | 20/20 | desk | d40-55t45 | gap_side_075 | 23 | 26.10 | -11.59 | 0.16 | 0.01 | -266.64 | 1/8 |  |
| oa_crosscheck_v1-428@s5 | IWM | orb60 | P | 20/20 | oa1m | d40-55t45 | gap_side_075 | 23 | 34.80 | -9.77 | 0.28 | 0.06 | -233.95 | 2/8 |  |
| oa_crosscheck_v1-321@s5 | IWM | orb60 | P | 15/45 | desk | d40-55t45 | skip_fomc_cpi | 79 | 17.70 | -7.80 | 0.40 | 0.15 | -616.12 | 1/8 |  |
| oa_crosscheck_v1-322@s5 | IWM | orb60 | P | 15/45 | oa1m | d40-55t45 | skip_fomc_cpi | 79 | 21.50 | -7.87 | 0.48 | 0.21 | -646.15 | 2/8 |  |
| oa_crosscheck_v1-323@s5 | IWM | orb60 | P | 10/30 | desk | d40-55t45 | skip_fomc_cpi | 79 | 17.70 | -7.38 | 0.28 | 0.06 | -598.70 | 1/8 |  |
| oa_crosscheck_v1-324@s5 | IWM | orb60 | P | 10/30 | oa1m | d40-55t45 | skip_fomc_cpi | 79 | 21.50 | -7.50 | 0.39 | 0.12 | -595.80 | 0/8 |  |
| oa_crosscheck_v1-319@s5 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | skip_fomc_cpi | 79 | 19.00 | -8.82 | 0.46 | 0.21 | -702.40 | 1/8 |  |
| oa_crosscheck_v1-320@s5 | IWM | orb60 | P | 20/60 | oa1m | d40-55t45 | skip_fomc_cpi | 79 | 26.60 | -4.71 | 0.72 | 0.36 | -602.75 | 3/8 |  |
| oa_crosscheck_v1-317@s5 | IWM | orb60 | P | 20/40 | desk | d40-55t45 | skip_fomc_cpi | 79 | 30.40 | -6.40 | 0.54 | 0.21 | -505.25 | 2/8 |  |
| oa_crosscheck_v1-318@s5 | IWM | orb60 | P | 20/40 | oa1m | d40-55t45 | skip_fomc_cpi | 79 | 31.60 | -6.11 | 0.61 | 0.28 | -577.55 | 3/8 |  |
| oa_crosscheck_v1-315@s5 | IWM | orb60 | P | 20/20 | desk | d40-55t45 | skip_fomc_cpi | 79 | 40.50 | -7.54 | 0.34 | 0.03 | -595.36 | 1/8 |  |
| oa_crosscheck_v1-316@s5 | IWM | orb60 | P | 20/20 | oa1m | d40-55t45 | skip_fomc_cpi | 79 | 46.80 | -4.86 | 0.59 | 0.16 | -458.75 | 2/8 |  |
| oa_crosscheck_v1-257@s5 | IWM | orb60 | P | 15/45 | desk | d40-55t45 | sma20_side | 36 | 19.40 | -7.14 | 0.51 | 0.19 | -268.69 | 1/5 |  |
| oa_crosscheck_v1-259@s5 | IWM | orb60 | P | 15/45 | oa1m | d40-55t45 | sma20_side | 36 | 22.20 | -8.63 | 0.52 | 0.22 | -386.15 | 1/5 |  |
| oa_crosscheck_v1-261@s5 | IWM | orb60 | P | 10/30 | desk | d40-55t45 | sma20_side | 36 | 16.70 | -8.78 | 0.27 | 0.06 | -316.24 | 0/5 |  |
| oa_crosscheck_v1-263@s5 | IWM | orb60 | P | 10/30 | oa1m | d40-55t45 | sma20_side | 36 | 22.20 | -7.49 | 0.43 | 0.12 | -269.80 | 0/5 |  |
| oa_crosscheck_v1-253@s5 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | sma20_side | 36 | 19.40 | -8.87 | 0.53 | 0.24 | -426.30 | 1/5 |  |
| oa_crosscheck_v1-255@s5 | IWM | orb60 | P | 20/60 | oa1m | d40-55t45 | sma20_side | 36 | 25.00 | -5.99 | 0.70 | 0.36 | -474.05 | 2/5 |  |
| oa_crosscheck_v1-249@s5 | IWM | orb60 | P | 20/40 | desk | d40-55t45 | sma20_side | 36 | 33.30 | -5.31 | 0.66 | 0.26 | -233.85 | 1/5 |  |
| oa_crosscheck_v1-251@s5 | IWM | orb60 | P | 20/40 | oa1m | d40-55t45 | sma20_side | 36 | 33.30 | -6.57 | 0.64 | 0.29 | -404.85 | 2/5 |  |
| oa_crosscheck_v1-245@s5 | IWM | orb60 | P | 20/20 | desk | d40-55t45 | sma20_side | 36 | 44.40 | -7.11 | 0.42 | 0.04 | -277.51 | 0/5 |  |
| oa_crosscheck_v1-247@s5 | IWM | orb60 | P | 20/20 | oa1m | d40-55t45 | sma20_side | 36 | 50.00 | -5.30 | 0.59 | 0.14 | -231.85 | 1/5 |  |
| oa_crosscheck_v1-258@s5 | IWM | orb60 | P | 15/45 | desk | d40-55t45 | sma20_side_1pct | 27 | 18.50 | -8.02 | 0.49 | 0.18 | -237.47 | 1/5 |  |
| oa_crosscheck_v1-260@s5 | IWM | orb60 | P | 15/45 | oa1m | d40-55t45 | sma20_side_1pct | 27 | 22.20 | -7.96 | 0.56 | 0.23 | -300.70 | 1/5 |  |
| oa_crosscheck_v1-262@s5 | IWM | orb60 | P | 10/30 | desk | d40-55t45 | sma20_side_1pct | 27 | 18.50 | -8.58 | 0.31 | 0.07 | -231.60 | 0/5 |  |
| oa_crosscheck_v1-264@s5 | IWM | orb60 | P | 10/30 | oa1m | d40-55t45 | sma20_side_1pct | 27 | 22.20 | -8.31 | 0.41 | 0.12 | -224.30 | 0/5 |  |
| oa_crosscheck_v1-254@s5 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | sma20_side_1pct | 27 | 22.20 | -5.87 | 0.68 | 0.31 | -330.97 | 1/5 |  |
| oa_crosscheck_v1-256@s5 | IWM | orb60 | P | 20/60 | oa1m | d40-55t45 | sma20_side_1pct | 27 | 25.90 | -4.30 | 0.79 | 0.40 | -381.45 | 2/5 |  |
| oa_crosscheck_v1-250@s5 | IWM | orb60 | P | 20/40 | desk | d40-55t45 | sma20_side_1pct | 27 | 37.00 | -3.12 | 0.79 | 0.30 | -157.98 | 1/5 |  |
| oa_crosscheck_v1-252@s5 | IWM | orb60 | P | 20/40 | oa1m | d40-55t45 | sma20_side_1pct | 27 | 33.30 | -6.09 | 0.68 | 0.30 | -317.25 | 2/5 |  |
| oa_crosscheck_v1-246@s5 | IWM | orb60 | P | 20/20 | desk | d40-55t45 | sma20_side_1pct | 27 | 40.70 | -8.76 | 0.37 | 0.03 | -236.41 | 0/5 |  |
| oa_crosscheck_v1-248@s5 | IWM | orb60 | P | 20/20 | oa1m | d40-55t45 | sma20_side_1pct | 27 | 48.10 | -6.86 | 0.54 | 0.13 | -209.25 | 1/5 |  |
| oa_crosscheck_v1-437@s5 | IWM | orb60 | P | 15/45 | desk | d40-55t45 | vixy_falling | 31 | 16.10 | -7.70 | 0.41 | 0.15 | -246.49 | 1/7 |  |
| oa_crosscheck_v1-439@s5 | IWM | orb60 | P | 15/45 | oa1m | d40-55t45 | vixy_falling | 31 | 16.10 | -8.86 | 0.44 | 0.19 | -295.65 | 1/7 |  |
| oa_crosscheck_v1-441@s5 | IWM | orb60 | P | 10/30 | desk | d40-55t45 | vixy_falling | 31 | 12.90 | -7.53 | 0.27 | 0.06 | -234.88 | 1/7 |  |
| oa_crosscheck_v1-443@s5 | IWM | orb60 | P | 10/30 | oa1m | d40-55t45 | vixy_falling | 31 | 16.10 | -10.36 | 0.23 | 0.07 | -321.30 | 1/7 |  |
| oa_crosscheck_v1-433@s5 | IWM | orb60 | P | 20/60 | desk | d40-55t45 | vixy_falling | 31 | 22.60 | -5.62 | 0.62 | 0.28 | -211.95 | 2/7 |  |
| oa_crosscheck_v1-435@s5 | IWM | orb60 | P | 20/60 | oa1m | d40-55t45 | vixy_falling | 31 | 22.60 | -6.87 | 0.61 | 0.31 | -242.35 | 2/7 |  |
| oa_crosscheck_v1-429@s5 | IWM | orb60 | P | 20/40 | desk | d40-55t45 | vixy_falling | 31 | 29.00 | -5.43 | 0.59 | 0.22 | -181.82 | 1/7 |  |
| oa_crosscheck_v1-431@s5 | IWM | orb60 | P | 20/40 | oa1m | d40-55t45 | vixy_falling | 31 | 25.80 | -8.80 | 0.48 | 0.22 | -277.50 | 0/7 |  |
| oa_crosscheck_v1-425@s5 | IWM | orb60 | P | 20/20 | desk | d40-55t45 | vixy_falling | 31 | 41.90 | -7.18 | 0.36 | 0.03 | -232.01 | 0/7 |  |
| oa_crosscheck_v1-427@s5 | IWM | orb60 | P | 20/20 | oa1m | d40-55t45 | vixy_falling | 31 | 32.30 | -10.30 | 0.32 | 0.08 | -319.35 | 1/7 |  |
| oa_crosscheck_v1-138@s5 | IWM | orb15 | C | 15/45 | desk | d40-55t45 | - | 141 | 21.30 | -6.82 | 0.50 | 0.18 | -1069.97 | 1/8 |  |
| oa_crosscheck_v1-139@s5 | IWM | orb15 | C | 10/30 | desk | d40-55t45 | - | 141 | 21.30 | -6.52 | 0.38 | 0.09 | -919.15 | 0/8 |  |
| oa_crosscheck_v1-137@s5 | IWM | orb15 | C | 20/60 | desk | d40-55t45 | - | 141 | 19.90 | -7.75 | 0.54 | 0.25 | -1266.18 | 1/8 |  |
| oa_crosscheck_v1-136@s5 | IWM | orb15 | C | 20/40 | desk | d40-55t45 | - | 141 | 28.40 | -7.27 | 0.52 | 0.20 | -1136.79 | 2/8 |  |
| oa_crosscheck_v1-135@s5 | IWM | orb15 | C | 20/20 | desk | d40-55t45 | - | 141 | 46.10 | -6.78 | 0.42 | 0.04 | -955.62 | 1/8 |  |
| oa_crosscheck_v1-143@s5 | IWM | orb15 | P | 15/45 | desk | d40-55t45 | - | 155 | 21.30 | -7.93 | 0.45 | 0.16 | -1264.89 | 0/8 |  |
| oa_crosscheck_v1-144@s5 | IWM | orb15 | P | 10/30 | desk | d40-55t45 | - | 155 | 19.40 | -7.30 | 0.34 | 0.08 | -1154.03 | 0/8 |  |
| oa_crosscheck_v1-142@s5 | IWM | orb15 | P | 20/60 | desk | d40-55t45 | - | 155 | 21.90 | -8.31 | 0.53 | 0.24 | -1400.19 | 2/8 |  |
| oa_crosscheck_v1-141@s5 | IWM | orb15 | P | 20/40 | desk | d40-55t45 | - | 155 | 29.70 | -8.05 | 0.49 | 0.19 | -1278.99 | 0/8 |  |
| oa_crosscheck_v1-140@s5 | IWM | orb15 | P | 20/20 | desk | d40-55t45 | - | 155 | 43.20 | -7.69 | 0.38 | 0.03 | -1236.73 | 0/8 |  |
| oa_crosscheck_v1-128@s5 | IWM | orb30 | C | 15/45 | desk | d40-55t45 | - | 112 | 20.50 | -7.33 | 0.44 | 0.16 | -881.14 | 2/8 |  |
| oa_crosscheck_v1-129@s5 | IWM | orb30 | C | 10/30 | desk | d40-55t45 | - | 112 | 17.90 | -7.50 | 0.29 | 0.07 | -866.38 | 0/8 |  |
| oa_crosscheck_v1-127@s5 | IWM | orb30 | C | 20/60 | desk | d40-55t45 | - | 112 | 23.20 | -6.06 | 0.61 | 0.28 | -775.61 | 2/8 |  |
| oa_crosscheck_v1-126@s5 | IWM | orb30 | C | 20/40 | desk | d40-55t45 | - | 112 | 29.50 | -7.02 | 0.51 | 0.19 | -845.57 | 1/8 |  |
| oa_crosscheck_v1-125@s5 | IWM | orb30 | C | 20/20 | desk | d40-55t45 | - | 112 | 42.90 | -8.01 | 0.33 | 0.03 | -963.16 | 0/8 |  |
| oa_crosscheck_v1-133@s5 | IWM | orb30 | P | 15/45 | desk | d40-55t45 | - | 128 | 21.10 | -7.78 | 0.45 | 0.16 | -995.92 | 1/8 |  |
| oa_crosscheck_v1-134@s5 | IWM | orb30 | P | 10/30 | desk | d40-55t45 | - | 128 | 16.40 | -7.73 | 0.30 | 0.07 | -989.86 | 0/8 |  |
| oa_crosscheck_v1-132@s5 | IWM | orb30 | P | 20/60 | desk | d40-55t45 | - | 128 | 25.00 | -6.09 | 0.63 | 0.29 | -787.73 | 2/8 |  |
| oa_crosscheck_v1-131@s5 | IWM | orb30 | P | 20/40 | desk | d40-55t45 | - | 128 | 31.20 | -7.00 | 0.54 | 0.20 | -895.56 | 0/8 |  |
| oa_crosscheck_v1-130@s5 | IWM | orb30 | P | 20/20 | desk | d40-55t45 | - | 128 | 39.80 | -8.70 | 0.33 | 0.03 | -1161.34 | 0/8 |  |


## Robustness on the top 5 runs

### oa_crosscheck_v1-024@s5: SPY orb60 P fixed 50/100 oa1m d40-55t45

Trades 124, win 37%, avg win 137.84, avg loss -79.30, expectancy **1.25** (2x slippage -17.47), PF 1.02 (2x 0.71), max DD -1456.00, % of peak kept 0.20, planned R:R - vs actual 0.01, expectancy CI95 [-18.4, 22.97], deflated Sharpe 0.000 (N=1366).

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
| Aug-Dec 2024 | 43 | 432.10 | 10.05 | 1.24 |
| 2025 (Jan 01-Oct 29) | 81 | -277.05 | -3.42 | 0.94 |
| 2m: Aug 2024-Sep 2024 | 22 | 276.30 | 12.56 | 1.26 |
| 2m: Oct 2024-Nov 2024 | 14 | 143.75 | 10.27 | 1.31 |
| 2m: Dec 2024-Jan 2025 | 14 | -310.80 | -22.20 | 0.56 |
| 2m: Feb 2025-Mar 2025 | 14 | -301.30 | -21.52 | 0.69 |
| 2m: Apr 2025-May 2025 | 18 | 598.05 | 33.22 | 1.48 |
| 2m: Jun 2025-Jul 2025 | 16 | -388.70 | -24.29 | 0.48 |
| 2m: Aug 2025-Sep 2025 | 17 | -265.30 | -15.61 | 0.66 |
| 2m: Oct 2025-Nov 2025 | 9 | 403.05 | 44.78 | 2.78 |


Sides: calls n=0 exp - PF -; puts n=124 exp 1.25 PF 1.02
Symbols: SPY n=124 exp 1.25 PF 1.02
Without the best 5 trades: net -1444.30, expectancy -12.14.
One-step nudges: entry=orb30 n=170 PF 0.90 exp -5.61; allout=15:50 n=124 PF 0.98 exp -1.02; fixed_stop=0.4 n=124 PF 0.95 exp -2.07; fixed_stop=0.6 n=124 PF 1.00 exp 0.21; fixed_target=0.9 n=124 PF 0.99 exp -0.35; fixed_target=1.25 n=124 PF 0.87 exp -7.24
Matched random entries (5 paths): expectancy 30.68, 5.22, 3.88, 13.49, 2.85; the run beats 0% of paths.
Exit reasons: {'FIXED STOP': 76, 'FIXED TARGET': 42, 'ALL OUT': 6}.
Median option MFE 0.497, MAE -0.518; median stock MFE $1.370; median distance from the stock's price at the option's peak to the nearest level $0.110; median minutes held 58.0.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 4.

### oa_crosscheck_v1-048@s5: QQQ orb60 P fixed 50/100 oa1m d40-55t45

Trades 111, win 32%, avg win 166.42, avg loss -83.62, expectancy **-2.52** (2x slippage -22.74), PF 0.95 (2x 0.67), max DD -1165.60, % of peak kept 0.09, planned R:R - vs actual -0.06, expectancy CI95 [-23.73, 21.58], deflated Sharpe 0.000 (N=1366).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 3 of 8 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 39 | -123.95 | -3.18 | 0.94 |
| 2025 (Jan 01-Oct 29) | 72 | -156.20 | -2.17 | 0.96 |
| 2m: Aug 2024-Sep 2024 | 22 | -296.15 | -13.46 | 0.79 |
| 2m: Oct 2024-Nov 2024 | 12 | 3.95 | 0.33 | 1.01 |
| 2m: Dec 2024-Jan 2025 | 11 | -125.70 | -11.43 | 0.79 |
| 2m: Feb 2025-Mar 2025 | 13 | -152.30 | -11.72 | 0.84 |
| 2m: Apr 2025-May 2025 | 16 | 523.10 | 32.69 | 1.48 |
| 2m: Jun 2025-Jul 2025 | 13 | -92.50 | -7.12 | 0.84 |
| 2m: Aug 2025-Sep 2025 | 15 | -252.10 | -16.81 | 0.67 |
| 2m: Oct 2025-Nov 2025 | 9 | 111.55 | 12.39 | 1.29 |


Sides: calls n=0 exp - PF -; puts n=111 exp -2.52 PF 0.95
Symbols: QQQ n=111 exp -2.52 PF 0.95
Without the best 5 trades: net -1844.55, expectancy -17.40.
One-step nudges: entry=orb30 n=159 PF 0.76 exp -15.03; allout=15:50 n=111 PF 0.95 exp -3.09; fixed_stop=0.4 n=111 PF 0.93 exp -3.59; fixed_stop=0.6 n=111 PF 0.95 exp -3.23; fixed_target=0.9 n=111 PF 0.89 exp -6.32; fixed_target=1.25 n=111 PF 0.74 exp -15.82
Matched random entries (5 paths): expectancy 11.93, -2.58, 19.55, 4.60, 3.60; the run beats 20% of paths.
Exit reasons: {'FIXED STOP': 73, 'FIXED TARGET': 36, 'ALL OUT': 2}.
Median option MFE 0.581, MAE -0.517; median stock MFE $1.620; median distance from the stock's price at the option's peak to the nearest level $0.140; median minutes held 51.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 1.

### oa_crosscheck_v1-079@s5: QQQ orb60 P fixed 50/100 desk d45-60t50

Trades 110, win 34%, avg win 168.40, avg loss -92.92, expectancy **-2.65** (2x slippage -26.49), PF 0.96 (2x 0.65), max DD -1270.48, % of peak kept 0.10, planned R:R - vs actual -0.06, expectancy CI95 [-26.69, 23.13], deflated Sharpe 0.000 (N=1366).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 2 of 8 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 39 | 90.85 | 2.33 | 1.04 |
| 2025 (Jan 01-Oct 29) | 71 | -381.90 | -5.38 | 0.92 |
| 2m: Aug 2024-Sep 2024 | 22 | -133.96 | -6.09 | 0.91 |
| 2m: Oct 2024-Nov 2024 | 12 | -129.78 | -10.81 | 0.79 |
| 2m: Dec 2024-Jan 2025 | 11 | 21.87 | 1.99 | 1.03 |
| 2m: Feb 2025-Mar 2025 | 13 | -1.21 | -0.09 | 1.00 |
| 2m: Apr 2025-May 2025 | 16 | 434.68 | 27.17 | 1.36 |
| 2m: Jun 2025-Jul 2025 | 12 | -79.39 | -6.62 | 0.85 |
| 2m: Aug 2025-Sep 2025 | 15 | -347.65 | -23.18 | 0.57 |
| 2m: Oct 2025-Nov 2025 | 9 | -55.61 | -6.18 | 0.86 |


Sides: calls n=0 exp - PF -; puts n=110 exp -2.65 PF 0.96
Symbols: QQQ n=110 exp -2.65 PF 0.96
Without the best 5 trades: net -1890.12, expectancy -18.00.
One-step nudges: entry=orb30 n=160 PF 0.71 exp -20.65; allout=15:50 n=110 PF 0.95 exp -3.20; fixed_stop=0.4 n=110 PF 0.86 exp -7.54; fixed_stop=0.6 n=110 PF 0.87 exp -8.92; fixed_target=0.9 n=110 PF 0.88 exp -7.18; fixed_target=1.25 n=110 PF 0.77 exp -15.21
Matched random entries (5 paths): expectancy 13.58, -4.61, 28.32, 0.80, -3.43; the run beats 40% of paths.
Exit reasons: {'FIXED STOP': 70, 'FIXED TARGET': 38, 'ALL OUT': 2}.
Median option MFE 0.576, MAE -0.509; median stock MFE $1.775; median distance from the stock's price at the option's peak to the nearest level $0.140; median minutes held 57.5.
Skipped signals: no contract with BS-EST |delta| in 0.45-0.60 2.

### oa_crosscheck_v1-023@s5: SPY orb60 P fixed 50/100 desk d40-55t45

Trades 124, win 36%, avg win 127.84, avg loss -75.68, expectancy **-3.46** (2x slippage -22.27), PF 0.93 (2x 0.63), max DD -1502.09, % of peak kept 0.16, planned R:R - vs actual -0.07, expectancy CI95 [-21.86, 16.11], deflated Sharpe 0.000 (N=1366).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 3 of 8 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 43 | 399.22 | 9.28 | 1.24 |
| 2025 (Jan 01-Oct 29) | 81 | -828.70 | -10.23 | 0.81 |
| 2m: Aug 2024-Sep 2024 | 22 | 317.93 | 14.45 | 1.33 |
| 2m: Oct 2024-Nov 2024 | 14 | 70.31 | 5.02 | 1.16 |
| 2m: Dec 2024-Jan 2025 | 14 | -311.49 | -22.25 | 0.54 |
| 2m: Feb 2025-Mar 2025 | 14 | -296.49 | -21.18 | 0.68 |
| 2m: Apr 2025-May 2025 | 18 | 570.70 | 31.71 | 1.47 |
| 2m: Jun 2025-Jul 2025 | 16 | -382.03 | -23.88 | 0.47 |
| 2m: Aug 2025-Sep 2025 | 17 | -283.94 | -16.70 | 0.62 |
| 2m: Oct 2025-Nov 2025 | 9 | -114.47 | -12.72 | 0.68 |


Sides: calls n=0 exp - PF -; puts n=124 exp -3.46 PF 0.93
Symbols: SPY n=124 exp -3.46 PF 0.93
Without the best 5 trades: net -1880.18, expectancy -15.80.
One-step nudges: entry=orb30 n=170 PF 0.78 exp -11.69; allout=15:50 n=124 PF 0.92 exp -3.76; fixed_stop=0.4 n=124 PF 0.90 exp -4.49; fixed_stop=0.6 n=124 PF 0.93 exp -3.79; fixed_target=0.9 n=124 PF 0.93 exp -3.21; fixed_target=1.25 n=124 PF 0.80 exp -10.59
Matched random entries (5 paths): expectancy 23.68, 3.64, 3.74, 9.99, -1.24; the run beats 0% of paths.
Exit reasons: {'FIXED STOP': 78, 'FIXED TARGET': 43, 'ALL OUT': 3}.
Median option MFE 0.446, MAE -0.508; median stock MFE $1.250; median distance from the stock's price at the option's peak to the nearest level $0.100; median minutes held 50.0.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 4.

### oa_crosscheck_v1-047@s5: QQQ orb60 P fixed 50/100 desk d40-55t45

Trades 111, win 33%, avg win 145.13, avg loss -79.32, expectancy **-4.50** (2x slippage -24.86), PF 0.92 (2x 0.62), max DD -1180.21, % of peak kept 0.08, planned R:R - vs actual -0.10, expectancy CI95 [-24.02, 16.96], deflated Sharpe 0.000 (N=1366).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 2 of 8 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 39 | -201.66 | -5.17 | 0.90 |
| 2025 (Jan 01-Oct 29) | 72 | -298.03 | -4.14 | 0.92 |
| 2m: Aug 2024-Sep 2024 | 22 | -265.05 | -12.05 | 0.80 |
| 2m: Oct 2024-Nov 2024 | 12 | -75.72 | -6.31 | 0.85 |
| 2m: Dec 2024-Jan 2025 | 11 | 58.38 | 5.31 | 1.12 |
| 2m: Feb 2025-Mar 2025 | 13 | -151.33 | -11.64 | 0.83 |
| 2m: Apr 2025-May 2025 | 16 | 440.87 | 27.55 | 1.43 |
| 2m: Jun 2025-Jul 2025 | 13 | -143.37 | -11.03 | 0.74 |
| 2m: Aug 2025-Sep 2025 | 15 | -314.55 | -20.97 | 0.58 |
| 2m: Oct 2025-Nov 2025 | 9 | -48.92 | -5.44 | 0.87 |


Sides: calls n=0 exp - PF -; puts n=111 exp -4.50 PF 0.92
Symbols: QQQ n=111 exp -4.50 PF 0.92
Without the best 5 trades: net -1884.24, expectancy -17.78.
One-step nudges: entry=orb30 n=159 PF 0.74 exp -15.42; allout=15:50 n=111 PF 0.91 exp -5.01; fixed_stop=0.4 n=111 PF 0.71 exp -14.21; fixed_stop=0.6 n=111 PF 0.83 exp -10.18; fixed_target=0.9 n=111 PF 0.90 exp -5.20; fixed_target=1.25 n=111 PF 0.84 exp -9.23
Matched random entries (5 paths): expectancy 17.10, -7.84, 19.25, 2.49, -0.52; the run beats 20% of paths.
Exit reasons: {'FIXED STOP': 72, 'FIXED TARGET': 37, 'ALL OUT': 2}.
Median option MFE 0.577, MAE -0.510; median stock MFE $1.560; median distance from the stock's price at the option's peak to the nearest level $0.134; median minutes held 45.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 1.

## Filters vs random day-skips (every filtered run with its unfiltered twin)

| run | config | twin | days skipped | filtered exp | random-skip exp | p |
|---|---|---|---|---|---|---|
| oa_crosscheck_v1-145@s5 | SPY orb60 C fixed 20/20 desk d40-55t45 sma20_side | oa_crosscheck_v1-001@s5 | 43 | -12.16 | -12.83 | 0.32 |
| oa_crosscheck_v1-146@s5 | SPY orb60 C fixed 20/20 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-001@s5 | 72 | -12.33 | -12.81 | 0.40 |
| oa_crosscheck_v1-147@s5 | SPY orb60 C fixed 20/20 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-002@s5 | 43 | -9.97 | -11.37 | 0.21 |
| oa_crosscheck_v1-148@s5 | SPY orb60 C fixed 20/20 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-002@s5 | 72 | -9.82 | -11.38 | 0.29 |
| oa_crosscheck_v1-149@s5 | SPY orb60 C fixed 20/40 desk d40-55t45 sma20_side | oa_crosscheck_v1-003@s5 | 43 | -15.56 | -15.33 | 0.56 |
| oa_crosscheck_v1-150@s5 | SPY orb60 C fixed 20/40 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-003@s5 | 72 | -15.75 | -15.26 | 0.58 |
| oa_crosscheck_v1-151@s5 | SPY orb60 C fixed 20/40 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-004@s5 | 43 | -14.53 | -17.12 | 0.09 |
| oa_crosscheck_v1-152@s5 | SPY orb60 C fixed 20/40 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-004@s5 | 72 | -14.20 | -17.13 | 0.20 |
| oa_crosscheck_v1-153@s5 | SPY orb60 C fixed 20/60 desk d40-55t45 sma20_side | oa_crosscheck_v1-005@s5 | 43 | -15.77 | -17.97 | 0.11 |
| oa_crosscheck_v1-154@s5 | SPY orb60 C fixed 20/60 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-005@s5 | 72 | -15.95 | -17.92 | 0.24 |
| oa_crosscheck_v1-155@s5 | SPY orb60 C fixed 20/60 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-006@s5 | 43 | -16.56 | -17.90 | 0.34 |
| oa_crosscheck_v1-156@s5 | SPY orb60 C fixed 20/60 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-006@s5 | 72 | -18.46 | -17.69 | 0.56 |
| oa_crosscheck_v1-157@s5 | SPY orb60 C fixed 15/45 desk d40-55t45 sma20_side | oa_crosscheck_v1-007@s5 | 43 | -13.88 | -16.15 | 0.04 |
| oa_crosscheck_v1-158@s5 | SPY orb60 C fixed 15/45 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-007@s5 | 72 | -12.29 | -16.16 | 0.03 |
| oa_crosscheck_v1-159@s5 | SPY orb60 C fixed 15/45 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-008@s5 | 43 | -13.81 | -16.90 | 0.04 |
| oa_crosscheck_v1-160@s5 | SPY orb60 C fixed 15/45 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-008@s5 | 72 | -12.21 | -16.90 | 0.06 |
| oa_crosscheck_v1-161@s5 | SPY orb60 C fixed 10/30 desk d40-55t45 sma20_side | oa_crosscheck_v1-009@s5 | 43 | -11.62 | -13.43 | 0.01 |
| oa_crosscheck_v1-162@s5 | SPY orb60 C fixed 10/30 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-009@s5 | 72 | -11.75 | -13.46 | 0.13 |
| oa_crosscheck_v1-163@s5 | SPY orb60 C fixed 10/30 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-010@s5 | 43 | -13.30 | -15.55 | 0.02 |
| oa_crosscheck_v1-164@s5 | SPY orb60 C fixed 10/30 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-010@s5 | 72 | -13.24 | -15.64 | 0.09 |
| oa_crosscheck_v1-165@s5 | SPY orb60 P fixed 20/20 desk d40-55t45 sma20_side | oa_crosscheck_v1-013@s5 | 93 | -8.65 | -11.08 | 0.30 |
| oa_crosscheck_v1-166@s5 | SPY orb60 P fixed 20/20 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-013@s5 | 100 | -7.43 | -11.60 | 0.22 |
| oa_crosscheck_v1-167@s5 | SPY orb60 P fixed 20/20 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-014@s5 | 93 | -10.31 | -13.55 | 0.32 |
| oa_crosscheck_v1-168@s5 | SPY orb60 P fixed 20/20 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-014@s5 | 100 | -8.67 | -14.13 | 0.21 |
| oa_crosscheck_v1-169@s5 | SPY orb60 P fixed 20/40 desk d40-55t45 sma20_side | oa_crosscheck_v1-015@s5 | 93 | -17.85 | -16.00 | 0.63 |
| oa_crosscheck_v1-170@s5 | SPY orb60 P fixed 20/40 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-015@s5 | 100 | -18.80 | -16.87 | 0.60 |
| oa_crosscheck_v1-171@s5 | SPY orb60 P fixed 20/40 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-016@s5 | 93 | -18.64 | -15.85 | 0.64 |
| oa_crosscheck_v1-172@s5 | SPY orb60 P fixed 20/40 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-016@s5 | 100 | -23.08 | -17.16 | 0.74 |
| oa_crosscheck_v1-173@s5 | SPY orb60 P fixed 20/60 desk d40-55t45 sma20_side | oa_crosscheck_v1-017@s5 | 93 | -12.31 | -15.83 | 0.29 |
| oa_crosscheck_v1-174@s5 | SPY orb60 P fixed 20/60 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-017@s5 | 100 | -10.12 | -16.61 | 0.24 |
| oa_crosscheck_v1-175@s5 | SPY orb60 P fixed 20/60 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-018@s5 | 93 | -9.05 | -15.22 | 0.23 |
| oa_crosscheck_v1-176@s5 | SPY orb60 P fixed 20/60 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-018@s5 | 100 | -10.37 | -16.24 | 0.29 |
| oa_crosscheck_v1-177@s5 | SPY orb60 P fixed 15/45 desk d40-55t45 sma20_side | oa_crosscheck_v1-019@s5 | 93 | -27.37 | -17.30 | 0.99 |
| oa_crosscheck_v1-178@s5 | SPY orb60 P fixed 15/45 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-019@s5 | 100 | -33.27 | -17.66 | 0.99 |
| oa_crosscheck_v1-179@s5 | SPY orb60 P fixed 15/45 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-020@s5 | 93 | -13.50 | -15.44 | 0.37 |
| oa_crosscheck_v1-180@s5 | SPY orb60 P fixed 15/45 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-020@s5 | 100 | -15.64 | -15.95 | 0.47 |
| oa_crosscheck_v1-181@s5 | SPY orb60 P fixed 10/30 desk d40-55t45 sma20_side | oa_crosscheck_v1-021@s5 | 93 | -21.92 | -13.26 | 0.99 |
| oa_crosscheck_v1-182@s5 | SPY orb60 P fixed 10/30 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-021@s5 | 100 | -26.04 | -13.52 | 1.00 |
| oa_crosscheck_v1-183@s5 | SPY orb60 P fixed 10/30 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-022@s5 | 93 | -14.78 | -13.09 | 0.62 |
| oa_crosscheck_v1-184@s5 | SPY orb60 P fixed 10/30 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-022@s5 | 100 | -16.82 | -13.50 | 0.69 |
| oa_crosscheck_v1-185@s5 | QQQ orb60 C fixed 20/20 desk d40-55t45 sma20_side | oa_crosscheck_v1-025@s5 | 46 | -15.33 | -17.75 | 0.05 |
| oa_crosscheck_v1-186@s5 | QQQ orb60 C fixed 20/20 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-025@s5 | 74 | -12.77 | -17.68 | 0.02 |
| oa_crosscheck_v1-187@s5 | QQQ orb60 C fixed 20/20 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-026@s5 | 46 | -14.40 | -16.22 | 0.18 |
| oa_crosscheck_v1-188@s5 | QQQ orb60 C fixed 20/20 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-026@s5 | 74 | -12.80 | -16.06 | 0.12 |
| oa_crosscheck_v1-189@s5 | QQQ orb60 C fixed 20/40 desk d40-55t45 sma20_side | oa_crosscheck_v1-027@s5 | 46 | -17.16 | -17.47 | 0.47 |
| oa_crosscheck_v1-190@s5 | QQQ orb60 C fixed 20/40 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-027@s5 | 74 | -15.45 | -17.47 | 0.25 |
| oa_crosscheck_v1-191@s5 | QQQ orb60 C fixed 20/40 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-028@s5 | 46 | -14.73 | -16.96 | 0.19 |
| oa_crosscheck_v1-192@s5 | QQQ orb60 C fixed 20/40 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-028@s5 | 74 | -12.92 | -16.96 | 0.14 |
| oa_crosscheck_v1-193@s5 | QQQ orb60 C fixed 20/60 desk d40-55t45 sma20_side | oa_crosscheck_v1-029@s5 | 46 | -16.74 | -20.26 | 0.04 |
| oa_crosscheck_v1-194@s5 | QQQ orb60 C fixed 20/60 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-029@s5 | 74 | -14.79 | -20.33 | 0.05 |
| oa_crosscheck_v1-195@s5 | QQQ orb60 C fixed 20/60 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-030@s5 | 46 | -17.02 | -21.87 | 0.02 |
| oa_crosscheck_v1-196@s5 | QQQ orb60 C fixed 20/60 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-030@s5 | 74 | -14.21 | -21.94 | 0.02 |
| oa_crosscheck_v1-197@s5 | QQQ orb60 C fixed 15/45 desk d40-55t45 sma20_side | oa_crosscheck_v1-031@s5 | 46 | -13.77 | -15.95 | 0.07 |
| oa_crosscheck_v1-198@s5 | QQQ orb60 C fixed 15/45 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-031@s5 | 74 | -11.96 | -15.86 | 0.07 |
| oa_crosscheck_v1-199@s5 | QQQ orb60 C fixed 15/45 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-032@s5 | 46 | -15.67 | -18.75 | 0.05 |
| oa_crosscheck_v1-200@s5 | QQQ orb60 C fixed 15/45 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-032@s5 | 74 | -14.62 | -18.73 | 0.09 |
| oa_crosscheck_v1-201@s5 | QQQ orb60 C fixed 10/30 desk d40-55t45 sma20_side | oa_crosscheck_v1-033@s5 | 46 | -12.51 | -14.48 | 0.02 |
| oa_crosscheck_v1-202@s5 | QQQ orb60 C fixed 10/30 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-033@s5 | 74 | -11.91 | -14.41 | 0.06 |
| oa_crosscheck_v1-203@s5 | QQQ orb60 C fixed 10/30 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-034@s5 | 46 | -14.18 | -15.75 | 0.15 |
| oa_crosscheck_v1-204@s5 | QQQ orb60 C fixed 10/30 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-034@s5 | 74 | -12.53 | -15.68 | 0.09 |
| oa_crosscheck_v1-205@s5 | QQQ orb60 P fixed 20/20 desk d40-55t45 sma20_side | oa_crosscheck_v1-037@s5 | 81 | -18.48 | -11.73 | 0.92 |
| oa_crosscheck_v1-206@s5 | QQQ orb60 P fixed 20/20 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-037@s5 | 89 | -20.11 | -11.91 | 0.91 |
| oa_crosscheck_v1-207@s5 | QQQ orb60 P fixed 20/20 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-038@s5 | 81 | -9.88 | -11.65 | 0.40 |
| oa_crosscheck_v1-208@s5 | QQQ orb60 P fixed 20/20 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-038@s5 | 89 | -6.88 | -11.93 | 0.26 |
| oa_crosscheck_v1-209@s5 | QQQ orb60 P fixed 20/40 desk d40-55t45 sma20_side | oa_crosscheck_v1-039@s5 | 81 | -8.93 | -10.91 | 0.39 |
| oa_crosscheck_v1-210@s5 | QQQ orb60 P fixed 20/40 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-039@s5 | 89 | -10.26 | -10.80 | 0.47 |
| oa_crosscheck_v1-211@s5 | QQQ orb60 P fixed 20/40 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-040@s5 | 81 | -12.66 | -12.74 | 0.49 |
| oa_crosscheck_v1-212@s5 | QQQ orb60 P fixed 20/40 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-040@s5 | 89 | -12.84 | -12.98 | 0.47 |
| oa_crosscheck_v1-213@s5 | QQQ orb60 P fixed 20/60 desk d40-55t45 sma20_side | oa_crosscheck_v1-041@s5 | 81 | -5.47 | -11.34 | 0.25 |
| oa_crosscheck_v1-214@s5 | QQQ orb60 P fixed 20/60 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-041@s5 | 89 | -10.76 | -11.30 | 0.45 |
| oa_crosscheck_v1-215@s5 | QQQ orb60 P fixed 20/60 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-042@s5 | 81 | -7.76 | -14.11 | 0.27 |
| oa_crosscheck_v1-216@s5 | QQQ orb60 P fixed 20/60 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-042@s5 | 89 | -2.39 | -14.63 | 0.16 |
| oa_crosscheck_v1-217@s5 | QQQ orb60 P fixed 15/45 desk d40-55t45 sma20_side | oa_crosscheck_v1-043@s5 | 81 | -25.43 | -17.88 | 0.94 |
| oa_crosscheck_v1-218@s5 | QQQ orb60 P fixed 15/45 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-043@s5 | 89 | -29.84 | -18.25 | 0.98 |
| oa_crosscheck_v1-219@s5 | QQQ orb60 P fixed 15/45 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-044@s5 | 81 | -12.13 | -15.22 | 0.34 |
| oa_crosscheck_v1-220@s5 | QQQ orb60 P fixed 15/45 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-044@s5 | 89 | -17.98 | -15.54 | 0.57 |
| oa_crosscheck_v1-221@s5 | QQQ orb60 P fixed 10/30 desk d40-55t45 sma20_side | oa_crosscheck_v1-045@s5 | 81 | -20.75 | -15.84 | 0.92 |
| oa_crosscheck_v1-222@s5 | QQQ orb60 P fixed 10/30 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-045@s5 | 89 | -23.72 | -16.08 | 0.98 |
| oa_crosscheck_v1-223@s5 | QQQ orb60 P fixed 10/30 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-046@s5 | 81 | -22.20 | -16.43 | 0.87 |
| oa_crosscheck_v1-224@s5 | QQQ orb60 P fixed 10/30 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-046@s5 | 89 | -22.78 | -16.81 | 0.80 |
| oa_crosscheck_v1-225@s5 | IWM orb60 C fixed 20/20 desk d40-55t45 sma20_side | oa_crosscheck_v1-049@s5 | 31 | -10.98 | -11.40 | 0.42 |
| oa_crosscheck_v1-226@s5 | IWM orb60 C fixed 20/20 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-049@s5 | 44 | -9.06 | -11.29 | 0.18 |
| oa_crosscheck_v1-227@s5 | IWM orb60 C fixed 20/20 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-050@s5 | 31 | -10.79 | -10.43 | 0.58 |
| oa_crosscheck_v1-228@s5 | IWM orb60 C fixed 20/20 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-050@s5 | 44 | -8.48 | -10.08 | 0.30 |
| oa_crosscheck_v1-229@s5 | IWM orb60 C fixed 20/40 desk d40-55t45 sma20_side | oa_crosscheck_v1-051@s5 | 31 | -10.23 | -11.67 | 0.22 |
| oa_crosscheck_v1-230@s5 | IWM orb60 C fixed 20/40 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-051@s5 | 44 | -7.35 | -11.41 | 0.10 |
| oa_crosscheck_v1-231@s5 | IWM orb60 C fixed 20/40 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-052@s5 | 31 | -7.99 | -9.06 | 0.33 |
| oa_crosscheck_v1-232@s5 | IWM orb60 C fixed 20/40 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-052@s5 | 44 | -5.67 | -8.62 | 0.20 |
| oa_crosscheck_v1-233@s5 | IWM orb60 C fixed 20/60 desk d40-55t45 sma20_side | oa_crosscheck_v1-053@s5 | 31 | -11.78 | -11.57 | 0.54 |
| oa_crosscheck_v1-234@s5 | IWM orb60 C fixed 20/60 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-053@s5 | 44 | -8.37 | -11.22 | 0.21 |
| oa_crosscheck_v1-235@s5 | IWM orb60 C fixed 20/60 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-054@s5 | 31 | -11.29 | -11.43 | 0.48 |
| oa_crosscheck_v1-236@s5 | IWM orb60 C fixed 20/60 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-054@s5 | 44 | -9.43 | -10.97 | 0.34 |
| oa_crosscheck_v1-237@s5 | IWM orb60 C fixed 15/45 desk d40-55t45 sma20_side | oa_crosscheck_v1-055@s5 | 31 | -10.95 | -10.36 | 0.63 |
| oa_crosscheck_v1-238@s5 | IWM orb60 C fixed 15/45 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-055@s5 | 44 | -8.94 | -10.17 | 0.32 |
| oa_crosscheck_v1-239@s5 | IWM orb60 C fixed 15/45 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-056@s5 | 31 | -11.05 | -11.46 | 0.43 |
| oa_crosscheck_v1-240@s5 | IWM orb60 C fixed 15/45 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-056@s5 | 44 | -9.35 | -11.28 | 0.27 |
| oa_crosscheck_v1-241@s5 | IWM orb60 C fixed 10/30 desk d40-55t45 sma20_side | oa_crosscheck_v1-057@s5 | 31 | -9.49 | -8.48 | 0.80 |
| oa_crosscheck_v1-242@s5 | IWM orb60 C fixed 10/30 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-057@s5 | 44 | -8.34 | -8.37 | 0.51 |
| oa_crosscheck_v1-243@s5 | IWM orb60 C fixed 10/30 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-058@s5 | 31 | -9.97 | -10.39 | 0.41 |
| oa_crosscheck_v1-244@s5 | IWM orb60 C fixed 10/30 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-058@s5 | 44 | -7.62 | -10.14 | 0.15 |
| oa_crosscheck_v1-245@s5 | IWM orb60 P fixed 20/20 desk d40-55t45 sma20_side | oa_crosscheck_v1-061@s5 | 53 | -7.11 | -8.69 | 0.21 |
| oa_crosscheck_v1-246@s5 | IWM orb60 P fixed 20/20 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-061@s5 | 62 | -8.76 | -8.78 | 0.49 |
| oa_crosscheck_v1-247@s5 | IWM orb60 P fixed 20/20 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-062@s5 | 53 | -5.30 | -6.73 | 0.33 |
| oa_crosscheck_v1-248@s5 | IWM orb60 P fixed 20/20 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-062@s5 | 62 | -6.86 | -6.89 | 0.51 |
| oa_crosscheck_v1-249@s5 | IWM orb60 P fixed 20/40 desk d40-55t45 sma20_side | oa_crosscheck_v1-063@s5 | 53 | -5.31 | -7.59 | 0.23 |
| oa_crosscheck_v1-250@s5 | IWM orb60 P fixed 20/40 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-063@s5 | 62 | -3.12 | -7.75 | 0.10 |
| oa_crosscheck_v1-251@s5 | IWM orb60 P fixed 20/40 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-064@s5 | 53 | -6.57 | -7.62 | 0.39 |
| oa_crosscheck_v1-252@s5 | IWM orb60 P fixed 20/40 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-064@s5 | 62 | -6.09 | -7.69 | 0.34 |
| oa_crosscheck_v1-253@s5 | IWM orb60 P fixed 20/60 desk d40-55t45 sma20_side | oa_crosscheck_v1-065@s5 | 53 | -8.87 | -10.40 | 0.33 |
| oa_crosscheck_v1-254@s5 | IWM orb60 P fixed 20/60 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-065@s5 | 62 | -5.87 | -10.34 | 0.13 |
| oa_crosscheck_v1-255@s5 | IWM orb60 P fixed 20/60 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-066@s5 | 53 | -5.99 | -6.85 | 0.43 |
| oa_crosscheck_v1-256@s5 | IWM orb60 P fixed 20/60 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-066@s5 | 62 | -4.30 | -6.84 | 0.31 |
| oa_crosscheck_v1-257@s5 | IWM orb60 P fixed 15/45 desk d40-55t45 sma20_side | oa_crosscheck_v1-067@s5 | 53 | -7.14 | -9.03 | 0.22 |
| oa_crosscheck_v1-258@s5 | IWM orb60 P fixed 15/45 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-067@s5 | 62 | -8.02 | -9.05 | 0.35 |
| oa_crosscheck_v1-259@s5 | IWM orb60 P fixed 15/45 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-068@s5 | 53 | -8.63 | -9.50 | 0.39 |
| oa_crosscheck_v1-260@s5 | IWM orb60 P fixed 15/45 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-068@s5 | 62 | -7.96 | -9.52 | 0.32 |
| oa_crosscheck_v1-261@s5 | IWM orb60 P fixed 10/30 desk d40-55t45 sma20_side | oa_crosscheck_v1-069@s5 | 53 | -8.78 | -8.25 | 0.64 |
| oa_crosscheck_v1-262@s5 | IWM orb60 P fixed 10/30 desk d40-55t45 sma20_side_1pct | oa_crosscheck_v1-069@s5 | 62 | -8.58 | -8.27 | 0.56 |
| oa_crosscheck_v1-263@s5 | IWM orb60 P fixed 10/30 oa1m d40-55t45 sma20_side | oa_crosscheck_v1-070@s5 | 53 | -7.49 | -8.57 | 0.32 |
| oa_crosscheck_v1-264@s5 | IWM orb60 P fixed 10/30 oa1m d40-55t45 sma20_side_1pct | oa_crosscheck_v1-070@s5 | 62 | -8.31 | -8.75 | 0.45 |
| oa_crosscheck_v1-265@s5 | SPY orb60 C fixed 20/20 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-001@s5 | 13 | -13.49 | -12.84 | 0.82 |
| oa_crosscheck_v1-266@s5 | SPY orb60 C fixed 20/20 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-002@s5 | 13 | -10.94 | -11.35 | 0.32 |
| oa_crosscheck_v1-267@s5 | SPY orb60 C fixed 20/40 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-003@s5 | 13 | -15.13 | -15.35 | 0.39 |
| oa_crosscheck_v1-268@s5 | SPY orb60 C fixed 20/40 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-004@s5 | 13 | -16.41 | -17.07 | 0.26 |
| oa_crosscheck_v1-269@s5 | SPY orb60 C fixed 20/60 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-005@s5 | 13 | -17.78 | -17.93 | 0.46 |
| oa_crosscheck_v1-270@s5 | SPY orb60 C fixed 20/60 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-006@s5 | 13 | -16.92 | -17.86 | 0.24 |
| oa_crosscheck_v1-271@s5 | SPY orb60 C fixed 15/45 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-007@s5 | 13 | -16.12 | -16.12 | 0.52 |
| oa_crosscheck_v1-272@s5 | SPY orb60 C fixed 15/45 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-008@s5 | 13 | -16.66 | -16.87 | 0.42 |
| oa_crosscheck_v1-273@s5 | SPY orb60 C fixed 10/30 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-009@s5 | 13 | -13.67 | -13.45 | 0.74 |
| oa_crosscheck_v1-274@s5 | SPY orb60 C fixed 10/30 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-010@s5 | 13 | -16.02 | -15.59 | 0.77 |
| oa_crosscheck_v1-275@s5 | SPY orb60 P fixed 20/20 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-013@s5 | 11 | -10.02 | -11.91 | 0.02 |
| oa_crosscheck_v1-276@s5 | SPY orb60 P fixed 20/20 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-014@s5 | 11 | -10.63 | -14.29 | 0.00 |
| oa_crosscheck_v1-277@s5 | SPY orb60 P fixed 20/40 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-015@s5 | 11 | -14.61 | -17.04 | 0.02 |
| oa_crosscheck_v1-278@s5 | SPY orb60 P fixed 20/40 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-016@s5 | 11 | -14.16 | -17.05 | 0.02 |
| oa_crosscheck_v1-279@s5 | SPY orb60 P fixed 20/60 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-017@s5 | 11 | -14.74 | -16.80 | 0.04 |
| oa_crosscheck_v1-280@s5 | SPY orb60 P fixed 20/60 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-018@s5 | 11 | -13.88 | -16.40 | 0.06 |
| oa_crosscheck_v1-281@s5 | SPY orb60 P fixed 15/45 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-019@s5 | 11 | -16.80 | -17.93 | 0.09 |
| oa_crosscheck_v1-282@s5 | SPY orb60 P fixed 15/45 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-020@s5 | 11 | -14.63 | -16.24 | 0.09 |
| oa_crosscheck_v1-283@s5 | SPY orb60 P fixed 10/30 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-021@s5 | 11 | -11.97 | -13.73 | 0.00 |
| oa_crosscheck_v1-284@s5 | SPY orb60 P fixed 10/30 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-022@s5 | 11 | -12.21 | -13.60 | 0.04 |
| oa_crosscheck_v1-285@s5 | QQQ orb60 C fixed 20/20 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-025@s5 | 13 | -17.94 | -17.76 | 0.61 |
| oa_crosscheck_v1-286@s5 | QQQ orb60 C fixed 20/20 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-026@s5 | 13 | -16.32 | -16.19 | 0.58 |
| oa_crosscheck_v1-287@s5 | QQQ orb60 C fixed 20/40 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-027@s5 | 13 | -17.34 | -17.59 | 0.41 |
| oa_crosscheck_v1-288@s5 | QQQ orb60 C fixed 20/40 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-028@s5 | 13 | -17.55 | -17.08 | 0.69 |
| oa_crosscheck_v1-289@s5 | QQQ orb60 C fixed 20/60 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-029@s5 | 13 | -20.82 | -20.43 | 0.68 |
| oa_crosscheck_v1-290@s5 | QQQ orb60 C fixed 20/60 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-030@s5 | 13 | -23.60 | -22.04 | 0.91 |
| oa_crosscheck_v1-291@s5 | QQQ orb60 C fixed 15/45 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-031@s5 | 13 | -15.71 | -15.99 | 0.39 |
| oa_crosscheck_v1-292@s5 | QQQ orb60 C fixed 15/45 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-032@s5 | 13 | -18.44 | -18.85 | 0.38 |
| oa_crosscheck_v1-293@s5 | QQQ orb60 C fixed 10/30 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-033@s5 | 13 | -14.71 | -14.42 | 0.76 |
| oa_crosscheck_v1-294@s5 | QQQ orb60 C fixed 10/30 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-034@s5 | 13 | -15.55 | -15.76 | 0.39 |
| oa_crosscheck_v1-295@s5 | QQQ orb60 P fixed 20/20 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-037@s5 | 10 | -13.78 | -11.86 | 0.97 |
| oa_crosscheck_v1-296@s5 | QQQ orb60 P fixed 20/20 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-038@s5 | 10 | -13.09 | -11.75 | 0.86 |
| oa_crosscheck_v1-297@s5 | QQQ orb60 P fixed 20/40 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-039@s5 | 10 | -11.09 | -10.71 | 0.64 |
| oa_crosscheck_v1-298@s5 | QQQ orb60 P fixed 20/40 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-040@s5 | 10 | -13.04 | -12.80 | 0.58 |
| oa_crosscheck_v1-299@s5 | QQQ orb60 P fixed 20/60 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-041@s5 | 10 | -11.86 | -11.18 | 0.68 |
| oa_crosscheck_v1-300@s5 | QQQ orb60 P fixed 20/60 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-042@s5 | 10 | -14.61 | -14.12 | 0.65 |
| oa_crosscheck_v1-301@s5 | QQQ orb60 P fixed 15/45 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-043@s5 | 10 | -17.43 | -18.14 | 0.25 |
| oa_crosscheck_v1-302@s5 | QQQ orb60 P fixed 15/45 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-044@s5 | 10 | -14.60 | -15.34 | 0.34 |
| oa_crosscheck_v1-303@s5 | QQQ orb60 P fixed 10/30 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-045@s5 | 10 | -15.43 | -15.96 | 0.25 |
| oa_crosscheck_v1-304@s5 | QQQ orb60 P fixed 10/30 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-046@s5 | 10 | -15.69 | -16.56 | 0.22 |
| oa_crosscheck_v1-305@s5 | IWM orb60 C fixed 20/20 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-049@s5 | 5 | -10.28 | -11.36 | 0.01 |
| oa_crosscheck_v1-306@s5 | IWM orb60 C fixed 20/20 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-050@s5 | 5 | -9.25 | -10.33 | 0.02 |
| oa_crosscheck_v1-307@s5 | IWM orb60 C fixed 20/40 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-051@s5 | 5 | -10.87 | -11.59 | 0.09 |
| oa_crosscheck_v1-308@s5 | IWM orb60 C fixed 20/40 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-052@s5 | 5 | -8.16 | -8.96 | 0.17 |
| oa_crosscheck_v1-309@s5 | IWM orb60 C fixed 20/60 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-053@s5 | 5 | -11.02 | -11.42 | 0.36 |
| oa_crosscheck_v1-310@s5 | IWM orb60 C fixed 20/60 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-054@s5 | 5 | -10.93 | -11.29 | 0.39 |
| oa_crosscheck_v1-311@s5 | IWM orb60 C fixed 15/45 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-055@s5 | 5 | -9.94 | -10.31 | 0.25 |
| oa_crosscheck_v1-312@s5 | IWM orb60 C fixed 15/45 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-056@s5 | 5 | -11.01 | -11.40 | 0.30 |
| oa_crosscheck_v1-313@s5 | IWM orb60 C fixed 10/30 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-057@s5 | 5 | -8.10 | -8.42 | 0.18 |
| oa_crosscheck_v1-314@s5 | IWM orb60 C fixed 10/30 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-058@s5 | 5 | -10.17 | -10.31 | 0.43 |
| oa_crosscheck_v1-315@s5 | IWM orb60 P fixed 20/20 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-061@s5 | 10 | -7.54 | -8.84 | 0.02 |
| oa_crosscheck_v1-316@s5 | IWM orb60 P fixed 20/20 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-062@s5 | 10 | -4.86 | -6.91 | 0.00 |
| oa_crosscheck_v1-317@s5 | IWM orb60 P fixed 20/40 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-063@s5 | 10 | -6.40 | -7.89 | 0.04 |
| oa_crosscheck_v1-318@s5 | IWM orb60 P fixed 20/40 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-064@s5 | 10 | -6.11 | -7.79 | 0.04 |
| oa_crosscheck_v1-319@s5 | IWM orb60 P fixed 20/60 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-065@s5 | 10 | -8.82 | -10.53 | 0.02 |
| oa_crosscheck_v1-320@s5 | IWM orb60 P fixed 20/60 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-066@s5 | 10 | -4.71 | -7.10 | 0.01 |
| oa_crosscheck_v1-321@s5 | IWM orb60 P fixed 15/45 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-067@s5 | 10 | -7.80 | -9.12 | 0.01 |
| oa_crosscheck_v1-322@s5 | IWM orb60 P fixed 15/45 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-068@s5 | 10 | -7.87 | -9.61 | 0.03 |
| oa_crosscheck_v1-323@s5 | IWM orb60 P fixed 10/30 desk d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-069@s5 | 10 | -7.38 | -8.28 | 0.01 |
| oa_crosscheck_v1-324@s5 | IWM orb60 P fixed 10/30 oa1m d40-55t45 skip_fomc_cpi | oa_crosscheck_v1-070@s5 | 10 | -7.50 | -8.76 | 0.01 |
| oa_crosscheck_v1-325@s5 | SPY orb60 C fixed 20/20 desk d40-55t45 vixy_falling | oa_crosscheck_v1-001@s5 | 41 | -10.43 | -12.79 | 0.05 |
| oa_crosscheck_v1-326@s5 | SPY orb60 C fixed 20/20 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-001@s5 | 63 | -12.08 | -12.75 | 0.37 |
| oa_crosscheck_v1-327@s5 | SPY orb60 C fixed 20/20 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-002@s5 | 41 | -8.70 | -11.30 | 0.05 |
| oa_crosscheck_v1-328@s5 | SPY orb60 C fixed 20/20 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-002@s5 | 63 | -11.66 | -11.26 | 0.56 |
| oa_crosscheck_v1-329@s5 | SPY orb60 C fixed 20/40 desk d40-55t45 vixy_falling | oa_crosscheck_v1-003@s5 | 41 | -12.55 | -15.24 | 0.05 |
| oa_crosscheck_v1-330@s5 | SPY orb60 C fixed 20/40 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-003@s5 | 63 | -13.77 | -15.21 | 0.27 |
| oa_crosscheck_v1-331@s5 | SPY orb60 C fixed 20/40 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-004@s5 | 41 | -14.85 | -16.95 | 0.14 |
| oa_crosscheck_v1-332@s5 | SPY orb60 C fixed 20/40 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-004@s5 | 63 | -18.06 | -17.03 | 0.63 |
| oa_crosscheck_v1-333@s5 | SPY orb60 C fixed 20/60 desk d40-55t45 vixy_falling | oa_crosscheck_v1-005@s5 | 41 | -15.98 | -17.82 | 0.15 |
| oa_crosscheck_v1-334@s5 | SPY orb60 C fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-005@s5 | 63 | -17.69 | -17.88 | 0.48 |
| oa_crosscheck_v1-335@s5 | SPY orb60 C fixed 20/60 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-006@s5 | 41 | -14.05 | -17.63 | 0.07 |
| oa_crosscheck_v1-336@s5 | SPY orb60 C fixed 20/60 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-006@s5 | 63 | -20.09 | -17.73 | 0.76 |
| oa_crosscheck_v1-337@s5 | SPY orb60 C fixed 15/45 desk d40-55t45 vixy_falling | oa_crosscheck_v1-007@s5 | 41 | -15.86 | -16.08 | 0.44 |
| oa_crosscheck_v1-338@s5 | SPY orb60 C fixed 15/45 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-007@s5 | 63 | -14.96 | -16.06 | 0.29 |
| oa_crosscheck_v1-339@s5 | SPY orb60 C fixed 15/45 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-008@s5 | 41 | -15.31 | -16.77 | 0.19 |
| oa_crosscheck_v1-340@s5 | SPY orb60 C fixed 15/45 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-008@s5 | 63 | -16.89 | -16.81 | 0.52 |
| oa_crosscheck_v1-341@s5 | SPY orb60 C fixed 10/30 desk d40-55t45 vixy_falling | oa_crosscheck_v1-009@s5 | 41 | -12.71 | -13.43 | 0.19 |
| oa_crosscheck_v1-342@s5 | SPY orb60 C fixed 10/30 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-009@s5 | 63 | -11.35 | -13.43 | 0.06 |
| oa_crosscheck_v1-343@s5 | SPY orb60 C fixed 10/30 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-010@s5 | 41 | -15.06 | -15.53 | 0.33 |
| oa_crosscheck_v1-344@s5 | SPY orb60 C fixed 10/30 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-010@s5 | 63 | -13.05 | -15.57 | 0.06 |
| oa_crosscheck_v1-345@s5 | SPY orb60 P fixed 20/20 desk d40-55t45 vixy_falling | oa_crosscheck_v1-013@s5 | 78 | -9.36 | -11.95 | 0.25 |
| oa_crosscheck_v1-346@s5 | SPY orb60 P fixed 20/20 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-013@s5 | 87 | -14.98 | -11.72 | 0.78 |
| oa_crosscheck_v1-347@s5 | SPY orb60 P fixed 20/20 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-014@s5 | 78 | -13.97 | -14.12 | 0.48 |
| oa_crosscheck_v1-348@s5 | SPY orb60 P fixed 20/20 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-014@s5 | 87 | -18.73 | -14.09 | 0.79 |
| oa_crosscheck_v1-349@s5 | SPY orb60 P fixed 20/40 desk d40-55t45 vixy_falling | oa_crosscheck_v1-015@s5 | 78 | -18.53 | -16.82 | 0.65 |
| oa_crosscheck_v1-350@s5 | SPY orb60 P fixed 20/40 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-015@s5 | 87 | -21.70 | -16.74 | 0.85 |
| oa_crosscheck_v1-351@s5 | SPY orb60 P fixed 20/40 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-016@s5 | 78 | -17.81 | -16.69 | 0.58 |
| oa_crosscheck_v1-352@s5 | SPY orb60 P fixed 20/40 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-016@s5 | 87 | -27.69 | -16.77 | 0.95 |
| oa_crosscheck_v1-353@s5 | SPY orb60 P fixed 20/60 desk d40-55t45 vixy_falling | oa_crosscheck_v1-017@s5 | 78 | -17.91 | -16.50 | 0.62 |
| oa_crosscheck_v1-354@s5 | SPY orb60 P fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-017@s5 | 87 | -21.58 | -16.63 | 0.79 |
| oa_crosscheck_v1-355@s5 | SPY orb60 P fixed 20/60 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-018@s5 | 78 | -13.66 | -15.94 | 0.37 |
| oa_crosscheck_v1-356@s5 | SPY orb60 P fixed 20/60 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-018@s5 | 87 | -26.30 | -16.18 | 0.90 |
| oa_crosscheck_v1-357@s5 | SPY orb60 P fixed 15/45 desk d40-55t45 vixy_falling | oa_crosscheck_v1-019@s5 | 78 | -18.86 | -17.81 | 0.59 |
| oa_crosscheck_v1-358@s5 | SPY orb60 P fixed 15/45 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-019@s5 | 87 | -20.92 | -17.87 | 0.73 |
| oa_crosscheck_v1-359@s5 | SPY orb60 P fixed 15/45 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-020@s5 | 78 | -19.71 | -15.96 | 0.76 |
| oa_crosscheck_v1-360@s5 | SPY orb60 P fixed 15/45 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-020@s5 | 87 | -22.94 | -16.09 | 0.88 |
| oa_crosscheck_v1-361@s5 | SPY orb60 P fixed 10/30 desk d40-55t45 vixy_falling | oa_crosscheck_v1-021@s5 | 78 | -15.98 | -13.61 | 0.82 |
| oa_crosscheck_v1-362@s5 | SPY orb60 P fixed 10/30 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-021@s5 | 87 | -14.39 | -13.63 | 0.58 |
| oa_crosscheck_v1-363@s5 | SPY orb60 P fixed 10/30 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-022@s5 | 78 | -17.00 | -13.34 | 0.82 |
| oa_crosscheck_v1-364@s5 | SPY orb60 P fixed 10/30 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-022@s5 | 87 | -20.99 | -13.28 | 0.95 |
| oa_crosscheck_v1-365@s5 | QQQ orb60 C fixed 20/20 desk d40-55t45 vixy_falling | oa_crosscheck_v1-025@s5 | 40 | -17.74 | -17.80 | 0.47 |
| oa_crosscheck_v1-366@s5 | QQQ orb60 C fixed 20/20 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-025@s5 | 79 | -12.71 | -17.70 | 0.02 |
| oa_crosscheck_v1-367@s5 | QQQ orb60 C fixed 20/20 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-026@s5 | 40 | -16.10 | -16.27 | 0.46 |
| oa_crosscheck_v1-368@s5 | QQQ orb60 C fixed 20/20 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-026@s5 | 79 | -10.64 | -16.11 | 0.03 |
| oa_crosscheck_v1-369@s5 | QQQ orb60 C fixed 20/40 desk d40-55t45 vixy_falling | oa_crosscheck_v1-027@s5 | 40 | -16.27 | -17.62 | 0.23 |
| oa_crosscheck_v1-370@s5 | QQQ orb60 C fixed 20/40 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-027@s5 | 79 | -10.92 | -17.53 | 0.01 |
| oa_crosscheck_v1-371@s5 | QQQ orb60 C fixed 20/40 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-028@s5 | 40 | -16.66 | -16.98 | 0.46 |
| oa_crosscheck_v1-372@s5 | QQQ orb60 C fixed 20/40 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-028@s5 | 79 | -14.39 | -17.02 | 0.24 |
| oa_crosscheck_v1-373@s5 | QQQ orb60 C fixed 20/60 desk d40-55t45 vixy_falling | oa_crosscheck_v1-029@s5 | 40 | -21.57 | -20.41 | 0.73 |
| oa_crosscheck_v1-374@s5 | QQQ orb60 C fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-029@s5 | 79 | -17.19 | -20.37 | 0.17 |
| oa_crosscheck_v1-375@s5 | QQQ orb60 C fixed 20/60 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-030@s5 | 40 | -23.82 | -21.93 | 0.80 |
| oa_crosscheck_v1-376@s5 | QQQ orb60 C fixed 20/60 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-030@s5 | 79 | -17.55 | -21.91 | 0.15 |
| oa_crosscheck_v1-377@s5 | QQQ orb60 C fixed 15/45 desk d40-55t45 vixy_falling | oa_crosscheck_v1-031@s5 | 40 | -16.18 | -15.94 | 0.57 |
| oa_crosscheck_v1-378@s5 | QQQ orb60 C fixed 15/45 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-031@s5 | 79 | -14.76 | -15.90 | 0.33 |
| oa_crosscheck_v1-379@s5 | QQQ orb60 C fixed 15/45 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-032@s5 | 40 | -18.20 | -18.79 | 0.40 |
| oa_crosscheck_v1-380@s5 | QQQ orb60 C fixed 15/45 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-032@s5 | 79 | -16.58 | -18.73 | 0.25 |
| oa_crosscheck_v1-381@s5 | QQQ orb60 C fixed 10/30 desk d40-55t45 vixy_falling | oa_crosscheck_v1-033@s5 | 40 | -14.37 | -14.41 | 0.49 |
| oa_crosscheck_v1-382@s5 | QQQ orb60 C fixed 10/30 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-033@s5 | 79 | -10.53 | -14.42 | 0.01 |
| oa_crosscheck_v1-383@s5 | QQQ orb60 C fixed 10/30 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-034@s5 | 40 | -15.21 | -15.80 | 0.34 |
| oa_crosscheck_v1-384@s5 | QQQ orb60 C fixed 10/30 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-034@s5 | 79 | -11.07 | -15.75 | 0.03 |
| oa_crosscheck_v1-385@s5 | QQQ orb60 P fixed 20/20 desk d40-55t45 vixy_falling | oa_crosscheck_v1-037@s5 | 68 | -7.48 | -11.70 | 0.12 |
| oa_crosscheck_v1-386@s5 | QQQ orb60 P fixed 20/20 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-037@s5 | 80 | -12.62 | -12.13 | 0.53 |
| oa_crosscheck_v1-387@s5 | QQQ orb60 P fixed 20/20 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-038@s5 | 68 | -7.43 | -11.54 | 0.22 |
| oa_crosscheck_v1-388@s5 | QQQ orb60 P fixed 20/20 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-038@s5 | 80 | -17.06 | -11.98 | 0.80 |
| oa_crosscheck_v1-389@s5 | QQQ orb60 P fixed 20/40 desk d40-55t45 vixy_falling | oa_crosscheck_v1-039@s5 | 68 | -15.05 | -10.43 | 0.79 |
| oa_crosscheck_v1-390@s5 | QQQ orb60 P fixed 20/40 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-039@s5 | 80 | -11.12 | -11.16 | 0.50 |
| oa_crosscheck_v1-391@s5 | QQQ orb60 P fixed 20/40 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-040@s5 | 68 | -18.80 | -12.56 | 0.82 |
| oa_crosscheck_v1-392@s5 | QQQ orb60 P fixed 20/40 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-040@s5 | 80 | -20.98 | -13.59 | 0.83 |
| oa_crosscheck_v1-393@s5 | QQQ orb60 P fixed 20/60 desk d40-55t45 vixy_falling | oa_crosscheck_v1-041@s5 | 68 | -18.08 | -11.13 | 0.83 |
| oa_crosscheck_v1-394@s5 | QQQ orb60 P fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-041@s5 | 80 | -11.23 | -11.73 | 0.47 |
| oa_crosscheck_v1-395@s5 | QQQ orb60 P fixed 20/60 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-042@s5 | 68 | -18.18 | -14.03 | 0.69 |
| oa_crosscheck_v1-396@s5 | QQQ orb60 P fixed 20/60 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-042@s5 | 80 | -15.46 | -15.00 | 0.50 |
| oa_crosscheck_v1-397@s5 | QQQ orb60 P fixed 15/45 desk d40-55t45 vixy_falling | oa_crosscheck_v1-043@s5 | 68 | -20.92 | -18.00 | 0.74 |
| oa_crosscheck_v1-398@s5 | QQQ orb60 P fixed 15/45 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-043@s5 | 80 | -15.03 | -18.04 | 0.28 |
| oa_crosscheck_v1-399@s5 | QQQ orb60 P fixed 15/45 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-044@s5 | 68 | -22.82 | -15.18 | 0.90 |
| oa_crosscheck_v1-400@s5 | QQQ orb60 P fixed 15/45 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-044@s5 | 80 | -16.35 | -15.40 | 0.54 |
| oa_crosscheck_v1-401@s5 | QQQ orb60 P fixed 10/30 desk d40-55t45 vixy_falling | oa_crosscheck_v1-045@s5 | 68 | -18.63 | -15.89 | 0.84 |
| oa_crosscheck_v1-402@s5 | QQQ orb60 P fixed 10/30 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-045@s5 | 80 | -11.72 | -15.89 | 0.12 |
| oa_crosscheck_v1-403@s5 | QQQ orb60 P fixed 10/30 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-046@s5 | 68 | -20.04 | -16.39 | 0.80 |
| oa_crosscheck_v1-404@s5 | QQQ orb60 P fixed 10/30 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-046@s5 | 80 | -12.46 | -16.54 | 0.21 |
| oa_crosscheck_v1-405@s5 | IWM orb60 C fixed 20/20 desk d40-55t45 vixy_falling | oa_crosscheck_v1-049@s5 | 21 | -9.52 | -11.35 | 0.06 |
| oa_crosscheck_v1-406@s5 | IWM orb60 C fixed 20/20 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-049@s5 | 46 | -8.49 | -11.55 | 0.14 |
| oa_crosscheck_v1-407@s5 | IWM orb60 C fixed 20/20 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-050@s5 | 21 | -6.92 | -10.34 | 0.00 |
| oa_crosscheck_v1-408@s5 | IWM orb60 C fixed 20/20 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-050@s5 | 46 | -8.17 | -10.54 | 0.23 |
| oa_crosscheck_v1-409@s5 | IWM orb60 C fixed 20/40 desk d40-55t45 vixy_falling | oa_crosscheck_v1-051@s5 | 21 | -9.67 | -11.56 | 0.08 |
| oa_crosscheck_v1-410@s5 | IWM orb60 C fixed 20/40 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-051@s5 | 46 | -6.50 | -11.82 | 0.04 |
| oa_crosscheck_v1-411@s5 | IWM orb60 C fixed 20/40 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-052@s5 | 21 | -5.62 | -8.96 | 0.03 |
| oa_crosscheck_v1-412@s5 | IWM orb60 C fixed 20/40 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-052@s5 | 46 | -7.04 | -9.22 | 0.29 |
| oa_crosscheck_v1-413@s5 | IWM orb60 C fixed 20/60 desk d40-55t45 vixy_falling | oa_crosscheck_v1-053@s5 | 21 | -9.24 | -11.47 | 0.08 |
| oa_crosscheck_v1-414@s5 | IWM orb60 C fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-053@s5 | 46 | -7.58 | -11.63 | 0.13 |
| oa_crosscheck_v1-415@s5 | IWM orb60 C fixed 20/60 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-054@s5 | 21 | -8.59 | -11.27 | 0.09 |
| oa_crosscheck_v1-416@s5 | IWM orb60 C fixed 20/60 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-054@s5 | 46 | -13.47 | -11.37 | 0.67 |
| oa_crosscheck_v1-417@s5 | IWM orb60 C fixed 15/45 desk d40-55t45 vixy_falling | oa_crosscheck_v1-055@s5 | 21 | -8.93 | -10.33 | 0.14 |
| oa_crosscheck_v1-418@s5 | IWM orb60 C fixed 15/45 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-055@s5 | 46 | -8.41 | -10.48 | 0.23 |
| oa_crosscheck_v1-419@s5 | IWM orb60 C fixed 15/45 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-056@s5 | 21 | -9.09 | -11.38 | 0.06 |
| oa_crosscheck_v1-420@s5 | IWM orb60 C fixed 15/45 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-056@s5 | 46 | -7.13 | -11.56 | 0.07 |
| oa_crosscheck_v1-421@s5 | IWM orb60 C fixed 10/30 desk d40-55t45 vixy_falling | oa_crosscheck_v1-057@s5 | 21 | -7.24 | -8.44 | 0.08 |
| oa_crosscheck_v1-422@s5 | IWM orb60 C fixed 10/30 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-057@s5 | 46 | -8.04 | -8.59 | 0.37 |
| oa_crosscheck_v1-423@s5 | IWM orb60 C fixed 10/30 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-058@s5 | 21 | -8.65 | -10.30 | 0.07 |
| oa_crosscheck_v1-424@s5 | IWM orb60 C fixed 10/30 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-058@s5 | 46 | -7.63 | -10.54 | 0.13 |
| oa_crosscheck_v1-425@s5 | IWM orb60 P fixed 20/20 desk d40-55t45 vixy_falling | oa_crosscheck_v1-061@s5 | 58 | -7.18 | -8.84 | 0.24 |
| oa_crosscheck_v1-426@s5 | IWM orb60 P fixed 20/20 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-061@s5 | 66 | -11.59 | -8.91 | 0.81 |
| oa_crosscheck_v1-427@s5 | IWM orb60 P fixed 20/20 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-062@s5 | 58 | -10.30 | -7.03 | 0.84 |
| oa_crosscheck_v1-428@s5 | IWM orb60 P fixed 20/20 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-062@s5 | 66 | -9.77 | -7.19 | 0.76 |
| oa_crosscheck_v1-429@s5 | IWM orb60 P fixed 20/40 desk d40-55t45 vixy_falling | oa_crosscheck_v1-063@s5 | 58 | -5.43 | -8.00 | 0.21 |
| oa_crosscheck_v1-430@s5 | IWM orb60 P fixed 20/40 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-063@s5 | 66 | -9.62 | -8.06 | 0.64 |
| oa_crosscheck_v1-431@s5 | IWM orb60 P fixed 20/40 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-064@s5 | 58 | -8.80 | -8.01 | 0.57 |
| oa_crosscheck_v1-432@s5 | IWM orb60 P fixed 20/40 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-064@s5 | 66 | -12.25 | -8.06 | 0.79 |
| oa_crosscheck_v1-433@s5 | IWM orb60 P fixed 20/60 desk d40-55t45 vixy_falling | oa_crosscheck_v1-065@s5 | 58 | -5.62 | -10.76 | 0.07 |
| oa_crosscheck_v1-434@s5 | IWM orb60 P fixed 20/60 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-065@s5 | 66 | -14.72 | -10.95 | 0.81 |
| oa_crosscheck_v1-435@s5 | IWM orb60 P fixed 20/60 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-066@s5 | 58 | -6.87 | -7.31 | 0.47 |
| oa_crosscheck_v1-436@s5 | IWM orb60 P fixed 20/60 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-066@s5 | 66 | -14.44 | -7.54 | 0.88 |
| oa_crosscheck_v1-437@s5 | IWM orb60 P fixed 15/45 desk d40-55t45 vixy_falling | oa_crosscheck_v1-067@s5 | 58 | -7.70 | -9.28 | 0.27 |
| oa_crosscheck_v1-438@s5 | IWM orb60 P fixed 15/45 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-067@s5 | 66 | -12.32 | -9.24 | 0.80 |
| oa_crosscheck_v1-439@s5 | IWM orb60 P fixed 15/45 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-068@s5 | 58 | -8.86 | -9.84 | 0.39 |
| oa_crosscheck_v1-440@s5 | IWM orb60 P fixed 15/45 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-068@s5 | 66 | -11.01 | -9.84 | 0.61 |
| oa_crosscheck_v1-441@s5 | IWM orb60 P fixed 10/30 desk d40-55t45 vixy_falling | oa_crosscheck_v1-069@s5 | 58 | -7.53 | -8.28 | 0.32 |
| oa_crosscheck_v1-442@s5 | IWM orb60 P fixed 10/30 desk d40-55t45 gap_side_075 | oa_crosscheck_v1-069@s5 | 66 | -6.88 | -8.40 | 0.24 |
| oa_crosscheck_v1-443@s5 | IWM orb60 P fixed 10/30 oa1m d40-55t45 vixy_falling | oa_crosscheck_v1-070@s5 | 58 | -10.36 | -8.89 | 0.71 |
| oa_crosscheck_v1-444@s5 | IWM orb60 P fixed 10/30 oa1m d40-55t45 gap_side_075 | oa_crosscheck_v1-070@s5 | 66 | -8.03 | -8.89 | 0.38 |



Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_oa_crosscheck_v1@s5_2026-10-31.csv.gz`.

Labels: BACKTEST (in-sample on DEV). Spread: MODELED-SPREAD 5.0% (sensitivity). Delta: BS-EST. Not financial advice: evidence for Nick to decide.
