# Linux amd64 package

Installation and rollback operate as the system administrator and require owner
review. Managed workers do not receive sudo, root shells, unrestricted container
sockets, or control of installed binaries, policy, units, or writable ancestors.
Do not grant a worker administrative privileges to make a task succeed.

Maintainers publish versioned packages by pushing a `vX.Y.Z` tag. The GitHub
release workflow reruns the required source/browser CI for that exact tag,
audits locked dependencies, builds the package twice on a fresh hosted runner,
checks reproducibility and Lintian, then publishes the `.deb`, checksum, SBOM,
license notices and source identity. Its isolated dpkg lifecycle test is not a
substitute for a full systemd Debian VM install test.

Build on Linux amd64 Debian/Ubuntu with systemd >= 254, Python3, acl and
Gitleaks >= 8.16, from an already validated locked release binary:

```sh
# cargo-audit must be on PATH; AUDIT_DB names a writable dedicated database directory.
python3 tools/release-audit.py --advisory-db "$AUDIT_DB"
cargo build --release --locked
SOURCE_DATE_EPOCH=$(git show -s --format=%ct HEAD) tools/build-deb.sh 0.3.7
(cd dist && sha256sum -c huou07-playground_0.3.7_amd64.deb.sha256)
```

The builder requires passing audit artifacts matching Cargo.lock under
`artifacts/release-audit` (or `H07P_RELEASE_AUDIT_DIR`), bundles their SBOM/notices,
strips the ELF and excludes macOS resource forks. Synthetic lifecycle fixtures
explicitly set `H07P_PACKAGE_FIXTURE=1`.

Build output is root-owned and timestamp-normalized; compare repeat artifact hashes
on the same toolchain/dpkg version. Only Linux amd64 is supported. The package does
not install any native agent CLI, create owner passwords, reset credentials, modify
VPN configuration or remove existing telemetry collectors. It adopts the known
DSH/OpenCode worker services and owner CLI entry point so every managed restart
uses the installed Rust policy launcher before permanently dropping to the existing
worker UID. Owner CLI invocations use revocable `h07p-worker-*` systemd cgroups
with PTY/pipe support and whole-group termination. Upgrade, rollback and removal
stop managed interactive CLI jobs; terminal commands are never replayed.
Existing enabled/active web-service states are preserved; missing worker accounts
are not created and disabled workers are not started.

Install with `apt install ./dist/huou07-playground_VERSION_amd64.deb` only on the
owner-authorized target. A matching legacy dashboard `/etc/systemd/system` unit is
saved and adopted; unrelated overrides fail closed. Matching legacy DSH/OpenCode
units and `/usr/local/sbin/h07p-harness` are saved too. Security-affecting worker
drop-ins require reconciliation before installation; other customizations remain.
Dashboard/helper drop-ins remain active and require review because they can
change the packaged unit's restrictions.
The root helper owns existing VPN relays; the dashboard listens on loopback.
The installed legacy Python dashboard also owned an OpenCode password bridge.
The Rust helper now preserves this bridge on loopback 4096, VPN 14096 and the
previously configured LAN interface. Existing root-protected
`opencode-proxy.env` supplies the same public/backend credentials; they are never
rewritten or exposed to workers. Only public listener settings are migrated from
the adopted unit into `native-network.env`, retaining later owner edits. The
bridge replaces owner Authorization, strips the dashboard cookie, streams bounded
Content-Length/chunked requests and SSE responses, and supports WebSocket upgrade.
Normal HTTP uses one request per connection; ambiguous/pipelined framing is
rejected and chunked trailers are dropped. The existing DSH LAN login handoff is
retained. Authenticated behavior uses synthetic bridge fixtures; production
passwords/model calls are not acceptance fixtures.
The helper shares host `/tmp` for owner Storage visibility. Managed worker services
have their own systemd temporary namespace and a per-worker 0700 TMPDIR. DSH web
has a narrow runtime-handoff write exception; all other external runtime paths
remain read-only under strict/balance Landlock.

Configuration: `/etc/huou07-playground/dashboard.env` (Debian conffile). Durable
apps/session state is `/var/lib/huou07-playground`, helper policy is root-only
`/var/lib/h07p-control`, NAS is `/var/lib/h07p-private/nas` mode 0700 under the
dedicated dashboard UID. Installed code/static files and all ancestors are root-owned.
Changing these paths requires a coordinated data migration and unit configuration.
The helper's typed owner Storage operations run as the owner; its mount namespace
allows host access and relies on peer checks, typed requests and UID/DAC enforcement.

Before upgrade, the maintainer script stops both SQLite writers and snapshots their
state, previous release and matching unit overrides under root-only
`/var/backups/huou07-playground`. A health failure restores these and retains failed
state separately. NAS bytes are never copied or deleted. Snapshots contain sensitive
state and must remain root-only. Rollback immediately after a failed/undesired
upgrade (later accepted user writes would otherwise be rolled back):

```sh
sudo /usr/lib/huou07-playground/lifecycle.py rollback
```

Rollback restores the last pre-install snapshot, not package-manager metadata;
reinstall the intended `.deb` afterward to reconcile dpkg. Remove/purge restore the original worker units and owner CLI wrapper, including
their original enabled/active states, and leave owner state, NAS, native CLI stores,
release rollback copies and snapshots intact. No
destructive data purge command is provided. The package never runs worker-writable
checkout code as root.

