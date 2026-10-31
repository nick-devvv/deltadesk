"""Sprint locked periods (sprint/periods.py): any range touching L1 (2026-07-01..2026-10-30) or L2 (2024-02-01..
2024-07-31) is refused by the runner and the puller unless --locked names it and --frozen matches the spec's sha256
as committed in git (no uncommitted edits)."""
import json
import subprocess
import sys
from datetime import date

import pytest

from sprint import periods, runner

ROOT = periods.REPO
sys.path.insert(0, str(ROOT / "tools"))                 # sprint_run, sprint_pull, pull_alpaca


def test_dev_and_locked_boundaries():
    assert periods.DEV == (date(2024, 8, 1), date(2026, 6, 30))
    assert periods.overlaps("2024-08-01", "2026-06-30") == []
    assert periods.overlaps("2024-07-31", "2024-08-01") == ["L2"]
    assert periods.overlaps("2026-06-30", "2026-07-01") == ["L1"]
    assert periods.overlaps("2026-10-31", "2026-12-31") == []
    assert periods.overlaps("2024-01-01", "2026-12-31") == ["L1", "L2"]
    assert periods.guard(date(2025, 1, 2), date(2025, 6, 30)) == []
    for a, b in (("2024-07-15", "2024-08-15"), ("2026-06-01", "2026-07-02"), ("2024-02-01", "2024-02-01")):
        with pytest.raises(periods.LockedPeriod, match="REFUSED"):
            periods.guard(a, b)


def _git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"spec_id": "x", "blocks": []}))
    _git(tmp_path, "add", "spec.json")
    _git(tmp_path, "commit", "-q", "-m", "freeze")
    return tmp_path, spec


def test_locked_run_needs_the_frozen_committed_spec(repo):
    tmp, spec = repo
    sha = periods.sha256_file(spec)
    a, b = periods.LOCKED["L2"]
    with pytest.raises(periods.LockedPeriod, match="REFUSED"):
        periods.guard(a, b, spec_path=spec)                                  # no --locked
    with pytest.raises(periods.LockedPeriod, match="names only L1"):
        periods.guard(a, b, "L1", sha, spec)                                 # wrong period named
    with pytest.raises(periods.LockedPeriod, match="not frozen"):
        periods.guard(a, b, "L2", "0" * 64, spec)                            # wrong sha
    assert periods.guard(a, b, "L2", sha, spec) == ["L2"]                    # frozen and committed: allowed
    spec.write_text(json.dumps({"spec_id": "x", "blocks": [], "tweak": 1}))  # edited after the commit
    with pytest.raises(periods.LockedPeriod, match="not frozen"):
        periods.guard(a, b, "L2", periods.sha256_file(spec), spec)
    new = tmp / "new.json"
    new.write_text("{}")
    with pytest.raises(periods.LockedPeriod, match="not committed"):
        periods.guard(a, b, "L2", periods.sha256_file(new), new)


def test_runner_refuses_locked_periods_before_reading_any_data(tmp_path, monkeypatch):
    spec = tmp_path / "s.json"
    spec.write_text(json.dumps({"spec_id": "s", "symbols": ["SPY"], "blocks": [{"name": "x", "grid": {"entry": ["orb15"]}}]}))
    import sprint.engine as E
    monkeypatch.setattr(E, "run_pass", lambda *a, **k: (_ for _ in ()).throw(AssertionError("data was read")))
    with pytest.raises(periods.LockedPeriod):
        runner.run_spec(spec, date(2026, 6, 1), date(2026, 7, 31), out_dir=tmp_path)
    with pytest.raises(periods.LockedPeriod):
        runner.run_spec(spec, locked="L1", frozen="0" * 64, out_dir=tmp_path)
    spec.write_text(json.dumps({"spec_id": "s", "period": "L2", "symbols": ["SPY"], "blocks": []}))
    with pytest.raises(periods.LockedPeriod):
        runner.run_spec(spec, out_dir=tmp_path)
    import sprint_run
    assert sprint_run.main([str(spec), "--from", "2024-07-01", "--to", "2024-08-31", "--out", str(tmp_path)]) == 2


def test_puller_refuses_locked_periods_without_any_request(monkeypatch, capsys):
    import pull_alpaca as PA
    import sprint_pull
    monkeypatch.setattr(PA, "_http", lambda *a: (_ for _ in ()).throw(AssertionError("network")))
    assert sprint_pull.main(["--symbols", "SPY", "--from", "2024-06-03", "--to", "2024-08-30"]) == 2
    assert sprint_pull.main(["--symbols", "SPY", "--from", "2026-07-01", "--to", "2026-07-10", "--locked", "L1",
                             "--frozen", "0" * 64, "--spec", str(ROOT / "sprint" / "specs" / "orb_exits_v1.json")]) == 2
    assert "REFUSED" in capsys.readouterr().err


def test_shipped_spec_is_dev_only():
    spec = json.loads((ROOT / "sprint" / "specs" / "orb_exits_v1.json").read_text())
    assert spec.get("period", "DEV") == "DEV"
    for f in ["tools/sprint_run.py", "tools/sprint_pull.py"] + [f"sprint/{p.name}" for p in (ROOT / "sprint").glob("*.py")]:
        src = (ROOT / f).read_text()
        for bad in ("paper-api", "/v2/orders", "/v2/positions", "import broker", "api.alpaca.markets/v2/"):
            assert bad not in src, (f, bad)
