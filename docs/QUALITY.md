# H07P quality bar

Authority: this is H07P's definition of "good" for the product. It does not
replace [AGENTS.md](../AGENTS.md), [WORKING.md](WORKING.md), [SECURITY.md](SECURITY.md)
or the project's gates; where they disagree, the source, the exact-SHA CI runs and
observed host behaviour decide. For the live Debian lane, the owner authorization
in [PRODUCT.md](PRODUCT.md), [WORKING.md](WORKING.md) and [VALIDATION.md](VALIDATION.md)
supersedes the historical no-live-host defaults in `README.md`, `TOOLS.md` and the
project skills; those defaults hold again when that authorization ends.

Last reviewed: 2026-10-18.

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
| Security | Landlock worker isolation, typed helper IPC, gitleaks with redaction, RustSec audit fails closed | `tools/security-audit.py`, `tools/release-audit.py`, `scan.rs` | CI jobs `security-audit`, `secret-scan` and `package-lifecycle`; owner-host audit stays manual | the audit tool now executes in CI against synthetic identities; real Debian findings remain owner-host evidence |
| Performance | resource cost of the Rust server and the guest baseline | `tools/check-performance-budget.py` over `tools/measure-product.py` | acceptance (`tools/acceptance.sh` performance lane) | bounded budget enforced on the named machine class; see Performance budget |
| Reliability | service health, restart, rollback of a package install | lifecycle scripts + systemd | lab/manual | partial |
| Accessibility / UX | roles, focus paths and screenshots in the browser matrix | `tests/e2e/ux.spec.mjs` | CI browser lane | verified for covered journeys; no pixel assertions |
| Compatibility | Debian package on the supported release | hosted workflow | `release.yml` | hosted authority |
| Maintainability | docs index complete, links resolve, framework checks | `tools/check-framework.py` | CI + `make check` | index is now complete and gated: every `docs/**/*.md` needs a `Current`/`Historical` entry |
| Cost | package size and build time | builder output | manual | partially measured |

## Known gaps, in priority order

1. The crate version (`0.1.0` in `crates/server/Cargo.toml`) has no link to the
   package version (`0.3.x`): `tools/build-deb.sh` stamps whatever version it is
   given, so the crate and the `.deb` can drift. A build-time assertion would
   close it.
2. `tests/native/workers.py` is deliberately **not** in CI because it cannot pass
   as written: it applies a Block naming `dsh-worker` before creating that account,
   and provisioning first instead trips `REVISION_CONFLICT`.
3. `tools/security-audit.py` now runs in the CI `security-audit` job, but only
   against the synthetic identities that job creates. Its real Debian findings
   (same-UID own-store access, live systemd properties) remain owner-host evidence
   and are not asserted by CI.
4. The performance budget is enforced by `tools/acceptance.sh` on the named
   Debian OptiPlex-class host only. Hosted CI is a different machine class and
   does not enforce it.
5. Two mutually exclusive isolation models are presented as current
   (`ORDINARY-USER-REINSTALL.md` vs `SECURITY.md`).
6. No tracing/log crate; only `eprintln`, so a deployed failure is hard to
   diagnose from evidence.

## Performance budget

Machine class: Debian 13 (trixie) x86_64, Dell OptiPlex Micro 7010, Intel Core
i5-13500T (20 threads), 15 GiB RAM — the owner's host, named because the budget
is calibrated on it. `tools/performance-budget.json` records the calibration and
the exact workload. Calibration run 2026-10-18 at `095603b8`, clean tree.

| Measure | Calibrated max | Budget | Margin |
|---|---:|---:|---:|
| Rust server tree peak RSS | 15,753,216 B (15.0 MiB) | 50,331,648 B (48 MiB) | 3.2x |
| `/api/health` p95 latency | 1.27 ms | 10 ms | 7.9x |
| `/` (dashboard) p95 latency | 2.33 ms | 15 ms | 6.4x |
| Idle CPU over 5 s | 0.00 s | reported, not budgeted | — |

`tools/check-performance-budget.py` runs `tools/measure-product.py` with a
loopback fixture, three repeats, 20 requests per endpoint and a 5 s idle window,
then fails when the worst repeat exceeds a budget. It is the performance lane of
the acceptance gate, so a gross regression fails `bash tools/acceptance.sh`; the
raw evidence lands in the gitignored `.hub/product-measurement.json`. The bound
catches a leak, a blocked request or runaway polling, not runner noise. Reproduce
with:

```sh
python3 tools/check-performance-budget.py \
  --binary target/debug/h07p-server \
  --budget tools/performance-budget.json \
  --output .hub/product-measurement.json
```

Scope limit: the measurement covers the Rust server process tree only. Helper
collectors, Redis, TLS/VPN relays, throughput and whole-machine energy are out of
scope, and hosted CI is a different machine class that does not enforce this
budget. A budget that cannot be measured is `UNVERIFIED`, never a pass.

## Verified at this revision

Each statement that an earlier revision of this file got wrong has a command that
proves or disproves it. The tree statements were verified at `095603b8`; the
hosted statements at `f6580e49`, the commit this record describes (only this
documentation changes after it). Re-run them rather than trusting this prose.

| Statement | Command that proves it |
|---|---|
| The checkout equals its remote-tracking branch and is clean | `git rev-list --left-right --count HEAD...origin/codex/h07p-product`; `git status --porcelain` |
| The tree passes its own lint gate | `cargo clippy --workspace --all-targets --locked -- -D warnings` (also inside `make check`) |
| `docs/prompts/UPGRADE-H07P.md` is tracked | `git ls-files docs/prompts/UPGRADE-H07P.md` |
| `.delivery/` holds no tracked ledger | `git ls-files .delivery`; `ls -A .delivery` |
| Every `docs/**/*.md` is indexed and marked | `python3 tools/check-framework.py` |
| The CI jobs run green including `security-audit` | `gh run view 39054428135` (push, `f6580e49`; every job success, aggregate `release-gate` success) |
| A release dispatch builds and audits without publishing | `gh run view 39054436095` (workflow_dispatch, `f6580e49`; `gates` and `package` success, `publish` skipped, artifact `h07p-release-0.0.0-dispatch.f6580e4905ac`) |

Hosted CI for a later revision must be re-checked at that revision. A run at a
different SHA is `STALE`, not evidence for HEAD, and a skipped or not-run lane is
`not_run` in the gate report, never a pass.

## Evidence rules

- Source gate: `make check` — Python reference, deploy scripts and Python tests,
  plus Rust format, clippy with warnings as errors and the workspace test suite.
  Cargo and Python caches resolve to a writable path (`tools/cargo-env.sh`) so the
  gate also runs when the verifier does not own the checkout.
- Acceptance gate: `bash tools/acceptance.sh` — source gate plus the same Rust
  lanes again, the bounded performance budget, the browser journeys for both
  backends when `node_modules` and node are present, and `--full` adds the release
  build. It writes the AEH gate report to `.hub/gate-report.json`, naming the
  contract gates it covered and every lane it did not run.
- Release gate: hosted CI (`ci.yml`, `release.yml`) with the aggregate
  `release-gate` job, plus the owner's lab for guest and package acceptance.
- A skipped, missing or unavailable check is `UNVERIFIED`; it is never PASS.
