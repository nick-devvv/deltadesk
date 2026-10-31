"""v4api.py - the /api/v4 endpoints (server.py hands every /api/v4* request here). Read-only views of the v4 paper
ledgers plus the v4 kill switch. Nothing here can place an order anywhere.

GET  /api/v4/chains           option-chain logger status (data/chains, gitignored)
"""


def _one(q, k, default=None):
    v = (q or {}).get(k)
    return v[0] if isinstance(v, list) and v else (v if v is not None else default)


def get(path, q):
    if path == "/api/v4/chains":
        import chain_logger
        return chain_logger.status()
    return None


def post(path, body):
    return None
