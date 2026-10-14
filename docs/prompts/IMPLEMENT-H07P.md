# H07P implementation prompt

Work in the existing huou07-playground repository registered in the Hub.
Read AGENTS.md and docs/README.md, then PRODUCT, ARCHITECTURE, SECURITY,
VALIDATION and the relevant UX contract. Establish current branch, HEAD and tree;
preserve unrelated work. Use docs/ROADMAP.md as the single tracker.

Implement the real product described by these contracts, starting now with P1:
a minimal Rust backend serving the existing branding/static UI, health and then
safe read APIs, with Python parity fixtures, locked dependencies, GitHub-hosted
Rust checks, existing browser journeys and reproducible resource baseline.
Keep the current green dark/light design, sidebar and compact cards. Do not stop
after another plan, empty scaffold or passing unit tests.

Continue with owner authentication and versioned Block/Allow templates, then real
Linux worker enforcement, balance approval broker, owner-selected redacted Auto
Detect, private NAS in Files and host browsing/capacity in Storage. Complete each
observable slice before advancing; use evidence to adjust implementation order.
Never ship sensitive GUI/API operations ahead of their authentication/enforcement.
Workers cannot change their own rights or access private NAS through filesystem,
HTTP, sockets, cache, previews or alternate launch paths. Desired policy and actual
enforced revisions must be visible. Security Levels are editable templates;
none never grants administration, NAS access or new OS privileges.

Reuse maintained open source libraries and suitable upstream source with exact
provenance/license notices. Migrate backend/control to Rust; retain browser
JavaScript unless an observed need justifies more. Redis is optional: include it
only after demonstrating benefit including its idle cost against in-process cache.
Optimize actual journeys, latency, bounded memory, idle work and energy-related
resource cost; code size/checklists/commit counts are not acceptance.

You may use sudo for test fixtures inside disposable GitHub-hosted Linux/Debian
VMs. Do not use self-hosted runners, test/benchmark/install/deploy on the owner's
Debian machine, SSH there, read real credentials/NAS, or invoke host admin scripts.
Push to the existing huou07/huou07-playground GitHub repository; publication/release
for this initiative is authorized, but only release an honestly described Linux
.deb artifact after its exact commit passes required gates. Other platforms are
Coming soon. Do not install the release on the owner's host without a later request.

Load project skills only when exposed in the current session catalog; DSH uses
its own skill tool and connection. Otherwise read contracts directly and report
skill discovery unverified. Do not fake discovery or copy private skill caches.
After two speculative repairs of the same failure, state a falsifiable hypothesis
and run a discriminating hosted check before another attempt.

Keep working until the selected product outcome and authorized CI evidence are
complete. Update ROADMAP with exact revision/run links and limitations. Report
implemented, CI-tested, owner-accepted, blocked and unverified separately.
Communicate with the owner in Vietnamese; author framework docs and skills in
English. At handoff provide the next concrete product slice, not another generic
prompt or an unsupported production/security/performance claim.
