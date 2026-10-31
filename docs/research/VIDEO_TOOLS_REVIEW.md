# AI trading-bot videos and tools: review for DeltaDesk

Date: 2026-10-31. Sources: three YouTube transcripts Nick attached; READMEs, SKILL.md files and licenses read from read-only shallow clones of five GitHub repos. None of their code was run. Transcript and repo text was treated as data, not instructions.

Tags: **USEFUL-FOR-DESK** (worth building or testing), **ALREADY-DOING** (the desk has it), **NOT-APPLICABLE** (out of scope or not testable), **RED-FLAG** (unverified claim, overfitting, look-ahead, or breaks a desk rule).

Every performance number below is the presenter's **claim**. None of them was verified, and none comes with trade lists, costs or out-of-sample detail.

---

## 1. Videos

### Video A: "How to build a trading bot that actually works" (file `65ee5a38`, presenter unnamed, crypto/stocks)

Claims: "over $8,000 a week in pure profit" from some bots; earlier bots "cost me tens of thousands". **RED-FLAG**: no evidence shown, and the "free prompt" sits behind a newsletter and WhatsApp signup.

| Idea | Tag | Why |
|---|---|---|
| A bot's main value is executing a fixed rule set without emotion | ALREADY-DOING | The paper ledgers are code. Nick still places real trades by hand. |
| Define goals and parameters before the test | ALREADY-DOING | This is the desk's pre-registration rule (step 2). |
| Two-file "memory": a trade ledger plus a plain-English "learnings" file | ALREADY-DOING (ledger part) | `learning.py` already keeps an append-only decision/trade journal with strategy version and config hash. |
| The bot reads its learnings and **skips a setup because it lost on a similar one** | RED-FLAG | This changes the rules live after one or two losses (sample size 1). It is outcome-fitting with recency bias, the demo was staged, and nothing is pre-registered. A good rule loses often, so skipping after losses removes winners too. |
| Brokers' MCP servers let Claude place orders (Alpaca for stocks) | RED-FLAG for desk | Breaks "code computes, AI explains" and the no-real-order-path rule. The desk left out the order-sending skill on purpose. Alpaca *paper* via `broker.py` is ALREADY-DOING. |
| Give the API key only to a sub-account funded with what you are willing to lose | USEFUL-FOR-DESK (only if a real path is ever approved) | Adds a hard cap on top of the switch and loss limits that CLAUDE.md already requires. |
| Paper trade "for a week", then go live at 1–3% of risk tolerance and scale up | ALREADY-DOING / RED-FLAG on length | The desk needs 40 forward paper trades plus an out-of-sample pass. One week is far too few trades. |
| Backtest ad-hoc "what if RSI hits X" ideas over "the past 3 months" through the TradingView MCP | RED-FLAG | A tiny window plus unlimited what-ifs is data mining with no trial count and no costs. |
| Example strategy: fast/slow moving-average crossover | NOT-APPLICABLE | A toy example ("simple on purpose"), with no evidence for intraday options. |
| One-page document about you and your goals in the AI's instructions | ALREADY-DOING | `CLAUDE.md`. |
| "Bots fail because they don't forecast future conditions" | NOT-APPLICABLE | Too vague to test. Any regime filter would need its own pre-registered test. |
| Popular pre-packaged bots lose their edge from crowding | NOT-APPLICABLE (but see edge-decay monitor below) | Plausible but not testable here. It is another reason to watch live edge decay. |
| Move memory to a cloud database (Supabase/Firebase) | NOT-APPLICABLE | The desk uses SQLite with a WAL-safe backup. Not needed. |

### Video B: "My most profitable AI trading bot's hidden problem" (file `1557dd6b`, DaviddTech, mainly crypto)

