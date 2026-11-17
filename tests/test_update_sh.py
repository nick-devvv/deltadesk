"""deploy/update.sh (2026-11-17): runs detached so a dropped SSH connection can't stop it, deploys only after the
new version's tests pass, refuses a second copy, and --status shows how the last update ended.

Each test builds a tiny throwaway "GitHub" repo and a desk checkout of it in tmp_path. Nothing is restarted
(DESK_RESTART=0), so running this suite on the server can never touch the live desk.
"""
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "update.sh"

pytestmark = pytest.mark.skipif(
    not all(shutil.which(t) for t in ("git", "setsid", "flock", "tail")),
    reason="needs git, setsid, flock and GNU tail (the server and CI have them)")

OK_TEST = "def test_ok():\n    assert True\n"
SLOW_TEST = "import time\n\n\ndef test_slow():\n    time.sleep(3)\n"
BAD_TEST = "def test_bad():\n    assert False\n"


IDENT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, **IDENT}).stdout.strip()


def _commit(repo, files, msg):
    for name, text in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def desk(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    (origin / "deploy").mkdir()
    shutil.copy2(SCRIPT, origin / "deploy" / "update.sh")
    _commit(origin, {"tests/test_ok.py": OK_TEST}, "first")
    d = tmp_path / "desk"
    subprocess.run(["git", "clone", "-q", f"file://{origin}", str(d)], check=True, capture_output=True,
                   env={**os.environ, **IDENT})
    env = {k: v for k, v in os.environ.items() if not k.startswith("DESK_")}
    env.update(IDENT, DESK_DIR=str(d), PYTHON=sys.executable, DESK_RESTART="0",
               DESK_UPDATE_LOG=str(tmp_path / "update.log"))
    return {"origin": origin, "desk": d, "env": env, "log": tmp_path / "update.log",
            "script": str(d / "deploy" / "update.sh")}


def _run(t, *args, timeout=120):
    return subprocess.run([t["script"], *args], env=t["env"], capture_output=True, text=True, timeout=timeout)


def _wait_for(path, text, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and text in path.read_text():
            return True
        time.sleep(0.2)
    return False


def test_script_parses():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode == 0


def test_update_deploys_after_the_tests_pass_and_logs_everything(desk):
    new = _commit(desk["origin"], {"tests/test_two.py": OK_TEST}, "second")
    r = _run(desk, "--force")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _git(desk["desk"], "rev-parse", "HEAD") == new
    log = desk["log"].read_text()
    assert "Deployed" in log and "== update finished: exit 0" in log
    assert "runs in the background" in r.stdout and "Deployed" in r.stdout   # the live view shows the same log


def test_failing_tests_change_nothing(desk):
    before = _git(desk["desk"], "rev-parse", "HEAD")
    _commit(desk["origin"], {"tests/test_bad.py": BAD_TEST}, "broken")
    r = _run(desk, "--force")
    assert r.returncode == 1
    assert _git(desk["desk"], "rev-parse", "HEAD") == before
    log = desk["log"].read_text()
    assert "STOP: the tests failed" in log and "== update finished: exit 1" in log


def test_a_dropped_connection_does_not_stop_the_update(desk):
    new = _commit(desk["origin"], {"tests/test_slow.py": SLOW_TEST}, "slow")
    p = subprocess.Popen([desk["script"], "--force"], env=desk["env"], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, start_new_session=True)
    assert _wait_for(desk["log"], "Testing"), "the update never started testing"
    os.killpg(p.pid, signal.SIGHUP)          # what a dropped SSH session does to everything it started
    p.stdout.close()
    p.wait(timeout=10)
    assert _wait_for(desk["log"], "== update finished"), desk["log"].read_text()
    assert "== update finished: exit 0" in desk["log"].read_text()
    assert _git(desk["desk"], "rev-parse", "HEAD") == new


def test_only_one_update_at_a_time_and_status_says_so(desk):
    new = _commit(desk["origin"], {"tests/test_slow.py": SLOW_TEST}, "slow")
    first = subprocess.Popen([desk["script"], "--force"], env=desk["env"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
    try:
        assert _wait_for(desk["log"], "Testing")
        second = _run(desk, "--force")
        assert second.returncode == 1 and "already running" in second.stdout
        st = _run(desk, "--status")
        assert st.returncode == 0 and "An update is running now" in st.stdout
    finally:
        out, _ = first.communicate(timeout=120)
    assert first.returncode == 0, out
    assert _git(desk["desk"], "rev-parse", "HEAD") == new
    log = desk["log"].read_text()
    assert log.count("== update finished") == 1      # the refused copy didn't touch the first one's log


def test_status_when_idle_shows_the_version_and_the_last_log(desk):
    _commit(desk["origin"], {"tests/test_two.py": OK_TEST}, "second")
    assert _run(desk, "--force").returncode == 0
    st = _run(desk, "--status")
    assert st.returncode == 0
    assert "No update is running." in st.stdout
    assert _git(desk["desk"], "log", "-1", "--format=%h") in st.stdout
    assert "== update finished: exit 0" in st.stdout


def test_already_up_to_date_finishes_cleanly(desk):
    r = _run(desk, "--force")
    assert r.returncode == 0 and "Already up to date" in r.stdout


def test_the_test_suite_runs_niced_without_the_lock():
    s = SCRIPT.read_text()
    assert 'nice -n 10 "$PY" -m pytest -q tests/ 9>&-' in s
    assert "setsid nohup" in s and 'DESK_RESTART:-1' in s


def test_rollback_also_runs_detached_and_goes_back(desk):
    before = _git(desk["desk"], "rev-parse", "HEAD")
    _commit(desk["origin"], {"tests/test_two.py": OK_TEST}, "second")
    assert _run(desk, "--force").returncode == 0
    r = _run(desk, "--rollback", "--force")
    assert r.returncode == 0, r.stdout
    assert _git(desk["desk"], "rev-parse", "HEAD") == before
    assert "rolling back" in desk["log"].read_text()
