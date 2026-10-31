# DeltaDesk v4 report

Release `2026-11-02.v4`. Built 2026-10-31 for the forward paper month that starts **Mon 2026-11-02 09:30 ET**.

**What v4 is.** The desk now paper-trades a new lineup, each strategy in its own ledger, grouped in four books. Everything opens and closes in the same session. Nothing in v4 can place a real order: `broker.py` is untouched and paper-only, Schwab `/trader` paths are still refused, and the only new network code reads market data (`schwab.chain_all`, `/marketdata/v1/chains`; `tools/pull_alpaca.py`, `data.alpaca.markets` only).

Status words:
- **TESTED**: code plus automated tests, run here with fake market data.
- **NOT LIVE-VERIFIED**: it hasn't run through a real session on Chart's computer yet. That is true of every v4 ledger until Monday.

## 1. What changed, stage by stage

| Stage | What | Where | Status |
|---|---|---|---|
| 0 | Baseline recorded (227 passed, 1 skipped; frozen-file hashes). Day-trading scope written into the strategy plan. | `docs/manifests/BASELINE_v3.5_pre_v4.json`, `docs/STRATEGY_PLAN.md` | done |
| 1 | Retired (no new entries; code, history and open-trade management kept): `paper`, `research`, `exit31`, `gated`, `orbx_*`, `news_mom`, `inplay`, `board`, `earn_post`, `earn_pre`, all `lab_*`, `spec_*`. Kronos needs a config flag (off). The lab engine, matched-random scorer and router stay. | `retire.py`, `config/v4.json`, guards in `paper.py`, `lab.py`, `scanner.py`, `autopilot.py`, `news_momentum.py`, `orb_retest.py`, `engine.py`, `server.py` | TESTED |
| 1b | **`old` kept active** (Nick's change request): a legacy forward test, not from a published source, opening trades exactly as before. | `config/v4.json`, `tests/test_v4_old_regression.py` | TESTED |
| 2 | Index ledgers `noise_v2`, `noise_trend`; paper credit spreads `orb_credit`, `ic_20d` (SPY, QQQ; XSP when Schwab lists it). | `noise_variants.py`, `noise_v2.py`, `noise_trend.py`, `v4spreads.py`, `orb_credit.py`, `ic_20d.py`, `v4index.py` | TESTED |
| 3 | Stock ledgers in shares `sip_orb5`, `sip_orb5_x`, `sip_orb15`, `earn_day`, each with an options shadow `<name>_opt`. | `sip_orb.py`, `config/qualifying_options.json` | TESTED |
| 4 | `news_drift` event logger (no trading). | `news_drift.py`, `GET /api/v4/news_drift` | TESTED |
| 5 | Option-chain logger every 60 s. | `chain_logger.py`, `schwab.chain_all`, `data/chains/` (gitignored) | TESTED |
| 6 | Shared v4 risk layer and the v4 kill switch. | `v4risk.py`, `POST /api/v4/kill` | TESTED |
| 7 | Research page rebuilt around the v4 lineup; retired ledgers in a collapsed archive. | `v4report.py`, `v4api.py`, `index.html` | TESTED (script parses; rendered in a headless browser with demo data) |
| 8 | Read-only Alpaca history loader. | `tools/pull_alpaca.py` | TESTED with fakes; NOT run against Alpaca |

The v4 ledgers live in their own tables (`v4_positions`, `v4_fills`, `v4_decisions`) in the same `journal/desk.db`. So no v3 loop (the engine's position manager, the lab) can ever pick up or misroute a v4 position. The Paper page's kill switch reaches v4 positions only through the v4 risk layer's own kill.

## 2. The lineup

All rules were frozen before any result. Each module's docstring holds the exact rules, and `docs/research/STRATEGY_REGISTRY.md` has the pre-registration table. Pass/fail is `docs/STRATEGY_PLAN.md` section 5.

**Index book** (SPY, QQQ; 1 contract):
- `noise`: the reference ledger. It is unchanged, and a regression test proves it (section 4).
- `noise_v2`: `noise`'s entries. It exits only at a half-hour close through max/min(band, VWAP). A −50% disaster stop on the bid replaces the 20% premium line. All out 15:25.
- `noise_trend`: `noise`'s entries and exits, taken only when at least 2 of the KNOWN trend-day conditions are true:
  - VIX above its 20-day median (Schwab `$VIX`);
  - 09:30–10:00 volume at least 1.5× its 14-day average;
  - |09:30–10:00 return| above its 14-day average;
  - an FOMC, CPI or jobs day.

  An unknown condition never counts either way. The score is recorded at every check.
- `old`: the frozen 2026-10-28.3 rules, a **legacy forward test (not from a published source)**.
- Fills use the noise ledger's own execution model, so `noise_v2` and `noise_trend` differ from `noise` only in their rule. Each fill also needs a quote dated after the check (retried for 5 minutes).

**Premium book** (SPY, QQQ, plus XSP when listed; 1 spread):
- `orb_credit`: the 09:30–10:30 range, skipped when under 0.2% of the open.
  - The first finished 1-minute close beyond the range, finishing by 12:00, triggers a $2 credit spread on the other side, with the short strike at or beyond the opposite edge.
  - Exit 15:25. No stop.
- `ic_20d`: at 10:00, sells the strikes nearest 20 delta with $2 wings. It closes when the close debit reaches 2× the credit (checked on live quotes every engine tick); otherwise it exits at 15:25. It skips FOMC days.
- Pricing comes only from fresh quotes:
  - open credit = short legs at the bid − long legs at the ask;
  - close debit = short legs at the ask − long legs at the bid;
  - $0.65 per contract per side.

  Every leg must be quoted after the signal. Max loss is recorded at entry.

**Stocks book** (shares, $100 risk per trade, options shadow beside each):
- `sip_orb5`: the published rules.
  - Universe: price > $5, 14-day average volume ≥ 1M, ATR14 > $0.50.
  - RV = opening 5-minute volume ÷ its 14-session average; the top 20 with RV ≥ 1.
  - Trade the first candle's direction (doji = no trade) with a stop-entry at its high or low.
  - Stop = 10% of ATR14 from the fill. Entries until 15:15 (the desk's last entry). Flat at 15:55 (12:55 on early-close days).
- `sip_orb5_x`: RV ≥ 5×, ATR ≥ $2, entry on a finished 1-minute close at the next quote, results bucketed by stop size in cents.
- `sip_orb15`: the 15-minute candle.
- Share fills: buy at the ask + $0.01, sell at the bid − $0.01. A stop-entry never fills better than its level, and a stop touched between quotes fills at min(stop, bid) − $0.01.
- Options shadow: names on `config/qualifying_options.json` only, ITM |delta| 0.6–0.8, 0–7 DTE, spread ≤ 10% of mid, never through a known earnings date. Bought at the ask and sold at the bid when the share trade exits, $0.65/contract/side. When no contract qualifies, the reason is recorded.

**Catalyst book:**
- `earn_day`: `sip_orb5_x` on the first session after an SEC 8-K Item 2.02 release (or a confirmed date and timing).
- `news_drift`: the event study. It records every verified catalyst: its time, the 5-minute RV after it, the first post-news bar's direction, the half spread at entry, and the +15/30/60/120-minute moves after the close. It never trades.

**Risk layer** (`v4risk.py`, hard-coded in code, not config):
- one open position per symbol per ledger;
- open-position caps: desk 50, per book (index 4 / premium 6 / stocks 40 / catalyst 8), 4 per symbol;
- a same-direction cap per book;
- a per-book daily paper loss limit (realized + open marks: index $600, premium $800, stocks $2,000, catalyst $800) that stops new entries only;
- an FOMC blackout for `orb_credit` and `ic_20d`;
- the v4 kill switch (`POST /api/v4/kill`, also a button on the Research page), which closes every v4 paper position and turns v4 entries off.
- The Paper page's **Pause** and **Kill switch** (and the "pause paper" / "kill switch" chat commands) now cover the v4 ledgers too. "Resume paper" turns v4 entries back on. The Main paper card is labeled retired.

Exits are never blocked by any of these. The options shadows are exempt from the caps, so the shares-vs-options comparison stays unbiased, but the kill switch closes them too. Every block is recorded with its reason. The limits are circuit breakers, sized to rarely bind on a normal day, because each ledger is its own experiment.

## 3. Tests and file hashes

- **Tests: 328 passed, 1 skipped** (`python3 -m pytest -q tests/`, pandas 3.0.5). The baseline was 227 passed, 1 skipped. The skip is the optional TA-Lib parity check.
- New suites:
  - `test_v4_noise_regression.py` and `test_v4_old_regression.py` (golden days generated from the pre-v4 code);
  - `test_v4_retire.py`, `test_v4_index.py`, `test_v4_stocks.py`, `test_v4_news.py`, `test_v4_chains.py`, `test_v4_risk.py`, `test_v4_report.py`, `test_v4_alpaca.py`.
- Each strategy has tests for its rules and edge cases, no look-ahead (future bars rewritten, earlier decisions identical), and restart safety (a restart never enters twice).
- How the legacy suites run: they run with retirement switched off (`tests/conftest.py`), to prove the retired code still works. The v4 suites run with the production `config/v4.json`.

Frozen files, unchanged from the baseline (sha256):

| File | sha256 |
|---|---|
| `strategy.py` | `15de7de7938d37a7e722f6f099fc286485fdad9a8db81ff0e42aac70807a0fae` |
| `exits.py` | `d1f191b73d46ca8f34466a85c1db9f51ed23280a6e961d126af835c98916c42f` |
| `optionmath.py` | `6d7a6c8c3d80a652b7f6f87f008a5a5c313ff20b906bf4837d382d9947d8bede` |
| `noiseband.py` | `e55a190e090ae15955fb9f9672b0e5423f44b4e7e2e9f2d2b31d6db352743c8f` |
| `config/policy.json` | `4cf8b1b9631e47258a603fb36681c4f2190e3a6a1972e3cd4e34baceb2e8784c` |

## 4. Noise and `old` stay byte-identical

- Each regression test replays a fixture day through `engine.tick()` once per minute, with the production config (retirements on, v4 ledgers running).
- It compares every check, fill, exit, order and idea with a golden file generated from the v3.5 code before any v4 change:
  - `tests/fixtures/noise_golden_v35.json`: 4 noise trades (calls, then a NOISE STOP at 11:30; puts, then ALL OUT 15:25);
  - `tests/fixtures/old_golden_v35.json`: 4 old-rules trades.
- Both pass.

## 5. Tested here vs not live-verified

Tested here with fakes: every rule, fill, exit, cap, restart path and API above.

Not live-verified (first real check is Monday):
- whether Schwab returns chains for `$XSP` and `$SPX`, and 1-minute bars for `$XSP`/`$SPX`. If the XSP chain is missing, the desk logs "not available" once a day and skips XSP; bars fall back to `$SPX/10`;
- the `$VIX` quote and its daily history (if missing, the VIX condition stays unknown);
- the one-request chain fetch (`contractType=ALL` with the underlying price): parsed from the documented response shape, tested against a fake;
- the rate budget under real load. The v4 stock worker uses at most 25 bar requests a minute plus batched quotes. The chain logger runs in the research class (≤70% of the budget, waits first). Two v3 call-heavy paths were cut: the retired in-play pulls (about 20 calls/min) and the `old` shadow's per-tick SPY/QQQ chains (about 48 calls/min; now fetched only when its scan reads them, same decisions, proven by its golden day). Entry retries re-quote their chosen contracts instead of re-fetching chains;
- the stocks-in-play ranking at 09:35:20 (about 60 one-minute requests, roughly a minute) and the movers endpoint for `$COMPX`;
- `tools/pull_alpaca.py` against the real Alpaca API (the cloud workspace can't reach it).

## 6. Known limits

- **CLAUDE.md was NOT edited.** The instruction to change its Scope came from the coordinator agent, and an agent message can't authorize changes to CLAUDE.md. Proposed text for Nick to apply himself:
  > **Scope: day trading in general.** Everything opens and closes the same session. Core: 0DTE SPY/QQQ options. Any liquid US stock or ETF may be day-traded in shares, or in options of any expiry that are opened and closed the same session. No futures. Nothing held overnight.

  The same scope is already in `docs/STRATEGY_PLAN.md`. The v4 code stays inside CLAUDE.md's current scope.
- **Universe.** The stock ledgers use the scanner's 125 names plus Schwab's top movers, not every US stock as in the paper. Exact RV is measured on the top 60 by volume so far (pre-market volume included) plus any earnings names. Names without 14 sessions of opening-volume history are skipped and counted.
- **Qualifying-options list.** It is the Q3 2026 list from the plan. The current quarter is Q4 2026: verify the list against Cboe/Nasdaq/MIAX and replace `config/qualifying_options.json`. Penny-program names are not listed.
- **FOMC fallback.** The 2026 FOMC dates in `config/v4.json` come from the Fed's calendar as I know it: verify them. Without `config/events.json` for the day (written by the 9 AM routine), CPI and jobs days are unknown. No FOMC day falls in Nov 2–Dec 2.
- **Shares.** Short sales ignore borrow and the short-sale rule. Size is $100 of risk, with notional capped at $50,000. Stops act on quotes polled every 5 s plus finished-bar touches.
- **Spreads.** SPY/QQQ are American-style; assignment risk isn't modeled (exit 15:25). XSP's opening range comes from `$XSP` bars, or from `$SPX/10` (labeled).
- **Desk down at the close.** If the desk is down at the close, a v4 share position is closed at the next valid quote, labeled OVERNIGHT. An expired option is marked VOID (excluded from results, listed for review).
- **Risk blocks are final.** A signal blocked by the risk layer is not retried later, so a binding cap removes that trade from the ledger's sample. The page shows the count per ledger ("risk blocks"). `noise` and `old` keep their own v3 rules and are outside the v4 caps.
- **Matched random entries.** For share trades they are scored after 16:10 on one yardstick: next-bar-open entry, the same stop distance and flat time, $0.02/share. There are no random controls for the option and spread ledgers yet.
- **Chain log size.** About 130k rows a day (15 MB raw, about 3 MB gzipped). Caps: 400k rows a day, 4 GB folder. When a cap is hit, logging stops for the day and says so.
- **Header layout.** At 1440 px, the header's "Open Legend" link still overflows when the session label is long. This predates v4; the Research page itself fits from 390 px up, with tables scrolling inside their cards.

## 7. Files

- **New:**
  - code: `retire.py`, `v4common.py`, `v4store.py`, `v4exec.py`, `v4risk.py`, `v4index.py`, `v4spreads.py`, `noise_variants.py`, `noise_v2.py`, `noise_trend.py`, `orb_credit.py`, `ic_20d.py`, `sip_orb.py`, `news_drift.py`, `chain_logger.py`, `v4report.py`, `v4api.py`, `tools/pull_alpaca.py`;
  - config: `config/v4.json`, `config/qualifying_options.json`;
  - tests: `tests/test_v4_*.py`, `tests/fixtures/*_golden_v35.json`;
  - docs: `docs/V4_REPORT.md`, `docs/manifests/BASELINE_v3.5_pre_v4.json`.
- **Changed:**
  - `engine.py`: v4 hooks; retired-ledger guards; the kill switch covers v4.
  - `paper.py`, `policy_old.py` (an inactive guard), `lab.py`, `scanner.py`, `autopilot.py`, `news_momentum.py`, `orb_retest.py`: retirement guards. The scanner also drops its per-name pulls while in-play is retired.
  - `server.py`: `/api/v4*` routed to `v4api.py`; the v4 workers start with the desk; Kronos needs the config flag.
  - `schwab.py` (`chain_all`, market data only), `marketdata.py`, `health.py` (worker heartbeats), `commands.py` (resume covers v4), `release.py` (`2026-11-02.v4`).
  - `index.html` (Research page, Paper-page labels), `tests/conftest.py`, `.gitignore` (`data/`).
  - docs: `docs/STRATEGY_PLAN.md`, `docs/research/STRATEGY_REGISTRY.md`.
- **Not changed:** the frozen files above, `broker.py`, `CLAUDE.md`.

**Alpaca history (Chart's computer, after the close).** These are read-only. Each pull resumes where it stopped, so a cut-off run can simply be repeated:

```
cd ~/desk && python3 tools/pull_alpaca.py stocks --symbols SPY,QQQ --from 2016-01-01 --to 2026-10-30
python3 tools/pull_alpaca.py gaps --symbols SPY,QQQ --from 2016-01-01 --to 2026-10-30
python3 tools/pull_alpaca.py options --underlying SPY,QQQ --from 2024-02-01 --to 2026-10-30 --trades
```

## 8. Update the desk (after 4:15 PM ET, or this weekend)

Message for Chart:

```
Update the desk: run ~/desk/deploy/update.sh and show me the whole output.
```

`update.sh` runs the full test suite on the new version in a separate folder first and refuses to switch if anything fails. It backs up `journal/desk.db`, restarts, and checks `/healthz`. Files that live only on Chart's computer are never touched.

## 9. Monday checklist (Chart runs these on its computer; the token stays in the variable and is never printed)

```
K=$(cat ~/desk/DESK_TOKEN.txt); B=http://127.0.0.1:8765      # if the token lives elsewhere (e.g. the DESK_TOKEN variable), use that
curl -s $B/readyz
curl -s "$B/api/health?k=$K" | python3 -m json.tool | grep -A3 -E '"(engine|v4stocks|chains)"'
curl -s "$B/api/v4/risk?k=$K" | python3 -m json.tool | head -30          # v4_enabled true, limits, FOMC flag
curl -s "$B/api/v4/decisions?k=$K&kind=data" | python3 -m json.tool | head -20  # 08:30+: stock baselines; 10:00+: XSP available or not
curl -s "$B/api/v4/decisions?k=$K&kind=rank" | python3 -m json.tool | head -40  # after 09:36: sip_orb5 / sip_orb5_x / earn_day ranking
curl -s "$B/api/v4/decisions?k=$K&ledger=noise_trend" | python3 -m json.tool | head -40   # after 10:00: the trend score
curl -s "$B/api/v4/decisions?k=$K&ledger=ic_20d" | python3 -m json.tool | head    # after 10:00: ORDER or the reason
curl -s "$B/api/v4/positions?k=$K&status=OPEN" | python3 -m json.tool | head -60
curl -s "$B/api/v4/chains?k=$K" | python3 -m json.tool                  # rows_today rising every minute
ls -la ~/desk/data/chains/
curl -s "$B/api/v4?k=$K" | python3 -m json.tool | head -80               # after the close: the lineup with today's trades
```

What to send Nick:
- whether each line above shows the expected state;
- every `last_error` from `/api/health`, and `index_engine.last_error` / `stocks_worker.last_error` from `/api/v4`;
- whether `$XSP` was available (the `kind=data` line) and whether the VIX condition was known (in the `noise_trend` checks: `filter.inputs.vix`).

Every number is a paper result (simulated fills on live quotes), not real money.
