# DeltaDesk intraday strategy research

Registry version 2026-10-31. Machine-readable twin: `strategy_registry.json` (25 entries, same folder). Every repo entry carries the full SHA that was read.

## Bottom line

- The best-supported intraday edge that fits our data is **index intraday momentum**: Gao et al. 2018 and Baltussen et al. 2021 (both peer-reviewed), plus the Zarattini/Aziz/Barbon "noise area" rules for SPY. All of it can be tested on Schwab 1m SPY/QQQ bars without any paid data.
- **ORB has no A-grade evidence yet.** The stocks-in-play paper is fully specified but author-only and models no slippage. An independent replication of the simpler index ORB reproduced the gross edge (about +0.13R per trade) and found it erased by CFD spreads. No implementation of breakout + confirmation + retest comes with any performance evidence; the cleanest code is a small C# project.
- **News continuation:** credible papers say news-driven moves continue while no-news moves reverse. They also say the first reaction is priced within seconds to a minute, and that multi-day earnings drift is gone for large caps. For a desk where a human places trades by hand, the only plausible window is continuation minutes to hours after the news, on the same day.
- **Options:** none of the sources test options on the underlying. With no historical option quotes, every options variant has to be judged on underlying-signal backtests plus option spreads recorded live from now on.

## Ranked shortlist (test order)

| # | Entry | Kind | Rank | Why it's here | First test on our data |
|---|---|---|---|---|---|
| 1 | Beat the Market: SPY noise-area momentum (Zarattini, Aziz, Barbon 2024) | paper + code | A (provisional) | Public rules and code; costs and slippage modeled; the mechanism matches A-grade literature | Replicate on SPY/QQQ 1m with next-open fills, frozen defaults, results by year and vol tercile |
| 2 | Market Intraday Momentum (Gao, Han, Li, Zhou 2018, JFE) | paper | A | Peer-reviewed, tested out of sample, replicated internationally; one decision per day | r1 and r12 predicting r13 by year; out-of-sample R^2; cost hurdle |
| 3 | Hedging Demand and Market Intraday Momentum (Baltussen et al. 2021, JFE) | paper | A | Same effect in 60+ futures, 1974-2020; dealer gamma as the regime switch | Start daily 15:25 chain snapshots; condition the Gao signal on a gamma proxy after 60+ sessions |
| 4 | backtesting.py | repo | A | Conservative fill semantics (next-open, gap-aware stops, SL before TP); Python | Second implementation to cross-check our simulator on #1 and #6 |
| 5 | Rest in Peace PEAD (Martineau 2022, CFR) | paper | A | Credible negative result: earnings news is priced on day 0 | Day-0 versus multi-day returns after 8-K Item 2.02 by gap and RV |
| 6 | Can Day Trading Really Be Profitable? QQQ 5m ORB (Zarattini, Aziz 2023) | paper | B | Gross edge independently reproduced, net zero on CFDs; untested on ETFs | Gross/net R and a random-direction benchmark on SPY/QQQ |
| 7 | orb-quantower: confirmation close + retest limit | repo | B | The only clean breakout → confirm → retest logic found | Stop-entry vs confirm-market vs confirm-retest-limit on the same days |
| 8 | ORB on Stocks in Play (Zarattini, Barbon, Aziz 2024) | paper | B | Relative volume at the open is a free catalyst proxy; fully specified | Cross-sectional ORB with spread/impact slippage, by RV decile and price bucket |
| 9 | Pervasive Underreaction (Jiang, Li, Wang 2021, JFE) | paper | B | News moves continue, no-news moves reverse; cost-sensitive | EDGAR-timestamped event study, t+5 to t+120 minutes |
| 10 | Leveraged ETFs and option imbalances, end of day (Barbon et al. 2021) | paper | B | LETF rebalancing demand is computable for free | Does LETF demand predict SPY/QQQ 15:30-16:00 returns? |

