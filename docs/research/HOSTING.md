# DeltaDesk hosting: zero-cost, stable-URL options (researched 2026-10-31)

All facts below come from official docs and pricing pages fetched on 2026-10-31. Citations are numbered `[n]` and listed at the end. Anything I could not confirm in an official source is marked **unverified**. No prices or limits were invented, and nothing was signed up for.

---

## Recommendation (short version)

**Keep the always-on box. Replace `watchdog.sh` with systemd user services. Replace the Cloudflare quick tunnel with Tailscale (free Personal plan).**

- **Tailscale Funnel** gives a stable public HTTPS URL, `https://<machine>.<tailnet>.ts.net`, at no cost and without buying a domain. Any phone browser can open it without installing Tailscale [14][15][16].
- **Tailscale Serve** uses the same URL but is reachable only from devices signed into your tailnet. That means installing the free Tailscale app on the phone. It is the more private choice [17].
- Nothing in this setup costs money. A Cloudflare *named* tunnel needs a domain on Cloudflare, and a domain costs money. **That route is PAID** [2][7].
- Limits stated plainly:
  - No free option has an uptime SLA.
  - Funnel is in beta and has bandwidth limits that Tailscale does not publish [15].
  - The box itself (power, ISP, hardware) stays a single point of failure.
  - What this setup does fix: the URL changing, and crashes or reboots killing everything.

---

## 0. Situation and constraints

| Item | Value |
|---|---|
| App | `server.py`, a Python `ThreadingHTTPServer` on **127.0.0.1:8765**. Threads: market-data engine, Schwab websocket, scanner, strategy lab, news poller. Storage: SQLite `journal/desk.db` (WAL). |
| Optional child | Kronos, about 370 MB |
| Host | Always-on Linux box. User `box`, home `/home/box`, 16 GB RAM, about 13 GB in use (about 3 GB headroom). |
| Today | Cloudflare **quick** tunnel (random `*.trycloudflare.com`), token in the URL, `watchdog.sh` |
| Needs | One stable HTTPS URL for the owner's phone browser. Engine running 09:30–16:00 ET plus overnight. **$0.** |

Why the current setup breaks: Cloudflare says quick tunnels are "intended for testing and development only". They get a random `trycloudflare.com` subdomain each time, are capped at 200 in-flight requests (excess gets HTTP 429), do not support Server-Sent Events, and come with no SLA or uptime guarantee [1].

---

## 1. Comparison (checked against current official docs)

### 1a. Tunnels that keep DeltaDesk on the existing box

| | Cloudflare named tunnel + Access | Tailscale Funnel | Tailscale Serve | ngrok Free |
|---|---|---|---|---|
| **Cost** | The tunnel itself costs nothing ("at no cost", 2021 announcement) [4]. Zero Trust Free plan is $0 for up to 50 users [8]. **The domain is PAID**: Registrar sells at cost with "no markup", and gives no free domains [7]. Price depends on the TLD and is not quoted here. | $0 on the Personal plan: "Free forever", non-commercial use, up to 6 users, unlimited user devices [14]. Funnel is "available for all plans" [15]. | $0, same plan [14] | $0 [27] |
| **Card / domain needed** | **A domain on Cloudflare is required to publish an app** [2][3]. Free and Pro plans support only full setup (Cloudflare nameservers); CNAME/partial setup is Business/Enterprise only [5][6]. Zero Trust onboarding asks for payment details even on the Free plan ("you will not be charged") [9]. | No domain: uses `<machine>.<tailnet>.ts.net` [15]. No card stated on the pricing page [14] (card requirement **unverified**). | Same as Funnel | No card for HTTP/S endpoints; card needed only for TCP endpoints [27]. No domain: 1 assigned dev domain [26]. |
| **Stable URL?** | Yes. You choose the hostname on your own domain [3]. | Yes, as long as the machine name and tailnet DNS name stay the same. Renaming the tailnet "may break existing links" [19]. With `--bg`, Funnel "automatically resumes" after a reboot or a `tailscale down`/`up` [16]. | Same as Funnel. `--bg` persists across reboots [18]. | Yes. The dev domain "doesn't change when you restart the agent" [26]. |
| **Reachable from any browser without installing anything?** | Yes (public hostname) [3] | **Yes**. Visitors don't need Tailscale [15]. | **No**. Serve is "available only within the tailnet" [17], so the phone needs the Tailscale app. | Yes, but a free-tier **interstitial warning page** is shown to browsers. Clicking through sets a 7-day cookie [26]. |
| **Exposure** | Public. Access can enforce login before traffic reaches the box [10]. | **Public internet.** Hostnames also appear in public Certificate Transparency logs when HTTPS is enabled [20]. | Private to the tailnet; ACLs apply [17] | Public [26] |
| **Limits** | Free Zero Trust: 50 users, 24 h log retention [8]. WebSocket idle timeout exists; the length is not published [12]. | Ports **443, 8443, 10000** only. "Non-configurable bandwidth limits" with **no published numbers** [15][16]. Beta [15]. Let's Encrypt rate limits if certs are re-requested often [15]. | Same certificate and port behavior on the tailnet side; no Funnel bandwidth cap stated [17] | 1 GB/month data out, **20,000 HTTP requests/month**, 4,000 req/min, 3 endpoints, 1 user [26]. What happens on overage is **unverified** [27]. |
| **WebSockets** | "Supported on all Cloudflare plans" [12] | Not mentioned in the docs (**unverified**; test it) | Not mentioned (**unverified**) | "HTTP endpoints support WebSockets without any special configuration" [28] |
| **Auth options** | Access with email **one-time PIN** (no IdP needed) [10], the Cloudflare IdP, generic OIDC/SAML, GitHub, and others [11] | **None from Tailscale**. "Funnel traffic … does not include identity headers" [17]. The app's own token/cookie is the only gate. | Tailnet membership plus ACLs. Identity headers (`Tailscale-User-Login`, etc.) are added for tailnet traffic [17]. | Traffic Identities (OAuth/OIDC) limited to 3 MAU/month on Free [26]. Basic auth not listed (**unverified**). |
| **Privacy** | TLS ends at Cloudflare's edge, so Cloudflare can see the traffic. This is inferred from how Access inspects requests, not stated in the docs fetched. | Relays "cannot decrypt". TLS ends on the box [15]. | TLS ends on the box (Serve terminates HTTPS on the device's daemon) [18] | Free plan offers HTTPS endpoints with ngrok-managed certs; raw TLS pass-through is paid [26]. So ngrok's edge terminates TLS (inference). |
| **Maintenance** | Low once set up: `sudo cloudflared service install <TUNNEL_TOKEN>` [2]. Domain renewal every year (paid). | Low. tailscaled is a system service. **Turn off key expiry**: the default is 180 days, after which connections "stop working" [21]. | Low (same as Funnel) | Low: `ngrok service install` creates a systemd unit [29]. Watch the monthly quotas. |

