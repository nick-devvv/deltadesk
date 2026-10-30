# Desk endpoints Chart may call

Base: `http://127.0.0.1:8765` on Chart's computer. Add `?k=DESK_TOKEN` (or `&k=` when there's already a query). Chart reads `DESK_TOKEN` from its Secrets; it is never pasted into chat.

| Call | Who | Purpose | Side effects |
| --- | --- | --- | --- |
| `POST /api/reply` `{"reply": "..."}` | Desk chat webhook | Deliver the answer to Nick | adds a CHART message |
| `GET /api/read?t=SPY,QQQ` | 9 AM routine, questions | Levels, VWAP, EMAs, 200s, trend, chop, RVOL | none |
| `POST /api/events` `{"date","events":[{"time":"HH:MM","name"}]}` | 9 AM routine | Today's scheduled releases. The engine blocks entries ±15 min around each. | writes config/events.json |
| `GET /api/review[?date=]` | 4:20 PM routine | Day summary kept apart by ledger: `real`, `paper` (main), `research`, `old` (frozen old rules), plus `candidates` (every setup with its decision and reasons) | none |
| `GET /api/candidates[?date=&portfolio=paper|research]` | review, questions | Every setup the engine saw: evidence, decision (ORDER, SKIP, BLOCKED-LIMIT, SKIP-CONFLICT), reasons, plan numbers | none |
| `GET /api/portfolios[?since=]` | review | 30-day results per ledger: trades, win rate, expectancy, profit factor, small-sample flag | none |
| `GET /api/chart?t=SPY&tf=1|2|5` | questions | The desk chart's data: candles, VWAP, EMAs, 2m MACD, levels with sources, markers, the decision snapshot | none |
| `GET /api/data/status` | questions, debugging | Schwab stream/REST/fallback mode, last message age, reconnects, latency | none |
| `GET /api/scanner[?date=]` | questions, review | Today's stocks-in-play ranking: every number, the contract checked, why names didn't qualify, scanner alerts | none |
| `GET /api/research[?since=]` | 4:20 review | Every paper ledger side by side (main, research, v3.1 exits, noise band, stocks in play, old rules, you): expectancy, avg win/loss, drawdown, sample size, stock move vs option, exit reasons | none |
| `GET /api/diagnostics` | review | The latest backtest diagnostics (coin flip, exits, hold tests, halves) | none |
| `GET /api/evaluation` | review | The forward paper test against its fixed criteria | none |
| `GET /api/lessons` | 4:20 PM routine | Existing lessons | none |
| `POST /api/lessons` `{"text","setup","sample","evidence":[]}` | 4:20 PM routine | Propose a lesson (status PROPOSED) | adds a row |
| `GET /api/journal?date=` | any | Journal and notes | none |
| `GET /api/state` | debugging | Everything the page shows | none |

**Chart never calls:**
- `POST /api/command` with IN/OUT. Only Nick logs his trades.
- Never `bot.py take`, `bot.py close`, or anything that sends an order. Paper trades are simulated inside the desk; no endpoint sends an order anywhere.
- `POST /api/command` with `STOP`. Only Nick moves his stops.
- Any Robinhood order screen.

**Errors:** a non-200 or `{"error": ...}` means stop and tell Nick in one line. Don't retry more than once.


## GET /api/chain?t=SPY&side=C|P[&exp=YYYY-MM-DD][&n=10]&k=DESK_TOKEN (v2.9)
View-only option chain around the money: {ticker, side, exp, dte, expiries, spot, feed (the provider name; Schwab when connected, otherwise a labeled fallback that is not tradable), rows:[{symbol, label, strike, bid, ask, mark, chg_pct, delta, delta_src, iv, breakeven, to_be_pct, volume, oi, spread_pct, itm, fits}]}. With no exp it uses today (0DTE) or the nearest expiry. No order path exists.
