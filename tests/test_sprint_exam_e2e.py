"""The final locked-period exam end to end on a SYNTHETIC "locked" fixture: L1 and L2 are monkeypatched to short made-up
windows outside the real ones (2024-10-07..16 and 2025-11-03..12; after 2024-02-01, where the puller allows option requests,
and touching no real L1/L2 date), the warm-up months sit in a temporary main cache, and a
fake data.alpaca.markets serves synthetic bars, so the real guarded pull path runs (stock and VIXY 1-minute bars, VIXY daily
closes, 0DTE option bars). No real L1/L2 data is read or made up. Also stage E1 (`fit`) and `freeze` on synthetic trade
files. Checks: the reports and trade files, the verdicts, the one-shot log (first read, re-run with identical results,
refusal after a code change), requests only inside the locked window, nothing locked in the main cache, keys never written."""
import gzip
import json
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sprint_synth as SS
from sprint import book, exam, features, periods
from test_sprint_exam import git, hist_days, dev_days, make_repo, synth_models, synth_rows

KEY, SECRET = "KEY-SENTINEL-7Q2", "SECRET-SENTINEL-9Z4"
FAKE = {"L2": {"from": "2024-10-07", "to": "2024-10-16", "warm_from": "2024-08-05", "warm_source": "HIST", "stock_adjustment": "split",
               "vixy_daily_from": "2024-08-01"},
        "L1": {"from": "2025-11-03", "to": "2025-11-12", "warm_from": "2025-09-02", "warm_source": "DEV", "stock_adjustment": "raw",
               "vixy_daily_from": "2024-10-17"}}
for _p in FAKE.values():                      # the made-up windows and every range they read avoid the real L1 / L2
    assert not periods.overlaps(min(_p["warm_from"], _p["vixy_daily_from"]), _p["to"])
PX = {"SPY": 400.0, "QQQ": 300.0, "IWM": 180.0, "VIXY": 20.0}


class FakeAlpaca:
    """data.alpaca.markets for the tests: serves the synthetic locked-period bars and records every request."""

    def __init__(self):
        self.stock, self.daily, self.opts, self.calls = {}, {}, {}, []

    @staticmethod
    def _bars(df):
        if not len(df):
            return []
        t = df["ts"].dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        return df.assign(t=t)[["t", "o", "h", "l", "c", "v", "n", "vw"]].to_dict("records")

    def __call__(self, url, headers):
        assert url.startswith("https://data.alpaca.markets/") and headers["APCA-API-KEY-ID"] == KEY
        u = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(u.query))
        start, end = pd.Timestamp(q["start"]), pd.Timestamp(q["end"])
        self.calls.append((u.path, q.get("timeframe"), start, end, q.get("adjustment")))
        if u.path.startswith("/v2/stocks/"):
            sym = u.path.split("/")[3]
            df = (self.daily if q["timeframe"] == "1Day" else self.stock).get(sym)
            sel = df[(df["ts"] >= start) & (df["ts"] < end)] if df is not None else df
            return {"bars": self._bars(sel) if sel is not None else [], "symbol": sym, "next_page_token": None}
        if u.path == "/v1beta1/options/bars":
            out = {}
            for s in q["symbols"].split(","):
                df = self.opts.get(s)
                if df is not None:
                    sel = df[(df["ts"] >= start) & (df["ts"] < end)]
                    if len(sel):
                        out[s] = self._bars(sel)
            return {"bars": out, "next_page_token": None}
        raise AssertionError(f"unexpected request {u.path}")


def _days(a, b):
    return [date.fromisoformat(d) for d in book.sessions_between(a, b)]


