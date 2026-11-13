"""telegram_alerts: off unless both env values are set; private to one chat id; Took / Skipped buttons feed the co-pilot
report card; restart-safe offset; the token never reaches a log; nothing can trade. No network."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import alerts  # noqa: E402
import store  # noqa: E402
import telegram_alerts as TG  # noqa: E402

TOKEN = "123456789:" + "A" * 35
CHAT = "987654321"
AID = "SPY|2026-11-24|10:00|5m|wick_reject|short"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB", tmp_path / "desk.db")
    monkeypatch.setattr(store, "_conn", None)
    monkeypatch.setattr(TG, "_ASYNC", False)
    calls = []

    def fake_post(method, payload, timeout=10):
        calls.append((method, payload))
        if method == "getUpdates":
            return {"ok": True, "result": fake_post.updates}
        return {"ok": True}
    fake_post.updates = []
    monkeypatch.setattr(TG, "_post", fake_post)
    TG._state.update(sent=0, taps=0, last_error=None)
    yield monkeypatch, calls, fake_post


def on(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT)


def test_off_unless_both_values_are_valid(env):
    mp, calls, _ = env
    assert not TG.configured() and TG.send("t", "b") is False and calls == []
    mp.setenv("TELEGRAM_BOT_TOKEN", "not-a-token")
    mp.setenv("TELEGRAM_CHAT_ID", CHAT)
    assert not TG.configured()
    on(mp)
    assert TG.configured() and alerts.settings()["telegram"] is True and alerts.settings()["phone"] is True


def test_alert_goes_to_telegram_with_buttons_only_on_copilot_alerts(env):
    mp, calls, _ = env
    on(mp)
    assert alerts.alert("copilot", "COPILOT SPY SHORT: <wick>", "Close 1 & stop 2", AID, "high")
    m, p = calls[-1]
    assert m == "sendMessage" and p["chat_id"] == CHAT and p["parse_mode"] == "HTML"
    assert p["text"].startswith("<b>COPILOT SPY SHORT: &lt;wick&gt;</b>") and "&amp;" in p["text"]
    btn = p["reply_markup"]["inline_keyboard"][0]
    assert [b["callback_data"] for b in btn] == [f"t:{AID}", f"s:{AID}"] and all(len(b["callback_data"]) <= 64 for b in btn)
    assert alerts.alert("news", "Fed", "headline", "n1")
    assert "reply_markup" not in calls[-1][1]
    assert not alerts.alert("copilot", "dup", "dup", AID)                     # alerts.alert still de-duplicates


def test_button_tap_from_nick_saves_the_answer_and_others_are_ignored(env):
    mp, calls, _ = env
    on(mp)
    store.kv_set("copilot:alerts:2026-11-24", [{"id": AID, "ticker": "SPY"}])
    tap = {"update_id": 5, "callback_query": {"id": "cb1", "data": f"t:{AID}", "message": {"message_id": 77, "chat": {"id": int(CHAT)}}}}
    assert TG.handle(tap) == "feedback took"
    assert store.kv_get("copilot:alerts:2026-11-24")[0]["answer"] == "took"
    methods = [m for m, _ in calls]
    assert methods == ["answerCallbackQuery", "editMessageReplyMarkup"]
    stranger = {"update_id": 6, "callback_query": {"id": "cb2", "data": f"s:{AID}", "message": {"message_id": 78, "chat": {"id": 111}}}}
    assert TG.handle(stranger) == "ignored: other chat"
    assert store.kv_get("copilot:alerts:2026-11-24")[0]["answer"] == "took"
    assert TG.handle({"update_id": 7, "message": {"chat": {"id": 111}, "text": "/status"}}) == "ignored: other chat"


def test_status_and_help_are_read_only_and_poll_offset_survives_a_restart(env, monkeypatch):
    mp, calls, fake = env
    on(mp)
    import copilot
    monkeypatch.setattr(copilot, "switches", lambda: (True, False))
    fake.updates = [{"update_id": 40, "message": {"chat": {"id": int(CHAT)}, "text": "/status"}},
                    {"update_id": 41, "message": {"chat": {"id": int(CHAT)}, "text": "/help"}},
                    {"update_id": 42, "message": {"chat": {"id": int(CHAT)}, "text": "buy 10 calls"}}]
    assert TG.poll_once(0) == 3 and store.kv_get("telegram:offset") == 43
    sent = [p["text"] for m, p in calls if m == "sendMessage"]
    assert len(sent) == 2 and "Desk paper entries" in sent[0] and "Read-only" in sent[0]
    fake.updates = []
    TG.poll_once(0)
    assert [p for m, p in calls if m == "getUpdates"][-1]["offset"] == 43


def test_token_never_reaches_the_error_log(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT)

    def boom(req, timeout=10):
        raise OSError(f"failed {req.full_url}")
    monkeypatch.setattr(TG.urllib.request, "urlopen", boom)
    assert TG._post("sendMessage", {"x": 1}) is None
    assert TG._state["last_error"] == "sendMessage: OSError" and TOKEN not in str(TG.status())


def test_wiring_and_no_order_path():
    code = (ROOT / "telegram_alerts.py").read_text().split('"""', 2)[2]
    assert "import broker" not in code and "place_order" not in code and "/trader" not in code
    assert "v4risk" not in code and "kill(" not in code and "enable(" not in code     # cannot flip a switch
    assert "import telegram_alerts" in (ROOT / "server.py").read_text()
    import release
    assert release.component_versions()["telegram_alerts.VERSION"] == TG.VERSION
    env = (ROOT / "deploy" / "deltadesk.env.example").read_text()
    assert "TELEGRAM_BOT_TOKEN=<" in env and "TELEGRAM_CHAT_ID=<" in env and "NTFY_TOPIC=<" in env
