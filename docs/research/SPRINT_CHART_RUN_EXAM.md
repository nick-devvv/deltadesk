# Sprint exam on Chart's computer: the final locked-period exam (L2, then L1)

This is the last test of the sprint: the frozen finalists run **once** on the two periods nobody has looked at, L2 (2024-02-01 to 2024-07-31) and L1 (2026-07-01 to 2026-10-30). Everything was fixed before any code, pull or run in SPRINT_PLAN "Amendment 11" (commit `68a3b1e`), which extends "Amendment 7" (its rules, guard and verdicts stand). Branch **`sprint/exam`**. Research only: nothing here trades, and nothing touches `~/desk`.

The four finalists:
- **FIN-H:** far out-of-the-money 0DTE calls at 11:00 (otm_v1-040's rules) on days when volume is running at least 1.06x normal.
- **FIN-L:** the same calls, taken when a model fitted on 2016-2024 history says P(win) is at least 0.5.
- **FIN-HS:** FIN-H with confidence sizing: skip, 1 or 2 contracts by the model's tercile.
- **NB-VOL:** the volatility-sized noise band in shares (SPY, QQQ, IWM, long and short).

The references are otm_v1-040 unfiltered on the same period (for the three call finalists), and coin-flip direction on the same entries and exits (for NB-VOL).

It runs in two pastes, because Amendment 11 says the models are committed before any locked data is pulled:
1. **Exam step 1** fits FIN-L's and FIN-HS's models on files already on Chart's computer (no locked data) and writes `sprint/specs/final_v2_models.json`. Nick sends the zip to Claude.
2. Claude commits that file, writes its sha256 into the exam spec (`tools/sprint_exam.py freeze`), commits the spec and fills in `<EXAM_SPEC_SHA>` below.
3. **Exam step 2** runs L2, then L1, once each, through the `--locked <name> --frozen <exam spec sha256>` guard.

## How the locked pull works

- **Refusals before any request.** `tools/sprint_exam.py run` refuses unless every one of these holds:
  - `--locked` names exactly one of L2 or L1;
  - `sprint/specs/final_v2_exam.json` is Amendment 11's spec, committed, unchanged, and hashes to `--frozen` (`sprint/periods.guard`, the same check the runner and puller use);
  - no tracked file differs from the commit, and no untracked code sits in `sprint/`, `tools/`, `tests/` or the top folder;
  - the models file is committed, unchanged, and hashes to the sha256 written in the spec;
  - the exam log allows this run (one shot, below);
  - the warm-up months are in the main cache;
  - the Alpaca keys are set.
- **Its own cache.** The period's data goes into `data/alpaca_exam/<L2|L1>/`, never into `data/alpaca/`, so no other tool can read it. The pull uses the existing read-only puller (only `data.alpaca.markets` is ever called):
  - SPY, QQQ, IWM and VIXY 1-minute bars for the period only;
  - SPY, QQQ and IWM 0DTE option bars (strikes within 3% of the open, widened to the day's range; bars only, as on DEV);
  - VIXY daily closes in **one** split-adjusted request, from `vixy_daily_from` to the period's end. That keeps the 252-close percentile and the 20-close z-score on one split basis: L2 reads from 2022-10-01, L1 from 2025-03-01, and neither range touches the other locked period.
- **Warm-up (indicators only, no trades).** Two calendar months of 1-minute bars come from the main cache, the same rule HIST used:
  - L2: Dec 2023 and Jan 2024, from HIST's pull (split-adjusted, so L2's stock bars are pulled split-adjusted too);
  - L1: May and June 2026, from DEV's pull (raw, so L1's are pulled raw).
  - SPY, QQQ and IWM had no splits then, so the two bases match for them.
- **One shot.** `data/sprint/exam_log.jsonl` records every start and finish with the code commit, the exam spec sha256 and the models sha256.
  - A second run of the same period is allowed only with the same spec and the same commit (crash recovery). It is logged and labeled as a re-run.
  - A different spec or commit on a period already read is refused.
  - The other period may run at a later commit. If any code file changed in between (anything outside `docs/` and `*.md`), every finalist on that run is labeled VOID, with the changed files listed.
  - Locked data found in the exam cache with no logged start for it (a deleted log) is refused.