The other entries (day-trader-skill, QuantRocket first-last, QC stocks-in-play replication, Busse and Green, Kaminski and Lo, PyBroker, vectorbt, NautilusTrader, LEAN) are B and support the tests above. The six C entries are rejected.

## Search method

- **Date:** 2026-10-31 UTC.
- **Discovery.** The GitHub search API and github.com/search were blocked in this session, and gist.github.com clones were refused by the proxy. Discovery therefore ran through web search plus references in papers, READMEs, Concretum tutorials and QuantConnect threads. I deliberately included low-star and recent repos. The full query list is in the JSON `method` field.
- **Repo handling.** Each repo was checked with `git ls-remote`, shallow-cloned into its own empty folder under `research/repos/`, and its SHA recorded with `git rev-parse HEAD`. The three large frameworks (vectorbt, NautilusTrader, LEAN) were sparse-checked-out to their execution code only.
- **Read only.** Nothing from any repo was installed, imported or run. Notebooks were parsed as JSON text.
- **Papers.** Read from author or institutional PDFs where possible (HSG Alexandria for the Zarattini et al. papers, a working-paper PDF for Gao et al., the 2018 draft for Jiang et al.). Otherwise read at abstract level via IDEAS/RePEc, SSRN and university pages.
- **Fetch tool caveat.** All web pages and PDFs came through a fetch tool that returns an extract or summary, so long PDFs may be partial. Each entry says how deep the reading went.
- **Claims handling.** Author numbers are copied as claims. Stars, equity curves and advertised win rates were not counted as evidence.
- **Seen but not entered:**
  - nkaz001/hftbacktest: needs L2/L3 tick data.
  - Two Python 2 ORB gists: clone refused; no P&L, no stops.
  - twopirllc/pandas-ta and ForexRobotEasy/Opening-Range-Breakout: not publicly cloneable.
  - Holmberg, Lonnbark and Lundstrom (2013, FRL), an ORB paper on crude oil futures: abstract only.
  - Remorov (2016 MIT thesis) on stop-losses: abstract only.
  - TradingView scripts and "winning strategy" blogs: leads only.

## Credible (A)

**Beat the Market: SPY noise-area momentum (SSRN 4824172).**
- *Rules.* Bands are max/min(open, prior close) x (1 ± sigma), where sigma is the 14-day mean of |close/open − 1| at the same minute. Trade only at HH:00 and HH:30. Trailing stop at the band or VWAP, flat at the close, vol-targeted to 2% daily with a 4x cap.
- *Claimed (2007-2024, net).* 1,985% total, 19.6% a year, Sharpe 1.33, max drawdown 25%. Sharpe 1.17 under I-Star slippage.
- *Code check.* In Concretum's Python, the bands are properly lagged. Entries effectively fill at the signal bar's close, and stops are only checked every 30 minutes.
- *Why provisional.* No independent replication found.

**Gao, Han, Li, Zhou (2018 JFE 129(2):394-414).**
- *Claimed (SPY 1993-2013).* Out-of-sample R^2 of 1.2-1.8%. Timing strategy about 6.67% a year, Sharpe 1.08. About 4.46% a year after spreads, post-2001.
- *Replications.* Mixed recently. QuantConnect's 2015-2020 re-creation had Sharpe -0.628 versus 0.582 for the benchmark. Li, Sakkas and Urquhart (2022) find in-sample predictability in 12 of 16 markets, but positive unconstrained out-of-sample R^2 in only 5.
- *Takeaway.* The effect concentrates in high-volatility periods and crises.

**Baltussen, Da, Lammers, Martens (2021 JFE 142(1):377-403).**
- Intraday momentum "everywhere" across 60+ futures, 1974-2020, tied to short-gamma hedging. It reverses over the following days.
- Abstract-level read only, so no numbers are verified here.

**Martineau (2022 CFR 11(3-4):613-646).**
- PEAD is gone for large caps since 2006. Prices fully reflect earnings news on the announcement date.
- Abstract-level read.

