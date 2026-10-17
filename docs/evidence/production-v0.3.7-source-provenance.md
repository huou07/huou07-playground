# Production v0.3.7 source provenance

Inspection date: 2026-10-17. Production inspection was read-only. No credential
values, runtime databases, private files, logs, or environment values were read.

## Runtime identity

The owner identifies the installed application as v0.3.7. The Playground system
service was active, its selected release directory was labeled
`0.3.7-acl-inherit-fix`, and the local health route returned `{"ok":true}`. The
health route does not report a version; the exact version is therefore
owner-reported and corroborated by the active release label, not independently
returned by the service.

The running service executable resolved to the selected release's
`bin/h07p-server`. Its SHA-256 was
`90626d3d4ee21d02f36bd2ed58fa61c10e4cce769931094e338894c96b901d3a`. This records
the installed binary; no production rebuild or binary replacement was attempted.

## Source relationship

The production source checkout was on branch `codex/h07p-product` at
`e6c0103881e7a2af180a6bb819691d871491d49a`, with no untracked files and one
source-file modification. The modified file was
`crates/server/src/helper.rs`. Its production working-tree Git blob was
`387dd51bf23a794c52c6bb876053ed2f39e42623`, identical to the blob for the same
path in commit `9512ccb4e35ff77fa703d63774e29c3f99029476`. That change corrects
default-ACL handling for non-recursive versus recursive rules. The production
working-tree diff also contained documentation changes, which are not part of
the executable source comparison.

The publication branch retains that recovered source with a small CI-driven
maintenance patch in `helper.rs`: Clippy-equivalent condition/borrow cleanups,
test placement, and extracting ACL string rendering over numeric UID fixtures
so hosted tests do not require production account names. Runtime account lookup
remains in the production wrapper. The ACL strings and intended policy behavior
are unchanged; the published helper is therefore not a byte-for-byte copy of
the deployed source blob. No production binary was rebuilt or replaced.

The release directory contains the compiled server and deployment assets, not a
Git checkout. All 12 deployed static UI files matched the files in commit `9512ccb`
by SHA-256. Deployed `gpu.py`, `power.py`, `wg_status.py`, and
`private-services.json` also matched their source paths in that commit. The
packaged Gitleaks configuration matched `deploy/package/gitleaks.toml`. Together
with the exact helper blob match, these comparisons map the deployed first-party
files to the recovered source tree. The four installed Playground/helper/worker
systemd unit files also matched their `deploy/package/*.service` sources by
SHA-256. The active timer templates are mapped under `deploy/systemd/`.

A byte-for-byte server rebuild comparison was not performed; the installed build
used a different recorded Rust toolchain from the currently pinned hosted build.
The binary hash and component/file comparisons establish provenance evidence,
not a reproducible binary claim. The active service loads owner configuration
from paths outside the source tree. Their contents, including authentication
values, were not read.

## Production component to source map

| Production component | First-party source |
| --- | --- |
| Rust dashboard server and API | `crates/server/src/main.rs`, `api.rs`, `telemetry.rs` |
| HTML, CSS, JavaScript, and static assets | `web/static/` |
| Owner authentication and API authorization | `crates/server/src/api.rs` |
| Worker policy, helper IPC, and ACL enforcement | `crates/server/src/helper.rs`, `sandbox.rs`, `broker.rs` |
| Worker launch and lifecycle adapters | `crates/server/src/sandbox.rs`, `worker_setup.rs`, `deploy/package/workers.py`, `deploy/package/*.service` |
| Sensitive-file detection and redaction | `crates/server/src/scan.rs`, `guard.rs`, `redact.rs` |
| Private NAS and host Storage | `crates/server/src/files.rs` |
| Monitoring and application status | `crates/server/src/telemetry.rs` |
| Python telemetry support files packaged beside the server | `deploy/gpu.py`, `power.py`, `wg_status.py`, `private-services.json` |
| VPN/app relays and supported login adapters | `crates/server/src/relays.rs`, `native_proxy.rs`, `vpn_apps.rs`, `app_logins.rs` |
| Debian install, update, rollback, and removal | `deploy/package/`, `tools/build-deb.sh`, `tools/h07p-install.sh` |
| Regression and acceptance coverage | `tests/native/`, `tests/package-*.sh`, `tests/e2e/`, `tests/` |

The public `codex/h07p-product` branch held the recovered implementation while
public `main` still referenced `53a2d7ef4bf2514a42e8830ba27d24387daa6fc9`. No
PR connected the source branch to `main` at the start of this synchronization.
The cause is branch publication: implementation commits were pushed to the
feature branch but had not been merged into the default branch.

## Scope and exclusions

The production installation is an artifact, not the complete source tree. The
source checkout supplies the first-party implementation listed above. External
harnesses, model providers, databases, runtime credentials, user files, host
policy state, and private service configuration are separate and are not
published as Playground source. Existing service configuration remains
owner-managed.

Source presence and production health do not prove every feature journey. This
inspection did not rerun authenticated UI flows, change services or ACLs, build
on the production host, or read production credentials. Hosted PR checks and
their exact source SHA are recorded separately.
