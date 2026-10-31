# DeltaDesk v3.5 report

Release `2026-10-31.v3.5`. The frozen main policy `2026-10-29.v3` is unchanged: `config/policy.json` sha256 `4cf8b1b9631e…` matches the v3.4.2 baseline manifest (`docs/manifests/BASELINE_v3.4.2.json`, `M-83e38eed2db16e4d`). The strategy registry is also unchanged. `strategy.py` (including the frozen `detect_orb`), `exits.py` and `optionmath.py` are byte-identical to v3.4.2. Every strategy change ships as a new versioned module with its own ledger.

Nothing in v3.5 can place a real order. The broker stub still refuses, Schwab `/trader` paths are still refused, Robinhood is never connected, and Nick places every real trade by hand.

Status words used below:
- **IMPLEMENTED AND TESTED**: code plus automated tests, run here.
- **IMPLEMENTED, NOT LIVE-VERIFIED**: works in tests and the local browser, but hasn't yet been through a market session on Chart's computer.
- **RESEARCH ONLY**: findings or a paper candidate, with no edge claimed.
- **BLOCKED**: needs something this session can't reach.

## 1. Diagnosis: what was wrong, where, and what changed

| # | Finding (from the prompt) | Reproduced? | Final location | Fix | Status |
|---|---|---|---|---|---|
| C1 | `detect_orb` emits ORB_BREAK on the first acceptance close; no independent candle | Yes (read in source) | `strategy.py:229` (kept frozen, unchanged) | New strategy ORBX-15-5 in `orb_retest.py:119 run`, `:139 _run_side` | IMPLEMENTED AND TESTED; live ledgers NOT LIVE-VERIFIED |
| C2 | Markets chart root `#mkDesk` not covered by `.chartbox>#desk,#tv` | **Yes, measured in a browser**: the root grew 271 → 583 → 911 → 1241 → 1561 px in 12 s inside a 514 px box | `index.html:174-175` | One bounded sizing contract for both roots (`contain:size`, min 160 px, absolute root). After the fix the root equals the box on load, over 12 s of updates, after a tab switch, at 1440/1000/760/390 px and across timeframes | IMPLEMENTED AND TESTED (browser) |
| C3 | Contract lab: unbounded exit sample, fallback 180 s before exit, no future-quote check, entry-timing mismatch hidden, duplicates counted twice, versions pooled, in-memory throttles | Yes (source + tests) | `contract_lab.py:118 pick`, `:164 start`, `:217 _tracked`, `:293 exit_quote`, `:312 _score_v2`, `:378 report` | New scorer `2026-10-31.v3.5-contracts2`; v3.4.2 rows keep their old scoring and are reported apart | IMPLEMENTED AND TESTED |
| C4 | Catalysts mutated in place; `_x_read` returned the current object; a URL was treated as proof | Yes (regression test reproduces the 10:00/10:05/10:20 case) | `catalysts.py:229 _save`, `:295 as_of`, `:153 entry_eligible`, `:662 verify`; `lab.py:387 _xcats`, `:405 _x_read` | Immutable revisions + as-of reads; content verification by the desk's own fetch | IMPLEMENTED AND TESTED |
| C5 | Router ADMIT without gate/contract/fill; unknown regime/bar passed | Yes | `strategy_router.py:42 admit`, `:123 route`, `:157 authorize`, `:96 actionable_discipline` | Fail-closed eligibility (ELIGIBLE), a separate `authorize()` that alone leads to a specialist paper fill; end-to-end test | IMPLEMENTED AND TESTED |
| C6 | Non-atomic lifecycle; `portfolio[:2]` ids could collide (all 15 lab ledgers were "LA-…"); upsert overwrote | Yes (crash-injection tests) | `store.py:69 tx`, `:170 pos_insert`, `:179 pos_save`; `paper.py:123 buy`, `:231 sell`; `policy_old.py _open` | Transactions, full-ledger ids `<ledger>:<idea>`, idempotent retries, closed trades can't be reopened by a stale copy | IMPLEMENTED AND TESTED |
| C7 | Risk management ran after research; one shared rate budget | Yes (source); worst case measured in a test (a 0.6 s history pull no longer delays exits: risk step < 0.2 s) | `engine.py:1010 _manage_open`, `:1044 tick`; `lab.py:1234 step`; `schwab.py:290 _throttle`; `health.py` | Risk first; priority budget (risk 100%, normal 90%, research 70%); heartbeats; `/healthz` `/readyz` `/api/health` | IMPLEMENTED AND TESTED; live soak pending |

