# Sprint study (auto), 2026-10-31

Every number is a BACKTEST with a MODELED spread, 1 contract per signal; DEV results are in-sample. Not financial advice.

Candidate rule: base cost, DEV, >= 60 trades, PF >= 1.25, PF 2x > 1.0, best per family. Runs in the log: 365.

| family | candidate | trades | exp $ | PF | PF 2x |
|---|---|---|---|---|---|
| failed_break | setups_v2-034 | 207 | 33.87 | 2.357 | 1.657 |
| failed_high | none held up | | | | |
| flush | none held up | | | | |
| noise | none held up | | | | |
| orb | none held up | | | | |
| pd_retest | none held up | | | | |
| time_1030 | otm_v1-008 | 361 | 15.96 | 1.965 | 1.809 |
| time_1100 | otm_v1-026 | 351 | 7.28 | 1.616 | 1.461 |
| vwap_macd | none held up | | | | |

## When does each strategy work? (walk-forward learner)

### Learner: otm_v1-008

Walk-forward: models refit each month on earlier months only; out-of-sample from 2025-02 (21 months with trades, the first 6 used only for training). BACKTEST, DEV, MODELED-SPREAD.

| | trades | win % | exp $ | PF | PF 2x | total $ | max DD | skipped | beats random skips | PASS |
|---|---|---|---|---|---|---|---|---|---|---|
| no model (base) | 253 | 7.5 | 15.79 | 1.917 | 1.766 | 3995.85 | -1559.58 | - | - | - |
| logit | 104 | 3.8 | -2.84 | 0.854 | 0.787 | -295.32 | -1245.66 | 149 | 0.125 | no |
| ridge | 42 | 7.1 | -13.51 | 0.276 | 0.252 | -567.47 | -738.01 | 211 | 0.135 | no |
| buckets | 237 | 7.6 | 15.97 | 1.914 | 1.764 | 3783.8 | -1559.58 | 16 | 0.335 | no |

What the bucket rule learned (last fit, training trades only):

| time | day | train trades | train exp $ | skip |
|---|---|---|---|---|
| 10:30-12:00 | chop | 164 | 33.59 |  |
| 10:30-12:00 | neutral | 120 | 3.42 |  |
| 10:30-12:00 | trend | 57 | 1.73 |  |

Strongest logit weights (last fit; + = more likely a winner): f_vwap_x60 +0.553, f_gap -0.553, f_rvol -0.426, f_vwap_dist -0.39, f_range_atr +0.385, f_prev_range -0.321, f_er30 -0.292, f_noise_true +0.245


### Learner: otm_v1-026

Walk-forward: models refit each month on earlier months only; out-of-sample from 2025-02 (21 months with trades, the first 6 used only for training). BACKTEST, DEV, MODELED-SPREAD.

| | trades | win % | exp $ | PF | PF 2x | total $ | max DD | skipped | beats random skips | PASS |
|---|---|---|---|---|---|---|---|---|---|---|
| no model (base) | 251 | 5.2 | -1.19 | 0.903 | 0.816 | -297.6 | -1634.21 | - | - | - |
| logit | 67 | 9.0 | -3.91 | 0.684 | 0.618 | -262.19 | -461.63 | 184 | 0.525 | no |
| ridge | 13 | 23.1 | -4.04 | 0.5 | 0.426 | -52.48 | -67.5 | 238 | 0.795 | no |
| buckets | 219 | 5.0 | -9.7 | 0.231 | 0.207 | -2123.42 | -2270.68 | 32 | 0.005 | no |

What the bucket rule learned (last fit, training trades only):

| time | day | train trades | train exp $ | skip |
|---|---|---|---|---|
| 10:30-12:00 | chop | 99 | 12.76 |  |
| 10:30-12:00 | neutral | 107 | 7.96 |  |
| 10:30-12:00 | trend | 127 | 4.56 |  |

Strongest logit weights (last fit; + = more likely a winner): f_adx -1.081, f_day_ret -0.916, f_vwap_dist +0.868, f_range_atr -0.853, f_gap -0.834, f_er30 +0.626, f_noise_true +0.626, f_event +0.576


### Learner: setups_v2-034

Walk-forward: models refit each month on earlier months only; out-of-sample from 2025-02 (23 months with trades, the first 6 used only for training). BACKTEST, DEV, MODELED-SPREAD.

