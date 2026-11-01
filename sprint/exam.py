"""sprint/exam.py - the final locked-period exam (SPRINT_PLAN Amendment 11, extending Amendment 7; both written before any
L1/L2 pull or run). Research only: no network, no orders. The tool is tools/sprint_exam.py.

Two stages (Amendment 11: "artifacts committed with their sha256 before any L1/L2 pull"):
  E1 fit   (no locked data) FIN-L's logit, once, on ALL HIST 11:00-call trades (hist_v1-005's trade files if present,
           else factory_hist_v1-012's, recorded), and FIN-HS's two B2 models: L2 = FIN-H trades through 2024-01-31 (HIST,
           MODELED), L1 = FIN-H trades through 2026-06-30 (HIST + DEV), each with its tercile cuts from its own training
           predictions. Written to sprint/specs/final_v2_models.json (weights, preprocessing, cuts, source sha256s).
           Any training row dated inside L1/L2 is refused.
  E2 exam  (one shot per period) given --locked L2|L1 --frozen <sha256 of sprint/specs/final_v2_exam.json>: the guarded
           pull of the period, the engine runs, NB-VOL in shares, Amendment 11's bars and verdicts, the report.

Finalists (frozen; Amendment 7 + 11):
  FIN-H   the otm_v1-040 rules (time_1100 calls, |delta| 0.03-0.12 nearest 0.07, -95% stop, +9900% target, all out 15:25,
          SPY + QQQ + IWM, desk fills, 2% half-spread with the $0.005 floor, $0.65 per contract per side, 1 contract) with
          daytype rvol at the signal bar >= 1.06 (the value stamped as f_rvol). Engine run `fin_h` (filter rvol_ge106); the
          exam also checks it equals the reference's trades with f_rvol >= 1.06 (once-a-day entry, so it must).
  FIN-L   the otm_v1-040 rules, taking a trade when P(win) >= 0.5 from the Amendment 3 logit (sprint/learn.py: L2 penalty
          lambda 1.0, class-balanced, median fill then standardize on the training trades) fit ONCE on all HIST 11:00-call
          trades. Literal reading: "exactly as Amendment 7" = the holdout-2 L-call model, whose feature list was the 18
          features of that commit (features.FEATURES18), so the 7 round-8 features are not used by FIN-L.
  FIN-HS  FIN-H with round 8's B2 confidence sizing: the same logit on the 18 + 7 features (features.FEATURES), fit once per
          locked period; P(win) <= the lower training tercile -> skip, >= the upper -> 2 contracts, otherwise 1 (bottom
          checked first, as round8.b2_sizing).
  NB-VOL  Amendment 10 A1 secondary in shares (shares.a1_day "noise_sh_vol"): SPY + QQQ + IWM, long and short, the noise
          band at the half-hour checks, notional 10,000 x min(4, 0.02 / sd of the 14 prior daily returns), fill at the next
          bar's open +/- $0.01 a share, out at the close of the 15:59 bar (12:59 on early closes).
  Reference for FIN-H / FIN-L / FIN-HS: otm_v1-040 unfiltered on the same period (engine run `reference`). For NB-VOL: random
          direction on the same entries and exits, 200 draws, numpy default_rng(seed) for seeds 31..230 (shares.random_direction).

Pass, per finalist and period (L2 = 2024-02-01..07-31, L1 = 2026-07-01..10-30):
  FIN-H, FIN-L  trades >= 30 on L2 / 20 on L1, PF >= 1.25, PF 2x > 1.0, expectancy > the reference's.
  FIN-HS        FIN-H's trade count >= 30 / 20 (literal: "counted as FIN-H's signals" = the FIN-H trades it sizes, the
                skipped ones included), sized PF >= 1.25, sized PF 2x > 1.0, P/L per contract (sized total / contracts
                traded) > FIN-H's expectancy (1 contract a trade) on the same period.
  NB-VOL        trades >= 100 / 60, expectancy at 2x costs > 0, random-direction p < 0.10.
  Verdicts: holds = passes both periods, mixed = one, fails = neither. Reported whatever the verdict: by month, by symbol,
  without the best 5 trades, without the best day; a 5% option half-spread rerun is information only.

Data (Amendment 11 "Data"): one guarded pull per period into its own cache root data/alpaca_exam/<L1|L2>/ (never the
main cache, so nothing else can read it): SPY/QQQ/IWM/VIXY stock 1-minute bars of the period, the VIXY daily closes from
`vixy_daily_from` to the period's end in ONE split-adjusted request (so the 252-close percentile and the 20-close z sit
on one split basis; the main VIXY file has the locked months cut out), and the 0DTE option bars (band 3%, bars only, as
DEV's pull). The 1-minute warm-up comes from the main cache: L2 from HIST's last two months (2023-12-01.., split-adjusted,
so L2's stock bars are pulled split-adjusted too), L1 from DEV's (2026-05-01.., raw, so L1's are pulled raw); two calendar
months, HIST's own warm-up rule (2015-11-01 before 2016-01-04). No finalist reads VIXY 1-minute bars (no VIXY 1-minute
filter in the otm_v1-040 rules); they are pulled because Amendment 11 lists them.

One shot (Amendment 11): each period runs once. A re-run of the same period with the same frozen spec sha256 and the same
code commit is allowed (crash recovery) and logged as a re-run; a different spec or commit on a period already read is
refused. A run of the OTHER period at a different code commit is allowed but every finalist on it is labeled VOID (the
tool can't tell which finalist a code change touches; the changed files are listed for the reviewer). A different spec
sha256 between the two periods is refused. The log is data/sprint/exam_log.jsonl.

Labels: option results are BACKTEST on the locked period, REAL Alpaca option prices, MODELED-SPREAD 2%; share results are
BACKTEST on real Alpaca stock bars. Nothing here is a live or paper fill.
"""
import csv
import gzip
import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import VERSION, book, contracts, data, engine, entries, features, learn, periods, shares
from . import round8
from .factory import pf_of
from .sim import simulate

