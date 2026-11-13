#!/usr/bin/env bash
# deploy/vps_setup.sh - one-time setup of a fresh Ubuntu 24.04 server for the desk (2026-11-13).
#
# Nick runs it once as root on the new InterServer server (1 slice: 1 core, 2 GB, New Jersey):
#   curl -fsSL https://raw.githubusercontent.com/nick-devvv/deltadesk/main/deploy/vps_setup.sh -o vps_setup.sh
#   bash vps_setup.sh 'ssh-ed25519 AAAA... chart-to-deltadesk'      <- Chart's PUBLIC key line
#
# What it does: New York clock, 2 GB swap, packages, user `box` with Chart's public key, the desk from GitHub in
# ~/desk with its own Python environment, the full test suite (in the background), systemd services (installed, NOT started),
# a firewall (SSH + Tailscale only), key-only SSH, and Tailscale (prints one login link for Nick to approve).
#
# It does NOT start the desk. Chart does that after copying journal/ and the desk's settings (deploy/VPS_MOVE.md),
# so two desks never run at once. Safe to run again. Never asks for, reads or prints a secret.
set -euo pipefail

DESK_USER=box
REPO=https://github.com/nick-devvv/deltadesk
TS_NAME=deltadesk-cloud
KEY="${1:-}"

step() { printf '\n== %s\n' "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "STOP: run this as root"; exit 1; }
. /etc/os-release
[ "${ID:-}" = ubuntu ] || echo "warning: this is ${ID:-unknown}, not Ubuntu; continuing"
if [ -n "$KEY" ]; then
  case "$KEY" in
    "ssh-ed25519 "*|"ssh-rsa "*|"ecdsa-sha2-"*) ;;
    *) echo "STOP: the argument must be Chart's PUBLIC key line (starts with ssh-ed25519)"; exit 1 ;;
  esac
fi

step "1/8 clock: New York time"
timedatectl set-timezone America/New_York
date

step "2/8 swap: 2 GB safety margin for the 2 GB server"
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
echo 'vm.swappiness=10' > /etc/sysctl.d/90-deltadesk.conf
sysctl -q -p /etc/sysctl.d/90-deltadesk.conf
free -m

step "3/8 packages (a few minutes)"
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
apt-get update -q
apt-get -y -q -o Dpkg::Options::=--force-confold upgrade
apt-get -y -q install python3-venv python3-pip git sqlite3 curl rsync ufw ca-certificates unattended-upgrades

step "4/8 user $DESK_USER"
id "$DESK_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$DESK_USER"
install -d -m 700 -o "$DESK_USER" -g "$DESK_USER" "/home/$DESK_USER/.ssh"
AK="/home/$DESK_USER/.ssh/authorized_keys"
touch "$AK"
if [ -n "$KEY" ]; then grep -qxF "$KEY" "$AK" || printf '%s\n' "$KEY" >> "$AK"; fi
chown "$DESK_USER:$DESK_USER" "$AK"
chmod 600 "$AK"
echo "authorized keys for $DESK_USER: $(grep -c . "$AK" || true)"
loginctl enable-linger "$DESK_USER"     # the desk keeps running with nobody logged in, and after a reboot

step "5/8 desk code and Python environment"
sudo -u "$DESK_USER" -H bash -s "$REPO" <<'EOF'
set -euo pipefail
cd ~
[ -d desk/.git ] || git clone -q "$1" desk
cd desk
git pull -q --ff-only
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python --version
.venv/bin/python -c "import pandas, numpy, websockets; print('packages ok: pandas', pandas.__version__, 'numpy', numpy.__version__)"
EOF

step "6/8 systemd services (installed, NOT started)"
sudo -u "$DESK_USER" -H bash -s <<'EOF'
set -euo pipefail
cd ~/desk
mkdir -p ~/.config/systemd/user ~/.config/deltadesk ~/.local/bin
cp deploy/systemd/deltadesk-web.service deploy/systemd/deltadesk-healthcheck.service \
   deploy/systemd/deltadesk-healthcheck.timer ~/.config/systemd/user/
install -m 700 deploy/deltadesk-healthcheck ~/.local/bin/deltadesk-healthcheck
# the desk's own Python; memory limits sized for a 2 GB server (the desk uses about 150 MB; Kronos stays off)
sed -i 's#^ExecStart=/usr/bin/python3#ExecStart=%h/desk/.venv/bin/python#; s#^MemoryHigh=2G#MemoryHigh=1200M#; s#^MemoryMax=3G#MemoryMax=1600M#' \
  ~/.config/systemd/user/deltadesk-web.service
if [ ! -f ~/.config/deltadesk/deltadesk.env ]; then (umask 077; echo "PORT=8765" > ~/.config/deltadesk/deltadesk.env); fi
chmod 600 ~/.config/deltadesk/deltadesk.env
EOF
for _ in 1 2 3 4 5 6 7 8 9 10; do systemctl --user -M "$DESK_USER@" daemon-reload 2>/dev/null && break; sleep 1; done
systemctl --user -M "$DESK_USER@" is-enabled deltadesk-web.service 2>/dev/null || echo "deltadesk-web: installed, not enabled yet (Chart enables it at cutover)"

step "7/8 firewall + SSH: only SSH and Tailscale come in; SSH takes keys only"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow OpenSSH >/dev/null
ufw allow in on tailscale0 >/dev/null
ufw allow 41641/udp >/dev/null            # Tailscale direct connections (faster; works without it too)
ufw --force enable >/dev/null
ufw status | head -12
if [ -s "$AK" ]; then
  # 10- sorts before Ubuntu's 50-cloud-init.conf, and sshd keeps the first value it reads
  printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin prohibit-password\n' \
    > /etc/ssh/sshd_config.d/10-deltadesk.conf
  mkdir -p /run/sshd
  sshd -t
  systemctl try-reload-or-restart ssh.service || true   # 24.04 may use ssh.socket: new logins read the file anyway
  echo "SSH: keys only from now on (this window stays open). Nick's way in if ever needed: InterServer's web console."
else
  echo "SSH: no key given, password login left ON. Run this again with Chart's public key to switch to keys only."
fi

step "8/8 Tailscale"
command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sh
if ! tailscale status >/dev/null 2>&1; then
  echo
  echo ">>> NICK: open the https://login.tailscale.com/... link below and click Connect. This waits until you do."
  echo
  tailscale up --hostname="$TS_NAME"
fi
tailscale set --operator="$DESK_USER"
echo "Tailscale name: $(tailscale status --self --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"])' 2>/dev/null || echo "$TS_NAME")"

# the full test suite takes 10+ minutes on 1 core: run it in the background; Chart checks ~/desk-tests.log at cutover
sudo -u "$DESK_USER" -H bash -c 'cd ~/desk && nohup .venv/bin/python -m pytest -q tests/ > ~/desk-tests.log 2>&1 &'
echo "tests: running in the background, results in /home/$DESK_USER/desk-tests.log"

printf '\n== DONE. The server is ready; the desk is NOT running here yet. You can close this window.\n'
printf 'Next: Chart copies the desk over and starts it (deploy/VPS_MOVE.md, Part 2).\n'
