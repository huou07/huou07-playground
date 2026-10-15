# Validation and release contract

## Allowed environment

For the current product delivery, the owner explicitly authorized build, test,
deployment and application on their Debian host in this conversation. That newer
authorization supersedes the historical hosted-only restrictions below for this
delivery. Use synthetic temporary data, isolated namespaces where appropriate,
separate test ports/control state, bounded fixture units, protected backups and
verified rollback. Never use owner credentials or NAS contents as test fixtures.
See [current native evidence](evidence/product-native-20261015.md).

The following hosted-only description records the earlier baseline policy:

Product tests/builds/benchmarks/package lifecycle checks run on disposable
GitHub-hosted Linux infrastructure. The owner's live Debian environment is not a
fixture. The sole local security exception is the isolated guest design below;
its current prerequisites are blocked.
Never use a self-hosted runner, SSH into the owner host or invoke deploy scripts
there. Sudo is allowed inside the disposable CI guest. Read-only source/Git review
does not establish runtime behavior.

Current CI: framework structure/routing guard, legacy make check, locked Rust
format/Clippy/test/release/HTTP smoke, and separate Python/Rust browser lanes.
See [IMPLEMENTATION.md](IMPLEMENTATION.md) for source coverage. The browser runner
selects the actual backend, uses a temporary apps registry/fixture app server and
intercepts several APIs; its pass does not prove Rust read parity or permissions/NAS.
Hosted Ubuntu tests do not establish Debian package or OS isolation acceptance.

## Evidence classes and current UI lanes

Use AEH's shared evidence contract when available. This repository maps its
existing words without rewriting history: implemented =
IMPLEMENTED; executed source checks = VERIFIED_SOURCE; actual ARIA assertions =
VERIFIED_SEMANTIC; completed browser journeys = VERIFIED_BEHAVIORAL; reviewed
screenshots/layout measurements = VERIFIED_VISUAL; real OS/package journeys =
VERIFIED_NATIVE. CI-verified/owner-accepted requires the corresponding exact-SHA
authoritative gates (ACCEPTED only within that scope). BLOCKED and UNVERIFIED
never mean PASS. A class does not automatically establish every preceding class.

The browser matrix runs the Python reference and actual Rust server separately.
Python retains the real registry/app journey. Both exercise synthetic UI
loading/error/retry, 360px keyboard navigation and representative dark/light
captures. Rust additionally proves actual health/static responses and requires
the unported metrics endpoint to remain an explicit 404. API-intercepted UI
behavior is not Rust read parity or security enforcement.

Failure traces and a small canonical screenshot set are uploaded for seven days,
bound to the CI run/SHA/backend. No full pixel golden suite or platform pixel
identity is required. Permissions/NAS and dialog focus acceptance remain
UNVERIFIED because those product surfaces do not yet exist. Mobile navigation
is tested as navigation, not advertised as an implemented permission dialog.

## Required gates as slices land

| Change | Gate and evidence |
| --- | --- |
| Framework | Hosted python3 tools/check-framework.py: links/anchors, navigation/router inventory, skill metadata and declared route-case schema; model selection/loading remains unverified |
| Rust baseline | Pinned toolchain: cargo fmt --all -- --check; cargo clippy --workspace --all-targets --locked -- -D warnings; cargo test --workspace --locked; cargo build --workspace --release --locked |
| API parity | Fixture comparisons with Python reference; errors/timeouts and limits included |
| Owner control | Auth/CSRF, replay, worker-to-owner API denial, policy revision conflicts |
| Isolation | Actual managed agents-worker subprocesses and descendants in disposable Debian VM, not mocked syscall results |
| NAS/Storage | File integrity, quota/full disk, path races, cut/copy/paste, partial failures and unauthorized filesystem/API retrieval |
| UX | Existing plus new Playwright journeys, keyboard, 360px/desktop and dark/light screenshot review |
| Dependencies | Locked versions, reviewed origin/license, redacted secret scan, cargo audit/deny with documented exceptions |
| .deb | Reproducible versioned build, lintian, install/upgrade/remove/purge and retained-data checks in disposable Debian VM |
| Release | Passed required gates for exact commit, artifacts/checksums/SBOM, honest notes and known limitations |

Use a disposable Debian VM on a GitHub-hosted runner for full systemd, DAC,
namespace, Landlock and package acceptance; containers alone may miss those.
Detect virtualization/capabilities. Unsupported test environment is an explicit
incomplete gate, never a skip presented as a pass. Supported minimum Debian/kernel
and required ABI are chosen from demonstrated capability tests before first release.
Start with Linux amd64 .deb; other Linux architectures need their own evidence.
Non-Linux platforms remain Coming soon.

## Framework checks and current executable entrypoints

The framework job is independent of product jobs. Its guard reads repository
text only; it does not import application code, start services, install packages
or contact host services. It checks declared routing cases in
[../tools/framework-routing.json](../tools/framework-routing.json); these are
declared positive/subtle/negative/no-skill expectations, not live model
routing results. Validate actual selection and output separately through the
current session loader before claiming discovery or promoting a skill.

