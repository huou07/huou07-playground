# H07P comprehensive upgrade — owner plan and authority

Owner authority, 2026-10-17: you may commit, push to `origin`, open pull requests,
merge after required checks, tag and publish a verified GitHub release without
asking again. You may stop and restart the production Playground **only** through
a documented, gated release of this project — never by hand. Inside the isolated
guest VM, root is allowed; on the Debian host it is not. Do not read owner
credentials, private NAS content or personal media.

## Verified host facts before you start (do not re-derive)

- Production runs playground **0.3.7** installed through dpkg; all four units are
  active and the GUI answers `{"ok":true}` on `127.0.0.1:8765`.
- **This checkout is 7 commits behind `origin/codex/h07p-product`.** Those commits
  include `Fix recursive ACLs and publish gated Debian releases`, release Clippy
  fixes, host-account-independent ACL tests and 0.3.8 CI release evidence. This
  working tree also carries five uncommitted changes that overlap them
  (`crates/server/src/helper.rs`, `deploy/package/dashboard.env`,
  `docs/{IMPLEMENTATION,ROADMAP,SECURITY}.md`). Integrate deliberately: fetch,
  inspect, reconcile or preserve, and record the decision. Never force-push and
  never discard either side.
- **No VM exists yet**: `virsh list --all` is empty, this uid is in neither the
  `libvirt` nor the `kvm` group, `/dev/kvm` is `root:kvm 0660`, and
  `/var/lib/h07p-security-lab/{base,fixtures,runs}` plus `/var/lib/h07p-lab-home`
  are not readable to it. Expect to stop at the VM privilege boundary and request
  one narrowly scoped owner action; do not work around it on the host.
- The published `v0.3.7` and `v0.3.8` GitHub releases already carry
  `huou07-playground_<version>_amd64.deb`, its `.sha256`, `sbom.cdx.json`,
  `report.json`, `licenses.json` and `h07p-install.sh`, so the packaging and
  release-audit path is real and CI-driven. `tools/build-deb.sh` additionally
  needs a pre-built ELF and the owner-only `deploy/package/dashboard.env`, so a
  worker cannot run it in place — that is by design, not a defect to paper over.
- `git` works. `gh` is authenticated as `huou07` through an owner-approved
  exact-file exception and can publish this repository. The retired `aehctl`
  capability broker and the `agents-worker` account are **not** part of the
  current design; do not reinstall them.
- `~/.cargo` is not writable by this uid; the project toolchain 1.90.0 is
  installed. Use a project-local `CARGO_HOME` when a build must write.
- No Android SDK, NDK, `adb`, AVD or emulator exists on this host.

## Resource discipline

Keep `MemAvailable` healthy and never push the host into swap pressure or OOM to
finish a benchmark. Production services on this machine outrank lab work. Bound
every job's memory, CPU, disk growth and wall-clock time, and clean up whole
process groups.

---

PROJECT: Huou07 Playground (H07P)

TASK:
Comprehensive architecture hardening, security remediation,
Auto Detect modernization, agent/harness extensibility,
performance optimization, portability, validation and release.

Repository:
https://github.com/huou07/huou07-playground

Current known production version:
v0.3.7

Last observed public main:
4b95001e2ad5905281816f928bda1e97bab49e79

Host:
Dell OptiPlex Debian Linux server.

Production:
Huou07 Playground is already installed and actively used.

CRITICAL OBJECTIVE:

Implement and verify the best maintainable solution for all
confirmed issues and technical limitations described below.

All development, builds, integration tests, security tests,
benchmarks, installation tests and acceptance testing MUST
happen in an isolated, disposable Debian virtual machine.

Do not modify the production Playground installation.

After local VM acceptance passes:

1. Push the implementation to a dedicated GitHub branch.
2. Open a pull request.
3. Run authoritative GitHub CI.
4. Fix any genuine failures.
5. Merge after required verification.
6. Create a new version tag.
7. Build and publish a verified GitHub release.

This is one continuous end-to-end engineering task.

Do not stop after planning.
Do not stop after implementation.
Do not stop after unit tests.
Do not claim completion merely because the application builds.

Continue through all stages unless a genuine security,
permission, infrastructure or verification blocker exists.

============================================================
0. NON-NEGOTIABLE OPERATING RULES
============================================================

PRODUCTION MUST REMAIN UNCHANGED.

Never:

- Stop or restart production Playground services.
- Restart production DSH, OpenCode or Codex.
- Modify production LiteLLM or OmniRoute.
- Modify production ACLs.
- Modify host user accounts or groups.
- Modify production systemd units.
- Modify production databases.
- Read production credentials.
- Read production NAS files.
- Copy production HOME into the VM.
- Mount production directories into the VM.
- Modify host WireGuard or network relays.
- Change production Docker/Podman containers.
- Install an experimental application over production.
- Run destructive or stress tests on the host.
- Use production as a self-hosted GitHub CI runner.
- Delete or reset existing worktrees.
- Discard uncommitted work.
- Introduce test backdoors into production.

