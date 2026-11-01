# Sprint run on Chart's computer: ORB exits, the Option Alpha cross-check, and the other setups

This runs the sprint's backtests on Chart's computer, the only machine that can reach Alpaca's data API. Everything runs in its own folder, `~/sprint`, from branch `sprint/exits`. Nothing touches `~/desk`, its journal or the live desk, and nothing can place an order: the puller only reads `data.alpaca.markets` (market data), and the engine only reads files it pulled.

## Run 8: round 8, steady share rules, a sharper big-day filter, indicators and levels (about 45-90 minutes, no new data)

Nick asked for steadier rules that win on different days than the big-day calls, a sharper big-day filter for those calls, contracts beyond 0DTE that can be sold early, and the classic indicators, alone and with levels, with a stop and target tuned honestly. Everything was fixed before any round-8 code or run in SPRINT_PLAN "Amendment 10" and Addenda 10.1, 10.2 and 10.3 (commits `0fc8fd1`, `d75e28b`, `e2d1369`, `e2cc2d6`); the code is `e49af2b`..`fb1adcc`. This run uses branch **`sprint/round8`** (the message checks it out).
- **Engine runs** (`tools/sprint_run.py`, 9 runs each, SPY + QQQ + IWM): B3 `newhigh_c` ("wait for proof") and B4 (FIN-H's 11:00 entry with relative volume 1.06+ on the 0DTE and the next-expiry far out-of-the-money contract, with four exits: -95%, -50%, -50% + giveback, -50% + target +100%). On **2016-01-04 to 2024-01-31** (`round8_hist_v1`, option prices **MODELED** with run 4's calibration; next-expiry modeled prices are **NOT VALIDATED**) and on **2024-08-01 to 2026-06-30** (`round8_dev_v1`, **REAL** option prices). The DEV run points `--chains-dir` at a folder that doesn't exist, so it uses the pre-registered 2% spread.
- **Then `tools/sprint_round8.py`** runs the rest and writes `data/sprint/round8_<date>.md` and `.json`:
  - Part A in shares on 10 years of real stock bars: the noise band in shares (`noise_sh`, plus a volatility-sized version), the last-half-hour momentum trade (`last30`, plus the 10:00 version) and the stressed-day gap fade (`gapfade_vix`), each also long-only. Share trade file `trades_round8_shares_<date>.csv.gz`.
  - Part D in shares: RSI, Bollinger, EMA 9/21, MACD, level + RSI and trend pullback on 5-minute bars (the level rule also against 5 sets of made-up levels).
  - The option pass, one pass per entry: the six indicator rules on 0DTE and next-expiry contracts with the 12 stop/target cells (chosen on 2016-2019 only) and the signal exit, their random-side twins, the noise band carried by options and the gap fade's option twins. On 2016-2024 MODELED and 2024-2026 REAL. Trade files `trades_round8_options_hist_<date>.csv.gz` and `..._dev_<date>.csv.gz`.
  - Part B on run 7's trade files: confidence sizing of the far-OTM call sleeves (skip / 1 / 2 contracts), B3 and B4 against FIN-H, then the book and the trial count (192 + the run logs).
- No pull: every file needed is on Chart's computer from runs 1-7 (stock bars 2015-11 to 2024-01 and 2024-08 to 2026-06, 0DTE option bars and next-expiry option bars 2024-08 to 2026-06, VIXY daily, `data/sprint/calib_modeled.json`, run 7's `trades_factory_hist_v1_*` and `trades_factory_dev_v1_*`).

### What to expect

| Step | Time (estimate) | Disk |
| --- | --- | --- |
| Update + sprint tests (243) | 4-8 min | |
| Check the files | seconds | |
| `round8_hist_v1`: 9 runs on 2,033 sessions x 3 symbols, MODELED options | 3-7 min | about 1-2 MB (trade file) |
| `round8_dev_v1`: 9 runs on 479 sessions x 3 symbols, real options | 3-7 min | under 1 MB |
| `tools/sprint_round8.py` (shares, the option pass on both periods, Part B, the book) | 33-70 min | about 40-70 MB (trade files + report) |
| Zip | 1-2 min | about 40-70 MB |
| **Total** | **45-90 minutes** | **about 80-140 MB (results + zip)** |

Estimates come from timing these exact specs and the tool on synthetic data of the real size on a 2-core machine: SPY, QQQ and IWM with 2,075 HIST sessions (42 of them warm-up) and 479 DEV sessions, every minute 04:00-20:00, 0DTE and next-expiry option bars within +/-3% of the open on DEV, VIXY daily, run 4's calibration file and synthetic run-7 factory trade files. `round8_hist_v1` took 3.3 min (peak memory 1.1 GB), `round8_dev_v1` 3.2 min, and `tools/sprint_round8.py` 33 min (peak memory 2.5 GB): the HIST option pass 23 min (3.19 million option trades, a 25 MB file), the DEV option pass 7 min (0.92 million, 7 MB), and the rest (loading the bars, re-stamping run 7's trades, the share pass of 81 s with 272,000 share trades, the readouts) about 2.5 min. The ranges allow for Chart's computer being up to twice as slow and for real files being bigger. The round-8 tool needs about 2.5-3 GB of memory, so nothing else heavy should run at the same time. The whole run stays well under 3 hours, so it is one run (no 8a / 8b split).

