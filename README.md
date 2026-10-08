# huou07 playground

A private, single-user Linux workspace dashboard. The first implementation unit is a responsive home dashboard with live, read-only Linux metrics and clear unavailable states for hardware integrations that are not configured.

## Current implementation

- Compact responsive dashboard with dark default and persisted light theme.
- Live CPU utilization, logical/physical core counts, frequency and temperature where exposed, RAM, root filesystem, swap/ZRAM, host identity, uptime, and physical network byte counters from Linux procfs and sysfs.
- Process owner, PID, CPU and memory data come from procfs. Service state comes from systemd; searches and sorting run in the browser. CPU, process and network rates use successive samples and return to unavailable/sampling states after long gaps.
- GPU and CPU package power report `N/A` until a supported telemetry adapter is available.
- Service and process views are read-only. Cockpit provides a separate browser terminal and host management UI. Applications can be listed in a root-owned server registry with optional bounded health checks. Direct browser access stays disabled; use SSH tunnels.

## Run locally

Requires Python 3.10+; no third-party Python packages are used.

```sh
make run
```

Open `http://127.0.0.1:8765`. `PORT` can be changed for local development; `HOST` accepts loopback addresses only. The listener cannot be exposed to a LAN or WAN until authentication and private-network access controls exist. The API is read-only: `/api/health` is a liveness check, `/api/metrics` returns hardware/network data, `/api/services` returns systemd states, and `/api/processes` returns a bounded process list without command arguments.

### Application registry

On the server, edit `/etc/huou07-playground/apps.json` to add links. The installer seeds this file from [`config/apps.example.json`](config/apps.example.json) once and preserves it on upgrades. Keep this file root-owned and out of Git; do not put credentials or tokens in it. Example:

```json
{
  "apps": [
    {
      "name": "Example app",
      "url": "http://127.0.0.1:3000/",
      "description": "A short note",
      "category": "Tools",
      "health_url": "http://127.0.0.1:3000/health",
      "health_method": "GET"
    }
  ]
}
```

Only `name` and `url` are required. URLs must use HTTP or HTTPS. The app link opens in your browser, so its URL must be reachable from that device. For a loopback-only app, add its port to your SSH tunnel and use the forwarded `127.0.0.1` URL. Optional health checks run from the server using GET or HEAD, do not follow redirects, and have a one-second timeout; the probe URL stays server-side and is not returned to the browser. Entries without a health URL display as “Not monitored.” `/api/apps` returns up to 20 validated entries and does not provide app credentials or control actions.

## Install on Debian with systemd

From a trusted checkout on the server, run `sudo ./deploy/install.sh`. It installs the web files under `/opt/huou07-playground`, creates a dedicated unprivileged service account, and starts a loopback-only systemd unit. It does not change firewall, VPN, proxy, or SSH settings. The installer keeps prior releases so the symlink can be switched back if an upgrade fails. To remove the app and its releases, run `sudo ./deploy/uninstall.sh`; the dedicated account is retained.

To open the dashboard from a computer that can SSH to the server, create a local tunnel:

```sh
ssh -L 8765:127.0.0.1:8765 -L 9090:127.0.0.1:9090 <your-ssh-alias>
```

Then open `http://127.0.0.1:8765` on that computer. This is a private access method over SSH; direct LAN/VPN browser access is not enabled yet. Keep the SSH tunnel running while using the dashboard.

## Optional SSH terminal and system management

On Debian 13 with its official backports repository enabled, run `sudo ./deploy/install-cockpit.sh`. The script requires Cockpit 368 or newer, simulates the package plan, refuses removals, and configures the systemd socket to listen only on `127.0.0.1:9090`. Cockpit is a separate, powerful host-management application; it does not run inside the dashboard's restricted service account. Its web login requires a valid Linux account credential. Do not enable SSH password login just to make Cockpit work. The dashboard shows Cockpit's state and links to it when its socket is active. The tunnel command above forwards both private loopback services. The browser uses Cockpit's local HTTP mode over the encrypted SSH tunnel.

The backport version floor avoids older releases affected by known security issues: [Cockpit 360 security fix](https://cockpit-project.org/blog/cockpit-360.html), [Debian Cockpit backports](https://tracker.debian.org/pkg/cockpit/news/), and [Cockpit loopback/TLS behavior](https://docs.cockpit-project.org/cockpit-guide/main/guide/https.html). The dashboard uninstall script intentionally leaves Cockpit installed because it is an independently managed host component.

## Local branding

The supplied turtle artwork is kept as a local-only file at `assets/turtle-local.png` and is excluded from Git until its redistribution rights are confirmed. Copy it to `web/static/branding.png` before deployment to use it; the installer carries an existing private copy forward across upgrades. The runtime asset is ignored by Git, and clean/public builds use a neutral fallback mark.

## Server discovery

A non-destructive target inspection was completed before implementation. Existing workloads and remote access must be preserved. No packages or services were changed during discovery. Host-specific inventory is intentionally excluded from this public repository.

## Development status

See [docs/STATUS.md](docs/STATUS.md) for verified progress, known gaps, and the next safe action. This repository is not production-ready; deployment and security acceptance remain outstanding.
