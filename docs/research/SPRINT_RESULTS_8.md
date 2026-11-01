# Sprint results 8: round 8, steady rules, a sharper big-day filter, indicators and levels (Chart's computer, 2026-11-01)

Pre-registered in SPRINT_PLAN Amendment 10 and Addenda 10.1-10.3 (commits `0fc8fd1`, `d75e28b`, `e2d1369`, `e2cc2d6`) before any round-8 code or run. Code `aa2baa8`; 243 sprint tests passed on Chart's computer. Reports: `docs/research/sprint_reports/2026-11-01_run8/`. 18 engine runs were added to `sprint_runs.csv` (1,801 rows). Round 8 counts 192 trials; deflated Sharpe N = 3,679, and every variant's deflated Sharpe is 0.0.

**Labels:** every number is a BACKTEST.
- Shares: real stock bars 2016-01 to 2026-06 (never L1/L2), $10,000 notional a trade, $0.01 a share each way.
- Options: MODELED 2016 to Jan 2024; REAL Aug 2024 to Jun 2026. Next-expiry MODELED tapes use the 0DTE calibration as a fallback (NOT VALIDATED).

## Verdicts

| part | what | verdict | key numbers |
|---|---|---|---|
| A1 | noise band in shares (`noise_sh`, primary) | fail | 7,005 trades, +$1.39 a trade (1.4 bps), 5 of 8 years, 60/120 months green; beats random direction (p 0.000) |
| A1 | same, vol-sized (paper's sizing; **secondary, information only**) | fail (only the steadiness item) | 6,985 trades, +$4.24 a trade, 6 of 8 years + DEV positive, CI above 0, positive without the best 5 days, p 0.000; **65/120 months green (bar 55% = 66)**; daily correlation with FIN-H 0.005 HIST / 0.238 DEV |
| A2 | last-half-hour momentum (`last30`) | fail | 7,461 trades, +$0.05 a trade; 2x costs negative; DEV -$3,541 |
| A3 | stressed-day gap fade, shares | fail | 486 trades, -$3.91 a trade, 3 of 8 years; 2020 -$8,347 |
| A3 | gap fade on options (DEV-only bar) | PASS on its bar, **but not credible** | 0DTE d55: 113 trades, PF 1.91; next expiry: 89 trades, PF 1.71. The same rule lost on 10 years of shares and on MODELED 2016-2023 options (PF 0.93 / 0.81) |
| A-opt | noise band carried by options | fail | PF 0.887 (0DTE) / 0.752 (next expiry) |
| B2 | confidence sizing (skip / 1 / 2 contracts) | **PASS, all three sleeves** | per contract, sized vs flat: 11:00 MODELED $12.66 vs $6.85, REAL $25.15 vs $13.22; 10:30 $17.36 / $17.72 vs $8.98 / $7.81; 12:00 $9.92 / $21.32 vs $4.38 / $11.21; Sharpe up in every window |
| B3 | wait for proof (`newhigh_c`) | PASS | HIST 807 trades PF 1.66; DEV 203 trades PF 2.55. On common days: lower win rate than FIN-H (10% vs 21% HIST), similar average loss; DEV total without the best day -$113 |
| B4 | FIN-H with exits that sell early, 0DTE and next expiry | no variant steadier; only FIN-H's own exit passes | gb50 trail PF 0.12-0.21; +100% target PF 0.36-0.83. -50% stop: REAL PF 2.94 but MODELED 1.22 (fail). Next expiry, FIN-H exit: REAL PF 3.03, MODELED 1.22 (fail, NOT VALIDATED) |
| D | RSI, Bollinger, EMA 9/21, MACD, level + RSI, trend pullback, in shares | all fail | expectancy -$1.71 to +$0.17 a trade; level + RSI did no better than made-up levels (-$0.90 vs -$0.89 to -$1.01) |
| D | the same in options, with the 12-cell stop/target grid chosen on 2016-2019 | all fail both holdouts | chosen cells were mostly the widest stop (-50%); none passed 2020-2023 or DEV |

## The book (as pre-registered) is one bet stacked six times

- Sleeves: FIN-H, B4 b4_d03_i (identical to FIN-H, so FIN-H is counted twice), the three B2 sized sleeves (FIN-H's family) and B3.
- Daily correlation on DEV: 0.98-1.00.
- Totals:
  - 2018 to Jan 2024 MODELED: +$83,937, max DD -$4,019, 39/73 months green;
  - DEV REAL: +$51,339, max DD -$7,652, 8/23 months green;
  - mixed: +$135,275.
- These totals are mostly position size on the same days, not diversification.
- On real prices, FIN-H alone made +$6,413 and +$57.82 without 2025-04-09 (run 7). The sized sleeves put 2 contracts on the days the model likes most, so they share that dependence. Their per-day P/L isn't in run 8's files, so their total without that day isn't measured here.

## What this means

- **Steady money:** no simple rule in shares or options made steady money over 10 years. That covers:
  - the noise band in shares, last-half-hour momentum and the gap fade;
  - four textbook indicators;
  - indicators combined with support/resistance levels or a trend filter;
  - a tuned stop.
  Support/resistance levels added nothing over made-up levels.
- **The closest to steady** is the noise band in shares at the paper's own volatility sizing, and it was a secondary (information) variant:
  - it passes 6 of 7 items and misses the steadiness bar by one month (65 vs 66 of 120);
  - it wins on different days than FIN-H (correlation about 0).
  It is a candidate for its own pre-registered confirmation (the untouched locked months), not a pass.
- **The big-day family:**
  - confidence sizing works in both windows: the walk-forward model ranks days well enough to roughly double P/L per contract;
  - wait-for-proof passes but is the same bet with a lower win rate;
  - selling early destroys it, as runs 2-3 suggested;
  - next-expiry contracts look good on real prices but rest on an unvalidated model for 2016-2023.
- **Gap fade on options:** a DEV-only pass that 10 years of shares and the MODELED years contradict. Treated as period luck: run 4's lesson.
- **Nothing is promoted.** L1/L2 remain untouched. The next clean test is a frozen locked-period exam of FIN-H, FIN-H with confidence sizing, and the vol-sized noise band in shares (a new amendment, written before any L1/L2 pull).
