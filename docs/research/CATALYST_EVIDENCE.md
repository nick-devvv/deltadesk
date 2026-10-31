# Catalyst and stocks-in-play books: backtested intraday rules for news/earnings moves in single stocks, and the economics of short-dated single-stock options (as of 2026-10-31)

Scope note: this file covers single stocks only. Index ORB and noise-band work is in index_intraday_signals.md, and 0DTE index options are in zero_dte_options_evidence.md. All web content was treated as untrusted data. Vendor and forum claims are labeled as such. Grades: A = independent, cost-inclusive replications. B = large sample with costs, but single source or decayed. C = vendor, no costs, or no realistic fills.

Already known to the desk (taken from the assignment, not re-verified here): Zarattini, Barbon & Aziz 2024 stocks-in-play 5-min ORB; Jiang, Li & Wang 2021 JFE (news-driven moves continue, no-news moves reverse); Martineau 2022 (PEAD gone for large caps). The desk's own 28-session SIP-ORB variant on about 125 stocks: stock -0.03R (PF 0.97), modeled options -$19.49/trade (PF 0.64).

## Q1. Stocks-in-play ORB: exact published rules, independent replications, slippage, liquidity buckets, post-2023 results, ORB-length sensitivity

### Takeaway
The published rules are fully mechanical. But the average edge per trade is small: +0.08R net of commission for RV above 100%, rising to +0.38R only for RV above 30x. No slippage is modeled, and the stop is just 10% of ATR, so 1 to 2 cents of slippage per side plausibly erases the edge in typical names. No independent, cost-inclusive replication covering 2024-2026 was found. The desk's -0.03R result fits "no edge after real fills." Grade: C (large sample, but no slippage, authors tied to a trading-education firm, replications only qualitative after 2016).

