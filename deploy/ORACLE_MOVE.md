# Moving the desk to an Oracle Cloud "Always Free" server (2026-11-13)

**Why:** Chart's computer sleeps whenever Chart is idle. On Nov 11 and 12 it slept through about 380 of 390 market minutes, so the desk wasn't watching the market, paper trading or sending alerts. There is no setting to keep it awake. An Oracle Always Free server (Ampere A1, 2 OCPUs, 12 GB) never sleeps, costs $0 inside the free limits, and has normal internet, so Tailscale Funnel and the Schwab stream stay up.

**Who does what:**
- **[N]** = Nick. He does every sign-up, login, approval and payment-card step. Chart never sees his passwords.
- **[C]** = Chart.
- Chart stays the operator. It reaches the server over Tailscale, runs updates there and keeps its own computer only as a workstation.

**Never:** commit or print `deltadesk.env`, the desk token, the Telegram token, the Tailscale auth key or Schwab tokens. Never run two desks at once; two engines would double paper trades, double alerts and fight over the Telegram bot.

## Part 1: create the server

1. **[C]** Make an SSH key for the server and send Nick the PUBLIC half only, the one line starting `ssh-ed25519`:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/deltadesk_oracle -N "" -C chart-to-deltadesk
   cat ~/.ssh/deltadesk_oracle.pub
   ```
2. **[N]** Sign up at oracle.com/cloud/free → **Start for free**.
   - Account type: Individual.
   - Home region: a US region (e.g. US East Ashburn or US West Phoenix). The home region can't be changed later.
   - The card is for identity checks only.
3. **[N]** Make a one-time Tailscale key at login.tailscale.com/admin/settings/keys → **Generate auth key**: not reusable, expires in 1 day. Copy it (starts `tskey-auth-`).
4. **[N]** In Oracle: **Compute → Instances → Create instance**.
   - **Name:** `deltadesk`.
   - **Image:** Canonical Ubuntu 24.04.
   - **Shape:** **Ampere → VM.Standard.A1.Flex**, **2 OCPUs, 12 GB**. It must show "Always Free-eligible".
   - **Networking:** keep the defaults, with a public IPv4 address assigned.
   - **SSH keys:** **Paste public keys** → paste Chart's line from step 1.
   - **Advanced options → Management → cloud-init script**: paste the 3 lines below, with the key from step 3:
     ```bash
     #!/bin/bash
     curl -fsSL https://tailscale.com/install.sh | sh
     tailscale up --hostname=deltadesk-cloud --authkey=PASTE_TSKEY_HERE
     ```
   - **Create.** If it says **out of capacity**, pick another availability domain in Placement, or retry in an hour.
5. **[N]** In the Tailscale admin, the new machine `deltadesk-cloud` appears within a few minutes. Open **…** → **Disable key expiry**. Tell Chart it's there.
6. **[N] Optional, recommended:** Oracle can reclaim a free server it considers idle for 7 days. Upgrading the account to **Pay As You Go** (Billing → Upgrade) avoids that, and you still pay $0 inside the free limits. Then set a **$1 budget alert** (Billing → Budgets) so any charge is flagged at once.

## Part 2: set up the desk on the server (Chart, over Tailscale)

```bash
ssh -i ~/.ssh/deltadesk_oracle ubuntu@deltadesk-cloud 'uname -m; nproc; free -g'      # aarch64, 2, ~11
ssh -i ~/.ssh/deltadesk_oracle ubuntu@deltadesk-cloud
sudo apt-get update && sudo apt-get -y upgrade
sudo apt-get -y install python3-venv python3-pip git sqlite3 curl
git clone https://github.com/nick-devvv/deltadesk ~/desk
python3 -m venv ~/desk/.venv && ~/desk/.venv/bin/pip install -r ~/desk/requirements.txt
cd ~/desk && .venv/bin/python -m pytest -q tests/                   # must pass before going on
sudo tailscale set --operator=ubuntu
mkdir -p ~/.config/systemd/user ~/.config/deltadesk ~/.local/bin
cp deploy/systemd/deltadesk-web.service deploy/systemd/deltadesk-healthcheck.service deploy/systemd/deltadesk-healthcheck.timer ~/.config/systemd/user/
install -m 700 deploy/deltadesk-healthcheck ~/.local/bin/deltadesk-healthcheck
sed -i 's#^ExecStart=/usr/bin/python3#ExecStart=%h/desk/.venv/bin/python#; s#^MemoryHigh=2G#MemoryHigh=6G#; s#^MemoryMax=3G#MemoryMax=8G#' ~/.config/systemd/user/deltadesk-web.service
sudo loginctl enable-linger ubuntu
systemctl --user daemon-reload
systemd-analyze --user verify ~/.config/systemd/user/deltadesk-*
```

**Environment:** write `~/.config/deltadesk/deltadesk.env` (chmod 600) with every variable `watchdog.sh` exports for the desk today:
- `NTFY_TOPIC`, `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
- the Schwab and webhook settings, `KRONOS` and anything else the desk reads
- `DESK_TOKEN`, if it is set by environment rather than `DESK_TOKEN.txt`

