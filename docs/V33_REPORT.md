# DeltaDesk v3.3: honest measurement, strategy evidence, and the fixes from the outside audit

Your layout is unchanged. My trades, Scanner and the other pages look the same; new things live in the **Markets** tab, plus a small evidence badge on the plan card.

Some rules hold for every change here:
- Main paper rules (`2026-10-29.v3`) stay frozen, and every fix is a new, labeled version next to the old one.
- No code sends an order anywhere. You place every real trade in Robinhood.
- No new paid service is used. The paid xAI search stays off.

**The headline:** no strategy is qualified. Every desk setup family tested no better than random entries after costs, or only looked good in-sample. So v3.3 stops presenting any of them as an entry. Each plan carries its evidence status, and a research-only setup is a note, not a ping. The research ledgers keep collecting paper evidence, so a strategy can only earn back "qualified" with unseen data that beats a matched random-entry control.

## 1. Root causes (with file and function)

| # | What was wrong | Where | Fix (new version label) |
|---|---|---|---|
| 530 | The page parsed whatever came back. A Cloudflare tunnel error page (HTTP 530, HTML) showed up as raw HTML in the chart, and retries had no limit. | `index.html` `api()` / chart `fetchChart()` | `readJson()` checks the status and type before parsing. `explainHttp()` turns 530, 502–504, 401/403, 429 and HTML pages into one short line. The chart keeps the last good candles with a **No data** badge. It backs off 5 s → 10 s → 20 s → 60 s, and only a user action retries early. Server errors come back as `{"error","diag_id"}`, with the same id in the server log (`server.py _fail`). |
| A | The gate accepted a confirmed call after price fell back below the trigger, because it only checked the upper bound. Missing freshness or spread counted as fine. | `entrygate.py evaluate()` | **gate2** (`2026-10-30.v3.3-gate2`): both zone bounds, mirrored for puts. Back below the trigger is **WAIT FOR RETEST**: a retest must form its own new setup. Unknown freshness or spread fails closed. Keys carry the caller's scope (`G2-{scope}-…`), so ledgers never share gate state. |
| B | The gated comparison ledger mirrored the main ledger's fills (`_mirror_gated` ran after another ledger traded), so it never judged candidates main had rejected. | `engine.py paper_scan()` / `_mirror_gated()` | `_gated_independent()` decides every candidate itself, with its own gate scope, limits, size and losing streak. `discipline_gate()` now maps each ledger to itself (it used to send unknown ledgers to "real"). |
| C | 2-minute MACD was forward-filled from the bar's **opening** time, so the 11:30 value could change when the 11:31 minute arrived (look-ahead). | `diagnostics.py day_frame()` | **diag2**: a 2m feature becomes available only at its last minute's close. A test perturbs future bars and checks that earlier features don't change. |
| D | `replay.bs()` returns theta per minute and `_q()` multiplied by 60, while `optionmath` uses theta per calendar day. | `replay.py _q()`, `optionmath.py` | **replay2**: theta per calendar day everywhere (×1440 from the per-minute model), with the unit written down. |
| E | The stocks backtest filled at the signal candle's close at that candle's **opening** time; stops through a gap filled at the stop; 185 trades were decided before 09:45. | `scanner.backtest_day()` | **bt2** `backtest_day_v2()`: decide at the bar's close, fill at the next bar's open plus latency, gap-through stops fill at the open, first decision at 09:45. `backtest.run_inplay` uses bt2 by default; `legacy=True` reproduces the old report. |
| F | `paper.buy()` compared the ask with the limit, but the simulated fill adds slippage, so ask 2.01 + 0.02 could "fill" a 2.02 limit. The 20% line came from the limit, not the fill. | `paper.buy()` | **exec2** for the strict ledgers (gated, board, earn_post, router, spec_*): fill = ask + $0.01 and must be ≤ the limit. Exit = bid − $0.01, with $0.02 fees per side. The 20% line is recomputed from the actual fill and rejected if infeasible. Zero size and non-100 multipliers are rejected. The stated latency (signal + 1 s) is enforced, not just logged. |
| G | The aggregate cache keyed on the day only, so a corrected history or another symbol could reuse a stale 2m/5m frame. "Complete" meant the clock passed, not that every minute existed. | `indicators.aggregate()`, `aggregate_multi()` | The cache keys on a hash of the frame's content. `require_all=True` also needs every constituent minute. |
| H | Trade-level bootstrap intervals (trades within a session aren't independent), versions mixed in one total, and 433 diagnostic setups reported like 433 executions. | `evaluation.py` | **eval2** `stats_v2()`: session-clustered bootstrap, every win counted, and results split by policy/execution version. The diagnostics header says its setups are not executions and its option quotes are modeled. |

Schwab: the v3.2 lifecycle (six states, numbered stream generations, connect verifies before restarting the stream, LOGOUT on retire) is kept. The repeat connect/disconnect/reconnect and stale-worker tests still pass. No live Schwab check was possible from here.

## 2. What's new

**Strategy evidence (new modules)**
- `config/specialists.json` registers 18 experiments: the frozen v3 families, the noise band, in-play ORB5, four filters/windows, the MACD video strategy, the gated baseline, and the ORB15 base and first-retest studies. Each has its spec, evidence and status: DRAFT / RESEARCH ONLY / PAPER QUALIFIED / PAUSED / RETIRED. `qualified` is empty.
- `strategy_registry.py`: the first time a spec is seen, its sha256 is stored. An edited spec shows **SPEC CHANGED** and drops to research only, so a tested definition can't be quietly changed after its results are known. Every evaluation run is appended to an attempt log.
- `strategy_router.py` (**router1**): one route per candidate. The checks run in order: data health, qualification status, window/regime/warmup, then shared portfolio limits across every specialist together (2 open, 4 ideas a day, losing-streak stop). Each decision stores the record and versions. With nothing qualified, every route ends in **SHADOW** (logged with the reason) or **REJECT**.
- `walk_forward.py`: expanding session folds with an inner split and an optional embargo, so a fold never sees its future (tested).
- `matched_benchmarks.py`: stock outcomes with conservative fills, seeded random-entry controls matched by ticker, day, side, window, stop distance, target and costs, a session-paired difference, and Holm adjustment.
- `research.py` (**research1**): the ORB15 BASE and first-RETEST signal study on the stocks bars, split into development vs later blocks, compared with the controls, walk-forward, Holm-adjusted, and logged as attempts. Writes `reports/research_<date>.md/.json`.

**On the page**
- **Plan card:** a **Research only** badge (and the headline reads RESEARCH SETUP instead of ENTRY CONDITIONS MET), or **Your idea** for a level you picked.
- **Plan text** (what Chart repeats): RESEARCH ONLY replaces ENTER, and "CONTRACT (research only, not an instruction)" replaces BUY.
- **Markets → Strategy evidence:** every experiment, its status, where/when it applies, the evidence, why, and today's router counts.

**Alerts:** setup alerts only ping for PAPER QUALIFIED families, which today is none. A research-only setup writes a "RESEARCH SETUP (not an entry)" note instead.

**Paper ledgers:**
- **board** (stock setups board through the gate, exec2) records the X read with each trade as context, never as a trigger.
- **earn_post / earn_pre:** earnings research.

**X, news and earnings (free):** `grok/X_SCAN_PROMPT.md` is a new Chart routine.
1. Chart reads `GET /api/x/targets` (up to 12 names, earnings first) and searches X with Grok's own access.
2. It finds the original sources and posts them to `/api/news` with `via:"x_scan"`. Trader, consumer and fundamentals sentiment stay separate, with sample counts.
3. It posts sourced results to `/api/earnings/results` and call statements to `/api/earnings/call`.

If Chart can't search X in a run, it sends nothing and replies `X SEARCH UNAVAILABLE`. Posts-only stories stay unverified and can never trigger anything.

**Chart's context:** `strategies` (qualified list and each experiment's status). The coach prompt now forbids calling a research-only setup an entry.