REPO = periods.REPO
SPEC_REL = "sprint/specs/final_v2_exam.json"
MODELS_REL = "sprint/specs/final_v2_models.json"
PENDING = "PENDING: the sha256 that tools/sprint_exam.py fit prints (set it with tools/sprint_exam.py freeze)"
SPEC_ID = "final_v2_exam"
SYMBOLS = ("SPY", "QQQ", "IWM")
STOCK_1M = ("SPY", "QQQ", "IWM", "VIXY")
FINALISTS = ("FIN-H", "FIN-L", "FIN-HS", "NB-VOL")
OPTION_FINALISTS = ("FIN-H", "FIN-L", "FIN-HS")
PERIOD_DEFS = {
    "L2": {"from": "2024-02-01", "to": "2024-07-31", "warm_from": "2023-12-01", "warm_source": "HIST",
           "stock_adjustment": "split", "vixy_daily_from": "2022-10-01"},
    "L1": {"from": "2026-07-01", "to": "2026-10-30", "warm_from": "2026-05-01", "warm_source": "DEV",
           "stock_adjustment": "raw", "vixy_daily_from": "2025-03-01"},
}
RVOL_CUT = 1.06
FIN_L_THRESHOLD = 0.5
FIN_L_FEATURES = list(features.FEATURES18)
FIN_HS_FEATURES = list(features.FEATURES)
MIN_TRADES = {"L2": 30, "L1": 20}
NB_MIN_TRADES = {"L2": 100, "L1": 60}
PF_MIN, PF2X_ABOVE, NB_EXP2X_ABOVE, NB_P_BELOW = 1.25, 1.0, 0.0, 0.10
RANDOM_SEEDS = tuple(range(31, 231))
BOOT_SEED, BOOT_DRAWS = 29, 2000
INFO_SPREAD_PCT = 0.05
OPTION_BAND = 0.03
HIST_V1_RUN = "hist_v1-005"
FACTORY_RUN = {"HIST": "factory_hist_v1-012", "DEV": "factory_dev_v1-012"}
# the otm_v1-040 rules (= run 7's otm_c_1100; tests/test_sprint_exam.py checks both)
ENGINE_DEFAULTS = {"entry": "time_1100", "side": "C", "contract": "d03-12t07", "allout": "15:25", "mechanics": "desk", "filters": [],
                   "risk": "none", "tp_buffer": "$0.03", "rr_min": None, "stop": "fixed", "fixed_stop": 0.95, "fixed_target": 99.0,
                   "tp": "none", "trail": "none", "time": "b"}
OPT_LABEL = "BACKTEST on the locked period (out-of-sample, run once), REAL Alpaca option prices, MODELED-SPREAD 2% half-spread"
SH_LABEL = "BACKTEST on the locked period (out-of-sample, run once), real Alpaca stock 1-minute bars (shares, no option model)"


class ExamRefused(RuntimeError):
    pass


# ---------------------------------------------------------------- the frozen exam spec
def _period_block(name):
    p = dict(PERIOD_DEFS[name])
    p.update(min_trades_fin=MIN_TRADES[name], min_trades_nbvol=NB_MIN_TRADES[name])
    return p


def canonical_spec(models_sha=PENDING):
    """The exam spec, built from this module's constants (the shipped sprint/specs/final_v2_exam.json must equal it, except
    the models sha256, which `freeze` sets after stage E1)."""
    return {
        "spec_id": SPEC_ID,
        "written": "2026-11-01, after run 8 and before any L1/L2 pull or run",
        "source": "docs/research/SPRINT_PLAN.md Amendment 7 + Amendment 11 (commit 68a3b1e); Amendment 10 A1 (noise_sh) and B2",
        "description": ("The final locked-period exam: FIN-H, FIN-L, FIN-HS (FIN-H with B2 confidence sizing) and NB-VOL (the "
                        "vol-sized noise band in shares), each run once on L2 and once on L1 through the --locked/--frozen "
                        "guard. Research only."),
        "models": {"path": MODELS_REL, "sha256": models_sha},
        "symbols": list(SYMBOLS),
        "periods": {k: _period_block(k) for k in ("L2", "L1")},
        "pull": {"stock_1m": list(STOCK_1M), "vixy_daily": "VIXY (split-adjusted, one request from vixy_daily_from to the period end)",
                 "options_0dte": list(SYMBOLS), "band": OPTION_BAND, "option_trades": False, "feed": "sip",
                 "cache": "data/alpaca_exam/<period>/ (the period only; the 1-minute warm-up is read from data/alpaca/)"},
        "engine": {"spec_id": SPEC_ID, "symbols": list(SYMBOLS), "defaults": dict(ENGINE_DEFAULTS),
                   "blocks": [{"name": "reference", "why": "otm_v1-040 unfiltered (the reference for FIN-H, FIN-L, FIN-HS)",
                               "grid": {"filters": [[]]}},
                              {"name": "fin_h", "why": "otm_v1-040 + relative volume at the signal bar >= 1.06 (FIN-H)",
                               "grid": {"filters": [["rvol_ge106"]]}}]},
        "costs": {"options": "desk fills; MODELED-SPREAD half-spread 2% of premium (SPY/QQQ/IWM), floor $0.005; logged chains never used; "
                             "$0.65 per contract per side; PF 2x = the 2x-slippage P/L stamped on every trade",
                  "information_rerun_half_spread_pct": INFO_SPREAD_PCT,
                  "shares": "fill at the open of the bar after the decision +/- $0.01 a share; 2x costs = $0.02 a side; no commission"},
        "finalists": {
            "FIN-H": {"engine_run": "fin_h", "rvol_cut": RVOL_CUT, "contracts": 1},
            "FIN-L": {"engine_run": "reference", "model": "fin_l", "take_if_p_win_at_least": FIN_L_THRESHOLD,
                      "features": FIN_L_FEATURES, "fit_on": "all HIST 11:00-call trades: hist_v1-005 if present, else factory_hist_v1-012"},
            "FIN-HS": {"engine_run": "fin_h", "model": "fin_hs.<period>", "features": FIN_HS_FEATURES,
                       "sizing": "P(win) <= lower tercile cut -> 0 contracts; >= upper cut -> 2; otherwise 1",
                       "fit_on": {"L2": "FIN-H trades (factory_hist_v1-012, f_rvol >= 1.06) through 2024-01-31",
                                  "L1": "FIN-H trades (factory_hist_v1-012 + factory_dev_v1-012, f_rvol >= 1.06) through 2026-06-30"}},
            "NB-VOL": {"rule": "noise_sh_vol (Amendment 10 A1 secondary)", "symbols": list(SYMBOLS), "sides": "long and short",
                       "notional": "10000 x min(4, 0.02 / sd of the 14 prior daily close-to-close returns)"}},
        "references": {"FIN-H": "reference", "FIN-L": "reference", "FIN-HS": "reference (shown); the bar compares P/L per contract with FIN-H",
                       "NB-VOL": "random direction on the same entries and exits"},
        "bars": {
            "FIN-H": {"min_trades": dict(MIN_TRADES), "pf_at_least": PF_MIN, "pf_2x_above": PF2X_ABOVE, "expectancy_above": "reference"},
            "FIN-L": {"min_trades": dict(MIN_TRADES), "pf_at_least": PF_MIN, "pf_2x_above": PF2X_ABOVE, "expectancy_above": "reference"},
            "FIN-HS": {"min_trades": dict(MIN_TRADES), "trades_counted_as": "FIN-H trades", "sized_pf_at_least": PF_MIN,
                       "sized_pf_2x_above": PF2X_ABOVE, "pnl_per_contract_above": "FIN-H expectancy"},
            "NB-VOL": {"min_trades": dict(NB_MIN_TRADES), "expectancy_2x_above": NB_EXP2X_ABOVE, "random_direction_p_below": NB_P_BELOW}},
        "seeds": {"nbvol_random_direction": {"seeds": [RANDOM_SEEDS[0], RANDOM_SEEDS[-1]], "draws": len(RANDOM_SEEDS),
                                             "rng": "numpy default_rng(seed)"},
                  "bootstrap_information": {"seed": BOOT_SEED, "draws": BOOT_DRAWS}},
        "verdicts": {"holds": "passes on both L2 and L1 (then a new versioned PAPER ledger and 40 forward trades; never real money "
                              "without Nick's explicit yes)", "mixed": "passes on one period (reported, not promoted)",
                     "fails": "passes on neither (dropped)"},
        "one_shot": ("Each period runs once. A crash may be re-run with the same frozen spec and the same code commit. Any code "
                     "change after the first L1/L2 read makes the exam void for that finalist, and it is reported as such."),
    }


