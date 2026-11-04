# Sprint results 12: daily ETF rules on 2005-2015 (run 2026-11-03)

Pre-registration: SPRINT_PLAN "Round 12 pre-registration" with Addenda 12.1 (trailing stops) and 12.2 (GLD Parabolic SAR). Chart ran commit `154dccb` in `~/sprint12`; all seven steps exited 0 and the 30 round 12 tests passed. Claude re-ran `tools/sprint_r12.py check` and `run` on the returned raw data (`sprint_data12.zip`, every file matching its sha256 manifest) and got the same JSON, 0 differences.

**Verdict: all 13 trials FAIL.** Every one misses pass item 1 (one-sided p < 0.05/13 = 0.0038). T13 also fails item 3 (random entries). Nothing is promoted. Deflated Sharpe at N = 11,297: best 0.60 (T6).

## FRESH 2005-01-03..2015-12-31, 2x costs (10 bps a side): BACKTEST, out-of-sample (no round had used these years)

| Trial | p | Sharpe | CAGR | Max DD | Deflated Sharpe | Failed |
|---|---|---|---|---|---|---|
| T1 rsi2 | 0.0321 | 0.40 | 2.9% | -9.2% | 0.25 | 1 |
| T2 rsi2 stop 3% | 0.1934 | 0.24 | 1.9% | -3.0% | 0.11 | 1 |
| T3 rsi2 stop 5% | 0.1238 | 0.31 | 2.3% | -4.3% | 0.16 | 1 |
| T4 rsi2 stop 8% | 0.0936 | 0.34 | 2.5% | -6.6% | 0.18 | 1 |
| T5 trend200 | 0.0733 | 0.42 | 5.4% | -20.0% | 0.26 | 1 |
| T6 sector dual momentum | 0.0052 | 0.69 | 12.0% | -26.6% | 0.60 | 1 |
| T7 vol target | 0.0488 | 0.42 | 5.5% | -24.8% | 0.27 | 1 |
| T8 two-MA 2% exit | 0.4583 | 0.03 | 1.2% | -14.8% | 0.03 | 1 |
| T9 mix | 0.0421 | 0.47 | 4.2% | -10.1% | 0.31 | 1 |
| T10 rsi2 trail 3% | 0.2819 | 0.16 | 1.7% | -3.9% | 0.07 | 1 |
| T11 rsi2 trail 5% | 0.1336 | 0.30 | 2.2% | -4.0% | 0.15 | 1 |
| T12 rsi2 trail 8% | 0.0956 | 0.34 | 2.4% | -6.4% | 0.18 | 1 |
| T13 GLD Parabolic SAR | 0.0992 | 0.40 | 5.8% | -23.0% | 0.25 | 1, 3 |
| Buy-and-hold SPY | | 0.38 | 7.0% | -55.2% | | |
| Buy-and-hold GLD | | 0.42 | 7.9% | -45.6% | | |

Every trial except T13 passed items 2 (drawdown smaller than SPY's), 3 where it applies, and 4 (Sharpe over cash > 0).

## Readings

- **T6 is the near miss.** p 0.0052 against a bar of 0.0038. It would have cleared the original 9-trial bar (0.0056), but Addenda 12.1-12.2 added four trials before the run, so the bar was 0.0038 and the FAIL stands. The other windows (BACKTEST, information): 2000-2004 CAGR 9.9%, Sharpe 0.62, max DD -11.8% (SPY -2.4%, -47.5%); 2016-2024-01 CAGR 9.3% vs SPY 13.2%; 2024-08..2026-06 CAGR 0.1%. Its edge came from stepping aside in the two bear markets; it lagged SPY in the 2016-2026 bull market.
- **rsi2 replicates at the trade level.** FRESH: 807 trades, PF 1.44 (round 11 on 2016-2026: 1.41), expectancy +0.241% a trade, CI +0.006% to +0.445%, above every one of the 1,000 random-entry draws (their 95th percentile: +0.086%). 2000-2004: PF 2.19. The portfolio return is small because each ETF's slice sits in cash most of the time, so the daily-return test (item 1) misses.
- **Stops hurt rsi2.** Every fixed and trailing stop lowered Sharpe (0.40 without a stop; 0.16 to 0.34 with one) and cut the max drawdown (-9.2% to -3.0% / -6.6%). The 3% trailing stop was the worst. The same order holds at 1x costs.
- **The gold SAR rule has no edge.** T13 matched buy-and-hold GLD (Sharpe 0.40 vs 0.42) and beat only 83% of random entries (needed 95%).
- **Trend, vol target and the mix** cut SPY's drawdown by more than half (-55% to -10%/-25%) with Sharpe 0.42-0.47, the usual result for these rules, but not significant on 11 years.
- **Costs:** at 1x (5 bps a side) T1's Sharpe is 0.58 and T6's 0.71. Pass/fail used 2x as pre-registered.

## Data notes

- Single source: Stooq returned a web page for every symbol, so there was no cross-check (labeled "single source"). FRED timed out; cash came from Yahoo ^IRX, the pre-registered fallback.
- Check: all 16 symbols had 0 missing sessions, 0 OHLC flags, 0 extreme moves, 0 dividend flags. Claude's spot checks against known yearly total returns match: SPY 2008 -36.8%, 2013 +32.3%; QQQ 2008 -41.7%; GLD 2013 -28.3%; TLT 2008 +34.0%; SPY's 2007-2009 low on 2009-03-09 at -55.2%.

## Next (candidates only, not pre-registered)

- T6 on a much longer, untouched history: the Kenneth French Data Library's industry portfolios go back to 1926 (free). Seventy years would need a Sharpe of about 0.3 instead of 0.8 to pass. Industry momentum has its own peer-reviewed support (Moskowitz & Grinblatt 1999, *JF*).
- rsi2: the forward paper ledger `wl50_rsi2` (approved 2026-11-02) still needs its module built.
- Drop: rsi2 stops (fixed and trailing), T8, T13.
