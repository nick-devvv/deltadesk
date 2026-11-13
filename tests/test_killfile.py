"""killfile (B7): `touch KILL` halts v4 paper entries and closes open paper positions once; held off while the file
exists; removing it never re-enables entries. No network."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import killfile  # noqa: E402
import store  # noqa: E402
import v4store as S  # noqa: E402


def test_kill_file_acts_once_holds_off_and_never_reenables(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    import v4exec
    monkeypatch.setattr(v4exec, "close_now", lambda p, reason, quotes=None: None)      # no quote in tests: pending
    calls = []
    import v4risk
    real = v4risk.kill
    monkeypatch.setattr(v4risk, "kill", lambda reason="x": calls.append(reason) or real(reason))
    f = tmp_path / "KILL"
    assert killfile.check(f) == {"present": False} and store.kv_get("v4_enabled", True)
    f.write_text("")
    r = killfile.check(f)
    assert r["acted"] and calls == ["KILL file"] and store.kv_get("v4_enabled") is False
    store.kv_set("v4_enabled", True)                                     # someone flips it back while the file exists
    r = killfile.check(f)
    assert not r["acted"] and calls == ["KILL file"] and store.kv_get("v4_enabled") is False
    f.unlink()
    killfile.check(f)
    assert store.kv_get("v4_enabled") is False                           # removal never re-enables


def test_no_order_path():
    code = (ROOT / "killfile.py").read_text().split('"""', 2)[2]
    assert "import broker" not in code and "place_order" not in code and "/trader" not in code
