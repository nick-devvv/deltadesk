# DeltaDesk v3: what changed, what was verified, what still needs a live session

Policy `2026-10-29.v3`. Everything new here is paper-only. Real money stays manual: Nick places every real trade in Robinhood, and no code path sends an order anywhere. Paper trades are simulated inside the desk.

## 1. The chart question

**Can the desk show a chart from Schwab data instead of the delayed TradingView chart? Yes, by drawing it ourselves.**

- The old desk used TradingView's **hosted widget** (`tv.js`, `new TradingView.widget`). Hosted widgets always use TradingView's own data and can't take a custom feed, so they can never show Schwab's numbers.
- Schwab doesn't offer an embeddable thinkorswim chart. What it offers is the data: 1-minute price history and a streaming API.
- v3 draws its own chart with TradingView **Lightweight Charts 5.2.1** (Apache-2.0, attribution logo kept on), served from the desk itself (`vendor/`), fed by `/api/chart`. The candles, VWAP, EMA 9/21, 2-minute MACD, levels and entry/exit marks come from the **same snapshot the engine decides on**. A test checks that the chart's MACD and last close equal the engine's.
- Lightweight Charts has no built-in indicators, so all indicator values are computed on the server (`indicators.py`, checked against TA-Lib 0.8.3) and sent as numbers.
- Advanced Charts was not used: it needs a TradingView license application, which isn't available here.
- The TradingView chart is still one click away (Desk / TradingView toggle). With Schwab connected the desk chart is the default; without Schwab the page starts on TradingView, since the desk would only have fallback data.

**Where the old delay came from.** This was not measured, because the build environment has no market access. The code shows two separate things. The chart was TradingView's own feed and plan, which the desk can't see or control. The desk's own numbers came from Yahoo 1-minute bars polled through `yfinance`, an unofficial research package. v3 measures this now: the chart chip shows the age of the newest finished bar, and `/api/data/status` keeps p50/p95/max latency for bars, quotes and signals. The first live session will give the real number.

## 2. The October 28 audit: root causes and fixes

The audit link was not readable; this follows the summary in the brief. The original records live in the desk database on Chart's computer. `replay.py` reads them read-only and lists every position, order and quantity, so the -$54 paper and -$41 real totals and the "x2, twice" SPY 772C wording can be checked against the actual records rather than guessed.

| # | Defect | Root cause in the old code | Fix | Where | Test |
|---|---|---|---|---|---|
| 1 | ORB retest on a rejected volume spike; PDH retest that never touched 771.14 | Retest = "close back above" with no touch check; no spike filter | A retest needs the bar to touch the level zone and close in the trade's direction. Rejected-spike filter (wick 60%+, volume 2x+, needs 2 accepting closes) | `strategy.detect_orb`, `detect_prior_day`, `rejected_spike` | `test_pdh_retest_requires_an_actual_touch_of_the_zone` |
| 2 | 7 cents over the ORB high became an A-grade trend day | Trend label from one comparison | Regime from ADX/DI, efficiency, VWAP crossings, overlap, range vs ATR, and ORB acceptance (3 closes beyond and 0.5 ATR away) | `strategy.regime` | `test_no_trend_day_from_seven_cents_above_the_opening_range` |
| 3 | MACD histogram faded 4 bars before the 13:06 entry | Only "MACD above signal" was checked | 2m histogram fading = 3 adverse changes (needs 4 values); cross event separate from state; sign-aware for puts; reversal setups judged on the new direction | `indicators.hist_fading`, `macd_cross`, `macd_state`; `strategy.qualify` | `test_macd_cross_event_vs_state_and_three_changes_need_four_samples` |
| 4 | Bought above value after a rejected spike, POC near 771.00 | No volume profile | Developing profile at the decision time, from finished 1m bars: $0.05 bins, 70% value area (a convention, not tuned), POC ties go to the price nearest the close. Labeled APPROXIMATE because bars are not a trade tape | `indicators.volume_profile`, `strategy.levels` | `test_levels_have_sources_and_orb_is_developing_until_done` |
| 5 | One idea opened two positions from two detectors | Each detector opened its own position | All detectors run on one snapshot; same side merges into one idea; calls+puts on one bar = skip the bar; ideas reserved atomically (SQLite `BEGIN IMMEDIATE`, primary key) so retries/restarts can't duplicate | `strategy.arbitrate`, `paper.reserve_idea`, `engine.paper_scan` | `test_conflicting_calls_and_puts_skip_the_bar_and_same_side_merges`, `test_idea_reservation_is_atomic_and_the_four_cap_holds_under_threads` |
| 6 | RVOL used an unfinished candle | Forming bar vs finished history | Only finished bars; same clock interval vs the median of up to 10 prior sessions, needs 5, otherwise "unavailable" | `indicators.rvol_at_time` | `test_two_minute_bars_complete_and_rvol_ignores_unfinished_candle` |
| 7 | Flat % stops/targets, weak reward/risk | Stops and targets were premium percentages | Structure stop + 20% planned-loss ceiling; T1 at the next opposing level; 2:1 needed on the stock move and on option dollars after spread, fees and theta; units never mixed | `optionmath.plan_trade`, `pick_t1` | `test_option_math_keeps_units_apart_and_enforces_ceiling_and_two_to_one` |
| 8 | T1 ignored levels, gains given back, no stall exit | No green-trade exit; T1 = % target | Exit state machine with a fixed order; 10-min green stall exit; momentum exit; T1 partial with a runner only on a clean break; cost-aware breakeven and profit lock; stops only tighten | `exits.py` | stall, momentum, T1 partial, precedence and ratchet tests |
| — | Data | Yahoo candles, delayed Alpaca option quotes, mixed silently | One pipeline (`marketdata.py`): Schwab stream or REST; fallback labeled "not executable" and never filled; incremental quote merges; finished-bar rule; gap detection and REST backfill after reconnects | `marketdata.py`, `schwab_stream.py`, `schwab.py` | stream merge, fallback, outage and Schwab path tests |
| — | User trades | Stop changes not recorded; a chase looked like a setup | Every stop change is versioned with who made it; widening refused unless `force`; a fill that doesn't match a desk plan is labeled "NOT a qualified desk setup" | `exits.user_stop`, `commands.log_real_in` | `test_stops_only_ratchet_toward_protection_and_widening_is_refused` |

