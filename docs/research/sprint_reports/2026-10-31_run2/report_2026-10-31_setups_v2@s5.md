# Sprint report: setups_v2 (DEV), MODELED-SPREAD 5.0% (sensitivity)

Generated 2026-10-31 12:21 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint1` in 3.6 min. Spec sha256 `2b3d90478447efffffb748223d893f71529c2565713379225e2d32f0e77a6f26`.

**Every number below is a BACKTEST in-sample (DEV)** on Alpaca 1-minute bars, 2024-08-01 to 2026-06-30. Option fills are real traded prices +/- a half-spread: **MODELED-SPREAD 5.0% of premium for every symbol (a SENSITIVITY run, not the pre-registered 2% default), floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Deltas are BS-EST (Black-Scholes from the option's price). Nothing here is a live or paper fill.

Data: IWM: 479 sessions, QQQ: 479 sessions, SPY: 479 sessions. Runs in this spec: 58. Trials counted for the deflated Sharpe: 2885 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Known limits: July 2024 is locked (L2), so early-August 2024 sessions have partial history; news and VIX are unknown in the backtest (rules that need them never fire); a contract needs BS-EST |delta| inside the band, so some signals have no contract (counted as skips).

**Cost caveat:** MODELED-SPREAD 5.0% of premium for every symbol (a SENSITIVITY run, not the pre-registered 2% default), floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: Failed-break deep dive (pre-registered 2026-10-31, after setups_v1 and before any v2 run). setups_v1-049 (failed_break calls, premium-ceiling stop, no target, all out 15:25; PF 1.47, PF 2x 1.03) is the only v1 run with PF >= 1.25, but it lost in Aug-Dec 2024 and is negative without its best 5 trades. This spec changes ONE thing at a time on that run: symbols (SPY+QQQ is an IN-SAMPLE choice made after seeing IWM lose), the entry's own numbers (re-close window, probe depth, which levels), the put mirror (failed_high), time rules, trails, level take-profits, fixed far targets, contracts (incl. the next listed expiry, bought and sold the same day), day filters (each checked against skipping the same number of random days), and the bot's risk rules. Base everywhere: SPY+QQQ+IWM pooled, calls, d40-55t45, premium ceiling, no target, time (b), all out 15:25, desk fills, 2% half-spread. A change is kept only if it adds expectancy after costs on DEV AND passes its own robustness checks; parameters picked here are in-sample. 58 runs.

## Exit families side by side: current plan vs best level target vs best trail

Best of each family by expectancy among runs with at least 60 trades (else the best with any trades).

| family | run | config | trades | win% | avg win | avg loss | exp $ | PF | PF 2x | max DD | CI95 exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plain stop + time | setups_v2-008@s5 | failed_break_p025 prem tpnone tb 15:25 | 218 | 6.00 | 685.69 | -26.27 | 16.18 | 1.66 | 0.79 | -1499.99 | -13.3..60.79 |
| B: best level target | setups_v2-035@s5 | failed_break leve tpB/$0.03 tc 15:25 | 34 | 11.80 | 13.55 | -22.04 | -17.86 | 0.08 | 0.00 | -645.12 | -24.79..-11.17 |
| best trail | setups_v2-032@s5 | failed_break prem tpnone tr:vwap tb 15:25 | 680 | 6.50 | 418.83 | -26.33 | 2.48 | 1.10 | 0.52 | -4335.72 | -9.78..19.12 |
| best C/D/E | setups_v2-038@s5 | failed_break prem tpD/$0.03 ta 15:25 | 681 | 13.10 | 26.57 | -22.77 | -14.55 | 0.19 | 0.04 | -9996.24 | -16.49..-12.51 |


## Fixed premium stop / target runs (Option Alpha's exit; the cross-check)

Each row: one symbol, one side, a fixed stop/target of the debit, all out 15:25. `desk` = SPRINT_PLAN's fill rules (inside the bar, same-bar stop wins); `oa1m` = OA-LIKE mechanics (checked once a minute on the close, filled at the next minute's print). `2m+` = profitable two-month blocks. `OA ref` = Option Alpha's own Stage-1 result for the same rule on SPY, Nov 2025-Jun 2026 (fills MODELED by OA, from docs/research/sprint_runs.csv); T1/T2 used OA's 1-year window. Different period, different fill model: a cross-check, not a replication.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| setups_v2-040@s5 | SPY+QQQ+IWM | failed_break | C | 20/200 | desk | d40-55t45 | - | 676 | 9.50 | -6.79 | 0.78 | 0.41 | -7038.58 | 4/12 |  |
| setups_v2-039@s5 | SPY+QQQ+IWM | failed_break | C | 20/100 | desk | d40-55t45 | - | 676 | 13.00 | -11.87 | 0.61 | 0.30 | -9047.23 | 1/12 |  |


## Robustness on the top 6 runs

### setups_v2-008@s5: failed_break_p025 prem tpnone tb 15:25

Trades 218, win 6%, avg win 685.69, avg loss -26.27, expectancy **16.18** (2x slippage -10.05), PF 1.66 (2x 0.79), max DD -1499.99, % of peak kept 0.64, planned R:R - vs actual -0.12, expectancy CI95 [-13.3, 60.79], deflated Sharpe 0.000 (N=2885).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 5 of 12 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 46 | -1113.55 | -24.21 | 0.00 |
| 2025 | 97 | 3418.82 | 35.25 | 2.48 |
| Jan-Jun 2026 | 75 | 1222.81 | 16.30 | 1.62 |
| 2m: Aug 2024-Sep 2024 | 18 | -499.30 | -27.74 | 0.00 |
| 2m: Oct 2024-Nov 2024 | 15 | -265.85 | -17.72 | 0.00 |
| 2m: Dec 2024-Jan 2025 | 22 | 296.56 | 13.48 | 1.60 |
| 2m: Feb 2025-Mar 2025 | 21 | -395.51 | -18.83 | 0.29 |
| 2m: Apr 2025-May 2025 | 21 | 3149.77 | 149.99 | 5.41 |
| 2m: Jun 2025-Jul 2025 | 9 | 15.07 | 1.67 | 1.08 |
| 2m: Aug 2025-Sep 2025 | 14 | 369.29 | 26.38 | 2.68 |
| 2m: Oct 2025-Nov 2025 | 18 | -239.14 | -13.29 | 0.36 |
| 2m: Dec 2025-Jan 2026 | 13 | -357.76 | -27.52 | 0.00 |
| 2m: Feb 2026-Mar 2026 | 35 | -29.06 | -0.83 | 0.97 |
| 2m: Apr 2026-May 2026 | 18 | -422.16 | -23.45 | 0.00 |
| 2m: Jun 2026-Jul 2026 | 14 | 1906.17 | 136.16 | 6.29 |


Sides: calls n=218 exp 16.18 PF 1.66; puts n=0 exp - PF -
Symbols: IWM n=70 exp -16.59 PF 0.10; QQQ n=63 exp 18.97 PF 1.64; SPY n=85 exp 41.11 PF 2.57
Without the best 5 trades: net -3706.67, expectancy -17.40.
One-step nudges: entry=failed_break n=680 PF 1.10 exp 2.48; allout=15:50 n=218 PF 1.67 exp 16.60
Matched random entries (5 paths): expectancy -0.05, -9.02, -13.09, -9.97, -13.06; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 205, 'ALL OUT': 13}.
Median option MFE 0.012, MAE -0.171; median stock MFE $0.226; median distance from the stock's price at the option's peak to the nearest level $0.050; median minutes held 1.0.
Skipped signals: busy: one position at a time 51, no contract with BS-EST |delta| in 0.40-0.55 29.

### setups_v2-002@s5: SPY failed_break prem tpnone tb 15:25

Trades 257, win 8%, avg win 487.80, avg loss -28.23, expectancy **13.94** (2x slippage -14.24), PF 1.54 (2x 0.72), max DD -1966.28, % of peak kept 0.51, planned R:R - vs actual -0.04, expectancy CI95 [-10.96, 53.09], deflated Sharpe 0.000 (N=2885).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 6 of 12 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 57 | -750.81 | -13.17 | 0.46 |
| 2025 | 129 | 3434.54 | 26.62 | 2.00 |
| Jan-Jun 2026 | 71 | 897.84 | 12.65 | 1.48 |
| 2m: Aug 2024-Sep 2024 | 26 | -296.50 | -11.40 | 0.57 |
| 2m: Oct 2024-Nov 2024 | 18 | -274.03 | -15.22 | 0.22 |
| 2m: Dec 2024-Jan 2025 | 22 | -169.51 | -7.70 | 0.69 |
| 2m: Feb 2025-Mar 2025 | 27 | -195.21 | -7.23 | 0.78 |
| 2m: Apr 2025-May 2025 | 24 | 2913.11 | 121.38 | 4.07 |
| 2m: Jun 2025-Jul 2025 | 12 | 167.32 | 13.94 | 1.72 |
| 2m: Aug 2025-Sep 2025 | 25 | 465.22 | 18.61 | 2.04 |
| 2m: Oct 2025-Nov 2025 | 24 | -223.24 | -9.30 | 0.60 |
| 2m: Dec 2025-Jan 2026 | 15 | 110.86 | 7.39 | 1.35 |
| 2m: Feb 2026-Mar 2026 | 36 | 935.72 | 25.99 | 1.92 |
| 2m: Apr 2026-May 2026 | 17 | 440.31 | 25.90 | 2.21 |
| 2m: Jun 2026-Jul 2026 | 11 | -292.48 | -26.59 | 0.00 |


Sides: calls n=257 exp 13.94 PF 1.54; puts n=0 exp - PF -
Symbols: SPY n=257 exp 13.94 PF 1.54
Without the best 5 trades: net -3157.28, expectancy -12.53.
One-step nudges: entry=failed_break_w3 n=249 PF 1.56 exp 14.67; entry=failed_break_w10 n=264 PF 1.49 exp 12.68; entry=failed_break_p025 n=85 PF 2.57 exp 41.11; entry=failed_break_p075 n=351 PF 1.20 exp 5.10; allout=15:50 n=257 PF 1.60 exp 15.64
Matched random entries (5 paths): expectancy -5.97, -11.00, -15.60, -12.93, -15.80; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 236, 'ALL OUT': 21}.
Median option MFE 0.037, MAE -0.170; median stock MFE $0.291; median distance from the stock's price at the option's peak to the nearest level $0.051; median minutes held 2.
Skipped signals: busy: one position at a time 60, no contract with BS-EST |delta| in 0.40-0.55 10.

### setups_v2-054@s5: failed_break prem tpnone tb 15:25 vixy_falling

Trades 293, win 10%, avg win 322.09, avg loss -24.73, expectancy **9.60** (2x slippage -14.60), PF 1.43 (2x 0.66), max DD -1297.41, % of peak kept 0.41, planned R:R - vs actual 0.05, expectancy CI95 [-4.82, 26.3], deflated Sharpe 0.000 (N=2885).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 8 of 12 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries
- [ ] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 68 | 451.33 | 6.64 | 1.30 |
| 2025 | 148 | -114.18 | -0.77 | 0.96 |
| Jan-Jun 2026 | 77 | 2474.82 | 32.14 | 2.40 |
| 2m: Aug 2024-Sep 2024 | 31 | 501.36 | 16.17 | 1.68 |
| 2m: Oct 2024-Nov 2024 | 25 | -450.91 | -18.04 | 0.00 |
| 2m: Dec 2024-Jan 2025 | 29 | 806.71 | 27.82 | 2.29 |
| 2m: Feb 2025-Mar 2025 | 18 | -329.68 | -18.32 | 0.32 |
| 2m: Apr 2025-May 2025 | 24 | -748.82 | -31.20 | 0.00 |
| 2m: Jun 2025-Jul 2025 | 22 | 25.51 | 1.16 | 1.07 |
| 2m: Aug 2025-Sep 2025 | 31 | 437.62 | 14.12 | 1.82 |
| 2m: Oct 2025-Nov 2025 | 24 | -131.72 | -5.49 | 0.78 |
| 2m: Dec 2025-Jan 2026 | 19 | 45.36 | 2.39 | 1.12 |
| 2m: Feb 2026-Mar 2026 | 26 | 498.04 | 19.16 | 1.92 |
| 2m: Apr 2026-May 2026 | 26 | 571.84 | 21.99 | 2.03 |
| 2m: Jun 2026-Jul 2026 | 18 | 1586.66 | 88.15 | 4.24 |


Sides: calls n=293 exp 9.60 PF 1.43; puts n=0 exp - PF -
Symbols: IWM n=74 exp -3.19 PF 0.79; QQQ n=97 exp 12.55 PF 1.46; SPY n=122 exp 15.01 PF 1.67
Without the best 5 trades: net -1046.18, expectancy -3.63.
One-step nudges: entry=failed_break_w3 n=282 PF 1.44 exp 9.80; entry=failed_break_w10 n=301 PF 1.38 exp 8.62; entry=failed_break_p025 n=89 PF 1.43 exp 9.39; entry=failed_break_p075 n=408 PF 1.15 exp 3.41; allout=15:50 n=293 PF 1.26 exp 5.90
Matched random entries (5 paths): expectancy -14.52, -15.74, -12.21, -16.63, -13.28; the run beats 100% of paths.
Filter vs random day-skips (twin setups_v2-001@s5, 162 days removed): p = 0.19 (filtered exp 9.6, random-skip mean 2.57).
Exit reasons: {'CEILING STOP': 264, 'ALL OUT': 29}.
Median option MFE 0.040, MAE -0.171; median stock MFE $0.280; median distance from the stock's price at the option's peak to the nearest level $0.040; median minutes held 2.
Skipped signals: VIX proxy (VIXY) not below its prior close 526, busy: one position at a time 67, no contract with BS-EST |delta| in 0.40-0.55 44.

### setups_v2-012@s5: failed_break_or prem tpnone tb 15:25

Trades 432, win 8%, avg win 444.25, avg loss -27.32, expectancy **8.71** (2x slippage -17.15), PF 1.34 (2x 0.64), max DD -2147.02, % of peak kept 0.45, planned R:R - vs actual -0.06, expectancy CI95 [-8.62, 34.04], deflated Sharpe 0.000 (N=2885).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 8 of 12 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 92 | -846.65 | -9.20 | 0.62 |
| 2025 | 208 | 4033.37 | 19.39 | 1.79 |
| Jan-Jun 2026 | 132 | 574.38 | 4.35 | 1.16 |
| 2m: Aug 2024-Sep 2024 | 43 | -458.59 | -10.66 | 0.59 |
| 2m: Oct 2024-Nov 2024 | 32 | -709.12 | -22.16 | 0.00 |
| 2m: Dec 2024-Jan 2025 | 37 | 1407.46 | 38.04 | 2.86 |
| 2m: Feb 2025-Mar 2025 | 44 | 140.11 | 3.18 | 1.11 |
| 2m: Apr 2025-May 2025 | 33 | 3042.67 | 92.20 | 3.55 |
| 2m: Jun 2025-Jul 2025 | 22 | 9.70 | 0.44 | 1.02 |
| 2m: Aug 2025-Sep 2025 | 36 | 104.63 | 2.91 | 1.18 |
| 2m: Oct 2025-Nov 2025 | 40 | -169.59 | -4.24 | 0.84 |
| 2m: Dec 2025-Jan 2026 | 31 | -660.95 | -21.32 | 0.12 |
| 2m: Feb 2026-Mar 2026 | 53 | 343.30 | 6.48 | 1.22 |
| 2m: Apr 2026-May 2026 | 39 | 585.38 | 15.01 | 1.66 |
| 2m: Jun 2026-Jul 2026 | 22 | 126.10 | 5.73 | 1.20 |


Sides: calls n=432 exp 8.71 PF 1.34; puts n=0 exp - PF -
Symbols: IWM n=121 exp -6.56 PF 0.61; QQQ n=150 exp -0.05 PF 1.00; SPY n=161 exp 28.34 PF 2.05
Without the best 5 trades: net -3217.55, expectancy -7.54.
One-step nudges: allout=15:50 n=432 PF 1.40 exp 9.98
Matched random entries (5 paths): expectancy -11.97, -12.48, -14.16, -16.25, -13.35; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 399, 'ALL OUT': 33}.
Median option MFE 0.043, MAE -0.172; median stock MFE $0.287; median distance from the stock's price at the option's peak to the nearest level $0.040; median minutes held 2.0.
Skipped signals: busy: one position at a time 124, no contract with BS-EST |delta| in 0.40-0.55 63.

### setups_v2-005@s5: SPY+QQQ failed_break prem tpnone tb 15:25

Trades 492, win 7%, avg win 469.98, avg loss -29.87, expectancy **6.70** (2x slippage -22.62), PF 1.24 (2x 0.58), max DD -3104.72, % of peak kept 0.42, planned R:R - vs actual -0.15, expectancy CI95 [-9.64, 29.39], deflated Sharpe 0.000 (N=2885).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 4 of 12 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 111 | -430.22 | -3.88 | 0.84 |
| 2025 | 245 | 2572.29 | 10.50 | 1.38 |
| Jan-Jun 2026 | 136 | 1155.34 | 8.50 | 1.28 |
| 2m: Aug 2024-Sep 2024 | 50 | -40.38 | -0.81 | 0.97 |
| 2m: Oct 2024-Nov 2024 | 42 | -806.07 | -19.19 | 0.09 |
| 2m: Dec 2024-Jan 2025 | 41 | 1247.63 | 30.43 | 2.35 |
| 2m: Feb 2025-Mar 2025 | 47 | -325.68 | -6.93 | 0.79 |
| 2m: Apr 2025-May 2025 | 41 | 2537.78 | 61.90 | 2.49 |
| 2m: Jun 2025-Jul 2025 | 21 | -48.71 | -2.32 | 0.89 |
| 2m: Aug 2025-Sep 2025 | 46 | 135.06 | 2.94 | 1.16 |
| 2m: Oct 2025-Nov 2025 | 52 | -629.79 | -12.11 | 0.55 |
| 2m: Dec 2025-Jan 2026 | 30 | -336.78 | -11.23 | 0.56 |
| 2m: Feb 2026-Mar 2026 | 66 | -161.39 | -2.45 | 0.92 |
| 2m: Apr 2026-May 2026 | 30 | -33.04 | -1.10 | 0.96 |
| 2m: Jun 2026-Jul 2026 | 26 | 1758.78 | 67.65 | 3.22 |


Sides: calls n=492 exp 6.70 PF 1.24; puts n=0 exp - PF -
Symbols: QQQ n=235 exp -1.21 PF 0.96; SPY n=257 exp 13.94 PF 1.54
Without the best 5 trades: net -4165.29, expectancy -8.55.
One-step nudges: entry=failed_break_w3 n=474 PF 1.25 exp 6.94; entry=failed_break_w10 n=500 PF 1.22 exp 6.05; entry=failed_break_p025 n=148 PF 2.15 exp 31.69; entry=failed_break_p075 n=706 PF 0.98 exp -0.44; allout=15:50 n=492 PF 1.23 exp 6.50
Matched random entries (5 paths): expectancy -9.88, -12.43, -16.72, -14.24, -15.89; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 456, 'ALL OUT': 36}.
Median option MFE 0.032, MAE -0.170; median stock MFE $0.320; median distance from the stock's price at the option's peak to the nearest level $0.051; median minutes held 2.0.
Skipped signals: busy: one position at a time 106, no contract with BS-EST |delta| in 0.40-0.55 12.

### setups_v2-050@s5: failed_break prem tpnone tb 15:25 skip_fomc_cpi

Trades 445, win 6%, avg win 417.75, avg loss -24.63, expectancy **3.21** (2x slippage -20.79), PF 1.14 (2x 0.53), max DD -2391.97, % of peak kept 0.41, planned R:R - vs actual -0.29, expectancy CI95 [-12.6, 26.99], deflated Sharpe 0.000 (N=2885).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 3 of 9 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries
- [ ] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 134 | -339.54 | -2.53 | 0.88 |
| 2025 | 311 | 1767.65 | 5.68 | 1.24 |
| Jan-Jun 2026 | 0 | - | - | - |
| 2m: Aug 2024-Sep 2024 | 57 | 115.64 | 2.03 | 1.09 |
| 2m: Oct 2024-Nov 2024 | 48 | -959.42 | -19.99 | 0.00 |
| 2m: Dec 2024-Jan 2025 | 55 | 1504.04 | 27.35 | 2.44 |
| 2m: Feb 2025-Mar 2025 | 63 | -326.85 | -5.19 | 0.81 |
| 2m: Apr 2025-May 2025 | 54 | 2407.63 | 44.59 | 2.32 |
| 2m: Jun 2025-Jul 2025 | 29 | -147.07 | -5.07 | 0.73 |
| 2m: Aug 2025-Sep 2025 | 51 | -176.46 | -3.46 | 0.79 |
| 2m: Oct 2025-Nov 2025 | 66 | -668.58 | -10.13 | 0.57 |
| 2m: Dec 2025-Jan 2026 | 22 | -320.82 | -14.58 | 0.21 |
| 2m: Feb 2026-Mar 2026 | 0 | - | - | - |
| 2m: Apr 2026-May 2026 | 0 | - | - | - |
| 2m: Jun 2026-Jul 2026 | 0 | - | - | - |


Sides: calls n=445 exp 3.21 PF 1.14; puts n=0 exp - PF -
Symbols: IWM n=114 exp -8.71 PF 0.45; QQQ n=159 exp -0.01 PF 1.00; SPY n=172 exp 14.09 PF 1.56
Without the best 5 trades: net -5138.44, expectancy -11.68.
One-step nudges: entry=failed_break_w3 n=429 PF 1.11 exp 2.65; entry=failed_break_w10 n=450 PF 1.12 exp 2.89; entry=failed_break_p025 n=132 PF 1.75 exp 17.71; entry=failed_break_p075 n=646 PF 0.90 exp -2.38; allout=15:50 n=445 PF 1.12 exp 2.86
Matched random entries (5 paths): expectancy -15.33, -13.51, -15.29, -14.59, -14.65; the run beats 100% of paths.
Filter vs random day-skips (twin setups_v2-001@s5, 105 days removed): p = 0.498 (filtered exp 3.21, random-skip mean 2.6).
Exit reasons: {'CEILING STOP': 417, 'ALL OUT': 28}.
Median option MFE 0.029, MAE -0.171; median stock MFE $0.235; median distance from the stock's price at the option's peak to the nearest level $0.042; median minutes held 2.
Skipped signals: event calendar unknown for this date 242, busy: one position at a time 98, no contract with BS-EST |delta| in 0.40-0.55 91, CPI day skipped 30, FOMC day skipped 24.

## Filters vs random day-skips (every filtered run with its unfiltered twin)

| run | config | twin | days skipped | filtered exp | random-skip exp | p |
|---|---|---|---|---|---|---|
| setups_v2-047@s5 | failed_break prem tpnone tb 15:25 noise_trend | setups_v2-001@s5 | 303 | 98.68 | 3.01 | 0.02 |
| setups_v2-048@s5 | failed_break prem tpnone tb 15:25 chop2 | setups_v2-001@s5 | 0 | 2.51 | - | - |
| setups_v2-049@s5 | failed_break prem tpnone tb 15:25 after14 | setups_v2-001@s5 | 4 | 2.79 | 2.51 | 0.38 |
| setups_v2-050@s5 | failed_break prem tpnone tb 15:25 skip_fomc_cpi | setups_v2-001@s5 | 105 | 3.21 | 2.60 | 0.50 |
| setups_v2-051@s5 | failed_break prem tpnone tb 15:25 sma20_side | setups_v2-001@s5 | 110 | -9.10 | 2.32 | 0.98 |
| setups_v2-052@s5 | failed_break prem tpnone tb 15:25 vixy_pctl_le40 | setups_v2-001@s5 | 57 | -3.83 | 2.66 | 0.95 |
| setups_v2-053@s5 | failed_break prem tpnone tb 15:25 vixy_pctl_ge60 | setups_v2-001@s5 | 297 | 43.62 | 3.18 | 0.08 |
| setups_v2-054@s5 | failed_break prem tpnone tb 15:25 vixy_falling | setups_v2-001@s5 | 162 | 9.60 | 2.57 | 0.19 |
| setups_v2-055@s5 | failed_break prem tpnone tb 15:25 vixy_not_rising | setups_v2-001@s5 | 91 | 1.09 | 2.42 | 0.66 |
| setups_v2-056@s5 | failed_break prem tpnone tb 15:25 gap_side_075 | setups_v2-001@s5 | 153 | -4.10 | 2.24 | 0.80 |


## All other runs (sorted by expectancy; fixed stop/target runs are in the cross-check table)

`sig` = signals seen, `skip%` = share not traded (no contract, level stop beyond the ceiling, R:R minimum, busy, no print); the top skip reasons per run are in the run log's notes.

| run | config | sig | skip% | n | win% | avg win | avg loss | exp | PF | PF2x | maxDD | kept | pRR | aRR | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| setups_v2-047@s5 | failed_break prem tpnone tb 15:25 noise_trend | 930 | 96.77 | 30 | 3.30 | 3863.50 | -31.14 | 98.68 | 4.28 | 2.04 | -540.53 | 0.91 | - | 0.38 | 0.00 |
| setups_v2-053@s5 | failed_break prem tpnone tb 15:25 vixy_pctl_ge60 | 930 | 94.19 | 54 | 3.70 | 2118.20 | -36.18 | 43.62 | 2.25 | 1.09 | -1368.51 | 0.74 | - | -0.08 | 0.00 |
| setups_v2-034@s5 | failed_break leve tpnone tb 15:25 | 930 | 96.34 | 34 | 8.80 | 672.45 | -30.09 | 31.90 | 2.16 | 1.01 | -711.17 | 0.67 | - | 0.23 | 0.00 |
| setups_v2-008@s5 | failed_break_p025 prem tpnone tb 15:25 | 298 | 26.85 | 218 | 6.00 | 685.69 | -26.27 | 16.18 | 1.66 | 0.79 | -1499.99 | 0.64 | - | -0.12 | 0.00 |
| setups_v2-002@s5 | SPY failed_break prem tpnone tb 15:25 | 327 | 21.41 | 257 | 8.20 | 487.80 | -28.23 | 13.94 | 1.54 | 0.72 | -1966.28 | 0.51 | - | -0.04 | 0.00 |
| setups_v2-054@s5 | failed_break prem tpnone tb 15:25 vixy_falling | 930 | 68.49 | 293 | 9.90 | 322.09 | -24.73 | 9.60 | 1.43 | 0.66 | -1297.41 | 0.41 | - | 0.05 | 0.00 |
| setups_v2-012@s5 | failed_break_or prem tpnone tb 15:25 | 619 | 30.21 | 432 | 7.60 | 444.25 | -27.32 | 8.71 | 1.34 | 0.64 | -2147.02 | 0.45 | - | -0.06 | 0.00 |
| setups_v2-005@s5 | SPY+QQQ failed_break prem tpnone tb 15:25 | 610 | 19.34 | 492 | 7.30 | 469.98 | -29.87 | 6.70 | 1.24 | 0.58 | -3104.72 | 0.42 | - | -0.15 | 0.00 |
| setups_v2-050@s5 | failed_break prem tpnone tb 15:25 skip_fomc_cpi | 930 | 52.15 | 445 | 6.30 | 417.75 | -24.63 | 3.21 | 1.14 | 0.53 | -2391.97 | 0.41 | - | -0.29 | 0.00 |
| setups_v2-049@s5 | failed_break prem tpnone tb 15:25 after14 | 930 | 28.49 | 665 | 6.60 | 418.83 | -26.69 | 2.79 | 1.11 | 0.52 | -4286.82 | 0.39 | - | -0.23 | 0.00 |
| setups_v2-006@s5 | failed_break_w3 prem tpnone tb 15:25 | 889 | 26.32 | 655 | 6.30 | 434.82 | -26.32 | 2.55 | 1.10 | 0.52 | -4521.54 | 0.38 | - | -0.26 | 0.00 |
| setups_v2-048@s5 | failed_break prem tpnone tb 15:25 chop2 | 930 | 27.31 | 676 | 6.40 | 427.05 | -26.33 | 2.51 | 1.10 | 0.52 | -4386.65 | 0.39 | - | -0.25 | 0.00 |
| setups_v2-001@s5 | failed_break prem tpnone tb 15:25 | 930 | 26.88 | 680 | 6.50 | 418.83 | -26.33 | 2.48 | 1.10 | 0.52 | -4335.72 | 0.38 | - | -0.25 | 0.00 |
| setups_v2-032@s5 | failed_break prem tpnone tr:vwap tb 15:25 | 930 | 26.88 | 680 | 6.50 | 418.83 | -26.33 | 2.48 | 1.10 | 0.52 | -4335.72 | 0.38 | - | -0.25 | 0.00 |
| setups_v2-033@s5 | failed_break prem tpnone tr:ema9 tb 15:25 | 930 | 26.88 | 680 | 6.50 | 418.83 | -26.33 | 2.48 | 1.10 | 0.52 | -4335.72 | 0.38 | - | -0.25 | 0.00 |
| setups_v2-041@s5 | failed_break prem tpnone tb 15:50 | 930 | 26.88 | 680 | 6.20 | 437.36 | -26.35 | 2.29 | 1.09 | 0.51 | -4107.25 | 0.37 | - | -0.27 | 0.00 |
| setups_v2-007@s5 | failed_break_w10 prem tpnone tb 15:25 | 947 | 27.03 | 691 | 6.40 | 418.83 | -26.39 | 1.96 | 1.08 | 0.51 | -4534.61 | 0.38 | - | -0.27 | 0.00 |
| setups_v2-055@s5 | failed_break prem tpnone tb 15:25 vixy_not_rising | 930 | 53.23 | 435 | 7.40 | 322.62 | -24.44 | 1.09 | 1.05 | 0.49 | -3215.67 | 0.32 | - | -0.22 | 0.00 |
| setups_v2-043@s5 | failed_break prem tpnone tb 15:25 d45-60t50 | 930 | 27.31 | 676 | 6.40 | 456.04 | -31.35 | -0.35 | 0.99 | 0.46 | -5547.84 | 0.35 | - | -0.33 | 0.00 |
| setups_v2-058@s5 | SPY+QQQ failed_break prem tpnone tb 15:25 risk:bot | 610 | 31.80 | 416 | 7.20 | 336.29 | -27.00 | -0.80 | 0.97 | 0.44 | -2469.40 | 0.32 | - | -0.22 | 0.00 |
| setups_v2-003@s5 | QQQ failed_break prem tpnone tb 15:25 | 283 | 16.96 | 235 | 6.40 | 445.04 | -31.64 | -1.21 | 0.96 | 0.45 | -3535.93 | 0.32 | - | -0.28 | 0.00 |
| setups_v2-057@s5 | failed_break prem tpnone tb 15:25 risk:bot | 930 | 38.92 | 568 | 6.70 | 305.21 | -23.76 | -1.76 | 0.92 | 0.42 | -3489.07 | 0.30 | - | -0.27 | 0.00 |
| setups_v2-009@s5 | failed_break_p075 prem tpnone tb 15:25 | 1345 | 27.66 | 973 | 5.70 | 377.57 | -26.09 | -3.27 | 0.87 | 0.40 | -6614.80 | 0.28 | - | -0.39 | 0.00 |
| setups_v2-010@s5 | failed_break_p100 prem tpnone tb 15:25 | 1534 | 28.49 | 1097 | 5.70 | 362.35 | -25.76 | -3.47 | 0.86 | 0.40 | -7842.56 | 0.27 | - | -0.39 | 0.00 |
| setups_v2-042@s5 | failed_break prem tpnone tb 15:25 d50-65t575 | 930 | 25.91 | 689 | 7.10 | 454.36 | -38.65 | -3.58 | 0.90 | 0.41 | -6773.49 | 0.32 | - | -0.36 | 0.00 |
| setups_v2-052@s5 | failed_break prem tpnone tb 15:25 vixy_pctl_le40 | 930 | 39.46 | 563 | 6.40 | 303.48 | -24.82 | -3.83 | 0.83 | 0.39 | -5199.01 | 0.25 | - | -0.33 | 0.00 |
| setups_v2-056@s5 | failed_break prem tpnone tb 15:25 gap_side_075 | 930 | 67.53 | 302 | 6.30 | 288.02 | -23.72 | -4.10 | 0.81 | 0.37 | -2611.08 | 0.26 | - | -0.38 | 0.00 |
| setups_v2-015@s5 | failed_break prem tpnone tc 15:25 | 930 | 26.88 | 680 | 6.00 | 296.67 | -23.59 | -4.28 | 0.81 | 0.37 | -5716.34 | 0.32 | - | -0.31 | 0.00 |
| setups_v2-016@s5 | failed_break prem tpnone td 15:25 | 930 | 26.88 | 680 | 6.00 | 296.67 | -23.59 | -4.28 | 0.81 | 0.37 | -5716.34 | 0.32 | - | -0.31 | 0.00 |
| setups_v2-030@s5 | failed_break prem tpnone tr:hl5m tb 15:25 | 930 | 26.77 | 681 | 9.50 | 191.18 | -25.95 | -5.23 | 0.78 | 0.28 | -5641.12 | 0.27 | - | -0.44 | 0.00 |
| setups_v2-020@s5 | failed_break prem tpnone tr:be15 tb 15:25 | 930 | 26.88 | 680 | 3.40 | 349.46 | -25.26 | -8.24 | 0.59 | 0.24 | -7681.44 | 0.25 | - | -0.42 | 0.00 |
| setups_v2-004@s5 | IWM failed_break prem tpnone tb 15:25 | 320 | 41.25 | 188 | 4.30 | 188.62 | -17.34 | -8.57 | 0.48 | 0.23 | -1962.32 | 0.09 | - | -0.52 | 0.00 |
| setups_v2-011@s5 | failed_break_pd prem tpnone tb 15:25 | 311 | 13.18 | 270 | 4.40 | 337.81 | -24.82 | -8.70 | 0.63 | 0.28 | -4892.15 | 0.19 | - | -0.60 | 0.00 |
| setups_v2-051@s5 | failed_break prem tpnone tb 15:25 sma20_side | 930 | 57.42 | 396 | 4.50 | 281.67 | -22.95 | -9.10 | 0.58 | 0.27 | -4842.23 | 0.12 | - | -0.50 | 0.00 |
| setups_v2-019@s5 | failed_break prem tpnone tr:be10 tb 15:25 | 930 | 26.77 | 681 | 2.60 | 348.46 | -24.96 | -10.11 | 0.48 | 0.18 | -8504.11 | 0.22 | - | -0.47 | 0.00 |
| setups_v2-014@s5 | failed_break prem tpnone ta 15:25 | 930 | 26.77 | 681 | 2.50 | 303.20 | -22.77 | -10.72 | 0.41 | 0.16 | -8251.96 | 0.22 | - | -0.48 | 0.00 |
| setups_v2-018@s5 | failed_break prem tpnone tr:be8 tb 15:25 | 930 | 26.77 | 681 | 2.20 | 327.28 | -24.74 | -11.87 | 0.38 | 0.14 | -9351.46 | 0.16 | - | -0.53 | 0.00 |
| setups_v2-023@s5 | failed_break prem tpnone tr:L2 tb 15:25 | 930 | 26.88 | 680 | 21.90 | 36.72 | -25.64 | -11.98 | 0.40 | 0.09 | -8273.67 | 0.17 | - | -0.49 | 0.00 |
| setups_v2-017@s5 | failed_break prem tpnone tr:be6 tb 15:25 | 930 | 26.77 | 681 | 1.90 | 302.33 | -24.42 | -12.62 | 0.31 | 0.12 | -8942.26 | 0.14 | - | -0.54 | 0.00 |
| setups_v2-024@s5 | failed_break prem tpnone tr:L3 tb 15:25 | 930 | 26.88 | 680 | 19.60 | 41.37 | -25.97 | -12.80 | 0.39 | 0.07 | -9091.23 | 0.12 | - | -0.54 | 0.00 |
| setups_v2-044@s5 | failed_break prem tpnone tb 15:25 n1d40-55t45 | 930 | 20.22 | 742 | 11.10 | 235.06 | -43.72 | -12.91 | 0.67 | 0.28 | -11048.16 | 0.25 | - | -0.46 | 0.00 |
| setups_v2-029@s5 | failed_break prem tpnone tr:hl1m tb 15:25 | 930 | 26.77 | 681 | 13.80 | 59.36 | -24.85 | -13.22 | 0.38 | 0.08 | -9372.18 | 0.10 | - | -0.57 | 0.00 |
| setups_v2-022@s5 | failed_break prem tpnone tr:L1 tb 15:25 | 930 | 26.88 | 680 | 20.10 | 34.34 | -25.94 | -13.80 | 0.33 | 0.04 | -9441.90 | 0.09 | - | -0.56 | 0.00 |
| setups_v2-038@s5 | failed_break prem tpD/$0.03 ta 15:25 | 930 | 26.77 | 681 | 13.10 | 26.57 | -22.77 | -14.55 | 0.19 | 0.04 | -9996.24 | 0.03 | -0.51 | -0.58 | 0.00 |
| setups_v2-021@s5 | failed_break prem tpnone tr:belevel tb 15:25 | 930 | 26.67 | 682 | 0.90 | 184.63 | -19.34 | -14.91 | 0.10 | 0.03 | -10169.87 | -0.06 | -0.47 | -0.59 | 0.00 |
| setups_v2-028@s5 | failed_break prem tpnone tr:gb60 tb 15:25 | 930 | 26.77 | 681 | 19.80 | 10.75 | -21.41 | -15.03 | 0.12 | 0.01 | -10248.92 | 0.02 | - | -0.58 | 0.00 |
| setups_v2-013@s5 | failed_high prem tpnone tb 15:25 | 1232 | 28.65 | 879 | 2.50 | 394.76 | -25.60 | -15.08 | 0.40 | 0.19 | -14743.01 | -0.03 | - | -0.62 | 0.00 |
| setups_v2-031@s5 | failed_break prem tpnone tr:lvl tb 15:25 | 930 | 26.77 | 681 | 16.90 | 23.58 | -23.17 | -15.28 | 0.21 | 0.01 | -10410.63 | -0.01 | - | -0.60 | 0.00 |
| setups_v2-025@s5 | failed_break prem tpnone tr:gb30 tb 15:25 | 930 | 26.77 | 681 | 20.00 | 8.67 | -21.44 | -15.42 | 0.10 | 0.00 | -10524.79 | -0.04 | - | -0.60 | 0.00 |
| setups_v2-027@s5 | failed_break prem tpnone tr:gb50 tb 15:25 | 930 | 26.77 | 681 | 19.80 | 8.79 | -21.41 | -15.42 | 0.10 | 0.00 | -10516.27 | -0.03 | - | -0.60 | 0.00 |
| setups_v2-026@s5 | failed_break prem tpnone tr:gb40 tb 15:25 | 930 | 26.77 | 681 | 20.00 | 8.67 | -21.44 | -15.43 | 0.10 | 0.00 | -10522.52 | -0.03 | - | -0.60 | 0.00 |
| setups_v2-037@s5 | failed_break leve tpE/$0.03 tc 15:25 | 930 | 96.34 | 34 | 11.80 | 25.53 | -22.98 | -17.27 | 0.15 | 0.04 | -679.36 | 0.03 | -0.43 | -0.57 | 0.00 |
| setups_v2-035@s5 | failed_break leve tpB/$0.03 tc 15:25 | 930 | 96.34 | 34 | 11.80 | 13.55 | -22.04 | -17.86 | 0.08 | 0.00 | -645.12 | 0.33 | -0.43 | -0.56 | 0.00 |
| setups_v2-036@s5 | failed_break leve tpC/$0.03 tc 15:25 | 930 | 96.34 | 34 | 14.70 | 8.28 | -22.67 | -18.12 | 0.06 | 0.00 | -631.60 | -0.01 | -0.43 | -0.55 | 0.00 |
| setups_v2-045@s5 | failed_break prem tpnone tb 15:25 n1d50-65t575 | 930 | 23.98 | 707 | 14.30 | 242.14 | -66.70 | -22.58 | 0.60 | 0.25 | -16150.63 | 0.26 | - | -0.49 | 0.00 |
| setups_v2-046@s5 | failed_break prem tpnone tb 15:25 trend_only | 930 | 100.00 | 0 | - | - | - | - | - | - | - | - | - | - | - |


Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_setups_v2@s5_2026-10-31.csv.gz`.

Labels: BACKTEST (in-sample on DEV). Spread: MODELED-SPREAD 5.0% (sensitivity). Delta: BS-EST. Not financial advice: evidence for Nick to decide.
