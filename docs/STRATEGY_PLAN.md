# DeltaDesk v4 strategy plan: a quantitative whole-market intraday desk

Written 2026-10-31. Source document: "DeltaDesk 0DTE quant rebuild" (Claude Docs). All rules below are provisional, frozen before testing, and unvalidated until they pass the gates in section 5.

**Scope (widened 2026-11-11 by Nick): stocks, ETFs and long options, any holding period.** Earlier v4 scope (2026-10-31) was day trading only; the sections below that say "same session" describe the day ledgers, which keep that rule.
- **Same-day books:** 0DTE SPY and QQQ options at the core; any liquid US stock or ETF in shares, or in options opened and closed the same session.
- **Multi-day books:** shares and long options held days to weeks, each in its own isolated risk book (like `swing` for `etf10_rsi2`, section 8), sized so a 3-sigma day is at most 1.5% of equity.
- **Not yet:** crypto (needs a data source and a pre-registered test). **Never:** futures.
- Every ledger still needs a pre-registered pass and Nick's go for paper. See `CLAUDE.md` Scope.

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

## 7. Sprint paper ledgers (forward tests)

Added 2026-11-02. Nick said yes (2026-10-31) to paper-only forward tests of the sprint's best near-misses. **These three ledgers are NOT promoted.** Each one failed at least one of its pre-registered robustness checks. Promotion still needs every gate in CLAUDE.md step 5:
- a pass on data the rules were never tuned on;
- at least 40 forward paper trades;
- a multiple-testing haircut (the sprint tried 3,187 variants; the deflated Sharpe of every run below is 0.000).

**Labels.** Forward results are **PAPER (simulated fills)** on live Schwab quotes, never real money. The backtest numbers below are **BACKTEST, in-sample** (DEV, Aug 2024 to Jun 2026, Alpaca 1-minute prices, MODELED 2% half-spread, $0.65 per contract per side, 1 contract, SPY + QQQ + IWM pooled).

**Where.** Module `sprint_paper.py`, book `sprint`, symbols SPY and QQQ, 1 contract per trade. Each ledger can be switched off in `config/v4.json` (`sprint_paper`). Off stops new entries only; open trades are still managed to their exit.

| Ledger | Source run | Backtest: trades / exp $ / PF / PF 2x / max DD | Failed checks |
|---|---|---|---|
| `fb_or` | setups_v2-012 | 429 / +18.57 / 1.78 / 1.27 / -$1,452 | Aug-Dec 2024 lost (-$609, PF 0.71). Positive without the best 5 (+$688). |
| `otm_put` | otm_v1-011 | 375 / +10.20 / 1.655 / 1.52 / -$1,690 | Jan-Jun 2026 lost (-$1,514, PF 0.29); negative without the best 5; 2 of 11 two-month blocks up. |
| `otm_bounce` (**WATCH-ONLY**) | otm_v1-042 | 44 / +130.48 / 10.34 / 9.44 / -$534 | Under 60 trades, all from one high-volatility episode (April 2025 dominates). |
| `otm_h` (rule H, added 2026-11-02) | otm_v1-040 + f_rvol >= 1.06 | 485 / +13.22 / 2.35 / 2.10 / -$1,278, **out-of-sample**: rule frozen on 2016-2019, scored on DEV REAL prices | Negative without the best 5 (-$1,083); +$58 without 2025-04-09; 8 of 23 months green; locked-period exam not run. |

### Rules (identical to the backtest runs)

The code reads each ledger's rules from its sprint spec (`sprint/specs/setups_v2.json`, `sprint/specs/otm_v1.json`), pinned by sha256. If a spec file changes, the ledger refuses new entries and records why.

1. **`fb_or`** (setups_v2-012): failed-break calls at the opening-range lows.
   - Levels: OR15L and OR30L (the low of the first 15 / 30 minutes).
   - Break: a finished 1-minute close more than $0.01 below a level.
   - Signal: within 5 bars, a finished close back above it, with the lowest low since the break no more than 0.5 x ATR(14, 5-minute) below the level.
   - One signal per level per day. Signal bars 09:45 to the bar finishing 15:15.
   - Contract: today's 0DTE call with BS-EST |delta| 0.40-0.55, nearest 0.45.
   - Exit: a premium-loss stop fixed at the entry window's value: 20% if the signal bar ends 09:45-11:30, 12% for 11:30-14:00, 10% for 14:00-15:30 (time rule b, no tightening). No breakeven, no target. All out 15:25.
