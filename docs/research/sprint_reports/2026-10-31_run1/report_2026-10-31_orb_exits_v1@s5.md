# Sprint report: orb_exits_v1 (DEV), MODELED-SPREAD 5.0% (sensitivity)

Generated 2026-10-31 06:22 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint1` in 4.5 min. Spec sha256 `ff58a7d2caed1125a7d49a42f95783a043cdd860ce9c6743b5ee91798f54896d`.

**Every number below is a BACKTEST in-sample (DEV)** on Alpaca 1-minute bars, 2024-08-01 to 2026-06-30. Option fills are real traded prices +/- a half-spread: **MODELED-SPREAD 5.0% of premium for every symbol (a SENSITIVITY run, not the pre-registered 2% default), floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Deltas are BS-EST (Black-Scholes from the option's price). Nothing here is a live or paper fill.

Data: IWM: 479 sessions, QQQ: 479 sessions, SPY: 479 sessions. Runs in this spec: 195. Trials counted for the deflated Sharpe: 478 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Known limits: July 2024 is locked (L2), so early-August 2024 sessions have partial history; news and VIX are unknown in the backtest (rules that need them never fire); a contract needs BS-EST |delta| inside the band, so some signals have no contract (counted as skips).

**Cost caveat:** MODELED-SPREAD 5.0% of premium for every symbol (a SENSITIVITY run, not the pre-registered 2% default), floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: The sprint's FIRST question (SPRINT_PLAN 'First answer'): ORB breakout both sides (15/30/60-minute ranges, first finished 1-minute close beyond, first break per side, signal bars finishing by 12:00) on SPY, QQQ and IWM 0DTE options, delta 0.40-0.55 (target 0.45, BS-EST). Which exit makes the most money after costs: the current fixed-% plan A (about 1:1), a key-level target B, the half-and-trail C, the rejection-or-next-level E, or a trailing stop? Each block below varies one thing; every run uses the same entries, so the exits differ only in their rule. 195 runs. Robustness (nudges, matched random entries, made-up levels) runs on the top 5 by expectancy with at least 60 trades.

## Exit families side by side: current plan vs best level target vs best trail

Best of each family by expectancy among runs with at least 60 trades (else the best with any trades).

| family | run | config | trades | win% | avg win | avg loss | exp $ | PF | PF 2x | max DD | CI95 exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plain stop + time | orb_exits_v1-001@s5 | orb15 prem tpnone tb 15:25 | 1742 | 5.50 | 315.32 | -28.51 | -9.76 | 0.64 | 0.31 | -17239.52 | -15.78..-2.63 |
| A: current fixed-% plan | orb_exits_v1-008@s5 | orb60 prem tpA ta 15:25 | 1035 | 11.70 | 23.21 | -20.71 | -13.55 | 0.17 | 0.03 | -14028.79 | -14.91..-12.18 |
| B: best level target | orb_exits_v1-052@s5 | orb30 leve tpB/0.05% rr1.5 ta 15:25 | 72 | 2.80 | 31.05 | -13.35 | -9.71 | 0.08 | 0.02 | -699.06 | -11.74..-7.29 |
| best trail | orb_exits_v1-185@s5 | orb60 leve tpnone tr:hl1m tc 15:25 | 609 | 9.70 | 73.71 | -21.70 | -12.45 | 0.36 | 0.10 | -7584.48 | -16.23..-8.03 |
| best C/D/E | orb_exits_v1-104@s5 | orb60 leve tpC/$0.03 ta 15:25 | 609 | 12.30 | 15.66 | -19.02 | -14.40 | 0.12 | 0.02 | -8771.77 | -16.05..-12.6 |


## Robustness on the top 5 runs

### orb_exits_v1-052@s5: orb30 leve tpB/0.05% rr1.5 ta 15:25

Trades 72, win 3%, avg win 31.05, avg loss -13.35, expectancy **-9.71** (2x slippage -23.59), PF 0.08 (2x 0.02), max DD -699.06, % of peak kept -0.14, planned R:R 2.63 vs actual -0.71, expectancy CI95 [-11.74, -7.29], deflated Sharpe 0.000 (N=478).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 0 of 12 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries
- [x] filter beats random day-skips
- [ ] real levels beat made-up levels

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 14 | -132.33 | -9.45 | 0.00 |
| 2025 | 44 | -437.25 | -9.94 | 0.07 |
| Jan-Jun 2026 | 14 | -129.48 | -9.25 | 0.19 |
| 2m: Aug 2024-Sep 2024 | 4 | -22.90 | -5.72 | 0.00 |
| 2m: Oct 2024-Nov 2024 | 7 | -95.43 | -13.63 | 0.00 |
| 2m: Dec 2024-Jan 2025 | 7 | -58.82 | -8.40 | 0.00 |
| 2m: Feb 2025-Mar 2025 | 2 | -25.46 | -12.73 | 0.00 |
| 2m: Apr 2025-May 2025 | 5 | -58.43 | -11.69 | 0.00 |
| 2m: Jun 2025-Jul 2025 | 8 | -73.25 | -9.16 | 0.00 |
| 2m: Aug 2025-Sep 2025 | 10 | -69.75 | -6.97 | 0.31 |
| 2m: Oct 2025-Nov 2025 | 7 | -100.24 | -14.32 | 0.00 |
| 2m: Dec 2025-Jan 2026 | 12 | -86.15 | -7.18 | 0.26 |
| 2m: Feb 2026-Mar 2026 | 2 | -30.29 | -15.14 | 0.00 |
| 2m: Apr 2026-May 2026 | 7 | -58.47 | -8.35 | 0.00 |
| 2m: Jun 2026-Jul 2026 | 1 | -19.87 | -19.87 | 0.00 |


Sides: calls n=46 exp -9.74 PF 0.07; puts n=26 exp -9.65 PF 0.11
Symbols: IWM n=42 exp -10.18 PF 0.07; QQQ n=13 exp -11.18 PF 0.00; SPY n=17 exp -7.41 PF 0.19
Without the best 5 trades: net -761.16, expectancy -11.36.
One-step nudges: entry=orb15 n=84 PF 0.14 exp -9.89; entry=orb60 n=47 PF 0.27 exp -7.24; tp_buffer=$0.03 n=34 PF 0.00 exp -12.74; tp_buffer=0.1atr n=35 PF 0.00 exp -13.26; rr_min=1.0 n=126 PF 0.14 exp -11.00; rr_min=2.0 n=43 PF 0.00 exp -9.27; allout=15:50 n=72 PF 0.08 exp -9.71
Matched random entries (5 paths): expectancy -13.32, -6.95, -11.37, -14.48, -9.68; the run beats 60% of paths.
Made-up levels (20 seeds): mean expectancy -10.40; real levels beat 75% of seeds.
Filter vs random day-skips (twin orb_exits_v1-050@s5, 363 days removed): p = 0.0 (filtered exp -9.71, random-skip mean -15.7).
Exit reasons: {'CEILING STOP': 28, 'LEVEL STOP': 17, 'BREAKEVEN STOP': 13, 'IF FLAT': 12, 'LEVEL TARGET': 2}.
Median option MFE 0.051, MAE -0.129; median stock MFE $0.150; median distance from the stock's price at the option's peak to the nearest level $0.070; median minutes held 2.0.
Skipped signals: R:R below 817, level stop does not fit 563, no contract with BS-EST |delta| in 0.40-0.55 161.

### orb_exits_v1-001@s5: orb15 prem tpnone tb 15:25

Trades 1742, win 6%, avg win 315.32, avg loss -28.51, expectancy **-9.76** (2x slippage -35.15), PF 0.64 (2x 0.31), max DD -17239.52, % of peak kept 0.11, planned R:R - vs actual -0.31, expectancy CI95 [-15.78, -2.63], deflated Sharpe 0.000 (N=478).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 1 of 12 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 375 | -4468.96 | -11.92 | 0.50 |
| 2025 | 896 | -4784.75 | -5.34 | 0.80 |
| Jan-Jun 2026 | 471 | -7747.95 | -16.45 | 0.46 |
| 2m: Aug 2024-Sep 2024 | 172 | -3080.55 | -17.91 | 0.34 |
| 2m: Oct 2024-Nov 2024 | 134 | -859.76 | -6.42 | 0.70 |
| 2m: Dec 2024-Jan 2025 | 138 | -1258.66 | -9.12 | 0.61 |
| 2m: Feb 2025-Mar 2025 | 143 | -150.68 | -1.05 | 0.96 |
| 2m: Apr 2025-May 2025 | 163 | -2206.06 | -13.53 | 0.63 |
| 2m: Jun 2025-Jul 2025 | 145 | -2073.68 | -14.30 | 0.28 |
| 2m: Aug 2025-Sep 2025 | 146 | -1981.13 | -13.57 | 0.37 |
| 2m: Oct 2025-Nov 2025 | 153 | 3734.52 | 24.41 | 1.96 |
| 2m: Dec 2025-Jan 2026 | 144 | -2599.87 | -18.05 | 0.22 |
| 2m: Feb 2026-Mar 2026 | 159 | -3830.82 | -24.09 | 0.27 |
| 2m: Apr 2026-May 2026 | 160 | -1639.55 | -10.25 | 0.61 |
| 2m: Jun 2026-Jul 2026 | 85 | -1055.42 | -12.42 | 0.67 |


Sides: calls n=883 exp -12.51 PF 0.52; puts n=859 exp -6.93 PF 0.75
Symbols: IWM n=479 exp -4.14 PF 0.76; QQQ n=622 exp -12.23 PF 0.63; SPY n=641 exp -11.57 PF 0.59
Without the best 5 trades: net -23586.11, expectancy -13.58.
One-step nudges: entry=orb30 n=1452 PF 0.55 exp -11.51; allout=15:50 n=1742 PF 0.63 exp -10.08
Matched random entries (5 paths): expectancy -9.84, -8.15, -7.73, -6.71, -10.01; the run beats 40% of paths.
Exit reasons: {'CEILING STOP': 1647, 'ALL OUT': 95}.
Median option MFE 0.055, MAE -0.181; median stock MFE $0.300; median distance from the stock's price at the option's peak to the nearest level $0.089; median minutes held 2.0.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 153.

### orb_exits_v1-003@s5: orb60 prem tpnone tb 15:25

Trades 1035, win 4%, avg win 329.76, avg loss -24.16, expectancy **-9.80** (2x slippage -32.38), PF 0.58 (2x 0.27), max DD -11381.35, % of peak kept 0.08, planned R:R - vs actual -0.44, expectancy CI95 [-17.41, -0.39], deflated Sharpe 0.000 (N=478).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 3 of 12 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 219 | -2826.25 | -12.91 | 0.37 |
| 2025 | 535 | -5320.79 | -9.95 | 0.57 |
| Jan-Jun 2026 | 281 | -1997.29 | -7.11 | 0.71 |
| 2m: Aug 2024-Sep 2024 | 115 | -2283.60 | -19.86 | 0.14 |
| 2m: Oct 2024-Nov 2024 | 64 | 26.34 | 0.41 | 1.02 |
| 2m: Dec 2024-Jan 2025 | 76 | -1353.22 | -17.81 | 0.10 |
| 2m: Feb 2025-Mar 2025 | 90 | -2402.64 | -26.70 | 0.00 |
| 2m: Apr 2025-May 2025 | 101 | -2199.62 | -21.78 | 0.32 |
| 2m: Jun 2025-Jul 2025 | 84 | -1229.92 | -14.64 | 0.18 |
| 2m: Aug 2025-Sep 2025 | 82 | -1302.78 | -15.89 | 0.14 |
| 2m: Oct 2025-Nov 2025 | 99 | 2909.01 | 29.38 | 2.30 |
| 2m: Dec 2025-Jan 2026 | 85 | -1209.18 | -14.23 | 0.31 |
| 2m: Feb 2026-Mar 2026 | 97 | -516.66 | -5.33 | 0.80 |
| 2m: Apr 2026-May 2026 | 96 | -1701.00 | -17.72 | 0.23 |
| 2m: Jun 2026-Jul 2026 | 46 | 1118.94 | 24.32 | 1.83 |


Sides: calls n=542 exp -17.90 PF 0.17; puts n=493 exp -0.90 PF 0.96
Symbols: IWM n=254 exp -5.40 PF 0.63; QQQ n=387 exp -9.18 PF 0.67; SPY n=394 exp -13.25 PF 0.45
Without the best 5 trades: net -16890.13, expectancy -16.40.
One-step nudges: entry=orb30 n=1452 PF 0.55 exp -11.51; allout=15:50 n=1035 PF 0.61 exp -8.98
Matched random entries (5 paths): expectancy -5.56, -6.29, -1.78, -7.57, -4.05; the run beats 0% of paths.
Exit reasons: {'CEILING STOP': 992, 'ALL OUT': 43}.
Median option MFE 0.048, MAE -0.174; median stock MFE $0.225; median distance from the stock's price at the option's peak to the nearest level $0.090; median minutes held 2.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 162.

### orb_exits_v1-022@s5: orb15 leve tpB/0.05% rr1.5 ta 15:25

Trades 84, win 5%, avg win 33.04, avg loss -15.04, expectancy **-9.89** (2x slippage -25.17), PF 0.14 (2x 0.04), max DD -830.58, % of peak kept 0.09, planned R:R 2.46 vs actual -0.69, expectancy CI95 [-12.36, -6.91], deflated Sharpe 0.000 (N=478).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 1 of 12 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries
- [x] filter beats random day-skips
- [ ] real levels beat made-up levels

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 21 | -210.01 | -10.00 | 0.00 |
| 2025 | 48 | -388.72 | -8.10 | 0.25 |
| Jan-Jun 2026 | 15 | -231.85 | -15.46 | 0.00 |
| 2m: Aug 2024-Sep 2024 | 6 | -37.54 | -6.26 | 0.00 |
| 2m: Oct 2024-Nov 2024 | 9 | -103.32 | -11.48 | 0.00 |
| 2m: Dec 2024-Jan 2025 | 12 | -148.80 | -12.40 | 0.00 |
| 2m: Feb 2025-Mar 2025 | 3 | -47.05 | -15.68 | 0.00 |
| 2m: Apr 2025-May 2025 | 6 | -47.73 | -7.96 | 0.36 |
| 2m: Jun 2025-Jul 2025 | 10 | -73.80 | -7.38 | 0.00 |
| 2m: Aug 2025-Sep 2025 | 9 | 3.33 | 0.37 | 1.03 |
| 2m: Oct 2025-Nov 2025 | 7 | -93.75 | -13.39 | 0.07 |
| 2m: Dec 2025-Jan 2026 | 11 | -103.37 | -9.40 | 0.00 |
| 2m: Feb 2026-Mar 2026 | 5 | -77.80 | -15.56 | 0.00 |
| 2m: Apr 2026-May 2026 | 5 | -80.88 | -16.18 | 0.00 |
| 2m: Jun 2026-Jul 2026 | 1 | -19.87 | -19.87 | 0.00 |


Sides: calls n=56 exp -8.57 PF 0.22; puts n=28 exp -12.52 PF 0.00
Symbols: IWM n=50 exp -9.23 PF 0.19; QQQ n=10 exp -8.49 PF 0.24; SPY n=24 exp -11.84 PF 0.00
Without the best 5 trades: net -962.73, expectancy -12.19.
One-step nudges: entry=orb30 n=72 PF 0.08 exp -9.71; tp_buffer=$0.03 n=36 PF 0.00 exp -14.67; tp_buffer=0.1atr n=40 PF 0.00 exp -14.99; rr_min=1.0 n=160 PF 0.24 exp -10.26; rr_min=2.0 n=45 PF 0.16 exp -7.89; allout=15:50 n=84 PF 0.14 exp -9.89
Matched random entries (5 paths): expectancy -11.63, -7.42, -12.21, -13.17, -13.80; the run beats 80% of paths.
Made-up levels (20 seeds): mean expectancy -9.18; real levels beat 35% of seeds.
Filter vs random day-skips (twin orb_exits_v1-020@s5, 380 days removed): p = 0.0 (filtered exp -9.89, random-skip mean -15.69).
Exit reasons: {'CEILING STOP': 32, 'LEVEL STOP': 22, 'BREAKEVEN STOP': 16, 'IF FLAT': 10, 'LEVEL TARGET': 4}.
Median option MFE 0.029, MAE -0.127; median stock MFE $0.135; median distance from the stock's price at the option's peak to the nearest level $0.050; median minutes held 2.0.
Skipped signals: R:R below 1054, level stop does not fit 604, no contract with BS-EST |delta| in 0.40-0.55 153.

### orb_exits_v1-023@s5: orb15 leve tpB/0.05% rr1.5 tc 15:25

Trades 84, win 8%, avg win 34.68, avg loss -14.56, expectancy **-10.45** (2x slippage -24.70), PF 0.22 (2x 0.07), max DD -882.47, % of peak kept -0.01, planned R:R 2.46 vs actual -0.75, expectancy CI95 [-13.49, -6.94], deflated Sharpe 0.000 (N=478).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 1 of 12 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries
- [x] filter beats random day-skips
- [ ] real levels beat made-up levels

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 21 | -213.51 | -10.17 | 0.13 |
| 2025 | 48 | -432.70 | -9.01 | 0.27 |
| Jan-Jun 2026 | 15 | -231.78 | -15.45 | 0.17 |
| 2m: Aug 2024-Sep 2024 | 6 | -68.69 | -11.45 | 0.00 |
| 2m: Oct 2024-Nov 2024 | 9 | -75.37 | -8.37 | 0.30 |
| 2m: Dec 2024-Jan 2025 | 12 | -149.10 | -12.42 | 0.00 |
| 2m: Feb 2025-Mar 2025 | 3 | -47.05 | -15.68 | 0.00 |
| 2m: Apr 2025-May 2025 | 6 | -47.73 | -7.96 | 0.36 |
| 2m: Jun 2025-Jul 2025 | 10 | -120.99 | -12.10 | 0.00 |
| 2m: Aug 2025-Sep 2025 | 9 | 18.44 | 2.05 | 1.17 |
| 2m: Oct 2025-Nov 2025 | 7 | -93.75 | -13.39 | 0.07 |
| 2m: Dec 2025-Jan 2026 | 11 | -138.71 | -12.61 | 0.00 |
| 2m: Feb 2026-Mar 2026 | 5 | -101.24 | -20.25 | 0.00 |
| 2m: Apr 2026-May 2026 | 5 | -33.93 | -6.79 | 0.58 |
| 2m: Jun 2026-Jul 2026 | 1 | -19.87 | -19.87 | 0.00 |


Sides: calls n=56 exp -8.88 PF 0.33; puts n=28 exp -13.61 PF 0.00
Symbols: IWM n=50 exp -10.32 PF 0.23; QQQ n=10 exp -8.49 PF 0.24; SPY n=24 exp -11.54 PF 0.19
Without the best 5 trades: net -1086.44, expectancy -13.75.
One-step nudges: entry=orb30 n=72 PF 0.15 exp -10.57; tp_buffer=$0.03 n=36 PF 0.13 exp -14.53; tp_buffer=0.1atr n=40 PF 0.12 exp -15.11; rr_min=1.0 n=160 PF 0.29 exp -10.66; rr_min=2.0 n=45 PF 0.33 exp -7.87; allout=15:50 n=84 PF 0.22 exp -10.45
Matched random entries (5 paths): expectancy -11.94, -11.91, -7.57, -13.17, -13.80; the run beats 80% of paths.
Made-up levels (20 seeds): mean expectancy -9.38; real levels beat 25% of seeds.
Filter vs random day-skips (twin orb_exits_v1-021@s5, 380 days removed): p = 0.0 (filtered exp -10.45, random-skip mean -15.69).
Exit reasons: {'CEILING STOP': 37, 'LEVEL STOP': 25, 'IF FLAT': 15, 'LEVEL TARGET': 7}.
Median option MFE 0.029, MAE -0.135; median stock MFE $0.135; median distance from the stock's price at the option's peak to the nearest level $0.050; median minutes held 2.0.
Skipped signals: R:R below 1054, level stop does not fit 604, no contract with BS-EST |delta| in 0.40-0.55 153.

## Filters vs random day-skips (every filtered run with its unfiltered twin)

| run | config | twin | days skipped | filtered exp | random-skip exp | p |
|---|---|---|---|---|---|---|
| orb_exits_v1-012@s5 | orb15 leve tpB/$0.03 rr1.5 ta 15:25 | orb_exits_v1-010@s5 | 422 | -14.67 | -15.71 | 0.31 |
| orb_exits_v1-013@s5 | orb15 leve tpB/$0.03 rr1.5 tc 15:25 | orb_exits_v1-011@s5 | 422 | -14.53 | -15.70 | 0.29 |
| orb_exits_v1-014@s5 | orb15 leve tpB/$0.03 rr2 ta 15:25 | orb_exits_v1-010@s5 | 435 | -12.20 | -15.79 | 0.08 |
| orb_exits_v1-015@s5 | orb15 leve tpB/$0.03 rr2 tc 15:25 | orb_exits_v1-011@s5 | 435 | -12.43 | -15.75 | 0.10 |
| orb_exits_v1-016@s5 | orb15 leve tpB/$0.03 rr2.5 ta 15:25 | orb_exits_v1-010@s5 | 444 | -9.22 | -15.63 | 0.02 |
| orb_exits_v1-017@s5 | orb15 leve tpB/$0.03 rr2.5 tc 15:25 | orb_exits_v1-011@s5 | 444 | -9.64 | -15.58 | 0.04 |
| orb_exits_v1-018@s5 | orb15 leve tpB/$0.03 rr3 ta 15:25 | orb_exits_v1-010@s5 | 449 | -6.39 | -15.90 | 0.02 |
| orb_exits_v1-019@s5 | orb15 leve tpB/$0.03 rr3 tc 15:25 | orb_exits_v1-011@s5 | 449 | -13.80 | -15.91 | 0.31 |
| orb_exits_v1-022@s5 | orb15 leve tpB/0.05% rr1.5 ta 15:25 | orb_exits_v1-020@s5 | 380 | -9.89 | -15.69 | 0.00 |
| orb_exits_v1-023@s5 | orb15 leve tpB/0.05% rr1.5 tc 15:25 | orb_exits_v1-021@s5 | 380 | -10.45 | -15.69 | 0.00 |
| orb_exits_v1-024@s5 | orb15 leve tpB/0.05% rr2 ta 15:25 | orb_exits_v1-020@s5 | 414 | -7.89 | -15.36 | 0.00 |
| orb_exits_v1-025@s5 | orb15 leve tpB/0.05% rr2 tc 15:25 | orb_exits_v1-021@s5 | 414 | -7.87 | -15.33 | 0.00 |
| orb_exits_v1-026@s5 | orb15 leve tpB/0.05% rr2.5 ta 15:25 | orb_exits_v1-020@s5 | 432 | -5.41 | -15.61 | 0.00 |
| orb_exits_v1-027@s5 | orb15 leve tpB/0.05% rr2.5 tc 15:25 | orb_exits_v1-021@s5 | 432 | -8.44 | -15.63 | 0.01 |
| orb_exits_v1-028@s5 | orb15 leve tpB/0.05% rr3 ta 15:25 | orb_exits_v1-020@s5 | 439 | -6.81 | -15.59 | 0.01 |
| orb_exits_v1-029@s5 | orb15 leve tpB/0.05% rr3 tc 15:25 | orb_exits_v1-021@s5 | 439 | -10.00 | -15.60 | 0.04 |
| orb_exits_v1-032@s5 | orb15 leve tpB/0.1atr rr1.5 ta 15:25 | orb_exits_v1-030@s5 | 418 | -14.99 | -15.90 | 0.30 |
| orb_exits_v1-033@s5 | orb15 leve tpB/0.1atr rr1.5 tc 15:25 | orb_exits_v1-031@s5 | 418 | -15.11 | -15.88 | 0.33 |
| orb_exits_v1-034@s5 | orb15 leve tpB/0.1atr rr2 ta 15:25 | orb_exits_v1-030@s5 | 433 | -12.91 | -15.87 | 0.11 |
| orb_exits_v1-035@s5 | orb15 leve tpB/0.1atr rr2 tc 15:25 | orb_exits_v1-031@s5 | 433 | -13.11 | -15.86 | 0.14 |
| orb_exits_v1-036@s5 | orb15 leve tpB/0.1atr rr2.5 ta 15:25 | orb_exits_v1-030@s5 | 442 | -9.96 | -15.62 | 0.04 |
| orb_exits_v1-037@s5 | orb15 leve tpB/0.1atr rr2.5 tc 15:25 | orb_exits_v1-031@s5 | 442 | -10.32 | -15.59 | 0.05 |
| orb_exits_v1-038@s5 | orb15 leve tpB/0.1atr rr3 ta 15:25 | orb_exits_v1-030@s5 | 449 | -6.39 | -15.93 | 0.02 |
| orb_exits_v1-039@s5 | orb15 leve tpB/0.1atr rr3 tc 15:25 | orb_exits_v1-031@s5 | 449 | -13.80 | -15.93 | 0.31 |
| orb_exits_v1-042@s5 | orb30 leve tpB/$0.03 rr1.5 ta 15:25 | orb_exits_v1-040@s5 | 395 | -12.74 | -15.52 | 0.09 |
| orb_exits_v1-043@s5 | orb30 leve tpB/$0.03 rr1.5 tc 15:25 | orb_exits_v1-041@s5 | 395 | -13.82 | -15.47 | 0.20 |
| orb_exits_v1-044@s5 | orb30 leve tpB/$0.03 rr2 ta 15:25 | orb_exits_v1-040@s5 | 409 | -10.29 | -15.18 | 0.06 |
| orb_exits_v1-045@s5 | orb30 leve tpB/$0.03 rr2 tc 15:25 | orb_exits_v1-041@s5 | 409 | -10.68 | -15.15 | 0.07 |
| orb_exits_v1-046@s5 | orb30 leve tpB/$0.03 rr2.5 ta 15:25 | orb_exits_v1-040@s5 | 418 | -8.22 | -15.50 | 0.04 |
| orb_exits_v1-047@s5 | orb30 leve tpB/$0.03 rr2.5 tc 15:25 | orb_exits_v1-041@s5 | 418 | -7.26 | -15.53 | 0.03 |
| orb_exits_v1-048@s5 | orb30 leve tpB/$0.03 rr3 ta 15:25 | orb_exits_v1-040@s5 | 420 | -7.84 | -15.52 | 0.05 |
| orb_exits_v1-049@s5 | orb30 leve tpB/$0.03 rr3 tc 15:25 | orb_exits_v1-041@s5 | 420 | -11.89 | -15.40 | 0.18 |
| orb_exits_v1-052@s5 | orb30 leve tpB/0.05% rr1.5 ta 15:25 | orb_exits_v1-050@s5 | 363 | -9.71 | -15.70 | 0.00 |
| orb_exits_v1-053@s5 | orb30 leve tpB/0.05% rr1.5 tc 15:25 | orb_exits_v1-051@s5 | 363 | -10.57 | -15.67 | 0.00 |
| orb_exits_v1-054@s5 | orb30 leve tpB/0.05% rr2 ta 15:25 | orb_exits_v1-050@s5 | 388 | -9.27 | -15.72 | 0.00 |
| orb_exits_v1-055@s5 | orb30 leve tpB/0.05% rr2 tc 15:25 | orb_exits_v1-051@s5 | 388 | -9.84 | -15.71 | 0.00 |
| orb_exits_v1-056@s5 | orb30 leve tpB/0.05% rr2.5 ta 15:25 | orb_exits_v1-050@s5 | 401 | -8.19 | -15.77 | 0.00 |
| orb_exits_v1-057@s5 | orb30 leve tpB/0.05% rr2.5 tc 15:25 | orb_exits_v1-051@s5 | 401 | -9.33 | -15.75 | 0.01 |
| orb_exits_v1-058@s5 | orb30 leve tpB/0.05% rr3 ta 15:25 | orb_exits_v1-050@s5 | 409 | -6.91 | -15.59 | 0.01 |
| orb_exits_v1-059@s5 | orb30 leve tpB/0.05% rr3 tc 15:25 | orb_exits_v1-051@s5 | 409 | -7.98 | -15.60 | 0.01 |
| orb_exits_v1-062@s5 | orb30 leve tpB/0.1atr rr1.5 ta 15:25 | orb_exits_v1-060@s5 | 394 | -13.26 | -15.61 | 0.14 |
| orb_exits_v1-063@s5 | orb30 leve tpB/0.1atr rr1.5 tc 15:25 | orb_exits_v1-061@s5 | 394 | -14.59 | -15.61 | 0.33 |
| orb_exits_v1-064@s5 | orb30 leve tpB/0.1atr rr2 ta 15:25 | orb_exits_v1-060@s5 | 410 | -10.90 | -15.41 | 0.07 |
| orb_exits_v1-065@s5 | orb30 leve tpB/0.1atr rr2 tc 15:25 | orb_exits_v1-061@s5 | 410 | -11.31 | -15.40 | 0.09 |
| orb_exits_v1-066@s5 | orb30 leve tpB/0.1atr rr2.5 ta 15:25 | orb_exits_v1-060@s5 | 418 | -9.33 | -15.65 | 0.07 |
| orb_exits_v1-067@s5 | orb30 leve tpB/0.1atr rr2.5 tc 15:25 | orb_exits_v1-061@s5 | 418 | -8.38 | -15.69 | 0.05 |
| orb_exits_v1-068@s5 | orb30 leve tpB/0.1atr rr3 ta 15:25 | orb_exits_v1-060@s5 | 422 | -7.71 | -15.03 | 0.05 |
| orb_exits_v1-069@s5 | orb30 leve tpB/0.1atr rr3 tc 15:25 | orb_exits_v1-061@s5 | 422 | -12.92 | -15.01 | 0.31 |
| orb_exits_v1-072@s5 | orb60 leve tpB/$0.03 rr1.5 ta 15:25 | orb_exits_v1-070@s5 | 321 | -12.47 | -14.41 | 0.20 |
| orb_exits_v1-073@s5 | orb60 leve tpB/$0.03 rr1.5 tc 15:25 | orb_exits_v1-071@s5 | 321 | -13.72 | -14.64 | 0.33 |
| orb_exits_v1-074@s5 | orb60 leve tpB/$0.03 rr2 ta 15:25 | orb_exits_v1-070@s5 | 336 | -9.73 | -14.51 | 0.05 |
| orb_exits_v1-075@s5 | orb60 leve tpB/$0.03 rr2 tc 15:25 | orb_exits_v1-071@s5 | 336 | -11.77 | -14.76 | 0.15 |
| orb_exits_v1-076@s5 | orb60 leve tpB/$0.03 rr2.5 ta 15:25 | orb_exits_v1-070@s5 | 342 | -6.97 | -14.26 | 0.02 |
| orb_exits_v1-077@s5 | orb60 leve tpB/$0.03 rr2.5 tc 15:25 | orb_exits_v1-071@s5 | 342 | -10.21 | -14.49 | 0.11 |
| orb_exits_v1-078@s5 | orb60 leve tpB/$0.03 rr3 ta 15:25 | orb_exits_v1-070@s5 | 344 | -4.41 | -14.06 | 0.01 |
| orb_exits_v1-079@s5 | orb60 leve tpB/$0.03 rr3 tc 15:25 | orb_exits_v1-071@s5 | 344 | -8.29 | -14.33 | 0.06 |
| orb_exits_v1-082@s5 | orb60 leve tpB/0.05% rr1.5 ta 15:25 | orb_exits_v1-080@s5 | 309 | -7.24 | -14.79 | 0.00 |
| orb_exits_v1-083@s5 | orb60 leve tpB/0.05% rr1.5 tc 15:25 | orb_exits_v1-081@s5 | 309 | -6.63 | -14.58 | 0.00 |
| orb_exits_v1-084@s5 | orb60 leve tpB/0.05% rr2 ta 15:25 | orb_exits_v1-080@s5 | 331 | -7.79 | -14.84 | 0.00 |
| orb_exits_v1-085@s5 | orb60 leve tpB/0.05% rr2 tc 15:25 | orb_exits_v1-081@s5 | 331 | -8.73 | -14.64 | 0.02 |
| orb_exits_v1-086@s5 | orb60 leve tpB/0.05% rr2.5 ta 15:25 | orb_exits_v1-080@s5 | 334 | -6.75 | -14.69 | 0.00 |
| orb_exits_v1-087@s5 | orb60 leve tpB/0.05% rr2.5 tc 15:25 | orb_exits_v1-081@s5 | 334 | -7.89 | -14.58 | 0.01 |
| orb_exits_v1-088@s5 | orb60 leve tpB/0.05% rr3 ta 15:25 | orb_exits_v1-080@s5 | 340 | -4.15 | -14.62 | 0.00 |
| orb_exits_v1-089@s5 | orb60 leve tpB/0.05% rr3 tc 15:25 | orb_exits_v1-081@s5 | 340 | -5.77 | -14.46 | 0.01 |
| orb_exits_v1-092@s5 | orb60 leve tpB/0.1atr rr1.5 ta 15:25 | orb_exits_v1-090@s5 | 321 | -12.47 | -14.38 | 0.19 |
| orb_exits_v1-093@s5 | orb60 leve tpB/0.1atr rr1.5 tc 15:25 | orb_exits_v1-091@s5 | 321 | -13.53 | -14.58 | 0.32 |
| orb_exits_v1-094@s5 | orb60 leve tpB/0.1atr rr2 ta 15:25 | orb_exits_v1-090@s5 | 336 | -10.67 | -14.45 | 0.10 |
| orb_exits_v1-095@s5 | orb60 leve tpB/0.1atr rr2 tc 15:25 | orb_exits_v1-091@s5 | 336 | -11.86 | -14.68 | 0.16 |
| orb_exits_v1-096@s5 | orb60 leve tpB/0.1atr rr2.5 ta 15:25 | orb_exits_v1-090@s5 | 343 | -7.96 | -14.17 | 0.05 |
| orb_exits_v1-097@s5 | orb60 leve tpB/0.1atr rr2.5 tc 15:25 | orb_exits_v1-091@s5 | 343 | -9.86 | -14.40 | 0.11 |
| orb_exits_v1-098@s5 | orb60 leve tpB/0.1atr rr3 ta 15:25 | orb_exits_v1-090@s5 | 345 | -4.90 | -14.54 | 0.01 |
| orb_exits_v1-099@s5 | orb60 leve tpB/0.1atr rr3 tc 15:25 | orb_exits_v1-091@s5 | 345 | -7.43 | -14.73 | 0.04 |


## All runs (sorted by expectancy)

`sig` = signals seen, `skip%` = share not traded (no contract, level stop beyond the ceiling, R:R minimum, busy, no print); the top skip reasons per run are in the run log's notes.

| run | config | sig | skip% | n | win% | avg win | avg loss | exp | PF | PF2x | maxDD | kept | pRR | aRR | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| orb_exits_v1-088@s5 | orb60 leve tpB/0.05% rr3 ta 15:25 | 1197 | 98.83 | 14 | 14.30 | 19.70 | -9.75 | -4.15 | 0.40 | 0.14 | -75.21 | 0.35 | 4.16 | -0.45 | 0.00 |
| orb_exits_v1-078@s5 | orb60 leve tpB/$0.03 rr3 ta 15:25 | 1197 | 99.16 | 10 | 10.00 | 38.80 | -13.82 | -4.41 | 0.47 | 0.15 | -66.01 | 0.21 | 3.84 | -0.31 | 0.00 |
| orb_exits_v1-098@s5 | orb60 leve tpB/0.1atr rr3 ta 15:25 | 1197 | 99.25 | 9 | 11.10 | 38.80 | -13.82 | -4.90 | 0.47 | 0.16 | -66.01 | 0.24 | 3.98 | -0.34 | 0.00 |
| orb_exits_v1-026@s5 | orb15 leve tpB/0.05% rr2.5 ta 15:25 | 1895 | 98.63 | 26 | 3.80 | 65.85 | -12.15 | -5.41 | 0.32 | 0.11 | -140.77 | 0.26 | 3.73 | -0.52 | 0.00 |
| orb_exits_v1-089@s5 | orb60 leve tpB/0.05% rr3 tc 15:25 | 1197 | 98.83 | 14 | 14.30 | 19.70 | -10.02 | -5.77 | 0.33 | 0.13 | -97.31 | 0.10 | 4.16 | -0.59 | 0.00 |
| orb_exits_v1-018@s5 | orb15 leve tpB/$0.03 rr3 ta 15:25 | 1895 | 99.63 | 7 | 0.00 | - | -14.90 | -6.39 | 0.00 | 0.00 | -44.70 | -0.24 | 3.73 | -0.50 | 0.00 |
| orb_exits_v1-038@s5 | orb15 leve tpB/0.1atr rr3 ta 15:25 | 1895 | 99.63 | 7 | 0.00 | - | -14.90 | -6.39 | 0.00 | 0.00 | -44.70 | -0.24 | 3.79 | -0.50 | 0.00 |
| orb_exits_v1-083@s5 | orb60 leve tpB/0.05% rr1.5 tc 15:25 | 1197 | 96.07 | 47 | 14.90 | 26.86 | -12.49 | -6.63 | 0.38 | 0.12 | -311.75 | 0.08 | 2.64 | -0.52 | 0.00 |
| orb_exits_v1-086@s5 | orb60 leve tpB/0.05% rr2.5 ta 15:25 | 1197 | 98.33 | 20 | 10.00 | 19.70 | -10.90 | -6.75 | 0.23 | 0.08 | -135.07 | 0.35 | 3.73 | -0.62 | 0.00 |
| orb_exits_v1-028@s5 | orb15 leve tpB/0.05% rr3 ta 15:25 | 1895 | 99.00 | 19 | 0.00 | - | -10.78 | -6.81 | 0.00 | 0.00 | -129.39 | -0.16 | 4.07 | -0.66 | 0.00 |
| orb_exits_v1-058@s5 | orb30 leve tpB/0.05% rr3 ta 15:25 | 1613 | 98.70 | 21 | 0.00 | - | -10.36 | -6.91 | 0.00 | 0.00 | -145.01 | -0.46 | 4.10 | -0.67 | 0.00 |
| orb_exits_v1-076@s5 | orb60 leve tpB/$0.03 rr2.5 ta 15:25 | 1197 | 99.00 | 12 | 8.30 | 38.80 | -15.31 | -6.97 | 0.32 | 0.11 | -105.54 | 0.21 | 3.65 | -0.49 | 0.00 |
| orb_exits_v1-082@s5 | orb60 leve tpB/0.05% rr1.5 ta 15:25 | 1197 | 96.07 | 47 | 10.60 | 24.74 | -12.89 | -7.24 | 0.27 | 0.08 | -340.30 | 0.00 | 2.64 | -0.54 | 0.00 |
| orb_exits_v1-047@s5 | orb30 leve tpB/$0.03 rr2.5 tc 15:25 | 1613 | 99.32 | 11 | 9.10 | 46.95 | -12.69 | -7.26 | 0.37 | 0.14 | -106.98 | -0.06 | 3.73 | -0.69 | 0.00 |
| orb_exits_v1-099@s5 | orb60 leve tpB/0.1atr rr3 tc 15:25 | 1197 | 99.25 | 9 | 11.10 | 38.80 | -13.21 | -7.43 | 0.37 | 0.15 | -66.84 | -0.00 | 3.98 | -0.56 | 0.00 |
| orb_exits_v1-068@s5 | orb30 leve tpB/0.1atr rr3 ta 15:25 | 1613 | 99.57 | 7 | 0.00 | - | -13.49 | -7.71 | 0.00 | 0.00 | -53.98 | -0.36 | 4.10 | -0.67 | 0.00 |
| orb_exits_v1-084@s5 | orb60 leve tpB/0.05% rr2 ta 15:25 | 1197 | 97.99 | 24 | 8.30 | 19.70 | -11.31 | -7.79 | 0.17 | 0.07 | -186.88 | 0.01 | 3.48 | -0.66 | 0.00 |
| orb_exits_v1-048@s5 | orb30 leve tpB/$0.03 rr3 ta 15:25 | 1613 | 99.44 | 9 | 0.00 | - | -11.75 | -7.84 | 0.00 | 0.00 | -70.53 | -0.43 | 3.92 | -0.66 | 0.00 |
| orb_exits_v1-025@s5 | orb15 leve tpB/0.05% rr2 tc 15:25 | 1895 | 97.63 | 45 | 8.90 | 44.11 | -12.95 | -7.87 | 0.33 | 0.13 | -381.39 | 0.07 | 3.07 | -0.69 | 0.00 |
| orb_exits_v1-024@s5 | orb15 leve tpB/0.05% rr2 ta 15:25 | 1895 | 97.63 | 45 | 2.20 | 65.85 | -13.57 | -7.89 | 0.16 | 0.05 | -354.88 | 0.08 | 3.07 | -0.64 | 0.00 |
| orb_exits_v1-087@s5 | orb60 leve tpB/0.05% rr2.5 tc 15:25 | 1197 | 98.33 | 20 | 10.00 | 19.70 | -10.95 | -7.89 | 0.20 | 0.08 | -157.77 | 0.10 | 3.73 | -0.72 | 0.00 |
| orb_exits_v1-096@s5 | orb60 leve tpB/0.1atr rr2.5 ta 15:25 | 1197 | 99.00 | 12 | 8.30 | 38.80 | -14.93 | -7.96 | 0.29 | 0.11 | -117.43 | 0.24 | 3.65 | -0.58 | 0.00 |
| orb_exits_v1-059@s5 | orb30 leve tpB/0.05% rr3 tc 15:25 | 1613 | 98.70 | 21 | 4.80 | 30.55 | -9.91 | -7.98 | 0.15 | 0.06 | -176.59 | -0.46 | 4.10 | -0.70 | 0.00 |
| orb_exits_v1-056@s5 | orb30 leve tpB/0.05% rr2.5 ta 15:25 | 1613 | 98.14 | 30 | 0.00 | - | -11.17 | -8.19 | 0.00 | 0.00 | -245.73 | -0.43 | 3.68 | -0.73 | 0.00 |
| orb_exits_v1-046@s5 | orb30 leve tpB/$0.03 rr2.5 ta 15:25 | 1613 | 99.32 | 11 | 0.00 | - | -12.91 | -8.22 | 0.00 | 0.00 | -90.40 | -0.23 | 3.73 | -0.67 | 0.00 |
| orb_exits_v1-079@s5 | orb60 leve tpB/$0.03 rr3 tc 15:25 | 1197 | 99.16 | 10 | 10.00 | 38.80 | -13.53 | -8.29 | 0.32 | 0.13 | -82.93 | -0.12 | 3.84 | -0.62 | 0.00 |
| orb_exits_v1-067@s5 | orb30 leve tpB/0.1atr rr2.5 tc 15:25 | 1613 | 99.32 | 11 | 9.10 | 46.95 | -13.91 | -8.38 | 0.34 | 0.14 | -119.22 | -0.03 | 3.59 | -0.78 | 0.00 |
| orb_exits_v1-027@s5 | orb15 leve tpB/0.05% rr2.5 tc 15:25 | 1895 | 98.63 | 26 | 3.80 | 65.85 | -11.41 | -8.44 | 0.23 | 0.10 | -219.31 | -0.14 | 3.73 | -0.78 | 0.00 |
| orb_exits_v1-085@s5 | orb60 leve tpB/0.05% rr2 tc 15:25 | 1197 | 97.99 | 24 | 8.30 | 19.70 | -11.32 | -8.73 | 0.16 | 0.06 | -209.58 | -0.18 | 3.48 | -0.74 | 0.00 |
| orb_exits_v1-016@s5 | orb15 leve tpB/$0.03 rr2.5 ta 15:25 | 1895 | 99.37 | 12 | 0.00 | - | -15.81 | -9.22 | 0.00 | 0.00 | -110.69 | -0.16 | 3.29 | -0.68 | 0.00 |
| orb_exits_v1-054@s5 | orb30 leve tpB/0.05% rr2 ta 15:25 | 1613 | 97.33 | 43 | 0.00 | - | -12.45 | -9.27 | 0.00 | 0.00 | -398.48 | -0.27 | 3.23 | -0.75 | 0.00 |
| orb_exits_v1-057@s5 | orb30 leve tpB/0.05% rr2.5 tc 15:25 | 1613 | 98.14 | 30 | 3.30 | 30.55 | -10.71 | -9.33 | 0.10 | 0.04 | -279.90 | -0.51 | 3.68 | -0.77 | 0.00 |
| orb_exits_v1-066@s5 | orb30 leve tpB/0.1atr rr2.5 ta 15:25 | 1613 | 99.32 | 11 | 0.00 | - | -14.66 | -9.33 | 0.00 | 0.00 | -102.64 | -0.19 | 3.59 | -0.76 | 0.00 |
| orb_exits_v1-017@s5 | orb15 leve tpB/$0.03 rr2.5 tc 15:25 | 1895 | 99.37 | 12 | 8.30 | 46.95 | -14.78 | -9.64 | 0.29 | 0.12 | -142.73 | -0.16 | 3.29 | -0.80 | 0.00 |
| orb_exits_v1-052@s5 | orb30 leve tpB/0.05% rr1.5 ta 15:25 | 1613 | 95.54 | 72 | 2.80 | 31.05 | -13.35 | -9.71 | 0.08 | 0.02 | -699.06 | -0.14 | 2.63 | -0.71 | 0.00 |
| orb_exits_v1-074@s5 | orb60 leve tpB/$0.03 rr2 ta 15:25 | 1197 | 98.41 | 19 | 5.30 | 38.80 | -14.91 | -9.73 | 0.17 | 0.07 | -184.79 | 0.08 | 3.15 | -0.67 | 0.00 |
| orb_exits_v1-001@s5 | orb15 prem tpnone tb 15:25 | 1895 | 8.07 | 1742 | 5.50 | 315.32 | -28.51 | -9.76 | 0.64 | 0.31 | -17239.52 | 0.11 | - | -0.31 | 0.00 |
| orb_exits_v1-003@s5 | orb60 prem tpnone tb 15:25 | 1197 | 13.53 | 1035 | 4.10 | 329.76 | -24.16 | -9.80 | 0.58 | 0.27 | -11381.35 | 0.08 | - | -0.44 | 0.00 |
| orb_exits_v1-055@s5 | orb30 leve tpB/0.05% rr2 tc 15:25 | 1613 | 97.33 | 43 | 4.70 | 38.75 | -12.21 | -9.84 | 0.15 | 0.06 | -422.92 | -0.30 | 3.23 | -0.77 | 0.00 |
| orb_exits_v1-097@s5 | orb60 leve tpB/0.1atr rr2.5 tc 15:25 | 1197 | 99.00 | 12 | 8.30 | 38.80 | -14.28 | -9.86 | 0.25 | 0.10 | -118.26 | -0.00 | 3.65 | -0.74 | 0.00 |
| orb_exits_v1-022@s5 | orb15 leve tpB/0.05% rr1.5 ta 15:25 | 1895 | 95.57 | 84 | 4.80 | 33.04 | -15.04 | -9.89 | 0.14 | 0.04 | -830.58 | 0.09 | 2.46 | -0.69 | 0.00 |
| orb_exits_v1-036@s5 | orb15 leve tpB/0.1atr rr2.5 ta 15:25 | 1895 | 99.26 | 14 | 0.00 | - | -15.50 | -9.96 | 0.00 | 0.00 | -139.48 | -0.16 | 3.22 | -0.75 | 0.00 |
| orb_exits_v1-029@s5 | orb15 leve tpB/0.05% rr3 tc 15:25 | 1895 | 99.00 | 19 | 0.00 | - | -10.00 | -10.00 | 0.00 | 0.00 | -189.95 | -0.70 | 4.07 | -0.95 | 0.00 |
| orb_exits_v1-077@s5 | orb60 leve tpB/$0.03 rr2.5 tc 15:25 | 1197 | 99.00 | 12 | 8.30 | 38.80 | -14.66 | -10.21 | 0.24 | 0.10 | -122.46 | -0.12 | 3.65 | -0.75 | 0.00 |
| orb_exits_v1-044@s5 | orb30 leve tpB/$0.03 rr2 ta 15:25 | 1613 | 98.76 | 20 | 0.00 | - | -13.71 | -10.29 | 0.00 | 0.00 | -205.71 | -0.44 | 3.09 | -0.77 | 0.00 |
| orb_exits_v1-037@s5 | orb15 leve tpB/0.1atr rr2.5 tc 15:25 | 1895 | 99.26 | 14 | 7.10 | 46.95 | -14.72 | -10.32 | 0.24 | 0.10 | -171.52 | -0.16 | 3.22 | -0.85 | 0.00 |
| orb_exits_v1-023@s5 | orb15 leve tpB/0.05% rr1.5 tc 15:25 | 1895 | 95.57 | 84 | 8.30 | 34.68 | -14.56 | -10.45 | 0.22 | 0.07 | -882.47 | -0.01 | 2.46 | -0.75 | 0.00 |
| orb_exits_v1-053@s5 | orb30 leve tpB/0.05% rr1.5 tc 15:25 | 1613 | 95.54 | 72 | 5.60 | 34.90 | -13.25 | -10.57 | 0.15 | 0.06 | -761.14 | -0.26 | 2.63 | -0.75 | 0.00 |
| orb_exits_v1-094@s5 | orb60 leve tpB/0.1atr rr2 ta 15:25 | 1197 | 98.41 | 19 | 5.30 | 38.80 | -15.09 | -10.67 | 0.16 | 0.06 | -202.64 | 0.09 | 3.13 | -0.73 | 0.00 |
| orb_exits_v1-045@s5 | orb30 leve tpB/$0.03 rr2 tc 15:25 | 1613 | 98.76 | 20 | 5.00 | 46.95 | -13.71 | -10.68 | 0.18 | 0.07 | -240.69 | -0.40 | 3.09 | -0.83 | 0.00 |
| orb_exits_v1-064@s5 | orb30 leve tpB/0.1atr rr2 ta 15:25 | 1613 | 98.82 | 19 | 0.00 | - | -14.79 | -10.90 | 0.00 | 0.00 | -207.01 | -0.41 | 3.03 | -0.80 | 0.00 |
| orb_exits_v1-065@s5 | orb30 leve tpB/0.1atr rr2 tc 15:25 | 1613 | 98.82 | 19 | 5.30 | 46.95 | -14.55 | -11.31 | 0.18 | 0.07 | -241.99 | -0.38 | 3.03 | -0.86 | 0.00 |
| orb_exits_v1-002@s5 | orb30 prem tpnone tb 15:25 | 1613 | 9.98 | 1452 | 4.60 | 309.32 | -27.03 | -11.51 | 0.55 | 0.27 | -16847.34 | 0.09 | - | -0.40 | 0.00 |
| orb_exits_v1-075@s5 | orb60 leve tpB/$0.03 rr2 tc 15:25 | 1197 | 98.41 | 19 | 5.30 | 38.80 | -14.58 | -11.77 | 0.15 | 0.06 | -223.58 | -0.21 | 3.15 | -0.84 | 0.00 |
| orb_exits_v1-095@s5 | orb60 leve tpB/0.1atr rr2 tc 15:25 | 1197 | 98.41 | 19 | 5.30 | 38.80 | -14.67 | -11.86 | 0.15 | 0.06 | -225.34 | -0.13 | 3.13 | -0.83 | 0.00 |
| orb_exits_v1-049@s5 | orb30 leve tpB/$0.03 rr3 tc 15:25 | 1613 | 99.44 | 9 | 0.00 | - | -11.89 | -11.89 | 0.00 | 0.00 | -106.98 | -1.05 | 3.92 | -1.02 | 0.00 |
| orb_exits_v1-014@s5 | orb15 leve tpB/$0.03 rr2 ta 15:25 | 1895 | 98.84 | 22 | 0.00 | - | -15.79 | -12.20 | 0.00 | 0.00 | -268.46 | -0.38 | 2.84 | -0.86 | 0.00 |
| orb_exits_v1-015@s5 | orb15 leve tpB/$0.03 rr2 tc 15:25 | 1895 | 98.84 | 22 | 4.50 | 46.95 | -15.26 | -12.43 | 0.15 | 0.06 | -300.50 | -0.33 | 2.84 | -0.92 | 0.00 |
| orb_exits_v1-185@s5 | orb60 leve tpnone tr:hl1m tc 15:25 | 1197 | 49.12 | 609 | 9.70 | 73.71 | -21.70 | -12.45 | 0.36 | 0.10 | -7584.48 | 0.14 | - | -0.50 | 0.00 |
| orb_exits_v1-072@s5 | orb60 leve tpB/$0.03 rr1.5 ta 15:25 | 1197 | 97.16 | 34 | 2.90 | 38.80 | -17.14 | -12.47 | 0.08 | 0.03 | -423.90 | -0.31 | 2.50 | -0.75 | 0.00 |
| orb_exits_v1-092@s5 | orb60 leve tpB/0.1atr rr1.5 ta 15:25 | 1197 | 97.16 | 34 | 2.90 | 38.80 | -17.14 | -12.47 | 0.08 | 0.03 | -423.90 | -0.32 | 2.48 | -0.75 | 0.00 |
| orb_exits_v1-042@s5 | orb30 leve tpB/$0.03 rr1.5 ta 15:25 | 1613 | 97.89 | 34 | 0.00 | - | -16.05 | -12.74 | 0.00 | 0.00 | -433.23 | -0.47 | 2.51 | -0.81 | 0.00 |
| orb_exits_v1-183@s5 | orb60 leve tpnone tr:L3 tc 15:25 | 1197 | 49.12 | 609 | 12.60 | 52.43 | -22.23 | -12.79 | 0.34 | 0.09 | -7790.40 | 0.12 | - | -0.51 | 0.00 |
| orb_exits_v1-119@s5 | orb15 leve tpnone tr:be15 tc 15:25 | 1895 | 39.95 | 1138 | 2.70 | 279.84 | -25.62 | -12.89 | 0.37 | 0.15 | -14665.49 | 0.12 | - | -0.40 | 0.00 |
| orb_exits_v1-034@s5 | orb15 leve tpB/0.1atr rr2 ta 15:25 | 1895 | 98.73 | 24 | 0.00 | - | -16.30 | -12.91 | 0.00 | 0.00 | -309.75 | -0.38 | 2.81 | -0.89 | 0.00 |
| orb_exits_v1-069@s5 | orb30 leve tpB/0.1atr rr3 tc 15:25 | 1613 | 99.57 | 7 | 0.00 | - | -12.92 | -12.92 | 0.00 | 0.00 | -90.43 | -1.00 | 4.10 | -1.13 | 0.00 |
| orb_exits_v1-035@s5 | orb15 leve tpB/0.1atr rr2 tc 15:25 | 1895 | 98.73 | 24 | 4.20 | 46.95 | -15.72 | -13.11 | 0.13 | 0.05 | -341.79 | -0.33 | 2.81 | -0.95 | 0.00 |
| orb_exits_v1-062@s5 | orb30 leve tpB/0.1atr rr1.5 ta 15:25 | 1613 | 97.83 | 35 | 0.00 | - | -17.20 | -13.26 | 0.00 | 0.00 | -464.27 | -0.64 | 2.39 | -0.82 | 0.00 |
| orb_exits_v1-184@s5 | orb60 leve tpnone tr:hl1m ta 15:25 | 1197 | 49.12 | 609 | 5.60 | 79.71 | -22.01 | -13.33 | 0.25 | 0.07 | -8117.96 | 0.12 | - | -0.52 | 0.00 |
| orb_exits_v1-093@s5 | orb60 leve tpB/0.1atr rr1.5 tc 15:25 | 1197 | 97.16 | 34 | 8.80 | 27.50 | -17.50 | -13.53 | 0.15 | 0.04 | -460.09 | -0.43 | 2.48 | -0.83 | 0.00 |
| orb_exits_v1-008@s5 | orb60 prem tpA ta 15:25 | 1197 | 13.53 | 1035 | 11.70 | 23.21 | -20.71 | -13.55 | 0.17 | 0.03 | -14028.79 | -0.10 | - | -0.58 | 0.00 |
| orb_exits_v1-009@s5 | orb60 prem tpA ta 15:50 | 1197 | 13.53 | 1035 | 11.70 | 23.21 | -20.71 | -13.55 | 0.17 | 0.03 | -14028.79 | -0.10 | - | -0.58 | 0.00 |
| orb_exits_v1-187@s5 | orb60 leve tpnone tr:hl5m tc 15:25 | 1197 | 49.12 | 609 | 7.90 | 87.11 | -22.30 | -13.67 | 0.33 | 0.10 | -8326.93 | 0.05 | - | -0.55 | 0.00 |
| orb_exits_v1-112@s5 | orb15 leve tpnone tr:be6 ta 15:25 | 1895 | 39.95 | 1138 | 1.70 | 301.06 | -25.01 | -13.70 | 0.27 | 0.10 | -15590.50 | 0.11 | - | -0.45 | 0.00 |
| orb_exits_v1-113@s5 | orb15 leve tpnone tr:be6 tc 15:25 | 1895 | 39.95 | 1138 | 1.70 | 301.06 | -25.01 | -13.70 | 0.27 | 0.10 | -15590.50 | 0.11 | - | -0.45 | 0.00 |
| orb_exits_v1-181@s5 | orb60 leve tpnone tr:L2 tc 15:25 | 1197 | 49.12 | 609 | 16.30 | 29.50 | -22.10 | -13.71 | 0.26 | 0.06 | -8349.41 | 0.09 | - | -0.48 | 0.00 |
| orb_exits_v1-073@s5 | orb60 leve tpB/$0.03 rr1.5 tc 15:25 | 1197 | 97.16 | 34 | 8.80 | 27.50 | -17.71 | -13.72 | 0.15 | 0.04 | -466.43 | -0.41 | 2.50 | -0.84 | 0.00 |
| orb_exits_v1-019@s5 | orb15 leve tpB/$0.03 rr3 tc 15:25 | 1895 | 99.63 | 7 | 0.00 | - | -13.80 | -13.80 | 0.00 | 0.00 | -96.61 | -0.89 | 3.73 | -1.15 | 0.00 |
| orb_exits_v1-039@s5 | orb15 leve tpB/0.1atr rr3 tc 15:25 | 1895 | 99.63 | 7 | 0.00 | - | -13.80 | -13.80 | 0.00 | 0.00 | -96.61 | -0.89 | 3.79 | -1.15 | 0.00 |
| orb_exits_v1-043@s5 | orb30 leve tpB/$0.03 rr1.5 tc 15:25 | 1613 | 97.89 | 34 | 5.90 | 32.83 | -16.73 | -13.82 | 0.12 | 0.04 | -500.65 | -0.57 | 2.51 | -0.88 | 0.00 |
| orb_exits_v1-180@s5 | orb60 leve tpnone tr:L2 ta 15:25 | 1197 | 49.12 | 609 | 12.00 | 31.32 | -22.06 | -14.03 | 0.21 | 0.05 | -8546.87 | 0.07 | - | -0.49 | 0.00 |
| orb_exits_v1-168@s5 | orb60 leve tpnone tr:be6 ta 15:25 | 1197 | 49.12 | 609 | 0.80 | 355.26 | -21.66 | -14.08 | 0.17 | 0.07 | -8575.52 | 0.05 | - | -0.50 | 0.00 |
| orb_exits_v1-169@s5 | orb60 leve tpnone tr:be6 tc 15:25 | 1197 | 49.12 | 609 | 0.80 | 355.26 | -21.66 | -14.08 | 0.17 | 0.07 | -8575.52 | 0.05 | - | -0.50 | 0.00 |
| orb_exits_v1-175@s5 | orb60 leve tpnone tr:be15 tc 15:25 | 1197 | 49.12 | 609 | 1.80 | 243.61 | -21.98 | -14.11 | 0.24 | 0.10 | -8595.86 | 0.04 | - | -0.50 | 0.00 |
| orb_exits_v1-114@s5 | orb15 leve tpnone tr:be8 ta 15:25 | 1895 | 39.95 | 1138 | 1.80 | 286.06 | -25.23 | -14.13 | 0.26 | 0.10 | -16080.05 | 0.09 | - | -0.46 | 0.00 |
| orb_exits_v1-115@s5 | orb15 leve tpnone tr:be8 tc 15:25 | 1895 | 39.95 | 1138 | 1.80 | 286.06 | -25.23 | -14.13 | 0.26 | 0.10 | -16080.05 | 0.09 | - | -0.46 | 0.00 |
| orb_exits_v1-116@s5 | orb15 leve tpnone tr:be10 ta 15:25 | 1895 | 39.95 | 1138 | 1.90 | 276.88 | -25.68 | -14.24 | 0.27 | 0.11 | -16202.98 | 0.08 | - | -0.45 | 0.00 |
| orb_exits_v1-117@s5 | orb15 leve tpnone tr:be10 tc 15:25 | 1895 | 39.95 | 1138 | 1.90 | 276.88 | -25.68 | -14.24 | 0.27 | 0.11 | -16202.98 | 0.08 | - | -0.45 | 0.00 |
| orb_exits_v1-118@s5 | orb15 leve tpnone tr:be15 ta 15:25 | 1895 | 39.95 | 1138 | 1.90 | 276.88 | -25.68 | -14.24 | 0.27 | 0.11 | -16202.98 | 0.08 | - | -0.45 | 0.00 |
| orb_exits_v1-194@s5 | orb60 leve tpnone tr:gb50 ta 15:25 | 1197 | 49.12 | 609 | 19.40 | 9.20 | -19.91 | -14.27 | 0.11 | 0.01 | -8692.50 | 0.09 | - | -0.53 | 0.00 |
| orb_exits_v1-195@s5 | orb60 leve tpnone tr:gb50 tc 15:25 | 1197 | 49.12 | 609 | 19.40 | 9.20 | -19.91 | -14.27 | 0.11 | 0.01 | -8692.50 | 0.09 | - | -0.53 | 0.00 |
| orb_exits_v1-170@s5 | orb60 leve tpnone tr:be8 ta 15:25 | 1197 | 49.12 | 609 | 1.00 | 296.21 | -21.87 | -14.35 | 0.17 | 0.07 | -8740.75 | 0.03 | - | -0.51 | 0.00 |
| orb_exits_v1-171@s5 | orb60 leve tpnone tr:be8 tc 15:25 | 1197 | 49.12 | 609 | 1.00 | 296.21 | -21.87 | -14.35 | 0.17 | 0.07 | -8740.75 | 0.03 | - | -0.51 | 0.00 |
| orb_exits_v1-104@s5 | orb60 leve tpC/$0.03 ta 15:25 | 1197 | 49.12 | 609 | 12.30 | 15.66 | -19.02 | -14.40 | 0.12 | 0.02 | -8771.77 | -0.03 | -0.10 | -0.65 | 0.00 |
| orb_exits_v1-090@s5 | orb60 leve tpB/0.1atr ta 15:25 | 1197 | 49.12 | 609 | 12.80 | 9.29 | -18.35 | -14.42 | 0.08 | 0.01 | -8781.06 | -0.06 | -0.10 | -0.66 | 0.00 |
| orb_exits_v1-004@s5 | orb15 prem tpA ta 15:25 | 1895 | 8.07 | 1742 | 14.80 | 27.98 | -24.96 | -14.47 | 0.22 | 0.05 | -25399.44 | 0.03 | - | -0.51 | 0.00 |
| orb_exits_v1-005@s5 | orb15 prem tpA ta 15:50 | 1895 | 8.07 | 1742 | 14.80 | 27.98 | -24.96 | -14.47 | 0.22 | 0.05 | -25399.44 | 0.03 | - | -0.51 | 0.00 |
| orb_exits_v1-070@s5 | orb60 leve tpB/$0.03 ta 15:25 | 1197 | 49.12 | 609 | 13.00 | 9.21 | -18.42 | -14.48 | 0.08 | 0.01 | -8816.64 | -0.07 | -0.10 | -0.66 | 0.00 |
| orb_exits_v1-179@s5 | orb60 leve tpnone tr:L1 tc 15:25 | 1197 | 49.12 | 609 | 14.00 | 32.37 | -22.11 | -14.51 | 0.24 | 0.04 | -8835.01 | 0.03 | - | -0.51 | 0.00 |
| orb_exits_v1-013@s5 | orb15 leve tpB/$0.03 rr1.5 tc 15:25 | 1895 | 98.10 | 36 | 5.60 | 39.53 | -17.71 | -14.53 | 0.13 | 0.05 | -535.03 | -0.38 | 2.42 | -0.93 | 0.00 |
| orb_exits_v1-105@s5 | orb60 leve tpC/$0.03 tc 15:25 | 1197 | 49.12 | 609 | 11.70 | 18.28 | -18.87 | -14.54 | 0.13 | 0.02 | -8856.06 | -0.04 | -0.10 | -0.66 | 0.00 |
| orb_exits_v1-188@s5 | orb60 leve tpnone tr:lvl ta 15:25 | 1197 | 49.12 | 609 | 6.90 | 41.42 | -21.24 | -14.58 | 0.16 | 0.03 | -8881.38 | 0.03 | - | -0.53 | 0.00 |
| orb_exits_v1-063@s5 | orb30 leve tpB/0.1atr rr1.5 tc 15:25 | 1613 | 97.83 | 35 | 5.70 | 32.83 | -17.46 | -14.59 | 0.11 | 0.04 | -541.44 | -0.75 | 2.39 | -0.91 | 0.00 |
| orb_exits_v1-091@s5 | orb60 leve tpB/0.1atr tc 15:25 | 1197 | 49.12 | 609 | 13.50 | 9.60 | -18.39 | -14.62 | 0.08 | 0.01 | -8906.22 | -0.13 | -0.10 | -0.67 | 0.00 |
| orb_exits_v1-081@s5 | orb60 leve tpB/0.05% tc 15:25 | 1197 | 49.12 | 609 | 14.10 | 11.65 | -18.99 | -14.66 | 0.10 | 0.01 | -8927.65 | -0.04 | 0.10 | -0.68 | 0.00 |
| orb_exits_v1-012@s5 | orb15 leve tpB/$0.03 rr1.5 ta 15:25 | 1895 | 98.10 | 36 | 0.00 | - | -17.61 | -14.67 | 0.00 | 0.00 | -528.19 | -0.47 | 2.42 | -0.91 | 0.00 |
| orb_exits_v1-190@s5 | orb60 leve tpnone tr:gb30 ta 15:25 | 1197 | 49.12 | 609 | 19.40 | 7.03 | -19.91 | -14.69 | 0.09 | 0.00 | -8948.30 | 0.02 | - | -0.55 | 0.00 |
| orb_exits_v1-191@s5 | orb60 leve tpnone tr:gb30 tc 15:25 | 1197 | 49.12 | 609 | 19.40 | 7.03 | -19.91 | -14.69 | 0.09 | 0.00 | -8948.30 | 0.02 | - | -0.55 | 0.00 |
| orb_exits_v1-071@s5 | orb60 leve tpB/$0.03 tc 15:25 | 1197 | 49.12 | 609 | 13.50 | 9.55 | -18.47 | -14.70 | 0.08 | 0.01 | -8952.25 | -0.15 | -0.10 | -0.68 | 0.00 |
| orb_exits_v1-176@s5 | orb60 leve tpnone tr:belevel ta 15:25 | 1197 | 49.12 | 609 | 0.80 | 227.15 | -19.86 | -14.70 | 0.11 | 0.04 | -8950.85 | -0.03 | -0.10 | -0.63 | 0.00 |
| orb_exits_v1-178@s5 | orb60 leve tpnone tr:L1 ta 15:25 | 1197 | 49.12 | 609 | 9.00 | 33.74 | -22.06 | -14.74 | 0.17 | 0.03 | -8977.89 | 0.01 | - | -0.52 | 0.00 |
| orb_exits_v1-192@s5 | orb60 leve tpnone tr:gb40 ta 15:25 | 1197 | 49.12 | 609 | 19.40 | 6.81 | -19.91 | -14.74 | 0.08 | 0.00 | -8974.15 | 0.01 | - | -0.55 | 0.00 |
| orb_exits_v1-193@s5 | orb60 leve tpnone tr:gb40 tc 15:25 | 1197 | 49.12 | 609 | 19.40 | 6.81 | -19.91 | -14.74 | 0.08 | 0.00 | -8974.15 | 0.01 | - | -0.55 | 0.00 |
| orb_exits_v1-080@s5 | orb60 leve tpB/0.05% ta 15:25 | 1197 | 49.12 | 609 | 12.80 | 10.23 | -19.07 | -14.85 | 0.08 | 0.01 | -9042.87 | -0.11 | 0.10 | -0.68 | 0.00 |
| orb_exits_v1-107@s5 | orb15 leve tpE/$0.03 tc 15:25 | 1895 | 39.95 | 1138 | 11.80 | 48.72 | -23.37 | -14.86 | 0.28 | 0.10 | -16975.13 | 0.09 | -0.16 | -0.60 | 0.00 |
| orb_exits_v1-147@s5 | orb30 leve tpnone tr:be15 tc 15:25 | 1613 | 44.89 | 889 | 2.00 | 241.95 | -23.79 | -14.87 | 0.25 | 0.10 | -13223.33 | 0.07 | - | -0.52 | 0.00 |
| orb_exits_v1-172@s5 | orb60 leve tpnone tr:be10 ta 15:25 | 1197 | 49.12 | 609 | 1.30 | 222.24 | -21.98 | -14.87 | 0.16 | 0.07 | -9058.01 | -0.00 | - | -0.53 | 0.00 |
| orb_exits_v1-173@s5 | orb60 leve tpnone tr:be10 tc 15:25 | 1197 | 49.12 | 609 | 1.30 | 222.24 | -21.98 | -14.87 | 0.16 | 0.07 | -9058.01 | -0.00 | - | -0.53 | 0.00 |
| orb_exits_v1-174@s5 | orb60 leve tpnone tr:be15 ta 15:25 | 1197 | 49.12 | 609 | 1.30 | 222.24 | -21.98 | -14.87 | 0.16 | 0.07 | -9058.01 | -0.00 | - | -0.53 | 0.00 |
| orb_exits_v1-186@s5 | orb60 leve tpnone tr:hl5m ta 15:25 | 1197 | 49.12 | 609 | 3.60 | 80.25 | -22.02 | -14.89 | 0.16 | 0.04 | -9069.26 | -0.01 | - | -0.57 | 0.00 |
| orb_exits_v1-189@s5 | orb60 leve tpnone tr:lvl tc 15:25 | 1197 | 49.12 | 609 | 10.50 | 32.84 | -20.51 | -14.90 | 0.19 | 0.04 | -9074.49 | -0.01 | - | -0.54 | 0.00 |
| orb_exits_v1-032@s5 | orb15 leve tpB/0.1atr rr1.5 ta 15:25 | 1895 | 97.89 | 40 | 0.00 | - | -18.17 | -14.99 | 0.00 | 0.00 | -599.72 | -0.57 | 2.37 | -0.92 | 0.00 |
| orb_exits_v1-121@s5 | orb15 leve tpnone tr:belevel tc 15:25 | 1895 | 39.95 | 1138 | 1.10 | 275.02 | -22.20 | -14.99 | 0.16 | 0.06 | -17053.99 | 0.04 | -0.16 | -0.62 | 0.00 |
| orb_exits_v1-106@s5 | orb15 leve tpE/$0.03 ta 15:25 | 1895 | 39.95 | 1138 | 8.40 | 44.00 | -23.47 | -15.01 | 0.20 | 0.06 | -17144.73 | 0.09 | -0.16 | -0.61 | 0.00 |
| orb_exits_v1-111@s5 | orb60 leve tpE/$0.03 tc 15:25 | 1197 | 49.12 | 609 | 11.00 | 28.17 | -20.43 | -15.08 | 0.17 | 0.05 | -9186.06 | -0.08 | -0.10 | -0.71 | 0.00 |
| orb_exits_v1-033@s5 | orb15 leve tpB/0.1atr rr1.5 tc 15:25 | 1895 | 97.89 | 40 | 5.00 | 39.53 | -17.98 | -15.11 | 0.12 | 0.04 | -604.23 | -0.52 | 2.37 | -0.95 | 0.00 |
| orb_exits_v1-140@s5 | orb30 leve tpnone tr:be6 ta 15:25 | 1613 | 44.89 | 889 | 1.20 | 260.50 | -23.88 | -15.15 | 0.17 | 0.07 | -13563.01 | 0.07 | - | -0.53 | 0.00 |
| orb_exits_v1-141@s5 | orb30 leve tpnone tr:be6 tc 15:25 | 1613 | 44.89 | 889 | 1.20 | 260.50 | -23.88 | -15.15 | 0.17 | 0.07 | -13563.01 | 0.07 | - | -0.53 | 0.00 |
| orb_exits_v1-006@s5 | orb30 prem tpA ta 15:25 | 1613 | 9.98 | 1452 | 12.80 | 25.09 | -23.43 | -15.17 | 0.17 | 0.04 | -22021.61 | -0.02 | - | -0.56 | 0.00 |
| orb_exits_v1-007@s5 | orb30 prem tpA ta 15:50 | 1613 | 9.98 | 1452 | 12.80 | 25.09 | -23.43 | -15.17 | 0.17 | 0.04 | -22021.61 | -0.02 | - | -0.56 | 0.00 |
| orb_exits_v1-138@s5 | orb15 leve tpnone tr:gb50 ta 15:25 | 1895 | 39.95 | 1138 | 21.20 | 10.35 | -22.06 | -15.19 | 0.13 | 0.01 | -17289.42 | 0.09 | - | -0.51 | 0.00 |
| orb_exits_v1-139@s5 | orb15 leve tpnone tr:gb50 tc 15:25 | 1895 | 39.95 | 1138 | 21.20 | 10.35 | -22.06 | -15.19 | 0.13 | 0.01 | -17289.42 | 0.09 | - | -0.51 | 0.00 |
| orb_exits_v1-177@s5 | orb60 leve tpnone tr:belevel tc 15:25 | 1197 | 49.12 | 609 | 0.80 | 227.15 | -19.93 | -15.19 | 0.11 | 0.04 | -9248.49 | -0.07 | -0.10 | -0.66 | 0.00 |
| orb_exits_v1-166@s5 | orb30 leve tpnone tr:gb50 ta 15:25 | 1613 | 44.89 | 889 | 19.90 | 10.26 | -21.53 | -15.20 | 0.12 | 0.02 | -13582.42 | 0.12 | - | -0.54 | 0.00 |
| orb_exits_v1-167@s5 | orb30 leve tpnone tr:gb50 tc 15:25 | 1613 | 44.89 | 889 | 19.90 | 10.26 | -21.53 | -15.20 | 0.12 | 0.02 | -13582.42 | 0.12 | - | -0.54 | 0.00 |
| orb_exits_v1-182@s5 | orb60 leve tpnone tr:L3 ta 15:25 | 1197 | 49.12 | 609 | 7.60 | 33.95 | -22.06 | -15.22 | 0.14 | 0.02 | -9271.91 | -0.04 | - | -0.58 | 0.00 |
| orb_exits_v1-155@s5 | orb30 leve tpnone tr:L3 tc 15:25 | 1613 | 44.89 | 889 | 13.40 | 40.91 | -23.93 | -15.25 | 0.26 | 0.07 | -13658.71 | 0.06 | - | -0.54 | 0.00 |
| orb_exits_v1-120@s5 | orb15 leve tpnone tr:belevel ta 15:25 | 1895 | 39.95 | 1138 | 0.80 | 300.61 | -22.25 | -15.30 | 0.13 | 0.05 | -17409.88 | 0.02 | -0.16 | -0.63 | 0.00 |
| orb_exits_v1-142@s5 | orb30 leve tpnone tr:be8 ta 15:25 | 1613 | 44.89 | 889 | 1.30 | 238.86 | -23.63 | -15.30 | 0.17 | 0.07 | -13682.92 | 0.05 | - | -0.54 | 0.00 |
| orb_exits_v1-143@s5 | orb30 leve tpnone tr:be8 tc 15:25 | 1613 | 44.89 | 889 | 1.30 | 238.86 | -23.63 | -15.30 | 0.17 | 0.07 | -13682.92 | 0.05 | - | -0.54 | 0.00 |
| orb_exits_v1-110@s5 | orb60 leve tpE/$0.03 ta 15:25 | 1197 | 49.12 | 609 | 8.90 | 17.16 | -20.51 | -15.32 | 0.09 | 0.02 | -9327.97 | -0.14 | -0.10 | -0.70 | 0.00 |
| orb_exits_v1-041@s5 | orb30 leve tpB/$0.03 tc 15:25 | 1613 | 44.89 | 889 | 13.80 | 12.32 | -19.83 | -15.38 | 0.10 | 0.02 | -13705.27 | 0.07 | -0.13 | -0.67 | 0.00 |
| orb_exits_v1-133@s5 | orb15 leve tpnone tr:lvl tc 15:25 | 1895 | 39.95 | 1138 | 14.90 | 30.89 | -23.47 | -15.38 | 0.23 | 0.04 | -17541.32 | 0.04 | - | -0.50 | 0.00 |
| orb_exits_v1-132@s5 | orb15 leve tpnone tr:lvl ta 15:25 | 1895 | 39.95 | 1138 | 10.00 | 36.62 | -24.73 | -15.41 | 0.19 | 0.03 | -17583.24 | 0.04 | - | -0.50 | 0.00 |
| orb_exits_v1-040@s5 | orb30 leve tpB/$0.03 ta 15:25 | 1613 | 44.89 | 889 | 13.00 | 11.34 | -19.78 | -15.43 | 0.09 | 0.01 | -13750.40 | 0.05 | -0.13 | -0.67 | 0.00 |
| orb_exits_v1-061@s5 | orb30 leve tpB/0.1atr tc 15:25 | 1613 | 44.89 | 889 | 13.30 | 12.62 | -19.83 | -15.52 | 0.10 | 0.02 | -13833.34 | 0.05 | -0.14 | -0.68 | 0.00 |
| orb_exits_v1-060@s5 | orb30 leve tpB/0.1atr ta 15:25 | 1613 | 44.89 | 889 | 12.50 | 11.62 | -19.79 | -15.56 | 0.09 | 0.01 | -13866.58 | 0.04 | -0.14 | -0.68 | 0.00 |
| orb_exits_v1-134@s5 | orb15 leve tpnone tr:gb30 ta 15:25 | 1895 | 39.95 | 1138 | 21.20 | 8.36 | -22.06 | -15.61 | 0.10 | 0.00 | -17767.95 | 0.04 | - | -0.52 | 0.00 |
| orb_exits_v1-135@s5 | orb15 leve tpnone tr:gb30 tc 15:25 | 1895 | 39.95 | 1138 | 21.20 | 8.36 | -22.06 | -15.61 | 0.10 | 0.00 | -17767.95 | 0.04 | - | -0.52 | 0.00 |
| orb_exits_v1-020@s5 | orb15 leve tpB/0.05% ta 15:25 | 1895 | 39.95 | 1138 | 15.20 | 12.84 | -21.33 | -15.63 | 0.11 | 0.02 | -17805.65 | 0.04 | 0.11 | -0.64 | 0.00 |
| orb_exits_v1-021@s5 | orb15 leve tpB/0.05% tc 15:25 | 1895 | 39.95 | 1138 | 16.20 | 13.56 | -21.26 | -15.63 | 0.12 | 0.02 | -17799.31 | 0.04 | 0.11 | -0.65 | 0.00 |
| orb_exits_v1-162@s5 | orb30 leve tpnone tr:gb30 ta 15:25 | 1613 | 44.89 | 889 | 19.90 | 8.09 | -21.53 | -15.63 | 0.09 | 0.01 | -14005.47 | 0.06 | - | -0.55 | 0.00 |
| orb_exits_v1-163@s5 | orb30 leve tpnone tr:gb30 tc 15:25 | 1613 | 44.89 | 889 | 19.90 | 8.09 | -21.53 | -15.63 | 0.09 | 0.01 | -14005.47 | 0.06 | - | -0.55 | 0.00 |
| orb_exits_v1-129@s5 | orb15 leve tpnone tr:hl1m tc 15:25 | 1895 | 39.95 | 1138 | 11.20 | 54.69 | -24.57 | -15.64 | 0.28 | 0.07 | -17972.02 | 0.01 | - | -0.50 | 0.00 |
| orb_exits_v1-131@s5 | orb15 leve tpnone tr:hl5m tc 15:25 | 1895 | 39.95 | 1138 | 7.40 | 108.62 | -25.61 | -15.68 | 0.34 | 0.11 | -17839.11 | 0.01 | - | -0.49 | 0.00 |
| orb_exits_v1-136@s5 | orb15 leve tpnone tr:gb40 ta 15:25 | 1895 | 39.95 | 1138 | 21.20 | 8.04 | -22.06 | -15.68 | 0.10 | 0.00 | -17846.59 | 0.03 | - | -0.52 | 0.00 |
| orb_exits_v1-137@s5 | orb15 leve tpnone tr:gb40 tc 15:25 | 1895 | 39.95 | 1138 | 21.20 | 8.04 | -22.06 | -15.68 | 0.10 | 0.00 | -17846.59 | 0.03 | - | -0.52 | 0.00 |
| orb_exits_v1-164@s5 | orb30 leve tpnone tr:gb40 ta 15:25 | 1613 | 44.89 | 889 | 19.90 | 7.85 | -21.53 | -15.68 | 0.09 | 0.00 | -14025.95 | 0.05 | - | -0.56 | 0.00 |
| orb_exits_v1-165@s5 | orb30 leve tpnone tr:gb40 tc 15:25 | 1613 | 44.89 | 889 | 19.90 | 7.85 | -21.53 | -15.68 | 0.09 | 0.00 | -14025.95 | 0.05 | - | -0.56 | 0.00 |
| orb_exits_v1-144@s5 | orb30 leve tpnone tr:be10 ta 15:25 | 1613 | 44.89 | 889 | 1.50 | 220.49 | -23.77 | -15.70 | 0.17 | 0.07 | -14008.09 | 0.02 | - | -0.55 | 0.00 |
| orb_exits_v1-145@s5 | orb30 leve tpnone tr:be10 tc 15:25 | 1613 | 44.89 | 889 | 1.50 | 220.49 | -23.77 | -15.70 | 0.17 | 0.07 | -14008.09 | 0.02 | - | -0.55 | 0.00 |
| orb_exits_v1-146@s5 | orb30 leve tpnone tr:be15 ta 15:25 | 1613 | 44.89 | 889 | 1.50 | 220.49 | -23.77 | -15.70 | 0.17 | 0.07 | -14008.09 | 0.02 | - | -0.55 | 0.00 |
| orb_exits_v1-100@s5 | orb15 leve tpC/$0.03 ta 15:25 | 1895 | 39.95 | 1138 | 15.50 | 13.90 | -21.44 | -15.73 | 0.12 | 0.01 | -17922.00 | -0.05 | -0.16 | -0.64 | 0.00 |
| orb_exits_v1-101@s5 | orb15 leve tpC/$0.03 tc 15:25 | 1895 | 39.95 | 1138 | 15.20 | 16.26 | -21.47 | -15.73 | 0.14 | 0.02 | -17920.46 | -0.05 | -0.16 | -0.64 | 0.00 |
| orb_exits_v1-127@s5 | orb15 leve tpnone tr:L3 tc 15:25 | 1895 | 39.95 | 1138 | 15.40 | 37.96 | -25.52 | -15.73 | 0.27 | 0.05 | -17926.27 | 0.01 | - | -0.51 | 0.00 |
| orb_exits_v1-130@s5 | orb15 leve tpnone tr:hl5m ta 15:25 | 1895 | 39.95 | 1138 | 3.40 | 112.22 | -25.71 | -15.74 | 0.20 | 0.06 | -17910.78 | 0.01 | - | -0.51 | 0.00 |
| orb_exits_v1-011@s5 | orb15 leve tpB/$0.03 tc 15:25 | 1895 | 39.95 | 1138 | 14.70 | 10.85 | -20.33 | -15.76 | 0.09 | 0.01 | -17938.58 | 0.00 | -0.16 | -0.65 | 0.00 |
| orb_exits_v1-152@s5 | orb30 leve tpnone tr:L2 ta 15:25 | 1613 | 44.89 | 889 | 14.70 | 21.50 | -23.83 | -15.76 | 0.17 | 0.03 | -14060.03 | 0.03 | - | -0.55 | 0.00 |
| orb_exits_v1-010@s5 | orb15 leve tpB/$0.03 ta 15:25 | 1895 | 39.95 | 1138 | 14.10 | 10.29 | -20.37 | -15.77 | 0.09 | 0.01 | -17949.57 | 0.00 | -0.16 | -0.65 | 0.00 |
| orb_exits_v1-157@s5 | orb30 leve tpnone tr:hl1m tc 15:25 | 1613 | 44.89 | 889 | 9.10 | 56.18 | -22.98 | -15.77 | 0.24 | 0.06 | -14197.24 | 0.02 | - | -0.54 | 0.00 |
| orb_exits_v1-122@s5 | orb15 leve tpnone tr:L1 ta 15:25 | 1895 | 39.95 | 1138 | 13.10 | 29.02 | -25.79 | -15.78 | 0.19 | 0.02 | -17978.61 | 0.01 | - | -0.51 | 0.00 |
| orb_exits_v1-031@s5 | orb15 leve tpB/0.1atr tc 15:25 | 1895 | 39.95 | 1138 | 14.50 | 10.73 | -20.33 | -15.83 | 0.09 | 0.01 | -18019.50 | -0.00 | -0.16 | -0.65 | 0.00 |
| orb_exits_v1-030@s5 | orb15 leve tpB/0.1atr ta 15:25 | 1895 | 39.95 | 1138 | 14.00 | 10.16 | -20.37 | -15.84 | 0.08 | 0.01 | -18030.49 | -0.01 | -0.16 | -0.65 | 0.00 |
| orb_exits_v1-051@s5 | orb30 leve tpB/0.05% tc 15:25 | 1613 | 44.89 | 889 | 13.50 | 13.79 | -20.47 | -15.84 | 0.10 | 0.02 | -14091.44 | 0.02 | 0.12 | -0.69 | 0.00 |
| orb_exits_v1-050@s5 | orb30 leve tpB/0.05% ta 15:25 | 1613 | 44.89 | 889 | 12.80 | 12.74 | -20.57 | -15.86 | 0.09 | 0.01 | -14101.52 | 0.02 | 0.12 | -0.69 | 0.00 |
| orb_exits_v1-128@s5 | orb15 leve tpnone tr:hl1m ta 15:25 | 1895 | 39.95 | 1138 | 6.60 | 56.19 | -25.68 | -15.86 | 0.19 | 0.04 | -18228.86 | 0.00 | - | -0.51 | 0.00 |
| orb_exits_v1-102@s5 | orb30 leve tpC/$0.03 ta 15:25 | 1613 | 44.89 | 889 | 14.20 | 11.32 | -20.82 | -16.01 | 0.09 | 0.01 | -14316.71 | -0.09 | -0.13 | -0.69 | 0.00 |
| orb_exits_v1-125@s5 | orb15 leve tpnone tr:L2 tc 15:25 | 1895 | 39.95 | 1138 | 20.30 | 21.94 | -25.75 | -16.04 | 0.22 | 0.03 | -18296.33 | -0.01 | - | -0.51 | 0.00 |
| orb_exits_v1-103@s5 | orb30 leve tpC/$0.03 tc 15:25 | 1613 | 44.89 | 889 | 13.80 | 13.74 | -20.85 | -16.06 | 0.11 | 0.01 | -14355.77 | -0.09 | -0.13 | -0.69 | 0.00 |
| orb_exits_v1-123@s5 | orb15 leve tpnone tr:L1 tc 15:25 | 1895 | 39.95 | 1138 | 17.50 | 28.48 | -25.57 | -16.09 | 0.24 | 0.02 | -18336.48 | -0.01 | - | -0.53 | 0.00 |
| orb_exits_v1-124@s5 | orb15 leve tpnone tr:L2 ta 15:25 | 1895 | 39.95 | 1138 | 17.20 | 20.16 | -25.79 | -16.11 | 0.18 | 0.02 | -18370.56 | -0.02 | - | -0.52 | 0.00 |
| orb_exits_v1-159@s5 | orb30 leve tpnone tr:hl5m tc 15:25 | 1613 | 44.89 | 889 | 6.90 | 87.36 | -23.78 | -16.15 | 0.27 | 0.08 | -14396.63 | -0.01 | - | -0.56 | 0.00 |
| orb_exits_v1-153@s5 | orb30 leve tpnone tr:L2 tc 15:25 | 1613 | 44.89 | 889 | 17.30 | 20.42 | -23.90 | -16.22 | 0.18 | 0.03 | -14455.95 | -0.02 | - | -0.57 | 0.00 |
| orb_exits_v1-154@s5 | orb30 leve tpnone tr:L3 ta 15:25 | 1613 | 44.89 | 889 | 8.70 | 30.80 | -23.83 | -16.26 | 0.14 | 0.02 | -14575.96 | -0.02 | - | -0.57 | 0.00 |
| orb_exits_v1-126@s5 | orb15 leve tpnone tr:L3 ta 15:25 | 1895 | 39.95 | 1138 | 10.70 | 30.77 | -25.79 | -16.28 | 0.17 | 0.02 | -18549.58 | -0.03 | - | -0.52 | 0.00 |
| orb_exits_v1-156@s5 | orb30 leve tpnone tr:hl1m ta 15:25 | 1613 | 44.89 | 889 | 5.30 | 50.29 | -23.77 | -16.30 | 0.14 | 0.03 | -14682.85 | -0.02 | - | -0.57 | 0.00 |
| orb_exits_v1-160@s5 | orb30 leve tpnone tr:lvl ta 15:25 | 1613 | 44.89 | 889 | 8.30 | 29.27 | -23.20 | -16.30 | 0.13 | 0.02 | -14628.03 | -0.03 | - | -0.57 | 0.00 |
| orb_exits_v1-161@s5 | orb30 leve tpnone tr:lvl tc 15:25 | 1613 | 44.89 | 889 | 12.10 | 27.82 | -22.45 | -16.34 | 0.17 | 0.03 | -14645.46 | -0.04 | - | -0.57 | 0.00 |
| orb_exits_v1-108@s5 | orb30 leve tpE/$0.03 ta 15:25 | 1613 | 44.89 | 889 | 7.30 | 28.17 | -22.34 | -16.39 | 0.11 | 0.03 | -14572.09 | -0.08 | -0.13 | -0.70 | 0.00 |
| orb_exits_v1-150@s5 | orb30 leve tpnone tr:L1 ta 15:25 | 1613 | 44.89 | 889 | 11.70 | 21.42 | -23.83 | -16.42 | 0.13 | 0.01 | -14637.30 | -0.04 | - | -0.57 | 0.00 |
| orb_exits_v1-109@s5 | orb30 leve tpE/$0.03 tc 15:25 | 1613 | 44.89 | 889 | 9.90 | 35.03 | -22.21 | -16.55 | 0.17 | 0.06 | -14716.50 | -0.08 | -0.13 | -0.71 | 0.00 |
| orb_exits_v1-158@s5 | orb30 leve tpnone tr:hl5m ta 15:25 | 1613 | 44.89 | 889 | 2.90 | 80.95 | -23.83 | -16.56 | 0.12 | 0.03 | -14777.14 | -0.04 | - | -0.58 | 0.00 |
| orb_exits_v1-148@s5 | orb30 leve tpnone tr:belevel ta 15:25 | 1613 | 44.89 | 889 | 0.40 | 150.22 | -21.20 | -16.71 | 0.04 | 0.01 | -14854.92 | -0.16 | -0.13 | -0.72 | 0.00 |
| orb_exits_v1-151@s5 | orb30 leve tpnone tr:L1 tc 15:25 | 1613 | 44.89 | 889 | 15.50 | 21.72 | -23.84 | -16.77 | 0.17 | 0.01 | -14928.75 | -0.07 | - | -0.58 | 0.00 |
| orb_exits_v1-149@s5 | orb30 leve tpnone tr:belevel tc 15:25 | 1613 | 44.89 | 889 | 0.60 | 120.24 | -21.20 | -17.07 | 0.04 | 0.01 | -15173.07 | -0.20 | -0.13 | -0.74 | 0.00 |


Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_orb_exits_v1@s5_2026-10-31.csv.gz`.

Labels: BACKTEST (in-sample on DEV). Spread: MODELED-SPREAD 5.0% (sensitivity). Delta: BS-EST. Not financial advice: evidence for Nick to decide.
