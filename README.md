# huou07 playground

Current Debian harness deployment: [separate worker UIDs with shared home and
applications](deploy/harness-workers/README.md). Use this migration for the
owner-selected account/ACL model; earlier owner-user install instructions are
historical deployment paths.

An open source, compact Linux control panel evolving from a private Debian
dashboard. The legacy reference uses Python; the Rust health/static baseline is
already present. See [implementation](docs/IMPLEMENTATION.md) for actual coverage
and [product](docs/PRODUCT.md) for the intended customizable, extensible product.

## Product direction (2026-10-15)

H07P is being organized for Rust backend/OS integration, owner-controlled worker
isolation, private NAS and an integrated Storage browser. Health/static serving
exists in Rust; remaining migration and new features are incomplete. Preserve the existing design. Start at [docs/README.md](docs/README.md)
and [AGENTS.md](AGENTS.md); implementation handoff is
[docs/prompts/IMPLEMENT-H07P.md](docs/prompts/IMPLEMENT-H07P.md).

All tests/builds/package acceptance for this initiative run on disposable
GitHub-hosted infrastructure, and the live Debian lane exists only under the
owner authorization recorded in [PRODUCT.md](docs/PRODUCT.md) and
[VALIDATION.md](docs/VALIDATION.md). That authorization is the authority: this
paragraph defers to those two contracts, and where this README disagrees with
them they win. Do not install or deploy on the owner's Debian machine beyond
that authorization. The following sections describe the legacy implementation
and historical owner operations; they do not establish current host state.

## What runs where

| App | User service | Data/config | Private loopback port |
| --- | --- | --- | ---: |
| Dashboard | Existing system unit, unchanged | `/var/lib/huou07-playground` | 8765 |
| DeepSeek Harness | `dsh.service` | `~/.dsh` | 3080 |
| OpenCode Web and CLI | `opencode-web.service` plus existing CLI | Existing `~/.opencode`; Web password in `~/.config/huou07-playground` | 4096 |
| LiteLLM and PostgreSQL | Rootless Podman Quadlets | `~/.config/litellm`, Podman volume | 4000 |
| OmniRoute and Redis | Rootless Podman Quadlets | `~/.config/omniroute`, rootless Podman volumes | 20128, 20129, 20132 |

The dashboard already has application cards for these private endpoints and relays them through its WireGuard listener. The app services stay on loopback. Port definitions are in [`deploy/private-services.json`](deploy/private-services.json).

## Clean reinstall

Prepare the pinned applications while legacy services are still running, then stop only the five old application units and activate the new user services. Legacy accounts, files, databases, and credentials remain untouched until browser acceptance. The dashboard, WireGuard, SSH, Cockpit, rootful Docker, AN3, LAN Arcade, AdGuard Home, and unrelated data stay outside scope. See [`docs/CLEAN-REINSTALL.md`](docs/CLEAN-REINSTALL.md) for the exact sequence and rollback.

Readiness installs pinned software, validates ACP initialization and Quadlet generation, and pre-pulls images while existing services are still active. It also verifies fresh PostgreSQL/LiteLLM and Redis/OmniRoute instances on temporary ports with temporary volumes. Activation checks final ports after the owner stops the old units and then verifies the application health endpoints. A failed activation leaves all old data and unit files intact; the documented `deactivate` action stops and holds the new definitions before the owner restores the old units.

The installer pins DSH `0.2.0-rc.2`, DSH ACP adapter `0.2.0-rc.2.9`, Codex ACP `2.2.2`, LiteLLM `v1.104.2`, PostgreSQL `16`, OmniRoute `3.8.51`, and Redis `8.6.5-alpine`. It uses the existing Node 24, OpenCode CLI, Codex CLI, and rootless Podman. It does not perform model inference or add provider credentials.

## Owner setup

- DSH: open its dashboard card and use **Plugins → ACP adapter**. Add Codex from the adapter's agent catalog (`codex-acp`) and add OpenCode as a custom ACP command: `/home/huou07/.opencode/bin/opencode` with argument `acp`. The native Codex and OpenCode commands own their authentication and approvals. ACP initialization is not proof of authenticated inference.
- DSH dashboard launches require the existing owner Web login (`OPENCODE_PUBLIC_USERNAME` and `OPENCODE_PUBLIC_PASSWORD` in the root-protected `/etc/huou07-playground/opencode-proxy.env`). The worker backend password must differ. Missing owner credentials deny launch; configuring or changing those secrets is an owner action. This login gate alone does not isolate credentials from agent tools; see [the boundary repair status](docs/security/DSH-BOUNDARY-REPAIR.md).
- OpenCode Web: sign in with username `opencode`; the generated password is in `~/.config/huou07-playground/opencode-web.env`. The web service runs the existing CLI wrapper without `--pure`, so it uses the same OpenCode configuration and provider state as the owner CLI. The wrapper's existing state under `~/.opencode` is preserved.
- LiteLLM: open its card and sign in as `admin` with `LITELLM_MASTER_KEY` in `~/.config/litellm/litellm.env`. Add provider credentials and models yourself. The database and encryption salt are fresh; keep the salt with the database.
- OmniRoute: complete its dashboard login/setup through its card. The generated initial password is in `~/.config/omniroute/omniroute.env`. Configure providers yourself. Its API requires a key and the service stays loopback-only.
- Codex CLI: the existing ChatGPT login is preserved. If the native CLI reports signed out, complete its normal owner login.

Keep the SSH tunnel available until the WireGuard dashboard and app links have been checked from the client. The existing private app URLs and external WireGuard UDP 3478 configuration are unchanged.

## Deterministic checks

```sh
make check
```

This runs Python regression tests, shell syntax checks, and browser-free app configuration checks. It does not invoke any AI model. The Dell readiness and post-cutover checks also avoid model requests.

## Develop the dashboard locally

Requires Python 3.10+ and no third-party Python packages:

```sh
make run
```

Open `http://127.0.0.1:8765`. Browser acceptance tests use a temporary local registry and do not touch the Dell.

The project is GPL-3.0. App credentials, local dashboards, host inventories and generated secrets must not be committed.