2. **`otm_put`** (otm_v1-011): far out-of-the-money puts at 10:30 on calm up days.
   - Signal: the bar finishing 10:30, every session, if all filters pass:
     - VIXY percentile <= 40%: the share of the last 252 daily VIXY closes, up to the prior session, that are at or below the prior close;
     - VIXY not rising: VIXY's last finished 1-minute close at the signal bar <= its prior close x 1.01;
     - day up: the underlying's close at the signal bar >= its prior close;
     - Wednesday to Friday only;
     - skip the third Friday (monthly expiration).
   - Contract: |delta| 0.06-0.15, nearest 0.10.
   - Exit: a -95% stop on the debit (practically: hold). The backtest's +9900% target is kept. All out 15:25.
3. **`otm_bounce`** (otm_v1-042), WATCH-ONLY: far out-of-the-money calls at 11:00 on stressed down days.
   - Signal: the bar finishing 11:00, if VIXY percentile >= 60%, the underlying is below its prior close, and it isn't the third Friday.
   - Contract: |delta| 0.03-0.12, nearest 0.07. Exit as `otm_put`.
4. **`otm_h`** (rule H, FIN-H: otm_v1-040 plus one entry-feature rule), added 2026-11-02 at Nick's yes (2026-11-01): far out-of-the-money calls at 11:00 on busy days.
   - Signal: the bar finishing 11:00, every session, taken only when `f_rvol` >= 1.06 at that bar.
     - `f_rvol` = regular-hours volume so far today / the mean volume of the same minutes over up to 14 prior sessions (at least 10), rounded to 2 decimals (`sprint/daytype.py`).
     - The cut was found on 2016-2019 only (SPRINT_PLAN Amendment 6) and frozen as FIN-H (Amendment 7).
   - It passed 2020-2023 (MODELED) and Aug 2024-Jun 2026 on real option prices; run 7 confirmed it over 10 years (`docs/research/SPRINT_RESULTS_5.md`, `_7.md`).
   - Contract: |delta| 0.03-0.12, nearest 0.07. Exit as `otm_put`: -95% stop, all out 15:25.
   - Shape: most trades lose the small debit, and a few big up days pay for everything. On real prices, 2025-04-09 alone made more than the whole period.

An unknown input (no VIXY bars, no VIXY daily closes, no prior close, or an unknown `f_rvol` for `otm_h`) means no trade, and the reason is recorded.

### How live stays identical to the backtest

- **Signals:** the engine's finished 1-minute bars become the sprint's own day context, and the sprint code (`sprint.entries.signals`) finds the signals. A bar counts only after its minute has ended.
- **Filters:** the sprint code too (`sprint.engine._filters_ok`), with VIXY supplied the way the backtest supplied it.
- **Contract:** the sprint picker (`sprint.contracts.pick`). Each contract's price is the live chain mid; the backtest used the last trade. BS-EST delta uses the underlying's close at the signal bar and the minutes to 16:00 from that bar's end. The chain's own delta is recorded next to it.
- **Entry:** the fill needs an executable quote dated after the signal bar, inside the backtest's 3-minute entry window. A signal not filled by then is MISSED, and recorded. Buy at the ask, $0.65 per contract. One position per symbol per ledger; a signal while busy is skipped and recorded.
- **Exit triggers, as `sprint/sim.py` computes them:**
  - ceiling (`fb_or`): cost = ask + $0.0065. Stop when the bid, net of $0.0065, falls to cost x (1 - ceiling).
  - fixed (`otm_*`): stop when the mid falls to the fill x 0.05; target when the mid reaches the fill x 100. The sim triggers on the traded price, the mid's stand-in.
  - Exits sell at the bid. With no quote, the exit waits (PENDING) and retries every tick.
- **Recorded on every trade:** the sprint's entry features, every filter input, the contract choice (mid, bid, ask, spread, BS-EST delta and IV, chain delta), the signal and the source run id.
- **Recorded on every signal:** a decision (ORDER, SKIP, FILTERED, BLOCKED-RISK, MISSED, NO SIGNAL), with its reason.
- **Restart-safe:** decision and position ids are fixed per signal, so a restart never enters twice.

### Deviations from the backtest