Read-only host resource inspection is allowed.

Read-only production configuration/source metadata inspection
is allowed when needed to understand provenance, provided
no private content or credentials are accessed.

All writes must stay within the dedicated VM workspace,
its explicitly allocated virtual disk, and the approved
GitHub development branch.

If VM creation requires host-level modifications, stop
at that specific privilege boundary and request owner
approval for the narrowly scoped virtualization operation.

Never grant unrestricted host sudo to an AI worker.

Inside the isolated VM, root privileges are permitted
for testing Linux security mechanisms.

Do not confuse guest root with host root.

Use verified open-source implementations wherever possible.

Do not invent unnecessary frameworks or abstractions.

Do not select Rust, Python, Go or another language merely
because it appears faster in theory.

Preserve the existing working Rust/Axum architecture unless
evidence demonstrates that a specific component requires
replacement.

Avoid unnecessary rewrites.

Do not add unsafe Rust to bypass compiler errors.
Do not suppress tests, warnings or CI failures.
Do not weaken security checks to make tests pass.

Use the existing H07P AGENTS.md, skills and development
contracts where they do not conflict with these requirements.

============================================================
1. DISCOVER AND ESTABLISH BASELINE
============================================================

Inspect the latest public repository and verify main HEAD.

Use a new isolated development checkout.

Do not modify the production source checkout.

Read:

README.md
AGENTS.md
docs/ARCHITECTURE.md
docs/SECURITY.md
docs/IMPLEMENTATION.md
docs/VALIDATION.md
docs/ROADMAP.md
docs/STATUS.md

Inspect the actual implementation, especially:

crates/server/src/api.rs
crates/server/src/helper.rs
crates/server/src/sandbox.rs
crates/server/src/broker.rs
crates/server/src/guard.rs
crates/server/src/scan.rs
crates/server/src/files.rs
crates/server/src/worker_setup.rs
crates/server/src/native_proxy.rs
crates/server/src/relays.rs
crates/server/src/telemetry.rs

deploy/package/
deploy/harness-workers/
web/static/
tests/
.github/workflows/

Discover additional relevant modules rather than assuming
the above list is complete.

The previous source synchronization intentionally excluded
five uncommitted changes:

crates/server/src/telemetry.rs
tests/e2e/product.spec.mjs
tests/test_app.py
web/app.py
web/static/app.js

Do not discard or blindly incorporate these changes.

Determine whether they represent independent unfinished
work or fixes that must be reconciled.

Do not read production-private data while doing so.

Create a baseline report containing:

- Exact source SHA.
- Component inventory.
- Existing security boundaries.
- Existing test coverage.
- Known limitations.
- Dependency versions.
- Baseline CPU/RAM/I/O measurements.
- Existing package and release behavior.

Distinguish confirmed code defects from unverified concerns.

============================================================
2. CREATE A FULLY ISOLATED DEBIAN LAB
============================================================

First inspect the host without changing it.

Check:

- Available RAM.
- Available disk space.
- CPU topology.
- KVM availability.
- Existing virtualization capabilities.
- Storage filesystem.
- Host load.
- Whether virtualization dependencies are already installed.

Preferred environment:

QEMU/KVM with a dedicated Debian amd64 VM.

Use a pinned Debian image and verify its origin/checksum.

Suggested VM identity:

h07p-lab

Use a dedicated qcow2 disk.

Do not reuse any production VM, container, image or volume.

Do not mount:

/home/huou07
/opt/huou07-playground
/var/lib/huou07-playground
/var/lib/h07p-control
/var/lib/h07p-private
/run/docker.sock
/run/podman/podman.sock

or any host credential store.

No host secrets are permitted in the guest.

Use synthetic usernames and synthetic credentials.

Resource limits:

- Derive VM CPU/RAM limits from actual free resources.
- Preserve sufficient capacity for production services.
- Limit guest memory and CPU.
- Limit virtual disk growth.
- Avoid host swap/OOM pressure.
- Stop heavy lab workloads if production resource
  headroom becomes unsafe.

Do not assume a specific RAM size.

The VM must have its own:

- Kernel.
- systemd.
- User/group database.
- Filesystem.
- ACL environment.
- Test NAS.
- Test services.
- Test workers.
- Application state.

Network requirements:

- Do not bridge the VM directly onto the production LAN.
- Do not expose guest test services to the public Internet.
- Do not allow access to production WireGuard endpoints.
- Do not connect to real provider APIs.
- Permit only necessary dependency downloads from
  verified sources during provisioning.
- Prefer offline operation for security acceptance tests.

Use a baseline VM snapshot.

Use additional snapshots before dangerous tests.

Install build tools and test dependencies inside the guest.

