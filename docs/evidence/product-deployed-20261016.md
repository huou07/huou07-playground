# H07P 0.2.2 — deployed Debian evidence

The owner explicitly authorized bounded synthetic testing and actual deployment
on Dell Debian. Work continued solo for this amendment. This is physical Debian
and installed-package evidence, not a fresh hosted CI run or human acceptance.

## Artifact and source identity

- Branch: `codex/h07p-product`; packaged source:
  `55da5e5d8ebc3e7aff4cab4efab58ce2a3dd815c`.
- Package: `huou07-playground_0.2.2_amd64.deb`.
- Package SHA-256:
  `2dabddc477f1c70d18f0916c2aeb1579c00dd01e589c0b86f651966141ea45ae`.
- Installed stripped executable SHA-256:
  `33ba194e8b18af6ea1b5493433078360e0bc03124e8fe108226a8de43bb44ec1`.
- Unstripped release executable SHA-256:
  `dbdd4df33e2d909391e192600033098dd035f05a6d971bf6785ef96869d477e9`.
- Pinned Rust 1.90, locked dependency graph. Fresh RustSec audit matched upstream
  database `edb58f5974b83eb8302332821cb6d389777aa351`: 169 lockfile dependencies,
  zero reported vulnerabilities/warnings, no ignores. CycloneDX/notices are
  bundled; see [dependency audit](dependency-release-audit-2026-10-16.md).
- Final package passed Lintian without errors or warnings. Only the documented
  versioned `/opt` layout override is used.
- Rebuilding final 0.2.2 with the same binary/source epoch produced identical
  package bytes. The distribution copy on Mac matches the installed candidate.

The versioned release is `/opt/huou07-playground/releases/0.2.2`; `current` points
there. `dpkg` reports `install ok installed`; doctor reports no package database
issues. Dashboard, helper, DSH and OpenCode units are active and enabled.

## Installed journeys and failure recovery

The guided installer actually installed Gitleaks from the existing Debian repo
and H07P, with no unrelated package upgrade/removal. APT simulation precedes
mutation; owner configuration is retained. Actual update 0.2.1 → 0.2.2 passed.
Actual `h07p-setup repair --yes` reinstalled 0.2.1 successfully before that final
UI-only update. The installer/lifecycle code is unchanged between those versions.
Doctor and repair dry-run also passed on the target.

The first 0.2.0 cutover failed when DSH could not drop UID. Automatic rollback
restored the working Python release and both native services. A discriminating
systemd fixture found explicit `User=root` with this host's sandbox setup lost
CAP_SETUID (effective mask 0x47 instead of 0xc7). Default root retained it. Worker
and helper units now use default root for their trusted launcher/typed actors;
workers permanently drop IDs before native execution. Exact hardening was added
to actual systemd fixture gates, rather than weakening the identity assertions.

Observed production identities after installation:

| Service | UID/GID | Effective capabilities | NNP |
| --- | --- | --- | --- |
| Dashboard | 996/985 | zero | 1 |
| DSH managed parent | 995/984, empty supplementary groups | zero | 1 |
| OpenCode managed parent | 993/982, empty supplementary groups | zero | 1 |
| Privileged typed helper | root/service group | trusted administrator boundary | 1 |

The already-provisioned Codex worker remains UID 994; no Codex login/model call
was required. Existing shared home/apps/project instructions and per-harness
stores remain in place. No provider credentials were inspected, replaced or
revoked by this deployment.

The deployed helper actually performed a synthetic owner Storage read, private
NAS upload/read/delete and exact byte roundtrip. All three real workers were
denied access to that synthetic NAS object. All three successfully appended to a
new Storage object created through the deployed owner actor in a shared project
folder. Only test-created objects were removed. Guard reports PARTIAL with its
same-UID limitation; monitoring/content scanning default OFF pending owner opt-in.
An additional 33 post-deployment metadata/sudo checks passed: own native roots
remain accessible, peer roots/owner secret roots/control/backups are denied, and
sudo is denied for all three workers. Real credential contents were not opened.

The legacy installed Python dashboard contained native web proxy behavior beyond
the checkout baseline. Rust now preserves its OpenCode public/backend password
substitution, local/VPN/LAN listeners and DSH LAN handoff. Only public listener
metadata migrates from the adopted unit. Existing protected authentication env
files and native provider/ACP configuration are retained. Synthetic tests cover
HTTP body forwarding, chunked framing/trailer stripping, SSE and WebSocket
upgrade; production auth was checked only for unauthenticated rejection (401).