### 1b. Moving DeltaDesk to a free cloud host instead

| | Cost / card | Sleep or idle | Persistent storage | Background workers | WebSockets | Auth | Maintenance / fit for DeltaDesk |
|---|---|---|---|---|---|---|---|
| **Oracle Cloud Always Free** | $0 within limits. **Credit/debit card required** for identity verification; authorization holds "do not result in actual charges" [31]. | **Idle reclamation**: an instance counts as idle if over 7 days the 95th-percentile CPU is below 20%, network is below 20%, and memory is below 20% (memory test applies to A1 only) [30]. Accounts idle 30+ days "may be deemed abandoned" [31]. | 200 GB block storage total (boot plus block) [30] | Yes (full VM) | Yes (full VM; your own stack) | Bring your own | A1 Flex is now **2 OCPUs / 12 GB total** (1,500 OCPU-h and 9,000 GB-h per month). Micro shape: 2 × E2.1.Micro with 1 GB each [30]. Home region only, and "out of host capacity" errors happen [30]. Still needs a tunnel or domain for HTTPS. High burden: OS patching, migrating Schwab tokens and SQLite. |
| **Google Cloud e2-micro** | $0 within limits. "A billing account is required"; Free Trial signup needs a card or other payment method [32]. | No sleep. Limits are by hours per month [32]. | 30 GB-months standard PD [32] | Yes (full VM) | Yes | Bring your own | Only us-west1, us-central1, us-east1. **1 GB/month egress** [32]. e2-micro RAM (commonly 1 GB) is **unverified**: the official machine-type table didn't load. Too small for engine plus Kronos. Google can change limits with 30 days' notice [32]. |
| **Render Free** | $0. Card not stated as required [33]. | **Spins down after 15 min** with no inbound traffic; about 1 min to spin up. 750 instance-hours/month. Render "may restart Free web services at any time" [33]. | **None**: ephemeral filesystem, no persistent disks [33] | **No**: "Other service types don't support Free instances" [33] | Yes (a new WebSocket connection wakes it) [33] | Bring your own | Unsuitable: the engine would stop, and SQLite would be lost on every spin-down. |
| **Railway Free** | $1/month free credit after a one-time $5 trial (30 days) [34][35]. Card requirement **unverified**. | Not stated (**unverified**) | 0.5 GB volume per service. Volumes are deleted 30 days after the plan expires [34]. | **Unverified** | **Unverified** | Bring your own | 0.5 GB RAM per service on Free [34]. $1 of credit is very unlikely to cover an always-on process (pricing math not verified). Unsuitable. |
| **Fly.io** | **No free plan for new customers.** Trial is 2 VM-hours or 7 days, whichever comes first, and trial machines stop after 5 min. After that a card is needed and billing starts [36][38]. Smallest machine $1.94/month, volumes $0.15/GB-month [37]. | Trial machines auto-stop after 5 min [36] | Volumes are paid [37] | Paid | **Unverified** | Bring your own | **PAID.** Not an option. |
| **Koyeb** | 1 free web service: 512 MB RAM, 0.1 vCPU, 2 GB SSD, Frankfurt or Washington DC [39]. A card is "generally required" with a $29 pre-authorization hold [39]. | **Scales to zero after 1 h** with no traffic. This can't be disabled on Free. An open WebSocket from the internet holds it up [40]. | Volumes on Free not mentioned (**unverified**). The Pricing page lists NVMe volumes under Pro [41]. | Only web services are described as free [39] | Yes (counts as activity) [40] | Bring your own | 0.1 vCPU / 512 MB is far too small. Unsuitable. |
| **Hugging Face Spaces** | **Docker/Gradio Spaces "require a paid plan to create" (PRO)**. Free personal accounts get only static Spaces or up to 2 ZeroGPU Gradio Spaces [42]. | Free `cpu-basic` sleeps or pauses after **48 h** of inactivity, and this is not configurable [43][45]. | Disk is "ephemeral"; persistence requires attached Storage Buckets [44]. Bucket pricing **unverified**. | No explicit rule; "upgrade to paid hardware" to run indefinitely [42] | **Unverified**. Outbound traffic is limited to ports 80, 443 and 8080 [42]. | Private Spaces are owner-only [42] | **PAID** for Docker. Unsuitable. |