If KVM is unavailable, investigate a compatible isolated
VM alternative.

Do not silently substitute an ordinary Docker/Podman
container for tests requiring an independent kernel.

If a genuine full-VM environment cannot be created safely,
report the blocker instead of testing on production.

============================================================
3. ESTABLISH LOCAL BASELINE TESTS
============================================================

Before changing the implementation:

Build the existing v0.3.7 source inside the VM.

Run all currently supported tests.

Create synthetic H07P installations.

Use at least two owner identities:

- A fixture representing the historical huou07 layout.
- A different normal Linux username.

Use fake DSH/OpenCode/Codex installations.

Use fake authentication stores.

Use fake NAS data.

Verify that the current application behaves according
to its documented features.

Measure baseline:

- Build duration.
- Idle CPU.
- Idle memory.
- Request CPU.
- API latency.
- GUI page transitions.
- Filesystem traversal.
- Auto Detect latency.
- Gitleaks invocation overhead.
- ACL snapshot.
- ACL apply.
- Worker restart.
- Package install.
- Package rollback.

Do not infer performance from disk capacity alone.

Separate file count, directory count, content bytes,
metadata operations and external process overhead.

Record exact VM/kernel/source/toolchain identity.

============================================================
4. PRIVILEGE SEPARATION AND SECURITY HARDENING
============================================================

Audit the current root helper.

Identify every function requiring root.

Separate privileged and unprivileged responsibilities.

Targets:

- Privileged policy application stays narrowly scoped.
- Linux account maintenance stays narrowly scoped.
- Network relay handling should run without root
  wherever technically possible.
- HTTP/WebSocket parsing should not execute in the same
  privileged security context as ACL mutation unless
  independently justified.
- Credential monitoring should use minimal privileges.
- Authentication secrets must not be exposed to workers.

Prefer multiple execution modes of the existing binary
over creating unnecessary services or frameworks.

Review:

- SO_PEERCRED checks.
- Unix socket ownership/modes.
- Broker socket accessibility.
- Request size limits.
- Queue limits.
- Connection limits.
- Timeouts.
- Rate limiting.
- IPC authentication.
- Root helper error handling.
- Privileged subprocess execution.
- Environment sanitization.
- File descriptor inheritance.
- Process capabilities.
- no_new_privs.
- Landlock.
- AppArmor where appropriate.
- cgroup isolation.

Review broker.sock mode 0666.

Determine whether less permissive access is practical.

A world-accessible socket must not enable policy mutation,
resource exhaustion or privileged action through an
unexpected protocol path.

Test local untrusted principals.

Do not simply chmod the socket and break legitimate workers.

Fix verified vulnerabilities.

Preserve legitimate IPC functionality.

============================================================
5. WORKER, ACL AND POLICY CORRECTNESS
============================================================

Review the complete policy lifecycle:

Draft
→ Dry-run
→ Owner confirmation
→ Snapshot
→ Worker stop
→ ACL enforcement
→ Verification
→ Worker restart
→ Audit record.

Ensure crashes cannot falsely report policy enforcement.

Ensure stale policy revisions cannot overwrite newer ones.

Preserve deny precedence.

Verify:

- ACL masks.
- Default ACL inheritance.
- Parent-directory traversal.
- Directory write/create/delete semantics.
- File ownership.
- Symlinks.
- Hardlinks.
- Bind mounts.
- Filesystem boundaries.
- Open file descriptors.
- Process descendants.
- Revocation.
- Concurrent owner changes.
- Rollback conflicts.
- Partial failures.
- Worker task cancellation.

Do not claim that POSIX ACL independently enforces
operations which Linux DAC cannot distinguish.

Do not claim that blocking execute prevents interpreters
from reading executable scripts.

Use Landlock or existing Linux facilities when a real
security requirement cannot be represented by ACL alone.

Never invent unsupported enforcement guarantees.

ACL execution must remain transactional at the policy level.

Parallelism is allowed only where independent mutations
and recovery semantics have been demonstrated.

============================================================
6. CREDENTIAL PROTECTION
============================================================

Review protected credential stores.

Review same-UID credential exposure.

Investigate separation between:

- Agent command execution.
- Harness authentication.
- Provider credentials.
- Credential broker or API gateway.
- Privileged H07P services.

Prefer separation through existing operating-system
identities, services and supported provider interfaces.

Do not move real provider credentials during development.

Do not patch real authentication stores.

Inside the VM, use fake providers and fake tokens.

A virtual LiteLLM key remains a secret.

Do not treat a virtual key as permission to expose the
underlying provider account without limits.

Do not claim same-UID credentials are hidden if the
untrusted shell still has direct read access.

Audit:

- /proc memory interfaces.
- ptrace.
- Environment exposure.
- Core dumps.
- Crash logs.
- Disk swap.
- ZRAM writeback.
- Device permissions.
- Container-management sockets.

