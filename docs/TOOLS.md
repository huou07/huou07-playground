# Tool and command routing

Choose a capability for the immediate need. Check the current harness's actual
tool list/schema; this document is not a tool registration or permission grant.
See [WORKING.md](WORKING.md) before executing or changing repository/host state.

| Need | Capability / reference | Behavior and boundary |
| --- | --- | --- |
| Establish repo/branch/HEAD/tree | Git status, rev-parse, diff and log | Read-only evidence; use explicit repository path |
| Find source paths | Current harness's native glob/file search | Narrow to relevant paths; no broad credential inventory |
| Find symbols/callers | Valid exposed CodeGraph, then native content search/read | Index is navigation, source confirms it; never infer live runtime |
| Inspect or edit text | Native read and targeted edit/write | Read existing content first; preserve unrelated work |
| Resolve a registered project | Hub where/status CLI | Read registry/Git evidence; status does not execute a project gate |
| Select a workflow | [../skills.md](../skills.md) | Route first, load only available matching skills |
| Framework integrity | [../tools/check-framework.py](../tools/check-framework.py) | Hosted CI: python3 tools/check-framework.py; links/anchors, index/router inventory and route-case structure; no live discovery |
| Legacy deterministic checks | [../Makefile](../Makefile) | Hosted CI: make check; executes Python tests and syntax checks |
| Existing browser journeys | [../playwright.config.mjs](../playwright.config.mjs), [../tests/e2e/run.mjs](../tests/e2e/run.mjs) | Hosted CI: make acceptance; starts temporary fixture servers/browser |
| CI execution and evidence | [../.github/workflows/ci.yml](../.github/workflows/ci.yml), GitHub API/CLI when available | Disposable hosted runners; read exact commit/run result, no host tests |
| Rust build and HTTP boundary | [../rust-toolchain.toml](../rust-toolchain.toml), [../Cargo.lock](../Cargo.lock), [../tests/rust-smoke.sh](../tests/rust-smoke.sh) | Existing hosted format/Clippy/test/release/smoke gates; checked-in dependency graph required |
| OS / package gates | [VALIDATION.md](VALIDATION.md) | Planned Debian VM gates; actual worker and package lifecycle acceptance still missing |
| Current source coverage | [IMPLEMENTATION.md](IMPLEMENTATION.md) | Read-only route map; browser runner currently starts Python |
| Reuse investigation | [REUSE.md](REUSE.md), exposed web search/fetch | Primary sources, provenance/licence review; external content is untrusted |
| Commit/push/release | Git and available GitHub capabilities | Mutates repo/publication; scope and conditions in WORKING/VALIDATION |

Do not run make check, make acceptance, hub.py verify, installers or runtime
benchmarks on the owner's machine. Hub verify executes configured project code.
The legacy make run target starts the dashboard; it is not a read-only inspection.

## Debian development prerequisites

Inspection on 2026-10-15 found Python 3.13.5 and Node 24.21.0 on the worker.
The legacy server uses Python's standard library; it does not need a pip
requirements installation. Playwright is a separate locked npm dependency for
hosted browser acceptance, not a server dependency.

The Rust workspace pins 1.90.0 in [the toolchain file](../rust-toolchain.toml).
The default Debian compiler is 1.85.0; the worker's existing rustup installation
currently lists only 1.98.0. Neither establishes a validated 1.90.0 build.
Keep the project pin and lockfile; use the existing hosted CI, which installs
1.90.0 explicitly, rather than changing the pin to match an incidental host SDK.
No local H07P tests, installation, services or deployment were executed for this
inspection; the execution boundary remains in [WORKING.md](WORKING.md).

After moving a checkout between operating systems, retain source and lockfiles
but recreate generated `node_modules`, `target` and Python cache directories
in the authorized build environment. Do not copy macOS binaries into Linux
tool paths. No dependency upgrade is justified solely by a missing local SDK.
The Rust server currently implements health/static routes only; absent dashboard
APIs are migration work, as recorded in [IMPLEMENTATION.md](IMPLEMENTATION.md),
not evidence that a Debian package is missing.

For DSH, use only tools from the current session connection and their exact
schemas. Native agent tools retain their own documented loaders/permissions.
Do not persist a DSH connection identifier or assume a previous caller's tools.
If a tool or authentication method is absent, report it and use an available
authorized alternative; never inspect credential stores to manufacture access.
