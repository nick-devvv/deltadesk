# Sprint run on Chart's computer: ORB exits, the Option Alpha cross-check, and the other setups

This runs the sprint's backtests on Chart's computer, the only machine that can reach Alpaca's data API. Everything runs in its own folder, `~/sprint`, from branch `sprint/exits`. Nothing touches `~/desk`, its journal or the live desk, and nothing can place an order: the puller only reads `data.alpaca.markets` (market data), and the engine only reads files it pulled.

## What runs

| Spec | Runs | Period | Cost runs | Question |
| --- | --- | --- | --- | --- |
| `sprint/specs/orb_exits_v1.json` | 195 | DEV 2024-08-01 to 2026-06-30 | base 2% + 5% stress | Which exit makes the most money on ORB 15/30/60 breakouts: the current fixed-% plan A, a key-level target B, C, E, or a trail? |
| `sprint/specs/oa_crosscheck_v1.json` | 444 | NOT_SEEN_BY_OA 2024-08-01 to 2025-10-29 | base 2% + 5% stress | Do Option Alpha's Stage-1 survivors (SPY ORB60 calls, fixed stop/target 20/60, 15/45, 10/30), OA's T1 (50/100) and OA's filter leads hold up on the 15 months OA never saw? |
| `sprint/specs/setups_v1.json` | 58 | DEV | base 2% only | First look at every other implemented setup (noise band and its no-cap twin, VWAP + 2-min MACD retest, prior-day high/low retest + 9 EMA, failed-break calls, flush reversal) with the same six exits. |

The cost model is the pre-registered one: a half-spread of **2% of the premium** on every fill (MODELED-SPREAD; amended from 5% before any run, see SPRINT_PLAN), plus fees of $0.65 per contract per side. The 5% reruns are the cost stress test; their run ids end in `@s5`. The desk's chain logs (which would give MEASURED-SPREAD) only start on 2026-11-02 and don't cover these periods. Option trades (for exact stop fills) are not part of this run; without them a stop that trades through inside a minute fills at the stop price, and a stop gapped through fills at the next bar's open.

## What to expect

| Step | Time (estimate) | Disk |
| --- | --- | --- |
| Clone + venv + sprint tests | 3-5 min | about 300 MB (venv) |
| Pull SPY, QQQ, IWM, 2024-08-01 to 2026-06-30: stock bars 04:00-20:00 ET and 0DTE option bars within ±3% of the open; VIXY stock bars only (the VIX proxy) | 30-60 min (about 3,000-4,000 requests under the 200/min free-plan limit) | 0.5-1.5 GB |
| ORB exits, base + 5% | 15-30 min | |
| OA cross-check, base + 5% | 10-25 min | |
| Other setups, base | 8-20 min | |
| **Total** | **about 1-2.5 hours** (most likely about 1.5) | about 1.5 GB plus about 100 MB of results |

Estimates come from timing all five runs on synthetic data of the same shape: they took about 3 minutes over 120 symbol-sessions (3 symbols x 40 sessions). The real runs cover 1,440 symbol-sessions (930 for the OA cross-check) with real option files and longer trades, so the run estimates above are about 1.5-2.5 times a straight scale-up. Memory stays under 2 GB. The pull is resumable: if it stops, run the same command again and it continues where it left off.

## Message for Chart (one paste)

```
Sprint backtests (research only, about 1.5 hours in total, at most about 2.5). Show me every output.
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
4. Pull the data (30-60 min, 0.5-1.5 GB; safe to re-run; VIXY stock bars come along by default):
   cd ~/sprint && .venv/bin/python tools/sprint_pull.py --symbols SPY,QQQ,IWM --from 2024-08-01 --to 2026-06-30 2>&1 | tail -25 ; du -sh ~/sprint/data/alpaca
5. Run the five backtests, one after the other (35-75 min in total):
   cd ~/sprint && mkdir -p data/sprint/logs && for a in "sprint/specs/orb_exits_v1.json" "sprint/specs/orb_exits_v1.json --spread-pct 0.05" "sprint/specs/oa_crosscheck_v1.json" "sprint/specs/oa_crosscheck_v1.json --spread-pct 0.05" "sprint/specs/setups_v1.json"; do L="data/sprint/logs/$(echo "$a" | tr ' /.' '___').log"; echo "=== $a"; .venv/bin/python tools/sprint_run.py $a > "$L" 2>&1 && grep -E "^sprint |pass [12] done|^report:" "$L" || { echo "FAILED: $a"; tail -30 "$L"; }; done
6. Show the results so Nick can paste them back, and pack them in one zip (about 1 MB of text in total):
   cd ~/sprint && ls -la data/sprint/ && .venv/bin/python -m zipfile -c ~/sprint_results.zip data/sprint/report_*.md data/sprint/runs_*.csv data/sprint/gaps_*.json && ls -la ~/sprint_results.zip
   for f in $(ls -tr data/sprint/report_*.md | tail -5); do echo "=== $f"; cat "$f"; done
   cat data/sprint/runs_*.csv
   (if the chat can't take that much text, send Nick the file ~/sprint_results.zip instead)
```

