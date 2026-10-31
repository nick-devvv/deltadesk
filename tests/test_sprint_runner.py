"""Sprint runner and puller end to end on synthetic data: tools/sprint_run.py writes one run-log row per run with the
columns of docs/research/sprint_runs.csv, a report and a trade file, robustness jobs run, results are deterministic
(a rerun gives the same numbers); tools/sprint_pull.py clips requests to the asked dates, resumes, pulls trades only
near the money, writes a gap report. Fake HTTP only, no network."""
import csv
import gzip
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

import sprint_synth as SS
from sprint import runner

ROOT = Path(__file__).resolve().parents[1]
DAYS = SS.weekdays(date(2025, 1, 6), 16)


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    root = tmp_path_factory.mktemp("alpaca")
    SS.write_cache(root, "SPY", DAYS, band=0.01, trend={d: (35, 0.00012 if k % 2 else -0.00012) for k, d in enumerate(DAYS)})
    return root


SPEC = {"spec_id": "e2e", "period": "DEV", "symbols": ["SPY"], "description": "end-to-end test spec",
        "defaults": {"side": "both", "contract": "d40-55t45", "allout": "15:25", "time": "a", "stop": "level", "tp": "none",
                     "tp_buffer": "$0.03", "rr_min": None, "trail": "none", "filters": []},
        "blocks": [{"name": "A", "grid": {"entry": ["orb15", "orb30"], "stop": ["premium"], "tp": ["A"]}},
                   {"name": "B", "grid": {"entry": ["orb15"], "tp": ["B"], "rr_min": [None, 1.0]}},
                   {"name": "T", "grid": {"entry": ["orb15"], "stop": ["premium"], "trail": ["gb30", "L1"], "time": ["c"]}}],
        "robustness": {"top_k": 2, "random_paths": 2, "fake_seeds": 2, "min_trades": 1}}


def _run(tmp_path, cache, name="out", **kw):
    spec = tmp_path / "e2e.json"
    spec.write_text(json.dumps(SPEC))
    out = tmp_path / name
    lines = []
    res = runner.run_spec(spec, DAYS[0], DAYS[-1], data_root=cache, chains_dir=tmp_path / "nochains", out_dir=out, host_name="t",
                          log=lines.append, today=date(2026, 10, 31), **kw)
    return res, out, "\n".join(lines)


def test_runner_end_to_end(tmp_path, cache):
    res, out, printed = _run(tmp_path, cache)
    rows = list(csv.DictReader(open(out / "runs_t.csv")))
    head = (ROOT / "docs" / "research" / "sprint_runs.csv").read_text().splitlines()[0]
    assert open(out / "runs_t.csv").read().splitlines()[0] == head
    assert len(rows) == 6 and [r["run_id"] for r in rows] == [f"e2e-{i:03d}" for i in range(1, 7)]
    assert all(r["tool"] == "DeskEngine" and r["period_tag"].startswith("DEV") and "MODELED-SPREAD" in r["slippage"] for r in rows)
    assert sum(int(r["trades"]) for r in rows) > 0
    rep = (out / "report_2026-10-31.md").read_text()
    assert "BACKTEST" in rep and "First answer" in rep and "Robustness on the top" in rep and "MODELED-SPREAD" in rep
    assert "run " in printed and "exp$" in printed and str(out / "runs_t.csv") in printed
    with gzip.open(out / "trades_e2e_2026-10-31.csv.gz", "rt") as f:
        tr = list(csv.DictReader(f))
    assert len(tr) == sum(int(r["trades"]) for r in rows)
    t = tr[0]
    for k in ("entry_time", "exit_time", "entry_basis", "exit_basis", "stock_entry", "stock_exit", "exit_reason", "opt_mfe_pct",
              "opt_mae_pct", "stock_mfe", "stock_mae", "peak_time", "peak_level", "pct_peak_kept", "planned_rr_opt", "actual_rr"):
        assert k in t
    rb = res["robust"]
    top = [k for k, v in rb.items() if "random_exp" in v]
    assert top and all("nudges" in rb[k] for k in top)
    b_filtered = next(r["run_id"] for r in res["runs"] if r["exit"].rr_min)
    assert "skip_test" in rb[b_filtered] or res["summary"][b_filtered].get("trades", 0) == 0


