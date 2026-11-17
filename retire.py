"""retire.py - v4: which paper ledgers take no NEW entries, and the Kronos switch. Pure code, no network, no AI.

The `old` ledger (policy_old.py, frozen 2026-10-28.3 rules) ran as a legacy forward test from 2026-10-31 and is
retired since 2026-11-16 (Nick: "why is the old rules even being traded"). Its code path is unchanged
(tests/test_v4_old_regression.py replays it with the guard lifted).

Since 2026-11-17 (Nick: "Stop them") only the four rules that passed their sealed backtests trade on paper (config
"four_rules": nbs_spy_ls, etf10_rsi2, pead_t21_tp, core_sso) plus the reference `noise` ledger. Every other v4 ledger is
on the list too, and v4store.open_position refuses a new position for any retired ledger, whatever its own switch says.

A retired ledger keeps its code, its database rows and its open trades: open positions are still managed to their exit
by the same code as before. Only new entries are refused, at every entry point (paper.buy, the lab, the scanner,
autopilot, news momentum, ORBX, the router; the old-policy guard stays in place, inactive while `old` is off the list). The list lives in config/v4.json; if that file is
missing or unreadable the defaults below apply, so a broken file can never silently un-retire a ledger.

Tests: legacy suites exercise the retired code paths with retirement switched off (`_override = False`, set in
tests/conftest.py for every test module that is not a v4 module); the v4 suites run with the production setting.
"""
import json

import core

FILE = core.HERE / "config" / "v4.json"
VERSION = "2026-11-17.v4-retire3"   # retire3: only the 4 rules + `noise` trade (Nick: "Stop them"); v4 ledgers guarded in v4store.open_position
REASON = "retired in v4: no new entries (code and history kept; open trades are still managed to their exit)"
DEFAULTS = {"retire_active": True,
            "retired": ["paper", "research", "exit31", "gated", "orbx_swing", "orbx_atr", "orbx_2r", "orbx_ormid",
                        "news_mom", "inplay", "board", "earn_post", "earn_pre", "old",
                        "noise_v2", "noise_trend", "orb_credit", "ic_20d", "sip_orb5", "sip_orb5_x", "sip_orb15", "earn_day", "fb_or", "otm_put", "otm_bounce", "otm_h", "copilot", "nbs_spy_long", "pead_t21", "core_spy", "core_trend"],
            "retired_prefixes": ["lab_", "spec_"],
            "legacy_forward_tests": {},
            "kronos_enabled": False}
STOPPED_2026_11_17 = ("noise_v2", "noise_trend", "orb_credit", "ic_20d", "sip_orb5", "sip_orb5_x", "sip_orb15", "earn_day",
                      "fb_or", "otm_put", "otm_bounce", "otm_h", "copilot", "nbs_spy_long", "pead_t21", "core_spy", "core_trend")
_override = None                       # tests only: None = production setting from config/v4.json
_active_in_tests = frozenset()         # tests only: ledgers whose own rule tests run as if not retired
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
    if led in _active_in_tests:
        return False
    c = cfg()
    return led in set(c.get("retired") or []) or led.startswith(tuple(c.get("retired_prefixes") or []))


def retired_list():
    c = cfg()
    return {"active": active(), "ledgers": list(c.get("retired") or []), "prefixes": list(c.get("retired_prefixes") or []),
            "why": c.get("retired_why"), "version": VERSION}


def legacy_label(ledger):
    """The label of a ledger kept active as a legacy forward test (e.g. `old`), or None."""
    return (cfg().get("legacy_forward_tests") or {}).get(str(ledger))


def kronos_enabled():
    return bool(cfg().get("kronos_enabled", False))