### Message for Chart, run 8 (one paste)

```
Sprint run 8: round 8, steady share rules, a sharper big-day filter, indicators and levels (research only, about 45-90 minutes, no new data). Show me every output.
Rules: you never place trades, never click buy/sell/order buttons, never enter passwords or keys, never print a key.
Never touch ~/desk: don't cd into it, don't edit, copy, restart or run anything there. Never pass --locked or --frozen to any command.
If a step fails, show the error and stop. Don't change any code; re-running the same command once is fine.
1. Update the sprint code to the round-8 branch:
   cd ~/sprint && git fetch -q origin sprint/round8 && git checkout -q -B sprint/round8 origin/sprint/round8 && git reset -q --hard origin/sprint/round8 && git log -1 --oneline
2. Tests:
   cd ~/sprint && .venv/bin/python -m pytest -q tests/test_sprint_*.py 2>&1 | tail -3
3. Check the files are there (no pull needed) and the free disk space:
   cd ~/sprint && ls -la data/sprint/calib_modeled.json && ls -t data/sprint/trades_factory_hist_v1_*.csv.gz | head -1 && ls -t data/sprint/trades_factory_dev_v1_*.csv.gz | head -1 && ls data/alpaca/options/SPY | wc -l && ls data/alpaca/options_next/SPY | wc -l && ls data/alpaca/stocks/SPY | head -1 && ls data/alpaca/stocks/SPY | tail -1 && ls -la data/alpaca/daily/VIXY.csv.gz && df -h ~ | tail -1
4. B3 and B4 on 2016-2024 (MODELED options), then on 2024-2026 (REAL options):
   cd ~/sprint && mkdir -p data/sprint/logs && .venv/bin/python tools/sprint_run.py sprint/specs/round8_hist_v1.json > data/sprint/logs/run8_hist.log 2>&1 && grep -E "^sprint |tapes:|pass 1 done|^report:|^trades:" data/sprint/logs/run8_hist.log || { echo "FAILED: round8_hist_v1"; tail -30 data/sprint/logs/run8_hist.log; }
   cd ~/sprint && .venv/bin/python tools/sprint_run.py sprint/specs/round8_dev_v1.json --chains-dir data/sprint/no_chains > data/sprint/logs/run8_dev.log 2>&1 && grep -E "^sprint |pass 1 done|^report:|^trades:" data/sprint/logs/run8_dev.log || { echo "FAILED: round8_dev_v1"; tail -30 data/sprint/logs/run8_dev.log; }
5. Round 8: the share rules, the indicator rules, the option pass, Part B and the book:
   cd ~/sprint && .venv/bin/python tools/sprint_round8.py > data/sprint/logs/run8_round8.log 2>&1; tail -70 data/sprint/logs/run8_round8.log
6. Zip everything and show the summary table:
   cd ~/sprint && .venv/bin/python -m zipfile -c ~/sprint_results8.zip $(ls -t data/sprint/round8_*.md | head -1) $(ls -t data/sprint/round8_*.json | head -1) $(ls -t data/sprint/trades_round8_shares_*.csv.gz | head -1) $(ls -t data/sprint/trades_round8_options_dev_*.csv.gz | head -1) $(ls -t data/sprint/trades_round8_hist_v1_*.csv.gz | head -1) $(ls -t data/sprint/trades_round8_dev_v1_*.csv.gz | head -1) $(ls -t data/sprint/report_*_round8_hist_v1.md | head -1) $(ls -t data/sprint/report_*_round8_dev_v1.md | head -1) data/sprint/logs/run8_*.log data/sprint/runs_*.csv && ls -la ~/sprint_results8.zip && ls -la $(ls -t data/sprint/trades_round8_options_hist_*.csv.gz | head -1)
   sed -n '/^## Summary/,/^## Part A/p' "$(ls -t data/sprint/round8_*.md | head -1)"
   (send Nick the file ~/sprint_results8.zip; the HIST option trade file, millions of rows, stays on this computer)
```

What Nick sends back: step 1's commit line, step 2's last line, step 3's lines, step 4's lines, step 5's output (the summary lines and any WARNING lines), step 6's table, and `~/sprint_results8.zip`.

Checks on the way in:
- Step 2: 243 sprint tests pass.
- Step 3: `calib_modeled.json` is there (its sha256 starts `4d50070991c1` if unchanged), both run-7 factory trade files are listed, about 470-479 days under `options/SPY` and under `options_next/SPY`, stock months `2015-11` to `2026-06`, and `VIXY.csv.gz`. If a factory trade file is missing, step 5 refuses: stop there.
- Step 4: run ids `round8_hist_v1-001..009` (period HIST, notes MODELED; the `tapes:` line lists `d03-12t07|C` and `n1d03-12t07|C [d03-12t07|C (fallback for n1d03-12t07|C)]`: run 4 has no next-expiry key for that band, so the 0DTE band's multiplier is used and labeled) and `round8_dev_v1-001..009` (period DEV, MODELED-SPREAD 2%, not MEASURED). The run log gains 18 rows.
- Step 5: the `option pass HIST` line lists the multipliers used (fallbacks labeled), then one summary line per Part A rule, A-opt / A3 twin, B2 sleeve, B3, B4 variant, D share rule, D option study (the chosen cell, SURVIVES or fail, the signal exit) and the book. A `WARNING:` line saying run 7's sleeve trades were re-stamped with the round-8 features is expected (run 7's files predate them); any other `WARNING:` line is a problem to look at.
- Known before any result (Amendment 10 and its addenda): the far-OTM call family wins on the same days; long 0DTE premium loses a little most days; A3 is a grade-C source (a pass is exploratory); most indicator rules are expected not to beat random entries after costs; next-expiry HIST prices are modeled and never validated, so DEV REAL decides.

