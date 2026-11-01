"""Round 10 pull (tools/sprint_pull10.py) with fake HTTP: the "needs" registry with stub providers of every accepted shape and
signature, fetch rounds until no provider asks for more (phase-by-phase probing), L1/L2 days refused before any request,
network errors retried with backoff then resumed, an interrupted pull resumed to the same files, keys never printed, batches
of 100, the request estimate, and D-IV's provider end to end (monthly-only names probed past the weekly). Synthetic data only."""
import urllib.error
from datetime import date

import pandas as pd
import pytest

import sprint_synth9 as S9
import pull_alpaca as PA
import sprint_pull9 as P9
import sprint_pull10 as P10
from sprint import ivdata as IV, periods
from sprint.catalyst import occ
from sprint.data import parse_occ

D1, D2 = date(2025, 3, 3), date(2025, 3, 4)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = tmp_path / "data" / "alpaca"
    root.mkdir(parents=True)
    m = S9.Market()
    fa = S9.FakeAlpaca(m)
    monkeypatch.setattr(PA, "_http", fa)
    monkeypatch.setattr(PA, "MAX_PER_MIN", 10 ** 9)
    monkeypatch.setattr(PA, "ROOT", root)
    monkeypatch.setattr(P10, "PROVIDERS", {})
    monkeypatch.setenv("ALPACA_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET", "s")
    return root, m, fa


def _atm(m, sym="SPY", d=D1):
    """A strike near the synthetic market's close (so the contract prints)."""
    dd = m.daily(sym)
    return float(round(float(dd[dd["day"] == d]["c"].iloc[0])))


def _ctx(root, days=(D1, D2)):
    lines = []
    return P10.Ctx(root, lines.append, list(days)), lines


# ---------------------------------------------------------------- the registry
def test_registry_reads_stub_providers_of_every_shape_and_signature(env):
    root, m, fa = env
    s = [occ("SPY", date(2025, 4, 17), "C", k) for k in (550, 551, 552, 553, 554, 555)]
    P10.register("by_ctx", lambda ctx: [IV.need(D1, IV.W_LAST, [s[0]], "x")])
    P10.register("by_names", lambda root, days: {days[0].isoformat(): [s[1]]}, window=("09:30", "09:35"))

    def by_range(start, end):
        return [(start, s[2], "09:30", "09:35"), {"day": end, "symbol": s[3], "t0": "15:45", "t1": "16:00"}, (end, [s[4]], "1545-1600")]
    P10.register("by_range", by_range)

    def odd(anything):                                        # one unknown parameter: gets ctx
        assert isinstance(anything, P10.Ctx)
        return [(D2, s[5])]
    P10.register("odd", odd)
    P10.register("locked", lambda ctx: [(date(2024, 3, 4), s[0]), (date(2026, 7, 6), s[0])])
    P10.register("broken", lambda foo, bar: [])
    P10.register("bad_shape", lambda ctx: [42])
    ctx, _ = _ctx(root)
    ctx.span = (D1, D2)
    new, refused, errors = P10.collect(ctx)
    assert new[(D1, IV.W_LAST)][0] == [s[0]]
    assert new[(D1, ("09:30", "09:35"))][0] == sorted([s[1], s[2]])
    assert new[(D2, IV.W_LAST)][0] == sorted([s[3], s[4]])
    assert new[(D2, IV.W_DAY)][0] == [s[5]]                   # no window anywhere: the whole session
    assert refused == {"locked": 2} and set(errors) == {"broken", "bad_shape"} and "lambda" in errors["broken"]
    assert fa.calls == []                                     # collecting never requests anything