Existing hosted entrypoints are `make check`, `make acceptance`, the pinned Rust
commands in [CI](../.github/workflows/ci.yml), and
`bash tests/rust-smoke.sh target/release/h07p-server`. Do not run them locally.
Missing Cargo.lock is a gate failure. Browser acceptance must be extended to a
real Rust backend as each API slice lands; a Python-only pass cannot close P1.

Retain sanitized raw measurements/reports as CI artifacts with source SHA,
workload/toolchain identity, job/run URL, units and sample duration. Link these
from ROADMAP rather than copying result tables into every contract. Publish only
synthetic paths/data; no real credential, NAS or owner host inventories.

## Adversarial fixture matrix

Create fake secrets and private directories inside the CI guest, never copy host
data. Test worker direct list/read/write/create/delete/execute plus forged API,
socket and helper requests. Include escaped paths, symlink/hardlink aliases,
rename/mount races, inherited descriptors, /proc access, open handles during revoke,
forked descendants, approval expiry/replay, stale cache, unsupported operation
combinations, failed policy activation and worker editing policy/launcher parents.
Test all templates and Custom, immutable NAS/admin protection under none, strict
runtime dependencies and balance direct denial plus broker approval.
Run real positive allow cases so a deny-all bug cannot pass.

Private NAS acceptance includes owner login, GUI Block selection of NAS subtree,
actual worker denial, owner upload/preview/download hash match, cut/copy/paste and
continued owner access. No secret values in screenshots, logs or uploaded artifacts.

## Performance and energy

Use identical fixture dataset, workload, runner/guest configuration and sample
duration for Python/Rust comparisons; record commit, toolchain, warm/cold state,
concurrency and raw sanitized measurements. Hosted-runner variance requires
repeats and declared tolerances. Existing PERFORMANCE.md is historical, not CI baseline.

Measure at least idle browser closed, Home open, Permissions/Storage navigation,
directory pagination and streaming upload/download. Record p50/p95 latency,
throughput, peak/RSS memory, CPU time, wakeups if available, storage writes and
background subprocesses. Include helper, collectors and optional Redis, not just
the dashboard PID. Hash-check transfers and assert memory does not grow with file size.
Bound operation concurrency and test cancellation/backpressure.

Initial targets are hypotheses, not achieved values: no overlapping UI requests;
no scanning while idle; zero recurring health subprocesses with no subscribers;
a small-file warm API p95 no worse than reference within declared runner noise;
bounded transfer buffers and no material idle CPU/memory regression. Establish
numeric resource/latency budgets from the first reproducible CI baseline before
accepting optimization claims. A regression needs user benefit and an explicit
tradeoff, not merely cleaner code.

CI can measure CPU cost but cannot prove electricity savings on the owner's machine.
If later authorized, measure joules for fixed work and idle watts over matched
intervals on actual hardware. Distinguish CPU package from whole-machine energy.

## Package lifecycle and data protection

In the disposable Debian guest, create synthetic owner configuration, policy
state and NAS data with known hashes before testing upgrade/removal. Install
protected binaries/units outside worker-writable trees; package scripts must not
execute a checkout or worker-controlled configuration with privilege. Check
fresh install, interrupted/failed upgrade, schema backup/restore, rollback,
remove and purge. Remove must preserve user data; purge may remove package-owned
configuration but must not silently delete NAS/workspaces, owner credentials or
unrelated services. Destructive user-data deletion is a separate explicit owner
operation, not an uninstall side effect. Verify retained hashes and service/
worker identity after each lifecycle transition. Legacy deploy scripts are not
the future .deb lifecycle proof.

## Disposable local OS security lab

The owner permits a local isolated guest for this mission. Host product tests
remain prohibited. The live Playground, real permission policy, DSH state,
credentials and NAS are never fixtures. Containers establish no OS isolation
claim. Do not install a general self-hosted runner on this machine.

Preflight on 2026-10-15: QEMU/qemu-img 10.0.13, genisoimage and xorriso exist;
20 logical CPUs, roughly 7.4 GiB available RAM and 211 GiB free product storage
were observed while OR's bounded native lane was active. No guest was created or
launched. Current UID 987 cannot read/write root:kvm 0660 /dev/kvm. No reviewed
read-only Debian base image/guest fixture was supplied. Local security execution
is BLOCKED by those prerequisites; no chmod, group membership or live agent
permission change was attempted. P2/P3 enforcement is also unimplemented:
a guest DAC smoke alone cannot become H07P security acceptance.

Reviewed design (QEMU CLI and cloud-init; no new orchestration service):

- One Debian 13 genericcloud base, verified against Debian's signed checksum
  manifest, with its resolved version/URL/hash recorded and mode 0444. Inspect
  image metadata; reject backing chains, external data files and host devices.
