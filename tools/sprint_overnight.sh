#!/usr/bin/env bash
# tools/sprint_overnight.sh - rounds 9 and 10 on Chart's computer in one unattended run (research only).
#
# Run from the sprint checkout (~/sprint) on branch sprint/round10, which holds all of round 9's code too:
#   nohup bash tools/sprint_overnight.sh >> data/sprint/logs/overnight.out 2>&1 &
# Progress:  tail -20 data/sprint/logs/overnight.log
#
# Order (each stage resumable; a finished stage writes data/sprint/overnight/<stage>.done and is skipped on a re-run):
#   1. pull9      round 9's data pull (tools/sprint_pull9.py)                       about 7-11 h, network
#   2. r9         round 9's analysis (tools/sprint_round9.py) + ~/sprint_results9.zip  about 1-2.5 h, started in the
#                 background as soon as pull9 is done, so it runs while round 10 downloads
#   3. etf_hist   DIA/XLK/XLF/SMH 1-minute stock bars 2015-11..2024-01 (tools/sprint_pull.py --period HIST)
#      etf_dev    the same 2024-08..2026-06 (--stock-bars-only)                      10-25 min together
#   4. pull10     round 10's option pull (tools/sprint_pull10.py --div-scope rebalance)  about 7-9 h, network
#   5. r10_noise, r10_credit, r10_grid, r10_swing   round 10's four tools              about 1.5-3 h
#   6. zip10      ~/sprint_results10.zip
# Network stages are retried (the pulls resume where they stopped) after a 5-minute wait; a stage that exits 2 (a locked
# period was asked for) or 3 (a missing key or setting) is never retried and stops the run. An analysis stage gets one
# crash re-run; if it still fails, the other analyses still run and the summary says which failed.
#
# Safety: market data only (data.alpaca.markets, and SEC EDGAR for round 9's 8-K headers); no orders, no account, no
# positions; never touches ~/desk; never passes --locked or --frozen; never prints a key.
# Environment for tests: PY (python, default .venv/bin/python), WAIT (seconds between tries, default 300), HOME_ZIP (where
# the zips go, default $HOME).
set -u
cd "$(dirname "$0")/.." || exit 3
ROOT_DIR="$(pwd -P)"
case "$ROOT_DIR" in
  "$HOME/desk"|"$HOME/desk/"*) echo "REFUSED: this script never runs inside ~/desk"; exit 3 ;;
esac
PY="${PY:-.venv/bin/python}"
WAIT="${WAIT:-300}"
HOME_ZIP="${HOME_ZIP:-$HOME}"
L=data/sprint/logs
M=data/sprint/overnight
mkdir -p "$L" "$M"

say() { echo "[$(date '+%F %T')] $*" | tee -a "$L/overnight.log"; }

# stage NAME TRIES LOGFILE COMMAND...: run until it exits 0 (then mark it done), at most TRIES times; exit codes 2 and 3
# are final (returned at once). Returns 0 when done, else the last exit code.
stage() {
  local name=$1 tries=$2 log=$3 rc=1 i
  shift 3
  if [ -f "$M/$name.done" ]; then say "$name: done before, skipped"; return 0; fi
  for i in $(seq 1 "$tries"); do
    say "$name: try $i of $tries (log $log)"
    "$@" >> "$log" 2>&1
    rc=$?
    if [ "$rc" -eq 0 ]; then
      date '+%F %T' > "$M/$name.done"
      say "$name: done"
      return 0
    fi
    if [ "$rc" -eq 2 ] || [ "$rc" -eq 3 ]; then
      say "$name: stopped with exit $rc (not retried: a locked period or a missing key/setting); last lines:"
      tail -5 "$log" | sed 's/^/    /' | tee -a "$L/overnight.log"
      return "$rc"
    fi
    if [ "$i" -lt "$tries" ]; then
      say "$name: exit $rc; waiting $WAIT s before the next try (pulls resume where they stopped)"
      sleep "$WAIT"
    fi
  done
  say "$name: FAILED after $tries tries (exit $rc); last lines:"
  tail -5 "$log" | sed 's/^/    /' | tee -a "$L/overnight.log"
  return "$rc"
}

latest() { ls -t $1 2>/dev/null | head -1; }

