<div align="center">

# DeltaDesk

**A quant paper-trading desk for stocks, ETFs and options.** Code computes every number, strategies reach the desk only after a pre-registered backtest, and every real trade is placed by hand.

[![tests](https://github.com/nick-devvv/deltadesk/actions/workflows/tests.yml/badge.svg)](https://github.com/nick-devvv/deltadesk/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Tests](https://img.shields.io/badge/tests-654-brightgreen)
![Paper only](https://img.shields.io/badge/execution-paper%20only-red)

<br>

<img src="docs/tour.gif" width="100%" alt="A tour of the live DeltaDesk: the SPY chart with its levels, the setups board, the rules page and the learning page">

<sub>Real screens from the running desk, after the Friday, Nov 13, 2026 session.</sub>

</div>

## Features

| | |
|---|---|
| **Desk chart**<br>SPY and QQQ from 1 to 15 minutes, with VWAP, EMA 9/21, the opening range, prior-day levels, value area and MACD. Ask for the desk's read and it gives the entry gate, what's missing and what kills the idea. | **Setups board**<br>Every qualifying setup across the market, ranked, with its level, distance in ATR, relative volume, spread, the reason it qualifies and the exact close that invalidates it. |
| **Trade plans in code**<br>Entry, a stop at the level that proves the trade wrong, a 2:1 target after spread, fees and time decay, the contract and the size, all computed before the AI says a word. | **Guidance on your own trades**<br>Report a fill on any ticker and the desk tracks that exact contract live: hold, tighten stop, take profit or exit, with the reason. |
| **Co-pilot alerts**<br>SPY and QQQ pattern alerts (sweeps, rejection wicks, VWAP, EMA, RSI), each labeled with how it did in testing. Sent to Telegram with Took / Skipped buttons. | **Market scanner**<br>At 9:35 it ranks liquid stocks by unusual opening volume, then checks their options one contract at a time: spread, quote age, open interest, delta, time decay and earnings. |
| **Rules and exits**<br>Every setup is written down; untested ones stay labeled research. Exits run in a fixed order where stops only tighten, and the desk won't chase past an entry zone. | **Options chain**<br>Bid, ask, mark, delta and breakeven, with the desk's pick marked and every contract that fits the rules flagged. The chain is saved every minute for research. |
| **Strategy lab**<br>Every strategy is scored against matched random entries, with every variant counted. Research runs on 1997–2021 data, then a sealed 2022–2025 test that runs once. | **Learning loop**<br>Skipped setups are scored by one fixed rule, open hypotheses carry pass/fail criteria set before the results, and the journal keeps a P/L calendar and lessons you approve. |
| **Ledgers and risk books**<br>Each strategy paper-trades in its own ledger and isolated risk book. Multi-day positions are sized so a 3-sigma day costs at most 1.5% of the account. | **Catalysts and earnings**<br>SEC filings, earnings dates and news are timestamped and checked against a measured price and volume reaction before a stock counts as in play. |

**Safe by design.** There is no code path to a real-money order: paper fills are simulated or on Alpaca's paper account, Schwab trading endpoints are refused in code, and `touch KILL` flattens and halts the desk. Chart, an AI agent, explains the numbers in chat but can never change them.

## On paper now

| Ledger | What it does | Held |
|---|---|---|
| `core_sso` | SSO while SPY is above its 200-day trend, T-bills (SGOV) when it isn't | Weeks to months |
| `core_spy` | SPY as the core position | Long term |
| `etf10_rsi2` | Buys short pullbacks (RSI 2) on 10 ETFs | Days |
| `pead_t21` | Post-earnings drift | 20 sessions |
| `nbs_spy_ls`, `nbs_spy_long` | Noise-band momentum on SPY shares | Same day |
| `noise` | The reference noise-band strategy on 0DTE SPY and QQQ options | Same day |

A few research-only ledgers run beside them for comparison. None is promoted yet: each needs 40 forward paper trades that match its backtest. Full rules and results: [`docs/STRATEGY_PLAN.md`](docs/STRATEGY_PLAN.md).

## How a strategy gets on the desk

1. **Written rules first:** taken from a published paper or a large backtest, frozen before any result.
2. **Two tests:** a research window (1997–2021), then a sealed 2022–2025 window, run once.
3. **Judged on profit after costs,** against matched random entries, with every variant tried counted.
4. **Paper forward test,** then promotion only if live fills match the backtest.

## Run it

```bash
pip install -r requirements.txt
python3 -m pytest -q tests/   # 654 offline tests: no network, no keys
python3 server.py             # http://localhost:8765
```

Live data needs `DESK_TOKEN` and Schwab market-data keys ([`docs/SCHWAB_SETUP.md`](docs/SCHWAB_SETUP.md)). The desk runs on its own small server, with health checks, and every push to `main` runs the tests on GitHub first.

**Built with:** Python, SQLite, Schwab and Alpaca market data, WRDS (research), TradingView Lightweight Charts, Telegram and ntfy.

---

<sub>A personal project, not financial advice. It never places a real order, and options carry a high risk of loss. Built with help from Claude (Anthropic); credits in [`docs/CREDITS.md`](docs/CREDITS.md). © 2026 nick-devvv. All rights reserved.</sub>
