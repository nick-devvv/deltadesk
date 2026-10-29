"""Shared test setup. Tests are hermetic even on Chart's computer, where the real secrets are in the environment:
no phone alert, no chat webhook, no Schwab/Alpaca/Quiver call, and the real Schwab token file is never read or written."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    for k in ("NTFY_TOPIC", "CHAT_WEBHOOK", "GROK_WEBHOOK", "SCHWAB_APP_KEY", "SCHWAB_APP_SECRET",
              "ALPACA_KEY", "ALPACA_SECRET", "QUIVER_KEY"):
        monkeypatch.delenv(k, raising=False)
    import schwab
    monkeypatch.setattr(schwab, "TOKEN_FILE", tmp_path / "no_schwab_token.json")
