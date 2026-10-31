# Stable hosting for DeltaDesk (v3.5): the plan, at $0

**What's running today.** DeltaDesk runs on Chart's always-on Linux computer (user `box`, 16 GB RAM). It has three moving parts:
- **The server.** `server.py` binds to 127.0.0.1:8765. It runs the web page plus the engine threads: market data, the Schwab stream, the scanner, the lab and news. The optional Kronos child process runs alongside it.
- **The restarter.** A shell `watchdog.sh` restarts the server when it dies.
- **The link.** A Cloudflare *quick* tunnel publishes the desk. Cloudflare's own docs say quick tunnels are for testing only. They get a new random `trycloudflare.com` address every time, have a 200-request concurrency cap, and come with no uptime guarantee.

**Why the link keeps breaking.** Two separate things cause it:
1. Every restart of the quick tunnel produces a new random link.
2. Anything that kills the process kills the desk until the watchdog notices. The worst offender so far was the Kronos pile-up, fixed in v3.4.1.

**What a stable URL does and doesn't fix.** A stable URL does not keep the engine alive. What keeps it alive is supervision, which is item 1 below. Moving to a free cloud host would not help either:

| Host | Problem |
|---|---|
| Render, Koyeb | Sleep when idle; Render also loses its disk |
| Fly.io, Hugging Face Docker | Trial-only or paid |
| Railway | $1/month of credit |
| Oracle, Google Cloud | Need a card and a migration, and still need a tunnel |

Full comparison with citations: `docs/research/HOSTING.md`.

## The recommendation (all free, no domain to buy)

1. **systemd user services** replace `watchdog.sh`:
   - `deploy/systemd/deltadesk-web.service` restarts the server on a crash with bounded backoff (at most 8 starts in 15 minutes).
   - It also enforces a memory budget that covers Kronos too, and stops the server gracefully.
   - `loginctl enable-linger box` keeps it running without anyone logged in.
2. **A health probe every minute.** `deploy/systemd/deltadesk-healthcheck.{service,timer}` together with `deploy/deltadesk-healthcheck` restart the desk only when a restart can help:
   - the process is dead or hung (`/healthz` stops answering), or
   - the engine heartbeat is stale, or the database is not writable (`/readyz`).
   - A Schwab login that expired is logged, not "fixed" by restart loops.
3. **Tailscale Funnel** gives the desk a **stable** `https://<name>.<tailnet>.ts.net` address on the free Personal plan:
   - Any phone browser can open it, and no domain is needed.
   - TLS ends on the box, so Tailscale's relays can't read the traffic.
   - With `--bg` it comes back by itself after a reboot.
   - **Private alternative:** Tailscale Serve uses the same address, but only devices signed into Nick's Tailscale (the free app on his phone) can open it.

## What this does NOT give you

- **No uptime guarantee.** No free option offers one. If the box loses power or internet, the desk is down.
- **Funnel is public internet.** The machine name is published in certificate-transparency logs, so expect scanners.
- **Funnel adds no login of its own.** The desk's token is the only gate. v3.5 hardens it:
  - The token is swapped for an HttpOnly cookie and dropped from the address bar.
  - Comparisons are constant-time.
  - A client gets a 10-minute pause after 20 wrong tries.
  - Cross-site POSTs are refused.
  - **With no `DESK_TOKEN` set, anything arriving through a tunnel or proxy is refused outright.**
- **Funnel's limits.** Bandwidth limits are not published, and Funnel is labeled beta.

## What would cost money (not needed; flagged PAID)

- A Cloudflare *named* tunnel needs a domain on Cloudflare (PAID). Cloudflare Access (email one-time code login) is free for up to 50 users, but signing up asks for payment details.
- An ngrok free static domain is free but shows a warning page and is capped at 20,000 requests a month. The desk's polling would hit that cap within days, so it is a fallback only.

## Runbook

**[C]** = Chart on the box: shell as `box`. Chart never types, sees or stores Nick's passwords.
**[N]** = Nick himself: browser logins, a sudo password prompt if one appears, the phone.

Do steps 3-5 outside 09:30-16:00 ET (tonight or the weekend).

