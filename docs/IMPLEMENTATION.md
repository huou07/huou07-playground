# Current implementation map

This map describes the recovered production v0.3.7 source. The deployed
executable is Rust; the UI is first-party HTML/CSS/JavaScript. The legacy Python
dashboard and its fixtures remain in the repository as compatibility/reference
code. See the [source provenance record](evidence/production-v0.3.7-source-provenance.md)
for the production revision relationship and its evidence limits.

| Boundary | Source | Implemented behavior |
| --- | --- | --- |
| Server and entry points | `crates/server/src/main.rs` | Rust HTTP server, typed helper/worker entry points, service file actor, and bounded broker CLI |
| Owner API | `crates/server/src/api.rs` | PAM-backed sessions, in-memory proof for protected requests, CSRF checks, and scoped download/media tickets |
| Dashboard and telemetry | `crates/server/src/telemetry.rs` | Metrics, process/service status, Cockpit, VPN, apps/icons, launch and registry operations with bounded work and caches |
| Policy and ACL enforcement | `crates/server/src/helper.rs` | Typed peer-checked IPC, policy history/audit, ordered ACL application, private-path protection, exact-file exceptions, impact challenge, revisions, and expiry |
| Worker isolation and approvals | `crates/server/src/sandbox.rs`, `broker.rs` | Worker identity drop, empty groups, no-new-privileges, descriptor closure, optional Landlock, scoped single-use file-operation approvals |
| Worker setup | `crates/server/src/worker_setup.rs`, `deploy/package/workers.py` | Supported harness detection, worker lifecycle, ACL restore/repair, rollback snapshot handling, and bounded job progress |
| Sensitive-file detection | `crates/server/src/scan.rs`, `guard.rs`, `redact.rs` | Bounded metadata/content suggestions, opt-in watches, redacted results, and reviewed closed-export cleanup |
| Private NAS and Storage | `crates/server/src/files.rs` | Descriptor-relative file operations, safe previews/ranges, streamed uploads, atomic replacement, recovery, and filename-only search |
| App integrations | `crates/server/src/relays.rs`, `native_proxy.rs`, `vpn_apps.rs`, `app_logins.rs` | Reviewed VPN-only relays, existing web-auth bridging, host service discovery, and selected supported login export/change |
| Linux telemetry support and timers | `deploy/gpu.py`, `power.py`, `wg_status.py`, `deploy/systemd/huou07-playground-*.{service,timer}` | Python support collectors and scheduled samples used alongside the Rust server |
| UI | `web/static/` | Dashboard, permissions, approvals, detection, NAS, Storage, Guard, navigation, and responsive styling |
| Packaging and lifecycle | `deploy/package/`, `tools/build-deb.sh`, `tools/h07p-install.sh` | Versioned Debian package, dependency checks, protected setup, snapshots, rollback, repair, and data-retaining removal |
| Tests | `tests/` | Rust/Python regressions, native policy/filesystem fixtures, package lifecycle and sandbox fixtures, and browser journeys |

## Evidence limits

- **Implemented in source:** the behaviors in the table are present in the
  recovered source tree.
- **Observed in production:** the active release label, running dashboard
  service, successful health response, executable path, and binary hash were
  inspected read-only. Individual authenticated journeys were not rerun for
  this synchronization.
- **Verified in CI:** report only checks attached to the exact source commit or
  the synchronization PR. Existing runs for later or different revisions do
  not transfer to this source snapshot.
- **Known limits:** same-UID native application stores are not isolated from
  their owner by this product; optional detection is bounded and cannot promise
  discovery of every secret; unsupported filesystem/kernel capabilities fail
  closed or remain explicitly incomplete; external apps retain their own
  authentication and update lifecycle.

The Python implementation is not the active production backend. Keep it as a
reference only where its fixtures or compatibility routes remain useful. No
source entry in this map includes provider credentials, private runtime state,
or third-party application implementations.

Other tracked operator utilities are not installed by the v0.3.7 package and are
not active Playground runtime modules. External service definitions and
host-specific deployment records were excluded from the synchronized tree;
first-party compatibility code and its regression tests remain distinguishable
from the production source mapped above.