## Run 7: the 10-year strategy factory (about 35-70 minutes, no new data)

Nick asked for every strategy we have code for, run across the full ~10 years, with its own numbers, the same "learn when it works / skip the losing conditions" process, and the survivors together as one book. Everything was fixed before any run in SPRINT_PLAN "Amendment 9" (commit `da61e34`). This run uses branch **`sprint/factory`** (the message checks it out; a later message for `sprint/exits` checks that branch out again).
- **21 runs**, SPY + QQQ + IWM pooled: the noise ledger (its own exit), ORB 15/30/60, VWAP + MACD retest, prior-day retest, flush, failed-break calls, failed-high puts (the plain exit), and far out-of-the-money calls and puts bought at 10:00, 10:30, 11:00, 12:00, 13:00 and 14:00.
- Each runs twice: on **2016-01-04 to 2024-01-31** (`factory_hist_v1`, real stock bars, option prices **MODELED** with run 4's calibration) and on **2024-08-01 to 2026-06-30** (`factory_dev_v1`, **REAL** option prices). L1 and L2 are never pulled or run.
- The DEV run points `--chains-dir` at a folder that doesn't exist, so it uses the pre-registered 2% spread, never logged 2026 chains.
- Then `tools/sprint_factory.py` reads the two trade files and, for each strategy: its numbers per period and per year; the best "skip these days" rule found on 2016-2019 only, checked on 2020-2024 (modeled) and on 2024-2026 (real); the walk-forward learner; the verdict. Then the book of the survivors and, for contrast, all 21 runs unfiltered. Output: `data/sprint/factory_<date>.md` and `.json`.
- No pull: every file needed is on Chart's computer from runs 1-4 (stock bars 2015-11 to 2024-01 and 2024-08 to 2026-06, 0DTE option bars 2024-08 to 2026-06, VIXY daily, `data/sprint/calib_modeled.json`).

### What to expect

| Step | Time (estimate) | Disk |
| --- | --- | --- |
| Update + sprint tests (194) | 3-5 min | |
| Check the files | seconds | |
| `factory_hist_v1`: 21 runs on 2,033 sessions x 3 symbols, MODELED options, no robustness pass | 22-45 min | about 10-20 MB (trade file) |
| `factory_dev_v1`: 21 runs on 479 sessions x 3 symbols, real options | 6-15 min | about 2-5 MB (trade file) |
| The factory (rules, learner, both books) | 1-3 min | about 1-3 MB |
| Zip | under 1 min | about 15-30 MB |
| **Total** | **35-70 minutes** | **about 30-60 MB (results + zip)** |

Estimates come from timing these exact specs and the factory on synthetic data of the real shape on a 2-core machine: 2,075 HIST sessions (42 of them warm-up) and 479 DEV sessions, SPY/QQQ/IWM plus VIXY, every minute 04:00-20:00, 0DTE option bars within ±3% of the open on DEV, run 4's calibration file. `factory_hist_v1` took 22 min (103,504 trades, a 9 MB trade file, peak memory 1.2 GB), `factory_dev_v1` 5.6 min (0.4 GB), the factory 1.4 min (0.6 GB). The ranges allow for Chart's computer being up to twice as slow and for real files being bigger (more strikes at higher prices, thicker option files). The HIST run needs about 1.2-1.5 GB of memory, so nothing else heavy should run at the same time.

### Message for Chart, run 7 (one paste)

```
Sprint run 7: the 10-year strategy factory (research only, about 35-70 minutes, no new data). Show me every output.
Rules: you never place trades, never click buy/sell/order buttons, never enter passwords or keys, never print a key.
Never touch ~/desk: don't cd into it, don't edit, copy, restart or run anything there. Never pass --locked or --frozen to any command.
If a step fails, show the error and stop. Don't change any code; re-running the same command once is fine.
1. Update the sprint code to the factory branch:
   cd ~/sprint && git fetch -q origin sprint/factory && git checkout -q -B sprint/factory origin/sprint/factory && git reset -q --hard origin/sprint/factory && git log -1 --oneline
2. Tests:
   cd ~/sprint && .venv/bin/python -m pytest -q tests/test_sprint_*.py 2>&1 | tail -3
3. Check the files are there (no pull needed) and the free disk space:
   cd ~/sprint && ls -la data/sprint/calib_modeled.json && ls data/alpaca/stocks/SPY | head -1 && ls data/alpaca/stocks/SPY | tail -1 && ls data/alpaca/options/SPY | wc -l && ls -la data/alpaca/daily/VIXY.csv.gz && df -h ~ | tail -1
4. Run the 21 strategies on 2016-2024 (MODELED options), then on 2024-2026 (REAL options):
   cd ~/sprint && mkdir -p data/sprint/logs && .venv/bin/python tools/sprint_run.py sprint/specs/factory_hist_v1.json > data/sprint/logs/run7_hist.log 2>&1 && grep -E "^sprint |tapes:|pass 1 done|^report:|^trades:" data/sprint/logs/run7_hist.log || { echo "FAILED: factory_hist_v1"; tail -30 data/sprint/logs/run7_hist.log; }
   cd ~/sprint && .venv/bin/python tools/sprint_run.py sprint/specs/factory_dev_v1.json --chains-dir data/sprint/no_chains > data/sprint/logs/run7_dev.log 2>&1 && grep -E "^sprint |pass 1 done|^report:|^trades:" data/sprint/logs/run7_dev.log || { echo "FAILED: factory_dev_v1"; tail -30 data/sprint/logs/run7_dev.log; }
5. The factory: each strategy's numbers, its rule and learner, the verdict, and the book:
   cd ~/sprint && .venv/bin/python tools/sprint_factory.py > data/sprint/logs/run7_factory.log 2>&1; tail -40 data/sprint/logs/run7_factory.log
6. Zip everything and show the factory's summary table:
   cd ~/sprint && .venv/bin/python -m zipfile -c ~/sprint_results7.zip $(ls -t data/sprint/factory_*.md | head -1) $(ls -t data/sprint/factory_*.json | head -1) $(ls -t data/sprint/trades_factory_hist_v1_*.csv.gz | head -1) $(ls -t data/sprint/trades_factory_dev_v1_*.csv.gz | head -1) $(ls -t data/sprint/report_*_factory_hist_v1.md | head -1) $(ls -t data/sprint/report_*_factory_dev_v1.md | head -1) data/sprint/logs/run7_*.log data/sprint/runs_*.csv && ls -la ~/sprint_results7.zip
   sed -n '/^## Summary/,/^## 1\. /p' "$(ls -t data/sprint/factory_*.md | head -1)"
   (send Nick the file ~/sprint_results7.zip)
```

What Nick sends back: step 1's commit line, step 2's last line, step 3's lines, step 4's lines, step 5's output (the summary table and the book lines), step 6's table, and `~/sprint_results7.zip`.

Checks on the way in:
- Step 2: 194 sprint tests pass.
- Step 3: `calib_modeled.json` is there (run 4 made it; its sha256 starts `4d50070991c1` if unchanged), stock months run from `2015-11` to `2026-06`, about 470-479 option days for SPY, and `VIXY.csv.gz` is there. If the calibration file is missing, step 4's first run refuses: stop there.
- Step 4: run ids `factory_hist_v1-001..021` (period HIST, notes say MODELED; the `tapes:` line lists six multipliers: `d03-12t07|C`, `d06-15t10|P`, `d40-55t45|C/P`, `d55-75t65|C/P`) and `factory_dev_v1-001..021` (period DEV, MODELED-SPREAD 2%, not MEASURED). The run log gains 42 rows.
- Step 5: a table of 21 strategies (HIST and DEV trades and PF, the rule, holdout 1 and 2, the learner, the verdict), then the survivors' book and the unfiltered book, each over 2018-2024 (MODELED), 2024-2026 (REAL) and the labeled mixed line. Any `WARNING:` line (for example a run that didn't use the 2% spread) is a problem to look at.
- Known before any result (Amendment 9): failed_break, otm_p_1030 and otm_c_1100 were studied before, so their verdicts are not new evidence; only those three strategies' MODELED tapes were checked against real prices (run 4), the rest are labeled NOT VALIDATED and holdout 2 on real prices decides; far-OTM put rules are flattered by the flat-IV model.

