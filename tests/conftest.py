"""Shared test setup. Tests are hermetic even on Chart's computer, where the real secrets are in the environment:
no phone alert, no chat webhook, no Schwab/Alpaca/Quiver call, and the real Schwab token file is never read or written."""
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _no_network(*a, **k):
    raise urllib.error.URLError("network is disabled in tests")


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    for k in ("NTFY_TOPIC", "CHAT_WEBHOOK", "GROK_WEBHOOK", "SCHWAB_APP_KEY", "SCHWAB_APP_SECRET",
              "ALPACA_KEY", "ALPACA_SECRET", "QUIVER_KEY", "XAI_API_KEY", "SEC_USER_AGENT"):
        monkeypatch.delenv(k, raising=False)
    import schwab
    import schwab_stream
    monkeypatch.setattr(schwab, "TOKEN_FILE", tmp_path / "no_schwab_token.json")
    monkeypatch.setattr(schwab, "_urlopen", _no_network)
    monkeypatch.setattr(schwab_stream, "available", lambda: False)   # a test that needs the stream turns it on itself
    schwab.reset_state()
    import catalysts
    monkeypatch.setattr(catalysts, "SEC_TICKERS_FILE", tmp_path / "sec_company_tickers.json")
    monkeypatch.setattr(catalysts, "_http", _no_network)
    monkeypatch.setattr(catalysts, "_xai_post", _no_network)
    monkeypatch.setattr(catalysts, "_fetch_doc", _no_network)       # source content checks never leave the test
    import lab
    monkeypatch.setattr(lab, "ARCHIVE", tmp_path / "bars")          # never write test bars into the real archive
    yield
    schwab_stream.stop("test finished")
    schwab.reset_state()
