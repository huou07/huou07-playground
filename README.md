# huou07 playground

A private, single-user Linux workspace dashboard. The first implementation unit is a responsive home dashboard with live, read-only Linux metrics and clear unavailable states for hardware integrations that are not configured.

## Current implementation

- Compact responsive dashboard with dark default and persisted light theme.
- Live CPU utilization, logical/physical core counts, frequency and temperature where exposed, RAM, root filesystem, detected physical drive model/type/capacity, swap/ZRAM, host identity, uptime, and physical network byte counters from Linux procfs and sysfs. Drive health is not queried; serial identifiers are not collected.
- Process owner, PID, CPU and memory data come from procfs. Service state comes from systemd; searches and sorting run in the browser. CPU, process and network rates use successive samples and return to unavailable/sampling states after long gaps. Network rates display in Kbps/Mbps; cumulative interface totals remain in bytes.
- WireGuard is the intended primary private access path, with SSH tunnels retained as an independent recovery route. The dashboard binds to loopback and, when available, the exact private IPv4 assigned to `wg0`, with the WireGuard socket bound to that device. It does not accept the WireGuard address through other interfaces. When UFW is active and `wg0` has a listener, the installer records and allows that UDP port only on the host's default-route interface; uninstall removes only that recorded rule. Configure the router's external UDP mapping separately. The installed wg-easy setup still needs the owner's endpoint and first peer before a real external handshake can be verified. Tailscale status omits private peer names and addresses; Tailscale Serve remains disabled.
- LiteLLM Gateway is installed as a separate rootless Podman service with a private PostgreSQL database. The proxy binds to server loopback on port 4000; the dashboard relays its UI and API only over `wg0`, with SSH forwarding as recovery. Provider credentials and model configuration remain owner-controlled and have not been entered.
- NVIDIA utilization, VRAM, and temperature use `nvidia-smi`. Intel i915 engine busy counters use a separate restricted `intel_gpu_top` sampler. The dashboard labels Intel usage as the busiest engine and does not invent dedicated VRAM or GPU temperature. CPU package watts use a separate restricted systemd collector; the dashboard account reads only recent sanitized samples and never receives hardware-counter access or root privileges.
- Service and process views are read-only. Cockpit provides a separate browser terminal and host management UI. Applications can be managed from Settings, with optional server-local health checks. The dashboard relays configured web interfaces only over `wg0`; each application service remains loopback-only. Use SSH tunnels until WireGuard passes external handshake and private-service checks.

## Run locally

Requires Python 3.10+; no third-party Python packages are used.

```sh
make run
```

Open `http://127.0.0.1:8765`. `PORT` can be changed for local development; `HOST` accepts loopback addresses only. When deployed, the dashboard also binds to the private IPv4 assigned to `wg0`, if present, and limits that listener to traffic arriving through `wg0`. It never binds to all interfaces. Metrics and process APIs are read-only. The application registry accepts validated same-origin changes from the local dashboard; it cannot run commands or store credentials.

### Browser acceptance checks

The browser suite uses a temporary dashboard registry and local test app; it does not alter a deployment or the normal app registry. It requires Node.js 20+ and uses test-only JavaScript dependencies. Install them and Chromium once, then run:

```sh
npm ci
npx playwright install chromium
make acceptance
```

The suite checks all nine routes, mobile navigation, persistent theme/refresh/metric preferences, and adding, health-checking, launching, and removing a local test app. To use an existing Chrome or Chromium binary instead of Playwright's downloaded browser, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable path.

### Application registry

Add and edit links on the Settings page. The installer seeds `/var/lib/huou07-playground/apps.json` from [`config/apps.example.json`](config/apps.example.json) and preserves it on upgrades. Component installers add their launch link after the service is ready, without overwriting an existing Settings entry. Existing installs migrate the registry from `/etc/huou07-playground/apps.json`. The dashboard can write only this validated, non-executable registry; application secrets stay under the root-managed `/etc/huou07-playground` directory. The registry is out of Git; do not put credentials or tokens in it. Health checks are optional, use GET or HEAD, and can target only `localhost`, `127.0.0.1`, or `::1`, which prevents the dashboard from probing other hosts. Example:

```json
{
  "apps": [
    {
      "name": "Example app",
      "url": "http://127.0.0.1:3000/",
      "description": "A short note",
      "category": "Tools",
      "management_url": "http://127.0.0.1:3000/admin",
      "health_url": "http://127.0.0.1:3000/health",
      "health_method": "GET"
    }
  ]
}
```

