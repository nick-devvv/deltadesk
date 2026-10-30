# DeltaDesk v3.2: setup on Chart's computer

You do every step yourself, in Grok. Nothing here needs Claude to take over your computer. The Schwab login, the Schwab keys and any new keys are yours to enter; nobody else types them.

## What's new in v3.2 (main paper rules unchanged; full details in docs/V32_REPORT.md)
- **Markets tab (new; your other pages keep their layout):**
  - search any stock or ETF and its live chart (1/2/5/15m, extended hours, Back to live, Pacific time);
  - the desk's read on that ticker and the setups board;
  - news & catalysts with source labels;
  - the earnings calendar in three phases;
  - the paper autopilot, settings and spending, and the entry rules compared.
- **Schwab you can manage yourself:** Connect, Reconnect, Restart stream and Disconnect on Rules → Data sources, with honest states (connected only when data is actually flowing).
- **Anti-chasing gate in code:** a missed move becomes "WAIT FOR RETEST": the move already happened, wait for a new setup or skip it. No entry is moved, no stop widened. Chart can't override it.
- **Catalysts:**
  - SEC filings (free), plus optional X + web search through xAI (paid, off until you turn it on).
  - Every story is labeled from the links actually retrieved. Rumors can never trigger an entry.
- **Your trades on any ticker:** exact contract, the 20% line, the full premium at risk, and "not monitoring" when the desk has no fresh quote.

## Step 0: what costs money (decide before turning anything on)
- **Nothing new by default.** SEC EDGAR is free. The xAI search stays OFF.
- **If you want X search:** create an API key at console.x.ai and put it in Chart's Secrets as `XAI_API_KEY` yourself, the same way you added the Schwab keys, then have Chart restart the desk. Then turn on "X and web search" on Markets → Settings.
  - Cost (docs.x.ai, checked Oct 29): grok-4.7 $2 per 1M input and $6 per 1M output tokens, X search $5 per 1,000 posts returned, web search $5 per 1,000 calls.
  - The desk stops at your daily budget (default $2) and 12 searches an hour, and shows what it spent.
- **SEC filings monitor:** put `SEC_USER_AGENT` in Chart's Secrets with your name and email, e.g. `Nick DeltaDesk nick@example.com` (the SEC requires one). It's free.

## Step 1: attach the file to Chart
Attach `deltadesk-v3.2.zip` (in Downloads/nicks-desk) to a new Chart chat with the message below. If the attachment doesn't arrive, tell Chart the file's path on your Mac and its sha256 (both in my message).

## Step 2: the message to send Chart (copy all of it)

```
DESK V3.2 INSTALL. Do these steps on your computer, in order, and show me the output of each.
You never place real trades, never click buy/sell/order buttons, and never enter passwords or keys.

1. Back up: cp -r ~/desk ~/desk_backup_v31_$(date +%Y%m%d)
2. Check the zip: sha256sum deltadesk-v3.2.zip   (must match the sha256 Nick gives you; if not, stop)
3. Unzip the attached deltadesk-v3.2.zip over ~/desk. Overwrite files with the same names and keep everything else (journal/desk.db, schwab.env, webhook.env, DESK_TOKEN.txt, watchdog.sh, bot.py, shadow.py, review.py, config/watchlist.json, config/events.json). The zip has no journal folder and no secrets.
4. cd ~/desk && python3 -m pytest -q tests/   -> must end with "112 passed, 1 skipped". If not, stop and show me the error.
5. Restart the desk with watchdog.sh. Then show me these two lines (no tokens in the output):
   curl -s "http://127.0.0.1:8765/api/schwab/status?k=$(cat DESK_TOKEN.txt)" | head -c 300
   curl -s "http://127.0.0.1:8765/api/setups?k=$(cat DESK_TOKEN.txt)" | head -c 300
6. Update your instructions from ~/desk/grok/: Desk chat webhook -> PRIMARY_COACH_SYSTEM_PROMPT.md, 20-minute news scan -> NEWS_SCAN_PROMPT.md, 4:20 PM review -> REVIEW_PROMPT.md. In your Library replace "Desk commands" with USER_QUICK_COMMANDS.md and the endpoint list with TOOL_CONTRACTS.md.
7. Main paper rules did not change. Do not change any rule or setting; I decide.
8. Reply with: the tests result, the two status lines, and "routines updated".
```

