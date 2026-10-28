# What Nick can type in the desk box

**Handled by code: instant and free (no AI credits)**

| Type | What happens |
| --- | --- |
| `SPY puts under 765.50?` / `confirm QQQ calls over 612` | Builds a full plan (trigger, invalidation, contract, buy ≤, size, stop, breakeven, T1, if-flat, all out) and **watches it for 15 minutes**. Add `for 30 min` to change the length. |
| `check once SPY` / Check once button | Same plan, without watching. |
| `IN 2 at 0.95` | Logs your real fill on the plan's contract and gives your stop, breakeven, T1 and if-flat time. **Set your stop in Robinhood.** |
| `IN SPY 765C 2 at 0.95` | Same, naming the contract. |
| `OUT 1.20` / `OUT SPY 765C 1 at 1.20` | Logs your exit and shows P/L, contracts left, today's total and your streak. |
| `stop watching` / Unwatch button | Ends the watch. The paper engine keeps running. |
| `pause paper` / `resume paper` | Stops or restarts new paper entries. Open paper positions are still managed. |

**Sent to Chart (uses an AI credit)**: anything else, plus the Why? button and the short explanation under a new plan. Examples: "why?", "what changed?", "is there news?", "second opinion on this".

**Other tickers (watchlist, bottom left):** click a ticker to chart it and ask Chart about it. The buttons are Earnings play?, Key levels?, News? and Expected move?. Add or remove tickers right in the list. Earnings within 14 days show an ER badge. `IN NVDA 140C 1 at 3.20` and `OUT NVDA 4.10` log those trades to your journal with your time-of-day stop (20/12/10%). You manage them with Chart, because the desk only auto-manages SPY/QQQ 0DTE.

**Options chain (under the chart):** calls/puts, expiry, bid/ask/mark, change, delta, breakeven, with the desk's pick marked and a green dot on contracts that fit your rules. Click a row, then **Ask Chart** (sends "SPY 765P 0DTE at 0.86 …: is this a good entry right now?") or **Log my fill** (fills the log form; you still buy in Robinhood first). Hide it to give the chart the full height.

**Alerts:** the desk pings you for A/B setups and move alerts (2 heavy 5-minute candles), plus market-moving news from Chart's 20-minute scan. Turn pop-ups on with **Alerts** in the top bar, and pick which kinds you want on the Rules page. Phone pings work through the free ntfy app.
`kill switch`: stops paper entries and closes all paper trades (Paper tab button, tap twice).

The plan is always computed first, so it's valid even if Chart is slow or offline.
