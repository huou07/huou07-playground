# Product contract

## Outcome and scope

H07P is an open source, compact Linux web control panel for one owner to manage
their machine, isolate coding agents and privately manage files. Keep the current
design language. Ship Linux .deb first; other platforms display "Coming soon".
Rust is the target implementation for backend and OS integration. Support customization through documented configuration,
UI preferences and versioned policy templates. Extensibility starts with typed
internal adapters and versioned APIs; add extension boundaries for demonstrated
callers rather than a speculative plugin daemon or platform.

Optimization must preserve owner authentication, private NAS, worker credential
separation and safe data handling. Web-app discovery, shortcuts and VPN exposure
preserve each application's existing login behavior. Do not introduce passwords
or an authentication proxy for apps that have no existing password. Supported
password export/change is a separate explicit owner action for existing app logins.

This preparation stage maintains contracts and verification paths; the existing
Rust health/static baseline is mapped in [IMPLEMENTATION.md](IMPLEMENTATION.md).
Remaining migration and new screens are tracked only in [ROADMAP.md](ROADMAP.md).
No installation, deployment or testing on the owner's Debian machine is authorized.

## Permissions

An owner can browse a server-side path picker or type an absolute file/folder path,
choose Block or Allow, and customize list/read/write/create/delete/execute
permissions, recursive scope and any expiry. "Use" must expand into the concrete
operations, not an unexplained checkbox. Blocked targets are labelled Private.
Show effective rights, inherited rules, conflict reason and enforced status.
Offer a dry-run impact view, apply, audit history and owner-controlled rollback.

Auto Detect Block finds candidate passwords, credentials, API keys, permission
configuration and other sensitive files within an owner-selected scope.
Auto Detect Allow proposes ordinary files. Never expose matching contents.
Unknown, skipped, unreadable and possibly sensitive items are not "safe".
The owner selects what to block/allow and explicitly applies; scans never
silently grant access or block new files.

Security Levels are templates: minimal blocks owner-confirmed detected sensitive
targets; balance requires approval for outside-workspace access; strict prevents
outside-workspace data access; none adds no discretionary worker file restrictions.
The first three disable sudo by default. Every template is editable; customization
is marked Custom. None does not create sudo privileges, bypass Linux DAC or grant
administration/NAS access. See [SECURITY.md](SECURITY.md) for runtime dependencies.

## Files: private NAS

Files becomes an owner-only NAS area with folder creation, upload/download,
rename, cut/copy/paste and previews for text, images and video. No SMB/NFS daemon
is required for the first web NAS; future protocols must preserve the same boundary.
Display a Private badge and actual isolation status. Dogfood Permissions: the owner
selects the NAS directory and applies Block to workers in a CI journey. The NAS
cannot expose content to workers before that action; initial OS ownership protects it.

Preview bounded text safely, render images and stream browser-supported video.
Unsupported formats offer download and an explanation. Never execute documents
or silently transcode large videos. Uploads show progress/cancel, use atomic
finalization, quotas and explicit conflict choice. No overwrite by default.
Copy/move has destination confirmation, progress and partial failure recovery;
cross-filesystem moves remove the source only after verified durable destination.
Cancel cannot claim to undo a completed move. Any permanent deletion is explicit.

## Storage: host browser

Storage shows actual mounted filesystem total/used/free/available capacity with
GB/GiB labels, and browsing subject to owner OS rights. Include previews, rename,
cut/copy/paste, path copy and accessible navigation. Do not imply full host access
from a listing. Private NAS content uses the NAS service; Storage cannot become
an alternate worker gateway. Host modifications require owner authentication and
scope validation; no arbitrary root shell backend.

## Acceptance journeys

1. Owner blocks a fixture subtree using browse and typed path. Worker list/read/
   write/delete/execute fail through direct OS operations and HTTP paths; owner
   can still manage it. Allowing a separate fixture restores only selected rights.
2. Auto Detect classifies synthetic secrets without leaking values; cancellation,
   skipped files and false positives are visible. Nothing changes before owner Apply.
3. Each preset is exercised under a real worker process, including approval expiry,
   restart/revocation and worker attempts to modify policy or use an owner session.
4. Owner uploads a file into NAS, previews/downloads it with matching hash, creates
   and renames folders, copies and moves across fixtures. Worker cannot retrieve
   bytes through filesystem, API, preview, cache or alternate path.
5. Storage browses permitted host fixtures, reports filesystem capacity, copies a
   path and handles permission errors and destination collisions without data loss.
6. Existing navigation, app links, preferences and telemetry survive Rust migration;
   desktop/mobile keyboard flows complete with no unhandled console errors.
7. CI compares idle/open/transfer resource use and latency to a reproducible baseline.
   New .deb installs/upgrades/removes in an isolated Debian VM without deleting data.

Passing mocked checks is not OS or owner acceptance. Record each journey's observed
CI evidence and explicitly state missing human/hardware acceptance.
