---
name: h07p-efficiency-ci
description: Migrate H07P backend behavior to Rust, diagnose resource costs, and validate hosted CI or Linux .deb acceptance. Excludes routine docs and prompt edits.
---

# H07P efficiency and CI

Read [implementation](../../../docs/IMPLEMENTATION.md),
[architecture](../../../docs/ARCHITECTURE.md),
[validation](../../../docs/VALIDATION.md) and [roadmap](../../../docs/ROADMAP.md).

## Procedure

1. Select the incomplete migration boundary from the tracker and current source map.
   Preserve design assets/Python reference. Reuse the existing health/static crate;
   do not recreate completed scaffolding. Compare fixture inputs, sampling state,
   null/unavailable fields, units and declared tolerances, not just JSON keys.
2. Use maintained Rust libraries with pinned Cargo.lock/features and reviewed
   licenses. Build/test only on disposable GitHub-hosted machines.
3. Compare the same fixtures, workload and sample duration. Capture latency
   distribution, CPU time, memory, writes, subprocesses and transfer integrity.
   Include helper/collector/Redis cost. Historical samples are not a fresh baseline.
4. Fix measured bottlenecks with bounded concurrency, streaming, shared collection,
   visibility-aware polling and in-process cache before external Redis.
5. Exercise actual Rust HTTP responses in the preserved UI; the current Python
   browser runner and intercepted APIs cannot prove Rust parity. Add meaningful
   parity/boundary regressions and required hosted gates. OS/package
   checks use disposable Debian VM; capability skips cannot count as acceptance.
6. Review action pins, token permissions, untrusted PR inputs and artifact redaction.
   A release needs exact passed gates and honest notes, not a count of completed tasks.

## Completion and output

Report changed product behavior, comparable measurements and variance, CI revision/
run, license provenance and remaining acceptance gaps. No invented watts saved.
Use shared verify-debug for failing-check repair rather than duplicating its loop.
Default: never run installers, tests or power tuning on the owner host. The
current owner authorization in [working guide](../../../docs/WORKING.md) and
[validation](../../../docs/VALIDATION.md) supersedes this default while it stands
and is the authority for the live Debian lane; it does not authorize installers,
credential changes or power tuning beyond what it names.
