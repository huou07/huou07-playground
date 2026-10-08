# huou07 playground

A private, single-user Linux workspace dashboard. The first implementation unit is a responsive home dashboard with live, read-only Linux metrics and clear unavailable states for hardware integrations that are not configured.

## Current implementation

- Compact responsive dashboard with dark default and persisted light theme.
- Live CPU utilization, logical/physical core counts, frequency and temperature where exposed, RAM, root filesystem, swap/ZRAM, host identity, uptime, and physical network byte counters from Linux procfs and sysfs.
- Process owner, PID, CPU and memory data come from procfs. Service state comes from systemd; searches and sorting run in the browser. CPU, process and network rates use successive samples and return to unavailable/sampling states after long gaps.
- GPU and CPU package power report `N/A` until a supported telemetry adapter is available.
- Service and process views are read-only. Authentication, service control/log access, browser terminal, VPN, app registry, and AI tool integration are not implemented yet. Bind the server to loopback until private-network access controls are in place.

## Run locally

Requires Python 3.10+; no third-party Python packages are used.

```sh
make run
```

Open `http://127.0.0.1:8765`. `PORT` can be changed for local development; `HOST` accepts loopback addresses only. The listener cannot be exposed to a LAN or WAN until authentication and private-network access controls exist. The API is read-only: `/api/health` is a liveness check, `/api/metrics` returns hardware/network data, `/api/services` returns systemd states, and `/api/processes` returns a bounded process list without command arguments.

## Install on Debian with systemd

From a trusted checkout on the server, run `sudo ./deploy/install.sh`. It installs the web files under `/opt/huou07-playground`, creates a dedicated unprivileged service account, and starts a loopback-only systemd unit. It does not change firewall, VPN, proxy, or SSH settings. The installer keeps prior releases so the symlink can be switched back if an upgrade fails. To remove the app and its releases, run `sudo ./deploy/uninstall.sh`; the dedicated account is retained.

To open the dashboard from a computer that can SSH to the server, create a local tunnel:

```sh
ssh -L 8765:127.0.0.1:8765 <your-ssh-alias>
```

Then open `http://127.0.0.1:8765` on that computer. This is a private access method over SSH; direct LAN/VPN browser access is not enabled yet. Keep the SSH tunnel running while using the dashboard.

## Local branding

The supplied turtle artwork is kept as a local-only file at `assets/turtle-local.png` and is excluded from Git until its redistribution rights are confirmed. For a local preview, copy it to `web/static/branding.png`; that runtime asset is also ignored by Git. Public builds use a neutral fallback mark.

## Server discovery

A non-destructive target inspection was completed before implementation. Existing workloads and remote access must be preserved. No packages or services were changed during discovery. Host-specific inventory is intentionally excluded from this public repository.

## Development status

See [docs/STATUS.md](docs/STATUS.md) for verified progress, known gaps, and the next safe action. This repository is not production-ready; deployment and security acceptance remain outstanding.
