# Clean reinstall of playground-managed applications

This procedure replaces only the old DSH, OpenCode Web, LiteLLM/PostgreSQL and OmniRoute/Redis deployments. The owner has accepted loss of their experimental service-account data. The existing OpenCode CLI and Codex CLI under `/home/huou07` are retained. No operation here changes the dashboard, SSH keys, WireGuard (including UDP 3478), UFW, Cockpit, Docker, AN3, LAN Arcade, AdGuard Home, other containers or personal files.

## Versions and upstream choices

The Dell inventory identified Debian, Node `24.21.0`, Podman `5.4.2`, the existing OpenCode CLI `1.18.35`, Codex CLI `0.161.0`, an existing ChatGPT login, and owner rootless Podman. The clean installer uses that Node and Podman runtime.

- DSH `0.2.0-rc.2`; this is the npm version used by the official ACP-adapter compatibility instructions. DSH's web profile and `dsh plugin --profile web add` are its native Web/plugin installation paths.
- ACP adapter `0.2.0-rc.2.9`, pinned to its stated compatible DSH release. Its directory includes Codex; OpenCode supports `opencode acp` and can be added as a custom command.
- Codex ACP `2.2.2`; its published adapter advertises ChatGPT login and uses the native Codex home unless explicitly redirected. The installer does not set a separate `CODEX_HOME`.
- OpenCode Web uses the already installed native command, bound to `127.0.0.1:4096`, with documented HTTP Basic Authentication. `opencode web` shares session state with the CLI when run in the same user environment.
- LiteLLM `v1.104.2` uses its monolithic proxy image and a fresh PostgreSQL 16 database. LiteLLM's own docs identify PostgreSQL as its persistent management/auth store and require keeping `LITELLM_SALT_KEY` stable with that database.
- OmniRoute `3.8.51` uses the project's pinned self-host image and Redis cache. The release's self-host guide publishes the three app ports on loopback and the Redis service only on the private container network.
- Podman Quadlet files follow the installed Podman 5.4.2 parser; generator validation is included below.

## Stage 1: update the checkout on the Dell

As `huou07`, from the existing trusted project checkout:

```sh
git pull --ff-only origin main
git rev-parse HEAD
```

Confirm the revision matches the commit provided with this procedure. Do not run an older installer from another checkout.

## Stage 2: owner reviews and retires the old services

First run the read-only checks:

```sh
sudo python3 deploy/admin/clean-playground-apps.py preflight
```

It must report the exact five app units, the dashboard/VPN/Docker health, expected service identities and fixed old unit paths. It rejects unexpected users, unit overrides, symlinked homes, a changed dashboard, or an inactive protected service.

After reviewing that output, stop only the old app units and prepare the dashboard's existing DSH link directory:

```sh
sudo python3 deploy/admin/clean-playground-apps.py retire
```

This disables the old DSH, OpenCode Web, LiteLLM, LiteLLM PostgreSQL and OmniRoute units. It does not delete their data, user accounts, or user-specific Podman storage. The current dashboard cards point to the same loopback ports and remain in place.

If the new install does not work, restore the prior services while their data still exists:

```sh
sudo python3 deploy/admin/clean-playground-apps.py rollback
```

Rollback disables the new user units, moves only the new Quadlet definitions into `~/.local/share/huou07-playground/rollback/containers-systemd`, and re-enables only old services that were enabled and starts only those previously active. After fixing the issue, rerun the user installer with `resume` to restore the new Quadlets and services.

## Stage 3: install as the normal user

Log in as `huou07` and run:

```sh
./deploy/install-user-apps.sh check
./deploy/install-user-apps.sh install
./deploy/install-user-apps.sh status
```

The installer refuses occupied ports or conflicting app state. It installs DSH, Codex ACP and the exact adapter under `~/.local`; creates the DSH and OpenCode user units; installs rootless Podman Quadlets; and generates fresh application passwords and keys with mode `0600`. Application configuration uses `~/.config/litellm`, `~/.config/omniroute`, and the playground's small Web-password directory. It uses no sudo and does not read or copy the existing Codex/OpenCode credentials.

The DSH login URL is passed to the existing dashboard by a short launcher that filters bearer tokens out of the system journal. The one URL file is readable only by its owner and the existing dashboard group. OpenCode and DSH user units keep `NoNewPrivileges` and block the Docker socket as defense in depth; they still run as the owner's user and can access that user's files and credentials.

Check the interfaces from a browser connected through WireGuard, or through the existing SSH tunnel. Verify DSH Web and plugin settings, OpenCode Web login, LiteLLM UI/database readiness, OmniRoute setup, and the dashboard cards. No provider inference is needed for these checks. Add the two ACP commands in DSH as described in the root README. Provider sign-in and model use remain owner actions.

The owner already has lingering enabled. User services and Quadlets declare `WantedBy=default.target`, so they start under the persistent user manager after logout and at boot. Check after the first reboot when convenient; do not run a model request as a service test.

## Stage 4: remove the old app-only state after acceptance

Do this only after the new UIs have been opened and accepted. This is the destructive step; it requires the owner's explicit final review:

```sh
sudo python3 deploy/admin/clean-playground-apps.py finalize --accept-data-loss
```

It verifies all new app units and loopback ports, LiteLLM and OmniRoute health endpoints, and dashboard, WireGuard, and Docker status before removing anything. It then removes only the four old app service accounts, their exact `/var/lib` homes (including their rootless Podman storage), the named old DSH/OpenCode workspaces and app install/config directories, and the five old system unit files. It leaves the dashboard service account/group, the DSH dashboard-link group, and all shared networking untouched. Exact `/etc/subuid` and `/etc/subgid` rows for those old service accounts are removed with sibling backup files.

The checkpoint is removed only when finalization succeeds. Do not manually delete broader directories or run `podman system reset`, `docker system prune`, `userdel` on any other account, or a wildcard cleanup.

## If the admin preflight stops

Do not bypass it. It prints a concise mismatch such as a changed service identity, unexpected unit path, existing unit drop-in, or protected service health failure. Review that specific item before changing the script or host. The installer itself has no privileged commands.

## Official documentation

- [DeepSeek Harness CLI and Web profile](https://github.com/deepseek-ai/deepseek-harness/tree/master/apps/cli)
- [DSH ACP adapter install, compatibility and agent setup](https://github.com/zaimokuza-yoshiteru/dsh-acp-adapter)
- [Codex ACP install and ChatGPT auth methods](https://github.com/agentclientprotocol/codex-acp)
- [OpenCode Web](https://docs.opencode.ai/docs/web/), [OpenCode server auth](https://docs.opencode.ai/docs/server), and [OpenCode ACP](https://docs.opencode.ai/docs/acp)
- [LiteLLM deployment and database/key settings](https://docs.litellm.ai/docs/proxy/deploy)
- [OmniRoute v3.8.51 self-host guide](https://github.com/diegosouzapw/OmniRoute/blob/v3.8.51/docs/getting-started/SELF_HOST_GUIDE.md)
- [Podman Quadlet unit format](https://docs.podman.io/en/v5.4.2/markdown/podman-systemd.unit.5.html)
- [OpenAI Codex CLI documentation](https://developers.openai.com/codex/cli)
