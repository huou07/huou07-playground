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
- Exact-commit push and PR CI passed on `c9cab8b2153b2fa6dae1eb678affa70281ab67aa`
  (framework, Rust/Python browser acceptance, Rust formatting/lints/tests/build/
  HTTP smoke, and Python/shell checks). Runs:
  https://github.com/huou07/huou07-playground/actions/runs/39002846996 and
  https://github.com/huou07/huou07-playground/actions/runs/39002850006.
- PR merged as `2e088607ece55d904a1e39b9de5e9b18bb861c75`.
- Tag `v0.3.7` points to that merge commit. Release:
  https://github.com/huou07/huou07-playground/releases/tag/v0.3.7
- Release run `39003280946` passed source CI, dependency/license audit, package
  lifecycle checks, reproducible double build, checksum, and Lintian. Its final
  publish step failed because the publish job had no Git checkout for
  `--verify-tag`; the uploaded CI artifact was checksum-verified and published
  to the release above. A follow-up PR adds checkout to the publish job.

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
  its Apache-2.0 notice. The v0.3.7 tag's release audit generated locked
  dependency, license, and SBOM reports; the reproducible Debian package and
  lifecycle checks passed in the release workflow.
- File/path audit found deployment-only external OmniRoute configuration and
  historical host-specific operational records in the candidate history. These
  are excluded from the synchronized working tree; existing public history is
  preserved and not rewritten.
- Candidate/history review and exact-commit hosted CI passed. The release is
  published; the automated final publish step's missing-checkout defect is
  corrected in a follow-up change.
- No build, installer, test, service restart, or policy change was run on
  production.

## OpenCode native proxy auth challenge — in progress

- Chrome Playwright CLI reproduced the blank OpenCode page through the native
  relay while the backend UI itself responded normally. The unauthenticated
  backend challenge includes a same-origin CORS header; the H07P-generated
  challenge did not, so Chrome could not complete the module-script auth retry.
- `native_proxy.rs` now adds that header only for an exact same-origin request
  on a loopback/private/local host authority. A focused regression covers
  allowed origins, untrusted hosts, duplicate headers and the 401 response.
- The production executable remains unchanged pending hosted CI and the
  owner-approved package rollout. DSH and OpenCode workers were observed active;
  this source change is not yet production acceptance evidence.

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
