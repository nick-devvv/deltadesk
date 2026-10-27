# Desk knowledge pack (for Chart's Library)

Short, sourced reference cards. The desk sends the 3 most relevant card IDs with each question; cite them as [K05] etc. 'research' = an idea being tested, not a rule. 'shadow' = running in the background with no say in trades.

## [K01] How the desk decides (4 layers)  (reference)
1) Hard gates (data fresh, session, spread, contract, 20% stop fits, events, streak) are never waived. 2) The selected setup's own trigger decides. 3) Other clues (RSI, MACD, extension, room to level) only rank/explain; they are not votes. EMA/MACD/RSI are the same price history, not 3 confirmations. 4) A good chart still needs a liquid, affordable contract. No fake confidence %.
_Source: Master prompt Part 27_

## [K02] Spread eats the stop  (reference)
A 0.90/1.00 quote marks a 1.00 buy near 0.90 at once: 10% gone before price moves, half the 20% stop. Prefer tight spreads; skip >10%. Mid touching T1 does not mean you could sell there; use the bid. A cheap premium dip may just mean the setup is failing or the quote is stale.
_Source: Master prompt Part 12_

## [K03] 0DTE greeks in plain words  (reference)
Near expiry, ATM gamma is high: small underlying moves swing the premium fast both ways. Theta decay is nonlinear and accelerates into the close (it does not 'start at 2 PM'). Delta is not the chance the trade works. Change in premium is roughly delta*move + 0.5*gamma*move^2 + vega*IV change + theta*time; use it to explain, not to predict fills.
_Source: OIC via master prompt Part 12_

## [K04] Robinhood close-out and stops  (reference)
Robinhood may start closing at-risk expiring options from 3:30 PM ET, so the desk is all out at 3:25. Robinhood supports sell-to-close stop-market and stop-limit orders; neither guarantees the stop price. Nick places his own stop every trade.
_Source: Robinhood help (master prompt S8,S9)_

## [K05] ORB research (what it does and doesn't prove)  (research)
Published ORB results use active stocks or 'trade the first 5m candle direction' with zero slippage and leverage. They are leads, not proof of our 15-min ORB retest on 0DTE options. Our ORB_BREAK / ORB_RETEST rules are tested on the desk's own paper results.
_Source: Zarattini/Barbon/Aziz 2024; QQQ opening strategy paper (S13,S22)_

## [K06] VWAP trend research  (research)
Long above / short below session VWAP on QQQ won only ~17% of trades; profit came from rare big winners, with zero slippage. Each VWAP cross is NOT a good 0DTE entry: repeated crosses = whipsaw (desk caps at 2 crosses/hour). Selective pullbacks are a separate test.
_Source: QQQ VWAP trend paper (S23)_

## [K07] SPY intraday momentum (noise bands)  (research)
Time-of-day movement bands on SPY with half-hour decisions; best headline uses up to 4x leverage. Useful as context for trend days, not a 1-minute entry model or an options result. Don't import its leverage or late-day exits (desk is all out 3:25).
_Source: SPY intraday momentum paper 2007-2024 (S21)_

## [K08] Candles: measure, don't believe  (reference)
Classic candle rules failed in tested daily data. Use candles as measured features: body %, close location, wick vs body, range vs recent volatility, relative volume. Only completed candles count. A wick doesn't prove a 'liquidity sweep'. Inside bar = compression; the break is a separate event. Never call an entry before the candle closes (Nick's Oct 22 lesson).
_Source: Marshall et al.; Lo/Mamaysky/Wang (S10-S12); Part 16_

## [K09] Context that actually helps  (reference)
Distance to next level vs invalidation distance (room to T1), VWAP crosses + overlapping candles (chop), trend efficiency, ORB width vs normal, gap vs prior close, event distance. UNCERTAIN/TRANSITION is a valid day type. Levels and MAs are references, not walls. OI 'walls'/gamma flips are model guesses, not facts.
_Source: Master prompt Part 17_

## [K10] Earnings plays  (reference)
Confirm date and BMO/AMC. Expected move = ATM straddle on the first expiry after the report / stock price. IV crush: premiums fall after the report even if you're right on direction; buying calls/puts into the print needs a move bigger than the expected move. A 20% stop cannot protect an overnight gap. Playing the post-report reaction (next morning ORB) avoids the crush.
_Source: Options basics; desk earnings rules_

## [K11] Smart-money data (Quiver)  (reference)
Congress trades are disclosed weeks late; insider buys are rarer and more meaningful than sells; off-exchange short volume is routine market making, not proof of shorting; WSB mentions measure attention, not direction. Background only, never an entry trigger.
_Source: Quiver Quantitative_

