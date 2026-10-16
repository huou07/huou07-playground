# H07P documentation

Read this index, then the smallest relevant contract. The repository is the
source of truth; the Hub contains its pointer only.

| Document | Purpose |
| --- | --- |
| [WORKING.md](WORKING.md) | Scope, authority, task loop and evidence |
| [TOOLS.md](TOOLS.md) | Tools, commands, side effects and execution targets |
| [PRODUCT.md](PRODUCT.md) | Owner intent, journeys and acceptance |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Proposed Rust boundaries, cache and migration |
| [IMPLEMENTATION.md](IMPLEMENTATION.md) | Source-backed implementation and route coverage; not task state |
| [SECURITY.md](SECURITY.md) | Permission semantics, presets and OS enforcement |
| [UX.md](UX.md) | Preserve design and make security/files usable |
| [VALIDATION.md](VALIDATION.md) | GitHub CI, evidence, performance and .deb gates |
| [ROADMAP.md](ROADMAP.md) | Single implementation tracker and first slice |
| [Deployed 0.2.2 evidence](evidence/product-deployed-20261016.md) | Artifact identity, physical Debian checks, installer recovery, VPN and limitations |
| [Credential Guard](security/credential-guard/README.md) | Opt-in monitoring, reviewed log cleanup and private recovery |
| [REUSE.md](REUSE.md) | Upstream candidates, licensing and decisions |
| [AUDIT-2026-10-15.md](AUDIT-2026-10-15.md) | Source inspection and its limits |
| [../skills.md](../skills.md) | Shared system and project skill routing |
| [prompts/IMPLEMENT-H07P.md](prompts/IMPLEMENT-H07P.md) | Owner handoff prompt |

## Historical references

[STATUS.md](STATUS.md), [PERFORMANCE.md](PERFORMANCE.md) and
[CLEAN-REINSTALL.md](CLEAN-REINSTALL.md) retain their original contents.
They describe earlier deployments and samples; do not execute their host
procedures or treat their reported state as current. Upstream licences and
[../LICENSE](../LICENSE) remain unchanged.

## Documentation rules

Update contracts when behavior changes. Record a decision in the relevant
contract with evidence; do not create parallel task lists or session diary dumps.
Architecture text labels planned behavior. Runtime claims require source/run
identity and an observed target. Keep private paths and secrets out of published
evidence. Project-local skills reference these contracts instead of duplicating them.