Do not introduce a memory-dumping credential scanner.

Do not require continuous full-RAM scanning.

Keep prevention and detection as separate concepts.

============================================================
7. REBUILD AUTO DETECT INTO A MAINTAINABLE SYSTEM
============================================================

Preserve the existing GUI and user workflow.

Do not replace the Permissions system with a separate
unrelated security application.

The new detection architecture should contain:

A. Sensitive File Registry.
B. Metadata scanner.
C. Content scanner adapter.
D. Optional deep-scanning capabilities.
E. Incremental scan cache.
F. Realtime filesystem event handling.
G. Coverage accounting.
H. Owner review.
I. Policy dry-run and enforcement integration.

Separate detection from enforcement.

Detection never directly grants new access.

Unknown content must never become ALLOW automatically.

------------------------------------------------------------
7.1 SENSITIVE FILE REGISTRY
------------------------------------------------------------

Implement a versioned registry of sensitive locations
and file types.

Include broad categories:

- SSH/GPG keys.
- Cloud credentials.
- OAuth stores.
- Browser profiles.
- Password databases.
- Private certificates.
- API configuration files.
- Container authentication.
- Package manager credentials.
- CI/CD credentials.
- Database credentials.
- Session stores.
- Application authentication databases.
- Backup archives.
- Private application state.
- Sensitive user-selected locations.

Use generic Linux rules and application-specific adapters.

Do not assume the username is huou07.

Do not depend only on filenames.

Use path context, metadata and format signatures.

Recognize sensitive containers even if their contents
are encrypted or unreadable.

Do not attempt to decrypt user files.

Unknown encrypted data must remain unclassified or
protected according to its container type.

Avoid broad filename patterns that block normal project
work unnecessarily.

Use explicit confidence and reason classifications.

------------------------------------------------------------
7.2 CONTENT DETECTION
------------------------------------------------------------

Keep the current maintained Gitleaks rules as a baseline.

First verify the exact installed Gitleaks version.

Run synthetic known-positive and known-negative canary tests
using the exact production invocation mode.

Pay particular attention to detect --pipe compatibility.

A scanner returning success while missing a known fake
credential must fail its acceptance test.

Evaluate these existing tools:

- Gitleaks.
- Betterleaks.
- TruffleHog in offline no-verification mode.
- detect-secrets.
- Trivy for container-specific use cases.

Optional format-specific engines may be considered only
when their value is demonstrated.

Do not run every scanner on every file by default.

Benchmark:

- Detection coverage.
- False positives.
- False negatives on known fixtures.
- Throughput.
- Startup overhead.
- RAM.
- CPU.
- I/O.
- Archive handling.
- Cancellation behavior.
- Offline privacy.

Prefer one efficient primary scanner with selected
complementary detectors.

Betterleaks is a candidate, not a predetermined winner.

Do not blindly replace Gitleaks.

Avoid one process spawn per small file when a safer,
more efficient batch or streaming approach exists.

Do not send real credentials to external verification APIs.

Do not store matched secret values in reports.

Use synthetic examples for CI.

------------------------------------------------------------
7.3 SCAN TYPES
------------------------------------------------------------

Support:

QUICK SCAN:
- Metadata.
- Known sensitive locations.
- New/changed files.
- Incremental cache.
- Low resource cost.

DEEP SCAN:
- Explicit owner-selected scope.
- Configurable content limits.
- Archive scanning where supported.
- Optional supplementary detectors.
- Coverage and skipped reasons.
- Bounded CPU/RAM/I/O.
- No automatic policy application.

REALTIME MONITORING:
- Kernel filesystem events.
- Cache invalidation.
- New file/directory handling.
- Watcher overflow detection.
- Reconciliation after lost events.
- Honest degraded status.

Do not claim inotify is a pre-read access control.

Continue to rely on OS enforcement for prevention.

------------------------------------------------------------
7.4 INCREMENTAL CACHE
------------------------------------------------------------

Use the existing SQLite ecosystem unless evidence
justifies another database.

Store sanitized metadata such as:

- Stable filesystem identity.
- Path.
- Size.
- Modification/change timestamps.
- Scanner identity/version.
- Ruleset version.
- Detection result category.
- Last verified time.
- Coverage state.

Do not store raw credentials.

Invalidate appropriately when:

- File identity changes.
- Content changes.
- Files are replaced.
- Filesystem is remounted.
- Scanner version changes.
- Ruleset changes.
- Watched events are lost.
- A scan scope changes.

A cached negative result is not proof that a file is safe.

Revalidate filesystem identity before applying policy.

------------------------------------------------------------
7.5 PARALLEL SCANNING
------------------------------------------------------------

Use bounded concurrency.

Compare:

1 worker.
2 workers.
4 workers.

Evaluate larger concurrency only if benchmarks justify it.

Parallelize independent work such as:

- Metadata classification.
- Independent directory inventory.
- Eligible content analysis.
- Scan-result aggregation.
- Read-only policy planning.

Preserve a bounded work queue.

Apply backpressure.

Never create one thread per file.

Do not let scanners overload the Debian host.

In production defaults, prioritize responsiveness and
low background resource usage over peak throughput.

Do not parallelize overlapping ACL mutations blindly.

------------------------------------------------------------
7.6 SCAN JOBS AND GUI
------------------------------------------------------------

Replace long blocking scan requests with a cancellable
job model if needed.

Expose:

- Job ID.
- Phase.
- Progress.
- Objects visited.
- Directories visited.
- Eligible files.
- Content files scanned.
- Bytes actually read.
- Skipped objects.
- Unknown objects.
- Detection count.
- Errors.
- Elapsed time.
- CPU/RAM/I/O estimates where available.
- Cancellation state.
- Coverage status.

Cancellation must stop server-side work.

Do not merely abort the browser HTTP request.

Preserve the owner review workflow.

No automatic blanket ALLOW.

No automatic destructive quarantine.

GUI must distinguish:

SENSITIVE
NO_FINDING
UNKNOWN
SKIPPED
PARTIAL
ERROR
ENFORCED
NOT_ENFORCED

Do not use a green "safe" indicator when content was
not actually classified.

============================================================
8. GENERIC HARNESS DISCOVERY AND REGISTRY
============================================================

Remove unnecessary hardcoded assumptions about the three
existing harnesses.

Design a small, maintainable Harness Registry.

Keep compatibility with:

DSH
OpenCode
Codex

Add a safe mechanism for describing additional harnesses.

Candidate future integrations include:

Claude Code
Gemini CLI
Aider
Goose
OpenHands
Other CLI/ACP-capable tools

Do not promise unrestricted support for every agent.

Distinguish:

DETECTED:
Executable, package or service metadata found.

SUPPORTED:
A compatible adapter exists.

MANAGED:
Owner enabled it with a verified worker identity.

ISOLATED:
The tested sandbox and permissions are enforced.

Do not automatically execute unknown binaries.

Do not automatically grant arbitrary programs root
or host-level permissions.

Registry entries should describe:

- Harness identifier.
- Executable discovery.
- Expected executable ownership.
- Supported launch modes.
- Native data locations.
- Credential store boundaries.
- Worker identity requirements.
- Workspace rules.
- Temporary storage needs.
- Network requirements.
- Service lifecycle.
- Health checks.
- Compatibility tests.

Discovery must be read-only.

Worker creation requires owner confirmation.

Actual managed isolation requires adapter acceptance.

Sub-agents inherit their parent worker's security context
unless a separate supported principal is deliberately
configured.

Do not infer a separate kernel security identity merely
from an agent's logical name.

Use one additional synthetic harness fixture to prove
the registry can be extended without rewriting the core
policy engine.

Retain functional parity for DSH, OpenCode and Codex.

============================================================
9. PORTABILITY AND INSTALLATION CORRECTNESS
============================================================

Remove host-specific assumptions where appropriate.

Especially inspect:

- Hardcoded /home/huou07 paths.
- Hardcoded owner username.
- Hardcoded worker executable paths.
- Hardcoded native stores.
- Hardcoded ACL backup paths.
- Host-specific service unit assumptions.
- Root-owned configuration path validation.

Discover the actual owner identity through a trusted
installation configuration and Unix account lookup.

Never trust worker-controlled environment variables
for privileged path resolution.

Preserve explicit trust boundaries.

Fix the hardcoded ACL snapshot dependency.

Known historical path:

/var/backups/h07p-harness-workers/20261015-220803/acl.restore

Replace it with a validated, versioned snapshot registry
or another auditable recovery mechanism.

Do not select arbitrary backup files.

Verify:

- Snapshot ownership.
- File type.
- Parent-directory trust.
- Policy identity.
- Checksum.
- Version compatibility.
- Recovery ordering.
- Rollback safety.

Test installation using a username other than huou07.

Avoid fixed ports that conflict with unrelated applications
unless they are explicit and configurable.

Preserve existing user data on upgrade/remove.

No destructive data purge behavior.

============================================================
10. VERSION AND SOURCE PROVENANCE
============================================================

Synchronize:

- Application version.
- Cargo package metadata where applicable.
- Debian package version.
- Git tag.
- Source revision.
- Build metadata.
- Release notes.

Provide a safe way to inspect version and build provenance.

Do not expose hostname, credentials, private paths
or authentication material.

The running binary must be traceable to a source commit.

Do not claim a byte-identical production rebuild unless
the artifact hashes actually match.

Do not alter the existing v0.3.7 tag.

Choose a new version appropriate to the verified changes.

============================================================
11. PERFORMANCE OPTIMIZATION
============================================================

Profile before optimizing.

Investigate the reported approximately two-minute
scan or permission operation.