def _build_market(main, fake, seed=50):
    """Synthetic continuous bars per symbol over each period's warm-up + window: the warm-up months go to the main cache
    (SPY/QQQ/IWM, as HIST / DEV pulls left them), the window is served by the fake (stock, VIXY and 0DTE option bars)."""
    import pull_alpaca as PA
    rng = np.random.default_rng(seed)
    live = {s: [] for s in PX}
    daily = []
    for name, p in FAKE.items():
        a = date.fromisoformat(p["from"])
        days = _days(p["warm_from"], p["to"])
        for k, sym in enumerate(PX):
            px, warm = PX[sym], []
            for n, d in enumerate(days):
                df = SS.stock_day(d, px, seed + 1000 * k + n + (0 if name == "L2" else 500))
                df["v"] = df["v"] * float(np.exp(rng.normal(0, 0.3)))          # day-to-day volume swings: rvol both sides of 1.06
                px = float(df["c"].iloc[-1])
                (warm if d < a else live[sym]).append(df)
                if d >= a and sym != "VIXY":
                    ob = SS.option_bars(d, df, sym, iv=0.18, band=0.03, seed=n)
                    ob["ts"] = pd.to_datetime(ob["ts"])
                    for s, g in ob.groupby("symbol"):
                        fake.opts[s] = g.reset_index(drop=True)
            if sym != "VIXY":
                w = pd.concat(warm, ignore_index=True)
                for m, g in w.groupby(w["ts"].dt.strftime("%Y-%m")):
                    PA._write_gz(main / "stocks" / sym / f"{m}.csv.gz", g.reset_index(drop=True))
        dd = _days(p["vixy_daily_from"], p["to"])
        closes = 20.0 * np.exp(np.cumsum(rng.normal(0, 0.03, len(dd))))
        ts = [pd.Timestamp(f"{d} 00:00", tz="America/New_York") for d in dd]
        daily.append(pd.DataFrame({"ts": ts, "o": closes, "h": closes, "l": closes, "c": closes, "v": 1000.0, "n": 10, "vw": closes}))
    fake.stock = {s: pd.concat(v, ignore_index=True) for s, v in live.items()}
    fake.daily = {"VIXY": pd.concat(daily, ignore_index=True).sort_values("ts").reset_index(drop=True)}


@pytest.fixture
def locked_fixture(tmp_path, monkeypatch):
    import pull_alpaca as PA
    for k, p in FAKE.items():
        monkeypatch.setitem(periods.LOCKED, k, (date.fromisoformat(p["from"]), date.fromisoformat(p["to"])))
    monkeypatch.setattr(exam, "PERIOD_DEFS", FAKE)
    monkeypatch.setattr(PA, "_throttle", lambda: None)
    fake = FakeAlpaca()
    monkeypatch.setattr(PA, "_http", fake)
    monkeypatch.setenv("ALPACA_KEY", KEY)
    monkeypatch.setenv("ALPACA_SECRET", SECRET)
    main = tmp_path / "alpaca"
    _build_market(main, fake)
    skip = [(v["from"], v["to"]) for v in FAKE.values()]
    models = synth_models(skip=skip)
    repo, ssha, msha = make_repo(tmp_path / "repo", models)
    return {"fake": fake, "main": main, "repo": repo, "ssha": ssha, "msha": msha, "models": models, "tmp": tmp_path,
            "exam": tmp_path / "alpaca_exam", "out": tmp_path / "sprint"}


def _run(fx, period, logs):
    import sprint_exam as T
    return T.run_exam(None, period, fx["ssha"], main_root=fx["main"], exam_base=fx["exam"], out_dir=fx["out"], repo=fx["repo"],
                      today="2026-11-01", log=logs.append)


def _all_text(*roots):
    out = []
    for root in roots:
        for f in Path(root).rglob("*"):
            if f.is_file():
                b = f.read_bytes()
                out.append(gzip.decompress(b).decode(errors="replace") if f.suffix == ".gz" and b[:2] == b"\x1f\x8b" else
                           b.decode(errors="replace"))
    return "\n".join(out)