**backtesting.py (ca2e261, AGPL-3.0).**
- Next-bar-open market fills; gap-aware stop fills; SL beats TP in the same bar.
- It warns, rather than hiding, when an entry bar's own SL/TP would trigger.
- Single asset only.

## Insufficient evidence (B)

**ORB and breakout-retest**
- **Stocks-in-Play ORB (SSRN 4729284).**
  - *Claimed.* Top-20 by opening relative volume: 1,637% net, Sharpe 2.81 (2016-2023). Commission only, no slippage. The 5m window beats 15/30/60m by a wide, unexplained margin.
  - *QC replication.* Only 2016, Sharpe 2.396.
  - *QC forum reports.* After-hours stop fills, "savage" slippage effects, live symbol selection that differs from the backtest, worse 2023-2025 results.
  - *Data vendors.* Concretum's own data-quality note found the same ORB backtest varies more than 3x across vendors.
- **QQQ ORB (SSRN 4416622).**
  - *Claimed.* 33% annual alpha; TQQQ 1,484%.
  - *Replication.* An independent CFD study (MQL5 blog, 2015-2026) got gross +0.131R and net about 0 in all five indices. The direction signal still beat random by 0.10-0.13R (|t| ≥ 2) in three of five.
  - *Takeaway.* ETF spreads are a far smaller share of R than CFD spreads, so this is the cheapest open question.
