# Desk v2: setup on Chart's computer

You do every step yourself, in Grok. Nothing here needs Claude to take over your computer.

## What changes
- **New page.** TradingView in the middle, with the Plan and Positions cards and the conversation on the right, and an activity feed under the chart. Separate Paper, Journal, Review and Rules pages. The old page is still at `/legacy`.
- **The paper engine trades SPY/QQQ by itself** in the Alpaca paper account, in code, with no AI credits. Chart no longer runs `bot.py take`.
- **Rules:**
  - Strict 20% stop.
  - No dollar limits.
  - 2 losses in a row: A setups only, plus a 10-minute cooldown.
  - 3 losses in a row: STOP FOR TODAY.
  - Breakeven, then T1, then trail.
  - If flat, get out at the time on the plan.
  - All out at 3:25.
- **Typing IN / OUT / confirm / check once / stop watching is handled in code**, so it's instant and free. Only "why?" and free questions use Chart.
- **Voice mode** (Voice button or press J): talk to the desk and Chart, and hear the answers. Fills you say out loud are read back for a yes before they're logged.
- **Watchlist (bottom left)** for other tickers and earnings plays. Click one to chart it and ask Chart about it.
- **Journal** is written at 4:05 PM every day. The **4:20 review** proposes lessons, and you approve them.

## Step 1: attach the files to Chart
Attach `nicks-desk-v2.zip` (in Downloads/nicks-desk) to a new Chart chat with the message below.

## Step 2: the message to send Chart (copy all of it)

```
DESK V2 INSTALL. Do these steps on your computer, in order, and show me the output of each.
You never place real trades, never click buy/sell/order buttons, and never enter passwords or keys.

1. Back up: cp -r ~/desk ~/desk_backup_$(date +%Y%m%d)
2. Unzip the attached nicks-desk-v2.zip over ~/desk (overwrite files with the same names; keep everything else, including bot.py, shadow.py, review.py, desk-state.json and my Secrets).
3. pip install yfinance pandas numpy pytest quiverquant
4. cd ~/desk && python3 -m pytest -q tests/   -> must say "29 passed". If not, stop and show me the error.
5. Restart the desk server the same way watchdog.sh starts it (same env: DESK_TOKEN, CHAT_WEBHOOK, CHAT_WEBHOOK_KEY, ALPACA_KEY, ALPACA_SECRET, PORT). Then run:
   curl -s "http://127.0.0.1:8765/api/state?k=$DESK_TOKEN" | head -c 400
   and show me the output. "paper" should say RUNNING or IDLE and the broker line should say paper account verified.
6. Replace your routine instructions with the files in ~/desk/grok/:
   - Desk chat webhook routine  -> PRIMARY_COACH_SYSTEM_PROMPT.md
   - 9:00 AM ET morning routine -> MORNING_ROUTINE_PROMPT.md (put my real DESK_TOKEN from Secrets where it says DESK_TOKEN; never paste it in chat)
   - 4:20 PM ET review routine  -> REVIEW_PROMPT.md (same)
7. From now on: do NOT run "bot.py take" or "bot.py close" after a verdict, and don't run shadow.py in/out. The desk's paper engine does paper trades by itself, and I log my trades on the desk.
8. Save ~/desk/docs/LEGACY_RULE_MIGRATION.md in your Library as "Desk v2 rules map".
9. Reply with: tests result, the /api/state line, and "routines updated".
```

## Step 3: check it
Open your desk link (same link as before). You should see:
- the new dark page, with SPY/QQQ at the top left and the session pill showing OPEN, PREMARKET or similar;
- the TradingView chart in the middle;
- the Plan card on the right.

Type `check once SPY calls` and a plan should appear right away.

If the page says "Disconnected", Chart's computer or the server is down. Ask Chart: "restart the desk server with watchdog.sh and show /api/state".

## Rollback (if something breaks during market hours)
Send Chart: `cp ~/desk_backup_YYYYMMDD/server.py ~/desk/server.py && cp ~/desk_backup_YYYYMMDD/index.html ~/desk/index.html`, then restart the server. `server_legacy.py` in the zip is also the old server.

## Known limits
- Option quotes from Alpaca are **delayed/indicative**. The plan says so. Always check the live bid/ask in Legend before you buy.
- The desk's price comes from Alpaca IEX (one exchange) or Yahoo 1-minute bars. TradingView uses its own feed. Small differences are normal.
- If Chart's computer sleeps or goes offline, the page, paper engine and watches stop until it's back.
- Chart answers through a webhook, so its replies take a few seconds to a minute. The plan never waits on Chart.

## Files in the zip
| File | What it is |
| --- | --- |
| `server.py` | Page + API + engine loop |
| `engine.py` | Plans, setups, paper engine, watches, position management, journal |
| `core.py` | Rules, market calendar, stop/size/exit math |
| `commands.py` | What you type → actions (IN/OUT/confirm/…) |
| `store.py` | SQLite journal database (`journal/desk.db`, created on first run) |
| `broker.py` | Alpaca **paper-only** client (refuses live keys and non-paper accounts) |
| `kronos_shadow.py` | Kronos forecast test (shadow only, own process, no keys). Off until KRONOS=1 |
| `knowledge/cards.json` | 35 knowledge cards; the desk sends the 3 most relevant to Chart with each question |
| `alerts.py` | Live alerts: setups + move alerts (code) and news from Chart's 20-minute scan; phone pings via ntfy (NTFY_TOPIC) |
| `schwab.py` | Optional live Schwab market data (read-only; trading endpoints refused in code). Setup: docs/SCHWAB_SETUP.md |
| `altdata.py` | Optional Quiver data (congress trades, short volume, WSB) when QUIVER_KEY is in Secrets |
| `watchlist.py` | Other tickers: quotes, earnings dates, add/remove (`config/watchlist.json`) |
| `desk.py`, `chartdata.py` | Market data read (Yahoo bars, indicators, levels) |
| `index.html`, `index_legacy.html` | New page and the old page (`/legacy`) |
| `server_legacy.py` | Old server, for rollback |
| `config/policy.json` | The active rules (version 2026-10-28.2) |
| `config/agent_policy.json` | Who does what (you trade real money, code does paper, Chart explains) |
| `grok/*` | Chart's three routine prompts, quick commands, context schema, endpoint list |
| `docs/LEGACY_RULE_MIGRATION.md` | Every Playbook rule and where it went, plus 3 open questions |
| `tests/test_desk.py` | 29 tests: no network, no AI, fake paper broker |
| `DESIGN.md` | Page design notes |
