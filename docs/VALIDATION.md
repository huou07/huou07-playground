# Validation and release contract

## Allowed environment

All executable tests/builds/benchmarks/package lifecycle checks run on disposable
GitHub-hosted Linux infrastructure. The owner's Debian machine is not authorized.
Never use a self-hosted runner, SSH into the owner host or invoke deploy scripts
there. Sudo is allowed inside the disposable CI guest. Read-only source/Git review
does not establish runtime behavior.

Current CI: framework structure/routing guard, legacy make check, locked Rust
format/Clippy/test/release/HTTP smoke, and existing Python browser acceptance.
See [IMPLEMENTATION.md](IMPLEMENTATION.md) for source coverage. The browser runner
starts Python, uses a temporary apps registry/fixture app server and intercepts
several APIs; its pass does not prove Rust UI/backend parity or permissions/NAS.
Hosted Ubuntu tests do not establish Debian package or OS isolation acceptance.

## Required gates as slices land

| Change | Gate and evidence |
| --- | --- |
| Framework | Hosted python3 tools/check-framework.py: links/anchors, navigation/router inventory, skill metadata and declared route-case schema; model selection/loading remains unverified |
| Rust baseline | Pinned toolchain: cargo fmt --all -- --check; cargo clippy --workspace --all-targets --locked -- -D warnings; cargo test --workspace --locked; cargo build --workspace --release --locked |
| API parity | Fixture comparisons with Python reference; errors/timeouts and limits included |
| Owner control | Auth/CSRF, replay, worker-to-owner API denial, policy revision conflicts |
| Isolation | Actual managed agents-worker subprocesses and descendants in disposable Debian VM, not mocked syscall results |
| NAS/Storage | File integrity, quota/full disk, path races, cut/copy/paste, partial failures and unauthorized filesystem/API retrieval |
| UX | Existing plus new Playwright journeys, keyboard, 360px/desktop and dark/light screenshot review |
| Dependencies | Locked versions, reviewed origin/license, redacted secret scan, cargo audit/deny with documented exceptions |
| .deb | Reproducible versioned build, lintian, install/upgrade/remove/purge and retained-data checks in disposable Debian VM |
| Release | Passed required gates for exact commit, artifacts/checksums/SBOM, honest notes and known limitations |

Use a disposable Debian VM on a GitHub-hosted runner for full systemd, DAC,
namespace, Landlock and package acceptance; containers alone may miss those.
Detect virtualization/capabilities. Unsupported test environment is an explicit
incomplete gate, never a skip presented as a pass. Supported minimum Debian/kernel
and required ABI are chosen from demonstrated capability tests before first release.
Start with Linux amd64 .deb; other Linux architectures need their own evidence.
Non-Linux platforms remain Coming soon.

## Framework checks and current executable entrypoints

The framework job is independent of product jobs. Its guard reads repository
text only; it does not import application code, start services, install packages
or contact host services. It checks declared routing cases in
[../tools/framework-routing.json](../tools/framework-routing.json); these are
declared positive/subtle/negative/no-skill expectations, not live model
routing results. Validate actual selection and output separately through the
current session loader before claiming discovery or promoting a skill.

Existing hosted entrypoints are `make check`, `make acceptance`, the pinned Rust
commands in [CI](../.github/workflows/ci.yml), and
`bash tests/rust-smoke.sh target/release/h07p-server`. Do not run them locally.
Missing Cargo.lock is a gate failure. Browser acceptance must be extended to a
real Rust backend as each API slice lands; a Python-only pass cannot close P1.

Retain sanitized raw measurements/reports as CI artifacts with source SHA,
workload/toolchain identity, job/run URL, units and sample duration. Link these
from ROADMAP rather than copying result tables into every contract. Publish only
synthetic paths/data; no real credential, NAS or owner host inventories.

## Adversarial fixture matrix

Create fake secrets and private directories inside the CI guest, never copy host
data. Test worker direct list/read/write/create/delete/execute plus forged API,
socket and helper requests. Include escaped paths, symlink/hardlink aliases,
rename/mount races, inherited descriptors, /proc access, open handles during revoke,
forked descendants, approval expiry/replay, stale cache, unsupported operation
combinations, failed policy activation and worker editing policy/launcher parents.
Test all templates and Custom, immutable NAS/admin protection under none, strict
runtime dependencies and balance direct denial plus broker approval.
Run real positive allow cases so a deny-all bug cannot pass.

Private NAS acceptance includes owner login, GUI Block selection of NAS subtree,
actual worker denial, owner upload/preview/download hash match, cut/copy/paste and
continued owner access. No secret values in screenshots, logs or uploaded artifacts.

## Performance and energy

Use identical fixture dataset, workload, runner/guest configuration and sample
duration for Python/Rust comparisons; record commit, toolchain, warm/cold state,
concurrency and raw sanitized measurements. Hosted-runner variance requires
repeats and declared tolerances. Existing PERFORMANCE.md is historical, not CI baseline.

Measure at least idle browser closed, Home open, Permissions/Storage navigation,
directory pagination and streaming upload/download. Record p50/p95 latency,
throughput, peak/RSS memory, CPU time, wakeups if available, storage writes and
background subprocesses. Include helper, collectors and optional Redis, not just
the dashboard PID. Hash-check transfers and assert memory does not grow with file size.
Bound operation concurrency and test cancellation/backpressure.

Initial targets are hypotheses, not achieved values: no overlapping UI requests;
no scanning while idle; zero recurring health subprocesses with no subscribers;
a small-file warm API p95 no worse than reference within declared runner noise;
bounded transfer buffers and no material idle CPU/memory regression. Establish
numeric resource/latency budgets from the first reproducible CI baseline before
accepting optimization claims. A regression needs user benefit and an explicit
tradeoff, not merely cleaner code.

CI can measure CPU cost but cannot prove electricity savings on the owner's machine.
If later authorized, measure joules for fixed work and idle watts over matched
intervals on actual hardware. Distinguish CPU package from whole-machine energy.

## CI trust and publication

Pin actions to reviewed immutable commits. Default GITHUB_TOKEN contents: read;
pull requests never receive release tokens, owner credentials or privileged host
connections. Privileged fixture tests in disposable hosted machines contain no
secrets. Do not use pull_request_target to execute untrusted source.
Future release job alone receives contents: write and runs from a trusted exact
commit after gates; do not run release credentials against arbitrary PR code.
Publish Linux .deb/checksums and source provenance to the existing H07P repository.
This framework change does not create a fake binary release. Installation on the
owner's host remains a separate owner request.
