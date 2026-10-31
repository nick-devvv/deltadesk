# What Nick can type in the desk box

**Handled by code: instant and free (no AI credits)**

| Type | What happens |
| --- | --- |
| `SPY puts under 765.50?` / `confirm QQQ calls over 612` | Builds a full plan (trigger, chart stop + 20% premium ceiling, contract, buy ≤, size, T1 at the next level, reward/risk, breakeven, exits, all out) and **watches it for 15 minutes**. Add `for 30 min` to change the length. If it can't reach 2:1 or fit the ceiling, it says so instead. |
| `check once SPY` / Check once button | Same plan, without watching. |
| `IN 2 at 0.95` / `I'm in SPY 765P 2 at 0.95` | Logs your real fill on the plan's contract and gives your chart stop, premium stop, T1, breakeven and exit rules. **Set your stop in Robinhood.** A trade that wasn't a desk setup is marked that way. |
| `STOP 0.85` | Tightens your stop. A looser stop is refused unless you type `STOP 0.70 force`, and every change is recorded with who made it. |
| `IN SPY 765C 2 at 0.95` | Same, naming the contract. |
| `IN NVDA 140C 11/07 1 at 3.20` | Any other ticker: add the expiry. The desk tracks that exact contract live and tells you HOLD / TIGHTEN STOP / TAKE PROFIT / EXIT as it changes. |
| `NVDA calls?` / `is AMD a buy here` | A full plan for any ticker, ending with ENTER, WAIT or PASS. It says whether it's a desk setup or your idea. |
| `OUT 1.20` / `OUT SPY 765C 1 at 1.20` | Logs your exit and shows P/L, contracts left, today's total and your streak. |
| `stop watching` / Unwatch button | Ends the watch. The paper engine keeps running. |
| `pause paper` / `resume paper` | Stops or restarts new paper entries. Open paper positions are still managed. |

**Sent to Chart (uses an AI credit)**: anything else, plus the Why? button and the short explanation under a new plan. Examples: "why?", "what changed?", "is there news?", "second opinion on this".

**Other tickers (watchlist, bottom left):** click a ticker to chart it and ask Chart about it. The buttons are Earnings play?, Key levels?, News? and Expected move?. Add or remove tickers right in the list. Earnings within 14 days show an ER badge. Log them with the expiry (`IN NVDA 140C 11/07 1 at 3.20`, `OUT NVDA 4.10`). The desk tracks them live with the same guidance as SPY/QQQ, starting from the 20% premium ceiling.

**Options chain (left column, above the watchlist):** calls/puts, expiry, bid/ask/mark, change, delta, breakeven, with the desk's pick marked and a green dot on contracts that fit your rules. Click a row, then **Ask Chart** (sends "SPY 765P 0DTE at 0.86 …: is this a good entry right now?") or **Log my fill** (fills the log form; you still buy in Robinhood first). Fold it with the arrow to give the watchlist more room.

**Chart:** the Desk chart is drawn from the same Schwab data the engine uses (1m, 2m or 5m candles, VWAP, EMA 9/21, MACD, levels, entry and exit marks). The TradingView button switches to TradingView's own chart.

**Alerts:** every setup alert carries the full plan: contract, max buy, size, chart stop and premium stop, T1 level, reward/risk, breakeven, stall and momentum exits, if-flat time and all out. The plan card fills in at the same time. It only pings when you could actually take the trade: not when you're at "stop for today", in a CPI/Fed block, under "A setups only" (for B setups), too far past the level, or in a cooldown. At most one per ticker and side every 10 minutes, and move alerts at most once per ticker every 15 minutes during entry hours (or when you hold a trade). The desk pings you for A/B setups and move alerts (2 heavy 5-minute candles), plus market-moving news from Chart's 20-minute scan. Turn pop-ups on with **Alerts** in the top bar, and pick which kinds you want on the Rules page. Phone pings work through the free ntfy app.
`kill switch`: stops paper entries and closes all simulated paper trades (Paper tab button, tap twice). Paper trades are simulated inside the desk on Schwab quotes; nothing is sent to any broker.

The plan is always computed first, so it's valid even if Chart is slow or offline.

