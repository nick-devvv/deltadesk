# DeltaDesk v3.4: setup on Chart's computer

You do every step yourself, in Grok. Nothing here needs Claude to take over your computer. Nothing new costs money.

## What's new in v3.4 (main paper rules unchanged; full details in docs/V34_REPORT.md)
- **The strategy lab (Markets tab, new box at the bottom; your other pages keep their layout):**
  - every strategy now runs on every stock on the desk's list, every day: 15 strategy families, each with its own paper ledger;
  - every signal is recorded with its conditions (RVOL, trend, MACD, VWAP, SPY, gap, sector, earnings, and the X read known at that moment);
  - every signal gets its stock result after the close, next to random entries on the same stock and day.
- **What works where:** split by strategy, stock, stock group or any condition. Each row says how often it worked, the edge over random with a range, and whether it held in both halves of the dates. Under 30 signals = too few.
- **Nothing was marked failed.** The four "retired" items (MACD video, RVOL 2+, ADX trend, morning only) run again. The ORB15 base and retest stay drafts. Nothing is "qualified": the lab collects data; you decide later which ones move into a fresh paper run.
- **Daily bar archive** in `~/desk/journal/bars/`, so the data keeps growing past Schwab's ~30-day history.
- **Your pause button and the kill switch** cover the lab too. Lab trades stay out of your trade feed.

## Step 1: attach the file to Chart
Attach `deltadesk-v3.4.zip` (in Downloads/nicks-desk) to a new Chart chat with the message below.

## Step 2: the message to send Chart (copy all of it)

```
DESK V3.4 INSTALL. Do these steps on your computer, in order, and show me the output of each.
You never place real trades, never click buy/sell/order buttons, and never enter passwords or keys.

1. Back up: cp -r ~/desk ~/desk_backup_v33_$(date +%Y%m%d)
2. Check the zip: shasum -a 256 deltadesk-v3.4.zip 2>/dev/null || sha256sum deltadesk-v3.4.zip   (must match the sha256 Nick gives you; if not, stop)
3. Unzip the attached deltadesk-v3.4.zip over ~/desk. Overwrite files with the same names and keep everything else (journal/ and everything in it, schwab.env, webhook.env, DESK_TOKEN.txt, watchdog.sh, bot.py, shadow.py, review.py, config/watchlist.json, config/events.json, config/variants.json, variants.py). The zip has no journal folder and no secrets.
4. cd ~/desk && python3 -m pytest -q tests/   -> must end with "153 passed, 1 skipped". If not, stop and show me the error.
5. Restart the desk with watchdog.sh. Then show me (no tokens in the output):
   grep -i "strategy lab" /tmp/desk*.log 2>/dev/null | tail -1    (or wherever watchdog.sh writes the server log)
   curl -s "http://127.0.0.1:8765/api/lab?k=$(cat DESK_TOKEN.txt)" | head -c 400
6. Wait 10 minutes, then run the /api/lab line again and tell me "with_history" and "last_error".
7. Your routines read their prompts live from ~/desk/grok, so the coach and the 4:20 PM review are on the v3.4 text now. In your Library, update "Desk commands" from USER_QUICK_COMMANDS.md and "Desk endpoints" from TOOL_CONTRACTS.md.
8. After 3:31 PM ET, run:
   curl -s "http://127.0.0.1:8765/api/lab/report?by=strategy&k=$(cat DESK_TOKEN.txt)" | head -c 600
   After 4:06 PM ET: ls ~/desk/journal/bars/$(date +%Y-%m-%d) | wc -l
9. Main paper rules did not change. Do not change any rule or setting; I decide.
10. Reply with: the tests result, the lab lines from steps 5, 6 and 8, and "routines updated".
```

## Step 3: check it
- My trades looks the same as before. Nothing new pings you.
- **Markets → Strategy lab:**
  - the status says "recording" during market hours;
  - the symbol count is about 127, with "with prior-day history" climbing after 7 AM ET;
  - the 15 lab ledgers are listed.
- **"What works where"** fills in after 3:31 PM ET. For the first weeks almost every row is grey ("too few"). That's expected: it needs about 30 signals per row.

## Rollback
Send Chart: "stop the desk server, restore ~/desk from ~/desk_backup_v33_YYYYMMDD (replace the whole folder), and restart it with watchdog.sh". v3.4 only added tables, files and settings, so the v3.3 code still reads the database.

## Known limits
- Not verified against the real services from here: the morning history pull from Schwab, CPU use on Chart's computer (about 5 seconds a minute expected), and the archive written after the close. Steps 5, 6 and 8 check them.
- Quiet stocks refresh about every 6 minutes on the board. Their signals still get a stock result but are too late to paper trade. That's honest, and it means fewer lab paper trades on quiet names.
- If Chart's computer sleeps or goes offline, the page, paper engine, lab and watches stop until it's back. The lab catches up on missed bars, but those signals are tape-only.

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
| `lab.py`, `config/sectors.json` | v3.4: the strategy lab (signal tape, 15 lab paper ledgers, what works where, daily bar archive) |
| `docs/V34_REPORT.md` | v3.4: what the lab does, costs, limits, live checks |
| `tests/` | 154 offline tests (no network, no AI, fake Schwab server and stream) |
