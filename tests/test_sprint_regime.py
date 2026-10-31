"""tools/sprint_regime.py (SPRINT_PLAN Amendment 6, holdout 2): frozen rule thresholds, the pass bar, the random
day-skip test and the HIST-trained learner applied to DEV trades. Synthetic trade files only."""
import gzip
import json
from datetime import date, timedelta

import numpy as np
import pandas as pd

import sprint_synth  # noqa: F401  (puts tools/ on sys.path)
import sprint_regime as SR
from sprint import features


def _trades(run, n, seed, planted=True, start=date(2024, 8, 5)):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        d = (start + timedelta(days=int(i // 3) * 1)).isoformat()
        rng_atr = float(rng.uniform(0.2, 1.0))
        rvol = float(rng.uniform(0.5, 1.6))
        big = rng_atr >= 0.61 and rvol >= 1.06
        pnl = float(rng.normal(25 if (planted and big) else -6, 20))
        r = {f: float(rng.normal()) for f in features.FEATURES}
        r.update(run_id=run, symbol="SPY" if i % 2 else "QQQ", day=d, signal_idx=89, entry_time="11:01", f_range_atr=rng_atr,
                 f_rvol=rvol, pnl=pnl, pnl_2x=pnl - 2)
        rows.append(r)
    return pd.DataFrame(rows)


def test_rules_are_the_frozen_thresholds():
    d = pd.DataFrame({"f_range_atr": [0.51, 0.52, 0.61, 0.70], "f_rvol": [1.2, 1.05, 1.0, 1.06]})
    assert list(SR.RULES["F"][2](d)) == [False, True, False, True]
    assert list(SR.RULES["G"][2](d)) == [False, False, True, True]
    assert list(SR.RULES["H"][2](d)) == [True, False, False, True]
    assert list(SR.RULES["I"][2](d)) == [False, False, False, True]
    assert {k: v[0] for k, v in SR.RULES.items()} == {"F": "otm_v1-010", "G": "otm_v1-040", "H": "otm_v1-040", "I": "otm_v1-040"}


def test_holdout2_cli_passes_a_planted_regime_and_fails_noise(tmp_path):
    dev = pd.concat([_trades("otm_v1-040", 900, 1), _trades("otm_v1-010", 900, 2, planted=False)])
    hist = pd.concat([_trades("hist_v1-005", 1200, 3, start=date(2016, 1, 4)), _trades("hist_v1-003", 1200, 4, planted=False,
                                                                                          start=date(2016, 1, 4))])
    with gzip.open(tmp_path / "trades_otm_v1_2026-10-31.csv.gz", "wt") as f:
        dev.to_csv(f, index=False)
    with gzip.open(tmp_path / "trades_hist_v1_2026-10-31.csv.gz", "wt") as f:
        hist.to_csv(f, index=False)
    rc = SR.main(["--trades", str(tmp_path / "trades_otm_v1_*.csv.gz"), "--hist", str(tmp_path / "trades_hist_v1_*.csv.gz"),
                  "--out", str(tmp_path / "out")])
    assert rc == 0
    res = {r["rule"]: r for r in json.loads(next((tmp_path / "out").glob("regime_holdout2_*.json")).read_text())}
    assert res["I"]["pass"] and res["I"]["p_day_skip"] < 0.10 and res["I"]["pf"] > 1.25
    assert not res["F"]["pass"]                                    # puts carry no planted edge
    assert res["L-call"]["trades"] > 0 and res["L-call"]["pf"] > res["L-call"]["base_pf"]
    assert (tmp_path / "out").glob("regime_holdout2_*.md")