**Journal (in the chat):** after each closed trade, a short card asks: followed the plan?, any mistakes, why you took it, why you got out, next time. Tap and type a few words, and it saves to the Journal tab. Press Later and it asks again in about 45 minutes. After 4:10 PM it asks 3 end-of-day questions (how it went, how you felt, one lesson). The 4:20 review uses all of it to suggest lessons. You never have to open the Journal tab.

**Pages:** **My trades** (your positions, the chart, Chart's guidance) · **Scanner** (stocks in play, live movers, why names didn't qualify) · **Markets** (v3.2: search any ticker, its live chart, the setups board, news & catalysts, earnings, paper autopilot, settings and spending) · **Paper** (the main strategy) · **Research** (experiments side by side) · Journal · Review · Rules.

**Live market alerts (Rules → Live alerts to switch each on/off):** stocks in play at 9:35, a top-movers digest every 30-60 minutes, quick moves on any scanned stock, scanner paper trades, and changes in the guidance on your own trades. Scanner and mover alerts are ideas, not validated setups.

**v3.2 (Markets tab):**
- Search any stock or ETF and open its live chart (1/2/5/15m, extended hours, Back to live). Times are Pacific by default.
- `check once NVDA calls` (or the Check calls / Check puts buttons) gives the desk's read: WAIT / SETUP FORMING / ENTRY CONDITIONS MET / INVALIDATED, the entry gate's state, and the planned max loss.
- If the gate says **TOO EXTENDED** or **WAIT FOR RETEST**, the move already happened: wait for a new setup or skip it.
- `IN NVDA 140C 11/07 2 at 3.20` tracks that exact contract (add the expiry for anything that isn't same-day SPY/QQQ).
- News labels: confirmed / attributed / unverified / opinion. Unverified never triggers an entry.

**v3.3:**
- Every plan shows an evidence badge. **Research only** means the setup's rules are met but testing found no edge over random entries: information, not an entry. **Your idea** means a level you picked: the desk checks it, but no tested edge stands behind it. Today no desk setup is qualified, so setup alerts are quiet notes instead of pings.
- Markets tab → **Strategy evidence**: every strategy that was tested, its status, the numbers and why.
- Markets tab → **Entry rules compared**: the old gate vs the new gate, side by side on paper.
- If the chart shows **No data** with "couldn't be reached through the tunnel (HTTP 530)", Chart's computer or its tunnel is down. The last good candles stay on screen and it retries by itself (5 s, then up to 60 s). If it lasts, ask Chart for the new desk link.

**v3.4 (Markets → Strategy lab):**
- Every strategy runs on every stock on the desk's list, every day, on paper. Nothing new pings you; the lab's paper trades stay out of your trade feed.
- **What works where:** split by strategy, setup, stock, strategy and stock, strategy and stock group, or strategy and a condition (X lean, RVOL, trend, time of day, MACD, gap, earnings and more). Each row shows signals, days, how often it won, the average result in R, what random entries on the same stock and day did, the edge over random with its 95% range, and whether it held in both halves of the dates.
- Grey rows have under 30 signals: too few to mean anything yet. Ask Chart "what's working?" and it reads the same report.
- When you're ready to reset paper with only the strategies that held up, tell Claude which rows. The history stays, so the fresh run shows whether they were real.

**v3.4.2:**
- **Which option contract** (Markets → Strategy lab, bottom): for the same live signals, 12 contracts each (same day, 1–2, 3–5 and 6–10 days out, at delta 0.35 / 0.45 / 0.60), followed on real quotes and nothing bought. It shows how often each choice made money with your 20% line, the average dollars, and how often the 20% line hit before the stock trade was over.
- **Exits selector:** "Same yardstick for all" or "Each strategy's own exits" (the noise band only at its half-hour checks).
- Rows stay "too few" until they have 30 signals over 10 trading days.

**v3.5:**
- **Learning tab** (new, at the end of the menu): what the desk looked at today, why it took or skipped each one, how skipped setups would have done under one fixed rule, and the experiments with their pass/fail rules written down before the results.
- **ORB retest** (top of Learning): your ORB sequence, live for SPY and QQQ: range forming, waiting for the break, waiting for a separate candle fully outside, waiting for the retest, entry confirmed. Paper only.
- **Health links** (safe to share with an uptime checker, no data inside): `/healthz` and `/readyz` on the desk address.
