"""v4api.py - the /api/v4 endpoints (server.py hands every /api/v4* request here). Read-only views of the v4 paper
ledgers plus the v4 kill switch. Nothing here can place an order anywhere.

GET  /api/v4/chains           option-chain logger status (data/chains, gitignored)
GET  /api/v4/risk             the shared v4 risk layer: hard-coded limits, open counts, book P/L today, FOMC flag
POST /api/v4/kill             {"reason"}: v4 entries OFF and every open v4 paper position closed (pending if no quote)
POST /api/v4/enable           {"on": true|false}: v4 entries back on (or off without closing anything)
"""


def _one(q, k, default=None):
    v = (q or {}).get(k)
    return v[0] if isinstance(v, list) and v else (v if v is not None else default)


def get(path, q):
    if path == "/api/v4/chains":
        import chain_logger
        return chain_logger.status()
    if path == "/api/v4/risk":
        import v4risk
        return v4risk.status()
    return None


def post(path, body):
    import v4risk
    if path == "/api/v4/kill":
        return v4risk.kill(str((body or {}).get("reason") or "kill switch (API)")[:120])
    if path == "/api/v4/enable":
        return v4risk.enable(bool((body or {}).get("on", True)))
    return None