**Conclusion for 1b:** no free cloud host matches what the box already does (about 2–3 GB+ RAM, always-on threads, a persistent SQLite DB, an outbound Schwab stream). The two "real VM" options (Oracle, GCP) need a card, still need their own HTTPS URL, and add migration and OS-maintenance work. Oracle also carries idle-reclamation and capacity risk.

---

## 2. Process supervision on the existing box (systemd user services)

### Why user services, and the facts the design relies on

- **Linger.** `loginctl enable-linger` means "a user manager is spawned for the user at boot and kept around after logouts. This allows users who are not logged in to run long-running services" [51]. Upstream polkit allows `set-self-linger` for the user themself (`allow_any=yes`) [53], so `loginctl enable-linger box` normally needs no sudo. A distro may override this; if it asks for authentication, the user runs it with sudo.
- **`Restart=on-failure`.** This restarts on a non-zero exit, on death by a signal (including core dumps) other than SIGHUP/SIGINT/SIGTERM/SIGPIPE, on operation timeouts, and on a watchdog timeout. It does *not* restart after systemd's own stop or restart [46]. Exit code 0 counts as clean, so it is not restarted.
- **Backoff.**
  - `RestartSec=` defaults to 100 ms [46].
  - `RestartSteps=` and `RestartMaxDelaySec=` (systemd ≥ 254) give exponential backoff. Example from the man page: `RestartSec=10s`, `RestartSteps=4`, `RestartMaxDelaySec=160s` produces 10, 20, 40, 80, 160 s [46].
  - `StartLimitIntervalSec=` and `StartLimitBurst=` go in **[Unit]**. They "apply to all kinds of starts (including manual)", and a unit that hits the limit is "not attempted to be restarted anymore" until `systemctl reset-failed` or the interval passes [47].
- **Resource budget.**
  - `MemoryHigh=` is "the main mechanism to control memory usage" (throttling). `MemoryMax=` is the hard cap; above it the OOM killer is invoked inside the unit [49].
  - `CPUWeight=` ranges 1–10000; the kernel default is 100 [49].
  - These need the cgroup v2 controllers delegated to the user manager. Upstream `user@.service` has `Delegate=pids memory cpu` [52]. `io` is **not** delegated, so `IOWeight=` has no effect in user units. Use `IOSchedulingClass=idle` (ioprio) instead [48].
- **Priority.** `Nice=` ranges from -20 (highest) to 19 (lowest) [48]. `OOMScoreAdjust=` ranges from -1000 to 1000 [48]. A user manager can *raise* the score but generally cannot lower it below the manager's level (kernel rule; **unverified** in the pages fetched).
- **Secrets.** `EnvironmentFile=` reads newline-separated `VAR=value` lines [48]. The systemd man page itself warns that "environment variables are not suitable for passing secrets", because they are visible over D-Bus and inherited by child processes. It recommends `LoadCredential=` instead [48]. The per-user manager looks for credentials in `$XDG_CONFIG_HOME/credstore/` and similar paths [48]. Below, I follow the requested `EnvironmentFile` + `chmod 600` pattern, with `LoadCredential=` noted as the stricter option, which needs a small app change.
- **Timers.**
  - `OnBootSec=` and `OnUnitActiveSec=` schedule the probe.
  - `AccuracySec=` defaults to 1 min [50].
  - `timers.target` exists in the user manager [54].
- **Network ordering.** `network-online.target` is a system unit and is not in the user manager's special units [54]. `After=network-online.target` in a user unit therefore does nothing (inference). `server.py` must retry Schwab and news connections itself.
- **Logs.** stdout and stderr go to the journal: `journalctl --user -u deltadesk-web`.

### Placeholders used below

| Placeholder | Meaning (fill in from step 0 of the runbook) |
|---|---|
| `<DESK_DIR>` | Directory that contains `server.py` (for example under `/home/box/...`) |
| `<PYTHON>` | Absolute path of the Python/venv interpreter currently used to run `server.py` |
| `<KRONOS_CMD>` | Exact command line that launches Kronos today (from `ps`) |
| `%h` | systemd specifier for the user's home directory (`/home/box`) [47] |

Memory values are **examples** sized for about 3 GB of free RAM. Measure the real peak first (runbook step 0) and set `MemoryHigh` to about 1.3× the observed peak RSS.

### 2.1 `~/.config/systemd/user/deltadesk-web.service`