The old settings were checked in the old code before freezing them: stops 20/12/10%, breakeven +10/+8/+6%, T1 +20/+15/+12%, if-flat 5/3/3 min. They are kept unchanged in `config/policy_old_2026-10-28.3.json` and run as the "Old rules" ledger.

## 3. Old rules vs new rules

| Area | Old (v2) | New (v3) | Applies to |
|---|---|---|---|
| Entry | 5m close past a level | Finished-bar confirmation; a retest needs a touch; extension under 1.0 ATR; conflicts skip the bar | main paper, research, alerts to Nick |
| Stop | 20/12/10% of the premium by time of day | Structure stop on a 1m close, inside a 20% planned-loss ceiling | main paper, research; plans and alerts for Nick |
| Target | +20/15/12% | Next opposing level; 2:1 needed on stock and option | same |
| Green trade | none | Stall 10 min → out; momentum fades or crosses → out | same |
| T1 | sell at target | 2+ contracts: sell 1, runner only on a clean break; 1 contract: sell | same |
| Losers | if-flat 5/3/3 min | kept | same |
| Session | all out 15:25 | 15:25, 12:50 on early-close days | all |
| Limits | streak stop | streak stop + 4 ideas a day + one direction across SPY/QQQ | main paper only |
| Research | none | same setups, continues after the main limits | research ledger |
| VWAP + MACD | not a strategy | one strategy: cross arms, VWAP retest entry, early entry only in a strong trend | paper ledgers, alerts |
| Real coaching | stop by time of day | same plan math as paper; Nick decides and places every trade | Nick |

## 4. Tests and the October 28 replay

- `python3 -m pytest -q tests/`: **54 tests: 53 passed, 1 skipped.** The skipped one is the TA-Lib parity test, which only runs when TA-Lib is installed; it passes with TA-Lib 0.8.3. Run on Python 3.13 with pandas 3.0.5 / numpy 2.5.3, and again with pandas 2.2.3 / numpy 2.1.3.
- Every test runs offline on a fake Schwab provider and synthetic markets. **No test talks to Schwab.** Live streaming, entitlements and real latency are unverified until the first live session.
- Covered: indicator warm-up and TA-Lib agreement, session VWAP reset, 2m completion, partial-candle RVOL, level sources, the false trend day, the PDH touch, conflict skip and merge, atomic idea reservation under threads, option units/ceiling/2:1/sizing, missing delta, no fill during an outage, stall timing with stale quotes, momentum exit, T1 partial vs one contract, exit precedence, stop ratchet and refused widening, fallback never filling, incremental stream merges and bar corrections, Schwab path refusal, early close and DST, the full VWAP+MACD flow with one idea per arming, research continuing after the streak stop, chart = engine snapshot, Kronos having no trading path and tagging its data source, and the replay sandbox.

