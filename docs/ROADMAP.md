# Product implementation tracker

This is the only task tracker. Product intent lives in PRODUCT, planned design in
ARCHITECTURE, source coverage in IMPLEMENTATION and dated evidence below.
Vocabulary: planned, in progress, implemented, CI-verified, owner-accepted, blocked.
A check or source artifact never implies owner acceptance.

## Outcomes and dependencies

| Slice | Observable result | State / prerequisite |
| --- | --- | --- |
| F0 framework | Navigable contracts, focused skills, executable handoff and hosted structural guards | Refresh CI-verified at 0b6a384; [run 38621848508](https://github.com/huou07/huou07-playground/actions/runs/38621848508); subsequent documentation finalization recorded below |
| P1 Rust baseline | Existing UI and read APIs work with fixture parity and comparable resource evidence | In progress; health/static CI-verified, metrics and remaining read APIs/resources unverified |
| P2 owner and policy | Independent owner login, rule editor, templates, dry-run, revisioned apply and redacted audit | Planned; build on Rust boundary; required before private/mutating control APIs |
| P3 actual isolation | Managed workers cannot administer themselves; Block/Allow and balance broker enforced in Debian VM | Planned; depends on P2; actual Linux workers plus positive/negative cases |
| P4 detect | Owner-selected redacted scan proposals, manual selection and no changes before Apply | Planned; depends on owner authority and policy apply path |
| P5 private NAS | Owner operations/previews, dogfood GUI Block and actual worker/API denial | Planned; depends on P2/P3; NAS private from creation, never an unprotected demo |
| P6 Storage | Host browse, operations/previews, copied path and accurate capacity | Planned; owner identity and safe file adapter required; preserve NAS/admin boundary |
| P7 efficiency and packaging | Measured journey/resource improvements and reliable Linux .deb lifecycle | Planned; compare throughout migration; package/isolation/journey evidence before release |

## Resume P1 at its first unverified boundary

| Boundary | State | Next observable evidence |
| --- | --- | --- |
| P1.1 health/static | CI-verified at c171e5e | Retain HTTP/header/traversal and loopback regressions |
| P1.2 GET /api/metrics | Unimplemented in Rust at inspected baseline | Same synthetic inputs/sampling state match Python; Home/System/Storage telemetry renders actual Rust responses; hosted idle/open comparison with raw sanitized samples |
| P1.3 remaining safe read APIs | Planned | Port incrementally using the [source map](IMPLEMENTATION.md); real HTTP fixture parity and unavailable/timeout states |
| P1.4 full dashboard/read parity and resource budgets | Unverified | Browser runs real Rust, not only Python/intercepts; same-workload repeat measurements with variance and numeric budgets established from data |

Start P1.2 by locating `web/app.py:linux_metrics`, its helper functions and
existing Python fixtures, `web/static/app.js:paint` and the Rust server.
Reuse the existing workspace and checked-in lockfile. Define fixture boundaries
for proc/sys/counter/clock/command inputs, including null, denied, malformed and
counter-reset cases. Preserve design assets and reference implementation.
Do not read real owner credentials or change host telemetry/power configuration.
Use the [implementation prompt](prompts/IMPLEMENT-H07P.md) for execution.

P1 closes only when selected read APIs and the preserved dashboard have actual
Rust parity plus comparable resource observations; health/static alone is partial.
Sensitive launch links, owner mutations and private APIs require P2 authorization;
parity must not reproduce an insecure access model.

## Evidence ledger

- Earlier F0 source `ed4cc8f99b3e77bfe89624990e73c79332d3a3ca`:
  [run 38611677690](https://github.com/huou07/huou07-playground/actions/runs/38611677690)
  passed framework/legacy and Python browser jobs.
- P1.1 source `c171e5e42799333aec72ea9b2a3c2c7608f240e3`, branch
  `codex/p1-rust-health-static`:
  [run 38619770803](https://github.com/huou07/huou07-playground/actions/runs/38619770803)
  passed locked Rust format/Clippy/test/release/HTTP smoke, framework/legacy checks
  and Python browser acceptance. Missing-lock bootstrap steps were skipped.
  Browser runner starts Python: this is not Rust dashboard parity.
- Those public run/job results were re-read on 2026-10-15 through GitHub API.
  Source inspection for this refresh stabilized at
  `67dbcda735b5e1eb7d4b889cfd9bc749d5290571`, initially clean, matching the remote
  feature branch. The initial Hub status snapshot had shown c171e5e plus one dirty
  file; a subsequent external evidence commit advanced HEAD before our edits.
  No external work was overwritten. The Hub has unrelated registry/ops changes.
- F0 refresh source `0b6a3847bbf67cf34c197b7d3d6dc48f9dbf81b4`, branch
  `codex/h07p-framework-refresh`:
  [run 38621848508](https://github.com/huou07/huou07-playground/actions/runs/38621848508)
  completed successfully. All three jobs passed: framework links/metadata/15
  declared route cases, legacy plus locked Rust gates/HTTP smoke, and Python
  browser acceptance. Source docs, navigation, rule limitations, focused project
  skills, prompt and structural/CI guards changed; no product code changed.
  Later documentation finalization adds the package data-protection contract,
  current prompt-assist evidence and this ledger. The run above remains evidence
  for its exact source; inspect the latest branch run for subsequent revisions.
  No local product tests/builds/benchmarks/installers were run. Scoped Git whitespace
  check and a fully redacted Gitleaks stdin scan of the staged framework diff passed;
  scanner coverage is that diff only, not historical source or host data. Manual
  trust review retained pinned actions, read-only CI tokens, hosted targets and
  owner/worker boundaries. Existing licences/deployment history retained; Git
  commits/diff provide rollback. No release, merge or host deployment performed.
- Discovery changed during this task: the initial DSH catalog exposed eight
  shared skills and a prompt-assist attempt returned unknown/unavailable. After
  the replacement catalog added `prompt-assist`, the current DSH loader returned
  its full body successfully and the prompt was revised using it. The eight
  shared bodies were also loaded through this session's DSH loader. Project
  bodies were read as repository references; live H07P project-skill discovery
  and model-routing performance remain unverified.

## Product verification refresh, 2026-10-15

Implemented: required 360px coverage, desktop dark/light screenshots, navigation
focus entry/cycling/restore and Escape, persistent live save status, failure trace
artifacts and a separate Rust health/static browser lane. UI fixtures remain
synthetic; the existing Python registry journey is retained. CI results for this
implementation must be attached to its exact commit before marking it CI-verified.

Local OS lab design and preflight are in
[VALIDATION](VALIDATION.md#disposable-local-os-security-lab). No guest or live
security test ran. Current worker KVM access and a reviewed immutable base are
missing; P2/P3 enforcement is still unimplemented. No new host permissions,
self-hosted runner or production policy were introduced.

## Acceptance gaps and working rules

Metrics/read parity, owner authentication, real worker isolation/revocation,
detection redaction, private NAS/Storage journeys, Debian package lifecycle,
reproducible performance/resource budgets, target-hardware energy and human UX/
owner acceptance remain unverified. The existing CI is not evidence for them.

Keep each slice reviewable and continue until its observed outcome exists.
Update this tracker instead of another TODO/plan or session journal.
Link exact source/run/artifact identities and limitations for the changed claim;
a later documentation commit does not retroactively validate new product code.
A failed gate gets a discriminating next check. Redis requires the architecture
comparison gate. No production isolation/release claim until the relevant real
P2/P3/P5 journeys and package gates pass under current owner authorization.
