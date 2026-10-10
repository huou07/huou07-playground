# Deployment status

The Dell's previous clean-install attempt was rolled back successfully. All five original app services are active, and the dashboard, WireGuard, rootful Docker, AN3, AdGuard Home and unrelated services remain untouched. No old app data was deleted.

The corrected deployment path keeps those services running through full readiness. It accepts Podman's actual cgroup value `v2`, validates the exact OmniRoute unit description, pre-installs the required pinned packages and container images, validates user Quadlets and ACP initialize, and only checks app ports after the owner requests cutover. It does not directly enable generated Quadlet units. LiteLLM/PostgreSQL and OmniRoute/Redis start through their dependency graph. Cutover failure triggers restoration of the old app units.

The Dell checkout's prior local OmniRoute-description adjustment matches the repository correction and is incorporated. No live cutover has been run by Codex. Use [`docs/CLEAN-REINSTALL.md`](CLEAN-REINSTALL.md) for the one readiness command, cutover, rollback and post-install owner setup. Provider login and model inference remain owner-only; tests send no model prompts.
