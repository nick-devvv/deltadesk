# Sprint run on Chart's computer: the first question (ORB exits)

This runs the sprint's first backtest (`sprint/specs/orb_exits_v1.json`, 195 runs) on Chart's computer, the only machine that can reach Alpaca's data API. Everything runs in its own folder, `~/sprint`, from branch `sprint/exits`. Nothing touches `~/desk`, its journal or the live desk, and nothing can place an order: the puller only reads `data.alpaca.markets` (market data), and the engine only reads files it pulled.

## What to expect

| Step | Time (estimate) | Disk |
| --- | --- | --- |
| Clone + venv + sprint tests | 2-5 min | about 300 MB (venv) |
| Pull SPY, QQQ, IWM, 2024-08-01 to 2026-06-30: stock bars 04:00-20:00 ET and 0DTE option bars within ±3% of the open | 30-60 min (about 3,000-4,000 requests under the 200/min free-plan limit) | 0.5-1.5 GB |
| Run the spec (195 runs, then robustness on the top 5) | 10-30 min, under 2 GB of memory | about 20 MB of results |

Estimates come from timing the engine on synthetic data of the same shape (195 runs over 120 symbol-sessions took 30 s here; the real run has 1,440 symbol-sessions and longer trades). The pull is resumable: if it stops, run the same command again and it continues where it left off.

The run uses the pre-registered cost model: a half-spread of **5% of the premium** on every fill (MODELED-SPREAD), because the desk's chain logs (which would give MEASURED-SPREAD) only start on 2026-11-02 and don't cover the development period. Option trades (for exact stop fills) are optional and not part of this first run; without them a stop that trades through inside a minute fills at the stop price, and a stop gapped through fills at the next bar's open.

## Message for Chart (one paste)

```
Sprint backtest (research only, about 1-1.5 hours in total). Show me every output.
Rules: you never place trades, never click buy/sell/order buttons, never enter passwords or keys, never print a key.
Never touch ~/desk: don't cd into it, don't edit, copy, restart or run anything there. Never pass --locked or --frozen to any command.
If a step fails, show the error and stop. Don't change any code; re-running the same command once is fine (the pull resumes).
1. Code in its own folder:
   if [ -d ~/sprint/.git ]; then git -C ~/sprint fetch -q origin sprint/exits && git -C ~/sprint checkout -q sprint/exits && git -C ~/sprint reset -q --hard origin/sprint/exits; else git clone -q --branch sprint/exits https://github.com/nick-devvv/deltadesk.git ~/sprint; fi
   cd ~/sprint && git log -1 --oneline
2. Python environment just for the sprint, then its tests:
   cd ~/sprint && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python -m pytest -q tests/test_sprint_*.py 2>&1 | tail -3
   (if python3 -m venv fails, stop and tell Nick; do not pip install anything outside ~/sprint/.venv)
3. Alpaca key check (prints only yes/no):
   [ -n "$ALPACA_KEY" ] && [ -n "$ALPACA_SECRET" ] && echo "alpaca keys present" || echo "ALPACA KEYS MISSING: stop and tell Nick"
4. Pull the data (30-60 min, 0.5-1.5 GB; safe to re-run):
   cd ~/sprint && .venv/bin/python tools/sprint_pull.py --symbols SPY,QQQ,IWM --from 2024-08-01 --to 2026-06-30 2>&1 | tail -25 ; du -sh ~/sprint/data/alpaca
5. Run the first question (10-30 min):
   cd ~/sprint && .venv/bin/python tools/sprint_run.py sprint/specs/orb_exits_v1.json 2>&1 | tail -70
6. Show the results so Nick can paste them back:
   cd ~/sprint && ls -la data/sprint/ && cat "$(ls -t data/sprint/report_*.md | head -1)"
   cat data/sprint/runs_*.csv
```

## What Nick sends back

- Step 2's last line (the sprint tests: all passed).
- Step 4's per-symbol gap lines (sessions, days without bars, sessions without 0DTE bars, contracts per session, MB on disk) and the spread-model line.
- Step 5's summary table and the three file paths.
- Step 6: the whole report and the run log CSV. Claude merges the CSV rows into `docs/research/sprint_runs.csv` (the run log keeps every run, winners and losers) and reads the report.

## What the report contains