## 3. Tests and checks run here
- **Full suite:** 140 passed, 1 skipped on pandas 3 and on pandas 2.2.
- **New tests:**
  - defects A–H, one or more each (`test_v33_fixes.py`);
  - the HTML 530 / HTML 200 / malformed JSON / 401 / 403 / 429 / 500-with-id cases run through the page's own code (`test_v33_http.py`);
  - the board ledger, x_targets, sentiment separation, and earnings sources (`test_v33.py`);
  - registry immutability, router SHADOW/REJECT/ADMIT with shared limits, walk-forward isolation, reproducible matched controls, the causal signal study, no order path, and the evidence status in Chart's context (`test_v33_router.py`);
  - a research-only plan never reads as an entry (`test_v32.py`).
- **UI in a demo server** (fake Schwab, scanner world):
  - no horizontal scroll at 1280 / 1440 / 1920 / 390;
  - My trades unchanged;
  - the Strategy evidence panel renders 18 rows, with "none qualified" and router counts;
  - the plan badges render (RESEARCH SETUP + Research only, and Your idea).
- **The 530 path in the browser:**
  - **outage:** during a 20 s fake Cloudflare 530 the chart made 3 requests (backoff), kept the last candles, and showed No data with the one-line reason;
  - **user action:** a timeframe switch during the outage made 1 request;
  - **recovery:** after the outage it came back to Live by itself.