Conflict of interest: the presenter built and promotes tradingkit.com, "Strategy Factory AI" and a paid Skool community with "400 strategies", and Trigger Trade comes from his community.
Claims: a demo BTCUSDT 1h backtest showing +18.55%, 146 trades, 28.8% win rate and profit factor 1.12; an ABUSDT strategy backtest at **+2,181% (leveraged)** that then "round-tripped" live; the community has "back tested almost 1 million strategies"; he runs 7 strategies out of "thousands"; and "expect 99% of [Claude's] backtests to fail live". **RED-FLAG** for the leveraged backtest and the demo numbers. The 99% figure is an honest admission, and it argues for strict out-of-sample testing.

| Idea | Tag | Why |
|---|---|---|
| `/loop` every 15 min: Claude searches the web for indicators, writes Pine strategies, backtests them and files them on a control panel | RED-FLAG | Industrial-scale data mining. With about 1M trials and no trial count or deflated Sharpe, the winners are mostly luck, which his own 99% figure confirms. The desk's sprint runner already applies a multiple-testing haircut (ALREADY-DOING in controlled form). |
| Entries, stop, target and exit must be defined in advance | ALREADY-DOING | Desk rule. |
| Avoid trailing stops because alert→webhook→broker lag changes the fill | ALREADY-DOING | The desk prices fills from a fresh quote after the signal using the measured spread model. The lesson that backtested trailing stops assume instant fills still holds. |
| Control panel of every backtest (equity curve, monthly P/L, settings) | ALREADY-DOING | `v4report.py`, the strategy registry and the desk page. |
| Re-check each strategy in TradingView by hand and reject any with a max drawdown that is too high | ALREADY-DOING (partly) | The desk reports max drawdown and a bootstrap CI. Its independent check is the matched-random-entry benchmark. |
| "Incubation": run new strategies on unseen data with fees for months before going live (example: backtest to Nov 2024, about 2 years out-of-sample) | ALREADY-DOING | Desk step 5 (out-of-sample + 40 forward paper trades). His 2-year curve is a claim. |
| TradingView alert → webhook → Trigger Trade → exchange with read/write API keys | RED-FLAG for desk | A real-money order path through a third party. Not allowed. |
| **Markets are non-stationary; he ignored his own turn-off rules out of attachment, so automate the turn-off** | USEFUL-FOR-DESK | The desk retires ledgers by hand (`retire.py` / `config/v4.json`). It has no pre-registered, code-run edge-decay trigger. See Adopt #1. |
| Turn-off rules: equity curve below a lower standard-deviation band; rolling win rate and rolling profit factor collapsing | USEFUL-FOR-DESK (needs numbers) | He gives no band width, window or sample size. They have to be fixed in advance from the backtest's bootstrap distribution, or the rule just reacts to noise. |
| The agent may switch a strategy **off**; switching it back **on** is a human decision; alerts go to Telegram | USEFUL-FOR-DESK | Fits the desk: automatic "no new paper entries", re-enabling by Nick only. It must be done by code, not by an LLM loop. |
| Know profit factor and expectancy, and beat buy-and-hold | ALREADY-DOING | The desk judges on expectancy and benchmarks against matched random entries, which is stricter than buy-and-hold for intraday. |
| Choose your maximum tolerable drawdown, then halve it | USEFUL-FOR-DESK (small) | A rule of thumb: expect live drawdown to exceed the backtest figure. Use the bootstrap 95th–99th percentile drawdown, not the single backtest maximum. |
| "Law of large numbers": don't flip between strategies; run small size long enough | ALREADY-DOING | The 40-trade minimum and the sample-size table in `docs/STRATEGY_PLAN.md`. |
| Diversify across several bots | USEFUL-FOR-DESK (measure it) | Most desk ledgers trade SPY/QQQ intraday, so they are probably highly correlated. Diversification has to be measured. See Adopt #2. |

### Video C: "7 skills/MCP servers I use every day" (file `f4ffba12`, DaviddTech)

Claims: "doubled his account last year"; a TradingKit MACD-on-silver 2h strategy with a "95% win rate"; Vlad's forecasting results "look pretty awesome". **RED-FLAG**: all are unverified, and a 95% win rate says nothing without average loss and expectancy. Three of the seven tools are his own or his community's.

