# DeltaDesk v3.3: setup on Chart's computer

You do every step yourself, in Grok. Nothing here needs Claude to take over your computer. The Schwab login and any keys are yours to enter; nobody else types them. Nothing new costs money.

## What's new in v3.3 (main paper rules unchanged; full details in docs/V33_REPORT.md)
- **Honest evidence on every plan:**
  - **No strategy is qualified.** Every setup family tested no better than random entries after costs, or only in-sample.
  - Plans show a **Research only** badge (or **Your idea** for your own levels). Chart says RESEARCH ONLY instead of ENTER.
  - Setup alerts for research-only families are quiet notes, not pings.
  - Markets → **Strategy evidence** lists all 18 tested strategies with the numbers and why.
- **The fixes from the outside audit (A–H):**
  - the gate checks both sides of the entry zone and fails closed;
  - the gated ledger judges every setup itself;
  - no look-ahead in the 2m MACD diagnostics;
  - theta in one unit;
  - the stocks backtest fills after the signal;
  - strict paper fills that respect the limit after slippage;
  - a content-keyed indicator cache;
  - session-clustered statistics.

  Each one is a new version; the old ones are kept for comparison.
- **The chart's 530 error:**
  - **What it is:** a Cloudflare tunnel error page, not a Schwab problem.
  - **On the page:** it shows one plain line and keeps the last good candles. It retries with backoff and comes back by itself.
  - **The real cause** is on Chart's computer (step 5).
- **New free X routine** (`grok/X_SCAN_PROMPT.md`): Chart searches X with its own access for earnings names, movers, setups and your trades, finds the original sources, and sends them with sentiment kept separate. If it can't search X, it says X SEARCH UNAVAILABLE.
- **Research tools:**
  - a strategy register that can't be quietly edited;
  - a router that logs every setup;
  - walk-forward folds;
  - matched random-entry controls;
  - `research.py` for the ORB15 study.

## Step 0: what costs money
Nothing new. The paid xAI search stays OFF. SEC filings are free (you already added `SEC_USER_AGENT`). The X routine uses Chart's own Grok access.

## Step 1: attach the file to Chart
Attach `deltadesk-v3.3.zip` (in Downloads/nicks-desk) to a new Chart chat with the message below. If the attachment doesn't arrive, tell Chart the file's path on your Mac and its sha256 (both in my message).

## Step 2: the message to send Chart (copy all of it)

```
DESK V3.3 INSTALL. Do these steps on your computer, in order, and show me the output of each.
You never place real trades, never click buy/sell/order buttons, and never enter passwords or keys.

1. Back up: cp -r ~/desk ~/desk_backup_v32_$(date +%Y%m%d)
2. Check the zip: sha256sum deltadesk-v3.3.zip   (must match the sha256 Nick gives you; if not, stop)
3. Unzip the attached deltadesk-v3.3.zip over ~/desk. Overwrite files with the same names and keep everything else (journal/desk.db, schwab.env, webhook.env, DESK_TOKEN.txt, watchdog.sh, bot.py, shadow.py, review.py, config/watchlist.json, config/events.json). The zip has no journal folder and no secrets.
4. cd ~/desk && python3 -m pytest -q tests/   -> must end with "140 passed, 1 skipped". If not, stop and show me the error.
5. Restart the desk with watchdog.sh. Then show me these lines (no tokens in the output):
   curl -s "http://127.0.0.1:8765/api/schwab/status?k=$(cat DESK_TOKEN.txt)" | head -c 300
   curl -s -o /dev/null -w "%{http_code} %{content_type}\n" "http://127.0.0.1:8765/api/chart?t=NVDA&tf=1&k=$(cat DESK_TOKEN.txt)"
   curl -s "http://127.0.0.1:8765/api/strategies?k=$(cat DESK_TOKEN.txt)" | head -c 300
6. The chart 530 error. Check the tunnel, without changing anything:
   pgrep -fl cloudflared || echo "cloudflared NOT running"
   grep -n cloudflared watchdog.sh
   tail -n 40 the cloudflared log watchdog.sh writes (if any), and tell me: did the trycloudflare link change today, and how many times did cloudflared restart?
   If the desk page shows a Cloudflare error, tell me the "Error 1xxx" number on it.
7. Update your instructions from ~/desk/grok/: Desk chat webhook -> PRIMARY_COACH_SYSTEM_PROMPT.md, 20-minute news scan -> NEWS_SCAN_PROMPT.md, 4:20 PM review -> REVIEW_PROMPT.md. In your Library replace "Desk commands" with USER_QUICK_COMMANDS.md and the endpoint list with TOOL_CONTRACTS.md.
8. New routine "X and earnings scan": paste ~/desk/grok/X_SCAN_PROMPT.md as its instructions, every 30 minutes on weekdays 8:00 AM-6:00 PM ET. If you can't search X, say so now.
9. After 4:00 PM ET today (or now if the market is closed), run the signal study and show me the last 25 lines:
   cd ~/desk && python3 research.py --csv reports/backtest_inplay_bars_2026-09-22_2026-10-29.csv --paths 20 | tail -n 25
   (If that file isn't there, tell me which backtest_inplay_bars_*.csv files are in ~/desk/reports.)
10. Main paper rules did not change. Do not change any rule or setting; I decide.
11. Reply with: the tests result, the three lines from step 5, the tunnel findings from step 6, "routines updated", whether you can search X, and the study output.
```

