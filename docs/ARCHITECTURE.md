# Target architecture

## Current and chosen direction

The inspected baseline is Python stdlib HTTPServer plus static HTML/CSS/JS.
Rust has not yet been implemented. Preserve static assets and migrate backend
behavior in slices with parity fixtures. Existing third-party apps remain external
integrations, not rewritten services.

Use Rust with Tokio, Axum, Tower/tower-http, Serde and tracing as the initial
backend candidates. Choose supported versions and pin Cargo.lock when implemented.
Use SQLite for durable policy revisions, approvals, redacted audit and file job
metadata; choose one maintained Rust binding then. Files remain ordinary filesystem
objects. Never put NAS bytes or credentials in a database/cache. Do not introduce
PostgreSQL, microservices or a queue without a measured requirement.

## Process boundaries

| Component | Identity and responsibility |
| --- | --- |
| Static UI / dashboard API | Unprivileged dashboard account; telemetry and owner-authenticated API orchestration |
| Policy administrator | Owner-authenticated control service; authoritative policy and approvals, outside worker-writable trees |
| Sandbox helper | Minimal typed operations to start/stop managed worker cgroups and apply compiled policy; privileged only where unavoidable |
| NAS / host file adapter | Owner/data service identity; no worker access to its sockets, credentials or content |
| Worker launcher / agent | Restricted agents-worker identity; workspace access, scoped broker requests, no administrative capability |

These are trust boundaries, not a requirement for one daemon per table row.
Start with one unprivileged Rust application and a minimal separately protected
helper where OS privilege demands it; NAS must not share the worker UID.
Authenticate owner sessions using an established maintained implementation.
A VPN/loopback listener and an Origin header are not owner authentication.
Keep owner-only API state and session material out of telemetry/worker endpoints.
Authorize every request; deny before metadata or preview reads. Helper IPC checks
kernel peer credentials and a narrow authenticated protocol; never accept command
strings, arbitrary systemd unit text or shell fragments from a request.

Worker binaries, launcher, policy DB, unit configuration, helper and all writable
ancestor paths must be outside worker control. A worker's edited checkout must
never be used as the privileged installed executable. Prevent connections to owner
APIs by both authentication and namespace/socket exposure controls.

## Suggested Rust workspace (create when implemented)

- crates/policy: pure typed rules, operation mapping, conflict decisions, revision.
- crates/platform-linux: capability probes and enforcement compiler/adapters.
- crates/server: API, owner sessions, telemetry, file job orchestration.
- crates/helper: narrow privileged IPC, only if integration proves it necessary.
- web/static: preserved UI; split readable modules by feature as each is touched.
- tests/fixtures and tests/integration: synthetic data and OS boundary scenarios.

Avoid empty crates and speculative traits. Add a boundary when the first real
caller needs it. Keep the policy evaluator independent of HTTP and privileged code.
Use typed errors for denied, approval-required, unavailable and unsupported;
API errors must not reveal a sensitive filename or value to unauthorized callers.

## OS enforcement and change application

Managed worker launches compile policy into namespaces/mount exposure, DAC where
appropriate, systemd restrictions, no_new_privs and optional Landlock.
Runtime libraries, toolchains and designated workspace are explicitly mapped;
system services, sockets, host homes and NAS are absent unless permitted.
Probe actual ABI and namespace availability; fail launch if required guarantees
cannot be enforced. Landlock adds restrictions and cannot itself relax a running
sandbox; systemd path protection alone is not a complete read/execute policy.

A desired revision is persisted, validated, then applied to the managed process
tree. Never display Enforced until all affected processes use that revision.
For revocation, stop the complete cgroup, close broker handles and recreate it.
A restart requirement or failed application is visible and recoverable; an old
running process is not protected merely because the new DB revision exists.
Existing unmanaged workers require owner migration, not automatic host changes.

## Caching, latency and energy

First use bounded in-process TTL/single-flight caches for non-sensitive telemetry
and app health, with timestamps and stale/error states. Collect on demand or with
low-frequency shared collectors; request count must not multiply sampling work.
Use streaming transfers, pagination and bounded blocking work off the async executor.
UI polling is scoped to visible views, stops when hidden, avoids overlap and
backs off on failures. Preserve configurable refresh intervals.

Redis is optional. Do not reuse another application's Redis or assume its presence
makes it safe. Add it only if multiple processes need shared non-sensitive cached
data and CI comparison shows lower p95 latency or resource use after including
Redis memory, CPU, wakeups and writes. Keep a working no-Redis path, bounded TTL,
private connectivity and explicit license/version choice. Policy decisions and
revocations always consult authoritative current state; no stale allow cache.

No CPU governor, swap, GPU, filesystem or power-management host changes are part
of optimization. Measure product idle/open/transfer cost before changing architecture.
CPU package energy is not whole-machine electricity; CI cannot establish target-host
watts. Hardware energy acceptance awaits owner-authorized measurement.

## Migration and rollback

Port health/static routes and safe read APIs first, then sessions/policy, OS
enforcement, NAS/Storage and remaining parity. Preserve old behavior fixtures;
security-sensitive routes may intentionally change only with a documented contract.
Keep the Python reference executable in CI until replacement parity passes.
No dual production listener or automated switch on the owner's host.
Use schema versions, atomic migrations with backup/restore and stable .deb data paths.
Only delete legacy source once its replacement has evidence and rollback is recorded.
