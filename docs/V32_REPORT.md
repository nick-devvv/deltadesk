# DeltaDesk v3.2: Schwab connection, live charts for any ticker, setups, catalysts, entry gate

Your layout is unchanged. Everything new lives in one new tab, **Markets**. The existing pages show a few new lines: guidance on your trade, planned-loss numbers on plans, and more controls in Rules → Data sources. Main paper rules did not change: v3 (`2026-10-29.v3`) stays frozen for the forward test. No code sends an order anywhere. You place every real trade in Robinhood.

## Root causes found
| Problem | Cause | Fix |
|---|---|---|
| You couldn't disconnect or reconnect Schwab cleanly | There was no disconnect path. "Connected" only meant a token file existed. A new login didn't restart the stream, and the stream retried forever on HTTP 401 | One lifecycle in `schwab.py` and `schwab_stream.py` with six states. Connected requires a market-data call that worked in the last 3 minutes. The stream runs in numbered generations, so an old worker shuts itself down. It stops after 3 refusals and tells you what to fix |
| The stream refused the old login | The login was made before "Accounts and Trading Production" was added to the Schwab app | Log in again (Rules → Data sources → Reconnect). The page now tells you this when it happens |
| The chart didn't feel live | It reloaded everything every 5 s and only for SPY/QQQ. With streaming on, tickers not on the stream got no bars at all. There was no current candle between stream bars | REST bars for any ticker the stream doesn't carry (throttled). A live update every 2 s that changes only the newest candles. A provisional current candle from streamed trade prices, with no volume. A redraw stops at the first older bar instead of drawing it wrong |
| Old responses could overwrite a new ticker | No request sequence and no cancel | Every full load is numbered and the previous one is cancelled. Anything for another ticker or timeframe is dropped |
| Hidden SPY/QQQ assumptions | The chart, plan card, "0DTE" labels, stream subscriptions and the coach context were all limited to SPY/QQQ | Any Schwab-supported ticker plans, charts and tracks. The chart ticker and open trades get streamed, and the previous chart ticker is unsubscribed |
| Entries could chase | Nothing stopped a plan from turning READY after the move had already happened | `entrygate.py` (below). It runs in code and nothing can override it, including Chart, a score or a headline |

## What's new
**Schwab connection (Rules → Data sources, plus a health line on Markets)**
- **States:** disconnected / connecting / connected / reconnecting / expired / error. Each one comes with the reason and the next step, and the page shows when data was last verified.
- **Buttons:** Connect, Reconnect (log in again), Restart stream and Disconnect (tap twice). None of them needs a restart or deleting a file.
- **What Disconnect does:** it stops the stream and its retries, drops the subscriptions and deletes the saved login on Chart's computer. It doesn't revoke anything at Schwab, because Schwab offers no revoke call here. The old login expires on its own after 7 days, or you can reset the app secret to cut it off sooner.
- **Problem cases handled:**
  - A login link can only be used once, so pasting it twice does nothing harmful.
  - If Schwab rejects the saved login, the state shows "expired" and the desk stops trying until you log in again.
  - When the network drops, the stream reconnects with backoff and refills the missing bars.
- **Tokens:** they stay in `journal/schwab_token.json` and never reach the page, Chart or the logs (tested).

**Live chart (Markets tab; the My trades chart keeps its controls)**
- **Basics:** any stock or ETF, 1/2/5/15m candles, extended hours on or off, and the previous session so you can scroll back. Zoom, pan, crosshair and **Back to live**. Updates never reset your view.
- **What it shows:** symbol, timeframe, session, last update and data source. The status reads **live / delayed / stale / market closed / no data**. "Stale" during market hours with the connection up says the symbol may be trading thinly, which is different from a broken feed.
- **Times:** shown in Pacific by default (PT/ET switch). Sessions use New York time, the exchange holiday list and half days.
- **Indicators:** VWAP is regular-session only. MACD on 2m matches the engine. On other timeframes it's for reading only and labeled.
- **Honest candles:** stream or REST 1m bars, deduplicated by minute, and an out-of-order trade never rewinds a candle. While streaming, the current minute is drawn from the trade prices the stream reported and labeled **provisional, no volume**. Schwab's real bar replaces it when the minute closes.

**Search vs scanning (Markets)**
- **Search** opens any ticker through Schwab's instrument search. Without Schwab it falls back to the desk's own lists and says so.
- **The setups board** scans a fixed list, not the whole market: the 125-name universe, SPY/QQQ, your watchlist and the stocks in play. Prices refresh every 60 s and bars for 20 symbols a minute, hot names first. The page shows the coverage and the age of every row.
- **Setups**, each a written rule shown on the page:
  - gainers and losers;
  - time-of-day RVOL, with a labeled approximation when there's no profile;
  - opening range 5/15/30, used only once the range is complete: approaching / breaking / closed beyond / retest / failed;
  - VWAP reclaim / rejection / holding above or below;
  - pre-market and previous-day high/low breaks;
  - relative strength vs SPY;
  - momentum continuation and pullbacks.
