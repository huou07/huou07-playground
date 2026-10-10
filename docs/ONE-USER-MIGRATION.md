# Single-user migration checkpoint

The dashboard and user-unit templates are ready, but the Debian services have
not been cut over. The old system units remain the only production instances.
Do not enable the user units or stop the old units yet.

## Read-only administrator inventory

The root-only files are mode 0600 and the rootless Podman volumes are not
visible from the SSH owner's Podman store. The owner should run this read-only
inventory on the Dell and return its output before the cutover procedure is
finalized:

```sh
sudo sh deploy/inspect-one-user-migration.sh
```

Run it from this repository's root; the script prints
account IDs and homes, unit state, ownership/mode/size metadata, credential-file
presence, state-file counts, and rootless Podman container/volume names. It does
not print environment values, database rows, project file names, process
arguments, authentication tokens, or private key material. It performs no
changes.

The reported output is needed to resolve OpenCode auth-store collisions and
confirm that every expected source, volume, user manager, and target directory
matches the known deployment. The existing owner Codex store at
`/home/huou07/.codex` must remain untouched. The isolated DSH `.codex` directory
is retained in the protected legacy backup but is not copied over native Codex
authentication.

## Cutover invariants

The migration runner will create a root-only local backup before stopping
writers. It must stop the old LiteLLM proxy before PostgreSQL, then export the
stopped PostgreSQL volume with `podman volume export` as `huou07-litellm` and
import that archive with `podman volume import` as `huou07`. It must never copy
the old user's Podman graphroot. OmniRoute's persistent bind-mounted data and
environment are copied as files with secrets mode 0600. DSH profiles/sessions,
OpenCode config/data/state/cache and web settings, app registry, and both
workspaces are copied without removing the source state.

The first cutover must keep the legacy service accounts, homes, PostgreSQL
volume, application data, environment files, and system units in place. It may
disable the old units only after the owner invokes the cutover runner; rollback
must stop the user units and reactivate the original units against their
original untouched state. User-level units must be enabled for the lingering
`huou07` manager, and the dashboard starts only after its application health
checks pass. A health failure must stop the new units and leave recovery to the
old system units. WireGuard, UFW, Cockpit, SSH, and Codex's existing native
authentication are outside the migration and must remain unchanged.

PostgreSQL migration, state copying, unit activation, and rollback are to be
performed by the migration runner as a single auditable operation; the owner
should not run database commands or manually copy database files. Real model
inference is not part of preflight or acceptance.