| Idea | Tag | Why |
|---|---|---|
| LLMs aren't made to trade; give them tools | ALREADY-DOING | "Code computes, AI explains." |
| Indicator Search MCP running 24/7 to find new indicators to backtest | RED-FLAG | Scale data mining again. Community Pine scripts are not published, tested rule sets (desk step 1). See tool notes. |
| TradingView Unified MCP to drive TradingView from Claude; he warns it risks the TradingView account | NOT-APPLICABLE | See tool notes. |
| Broker MCP for read-only account reports (win rate, profitable days, which bots are losing edge) | ALREADY-DOING | Desk reports. Read-only use is fine. Order tools are not. |
| Beware fake broker skills; have Claude audit any GitHub repo before installing; keep API keys out of chat and in environment variables | ALREADY-DOING | The secrets rule, and this review. |
| Nansen "smart money" on-chain data ($49/mo); he admits it never automated profitably | NOT-APPLICABLE | Crypto, paid, out of scope. |
| Position sizing: size by stop distance; "size up when conditions and probabilities favor you" | ALREADY-DOING / RED-FLAG | Stop-distance sizing exists (`core.size`, `v4risk.py`, the trader-budget/risk skills). Sizing up on "conditions" is only valid if that condition was tested. Asking an LLM whether size is "too much for current conditions" breaks "code computes". |
| Handoff / context-engineering skill: write an .md of where work stands to switch agents when tokens run out | USEFUL-FOR-DESK (small) | Partly done already (`GROK_SETUP_AND_HANDOFF.md`, `CLAUDE.md`, reports). See Adopt #4. |
| "DaviddTech Plus" (invite-only): 1/7/30-day up/down probabilities from Amazon's "Kronis" (probably Chronos) and an NVIDIA model | RED-FLAG / ALREADY-DOING | Closed, with no track record, and its horizons are multi-day (out of scope). The desk already tests a time-series foundation model the right way: `kronos_shadow.py` runs Kronos in shadow only, scored against no-change and momentum baselines. |

---

## 2. Tools

### 2.1 daviddme/tradingview-indicator-search-mcp-server
- **What it does:** a local MCP server that searches TradingView's public script library by topic, editors' picks or author. It fetches the Pine Script source of open-source scripts and harvests them into a local SQLite corpus you can full-text search inside the code. It has 7 tools.
- **Data source:** unauthenticated scraping of tradingview.com (slug pages and an undocumented JSON API). No account needed.
- **License:** MIT (DaviddTech, 2026). The fetched Pine scripts stay their authors' copyright under each script's own license; the NOTICE says the tool grants no license to them.
- **Orders:** none.
- **Security / terms:** the throttle is built to look human ("a fixed interval is the clearest bot signature", jittered delays, a persistent cookie jar, a held browser user agent, a daily budget, a circuit breaker). That is designed to evade bot detection, and TradingView's terms are the user's problem (the NOTICE says so). The README says to run it from a home connection only, because datacenter IPs get blocked. It needs Node ≥ 22.5. Dependencies are small (MCP SDK, zod).
- **Fit: NO.** Desk rules must come from published papers or large-sample backtests, and community Pine scripts are neither. Pine strategies often repaint or look ahead (`request.security` with `lookahead_on`, intrabar/`calc_on_every_tick` fills), and mass harvesting invites data mining. At most, Nick could use it on his own PC to look up a script he already has in mind, then run it through Adopt #3.