- **Flags:** illiquid, wide spread, low-volume move, extended, thin pre-market, stale.
- **Rank score:** the sum of the listed parts, explained on the page. It is not a probability. "No qualifying setups" is a normal answer.
- **Reversals:** a failed breakout is a *watch*. It needs its own confirmed reversal setup with a fresh zone, invalidation and contract. The desk never flips direction automatically after a stop, and never buys puts just because a stock rose.

**Anti-chasing entry gate (`entrygate.py`, settings in policy `entry_gate`)**
- **What's stored:** each setup is saved once, versioned, with its trigger, entry zone, latest acceptable entry, structural invalidation, a target taken from a real level, an expiry time and the data it was built from. None of these can be edited afterwards.
- **States:** WATCHING / CONFIRMATION NEEDED / ENTRY CONDITIONS MET / TOO EXTENDED / WAIT FOR RETEST (missed) / INVALIDATED / NO TRADE. The page shows the check that failed.
- **The math:** reward/risk is recomputed from the CURRENT price after costs: RR = (target − entry − cost) / (entry − invalidation + cost). The latest acceptable entry is where RR falls to the minimum. Your example: 100 / 99.50 / 101 gives 2.0 at 100.00 and 0.15 at 100.80.
- **When price leaves the zone:** the setup is **MISSED: the move already happened. Wait for a new setup or skip it.** Only a NEW structure, such as a retest that holds, creates a new setup with its own risk.
- **Where it's enforced:** on your plans (ENTER only when the gate passes) and in the new "Entry gate" research ledger. On main paper it only observes, to keep the frozen forward test frozen.
- **Thresholds** (zone 0.6 × 5m ATR, 10-minute confirmation window, 60-minute expiry, the v3 2:1 minimum) are **starting hypotheses to test on paper**, not proven values.

**Catalysts (`catalysts.py`, Markets → News & catalysts)**
- **SEC EDGAR (free):** current 8-K/6-K filings for the scanned universe, matched by CIK, checked once a minute, at most 10 requests a second. It needs `SEC_USER_AGENT` (your name and email) in Chart's Secrets.
- **xAI X + web search (paid, OFF by default):**
  - The Responses API at `api.x.ai/v1/responses` with the `x_search` and `web_search` tools, model grok-4.7. Checked against docs.x.ai on Oct 29.
  - Prices: $2 / 1M input tokens, $6 / 1M output, X search $5 per 1,000 posts returned, web search $5 per 1,000 calls.
  - Turned on with `XAI_API_KEY` in Chart's Secrets plus the switch on Markets → Settings.
  - Limits: a daily dollar budget (default $2) and an hourly cap (12). Searches run only for new catalysts, unusual activity, shortlisted setups and open trades.