def spec_text(spec):
    return json.dumps(spec, indent=1, ensure_ascii=False) + "\n"


def check_spec(spec):
    """None when `spec` is the canonical exam spec (models sha256 aside) and its periods are periods.LOCKED's; else why not."""
    if not isinstance(spec, dict):
        return "the exam spec is not a JSON object"
    a = json.loads(json.dumps(spec))
    b = canonical_spec()
    ms = (a.get("models") or {}).get("sha256")
    a.setdefault("models", {})["sha256"] = b["models"]["sha256"]
    if a != b:
        diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        return f"the exam spec differs from Amendment 11's (sprint/exam.py canonical_spec) in: {', '.join(diff)}"
    for k, p in spec["periods"].items():
        if (date.fromisoformat(p["from"]), date.fromisoformat(p["to"])) != periods.LOCKED[k]:
            return f"the spec's {k} dates {p['from']}..{p['to']} are not periods.LOCKED[{k}]"
    if not isinstance(ms, str):
        return "the spec's models sha256 is missing"
    return None


def models_sha_ready(sha):
    return isinstance(sha, str) and len(sha) == 64 and all(c in "0123456789abcdef" for c in sha.lower())


def engine_runs(spec):
    from . import runner
    runs = engine.expand(spec["engine"])
    runner.validate(runs)
    return {r["block"]: r for r in runs}


# ---------------------------------------------------------------- stage E1: the models
def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def check_training_rows(rows):
    """None, or the reason the rows are refused: a row dated inside L1/L2, or a HIST/DEV row outside its period."""
    for r in rows:
        d = date.fromisoformat(str(r["day"])[:10])
        hit = periods.overlaps(d, d)
        if hit:
            return f"REFUSED: a training trade on {d} is inside locked period {', '.join(hit)} ({r.get('run_id', '')})"
        src = r.get("_src")
        if src in ("HIST", "DEV"):
            lo, hi = periods.HIST if src == "HIST" else periods.DEV
            if not lo <= d <= hi:
                return f"REFUSED: a {src} training trade on {d} is outside {src} {lo}..{hi} ({r.get('run_id', '')})"
    return None


def fit_logit_model(rows, names, cuts=False):
    """The Amendment 3 logit (learn._prep_fit / _prep_apply / fit_logit) fit once on `rows` (win = pnl > 0). Returns the JSON
    model; with cuts=True also the terciles of its own training predictions (numpy.quantile 1/3, 2/3, linear)."""
    if not rows:
        raise ValueError("no training trades")
    why = check_training_rows(rows)
    if why:
        raise ExamRefused(why)
    X = features.matrix(rows, names)
    prep = learn._prep_fit(X)
    Z = learn._prep_apply(prep, X)
    if Z.shape[1] == 0:
        raise ValueError("no usable feature (every column empty or constant)")
    y = (np.array([float(r["pnl"]) for r in rows]) > 0).astype(float)
    w, b = learn.fit_logit(Z, y)
    ptr = _sigmoid(Z @ w + b)
    days = sorted(str(r["day"])[:10] for r in rows)
    m = {"features": list(names), "prep": {"med": [float(x) for x in prep["med"]], "mu": [float(x) for x in prep["mu"]],
                                          "sd": [float(x) for x in prep["sd"]], "keep": [bool(x) for x in prep["keep"]]},
         "w": [float(x) for x in w], "b": float(b), "rows": len(rows), "wins": int(y.sum()), "first_day": days[0], "last_day": days[-1],
         "used_features": [n for n, k in zip(names, prep["keep"]) if k],
         "settings": "sprint/learn.py fit_logit: L2 lambda 1.0, class-balanced, Newton (50 steps max); median fill then standardize "
                     "on the training trades; all-empty or constant columns dropped"}
    if cuts:
        q = np.quantile(ptr, [1 / 3, 2 / 3])
        m["cuts"] = {"lower": float(q[0]), "upper": float(q[1])}
        sz = contracts_for(ptr, m["cuts"])
        m["train_sizes"] = {"skip": int((sz == 0).sum()), "one": int((sz == 1).sum()), "two": int((sz == 2).sum())}
    return m


def model_probs(m, rows):
    """P(win) for `rows` from a JSON model (the preprocessing and weights exactly as fitted)."""
    if not rows:
        return np.zeros(0)
    X = features.matrix(rows, m["features"])
    p = {"med": np.array(m["prep"]["med"], float), "mu": np.array(m["prep"]["mu"], float), "sd": np.array(m["prep"]["sd"], float),
         "keep": np.array(m["prep"]["keep"], bool)}
    Z = learn._prep_apply(p, X)
    return _sigmoid(Z @ np.array(m["w"], float) + float(m["b"]))


def contracts_for(p, cuts):
    """B2 sizing: P <= lower -> 0, P >= upper -> 2, otherwise 1 (bottom checked first, as round8.b2_sizing)."""
    p = np.asarray(p, float)
    return np.where(p <= cuts["lower"], 0, np.where(p >= cuts["upper"], 2, 1)).astype(int)


def rvol_ok(r):
    v = _num(r.get("f_rvol"))
    return v is not None and v >= RVOL_CUT


def _num(x):
    if x is None or x == "":
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def fit_models(fin_l_rows, fin_l_source, finh_hist, finh_dev, sources_hs, extra=None):
    """The models file content. fin_l_rows: all HIST 11:00-call trades; finh_hist / finh_dev: FIN-H trades (f_rvol >= 1.06,
    the seven round-8 features stamped) with _src set. FIN-HS L2 trains on HIST through L2's day before; L1 on HIST + DEV
    through L1's day before."""
    out = {"file": "final_v2_models", "spec": SPEC_ID, "amendment": "SPRINT_PLAN Amendment 11 (extending Amendment 7)",
           "labels": "HIST trades: option P/L MODELED (BS, calibrated IV); DEV trades: REAL Alpaca option prices"}
    fl = fit_logit_model(fin_l_rows, FIN_L_FEATURES)
    fl.update(name="FIN-L", threshold=FIN_L_THRESHOLD, source=fin_l_source)
    out["fin_l"] = fl
    out["fin_hs"] = {}
    for name, srcs in (("L2", ("HIST",)), ("L1", ("HIST", "DEV"))):
        through = (periods.LOCKED[name][0] - timedelta(days=1)).isoformat()
        rows = [r for r in (finh_hist if "HIST" in srcs else []) + (finh_dev if "DEV" in srcs else []) if str(r["day"])[:10] <= through]
        rows = sorted(rows, key=lambda r: (str(r["day"])[:10], _num(r.get("f_minute")) or 0))
        m = fit_logit_model(rows, FIN_HS_FEATURES, cuts=True)
        m.update(name=f"FIN-HS {name}", train_sources=list(srcs), train_through=through,
                 sources=[s for s in sources_hs if s["src"] in srcs])
        out["fin_hs"][name] = m
    if extra:
        out.update(extra)
    return out