**Reproducible replay** (on Chart's computer, in the desk folder):
```
python3 replay.py 2026-10-28                 # Schwab 1m history (Schwab must be connected)
python3 replay.py 2026-10-28 --csv reports/replay_bars_2026-10-28_schwab.csv   # exact rerun
```
It writes `reports/replay_2026-10-28.md`: the original records and totals, the v3 engine over the whole day (main, research, old rules), every candidate with its decision and reasons, the bars skipped for call/put conflicts, and each original entry (including SPY 770C) re-managed under old and new exits with peak executable bid vs marked mid, giveback, runner contribution and costs.

Missing-data limits, stated in the report as well:
- Schwab has no historical option quotes, so **every option price in the replay is modeled** (Black-Scholes on the real underlying, with the volatility solved from each actual fill). None of it is an observed fill.
- Intrabar order is unknown. The replay runs twice: once on 1m closes, and once "adverse", where the worst price inside each minute counts first.
- The news calendar for Oct 28 wasn't recorded, so the event state replays as "unknown".
- October 28 was used to design these rules. Its replay is a regression check, not evidence.

## 5. Ledgers, the forward test and Kronos

- Four ledgers that are never added together: **You** (reported fills), **Main paper** (v3), **Research** (v3 without the day limits), **Old rules** (frozen v2). The Paper page shows each one with ideas today, streak, trades, win rate, expectancy and profit factor, plus a "too few trades" note under 30 trades, and a table of every decision with its reasons.
- **Forward paper test**, set in `policy.json → evaluation` before any results exist. It starts 2026-10-30 and runs for at least 2 weeks and 10 complete sessions with Schwab live. The policy is frozen for the whole test, and any change starts a new test. The primary measure is main-paper net expectancy per trade after costs, with a bootstrap interval. It needs at least 20 closed trades or the verdict is "not enough trades". It also requires profit factor ≥ 1.2, drawdown under 3x the average loss, and zero rule violations. The test compares main vs old rules and main vs research on the same sessions. Passing does not allow real-money automation or larger size.
- **Kronos** stays forecast-only. It has no import path to orders, paper, exits or idea reservation, and a test checks that. Each forecast now stores its data source: `yahoo (pre-v3)` for old rows, `yahoo 5m (research input)` until the desk's Schwab archive holds about 5 sessions, then `schwab 1m->5m (desk archive)`. Only one source is used per forecast. The reported 39–46% direction accuracy vs 53–63% for momentum could not be re-checked here (that database is on Chart's computer). `/api/kronos` computes both on the same rows, excludes flat outcomes from direction scoring, and shows counts by source. The 20-day study and the 2-week paper test are separate.

## 6. Setup, rollback, versions, what's left

**Setup (Nick and Chart):**
1. Back up the desk folder and `journal/desk.db` (the install message does this).
2. `pip install websockets==17.3` (streaming). Nothing else new is required.
3. Nick puts `SCHWAB_APP_KEY` and `SCHWAB_APP_SECRET` into Chart's Secrets himself (`docs/SCHWAB_SETUP.md`). Reset the secret first if it was ever pasted anywhere.
4. Restart the desk, then Nick connects Schwab on the Rules page.
5. Chart replaces its webhook and 4:20 review instructions with `grok/PRIMARY_COACH_SYSTEM_PROMPT.md` and `grok/REVIEW_PROMPT.md`, and uploads `grok/RULES_MAP_V3.md` to its Library as "Desk v3 rules map".

**Rollback:** stop the server, restore the backup folder (code + `config/` + `journal/desk.db`), start it again. v3 only adds tables (`ideas`, `candidates`, `bars_archive`, `quotes_archive`) and one column (`forecasts.data_src`), so the old code ignores them.

**Implementation map:**

| Capability | Module | Library / version | Called by | Verified by |
|---|---|---|---|---|
| Schwab REST market data | `schwab.py` | stdlib `urllib` | `marketdata.SchwabREST`, `replay.py` | path refusal test (live: unverified) |
| Schwab streaming | `schwab_stream.py` | websockets 17.3; protocol checked against schwab-py 1.5.0 (unofficial wrapper, reference only, not installed) | `server.py` start | message-merge tests (live: unverified) |
| Normalized data, freshness | `marketdata.py` | pandas 3.0.5 / 2.2.3 | engine, exits, paper, chart | fallback/outage/stream tests |
| Indicators | `indicators.py` | numpy 2.5.3 / 2.1.3 | strategy, chartfeed | TA-Lib 0.8.3 parity test |
| Levels, regime, setups | `strategy.py` | | engine | setup and regime tests |
| Option plan, sizing | `optionmath.py` | | engine, replay | option math tests |
| Simulated fills | `paper.py` | sqlite3 | engine, exits | outage and reservation tests |
| Exits | `exits.py` | | engine | exit tests |
| Old rules (frozen) | `policy_old.py` + `config/policy_old_2026-10-28.3.json` | | engine, replay | old-settings check |
| Desk chart | `chartfeed.py`, `index.html` | Lightweight Charts 5.2.1 (vendored) | browser | chart = snapshot test, browser check |
| Replay | `replay.py` | | Chart / Nick | replay sandbox test |
| Kronos | `kronos_shadow.py` | Kronos rev 67b630e (unchanged) | separate process | no-trading-path and source-tag tests |

**Dependencies** (`requirements.txt`, pinned to the tested versions): pandas 3.0.5, numpy 2.5.3, yfinance 1.7.0 (research-only fallback and Kronos warm-up), websockets 17.3, pytest 9.1.1. Optional: TA-Lib 0.8.3 for the parity test only.

**Not verified, and why:**
- Schwab streaming login, subscriptions and entitlements, and the real delay. These need Nick's connected account during market hours.
- The Oct 28 replay numbers. They need the Schwab history and the desk database on Chart's computer (`python3 replay.py 2026-10-28`).
- The Kronos day-1 accuracy figures. Its database is on Chart's computer.
- The SPY 772C "x2, twice" records and the MU 1015C contract identifier. The replay lists the actual rows; nothing was assumed.

Don't treat v3 as ready until the first live session has shown "Schwab live" on the chart chip and `/api/data/status` reports sane latency.
