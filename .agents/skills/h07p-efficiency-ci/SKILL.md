---
name: h07p-efficiency-ci
description: Migrate H07P backend behavior to Rust, diagnose resource costs, and validate hosted CI or Linux .deb acceptance. Excludes routine docs and prompt edits.
---

# H07P efficiency and CI

Read [architecture](../../../docs/ARCHITECTURE.md),
[validation](../../../docs/VALIDATION.md) and [roadmap](../../../docs/ROADMAP.md).

## Procedure

1. Establish exact source and one user-observable slice. Preserve design assets
   and Python reference until parity evidence exists. Do not scaffold unused crates.
2. Use maintained Rust libraries with pinned Cargo.lock/features and reviewed
   licenses. Build/test only on disposable GitHub-hosted machines.
3. Compare the same fixtures, workload and sample duration. Capture latency
   distribution, CPU time, memory, writes, subprocesses and transfer integrity.
   Include helper/collector/Redis cost. Historical samples are not a fresh baseline.
4. Fix measured bottlenecks with bounded concurrency, streaming, shared collection,
   visibility-aware polling and in-process cache before external Redis.
5. Add meaningful parity/boundary regressions and required hosted gates. OS/package
   checks use disposable Debian VM; capability skips cannot count as acceptance.
6. Review action pins, token permissions, untrusted PR inputs and artifact redaction.
   A release needs exact passed gates and honest notes, not a count of completed tasks.

## Completion and output

Report changed product behavior, comparable measurements and variance, CI revision/
run, license provenance and remaining acceptance gaps. No invented watts saved.
If two speculative repairs fail, state a falsifiable hypothesis and discriminating
check before continuing. Never run installers, tests or power tuning on the owner host.
