---
name: h07p-isolation
description: Implement or review H07P worker permission rules, approvals, secret detection and Linux isolation. Excludes ordinary telemetry and styling.
---

# H07P isolation

Read [security](../../../docs/SECURITY.md) and
[architecture](../../../docs/ARCHITECTURE.md) for the scoped boundary.

## Procedure

1. Establish branch/HEAD/tree, worker identity, managed launch scope and the exact
   operation/object at risk. Use synthetic fixtures; never inspect real credentials.
2. Specify expected allow/deny/ask behavior, conflict order and desired/enforced
   revision. Map operations to Linux reality; reject unsupported combinations.
3. Implement the smallest policy/control/launcher path. Keep owner authentication,
   helper IPC, binaries, DB and writable parents outside worker control.
4. Validate on hosted disposable Debian VM only: actual worker plus descendants,
   direct syscalls, API/helper forgeries, aliases, inherited handles and revocation.
   Include positive allows. Mock policy tests do not prove kernel enforcement.
5. For balance, use explicit scoped broker requests; for Auto Detect, redacted
   proposals and owner selection only. Never introduce a generic sudo executor.
6. Capture exact revision/run, applied policy and capability limits. On failure,
   stop affected workers or preserve known protection; never silently weaken policy.

## Completion and output

The selected journey succeeds for owner and fails for unauthorized worker through
all relevant paths. Report implementation, CI evidence, uncovered bypasses,
unsupported backend rights and owner acceptance separately. If a required runtime
capability is absent, name the discriminating next test; do not test the owner host.
