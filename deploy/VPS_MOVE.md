# Moving the desk to the InterServer server (2026-11-13)

**Why:** Chart's computer sleeps whenever Chart is idle (it slept through most of Nov 11-12), so the desk missed the market. The new server never sleeps.

**Server:** InterServer, 1 slice (1 core, 2 GB, 40 GB SSD), New Jersey, Ubuntu 24.04, $3/month, Nick's account. Tailscale name `deltadesk-cloud`, then `nicks-desk` after the cutover. User `box`, desk in `~/desk`, same layout as Chart's computer.

**Who does what:** **[N]** = Nick, **[C]** = Chart. Chart never sees a password. Nick never pastes a secret into chat.

**Never:** commit or print `deltadesk.env`, the desk token, the Telegram or Schwab tokens. Never run two desks at once: two engines double paper trades and alerts and fight over the Telegram bot.

## Part 1: set up the server

1. **[C]** Make a key for the server and send Nick the PUBLIC line only:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/deltadesk_vps -N "" -C chart-to-deltadesk
   cat ~/.ssh/deltadesk_vps.pub
   ```
2. **[N]** In the Mac Terminal: `ssh root@<server IP>`, type the root password, then:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/nick-devvv/deltadesk/main/deploy/vps_setup.sh -o vps_setup.sh
   bash vps_setup.sh 'ssh-ed25519 AAAA... chart-to-deltadesk'
   ```
   It takes about 5-10 minutes. It installs everything and starts the test suite in the background, but does **not** start the desk. Near the end it prints a `login.tailscale.com` link: open it and click **Connect**. If the window closes midway, log in again and run the same `bash` line; it is safe to repeat.
3. **[N]** In the Tailscale admin, on `deltadesk-cloud`: **…** → **Disable key expiry**.

## Part 2: cut over (Chart; outside 09:25-16:05 ET)

1. **Settings file, from the desk that's running now** (values never printed):
   ```bash
   P=$(pgrep -f 'server\.py' | head -1)
   tr '\0' '\n' < /proc/$P/environ | grep -E '^(PORT|DESK_TOKEN|SCHWAB_APP_KEY|SCHWAB_APP_SECRET|SCHWAB_CALLBACK|ALPACA_KEY|ALPACA_SECRET|SEC_USER_AGENT|NTFY_TOPIC|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID|CHAT_WEBHOOK|CHAT_WEBHOOK_KEY|XAI_API_KEY|QUIVER_KEY|KILLFILE_OFF)=' > ~/deltadesk.env.move
   chmod 600 ~/deltadesk.env.move; cut -d= -f1 ~/deltadesk.env.move      # names only
   ```
   Leave `KRONOS` out: it stays off on the 2 GB server. If `CHAT_WEBHOOK` points at `127.0.0.1` on your computer, the server can't reach it: point it at your Tailscale name, or tell Nick.
2. **Stop the old desk for good:**
   - Back up `watchdog.sh`, then remove its server.py start, health check and funnel lines. Keep its Tailscale lines.
   - `pkill -TERM -f 'server\.py'`. Then `pgrep -f server.py` must print nothing.
   - `tailscale funnel reset`.
3. **Copy the desk's private files** (the old desk is stopped, so the database is quiet):
   ```bash
   S="ssh -i ~/.ssh/deltadesk_vps -o StrictHostKeyChecking=accept-new"
   cd ~/desk && git status --porcelain --ignored          # what git doesn't track
   rsync -a -e "$S" journal schwab.env webhook.env DESK_TOKEN.txt bot.py shadow.py review.py variants.py \
     config/events.json config/variants.json config/watchlist.json box@deltadesk-cloud:desk/ --relative
   rsync -a -e "$S" ~/deltadesk.env.move box@deltadesk-cloud:.config/deltadesk/deltadesk.env
   rm ~/deltadesk.env.move
   ```
   If `deltadesk-cloud` doesn't resolve, use its address from `tailscale ip -4 deltadesk-cloud`. Add any other untracked desk file from the `git status` list. Skip `.venv/`, caches and old backup folders. Files missing on your side are fine to skip.
4. **Start it on the server:**
   ```bash
   $S box@deltadesk-cloud
   tail -2 ~/desk-tests.log                                         # must say passed, with no failures
   chmod 600 ~/.config/deltadesk/deltadesk.env
   sqlite3 ~/desk/journal/desk.db 'PRAGMA integrity_check'          # must print ok
   systemctl --user enable --now deltadesk-web.service deltadesk-healthcheck.timer
   sleep 20; curl -s http://127.0.0.1:8765/healthz; curl -s http://127.0.0.1:8765/readyz
   ```
5. **Keep Nick's bookmark** (same address):
   - On your computer: `tailscale set --hostname=chart-box`. On the server: `tailscale set --hostname=nicks-desk`.
   - Check with `tailscale status`. If the names didn't change (they were renamed by hand in the admin), Nick renames them in the Tailscale admin: Chart's computer → `chart-box`, then `deltadesk-cloud` → `nicks-desk`.
   - On the server: `tailscale funnel --bg 8765`, then `tailscale funnel status`. It must show `https://nicks-desk.tail5aa056.ts.net`.
6. **Checks; report each to Nick:**
   - The desk link opens on his phone and laptop.
   - Telegram `/status` gets a reply.
   - `free -m` shows memory left over, and `systemctl --user status deltadesk-web` says active.
   - Freeze test: `kill -STOP $(systemctl --user show -p MainPID --value deltadesk-web)`. The health timer restarts it in about 3-4 minutes.

## After the move

- **Updates** (after 4:15 PM ET): `ssh -i ~/.ssh/deltadesk_vps box@nicks-desk desk/deploy/update.sh`.
- **Logs:** `journalctl --user -u deltadesk-web -n 200`.
- **Schwab login when it's due:** the same Connect Schwab steps on the desk page as before.
- **Reboot:** Nick reboots from InterServer's panel (VPS → the server → Reboot). The desk, health timer and funnel come back by themselves.
- **Rollback:** on the server, `systemctl --user disable --now deltadesk-web deltadesk-healthcheck.timer` and `tailscale funnel reset`. Restore Chart's `watchdog.sh` backup and start it.
- **Forward test:** count forward-test trades from the move date. Days Chart's computer slept have gaps; none were faked, because fills need a live quote.