0. **[C] Inventory (read-only):**

   ```bash
   systemctl --version | head -1
   loginctl show-user box -p Linger
   pgrep -af 'server\.py|watchdog\.sh|cloudflared|kronos'
   crontab -l | grep -nE 'watchdog|server\.py|cloudflared'
   ps -o pid,rss,etime,cmd -p "$(pgrep -d, -f 'server\.py|kronos')"
   readlink -f /proc/$(pgrep -f server.py | head -1)/exe   # the python to use
   curl -s http://127.0.0.1:8765/readyz
   ```

1. **[C]** Enable linger: `loginctl enable-linger box`. If it asks for authentication, **[N]** runs `sudo loginctl enable-linger box`.
2. **[C]** Install the units. This step uses no secrets:

   ```bash
   mkdir -p ~/.config/systemd/user ~/.config/deltadesk ~/.local/bin
   install -m 600 deploy/deltadesk.env.example ~/.config/deltadesk/deltadesk.env   # then copy the existing values from Chart's Secrets into it
   cp deploy/systemd/deltadesk-web.service deploy/systemd/deltadesk-healthcheck.service deploy/systemd/deltadesk-healthcheck.timer ~/.config/systemd/user/
   install -m 700 deploy/deltadesk-healthcheck ~/.local/bin/deltadesk-healthcheck
   # edit ExecStart in deltadesk-web.service if the python path or desk folder differs from step 0
   systemctl --user daemon-reload
   systemd-analyze --user verify ~/.config/systemd/user/deltadesk-*.service ~/.config/systemd/user/deltadesk-*.timer
   ```

3. **[C]** Cut over from the watchdog, after the close:

   ```bash
   crontab -l > ~/crontab.backup.$(date +%F); crontab -l | grep -v 'watchdog\.sh' | crontab -
   pkill -f watchdog.sh; pkill -TERM -f 'server\.py'; sleep 5; pkill -f kronos_shadow
   systemctl --user enable --now deltadesk-web.service deltadesk-healthcheck.timer
   systemctl --user status deltadesk-web --no-pager; curl -s http://127.0.0.1:8765/readyz
   ```

   The v3.5 server refuses to start a second copy from the same folder, so an overlap can never run two engines.

   Crash test: `kill -9 $(systemctl --user show -p MainPID --value deltadesk-web)`. It should come back within about 5 s.

4. **Tailscale.** **[N]** installs it, or **[C]** does if sudo needs no password:
   - Install and start it: `curl -fsSL https://tailscale.com/install.sh | sh`, then `sudo systemctl enable --now tailscaled`.
   - Log in: `sudo tailscale up --hostname=<a neutral name>`. **[N]** opens the printed link and signs in with his own account.
   - Let Chart manage Funnel without sudo: `sudo tailscale set --operator=box`.
   - **[N]** in the Tailscale admin console: turn on MagicDNS and **Enable HTTPS**, then Machines → this box → **Disable key expiry**. Keys otherwise expire after 180 days and the link stops working.
   - **[C]** `tailscale funnel --bg 8765`. If it prints an approval link, **[N]** approves it. Then run `tailscale funnel status`.
   - Private option instead: `tailscale serve --bg 8765`.
5. **[N]** On the phone, with Wi-Fi off, open the `https://….ts.net/?k=<token>` link once. DNS can take up to 10 minutes the first time.
   - The desk swaps the token for a cookie and drops it from the address bar. **Bookmark the page after that.**
   - Then **[C]** retires the quick tunnel: `pkill -f 'cloudflared tunnel --url'`.
   - Reboot test (when Nick approves): after the reboot, `systemctl --user status deltadesk-web` and `tailscale funnel status` should both be active without anyone logging in.

**Rollback:**

```bash
tailscale funnel reset
systemctl --user disable --now deltadesk-healthcheck.timer deltadesk-web.service
crontab ~/crontab.backup.<date>
```

**Never:**
- Commit `deltadesk.env`, the token or the `.ts.net` link to GitHub.
- Paste the token link into a chat.
- Let Chart log in to Tailscale, Schwab or anything else for Nick.

## What restarts preserve

- Positions, orders, ideas, journal, catalysts and the learning tables all live in SQLite (WAL). Every paper fill and exit commits atomically (v3.5).
- A restart re-reads open positions and keeps managing them.
- ORB-retest episodes and contract-lab dedupe are rebuilt from the database, so a restart can't double-enter.
- A signal recovered after a restart can enter research history, but it never becomes a retroactive paper fill. Fills need a fresh quote dated after the signal.
- The 16:10 job makes a consistent backup (SQLite backup API plus an integrity check, 7 kept) in `journal/backups/`.