## Run 5: the "skip the quiet days" rules on real option prices (about 5 minutes, no new data)

SPRINT_PLAN Amendment 6, holdout 2. The four rules that passed 2020-2023 (F, G, H, I), plus a learner trained only on 2016-2024 history, are scored on the run-3 trade files: DEV 2024-08 to 2026-06, real Alpaca option prices. Results: SPRINT_RESULTS_5.md.

```
Sprint run 5 (research only, about 5 minutes, no new data). Show me every output.
Same rules as before: never trade, never touch ~/desk, never pass --locked or --frozen, stop and show the error if a step fails.
1. cd ~/sprint && git fetch -q origin sprint/exits && git reset -q --hard origin/sprint/exits && git log -1 --oneline
2. cd ~/sprint && .venv/bin/python -m pytest -q tests/test_sprint_*.py 2>&1 | tail -3
3. cd ~/sprint && ls -la data/sprint/trades_otm_v1_*.csv.gz data/sprint/trades_hist_v1_*.csv.gz && .venv/bin/python tools/sprint_regime.py > data/sprint/logs/run5_regime.log 2>&1; tail -25 data/sprint/logs/run5_regime.log
4. cd ~/sprint && .venv/bin/python -m zipfile -c ~/sprint_results5.zip data/sprint/regime_holdout2_* data/sprint/logs/run5_regime.log && ls -la ~/sprint_results5.zip
   (send Nick the step-3 output, or the file ~/sprint_results5.zip)
```