Other fixes made along the way:
- **Single server instance.** A second server started from the same folder now exits before starting any worker (`server.py _singleton`), so two engines can never trade the same ledgers. Checked by launching two copies.
- **Graceful shutdown on SIGTERM.**
- **Desk link token.** The token in the link is swapped for an HttpOnly cookie, and the address bar no longer shows it (302 redirect). Token and cookie checks use constant-time comparison. Cross-site browser POSTs are refused.
- **Future-dated quotes.** Option quotes timestamped more than 5 s in the future are marked not executable and counted on the health page.
- **Stale stock feed.** When the engine measures the stock feed as stale, new simulated entries are blocked and exits keep running.
- **Loss streak across specialists.** The losing streak now runs across all actionable specialist ledgers in time order, so switching ledgers or symbols never resets it (E2).

## 2. Reported vs reproduced

| Item | Source | What this session reproduced |
|---|---|---|
| ~$500 day (SPY 760P +$401, QQQ 692P +$136 = $537, noise-band paper ledger, Oct 30) | Chart's Oct 30 report | **Not verifiable here.** The live database is on Chart's computer. `tools/verify_day.py 2026-10-30 noise` opens it read-only and recomputes each position's P/L from its own orders and fees. Until Chart runs it, $537 is a report-derived sum of SIMULATED paper fills, not real money. One good day is not evidence of an edge. |
| Test count | earlier reports | **Fresh run here: 224 passed, 1 skipped** (pandas 3; the pandas-2.2 run is in §8). The skip is the node-based page test when node is absent. |
| ORB15 first-break underperformed controls | v3.3 study | Consistent on the same sessions in this study's baseline. Frozen ORB15 BASE (fixed 2R): stocks n 1,947, avg −0.224 R [−0.29, −0.16], controls −0.173, difference −0.051 [−0.135, +0.031]. SPY/QQQ n 30, avg −0.565 R. |
| Noise band 61 trades / PF 1.67 | v3.1 report | Not re-run (modeled option prices, in-sample dates). Still RESEARCH ONLY. |

## 3. The corrected ORB (ORBX-15-5): spec, study, ledgers

**Sequence enforced in code.** Opening range frozen → a candle closes beyond the boundary (B) → a later, separate candle sits entirely beyond the boundary, wick included (C: bull `C.low > OR.high` strictly, at least 1 tick) → a later candle touches the retest zone and closes back on the breakout side (R) → entry at the next quote after R closes, plus latency. `B.close < C.close < R.close`, and no candle fills two stages.

**Rules.** All parameters are provisional, fixed before testing, and unvalidated.
- **Opening range and candles:** 15-minute opening range, 5-minute candles.
- **Retest zone:** boundary ± max(2 ticks, 0.10×ATR5), frozen when C closes.
- **Failed retest:** a wick deeper than max(3 ticks, 0.30×ATR5) inside the range, or a close back inside it.
- **Timeouts and cutoff:** C must come within 6 candles of B, and R within 9 candles of C. No entry after 15:00.
- **Anti-chasing:** the entry quote must be within 0.5×ATR5 of the boundary, and the stop at most 1.5×ATR5 away.
- **Resets:** one per side per day, and only after a close back inside the range followed by a new break.
- **Gaps:** a gap candle can be B but never also C.
- **Identity:** episode ids are deterministic, so a restart or repeated polling can never create a second trade.

Tests cover overlap, equality, gaps, premature touches, missing/deep/close-failed retests, bear mirror, resets, the cutoff, no look-ahead (future candles changed, earlier episodes identical), restart identity, next-quote entry and trailing.

**Study** (`studies/orbx_study.py`, results in `docs/studies/ORBX_STUDY_2026-10-08_2026-10-29.md` + `.json`). The study runs on the staged Schwab bars: underlying only, $0.04/share, session-clustered 95% CIs, nothing tuned.

| Universe | Exit | n | win % | avg R [95% CI] | vs matched random entries |
|---|---|---|---|---|---|
| SPY/QQQ, 16 sessions | fixed 2R | 10 | 30 | −0.30 [−0.96, +0.72] | −0.01 [−0.81, +1.17]: **too few to say anything** |
| | OR-mid stop, 1R | 10 | 50 | −0.04 [−0.67, +0.72] | |
| Stocks (signal-only), 19 sessions | fixed 2R | 477 | 34 | −0.46 [−0.58, −0.34] | **−0.01 [−0.13, +0.12]: no edge over random** |
| | swing trail | 477 | 22 | −0.39 [−0.62, −0.13] | |
| | ATR trail | 477 | 16 | −0.22 [−0.55, +0.13] | |
| | OR-mid stop, 1R | 477 | 47 | −0.09 [−0.21, +0.04] | |

