"""killfile.py - B7 (2026-11-13, Nick: "build it" + "ye"): a file kill switch for the paper desk.

`touch KILL` in the desk folder (~/desk/KILL on Chart's computer) does what the v4 kill switch does, once per file:
v4 paper entries OFF and every open v4 paper position closed at the current quote (pending if none), plus a phone alert.
While the file exists, entries are held OFF (re-set every check). Removing the file does NOT turn entries back on: that
stays a deliberate step (POST /api/v4/enable or the Risk page). Exits always run. Paper only; there is no order path here.
Idea from calibrain-harness (MIT, github.com/zadescoxp/calibrain-harness): `touch KILL` flattens and halts.
"""
import os
import threading
import time
from pathlib import Path

import store

VERSION = "2026-11-13.killfile-1"
ROOT = Path(__file__).resolve().parent
PATH = ROOT / "KILL"
EVERY_S = 5
_state = {"thread": None, "stop": False, "last": None}


def check(path=None):
    """One check. Returns {"present", "acted", "result"}; acts once per file (keyed by its modification time)."""
    p = Path(path or PATH)
    if not p.exists():
        _state["last"] = {"present": False}
        return _state["last"]
    key = f"{p.stat().st_mtime:.3f}"
    done = store.kv_get("killfile:acted") or {}
    import v4risk
    if done.get("key") == key:
        if store.kv_get("v4_enabled", True):
            store.kv_set("v4_enabled", False)                       # held off while the file exists
        _state["last"] = {"present": True, "acted": False}
        return _state["last"]
    r = v4risk.kill("KILL file")
    store.kv_set("killfile:acted", {"key": key, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "result": r})
    try:
        import alerts
        alerts.alert("copilot", "KILL file: desk halted", r["message"], "killfile", "high")
    except Exception:
        pass
    _state["last"] = {"present": True, "acted": True, "result": r}
    return _state["last"]


def _run():
    while not _state["stop"]:
        try:
            check()
        except Exception as e:                                       # never let the watcher die
            _state["last"] = {"error": type(e).__name__}
        time.sleep(EVERY_S)


def start():
    if _state["thread"] and _state["thread"].is_alive():
        return True
    if os.environ.get("KILLFILE_OFF"):
        return False
    _state["stop"] = False
    th = threading.Thread(target=_run, daemon=True, name="killfile")
    _state["thread"] = th
    th.start()
    return True


def status():
    return {"version": VERSION, "path": str(PATH), "present": PATH.exists(), "last": _state["last"],
            "acted": store.kv_get("killfile:acted")}