- **Chart's 20-minute news routine** still works and is labeled "via Chart".
- **Labels:** set in code from the URLs actually retrieved: **confirmed** (sec.gov, an agency, a press wire or the company's site), **attributed** (named outlets), **unverified** (posts only: watchlist only, can never trigger an entry), **opinion**. An item with no retrieved source is dropped.
- **Duplicates and old news:** same-story items are grouped. Reposts don't alert again, but a verification upgrade does. A story more than 24 h old when first seen is marked resurfacing.
- **Times kept:** event, publication, first detection, verification, alert, and the price move since detection.
- **Sentiment:** trader sentiment, product sentiment and fundamentals are kept apart and shown as a sample with its time window.
- **Retrieved text** is untrusted data. It's cleaned and displayed, never followed as an instruction.

**Earnings (`earnings.py`)**
- **The three phases** are recorded separately:
  - **before:** date and timing marked confirmed or estimated, the expiry exposed to the event, ATM IV for that expiry vs the next one, and spreads;
  - **after the release:** reported vs expected numbers only when both have sources, GAAP and adjusted kept apart;
  - **the call:** attributed statements, when an authorized source exists.
- **The move proxy** shows its strikes, expiry, quote time and formula. It is a rough price proxy, not a guaranteed range and not a 68% interval.
- **Paper strategies:**
  - `earn_post` (the default) waits for a confirmed setup in the first session after the release, through the gate.
  - `earn_pre` is research only: an ATM straddle held through the report and sized by the **full** premium at risk. It exists to measure IV crush, and nothing assumes it profits.
- **Dates:** Schwab has no earnings calendar. Yahoo dates are labeled estimated until you or Chart confirm one with a source (POST `/api/earnings`).

**Options, your 20% and paper realism**
- **Options hours:** checked against Cboe and Robinhood on Oct 29. Equity options trade 9:30–16:00 ET; designated ETFs to 16:15; half days to 13:00/13:15. The desk makes **no simulated fills** in Cboe's extended sessions or with no valid quote.
- **Your trades:** the desk tracks the exact contract (expiry, strike, call/put, fill, quantity).
  - Your example works out as stated: $2.00 → **$1.60 line, 3 × 100 → $120 before fees and slippage**.
  - The full premium at risk is shown separately: $600 in that example.
  - The stock invalidation is shown separately too.
- **Planned, not a cap:** the 20% is an alert/exit threshold, not a cap on the real loss. The desk says there's no broker stop it knows of. It says "NOT monitoring the premium" whenever there's no fresh quote for that exact contract.
- **Paper realism:**
  - Fills come at the first executable quote after the signal plus latency, at ask + slippage + fees, and exits at the bid.
  - A gap exits at the real bid, so losses are not clipped to 20% (tested).
  - There's an emergency pause, duplicate suppression and daily limits. Rejected and skipped setups are recorded with reasons.

**Evaluation (Markets → Entry rules compared)**
- **Same sample for every rule:** confirmed breakouts, pullbacks/retests and reversals are compared on every stored setup, traded or not, so fewer trades can't hide missed moves. Early breakouts are never taken by the gate (it needs a finished close).
- **Latency:** signal to simulated fill, and catalyst publication to detection to alert, measured from timestamps. When other traders saw the same news is unknown.

## Checks that passed (offline: 112 passed, 1 skipped; fake Schwab server and fake websocket)
- **Connection:**
  - Connect → disconnect three times in a row with exactly one socket open at a time and a LOGOUT each time.
  - Restart and reconnect never open a second stream.
  - A login link is used only once.
  - "Connected" requires a working data call: 401 → error, network loss → reconnecting.
  - An expired or rejected login can be fixed in place without a restart.
  - 3 stream refusals → stopped, with the fix shown.
  - A dropped socket reconnects with one socket.
  - Switching chart tickers unsubscribes the old one but keeps open-trade tickers.
  - Tokens never reach the page.
- **Chart:**
  - 1/2/5/15m candles sit on the 09:30 grid with no duplicates, and 15m volume equals its 1m bars.
  - A new candle appears when the minute ends.
  - Extended hours on or off, with VWAP regular-session only.
  - A provisional candle has no volume and is replaced by the real bar.
  - Stale, closed and unknown-symbol states are shown.
  - ORB levels use the 09:30 open and complete ranges only.
  - Any ticker charts.
- **Setups board:**
  - ORB states, an extended entry not qualifying, time-of-day RVOL and its labeled approximation.
  - VWAP, pre-market and prior-day breaks, relative strength, flags and ranking, "no qualifying setups".
  - A full board pass on the stock fixture whose rows point to the same ORB level the chart draws.
  - A failed breakout stays a watch.
- **Gate:**
  - Your worked example; every state; the window expiring; a missed entry not chased.
  - **A bullish score can't bypass the gate.**
  - A qualified retest is a new setup with its own risk.
- **Paper:**
  - **A closed options market never gets a simulated fill.**
  - **An earnings gap exits at the real bid below the planned stop, and losses aren't capped.**
  - The emergency pause works.
- **Catalysts:**
  - An EDGAR 8-K is confirmed and starts the release phase.
  - Labels come from retrieved URLs; rumors can't trigger entries.
  - Resurfacing stories, ambiguous tickers and untrusted text are handled.
  - xAI keeps only cited URLs, tracks cost and stops at the budget.
  - The straddle proxy shows its inputs.
- **Your trades and plans:**
  - Any-ticker trades are tracked by exact contract; with no quote the desk says NO DATA and never sells.
  - The 20% example works out as stated.
  - Plan states keep observations apart from interpretation.
  - The rule comparison keeps untraded setups.
- **UI:** checked in a browser at 1280 / 1440 / 1920 / 390 px with no sideways scrolling. My trades looks the same as v3.1 apart from the new tab in the menu.

## Needs your live session (not verified yet)
- **Schwab:** a real login, the stream LOGIN with your new app products, CHART_EQUITY timing, the instrument search response, movers, the cumulative volume field and single-stock chain quote ages.
- **EDGAR:** the current-filings feed from Chart's computer (with SEC_USER_AGENT set).
- **xAI:** a real search, only if you turn it on and accept the cost, and the actual citation format for X posts.
- **Live timing:** latency and the setups-board refresh cycle under real load (the whole board shares Schwab's ~120 calls a minute).
- **Yahoo earnings dates:** unofficial; they will stay "estimated" until confirmed.

## Provider limits
- **Schwab:** no earnings calendar, no consensus estimates, no historical option quotes. Option backtests stay modeled: a signal study, not an options backtest.
- **Coverage:** the setups board covers the listed symbols only. Quiet names can be several minutes old, and each row says how old.
- **X search** results are a sample of posts, not a full count, and the docs give no post timestamps in the citations. Engagement and badges are never treated as proof.
- **Speed:** the desk can't claim to beat professional news feeds. It only measures its own delays.
