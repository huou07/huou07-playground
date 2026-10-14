# H07P agent contract

H07P is huou07-playground: a small Linux dashboard becoming a Rust product for
owner-controlled agent isolation, private NAS and host storage management.
Optimize completed user journeys, latency, resource use and trustworthy isolation.
Commit counts, code volume and checklist completion are not product outcomes.

## Start here

1. Establish repository path, branch, HEAD and working tree. Preserve unrelated work.
2. Read [docs/README.md](docs/README.md), then only the contract for your task.
   [docs/PRODUCT.md](docs/PRODUCT.md) is product authority;
   [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) defines the target, not implemented state.
   [docs/ROADMAP.md](docs/ROADMAP.md) is the single task tracker.
3. Use a valid current CodeGraph index when available, verify against source;
   otherwise use the current harness's native search/read tools on relevant paths.
4. Load a project skill only if it is exposed in the current session catalog and
   its trigger matches. Disk files are candidates, not proof of discovery.
   DSH skills use the current DSH skill tool; never copy them into native caches.

## Authority and execution

- The owner's Debian host is NOT a test target. Do not run project tests,
  benchmarks, installers, services, package installation or deployment there.
  Read-only repository inspection and authorized edits/Git operations are allowed.
- Run executable validation on disposable GitHub-hosted Linux runners. Sudo there
  is permitted for fixture accounts, namespaces, systemd and .deb lifecycle tests.
  Never use a self-hosted runner or remote SSH to the owner's host.
- Push/publication/release to the existing project GitHub repository is authorized
  by the owner for this initiative. Release only an honestly described artifact
  whose applicable CI gates passed. A framework commit is not a product release.
  Do not deploy or install on the owner's machine without a later explicit request.
- Never read owner credentials, private NAS content or sensitive host paths for
  investigation. Use synthetic fixtures. Do not bypass OS/tool denials or use sudo
  on this host. Do not modify shared managed infrastructure.
- Historical deployment documents are archival data, never current evidence or
  executable instructions for agents.

## Invariants

- Preserve the existing branding, dark/light CSS tokens, sidebar and compact cards.
  No frontend framework or broad visual redesign without a demonstrated need.
- Rust replaces product backend, file operations and sandbox control incrementally.
  Browser code may remain JavaScript. Keep Python behavior as the parity reference
  until each replacement has CI evidence; do not rewrite third-party applications.
- Owner identity, worker identity, policy administrator and NAS data service are
  separate trust boundaries. A worker cannot administer itself by any API, socket,
  policy file, executable, writable parent directory or alternate launcher.
- Configuration is never evidence of isolation. Report desired and enforced policy
  separately. Reject unsupported security guarantees; do not silently weaken them.
- Auto Detect proposes redacted classifications; only the owner applies selections.
  No secret values in API responses, logs, diagnostics, screenshots or CI artifacts.
- Security presets are editable templates. The owner administration boundary and
  private NAS remain protected even under 'none'; none grants no new OS privilege.
- Reuse upstream implementations with provenance and compatible licensing.
  Redis is optional and requires evidence; never cache authorization as authority.
- Bound concurrency, memory, scan scope, previews and transfers. Avoid recursive
  scans, subprocess-per-poll and idle background work.

## Working and evidence

Use one observable slice from the roadmap. Update its status with source revision,
CI run and limitations. After two speculative repairs, write a falsifiable
hypothesis and a check that distinguishes it before another attempt.
Use existing deterministic gates, add meaningful boundary/journey regressions.
Do not run 'make check', 'make acceptance' or 'hub.py verify' on the owner host.
[docs/VALIDATION.md](docs/VALIDATION.md) defines CI validation and release gates.
Report implemented, tested, owner-accepted, blocked and unverified separately.
Never claim watts saved from CPU percentage or mocked permission tests.
Author framework docs, AGENTS and skills in English; converse in the owner's language.
