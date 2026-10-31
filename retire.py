"""retire.py - v4: which paper ledgers take no NEW entries, and the Kronos switch. Pure code, no network, no AI.

A retired ledger keeps its code, its database rows and its open trades: open positions are still managed to their exit
by the same code as before. Only new entries are refused, at every entry point (paper.buy, the old-policy shadow, the
lab, the scanner, autopilot, news momentum, ORBX, the router). The list lives in config/v4.json; if that file is
missing or unreadable the defaults below apply, so a broken file can never silently un-retire a ledger.

Tests: legacy suites exercise the retired code paths with retirement switched off (`_override = False`, set in
tests/conftest.py for every test module that is not a v4 module); the v4 suites run with the production setting.
"""
import json

import core

FILE = core.HERE / "config" / "v4.json"
VERSION = "2026-10-31.v4-retire1"
REASON = "retired in v4: no new entries (code and history kept; open trades are still managed to their exit)"
DEFAULTS = {"retire_active": True,
            "retired": ["paper", "research", "exit31", "gated", "orbx_swing", "orbx_atr", "orbx_2r", "orbx_ormid", "old",
                        "news_mom", "inplay", "board", "earn_post", "earn_pre"],
            "retired_prefixes": ["lab_", "spec_"],
            "kronos_enabled": False}
_override = None                       # tests only: None = production setting from config/v4.json
_cache = {"mtime": None, "cfg": None}


def cfg():
    try:
        m = FILE.stat().st_mtime
        if _cache["cfg"] is None or _cache["mtime"] != m:
            d = json.loads(FILE.read_text())
            _cache.update(mtime=m, cfg=dict(DEFAULTS, **{k: v for k, v in d.items() if v is not None}))
        return _cache["cfg"]
    except (OSError, ValueError):
        return dict(DEFAULTS)


def active():
    if _override is not None:
        return bool(_override)
    return bool(cfg().get("retire_active", True))


def is_retired(ledger):
    """True when this ledger may not open new paper positions."""
    if not active():
        return False
    led = str(ledger or "")
    c = cfg()
    return led in set(c.get("retired") or []) or led.startswith(tuple(c.get("retired_prefixes") or []))


def retired_list():
    c = cfg()
    return {"active": active(), "ledgers": list(c.get("retired") or []), "prefixes": list(c.get("retired_prefixes") or []),
            "why": c.get("retired_why"), "version": VERSION}


def kronos_enabled():
    return bool(cfg().get("kronos_enabled", False))
