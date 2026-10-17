# Product implementation tracker

This is the only task tracker. Product intent lives in PRODUCT, planned design in
ARCHITECTURE, source coverage in IMPLEMENTATION and dated evidence below.
Vocabulary: planned, in progress, implemented, CI-verified, owner-accepted, blocked.
A check or source artifact never implies owner acceptance.

## Quality-system reconciliation and documentation gate — implemented, 2026-10-17

Source: branch `codex/h07p-product`, parent `c0ce1bf91d1f6626cc13cfefa457024c9e19c8ca` (this record is committed with
the work). Gate result: `bash tools/acceptance.sh --full` -> `PROJECT_ACCEPTANCE=PASS`
(`make check` 131 tests, `cargo fmt --check`, `cargo clippy --workspace
--all-targets -D warnings`, workspace tests, release build).

Done in this task, with evidence:

1. **Reconciled with `origin/codex/h07p-product`.** The checkout was nine commits
   behind with two local reorganization commits and eight uncommitted files. The
   merge is conflict-free (local and upstream changes touch disjoint paths). The
   uncommitted edits were resolved per file: `helper.rs` and `ROADMAP.md` were
   strictly superseded; `IMPLEMENTATION.md`, `SECURITY.md`,
   `IMPLEMENT-H07P.md` and the credential-guard spec were **byte-identical** to
   upstream (verified by sha256 before discarding); `.gitignore` was kept;
   `deploy/package/dashboard.env` is owner-only and untouched. Applied with
   plumbing because this uid cannot unlink huou07-owned files in the sticky
   `deploy/package` directory; those three files were written in place and
   content-verified. The tree now passes the Clippy gate that previously failed
   at five sites in `helper.rs`.
2. **Authority chain visible.** Every `docs/**/*.md` is indexed in
   `docs/README.md` with a `Current`/`Historical` marker, and
   `tools/check-framework.py` fails on an unindexed document or an unmarked entry
   (verified with negative controls). `docs/prompts/UPGRADE-H07P.md` is committed
   and marked Historical.
3. **Contradictions collapsed.** `IMPLEMENTATION.md` no longer carries tables
   claiming Permissions/Auto Detect/NAS are absent; `SECURITY.md` now names the
   two mutually exclusive arrangements (ordinary-user vs managed worker) up front
   and states which one it describes; `ORDINARY-USER-REINSTALL.md` is Historical
   with a do-not-rerun banner.
4. **Real gates automatic.** New CI jobs `package-lifecycle` (release audit,
   `tests/package` unit tests, `tests/package-lifecycle.sh` install/upgrade/
   rollback/remove/purge, two compared `build-deb.sh` builds, Lintian),
   `native-isolation` (`product.py`, `broker.py`, `guard.py`, `files.py` as root
   with synthetic identities) and `secret-scan` (pinned Gitleaks 8.30.1, checksum
   verified, change-set scoped, redacted). `tests/native/workers.py` is excluded
   with its two failure modes recorded; whole-tree secret scanning is not used
   because it reports 229 findings dominated by the local lab cache.
5. **Test reachability.** `tests/package` is importable, so `make check` now runs
   131 tests instead of 113. The Rust browser lane was measured against
   `dashboard.spec.mjs`: 34 passed, 1 failed at `#sidebar [data-route="system"]`,
   so that lane is not claimed and `VALIDATION.md` states Rust dashboard journeys
   are UNVERIFIED.
6. **Lies deleted.** `.delivery/{ledger,gui-ledger}.json` (tracked, embedding
   `/Users/meomeo`) are removed; `docs/SKILLS.md`, `docs/STATUS.md` and
   `docs/PERFORMANCE.md` moved to `docs/history/` with banners.

Not done, with the next action named:

- **Tracker split (prompt item 6).** `ROADMAP.md` still mixes the 2026-10-15/16/17
  eras and OR/VCE/Flutter work; the dated and cross-project sections have not yet
  moved to `docs/evidence/`. This section is prepended so current state is read
  first, but the split itself is outstanding.