zip9() {
  local D
  D=$(latest 'data/sprint/round9_*.md' | sed 's/.*round9_\(.*\)\.md/\1/')
  [ -n "$D" ] || return 1
  local files="data/sprint/round9_$D.md data/sprint/round9_$D.json data/alpaca/universe/ustk.json"
  local f
  for f in F Fopt G1 G2 G2pool H I E; do
    [ -f "data/sprint/trades_round9_${f}_$D.csv.gz" ] && files="$files data/sprint/trades_round9_${f}_$D.csv.gz"
  done
  # shellcheck disable=SC2086
  "$PY" -m zipfile -c "$HOME_ZIP/sprint_results9.zip" $files $L/run9_*.log
}

zip10() {
  local files="" p
  for p in r10noise r10credit r10grid r10swing; do
    [ -n "$(latest "data/sprint/${p}_*.md")" ] && files="$files $(latest "data/sprint/${p}_*.md") $(latest "data/sprint/${p}_*.json")"
  done
  for p in 'trades_r10credit_*.csv.gz' 'trades_r10noise_fixes_*.csv.gz' 'r10_div_*.csv.gz'; do
    [ -n "$(latest "data/sprint/$p")" ] && files="$files $(latest "data/sprint/$p")"
  done
  for p in V1 V2 V2s V3 V3opt V3pool V4 V4opt; do
    [ -n "$(latest "data/sprint/trades_r10swing_${p}_*.csv.gz")" ] && files="$files $(latest "data/sprint/trades_r10swing_${p}_*.csv.gz")"
  done
  [ -n "$files" ] || return 1
  # shellcheck disable=SC2086
  "$PY" -m zipfile -c "$HOME_ZIP/sprint_results10.zip" $files $L/run10_*.log
}

say "overnight: start in $ROOT_DIR ($(git log -1 --oneline 2>/dev/null)); research only, market data only"
status=""

# 1. round 9's pull (network; resumable)
stage pull9 8 "$L/run9_pull.log" "$PY" tools/sprint_pull9.py
rc=$?
if [ "$rc" -ne 0 ]; then say "overnight: STOPPED (round 9's pull did not finish; rounds 9 and 10 need it). Show Nick this log."; exit "$rc"; fi

# 2. round 9's analysis in the background (CPU), while round 10 downloads
(
  stage r9 2 "$L/run9_round9.log" "$PY" tools/sprint_round9.py && stage zip9 1 "$L/run9_zip.log" zip9
) &
R9=$!

# 3-4. round 10's data (network; resumable)
stage etf_hist 5 "$L/run10_etf_hist.log" "$PY" tools/sprint_pull.py --period HIST --symbols DIA,XLK,XLF,SMH || status="$status etf_hist"
stage etf_dev 5 "$L/run10_etf_dev.log" "$PY" tools/sprint_pull.py --symbols DIA,XLK,XLF,SMH --from 2024-08-01 --to 2026-06-30 --stock-bars-only || status="$status etf_dev"
stage pull10 8 "$L/run10_pull.log" "$PY" tools/sprint_pull10.py --div-scope rebalance
rc=$?
wait "$R9"
r9rc=$?
[ "$r9rc" -eq 0 ] || status="$status r9"
if [ "$rc" -ne 0 ]; then
  say "overnight: STOPPED before round 10's analysis (round 10's pull did not finish). Round 9: $([ "$r9rc" -eq 0 ] && echo done || echo FAILED). Show Nick this log."
  exit "$rc"
fi

# 5. round 10's analysis (CPU)
stage r10_noise 2 "$L/run10_noise.log" "$PY" tools/sprint_r10_noise.py || status="$status r10_noise"
stage r10_credit 2 "$L/run10_credit.log" "$PY" tools/sprint_r10_credit.py || status="$status r10_credit"
stage r10_grid 2 "$L/run10_grid.log" "$PY" tools/sprint_r10_grid.py || status="$status r10_grid"
stage r10_swing 2 "$L/run10_swing.log" "$PY" tools/sprint_r10_swing.py || status="$status r10_swing"

# 6. the zip
stage zip10 1 "$L/run10_zip.log" zip10 || status="$status zip10"

if [ -z "$status" ]; then
  say "overnight: ALL DONE. Send Nick ~/sprint_results9.zip and ~/sprint_results10.zip."
else
  say "overnight: finished with failures:$status. Send Nick this log and whatever zips exist."
fi
exit 0
