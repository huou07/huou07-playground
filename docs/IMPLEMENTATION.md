# Current implementation map

Type: Source reference, inspected 2026-10-15.
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
| Verification | [workflow](../.github/workflows/ci.yml), [Makefile](../Makefile), [Rust smoke](../tests/rust-smoke.sh), [browser runner](../tests/e2e/run.mjs) | Hosted legacy checks, Rust gates and HTTP smoke; browser runner starts Python |

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
The [browser spec](../tests/e2e/dashboard.spec.mjs) also intercepts several APIs;
it proves selected Python UI journeys, not Rust read APIs or real OS boundaries.

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