## [K12] Reviewing performance  (reference)
Look at: net expectancy ($ and R), average win vs loss, profit factor, max losing streak, drawdown, results by setup/time/ticker. High win rate with tiny winners can still lose. Small samples (20 trades) start a review, they don't prove an edge. Judge process (followed plan?) separately from outcome.
_Source: tradingview-mcp performance-analyst; master prompt Part 19-20_

## [K13] How lessons become rules  (reference)
Observation -> hypothesis -> test on the same setups -> forward paper -> PROPOSED -> Nick approves. Two losses are an observation, not a rule. Never punish a correctly executed loss with a new restriction. Separate why it lost: signal, contract, execution, management, or process. Never propose a looser stop or bigger size.
_Source: Master prompt Part 20, 29_

## [K14] Backtest traps  (reference)
Trying many variants finds lucky ones (overfitting). Keep a log of every variant tried, test on untouched later data, use completed bars only, no fills before the bar closed, no midpoint fills, and if stop and target hit in one bar assume the worse. SPY and QQQ move together; they're not two independent tests.
_Source: Bailey et al. (S15); freqtrade/jesse bias checks_

## [K15] AI trading claims on Reddit  (reference)
'$20K Grok bot' posts were paper accounts on small stocks, often followed by losing days. Vendor posts are promotions. Lessons worth keeping: timestamps, fresh quotes, conservative fills, honest live vs backtest. More AI agents don't replace verification.
_Source: Master prompt Part 30_

## [K16] Kronos forecast (shadow test)  (shadow)
Pre-trained candlestick model (trained on daily/hourly data, not proven on SPY/QQQ 1-minute). The desk runs it in the background and scores it against simple baselines. It has no say in trades until it beats them over weeks. A shaded range is not a guaranteed probability.
_Source: Kronos repo/paper (S34-S37)_

## [K17] Chart analysis checklist  (reference)
Price vs recent range; PDH/PDL/PDC, PMH/PML, ORB, VWAP, 9/21 EMA, 200s; trend on 15m/5m; room to the next level; what would invalidate; one-line bias with the reason. Use the desk's read numbers first; open Legend only for the option chain or if data is stale.
_Source: tradingview-mcp chart-analysis skill; Nick's Playbook_

## [K18] Option-chain levels (max pain, top OI)  (reference)
Max pain and the strikes with the most open interest or volume can act as magnets near expiration, especially on 0DTE. They're context, not support/resistance guarantees. OI is yesterday's count and doesn't say who is long or short, so a 'gamma wall' is a model guess. Mention them as 'a level to watch', never as the reason to enter.
_Source: bandaru-trade-analysis (MIT); master prompt Part 17_

## [K19] Squeeze (compression) setups  (research)
TTM squeeze = Bollinger Bands inside Keltner Channels: volatility is compressed. The release can go either way. The trade is the completed break of a nearby level after the squeeze, not the squeeze itself. Being tested as a research setup, not active.
_Source: bandaru-trade-analysis (MIT); master prompt Part 15 #6_

## [K20] Why the desk shows no 'confidence %'  (reference)
Some bots fire when a made-up confidence score passes 78%. Those scores aren't calibrated win probabilities. The desk instead shows the state (WAIT/READY/PASS), the grade (how many things line up) and the reasons for and against. When the paper record by setup builds up, that's the real evidence.
_Source: celo-trader review; master prompt Part 27_

## [K21] ORB retest (celo version vs ours)  (reference)
Same idea as the desk's ORB_RETEST: record the 5m close beyond the 9:30-9:45 range, wait for the candle low/high to tag within ~0.15% of the level, enter on the close back beyond it. Extra filters they use: volume above normal (RVOL), price on the right side of VWAP, skip if price already ran >1.5x the average candle past the level, 20-min cooldown after it fires. Window 9:45-10:45.
_Source: celo-trader README playbook (manujbh/mmoore723), rules summarized_

## [K22] VWAP pullback in a trend  (research)
Calls: 50 EMA rising, VWAP above the 50 EMA, previous 5m candle's low dipped to/below VWAP, current candle closes back above VWAP, volume above normal. Puts: mirror. Stop: VWAP failing = trend probably over. This is a pullback-in-trend entry, not 'every VWAP cross' (see K06).
_Source: celo-trader README playbook (manujbh/mmoore723), rules summarized_

## [K23] Trend continuation (2nd/3rd wave)  (research)
In a confirmed trend, a fresh higher low (calls) or lower high (puts) from the last 20 candles, then a close beyond that pivot candle, with VWAP on the right side and RVOL >= 1.2. Joins a proven trend at a discount; stale pivots (>20 candles) don't count. Close to Nick's Momentum setup; window 9:45-2:30.
_Source: celo-trader README playbook (manujbh/mmoore723), rules summarized_

## [K24] Break of structure / market structure shift  (research)
A 5m CLOSE (not a wick) beyond the last confirmed swing high/low, volume >= 1.5x, price on the trend side of the 50 EMA and VWAP, not already extended >1.5x average candle. Swings must be confirmed when they happen (no hindsight).
_Source: celo-trader README playbook (manujbh/mmoore723), rules summarized_

