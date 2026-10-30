# Research behind the v3.1 experiments, and what it does and doesn't show

Checked on Oct 29–30, 2026 against the authors' own pages and an independent replication. These are hypotheses to test on paper. None of them is a proven edge for 0DTE options.

## 1. Noise-band intraday momentum on SPY ("Beat the Market", Zarattini, Aziz, Barbon, 2024)
- **Rules as published:** sigma(t) is the average over 14 sessions of |close at t / 09:30 open − 1|. The bands are max/min(today's open, yesterday's close) × (1 ± sigma). The strategy checks only at :00 and :30 from 10:00, goes long above the band and short below it, uses a stop at the tighter of the band and VWAP, and is flat at the close.
- **Reported result:** May 2007 to early 2024, SPY **shares**, net of $0.0035/share commission and $0.001/share slippage. Sharpe 1.33, 19.6% a year with volatility sizing, a hit ratio of 37–46%, and no fade after 2020 in its yearly table.
- **What doesn't transfer:** the edge is on shares with sub-cent costs. Options pay the spread and time decay, so the same signal can lose with options. The paper also holds to 16:00, while the desk is out at 15:25.
- **How the desk tests it:** the "Noise band" research ledger, SPY/QQQ only, with delta-0.65 contracts. Every trade records the stock move next to the option result.
- **Caveats:** the paper's own numbers differ a little between its main text and its FAQ (Sharpe 1.33 vs 1.35, trade counts). The authors sell research services.

## 2. Opening-range breakout on "stocks in play" (Zarattini, Barbon, Aziz, "A Profitable Day Trading Strategy for the U.S. Equity Market")
- **Rules:**
  - Universe: price > $5, 14-day average volume ≥ 1M, ATR > $0.50.
  - Selection: opening relative volume ≥ 100%, then the top 20 by relative volume.
  - Trade: in the direction of the first 5-minute candle, on a break of its high or low.
  - Exits: a stop at 10% of ATR, otherwise flat at the close.
- **Reported result:** 2016–2023, US shares, net of costs. Over 1,600% total and Sharpe 2.81. The abstract says limiting trading to stocks in play was the key.
- **Independent replication** of the companion index study (5-minute opening range on index CFDs): the gross pattern is real, but **net of realistic costs no index market was distinguishable from zero**. Hit rate was 20–23%, and the original assumed zero slippage. This is why the desk does not trade this rule on SPY/QQQ, and only tests it on stocks in play.
- **What doesn't transfer:** shares, not options. Single-stock options have wider spreads, higher implied volatility on in-play names and earnings crush.
- **How the desk tests it:** the "Stocks in play" ledger.
  - Price ≥ $20 instead of $5, because cheap names have unusable option spreads.
  - Entries on a finished 1m close, not a resting stop order.
  - Options checked contract by contract: spread ≤ 5%, fresh quote, volume, open interest, delta 0.50–0.70, decay over the hold, and no expiry after earnings. The nearest expiry is never assumed.

## 3. Intraday momentum, first half-hour → last half-hour (Gao, Han, Li, Zhou)
- SPY 1999–2012. The relationship is real but weak (it explains about 2% of last-half-hour moves) and stronger on volatile and news days.
- **Not used:** the last half-hour is 15:30–16:00, after the desk's 15:25 all-out (Robinhood starts closing at-risk 0DTE positions around 15:30).

## 4. What the 0DTE evidence says about buying options
- Retail traders lost money on 0DTE SPX options in aggregate (about $350k a day in the period studied).
- Same-day options carry a variance risk premium: buyers pay up on average, and being right on direction is not enough without timing and size of move.
- Cboe found no sign that 0DTE dealer hedging drives intraday moves (Cboe has a stake in that finding), so "gamma levels" are not treated as signals.
- Fewer than 20% of day traders profit after costs (Barber et al., Taiwan). That's the base rate this desk is up against.

## How the desk judges any of this
1. **Diagnostics first** (`backtest.py` + `diagnostics.py`): a coin-flip baseline on the same setups, the exit breakdown, hold tests, the stock vs the option, split halves, and up vs down days. These run on modeled option prices, so they find causes. They are not proof.
2. **Forward paper evidence decides.** Each experiment keeps its own ledger and version. It is compared on expectancy, average win vs loss, drawdown and sample size, never win rate alone. Under 30 trades is "too early".
3. **Nothing is promoted automatically.** A change to main paper needs forward results and Nick's decision, and a new test period with a new version.

## Sources
- [Beat the Market (Concretum summary)](https://concretumgroup.com/beat-the-market-an-effective-intraday-momentum-strategy-for-sp500-etf-spy/), [full paper](https://concretumgroup.com/wp-content/uploads/2026/02/Beat-the-Market.pdf)
- [A Profitable Day Trading Strategy for the U.S. Equity Market (abstract)](https://ideas.repec.org/p/chf/rpseri/rp2498.html), [rules summary](https://www.cxoadvisory.com/individual-investing/intraday-trading-of-overactive-stocks-via-opening-range-breakout/)
- [Opening-range breakout replicated on five indices: net zero](https://www.mql5.com/en/blogs/post/776235)
- [Can Day Trading Really Be Profitable? (SSRN)](https://papers.ssrn.com/abstract=4416622)
- [Market intraday momentum (Alpha Architect summary)](https://alphaarchitect.com/2014/08/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/)
- [0DTE options: a losing bet for retail (Neudata)](https://neudata.co/literature-reviews/zero-day-to-expiry-options-a-losing-bet-for-retail-traders)
- [0DTE options: tiny edge, huge distribution (Hull Tactical on Vilkov)](https://hulltactical.com/2026/07/08/0dte-options-tiny-edge-huge-distribution/)
- [0DTE asset pricing (Hizmeri)](https://liverpool.ac.uk/institute-for-financial-and-actuarial-mathematics/past-seminars/rodrigo-hizmeri)
- [Evaluating the market impact of SPX 0DTE options (Cboe)](https://www.cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options)
- [Do day traders make money? (CXO, Barber et al.)](https://www.cxoadvisory.com/individual-investing/do-day-traders-make-money/)
