# DeltaDesk v3.1: setup on Chart's computer

You do every step yourself, in Grok. Nothing here needs Claude to take over your computer. The Schwab login and the Schwab keys are yours to enter; nobody else types them.

## What's new in v3.1 (main paper rules unchanged)
- **My trades:** tell Chart what you bought (any ticker; add the expiry for non-SPY/QQQ). The desk tracks that exact contract live and says HOLD / TIGHTEN STOP / TAKE PROFIT / EXIT as things change, labels it "desk setup" or "your idea", and never lets the stop go past your 20% max planned loss.
- **Scanner page:** at 9:35 it ranks stocks in play by unusual opening volume, checks their options contract by contract, and says why names didn't qualify. Passing is a valid day.
- **Live alerts:** stocks in play, top movers through the day, quick moves on any scanned stock, scanner paper trades and changes in your trade guidance. Each one is labeled as an idea or a desk setup.
- **Research page:** three experiments on paper, each in its own ledger and kept apart from main paper: exits that let winners run, the noise-band momentum strategy and stocks-in-play breakouts. They're compared on expectancy, average win vs loss and drawdown, never win rate alone.
- **Diagnostics:** `backtest.py` runs the desk over past days and tests why the October results were bad (coin-flip baseline, exits, hold tests, stock vs option).

## What changes in v3
- **Schwab is the only live data.** Candles, quotes and option prices come from Schwab (stream, or REST polling if the stream isn't available). Without Schwab the desk says **FALLBACK - not executable**: plans are marked delayed and the paper engine doesn't trade.
- **The desk chart** in the middle is drawn from the same Schwab data the engine decides on, with 1m/2m/5m candles, VWAP, EMA 9/21, MACD, levels and entry/exit marks. One click switches to TradingView.
- **New stops and targets.** The stop is the chart level that proves the idea wrong, inside a 20% premium ceiling. T1 is the next opposing level. A trade needs 2:1 on the stock move and on the option dollars. The old 20/12/10% stops are retired.
- **New exits.** Green and stalled for 10 minutes: out. Green and momentum fades or MACD crosses against: out. At T1, 2 contracts sell 1 and keep a runner only on a clean break; 1 contract sells. Breakeven and a profit lock protect winners. All out at 3:25.
- **VWAP + MACD**, one strategy. The cross arms it, the entry comes on the VWAP retest, and an early entry is allowed only in a strong trend.
- **Paper is simulated inside the desk** on Schwab quotes, with no broker and no orders. There are four ledgers kept apart: You, Main paper (4 ideas a day), Research (keeps watching after the limits) and Old rules (frozen, for comparison).
- **Everything else stays:** the chain, watchlist, journal in the chat, alerts, voice and the Kronos test (still forecast-only).

## Step 1: attach the file to Chart
Attach `deltadesk-v3.1.zip` (in Downloads/nicks-desk) to a new Chart chat with the message below.

## Step 2: the message to send Chart (copy all of it)

```
DESK V3.1 INSTALL. Do these steps on your computer, in order, and show me the output of each.
You never place real trades, never click buy/sell/order buttons, and never enter passwords or keys.

1. Back up: cp -r ~/desk ~/desk_backup_v3_$(date +%Y%m%d)
2. Unzip the attached deltadesk-v3.1.zip over ~/desk. Overwrite files with the same names and keep everything else (journal/desk.db, schwab.env, webhook.env, DESK_TOKEN.txt, watchdog.sh, bot.py, shadow.py, review.py, config/watchlist.json, config/events.json). The zip has no journal folder and no secrets.
3. cd ~/desk && python3 -m pytest -q tests/   -> must end with "70 passed, 1 skipped". If not, stop and show me the error.
4. Restart the desk with watchdog.sh. Then show me:
   curl -s "http://127.0.0.1:8765/api/scanner?k=$(cat DESK_TOKEN.txt)" | head -c 300
5. Update your instructions from ~/desk/grok/: Desk chat webhook -> PRIMARY_COACH_SYSTEM_PROMPT.md, 4:20 PM review -> REVIEW_PROMPT.md. In your Library replace "Desk v3 rules map" with RULES_MAP_V3.md and "Desk commands" with USER_QUICK_COMMANDS.md.
6. Once Schwab is connected, run the diagnostics in the background (about 1-1.5 hours):
   cd ~/desk && mkdir -p reports && nohup python3 backtest.py --from 2026-09-22 --to 2026-10-29 > reports/backtest.log 2>&1 &
   When it finishes, send me reports/diagnostics_2026-09-22_2026-10-29.md and reports/backtest_2026-09-22_2026-10-29.md.
7. Main paper rules did not change. Do not change any rule or setting based on the results; I decide.
8. Reply with: the tests result, the scanner status line, and "routines updated".
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
| `scanner.py`, `noiseband.py`, `backtest.py`, `diagnostics.py` | v3.1: stocks-in-play scanner, noise band, multi-day backtest, diagnostics |
| `docs/V31_REPORT.md`, `docs/RESEARCH_NOTES.md` | What v3.1 does and its limits; the research behind the experiments |
| `tests/` | 71 offline tests (no network, no AI, fake Schwab) |