- **Keys.** They are read from the environment by the puller, sent only in the request headers to `data.alpaca.markets`, and never printed or written.

## Exam step 1: fit the models (about 10-20 minutes, no new data, no locked data)

`tools/sprint_exam.py fit` does three things:
- It fits **FIN-L**'s logit once, on every 2016-2024 11:00-call trade: run 4's `hist_v1-005` rows if that trade file is still on Chart's computer, else run 7's `factory_hist_v1-012`. It says which.
- It fits **FIN-HS**'s two models (round 8's B2 logit on the 25 entry features), each with its tercile cuts:
  - the L2 model on FIN-H trades through 2024-01-31 (HIST, MODELED);
  - the L1 model on FIN-H trades through 2026-06-30 (HIST MODELED + DEV REAL).
  - Run 7's trades predate the seven round-8 features, so those are re-stamped from cached bars first (trade P/L unchanged).
- It writes `sprint/specs/final_v2_models.json` and prints its sha256 and every source file's sha256.

It refuses any trade dated inside L1 or L2, any fit after a locked read, and any fit over a committed models file.

| Step | Time (estimate) | Disk |
| --- | --- | --- |
| Update + sprint tests (270) | 5-10 min | |
| Check the files | seconds | |
| Stage E1 (reads the trade files, re-stamps run 7's FIN-H trades from cached bars, fits three small models) | 3-10 min | under 1 MB |
| Zip | seconds | under 1 MB |

### Message for Chart, exam step 1 (one paste)

```
Sprint exam step 1: fit the exam's models (research only, about 10-20 minutes, no new data, no locked data). Show me every output.
Rules: you never place trades, never click buy/sell/order buttons, never enter passwords or keys, never print a key.
Never touch ~/desk: don't cd into it, don't edit, copy, restart or run anything there.
Never pass --locked or --frozen to any command, except exactly as written in exam step 2 (a later, separate message). This message uses neither.
If a step fails, show the error and stop. Don't change any code; re-running the same command once is fine.
1. Update the sprint code to the exam branch:
   cd ~/sprint && git fetch -q origin sprint/exam && git checkout -q -B sprint/exam origin/sprint/exam && git reset -q --hard origin/sprint/exam && git log -1 --oneline
2. Tests:
   cd ~/sprint && .venv/bin/python -m pytest -q tests/test_sprint_*.py 2>&1 | tail -3
3. Check the files are there (no pull needed) and that no locked data exists yet:
   cd ~/sprint && (ls -la data/sprint/trades_hist_v1_*.csv.gz 2>/dev/null || echo "no hist_v1 trade file: FIN-L will use factory_hist_v1-012") && ls -t data/sprint/trades_factory_hist_v1_*.csv.gz | head -1 && ls -t data/sprint/trades_factory_dev_v1_*.csv.gz | head -1 && ls -la data/alpaca/daily/VIXY.csv.gz && ls data/alpaca/stocks/SPY | head -1 && ls data/alpaca/stocks/SPY | tail -1 && echo "exam cache entries: $(ls data/alpaca_exam 2>/dev/null | wc -l)" && (ls data/sprint/exam_log.jsonl 2>/dev/null || echo "no exam log yet")
4. Stage E1: fit FIN-L's and FIN-HS's models (no locked data):
   cd ~/sprint && mkdir -p data/sprint/logs && .venv/bin/python tools/sprint_exam.py fit > data/sprint/logs/exam_fit.log 2>&1 && cat data/sprint/logs/exam_fit.log || { echo "FAILED: exam fit"; tail -30 data/sprint/logs/exam_fit.log; }
5. Show the models file's fingerprint and zip it with the log:
   cd ~/sprint && sha256sum sprint/specs/final_v2_models.json && .venv/bin/python -m zipfile -c ~/sprint_exam_models.zip sprint/specs/final_v2_models.json data/sprint/logs/exam_fit.log && ls -la ~/sprint_exam_models.zip
   (send Nick the file ~/sprint_exam_models.zip)
```

What Nick sends back: step 1's commit line, step 2's last line, step 3's lines, step 4's whole output, step 5's sha256 line, and `~/sprint_exam_models.zip`.

Checks on the way in:
- Step 2: 270 sprint tests pass.
- Step 3:
  - both run-7 factory trade files are listed (if one is missing, step 4 refuses: stop there);
  - stock months run from `2015-11` to `2026-06`;
  - `VIXY.csv.gz` is there;
  - "exam cache entries: 0" and "no exam log yet". Anything else means a locked read already happened, and step 4 refuses.
- Step 4:
  - a `FIN-L source:` line (`hist_v1-005 ...` or `factory_hist_v1-012 ...`) with each file's sha256 and trade count. When `hist_v1-005` is used, a `check:` line compares it with run 7's same-configuration file (information only);
  - two `FIN-HS sources` lines (HIST and DEV, run 7's `otm_c_1100` with f_rvol >= 1.06; the DEV count should be close to holdout 2's 485 H trades);
  - a line saying how many run-7 FIN-H trades were re-stamped with the round-8 features. That is expected: run 7's files predate them;
  - `FIN-HS L2` and `FIN-HS L1` lines with trade counts, the dates trained through (2024-01-31 and 2026-06-30) and the tercile cuts. The L1 line has more trades than the L2 line;
  - `models sha256: <64 hex>`, which must equal step 5's `sha256sum` line. A `(for Claude: ...)` line gives the exam spec sha256 that `freeze` will produce.
  - A `WARNING:` line about a dirty tree is a problem to look at. A `REFUSED:` line means nothing was written.

## Between the two steps (Claude's side)

1. Put `final_v2_models.json` from the zip at `sprint/specs/final_v2_models.json`, check its sha256 equals step 4's `models sha256`, and commit it.
2. Run `python3 tools/sprint_exam.py freeze`: it refuses unless the models file is committed and unchanged, then rewrites the exam spec with that sha256 and prints the spec's new sha256. It must equal step 4's `(for Claude: ...)` value.
3. Commit `sprint/specs/final_v2_exam.json`, push `sprint/exam`, and put the spec's sha256 in place of `<EXAM_SPEC_SHA>` (both places) in the message below. From here on no code changes before both periods have run (Amendment 11: a code change after the first locked read voids the exam for the finalists it touches).

## Exam step 2: the one-shot exam, L2 then L1 (about 30-60 minutes, pulls market data)

| Step | Time (estimate) | Disk |
| --- | --- | --- |
| Update + sprint tests (270) | 5-10 min | |
| Key check, fingerprints | seconds | |
| L2: pull 125 sessions (SPY/QQQ/IWM/VIXY 1-minute bars, 0DTE option bars, VIXY daily; about 1,000-1,500 requests under the 200/min limit), then the engine at 2% and 5% and NB-VOL | 10-25 min | about 0.2-0.5 GB |
| L1: the same for 86 sessions | 7-18 min | about 0.15-0.35 GB |
| Zip | under 1 min | a few MB |

Estimates: DEV's pull of 479 sessions took 30-60 minutes for about 3,000-4,000 requests; L2 + L1 are 211 sessions with the same band. The exam's own computing (two engine runs at two spreads, NB-VOL and the bars) took under a second per symbol-session on synthetic data, so a few minutes per period.

### Message for Chart, exam step 2 (one paste)

```
Sprint exam step 2: the final locked-period exam, L2 then L1, each run ONCE (research only, about 30-60 minutes, pulls market data). Show me every output.
Rules: you never place trades, never click buy/sell/order buttons, never enter passwords or keys, never print a key.
Never touch ~/desk: don't cd into it, don't edit, copy, restart or run anything there.
Never pass --locked or --frozen except exactly as written in steps 4 and 5 below, one time each. Never run step 4 or 5 a second time unless Nick says so.
If a step fails, show the error and stop. Don't change any code.
1. Update the sprint code to the frozen exam commit (this replaces step 1's local models file with the committed one):
   cd ~/sprint && git fetch -q origin sprint/exam && git checkout -q -f -B sprint/exam origin/sprint/exam && git reset -q --hard origin/sprint/exam && git log -1 --oneline && git status --short | head -5
2. Tests:
   cd ~/sprint && .venv/bin/python -m pytest -q tests/test_sprint_*.py 2>&1 | tail -3
3. Alpaca key check (prints only yes/no), the frozen files' fingerprints and the free disk space:
   [ -n "$ALPACA_KEY" ] && [ -n "$ALPACA_SECRET" ] && echo "alpaca keys present" || echo "ALPACA KEYS MISSING: stop and tell Nick"
   cd ~/sprint && sha256sum sprint/specs/final_v2_exam.json sprint/specs/final_v2_models.json && df -h ~ | tail -1
4. L2 (2024-02-01 to 2024-07-31), once:
   cd ~/sprint && mkdir -p data/sprint/logs && .venv/bin/python tools/sprint_exam.py run --locked L2 --frozen <EXAM_SPEC_SHA> > data/sprint/logs/exam_L2.log 2>&1 && grep -E "^sprint_exam |^exam |^WARNING|^report:" data/sprint/logs/exam_L2.log || { echo "FAILED: exam L2"; tail -30 data/sprint/logs/exam_L2.log; }
5. L1 (2026-07-01 to 2026-10-30), once, only if step 4 did not print FAILED:
   cd ~/sprint && .venv/bin/python tools/sprint_exam.py run --locked L1 --frozen <EXAM_SPEC_SHA> > data/sprint/logs/exam_L1.log 2>&1 && grep -E "^sprint_exam |^exam |^WARNING|^report:" data/sprint/logs/exam_L1.log || { echo "FAILED: exam L1"; tail -30 data/sprint/logs/exam_L1.log; }
6. Zip everything and show both result tables:
   cd ~/sprint && .venv/bin/python -m zipfile -c ~/sprint_exam_results.zip data/sprint/exam_L2_*.md data/sprint/exam_L2_*.json data/sprint/exam_L1_*.md data/sprint/exam_L1_*.json data/sprint/trades_exam_*.csv.gz data/sprint/exam_log.jsonl data/sprint/logs/exam_*.log && ls -la ~/sprint_exam_results.zip
   for f in $(ls -tr data/sprint/exam_L2_*.md data/sprint/exam_L1_*.md); do echo "=== $f"; sed -n '/^## This period/,/^## FIN-H$/p' "$f"; done
   (send Nick the file ~/sprint_exam_results.zip)
```

What Nick sends back: step 1's commit line and status, step 2's last line, step 3's lines, steps 4 and 5's output, step 6's tables, and `~/sprint_exam_results.zip`.

Checks on the way in:
- Step 1: the commit is the frozen one Claude named, and `git status --short` prints nothing, or only `?? .venv/` (the sprint's Python environment, which the dirty-tree check ignores). Any ` M` line or a `??` file under `sprint/`, `tools/` or `tests/` makes steps 4 and 5 refuse.
- Step 2: 270 sprint tests pass.
- Step 3: "alpaca keys present". The exam spec's sha256 equals `<EXAM_SPEC_SHA>`, and the models file's equals exam step 1's.
- Steps 4 and 5:
  - a `sprint_exam run:` line saying FIRST READ, with the commit, the exam spec sha256 and the models sha256;
  - four `exam L2 ...` (then `exam L1 ...`) lines, one per finalist, each PASS or fail with its numbers. After L1 each line also gives the verdict: holds (passes both periods), mixed (one) or fails (neither);
  - `report:` with the report's path.
  - Any `WARNING:` line is a problem to look at, for example FIN-H's engine run differing from the reference's trades with rvol >= 1.06.
  - `FAILED` or `REFUSED:` means stop. A refusal happens before any request, and nothing locked was read.
- The reports list each symbol's sessions with bars and with 0DTE option bars. A session without option bars is skipped and counted; Alpaca has known option gaps on 2024-02-26 and 2024-03-15.
- Known before any result (Amendments 7 and 11):
  - each period is a few months, so a pass is evidence, not proof;
  - FIN-H and FIN-L were both negative without their best 5 trades on DEV;
  - FIN-HS's models learned from MODELED 2016-2024 option prices (and REAL DEV for L1);
  - a finalist that holds becomes a new versioned PAPER ledger that needs 40 forward paper trades (CLAUDE.md step 5), never real money without Nick's explicit yes.