What the study shows:
- The retest-candle stop is tight: a median 0.33×ATR5 from the entry.
- So the $0.04 cost alone is about 0.14 R per trade on SPY/QQQ and 0.26 R on stocks, which is the main reason average losses exceed 1 R.
- The sequence did NOT beat random entries on this sample.

**Status: RESEARCH ONLY.** No parameter was changed after seeing these results; any change gets a new version id. Four paper ledgers (`orbx_swing`, `orbx_atr`, `orbx_2r`, `orbx_ormid`) take the same SPY/QQQ entries with different exits and collect forward evidence for hypotheses H-ORBX-1 and H-ORBX-TRAIL. The Learning tab shows every stage live.

## 4. News momentum (NEWS-MOM-1)

The machine-readable spec, with a reason for every threshold, is in `config/news_momentum.json`. The code is in `news_momentum.py:59 evaluate` (pure) and `live_step` / `manage`. All conditions below must hold:
- **The catalyst.** It must be entry-eligible: confirmed or attributed, CONTENT-VERIFIED by the desk's own fetch, and not resurfacing. It must be company-specific (3 tickers or fewer, an allowed category) and no more than 90 min old. If the desk received it more than 30 min after publication, it is flagged LATE.
- **The price reaction.** Price has moved at least 1.5 and at most 6 five-minute ATRs from the price when the news arrived. Volume over those minutes is at least 2× the same minutes over the prior 10 sessions; with no baseline, the check fails closed. The move has held for 10 min and given back less than half.
- **The entry.** Between 09:45 and 15:00. A 1-minute continuation close beyond the prior candle, with the last 3 closes on the news side of VWAP, at most 2 ATR5 from VWAP. The stop sits beyond VWAP or the last 5-minute candle's extreme and is at most 1.5 ATR5 away.
- **Instruments and exits.** Calls for up moves, puts for down moves; no shorting and no naked options. Exits, in order: the 20% premium line, then the 15:25 all-out, then the underlying stop or trail, then a 5-minute close back through VWAP. An ATR trail starts after +1R and only ever tightens.
- **Evidence.** No news backtest exists, because there are no historical publication/receipt times and none were invented. Evidence is collected forward from Mon Nov 2 (H-NEWS-1).

**Status:** IMPLEMENTED AND TESTED (synthetic data); RESEARCH ONLY; NOT LIVE-VERIFIED.

## 5. Underlying first

**The 20% trigger** (`underlying_first.py:47 premium_trigger`). The planned loss if sold at bid trigger B is `L(B) = M*(F-(B-s)) + fe + fx`. Requiring L(B) ≤ 20% × M × F gives `B ≥ F(1−0.20) + s + (fe+fx)/M`, rounded UP to a valid tick. The entry is rejected when B ≥ the bid or B ≥ F.
- **Worked case:** F = 2.03, 2 contracts, s = 0.01, fees $0.02/side. Then B = 1.64; the planned loss is $40.04 per contract and $80.08 total, inside an $81.20 budget. This is the same line the paper ledgers and contract lab already use.
- **Planned, not guaranteed:** gaps, halts, latency and manual orders can lose more.

**0DTE availability** comes from the chain actually received (`zero_dte`) and is never assumed. SPY/QQQ list daily expirations; most single stocks don't.

**Why a right-way stock move can still lose** (Black-Scholes MODEL numbers with stated spreads, not market data):

| Example | Stock move | Contract | IV | Entry ask | Exit bid | P/L per contract |
|---|---|---|---|---|---|---|
| A. right direction, fast move, 0DTE near the money: profit | 600.0 → 601.5 in 15 min | 600C, 5 h to expiry | 14% → 14% | 0.83 | 1.74 | +91.22 |
| B. right direction but slow: 0DTE decay wins | 600.0 → 600.4 in 150 min | 601C, 5 h | 14% | 0.42 | 0.30 | −12.43 |
| C. right direction, IV falls after news | 600.0 → 600.8 in 30 min | 600C, 2 days | 30% → 20% | 5.41 | 3.98 | −142.96 |
| D. right direction, cheap far-OTM 0DTE, wide spread | 600.0 → 600.6 in 20 min | 603C, 2 h | 14% | 0.05 | 0.00 | −5.44 |
| E. same move as B with a 7-day contract | 600.0 → 600.4 in 150 min | 601C, 7 days | 16% | 5.07 | 5.17 | +9.43 |
| F. puts: right-way down move, fast, 0DTE | 600.0 → 598.6 in 15 min | 600P, 5 h | 14% → 15% | 0.81 | 1.69 | +87.13 |

