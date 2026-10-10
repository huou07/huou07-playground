# Deployment status

The application replacement is **prepared, not deployed**. Preparation must be rerun from the pinned `main` commit on the Dell. It is designed to leave the old five application services and all protected services running until the owner runs the one-time switch in [`CLEAN-REINSTALL.md`](CLEAN-REINSTALL.md).

Current verified host evidence before this source update: the Dell checkout was `658fc2f`, the five old app services and the dashboard/WireGuard/Docker were active, user-scoped Codex/OpenCode/DSH packages and container images were present, and the rootless Podman pod/volume inventory was empty. Temporary runtime checks have since verified LiteLLM/PostgreSQL and OmniRoute/Redis against the freshly prepared configs on non-production ports; those exact temporary resources were removed. The corrected `UserNS`/Podman-volume behavior and current commit still require a final `prepare` run after the owner pulls this revision.

No final application listener was replaced, no provider inference was sent, and no old data/account was deleted. The owner must perform the switch and sign in to the browser UIs before deployment can be called verified.
