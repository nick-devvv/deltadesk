# Sprint study (learn), 2026-10-31

Every number is a BACKTEST with a MODELED spread, 1 contract per signal; DEV results are in-sample. Not financial advice.


## When does each strategy work? (walk-forward learner)

### Learner: setups_v2-001

Walk-forward: models refit each month on earlier months only; out-of-sample from 2025-02 (23 months with trades, the first 6 used only for training). BACKTEST, DEV, MODELED-SPREAD.

| | trades | win % | exp $ | PF | PF 2x | total $ | max DD | skipped | beats random skips | PASS |
|---|---|---|---|---|---|---|---|---|---|---|
| no model (base) | 501 | 8.8 | 13.2 | 1.548 | 1.088 | 6613.1 | -2122.93 | - | - | - |
| logit | 139 | 10.1 | 3.85 | 1.134 | 0.81 | 534.66 | -1314.15 | 362 | 0.32 | no |
| ridge | 144 | 10.4 | 9.9 | 1.346 | 0.955 | 1425.85 | -1137.65 | 357 | 0.505 | no |
| buckets | 482 | 9.1 | 14.65 | 1.608 | 1.131 | 7063.62 | -2079.47 | 19 | 0.87 | no |

What the bucket rule learned (last fit, training trades only):

| time | day | train trades | train exp $ | skip |
|---|---|---|---|---|
| 09:30-10:30 | chop | 399 | 6.43 |  |
| 09:30-10:30 | neutral | 27 | 10.21 |  |
| 09:30-10:30 | trend | 4 | -26.65 |  |
| 10:30-12:00 | chop | 69 | 58.43 |  |
| 10:30-12:00 | neutral | 40 | -21.98 | SKIP |
| 10:30-12:00 | trend | 29 | 8.42 |  |
| 12:00-14:00 | chop | 3 | -11.09 |  |
| 12:00-14:00 | neutral | 24 | -6.48 |  |
| 12:00-14:00 | trend | 32 | -15.24 | SKIP |
| 14:00-close | chop | 2 | -9.34 |  |
| 14:00-close | neutral | 3 | -6.05 |  |
| 14:00-close | trend | 8 | -3.94 |  |

Strongest logit weights (last fit; + = more likely a winner): f_day_ret +0.651, f_range_atr +0.648, f_prev_ret -0.64, f_minute -0.459, f_er30 -0.372, f_weekday -0.355, f_prev_range -0.207, f_event +0.193


### Learner: setups_v2-005

Walk-forward: models refit each month on earlier months only; out-of-sample from 2025-02 (23 months with trades, the first 6 used only for training). BACKTEST, DEV, MODELED-SPREAD.

| | trades | win % | exp $ | PF | PF 2x | total $ | max DD | skipped | beats random skips | PASS |
|---|---|---|---|---|---|---|---|---|---|---|
| no model (base) | 357 | 10.1 | 20.17 | 1.738 | 1.219 | 7201.67 | -1519.62 | - | - | - |
| logit | 116 | 12.1 | 16.04 | 1.506 | 1.078 | 1860.63 | -842.29 | 241 | 0.49 | no |
| ridge | 129 | 10.9 | 44.8 | 2.409 | 1.711 | 5778.78 | -1282.52 | 228 | 0.865 | no |
| buckets | 357 | 10.1 | 20.17 | 1.738 | 1.219 | 7201.67 | -1519.62 | 0 | None | no |

What the bucket rule learned (last fit, training trades only):

| time | day | train trades | train exp $ | skip |
|---|---|---|---|---|
| 09:30-10:30 | chop | 289 | 7.53 |  |
| 09:30-10:30 | neutral | 18 | 24.78 |  |
| 09:30-10:30 | trend | 3 | -28.15 |  |
| 10:30-12:00 | chop | 48 | 87.99 |  |
| 10:30-12:00 | neutral | 29 | -23.99 |  |
| 10:30-12:00 | trend | 19 | 21.15 |  |
| 12:00-14:00 | chop | 2 | -13.91 |  |
| 12:00-14:00 | neutral | 19 | -5.91 |  |
| 12:00-14:00 | trend | 26 | -17.03 |  |
| 14:00-close | chop | 1 | -6.49 |  |
| 14:00-close | neutral | 1 | -4.35 |  |
| 14:00-close | trend | 8 | -3.94 |  |

Strongest logit weights (last fit; + = more likely a winner): f_range_atr +0.943, f_day_ret +0.591, f_er30 -0.57, f_minute -0.567, f_weekday -0.499, f_prev_ret -0.496, f_prev_range -0.302, f_event +0.214


### Learner: setups_v2-012

Walk-forward: models refit each month on earlier months only; out-of-sample from 2025-02 (23 months with trades, the first 6 used only for training). BACKTEST, DEV, MODELED-SPREAD.

| | trades | win % | exp $ | PF | PF 2x | total $ | max DD | skipped | beats random skips | PASS |
|---|---|---|---|---|---|---|---|---|---|---|
| no model (base) | 318 | 11.0 | 23.25 | 1.96 | 1.393 | 7393.84 | -828.49 | - | - | - |
| logit | 88 | 19.3 | 47.16 | 2.873 | 2.058 | 4150.31 | -530.53 | 230 | 0.76 | no |
| ridge | 148 | 12.2 | 19.15 | 1.722 | 1.224 | 2834.93 | -659.9 | 170 | 0.415 | no |
| buckets | 318 | 11.0 | 23.25 | 1.96 | 1.393 | 7393.84 | -828.49 | 0 | None | no |

What the bucket rule learned (last fit, training trades only):

| time | day | train trades | train exp $ | skip |
|---|---|---|---|---|
| 09:30-10:30 | chop | 304 | 11.87 |  |
| 09:30-10:30 | neutral | 12 | -29.57 |  |
| 10:30-12:00 | chop | 51 | 79.76 |  |
| 10:30-12:00 | neutral | 13 | -23.97 |  |
| 10:30-12:00 | trend | 6 | 126.89 |  |
| 12:00-14:00 | chop | 2 | -9.56 |  |
| 12:00-14:00 | neutral | 7 | -11.29 |  |
| 12:00-14:00 | trend | 9 | -14.11 |  |
| 14:00-close | chop | 2 | -9.34 |  |
| 14:00-close | trend | 1 | -9.65 |  |

Strongest logit weights (last fit; + = more likely a winner): f_minute -0.796, f_prev_ret -0.764, f_range_atr +0.665, f_day_ret +0.519, f_gap +0.467, f_di -0.443, f_er30 -0.362, f_prev_range -0.35

