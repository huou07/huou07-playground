# Single-user migration

The Debian production services remain on their existing system units until the
owner reviews the complete inventory and explicitly runs the cutover. The
runner has three modes: `preflight` is read-only, `cutover` migrates, and
`rollback` returns to the original services and their untouched data. The
runner does not use `sudo` to launch privileged work; preflight uses only the
read-only `sudo -n -l -U huou07` policy query.

## 1. Complete the privileged inventory

No production service deployment is needed for the inventory or preflight.
First make a root-owned, commit-pinned copy of the public source on the Dell so
the owner-run privileged scripts cannot be changed by an ordinary user between
review and execution:

```sh
sudo git clone --no-checkout https://github.com/huou07/huou07-playground.git /root/huou07-playground-migration-73c2c4b
sudo git -C /root/huou07-playground-migration-73c2c4b checkout --detach 73c2c4b5a473fc054040bf5fdb7bd6cac205068b
sudo sh /root/huou07-playground-migration-73c2c4b/deploy/inspect-one-user-migration.sh
```

The script changes to `/` before invoking either rootless Podman account, so
the caller's working-directory permissions cannot break discovery. Any
required Podman command failure stops the inventory with an error. OmniRoute
ownership and UID/GID maps are read inside its original Podman user namespace;
the host's mapped `UNKNOWN` owner is not used to make a `chown` decision.

The output reports account and unit state, file counts, credential locations,
the rootless container and volume inventory, volume metadata, namespace maps,
destination conflicts, and sudo/Docker-socket facts. It prints no credential
values, database rows, project file names, process arguments, or private key
material. OpenCode credentials are identified by path only. Codex login status
is queried through the owner's existing CLI without copying or changing its
authentication store.

Return the complete output for review. Do not proceed if the inventory exits
nonzero or says a required discovery failed.

## 2. Read-only migration preflight

After the inventory is reviewed, run:

```sh
sudo bash /root/huou07-playground-migration-73c2c4b/deploy/migrate-one-user.sh preflight
```

Preflight checks production health, target user-manager availability, native
Codex login, OpenCode credential presence, rootless Podman for all three
identities, original OmniRoute namespace ownership, PostgreSQL volume
availability, HOME collisions, existing user-unit files, Docker socket access,
and passwordless sudo rules. It also compares colliding XDG paths without
printing their contents. It does not stop or restart services. Resolve any
reported conflict and review the entire preflight output before choosing the
cutover command.

The account's `sudo` group membership is reported as an owner privilege fact;
no passwordless sudo rule is accepted. The DSH and OpenCode units set
`NoNewPrivileges=yes` and make the rootful Docker socket inaccessible. This
prevents those user services from elevating through sudo or calling a rootful
Docker API. It does not make the shared interactive `huou07` account a separate
security identity; an agent process with that account's ordinary file access
can access the same user-readable files and credentials.

## 3. Owner-reviewed cutover

Only after reviewing the full inventory and successful preflight, the owner
may run this exact command:

```sh
sudo bash /root/huou07-playground-migration-73c2c4b/deploy/migrate-one-user.sh cutover
```

The runner first makes a root-only backup and captures the original unit
enablement. It then stops old writers in dependency order, exports the stopped
LiteLLM PostgreSQL volume with the old rootless Podman identity, and imports
that archive into a new target-user volume. OmniRoute data is archived and
restored inside the source and target Podman user namespaces, preserving the
container-view numeric ownership. It does not copy either Podman graphroot.
DSH sessions/profiles, OpenCode XDG data, configuration, environment files,
dashboard settings, and workspaces are copied into `/home/huou07`; the native
Codex store is backed up but not replaced. Original service homes, accounts,
volumes, data, and unit files are retained.

Local health checks validate the user services without model inference. If a
cutover step fails after the source stop begins, the runner automatically
reactivates the original services. If manual recovery is needed, run:

```sh
sudo bash /root/huou07-playground-migration-73c2c4b/deploy/migrate-one-user.sh rollback
```

Rollback stops and removes the new user-unit definitions, restores the prior
DSH policy patch, restores workspace paths, restores the old unit enablement,
and starts the original services against their original state. It retains the
new HOME data and private backup for diagnosis. Do not delete the legacy state
or backup as part of this initial cutover.

## Migration boundaries

- PostgreSQL data moves through `podman volume export` / `podman volume import`
  with both services stopped; database files are not copied manually.
- OmniRoute bind-mounted data is translated through each rootless Podman user
  namespace; there is no host `chown` or Podman storage copy.
- Codex ChatGPT login remains in `/home/huou07/.codex`; OpenCode provider
  credentials stay in the native OpenCode XDG data path.
- WireGuard, SSH, UFW, Cockpit, system monitoring, and their system-managed
  operating-system services are outside this migration.
- No provider login, model request, inference, or quota use occurs.
- Old accounts, services, data, and backups are intentionally retained.
  Cleanup requires a separate owner review and approval.
