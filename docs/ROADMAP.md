# Product implementation tracker

This is the only task tracker. Product intent lives in PRODUCT, planned design in
ARCHITECTURE, source coverage in IMPLEMENTATION and dated evidence below.
Vocabulary: planned, in progress, implemented, CI-verified, owner-accepted, blocked.
A check or source artifact never implies owner acceptance.


## Current authorized product integration, 2026-10-15

P1–P7 now have integrated Rust/UI/package implementations on
`codex/h07p-product`; the historical baseline rows below are not current source
coverage. [Native evidence](evidence/product-native-20261015.md) records the exact
executed boundaries and remaining release gates. This delivery is **in progress**:
production cutover, final package/advisory checks and VPN verification are pending.
The earlier permissive shared-home model remains the default `none` preset.

## Historical outcomes and dependencies at the planning baseline

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
synthetic; the existing Python registry journey is retained. Exact product source
`dee548fc9175b4b2b1e5c740f359f0cf8a763147` passed all four jobs in
[hosted run 38678354948](https://github.com/huou07/huou07-playground/actions/runs/38678354948):
framework, existing checks, Python browser and actual Rust browser. Both browser
lanes passed four tests, including the stable Theme combobox name regression.
This accepts those scoped contracts, not backend read parity or visual polish;
the retained screenshots still need human/vision review.

Local OS lab design and preflight are in
[VALIDATION](VALIDATION.md#disposable-local-os-security-lab). No guest or live
security test ran. The owner subsequently installed the dedicated h07p-lab
account (UID 985) and verified KVM API 12; the normal worker intentionally has
no KVM membership. The immutable Debian base and synthetic seed are still
missing, so the registered lab profile remains disabled. The installed snapshot
service needs the reviewed Hub owner upgrade before protected history is usable.
P2/P3 product enforcement is still unimplemented. No self-hosted runner or live
production policy was introduced. The implementation prompt records current
standing publication authority and the actual local lab boundary.

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

## Owner-requested Mac intake and Debian harness account migration, 2026-10-15

Scope: merge the Debian source/working changes into the existing Mac project,
preserve the Mac migration history, and deploy three permissive shared-home
harness users. This is separate from implementing the future Rust policy/NAS
product. The owner authorizes Debian build/test execution and the host cutover
for this task; native harness login/model calls are excluded from acceptance.

Source intake preserved Mac `58106d8` and Debian `805861c` through merge
`ff873ef`; Debian's two modified files and five untracked hardening files are
preserved in `96121b7`. Mac's previous branch is retained as
`backup/macos-before-debian-20261015`; Debian's previous dirty tree is retained
in its named pre-integration stash. Neither history was reset or replaced.
The shared working branch is `codex/debian-harness-acl`.

Implemented and deployed on Debian: `dsh-worker` (UID 995), `codex-worker`
(994), `opencode-worker` (993), each with `/home/huou07` as HOME. Existing CLI
installations are reused. The DSH/OpenCode owner user services are disabled;
`h07p-dsh.service` and `h07p-opencode.service` run under their respective UIDs.
Codex has an owner entry point without starting a daemon or signing in.
See [the account/ACL implementation](../deploy/harness-workers/README.md) for
the exact direct-access guarantee, private inventory, native store ownership,
Git shared-home trust, npm configuration, ancestor protection and rollback.

Real host evidence: ACL cutover inventoried 1,259,492 shared paths, 32,103
read-only paths, 803 private boundaries and six native store roots after
creating the private owner secret directory. The original root-only ACL/owner
snapshot is `/var/backups/h07p-harness-workers/20261015-220803/acl.restore`.
No credential contents were copied into the snapshot or into the Mac checkout.
Private denials were reconciled after shared grants, including a hardlink
regression; the additional credential filename sweep found no extra matches.

Verification on Debian:

- Real-UID verification: 119 assertions passed for shared create/read/edit/
  rename, project AGENTS/skills access, shared installed launchers, Git trust,
  cross-harness denial of synthetic native secrets, owner secret denial,
  rename-substitution denial, sudo/owner switching/Docker denial and actual
  running service UID/no-new-privileges/process-environment separation.
- Existing Python/shell checks, Rust 1.90 locked format/Clippy/test/release
  build and real HTTP smoke passed. Rust has four unit tests; the Python suite
  includes the account-policy regressions.
- Python browser lane: four tests passed. Actual Rust browser lane: four tests
  passed. These preserve the previously scoped UI/health/static acceptance;
  synthetic browser APIs do not establish unimplemented Rust read parity.
- Live HTTP checks returned 200 for dashboard health, metrics, apps, VPN,
  files, LiteLLM readiness and OmniRoute health. DSH/OpenCode and the owner
  launch endpoint rejected unauthenticated access with 401. Both new system
  units parsed successfully and ran without automatic restarts at inspection.

The pinned Rust 1.90 toolchain and the locked browser test runtime were prepared
once under the shared owner installation for these authorized tests. No separate
harness app installation, external model/API call, native CLI login or claim of
complete future P2/P3 enforcement was made. New public-mode secrets in arbitrary
shared files and indirect attacks through owner-executed shared code remain
limitations of the expressly requested permissive model. Future private owner
data belongs in the protected stores, especially `~/.secrets`.

## Android VPN timeout investigation, 2026-10-15

The owner reports Android WireGuard timing out at `http://10.8.0.1:8765/`.
Mac requests through WireGuard succeed; that does not establish Android access.
Server listeners and UFW cover all nine declared private service ports. Packet
headers show peer `10.8.0.2` reaching dashboard TCP and the server sending replies.
This disproves a blanket missing-listener/firewall diagnosis for that peer.
Large responses were retransmitted. The server wg0 MTU was first temporarily
reduced from 1420 to 1280. The owner confirmed Android is `10.8.0.2/32`, endpoint
`123.21.137.86:3478`, allowed destination `10.8.0.1/32`. A subsequent packet-header
capture at 23:00 showed Android acknowledging large response blocks and opening
multiple follow-up resource requests, unlike the earlier retransmission stall.
This supports the mobile-path MTU diagnosis; visual confirmation from the phone
is still pending. The server/interface and future-profile default MTUs were
then saved as 1280 in wg-easy and its generated config without restarting the
tunnel. Existing endpoint, addresses, peers and keys were preserved. The
[MTU utility](../deploy/configure-wg-mtu.py) retains numeric-only rollback values
under `/var/backups/h07p-wg-mtu/`; no key copies are made.

A separate real failure was fixed: OmniRoute API/live listeners were bound to
container loopback, unreachable from Podman's published ports. The existing
Quadlet now binds those listeners to the container interface and permits the
VPN dashboard origin. Host publication remains on 127.0.0.1 and existing wg0
relays; no LAN/public port publication was introduced. The owner Quadlet was
updated and only OmniRoute restarted, retaining its data and Redis pod.

Actual Mac-over-WireGuard evidence after deployment: dashboard 200, Cockpit
HTTPS 200, LiteLLM 200, wg-easy 302, DSH/OpenCode 401, OmniRoute web health 200,
API `/v1/models` 401 (previously empty connection), live HTTP 404 (previously
empty connection). The live WebSocket accepts an upgrade then rejects a foreign
origin with `FORBIDDEN_ORIGIN`, and the permitted VPN origin without a login
with `UNAUTHORIZED`; these are authentication checks, not model/API calls.
Authenticated native/model workflows and Android UI acceptance remain
unverified. Runtime, saved interface config and saved default were each read
back as 1280. Reboot persistence is configured, not reboot-tested. For rollback,
restore the numeric interface/default values from the utility's root-only JSON
record, replace only the MTU line in `wg0.conf`, then set the live interface MTU
to the restored value. Never dump the WireGuard configuration or database keys.