def models_text(models):
    return json.dumps(models, indent=1, sort_keys=True) + "\n"


def check_models(models):
    """None when the models file has FIN-L and both FIN-HS models in the expected shape; else why not."""
    try:
        fl = models["fin_l"]
        assert fl["features"] == FIN_L_FEATURES and fl["threshold"] == FIN_L_THRESHOLD
        for k in ("L2", "L1"):
            m = models["fin_hs"][k]
            assert m["features"] == FIN_HS_FEATURES and m["cuts"]["lower"] <= m["cuts"]["upper"]
            assert m["train_through"] == (periods.LOCKED[k][0] - timedelta(days=1)).isoformat()
        for m in (fl, models["fin_hs"]["L2"], models["fin_hs"]["L1"]):
            n = len(m["features"])
            assert all(len(m["prep"][x]) == n for x in ("med", "mu", "sd", "keep")) and len(m["w"]) == sum(m["prep"]["keep"])
    except (KeyError, TypeError, AssertionError) as e:
        return f"the models file is not stage E1's ({type(e).__name__} {e})"
    return None


# ---------------------------------------------------------------- git: commit, dirty tree, frozen files
def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True)


def head_commit(repo):
    r = _git(["rev-parse", "HEAD"], repo)
    return r.stdout.decode().strip() if r.returncode == 0 else None


def dirty_reason(repo):
    """None when no tracked file differs from HEAD (staged or not) and no untracked file sits in the code folders sprint/,
    tools/ or tests/; otherwise the reason. Untracked files elsewhere (a .venv, data/, zips) don't count: they are not code
    that runs."""
    r = _git(["status", "--porcelain", "--untracked-files=no"], repo)
    if r.returncode != 0:
        return f"git status failed: {r.stderr.decode().strip()[:200]}"
    lines = [x for x in r.stdout.decode().splitlines() if x.strip()]
    u = _git(["status", "--porcelain", "--untracked-files=all", "--", "sprint", "tools", "tests"], repo)
    lines += [x for x in u.stdout.decode().splitlines() if x.startswith("??")]
    if lines:
        return "the working tree is dirty (commit or discard these first): " + "; ".join(lines[:8]) + (" ..." if len(lines) > 8 else "")
    return None


def changed_files(repo, a, b):
    r = _git(["diff", "--name-only", a, b], repo)
    return [x for x in r.stdout.decode().splitlines() if x.strip()] if r.returncode == 0 else ["(git diff failed)"]


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------- the exam log (one shot)
def read_log(path):
    out = []
    p = Path(path)
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def append_log(path, entry):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def log_policy(entries_, period, spec_sha, commit, repo=None):
    """(kind, void) for a new run of `period`, or raises ExamRefused. kind: "first" or "rerun". void: None or the reason
    every finalist on this run is VOID (code changed after the first locked read)."""
    starts = [e for e in entries_ if e.get("event") == "start"]
    same = [e for e in starts if e.get("period") == period]
    for e in same:
        if e.get("spec_sha") != spec_sha or e.get("commit") != commit:
            raise ExamRefused(f"REFUSED: {period} was already read on {e.get('at')} (spec sha256 {str(e.get('spec_sha'))[:12]}, commit "
                              f"{str(e.get('commit'))[:12]}). Amendment 11 allows only a crash re-run with the same frozen spec and the "
                              f"same code commit (this run: spec {spec_sha[:12]}, commit {str(commit)[:12]}).")
    for e in starts:
        if e.get("spec_sha") != spec_sha:
            raise ExamRefused(f"REFUSED: {e.get('period')} ran with exam spec sha256 {str(e.get('spec_sha'))[:12]}, this run has "
                              f"{spec_sha[:12]}: both periods must run on the same frozen spec.")
    kind = "rerun" if same else "first"
    void = None
    if starts:
        first = starts[0]
        if first.get("commit") != commit:
            files = changed_files(repo, first.get("commit"), commit) if repo else []
            void = (f"the code changed after the first locked read ({first.get('period')} at commit {str(first.get('commit'))[:12]}; this run "
                    f"at {str(commit)[:12]}; changed files: {', '.join(files[:20]) or 'unknown'}). Amendment 11: the exam is void for a "
                    "finalist whose code changed; the tool can't tell which, so every finalist on this run is labeled VOID.")
    return kind, void


# ---------------------------------------------------------------- loading the period (warm-up + locked)
def warm_months(warm_from, a):
    """Month files (YYYY-MM) of the warm-up [warm_from, a - 1 day]."""
    end = a - timedelta(days=1)
    out, m = [], date(warm_from.year, warm_from.month, 1)
    while m <= end:
        out.append(m.strftime("%Y-%m"))
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return out


def missing_warmup(main_root, warm_from, a, symbols=SYMBOLS):
    """[(symbol, month)] warm-up month files absent from the main cache (checked before any locked read)."""
    root = Path(main_root)
    return [(s, m) for s in symbols for m in warm_months(warm_from, a) if not (root / "stocks" / s / f"{m}.csv.gz").exists()]


def load_period_series(sym, warm_from, a, b, main_root, exam_root):
    """data.Series of the warm-up (main cache, dates warm_from..a-1, which touch no locked period) and the locked period
    (exam cache, dates a..b only)."""
    wend = a - timedelta(days=1)
    if periods.overlaps(warm_from, wend):
        raise ExamRefused(f"REFUSED: the warm-up {warm_from}..{wend} touches a locked period")
    w = data.read_stock(sym, warm_from, wend, main_root)
    p = data.read_stock(sym, a, b, exam_root)
    parts = [x for x in (w, p) if x is not None and len(x)]
    if not parts:
        return data.Series(sym, None)
    df = pd.concat(parts, ignore_index=True).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    return data.Series(sym, df)


def read_exam_daily(path, a, b, period):
    """VIXY split-adjusted daily closes {date: close} from the exam cache, dates a..b; a date inside the OTHER locked period
    is refused (never pulled)."""
    f = Path(path)
    if not f.exists():
        return None
    df = pd.read_csv(f, compression="gzip")
    if not len(df):
        return pd.Series(dtype=float)
    d = pd.to_datetime(df["ts"], utc=True, format="ISO8601").dt.tz_convert("America/New_York").dt.date
    s = pd.Series(df["c"].to_numpy(float), index=d)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s = s[(s.index >= a) & (s.index <= b)]
    for k, (x, y) in periods.LOCKED.items():
        if k != period and any(x <= z <= y for z in s.index):
            raise ExamRefused(f"REFUSED: the exam's VIXY daily file holds dates inside {k}")
    return s


