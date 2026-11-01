# Strategy + exits sprint: pre-registration

Written 2026-10-31, before any sprint run. Branch `sprint/exits` (nothing here touches the live desk or `main` until Nick says yes). Source brief: Nick's "Strategy + exits sprint" message, 2026-10-31. `context.rules` was not found in the repo or on Nick's Mac; base numbers come from `docs/STRATEGY_PLAN.md` and the brief, and any later `context.rules` numbers are tested as variants.

## Goal

Maximize profit after costs, per trade and in total, with drawdown under control. Win rate is not a target. The main question is how to exit: the current fixed-% plan (about 1:1) against key-level targets and trailing stops.

## Periods

| Use | Option Alpha (OA) | Desk engine (Alpaca option prices) |
| --- | --- | --- |
| Development (free to explore, no run cap) | 2025-10-30 to 2026-06-30 (the trial's 1-year window with Jul 1 to Oct 30 2026 excluded) | 2024-08-01 to 2026-06-30 |
| Locked period L1 | 2026-07-01 to 2026-10-30 | 2026-07-01 to 2026-10-30 |
| Locked period L2 | n/a (outside OA's data) | 2024-02-01 to 2024-07-31 |
| Not seen by OA (desk engine cross-check of OA ideas) | n/a | 2024-08-01 to 2025-10-29 |

- No run of any kind on L1 or L2 until the finalists' rules are frozen and committed. Each finalist then runs once on each locked period. Results are reported whatever they are.
- T1-T9 (2026-10-31) already covered Jul-Oct 2026 for the 60-min ORB, credit spreads and iron condor, so L1 is not fully clean for those; L2 is the clean check for them.
- If OA cannot exclude a date range, OA development runs are cut off at 2026-06-30 by the closest available setting, and the deviation is logged.

## Cost model and fills

**Option Alpha:** fills at mid plus slippage. Base slippage $0.03 per contract on entries and on exits. If OA's stops fill at the stop level or at mid without slippage, add $0.03 more on stop exits. "2x slippage" = $0.06 base and +$0.06 on stops. Fees ($0.04/contract/side by default) are added back to P/L in the log.

**Desk engine:**
- Long options are bought at the ask and sold at the bid when quotes are logged. On Alpaca bars and trades (no historical quotes), fills are the trade/bar price ± k × the half-spread from the spread model, with k = 1 as base and k = 2 as "2x slippage". The half-spread uses the desk's logged chains when present, otherwise a default of 2% of premium for SPY/QQQ/IWM and 10% for single stocks, labeled MODELED-SPREAD.
- Fees: $0.65 per contract per side.
- **Same-bar stop and target:** if a stop and a target both fall inside the same 1-minute bar, the stop counts.
- **Stop fills:** a stop fills at the worse of the stop price and the next real price after it, plus slippage. A fill is never at a price the option did not trade or quote.
- **No quote:** if the option has no trade or quote in a minute, no fill is assumed in that minute.
- **Signals and levels:** signals use finished 1-minute (or 5-minute) bars only. Levels use only data known at entry.
- **Entries:** at the next bar after the signal.

**Amendment, 2026-10-31, before any desk-engine run:** the SPY/QQQ/IWM default half-spread changed from 5% to 2% of premium. Option Alpha's T1a fills, at mid + $0.03, sat at the ask and bid on an average premium of about $1.44, so the real half-spread is at most about $0.03 (2%). 5% (a 10% round trip) is kept as a stress run.

## Levels (known at entry)

- Prior-day high, low and close.
- Premarket and overnight high/low (04:00-09:29 ET bars).
- Opening-range high/low for 5, 15, 30 and 60 minutes, once the range is complete.
- VWAP and its 1 and 2 standard-deviation bands.
- The developing volume profile's POC, VAH and VAL (70% value area, $0.10 bins for SPY/QQQ).
- Round numbers ($1 and $5 for SPY/QQQ).
- Prior-week high/low.
- Intraday swing highs and lows already printed: a 1-minute bar whose high or low beats the 3 bars on each side, confirmed 3 bars later.

## Entries tested

1. **ORB breakout, both sides** (priority): 15-, 30- and 60-minute ranges. Calls on a finished 1-minute close above the high, puts on a close below the low. First break only, entries until 12:00.
2. **Noise band** (`noise` rules) and a twin without the 20% premium ceiling checked every tick. The original ledger is never changed.
3. **Nick's bot setups**, as pre-registered tests:
   - VWAP + 2-minute MACD cross, entering on the VWAP retest.
   - Prior-day high/low retest + 9 EMA pullback.
   - Failed-break calls.
   - Reversal after a flush.

   Each one's exact mechanical definition is written into its module docstring before its first run.
4. **Stock books** (`sip_orb5`, `sip_orb5_x`, `earn_day`) for the exit study on shares and option shadows, after the index work.

**Contracts:** delta 0.40-0.55, aiming for 0.45 (base). Spread at most ~10% of price. The stop's % is a ceiling with costs included; if the level stop doesn't fit inside it, the trade is skipped. Variants: delta 0.50-0.65.

## Exit variants (each tested against the others)

**Take profit:**
- **A.** Fixed % T1 by time of day (the current plan, the one to beat):

| Window (ET) | Max stop | Breakeven at | T1 | If flat, exit after |
| --- | --- | --- | --- | --- |
| 09:45-11:30 | 20% | +10% | +20% | 5 min |
| 11:30-14:00 | 12% | +8% | +15% | 3 min |
| 14:00-15:30 | 10% | +6% | +12% | 3 min |
| After 15:30 | no new trades | | | |

  All out by 15:25 and by 15:50, both tested.
- **B.** Sell all just before the first key level. Approach buffers: $0.03, 0.05% and 0.1 ATR(14, 1-min).
- **C.** Sell half at the first level and trail the rest. If price closes through the level and holds a retest, hold the rest to the next level.
- **D.** A, except on trend days, volume 1.5x+ or live news, where it uses C.
- **E.** At the level, exit only on a measurable rejection: a wick back of 50%+ of the bar's range, a volume spike of 2x the 20-bar average, or the MACD histogram shrinking 2 bars in a row. Otherwise hold to the next level.

**Stop:** the level that proves the idea wrong, judged on a finished 1-minute close, plus a buffer of max($0.02, 0.05 ATR). The planned reward to risk is (target − entry) / (entry − stop), on the stock and on the option after spread, fees and decay. Trades below a minimum are skipped; minimums of 1.5, 2, 2.5 and 3 are tested.

**Trails (once the trade is green):**
1. **Breakeven move** to fill + costs, triggered at +6%, +8%, +10%, +15%, or once the first level clears.
2. **Profit-lock ladders:**
   - L1: +20% → lock +10%, +30% → lock +20%, +50% → lock +35%.
   - L2: +15% → lock +5%, +30% → lock +15%, +60% → lock +40%.
   - L3: +25% → lock +10%, +50% → lock +30%, +100% → lock +70%.
3. **Structure trail:** under each 1-minute higher low; under each 5-minute higher low; under the last level cleared.
4. **Giveback trail:** give back at most 30%, 40% or 50% of the peak open profit.
5. **VWAP or 9 EMA trail,** on trend days only.

**Time of day:**
- (a) The table as it is.
- (b) Level exits with no time tightening.
- (c) Levels set the target; time only tightens the stop ceiling and the if-flat clock.
- (d) Version (c), with time tightening off on trend days and news.

An open trade that crosses into a new window never gets a looser stop.

**Day type** uses only information known at the time:
- ADX/DI(14, 5-minute).
- Efficiency ratio (30 bars).
- VWAP crossings in 60 minutes.
- Bar overlap.
- Range vs ATR.
- Opening-range acceptance (3 closes beyond, 0.5 ATR away).
- News state.
- The `noise_trend` score.

Chop days allow at most 2 trades, 1 contract each. After 14:00, a trade needs efficiency 0.35+, at most 2 VWAP crosses in 60 minutes, bar overlap under 60%, and RVOL 1.2+.

**Risk** (the base for the full bot rules):
- $50 max loss per trade.
- At most 4 trades a day.
- After 2 losses in a row: A setups only, with a 10-minute cooldown.
- After 3 losses in a row: done for the day.
- One idea = one trade.
- No continuation entries in a pre-event or news-shock window.
- Runner exception: on live market-moving news, or a one-way move with volume 1.5x+, hold 1 contract and trail it.

## Measured on every trade

- The option's MFE and MAE, and the stock's.
- Where the peak happened relative to the nearest level.
- The % of peak profit kept.
- Planned vs actual reward to risk.

**Level test:** exits at real levels vs made-up levels at the same distance (each real level shifted to a random point between the neighboring levels, 20 seeds). If the made-up levels do as well, the levels add nothing.

## Build order (desk engine)

1. Start plain: entry + hard stop + time exit.
2. Add one rule at a time:
   - level targets
   - the reward-to-risk minimum
   - the breakeven move
   - each trail
   - time-of-day tightening
   - the if-flat exit
   - green-trade exits
   - the runner exception
   - the trend/chop rules
   - the after-14:00 filter
   - the streak rules
3. Keep a rule only if it adds profit after costs on development data.
4. Tune the numbers only on rules that earned their place.

**First answer sent to Nick before building further:** ORB exits, both sides, comparing the current 1:1 plan, the best level target and the best trail.

## Robustness (must pass before the locked periods)

- At least 60 trades.
- Profit factor at least 1.25, and above 1.0 at 2x slippage (with the extra on stop exits).
- Profitable on its own in each of: Aug-Dec 2024, 2025, and Jan-Jun 2026. OA-only ideas: profitable in 3 of the 4 two-month blocks of Nov 2025-Jun 2026.
- Moving any number one step keeps PF above 1.1 (a plateau, not a spike).
- Still positive without its best 5 trades.
- Works on both sides, or the side is picked by a rule known before entry.
- Beats matched random entries.
- Every filter beats skipping the same number of random days.
- Real levels beat made-up levels.

Freeze at most 3-5 finalists, commit their rules, then run L1 and L2 once each.

## Logging

Every run in both tools, winners and losers, goes in `docs/research/sprint_runs.csv` (one row per run, including OA runs and failed or aborted runs). The total count of runs tried is reported next to every finalist, and the multiple-testing haircut (deflated Sharpe) uses it.

Columns: run_id, timestamp, tool, period_tag (DEV/L1/L2/NOT_SEEN_BY_OA), symbol, setup, side, stop_rule, tp_rule, trail, time_rule, trend_rule, filters, contract_rule, slippage, trades, win_rate, avg_win, avg_loss, expectancy, profit_factor, pf_2x_slip, max_dd, pct_peak_kept, planned_rr, actual_rr, notes.

## Amendment 2, 2026-10-31: setups_v2, the failed-break deep dive (written after run 1, before any v2 run)

Run 1 (`docs/research/SPRINT_RESULTS_1.md`) left one lead: failed-break calls with the plain exit (setups_v1-049). `sprint/specs/setups_v2.json` (58 runs, DEV) changes one thing at a time on that run. Everything chosen from these results is **in-sample**, and every run counts as a trial for the deflated Sharpe.
- **Entry numbers** (`sprint/entries.py`): re-close window 3 / 10 bars (base 5); probe depth 0.25 / 0.75 / 1.0 x ATR(14, 5m) (base 0.5); prior-day and premarket lows only; opening-range lows only.
- **Mirror** `failed_high` (puts): a failed break above PDH, PMH, OR15H or OR30H, the same numbers. This is the "works on both sides" check.
- **Symbols:** SPY, QQQ, IWM each alone, and SPY+QQQ. SPY+QQQ was chosen after seeing IWM lose in run 1, so it is in-sample.
- **Exits on the plain base:**
  - time rules (a), (c), (d);
  - each trail alone;
  - the level stop alone;
  - level take-profits B, C, E and D;
  - a fixed 20% stop with a +100% or +200% target;
  - all out 15:50.
- **Contracts:**
  - delta 0.50-0.65 and 0.45-0.60;
  - the **next listed expiry** (`n1...`): the nearest expiry after the session, bought and sold the same session.
  - Next-expiry prices are 1-minute bars only (no trades). BS-EST time = minutes to 16:00 plus 1440 x the calendar days to expiry.
- **Day filters:** each alone, each against skipping the same number of random days. The filters: trend_only, noise_trend, chop2, after14, skip_fomc_cpi, sma20_side, VIXY percentile <=40% / >=60%, VIXY falling / not rising, gap side.
- **Bot risk rules** (`sprint/engine.bot_risk`), applied in time order across all symbols of the run, using only trades closed before each entry:
  - skip a trade whose planned loss at 1 contract is above $50;
  - at most 4 trades a day;
  - after 2 losses in a row, a 10-minute cooldown from the second loss's exit ("A setups only" cannot be expressed for a single-setup run);
  - after 3 losses in a row, done for the day.
  - Streaks reset daily. A trade the risk pass removes cannot free its symbol for a signal that was skipped as "busy", so the pass is slightly conservative.
- **Keep rule:** a change survives only if it raises expectancy after costs on DEV and passes its own robustness checks (filters must also beat random day-skips). Then 3-5 finalists are frozen and run once on L1 and L2. If no failed-break version passes every robustness check, the report says "nothing held up" and no locked period is used.

## Amendment 3, 2026-10-31: learning when to trade, and several strategies as one book (written before any result)

Nick's goals (2026-10-31): several strategies at once for more trades a day, losses kept small and wins large, and a desk that learns from its own trades when each strategy works best. Built as tested research tools, not as live behavior:
- **Entry features** (`sprint/features.py`) are stamped on every trade from sprint run 3 on: time of day, weekday, ADX, efficiency, VWAP crosses, bar overlap, range vs ATR, relative volume, trend votes, DI spread, noise-trend count, gap, move so far, distance from VWAP, prior-day range, prior-day return (added before run 3, after Chart's in-sample look at v2-034), FOMC/CPI day, and the VIXY percentile. All are known at the end of the signal bar. Older trade files get the same values recomputed from cached bars, and a test checks the two match.
- **Learner** (`sprint/learn.py`): walk-forward by month, fit only on earlier months, scored only on later months.
  - Three fixed models: L2 logistic regression on win/loss, ridge regression on winsorized P/L, and a 12-cell time-of-day x day-type skip table.
  - **PASS** needs all four:
    - at least 60 trades taken;
    - out-of-sample expectancy above taking every trade;
    - a total above the 95th percentile of skipping the same number of trades at random;
    - PF above 1.0 at 2x slippage.
  - Each model counts as a trial.
- **Combined book** (`sprint/book.py`):
  - every session counts, including sessions with no trades;
  - reports per-sleeve and book metrics, correlation of daily P/L, and same-symbol overlaps;
  - optional desk daily stop that counts closed trades only.
- **Candidate rule for `tools/sprint_study.py auto`**:
  - base-cost DEV runs with at least 60 trades, PF >= 1.25 and PF 2x > 1.0;
  - the best expectancy per strategy family;
  - the book is shown with and without a $150 desk daily stop.
- **The journal** (phase 2, needs Nick's yes because it touches the live desk): the v4 paper ledgers stamp the same features at entry from the same code. The learner then retrains on backtest plus paper trades after each week. A learned skip rule reaches paper trading only after it passes on held-out data, through a new versioned ledger. The original ledger keeps running unchanged next to it.

## Amendment 4, 2026-10-31: Option Alpha's Top Backtests, the far out-of-the-money family (written before any run)

Option Alpha's Top Backtests list is the best of about 1.5 million saved user backtests, so its numbers are heavily selected. Its top ranks are 0DTE SPX/XSP options bought far out of the money at a fixed time and held to expiration:
- **Puts at about 0.06-0.10 delta, around 10:30.** Example: "0DTE Put Hedge", 1 contract, 196 trades, PF 4.91, average win $4.1K, average loss -$90. Filters: IV rank < 40, VIX <= 20 and not rising, day up, Wed-Fri only, skip CPI and monthly expiration.
- **Calls at 0.10 delta, at 11:00.** Example: "Long Call Bounce", 5 years, 97 trades, PF 4.67. Filters: VIX >= 17, VIX change <= 5, negative GEX; skip FOMC, NFP, triple witching and monthly expiration.

`sprint/specs/otm_v1.json` (54 runs, DEV) tests this family on SPY/QQQ/IWM:
- 10:30 and 11:00 entries, calls and puts as separate runs;
- |delta| 0.03-0.12 (target 0.07) and 0.06-0.15 (target 0.10): with $1 strikes a narrower band often holds no strike;
- held with a -95% stop and no target until 15:50 or 15:25;
- three filter sets: none, the put-hedge proxy (VIXY percentile <= 40%, VIXY not up > 1%, day up, Wed-Fri, skip third Friday) and the call-bounce proxy (VIXY percentile >= 60%, day down, skip third Friday; a down day stands in for GEX, which isn't available);
- plus +300/+500/+1000% take-profits.

The cost floor ($0.005 half-spread) binds on these cheap options. The same robustness checks apply, and "positive without the best 5 trades" is expected to be the hard one, since these payoffs come from a few big days. As a book sleeve, this family's value may be its correlation with the call setups rather than its own profit factor, which the combined-book tool measures.

## Amendment 5, 2026-10-31: the free 2016-2023 history check (written before any HIST pull, calibration or run)

Nick approved a free long-history check (no paid data). Alpaca has stock 1-minute bars from 2016 but no option prices before February 2024. So the sprint's surviving ideas are tested in two layers on **HIST = 2016-01-04 to 2024-01-31**.
- HIST ends the day before L2 (2024-02-01 to 2024-07-31) starts. L1 and L2 stay locked: never pulled for this, never run. The period guard refuses any range that touches them.
- Every rule below was chosen on DEV (Aug 2024 to Jun 2026). HIST is eight years those rules were never tuned on.
- Nothing here can promote a strategy. Layer 2 is modeled; promotion still needs real option prices and 40 forward paper trades (CLAUDE.md step 5).

### The six runs

The exact rules of the DEV runs, run by the same code. A test checks that each HIST config equals its DEV run's config.

| name | DEV run | rules (SPY, QQQ, IWM pooled) |
| --- | --- | --- |
| `fb` (reference) | setups_v2-001 | `failed_break` calls; delta 0.40-0.55 nearest 0.45; premium ceiling of the entry window (20/12/10%) held for the trade (time rule b); no target; all out 15:25 |
| `fb_or` | setups_v2-012 | the same with `failed_break_or` (opening-range lows only) |
| `otm_put_base` (twin) | otm_v1-010 | `time_1030` puts; delta 0.06-0.15 nearest 0.10; -95% stop; +9900% target (never reached in practice); all out 15:25; no filter |
| `otm_put` | otm_v1-011 | `otm_put_base` + vixy_pctl_le40, vixy_not_rising, day_up, wed_fri, skip_opex |
| `otm_bounce_base` (twin) | otm_v1-040 | `time_1100` calls; delta 0.03-0.12 nearest 0.07; exit as `otm_put_base` |
| `otm_bounce` | otm_v1-042 | `otm_bounce_base` + vixy_pctl_ge60, day_down, skip_opex |

### Data (pulled on Chart's computer)

- Stock 1-minute bars, 04:00-20:00 ET, for SPY, QQQ, IWM and VIXY, from 2015-11-01 (warm-up for prior-day levels, ATRs and the IV proxy) to 2024-01-31.
- These bars are **split-adjusted**. SPY, QQQ and IWM had no splits in these years, so nothing changes for them. VIXY had reverse splits; raw bars would turn each split day into a false "VIXY up 300%" day for `vixy_not_rising`.
- VIXY split-adjusted daily bars from 2014-11-01 to 2026-06-30 with L2 cut out, in one file. So the 252-close percentile has a full year before 2016-01-04, and the DEV validation reads the same file.
- No option request is ever made for a date before 2024-02-01.
- NYSE holidays and 1:00 PM early closes for 2015-2023 are added to `sprint/periods.py`. Early-close days use the 12:50 all-out, as in DEV.
- The proxies are DEV's: VIXY for VIX (`vixy_not_rising`), the VIXY percentile for IV rank.

### Layer 1: the stock signal (no option model)

Code: `sprint/underlying.py`, run by `tools/sprint_hist.py`, output `data/sprint/hist_layer1_<date>.md/.json`.
- The same entry and filter code as the engine (`sprint.entries.signals`, `engine._filters_ok` with the VIXY data), on stock-only day contexts with history from 2015-11-01.
- One position at a time per strategy and symbol, as in the engine.

**fb and fb_or** (calls, so a long stock position stands in):
- Entry: the open of the first bar after the signal bar (within 3 minutes, else skipped) + $0.01 half-spread.
- Stop: the signal's `invalid` level (the lowest low since the break) minus max($0.02, 0.05 x ATR(14, 1m) at the signal bar). Judged on finished 1-minute closes from the entry bar on. A close below it exits at the next bar's open - $0.01.
- Otherwise out at the close of the bar finishing at 15:25 (12:50 on early-close days) - $0.01.
- R = entry fill - stop. A signal with R <= 0 (it opened at or below the stop) is skipped and counted.
- Recorded: P/L in R and in %, and the max favorable excursion in R (highest high from the entry bar through the exit decision bar, minus the entry fill, over R).

**otm_put, otm_bounce and their twins** (no stop):
- Reference price: the close of the signal bar (10:30 or 11:00).
- Measured: the move to (a) the close at 15:25 and (b) the lowest low (puts) or highest high (calls) of the bars after the signal bar through 15:25. In % and in units of the **remaining-day sigma**.
- Remaining-day sigma = sigma_1m x sqrt(minutes from the end of the signal bar to 15:25). sigma_1m = realized volatility of regular-hours 1-minute log returns over the prior 20 sessions (at least 10 needed). Each return is between consecutive bars and is divided by the minutes between them. Prior sessions only. Moves are log moves.
- A **large drop** (puts) = the 15:25 close at least 1.5 remaining-day sigma below the reference. A **large rise** (calls) = at least 1.5 sigma above. The lowest-low / highest-high version is shown beside it, not used for the reading. (The close-to-15:25 move is what a held option is paid on.)

**Comparisons:**
- Matched random entries, 5 seeds (101-105). Each taken signal gets a random signal bar in the setup's window (finished bars 09:45-15:14, as the engine's random entries), same symbol, day and side. fb and fb_or keep the signal's stop distance (signal price - invalid), as the engine does.
- Random day-skips (filtered runs only): from the twin's days, 2,000 random subsets with as many days as the filtered run. p = share of subsets whose large-move rate is at or above the filtered run's.
- Reported overall; by year 2016-2023 (January 2024 shown apart); by stretch: 2018 Q1 volatility spike (2018-01-01 to 2018-03-31), 2020 Feb-May (2020-02-01 to 2020-05-31), 2022 bear market (2022-01-03 to 2022-10-12, the S&P 500's peak-to-trough); and by symbol.
- Metrics in R: trades, win rate, average win, average loss, expectancy, profit factor, max drawdown in R (time order), and a 95% interval of the expectancy (bootstrap by session, 2,000 draws).

**Pre-registered Layer-1 reading:**
- **fb, fb_or: "signal holds"** if expectancy in R is above 0 overall, above 0 in at least 6 of the 8 years 2016-2023, and above the expectancy of every one of the 5 matched-random seeds.
- **otm_put: "tail holds"** if the filtered days' large-drop rate beats random day-skips (p < 0.10), and is above that year's rate on all the twin's days in at least 5 of the 8 years. A year without filtered days counts as a miss.
- **otm_bounce: "bounce holds"** (added here, same shape, because its filter fires only in stressed years): the large-rise rate beats random day-skips (p < 0.10), and is above that year's all-day rate in at least half of the years with 5 or more filtered days. At least 3 such years are needed.
- The twins (`otm_put_base`, `otm_bounce_base`) are context: their large-move rate against matched random minutes. No pass/fail.

### Layer 2: modeled option P/L

Every Layer-2 number carries the label **MODELED (BS, calibrated IV)**.

**Modeled 0DTE tapes** (`sprint/modeled.py`, a generalization of `tests/sprint_synth.option_bars`):
- One implied vol per symbol, session, contract rule and side, for every strike, all day: IV = IV proxy x multiplier(rule, side).
- IV proxy, known at the open = sigma_1m (as in Layer 1, prior sessions only) x sqrt(525,600). That is the engine's calendar-minute year, so the proxy and the BS-EST IVs solved from real prices are on the same scale.
- Strikes: every $1 strike within ±6% of the underlying's close at the decision bar, built when the contract picker asks (point-in-time).
- Bars:
  - open = Black-Scholes at the stock's open, with the minutes to the close at the bar's start;
  - close = BS at the stock's close, with the minutes left at the bar's end;
  - high / low = BS at the stock's high / low (calls; low / high for puts) at the bar's end, widened to include the open and close;
  - rounded to $0.01 with a $0.01 floor; no bar where the stock has none.
- Expiry at 16:00 (13:00 on early-close days). r = 0, no dividends.
- Then the engine runs exactly as on real tapes: the contract picker (BS-EST delta from the modeled price), entry at the next bar's open + half-spread, the same exits. Bars only, so a stop fills at the stop price inside the bar, or at the open when the bar gapped through it.

**Costs:** the sprint's. Half-spread 2% of premium with a $0.005 floor, $0.65 per contract per side, PF at 2x slippage, and one 5% stress rerun of `hist_v1` (run ids end in `@s5`). The desk's logged chains (2026 spreads) are never used for modeled runs.

**Calibration on DEV** (`tools/sprint_calibrate.py`):
- Input: the real-tape DEV trade files of runs 1-3 on Chart's computer (`data/sprint/trades_*.csv.gz`; files of modeled specs are excluded), deduplicated by symbol, day, contract and signal bar.
- Ratio per trade = `iv_est` (BS-EST IV solved from the real option's price at the decision) / the IV proxy for that symbol and day.
- Multiplier = the median ratio **per contract rule and side**. Far out-of-the-money puts and calls sit on opposite sides of the volatility smile, so a pooled d06-15t10 number would price the puts too cheap.
- Quartiles and counts are reported, plus medians by symbol and by setup (information only).
- A rule-and-side key with fewer than 30 trades gets no multiplier, and a run that needs it is refused.
- Saved to `data/sprint/calib_modeled.json`.

**Validation on DEV** (`sprint/specs/hist_val_v1.json`: the same six runs on DEV with `"tapes": "modeled"`), against the real-tape runs in `docs/research/sprint_runs.csv`:
- **Pre-registered bar, per strategy:** the same sign of expectancy as the real run, AND the modeled PF within ±35% of the real PF (0.65 x real <= modeled <= 1.35 x real).
- A strategy that fails keeps its HIST Layer-2 numbers in the report, labeled **UNRELIABLE**, with no verdict.
- Known weak spots, stated now:
  - otm_bounce_base's real expectancy is +$0.08 (PF 1.009), so its sign test is close to a coin flip;
  - the multiplier is fitted on the same DEV data, so the validation checks the model's shape, not a prediction;
  - the first ~10 DEV sessions (Aug 2024) have no IV proxy (July 2024 is locked) and are skipped.

**HIST run** (`sprint/specs/hist_v1.json`: period HIST, history from 2015-11-01, six runs):
- Plus the runner's robustness pass: matched random entries (5 paths), one-step nudges, and random day-skips for the two filtered runs against their twins.

**Pre-registered Layer-2 reading** (validated strategies only). **"Holds on HIST (MODELED)"** needs all of:
- at least 60 trades;
- expectancy > 0 and PF >= 1.25 at base cost;
- PF > 1.0 at 2x slippage;
- profitable in at least 6 of the 8 years 2016-2023;
- positive without its best 5 trades;
- otm_put and otm_bounce: the filter beats random day-skips of its twin (p <= 0.05).

Also reported, not pass/fail: the 5% stress, the 95% interval, the deflated Sharpe with the full trial count, matched random entries, by stretch, by symbol, and Mon/Wed/Fri vs Tue/Thu.

**Idealizations, stated plainly:**
- Before November 2022, SPY, QQQ and IWM did not list an expiry every weekday. Layer 2 prices a 0DTE contract every session as if it existed. Results split into Mon/Wed/Fri vs Tue/Thu are an extra line.
- One flat IV per day: no smile across strikes and no intraday IV change. Real puts gain extra value when IV jumps in a selloff; real calls lose some when IV falls in a rally.
- Every minute has a price; real far-out-of-the-money contracts skip minutes.
- A 2% half-spread may be optimistic for 2016-2019, when 0DTE markets were thinner. The 5% stress is the check.

### What each outcome means (written before any result)

- **Layer 1 holds and Layer 2 holds:** the idea survives eight unseen years in the model. Next: keep the forward paper ledger, look for real option history. Nothing is promoted.
- **Layer 1 holds, Layer 2 fails:** the stock signal is real, but 0DTE options eat it (spread, decay). Next: test longer-dated options or shares.
- **Layer 1 fails:** the DEV result was most likely luck or one regime. The paper ledger keeps running for its 40 trades, with a "failed HIST" note.
- **Validation fails:** Layer 2 says nothing for that strategy; only Layer 1 counts.

### Build notes (2026-10-31, written while building, still before any HIST pull or run)

These pin down details the text above left open. None comes from a result.
- Matched random entries in Layer 1 keep the strategy's filters, checked at the random bar, exactly as the engine's random runs do. Random day-skips drop whole dates (all symbols of a date), as the engine's day-skip test does.
- The 5% stress rerun of `hist_v1` skips the robustness pass (`--no-robust`): it only shows how the headline numbers move with costs.
- Modeled tapes have a price every minute (at least $0.01). Real far out-of-the-money contracts can stop trading, and the real-tape engine drops such trades as VOID (12 next to otm_v1-010's 1,408 trades, 4 next to otm_v1-040's 1,418). This flatters the real far-OTM runs slightly next to the model; the validation bar is unchanged.
- HIST stock bars and VIXY bars are split-adjusted; DEV's (already pulled) stay raw. The two never share a month file.
- The HIST calendar: NYSE holidays and early closes for 2015-2023 in `sprint/periods.py`; sessions per year 252, 251, 251, 252, 253, 252, 251, 250 (2016-2023), checked against NYSE's published counts.

### Trials and run budget

- Layer 2 adds 18 rows to the run log: 6 validation, 6 HIST, 6 HIST at 5%.
- Layer 1 adds 6 measurements, in its own report.
- All of them count as trials.
- Nothing else runs on HIST. No rule or number changes after seeing HIST results; any change would be a new amendment, labeled in-sample.

## Amendment 6, 2026-10-31: why the ideas lose in some years. Regime rules found on 2016-2019, tested on 2020-2023 (written before any 2020-2023 look)

**Discovery set:** HIST 2016-2019 only, from run 4's trade file (`trades_hist_v1_2026-10-31.csv.gz`). Option P/L is MODELED (BS, calibrated IV); every feature is known at entry (sprint/features.py). Only feature-by-tercile tables were looked at, and nothing from 2020 on.
- **Failed-break calls lose in calm regimes.** VIXY percentile low/mid tercile: PF 0.17-0.56. High tercile: 0.93-1.08.
- **Failed-break calls do better after a down prior day.** fb_or, prior-day return low tercile: PF 1.17 vs 0.49-0.62. This matches DEV's learner weights and Chart's v2-034 look.
- **Far-OTM 0DTE options pay only on days that are already moving.** Range so far vs ATR, high tercile: PF 1.48 (10:30 puts), 1.62 (11:00 calls); low tercile 0.28 / 0.34. Relative volume, high tercile: PF 1.43 / 1.98.
  - The calm-day put filter (otm_put) points the opposite way, which fits its failure on 2016-2023.
- **Known model bias:** the model uses one flat IV per day (20-session realized vol x a multiplier). On days that are already moving, real 0DTE IV rises and the model doesn't, so it may flatter these rules. That is why DEV's real option prices are the deciding test.

**Nine candidate rules** (the thresholds are the discovery-set tercile cuts, frozen here). Each is a filter on the unfiltered run's trades; all nine count as trials.

| id | strategy (run) | rule |
|---|---|---|
| A | fb_or (hist_v1-002 / setups_v2-012) | f_vixy_pctl >= 0.443 |
| B | fb_or | f_prev_ret <= 0 (side-signed: the prior session closed down) |
| C | fb_or | A and B |
| D | 10:30 far-OTM puts, unfiltered (hist_v1-003 / otm_v1-010) | f_range_atr >= 0.52 |
| E | same | f_rvol >= 1.05 |
| F | same | D and E |
| G | 11:00 far-OTM calls, unfiltered (hist_v1-005 / otm_v1-040) | f_range_atr >= 0.61 |
| H | same | f_rvol >= 1.06 |
| I | same | G and H |

**Holdout 1: HIST 2020-01-01 to 2024-01-31, MODELED, evaluated once.** A rule passes only if all of these hold:
- at least 60 trades;
- PF >= 1.25 and PF at 2x slippage > 1.0;
- profitable in at least 3 of the 4 years 2020-2023 (years with 10+ trades);
- still positive without its best 5 trades;
- its total beats removing the same number of trades by random whole days (2,000 draws, seed 17), p < 0.05.

**Holdout 2: DEV 2024-08 to 2026-06, real option prices (Chart),** only for rules that pass holdout 1. It runs on the run-1-3 trade files, which carry the same features. Pass: PF >= 1.25, PF 2x > 1.0, at least 40 trades, and beats random day-skips p < 0.10.

A rule that passes both becomes a frozen finalist for L1/L2 (each run once). If none passes, the report says so and nothing changes on the desk.

**Holdout 1 result** (evaluated once, 2026-10-31; MODELED; numbers in SPRINT_RESULTS_5.md):
- PASS: F (10:30 puts, range and volume), G, H and I (11:00 calls).
- Fail: A, B and C (failed-break calls).

**Learner, same session.** The walk-forward learner from Amendment 3 was run unchanged on the HIST trade file, with 24 months of training before its first out-of-sample month. Its logit model passed on both far-OTM runs (10:30 puts and 11:00 calls) and failed on fb_or.

**Holdout 2 adds one pre-registered learner test** (written before any DEV look): fit the same logit model (Amendment 3 settings) on ALL HIST trades of the run, then score that run's DEV real-price trades with it. Take a trade when P(win) >= 0.5. It must meet the same holdout-2 bar as the rules.

**Run ids:**
- HIST: hist_v1-003 / hist_v1-005.
- DEV real prices: otm_v1-010 (10:30 puts, d06-15t10, 15:25) and otm_v1-040 (11:00 calls, d03-12t07, 15:25).

## Amendment 7, 2026-10-31: frozen finalists and the locked-period exam (written after holdout 2, before any L1/L2 pull or run)

**Holdout 2 result** (Chart run 5, DEV real option prices; SPRINT_RESULTS_5.md):
- PASS: H (11:00 far-OTM calls with f_rvol >= 1.06): 485 trades, PF 2.35, PF 2x 2.10, p 0.0045.
- PASS: L-call (logit fit on HIST hist_v1-005, applied to DEV): 504 trades, PF 1.93, PF 2x 1.73, p 0.083.
- Fail: F, G, I and L-put.
- Both passes are negative without their best 5 trades.

**Finalists (frozen, nothing tuned after this point):**
- **FIN-H:** the otm_v1-040 rules, plus a filter that the relative volume at the signal bar is at least 1.06. That relative volume is daytype `rvol`, the value stamped as `f_rvol`.
- **FIN-L:** the otm_v1-040 rules, plus the Amendment 3 logit fit once on ALL HIST hist_v1-005 trades. Its weights and preprocessing are saved to a committed JSON with its sha256. A trade is taken when P(win) >= 0.5 from the entry features.
- **Reference:** otm_v1-040 unfiltered on the same period.
- **otm_v1-040 rules:** 11:00 bar signal, calls, |delta| 0.03-0.12 nearest 0.07, -95% stop, no target, all out 15:25, SPY + QQQ + IWM, desk fills, 2% half-spread, $0.65 per contract per side.

**The exam:**
- The spec is committed with its sha256 and run once on L2 (2024-02-01 to 2024-07-31) and once on L1 (2026-07-01 to 2026-10-30), through the existing `--locked <name> --frozen <sha256>` guard.
- A 5% half-spread rerun is information only.
- Features need VIXY daily closes up to each prior session; the locked-period run may read them.

**Pass, per finalist and per period:**
- at least 30 trades on L2 and at least 20 on L1;
- PF >= 1.25 and PF at 2x slippage > 1.0;
- expectancy above the unfiltered reference's on the same period.

**Verdict:**
- **Holds:** passes on both L2 and L1. It then becomes a new versioned PAPER ledger and needs 40 forward trades under CLAUDE.md step 5. Never real money without Nick's explicit yes.
- **Mixed:** passes on one period. It's reported as such and not promoted.
- **Fails:** dropped.
- Without-best-5, by symbol and by month are reported for both periods whatever the verdict.

## Amendment 9, 2026-11-01: the 10-year strategy factory (written before any factory run, rule search or learner fit)

Nick's request (2026-11-01): run every strategy we have code for across the full ~10 years, give separate statistics for each one, apply the same "learn when it works / skip the losing conditions" process to each, and show how the survivors do together as one book. Branch `sprint/factory`. Research only: nothing here trades or touches the desk.

### Periods and data

- **HIST** = 2016-01-04 to 2024-01-31: Alpaca stock bars (run 4's pull), option prices **MODELED (BS, calibrated IV)** with run 4's calibration (`data/sprint/calib_modeled.json` on Chart's computer; its sha256 is printed in the run log). History from 2015-11-01 feeds indicators only.
- **DEV** = 2024-08-01 to 2026-06-30: **REAL** Alpaca option prices (runs 1-3's pull).
- L1 and L2 are never pulled or run. No new pull: every file needed is already on Chart's computer.
- Costs: desk fills, 2% half-spread with the $0.005 floor (the pre-registered MODELED-SPREAD; the DEV run is pointed at an empty chains folder so logged 2026 chains are never used), $0.65 per contract per side, 1 contract. PF 2x = the 2x-slippage P/L already stamped on every trade.

### The 21 runs (SPY + QQQ + IWM pooled in each run; one position at a time per run and symbol)

| # | name | entry | side | exit | contract |
|---|---|---|---|---|---|
| 1 | noise (reference) | `noise` | both | the noise ledger's own exit: stop `noise` (close through max/min(band, VWAP) at the half-hour checks, reversal, 20% premium ceiling every minute), no target, time b, all out 15:25 | d55-75t65 |
| 2-4 | orb15, orb30, orb60 | `orb15/30/60` | both | **plain**: the entry window's premium ceiling (20/12/10%, costs included) held for the whole trade (time b), no target, no trail, all out 15:25 | d40-55t45 |
| 5-7 | vwap_macd, pd_retest, flush | same names | both | plain | d40-55t45 |
| 8 | failed_break | `failed_break` | calls | plain | d40-55t45 |
| 9 | failed_high | `failed_high` | puts | plain | d40-55t45 |
| 10-15 | otm_c_1000, otm_c_1030, otm_c_1100, otm_c_1200, otm_c_1300, otm_c_1400 | `time_1000/1030/1100/1200/1300/1400` | calls | fixed -95% stop, +9900% target (never reached in practice), desk mechanics, all out 15:25 | d03-12t07 |
| 16-21 | otm_p_1000 ... otm_p_1400 | the same six times | puts | the same | d06-15t10 |

- **New time entries** (added to `sprint/entries.py` TIME_ENTRIES with this amendment, the same rule as `time_1030` / `time_1100`): `time_1000` = the bar that finishes at 10:00 (index 29), `time_1200` = 149, `time_1300` = 209, `time_1400` = 269. A signal every session on that bar, none when the bar is missing or within 2 bars of the close (so no 13:00 or 14:00 signal on 1:00 PM early-close days). `time_1030` (59) and `time_1100` (89) are unchanged.
- **Specs:** `sprint/specs/factory_hist_v1.json` (HIST, `"tapes": "modeled"`) and `sprint/specs/factory_dev_v1.json` (DEV, real tapes): the same 21 runs in the same order (a test checks this), run ids `factory_hist_v1-001..021` and `factory_dev_v1-001..021`. No pass-2 robustness in these specs (`top_k` 0): the factory does its own checks.
- **Known before any result:**
  - A run with both sides takes one position at a time per symbol, so an opposite-side signal while a trade is open is skipped as busy. The noise run's reversal exit therefore does not flip into the other side (setups_v1 ran the noise ledger's two sides as separate runs).
  - The DEV numbers of most of these runs, unfiltered, were seen in runs 1-3 (orb_exits_v1 plain, setups_v1, setups_v2, otm_v1); only the 10:00, 12:00, 13:00 and 14:00 far-OTM runs are new on DEV. No rule in this amendment is chosen on DEV.
  - **Not independent:** failed_break calls, 10:30 far-OTM puts and 11:00 far-OTM calls are hist_v1-001/003/005. Amendment 6 already looked at their 2016-2019 terciles and their 2020-2023 holdout, and run 5 at their DEV holdout. Their factory verdicts are reported but labeled "seen before (Amendment 6)": they are not new evidence.
  - **Model validation:** run 4 checked the MODELED tapes against real prices for failed-break calls (plain exit), 10:30 puts (d06-15t10) and 11:00 calls (d03-12t07), all PASS. Every other strategy's HIST numbers are **NOT VALIDATED** against real prices (labeled so); holdout 2 on real DEV prices is the deciding test for each of them. The noise exit's every-minute 20% ceiling acts on modeled bar highs and lows (BS from the stock's high/low, one flat IV per day).
  - **Known model bias:** one flat IV per day. On days that are already moving, real 0DTE IV rises and the model's doesn't, which flattered the far-OTM put rules in Amendment 6 (they passed the modeled holdout and failed on real prices). Expect the same for every far-OTM put rule here.

### Per strategy (the same procedure for each of the 21; `tools/sprint_factory.py` + `sprint/factory.py`)

Inputs: the two trade files (`data/sprint/trades_factory_hist_v1_<date>.csv.gz` and `trades_factory_dev_v1_<date>.csv.gz`, the newest of each). Every trade carries the entry features stamped by the engine (sprint/features.py); they are recomputed from cached bars only for a row that lacks them.

**(a) All days.** Per period (HIST MODELED / DEV REAL) and per year: 2016 ... 2023, Jan 2024 (MODELED), Aug-Dec 2024 (REAL), 2025, Jan-Jun 2026 (REAL). 2024 is never one number: its two parts come from different price sources. Reported: trades, trades per session (NYSE sessions in the window, sprint/periods calendar), win % (pnl > 0), average win, average loss (pnl < 0), expectancy, PF, PF 2x, total, max drawdown (cumulative P/L in trade order), total without the best 5 trades, months green (months with trades whose net is > 0, out of months with trades), by symbol and by side.

**(b) The rule (found on 2016-2019 only).**
- Discovery = HIST trades dated 2016-01-04 to 2019-12-31.
- Six features, in this order: `f_rvol`, `f_range_atr`, `f_vixy_pctl`, `f_prev_ret`, `f_gap`, `f_day_ret`.
- Tercile cuts per feature = `numpy.quantile(values, [1/3, 2/3])` (linear interpolation) over the discovery trades that have a value. "keep top tercile" keeps trades with value >= the upper cut; "keep bottom tercile" keeps value <= the lower cut. A trade without a value is not kept.
- 12 candidates per strategy. A candidate needs at least 60 discovery trades kept. The chosen rule = the highest discovery PF (a PF with no losing trade ranks first); ties go to more trades, then to the order above (features in order, top before bottom). No candidate with 60 trades = no rule.
- The rule (feature, side, cut at full precision) is then frozen and applied unchanged to every later trade. Nothing dated 2020 or later can change it (a test checks this).
- **Holdout 1** = HIST 2020-01-01 to 2024-01-31 (MODELED). Pass needs all of Amendment 6's bar:
  - at least 60 trades;
  - PF >= 1.25 and PF 2x > 1.0;
  - profitable in at least 3 of the 4 years 2020-2023, a year counting only with 10+ trades;
  - total without the best 5 trades > 0;
  - beats random whole-day removal, p < 0.05: from the strategy's unfiltered holdout-1 trades, remove random whole sessions (a random order of the sessions, removed until at least as many trades are gone as the rule removed), 2,000 draws, seed 17; p = the share of draws whose remaining total is at or above the rule's total (the method of `tools/sprint_regime.day_skip_p`).
- **Holdout 2** = DEV (REAL prices), Amendment 6's holdout-2 bar: at least 40 trades, PF >= 1.25, PF 2x > 1.0, and random whole-day removal p < 0.10 (2,000 draws, seed 23, as `tools/sprint_regime.py`). It counts only for a rule that passed holdout 1; its numbers are shown for every rule, labeled.
- A rule **survives** when it passes both holdouts. Its per-year stats are reported on all years (2016-2019 labeled in-sample for the rule).

**(c) The learner.** `sprint/learn.walk_forward` exactly as pre-registered in Amendment 3, over the strategy's HIST + DEV trades together, with 24 training months (monthly refit on earlier months only; out-of-sample from the 25th month with trades, 2018-01 for a strategy that trades every month). Models logit, ridge and buckets, each with Amendment 3's pass rule (at least 60 trades taken, out-of-sample expectancy above taking every trade, total above the 95th percentile of 200 random skips with seed 7, PF 2x > 1.0).
- The factory needs each trade's take/skip decision for per-year and DEV-only numbers. It re-runs walk_forward's monthly loop with the same functions of sprint/learn.py on a precomputed feature matrix (much faster on 7,000-trade runs); a test checks that its decisions and results equal `learn.walk_forward`'s exactly.
- Reported: each model's walk-forward result, the logit's per-year stats, and each model's DEV-only segment (its out-of-sample decisions on DEV trades, real prices).
- A model **survives** only if it passes walk_forward's rule AND its DEV-only segment has at least 40 trades, PF >= 1.25 and PF 2x > 1.0.

**(d) Verdict.** The candidates are the rule (if it survives) and every surviving learner model. The chosen variant = the highest DEV-real expectancy (ties: rule, then logit, ridge, buckets). None survives = "none". The report gives the first failed check for every variant that was dropped.

**Multiple testing (information, not a pass bar):** the deflated Sharpe of each chosen variant's DEV daily P/L (every DEV session, 0 on days without a trade; sprint/report.deflated_sharpe), with N = the trials counted by the run logs plus this amendment's rule and learner trials, and the trial-Sharpe variance taken over every DEV variant the factory scores (21 unfiltered runs, 252 candidate rules, 63 learner models).

### The book (all survivors together)

- Sleeves: each strategy whose verdict is not "none", trading its chosen variant, 1 contract per signal. A rule sleeve takes the rule's trades in every year; a learner sleeve takes its out-of-sample picks only (none before its first out-of-sample month).
- `sprint/book.py`: every session counts (P/L 0 on days without a trade), sleeves' daily P/L, correlation of daily P/L, same symbol and side held at the same time in two sleeves, and a second view with the $150 desk daily stop (closed trades only).
- Windows, never mixed without a label:
  - (i) 2018-01-02 to 2024-01-31, HIST, **MODELED**;
  - (ii) 2024-08-01 to 2026-06-30, DEV, **REAL**;
  - per year 2018 ... 2023, Jan 2024 (MODELED), Aug-Dec 2024, 2025, Jan-Jun 2026 (REAL);
  - one combined line labeled **"mixed: modeled 2018-2024 + real 2024-2026"** over the sessions of (i) and (ii) together (the locked Feb-Jul 2024 is not in it).
- Per window: total, average per year (total / (sessions / 252)), trades per session, max drawdown on the daily equity curve, worst calendar month, months green (calendar months in the window with net > 0, out of all its months), daily Sharpe (mean / std x sqrt(252)), and the same by sleeve.
- Rule sleeves in 2018-2019 are inside their discovery years: labeled in-sample. 2020 onward is out-of-sample for every sleeve.
- **Contrast:** the "everything unfiltered" book = all 21 runs, every trade, the same windows.

### Outputs and trials

- `data/sprint/factory_<date>.md` (one section per strategy, then the book) and `factory_<date>.json` (every number).
- **Trials added by this amendment: 357** = 42 runs (21 on HIST + 21 on DEV) + 252 candidate rules (12 x 21) + 63 learner models (3 x 21). The holdout evaluations are of rules already counted.
- No rule, cut, threshold or book setting changes after seeing factory results. Any change is a new amendment, labeled in-sample. A surviving variant is still research: it reaches paper trading only through a new versioned ledger after Nick's yes, and promotion still needs CLAUDE.md step 5 (40 forward paper trades); L1/L2 stay reserved for frozen finalists.

## Amendment 10, 2026-11-01: round 8, steady daily rules plus a sharper big-day filter (written before any round-8 code or run)

Amendment 8 lives on `sprint/exits` (the locked-exam finalists); this branch skips the number so the two merge cleanly. Branch `sprint/round8`, from `sprint/factory` at `31860f5`. Research only: nothing here trades or touches the desk.

Nick's request (2026-11-01): keep the big-day calls (FIN-H family). Try to make the program spot the big days and skip the rest. Also research strategies beyond ORB that make steadier, simple, repeatable money through the days, so a combined book pays out more consistently and can be sized up.

Run 7's lesson, recorded before any round-8 result:
- The only surviving family is far-OTM calls on busy days.
- On real prices the four survivors win on the same days: daily correlation 0.95-0.99, and 2025-04-09 carries the book.
- Steadier payouts need rules that win on *different* days. A lottery-shaped long-option rule can't be steady on its own: long 0DTE premium loses a little most days by construction.
- So Part A tests steady rules in **shares**, on 10 years of real stock bars with no option model.

### Data and periods

- **Stock tests (Part A):** real Alpaca 1-minute bars for SPY, QQQ and IWM over HIST 2016-01-04 to 2024-01-31 and DEV 2024-08-01 to 2026-06-30. These files are already on Chart's computer.
  - L1 (2026-07-01 to 10-30) and L2 (2024-02-01 to 07-31) are never pulled or read.
  - History from 2015-11-01 feeds indicators only.
- **Option tests (Part B, Part A's option twin):** as Amendment 9. HIST options are **MODELED** (run 4's calibration); DEV options are **REAL** Alpaca prices. The same 2% half-spread with the $0.005 floor and $0.65 per contract per side.
- **Share costs:** fill at the open of the bar after the decision bar, +$0.01 per share for a buy and -$0.01 for a sell (half-spread plus slippage). No commission. "2x costs" = $0.02 per side.
- **Share sizing:** $10,000 notional per trade, shares = floor(10,000 / the decision bar's close). Results in $ and in bps of notional. One position at a time per rule and symbol.
- **Exit time for shares:** the close of the bar finishing 15:59 (index 389) +/- $0.01, or 12:59 (index 209) on 1 PM early-close days. Shares may trade to the close: the desk's 15:25 all-out is the 0DTE options rule. Option twins keep 15:25.

### Part A: steady rules in shares (rules from the sources, frozen, no tuning)

**A1 `noise_sh`: Beat the Market** (Zarattini, Aziz & Barbon 2024; registry #1; the paper's final version).
- Noise: sigma(t) for minute index t = the mean over the 14 prior sessions (at least 10) of |close(t) / that session's open - 1|.
- Bands:
  - UB(t) = max(open, prior close) x (1 + sigma(t));
  - LB(t) = min(open, prior close) x (1 - sigma(t)).
- Checks at the bars finishing 10:00, 10:30, ..., 15:30 (indices 29, 59, ..., 359):
  - flat: close > UB -> long; close < LB -> short;
  - long: close < LB -> reverse to short; else close < max(UB, VWAP) -> flat;
  - short: mirrored (close > UB -> reverse to long; else close > min(LB, VWAP) -> flat).
- VWAP is regular-hours, from 09:30.
- Primary variant: long and short, $10,000 notional.
- Secondary variant (vol-sized, the paper's sizing): notional = 10,000 x min(4, 0.02 / sd), where sd = the sample standard deviation of the 14 prior daily close-to-close returns.
- The paper reports 2007 to Apr 2024, net: 100% sizing Sharpe 1.24, hit ratio 43%, 1.8 trades a day. Vol-sized Sharpe 1.33, with 2016 -12.8% and 2017 -6.9%.

**A2 `last30`: market intraday momentum** (Gao, Han, Li & Zhou 2018 JFE; Baltussen, Da, Lammers & Martens 2021 JFE; registry #2-3).
- Primary (Baltussen's "rest of day" signal): r = close of the bar finishing 15:30 (index 359) / prior close - 1.
  - r > 0: buy at the open of index 360. r < 0: sell short. Exit at the close of index 389.
  - One trade a day. No trade on early-close days, or when r = 0.
- Secondary (Gao's first half-hour signal): r1 = close of index 29 / prior close - 1, same trade window.
- Shares only: a 15:30-16:00 trade can't be an option twin under the desk's 15:25 all-out.

**A3 `gapfade_vix`: overnight gap fade on stressed days.**
- Source: falsifylab 2025, a blog test on about 2 years: Sharpe 1.1-1.15, random-date p = 0.005, low VIX loses. Source grade **C**, exploratory.
- Context: the overnight-versus-intraday reversal literature (Lou, Polk & Skouras 2019 JFE, cross-sectional).
- This 10-year test is the large-sample check CLAUDE.md step 1 asks for; a pass would still be labeled exploratory.
- Gap g = open / prior close - 1. Gap z = g / the sample sd of the 60 prior sessions' gaps (at least 40).
- VIX proxy z = (VIXY's prior-session close - the mean of the 60 closes before it) / their sample sd.
- Trade when |gap z| > 1.0 and the VIXY z > 0.5. Direction against the gap.
- Enter at the open of index 60 (after the bar finishing 10:30). No stop; exit at the close of index 389.
- **Option twin on DEV, REAL:** calls for longs, puts for shorts, contract d55-75t65, no stop, all out 15:25.

Every Part A rule is also reported **long-only**, since Nick's account may not short shares. Shorts can be carried by puts, as in A3's twin. A2's VWAP-trend cousin (Zarattini & Aziz 2023) is not tested. Its replications fail after costs, and it flips many times a day, so it is not simple to hand-trade.

**Part A pass bar.** Per rule, primary variant, SPY + QQQ + IWM pooled, base costs unless stated:
1. at least 300 trades over the 2016-2026 windows;
2. expectancy per trade > 0 at 2x costs;
3. profitable in at least 6 of the 8 years 2016-2023, and in DEV 2024-08 to 2026-06;
4. the bootstrap 95% interval of the daily mean P/L is above 0 (all sessions, 0 on days without a trade; resampled by session, 2,000 draws, seed 29);
5. positive without the best 5 days;
6. beats random direction, p < 0.05: the same entries and exits with a coin-flip side, 200 draws, seeds 31-230; p = the share of draws with a total at or above the rule's;
7. **steadiness:** at least 55% of months green (months with at least one trade, 2016-2026).

Reported per rule:
- by year and by symbol;
- long-only, with its own pass line;
- months and weeks green;
- the longest run of losing months;
- the worst month;
- trades per day;
- daily correlation with FIN-H.

### Part B: a sharper big-day filter for the far-OTM calls (FIN-H family)

Sleeves: the run-7 rule sleeves otm_c_1030, otm_c_1100 (= FIN-H) and otm_c_1200: d03-12t07, -95% stop, all out 15:25, f_rvol >= 1.06. Trade files: run 7's HIST and DEV factory files, so no new option run.

**B1 new entry features**, known at the end of the decision bar, added to sprint/features.py:
- `f_ret5d`: side-signed % return over the 5 sessions to the prior close.
- `f_dd20`: prior close vs the highest close of the 20 prior sessions, %.
- `f_vixy_chg1`: VIXY's prior close / the close before it - 1, %.
- `f_vixy_z20`: VIXY's prior close, z vs the 20 closes before it.
- `f_or30_atr`: the 09:30-10:00 range / daily ATR.
- `f_gap_abs`: |gap| %.
- `f_hod`: 1 if the decision bar's close is at or above every earlier high of the session.

Run 7's trades are re-stamped from cached bars (features.recompute style); trade P/L is unchanged.

**B2 confidence sizing.**
- sprint/learn.walk_forward's logit (Amendment 3 settings, 24 training months), on the 18 existing plus 7 new features, over each sleeve's rule trades.
- At every monthly refit, take the terciles of the training trades' predicted probabilities.
- Then, out-of-sample: bottom tercile -> skip, middle -> 1 contract, top -> 2 contracts.
- **Pass, per sleeve:** on DEV (REAL, out-of-sample decisions) and on 2018-01 to 2024-01 (MODELED, walk-forward), all of:
  - (a) P/L per contract traded is above the flat 1-contract rule's;
  - (b) daily Sharpe is above the flat rule's;
  - (c) PF 2x > 1.0.

**B3 "wait for proof" entry `newhigh_c`** (calls, new in sprint/entries.py).
- Signal: the first finished bar with index 89-269 (11:00-14:00) whose close is above every earlier high of the session, with f_rvol >= 1.06 at that bar. One per day per symbol.
- Trade: d03-12t07, -95% stop, all out 15:25.
- There is no fitted parameter (the 1.06 cut is FIN-H's frozen cut), so there is no discovery split.
- **Pass:**
  - HIST 2016-2023 (MODELED): at least 60 trades, PF >= 1.25, PF 2x > 1.0, profitable in at least 5 of 8 years, positive without the best 5 trades;
  - DEV (REAL): at least 40 trades, PF >= 1.25, PF 2x > 1.0.
- Reported beside FIN-H on the same days: win rate, average loss, total without the best day.

### The book

- Sleeves: FIN-H (1 contract), each Part B variant that passes, and each Part A rule whose primary or long-only variant passes. Shares at $10,000 notional per trade.
- **A Part A rule counts as adding steadiness only if its daily P/L correlation with FIN-H is below 0.3** (sessions both could trade).
- Windows as Amendment 9: 2018 to Jan 2024 MODELED for option sleeves (shares are real throughout), DEV REAL, and a labeled mixed line.
- Reported:
  - total and per year;
  - max drawdown;
  - months green and weeks green;
  - the longest losing-month run;
  - the worst month;
  - each sleeve's share of the total;
  - the correlation matrix.

### Trials and outputs

- **Trials added by this amendment:**
  - Part A: 3 rules, 2 sides each (long-short, long-only), plus 2 secondary variants (vol-sized A1, Gao A2) = 8;
  - A3's option twin = 1;
  - Part B: 3 sleeves x B2 + B3 = 4.
  - Total 13. Deflated Sharpe (information) uses the run logs' count + 13.
- Outputs: `data/sprint/round8_<date>.md` and `.json`, the share trade file `data/sprint/trades_round8_shares_<date>.csv.gz`, and the B3 HIST/DEV option trade files.
- No rule, cut or threshold changes after results. A change is a new amendment, labeled in-sample.
- A pass is still research: it reaches paper trading only through a new versioned ledger after Nick's yes, and promotion needs CLAUDE.md step 5.

### Addendum 10.1, 2026-11-01: not only 0DTE, and selling before 15:25 (written before any round-8 code finished or any round-8 run)

Nick (2026-11-01): "maybe for better wins more consistent not only 0DTE would be good" and "we can sell those contracts whenever, they don't have to be held till the end".

Recorded before any result:
- Earlier runs already showed that early profit-taking on 0DTE far-OTM calls and on failed-break calls cut the few winners that pay for everything:
  - run 2: every early exit on failed-break lost;
  - run 3: +300/+500/+1000% targets on far-OTM gave PF 0.50-0.70.
  Those runs were in-sample on DEV. The tests below are the clean 10-year version.
- Next-expiry contracts keep overnight time value at 15:25, so a losing day should lose less than 0DTE. They also pay less on a big day.
- Weekly expiries (5-10 days) need a new option pull. That goes to round 9 with the single-stock pull; the next-expiry bars are already on Chart's computer (runs 2-3, 479 sessions per symbol).

**B4 FIN-H on next-expiry contracts, with exits that can sell early.**
- Entry: FIN-H's own (time_1100 calls, SPY + QQQ + IWM, taken only when f_rvol >= 1.06).
- New contract rule `n1d03-12t07`: the next expiry after today, BS-EST |delta| 0.03-0.12 nearest 0.07. Same band as d03-12t07; BS time includes the calendar days to the next expiry, as n1d40-55t45 does.
- Four exits, all with all out 15:25:
  - (i) fixed -95% stop, no target (FIN-H's own);
  - (ii) fixed -50% stop, no target;
  - (iii) fixed -50% stop plus trail `gb50` (give back at most 50% of the peak open profit, sprint/sim.py);
  - (iv) fixed -50% stop plus fixed target +100%.
- **The same four exits on FIN-H's 0DTE contract (d03-12t07)**, so "sell early" is judged on the ledger Nick is paper trading.
- HIST twins are MODELED. The next-expiry modeled tapes were never validated against real prices (labeled NOT VALIDATED); DEV REAL decides.
- **Pass** (per variant): B3's bars (HIST 2016-2023: at least 60 trades, PF >= 1.25, PF 2x > 1.0, profitable in 5 of 8 years, positive without the best 5 trades; DEV: at least 40 trades, PF >= 1.25, PF 2x > 1.0).
- **"Steadier than FIN-H"** additionally needs, on DEV REAL against FIN-H 0DTE exit (i) on the same days:
  - more months green;
  - a total without the best day above FIN-H's (+$57.82);
  - a smaller average loss.

**A-opt: the steady share rules carried by options, exiting on the rule's own signal** (DEV, REAL; reported beside the shares, CLAUDE.md step 3):
- A1 `noise_sh` on 0DTE d55-75t65, and on next expiry with the new rule `n1d55-75t65` (|delta| 0.55-0.75 nearest 0.65).
  - Exits are the share rule's own: band/VWAP stop and reversal at the half-hour checks. No premium line; all out 15:25.
  - Calls carry longs, puts carry shorts.
- A3 `gapfade_vix` on next expiry `n1d55-75t65` (its 0DTE twin is already in Amendment 10).
- A2 can't be carried: its 15:30-16:00 window is after the options' 15:25 all-out.
- **Pass:** at least 40 trades, PF >= 1.25, PF 2x > 1.0, expectancy > 0.

**Trials added by this addendum:** B4 4 exits x 2 contracts = 8; A-opt 3. That makes 11, and round 8 totals 24 (the deflated Sharpe uses the run logs' count + 24).

### Addendum 10.2, 2026-11-01: classic indicator setups with a +30% take-profit (written before any round-8 code finished or any round-8 run)

Nick (2026-11-01): "look at indicators too, I believe those have good setups sometimes, and we can TP at like 30% or something every time just to maximize profit and enter at good times".

Recorded before any result:
- **Marshall, Cahan & Cahan 2008** (J. Empirical Finance 15(2)): 7,846 popular technical rules on US equity intraday data; none profitable after two bootstrap data-snooping corrections.
- **Schulmeister 2009** (Review of Financial Economics 18(4)): 2,580 momentum/reversal models on the S&P 500. Daily models have been unprofitable since the early 1990s. 30-minute models averaged 7.2% a year gross from 1983 to 2007, weaker in 2001-2007.
- The desk's own `vwap_macd` (an indicator setup) failed in run 7: HIST PF 0.68, DEV PF 0.89, options.
- **The cost arithmetic.** A +30% target with the desk's -20% premium line, on near-the-money 0DTE options at the 2% half-spread plus $0.65 per side, nets about +25% on a win and -25% on a loss. So it needs about a 50% win rate just to break even.
- Expectation: most indicator rules will not beat random entries after costs. This test is the clean 10-year check.

**D: four textbook indicator rules, default settings, no tuning.**
- Bars: 5-minute regular-hours bars built from the 1-minute bars, aligned to 09:30 (the first bar finishes 09:35).
- Indicators run on the continuous series of regular-hours 5-minute closes, prior sessions included, so they are warmed up by the first decision.
- Decisions at the close of a finished 5-minute bar finishing 09:45 to 15:00. Entry at the open of the next 1-minute bar. One position at a time per rule and symbol.
- The rules:
  - **D1 `ind_rsi`:** RSI(14, Wilder smoothing) crosses up through 30 -> long; crosses down through 70 -> short.
  - **D2 `ind_bb`:** Bollinger Bands (20, 2 x the population sd). A close back above the lower band after the previous close was below it -> long; mirrored at the upper band -> short.
  - **D3 `ind_ema`:** EMA(9) crosses above EMA(21) -> long; below -> short.
  - **D4 `ind_macd`:** MACD(12, 26, 9) line crosses above its signal line -> long; below -> short.
- **Shares first** (Part A's data, costs, $10,000 notional and exit time). Exit on the same rule's opposite signal, which also reverses into it, or at the close of index 389. Long-only reported too.
  - Pass = Part A's 7-item bar.
- **Option twins** (HIST MODELED, DEV REAL). Calls carry longs, puts carry shorts.
  - Contracts: 0DTE `d40-55t45` (its modeled tapes passed run 4's check for calls) and next-expiry `n1d40-55t45`.
  - Two exits, both with all out 15:25:
    - (i) **TP30:** fixed target +30% of the debit, fixed stop -20%;
    - (ii) **signal:** the opposite signal or the -20% stop.
  - Pass: B3's bars (HIST 2016-2023: at least 60 trades, PF >= 1.25, PF 2x > 1.0, profitable in 5 of 8 years, positive without the best 5 trades; DEV: at least 40 trades, PF >= 1.25, PF 2x > 1.0).
  - Win rate and break-even win rate are reported beside each.
- Every D variant gets matched random entries (Part A's random-direction test on shares; same days and times with a random side for options).

**Trials added by this addendum:**
- shares: 4 rules x 2 sides = 8;
- options: 4 rules x 2 contracts x 2 exits = 16.

That makes 24, and **round 8 totals 48** (the deflated Sharpe uses the run logs' count + 48).

### Addendum 10.3, 2026-11-01: indicators combined with levels, and a tuned stop (written before any round-8 code or run)

Nick (2026-11-01): "I'm not too sure on the 20% stop loss, you can tweak that around to find out what works best. Indicators alone don't work good, but pairing them with levels of resistance and other indicators together could work good."

Recorded before any result:
- Tuning a stop on the same data it is judged on is curve-fitting. So the stop and target are **chosen on 2016-2019 only**, frozen, and judged on 2020 to Jan 2024 (MODELED) and on DEV (REAL), the way the factory chose its rules.
- `failed_break` is already a level-based reversal setup, and it failed on 2016-2023 (runs 4-7). The confluence rules below add the indicator confirmation it lacked.
- They are **designed tests of Nick's idea**, with no published source (CLAUDE.md step 1: "design a pre-registered test for it"). So the made-up-levels benchmark below must also be beaten.

**D5 `conf_level_rsi`: a level plus RSI** (5-minute bars and decision window as Addendum 10.2; levels from sprint/levels.py, known at the decision).
- Support = PDL, PML, OR30L, VWAP-2, VAL, PWL. Resistance = PDH, PMH, OR30H, VWAP+2, VAH, PWH.
- Long: the decision bar's low is at or within 0.10 x ATR(14, 5-minute) of a support level (or traded through it), RSI(14) at that bar <= 30, and the bar closes above that level. Short: mirrored at resistance, with RSI >= 70.
- If two levels qualify, the nearest to the close counts.
- **Made-up-levels benchmark:** the same rule on `LevelMap.fake(seed)` for seeds 1-5. The real levels must beat every seed's expectancy, or levels add nothing.

**D6 `conf_trend_pullback`: trend plus pullback plus momentum.**
- Long: the 5-minute close > VWAP, EMA(9) > EMA(21), the bar's low at or within 0.10 x ATR(14, 5-minute) of VWAP or of EMA(21), the MACD(12,26,9) histogram above its value on the prior bar, and the close above both VWAP and EMA(21).
- Short: mirrored.

**Shares (underlying first)**, with Part A's costs, notional and exit time.
- D5 stop: the touched level -/+ 0.10 x ATR(14, 5-minute). D6 stop: the decision bar's low (long) / high (short) -/+ 0.10 x ATR.
- The stop is judged on finished 1-minute closes and exits at the next bar's open -/+ $0.01. No target. Out at index 389.
- Long-only reported too.
- Pass = Part A's 7-item bar, and for D5 also beating all five made-up-level seeds.

**The stop and target grid** (option twins of D1-D6; contracts 0DTE d40-55t45 and next-expiry n1d40-55t45; HIST MODELED, DEV REAL):
- 12 exits: fixed stop -10%, -20%, -30% or -50% of the debit, crossed with fixed target +30%, +50% or none. All out 15:25. Addendum 10.2's TP30 exit is the (-20%, +30%) cell.
- **Choice, per rule and contract, on HIST 2016-2019 only:** the cell with the highest PF among cells with at least 60 discovery trades.
  - Ties: more trades, then the smaller stop, then the smaller target (none last).
  - No cell with 60 trades = no choice.
  - The choice is frozen; nothing dated 2020 or later can change it.
- **Holdout 1** = HIST 2020-01 to 2024-01 (MODELED): at least 60 trades, PF >= 1.25, PF 2x > 1.0, profitable in at least 3 of 2020-2023 (years with 10+ trades), positive without the best 5 trades.
- **Holdout 2** = DEV (REAL): at least 40 trades, PF >= 1.25, PF 2x > 1.0.
- A rule and contract **survives** when its chosen cell passes both holdouts.
- All 12 cells are shown in every window, labeled, so the picture isn't one cherry-picked cell. Win rate and break-even win rate are shown beside each.
- Addendum 10.2's signal exit stays as a separate reported variant, with its -20% stop.
- Implementation note: the 12 exits share each entry and its option tape. Evaluate them in one pass per entry rather than as 12 separate engine runs, and keep the whole Chart run near 3 hours or less. If it can't be, split it into run 8a and run 8b.

**Trials, Part D, recounted** (this replaces Addendum 10.2's count of 24):
- shares: 6 rules (D1-D6) x 2 sides = 12;
- options: 6 rules x 2 contracts x (12 grid cells + 1 signal exit) = 156.

That makes 168, and **round 8 totals 192**: Amendment 10's 13, plus 10.1's 11, plus 168. The deflated Sharpe uses the run logs' count + 192.

### Next, not in this amendment (round 9)

- Single-stock catalyst days: news/earnings movers, so the wins come on company days, not market days. This needs an earnings/8-K calendar and a single-stock option pull (Feb 2024+), so it gets its own pre-registration before any pull.
- Weekly-expiry (5-10 day) contracts for the FIN-H family and the steady rules, which need a new option pull (Addendum 10.1).

## Amendment 11, 2026-11-01: the final locked-period exam, four finalists (written after run 8, before any L1/L2 pull or run)

Nick (2026-11-01) asked for the final clean test. This extends Amendment 7's exam (its rules, guard and verdicts stand) with two finalists from round 8. Branch `sprint/exam`, cut from `sprint/round9`.

**Finalists (frozen; artifacts committed with their sha256 before any L1/L2 pull):**
- **FIN-H** and **FIN-L**, exactly as Amendment 7.
  - FIN-L's logit is fit once on all HIST 11:00-call trades. Use hist_v1-005's file if present on Chart's computer, else factory_hist_v1-012 (run 7, the same run configuration), and record which.
- **FIN-HS (new): FIN-H with round 8's B2 confidence sizing.**
  - The B2 logit (Amendment 3 settings, the 18 + 7 round-8 features) is fit once per locked period, on every FIN-H trade dated before that period:
    - L2: HIST trades through 2024-01-31 (MODELED);
    - L1: HIST plus DEV trades through 2026-06-30.
  - The tercile cuts come from that fit's training predictions. Bottom tercile -> skip, middle -> 1 contract, top -> 2.
  - The two fitted models and their cuts are committed as JSON with sha256.
- **NB-VOL (new): the vol-sized noise band in shares** (Amendment 10 A1 secondary): SPY + QQQ + IWM, long and short, with A1's rules, costs, sizing and exit time.
- **References:**
  - for FIN-H, FIN-L and FIN-HS: otm_v1-040 unfiltered on the same period (Amendment 7);
  - for NB-VOL: random direction on the same entries and exits (200 draws, seeds 31-230).

**Data.** One pull, through the existing `--locked <name> --frozen <spec sha256>` guard, for each period plus its warm-up:
- SPY, QQQ, IWM and VIXY stock 1-minute bars;
- VIXY daily closes;
- 0DTE option bars for SPY, QQQ and IWM.
L2's warm-up comes from HIST's last months and L1's from DEV's. Nothing in L1/L2 is used for anything but this exam.

**Pass, per finalist and period** (L2 = 2024-02-01..07-31, L1 = 2026-07-01..10-30):
- **FIN-H, FIN-L:** Amendment 7's bar: at least 30 trades on L2 and 20 on L1, PF >= 1.25, PF 2x > 1.0, expectancy above the reference's.
- **FIN-HS:** the same trade counts (counted as FIN-H's signals), sized PF >= 1.25, sized PF 2x > 1.0, and P/L per contract above FIN-H's on the same period.
- **NB-VOL:** at least 100 trades on L2 and 60 on L1, expectancy > 0 at 2x costs, and beats random direction with p < 0.10.
- **Verdicts as Amendment 7:**
  - holds = passes both periods;
  - mixed = passes one;
  - fails = passes neither.
- Reported whatever the verdict: by month, by symbol, and without the best 5 trades and without the best day. A 5% option half-spread rerun is information only.

**One shot.** Each period runs once. A crash may be re-run with the same frozen spec and the same code commit. Any code change after the first L1/L2 read makes the exam void for that finalist, and it is reported as such.

## Amendment 12, 2026-11-01: round 9, steadier money: multi-day rules, all-stock catalysts, an honest tweak search, weekly expiries (written before any round-9 code, pull or run)

Nick (2026-11-01): "can we not tweak any of the other strategies... I want to make consistent money so I can grow my account. Try everything, look online for day trading or general options trading strategies, it doesn't have to be for the day... continue the news scanner... scan all the stocks not just SPY and QQQ... same with the strategies".

**Scope change, recorded:** Nick asked in this conversation for strategies that need not close the same day. So multi-day holds are in scope for this round (CLAUDE.md: out of scope "unless Nick asks in that conversation"). Holding options through an earnings report stays out. Branch `sprint/round9`. Research only.

**Known before any result:**
- Steady option income mostly belongs to option sellers. Examples: cash-secured put writing (the Cboe PUT index: 1986-2015 Sharpe 0.67 vs the S&P 500's 0.47, gross, per CXO) and covered calls.
- Nick's account is long options only. Whether it allows covered calls or cash-secured puts is unknown (asked). So those stay paper research only and are not in this round's rules.
- **Locked periods for multi-day trades:** a trade whose holding window touches L1 or L2 is dropped entirely.

### Universes

- **U-ETF** (survivorship-free; all traded before 2016): SPY, QQQ, IWM, DIA, XLK, XLF, XLE, XLV, XLY, XLP, XLI, XLU, XLB, SMH, XBI, TLT, GLD, EEM, EFA, HYG.
- **U-STK** ("all the stocks"): every US common stock Alpaca lists today as active and tradable, with listed options.
  - On each day it is filtered point-in-time from daily bars: prior close > $5 and 20-session average dollar volume > $50 million.
  - It is SURVIVORSHIP-BIASED (today's survivors only), and labeled so everywhere.

### Part F: multi-day rules in shares (daily bars 2016-01..2026-06, never L1/L2)

**F1 `rsi2`** (Connors & Alvarez 2008, *Short Term Trading Strategies That Work*; widely replicated, e.g. a Nasdaq-100 2006-2025 test with a 64% win rate and PF 1.45).
- Long only. Signal at the close: close > SMA(200), close < SMA(5) and RSI(2) < 10.
- Buy at the next open. Exit at the next open after a close > SMA(5). No stop.
- One position per symbol. Run on U-ETF and on U-STK; U-STK's daily cap is the 10 lowest RSI(2) signals.

**F2 `tom`** (turn of the month: Lakonishok & Smidt 1988; McConnell & Xu 2008).
- Buy at the close of the last trading day of the month; sell at the close of the third trading day of the next month.
- SPY, QQQ, IWM, DIA.

**Costs and sizing:**
- $10,000 notional a trade.
- Costs per side: $0.01 a share for U-ETF, 0.05% of price for U-STK. 2x costs = double.

**Pass (shares):**
1. at least 200 trades;
2. expectancy > 0 at 2x costs;
3. profitable in at least 6 of the 8 years 2016-2023 and in 2024-08..2026-06;
4. bootstrap 95% CI of the daily mean P/L above 0 (sessions, 2,000 draws, seed 29);
5. positive without the best 5 days;
6. beats random entry with p < 0.05: the same number of entries per symbol on random days with the same holding lengths, 200 draws, seeds 31-230;
7. at least 55% of months green.

U-STK results are labeled survivorship-biased, and a U-STK pass needs U-ETF's rule to pass too.

**F-opt (DEV REAL; option bars pulled for the contracts needed):**
- The same F1 / F2 trades on U-ETF carried by a call: 30-60 calendar days to expiry, BS-EST delta 0.60-0.80 nearest 0.70. Bought at the entry open, sold at the exit open.
- Costs: half-spread 2% of premium per side ($0.005 floor) + $0.65 per contract per side.
- Pass: at least 40 trades, PF >= 1.25, PF 2x > 1.0, expectancy > 0.

### Part G: news and catalysts on all stocks (U-STK)

**Event source:** SEC EDGAR 8-K filings with their EDGAR acceptance timestamps.
- Use the daily form indexes plus each filing's index headers.
- At most 10 requests a second, with the desk's existing `SEC_USER_AGENT` (catalysts.py); never a personal value written into code.

**G1 `news_go`:** premarket 8-K continuation (Jiang, Li & Wang 2021, JFE: news-driven moves continue).
- Event: an 8-K accepted between 16:00 of the prior session and 09:15 on day t, for a U-STK name on t.
- Signal at the bar finishing 09:45, when all three hold:
  - |gap| = |open / prior close - 1| >= 2%;
  - the 09:30-09:45 move is in the gap's direction;
  - RV15 = the 09:30-09:45 volume / (0.10 x the 20-session average daily volume) is >= 3.
- Trade in the gap's direction at the next 1-minute open.
- Stop: the opposite end of the 09:30-09:45 range, judged on finished 1-minute closes and exiting at the next open. Out at the 15:55 close.
- Shares, 0.05% of price per side; long-only reported too.
- Pass: Part F's 7 items (at least 200 trades), plus beating random direction on the same events with p < 0.05.

**G2 `pre_earn_straddle`** (Gao, Xing & Zhang 2018, JFQA, "Anticipating Uncertainty: Straddles around Earnings Announcements": on 1996-2010 data, ATM straddles from 3 days before the announcement earned about 3% on average).
- Earnings date: an 8-K with Item 2.02.
  - If it was accepted before 09:30, day t is that day and the trade exits at the close of t-1.
  - Otherwise it exits at the close of t.
  - That way the position is always out before the report.
- Entry: buy the ATM call and the ATM put (strike nearest the close) of the first expiry 10-60 calendar days out, at the close of trading day t-3.
- Real option prices, DEV window 2024-08..2026-06 only (Alpaca option bars begin Feb 2024; Feb-Jul 2024 is L2).
- Costs: half-spread 5% of premium per leg per side ($0.01 floor) + $0.65 per contract per side.
- **Look-ahead caveat, labeled:** the 8-K date is the realized date; companies usually announce it weeks ahead, but not always.
- **Benchmark:** the same stocks' straddles on random non-earnings dates with the same 2- or 3-day hold, 200 draws.
- **Pass:**
  - at least 100 events;
  - mean return per straddle > 0 after costs;
  - PF >= 1.25;
  - positive in at least 3 of the 4 half-years (Aug-Dec 2024, H1 2025, H2 2025, H1 2026);
  - mean above the random-date benchmark's 95th percentile.

### Part H: the honest tweak search ("can we tweak the other strategies")

- Run 7's per-strategy factory procedure (Amendment 9 (b)-(d)) on round 8's share trades. That means:
  - 12 tercile candidate rules on 6 features, found on 2016-2019;
  - holdout 1 2020-01..2024-01 and holdout 2 DEV, with the factory's bars;
  - the walk-forward learner, with the factory's survival rule.
- Strategies, 11: noise_sh, noise_sh_vol, noise_sh_lo, last30, gapfade_vix, gapfade_vix_lo, and D1-D6 shares (long and short).
- Trade-level features are the sprint entry features at each share entry (stamped from cached bars).
- This is "tweaking" with the tweak chosen only on old years, which is the only kind the desk can trust.

### Part I: weekly expiries for FIN-H

- New contract rule `w5-10d03-12t07`: the nearest expiry 5-10 calendar days out, BS-EST |delta| 0.03-0.12 nearest 0.07. FIN-H's entry and exit (i).
- DEV REAL only, option bars pulled for that expiry.
- Pass: Addendum 10.1's DEV bar and its "steadier than FIN-H" readout.

### The book, trials and outputs

- **Book:** FIN-H (1 contract) plus every round-9 survivor, as Amendment 10's book.
  - It reports months and weeks green, the longest losing-month run and the correlation matrix.
  - A sleeve counts as "adds steadiness" only if its daily correlation with FIN-H is below 0.3.
- **Trials:**
  - F: 2 rules x 2 universes + 2 option twins = 6;
  - G: G1 (2 sides) + G2 = 3;
  - H: 11 strategies x (12 rules + 3 learner models) = 165;
  - I: 1.
  - Round 9 = 175. The deflated Sharpe uses the run logs' count + 175.
- **Outputs:** `data/sprint/round9_<date>.md` and `.json`, plus per-part trade files.
- No rule, cut or threshold changes after results.

## Amendment 13, 2026-11-01: Part S, the 1-minute option scalper (written before any Part S code or run; part of round 9)

Nick (2026-11-01) shared one day of trade alerts from four "QQQ Trader" bots and asked to reverse-engineer them. He'd be comfortable with "5 contracts for really good entries and 3 otherwise, with a tighter stop".

**What the alerts show** (Friday 2026-10-30; parsed by code, information only; 38 round trips):
- Entries land 1-14 seconds after a minute ends, so the bots act on each finished 1-minute bar. Median hold 90 seconds, longest 705 seconds.
- Near-the-money QQQ options at $5-7. The strikes follow the price (697 at the open, 685 by 14:46, a falling day).
- Overall win rate 82%, median trade +3.2%:
  - wins average +3.3% to +5.4% by bot;
  - losses average -5.4% to -8.9%.
- The largest bot ("#3", $57,000-84,000 a trade) bought only puts all day. The others switched between calls and puts in the choppy morning.
- One day of posted alerts is not a record: there's no account, no losing days and no fill quality. **That day is inside L1, which is never read, so the hypotheses below come from the alert text alone, not from that day's bars.**

**S signals** (DEV REAL option prices, SPY + QQQ, 0DTE; decisions at each finished 1-minute bar finishing 09:31-15:20; entry at the next bar's open):
- **S1 `scalp_trend`:**
  - close below VWAP and below the lowest close of the 5 prior bars -> buy a put;
  - close above VWAP and above the highest close of the 5 prior bars -> buy a call.
- **S2 `scalp_fade`:** the same triggers, the opposite option.
- One position at a time per symbol and rule. No new trigger while a position is open.

**Contracts:**
- `d45-55t50`: the bots' near-the-money shape.
- `d20-30t25`: a cheaper one that fits a $3,000 account.

**Exits, a 6-cell grid:** target +3%, +5% or +8% of the debit, crossed with stop -5% or -10%. Max hold 5 minutes, then out at the next bar's open.
- Target and stop are judged on each 1-minute option bar's high/low (desk fills: a bar touching both counts as the stop).
- All out 15:25.

**Costs** (the spread decides a strategy whose wins are +3-5%):
- Base: sprint/spread.py's MEASURED-SPREAD from the desk's logged chains where a cell has data, else a half-spread of max($0.02, 0.5% of premium). Logged chains exist only for recent months, so applying them to 2024-2025 is an assumption, and labeled.
- Plus $0.65 per contract per side.
- Stress: 2x the half-spread.
- Robinhood-fee view (about $0.03 a contract per side, information): reported beside the base.

**Choice and test (inside DEV only, since 1-minute option behavior needs real prices):**
- The cell is chosen per signal and contract on 2024-08-01..2025-06-30: highest PF among cells with at least 200 trades (ties: more trades, smaller stop, smaller target). Then it is frozen.
- **Test** on 2025-07-01..2026-06-30, all of:
  - at least 200 trades;
  - PF >= 1.20;
  - PF at 2x spread > 1.0;
  - positive in at least 4 of the 6 two-month blocks;
  - beats random direction (the same entries and exits with a coin-flip side, 200 draws, seeds 31-230) with p < 0.05.

**Underlying first** (CLAUDE.md step 3): the S1 / S2 triggers on SPY + QQQ 1-minute stock bars, 2016-01..2026-06 (never L1/L2).
- Report: the hit rate and mean of the next 5-minute move in the trade's direction, in bps, by year, against random direction.
- Information only: the option test decides.

**Nick's sizing (S-size, information plus a pass):**
- 5 contracts when the trigger agrees with the day's direction (close vs the open) and f_rvol >= 1.06; otherwise 3.
- Reported for the chosen cell on the test half: P/L, worst losing streak in $, max drawdown.
- **Account view:** each trade's debit as a % of $3,000, and the max drawdown as a % of $3,000.
- Pass: sized PF >= 1.20 and the sized max drawdown smaller than 50% of $3,000.

**Trials:** 2 signals x 2 contracts x 6 cells = 24, plus 2 underlying checks, plus 2 sized variants = 28. Round 9 becomes 203 (the deflated Sharpe uses the run logs' count + 203).

## Amendment 14, 2026-11-01: Part E, a predicted-efficiency gate (part of round 9; written before any Part E code or run)

Nick (2026-11-01) shared a post about a logistic regression that predicts the next day's efficiency ratio and skips predicted low-efficiency days. The post is unverified: no strategy, costs or random-skip comparison is shown.

**Target.** The day's efficiency ratio ER = |close(15:59) - open(09:30)| / the sum of |1-minute close-to-close moves| over regular hours. The label is 1 when the day's ER is in the top tercile of the training window's days, per symbol.

**Inputs, all known before 09:30.** Fifteen features:
- the prior session's ER and the mean ER of the prior 5 sessions;
- |gap| at 09:30 is NOT allowed (it is not known before the open), so the prior session's close vs its open is used instead;
- the prior session's range / ATR(14), and ATR(14) / ATR(60);
- 1-, 5- and 20-session returns;
- VIXY's prior close percentile (252 sessions), its 1-day change, and its z vs 20 sessions;
- the prior session's VWAP distance at the close;
- the prior session's last-hour return;
- weekday;
- FOMC/CPI day (sprint/events);
- the count of the prior 5 sessions with ER in the top tercile.

**Model.** Logistic regression (sprint/learn's preprocessing, L2 lambda 1, class-balanced), per symbol pooled over SPY, QQQ and IWM.
- Walk-forward: refit monthly on all earlier sessions, with at least 24 months of training. Out-of-sample from 2018-01.
- Gate: skip the day when the predicted P(top-tercile ER) is in the bottom tercile of that refit's training predictions.

**Applied, unchanged, to:**
- FIN-H (run 7's factory trades, 11:00 calls with f_rvol >= 1.06);
- NB-VOL (round 8's noise_sh_vol share trades);
- Part S's chosen cells (test half only).

**Pass, per strategy:** on 2018-01..2024-01 (MODELED options / real shares) and on DEV (REAL), all of:
- the gated expectancy above the ungated;
- the gated total above the 95th percentile of 200 random whole-day skips of the same count (seeds 31-230);
- gated PF 2x > 1.0.

Information: months green, max drawdown, total without the best day, and the $3,000 account view.

**Trials:** 3. Round 9 becomes 206.

## Amendment 15, 2026-11-01: round 10, an exit and entry search on Nick's setups (written before any round-10 code or run)

Nick (2026-11-01) is unsure which stops and targets suit his setups and asked to "fool around with those strategies to find out".

**Setups:**
- vwap_macd, with MACD on 1-, 2- or 5-minute bars (3 entries);
- orb15 and orb30;
- failed_break (calls);
- pd_retest.

That makes 7 entries, from sprint/entries.py as they stand.

**The grid** (per entry, evaluated in one pass per entry with sprint/optpass.py):
- stop: option -10%, -20%, -30% or -50%, or the setup's own level stop (its `invalid` price);
- target: +20%, +30%, +50%, +100% or none;
- trail: none or gb50;
- time cap: 30 minutes, 60 minutes, or all out 15:25;
- contract: d40-55t45, d20-30t25 or n1d40-55t45;
- trend filter: off, or only trades whose side agrees with the close vs the open at the signal bar.

That gives 5 x 5 x 2 x 3 x 3 x 2 = 900 cells per entry, and 6,300 in all.

**The choice:**
- Per entry, choose on HIST 2016-2019 (MODELED) only: the cell with the highest PF among cells with at least 100 discovery trades (ties: more trades, then the simpler cell in the order listed).
- Freeze the choice.
- **Holdout 1** = 2020-01..2024-01 (MODELED): Amendment 10.3's bar.
- **Holdout 2** = DEV (REAL): at least 60 trades, PF >= 1.25, PF 2x > 1.0, and above the same cell's random-side twin (seed 31).

**Reported:**
- the full grid as heat maps;
- the share of cells with PF > 1 in each window, which shows whether a stop or target style works broadly or only in one lucky cell;
- the $3,000 account view.

**Trials:** 6,300. The deflated Sharpe uses the run logs' count + 6,300; expect it to be strict.

The build comes after round 9's Part E lands; no new data is needed.

### Addendum 15.1, 2026-11-01: the noise band's own settings (part of round 10; written before any round-10 code or run)

Nick asked to optimize the vol-sized noise band in shares (NB-VOL). Exam L2 already read Feb-Jul 2024 for NB-VOL, so a tuned version can never use L2. It is judged on its holdouts and on forward paper trades only.

**The grid** (A1's rules otherwise unchanged, vol-sized as A1's secondary):
- band multiplier VM: 1.0, 1.25 or 1.5;
- noise lookback: 10, 14 or 20 sessions;
- check interval: 15, 30 or 60 minutes;
- trailing stop: max(band, VWAP) (the paper's), VWAP only, or band only;
- universe: SPY + QQQ + IWM, or plus DIA, XLK, XLF and SMH (U-ETF subset, 1-minute bars pulled in round 9's universe if present, else the three).

That gives 3 x 3 x 3 x 3 x 2 = 162 cells.

**The choice:** on 2016-2019 only, the highest Sharpe of daily P/L among cells with at least 1,000 trades. Holdout 1 = 2020-01..2024-01, holdout 2 = DEV (2024-08..2026-06), each with Part A's 7-item bar.

The full grid is reported, including the share of cells with a positive holdout Sharpe.

**Trials:** 162.

### Addendum 15.2, 2026-11-01: noise band loss autopsy fixes (discovery 2016-2019 only; written before any test on 2020+)

The autopsy used round 8's noise_sh_vol share trades, 2016-2019 only: 2,796 trades, mean +$4.25 a trade, t 2.24 (in-sample, BACKTEST).
- **First trade of the day:** +$6.86 a trade (n 1,787, t 2.68). Later re-entries: -$1.04 (2nd) and -$1.35 (3rd).
- **Symbol-days by number of trades:** 1 trade +$34.1 a day; 2 trades -$21.3; 3 trades -$53.6. That's the chop whipsaw.
- **By entry hour:**
  - 10:00 hour: +$8.95 (t 2.51);
  - 11:00: +$4.03;
  - 12:00: +$1.97;
  - 13:00: -$3.99;
  - 14:00: +$2.78;
  - 15:00: -$0.90.
- **Holding time:** trades exiting within 30 minutes average -$37.70 (n 1,130). Trades held 240+ minutes average +$147.35.
- **By symbol:** SPY +$1.77 (t 0.56), weaker than QQQ (+$5.81) and IWM (+$5.16). Not acted on: weak evidence.

**Fixes, frozen** (each alone and all together; A1's rules otherwise unchanged, vol-sized):
- **N1:** one trade per symbol per day. After the first exit, no re-entry.
- **N2:** no new entry after the check finishing 12:00.
- **N12:** N1 and N2 together.

**Test:** holdout 1 = 2020-01..2024-01 and holdout 2 = DEV, each with Part A's 7-item bar, against the unfixed NB-VOL on the same windows. A fix holds only if it beats the unfixed version's daily Sharpe in both holdouts.

**Trials:** 3 (round 10).

### Addendum 15.3, 2026-11-01: the alpaca-options-framework 0DTE rules, frozen as published (part of round 10; written before any code or run)

Nick (2026-11-01) linked github.com/milgar7969/alpaca-options-framework (MIT; a paper bot with no backtest; its settings were tuned on its own recent paper months). Its config.py and momentum.py, read as data, give a fully mechanical rule set. It is tested exactly as published, with nothing tuned.

**Entry** (SPY; QQQ reported as information):
- finished 1-minute bars, entries 09:45-12:00;
- 3 consecutive green bars (red for puts);
- 5-bar rate of change >= +0.03% (<= -0.03% for puts);
- ATR(5 bars, 1-minute) >= $0.20;
- 3-bar cooldown after a trade closes.

**Contract:**
- 0DTE, out of the money by 0.60 x the 5-day ATR, capped at $4.50, on the $1 strike grid;
- premium between $0.20 and $10.00;
- never in the money at entry.

**Exit**, all checked on the option mid (our 1-minute option bars) plus SPY:
- stop at 50% of the entry price;
- target at +50%;
- trail armed at +20%, exiting at 88% of the peak;
- an SPY stop 0.75 x ATR5 (at least $0.10) beyond the entry price;
- all out 15:25.

**Day gates:** stop new entries after a -$300 day, a +$125 day or 3 wins in a row, at their $150-risk sizing. Reported both with and without the gates.

**Windows and pass:** HIST 2016-2024 MODELED and DEV REAL, with B3's bars. Information: by hour, by exit reason, and win rate against break-even win rate.

**Trials:** 2 (with and without the day gates).

## Limits

- Backtests only.
- No bots created or edited, no broker connected, no account, plan or billing settings touched, no passwords or payment details.
- No existing runs deleted.
- Nothing coded into the live desk or deployed until Nick says yes.