## Run 4: free 2016-2023 history

Nick approved a free long-history check. It tests the sprint's surviving ideas (`fb_or` with its base `fb`, `otm_put` with its unfiltered twin, `otm_bounce` with its twin) on **HIST = 2016-01-04 to 2024-01-31**: eight years these rules were never tuned on. The rules, pass bars, costs and idealizations were fixed before any pull or run in SPRINT_PLAN "Amendment 5" (commit `1d889ce`).
- HIST ends the day before L2 starts. L1 and L2 are never pulled or run; the guard refuses any range that touches them.
- Alpaca has stock bars there but no option prices (they start in Feb 2024). So there are two layers:
  - **Layer 1** (`tools/sprint_hist.py`): the same entries and filters on the stock alone. fb/fb_or as long stock with a stock stop (in R); the far out-of-the-money ideas as the stock's move after 10:30 / 11:00, in remaining-day sigmas. No option model.
  - **Layer 2** (`hist_v1`): option prices MODELED with Black-Scholes from the stock bars, at one implied vol per day = the 20-session realized volatility x a multiplier fitted on the real 2024-2026 option trades (`tools/sprint_calibrate.py`). Every Layer-2 number is labeled **MODELED (BS, calibrated IV)**.
  - First the model runs on 2024-2026 with modeled prices (`hist_val_v1`) and is compared with the real-price runs. A strategy that misses the pre-registered bar (same sign of expectancy, PF within ±35%) gets its HIST numbers labeled UNRELIABLE.
- New pull: stock 1-minute bars only (no option requests), split-adjusted, for SPY, QQQ, IWM and VIXY from 2015-11-01 (warm-up) to 2024-01-31; plus one VIXY daily file from 2014-11-01 to 2026-06-30 with L2 cut out (it replaces the 2023-2026 one with the same split-adjusted closes over a longer range).
- The 5% stress rerun skips the robustness pass (`--no-robust`): it only checks how the headline numbers move with costs.

### What to expect

| Step | Time (estimate) | Disk |
| --- | --- | --- |
| Update + sprint tests | 3-5 min | |
| Pull: 99 months x 4 symbols of 1-minute bars 04:00-20:00 (about 700-900 requests) + VIXY daily (2 requests) | 15-30 min | about 100-250 MB |
| Layer 1 (6 strategies, 5 random seeds) | 2-4 min | under 10 MB |
| Calibration (reads the run 1-3 trade files) | 2-5 min | |
| Validation on 2024-2026, modeled (6 runs) | 2-5 min | |
| HIST Layer 2, base cost + robustness (6 runs, 40 robustness jobs) | 17-35 min | a few MB of trades |
| HIST Layer 2 at 5%, no robustness | 5-12 min | |
| **Total** | **about 1-1.5 hours** | about 100-250 MB |

Estimates come from timing the full HIST length on synthetic stock bars of the real shape (2,075 sessions with the warm-up, 3 symbols plus VIXY, every minute 04:00-20:00, the same six runs) on a 2-core machine: Layer 1 took 1.6 min; Layer 2 took about 17 min with the robustness pass (6 runs + 40 robustness jobs) and about 5 min without; peak memory 1.5 GB. The ranges allow for Chart's computer being up to twice as slow. The synthetic cache was 28 MB per symbol (real VIXY is much thinner). The pull is resumable: if it stops, run the same command again; finished months are skipped.

### Message for Chart, run 4 (one paste)

