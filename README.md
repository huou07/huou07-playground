# huou07 playground

A private, single-user Linux workspace dashboard. The first implementation unit is a responsive home dashboard with live, read-only Linux metrics and clear unavailable states for hardware integrations that are not configured.

## Current implementation

- Compact responsive dashboard with dark default and persisted light theme.
- Live CPU utilization, logical/physical core counts, frequency and temperature where exposed, RAM, root filesystem, detected physical drive model/type/capacity, swap/ZRAM, host identity, uptime, and physical network byte counters from Linux procfs and sysfs. Drive health is not queried; serial identifiers are not collected.
- Process owner, PID, CPU and memory data come from procfs. Service state comes from systemd; searches and sorting run in the browser. CPU, process and network rates use successive samples and return to unavailable/sampling states after long gaps. Network rates display in Kbps/Mbps; cumulative interface totals remain in bytes.
- The VPN indicator reflects the Tailscale client's running state and omits private peer names and addresses. Browser access currently uses SSH tunnels; the requested WireGuard access path is not yet configured.
- LiteLLM Gateway is installed as a separate rootless Podman service with a private PostgreSQL database. The proxy binds to server loopback on port 4000; its dashboard and API are available through an SSH tunnel. Provider credentials and model configuration remain owner-controlled and have not been entered.
- NVIDIA utilization, VRAM, and temperature use `nvidia-smi`. Intel i915 engine busy counters use a separate restricted `intel_gpu_top` sampler. The dashboard labels Intel usage as the busiest engine and does not invent dedicated VRAM or GPU temperature. CPU package watts use a separate restricted systemd collector; the dashboard account reads only recent sanitized samples and never receives hardware-counter access or root privileges.
- Service and process views are read-only. Cockpit provides a separate browser terminal and host management UI. Applications can be managed from Settings, with optional server-local health checks. Direct browser access stays disabled; use SSH tunnels.

## Run locally

Requires Python 3.10+; no third-party Python packages are used.

```sh
make run
```

Open `http://127.0.0.1:8765`. `PORT` can be changed for local development; `HOST` accepts loopback addresses only. The listener cannot be exposed to a LAN or WAN until authentication and private-network access controls exist. Metrics and process APIs are read-only. The application registry accepts validated same-origin changes from the local dashboard; it cannot run commands or store credentials.

### Application registry

Add and edit links on the Settings page. The installer seeds `/etc/huou07-playground/apps.json` from [`config/apps.example.json`](config/apps.example.json) once and preserves it on upgrades. The dashboard can write only this validated, non-executable registry. The file is out of Git; do not put credentials or tokens in it. Health checks are optional, use GET or HEAD, and can target only `localhost`, `127.0.0.1`, or `::1`, which prevents the dashboard from probing other hosts. Example:

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

From a trusted checkout on the server, run `sudo ./deploy/install.sh`. It installs the web files under `/opt/huou07-playground`, creates a dedicated unprivileged service account, and starts a loopback-only systemd unit. It does not change firewall, VPN, proxy, or SSH settings. The installer keeps prior releases so the symlink can be switched back if an upgrade fails. To remove the app and its releases, run `sudo ./deploy/uninstall.sh`; the dedicated account is retained.

On a host with rootless Podman configured, run `sh deploy/check-rootless-sandbox.sh` as the unprivileged Podman owner to verify the digest-pinned workspace boundary before integrating a containerized agent.

### Back up and restore private state

Before uninstalling or making a risky change, run `sudo python3 /opt/huou07-playground/current/deploy/state.py backup`. The archive is written with mode `0600` under `/var/backups/huou07-playground/`, outside the repository. It contains the app registry, OpenCode's private config/sessions/provider auth, LiteLLM's database dump and private environment files when installed, and the private turtle image when present. The archive is not encrypted; treat it as a credential file and store copies only on trusted storage. Backup briefly stops OpenCode and LiteLLM so their state is consistent, then starts them again. Restore validates the archive before replacing state and restarts the services whose data is included: `sudo python3 /opt/huou07-playground/current/deploy/state.py restore /var/backups/huou07-playground/<archive>.tar.gz`. OpenCode state is limited to 1 GiB per archive; larger state is rejected without creating a backup. Backups stay local unless you copy them to trusted storage yourself.

To open the dashboard from a computer that can SSH to the server, create a local tunnel:

```sh
ssh -L 8765:127.0.0.1:8765 -L 9090:127.0.0.1:9090 -L 14096:127.0.0.1:4096 <your-ssh-alias>
```

Then open `http://127.0.0.1:8765` on that computer. This is a private access method over SSH; direct LAN/VPN browser access is not enabled yet. Keep the SSH tunnel running while using the dashboard.

To reach LiteLLM through the same private tunnel, add `-L 4000:127.0.0.1:4000` and open `http://127.0.0.1:4000/ui`. Sign in as `admin` using the gateway master key from `/etc/huou07-litellm/litellm.env` on the server. Keep that key on the server and enter provider credentials yourself in LiteLLM after signing in. The master key is also included in local state backups, which must be handled as credentials.

Install the isolated LiteLLM gateway on a compatible Debian host with `sudo ./deploy/install-litellm.sh`. It requires rootless Podman and creates a dedicated service account, loopback-only proxy, private PostgreSQL database, and local-only secrets. An empty startup model list enables LiteLLM's database-backed model management without putting credentials in a YAML file. The first install does not configure providers or models; complete those steps in LiteLLM yourself after login. Back up before upgrades or restore operations using the state commands above.

### OpenCode CLI and web interface

