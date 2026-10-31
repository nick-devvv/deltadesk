# Updating the desk from GitHub (replaces zips)

From now on Claude pushes changes to `github.com/nick-devvv/deltadesk` (branch `main`), GitHub runs the tests, and Chart pulls the new version with one command. No zip, no sha256 to paste.

## One-time setup on Chart's computer (after 4:15 PM ET or on the weekend)

Message for Chart:

```
One-time switch: update the desk from GitHub instead of zips. Show me each output.
You never place real trades, never click buy/sell/order buttons, and never enter passwords or keys.
1. Backup:  cd ~ && tar czf ~/desk_backup_pre_git_$(date +%F).tgz --exclude='desk/journal/backups' --exclude='__pycache__' desk && ls -lh ~/desk_backup_pre_git_*.tgz
2. Connect the folder to GitHub (the repo is public, no login needed):
   cd ~/desk && git init -q && git remote add origin https://github.com/nick-devvv/deltadesk.git && git fetch -q --depth 50 origin main && git reset -q origin/main && git checkout origin/main -- deploy/ && git status --short | head -40
   (" M" = your copy differs from GitHub; " D" = a file GitHub has that you don't yet, it gets added; "??" = your own files, never touched)
3. Preview:  ~/desk/deploy/update.sh --check
4. Update:   ~/desk/deploy/update.sh
   If it stops because of "M" files, show me the list and wait for Nick. Nick decides whether to re-run with --force.
5. Show:  curl -s http://127.0.0.1:8765/readyz ; git -C ~/desk log -1 --oneline
```

If step 2 fails because `git` is missing or github.com is unreachable from Chart's computer, stop and tell Nick. The zip route still works as a fallback.

## Every update after that

Message for Chart (after the close):

```
Update the desk: run ~/desk/deploy/update.sh and show me the whole output.
```

What `update.sh` does:
1. Refuses during 09:25–16:05 ET on weekdays unless `--force`.
2. Fetches `main`, lists the new commits, and stops if any tracked file was edited locally.
3. Runs the full test suite on the new version **in a separate folder**. If a test fails, nothing changes.
4. Backs up `journal/desk.db` (SQLite backup API plus an integrity check).
5. Switches the files and restarts the desk: systemd if `deltadesk-web` is active, otherwise it stops `server.py` and `watchdog.sh` restarts it.
6. Checks `/healthz`.

Untracked files are never touched: `journal/`, `schwab.env`, `webhook.env`, `DESK_TOKEN.txt`, `watchdog.sh`, `bot.py`, `shadow.py`, `review.py`, `variants.py`, `config/events.json`, `config/variants.json`, `config/watchlist.json`.

**Undo the last update:** `~/desk/deploy/update.sh --rollback` (add `--force` during market hours).
