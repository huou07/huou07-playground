# Owner-requested clean reinstall — 2026-10-15

The owner replaced the former credential-isolation objective with a clean normal-user installation. Run DSH, OpenCode, Codex and their ACP adapters as `huou07`; run the standard rootless LiteLLM/PostgreSQL and OmniRoute/Redis deployment in that account. Remove `agents-worker`, its services, wrappers, ACLs and worker-only controls. Keep the existing Playground, VPN and unrelated services.

Preserve AEH at `/home/huou07/AEH`, OR and VCE at `/home/huou07/Projects/OR` and `VCE`, and H07P at `/home/huou07/Projects/H07P`. Preserve both pre-existing H07P histories, all local branches, staged/unstaged changes, untracked project files and VCE scratch archives. Build/dependency caches are reproducible and excluded from the initial transfer; a tracked-file check must reject an exclusion that removed tracked source.

Private migration backup: `/home/huou07/clean-reinstall-20261015` (0700). Old credentials are rollback material only, never automatically imported into fresh apps. Do not print secrets or commit private backups. Do not wipe SSH keys, owner sudo access, WireGuard state, dashboard registry, unrelated containers or projects.

Additional owner requirement: retain shared skills as AEH's `skills/` documentation, and preserve the exact shared `AGENTS.md` in `AEH/docs/writing-agents-md/`. Preserve `skills.md`, instruction history and framework Git history privately as provenance. Remove obsolete runtime links only after the copied document contents are verified.

Archived isolation experiment: commit `82c0c2b`. It was staging only, never a completed production isolation repair. The new ordinary-user arrangement deliberately has no separate credential/tool UID boundary; it cannot satisfy the superseded isolation acceptance tests.

Acceptance: independent owner-owned project copies match original HEAD, staged/unstaged diffs and untracked status; Git integrity passes. Fresh native CLIs resolve outside worker wrappers. DSH/OpenCode/ACP start as UID1000, fresh gateways pass UI/persistence checks, and Playground plus VPN routes reach the new backends. No provider inference is required by the latest owner instruction. Verify restart and removed worker services/account at runtime before reporting completion.

Root changes still require a concrete reviewed cutover under the original instruction. Prepare normal-user packages and project copies first. Never enable the obsolete root-launching `huou07-dsh.service`.

## Prepared evidence

- Project transfer archive SHA256: `81c3062b91371f1e230176c8152e28dbc312f50c4c825e397e00b8c4f051f2e0` (6.2 GiB; private).
- Independent clones: AEH `3cb2e4e`, OR `219bcf72`, VCE `0c3c9d88`, H07P `805861cf`; second H07P setup clone `f4cc44a1`. HEAD, staged/unstaged binary diffs, untracked status and Git integrity verified. VCE sparse-checkout metadata retained.
- All 2,731 preserved worktree files/symlink targets were separately compared against the owner clones, including ignored/untracked contents. Owner clone files are UID1000.
- Fresh normal-user native packages: Codex 0.162.1, OpenCode 1.19.0, DSH 0.2.0-rc.2, Codex ACP 2.2.2; DSH ACP adapter 0.2.0-rc.2.9 and pnpm 11.7.0 installed in the private preparation directory.
- Both native ACP initialize handshakes passed under UID1000 without provider login or inference. Fresh DSH browser authentication, forged-cookie rejection and restart passed under UID1000 on a temporary port.
- The live dashboard source with the proposed one-condition LAN fix passed an actual fresh DSH token/cookie/HTML flow, owner-login denial and forged-cookie rejection on temporary loopback listeners. The production source remains unchanged before approval.
- All 97 repository tests passed; shell and migration Python syntax checked. Privileged cutover, new gateway production databases and final localhost/VPN acceptance are still pending approval.
- Exact shared skills contents and shared AGENTS.md verified against their AEH document copies. Old instruction history and Git history are private migration material.
- Fresh LiteLLM/PostgreSQL and OmniRoute/Redis instances passed UI, health and persistence across restart with disposable new credentials/data. All their temporary containers, pods and volumes were removed; existing production gateways were untouched.

