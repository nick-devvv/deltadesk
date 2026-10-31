# DeltaDesk v4 strategy plan: a quantitative whole-market intraday desk

Written 2026-10-31. Source document: "DeltaDesk 0DTE quant rebuild" (Claude Docs). All rules below are provisional, frozen before testing, and unvalidated until they pass the gates in section 5.

**Scope (v4, from 2026-10-31): day trading in general.** Everything opens and closes in the same session.
- **Core:** 0DTE SPY and QQQ options.
- **Everything else:** any liquid US stock or ETF, day-traded in shares, or in options of any expiry that are opened and closed the same session.
- **Never:** futures, or anything held overnight.

**Four books, one engine, one risk layer.** Index momentum (SPY, QQQ, IWM, XSP; liquid ETFs as research candidates), index premium selling (SPX/XSP first, then SPY/QQQ), stocks in play (the day's top stocks by opening relative volume, option-liquid only), and catalysts (any stock with a verified news/earnings/filing catalyst and a measured reaction). Each strategy x instrument x timeframe x version is its own ledger. Each family runs on its published timeframe plus at most two alternates chosen before testing; every alternate counts as a trial for the deflated Sharpe.

## 1. What stays, what goes

**Keep**
- `noise` ledger (`noiseband.py`), unchanged, including the 20% premium stop. Report SPY and QQQ separately.
- The matched-random-entry scorer (from the lab).
- The specialist router, repurposed as the promotion gate.
- Desk-wide rules for long-premium ledgers: 20% planned premium-loss line, entries 09:45–15:15 ET, all out 15:25 ET.

**Retire** (stop new entries, keep code and history, manage any open position to its exit)
- SPY/QQQ: `paper` (main v3), `research`, `exit31`, `gated`, `orbx_swing`, `orbx_atr`, `orbx_2r`, `orbx_ormid`.
- Exception (Nick, 2026-10-31): `old` (policy_old.py, frozen 2026-10-28.3 rules) stays ACTIVE as a legacy forward test (not from a published source), shown next to the v4 ledgers with the same metrics. Its behavior is unchanged (tests/test_v4_old_regression.py).
- `earn_pre` (holds options through the report: pays the IV crush, no stop protects the gap).

**Rebuild on published rules** (stop the current versions, replace with new versioned ledgers in section 4): `news_mom`, `inplay`, `board`, `earn_post`.
- All 15 strategy-lab families (`lab_*`), and `spec_*` fills. The lab ENGINE (every family on every scanned stock, scored against matched random entries) is kept and becomes the v4 engine.
- Kronos forecasts: off by default.

**Why** (desk data, Sep 22 – Oct 29 2026, 28 sessions, modeled option prices, mostly in-sample)
- v3 signals on 433 setups: −$9.00/trade, PF 0.44; random direction −$6.73; opposite direction −$4.43.
- Runner exits on the same entries: −$12.16/trade, PF 0.51.
- ORBX: no edge over matched random entries; ORB15 SPY/QQQ −0.565R over 30 trades; ORB15 stocks −0.224R vs −0.173R for controls (n 1,947).
- Stocks in play with modeled options: 425 trades, −$19.49/trade, PF 0.64, max DD $8,329.
- Noise band (kept): 61 trades, 23% wins, +$22.48/trade, PF 1.67.

## 2. Evidence summary

- Buying 0DTE index options loses on average (retail SPX 0DTE longs −53%, −61% after May 2022; shorts +48%; Beckmeyer, Branger & Gayda 2023). The intraday variance premium is positive but small (SPY 10:00 straddle implied move overstates the realized move by about 13%, FlashAlpha 2026, 193 sessions, mids, no costs).
- Unconditional daily 0DTE selling is weak after costs and tail risk; conditional out-of-sample rules reach Sharpe about 1.0–1.3 on SPXW 2016–2026 before retail frictions (Vilkov, replication package `vilkovgr/0dte-strategies`).
- Noise-area momentum: four independent replications (2025–2026). SPY Sharpe about 0 since 2025; NQ positive after publication but not significant (t = 1.37); ES negative after publication.
- Dealer-gamma effects are real but small (1–3 bp over 30–120 min) and not tradable from free open-interest data (Adams et al. 2026). Use only as a recorded condition.
- Tail day reference: 2025-04-09, SPY +8.72% vs a 3.51% implied move.

## 3. Index books (SPY and QQQ, each also run on SPX/XSP; 1 contract or 1 spread per ledger, paper)

1. **`noise`**: unchanged.
2. **`noise_v2`**: same entries as `noise`. Exit only on a half-hour (HH:00/HH:30) close through max(upper band, VWAP) for calls or min(lower band, VWAP) for puts, as in Zarattini, Aziz & Barbon (2024). A disaster stop at −50% of premium on the bid replaces the 20% line. All out 15:25.
3. **`orb_credit`** (Option Alpha, "Opening range breakout 0DTE", 2025; SPX, $15 wide, held to close, 89.4% wins, PF 1.44, max DD −$3,453, costs not modeled):
   - Opening range = high/low of 09:30–10:30 ET. Skip the day if the range width is < 0.2% of the 09:30 open.
   - First finished 1-minute close above the range high before 12:00 ET → sell a $2-wide put credit spread, short strike = the first listed strike at or below the range low.
   - First finished 1-minute close below the range low before 12:00 ET → sell a $2-wide call credit spread, short strike = the first listed strike at or above the range high.
   - One trade per symbol per day. No stop, no target. Exit 15:25 ET (deviation: the source holds to the close; SPY/QQQ are American-style and can be assigned).
4. **`ic_20d`** (tastytrade 0DTE SPX iron condor study, via StockWire X 2026-09-27; 20-delta shorts, $20 wings, ~72% wins unmanaged; 2× stop kept win rate near 70% and cut CVaR ~13%):
   - At 10:00 ET sell the call and the put nearest 20 delta, buy wings $2 further out.
   - Close the whole condor when its cost to close (at the ask) reaches 2× the credit received; otherwise exit 15:25 ET.
   - Skip FOMC days (config/events.json).
5. **`noise_trend`**: same entries as `noise`, taken only on likely trend days. Score known before each entry, thresholds frozen now: (a) VIX at the check above its 20-day median; (b) 09:30-10:00 volume >= 1.5x its 14-day average for that half hour; (c) |09:30-10:00 return| above its 14-day average; (d) FOMC, CPI or jobs-report day. Trade when >= 2 of 4 are true. Basis: Gao, Han, Li & Zhou (2018, JFE): intraday momentum is "stronger on more volatile days, on higher volume days, on recession days, and on major macroeconomic news release days"; the noise-band authors report Sharpe 3.50 when VIX > 40 (in-sample). Test each condition alone and the combined score on SPY/QQQ 1-minute bars since 2016; it must beat the same strategy skipping the same number of randomly chosen days, and raise profit per day (not just win rate) on held-out years. No condition may use information from after the entry.
6. **Conditional selector (phase 2, research only)**: rebuild Vilkov's conditional 0DTE strategy selection on SPY/QQQ from his public replication package after the data layer exists. Not a ledger until it passes the gates.

**Recorded on every trade, never used as a filter until separately pre-registered and tested:** FOMC/CPI/jobs-day flag, opening gap %, VIX1D (if available), realized vs implied move so far, weekday.

**Selling-ledger risk rules:** size by max loss (width − credit); one open spread per ledger; a shared daily loss cap across selling ledgers; legs priced from fresh Schwab quotes; exit by 15:25.

## 4. Stock books (stocks in play, catalysts)

Evidence: `docs/research/CATALYST_EVIDENCE.md`. No public rule set survives realistic costs yet (all grade C), so shares are the measuring stick for every stock-book signal and options are added only after the share version is positive after slippage. Flat by 15:55 ET; one position per symbol per ledger; 1 unit per trade on paper.

1. **`sip_orb5`** (Zarattini, Barbon & Aziz 2024, published rules): universe = price > $5, 14-day average volume >= 1M shares, 14-day ATR > $0.50. RV = 09:30-09:35 volume / its 14-day average; trade the top 20 with RV >= 100%. First 5-min candle green -> buy-stop at its high only; red -> sell-stop at its low only; doji -> no trade. Stop = 10% of 14-day ATR; otherwise exit 15:55. (Claimed 2016-2023: Sharpe 2.81, 48.4% wins, +0.08R/trade for RV > 100%, +0.38R for RV > 30x; no slippage modeled.)
2. **`sip_orb5_x`**: as `sip_orb5` with RV >= 5x, ATR >= $2 (stop >= $0.20), entry on a finished bar's close with a next-bar fill, after-hours prints excluded. Results bucketed by stop size in cents.
3. **`sip_orb15`**: published 15-minute alternate (paper Sharpe 1.43).
4. **`earn_day`**: `sip_orb5_x` restricted to the first session after an earnings report (EDGAR 8-K Item 2.02 or calendar).
5. **`news_drift`** (event study first, then a ledger): verified catalyst timestamp (EDGAR 8-K acceptance time, or a headline fetched and verified by the desk); 5-minute RV >= 3x after it; direction = first finished post-news 1-minute bar; entry next bar. Measure 15/30/60/120-minute moves net of half the spread, 2016-2026. Pick the holding time on the first 2/3 of events; it becomes a ledger only if it holds on the last 1/3.
6. **`earn_runup`** (research only, multi-day): delta-neutral ATM straddle bought 1-3 days before a scheduled report, sold the day before (Gao, Xing & Zhang 2018: +1.9-2.6% per window at mids, 1996-2013, no costs; edge concentrated in wide-spread names). Test on Alpaca option prices only.

**Option rules for stock books (hypotheses, tested like everything else):**
- Only names on the current quarterly "Qualifying Securities" list (Mon/Wed/Fri expiries; Q3 2026 per MIAX: AMD, GOOGL, AMZN, AAPL, AVGO, XLF, INTC, META, MU, MSFT, NVDA, TSLA, SMH; verify against Cboe/Nasdaq) and penny-program names.
- Skip if spread > 10% of mid, or if the round-trip spread exceeds half the trade's expected edge (in option terms via delta).
- In-the-money, delta about 0.6-0.8, 0-7 DTE. Never hold through an earnings report.

## 5. Gates (every ledger)

1. **Pre-register** rules, parameters, data window, cost model and pass/fail thresholds in `docs/research/STRATEGY_REGISTRY.md` before any result.
2. **Signal test** for signal-driven ledgers (`noise`, `noise_v2`, `noise_trend`, `orb_credit`, all stock-book ledgers) on 1-minute bars since 2016 (Alpaca stock bars), next-bar entry; 2022-2026 also reported on its own.
3. **Option test** on Alpaca option bars/trades, 2024-02 to now. First 2/3 for code checks, last 1/3 held out. Fills at trade price ± half the modeled spread; $0.65 per contract per side; matched random entries on the same sessions.
4. **Pass bar:** held-out expectancy > 0 after costs, profit-factor 95% session-bootstrap interval above 1.0, deflated Sharpe when more than one variant was tried. Index-option families: at most ~10 variants in total (about 2.7 years of option history). Stock books produce far more trades and can afford more, but every variant is logged and charged in the deflated Sharpe.
5. **Forward paper:** 40 live paper trades within the backtest's range → promotion to main paper by the router. This gate checks modeled vs real fills (40 trades pin a win rate to only ±15.5 points); the edge itself must come from gates 3-4.

Sample sizes: 55% vs 50% win rate ≈ 271 trades (one-sided) / 385 (two-sided); PF 1.3 vs 1.0 at 80% power ≈ 364–810 trades (≈483 for an 80%-win spread, ≈810 for a 90%-win spread).

## 6. Data

- **Schwab** (connected): SPY/QQQ 1-minute bars, live quotes and chains, no option history. Log 0DTE chains every minute from now on to measure real spreads.
- **Alpaca** (paper key on the desk): option bars and trades from Feb 2024, expired contracts included, no historical quotes. The free plan's option feed may be Alpaca's derived "indicative" feed; compare against Schwab quotes on the first pull. Known gaps reported on 2024-02-26 and 2024-03-15.
- Claude's cloud workspace cannot reach data.alpaca.markets (proxy 403, checked 2026-10-31), so history pulls and backtests run on Chart's computer.
