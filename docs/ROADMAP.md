# Product implementation tracker

This file is the only current task tracker. Product behavior is in
[PRODUCT](PRODUCT.md); current code coverage is in
[IMPLEMENTATION](IMPLEMENTATION.md); production evidence is in the
[v0.3.7 provenance record](evidence/production-v0.3.7-source-provenance.md).

## Recover and publish production v0.3.7 — in progress

### Production and provenance

- Owner-reported version: v0.3.7.
- Read-only runtime observation on 2026-10-17: dashboard system service active;
  active release label `0.3.7-acl-inherit-fix`; `/api/health` returned
  `{"ok":true}`. The endpoint has no version field.
- Active executable SHA-256:
  `90626d3d4ee21d02f36bd2ed58fa61c10e4cce769931094e338894c96b901d3a`.
- Production source base: `e6c0103881e7a2af180a6bb819691d871491d49a`, plus
  `crates/server/src/helper.rs` blob
  `387dd51bf23a794c52c6bb876053ed2f39e42623`. The helper blob matches commit
  `9512ccb4e35ff77fa703d63774e29c3f99029476` exactly.
- Production services, databases, ACLs, authentication, credentials, and user
  data were not changed or accessed beyond the listed read-only metadata and
  health request.

### GitHub synchronization

- Latest public `main` at intake: `53a2d7ef4bf2514a42e8830ba27d24387daa6fc9`.
- The source was already committed on public feature branch
  `codex/h07p-product`; 55 commits from `origin/main` through `9512ccb` contain
  the product implementation. No PR connected that work to `main`.
- Cause established: implementation was pushed to the feature branch but had
  not been merged into the default branch.
- Dedicated branch: `sync/production-v0.3.7`, based on the latest `main` history
  and recovered source revision `9512ccb`.
- PR URL, exact-SHA CI, merge SHA, and tag status: pending.

### Recovered first-party components

Backend, frontend, owner authentication, policy/ACL enforcement, worker
isolation, sensitive-file detection, NAS/Storage, telemetry, app integrations,
packaging, tests, and docs are mapped in [IMPLEMENTATION](IMPLEMENTATION.md).
Third-party harnesses, provider services, runtime credentials, owner state, and
external application configuration are excluded. Source implementation is not
itself proof that every production journey was verified.

### Security and validation

- Redacted Gitleaks scan of the full 264-commit ancestry through `9512ccb`,
  including 55 commits beyond `origin/main`: no leaks found (Gitleaks 8.30.1).
- License identity: repository license is GPL-3.0 and the bundled Noto asset has
  its Apache-2.0 notice. The recovered `Cargo.lock` SHA-256 matches the
  2026-10-16 dependency/license audit, which enumerated 169 locked dependencies
  and 143 third-party license notices. That report covered an older package
  candidate; the exact v0.3.7 tag still requires the current release audit.
- File/path audit found deployment-only external OmniRoute configuration and
  historical host-specific operational records in the candidate history. These
  are excluded from the synchronized working tree; existing public history is
  preserved and not rewritten.
- Tree/history review, license review, exact-commit hosted CI, and clean-checkout
  reproducibility checks remain required before merge/tag.
- No build, installer, test, service restart, or policy change was run on
  production.

## Known limits

The running health route does not identify its version. A byte-for-byte rebuild
comparison was not possible within this read-only production inspection. The
source/release relationship is supported by the production checkout revision,
the exact helper blob match, active release label, executable path and recorded
binary hash. Authenticated UI journeys were not rerun for this synchronization.

Same-UID native application stores are not isolated from their owner; detection
is bounded and incomplete by design; package lifecycle fixtures do not equal a
full Debian systemd installation; and CI on a disposable runner does not prove
every target kernel or hardware configuration.