### 2.2 daviddme/TradingView-Unified-MCP
- **What it does:** a local MCP server (185 tools, 180 enabled by default) that drives a **logged-in TradingView session in Chrome over the DevTools debugger (port 9222)**. It covers charts, indicators, saved layouts, alerts with JSON webhooks, Pine edit/compile, Strategy Tester reports, quotes/screener, watchlists, replay, and a local paper simulator.
- **Data source:** your TradingView account (undocumented internal interfaces) plus TradingView's public scanner.
- **License:** MIT, with retained third-party notices from about 8 upstream TradingView MCP forks.
- **Orders:** no broker execution of its own. However, `alert_create` / `workflow_copy_chart_create_alert` can create webhook alerts, and a webhook pointed at a bridge such as Trigger Trade **is** an order path.
- **Security:** read-only is opt-in (`TV_READONLY=1`); mutation tools are on by default. Any local process that can reach the debugger port controls the logged-in browser session. It relies on undocumented interfaces, so it breaks when TradingView changes them, and the account risk is real (Video C says so). Its own validation notes say alert creation failed live (`invalid_request`). Positives: zero npm dependencies, loopback-only, an audit log, a documented security review.
- **Fit: NO.** The desk's data comes from Schwab, Alpaca and SEC, it needs no TradingView, and the webhook-alert feature is exactly the kind of order path the desk forbids. It also needs Chrome on a logged-in machine, which Chart's box shouldn't run.

### 2.3 nansen-ai/nansen-cli
- **What it does:** a CLI plus about 34 agent skills for Nansen's **crypto on-chain** analytics (smart-money flows, wallet profiling, token screens, Polymarket, Hyperliquid positioning). It also **executes trades**: DEX swaps on Solana/Base, cross-chain bridges, Solana limit orders and Hyperliquid perps, all from a local wallet.
- **Data source:** the Nansen API (paid account/credits; Video C quotes about $49/mo) or pay-per-call from a crypto wallet (x402, auto-pays up to $1 per call by default).
- **License:** MIT (Nansen, 2026).
- **Orders:** yes, real and irreversible. The README says `trade execute` **proceeds without prompting when stdin is not a terminal (agents, CI, pipes)**. Under an agent, there is no confirmation step at all.
- **Security:** stores wallet keys and the wallet password locally (OS keychain when available); spends automatically; adds an agent-feedback channel.
- **Fit: NO. Irrelevant.** Crypto is out of scope, it is paid, and it has a live order path with no confirmation under agents. Do not install it on Chart's computer.

