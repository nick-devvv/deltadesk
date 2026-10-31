"""release.py - v3.5: the release identity and run manifests (what code, rules and models produced a result).

A manifest freezes more than the policy's version string: the sha256 of every source file, the policy and registry
hashes, and the version of every detector, fill model, exit model and outcome scorer that was live. Research runs,
lab days and paper ledgers record the manifest id they ran under, so results from different code never mix silently.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RELEASE = "4.0"
RELEASE_ID = "2026-11-02.v4"
HERE = Path(__file__).resolve().parent
SOURCE_GLOBS = ("*.py", "index.html", "config/*.json", "grok/*.md", "grok/*.json")


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def source_hashes(root=HERE):
    out = {}
    for g in SOURCE_GLOBS:
        for p in sorted(Path(root).glob(g)):
            if p.is_file():
                out[str(p.relative_to(root))] = sha256_file(p)
    return out


def _digest(d):
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def component_versions():
    """Every versioned component that can change a result. Imports are local so a broken optional module can't
    stop the server; a missing one is reported as such."""
    out = {}
    for mod, attrs in (("core", ()), ("entrygate", ("VERSION",)), ("lab", ("VERSION",)), ("contract_lab", ("VERSION", "SCORER")),
                       ("strategy_router", ("VERSION",)), ("research", ("VERSION",)), ("diagnostics", ("FRAME_VERSION",)),
                       ("replay", ("REPLAY_VERSION",)), ("scanner", ("BACKTEST_VERSION",)), ("noiseband", ("VERSION",)),
                       ("scanner_setups", ("VERSION",)), ("autopilot", ("BOARD_VERSION",)), ("orb_retest", ("VERSION",)),
                       ("news_momentum", ("VERSION",)), ("underlying_first", ("VERSION",)), ("learning", ("SCHEMA_VERSION",)),
                       ("retire", ("VERSION",)), ("noise_v2", ("VERSION",)), ("noise_trend", ("VERSION",)),
                       ("orb_credit", ("VERSION",)), ("ic_20d", ("VERSION",)), ("sip_orb", ("VERSION",)),
                       ("news_drift", ("VERSION",)), ("chain_logger", ("VERSION",)), ("v4risk", ("VERSION",))):
        try:
            m = __import__(mod)
            for a in attrs:
                out[f"{mod}.{a}"] = getattr(m, a, None)
        except Exception as e:
            out[mod] = f"unavailable ({type(e).__name__})"
    try:
        import paper
        out["paper.EXEC_MODEL"] = paper.EXEC_MODEL
    except Exception:
        pass
    try:
        import core
        out["policy.version"] = core.policy()["version"]
    except Exception:
        pass
    return out


def manifest(kind="runtime", params=None, root=HERE):
    src = source_hashes(root)
    pol = (Path(root) / "config" / "policy.json")
    spec = (Path(root) / "config" / "specialists.json")
    m = {"release": RELEASE_ID, "kind": kind, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "source_digest": _digest(src), "files": len(src),
         "policy_sha256": sha256_file(pol) if pol.exists() else None,
         "registry_sha256": sha256_file(spec) if spec.exists() else None,
         "components": component_versions(), "params": params or {}}
    m["manifest_id"] = "M-" + _digest({k: v for k, v in m.items() if k != "created_utc"})[:16]
    return m, src
