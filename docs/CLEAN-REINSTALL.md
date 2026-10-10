# Fresh application installation

This procedure prepares the replacement applications while the existing services stay online. It does not change the dashboard registry, dashboard UI, WireGuard, SSH, Cockpit, UFW, rootful Docker, AN3, LAN Arcade, AdGuard Home, personal files, or native Codex/OpenCode authentication. It does not delete legacy application data.

## Preparation

As `huou07` on the Dell:

```sh
cd /home/huou07/huou07-playground-setup
git pull --ff-only origin main
git rev-parse HEAD
./deploy/install-user-apps.sh prepare
```

Wait for `READY`. Preparation checks the pinned DSH/ACP packages and both ACP initialize handshakes without inference, validates the host's Quadlet generator and images, then starts fresh PostgreSQL/LiteLLM and Redis/OmniRoute on temporary loopback ports with disposable Podman volumes. It verifies both gateway UIs, database/Redis persistence across restart, and removes those temporary resources. It does not stop the existing application services.

The Dell's previously verified listeners and old-unit ownership are not readiness requirements. The old units' current health is irrelevant; the final ports are checked only after the owner stops those exact units.

## One-time switch

Only after preparation says `READY`, the owner stops and disables the five old application units, then activates the fresh user services:

```sh
sudo systemctl disable --now huou07-litellm.service huou07-litellm-db.service huou07-omniroute.service huou07-opencode-web.service huou07-dsh.service
./deploy/install-user-apps.sh activate
```

The first command touches only those five legacy application units. The second starts the existing user's prepared DSH, OpenCode Web, LiteLLM/PostgreSQL and OmniRoute/Redis services at the already-registered loopback ports. The dashboard and WireGuard remain in place. Activation verifies local service health and the DSH browser login flow. Do not run the old `deploy/admin/clean-playground-apps.py preflight` or `cutover` commands.

## Recovery

If activation fails or the browser check does not pass, run the user-level rollback first. It stops only the new app units, verifies the rootless containers stopped, and moves only the eight new Quadlet files to the named holding directory. It leaves new application data intact.

```sh
./deploy/install-user-apps.sh deactivate
sudo systemctl enable --now huou07-dsh.service huou07-opencode-web.service huou07-litellm.service huou07-litellm-db.service huou07-omniroute.service
```

If `deactivate` reports a unit or container still active, do not restore the old services on their overlapping ports. Keep SSH available and inspect the named fresh units/containers. No legacy data or accounts are removed by either procedure.

## Explicit legacy deletion manifest

Retain these until the owner has accepted the new apps in a browser. They are the only known disposable legacy targets; do not use broad home or Podman/Docker cleanup.

- System units: `/etc/systemd/system/huou07-dsh.service`, `huou07-opencode-web.service`, `huou07-litellm.service`, `huou07-litellm-db.service`, and `huou07-omniroute.service`.
- Legacy service accounts and their own homes/rootless stores: `huou07-dsh` at `/var/lib/huou07-dsh`, `huou07-opencode` at `/var/lib/huou07-opencode`, `huou07-litellm` at `/var/lib/huou07-litellm`, and `huou07-omniroute` at `/var/lib/huou07-omniroute`.
- Exact app paths: `/opt/huou07-dsh`, `/srv/huou07-dsh-workspaces`, `/srv/huou07-opencode-workspaces`, `/etc/huou07-litellm`, `/etc/huou07-omniroute`, `/usr/local/libexec/huou07-dsh`, `/usr/local/libexec/huou07-opencode`, `/usr/local/libexec/huou07-litellm`, `/usr/local/libexec/huou07-omniroute`, and `/etc/huou07-playground/opencode-web.env`.

Do not delete `/home/huou07/.codex`, `/home/huou07/.opencode`, the normal user account, dashboard registry, fresh rootless Podman storage, `/var/lib/huou07-playground`, or any rootful Docker resource. No deletion command is part of the initial switch.

## Owner sign-in after the switch

- DSH: open its dashboard card and configure Codex and OpenCode in **Plugins → ACP adapter**. ACP initialization is checked without inference; authenticated coding turns still require owner verification.
- OpenCode Web: use username `opencode`; its generated password is in `~/.config/huou07-playground/opencode-web.env`. It runs the existing CLI/configuration under `~/.opencode`.
- LiteLLM: open `/ui` through the existing card and use `LITELLM_MASTER_KEY` from `~/.config/litellm/litellm.env`. The PostgreSQL database and salt are fresh.
- OmniRoute: use the initial password in `~/.config/omniroute/omniroute.env`; configure provider accounts manually.
- Codex CLI: the existing native ChatGPT login was recognized during preparation. No login file is copied or reset.

No real model requests are made during preparation or acceptance. Provider sign-in and inference remain owner-managed.
