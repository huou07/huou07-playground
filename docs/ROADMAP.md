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
- Production source base: `e6c0103881e7a2af180a6bb819691d871491d49a`, plus the
  helper working-tree blob recorded in the provenance document, which matched
  commit `9512ccb4e35ff77fa703d63774e29c3f99029476`. The publication branch
  adds disclosed behavior-equivalent Clippy/testability edits to `helper.rs`;
  it is not a byte-for-byte copy of the deployed helper.
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
- PR: https://github.com/huou07/huou07-playground/pull/1
- Exact-commit hosted CI passed on branch commit
  `ca81c830960b10d76f61c8343a8f04962c80b5b6` (framework, Rust/Python browser
  acceptance, Rust formatting/lints/tests/build/HTTP smoke, and Python/shell
  checks). The PR event checks for this commit are still finishing.
- Merge SHA and tag status: pending PR checks and merge.

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
- Candidate/history and license review completed; hosted CI passed on the branch
  commit above. Merge review and an exact release/tag audit remain outstanding.
- No build, installer, test, service restart, or policy change was run on
  production.

## Known limits

The running health route does not identify its version. A byte-for-byte rebuild
comparison was not possible within this read-only production inspection. The
source/release relationship is supported by the production checkout revision,
the recovered helper blob match at intake, deployed static/configuration file
matches, active release label, executable path and recorded binary hash. The
publication branch's disclosed helper maintenance edits were not deployed.
Authenticated UI journeys were not rerun for this synchronization.

Same-UID native application stores are not isolated from their owner; detection
is bounded and incomplete by design; package lifecycle fixtures do not equal a
full Debian systemd installation; and CI on a disposable runner does not prove
every target kernel or hardware configuration.
