---
name: h07p-isolation
description: Implement or review H07P worker permission rules, approvals, secret detection and Linux isolation. Excludes ordinary telemetry and styling.
---

# H07P isolation

Read [security](../../../docs/SECURITY.md) and
[architecture](../../../docs/ARCHITECTURE.md) for the scoped boundary.

## Procedure

1. Identify the worker principal, managed launch tree and operation/object at risk,
   including API/socket and same-UID bypass paths. Consult the current implementation
   map before assuming a launcher/control service exists. Use synthetic fixtures.
2. Specify expected allow/deny/ask behavior, conflict order and desired/enforced
   revision. Map operations to Linux reality; reject unsupported combinations.
3. Implement the smallest policy/control/launcher path. Keep owner authentication,
   helper IPC, binaries, DB and writable parents outside worker control.
4. Validate in a disposable real Debian guest: actual worker plus descendants,
   direct syscalls, API/helper forgeries, aliases, inherited handles and revocation.
   Include positive allows. The bounded local lab design and its current blockers
   are in docs/VALIDATION.md; do not launch without its resource/isolation guards.
   Hosted CI remains independent acceptance. Mock/container policy tests do not
   prove kernel enforcement; never use live owner permissions as fixtures.
5. For balance, use explicit scoped broker requests; for Auto Detect, redacted
   proposals and owner selection only. Never introduce a generic sudo executor.
6. Capture exact revision/run, applied policy and capability limits. On failure,
   stop affected workers or preserve known protection; never silently weaken policy.

## Completion and output

The selected journey succeeds for owner and fails for unauthorized worker through
all relevant paths. Report implementation, CI evidence, uncovered bypasses,
unsupported backend rights and owner acceptance separately. If a required runtime
capability is absent, name the discriminating next test; do not test the owner host.
