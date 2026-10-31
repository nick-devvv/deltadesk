# Sprint report: setups_v1 (DEV), MODELED-SPREAD

Generated 2026-10-31 06:33 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint1` in 6.2 min. Spec sha256 `9fc7cf14c0b7e30e737aa72b6424d27ce4a3fc1462e939879c043dfc6ccce648`.

**Every number below is a BACKTEST in-sample (DEV)** on Alpaca 1-minute bars, 2024-08-01 to 2026-06-30. Option fills are real traded prices +/- a half-spread: **MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Deltas are BS-EST (Black-Scholes from the option's price). Nothing here is a live or paper fill.

Data: IWM: 479 sessions, QQQ: 479 sessions, SPY: 479 sessions. Runs in this spec: 58. Trials counted for the deflated Sharpe: 1424 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Known limits: July 2024 is locked (L2), so early-August 2024 sessions have partial history; news and VIX are unknown in the backtest (rules that need them never fire); a contract needs BS-EST |delta| inside the band, so some signals have no contract (counted as skips).

**Cost caveat:** MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: Every implemented non-ORB entry (pre-registered in sprint/entries.py) with the same six exits, on DEV, SPY+QQQ+IWM pooled per run, calls and puts as separate runs (failed-break is calls only): (1) plain: the entry window's premium ceiling + all out 15:25; (2) plan A, the time-of-day table; (3) plan B, sell just before the first level, $0.03 buffer, level stop, no R:R minimum, time (c); (4) the same with R:R >= 2 on the stock and the option; (5) giveback 40% trail on B's base (no target); (6) fixed premium stop/target 20/60 of the debit (Option Alpha's 1:3 shape, desk fills). The noise band also runs with the noise ledger's own exit (band/VWAP stop at the half-hour checks, reversal, 20% ceiling every minute, delta 0.55-0.75), and its twin runs with that exit minus the per-minute 20% ceiling (the twin differs from noise only inside that exit, so it isn't repeated with the six). Contract d40-55t45 for the six exits. 58 runs. First look at these setups: nothing tuned.

## Exit families side by side: current plan vs best level target vs best trail

Best of each family by expectancy among runs with at least 60 trades (else the best with any trades).

| family | run | config | trades | win% | avg win | avg loss | exp $ | PF | PF 2x | max DD | CI95 exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plain stop + time | setups_v1-049 | failed_break prem tpnone tb 15:25 | 676 | 8.90 | 384.90 | -25.47 | 10.95 | 1.47 | 1.03 | -2122.93 | -2.8..28.57 |
| A: current fixed-% plan | setups_v1-002 | noise prem tpA ta 15:25 | 1621 | 22.20 | 16.81 | -11.30 | -3.54 | 0.51 | 0.22 | -5792.43 | -4.51..-2.5 |
| B: best level target | setups_v1-009 | noise leve tpB/$0.03 tc 15:25 | 104 | 38.50 | 16.56 | -17.88 | -4.63 | 0.58 | 0.26 | -561.51 | -9.63..1.36 |
| best trail | setups_v1-011 | noise leve tpnone tr:gb40 tc 15:25 | 104 | 41.30 | 14.97 | -18.07 | -4.41 | 0.58 | 0.15 | -536.96 | -9.27..1.58 |


## Fixed premium stop / target runs (Option Alpha's exit; the cross-check)

Each row: one symbol, one side, a fixed stop/target of the debit, all out 15:25. `desk` = SPRINT_PLAN's fill rules (inside the bar, same-bar stop wins); `oa1m` = OA-LIKE mechanics (checked once a minute on the close, filled at the next minute's print). `2m+` = profitable two-month blocks. `OA ref` = Option Alpha's own Stage-1 result for the same rule on SPY, Nov 2025-Jun 2026 (fills MODELED by OA, from docs/research/sprint_runs.csv); T1/T2 used OA's 1-year window. Different period, different fill model: a cross-check, not a replication.

| run | sym | entry | side | stop/tgt | mech | contract | filter | n | win% | exp $ | PF | PF 2x | max DD | 2m+ | OA ref |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| setups_v1-054 | SPY+QQQ+IWM | failed_break | C | 20/60 | desk | d40-55t45 | - | 673 | 22.30 | -5.48 | 0.77 | 0.54 | -5008.31 | 3/12 |  |
| setups_v1-042 | SPY+QQQ+IWM | flush | C | 20/60 | desk | d40-55t45 | - | 562 | 21.90 | -5.88 | 0.73 | 0.51 | -3772.25 | 1/12 |  |
| setups_v1-048 | SPY+QQQ+IWM | flush | P | 20/60 | desk | d40-55t45 | - | 346 | 19.70 | -6.79 | 0.68 | 0.47 | -2348.17 | 2/12 |  |
| setups_v1-006 | SPY+QQQ+IWM | noise | C | 20/60 | desk | d40-55t45 | - | 1364 | 24.10 | -4.48 | 0.73 | 0.51 | -6350.01 | 0/12 |  |
| setups_v1-012 | SPY+QQQ+IWM | noise | P | 20/60 | desk | d40-55t45 | - | 1608 | 22.90 | -6.02 | 0.72 | 0.50 | -9928.53 | 1/12 |  |
| setups_v1-030 | SPY+QQQ+IWM | pd_retest | C | 20/60 | desk | d40-55t45 | - | 59 | 13.60 | -15.86 | 0.33 | 0.23 | -935.65 | 2/12 |  |
| setups_v1-036 | SPY+QQQ+IWM | pd_retest | P | 20/60 | desk | d40-55t45 | - | 47 | 19.10 | -6.70 | 0.68 | 0.48 | -524.11 | 4/12 |  |
| setups_v1-018 | SPY+QQQ+IWM | vwap_macd | C | 20/60 | desk | d40-55t45 | - | 299 | 19.40 | -8.74 | 0.59 | 0.41 | -2778.87 | 1/12 |  |
| setups_v1-024 | SPY+QQQ+IWM | vwap_macd | P | 20/60 | desk | d40-55t45 | - | 297 | 25.60 | -5.97 | 0.72 | 0.50 | -1836.88 | 4/12 |  |


## Robustness on the top 5 runs

### setups_v1-049: failed_break prem tpnone tb 15:25

Trades 676, win 9%, avg win 384.90, avg loss -25.47, expectancy **10.95** (2x slippage 1.09), PF 1.47 (2x 1.03), max DD -2122.93, % of peak kept 0.27, planned R:R - vs actual 0.04, expectancy CI95 [-2.8, 28.57], deflated Sharpe 0.000 (N=1424).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [x] PF >= 1.25
- [x] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [x] both sides profitable (sides traded)
- [x] profitable two-month blocks: 9 of 12 (info)
- [x] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 146 | -196.89 | -1.35 | 0.94 |
| 2025 | 333 | 4233.68 | 12.71 | 1.54 |
| Jan-Jun 2026 | 197 | 3364.62 | 17.08 | 1.69 |
| 2m: Aug 2024-Sep 2024 | 66 | 37.42 | 0.57 | 1.02 |
| 2m: Oct 2024-Nov 2024 | 50 | -792.03 | -15.84 | 0.14 |
| 2m: Dec 2024-Jan 2025 | 59 | 1542.92 | 26.15 | 2.34 |
| 2m: Feb 2025-Mar 2025 | 66 | 389.33 | 5.90 | 1.22 |
| 2m: Apr 2025-May 2025 | 59 | 2377.56 | 40.30 | 2.17 |
| 2m: Jun 2025-Jul 2025 | 33 | -159.84 | -4.84 | 0.73 |
| 2m: Aug 2025-Sep 2025 | 54 | 149.19 | 2.76 | 1.17 |
| 2m: Oct 2025-Nov 2025 | 68 | -322.21 | -4.74 | 0.79 |
| 2m: Dec 2025-Jan 2026 | 46 | 281.18 | 6.11 | 1.31 |
| 2m: Feb 2026-Mar 2026 | 90 | 856.18 | 9.51 | 1.36 |
| 2m: Apr 2026-May 2026 | 49 | 1026.32 | 20.95 | 1.97 |
| 2m: Jun 2026-Jul 2026 | 36 | 2015.39 | 55.98 | 3.31 |


Sides: calls n=676 exp 10.95 PF 1.47; puts n=0 exp - PF -
Symbols: IWM n=187 exp -3.29 PF 0.79; QQQ n=232 exp 12.90 PF 1.47; SPY n=257 exp 19.55 PF 1.79
Without the best 5 trades: net -384.57, expectancy -0.57.
One-step nudges: allout=15:50 n=675 PF 1.44 exp 10.35
Matched random entries (5 paths): expectancy -2.26, -10.04, -9.44, -7.20, -7.62; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 615, 'ALL OUT': 61}.
Median option MFE 0.113, MAE -0.196; median stock MFE $0.430; median distance from the stock's price at the option's peak to the nearest level $0.049; median minutes held 5.5.
Skipped signals: busy: one position at a time 153, no contract with BS-EST |delta| in 0.40-0.55 101.

### setups_v1-019: vwap_macd prem tpnone tb 15:25

Trades 297, win 9%, avg win 259.78, avg loss -22.04, expectancy **2.63** (2x slippage -6.18), PF 1.13 (2x 0.78), max DD -2368.56, % of peak kept 0.12, planned R:R - vs actual 0.26, expectancy CI95 [-9.95, 17.88], deflated Sharpe 0.000 (N=1424).

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
| Aug-Dec 2024 | 59 | -64.11 | -1.09 | 0.94 |
| 2025 | 164 | 1082.65 | 6.60 | 1.33 |
| Jan-Jun 2026 | 74 | -237.95 | -3.22 | 0.86 |
| 2m: Aug 2024-Sep 2024 | 23 | -353.32 | -15.36 | 0.23 |
| 2m: Oct 2024-Nov 2024 | 28 | 277.60 | 9.91 | 1.61 |
| 2m: Dec 2024-Jan 2025 | 25 | -373.15 | -14.93 | 0.25 |
| 2m: Feb 2025-Mar 2025 | 18 | -393.53 | -21.86 | 0.00 |
| 2m: Apr 2025-May 2025 | 28 | -937.40 | -33.48 | 0.00 |
| 2m: Jun 2025-Jul 2025 | 29 | -259.79 | -8.96 | 0.41 |
| 2m: Aug 2025-Sep 2025 | 33 | 590.87 | 17.91 | 2.24 |
| 2m: Oct 2025-Nov 2025 | 27 | 2506.72 | 92.84 | 6.42 |
| 2m: Dec 2025-Jan 2026 | 19 | -187.25 | -9.86 | 0.45 |
| 2m: Feb 2026-Mar 2026 | 25 | -87.84 | -3.51 | 0.80 |
| 2m: Apr 2026-May 2026 | 27 | -353.83 | -13.10 | 0.41 |
| 2m: Jun 2026-Jul 2026 | 15 | 351.51 | 23.43 | 1.75 |


Sides: calls n=0 exp - PF -; puts n=297 exp 2.63 PF 1.13
Symbols: IWM n=72 exp -6.04 PF 0.51; QQQ n=116 exp 7.27 PF 1.31; SPY n=109 exp 3.41 PF 1.16
Without the best 5 trades: net -2815.75, expectancy -9.64.
One-step nudges: allout=15:50 n=297 PF 1.01 exp 0.26
Matched random entries (5 paths): expectancy -11.67, -3.33, -8.57, -0.59, -16.41; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 271, 'ALL OUT': 26}.
Median option MFE 0.112, MAE -0.184; median stock MFE $0.300; median distance from the stock's price at the option's peak to the nearest level $0.040; median minutes held 5.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 74, no contract traded in the 5 minutes before the signal 1.

### setups_v1-043: flush prem tpnone tb 15:25

Trades 346, win 5%, avg win 337.27, avg loss -19.46, expectancy **-2.96** (2x slippage -11.48), PF 0.84 (2x 0.56), max DD -2538.28, % of peak kept 0.06, planned R:R - vs actual -0.53, expectancy CI95 [-15.67, 15.29], deflated Sharpe 0.000 (N=1424).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 3 of 12 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 79 | -964.81 | -12.21 | 0.35 |
| 2025 | 176 | 1262.06 | 7.17 | 1.40 |
| Jan-Jun 2026 | 91 | -1321.31 | -14.52 | 0.26 |
| 2m: Aug 2024-Sep 2024 | 38 | -793.20 | -20.87 | 0.00 |
| 2m: Oct 2024-Nov 2024 | 27 | 54.62 | 2.02 | 1.12 |
| 2m: Dec 2024-Jan 2025 | 24 | -313.02 | -13.04 | 0.12 |
| 2m: Feb 2025-Mar 2025 | 34 | -858.26 | -25.24 | 0.08 |
| 2m: Apr 2025-May 2025 | 43 | 2970.11 | 69.07 | 5.16 |
| 2m: Jun 2025-Jul 2025 | 40 | -449.94 | -11.25 | 0.25 |
| 2m: Aug 2025-Sep 2025 | 19 | 85.59 | 4.50 | 1.29 |
| 2m: Oct 2025-Nov 2025 | 19 | -289.38 | -15.23 | 0.00 |
| 2m: Dec 2025-Jan 2026 | 16 | -159.30 | -9.96 | 0.33 |
| 2m: Feb 2026-Mar 2026 | 27 | -25.20 | -0.93 | 0.95 |
| 2m: Apr 2026-May 2026 | 48 | -955.54 | -19.91 | 0.01 |
| 2m: Jun 2026-Jul 2026 | 11 | -290.54 | -26.41 | 0.00 |


Sides: calls n=0 exp - PF -; puts n=346 exp -2.96 PF 0.84
Symbols: IWM n=81 exp -6.84 PF 0.50; QQQ n=125 exp -0.61 PF 0.97; SPY n=140 exp -2.81 PF 0.85
Without the best 5 trades: net -4663.58, expectancy -13.68.
One-step nudges: allout=15:50 n=346 PF 0.71 exp -5.38
Matched random entries (5 paths): expectancy -14.87, -11.37, -7.93, -14.14, -9.48; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 330, 'ALL OUT': 16}.
Median option MFE 0.093, MAE -0.183; median stock MFE $0.300; median distance from the stock's price at the option's peak to the nearest level $0.050; median minutes held 4.0.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 87.

### setups_v1-002: noise prem tpA ta 15:25

Trades 1621, win 22%, avg win 16.81, avg loss -11.30, expectancy **-3.54** (2x slippage -9.66), PF 0.51 (2x 0.22), max DD -5792.43, % of peak kept 0.08, planned R:R - vs actual -0.31, expectancy CI95 [-4.51, -2.5], deflated Sharpe 0.000 (N=1424).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 0 of 12 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [x] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 300 | -1016.41 | -3.39 | 0.50 |
| 2025 | 761 | -2028.90 | -2.67 | 0.61 |
| Jan-Jun 2026 | 560 | -2691.66 | -4.81 | 0.42 |
| 2m: Aug 2024-Sep 2024 | 58 | -100.03 | -1.72 | 0.72 |
| 2m: Oct 2024-Nov 2024 | 165 | -803.04 | -4.87 | 0.35 |
| 2m: Dec 2024-Jan 2025 | 134 | -363.03 | -2.71 | 0.58 |
| 2m: Feb 2025-Mar 2025 | 90 | -517.30 | -5.75 | 0.33 |
| 2m: Apr 2025-May 2025 | 130 | -117.01 | -0.90 | 0.90 |
| 2m: Jun 2025-Jul 2025 | 154 | -147.14 | -0.96 | 0.79 |
| 2m: Aug 2025-Sep 2025 | 131 | -75.91 | -0.58 | 0.88 |
| 2m: Oct 2025-Nov 2025 | 165 | -844.12 | -5.12 | 0.36 |
| 2m: Dec 2025-Jan 2026 | 109 | -394.05 | -3.62 | 0.42 |
| 2m: Feb 2026-Mar 2026 | 153 | -692.00 | -4.52 | 0.47 |
| 2m: Apr 2026-May 2026 | 236 | -1091.06 | -4.62 | 0.38 |
| 2m: Jun 2026-Jul 2026 | 96 | -592.28 | -6.17 | 0.44 |


Sides: calls n=1621 exp -3.54 PF 0.51; puts n=0 exp - PF -
Symbols: IWM n=375 exp -3.09 PF 0.45; QQQ n=638 exp -3.54 PF 0.56; SPY n=608 exp -3.81 PF 0.49
Without the best 5 trades: net -6170.02, expectancy -3.82.
One-step nudges: allout=15:50 n=1621 PF 0.51 exp -3.54
Matched random entries (5 paths): expectancy -5.22, -4.58, -4.59, -4.84, -4.72; the run beats 100% of paths.
Exit reasons: {'CEILING STOP': 824, 'T1': 352, 'BREAKEVEN STOP': 258, 'IF FLAT': 187}.
Median option MFE 0.078, MAE -0.096; median stock MFE $0.175; median distance from the stock's price at the option's peak to the nearest level $0.040; median minutes held 1.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 670, busy: one position at a time 1.

### setups_v1-055: noise nois tpnone tb 15:25

Trades 996, win 18%, avg win 137.31, avg loss -34.48, expectancy **-3.61** (2x slippage -15.75), PF 0.87 (2x 0.59), max DD -4821.39, % of peak kept 0.09, planned R:R - vs actual -0.17, expectancy CI95 [-12.25, 8.67], deflated Sharpe 0.000 (N=1424).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 2 of 12 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 217 | -1905.83 | -8.78 | 0.63 |
| 2025 | 452 | 318.15 | 0.70 | 1.02 |
| Jan-Jun 2026 | 327 | -2006.32 | -6.14 | 0.80 |
| 2m: Aug 2024-Sep 2024 | 43 | -1377.11 | -32.03 | 0.04 |
| 2m: Oct 2024-Nov 2024 | 129 | -1392.00 | -10.79 | 0.52 |
| 2m: Dec 2024-Jan 2025 | 85 | 469.89 | 5.53 | 1.28 |
| 2m: Feb 2025-Mar 2025 | 57 | -1224.88 | -21.49 | 0.36 |
| 2m: Apr 2025-May 2025 | 58 | 3660.61 | 63.11 | 2.25 |
| 2m: Jun 2025-Jul 2025 | 91 | -736.32 | -8.09 | 0.59 |
| 2m: Aug 2025-Sep 2025 | 89 | -346.50 | -3.89 | 0.83 |
| 2m: Oct 2025-Nov 2025 | 89 | -163.52 | -1.84 | 0.94 |
| 2m: Dec 2025-Jan 2026 | 83 | -820.29 | -9.88 | 0.59 |
| 2m: Feb 2026-Mar 2026 | 92 | -781.51 | -8.49 | 0.76 |
| 2m: Apr 2026-May 2026 | 113 | -557.14 | -4.93 | 0.83 |
| 2m: Jun 2026-Jul 2026 | 67 | -325.23 | -4.85 | 0.86 |


Sides: calls n=996 exp -3.61 PF 0.87; puts n=0 exp - PF -
Symbols: IWM n=340 exp -7.62 PF 0.59; QQQ n=340 exp 2.46 PF 1.07; SPY n=316 exp -5.83 PF 0.81
Without the best 5 trades: net -10356.50, expectancy -10.45.
One-step nudges: allout=15:50 n=996 PF 0.87 exp -3.72
Matched random entries (5 paths): expectancy 4.92, 6.93, 17.64, 9.96, 13.91; the run beats 0% of paths.
Exit reasons: {'CEILING STOP': 767, 'ALL OUT': 159, 'NOISE STOP': 70}.
Median option MFE 0.148, MAE -0.192; median stock MFE $0.405; median distance from the stock's price at the option's peak to the nearest level $0.050; median minutes held 14.0.
Skipped signals: busy: one position at a time 1186, no contract with BS-EST |delta| in 0.55-0.75 109, no option print 1.

## Filters vs random day-skips (every filtered run with its unfiltered twin)

| run | config | twin | days skipped | filtered exp | random-skip exp | p |
|---|---|---|---|---|---|---|
| setups_v1-004 | noise leve tpB/$0.03 rr2 tc 15:25 | setups_v1-003 | 102 | -0.89 | -5.70 | 0.27 |
| setups_v1-010 | noise leve tpB/$0.03 rr2 tc 15:25 | setups_v1-009 | 73 | -10.22 | -4.99 | 0.57 |


## All other runs (sorted by expectancy; fixed stop/target runs are in the cross-check table)

`sig` = signals seen, `skip%` = share not traded (no contract, level stop beyond the ceiling, R:R minimum, busy, no print); the top skip reasons per run are in the run log's notes.

| run | config | sig | skip% | n | win% | avg win | avg loss | exp | PF | PF2x | maxDD | kept | pRR | aRR | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| setups_v1-049 | failed_break prem tpnone tb 15:25 | 930 | 27.31 | 676 | 8.90 | 384.90 | -25.47 | 10.95 | 1.47 | 1.03 | -2122.93 | 0.27 | - | 0.04 | 0.00 |
| setups_v1-019 | vwap_macd prem tpnone tb 15:25 | 372 | 20.16 | 297 | 8.80 | 259.78 | -22.04 | 2.63 | 1.13 | 0.78 | -2368.56 | 0.12 | - | 0.26 | 0.00 |
| setups_v1-032 | pd_retest prem tpA ta 15:25 | 52 | 9.62 | 47 | 38.30 | 24.81 | -16.16 | 1.25 | 1.15 | 0.56 | -80.52 | 0.32 | - | -0.02 | 0.00 |
| setups_v1-033 | pd_retest leve tpB/$0.03 tc 15:25 | 52 | 69.23 | 16 | 68.80 | 9.42 | -16.71 | 1.25 | 1.24 | 0.42 | -40.73 | 0.52 | -0.08 | 0.07 | 0.00 |
| setups_v1-035 | pd_retest leve tpnone tr:gb40 tc 15:25 | 52 | 69.23 | 16 | 62.50 | 9.54 | -13.63 | 0.85 | 1.17 | 0.12 | -50.91 | 0.33 | - | 0.06 | 0.00 |
| setups_v1-004 | noise leve tpB/$0.03 rr2 tc 15:25 | 2292 | 99.87 | 3 | 33.30 | 43.40 | -23.04 | -0.89 | 0.94 | 0.61 | -46.08 | 0.29 | 3.66 | -0.27 | 0.00 |
| setups_v1-045 | flush leve tpB/$0.03 tc 15:25 | 433 | 92.84 | 31 | 32.30 | 18.20 | -10.87 | -1.49 | 0.80 | 0.35 | -138.53 | 0.55 | -0.04 | -0.15 | 0.00 |
| setups_v1-043 | flush prem tpnone tb 15:25 | 433 | 20.09 | 346 | 4.60 | 337.27 | -19.46 | -2.96 | 0.84 | 0.56 | -2538.28 | 0.06 | - | -0.53 | 0.00 |
| setups_v1-002 | noise prem tpA ta 15:25 | 2292 | 29.28 | 1621 | 22.20 | 16.81 | -11.30 | -3.54 | 0.51 | 0.22 | -5792.43 | 0.08 | - | -0.31 | 0.00 |
| setups_v1-047 | flush leve tpnone tr:gb40 tc 15:25 | 433 | 92.84 | 31 | 35.50 | 12.38 | -12.39 | -3.60 | 0.55 | 0.11 | -191.23 | 0.24 | - | -0.19 | 0.00 |
| setups_v1-055 | noise nois tpnone tb 15:25 | 2292 | 56.54 | 996 | 18.00 | 137.31 | -34.48 | -3.61 | 0.87 | 0.59 | -4821.39 | 0.09 | - | -0.17 | 0.00 |
| setups_v1-011 | noise leve tpnone tr:gb40 tc 15:25 | 2104 | 95.06 | 104 | 41.30 | 14.97 | -18.07 | -4.41 | 0.58 | 0.15 | -536.96 | 0.16 | - | -0.10 | 0.00 |
| setups_v1-057 | noise_nocap nois tpnone tb 15:25 | 2292 | 74.30 | 589 | 31.70 | 141.01 | -72.10 | -4.44 | 0.91 | 0.72 | -4686.68 | 0.06 | - | - | 0.00 |
| setups_v1-044 | flush prem tpA ta 15:25 | 433 | 20.09 | 346 | 19.70 | 26.63 | -14.41 | -4.56 | 0.54 | 0.25 | -1606.09 | 0.09 | - | -0.32 | 0.00 |
| setups_v1-009 | noise leve tpB/$0.03 tc 15:25 | 2104 | 95.06 | 104 | 38.50 | 16.56 | -17.88 | -4.63 | 0.58 | 0.26 | -561.51 | 0.24 | -0.19 | -0.19 | 0.00 |
| setups_v1-023 | vwap_macd leve tpnone tr:gb40 tc 15:25 | 372 | 82.53 | 65 | 33.80 | 9.77 | -12.09 | -4.69 | 0.41 | 0.09 | -408.73 | -0.08 | - | -0.20 | 0.00 |
| setups_v1-020 | vwap_macd prem tpA ta 15:25 | 372 | 20.16 | 297 | 22.90 | 24.73 | -16.26 | -4.96 | 0.53 | 0.26 | -1519.91 | -0.03 | - | -0.29 | 0.00 |
| setups_v1-015 | vwap_macd leve tpB/$0.03 tc 15:25 | 361 | 86.70 | 48 | 35.40 | 5.32 | -11.26 | -5.39 | 0.26 | 0.06 | -258.80 | -0.09 | -0.21 | -0.27 | 0.00 |
| setups_v1-003 | noise leve tpB/$0.03 tc 15:25 | 2292 | 93.94 | 139 | 34.50 | 12.65 | -14.97 | -5.43 | 0.45 | 0.17 | -764.07 | -0.03 | -0.11 | -0.34 | 0.00 |
| setups_v1-005 | noise leve tpnone tr:gb40 tc 15:25 | 2292 | 93.94 | 139 | 37.40 | 10.97 | -15.25 | -5.44 | 0.43 | 0.08 | -761.89 | 0.01 | - | -0.25 | 0.00 |
| setups_v1-007 | noise prem tpnone tb 15:25 | 2104 | 38.97 | 1284 | 4.20 | 275.32 | -17.84 | -5.51 | 0.68 | 0.44 | -9745.37 | 0.02 | - | -0.36 | 0.00 |
| setups_v1-001 | noise prem tpnone tb 15:25 | 2292 | 50.61 | 1132 | 6.30 | 134.95 | -15.02 | -5.62 | 0.60 | 0.39 | -6837.13 | -0.05 | - | -0.42 | 0.00 |
| setups_v1-038 | flush prem tpA ta 15:25 | 630 | 10.79 | 562 | 21.20 | 22.42 | -16.47 | -5.86 | 0.45 | 0.21 | -3556.19 | 0.02 | - | -0.31 | 0.00 |
| setups_v1-014 | vwap_macd prem tpA ta 15:25 | 361 | 17.17 | 299 | 19.10 | 22.22 | -15.30 | -6.15 | 0.41 | 0.20 | -1904.79 | -0.01 | - | -0.38 | 0.00 |
| setups_v1-026 | pd_retest prem tpA ta 15:25 | 74 | 20.27 | 59 | 16.90 | 25.63 | -17.28 | -6.20 | 0.41 | 0.20 | -471.67 | 0.18 | - | -0.31 | 0.00 |
| setups_v1-008 | noise prem tpA ta 15:25 | 2104 | 16.78 | 1751 | 20.20 | 21.47 | -15.15 | -6.54 | 0.40 | 0.18 | -11458.99 | -0.01 | - | -0.45 | 0.00 |
| setups_v1-050 | failed_break prem tpA ta 15:25 | 930 | 27.10 | 678 | 22.10 | 26.90 | -20.22 | -6.72 | 0.47 | 0.23 | -4673.67 | 0.03 | - | -0.28 | 0.00 |
| setups_v1-013 | vwap_macd prem tpnone tb 15:25 | 361 | 17.17 | 299 | 5.00 | 237.90 | -20.09 | -7.15 | 0.62 | 0.43 | -3353.51 | -0.03 | - | -0.33 | 0.00 |
| setups_v1-021 | vwap_macd leve tpB/$0.03 tc 15:25 | 372 | 82.53 | 65 | 27.70 | 5.19 | -12.40 | -7.53 | 0.16 | 0.03 | -489.41 | -0.61 | -0.24 | -0.30 | 0.00 |
| setups_v1-053 | failed_break leve tpnone tr:gb40 tc 15:25 | 930 | 77.53 | 209 | 33.00 | 10.49 | -16.53 | -7.53 | 0.32 | 0.06 | -1598.89 | 0.11 | - | -0.25 | 0.00 |
| setups_v1-039 | flush leve tpB/$0.03 tc 15:25 | 630 | 96.83 | 20 | 20.00 | 10.54 | -12.25 | -7.69 | 0.21 | 0.08 | -167.47 | 0.11 | -0.20 | -0.28 | 0.00 |
| setups_v1-017 | vwap_macd leve tpnone tr:gb40 tc 15:25 | 361 | 86.70 | 48 | 39.60 | 4.04 | -15.46 | -7.74 | 0.17 | 0.01 | -371.66 | -0.32 | - | -0.28 | 0.00 |
| setups_v1-051 | failed_break leve tpB/$0.03 tc 15:25 | 930 | 77.53 | 209 | 29.20 | 11.01 | -15.92 | -8.06 | 0.28 | 0.10 | -1727.96 | 0.14 | -0.14 | -0.31 | 0.00 |
| setups_v1-058 | noise_nocap nois tpnone tb 15:25 | 2104 | 71.91 | 591 | 28.60 | 196.07 | -90.19 | -8.33 | 0.87 | 0.71 | -9544.06 | 0.06 | - | - | 0.00 |
| setups_v1-041 | flush leve tpnone tr:gb40 tc 15:25 | 630 | 96.83 | 20 | 35.00 | 1.79 | -14.06 | -8.51 | 0.07 | 0.00 | -170.20 | -0.08 | - | -0.24 | 0.00 |
| setups_v1-027 | pd_retest leve tpB/$0.03 tc 15:25 | 74 | 71.62 | 21 | 42.90 | 4.07 | -20.29 | -9.85 | 0.15 | 0.02 | -229.22 | 0.11 | 0.03 | -0.37 | 0.00 |
| setups_v1-037 | flush prem tpnone tb 15:25 | 630 | 10.79 | 562 | 6.20 | 163.05 | -21.70 | -10.20 | 0.50 | 0.34 | -6326.58 | -0.10 | - | -0.45 | 0.00 |
| setups_v1-010 | noise leve tpB/$0.03 rr2 tc 15:25 | 2104 | 99.95 | 1 | 0.00 | - | -10.22 | -10.22 | 0.00 | 0.00 | -10.22 | -2.28 | 2.07 | -0.73 | 0.00 |
| setups_v1-031 | pd_retest prem tpnone tb 15:25 | 52 | 9.62 | 47 | 4.30 | 232.00 | -21.01 | -10.24 | 0.49 | 0.33 | -734.93 | -0.10 | - | -0.66 | 0.00 |
| setups_v1-056 | noise nois tpnone tb 15:25 | 2104 | 49.24 | 1068 | 13.00 | 199.40 | -42.09 | -10.66 | 0.71 | 0.49 | -13878.59 | 0.02 | - | -0.19 | 0.00 |
| setups_v1-029 | pd_retest leve tpnone tr:gb40 tc 15:25 | 74 | 71.62 | 21 | 38.10 | 2.79 | -21.74 | -12.39 | 0.08 | 0.00 | -265.96 | -0.12 | - | -0.38 | 0.00 |
| setups_v1-025 | pd_retest prem tpnone tb 15:25 | 74 | 20.27 | 59 | 5.10 | 83.57 | -22.21 | -16.83 | 0.20 | 0.14 | -993.00 | -0.36 | - | -0.50 | 0.00 |
| setups_v1-016 | vwap_macd leve tpB/$0.03 rr2 tc 15:25 | 361 | 100.00 | 0 | - | - | - | - | - | - | - | - | - | - | - |
| setups_v1-022 | vwap_macd leve tpB/$0.03 rr2 tc 15:25 | 372 | 100.00 | 0 | - | - | - | - | - | - | - | - | - | - | - |
| setups_v1-028 | pd_retest leve tpB/$0.03 rr2 tc 15:25 | 74 | 100.00 | 0 | - | - | - | - | - | - | - | - | - | - | - |
| setups_v1-034 | pd_retest leve tpB/$0.03 rr2 tc 15:25 | 52 | 100.00 | 0 | - | - | - | - | - | - | - | - | - | - | - |
| setups_v1-040 | flush leve tpB/$0.03 rr2 tc 15:25 | 630 | 100.00 | 0 | - | - | - | - | - | - | - | - | - | - | - |
| setups_v1-046 | flush leve tpB/$0.03 rr2 tc 15:25 | 433 | 100.00 | 0 | - | - | - | - | - | - | - | - | - | - | - |
| setups_v1-052 | failed_break leve tpB/$0.03 rr2 tc 15:25 | 930 | 100.00 | 0 | - | - | - | - | - | - | - | - | - | - | - |


Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_setups_v1_2026-10-31.csv.gz`.

Labels: BACKTEST (in-sample on DEV). Spread: MODELED-SPREAD. Delta: BS-EST. Not financial advice: evidence for Nick to decide.
