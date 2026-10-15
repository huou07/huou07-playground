# Shared-home harness workers

Current owner request, 2026-10-15: use `dsh-worker`, `codex-worker` and
`opencode-worker` on Debian, all with `/home/huou07` as HOME, shared installed
applications and broad access to ordinary owner files. No worker gets root,
owner sessions or another harness's credential store. Each harness's own
native credential handling remains native; no credential broker, copied
application installations or additional per-file native credential rules.

This is a host account/ACL migration, not completion of the Rust product roadmap.
The owner explicitly authorizes Debian builds, tests and this host cutover for
this task. Earlier preparation-only/host-testing prohibitions do not apply to
these authorized operations. No model/API call or native CLI login is required.

## Installed layout

| Surface | Identity / access |
| --- | --- |
| Ordinary files in shared HOME | Existing files get named user read/write ACLs; directories get traverse/create and inherited ACLs |
| Project `AGENTS.md`, `.agents/skills` | One shared copy, readable/editable by all workers |
| `~/.dsh` | Owned by `dsh-worker`, peer workers denied at store root |
| `~/.codex` | Owned by `codex-worker`, peer workers denied at store root |
| `~/.config/opencode`, `~/.local/{share,state}/opencode`, `~/.cache/opencode` | Owned by `opencode-worker`, peer workers denied at store roots |
| Global instructions | Separate `~/.dsh/AGENTS.md`, `~/.codex/AGENTS.md`, `~/.config/opencode/AGENTS.md`; existing instructions preserved |
| Installed CLI packages and launchers | Existing `~/.local/bin` and `~/.local/lib` reused; worker read/execute, owner maintains installation |
| Owner secrets | Known private directories, credential filenames and non-example `.env` files denied to every worker |
| Future owner secrets | Put in `~/.secrets` or another registered private directory; create individual secrets as mode 0600 |
| DSH / OpenCode web | System units `h07p-dsh.service`, `h07p-opencode.service` run as their respective workers, using existing ports 3080 / 4097 |
| Codex | Prepared account and owner entry point; no new daemon or login |
| LiteLLM / OmniRoute | Existing owner services remain owner-managed; credentials/configuration and container stores private |

Workers have locked passwords, no administrative supplementary groups, no sudo
rules, no Docker socket membership and no PolicyKit authorization. Services and
the interactive entry point use `NoNewPrivileges`. Distinct UIDs also separate
the harnesses' normal process memory permissions.

Private directories deny traversal to peers, so native future credentials and
session files inside are covered without changing their native 0600 behavior.
The harness UID owns its own native store; it can change its own permissions,
as requested. A malicious harness deliberately publishing its own credential
is outside the guarantee. Owner access uses named owner ACLs; a native 0600
chmod may mask those ACLs, so use the harness entry point for native state.

Private path ancestors use the sticky bit to prevent workers renaming
owner-owned private directories/files out of the way. This can also prevent
renaming/deleting another user's ordinary entries in those specific parent
directories; editing file contents remains allowed. Plain project directories
without private descendants keep normal shared rename/delete behavior.

## Apply and use

Requires existing Debian `acl`, Python 3 and systemd; no dependency upgrade or
additional app install. Run as the owner:

```sh
sudo python3 deploy/harness-workers/setup.py          # inventory only
sudo python3 deploy/harness-workers/setup.py --apply  # ACL/account cutover, restarts web services
sudo python3 deploy/harness-workers/verify.py         # real UID/ACL and process checks

sudo h07p-harness dsh
sudo h07p-harness codex
sudo h07p-harness opencode
```

The owner entry point clears inherited environment variables and agent sockets,
then switches to the selected worker and invokes the existing CLI. It preserves
the current project directory when invoked inside the shared home. Never start
an agent directly as `huou07` when worker separation is intended. A worker cannot
use this root-only entry point to switch to another harness or to the owner.

The launch environment trusts Git repositories below the deliberately shared
home, so Git's different-owner check does not prevent normal shared project work.
It does not set `safe.directory=*` globally. npm uses an optional `npmrc` inside
the selected harness's existing native directory, avoiding the owner's private
`~/.npmrc` without installing another npm or another application.

Native DSH plugins which spawn Codex/OpenCode under DSH's own UID do not gain
access to those harnesses' native stores. Use the respective worker entry point
for an authenticated native harness. Cross-harness credential sharing is not
reintroduced to preserve an adapter's previous same-user behavior.

The existing DSH token publication group is retained for the dashboard. The
OpenCode web environment file is read by systemd before dropping privileges;
other workers cannot read that owner's secret directory. Root-owned installed
units and the DSH launch helper are independent of the writable source checkout.
The old owner user units are disabled; historical installers are not migration
entry points and would restore the old owner-run arrangement if invoked.

## Secret inventory and limits

`setup.py` contains the reviewed native/private/read-only path inventory. It
inspects names and metadata, not secret contents. Add owner-specific private
relative paths to root-owned `/etc/h07p-workers/private-paths.json`, then rerun
the migration. Inventory/application require a maintenance window: do not edit
the shared tree concurrently with an administrator changing its ACLs.

ACLs do not identify arbitrary bytes as a secret. A new public-mode `.env` in a
shared project inherits sharing until an owner reruns the inventory; new secrets
belong inside a private directory or must be created as 0600. Unknown secrets,
copies in project history, old logs/backups and secrets outside the reviewed
paths cannot be guaranteed by filename classification. Never claim an exhaustive
content audit; no real credential bytes are opened by the verification tool.

Broad shared write access also permits modifying project code the owner may
later execute. Direct credential-path and UID isolation do not prevent every
indirect attack through deliberately shared executable project code. Protect
installed launch paths and owner startup configuration, and do not execute
unreviewed worker edits in a privileged owner session. This is the owner's
requested permissive ACL model, not the stronger future product policy broker.

## Rollback

Each apply prints a root-only directory under
`/var/backups/h07p-harness-workers/` with a `getfacl` snapshot including file
ownership, ACLs, defaults and sticky flags. Native store ownership is recorded
recursively; secret contents are not copied. Keep the selected snapshot path.

To revert the first migration, stop the worker services, restore that ACL file
with `sudo setfacl --restore=<snapshot>/acl.restore`, restore the saved
`huou07-dsh-link.conf` into `/etc/tmpfiles.d/`, run `systemd-tmpfiles --create`
for that file, and enable/start the two original owner user units. Remove or
disable `h07p-dsh.service` and `h07p-opencode.service`, the installed
`h07p-harness` entry point and the worker-specific PolicyKit rule after rollback.
Leave accounts locked while retaining any worker-created files for review;
do not delete users or their files as part of an automatic recovery.

The snapshot restores preexisting paths; remove newly generated global AGENTS
only after confirming they were not present before the migration. Files created
after the snapshot need their ownership reviewed before full rollback. A later
repeat apply has its own snapshot; select the original if undoing the migration.

## Documentation references

- [Linux ACL modification and default inheritance](https://man7.org/linux/man-pages/man1/setfacl.1.html)
- [Linux path traversal and sticky parent behavior](https://man7.org/linux/man-pages/man7/path_resolution.7.html)
- [Codex global/project instructions](https://developers.openai.com/codex/guides/agents-md)
- [OpenCode global/project instructions](https://opencode.ai/docs/rules/)
- [OpenCode project skills](https://opencode.ai/docs/skills/)

DSH's installed `dsh-agent-instructions` and `dsh-skill-filesystem` source was
inspected for `DSH_HOME/AGENTS.md` and project `.agents/skills` discovery. File
access tests do not claim that a live model discovered/loaded every skill.
