# DeltaDesk v3.4: the strategy lab

What Nick asked for on Oct 30: run every strategy every day, collect as much data as possible, find which strategies and indicators work on which stocks and under which conditions (X included), and don't call anything failed yet.

Your layout is unchanged. Everything new lives in one box at the bottom of the **Markets** tab: **Strategy lab**.

Some rules hold for all of it:
- Main paper (`2026-10-29.v3`) is untouched.
- Nothing sends an order anywhere. Real trades are yours, in Robinhood.
- Nothing new costs money.

## What it does

**1. Signal tape: every strategy on every stock**

- **Coverage:**
  - every symbol on the setups board: the 125-name universe, SPY/QQQ, your watchlist and the day's stocks in play;
  - every finished 1-minute bar, processed in time order, so a signal only ever sees data up to its own bar.

  A test changes later prices and checks that earlier signals don't move.
- **Detectors** (15 strategy families):
  - the setups board's rules: ORB 5/15/30 break, retest and failed break; pre-market and prior-day level break and retest; VWAP reclaim and rejection; momentum continuation; pullback in a trend;
  - the v3 rules (ORB break/retest, failed break, PDH/PDL retest, VWAP reclaim, VWAP + MACD) on every stock;
  - the ORB15 first break and first retest, exactly as the study defines them;
  - the MACD video rule: 5m MACD crossing its signal beyond the zero line on the 200 EMA's side, 2R;
  - the noise band at the half-hour checks, on every stock with two weeks of history.
- **Conditions saved with each signal** (as known at that moment):
  - time of day, RVOL, 5m trend (ADX ≥ 25 with efficiency ≥ 0.4), 2m MACD, the 5m 200 EMA;
  - distance from VWAP, SPY since the open, the opening gap;
  - price, liquidity, stock group, earnings phase;
  - **the X read**: the latest story the desk had detected *before* the signal, with its trader lean vs the trade, its label and whether attention was rising. A story found later is never used for an earlier signal (tested).
- **Outcome** (after 3:31 PM, for signals decided 09:45–3:15 PM):
  - one yardstick for every strategy, in R: entry at the next bar's open, stop just past the signal's invalidation (0.05 × daily ATR), 2R target, flat at 3:25 PM, $0.04/share costs, the stop counted first on an ambiguous bar;
  - also the move at 5, 15 and 30 minutes;
  - **random entries** on the same stock, day, side, window and stop distance (20 per signal, fixed seed), so every row says what chance alone did.

**2. Lab paper ledgers: every strategy trades on paper, each in its own ledger**

- **15 ledgers** (`lab_*`), so one strategy can't crowd another out.
- **When a signal can be traded:** only if it was seen within 150 seconds of its bar, inside 09:45–3:15 PM.
- **Same checks as the strict ledgers:**
  - the anti-chasing gate (scoped to the ledger, no entry worse than the signal price);
  - the option contract check;
  - strict fills: ask + $0.01 in, the final fill at or under the limit, bid − $0.01 out, $0.02 fees per side, latency enforced;
  - 1 contract and the 20% planned premium line.
- **Exits** (one batched quote request for all open lab trades): all out at 3:25 PM, the 20% line, a finished 1m close past the invalidation, or the 2:1 target. The noise ledger keeps its own half-hour stop.
- **Caps:**
  - 2 open per ledger and 6 ideas per ledger per day;
  - 20 open lab trades in total;
  - 8 entry attempts a minute (each costs 2 Schwab requests).
- **Separate from your trades:**
  - your pause button and the kill switch cover the lab too;
  - lab trades stay out of your trade feed and off My trades;
  - SPY/QQQ keep their own ledgers for the v3 rules and the noise band.

**3. What works where (Markets → Strategy lab)**

