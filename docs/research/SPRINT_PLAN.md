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
- Long options are bought at the ask and sold at the bid when quotes are logged. On Alpaca bars and trades (no historical quotes), fills are the trade/bar price ± k × the half-spread from the spread model, with k = 1 as base and k = 2 as "2x slippage". The half-spread uses the desk's logged chains when present, otherwise a default of 5% of premium for SPY/QQQ/IWM and 10% for single stocks, labeled MODELED-SPREAD.
- Fees: $0.65 per contract per side.
- **Same-bar stop and target:** if a stop and a target both fall inside the same 1-minute bar, the stop counts.
- **Stop fills:** a stop fills at the worse of the stop price and the next real price after it, plus slippage. A fill is never at a price the option did not trade or quote.
- **No quote:** if the option has no trade or quote in a minute, no fill is assumed in that minute.
- **Signals and levels:** signals use finished 1-minute (or 5-minute) bars only. Levels use only data known at entry.
- **Entries:** at the next bar after the signal.

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

## Limits

- Backtests only.
- No bots created or edited, no broker connected, no account, plan or billing settings touched, no passwords or payment details.
- No existing runs deleted.
- Nothing coded into the live desk or deployed until Nick says yes.
