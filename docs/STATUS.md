# Project status

## Objective
Build huou07 playground as a private, single-user Linux workspace on the existing Linux server while preserving existing services and private remote access.

## Repository
- Remote: `https://github.com/huou07/huou07-playground`
- Default branch: `main`
- Initial commit inspected: `524ff98a82a44c4897a0bf8996a00cc16e2e5c6d`
- Existing license: GPL-3.0 text; confirm project licensing before distribution.

## Architecture decision
The reference calls for a compact, custom personal dashboard. The portal starts as a small Python standard-library HTTP server serving static HTML/CSS/JS and read-only Linux metrics over a single-threaded, loopback-only HTTP listener, with no frontend or backend package dependencies. Applications remain separate services. No privileged host operations or credentials are exposed by the initial API.

## Completed
- Inspected the public repository and completed read-only access and platform discovery on the intended server while retaining SSH host-key verification.
- Discovery confirmed that existing containers, services, VPN connectivity, and swap must be preserved. Host-specific inventory is excluded from this public repository. No system changes were made.
- The optional host integrations still require a full compatibility review before deployment.
- Built a responsive dashboard with live Linux hardware/network metrics, read-only systemd service status, and a searchable/sortable process table. Process command arguments are not returned. The supplied turtle remains local-only pending license confirmation.
- Added a Debian/systemd installer and removal script. The unit uses a dedicated unprivileged account, read-only system paths, and binds to IPv4 loopback. It leaves firewall, SSH, VPN, and proxy configuration untouched.

## Verification
Verified: `make check` passes (5 standard-library tests); actual Linux probes confirm CPU frequency, temperature, core counts, memory, storage, swap/ZRAM and network data are read without privileged access. Playwright inspected desktop (1600×900), phone portrait (390×844), and landscape (844×390) layouts, including live hardware, systemd and process data from the target. Process search, sorting, mobile representation, and no-horizontal-overflow were verified. The browser console was clear after fixes. Theme persistence and mobile menu keyboard dismissal passed. A stale-sample probe confirmed CPU, network and process rates return to unavailable after a long polling gap. The installed systemd unit passed `systemd-analyze verify`; health, metrics, process and service APIs all responded. The listener is loopback-only, the service account cannot write `/etc`, the app code or `/root`, and it has no sudo permission. The existing VPN service and active firewall remained active. Installed API response medians were 3.3 ms for metrics, 23.9 ms for process data and 41.6 ms for service listing in a five-sample check. Gitleaks found no staged or committed secret findings.

## Deployment state
Installed and running as a loopback-only systemd service on the target from source commit `e32a90dafb546a042969036aaac89318221a7113`. Private remote use is available through an SSH tunnel; direct browser access over the VPN still needs an access-control design and verification. The existing remote-access service remains active as recovery access. The local turtle image is installed from the user's local file and is not part of the public repository.

## Remaining work
- Continue implementation in small verified units and scan staged files/history for secrets before each push.
- Inspect existing Compose definitions, reverse proxy, firewall/network policy, systemd units, storage, and available hardware telemetry without printing credentials or private configuration into public artifacts.
- Add controlled service management/log access through a mature authenticated integration, SSH through Cockpit or another verified upstream, application registry/health checks, VPN/wg-easy only after compatibility and end-to-end review, supported AI/gateway integrations, installation/upgrade/backup/uninstall, and enforced agent isolation.
- Add authenticated private-network browser access after reviewing the existing VPN policy and a rollback path. Real remote-client VPN handshake and credential-dependent AI tests require owner-side access/setup.

## Next useful action
Continue with a private-network access design that does not expose management surfaces publicly.