- SPY and QQQ only. The backtests pooled SPY, QQQ and IWM, but the engine has no IWM snapshot (`config/policy.json` is frozen).
- Schwab bars and live quotes replace Alpaca bars, last trades and the modeled spread. This is what the forward test measures.
- VIXY comes from Schwab: 1-minute bars, and daily closes for the percentile. All of the last 252 closes count; the backtest's file skipped the never-pulled locked months.
- Features that need long history (daily ATR over 60 sessions) see the engine's ~30 days. They are recorded only; no entry or exit rule uses them.
- The v4 risk layer can block an entry the backtest would take (kill switch, sprint-book caps, a $600 sprint-book daily paper loss limit). Every block is recorded.
- On 1 PM early-close days, the desk's 12:30 last entry is stricter than the backtest's 12:50.
- `otm_h`: `f_rvol` uses Schwab volume for today and the prior sessions (the backtest used Alpaca volume for both). With fewer than 10 prior sessions in the engine's snapshot, the signal is FILTERED and recorded.
- The sprint book's caps went from 6 to 8 open positions (and 8 same-direction) for the fourth ledger (`v4risk.py` risk3).
- Not a deviation from the backtest, but from the desk-wide 20% premium line (section 1): `otm_put`, `otm_bounce` and `otm_h` use their backtest's -95% stop instead, the way `noise_v2` uses -50%. The most either can lose is its debit (cheap far out-of-the-money options) plus fees. `fb_or`'s ceilings are 20% or tighter.

### What the forward test measures (fixed before any forward trade)

- **Fills vs the model:** the half-spread actually paid at entry and exit vs the backtest's 2% assumption, and how many signals the live desk filled.
- **Results, after 40 trades per ledger:** trades, win rate, average win and loss, expectancy after costs, profit factor, max drawdown and a session-bootstrap 95% interval (`/api/v4`, Research page).
- Under 30 trades is not evidence. A forward test can show the live fills match the model, but 40 trades cannot prove an edge built on 20-30 big days.
- No rule changes during the test. A change ships as a new versioned ledger, and this one keeps running.

**Risk book `sprint`** (`v4risk.py`): at most 6 open, at most 6 in one direction, and a $600 daily paper loss limit. The book is **isolated**: its positions never count toward any other ledger's caps, so the existing ledgers behave exactly as before. The v4 kill switch blocks its entries; exits are never blocked.

## 8. ETF swing ledger `etf10_rsi2` (forward test, held overnight)

Added 2026-11-10. Nick said "go" to a paper forward test of the first strategy that passed both a research window and a sealed out-of-sample window. **Not promoted.** It is the only v4 ledger that holds positions overnight.

**Labels.** Forward results are **PAPER (simulated fills)** on live Schwab quotes. Backtest numbers are **BACKTEST** on WRDS CRSP daily data (split-adjusted, survivorship-free), run on Nick's computer; the notes are in Nick's TradingVault (`Research/2026-11-09-t56-prereg`, `-t56-result`, `-t6-sealed-result`).

**Rules (frozen as T6 R2, pre-registered 2026-11-09 before any result).**
- Universe: SPY QQQ IWM DIA XLF XLE XLV EEM GLD TLT. Long only, shares.
- Signal on the last finished daily bar: close > SMA(200), close < SMA(5), RSI(2) < 10 (Wilder, EWM alpha 1/2).
- Entry: the next open (first fresh quote after 09:30 ET, ask + $0.01). No fill by 09:40 is recorded as MISSED.
- Exit: the next open after any daily close > SMA(5), counting the entry day's close (bid - $0.01). No stop.
- One position per symbol; 3 slots of $1,000 notional (fractional shares); same-day signals in the universe order; exits at an open free their slot before that open's entries.

| Window | Trades | Win | Mean per trade, 2x costs | 90% CI | PF | 3 x $1k portfolio |
|---|---|---|---|---|---|---|
| BACKTEST research 1997-2021 | 1,491 | 69% | +0.381% | +0.25 to +0.51% | 1.77 | Sharpe 0.72, max DD -5% |
| BACKTEST sealed 2022-2025 (out-of-sample, run once; corrected 2026-11-10*) | 270 | 68% | +0.38% | +0.11 to +0.64% | 1.74 | CAGR 8.8%, Sharpe 0.71, max DD -7% |

\* CRSP switched data formats in 2025, and the two formats adjust for splits differently, so a 2025 split looked like a -50% drop (XLE in this universe). The fix rescales the older data at the junction; rules and verdict are unchanged. The first run showed 267 trades, PF 1.72, Sharpe 0.69.

**Trials.** T6 is 2 of the 19 WRDS trials run so far (rows 51-69) (TradingVault `Ledger/variants-tried.md`). The rule itself is the published Connors & Alvarez (2008) family plus the desk's frozen F1 entry filter; the 10-ETF universe was fixed before testing.

