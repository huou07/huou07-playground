# Implement H07P

Deliver the compact, customizable open source Linux product in
[PRODUCT](../PRODUCT.md), beginning with the first unverified boundary in the
single [ROADMAP](../ROADMAP.md) tracker.

Verified handoff snapshot (2026-10-15): Hub resolves `huou07-playground` to
`/home/huou07/Projects/huou07-playground`; branch
`codex/h07p-framework-refresh`, inspected HEAD
`0b6a3847bbf67cf34c197b7d3d6dc48f9dbf81b4`.
[Hosted CI](https://github.com/huou07/huou07-playground/actions/runs/38621848508)
passed framework, legacy/Python browser and locked Rust health/static gates.
Recheck current HEAD/tree and preserve unrelated changes; this snapshot is dated.

Use [AGENTS](../../AGENTS.md) to select docs/tools and [skills.md](../../skills.md)
to choose procedures exposed by the current harness. Read
[WORKING](../WORKING.md) for authority and
[IMPLEMENTATION](../IMPLEMENTATION.md) for source locations. Retrieve only what
the active outcome needs.

Implement P1.2 now: port GET /api/metrics against `web/app.py:linux_metrics` and
its helper fixtures, reuse the existing Rust workspace/lockfile, and make the
preserved Home/System/Storage UI render actual Rust telemetry. Keep null/error
states, units, rounding and sampling/counter semantics. Add same-input HTTP
parity, including unavailable/malformed/reset cases, and a reproducible
Python/Rust idle/open resource comparison with raw sanitized samples and variance.
The existing browser runner starts Python and intercepts some APIs; its pass
alone cannot close Rust parity. If P1.2 already has fresh evidence, implement the
tracker's next unverified outcome instead.

Continue through remaining read APIs, owner authentication/policy, actual worker
isolation and approvals, detection proposals, private NAS and host Storage using
[ARCHITECTURE](../ARCHITECTURE.md), [SECURITY](../SECURITY.md),
[UX](../UX.md) and [REUSE](../REUSE.md) as needed. Preserve the design and licences.
Do not replace implementation with another general plan or empty crates.
Redis requires measured benefit including its operating/resource cost.

Run verification only on disposable GitHub-hosted Linux runners/VMs; sudo is
allowed there. Never use self-hosted runners or test/install/deploy on the owner's
Debian machine. Existing hosted commands are `python3 tools/check-framework.py`,
`make check`, `make acceptance`, the pinned Rust commands in
[CI](../../.github/workflows/ci.yml), and
`bash tests/rust-smoke.sh target/release/h07p-server`.
Extend meaningful gates for the changed boundary according to
[VALIDATION](../VALIDATION.md). Use the existing GitHub repository for authorized
validation pushes; publication/release and host operations follow current owner
authority. Linux/.deb is supported; other platforms remain Coming soon.

Complete each slice when its real journey and applicable hosted gates pass for
the exact source, with required parity, resource or Linux-boundary evidence.
Update ROADMAP with source/run/artifact pointers and implemented, CI-tested,
owner-accepted, blocked and unverified results; then continue authorized work.
Mock policy tests cannot prove isolation; CI CPU cannot prove target-host energy.
If a concrete capability/authority blocks execution, report it and the smallest
next action.

Assumptions: no additional product decisions are inferred; implementation details
remain reversible until source and the applicable contracts justify them.
Unverified: remaining product journeys, real worker isolation, .deb lifecycle,
resource improvements, target-hardware energy and owner acceptance.
Prompt method: `prompt-assist` was successfully loaded through the current DSH
skill tool after the catalog update; project-skill discovery is still unverified.