def test_exam_end_to_end_on_a_synthetic_locked_fixture(locked_fixture, capsys):
    fx = locked_fixture
    logs = []
    r2 = _run(fx, "L2", logs)
    out = r2["result"]
    assert r2["meta"]["kind"] == "first" and r2["meta"]["commit"] == exam.head_commit(fx["repo"]) and r2["meta"]["void"] is None
    assert set(out["finalists"]) == set(exam.FINALISTS)
    assert out["reference"]["trades"] > 0 and out["fin_h_check"]["match"]
    assert r2["meta"]["sessions"] == {"SPY": 8, "QQQ": 8, "IWM": 8}
    for f, v in out["finalists"].items():
        assert v["pass"] is (all(ok for _, ok in v["checks"])) and v["period_pass"] == v["pass"]
    assert not out["finalists"]["NB-VOL"]["pass"]                         # 8 sessions can't reach 100 trades
    assert out["finalists"]["FIN-HS"]["fin_h_trades"] == out["finalists"]["FIN-H"]["stats"]["trades"]
    assert out["info_5pct"] is not None and out["info_5pct"]["reference"]["trades"] == out["reference"]["trades"]
    assert r2["meta"]["combined"]["FIN-H"]["verdict"].startswith("pending")
    md = r2["md"].read_text()
    for s in ("BACKTEST on the locked period L2", "first read", "By month", "By symbol", "without the best 5", "Information only: 5% "
              "half-spread rerun", fx["ssha"], fx["msha"], "## Verdicts"):
        assert s in md, s
    tf = fx["out"] / "trades_exam_L2_2026-11-01.csv.gz"
    tr = pd.read_csv(tf)
    assert set(tr["run"]) == {"reference", "fin_h"} and set(tr["spread"]) == {"MODELED-SPREAD 2%", "MODELED-SPREAD 5% (information)"}
    base = tr[(tr["run"] == "reference") & (tr["spread"] == "MODELED-SPREAD 2%")]
    assert len(base) == out["reference"]["trades"] and base["fin_l_take"].isin([0, 1]).all()
    assert int(base["fin_l_take"].sum()) == out["finalists"]["FIN-L"]["taken"]
    assert (fx["out"] / "trades_exam_L2_shares_2026-11-01.csv.gz").exists()
    # the pull asked only for the locked window (1-minute and option bars) and the VIXY daily range; adjustments as specified
    a, b = periods.LOCKED["L2"]
    lo, hi = pd.Timestamp(f"{a} 00:00", tz="America/New_York"), pd.Timestamp(f"{b + timedelta(days=1)} 00:00", tz="America/New_York")
    calls = fx["fake"].calls
    for path, tf_, s, e, adj in calls:
        if tf_ == "1Day":
            assert s >= pd.Timestamp(FAKE["L2"]["vixy_daily_from"] + " 00:00", tz="America/New_York") and e <= hi and adj == "split"
        else:
            assert lo <= s and e <= hi, (path, s, e)
            if path.startswith("/v2/stocks/"):
                assert adj == "split"
    assert any(c[0] == "/v1beta1/options/bars" for c in calls) and any(c[0] == "/v2/stocks/VIXY/bars" and c[1] == "1Min" for c in calls)
    # nothing locked reached the main cache; the exam cache holds the window only
    for f in (fx["main"] / "stocks").rglob("*.csv.gz"):
        d = pd.read_csv(f)["ts"].str[:10]
        assert not d.between(str(a), str(b)).any(), f
    for f in (fx["exam"] / "L2" / "stocks").rglob("*.csv.gz"):
        d = pd.read_csv(f)["ts"].str[:10]
        assert d.between(str(a), str(b)).all(), f
    # L1 (same spec, same commit): verdicts across both periods
    n_calls = len(calls)
    r1 = _run(fx, "L1", logs)
    assert r1["meta"]["kind"] == "first" and r1["meta"]["other_file"].endswith("exam_L2_2026-11-01.json")
    for f in exam.FINALISTS:
        c = r1["meta"]["combined"][f]
        assert c["L2"] == out["finalists"][f]["pass"] and c["L1"] == r1["result"]["finalists"][f]["pass"]
        assert c["verdict"] == exam.verdict({"L2": c["L2"], "L1": c["L1"]}) and c["verdict"] in ("holds", "mixed", "fails")
    assert all(c[4] == "raw" for c in fx["fake"].calls[n_calls:] if c[0].startswith("/v2/stocks/") and c[1] == "1Min")
    # crash re-run of L1: same spec, same commit -> allowed, logged as a re-run, identical numbers (restart safety)
    r1b = _run(fx, "L1", logs)
    assert r1b["meta"]["kind"] == "rerun" and r1b["md"].name == "exam_L1_2026-11-01_rerun1.md"
    assert json.dumps(exam.clean(r1b["result"]), sort_keys=True) == json.dumps(exam.clean(r1["result"]), sort_keys=True)
    assert "re-run" in r1b["md"].read_text()
    log = exam.read_log(fx["out"] / "exam_log.jsonl")
    assert [(e["event"], e["period"], e["kind"]) for e in log] == [("start", "L2", "first"), ("done", "L2", "first"),
                                                                    ("start", "L1", "first"), ("done", "L1", "first"),
                                                                    ("start", "L1", "rerun"), ("done", "L1", "rerun")]
    assert {e["commit"] for e in log} == {exam.head_commit(fx["repo"])} and {e["spec_sha"] for e in log} == {fx["ssha"]}
    # a code change after the first read: a period already read is refused, nothing is requested or logged
    (fx["repo"] / "sprint" / "tweak.py").write_text("x = 1\n")
    git(fx["repo"], "add", "-A")
    git(fx["repo"], "commit", "-q", "-m", "tweak")
    n_calls = len(fx["fake"].calls)
    with pytest.raises(exam.ExamRefused, match="already read"):
        _run(fx, "L2", logs)
    assert len(fx["fake"].calls) == n_calls and len(exam.read_log(fx["out"] / "exam_log.jsonl")) == 6
    # keys: used in the request headers only, never printed or written
    text = _all_text(fx["out"], fx["exam"]) + "\n".join(logs) + "".join(capsys.readouterr())
    assert KEY not in text and SECRET not in text


