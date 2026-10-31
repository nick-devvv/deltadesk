# Option Alpha 0DTE backtester: pre-registered SPY runs

Source: Option Alpha web backtester (app.optionalpha.com/backtests), Nick's free trial, run 2026-10-31 (UTC).
All numbers below are copied exactly as the tool displayed them. Label: **backtest, pre-registered list, nothing tuned or re-run for better results; fills MODELED by Option Alpha** (see Notes). Only one window (the last 12 months) was available, so there is no held-out period.

## Summary of all runs (as displayed; P/L and drawdown exclude fees)

"a" = trial maximum window (1Y, 2025-10-30 to 2026-10-30). "b" = same window with 2025-10-30 and 2025-10-31 excluded (= 2025-11-01 to 2026-10-30).

| Run | Strategy | Trades | Win rate | Profit factor | Total P/L | Max DD | Avg win / avg loss | Est. fees (not in P/L) |
|---|---|---|---|---|---|---|---|---|
| T1a | Long call .50d, ORB60 above | 115 | 42.6% | 1.44 | $2,008 | -$648 | $134 / -$69 | $9.20 |
| T1b | same, 2025-11-01 start | 115 | 42.6% | 1.44 | $2,008 | -$648 | $134 / -$69 | $9.20 |
| T2a | Long put -.50d, ORB60 below | 96 | 26.0% | 0.73 | -$1,582 | -$1,953 | $173 / -$83 | $7.68 |
| T2b | same, 2025-11-01 start | 95 | 25.3% | 0.7 | -$1,749 | -$1,953 | $173 / -$83 | $7.60 |
| T3a | Long call .50d, ORB30 above | 133 | 36.8% | 0.99 | -$85 | -$995 | $136 / -$80 | $10.64 |
| T3b | same, 2025-11-01 start | 132 | 37.1% | 1.0 | $9 | -$995 | $136 / -$80 | $10.56 |
| T4a | Long put -.50d, ORB30 below | 110 | 30.0% | 0.85 | -$1,035 | -$1,152 | $175 / -$88 | $8.80 |
| T4b | same, 2025-11-01 start | 109 | 30.3% | 0.86 | -$930 | -$1,152 | $175 / -$88 | $8.72 |
| T5a | Long call .50d, ORB15 above | 129 | 34.1% | 0.93 | -$488 | -$1,063 | $159 / -$88 | $10.32 |
| T5b | same, 2025-11-01 start | 128 | 34.4% | 0.95 | -$360 | -$1,063 | $159 / -$87 | $10.24 |
| T6a | Long put -.50d, ORB15 below | 120 | 29.2% | 0.77 | -$1,791 | -$2,544 | $170 / -$91 | $9.60 |
| T6b | same, 2025-11-01 start | 119 | 29.4% | 0.78 | -$1,694 | -$2,544 | $170 / -$91 | $9.52 |
| T7a | Short put spread (short at/below OR low, $2 wide), ORB60 above | 114 | 76.3% | 0.61 | -$646 | -$746 | $11 / -$63 | $16 |
| T7b | not run: identical to T7a (no Oct-2025 trades) | 114 | 76.3% | 0.61 | -$646 | -$746 | $11 / -$63 | $16 |
| T8a | Short call spread (short at/above OR high, $2 wide), ORB60 below | 96 | 75.0% | 0.63 | -$614 | -$667 | $14 / -$71 | $13.20 |
| T8b | same, 2025-11-01 start | 95 | 74.7% | 0.62 | -$617 | -$667 | $14 / -$71 | $13.04 |
| T9a | Iron condor .20d shorts, $2 wings, 10:00 entry, stop -200% of credit, skip FOMC | 237 | 68.4% | 0.98 | -$125 | -$1,323 | $37 / -$84 | $61.44 |
| T9b | same, 2025-11-01 start | 235 | 68.1% | 0.97 | -$171 | -$1,323 | $38 / -$84 | $60.80 |

17 backtests were run and saved in "My Backtests" (T7b was not run, see its section). No backtest-count limit was hit.

## Notes

### Deviations from the pre-registered list
1. **Period (all tests):** the trial shows "Backtests are limited to 1 year during a free trial". Custom dates (2013-01-01 to 2026-10-30, and 2025-11-01 to 2026-10-30) were entered but the server saved every test with period = "1y" and ignored the dates. So (a) "longest history" was not available (paid feature, skipped); every "a" run is the trial's 1-year window, which starts 2025-10-30 (first session in the result data) and runs to the last session before 2026-10-31. Custom dates allow back to 2013-01-01 on paid plans (form text: "Backtest SPY back to January 2, 2013").
2. **(b) window:** made with the tool's "Excluded Dates" field (2025-10-30 2025-10-31) on the 1-year run, which gives 2025-11-01 to the latest date. T1b was run with the custom-date entry (ignored by the server), so it equals T1a; T1 had no Oct-2025 trades anyway. T7b was not run because T7a's Monthly P/L shows no trades before November 2025, so the two windows hold the same trades.
3. **Yearly rows:** the tool does not show results by year as separate runs, but its "Monthly P/L" table has year rows; these are recorded under each test. The 2025 row covers only Nov-Dec (plus Oct 30-31 in the "a" runs).
4. **Commissions:** not set to $0.65. Fees are a per-user "Trading Fees" preference (Adjust fees: "Adjust the values used to calculate commissions and fees"), i.e. an account-level setting, so it was left at the default: SPX and XSP $0.79 per contract to open and to close; "Other Symbols" (SPY) $0.04 to open, $0.04 to close; assignment/exercise fee $0. The page says these defaults are "the estimated fees charged by TradeStation for trades made through Option Alpha". Fees are shown only as "Estimated fees" and are **not included** in Total P/L, Max Drawdown or other stats (OA help: "they are not included in the Total P/L, Max Drawdown and other stats"). The counts are consistent with $0.04 per contract per side, no close fee on expired positions (e.g. T1a: 115 positions, $9.20; T7a: $16.00 with 28 expired).
5. **T7/T8 strike rule:** the "$ below/above N minute opening range low/high" recipe exists, but the $ offset has a minimum of $0.01 ("The minimum value is 0.01"). Used "$0.01 below 60 minute opening range low or lower" (T7) and "$0.01 above 60 minute opening range high or higher" (T8). Long leg: "$2.00 below short put leg" / "$2.00 above short call leg" (or closest).
6. **T9 stop:** set to the tool's option "-200% of credit" (results show "STOP LOSS 200%"). The form does not state whether that means loss = 2x credit (close cost = 3x credit); recorded exactly as set. Profit target None. Skip Events = "FOMC Meeting" (exists), mode "Event is on the open date".
7. **Time exit:** the tool's Exit Options "Expiration" list has "35 min before close" (= 3:25 PM ET on full days, 12:25 PM on 1:00 PM early-close days). Used for all tests.
8. **ORB latest entry:** set 12:00 PM. T1a's positions list shows some entries stamped 12:01pm (e.g. Sep 25, 2026; Aug 24, 2026), so the tool appears to allow the bar ending just after the cutoff.
9. **Strike for long options:** ".50 delta or closest" (calls) and "-.50 delta or closest" (puts).
10. **Defaults left as is:** allocation $25,000; "Automatically detect and ignore unrealistic exit prices" checked (default); no position criteria or entry filters; bid/ask entry filter off; "At least 1 market day from last opened position" unchecked.
11. **Results field "Avg R/R":** shows 0 on the results page and "--" in the My Backtests list for all long-option tests; shows a % for credit strategies (T7 8.4%, T8 9.7%, T9 30.0%).

### How Option Alpha models fills (from the tool's own text)
- Opening and closing fills are at the **mid price** plus the slippage you enter (we entered $0.03 open and $0.03 close). The slippage box pre-fills with "the average slippage from the mid price for the selected symbol based on liquidity research": SPY long call showed $0.05 open and $0.05 close before we changed it; the iron condor's placeholder was $0.20. Help text: "Mid price does not include any slippage defined in the Position Entry section."
- **Exit bid/ask guard** ("Automatically detect and prevent closing positions when there is a pricing issue that may produce an unrealistic fill price (for example, when the bid/ask spread is too wide or a leg ask price is $0)"). OA's help ("Invalid Pricing Detected"): when an exit triggers but the spread is too wide, "The backtester will recheck prices every minute"; if no valid mid is found before 4:00 pm, "the position will expire and the P/L will be calculated from the underlying's close price." This hit many credit trades: T7a 28 of 114 expired, T8a 27 of 96, T9a 90 of 237 ("could not be closed before expiration. Unable to calculate a valid mid price"). So the 3:25 PM exit did not apply to those trades; they were settled at the close.
- Profit-target exits can fill beyond the target: T1a's positions list shows a "Profits" exit on Oct 27, 2026 with risk $124 and P/L $130 on a 100% target.
- The tool flags "closed positions had wider than normal bid/ask spreads that may affect results" (3 to 10 per test) and, for credit trades, after-hours assignment risk (T9: "25 positions expired in the money may be assigned or exercised").
- Fees are separate from P/L (see deviation 4).
- Data window used: 2025-10-30 to 2026-10-30 (trial). OA says paid plans can backtest SPY back to 2013-01-02.

## T1: Long call, ORB 60 min, Above high

### T1a (requested: longest history; trial clamped it to 1 year)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793434719013510129 |
| Description | T1a long call ORB60 above full |
| Settings used | SPY, exactly 0 DTE, Long Call .50 delta (or closest), allocation $25,000 (default), 1 contract, entry trigger ORB, opening period 60 min, direction Above high, latest entry 12:00pm, only trade first breakout = Yes, Mon-Fri, skip events None, position limit 1, opening slippage $0.03, profit taking 100% return, stop loss -50% of debit, Expiration exit 35 min before close (= 3:25 PM ET on full days), closing slippage $0.03, "Automatically detect and ignore unrealistic exit prices" = checked (default) |
| Deviation | Custom period 2013-01-01 to 2026-10-30 was entered, but the trial shows "Backtests are limited to 1 year during a free trial"; the saved test has period = 1y |
| Period | 1Y: first session in result data 2025-10-30, last trade 2026-10-29 (chart axis Dec '25 to Oct '26) |
| Total P/L | $2,008 |
| Max drawdown | -$648 |
| Return on DD | 309.9% |
| High P/L / Low P/L | $2,342 / -$57 |
| Profit factor | 1.44 |
| Sharpe / Sortino | 1.82 / 1.859 |
| Positions (count) | 115 |
| Filtered | 136 |
| Win rate | 42.6% (49W / 66L) |
| Best win / worst loss | $417 / -$137 |
| Win streak / loss streak | 4 / -5 |
| Avg P/L | $17 |
| Avg risk | $132 |
| Avg return on risk (avg ROR) | 13.2% |
| Avg reward/risk (avg R/R) | 0 |
| Avg entry price / premium | 1.32 / $132 |
| Avg win / avg loss | $134 / -$69 |
| Exits | Profits 45, Stop loss 62, Before exp 8 |
| Fees (tool) | Estimated fees: $9.20 (Commissions $9.20, Assignment 0, Total $9.20) |
| Other insights | 4 closed positions had wider than normal bid/ask spreads that may affect results. Longest drawdown lasted 112 days. 2 drawdowns lasted 30 days or more. Average drawdown duration is 21 days. Average drawdown is $187.21. |

