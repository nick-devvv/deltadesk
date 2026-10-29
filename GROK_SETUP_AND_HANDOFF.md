# DeltaDesk v3: setup on Chart's computer

You do every step yourself, in Grok. Nothing here needs Claude to take over your computer. The Schwab login and the Schwab keys are yours to enter; nobody else types them.

## What changes in v3
- **Schwab is the only live data.** Candles, quotes and option prices come from Schwab (stream, or REST polling if the stream isn't available). Without Schwab the desk says **FALLBACK - not executable**: plans are marked delayed and the paper engine doesn't trade.
- **The desk chart** in the middle is drawn from the same Schwab data the engine decides on, with 1m/2m/5m candles, VWAP, EMA 9/21, MACD, levels and entry/exit marks. One click switches to TradingView.
- **New stops and targets.** The stop is the chart level that proves the idea wrong, inside a 20% premium ceiling. T1 is the next opposing level. A trade needs 2:1 on the stock move and on the option dollars. The old 20/12/10% stops are retired.
- **New exits.** Green and stalled for 10 minutes: out. Green and momentum fades or MACD crosses against: out. At T1, 2 contracts sell 1 and keep a runner only on a clean break; 1 contract sells. Breakeven and a profit lock protect winners. All out at 3:25.
- **VWAP + MACD**, one strategy. The cross arms it, the entry comes on the VWAP retest, and an early entry is allowed only in a strong trend.
- **Paper is simulated inside the desk** on Schwab quotes, with no broker and no orders. There are four ledgers kept apart: You, Main paper (4 ideas a day), Research (keeps watching after the limits) and Old rules (frozen, for comparison).
- **Everything else stays:** the chain, watchlist, journal in the chat, alerts, voice and the Kronos test (still forecast-only).

## Step 1: attach the file to Chart
Attach `deltadesk-v3.zip` (in Downloads/nicks-desk) to a new Chart chat with the message below.

## Step 2: the message to send Chart (copy all of it)

```
DESK V3 INSTALL. Do these steps on your computer, in order, and show me the output of each.
You never place real trades, never click buy/sell/order buttons, and never enter passwords or keys.

1. Back up code, settings and the journal: cp -r ~/desk ~/desk_backup_v2_$(date +%Y%m%d)
2. Unzip the attached deltadesk-v3.zip over ~/desk. Overwrite files with the same names and keep everything else, including journal/desk.db, bot.py, shadow.py, review.py, desk-state.json, config/watchlist.json, config/events.json and my Secrets. The zip has no journal folder, so my trade history is untouched.
3. pip install websockets==17.3
4. cd ~/desk && python3 -m pytest -q tests/   -> must end with "53 passed, 1 skipped". If not, stop and show me the error.
5. Restart the desk server the same way watchdog.sh starts it (same env as before). Then run:
   curl -s "http://127.0.0.1:8765/api/data/status?k=$DESK_TOKEN" | head -c 400
   and show me the output. Until I connect Schwab it says "FALLBACK - not executable". That's expected.
6. Replace your routine instructions with the files in ~/desk/grok/ (put my real DESK_TOKEN from Secrets where a file says DESK_TOKEN; never paste it in chat):
   - Desk chat webhook routine  -> PRIMARY_COACH_SYSTEM_PROMPT.md
   - 9:00 AM ET morning routine -> MORNING_ROUTINE_PROMPT.md
   - 4:20 PM ET review routine  -> REVIEW_PROMPT.md
   Keep the 20-minute news scan as it is.
7. In your Library: save ~/desk/grok/RULES_MAP_V3.md as "Desk v3 rules map" (it replaces "Desk v2 rules map"), and replace "Desk commands" with ~/desk/grok/USER_QUICK_COMMANDS.md.
8. Paper trades are now simulated inside the desk. Never run bot.py, shadow.py or anything that places an order, paper or real.
9. Later, after I've connected Schwab myself, run: cd ~/desk && python3 replay.py 2026-10-28 and send me reports/replay_2026-10-28.md.
10. Reply with: the tests result, the data status line, and "routines updated".
```

## Step 3: connect Schwab (you, about 2 minutes)
Follow `docs/SCHWAB_SETUP.md`. In short: put `SCHWAB_APP_KEY` and `SCHWAB_APP_SECRET` into Chart's Secrets yourself (reset the secret first if it was ever pasted anywhere), have Chart restart the server, then go to **Rules → Data sources → Open Schwab login** and paste the `?code=` address back within 30 seconds.

## Step 4: check it
Open your desk link (same link as before). You should see:
- the chart chip next to 1m/2m/5m saying **Schwab live** or **Schwab polling** (after Step 3);
- the Plan card showing the stop as a SPY/QQQ price, T1 as a level, and reward/risk;
- the Paper page with four ledger cards and today's decisions.

Type `check once SPY calls`. A plan, or a clear reason it isn't a trade, should appear right away.

## Rollback (if something breaks during market hours)
Send Chart: "stop the desk server, restore ~/desk from ~/desk_backup_v2_YYYYMMDD (replace the whole folder), and restart it with watchdog.sh". v3 only added tables and one column, so the v2 code still reads the database.

## Known limits
- Nothing was tested against the real Schwab servers yet: streaming login, entitlements and the real delay get confirmed on the first live session.
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
| `tests/` | 54 offline tests (no network, no AI, fake Schwab) |
