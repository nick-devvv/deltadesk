# DeltaDesk v3.4.2: overview, every result, open problems

As of Friday, Oct 30, 2026 (after the close). This file holds what the current version does, every backtest, study and live result so far, the open problems, the rules any fix must keep, and the complete source of every file in `deltadesk-v3.4.2.zip` (sha256 `44adf4542054aa19702a5304a1ef91516810c2aad35661206ca8e28f140f9c76`), plus the earlier backtest reports.

**What's not inline:**
- the minified third-party chart library (`vendor/lightweight-charts-5.2.1.js`, Apache-2.0, 198 KB), which is listed only;
- the two raw bar files, which are on Nick's Mac in `Downloads/nicks-desk/` and on Chart's computer in `~/desk/reports/`:
  - `backtest_bars_2026-09-22_2026-10-29_schwab.csv` (4.5 MB, SPY/QQQ 1m);
  - `backtest_inplay_bars_2026-09-22_2026-10-29.csv` (97 MB, ~125 stocks 1m).

**How to read it:** Parts 1–4 are the explanation and the evidence (about 45 KB, ~11k tokens). This is Parts 1–4 of the all-in-one file. The source is the repository itself; section 4.4 maps it.

## Contents
1. The trader, the rules that never change, and how the system is built
2. What every part does today (v3.4.2)
3. Every result so far
4. Open problems, known limits, how to propose fixes, and a map of the code
5. Full source (every file, in a fixed order)

---

# 1. The trader, the rules that never change, the architecture

## 1.1 Who it's for
Nick trades options **by hand in Robinhood**: mostly 0DTE SPY/QQQ calls and puts, plus liquid single stocks and ETFs when they have a better setup, usually 1–2 contracts. DeltaDesk is his command deck:
- deterministic Python code computes plans, monitors, alerts and paper-trades on live Schwab market data;
- an AI coach called **Chart** (a Grok agent on its own computer, `~/desk`) explains the desk's numbers in plain words;
- real money is never touched by the software.

## 1.2 Non-negotiables (a fix that breaks one of these is rejected)
- **No automated real-money execution, ever.** No code path sends an order:
  - `broker.submit()` is a stub that refuses;
  - the Schwab client refuses `/trader` paths except `GET /trader/v1/userPreference` (the streaming address);
  - the Schwab app's order limit is 0;
  - Robinhood is never connected.

  Only Nick places real trades.
- **Paper only for every automated strategy.** Simulated fills on live Schwab quotes.
- **20% maximum planned loss on the option premium** per trade, costs included. It's an alert/exit line, not a guaranteed cap. Never propose wider stops; no new dollar caps (Nick's choice: risk control = the 20% line + losing-streak stops).
- **Finished candles only.** Every decision uses bars that have closed; nothing reads a forming bar or future data.
- **No chasing.** The entry gate (`entrygate.py`) refuses entries past the latest acceptable price. Never loosen it to get more trades.
- **Discipline** (main paper): max 2 contracts, 2 open positions, 4 ideas a day. Two losses in a row means A setups only plus a 10-minute cooldown; three in a row means STOP FOR TODAY.
- **Session:**
  - No trades 09:30–09:45 (the opening range forms).
  - Entries 09:45–15:15.
  - All out 15:25 ET.
  - Early-close days: last entry 12:30, all out 12:50.
- **Display:** times show in Pacific by default, with ET available.
- **Versioning:** the frozen main paper policy `2026-10-29.v3` is never edited in place. Every change is a new labeled version in its own ledger.
- **Money:** nothing paid gets added (Nick: "i dont want to pay for anything"). The optional paid xAI search stays off.
- **Layout:** the page layout stays as Nick likes it. New features go in the Markets tab or a new box.
- **Secrets:** they live only on Chart's computer (`schwab.env`, `webhook.env`, `DESK_TOKEN.txt`). The public GitHub repo (`nick-devvv/deltadesk`) never contains secrets, the journal database, tokens, the desk link or personal email.

## 1.3 Architecture
```
Browser (single page, index.html; Lightweight Charts fed by the server)
   |  polls /api/state ~2 s, the chart tail ~2 s; Markets tab polls its boxes
server.py  (Python ThreadingHTTPServer on 127.0.0.1:8765, token-protected; exposed through a Cloudflare quick tunnel)
   |-- engine.py         the minute loop: snapshots per finished bar, plans, paper scans per ledger, watches, alerts
   |-- marketdata.py     one pipeline: Schwab stream (schwab_stream.py) or REST (schwab.py), freshness labels, gaps
   |-- strategy.py       v3 levels, regime, setup detectors (ORB break/retest, failed break, PDH/PDL retest,
   |                     VWAP reclaim, VWAP+MACD), qualification, grade
   |-- indicators.py     VWAP, EMA, MACD, Wilder ATR/ADX, time-of-day RVOL, chop measures, volume profile
   |-- optionmath.py     contract pick, structural stop inside the 20% ceiling, T1, 2:1 checks, sizing
   |-- exits.py          v3 exit state machine (and guidance on Nick's own trades)
   |-- entrygate.py      anti-chasing gate (gate2): zone bounds, latest entry, missed / too extended / invalidated
   |-- paper.py          simulated fills: exec1 (legacy ledgers), exec2 (strict ledgers)
   |-- scanner.py        9:35 stocks-in-play ranking, contract scoring, in-play ledger
   |-- scanner_setups.py the setups board: ~127 symbols, ORB 5/15/30, PM/PD levels, VWAP, momentum, flags, rank
   |-- autopilot.py      board ledger, earnings ledgers
   |-- noiseband.py      noise-band momentum ledger (SPY/QQQ)
   |-- policy_old.py     the frozen pre-Oct-29 rules, as a comparison ledger
   |-- catalysts.py / earnings.py   source-labeled news (SEC EDGAR, Chart's X scan), earnings phases
   |-- strategy_registry.py / strategy_router.py   evidence status of every strategy; routing (nothing qualified)
   |-- lab.py            v3.4 strategy lab: every strategy on every stock, signal tape, lab ledgers, report
   |-- contract_lab.py   v3.4.2: 12 option contracts followed per live signal
   |-- backtest.py / replay.py / diagnostics.py / evaluation.py / research.py / walk_forward.py / matched_benchmarks.py
   `-- kronos_shadow.py  separate process: Kronos-mini forecast test on SPY/QQQ (shadow only)
