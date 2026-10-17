# Implement H07P

Deliver the compact, customizable open source Linux product in
[PRODUCT](../PRODUCT.md), beginning with the first unverified boundary in the
single [ROADMAP](../ROADMAP.md) tracker.

Verified handoff snapshot (2026-10-15): the Hub now resolves `h07p` to
`/home/huou07/Projects/H07P`; the handle `huou07-playground` and the duplicate
checkout at the old path were retired on 2026-10-17. Branch
`codex/h07p-framework-refresh`, inspected HEAD
`7785c3bd479817c2de1af7fc6fb435033972dca4`.
[Hosted CI](https://github.com/huou07/huou07-playground/actions/runs/38680918199)
reports success for that exact SHA. Current Rust source still exposes health and
static files, not metrics parity. Pre-existing WIP in .gitignore and docs/TOOLS.md
must be preserved. Recheck current HEAD/tree; this snapshot is dated.

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
The Python browser lane and intercepted API fixtures cannot close Rust parity;
the separate Rust browser lane currently proves only health/static behavior. If P1.2 already has fresh evidence, implement the
tracker's next unverified outcome instead.

Continue through remaining read APIs, owner authentication/policy, actual worker
isolation and approvals, detection proposals, private NAS and host Storage using
[ARCHITECTURE](../ARCHITECTURE.md), [SECURITY](../SECURITY.md),
[UX](../UX.md) and [REUSE](../REUSE.md) as needed. Preserve the design and licences.
Do not replace implementation with another general plan or empty crates.
Redis requires measured benefit including its operating/resource cost.

Run executable validation on disposable GitHub-hosted Linux infrastructure;
sudo is allowed there for synthetic OS fixtures. Local execution is permitted
only inside an enabled owner-installed disposable lab profile, never directly
against the owner's live Debian environment. Use /usr/local/bin/aehctl status
before relying on a local capability. The dedicated h07p-lab account and KVM
prerequisite are installed; the immutable Debian base and synthetic seed are
still missing, so h07p-lab remains disabled. The Hub's
ops/product-verification/UPGRADE.md also repairs the installed snapshot service;
check actual runtime results rather than assuming installation success.
Do not execute source ops installers/guest launchers, widen your rights, use
self-hosted runners, inspect owner credentials/NAS content or alter live policy.

Existing hosted commands are `python3 tools/check-framework.py`, `make check`,
`make acceptance`, the pinned Rust commands in [CI](../../.github/workflows/ci.yml),
and `bash tests/rust-smoke.sh target/release/h07p-server`. Extend meaningful
gates for the changed boundary according to [VALIDATION](../VALIDATION.md).
Serialize heavy work, check fresh memory/disk headroom, keep bounded cgroups/
timeouts, and stop all test descendants on completion, cancellation or pressure.
A host capability account is not implementation of product P2/P3 enforcement.

The owner's current standing authorization permits coherent commits, scoped
pushes and stable releases to registered destinations after required exact-source
CI, version/artifact, health and rollback gates. It supersedes older blanket
session prohibitions, but grants no credentials, general sudo, permission changes
or branch-protection bypass. Keep publication credentials in protected CI/brokers.
Unregistered or unverified production targets require an exact owner action;
continue independent product work while reporting that boundary. Linux/.deb is
supported; other platforms remain Coming soon.

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