- **One version source and tracing (prompt item 7).** `Cargo.toml` is still 0.1.0
  while the package is 0.3.x, and no `tracing` crate is wired, so a deployed
  failure still cannot be diagnosed from structured evidence.
- **Hosted CI execution.** The three new jobs parse as YAML and their command
  sequences were rehearsed locally or executed in the disposable guest, but no
  hosted runner has executed them yet; hosted coverage is UNVERIFIED.
- **Runtime note.** `dpkg -l huou07-playground` reports 0.3.9 on this host; the
  2026-10-17 section below still narrates the 0.3.7 hotfix era and awaits item 6.

## System-wide permissions, worker tool recovery and live Debian acceptance — in progress, 2026-10-17

The owner authorizes this task to restore/update the missing project tools/docs,
build and deploy H07P on the real Debian host, use H07P's own GUI to reset ACLs
from the saved pre-worker snapshot, detect/create/repair workers and set policy,
then verify the real journeys without a VM. Preserve all project data. Worker
workspaces and permission targets must accept canonical absolute paths anywhere on
the host. Recursive Allow must keep default private stores, detected credentials
and explicit Blocks denied; explicit Blocks win. An exact credential exception
requires a warning acknowledgement and a second Apply. The actual GitHub credential
is authorized for one selected worker solely to test push access. Do not inspect,
log or display its contents; other credentials remain unauthorized.

Source changes currently add system-wide target/workspace validation, broad-home
privacy filtering, exact-file private exceptions, block-last ACL ordering, a
two-step impact challenge, arbitrary-file/directory scans, arbitrary Guard watch
roots, and a GUI ACL reset that uses the existing root-owned snapshot while
preserving bytes. They also address shared runtime read-only ACLs, the DSH Git
config scrubber issue and traversal for exact private-file exceptions.

At the start of this delivery, the active real-Debian release was
`/opt/huou07-playground/releases/0.3.7-acl-inherit-fix/bin/h07p-server`, SHA-256
`90626d3d4ee21d02f36bd2ed58fa61c10e4cce769931094e338894c96b901d3a`. Both
Playground and helper services were active and `/api/health` returned
`{"ok":true}`. That direct Rust hotfix build passed 46 host Rust tests, locked
offline release build and `cargo fmt --all -- --check` with Rust 1.98.0. The ACL
fix only adds default entries for recursive directory rules; nonrecursive rules
leave existing defaults alone.