## Exact production commands for owner approval

Run from the owner's normal SSH shell. `deployment` is a frozen Git checkout of this change, with no old credentials. Expected application downtime is approximately 5–10 minutes; package/image downloads are prepared first. SSH and VPN configuration are untouched.

```sh
cd /home/huou07/clean-reinstall-20261015/deployment
sudo install -m 0700 deploy/retire-worker-root.py /root/retire-worker-root-20261015.py
sudo python3 /root/retire-worker-root-20261015.py quiesce
python3 deploy/reset-owner-apps.py
python3 deploy/install-fresh-owner-clis.py
sh deploy/install-user-apps.sh prepare
sudo python3 /root/retire-worker-root-20261015.py connect
sh deploy/install-user-apps.sh activate
python3 deploy/accept-owner-reinstall.py
sudo python3 /root/retire-worker-root-20261015.py retire
```

Stop at any failing command. Do not continue to account deletion without `accepted.json` from the real runtime checks. The root script has an explicit retirement manifest; it does not use broad Podman/Docker pruning or delete the owner account, SSH keys, sudo access, dashboard state, WireGuard state or unrelated projects.

`quiesce` checks the source project identities before stopping the exact old units and remaining UID987 processes; saves the worker home and system configuration privately under `/root/huou07-clean-reinstall-20261015`; removes only the retired worker/app identities' ACL entries and reclaims their artifacts in the owner's home; keeps original OR/VCE/AEH worktrees in the private migration directory; moves verified OR/VCE clones into their final locations; changes only the DSH handoff ownership to `huou07` with the existing dashboard read group.

The final safety revision keeps the same production command sequence and scope: Git metadata checks run as the old unprivileged worker with fsmonitor disabled, never as root; the worker login shell is disabled before stopping its remaining processes; source file bytes are checked again after shutdown so recent edits cannot be silently replaced. A partially started root cutover refuses a blind rerun that would overwrite its original backup.

The owner reset exports the exact three gateway volumes before removing their two pods and those volumes, moves old application config/native packages into the private backup, and installs the fresh native packages/profile. The existing installer creates new secrets, empty gateway databases and user units, then checks fresh gateway persistence and health. Standard rootless application containers remain the normal LiteLLM/OmniRoute deployment; the special agent identity and tool restrictions are removed.

`connect` replaces the dashboard's OpenCode public/backend login with the new owner-generated login, retaining public localhost4096/VPN14096 and backend4097. It fixes one existing LAN handoff condition so a browser with its DSH cookie reaches the page rather than looping through the login redirect. DSH trusts the explicit wg0 and LAN interface addresses. Provider login files are never imported.

`retire` runs only after runtime acceptance. It moves the named obsolete wrappers, units, app data/configuration and worker home into the root-only recovery directory, removes five obsolete service accounts plus the worker skill/workspace groups, and validates SSH/sudo syntax. The Playground service account and its DSH link read group remain. No live credentials are automatically revoked; old provider sessions require the owner to revoke them separately if desired.

## Failure recovery

Before root cutover, production services and their configuration are unchanged. A failed preparation can be retried after inspecting the named private logs and stage resources.

After quiesce, keep the old worker stopped. Original projects remain intact under `clean-reinstall-20261015/original-projects`; the original worker home and system configuration are in the root-only backup. Repair the fresh user installation and rerun health checks; do not automatically revive the abandoned worker model.

Before connect, the original dashboard is unchanged. After connect, the original application source is `/root/huou07-clean-reinstall-20261015/dashboard-app.before.py` and original configuration is in `original-system-config.tar`. To undo only a failed dashboard edit, install that saved Python file back to `/opt/huou07-playground/current/web/app.py`, then restart `huou07-playground.service`. Keep the fresh matching OpenCode login when running the new backend.

After retirement, no destructive deletion of private recovery material is performed. Account/service restoration would require owner review because it reinstates the retired execution model and potentially old provider credentials. The final acceptance record explicitly distinguishes host-side VPN route checks from an external device's VPN connection, and does not claim successful provider inference.
