# DeltaDesk v3.1: scanner, research experiments, trade guidance

Main paper rules did not change. They stay v3 (`2026-10-29.v3`), frozen for the forward test that starts Oct 30. Everything new is either guidance for Nick's own trades, or an experiment in its own paper ledger. No code path sends an order anywhere, and real trades are placed by Nick in Robinhood.

## What works now (tested offline, 70 tests passing plus the TA-Lib parity test)

**My trades (any ticker)**
- `IN NVDA 140C 11/07 1 at 3.20` (SPY/QQQ same-day needs no date) tracks that exact contract on live Schwab quotes. Each tick the desk updates its guidance: **HOLD / TIGHTEN STOP / TAKE PROFIT: sell n / EXIT / NO DATA**, with reasons, the chart stop and premium stop, T1 and the profit plan. A change pushes a "My trades" alert. The desk never sells for Nick.
- Plans for any ticker end with **ENTER / WAIT / PASS**. Single stocks use the scanner's option liquidity rules.
- Every trade is labeled **desk setup** or **your idea (discretionary)**. Discretionary trades get levels-based stops and targets from the same Schwab snapshot, and their results stay separate.
- The stop can never be set past the **20% max planned loss**, even with `force`. A wider stop Nick reports is logged as a rule break, and the plan keeps the 20% level. The 20% is described as planned, not guaranteed.

**Market scanner (stocks in play)**
- 08:30: baselines for ~125 liquid optionable stocks (`config/universe.json`, editable): ATR14, 14-day average volume, and the median first-5-minute volume. That's 2 Schwab calls per ticker.
- 09:35:20: Schwab's top movers are added, then the list is ranked by opening volume vs normal. Filters: price ≥ $20, average volume ≥ 1M, ATR ≥ $0.50, opening volume ≥ 1.0x, and a first candle with a direction. The top 20 are watched. Every rejected name is saved with its reason.
- From 09:36 the in-play rules run. A 1m close beyond the opening range in the first candle's direction triggers a contract check across every expiry 0–10 days out:
  - spread ≤ 5% of mid, quote ≤ 20 s old, open interest ≥ 500, volume ≥ 100;
  - delta 0.50–0.70, premium $0.30–$8;
  - decay over the expected hold, and no expiry after the next earnings date.
  The cheapest contract by spread plus decay wins, so the nearest expiry is not assumed. If nothing passes, the scanner records why and passes.
- Paper trades go to the "Stocks in play" research ledger: 1 contract, at most 6 open, stop 10% of ATR on a 1m close, the 20% premium ceiling, all out 15:25.

**Live market alerts** (each kind can be switched off on the Rules page)
- **Movers**: the 9:35 in-play list, and a top-movers digest at 10:00, 10:30, 11:00, 11:30, 12:30, 13:30, 14:00, 14:30 and 15:00. A digest is skipped when nothing changed.
- **Moves**:
  - SPY/QQQ: 2 heavy 5-minute candles.
  - Any watched in-play name: a sharp 5-minute move.
  - Every other universe stock: ≥ 1% and ≥ 0.25 ATR in about 5 minutes on 2x normal volume, from two batched quote calls a minute.
  - All from 09:45, with a 20-minute cooldown per ticker.
- **Scanner trades**: when the in-play ledger takes a paper trade, with the full contract details.
- **My trades**: guidance changes on Nick's positions.
- Every scanner and mover alert says it's an idea, not a validated setup. News still comes from Chart's 20-minute scan.

**Research experiments**, each with its own ledger and version and never mixed with main paper:
| Ledger | Version | What it tests |
|---|---|---|
| research | v3 | the v3 setups without the daily limits (existing) |
| exit31 | 2026-10-30.v3.1-exit31 | the **same entries** as research (same tick, same quote), with exits that let winners run: no stall or momentum exit before T1, a 15-minute if-flat, then at T1 sell 1 (or keep the single contract) with the stop at breakeven, trailing the tighter of the last 1m swing and VWAP |
| noise | 2026-10-30.v3.1-noise | the noise-band momentum rules on SPY/QQQ, half-hour checks, delta-0.65 contracts |
| inplay | 2026-10-30.v3.1-inplay | the stocks-in-play opening-range rules above |
| old | frozen | the old 20/12/10% rules (existing) |

