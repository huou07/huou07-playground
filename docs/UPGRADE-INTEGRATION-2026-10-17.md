# Source integration record — 2026-10-17

## Context

The stale production checkout at `/home/huou07/Projects/H07P` was on branch
`codex/h07p-product` at `e6c01038`, seven commits behind
`origin/codex/h07p-product` (`a91bd571`), with uncommitted working-tree edits.

The preflight also established facts that differ from the task brief:

- Production is **0.3.9** (`dpkg -l`), not 0.3.7. Tags `v0.3.7`, `v0.3.8`,
  `v0.3.9` all exist; `v0.3.9` is `origin/main` at `11932829`.
- `origin/main` has advanced past the brief's "last observed public main"
  `4b95001e`; it is now `11932829` (13 commits ahead of local `HEAD`).
- The actual uncommitted tracked set is **seven** files, not five. Neither of
  the two lists in the brief matches the observed set:
  - `crates/server/src/helper.rs`
  - `deploy/package/dashboard.env` (owner-only, not readable at this uid)
  - `docs/IMPLEMENTATION.md`
  - `docs/ROADMAP.md`
  - `docs/SECURITY.md`
  - `docs/prompts/IMPLEMENT-H07P.md`
  - `docs/security/credential-guard/proposed-spec-v1.md`
  - plus untracked `docs/prompts/UPGRADE-H07P.md`
- The brief's section-1 list (`telemetry.rs`, `tests/e2e/product.spec.mjs`,
  `tests/test_app.py`, `web/app.py`, `web/static/app.js`) is not modified in
  this checkout at all.
- `codex/h07p-product` and `origin/main` are **badly diverged**: merge base
  `53a2d7ef`, with 61 commits unique to `codex/h07p-product` and 13 unique to
  `origin/main`. This is not a simple seven-commit gap.

## Reconciliation (read-only analysis, no production writes)

| file | status | decision |
| --- | --- | --- |
| `crates/server/src/helper.rs` | local file is byte-identical to upstream `9512ccb4`; origin later refactors it and adds host-account-independent tests | adopt upstream |
| `docs/IMPLEMENTATION.md` | byte-identical to upstream (`9512ccb4`) | adopt upstream (no-op) |
| `docs/SECURITY.md` | byte-identical to upstream (`9512ccb4`) | adopt upstream (no-op) |
| `docs/ROADMAP.md` | byte-identical to `9512ccb4`; upstream `a91bd571` supersedes it | adopt upstream |
| `docs/prompts/IMPLEMENT-H07P.md` | independent edit; upstream does not touch the file | preserve |
| `docs/security/credential-guard/proposed-spec-v1.md` | independent edit; upstream does not touch the file | preserve |
| `deploy/package/dashboard.env` | owner-only mode 600; unreadable at this uid; unchanged upstream | leave untouched in production checkout |

No side was discarded. The two genuinely independent edits were re-applied on
top of `origin/codex/h07p-product`; everything else adopts the strictly newer
upstream state.

## Development checkout

`/home/huou07/Projects/H07P/.h07p-dev/repo`, branch `codex/h07p-upgrade`,
based on `origin/codex/h07p-product` (`a91bd571`) plus commit `801a745`
preserving the two independent documentation edits. The production checkout
was not modified.