Only `name` and `url` are required. URLs must use HTTP or HTTPS. The app link opens in your browser, so its URL must be reachable from that device. For a loopback-only app, add its port to your SSH tunnel and use the forwarded `127.0.0.1` URL. Optional `management_url` adds a separate Manage link to the app's own admin page. Optional health checks run from the server using GET or HEAD, do not follow redirects, and have a one-second timeout; the probe URL stays server-side and is not returned to the browser. Entries without a health URL display as “Not monitored.” `/api/apps` returns up to 20 validated entries and does not provide app credentials or control actions.

## Install on Debian with systemd

From a trusted checkout on the server, run `sudo ./deploy/install.sh`. It installs the web files under `/opt/huou07-playground`, creates a dedicated unprivileged service account, and starts a systemd unit that listens on loopback and, when present, only the private IPv4 assigned to `wg0`, with that listener bound to the WireGuard device. The installer waits for a successful dashboard health response and restores the previous release if the new one does not become healthy. On a host with active UFW, it adds TCP allowances for the dashboard and configured app interfaces on `wg0` only; the rules take effect when that interface is present. It does not change global firewall policies, SSH, VPN, or router settings. To remove the app and its releases, run `sudo ./deploy/uninstall.sh`; it removes only firewall rules recorded as created by this installer, and retains the dedicated account.

On a host with rootless Podman configured, run `sh deploy/check-rootless-sandbox.sh` as the unprivileged Podman owner to verify the digest-pinned workspace boundary before integrating a containerized agent.

### Back up and restore private state

Before uninstalling or making a risky change, run `sudo python3 /opt/huou07-playground/current/deploy/state.py backup`. The archive is written with mode `0600` under `/var/backups/huou07-playground/`, outside the repository. It contains the app registry, files under the OpenCode workspace, OpenCode's private config/sessions/provider auth, LiteLLM's database dump and private environment files when installed, OmniRoute's database/session data and private environment when installed, and the private turtle image when present. Workspace symlinks and special files are rejected; up to 100,000 workspace files and directories are supported, with file contents streamed without an application size cap. The archive is not encrypted; treat it as a credential file and store copies only on trusted storage. Backup briefly stops OpenCode and OmniRoute to snapshot their state, while LiteLLM uses an online PostgreSQL dump; stopped services are started again afterward. Restore validates the archive before replacing state, replaces the OpenCode workspace contents with the archived copy, and restarts the services whose data is included: `sudo python3 /opt/huou07-playground/current/deploy/state.py restore /var/backups/huou07-playground/<archive>.tar.gz`. Each AI service's private state is limited to 1 GiB per archive. Backups stay local unless you copy them to trusted storage yourself.

To open the dashboard and its configured web apps from a computer that can SSH to the server, run this from the checkout:

```sh
./tools/huou07-ssh-tunnel <your-ssh-alias>
```

Then open `http://127.0.0.1:8765`. The helper forwards the dashboard, Cockpit, LiteLLM, wg-easy, OpenCode Web, and OmniRoute to this computer's loopback only. It stays in the foreground; press Ctrl+C to close it. SSH host-key verification remains controlled by your normal SSH configuration. On a phone, configure the same local-to-server forwards in its SSH client before opening the dashboard; this remains the recovery access method. After wg-easy setup, open the dashboard at the server's private WireGuard address on port `8765`. The dashboard relays the installed Cockpit, OpenCode, LiteLLM, OmniRoute, and wg-easy web interfaces on their documented ports, while their own services remain loopback-only. Relay sockets accept traffic only on `wg0`; active UFW hosts receive matching interface-scoped TCP rules. In each client, set `Allowed IPs` to only the server's WireGuard address (or explicitly needed private subnets); do not use `0.0.0.0/0` or `::/0`, and do not set client DNS. Verify the dashboard handshake, normal Internet, and local-LAN routes before relying on the peer. Keep SSH available independently. The dashboard binds only to loopback and the exact private `wg0` address. Restart `huou07-playground.service` over SSH if the `wg0` address changes.

### Private WireGuard setup

Install the pinned wg-easy service with `sudo ./deploy/install-wg-easy.sh`. Its administration page stays on server loopback; the SSH tunnel above forwards `51821`, so open `http://127.0.0.1:51821`, or open it from the dashboard while connected through WireGuard. In the v15 owner setup wizard, enter the DDNS hostname and the UDP listen port that matches the router's verified external-to-server mapping. The wizard stores the host and listen port and uses them in generated client profiles; do not guess the previously mentioned port. See the upstream [v15 setup guide](https://wg-easy.github.io/wg-easy/latest/guides/setup/).