Each trade records the underlying price at entry and exit, so the Research page shows how often the stock went the right way next to the option P/L. The page also shows expectancy with a 95% bootstrap range, average win vs loss, profit factor, max drawdown, trade count and how trades ended.

**Diagnostics** (`python3 backtest.py --from 2026-09-22 --to 2026-10-29`):
- Runs the real engine over every past day in a sandbox, then `diagnostics.py`:
  - a coin-flip baseline (20 seeds) and the opposite direction;
  - the exit breakdown, including losers closed by the if-flat timer within ~5 minutes;
  - the same entries under v3-style, bracket, hold-to-15:25, VWAP-trail and v3.1-runner exits;
  - the stock vs the option, split halves, and up vs down days.
- Also runs the in-play rules over the universe history.
- Writes `reports/backtest_*.md` and `diagnostics_*.md`. The Research page shows the latest.

## What is still experimental
- All three experiments. They have no forward results yet. Under 30 trades is "too early", and promotion needs forward evidence and Nick's decision.
- Backtests and diagnostics use **modeled option prices**, because Schwab has no historical option quotes. They find causes; they don't measure an option edge. Counterfactual exits run on 1m closes and approximate the live state machine. The live paper ledgers are the real record.
- The suspected causes of the bad Oct backtest are still only hypotheses until Chart runs the diagnostics on real Schwab history: the if-flat timer, capped winners, stops inside noise, and signals worse than random.

## Data and runtime limits for unattended scanning
- **Schwab must be connected.** With no Schwab login the scanner waits and says so. It never scans or trades on delayed data. The login expires every 7 days.
- **Chart's computer must stay awake and online**, with the server running. If it sleeps the scanner misses its 08:30/09:35 steps; it catches up when it wakes (until 15:15) but the morning ranking is then late. The Cloudflare quick-tunnel address changes when the tunnel restarts.
- **API budget:** every Schwab call shares one limiter (100 a minute, under Schwab's ~120).
  - The 08:30 baseline pass takes about 3 minutes.
  - The 09:35 scan makes about 60 calls plus chains.
  - Then about 22 calls a minute: one per watched name plus 2 for the universe pulse.
  - If the stream isn't available, SPY/QQQ REST polling adds about 15–30 a minute. The limiter waits instead of getting blocked.
- **Not verified against live Schwab yet:**
  - the movers endpoint's exact response;
  - how fresh single-stock chain quote times are (if they lag past 20 s, contracts are rejected as stale, which shows on the Scanner page);
  - the cumulative-volume field used by the pulse.
- **Earnings dates** come from Yahoo's calendar (unofficial, labeled), because Schwab's market-data API has no earnings calendar. When the date is unknown, a contract isn't rejected for earnings, and the row shows no ER tag.
- **History depth:** the engine now loads about 30 days of 1m history once a day. Noise-band needs 14 full prior sessions and won't trade until it has 10. Schwab keeps about 48 days of 1m history, so a backtest from Sep 22 has noise-band only partly active in its first days.
- **Backtest runtime:** about 2–3 minutes per day for SPY/QQQ, so about 1–1.5 hours for 28 days, plus a few minutes for the universe download. Run it in the background.

## Files
New: `scanner.py`, `noiseband.py`, `backtest.py`, `diagnostics.py`, `config/universe.json`, `tests/test_v31.py`, `docs/RESEARCH_NOTES.md`, this report.
Changed:
- `schwab.py`: rate limiter, movers, batch quotes, ranged bars, strike-limited chains.
- `marketdata.py`: deep history once a day.
- `exits.py`: v3.1 profile, guidance and alerts, 20% floor.
- `engine.py`: exit31 mirror, noise and in-play routing, any-ticker plans and contracts.
- `paper.py`: variant, version and underlying prices.
- `commands.py`: any ticker, expiry in IN, ENTER/WAIT/PASS, scanner context for Chart.
- `server.py`: `/api/scanner`, `/api/research`, `/api/diagnostics`.
- `index.html`: My trades / Scanner / Paper / Research pages, guidance cards, alert settings.
- `alerts.py`, `indicators.py` (about 3x faster Wilder smoothing, same results), `config/policy.json` (`research_variants`, `scanner`).

Rollback: restore the v3 backup folder. The new tables (`scan_rows`) and keys are ignored by v3.