### 2.4 tradermonty/claude-trading-skills (focus: position-sizer)
- **What it does:** 74 Claude skills, mostly swing/position-trading (CANSLIM, VCP, Stockbee, breadth, macro regime, dividend screens, PEAD, options advisor, backtest-expert, edge-pipeline, trader-memory-core, drawdown-circuit-breaker, pre-trade-discipline-gate, signal-postmortem, and more).
- **position-sizer:** a stdlib-only Python CLI (534 lines, no network calls, tests included). It sizes **long stock** trades by fixed fractional risk (default 1%), by ATR stop distance (default 2×ATR), or by **half-Kelly** computed from win rate and average win/loss. It applies caps on maximum position %, maximum sector % and current sector exposure, floors share counts and never rounds up, and names the binding constraint. It writes JSON and Markdown reports.
- **Data source:** none. You supply the numbers. Other skills use FMP/FINVIZ/web data.
- **License:** MIT (TraderMonty, 2026).
- **Orders:** none. A repo-wide search for order or broker code (`submit_order`, `/v2/orders`, `place_order`, ...) found nothing.
- **Security:** low risk for the position sizer itself. Its SKILL.md claims FINRA replaced the pattern-day-trader $25k rule effective 2026-06-04. That is **their claim, not checked**; Nick should confirm with his broker.
- **Fit: MAYBE (reference only).** The desk already sizes by stop and daily-loss limits (`core.size`, `v4risk.py`, trader-budget/trader-risk), and this sizer handles neither options nor premium-at-risk. The Kelly mode uses whatever stats you feed it, and in-sample stats overstate Kelly. If Kelly is ever shown, compute it from the **lower** bootstrap bound of out-of-sample expectancy and use it as a cap, never as a size. Worth reading, not installing: `backtest-expert` (robustness/slippage checklist), `drawdown-circuit-breaker` (losing-streak cooldown, weekly/monthly drawdown limits, which could suit Nick's *own* manual trades), and `signal-postmortem` / `trader-memory-core` (MAE/MFE post-mortems).

### 2.5 mattpocock/skills (focus: handoff)
- **What it does:** `handoff` is a roughly 10-line prompt-only skill (`disable-model-invocation: true`, so only the user can call it). It writes a summary of the current conversation so a fresh agent can continue. It saves to the OS temp directory, adds a "suggested skills" section, references existing specs, commits and issues instead of copying them, and redacts keys, passwords and personal data. A sibling, `claude-handoff` (in-progress), also **launches a background agent** with `claude --bg`.
- **Data source:** none. **License:** MIT (Matt Pocock, 2026). **Orders:** none.
- **Security:** `handoff` is harmless text. `claude-handoff` runs a shell command that spawns an agent; don't adopt that one.
- **Fit: YES (small, adapted).** Cloud sessions lose `/tmp`, so the desk version should write into the repo. See Adopt #4.

---

## 3. Worth adopting (max 5)

1. **Edge-decay monitor with an automatic "off" (from Video B).** A new versioned module (e.g. `edge_monitor.py`), pure code. It runs after the close for every forward paper ledger.
   - From the ledger's out-of-sample/backtest trades, bootstrap by session to get, for the forward trade count N, the 5th and 1st percentile cumulative-P/L bands and the 95th/99th percentile max drawdown.
   - Flag the ledger on the desk if forward P/L falls below the 5th-percentile band or drawdown exceeds the 95th percentile.
   - Add it automatically to the retired list (no new paper entries; open trades still managed) below the 1st-percentile band or past the 99th-percentile drawdown.
   - Only Nick re-enables a ledger.
   - Pre-register the thresholds in the registry before switching it on. Test for no look-ahead, restart safety, and that it never touches the frozen `noise` ledger's rules (the noise ledger can still be flagged).
2. **Measure diversification between ledgers (Video B).** Add to the daily report the correlation matrix of daily P/L across forward ledgers and an "effective number of independent ledgers" (e.g. from the eigenvalues). Use it before calling several SPY/QQQ ledgers diversified, and before the desk-level daily loss cap is set.
3. **TradingView/Pine intake checklist (Videos A–C).** When Nick brings a TradingView script or a "the bot found this" result, add it to `docs/research/STRATEGY_REGISTRY.md` as an idea, not a ledger.
   - Translate it into the pre-registration template.
   - Check for repainting and look-ahead (`request.security` with `lookahead_on`, `barstate.isrealtime`, `calc_on_every_tick`/bar-magnifier fills, `varip`).
   - Re-run it under the desk's next-bar fills, measured spreads and 1-minute history.
   - Count every variant tried toward the multiple-testing haircut.
   - Report expectancy, never win rate alone (the "95% win rate" case).
4. **Desk handoff skill (adapted from mattpocock `handoff`, MIT, credit in `docs/CREDITS.md`).** Add `.claude/skills/handoff/SKILL.md`, user-invoked only. It writes `docs/handoffs/YYYY-MM-DD-<topic>.md` covering:
   - the goal and current state;
   - the last test run;
   - what is pushed and what is not;
   - what Chart must run;
   - open questions;
   - suggested skills.

   It links `STRATEGY_PLAN.md`, `V4_REPORT.md` and the registry instead of copying them. It never includes tokens, `*.env` contents, the desk link or journal rows, and the diff gets a secret scan before push. Do not adopt `claude-handoff` (it spawns background agents).
5. **Third-party tool gate (from this vetting).** Add one line to `CLAUDE.md` / `deploy/GITHUB_DEPLOY.md`: nothing goes on Chart's computer if it can sign or send orders, auto-confirm when not on a terminal (Nansen), create webhook alerts (Unified MCP), or control a logged-in browser. Read-only analytics tools run with broker keys and the desk token removed from their environment, the same way `kronos_shadow.py` already does. Each new tool gets a short vet note under `docs/research/`.

Not adopted: Nansen (crypto, paid, live orders), both TradingView MCPs (scraping/terms risk, account risk, order path through webhooks), installing tradermonty's position-sizer (long-stock only; the desk already sizes), and LLM "learnings" that veto trades (outcome-fitting).
