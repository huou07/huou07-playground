# H07P quality bar

Authority: this is H07P's definition of "good" for the product. It does not
replace [AGENTS.md](../AGENTS.md), [WORKING.md](WORKING.md), [SECURITY.md](SECURITY.md)
or the project's gates; where they disagree, the source, the exact-SHA CI runs and
observed host behaviour decide.

Last reviewed: 2026-10-17.

## Supported targets

| Target | Claimed support | Evidence class | Last exact-source run |
|---|---|---|---|
| Debian Linux, owner host (live dashboard) | installed and healthy at version 0.3.x | MEASURED (live health) | systemd units + version check |
| Debian package (`.deb`) | built by the release workflow | VERIFIED_NATIVE only for the artifact the workflow produced | hosted `release.yml` |
| Browser matrix (Python and Rust lanes) | dashboard journeys on a disposable runner | VERIFIED_BEHAVIORAL | hosted `ci.yml` |
| Disposable guest lab | isolation and packaging acceptance | MEASURED in the guest only | `.h07p-dev` guest, not CI |
| Windows / macOS | not claimed | — | — |

Not claimed: worker isolation of the owner's own store (same-UID own-store access
is unresolved), a published package repository, or cross-platform support.

## Attributes

| Attribute | Target | How it is measured | Gate that enforces it | Current status |
|---|---|---|---|---|
| Correctness | admission gate passes | `bash tools/acceptance.sh` | acceptance | see recorded result |
| Correctness (source) | Python reference, deploy scripts and tests | `make check` | verify | see recorded result |
| Security | Landlock worker isolation, typed helper IPC, gitleaks with redaction, RustSec audit fails closed | `tools/security-audit.py`, `tools/release-audit.py`, `scan.rs` | manual + publication flow | real probes exist but are not in CI |
| Performance | resource cost of the Rust server and the guest baseline | `tools/measure-product.py`, native RSS/latency checks | manual | measured, no enforced budget |
| Reliability | service health, restart, rollback of a package install | lifecycle scripts + systemd | lab/manual | partial |
| Accessibility / UX | roles, focus paths and screenshots in the browser matrix | `tests/e2e/ux.spec.mjs` | CI browser lane | verified for covered journeys; no pixel assertions |
| Compatibility | Debian package on the supported release | hosted workflow | `release.yml` | hosted authority |
| Maintainability | docs index complete, links resolve, framework checks | `tools/check-framework.py` | CI + `make check` | index is now complete and gated: every `docs/**/*.md` needs a `Current`/`Historical` entry |
| Cost | package size and build time | builder output | manual | partially measured |

## Known gaps, in priority order

1. This checkout is behind `origin/codex/h07p-product`; the release workflow and
   the 0.3.8 evidence exist only on the remote, and the local uncommitted edits
   overlap that work without being identical. Reconcile before any new work.
   Measured 2026-10-17: `cargo clippy --workspace --all-targets -- -D warnings`
   fails on the uncommitted `crates/server/src/helper.rs` (collapsible `if` at
   line 591, simplifiable boolean at 897, needless references at 954/959, items
   after a test module at 1035), while `cargo test --workspace` passes. The tree
   therefore does not pass its own CI lint gate as it stands.
2. `docs/prompts/UPGRADE-H07P.md` is untracked and 11 documents are missing from
   `docs/README.md`; the tracker mixes several eras and other projects' work.
3. The `.delivery/*.json` ledgers (tracked) embed a private macOS path, and the
   crate version (0.1.0) has no link to the package version (0.3.x).
4. `tests/native/*`, `tests/package-*.sh`, `tools/release-audit.py` and
   `tools/build-deb.sh` are now wired to CI jobs (`native-isolation`,
   `package-lifecycle`) plus a change-set secret scan. Two limits remain explicit:
   `tests/native/workers.py` is deliberately **not** in CI because it cannot pass
   as written (it applies a Block naming `dsh-worker` before creating that account,
   and provisioning first instead trips `REVISION_CONFLICT`), and
   `tools/security-audit.py` is still invoked by no job. The new jobs have not been
   executed on a hosted runner yet, so hosted coverage is UNVERIFIED until a run
   exists.
5. The project skills forbid running on the owner host while `WORKING.md` and
   `VALIDATION.md` authorise exactly that lane; the routing and the authority
   contradict each other.
6. Two mutually exclusive isolation models are presented as current
   (`ORDINARY-USER-REINSTALL.md` vs `SECURITY.md`).
7. No tracing/log crate; only `eprintln`, so a deployed failure is hard to
   diagnose from evidence.

## Evidence rules

- Source gate: `make check` — Python reference, deploy scripts and Python tests.
- Acceptance gate: `bash tools/acceptance.sh` — source gate plus Rust format,
  clippy with warnings as errors, and the workspace test suite; `--full` adds the
  release build.
- Release gate: hosted CI (`ci.yml`, `release.yml`) plus the owner's lab for guest
  and package acceptance.
- A skipped, missing or unavailable check is `UNVERIFIED`; it is never PASS.