# ---------------------------------------------------------------- stage E1 (fit) and freeze on synthetic trade files
def _write_trades(path, rows):
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "_src"} for r in rows])
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, compression="gzip")


@pytest.fixture
def e1_files(tmp_path):
    out = tmp_path / "sprint"
    hist = synth_rows(hist_days(8), exam.HIST_V1_RUN, "HIST", seed=1, new7=False)
    hist += synth_rows(hist_days(40), "hist_v1-003", "HIST", seed=2, new7=False)           # other runs in the file are ignored
    _write_trades(out / "trades_hist_v1_2026-10-31.csv.gz", hist)
    fh = synth_rows(hist_days(6), exam.FACTORY_RUN["HIST"], "HIST", seed=3)
    for r in fh:                                                                             # run 7's file predates B1: a few rows
        if r["symbol"] == "SPY" and "2023-11-01" <= r["day"] <= "2023-12-29":               # lack the round-8 features
            for k in features.NEW7:
                r.pop(k)
    fh += synth_rows(hist_days(50), "factory_hist_v1-011", "HIST", seed=4)
    _write_trades(out / "trades_factory_hist_v1_2026-11-01.csv.gz", fh)
    fd = synth_rows(dev_days(3), exam.FACTORY_RUN["DEV"], "DEV", seed=5)
    _write_trades(out / "trades_factory_dev_v1_2026-11-01.csv.gz", fd)
    data = tmp_path / "alpaca"
    SS.write_stock_only(data, "SPY", [date.fromisoformat(d) for d in book.sessions_between("2023-09-01", "2023-12-29")], px0=450.0)
    SS.write_daily(data, "VIXY", date(2022, 6, 1), date(2023, 12, 29))
    return {"out": out, "data": data, "tmp": tmp_path, "n_hist005": sum(1 for r in hist if r["run_id"] == exam.HIST_V1_RUN),
            "n_finh": sum(1 for r in fh + fd if r["run_id"] in exam.FACTORY_RUN.values() and exam.rvol_ok(r))}


def _fit(fx, models, extra=()):
    import sprint_exam as T
    return T.main(["fit", "--out", str(fx["out"]), "--data", str(fx["data"]), "--exam-data", str(fx["tmp"] / "alpaca_exam"),
                   "--models", str(models), *extra])


