# H07P 0.3.0 — Dell GUI deployment evidence

This amendment was implemented solo under the owner's authorization to build,
test and deploy on Dell Debian. Human Android acceptance remains unverified.

## Exact artifact

- Runtime source: `0378a1d167a942d36e8cca6bfa9d8d98f7b2182f`.
- Package: `huou07-playground_0.3.0_amd64.deb`.
- Package SHA-256: `9d06671d52058c030e4ffd86095a0cd130ccf8447e9309209f37891c29ce1381`.
- Installed executable SHA-256: `4aa92e62cb6cef2b913f18b623b3478c9ffc18c0ae32bfadf2c7dddde806aea9`.
- Two builds with identical source/binary/epoch produced identical package bytes.
  Lintian completed without errors or warnings. The artifact copied to Mac matches.
- Release audit: 144 shipped dependency components, zero vulnerabilities/warnings;
  RustSec database `479c888ce4401313bca61ba4aba2d0f6244c4a09`, Cargo.lock SHA-256
  `69878fef9f60f4a2f4e0b5d123475d21b23e07a6dba0004d43abe5dc691087b7`.
  SBOM and notices are bundled. This does not guarantee absence of unknown flaws.

Guided update actually upgraded 0.2.2 to 0.3.0. Its APT plan removed no packages
and installed no unrelated dependency upgrades. Lintian was subsequently installed
as a validation tool. Doctor reports 0.3.0, clean package database and all four
services active. `current` resolves to `/opt/huou07-playground/releases/0.3.0`.
The Mac and Dell project checkouts were synchronized to the runtime source;
subsequent evidence-only commits do not alter the deployed binary.

## Delivered and exercised

NAS/Storage filename search, selected/all worker settings, supported harness
account lifecycle and repair, host localhost/LAN web-listener discovery, reviewed
VPN app relays, selected existing web-login exports/manual entries and supported
public bridge password changes are implemented. Exact generated login files merge
selected entries while preserving others; manual edits require explicit replacement.
Apps without passwords retain their existing authentication. No native provider
credential store was read into the agent context or rewritten.

Final Debian checks passed: 41 Rust tests, Clippy warnings denied, release build;
105 legacy checks; 85 real PAM/UID/ACL/API checks; 37 private-mount filesystem
checks; 27 private PID/mount namespace account/ACL lifecycle checks; 19 isolated
network relay/native-web-auth checks; 31 Guard checks; 34 browser contracts;
actual sandbox preset/override/disabled-worker and cgroup descendant-stop checks.
Real isolated dpkg install, upgrade, failed-upgrade rollback, manual rollback,
remove and purge retained fixture state. These fixtures used synthetic identities,
credentials and data. Production accounts were not created/removed merely for tests.

Playwright CLI exercised the installed package executable with synthetic PAM:
NAS search, harness detection, web discovery, unselected login-export defaults
and 390px worker dialog. No page errors were observed. The production VPN page
and health endpoint were also reachable from Mac without owner credentials.
Authenticated production-owner GUI journeys were not run.

An actual temporary encrypted WireGuard peer reached all nine declared services:
8765/9090/4000/51821/14096/3080/20128/20129/20132. Dashboard HTML and the full
70,642-byte product.js passed. Existing authenticated apps returned their expected
unauthenticated responses. The temporary peer/namespace was removed; persistent
WireGuard configuration was unchanged. Dynamic additional relays were exercised
in the isolated real network/interface fixture, not through this encrypted peer.

After deployment DSH UID995/GID984 and OpenCode UID993/GID982 had no supplementary
groups, zero effective capabilities and NNP=1. Dashboard was UID996/GID985 with
its service groups, zero capabilities and NNP=1. Codex remains UID994. Twenty-eight
production metadata/access checks confirmed shared `/home/huou07`, no sudo,
protected owner/NAS/control/backup boundaries and cross-harness store denial.
Harness detection found all three installed executables. Credential contents were
not opened. Own harness native authentication keeps its original behavior.

## Resource evidence and limits

[Repeated CLI observations](gui-resource-20261016.json): all three baseline NAS
windows made nine unrelated API requests in 16 seconds; all three installed 0.3.0
windows made zero. NAS list median/p95 ranged 9.3–10.6/11.8–13.2 ms baseline and
7.9–10.3/9.4–12.3 ms candidate. These short warm samples do not establish a broad
latency improvement. Hidden pages pause telemetry; dynamic relays wait on sockets
instead of periodic idle timers.

A metadata-only Dell home inventory covered 1,319,015 entries in 8.958 seconds,
peak RSS 15,544 KiB, changing no account or ACL. Job planning stages bounded SQLite
metadata and executes ACL batches; current bounds are five million entries,
300-second inspection and 900-second whole job. Synthetic fixtures exercise the
batch boundaries and repair failures. Actual full-home ACL repair was deliberately
not triggered just to benchmark a working host. File upload adapter peak RSS was
4328/4388 KiB for 16/64 MiB synthetic transfers.

There is no measured electricity saving or claim that no further optimization is
possible. Password support is adapter-specific: initial automatic export/change
handles the existing public OpenCode/DSH LAN bridge login. Hash-only passwords
cannot be recovered; unsupported apps use manual entry/native administration.
The GUI reuses existing WireGuard/WG-easy and reports missing tunnel setup;
external router forwarding and universal clean-machine VPN bootstrap are outside
this verified path. All three requested harnesses are supported, not arbitrary
future harnesses. Own-store same-UID and indirect shared-code limitations remain
as documented in SECURITY. Provider/model CLI login was not required or tested.
