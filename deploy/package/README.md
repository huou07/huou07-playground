# Linux amd64 package

Build on Linux amd64 Debian/Ubuntu with systemd >= 254, Python3, acl and
Gitleaks >= 8.16, from an already validated locked release binary:

```sh
cargo build --release --locked
SOURCE_DATE_EPOCH=$(git show -s --format=%ct HEAD) tools/build-deb.sh 0.2.0
(cd dist && sha256sum -c huou07-playground_0.2.0_amd64.deb.sha256)
```

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
