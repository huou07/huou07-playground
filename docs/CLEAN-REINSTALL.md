# Clean reinstall of playground-managed applications

This replaces only the old DSH, OpenCode Web, LiteLLM/PostgreSQL and OmniRoute/Redis deployments. The owner's native OpenCode and Codex installations and credentials stay in `/home/huou07`. Dashboard, SSH, WireGuard (UDP 3478), UFW, Cockpit, rootful Docker, AN3, LAN Arcade, AdGuard Home, unrelated containers and personal files are outside the cleanup scope.

## Pinned software and readiness

The Dell inventory verified Debian, Node `24.21.0`, Podman `5.4.2`, OpenCode CLI `1.18.35`, Codex CLI `0.161.0`, rootless Podman and a ChatGPT-authenticated Codex CLI. The installer pins DSH `0.2.0-rc.2`, its compatible ACP adapter `0.2.0-rc.2.9`, Codex ACP `2.2.2`, LiteLLM `v1.104.2`, PostgreSQL `16`, OmniRoute `3.8.51`, and Redis `8.6.5-alpine`.

As `huou07`, update the Dell checkout to the reviewed commit. Then run the single administrator readiness command below. It validates exact old service identities and listener ownership, protected services, free-space/runtime prerequisites, and the rollback state; it then runs `deploy/install-user-apps.sh prepare` as `huou07` while all old application services remain running. That preparation installs the pinned CLIs/plugin, checks Codex and OpenCode ACP `initialize` without inference, creates owner-only settings, validates the actual Quadlet generator, and pre-pulls all container images. The prior rollout's cgroup output `v2` and OmniRoute description are handled explicitly. An incompatible user file, app name or version must be reviewed rather than overwritten.

```sh
git pull --ff-only origin main
git rev-parse HEAD
sudo python3 deploy/admin/clean-playground-apps.py preflight
```

Proceed only when the final output says `READY FOR CUTOVER`. The warning about the owner's existing sudo/Docker privileges is informational; this procedure does not change either privilege.

## Cutover and automatic rollback

This one administrator command saves the old service enabled/active state, stops and disables only the five named old app units, and asks the normal user manager to start DSH, OpenCode Web, LiteLLM/PostgreSQL and OmniRoute/Redis. It checks services, local health endpoints, dashboard/WireGuard/Docker status, and the DSH private login link. Old app data and accounts are left in place.

```sh
sudo python3 deploy/admin/clean-playground-apps.py cutover
```

If activation or validation fails, the command automatically stops the new services, moves their Quadlet definitions into the owner-owned rollback holding directory, restores the previous services' enabled/active state, and reports the failure. If a manual rollback is needed after a successful cutover, run:

```sh
sudo python3 deploy/admin/clean-playground-apps.py rollback
```

The new Quadlets are preserved under `~/.local/share/huou07-playground/rollback/containers-systemd`; after resolving the cause, rerun `preflight` to install them again. The old installations remain intact for rollback until final acceptance.

## Owner browser setup

Open the dashboard over WireGuard and verify each card. DSH Web keeps its browser login link in the existing private dashboard flow. In DSH **Plugins → ACP adapter**, add Codex from the adapter catalog and OpenCode as a custom ACP command using `/home/huou07/.opencode/bin/opencode` with argument `acp`. Confirm both agents appear; initialization is verified without a real inference turn.

OpenCode Web uses the existing CLI/configuration under `~/.opencode`, with Basic Auth username `opencode`; its generated Web password is in `~/.config/huou07-playground/opencode-web.env`. LiteLLM's admin key is in `~/.config/litellm/litellm.env`; its PostgreSQL volume and salt are fresh. OmniRoute generates its initial admin password in `~/.config/omniroute/omniroute.env`. The owner signs in and configures provider credentials. No model calls are part of install or acceptance.

User services are enabled in the lingering `huou07` systemd manager and Quadlets are generated at manager reload. Keep the existing SSH tunnel available until the WireGuard paths have been checked. A reboot-survival check can be done after browser acceptance; do not reboot solely for readiness.

## Final cleanup after acceptance only

The destructive command below removes only the four verified old app-specific users, their fixed homes and rootless Podman data, listed old app paths, exact old system units, and their subordinate-ID rows. It runs only after the new applications pass browser acceptance. It never runs Docker prune/system reset and never sweeps broad home, system or container paths.

```sh
sudo python3 deploy/admin/clean-playground-apps.py finalize --accept-data-loss
```

Do not run final cleanup before the owner has signed in to the new interfaces and accepted the result.

## Upstream references

- [DeepSeek Harness CLI and Web profiles](https://github.com/deepseek-ai/deepseek-harness/tree/master/apps/cli)
- [DSH ACP adapter compatibility and agent setup](https://github.com/zaimokuza-yoshiteru/dsh-acp-adapter)
- [Codex ACP and native authentication](https://github.com/agentclientprotocol/codex-acp)
- [OpenCode Web](https://docs.opencode.ai/docs/web/), [server authentication](https://docs.opencode.ai/docs/server), and [ACP](https://docs.opencode.ai/docs/acp)
- [LiteLLM proxy deployment](https://docs.litellm.ai/docs/proxy/deploy)
- [OmniRoute 3.8.51 environment contract](https://github.com/diegosouzapw/OmniRoute/blob/release/v3.8.51/.env.example) and [Docker guide](https://github.com/diegosouzapw/OmniRoute/blob/release/v3.8.51/docs/guides/DOCKER_GUIDE.md)
- [Podman 5.4 Quadlet](https://docs.podman.io/en/v5.4.2/markdown/podman-systemd.unit.5.html)
- [OpenAI Codex CLI documentation](https://developers.openai.com/codex/cli)