Install OpenCode CLI for the SSH owner's account from the official source with `curl -fsSL https://opencode.ai/install | bash -s -- --version 1.18.35 --no-modify-path`, then run `sh deploy/install-opencode-launcher.sh` as that account. To enable the web workspace, run `sudo ./deploy/install-opencode-web.sh` from a trusted checkout. The installer copies only the CLI executable into a separate, restricted `huou07-opencode` system account, creates an empty shared workspace at `/srv/huou07-opencode-workspaces`, and starts a loopback-only web service with HTTP Basic Authentication. It does not copy any project or provider credentials. The systemd unit hides user home directories, limits writes to its private state and workspace, and caps memory at 4 GiB and CPU at two cores. OpenCode's default policy asks before shell commands, edits, and subagents. Verify the boundary with `sudo ./deploy/check-opencode-web-sandbox.sh`. The owner must sign in to providers manually in the web UI; their credentials and sessions are stored in the service's private state at `/var/lib/huou07-opencode` and included in local dashboard backups. Add the SSH owner's account to the workspace group via the installer, then start a new SSH session before managing workspace files. Forward local port 14096 to server loopback port 4096 and open `http://127.0.0.1:14096`; sign in as `opencode` and retrieve the generated web password with `sudo cat /etc/huou07-playground/opencode-web.env`. Keep the server bound to loopback and use the SSH tunnel. Do not use unattended mode; native authentication and an authenticated coding run still require owner setup.

### Codex CLI on the server

Codex CLI 0.161.0 is installed for the SSH owner. The managed profile in `deploy/codex-requirements.toml` makes the active workspace writable and denies sandboxed local commands access to the rest of the filesystem. Install it with `sudo ./deploy/install-codex-policy.sh`, then run `./deploy/check-codex-policy.sh` as the Codex owner. The check verifies an in-workspace write, a blocked home-directory read, and a blocked full-access override. Re-run it after Codex upgrades because permission profiles are beta and may change.

Open Cockpit's terminal, change into a project directory, and run `codex --ask-for-approval on-request`. The system-managed profile is the default; do not pass legacy `--sandbox` options, which select the older sandbox mode. On first launch, sign in with ChatGPT yourself; huou07 playground does not handle provider credentials. This filesystem profile covers Codex's sandboxed local commands, not separate MCP, browser, connector, or cloud execution surfaces. See the official [Codex permissions documentation](https://learn.chatgpt.com/docs/permissions) for its scope and limitations.

## Optional CPU package power telemetry

The dashboard uses `turbostat`'s `PkgWatt` summary when supported. On Debian, `turbostat` is provided by [`linux-cpupower`](https://packages.debian.org/trixie/linux-cpupower). Install it with `sudo apt install linux-cpupower`, then install or upgrade huou07 playground. The installer sets up a separate fixed-purpose systemd sampler with read-only MSR device access and a 15-second timer; it writes only a sanitized sample that the dashboard can read. Unsupported CPUs or unavailable counters remain `N/A`. The web service gets no MSR access, root, or sudo permission. This measures CPU package power, not whole-system wall power.

## Optional Intel GPU telemetry

On Debian 13 systems using Intel's `i915` driver, install [`intel-gpu-tools`](https://packages.debian.org/trixie/intel-gpu-tools) with `sudo apt install intel-gpu-tools`, then install or upgrade huou07 playground. The installer detects i915 and enables a 30-second one-shot collector. This kernel's system-wide i915 metrics require privileged access, so the fixed collector runs as a bounded system service with only `CAP_SYS_ADMIN`, no network, restricted namespaces, and mount/module/reboot/swap syscalls blocked. It accesses the GPU through the normal `video` and `render` groups. The web service reads only the atomic sanitized sample and has no GPU device or performance-counter access. Intel GPU usage is the busiest engine percentage; shared system memory is not reported as dedicated VRAM.

## Optional SSH terminal and system management

On Debian 13 with its official backports repository enabled, run `sudo ./deploy/install-cockpit.sh` and `sudo ./deploy/install-cockpit-files.sh`. Cockpit Files adds the file browser, upload, and download UI. The scripts simulate package plans and refuse removals; Cockpit itself is configured to listen only on `127.0.0.1:9090`. Cockpit is a separate, powerful host-management application; it does not run inside the dashboard's restricted service account. Its web login requires a valid Linux account credential. Do not enable SSH password login just to make Cockpit work. The dashboard shows Cockpit and Cockpit Files availability and links to them when ready. The tunnel command above forwards both private loopback services. The browser uses Cockpit's local HTTP mode over the encrypted SSH tunnel.

The backport version floor avoids older releases affected by known security issues: [Cockpit 360 security fix](https://cockpit-project.org/blog/cockpit-360.html), [Debian Cockpit backports](https://tracker.debian.org/pkg/cockpit/news/), and [Cockpit loopback/TLS behavior](https://docs.cockpit-project.org/cockpit-guide/main/guide/https.html). The dashboard uninstall script intentionally leaves Cockpit installed because it is an independently managed host component.

## Local branding

The supplied turtle artwork is kept as a local-only file at `assets/turtle-local.png` and is excluded from Git until its redistribution rights are confirmed. Copy it to `web/static/branding.png` before deployment to use it; the installer carries an existing private copy forward across upgrades. The runtime asset is ignored by Git, and clean/public builds use a neutral fallback mark.

## Server discovery

A non-destructive target inspection was completed before implementation. Existing workloads and remote access must be preserved. No packages or services were changed during discovery. Host-specific inventory is intentionally excluded from this public repository.

## Development status

See [docs/STATUS.md](docs/STATUS.md) for verified progress, known gaps, and the next safe action. This repository is not production-ready; deployment and security acceptance remain outstanding.