Check with `grep -c = ~/.config/deltadesk/deltadesk.env` (a count only, never the values).

## Part 3: cut over (outside 09:25-16:05 ET; tell Nick first)

1. **[C] Stop the old desk for good on Chart's computer.**
   - Back up `watchdog.sh`.
   - Remove its server.py start, health check and funnel lines. Keep its Tailscale lines, so Chart's computer stays on the tailnet to reach the server.
   - Then `pkill -TERM -f 'server\.py'`. Confirm `pgrep -f server.py` prints nothing.
   - Run `tailscale funnel reset`, so the old computer stops publishing anything.
2. **[C] Copy the desk's private files**, with the old desk stopped so the database is quiet:
   - List what git doesn't track: `cd ~/desk && git status --porcelain --ignored`.
   - Copy every desk file in that list, with `rsync -a <files> ubuntu@deltadesk-cloud:~/desk/`. That includes `journal/` (the database, WAL and backups), `schwab.env`, `webhook.env`, `DESK_TOKEN.txt`, `config/events.json`, `config/variants.json`, `config/watchlist.json`, `bot.py`, `shadow.py`, `review.py`, `variants.py` and any Schwab token file.
   - Skip `.venv/`, caches, `/tmp` backups and old `desk_backup_*` folders.
   - On the server, run `sqlite3 journal/desk.db 'PRAGMA integrity_check'`. It must print `ok`.
3. **[C] Start the new desk:**
   ```bash
   systemctl --user enable --now deltadesk-web.service deltadesk-healthcheck.timer
   curl -s http://127.0.0.1:8765/healthz; curl -s http://127.0.0.1:8765/readyz
   tr '\0' '\n' < /proc/$(systemctl --user show -p MainPID --value deltadesk-web)/environ | grep -c -E '^(NTFY_TOPIC|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)='   # 3
   ```
4. **Keep Nick's bookmark working** (same address, so he stays logged in):
   - **[N]** In the Tailscale admin: rename Chart's computer from `nicks-desk` to `chart-box`, then rename `deltadesk-cloud` to `nicks-desk`.
   - **[C]** On the server, run `tailscale funnel --bg 8765`, then `tailscale funnel status`. The address must be `https://nicks-desk.tail5aa056.ts.net`.
5. **[C] Checks; report each result to Nick:**
   - **Address:** the `ts.net` address opens the desk from outside, and `/healthz` answers.
   - **Alerts:** a Telegram `/status` gets a reply, and an ntfy test arrives.
   - **Reboot test:** `sudo reboot`. Within about 3 minutes the desk, the funnel and the health timer are back with nobody logged in.
   - **Freeze test:** `kill -STOP <MainPID>`. The health timer restarts it in about 3-4 minutes.
6. **[C] Schwab:** the copied tokens keep working until their normal expiry. When the Schwab login is due again, do it exactly as before, but on the server.

## After the move

- **Updates:** Chart runs `ssh -i ~/.ssh/deltadesk_oracle ubuntu@nicks-desk ~/desk/deploy/update.sh` after 4:15 PM ET. update.sh restarts the desk through systemd.
- **Logs:** `journalctl --user -u deltadesk-web -n 200`. Health: `systemctl --user status deltadesk-web`.
- **Rollback:** on the server, `systemctl --user disable --now deltadesk-web deltadesk-healthcheck.timer` and `tailscale funnel reset`. Then restore Chart's `watchdog.sh` backup and start it.
- **Forward-test caveat:** paper results before the move have gaps on days Chart's computer slept (Nov 3-5 afternoons, most of Nov 11-12). Those trades didn't happen; none were faked, because fills need a live quote. Count forward-test trades from the move date.