# ---------------------------------------------------------------- the engine pass (real tapes, 0DTE)
def engine_pass(runs, series, a, b, opt_root, spread, aux, progress=None, limit_days=None):
    """engine.run_pass's loop for real 0DTE tapes (no modeled, next-expiry, random, made-up-level or risk-rule runs), on
    Series already built (warm-up + locked period) and the exam's VIXY daily closes, so it never reads the main cache's
    VIXY file (which has the locked months cut out). tests/test_sprint_exam.py checks it equals engine.run_pass trade for
    trade. Returns ({run_id: {"trades" (engine.LEAN), "rows" (full trade rows), "skips", "signals"}}, {symbol: [sessions]})."""
    for r in runs:
        if contracts.is_next(r["exit"].contract) or r.get("random") or r.get("fake_seed") is not None or r["exit"].risk != "none":
            raise ValueError(f"{r['run_id']}: the exam pass runs 0DTE real-tape runs only")
    res = {r["run_id"]: {"trades": [], "rows": [], "skips": Counter(), "signals": 0} for r in runs}
    sessions = {}
    for sym in sorted({s for r in runs for s in r["symbols"]}):
        rs = [r for r in runs if sym in r["symbols"]]
        ser = series[sym]
        odays = data.option_days(sym, opt_root)
        days = [d for d in ser.days if a <= d <= b]
        if limit_days:
            days = days[:limit_days]
        sessions[sym] = [d.isoformat() for d in days]
        for n, day in enumerate(days):
            tapes = data.read_option_day(sym, day, opt_root) if day in odays else {}
            ctx = data.DayContext(ser, day, tapes, spread, aux=aux)
            sig_cache, pick_cache = {}, {}
            for r in rs:
                rid = r["run_id"]
                key = (r["entry"], r["side"])
                if key not in sig_cache:
                    sig_cache[key] = entries.signals(ctx, r["entry"], r["side"])
                sigs = sig_cache[key]
                if not sigs:
                    continue
                levels = ctx.levels(None)
                last_exit, count = -1, 0
                for sig in sorted(sigs, key=lambda s: s.idx):
                    res[rid]["signals"] += 1
                    if sig.idx < last_exit:
                        res[rid]["skips"]["busy: one position at a time"] += 1
                        continue
                    why = engine._filters_ok(r, ctx, sig, count)
                    if why:
                        res[rid]["skips"][why] += 1
                        continue
                    if not tapes:
                        res[rid]["skips"]["no 0DTE option data for the day"] += 1
                        continue
                    pk = (sig.key, r["exit"].contract)
                    if pk not in pick_cache:
                        pick_cache[pk] = contracts.pick(ctx, sig.side, sig.idx, r["exit"].contract)
                    tape, info = pick_cache[pk]
                    if tape is None:
                        res[rid]["skips"][info] += 1
                        continue
                    out = simulate(ctx, sig, r["exit"], levels, tape, info)
                    if out["status"] != "TRADE":
                        res[rid]["skips"][engine._skip_key(out["reason"])] += 1
                        continue
                    last_exit = out["exit_idx"]
                    count += 1
                    res[rid]["rows"].append(out)
                    res[rid]["trades"].append({k: out.get(k) for k in engine.LEAN})
            if progress and (n % 25 == 0 or n == len(days) - 1):
                progress(f"  {sym} {day} ({n + 1}/{len(days)} sessions)")
    return res, sessions


def nbvol_trades(series, a, b, aux, src):
    """NB-VOL = shares.a1_day's "noise_sh_vol" (the same call as shares.run_day) on every session of [a, b]."""
    out = []
    for sym in SYMBOLS:
        ser = series.get(sym)
        if ser is None:
            continue
        for d in [d for d in ser.days if a <= d <= b]:
            ctx = data.DayContext(ser, d, {}, None, aux=aux)
            out += shares.a1_day(ctx, src, "noise_sh_vol", notional=shares.a1_vol_notional(ser, d))
    return out


# ---------------------------------------------------------------- numbers
def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), n)


def _pfv(x):
    return -1.0 if x is None else (math.inf if isinstance(x, float) and math.isinf(x) else float(x))


def breakdown(rows, key="pnl"):
    """By month, by symbol, without the best 5 trades and without the best day (P/L in `key`)."""
    by_m, by_s, by_d = defaultdict(lambda: [0, 0.0]), defaultdict(list), defaultdict(float)
    p = []
    for r in rows:
        x = float(r[key])
        p.append(x)
        m = str(r["day"])[:7]
        by_m[m][0] += 1
        by_m[m][1] += x
        by_s[r["symbol"]].append(x)
        by_d[str(r["day"])[:10]] += x
    p = np.array(p, float)
    tot = float(p.sum()) if len(p) else 0.0
    best_day = max(by_d.items(), key=lambda kv: kv[1]) if by_d else None
    return {"by_month": {m: {"trades": v[0], "net": _r(v[1])} for m, v in sorted(by_m.items())},
            "by_symbol": {s: {"trades": len(v), "net": _r(sum(v)), "expectancy": _r(np.mean(v)), "pf": pf_of(v)} for s, v in sorted(by_s.items())},
            "without_best5": _r(tot - float(np.sort(p)[::-1][:5].sum())) if len(p) else 0.0,
            "without_best_day": _r(tot - best_day[1]) if best_day else 0.0, "best_day": [best_day[0], _r(best_day[1])] if best_day else None}


def ostats(rows):
    """Option rows (1 contract each, or sized rows with pnl / pnl_2x already multiplied): round8.ostats + breakdown."""
    s = round8.ostats(rows)
    if s["trades"]:
        s["expectancy_2x"] = _r(np.mean([float(r.get("pnl_2x", r["pnl"])) for r in rows]))
    s.update(breakdown(rows))
    return s


def boot_info(rows, a, b, key="pnl"):
    """Information: the 95% bootstrap interval of the daily mean P/L over every session of [a, b] (0 on days without a trade),
    resampled by session (shares.bootstrap_daily, seed 29, 2,000 draws)."""
    days = book.sessions_between(a, b)
    return shares.bootstrap_daily(shares.daily([dict(r, day=str(r["day"])[:10]) for r in rows], days, key), BOOT_SEED, BOOT_DRAWS)


def bar_fin(name, st, ref_st, period):
    n_min = MIN_TRADES[period]
    ch = [(f"at least {n_min} trades ({st['trades']})", st["trades"] >= n_min),
          (f"PF >= {PF_MIN} ({st.get('pf')})", _pfv(st.get("pf")) >= PF_MIN),
          (f"PF 2x > {PF2X_ABOVE} ({st.get('pf_2x')})", _pfv(st.get("pf_2x")) > PF2X_ABOVE),
          (f"expectancy above the reference's ({st.get('expectancy')} vs {ref_st.get('expectancy')})",
           st.get("expectancy") is not None and ref_st.get("expectancy") is not None and st["expectancy"] > ref_st["expectancy"])]
    return {"finalist": name, "checks": ch, "pass": all(ok for _, ok in ch)}


def sized_rows(finh_rows, sizes):
    return [dict(r, pnl=float(r["pnl"]) * int(c), pnl_2x=float(r.get("pnl_2x", r["pnl"])) * int(c), contracts=int(c))
            for r, c in zip(finh_rows, sizes) if int(c) > 0]


