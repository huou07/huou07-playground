# Production architecture

Huou07 Playground v0.3.7 uses one Rust server and a static browser UI. Rust
modules own HTTP/API handling, telemetry, helper IPC, worker policy, file access,
and app integrations. Static assets are under `web/static/`. Python sources and
tests remain as compatibility/reference tooling; they are not the active
dashboard backend.

## Runtime boundaries

| Component | Responsibility and boundary |
| --- | --- |
| Dashboard server | Serves the UI and APIs as an unprivileged system service; authenticates owner requests and bounds telemetry/file work. |
| Typed helper | Performs narrowly typed privileged operations after checking the local peer and request; it does not accept shell commands from HTTP. |
| Managed worker launcher | Drops to the selected worker identity, clears supplementary groups and inherited descriptors, sets no-new-privileges, and applies supported OS restrictions. |
| Broker | Handles explicit, scoped worker file requests and single-use owner approvals; it is separate from direct filesystem permissions. |
| File service | Performs owner-authorized NAS/Storage operations with descriptor-relative paths, bounded streams, and atomic replacement. |
| Browser UI | Presents owner sessions, policy controls, approvals, detection, files and monitoring; UI controls do not replace OS enforcement. |

The helper, policy data, installed binaries, system units, owner sessions, and
NAS storage are protected from worker modification. Worker policies use Linux
DAC/ACLs and process restrictions; Landlock is used where available and required
by the selected mode. Unsupported guarantees must be reported instead of
silently widened. The exact rule model and limitations are in
[SECURITY](SECURITY.md).

## Data and external integrations

Sessions and policy/audit metadata are stored locally with restrictive access.
NAS bytes remain ordinary filesystem objects; no credentials or file contents
are placed in a telemetry cache. Uploads stream to a temporary object and
finalize atomically. Transfers and previews have explicit bounds.

Playground can integrate with external harnesses, Cockpit, VPN services, and
selected web applications. Those services, their databases, provider accounts,
and native authentication stores are not Playground source and remain separately
managed. Relays preserve an application's existing authentication behavior;
Playground does not invent credentials for an app without a supported login.

## Configuration and lifecycle

The Debian package provides generic defaults and reads owner configuration from
the system configuration directory. Secret values must be supplied in
owner-controlled files with restricted permissions. Package scripts preserve
owner data and supported existing service state, save rollback snapshots, and
provide update, repair, rollback, and data-retaining removal. See the
[package guide](../deploy/package/README.md) for supported operations.

## Build and performance boundaries

The Rust workspace and lockfile are pinned. Hosted CI runs formatting, Clippy,
unit/source checks, release build, HTTP smoke, browser lanes, and package gates.
The existing cache is bounded and process-local; no external cache is required.
Performance observations must use the same workload and state their coverage.
CPU time or a short host sample does not establish electricity savings.

See the [implementation map](IMPLEMENTATION.md) for component paths and
[validation contract](VALIDATION.md) for exact evidence classes.
