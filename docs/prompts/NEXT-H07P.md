# NEXT-H07P — continue under the quality system

Authority for this work: [../AGENTS.md](../AGENTS.md), [../docs/WORKING.md](../docs/WORKING.md)
and [../docs/VALIDATION.md](../docs/VALIDATION.md). This prompt is an owner
instruction from 2026-10-17 and grants nothing those files forbid. It explicitly
authorises the reconciliation and the deletions listed below.

## What changed before you start

A reorganization ran while your session was paused, and the goal that was driving
automatic rounds is paused. Do not resume it; work this prompt as one ordinary
task and stop at the end.

Read first:

- [../docs/QUALITY.md](../docs/QUALITY.md) — H07P's definition of good, with the
  measured gaps.
- `~/AEH/docs/quality-system.md` — the process this repository now follows.

Two gates now exist:

| Gate | Command | Proves |
|---|---|---|
| verify | `make check` | the preserved Python reference, deploy scripts and Python tests |
| acceptance | `bash tools/acceptance.sh` | the above, plus `cargo fmt --check`, `cargo clippy -D warnings` and `cargo test --workspace` |

`tools/acceptance.sh` uses a per-worker `CARGO_TARGET_DIR` because the checked-out
`target/` cache denies this worker at the file ACL. `--full` adds the release
build. Do not weaken these checks; make the tree pass them.

## Do these, in order

1. **Reconcile with `origin/codex/h07p-product` before anything else.** This
   checkout is seven commits behind; `.github/workflows/release.yml` and the 0.3.8
   evidence exist only on the remote, and the local uncommitted edits to
   `crates/server/src/helper.rs` and four documents overlap that work without
   being identical. Fetch, diff both sides, then either re-apply the local intent
   on top of the remote or discard it with the reason recorded. Never force-push.
   Measured 2026-10-17: the uncommitted `helper.rs` fails
   `cargo clippy --workspace --all-targets -- -D warnings` at lines 591, 897, 954,
   959 and 1035 while `cargo test --workspace` passes. The tree must pass the
   acceptance gate before you stop.
2. **Make the authority chain visible.** Commit
   `docs/prompts/UPGRADE-H07P.md` (it is untracked) or move it to `docs/archive/`
   with a reason; add every document under `docs/` to `docs/README.md`; add a
   `tools/check-framework.py` rule that fails when a `docs/**/*.md` file is absent
   from the index or lacks a `Current`/`Historical` marker.
3. **Collapse the contradictions.** Remove or archive the "superseded" tables in
   `docs/IMPLEMENTATION.md` that claim Permissions/NAS are absent;
   reconcile `docs/ORDINARY-USER-REINSTALL.md` with `docs/SECURITY.md` (they
   present two mutually exclusive isolation models as current); mark
   `docs/AUDIT-2026-10-15.md` as historical in the index.
4. **Make the real gates automatic.** Add CI jobs for `tests/native/*`,
   `tests/package-*.sh`, `tools/release-audit.py`, and
   `tools/build-deb.sh` + lintian + install/upgrade/purge, plus a redacted
   gitleaks scan. Where a lane genuinely cannot run in CI, delete the claim that
   it is covered rather than leaving it implied.
5. **Fix test reachability.** `tests/package/test_*.py` are unreachable by
   `make check`'s `unittest discover -s tests` (no `__init__.py`); either add it
   or list those files explicitly in the Makefile. Add a Rust lane for
   `dashboard.spec.mjs`, or state plainly that Rust dashboard journeys are
   unverified.
6. **Split the tracker.** `docs/ROADMAP.md` mixes 2026-10-15/16/17 eras and other
   projects' work (OR, VCE, Flutter). Keep only current task state; move dated
   and cross-project content to `docs/evidence/`.
7. **One version source and observability.** Derive the package version from one
   place so `Cargo.toml` (0.1.0) cannot drift from the package (0.3.x), and add
   `tracing` as `docs/ARCHITECTURE.md` already proposes so a deployed failure is
   diagnosable from evidence.
8. **Delete what lies.** `.delivery/ledger.json` and `.delivery/gui-ledger.json`
   are tracked and embed a private macOS path; `docs/SKILLS.md` is a pointer only;
   `docs/STATUS.md` and `docs/PERFORMANCE.md` are stale. Delete them or move them
   to `docs/history/` with a banner.

## Rules

- Do not run privileged commands, the guest lab, or a `.deb` install unless the
  owner authorises that lane; the acceptance gate does not need it.
- Do not push, publish, open a release or change permissions.
- Never weaken a gate, an assertion or a scanner to obtain PASS.
- One coherent change per commit, with the gate result in the message.
- Record evidence with the exact SHA in the project's existing tracker; do not
  start a second journal.
- Report `IMPLEMENTED`, `VERIFIED_*`, `ACCEPTED` and `BLOCKED/UNVERIFIED`
  separately, and name what you did not run.

## Stop when

The acceptance gate passes on a reconciled tree, every item above is done with
recorded evidence or reported blocked with the exact missing capability, and the
handoff records branch, HEAD, gate result, unverified items and the next action.