Chart (Grok) <- webhook with compact context; routines: desk chat, 20-min news scan, 30-min X scan, 4:20 PM review
```
- **Storage:** SQLite `journal/desk.db`, which holds positions, orders, events, candidates, ideas, gate setups, catalysts, earnings, router decisions, experiment attempts, the lab tape and lab contracts. The bar archive is in `journal/bars/<day>/<ticker>.csv.gz`.
- **Data:** Schwab market data only (1m bars, quotes, option chains with greeks). There's no historical option-quote data, so every option backtest uses **modeled** prices. Only forward paper and the contract lab use real option quotes.

---

# 2. What every part does today (v3.4.2)

## 2.1 Main paper (frozen policy `2026-10-29.v3`, SPY/QQQ)
- **Setups** (strategy.py), decided on finished 5m bars (2m for VWAP+MACD):
  - ORB break and ORB retest (opening range 09:30–09:45);
  - failed break;
  - PDH/PDL retest;
  - VWAP reclaim;
  - VWAP+MACD as ONE strategy: a 2m MACD cross with the close beyond VWAP arms it; it enters on a VWAP retest plus a confirming close; it enters early on the cross only in a clearly strong trend; it cancels on a close back through VWAP or a MACD cross back.
- **Shared mechanics:**
  - Level tolerance is max(3 ticks, 0.15 × ATR14 of the decision bars).
  - Calls and puts on the same bar means skip. One idea = one trade.
- **Regime:** ADX ≥ 25 and efficiency ≥ 0.4 counts as a trend; ADX ≤ 18 or efficiency ≤ 0.25 as chop. After 14:00 the structure must be cleaner.
- **Plan:**
  - The stop is structural, just beyond the level that disproves the setup, judged on a finished 1m close, with a hard 20% premium ceiling (costs included). If the structure can't fit inside 20%, skip or pick another contract.
  - T1 is the next opposing level. It needs at least 2:1 on the stock move AND on the modeled option dollars after spread, fees and decay.
- **Contract** (SPY/QQQ): **0DTE, delta 0.40–0.55 (aim 0.45), premium $0.10–$3.00, spread ≤ 10%.**
- **Size:** A = 2 contracts, B = 1, C = no paper trade.
- **Exits** (exits.py), in order:
  1. all out;
  2. the premium stop (20%, or the raised breakeven/lock);
  3. the structure stop;
  4. momentum or stall exits (only when green), T1 rejection, or the if-flat timer for non-green trades;
  5. at T1, sell 1 of 2 and run the rest only on a clean break, or sell 1 of 1;
  6. breakeven at +10%; lock +10% after +25%.
- **Limits:** 4 ideas a day; the streak rules from 1.2.

## 2.2 The other paper ledgers (all simulated, all kept apart)
| Ledger | What | Fills |
|---|---|---|
| `research` | v3 setups with no daily limits | exec1 |
| `exit31` | the research entries with exits that let winners run (v3.1) | exec1 |
| `old` | the frozen pre-Oct-29 rules (20/12/10% stops, if-flat, BE/T1/trail) | exec1 |
| `noise` | noise-band momentum on SPY/QQQ (Zarattini/Aziz/Barbon). Checks at :00/:30 from 10:00 to 15:00; band = max/min(open, prev close) × (1 ± σ14); stop max(band, VWAP) for longs (min for shorts), checked at the half-hour marks; delta 0.55–0.75 | exec1 |
| `inplay` | 5-minute ORB on the 9:35 stocks in play (price ≥ $20, avg vol ≥ 1M, ATR ≥ $0.50, RVOL ≥ 1); stop 0.1 ATR; contracts delta 0.50–0.70, ≤ 10 DTE, spread ≤ 5% | exec1 |
| `gated` | every research-eligible candidate, admitted independently only when gate2 says ENTRY CONDITIONS MET | exec2 |
| `board` | qualifying setups-board rows on stocks/ETFs (10:00–14:30, score ≥ 4), through the gate, 1 contract; the X read is recorded, never a trigger | exec2 |
| `earn_post` / `earn_pre` | post-release confirmation setups / an ATM straddle held through the report (research) | exec2 / exec1 |
| `lab_*` (15) | the strategy lab, one ledger per strategy family (2.6) | exec2 |
| `spec_*` | router specialists. **None exist**: nothing is PAPER QUALIFIED | exec2 |

- **exec1** (legacy): fill = ask + max($0.01, half the spread); exit = bid − the same.
- **exec2** (strict):
  - fill = ask + $0.01 and must be ≤ the limit; exit = bid − $0.01; $0.02 fees per side;
  - the 20% line is recomputed from the actual fill (infeasible means rejected);
  - zero size or a non-100 multiplier means rejected;
  - latency of signal + 1 s is enforced;
  - no fills outside options hours (Cboe 9:30–16:00 ET; designated ETFs to 16:15).

## 2.3 Entry gate (entrygate.py, gate2 `2026-10-30.v3.3-gate2`)
- Each setup is stored once: trigger, entry zone (trigger to trigger ± 0.6 × ATR5), invalidation, target, the latest acceptable entry (the tighter of the zone edge and the price where remaining R/R after costs = 2), a 10-minute window after confirmation, and expiry after 60 minutes unconfirmed.
- **States:** WATCHING, CONFIRMATION NEEDED, ENTRY CONDITIONS MET, TOO EXTENDED, WAIT FOR RETEST, INVALIDATED, NO TRADE.
- **Both zone bounds:** back below the trigger is WAIT FOR RETEST, and a retest must form its own new setup.
- **Fails closed** when freshness is unknown or the stock spread is over 0.15% or unknown.
- **Scopes:** setup keys are scoped per caller/ledger (`G2-{scope}-...`), so experiments never share state.
- Nothing can override it: not a score, not a headline, not Chart.

## 2.4 Setups board and scanner
- **Setups board** (scanner_setups.py):
  - **Coverage:** ~127 symbols (the 125-name universe, SPY/QQQ, the watchlist, the stocks in play). Quotes every 60 s; 1m bars for 20 symbols a minute, hot names first, so a full pass over quiet names takes about 6 minutes.
  - **Rules:**
    - ORB 5/15/30 states: approaching, breaking, closed beyond, retest holding, failed, and reversal confirmed (a close through the range midpoint on the reversal side of VWAP);
    - pre-market and prior-day high/low breaks;
    - VWAP reclaim, rejection, and sustained above/below;
    - relative strength vs SPY;
    - momentum continuation and pullback in a trend;
    - movers and unusual volume (lists, not entries).
  - **Flags:** illiquid, wide spread, low-volume move, extended, stale.
  - **The rank score** is a sort order, not a probability.
- **Scanner** (scanner.py): the 9:35 stocks-in-play ranking by opening volume vs normal, then contract-by-contract option scoring (spread, quote age, volume, OI, delta, decay over the hold, no expiry after earnings).

## 2.5 News, X and earnings
- **Labels** (catalysts.py), set from the links actually retrieved:
  - **confirmed**: SEC filing, agency, press wire, company site;
  - **attributed**: a named outlet;
  - **unverified**: posts only, which can never trigger anything;
  - **opinion**.
- **Sources:**
  - **SEC EDGAR:** free, needs `SEC_USER_AGENT`.
  - **Chart's 20-minute news scan.**
  - **Chart's 30-minute X scan** (free, through Grok's own X access; `GET /api/x/targets` picks up to 12 names, earnings first). It posts trader / consumer / fundamentals sentiment kept separate, with sample counts.
- **Earnings** (earnings.py): phases PRE / RELEASE / CALL / NEXT SESSION; results and call statements are stored only with sources; straddle move proxy.

## 2.6 Strategy lab (lab.py, v3.4, `2026-10-30.v3.4-lab1`)
**Signal tape:**
- **Coverage:** every symbol on the board; every newly finished 1m bar processed in time order, so a signal sees only bars up to its own bar (tested by changing later bars).
- **15 strategy families:**
  - **from the setups board:** ORB break, ORB retest, failed ORB with reversal confirmed, PM/PD level break, level retest, VWAP reclaim, VWAP rejection, momentum continuation, pullback;
  - **v3 rules on every stock:** one family for ORB break/retest, failed break, PDH/PDL retest and VWAP reclaim, and a separate one for VWAP+MACD (namespaced state, no events);
  - **ORB15 first break and ORB15 first retest** (the research.py definitions);
  - **the MACD video rule:** a 5m MACD(12,26,9) cross below zero with the close above the 200 EMA → long, mirrored for shorts; the stop is the 200 EMA frozen at the signal; 2R; it needs 1000 finished 5m bars of history;
  - **the noise band** at the half-hour checks, on every stock with two weeks of history.
- **Board signals** come as episodes: one signal per setup/side/state until it disappears for 10 minutes.

**Conditions saved per signal** (known at that moment):
- the time window (before 09:45 / 09:45–11:30 / 11:30–14:00 / 14:00–15:15 / after);
- RVOL bucket; the 5m trend (ADX ≥ 25 and efficiency ≥ 0.4 with DI with/against); 2m MACD histogram with/against; 5m 200 EMA side;
- VWAP distance in ATR; SPY since the open with/against; the opening gap;
- price bucket; liquidity bucket; stock group (`config/sectors.json`); ETF flag; earnings phase;
- **the X read:** the newest catalyst *first detected before* the signal (24 h), with trader lean agrees / disagrees / mixed / none, its label, and attention rising;
- for board rows also: score, qualifies, extended;
- the raw numbers.

**Outcome after 15:31** (signals decided 09:45–15:15):
- **Shared yardstick:** entry at the next bar's open; stop just past the invalidation (0.05 × daily ATR) on any touch; 2R target; flat 15:25; $0.04/share costs; the stop counted first on an ambiguous bar. Plus the R at 5, 15 and 30 minutes.
- **Own exits (v3.4.2):** a finished 1m close past the invalidation stops it and a finished close past 2R takes it, both filled at the next bar's open (gaps included). The noise band only exits at its half-hour checks, with no target.
- **Matched random entries** (20 per signal, fixed seed): same stock, day, side, window 09:45–15:15, stop distance, target and costs, under the same exit rules.

**Lab paper ledgers:**
- One `lab_*` ledger per family; only signals seen within 150 s of their bar.
- Each goes through the gate, scoped to the ledger: the target is the 2:1 point after costs from the signal close + 1¢, so no entry is worse than the signal price.
- Then the contract check (scanner scoring, ≤ 10 DTE), exec2, 1 contract.
- **Exits:** all out 15:25, the 20% line, a finished close past the invalidation, or a finished close past the target. The noise ledger uses its half-hour rule.
- **Caps:** 2 open per ledger, 6 ideas per ledger a day, 20 open in total, 8 attempts a minute.
- SPY/QQQ keep their own ledgers for the v3 rules and the noise band.
- **Separate from Nick:** pause and kill switch cover the lab; lab events stay out of the trade feed.

**What works where** (`/api/lab/report`): split by strategy, setup, stock, strategy × stock, strategy × stock group, or strategy × condition. Each row shows:
- signals, days, won %, avg R and random avg R;
- the **edge over random** with a 95% interval resampled by whole days;
- the earlier half vs the later half of the dates.

A row is **"too few" until 30 signals AND 10 trading days**. When a stock has too few, the hierarchy shows its group and all stocks.

**Bar archive:** each morning the history pull (30 calls a minute, ~30 days) back-fills missing days, and after 16:06 it writes today's bars (pre-market included).

**Load:** about 40 ms per symbol per minute (~5 s/minute for 127 symbols). The whole lab step is capped at 4 s (v3.4.1); catch-up after a restart continues over the following steps.

## 2.7 Contract lab (contract_lab.py, v3.4.2, `2026-10-30.v3.4.2-contracts1`)
- **What it follows:** for every live lab signal 09:45–15:15, up to **12 contracts** from the real Schwab chain: expiry **0DTE / 1–2 days / 3–5 days / 6–10 days** × delta **0.35 / 0.45 / 0.60**.
  - Each is the nearest expiry in its bucket, with the strike closest to the delta (within 0.10) and a two-sided quote ≤ 20 s old.
  - When none fits, the reason is recorded.
- **How:** one batched quote request per step until 15:26. It records:
  - the 20% line touch (the same formula as exec2 from the actual entry);
  - the best/worst bid;
  - one sample a minute.
- **Nothing is filled.**
- **Scoring** at the moment the signal's stock trade ended (shared yardstick):
  - entry = the ask + $0.01, exit = the bid − $0.01, $0.02 fees per side;
  - "with the 20% line" exits at the line if the bid touched it first; "held" exits at the stock exit.
- **Report** `/api/lab/contracts` shows, by expiry × delta (overall or per strategy): won with the line, average $ and % of premium with the line and held, % of times the line hit first, and the stock R of the same signals.
- **Budget:** 4 new signals a minute; at most 16 followed at once; no same stock and side twice within 10 minutes.

## 2.8 Evidence, registry and router
- `config/specialists.json` (registry2) has 33 experiments, each with its spec (sha256-locked at first sight: an edited spec shows SPEC CHANGED and drops to research only), evidence and status:
  - DRAFT, RESEARCH ONLY, PAPER QUALIFIED, PAUSED or RETIRED;
  - **nothing is PAPER QUALIFIED and nothing is RETIRED** (Nick, Oct 30: keep everything running, no verdict yet).
- **Plans:** every plan carries an evidence badge (Research only / Your idea). A research-only setup reads RESEARCH SETUP, never ENTER. Setup alerts only ping for PAPER QUALIFIED families, which today means none.
- **Router** (`strategy_router.py`): admission → SHADOW / REJECT / ADMIT with shared limits; every route logged.
- **Research tools:**
  - walk-forward folds (`walk_forward.py`);
  - matched random controls, session-paired differences and Holm adjustment (`matched_benchmarks.py`);
  - the ORB15 signal study (`research.py`).

## 2.9 Chart, operations, Kronos
- **Chart:** reads the desk's numbers through endpoints (`grok/TOOL_CONTRACTS.md`) and its prompts (`grok/*.md`).
  - It never trades, clicks order buttons, enters passwords or keys, or changes rules.
  - Routines: desk chat webhook, 20-minute news scan, 30-minute X and earnings scan, 4:20 PM daily review, 9 AM morning routine.
- **Hosting:** a Cloudflare quick tunnel, whose address changes when cloudflared restarts. `watchdog.sh` restarts the server; Chart records the current link in `tunnel_url.txt` on its computer.
- **Kronos** (`kronos_shadow.py`): Kronos-mini forecasts SPY/QQQ 5/10/15 minutes ahead at each finished 5m bar, scored against no-change and momentum baselines. Shadow only.
  - v3.4.1: one copy at most (a file lock), it exits when its server dies, and the server stops orphaned copies on start.
  - Verdict on Oct 30: "collecting: 3 of 20 trading days scored".

---

# 3. Every result so far

Read these with their sample sizes. Option results in backtests are MODELED: there is no historical option-quote data. Sep 22 – Oct 29 was used to design v3, so it is in-sample, and patterns there are hypotheses.

## 3.1 Backtest, Sep 22 – Oct 29 2026 (28 trading days, SPY/QQQ, modeled options)
| Ledger / test | Trades | Won | Expectancy / trade | Notes |
|---|---|---|---|---|
| Noise band | 61 | 23% | **+$22.48** | PF 1.67, max DD $693; a few all-day winners carry it; in-sample |
| Old rules (20/12/10%) | 106 | 31% | +$8.27 | PF 1.43 |
| v3 setups, opposite direction | 433 | 34% | −$4.43 | |
| Coin flip, same times and exits (20 seeds) | 433 | 32% | −$6.73 | |
| v3 setups | 433 | 30% | −$9.00 | PF 0.44: **worse than random** |
| Stocks-in-play ORB5 with options | 425 | 15% | −$19.49 | the stock alone −0.03R (break-even): options turned it into a loss |
| Main paper / research / exit31 in the engine replay | 2 each | 0% | −$19.04 | tiny |

From the diagnostics (full text in 3.9):
- **No exit variant** (bracket, hold, VWAP trail, v3.1 runner) made the v3 entries positive.
- **By setup:**
  - ORB break, failed break and VWAP reclaim were clearly negative;
  - PDL retest puts +$5.70 (10 trades) and PDH retest calls +$8.65 (3 trades) were tiny samples;
  - VWAP+MACD calls −$3.22 (42 trades), puts −$5.74 (52 trades).
- **Against the day:** puts on up days −$17.71 and calls on down days −$11.04 (judged at the close, which is look-ahead).
- **Old-rules exits:** breakeven stops +$690 over 39 trades; stops −$1,497 over 34. 15 trades had the stock right but the option lost.
- **Noise band exits:** premium stops −$1,970 over 45 trades; all-out winners +$3,248 over 10.

## 3.2 Outside audit, rounds 2–3 (their data files weren't supplied, so these are not reproduced here)
- **Stocks-in-play source scanner:** 286 trades, −$12.42/trade modeled; 185 were decided before 09:45 (the bt1 look-ahead defect, fixed in bt2). The later block, Oct 16–29: 47 trades, 12.8% won, −$42.54/trade.
- **Filters (later block):**
  - RVOL ≥ 2: 20 trades, 15% won, −$42.56;
  - SPY alignment: 27 trades, 11.1%, −$44.47;
  - ADX ≥ 25 + efficiency ≥ 0.4 trend (selected in development): 19 trades, 10.5%, −$53.49;
  - morning only: 34 trades, 11.8%, −$46.13;
  - midday: 10 trades, 20%, −$30.11;
  - afternoon: 3 trades.
- **MACD video, 5m adaptation:**
  - 1.5R: 90 outcomes, 26.7% positive, −0.384R;
  - 2R: 90, 24.4%, −0.416R; the later dates 46, 34.8%, −0.294R;
  - with a prior-pivot retest filter: 12, 25%, −0.936R.
- **Earlier ORB15 definitions:** breakout 75 later signals, 45.3% positive at 15 min; retest 60 signals, 36.7%; both negative after costs.

## 3.3 ORB15 signal study (`research.py`, run on Chart's computer Oct 30, stock moves in R after $0.04/share, no options)
34 sessions; 3,554 signals. Skipped ticker-days: 1,875 for insufficient warmup, 314 illiquid or cheap, 111 with no completed break.

| Variant | Block | Signals | Won | Avg R | Random avg R (won) | Paired diff vs random | 95% CI | p |
|---|---|---|---|---|---|---|---|---|
| BASE (first break) | development (24 sessions) | 918 | 32.6% | −0.227 | −0.132 (37.5%) | −0.036 | [−0.085, −0.001] | 0.98 |
| BASE | later (10 sessions) | 1,029 | 32.8% | −0.222 | −0.175 (35.8%) | −0.048 | [−0.183, +0.086] | 0.76 |
| RETEST (first retest) | development | 761 | 31.0% | −0.256 | −0.115 (37.9%) | −0.054 | [−0.116, −0.002] | 0.98 |
| RETEST | later | 846 | 33.0% | −0.201 | −0.153 (36.1%) | −0.048 | [−0.223, +0.165] | 0.69 |

- Holm-adjusted p (later): 1.0 / 1.0.
- Both did worse than random entries. In development the gap is statistically clear; in the later block there are too few sessions to tell.
- **Status: still DRAFT** at Nick's request; both now run live every day in the lab.

## 3.4 First forward day: Oct 30 2026 (one session; read nothing into it)
- **The market:** choppy and news-driven (Fed President Daly spoke midday). Puts paid in most ledgers.
- **Main paper:** 0 trades; it skipped all 13 SPY/QQQ setups (no clear target ×8, choppy range ×6, R/R under 2:1; one setup was 2.7 ATR past VWAP during the Fed speech).
- **Old rules:** 4 puts (SPY 760P, SPY 759P, QQQ 695P ×2), all on breakeven stops, +$51.84.
- **Noise band:** SPY 760P **+$401**, QQQ 692P **+$136**, both held to the 15:25 exit (the stock moved about 0.5%).
- **Stocks in play:** 2 for 7, −$210; avg win $31, avg loss $55; 4 premium stops cost $218.
- **v3.1 exits:** 0 trades.
- **Strategy lab, first day** (shared yardstick, one session):

  | Family | Signals | Won | Avg R | Random avg R | Edge |
  |---|---|---|---|---|---|
  | VWAP rejection | 171 | 46.2% | +0.233 | +0.255 | −0.021 |
  | v3 rules on stocks | 332 | 43.4% | +0.072 | +0.104 | −0.032 |
  | Noise band (stocks) | 67 | | | | −0.42 (worst, but the shared yardstick is unfair to it; see 4.1) |
  | MACD video | 17 | | | | +0.15 (too few) |

  VWAP rejection's +0.23R "looked good", but random same-side entries made +0.26R: the down day, not the setup.
- **Data quality:** the desk crashed repeatedly that afternoon (the Kronos memory pile-up, fixed in v3.4.1) and bars went stale twice. Lab paper trades that day are incomplete; the tape caught up.

## 3.5 Option contract math: why 0DTE may be the bottleneck (estimates, not measurements)
Black-Scholes at 10:00 ET, SPY at 760, IV 15%, a typical 5m bar = 0.10% of the price. How far the stock must move against you before the **20% line** hits:

| Contract | Premium | 20% = $ | SPY move | In 5m bars | Same after 30 min | Time decay / hour |
|---|---|---|---|---|---|---|
| **0DTE δ0.45 (current SPY/QQQ pick)** | 1.01 | 20 | 0.48 (0.06%) | **0.6** | 0.5 | **10.3%** |
| 0DTE δ0.35 | 0.70 | 14 | 0.43 | 0.6 | 0.4 | 13.8% |
| 0DTE δ0.60 | 1.60 | 32 | 0.57 | 0.7 | 0.6 | 6.4% |
| 1DTE δ0.45 | 2.25 | 45 | 1.08 | 1.4 | 1.3 | 2.0% |
| 3DTE δ0.45 | 3.62 | 72 | 1.73 | 2.3 | 2.2 | 0.8% |
| 7DTE δ0.45 | 5.38 | 108 | 2.57 | 3.4 | 3.4 | 0.4% |

A big tech stock at IV 45% (5m bar = 0.3% of price) gives the same pattern: 0DTE δ0.45 needs 0.6 bars, 3DTE 2.2 bars, 7DTE 3.3 bars.

- **Reading:** with 0DTE, the 20% line hits on ordinary noise before the chart's structure stop is tested, so a signal that works on the stock can still lose on the option. That matches 3.1 (in-play stock ≈ 0R but options −$19.49/trade) and Oct 30 (in-play losses were all premium stops).
- **The trade-off:** a longer expiry under the same 20% rule risks more dollars per contract.
- **Status:** the contract lab (2.7) now measures this on real quotes. First results arrive Mon Nov 2; read nothing before ~10 days.

## 3.6 Outside research (summaries; see docs/RESEARCH_NOTES.md in Part 5)
- **Noise band** (Zarattini, Aziz, Barbon 2024): SPY shares 2007–2024, Sharpe ~1.33, net of sub-cent costs. Options add spread and decay.
- **Stocks-in-play ORB** (Zarattini, Barbon, Aziz): shares 2016–2023 with strong reported results. An independent replication of the index version found nothing after realistic costs.
- **Gao et al.** last-half-hour momentum: outside the 15:25 all-out, so not used.
- **0DTE retail buyers** lose in aggregate (Beckmeyer, Branger, Gayda 2023; Bloomberg: "Day Traders Lose $358,000 Per Day Gambling on Zero-Day Options").
- **SEC staff (DERA):** customers using limit orders pay small trading costs; losses come mostly from paying up for crowded contracts, not the spread.
- **de Silva, Smith, So** ("Losing is Optional"): around earnings, single-stock option spreads average ~20% of the price; retail loses 5–14% around announcements.
- **Barber et al. (Taiwan):** fewer than 20% of day traders profit after costs.

## 3.7 Defects found and fixed (so earlier numbers are read correctly)
- **v3.3 (from the outside audit), each fixed as a new version with the old one kept:**
  - **A:** the gate checked only one zone bound, so a confirmed call could enter after falling back below the trigger. gate2 checks both and fails closed.
  - **B:** the "gated" ledger mirrored another ledger's fills; it now decides every candidate itself.
  - **C:** 2m MACD was forward-filled from the bar's open time (look-ahead) in diagnostics. diag2 uses the bar's close.
  - **D:** theta units were inconsistent (per minute ×60 vs per calendar day). replay2 uses per calendar day everywhere.
  - **E:** the stocks backtest filled at the signal candle's close at its open timestamp, had ideal gap stops, and decided before 09:45. bt2 decides at the close, fills at the next open, gaps fill at the open, and starts at 09:45.
  - **F:** `paper.buy` compared the ask, not the final fill after slippage, with the limit. exec2 checks the final fill and enforces latency.
  - **G:** the indicator cache keyed on the day only; it now keys on a hash of the content.
  - **H:** evaluation used trade-level intervals and mixed versions; eval2 uses session-clustered bootstrap and versioned splits.
- **The 530 chart error:** a Cloudflare quick-tunnel error page (the tunnel restarted with a new address). The page now shows one plain line, keeps the last candles and backs off. Chart now records the current link.
- **v3.4.1:** the Kronos pile-up. Kronos was a child process that outlived server restarts: 38–40 copies × 370 MB filled 16 GB, and the server crash-looped. Fixed with the lock, exit-with-parent and orphan cleanup. The lab step is now capped at 4 s.
- **v3.4.2:**
  - the noise band is scored by its own exits;
  - "too few" now requires 10 days;
  - the old-rules ledger records best/worst moves (its MFE/MAE were always 0).

## 3.8 Live state after the v3.4.2 install (Oct 30, 6:18 PM ET)
- **Install:** 164 tests pass on Chart's computer. The server stayed up 36+ minutes with 1 Kronos copy and no watchdog restarts; the tunnel link is unchanged.
- **Memory:** "used" jumped to 13.4 GB with only ~2.7 GB in visible processes. Under investigation (read-only diagnostics sent to Chart); the desk itself uses ~144 MB and Kronos ~319 MB.
- **Checks:**
  - lab bar archive: 127 files for Oct 30;
  - lab report: rows resolved on Oct 30;
  - the contract lab's first data comes Mon Nov 2.
- **Pending decision:** two lessons wait for Nick's approval on the Review page ("enter only after the 2-minute candle closes", "one position per level").

## 3.9 The earlier backtest and diagnostics reports, verbatim
The reports for Sep 22 – Oct 29 follow (they're also in the earlier all-in-one file). Note that "diagnostics" here predates the v3.3 fixes C/D (MACD availability, theta units). Re-run them with the current `backtest.py` for corrected numbers.

===== FILE: reports/backtest_2026-09-22_2026-10-29.md =====
~~~~~markdown
# Backtest 2026-09-22 to 2026-10-29

28 trading days. Bars `backtest_bars_2026-09-22_2026-10-29_schwab.csv` (sha256 `6f4af16e394f6893...`, kept on Chart's computer). Option prices are MODELED everywhere in this report. In-sample research: forward paper decides.

## Engine ledgers (SPY/QQQ, modeled option quotes)

- paper: 2 trades, 0.0% won, avg win None, avg loss -19.04, expectancy -19.04, PF 0.0, max DD 38.08 (small sample)
- research: 2 trades, 0.0% won, avg win None, avg loss -19.04, expectancy -19.04, PF 0.0, max DD 38.08 (small sample)
- exit31: 2 trades, 0.0% won, avg win None, avg loss -19.04, expectancy -19.04, PF 0.0, max DD 38.08 (small sample)
- noise: 61 trades, 23.0% won, avg win 243.67, avg loss -43.4, expectancy 22.48, PF 1.67, max DD 693.24
- old: 106 trades, 31.1% won, avg win 87.73, avg loss -28.03, expectancy 8.27, PF 1.43, max DD 623.54

Diagnostics: see `diagnostics_2026-09-22_2026-10-29.md` (coin flip, exits, hold tests, halves, up/down days).

## Stocks in play (scanner rules, shares rules + modeled options)

- Stock, in R: 425 trades, 14.8% won, avg win 5.49, avg loss -1.0, expectancy -0.03, PF 0.97, max DD 55.96
- Option (modeled): 425 trades, 14.6% won, avg win 232.73, avg loss -62.74, expectancy -19.49, PF 0.64, max DD 8328.78

~~~~~

===== FILE: reports/diagnostics_2026-09-22_2026-10-29.md =====
~~~~~markdown
# Diagnostics 2026-09-22 to 2026-10-29
433 setups on 28 days. Option results are MODELED (427 setups had no contract quote and use a default delta-0.45 contract). Exits are counterfactual on 1m closes.

1. Signals vs a coin flip (same setups, same times, v3-style exits)
Signals: 433 trades, 29.6% won, avg win 23.49, avg loss -22.94, expectancy -9.0, PF 0.44, max DD 3930.38
Coin flip (20 seeds): win rate 31.5% (sd 1.7), expectancy -6.73
Opposite direction: 433 trades, 33.5% won, avg win 27.64, avg loss -21.09, expectancy -4.43, PF 0.68, max DD 2037.41
Reading: if the coin flip wins about as often as the signals, the low win rate comes from the exits and costs, not the direction.
2. Same entries, different exits
Exits	Option (modeled)	Stock, in R	Exit reasons
v3_approx	433 trades, 29.6% won, avg win 23.49, avg loss -22.94, expectancy -9.0, PF 0.44, max DD 3930.38	433 trades, 15.0% won, avg win 1.07, avg loss -1.09, expectancy -0.04, PF 0.82, max DD 22.75	if-flat 3 min 158, T1 111, if-flat 5 min 67, structure stop 40
bracket	433 trades, 45.3% won, avg win 29.25, avg loss -46.64, expectancy -11.21, PF 0.54, max DD 4881.0	433 trades, 21.7% won, avg win 1.15, avg loss -1.3, expectancy -0.17, PF 0.51, max DD 76.14	T1 224, structure stop 161, all out 15:25 48
hold	433 trades, 26.3% won, avg win 120.94, avg loss -54.78, expectancy -8.27, PF 0.79, max DD 6246.97	433 trades, 22.2% won, avg win 2.43, avg loss -1.28, expectancy -0.2, PF 0.73, max DD 106.04	structure stop 241, all out 15:25 192
vwap_trail	433 trades, 23.1% won, avg win 88.56, avg loss -38.31, expectancy -8.74, PF 0.7, max DD 5006.17	433 trades, 15.2% won, avg win 2.1, avg loss -1.28, expectancy -0.19, PF 0.63, max DD 82.04	structure stop 161, all out 15:25 95, trail 92, breakeven stop 85
v31_approx	433 trades, 32.1% won, avg win 40.17, avg loss -37.67, expectancy -12.16, PF 0.51, max DD 5279.12	433 trades, 19.4% won, avg win 1.34, avg loss -1.28, expectancy -0.19, PF 0.58, max DD 83.13	trail 173, structure stop 136, if-flat 15 min 78, all out 15:25 28
3. Live engine ledgers: what closed the trades
old: BREAKEVEN STOP: 39 (+690), STOP: 34 (-1497), IF FLAT: 28 (-348), ALL OUT 15: 4 (+2072), SETUP INVALIDATED: 1 (-40). Losers closed by if-flat within ~5 min: 23 of 72. Stock moved the right way on 42.5% of trades; stock right but option lost: 15.
paper: STRUCTURE BROKEN: 2 (-38). Losers closed by if-flat within ~5 min: 0 of 2. Stock moved the right way on 0.0% of trades; stock right but option lost: 0.
research: STRUCTURE BROKEN: 2 (-38). Losers closed by if-flat within ~5 min: 0 of 2. Stock moved the right way on 0.0% of trades; stock right but option lost: 0.
exit31: STRUCTURE BROKEN: 2 (-38). Losers closed by if-flat within ~5 min: 0 of 2. Stock moved the right way on 0.0% of trades; stock right but option lost: 0.
noise: PREMIUM STOP: 45 (-1970), ALL OUT 15: 10 (+3248), NOISE STOP at 13: 3 (+29), NOISE STOP at 12: 2 (-70), NOISE STOP at 14: 1 (+135). Losers closed by if-flat within ~5 min: 0 of 47. Stock moved the right way on 23.0% of trades; stock right but option lost: 0.
4. By setup (v3-style exits)
FAILED_BREAK calls: 79 trades, 27.8% won, avg win 34.19, avg loss -21.34, expectancy -5.88, PF 0.62, max DD 572.24
FAILED_BREAK puts: 66 trades, 18.2% won, avg win 18.49, avg loss -22.35, expectancy -14.92, PF 0.18, max DD 984.79
ORB_BREAK calls: 50 trades, 36.0% won, avg win 21.11, avg loss -24.54, expectancy -7.62, PF 0.5, max DD 404.85
ORB_BREAK puts: 51 trades, 19.6% won, avg win 31.02, avg loss -27.5, expectancy -15.49, PF 0.28, max DD 789.92
ORB_RETEST calls: 12 trades, 50.0% won, avg win 27.23, avg loss -35.12, expectancy -3.94, PF 0.78, max DD 90.69 (small sample)
ORB_RETEST puts: 8 trades, 12.5% won, avg win 35.25, avg loss -30.6, expectancy -22.37, PF 0.16, max DD 178.96 (small sample)
PDH_RETEST calls: 3 trades, 66.7% won, avg win 14.21, avg loss -2.48, expectancy 8.65, PF 11.46, max DD 2.48 (small sample)
PDL_RETEST puts: 10 trades, 50.0% won, avg win 29.69, avg loss -18.28, expectancy 5.7, PF 1.62, max DD 55.06 (small sample)
VWAP_MACD calls: 42 trades, 23.8% won, avg win 20.26, avg loss -10.89, expectancy -3.22, PF 0.6, max DD 218.82
VWAP_MACD puts: 52 trades, 36.5% won, avg win 22.8, avg loss -22.17, expectancy -5.74, PF 0.59, max DD 392.57
VWAP_RECLAIM calls: 27 trades, 40.7% won, avg win 14.72, avg loss -20.52, expectancy -6.16, PF 0.49, max DD 166.34 (small sample)
VWAP_RECLAIM puts: 33 trades, 36.4% won, avg win 14.07, avg loss -35.19, expectancy -16.21, PF 0.24, max DD 557.06
5. Split halves (split at 2026-10-12)
v3_approx: first half 243 trades, 30.5% won, avg win 21.64, avg loss -22.38, expectancy -8.79, PF 0.43, max DD 2157.94; second half 190 trades, 28.4% won, avg win 26.02, avg loss -23.64, expectancy -9.28, PF 0.44, max DD 1772.44
hold: first half 243 trades, 25.9% won, avg win 85.75, avg loss -53.81, expectancy -17.41, PF 0.56, max DD 6246.97; second half 190 trades, 26.8% won, avg win 164.4, avg loss -56.04, expectancy 3.42, PF 1.08, max DD 4035.11
VWAP_RECLAIM puts: expectancy 0.29 then -26.94 (n 13 / 20)
ORB_BREAK puts: expectancy -19.09 then -8.88 (n 33 / 18)
FAILED_BREAK puts: expectancy -18.6 then -10.77 (n 35 / 31)
FAILED_BREAK calls: expectancy -8.0 then -2.6 (n 48 / 31)
ORB_BREAK calls: expectancy -5.03 then -10.93 (n 28 / 22)
VWAP_RECLAIM calls: expectancy -2.63 then -9.44 (n 13 / 14)
VWAP_MACD puts: expectancy -7.75 then -4.01 (n 24 / 28)
VWAP_MACD calls: expectancy -5.24 then -0.51 (n 24 / 18)
ORB_RETEST calls: expectancy -2.3 then -12.15 (n 10 / 2)
PDL_RETEST puts: expectancy 14.01 then -27.53 (n 8 / 2)
PDH_RETEST calls: expectancy 8.65 then None (n 3 / 0)
ORB_RETEST puts: expectancy -25.72 then -19.02 (n 4 / 4)
6. Up and down days
Days: {'down': np.int64(28), 'up': np.int64(28)}

down day, calls: 96 trades, 27.1% won, avg win 21.5, avg loss -23.12, expectancy -11.04, PF 0.35, max DD 1096.55
down day, puts: 125 trades, 32.8% won, avg win 24.35, avg loss -24.94, expectancy -8.38, PF 0.49, max DD 1088.92
up day, calls: 117 trades, 36.8% won, avg win 26.27, avg loss -17.2, expectancy -0.93, PF 0.91, max DD 301.35
up day, puts: 95 trades, 18.9% won, avg win 17.75, avg loss -26.0, expectancy -17.71, PF 0.16, max DD 1682.8
Notes
Counterfactual exits run on 1m closes and approximate the live exit rules.
Option P/L is MODELED (delta/gamma/theta + spread + fees); there is no historical option-quote data.
October 28 and the days used to design v3 are in-sample; read every pattern as a hypothesis.

~~~~~

---

# 4. Open problems, limits, how to propose fixes, and a map of the code

## 4.1 Open problems (the best places to improve)
1. **The option layer:**
   - 0DTE plus a 20% premium line may stop most trades on noise (3.5). The contract lab measures this from Nov 2.
   - Candidate fixes to *test*, not adopt: a longer expiry (1–5 DTE) or a higher delta for the same signals, limit-order entries, or choosing the contract so the 20% line sits at or beyond the structure stop (skip the trade if it can't).
2. **Entry edge:** almost every entry family so far is at or below random on the stock move (3.1, 3.3, 3.4). Only the noise band (SPY/QQQ, in-sample) and a few tiny retest samples were positive. Finding conditions where a family beats random is what the lab report is for; it needs 10+ days.
3. **The shared yardstick vs native exits:** compare both views (Exits selector) before judging a strategy.
4. **Late signals:** quiet symbols refresh only every ~6 minutes on the board, so their signals are too late to paper trade (tape only). Raising the board's request budget (`bars_calls_per_min`, default 20, under a desk-wide limit of 100/min) would make more signals live.
5. **Lab v3 detections are raw** (before v3's grade and qualification), so they're broader than main paper's.
6. **Memory on Chart's computer:** unexplained "used" memory (3.8).
7. **Single tunnel:** the quick tunnel's address changes on restart. A stable free option (e.g. Tailscale) is a separate setup.

## 4.2 Known limits
- **Option prices:** modeled in every backtest; real quotes only in forward paper and the contract lab.
- **Data reuse:** Sep–Oct data was used to design v3, so studies on it are diagnostic, not unseen evidence.
- **Coverage:** the lab covers ~127 symbols, not the whole market.
- **Statistics:** with hundreds of lab combinations, some will look good by luck. Rows count only with 30+ signals, 10+ days, an interval above zero, and a positive edge in both halves, and then must keep holding.

## 4.3 Rules for any proposed fix (so results stay honest)
- Keep every non-negotiable in 1.2.
- **No look-ahead:** decisions use only finished bars. Changing later bars must never change earlier outputs; add a test.
- **New versions, never edits in place:** a fix to a strategy becomes a new labeled version in its own ledger (or a new registry experiment with a new id). The frozen main paper (`2026-10-29.v3`) stays.
- **Few rules, few parameters,** each with a reason. Evaluate chronologically (development → later dates, or walk-forward), and compare against matched random entries.
- **Count every cost:** spread, $0.01 slippage, $0.02 fees per side, decay over the hold.
- **Report skipped setups,** so a filter can't look good just by trading less.
- **Judge by expectancy after costs,** with intervals, drawdown and sample size; report the win rate next to it. Never promise profits.
- **Tests:** offline, no network (`python3 -m pytest -q tests/`; Python 3.12/3.13, pandas 2.2 or 3). The current suite: 164 passed, 1 skipped. Add tests for every change.

## 4.4 Map of the code (Part 5 order)
| File | What it is |
|---|---|
| `config/policy.json` | Every threshold: session, contract, risk, discipline, v3 rules, exits, gate, research variants, scanner |
| `config/specialists.json` | The experiment registry (33 experiments, statuses, evidence) |
| `config/sectors.json`, `config/universe.json`, `config/policy_old_2026-10-28.3.json` | Stock groups, the scanner universe, the frozen old rules |
| `strategy.py`, `indicators.py`, `entrygate.py`, `optionmath.py`, `exits.py` | The v3 rules: setups, indicators, gate, contract/stop/target math, exits |
| `paper.py`, `optionhours.py` | Simulated fills (exec1/exec2), options market hours |
| `engine.py`, `commands.py`, `core.py`, `store.py` | The minute loop and ledgers, chat commands, sessions/policy, SQLite |
| `scanner.py`, `scanner_setups.py`, `autopilot.py`, `noiseband.py`, `policy_old.py` | Stocks in play, the setups board, board/earnings ledgers, the noise band, the old rules |
| `lab.py`, `contract_lab.py` | v3.4 strategy lab, v3.4.2 contract lab |
| `strategy_registry.py`, `strategy_router.py`, `research.py`, `walk_forward.py`, `matched_benchmarks.py`, `evaluation.py` | Evidence, routing, studies, statistics |
| `backtest.py`, `replay.py`, `diagnostics.py` | Multi-day backtest, day replay, diagnostics |
| `catalysts.py`, `earnings.py`, `alerts.py`, `watchlist.py`, `altdata.py` | News/X/SEC, earnings, alerts, watchlist, optional alt data |
| `marketdata.py`, `schwab.py`, `schwab_stream.py`, `chartfeed.py`, `chartdata.py`, `broker.py` | Data pipeline, Schwab REST/stream (market data only), chart feed, legacy chart data, the refusing broker stub |
| `server.py`, `index.html` | API and the page |
| `kronos_shadow.py` | The Kronos forecast test |
| `grok/*` | Chart's prompts, endpoints, rules map, knowledge pack, context schema |
| `docs/*`, `GROK_SETUP_AND_HANDOFF.md`, `DESIGN.md`, `README` notes | Reports per version, setup steps, design rules, credits, research notes |
| `tests/*` | The offline test suite and its fakes |
| `desk.py`, `server_legacy.py`, `index_legacy.html` | Legacy v1 code kept for `/legacy` |

## 4.5 Re-running things (on Chart's computer, or anywhere with the bar CSVs)
```
pip install -r requirements.txt
python3 -m pytest -q tests/                      # 164 passed, 1 skipped
python3 backtest.py --from 2026-09-22 --to 2026-10-29 --csv reports/backtest_bars_2026-09-22_2026-10-29_schwab.csv \
        --inplay-csv reports/backtest_inplay_bars_2026-09-22_2026-10-29.csv      # bt2 + diag2 (corrected)
python3 research.py --csv reports/backtest_inplay_bars_2026-09-22_2026-10-29.csv --paths 20   # ORB15 signal study
```
Live endpoints (add `?k=DESK_TOKEN`):
- `/api/lab`
- `/api/lab/report?by=strategy_condition&cond=x_lean&exits=own`
- `/api/lab/contracts`
- `/api/strategies`
- `/api/research`
- `/api/review`

---
