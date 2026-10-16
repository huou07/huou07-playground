# Credential Guard integration decisions

The pasted v1.0 specification is design advice. This delivery adopts the controls
that fit the existing H07P architecture and the owner's newer instructions.

- P0 was executed against Debian before any new Guard/systemd change; see `p0/`.
- Retain the three worker UIDs, shared home/apps/project skills and `none` default.
- Reuse the existing root policy helper, peer identity checks, SQLite policy store,
  owner proof/CSRF boundary and rollback. Do not build another ACL engine.
- Keep native harness authentication/provider/ACP transport unchanged. Own-store
  access is `UNRESOLVED_SAME_UID`, not full credential isolation. Do not silently
  replace it with a credential broker or revoke keys.
- Add bounded event-driven monitoring and metadata-only incidents. Privileged
  watching is metadata/control only; content scanning runs under an unprivileged
  identity. Disabling detection does not remove existing DAC/Landlock boundaries.
- Reuse the maintained Gitleaks scanner; never put matching bytes, raw headers,
  environments or original authentication files into reports/model context.
- Log cleanup is explicit and limited to registered closed exports. Plan before
  applying, retain originals in root-private quarantine, and restore into private
  NAS rather than re-exposing secrets in a shared log path. Never edit live
  journals, native authentication stores, databases or actively written logs.
- Redact recognized secret-bearing web-service output before journald when
  compatible; preserve interactive CLI terminal behavior. Detection is not proof
  that every unknown secret format has been removed.
- Use installer simulation/diagnostics, targeted dependency resolution, repair,
  rollback and data-preserving uninstall. Reject destructive/unrelated dependency
  plans rather than running a broad automatic package purge.
- Use Playwright CLI for active UI inspection/operation; ordinary automated test
  suites remain reproducible regression gates. Continue solo unless independent
  agent work clearly pays for its coordination/token cost.
- The owner explicitly permits bounded synthetic builds/tests/deployment on Dell
  Debian. The proposal's older hosted-only rule does not override that permission.
- Fanotify permission interception, new global AppArmor profiles, memory/swap
  scanning and real model/login tests are excluded. Report unverified/unsupported
  capabilities and target benchmarks honestly; do not claim blanket PROTECTED.
