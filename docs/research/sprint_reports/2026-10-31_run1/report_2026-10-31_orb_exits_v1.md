# Sprint report: orb_exits_v1 (DEV), MODELED-SPREAD

Generated 2026-10-31 06:17 on `grok-bot-vm-510907181` by sprint engine `2026-10-31.sprint1` in 4.0 min. Spec sha256 `ff58a7d2caed1125a7d49a42f95783a043cdd860ce9c6743b5ee91798f54896d`.

**Every number below is a BACKTEST in-sample (DEV)** on Alpaca 1-minute bars, 2024-08-01 to 2026-06-30. Option fills are real traded prices +/- a half-spread: **MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005**. Fees $0.65 per contract per side. P/L is per 1-contract unit. Deltas are BS-EST (Black-Scholes from the option's price). Nothing here is a live or paper fill.

Data: IWM: 479 sessions, QQQ: 479 sessions, SPY: 479 sessions. Runs in this spec: 195. Trials counted for the deflated Sharpe: 283 (docs/research/sprint_runs.csv + data/sprint/runs_*.csv + this spec).

Known limits: July 2024 is locked (L2), so early-August 2024 sessions have partial history; news and VIX are unknown in the backtest (rules that need them never fire); a contract needs BS-EST |delta| inside the band, so some signals have no contract (counted as skips).

**Cost caveat:** MODELED-SPREAD: half-spread = 2% of premium (SPY/QQQ/IWM), 10% single stocks, floor $0.005. The pre-registered default (2% of premium for SPY/QQQ/IWM, amended from 5% before any run, see SPRINT_PLAN) is a placeholder until the desk's logged chains exist; the 5% rerun is the stress test. Results that depend on small option moves (near level targets, tight trails, small fixed targets) are the most sensitive to it.

Spec: The sprint's FIRST question (SPRINT_PLAN 'First answer'): ORB breakout both sides (15/30/60-minute ranges, first finished 1-minute close beyond, first break per side, signal bars finishing by 12:00) on SPY, QQQ and IWM 0DTE options, delta 0.40-0.55 (target 0.45, BS-EST). Which exit makes the most money after costs: the current fixed-% plan A (about 1:1), a key-level target B, the half-and-trail C, the rejection-or-next-level E, or a trailing stop? Each block below varies one thing; every run uses the same entries, so the exits differ only in their rule. 195 runs. Robustness (nudges, matched random entries, made-up levels) runs on the top 5 by expectancy with at least 60 trades.

## Exit families side by side: current plan vs best level target vs best trail

Best of each family by expectancy among runs with at least 60 trades (else the best with any trades).

| family | run | config | trades | win% | avg win | avg loss | exp $ | PF | PF 2x | max DD | CI95 exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plain stop + time | orb_exits_v1-003 | orb60 prem tpnone tb 15:25 | 1035 | 6.40 | 303.93 | -23.47 | -2.60 | 0.88 | 0.62 | -8526.74 | -11.9..8.14 |
| A: current fixed-% plan | orb_exits_v1-008 | orb60 prem tpA ta 15:25 | 1035 | 21.50 | 24.40 | -18.05 | -6.01 | 0.47 | 0.23 | -6243.18 | -7.53..-4.52 |
| B: best level target | orb_exits_v1-087 | orb60 leve tpB/0.05% rr2.5 tc 15:25 | 78 | 15.40 | 38.77 | -11.17 | -3.48 | 0.63 | 0.37 | -296.64 | -7.46..0.95 |
| best trail | orb_exits_v1-170 | orb60 leve tpnone tr:be8 ta 15:25 | 835 | 1.60 | 502.31 | -16.27 | -2.86 | 0.73 | 0.38 | -4045.83 | -8.41..4.32 |
| best C/D/E | orb_exits_v1-106 | orb15 leve tpE/$0.03 ta 15:25 | 1509 | 14.30 | 39.49 | -18.42 | -6.53 | 0.46 | 0.23 | -9855.31 | -8.3..-4.71 |


## Robustness on the top 5 runs

### orb_exits_v1-003: orb60 prem tpnone tb 15:25

Trades 1035, win 6%, avg win 303.93, avg loss -23.47, expectancy **-2.60** (2x slippage -11.28), PF 0.88 (2x 0.62), max DD -8526.74, % of peak kept 0.06, planned R:R - vs actual -0.16, expectancy CI95 [-11.9, 8.14], deflated Sharpe 0.000 (N=283).

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
| Aug-Dec 2024 | 219 | -134.17 | -0.61 | 0.97 |
| 2025 | 535 | -3119.46 | -5.83 | 0.74 |
| Jan-Jun 2026 | 281 | 567.43 | 2.02 | 1.08 |
| 2m: Aug 2024-Sep 2024 | 115 | -188.69 | -1.64 | 0.92 |
| 2m: Oct 2024-Nov 2024 | 64 | 344.61 | 5.38 | 1.33 |
| 2m: Dec 2024-Jan 2025 | 76 | -1051.39 | -13.83 | 0.26 |
| 2m: Feb 2025-Mar 2025 | 90 | -2330.66 | -25.90 | 0.00 |
| 2m: Apr 2025-May 2025 | 101 | -1852.24 | -18.34 | 0.40 |
| 2m: Jun 2025-Jul 2025 | 84 | -933.45 | -11.11 | 0.36 |
| 2m: Aug 2025-Sep 2025 | 82 | -910.63 | -11.11 | 0.36 |
| 2m: Oct 2025-Nov 2025 | 99 | 3619.56 | 36.56 | 2.75 |
| 2m: Dec 2025-Jan 2026 | 85 | -761.52 | -8.96 | 0.54 |
| 2m: Feb 2026-Mar 2026 | 97 | -185.07 | -1.91 | 0.93 |
| 2m: Apr 2026-May 2026 | 96 | -979.71 | -10.21 | 0.53 |
| 2m: Jun 2026-Jul 2026 | 46 | 2542.99 | 55.28 | 2.99 |


Sides: calls n=542 exp -13.84 PF 0.32; puts n=493 exp 9.77 PF 1.41
Symbols: IWM n=254 exp -3.38 PF 0.76; QQQ n=387 exp -0.46 PF 0.98; SPY n=394 exp -4.19 PF 0.82
Without the best 5 trades: net -9790.64, expectancy -9.51.
One-step nudges: entry=orb30 n=1452 PF 0.81 exp -4.56; allout=15:50 n=1035 PF 0.88 exp -2.74
Matched random entries (5 paths): expectancy 2.84, 4.95, 7.99, 3.19, 2.65; the run beats 0% of paths.
Exit reasons: {'CEILING STOP': 967, 'ALL OUT': 68}.
Median option MFE 0.122, MAE -0.200; median stock MFE $0.330; median distance from the stock's price at the option's peak to the nearest level $0.090; median minutes held 5.
Skipped signals: no contract with BS-EST |delta| in 0.40-0.55 162.

### orb_exits_v1-170: orb60 leve tpnone tr:be8 ta 15:25

Trades 835, win 2%, avg win 502.31, avg loss -16.27, expectancy **-2.86** (2x slippage -12.19), PF 0.73 (2x 0.38), max DD -4045.83, % of peak kept 0.13, planned R:R - vs actual -0.17, expectancy CI95 [-8.41, 4.32], deflated Sharpe 0.000 (N=283).

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
| Aug-Dec 2024 | 163 | -1531.09 | -9.39 | 0.13 |
| 2025 | 446 | -837.03 | -1.88 | 0.81 |
| Jan-Jun 2026 | 226 | -17.53 | -0.08 | 0.99 |
| 2m: Aug 2024-Sep 2024 | 89 | -1022.11 | -11.48 | 0.00 |
| 2m: Oct 2024-Nov 2024 | 46 | -231.01 | -5.02 | 0.49 |
| 2m: Dec 2024-Jan 2025 | 57 | -595.08 | -10.44 | 0.00 |
| 2m: Feb 2025-Mar 2025 | 78 | -721.53 | -9.25 | 0.00 |
| 2m: Apr 2025-May 2025 | 92 | -177.14 | -1.93 | 0.83 |
| 2m: Jun 2025-Jul 2025 | 73 | -696.44 | -9.54 | 0.00 |
| 2m: Aug 2025-Sep 2025 | 64 | -471.27 | -7.36 | 0.32 |
| 2m: Oct 2025-Nov 2025 | 79 | 1638.14 | 20.74 | 3.47 |
| 2m: Dec 2025-Jan 2026 | 66 | -434.39 | -6.58 | 0.28 |
| 2m: Feb 2026-Mar 2026 | 83 | 447.16 | 5.39 | 1.40 |
| 2m: Apr 2026-May 2026 | 73 | -535.06 | -7.33 | 0.31 |
| 2m: Jun 2026-Jul 2026 | 35 | 413.08 | 11.80 | 1.76 |


Sides: calls n=449 exp -9.22 PF 0.10; puts n=386 exp 4.54 PF 1.41
Symbols: IWM n=200 exp 1.45 PF 1.20; QQQ n=307 exp -2.35 PF 0.82; SPY n=328 exp -5.95 PF 0.42
Without the best 5 trades: net -6963.67, expectancy -8.39.
One-step nudges: entry=orb30 n=1199 PF 0.50 exp -6.30; trail=be6 n=835 PF 0.54 exp -4.65; trail=be10 n=835 PF 0.69 exp -3.50; allout=15:50 n=835 PF 0.84 exp -1.74
Matched random entries (5 paths): expectancy -1.56, -0.09, 1.05, -5.22, 3.64; the run beats 20% of paths.
Exit reasons: {'BREAKEVEN STOP': 311, 'LEVEL STOP': 290, 'CEILING STOP': 167, 'IF FLAT': 54, 'ALL OUT': 13}.
Median option MFE 0.075, MAE -0.112; median stock MFE $0.202; median distance from the stock's price at the option's peak to the nearest level $0.083; median minutes held 2.
Skipped signals: level stop does not fit 200, no contract with BS-EST |delta| in 0.40-0.55 162.

### orb_exits_v1-171: orb60 leve tpnone tr:be8 tc 15:25

Trades 835, win 2%, avg win 502.31, avg loss -16.27, expectancy **-2.86** (2x slippage -12.19), PF 0.73 (2x 0.38), max DD -4045.83, % of peak kept 0.13, planned R:R - vs actual -0.17, expectancy CI95 [-8.41, 4.32], deflated Sharpe 0.000 (N=283).

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
| Aug-Dec 2024 | 163 | -1531.09 | -9.39 | 0.13 |
| 2025 | 446 | -837.03 | -1.88 | 0.81 |
| Jan-Jun 2026 | 226 | -17.53 | -0.08 | 0.99 |
| 2m: Aug 2024-Sep 2024 | 89 | -1022.11 | -11.48 | 0.00 |
| 2m: Oct 2024-Nov 2024 | 46 | -231.01 | -5.02 | 0.49 |
| 2m: Dec 2024-Jan 2025 | 57 | -595.08 | -10.44 | 0.00 |
| 2m: Feb 2025-Mar 2025 | 78 | -721.53 | -9.25 | 0.00 |
| 2m: Apr 2025-May 2025 | 92 | -177.14 | -1.93 | 0.83 |
| 2m: Jun 2025-Jul 2025 | 73 | -696.44 | -9.54 | 0.00 |
| 2m: Aug 2025-Sep 2025 | 64 | -471.27 | -7.36 | 0.32 |
| 2m: Oct 2025-Nov 2025 | 79 | 1638.14 | 20.74 | 3.47 |
| 2m: Dec 2025-Jan 2026 | 66 | -434.39 | -6.58 | 0.28 |
| 2m: Feb 2026-Mar 2026 | 83 | 447.16 | 5.39 | 1.40 |
| 2m: Apr 2026-May 2026 | 73 | -535.06 | -7.33 | 0.31 |
| 2m: Jun 2026-Jul 2026 | 35 | 413.08 | 11.80 | 1.76 |


Sides: calls n=449 exp -9.22 PF 0.10; puts n=386 exp 4.54 PF 1.41
Symbols: IWM n=200 exp 1.45 PF 1.20; QQQ n=307 exp -2.35 PF 0.82; SPY n=328 exp -5.95 PF 0.42
Without the best 5 trades: net -6963.67, expectancy -8.39.
One-step nudges: entry=orb30 n=1199 PF 0.50 exp -6.30; trail=be6 n=835 PF 0.54 exp -4.65; trail=be10 n=835 PF 0.69 exp -3.52; allout=15:50 n=835 PF 0.84 exp -1.74
Matched random entries (5 paths): expectancy -1.56, -0.09, 1.05, -5.22, 3.64; the run beats 20% of paths.
Exit reasons: {'BREAKEVEN STOP': 311, 'LEVEL STOP': 290, 'CEILING STOP': 167, 'IF FLAT': 54, 'ALL OUT': 13}.
Median option MFE 0.075, MAE -0.112; median stock MFE $0.202; median distance from the stock's price at the option's peak to the nearest level $0.083; median minutes held 2.
Skipped signals: level stop does not fit 200, no contract with BS-EST |delta| in 0.40-0.55 162.

### orb_exits_v1-176: orb60 leve tpnone tr:belevel ta 15:25

Trades 835, win 1%, avg win 512.05, avg loss -15.59, expectancy **-3.32** (2x slippage -12.73), PF 0.67 (2x 0.34), max DD -3916.46, % of peak kept 0.12, planned R:R 0.38 vs actual -0.30, expectancy CI95 [-8.17, 3.13], deflated Sharpe 0.000 (N=283).

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
- [ ] real levels beat made-up levels

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 163 | -1691.58 | -10.38 | 0.00 |
| 2025 | 446 | -519.42 | -1.16 | 0.87 |
| Jan-Jun 2026 | 226 | -562.11 | -2.49 | 0.79 |
| 2m: Aug 2024-Sep 2024 | 89 | -952.49 | -10.70 | 0.00 |
| 2m: Oct 2024-Nov 2024 | 46 | -461.12 | -10.02 | 0.00 |
| 2m: Dec 2024-Jan 2025 | 57 | -592.62 | -10.40 | 0.00 |
| 2m: Feb 2025-Mar 2025 | 78 | -608.02 | -7.80 | 0.00 |
| 2m: Apr 2025-May 2025 | 92 | -22.53 | -0.24 | 0.97 |
| 2m: Jun 2025-Jul 2025 | 73 | -735.21 | -10.07 | 0.00 |
| 2m: Aug 2025-Sep 2025 | 64 | -413.22 | -6.46 | 0.35 |
| 2m: Oct 2025-Nov 2025 | 79 | 1688.59 | 21.37 | 3.75 |
| 2m: Dec 2025-Jan 2026 | 66 | -457.09 | -6.93 | 0.28 |
| 2m: Feb 2026-Mar 2026 | 83 | -206.34 | -2.49 | 0.81 |
| 2m: Apr 2026-May 2026 | 73 | -492.37 | -6.74 | 0.33 |
| 2m: Jun 2026-Jul 2026 | 35 | 479.31 | 13.69 | 2.01 |


Sides: calls n=449 exp -8.46 PF 0.11; puts n=386 exp 2.66 PF 1.25
Symbols: IWM n=200 exp 1.39 PF 1.19; QQQ n=307 exp -1.47 PF 0.88; SPY n=328 exp -7.93 PF 0.17
Without the best 5 trades: net -7196.01, expectancy -8.67.
One-step nudges: entry=orb30 n=1199 PF 0.50 exp -6.01; tp_buffer=0.05% n=835 PF 0.70 exp -3.35; allout=15:50 n=835 PF 0.75 exp -2.52
Matched random entries (5 paths): expectancy -0.26, 0.39, 0.02, -2.21, 2.96; the run beats 0% of paths.
Made-up levels (20 seeds): mean expectancy -2.40; real levels beat 10% of seeds.
Exit reasons: {'BREAKEVEN STOP': 337, 'LEVEL STOP': 280, 'CEILING STOP': 162, 'IF FLAT': 45, 'ALL OUT': 11}.
Median option MFE 0.074, MAE -0.107; median stock MFE $0.200; median distance from the stock's price at the option's peak to the nearest level $0.084; median minutes held 2.
Skipped signals: level stop does not fit 200, no contract with BS-EST |delta| in 0.40-0.55 162.

### orb_exits_v1-087: orb60 leve tpB/0.05% rr2.5 tc 15:25

Trades 78, win 15%, avg win 38.77, avg loss -11.17, expectancy **-3.48** (2x slippage -9.02), PF 0.63 (2x 0.37), max DD -296.64, % of peak kept 0.11, planned R:R 4.10 vs actual -0.41, expectancy CI95 [-7.46, 0.95], deflated Sharpe 0.000 (N=283).

Checklist (SPRINT_PLAN robustness):

- [x] at least 60 trades
- [ ] PF >= 1.25
- [ ] PF > 1.0 at 2x slippage
- [ ] profitable in each stretch
- [ ] positive without best 5
- [ ] both sides profitable (sides traded)
- [x] profitable two-month blocks: 4 of 12 (info)
- [ ] every one-step nudge keeps PF > 1.1
- [ ] beats matched random entries
- [x] filter beats random day-skips
- [ ] real levels beat made-up levels

| stretch / two-month block | trades | net $ | exp $ | PF |
|---|---|---|---|---|
| Aug-Dec 2024 | 18 | -146.43 | -8.13 | 0.17 |
| 2025 | 45 | -93.76 | -2.08 | 0.77 |
| Jan-Jun 2026 | 15 | -31.53 | -2.10 | 0.80 |
| 2m: Aug 2024-Sep 2024 | 8 | -83.30 | -10.41 | 0.00 |
| 2m: Oct 2024-Nov 2024 | 7 | -31.88 | -4.55 | 0.49 |
| 2m: Dec 2024-Jan 2025 | 6 | -27.68 | -4.61 | 0.52 |
| 2m: Feb 2025-Mar 2025 | 2 | -23.70 | -11.85 | 0.00 |
| 2m: Apr 2025-May 2025 | 5 | -67.31 | -13.46 | 0.00 |
| 2m: Jun 2025-Jul 2025 | 10 | -47.12 | -4.71 | 0.47 |
| 2m: Aug 2025-Sep 2025 | 13 | 16.93 | 1.30 | 1.17 |
| 2m: Oct 2025-Nov 2025 | 7 | 73.15 | 10.45 | 2.50 |
| 2m: Dec 2025-Jan 2026 | 9 | -90.57 | -10.06 | 0.00 |
| 2m: Feb 2026-Mar 2026 | 3 | 11.05 | 3.68 | 1.32 |
| 2m: Apr 2026-May 2026 | 4 | 1.28 | 0.32 | 1.03 |
| 2m: Jun 2026-Jul 2026 | 4 | -2.57 | -0.64 | 0.93 |


Sides: calls n=46 exp -2.63 PF 0.71; puts n=32 exp -4.71 PF 0.52
Symbols: IWM n=32 exp -5.55 PF 0.43; QQQ n=18 exp -5.02 PF 0.55; SPY n=28 exp -0.14 PF 0.98
Without the best 5 trades: net -493.50, expectancy -6.76.
One-step nudges: entry=orb30 n=115 PF 0.55 exp -4.69; tp_buffer=$0.03 n=53 PF 0.20 exp -9.12; tp_buffer=0.1atr n=52 PF 0.18 exp -9.41; rr_min=2.0 n=112 PF 0.59 exp -4.05; rr_min=3.0 n=55 PF 0.74 exp -2.23; allout=15:50 n=78 PF 0.63 exp -3.48
Matched random entries (5 paths): expectancy -1.08, -8.74, -9.71, -10.16, -4.35; the run beats 80% of paths.
Made-up levels (20 seeds): mean expectancy -4.84; real levels beat 80% of seeds.
Filter vs random day-skips (twin orb_exits_v1-081, 333 days removed): p = 0.024 (filtered exp -3.48, random-skip mean -6.25).
Exit reasons: {'LEVEL STOP': 35, 'CEILING STOP': 20, 'LEVEL TARGET': 12, 'IF FLAT': 11}.
Median option MFE 0.069, MAE -0.117; median stock MFE $0.150; median distance from the stock's price at the option's peak to the nearest level $0.060; median minutes held 2.0.
Skipped signals: R:R below 757, level stop does not fit 200, no contract with BS-EST |delta| in 0.40-0.55 162.

## Filters vs random day-skips (every filtered run with its unfiltered twin)

| run | config | twin | days skipped | filtered exp | random-skip exp | p |
|---|---|---|---|---|---|---|
| orb_exits_v1-012 | orb15 leve tpB/$0.03 rr1.5 ta 15:25 | orb_exits_v1-010 | 314 | -5.99 | -7.00 | 0.10 |
| orb_exits_v1-013 | orb15 leve tpB/$0.03 rr1.5 tc 15:25 | orb_exits_v1-011 | 314 | -5.50 | -6.84 | 0.05 |
| orb_exits_v1-014 | orb15 leve tpB/$0.03 rr2 ta 15:25 | orb_exits_v1-010 | 383 | -6.81 | -6.97 | 0.41 |
| orb_exits_v1-015 | orb15 leve tpB/$0.03 rr2 tc 15:25 | orb_exits_v1-011 | 383 | -8.33 | -6.81 | 0.91 |
| orb_exits_v1-016 | orb15 leve tpB/$0.03 rr2.5 ta 15:25 | orb_exits_v1-010 | 416 | -8.10 | -7.02 | 0.78 |
| orb_exits_v1-017 | orb15 leve tpB/$0.03 rr2.5 tc 15:25 | orb_exits_v1-011 | 416 | -10.61 | -6.87 | 0.99 |
| orb_exits_v1-018 | orb15 leve tpB/$0.03 rr3 ta 15:25 | orb_exits_v1-010 | 433 | -6.37 | -6.97 | 0.33 |
| orb_exits_v1-019 | orb15 leve tpB/$0.03 rr3 tc 15:25 | orb_exits_v1-011 | 433 | -9.73 | -6.78 | 0.94 |
| orb_exits_v1-022 | orb15 leve tpB/0.05% rr1.5 ta 15:25 | orb_exits_v1-020 | 252 | -5.13 | -6.75 | 0.00 |
| orb_exits_v1-023 | orb15 leve tpB/0.05% rr1.5 tc 15:25 | orb_exits_v1-021 | 252 | -6.37 | -7.07 | 0.16 |
| orb_exits_v1-024 | orb15 leve tpB/0.05% rr2 ta 15:25 | orb_exits_v1-020 | 312 | -4.74 | -6.78 | 0.01 |
| orb_exits_v1-025 | orb15 leve tpB/0.05% rr2 tc 15:25 | orb_exits_v1-021 | 312 | -6.16 | -7.10 | 0.14 |
| orb_exits_v1-026 | orb15 leve tpB/0.05% rr2.5 ta 15:25 | orb_exits_v1-020 | 354 | -3.98 | -6.78 | 0.00 |
| orb_exits_v1-027 | orb15 leve tpB/0.05% rr2.5 tc 15:25 | orb_exits_v1-021 | 354 | -5.98 | -7.09 | 0.16 |
| orb_exits_v1-028 | orb15 leve tpB/0.05% rr3 ta 15:25 | orb_exits_v1-020 | 388 | -4.94 | -6.90 | 0.08 |
| orb_exits_v1-029 | orb15 leve tpB/0.05% rr3 tc 15:25 | orb_exits_v1-021 | 388 | -6.43 | -7.21 | 0.28 |
| orb_exits_v1-032 | orb15 leve tpB/0.1atr rr1.5 ta 15:25 | orb_exits_v1-030 | 313 | -6.27 | -7.11 | 0.14 |
| orb_exits_v1-033 | orb15 leve tpB/0.1atr rr1.5 tc 15:25 | orb_exits_v1-031 | 313 | -6.57 | -7.01 | 0.27 |
| orb_exits_v1-034 | orb15 leve tpB/0.1atr rr2 ta 15:25 | orb_exits_v1-030 | 381 | -8.07 | -7.08 | 0.81 |
| orb_exits_v1-035 | orb15 leve tpB/0.1atr rr2 tc 15:25 | orb_exits_v1-031 | 381 | -9.93 | -6.98 | 0.99 |
| orb_exits_v1-036 | orb15 leve tpB/0.1atr rr2.5 ta 15:25 | orb_exits_v1-030 | 412 | -7.73 | -7.08 | 0.67 |
| orb_exits_v1-037 | orb15 leve tpB/0.1atr rr2.5 tc 15:25 | orb_exits_v1-031 | 412 | -10.53 | -6.98 | 0.99 |
| orb_exits_v1-038 | orb15 leve tpB/0.1atr rr3 ta 15:25 | orb_exits_v1-030 | 430 | -6.57 | -7.12 | 0.37 |
| orb_exits_v1-039 | orb15 leve tpB/0.1atr rr3 tc 15:25 | orb_exits_v1-031 | 430 | -10.33 | -6.99 | 0.97 |
| orb_exits_v1-042 | orb30 leve tpB/$0.03 rr1.5 ta 15:25 | orb_exits_v1-040 | 322 | -6.88 | -7.70 | 0.19 |
| orb_exits_v1-043 | orb30 leve tpB/$0.03 rr1.5 tc 15:25 | orb_exits_v1-041 | 322 | -7.36 | -7.71 | 0.36 |
| orb_exits_v1-044 | orb30 leve tpB/$0.03 rr2 ta 15:25 | orb_exits_v1-040 | 372 | -5.87 | -7.64 | 0.10 |
| orb_exits_v1-045 | orb30 leve tpB/$0.03 rr2 tc 15:25 | orb_exits_v1-041 | 372 | -7.76 | -7.66 | 0.51 |
| orb_exits_v1-046 | orb30 leve tpB/$0.03 rr2.5 ta 15:25 | orb_exits_v1-040 | 402 | -5.71 | -7.70 | 0.12 |
| orb_exits_v1-047 | orb30 leve tpB/$0.03 rr2.5 tc 15:25 | orb_exits_v1-041 | 402 | -9.23 | -7.71 | 0.83 |
| orb_exits_v1-048 | orb30 leve tpB/$0.03 rr3 ta 15:25 | orb_exits_v1-040 | 421 | -6.16 | -7.60 | 0.22 |
| orb_exits_v1-049 | orb30 leve tpB/$0.03 rr3 tc 15:25 | orb_exits_v1-041 | 421 | -8.47 | -7.62 | 0.66 |
| orb_exits_v1-052 | orb30 leve tpB/0.05% rr1.5 ta 15:25 | orb_exits_v1-050 | 277 | -7.15 | -7.93 | 0.17 |
| orb_exits_v1-053 | orb30 leve tpB/0.05% rr1.5 tc 15:25 | orb_exits_v1-051 | 277 | -7.54 | -8.10 | 0.24 |
| orb_exits_v1-054 | orb30 leve tpB/0.05% rr2 ta 15:25 | orb_exits_v1-050 | 325 | -6.38 | -7.99 | 0.08 |
| orb_exits_v1-055 | orb30 leve tpB/0.05% rr2 tc 15:25 | orb_exits_v1-051 | 325 | -6.43 | -8.14 | 0.08 |
| orb_exits_v1-056 | orb30 leve tpB/0.05% rr2.5 ta 15:25 | orb_exits_v1-050 | 361 | -4.46 | -7.98 | 0.01 |
| orb_exits_v1-057 | orb30 leve tpB/0.05% rr2.5 tc 15:25 | orb_exits_v1-051 | 361 | -4.69 | -8.17 | 0.00 |
| orb_exits_v1-058 | orb30 leve tpB/0.05% rr3 ta 15:25 | orb_exits_v1-050 | 386 | -4.85 | -7.94 | 0.04 |
| orb_exits_v1-059 | orb30 leve tpB/0.05% rr3 tc 15:25 | orb_exits_v1-051 | 386 | -5.02 | -8.08 | 0.04 |
| orb_exits_v1-062 | orb30 leve tpB/0.1atr rr1.5 ta 15:25 | orb_exits_v1-060 | 326 | -7.66 | -7.81 | 0.42 |
| orb_exits_v1-063 | orb30 leve tpB/0.1atr rr1.5 tc 15:25 | orb_exits_v1-061 | 326 | -8.28 | -7.86 | 0.64 |
| orb_exits_v1-064 | orb30 leve tpB/0.1atr rr2 ta 15:25 | orb_exits_v1-060 | 377 | -7.01 | -7.86 | 0.26 |
| orb_exits_v1-065 | orb30 leve tpB/0.1atr rr2 tc 15:25 | orb_exits_v1-061 | 377 | -9.23 | -7.92 | 0.84 |
| orb_exits_v1-066 | orb30 leve tpB/0.1atr rr2.5 ta 15:25 | orb_exits_v1-060 | 403 | -5.67 | -7.66 | 0.13 |
| orb_exits_v1-067 | orb30 leve tpB/0.1atr rr2.5 tc 15:25 | orb_exits_v1-061 | 403 | -9.59 | -7.72 | 0.87 |
| orb_exits_v1-068 | orb30 leve tpB/0.1atr rr3 ta 15:25 | orb_exits_v1-060 | 423 | -5.76 | -7.96 | 0.14 |
| orb_exits_v1-069 | orb30 leve tpB/0.1atr rr3 tc 15:25 | orb_exits_v1-061 | 423 | -8.70 | -8.02 | 0.62 |
| orb_exits_v1-072 | orb60 leve tpB/$0.03 rr1.5 ta 15:25 | orb_exits_v1-070 | 301 | -7.08 | -6.19 | 0.84 |
| orb_exits_v1-073 | orb60 leve tpB/$0.03 rr1.5 tc 15:25 | orb_exits_v1-071 | 301 | -7.95 | -6.30 | 0.96 |
| orb_exits_v1-074 | orb60 leve tpB/$0.03 rr2 ta 15:25 | orb_exits_v1-070 | 341 | -5.95 | -6.21 | 0.41 |
| orb_exits_v1-075 | orb60 leve tpB/$0.03 rr2 tc 15:25 | orb_exits_v1-071 | 341 | -7.63 | -6.34 | 0.83 |
| orb_exits_v1-076 | orb60 leve tpB/$0.03 rr2.5 ta 15:25 | orb_exits_v1-070 | 354 | -6.97 | -6.19 | 0.72 |
| orb_exits_v1-077 | orb60 leve tpB/$0.03 rr2.5 tc 15:25 | orb_exits_v1-071 | 354 | -9.12 | -6.32 | 0.98 |
| orb_exits_v1-078 | orb60 leve tpB/$0.03 rr3 ta 15:25 | orb_exits_v1-070 | 368 | -7.21 | -6.31 | 0.69 |
| orb_exits_v1-079 | orb60 leve tpB/$0.03 rr3 tc 15:25 | orb_exits_v1-071 | 368 | -8.84 | -6.44 | 0.92 |
| orb_exits_v1-082 | orb60 leve tpB/0.05% rr1.5 ta 15:25 | orb_exits_v1-080 | 268 | -5.66 | -6.36 | 0.19 |
| orb_exits_v1-083 | orb60 leve tpB/0.05% rr1.5 tc 15:25 | orb_exits_v1-081 | 268 | -4.92 | -6.23 | 0.08 |
| orb_exits_v1-084 | orb60 leve tpB/0.05% rr2 ta 15:25 | orb_exits_v1-080 | 307 | -4.71 | -6.40 | 0.06 |
| orb_exits_v1-085 | orb60 leve tpB/0.05% rr2 tc 15:25 | orb_exits_v1-081 | 307 | -4.05 | -6.30 | 0.03 |
| orb_exits_v1-086 | orb60 leve tpB/0.05% rr2.5 ta 15:25 | orb_exits_v1-080 | 333 | -3.67 | -6.39 | 0.02 |
| orb_exits_v1-087 | orb60 leve tpB/0.05% rr2.5 tc 15:25 | orb_exits_v1-081 | 333 | -3.48 | -6.25 | 0.02 |
| orb_exits_v1-088 | orb60 leve tpB/0.05% rr3 ta 15:25 | orb_exits_v1-080 | 351 | -2.02 | -6.34 | 0.00 |
| orb_exits_v1-089 | orb60 leve tpB/0.05% rr3 tc 15:25 | orb_exits_v1-081 | 351 | -2.23 | -6.20 | 0.02 |
| orb_exits_v1-092 | orb60 leve tpB/0.1atr rr1.5 ta 15:25 | orb_exits_v1-090 | 301 | -7.91 | -6.04 | 0.97 |
| orb_exits_v1-093 | orb60 leve tpB/0.1atr rr1.5 tc 15:25 | orb_exits_v1-091 | 301 | -8.77 | -6.07 | 1.00 |
| orb_exits_v1-094 | orb60 leve tpB/0.1atr rr2 ta 15:25 | orb_exits_v1-090 | 342 | -7.45 | -6.14 | 0.83 |
| orb_exits_v1-095 | orb60 leve tpB/0.1atr rr2 tc 15:25 | orb_exits_v1-091 | 342 | -8.96 | -6.18 | 0.98 |
| orb_exits_v1-096 | orb60 leve tpB/0.1atr rr2.5 ta 15:25 | orb_exits_v1-090 | 356 | -7.49 | -6.07 | 0.83 |
| orb_exits_v1-097 | orb60 leve tpB/0.1atr rr2.5 tc 15:25 | orb_exits_v1-091 | 356 | -9.41 | -6.12 | 0.99 |
| orb_exits_v1-098 | orb60 leve tpB/0.1atr rr3 ta 15:25 | orb_exits_v1-090 | 371 | -7.12 | -6.01 | 0.73 |
| orb_exits_v1-099 | orb60 leve tpB/0.1atr rr3 tc 15:25 | orb_exits_v1-091 | 371 | -9.46 | -6.06 | 0.96 |


## All runs (sorted by expectancy)

`sig` = signals seen, `skip%` = share not traded (no contract, level stop beyond the ceiling, R:R minimum, busy, no print); the top skip reasons per run are in the run log's notes.

| run | config | sig | skip% | n | win% | avg win | avg loss | exp | PF | PF2x | maxDD | kept | pRR | aRR | DSR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| orb_exits_v1-088 | orb60 leve tpB/0.05% rr3 ta 15:25 | 1197 | 95.41 | 55 | 10.90 | 38.48 | -10.06 | -2.02 | 0.68 | 0.33 | -163.45 | 0.30 | 4.67 | -0.29 | 0.00 |
| orb_exits_v1-089 | orb60 leve tpB/0.05% rr3 tc 15:25 | 1197 | 95.41 | 55 | 16.40 | 39.26 | -10.35 | -2.23 | 0.74 | 0.44 | -192.99 | 0.22 | 4.67 | -0.34 | 0.00 |
| orb_exits_v1-003 | orb60 prem tpnone tb 15:25 | 1197 | 13.53 | 1035 | 6.40 | 303.93 | -23.47 | -2.60 | 0.88 | 0.62 | -8526.74 | 0.06 | - | -0.16 | 0.00 |
| orb_exits_v1-170 | orb60 leve tpnone tr:be8 ta 15:25 | 1197 | 30.24 | 835 | 1.60 | 502.31 | -16.27 | -2.86 | 0.73 | 0.38 | -4045.83 | 0.13 | - | -0.17 | 0.00 |
| orb_exits_v1-171 | orb60 leve tpnone tr:be8 tc 15:25 | 1197 | 30.24 | 835 | 1.60 | 502.31 | -16.27 | -2.86 | 0.73 | 0.38 | -4045.83 | 0.13 | - | -0.17 | 0.00 |
| orb_exits_v1-176 | orb60 leve tpnone tr:belevel ta 15:25 | 1197 | 30.24 | 835 | 1.30 | 512.05 | -15.59 | -3.32 | 0.67 | 0.34 | -3916.46 | 0.12 | 0.38 | -0.30 | 0.00 |
| orb_exits_v1-087 | orb60 leve tpB/0.05% rr2.5 tc 15:25 | 1197 | 93.48 | 78 | 15.40 | 38.77 | -11.17 | -3.48 | 0.63 | 0.37 | -296.64 | 0.11 | 4.10 | -0.41 | 0.00 |
| orb_exits_v1-172 | orb60 leve tpnone tr:be10 ta 15:25 | 1197 | 30.24 | 835 | 1.60 | 502.31 | -16.64 | -3.50 | 0.69 | 0.37 | -4238.48 | 0.10 | - | -0.19 | 0.00 |
| orb_exits_v1-174 | orb60 leve tpnone tr:be15 ta 15:25 | 1197 | 30.24 | 835 | 1.60 | 502.31 | -16.64 | -3.50 | 0.69 | 0.37 | -4238.48 | 0.10 | - | -0.19 | 0.00 |
| orb_exits_v1-173 | orb60 leve tpnone tr:be10 tc 15:25 | 1197 | 30.24 | 835 | 1.60 | 502.31 | -16.64 | -3.52 | 0.69 | 0.37 | -4238.48 | 0.10 | - | -0.19 | 0.00 |
| orb_exits_v1-177 | orb60 leve tpnone tr:belevel tc 15:25 | 1197 | 30.24 | 835 | 1.90 | 386.35 | -15.65 | -3.54 | 0.68 | 0.36 | -4184.27 | 0.11 | 0.38 | -0.32 | 0.00 |
| orb_exits_v1-086 | orb60 leve tpB/0.05% rr2.5 ta 15:25 | 1197 | 93.48 | 78 | 9.00 | 37.75 | -11.24 | -3.67 | 0.48 | 0.23 | -311.53 | 0.11 | 4.10 | -0.40 | 0.00 |
| orb_exits_v1-026 | orb15 leve tpB/0.05% rr2.5 ta 15:25 | 1895 | 92.35 | 145 | 11.00 | 43.52 | -13.00 | -3.98 | 0.55 | 0.28 | -602.70 | 0.16 | 3.86 | -0.44 | 0.00 |
| orb_exits_v1-175 | orb60 leve tpnone tr:be15 tc 15:25 | 1197 | 30.24 | 835 | 2.30 | 366.80 | -17.04 | -4.02 | 0.68 | 0.38 | -4605.08 | 0.08 | - | -0.20 | 0.00 |
| orb_exits_v1-085 | orb60 leve tpB/0.05% rr2 tc 15:25 | 1197 | 90.64 | 112 | 16.10 | 36.51 | -11.82 | -4.05 | 0.59 | 0.34 | -478.96 | 0.03 | 3.53 | -0.41 | 0.00 |
| orb_exits_v1-056 | orb30 leve tpB/0.05% rr2.5 ta 15:25 | 1613 | 92.87 | 115 | 8.70 | 34.70 | -11.94 | -4.46 | 0.40 | 0.19 | -546.00 | 0.07 | 4.06 | -0.49 | 0.00 |
| orb_exits_v1-119 | orb15 leve tpnone tr:be15 tc 15:25 | 1895 | 20.37 | 1509 | 3.30 | 287.34 | -20.57 | -4.54 | 0.68 | 0.38 | -6857.21 | 0.08 | - | -0.16 | 0.00 |
| orb_exits_v1-002 | orb30 prem tpnone tb 15:25 | 1613 | 9.98 | 1452 | 7.20 | 275.04 | -26.36 | -4.56 | 0.81 | 0.58 | -7816.20 | 0.06 | - | -0.11 | 0.00 |
| orb_exits_v1-168 | orb60 leve tpnone tr:be6 ta 15:25 | 1197 | 30.24 | 835 | 1.30 | 410.66 | -15.67 | -4.65 | 0.54 | 0.27 | -4441.34 | 0.07 | - | -0.21 | 0.00 |
| orb_exits_v1-169 | orb60 leve tpnone tr:be6 tc 15:25 | 1197 | 30.24 | 835 | 1.30 | 410.66 | -15.67 | -4.65 | 0.54 | 0.27 | -4441.34 | 0.07 | - | -0.21 | 0.00 |
| orb_exits_v1-057 | orb30 leve tpB/0.05% rr2.5 tc 15:25 | 1613 | 92.87 | 115 | 16.50 | 34.09 | -12.36 | -4.69 | 0.55 | 0.32 | -572.69 | 0.04 | 4.06 | -0.50 | 0.00 |
| orb_exits_v1-185 | orb60 leve tpnone tr:hl1m tc 15:25 | 1197 | 30.24 | 835 | 14.10 | 66.34 | -16.38 | -4.69 | 0.67 | 0.35 | -4007.21 | 0.07 | - | -0.25 | 0.00 |
| orb_exits_v1-084 | orb60 leve tpB/0.05% rr2 ta 15:25 | 1197 | 90.64 | 112 | 8.90 | 36.37 | -12.37 | -4.71 | 0.41 | 0.20 | -552.16 | -0.03 | 3.53 | -0.44 | 0.00 |
| orb_exits_v1-024 | orb15 leve tpB/0.05% rr2 ta 15:25 | 1895 | 89.13 | 206 | 12.60 | 38.27 | -14.28 | -4.74 | 0.51 | 0.26 | -1148.03 | 0.08 | 3.38 | -0.44 | 0.00 |
| orb_exits_v1-058 | orb30 leve tpB/0.05% rr3 ta 15:25 | 1613 | 94.73 | 85 | 7.10 | 32.02 | -10.79 | -4.85 | 0.32 | 0.16 | -418.06 | -0.06 | 4.52 | -0.55 | 0.00 |
| orb_exits_v1-184 | orb60 leve tpnone tr:hl1m ta 15:25 | 1197 | 30.24 | 835 | 7.70 | 84.31 | -16.62 | -4.85 | 0.57 | 0.27 | -4046.97 | 0.08 | - | -0.25 | 0.00 |
| orb_exits_v1-083 | orb60 leve tpB/0.05% rr1.5 tc 15:25 | 1197 | 86.97 | 156 | 17.90 | 33.74 | -13.38 | -4.92 | 0.55 | 0.31 | -822.69 | 0.01 | 3.02 | -0.46 | 0.00 |
| orb_exits_v1-028 | orb15 leve tpB/0.05% rr3 ta 15:25 | 1895 | 94.72 | 100 | 9.00 | 41.45 | -12.21 | -4.94 | 0.43 | 0.23 | -531.14 | 0.10 | 4.35 | -0.58 | 0.00 |
| orb_exits_v1-116 | orb15 leve tpnone tr:be10 ta 15:25 | 1895 | 20.37 | 1509 | 2.60 | 312.35 | -20.20 | -4.95 | 0.62 | 0.34 | -7470.48 | 0.08 | - | -0.17 | 0.00 |
| orb_exits_v1-117 | orb15 leve tpnone tr:be10 tc 15:25 | 1895 | 20.37 | 1509 | 2.60 | 312.35 | -20.20 | -4.95 | 0.62 | 0.34 | -7470.48 | 0.08 | - | -0.17 | 0.00 |
| orb_exits_v1-118 | orb15 leve tpnone tr:be15 ta 15:25 | 1895 | 20.37 | 1509 | 2.60 | 312.35 | -20.20 | -4.95 | 0.62 | 0.34 | -7470.48 | 0.08 | - | -0.17 | 0.00 |
| orb_exits_v1-059 | orb30 leve tpB/0.05% rr3 tc 15:25 | 1613 | 94.73 | 85 | 14.10 | 33.04 | -11.28 | -5.02 | 0.48 | 0.29 | -447.98 | -0.07 | 4.52 | -0.57 | 0.00 |
| orb_exits_v1-187 | orb60 leve tpnone tr:hl5m tc 15:25 | 1197 | 30.24 | 835 | 9.70 | 109.22 | -17.30 | -5.03 | 0.68 | 0.39 | -5565.67 | 0.04 | - | -0.27 | 0.00 |
| orb_exits_v1-001 | orb15 prem tpnone tb 15:25 | 1895 | 8.13 | 1741 | 7.20 | 285.79 | -27.75 | -5.06 | 0.80 | 0.57 | -9058.89 | 0.03 | - | -0.14 | 0.00 |
| orb_exits_v1-186 | orb60 leve tpnone tr:hl5m ta 15:25 | 1197 | 30.24 | 835 | 4.70 | 133.18 | -16.67 | -5.10 | 0.55 | 0.27 | -4798.08 | 0.05 | - | -0.27 | 0.00 |
| orb_exits_v1-022 | orb15 leve tpB/0.05% rr1.5 ta 15:25 | 1895 | 84.38 | 296 | 15.20 | 34.84 | -16.07 | -5.13 | 0.51 | 0.26 | -1717.78 | 0.11 | 2.87 | -0.42 | 0.00 |
| orb_exits_v1-149 | orb30 leve tpnone tr:belevel tc 15:25 | 1613 | 25.67 | 1199 | 2.60 | 283.99 | -18.40 | -5.35 | 0.58 | 0.32 | -6411.28 | 0.12 | 0.35 | -0.37 | 0.00 |
| orb_exits_v1-114 | orb15 leve tpnone tr:be8 ta 15:25 | 1895 | 20.37 | 1509 | 2.30 | 320.83 | -19.93 | -5.36 | 0.57 | 0.30 | -8082.82 | 0.07 | - | -0.19 | 0.00 |
| orb_exits_v1-115 | orb15 leve tpnone tr:be8 tc 15:25 | 1895 | 20.37 | 1509 | 2.30 | 320.83 | -19.93 | -5.36 | 0.57 | 0.30 | -8082.82 | 0.07 | - | -0.19 | 0.00 |
| orb_exits_v1-121 | orb15 leve tpnone tr:belevel tc 15:25 | 1895 | 20.37 | 1509 | 2.30 | 306.93 | -18.90 | -5.40 | 0.56 | 0.29 | -8146.20 | 0.07 | 0.32 | -0.30 | 0.00 |
| orb_exits_v1-013 | orb15 leve tpB/$0.03 rr1.5 tc 15:25 | 1895 | 90.45 | 181 | 22.10 | 30.47 | -15.71 | -5.50 | 0.55 | 0.31 | -1147.72 | 0.04 | 2.57 | -0.49 | 0.00 |
| orb_exits_v1-147 | orb30 leve tpnone tr:be15 tc 15:25 | 1613 | 25.67 | 1199 | 3.20 | 270.35 | -19.83 | -5.58 | 0.61 | 0.35 | -6685.29 | 0.09 | - | -0.21 | 0.00 |
| orb_exits_v1-194 | orb60 leve tpnone tr:gb50 ta 15:25 | 1197 | 30.24 | 835 | 33.40 | 8.47 | -12.72 | -5.63 | 0.34 | 0.06 | -4710.05 | 0.08 | - | -0.24 | 0.00 |
| orb_exits_v1-195 | orb60 leve tpnone tr:gb50 tc 15:25 | 1197 | 30.24 | 835 | 33.40 | 8.47 | -12.72 | -5.63 | 0.34 | 0.06 | -4710.05 | 0.08 | - | -0.24 | 0.00 |
| orb_exits_v1-082 | orb60 leve tpB/0.05% rr1.5 ta 15:25 | 1197 | 86.97 | 156 | 10.30 | 31.83 | -13.79 | -5.66 | 0.37 | 0.18 | -913.15 | -0.06 | 3.02 | -0.50 | 0.00 |
| orb_exits_v1-066 | orb30 leve tpB/0.1atr rr2.5 ta 15:25 | 1613 | 96.28 | 60 | 6.70 | 40.91 | -13.62 | -5.67 | 0.33 | 0.16 | -393.68 | -0.13 | 3.85 | -0.54 | 0.00 |
| orb_exits_v1-192 | orb60 leve tpnone tr:gb40 ta 15:25 | 1197 | 30.24 | 835 | 33.40 | 8.33 | -12.72 | -5.67 | 0.33 | 0.06 | -4752.00 | 0.08 | - | -0.25 | 0.00 |
| orb_exits_v1-193 | orb60 leve tpnone tr:gb40 tc 15:25 | 1197 | 30.24 | 835 | 33.40 | 8.33 | -12.72 | -5.67 | 0.33 | 0.06 | -4752.00 | 0.08 | - | -0.25 | 0.00 |
| orb_exits_v1-046 | orb30 leve tpB/$0.03 rr2.5 ta 15:25 | 1613 | 96.22 | 61 | 8.20 | 32.95 | -13.49 | -5.71 | 0.32 | 0.15 | -401.26 | -0.14 | 3.90 | -0.55 | 0.00 |
| orb_exits_v1-068 | orb30 leve tpB/0.1atr rr3 ta 15:25 | 1613 | 97.58 | 39 | 5.10 | 40.25 | -12.20 | -5.76 | 0.26 | 0.13 | -277.68 | -0.20 | 4.44 | -0.57 | 0.00 |
| orb_exits_v1-044 | orb30 leve tpB/$0.03 rr2 ta 15:25 | 1613 | 94.23 | 93 | 8.60 | 39.93 | -14.67 | -5.87 | 0.37 | 0.18 | -587.03 | -0.07 | 3.32 | -0.53 | 0.00 |
| orb_exits_v1-074 | orb60 leve tpB/$0.03 rr2 ta 15:25 | 1197 | 94.40 | 67 | 6.00 | 41.89 | -13.17 | -5.95 | 0.30 | 0.14 | -424.66 | -0.09 | 3.68 | -0.58 | 0.00 |
| orb_exits_v1-190 | orb60 leve tpnone tr:gb30 ta 15:25 | 1197 | 30.24 | 835 | 33.40 | 7.46 | -12.72 | -5.96 | 0.29 | 0.04 | -4993.67 | 0.05 | - | -0.26 | 0.00 |
| orb_exits_v1-191 | orb60 leve tpnone tr:gb30 tc 15:25 | 1197 | 30.24 | 835 | 33.40 | 7.46 | -12.72 | -5.96 | 0.29 | 0.04 | -4993.67 | 0.05 | - | -0.26 | 0.00 |
| orb_exits_v1-027 | orb15 leve tpB/0.05% rr2.5 tc 15:25 | 1895 | 92.35 | 145 | 13.80 | 42.15 | -13.69 | -5.98 | 0.49 | 0.29 | -892.98 | -0.02 | 3.86 | -0.63 | 0.00 |
| orb_exits_v1-012 | orb15 leve tpB/$0.03 rr1.5 ta 15:25 | 1895 | 90.45 | 181 | 13.30 | 30.83 | -15.72 | -5.99 | 0.41 | 0.20 | -1169.11 | -0.00 | 2.57 | -0.49 | 0.00 |
| orb_exits_v1-120 | orb15 leve tpnone tr:belevel ta 15:25 | 1895 | 20.37 | 1509 | 1.70 | 333.39 | -18.86 | -5.99 | 0.49 | 0.25 | -9044.21 | 0.05 | 0.32 | -0.34 | 0.00 |
| orb_exits_v1-008 | orb60 prem tpA ta 15:25 | 1197 | 13.53 | 1035 | 21.50 | 24.40 | -18.05 | -6.01 | 0.47 | 0.23 | -6243.18 | -0.01 | - | -0.28 | 0.00 |
| orb_exits_v1-009 | orb60 prem tpA ta 15:50 | 1197 | 13.53 | 1035 | 21.50 | 24.40 | -18.05 | -6.01 | 0.47 | 0.23 | -6243.18 | -0.01 | - | -0.28 | 0.00 |
| orb_exits_v1-148 | orb30 leve tpnone tr:belevel ta 15:25 | 1613 | 25.67 | 1199 | 1.90 | 310.54 | -18.44 | -6.01 | 0.50 | 0.26 | -7205.38 | 0.10 | 0.35 | -0.39 | 0.00 |
| orb_exits_v1-090 | orb60 leve tpB/0.1atr ta 15:25 | 1197 | 30.24 | 835 | 28.60 | 11.12 | -13.79 | -6.08 | 0.34 | 0.12 | -5093.97 | 0.03 | 0.38 | -0.43 | 0.00 |
| orb_exits_v1-091 | orb60 leve tpB/0.1atr tc 15:25 | 1197 | 30.24 | 835 | 30.30 | 11.51 | -13.79 | -6.12 | 0.36 | 0.14 | -5127.87 | 0.03 | 0.38 | -0.44 | 0.00 |
| orb_exits_v1-025 | orb15 leve tpB/0.05% rr2 tc 15:25 | 1895 | 89.13 | 206 | 16.50 | 37.08 | -14.71 | -6.16 | 0.50 | 0.29 | -1385.15 | -0.04 | 3.38 | -0.57 | 0.00 |
| orb_exits_v1-048 | orb30 leve tpB/$0.03 rr3 ta 15:25 | 1613 | 97.46 | 41 | 7.30 | 27.21 | -12.37 | -6.16 | 0.24 | 0.12 | -305.62 | -0.21 | 4.46 | -0.61 | 0.00 |
| orb_exits_v1-070 | orb60 leve tpB/$0.03 ta 15:25 | 1197 | 30.24 | 835 | 28.40 | 10.98 | -13.89 | -6.23 | 0.33 | 0.12 | -5236.10 | 0.01 | 0.38 | -0.43 | 0.00 |
| orb_exits_v1-032 | orb15 leve tpB/0.1atr rr1.5 ta 15:25 | 1895 | 90.34 | 183 | 12.00 | 30.88 | -15.49 | -6.27 | 0.37 | 0.19 | -1212.21 | -0.05 | 2.60 | -0.50 | 0.00 |
| orb_exits_v1-081 | orb60 leve tpB/0.05% tc 15:25 | 1197 | 30.24 | 835 | 29.10 | 14.05 | -14.62 | -6.28 | 0.39 | 0.17 | -5269.30 | -0.01 | 0.69 | -0.45 | 0.00 |
| orb_exits_v1-142 | orb30 leve tpnone tr:be8 ta 15:25 | 1613 | 25.67 | 1199 | 2.10 | 306.78 | -19.23 | -6.30 | 0.50 | 0.28 | -7557.22 | 0.09 | - | -0.24 | 0.00 |
| orb_exits_v1-143 | orb30 leve tpnone tr:be8 tc 15:25 | 1613 | 25.67 | 1199 | 2.10 | 306.78 | -19.23 | -6.30 | 0.50 | 0.28 | -7557.22 | 0.09 | - | -0.24 | 0.00 |
| orb_exits_v1-144 | orb30 leve tpnone tr:be10 ta 15:25 | 1613 | 25.67 | 1199 | 2.30 | 291.23 | -19.54 | -6.32 | 0.52 | 0.29 | -7577.95 | 0.08 | - | -0.24 | 0.00 |
| orb_exits_v1-146 | orb30 leve tpnone tr:be15 ta 15:25 | 1613 | 25.67 | 1199 | 2.30 | 291.23 | -19.54 | -6.32 | 0.52 | 0.29 | -7577.95 | 0.08 | - | -0.24 | 0.00 |
| orb_exits_v1-145 | orb30 leve tpnone tr:be10 tc 15:25 | 1613 | 25.67 | 1199 | 2.30 | 291.23 | -19.54 | -6.33 | 0.52 | 0.29 | -7594.80 | 0.08 | - | -0.24 | 0.00 |
| orb_exits_v1-071 | orb60 leve tpB/$0.03 tc 15:25 | 1197 | 30.24 | 835 | 30.10 | 11.42 | -13.99 | -6.35 | 0.35 | 0.14 | -5335.24 | -0.00 | 0.38 | -0.44 | 0.00 |
| orb_exits_v1-018 | orb15 leve tpB/$0.03 rr3 ta 15:25 | 1895 | 97.68 | 44 | 6.80 | 48.01 | -13.69 | -6.37 | 0.34 | 0.19 | -306.39 | -0.16 | 4.39 | -0.65 | 0.00 |
| orb_exits_v1-023 | orb15 leve tpB/0.05% rr1.5 tc 15:25 | 1895 | 84.38 | 296 | 19.90 | 32.60 | -16.08 | -6.37 | 0.51 | 0.29 | -2053.33 | 0.01 | 2.87 | -0.52 | 0.00 |
| orb_exits_v1-054 | orb30 leve tpB/0.05% rr2 ta 15:25 | 1613 | 89.89 | 163 | 8.00 | 36.04 | -13.97 | -6.38 | 0.31 | 0.16 | -1073.38 | -0.03 | 3.52 | -0.58 | 0.00 |
| orb_exits_v1-080 | orb60 leve tpB/0.05% ta 15:25 | 1197 | 30.24 | 835 | 26.60 | 12.86 | -14.61 | -6.40 | 0.35 | 0.13 | -5369.40 | -0.02 | 0.69 | -0.46 | 0.00 |
| orb_exits_v1-129 | orb15 leve tpnone tr:hl1m tc 15:25 | 1895 | 20.37 | 1509 | 16.00 | 62.80 | -19.64 | -6.42 | 0.61 | 0.32 | -10157.88 | 0.03 | - | -0.22 | 0.00 |
| orb_exits_v1-029 | orb15 leve tpB/0.05% rr3 tc 15:25 | 1895 | 94.72 | 100 | 11.00 | 42.75 | -12.51 | -6.43 | 0.42 | 0.25 | -680.72 | -0.06 | 4.35 | -0.77 | 0.00 |
| orb_exits_v1-055 | orb30 leve tpB/0.05% rr2 tc 15:25 | 1613 | 89.89 | 163 | 15.30 | 34.92 | -13.92 | -6.43 | 0.46 | 0.27 | -1081.21 | -0.03 | 3.52 | -0.59 | 0.00 |
| orb_exits_v1-004 | orb15 prem tpA ta 15:25 | 1895 | 8.07 | 1742 | 24.70 | 26.52 | -22.08 | -6.51 | 0.50 | 0.25 | -11395.79 | 0.02 | - | -0.24 | 0.00 |
| orb_exits_v1-005 | orb15 prem tpA ta 15:50 | 1895 | 8.07 | 1742 | 24.70 | 26.52 | -22.08 | -6.51 | 0.50 | 0.25 | -11395.79 | 0.02 | - | -0.24 | 0.00 |
| orb_exits_v1-106 | orb15 leve tpE/$0.03 ta 15:25 | 1895 | 20.37 | 1509 | 14.30 | 39.49 | -18.42 | -6.53 | 0.46 | 0.23 | -9855.31 | 0.04 | 0.32 | -0.37 | 0.00 |
| orb_exits_v1-105 | orb60 leve tpC/$0.03 tc 15:25 | 1197 | 30.24 | 835 | 26.10 | 14.65 | -14.04 | -6.55 | 0.37 | 0.13 | -5481.78 | -0.02 | 0.38 | -0.45 | 0.00 |
| orb_exits_v1-180 | orb60 leve tpnone tr:L2 ta 15:25 | 1197 | 30.24 | 835 | 23.50 | 20.26 | -16.75 | -6.56 | 0.42 | 0.15 | -5473.65 | -0.01 | - | -0.26 | 0.00 |
| orb_exits_v1-033 | orb15 leve tpB/0.1atr rr1.5 tc 15:25 | 1895 | 90.34 | 183 | 20.80 | 29.09 | -15.91 | -6.57 | 0.48 | 0.28 | -1317.33 | -0.06 | 2.60 | -0.54 | 0.00 |
| orb_exits_v1-038 | orb15 leve tpB/0.1atr rr3 ta 15:25 | 1895 | 97.52 | 47 | 6.40 | 48.01 | -13.72 | -6.57 | 0.32 | 0.17 | -323.89 | -0.17 | 4.39 | -0.67 | 0.00 |
| orb_exits_v1-104 | orb60 leve tpC/$0.03 ta 15:25 | 1197 | 30.24 | 835 | 26.10 | 12.64 | -14.15 | -6.60 | 0.33 | 0.11 | -5526.49 | -0.03 | 0.38 | -0.45 | 0.00 |
| orb_exits_v1-112 | orb15 leve tpnone tr:be6 ta 15:25 | 1895 | 20.37 | 1509 | 2.00 | 268.69 | -19.65 | -6.77 | 0.44 | 0.23 | -10215.70 | 0.02 | - | -0.23 | 0.00 |
| orb_exits_v1-113 | orb15 leve tpnone tr:be6 tc 15:25 | 1895 | 20.37 | 1509 | 2.00 | 268.69 | -19.65 | -6.77 | 0.44 | 0.23 | -10215.70 | 0.02 | - | -0.23 | 0.00 |
| orb_exits_v1-020 | orb15 leve tpB/0.05% ta 15:25 | 1895 | 20.37 | 1509 | 28.60 | 16.02 | -17.44 | -6.78 | 0.40 | 0.17 | -10437.82 | 0.04 | 0.71 | -0.40 | 0.00 |
| orb_exits_v1-014 | orb15 leve tpB/$0.03 rr2 ta 15:25 | 1895 | 94.83 | 98 | 9.20 | 37.98 | -15.52 | -6.81 | 0.34 | 0.18 | -732.14 | -0.11 | 3.29 | -0.59 | 0.00 |
| orb_exits_v1-011 | orb15 leve tpB/$0.03 tc 15:25 | 1895 | 20.37 | 1509 | 32.30 | 13.79 | -16.69 | -6.82 | 0.40 | 0.16 | -10546.43 | 0.03 | 0.32 | -0.40 | 0.00 |
| orb_exits_v1-122 | orb15 leve tpnone tr:L1 ta 15:25 | 1895 | 20.37 | 1509 | 21.60 | 28.38 | -20.34 | -6.87 | 0.47 | 0.17 | -10457.93 | 0.02 | - | -0.24 | 0.00 |
| orb_exits_v1-042 | orb30 leve tpB/$0.03 rr1.5 ta 15:25 | 1613 | 90.39 | 155 | 10.30 | 34.77 | -15.75 | -6.88 | 0.34 | 0.17 | -1066.06 | -0.12 | 2.69 | -0.57 | 0.00 |
| orb_exits_v1-136 | orb15 leve tpnone tr:gb40 ta 15:25 | 1895 | 20.37 | 1509 | 33.30 | 9.82 | -15.30 | -6.90 | 0.32 | 0.06 | -10524.01 | 0.03 | - | -0.25 | 0.00 |
| orb_exits_v1-137 | orb15 leve tpnone tr:gb40 tc 15:25 | 1895 | 20.37 | 1509 | 33.30 | 9.82 | -15.30 | -6.90 | 0.32 | 0.06 | -10524.01 | 0.03 | - | -0.25 | 0.00 |
| orb_exits_v1-107 | orb15 leve tpE/$0.03 tc 15:25 | 1895 | 20.37 | 1509 | 19.20 | 43.52 | -18.91 | -6.93 | 0.55 | 0.32 | -10660.05 | 0.01 | 0.32 | -0.40 | 0.00 |
| orb_exits_v1-138 | orb15 leve tpnone tr:gb50 ta 15:25 | 1895 | 20.37 | 1509 | 33.30 | 9.72 | -15.30 | -6.93 | 0.32 | 0.06 | -10548.05 | 0.03 | - | -0.25 | 0.00 |
| orb_exits_v1-139 | orb15 leve tpnone tr:gb50 tc 15:25 | 1895 | 20.37 | 1509 | 33.30 | 9.72 | -15.30 | -6.93 | 0.32 | 0.06 | -10548.05 | 0.03 | - | -0.25 | 0.00 |
| orb_exits_v1-181 | orb60 leve tpnone tr:L2 tc 15:25 | 1197 | 30.24 | 835 | 28.00 | 19.37 | -17.17 | -6.93 | 0.44 | 0.16 | -5784.69 | -0.03 | - | -0.27 | 0.00 |
| orb_exits_v1-110 | orb60 leve tpE/$0.03 ta 15:25 | 1197 | 30.24 | 835 | 15.60 | 22.18 | -15.15 | -6.96 | 0.33 | 0.15 | -5811.23 | -0.06 | 0.38 | -0.48 | 0.00 |
| orb_exits_v1-076 | orb60 leve tpB/$0.03 rr2.5 ta 15:25 | 1197 | 95.57 | 53 | 5.70 | 30.14 | -13.14 | -6.97 | 0.20 | 0.10 | -369.62 | -0.23 | 4.06 | -0.64 | 0.00 |
| orb_exits_v1-010 | orb15 leve tpB/$0.03 ta 15:25 | 1895 | 20.37 | 1509 | 30.40 | 13.11 | -16.70 | -6.98 | 0.36 | 0.14 | -10745.60 | 0.01 | 0.32 | -0.41 | 0.00 |
| orb_exits_v1-183 | orb60 leve tpnone tr:L3 tc 15:25 | 1197 | 30.24 | 835 | 20.80 | 31.73 | -17.17 | -6.98 | 0.49 | 0.20 | -5828.75 | -0.03 | - | -0.27 | 0.00 |
| orb_exits_v1-134 | orb15 leve tpnone tr:gb30 ta 15:25 | 1895 | 20.37 | 1509 | 33.30 | 9.50 | -15.30 | -7.00 | 0.31 | 0.05 | -10708.13 | 0.02 | - | -0.25 | 0.00 |
| orb_exits_v1-135 | orb15 leve tpnone tr:gb30 tc 15:25 | 1895 | 20.37 | 1509 | 33.30 | 9.50 | -15.30 | -7.00 | 0.31 | 0.05 | -10708.13 | 0.02 | - | -0.25 | 0.00 |
| orb_exits_v1-064 | orb30 leve tpB/0.1atr rr2 ta 15:25 | 1613 | 94.54 | 88 | 5.70 | 44.13 | -14.96 | -7.01 | 0.26 | 0.13 | -624.70 | -0.20 | 3.33 | -0.62 | 0.00 |
| orb_exits_v1-031 | orb15 leve tpB/0.1atr tc 15:25 | 1895 | 20.37 | 1509 | 31.90 | 13.70 | -16.80 | -7.03 | 0.38 | 0.16 | -10854.37 | 0.02 | 0.33 | -0.42 | 0.00 |
| orb_exits_v1-101 | orb15 leve tpC/$0.03 tc 15:25 | 1895 | 20.37 | 1509 | 28.80 | 17.26 | -16.87 | -7.03 | 0.41 | 0.16 | -10816.65 | -0.00 | 0.32 | -0.40 | 0.00 |
| orb_exits_v1-131 | orb15 leve tpnone tr:hl5m tc 15:25 | 1895 | 20.37 | 1509 | 10.30 | 115.92 | -21.11 | -7.03 | 0.63 | 0.37 | -10612.05 | 0.01 | - | -0.23 | 0.00 |
| orb_exits_v1-111 | orb60 leve tpE/$0.03 tc 15:25 | 1197 | 30.24 | 835 | 18.80 | 29.41 | -15.48 | -7.04 | 0.44 | 0.24 | -5877.16 | -0.05 | 0.38 | -0.51 | 0.00 |
| orb_exits_v1-133 | orb15 leve tpnone tr:lvl tc 15:25 | 1895 | 20.37 | 1509 | 23.50 | 28.91 | -18.10 | -7.07 | 0.49 | 0.19 | -10880.21 | 0.01 | - | -0.24 | 0.00 |
| orb_exits_v1-072 | orb60 leve tpB/$0.03 rr1.5 ta 15:25 | 1197 | 90.64 | 112 | 8.90 | 30.13 | -14.79 | -7.08 | 0.28 | 0.14 | -832.98 | -0.07 | 2.90 | -0.64 | 0.00 |
| orb_exits_v1-021 | orb15 leve tpB/0.05% tc 15:25 | 1895 | 20.37 | 1509 | 30.70 | 16.42 | -17.52 | -7.09 | 0.41 | 0.18 | -10908.46 | 0.00 | 0.71 | -0.42 | 0.00 |
| orb_exits_v1-182 | orb60 leve tpnone tr:L3 ta 15:25 | 1197 | 30.24 | 835 | 13.10 | 32.27 | -16.75 | -7.10 | 0.37 | 0.14 | -5927.92 | -0.04 | - | -0.28 | 0.00 |
| orb_exits_v1-030 | orb15 leve tpB/0.1atr ta 15:25 | 1895 | 20.37 | 1509 | 29.90 | 13.07 | -16.73 | -7.12 | 0.35 | 0.14 | -10949.52 | 0.01 | 0.33 | -0.42 | 0.00 |
| orb_exits_v1-098 | orb60 leve tpB/0.1atr rr3 ta 15:25 | 1197 | 97.08 | 35 | 5.70 | 35.32 | -12.80 | -7.12 | 0.22 | 0.12 | -249.29 | -0.20 | 4.71 | -0.70 | 0.00 |
| orb_exits_v1-052 | orb30 leve tpB/0.05% rr1.5 ta 15:25 | 1613 | 86.17 | 223 | 10.30 | 32.12 | -15.65 | -7.15 | 0.32 | 0.16 | -1627.04 | -0.04 | 3.04 | -0.58 | 0.00 |
| orb_exits_v1-188 | orb60 leve tpnone tr:lvl ta 15:25 | 1197 | 30.24 | 835 | 12.80 | 28.69 | -15.72 | -7.15 | 0.34 | 0.12 | -6051.96 | -0.06 | - | -0.30 | 0.00 |
| orb_exits_v1-126 | orb15 leve tpnone tr:L3 ta 15:25 | 1895 | 20.37 | 1509 | 16.80 | 34.84 | -20.32 | -7.16 | 0.45 | 0.17 | -10863.60 | 0.00 | - | -0.24 | 0.00 |
| orb_exits_v1-189 | orb60 leve tpnone tr:lvl tc 15:25 | 1197 | 30.24 | 835 | 19.40 | 25.37 | -15.00 | -7.17 | 0.41 | 0.16 | -6020.08 | -0.05 | - | -0.30 | 0.00 |
| orb_exits_v1-178 | orb60 leve tpnone tr:L1 ta 15:25 | 1197 | 30.24 | 835 | 17.00 | 24.29 | -16.75 | -7.18 | 0.36 | 0.12 | -5995.61 | -0.06 | - | -0.28 | 0.00 |
| orb_exits_v1-100 | orb15 leve tpC/$0.03 ta 15:25 | 1895 | 20.37 | 1509 | 29.30 | 15.09 | -17.26 | -7.19 | 0.38 | 0.13 | -10964.41 | -0.01 | 0.32 | -0.41 | 0.00 |
| orb_exits_v1-078 | orb60 leve tpB/$0.03 rr3 ta 15:25 | 1197 | 96.83 | 38 | 5.30 | 35.32 | -13.26 | -7.21 | 0.20 | 0.11 | -274.10 | -0.23 | 4.59 | -0.69 | 0.00 |
| orb_exits_v1-123 | orb15 leve tpnone tr:L1 tc 15:25 | 1895 | 20.37 | 1509 | 28.10 | 27.73 | -20.92 | -7.25 | 0.52 | 0.20 | -11178.23 | -0.00 | - | -0.24 | 0.00 |
| orb_exits_v1-128 | orb15 leve tpnone tr:hl1m ta 15:25 | 1895 | 20.37 | 1509 | 8.70 | 65.53 | -20.27 | -7.26 | 0.44 | 0.20 | -10954.27 | -0.00 | - | -0.24 | 0.00 |
| orb_exits_v1-130 | orb15 leve tpnone tr:hl5m ta 15:25 | 1895 | 20.37 | 1509 | 4.60 | 122.72 | -20.24 | -7.32 | 0.44 | 0.21 | -11039.22 | -0.00 | - | -0.25 | 0.00 |
| orb_exits_v1-140 | orb30 leve tpnone tr:be6 ta 15:25 | 1613 | 25.67 | 1199 | 1.90 | 255.74 | -18.93 | -7.33 | 0.40 | 0.21 | -8791.30 | 0.04 | - | -0.26 | 0.00 |
| orb_exits_v1-141 | orb30 leve tpnone tr:be6 tc 15:25 | 1613 | 25.67 | 1199 | 1.90 | 255.74 | -18.93 | -7.33 | 0.40 | 0.21 | -8791.30 | 0.04 | - | -0.26 | 0.00 |
| orb_exits_v1-043 | orb30 leve tpB/$0.03 rr1.5 tc 15:25 | 1613 | 90.39 | 155 | 16.80 | 34.08 | -15.71 | -7.36 | 0.44 | 0.25 | -1206.19 | -0.14 | 2.69 | -0.64 | 0.00 |
| orb_exits_v1-124 | orb15 leve tpnone tr:L2 ta 15:25 | 1895 | 20.37 | 1509 | 27.40 | 20.37 | -20.36 | -7.43 | 0.43 | 0.14 | -11269.58 | -0.01 | - | -0.25 | 0.00 |
| orb_exits_v1-127 | orb15 leve tpnone tr:L3 tc 15:25 | 1895 | 20.37 | 1509 | 24.50 | 34.17 | -20.89 | -7.43 | 0.53 | 0.23 | -11445.18 | -0.01 | - | -0.24 | 0.00 |
| orb_exits_v1-094 | orb60 leve tpB/0.1atr rr2 ta 15:25 | 1197 | 94.49 | 66 | 6.10 | 25.45 | -13.81 | -7.45 | 0.17 | 0.08 | -502.56 | -0.28 | 3.69 | -0.67 | 0.00 |
| orb_exits_v1-132 | orb15 leve tpnone tr:lvl ta 15:25 | 1895 | 20.37 | 1509 | 16.70 | 30.91 | -19.29 | -7.48 | 0.41 | 0.15 | -11339.73 | -0.01 | - | -0.26 | 0.00 |
| orb_exits_v1-096 | orb60 leve tpB/0.1atr rr2.5 ta 15:25 | 1197 | 95.66 | 52 | 3.80 | 35.32 | -13.14 | -7.49 | 0.15 | 0.08 | -389.40 | -0.30 | 4.08 | -0.69 | 0.00 |
| orb_exits_v1-125 | orb15 leve tpnone tr:L2 tc 15:25 | 1895 | 20.37 | 1509 | 32.30 | 20.32 | -20.74 | -7.49 | 0.47 | 0.17 | -11418.51 | -0.01 | - | -0.25 | 0.00 |
| orb_exits_v1-053 | orb30 leve tpB/0.05% rr1.5 tc 15:25 | 1613 | 86.17 | 223 | 17.00 | 30.75 | -15.40 | -7.54 | 0.41 | 0.24 | -1718.04 | -0.07 | 3.04 | -0.61 | 0.00 |
| orb_exits_v1-179 | orb60 leve tpnone tr:L1 tc 15:25 | 1197 | 30.24 | 835 | 23.00 | 24.20 | -17.09 | -7.60 | 0.42 | 0.15 | -6343.61 | -0.07 | - | -0.29 | 0.00 |
| orb_exits_v1-075 | orb60 leve tpB/$0.03 rr2 tc 15:25 | 1197 | 94.40 | 67 | 10.40 | 34.95 | -12.60 | -7.63 | 0.32 | 0.18 | -519.60 | -0.23 | 3.68 | -0.75 | 0.00 |
| orb_exits_v1-040 | orb30 leve tpB/$0.03 ta 15:25 | 1613 | 25.67 | 1199 | 26.90 | 13.24 | -16.26 | -7.66 | 0.32 | 0.13 | -9371.49 | 0.06 | 0.35 | -0.45 | 0.00 |
| orb_exits_v1-062 | orb30 leve tpB/0.1atr rr1.5 ta 15:25 | 1613 | 90.64 | 151 | 7.90 | 40.37 | -16.08 | -7.66 | 0.29 | 0.15 | -1155.99 | -0.19 | 2.68 | -0.61 | 0.00 |
| orb_exits_v1-041 | orb30 leve tpB/$0.03 tc 15:25 | 1613 | 25.67 | 1199 | 28.40 | 13.90 | -16.21 | -7.67 | 0.34 | 0.14 | -9433.49 | 0.05 | 0.35 | -0.46 | 0.00 |
| orb_exits_v1-036 | orb15 leve tpB/0.1atr rr2.5 ta 15:25 | 1895 | 96.57 | 65 | 7.70 | 36.26 | -15.20 | -7.73 | 0.27 | 0.14 | -517.52 | -0.20 | 3.93 | -0.71 | 0.00 |
| orb_exits_v1-006 | orb30 prem tpA ta 15:25 | 1613 | 9.98 | 1452 | 22.40 | 24.82 | -21.66 | -7.75 | 0.42 | 0.21 | -11339.72 | -0.01 | - | -0.29 | 0.00 |
| orb_exits_v1-007 | orb30 prem tpA ta 15:50 | 1613 | 9.98 | 1452 | 22.40 | 24.82 | -21.66 | -7.75 | 0.42 | 0.21 | -11339.72 | -0.01 | - | -0.29 | 0.00 |
| orb_exits_v1-045 | orb30 leve tpB/$0.03 rr2 tc 15:25 | 1613 | 94.23 | 93 | 12.90 | 39.98 | -14.83 | -7.76 | 0.40 | 0.23 | -802.20 | -0.22 | 3.32 | -0.71 | 0.00 |
| orb_exits_v1-060 | orb30 leve tpB/0.1atr ta 15:25 | 1613 | 25.67 | 1199 | 26.00 | 13.49 | -16.31 | -7.82 | 0.31 | 0.13 | -9543.20 | 0.04 | 0.34 | -0.46 | 0.00 |
| orb_exits_v1-158 | orb30 leve tpnone tr:hl5m ta 15:25 | 1613 | 25.67 | 1199 | 4.70 | 112.39 | -19.60 | -7.86 | 0.40 | 0.20 | -9505.71 | 0.02 | - | -0.29 | 0.00 |
| orb_exits_v1-061 | orb30 leve tpB/0.1atr tc 15:25 | 1613 | 25.67 | 1199 | 27.60 | 14.18 | -16.28 | -7.87 | 0.33 | 0.14 | -9651.77 | 0.04 | 0.34 | -0.47 | 0.00 |
| orb_exits_v1-092 | orb60 leve tpB/0.1atr rr1.5 ta 15:25 | 1197 | 90.64 | 112 | 7.10 | 34.32 | -15.28 | -7.91 | 0.24 | 0.12 | -886.41 | -0.14 | 2.89 | -0.70 | 0.00 |
| orb_exits_v1-162 | orb30 leve tpnone tr:gb30 ta 15:25 | 1613 | 25.67 | 1199 | 31.20 | 8.85 | -15.54 | -7.92 | 0.26 | 0.04 | -9726.14 | 0.04 | - | -0.29 | 0.00 |
| orb_exits_v1-163 | orb30 leve tpnone tr:gb30 tc 15:25 | 1613 | 25.67 | 1199 | 31.20 | 8.85 | -15.54 | -7.92 | 0.26 | 0.04 | -9726.14 | 0.04 | - | -0.29 | 0.00 |
| orb_exits_v1-050 | orb30 leve tpB/0.05% ta 15:25 | 1613 | 25.67 | 1199 | 24.70 | 15.37 | -17.12 | -7.93 | 0.32 | 0.14 | -9578.17 | 0.01 | 0.71 | -0.48 | 0.00 |
| orb_exits_v1-073 | orb60 leve tpB/$0.03 rr1.5 tc 15:25 | 1197 | 90.64 | 112 | 15.20 | 27.36 | -14.27 | -7.95 | 0.34 | 0.20 | -930.91 | -0.15 | 2.90 | -0.72 | 0.00 |
| orb_exits_v1-157 | orb30 leve tpnone tr:hl1m tc 15:25 | 1613 | 25.67 | 1199 | 14.50 | 56.26 | -18.88 | -7.97 | 0.51 | 0.26 | -9872.84 | 0.01 | - | -0.28 | 0.00 |
| orb_exits_v1-164 | orb30 leve tpnone tr:gb40 ta 15:25 | 1613 | 25.67 | 1199 | 31.20 | 8.67 | -15.54 | -7.98 | 0.25 | 0.04 | -9756.41 | 0.03 | - | -0.29 | 0.00 |
| orb_exits_v1-165 | orb30 leve tpnone tr:gb40 tc 15:25 | 1613 | 25.67 | 1199 | 31.20 | 8.67 | -15.54 | -7.98 | 0.25 | 0.04 | -9756.41 | 0.03 | - | -0.29 | 0.00 |
| orb_exits_v1-156 | orb30 leve tpnone tr:hl1m ta 15:25 | 1613 | 25.67 | 1199 | 8.70 | 58.92 | -19.62 | -8.00 | 0.39 | 0.18 | -9703.33 | 0.01 | - | -0.28 | 0.00 |
| orb_exits_v1-034 | orb15 leve tpB/0.1atr rr2 ta 15:25 | 1895 | 94.78 | 99 | 7.10 | 34.89 | -15.81 | -8.07 | 0.23 | 0.12 | -814.00 | -0.21 | 3.34 | -0.68 | 0.00 |
| orb_exits_v1-159 | orb30 leve tpnone tr:hl5m tc 15:25 | 1613 | 25.67 | 1199 | 9.40 | 104.64 | -19.80 | -8.07 | 0.55 | 0.32 | -9734.84 | 0.01 | - | -0.27 | 0.00 |
| orb_exits_v1-016 | orb15 leve tpB/$0.03 rr2.5 ta 15:25 | 1895 | 96.78 | 61 | 6.60 | 40.31 | -15.24 | -8.10 | 0.25 | 0.14 | -520.04 | -0.24 | 3.93 | -0.73 | 0.00 |
| orb_exits_v1-051 | orb30 leve tpB/0.05% tc 15:25 | 1613 | 25.67 | 1199 | 26.80 | 16.24 | -17.03 | -8.11 | 0.35 | 0.16 | -9781.96 | -0.01 | 0.71 | -0.49 | 0.00 |
| orb_exits_v1-166 | orb30 leve tpnone tr:gb50 ta 15:25 | 1613 | 25.67 | 1199 | 31.20 | 8.09 | -15.54 | -8.16 | 0.24 | 0.04 | -9954.45 | 0.01 | - | -0.30 | 0.00 |
| orb_exits_v1-167 | orb30 leve tpnone tr:gb50 tc 15:25 | 1613 | 25.67 | 1199 | 31.20 | 8.09 | -15.54 | -8.16 | 0.24 | 0.04 | -9954.45 | 0.01 | - | -0.30 | 0.00 |
| orb_exits_v1-108 | orb30 leve tpE/$0.03 ta 15:25 | 1613 | 25.67 | 1199 | 13.20 | 32.16 | -18.12 | -8.18 | 0.34 | 0.17 | -9841.62 | -0.01 | 0.35 | -0.47 | 0.00 |
| orb_exits_v1-063 | orb30 leve tpB/0.1atr rr1.5 tc 15:25 | 1613 | 90.64 | 151 | 14.60 | 37.16 | -16.03 | -8.28 | 0.40 | 0.23 | -1311.38 | -0.22 | 2.68 | -0.70 | 0.00 |
| orb_exits_v1-015 | orb15 leve tpB/$0.03 rr2 tc 15:25 | 1895 | 94.83 | 98 | 15.30 | 31.91 | -15.60 | -8.33 | 0.37 | 0.22 | -865.98 | -0.23 | 3.29 | -0.74 | 0.00 |
| orb_exits_v1-102 | orb30 leve tpC/$0.03 ta 15:25 | 1613 | 25.67 | 1199 | 26.40 | 13.14 | -17.04 | -8.42 | 0.29 | 0.10 | -10306.82 | -0.03 | 0.35 | -0.49 | 0.00 |
| orb_exits_v1-150 | orb30 leve tpnone tr:L1 ta 15:25 | 1613 | 25.67 | 1199 | 19.00 | 24.56 | -19.71 | -8.43 | 0.36 | 0.12 | -10156.18 | -0.01 | - | -0.30 | 0.00 |
| orb_exits_v1-103 | orb30 leve tpC/$0.03 tc 15:25 | 1613 | 25.67 | 1199 | 25.60 | 15.27 | -16.60 | -8.44 | 0.32 | 0.12 | -10415.93 | -0.03 | 0.35 | -0.50 | 0.00 |
| orb_exits_v1-049 | orb30 leve tpB/$0.03 rr3 tc 15:25 | 1613 | 97.46 | 41 | 9.80 | 29.69 | -12.60 | -8.47 | 0.26 | 0.15 | -423.75 | -0.42 | 4.46 | -0.84 | 0.00 |
| orb_exits_v1-154 | orb30 leve tpnone tr:L3 ta 15:25 | 1613 | 25.67 | 1199 | 15.30 | 29.01 | -19.69 | -8.65 | 0.34 | 0.13 | -10506.26 | -0.03 | - | -0.31 | 0.00 |
| orb_exits_v1-109 | orb30 leve tpE/$0.03 tc 15:25 | 1613 | 25.67 | 1199 | 17.20 | 37.69 | -18.31 | -8.69 | 0.43 | 0.25 | -10494.77 | -0.04 | 0.35 | -0.51 | 0.00 |
| orb_exits_v1-069 | orb30 leve tpB/0.1atr rr3 tc 15:25 | 1613 | 97.58 | 39 | 7.70 | 42.15 | -12.94 | -8.70 | 0.27 | 0.16 | -424.70 | -0.45 | 4.44 | -0.86 | 0.00 |
| orb_exits_v1-093 | orb60 leve tpB/0.1atr rr1.5 tc 15:25 | 1197 | 90.64 | 112 | 13.40 | 29.22 | -14.65 | -8.77 | 0.31 | 0.18 | -998.36 | -0.22 | 2.89 | -0.79 | 0.00 |
| orb_exits_v1-160 | orb30 leve tpnone tr:lvl ta 15:25 | 1613 | 25.67 | 1199 | 14.90 | 27.12 | -19.04 | -8.78 | 0.32 | 0.12 | -10770.45 | -0.04 | - | -0.31 | 0.00 |
| orb_exits_v1-161 | orb30 leve tpnone tr:lvl tc 15:25 | 1613 | 25.67 | 1199 | 21.00 | 25.36 | -17.88 | -8.79 | 0.38 | 0.15 | -10905.27 | -0.04 | - | -0.32 | 0.00 |
| orb_exits_v1-079 | orb60 leve tpB/$0.03 rr3 tc 15:25 | 1197 | 96.83 | 38 | 7.90 | 34.62 | -12.57 | -8.84 | 0.24 | 0.14 | -336.02 | -0.36 | 4.59 | -0.87 | 0.00 |
| orb_exits_v1-151 | orb30 leve tpnone tr:L1 tc 15:25 | 1613 | 25.67 | 1199 | 25.50 | 23.75 | -20.06 | -8.88 | 0.41 | 0.15 | -10822.33 | -0.04 | - | -0.32 | 0.00 |
| orb_exits_v1-095 | orb60 leve tpB/0.1atr rr2 tc 15:25 | 1197 | 94.49 | 66 | 10.60 | 25.56 | -13.05 | -8.96 | 0.23 | 0.13 | -601.78 | -0.41 | 3.69 | -0.82 | 0.00 |
| orb_exits_v1-155 | orb30 leve tpnone tr:L3 tc 15:25 | 1613 | 25.67 | 1199 | 22.80 | 28.18 | -19.98 | -9.02 | 0.42 | 0.17 | -11120.24 | -0.04 | - | -0.32 | 0.00 |
| orb_exits_v1-077 | orb60 leve tpB/$0.03 rr2.5 tc 15:25 | 1197 | 95.57 | 53 | 7.50 | 30.91 | -12.39 | -9.12 | 0.20 | 0.12 | -483.23 | -0.42 | 4.06 | -0.86 | 0.00 |
| orb_exits_v1-047 | orb30 leve tpB/$0.03 rr2.5 tc 15:25 | 1613 | 96.22 | 61 | 9.80 | 33.65 | -13.91 | -9.23 | 0.26 | 0.15 | -639.48 | -0.43 | 3.90 | -0.86 | 0.00 |
| orb_exits_v1-065 | orb30 leve tpB/0.1atr rr2 tc 15:25 | 1613 | 94.54 | 88 | 10.20 | 43.31 | -15.21 | -9.23 | 0.32 | 0.19 | -881.21 | -0.36 | 3.33 | -0.83 | 0.00 |
| orb_exits_v1-153 | orb30 leve tpnone tr:L2 tc 15:25 | 1613 | 25.67 | 1199 | 29.40 | 16.56 | -20.02 | -9.25 | 0.34 | 0.11 | -11202.91 | -0.06 | - | -0.33 | 0.00 |
| orb_exits_v1-152 | orb30 leve tpnone tr:L2 ta 15:25 | 1613 | 25.67 | 1199 | 24.40 | 15.79 | -19.73 | -9.26 | 0.29 | 0.09 | -11159.73 | -0.07 | - | -0.33 | 0.00 |
| orb_exits_v1-097 | orb60 leve tpB/0.1atr rr2.5 tc 15:25 | 1197 | 95.66 | 52 | 7.70 | 26.14 | -12.37 | -9.41 | 0.18 | 0.10 | -489.15 | -0.48 | 4.08 | -0.89 | 0.00 |
| orb_exits_v1-099 | orb60 leve tpB/0.1atr rr3 tc 15:25 | 1197 | 97.08 | 35 | 5.70 | 35.32 | -12.18 | -9.46 | 0.18 | 0.10 | -331.27 | -0.45 | 4.71 | -0.92 | 0.00 |
| orb_exits_v1-067 | orb30 leve tpB/0.1atr rr2.5 tc 15:25 | 1613 | 96.28 | 60 | 8.30 | 41.92 | -14.27 | -9.59 | 0.27 | 0.16 | -660.79 | -0.45 | 3.85 | -0.89 | 0.00 |
| orb_exits_v1-019 | orb15 leve tpB/$0.03 rr3 tc 15:25 | 1895 | 97.68 | 44 | 6.80 | 48.01 | -13.95 | -9.73 | 0.25 | 0.16 | -454.23 | -0.48 | 4.39 | -0.98 | 0.00 |
| orb_exits_v1-035 | orb15 leve tpB/0.1atr rr2 tc 15:25 | 1895 | 94.78 | 99 | 13.10 | 29.31 | -15.86 | -9.93 | 0.28 | 0.16 | -1003.13 | -0.36 | 3.34 | -0.87 | 0.00 |
| orb_exits_v1-039 | orb15 leve tpB/0.1atr rr3 tc 15:25 | 1895 | 97.52 | 47 | 6.40 | 48.01 | -14.31 | -10.33 | 0.23 | 0.14 | -500.62 | -0.54 | 4.39 | -1.03 | 0.00 |
| orb_exits_v1-037 | orb15 leve tpB/0.1atr rr2.5 tc 15:25 | 1895 | 96.57 | 65 | 9.20 | 36.64 | -15.33 | -10.53 | 0.24 | 0.15 | -699.76 | -0.45 | 3.93 | -0.99 | 0.00 |
| orb_exits_v1-017 | orb15 leve tpB/$0.03 rr2.5 tc 15:25 | 1895 | 96.78 | 61 | 8.20 | 39.96 | -15.13 | -10.61 | 0.24 | 0.14 | -673.39 | -0.46 | 3.93 | -0.99 | 0.00 |


Run log rows appended to `/home/box/sprint/data/sprint/runs_grok-bot-vm-510907181.csv`; every trade in `/home/box/sprint/data/sprint/trades_orb_exits_v1_2026-10-31.csv.gz`.

Labels: BACKTEST (in-sample on DEV). Spread: MODELED-SPREAD. Delta: BS-EST. Not financial advice: evidence for Nick to decide.