```ini
[Unit]
Description=DeltaDesk server (web UI + engine threads: market data, Schwab stream, scanner, strategy lab, news)
# Bounded restarts: at most 8 starts in 15 min, counting automatic, manual and health-check starts.
# After that the unit stays "failed" and the health-check timer retries it slowly.
StartLimitIntervalSec=15min
StartLimitBurst=8

[Service]
Type=exec
WorkingDirectory=<DESK_DIR>
Environment=PYTHONUNBUFFERED=1
# Only non-password app settings belong here. The file is chmod 600 and is never committed.
EnvironmentFile=%h/.config/deltadesk/deltadesk.env
ExecStart=<PYTHON> <DESK_DIR>/server.py
Restart=on-failure
RestartSec=5s
# Exponential backoff 5s -> 2min (systemd >= 254; delete these two lines on older systemd)
RestartSteps=5
RestartMaxDelaySec=2min
# Give threads and SQLite (WAL) time to finish on stop; SIGKILL after that.
TimeoutStopSec=30s
# KillSignal=SIGINT   # optional: only if server.py turns KeyboardInterrupt into a clean shutdown
# Resource budget (EXAMPLE values: measure first)
MemoryHigh=1536M
MemoryMax=2G
CPUWeight=200
# Light hardening that works in user services
NoNewPrivileges=yes
UMask=0077
SyslogIdentifier=deltadesk-web

[Install]
WantedBy=default.target
```

### 2.2 `~/.config/systemd/user/deltadesk-kronos.service` (optional, low priority)

> This applies only if `server.py` can run with Kronos started *externally*. Check how `server.py` launches it today, for example `grep -n "subprocess\|Popen\|kronos" <DESK_DIR>/server.py`. If Kronos is hard-wired as a `subprocess` child, it already runs inside `deltadesk-web.service`'s cgroup, and the web unit's `MemoryMax` budgets both. In that case, skip this unit, or add a config switch to `server.py` first.

```ini
[Unit]
Description=DeltaDesk Kronos worker (optional, low priority)
# Restarts and stops of the web unit propagate here. Kronos failing never touches the web unit.
PartOf=deltadesk-web.service
After=deltadesk-web.service
StartLimitIntervalSec=1h
StartLimitBurst=5

[Service]
Type=exec
WorkingDirectory=<DESK_DIR>
EnvironmentFile=%h/.config/deltadesk/deltadesk.env
ExecStart=<KRONOS_CMD>
Restart=on-failure
RestartSec=30s
RestartSteps=4
RestartMaxDelaySec=10min
TimeoutStopSec=20s
# Lower priority than the web/engine unit
Nice=10
CPUWeight=20
IOSchedulingClass=idle
# Make the kernel prefer killing Kronos over anything else under global memory pressure
OOMScoreAdjust=500
# About 370 MB observed; throttle at 450M, hard cap 640M (EXAMPLE values)
MemoryHigh=450M
MemoryMax=640M
NoNewPrivileges=yes
SyslogIdentifier=deltadesk-kronos

[Install]
# Enabling this unit makes it start whenever the web unit starts
WantedBy=deltadesk-web.service
```

### 2.3 `~/.config/systemd/user/deltadesk-healthcheck.service`

```ini
[Unit]
Description=DeltaDesk readiness probe (restarts deltadesk-web after repeated /readyz failures)

[Service]
Type=oneshot
Environment=DESK_UNIT=deltadesk-web.service
Environment=DESK_READYZ_URL=http://127.0.0.1:8765/readyz
Environment=DESK_MAX_FAILS=3
Environment=DESK_WARMUP_SEC=120
Environment=DESK_FAILED_RETRY_SEC=900
ExecStart=%h/.local/bin/deltadesk-healthcheck
TimeoutStartSec=30s
Nice=5
```

### 2.4 `~/.config/systemd/user/deltadesk-healthcheck.timer`

```ini
[Unit]
Description=Run the DeltaDesk readiness probe every minute

[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
AccuracySec=10s

[Install]
WantedBy=timers.target
```

### 2.5 `~/.local/bin/deltadesk-healthcheck` (chmod 700)

