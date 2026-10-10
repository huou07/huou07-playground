# Deployment status

## Current host, inspected read-only

The repository is being prepared for a clean reinstall. The Dell currently has the dashboard, WireGuard, Docker and old app-specific services active. The owner confirmed experimental app data can be discarded. No application was stopped and no privileged command was run during this implementation.

Verified facts from the host inventory:

- Primary user: `huou07`; HOME `/home/huou07`; user lingering is enabled.
- Node 24.21.0, Podman 5.4.2, OpenCode CLI 1.18.35, Codex CLI 0.161.0.
- Codex reports an existing ChatGPT login; OpenCode's native auth command reports configured providers. Credential values were not read or shown.
- Rootless Podman is available. Current production rootful Docker is separate and remains untouched.
- Dashboard cards and port definitions are already present. The dashboard system unit is intentionally left in place so its WireGuard-bound listener and app relays are not disturbed.
- Old app services still run under their previous accounts until the owner runs the reviewed `retire` step. Reinstallation and browser acceptance have not happened yet.

## New clean-install files

The user installer targets DSH and ACP under `~/.local`, DSH profile/state under `~/.dsh`, the existing OpenCode CLI wrapper/config/auth under `~/.opencode`, app-generated settings under `~/.config/huou07-playground`, LiteLLM and OmniRoute state in owner rootless Podman storage, and standard `systemd --user` / Quadlet units.

The owner-run retirement helper is `deploy/admin/clean-playground-apps.py`. It has read-only preflight, reversible service retirement/rollback, and explicitly confirmed final deletion of only the previous app-specific accounts and paths. It does not touch the dashboard, WireGuard, Docker, Cockpit, other containers, or `/home`.

## Acceptance still pending

The owner must review and execute the admin preflight/retire steps, then the unprivileged install. Browser logins and DSH ACP agent setup require owner interaction. Model inference is intentionally excluded. Final cleanup is pending until browser acceptance.
