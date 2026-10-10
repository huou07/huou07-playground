# Single-user migration

This is an owner-run migration from the existing system services to ordinary
`huou07` user services. It does not stop services until the owner runs the
explicit `cutover` command. The `preflight` command is read-only with respect
to service state and application data: it performs health/auth/path checks,
Podman inventory, and disk-space estimates. No model request is made.

## 1. Pin and inspect the reviewed source

Run these commands on the Dell to use the verified migration runner commit:

```sh
sudo git clone --no-checkout https://github.com/huou07/huou07-playground.git /root/huou07-playground-migration-87665bf
sudo git -C /root/huou07-playground-migration-87665bf checkout --detach 87665bfb3a489cd5968cfb7be8f473caef4ff151
sudo sh /root/huou07-playground-migration-87665bf/deploy/inspect-one-user-migration.sh
```

Review the complete inventory. Required Podman discovery must succeed. It
reports paths and metadata without printing credential values, database rows,
project file names, process arguments, or private key material. OmniRoute file
ownership is inspected from its original Podman user namespace; do not use the
host's mapped `UNKNOWN` ownership for a `chown` decision.

## 2. Read-only preflight

After reviewing inventory, run:

```sh
sudo bash /root/huou07-playground-migration-87665bf/deploy/migrate-one-user.sh preflight
```

Preflight must finish with `Preflight passed`. It checks active source services,
the user manager and linger setting, Codex ChatGPT login, OpenCode auth-file
presence without printing contents, DSH session/configuration paths, rootless
Podman and volume discovery, namespace
ownership, destination collisions, and all current application health checks.
It also makes an HTTP health check to the dashboard's active `wg0` IPv4
address. A missing WireGuard interface or unreachable dashboard is a blocker.

The disk check estimates the protected backup (including the second
OmniRoute-data archive), the migrated HOME state, PostgreSQL volume import,
and pinned container images. It groups simultaneous space needs by filesystem,
reserves 25% headroom plus 1 GiB, and stops if any required discovery or
capacity check fails. Re-run preflight immediately before cutover so free space
and service health are current.

Sudo/NOPASSWD and Docker-group access are reported as explicit security
warnings and do not block migration, as the owner has accepted those privileges
on this personal computer. DSH and OpenCode retain `NoNewPrivileges=yes` and
mask `/run/docker.sock` as defense in depth. These unit restrictions do not
isolate the shared `huou07` account from its sudo rights, Docker access, or
user-readable credentials. The migration does not stop or modify the rootful
Docker daemon or unrelated containers.

## 3. Owner-reviewed cutover

Run the following only after the full inventory is reviewed and the latest
preflight passes all essential checks:

```sh
sudo bash /root/huou07-playground-migration-87665bf/deploy/migrate-one-user.sh cutover
```

The runner downloads the required images before the outage. It writes a
mode-0700 root-only backup before stopping the six source application units.
It does not stop SSH, WireGuard, Cockpit, Docker, AN3,
AdGuard Home, or unrelated containers. It exports LiteLLM PostgreSQL with the
source rootless Podman identity and imports it into a new owner-user volume;
it does not copy Podman storage. OmniRoute data is archived and restored inside
each rootless Podman user namespace to preserve container-view numeric
ownership. Original accounts, databases, credentials, and source data remain
in place.

The runner copies DSH sessions/configuration, OpenCode XDG state and auth,
workspace files, environment/configuration, dashboard settings, and keeps the
existing Codex store in place. It checks the migrated OpenCode auth file byte
for byte and rechecks Codex login status without making a model request.
It installs and enables the user units, checks their active/enabled state,
checks all local application health endpoints, and verifies dashboard access
through `wg0`. Existing user linger plus enabled user units is the standard
systemd mechanism for logout/reboot persistence; this procedure does not reboot
the production machine as an acceptance test.

If any cutover step fails after source services stop, the exit handler attempts
automatic rollback. It stops and verifies the new services/containers before
reactivating the original units. If it reports that automatic rollback failed,
keep all state and backups, inspect the service status, then run:

```sh
sudo bash /root/huou07-playground-migration-87665bf/deploy/migrate-one-user.sh rollback
```

Rollback returns the workspace paths and DSH policy patches, restores original
unit enablement, and starts the original services against untouched source
data. The newly migrated HOME data and root-only backup are retained. Do not
delete old accounts, source databases, credentials, or backups during initial
acceptance; cleanup requires a separate explicit owner decision.

## Boundaries

- WireGuard UDP 3478, SSH, UFW, Cockpit, and operating-system services are
  outside this migration and remain managed as they are today.
- No Codex/OpenCode inference, provider login, model fallback, or quota use is
  part of inventory, preflight, cutover checks, or rollback.
- A healthy service and preserved authentication files do not prove an
  authenticated ACP coding turn; that remains separate owner-authorized work.
