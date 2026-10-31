#!/usr/bin/env bash
# deploy/update.sh - update the desk on Chart's computer straight from GitHub (replaces the zip + sha256 relay).
#
#   ~/desk/deploy/update.sh            update to the latest main, if its tests pass
#   ~/desk/deploy/update.sh --check    only show what would change
#   ~/desk/deploy/update.sh --rollback go back to the commit that ran before the last update
#   add --force to run during market hours, or over local edits to tracked files
#
# Safety:
#   * Refuses 09:25-16:05 ET on weekdays (open paper trades are managed by the running server).
#   * Runs the full test suite on the NEW commit in a separate folder first. The live folder is untouched unless
#     the tests pass.
#   * Untracked files are never touched: journal/, schwab.env, webhook.env, DESK_TOKEN.txt, watchdog.sh, bot.py,
#     shadow.py, review.py, variants.py, config/events.json, config/variants.json, config/watchlist.json.
#   * Backs up journal/desk.db with SQLite's backup API (plus an integrity check) before switching.
#   * Never reads, prints or changes secrets.
set -euo pipefail

DESK="${DESK_DIR:-$HOME/desk}"
PY="${PYTHON:-python3}"
BRANCH="${DESK_BRANCH:-main}"
FORCE=0; MODE=update
for a in "$@"; do
  case "$a" in
    --force) FORCE=1 ;;
    --check) MODE=check ;;
    --rollback) MODE=rollback ;;
    *) echo "unknown option: $a"; exit 2 ;;
  esac
done

cd "$DESK"
[ -d .git ] || { echo "STOP: $DESK is not a git checkout yet. Do the one-time setup in deploy/GITHUB_DEPLOY.md."; exit 1; }

say() { printf '%s\n' "$*"; }

market_hours() {
  local dow hm
  dow=$(TZ=America/New_York date +%u); hm=$(TZ=America/New_York date +%H%M)
  [ "$dow" -le 5 ] && [ "$((10#$hm))" -ge 925 ] && [ "$((10#$hm))" -le 1605 ]
}

backup_db() {
  [ -f journal/desk.db ] || { say "no journal/desk.db yet, skipping backup"; return 0; }
  mkdir -p journal/backups
  local out="journal/backups/desk-before-update-$(date +%Y%m%d-%H%M%S).db"
  "$PY" - "$out" <<'EOF'
import sqlite3, sys
s = sqlite3.connect("journal/desk.db"); d = sqlite3.connect(sys.argv[1]); s.backup(d); d.close(); s.close()
r = sqlite3.connect(sys.argv[1]).execute("PRAGMA integrity_check").fetchone()[0]
print("backup", sys.argv[1], "integrity:", r)
sys.exit(0 if r == "ok" else 1)
EOF
}

restart_desk() {
  if command -v systemctl >/dev/null 2>&1 && systemctl --user is-active --quiet deltadesk-web 2>/dev/null; then
    systemctl --user restart deltadesk-web
    say "restarted with systemd (deltadesk-web)"
  elif pgrep -f 'watchdog\.sh' >/dev/null 2>&1; then
    pkill -TERM -f 'server\.py' || true
    say "stopped server.py; watchdog.sh will start the new version"
  else
    say "NOTE: no systemd service or watchdog.sh found. Start the desk the way you normally do."
    return 0
  fi
  for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8765/healthz >/dev/null 2>&1; then
      say "healthz: $(curl -fsS http://127.0.0.1:8765/healthz)"; return 0
    fi
    sleep 2
  done
  say "WARNING: the desk did not answer /healthz within 60 s. Check it, or run: deploy/update.sh --rollback --force"
}

if [ "$FORCE" -eq 0 ] && [ "$MODE" != check ] && market_hours; then
  say "STOP: it's market hours (09:25-16:05 ET). Run this after the close, or add --force."
  exit 1
fi

current=$(git rev-parse HEAD 2>/dev/null || echo none)

if [ "$MODE" = rollback ]; then
  [ -f .deploy_prev ] || { say "STOP: no previous version recorded."; exit 1; }
  prev=$(cat .deploy_prev)
  say "rolling back $current -> $prev"
  backup_db
  git reset -q --hard "$prev"
  echo "$current" > .deploy_prev
  restart_desk
  say "now running $(git log -1 --format='%h %s')"
  exit 0
fi

git fetch -q --depth 50 origin "$BRANCH"
target=$(git rev-parse "origin/$BRANCH")

# local edits to tracked files would be overwritten: show them and stop unless --force
# files that are only missing locally (" D") are simply restored; edited files ("M") need a decision
dirty=$(git status --porcelain --untracked-files=no | grep -v '^ D ' || true)
if [ -n "$dirty" ]; then
  say "Local copies differ from the last deployed version in these tracked files:"
  say "$dirty"
  if [ "$FORCE" -eq 0 ] && [ "$MODE" != check ]; then
    say "STOP: show this list to Nick. Re-run with --force to replace them with the GitHub version."
    exit 1
  fi
fi

missing=$(git status --porcelain --untracked-files=no | grep '^ D ' || true)
[ -n "$missing" ] && say "Files GitHub has that this copy is missing (they will be added):" && say "$missing"
if [ "$current" = "$target" ] && [ -z "$dirty" ] && [ -z "$missing" ]; then
  say "Already up to date: $(git log -1 --format='%h %s')"; exit 0
fi

say "Running now: $( [ "$current" = none ] && echo 'not set' || git log -1 --format='%h %s' "$current")"
say "On GitHub:   $(git log -1 --format='%h %s' "$target")"
if [ "$current" != none ] && git cat-file -e "$current" 2>/dev/null; then
  say "Changes:"; git log --format='  %h %s' "$current..$target" | head -30
fi
[ "$MODE" = check ] && exit 0

tmp=$(mktemp -d)
cleanup() { git worktree remove --force "$tmp" >/dev/null 2>&1 || rm -rf "$tmp"; }
trap cleanup EXIT
git worktree add -q --detach "$tmp" "$target"
say "Testing $(git log -1 --format=%h "$target") in a separate folder..."
set +e
out=$(cd "$tmp" && "$PY" -m pytest -q tests/ 2>&1); rc=$?
set -e
printf '%s\n' "$out" | tail -3
if [ "$rc" -ne 0 ]; then
  say "STOP: the tests failed on the new version. Nothing was changed."; exit 1
fi

backup_db
[ "$current" != none ] && echo "$current" > .deploy_prev
git reset -q --hard "$target"
say "Deployed $(git log -1 --format='%h %s')"
restart_desk