```
Sprint run 4: free 2016-2023 history (research only, about 1 to 1.5 hours). Show me every output.
Rules: you never place trades, never click buy/sell/order buttons, never enter passwords or keys, never print a key.
Never touch ~/desk: don't cd into it, don't edit, copy, restart or run anything there. Never pass --locked or --frozen to any command.
If a step fails, show the error and stop. Don't change any code; re-running the same command once is fine (the pull resumes).
1. Update the sprint code:
   cd ~/sprint && git fetch -q origin sprint/exits && git checkout -q sprint/exits && git reset -q --hard origin/sprint/exits && git log -1 --oneline
2. Tests:
   cd ~/sprint && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python -m pytest -q tests/test_sprint_*.py 2>&1 | tail -3
3. Alpaca key check (prints only yes/no):
   [ -n "$ALPACA_KEY" ] && [ -n "$ALPACA_SECRET" ] && echo "alpaca keys present" || echo "ALPACA KEYS MISSING: stop and tell Nick"
4. Pull 2015-11 to 2024-01 stock bars (no options) and the VIXY daily file (15-30 min, about 100-250 MB, safe to re-run):
   cd ~/sprint && mkdir -p data/sprint/logs && .venv/bin/python tools/sprint_pull.py --period HIST > data/sprint/logs/run4_pull.log 2>&1; grep -vE "^  [A-Z]+ [0-9]{4}-[0-9]{2}: " data/sprint/logs/run4_pull.log | tail -14; du -sh data/alpaca/stocks data/alpaca/daily
5. Layer 1, the stock signal alone:
   cd ~/sprint && .venv/bin/python tools/sprint_hist.py > data/sprint/logs/run4_layer1.log 2>&1; grep -E "^sprint_hist|^  [A-Z]+:|^  VIXY|^layer1 |^done|^report:" data/sprint/logs/run4_layer1.log || tail -30 data/sprint/logs/run4_layer1.log
6. Fit the option model on the real 2024-2026 option trades:
   cd ~/sprint && .venv/bin/python tools/sprint_calibrate.py > data/sprint/logs/run4_calib.log 2>&1; grep -vE "^  trades_" data/sprint/logs/run4_calib.log | tail -14
7. Check the model against real option prices (2024-2026), then run 2016-2023 with it, then the 5% stress:
   cd ~/sprint && for a in "sprint/specs/hist_val_v1.json" "sprint/specs/hist_v1.json" "sprint/specs/hist_v1.json --spread-pct 0.05 --no-robust"; do L="data/sprint/logs/run4_$(echo "$a" | tr ' /.-' '____').log"; echo "=== $a"; .venv/bin/python tools/sprint_run.py $a > "$L" 2>&1 && grep -E "^sprint |tapes:|^validation |^HIST reading|pass [12] done|^report:" "$L" || { echo "FAILED: $a"; tail -30 "$L"; }; done
8. Zip everything and show the Layer-1 readings:
   cd ~/sprint && .venv/bin/python -m zipfile -c ~/sprint_results4.zip $(ls data/sprint/report_*hist_*.md data/sprint/hist_layer1_* data/sprint/validation_hist_val_v1*.json data/sprint/calib_modeled.json data/sprint/gaps_*_2015-11-01_2024-01-31.json data/sprint/trades_hist_v1_*.csv.gz data/sprint/logs/run4_*.log) data/sprint/runs_*.csv && ls -la ~/sprint_results4.zip
   sed -n '/^## Pre-registered readings/,/^## fb /p' "$(ls -t data/sprint/hist_layer1_*.md | head -1)"
   (send Nick the file ~/sprint_results4.zip)
```

What Nick sends back: step 2's last line, step 4's lines, step 5's `layer1` lines, step 6's multiplier table, step 7's lines (the `validation` and `HIST reading` lines are the headline), step 8's readings, and `~/sprint_results4.zip`.

Checks on the way in:
- Step 2: 177 sprint tests pass.
- Step 4: 2,075 sessions per symbol from 2015-11-02 (42 of them warm-up, 2,033 in HIST: 252, 251, 251, 252, 253, 252, 251, 250 a year, plus 21 in January 2024), "no option request before 2024-02-01", and VIXY daily over `2014-11-01..2024-01-31, 2024-08-01..2026-06-30`. A weekday without bars or a short session that isn't an early close is a data gap (or a calendar miss) to look at.
- Step 6: three keys are needed (`d40-55t45|C`, `d06-15t10|P`, `d03-12t07|C`). If one says MISSING or THIN, step 7 refuses the modeled runs; stop there.
- Step 7: run ids `hist_val_v1-001..006`, `hist_v1-001..006` and `hist_v1-001@s5..006@s5`, period tags DEV and HIST, notes saying MODELED. The run log gains 18 rows.
- Known gap between model and reality: a modeled option has a price every minute (at least $0.01), while a real far out-of-the-money contract can stop trading. The real runs dropped those trades as VOID (12 next to otm_v1-010's 1,408 trades; 4 next to otm_v1-040's 1,418), which flatters the real far-OTM results a little next to the model.

## Run 2 (setups_v2): the failed-break deep dive