def test_needs_rounds_fetch_phase_by_phase_until_nothing_is_new(env):
    root, m, fa = env
    k = _atm(m)
    ghost = occ("SPY", date(2025, 4, 17), "C", k + 0.5)       # not on SPY's $1 grid: never prints
    real = occ("SPY", date(2025, 4, 17), "C", k)

    def phased(ctx):
        if ghost not in ctx.bars.asked(D1, IV.W_LAST):
            return [(D1, ghost, IV.W_LAST)]
        if ghost not in ctx.bars.printed(D1, IV.W_LAST):
            return [(D1, real, IV.W_LAST)]
        return []
    P10.register("phased", phased)
    ctx, lines = _ctx(root)
    out = P10.pull_needs(ctx)
    assert out["rounds"] == 2 and out["contracts"] == 2 and out["day_windows"] == 2
    mk = IV.read_marker(IV.opt_marker(root, D1, IV.W_LAST))
    assert mk["asked"] == sorted([ghost, real]) and mk["printed"] == [real]
    df = IV.read_opt(root, D1, IV.W_LAST)
    mins = IV.minutes(df)
    assert set(df["symbol"]) == {real} and mins.min() >= 375 and mins.max() <= 390
    n = len(fa.calls)
    ctx2, _ = _ctx(root)
    assert P10.pull_needs(ctx2)["contracts"] == 0 and len(fa.calls) == n            # resumed: nothing asked twice


def test_locked_days_are_refused_before_any_request(env):
    root, m, fa = env
    P10.register("locked", lambda ctx: [(date(2024, 5, 1), occ("SPY", date(2024, 6, 21), "C", 500)),
                                        (date(2026, 8, 3), occ("SPY", date(2026, 9, 18), "C", 600))])
    ctx, lines = _ctx(root)
    out = P10.pull_needs(ctx)
    assert out["refused"] == {"locked": 2} and out["contracts"] == 0 and fa.calls == []
    assert any("REFUSED" in ln for ln in lines)
    for d in (date(2024, 2, 1), date(2024, 7, 31), date(2026, 7, 1), date(2026, 10, 30)):
        with pytest.raises(periods.LockedPeriod):
            P10.opt_bars([occ("SPY", d, "C", 500)], d, IV.W_LAST)
        with pytest.raises(periods.LockedPeriod):
            P10.stock_bars(["SPY"], d, IV.W_LAST)
    assert fa.calls == []
    assert P10.main(["--from", "2024-07-01", "--to", "2024-08-30"]) == 2


# ---------------------------------------------------------------- network errors and resuming
class Flaky:
    def __init__(self, inner, fail, exc=None):
        self.inner, self.fail, self.exc, self.n = inner, fail, exc, 0

    def __call__(self, url, headers):
        self.n += 1
        if self.n <= self.fail:
            raise self.exc or urllib.error.URLError("connection reset")
        return self.inner(url, headers)


def test_network_errors_are_retried_with_backoff_and_http_errors_are_not(env, monkeypatch):
    root, m, fa = env
    c = occ("SPY", date(2025, 4, 17), "C", _atm(m))
    slept = []
    monkeypatch.setattr(P10.time, "sleep", slept.append)
    monkeypatch.setattr(PA, "_http", Flaky(fa, 3))
    df = P10.opt_bars([c], D1, IV.W_LAST)
    assert len(df) and slept == list(P10.NET_BACKOFF[:3])
    slept.clear()
    monkeypatch.setattr(PA, "_http", Flaky(fa, 2, TimeoutError("timed out")))
    assert len(P10.stock_bars(["SPY"], D1, IV.W_LAST)) and slept == list(P10.NET_BACKOFF[:2])
    slept.clear()
    monkeypatch.setattr(PA, "_http", Flaky(fa, 99))
    with pytest.raises(ConnectionError):
        P10.opt_bars([c], D1, IV.W_LAST)
    assert slept == list(P10.NET_BACKOFF)
    slept.clear()
    e503 = urllib.error.HTTPError("https://data.alpaca.markets/x", 503, "busy", {}, None)
    monkeypatch.setattr(PA, "_http", Flaky(fa, 1, e503))
    assert len(P10.opt_bars([c], D1, IV.W_LAST)) and slept == [P10.NET_BACKOFF[0]]
    e403 = urllib.error.HTTPError("https://data.alpaca.markets/x", 403, "forbidden", {}, None)
    monkeypatch.setattr(PA, "_http", Flaky(fa, 1, e403))
    with pytest.raises(RuntimeError, match="HTTP 403"):
        P10.opt_bars([c], D1, IV.W_LAST)


