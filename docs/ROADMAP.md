# Product implementation tracker

Status vocabulary: planned, in progress, implemented, CI-verified, owner-accepted, blocked.
No phase is accepted from a checklist alone. Evidence includes exact source and run.

| Slice | Observable result | State |
| --- | --- | --- |
| F0 framework | Contracts, source audit, focused skills and handoff; hosted framework/legacy/browser checks | CI-verified at ed4cc8f; [run 38611677690](https://github.com/huou07/huou07-playground/actions/runs/38611677690); live skill discovery and owner acceptance unverified |
| P1 Rust baseline | Rust serves existing UI and health/read APIs against parity fixtures; hosted build and resource baseline | In progress — health/static boundary CI-verified at `c171e5e42799333aec72ea9b2a3c2c7608f240e3`; [run 38619770803](https://github.com/huou07/huou07-playground/actions/runs/38619770803). Remaining read API parity and comparable resource samples unverified; owner acceptance pending |
| P2 owner and policy | Independent owner login, rule editor, templates, dry-run, revisioned apply and redacted audit | Planned |
| P3 actual isolation | Managed workers cannot administer themselves; block/allow and balance broker enforced in Debian VM | Planned |
| P4 detect | Owner-selected redacted scan proposals, manual selection and no changes before Apply | Planned |
| P5 private NAS | Owner file operations/previews and dogfood Block with real worker/API denial | Planned |
| P6 Storage | Host fixture browse, operations, previews, copied path and accurate capacity | Planned |
| P7 efficiency and packaging | Measured workload improvements, reliable .deb upgrade/rollback, release artifacts | Planned |

## First implementation slice

Start P1 immediately after reading contracts. Create the minimal Rust workspace
only with needed crates, lock dependencies and port health/static serving.
Keep branding and frontend behavior. Add hosted Rust gates, parity tests and a
baseline workload; use GitHub CI only. Do not implement an unprotected permissions
or NAS demo before owner authentication and real enforcement exist.
Then port telemetry/app reads incrementally; preserve historical protected launch
tokens and external app behavior without reading real credentials.

2026-10-15 hosted evidence: source branch `codex/p1-rust-health-static`, HEAD
`c171e5e42799333aec72ea9b2a3c2c7608f240e3`. The Rust server serves the existing
static UI and `/api/health`, rejects non-loopback binding, and passes traversal and
response-header regressions. `Cargo.lock` is checked in from the hosted-generated
dependency graph. [GitHub run 38619770803](https://github.com/huou07/huou07-playground/actions/runs/38619770803)
passed framework and legacy checks, Rust format/Clippy/test/release build/HTTP smoke,
and existing browser acceptance. This verifies the health/static migration boundary;
it does not establish production deployment or owner acceptance. Python remains the
runtime and parity reference for the other APIs.

P1 remains in progress. Safe read API parity fixtures and comparable bounded resource
samples for the same workload are unverified. The next action is to port the dashboard
metrics read API against Python fixtures and add the same-fixture CI comparison. No
local tests/builds were run; executable checks ran on GitHub-hosted infrastructure.
P1 is a backend baseline, not secure NAS acceptance.

## Working rules

Keep each slice reviewable but continue until its user outcome is demonstrated.
Update this table instead of adding another TODO/plan. Record blockers with a
discriminating next check. Security/UX contracts are dependencies, not optional
afterthoughts. Redis requires the architecture evidence gate before becoming scope.
Do not release a production isolation claim until P2/P3/P5 denial journeys pass.