Synthetic lifecycle validation: `sh tests/package-lifecycle.sh` uses a temporary
`dpkg --root` with `--force-script-chrootless`; maintainer scripts use `DPKG_ROOT`
and never call host systemd in this mode. It verifies hashes across install,
upgrade, an intentionally failed dpkg postinst with automatic rollback, repeated
explicit rollback, remove and purge with `/bin/true` as the ELF fixture. It also
compares repeat package hashes and restores the original synthetic worker units
and owner entry point.
This does not prove real systemd startup, PAM, isolation or target-kernel acceptance.
`python3 -m unittest discover -s tests/package` covers path and adoption failures.
`sudo tests/package-sandbox.sh target/debug/h07p-server` separately exercises the
actual root launcher inside a private mount namespace with a synthetic chroot,
synthetic passwd identities/native scripts, real Landlock, UID/GID/groups,
no-new-privileges, inherited descriptor closure, workspace/native positive writes,
peer denial, outside/symlink denial, inherited descendant restrictions and invalid
policy refusal for none/minimal/strict/balance. Owner-wrapper argv/cgroup/PTY/pipe
checks replace systemd-run only inside that namespace.
`sudo timeout 25s tests/package-cgroup.sh target/debug/h07p-server` creates one
real, uniquely named synthetic `h07p-worker-fixture-*` systemd service with its
own RootDirectory, synthetic identity and fake native Python process. It checks
the parent and child are in the same cgroup and both terminate on stop, then
removes the fixture. It never starts/stops production worker services. It mounts host `/usr` read-only for
runtime libraries; no real home, credentials or native model command is mounted.
A disposable Debian systemd VM must additionally install the actual server, verify
health/failure rollback, service identities and actual worker/data denials.

`tools/measure-product.py` compares supplied Python/Rust commands on one isolated
loopback port and fresh synthetic registries. It records repeated latency samples,
idle/request CPU time, sampled aggregate process-tree RSS, write bytes and live
process count. It omits commands, URLs, bodies and environment from artifacts.
The `--python-reference` mode bypasses the legacy main function so benchmark requests
never start VPN relays. Custom commands must provide the same loopback-only fixture
behavior. External helper/collector/service cost and exited children are excluded explicitly;
measure those separately before making whole-product efficiency claims. It makes no
energy claim. Endpoints must be fixed synthetic paths without credentials or query
strings. Example (Linux test environment, from repository root):

```sh
python3 tools/measure-product.py \
  --python-reference web/app.py \
  --rust-command '["target/release/h07p-server"]' \
  --output artifacts/product-measurements.json
```

This is an idle/HTTP microbenchmark; browser visibility, Permissions/Storage and
large streaming transfer memory/integrity require their own journey measurements.

## Worker requests and owner authentication

The dashboard uses the existing owner's Linux PAM password. Every private API
also requires a random proof kept only in dashboard memory: a host cookie alone
is insufficient because browsers send host cookies to other service ports on the
same VPN IP. Reload requires signing in again. Downloads and media use expiring
file-specific links; signing out revokes them. Owner proof is never appended to a
native app URL.

Inside a managed worker, request ordinary owner data explicitly:

```sh
/opt/huou07-playground/current/bin/h07p-server request read /absolute/file
/opt/huou07-playground/current/bin/h07p-server request list /absolute/folder
printf '%s' 'new contents' | /opt/huou07-playground/current/bin/h07p-server request write /absolute/file --stdin
printf '%s' 'new contents' | /opt/huou07-playground/current/bin/h07p-server request create /absolute/new-file --stdin
/opt/huou07-playground/current/bin/h07p-server request delete /absolute/file
/opt/huou07-playground/current/bin/h07p-server redeem APPROVAL_ID
```

The owner reviews the target, worker and concrete operation in Permissions and
approves once. Requests expire after five minutes, bind the policy revision and
object identity, and cannot cross workers or override a Block. Writes are fixed
at request time and limited to 64 KiB UTF-8; reads are at most 1 MiB. Binary reads
return explicit hexadecimal encoding. Execute, symlink/hardlink aliases and
immutable owner/native/NAS boundaries are unsupported. Strict refuses outside
workspace requests; balance uses this broker for outside data. A failed redemption
is consumed and requires a fresh owner decision.

Interrupted upload staging remains private. Active uploads are hidden; abandoned
uploads appear as **Incomplete upload** for owner inspection or explicit confirmed
deletion. They are never silently discarded during startup or upgrade.

## Beginner install and maintenance

Distribute the `.deb`, its `.sha256` and `h07p-install.sh` together. Run
`sh h07p-install.sh` in that directory (or pass the `.deb` path). Debian APT resolves
missing dependencies, including Python before the package's maintainer scripts.
The bootstrap checks package identity, architecture and checksum, previews the
APT transaction, refuses removals, and caches the verified installer for Repair.
It does not add repositories or silently upgrade the OS.

After installation, open **H07P — Cài đặt và sửa lỗi** from the applications menu,
or run `sudo h07p-setup`. The Vietnamese menu provides diagnostics, install/update,
repair from the cached `.deb`, rollback, data-preserving uninstall, and an explicit
APT index refresh. `h07p-setup doctor` works without root and never reads credentials
or log contents. CLI actions support `--dry-run` and `--yes`; `doctor --json`
exports sanitized metadata for support. Dependency/lock/network failures explain
what to do; unrelated package removals and conflicting unowned units are refused.
Repair reinstalls program files and keeps owner state, NAS, native stores and
accounts. Uninstall does not purge app data or forensic snapshots.
