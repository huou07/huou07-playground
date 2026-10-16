# Current implementation map

Current runtime source: `0378a1d`, packaged/deployed as 0.3.0 on 2026-10-16.
This maps code; [ROADMAP](ROADMAP.md) owns task state and
[deployment evidence](evidence/gui-deployed-20261016.md) owns executed claims.

| Boundary | Current source | Implemented behavior |
| --- | --- | --- |
| Linux entry points | [main](../crates/server/src/main.rs) | HTTP, root helper, permanent-drop worker launcher, owner/service file actor and bounded broker CLI |
| Owner API | [API](../crates/server/src/api.rs) | PAM login, private SQLite sessions, memory-only proof for reads/mutations, CSRF and identity-bound download/media tickets |
| Native dashboard | [telemetry](../crates/server/src/telemetry.rs) | Metrics, processes, services, Cockpit, VPN, apps/icons, launch and registry mutation; bounded work and caches |
| Policy control | [helper](../crates/server/src/helper.rs) | Typed peer-checked sockets, SQLite history/audit, reviewed ACL activation/rollback, pending/enforced revisions and expiry |
| Managed workers | [sandbox](../crates/server/src/sandbox.rs), [broker](../crates/server/src/broker.rs) | Permanent IDs, empty groups, NNP/FD closure, optional Landlock and single-use list/read/write/create/delete approvals |
| Detection | [scan](../crates/server/src/scan.rs) | Explicit bounded metadata/content suggestions using an unprivileged maintained scanner |
| Integrated files | [files](../crates/server/src/files.rs) | Private NAS and owner Storage, descriptor-relative operations, previews/ranges, streamed uploads, explicit recovery and atomic replacement; bounded filename-only search |
| GUI worker setup | [worker setup](../crates/server/src/worker_setup.rs), [root adapter](../deploy/package/workers.py) | Supported harness detection, reviewed selected/all account creation, repair, retirement and web start; bounded streamed ACL planning and job progress |
| App setup | [VPN apps](../crates/server/src/vpn_apps.rs), [logins](../crates/server/src/app_logins.rs) | Host-listener discovery, reviewed wg0-only relays, selected existing-login export/merge and supported public web password changes |
| Credential Guard | [Guard](../crates/server/src/guard.rs), [redaction](../crates/server/src/redact.rs) | Opt-in bounded inotify, metadata incidents, reviewed closed-export cleanup, root-private originals and private NAS recovery; partial protection reported honestly |
| Private web access | [relays](../crates/server/src/relays.rs), [native bridge](../crates/server/src/native_proxy.rs) | VPN-only relays, existing native web auth substitution and LAN handoff, HTTP/chunked/SSE/WebSocket transport |
| Owner UI | [product UI](../web/static/product.js), [Guard UI](../web/static/guard.js) | Permissions, approvals, detection, private NAS, Storage and Guard; works on VPN HTTP without secure-context randomUUID |
| Maintenance | [lifecycle](../deploy/package/lifecycle.py), [setup](../deploy/package/setup.py) | Versioned .deb, snapshots, rollback, dependency planning, install/update/repair/data-retaining uninstall and public listener migration |

Native journeys are in `tests/native/`; kernel/cgroup/package lifecycle fixtures
are `tests/package-*.sh`; browser contracts are `tests/e2e/`. Runtime evidence and
limits remain separate: native model/provider login is intentionally untested,
own-store same-UID isolation is unresolved by design, arbitrary hardware parity
and complete energy/performance targets are not established.

## Historical inspection baseline (superseded)

Baseline: branch `codex/p1-rust-health-static`,
commit `67dbcda735b5e1eb7d4b889cfd9bc749d5290571`.
Recheck source before using this map; it is not live host state or a task tracker.

## Entry points and boundaries