## Step 3: check it
- My trades looks the same as before. A desk setup shows a **Research only** badge; your own level shows **Your idea**.
- **Markets → Strategy evidence** shows "none qualified" and 18 strategies.
- If the chart ever says the desk couldn't be reached through the tunnel (HTTP 530), Chart's computer, or its tunnel, is down. It retries by itself. If the link changed, ask Chart for the new one.

## Step 4: what the 530 answer means
- **cloudflared not running, or Error 1033:** the tunnel is down. Chart restarts it with watchdog.sh. A quick tunnel gets a **new link** every time it restarts, so the old link shows 530 until you open the new one.
- **Error 1016:** the link points at a tunnel that no longer exists: use the newest link.
- **A link that keeps changing** is how free quick tunnels work. Cloudflare says they're for testing, with no uptime guarantee. Tell me what Chart finds and I'll give you the next step. A stable link without paying is possible, but it needs a different setup on Chart's computer.

## Rollback
Send Chart: "stop the desk server, restore ~/desk from ~/desk_backup_v32_YYYYMMDD (replace the whole folder), and restart it with watchdog.sh". v3.3 only added tables, files and settings, so the v3.2 code still reads the database.

## Known limits
- Not verified against the real services from here: the Schwab stream, instrument search, the SEC feed from Chart's computer, X access in Chart's routine, and the tunnel. Those get confirmed in step 5-9 and on the first live session.
- The backtests use modeled option prices (no option-quote history). The Sep-Oct data was used to design v3, so studies on it are diagnostic, not unseen evidence.
- If Chart's computer sleeps or goes offline, the page, paper engine and watches stop until it's back.

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
| `strategy_registry.py`, `config/specialists.json` | v3.3: every tested strategy, its spec hash, evidence and status (none qualified); the attempt log |
| `strategy_router.py` | v3.3: one route from a setup to SHADOW / REJECT / ADMIT, with shared limits across specialists |
| `walk_forward.py`, `matched_benchmarks.py`, `research.py` | v3.3: walk-forward folds, matched random-entry controls with Holm adjustment, the ORB15 signal study |
| `grok/X_SCAN_PROMPT.md` | v3.3: the free X and earnings scan routine for Chart |
| `docs/V33_REPORT.md` | v3.3: root causes with file/function, fixes, tests, what's research only, the live checks left |
| `tests/` | 141 offline tests (no network, no AI, fake Schwab server and stream) |
