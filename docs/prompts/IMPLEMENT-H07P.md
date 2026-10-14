# Implement H07P

Work in the Hub-registered `huou07-playground` repository. Establish current
branch, HEAD and working tree; preserve unrelated work. Select references through
[AGENTS](../../AGENTS.md) and available procedures through
[skills.md](../../skills.md). Read [WORKING](../WORKING.md) for execution authority
and [ROADMAP](../ROADMAP.md) for the first incomplete outcome. Retrieve only the
source/contracts needed for that outcome.

Start implementing the next unverified P1 boundary. At this handoff Rust already
serves health/static with a checked-in lockfile; do not recreate that scaffold.
Use [IMPLEMENTATION](../IMPLEMENTATION.md) to locate `linux_metrics`, its helpers,
existing fixtures and the Rust server. Port GET /api/metrics against the Python
reference and make the existing Home/System/Storage telemetry render real Rust
responses with the current design. Preserve null/unavailable states, units,
sampling/counter semantics and bounded collection. Add same-fixture HTTP parity
and a reproducible Python/Rust idle/open workload comparison on disposable hosted
Linux infrastructure. Measure resource cost and variance before claiming gains.
Recheck the tracker: if that boundary has fresh evidence, continue at its next
unverified outcome rather than repeating completed work.

Use [ARCHITECTURE](../ARCHITECTURE.md), [VALIDATION](../VALIDATION.md) and
[REUSE](../REUSE.md) for migration, gates and provenance. Keep the Python reference
until replacement evidence exists. The current browser runner starts Python;
exercise Rust explicitly, and do not treat intercepted API responses as backend
parity. Fix observed failures and update the single tracker with exact source,
run URLs, observations and limitations.

Continue authorized product development through the remaining read APIs, owner
authentication/revisioned policy, actual worker isolation, detection proposals,
private NAS and host Storage, following tracker dependencies and the relevant
[product](../PRODUCT.md), [security](../SECURITY.md) and [UX](../UX.md) contracts.
Each slice must produce usable behavior and an observed journey; do not stop at
another general plan or empty crates. Redis requires measured total-cost benefit.
Linux/.deb is the supported delivery target; other platforms remain Coming soon.

Run tests/builds/benchmarks/package lifecycle only on disposable GitHub-hosted
Linux runners/VMs; sudo is allowed there. Never use self-hosted runners, test or
install Playground on the owner's Debian machine. Use the existing H07P GitHub
repository for authorized validation pushes/publication; a framework pass is not
a product release. Respect the release/host authority in WORKING and VALIDATION.

A slice is done when its real owner journey and applicable hosted gates pass for
the exact source, with parity/resource/boundary evidence appropriate to it.
Record implemented, CI-tested, owner-accepted, blocked and unverified separately.
Mock rules do not prove isolation, CPU measurements do not prove target-host
electricity savings, and CI cannot grant owner acceptance. Continue at the next
incomplete outcome; if an actual capability or authority is missing, report the
specific condition and smallest next action.

Prompt provenance: the current DSH loader rejected `prompt-assist` as unavailable
on 2026-10-15. This artifact follows the Hub's prompting reference; no successful
prompt-assist activation or project-skill discovery is claimed.
