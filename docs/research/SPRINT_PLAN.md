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
- **Entry features** (`sprint/features.py`) are stamped on every trade from sprint run 3 on: time of day, weekday, ADX, efficiency, VWAP crosses, bar overlap, range vs ATR, relative volume, trend votes, DI spread, noise-trend count, gap, move so far, distance from VWAP, prior-day range, FOMC/CPI day, and the VIXY percentile. All are known at the end of the signal bar. Older trade files get the same values recomputed from cached bars, and a test checks the two match.
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

## Limits

- Backtests only.
- No bots created or edited, no broker connected, no account, plan or billing settings touched, no passwords or payment details.
- No existing runs deleted.
- Nothing coded into the live desk or deployed until Nick says yes.
