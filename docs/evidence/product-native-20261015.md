# H07P product integration — 2026-10-15

This is executed Debian evidence under the owner's explicit authorization in this
conversation. It is not hosted-CI evidence or human acceptance. Production was
kept on the prior Python release while these gates ran.

## Executed boundaries

- Rust 1.90 locked build, Clippy with warnings denied and 22 unit tests passed.
- `tests/native/product.py`: 57 checks passed with real PAM authentication using
  a temporary account, service/worker UIDs, HTTP/session/proof/CSRF, streamed hash
  integrity, byte ranges, aliases, NAS denials, revision conflict, ACL apply and
  rollback, approved reads and maintained-scanner synthetic detection. A real
  transient fixture service and its child were terminated by policy activation.
- `tests/native/browser.mjs`, called by the above fixture: real Chromium at
  360×800, real Rust/helper/PAM (no API interception), sign in, private NAS list,
  scoped download with hash verification, mkdir, GUI NAS Block review/apply/remove,
  and sign out passed. NAS privacy remains after removing the discretionary rule.
- `tests/native/broker.py`: 66 checks passed for scoped list/read/write/create/
  delete, actual peer UID, bounds, pending/denied/cross-worker/replay, immutable
  boundaries, object replacement, parent replacement, aliases, expiry, stale
  revisions, strict outside denial, redacted status and binary integrity.
- `tests/native/files.py`: 15 checks passed in a private mount namespace with
  an actual 2 MiB tmpfs. ENOSPC and canceled uploads did not publish a destination
  or leave an upload temporary. FIFO and symlink reads failed promptly. Actual
  mount capacity matched. 16/64 MiB streaming uploads/downloads matched SHA-256;
  debug adapter RSS samples were 9300/9176 KiB, within the stated fixed bound.
- `tests/package-sandbox.sh`: actual none/minimal/balance/strict processes in a
  synthetic chroot passed UID/groups/NNP/FD, native/workspace positive cases,
  cross-harness denial, Landlock outside/alias/descendant denials and fail-closed
  unknown policy checks. No real native CLI login or model request was made.
- `tests/package-cgroup.sh`: a synthetic transient systemd service and its forked
  child shared a cgroup and both terminated on stop. CLI wrapper PTY/pipe/literal
  argument contracts were separately tested with a fixture systemd-run adapter.
- Package boundary unit tests and isolated dpkg install/upgrade/invalid-upgrade
  rollback/remove/purge retained fixture data and restored prior entry points.
  Repeated fixture builds produced identical package hashes.
- Rust browser lane: 22 tests passed. Python-reference browser lane: 22 tests
  passed after allowing the dashboard's authenticated blob icons in its CSP.
  These lanes include synthetic APIs and do not replace the native journeys above.

## Security detail

A host cookie is sent to other ports on the same VPN IP. Consequently every
owner API, including GET and session confirmation, also requires a random proof
held only in dashboard memory. Cookie alone cannot retrieve that proof. Reload
requires signing in again. Downloads/media use expiring session-bound tickets
scoped to operation, area, path and file identity; logout revokes them. Neither
owner credentials nor the general proof are added to native app URLs.

The default remains none with the earlier broad shared-home ACL model. NAS,
control state, installed code, owner secrets and peer native stores remain private.
Balance/strict add Landlock only to managed workers. ACL cannot independently
represent write/create/delete; unsupported combinations fail explicitly. Broker
execute and folder archives are explicitly unsupported. Revocation cannot erase
bytes already copied by a worker.

## Release gates still open at this checkpoint

Fresh advisory/dependency review and Lintian, final release binary/package,
production installation and verification, final measurements, and VPN service
checks remain. Earlier selected telemetry parity and resource runs are diagnostic
baseline evidence, not performance acceptance for the final integrated release.
No claim of electricity savings, arbitrary hardware collector success, full
Unicode casefold identity, Android browser acceptance or a fresh-VM lifecycle is
made by this checkpoint.
