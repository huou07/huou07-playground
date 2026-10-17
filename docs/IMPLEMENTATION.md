# Current implementation map

Source identity: `codex/h07p-product` at the merge of `origin/codex/h07p-product`
(`9b89914a`). The tables below describe what the source on this branch implements;
[ROADMAP.md](ROADMAP.md) owns task state and executed evidence, and dated runtime
claims live in [docs/evidence/](evidence/).

The 2026-10-15 inspection baseline that described Permissions, Auto Detect, private
NAS and Storage as absent was written against branch `codex/p1-rust-health-static`
at `67dbcda7` and contradicted the implemented product. It is removed rather than
kept as a second, contradictory "current" map; its dated observations remain in
[AUDIT-2026-10-15.md](AUDIT-2026-10-15.md) and
[evidence/product-native-20261015.md](evidence/product-native-20261015.md).

| Boundary | Current source | Implemented behavior |
| --- | --- | --- |
| Linux entry points | [main](../crates/server/src/main.rs) | HTTP, root helper, permanent-drop worker launcher, owner/service file actor and bounded broker CLI |
| Owner API | [API](../crates/server/src/api.rs) | PAM login, private SQLite sessions, memory-only proof for reads/mutations, CSRF and identity-bound download/media tickets |
| Native dashboard | [telemetry](../crates/server/src/telemetry.rs) | Metrics, processes, services, Cockpit, VPN, apps/icons, launch and registry mutation; bounded work and caches |
| Policy control | [helper](../crates/server/src/helper.rs) | Typed peer-checked sockets, SQLite history/audit, unrestricted absolute targets/workspaces, block-last ACL activation, exact-file private exceptions, two-click impact challenge, pending/enforced revisions and expiry |
| Managed workers | [sandbox](../crates/server/src/sandbox.rs), [broker](../crates/server/src/broker.rs) | Permanent IDs, empty groups, NNP/FD closure, optional Landlock and single-use list/read/write/create/delete approvals |
| Detection | [scan](../crates/server/src/scan.rs), [registry](../crates/server/src/sensitive.rs) | Versioned sensitive-location registry, bounded metadata/content suggestions for any canonical absolute file/directory including hidden paths, fail-closed scanner self-test, explicit confidence/reason, redacted results |
| Integrated files | [files](../crates/server/src/files.rs) | Private NAS and owner Storage, descriptor-relative operations, previews/ranges, streamed uploads, explicit recovery and atomic replacement; bounded filename-only search |
| GUI worker setup | [worker setup](../crates/server/src/worker_setup.rs), [root adapter](../deploy/package/workers.py) | Supported harness detection, validated pre-worker ACL snapshot registry, GUI restore with rollback snapshot, stale-path filtering and restore dry-run, repair, retirement and web start; bounded streamed ACL planning and job progress |
| App setup | [VPN apps](../crates/server/src/vpn_apps.rs), [logins](../crates/server/src/app_logins.rs) | Host-listener discovery, reviewed wg0-only relays, selected existing-login export/merge and supported public web password changes |
| Credential Guard | [Guard](../crates/server/src/guard.rs), [redaction](../crates/server/src/redact.rs) | Opt-in bounded inotify over owner-selected canonical host paths, metadata incidents, reviewed owner-owned closed-export cleanup, root-private originals and private NAS recovery; partial protection reported honestly |
| Private web access | [relays](../crates/server/src/relays.rs), [native bridge](../crates/server/src/native_proxy.rs) | VPN-only relays, existing native web auth substitution and LAN handoff, HTTP/chunked/SSE/WebSocket transport |
| Owner UI | [product UI](../web/static/product.js), [Guard UI](../web/static/guard.js) | Permissions, approvals, detection, private NAS, Storage and Guard; works on VPN HTTP without secure-context randomUUID |
| Maintenance | [lifecycle](../deploy/package/lifecycle.py), [setup](../deploy/package/setup.py) | Versioned .deb, snapshots, rollback, dependency planning, install/update/repair/data-retaining uninstall and public listener migration |

Python `web/app.py` remains the preserved reference for the legacy dashboard and is
not the security model: its same-origin mutation check is not independent owner
authentication, and new private/control APIs must not inherit it.

Native journeys are in `tests/native/`; kernel/cgroup/package lifecycle fixtures
are `tests/package-*.sh`; browser contracts are `tests/e2e/`. Runtime evidence and
limits remain separate: native model/provider login is intentionally untested,
own-store same-UID isolation is unresolved by design, arbitrary hardware parity
and complete energy/performance targets are not established.

## Inspect only the surface needed

For metrics work, start with `web/app.py:linux_metrics` and its helper functions,
the corresponding Python tests, `web/static/app.js:paint`, and the Rust server.
Supply synthetic proc/sys data, clock/counter samples and command results to both
implementations. Production fixture injection must never be a public path parameter.
Compare absent/malformed/denied data, first and later samples, reset counters,
null values, units and rounding. Use tolerances only for declared nondeterministic
fields. Test a real Rust HTTP response and render it in the preserved UI; intercepted
browser responses alone cannot prove that path.

[ROADMAP.md](ROADMAP.md) owns remaining work and source/run evidence.
[ARCHITECTURE.md](ARCHITECTURE.md) owns proposed boundaries;
[AUDIT-2026-10-15.md](AUDIT-2026-10-15.md) retains the earlier source audit.

## Current product integration

The Linux Rust entry point dispatches unprivileged HTTP, the typed root helper,
permanent worker drop/sandbox, descriptor-relative file actors and the worker
broker. Source: `crates/server/src/{api,helper,files,broker,sandbox,scan,sensitive,guard,relays,native_proxy,telemetry,worker_setup}.rs`.
`web/static/product.js` supplies owner sessions, permissions and NAS/Storage.
The legacy dashboard uses the same memory-only proof bridge. Package lifecycle
and protected worker entry points live in `deploy/package`; `tools/build-deb.sh`
builds the versioned Linux amd64 artifact. Native regressions live in
`tests/native` and `tests/package-*.sh`.

See [dated evidence](evidence/product-native-20261015.md) for executed tests and
release gaps.