**Reach odds** (`reach_odds`). The question is how often the stock reaches the level the option needs, before the stop and before the cutoff, plus the median minutes to get there. The method is a block bootstrap of the stock's own recent sessions, scaled to today's volatility. The idea is credited to day-trader-skill's Time Machine (MIT). It is information only until it is calibrated (H-REACH-1, Brier skill > 0).

**Which underlying signals have predictive value? None yet.** On matched random-entry comparisons, the desk's tested signals have not beaten random entries out-of-sample: ORB15 first break, the VWAP rejection, and now ORBX. This was not hidden or tuned away.

**Which option checks earn their place:**

| Check | Status | Why |
|---|---|---|
| Spread %, quote freshness, future-dated quotes | Justified | Mechanics: execution cost and data validity |
| A delta band | Justified | Ties the option's move to the stock's |
| The 20% trigger being feasible | Justified | A tiny premium can't carry the fees and tick |
| Expiry vs expected holding time | Justified | Decay (examples B and E) |
| 0DTE availability | Justified | Must come from the actual chain |
| Event/IV checks | Justified | IV crush (example C) |
| Bucket (expiry × delta) preference | Unproven | The contract lab, scorer contracts2, is measuring it; needs 30 signals and 10 sessions first |

## 6. Learning journal (`learning.py`, new Learning tab)

- **decision_events.** Append-only (triggers refuse UPDATE/DELETE). Each event has an id, schema version, full ledger id, strategy and version, config hash, opportunity id, episode/position/order ids, event/receipt/decision time in UTC, ET clock, minutes since the open, a snapshot and data-quality flags. Missing values are recorded as missing.
- **The older candidates table.** Every write to it is mirrored by a trigger, so INSERT OR REPLACE can no longer erase history. Rows from before v3.5 are backfilled once and flagged.
- **Shadow outcomes.** Each skipped setup is scored once by the fixed rule SHADOW-1 (stock only, options unknown). These are never mixed with fills.
- **Hypotheses.** They are preregistered, with a spec hash and an append-only status history. Seeded: H-ORBX-1, H-ORBX-TRAIL, H-NEWS-1, H-REACH-1.
- **End-of-day job (16:10).** Shadow outcomes, the opportunity summary, then a WAL-safe backup via the SQLite backup API with an integrity check, keeping 7. The job resumes where it stopped if interrupted.
- **Exports.** CSV export of decisions, shadow outcomes, opportunities and hypotheses.
- **Run manifests.** Each study run records its parameters and source hashes. The ORBX study writes its manifest id into its report.

## 7. Research registry and hosting

See §9 (filled from the research runs) and `deploy/DEPLOY.md`.

## 8. Tests and validation levels

- **Unit/integration (here): 224 passed, 1 skipped** on pandas 3.x. New suites:
  - `tests/test_v35.py`: crash-injected lifecycle, ledger-id collisions, as-of catalysts, content verification, contract scorer v2, router end-to-end, health/CSRF/cookie over real HTTP, priority budget, risk-first measurement, learning journal, news momentum, underlying-first, verify_day.
  - `tests/test_orbx.py`: the ORB sequence suite.
- **Browser (local demo, Playwright):** chart sizing over time, tabs, widths and timeframes; Learning tab; header width at 11 widths. Adding the tab does not overflow the header more than v3.4.2 did; the min-width overflow between 1101 and 1252 px existed before.
- **Clean install:** see the package section of the handoff.
- **Live session soak: PENDING.** The first trading day for v3.5 is Mon Nov 2, 2026. §10 lists the measurements to take.

## 9. Research registry and hosting results

### Strategy research registry (`docs/research/STRATEGY_REGISTRY.md`, `docs/research/strategy_registry.json`; also shown on the Learning tab)

The registry has 25 entries (14 repos, 10 papers, 1 docs page). Every repo was read at a recorded commit, and none was executed.

| Rank | Count | What |
|---|---|---|
| A | 5 | Index intraday momentum and framework evidence, below |
| B | 14 | Promising but under-evidenced |
| C | 6 | Rejected |

