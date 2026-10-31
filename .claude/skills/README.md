# Project skills

These load automatically when Claude works in this repo (Claude Code on Nick's Mac, or a Claude session with the repo attached).

## day-trader-skill (8 of 11 skills)

From [jakeschincariol/day-trader-skill](https://github.com/jakeschincariol/day-trader-skill), commit `3d0f4ef` (2026-10-20), MIT license (`LICENSE-day-trader-skill`). Copied unchanged.

| Skill | What it's for on this desk |
| --- | --- |
| `trader-scanner` | Find stocks moving or set up before and during the session (Nasdaq Trader symbol lists, Yahoo bars) |
| `trader-news` | Headlines per ticker and 8-K filings from SEC EDGAR, with how far each stock has moved |
| `trader-analyst` | What changed in a company's reported numbers (EDGAR XBRL + the earnings 8-K) |
| `trader-timemachine` | Replays the rest of the session 10,000 times and reruns the rule on past sessions: how often the target comes before the stop |
| `trader-entry`, `trader-exit` | Opening-range entry timing and stop/target planning for a stock plan |
| `trader-risk` | Checks a plan against loss limits |
| `trader-alerts` | Price, stop and target alerts |

**Left out on purpose:** `trader-broker` (sends orders through an Alpaca connector), `trader-budget` (share sizing for those orders) and `trader-pelosi` (congressional trades). Nothing in this folder can place an order. Nick places every real trade.

**How to use them on this desk:**
- They are research and discovery tools. A setup they flag is a lead, not a trade: no ledger trades a rule until it passes the gates in `docs/STRATEGY_PLAN.md`. The pack's own default (15-minute opening-range break, 1:1 target) came out "close to a coin flip" in its TSLA example.
- They read free Yahoo and SEC data. Yahoo is unofficial and can rate-limit. The desk's own numbers come from Schwab; when the two disagree, Schwab wins.
- Claude's cloud workspace can't reach Yahoo, SEC or Nasdaq Trader (blocked by its network proxy, checked 2026-10-31). Run them from Claude Code on the Mac: `cd ~/deltadesk && claude`.
- They write working files under `trader/` in the current folder; that folder is gitignored.