**Risk book `swing`** (`v4risk.py` risk4, isolated like `sprint`): at most 10 open (the strategy's 3 slots bind first), the v4 kill switch and pauses, and the approved risk framework's daily stop: no new entries after -$90 today. For a multi-day book, "today" is realized on positions closed today plus open marks, each measured from the position's previous-session mark. Exits are never blocked. Each position's `risk_usd` is a 3-sigma one-day move on its notional (20-day sigma).

**Deviations from the backtest.** Schwab daily bars instead of CRSP; the first fresh quote after 09:30 instead of the official opening print; a fixed $1,000 per slot instead of min($1,000, cash); dividends are not credited to paper P/L; the $90 daily stop can block an entry the backtest would take (every block is recorded).

**What the forward test measures.** Fill cost vs the backtest's $0.02 per share per side, missed opens, and after 40 trades the same metrics as every ledger plus the mean % per trade next to the backtest's +0.38%. Promotion needs CLAUDE.md step 5. Live sizing for real money (risk framework: a 3-sigma day on the whole sleeve <= 1.5% of equity, the drawdown throttle and the kill rules) is set at promotion, not here.

## 9. SPY noise band in shares: `nbs_spy_ls` and `nbs_spy_long` (forward test, intraday)

Added 2026-11-10 after Nick said yes to a paper forward test of T12. **Not promoted.** Intraday, flat at the close, in its own isolated `trend` risk book. The `noise` reference ledger (options) is unchanged.

**Labels.**
- Forward results: **PAPER (simulated fills)** on live Schwab bars and quotes.
- Backtest numbers: **BACKTEST** on WRDS TAQ tick data, run on Nick's computer. The notes are in Nick's TradingVault (`Research/2026-11-10-t12-prereg`, `-t12-result`, `-t12-sealed-result`).

**Rules (frozen as T12; nothing tuned).**
- **Checks:** at 10:00, 10:30, ..., 15:30 ET.
- **Signal price:** the close of the finished 1-minute bar ending at the check.
- **Band:** sigma(t) = the average over the prior 14 full sessions of |close(t) / open - 1|.
  - Upper = max(open, prior close) x (1 + sigma).
  - Lower = min(open, prior close) x (1 - sigma).
  - The prior close is reduced by the dividend on ex-dividend days.
- **At each check, in this order:**
  1. A long exits below max(upper, session VWAP); a short exits above min(lower, VWAP).
  2. Then, if flat: above upper -> buy; below lower -> short (`nbs_spy_ls` only).
- **Flat at 15:59.**
- **Fills:**
  - The first fresh quote after the check: buy at the ask, sell at the bid, + $0.0035/share per side. That is the backtest's cost model (execution model `nbspy1`). The desk's generic shares model would add $0.01 per side, about the size of the whole edge.
  - Entries without a fresh quote within 180 s are MISSED. Exits are never dropped.
- **Missed checks:** a check whose bar isn't available within 120 s, or that passed while the desk was down, is recorded as NO DATA, with no catch-up trading. Early-close days are skipped, as in the backtest.
- **Size:** $3,000 notional per ledger (1x Nick's account), fractional shares.

| Window | T12a long/short, per day after costs | T12b long only, per day after costs |
|---|---|---|
| BACKTEST research 2003-2021 | +1.76 bp (CI +0.78 to +2.80), Sharpe 0.60 | +0.98 bp (CI +0.39 to +1.56), Sharpe 0.55 |
| BACKTEST sealed 2022-2025 (run once) | +2.18 bp (CI +0.40 to +4.14), Sharpe 0.80 | +1.10 bp (CI -0.01 to +2.29), Sharpe 0.62 |

**Read with care.**
- The edge comes from volatile years (2008, 2022-23). 2012-2021 and 2024-2025 were about flat.
- Deflated Sharpe probability: 0.75 / 0.68 at 21 trials.
- Paired with `etf10_rsi2` (correlation about 0), the equal-risk desk blend is 0.96 (research) and 1.04 (sealed).

**Risk book `trend`** (`v4risk.py` risk5, isolated): at most 2 open (one per ledger), the v4 kill switch and pauses, and the risk framework's -$90 daily stop on new entries. Exits are never blocked. A leftover position from an earlier session closes at the next valid quote (a day ledger).

**Practical.** For a $3k live account, the pattern-day-trader rule caps margin accounts under $25k at 3 day trades per 5 days. The long-only version fits a cash account; long/short would need puts or more capital. This is decided at promotion, not here.

**Deviations from the backtest.** 1-minute bar closes instead of the NBBO mid at the second; bar VWAP instead of trade VWAP; the flat uses the first quote after 15:59:00.