### Cited Findings
**Rule set 1: Zarattini, Barbon & Aziz, "A Profitable Day Trading Strategy for the U.S. Equity Market" (SSRN, 2024-02-16)**
- Universe: all NYSE and Nasdaq stocks, 2016-01-01 to 2023-12-31, about 7,000 stocks, survivorship-bias-free (CRSP). IQFeed intraday data, not adjusted for splits or dividends. — [Paper PDF (U. St. Gallen repository)](https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content)
- Daily pre-open filters: opening price above $5, 14-day average volume of at least 1,000,000 shares, 14-day ATR above $0.50. — [Paper PDF](https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content)
- Relative volume (RV) = volume from 9:30 to 9:35 ET on day t divided by the average 9:30-9:35 volume over the prior 14 days. Stocks in play are names with RV of at least 100%; only the top 20 by RV are traded each day. — [Paper PDF](https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content)
- Entry: the first 5-min candle sets direction. A bullish candle allows only a buy-stop at the 5-min high; a bearish candle allows only a sell-stop at the 5-min low. A doji (open = close) means no trade. — [Paper PDF](https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content)
- Stop: 10% of the 14-day ATR from entry. Exit: the stop, or the 16:00 close. Sizing: a stop-out loses 1% of the capital allocated to that position. Maximum leverage 4x. Starting capital $25,000. Commission $0.0035/share. No slippage assumption is stated. — [Paper PDF](https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content)
- Results, 2016-2023, as claimed:
  - ORB plus RV, top 20: total return 1,637%, IRR 41.6%, volatility 14.8%, Sharpe 2.81, hit ratio 48.4%, max drawdown 12%, worst day -1.61%, alpha 35.8%, beta 0.00.
  - Base ORB on all filtered stocks: 29% total, Sharpe 0.48, hit ratio 41.4%, max drawdown 13%.
  - S&P 500 buy-and-hold: 198%, Sharpe 0.78.
  - [Paper PDF](https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content); headline also on [Concretum page](https://concretumgroup.com/a-profitable-day-trading-strategy-for-the-u-s-equity-market/)
- Average trade by RV bucket (base filters, net of commission): RV below 100% gives -0.02R, above 100% gives +0.08R, above 30x gives +0.38R. — [Paper PDF](https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content)
- ORB-length sensitivity (stocks in play): 5-min Sharpe 2.81 (1,637%); 15-min Sharpe 1.43 (272%, max drawdown 11%); 30-min Sharpe 0.21 (21%, max drawdown 35%); 60-min Sharpe 0.40 (39%); equal-weight combo Sharpe 1.99 (max drawdown 7%). The authors write: "The reason for the 5-minute ORB's superior performance is unclear and warrants further investigation." — [Paper PDF](https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content)
- Not reported: slippage, top-N sensitivity (only top 20 tested), long vs short split, year-by-year results, price or liquidity buckets. Two authors are affiliated with Bear Bull Traders, a trading and training business. — [Paper PDF](https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content)

**Replication: QuantConnect research post plus forum thread #18444 (dates not shown on the fetched page)**
- Universe: the top 1,000 liquid US equities priced above $5 with ATR above $0.50. Trades 20 names ranked by first-5-min volume versus the 14-day average, requiring RV above 1. 5-min ORB, ATR-based stop, 1% risk per trade capped at equal weight. Backtested on 2016 only: Sharpe 2.396, beta -0.042 (SPY Sharpe 0.836). Net return, drawdown, win rate and cost assumptions were not reported in the summary. — [QuantConnect thread](https://www.quantconnect.com/forum/discussion/18444/Opening+Range+Breakout+for+Stocks+in+Play/p3/comment-50591); [QuantConnect research page](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/)
- Sensitivity, 2016 only:
  - ORB length 5-25 min crossed with universe size 500-1,500: 17 of 25 combinations (68%) beat the benchmark Sharpe.
  - ATR threshold $0-$2: Sharpe 1.5 to 2.7.
  - ATR above 1% of price: Sharpe 2.237, Probabilistic Sharpe Ratio 97%.
  - [QuantConnect thread](https://www.quantconnect.com/forum/discussion/18444/Opening+Range+Breakout+for+Stocks+in+Play/p3/comment-50591)
- Community follow-ups, all qualitative with no figures:
  - A 2023-2025 Python test on backtrader with Alpaca data "got way worse sharpe ratio and result."
  - One poster says after-hours fills inflated backtest results ("Strip that out and the true intraday-only performance is much more marginal").
  - MarketImpactSlippage has "quite a savage effect."
  - Live stop orders were sometimes placed 20-40 seconds after entry.
  - About half of the symbols chosen live overlapped with the backtest's picks (IBKR paper trading).
  - VolumeSMA is not warmed up for newly added symbols.
  - [QuantConnect thread](https://www.quantconnect.com/forum/discussion/18444/Opening+Range+Breakout+for+Stocks+in+Play/p3/comment-50591)
- An MQL5 blog post is titled "The opening-range breakout paper, replicated on five indices: gross reproduced, net zero". It covers index ORB, not stocks in play, and was seen as a search title only (not fetched). — [MQL5 blog](https://www.mql5.com/en/blogs/post/776235)

### Inferences
- **Slippage arithmetic.** The stop distance is 10% of ATR, and ATR only has to exceed $0.50, so the risk unit can be as small as $0.05/share. With 1 cent of slippage on entry and 1 cent on exit, a $0.05 stop loses 0.4R per trade, a $0.10 stop loses 0.2R, and a $0.20 stop loses 0.1R. Against a published average edge of +0.08R (RV above 100%), the strategy only survives realistic fills in names with ATR of about $2 or more, or in the extreme-RV tail (above 30x, +0.38R). The desk should bucket results by stop size in cents, not just by price.
- **ORB-length fragility.** Sharpe falls steeply from 5-min (2.81) to 15-min (1.43) to 30-min (0.21). The paper itself has no explanation for this. That pattern looks more like a sensitive or data-mined parameter than a robust effect, and 5-min entries are the ones most exposed to opening-auction noise and fill slippage.
- **Desk result.** The desk's -0.03R (PF 0.97) over 28 sessions is statistically indistinguishable from the paper's gross +0.08R once realistic fills are included. It is also consistent with the qualitative "way worse" 2023-2025 replication.
- **Changes worth testing.** (a) Require RV of 5x or more, or rank by RV and size up the extreme tail. (b) Require a stop of at least 15-20 cents, or ATR of at least $2. (c) Use bar-close entry plus a next-bar fill model, not a touch fill. (d) Exclude after-hours prints. (e) Report results by year for 2024-2026 using Alpaca minute bars.

### Gaps
- No independent replication with explicit slippage, by price or liquidity bucket, or covering 2024-2026 with figures was found (QuantConnect, Quantpedia, CXO and Substack checked via search). A CXO Advisory page appeared in search but was not fetched.
- No Concretum follow-up paper on stocks-in-play with costs or post-2023 data was found.
- The paper reports no long vs short split, no top-N sensitivity and no annual returns.

## Q2. Intraday news continuation with tradable rules: drift duration after a news timestamp, size net of spread, which news types continue, role of relative volume, LULD halts

### Takeaway
The academic evidence that news-driven moves continue intraday is real: Jiang, Li & Wang 2021 (already known) and a liquidity-screened news study on S&P 500 TAQ data that shows drift for up to about 150 minutes. But none of the material retrieved here provides a cost-inclusive trading rule, a breakdown by news type (8-K item, FDA, M&A, upgrade), or LULD-halt return statistics. Volume and liquidity regime shifts are the best published filter for "news that matters": only about 10% of intraday releases moved the market. Grade: C (no costs, no rules).

### Cited Findings
- Paper: "Towards systematic intraday news screening: a liquidity-focused approach" (arXiv 2304.05115).
  - Data: NYSE TAQ for S&P 500 constituents, four 5-min liquidity variables (spread in ticks, traded value, volatility, book size), plus Bloomberg headlines scored for sentiment.
  - Periods: liquidity model fit on 2017-2019; out-of-sample test on 2020-2021.
  - [arXiv 2304.05115](https://arxiv.org/pdf/2304.05115)
- In that study, with λ = 0.5 "only around 10% of total intraday releases are thought to have impacted the market." News counts as impactful when the stock's liquidity regime jumps from Mode 1 to Mode 2 (higher volatility and traded volume) around the publication time. — [arXiv 2304.05115](https://arxiv.org/pdf/2304.05115)
- Reaction measure: the h-minute post-publication market-detrended return. Main tests use h = 15 minutes; robustness checks use 5, 10 and 30 minutes. Average drift is plotted out to 150 minutes, and the screened sample's drift is described as "more significant and persistent." No exact drift sizes are given, no trading strategy is built, and no transaction costs are modeled. — [arXiv 2304.05115](https://arxiv.org/pdf/2304.05115)
- Kanniainen & Magris (arXiv 1810.12200) studied SPX index options, minute data, 2006-2010. Using the Lee-Mykland test they found 1,226 one-minute jumps. Implied volatility kept rising for about an hour after negative jumps (3-month ATM-IV coefficient 0.136 at 5 minutes, 0.218 at 60 minutes). After positive jumps the effect faded and was insignificant at 60 minutes (p = 0.720). This is index evidence, not single-stock. — [arXiv 1810.12200](https://arxiv.org/pdf/1810.12200)
- LULD halts: search returned only explainers, retail blogs and halt-list pages (e.g. a tapeboard page listing 50 halts on 2026-07-02). No academic or large-backtest study of post-halt continuation or reversal was retrieved. — [tapeboard halts page](https://tapeboard.com/blog/trading-halts-2026-07-02); [IEX resumption alert (2016)](https://iextrading.com/trading/alerts/2016/040)

### Inferences
- Relative volume works as a real-news detector. In arXiv 2304.05115 a jump into a high-volume, high-volatility liquidity regime is what separates the roughly 10% of releases that matter. This lines up with the RV filter in Zarattini et al. and with Jiang-Li-Wang's news vs no-news split. A tradable rule for the desk to test: confirmed news timestamp (RSS or EDGAR 8-K) + 5-min RV spike + direction of the first post-news bar, then hold 15-150 minutes, flat by the close. This rule is untested as a whole and would need its own backtest on Alpaca bars.
- No retrieved source supports the size of the drift net of spread. Measure it directly: take EDGAR 8-K acceptance timestamps, then compute the move from the first minute bar after acceptance to 15, 30, 60 and 120 minutes later, net of half the quoted spread.

### Gaps
- No retrieved source breaks down intraday continuation by 8-K item, FDA decision, M&A or analyst upgrade/downgrade with costs. Known literature leads, not retrieved or verified this session: Boudoukh, Feldman, Kogan & Richardson (RFS 2019) on firm-specific news and volatility; Gross-Klussmann & Hautsch (2011) on high-frequency news-implied reactions; Rogers, Skinner & Zechman (2016) on EDGAR dissemination timing.
- No academic study of LULD pause outcomes (continuation vs reversal after reopening) was found.
- No study gives drift half-life in minutes for single stocks with numbers.

## Q3. Earnings-day intraday: gap continuation vs fade, earnings-day opening-range rules, evidence since 2020; pre-announcement IV run-up straddle (Gao, Xing & Zhang 2018)

### Takeaway
The pre-announcement straddle (buy 1-3 days before earnings, sell on day -1/0/+1) earned about 1.9-2.6% per holding period at mid prices in 1996-2013. But it is strongest exactly where option spreads are widest and volume lowest, and costs were never tested. Retail-flow evidence (de Silva, Smith & So) shows option buyers around earnings lose 5-9% on average, with quoted spreads of about 20% of the option price. No rigorous source on earnings-day intraday gap continuation vs fade since 2020 was retrieved. Grades: Gao-Xing-Zhang straddle C for tradability (academic, large sample, no costs, pre-2014); earnings-day gap rules: no gradable evidence found.

### Cited Findings
**Rule set 2: Gao, Xing & Zhang, "Anticipating Uncertainty: Straddles around Earnings Announcements" (JFQA 2018)**
- Instrument: delta-neutral ATM straddles, weighted so delta is zero at formation, using options with 10-60 days to expiry, moneyness 0.9-1.1 and absolute delta 0.375-0.625. — [Paper PDF (Tsinghua PBCSF host)](https://www.pbcsf.tsinghua.edu.cn/__local/B/7B/EF/9C90E5DE82928B64858EFBA685C_E7B3C45C_4183B.pdf?e=.pdf)
- Other filters: option price at least $0.125, stock price at least $5, positive open interest, arbitrage bounds.
- Timing: buy on day -3 or day -1 before the scheduled announcement (day 0); sell on day -1, 0 or +1. Bid-ask midpoint prices, buy and hold.
- [Paper PDF](https://www.pbcsf.tsinghua.edu.cn/__local/B/7B/EF/9C90E5DE82928B64858EFBA685C_E7B3C45C_4183B.pdf?e=.pdf)
- Sample: January 1996 to December 2013 (OptionMetrics). 76,848 straddle observations, falling to 42,080 with a stricter liquidity filter. — [Paper PDF](https://www.pbcsf.tsinghua.edu.cn/__local/B/7B/EF/9C90E5DE82928B64858EFBA685C_E7B3C45C_4183B.pdf?e=.pdf)
- Equal-weighted pooled returns per holding window: [-3,-1] 1.90% (t = 16.35); [-3,0] 2.60%; [-3,1] 1.98%; [-1,0] 1.88%; [-1,1] 2.43%. Time-series versions range from 2.10% to 3.34%. Weighted by dollar open interest, [-3,1] and [-1,1] are not significant. — [Paper PDF](https://www.pbcsf.tsinghua.edu.cn/__local/B/7B/EF/9C90E5DE82928B64858EFBA685C_E7B3C45C_4183B.pdf?e=.pdf)
- Costs: the paper reports no returns net of effective spread and no Sharpe ratio. It uses end-of-day quotes and leaves tradability to future intraday work. — [Paper PDF](https://www.pbcsf.tsinghua.edu.cn/__local/B/7B/EF/9C90E5DE82928B64858EFBA685C_E7B3C45C_4183B.pdf?e=.pdf)
- Cross-section for the [-3,0] window:
  - Option bid-ask spread: lowest quintile 1.14%, highest 4.93%.
  - Option volume: lowest 5.82%, highest 0.90%.
  - Analyst coverage: lowest 4.67%, highest 2.12%.
  - Smaller firms earn more.
  - [Paper PDF](https://www.pbcsf.tsinghua.edu.cn/__local/B/7B/EF/9C90E5DE82928B64858EFBA685C_E7B3C45C_4183B.pdf?e=.pdf)

**Retail options around earnings: de Silva, Smith & So, "Losing is Optional" (SSRN 4050165)**
- "Retail losses of 5-to-9% around earnings announcements on average," rising to 10-14% for announcements with high expected volatility. Retail traders bid up option prices before such announcements. About $1.5B flowed from retail over the sample window. — [Quantpedia summary](https://quantpedia.com/how-retail-losses-money-in-option-trading/); [Stanford GSB listing](https://www.gsb.stanford.edu/faculty-research/working-papers/losing-optional-retail-option-trading-expected-announcement)
- "Average bid-ask spreads in our sample amount to a whopping ∼20% of the option price." These are quoted spreads, and they widen before high-volatility announcements. — [Quantpedia summary](https://quantpedia.com/how-retail-losses-money-in-option-trading/)

**IV crush and implied vs realized move (vendor, tiny samples)**
- FlashAlpha, as of 2026-08-03, defines crush as the drop in front-expiry ATM IV from the last pre-event reading to the first post-event reading. Median crush: META 42.5% (6 events), AAPL 23.2% (6 events), NVDA 14.8% (4 events). — [FlashAlpha](https://flashalpha.com/articles/how-much-does-iv-drop-after-earnings-real-crush-numbers)
- FlashAlpha's separate 70-event short-straddle study: the median event "harvested a third of the implied move," sellers won 67% of the time, and there was a "fat left tail." The period is not given. Vendor claim, grade C. — [FlashAlpha](https://flashalpha.com/articles/how-much-does-iv-drop-after-earnings-real-crush-numbers); [FlashAlpha VRP article](https://flashalpha.com/articles/earnings-vrp-harvesting-systematic-backtest-short-straddles)

**Earnings-day gap continuation vs fade**
- Searches returned only practitioner pages: Option Strategist video "Should Gap Moves Be Followed or Faded?", LuxAlgo concept pages, TradingView scripts, Benzinga gap API docs. None was a sample-based backtest with costs. — [Option Strategist](https://optionstrategist.com/node/5106); [Benzinga ERX gaps API](https://docs.benzinga.com/api-reference/calendar-api/get-erx-gaps.md)

### Inferences
- The pre-earnings straddle premium is concentrated where it cannot be harvested. The quintile with the widest option spreads earns 4.93% and the tightest earns 1.14%; the lowest-volume quintile earns 5.82% and the highest 0.90%. A round-trip straddle in a liquid name crosses two spreads twice, which likely costs more than 1%. So in liquid, high-volume names the edge after costs is probably near zero, and in illiquid names the spreads are about 20% (de Silva et al.). Grade it C and test it only with Alpaca option quotes from 2024 on.
- The IV crush figures (median 15-43% for mega-caps) mean any long option held through an after-close report must beat a large vega loss. Buying calls or puts the evening before to catch the day-0 move is structurally negative unless the realized move clearly exceeds the implied one. Per FlashAlpha's vendor claim, that happens in about one third of events.
- For the catalyst book, earnings-day trades should be measured in shares first: day-0 opening range plus RV, using the Zarattini rules restricted to earnings names. Options should come only after the open, once IV has already crushed.

### Gaps
- No retrieved paper or large backtest gives day-0/day-1 earnings gap continuation vs fade by gap size and volume since 2020, or tests earnings-day opening-range rules. The desk will need to build this from Alpaca minute bars (2016 on) plus EDGAR 8-K Item 2.02 timestamps.
- No independent replication of Gao-Xing-Zhang after 2013, or with intraday quotes, was retrieved.
- The de Silva et al. sample period and the split of losses between spread and IV overpayment were not in the retrieved summary.

## Q4. Single-stock options for these trades: daily-expiry coverage (Oct 2026), spreads by liquidity tier, implied vs realized move, buying options after a news jump, contract rules

### Takeaway
As of the Q3 2026 exchange lists, single stocks have Monday, Wednesday and Friday expirations only for a short list of "Qualifying Securities," roughly a dozen mega-cap names. Tuesday/Thursday single-stock expirations were not found in any retrieved filing. Monday/Wednesday series are not listed on a stock's after-close earnings day. The evidence on buying options after a jump (index data) and on retail options around earnings is that mid-price gains turn negative after spreads. So shares should be the default instrument. Options belong only in the tightest-spread names, with a hard spread cap. No published, evidence-based single-stock contract-selection rule set was found.

### Cited Findings
**Daily and sub-weekly expirations**
- On 2026-01-16 the SEC approved Nasdaq listing Monday and Wednesday expiring options in nine stocks (Bloomberg headline: "Mag 7 Stock Options Get SEC Nod for Monday, Wednesday Expiries"). Before that, single-stock options expired only on Fridays; SPY, QQQ and IWM already had daily expiries. — [Bloomberg Government, 2026-01-16](https://news.bgov.com/crypto/sec-gives-nasdaq-approval-for-mon-wed-stock-options-expiries); [Bloomberg](https://www.bloomberg.com/news/articles/2026-01-16/mag-7-stock-options-get-sec-nod-for-monday-wednesday-expiries); [SEC order 34-104624](https://www.sec.gov/files/rules/sro/ise/2026/34-104624.pdf)
- Qualifying Security criteria, measured quarterly:
  1. Market cap above $700B for a stock, or AUM above $50B for an ETF.
  2. Monthly options volume above 10 million sides.
  3. Position limit of at least 250,000 contracts.
  4. Participation in the Penny Interval Program.
  - The list is published on the first trading day of each quarter. Some Qualifying Securities may list up to two Monday and two Wednesday expirations.
  - [Nasdaq ISE SR-ISE-2026-19, Federal Register 2026-08365 (filed 2026-04-24)](https://public-inspection.federalregister.gov/2026-08365.pdf); [MIAX alert 2026-07-01](https://www.miaxglobal.com/alert/2026/07/01/miax-exchange-group-options-markets-listing-monday-and-wednesday-weekly)
- MIAX's Q3 2026 list (2026-07-01): AMD, GOOGL, AMZN, AAPL, AVGO, XLF, INTC, META, MU, MSFT, NVDA, TSLA, SMH. These are 11 stocks and 2 ETFs. — [MIAX alert 2026-07-01](https://www.miaxglobal.com/alert/2026/07/01/miax-exchange-group-options-markets-listing-monday-and-wednesday-weekly)
- Earnings exclusion: "A Qualifying Security expiration would not be listed on a day when there will be an earnings announcement" (after-close announcements). Under SR-ISE-2026-19, an already-listed Mon/Wed series is delisted if it has no open interest, or set to closing-only if it has open interest. — [MIAX alert](https://www.miaxglobal.com/alert/2026/07/01/miax-exchange-group-options-markets-listing-monday-and-wednesday-weekly); [FR 2026-08365](https://public-inspection.federalregister.gov/2026-08365.pdf)
- Other exchanges also list these series: MIAX alerts dated 2026-01-20 and 2026-04-06, Cboe notice "Cboe Options Exchanges to Begin Listing Options on Qualifying Securities", BOX Notices 2026-005 and 2026-026. These were seen as search titles only. — [MIAX 2026-01-20](https://www.miaxglobal.com/alert/2026/01/20/miax-exchange-group-options-markets-listing-monday-and-wednesday-weekly); [Cboe notice](https://www.cboe.com/notices/content/?id=58202); [BOX 2026-005](https://boxexchange.com/assets/Notice-2026-005-New-Short-Term-Option-Series.pdf)
- A separate Nasdaq ISE filing (Federal Register 2026-09122, 2026-05-08) proposes Monday-through-Friday expirations for A.M.-settled NDX index options. It is not a single-stock filing. — [PolicyRisk FR 2026-09122](https://policyrisk.com/federal-register/2026-09122)

**Spreads and buying options after a move**
- Quoted spreads on retail-traded options around earnings average about 20% of the option price. — [Quantpedia on de Silva, Smith & So](https://quantpedia.com/how-retail-losses-money-in-option-trading/)
- Buying ATM options after a negative 1-minute jump (SPX, 2006-2010) and holding about 30 minutes earned roughly +1.09% to +1.54% at mid prices (via the IV drift). After the bid-ask spread, returns were "clearly negative on average," and put returns were also negative net of spread. — [Kanniainen & Magris, arXiv 1810.12200](https://arxiv.org/pdf/1810.12200)
- Gao-Xing-Zhang straddle returns rise with option spread and fall with option volume. — [Paper PDF](https://www.pbcsf.tsinghua.edu.cn/__local/B/7B/EF/9C90E5DE82928B64858EFBA685C_E7B3C45C_4183B.pdf?e=.pdf)

### Inferences
- **Daily-expiry coverage is narrow.** For the catalyst book, true 0DTE single-stock options exist only Mon/Wed/Fri, and only in the Qualifying Securities list. That list should be refreshed from the exchange on the first trading day of each quarter; the Q4 2026 list (2026-10-01) was not retrieved. The list also excludes a name's own after-close earnings day. For the long tail of stocks in play (small and mid caps on news), only Friday weeklies or later expirations exist, and spreads are likely nearer the 20% average than the penny-wide mega-cap books.
- **Caution on the list.** INTC, MU and AMD appear on MIAX's Q3 2026 list despite the $700B market-cap test. Either their caps passed $700B by 2026-06-30 or the source is wrong. Check against the Nasdaq ISE or Cboe published list before relying on it.
- **Desk numbers match the evidence.** Stock PF 0.97 vs options PF 0.64 is what you would expect if spread plus theta roughly triples the drag. The 0.08R published edge leaves no room for option spreads.
- **Proposed contract rules.** These are derived from the evidence above, not a published rule set. Treat them as hypotheses to backtest on Alpaca option quotes from February 2024 on.
  1. Shares are the default and the measuring stick. Use options only if the stock-leg backtest is positive after slippage.
  2. Allow options only on Qualifying Securities and penny-program names.
  3. Maximum spread: require (ask - bid)/mid × 0.5 × 2 sides to be less than half the expected per-trade gross edge of the stock trade, converted to option terms via delta. For a 0.1-0.4R edge this implies spreads of a few percent of premium. Any contract with a spread above 10% of mid is excluded; the ~20% retail average is untradeable for minute-to-hour holds.
  4. Prefer ITM contracts (delta about 0.6-0.8) to cut the spread as a share of premium and lower vega and theta exposure. Use 0-7 DTE, and avoid holding through after-close earnings (median IV crush 15-43% on mega-caps per FlashAlpha).
  5. Require a minimum quoted size and same-day volume. No evidence-based threshold was found; the desk should calibrate this from its own fill data.
  6. Never buy options in the minutes right after a jump unless the spread test passes. Mid-price post-jump option gains turn negative after spreads (Kanniainen & Magris).

### Gaps
- No source was found giving bid-ask spread as a percentage of premium for short-dated single-stock options by liquidity tier (mega-cap vs mid-cap vs small-cap). A University of Houston paper (Doshi, "DPS_Oct_2024") returned "file not found." Muravyev & Pearson (RFS 2020), "Options Trading Costs Are Lower than You Think", on effective vs quoted spreads, is a relevant lead but was not retrieved.
- No single-stock (vs index) study of option returns bought right after a news jump was retrieved.
- No independent, large-sample implied vs realized earnings-move statistics (e.g. ORATS or Market Chameleon multi-year studies) were retrieved. Only FlashAlpha's small vendor samples were found.
- No published, evidence-based contract-selection rules (delta, DTE, maximum spread %, minimum OI or volume) for directional single-stock option day trades were found. The rules above are inferences.
- The Q4 2026 Qualifying Securities list was not retrieved.

### Rule-set summary and grades
| Rule set | Sample / period | Costs | Win rate | Expectancy | Max drawdown | Replication | Grade |
|---|---|---|---|---|---|---|---|
| Zarattini et al. SIP 5-min ORB, top 20 by RV | ~7,000 US stocks, 2016-2023 | $0.0035/sh commission, no slippage | 48.4% | +0.08R (RV>100%), +0.38R (RV>30x), net of commission | 12% | QC 2016-only Sharpe 2.40; 2023-25 forum "way worse" (no figures); desk -0.03R | C |
| SIP 15-min ORB variant | same | same | 44.7% | not reported per trade (Sharpe 1.43) | 11% | none | C |
| Liquidity-screened intraday news drift (arXiv 2304.05115) | S&P 500, 2017-2021 | none | n/a | not quantified | n/a | none | C |
| Gao-Xing-Zhang pre-earnings straddle | US optionable stocks, 1996-2013 | mid prices, no costs | n/a | +1.9% to +2.6% per window (mid) | n/a | none retrieved | C (tradability) |
| Buying options after a jump (Kanniainen-Magris) | SPX, 2006-2010 | spread included | n/a | negative net of spread | n/a | none | B for the negative result (index only) |
| FlashAlpha short earnings straddle | 70 events, period not stated | not stated | 67% seller | 1/3 of implied move (median) | fat left tail | none | C |
