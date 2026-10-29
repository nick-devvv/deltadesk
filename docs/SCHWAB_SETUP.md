# Schwab market data: Nick does these steps himself

From v3, Schwab is the desk's only live source for candles, stock quotes and option quotes. The paper engine only fills on Schwab quotes. Without Schwab the desk still runs, but it shows **FALLBACK - not executable**: plans are marked delayed and the paper engine makes no trades.

The connection is **read-only market data**. The desk's code refuses every Schwab trading and account endpoint. The one exception is `GET /trader/v1/userPreference`, which only returns the streaming server's address and IDs.

## 1. Schwab developer app
1. Go to developer.schwab.com, sign in with your Schwab login, and open your app (or "Create App").
2. API products: **Market Data Production**. Also add **Accounts and Trading Production**: Schwab puts the streaming address behind that product. The desk uses it for that one read and nothing else.
3. Callback URL: exactly `https://127.0.0.1` (no slash at the end, no port).
4. Wait until the app status says **Ready For Use**.

## 2. Keys go into Chart's Secrets, never into a chat
- In Chart's Secrets add `SCHWAB_APP_KEY` (the App Key / Client ID) and `SCHWAB_APP_SECRET` (the Secret).
- If a key or secret was ever pasted into a chat or a document, reset the secret on developer.schwab.com first and use the new one.
- Then tell Chart: "restart the desk server with the new Schwab secrets".

## 3. Connect (about a minute, every 7 days)
1. On the desk: **Rules → Data sources → Open Schwab login**. Log in on Schwab's own site yourself and approve.
2. You land on a page that doesn't load. That's expected. Copy that page's whole address (it contains `?code=`).
3. Paste it into the box and press **Connect** within about 30 seconds.
4. Schwab makes you log in again every 7 days. The desk shows a banner the day before.

## 4. Check it worked
- Rules page: "Schwab: connected".
- On the chart, the dot next to the timeframe says **Schwab live** (streaming) or **Schwab polling** (REST every 5 s). Both are tradable data. If it says "Delayed, not tradable", Schwab isn't connected.
- `GET /api/data/status` shows the mode, the age of the last message, reconnects and latency.

## What still needs a live session to confirm
These can only be checked with your account during market hours. The desk reports what it actually receives, but nothing here was tested against the real Schwab servers:
- that the streamer login works with your app's products (if it doesn't, the desk keeps using REST polling, still Schwab);
- your real-time entitlement for options and equities (non-professional);
- the real delay of bars and quotes (the chart chip and `/api/data/status` measure it).

Streaming needs the `websockets` package (`pip install websockets==17.3`). Without it the desk uses REST polling.
