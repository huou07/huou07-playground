# Validation and release contract

## Execution boundary

Production may be inspected only within the current request's read-only scope.
Do not run builds, tests, installers, benchmarks, migrations, deployments, service
restarts, or policy changes on the production host. Do not access credentials,
authentication state, private files, or NAS contents. Use disposable hosted
runners for source checks and disposable Linux guests for OS/package acceptance.

Production observations, source tests, browser assertions, CI results, and owner
acceptance are distinct evidence. A passing health route does not prove API
parity, authenticated behavior, or isolation. Every result must name the exact
source SHA and environment; unsupported capabilities are incomplete rather than
passed.

## Existing source and browser lanes

The CI workflow runs the framework guard, legacy Python/shell checks, pinned Rust
formatting/Clippy/tests/release build/HTTP smoke, and separate Python and Rust
browser lanes. `make acceptance` starts temporary fixture services. Browser lanes
exercise the backend selected by the runner; intercepted APIs do not prove that
the actual Rust server implements the intercepted behavior.

Useful entry points in the hosted CI environment:

- `python3 tools/check-framework.py`
- `make check`
- `make acceptance`
- `cargo fmt --all -- --check`
- `cargo clippy --workspace --all-targets --locked -- -D warnings`
- `cargo test --workspace --locked`
- `cargo build --workspace --release --locked`
- `bash tests/rust-smoke.sh target/release/h07p-server`

## Product acceptance

When product changes touch a boundary, exercise representative owner journeys
with synthetic data: login/CSRF, worker policy conflicts and expiry, direct OS
allow/deny behavior, worker-to-owner API denial, NAS/Storage integrity and
recovery, bounded previews/transfers, and existing UI navigation. Include
positive access cases so a deny-all implementation cannot pass. Never use real
credentials, NAS content, or owner files as fixtures.

Isolation acceptance needs real worker processes and descendants in an
appropriate disposable Debian environment. Test DAC/ACL behavior, helper/IPC
authorization, inherited descriptors, symlink and path races, revocation,
cgroups, namespace/Landlock capability failures, and package lifecycle. A
container or a mocked syscall result is not OS isolation evidence. The checked-in
package lifecycle fixture is not a complete systemd installation test.

## Dependencies, packaging, and release

Use the checked-in lockfiles and pinned toolchain. Review dependency origin and
license, run redacted secret scanning, and retain source/run identity with
sanitized audit artifacts. Release CI must rerun required gates for the exact
tag, audit the dependency graph, build repeat packages, verify hashes and
Lintian, and execute package lifecycle fixtures. Do not claim reproducibility
from a single build or byte-identical production binaries without a comparison.

Tagging `vX.Y.Z` invokes the configured release workflow. Its package lifecycle
lane does not replace a disposable Debian system installation and worker
isolation test. Do not weaken required gates to publish.

## CI trust and privacy

Pin third-party actions to reviewed immutable commits. Use read-only default
workflow token permissions; untrusted pull requests must not receive release
credentials or execute under `pull_request_target`. Do not print environment
values, secret matches, user paths, runtime inventories, or private test data in
logs or uploaded artifacts. Keep failure artifacts synthetic and time-limited.
