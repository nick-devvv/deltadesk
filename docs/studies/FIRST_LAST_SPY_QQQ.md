# First half hour -> last half hour (Gao, Han, Li, Zhou 2018) on our SPY/QQQ bars

Rule: at 15:30 ET take the sign of (10:00 close / previous close - 1); hold to the 16:00 close. Basis points, $0.04/share round trip subtracted, session bootstrap 95% CI. Underlying only; options not modeled.

| Symbol | Sessions | corr(first, last) | hit rate | mean trade (bp) [95% CI] | sum (bp) |
|---|---|---|---|---|---|
| QQQ | 28 (2026-09-22 to 2026-10-29) | -0.36 | 29% | -5.46 [-10.81, -0.01] | -152.8 |
| SPY | 30 (2026-09-18 to 2026-10-29) | -0.36 | 33% | -4.27 [-8.8, -0.03] | -128.1 |

With about 30 sessions per symbol this cannot confirm or reject the published effect (the paper uses 1993-2013; later re-creations report it weaker and concentrated in high-volatility days). It is recorded as a reproduction of the method on our data, not evidence of an edge. A forward paper candidate would need a preregistered hypothesis (see the Learning tab).
