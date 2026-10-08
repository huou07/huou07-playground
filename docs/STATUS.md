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
- Built a responsive dashboard with live Linux hardware/network metrics, read-only systemd service status, and a searchable/sortable process table. Process command arguments are not returned. The supplied turtle remains local-only pending license confirmation.
- Added a Debian/systemd installer and removal script. The unit uses a dedicated unprivileged account, read-only system paths, and binds to IPv4 loopback. It leaves firewall, SSH, VPN, and proxy configuration untouched.
- Installed Cockpit 368 from Debian 13 backports as the upstream SSH terminal and system-management interface. Its systemd socket is bound only to loopback; the dashboard reports its socket state and links to it. The dashboard does not proxy Cockpit or run it under the dashboard account.
- Added a root-owned application registry with HTTP(S) links, optional bounded GET/HEAD health checks, and a responsive dashboard card view. Health probe URLs remain server-side, upgrades preserve the registry, and no credentials belong in this file. The registry is currently empty on the target.
- Upgrades preserve the local-only turtle branding file from earlier releases without committing that asset to the public repository.
- Added backup and restore for the current private state (the application registry and optional local turtle image). Archives are stored outside the repository with owner-only permissions; the restore validates archive members and app URLs before replacing state.

## Verification
Verified locally: `make check` passes (11 standard-library tests); this includes backup/restore round-trip and rejection of unexpected paths, symlinks, and invalid app URLs. Actual Linux probes confirm CPU frequency, temperature, core counts, memory, storage, swap/ZRAM and network data are read without privileged access. Playwright inspected desktop (1600×900), phone portrait (390×844), and landscape (844×390) layouts, including live hardware, systemd and process data from the target. Process search, sorting, mobile representation, no-horizontal-overflow, dark/light persistence, the registry empty state and an app card were verified. The live mobile browser loaded the preserved turtle asset and had no console errors after the latest install. Cockpit's login page loaded through the SSH tunnel and presented its credential form; the expected pre-authentication 401 was observed. A credential-authenticated session is OWNER SETUP REQUIRED and has not been verified. A stale-sample probe confirmed CPU, network and process rates return to unavailable after a long polling gap. The installed systemd units passed `systemd-analyze verify`; health, metrics, process, service, Cockpit and app registry APIs responded. Both management listeners are loopback-only. The dashboard service account cannot write `/etc`, the app code or `/root`, and it has no sudo permission. The existing VPN service and active firewall remained active. Installed API response medians were 3.3 ms for metrics, 23.9 ms for process data and 41.6 ms for service listing in a five-sample check. Gitleaks found no staged or committed secret findings.

## Deployment state
Installed and running as a loopback-only systemd service on the target from source commit `f8e9dcbe9c2f93b8df3274cf2aa208ed0d3cf5f4`. Cockpit `368-1~bpo13+1` is installed on loopback through Debian backports. Private remote use is available through SSH tunnels only, per owner preference; Tailscale Serve was not enabled. Cockpit login needs a valid Linux account credential and remains owner setup. The existing remote-access service remains active as recovery access. The local turtle image is installed from the user's local file and is not part of the public repository. The target app registry currently has zero entries. A live backup-and-restore round-trip succeeded; the archive was root-owned mode `0600` and contained only the registry and branding image.

## Remaining work
- Continue implementation in small verified units and scan staged files/history for secrets before each push.
- Populate the private application registry with browser-reachable URLs and confirmed health checks for supported existing services; the app URLs must be reachable from each client through its own SSH forwards.
- Verify Cockpit browser login with an owner-provided Linux account credential; integrate supported AI/gateway interfaces and an enforced agent isolation boundary.
- Do not deploy DeepSeek Harness yet. Its current upstream safety notice describes it as developer-preview software without a security audit. Public upstream reports from October 6–7, 2026 describe a caller-selected workspace root that can defeat file confinement and access to the Harness credential store from confined commands. Review/fix status is unverified; an isolated runtime and negative boundary tests are prerequisites. References: [upstream safety notice](https://github.com/deepseek-ai/deepseek-harness/blob/master/SAFETY.md), [workspace-root report](https://github.com/deepseek-ai/deepseek-harness/discussions/9026), and [control-plane/credential report](https://github.com/deepseek-ai/deepseek-harness/discussions/8887).
- Current OmniRoute requires Node.js 22.22.2 or newer while the target currently has Node.js 20; do not replace the host Node runtime without reviewing its existing consumers. LiteLLM virtual-key and usage features need an isolated PostgreSQL database and owner-controlled master/salt keys. Neither gateway has been installed or configured.
- OpenCode and Codex CLI are not installed. Native provider credentials and subscription login remain owner actions. GPU telemetry, CPU package power, wg-easy integration, backup/restore, and real DSH/OpenCode/Codex/LiteLLM/OmniRoute client flows remain unverified or unavailable. Real remote-client VPN handshake and credential-dependent AI tests require owner-side setup. Do not enable Tailscale Serve; the owner chose SSH tunnels only.
- A rootless Podman install was simulated with 19 new packages and no upgrades/removals; the actual install could not proceed because the SSH session's non-interactive sudo requires an administrator password. No package change occurred. Bubblewrap is already present, but the DSH API/workspace boundary still needs a tested, enforced design before using it as the sole isolation layer.

## Next useful action
Continue building the credential-independent AI runtime boundary; keep SSH tunnel access unchanged. Ask the owner for an interactive administrator step only when the Podman install is ready to run.