## Executed regression layers

- 32 Rust unit tests; format/Clippy with warnings denied; locked release build.
- 65 real PAM/UID/ACL/API checks plus real 360px Rust/PAM/NAS browser journeys.
- 66 scoped broker checks across all five supported approval operations.
- 31 Guard checks, also run with actual systemd helper hardening: inotify,
  closed-writer refusal, aliases, scanner failure, preview binding/single use,
  root-private originals, exact restore, restart persistence and detection OFF
  preserving worker denial. Ordinary staging/child deletion no longer reports a
  lost scope root.
- 22 descriptor/transfer checks including actual ENOSPC and interrupted atomic
  replacement preserving the original; 16/64 MiB transfer hashes matched,
  sampled adapter RSS 4060/3932 KiB.
- Actual sandbox/cgroup fixtures with positive native/workspace rights,
  none/minimal/balance/strict, UID/groups/NNP/FD closure, peer/alias/descendant
  denial, permanent-drop web stdout/stderr redaction and whole-cgroup stop.
- 17 maintenance boundary tests and isolated dpkg install/upgrade/failed-upgrade
  rollback/repeated rollback/remove/purge preserving data and original entrypoints.
  Uninstall was tested in the fixture, not against the now-running owner product.
- 105 Python reference tests, framework/link checks and real Rust HTTP smoke.
- 24 browser contracts on Rust and 24 on Python reference, including overlapping
  refresh prevention and absence of secure-context randomUUID.

Playwright CLI operated the real Rust/PAM mobile Guard flow using disposable
credentials: settings, preview, mandatory confirmation, cleanup, restore to
private NAS and logout. No API interception was used for that journey. Final
Playwright CLI inspection at the real VPN HTTP address found an insecure-origin
randomUUID bug; 0.2.2 replaces only UI IDs with getRandomValues. Reload on actual
`http://10.8.0.1:8765/#/permissions` now opens the login dialog with zero console
errors; the origin is confirmed insecure and randomUUID absent. Production owner
passwords were not used as test data.

## VPN evidence

A runtime-only peer with a private key held solely in process memory completed
an encrypted WireGuard handshake in a separate network namespace. All nine
declared service TCP/HTTP probes passed after final update:

| Service | VPN port | Unauthenticated response |
| --- | --- | --- |
| Dashboard | 8765 | 200 |
| Cockpit HTTPS | 9090 | 200 |
| LiteLLM | 4000 | 200 |
| wg-easy | 51821 | 302 |
| OpenCode | 14096 | 401 |
| DSH | 3080 | 401 |
| OmniRoute web | 20128 | 307 |
| OmniRoute API | 20129 | 404 at root |
| OmniRoute live | 20132 | 404 at root |

`product.js` transferred completely: 49,435 bytes, HTTP 200. Temporary peer,
interface and namespace were removed, original peer routes unchanged, persistent
VPN configuration untouched by this test. Mac's actual VPN address also served
health and the UI through Playwright CLI. Namespace transport does not reproduce
the Android carrier/NAT path; direct Android visual acceptance remains unverified.
401/404 transport responses do not prove authenticated app/model workflows.

## Resource and protection limits

Selected 18 stable telemetry parity checks passed. A three-repeat synthetic
Python/Rust comparison showed smaller Rust server RSS and CPU for that read
workload, with endpoint-dependent latency. It excluded the privileged helper,
native apps, PAM login and some short-lived collectors; it is diagnostic, not
full-product efficiency or energy acceptance. A separate five-second production
observation, with the unauthenticated VPN browser open, measured dashboard/helper
RSS 21,774,336/9,207,808 bytes and CPU 0.11/0 seconds, zero sampled write bytes.
This is an operational observation, not a matched baseline or watts saved.

Own native stores remain `UNRESOLVED_SAME_UID` by owner choice. Detection is
reactive, signature-based and bounded; unknown secrets may remain. Closed-export
cleanup never edits live journals, native authentication stores or active logs;
originals remain private. Source redaction covers managed web stdout/stderr only.
Full fanotify/global MAC/memory/swap scanning was not adopted from the advisory
proposal. Broker execute and folder archives remain explicitly unsupported.
No fresh-VM lifecycle, real provider login/model call, full hardware parity,
host reboot or direct Android acceptance is claimed.
