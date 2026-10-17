# Huou07 Playground

Huou07 Playground is a Linux dashboard for monitoring a host, managing coding
workers, and handling owner files. The v0.3.7 production source is implemented in
Rust with a browser interface in HTML, CSS, and JavaScript. The older Python
dashboard remains as a reference and compatibility tool.

## What is included

- Host telemetry, service and application status, and approved app integrations.
- Owner login, worker permissions, policy history, approvals, and Linux ACL
  enforcement.
- Managed worker launch and isolation controls.
- Private NAS and host Storage operations with bounded previews and transfers.
- Optional credential monitoring and reviewed cleanup tools.
- Debian package installation, update, rollback, repair, and data-retaining
  removal.

See [current implementation coverage](docs/IMPLEMENTATION.md), the
[architecture](docs/ARCHITECTURE.md), and the
[security boundaries and limitations](docs/SECURITY.md).

## Source and production provenance

The owner identifies the running production application as v0.3.7. On 2026-10-17,
read-only inspection found the active release label `0.3.7-acl-inherit-fix`; the
dashboard service was running and `/api/health` returned `{"ok":true}`. That API
does not report a version. The deployed binary SHA-256 and source-tree comparison
are recorded in the [sanitized provenance map](docs/evidence/production-v0.3.7-source-provenance.md).

The public `main` branch had not received the production implementation. The
first-party source was on the existing `codex/h07p-product` branch; this sync
preserves the existing repository history and documents the verified source
relationship. Production configuration, credentials, private files, and external
applications are not part of this repository.

## Build and check

The Rust workspace pins its toolchain and dependencies. From a clean Linux
checkout, use the commands documented in [validation](docs/VALIDATION.md) and
the [package guide](deploy/package/README.md). The hosted CI workflow is the
authoritative source-check lane. Do not treat a production health check as a
build or test result.

## Configuration and operations

The package supplies non-secret defaults and reads owner-specific settings from
the system configuration directory. Supply credentials through owner-controlled
files with restricted permissions; never commit actual values. Install and update
the versioned Debian package using the [package guide](deploy/package/README.md),
which also documents rollback and retained-data behavior.

Playground integrates with externally installed harnesses and web applications.
Those applications, their databases, provider credentials, and their runtime
configuration remain separately managed dependencies.

## License

GPL-3.0. See [LICENSE](LICENSE) and the retained third-party asset notices.