def bar_fin_hs(finh_st, sized, sizes, period):
    n_min = MIN_TRADES[period]
    n_c = int(np.sum(sizes)) if len(sizes) else 0
    tot = float(sum(float(r["pnl"]) for r in sized))
    per_c = tot / n_c if n_c else None
    pf, pf2 = (pf_of([float(r["pnl"]) for r in sized]), pf_of([float(r["pnl_2x"]) for r in sized])) if sized else (None, None)
    ch = [(f"at least {n_min} trades, counted as FIN-H's ({finh_st['trades']})", finh_st["trades"] >= n_min),
          (f"sized PF >= {PF_MIN} ({pf})", _pfv(pf) >= PF_MIN),
          (f"sized PF 2x > {PF2X_ABOVE} ({pf2})", _pfv(pf2) > PF2X_ABOVE),
          (f"P/L per contract above FIN-H's ({_r(per_c)} vs {finh_st.get('expectancy')})",
           per_c is not None and finh_st.get("expectancy") is not None and per_c > finh_st["expectancy"])]
    sz = np.asarray(sizes, int)
    return {"finalist": "FIN-HS", "checks": ch, "pass": all(ok for _, ok in ch), "contracts": n_c, "pnl_per_contract": _r(per_c),
            "sized_total": _r(tot), "sized_pf": pf, "sized_pf_2x": pf2, "fin_h_trades": finh_st["trades"],
            "skipped": int((sz == 0).sum()), "one": int((sz == 1).sum()), "doubled": int((sz == 2).sum())}


def bar_nbvol(trades, period, seeds=RANDOM_SEEDS):
    n_min = NB_MIN_TRADES[period]
    st = shares.stats(trades)
    p, tots = shares.random_direction(trades, seeds)
    e2 = st.get("expectancy_2x")
    ch = [(f"at least {n_min} trades ({st['trades']})", st["trades"] >= n_min),
          (f"expectancy at 2x costs > 0 ({e2})", e2 is not None and e2 > NB_EXP2X_ABOVE),
          (f"beats random direction, p < {NB_P_BELOW} (p = {p}, {len(seeds)} draws, seeds {seeds[0]}-{seeds[-1]})",
           p is not None and p < NB_P_BELOW)]
    rd = {"p": p, "draws": len(seeds), "mean_total": _r(float(np.mean(tots))) if len(tots) else None,
          "p95_total": _r(float(np.percentile(tots, 95))) if len(tots) else None}
    return {"finalist": "NB-VOL", "checks": ch, "pass": all(ok for _, ok in ch), "random_direction": rd}


def verdict(passes):
    """passes: {period: True | False | None (not run yet)} -> holds / mixed / fails / pending."""
    vals = [passes.get("L2"), passes.get("L1")]
    if any(v is None for v in vals):
        return "pending (the other period has not run)"
    n = sum(1 for v in vals if v)
    return "holds" if n == 2 else "mixed" if n == 1 else "fails"


def finh_consistency(ref_rows, finh_rows):
    """FIN-H's engine run must equal the reference's trades with f_rvol >= 1.06 (time_1100 is once a day per symbol)."""
    key = lambda r: (r["symbol"], str(r["day"])[:10], r.get("signal_idx"), r.get("contract"), _r(float(r["pnl"]), 4))
    a = sorted(key(r) for r in ref_rows if rvol_ok(r))
    b = sorted(key(r) for r in finh_rows)
    return {"match": a == b, "reference_with_rvol": len(a), "fin_h_run": len(b),
            "only_in_reference": len(set(a) - set(b)), "only_in_fin_h": len(set(b) - set(a))}


def evaluate(period, ref, finh, models, nb, a, b, ref5=None, finh5=None, void=None):
    """Every finalist's numbers and bar on one period, from the trades (pure: no data access). ref / finh: the engine runs'
    trade rows (reference, fin_h) at the base cost; ref5 / finh5 at the 5% half-spread (information)."""
    a, b = str(a), str(b)
    out = {"period": period, "from": a, "to": b, "void": void, "finalists": {}, "info_5pct": None}
    ref_st = ostats(ref)
    out["reference"] = dict(ref_st, label=OPT_LABEL, bootstrap_ci95_daily_mean=boot_info(ref, a, b))
    finh_st = ostats(finh)
    fh = bar_fin("FIN-H", finh_st, ref_st, period)
    out["finalists"]["FIN-H"] = dict(fh, stats=finh_st, bootstrap_ci95_daily_mean=boot_info(finh, a, b), label=OPT_LABEL)
    ml = models["fin_l"]
    pl = model_probs(ml, ref)
    take = pl >= ml["threshold"]
    finl = [r for r, t in zip(ref, take) if t]
    fl_st = ostats(finl)
    fl = bar_fin("FIN-L", fl_st, ref_st, period)
    out["finalists"]["FIN-L"] = dict(fl, stats=fl_st, bootstrap_ci95_daily_mean=boot_info(finl, a, b), label=OPT_LABEL,
                                     taken=int(take.sum()), skipped=int((~take).sum()),
                                     p_win={"min": _r(float(pl.min()), 4) if len(pl) else None, "median": _r(float(np.median(pl)), 4) if len(pl) else None,
                                            "max": _r(float(pl.max()), 4) if len(pl) else None})
    mh = models["fin_hs"][period]
    ph = model_probs(mh, finh)
    sz = contracts_for(ph, mh["cuts"])
    srows = sized_rows(finh, sz)
    hs = bar_fin_hs(finh_st, srows, sz, period)
    out["finalists"]["FIN-HS"] = dict(hs, stats=ostats(srows), bootstrap_ci95_daily_mean=boot_info(srows, a, b), label=OPT_LABEL,
                                      cuts=mh["cuts"], model=f"fin_hs.{period} (trained through {mh['train_through']})")
    nbb = bar_nbvol(nb, period)
    nst = shares.stats(nb)
    nst.update(breakdown(nb))
    nst["steadiness"] = shares.steadiness(nb)
    out["finalists"]["NB-VOL"] = dict(nbb, stats=nst, bootstrap_ci95_daily_mean=boot_info(nb, a, b), label=SH_LABEL)
    out["fin_h_check"] = finh_consistency(ref, finh)
    for k, v in out["finalists"].items():
        v["period_pass"] = None if void else v["pass"]
        v["void"] = void
    if ref5 is not None and finh5 is not None:
        r5 = ostats(ref5)
        h5 = ostats(finh5)
        l5 = [r for r, t in zip(ref5, model_probs(ml, ref5) >= ml["threshold"]) if t]
        s5z = contracts_for(model_probs(mh, finh5), mh["cuts"])
        s5 = sized_rows(finh5, s5z)
        out["info_5pct"] = {"label": "INFORMATION ONLY: the same trades at a 5% half-spread (MODELED-SPREAD 5%, sensitivity); not a pass bar",
                            "reference": r5, "FIN-H": dict(h5, bar=bar_fin("FIN-H", h5, r5, period)),
                            "FIN-L": dict(ostats(l5), bar=bar_fin("FIN-L", ostats(l5), r5, period)),
                            "FIN-HS": dict(ostats(s5), bar=bar_fin_hs(h5, s5, s5z, period))}
    return out


