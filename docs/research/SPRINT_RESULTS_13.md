# Sprint results 13: T6's rule on 1927-1997 US industries (run 2026-11-03)

Pre-registration: SPRINT_PLAN "Round 13 pre-registration" and Addendum 13.1. Chart ran commit `13384e3` in `~/sprint13`; all six steps exited 0 and the 17 round 13 tests passed. Claude re-ran `tools/sprint_r13.py run` on the returned cleaned data (`sprint_data13.zip`, every file matching its sha256 manifest) and got the same JSON, 0 differences.

**Verdict: R13 FAIL.** It passes items 2-8, including all four luck checks, and misses item 1: its Sharpe edge over the market has a one-sided p of 0.0359 against the pre-registered 0.01. Nothing is promoted.

## PASS 1927-07-01..1997-12-31, 10 bps a side (BACKTEST on Ken French value-weighted industry returns)

| Series | Sharpe | CAGR | Max DD | 1927-1949 | 1950-1973 | 1974-1997 |
|---|---|---|---|---|---|---|
| R13 | 0.66 | 12.2% | -49.5% | 0.59 | 0.88 | 0.65 |
| D1 momentum only | 0.66 | 14.3% | -72.2% | 0.53 | 0.97 | 0.69 |
| D2 trend only | 0.57 | 10.0% | -47.4% | 0.45 | 0.91 | 0.57 |
| Market | 0.46 | 10.4% | -84.1% | 0.32 | 0.76 | 0.56 |
| Equal weight 10 | 0.52 | 11.3% | -82.3% | 0.38 | 0.85 | 0.61 |

Era columns are Sharpe ratios.

| Item | Result |
|---|---|
| 1 Sharpe above the market's, p < 0.01 | **no**: +0.20 a year, 95% CI -0.01 to +0.42, p 0.0359 |
| 2 drawdown smaller than the market's | yes: -49.5% vs -84.1% |
| 3 2 of 3 eras | yes: all 3 |
| 4 Sharpe > 0 at 50 bps | yes: 0.53 |
| 5 beats 95% of random industry picks | yes: 100% (their median 0.46, 95th percentile 0.52) |
| 6 beats 95% of shifted trend filters | yes, narrowly: 95.9% (median 0.54, 95th percentile 0.66) |
| 7 above the market's Sharpe in 95% of noisy runs | yes: 100% (median 0.59, worst 0.53) |
| 8 keeps 50% without its 10 best months | yes: 75.5% of 846 months |

## Readings

- **Strongest result of the sprint, still not proven.** The rule was steadier than the market in every era and survived every luck check, but its edge over the market is not significant at the bar set before the run. The bar was 0.01 because the rule was picked as round 12's best of 13; at 0.05 it would have passed. The FAIL stands.
- **After publication (SEEN 1998-01-02..2024-01-31, information: round 12 covered part of it):** R13 Sharpe 0.62 vs the market's 0.42, CAGR 10.3% vs 8.6%, max DD -26.0% vs -54.6%. Industry momentum was published in 1999 (Moskowitz & Grinblatt, *JF*, data 1963-1995), so these 26 years are the cleanest out-of-sample stretch relative to the literature. 1927-1997 was new to the desk, not to academia.
- **Where the edge comes from:** momentum alone (D1) matches R13's Sharpe with more return and a far deeper drawdown (-72%); the trend filter alone (D2) cuts the drawdown with less return. Together: about the same Sharpe as D1 at two thirds of its drawdown. CAPM: beta 0.55, alpha +4.6% a year.
- **Sized to a -20% worst drop (hindsight, information):** R13 at 0.40x earns 7.2% a year; the market at 0.16x earns 4.9%.
- **The deflated Sharpe (0.9999) is not meaningful here.** It takes the spread of trial Sharpes from round 13's three similar trials (sr_var 1.0e-5 per session). With an annualized spread of 0.16 it would be 0.59, and 0 at 0.32. It is reported as computed, but should not be read as a pass.

## Data notes

- Ken French Data Library, fetched by Chart: 25,670 sessions 1926-07-01..2024-01-31, 0 missing values; 668 later rows dropped while parsing and never saved.
- Spot checks: market 1931 -44.3%, 1933 +56.5%, 1974 -27.8%, 2008 -36.5%; 1987-10-19 -17.4%; Saturday sessions before 1952 (about 300 a year).

## Next (candidates only)

- A watch-only forward paper ledger for T6 (the ETF version), labeled "failed round 13 item 1", to collect forward evidence without promotion, if Nick agrees.
- rsi2's approved forward ledger (`wl50_rsi2`) still needs its module built.