def test_runner_is_deterministic_and_appends(tmp_path, cache):
    r1, out, _ = _run(tmp_path, cache, robust=False)
    r2, _, _ = _run(tmp_path, cache, robust=False)
    assert {k: v.get("expectancy") for k, v in r1["summary"].items()} == {k: v.get("expectancy") for k, v in r2["summary"].items()}
    rows = list(csv.DictReader(open(out / "runs_t.csv")))
    assert len(rows) == 12                                                    # appended, header written once
    assert r2["trials"] > r1["trials"]                                        # the earlier rows count as trials


# ---------------------------------------------------------------- puller
class FakeAlpaca:
    def __init__(self, stock):
        self.calls, self.stock = [], stock

    def __call__(self, url, headers):
        assert url.startswith("https://data.alpaca.markets/")
        self.calls.append(url)
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        a, b = pd.Timestamp(q["start"]), pd.Timestamp(q["end"])
        if "/v2/stocks/" in u.path:
            df = self.stock[(self.stock["ts"] >= a) & (self.stock["ts"] < b)]
            return {"bars": [{"t": t.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), "o": o, "h": h, "l": l, "c": c, "v": v}
                             for t, o, h, l, c, v in df[["ts", "o", "h", "l", "c", "v"]].itertuples(index=False)], "next_page_token": None}
        syms = q["symbols"].split(",")
        kind = "bars" if u.path.endswith("/bars") else "trades"
        t = a + pd.Timedelta(minutes=60)
        if kind == "bars":
            return {"bars": {s: [{"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}] for s in syms[:3]}}
        return {"trades": {s: [{"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "p": 1.0, "s": 1, "x": "C"}] for s in syms}}


def test_puller_clips_to_the_dates_resumes_and_reports_gaps(tmp_path, monkeypatch):
    import pull_alpaca as PA
    import sprint_pull as SPL
    days = SS.weekdays(date(2025, 1, 27), 6)                                  # Jan 27 .. Feb 3
    stock = pd.concat([SS.stock_day(d, 500, k) for k, d in enumerate(days)], ignore_index=True)
    fake = FakeAlpaca(stock)
    monkeypatch.setattr(PA, "_http", fake)
    monkeypatch.setattr(PA, "_calls", [])
    monkeypatch.setattr(PA, "ROOT", tmp_path / "alpaca")
    monkeypatch.setenv("ALPACA_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET", "s")
    a, b = date(2025, 1, 28), date(2025, 2, 3)
    r = SPL.pull_stock("SPY", a, b, today=date(2026, 10, 31), log=lambda *x: None)
    starts = [parse_qs(urlparse(c).query)["start"][0] for c in fake.calls]
    assert starts == ["2025-01-28T05:00:00Z", "2025-02-01T05:00:00Z"]            # ET midnight of the asked dates, not month starts
    assert r["pulled"] == 2 and not (PA.ROOT / "stocks" / "SPY" / "2025-01.csv.done").exists()   # partial month: never done
    got = pd.read_csv(PA.ROOT / "stocks" / "SPY" / "2025-01.csv.gz")
    assert got["ts"].str[:10].min() == "2025-01-28"
    o = SPL.pull_options("SPY", a, b, band=0.01, trades=True, trades_band=0.002, today=date(2026, 10, 31), log=lambda *x: None)
    assert o["days"] == 5 and o["bars"] > 0
    tr_urls = [c for c in fake.calls if "/options/trades" in c]
    n_tr = sum(len(parse_qs(urlparse(c).query)["symbols"][0].split(",")) for c in tr_urls)
    n_bars = sum(len(parse_qs(urlparse(c).query)["symbols"][0].split(",")) for c in fake.calls if "/options/bars" in c)
    assert 0 < n_tr < n_bars                                                  # trades only near the money
    n = len(fake.calls)
    o2 = SPL.pull_options("SPY", a, b, band=0.01, trades=True, today=date(2026, 10, 31), log=lambda *x: None)
    assert o2["skipped"] == 5 and len(fake.calls) == n                       # resumable
    g = SPL.gap_report("SPY", a, b, tmp_path / "rep")
    assert g["sessions"] == 5 and g["no_bars"] == [] and Path(g["file"]).exists() and g["contracts_per_session"]["min"] >= 1
    PA._write_gz(PA.ROOT / "options" / "SPY" / "2025-01-29" / "bars.csv.gz", PA._frame([]))     # a day Alpaca had nothing for
    g = SPL.gap_report("SPY", a, b)
    assert g["no_option_bars"] == ["2025-01-29"]
    from sprint.data import read_option_day
    assert read_option_day("SPY", date(2025, 1, 29), PA.ROOT) == {}
