# Owner-requested clean reinstall — 2026-10-15

> **Historical record. Completed one-time cutover — do not rerun.**
>
> This document records the 2026-10-15 ordinary-user reinstall. It is retained as
> dated evidence, not as current state or procedure. Its arrangement runs every
> harness as the owner account and deliberately has **no per-harness UID boundary**,
> so the managed-worker isolation model in [SECURITY.md](SECURITY.md) does not apply
> to it and it cannot satisfy worker-isolation acceptance tests. The two
> arrangements are mutually exclusive per host; see the table at the top of
> SECURITY.md. Runtime state and current task state live in [ROADMAP.md](ROADMAP.md).

**Completed with owner approval.** The five applications now use the normal `huou07` account (standard rootless containers for the two gateways). `agents-worker`, four obsolete application accounts, their units/wrappers/ACLs and the worker-only AEH capability broker have been retired. Provider inference was intentionally excluded by the owner.

Current usage and retained instruction documents are also recorded in `/home/huou07/AEH/docs/normal-user-runtime.md`. Routine maintenance uses the normal user services; do not rerun this one-time cutover.

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
- All 97 repository tests passed; shell and migration Python syntax checked. Privileged cutover, new production databases and final localhost/VPN acceptance subsequently completed; see the runtime results below.
- Exact shared skills contents and shared AGENTS.md verified against their AEH document copies. Old instruction history and Git history are private migration material.
- Fresh LiteLLM/PostgreSQL and OmniRoute/Redis instances passed UI, health and persistence across restart with disposable new credentials/data. All their temporary containers, pods and volumes were removed; existing production gateways were untouched.

## Approved production procedure (completed)

The owner approved the complete transition and cleanup in this conversation. It was executed from the owner's normal SSH shell. `deployment` records the initial frozen checkout (`10a7178`); the root helper was subsequently repaired within the approved scope as described below. The original downtime estimate was 5–10 minutes; enumerating old ACLs took longer than expected and was changed to a native batch operation. SSH and VPN configuration were untouched.

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

Execution repair: the old home contained 1,537,304 ACL records. The per-file cleanup was stopped before project moves and resumed from its saved ACL snapshot using one native `setfacl --restore` operation, preserving all unrelated entries. VCE's old immutable `.git/config` flag was recorded and removed. No original backup was overwritten. The final root helper and original helper are retained under `/root` for audit. The later-discovered AEH socket accepted only the retired worker; its root broker, socket/template/slice, CLI and ledger were moved to the root-only recovery directory. The separate `h07p-lab` product verification fixture and owner-only preparation helper were preserved as project test infrastructure; none of the applications uses that identity.

The owner reset exports the exact three gateway volumes before removing their two pods and those volumes, moves old application config/native packages into the private backup, and installs the fresh native packages/profile. The existing installer creates new secrets, empty gateway databases and user units, then checks fresh gateway persistence and health. Standard rootless application containers remain the normal LiteLLM/OmniRoute deployment; the special agent identity and tool restrictions are removed.

`connect` replaces the dashboard's OpenCode public/backend login with the new owner-generated login, retaining public localhost4096/VPN14096 and backend4097. It fixes one existing LAN handoff condition so a browser with its DSH cookie reaches the page rather than looping through the login redirect. DSH trusts the explicit wg0 and LAN interface addresses. Provider login files are never imported.

`retire` runs only after runtime acceptance. It moves the named obsolete wrappers, units, app data/configuration and worker home into the root-only recovery directory, removes five obsolete service accounts plus the worker skill/workspace groups, and validates SSH/sudo syntax. The Playground service account and its DSH link read group remain. No live credentials are automatically revoked; old provider sessions require the owner to revoke them separately if desired.

## Failure recovery

Before root cutover, production services and their configuration are unchanged. A failed preparation can be retried after inspecting the named private logs and stage resources.

After quiesce, keep the old worker stopped. Original projects remain intact under `clean-reinstall-20261015/original-projects`; the original worker home and system configuration are in the root-only backup. Repair the fresh user installation and rerun health checks; do not automatically revive the abandoned worker model.

Before connect, the original dashboard is unchanged. After connect, the original application source is `/root/huou07-clean-reinstall-20261015/dashboard-app.before.py` and original configuration is in `original-system-config.tar`. To undo only a failed dashboard edit, install that saved Python file back to `/opt/huou07-playground/current/web/app.py`, then restart `huou07-playground.service`. Keep the fresh matching OpenCode login when running the new backend.

After retirement, no destructive deletion of private recovery material is performed. Account/service restoration would require owner review because it reinstates the retired execution model and potentially old provider credentials. The final acceptance record explicitly distinguishes host-side VPN route checks from an external device's VPN connection, and does not claim successful provider inference.

## Final runtime results

- Native versions: Codex 0.162.1, OpenCode 1.19.0, DSH 0.2.0-rc.2; both native ACP initialize handshakes passed again after the old binaries were removed. Developer tools, including CodeGraph 1.6.0, have independent owner installations.
- DSH and OpenCode service processes are UID1000. Both report `NoNewPrivileges=no` and no `InaccessiblePaths` override. Owner lingering and both native service enablement were verified. No old provider-key environment variables were present in the user manager.
- Fresh LiteLLM/PostgreSQL and OmniRoute/Redis passed health, UI and restart/persistence tests. Generated administrator passwords were then used successfully over VPN: OmniRoute issued an authenticated management session and LiteLLM opened its admin UI; the LiteLLM deployed model list is empty.
- Post-retirement application restart, DSH token-to-cookie exchange, authenticated DSH HTML, Playground launch, OpenCode authenticated health and anonymous denial all passed on the actual installation.
- External verification from the owner's Mac used its direct `utun5` VPN route, with HTTP proxies disabled: Playground launched real DSH HTML, its cookie remained usable, OpenCode UI/health and both gateway UIs loaded, and ports 20129/20132 accepted connections. This is additional evidence beyond the host-side VPN checks.
- AEH, OR, VCE and H07P are owner-owned at their requested paths. Both H07P histories are available in the active H07P clone, with the older setup branches under `refs/remotes/preserved-setup/`; fetching them did not change its working branch or uncommitted work.
- AEH document preservation is committed locally as `ef2a8de` on `codex/normal-user-runtime`. Shared skill bodies and shared AGENTS.md remain byte-for-byte copies; older owner-global skills and the former AEH guide are retained as labelled documents. Original unrelated dirty/untracked project work remains intact. Secret scans of the preserved skills and instruction documents reported zero findings.
- SSH, WireGuard gateway and Playground remain active. The old five accounts, worker binaries/controllers and both old control sockets are absent. No provider credentials were imported into the fresh login stores.

Private runtime receipts are under `/home/huou07/clean-reinstall-20261015`: `accepted.json`, `external-vpn-accepted.json`, `gateway-admin-login-accepted.json`, `post-retirement-acp.json`, project/content manifests and redacted secret-scan reports. Root-only original configuration, old service data, worker home, ACL/attribute records and retired files are under `/root/huou07-clean-reinstall-20261015`.

The clean login configuration does not revoke historical OAuth sessions or API keys at external providers. Those can be revoked separately by the owner. New provider sign-in and actual model inference remain owner-managed as requested; this normal shared-user deployment is not a credential/tool isolation boundary.