H07P **0.3.8** is now published from tag [`v0.3.8`](https://github.com/huou07/huou07-playground/releases/tag/v0.3.8),
source `78ecb43b8126e67861fa56bf633551a318c5f1c6`. Exact-tag GitHub Actions
[release run 38999148525](https://github.com/huou07/huou07-playground/actions/runs/38999148525)
passed framework/legacy gates, pinned Rust format/Clippy/tests/release/HTTP smoke,
both 34-test browser lanes, fresh dependency audit, package lifecycle tests,
Lintian and two identical package builds on Ubuntu 24.04. The public amd64 `.deb`
SHA-256 is `bfc2bb4068c09050e21c98752f7be4257639596ea397bfdf597364aab767fbd7`;
the downloaded release checksum was verified. The workflow's lifecycle fixture
uses an isolated synthetic dpkg root, not a full Debian systemd VM install. The
0.3.8 package has not been deployed to the real Debian host.

GUI ACL reset, harness detection, worker repair and the first policy reapply were
done through Playground at **Desired revision 17 · Enforced revision 17**. The
owner reviewed the warnings and confirmed Apply a second time. A later GUI
workspace update set `opencode-worker` to `/home/huou07/Projects/VCE`; the current
policy is **Desired revision 18 · Enforced revision 18**. The enforced rules retain
broad home access with private paths and Blocks protected, exact GitHub-file read
exceptions for `dsh-worker`, writable Flutter build paths and the nonrecursive
`/home/huou07/.rustup/tmp` rule for `codex-worker`. A read-only ACL check shows
direct `-wx` access on `.rustup/tmp` but default `r-x`; the worker can read Rust
1.98.0, create/remove a temp file there and has no sudo group membership. Read-only
worker checks confirm only `dsh-worker` can read the two explicitly allowed
GitHub files; `codex-worker` and `opencode-worker` are denied both. The ACL helper
now adds default ACL entries only for recursive rules. It still skips only missing
paths when restoring old ACL snapshots and fails closed on other errors.

The user-authorized GitHub credential scan found the exact GitHub auth files;
the selected `dsh-worker` exception was set through the GUI, and its push check
succeeded without exposing credential contents. H07P changes are committed and
pushed to `codex/h07p-product` through `78ecb43`; Rustup/Flutter/Playwright/public package and browser
runtime assets were recovered from retained owner sources. The real OR preflight
then passed under `codex-worker`: Linux debug app built, the editor journey passed
in 79.1s, and minimum available RAM was 6,014,963,712 bytes. Its runner temporarily
scopes the bridge manifest to the Linux host target and restores the original
bytes. `pub get --offline --enforce-lockfile` still warns that cached content
hashes differ for many locked packages, but succeeded and left `pubspec.lock`
unchanged. This does not prove package/OS-picker acceptance or other platforms.

The VCE browser lane then passed on the real Debian host under `opencode-worker`
with Playwright CLI 0.1.22 and pinned Chromium 155.0.8059.12 in 12.25s. Its saved
evidence records source `0c3c9d882133c7afea6f5324748ba472882e0f55`, three viewport
screenshots and no browser errors. This uses an existing managed worker; there is
no dedicated `vce-web` profile. VCE native stays intentionally disabled and no
native journey was run.

Tool recovery finding: current AEH capability sources remain under
`/home/huou07/AEH/ops/product-verification/` and their listed source checksums
match. The deployed capability bundle/services and `agents-worker` identity were
intentionally retired; do not reinstall them as an H07P substitute. Legacy paths
and install instructions are now marked retired in AEH. Flutter 3.47.7/Dart
3.13.5, Rust 1.98.0, Playwright CLI 0.1.22, public Dart packages and Chromium
cache were restored from the retained owner backup into shared owner-home paths.
AEH, OR and VCE docs now point to those locations.

## GUI setup and discovery amendment, 2026-10-16 — implemented and Dell package-verified

The owner requests scoped filename search in NAS/Storage; beginner onboarding;
GUI harness detection and managed worker create/edit/disable/delete without
deleting shared home/native data; worker-specific or all-worker policy settings;
on-demand discovery of host localhost/LAN web services and selected shortcuts;
reviewed VPN exposure; selected supported app login export to private NAS
`apps-login-password.md`; and supported password changes with clear adapter limits.
Build/test/deploy on Dell and solo Playwright CLI operation remain authorized.
No background network/subnet or credential harvesting is implied. Native provider
stores stay unchanged. Hash-only passwords cannot be recovered; unsupported apps
need manual entry or their existing administration UI. Root actions stay typed,
owner-authenticated and reviewed. VPN bootstrap must preserve an existing
WireGuard/WG-easy installation and expose external-router limitations honestly.

Implementation proceeds through dependency-safe increments under the frozen
`delivery-authority-gui.json` delegation. Optimization uses repeated baseline and
after measurements, bounded scans/work, no hidden-view polling and a diminishing
returns stop rule; it cannot prove that no conceivable optimization remains.
Historical baseline was 0.2.2. The final 0.3.0 deployment and scoped acceptance are recorded below.

Owner clarification: preserve safety when optimizing. Apps without an existing
password keep their existing authentication behavior; do not add a password,
authentication proxy or other app security mechanism during discovery, shortcut
creation or VPN setup. Existing VPN access controls still apply. Password export
and change adapters only handle explicitly selected apps with existing supported
login mechanisms.

First implementation checkpoint: bounded filename-only NAS/Storage search and
per-worker preset/workspace overrides are implemented. Debian checks passed:
34 Rust unit tests, Clippy, release build, 30 native filesystem checks, 66 native
owner/API checks, 26 browser contract tests, and real sandbox checks including
individual-worker overrides and disabled launches. These checks do not establish
the remaining setup, discovery, worker lifecycle or password GUI outcomes.

Second implementation checkpoint: explicit host-listener web discovery and
reviewed additional-app VPN relay GUI are implemented. Discovery uses at most
64 host sockets, eight bounded HEAD probes at a time, no credentials, no redirects
and no persistent polling. Additional relays bind exclusively to wg0/10.8.0.1,
preserve app authentication, reserve built-in/internal ports, persist privately,
and close active streams on removal. Existing UFW rules must be preserved.
Debian checks passed: 38 Rust tests, Clippy, release build, 69 native PAM/API
checks, 28 browser contracts, and the new isolated-network typed-helper test
covering actual interface denial, stream preservation, revocation and persistence.
An initial test incorrectly treated host-local traffic as LAN ingress; the
discriminating veth/network-namespace check now tests actual foreign-interface
ingress. This is not fresh WireGuard bootstrap, encrypted dynamic-relay acceptance,
GUI worker lifecycle, password management or deployment acceptance. Those remain
open; production remains 0.2.2.

Third implementation checkpoint: selected supported existing public web-login
export and manual existing-login entry GUI save `apps-login-password.md` through
the NAS service actor. No provider/native auth stores are inspected. Empty-password
apps need no entry; export never changes their authentication. New files are 0600,
replacement is version-bound and explicitly confirmed, symlinks/hardlink aliases
are rejected, and ordinary NAS deletion leaves no hidden credential copy. The
initial supported automatic source is the already configured public OpenCode/DSH
LAN bridge login; other logins remain manual/native-app administration. Password
change adapters are still pending. Debian passed 39 Rust tests, Clippy/release,
78 native owner/API checks, 35 private-mount filesystem checks and 29 browser
contracts. Synthetic secrets were checked for response/log leakage. Stream adapter
RSS samples for 16/64 MiB uploads were 4408/4200 KiB; these are memory observations,
not electricity measurements. This increment is not deployed yet.

Fourth implementation checkpoint: the existing public OpenCode web/DSH LAN
bridge login has an explicit password-change GUI. It requires a configured
original login; absent/anonymous apps cannot gain authentication through this
adapter. Native backend/provider credentials remain unchanged. A private root
override persists rotation, new connections use the updated cached login and
active public/backend streams close on rotation. A password export is refreshed
only by a separate explicit export operation. Uncertain post-rename durability
fails closed. Debian passed Clippy/release, 39 Rust tests, 78 native owner/API
checks, 30 browser contracts and 19 isolated typed-helper/network checks including
old/new password acceptance, active backend disconnection, restart persistence,
and refusal to introduce authentication without an original login. These are
synthetic accounts; no production password was inspected or changed. GUI worker
lifecycle, complete onboarding/bootstrap, final measurements and deployment remain
open.

Fifth implementation checkpoint: the setup GUI detects the three supported
harness executables without executing them, reviews selected/all account
create/repair/remove jobs, links individual permission editing, toggles selected
or all worker launches, and starts supported existing web units. Provisioning
reuses the existing metadata/ACL classifier; it does not install apps or rewrite
native auth. Jobs publish a pending policy before stopping workers, preserve ACL
backups and reapply custom rules before marking enforcement complete. Removed
names become locked UID/GID tombstones with retained files; recreation uses new
identities. A private journal repairs interrupted user/group retirement. Metadata
inventory is bounded at 100k entries/15s before changes; job subprocesses are
bounded at 300s. Debian passed 24 isolated actual account/ACL/helper checks,
including failed retirement repair, custom Block reapplication and failed pending
policy recovery; 84 native PAM/API checks; and 32 browser contracts. No production
account was created, removed or reconfigured for these fixtures. Package dependencies
now explicitly include passwd and iproute2. Final packaging, efficiency comparison,
Playwright CLI and deployment remain open.


## Current authorized product integration, 2026-10-15

P1–P7 now have integrated Rust/UI/package implementations on
`codex/h07p-product`; the historical baseline rows below are not current source
coverage. **H07P 0.2.2 is installed and running on Dell Debian**, built from
`55da5e5d8ebc3e7aff4cab4efab58ce2a3dd815c`.
[Deployment evidence](evidence/product-deployed-20261016.md) records package identity,
actual install/update/repair, rollback recovery, runtime UIDs, native tests,
Playwright CLI and nine-service encrypted VPN verification. Earlier
[native evidence](evidence/product-native-20261015.md) remains a dated checkpoint.
This is package/physical-runtime verification, not human Android acceptance,
fresh hosted CI, blanket credential protection or complete energy/performance proof.
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

## Historical P1 planning baseline (superseded by deployed source above)

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

## Resource and safety verification checkpoint, 2026-10-16

Worker preparation now stages bounded metadata in a disposable, root-private SQLite
plan instead of retaining the entire home inventory in RAM. Limits are five million
entries / 300 seconds for inspection and 900 seconds for the reviewed job. Progress
is job-bound; ACL rollback snapshots remain private and completed snapshots persist.
A metadata-only Dell inspection visited 1,319,015 entries in 8.958 seconds, with
15,544 KiB peak RSS; it changed no permissions or account data. Synthetic namespace
tests exercise real account creation, retirement/recreation, disabled preservation,
custom Block reapplication, interrupted repair and worker-owned Block rejection.

Telemetry is route/visibility-aware. Playwright CLI against synthetic PAM sessions
observed nine unrelated API requests in a 16-second NAS baseline window versus zero
with the candidate. NAS list median/p95 observations were 9.3/11.8 and 9.8/12.5 ms
baseline, 10.1/12.8 ms candidate; these small differences do not establish a latency
improvement or an electricity saving. Candidate GUI discovery, selected login
export defaults, filename search and mobile worker layout passed without page errors.
Generated login files support version-bound selected-entry merge; manual edits
disable automatic merge and require explicit replacement. No authentication is
added to anonymous apps. Packaging/deployment acceptance remains pending here.

## GUI deployment acceptance — 0.3.0

Source `0378a1d` was packaged reproducibly, passed Lintian, and installed on Dell
through the guided updater. Doctor reports 0.3.0 and all four managed services
active. Real encrypted WireGuard transport passed all nine declared services and
the 70,642-byte GUI asset. Three installed-candidate Playwright CLI runs each had
zero unrelated NAS-view requests; synthetic authenticated GUI and mobile checks
passed. Final verification: 41 Rust tests, Clippy, 105 legacy checks, 85 native
PAM/API checks, 37 filesystem checks, 27 account/ACL checks, 19 dynamic relay
checks, 31 Guard checks, 34 browser contracts and actual sandbox/cgroup/package
lifecycle fixtures. Production metadata checks confirm three distinct worker UIDs,
shared home, no sudo and protected store denial without reading credential values.

[Deployment evidence](evidence/gui-deployed-20261016.md) records exact artifacts,
measured resource observations and limits. This completes the Dell GUI amendment
within the supported adapters; it is not human Android acceptance, arbitrary-app
password recovery or universal fresh VPN/router bootstrap. Frozen delegation state
remains owner-controlled.

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


## Owner amendment — installer and Credential Guard, 2026-10-16

The owner requests a beginner-friendly install/update/dependency diagnosis/repair/
uninstall flow and safe cleanup of secret-bearing logs, prefers solo execution
and Playwright CLI, and renews authorization for bounded synthetic testing and
deployment on Dell Debian. The supplied Guard proposal is advisory; adopted scope
and compatibility decisions are in
[Guard integration](security/credential-guard/INTEGRATION.md). P0 metadata/access
audit is recorded; the guided installer and Guard are implemented and deployed in
0.2.2. Guard content scanning is opt-in; cleanup requires a reviewed closed export.
Existing native authentication stays unchanged and its same-UID
limitation is explicit. This amendment extends the current delivery rather than
canceling the original P1–P7/VPN/deployment objective.