Do not assume the entire 270 GB was read.

Measure:

- Number of filesystem objects.
- Directory count.
- Actual bytes read.
- Metadata traversal duration.
- Content scanner duration.
- External process startup overhead.
- ACL snapshot duration.
- ACL apply duration.
- Verification duration.
- Worker restart duration.
- Total elapsed time.

Use synthetic workloads representing:

- Few large files.
- Many small files.
- Source repositories.
- Dependency trees.
- Nested directories.
- Sparse large files.
- Mixed file types.
- Archive files.
- Unreadable paths.
- Symlinks and hardlinks.

Do not create a 270 GB physical test dataset merely
because the production drive has that capacity.

Use bounded synthetic datasets representative of object
count and filesystem behavior.

Compare baseline and candidate on the same guest,
same resources, same filesystem and same dataset.

Separate cold-cache and warm-cache measurements.

Measure:

p50
p95
p99
maximum
sample count
CPU time
wall time
peak RSS
I/O bytes
process count

Use sufficiently many samples for meaningful percentiles.

If sample counts are too small for a reliable p99,
report that limitation.

Optimize proven bottlenecks.

Do not introduce complex lock-free queues, custom thread
schedulers or unsafe memory tricks without measurable need.

Prefer bounded work queues, ordinary threads and standard
libraries when sufficient.

Parallel ACL application must preserve correct policy
ordering, rollback and object-identity validation.

A faster implementation that weakens authorization fails.

A more complex implementation without meaningful benefit
should not replace a simpler working one.

============================================================
12. REALTIME GUARD RELIABILITY
============================================================

Preserve the current bounded watcher design.

Improve where justified.

Test:

- Inotify queue overflow.
- Watch exhaustion.
- Directory creation.
- Directory move.
- Rename.
- File replacement.
- Log rotation.
- Partial writes.
- Scanner failure.
- Daemon crash.
- Daemon restart.
- Filesystem remount.
- Loss of watch coverage.
- Large event bursts.
- Reconciliation.
- Scanner cancellation.

Do not silently drop events and report HEALTHY.

Use explicit degraded states.

Keep event metadata sanitized.

Do not store matching secret text.

Do not perform destructive cleanup automatically.

Do not continuously scan process RAM.

Keep mandatory kernel restrictions independent of
watcher uptime.

If fanotify is considered, evaluate its privilege and
operational costs in the VM.

Do not add fanotify permission interception merely
because it appears faster or more powerful.

============================================================
13. AUTHENTICATION AND INTEGRATIONS
============================================================

Regression-test all existing integrations using synthetic
services and credentials.

Test:

- DSH Web launch and reconnect.
- DSH CLI operations.
- OpenCode Web.
- OpenCode CLI/ACP.
- Codex CLI/ACP.
- Worker process lifecycle.
- Terminal/PTY support.
- Native login storage boundaries.
- Session resume.
- Cancellation.
- Tool execution.
- VPN relay behavior.
- HTTP/WebSocket/SSE compatibility.
- LiteLLM and OmniRoute integration contracts.

Do not connect to real model APIs.

Do not copy existing native auth stores.

Do not force users to relogin merely to satisfy an
unrelated security change.

If OpenCode Go through LiteLLM/DSH is covered by an
existing integration contract, verify dynamic
x-opencode-session forwarding with synthetic requests.

Do not use a static session ID across conversations.

Do not patch third-party harness internals unnecessarily.

If a provider-specific behavior cannot be verified offline,
mark live-provider acceptance as requiring later owner
validation; do not request the real key.

============================================================
14. INDEPENDENT SECURITY ACCEPTANCE
============================================================

Create an authoritative test suite using the actual
Linux kernel inside the disposable Debian VM.

The existing repository contains important fixtures:

tests/package-sandbox.sh
tests/package-cgroup.sh
tests/native/product.py
tests/native/workers.py
tests/native/guard.py

Reuse and improve them.

Do not replace real security tests with mocks.

Use synthetic users:

fixture-owner
fixture-dsh-worker
fixture-codex-worker
fixture-opencode-worker
fixture-other-agent
fixture-untrusted-user

The exact fixture names may vary.

Required negative tests:

- Worker cannot read owner private files.
- Worker cannot read another worker's auth store.
- Worker cannot mutate privileged policy.
- Worker cannot access unrestricted root helper IPC.
- Worker cannot read forbidden process memory.
- Worker cannot read raw swap devices.
- Worker cannot escape via symlinks.
- Worker cannot bypass policy using alternate hardlinks
  where the threat model requires denial.
- Worker cannot use Docker/Podman host sockets.
- Worker cannot bypass restrictions via descendants.
- Worker cannot retain revoked permissions merely
  through a surviving managed process.
- Worker cannot approve its own broker request.
- Stale approval cannot be reused.
- Failed policy application does not report success.

Required positive tests:

- Worker can read/write allowed project files.
- Allowed native harness functionality works.
- Approved broker requests succeed exactly once.
- Ordinary build tools remain functional.
- Owner can manage policies.
- Owner can restore permitted data.
- Private NAS operates correctly.
- Existing GUI functionality remains accessible.

Deny-all is not an acceptable implementation.

A test passes only when the expected Linux access behavior
is demonstrated, not merely when a policy JSON file exists.

Use fake credentials exclusively.

Do not weaken a failing test.

============================================================
15. LOCAL INSTALLATION AND ROLLBACK ACCEPTANCE
============================================================

Build a candidate Debian package inside the VM.

Install it into a fresh Debian guest state.

Test:

- Fresh install.
- Initial owner setup.
- Worker account creation.
- DSH/OpenCode/Codex synthetic integration.
- Owner authentication.
- Permissions GUI.
- Auto Detect.
- Credential Guard.
- NAS/Storage.
- Monitoring.
- Service lifecycle.
- Upgrade from a v0.3.7-compatible fixture.
- Rollback.
- Remove.
- Purge without destroying retained user data.
- Failed upgrade recovery.
- Interrupted installation.
- Database migration failure.
- Service startup failure.

Use snapshots to compare before/after state.

The release must not depend on production-specific
ACL snapshots or the username huou07.

All required service units should start under the intended
identities.

No real host data or services are involved.

============================================================
16. FRONTEND AND UX ACCEPTANCE
============================================================

Preserve the current H07P visual design.

Do not introduce unnecessary frontend frameworks.

Test actual Rust backend interactions through Playwright.

Do not count intercepted/mock API responses as proof
that real backend routes work.

Test:

- Login/logout.
- CSRF-protected actions.
- Dashboard.
- Metrics.
- Service management.
- Permissions.
- Auto Detect.
- Scan progress.
- Cancellation.
- Partial scan reporting.
- Owner review.
- ACL impact preview.
- Apply/rollback.
- Harness discovery.
- Worker setup.
- Credential Guard.
- NAS/Storage.
- Large transfers.
- Errors and recovery.
- Mobile layout.

Verify that sensitive content never appears in frontend
logs, notifications, screenshots or exported reports.

============================================================
17. CI AND RELEASE GATES
============================================================

Only after all required local VM acceptance tests pass:

Prepare a clean implementation branch.

Use the existing GitHub repository.

Do not force-push main.

Do not replace the repository.

Do not rewrite existing tags.

Extend GitHub Actions to require:

- Rust formatting.
- Clippy.
- Rust unit tests.
- Python regression tests.
- Frontend tests.
- Browser integration tests.
- Security fixtures.
- Actual Linux isolation tests.
- Package lifecycle tests.
- Dependency audit.
- Secret scanning.
- License checks.
- Clean release build.
- Reproducible package comparison.
- Checksum verification.
- Lintian.
- SBOM.
- Release provenance.

Security-sensitive kernel tests must execute in a suitable
disposable Linux VM or equivalent independently verified
environment with the required capabilities.

Do not silently skip them.

A container sharing the host kernel is not sufficient for
tests specifically requiring an independent guest kernel.

If GitHub-hosted runners cannot provide required privileges,
use an approved disposable VM runner.

Never use production Debian as the privileged CI runner.

Do not give the VM a GitHub credential with broad account
permissions.

Use a trusted publication mechanism with repository-scoped
permissions.

Do not expose authentication tokens in logs or model context.

============================================================
18. QUALITY AND ANTI-SHORTCUT RULES
============================================================

An agent must not:

- Change tests to match an incorrect implementation.
- Delete failing tests.
- Disable CI jobs.
- Mark tests optional to obtain a green run.
- Introduce unsafe Rust as a compiler workaround.
- Suppress Clippy warnings without justification.
- Add excessive wrappers or traits without demonstrated use.
- Replace real kernel tests with fake success responses.
- Falsify benchmark results.
- Hide skipped files.
- Hide unsupported harnesses.
- Claim all credentials are detected.
- Claim all agents are isolated without evidence.
- Report performance improvements without measurements.
- Alter production to make acceptance easier.

Changes to security tests, CI workflows, release gates,
or policy invariants require separate scrutiny.

Compare test changes against the original requirements.

Use an independent verification pass after implementation.

Prefer deterministic tools and existing project mechanisms
over unnecessary agent sessions.

Do not launch idle helper agents.

Do not repeatedly rebuild unchanged components.

Preserve useful checkpoints to survive session interruption.

============================================================
19. GITHUB PUBLICATION
============================================================

After local VM acceptance passes:

1. Run a full secret/privacy audit of the candidate tree.
2. Verify Git history contains no newly introduced secrets.
3. Verify release artifacts contain no private host state.
4. Push a dedicated branch.
5. Open a PR against latest main.
6. Wait for exact-SHA CI.
7. Repair genuine failures.
8. Verify all required checks pass.
9. Merge using the normal repository workflow.
10. Create a NEW immutable version tag.
11. Run the release workflow.
12. Verify release assets and checksums.
13. Publish the GitHub release.
14. Verify the published source SHA and package provenance.

Do not overwrite v0.3.7.

Do not bypass branch protection.

Do not use a privileged production token inside the guest.

If publication requires owner-side authentication, use the
trusted GitHub integration or request only that narrow
authorization step.

Do not weaken the security model to avoid asking for it.

Do not deploy the new package to production.

Publication and production deployment are separate actions.

Production deployment requires a future explicit owner
decision after reviewing the final results.

============================================================
20. DEFINITION OF DONE
============================================================

The task is complete only when:

ARCHITECTURE
- Privileged responsibilities are minimized and justified.
- Existing functionality remains operational.
- Security boundaries are documented and tested.

AUTO DETECT
- Known fake secrets are detected.
- Unsupported data is honestly marked unknown.
- Content scanning is bounded and correct.
- Sensitive file classification is broader and portable.
- Quick/deep/realtime modes behave correctly.
- Incremental scanning is reliable.
- Scanner failures never become false clean results.

HARNESS SUPPORT
- Existing DSH/OpenCode/Codex integration passes.
- Registry architecture supports tested extensions.
- Unknown executables are not automatically trusted.

PERFORMANCE
- Baseline and candidate measurements exist.
- p50/p95/p99 are reported where statistically meaningful.
- Optimizations have measured benefit.
- CPU/RAM/I/O remain bounded.
- No security regression was introduced.

SECURITY
- Protected file reads fail for unauthorized workers.
- Valid owner-authorized operations succeed.
- Kernel security tests pass.
- Revocation and rollback work.
- No secret values appear in artifacts.
- Residual limitations are disclosed.

PORTABILITY
- Installation works with a non-huou07 owner.
- No fixed historical ACL snapshot is required.
- Configuration is portable.
- Version and source metadata are correct.

RELEASE
- Clean guest build passes.
- Fresh VM installation passes.
- Upgrade and rollback pass.
- GitHub CI passes on exact source SHA.
- Release artifacts are verified.
- A new GitHub release is published.
- Production remains unchanged.

Do not claim that detection covers every possible secret.

Do not claim perfect isolation of same-UID secrets if
native harness architecture still makes them accessible.

Report such limitations explicitly.

============================================================
21. REQUIRED FINAL REPORT
============================================================

Provide:

SOURCE
- Original SHA.
- Final SHA.
- Branch.
- PR.
- Merge commit.
- Version tag.

ARCHITECTURE
- Components changed.
- Privilege boundaries.
- New registry/scanner design.
- Reasons for important decisions.

SECURITY
- Confirmed vulnerabilities fixed.
- Security tests.
- Residual limitations.
- Secret audit.
- Production safety.

AUTO DETECT
- Detection coverage.
- Scanner selected.
- False-positive/negative fixtures.
- Quick/deep/realtime behavior.
- Unknown/skipped accounting.

HARNESS
- Supported harnesses.
- Discovered harnesses.
- Managed harnesses.
- Isolation results.

PERFORMANCE
- Baseline vs candidate.
- Object counts.
- Bytes read.
- CPU/RAM/I/O.
- p50/p95/p99.
- Parallelism results.
- Incremental scan performance.
- ACL snapshot/apply performance.

VALIDATION
- Unit tests.
- Integration tests.
- OS isolation.
- Browser acceptance.
- VM package installation.
- Upgrade/rollback.
- CI run URLs.

RELEASE
- Tag.
- Release URL.
- Package checksum.
- SBOM.
- License/audit reports.

PRODUCTION
- Explicit confirmation production was not modified.
- No service restarts.
- No ACL changes.
- No credential access.
- No production deployment.

FINAL STATUS

Choose exactly one:

RELEASED_AND_VERIFIED
IMPLEMENTED_NOT_RELEASED
PARTIALLY_VERIFIED
BLOCKED

Never report RELEASED_AND_VERIFIED if required acceptance
gates failed or were skipped.

============================================================
22. EXECUTION INSTRUCTION
============================================================

Begin immediately with a read-only preflight.

Verify the host has enough resources for an isolated VM.

Create the disposable development environment safely.

Establish the baseline.

Then implement, test, benchmark and refine continuously.

Use the most cost-effective available coding tools without
compromising quality.

Complete the entire workflow through GitHub release if all
security and verification conditions are satisfied.

Do not ask for permission at every ordinary development step.

Request approval only when a genuine host privilege,
secret-access or external publication authorization
boundary requires it.

Do not turn this into multiple disconnected development
projects.

Do not stop merely because the task is long.

Preserve checkpoints and resume from verified state.

Never modify the production Playground installation.

Start now.