**A: credible evidence.** All of it is index intraday momentum or framework work; none of it is ORB:
- the SPY "noise area" momentum of Zarattini, Aziz and Barbon (2024). The desk already runs it as the `noise` paper ledger, which is the source of the reported Oct 30 day;
- Gao, Han, Li and Zhou (2018) market intraday momentum (JFE);
- Baltussen et al. (2021) hedging-demand momentum (JFE);
- Martineau (2022), a NEGATIVE result: post-earnings drift is gone for large caps, so news trades must be same-day continuation;
- backtesting.py as a conservative cross-check framework (AGPL).

**B: promising but under-evidenced.**
- Stocks-in-play ORB: only the authors' own backtest, without slippage.
- The 5-minute index ORB: an independent study reproduced the gross edge, but costs cancelled it.
- The only code found for breakout → confirmation → retest (orb-quantower, C#, MIT): no results, and two parameters were never wired in.
- day-trader-skill (MIT, 3d0f4ef6…): one worked example.

**C: rejected.** Six repos, including one with look-ahead bias and one that fills at the same bar close that generated the signal.

**Reproduced on our data in this session:**
- **ORBX** (§3): no edge over random entries.
- **Gao et al. first-half-hour → last-half-hour on SPY/QQQ** (`studies/first_last.py`, `docs/studies/FIRST_LAST_SPY_QQQ.md`): on 28–30 recent sessions the relationship was REVERSED.

  | Symbol | Correlation | Mean trade | 95% CI |
  |---|---|---|---|
  | SPY | −0.36 | −4.3 bp | [−8.8, −0.0] |
  | QQQ | −0.36 | −5.5 bp | [−10.8, −0.0] |

  This sample can't overturn a 20-year published result. It does mean adopting the rule now is not supported. The registry's "next" fields list the tests to run as data accumulates.
- **Noise band:** already running forward as the `noise` ledger (see the $537 verification).

### Hosting (full comparison with official citations: `docs/research/HOSTING.md`; runbook: `deploy/DEPLOY.md`)

**The actual host.** "Cloud Desk" is not a host. The desk runs on Chart's always-on Linux computer. The Cloudflare quick tunnel is only a routing component, and Cloudflare documents quick tunnels as testing-only: the URL is random on every start, there's a 200-request concurrency cap, and there's no uptime guarantee. `watchdog.sh` restarts the process.

**Confirmed failure causes:**
- the link changes on every tunnel restart;
- the v3.4.1 Kronos pile-up, which caused the out-of-memory loop;
- the possibility of two server copies overlapping. That one is now prevented: v3.5 refuses to start workers when a second copy is launched.

Current memory pressure on the box hasn't been re-measured since v3.4.2. Runbook step 0 measures it.

**Recommendation (free):**
- systemd user units (`deploy/systemd/`): restart on failure, bounded backoff, a memory budget that covers the Kronos child, and linger so the desk runs with no one logged in;
- a health probe every minute that restarts only when the process is dead or hung, or the engine heartbeat is stale;
- **Tailscale Funnel** for a stable `https://<name>.<tailnet>.ts.net` address that any browser can open (free Personal plan, no domain). Tailscale Serve is the private variant.

**Paid alternatives (flagged, not provisioned):**
- a domain for a Cloudflare named tunnel;
- ngrok paid domains;
- Fly.io, Hugging Face Docker, Railway beyond $1/month.

Free cloud tiers either sleep or lose disk (Render, Koyeb), or need a card and a migration plus a tunnel (Oracle, Google Cloud).

**Security before going public:**
- the token cookie;
- a 10-minute pause after 20 bad tries;
- cross-site POSTs refused;
- **no token = no tunnel access**.

**Not deployed.** This session has no access to the box. Deployment is NOT claimed, and the steps are in the runbook.

## 10. Limitations and what is still open

- Not live-verified: the ORBX and news-momentum paper ledgers, content verification against real news sites (some reporting sites block or paywall; those stay observational), and the priority budget under real load.
- Single-stock news momentum depends on bars for that stock being in the lab/board caches. The tiered scan is ordered by open positions → confirmed candidates → board rotation, but per-tier coverage % is not yet shown on screen (E9).
- The contract lab has no scorer-v2 data yet. The ORBX SPY/QQQ sample (n 10) is too small to judge anything.
- The $537 verification needs Chart to run `tools/verify_day.py` (read-only).