## What Nick sends back

- Step 2's last line (the sprint tests: all passed).
- Step 4's per-symbol gap lines (sessions, days without bars, sessions without 0DTE bars, contracts per session, MB on disk), the VIXY line and the spread-model line.
- Step 5: for each of the five runs, its first line, the two "pass done" lines and the report path (or the FAILED block).
- Step 6: the five reports and the run log CSV (about 1,350 rows), or the zip `~/sprint_results.zip` with the same files. Claude merges the CSV rows into `docs/research/sprint_runs.csv` (the run log keeps every run, winners and losers) and reads the reports.

## What the reports contain

- **ORB exits and the other setups:** the exit families side by side (plain stop + time, plan A, the best level target B, the best trail, the best of C/D/E): trades, win rate, average win and loss, expectancy, profit factor, PF at 2x slippage, max drawdown, the expectancy's 95% day-block bootstrap interval.
- **OA cross-check:** every run in one table: symbol, side, stop/target pair, mechanics (`desk` = SPRINT_PLAN's fill rules; `oa1m` = OA-LIKE: checked once a minute on the close, filled at the next minute's print), contract rule, filter, trades, win rate, expectancy, PF, PF at 2x slippage, max drawdown, profitable two-month blocks, and Option Alpha's own Stage-1 result for the same rule (from `docs/research/sprint_runs.csv`).
- **Robustness on the top 5 of each run** (SPRINT_PLAN's checklist): at least 60 trades, PF ≥ 1.25 and > 1.0 at 2x slippage, profitable in each stretch inside the period, positive without the best 5 trades, both sides, one-step nudges keep PF > 1.1, beats matched random entries, filters beat random day-skips, real levels beat made-up levels (level-based runs), deflated Sharpe with the total run count. Two-month blocks are shown too (Option Alpha's "3 of 4 blocks" test).
- Every number is labeled **BACKTEST** with its period (in-sample DEV, or the period Option Alpha never saw) and **MODELED-SPREAD**. None is a live or paper fill. Not financial advice: evidence for Nick to decide.

## The specs

**`orb_exits_v1` (195 runs).** Entries are the same in every run: ORB breakout on SPY, QQQ and IWM, both sides, 15/30/60-minute ranges, the first finished 1-minute close beyond the range (first break per side), signal bars finishing by 12:00, the next option print as the fill, contract = 0DTE with BS-EST |delta| 0.40-0.55 nearest 0.45. One position at a time per run and symbol.

| Block | Runs | What varies |
| --- | --- | --- |
| plain | 3 | entry + the entry window's premium ceiling + all out 15:25 (build step 1) |
| A (current plan) | 6 | the time-of-day table as it is; all out 15:25 vs 15:50 |
| B (level target) | 90 | approach buffer $0.03 / 0.05% / 0.1 ATR × R:R minimum none / 1.5 / 2 / 2.5 / 3 × time (a) / (c) |
| C (half + trail) | 6 | time (a) / (c), same trades as unfiltered B ($0.03) |
| E (rejection or next level) | 6 | time (a) / (c), same trades as unfiltered B ($0.03) |
| trails on B's base | 84 | 14 trails (breakeven +6/8/10/15% or first level; ladders L1-L3; 1m/5m pivots; last level cleared; giveback 30/40/50%) × time (a) / (c), same trades as unfiltered B, the trail replaces the target |

C, E and the trails use B without an R:R minimum so that they compare exits on the same trades; after the spread, fees and decay, the option-side R:R to the nearest level is often below the minimums. The R:R minimums are tested in the B block, each against its unfiltered twin with random day-skips.

**`oa_crosscheck_v1` (444 runs, period NOT_SEEN_BY_OA).** Option Alpha's rules: 0DTE, first breakout only per side, signal bars finishing by 12:00, next-bar entry, a fixed stop and target as % of the debit on the option's price, nothing else (no breakeven, no if-flat, no time tightening), all out 15:25. Contract d40-55t45 (OA took the closest delta to 0.45 with no band; band misses are skipped and counted). Each symbol and each side runs on its own.

