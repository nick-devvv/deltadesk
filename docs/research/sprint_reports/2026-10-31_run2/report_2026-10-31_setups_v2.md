# Sprint report: setups_v2 (DEV), MODELED-SPREAD

Generated 2026-10-31 12:17 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint1` in 3.7 min. Spec sha256 `2b3d90478447efffffb748223d893f71529c2565713379225e2d32f0e77a6f26`.

**Every number below is a BACKTEST in-sample (DEV)** on Alpaca 1-minute bars, 2024-08-01 to 2026-06-30. Option fills are real traded prices +/- a half-spread: **MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Deltas are BS-EST (Black-Scholes from the option's price). Nothing here is a live or paper fill.

Data: IWM: 479 sessions, QQQ: 479 sessions, SPY: 479 sessions. Runs in this spec: 58. Trials counted for the deflated Sharpe: 2827 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Known limits: July 2024 is locked (L2), so early-August 2024 sessions have partial history; news and VIX are unknown in the backtest (rules that need them never fire); a contract needs BS-EST |delta| inside the band, so some signals have no contract (counted as skips).

**Cost caveat:** MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: Failed-break deep dive (pre-registered 2026-10-31, after setups_v1 and before any v2 run). setups_v1-049 (failed_break calls, premium-ceiling stop, no target, all out 15:25; PF 1.47, PF 2x 1.03) is the only v1 run with PF >= 1.25, but it lost in Aug-Dec 2024 and is negative without its best 5 trades. This spec changes ONE thing at a time on that run: symbols (SPY+QQQ is an IN-SAMPLE choice made after seeing IWM lose), the entry's own numbers (re-close window, probe depth, which levels), the put mirror (failed_high), time rules, trails, level take-profits, fixed far targets, contracts (incl. the next listed expiry, bought and sold the same day), day filters (each checked against skipping the same number of random days), and the bot's risk rules. Base everywhere: SPY+QQQ+IWM pooled, calls, d40-55t45, premium ceiling, no target, time (b), all out 15:25, desk fills, 2% half-spread. A change is kept only if it adds expectancy after costs on DEV AND passes its own robustness checks; parameters picked here are in-sample. 58 runs.

## Exit families side by side: current plan vs best level target vs best trail

Best of each family by expectancy among runs with at least 60 trades (else the best with any trades).

| family | run | config | trades | win% | avg win | avg loss | exp $ | PF | PF 2x | max DD | CI95 exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plain stop + time | setups_v2-034 | failed_break leve tpnone tb 15:25 | 207 | 10.10 | 579.77 | -27.77 | 33.87 | 2.36 | 1.66 | -1411.48 | -2.39..83.97 |
| B: best level target | setups_v2-035 | failed_break leve tpB/$0.03 tc 15:25 | 209 | 29.20 | 11.01 | -15.92 | -8.06 | 0.28 | 0.10 | -1727.96 | -10.57..-5.63 |
| best trail | setups_v2-032 | failed_break prem tpnone tr:vwap tb 15:25 | 676 | 8.90 | 384.90 | -25.47 | 10.95 | 1.47 | 1.03 | -2122.93 | -2.8..28.57 |
| best C/D/E | setups_v2-037 | failed_break leve tpE/$0.03 tc 15:25 | 207 | 21.70 | 44.16 | -17.90 | -4.41 | 0.69 | 0.40 | -1273.68 | -10.27..3.55 |


## Fixed premium stop / target runs (Option Alpha's exit; the cross-check)

Each row: one symbol, one side, a fixed stop/target of the debit, all out 15:25. `desk` = SPRINT_PLAN's fill rules (inside the bar, same-bar stop wins); `oa1m` = OA-LIKE mechanics (checked once a minute on the close, filled at the next minute's print). `2m+` = profitable two-month blocks. `OA ref` = Option Alpha's own Stage-1 result for the same rule on SPY, Nov 2025-Jun 2026 (fills MODELED by OA, from docs/research/sprint_runs.csv); T1/T2 used OA's 1-year window. Different period, different fill model: a cross-check, not a replication.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| setups_v2-040 | SPY+QQQ+IWM | failed_break | C | 20/200 | desk | d40-55t45 | - | 673 | 10.10 | -0.42 | 0.98 | 0.72 | -4055.42 | 5/12 |  |
| setups_v2-039 | SPY+QQQ+IWM | failed_break | C | 20/100 | desk | d40-55t45 | - | 673 | 14.40 | -4.53 | 0.82 | 0.60 | -4897.07 | 3/12 |  |


## Robustness on the top 6 runs

### setups_v2-034: failed_break leve tpnone tb 15:25

Trades 207, win 10%, avg win 579.77, avg loss -27.77, expectancy **33.87** (2x slippage 22.54), PF 2.36 (2x 1.66), max DD -1411.48, % of peak kept 0.48, planned R:R - vs actual 0.57, expectancy CI95 [-2.39, 83.97], deflated Sharpe 0.000 (N=2827).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 7 of 12 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 38 | -272.58 | -7.17 | 0.70 |
| 2025 | 111 | 4328.76 | 39.00 | 2.56 |
| Jan-Jun 2026 | 58 | 2954.42 | 50.94 | 3.00 |
| 2m: Aug 2024-Sep 2024 | 20 | -324.30 | -16.21 | 0.41 |
| 2m: Oct 2024-Nov 2024 | 9 | -197.75 | -21.97 | 0.00 |
| 2m: Dec 2024-Jan 2025 | 18 | 775.80 | 43.10 | 2.96 |
| 2m: Feb 2025-Mar 2025 | 29 | 606.73 | 20.92 | 1.75 |
| 2m: Apr 2025-May 2025 | 22 | 3342.37 | 151.93 | 5.97 |
| 2m: Jun 2025-Jul 2025 | 8 | -181.36 | -22.67 | 0.00 |
| 2m: Aug 2025-Sep 2025 | 15 | 49.85 | 3.32 | 1.20 |
| 2m: Oct 2025-Nov 2025 | 19 | -447.48 | -23.55 | 0.00 |
| 2m: Dec 2025-Jan 2026 | 14 | 292.30 | 20.88 | 1.92 |
| 2m: Feb 2026-Mar 2026 | 28 | -174.05 | -6.22 | 0.80 |
| 2m: Apr 2026-May 2026 | 15 | 895.31 | 59.69 | 4.14 |
| 2m: Jun 2026-Jul 2026 | 10 | 2373.18 | 237.32 | 13.00 |


Sides: calls n=207 exp 33.87 PF 2.36; puts n=0 exp - PF -
Symbols: IWM n=47 exp 13.47 PF 1.76; QQQ n=68 exp 40.70 PF 2.42; SPY n=92 exp 39.24 PF 2.51
Without the best 5 trades: net -376.92, expectancy -1.87.
One-step nudges: entry=failed_break_w3 n=207 PF 2.36 exp 33.87; entry=failed_break_w10 n=208 PF 2.34 exp 33.55; entry=failed_break_p025 n=109 PF 3.19 exp 53.90; entry=failed_break_p075 n=223 PF 2.19 exp 30.05; allout=15:50 n=206 PF 2.31 exp 33.20
Matched random entries (5 paths): expectancy 17.93, -22.59, -25.19, 29.65, -29.43; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 134, 'LEVEL STOP': 52, 'ALL OUT': 21}.
Median option MFE 0.088, MAE -0.187; median stock MFE $0.440; median distance from the stock's price at the option's peak to the nearest level $0.045; median minutes held 6.
Skipped signals: level stop does not fit 573, no contract with BS-EST |delta| in 0.40-0.55 102, busy: one position at a time 48.

### setups_v2-008: failed_break_p025 prem tpnone tb 15:25

Trades 217, win 7%, avg win 636.60, avg loss -25.48, expectancy **23.34** (2x slippage 13.23), PF 1.99 (2x 1.41), max DD -1236.13, % of peak kept 0.44, planned R:R - vs actual 0.08, expectancy CI95 [-8.38, 69.85], deflated Sharpe 0.000 (N=2827).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 6 of 12 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 45 | -1057.59 | -23.50 | 0.00 |
| 2025 | 97 | 3998.46 | 41.22 | 2.79 |
| Jan-Jun 2026 | 75 | 2124.10 | 28.32 | 2.16 |
| 2m: Aug 2024-Sep 2024 | 18 | -483.79 | -26.88 | 0.00 |
| 2m: Oct 2024-Nov 2024 | 14 | -235.31 | -16.81 | 0.00 |
| 2m: Dec 2024-Jan 2025 | 22 | 354.47 | 16.11 | 1.74 |
| 2m: Feb 2025-Mar 2025 | 21 | -115.67 | -5.51 | 0.78 |
| 2m: Apr 2025-May 2025 | 21 | 3324.28 | 158.30 | 5.82 |
| 2m: Jun 2025-Jul 2025 | 9 | 30.30 | 3.37 | 1.17 |
| 2m: Aug 2025-Sep 2025 | 14 | 406.58 | 29.04 | 2.91 |
| 2m: Oct 2025-Nov 2025 | 18 | -218.62 | -12.15 | 0.40 |
| 2m: Dec 2025-Jan 2026 | 13 | -346.82 | -26.68 | 0.00 |
| 2m: Feb 2026-Mar 2026 | 35 | 707.61 | 20.22 | 1.82 |
| 2m: Apr 2026-May 2026 | 18 | -391.45 | -21.75 | 0.00 |
| 2m: Jun 2026-Jul 2026 | 14 | 2033.39 | 145.24 | 6.81 |


Sides: calls n=217 exp 23.34 PF 1.99; puts n=0 exp - PF -
Symbols: IWM n=70 exp -11.98 PF 0.31; QQQ n=62 exp 33.63 PF 2.20; SPY n=85 exp 44.92 PF 2.77
Without the best 5 trades: net -2486.43, expectancy -11.73.
One-step nudges: entry=failed_break n=676 PF 1.47 exp 10.95; allout=15:50 n=217 PF 1.97 exp 23.22
Matched random entries (5 paths): expectancy 4.55, -7.57, -6.90, -8.18, -5.59; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 200, 'ALL OUT': 17}.
Median option MFE 0.080, MAE -0.196; median stock MFE $0.320; median distance from the stock's price at the option's peak to the nearest level $0.050; median minutes held 5.
Skipped signals: busy: one position at a time 52, no contract with BS-EST |delta| in 0.40-0.55 29.

### setups_v2-002: SPY failed_break prem tpnone tb 15:25

Trades 257, win 10%, avg win 454.78, avg loss -27.35, expectancy **19.55** (2x slippage 8.73), PF 1.79 (2x 1.26), max DD -1673.33, % of peak kept 0.34, planned R:R - vs actual 0.15, expectancy CI95 [-6.74, 60.37], deflated Sharpe 0.000 (N=2827).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 7 of 12 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 57 | -659.92 | -11.58 | 0.51 |
| 2025 | 129 | 4067.70 | 31.53 | 2.23 |
| Jan-Jun 2026 | 71 | 1616.40 | 22.77 | 1.95 |
| 2m: Aug 2024-Sep 2024 | 26 | -245.01 | -9.42 | 0.64 |
| 2m: Oct 2024-Nov 2024 | 18 | -255.66 | -14.20 | 0.25 |
| 2m: Dec 2024-Jan 2025 | 22 | -127.26 | -5.78 | 0.76 |
| 2m: Feb 2025-Mar 2025 | 27 | 58.49 | 2.17 | 1.07 |
| 2m: Apr 2025-May 2025 | 24 | 3090.91 | 128.79 | 4.35 |
| 2m: Jun 2025-Jul 2025 | 12 | 201.96 | 16.83 | 1.89 |
| 2m: Aug 2025-Sep 2025 | 25 | 534.34 | 21.37 | 2.23 |
| 2m: Oct 2025-Nov 2025 | 24 | -182.33 | -7.60 | 0.67 |
| 2m: Dec 2025-Jan 2026 | 15 | 151.91 | 10.13 | 1.50 |
| 2m: Feb 2026-Mar 2026 | 36 | 1279.41 | 35.54 | 2.35 |
| 2m: Apr 2026-May 2026 | 17 | 558.06 | 32.83 | 2.62 |
| 2m: Jun 2026-Jul 2026 | 11 | -40.64 | -3.69 | 0.82 |


Sides: calls n=257 exp 19.55 PF 1.79; puts n=0 exp - PF -
Symbols: SPY n=257 exp 19.55 PF 1.79
Without the best 5 trades: net -2009.66, expectancy -7.97.
One-step nudges: entry=failed_break_w3 n=249 PF 1.82 exp 20.41; entry=failed_break_w10 n=264 PF 1.73 exp 18.17; entry=failed_break_p025 n=85 PF 2.77 exp 44.92; entry=failed_break_p075 n=349 PF 1.39 exp 9.75; allout=15:50 n=257 PF 1.87 exp 21.65
Matched random entries (5 paths): expectancy 2.64, -9.67, -13.16, -8.39, -7.76; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 232, 'ALL OUT': 25}.
Median option MFE 0.124, MAE -0.197; median stock MFE $0.510; median distance from the stock's price at the option's peak to the nearest level $0.051; median minutes held 7.
Skipped signals: busy: one position at a time 60, no contract with BS-EST |delta| in 0.40-0.55 10.

### setups_v2-012: failed_break_or prem tpnone tb 15:25

Trades 429, win 10%, avg win 402.52, avg loss -26.43, expectancy **18.57** (2x slippage 8.60), PF 1.78 (2x 1.27), max DD -1452.16, % of peak kept 0.33, planned R:R - vs actual 0.28, expectancy CI95 [-0.88, 45.2], deflated Sharpe 0.000 (N=2827).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [x] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 10 of 12 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 91 | -609.27 | -6.70 | 0.71 |
| 2025 | 206 | 6426.62 | 31.20 | 2.35 |
| Jan-Jun 2026 | 132 | 2148.76 | 16.28 | 1.65 |
| 2m: Aug 2024-Sep 2024 | 43 | -312.58 | -7.27 | 0.70 |
| 2m: Oct 2024-Nov 2024 | 31 | -665.98 | -21.48 | 0.00 |
| 2m: Dec 2024-Jan 2025 | 37 | 1550.83 | 41.91 | 3.11 |
| 2m: Feb 2025-Mar 2025 | 43 | 1020.88 | 23.74 | 1.89 |
| 2m: Apr 2025-May 2025 | 32 | 3305.26 | 103.29 | 3.98 |
| 2m: Jun 2025-Jul 2025 | 22 | 46.97 | 2.13 | 1.12 |
| 2m: Aug 2025-Sep 2025 | 36 | 174.14 | 4.84 | 1.31 |
| 2m: Oct 2025-Nov 2025 | 40 | 229.74 | 5.74 | 1.23 |
| 2m: Dec 2025-Jan 2026 | 31 | 1.44 | 0.05 | 1.00 |
| 2m: Feb 2026-Mar 2026 | 53 | 947.67 | 17.88 | 1.65 |
| 2m: Apr 2026-May 2026 | 39 | 1220.04 | 31.28 | 2.50 |
| 2m: Jun 2026-Jul 2026 | 22 | 447.70 | 20.35 | 1.80 |


Sides: calls n=429 exp 18.57 PF 1.78; puts n=0 exp - PF -
Symbols: IWM n=120 exp 1.28 PF 1.08; QQQ n=148 exp 15.14 PF 1.55; SPY n=161 exp 34.60 PF 2.34
Without the best 5 trades: net 687.55, expectancy 1.62.
One-step nudges: allout=15:50 n=428 PF 1.80 exp 19.02
Matched random entries (5 paths): expectancy -5.36, -10.43, -9.98, -11.73, -7.04; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 383, 'ALL OUT': 46}.
Median option MFE 0.139, MAE -0.200; median stock MFE $0.475; median distance from the stock's price at the option's peak to the nearest level $0.040; median minutes held 7.
Skipped signals: busy: one position at a time 127, no contract with BS-EST |delta| in 0.40-0.55 63.

### setups_v2-005: SPY+QQQ failed_break prem tpnone tb 15:25

Trades 489, win 10%, avg win 432.91, avg loss -28.94, expectancy **16.40** (2x slippage 5.10), PF 1.63 (2x 1.14), max DD -1693.70, % of peak kept 0.30, planned R:R - vs actual 0.16, expectancy CI95 [-1.78, 40.75], deflated Sharpe 0.000 (N=2827).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [x] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 8 of 12 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 110 | -108.66 | -0.99 | 0.96 |
| 2025 | 243 | 4423.32 | 18.20 | 1.69 |
| Jan-Jun 2026 | 136 | 3702.84 | 27.23 | 1.97 |
| 2m: Aug 2024-Sep 2024 | 50 | 162.29 | 3.25 | 1.13 |
| 2m: Oct 2024-Nov 2024 | 41 | -748.59 | -18.26 | 0.10 |
| 2m: Dec 2024-Jan 2025 | 41 | 1402.13 | 34.20 | 2.57 |
| 2m: Feb 2025-Mar 2025 | 47 | -19.00 | -0.40 | 0.99 |
| 2m: Apr 2025-May 2025 | 40 | 2801.99 | 70.05 | 2.74 |
| 2m: Jun 2025-Jul 2025 | 21 | -7.93 | -0.38 | 0.98 |
| 2m: Aug 2025-Sep 2025 | 45 | 249.40 | 5.54 | 1.32 |
| 2m: Oct 2025-Nov 2025 | 52 | -436.91 | -8.40 | 0.67 |
| 2m: Dec 2025-Jan 2026 | 30 | 513.90 | 17.13 | 1.77 |
| 2m: Feb 2026-Mar 2026 | 66 | 1321.55 | 20.02 | 1.69 |
| 2m: Apr 2026-May 2026 | 30 | 604.11 | 20.14 | 1.78 |
| 2m: Jun 2026-Jul 2026 | 26 | 2174.56 | 83.64 | 4.04 |


Sides: calls n=489 exp 16.40 PF 1.63; puts n=0 exp - PF -
Symbols: QQQ n=232 exp 12.90 PF 1.47; SPY n=257 exp 19.55 PF 1.79
Without the best 5 trades: net 231.52, expectancy 0.48.
One-step nudges: entry=failed_break_w3 n=471 PF 1.64 exp 16.76; entry=failed_break_w10 n=497 PF 1.59 exp 15.60; entry=failed_break_p025 n=147 PF 2.51 exp 40.16; entry=failed_break_p075 n=698 PF 1.29 exp 7.70; allout=15:50 n=489 PF 1.63 exp 16.48
Matched random entries (5 paths): expectancy -1.97, -10.54, -12.12, -8.65, -7.60; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 441, 'ALL OUT': 48}.
Median option MFE 0.124, MAE -0.198; median stock MFE $0.520; median distance from the stock's price at the option's peak to the nearest level $0.054; median minutes held 6.
Skipped signals: busy: one position at a time 109, no contract with BS-EST |delta| in 0.40-0.55 12.

### setups_v2-054: failed_break prem tpnone tb 15:25 vixy_falling

Trades 291, win 12%, avg win 314.04, avg loss -23.82, expectancy **15.66** (2x slippage 6.38), PF 1.74 (2x 1.22), max DD -1198.84, % of peak kept 0.31, planned R:R - vs actual 0.29, expectancy CI95 [-0.4, 33.73], deflated Sharpe 0.000 (N=2827).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [x] profitable in each stretch
- [x] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 8 of 12 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries
- [ ] filter beats random day-skips

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 68 | 692.08 | 10.18 | 1.49 |
| 2025 | 146 | 789.53 | 5.41 | 1.26 |
| Jan-Jun 2026 | 77 | 3075.06 | 39.94 | 2.86 |
| 2m: Aug 2024-Sep 2024 | 31 | 682.35 | 22.01 | 2.01 |
| 2m: Oct 2024-Nov 2024 | 25 | -437.10 | -17.48 | 0.00 |
| 2m: Dec 2024-Jan 2025 | 29 | 912.65 | 31.47 | 2.50 |
| 2m: Feb 2025-Mar 2025 | 18 | -303.40 | -16.86 | 0.35 |
| 2m: Apr 2025-May 2025 | 23 | -682.82 | -29.69 | 0.00 |
| 2m: Jun 2025-Jul 2025 | 22 | 61.01 | 2.77 | 1.17 |
| 2m: Aug 2025-Sep 2025 | 30 | 543.11 | 18.10 | 2.10 |
| 2m: Oct 2025-Nov 2025 | 24 | -81.29 | -3.39 | 0.86 |
| 2m: Dec 2025-Jan 2026 | 19 | 610.55 | 32.13 | 2.93 |
| 2m: Feb 2026-Mar 2026 | 26 | 572.31 | 22.01 | 2.08 |
| 2m: Apr 2026-May 2026 | 26 | 710.49 | 27.33 | 2.34 |
| 2m: Jun 2026-Jul 2026 | 18 | 1968.81 | 109.38 | 5.70 |


Sides: calls n=291 exp 15.66 PF 1.74; puts n=0 exp - PF -
Symbols: IWM n=74 exp -1.99 PF 0.87; QQQ n=95 exp 23.14 PF 1.90; SPY n=122 exp 20.54 PF 1.97
Without the best 5 trades: net 507.51, expectancy 1.77.
One-step nudges: entry=failed_break_w3 n=280 PF 1.74 exp 15.76; entry=failed_break_w10 n=299 PF 1.69 exp 14.53; entry=failed_break_p025 n=89 PF 1.55 exp 11.70; entry=failed_break_p075 n=403 PF 1.47 exp 10.23; allout=15:50 n=291 PF 1.60 exp 12.61
Matched random entries (5 paths): expectancy -6.29, -14.11, -8.17, -9.76, -3.30; the run beats 100% of paths.
Filter vs random day-skips (twin setups_v2-001, 162 days removed): p = 0.302 (filtered exp 15.66, random-skip mean 11.06).
Exit reasons: {'CEILING STOP': 257, 'ALL OUT': 34}.
Median option MFE 0.142, MAE -0.192; median stock MFE $0.450; median distance from the stock's price at the option's peak to the nearest level $0.040; median minutes held 7.
Skipped signals: VIX proxy (VIXY) not below its prior close 526, busy: one position at a time 69, no contract with BS-EST |delta| in 0.40-0.55 44.

## Filters vs random day-skips (every filtered run with its unfiltered twin)

| run | config | twin | days skipped | filtered exp | random-skip exp | p |
|---|---|---|---|---|---|---|
| setups_v2-047 | failed_break prem tpnone tb 15:25 noise_trend | setups_v2-001 | 303 | 108.89 | 11.92 | 0.02 |
| setups_v2-048 | failed_break prem tpnone tb 15:25 chop2 | setups_v2-001 | 0 | 11.01 | - | - |
| setups_v2-049 | failed_break prem tpnone tb 15:25 after14 | setups_v2-001 | 4 | 11.34 | 10.98 | 0.34 |
| setups_v2-050 | failed_break prem tpnone tb 15:25 skip_fomc_cpi | setups_v2-001 | 105 | 9.19 | 11.06 | 0.65 |
| setups_v2-051 | failed_break prem tpnone tb 15:25 sma20_side | setups_v2-001 | 110 | -2.49 | 10.74 | 0.99 |
| setups_v2-052 | failed_break prem tpnone tb 15:25 vixy_pctl_le40 | setups_v2-001 | 57 | 4.57 | 11.13 | 0.94 |
| setups_v2-053 | failed_break prem tpnone tb 15:25 vixy_pctl_ge60 | setups_v2-001 | 297 | 49.61 | 11.58 | 0.10 |
| setups_v2-054 | failed_break prem tpnone tb 15:25 vixy_falling | setups_v2-001 | 162 | 15.66 | 11.06 | 0.30 |
| setups_v2-055 | failed_break prem tpnone tb 15:25 vixy_not_rising | setups_v2-001 | 91 | 7.09 | 10.91 | 0.76 |
| setups_v2-056 | failed_break prem tpnone tb 15:25 gap_side_075 | setups_v2-001 | 153 | 0.10 | 10.68 | 0.92 |


## All other runs (sorted by expectancy; fixed stop/target runs are in the cross-check table)

`sig` = signals seen, `skip%` = share not traded (no contract, level stop beyond the ceiling, R:R minimum, busy, no print); the top skip reasons per run are in the run log's notes.

| run | config | sig | skip% | n | win% | avg win | avg loss | exp | PF | PF2x | maxDD | kept | pRR | aRR | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| setups_v2-047 | failed_break prem tpnone tb 15:25 noise_trend | 930 | 96.88 | 29 | 3.40 | 4014.22 | -30.58 | 108.89 | 4.69 | 3.31 | -501.42 | 0.73 | - | 0.52 | 0.00 |
| setups_v2-053 | failed_break prem tpnone tb 15:25 vixy_pctl_ge60 | 930 | 94.30 | 53 | 3.80 | 2206.70 | -34.98 | 49.61 | 2.47 | 1.76 | -1248.93 | 0.55 | - | 0.01 | 0.00 |
| setups_v2-034 | failed_break leve tpnone tb 15:25 | 930 | 77.74 | 207 | 10.10 | 579.77 | -27.77 | 33.87 | 2.36 | 1.66 | -1411.48 | 0.48 | - | 0.57 | 0.00 |
| setups_v2-008 | failed_break_p025 prem tpnone tb 15:25 | 298 | 27.18 | 217 | 7.40 | 636.60 | -25.48 | 23.34 | 1.99 | 1.41 | -1236.13 | 0.44 | - | 0.08 | 0.00 |
| setups_v2-002 | SPY failed_break prem tpnone tb 15:25 | 327 | 21.41 | 257 | 9.70 | 454.78 | -27.35 | 19.55 | 1.79 | 1.26 | -1673.33 | 0.34 | - | 0.15 | 0.00 |
| setups_v2-012 | failed_break_or prem tpnone tb 15:25 | 619 | 30.69 | 429 | 10.50 | 402.52 | -26.43 | 18.57 | 1.78 | 1.27 | -1452.16 | 0.33 | - | 0.28 | 0.00 |
| setups_v2-005 | SPY+QQQ failed_break prem tpnone tb 15:25 | 610 | 19.84 | 489 | 9.80 | 432.91 | -28.94 | 16.40 | 1.63 | 1.14 | -1693.70 | 0.30 | - | 0.16 | 0.00 |
| setups_v2-054 | failed_break prem tpnone tb 15:25 vixy_falling | 930 | 68.71 | 291 | 11.70 | 314.04 | -23.82 | 15.66 | 1.74 | 1.22 | -1198.84 | 0.31 | - | 0.29 | 0.00 |
| setups_v2-003 | QQQ failed_break prem tpnone tb 15:25 | 283 | 18.02 | 232 | 9.90 | 409.14 | -30.70 | 12.90 | 1.47 | 1.03 | -1202.73 | 0.26 | - | 0.17 | 0.00 |
| setups_v2-049 | failed_break prem tpnone tb 15:25 after14 | 930 | 28.92 | 661 | 8.90 | 390.55 | -25.83 | 11.34 | 1.48 | 1.04 | -2079.17 | 0.27 | - | 0.06 | 0.00 |
| setups_v2-006 | failed_break_w3 prem tpnone tb 15:25 | 889 | 26.77 | 651 | 8.60 | 400.25 | -25.48 | 11.14 | 1.48 | 1.04 | -2396.81 | 0.27 | - | 0.04 | 0.00 |
| setups_v2-048 | failed_break prem tpnone tb 15:25 chop2 | 930 | 27.74 | 672 | 8.80 | 390.07 | -25.48 | 11.01 | 1.47 | 1.04 | -2122.93 | 0.27 | - | 0.05 | 0.00 |
| setups_v2-001 | failed_break prem tpnone tb 15:25 | 930 | 27.31 | 676 | 8.90 | 384.90 | -25.47 | 10.95 | 1.47 | 1.03 | -2122.93 | 0.27 | - | 0.04 | 0.00 |
| setups_v2-032 | failed_break prem tpnone tr:vwap tb 15:25 | 930 | 27.31 | 676 | 8.90 | 384.90 | -25.47 | 10.95 | 1.47 | 1.03 | -2122.93 | 0.27 | - | 0.04 | 0.00 |
| setups_v2-033 | failed_break prem tpnone tr:ema9 tb 15:25 | 930 | 27.31 | 676 | 8.90 | 384.90 | -25.47 | 10.95 | 1.47 | 1.03 | -2122.93 | 0.27 | - | 0.04 | 0.00 |
| setups_v2-043 | failed_break prem tpnone tb 15:25 d45-60t50 | 930 | 27.74 | 672 | 9.70 | 396.93 | -30.48 | 10.86 | 1.39 | 0.98 | -2754.55 | 0.26 | - | 0.02 | 0.00 |
| setups_v2-041 | failed_break prem tpnone tb 15:50 | 930 | 27.42 | 675 | 8.30 | 406.85 | -25.52 | 10.35 | 1.44 | 1.01 | -1995.91 | 0.25 | - | 0.04 | 0.00 |
| setups_v2-007 | failed_break_w10 prem tpnone tb 15:25 | 947 | 27.46 | 687 | 8.70 | 384.90 | -25.54 | 10.31 | 1.44 | 1.01 | -2275.23 | 0.26 | - | 0.03 | 0.00 |
| setups_v2-050 | failed_break prem tpnone tb 15:25 skip_fomc_cpi | 930 | 52.58 | 441 | 8.20 | 382.16 | -23.96 | 9.19 | 1.42 | 1.00 | -1949.70 | 0.27 | - | -0.03 | 0.00 |
| setups_v2-042 | failed_break prem tpnone tb 15:25 d50-65t575 | 930 | 26.56 | 683 | 10.10 | 409.28 | -37.51 | 7.62 | 1.23 | 0.86 | -4510.66 | 0.23 | - | -0.11 | 0.00 |
| setups_v2-055 | failed_break prem tpnone tb 15:25 vixy_not_rising | 930 | 53.44 | 433 | 9.50 | 300.91 | -23.65 | 7.09 | 1.33 | 0.93 | -2088.89 | 0.23 | - | 0.03 | 0.00 |
| setups_v2-058 | SPY+QQQ failed_break prem tpnone tb 15:25 risk:bot | 610 | 30.66 | 423 | 9.50 | 320.32 | -26.77 | 6.05 | 1.25 | 0.87 | -1466.22 | 0.20 | - | 0.07 | 0.00 |
| setups_v2-015 | failed_break prem tpnone tc 15:25 | 930 | 27.31 | 676 | 8.00 | 306.40 | -21.08 | 5.08 | 1.26 | 0.87 | -2371.97 | 0.24 | - | 0.01 | 0.00 |
| setups_v2-016 | failed_break prem tpnone td 15:25 | 930 | 27.31 | 676 | 8.00 | 306.40 | -21.08 | 5.08 | 1.26 | 0.87 | -2371.97 | 0.24 | - | 0.01 | 0.00 |
| setups_v2-057 | failed_break prem tpnone tb 15:25 risk:bot | 930 | 37.96 | 577 | 8.70 | 300.84 | -23.45 | 4.65 | 1.22 | 0.85 | -1699.90 | 0.20 | - | 0.01 | 0.00 |
| setups_v2-052 | failed_break prem tpnone tb 15:25 vixy_pctl_le40 | 930 | 39.78 | 560 | 8.90 | 295.91 | -24.00 | 4.57 | 1.21 | 0.85 | -2050.79 | 0.18 | - | -0.03 | 0.00 |
| setups_v2-009 | failed_break_p075 prem tpnone tb 15:25 | 1345 | 28.48 | 962 | 8.00 | 346.18 | -25.29 | 4.45 | 1.19 | 0.84 | -2973.61 | 0.19 | - | -0.10 | 0.00 |
| setups_v2-010 | failed_break_p100 prem tpnone tb 15:25 | 1534 | 29.34 | 1084 | 8.10 | 330.76 | -24.95 | 3.92 | 1.17 | 0.82 | -3931.59 | 0.18 | - | -0.11 | 0.00 |
| setups_v2-044 | failed_break prem tpnone tb 15:25 n1d40-55t45 | 930 | 22.58 | 720 | 17.60 | 216.97 | -42.01 | 3.67 | 1.11 | 0.75 | -3690.80 | 0.21 | - | -0.11 | 0.00 |
| setups_v2-030 | failed_break prem tpnone tr:hl5m tb 15:25 | 930 | 27.20 | 677 | 14.30 | 163.75 | -24.53 | 2.45 | 1.12 | 0.70 | -2650.60 | 0.18 | - | -0.18 | 0.00 |
| setups_v2-020 | failed_break prem tpnone tr:be15 tb 15:25 | 930 | 27.20 | 677 | 4.70 | 339.86 | -24.17 | 0.78 | 1.05 | 0.62 | -3317.86 | 0.18 | - | -0.10 | 0.00 |
| setups_v2-056 | failed_break prem tpnone tb 15:25 gap_side_075 | 930 | 67.74 | 300 | 8.00 | 264.93 | -22.93 | 0.10 | 1.00 | 0.70 | -1867.71 | 0.13 | - | -0.22 | 0.00 |
| setups_v2-045 | failed_break prem tpnone tb 15:25 n1d50-65t575 | 930 | 27.63 | 673 | 21.00 | 236.59 | -63.81 | -0.88 | 0.98 | 0.66 | -5367.80 | 0.21 | - | -0.18 | 0.00 |
| setups_v2-019 | failed_break prem tpnone tr:be10 tb 15:25 | 930 | 27.20 | 677 | 3.80 | 317.28 | -23.28 | -1.19 | 0.91 | 0.50 | -3087.23 | 0.16 | - | -0.13 | 0.00 |
| setups_v2-018 | failed_break prem tpnone tr:be8 tb 15:25 | 930 | 27.20 | 677 | 3.70 | 313.41 | -22.62 | -1.33 | 0.90 | 0.49 | -3303.31 | 0.17 | - | -0.13 | 0.00 |
| setups_v2-014 | failed_break prem tpnone ta 15:25 | 930 | 27.20 | 677 | 3.70 | 301.56 | -19.92 | -1.54 | 0.88 | 0.49 | -3409.89 | 0.18 | - | -0.13 | 0.00 |
| setups_v2-011 | failed_break_pd prem tpnone tb 15:25 | 311 | 13.18 | 270 | 6.30 | 321.72 | -24.09 | -2.32 | 0.90 | 0.62 | -3480.23 | 0.09 | - | -0.36 | 0.00 |
| setups_v2-051 | failed_break prem tpnone tb 15:25 sma20_side | 930 | 57.63 | 394 | 7.10 | 255.59 | -22.23 | -2.49 | 0.88 | 0.62 | -2987.38 | 0.08 | - | -0.21 | 0.00 |
| setups_v2-022 | failed_break prem tpnone tr:L1 tb 15:25 | 930 | 27.31 | 676 | 33.90 | 41.04 | -24.90 | -2.56 | 0.84 | 0.41 | -3254.11 | 0.16 | - | -0.13 | 0.00 |
| setups_v2-004 | IWM failed_break prem tpnone tb 15:25 | 320 | 41.56 | 187 | 6.40 | 192.83 | -16.74 | -3.29 | 0.79 | 0.56 | -1319.70 | 0.07 | - | -0.25 | 0.00 |
| setups_v2-029 | failed_break prem tpnone tr:hl1m tb 15:25 | 930 | 27.20 | 677 | 22.30 | 60.85 | -22.50 | -3.91 | 0.78 | 0.41 | -3319.30 | 0.09 | - | -0.22 | 0.00 |
| setups_v2-037 | failed_break leve tpE/$0.03 tc 15:25 | 930 | 77.74 | 207 | 21.70 | 44.16 | -17.90 | -4.41 | 0.69 | 0.40 | -1273.68 | 0.24 | -0.14 | -0.20 | 0.00 |
| setups_v2-017 | failed_break prem tpnone tr:be6 tb 15:25 | 930 | 27.20 | 677 | 2.50 | 310.71 | -21.22 | -4.42 | 0.64 | 0.34 | -5057.43 | 0.09 | - | -0.24 | 0.00 |
| setups_v2-024 | failed_break prem tpnone tr:L3 tb 15:25 | 930 | 27.31 | 676 | 30.90 | 41.57 | -25.04 | -4.44 | 0.74 | 0.36 | -4101.86 | 0.08 | - | -0.21 | 0.00 |
| setups_v2-021 | failed_break prem tpnone tr:belevel tb 15:25 | 930 | 26.99 | 679 | 2.40 | 283.10 | -18.66 | -4.46 | 0.60 | 0.30 | -4803.35 | 0.10 | -0.16 | -0.21 | 0.00 |
| setups_v2-023 | failed_break prem tpnone tr:L2 tb 15:25 | 930 | 27.20 | 677 | 37.80 | 26.49 | -24.55 | -5.25 | 0.66 | 0.28 | -4389.15 | 0.07 | - | -0.23 | 0.00 |
| setups_v2-028 | failed_break prem tpnone tr:gb60 tb 15:25 | 930 | 26.77 | 681 | 37.60 | 10.55 | -15.27 | -5.55 | 0.42 | 0.10 | -4064.08 | 0.11 | - | -0.21 | 0.00 |
| setups_v2-026 | failed_break prem tpnone tr:gb40 tb 15:25 | 930 | 26.77 | 681 | 37.60 | 10.26 | -15.27 | -5.65 | 0.41 | 0.09 | -3945.44 | 0.12 | - | -0.21 | 0.00 |
| setups_v2-027 | failed_break prem tpnone tr:gb50 tb 15:25 | 930 | 26.77 | 681 | 37.60 | 10.27 | -15.27 | -5.65 | 0.41 | 0.09 | -3909.02 | 0.12 | - | -0.22 | 0.00 |
| setups_v2-025 | failed_break prem tpnone tr:gb30 tb 15:25 | 930 | 26.77 | 681 | 37.60 | 10.22 | -15.27 | -5.67 | 0.40 | 0.08 | -4021.89 | 0.12 | - | -0.21 | 0.00 |
| setups_v2-031 | failed_break prem tpnone tr:lvl tb 15:25 | 930 | 26.99 | 679 | 28.70 | 25.87 | -19.25 | -6.29 | 0.54 | 0.20 | -4365.78 | 0.04 | - | -0.23 | 0.00 |
| setups_v2-038 | failed_break prem tpD/$0.03 ta 15:25 | 930 | 27.20 | 677 | 22.70 | 25.68 | -19.67 | -6.53 | 0.47 | 0.23 | -4538.34 | 0.04 | -0.21 | -0.27 | 0.00 |
| setups_v2-036 | failed_break leve tpC/$0.03 tc 15:25 | 930 | 77.63 | 208 | 29.80 | 14.54 | -17.49 | -7.94 | 0.35 | 0.12 | -1677.77 | 0.03 | -0.14 | -0.29 | 0.00 |
| setups_v2-035 | failed_break leve tpB/$0.03 tc 15:25 | 930 | 77.53 | 209 | 29.20 | 11.01 | -15.92 | -8.06 | 0.28 | 0.10 | -1727.96 | 0.14 | -0.14 | -0.31 | 0.00 |
| setups_v2-013 | failed_high prem tpnone tb 15:25 | 1232 | 29.22 | 872 | 4.10 | 343.00 | -24.82 | -9.63 | 0.59 | 0.42 | -10125.18 | -0.06 | - | -0.39 | 0.00 |
| setups_v2-046 | failed_break prem tpnone tb 15:25 trend_only | 930 | 100.00 | 0 | - | - | - | - | - | - | - | - | - | - | - |


Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_setups_v2_2026-10-31.csv.gz`.

Labels: BACKTEST (in-sample on DEV). Spread: MODELED-SPREAD. Delta: BS-EST. Not financial advice: evidence for Nick to decide.
