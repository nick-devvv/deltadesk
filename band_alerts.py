"""band_alerts.py - phone alerts for the noise band's PAPER entries and exits (2026-11-17).

Nick, 2026-11-17: "i keep getting notifications and a lot of the time they are useless ... maybe getting ones only for
these would be good" (two noise band 0DTE trades). So the phone gets one alert when the `noise` ledger (the reference
noise band, Zarattini, Aziz & Barbon 2024, SPY/QQQ 0DTE options, noiseband.py) opens a paper position and one when it
closes it; config/v4.json "phone_alert_kinds" = ["band", "mytrades"] (Nick kept the alerts on trades he logs himself).
The co-pilot keeps running for the desk feed and its report card, off the phone.

Every number in an alert is read from the desk's own records (fill, stop, exit, P/L); nothing is computed here but the
wording. All PAPER (simulated fills). Each alert carries the evidence in one line: the same signals on real 0DTE option
prices lost on average (T42, BACKTEST), so a win is a big trend day, not proof.

De-duplicated per position and event (alerts.alert ref), only for today's positions, so a restart or an update never
re-sends old trades. VOID positions (expiry_void.py) never alert.
"""
import core
import store

VERSION = "2026-11-17.band-alerts1"
LEDGER = "noise"
EVIDENCE = ("Evidence: on real 0DTE option prices this exact band lost on average (T42 backtest, Feb 2024-2026, "
            "627 trades, 13% won, -3.2% of premium per trade). It pays on big one-way days.")


def _hhmm(ts):
    return str(ts or "")[11:16]


def _stop_text(p):
    pl = p.get("plan") or {}
    parts = []
    if pl.get("stop_px") is not None:
        parts.append(f"{p['ticker']} back {'above' if p.get('side') == 'P' else 'below'} {float(pl['stop_px']):.2f} at a half-hour check")
    if pl.get("premium_stop") is not None:
        parts.append(f"the option bid at ${float(pl['premium_stop']):.2f}")
    return " or ".join(parts) or "the band rules"


def _exit_px(pid):
    r = store.q("SELECT filled_price, ts FROM orders WHERE position_id=? AND side='sell' AND status='FILLED' ORDER BY ts DESC LIMIT 1", (pid,))
    return (r[0]["filled_price"], r[0]["ts"]) if r else (None, None)


def entry_text(p):
    title = f"Noise band: bought {p['ticker']} {p['contract']} x{p['qty_init']} (PAPER)"
    body = (f"Paper fill ${float(p['fill']):.2f} at {_hhmm(p['opened'])} ET. Stop: {_stop_text(p)}. "
            f"All out by 15:25 ET. {EVIDENCE}")
    return title, body


def exit_text(p):
    px, ts = _exit_px(p["id"])
    pl = p.get("plan") or {}
    r = float(p.get("realized") or 0)
    title = f"Noise band: sold {p['ticker']} {p['contract']} {'+' if r >= 0 else '-'}${abs(r):,.2f} (PAPER)"
    body = (f"Paper exit {'$' + format(float(px), '.2f') if px is not None else 'n/a'} at {_hhmm(ts or p.get('closed'))} ET"
            f" ({pl.get('exit_reason') or 'exit'}). Paid ${float(p['fill']):.2f}. Trade P/L ${r:+,.2f} after costs, simulated.")
    return title, body


def push(day=None):
    """Send any noise band entry or exit of `day` (default today, ET) not sent yet. Returns how many were sent."""
    import alerts
    day = str(day or core.now_et().date().isoformat())
    n = 0
    for p in store.positions(ledger=LEDGER, day=day):
        if p["status"] not in ("OPEN", "CLOSED"):
            continue
        t, b = entry_text(p)
        n += bool(alerts.alert("band", t, b, f"band:{p['id']}:open", "high"))
        if p["status"] == "CLOSED":
            t, b = exit_text(p)
            n += bool(alerts.alert("band", t, b, f"band:{p['id']}:close", "high"))
    return n
