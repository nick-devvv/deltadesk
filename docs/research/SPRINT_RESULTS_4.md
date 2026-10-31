# Sprint results, run 4: the free 2016-2023 history check (Chart's computer, 2026-10-31)

Code `cf13f19`, 177 sprint tests passed on Chart's computer. Pre-registered in SPRINT_PLAN Amendment 5 (commit `1d889ce`) before any pull or run. Reports: `docs/research/sprint_reports/2026-10-31_run4/`. 18 runs added to `docs/research/sprint_runs.csv` (1,741 rows; 3,361 trials counted).

**Data:** Alpaca 1-minute stock bars for SPY, QQQ, IWM and VIXY, 2015-11 to 2024-01. That's 2,033 sessions in HIST (2016-01-04 to 2024-01-31), split-adjusted, 118 MB. No option prices exist for these years. L1 and L2 were never pulled.

## Layer 1: the signal on the stock alone (BACKTEST, real stock bars, no option model)

| idea | result | pre-registered reading |
|---|---|---|
| fb (failed-break, all levels) | 3,157 trades, +0.02R, PF 1.01; positive in 5 of 8 years; random entries -0.21 to -0.33R | **NO** (needed 6 of 8 years) |
| fb_or (opening-range lows) | 2,006 trades, +0.08R, PF 1.07; positive in 4 of 8 years (2016, 2020, 2022, 2023); random entries -0.13 to -0.27R | **NO** |
| otm_put (calm up days, 10:30) | large-drop rate 5.74% on 1,236 days vs 5.41% on all days; p = 0.35; above the yearly rate in 3 of 8 years | **NO**: the filter doesn't pick days with more big drops |
| otm_bounce (high-VIX down days, 11:00) | large-rise rate 7.87% on 216 days vs 3.77% on all days; p = 0.018; filtered days only in 2018, 2019 and 2020 | **YES** (stock signal only) |

The failed-break signal beats random entries at the stock level, but the edge is small and switches sign from year to year.

## Layer 2: option P/L, MODELED (Black-Scholes, one IV per day = 20-session realized vol x a multiplier fitted on the real 2024-2026 option trades)

**Validation on DEV** (modeled vs real option prices, same rules):
- **Pass:** fb (PF 1.61 vs real 1.47), fb_or (1.91 vs 1.79), otm_put base (0.98 vs 0.87), otm_put (1.88 vs 1.66), otm_bounce base (1.33 vs 1.01).
- **Fail:** otm_bounce (modeled 6.29 vs real 10.34, ratio 0.61). Its HIST numbers are UNRELIABLE.
- The model runs slightly optimistic for the passing strategies.

**HIST 2016-2023:**

| strategy | trades | exp $ | PF | PF 2x | without best 5 | reading |
|---|---|---|---|---|---|---|
| fb | 1,901 | -2.31 | 0.84 | 0.59 | -8,063 | does not hold |
| fb_or (paper ledger `fb_or`) | 1,235 | -2.13 | 0.86 | 0.60 | -5,862 | does not hold |
| otm_put base | 4,731 | -3.26 | 0.71 | 0.64 | -18,391 | does not hold |
| otm_put (paper ledger `otm_put`) | 988 | -1.33 | 0.88 | 0.78 | -3,875 | does not hold |
| otm_bounce base | 5,445 | +0.94 | 1.18 | 0.97 | +1,764 | does not hold (PF 2x < 1) |
| otm_bounce (paper ledger `otm_bounce`) | 211 | +7.19 | 2.02 | 1.75 | -154 | UNRELIABLE (model failed validation) |

- **otm_bounce on HIST:** it trades only in 2018, 2019 and 2020. 2019 lost; 2020 made $1,266. It beat 60% of random-entry paths, and the filter vs random day-skips gave p = 0.084.
- **5% stress:** same readings.
- **Mon/Wed/Fri vs Tue/Thu** (before Nov 2022 not every weekday had a 0DTE expiry): no reading changes.

## What this means

- Neither of the two main paper ledgers holds up on eight years they were never tuned on. `fb_or` and `otm_put` lose money there with modeled options, and their stock-level signals are weak or absent.
- The 2024-2026 results were most likely fitted to that period: the failed-break calls' profits came from strong up days in a bull market.
- `otm_bounce` is the only idea whose stock signal held on 2016-2023, but it fires only in high-volatility stretches (2018, 2020, April 2025). Its option result can't be confirmed with this model.
- The paper ledgers keep running (paper costs nothing and gives real-fill data), labeled as having failed the 2016-2023 check. Nothing is promoted, and L1/L2 stay locked.
- **Next research step (proposal):** use HIST as the discovery set, with eight years and several regimes of real stock bars and validated modeled options. Then confirm on DEV's real option prices, and use L1/L2 last. That reverses the order that let a two-year bull market drive this sprint.