## Step 3: log in to Schwab again (you, about 1 minute)
Your stream was refused because the saved login was made before "Accounts and Trading Production" was added. On the desk: **Rules → Data sources → Reconnect (log in again)**. Log in on Schwab's site yourself, then paste the `https://127.0.0.1/?code=...` address back within 30 seconds. The page should show **Connected** and **Streaming live**.

## Step 4: check it
- My trades looks the same as before.
- **Markets:** the health line says Schwab login connected and market data live. Search a ticker (e.g. NVDA): the chart loads and the status says Live (or Market closed after hours).
- **Setups board:** during market hours it shows rows, or "No qualifying setups right now".
- Type `check once NVDA calls`: the plan shows a desk read, the entry gate state and the planned max loss.

## Rollback
Send Chart: "stop the desk server, restore ~/desk from ~/desk_backup_v31_YYYYMMDD (replace the whole folder), and restart it with watchdog.sh". v3.2 only added tables and settings, so the v3.1 code still reads the database.

## Known limits
- Not verified against the real services yet: the Schwab stream login, instrument search, the SEC feed from Chart's computer and (if you turn it on) xAI search. Those get confirmed on the first live session.
- The Oct 28 replay uses modeled option prices (Schwab has no option-quote history). It's a regression check, not proof.
- If Chart's computer sleeps or goes offline, the page, paper engine and watches stop until it's back.
- Chart answers through a webhook, so its replies take a few seconds to a minute. The plan never waits on Chart.

## Files in the zip
| File | What it is |
| --- | --- |
| `server.py` | Page + API + engine loop |
| `marketdata.py`, `schwab.py`, `schwab_stream.py` | The one data pipeline: Schwab REST and stream, freshness labels, fallback marked not executable |
| `indicators.py` | VWAP, MACD, ATR/ADX, RVOL, chop measures, volume profile (checked against TA-Lib) |
| `strategy.py` | Levels, regime, setups (incl. VWAP + MACD), conflict handling, qualification, grade |
| `optionmath.py` | Contract pick, structure stop, 20% ceiling, T1, 2:1 check, size |
| `paper.py`, `exits.py` | Simulated fills on Schwab quotes and the exit rules |
| `policy_old.py`, `config/policy_old_2026-10-28.3.json` | The frozen old rules, for comparison |
| `engine.py`, `commands.py`, `core.py`, `store.py` | Plans, paper scan, ledgers, what you type, rules, the database |
| `chartfeed.py`, `vendor/` | The desk chart's data and Lightweight Charts 5.2.1 |
| `replay.py`, `evaluation.py` | The Oct 28 replay and the forward paper test scorecard |
| `kronos_shadow.py` | Kronos forecast test (shadow only), now tagged by data source |
| `alerts.py`, `watchlist.py`, `altdata.py`, `broker.py`, `desk.py`, `chartdata.py` | Alerts, watchlist, optional Quiver data, Alpaca (watchlist quotes only), legacy reads |
| `index.html`, `index_legacy.html`, `server_legacy.py` | The page, the old page (`/legacy`), the old server |
| `config/policy.json` | The active rules (version 2026-10-29.v3) and the forward test settings |
| `grok/*` | Chart's routine prompts, rules map, quick commands, endpoint list |
| `docs/V3_REPORT.md` | What changed, what was verified, what still needs a live session |
| `docs/SCHWAB_SETUP.md` | Your Schwab steps |
| `scanner.py`, `noiseband.py`, `backtest.py`, `diagnostics.py` | v3.1: stocks-in-play scanner, noise band, multi-day backtest, diagnostics |
| `docs/V31_REPORT.md`, `docs/RESEARCH_NOTES.md` | What v3.1 does and its limits; the research behind the experiments |
| `scanner_setups.py` | v3.2: the setups board (objective setups, flags, transparent rank, coverage) |
| `entrygate.py` | v3.2: the anti-chasing entry gate (versioned setups, latest acceptable entry, missed / too extended) |
| `catalysts.py`, `earnings.py` | v3.2: catalysts with source labels and timestamps (SEC EDGAR, optional xAI, Chart's routine); earnings in phases |
| `autopilot.py`, `optionhours.py` | v3.2: scheduled paper strategies (earnings post-release, pre-event research); options market hours for fills |
| `docs/V32_REPORT.md` | v3.2: root causes, changes, what was verified, what needs a live session, provider limits |
| `tests/` | 113 offline tests (no network, no AI, fake Schwab server and stream) |