def combined(results):
    """results: {period: evaluate() output or None} -> {finalist: {"L2": pass/None, "L1": pass/None, "verdict"}}."""
    out = {}
    for f in FINALISTS:
        pp, void = {}, []
        for k in ("L2", "L1"):
            r = results.get(k)
            if r is None:
                pp[k] = None
                continue
            v = r["finalists"][f]
            if v.get("void"):
                void.append(k)
            pp[k] = bool(v["pass"])
        out[f] = {"L2": pp["L2"], "L1": pp["L1"], "verdict": ("VOID (" + ", ".join(void) + ")") if void else verdict(pp)}
    return out


# ---------------------------------------------------------------- trade files
EXAM_COLS = ["run", "spread"] + engine.TRADE_COLS + ["fin_l_p", "fin_l_take", "fin_hs_p", "fin_hs_contracts"]


def write_option_trades(path, blocks):
    """blocks: [(run name, spread label, rows, models or None, period)]."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EXAM_COLS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for name, lab, rows, models, period in blocks:
            pl = model_probs(models["fin_l"], rows) if models and name == "reference" else None
            ph = model_probs(models["fin_hs"][period], rows) if models and name == "fin_h" else None
            for k, t in enumerate(rows):
                row = dict(t, run=name, spread=lab)
                row["legs"] = ";".join(f"{x['qty']:g}@{x['basis']:.4f}@{x['idx']}:{x['reason']}" for x in t.get("legs") or [])
                for kk in ("peak_level", "target_level"):
                    if isinstance(row.get(kk), dict):
                        row[kk] = json.dumps(row[kk], sort_keys=True)
                if pl is not None:
                    row["fin_l_p"], row["fin_l_take"] = round(float(pl[k]), 6), int(pl[k] >= models["fin_l"]["threshold"])
                if ph is not None:
                    row["fin_hs_p"] = round(float(ph[k]), 6)
                    row["fin_hs_contracts"] = int(contracts_for([ph[k]], models["fin_hs"][period]["cuts"])[0])
                w.writerow(row)


# ---------------------------------------------------------------- the report
def _f(x, n=2):
    if x is None:
        return "-"
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return f"{x:,.{n}f}" if isinstance(x, (int, float)) else str(x)


def _row(cells):
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _head(cols):
    return _row(cols) + "\n" + _row(["---"] * len(cols))


STAT_COLS = ("trades", "win %", "avg win $", "avg loss $", "exp $", "PF", "PF 2x", "total $", "max DD $", "w/o best 5 $", "w/o best day $")


def _stat_cells(s):
    wr = s.get("win_rate")
    return [s.get("trades", 0), "-" if wr is None else f"{100 * wr:.1f}", _f(s.get("avg_win")), _f(s.get("avg_loss")), _f(s.get("expectancy")),
            _f(s.get("pf"), 3), _f(s.get("pf_2x"), 3), _f(s.get("total")), _f(s.get("max_dd")), _f(s.get("without_best5")),
            _f(s.get("without_best_day"))]


def _breakdown_md(L, s):
    bm = s.get("by_month") or {}
    if bm:
        L.append("By month: " + "; ".join(f"{m} n={v['trades']} net {_f(v['net'])}" for m, v in bm.items()) + ".")
    bs = s.get("by_symbol") or {}
    if bs:
        L.append("By symbol: " + "; ".join(f"{k} n={v['trades']} net {_f(v['net'])} exp {_f(v['expectancy'])} PF {_f(v['pf'], 3)}"
                                         for k, v in bs.items()) + ".")
    if s.get("best_day"):
        L.append(f"Best day {s['best_day'][0]} ({_f(s['best_day'][1])}); without it {_f(s.get('without_best_day'))}; without the best 5 "
                 f"trades {_f(s.get('without_best5'))}.")


def _checks_md(L, v):
    for n, ok in v["checks"]:
        L.append(f"- [{'x' if ok else ' '}] {n}")


def render(res, meta):
    p = res["period"]
    L = [f"# Locked-period exam {p} ({res['from']} to {res['to']}): FIN-H, FIN-L, FIN-HS, NB-VOL\n"]
    L.append(f"**Every number below is a BACKTEST on the locked period {p}: out-of-sample, run once, never used to choose any "
             "rule.** Options (FIN-H, FIN-L, FIN-HS, the reference): REAL Alpaca 0DTE option bars, desk fills +/- a MODELED-SPREAD "
             "half-spread of 2% of premium ($0.005 floor), $0.65 per contract per side, 1 contract (FIN-HS 0, 1 or 2). Shares "
             "(NB-VOL): real Alpaca stock 1-minute bars, fill at the next bar's open +/- $0.01 a share. Nothing here is a live or "
             "paper fill. Not financial advice: evidence for Nick to decide.\n")
    kind = meta.get("kind")
    L.append(f"Run: **{'first read' if kind == 'first' else 're-run (crash recovery, same frozen spec and code commit)'}**"
             + (f". **VOID**: {res['void']}" if res.get("void") else "") + ".\n")
    L.append(f"Code commit `{meta.get('commit')}`; exam spec `{meta.get('spec_path')}` sha256 `{meta.get('spec_sha')}`; models "
             f"`{meta.get('models_path')}` sha256 `{meta.get('models_sha')}`; sprint engine `{VERSION}`; host `{meta.get('host')}`; "
             f"started {meta.get('started')}, finished {meta.get('finished')}.\n")
    if meta.get("coverage"):
        L.append("Data: " + "; ".join(f"{k}: {v}" for k, v in meta["coverage"].items()) + ".\n")
    if meta.get("warm"):
        L.append(f"Warm-up (indicators only, no trades): {meta['warm']}.\n")
    L.append("## This period\n")
    L.append(_head(("finalist", "trades", "exp $", "PF", "PF 2x", "total $", "bar", "this period")))
    names = {"FIN-H": "FIN-H (rvol >= 1.06)", "FIN-L": "FIN-L (logit P(win) >= 0.5)", "FIN-HS": "FIN-HS (sized 0/1/2)",
             "NB-VOL": "NB-VOL (shares)"}
    for f in FINALISTS:
        v = res["finalists"][f]
        s = v["stats"]
        if f == "FIN-HS":
            cells = [names[f], f"{v['fin_h_trades']} (contracts {v['contracts']})", _f(v.get("pnl_per_contract")) + " /contract",
                     _f(v.get("sized_pf"), 3), _f(v.get("sized_pf_2x"), 3), _f(v.get("sized_total"))]
        else:
            cells = [names[f], s.get("trades", 0), _f(s.get("expectancy")), _f(s.get("pf"), 3), _f(s.get("pf_2x"), 3), _f(s.get("total"))]
        state = "VOID" if v.get("void") else ("PASS" if v["pass"] else "fail")
        L.append(_row(cells + ["; ".join(n.split(" (")[0] for n, ok in v["checks"] if not ok) or "all checks met", f"**{state}**"]))
    rs = res["reference"]
    L.append(_row(["reference (otm_v1-040 unfiltered)", rs.get("trades", 0), _f(rs.get("expectancy")), _f(rs.get("pf"), 3),
                   _f(rs.get("pf_2x"), 3), _f(rs.get("total")), "-", "-"]))
    L.append("")
    comb = meta.get("combined")
    L.append("## Verdicts (Amendment 7 / 11: holds = passes both periods, mixed = one, fails = neither)\n")
    if comb:
        L.append(_head(("finalist", "L2", "L1", "verdict")))
        lab = lambda x: "-" if x is None else ("pass" if x else "fail")
        for f in FINALISTS:
            c = comb[f]
            L.append(_row([f, lab(c["L2"]), lab(c["L1"]), f"**{c['verdict']}**"]))
        L.append("")
        if meta.get("other_file"):
            L.append(f"The other period's result: `{meta['other_file']}`.\n")
        L.append("A finalist that holds becomes a new versioned PAPER ledger and needs 40 forward paper trades (CLAUDE.md step 5); "
                 "never real money without Nick's explicit yes. Mixed: reported, not promoted. Fails: dropped.\n")
    for f in FINALISTS:
        v = res["finalists"][f]
        L.append(f"## {f}\n")
        L.append(f"Label: {v['label']}.\n")
        if v.get("void"):
            L.append(f"**VOID on this period**: {v['void']}\n")
        L.append("Bar:\n")
        _checks_md(L, v)
        L.append("")
        s = v["stats"]
        if f == "FIN-HS":
            L.append(f"Sizing on {v['fin_h_trades']} FIN-H trades ({v['model']}; cuts P(win) <= {_f(v['cuts']['lower'], 4)} skip, >= "
                     f"{_f(v['cuts']['upper'], 4)} 2 contracts): skipped {v['skipped']}, 1 contract {v['one']}, 2 contracts {v['doubled']}; "
                     f"{v['contracts']} contracts; sized total {_f(v['sized_total'])}, P/L per contract {_f(v['pnl_per_contract'])}.\n")
            L.append("Sized trades (P/L x contracts):\n")
        if f == "FIN-L":
            L.append(f"Taken {v['taken']} of the reference's trades, skipped {v['skipped']}; P(win) min / median / max "
                     f"{v['p_win']['min']} / {v['p_win']['median']} / {v['p_win']['max']}.\n")
        L.append(_head(STAT_COLS))
        L.append(_row(_stat_cells(s)))
        L.append("")
        if f == "NB-VOL":
            rd = v["random_direction"]
            L.append(f"Expectancy at 2x costs {_f(s.get('expectancy_2x'))}; expectancy in bps of notional {_f(s.get('exp_bps'), 3)}. Random "
                     f"direction ({rd['draws']} draws): p = {rd['p']}, mean total {_f(rd['mean_total'])}, 95th percentile {_f(rd['p95_total'])}. "
                     f"Months green {s['steadiness']['months_green']}/{s['steadiness']['months']}, weeks green "
                     f"{s['steadiness']['weeks_green']}/{s['steadiness']['weeks']}.\n")
        _breakdown_md(L, s)
        L.append(f"Information: 95% bootstrap interval of the daily mean P/L (every session, resampled by session): "
                 f"{v.get('bootstrap_ci95_daily_mean')}.\n")
    L.append("## Reference: otm_v1-040 unfiltered\n")
    L.append(_head(STAT_COLS))
    L.append(_row(_stat_cells(rs)))
    L.append("")
    _breakdown_md(L, rs)
    L.append("")
    fc = res["fin_h_check"]
    L.append(f"Check: FIN-H's engine run vs the reference's trades with f_rvol >= 1.06: {'identical' if fc['match'] else '**DIFFERENT**'} "
             f"({fc['fin_h_run']} vs {fc['reference_with_rvol']} trades).\n")
    i5 = res.get("info_5pct")
    if i5:
        L.append("## Information only: 5% half-spread rerun\n")
        L.append(f"{i5['label']}.\n")
        L.append(_head(("run",) + STAT_COLS + ("bar met at 5%",)))
        L.append(_row(["reference"] + _stat_cells(i5["reference"]) + ["-"]))
        for f in OPTION_FINALISTS:
            x = i5[f]
            L.append(_row([f + (" (sized)" if f == "FIN-HS" else "")] + _stat_cells(x) + ["yes" if x["bar"]["pass"] else "no"]))
        L.append("")
    if meta.get("skips"):
        L.append("## Skipped signals (engine)\n")
        for k, v in meta["skips"].items():
            L.append(f"- {k}: " + (", ".join(f"{a} {b}" for a, b in v) or "none"))
        L.append("")
    if meta.get("warnings"):
        L.append("## Warnings\n")
        for w in meta["warnings"]:
            L.append(f"- {w}")
        L.append("")
    L.append("## Limits\n")
    L.append("- Option fills use the pre-registered 2% half-spread on traded bar prices (Alpaca has no historical quotes); the 5% "
             "rerun is the stress. A stop inside a minute fills at the stop price, a gap at the next bar's open (bars only, no option "
             "trades were pulled, as on DEV).")
    L.append("- FIN-L and FIN-HS read the entry features stamped by the engine; a feature unknown at entry (for example the CPI "
             "calendar outside 2024-08..2025-12) is median-filled from the training trades, as Amendment 3's preprocessing does.")
    L.append("- FIN-HS's models were trained on MODELED HIST option P/L (L2) and on MODELED HIST + REAL DEV (L1).")
    L.append("- One period is a few months: a pass is evidence, not proof. Promotion still needs 40 forward paper trades.\n")
    L.append(f"Trade files: {meta.get('trade_files')}. Exam log: `{meta.get('log')}`.\n")
    return "\n".join(L)


def summary_lines(res, comb=None):
    out = []
    for f in FINALISTS:
        v = res["finalists"][f]
        s = v["stats"]
        state = "VOID" if v.get("void") else ("PASS" if v["pass"] else "fail")
        if f == "FIN-HS":
            num = f"FIN-H trades={v['fin_h_trades']} contracts={v['contracts']} per-contract={_f(v['pnl_per_contract'])} sized PF={_f(v['sized_pf'], 3)} PF2x={_f(v['sized_pf_2x'], 3)}"
        elif f == "NB-VOL":
            num = f"n={s.get('trades', 0)} exp={_f(s.get('expectancy'))} exp2x={_f(s.get('expectancy_2x'))} random-direction p={v['random_direction']['p']}"
        else:
            num = f"n={s.get('trades', 0)} exp={_f(s.get('expectancy'))} PF={_f(s.get('pf'), 3)} PF2x={_f(s.get('pf_2x'), 3)} ref exp={_f(res['reference'].get('expectancy'))}"
        tail = f"; verdict so far: {comb[f]['verdict']}" if comb else ""
        out.append(f"exam {res['period']} {f}: {state} ({num}){tail} [BACKTEST, locked period {res['period']}]")
    return out


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        x = float(o)
        return None if math.isnan(x) else ("inf" if math.isinf(x) else x)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return o


def stamp():
    return datetime.now().isoformat(timespec="seconds")