def test_fit_writes_the_models_file_and_prints_its_sha(e1_files, capsys):
    fx = e1_files
    mp = fx["tmp"] / "m" / "final_v2_models.json"
    assert _fit(fx, mp) == 0
    o = capsys.readouterr().out
    sha = periods.sha256_file(mp)
    assert f"models sha256: {sha}" in o and "FIN-L source: hist_v1-005" in o
    assert exam.sha256_bytes(exam.spec_text(exam.canonical_spec(sha)).encode()) in o
    m = json.loads(mp.read_text())
    assert exam.check_models(m) is None
    assert m["fin_l"]["rows"] == fx["n_hist005"] and m["fin_l"]["source"]["run_id"] == exam.HIST_V1_RUN
    assert m["fin_l"]["source"]["files"][0]["sha256"] == periods.sha256_file(fx["out"] / "trades_hist_v1_2026-10-31.csv.gz")
    assert m["fin_hs"]["L2"]["rows"] < m["fin_hs"]["L1"]["rows"] == fx["n_finh"] and m["fin_hs"]["L2"]["last_day"] <= "2024-01-31"
    assert m["restamp"]["rows_missing_round8_features"] > 0 and m["restamp"]["rows_filled"] == m["restamp"]["rows_missing_round8_features"]
    assert m["fin_l_vs_factory"]["hist_v1_005_trades"] == fx["n_hist005"]
    assert {s["src"] for s in m["fin_hs"]["L1"]["sources"]} == {"HIST", "DEV"} and {s["src"] for s in m["fin_hs"]["L2"]["sources"]} == {"HIST"}
    first = mp.read_bytes()
    assert _fit(fx, mp) == 0 and mp.read_bytes() == first                    # deterministic: the same fit, the same bytes


def test_fit_falls_back_to_factory_hist_and_refuses_locked_rows(e1_files, capsys):
    fx = e1_files
    (fx["out"] / "trades_hist_v1_2026-10-31.csv.gz").unlink()
    mp = fx["tmp"] / "m.json"
    assert _fit(fx, mp) == 0
    o = capsys.readouterr().out
    assert "FIN-L source: factory_hist_v1-012 (hist_v1-005's trade file not found" in o
    m = json.loads(mp.read_text())
    assert m["fin_l"]["source"]["run_id"] == exam.FACTORY_RUN["HIST"] and m["fin_l_vs_factory"] is None
    fd = pd.read_csv(fx["out"] / "trades_factory_dev_v1_2026-11-01.csv.gz")
    bad = pd.concat([fd, fd.iloc[[0]].assign(day="2026-07-15")], ignore_index=True)       # a row inside L1
    bad.to_csv(fx["out"] / "trades_factory_dev_v1_2026-11-01.csv.gz", index=False, compression="gzip")
    mp2 = fx["tmp"] / "m2.json"
    assert _fit(fx, mp2) == 2 and not mp2.exists()
    assert "inside locked period L1" in capsys.readouterr().err


def test_freeze_writes_the_models_sha_into_the_committed_spec(tmp_path, capsys):
    import sprint_exam as T
    repo, _, msha = make_repo(tmp_path / "repo", synth_models(), msha_override=exam.PENDING)
    sp, mp = repo / exam.SPEC_REL, repo / exam.MODELS_REL
    assert json.loads(sp.read_text())["models"]["sha256"] == exam.PENDING
    assert T.main(["freeze", "--spec", str(sp), "--models", str(mp)]) == 0
    assert sp.read_text() == exam.spec_text(exam.canonical_spec(msha))
    assert f"sha256: {periods.sha256_file(sp)}" in capsys.readouterr().out
    git(repo, "checkout", "-q", exam.SPEC_REL)
    mp.write_text(mp.read_text() + " ")                                      # models edited, not committed
    assert T.main(["freeze", "--spec", str(sp), "--models", str(mp)]) == 2
    assert "commit the models file first" in capsys.readouterr().err
