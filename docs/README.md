# H07P documentation

Read this index, then the smallest relevant contract. The repository is the
source of truth; the Hub contains its pointer only.

Every Markdown file under `docs/` must appear in one of the two tables below with
an explicit `Current` or `Historical` marker. `tools/check-framework.py` fails
when a document is unindexed or unmarked, so this index is a gate, not a habit.

`Current` means the document still states how the product is or should be built.
`Historical` means it is retained as a dated record; do not execute its host
procedures or treat its reported state as current.

## Current contracts

| Document | Purpose | Status |
| --- | --- | --- |
| [WORKING.md](WORKING.md) | Scope, authority, task loop and evidence | Current |
| [TOOLS.md](TOOLS.md) | Tools, commands, side effects and execution targets | Current |
| [QUALITY.md](QUALITY.md) | H07P's definition of good, with measured gaps | Current |
| [PRODUCT.md](PRODUCT.md) | Owner intent, journeys and acceptance | Current |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Rust boundaries, cache and migration | Current |
| [IMPLEMENTATION.md](IMPLEMENTATION.md) | Source-backed implementation and route coverage; not task state | Current |
| [SECURITY.md](SECURITY.md) | Permission semantics, presets and OS enforcement | Current |
| [UX.md](UX.md) | Preserve design and make security/files usable | Current |
| [VALIDATION.md](VALIDATION.md) | Gates, evidence classes, browser lanes and package acceptance | Current |
| [ROADMAP.md](ROADMAP.md) | Single current-task tracker | Current |
| [REUSE.md](REUSE.md) | Upstream candidates, licensing and decisions | Current |
| [UPGRADE-INTEGRATION-2026-10-17.md](UPGRADE-INTEGRATION-2026-10-17.md) | Source reconciliation record and decisions | Current |
| [Credential Guard](security/credential-guard/README.md) | Opt-in monitoring, reviewed log cleanup and private recovery | Current |
| [Credential Guard integration](security/credential-guard/INTEGRATION.md) | Guard wiring, limits and owner review flow | Current |
| [Credential Guard proposed spec](security/credential-guard/proposed-spec-v1.md) | Proposed v1 detection design and its provenance | Current |
| [DSH boundary repair](security/DSH-BOUNDARY-REPAIR.md) | DSH native-store boundary and repair procedure | Current |
| [Credential Guard P0 security audit](security/credential-guard/p0/security-audit.md) | Threat review behind the Guard design | Current |
| [prompts/IMPLEMENT-H07P.md](prompts/IMPLEMENT-H07P.md) | Owner handoff prompt | Current |
| [prompts/NEXT-H07P.md](prompts/NEXT-H07P.md) | Owner's current bounded task (2026-10-17) | Current |
| [../skills.md](../skills.md) | Shared system and project skill routing | Current |

## Historical references

| Document | Purpose | Status |
| --- | --- | --- |
| [CLEAN-REINSTALL.md](CLEAN-REINSTALL.md) | Dated reinstall walkthrough | Historical |
| [ORDINARY-USER-REINSTALL.md](ORDINARY-USER-REINSTALL.md) | Dated completed owner-run cutover; its model has no per-harness UID boundary | Historical |
| [AUDIT-2026-10-15.md](AUDIT-2026-10-15.md) | Dated source inspection and its limits | Historical |
| [history/SKILLS.md](history/SKILLS.md) | Pointer-only stub; `skills.md` is authoritative | Historical |
| [history/STATUS.md](history/STATUS.md) | Dated deployment snapshot; superseded by ROADMAP.md | Historical |
| [history/PERFORMANCE.md](history/PERFORMANCE.md) | Dated samples; no enforced budget | Historical |
| [prompts/UPGRADE-H07P.md](prompts/UPGRADE-H07P.md) | Paused comprehensive upgrade plan; superseded as the active task by prompts/NEXT-H07P.md | Historical |
| [evidence/product-deployed-20261016.md](evidence/product-deployed-20261016.md) | Artifact identity and physical Debian checks | Historical |
| [evidence/product-native-20261015.md](evidence/product-native-20261015.md) | Dated native/guest acceptance results | Historical |
| [evidence/gui-deployed-20261016.md](evidence/gui-deployed-20261016.md) | Dated GUI deployment evidence | Historical |
| [evidence/dependency-release-audit-2026-10-16.md](evidence/dependency-release-audit-2026-10-16.md) | Dated dependency and licence audit | Historical |
| [Credential Guard P0 deployment preflight](security/credential-guard/p0/deployment-preflight.md) | Dated preflight for an earlier deployment attempt | Historical |

They describe earlier deployments and samples; do not execute their host
procedures or treat their reported state as current. Upstream licences and
[../LICENSE](../LICENSE) remain unchanged.

## Documentation rules

Update contracts when behavior changes. Record a decision in the relevant
contract with evidence; do not create parallel task lists or session diary dumps.
Architecture text labels planned behavior. Runtime claims require source/run
identity and an observed target. Keep private paths and secrets out of published
evidence. Project-local skills reference these contracts instead of duplicating them.

Add a document to this index in the same commit that adds or moves the document,
with its `Current` or `Historical` marker; `tools/check-framework.py` enforces it.