```bash
#!/usr/bin/env bash
# Probe DeltaDesk /readyz. Restart only after N consecutive failures, skip the warm-up window,
# leave deliberately stopped units alone, and retry a start-limited ("failed") unit slowly.
set -u
UNIT="${DESK_UNIT:-deltadesk-web.service}"
URL="${DESK_READYZ_URL:-http://127.0.0.1:8765/readyz}"
MAX_FAILS="${DESK_MAX_FAILS:-3}"
WARMUP_SEC="${DESK_WARMUP_SEC:-120}"
FAILED_RETRY_SEC="${DESK_FAILED_RETRY_SEC:-900}"
STATE_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/deltadesk"
FAILS_FILE="$STATE_DIR/readyz.fails"
mkdir -p "$STATE_DIR"

now=$(date +%s)
ts() { date -d "$(systemctl --user show "$UNIT" -p "$1" --value)" +%s 2>/dev/null || echo 0; }

state="$(systemctl --user is-active "$UNIT" 2>/dev/null)"
case "$state" in
  active) ;;
  activating|deactivating|reloading|refreshing) exit 0 ;;   # systemd is already handling it
  failed)
    # Restart= gave up (start limit hit). Retry at most every FAILED_RETRY_SEC.
    if [ $(( now - $(ts StateChangeTimestamp) )) -ge "$FAILED_RETRY_SEC" ]; then
      echo "$UNIT is failed; reset-failed + start"
      systemctl --user reset-failed "$UNIT"
      systemctl --user start --no-block "$UNIT"
    fi
    exit 0 ;;
  *) exit 0 ;;   # inactive = deliberately stopped by the operator; don't fight it
esac

# Grace period right after a (re)start, while the engine warms up
[ $(( now - $(ts ActiveEnterTimestamp) )) -lt "$WARMUP_SEC" ] && exit 0

if curl -fsS --max-time 5 -o /dev/null "$URL"; then
  rm -f "$FAILS_FILE"; exit 0
fi
n=$(( $(cat "$FAILS_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$FAILS_FILE"
echo "readyz failed ($n/$MAX_FAILS): $URL"
if [ "$n" -ge "$MAX_FAILS" ]; then
  rm -f "$FAILS_FILE"
  echo "restarting $UNIT after $n consecutive failures"
  systemctl --user restart --no-block "$UNIT"   # counts toward StartLimitBurst (bounded)
fi
exit 0
```

**`/readyz` contract.** If `server.py` has no `/readyz`, add one. It should return 200 only when the engine threads are alive and the DB is writable, and it should return no data. With any tunnel, every request reaches the app from `127.0.0.1` (Funnel only proxies to `http://127.0.0.1` [16]), so this endpoint is effectively public.

### 2.6 `~/.config/deltadesk/deltadesk.env` (chmod 600, owner `box`)

```sh
# Non-secret settings and app-generated tokens only. Never the user's account passwords.
# Example keys (names are placeholders; use whatever server.py actually reads):
DESK_BIND=127.0.0.1
DESK_PORT=8765
# DESK_TOKEN=<generated on the box, e.g. python3 -c 'import secrets;print(secrets.token_urlsafe(32))'>
```

A stricter variant that systemd recommends [48]: put the token in `~/.config/credstore/deltadesk-token` (chmod 600), add `LoadCredential=deltadesk-token` to the unit, and have `server.py` read `$CREDENTIALS_DIRECTORY/deltadesk-token`.

---

## 3. Recommendation in detail

### Best zero-cost route for this exact situation

**Keep the box, add systemd (section 2), and add Tailscale Funnel on port 443 → `127.0.0.1:8765`.** If the owner is willing to install the free Tailscale app on the phone, use **Tailscale Serve** instead: same URL, tailnet-only.

Why Funnel wins on the stated requirements:
- It is the only verified option with all four of these properties: (a) **$0**, (b) **no domain to buy**, (c) a **stable** HTTPS URL that survives restarts (`--bg` config persists across reboot and `tailscale down`/`up` [16]), and (d) reachable from **any phone browser without installing anything** [15].
- TLS ends **on the box**, and Funnel relays "cannot decrypt" the traffic [15].
- It proxies to `http://127.0.0.1:<port>` [16], which matches how `server.py` already binds.

Why not the others:
- **ngrok Free**: the dev domain is stable and free [26], but there is a browser **interstitial** [26] and a **20,000 HTTP requests/month** cap [26]. Illustrative arithmetic, not a measurement: a page polling every 5 s during a 6.5 h session makes about 4,700 requests/day, roughly 98k per 21 trading days. That is about 5× the cap. Use it only as a fallback.
- **Cloudflare named tunnel + Access**: the best-engineered option, because the tunnel is free and Access adds email-OTP login in front of the app [4][10]. But it **requires a domain on Cloudflare**, which is **PAID** [2][7]. Zero Trust onboarding also asks for payment details, even though the Free plan charges nothing [9].
- **Free cloud hosts** (section 1b): either they sleep or lose disk (Render, Koyeb, HF), or they are trial-only or paid (Fly, Railway, HF Docker), or they need a card and a migration and still need a tunnel (Oracle, GCP).

### Honest tradeoffs of Funnel

1. **Public exposure.** The URL is on the open internet. Enabling HTTPS publishes the machine name and tailnet name in **public Certificate Transparency logs** [20], so expect scanners. Funnel adds **no authentication** and no identity headers [17]. DeltaDesk's own token/cookie auth is the only gate. Before going live:
   - Check that `server.py` does **not** trust `127.0.0.1` or `localhost` as "already authenticated". Every Funnel, cloudflared or ngrok request arrives from 127.0.0.1, so such a check would be a full auth bypass.
   - Move the token out of the URL query string. Use a one-time login that sets an `HttpOnly; Secure; SameSite=Strict` cookie, because URL tokens leak through browser history and shared links.
   - Rate-limit failed logins, and keep `/readyz` content-free.