- **First answer:** the plain stop + time floor, plan A (the current fixed-% plan), the best level target B, the best trail, and the best of C/E, side by side: trades, win rate, average win and loss, expectancy, profit factor, PF at 2x slippage, max drawdown, the expectancy's 95% day-block bootstrap interval.
- **Robustness on the top 5** (SPRINT_PLAN's checklist): at least 60 trades, PF ≥ 1.25 and > 1.0 at 2x slippage, profitable in each of Aug-Dec 2024 / 2025 / Jan-Jun 2026, positive without the best 5 trades, both sides, one-step nudges keep PF > 1.1, beats matched random entries, filters beat random day-skips, real levels beat made-up levels, deflated Sharpe with the total run count.
- **All 195 runs**, sorted by expectancy, with signals seen and the share skipped.
- Every number is labeled **BACKTEST (in-sample, DEV)** with **MODELED-SPREAD**. None is a live or paper fill. Not financial advice: evidence for Nick to decide.

## The spec (sprint/specs/orb_exits_v1.json)

Entries are the same in every run: ORB breakout on SPY, QQQ and IWM, both sides, 15/30/60-minute ranges, the first finished 1-minute close beyond the range (first break per side), signal bars finishing by 12:00, the next option print as the fill, contract = 0DTE with BS-EST |delta| 0.40-0.55 nearest 0.45. One position at a time per run and symbol. Blocks:

| Block | Runs | What varies |
| --- | --- | --- |
| plain | 3 | entry + the entry window's premium ceiling + all out 15:25 (build step 1) |
| A (current plan) | 6 | the time-of-day table as it is; all out 15:25 vs 15:50 |
| B (level target) | 90 | approach buffer $0.03 / 0.05% / 0.1 ATR × R:R minimum none / 1.5 / 2 / 2.5 / 3 × time (a) / (c) |
| C (half + trail) | 6 | time (a) / (c), same trades as unfiltered B ($0.03) |
| E (rejection or next level) | 6 | time (a) / (c), same trades as unfiltered B ($0.03) |
| trails on B's base | 84 | 14 trails (breakeven +6/8/10/15% or first level; ladders L1-L3; 1m/5m pivots; last level cleared; giveback 30/40/50%) × time (a) / (c), same trades as unfiltered B, the trail replaces the target |

Why C, E and the trails use B without an R:R minimum: with the 5% modeled half-spread, the option-side R:R to the nearest level is usually below 1, so a minimum would leave almost no trades to compare. The R:R minimums are tested in the B block, each against its unfiltered twin with random day-skips.

## Later (only when Nick asks)

- **Option trades for exact stop fills:** add `--trades` to step 4 (strikes within ±1.5% of the open). This is much bigger: roughly 5-10 GB and 3-6 hours. The engine uses trades automatically where they exist.
- **Spread sensitivity:** `tools/sprint_run.py SPEC --spread-pct 0.01` reruns with a 1% half-spread, labeled "MODELED-SPREAD 1.0% (sensitivity)". It is not the pre-registered model and never replaces it.
- **MEASURED-SPREAD:** once the desk has logged a few weeks of chains, Nick can decide whether to copy `data/chains/*.csv.gz` into `~/sprint/data/chains/`, and the runner picks them up automatically.
- **Locked periods L1 and L2** are refused by both tools. They run once, on 3-5 frozen finalists, after their spec is committed: `--locked L1 --frozen <sha256>`. Chart never runs that unless Nick sends the exact command.

## Engine status

| Part | Status |
| --- | --- |
| Data puller, gap report, locked-period refusal | implemented, tested with fake HTTP; not yet run against Alpaca |
| Level map (all SPRINT_PLAN levels) + made-up levels | implemented, tested (no look-ahead) |
| Fill rules | implemented, tested |
| Exits: stops, A-E, trails 1-5, time (a)-(d), R:R minimum, never-loosen | implemented, tested on hand-checked paths |
| Day-type features | implemented, tested (point-in-time). News and VIX are unknown in the backtest. |
| Entries: ORB 15/30/60 | implemented, tested; in this spec |
| Entries: noise band + no-cap twin, VWAP + 2m MACD retest, PDH/PDL retest + 9 EMA, failed-break calls, flush reversal | pre-registered in `sprint/entries.py` docstrings, implemented and tested for rules and no look-ahead; not run yet |
| Risk layer for the full bot rules (max loss sizing, 4 trades a day, streak rules, runner exception) | not built yet (later build steps) |
