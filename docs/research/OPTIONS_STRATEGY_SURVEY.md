# Long-option strategy survey: what the evidence says for an options buyer (2026-11-01)

Research only. Nothing here is a ledger, a rule change or a trade. Every family below needs its own pre-registered test (CLAUDE.md steps 1-5) before it can go anywhere near the desk.

**Scope.** Strategy families that can be traded by **buying** options: long calls, long puts, long straddles and strangles. Two horizons: intraday, and swing (held 1-30 days, options 7-90 days to expiry). Multi-day holds are in scope only because Nick asked for them in the round 9 conversation (SPRINT_PLAN Amendment 12). Holding an option through an earnings report stays out of scope.

**Labels.** Every number below is a published claim by the cited authors (gross of costs unless it says "net"), or a desk BACKTEST where it says so. Trade counts per year are my own rough estimates for a 100-stock liquid optionable universe; they are not measured.

**Grades** (evidence quality, not direction):
- **A**: independent, cost-inclusive replication.
- **B**: large sample, single source (or replications that ignore costs).
- **C**: weak: a vendor, a book, a blog, a short sample, no costs, or no out-of-sample test.

A family can have A-grade evidence that it **no longer works** (for example index additions). The "Fit" column says how well the signal survives being carried by a bought option: **good**, **fair**, **poor**, or **avoid**.

## The bottom line