| | trades | win % | exp $ | PF | PF 2x | total $ | max DD | skipped | beats random skips | PASS |
|---|---|---|---|---|---|---|---|---|---|---|
| no model (base) | 160 | 10.6 | 42.23 | 2.681 | 1.886 | 6756.85 | -1411.48 | - | - | - |
| logit | 29 | 20.7 | 75.39 | 4.234 | 3.032 | 2186.39 | -440.73 | 131 | 0.795 | no |
| ridge | 55 | 18.2 | 64.36 | 3.735 | 2.644 | 3540.03 | -427.58 | 105 | 0.69 | no |
| buckets | 154 | 9.7 | 39.03 | 2.531 | 1.779 | 6010.76 | -1411.48 | 6 | 0.1 | no |

What the bucket rule learned (last fit, training trades only):

| time | day | train trades | train exp $ | skip |
|---|---|---|---|---|
| 09:30-10:30 | chop | 143 | 6.56 |  |
| 09:30-10:30 | neutral | 11 | 31.94 |  |
| 09:30-10:30 | trend | 1 | -34.81 |  |
| 10:30-12:00 | chop | 25 | 152.16 |  |
| 10:30-12:00 | neutral | 10 | -25.12 |  |
| 10:30-12:00 | trend | 7 | -24.27 |  |

Strongest logit weights (last fit; + = more likely a winner): f_rvol -1.531, f_gap -1.328, f_prev_ret -1.254, f_vixy_pctl -0.749, f_prev_range +0.727, f_weekday -0.568, f_overlap30 -0.542, f_di -0.395



## Combined book

### Combined book (479 sessions, 1 contract per signal, BACKTEST, MODELED-SPREAD)

| sleeve | trades | per session | % sessions | exp $ | PF | PF 2x | total $ | total 2x $ | max DD | worst day | Sharpe | daily CI95 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| otm_v1-008 | 361 | 0.75 | 0.315 | 15.96 | 1.965 | 1.809 | 5761.05 | 5124.03 | -1532.11 | -120.76 | 0.75 | (-7.29, 39.14) |
| otm_v1-026 | 351 | 0.73 | 0.311 | 7.28 | 1.616 | 1.461 | 2555.06 | 2065.7 | -1628.91 | -80.88 | 0.45 | (-7.49, 23.97) |
| setups_v2-034 | 207 | 0.43 | 0.303 | 33.87 | 2.357 | 1.657 | 7010.6 | 4666.78 | -1217.78 | -134.68 | 1.1 | (-0.95, 34.43) |
| BOOK | 919 | 1.92 | 0.562 | 16.68 | 2.003 | 1.662 | 15326.71 | 11856.51 | -2199.57 | -245.02 | 1.09 | (-3.99, 76.13) |

Correlation of daily P/L (near 0 or negative = the sleeves diversify each other):

| | otm_v1-008 | otm_v1-026 | setups_v2-034 |
|---|---|---|---|
| otm_v1-008 | +1.00 | +0.78 | -0.01 |
| otm_v1-026 | +0.78 | +1.00 | -0.01 |
| setups_v2-034 | -0.01 | -0.01 | +1.00 |

Same symbol and side held at the same time in two sleeves: 310 trade pairs.


### Combined book (479 sessions, 1 contract per signal, BACKTEST, MODELED-SPREAD)

| sleeve | trades | per session | % sessions | exp $ | PF | PF 2x | total $ | total 2x $ | max DD | worst day | Sharpe | daily CI95 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| otm_v1-008 | 361 | 0.75 | 0.315 | 15.96 | 1.965 | 1.809 | 5761.05 | 5124.03 | -1532.11 | -120.76 | 0.75 | (-7.29, 39.14) |
| otm_v1-026 | 351 | 0.73 | 0.311 | 7.28 | 1.616 | 1.461 | 2555.06 | 2065.7 | -1628.91 | -80.88 | 0.45 | (-7.49, 23.97) |
| setups_v2-034 | 207 | 0.43 | 0.303 | 33.87 | 2.357 | 1.657 | 7010.6 | 4666.78 | -1217.78 | -134.68 | 1.1 | (-0.95, 34.43) |
| BOOK (daily stop $150) | 918 | 1.92 | 0.562 | 16.04 | 1.963 | 1.629 | 14724.01 | 11275.81 | -2568.37 | -245.02 | 1.04 | (-5.51, 75.65) |

Daily stop skipped 1 entries.

Correlation of daily P/L (near 0 or negative = the sleeves diversify each other):

| | otm_v1-008 | otm_v1-026 | setups_v2-034 |
|---|---|---|---|
| otm_v1-008 | +1.00 | +0.78 | -0.01 |
| otm_v1-026 | +0.78 | +1.00 | -0.01 |
| setups_v2-034 | -0.01 | -0.01 | +1.00 |

Same symbol and side held at the same time in two sleeves: 310 trade pairs.

