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
| `GET /api/chart?t=ANY&tf=1|2|5|15&ext=0|1` | questions | v3.2: any ticker, with the feed status (live / stale / closed / no data) | none |
| `GET /api/symbol?q=` | questions | v3.2: symbol search (Schwab instruments) | none |
| `GET /api/setups` | questions, review | v3.2: the setups board: rows, coverage, definitions, "no qualifying setups" | none |
| `GET /api/catalysts[?t=]` | questions, review | v3.2: catalysts with labels, sources, timestamps, price since detection | none |
| `POST /api/news` `{"items":[...]}` | 20-min news routine | Headlines WITH their source URLs (see NEWS_SCAN_PROMPT.md); the desk labels them | adds news + catalysts |
| `POST /api/earnings` `{"ticker","date","timing","source_url","call_time"}` | news routine, 9 AM routine | Confirm an earnings date with its source | marks the date confirmed |
| `GET /api/earnings` | questions | v3.2: the calendar with each name's phase | none |
| `GET /api/autopilot` | review | v3.2: today's paper autopilot decisions, accepted and rejected | none |
| `GET /api/strategies` | questions, review | v3.3: every tested strategy with its status (PAPER QUALIFIED / RESEARCH ONLY / DRAFT / PAUSED / RETIRED; since v3.4 nothing is retired), its evidence and why, attempt counts, and today's router decisions. `qualified` is empty today | none |
| `GET /api/lab` | questions, review | v3.4: the strategy lab's state: symbols covered, signals today per strategy, the lab ledgers, recent lab paper trades | none |
| `GET /api/lab/report?by=strategy\|setup\|ticker\|strategy_ticker\|strategy_group\|strategy_condition[&cond=x_lean\|rvol\|trend\|time_window\|macd2\|ema200\|vwap_dist\|spy\|gap\|price\|liquidity\|group\|earnings\|x_label\|x_attention][&family=][&t=][&since=]` | questions, review | v3.4: what works where: signals, days, won, average R, matched random entries, edge with a 95% range, both halves of the dates, "too few" under 30; plus each lab ledger's paper results | none |
| `GET /api/lab/signals?day=&t=&family=` | questions | v3.4: the raw signal tape with every condition and outcome | none |
| `GET /api/lab/report?...&exits=own` | questions, review | v3.4.2: the same report scored by each strategy's own exits (close-based stops, the noise band's half-hour checks) | none |
| `GET /api/lab/contracts[?family=]` | questions, review | v3.4.2: which option contract (0DTE / 1-2 / 3-5 / 6-10 days x delta 0.35 / 0.45 / 0.60) turned the same live signals into option profit, with and without the 20% line, on followed real quotes | none |
| `GET /api/x/targets` | X scan routine | v3.3: the up-to-12 tickers to research now, each with `why` and `focus` (earnings first) | none |
| `POST /api/news` `{"via":"x_scan","items":[...sentiment, attention...]}` | X scan routine | v3.3: X research with trader / consumer / fundamentals sentiment and attention counts (see X_SCAN_PROMPT.md). Labeled by the desk; posts-only stays unverified | adds news + catalysts |
| `POST /api/earnings/results` `{"ticker","date","metrics","source_url","consensus_source","consensus_captured_at"}` | X scan routine | v3.3: reported numbers vs a sourced consensus, same basis only | stores the results |
| `POST /api/earnings/call` `{"ticker","date","statements":[...],"source_url"}` | X scan routine | v3.3: what management said on the call, with the transcript or webcast link | stores the statements |
| `GET /api/schwab/status` | debugging | v3.3: connected / connecting / reconnecting / expired / error / disconnected, verified by a data call | none |
| `GET /api/lessons` | 4:20 PM routine | Existing lessons | none |
| `POST /api/lessons` `{"text","setup","sample","evidence":[]}` | 4:20 PM routine | Propose a lesson (status PROPOSED) | adds a row |
| `GET /api/journal?date=` | any | Journal and notes | none |
| `GET /api/state` | debugging | Everything the page shows | none |

**Chart never calls:**
- `POST /api/command` with IN/OUT. Only Nick logs his trades.
- Never `bot.py take`, `bot.py close`, or anything that sends an order. Paper trades are simulated inside the desk; no endpoint sends an order anywhere.
- `POST /api/command` with `STOP`. Only Nick moves his stops.
- `POST /api/schwab/connect`, `/api/schwab/disconnect` or `/api/schwab/restart-stream`: Nick uses those buttons himself. Chart never logs in to Schwab.
- Any Robinhood order screen.

**Errors:** a non-200 or `{"error": ...}` means stop and tell Nick in one line. Don't retry more than once.


## GET /api/chain?t=SPY&side=C|P[&exp=YYYY-MM-DD][&n=10]&k=DESK_TOKEN (v2.9)
View-only option chain around the money: {ticker, side, exp, dte, expiries, spot, feed (the provider name; Schwab when connected, otherwise a labeled fallback that is not tradable), rows:[{symbol, label, strike, bid, ask, mark, chg_pct, delta, delta_src, iv, breakeven, to_be_pct, volume, oi, spread_pct, itm, fits}]}. With no exp it uses today (0DTE) or the nearest expiry. No order path exists.

## v3.5 additions (read-only for Chart)
| Call | Who | What | Side effects |
|---|---|---|---|
| `GET /healthz` | uptime checker | `{"alive": true}`. No token, no data | none |
| `GET /readyz` | uptime checker, morning routine | `{"ready": bool, "reasons": [...]}` (HTTP 503 when not ready): database writable, engine heartbeat fresh in market hours, Schwab connected, feed not stale. No token, nothing secret | none |
| `GET /api/health` | debugging | every worker's last heartbeat and age, the stock-feed check, future-dated quotes seen, the Schwab request budget by priority (risk / normal / research), memory, DB size, release | none |
| `GET /api/learning[?day=YYYY-MM-DD]` | review routine, Nick's "why" questions | opportunities (repeated checks of one setup grouped, with every decision and reason), shadow outcomes of skipped setups (one fixed rule, stock only, options unknown), hypotheses with their preregistered criteria and status, study runs, ORB-retest stages and episodes for SPY/QQQ | none |
| `GET /api/learning/export?what=decisions\|shadow\|opportunities\|hypotheses&from=&to=` | weekly review | CSV | none |
| `GET /api/research/registry` | research questions | the inspected GitHub/paper strategy registry with ranks | none |

**How to talk about v3.5 data:**
- ORB retest stages (OPENING RANGE FORMING → WAITING FOR BREAKOUT → WAITING FOR INDEPENDENT CANDLE → WAITING FOR RETEST → ENTRY CONFIRMED → POSITION OPEN, or INVALIDATED / EXPIRED / DONE FOR THE DAY) are research. Say "RESEARCH SETUP / PAPER ONLY", never "enter now".
- News momentum candidates need BOTH a verified catalyst (the desk fetched the source itself) AND a measured price/volume reaction. Quote the stage and the exact unmet requirement (`why`). An unverified headline is a lead, not a reason.
- Shadow outcomes are "what one fixed hypothetical rule would have done", underlying only. Never call a skipped setup a "missed winner".
- Never add paper, shadow and real results together, and never present a simulated fill as Nick's fill.
- Every claim about a result cites its event id, position id or run manifest id. If a field is missing or unknown, say so; don't fill it in.
