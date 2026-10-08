# Project status

## Objective
Build huou07 playground as a private, single-user Linux workspace on the existing Linux server while preserving existing services and private remote access.

## Repository
- Remote: `https://github.com/huou07/huou07-playground`
- Default branch: `main`
- Last pushed implementation commit: `af83d6c0c5a6dd506f4c9214f12ebeeafd750cbf`
- Initial commit inspected: `524ff98a82a44c4897a0bf8996a00cc16e2e5c6d`
- Existing license: GPL-3.0 text; confirm project licensing before distribution.

## Architecture decision
The reference calls for a compact, custom personal dashboard. The portal starts as a small Python standard-library HTTP server serving static HTML/CSS/JS and read-only Linux metrics over a single-threaded, loopback-only HTTP listener, with no frontend or backend package dependencies. Applications remain separate services. No privileged host operations or credentials are exposed by the initial API.

## Completed
- Inspected the public repository and completed read-only access and platform discovery on the intended server while retaining SSH host-key verification.
- Discovery confirmed that existing containers, services, VPN connectivity, and swap must be preserved. Host-specific inventory is excluded from this public repository. No system changes were made.
- The optional host integrations still require a full compatibility review before deployment.
- Built the first responsive dashboard slice and Linux read-only metrics endpoint. The supplied turtle is local-only pending license confirmation.

## Verification
Verified: `make check` passes (4 standard-library tests); the actual Linux probe also confirms CPU frequency and temperature fields are read without privileged access; the health and static routes return successfully; a temporary probe ran the metrics collector on the actual Linux host and validated the Linux metrics payload; Gitleaks found no staged secret findings; Playwright inspected desktop (1600×900), phone portrait (390×844), and landscape (844×390) layouts. The browser console was clear after fixes. Theme persistence and mobile menu keyboard dismissal passed.

## Deployment state
Not deployed. Existing service inventory and network bindings need a more complete private review before choosing a bind address, proxy integration, or installation method. Preserve the existing private remote-access path as recovery access.

## Remaining work
- Continue implementation in small verified units and scan staged files/history for secrets before each push.
- Inspect existing Compose definitions, reverse proxy, firewall/network policy, systemd units, storage, and available hardware telemetry without printing credentials or private configuration into public artifacts.
- Implement safe service/process inspection, SSH through a reused mature integration, app registry and health checks, VPN/wg-easy only after compatibility and port review, supported AI/gateway integrations, install/upgrade/backup/uninstall, and security boundaries.
- Deploy and verify on actual hardware only after the configuration plan and rollback path are concrete. Real remote-client VPN handshake and credential-dependent AI tests require owner-side access/setup.

## Next useful action
Commit and push the verified CPU telemetry update, then finish the private container, firewall, process, and access-path review before designing any installation changes.