## [K25] Fair value gap retest  (research)
3-candle pattern: candle 1's low above candle 3's high (bullish gap) or the reverse. Gap must be at least half an average candle wide, from the last ~20 candles. Entry when price trades back into the gap with volume >= 1.5x and VWAP alignment; stop just outside the gap. A gap is a price feature, not proof of 'institutions'.
_Source: celo-trader README playbook (manujbh/mmoore723), rules summarized_

## [K26] Midday breakdown (puts)  (research)
10:30-1:00, puts only: a confirmed lower high already printed, price below the ORB low AND below VWAP (VWAP acting as a ceiling), volume >= 1.5x normal for that time of day. Three things already against the bulls before entry. Celo reports it rarely fires.
_Source: celo-trader README playbook (manujbh/mmoore723), rules summarized_

## [K27] Afternoon reversal (calls)  (research)
1:00-3:30, calls only: after a midday selloff, a confirmed higher low, then a close above the most recent swing high, volume >= 1.2x. Most afternoon reversals fail, so it needs both confirmations. Afternoon = tighter 10% stop and fast theta (K03).
_Source: celo-trader README playbook (manujbh/mmoore723), rules summarized_

## [K28] Channel trendline rejection  (research)
Line through the last two swing highs (or lows), projected to now. Entry when a candle tags within 0.3% of the line and closes back in rejection, VWAP on the right side, not against a confirmed opposite trend, pivots < 40 candles old. They skip 12:00-1:30 because midday touches fake out.
_Source: celo-trader README playbook (manujbh/mmoore723), rules summarized_

## [K29] Celo trade management (for comparison)  (reference)
Their stop starts at 20% and tightens with TIME IN TRADE (15% after 15 min, 10% after 30); sell half at +50%; runner exits at entry x1.15; out if down 12% in the first 30 min; time limit 30 min (90 if first target hit). The desk uses time-of-day stops (20/12/10%), BE then T1 then trail, and flat exits instead. Different design, same goal: don't let a 0DTE trade sit and decay.
_Source: celo-trader README playbook (manujbh/mmoore723), rules summarized_

## [K30] Don't chase + setup cooldown  (reference)
If price is already more than 1.5x the average 5m candle past the level, it's extended: wait for the retest or skip. After a setup fires, the same setup can't fire again for 20 minutes. The desk now enforces both in the paper engine. Re-entering the same failed setup three times on a chop day is the classic account-killer.
_Source: celo-trader rules; Nick's LE-model video lesson_

## [K31] ADX: trend vs chop  (reference)
ADX(14) measures trend STRENGTH, not direction. Rough guide on 5m: under ~18 = no trend (chop risk), 25+ = trending. The desk now adds ADX to every plan: under 18 on a non-trend day marks it a chop day; 25+ counts in favor. Direction still comes from structure, VWAP and the 200s.
_Source: bandaru-trade-analysis (MIT), Wilder's ADX_

## [K32] Floor pivots  (reference)
Pivot P = (prior high + low + close)/3; R1 = 2P - low; S1 = 2P - high; R2 = P + (high - low); S2 = P - (high - low). Widely watched reference levels, like PDH/PDL. They're context for room-to-target, not entry signals by themselves.
_Source: bandaru-trade-analysis (MIT)_

## [K33] GO / READY / STANDBY / INVALID  (reference)
Bandaru labels trade cards: GO (at the level, conditions met), READY (within ~0.2% of the level), STANDBY (not close), INVALID (broke the level by ~0.3%). The desk's version: READY, WAIT (plus NEAR on a watch), PASS, INVALIDATED/EXPIRED, all from completed candles. Same idea: say how close and what kills it.
_Source: bandaru-trade-analysis (MIT)_

## [K34] PDH/PDL retest + 9 EMA pullback (LE model)  (reference)
Levels first, then EMAs. Trend days break OUTSIDE the prior day's range (outside day) and pay; inside/chop days ping-pong and bleed. Calls: price breaks and holds above PDH (and above the premarket high), settles, pops, then pulls back to PDH or the 9 EMA: enter on the green close that holds. Puts mirror at PDL. Don't short pops on a trend-up day; avoid trading inside days.
_Source: Nick's trading video (LE model) + Oct 26 Playbook; desk setup PDH_RETEST/PDL_RETEST_

## [K35] Using the journal to improve  (reference)
After each trade: why in, why out, followed plan?, what went well, what to improve, next time, and mistake tags (chased, early entry, no stop set, moved stop, oversized, revenge trade, held too long, ignored chop). Weekly: check 'What's working' by setup, time of day and grade, and the mistake counts. Fix the most frequent mistake first, one at a time.
_Source: OptionsTradingJournal ideas; master prompt Part 20_
