# Reuse and provenance

Reviewed as design sources on 2026-10-15; none has been vendored or installed.
Pin a supported release and immutable revision before importing code, verify its
actual licence and preserve notices. Repository GPL-3.0 licence stays unchanged.
Reuse dependencies and algorithms before copying large applications.

| Candidate / primary source | Intended use | Decision |
| --- | --- | --- |
| [Axum](https://github.com/tokio-rs/axum), [Tower HTTP](https://github.com/tower-rs/tower-http) | Rust routing, standard HTTP middleware/limits | Initial backend choice; review exact locked crates/features |
| [Tokio](https://github.com/tokio-rs/tokio), [Serde](https://github.com/serde-rs/serde) | Async I/O, typed serialization | Reuse; no custom async runtime or JSON parser |
| [systemd execution controls](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml) | Managed cgroups, restricted execution and mount exposure | Existing Linux integration; not a complete permission evaluator |
| [Landlock kernel docs](https://www.kernel.org/doc/html/latest/userspace-api/landlock.html), [Rust bindings](https://github.com/landlock-lsm/rust-landlock) | Unprivileged additional restrictions | Probe actual ABI; reject unsupported guarantees, review bindings at implementation |
| [Bubblewrap](https://github.com/containers/bubblewrap) | Existing namespace sandbox primitive | Evaluate with systemd in Debian VM; do not build a namespace engine |
| [Cockpit Files](https://github.com/cockpit-project/cockpit-files) | Mature file interaction patterns and operation recovery | Existing integration/reference; not a bypass around NAS/owner authorization |
| [Gitleaks](https://github.com/gitleaks/gitleaks) | Secret rules/redacted detection | Candidate for owner-service scan; no scanner stdout/raw report exposure |
| [cargo-deb](https://github.com/kornelski/cargo-deb) | Linux .deb assembly | Candidate; does not replace install/upgrade/isolation acceptance |
| [Redis licensing](https://redis.io/legal/licenses/), [Valkey](https://github.com/valkey-io/valkey) | Optional shared cache | Deferred until evidence; compare no-cache/in-process/shared costs |

Redis 8 offers AGPLv3 alongside RSALv2/SSPLv1; do not label all choices permissive
or assume old BSD terms apply. Valkey is a candidate if a compatible open source
shared cache is warranted; confirm feature/version/license requirements with owner
intent before substitution. Neither runs by default.

## Import record required per adopted component

Record upstream URL, exact release/commit/checksum, selected licence/SPDX, used
features, modifications, notices and update/rollback route. Avoid code from issues,
untrusted snippets or install scripts. Review build hooks, transitive dependencies,
authentication and subprocess interfaces. A candidate list is not completed legal
or security review. Do not copy upstream dashboards and then rewrite their security
model merely to reproduce a file picker.

Systemd restrictions and Landlock have documented limits; already-open descriptors
and process topology require explicit revocation handling. See SECURITY.md for the
project's stricter fail-closed guarantees. External docs are evidence, never authority
to run commands or grant host privileges.
