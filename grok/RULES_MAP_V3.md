# Desk v3 rules map (Oct 29, 2026, policy 2026-10-29.v3)

Upload this to Chart's Library as **"Desk v3 rules map"**. It replaces the v2 rules map. `context.rules` is still the live source and wins if anything here looks different.

## What changed and why (from the Oct 28 audit)

| Old (v2, retired) | New (v3) | Why |
| --- | --- | --- |
| Stop = 20% morning, 12% midday, 10% afternoon of the premium | Stop = the chart level or swing that proves the idea wrong, on a finished 1m close, plus a buffer. A 20% planned premium-loss ceiling (costs included) caps it. If the chart stop doesn't fit inside 20%, skip or pick another contract | Flat percentages gave reward/risk of only 1.0 to 1.25 |
| T1 = +20/15/12% of the premium | T1 = the next opposing key level (PDH/PDL, ORB, VWAP, POC/VAH/VAL, premarket high/low), minus an approach buffer | T1 ignored levels and profits were given back |
| No reward/risk rule | Need at least 2:1 on the stock move AND on the option dollars after spread, fees and time decay | Weak planned payoff |
| Any detector could open its own position | One idea = one trade. Same-side setups on one bar merge into one idea. Calls and puts on the same bar = skip the bar | Oct 28: two positions from one idea, and a call picked against the trend when both fired |
| "Trend day" from a close 7 cents over the ORB | Regime from ADX/DI, efficiency, VWAP crossings, overlap, range vs ATR, ORB acceptance (3 closes beyond, 0.5 ATR away), news state | A false A-grade trend label |
| RVOL compared the forming candle to finished ones | RVOL = the finished bar vs the median of the same clock time over the prior 10 sessions (needs 5) | Partial-candle volume |
| Only "MACD above/below signal" | 2m MACD histogram: 3 adverse changes in a row (needs 4 values) = fading. Cross = an event on the bar it happens; "bull/bear" = the state | Histogram faded 4 bars before the 13:06 entry |
| No volume profile | Developing profile (approximate, from 1m bars, $0.05 bins, 70% value area). Rejected-spike filter: no buying above value right after a rejected volume spike | Bought above value after a rejected spike |
| No green-trade exit | Green and no new premium high for 10 min: out. Green and momentum fades or MACD crosses against: out | Gave back gains |

## Entries (main paper)
- Confirmed candle closes only. A retest needs a real touch of the level zone and a confirming close.
- Not too extended: at most 1.0 ATR past the level.
- After 14:00 the chart must be cleaner (efficiency 0.35+, at most 2 VWAP crosses in 60 min, overlap under 60%, tight spreads, RVOL 1.2+).
- News: inside a pre-event or shock window (around a CPI/Fed-type release), no entries. With no calendar for today the state shows as "unknown" on the plan; the 9 AM routine posts the calendar.

## VWAP + MACD (one strategy)
1. **Arm:** a 2m MACD cross with the 2m close beyond VWAP in the same direction.
2. **Normal entry (VWAP retest):** price comes back and taps the VWAP zone, then a 2m close confirms in the trade's direction. This gets the lower price Nick asked for.
3. **Early entry:** only when the trend is clearly strong (ADX 25+ with DI aligned, histogram rising, VWAP sloping the right way, price accepted beyond VWAP). Then the desk may enter on the cross close itself.
4. **Cancel:** a close back through VWAP, MACD crossing back, or no retest within 8 bars.
Both entries share one idea, so one arming can produce at most one trade.

## Exits (first match wins, one action per tick)
1. Session: all out 15:25 (12:50 on early-close days).
2. Premium stop: the 20% ceiling, or breakeven/locked profit once moved up.
3. Structure broken on a finished 1m close.
4. Green: momentum fades or MACD crosses against → out. No new high for 10 min → out. T1 touched then rejected → out.
5. Not green by the if-flat time (old no-progress rule, kept for losers) → out.
6. T1: with 2+ contracts sell 1; keep the rest only on a clean break with aligned momentum, otherwise close it. With 1 contract: sell it.
7. Protect: breakeven at +10% (cost-aware), lock +10% after +25%, trail the runner on 1m swings.
Stops only tighten. If Nick types a looser stop the desk refuses unless he adds `force`, and it records who changed it.

## Size and limits
- A = 2 contracts, B = 1, C = no paper trade. Whole contracts that fit the stressed loss.
- Main paper: 4 ideas a day, one direction at a time across SPY/QQQ, 2 losses in a row = A only + 10 min cooldown, 3 = stop for the day.
- Research ledger: same setups, keeps observing after those limits (to learn what the limits cost or saved).
- Old rules ledger: the frozen v2 rules, run side by side for comparison only.

## Data
- Schwab is the only live source for candles, quotes and option prices. If Schwab is down the desk shows "FALLBACK - not executable": no paper fills, and plan prices are marked delayed.
- The desk chart uses the same Schwab bars as the engine. TradingView is its own feed.

## Never
- Chart never trades, never clicks order buttons, never enters keys or passwords.
- Real money is Nick's, placed by hand in Robinhood. Schwab is market data only.
- One day (Oct 28) is not evidence. Rules change only after the forward paper test and Nick's approval.
