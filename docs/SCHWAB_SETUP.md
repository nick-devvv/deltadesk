# Live data from Schwab (optional, free): Nick does these steps himself

Why: today the desk's option prices are delayed (Alpaca's free feed) and its candles come from Yahoo (free but unofficial).
With Schwab connected, candles, option quotes and greeks are live, so the plan's buy-at-or-under, stop and T1 match what
you see in Legend. The connection is **read-only market data**. The desk's code can't place orders or read your Schwab account.

1. **Schwab account.** Open a Schwab brokerage account at schwab.com if you don't have one (no need to trade in it).
2. **Developer app.** Go to developer.schwab.com, sign up, then "Create App":
   - API product: **Market Data Production** (Schwab may also ask for "Accounts and Trading Production"; it's fine to add it, the desk never uses it).
   - Callback URL: `https://127.0.0.1`
   - Wait until the app status says **Ready For Use** (usually 1 to 3 business days).
3. **Keys into Chart's Secrets.** Copy the app's **App Key** and **Secret** and paste them into Chart's Secrets yourself as
   `SCHWAB_APP_KEY` and `SCHWAB_APP_SECRET`. Then tell Chart: "restart the desk server with the new Schwab secrets".
4. **Connect (1 minute).** On your desk: **Rules → Data sources → Open Schwab login**. Log in on Schwab's site yourself,
   approve, press Done. You land on a page that doesn't load (that's expected). Copy that page's whole address
   (it contains `?code=`) and paste it into the box, then press **Connect** within about 30 seconds.
5. **Every 7 days**, Schwab makes you log in again (their rule). The desk shows a reminder banner the day before; repeat step 4.

Until you connect, everything keeps working on the free sources (Yahoo candles, delayed Alpaca quotes).
