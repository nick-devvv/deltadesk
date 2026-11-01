# Sprint results 7: the 10-year strategy factory (Chart's computer, 2026-10-31)

Pre-registered in SPRINT_PLAN Amendment 9 (commit `da61e34`) before any factory code or run. Code `5568c2e`; 194 sprint tests passed on Chart's computer. Reports: `docs/research/sprint_reports/2026-10-31_run7/` (`factory_2026-10-31.md` has one section per strategy with every year). 42 runs added to `docs/research/sprint_runs.csv` (1,783 rows); the deflated Sharpe counts 3,742 trials.

**Labels:** every number is a BACKTEST, 1 contract per signal, 2% half-spread ($0.005 floor), $0.65 per contract per side.
- HIST 2016-01 to 2024-01: real stock bars, option prices **MODELED** (BS, one calibrated IV per day).
- DEV 2024-08 to 2026-06: **REAL** Alpaca option prices.
- L1 and L2 were never pulled or run.

## 1. Each strategy

Rules were found on 2016-2019 only. Holdout 1 = 2020 to Jan 2024 (MODELED); holdout 2 = DEV (REAL).

| # | strategy | HIST MODELED n / PF / $ | DEV REAL n / PF / $ | rule | H1 | H2 | verdict |
|---|---|---|---|---|---|---|---|
| 1 | noise | 7,056 / 0.85 / -19,791 | 2,064 / 0.78 / -14,976 | VIXY pctl top | fail | | none |
| 2-4 | orb15 / 30 / 60 | PF 0.78 / 0.64 / 0.59 | PF 0.80 / 0.81 / 0.88 | gap / range / rvol top | fail | | none |
| 5 | vwap_macd | 1,869 / 0.68 / -7,566 | 594 / 0.89 / -1,333 | VIXY pctl top | fail | | none |
| 6 | pd_retest | 381 / 0.64 / -1,557 | 106 / 0.33 / -1,474 | gap top | fail | | none |
| 7 | flush | 2,567 / 0.52 / -14,120 | 876 / 0.65 / -6,122 | range top | fail | | none |
| 8 | failed_break (seen before) | 1,901 / 0.84 / -4,398 | 676 / 1.47 / +7,401 | gap top | fail | | none |
| 9 | failed_high | 2,307 / 0.63 / -13,898 | 872 / 0.60 / -8,398 | gap bottom | fail | | none |
| 10 | otm_c_1000 | 5,438 / 1.31 / +9,478 | 1,410 / 0.65 / -5,176 | rvol >= 1.06 | PASS | fail | none |
| 11 | **otm_c_1030** | 5,484 / 1.30 / +9,146 | 1,423 / 0.76 / -3,218 | rvol >= 1.06 | PASS | PASS | **rule** |
| 12 | **otm_c_1100** (seen before) | 5,445 / 1.18 / +5,142 | 1,418 / 1.01 / +107 | rvol >= 1.06 | PASS | PASS | **rule** |
| 13 | **otm_c_1200** | 5,471 / 0.95 / -1,373 | 1,387 / 1.03 / +349 | rvol >= 1.06 | PASS | PASS | **rule** |
| 14 | **otm_c_1300** | 5,416 / 0.91 / -2,134 | 1,367 / 1.10 / +911 | rvol >= 1.06 | PASS | PASS | **learner: buckets** |
| 15 | otm_c_1400 | 5,347 / 0.93 / -1,244 | 1,349 / 0.44 / -4,273 | rvol >= 1.06 | PASS | fail | none |
| 16-21 | otm puts 10:00-14:00 | PF 0.65-0.87, all losing | PF 0.56-0.87, all losing | rvol / range / VIXY top | fail | | none |

- **Every stock setup failed** (ORB, VWAP-MACD, PD retest, flush, failed-break, failed-high), and so did the noise reference. No learner model survived for any of them.
- **Every far-OTM put failed holdout 1.**
- **Far-OTM calls:** the same rule was chosen at all six times: relative volume >= 1.06, "only on busy days". It passed holdout 1 at every time. On real prices it passed at 10:30, 11:00, 12:00 and 13:00 and failed at 10:00 and 14:00.
- **Learners:** a logit also survived at 11:00, 12:00 and 13:00, and buckets at 13:00. The pre-registered choice is the highest DEV expectancy, so the rule wins at 11:00 and 12:00 and buckets wins at 13:00.
- Deflated Sharpe of every chosen variant on DEV: 0.0 (information only).

## 2. The four survivors on their test years

| sleeve | holdout 1 (2020 to Jan 2024, MODELED) | holdout 2 (DEV, REAL) | DEV without best 5 trades |
|---|---|---|---|
| otm_c_1030 rule | 1,075 trades, PF 2.57, +$10,678 | 479 trades, PF 1.72, PF 2x 1.54, +$3,740 (p 0.012) | -$2,261 |
| otm_c_1100 rule (= FIN-H) | 1,099 trades, PF 2.35, +$8,768 | 485 trades, PF 2.35, PF 2x 2.10, +$6,413 (p 0.0045) | -$1,083 |
| otm_c_1200 rule | 1,049 trades, PF 1.96, +$5,662 | 487 trades, PF 2.28, PF 2x 2.01, +$5,457 (p 0.017) | -$1,675 |
| otm_c_1300 buckets | walk-forward picks, OOS from 2018: 312 HIST trades, PF 1.07, +$130 | 256 trades, PF 3.50, PF 2x 3.01, +$4,248 | not in report |

## 3. The book: all four together (1 contract per signal per sleeve)