1. **Buying options starts behind.** Option buyers pay a volatility risk premium. Unconditional single-stock straddles lost about 0.19% a day (2.09% a week) in 1996-2010 ([Gao, Xing & Zhang summary](https://alphaarchitect.com/2013/02/straddle-earnings-announcements-and-win/)). Delta-hedged ATM stock options lost about 2.4-2.9% a month in 1996-2016 ([Ruan 2020](https://acfr.aut.ac.nz/__data/assets/pdf_file/0008/185291/157562-X-Ruan-VOV_Option.pdf)). Short-dated far-OTM "lottery" options are the most overpriced: 7-day high-skew calls averaged -35% to expiry ([Boyer & Vorkink 2014, CXO summary](https://www.cxoadvisory.com/equity-options/sell-lottery-tickets-for-their-fun-and-your-profit)). Stock options also lose most of their value over weekends ([Jones & Shemesh 2018](https://www.cxoadvisory.com/?p=5800)). A buyer's signal has to beat all of that plus two half-spreads.
2. **The best-supported buyer strategies are option-native.** They pick *which* options are cheap rather than which stock goes up:
   - straddles bought a few days before earnings and sold before the report;
   - straddles on stocks whose implied vol is low against realized vol, or whose IV term structure slopes up;
   - straddles on stocks whose options have done well over the past year (option momentum).
   All are peer-reviewed. All fade sharply once you pay the full quoted spread, so execution (limit orders inside the spread) decides whether they make money.
3. **Classic stock signals are weak in options.** Stock momentum, short-term reversal, RSI(2), IBS and turn of the month earn roughly 0.1-1% per trade or per month gross. That is about the size of one option round-trip spread plus a few days of theta. They are better used as **filters** (trade the option families only in the right trend or regime) than as option triggers.
4. **Event signals with a large move per trade fit options best:** earnings run-ups, news continuation and big breakouts. Pre-announcement trades also benefit from implied vol rising into the event. Those families are the top of the ranking below.
5. **Data is the binding limit.** Every IV-based family needs implied vol history. The desk has none before Feb 2024. It can be approximated from Alpaca option trade bars (Feb 2024 onward) and recorded from Schwab chains going forward. So IV-sorted families can be tested only on 2024-2026 real prices (DEV), with the locked periods L1 and L2 untouched. That gives about 22 months, roughly 200-260 monthly straddle trades on 100 stocks: enough for one honest test per family, not for tuning.

## Ranked table

"Trades/yr" is the estimated number of option trades a year across a 100-stock liquid universe (or the stated ETFs). "Desk" is what the desk has already run.

| # | Family | Horizon | Grade | Fit | Trades/yr (est.) | Long-option mapping | Data needs (desk) | Sources | Desk status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Pre-earnings straddle, sold before the report | swing, 3 days | B | good | ~400 (4 reports x 100) | ATM straddle, first expiry 10-60 days out, buy close t-3, sell last close before report | Alpaca option bars (Feb 2024+), EDGAR 8-K 2.02 dates | [GXZ 2018 JFQA](https://resolve.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/anticipating-uncertainty-straddles-around-earnings-announcements/7B34877AD5E06304BA3C55FBA3219FDD), [AA](https://alphaarchitect.com/2013/02/straddle-earnings-announcements-and-win/), [BSIC](https://bsic.it/straddling-outside-and-into-earnings/) | Registered as round 9 G2, no result yet |
| 2 | Pre-earnings run-up of momentum winners (long calls) | swing, 5 days | B | good | ~40-80 | Delta 0.5-0.6 call, first expiry after the report; buy 5 days before, sell last close before report | stock bars, EDGAR dates, option bars | [Aboody, Lehavy & Trueman 2010](https://www.cxoadvisory.com/animal-spirits/returns-of-high-momentum-stocks-around-earnings-announcements); [Frazzini & Lamont](https://www.nber.org/digest/mar08/stocks-rise-around-earnings-announcements) | Not tested |
| 3 | IV term-structure slope: long straddles where it slopes up | swing, ~1 month | B | good | ~120 (top decile monthly) | ATM straddle ~30 days out, hold 1 month | IV by expiry: computed from Alpaca bars; Schwab chains going forward | [Vasquez 2017 JFQA](https://ideas.repec.org/a/cup/jfinqa/v52y2017i06p2727-2754_00.html), [CXO](https://www.cxoadvisory.com/volatility-effects/exploiting-the-implied-volatility-term-structure/), [AA](https://alphaarchitect.com/2014/01/equity-term-structure-and-option-returns/) | Not tested |
| 4 | Realized-minus-implied vol gap: long straddles where IV is cheap | swing, ~1 month | B | good | ~120 | ATM straddle ~30 days out, hold 1 month | 1-year realized vol (stock bars) + ATM IV (as #3) | [Goyal & Saretto 2009 JFE (PDF)](https://www.erim.eur.nl/fileadmin/erim_content/documents/10), [abstract](https://academicnewsletter.sufe.edu.cn/info/357238) | Not tested |
| 5 | Option momentum: long straddles whose straddles did well over 6-36 months | swing, ~1 month | B | fair | ~120 | ATM straddle ~30 days out, monthly | 1-36 months of straddle returns: only ~2 years buildable, so a short form only | [Heston et al. 2023 JF](https://alphaarchitect.com/2022/11/option-momentum/), [RIT](https://www.rit.edu/business/spotlights/research-insights-weighing-your-options) | Not tested |
| 6 | Trend breakout / new-high trend following on stocks | swing, weeks (roll) | B | fair | ~150-300 | Delta 0.6-0.7 call 60-120 days out, roll at ~30 days; exit on the stock's ATR trailing stop | stock bars 2016+ (signal), option bars 2024+ | [Zarattini, Pagani & Wilcox 2025](https://concretumgroup.com/does-trend-following-still-work-on-stocks/), [summary](https://harbourfrontquant.substack.com/p/does-trend-following-still-work-on) | Not tested |
| 7 | 8-K / news continuation, same day | intraday (and 1-2 days) | B | fair | ~100-200 | Delta ~0.5 weekly call/put in the news direction, out by 15:55 | EDGAR acceptance times, 1-min bars, Schwab live chains | [Jiang, Li & Wang 2021 JFE](https://ideas.repec.org:443/a/eee/jfinec/v141y2021i2p573-599.html); registry #9 | Shares test registered as round 9 G1; `news_drift` event study |
| 8 | Cross-sectional stock momentum (12-1), incl. high-turnover 1-month momentum | swing, 1 month | A | fair | ~120 | Delta 0.7 call 60-90 days out on top-decile names, monthly roll | stock bars 2016+ | [Jegadeesh & Titman 1993](https://ideas.repec.org/a/bla/jfinan/v48y1993i1p65-91.html), [decay](https://quantpedia.com/has-momentum-lost-its-momentum/), [crashes](https://ideas.repec.org:443/p/nbr/nberwo/20439.html), [Medhat & Schmeling](https://alphaarchitect.com/short-term-momentum/) | Not tested |
| 9 | Time-series momentum / dual momentum on ETFs | swing, 1 month | A | fair | ~60-120 (20 ETFs) | Call when 12-month return > 0, else put (or flat), 60-90 days out, monthly | stock/ETF bars 2016+ | [Moskowitz, Ooi & Pedersen 2012](https://papers.ssrn.com/abstract=2089463), [post-2012](https://alphaarchitect.com/?p=58168), [GEM robustness](https://files.advisorperspectives.com/articles/2019/05/06/global-equity-momentum-a-craftsmans-perspective) | Not tested; best used as a filter |
| 10 | RSI(2) / oversold bounce in an uptrend (incl. MA pullbacks) | swing, 2-6 days | C | poor-fair | ~300-500 | Delta 0.6-0.8 call 30-60 days out (round 9 F-opt rule) | stock bars 2016+, option bars 2024+ | [Connors RSI2 Nasdaq-100 test](https://backtest.substack.com/p/the-2-period-rsi-a-simple-system), [CXO critique](https://www.cxoadvisory.com/technical-trading/a-few-notes-on-short-term-trading-strategies-that-work/) | Registered as round 9 F1 + F-opt, no result yet |
| 11 | 52-week-high proximity | swing, 1-6 months | B | poor-fair | ~120 | As #8 | stock bars | [George & Hwang 2004](https://www.cxoadvisory.com/1284/technical-trading/the-52-week-high-as-a-momentum-indicator-for-individual-stocks/), [AA](https://alphaarchitect.com/52-week-high-q-factor-investment-model/) | Not tested |
| 12 | Earnings-day gap continuation (day 0) | intraday | C | poor | ~150 | Weekly ATM call/put in the gap direction after 09:45, out same day | EDGAR 2.02 times, 1-min bars, live chains | [Martineau 2022](https://cfr.ivo-welch.info/published/papers/martineau2021rest.pdf); desk `earn_day` | `earn_day` forward ledger (C) |
| 13 | IV spread and IV innovations (call IV vs put IV) | swing, 1 week-1 month | B | poor-fair | ~120-500 | Call on stocks with rich calls / rising call IV; put on the opposite | call and put IV at the same strike: Alpaca bars (noisy) or Schwab forward | [Cremers & Weinbaum 2010](https://ideas.repec.org/a/cup/jfinqa/v45y2010i02p335-367_00.html), [CXO](https://www.cxoadvisory.com/volatility-effects/do-informed-traders-tip-their-hands-via-option-purchases/), [An et al. 2014](https://www.nber.org/papers/w19590.pdf) | Not tested |
| 14 | Volatility smirk (OTM put IV minus ATM call IV) | swing, 1 week-1 month | B | poor-fair | ~120-500 | Put on steepest-smirk names, call on flattest | OTM put + ATM call IV, as #13 | [Xing, Zhang & Zhao 2010](https://ideas.repec.org/a/cup/jfinqa/v45y2010i03p641-662_00.html), [CXO](https://www.cxoadvisory.com/volatility-effects/smirking-because-they-know-something/) | Not tested |
| 15 | Option-to-stock volume ratio (O/S) | swing, 1 week | B | poor-fair | ~500 (weekly) | Put on high-O/S names, call on low-O/S names | daily option volume per underlying: sum of Alpaca option bars; Schwab forward | [Johnson & So 2012](https://academicnewsletter.sufe.edu.cn/info/356813) | Not tested |
| 16 | Vol-of-vol: buy options where IV is stable | swing, 1 month (filter) | B | fair as filter | filter | Prefer straddles/calls on low vol-of-vol names | daily ATM IV history (as #3) | [Ruan 2020](https://acfr.aut.ac.nz/__data/assets/pdf_file/0008/185291/157562-X-Ruan-VOV_Option.pdf), [Baltussen et al. 2018](https://personal.eur.nl/vanbekkum/2018JFQA_unknown_unknowns.pdf), [Cao & Han 2013](https://optionmetrics.com/research/j-cao-and-b-han-cross-section-of-option-returns-and-idiosyncratic-stock-volatility/) | Not tested |
| 17 | Pre-FOMC drift, only when VIX is high | 1 day | B (decay: A) | poor | ~4 (index only) | SPY/QQQ call bought the prior close, sold before 14:00 on FOMC day | Fed calendar, VIX proxy (VIXY or Cboe CSV) | [Kurov et al. 2021](https://www.skidmore.edu/economics/documents/KurovWolfeGilbert-TheDisappearingPre-FOMC-Announce-Drift-200914.pdf), [Martello & Ribeiro via Quantpedia](https://quantpedia.com/fomc-equity-drift-occurs-in-periods-of-high-uncertainty/) | Not tested |
| 18 | Turn of the month | 4 days | A (gross) | poor | ~48 (4 ETFs) | SPY/QQQ/IWM/DIA call 7-30 days out, last day close to day +3 close | ETF bars | [Quantpedia](https://quantpedia.com/strategies/turn-of-the-month-in-equity-indexes), [McConnell & Xu 2008](https://ideas.repec.org/a/taf/ufajxx/v64y2008i2p49-64.html) | Registered as round 9 F2, no result yet |
| 19 | VIX term-structure backwardation, buy the dip | swing, days-weeks | C | poor | ~5-15 episodes | SPY call 30-60 days out when VIX > VIX3M | Cboe VIX/VIX3M CSV, or VIXY/VIXM proxy | [Macrosynergy summary](https://macrosynergy.com/?p=41000) | VIXY filters used in sprints (otm_bounce, one episode) |
| 20 | Overnight-intraday gap reversal | intraday | B | poor | ~200 | 0DTE/weekly option against the opening gap | 1-min bars | [Lou, Polk & Skouras 2019](https://personal.lse.ac.uk/polk/research/TugOfWar.pdf), registry #11 | **Failed**: run 8 A3 (10 years of shares, -$3.91/trade) |
| 21 | Short-term (1-week/1-month) reversal | swing, 1 week | A | avoid | ~500 | Call on last week's losers | stock bars | [Medhat & Schmeling](https://alphaarchitect.com/short-term-momentum/), [Avramov, Chordia & Goyal 2006](https://ideas.repec.org/a/bla/jfinan/v61y2006i5p2365-2394.html) | Not tested |
| 22 | IBS (internal bar strength) | 1 day | C | avoid | ~1,000+ | 1-day call after IBS < 0.2 | stock bars | [arXiv 2306.12434](https://arxiv.org/abs/2306.12434v1) | Not tested |
| 23 | Put/call ratios and unusual options activity | swing, days | B (signed data) / C (public) | poor | ~500 | Call on low open-buy put/call; follow big call buying | needs signed open-buy volume (not free); public totals only from Alpaca/Schwab | [Pan & Poteshman 2006, CXO](https://www.cxoadvisory.com/sentiment-indicators/the-predictive-power-of-the-put-call-ratio-for-individual-stocks), [Bergsma et al. 2020](https://alphaarchitect.com/do-option-prices-inform-stock-returns/) | Not tested |
| 24 | Post-earnings drift (SUE/EAR) in liquid names | swing, weeks | A (against) | avoid | ~80 | Call on top SUE+EAR names day +2 | EDGAR XBRL EPS, stock bars | [Quantpedia](https://quantpedia.com/strategies/post-earnings-announcement-effect/), [Martineau 2022](https://cfr.ivo-welch.info/published/papers/martineau2021rest.pdf), [UCLA review](https://anderson-review.ucla.edu/is-post-earnings-announcement-drift-a-thing-again/) | Registry #5 (A, negative) |
| 25 | Low IV rank long options | swing | C | avoid | ~100-200 | Straddle when IV rank < 20-30 | IV history | [tastylive 2015](https://tastylive.com/shows/market-measures/episodes/low-implied-volatility-long-straddles-06-11-2015), [2016](https://www.tastylive.com/shows/market-measures/episodes/long-straddles-is-there-ever-an-opportunity-07-11-2016) | Not tested |
| 26 | Intraday index momentum, noise band, ORB on 0DTE | intraday | A/B (signal) | avoid as built | ~250-1,800 | 0DTE SPY/QQQ calls/puts | 1-min bars, option bars | registry #1-3, #6-8; [Gao et al. 2018](https://academicnewsletter.sufe.edu.cn/info/356150) | **Failed** in options: runs 1, 7, 8 (noise PF 0.78-0.89, ORB PF 0.80-0.88) |
| 27 | Other calendar: overnight hold, pre-holiday, day of week | 1 day | B/C | avoid | ~9-250 | Calls held overnight or into holidays | ETF bars | [Cliff, Cooper & Gulen, CXO](https://www.cxoadvisory.com/calendar-effects/buy-at-the-close-and-sell-at-the-open), [Heston, Korajczyk & Sadka](https://ar5iv.arxiv.org/html/1005.3535) | Not tested |
| 28 | Dealer gamma (GEX) regimes | intraday-daily | B (against) | avoid as signal | n/a | none | full chain OI (Schwab forward only) | [FlashAlpha 8-year test](https://flashalpha.com/articles/gex-dex-vex-chex-8-year-backtest-spy-vix-control), [Adams et al.](https://www.jean-sebastienfontaine.com/papers/0dte-options-volatility.pdf) | Registry #3 suggests snapshots; no test |
| 29 | Straddles held through FOMC / CPI / earnings | 1-3 days | B (against) | avoid | ~8-400 | (none: buyers lose on average) | event calendars | [macro VRP](https://harbourfrontquant.substack.com/p/the-volatility-risk-premium-around), [NDX FOMC straddles](https://www.nasdaq.com/articles/fomc-volatility-premium-evidence-1-day-nasdaq-100-straddles) | Out of scope for earnings anyway |
| 30 | Index additions and analyst rating changes | days | A / B (against) | avoid | ~20 / ~1,000 | (none) | S&P releases (manual); no free analyst data | [Greenwood & Sammon](https://alphaarchitect.com/disappearing-index-effect/), [Altınkılıç & Hansen](https://academicnewsletter.sufe.edu.cn/info/412540) | Not tested |

**Ranking rule (mine, stated before writing the table).** Order by, in turn: (1) evidence that the edge survives being carried by a *bought* option (option-native evidence first); (2) size of the move per trade against a typical option round trip; (3) grade; (4) trades per year; (5) whether the desk's free data can test it. Families with credible evidence that they are gone sit at the bottom however good their grade.

## Rules that apply to every family (buyer's checklist)

These come from the papers above and from the desk's sprints:

- **Never hold through the event that implied vol is pricing.** Earnings (out of scope anyway), FOMC and CPI straddles lose on average for buyers. Pre-event trades should exit before the release.
- **Avoid weekends where the rule allows.** Stock options earned -0.62% on average from Friday close to Monday close, with all other days positive ([Jones & Shemesh](https://www.cxoadvisory.com/?p=5800)). Pre-register "enter Monday-Thursday" as a variant, not as a tweak.
- **Avoid short-dated far-OTM single-stock options** unless the strategy is explicitly a convexity bet. Buyers of lottery-like options paid the most ([Boyer & Vorkink](https://www.cxoadvisory.com/equity-options/sell-lottery-tickets-for-their-fun-and-your-profit)). The desk's FIN-H (far-OTM 0DTE index calls on busy days) is the exception that passed holdouts, and it is a lottery shape carried by a handful of days (SPRINT_RESULTS_7, section 4).
- **Liquidity is the edge.** In Goyal & Saretto, a long-short straddle edge of 21.9% a month at mid shrank to 4.1% at the full quoted spread. Vasquez's term-structure edge became insignificant at 1.25x the quoted spread on one reading. Every test must report results at mid, at 50% and at 100% of the measured spread. The desk measures spreads from Schwab chains; Alpaca has no historical bid/ask.
- **Selling early hurt every desk test so far** (runs 1-3, run 8 B4). For swing families, pre-register the paper's own exit first, then one simple alternative.

## Regime and cross-asset filters

These don't trade on their own. Each is a candidate filter for a family above, and each must be pre-registered as a variant, counting toward the deflated Sharpe.

- **Market trend (index above its 10-month or 200-day average; 12-month index return > 0).** Stock momentum earned its profits after up markets and failed after down markets ([Cooper, Gutierrez & Hameed 2004](https://academicnewsletter.sufe.edu.cn/info/361185)). Momentum crashes happen in rebounds after bear markets ([Daniel & Moskowitz 2016](https://ideas.repec.org:443/p/nbr/nberwo/20439.html)). A stock-and-bond cross-asset trend filter beat plain TSMOM in 19 of 20 countries ([Pitkäjärvi, Suominen & Vaittinen, via Alpha Architect](https://alphaarchitect.com/?p=58168)). Applies to #2, #6, #8, #10 and #11.
- **Volatility level (VIX above its median).** The pre-FOMC drift lived almost entirely in high-VIX periods: 109 bps vs 9.7 bps ([Quantpedia](https://quantpedia.com/fomc-equity-drift-occurs-in-periods-of-high-uncertainty/)). Intraday momentum concentrates in high-vol periods (registry #2). But calls are dearest exactly then, so a buyer needs the IV filters (#3, #4) alongside.
- **VIX term structure (backwardation).** Backwardation predicted positive S&P 500 returns in 2010-2017; contango predicted nothing ([Macrosynergy](https://macrosynergy.com/?p=41000)). The desk's VIXY-percentile filters found the same kind of thing (otm_bounce), but in one episode only (SPRINT_RESULTS_3).
- **Dealer gamma.** Adds nothing after controlling for VIX and ATM IV ([FlashAlpha](https://flashalpha.com/articles/gex-dex-vex-chex-8-year-backtest-spy-vix-control)). Don't build a GEX filter until a VIX-plus-IV baseline is beaten in a pre-registered test.

## What data the desk lacks, and how to approximate it

| Need | Families | Free approximation | Caveat |
|---|---|---|---|
| Historical implied vol (ATM, by expiry, call vs put, OTM puts) | 3, 4, 5, 13, 14, 16, 25 | Solve Black-Scholes IV from Alpaca option trade bars (Feb 2024+): use the last trade in 15:45-16:00 per contract, matched to the stock's 1-minute price in the same minute; interpolate the two strikes around ATM; drop trades older than 30 minutes. Forward: a 15:45 Schwab chain snapshot (bid, ask, IV, OI, volume) for the 100 names, 3 expiries | Trade prices bounce between bid and ask, so single-day IV is noisy. Use 5-day averages for sorting. No IV history before Feb 2024, so these families can't be tested on 2016-2023 |
| Historical bid/ask | all option tests | Spread model measured from Schwab chains (desk practice); report at mid, 50% and 100% of spread | Spreads in 2024-2026 may differ from the model |
| Option volume per underlying | 15, 23 | Sum daily volume over all of the underlying's contracts in Alpaca option bars | Heavy pull; needs the full contract list per day. No signed (buy/sell, open/close) volume anywhere free, so Pan-Poteshman can't be replicated |
| Open interest | 23, 28 | Schwab chains, forward only | No history |
| Earnings dates | 1, 2, 12, 24 | EDGAR 8-K Item 2.02 acceptance times | Realized dates, not pre-announced ones: a look-ahead caveat (labeled in G2). Forward use needs a calendar Chart's computer can reach |
| Macro dates | 17, 29 | Fed and BLS public calendars | Manual list |
| VIX and VIX3M | 19, filters | Cboe's free daily history files (check from Chart's computer); else VIXY/VIXM price ratio from Alpaca | VIXY/VIXM is a futures-ETF proxy, not the index term structure |
| Earnings surprise (SUE) | 24 | EDGAR XBRL diluted EPS, seasonal random walk | No analyst consensus |
| Analyst revisions, index-change announcements | 30 | None free (analysts); S&P press releases (index) | Not worth the work given the evidence |

## Family notes

Each note gives the rules as published, the evidence, how it maps to bought options, and a "first test on our data". First tests are proposals for a future amendment; none is pre-registered by this document.

### 1. Pre-earnings straddle, sold before the report
- **Rules (Gao, Xing & Zhang 2018, JFQA).** Buy a delta-neutral ATM straddle (moneyness 0.95-1.05, 10-60 days to expiry, average about 38) 3 trading days before the earnings date. Results are reported for several windows ending around day 0.
- **Evidence.** 1996-2010, OptionMetrics. About 3.0% equal-weighted for [-3, 0] and about 2.3% for [-1, 0], against -2.09% a week for unconditional straddles. Option liquidity is the strongest predictor: returns are higher where option spreads are wider, which is also where costs are highest (BSIC quotes 1.14% for one spread quintile, holding window not stated). Costs reduce it; one summary says only near-term straddles stay positive after costs. Only about 18% of firms report within 10 days of an expiry.
- **Decay.** No post-2010 replication found.
- **Options mapping.** This is already an option strategy. What kills it: paying 5%+ half-spreads per leg; a report date that turns out wrong; holding through the report (IV crush). Caveat: windows ending at day 0 may include the reaction for companies that report before the open. The desk's G2 exits before the report in every case, so it may earn less than the paper.
- **First test.** Round 9 G2 is already pre-registered (DEV real prices, random-date benchmark). Add nothing until it reports.

### 2. Pre-earnings run-up of momentum winners (long calls)
- **Rules (Aboody, Lehavy & Trueman 2010, RAST).** Stocks in the top 1% of prior-year return. Buy about 5 trading days before the earnings announcement, sell at the first open after it. The broader earnings-announcement premium (Frazzini & Lamont: stocks expected to report this month beat the rest by more than 60 bps a month, 1972-2004; the global version is in [Barber et al.](https://alphaarchitect.com/introducing-the-global-earnings-announcement-premium/)) is the same idea at lower intensity.
- **Evidence.** 1971-2005. +1.58% market-adjusted in the 5 days before (+0.94% after bid-ask spreads), then -1.86% in the 5 days after. Full sample: +0.30%. About +0.35% a day over days -4 to 0.
- **Decay.** Not measured after 2005.
- **Options mapping.** A call with an expiry just after the report rises with the drift *and* with implied vol running up into the report, so the buyer gets two tailwinds. Sell at the last close **before** the report (scope rule), which gives up the day-0 part (+0.93% of the after-hours subset's +3.09%). What kills it: spread at entry and exit, and a small run-up in large caps.
- **First test.** Shares first: top 10% by 12-1 month return among the 100 names; enter the close 5 sessions before the 8-K 2.02 date; exit the last close before it. 2016-2023 discovery, DEV holdout, random-date benchmark. Then DEV real option prices: delta 0.5-0.6 call, first expiry after the report.

### 3. IV term-structure slope: long straddles where the curve slopes up
- **Rules (Vasquez 2017, JFQA).** Each month, slope = long-dated ATM IV minus 1-month ATM IV. Rank stocks into deciles; long ATM options (moneyness 0.95-1.05) on the highest-slope decile, short the lowest; hold one month.
- **Evidence.** 1996-2007, about 260-386 stocks a month. Long-short straddles 27.1% a month gross, with the **long leg alone +14.8%**, 81% of months positive. At 1.1x the spread (CXO): 12.3% net long-short. Alpha Architect reports 19.6% gross and 5.5% net at the quoted spread, insignificant at 1.25x.
- **Decay.** Similar in 1996-2000 and 2001-2007; nothing after 2007 found.
- **Options mapping.** Already an option strategy, and the published edge lives on the long side. What kills it: the spread, and too few names with several liquid expiries.
- **First test.** Build daily ATM IV for the 1-month and ~3-month expiries from Alpaca bars on DEV. Each month, buy the ATM straddle (expiry nearest 30 days) on the top 10 of 100 by slope, and hold to the next rebalance. Report at mid / 50% / 100% of the measured spread, against random-name straddles on the same dates.

### 4. Realized-minus-implied vol gap: long straddles where IV is cheap
- **Rules (Goyal & Saretto 2009, JFE).** Each month, sort stocks on log(1-year realized vol / ATM 1-month IV). Buy straddles on decile 10 (IV cheapest against realized), sell decile 1, hold one month.
- **Evidence.** 1996-2005, 3,885 stocks, about 110 per decile. Decile 10 straddles **+9.8% a month**, decile 1 -12.5%; long-short 21.9%. After costs (long-short): 13.0% at 50% of the quoted spread, 8.6% at 75%, 4.1% at 100%. The long leg net of costs isn't reported. Related findings point the same way: Cao & Han 2013 (options on high idiosyncratic-vol stocks are overpriced) and Vasquez (#3).
- **Decay.** Not measured after 2005.
- **Options mapping.** Native. What kills it: full-spread fills; and the 1-year realized vol used by the paper reacts slowly, so try it as pre-registered, not tuned.
- **First test.** As #3, sorting on the paper's ratio (1-year realized vol from Alpaca stock bars). Run #3 and #4 together and report their overlap, because they may pick the same names.

### 5. Option momentum
- **Rules (Heston, Jones, Khorram, Li & Mo, JF).** Rank stocks on the average past return of their ATM delta-neutral straddles over 6-36 months (1-month returns reverse, so skip the last month); buy winners, sell losers, monthly.
- **Evidence.** 1996-2019. About 6% a month for the zero-cost portfolio; Sharpe more than 3 times stock momentum's, before costs. Average returns are near zero after paying the full spread, even on options with below-median spreads. They stay profitable with deciles, by excluding wide-spread straddles, or by combining with the reversal signal.
- **Options mapping.** Native, but the formation window needs 6-36 months of straddle history, and the desk has about 24 months.
- **First test.** Low priority. The desk can only build a 6-12 month formation window inside DEV, so test #3 and #4 first. If it is tested at all, label it a short-window variant.

### 6. Trend breakout / new-high trend following on stocks
- **Rules (Zarattini, Pagani & Wilcox 2025, Concretum).** Buy at the next open when a liquid stock closes at its highest adjusted close in history. Exit at the next open after a close below an ATR trailing stop that is raised daily and never lowered. Turtle/Donchian rules are the 20/55-day version of the same idea.
- **Evidence.** US stocks 1950-2024, survivorship-free, more than 66,000 trades. About 15% CAGR gross and about 6.2% annual alpha for 1991-2024. Fewer than 7% of trades make most of the money, and the authors report this holds out of sample (2005-2024). Costs make the base version hard below $1 million, which the authors address with a turnover control.
- **Options mapping.** The payoff shape (many small losses, a few big winners) suits a long call, since the call caps the loss. But a long-dated call pays theta through the many failed breakouts. Use delta 0.6-0.7 calls 60-120 days out, roll near 30 days, and exit on the stock's stop. What kills it: theta on the losers, and IV that is often high after a breakout.
- **First test.** Shares on 2016-2026 bars for the 100 names (survivorship-biased, labeled): the paper's entry (or a 252-day closing high if all-time highs are too rare) and exit, its ATR stop, profit factor and the share of profit from the top 7% of trades. If it passes, run DEV real option prices with the call rule above.

### 7. 8-K / news continuation, same day
- **Rules (Jiang, Li & Wang 2021, JFE).** Jumps on identified news keep drifting; jumps without news reverse. The desk's version (round 9 G1): premarket 8-K, |gap| >= 2%, first 15 minutes in the gap direction, RV15 >= 3; enter in the gap direction, stop at the far end of the 15-minute range, out at 15:55.
- **Evidence.** In the 2018 draft, equal-weighted is negative after costs and value-weighted is about +8.6% a year net (registry #9). First reactions are priced within seconds to a minute (registry, Busse & Green).
- **Options mapping.** Weekly delta-0.5 options in the direction of the news, same day. What kills it: single-stock weekly spreads at the open, and IV falling through the day after news.
- **First test.** Round 9 G1 (shares) first. If it passes, add an options twin on DEV with a measured spread.

### 8. Cross-sectional stock momentum
- **Rules.** Jegadeesh & Titman 1993: rank on the past 12-month return skipping the last month; long the top decile, hold 3-12 months. Medhat & Schmeling (RFS): among the highest-turnover stocks, last month's winners keep winning (+1.37% a month, t = 4.74) and survive costs; among low-turnover stocks they reverse.
- **Evidence.** Replicated worldwide; survives costs in large studies. But US momentum profits were insignificant from about 1999 to 2012 ([Quantpedia summary](https://quantpedia.com/has-momentum-lost-its-momentum/)), and momentum crashes in rebounds after bear markets.
- **Options mapping.** About 1% a month gross per name, so a delta-0.7 call 60-90 days out gains about 7-9% a month on the edge and pays a few percent a month in theta plus 2-4% in round-trip spread: thin. The long call does cut crash risk. Better used as a filter for #2 and #6.
- **First test.** Shares, monthly, top 10 of 100 by 12-1 return, 2016-2023 discovery and DEV holdout, against random top-10 lists. Option twin only if shares pass with room to spare.

### 9. Time-series and dual momentum on ETFs
- **Rules.** Moskowitz, Ooi & Pedersen 2012: long when the past 12-month excess return is positive, short (or flat) when negative, volatility-scaled, monthly. Antonacci's GEM: hold US stocks, foreign stocks or bonds by 12-month relative momentum, with an absolute trend check.
- **Evidence.** Grade A in futures and asset classes over a century (AQR). GEM: 1,226 specifications were statistically indistinguishable, and the original rule is not special; a Sharpe around 0.9 gross, 1950-2018.
- **Options mapping.** Few trades and small monthly edges. Its best use is as the regime filter for the families above, not as an option trigger.
- **First test.** None standalone. Pre-register "SPY 12-month return > 0" as the regime filter variant for #2, #6, #8 and #10.

### 10. RSI(2) / oversold bounce in an uptrend
- **Rules (Connors & Alvarez 2008).** Close > SMA(200), close < SMA(5), RSI(2) < 10; buy the next open; sell the next open after a close > SMA(5). MA pullbacks and "N down days in an uptrend" are variants of the same buy-the-dip-in-an-uptrend idea.
- **Evidence.** Book tests on 1995-2007 had no out-of-sample test and no data-snooping control (CXO). A practitioner Nasdaq-100 test for 2006-2025 reports a 64% win rate, +2.33% / -3.02% average win/loss and PF 1.45, with no costs stated.
- **Options mapping.** About +0.4% a trade over a few days. A delta-0.7 call 30-60 days out turns that into a few percent, roughly the round-trip spread. The high win rate is attractive, but expectancy is what counts.
- **First test.** Round 9 F1 and F-opt are already pre-registered. Wait for them.

### 11. 52-week-high proximity
- **Rules (George & Hwang 2004).** Rank on price / 52-week high; long the top decile, hold 6 months.
- **Evidence.** 1963-2001; alphas survive the usual factor models but not the q-factor model, and Alpha Architect calls it "not robust to small alterations".
- **Options mapping.** As #8: monthly edge too small for options on its own.
- **First test.** None standalone. If #6 is tested, report its trades split by distance from the 52-week high.

### 12. Earnings-day gap continuation (day 0)
- **Rules.** No published mechanical day-0 rule with cost-inclusive evidence was found. Martineau 2022 says large-cap earnings news is priced on day 0, which leaves only intraday continuation, if any.
- **Options mapping.** Poor: implied vol keeps collapsing through day 0, and weekly spreads are widest at the open.
- **First test.** None new. The `earn_day` forward ledger and G1's earnings subset already cover it. Read them in shares first.

### 13. IV spread and IV innovations
- **Rules.** Cremers & Weinbaum 2010: call IV minus put IV at the same strike and expiry; long stocks with rich calls, short stocks with rich puts; weekly. An, Ang, Bali & Cakici 2014: stocks whose call IV rose most last month outperform; rising put IV predicts low returns.
- **Evidence.** 1996-2005: 0.51% a week risk-adjusted, value-weighted, before costs, and the predictive power **declined over the sample**. An et al.: about 1% a month for the call-IV sort, lasting up to 6 months, before costs.
- **Options mapping.** A weekly edge of tenths of a percent can't pay option spreads. Possible only as a monthly stock-direction filter.
- **First test.** Defer. It needs same-strike call and put IV, which is the noisiest thing to compute from trade bars. Revisit once 6+ months of Schwab chain snapshots exist.

### 14. Volatility smirk
- **Rules (Xing, Zhang & Zhao 2010).** Smirk = OTM put IV minus ATM call IV. Long the flattest-smirk decile, short the steepest; weekly rebalance; predictability lasts up to 6 months.
- **Evidence.** 1996-2005, about 15% a year risk-adjusted before costs. The steepest-smirk firms had the worst earnings surprises the next quarter. Bimonthly rebalancing with rough costs "may be profitable".
- **Options mapping.** Puts on steep-smirk names cost more (that is what the smirk measures), so the buyer pays for the signal. Better as a filter: skip calls on the steepest-smirk names.
- **First test.** As #13: defer until forward chain snapshots exist; then a monthly filter test layered on #2 or #6.

### 15. Option-to-stock volume ratio (O/S)
- **Rules (Johnson & So 2012, JFE).** O/S = option volume / stock volume. The lowest decile beats the highest by 0.34% a week (about 19% a year). O/S also predicts earnings news.
- **Evidence.** Single source, gross; stronger when short-sale costs are high.
- **Options mapping.** Weekly edge too small for option round trips; usable as a filter (avoid calls on extreme high-O/S names).
- **First test.** Data-feasible on DEV (Alpaca option volume summed per underlying). Shares first: weekly decile sort among the 100 names, DEV only, against random sorts. Option twin only if the share edge is far above spread.

### 16. Vol-of-vol
- **Rules.** Ruan 2020: VOV = the monthly standard deviation of daily ATM 30-day IV. Delta-hedged options on low-VOV stocks beat those on high-VOV stocks by about 3% a month (1996-2016). Baltussen et al. 2018: high-VOV stocks also have lower stock returns.
- **Options mapping.** Both point the same way for a buyer: buy options on stocks whose IV is stable, and avoid options on stocks whose IV swings. A filter for #3 and #4, not a strategy.
- **First test.** Once daily IV exists for DEV, report #3 and #4 split by VOV tercile (information only), then pre-register a filter if warranted.

### 17. Pre-FOMC drift
- **Rules.** Lucca & Moench 2015: stocks rose about 49 bps in the 24 hours before scheduled FOMC announcements (1994-2011).
- **Evidence.** Kurov, Halova Wolfe & Gilbert: the drift fell to 0.09% in 2016-2019 (meetings with press conferences), indistinguishable from ordinary days. Martello & Ribeiro: 109 bps when implied vol is above its median, 9.7 bps below.
- **Options mapping.** A short-dated SPY call held from the prior close to 13:55 on FOMC day, exiting before the IV crush. That's about 4 qualifying events a year, too few to test.
- **First test.** Information only: tabulate SPY's prior-close-to-13:55 return on FOMC days, 2016-2026, split at the VIXY median. No ledger: the sample is too small.

### 18. Turn of the month
- **Rules.** Buy the close of the last trading day of the month; sell the close of the third trading day (Lakonishok & Smidt; McConnell & Xu).
- **Evidence.** Persistent over a century and in many markets (A), but small per window. The Quantpedia extract quotes about 0.15% for the (-1, +3) strategy and is unclear about the unit; either way it is a fraction of a percent per 4-day window.
- **Options mapping.** A 4-day hold on a short-dated call pays theta on every day, including a weekend in most months. Poor fit.
- **First test.** Round 9 F2 (shares) is registered; no options twin unless F2 shows an edge per trade several times the option spread.

### 19. VIX term-structure backwardation
- **Rules.** Fit the VIX futures curve; a negative slope (backwardation) has been a contrarian buy signal for the S&P 500 (2010-2017, one study, no costs or out-of-sample test).
- **Options mapping.** Calls are most expensive exactly when the signal fires. Few episodes.
- **First test.** Information only: with the VIXY/VIXM ratio (or Cboe CSVs if reachable), list backwardation days in 2016-2026 and SPY's 5/10/20-day returns afterwards against all days. Use as a filter candidate only.

### 20. Overnight-intraday gap reversal
- **Rules.** Lou, Polk & Skouras 2019: momentum profits accrue overnight and partly reverse intraday; the desk tested a stressed-day SPY gap fade (registry #11).
- **Desk result.** Failed in 10 years of shares (run 8 A3: 486 trades, -$3.91 a trade, 3 of 8 years). The DEV-only option pass was judged period luck.
- **First test.** None. Retired by the desk's own evidence.

### 21. Short-term reversal
- **Rules.** Buy last week's or last month's biggest losers.
- **Evidence.** Grade A that it existed, and grade A that costs absorb it: Medhat & Schmeling find microcap reversal of 2.04% a month against about 1.94% a month in costs, weakening since 2011. Avramov, Chordia & Goyal tie it to illiquid stocks.
- **Options mapping.** Avoid: the edge lives where options are least liquid.
- **First test.** None.

### 22. IBS (internal bar strength)
- **Rules.** IBS = (close - low) / (high - low). Buy at the close when IBS < 0.2, sell at the next close.
- **Evidence.** 15 country ETFs, 2009-2019, one sample with no holdout and best baskets selected from many combinations. Moving the entry from the close to the next open turned the top basket's Sharpe from 3.73 to -0.25.
- **Options mapping.** Avoid: a 1-day hold pays the full round trip for a tiny move, and the edge needs close-to-close fills.
- **First test.** None.

### 23. Put/call ratios and unusual options activity
- **Rules.** Pan & Poteshman 2006: put open-buy volume / (put + call open-buy volume); low-ratio stocks beat high-ratio stocks by more than 0.4% the next day and more than 1% the next week (1990-2001).
- **Evidence.** The predictive power comes from non-public signed data. Public ratios predict only 1-2 days and then reverse. Bergsma et al. 2020: dollar-volume-weighted call moneyness predicts next-day returns (5.4 bps a day), but daily rebalancing costs eliminate it.
- **Options mapping.** "Follow the unusual call buying" has no cost-inclusive support with public data.
- **First test.** None until signed volume is available, which it isn't for free.

### 24. Post-earnings drift in liquid names
- **Rules.** Long top quintiles of SUE and the 3-day announcement return, enter day +2, hold about 60 days (Quantpedia version).
- **Evidence.** Gone for non-microcaps since about 2006 (Martineau 2022). A 2025 replication finds t = 1.43 once microcaps are excluded (UCLA Anderson summary).
- **Options mapping.** Avoid: what drift remains lives in microcaps with unusable options.
- **First test.** None (registry #5 already records the negative result).

### 25. Low IV rank long options
- **Rules (tastytrade shows).** Buy straddles when IV rank is low.
- **Evidence.** Vendor shows with no published methodology; tastytrade itself sells premium. No peer-reviewed support for IV rank as such. The peer-reviewed version of "cheap vol" is relative to realized vol (#4) or across expiries (#3), not against the stock's own IV range.
- **First test.** None standalone. Report #4 results split by IV rank for information only.

### 26. Intraday index momentum, noise band and ORB on 0DTE
- **Desk result.** Runs 1, 7 and 8: every intraday stock setup and the noise band lost money when carried by 0DTE options (noise PF 0.78-0.89, ORB PF 0.80-0.88). The vol-sized noise band in shares nearly passed (run 8). The only intraday options survivor is FIN-H's far-OTM busy-day calls, which is a desk result, not a published family.
- **First test.** None new. Round 10 (Amendment 15) already covers the noise band's settings.

### 27. Other calendar effects
- **Evidence.** Overnight returns beat intraday returns for SPY, QQQ and 12 of 14 ETFs in 1993-2006 (Cliff, Cooper & Gulen). Same-half-hour intraday return continuation exists but is about 3 bps per half-hour, below costs (Heston, Korajczyk & Sadka). I found no recent cost-inclusive evidence for pre-holiday or day-of-week effects in this pass.
- **Options mapping.** Avoid: holding options overnight or into holidays pays theta for every calendar day, and weekend option returns are worst (Jones & Shemesh).
- **First test.** None.

### 28. Dealer gamma (GEX)
- **Evidence.** SPY 2018-2026, pre-registered tests: GEX predicts next-day realized vol (rho -0.36), but not after controlling for VIX and ATM IV (rho -0.03, p 0.18), and gives no next-day return signal. Adams et al. find market-maker gamma effects of 1-3 bps and say they are not tradable from public data.
- **First test.** None as a signal. If Schwab chain snapshots accumulate, test only "does GEX add to a VIX + IV baseline", pre-registered.

### 29. Straddles held through FOMC, CPI or earnings
- **Evidence.** Delta-neutral straddle returns around macro announcements are negative across windows and weightings (no evidence that buying ahead pays). 1-day NDX straddles over the last 12 FOMC meetings were overpriced 10 times. Earnings straddles held through the report are out of scope for the desk.
- **First test.** None. This is a "don't".

### 30. Index additions and analyst rating changes
- **Evidence.** S&P 500 addition returns fell from 7.4% in the 1990s to under 1% (insignificant) in the 2010s ([Greenwood & Sammon, JF 2025](https://ideas.repec.org/a/bla/jfinan/v80y2025i2p657-698.html)). Analyst revisions mostly follow public news, with "economically insignificant" price reactions (Altınkılıç & Hansen), and there is no free data.
- **First test.** None.

## Suggested order for the next amendment

1. Read round 9's G2 (pre-earnings straddle), G1 (news continuation), F1/F-opt (RSI2) and F2 (turn of the month) results first: they test families 1, 7, 10 and 18 with rules already frozen.
2. **Data step, no results:** build daily ATM IV per expiry for the 100-stock universe on DEV from Alpaca option bars, and start a daily 15:45 Schwab chain snapshot (bid, ask, IV, OI, volume). Validate IV against the Schwab snapshot on overlapping days before any sort is run.
3. **One amendment, three option-native tests on DEV,** pre-registered together with a shared random-name benchmark and spread levels of mid, 50% and 100%: #3 (term slope), #4 (RV-IV gap) and #2 (pre-earnings run-up calls; shares 2016-2023 first). Trial count: 3, added to the deflated-Sharpe N; the spread levels are sensitivity readings of the same 3 trials, and pass/fail is judged at 100% of the measured spread.
4. **Shares first, then options:** #6 (new-high trend following) on 2016-2026 shares.
5. Everything ranked 11 and below: filters or information-only tables, or nothing.

## Search method and limits

- **Date:** 2026-11-01 UTC. WebSearch plus WebFetch. Every page was treated as data, not instructions.
- **Depth:** the fetch tool returns extracts. Most papers were read through abstracts, journal or author pages, or summaries (Alpha Architect, CXO Advisory, Quantpedia, Concretum, Harbourfront Quant). Goyal & Saretto's numbers come from a PDF of the paper. Figures quoted from summaries are labeled with the summary's link.
- **Not found or not verified:** post-2010 replications of the pre-earnings straddle, Vasquez and Goyal-Saretto; cost-inclusive long-leg-only results for any option-sorted strategy; recent cost-inclusive evidence on pre-holiday or day-of-week effects. A Critical Finance Review pre-holiday paper could not be fetched.
- **Survivorship:** the 100-stock universe in every estimate is today's liquid names (survivorship-biased); trade counts are rough.