| Block | Runs | What varies |
| --- | --- | --- |
| oa_core | 72 | SPY / QQQ / IWM × ORB60 × calls / puts × 20/20, 20/40, 20/60, 15/45, 10/30, 50/100 × mechanics desk / oa1m |
| oa_t1_delta50 | 12 | T1 itself: 50/100 with the 0.50-delta contract (d45-60t50: 0.45-0.60 nearest 0.50) × symbols × sides × mechanics |
| orb_context | 60 | ORB30 and ORB15 × symbols × sides × the five Stage-1 pairs, desk mechanics |
| side_rule | 120 | ORB60 × symbols × sides × five pairs × mechanics × two pre-registered forms: calls only when the prior close is above its 20-day SMA, puts only when below; and the same with a 1% margin (no trade within ±1% of the SMA) |
| event_skip | 60 | ORB60 × symbols × sides × five pairs × mechanics, skipping FOMC statement days and CPI release days (dates and sources in `sprint/events.py`: federalreserve.gov and BLS's 2024/2025 release calendars) |
| optimizer_leads | 120 | ORB60 × symbols × sides × five pairs × mechanics × two leads from OA's Strategy Optimizer on its run 023 (in-sample there): "VIX falling" with **proxy: VIXY** (VIXY's last finished 1-minute close below its prior close; applied to calls and puts alike), and the open-gap side rule (calls when the open is 0 to +0.75% above the prior close, puts 0 to -0.75% below) |

**`setups_v1` (58 runs, DEV).** Noise band, VWAP + 2-min MACD retest, prior-day high/low retest + 9 EMA and flush reversal (calls and puts as separate runs), and failed-break calls, each with six exits: (1) plain premium ceiling + time; (2) plan A; (3) plan B with a $0.03 buffer and no R:R minimum; (4) plan B with R:R ≥ 2; (5) giveback 40% trail on B's base; (6) fixed 20/60. The noise band also runs with the noise ledger's own exit and its delta 0.55-0.75 contract, and its twin runs with that exit minus the per-minute 20% ceiling. The twin differs from the noise band only inside that exit, so it isn't repeated with the six. SPY, QQQ and IWM are pooled in each run; the report splits the top runs by symbol and side.

## Later (only when Nick asks)

- **Option trades for exact stop fills:** add `--trades` to step 4 (strikes within ±1.5% of the open). This is much bigger: roughly 5-10 GB and 3-6 hours. The engine uses trades automatically where they exist.
- **Spread sensitivity:** `tools/sprint_run.py SPEC --spread-pct 0.05` reruns with a 5% half-spread for every symbol, labeled "MODELED-SPREAD 5.0% (sensitivity)" in the run log, with run ids ending in `@s5`. It is a stress test, not the pre-registered model.
- **MEASURED-SPREAD:** once the desk has logged a few weeks of chains, Nick can decide whether to copy `data/chains/*.csv.gz` into `~/sprint/data/chains/`, and the runner picks them up automatically.
- **Locked periods L1 and L2** are refused by both tools. They run once, on 3-5 frozen finalists, after their spec is committed: `--locked L1 --frozen <sha256>`. Chart never runs that unless Nick sends the exact command.

## Engine status

| Part | Status |
| --- | --- |
| Data puller, gap report, locked-period refusal | implemented, tested with fake HTTP; not yet run against Alpaca |
| Level map (all SPRINT_PLAN levels) + made-up levels | implemented, tested (no look-ahead) |
| Fill rules | implemented, tested |
| Exits: stops, A-E, trails 1-5, time (a)-(d), R:R minimum, never-loosen, fixed stop/target (desk and OA-LIKE mechanics) | implemented, tested on hand-checked paths |
| Day-type features, 20-day SMA side rule, FOMC/CPI calendar | implemented, tested (point-in-time). News and VIX are unknown in the backtest. |
| Entries: ORB 15/30/60, noise band + no-cap twin, VWAP + 2m MACD retest, PDH/PDL retest + 9 EMA, failed-break calls, flush reversal | pre-registered in `sprint/entries.py` docstrings, implemented and tested for rules and no look-ahead |
| Risk layer for the full bot rules (max loss sizing, 4 trades a day, streak rules, runner exception) | not built yet (later build steps) |