- **QuantConnect stocks-in-play post.** Useful as a bug checklist: warm-up, after-hours fills, stop latency, universe parity.
- **orb-quantower (5a3a084, MIT, C#).**
  - Confirmation is a closed bar beyond OR ± 10% of the range; the retest entry is a limit at the OR boundary; one trade per session.
  - Defects: the documented last-entry cutoff is never wired into the decider, and resting retest limits never expire.
  - No performance evidence.
- **day-trader-skill (3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd, MIT).**
  - Carried over from the prior record.
  - Entry is the first 5m close above the 15m OR.
  - One TSLA example, average R -0.062 over 33 fires.

**Index momentum and regime filters**
- **QuantRocket first-last (6eebaf9, Apache-2.0).** A clean Gao implementation. Its VIX≥20 filter was chosen after splitting the same backtest by VIX, and the repo reports no numbers.
- **Barbon, Beckmeyer, Buraschi, Moerke (2021 WP).**
  - Dealer gamma imbalance and leveraged-ETF rebalancing drive end-of-day momentum or reversal in single stocks.
  - Decile Sharpe 4-5 before costs, which is a cost-fragility warning.
  - Needs paid signed option volume. The LETF piece can be computed from free issuer AUM.

**News and catalysts**
- **Jiang, Li, Wang (2021 JFE 141(2):573-599).**
  - News-driven returns drift while no-news returns reverse.
  - In the 2018 draft, the equal-weighted strategy loses money net (21.7 bps daily cost against a 15.9 bps return); value-weighted is about 8.6% a year net.
  - Built on RavenPack (paid).
- **Busse and Green (2002 JFE 65(3):415-437).**
  - CNBC reports are priced within seconds; positive news is fully priced within about a minute. Only trades within 15 seconds earned small profits.
  - Rogers, Skinner and Zechman (2017 JAR) show paying subscribers got EDGAR filings about 18 s early in 2012-2013.
  - Takeaway: measure our alert latency before designing any news trade.

**Trailing exits and momentum failure**
- **Kaminski and Lo (2014 JFM 18:234-254).**
  - Stop-losses add value only when returns have momentum or regime structure. Daily data, so the conclusion is indirect for us.
  - Use the framework to test exits on paired trades, not on equity curves.
- The exit candidates to compare are collected under the Kaminski-Lo entry in the JSON: BTM's VWAP/band trail, an ATR chandelier, the Alpaca example's MACD-fade exit, and an OR-midpoint stop.

**Backtesting frameworks with realistic execution**
- **PyBroker (01f11fd, Apache-2.0 + Commons Clause).**
  - Good defaults: 1-bar order delay; stops evaluated loss, then profit, then trailing; no stop on the entry bar.
  - Has slippage models, walk-forward and bootstrap confidence intervals. Good for cross-sectional stocks-in-play tests.
- **vectorbt (70da8fe, Apache-2.0 + Commons Clause).**
  - Sound stop logic (SL first, gap-to-open), but the default fill price is the current close, which is an easy route to look-ahead.
  - Use it for sensitivity grids only.
- **NautilusTrader (14e8528, LGPL-3.0, v2.0.0rc9).** The most realistic open-source engine, but its defaults are optimistic on bars:
  - The bar path defaults to O-H-L-C, which visits the high first and favors longs with targets above.
  - There is zero slippage by default.
  - It does have latency models and option instruments, so it is the candidate for replaying recorded option quotes later.
- **LEAN (1383825, Apache-2.0, C#).**
  - Reference fill model: stops fill on the next bar, gaps fill at the open, market orders fill at bid/ask.
  - Has VolumeShare and MarketImpact slippage formulas worth porting.

## Rejected (C)

- **umerdawood23/Opening-Range-Breakout-Strategy-in-Python (495ba4c).**
  - Requests 2016-2023 intraday data from Yahoo, which doesn't serve that history.
  - The 5-bar range on 5m bars is really 25 minutes.
  - The README looks machine-generated, and its sample results aren't tied to any run.
- **westonplatter/opening_range_breakout (ee0eb1f).** orbo.py has a syntax error. simple.py fills stops at the bar close and never applies its declared slippage. The window is hard-coded in UTC, so it breaks across DST.
- **IDEXAONE/orb-bot (e479ce2).** The "verified backtest" has no code. Its 1,462 trades in two years implies a long trigger on about 97% of symbol-days, which is implausible for the stated rule.
- **je-suis-tm/quant-trading, Dual Thrust (611b73f).** Look-ahead: today's own high, low and close feed today's trigger levels. It produces no P&L.
- **alpacahq/Momentum-Trading-Example (be43528).**
  - Never backtested; uses legacy APIs; the startup wait loop never exits.
  - Keep two ideas: the pivot-low stop and the MACD-fade exit.
- **amor71/LiuAlgoTrader (3df7006).** The backtester fills at the same bar close the signal used, and checks stops on closes rather than lows.

## Rules for every DeltaDesk test (drawn from what went wrong above)

1. **Bars and fills.** Stamp bars at their close. Fill at the next bar's open at the earliest. A stop fills at max(stop, open) on gaps. If SL and TP touch in the same bar, SL wins.
2. **Session hygiene.** No fills outside 09:30-16:00 ET. Handle half-day early closes. Build session windows in America/New_York, never fixed UTC.
3. **Costs.**
   - SPY/QQQ: at least a 1-cent spread plus slippage per side.
   - Stocks: a price-bucket spread, plus a VolumeShare-style impact model for stop entries at the open.
4. **Evaluation.**
   - Report gross and net R per trade by year.
   - Use a random-direction benchmark for direction signals.
   - Choose parameters on the first half of the sample, freeze them, and report the second half.
5. **Data audit.** Audit our 1m bars for phantom highs and lows, stale O=H=L=C bars and missing minutes before trusting any ORB result. Concretum's note found vendor differences larger than 3x for ORB.
6. **Options.** Never report an options P&L from underlying bars alone. Record live bid/ask for the contracts each signal would trade, starting now, and apply those costs.
7. **Data-quality pass.** Survivorship: record the daily scan universe going forward. News latency: log EDGAR acceptance time against our receipt time.

## Gaps

- No repo with documented, out-of-sample evidence for breakout + confirmation + retest.
- No open-source news-catalyst intraday backtest with real timestamps.
- No independent replication of the Beat the Market or stocks-in-play results beyond the QC 2016 run and forum anecdotes.
- No regime-filter study specific to avoiding intraday chop beyond volatility, relative-volume, NR4/NR7 and gamma conditioning.

Future searches should start from these gaps and from the JSON registry.