2. **Privacy.** Better than the quick tunnel or ngrok, because the relay can't read traffic [15]. Tailscale still sees metadata and DNS names (CT logs) [20].
3. **Rate and bandwidth limits.** Bandwidth limits are "non-configurable" and **unpublished** [15]. A dashboard's HTML/JSON traffic is small, but there is no guarantee. Funnel is **beta** [15]. No SLA was found (**unverified**: none published).
4. **Unattended pitfalls.**
   - Tailscale node keys expire after **180 days** by default, after which connections "stop working". The user must **Disable Key Expiry** for the box [21].
   - Renaming the tailnet later breaks links [19].
   - Initial public DNS can take up to 10 minutes to appear [15].
   - Certificate renewal for Serve/Funnel is "automatically provisioned" [17][18], but renewal behavior is not documented (**unverified**). Section 4 includes a check.
5. **Serve instead of Funnel** removes points 1 and 3 entirely: tailnet-only, with ACLs and identity headers [17]. The cost is installing the Tailscale app on the phone and keeping it connected.

### What would require money (flagged PAID)

- **Domain for a Cloudflare named tunnel**: PAID, at-cost registrar pricing that varies by TLD; not quoted [7]. Partial/CNAME setup on a domain you already own elsewhere is **Business/Enterprise only** (PAID) [5].
- ngrok custom or reserved domains and removing the interstitial: PAID [26].
- Fly.io beyond the trial (PAID) [36]. Hugging Face Docker Spaces (PRO, PAID) [42]. Railway beyond $1/month of credit (PAID) [34].
- Any real uptime SLA (none available free).

### Does anything free meet "unattended uptime"?

Partly. systemd plus Funnel gives **unattended recovery from process crashes, hangs (through `/readyz`) and reboots**, plus a URL that never changes. It does **not** protect against the box losing power or network, and no free tier offers an SLA. If the box itself goes down, the desk is down.

---

## 4. Runbook: exact steps, and who does them

