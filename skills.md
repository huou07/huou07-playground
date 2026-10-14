# H07P skill routing

Choose the smallest matching procedure; a catalog does not preload skills.
Canonical shared catalog: [system skills](/srv/agent-workbench/skills.md).
Shared bodies remain system-owned; project bodies remain in this repository.
System links are optional host references, not portable CI dependencies.

## Shared system skills

| Skill | Use for | Exclude / neighboring route |
| --- | --- | --- |
| code-investigate | Locate code, callers, change impact or investigate a bug | Simple listing or an already grounded edit |
| project-bootstrap | Onboard/organize a project or selective migration | Routine implementation or status |
| project-steward | Project status, next task, brief/handoff, readiness or cost | Actual failing-check diagnosis; standalone prompt rewrite |
| verify-debug | Diagnose a failing test/build/runtime check or requested verification | Prose-only changes or status-only requests |
| sustained-repair | Grounded repeated failures or unfinished work spanning sessions | One failing check; no blind retries |
| security-review | Scoped auth/isolation, dependency/import, commit or release trust review | Trivial wording or correctness debugging |
| skill-maintainer | Instruction/skill organization, routing misfires or maintenance | Ordinary product implementation |
| ui-ux-review | New screen/flow, interaction/navigation or UX/accessibility review | Backend-only changes or one CSS value |

The table follows the canonical shared catalog inspected on 2026-10-15.
It describes routing candidates, not this session's exposed DSH skill names.

## Project skills

| Skill / body | Use for | Exclude / neighboring route |
| --- | --- | --- |
| [h07p-isolation](.agents/skills/h07p-isolation/SKILL.md) | Worker rules, approval broker, detection and Linux enforcement | Ordinary telemetry or styling |
| [h07p-files](.agents/skills/h07p-files/SKILL.md) | NAS/Storage operations, safe previews, transfer recovery and file UX | Generic navigation or isolation-only work |
| [h07p-efficiency-ci](.agents/skills/h07p-efficiency-ci/SKILL.md) | Rust parity migration, resource costs, hosted CI and .deb acceptance | Routine docs/prompt edits |

Use a project procedure for its specific contract and a shared procedure only
when another boundary applies: file UX may need ui-ux-review; OS isolation may
need security-review; an actual failed gate belongs to verify-debug.
Do not load all of them for every task or duplicate shared bodies locally.

## Prompt artifacts

Hub-local prompt-assist is the candidate for an explicit task, handoff, corrective,
review or compression prompt. It is not a shared system skill and is not installed
in H07P. Load it through DSH only if the current session exposes that exact name.
If unavailable, report the limitation and use the Hub's prompting documentation
as reference guidance; do not claim a successful skill load.

## Availability and loading

Use the current session catalog and loader. DSH catalog entries use the current
DSH skill tool/exact exposed name; native skills use their native mechanism.
Do not reuse old DSH catalogs, copy connection identities or copy DSH bodies into
private native directories. Readable files do not prove discovery or activation.
If a needed procedure is unavailable, report that fact; project docs remain
retrievable references, not a substitute claim that a skill was loaded.

## Representative routes

| Request | Route |
| --- | --- |
| "Who calls the metrics collector?" | code-investigate |
| "Make balance ask before outside writes" | h07p-isolation; security-review for the changed trust boundary |
| "Write but prevent deletion in this folder" | h07p-isolation; validate actual supported Linux operation mapping |
| "Preview uploaded HTML safely" | h07p-files; security-review if preview trust changes |
| "Cut across filesystems failed halfway" | h07p-files; verify-debug for observed check failure |
| "Port health/static to Rust" | h07p-efficiency-ci |
| "Add Redis because it is faster" | h07p-efficiency-ci; require comparison evidence |
| "Instructions/routes are wrong" | skill-maintainer |
| "Rewrite the implementation prompt" | prompt-assist if exposed; otherwise documented limitation |
| "Change one accent value" | No project skill needed |

Structure/link checks do not prove live routing, loading or product acceptance.
Record observed selection/output before promoting candidates or claiming discovery.
