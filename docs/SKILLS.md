# Project skill routing

Project skills live under .agents/skills in this repository. They are authored
candidates for the project's agents, not currently discovered DSH skills.
A future session must inspect its actual catalog: native agents load using their
native mechanism; DSH loads only exact exposed names using its own skill tool.
Do not copy them into a private cache to fake discovery. If not exposed, read the
project contracts directly and report discovery as unverified.

| Candidate | Trigger | Neighboring negative trigger |
| --- | --- | --- |
| [h07p-isolation](../.agents/skills/h07p-isolation/SKILL.md) | Implement/review worker permissions, approvals, scans or Linux sandbox boundaries | Static UI styling or ordinary telemetry |
| [h07p-files](../.agents/skills/h07p-files/SKILL.md) | Implement NAS/Storage operations, preview or private-file UX | Generic dashboard route or isolation-only work |
| [h07p-efficiency-ci](../.agents/skills/h07p-efficiency-ci/SKILL.md) | Rust migration parity, resource diagnosis, hosted CI and .deb acceptance | Prompt editing or routine docs changes |

Shared code investigation, UX review, security review and verify-debug remain
available only when the current session exposes them. Do not duplicate those broad
workflows here. These three skills hold project-specific procedures and evidence.

Representative routing contracts:
- "Make balance ask before outside writes" -> h07p-isolation.
- "Allow write but prevent deletion in a folder" -> h07p-isolation, require real
  supported operation mapping; chmod-only implementation is insufficient.
- "Preview uploaded HTML safely" -> h07p-files, private/auth boundary review.
- "Storage cut across filesystems failed halfway" -> h07p-files, integrity recovery.
- "Rust port health/static with same UI" -> h07p-efficiency-ci.
- "Add Redis because it is faster" -> h07p-efficiency-ci, require comparison first.
- "Change one accent value" -> no project skill.
- "Write a task prompt" -> contracts only, no executable validation.
Structural CI validates files/links/frontmatter, not live harness routing. Record
actual loading and representative observed outputs before claiming discovery.
