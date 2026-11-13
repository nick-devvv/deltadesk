"""deploy/vps_setup.sh: parses, never starts the desk, never prints a secret, and keeps two desks from running."""
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "vps_setup.sh"


def test_script_parses():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode == 0


def test_script_does_not_start_the_desk():
    s = SCRIPT.read_text()
    assert "enable --now" not in s and "systemctl --user start" not in s


def test_script_never_reads_or_prints_secrets():
    s = SCRIPT.read_text()
    for name in ("TELEGRAM_BOT_TOKEN", "DESK_TOKEN", "SCHWAB_APP_SECRET", "ALPACA_SECRET", "NTFY_TOPIC"):
        assert name not in s
    assert "cat ~/.config/deltadesk/deltadesk.env" not in s


def test_ssh_goes_key_only_only_when_a_key_was_given():
    s = SCRIPT.read_text()
    assert 'if [ -s "$AK" ]; then' in s and "PasswordAuthentication no" in s


def test_move_runbook_prints_names_not_values():
    doc = (ROOT / "deploy" / "VPS_MOVE.md").read_text()
    assert "cut -d= -f1" in doc and "KRONOS` out" in doc