For every client, set `Allowed IPs` to the server's WireGuard address only unless another private subnet is explicitly needed. Do not include `0.0.0.0/0` or `::/0`, and leave client DNS unchanged. `Allowed IPs` determines client-side routes; wg-easy documents this in its [client settings](https://wg-easy.github.io/wg-easy/latest/guides/clients/). The Network page shows the detected server-side UDP listen port; it cannot verify the router's external port-forward rule. Map the router's chosen external UDP port to that server port. The dashboard and fixed app relays bind only to the private IPv4 address on `wg0` and the WireGuard device. The installer adds TCP allowances on `wg0` only when UFW is active; it never adds WAN or LAN interface rules. Keep SSH as recovery access until an external cellular peer passes handshake, dashboard, Internet, LAN, reconnect, and revocation checks. Verify router UDP forwarding separately from these private-interface TCP rules.

To reach LiteLLM through the same private tunnel, open `http://127.0.0.1:4000/ui`; the SSH command above forwards its loopback port. Sign in as `admin` using the gateway master key from `/etc/huou07-litellm/litellm.env` on the server. Keep that key on the server and enter provider credentials yourself in LiteLLM after signing in. The master key is also included in local state backups, which must be handled as credentials.

Install the isolated LiteLLM gateway on a compatible Debian host with `sudo ./deploy/install-litellm.sh`. It requires rootless Podman and creates a dedicated service account, loopback-only proxy, private PostgreSQL database, and local-only secrets. An empty startup model list enables LiteLLM's database-backed model management without putting credentials in a YAML file. The first install does not configure providers or models; complete those steps in LiteLLM yourself after login. Back up before upgrades or restore operations using the state commands above.

### OmniRoute free model gateway

Install OmniRoute with `sudo ./deploy/install-omniroute.sh` after installing the dashboard. It uses the upstream stable `3.8.51` container, a dedicated rootless account, local Redis cache, a persistent private data directory, API-key enforcement, and systemd CPU/memory limits. Dashboard, API, and live-WebSocket ports `20128`, `20129`, and `20132` bind only to server loopback and are relayed through the dashboard on `wg0`; the SSH command above forwards all three for recovery access. Sign in at `http://127.0.0.1:20128`. The generated first-login password is kept in `/etc/huou07-omniroute/omniroute.env`; retrieve it yourself on the server and do not paste it into chat. Add provider accounts and keys through OmniRoute after signing in. No provider is preconfigured. OmniRoute data and its private environment are included in local backups. The 10 GiB service memory cap follows the upstream single coding-agent guidance; coding-context inference and provider flows still need owner setup and runtime validation.

### OpenCode CLI and web interface

Install OpenCode CLI for the SSH owner's account from the official source with `curl -fsSL https://opencode.ai/install | bash -s -- --version 1.18.35 --no-modify-path`, then run `sh deploy/install-opencode-launcher.sh` as that account. To enable the web workspace, install bubblewrap and run `sudo ./deploy/install-opencode-web.sh` from a trusted checkout. The installer copies only the CLI executable into a separate, restricted `huou07-opencode` system account, creates an empty shared workspace at `/srv/huou07-opencode-workspaces`, and starts a loopback-only web service with HTTP Basic Authentication. It does not copy any project or provider credentials. The systemd unit hides user home directories, limits writes to private state and the workspace, and caps memory at 4 GiB and CPU at two cores. Shell commands run in bubblewrap with the selected checkout writable; provider state, files outside that checkout, owner home, and the web password environment are hidden. For a linked worktree, the selected repository’s shared Git metadata is also writable so Git can update its index and commits. Host networking remains available for dependency downloads, and each command still requires approval. The shell supports linked Git worktrees when their shared Git metadata stays under `/srv/huou07-opencode-workspaces`; it mounts that repository metadata while keeping other worktree files hidden. Worktrees with common metadata outside this directory and repositories using external Git object alternates are refused. OpenCode's default policy also asks before edits and subagents. Verify the boundary with `sudo ./deploy/check-opencode-web-sandbox.sh`. The owner must sign in to providers manually in the web UI; their credentials and sessions are stored in the service's private state at `/var/lib/huou07-opencode` and included in local dashboard backups. Add the SSH owner's account to the workspace group via the installer, then start a new SSH session before managing workspace files. Forward local port 14096 to server loopback port 4096 and open `http://127.0.0.1:14096`, or open it from the dashboard while connected through WireGuard; sign in as `opencode` and retrieve the generated web password with `sudo cat /etc/huou07-playground/opencode-web.env`. The web service itself stays loopback-only. Do not use unattended mode; native authentication and an authenticated coding run still require owner setup.

