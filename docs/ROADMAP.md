# Product implementation tracker

Status vocabulary: planned, in progress, implemented, CI-verified, owner-accepted, blocked.
No phase is accepted from a checklist alone. Evidence includes exact source and run.

| Slice | Observable result | State |
| --- | --- | --- |
| F0 framework | Contracts, source audit, focused skills and handoff; hosted framework/legacy/browser checks | CI-verified at ed4cc8f; [run 38611677690](https://github.com/huou07/huou07-playground/actions/runs/38611677690); live skill discovery and owner acceptance unverified |
| P1 Rust baseline | Rust serves existing UI and health/read APIs against parity fixtures; hosted build and resource baseline | In progress — initial health/static boundary is only in the working tree; P1 acceptance remains unverified |
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

2026-10-15 progress evidence: working tree based on `main` HEAD
`53a2d7ef4bf2514a42e8830ba27d24387daa6fc9` adds a Rust loopback server for the
existing static assets and `/api/health`, with traversal, response-header and
non-loopback regression cases. No CI run exists for this working tree. Rust is not
installed in the repository host session, so no local build or test was attempted.
Cargo.lock is not yet checked in; CI has a one-time lock bootstrap artifact path.
This is implemented source, not a deployed service or an accepted Rust migration.
Python remains the runtime and parity reference.

Completion of P1 still needs a committed exact Cargo.lock, remaining safe read API
parity fixtures, hosted Rust build/test/browser evidence, and comparable bounded
resource samples for the same workload. The next action is to obtain the hosted
lockfile from CI, check it in, and then port read endpoints against Python fixtures.
P1 is a backend baseline, not secure NAS acceptance. Choose the next P2/P3 boundary
only after this evidence is available.

## Working rules

Keep each slice reviewable but continue until its user outcome is demonstrated.
Update this table instead of adding another TODO/plan. Record blockers with a
discriminating next check. Security/UX contracts are dependencies, not optional
afterthoughts. Redis requires the architecture evidence gate before becoming scope.
Do not release a production isolation claim until P2/P3/P5 denial journeys pass.
