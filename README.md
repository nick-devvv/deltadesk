# Nick's Desk

A personal trading command deck for 0DTE SPY/QQQ options. Deterministic code does the math, the monitoring and the paper trading. An AI coach ("Chart", a Grok agent) explains the numbers in plain words. Real-money trades are placed by hand. The system never places them.

![The deck](docs/screenshots/deck.png)
*The deck with demo data: plan, options chain, watchlist, positions and coach chat. In the live app the TradingView chart fills the middle.*

## What it does
- **Plans in code.** Each trade idea gets a full plan: trigger, invalidation, contract pick (target delta 0.45), max buy, size, stop, breakeven, T1, trail and exit times. The plan is computed from live market data before the AI says a word.
- **Live alerts.** A/B setup alerts (opening range break and retest, failed breaks, PDH/PDL retests, VWAP reclaims), alerts for two heavy 5-minute candles, and market-moving news from a 20-minute AI news scan. Each setup alert carries the full plan and only fires when the trader's own rules allow the trade. Delivered as browser pop-ups, sound and phone push (ntfy).
- **Risk rules as code.** Time-of-day stops (20% hard cap in the morning, 12% midday, 10% afternoon), a losing-streak brake (2 losses = A setups only plus a cooldown; 3 = stop for the day), no-chase and cooldown filters, event blocks around CPI/Fed releases, and all out at 3:25.
- **Paper engine.** Trades the same setups by itself in an Alpaca paper account, with breakeven, T1 and trailing-stop management, plus a kill switch.
- **Journal and learning loop.** After every trade the chat asks a short review (plan followed, mistake tags, why in and out). An end-of-day wrap fills the daily journal. The analytics break results down by setup, time of day, ticker, grade and mistake, with a P/L calendar and CSV export. A 4:20 PM review proposes lessons, which only take effect after the trader approves them.
- **Options chain view.** A Robinhood-style chain with bid, ask, mark, delta and breakeven. The desk's pick is marked, and contracts that fit the rules get a green dot. Read-only.
- **Forecast research.** Runs the Kronos time-series model in shadow mode only, scored against no-change and momentum baselines.

| Journal | Phone |
|---|---|
| ![Journal](docs/screenshots/journal.png) | <img src="docs/screenshots/phone.png" width="260"> |

## Architecture
```
Browser (single-page deck, TradingView chart)
   |  polls /api/state every 2 s, sends commands
server.py  (Python HTTP API, token-protected, exposed via Tailscale Funnel)
   |-- engine.py     plans, setup detection (ADX/RVOL/VWAP/levels), paper engine, position management
   |-- core.py       rules: market calendar, stops, sizing, exit plan, Black-Scholes delta fallback
   |-- commands.py   chat text -> actions (IN/OUT/confirm/check) handled in code, AI only for judgment
   |-- alerts.py     setup / move / news alerts with de-duplication, cooldowns and phone push
   |-- store.py      SQLite journal (WAL): positions, events, opportunities, notes, analytics
   |-- broker.py     Alpaca client, refuses anything but a paper account
   |-- schwab.py     Schwab market-data client, refuses trading and account endpoints
   `-- kronos_shadow.py  separate forecast process (shadow only)
Chart (Grok agent) <- webhook with compact context (rules, plan, 3 relevant knowledge cards)
```

## Design choices
- **Code computes, AI explains.** Standard commands never call the model, which keeps AI cost to about 20 scheduled runs a day plus questions. The model may not change any number.
- **Safety by construction.** No code path places a real-money order. The paper client checks for a paper key and account, and the Schwab client allows only market-data paths.
- **Tested.** 31 offline tests (no network, no AI, fake broker) cover stops, sizing, the streak brake, the paper engine, alerts, the journal, the chain and safety refusals.

## Stack
Python 3, SQLite, pandas/numpy, yfinance; vanilla HTML/CSS/JS with canvas animations and the TradingView widget; Alpaca and Schwab REST APIs; Grok agent routines; pytest.

## Running it
`python3 server.py` with `DESK_TOKEN`, `ALPACA_KEY`/`ALPACA_SECRET` (paper), and optionally `CHAT_WEBHOOK`, `SCHWAB_*`, `NTFY_TOPIC`, `KRONOS=1` set in the environment. Never commit keys. Tests: `python3 -m pytest -q tests/`.

Built with help from Claude (Anthropic). Credits for ideas and tools are in `docs/CREDITS.md`.
