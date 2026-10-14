# Implement H07P

Work in the Hub-registered huou07-playground repository. Establish current
branch, HEAD and working tree, preserving unrelated work. Use
[../../AGENTS.md](../../AGENTS.md) as the navigation entrypoint and
[../../skills.md](../../skills.md) to select available procedures.
Retrieve only the docs/tools needed for the current task; do not preload the index.

Deliver the product described by [../PRODUCT.md](../PRODUCT.md), starting with
the next unverified slice in [../ROADMAP.md](../ROADMAP.md). At this handoff P1
is planned: port existing UI serving, health and safe read APIs to Rust, preserve
the current design, and demonstrate parity and resource behavior on hosted CI.
Recheck the tracker/source before acting; this dated statement is not live evidence.

Continue through owner authentication, enforceable worker permissions and
approvals, owner-selected redacted detection, private NAS and host Storage.
Choose implementation details from the relevant contracts and observed failures.
Optimize actual owner journeys, latency and resource use; introduce Redis only
when the comparison supports it. Keep each outcome demonstrable and resumable.

Before executing work, consult [../WORKING.md](../WORKING.md) for authority and
[../TOOLS.md](../TOOLS.md) for command effects. Tests/builds/package checks run
on disposable GitHub-hosted infrastructure; do not test/install/deploy on the
owner's Debian machine. Push/publication/release to the existing GitHub repository
is authorized under the documented acceptance conditions.

Finish when the selected product slice works through its representative journey
and required hosted gates for the exact source pass. Update the existing roadmap
with evidence, limitations and next slice; distinguish implemented, CI-tested,
owner-accepted and unverified. Continue authorized implementation rather than
ending with another plan or empty scaffold. For a concrete capability/authority
blocker, report the missing condition and the smallest next action.
