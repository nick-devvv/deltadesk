"""tools/sprint_overnight.sh (rounds 9 + 10 unattended) with a stub python: the stage order, retries with resume, the stop on
exit 2/3, skipping finished stages on a re-run, round 9's analysis in the background, the zips. No network, no real tools."""
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
STUB = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
name = "zipfile" if args[:2] == ["-m", "zipfile"] else Path(args[0]).name
calls = Path(os.environ["STUB_CALLS"])
with calls.open("a") as f:
    f.write(json.dumps([name] + args[1:]) + "\n")
plan = json.loads(os.environ.get("STUB_PLAN", "{}"))
n = sum(1 for l in calls.read_text().splitlines() if json.loads(l)[0] == name)
codes = plan.get(name, [])
rc = codes[n - 1] if n - 1 < len(codes) else 0
if rc == 0:
    out = Path("data/sprint")
    if name == "sprint_round9.py":
        (out / "round9_2026-11-02.md").write_text("# r9\n"); (out / "round9_2026-11-02.json").write_text("{}")
    for p in ("noise", "credit", "grid", "swing"):
        if name == f"sprint_r10_{p}.py":
            (out / f"r10{p}_2026-11-02.md").write_text("# r10\n"); (out / f"r10{p}_2026-11-02.json").write_text("{}")
    if name == "zipfile":
        Path(args[3]).write_text("zip")
sys.exit(rc)
'''


@pytest.fixture()
def box(tmp_path):
    root = tmp_path / "sprint"
    (root / "tools").mkdir(parents=True)
    (root / "data" / "sprint" / "logs").mkdir(parents=True)
    (root / "data" / "alpaca" / "universe").mkdir(parents=True)
    (root / "data" / "alpaca" / "universe" / "ustk.json").write_text("{}")
    shutil.copy(HERE / "tools" / "sprint_overnight.sh", root / "tools" / "sprint_overnight.sh")
    stub = tmp_path / "stubpy"
    stub.write_text(STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return root, stub, tmp_path


def run(box, plan=None):
    root, stub, tmp = box
    env = dict(os.environ, PY=str(stub), WAIT="0", HOME_ZIP=str(tmp), STUB_CALLS=str(tmp / "calls.jsonl"),
               STUB_PLAN=json.dumps(plan or {}), HOME=str(tmp / "home"))
    p = subprocess.run(["bash", str(root / "tools" / "sprint_overnight.sh")], cwd=tmp, env=env, capture_output=True, text=True,
                       timeout=120)
    calls = [json.loads(l) for l in (tmp / "calls.jsonl").read_text().splitlines()] if (tmp / "calls.jsonl").exists() else []
    log = (root / "data" / "sprint" / "logs" / "overnight.log").read_text()
    return p.returncode, calls, log


def test_everything_runs_in_order_and_both_zips_are_made(box):
    rc, calls, log = run(box)
    names = [c[0] for c in calls]
    assert rc == 0 and "ALL DONE" in log
    assert names[0] == "sprint_pull9.py"
    assert names.index("sprint_pull10.py") < names.index("sprint_r10_noise.py") < names.index("sprint_r10_credit.py") \
        < names.index("sprint_r10_grid.py") < names.index("sprint_r10_swing.py")
    assert names.index("sprint_round9.py") > names.index("sprint_pull9.py")
    hist = [c for c in calls if c[0] == "sprint_pull.py"]
    assert hist[0][1:] == ["--period", "HIST", "--symbols", "DIA,XLK,XLF,SMH"]
    assert hist[1][1:] == ["--symbols", "DIA,XLK,XLF,SMH", "--from", "2024-08-01", "--to", "2026-06-30", "--stock-bars-only"]
    assert [c for c in calls if c[0] == "sprint_pull10.py"][0][1:] == ["--div-scope", "rebalance"]
    _, _, tmp = box
    assert (tmp / "sprint_results9.zip").exists() and (tmp / "sprint_results10.zip").exists()
    for c in calls:
        assert "--locked" not in c and "--frozen" not in c


def test_a_network_failure_is_retried_and_a_rerun_skips_finished_stages(box):
    rc, calls, log = run(box, {"sprint_pull9.py": [1, 4, 0], "sprint_pull10.py": [1, 0]})
    assert rc == 0 and [c[0] for c in calls].count("sprint_pull9.py") == 3 and [c[0] for c in calls].count("sprint_pull10.py") == 2
    assert "pull9: try 3 of 8" in log and "ALL DONE" in log
    root, stub, tmp = box
    (tmp / "calls.jsonl").unlink()
    rc, calls, log = run(box)
    assert rc == 0 and calls == [] and log.count("done before, skipped") >= 9


def test_a_missing_key_or_a_locked_period_stops_at_once(box):
    rc, calls, log = run(box, {"sprint_pull9.py": [3]})
    assert rc == 3 and [c[0] for c in calls] == ["sprint_pull9.py"] and "not retried" in log and "STOPPED" in log


def test_a_failed_analysis_does_not_stop_the_others(box):
    rc, calls, log = run(box, {"sprint_r10_grid.py": [1, 1]})
    names = [c[0] for c in calls]
    assert rc == 0 and names.count("sprint_r10_grid.py") == 2 and "sprint_r10_swing.py" in names
    assert "finished with failures: r10_grid" in log


def test_it_refuses_to_run_inside_the_desk_folder(tmp_path):
    desk = tmp_path / "home" / "desk"
    (desk / "tools").mkdir(parents=True)
    shutil.copy(HERE / "tools" / "sprint_overnight.sh", desk / "tools" / "sprint_overnight.sh")
    p = subprocess.run(["bash", str(desk / "tools" / "sprint_overnight.sh")], env=dict(os.environ, HOME=str(tmp_path / "home")),
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 3 and "REFUSED" in p.stdout
