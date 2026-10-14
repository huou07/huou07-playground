# Product implementation tracker

This is the only task tracker. Product intent lives in PRODUCT, planned design in
ARCHITECTURE, source coverage in IMPLEMENTATION and dated evidence below.
Vocabulary: planned, in progress, implemented, CI-verified, owner-accepted, blocked.
A check or source artifact never implies owner acceptance.

## Outcomes and dependencies

| Slice | Observable result | State / prerequisite |
| --- | --- | --- |
| F0 framework | Navigable contracts, focused skills, executable handoff and hosted structural guards | Earlier framework CI-verified at ed4cc8f; refresh in progress, fresh hosted evidence pending |
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
- F0 refresh: source docs, navigation, rule limitations, focused project skills,
  prompt and structural/CI guards updated; no product code changed. Hosted
  verification pending. No local tests/builds/benchmarks/installers were run.
  Existing licences and deployment history retained; Git diff is the rollback.
- Current DSH catalog exposes the eight shared skills only. Their full bodies
  were loaded through this session's DSH loader. Project bodies were read as
  repository references; live project-skill discovery remains unverified.
  A current `prompt-assist` load returned unknown/unavailable; the prompt follows
  the Hub prompting reference without claiming activation.

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
