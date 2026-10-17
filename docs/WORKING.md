# Working guide

This repository contains the recovered first-party Playground source and its
public documentation. Product behavior is described in [PRODUCT](PRODUCT.md),
architecture in [ARCHITECTURE](ARCHITECTURE.md), worker boundaries in
[SECURITY](SECURITY.md), and current work/evidence in [ROADMAP](ROADMAP.md).

## Scope and authority

Documentation and historical deployment records do not authorize access to
production. Treat the installed system as read-only unless the current owner
request explicitly authorizes a particular change. Never restart services,
change authentication or worker policy, alter ACLs, install packages, access
credentials, or read private user files as part of source publication.

The source tree may contain integration adapters and generic package templates.
Do not publish third-party applications, provider credentials, authentication
state, production environment files, host inventories, private NAS data, or
runtime snapshots. Use source and template configuration only.

## Task loop

1. Establish repository path, branch, HEAD and worktree state; preserve unrelated
   changes.
2. Read the applicable source map and product/security contract before editing.
3. Ground production claims in current, permitted read-only evidence. Keep
   source, production, CI and owner-acceptance evidence distinct.
4. Make the smallest change that fully addresses the request. Do not recreate
   working code from memory or change product behavior during source recovery.
5. Run existing checks in their authorized environment. Production is not a
   build, stress, package-install, or destructive test target.
6. Record exact source and CI identities, limitations, and remaining work in
   [ROADMAP](ROADMAP.md).

## Evidence and publication

Source presence means implemented, not production verified. A health response
does not prove every feature journey. CI applies only to the exact commit it ran
against. Report unsupported environments as incomplete, never as a pass.

Before publishing, inspect the candidate tree and relevant history for secrets
and private deployment state. Do not stage secret values or copy them into
reports. Preserve public Git history; never force-push or replace it with an
unrelated history. Use the normal PR and branch-protection workflow.
