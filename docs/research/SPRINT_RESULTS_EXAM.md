# Sprint exam results: the locked periods L2 and L1 (2026-11-01)

**Every number here is a BACKTEST on a locked period:** out-of-sample, run once, never used to choose any rule.
- **Options:** REAL Alpaca 0DTE option bars with the pre-registered 2% MODELED half-spread and $0.65 per contract per side.
- **Shares:** real Alpaca stock 1-minute bars.
- Nothing here is a live or paper fill. Not financial advice.

## What was run

- **Spec:** the frozen exam of SPRINT_PLAN Amendment 11.
  - Code commit `df6f75d`.
  - Exam spec sha256 `6a27dbeac269…ce864`.
  - Models sha256 `7f4b9951e53f…8dc97`.
  - Engine `2026-11-01.sprint3`, on Chart's computer.
- **L2** (2024-02-01..07-31): the first run and one re-run crashed on network errors before producing a result. Re-run 2 finished at 02:54.
- **L1** (2026-07-01..10-30): the first run and six re-runs crashed on TLS handshake timeouts to Alpaca. Re-run 7 finished at 05:30.
- **Valid crash re-runs:** each attempt used the same commit, spec and models (exam_log.jsonl). Each period logged exactly one `done`, so no result existed before the finished run. Amendment 11 allows crash re-runs.

## Results

| Finalist | L2 trades | L2 exp $ | L2 PF | L1 trades | L1 exp $ | L1 PF | Verdict |
|---|---|---|---|---|---|---|---|
| FIN-H (far-OTM calls, rvol >= 1.06) | 110 | -5.49 | 0.356 | 92 | -1.42 | 0.847 | **fails** (both periods) |
| FIN-L (logit P(win) >= 0.5) | 97 | -4.30 | 0.475 | 65 | -8.75 | 0.160 | **fails** |
| FIN-HS (sized 0/1/2; per contract) | 110 (93 contracts) | -6.74 | 0.319 | 92 (86 contracts) | -6.76 | 0.340 | **fails** |
| NB-VOL (noise band, shares, vol-sized) | 342 | +2.65 | 1.092 | 220 | +1.95 | 1.072 | **fails**: random direction p 0.19 and 0.31, bar p < 0.10 |
| reference (otm_v1-040 unfiltered) | 334 | -3.12 | 0.569 | 257 | -5.18 | 0.415 | - |

**Both periods together** (information only, computed by code from the two trade files; not a new test):

| Finalist | Trades | Exp $ | PF | Total $ |
|---|---|---|---|---|
| FIN-H | 202 | -3.64 | 0.590 | -734.64 |
| Reference | 591 | -4.02 | 0.494 | -2,374.53 |
| NB-VOL | 562 | +2.38 | 1.084 | +1,335.39 |

By symbol, both periods together:
- **FIN-H:** SPY -0.47 a trade (PF 0.943), QQQ -4.86, IWM -5.98.
- **NB-VOL:** QQQ +14.45 a trade (PF 1.579), SPY +0.90, IWM -6.84.

These splits were seen after the exam, so they can't be acted on without a new pre-registered test.

## What it means

- **FIN-H, FIN-L, FIN-HS: dropped.**
  - The far-OTM call family lost in both locked periods.
  - Over the two periods together, the big-day filter (rvol >= 1.06) did no better than buying every day: -3.64 vs -4.02 a trade.
  - The learned sizing and the logit filter made things worse.
  - The run 7 edge was lumpy and in-sample, and it did not survive.
- **NB-VOL: not promoted.**
  - It made a little money in both periods.
  - But random entry directions with the same sizing and exits did as well about 1 time in 4 or 5. So the profit comes from the payoff shape (small losses, a few long winners), not from picking the direction.
  - Round 10's noise-band grid (Addenda 15.1 and 15.2) never touches L1 or L2 and is judged on its own holdouts and forward trades.
- **Paper ledger `otm_h`** (FIN-H's paper twin on main): its label should change from "BACKTEST out-of-sample" to "failed the locked-period exam (L2 and L1)". This is a desk change and waits for Nick's yes. Keeping it as a forward paper record costs nothing.
- **No locked period is left.**
  - L1 and L2 are spent.
  - Future finalists are judged on pre-registered holdouts, then 40 forward paper trades with real fills.
  - Suggestion (not yet adopted): reserve a new forward window, for example from 2026-11-02, and pull no data from it until a frozen exam asks for it.

## The network problem

The crashes were Python TLS handshake and read timeouts to `data.alpaca.markets` on Chart's computer. `tools/pull_alpaca.py` retried only HTTP 429/5xx answers, not network errors.

It now also retries network errors 6 times over about 9 minutes, then stops. The pulls are resumable, so re-running continues. Test: `tests/test_sprint_pull_alpaca_net.py`. Rounds 9 and 10 pull through it (round 10's own pull already had the same retry).