Run 1's results are in `docs/research/SPRINT_RESULTS_1.md`. Run 2 changes one thing at a time on the only lead, failed-break calls (58 runs on DEV; what each block tests is in `sprint/specs/setups_v2.json` and SPRINT_PLAN "Amendment 2"). It needs one new pull: each session's prices of the **next listed expiry** (bars only, strikes within 1.5% of the open widened to the day's range; about 30-45 minutes, about 100-250 MB). Then it runs the spec at the base cost and at the 5% stress cost, and the former optional step 5b, `oa_crosscheck_v2` (66 runs): Option Alpha's "calm market" filters (VIX level and VIX change via the VIXY proxy, small gap up) on the 15 months Option Alpha never saw. Its VIXY daily bars come with step 3's pull. About 20-35 minutes for the three runs.

### Message for Chart, run 2 (one paste)

```
Sprint run 2 (research only, about 1 hour). Show me every output.
Rules: you never place trades, never click buy/sell/order buttons, never enter passwords or keys, never print a key.
Never touch ~/desk: don't cd into it, don't edit, copy, restart or run anything there. Never pass --locked or --frozen to any command.
If a step fails, show the error and stop. Don't change any code; re-running the same command once is fine (the pull resumes).
1. Update the sprint code:
   cd ~/sprint && git fetch -q origin sprint/exits && git checkout -q sprint/exits && git reset -q --hard origin/sprint/exits && git log -1 --oneline
2. Tests:
   cd ~/sprint && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python -m pytest -q tests/test_sprint_*.py 2>&1 | tail -3
3. Pull the next-expiry option bars (30-45 min, safe to re-run):
   cd ~/sprint && .venv/bin/python tools/sprint_pull.py --symbols SPY,QQQ,IWM --from 2024-08-01 --to 2026-06-30 --next-only --band 0.015 2>&1 | tail -12 ; du -sh ~/sprint/data/alpaca/options_next
4. Run setups_v2 at the base cost, then at the 5% stress cost, then the Option Alpha calm-market check (20-35 min):
   cd ~/sprint && mkdir -p data/sprint/logs && for a in "sprint/specs/setups_v2.json" "sprint/specs/setups_v2.json --spread-pct 0.05" "sprint/specs/oa_crosscheck_v2.json"; do L="data/sprint/logs/$(echo "$a" | tr ' /.' '___').log"; echo "=== $a"; .venv/bin/python tools/sprint_run.py $a > "$L" 2>&1 && grep -E "^sprint |VIX|pass [12] done|^report:" "$L" || { echo "FAILED: $a"; tail -30 "$L"; }; done
5. Zip the results and show the base report:
   cd ~/sprint && .venv/bin/python -m zipfile -c ~/sprint_results2.zip $(ls data/sprint/report_*setups_v2*.md data/sprint/report_*oa_crosscheck_v2*.md) data/sprint/runs_*.csv && ls -la ~/sprint_results2.zip
   cat "$(ls -t data/sprint/report_*setups_v2.md | head -1)"
   (send Nick the file ~/sprint_results2.zip)
```

What Nick sends back: step 2's last line, step 3's lines (sessions pulled per symbol, any "no_expiry_found" dates, MB on disk), step 4's lines, and `~/sprint_results2.zip`. Check on the way in: run setups_v2-001 is setups_v1-049 rerun unchanged, so it must show 676 trades and +$10.95 a trade.

## Run 3: Option Alpha's top-list family, the learner and the combined book (about 30-45 minutes, after run 2)

1. `otm_v1` (54 runs, base cost and the 5% stress): far out-of-the-money 0DTE calls and puts bought at 10:30 or 11:00 and held, the family that fills Option Alpha's Top Backtests (SPRINT_PLAN Amendment 4). It uses the 0DTE bars already pulled, plus VIXY daily bars. Step 3 fetches those if run 2 didn't (2 requests, resumable).
2. `tools/sprint_study.py auto` reads the run logs and trade files from runs 1-3. It picks the candidate runs (SPRINT_PLAN Amendment 3), runs the walk-forward learner on each, and combines the best run of each strategy family into one book. Trade files written before run 3 have no feature columns; the tool recomputes them from the cached bars.
3. An extra learner run on failed-break versions with enough trades to learn from: the base (setups_v2-001, 676 trades), opening-range lows only (012, 429) and SPY+QQQ (005, 489). Its three models count as trials for each.

```
Sprint run 3 (research only, about 45 minutes). Show me every output.
Same rules as before: never trade, never touch ~/desk, never pass --locked or --frozen, stop and show the error if a step fails.
1. cd ~/sprint && git fetch -q origin sprint/exits && git reset -q --hard origin/sprint/exits && git log -1 --oneline
2. cd ~/sprint && .venv/bin/python -m pytest -q tests/test_sprint_*.py 2>&1 | tail -3
3. cd ~/sprint && .venv/bin/python tools/sprint_pull.py --symbols "" --from 2024-08-01 --to 2026-06-30 2>&1 | tail -4
4. cd ~/sprint && mkdir -p data/sprint/logs && for a in "sprint/specs/otm_v1.json" "sprint/specs/otm_v1.json --spread-pct 0.05"; do L="data/sprint/logs/$(echo "$a" | tr ' /.' '___').log"; echo "=== $a"; .venv/bin/python tools/sprint_run.py $a > "$L" 2>&1 && grep -E "^sprint |VIX|pass [12] done|^report:" "$L" || { echo "FAILED: $a"; tail -30 "$L"; }; done
5. cd ~/sprint && .venv/bin/python tools/sprint_study.py auto > data/sprint/logs/study.log 2>&1; tail -80 data/sprint/logs/study.log
6. cd ~/sprint && .venv/bin/python tools/sprint_study.py learn --runs setups_v2-001,setups_v2-012,setups_v2-005 > data/sprint/logs/learn.log 2>&1; tail -60 data/sprint/logs/learn.log
7. cd ~/sprint && .venv/bin/python -m zipfile -c ~/sprint_results3.zip $(ls data/sprint/report_*otm_v1*.md data/sprint/study_*) data/sprint/runs_*.csv && ls -la ~/sprint_results3.zip
   (send Nick the file ~/sprint_results3.zip)
```

## What runs (run 1)

| Spec | Runs | Period | Cost runs | Question |
| --- | --- | --- | --- | --- |
| `sprint/specs/orb_exits_v1.json` | 195 | DEV 2024-08-01 to 2026-06-30 | base 2% + 5% stress | Which exit makes the most money on ORB 15/30/60 breakouts: the current fixed-% plan A, a key-level target B, C, E, or a trail? |
| `sprint/specs/oa_crosscheck_v1.json` | 444 | NOT_SEEN_BY_OA 2024-08-01 to 2025-10-29 | base 2% + 5% stress | Do Option Alpha's Stage-1 survivors (SPY ORB60 calls, fixed stop/target 20/60, 15/45, 10/30), OA's T1 (50/100) and OA's filter leads hold up on the 15 months OA never saw? |
| `sprint/specs/oa_crosscheck_v2.json` (optional step 5b) | 66 | NOT_SEEN_BY_OA | base 2% only | Does Option Alpha's "calm, risk-on day" theme for breakout calls (IV-rank proxy, VIX not rising, small gap up) hold on unseen data? T1's 50/100 and 20/60. |
| `sprint/specs/setups_v1.json` | 58 | DEV | base 2% only | First look at every other implemented setup (noise band and its no-cap twin, VWAP + 2-min MACD retest, prior-day high/low retest + 9 EMA, failed-break calls, flush reversal) with the same six exits. |

The cost model is the pre-registered one: a half-spread of **2% of the premium** on every fill (MODELED-SPREAD; amended from 5% before any run, see SPRINT_PLAN), plus fees of $0.65 per contract per side. The 5% reruns are the cost stress test; their run ids end in `@s5`. The desk's chain logs (which would give MEASURED-SPREAD) only start on 2026-11-02 and don't cover these periods. Option trades (for exact stop fills) are not part of this run; without them a stop that trades through inside a minute fills at the stop price, and a stop gapped through fills at the next bar's open.

## What to expect

| Step | Time (estimate) | Disk |
| --- | --- | --- |
| Clone + venv + sprint tests | 3-5 min | about 300 MB (venv) |
| Pull SPY, QQQ, IWM, 2024-08-01 to 2026-06-30: stock bars 04:00-20:00 ET and 0DTE option bars within ±3% of the open; VIXY 1-minute stock bars (the VIX proxy) and VIXY split-adjusted daily bars from 2023-01-01 with the locked months cut out (the IV-rank proxy) | 30-60 min (about 3,000-4,000 requests under the 200/min free-plan limit) | 0.5-1.5 GB |
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

## Optional step 5b (run after the first five; about 5 minutes)

`oa_crosscheck_v2` (66 runs) tests Option Alpha's "calm, risk-on day" theme for breakout calls on the period OA never saw. It needs VIXY daily bars from 2023, which the earlier pull didn't fetch, so the line below updates the code, pulls them (locked months cut out, 2 requests), runs the spec and prints its report:

```
cd ~/sprint && git fetch -q origin sprint/exits && git reset -q --hard origin/sprint/exits && mkdir -p data/sprint/logs && .venv/bin/python tools/sprint_pull.py --symbols "" --stock-only VIXY --daily VIXY --from 2024-08-01 --to 2025-10-29 2>&1 | tail -4 && .venv/bin/python tools/sprint_run.py sprint/specs/oa_crosscheck_v2.json > data/sprint/logs/oa_v2.log 2>&1 && grep -E "^sprint |VIX|pass [12] done|^report:" data/sprint/logs/oa_v2.log && cat "$(ls -t data/sprint/report_*oa_crosscheck_v2*.md | head -1)" || tail -30 data/sprint/logs/oa_v2.log
```

Then re-run step 6's zip line so `~/sprint_results.zip` includes the new report and run-log rows.

Pre-registered in the spec (all 66 runs count as trials): SPY, QQQ, IWM each on its own, ORB60 calls and puts, desk fills, base cost, fixed 50/100 with the 0.50-delta contract (d45-60t50) and 20/60 with d40-55t45. Filters, each against its unfiltered twin and random day-skips:
- `vixy_pctl_le40`: IV-rank **proxy: VIXY percentile** ≤ 40% (share of the 252 split-adjusted daily VIXY closes ending at the prior close that are at or below it). The window skips the locked months, so early dates reach back into 2023. VIXY decays over time, so this runs lower than a true IV rank.
- `vixy_not_rising`: VIXY's last finished 1-minute close at the decision ≤ its prior close × 1.01 (**proxy: VIXY**).
- `gap_side_075`: open vs prior close in (0%, +0.75%] for calls, [-0.75%, 0%) for puts.
- **calm** = all three together.
- Puts only, the mirrored regime: VIXY percentile ≥ 60% and VIXY ≥ its prior close × 1.01.

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
| Risk layer for the full bot rules ($50 max planned loss, 4 trades a day, streak rules) | implemented for setups_v2 (`sprint/engine.bot_risk`), tested; the runner exception needs live news and is not testable here |
| Failed-break variants, the put mirror (failed_high), next-expiry contracts and their puller | implemented for setups_v2, tested (rules, no look-ahead, fake HTTP) |
| HIST check (run 4): stock-only HIST pull, Layer 1 (`sprint/underlying.py`), MODELED (BS, calibrated IV) tapes, calibration and validation (`sprint/modeled.py`) | implemented, tested on synthetic data (rules, no look-ahead, prior-session IV proxy, planted-multiplier recovery, guard, fake HTTP); not yet run against Alpaca |