- **Signal study CLI:** run end to end on a 25-ticker × 49-session synthetic random-walk file (~4.5 minutes). It promoted nothing, as it should on noise.

## 4. Status of every strategy

**No strategy is changed for real use:** real trades stay yours, by hand.

**Tested offline only:**
- every fix in section 1;
- the router and registry;
- the signal study, on synthetic data.

**Disabled as entry instructions (research only), with the reason:**

| Strategy | Why |
|---|---|
| ORB break, ORB retest, failed break, VWAP reclaim, VWAP + MACD | Negative per trade in the Sep 22 – Oct 29 diagnostics. |
| PDH / PDL retest | Too few trades to say anything. |
| All v3 setups together | 433 setups at −$9.00/trade vs coin flip −$6.73 and opposite direction −$4.43: worse than random. |
| Noise band | +$22.48/trade but in-sample and carried by a few all-day winners. |
| In-play ORB5 | Negative, and bt1 had look-ahead fills. |
| SPY-alignment filter | No improvement. |
| Gated baseline | Collecting forward outcomes. |

**Retired:** RVOL ≥ 2 filter, ADX > 25 trend filter, morning-only window, and the MACD video strategy (5m cross, 2R): 90 outcomes, 24.4% positive, −0.416R. Its 86% claim was not reproduced.

**Draft (to be measured):** the ORB15 base signal and the first-retest variant. Run `research.py` on the real stocks bars.

**Evidence from the outside audit** (rounds 2–3, the filters and video numbers) is recorded with that source. Their data files were not supplied, so those numbers are not reproduced in this repo.

## 5. Checks only Chart's computer can do
1. **The 530 cause.** A 530 page comes from Cloudflare, not from Schwab. The desk runs on a quick tunnel (`*.trycloudflare.com`):
   - Cloudflare documents that its hostname changes each time the tunnel is created, and that it has no uptime guarantee and is meant for testing.
   - Error **1033** means Cloudflare can't find a running `cloudflared` for the tunnel. **1016** is an origin DNS error.

   On Chart's computer:
   - check that `cloudflared` is running;
   - check what `watchdog.sh` does when it restarts it (a new link each time);
   - read the 1xxx code in the error page.
2. **Schwab live:** status `connected`, the stream live, instrument search, and a chart for a non-streamed ticker (REST).
3. **SEC EDGAR** from Chart's computer (with `SEC_USER_AGENT`).
4. **X access:** does Chart's Grok plan let the routine search X? If not, it replies `X SEARCH UNAVAILABLE` and the desk shows that.
5. **The real signal study:**

   ```
   python3 research.py --csv reports/backtest_inplay_bars_2026-09-22_2026-10-29.csv
   ```

   This is about 15–25 minutes for ~125 names; add `--paths 20` for a quicker pass. Those Sep–Oct bars were used to design v3, so the result is diagnostic, not unseen evidence.

## 6. Commands
- Tests: `cd ~/desk && python3 -m pytest -q tests/`
- Re-run the backtest with the fixed stocks replay: `python3 backtest.py --from 2026-09-22 --to 2026-10-29 --inplay-csv reports/backtest_inplay_bars_2026-09-22_2026-10-29.csv` (bt2 by default)
- The signal study: see 5.5.
- Evidence table: `curl -s "http://127.0.0.1:8765/api/strategies?k=$(cat DESK_TOKEN.txt)" | head -c 600`

## 7. Ready for the next forward paper session when
- the tests pass on Chart's computer;
- `/api/schwab/status` says connected and the stream is live;
- `/api/chart` returns JSON (not HTML) for SPY and for NVDA;
- `/api/strategies` shows `qualified: []` and 18 experiments;
- the X scan either posts sourced items or replies X SEARCH UNAVAILABLE;
- the tunnel link has stayed the same through a full session (no 530s), or you know the new link after a restart.

**What would change a status:** at least 100 paper outcomes over 30+ sessions after the strategy's registration date. Net expectancy after costs must have a session-clustered 95% interval above zero, and it must beat its matched random-entry control after Holm adjustment. That is a review point, not a promise of profit.