| window | trades | per session | total $ | per year $ | max DD $ | months green | Sharpe |
|---|---|---|---|---|---|---|---|
| 2018 to Jan 2024, MODELED | 4,771 | 3.12 | +30,230 | +4,979 | -2,589 | 39/73 | 1.41 |
| Aug 2024 to Jun 2026, REAL | 1,707 | 3.56 | +19,858 | +10,447 | -4,598 | 7/23 | 0.62 |
| mixed (labeled) | 6,478 | 3.22 | +50,088 | +6,283 | -4,598 | 46/96 | 0.72 |
| contrast: all 21 unfiltered, mixed | 97,975 | 48.8 | -225,942 | -28,341 | -245,113 | 24/96 | -1.24 |

| year | prices | total $ | max DD $ | months green |
|---|---|---|---|---|
| 2018 (in-sample for the rules) | MODELED | +4,613 | -372 | 9/12 |
| 2019 (in-sample for the rules) | MODELED | +380 | -505 | 4/12 |
| 2020 | MODELED | +7,747 | -1,018 | 7/12 |
| 2021 | MODELED | +5,054 | -571 | 8/12 |
| 2022 | MODELED | +9,331 | -2,589 | 5/12 |
| 2023 | MODELED | +2,684 | -842 | 5/12 |
| Jan 2024 | MODELED | +421 | -168 | 1/1 |
| Aug-Dec 2024 | REAL | +815 | -1,656 | 1/5 |
| 2025 | REAL | +17,870 | -3,417 | 3/12 |
| Jan-Jun 2026 | REAL | +1,172 | -1,211 | 3/6 |

The $150 desk daily stop never triggered: losing days are small.

## 4. Follow-up checks (after the results, not pre-registered: information only)

Computed from run 7's trade files with the factory's own code (`sprint/factory.run_strategy` rebuilds the same sleeves; the book totals match the report exactly).

- **One day carries the real-price book.** On 2025-04-09 (the tariff-pause rally) the book made +$22,737, more than its whole DEV total.
  - Without that day the book lost -$2,879 on DEV. Without all of April 2025 it lost -$1,518, with 6 of 22 months green.
  - Without its best 5 days it lost -$10,324 on DEV. On the MODELED years it stays positive without its best 5 days (+$15,986 of +$30,230).
  - FIN-H alone (11:00 rule) made +$6,413 on DEV, and +$58 without 2025-04-09.
- **Big days per year** (book day P/L of $500 or more):

| year | prices | days >= $500 | their $ | days >= $2,000 | all other days $ |
|---|---|---|---|---|---|
| 2018 | MODELED | 4 | +4,792 | 0 | -179 |
| 2019 | MODELED | 1 | +915 | 0 | -535 |
| 2020 | MODELED | 7 | +8,878 | 1 | -1,131 |
| 2021 | MODELED | 6 | +6,586 | 1 | -1,532 |
| 2022 | MODELED | 9 | +14,599 | 3 | -5,268 |
| 2023 | MODELED | 3 | +3,937 | 0 | -1,253 |
| Aug-Dec 2024 | REAL | 1 | +3,020 | 1 | -2,204 |
| 2025 | REAL | 3 | +24,657 | 1 | -6,787 |
| Jan-Jun 2026 | REAL | 3 | +4,000 | 0 | -2,828 |

- **The four sleeves are one bet.**
  - Their daily P/L correlation on DEV is 0.95-0.99, set by 2025-04-09. Without April 2025 it is 0.04-0.87.
  - On 2025-04-09 every sleeve won between $4,949 and $6,356.
  - Four contracts of FIN-H alone would have made more on DEV: +$25,653, max DD -$5,113, Sharpe 0.70, against the book's +$19,858, -$4,598, 0.62.
  - On the MODELED years the book is a little smoother: Sharpe 1.41 against FIN-H's 1.27.
  - So adding sleeves here mostly means a bigger position in the same idea, not more edge.
- **The stock moves weren't rarer in 2024-2026.** Share of FIN-H trades whose stock ran at least +1% above entry (real stock bars):
  - REAL years: 8.5% in Aug-Dec 2024, 17.8% in 2025, 12.2% in 2026.
  - MODELED years: 0.9% to 34.3% (2017 lowest, 2020 highest).
  - 2025 was an ordinary year for moves. Run 4 already found the model optimistic for 11:00 far-OTM calls (modeled PF 1.33 against real 1.01), so the MODELED years likely overstate the real payoff.
- **Sensitivity (in-sample choice, information only):** using the 13:00 rule instead of buckets gives +$20,727 on DEV and +$34,923 on 2018 to Jan 2024 MODELED.

## 5. What this means

- **Ten years of history found one idea, not several:** buy far-OTM 0DTE calls (delta 0.03-0.12) on busy days (relative volume >= 1.06), at any time from 10:30 to 13:00, with a -95% stop, holding to 15:25.
  - Nothing else in the codebase holds up across years: no stock setup, no put, not the noise band.
- **The combined book was green in every year from 2018 to mid-2026**, but it is a lottery-ticket shape:
  - most months lose a little (7 of 23 green on real prices);
  - a few violent up days pay for everything;
  - each real-price period was carried by 1 to 3 days.
- **Combining the four is not diversification.** They win and lose on the same days, like trading more contracts of FIN-H.
- **Status:** nothing is promoted and L1/L2 stay locked.
  - The finalists' locked-period exam (FIN-H, FIN-L, and FIN-HL from Amendment 8) is the next clean test.
  - For this shape, one short window can be won or lost by a single day, so 40 forward paper trades (CLAUDE.md step 5) matter as much as the exam.
