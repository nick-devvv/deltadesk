"""telegram_alerts.py - desk alerts as Telegram messages, with Took / Skipped buttons on co-pilot alerts (2026-11-13).

Nick, 2026-11-12: "is there a way to link it to telegram or discord is that better?" Telegram is private (the bot writes
only to Nick's chat id), free and instant, and its buttons send his answer for a co-pilot alert straight into the report
card (copilot.feedback, B4) without opening the desk.

Setup (both values live only in the desk's environment on Chart's computer, never in git or chat):
  TELEGRAM_BOT_TOKEN  from @BotFather (/newbot)
  TELEGRAM_CHAT_ID    Nick's own chat id (send the bot any message, then read it from getUpdates)
Off when either is missing or malformed. Every alert that reaches alerts.alert() is also sent here (ntfy keeps working
beside it). A background long-poll reads only button taps and two read-only commands (/status, /help) from that one chat
id; anything from any other chat is ignored. Nothing here can trade, change a plan, flip a switch or reveal the desk link.
"""
import html
import json
import os
import re
import threading
import time
import urllib.request

import store

VERSION = "2026-11-13.telegram-1"
API = "https://api.telegram.org"
_ASYNC = True                       # tests set False to send inline
_state = {"thread": None, "stop": False, "last_error": None, "sent": 0, "taps": 0}


def config():
    """(token, chat_id) or (None, None)."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if re.fullmatch(r"\d{5,15}:[A-Za-z0-9_-]{30,64}", tok) and re.fullmatch(r"-?\d{3,20}", chat):
        return tok, chat
    return None, None


def configured():
    return config()[0] is not None


def _post(method, payload, timeout=10):
    tok, _ = config()
    if not tok:
        return None
    req = urllib.request.Request(f"{API}/bot{tok}/{method}", data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception as e:                       # never let the token reach a log: report the error type only
        _state["last_error"] = f"{method}: {type(e).__name__}"
        return None


def _is_copilot_alert(kind, ref):
    return kind == "copilot" and str(ref).count("|") == 5 and len(f"t:{ref}") <= 64


def message(title, body, kind=None, ref=None):
    """The sendMessage payload (without chat_id): bold title, the body, Took / Skipped buttons on co-pilot alerts."""
    text = f"<b>{html.escape(str(title))}</b>\n{html.escape(str(body))}"[:4000]
    p = {"text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if _is_copilot_alert(kind, ref):
        p["reply_markup"] = {"inline_keyboard": [[{"text": "Took it", "callback_data": f"t:{ref}"},
                                                  {"text": "Skipped", "callback_data": f"s:{ref}"}]]}
    return p


def send(title, body, level="normal", kind=None, ref=None):
    """Send one alert (in a thread unless _ASYNC is off). Returns False when Telegram is not set up."""
    tok, chat = config()
    if not tok:
        return False
    p = message(title, body, kind, ref) | {"chat_id": chat, "disable_notification": False}

    def go():
        if _post("sendMessage", p):
            _state["sent"] += 1
    if _ASYNC:
        threading.Thread(target=go, daemon=True).start()
    else:
        go()
    return True


def _status_text():
    import v4common as C
    import copilot
    st = copilot.status()
    blk = C.entries_blocked()
    return "\n".join([f"Desk paper entries: {'BLOCKED - ' + blk if blk else 'ON'}",
                      f"Co-pilot: {st['status']}", f"Co-pilot alerts today: {len(st['alerts'])}, open paper shadows: {len(st['open'])}",
                      "Read-only. The desk page has the full view."])


def handle(update):
    """One getUpdates item. Only Nick's chat counts. Returns what was done (for tests and the log)."""
    _, chat = config()
    if not chat:
        return "off"
    cq = update.get("callback_query")
    if cq:
        cid = str(((cq.get("message") or {}).get("chat") or {}).get("id"))
        if cid != chat:
            return "ignored: other chat"
        data = str(cq.get("data") or "")
        if data[:2] not in ("t:", "s:"):
            return "ignored: unknown button"
        import copilot
        r = copilot.feedback(data[2:], data[0] == "t")
        _state["taps"] += 1
        _post("answerCallbackQuery", {"callback_query_id": cq.get("id"),
                                      "text": f"Saved: {r['answer']}" if r.get("ok") else f"Not saved: {r.get('error')}"})
        if r.get("ok"):
            m = cq.get("message") or {}
            _post("editMessageReplyMarkup", {"chat_id": chat, "message_id": m.get("message_id"), "reply_markup": {
                "inline_keyboard": [[{"text": f"You: {r['answer']}", "callback_data": "done"}]]}})
        return f"feedback {r.get('answer') or r.get('error')}"
    msg = update.get("message") or {}
    if str((msg.get("chat") or {}).get("id")) != chat:
        return "ignored: other chat"
    cmd = str(msg.get("text") or "").strip().split("@")[0].lower()
    if cmd == "/status":
        _post("sendMessage", {"chat_id": chat, "text": _status_text()})
        return "status"
    if cmd in ("/help", "/start"):
        _post("sendMessage", {"chat_id": chat, "text": "DeltaDesk alerts. Tap Took it / Skipped on co-pilot alerts so the report "
                                                       "card learns which ones you trade. /status = desk status (read-only)."})
        return "help"
    return "ignored: text"


def poll_once(timeout=25):
    """Long-poll getUpdates once and handle what arrived. The offset lives in kv, so a restart never replays a tap."""
    off = int(store.kv_get("telegram:offset") or 0)
    r = _post("getUpdates", {"offset": off, "timeout": timeout, "allowed_updates": ["message", "callback_query"]},
              timeout=timeout + 10)
    if not r or not r.get("ok"):
        return 0
    n = 0
    for u in r.get("result") or []:
        try:
            handle(u)
        except Exception as e:
            _state["last_error"] = f"handle: {type(e).__name__}"
        off = max(off, int(u.get("update_id", 0)) + 1)
        n += 1
    store.kv_set("telegram:offset", off)
    return n


def _run():
    while not _state["stop"]:
        try:
            poll_once()
        except Exception as e:
            _state["last_error"] = f"poll: {type(e).__name__}"
            time.sleep(10)


def start():
    if not configured():
        return False
    if _state["thread"] and _state["thread"].is_alive():
        return True
    _state["stop"] = False
    th = threading.Thread(target=_run, daemon=True, name="telegram")
    _state["thread"] = th
    th.start()
    return True


def status():
    return {"version": VERSION, "configured": configured(), "sent": _state["sent"], "taps": _state["taps"],
            "last_error": _state["last_error"], "polling": bool(_state["thread"] and _state["thread"].is_alive())}