### Codex CLI on the server

Codex CLI 0.161.0 is installed for the SSH owner. The managed profile in `deploy/codex-requirements.toml` makes the active workspace writable and denies sandboxed local commands access to the rest of the filesystem. Install it with `sudo ./deploy/install-codex-policy.sh`, then run `./deploy/check-codex-policy.sh` as the Codex owner. The check verifies an in-workspace write, a blocked home-directory read, and a blocked full-access override. Re-run it after Codex upgrades because permission profiles are beta and may change.

Open Cockpit's terminal, change into a project directory, and run `codex --ask-for-approval on-request`. The system-managed profile is the default; do not pass legacy `--sandbox` options, which select the older sandbox mode. On first launch, sign in with ChatGPT yourself; huou07 playground does not handle provider credentials. This filesystem profile covers Codex's sandboxed local commands, not separate MCP, browser, connector, or cloud execution surfaces. See the official [Codex permissions documentation](https://learn.chatgpt.com/docs/permissions) for its scope and limitations.

## Optional CPU package power telemetry

The dashboard uses `turbostat`'s `PkgWatt` summary when supported. On Debian, `turbostat` is provided by [`linux-cpupower`](https://packages.debian.org/trixie/linux-cpupower). Install it with `sudo apt install linux-cpupower`, then install or upgrade huou07 playground. The installer sets up a separate fixed-purpose systemd sampler with read-only MSR device access and a 15-second timer; it writes only a sanitized sample that the dashboard can read. Unsupported CPUs or unavailable counters remain `N/A`. The web service gets no MSR access, root, or sudo permission. This measures CPU package power, not whole-system wall power.

## Optional Intel GPU telemetry

On Debian 13 systems using Intel's `i915` driver, install [`intel-gpu-tools`](https://packages.debian.org/trixie/intel-gpu-tools) with `sudo apt install intel-gpu-tools`, then install or upgrade huou07 playground. The installer detects i915 and enables a 30-second one-shot collector. This kernel's system-wide i915 metrics require privileged access, so the fixed collector runs as a bounded system service with only `CAP_SYS_ADMIN`, no network, restricted namespaces, and mount/module/reboot/swap syscalls blocked. It accesses the GPU through the normal `video` and `render` groups. The web service reads only the atomic sanitized sample and has no GPU device or performance-counter access. Intel GPU usage is the busiest engine percentage; shared system memory is not reported as dedicated VRAM.

## Optional SSH terminal and system management

On Debian 13 with its official backports repository enabled, run `sudo ./deploy/install-cockpit.sh` and `sudo ./deploy/install-cockpit-files.sh`. Cockpit Files adds the file browser, upload, and download UI. The second script also installs a small Cockpit page for moving a file or directory into an existing destination directory. Its Browse controls let you navigate directories and choose the source and destination; absolute paths can also be entered directly. It refuses to overwrite an existing name and runs as the signed-in Linux user, with no added privileges. The scripts simulate package plans and refuse removals; Cockpit itself is configured to listen only on `127.0.0.1:9090`. Cockpit is a separate, powerful host-management application; it does not run inside the dashboard's restricted service account. Its web login requires a valid Linux account credential. Do not enable SSH password login just to make Cockpit work. The dashboard shows Cockpit and Cockpit Files availability and links to them when ready. The SSH tunnel command forwards Cockpit over an encrypted SSH channel; the dashboard relays it on `wg0` when WireGuard is available. Cockpit's local HTTP mode uses the SSH tunnel or encrypted WireGuard transport.

The backport version floor avoids older releases affected by known security issues: [Cockpit 360 security fix](https://cockpit-project.org/blog/cockpit-360.html), [Debian Cockpit backports](https://tracker.debian.org/pkg/cockpit/news/), and [Cockpit loopback/TLS behavior](https://docs.cockpit-project.org/cockpit-guide/main/guide/https.html). The dashboard uninstall script intentionally leaves Cockpit installed because it is an independently managed host component.

## Turtle branding

The dashboard uses the supplied Google Noto Emoji turtle (U+1F422) as its local brand image. The image is distributed under Apache License 2.0; its attribution and the complete license are next to the image in `web/static/`. This keeps clean checkouts and deployments consistent with the supplied design.

## Server discovery

A non-destructive target inspection was completed before implementation. Existing workloads and remote access must be preserved. No packages or services were changed during discovery. Host-specific inventory is intentionally excluded from this public repository.

## Development status

See [docs/STATUS.md](docs/STATUS.md) for verified progress, known gaps, and the next safe action. This repository is not production-ready; deployment and security acceptance remain outstanding.