Legend: **[A]** = the assistant on the box (shell as `box`; never types or sees the user's passwords). **[U]** = the user personally (browser logins, sudo password, phone).

> Rule: if any `sudo` step asks for a password, **[U]** types it. The assistant never asks for it, stores it, or pipes it.
> Do the cutover (steps 3–4) **outside 09:30–16:00 ET** (evening or weekend).

### Step 0: Inventory (read-only) [A]

```bash
id; systemctl --version | head -1          # need >= 254 for RestartSteps/RestartMaxDelaySec
loginctl show-user box -p Linger
pgrep -af 'server\.py|watchdog\.sh|cloudflared|kronos'
crontab -l 2>/dev/null | grep -nE 'watchdog|server\.py|cloudflared'
ps -o pid,rss,etime,cmd -p "$(pgrep -d, -f 'server\.py|kronos')"   # RSS in KiB -> size MemoryHigh
readlink -f /proc/$(pgrep -f server.py | head -1)/exe               # -> <PYTHON>
readlink -f /proc/$(pgrep -f server.py | head -1)/cwd               # -> <DESK_DIR>
cat /sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers  # expect: cpu memory pids
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/readyz
grep -nE "127\.0\.0\.1|localhost|client_address|remote_addr" <DESK_DIR>/server.py   # look for a localhost auth bypass
grep -nE "subprocess|Popen|kronos" <DESK_DIR>/server.py                           # how Kronos is launched
```

### Step 1: Enable linger [A], with [U] as fallback

```bash
loginctl enable-linger box && loginctl show-user box -p Linger   # expect Linger=yes
# If it says "Access denied" or prompts for auth -> [U] runs:  sudo loginctl enable-linger box
```

### Step 2: Install units (no secrets in unit files) [A]

```bash
export XDG_RUNTIME_DIR=/run/user/$(id -u)
mkdir -p ~/.config/systemd/user ~/.config/deltadesk ~/.local/bin
install -m 600 /dev/null ~/.config/deltadesk/deltadesk.env      # then add the non-password settings
# Write the files from sections 2.1-2.5 with <DESK_DIR>, <PYTHON>, <KRONOS_CMD> filled in
chmod 700 ~/.local/bin/deltadesk-healthcheck
systemd-analyze --user verify ~/.config/systemd/user/deltadesk-*.service ~/.config/systemd/user/deltadesk-*.timer
systemctl --user daemon-reload
```

### Step 3: Cut over from watchdog.sh to systemd (after market hours) [A]

```bash
crontab -l > ~/crontab.backup.$(date +%F) 2>/dev/null || true
crontab -l 2>/dev/null | grep -v 'watchdog\.sh' | crontab -      # remove the watchdog entry (backup kept)
pkill -f watchdog.sh
pkill -INT -f server.py; pkill -f kronos                          # old copies must free port 8765
ss -ltnp | grep 8765 || echo "port free"
systemctl --user enable --now deltadesk-web.service deltadesk-healthcheck.timer
# systemctl --user enable deltadesk-kronos.service   # only if Kronos can run externally (see 2.2)
systemctl --user status deltadesk-web --no-pager
journalctl --user -u deltadesk-web -n 50 --no-pager
systemctl --user list-timers deltadesk-healthcheck.timer --no-pager
```

Leave the old quick-tunnel `cloudflared` process running until step 5 passes, as a temporary way in.

Crash test: `kill -9 $(systemctl --user show -p MainPID --value deltadesk-web)`. Expect an automatic restart within about 5 s (`journalctl --user -u deltadesk-web -f`).

### Step 4: Tailscale on the box

```bash
# [U] or [A] with passwordless sudo: install (official script) [22]
curl -fsSL https://tailscale.com/install.sh | sh
sudo systemctl enable --now tailscaled          # install doc doesn't say whether the script enables it
# [A] may run the next line, but [U] completes the login in their own browser at the printed URL
sudo tailscale up --hostname=<DESK_HOSTNAME>    # use a non-sensitive name: it ends up in public CT logs [20]
# [U]/sudo: let user "box" manage serve/funnel without sudo [23]
sudo tailscale set --operator=box
```

**[U] in the Tailscale admin console (browser, own account):**
1. DNS page: make sure **MagicDNS** is on, then **Enable HTTPS**. This acknowledges that names are published to CT logs [20].
2. Optional: choose the tailnet DNS name now. Changing it later "may break existing links" [19].
3. Machines page → the box → **Disable key expiry** [21].

**[A] Expose the desk (pick ONE: a port can't be Serve and Funnel at the same time [15]):**

```bash
tailscale status
# Option A, public, any browser (Funnel). The first run may print a link to approve Funnel -> [U] approves it [15]
tailscale funnel --bg 8765
tailscale funnel status
# Option B, private, phone needs the Tailscale app (Serve)
# tailscale serve --bg 8765 && tailscale serve status
tailscale status --json | python3 -c 'import json,sys; print("https://"+json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))'
```

### Step 5: Verify from the phone [U]

- **Funnel:** with Wi-Fi off and no Tailscale app, open the printed `https://<DESK_HOSTNAME>.<tailnet>.ts.net/` (allow up to 10 min for DNS [15]). Log in with the desk token and bookmark the page.
- **Serve:** install the Tailscale app, sign in with the same account, then open the same URL.
- **[A]** after it works: `pkill -f 'cloudflared tunnel --url'` to retire the quick tunnel, then confirm with `pgrep -af cloudflared`.
- **[A]** reboot test, at a time [U] approves: `sudo reboot` (or [U] reboots). Afterwards `systemctl --user status deltadesk-web` and `tailscale funnel status` should both be active without anyone logging in.
- **[A]** monthly certificate check:

```bash
H=<DESK_HOSTNAME>.<tailnet>.ts.net
echo | openssl s_client -connect "$H:443" -servername "$H" 2>/dev/null | openssl x509 -noout -enddate
```

### Rollback [A]

```bash
tailscale funnel reset        # or: tailscale serve reset   [16][18]
systemctl --user disable --now deltadesk-healthcheck.timer deltadesk-web.service deltadesk-kronos.service
crontab ~/crontab.backup.<DATE>          # restores watchdog.sh
```

### Fallback (free, but quota-limited): ngrok dev domain

- **[U]:** create the ngrok account, copy the authtoken, and paste it on the box. This is an API token, not a password, but the user handles it: `ngrok config add-authtoken <TOKEN>`.
- **[A]:** run it as a user unit with `ExecStart=<NGROK_BIN> http 8765 --url=https://<ASSIGNED_DEV_DOMAIN>`. The flag name may differ by agent version (`--url` vs `--domain`, **unverified**); check `ngrok http --help`. Alternatively use `ngrok service install --config <PATH>`, which creates a systemd unit but usually needs admin rights [29].
- Expect the interstitial page and the 1 GB / 20k-request monthly caps [26].

### Paid upgrade path, if the user ever buys a domain (PAID)

1. **[U]:** add the domain to Cloudflare (full setup with Cloudflare nameservers) [6], create a Zero Trust org on the Free plan (payment details required, $0) [9][8], create a tunnel, and copy its token.
2. **[U]/sudo:** `sudo cloudflared service install <TUNNEL_TOKEN>` [2].
3. **[U]:** add a published application with hostname `desk.<domain>` and service `http://localhost:8765` [3]. Protect it with an Access application that uses **one-time PIN** for the owner's email only [10].

---

## Sources (fetched 2026-10-31)

**Cloudflare**
1. Quick Tunnels (TryCloudflare): https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/
2. Tunnel, get started (prerequisites, `cloudflared service install <TUNNEL_TOKEN>`): https://developers.cloudflare.com/tunnel/get-started/index.md
3. Create a remotely-managed tunnel (publish application, add a website first): https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/index.md
4. Cloudflare blog, "Tunnel for everyone" (2021-04-15): https://blog.cloudflare.com/tunnel-for-everyone
5. Partial (CNAME) setup, Business/Enterprise only: https://developers.cloudflare.com/dns/zone-setups/partial-setup/index.md
6. Full (primary) setup, the only option for Free/Pro: https://developers.cloudflare.com/dns/zone-setups/full-setup/
7. Cloudflare Registrar (at cost, no markup): https://developers.cloudflare.com/registrar
8. Cloudflare SASE / Zero Trust plans (Free: $0, 50 users): https://www.cloudflare.com/plans/sase-zero-trust.md
9. Create a Zero Trust organization (payment details needed on Free): https://developers.cloudflare.com/learning-paths/zero-trust-web-access/initial-setup/create-zero-trust-org/
10. Access one-time PIN: https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/index.md
11. Access identity providers (and GitHub IdP): https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/index.md and https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/github/
12. Cloudflare WebSockets: https://developers.cloudflare.com/network/websockets
13. cloudflared as a Linux service: https://developers.cloudflare.com/tunnel/advanced/local-management/as-a-service/linux/

**Tailscale**

14. Tailscale pricing (Personal plan): https://tailscale.com/pricing
15. Tailscale Funnel: https://tailscale.com/kb/1223/funnel (same content at https://tailscale.com/docs/features/tailscale-funnel.md)
16. `tailscale funnel` CLI (`--bg`, ports 443/8443/10000, `http://127.0.0.1` only, reset): https://tailscale.com/kb/1311/tailscale-funnel
17. Tailscale Serve (tailnet-only, identity headers, Funnel has none): https://tailscale.com/kb/1312/serve and https://tailscale.com/docs/features/tailscale-serve.md
18. `tailscale serve` CLI (`--bg` persistence, status, reset): https://tailscale.com/docs/reference/tailscale-cli/serve
19. Tailnet names: https://tailscale.com/docs/concepts/tailnet-name.md (also https://tailscale.com/kb/1217/tailnet-name)
20. Enabling HTTPS (CT log publication, Let's Encrypt): https://tailscale.com/docs/how-to/set-up-https-certificates.md
21. Key expiry (180-day default, disable per device): https://tailscale.com/docs/features/access-control/key-expiry.md
22. Install on Linux: https://tailscale.com/docs/install/linux.md
23. Linux operator permission (`tailscale set --operator`): https://tailscale.com/docs/reference/troubleshooting/linux/linux-operator-permission.md
24. Funnel examples: https://tailscale.com/docs/reference/examples/funnel
25. Userspace networking: https://tailscale.com/docs/concepts/userspace-networking

**ngrok**

26. ngrok free plan limits: https://ngrok.com/docs/pricing-limits/free-plan-limits/
27. ngrok pricing: https://ngrok.com/pricing
28. ngrok WebSockets: https://ngrok.com/docs/using-ngrok-with/websockets.md
29. ngrok agent as a service: https://ngrok.com/docs/gateway/agent/service.md

**Cloud hosts**

30. Oracle Always Free resources: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
31. Oracle Free Tier FAQ: https://www.oracle.com/cloud/free/faq/
32. Google Cloud Free Tier features: https://docs.cloud.google.com/free/docs/free-cloud-features
33. Render, Deploy for Free: https://render.com/docs/free
34. Railway pricing plans: https://docs.railway.com/pricing/plans.md
35. Railway free trial: https://docs.railway.com/reference/pricing/free-trial
36. Fly.io free trial: https://fly.io/docs/about/free-trial/
37. Fly.io resource pricing: https://fly.io/docs/about/pricing/
38. Fly.io discontinued plans: https://fly.io/docs/about/discontinued-plans/
39. Koyeb pricing FAQ: https://www.koyeb.com/docs/faqs/pricing
40. Koyeb scale-to-zero: https://www.koyeb.com/docs/run-and-scale/scale-to-zero
41. Koyeb pricing page: https://www.koyeb.com/pricing
42. Hugging Face Spaces overview: https://huggingface.co/docs/hub/en/spaces-overview
43. Hugging Face Spaces hardware: https://huggingface.co/docs/hub/en/spaces-gpus
44. Hugging Face Spaces storage: https://huggingface.co/docs/hub/en/spaces-storage
45. huggingface_hub, manage Spaces (48 h on cpu-basic): https://huggingface.co/docs/huggingface_hub/guides/manage-spaces

**systemd**

46. systemd.service(5) (Restart=, RestartSec=, RestartSteps=, RestartMaxDelaySec=, TimeoutStopSec=; page v262): https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html
47. systemd.unit(5) (StartLimitIntervalSec=/StartLimitBurst=, user unit paths, %h/%t specifiers): https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html
48. systemd.exec(5) (Nice=, OOMScoreAdjust=, IOSchedulingClass=, EnvironmentFile=, secrets warning, LoadCredential=): https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
49. systemd.resource-control(5) (MemoryHigh=, MemoryMax=, CPUWeight=, Delegate=): https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html
50. systemd.timer(5): https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html
51. loginctl(1) (enable-linger): https://www.freedesktop.org/software/systemd/man/latest/loginctl.html
52. Upstream `user@.service` unit (`Delegate=pids memory cpu`): https://github.com/systemd/systemd/blob/main/units/user%40.service.in
53. Upstream logind polkit policy (`org.freedesktop.login1.set-self-linger`, allow_any=yes): https://github.com/systemd/systemd/blob/main/src/login/org.freedesktop.login1.policy
54. systemd.special(7) (Special User Units include timers.target; network-online.target is a system unit): https://www.freedesktop.org/software/systemd/man/latest/systemd.special.html

Notes on method:
- Some freedesktop "latest" pages were blocked by the fetch proxy. Their text was checked against the versioned freedesktop pages (v258/v260/v262) and against the upstream systemd `man/*.xml` sources, which are the same documents.
- The e2-micro RAM figure, Railway sleep/worker/card details, Koyeb free volumes, Hugging Face WebSockets and bucket pricing, Tailscale Funnel bandwidth numbers, WebSocket support and certificate renewal, and ngrok overage behavior could not be confirmed in official docs. They are marked **unverified** above.