- One disposable qcow2 overlay and read-only NoCloud seed ISO. Synthetic
  lab-owner and lab-worker accounts; locked passwords; fake private files,
  NAS tree and services created only inside the guest. Boot cloud-init/systemd
  to run the fixture and power off. Never inject real keys/tokens.
- Hard budget: one guest, 2 vCPUs, 2048 MiB guest RAM, 180s runtime, 8 GiB
  maximum virtual disk, 2 GiB overlay allocation and 10 MiB retained log.
  Require at least 6 GiB MemAvailable and 8 GiB free disk before any image
  creation; stop if available RAM drops below 3 GiB or overlay/log budget is
  exceeded. Refuse concurrent OR/VCE native work using the same
  /tmp/aeh-native-ui-UID.lock and inspect other QEMU processes first.
- Fixed launch options: q35/KVM, no default devices, no user config,
  -display none -monitor none -serial stdio -nic none -no-reboot,
  virtio overlay plus read-only seed only, and QEMU sandbox enabled.
  No host filesystem sharing, clipboard, guest agent, SSH agent sockets,
  USB passthrough, credentials, network or live management endpoint access.
- Enforce timeout/process-group cleanup and delete only that run's resolved
  overlay/seed/temp directory after collecting bounded synthetic results.
  Verify the base hash again. Reuse the immutable base; never clone full disks
  or accumulate per-run overlays.

Owner-only provisioning, if local feedback is still desired: use a dedicated
unprivileged lab account with KVM access and an empty private home. Review/copy
the guest fixture into an owner-controlled read-only location, provision the
verified base, and execute QEMU under that account. Do not grant agents-worker
new KVM/owner access merely for acceptance. No agent may invoke an elevated
worker-writable fixture or bypass the current /dev/kvm denial.

Reviewed owner-only host preparation (not executed by this task): first confirm
that `h07p-lab` and the paths below are unused. If they exist, inspect ownership
and contents; do not reuse or overwrite them blindly. These commands create no
VM, runner, live policy or permission grant for agents-worker.

```sh
sudo useradd --system --user-group --create-home --home-dir /var/lib/h07p-lab-home --shell /usr/sbin/nologin h07p-lab
sudo chmod 0700 /var/lib/h07p-lab-home
sudo usermod --append --groups kvm h07p-lab
sudo install -d -o root -g root -m 0755 /var/lib/h07p-security-lab
sudo install -d -o root -g h07p-lab -m 0550 /var/lib/h07p-security-lab/base /var/lib/h07p-security-lab/fixtures
sudo install -d -o h07p-lab -g h07p-lab -m 0700 /var/lib/h07p-security-lab/runs
sudo -u h07p-lab test -r /dev/kvm
sudo -u h07p-lab test -w /dev/kvm
```

Stop after this capability check until the signed base identity, synthetic seed
and bounded launcher are reviewed. Install the reviewed base/fixture as root-owned
read-only files under the protected directories; run only QEMU as h07p-lab, never
a worker-writable script with sudo. Recheck current headroom immediately before
image creation. No base download or VM launch is implied by this example.

After those prerequisites are reviewed, the native command shape is:

```sh
qemu-img create -f qcow2 -F qcow2 -b "$reviewed_base" "$run_dir/guest.qcow2"
timeout --kill-after=5s 180s qemu-system-x86_64 \
  -no-user-config -nodefaults -machine q35,accel=kvm -cpu host -smp 2 -m 2048 \
  -display none -monitor none -serial stdio -nic none -no-reboot \
  -sandbox on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny \
  -drive "file=$run_dir/guest.qcow2,format=qcow2,if=virtio" \
  -drive "file=$run_dir/seed.iso,format=raw,media=cdrom,readonly=on"
```

This is a reviewed command shape, not an executed acceptance result or a complete
launcher: resource monitoring, approved base/seed and safe cleanup are required.
Start with real positive worker-workspace access plus negative private-file,
alias, forged API and descendant cases from the matrix above. Revoke/open-FD,
same-UID, package lifecycle and P2/P3 policy journeys need their actual implemented
H07P boundaries. Keep GitHub-hosted Debian VM execution as independent acceptance;
an ephemeral guest runner is deferred until it provides measured value.

References: [Debian cloud images](https://cloud.debian.org/images/cloud/),
[QEMU disk images](https://www.qemu.org/docs/master/system/images.html) and
[cloud-init NoCloud](https://cloudinit.readthedocs.io/en/latest/reference/datasources/nocloud.html).
External instructions do not grant host privilege.

## CI trust and publication

Pin actions to reviewed immutable commits. Default GITHUB_TOKEN contents: read;
pull requests never receive release tokens, owner credentials or privileged host
connections. Privileged fixture tests in disposable hosted machines contain no
secrets. Do not use pull_request_target to execute untrusted source.
Future release job alone receives contents: write and runs from a trusted exact
commit after gates; do not run release credentials against arbitrary PR code.
Publish Linux .deb/checksums and source provenance to the existing H07P repository.
This framework change does not create a fake binary release. Installation on the
owner's host remains a separate owner request.