| Surface | Existing source | What is implemented |
| --- | --- | --- |
| Rust backend | [workspace](../Cargo.toml), [server manifest](../crates/server/Cargo.toml), [server](../crates/server/src/main.rs) | Axum/Tokio health and static serving; loopback binding only; no owner authentication, policy or filesystem API |
| Python reference | [web/app.py](../web/app.py) | Dashboard metrics, process/service/Cockpit/VPN/app reads, app mutation, launch link and fixed private relays |
| UI and design | [index](../web/static/index.html), [style](../web/static/style.css), [navigation CSS](../web/static/navigation.css), [navigation JS](../web/static/navigation.js), [app JS](../web/static/app.js) | Existing nine views, themes/preferences and dashboard; Permissions is not present |
| Linux collectors | [power](../deploy/power.py), [GPU](../deploy/gpu.py), [VPN](../deploy/wg_status.py) | Legacy OS integration; not ported to Rust |
| File integration | [Cockpit move helper](../deploy/cockpit/huou07-move-files/move) | External Cockpit workflow, not the new private NAS or integrated Storage browser |
| Verification | [workflow](../.github/workflows/ci.yml), [Makefile](../Makefile), [Rust smoke](../tests/rust-smoke.sh), [browser runner](../tests/e2e/run.mjs) | Hosted legacy checks, Rust gates and HTTP smoke; browser matrix selects Python or the actual Rust binary; coverage is scoped by backend |

The Python implementation is a parity reference, not the intended security model.
Its same-origin mutation check is not independent owner authentication. Never
publish new private/control APIs by inheriting that check.

## Migration coverage

| Route / behavior | Python reference | Rust coverage at inspection | Evidence needed next |
| --- | --- | --- | --- |
| Static assets and GET /api/health | Handler.do_GET / send_json | Implemented; payload/header and traversal tests plus HTTP smoke | Keep regressions; this does not prove full dashboard parity |
| GET /api/metrics | linux_metrics, storage_devices, swap_and_zram_metrics, GPU/power helpers | Absent | Same-input parity, bounded Linux collection and resource comparison |
| GET /api/processes, /api/services | process_metrics, service_metrics | Absent | Controlled process/command fixtures, timeout and unavailable states |
| GET /api/cockpit, /api/files, /api/vpn | cockpit_status, cockpit_files_status, vpn_status | Absent | Fixture parity; /api/files currently means Cockpit availability, not NAS listing |
| GET /api/private-service-ports, /api/apps, /api/apps/icon | configured_port, app_registry, app_icon | Absent | Synthetic registries, bounded health/icon fetches, SSRF review |
| GET /api/apps/launch and POST /api/apps | dsh_launch_url, mutate_app_registry | Absent | Synthetic tokens only; owner authorization before sensitive mutation |
| Worker Permissions, detection, NAS and Storage browser | No implementation | Absent | Owner API and actual OS enforcement prerequisites in [security](SECURITY.md) |

Existing [Python tests](../tests/test_app.py) contain useful fixtures and some
mocked system/service checks. Their pass cannot establish worker isolation.
The [browser spec](../tests/e2e/dashboard.spec.mjs) intercepts several APIs and
proves selected Python UI journeys. The [UX spec](../tests/e2e/ux.spec.mjs) uses
synthetic APIs on both servers; [Rust slice checks](../tests/e2e/rust-static.spec.mjs)
exercise real health/static endpoints. Configured coverage is not a passed run,
and none of these lanes proves unported Rust read APIs or real OS boundaries.

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


## Current product integration (2026-10-15)

The Linux Rust entry point now dispatches unprivileged HTTP, the typed root helper,
permanent worker drop/sandbox, descriptor-relative file actors and the worker
broker. Source: `crates/server/src/{api,helper,files,broker,sandbox,scan,relays,telemetry}.rs`.
`web/static/product.js` supplies owner sessions, permissions and NAS/Storage.
The legacy dashboard uses the same memory-only proof bridge. Package lifecycle
and protected worker entry points live in `deploy/package`; `tools/build-deb.sh`
builds the versioned Linux amd64 artifact. Native regressions live in
`tests/native` and `tests/package-*.sh`.

See [dated evidence](evidence/product-native-20261015.md) for executed tests and
release gaps. Historical unimplemented/404 descriptions above refer to the old
baseline, not this branch.