Yearly rows (tool's Monthly P/L table; columns: P/L, trades, win rate, avg ROR, avg P/L, avg risk, best, worst):

| Year | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 (Nov-Dec only) | $726 | 16 | 50.0% | 33.2% | $45 | $137 | $247 | -$96 |
| 2026 (Jan-Oct) | $1,282 | 99 | 41.4% | 9.8% | $13 | $132 | $417 | -$137 |

### T1b (requested: 2025-11-01 to latest; trial again ran 1 year)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793434953173919130 |
| Description | T1b long call ORB60 above 2025-11-01 |
| Settings used | Same as T1a |
| Deviation | Custom period 2025-11-01 to 2026-10-30 was entered; the server saved period = 1y again (custom dates dropped on the trial) |
| Result | Identical to T1a in every field: P/L $2,008, max DD -$648, PF 1.44, 115 positions, win rate 42.6% (49W/66L), avg win $134, avg loss -$69, avg ROR 13.2%, avg R/R 0, est. fees $9.20 |

Note: T1a's 1-year window has no trades before 2025-11-04 (2025-10-30, 10-31 and 11-03 had no breakout), so the 1Y run and the requested 2025-11-01 window contain the same trades.

## T2: Long put, ORB 60 min, Below low

### T2a (trial maximum: 1 year)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793435131128218131 |
| Description | T2 long put ORB60 below 1Y |
| Settings used | As T1 but Long Put -.50 delta (or closest), breakout direction Below low |
| Deviation | Period 1Y (trial maximum); longest history not available on the trial |
| Period | 1Y (2025-10-30 to 2026-10-30); includes 1 trade in Oct 2025 |
| Total P/L | -$1,582 |
| Max drawdown | -$1,953 |
| Return on DD | -81.0% |
| High P/L / Low P/L | $270 / -$1,683 |
| Profit factor | 0.73 |
| Sharpe / Sortino | -1.498 / -1.254 |
| Positions (count) | 96 |
| Filtered | 155 |
| Win rate | 26.0% (25W / 71L) |
| Best win / worst loss | $294 / -$214 |
| Win streak / loss streak | 3 / -11 |
| Avg P/L | -$16 |
| Avg risk | $159 |
| Avg ROR | -10.3% |
| Avg R/R | 0 |
| Avg entry price / premium | 1.59 / $159 |
| Avg win / avg loss | $173 / -$83 |
| Exits | Profits 23, Stop loss 69, Before exp 4 |
| Fees (tool) | Estimated fees: $7.68 (Commissions $7.68, Assignment 0, Total $7.68) |
| Other insights | 9 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.73 is considered poor. 2 losing streaks with 10 or more losses in a row. Longest drawdown lasted 357 days. Average drawdown duration is 181 days. Average drawdown is $1,019.50. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 | -$434 | 19 | 26.3% | -14.6% | -$23 | $157 | $189 | -$169 |
| of which Oct 2025 | $167 | 1 | 100.0% | 106.4% | $167 | $157 | $167 | 0 |
| 2026 | -$1,148 | 77 | 26.0% | -9.3% | -$15 | $160 | $294 | -$214 |

### T2b (requested: 2025-11-01 to latest)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793435206970991132 |
| Description | T2b long put ORB60 below from 2025-11-01 |
| Settings used | Same as T2a, plus Excluded Dates = 2025-10-30 2025-10-31 |
| Deviation | Custom dates are ignored on the trial, so the 1Y window was cut to start 2025-11-01 with the tool's "Excluded Dates" field (drops the two Oct-2025 sessions) |
| Period | 2025-11-01 to 2026-10-30 (1Y window minus 2025-10-30/31) |
| Total P/L | -$1,749 |
| Max drawdown | -$1,953 |
| Return on DD | -89.6% |
| High P/L / Low P/L | $103 / -$1,850 |
| Profit factor | 0.7 |
| Sharpe / Sortino | -1.669 / -1.382 |
| Positions (count) | 95 |
| Filtered | 156 |
| Win rate | 25.3% (24W / 71L) |
| Best win / worst loss | $294 / -$214 |
| Win streak / loss streak | 3 / -11 |
| Avg P/L | -$18 |
| Avg risk | $159 |
| Avg ROR | -11.6% |
| Avg R/R | 0 |
| Avg entry price / premium | 1.59 / $159 |
| Avg win / avg loss | $173 / -$83 |
| Exits | Profits 22, Stop loss 69, Before exp 4 |
| Fees (tool) | Estimated fees: $7.60 (Commissions $7.60, Assignment 0, Total $7.60) |
| Other insights | 8 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.7 is considered poor. 2 losing streaks with 10 or more losses in a row. Longest drawdown lasted 357 days. Average drawdown duration is 181 days. Average drawdown is $1,019.50. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 (Nov-Dec) | -$601 | 18 | 22.2% | -21.3% | -$33 | $157 | $189 | -$169 |
| 2026 | -$1,148 | 77 | 26.0% | -9.3% | -$15 | $160 | $294 | -$214 |


## T4: Long put, ORB 30 min, Below low

### T4a (trial maximum: 1 year)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793435297862903133 |
| Description | T4a long put ORB30 below 1Y |
| Settings used | As T2 but opening period 30 minutes |
| Deviation | Period 1Y (trial maximum) |
| Period | 1Y (2025-10-30 to 2026-10-30); includes 1 trade in Oct 2025 |
| Total P/L | -$1,035 |
| Max drawdown | -$1,152 |
| Return on DD | -89.8% |
| High P/L / Low P/L | $117 / -$1,035 |
| Profit factor | 0.85 |
| Sharpe / Sortino | -0.651 / -0.602 |
| Positions (count) | 110 |
| Filtered | 141 |
| Win rate | 30.0% (33W / 77L) |
| Best win / worst loss | $323 / -$163 |
| Win streak / loss streak | 3 / -10 |
| Avg P/L | -$9 |
| Avg risk | $165 |
| Avg ROR | -5.7% |
| Avg R/R | 0 |
| Avg entry price / premium | 1.65 / $165 |
| Avg win / avg loss | $175 / -$88 |
| Exits | Profits 33, Stop loss 77 (no "Before exp" row shown) |
| Fees (tool) | Estimated fees: $8.80 (Commissions $8.80, Assignment 0, Total $8.80) |
| Other insights | 10 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.85 is considered poor. 1 losing streak with 10 or more losses in a row. Longest drawdown lasted 220 days. 2 drawdowns lasted 30 days or more. Average drawdown duration is 120 days. Average drawdown is $755.00. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 | -$517 | 21 | 23.8% | -15.7% | -$25 | $157 | $231 | -$163 |
| of which Oct 2025 | -$105 | 1 | 0 | -52.8% | -$105 | $199 | 0 | -$105 |
| 2026 | -$518 | 89 | 31.5% | -3.5% | -$6 | $167 | $323 | -$162 |

### T4b (requested: 2025-11-01 to latest)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793435350475545134 |
| Description | T4b long put ORB30 below from 2025-11-01 |
| Settings used | Same as T4a plus Excluded Dates = 2025-10-30 2025-10-31 |
| Deviation | Window cut to 2025-11-01 start with Excluded Dates (custom dates ignored on trial) |
| Period | 2025-11-01 to 2026-10-30 |
| Total P/L | -$930 |
| Max drawdown | -$1,152 |
| Return on DD | -80.7% |
| High P/L / Low P/L | $222 / -$930 |
| Profit factor | 0.86 |
| Sharpe / Sortino | -0.584 / -0.539 |
| Positions (count) | 109 |
| Filtered | 142 |
| Win rate | 30.3% (33W / 76L) |
| Best win / worst loss | $323 / -$163 |
| Win streak / loss streak | 3 / -10 |
| Avg P/L | -$9 |
| Avg risk | $164 |
| Avg ROR | -5.2% |
| Avg R/R | 0 |
| Avg entry price / premium | 1.64 / $164 |
| Avg win / avg loss | $175 / -$88 |
| Exits | Profits 33, Stop loss 76 |
| Fees (tool) | Estimated fees: $8.72 (Commissions $8.72, Assignment 0, Total $8.72) |
| Other insights | 10 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.86 is considered poor. 1 losing streak with 10 or more losses in a row. Longest drawdown lasted 220 days. 2 drawdowns lasted 30 days or more. Average drawdown duration is 119 days. Average drawdown is $720.00. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 (Nov-Dec) | -$412 | 20 | 25.0% | -13.3% | -$21 | $154 | $231 | -$163 |
| 2026 | -$518 | 89 | 31.5% | -3.5% | -$6 | $167 | $323 | -$162 |

## T6: Long put, ORB 15 min, Below low

### T6a (trial maximum: 1 year)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793435414847687135 |
| Description | T6a long put ORB15 below 1Y |
| Settings used | As T2 but opening period 15 minutes |
| Deviation | Period 1Y (trial maximum) |
| Period | 1Y (2025-10-30 to 2026-10-30); includes 1 trade in Oct 2025 |
| Total P/L | -$1,791 |
| Max drawdown | -$2,544 |
| Return on DD | -70.4% |
| High P/L / Low P/L | $303 / -$2,241 |
| Profit factor | 0.77 |
| Sharpe / Sortino | -1.095 / -1.033 |
| Positions (count) | 120 |
| Filtered | 131 |
| Win rate | 29.2% (35W / 85L) |
| Best win / worst loss | $294 / -$179 |
| Win streak / loss streak | 3 / -11 |
| Avg P/L | -$15 |
| Avg risk | $174 |
| Avg ROR | -8.6% |
| Avg R/R | 0 |
| Avg entry price / premium | 1.74 / $174 |
| Avg win / avg loss | $170 / -$91 |
| Exits | Profits 33, Stop loss 83, Before exp 4 |
| Fees (tool) | Estimated fees: $9.60 (Commissions $9.60, Assignment 0, Total $9.60) |
| Other insights | 9 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.77 is considered poor. 2 losing streaks with 10 or more losses in a row. Longest drawdown lasted 241 days. 2 drawdowns lasted 30 days or more. Average drawdown duration is 119 days. Average drawdown is $1,168.00. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 | -$440 | 25 | 28.0% | -9.9% | -$18 | $177 | $294 | -$179 |
| of which Oct 2025 | -$97 | 1 | 0 | -50.8% | -$97 | $191 | 0 | -$97 |
| 2026 | -$1,351 | 95 | 29.5% | -8.2% | -$14 | $173 | $293 | -$177 |

### T6b (requested: 2025-11-01 to latest)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793435498843902136 |
| Description | T6b long put ORB15 below from 2025-11-01 |
| Settings used | Same as T6a plus Excluded Dates = 2025-10-30 2025-10-31 |
| Deviation | Window cut to 2025-11-01 start with Excluded Dates (custom dates ignored on trial) |
| Period | 2025-11-01 to 2026-10-30 |
| Total P/L | -$1,694 |
| Max drawdown | -$2,544 |
| Return on DD | -66.6% |
| High P/L / Low P/L | $400 / -$2,144 |
| Profit factor | 0.78 |
| Sharpe / Sortino | -1.032 / -0.971 |
| Positions (count) | 119 |
| Filtered | 132 |
| Win rate | 29.4% (35W / 84L) |
| Best win / worst loss | $294 / -$179 |
| Win streak / loss streak | 3 / -11 |
| Avg P/L | -$14 |
| Avg risk | $174 |
| Avg ROR | -8.2% |
| Avg R/R | 0 |
| Avg entry price / premium | 1.74 / $174 |
| Avg win / avg loss | $170 / -$91 |
| Exits | Profits 33, Stop loss 82, Before exp 4 |
| Fees (tool) | Estimated fees: $9.52 (Commissions $9.52, Assignment 0, Total $9.52) |
| Other insights | 9 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.78 is considered poor. 2 losing streaks with 10 or more losses in a row. Longest drawdown lasted 241 days. 2 drawdowns lasted 30 days or more. Average drawdown duration is 176 days. Average drawdown is $1,703.50. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 (Nov-Dec) | -$343 | 24 | 29.2% | -8.1% | -$14 | $177 | $294 | -$179 |
| 2026 | -$1,351 | 95 | 29.5% | -8.2% | -$14 | $173 | $293 | -$177 |

## T5: Long call, ORB 15 min, Above high

### T5a (trial maximum: 1 year)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793435616018171137 |
| Description | T5a long call ORB15 above 1Y |
| Settings used | As T1 but opening period 15 minutes |
| Deviation | Period 1Y (trial maximum) |
| Period | 1Y (2025-10-30 to 2026-10-30); includes 1 trade in Oct 2025 |
| Total P/L | -$488 |
| Max drawdown | -$1,063 |
| Return on DD | -45.9% |
| High P/L / Low P/L | $502 / -$561 |
| Profit factor | 0.93 |
| Sharpe / Sortino | 0.176 / 0.18 |
| Positions (count) | 129 |
| Filtered | 122 |
| Win rate | 34.1% (44W / 85L) |
| Best win / worst loss | $298 / -$189 |
| Win streak / loss streak | 4 / -8 |
| Avg P/L | -$4 |
| Avg risk | $164 |
| Avg ROR | -2.3% |
| Avg R/R | 0 |
| Avg entry price / premium | 1.64 / $164 |
| Avg win / avg loss | $159 / -$88 |
| Exits | Profits 41, Stop loss 82, Before exp 6 |
| Fees (tool) | Estimated fees: $10.32 (Commissions $10.32, Assignment 0, Total $10.32) |
| Other insights | 4 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.93 is considered poor. Longest drawdown lasted 144 days. 3 drawdowns lasted 30 days or more. Average drawdown duration is 50 days. Average drawdown is $437.43. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 | -$107 | 16 | 25.0% | -3.8% | -$7 | $174 | $278 | -$136 |
| of which Oct 2025 | -$128 | 1 | 0 | -54.0% | -$128 | $237 | 0 | -$128 |
| 2026 | -$381 | 113 | 35.4% | -2.1% | -$3 | $163 | $298 | -$189 |

### T5b (requested: 2025-11-01 to latest)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793435666841873138 |
| Description | T5b long call ORB15 above from 2025-11-01 |
| Settings used | Same as T5a plus Excluded Dates = 2025-10-30 2025-10-31 |
| Deviation | Window cut to 2025-11-01 start with Excluded Dates (custom dates ignored on trial) |
| Period | 2025-11-01 to 2026-10-30 |
| Total P/L | -$360 |
| Max drawdown | -$1,063 |
| Return on DD | -33.9% |
| High P/L / Low P/L | $630 / -$433 |
| Profit factor | 0.95 |
| Sharpe / Sortino | 0.24 / 0.244 |
| Positions (count) | 128 |
| Filtered | 123 |
| Win rate | 34.4% (44W / 84L) |
| Best win / worst loss | $298 / -$189 |
| Win streak / loss streak | 4 / -8 |
| Avg P/L | -$3 |
| Avg risk | $163 |
| Avg ROR | -1.7% |
| Avg R/R | 0 |
| Avg entry price / premium | 1.63 / $163 |
| Avg win / avg loss | $159 / -$87 |
| Exits | Profits 41, Stop loss 81, Before exp 6 |
| Fees (tool) | Estimated fees: $10.24 (Commissions $10.24, Assignment 0, Total $10.24) |
| Other insights | 4 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.95 is considered poor. Longest drawdown lasted 144 days. 3 drawdowns lasted 30 days or more. Average drawdown duration is 50 days. Average drawdown is $437.43. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 (Nov-Dec) | $21 | 15 | 26.7% | 0.8% | $1 | $170 | $278 | -$136 |
| 2026 | -$381 | 113 | 35.4% | -2.1% | -$3 | $163 | $298 | -$189 |

## T3: Long call, ORB 30 min, Above high

### T3a (trial maximum: 1 year)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793435732843136139 |
| Description | T3a long call ORB30 above 1Y |
| Settings used | As T1 but opening period 30 minutes |
| Deviation | Period 1Y (trial maximum) |
| Period | 1Y (2025-10-30 to 2026-10-30); includes 1 trade in Oct 2025 |
| Total P/L | -$85 |
| Max drawdown | -$995 |
| Return on DD | -8.5% |
| High P/L / Low P/L | $341 / -$654 |
| Profit factor | 0.99 |
| Sharpe / Sortino | 0.449 / 0.461 |
| Positions (count) | 133 |
| Filtered | 118 |
| Win rate | 36.8% (49W / 84L) |
| Best win / worst loss | $249 / -$147 |
| Win streak / loss streak | 3 / -6 |
| Avg P/L | -$1 |
| Avg risk | $147 |
| Avg ROR | -0.4% |
| Avg R/R | 0 |
| Avg entry price / premium | 1.47 / $147 |
| Avg win / avg loss | $136 / -$80 |
| Exits | Profits 44, Stop loss 82, Before exp 7 |
| Fees (tool) | Estimated fees: $10.64 (Commissions $10.64, Assignment 0, Total $10.64) |
| Other insights | 4 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.99 is considered poor. Longest drawdown lasted 318 days. Average drawdown duration is 57 days. Average drawdown is $274.00. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 | $206 | 20 | 35.0% | 6.9% | $10 | $149 | $230 | -$113 |
| of which Oct 2025 | -$94 | 1 | 0 | -52.2% | -$94 | $180 | 0 | -$94 |
| 2026 | -$291 | 113 | 37.2% | -1.8% | -$3 | $146 | $249 | -$147 |

### T3b (requested: 2025-11-01 to latest)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793435783842047140 |
| Description | T3b long call ORB30 above from 2025-11-01 |
| Settings used | Same as T3a plus Excluded Dates = 2025-10-30 2025-10-31 |
| Deviation | Window cut to 2025-11-01 start with Excluded Dates (custom dates ignored on trial) |
| Period | 2025-11-01 to 2026-10-30 |
| Total P/L | $9 |
| Max drawdown | -$995 |
| Return on DD | 0.9% |
| High P/L / Low P/L | $435 / -$560 |
| Profit factor | 1.0 |
| Sharpe / Sortino | 0.511 / 0.522 |
| Positions (count) | 132 |
| Filtered | 119 |
| Win rate | 37.1% (49W / 83L) |
| Best win / worst loss | $249 / -$147 |
| Win streak / loss streak | 3 / -6 |
| Avg P/L | $0 |
| Avg risk | $146 |
| Avg ROR | 0.1% |
| Avg R/R | 0 |
| Avg entry price / premium | 1.46 / $146 |
| Avg win / avg loss | $136 / -$80 |
| Exits | Profits 44, Stop loss 81, Before exp 7 |
| Fees (tool) | Estimated fees: $10.56 (Commissions $10.56, Assignment 0, Total $10.56) |
| Other insights | 4 closed positions had wider than normal bid/ask spreads that may affect results. Longest drawdown lasted 318 days. Average drawdown duration is 57 days. Average drawdown is $274.00. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 (Nov-Dec) | $300 | 19 | 36.8% | 10.7% | $16 | $147 | $230 | -$113 |
| 2026 | -$291 | 113 | 37.2% | -1.8% | -$3 | $146 | $249 | -$147 |

## T7: Short put spread, ORB 60 min, Above high

### T7a (trial maximum: 1 year)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793436066851865141 |
| Description | T7a short put spread ORB60 above 1Y |
| Settings used | SPY, exactly 0 DTE, Short Put Spread; SHORT PUT = "$0.01 below 60 minute opening range low or lower"; LONG PUT = "$2.00 below short put leg" (or closest); allocation $25,000, 1 contract, ORB 60 min Above high, latest entry 12:00pm, first breakout only = Yes, Mon-Fri, skip events None, position limit 1, opening slippage $0.03; exits: no profit target, no stop (both None), Expiration exit 35 min before close, closing slippage $0.03, ignore-unrealistic-exit-prices = checked (default) |
| Deviation | Period 1Y (trial maximum). Strike-by-range exists, but the $ offset has a minimum of $0.01 ("The minimum value is 0.01"), so the short put is the first strike at or below (OR low - $0.01) instead of at or below the OR low itself |
| Period | 1Y (2025-10-30 to 2026-10-30); no trades in Oct 2025 (first month row is November) |
| Total P/L | -$646 |
| Max drawdown | -$746 |
| Return on DD | -86.6% |
| High P/L / Low P/L | $21 / -$725 |
| Profit factor | 0.61 |
| Sharpe / Sortino | -1.475 / -0.492 |
| Positions (count) | 114 |
| Filtered | 137 |
| Win rate | 76.3% (87W / 26L) |
| Best win / worst loss | $42 / -$180 |
| Win streak / loss streak | 16 / -2 |
| Max profit % / max loss % | 24.6% / 0.9% |
| Avg P/L | -$6 |
| Avg risk | $185 |
| Avg ROR | -3.1% |
| Avg R/R | 8.4% |
| Avg entry price / premium | 0.15 / $15 (credit) |
| Avg win / avg loss | $11 / -$63 |
| Exits | Before exp 86, Expired 28 |
| Fees (tool) | Estimated fees: $16 (Commissions $16, Assignment 0, Total $16) |
| Other insights | 3 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.61 is considered poor. 28 positions held into expiration may be assigned after hours. 76.32% win rate is high. Longest drawdown lasted 344 days. Average drawdown duration is 173 days. Average drawdown is $379.00. 28 positions could not be closed before expiration. Unable to calculate a valid mid price. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 (Nov-Dec) | -$21 | 16 | 87.5% | -0.7% | -$1 | $186 | $42 | -$180 |
| 2026 | -$625 | 98 | 75.3% | -3.5% | -$6 | $185 | $30 | -$163 |

### T7b (requested: 2025-11-01 to latest)

Not run separately: T7a's 1Y result has no trades before 2025-11-01 (its Monthly P/L table starts in November 2025), so the 2025-11-01 window holds exactly the same 114 positions. T7b = T7a.

## T8: Short call spread, ORB 60 min, Below low

### T8a (trial maximum: 1 year)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793436268852564142 |
| Description | T8a short call spread ORB60 below 1Y |
| Settings used | SPY, exactly 0 DTE, Short Call Spread; SHORT CALL = "$0.01 above 60 minute opening range high or higher"; LONG CALL = "$2.00 above short call leg" (or closest); ORB 60 min Below low, latest entry 12:00pm, first breakout only = Yes; other common settings as T7; no profit target, no stop; Expiration exit 35 min before close; slippage $0.03 open and close |
| Deviation | Period 1Y (trial maximum). $ offset minimum is $0.01, so short call = first strike at or above (OR high + $0.01) |
| Period | 1Y (2025-10-30 to 2026-10-30); includes 1 trade in Oct 2025 |
| Total P/L | -$614 |
| Max drawdown | -$667 |
| Return on DD | -92.1% |
| High P/L / Low P/L | $17 / -$650 |
| Profit factor | 0.63 |
| Sharpe / Sortino | -1.263 / -0.402 |
| Positions (count) | 96 |
| Filtered | 155 |
| Win rate | 75.0% (72W / 23L) |
| Best win / worst loss | $46 / -$177 |
| Win streak / loss streak | 13 / -3 |
| Max profit % / max loss % | 28.1% / 1.0% |
| Avg P/L | -$6 |
| Avg risk | $183 |
| Avg ROR | -3.5% |
| Avg R/R | 9.7% |
| Avg entry price / premium | 0.17 / $17 (credit) |
| Avg win / avg loss | $14 / -$71 |
| Exits | Before exp 69, Expired 27 |
| Fees (tool) | Estimated fees: $13.20 (Commissions $13.20, Assignment 0, Total $13.20) |
| Other insights | 5 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.63 is considered poor. 27 positions held into expiration may be assigned after hours. 75% win rate is high. Longest drawdown lasted 357 days. Average drawdown duration is 357 days. Average drawdown is $667.00. 27 positions could not be closed before expiration. Unable to calculate a valid mid price. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 | -$285 | 19 | 63.2% | -8.2% | -$15 | $183 | $30 | -$142 |
| of which Oct 2025 | $3 | 1 | 100.0% | 1.6% | $3 | $187 | $3 | 0 |
| 2026 | -$329 | 77 | 79.0% | -2.3% | -$4 | $183 | $46 | -$177 |

### T8b (requested: 2025-11-01 to latest)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793436323838133143 |
| Description | T8b short call spread ORB60 below from 2025-11-01 |
| Settings used | Same as T8a plus Excluded Dates = 2025-10-30 2025-10-31 |
| Deviation | Window cut to 2025-11-01 start with Excluded Dates (custom dates ignored on trial); $0.01 strike offset as in T8a |
| Period | 2025-11-01 to 2026-10-30 |
| Total P/L | -$617 |
| Max drawdown | -$667 |
| Return on DD | -92.5% |
| High P/L / Low P/L | $14 / -$653 |
| Profit factor | 0.62 |
| Sharpe / Sortino | -1.269 / -0.404 |
| Positions (count) | 95 |
| Filtered | 156 |
| Win rate | 74.7% (71W / 23L) |
| Best win / worst loss | $46 / -$177 |
| Win streak / loss streak | 13 / -3 |
| Max profit % / max loss % | 28.4% / 1.1% |
| Avg P/L | -$6 |
| Avg risk | $183 |
| Avg ROR | -3.6% |
| Avg R/R | 9.7% |
| Avg entry price / premium | 0.17 / $17 (credit) |
| Avg win / avg loss | $14 / -$71 |
| Exits | Before exp 68, Expired 27 |
| Fees (tool) | Estimated fees: $13.04 (Commissions $13.04, Assignment 0, Total $13.04) |
| Other insights | 5 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.62 is considered poor. 27 positions held into expiration may be assigned after hours. Longest drawdown lasted 357 days. Average drawdown duration is 357 days. Average drawdown is $667.00. 27 positions could not be closed before expiration. Unable to calculate a valid mid price. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 (Nov-Dec) | -$288 | 18 | 61.1% | -8.8% | -$16 | $182 | $30 | -$142 |
| 2026 | -$329 | 77 | 79.0% | -2.3% | -$4 | $183 | $46 | -$177 |

## T9: Iron condor, time entry 10:00 AM, 0.20-delta shorts, $2 wings

### T9a (trial maximum: 1 year)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793436603403487144 |
| Description | T9a iron condor 10:00 20d $2 wings 1Y |
| Settings used | SPY, exactly 0 DTE, Iron Condor; SHORT CALL = .20 delta (or closest); SHORT PUT = -.20 delta (or closest); LONG CALL = $2.00 above short call leg; LONG PUT = $2.00 below short put leg; allocation $25,000, 1 contract; entry trigger Time of day, entry time 10:00am; Mon-Fri; Skip Events = FOMC Meeting (mode "Event is on the open date"); position limit 1; opening slippage $0.03; exits: Stop Loss % = "-200% of credit" (tool's own wording; shown in results as STOP LOSS 200%), no profit target, Expiration exit 35 min before close, closing slippage $0.03, ignore-unrealistic-exit-prices = checked (default) |
| Deviation | Period 1Y (trial maximum). Stop set as the tool's "-200% of credit" option; the tool does not say in the form whether this is measured as loss = 2x credit (cost to close = 3x credit) — recorded exactly as set |
| Period | 1Y (2025-10-30 to 2026-10-30); includes 2 trades in Oct 2025 |
| Total P/L | -$125 |
| Max drawdown | -$1,323 |
| Return on DD | -9.5% |
| High P/L / Low P/L | $594 / -$729 |
| Profit factor | 0.98 |
| Sharpe / Sortino | -0.103 / -0.066 |
| Positions (count) | 237 |
| Filtered | 14 |
| Win rate | 68.4% (162W / 74L) |
| Best win / worst loss | $64 / -$156 |
| Win streak / loss streak | 15 / -4 |
| Max profit % / max loss % | 27.4% / 3.4% |
| Avg P/L | -$1 |
| Avg risk | $154 |
| Avg ROR | -0.3% |
| Avg R/R | 30.0% |
| Avg entry price / premium | 0.46 / $46 (credit) |
| Avg win / avg loss | $37 / -$84 |
| Exits | Stop loss 39, Before exp 108, Expired 90 |
| Fees (tool) | Estimated fees: $61.44 (Commissions $61.44, Assignment 0, Total $61.44) |
| Other insights | 25 positions expired in the money may be assigned or exercised. 4 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.98 is considered poor. 90 positions held into expiration may be assigned after hours. Longest drawdown lasted 272 days. 2 drawdowns lasted 30 days or more. Average drawdown duration is 115 days. Average drawdown is $590.33. 90 positions could not be closed before expiration. Unable to calculate a valid mid price. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 | $77 | 39 | 69.2% | 1.3% | $2 | $153 | $62 | -$156 |
| of which Oct 2025 | $46 | 2 | 100.0% | 15.4% | $23 | $149 | $40 | 0 |
| 2026 | -$202 | 198 | 68.5% | -0.7% | -$1 | $155 | $64 | -$153 |

### T9b (requested: 2025-11-01 to latest)

| Field | Value |
|---|---|
| Test id (OA) | ZT31793436694195621145 |
| Description | T9b iron condor 10:00 20d $2 wings from 2025-11-01 |
| Settings used | Same as T9a plus Excluded Dates = 2025-10-30 2025-10-31 |
| Deviation | Window cut to 2025-11-01 start with Excluded Dates (custom dates ignored on trial); stop as in T9a |
| Period | 2025-11-01 to 2026-10-30 |
| Total P/L | -$171 |
| Max drawdown | -$1,323 |
| Return on DD | -12.9% |
| High P/L / Low P/L | $548 / -$775 |
| Profit factor | 0.97 |
| Sharpe / Sortino | -0.152 / -0.097 |
| Positions (count) | 235 |
| Filtered | 16 |
| Win rate | 68.1% (160W / 74L) |
| Best win / worst loss | $64 / -$156 |
| Win streak / loss streak | 15 / -4 |
| Max profit % / max loss % | 27.7% / 3.4% |
| Avg P/L | -$1 |
| Avg risk | $154 |
| Avg ROR | -0.5% |
| Avg R/R | 29.9% |
| Avg entry price / premium | 0.46 / $46 (credit) |
| Avg win / avg loss | $38 / -$84 |
| Exits | Stop loss 39, Before exp 106, Expired 90 |
| Fees (tool) | Estimated fees: $60.80 (Commissions $60.80, Assignment 0, Total $60.80) |
| Other insights | 25 positions expired in the money may be assigned or exercised. 4 closed positions had wider than normal bid/ask spreads that may affect results. Profit factor of 0.97 is considered poor. 90 positions held into expiration may be assigned after hours. Longest drawdown lasted 272 days. 2 drawdowns lasted 30 days or more. Average drawdown duration is 115 days. Average drawdown is $590.33. 90 positions could not be closed before expiration. Unable to calculate a valid mid price. |

| Period row | P/L | Trades | Win rate | Avg ROR | Avg P/L | Avg risk | Best | Worst |
|---|---|---|---|---|---|---|---|---|
| 2025 (Nov-Dec) | $31 | 37 | 67.6% | 0.6% | $1 | $153 | $62 | -$156 |
| 2026 | -$202 | 198 | 68.5% | -0.7% | -$1 | $155 | $64 | -$153 |

## Fact-finding 2026-10-31

Read-only pass: no new backtests were run. Sources: the backtest settings form (opened as "Create a new backtest as a variation", never submitted), the in-app help cards, the saved runs and their position details, and the app's own page script (bots.v2587.js), read in the browser. Quotes are exact UI wording.

### 1. Exit options the backtester offers

Exit Options section (labels as shown):

| Exit | Exact name in UI | Allowed values | Long call/put | Credit spreads / iron condor |
|---|---|---|---|---|
| % profit target | "Profit Taking %" | None; "5% return" … "100% return" in 5% steps; 110–200% in 10% steps; 225% … "1000% return" in 25% steps (debit). Credit version: None; "2.5% of credit", "5%", "7.5%", "10%", "12.5%", "15%", "17.5%", "20% of credit", then 25% … "95% of credit" in 5% steps | yes (debit list) | yes (credit list) |
| Confirm target | "Require 2 consecutive hits" (checkbox) | on/off. Tooltip: "Checking this box means the position has to hit your profit taking % two consecutive 1 minute intervals" | yes | yes |
| $ profit target | "Profit Taking $" | "$ [number] or more" (whole dollars, step 1). Tooltip: "Close positions when the overall $ profit is greater than or equal to this value" | yes | yes |
| % stop | "Stop Loss %" | Debit: None; "-5% of debit" … "-95% of debit" in 5% steps. Credit: None; "-5% of credit" … "-100% of credit" in 5% steps; "-110%" … "-200% of credit" in 10% steps; "-225%" … "-500% of credit" in 25% steps | yes (debit list) | yes (credit list) |
| $ stop | "Stop Loss $" | editor titled "Stop Loss Amount": "$ [number]" (step 1). Tooltip: "Close positions when the overall $ loss is less than or equal to this value" | yes | yes |
| Time exit | "Expiration" | None; "5 min before close" … "15 min before close" in 1-min steps; 20, 25, 30, 35, 40, 45 min; "1 hour" … "6 hours before close" in 30-min steps; "1 day before" … "25 days before", "30 days before" | yes | yes |
| Event exit | "Avoid Events" | "Close positions on the day before an important event. Select the event(s) below and a time to close the position." Event(s) list + Time "5 minutes" … "before market close" (default "1 hour") | yes | yes |
| Underlying vs strike | "Touch" | editor: "Close position if underlying price is... [value] [$ or %] from ITM or less" (step 0.01; negative allowed). Tooltip: "Use a negative value to allow the position to go ITM before exiting" | field shows and opens on the long-call form; help says "The 'Touch' setting can also be used for long options and debit spreads. The touch value always refers to a position going in-the-money." | yes (main use) |
| PDT | "Do not exit on the first day to avoid pattern day trading" | checkbox; hidden for 0 DTE | n/a | n/a |
| Exit slippage | "Include [x] slippage from the mid price on closing trades" | number, $ per contract/spread | yes | yes |
| Exit price guard | "Automatically detect and ignore unrealistic exit prices" (checked by default); if unchecked: "Disable Exit Options if bid/ask spread exceeds $ [x]" | placeholder for SPY: $0.15 for 1-leg, $0.20 for 2- and 4-leg positions (app table `maxba`; SPX 1-leg $1, 2/4-leg $2) | yes | yes |

**Not offered in the backtester:**
- **Trailing stop.** No setting. The only "Trailing stop" text in the app script belongs to live-bot position views ("Waiting to activate", "Target hit, trails high by …"), not to the backtest form.
- **Stops or targets on the underlying's own price or % move.** No such setting (Touch is measured from the option's strike).
- **Delta-based exits.** None.

Help text read:
- **Expiration time exit:** "the hour and minute-based selections will send orders at those specified times prior to the market close". Day-based options send at 3:29 pm ET.
- **Touch:** "references the underlying price relative to a position's strike price(s)". It triggers if the underlying is "'$X' or 'X%' from in-the-money (ITM) or less".

### 2. How exits fill

**Check frequency and trigger price** (tool's help):
- Profit Target help: "Exit Options monitor the position every minute, use the position's mid-price when evaluating returns and send an order if the criteria are met."
- Bid/Ask Guards help: "Backtest position returns are calculated using the mid-price at the time an Exit Option triggers."
- "Require 2 consecutive hits" help: "two consecutive 1 minute intervals".
- Invalid-pricing help: "The backtester will recheck prices every minute… If a mid-price within the bid/ask spread guard is not available prior to 4:00 pm, the position will expire and the P/L will be calculated from he underlying's close price."
- OA blog: "all backtesting for 0DTE and 1DTE uses 1 min historical options data".

**Fill price.** Fills are mid ± the slippage entered, but never outside the quoted bid/ask.
- Observed in T1a (all 115 position details, saved to `optionalpha_T1a_positions.csv`): every open filled at the ask (debit = ask x 100 in 115 of 115). 111 of 115 closes filled at the bid.
- The 4 other closes had wider quotes and filled at about mid - $0.03, inside the quote: 2026-05-20 bid/ask 3.46-3.54 filled 3.47; 2026-04-02 6.40-6.48 filled 6.41; 2026-02-06 3.04-3.12 filled 3.05; 2025-11-24 3.20-3.27 filled 3.21.
- Credit example (T9b iron condor): open quote 0.45-0.49 filled 0.45 (bid); stop close 1.36-1.40 filled 1.40 (ask).

**Does slippage apply to exits and stops?** Yes, through the separate "Include … slippage from the mid price on closing trades" box. It applies to every closing exit (profit, stop, time), and opening slippage is a separate box. Help: "Mid price does not include any slippage defined in the Position Entry section."

**Stop crossed between checks.** The fill comes at the next 1-minute check's price (mid ± slippage, capped at the bid/ask), not at the stop level. T1a, stop "-50% of debit":
- The 62 stop exits closed between -50.34% and -59.50% return on risk.
- Example 2026-08-07: debit $121, close bid 0.49, P/L -$72, -59.50%.

Profit target "100% return":
- The 45 target exits closed between +98.15% and +186.16%.
- Example 2026-04-02: debit $224, closed 4 minutes after entry at 6.41, +186.16%.
- Some closed just under 100% because the trigger uses the mid and the fill is at the bid.

**Credit stop "-200% of credit"** (T9b position details):

| Date | Credit | Close debit | P/L |
|---|---|---|---|
| 2026-10-27 | $45 | $140 | -$95 |
| 2026-10-16 | $40 | $124 | -$84 |
| 2026-09-23 | $31 | $106 | -$75 |

Close cost is about 3x the credit in each case, i.e. loss of about 2x credit.

**Stops can fail on illiquid legs.** In T9b, 2026-10-15 "Expired" at the full max loss: credit $47, value at exp $200, P/L -$153. The card says "Position could not be closed before expiration. Unable to calculate a valid mid price." So the 200% stop did not fill that day.

### 3. What the saved runs actually used (sidebar of each saved run, plus the stored settings in the run's API response)

All 17 runs share these settings:
- SPY, DTE "exactly 0 days", allocation $25,000, position size 1 contract, trading days Mon-Fri, position limit 1.
- Opening slippage $0.03 and closing slippage $0.03 (stored `oslip`/`xslip` 0.03).
- Position Criteria "None"; Entry Filters "None"; Profit Taking $ / Stop Loss $ / Touch / Avoid Events: none.
- "Require 2 consecutive hits": off.
- "Automatically detect and ignore unrealistic exit prices": on (stored settings have no `nobac`/`igba`, i.e. the default guard).
- Period stored as "1y" for every run.
- "b" runs store `exclude: "2025-10-30,2025-10-31"`.

| Run | Strike selection (exact) | Entry | Exits stored | Exit counts (tool) |
|---|---|---|---|---|
| T1a, T1b | LONG CALL ".50 delta" (or closest) | ORB 60 min, Above high, latest 12:00pm, first breakout Yes | PROFIT TAKING 100%, STOP LOSS 50% (stored `profits:1, stoploss:0.5` = "-50% of debit"), EXPIRATION 35 minutes | Profits 45, Stop loss 62, Before exp 8 |
| T2a / T2b | LONG PUT "-.50 delta" | ORB 60, Below low | 100% / 50% / 35 min | 23/69/4; 22/69/4 |
| T3a / T3b | LONG CALL ".50 delta" | ORB 30, Above high | 100% / 50% / 35 min | 44/82/7; 44/81/7 |
| T4a / T4b | LONG PUT "-.50 delta" | ORB 30, Below low | 100% / 50% / 35 min | 33/77/0; 33/76/0 (no "Before exp" row) |
| T5a / T5b | LONG CALL ".50 delta" | ORB 15, Above high | 100% / 50% / 35 min | 41/82/6; 41/81/6 |
| T6a / T6b | LONG PUT "-.50 delta" | ORB 15, Below low | 100% / 50% / 35 min | 33/83/4; 33/82/4 |
| T7a | SHORT PUT "$0.01 below 60 minute opening range low or lower"; LONG PUT "$2.00 below short put leg" | ORB 60, Above high, 12:00pm, first breakout | EXPIRATION 35 minutes only (stored exits `{exp, xslip}`) | Before exp 86, Expired 28 |
| T8a / T8b | SHORT CALL "$0.01 above 60 minute opening range high or higher"; LONG CALL "$2.00 above short call leg" | ORB 60, Below low | EXPIRATION 35 minutes only | 69/27; 68/27 (before exp/expired) |
| T9a / T9b | SHORT CALL ".20 delta", SHORT PUT "-.20 delta", LONG CALL "$2.00 above short call leg", LONG PUT "$2.00 below short put leg" | Time, 10:00am; SKIP EVENTS "FOMC Meeting" (mode "Event is on the open date") | STOP LOSS 200% (stored `stoploss:2` = "-200% of credit"), EXPIRATION 35 minutes; no profit target | Stop 39, Before exp 108/106, Expired 90 |

**Long-call 50% stop check:** yes. T1 stored `stoploss: 0.5` and the sidebar shows "STOP LOSS 50%".
- The tool shows avg risk $132 and avg loss -$69 for T1a.
- Losing stop exits filled at -50.34% to -59.50% of the debit, because of next-minute fills at the bid (see section 2 and the CSV).
- The 8 "Before Exp" exits at 3:25pm also include losers that never reached the stop (-22.68% to -47.22%).

### 4. Dates and export

- **End date:**
  - The form's "Custom" period has a start and an end date box. Start minimum 2013-01-01, end minimum 2013-02-01, end maximum today; "* Backtest SPY back to January 2, 2013".
  - On the trial the page script overrides it before sending: `if(a5.trial||a5.nop) s.period="1y"`. So neither the start nor the end date is used on the trial; every run is the last 1 year.
  - On a paid plan, custom sends `startDate` (required: "Invalid startDate") and an optional `endDate`. The list view shows "start to end" (or "to *" with no end).
- **Excluded Dates, range syntax:** none.
  - The placeholder reads "A list of dates (YYYY-MM-DD) separated by a space". There is no help text.
  - The script only splits on whitespace and joins with commas: `e.exclude.replace(/\s+/g," ").split(" ").join(",")`. Stored example: `"2025-10-30,2025-10-31"`.
  - An entry like "2026-07-01 to 2026-10-30" would be sent as three tokens, not a range. To lock away a period, every session date must be listed one by one.
  - No length limit is set on that box (the Description box has maxlength 150). Not tested with a long list, because that needs a backtest run.
- **CSV export:**
  - The positions list ("115 positions" link on a result) has "Copy CSV" and "Download CSV" buttons. The script shows them to any logged-in user (`right: a5.uid ? [Copy CSV, Download CSV]`), with no trial check, and builds the file in the browser as `positions.csv`.
  - So it is available on the trial. I did not click either (no downloads).
  - Instead, the 115 T1a positions were read from the position-detail cards and saved to `/home/claude/research_notes/optionalpha_T1a_positions.csv`. Checks: 115 rows, closed P/L sums to $2,008, and the exit counts match the tool (45/62/8).

## Stage 1 summary (exits sprint) - STOPPED after 4 runs (superseded by "Stage 1 summary (complete)" below)

Run log: `/home/claude/research_notes/oa_stage1_runs.csv` (5 rows: 4 completed, 1 aborted). Labels: backtest, DEV period (2025-11-03 to 2026-06-30), fills MODELED by Option Alpha. P/L excludes OA's estimated fees.

- **Locked period:** the 88-date Excluded Dates list was applied to every run (stored as a comma list). Check on OA-S1-001: 86 trades, first 2025-11-04, last 2026-06-30, none on an excluded date. The Monthly P/L table shows only Nov 2025-Jun 2026. No Jul-Oct 2026 results were viewed.
- **How runs were submitted:** to save time, runs were started with the app's own client call (`a5.to.zdte.startTest`, the same call the "Run Backtest" button makes), using the same settings object the form builds. The saved runs show the intended settings in their sidebars (".45 delta", ORB 15, Above high, 12:00pm, first breakout, targets and stops, 35 min, $0.03 slippage).
- **Why it stopped:** after 4 quick starts (OA-S1-002 to 004 within 3 seconds), the 5th start (OA-S1-005, ORB15 call 10/30) was answered with a human-verification challenge: "Good morning. Are you human? | Verify", a math question. It was **not answered**. The pending request was cleared by reloading the page, and no OA-S1-005 backtest exists. Groups G1 (26 runs left) and G2-G7 were not run.

| Run | Setup | Side | Stop / target | Trades | Win rate | Avg win | Avg loss | PF | P/L | Max DD | Nov-Dec / Jan-Feb / Mar-Apr / May-Jun P/L |
|---|---|---|---|---|---|---|---|---|---|---|---|
| OA-S1-001 | SPY ORB15, .45d, latest 12:00 | call | -20% / +20% | 86 | 47.7% | $42 | -$35 | 1.09 | $136 | -$323 | +56 / +123 / +24 / -67 |
| OA-S1-002 | same | call | -20% / +40% | 86 | 31.4% | $70 | -$35 | 0.9 | -$212 | -$706 | +179 / -131 / -170 / -90 |
| OA-S1-003 | same | call | -20% / +60% | 86 | 26.7% | $99 | -$36 | 1.0 | $9 | -$734 | +258 / -20 / -340 / +111 |
| OA-S1-004 | same | call | -15% / +45% | 86 | 24.4% | $82 | -$28 | 0.95 | -$94 | -$618 | +167 / -75 / -108 / -78 |
| OA-S1-005 | same | call | -10% / +30% | not run (human-verification challenge) | | | | | | | |

Things that look odd, recorded as seen:
- All four runs have best win $243. That trade is 2026-02-20: debit $171, opened 10:01am, closed 10:02am at $4.14 (bid/ask 4.10-4.23), +142.11% on a 20% target, SPY 685.50 to 688.96 in one minute. In OA-S1-001 that one trade ($243) is larger than the run's total P/L ($136).
- Average losses (-$28 to -$36) are larger than the stop % of the average risk ($144). This is consistent with exits filling at the next 1-minute price (see Fact-finding section 2).

## Stage 1 summary (complete)

Run log: `/home/claude/research_notes/oa_stage1_runs.csv` (79 rows, OA-S1-001 to OA-S1-079). All numbers are **backtest, in-sample**: DEV window 2025-11-03 to 2026-06-30, fills MODELED by Option Alpha (mid +/- slippage, 1-minute checks). P/L excludes OA's estimated fees. The table and the criteria check below were built by code (`s1_table.py` in the session scratchpad) from the CSV.

- **Locked period:** the 88-date Excluded Dates list was on every run (each run's settings showed excl=88 before Run). No Jul-Oct 2026 results were read.
- **Runs:** 79 completed backtests: G1 30, G2 3, G3 4, G4 16, G5 4, G6 10, G7 12.
  - Two attempts (OA-S1-005 first try, OA-S1-058 first try) stopped at OA's human-verification box. Nick answered it both times, and both runs were then redone through the form; their log rows were replaced.
  - Runs 001-004 were started with the app's own client call (see the section above). Runs 005-079 were started with the normal form and the Run Backtest button, one at a time.
- **Setup choices (where the run list left room):**
  - **G3 "best G1 pair":** calls 20/60 (tied with 15/45 on PF, higher P/L), puts 10/30.
  - **Credit spreads (G6):**
    - Short strike is "$0.01 beyond the 60-minute range edge, or lower (put) / or higher (call)".
    - No profit target.
    - Stop is "-100% of credit".
    - Skips FOMC days.
    - Run order was SPX call before SPX put, and the iron condor with stop before without; IDs follow run order.
  - **Iron condor:** $2 wings (assumption; the run list gave no width).
  - **SPX:** not blocked by the trial.
  - **G7 base configs:** filters were run on 023 (ORB60 call 20/60) and 024 (ORB60 call 15/45). No G1 put config had PF > 1.1 (best was 020 at 1.04), so G7 puts were skipped.
  - **G7 filters as set in OA:**
    - Gap up: Gap % >= 0.01. Gap down: Gap % <= -0.01.
    - VIX below 20: max 19.99. VIX 20 or above: min 20. OA does not say which VIX reading it uses.
    - Side rule: SMA(20) "Above" (Moving averages menu), on calls only.
    - Skip events: "FOMC Meeting or CPI Release", which skips the entry that day.
- **G7 trade counts** (base 75 trades for each config):
  - Gap up: 37. Gap down: 38.
  - VIX < 20: 59. VIX >= 20: 16.
  - SPY > SMA20: 48.
  - Skip FOMC+CPI: 70.

**Configs meeting all three tests** (PF >= 1.25, PF at 2x slippage > 1.0, profitable in at least 3 of 4 two-month blocks):
- 023: SPY ORB60 call, 20/60 (2x rerun 031)
- 024: SPY ORB60 call, 15/45 (2x rerun 032)
- 025: SPY ORB60 call, 10/30 (2x rerun 033)

**PF >= 1.25 and 3+ profitable blocks, but no 2x-slippage run.** G2 covered G1 configs only. These are all variants of 023 and 024:
- 036
- 068, 072, 073
- 075, 076, 078, 079

**PF >= 1.25 but fewer than 3 profitable blocks:**
- 045: QQQ ORB60 put 10/30
- 071: 023 + VIX >= 20
- 077: 024 + VIX >= 20

**Odd things, recorded as seen:**
- **Slippage:** $0.06 slippage gave results identical to $0.03 (031-033 vs 023-025).
- **Time-exit runs:**
  - 037 (exit 3:50) is identical to 030.
  - 036 differs from 023 only in Jan-Feb (+24 vs +12).
- **Filter splits add up exactly to the base runs:**
  - 068+069 and 070+071: 75 trades, $484 (base 023).
  - 074+075 and 076+077: 75 trades, $384 (base 024).
- **Months with no trades:**
  - VIX >= 20 runs: 10 of 16 trades fall in March 2026, and there are no trades in May-Jun.
  - VIX < 20 and SMA20 runs: no trades in March 2026.
- **Credit spreads and the iron condor:**
  - Many exits are "EXPIRED" (settled) rather than closed at 3:25: 058 40/69, 060 33/58, 067 123/129.
  - OA estimated fees are large next to the credits:
    - XSP spreads (credit about $0.11-0.13): $131-$179.
    - SPX spreads: $159-$212. For 065 the fees ($211.72) are larger than its P/L ($114).
    - Iron condors: $585 / $427.
- **Losses larger than the stop:**
  - Debit runs: average losses are larger than the stop % (next-minute fills).
  - SPX with a -100% credit stop (062): worst loss -$331 on an average credit of $1.11.
- **Odd counts:**
  - 060: 44 wins + 13 losses = 57 of 58 trades.
  - Same rule, different trade counts: XSP 58 vs SPX 59 (call credit spread, break below low).
  - 056 shows a 30.7% win rate for 19W/43L.
- **Earlier finding:** the $243 best win on 2026-02-20 appears in several ORB15/ORB30 call runs (see above).
- **OA behavior:**
  - OA result IDs start with ZT2 (SPX), ZT3 (SPY), ZT4 (QQQ), ZT5 (XSP), ZT6 (IWM).
  - An OA "App update in progress" reload happened during the 077 read. After it, the IDs are one digit shorter (078, 079).

Columns: stop/tgt % is the stop (% of debit or credit) and the profit target (% return); "none" means not set. Blocks are Nov-Dec 2025 / Jan-Feb / Mar-Apr / May-Jun 2026 P/L in $. PF 2x is filled only where G2 reran the config at $0.06.

| # | grp | sym | setup | side | stop/tgt % | filters | trades | WR | avg win | avg loss | PF | PF 2x | P/L | max DD | blocks ND/JF/MA/MJ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 001 | G1 | SPY | ORB15 | call | 20/20 | - | 86 | 47.7% | 42 | -35 | 1.09 |  | $136 | -323 | +56 / +123 / +24 / -67 |
| 002 | G1 | SPY | ORB15 | call | 20/40 | - | 86 | 31.4% | 70 | -35 | 0.90 |  | -$212 | -706 | +179 / -131 / -170 / -90 |
| 003 | G1 | SPY | ORB15 | call | 20/60 | - | 86 | 26.7% | 99 | -36 | 1.00 |  | $9 | -734 | +258 / -20 / -340 / +111 |
| 004 | G1 | SPY | ORB15 | call | 15/45 | - | 86 | 24.4% | 82 | -28 | 0.95 |  | -$94 | -618 | +167 / -75 / -108 / -78 |
| 005 | G1 | SPY | ORB15 | call | 10/30 | - | 86 | 24.4% | 62 | -22 | 0.90 |  | -$139 | -491 | +201 / +5 / -92 / -253 |
| 006 | G1 | SPY | ORB15 | put | 20/20 | - | 76 | 40.8% | 46 | -42 | 0.76 |  | -$443 | -654 | -330 / +265 / -30 / -348 |
| 007 | G1 | SPY | ORB15 | put | 20/40 | - | 76 | 31.6% | 73 | -43 | 0.80 |  | -$452 | -1042 | -71 / +431 / -505 / -307 |
| 008 | G1 | SPY | ORB15 | put | 20/60 | - | 76 | 23.7% | 104 | -42 | 0.78 |  | -$542 | -1378 | -86 / +619 / -586 / -489 |
| 009 | G1 | SPY | ORB15 | put | 15/45 | - | 76 | 27.6% | 86 | -37 | 0.90 |  | -$209 | -863 | +61 / +316 / -371 / -215 |
| 010 | G1 | SPY | ORB15 | put | 10/30 | - | 76 | 23.7% | 64 | -27 | 0.72 |  | -$439 | -660 | -132 / -74 / -145 / -88 |
| 011 | G1 | SPY | ORB30 | call | 20/20 | - | 91 | 46.2% | 36 | -34 | 0.91 |  | -$157 | -388 | -324 / +347 / -140 / -40 |
| 012 | G1 | SPY | ORB30 | call | 20/40 | - | 91 | 30.8% | 63 | -34 | 0.83 |  | -$362 | -557 | -416 / +150 / -47 / -49 |
| 013 | G1 | SPY | ORB30 | call | 20/60 | - | 91 | 25.3% | 84 | -33 | 0.85 |  | -$336 | -513 | -355 / +157 / -22 / -116 |
| 014 | G1 | SPY | ORB30 | call | 15/45 | - | 91 | 25.3% | 67 | -27 | 0.83 |  | -$319 | -655 | -280 / +266 / -249 / -56 |
| 015 | G1 | SPY | ORB30 | call | 10/30 | - | 91 | 30.8% | 48 | -21 | 1.01 |  | $10 | -474 | -139 / +418 / -176 / -93 |
| 016 | G1 | SPY | ORB30 | put | 20/20 | - | 67 | 44.8% | 48 | -38 | 1.02 |  | $24 | -226 | +26 / +79 / -82 / +1 |
| 017 | G1 | SPY | ORB30 | put | 20/40 | - | 67 | 34.3% | 75 | -38 | 1.02 |  | $42 | -490 | +34 / +263 / -102 / -153 |
| 018 | G1 | SPY | ORB30 | put | 20/60 | - | 67 | 23.9% | 103 | -40 | 0.81 |  | -$385 | -860 | -63 / +282 / -573 / -31 |
| 019 | G1 | SPY | ORB30 | put | 15/45 | - | 67 | 29.9% | 73 | -33 | 0.93 |  | -$108 | -383 | -43 / +165 / -156 / -74 |
| 020 | G1 | SPY | ORB30 | put | 10/30 | - | 67 | 31.3% | 57 | -25 | 1.04 |  | $47 | -252 | 0 / +163 / -37 / -79 |
| 021 | G1 | SPY | ORB60 | call | 20/20 | - | 75 | 46.7% | 29 | -30 | 0.86 |  | -$167 | -313 | +30 / -150 / -47 / 0 |
| 022 | G1 | SPY | ORB60 | call | 20/40 | - | 75 | 37.3% | 53 | -30 | 1.04 |  | $63 | -268 | +100 / -58 / -95 / +116 |
| 023 | G1 | SPY | ORB60 | call | 20/60 | - | 75 | 34.7% | 75 | -30 | 1.33 | 1.33 | $484 | -268 | +252 / +12 / -1 / +221 |
| 024 | G1 | SPY | ORB60 | call | 15/45 | - | 75 | 34.7% | 59 | -24 | 1.33 | 1.33 | $384 | -165 | +184 / +16 / -65 / +249 |
| 025 | G1 | SPY | ORB60 | call | 10/30 | - | 75 | 36.0% | 41 | -18 | 1.30 | 1.30 | $257 | -131 | +84 / -7 / +3 / +177 |
| 026 | G1 | SPY | ORB60 | put | 20/20 | - | 62 | 50.0% | 36 | -40 | 0.91 |  | -$115 | -458 | +26 / -72 / -152 / +83 |
| 027 | G1 | SPY | ORB60 | put | 20/40 | - | 62 | 35.5% | 63 | -40 | 0.87 |  | -$200 | -544 | +8 / +28 / -150 / -86 |
| 028 | G1 | SPY | ORB60 | put | 20/60 | - | 62 | 25.8% | 99 | -39 | 0.88 |  | -$209 | -629 | +37 / -39 / -77 / -130 |
| 029 | G1 | SPY | ORB60 | put | 15/45 | - | 62 | 29.0% | 72 | -33 | 0.88 |  | -$176 | -374 | -74 / +112 / -83 / -131 |
| 030 | G1 | SPY | ORB60 | put | 10/30 | - | 62 | 29.0% | 56 | -23 | 1.00 |  | $2 | -311 | +15 / +56 / -118 / +49 |
| 031 | G2 | SPY | ORB60 | call | 20/60 | slip $0.06 | 75 | 34.7% | 75 | -30 | 1.33 | 1.33 | $484 | -268 | +252 / +12 / -1 / +221 |
| 032 | G2 | SPY | ORB60 | call | 15/45 | slip $0.06 | 75 | 34.7% | 59 | -24 | 1.33 | 1.33 | $384 | -165 | +184 / +16 / -65 / +249 |
| 033 | G2 | SPY | ORB60 | call | 10/30 | slip $0.06 | 75 | 36.0% | 41 | -18 | 1.30 | 1.30 | $257 | -131 | +84 / -7 / +3 / +177 |
| 034 | G3 | SPY | ORB60 (latest entry 11:30) | call | 20/20 | - | 69 | 47.8% | 29 | -30 | 0.89 |  | -$120 | -342 | +90 / -146 / -64 / 0 |
| 035 | G3 | SPY | ORB60 (latest entry 11:30) | put | 20/20 | - | 60 | 50.0% | 36 | -41 | 0.89 |  | -$128 | -478 | +41 / -72 / -180 / +83 |
| 036 | G3 | SPY | ORB60 exit 3:50 | call | 20/60 | - | 75 | 34.7% | 75 | -30 | 1.34 |  | $496 | -256 | +252 / +24 / -1 / +221 |
| 037 | G3 | SPY | ORB60 exit 3:50 | put | 10/30 | - | 62 | 29.0% | 56 | -23 | 1.00 |  | $2 | -311 | +15 / +56 / -118 / +49 |
| 038 | G4 | QQQ | ORB30 | call | 20/40 | - | 85 | 27.1% | 69 | -45 | 0.57 |  | -$1,218 | -1439 | -482 / -308 / -336 / -92 |
| 039 | G4 | QQQ | ORB30 | call | 20/60 | - | 85 | 20.0% | 95 | -45 | 0.53 |  | -$1,453 | -1453 | -438 / -374 / -225 / -416 |
| 040 | G4 | QQQ | ORB30 | put | 20/40 | - | 74 | 31.1% | 85 | -49 | 0.78 |  | -$538 | -740 | -19 / -152 / +49 / -416 |
| 041 | G4 | QQQ | ORB30 | put | 10/30 | - | 74 | 20.3% | 89 | -32 | 0.71 |  | -$551 | -772 | +24 / -295 / -85 / -195 |
| 042 | G4 | QQQ | ORB60 | call | 20/40 | - | 75 | 26.7% | 69 | -36 | 0.71 |  | -$578 | -841 | -27 / -274 / -370 / +93 |
| 043 | G4 | QQQ | ORB60 | call | 20/60 | - | 75 | 22.7% | 90 | -36 | 0.73 |  | -$580 | -848 | -62 / -243 / -331 / +56 |
| 044 | G4 | QQQ | ORB60 | put | 20/40 | - | 61 | 32.8% | 91 | -48 | 0.93 |  | -$141 | -622 | +103 / -127 / -243 / +126 |
| 045 | G4 | QQQ | ORB60 | put | 10/30 | - | 61 | 36.1% | 73 | -33 | 1.26 |  | $333 | -500 | +238 / -82 / -43 / +220 |
| 046 | G4 | IWM | ORB30 | call | 20/40 | - | 83 | 39.8% | 35 | -22 | 1.04 |  | $44 | -245 | -47 / +152 / -94 / +33 |
| 047 | G4 | IWM | ORB30 | call | 20/60 | - | 83 | 33.7% | 49 | -21 | 1.17 |  | $200 | -263 | +36 / +260 / -7 / -89 |
| 048 | G4 | IWM | ORB30 | put | 20/40 | - | 70 | 34.3% | 38 | -23 | 0.87 |  | -$132 | -309 | -97 / +92 / -78 / -49 |
| 049 | G4 | IWM | ORB30 | put | 10/30 | - | 70 | 27.1% | 27 | -16 | 0.63 |  | -$307 | -345 | -56 / -86 / -123 / -42 |
| 050 | G4 | IWM | ORB60 | call | 20/40 | - | 69 | 34.8% | 31 | -19 | 0.86 |  | -$122 | -259 | +67 / -132 / +49 / -106 |
| 051 | G4 | IWM | ORB60 | call | 20/60 | - | 69 | 29.0% | 48 | -19 | 1.03 |  | $26 | -269 | +163 / -90 / +97 / -144 |
| 052 | G4 | IWM | ORB60 | put | 20/40 | - | 59 | 35.6% | 32 | -19 | 0.93 |  | -$50 | -202 | +47 / -68 / +26 / -55 |
| 053 | G4 | IWM | ORB60 | put | 10/30 | - | 59 | 32.2% | 26 | -13 | 0.93 |  | -$38 | -157 | +17 / -65 / +46 / -36 |
| 054 | G5 | SPY | ORB60 debit spr $2w | call | 50/100 | - | 75 | 41.3% | 71 | -41 | 1.23 |  | $412 | -522 | +327 / -278 / +130 / +233 |
| 055 | G5 | SPY | ORB60 debit spr $2w | call | 30/60 | - | 75 | 34.7% | 49 | -28 | 0.91 |  | -$121 | -435 | +14 / -358 / +175 / +48 |
| 056 | G5 | SPY | ORB60 debit spr $2w | put | 50/100 | - | 62 | 30.7% | 71 | -38 | 0.82 |  | -$289 | -749 | -241 / -213 / -259 / +424 |
| 057 | G5 | SPY | ORB60 debit spr $2w | put | 30/60 | - | 62 | 29.0% | 44 | -26 | 0.69 |  | -$354 | -537 | -101 / -91 / -196 / +34 |
| 058 | G6 | XSP | ORB60 credit spr $2w | put cr (brk high) | none/none | skip FOMC | 69 | 82.6% | 9 | -79 | 0.57 |  | -$407 | -431 | -79 / -141 / +141 / -328 |
| 059 | G6 | XSP | ORB60 credit spr $2w | put cr (brk high) | 100/none | skip FOMC | 69 | 43.5% | 12 | -14 | 0.65 |  | -$193 | -244 | -21 / -148 / +27 / -51 |
| 060 | G6 | XSP | ORB60 credit spr $2w | call cr (brk low) | none/none | skip FOMC | 58 | 75.9% | 12 | -68 | 0.59 |  | -$361 | -396 | -197 / +71 / -49 / -186 |
| 061 | G6 | XSP | ORB60 credit spr $2w | call cr (brk low) | 100/none | skip FOMC | 58 | 37.9% | 13 | -16 | 0.49 |  | -$298 | -329 | -70 / -135 / -41 / -52 |
| 062 | G6 | SPX | ORB60 credit spr $10w | call cr (brk low) | 100/none | skip FOMC | 59 | 52.5% | 93 | -144 | 0.72 |  | -$1,136 | -1558 | -790 / -243 / -71 / -32 |
| 063 | G6 | SPX | ORB60 credit spr $10w | call cr (brk low) | none/none | skip FOMC | 59 | 76.3% | 95 | -421 | 0.72 |  | -$1,627 | -2259 | -1733 / +639 / +199 / -732 |
| 064 | G6 | SPX | ORB60 credit spr $10w | put cr (brk high) | none/none | skip FOMC | 69 | 79.7% | 70 | -412 | 0.66 |  | -$1,942 | -2181 | -255 / -751 / +908 / -1844 |
| 065 | G6 | SPX | ORB60 credit spr $10w | put cr (brk high) | 100/none | skip FOMC | 69 | 58.0% | 75 | -100 | 1.04 |  | $114 | -1033 | +125 / -466 / +352 / +103 |
| 066 | G6 | XSP | 10:00 iron condor .20d $2w | IC | 100/none | skip FOMC | 129 | 54.3% | 43 | -56 | 0.92 |  | -$275 | -729 | -92 / +392 / -142 / -433 |
| 067 | G6 | XSP | 10:00 iron condor .20d $2w | IC | none/none | skip FOMC | 129 | 69.8% | 43 | -115 | 0.86 |  | -$628 | -1644 | -250 / +786 / -448 / -716 |
| 068 | G7 | SPY | ORB60 | call | 20/60 | gap up only | 37 | 37.8% | 68 | -28 | 1.46 |  | $300 | -179 | +151 / -14 / +20 / +143 |
| 069 | G7 | SPY | ORB60 | call | 20/60 | gap down only, reverse side | 38 | 31.6% | 83 | -31 | 1.23 |  | $184 | -210 | +101 / +26 / -21 / +78 |
| 070 | G7 | SPY | ORB60 | call | 20/60 | VIX below 20 | 59 | 33.9% | 64 | -27 | 1.18 |  | $198 | -186 | +23 / +92 / -138 / +221 |
| 071 | G7 | SPY | ORB60 | call | 20/60 | VIX 20 or above | 16 | 37.5% | 113 | -39 | 1.73 |  | $286 | -244 | +229 / -80 / +137 / 0 |
| 072 | G7 | SPY | ORB60 | call | 20/60 | SPY > SMA20 | 48 | 35.4% | 60 | -25 | 1.31 |  | $241 | -176 | +83 / +136 / -138 / +160 |
| 073 | G7 | SPY | ORB60 | call | 20/60 | skip FOMC and CPI days | 70 | 34.3% | 74 | -29 | 1.32 |  | $434 | -230 | +75 / +50 / +88 / +221 |
| 074 | G7 | SPY | ORB60 | call | 15/45 | gap up only | 37 | 35.1% | 53 | -23 | 1.24 |  | $134 | -191 | +111 / -17 / -149 / +189 |
| 075 | G7 | SPY | ORB60 | call | 15/45 | gap down only, reverse side | 38 | 34.2% | 66 | -24 | 1.41 |  | $250 | -135 | +73 / +33 / +84 / +60 |
| 076 | G7 | SPY | ORB60 | call | 15/45 | VIX below 20 | 59 | 35.6% | 50 | -22 | 1.26 |  | $217 | -136 | +3 / +77 / -112 / +249 |
| 077 | G7 | SPY | ORB60 | call | 15/45 | VIX 20 or above | 16 | 31.3% | 99 | -30 | 1.51 |  | $167 | -169 | +181 / -61 / +47 / 0 |
| 078 | G7 | SPY | ORB60 | call | 15/45 | SPY > SMA20 | 48 | 37.5% | 47 | -20 | 1.40 |  | $240 | -136 | +63 / +133 / -112 / +156 |
| 079 | G7 | SPY | ORB60 | call | 15/45 | skip FOMC and CPI days | 70 | 34.3% | 59 | -23 | 1.35 |  | $369 | -160 | +60 / +54 / +6 / +249 |

## Optimizer (Strategy Optimizer on Stage 1 runs, 2026-10-31)

All numbers here are **backtest, in-sample**: DEV window 2025-11-03 to 2026-06-30, with the 88 locked dates excluded. Fills are MODELED by Option Alpha, and P/L excludes fees.

The Strategy Optimizer does not run new backtests. It filters the trades a backtest already has, and every filter range it suggests was chosen by looking at those same trades. The only new backtests are the "Apply Filters" runs (080-087) and the locked copy of T1a (088). They are all logged in `oa_stage1_runs.csv`.

**Settings.** On every run the optimizer was set to: Optimize for Return on DD, Level Balanced, Min trades 30% (the panel's defaults). Each run was started with the "Run Optimizer" button. "View N Additional Results" was opened every time it appeared.

**What it was run on.** 19 base runs: 001, 003, 015, 016, 017, 020, 022, 023, 024, 025, 030, 036, 045, 046, 047, 051, 054, 065, and 088 (in place of T1a).
- **Scope changes:** the run list changed twice during the task (first to PF >= 1.25 only, then to every run with P/L above $0). The final list was used.
- **030 added:** its P/L is +$2, which meets the rule. It was not on the coordinator's list.
- **Not run:** 031-033 and 037 (duplicates) and 068-079 (already filtered).
- **023:** rerun so its Apply Filters buttons could be used. The results match the coordinator's numbers exactly.

**T1a.** T1a (ZT31793434719013510129) has no excluded dates, so its trades run through Oct 2026. Optimizing it would have tuned filters on the locked Jul-Oct 2026 period.
- Instead, T1a's exact settings were rerun through the form with the 88 locked dates excluded. That run is OA-S1-088 (75 trades, PF 1.55, P/L $1,619), and the optimizer was run on it.
- The original T1a was not optimized.

**How "Apply Filters" works.** This was read from the app's own script (`bots.v2587.js`, `applyFilters` / `genOpts`).
- The button copies the base backtest's stored settings, adds the suggested filters, and offers three choices:
  - "Edit this backtest with the new filters"
  - "Create a new backtest with these filters"
  - "Compare these filters to the original backtest"
- Only "Create a new backtest" was used, so no saved run was edited.
- That choice asks for a description and then starts the run directly. There is no settings form and no "Run Backtest" step.
- So the 88 locked dates could not be checked before the run started. Instead, each new run's stored settings were opened in a variation form *before its results were read*, then the form was closed without running. All 8 Apply Filters runs showed 88 excluded dates (2025-10-30 to 2026-10-30), with the filter values as suggested.
- When a variation is shown under several labels (for example "Best · Simplest · Most Consistent"), Simplest and Most consistent are the same filters. For 047 and 054 they were, so each got one backtest (086, 087). That gives 8 Apply Filters runs instead of 10.

### Optimizer suggestions (all variations shown, including "Additional")

Variation labels are shortened ("Best" = Best Return on Drawdown, "Highest RoDD" = Highest Return on Drawdown). Every variation on every run was labeled **Low Confidence**. "Kept" is OA's "% of trades retained".

| Base run | Variation | Conf. | Trades | WR | PF | P/L | Max DD | RoDD | Kept | Filters (exact) |
|---|---|---|---|---|---|---|---|---|---|---|
| 023 SPY ORB60 call 20/60 (base 75 tr, PF 1.33, P/L $484, DD -$268) | Best + Most consistent | Low | 46 | 43.5% | 2.18 | $784 | -$110 | 713% | 61% | VIX CHANGE -3 to -0.01; OPEN CHG % 0% to 0.75%; STOCH(14,3,3) 20 or greater |
|  | Highest RoDD | Low | 31 | 48.4% | 2.40 | $575 | -$69 | 833% | 41% | VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; CHANGE % -0.25% to 2%; OPEN CHG % 0.5% or less |
|  | Simplest | Low | 50 | 40% | 1.75 | $622 | -$110 | 565% | 67% | VIX CHANGE -3 to -0.01 |
|  | Additional 1 | Low | 48 | 41.7% | 1.98 | $720 | -$110 | 655% | 64% | VIX CHANGE -3 to -0.01; OPEN CHG % 0% to 0.75% |
|  | Additional 2 | Low | 46 | 43.5% | 2.18 | $784 | -$110 | 713% | 61% | VIX CHANGE -3 or greater; VIX CHANGE % -0.01% or less; OPEN CHG % 0% to 0.75%; STOCH(14,3,3) 20 or greater |
|  | Additional 3 | Low | 37 | 45.9% | 2.25 | $618 | -$93 | 665% | 49% | VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; CHANGE % -0.25% to 2%; OPEN CHG % 0.75% or less; MFI(14) 30 or greater |
|  | Additional 4 | Low | 37 | 45.9% | 2.25 | $618 | -$93 | 665% | 49% | VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; CHANGE % -0.25% to 2%; OPEN CHG % 0.75% or less; MFI(14) 30 to 89.99 |
|  | Additional 5 | Low | 48 | 41.7% | 1.98 | $720 | -$110 | 655% | 64% | VIX CHANGE -3 or greater; VIX CHANGE % -0.01% or less; OPEN CHG % 0% to 0.75% |
| 024 SPY ORB60 call 15/45 (base 75 tr, PF 1.33, P/L $384, DD -$165) | Best + Highest RoDD + Most consistent | Low | 34 | 44.1% | 2.45 | $629 | -$66 | 953% | 45% | DAY OF WEEK Mon/Wed/Thu/Fri; CHANGE % -1% to 2%; OPEN CHG % 0% to 0.75%; MACD(12,26,9) -10 to 9.99; MOMENTUM(10) -20 to 39.99 |
|  | Simplest | Low | 55 | 43.6% | 2.09 | $754 | -$103 | 732% | 73% | CHANGE % -1% to 1.75%; OPEN CHG % 0% to 0.75%; MOMENTUM(10) -20 to 29.99 |
|  | Additional 1 | Low | 43 | 44.2% | 2.24 | $684 | -$98 | 698% | 57% | CHANGE % -1% to 1.75%; OPEN CHG % 0% to 0.75%; MOMENTUM(10) -20 to 19.99; RSI(14) 69.99 or less |
|  | Additional 2 | Low | 53 | 43.4% | 2.03 | $685 | -$103 | 665% | 71% | CHANGE % -1% to 1.75%; OPEN CHG % 0% to 0.75%; MOMENTUM(10) -30 to 29.99; RSI(14) 40 or greater |
|  | Additional 3 | Low | 49 | 44.9% | 2.15 | $665 | -$103 | 646% | 65% | CHANGE % -1% to 1.75%; OPEN CHG % 0% to 0.75%; MOMENTUM(10) -30 to 29.99; RSI(14) 40 or greater; STOCH RSI(14,14,3,3) 20 or greater |
|  | Additional 4 | Low | 35 | 45.7% | 2.63 | $684 | -$98 | 698% | 47% | CHANGE % -1% to 1.75%; OPEN CHG % 0% to 0.75%; MOMENTUM(10) -20 to 19.99; RSI(14) 59.99 or less |
|  | Additional 5 | Low | 51 | 41.2% | 1.94 | $642 | -$103 | 623% | 68% | DAY OF WEEK Mon/Wed/Thu/Fri; IV RANK 10 to 49.99; CHANGE % -1% to 2%; OPEN CHG % 0.75% or less |
| 025 SPY ORB60 call 10/30 (base 75 tr, PF 1.30, P/L $257, DD -$131) | Best + Most consistent | Low | 35 | 42.9% | 1.96 | $258 | -$101 | 255% | 47% | VIX 19.99 or less; VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; OPEN CHG % 0.75% or less |
|  | Highest RoDD | Low | 45 | 42.2% | 1.77 | $293 | -$101 | 290% | 60% | VIX 19.99 or less; VIX CHANGE % 0.99% or less; OPEN CHG % 0% to 0.75% |
|  | Simplest | Low | 37 | 40.5% | 1.69 | $215 | -$101 | 213% | 49% | VIX 19.99 or less; VIX CHANGE % 0.99% or less; IV RANK 39.99 or less |
|  | Additional 1 | Low | 39 | 41% | 1.82 | $249 | -$101 | 247% | 52% | VIX 19.99 or less; VIX CHANGE % 2.99% or less; IV RANK 39.99 or less; OPEN CHG % 0.75% or less |
|  | Additional 2 | Low | 32 | 43.8% | 1.98 | $238 | -$101 | 236% | 43% | VIX 19.99 or less; VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; OPEN CHG % 0.75% or less; MOMENTUM(10) -30 to 39.99 |
|  | Additional 3 | Low | 32 | 43.8% | 1.98 | $238 | -$101 | 236% | 43% | VIX 19.99 or less; VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; OPEN CHG % 0.75% or less; MOMENTUM(10) -20 to 39.99 |
|  | Additional 4 | Low | 38 | 39.5% | 1.74 | $225 | -$101 | 223% | 51% | VIX 19.99 or less; VIX CHANGE % 1.99% or less; IV RANK 39.99 or less; OPEN CHG % 0.75% or less |
|  | Additional 5 | Low | 41 | 39% | 1.60 | $206 | -$101 | 204% | 55% | VIX 19.99 or less; VIX CHANGE % 2.99% or less; IV RANK 39.99 or less |
| 036 SPY ORB60 call 20/60 exit 3:50 (base 75 tr, PF 1.34, P/L $496, DD -$256) | Best + Most consistent | Low | 46 | 43.5% | 2.19 | $796 | -$110 | 724% | 61% | VIX CHANGE -3 to -0.01; OPEN CHG % 0% to 0.75%; STOCH(14,3,3) 20 or greater |
|  | Highest RoDD | Low | 31 | 48.4% | 2.43 | $587 | -$69 | 851% | 41% | VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; CHANGE % -0.25% to 2%; OPEN CHG % 0.5% or less |
|  | Simplest | Low | 50 | 40% | 1.76 | $634 | -$110 | 576% | 67% | VIX CHANGE -3 to -0.01 |
|  | Additional 1 | Low | 48 | 41.7% | 2.00 | $732 | -$110 | 665% | 64% | VIX CHANGE -3 to -0.01; OPEN CHG % 0% to 0.75% |
|  | Additional 2 | Low | 46 | 43.5% | 2.19 | $796 | -$110 | 724% | 61% | VIX CHANGE -3 or greater; VIX CHANGE % -0.01% or less; OPEN CHG % 0% to 0.75%; STOCH(14,3,3) 20 or greater |
|  | Additional 3 | Low | 37 | 45.9% | 2.28 | $630 | -$93 | 677% | 49% | VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; CHANGE % -0.25% to 2%; OPEN CHG % 0.75% or less; MFI(14) 30 or greater |
|  | Additional 4 | Low | 37 | 45.9% | 2.28 | $630 | -$93 | 677% | 49% | VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; CHANGE % -0.25% to 2%; OPEN CHG % 0.75% or less; MFI(14) 30 to 89.99 |
|  | Additional 5 | Low | 48 | 41.7% | 2.00 | $732 | -$110 | 665% | 64% | VIX CHANGE -3 or greater; VIX CHANGE % -0.01% or less; OPEN CHG % 0% to 0.75% |
| 001 SPY ORB15 call 20/20 (base 86 tr, PF 1.09, P/L $136, DD -$323) | Best + Highest RoDD + Most consistent | Low | 45 | 60% | 1.88 | $573 | -$182 | 315% | 52% | IV RANK 39.99 or less; CHANGE SD -2 to 0.7499; OPEN CHG % 0% to 0.5%; CMO(9) 59.99 or less; MACD(12,26,9) -15 to 9.99 |
|  | Simplest | Low | 44 | 56.8% | 1.72 | $485 | -$182 | 266% | 51% | IV RANK 39.99 or less; CHANGE SD -2 to 0.7499; OPEN CHG % 0% to 0.5%; CMO(9) 39.99 or less |
|  | Additional 1 | Low | 46 | 58.7% | 1.81 | $548 | -$182 | 301% | 53% | IV RANK 39.99 or less; CHANGE SD -2 to 0.7499; OPEN CHG % 0% to 0.5%; CMO(9) 59.99 or less; RSI(14) 69.99 or less |
|  | Additional 2 | Low | 39 | 61.5% | 2.09 | $561 | -$182 | 308% | 45% | IV RANK 39.99 or less; CHANGE SD -2 to 0.7499; OPEN CHG % 0% to 0.5%; CMO(9) 59.99 or less; MACD(12,26,9) -5 to 9.99 |
|  | Additional 3 | Low | 45 | 57.8% | 1.71 | $495 | -$164 | 302% | 52% | IV RANK 39.99 or less; CHANGE % 0.75% or less; CHANGE SD -2 to 0.9999; OPEN CHG % 0% to 0.5%; CMO(9) 39.99 or less; MACD(12,26,9) -15 to 4.99 |
| 003 SPY ORB15 call 20/60 (base 86 tr, PF 1.00, P/L $9, DD -$734) | Best + Highest RoDD + Most consistent + Simplest | Low | 47 | 44.7% | 2.39 | $1,190 | -$243 | 490% | 55% | DAY OF WEEK Mon/Tue/Wed/Fri; CHANGE % 0.75% or less; CHANGE SD -2 to 0.7499; OPEN CHG % 0% to 0.5%; CMO(9) 59.99 or less; MACD(12,26,9) -5 to 20 |
|  | Additional 1 | Low | 48 | 43.8% | 2.32 | $1,164 | -$243 | 479% | 56% | DAY OF WEEK Mon/Tue/Wed/Fri; CHANGE % 0.75% or less; CHANGE SD -2 to 0.7499; OPEN CHG % 0% to 0.5%; MACD(12,26,9) -5 to 20; MFI(14) 69.99 or less |
| 015 SPY ORB30 call 10/30 (base 91 tr, PF 1.01, P/L $10, DD -$474) | Best + Most consistent + Simplest | Low | 31 | 45.2% | 2.38 | $447 | -$175 | 255% | 34% | DAY OF WEEK Mon/Tue/Wed/Fri; VIX CHANGE -3 or greater; IV RANK 29.99 or less; CHANGE SD 0.9999 or less |
|  | Highest RoDD | Low | 30 | 46.7% | 2.48 | $460 | -$175 | 263% | 33% | DAY OF WEEK Mon/Tue/Wed/Fri; VIX CHANGE -2 or greater; IV RANK 29.99 or less; CHANGE SD 0.9999 or less; RSI(14) 69.99 or less |
|  | Additional 1 | Low | 31 | 45.2% | 2.38 | $447 | -$175 | 255% | 34% | DAY OF WEEK Mon/Tue/Wed/Fri; VIX CHANGE -3 to 4.99; IV RANK 29.99 or less; CHANGE SD 0.9999 or less |
|  | Additional 2 | Low | 30 | 46.7% | 2.48 | $460 | -$175 | 263% | 33% | DAY OF WEEK Mon/Tue/Wed/Fri; VIX CHANGE -2 or greater; IV RANK 29.99 or less; CHANGE SD 0.9999 or less; RSI(14) 40 to 69.99 |
| 016 SPY ORB30 put 20/20 (base 67 tr, PF 1.02, P/L $24, DD -$226) | Best + Highest RoDD + Most consistent + Simplest | Low | 29 | 72.4% | 3.55 | $719 | -$57 | 1,261% | 43% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX CHANGE 0 or greater; VIX CHANGE % 1% or greater; CHANGE % -1.25% or greater; CMO(9) 39.99 or less; MOMENTUM(10) -20 to 50 |
|  | Additional 1 | Low | 29 | 72.4% | 3.55 | $719 | -$57 | 1,261% | 43% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX CHANGE 0 or greater; VIX CHANGE % 1% or greater; CHANGE % -1.25% or greater; CMO(9) 39.99 or less; MOMENTUM(10) -20 to 39.99 |
| 017 SPY ORB30 put 20/40 (base 67 tr, PF 1.02, P/L $42, DD -$490) | Best + Highest RoDD + Most consistent + Simplest | Low | 24 | 58.3% | 2.89 | $676 | -$59 | 1,146% | 36% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX CHANGE 0 to 3.99; VIX CHANGE % 1% or greater; IV RANK 39.99 or less; CMO(9) 39.99 or less; MOMENTUM(10) -20 to 50 |
|  | Additional 1 | Low | 24 | 58.3% | 2.89 | $676 | -$59 | 1,146% | 36% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX CHANGE 0 to 3.99; VIX CHANGE % 1% or greater; IV RANK 39.99 or less; CMO(9) 39.99 or less; MOMENTUM(10) -20 to 39.99 |
|  | Additional 2 | Low | 24 | 58.3% | 2.89 | $676 | -$59 | 1,146% | 36% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX CHANGE 0 to 3.99; VIX CHANGE % 1% or greater; IV RANK 39.99 or less; CMO(9) -40 to 39.99; MOMENTUM(10) -20 to 50 |
|  | Additional 3 | Low | 24 | 58.3% | 2.89 | $676 | -$59 | 1,146% | 36% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX CHANGE 0 to 3.99; VIX CHANGE % 1% or greater; IV RANK 39.99 or less; CMO(9) 39.99 or less; MOMENTUM(10) -20 to 29.99 |
|  | Additional 4 | Low | 24 | 58.3% | 2.89 | $676 | -$59 | 1,146% | 36% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX CHANGE % 1% or greater; IV RANK 10 to 39.99; CHANGE % -1.25% or greater; CMO(9) 39.99 or less; MOMENTUM(10) -20 to 50 |
|  | Additional 5 | Low | 24 | 58.3% | 2.89 | $676 | -$59 | 1,146% | 36% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX CHANGE % 1% or greater; IV RANK 10 to 39.99; CHANGE % -1.25% or greater; CMO(9) 39.99 or less; MOMENTUM(10) -20 to 39.99 |
| 020 SPY ORB30 put 10/30 (base 67 tr, PF 1.04, P/L $47, DD -$252) | Best + Most consistent + Simplest | Low | 25 | 48% | 2.53 | $377 | -$82 | 460% | 37% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX 24.99 or less; VIX CHANGE % -2% or greater; IV RANK 39.99 or less; CHANGE % -0.5% or greater |
|  | Highest RoDD | Low | 24 | 50% | 2.69 | $392 | -$82 | 478% | 36% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX 24.99 or less; VIX CHANGE % -2% or greater; IV RANK 39.99 or less; CHANGE % -0.5% or greater; CMO(9) 39.99 or less |
|  | Additional 1 | Low | 24 | 50% | 2.69 | $392 | -$82 | 478% | 36% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX 24.99 or less; VIX CHANGE % -2% or greater; IV RANK 39.99 or less; CHANGE % -0.5% or greater; CMO(9) -40 to 39.99 |
| 022 SPY ORB60 call 20/40 (base 75 tr, PF 1.04, P/L $63, DD -$268) | Best + Highest RoDD + Most consistent + Simplest | Low | 40 | 47.5% | 1.73 | $377 | -$106 | 356% | 53% | VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; CHANGE % -0.25% to 1.25% |
|  | Additional 1 | Low | 40 | 47.5% | 1.73 | $377 | -$106 | 356% | 53% | VIX CHANGE -3 or greater; VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; CHANGE % -0.25% to 2% |
|  | Additional 2 | Low | 40 | 47.5% | 1.73 | $377 | -$106 | 356% | 53% | VIX CHANGE -3 or greater; VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; CHANGE % -0.25% to 1.75% |
|  | Additional 3 | Low | 40 | 47.5% | 1.73 | $377 | -$106 | 356% | 53% | VIX CHANGE 1.99 or less; VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; CHANGE % -0.25% to 1.25% |
|  | Additional 4 | Low | 40 | 47.5% | 1.73 | $377 | -$106 | 356% | 53% | VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; CHANGE % -0.25% or greater; CHANGE SD 1.999 or less |
|  | Additional 5 | Low | 40 | 47.5% | 1.73 | $377 | -$106 | 356% | 53% | VIX CHANGE % 0.99% or less; IV RANK 39.99 or less; CHANGE % -0.25% or greater; CHANGE SD -2 to 1.999 |
| 030 SPY ORB60 put 10/30 (base 62 tr, PF 1.00, P/L $2, DD -$311) | Best + Highest RoDD + Most consistent + Simplest | Low | 23 | 47.8% | 2.82 | $432 | -$58 | 745% | 37% | DAY OF WEEK Mon/Tue/Thu/Fri; VIX CHANGE -2 to 1.99; CHANGE SD -1 or greater; ADX(14) 29.99 or less; CCI(20) 99.99 or less; MACD(12,26,9) -15 to 9.99 |
|  | Additional 1 | Low | 23 | 47.8% | 2.82 | $432 | -$58 | 745% | 37% | DAY OF WEEK Mon/Tue/Thu/Fri; VIX CHANGE -2 to 1.99; CHANGE SD -1 or greater; ADX(14) 29.99 or less; CCI(20) 99.99 or less; MACD(12,26,9) -10 to 9.99 |
|  | Additional 2 | Low | 23 | 47.8% | 2.82 | $432 | -$58 | 745% | 37% | DAY OF WEEK Mon/Tue/Thu/Fri; VIX CHANGE -2 to 1.99; CHANGE SD -1 or greater; ADX(14) 29.99 or less; CCI(20) -200 to 99.99; MACD(12,26,9) -15 to 9.99 |
|  | Additional 3 | Low | 23 | 47.8% | 2.82 | $432 | -$58 | 745% | 37% | DAY OF WEEK Mon/Tue/Thu/Fri; VIX CHANGE -2 to 1.99; CHANGE SD -1 or greater; ADX(14) 29.99 or less; CCI(20) 99.99 or less; MACD(12,26,9) -5 to 9.99 |
|  | Additional 4 | Low | 24 | 45.8% | 2.60 | $412 | -$58 | 710% | 39% | DAY OF WEEK Mon/Tue/Thu/Fri; VIX CHANGE -2 to 1.99; GAP % -0.5% to 0.75%; ADX(14) 10 to 29.99; CCI(20) 99.99 or less; MACD(12,26,9) -15 to 9.99 |
|  | Additional 5 | Low | 24 | 45.8% | 2.60 | $412 | -$58 | 710% | 39% | DAY OF WEEK Mon/Tue/Thu/Fri; VIX CHANGE -2 to 1.99; GAP % -0.5% to 0.75%; ADX(14) 10 to 29.99; CCI(20) 99.99 or less; MACD(12,26,9) -10 to 9.99 |
| 045 QQQ ORB60 put 10/30 (base 61 tr, PF 1.26, P/L $333, DD -$500) | Best + Highest RoDD + Most consistent | Low | 25 | 56% | 4.04 | $782 | -$84 | 931% | 41% | DAY OF WEEK Mon/Thu/Fri; VIX CHANGE 1.99 or less; VIX CHANGE % -5% or greater; MACD(12,26,9) -5 to 25; RSI(14) 30 to 79.99 |
|  | Simplest | Low | 26 | 53.8% | 3.56 | $747 | -$84 | 889% | 43% | DAY OF WEEK Mon/Thu/Fri; VIX CHANGE 1.99 or less; VIX CHANGE % -5% or greater; MACD(12,26,9) -5 to 25 |
|  | Additional 1 | Low | 25 | 56% | 4.04 | $782 | -$84 | 931% | 41% | DAY OF WEEK Mon/Thu/Fri; VIX CHANGE 1.99 or less; VIX CHANGE % -5% or greater; RSI(14) 30 to 79.99; SMA(200) Above |
|  | Additional 2 | Low | 24 | 54.2% | 3.78 | $715 | -$84 | 851% | 39% | DAY OF WEEK Mon/Thu/Fri; VIX CHANGE 1.99 or less; VIX CHANGE % -5% or greater; GAP % -0.75% or greater; RSI(14) 30 to 79.99 |
|  | Additional 3 | Low | 24 | 54.2% | 3.78 | $715 | -$84 | 851% | 39% | DAY OF WEEK Mon/Thu/Fri; VIX CHANGE 1.99 or less; VIX CHANGE % -5% or greater; GAP % -0.75% or greater; MACD(12,26,9) -5 to 25; RSI(14) 30 to 79.99 |
|  | Additional 4 | Low | 25 | 52% | 3.33 | $680 | -$84 | 810% | 41% | DAY OF WEEK Mon/Thu/Fri; VIX CHANGE 1.99 or less; VIX CHANGE % -5% or greater; GAP % -0.75% or greater; MACD(12,26,9) -5 to 25 |
|  | Additional 5 | Low | 25 | 52% | 3.33 | $680 | -$84 | 810% | 41% | DAY OF WEEK Mon/Thu/Fri; VIX CHANGE 1.99 or less; VIX CHANGE % -5% or greater; GAP % -0.75% or greater; SMA(200) Above |
| 046 IWM ORB30 call 20/40 (base 83 tr, PF 1.04, P/L $44, DD -$245) | Best + Most consistent + Simplest | Low | 31 | 51.6% | 1.83 | $255 | -$131 | 195% | 37% | DAY OF WEEK Mon/Tue/Wed/Fri; VIX CHANGE -1 or greater; IV RANK 39.99 or less; OPEN CHG % 0.25% or greater |
|  | Highest RoDD | Low | 30 | 53.3% | 2.12 | $297 | -$114 | 261% | 36% | DAY OF WEEK Mon/Tue/Wed/Fri; VIX CHANGE -2 or greater; IV RANK 39.99 or less; OPEN CHG % 0.25% or greater; MACD(12,26,9) -2 to 8; MFI(14) 89.99 or less |
|  | Additional 1 | Low | 31 | 51.6% | 1.83 | $255 | -$131 | 195% | 37% | DAY OF WEEK Mon/Tue/Wed/Fri; VIX CHANGE -1 or greater; IV RANK 39.99 or less; OPEN CHG % 0.25% to 2% |
|  | Additional 2 | Low | 31 | 51.6% | 1.83 | $255 | -$131 | 195% | 37% | DAY OF WEEK Mon/Tue/Wed/Fri; VIX CHANGE % -5% or greater; IV RANK 39.99 or less; OPEN CHG % 0.25% or greater |
|  | Additional 3 | Low | 30 | 53.3% | 1.96 | $275 | -$131 | 210% | 36% | DAY OF WEEK Mon/Tue/Wed/Fri; VIX CHANGE -1 or greater; IV RANK 39.99 or less; OPEN CHG % 0.25% or greater; MFI(14) 89.99 or less |
|  | Additional 4 | Low | 30 | 53.3% | 1.96 | $275 | -$131 | 210% | 36% | DAY OF WEEK Mon/Tue/Wed/Fri; VIX CHANGE -1 or greater; IV RANK 39.99 or less; OPEN CHG % 0.25% to 2%; MFI(14) 89.99 or less |
|  | Additional 5 | Low | 30 | 53.3% | 1.96 | $275 | -$131 | 210% | 36% | DAY OF WEEK Mon/Tue/Wed/Fri; VIX CHANGE % -5% or greater; IV RANK 39.99 or less; OPEN CHG % 0.25% or greater; MFI(14) 89.99 or less |
| 047 IWM ORB30 call 20/60 (base 83 tr, PF 1.17, P/L $200, DD -$263) | Best + Most consistent + Simplest | Low | 30 | 40% | 1.70 | $238 | -$102 | 233% | 36% | DAY OF WEEK Mon/Tue/Wed/Fri; IV RANK 29.99 or less |
|  | Highest RoDD | Low | 28 | 50% | 2.55 | $406 | -$58 | 700% | 34% | IV RANK 29.99 or less; CHANGE % 1% or less; OPEN CHG % 0% to 1.25%; MACD(12,26,9) -4 to 8 |
|  | Additional 1 | Low | 28 | 46.4% | 2.06 | $324 | -$71 | 456% | 34% | VIX CHANGE % -3% or greater; IV RANK 29.99 or less |
|  | Additional 2 | Low | 30 | 40% | 1.70 | $238 | -$102 | 233% | 36% | DAY OF WEEK Mon/Tue/Wed/Fri; VIX CHANGE -3 or greater; IV RANK 29.99 or less |
|  | Additional 3 | Low | 29 | 48.3% | 2.39 | $388 | -$60 | 647% | 35% | IV RANK 29.99 or less; CHANGE % 1% or less; MACD(12,26,9) -4 to 8 |
|  | Additional 4 | Low | 28 | 46.4% | 2.06 | $324 | -$71 | 456% | 34% | VIX CHANGE -3 or greater; VIX CHANGE % -3% or greater; IV RANK 29.99 or less |
|  | Additional 5 | Low | 28 | 46.4% | 2.06 | $324 | -$71 | 456% | 34% | VIX CHANGE -3 to 4.99; VIX CHANGE % -3% or greater; IV RANK 29.99 or less |
| 051 IWM ORB60 call 20/60 (base 69 tr, PF 1.03, P/L $26, DD -$269) | Best + Highest RoDD + Most consistent | Low | 26 | 57.7% | 3.87 | $473 | -$41 | 1,154% | 38% | VIX CHANGE 0.99 or less; CHANGE % 0.25% to 1.25%; CHANGE SD -2 to 0.9999; ADX(14) 10 or greater; MACD(12,26,9) -6 to 5.99 |
|  | Simplest | Low | 28 | 53.6% | 3.32 | $446 | -$41 | 1,088% | 41% | VIX CHANGE % 1.99% or less; CHANGE % 0.25% to 1.25%; CHANGE SD -1 to 0.9999; ADX(14) 10 or greater |
|  | Additional 1 | Low | 26 | 57.7% | 3.87 | $473 | -$41 | 1,154% | 38% | VIX CHANGE 0.99 or less; CHANGE % 0.25% to 1.25%; CHANGE SD -2 to 0.9999; ADX(14) 10 to 89.99; MACD(12,26,9) -6 to 5.99 |
|  | Additional 2 | Low | 26 | 57.7% | 3.87 | $473 | -$41 | 1,154% | 38% | VIX CHANGE 0.99 or less; CHANGE % 0.25% to 1.25%; CHANGE SD -2 to 0.9999; ADX(14) 10 to 79.99; MACD(12,26,9) -6 to 5.99 |
|  | Additional 3 | Low | 26 | 57.7% | 3.87 | $473 | -$41 | 1,154% | 38% | VIX CHANGE 0.99 or less; CHANGE % 0.25% to 1.25%; CHANGE SD -2 to 0.9999; ADX(14) 10 to 69.99; MACD(12,26,9) -6 to 5.99 |
|  | Additional 4 | Low | 28 | 53.6% | 3.32 | $446 | -$41 | 1,088% | 41% | VIX CHANGE % 1.99% or less; CHANGE % 0.25% to 1.25%; CHANGE SD -1 to 0.9999; ADX(14) 10 to 89.99 |
|  | Additional 5 | Low | 28 | 53.6% | 3.32 | $446 | -$41 | 1,088% | 41% | VIX CHANGE % 1.99% or less; CHANGE % 0.25% to 1.25%; CHANGE SD -1 to 0.9999; ADX(14) 10 to 79.99 |
| 054 SPY ORB60 call debit spread $2w 50/100 (base 75 tr, PF 1.23, P/L $412, DD -$522) | Best + Most consistent + Simplest | Low | 37 | 56.8% | 2.47 | $861 | -$129 | 667% | 49% | REWARD / RISK 80% to 210%; VIX 19.99 or less; VIX CHANGE -2 to 2.99; CMO(9) 0 or greater; MFI(14) 30 to 69.99 |
|  | Highest RoDD | Low | 36 | 58.3% | 2.49 | $867 | -$129 | 672% | 48% | REWARD / RISK 80% to 210%; VIX 19.99 or less; VIX CHANGE -2 to 2.99; GAP % 0.75% or less; CMO(9) 0 or greater; MFI(14) 30 to 69.99 |
|  | Additional 1 | Low | 37 | 56.8% | 2.47 | $861 | -$129 | 667% | 49% | REWARD / RISK 80% to 210%; VIX 19.99 or less; VIX CHANGE -2 to 2.99; CMO(9) 0 to 79.99; MFI(14) 30 to 69.99 |
|  | Additional 2 | Low | 36 | 58.3% | 2.49 | $867 | -$129 | 672% | 48% | REWARD / RISK 80% to 210%; VIX 19.99 or less; VIX CHANGE -2 to 2.99; GAP % 0.75% or less; CMO(9) 0 to 79.99; MFI(14) 30 to 69.99 |
|  | Additional 3 | Low | 38 | 55.3% | 2.27 | $809 | -$129 | 627% | 51% | REWARD / RISK 80% to 210%; VIX 19.99 or less; VIX CHANGE -2 to 2.99; CMO(9) 0 or greater; MFI(14) 69.99 or less |
|  | Additional 4 | Low | 38 | 55.3% | 2.27 | $809 | -$129 | 627% | 51% | REWARD / RISK 80% to 210%; VIX 19.99 or less; VIX CHANGE -2 to 2.99; CMO(9) 0 to 79.99; MFI(14) 69.99 or less |
|  | Additional 5 | Low | 37 | 54.1% | 2.12 | $716 | -$171 | 419% | 49% | REWARD / RISK 90% to 210%; VIX 19.99 or less; VIX CHANGE -2 to 2.99; CCI(20) 0 to 199.99; MFI(14) 69.99 or less |
| 065 SPX ORB60 put credit spread $10w, -100% stop (research only) (base 69 tr, PF 1.04, P/L $114, DD -$1,033) | Best + Most consistent + Simplest | Low | 52 | 67.3% | 1.59 | $943 | -$501 | 188% | 75% | IV RANK 10 to 49.99; CHANGE % -0.75% to 1.75%; OPEN CHG % 0.75% or less; CCI(20) -100 or greater |
|  | Highest RoDD | Low | 49 | 67.3% | 1.68 | $976 | -$501 | 195% | 71% | IV RANK 10 to 49.99; CHANGE % -0.75% to 1.75%; OPEN CHG % 0.75% or less; CCI(20) -100 or greater; CMO(9) 59.99 or less |
|  | Additional 1 | Low | 49 | 67.3% | 1.68 | $976 | -$501 | 195% | 71% | IV RANK 10 to 49.99; CHANGE % -0.75% to 1.75%; OPEN CHG % 0.75% or less; CCI(20) -100 or greater; CMO(9) -20 to 59.99 |
| 088 SPY ORB60 call .50d 50/100 (base 75 tr, PF 1.55, P/L $1,619, DD -$630) | Best + Most consistent + Simplest | Low | 53 | 52.8% | 2.40 | $2,285 | -$253 | 903% | 71% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX CHANGE -3 to 2.99; OPEN CHG % 0.75% or less; MFI(14) 69.99 or less |
|  | Highest RoDD | Low | 52 | 53.8% | 2.51 | $2,353 | -$253 | 930% | 69% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX CHANGE -3 to 4.99; CHANGE SD -2 to 1.999; OPEN CHG % 0.75% or less; MFI(14) 69.99 or less |
|  | Additional 1 | Low | 53 | 52.8% | 2.37 | $2,261 | -$253 | 894% | 71% | DAY OF WEEK Mon/Tue/Wed/Thu; CHANGE SD -2 to 1.999; OPEN CHG % 0.75% or less; MFI(14) 69.99 or less |
|  | Additional 2 | Low | 52 | 53.8% | 2.51 | $2,353 | -$253 | 930% | 69% | DAY OF WEEK Mon/Tue/Wed/Thu; VIX CHANGE -3 to 4.99; CHANGE SD -2 to 1.999; OPEN CHG % 0% to 0.75%; MFI(14) 69.99 or less |

### Backtests made with Apply Filters (OA-S1-080 to 087) and the locked T1a copy (088)

Blocks are P/L for Nov-Dec 2025 / Jan-Feb / Mar-Apr / May-Jun 2026.

| Run | Base | Variation applied | Exact filters | Trades | WR | PF | P/L | Max DD | Blocks | vs optimizer preview |
|---|---|---|---|---|---|---|---|---|---|---|
| 080 | 023 SPY ORB60 call 20/60 | Simplest | VIX CHANGE -3 to -0.01 | 50 | 40.0% | 1.75 | $622 | -$110 | +210 / +99 / +94 / +219 | same |
| 081 | 023 | Most consistent (= Best) | VIX CHANGE -3 to -0.01; OPEN CHG % 0% to 0.75%; STOCH(14,3,3) 20 or greater | 46 | 43.5% | 2.18 | $784 | -$110 | +210 / +116 / +158 / +300 | same |
| 082 | 024 SPY ORB60 call 15/45 | Simplest | CHANGE % -1% to 1.75%; OPEN CHG % 0% to 0.75%; MOMENTUM(10) -20 to 29.99 | 56 | 42.9% | 2.01 | $728 | -$103 | +227 / +61 / +154 / +286 | preview 55 tr, $754, PF 2.09 |
| 083 | 024 | Most consistent (= Best = Highest RoDD) | DAY OF WEEK Mon/Wed/Thu/Fri; CHANGE % -1% to 2%; OPEN CHG % 0% to 0.75%; MACD(12,26,9) -10 to 9.99; MOMENTUM(10) -20 to 39.99 | 35 | 42.9% | 2.31 | $603 | -$66 | +209 / +78 / +127 / +189 | preview 34 tr, $629, PF 2.45 |
| 084 | 045 QQQ ORB60 put 10/30 | Simplest | DAY OF WEEK Mon/Thu/Fri; VIX CHANGE 1.99 or less; VIX CHANGE % -5% or greater; MACD(12,26,9) -5 to 25 | 26 | 53.9% | 3.56 | $747 | -$84 | +284 / +15 / +167 / +281 | same |
| 085 | 045 | Most consistent (= Best = Highest RoDD) | same as 084 + RSI(14) 30 to 79.99 | 25 | 56.0% | 4.04 | $782 | -$84 | +284 / +15 / +167 / +316 | same |
| 086 | 047 IWM ORB30 call 20/60 | Simplest = Most consistent (one variation) | DAY OF WEEK Mon/Tue/Wed/Fri; IV RANK 29.99 or less | 30 | 40.0% | 1.70 | $238 | -$102 | -49 / +264 / +44 / -21 | same |
| 087 | 054 SPY ORB60 call debit $2w 50/100 | Simplest = Most consistent (one variation) | REWARD / RISK 80% to 210%; VIX 19.99 or less; VIX CHANGE -2 to 2.99; CMO(9) 0 or greater; MFI(14) 30 to 69.99 | 37 | 56.8% | 2.47 | $861 | -$129 | +262 / -60 / +302 / +357 | same |
| 088 | T1a settings (SPY ORB60 call .50d 100/50), locked dates excluded | none | none | 75 | 42.7% | 1.55 | $1,619 | -$630 | +726 / -480 / +1038 / +335 | n/a |

### Filters that recur across strategies

Counted by code over the 19 base runs, using the named variations (Best / Highest RoDD / Simplest / Most consistent):

| Filter | Base runs whose named variations use it (of 19) |
|---|---|
| VIX CHANGE (points) | 11: 015, 016, 017, 023, 030, 036, 045, 046, 051, 054, 088 |
| IV RANK | 11: 001, 015, 017, 020, 022, 023, 025, 036, 046, 047, 065 |
| DAY OF WEEK | 11: 003, 015, 016, 017, 020, 024, 030, 045, 046, 047, 088 |
| CHANGE % (since prior close, at entry) | 10: 003, 016, 020, 022, 023, 024, 036, 047, 051, 065 |
| OPEN CHG % (since today's open, at entry) | 10: 001, 003, 023, 024, 025, 036, 046, 047, 065, 088 |
| VIX CHANGE % | 9: 016, 017, 020, 022, 023, 025, 036, 045, 051 |
| MACD(12,26,9) | 8: 001, 003, 024, 030, 045, 046, 047, 051 |
| CMO(9) | 7: 001, 003, 016, 017, 020, 054, 065 |
| CHANGE SD | 6: 001, 003, 015, 030, 051, 088 |
| MFI(14), MOMENTUM(10), VIX level | 3 each |
| RSI(14), CCI(20), STOCH(14,3,3), ADX(14) | 2 each |
| GAP %, REWARD / RISK | 1 each |

Exact values that repeat in two or more base runs:
- "IV RANK 39.99 or less" in 8 runs: 001, 017, 020, 022, 023, 025, 036, 046.
- "OPEN CHG % 0% to 0.75%" in 4 runs: 023, 024, 025, 036.
- "VIX CHANGE % 0.99% or less" in 4 runs: 022, 023, 025, 036.
- "CMO(9) 39.99 or less" in 4 runs: 001, 016, 017, 020.
- DAY OF WEEK leaving out Thursday (Mon/Tue/Wed/Fri) in 4 runs: 003, 015, 046, 047.
- DAY OF WEEK leaving out Friday (Mon/Tue/Wed/Thu) in 4 runs: 016, 017, 020, 088.
- "OPEN CHG % 0.75% or less" in 3 runs: 025, 065, 088.
- 023 and 036 are the same strategy apart from the exit time, and they share every named filter set.

### Odd things, recorded as seen

**Results**
- Every variation on every base run is labeled "Low Confidence".
- **Weak base runs became strong:**
  - 003: base P/L $9, PF 1.00 became $1,190, PF 2.39 (6 filters, 55% of trades kept).
  - 030: $2 became $432, PF 2.82 (6 filters, 37% kept).
  - 051: $26 became $473, PF 3.87 (5 filters, 38% kept).
  - 016: $24 became $719, PF 3.55 (6 filters, 43% kept).
- **Labels:** on 047, the variation labeled "Best Return on Drawdown" has return on DD 233%, which is lower than "Highest Return on Drawdown" (700%) and four "Additional" variations (456-647%).
- **Repeated max drawdowns:** all 8 variations for 025 show max DD -$101. All 3 for 065 show -$501.
- **Puts:** 045 is a put strategy, and two of its "Additional" variations filter on "SMA(200) Above".

**Apply Filters runs**
- **Same as preview:** 6 of the 8 Apply Filters backtests match the optimizer preview exactly (084's win rate shows 53.9% against 53.8% in the preview).
- **Different from preview:** 082 and 083 (both from base 024) each have one more trade than the preview, and lower P/L and PF.
- **Missing months:**
  - 083: no May 2026 trades.
  - 086: 27 of 30 trades fall in Nov-Feb.
  - 087: no March 2026 trades.

**Process**
- One read-only inspection of the page's internal objects was refused by the session's permission check. It was not retried. How Apply Filters works was taken from the app's public script instead.