def test_an_interrupted_pull_resumes_to_the_same_files(env, tmp_path, monkeypatch):
    root, m, fa = env
    k0 = int(_atm(m))
    syms = [occ("SPY", date(2025, 4, 17), r, k) for k in range(k0 - 10, k0 + 12) for r in "CP"]

    def prov(ctx):
        return [(d, syms[i::3], IV.W_LAST) for i, d in enumerate((D1, D2, date(2025, 3, 5)))]
    P10.register("many", prov)
    ctx, _ = _ctx(root)
    P10.pull_needs(ctx)
    ref = {d: IV.read_opt(root, d, IV.W_LAST) for d in (D1, D2, date(2025, 3, 5))}
    root2 = tmp_path / "second"
    monkeypatch.setattr(P10.time, "sleep", lambda s: None)
    calls = []

    def dropping(url, headers):                               # one good request, then the line drops for good
        calls.append(url)
        if len(calls) > 1:
            raise urllib.error.URLError("network is unreachable")
        return fa(url, headers)
    monkeypatch.setattr(PA, "_http", dropping)
    ctx2, _ = _ctx(root2)
    with pytest.raises(ConnectionError):
        P10.pull_needs(ctx2)
    assert len(list((root2 / "r10" / "opt").rglob("*.json"))) == 1
    monkeypatch.setattr(PA, "_http", fa)
    ctx3, _ = _ctx(root2)
    P10.pull_needs(ctx3)
    for d, df in ref.items():
        got = IV.read_opt(root2, d, IV.W_LAST).sort_values(["symbol", "ts"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(got, df.sort_values(["symbol", "ts"]).reset_index(drop=True))


def test_keys_are_never_printed(env, monkeypatch, capsys):
    root, m, fa = env
    monkeypatch.setenv("ALPACA_KEY", "fake-key-id-123")
    monkeypatch.setenv("ALPACA_SECRET", "fake-secret-456")
    seen = []
    e401 = urllib.error.HTTPError("https://data.alpaca.markets/v1beta1/options/bars", 401, "unauthorized", {}, None)

    def deny(url, headers):
        seen.append(headers)
        raise e401
    monkeypatch.setattr(PA, "_http", deny)
    P10.register("one", lambda ctx: [(D1, occ("SPY", date(2025, 4, 17), "C", 550), IV.W_LAST)])
    rc = P10.main(["--only", "needs", "--providers", "one", "--from", "2025-03-03", "--to", "2025-03-04"])
    out = capsys.readouterr()
    assert rc == 3 and seen and seen[0]["APCA-API-KEY-ID"] == "fake-key-id-123"
    for txt in (out.out, out.err):
        assert "fake-key-id-123" not in txt and "fake-secret-456" not in txt
    assert "HTTP 401" in out.out


def test_requests_are_batched_by_100(env):
    root, m, fa = env
    syms = [occ("SPY", date(2025, 4, 17), "C", 300 + k) for k in range(250)]
    P10.opt_bars(syms, D1, IV.W_LAST)
    assert len(fa.calls) == 3
    assert all(len(u.split("symbols=")[1].split("&")[0].split("%2C")) <= 100 for u in fa.calls)


def test_estimate_scales_with_the_universe_and_needs_no_network(env, monkeypatch, capsys):
    root, m, fa = env
    e = P10.estimate(479, 1020, 22, per_min=180)
    assert e["requests"]["stock15"] == 479 * 11 and e["total_requests"] == sum(e["requests"].values())
    assert e["hours"] == pytest.approx(e["total_requests"] / 180 / 60, abs=0.05) and e["per_minute"] == 180
    big = P10.estimate(479, 2020, 22, per_min=180)
    assert big["requests"]["div"] > 1.9 * e["requests"]["div"]
    reb = P10.estimate(479, 1020, 22, div_scope="rebalance", per_min=180)
    assert reb["div_days"] == 22 * 6 and reb["requests"]["div"] < e["requests"]["div"] / 3
    monkeypatch.delenv("ALPACA_KEY")
    monkeypatch.delenv("ALPACA_SECRET")
    assert P10.main(["--estimate"]) == 0 and fa.calls == []
    assert "total" in capsys.readouterr().out


# ---------------------------------------------------------------- D-IV's provider end to end
def test_div_provider_probes_monthly_only_names_and_recovers_the_vol(env, capsys):
    root, m, fa = env
    real_rows = m.option_rows

    def monthly_only(sym, d, m0, m1):                         # AAA lists monthly expiries only
        meta = parse_occ(sym)
        if meta and meta["root"] == "AAA" and meta["expiry"] not in IV.monthly_expiries(meta["expiry"], meta["expiry"]):
            return []
        return real_rows(sym, d, m0, m1)
    m.option_rows = monthly_only
    P9.trading_http = lambda url, h: m.assets()
    P9.pull_assets(root, print)
    P9.pull_daily(["SPY", "AAA", "BBB"], root, print)
    P10.register("div", IV.needed_option_contracts)
    ctx, lines = _ctx(root)
    assert set(ctx.universe(D1)) == {"SPY", "AAA", "BBB"}
    st = P10.pull_stock15(ctx, days=[D1, D2])
    assert st["asked"] == 6 and IV.read_frame(IV.stock_path(root, D1)) is not None
    out = P10.pull_needs(ctx)
    assert out["rounds"] >= 2 and all((IV.opt_dir(root, d) / "div.done").exists() for d in (D1, D2))
    res = IV.day_result(root, D1, ["SPY", "AAA", "BBB"])
    assert res["AAA"]["exp30"] == "2025-04-17" and res["BBB"]["exp30"] == "2025-03-28"
    assert res["SPY"]["exp30"] == "2025-03-24"                # ETFs: the first session >= 21 days out
    assert res["AAA"]["iv30"] == pytest.approx(0.40, abs=0.003) and res["SPY"]["iv30"] == pytest.approx(0.18, abs=0.003)
    for n in ("SPY", "AAA", "BBB"):
        e90 = date.fromisoformat(res[n]["exp90"])
        assert 60 <= (e90 - D1).days <= 120 and res[n]["iv90"] == pytest.approx(0.40 if n != "SPY" else 0.18, abs=0.003)
    n = len(fa.calls)
    ctx2, _ = _ctx(root)
    assert P10.pull_needs(ctx2)["contracts"] == 0 and len(fa.calls) == n
    P10.status(root, print, [D1, D2])
    o = capsys.readouterr().out
    assert "D-IV: 2 of 2" in o and "stock15: 2 of 2" in o


# ---------------------------------------------------------------- Addendum 16.1's calibration provider
def test_the_module_registers_the_three_round10_swing_providers():
    src = open(P10.__file__).read()
    for line in ('register("div", IV.needed_option_contracts)', 'register("r10swing", SW.needed_option_contracts)',
                 'register("spread_cal", SE.needed_option_contracts)'):
        assert line in src


def test_spread_cal_asks_only_for_chain_contracts_the_0dte_cache_lacks(env, tmp_path):
    from sprint import spread_est as SE
    root, m, fa = env
    chains = tmp_path / "chains"
    chains.mkdir()
    k = int(_atm(m))
    syms = [occ("SPY", D1, "C", k + j) for j in range(3)]
    rows = [{"logged_at": f"{D1}T10:00:05-05:00", "underlying": "SPY", "spot": k, "symbol": s, "type": "C", "expiry": D1.isoformat(),
             "strike": float(k + j), "bid": 1.0, "ask": 1.1} for j, s in enumerate(syms)]
    pd.DataFrame(rows).to_csv(chains / f"{D1}.csv.gz", index=False, compression="gzip")
    (chains / "2026-07-06.csv.gz").write_bytes(b"inside L1: never opened")
    (chains / "2024-05-01.csv.gz").write_bytes(b"inside L2: never opened")
    have = pd.DataFrame([{"ts": pd.Timestamp(f"{D1} 10:00", tz="America/New_York"), "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0,
                          "symbol": syms[0]}])
    PA._write_gz(root / "options" / "SPY" / D1.isoformat() / "bars.csv.gz", have)
    P10.register("spread_cal", SE.needed_option_contracts)
    ctx = P10.Ctx(root, print, [D1, D2], chains_dir=chains)
    new, refused, errors = P10.collect(ctx)
    assert new == {(D1, IV.W_DAY): (syms[1:], 1, ["spread_cal"])} and not refused and not errors
    out = P10.pull_needs(ctx)
    assert out["contracts"] == 2 and out["rounds"] == 1
    got = IV.read_opt(root, D1, IV.W_DAY)
    assert len(got) and set(got["symbol"]) <= set(syms[1:]) and IV.minutes(got).min() >= 0
    ctx.span = (D2, D2)                                       # outside the pull's span: nothing asked
    assert SE.needed_option_contracts(ctx) == []


# ---------------------------------------------------------------- integration: the r10credit provider and the export stage
def _stock_day(root, sym, d, px=500.0):
    ts = pd.date_range(f"{d} 09:30", periods=390, freq="1min", tz="America/New_York")
    df = pd.DataFrame({"ts": ts, "o": px, "h": px + 0.2, "l": px - 0.2, "c": px, "v": 1000.0})
    PA._write_gz(root / "stocks" / sym / f"{d.strftime('%Y-%m')}.csv.gz", df)


def test_the_module_registers_the_credit_provider_and_runs_the_export_stage():
    assert "r10credit" in open(P10.__file__).read() and "export" in P10.STAGES
    assert P10.STAGES.index("export") > P10.STAGES.index("needs")


def test_credit_needs_asks_for_the_0dte_contracts_no_cache_holds(env):
    from sprint import r10credit as RC
    root, m, fa = env
    _stock_day(root, "SPY", D1)
    ctx = P10.Ctx(root, print, [D1], span=(D1, D1))
    out = P10.credit_needs(ctx)
    assert len(out) == 1 and out[0].day == D1 and out[0].window == IV.W_DAY and out[0].tag == "r10credit"
    need = RC.needed_option_contracts(D1, RC.data.read_stock("SPY", D1, D1, root), "SPY", tapes={})
    assert set(out[0].symbols) == set(need) and all(parse_occ(s)["expiry"] == D1 for s in out[0].symbols)
    have = pd.DataFrame([{"ts": pd.Timestamp(f"{D1} 10:00", tz="America/New_York"), "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0,
                          "v": 1.0, "symbol": need[0]}])
    PA._write_gz(root / "options" / "SPY" / D1.isoformat() / "bars.csv.gz", have)
    ctx2 = P10.Ctx(root, print, [D1], span=(D1, D1))
    assert need[0] not in P10.credit_needs(ctx2)[0].symbols          # already on file: not asked again
    assert P10.credit_needs(ctx2) is P10.credit_needs(ctx2)          # computed once per run


def test_export_writes_0dte_and_next_expiry_files_in_the_reader_layout(env):
    from sprint import r10credit as RC
    root, m, fa = env
    nxt = date(2025, 3, 7)
    s0, s1, other = occ("SPY", D1, "C", 500), occ("SPY", nxt, "P", 495), occ("AAPL", nxt, "C", 200)
    ts = [pd.Timestamp(f"{D1} 10:0{k}", tz="America/New_York") for k in range(3)]
    rows = [{"symbol": s, "ts": t, "o": 1.0 + k, "h": 1.1 + k, "l": 0.9 + k, "c": 1.0 + k, "v": 5.0, "n": 3, "vw": 1.0 + k}
            for s in (s0, s1, other) for k, t in enumerate(ts)]
    df = pd.DataFrame(rows)
    PA._write_gz(IV.opt_dir(root, D1) / f"{IV.wkey(IV.W_DAY)}.p0001.csv.gz", df)
    dup = df[df["symbol"] == s0].assign(c=99.0)                     # the same minutes again from a shorter window
    PA._write_gz(IV.opt_dir(root, D1) / f"{IV.wkey(IV.W_LAST)}.p0001.csv.gz", dup)
    res = P10.export_index_options(root, print)
    assert res["days"] == 1 and res["files"] == 2
    tapes = RC.read_tapes("SPY", D1, root)                           # options/ + options_r10/
    assert set(tapes) == {s0} and float(tapes[s0].c[30]) == 1.0      # whole-day window's row kept, not the duplicate
    f_next = root / "options_r10_next" / "SPY" / D1.isoformat() / "bars.csv.gz"
    got = pd.read_csv(f_next, compression="gzip")
    assert set(got["symbol"]) == {s1} and list(got.columns)[:2] == ["symbol", "ts"]
    assert not (root / "options_r10" / "AAPL").exists()
    before = (root / "options_r10" / "SPY" / D1.isoformat() / "bars.csv.gz").read_bytes()
    P10.export_index_options(root, print)
    assert (root / "options_r10" / "SPY" / D1.isoformat() / "bars.csv.gz").read_bytes() == before   # a re-run is identical


def test_grid_needs_asks_for_0dte_and_next_expiry_strikes_beyond_the_old_band(env):
    from sprint import r10grid as RG
    root, m, fa = env
    ts = pd.date_range(f"{D1} 09:30", periods=390, freq="1min", tz="America/New_York")
    px = pd.Series(range(390), dtype=float) * 0.06 + 500.0             # a +4.7% trend day: beyond the +/-3% band
    df = pd.DataFrame({"ts": ts, "o": px, "h": px + 0.1, "l": px - 0.1, "c": px, "v": 1000.0})
    PA._write_gz(root / "stocks" / "SPY" / f"{D1.strftime('%Y-%m')}.csv.gz", df)
    ctx = P10.Ctx(root, print, [D1], span=(D1, D1))
    out = P10.grid_needs(ctx)
    assert len(out) == 1 and out[0].tag == "r10grid" and out[0].window == IV.W_DAY
    exps = {parse_occ(s)["expiry"] for s in out[0].symbols}
    assert exps == {D1, D2}                                             # 0DTE + the next session (no next-expiry file)
    want0 = set(RG.needed_option_contracts("SPY", D1, SD_read(root, D1)))
    assert want0 and want0 <= set(out[0].symbols)
    assert "r10grid" in open(P10.__file__).read()


def SD_read(root, d):
    from sprint import data as SD
    return SD.read_stock("SPY", d, d, root)


def test_next_expiry_prefers_the_cached_next_expiry_file(env):
    root, m, fa = env
    fri = date(2025, 3, 7)
    PA._write_gz(root / "options_next" / "SPY" / D1.isoformat() / "bars.csv.gz",
                 pd.DataFrame([{"symbol": occ("SPY", fri, "C", 500), "ts": pd.Timestamp(f"{D1} 10:00", tz="America/New_York"),
                                "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0}]))
    assert P10.next_expiry(root, "SPY", D1, [D1, D2, fri]) == fri
    assert P10.next_expiry(root, "QQQ", D1, [D1, D2, fri]) == D2


def test_parallel_workers_write_the_same_files_as_one_worker(env, tmp_path, monkeypatch):
    root, m, fa = env
    k = int(_atm(m))
    days = [D1, D2]
    syms = {d: [occ("SPY", d, r, k + j) for j in range(-2, 3) for r in ("C", "P")] for d in days}

    def prov(ctx):
        return [IV.need(d, w, syms[d], "par", 1) for d in days for w in (IV.W_LAST, IV.W_DAY)]
    P10.register("par", prov)
    outs = {}
    for wk in (1, 4):
        r = tmp_path / f"w{wk}" / "data" / "alpaca"
        r.mkdir(parents=True)
        monkeypatch.setattr(PA, "ROOT", r)
        ctx = P10.Ctx(r, print, days, span=(D1, D2))
        res = P10.pull_needs(ctx, workers=wk)
        assert res["day_windows"] == 4 and res["contracts"] == 40
        files = sorted(p.relative_to(r) for p in (r / IV.R10 / "opt").rglob("*") if p.is_file())
        outs[wk] = {str(f): (r / f).read_bytes() for f in files}
    assert outs[1] == outs[4] and len(outs[1]) == 8
