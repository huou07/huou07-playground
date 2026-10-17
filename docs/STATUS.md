# Project status

## Production v0.3.7

The owner reports v0.3.7 is installed, fully implemented, and operational. On
2026-10-17, read-only inspection confirmed an active Playground service, the
release label `0.3.7-acl-inherit-fix`, and a successful health response. The
health response does not include a version field, so the exact version remains
owner-reported and supported by the release label and source evidence.

The production source checkout was based on commit
`e6c0103881e7a2af180a6bb819691d871491d49a` with a tracked change to
`crates/server/src/helper.rs`. Its content hash
`387dd51bf23a794c52c6bb876053ed2f39e42623` exactly matches that file in commit
`9512ccb4e35ff77fa703d63774e29c3f99029476`. The deployed binary hash is
`90626d3d4ee21d02f36bd2ed58fa61c10e4cce769931094e338894c96b901d3a`. Details and
scope limits are in the [provenance map](evidence/production-v0.3.7-source-provenance.md).

## Publication state

The recovered source is present on the existing public feature branch. Public
`main` was still at `53a2d7ef4bf2514a42e8830ba27d24387daa6fc9`; no pull request had
been opened for that source when this synchronization began. The dedicated
`sync/production-v0.3.7` branch is based on the latest `main` history. Its PR,
exact-SHA CI, merge, and v0.3.7 tag status are tracked in
[ROADMAP](ROADMAP.md).

## Evidence boundaries

- **Implemented in source:** backend, UI, worker policy and isolation, private
  files, monitoring, integrations, package lifecycle, and tests are mapped in
  [IMPLEMENTATION](IMPLEMENTATION.md).
- **Observed in production:** active service, release label, health response,
  executable path, and binary hash were checked read-only. Production feature
  journeys were not rerun for this source synchronization.
- **Verified in CI:** only checks attached to the exact source SHA count. The
  synchronization PR's hosted checks are authoritative for publication.
- **Not verified here:** a clean Debian system installation, exact binary
  reproduction, all authenticated production journeys, and all supported-host
  isolation variants.