- **Splits:** by strategy, setup, stock, strategy and stock, strategy and stock group, or strategy and any condition (for example *VWAP reclaim when X agrees* vs *when there's no X read*).
- **Each row shows:** signals, days, won %, average R, random average R, the **edge over random** with a 95% range (resampled by whole days), and whether the edge is positive in **both the earlier and the later half** of the dates.
- **Grey rows** have under 30 signals.
- **When one stock has too few signals,** the row shows its group's and all stocks' numbers underneath.
- **The lab ledgers' paper results** sit above, per ledger.

**Daily bar archive:** `journal/bars/<day>/<ticker>.csv.gz`.
- Each morning, after the history pull, it back-fills every day Schwab still has (about 30 days).
- After the close it writes today's bars, pre-market included.

The data keeps growing past Schwab's history window, and later studies can be re-run on it.

## What changed in the code

| Where | Change |
|---|---|
| `lab.py` (new) | Everything above. Version `2026-10-30.v3.4-lab1`. |
| `paper.py` | `LAB_LEDGERS` added to the research ledgers; `lab_*` uses strict fills; lab events are logged as kind `lab`. |
| `engine.py` | The engine skips lab trades (the lab manages them with one batched request). The kill switch now closes every simulated ledger. |
| `marketdata.py` | `option_quotes()`: one request for up to 100 contracts. `option_quote_cached()`: no request at all. |
| `strategy.py` | `build_snapshot(..., quote=True)`: the default is unchanged; the lab passes `quote=False`. VWAP + MACD state can use its own namespace and skip events. The main engine's behavior is unchanged. |
| `research.py` | `signals_for_day(..., live=False)`: the study is unchanged; `live=True` reports a signal on the newest bar. |
| `matched_benchmarks.py` | `outcome_arrays()` (same rules as `stock_outcome`, about 100× faster; equality tested) and `control_mean()`. |
| `server.py` | `/api/lab`, `/api/lab/report`, `/api/lab/signals`. The lab starts with the server. The page state no longer carries lab trades. |
| `config/specialists.json` | **registry2**. The 4 retired items (MACD video, RVOL ≥ 2, ADX trend filter, morning window) are back to RESEARCH ONLY; the earlier status is kept as `previous_status`. 15 `LAB-*` experiments were added. The ORB15 base and retest stay DRAFT, as you asked. Nothing is PAPER QUALIFIED. |
| `config/sectors.json` (new) | Stock groups for the report. |
| `index.html` | The Strategy lab box in Markets. Lab events are kept out of the trade feed. The "simulated open" count excludes the lab. |
| Chart prompts | The coach, review, endpoint list and quick commands. Lab rows are research: quote sample size, edge vs random and both halves; never a win rate to expect. |

## Tests and checks
- **Full suite: 153 passed, 1 skipped** (v3.4.1: 156).
- **13 new tests** (`tests/test_v34.py`):
  - every family is recorded;
  - future bars don't change earlier signals;
  - the fast outcome matches the reference path rules;
  - outcomes wait for the close, and the random entries are reproducible;
  - a live signal fills its own ledger with strict fills;
  - caps, budget, pause, SPY/QQQ separation, and stale signals failing closed;
  - exits (20% line, all out);
  - the report's math: edge, interval, both halves, hierarchy, X condition;
  - X is point-in-time;
  - archive round trip, back-fill and history budget;
  - the registry;
  - batched quotes (12 contracts in 1 request);
  - the kill switch closes lab trades, and the lab has no order path.
- **Test isolation:** tests write archive files only to a temporary folder (the harness enforces it).
- **Demo UI:** the box renders at 1280 / 1440 / 1920 / 390 with no sideways scroll; My trades is unchanged. Two bugs were fixed: an older "what works" answer could overwrite a newer selection, and the condition picker showed when hidden.

## Costs on Chart's computer
- **Schwab requests:** they share the desk's built-in limit of 100 a minute (Schwab allows about 120).
  - The lab adds the morning history pull: 30 a minute until done, about 4 minutes for 125 names.
  - Entry attempts: at most 16 a minute, only when signals are live.
  - Exits: 4 a minute.
- **CPU:** about 40 ms per symbol per minute here, so about 5 seconds per minute for ~127 symbols (roughly 9% of one core). After a restart, catch-up is capped at 8 seconds per 15-second step.
- **Disk:** the archive is about 1 MB a day compressed for ~127 symbols; the tape is a few thousand rows a day in the journal database.

## What this can and can't tell you
- With 15 strategies × ~127 stocks × many conditions, **some rows will look great by luck**. A row means something only when it has:
  - enough signals (30+);
  - a 95% range above zero;
  - a positive edge in both halves of the dates;
  - and it then keeps holding on new dates.

  Nothing is promoted automatically.
- **The tape is about the stock move;** the lab ledgers are the option results. A strategy can work on the stock and still lose on options (spread and decay). The page shows both.
- **Late signals:** the board refreshes quiet names about every 6 minutes. A signal found late still gets its stock outcome, but it isn't paper traded (the 150-second rule). That's honest, but it means fewer paper trades on quiet names.
- **How to reset paper with the winners later:** tell me which rows. The new run starts as fresh versions, and the old history stays, because the new run is the test of whether the winners were real.

## v3.4.1 (same day): the Kronos pile-up and the lab's time budget
**What happened on Oct 30.** The desk server went into a restart loop at about 1:40 PM ET. The box was out of memory: 40 copies of `kronos_shadow.py` were running at about 370 MB each, roughly 13.8 GB of 16 GB.

**Why it happened:**
- **Kronos copies outlived their server.** `server.py start_kronos()` runs Kronos as a child process. When the server stopped (a restart for an install, a tunnel restart, or a crash), nothing stopped the child, and every new server started another copy.
- **The squeeze fed itself.** Once memory was tight, the server was killed; the watchdog restarted it and added one more copy each time.
- **The v3.4 lab made it worse.** Just after a restart it catches up on the morning's bars, and its live bars weren't under its time budget, so one step took about 20 seconds.

**Fixed:**
- `kronos_shadow.py`: one copy at most (an OS file lock in `journal/kronos.lock`). It exits by itself within 5 seconds of its server being gone.
- `server.py`: on start, it stops leftover Kronos copies of this desk whose server is gone; copies started by a live server and copies from other folders are left alone. Kronos keeps running as a test, as you asked.
- `lab.py`: one 4-second time budget for the whole lab step, live bars included, and it yields to the desk's other threads between symbols. A lab that falls behind catches up over the next steps instead of hogging the desk; `/api/lab` shows `bars_behind`.
- The lab's indicator cache resets daily, and the after-close outcome checks run every 2 minutes, not every 15 seconds.
- Signal rules, outcomes and ledgers are unchanged.

**Tests:** 156 passed, 1 skipped:
- a second Kronos process is refused while the first holds the lock;
- only orphaned copies are selected for stopping;
- the step budget covers live bars.

## Live checks that only Chart's computer can do
1. **Startup:** the server log shows "Strategy lab ... started", and `/api/lab` shows `with_history` climbing to ~125 within minutes of 07:00 ET.
2. **During the session:** `/api/lab` today-counts grow, and `last_error` is empty.
3. **After 3:31 PM:** `/api/lab/report?by=strategy` shows resolved rows. After 4:06 PM, `journal/bars/<today>/` has a file per symbol.
