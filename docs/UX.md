# UX contract

## Preserve the established design

Reuse web/static/style.css and navigation.css tokens: dark green surfaces,
green accent, light theme, compact panels, sidebar, branding and visible focus.
Keep existing route names. Files becomes NAS; Storage remains host storage.
Add one Permissions route rather than scattering security controls across pages.
Do not introduce a frontend framework or replace branding for this work.
Source inspection is not visual acceptance; capture desktop and 360px CI screenshots.

Primary user is the machine owner using mouse, keyboard or touch. Workers can
receive narrow denied/approval status but cannot access the administrator UI.

## Permissions journey

Page header: Security Level selector, effective preset/Custom label, managed-worker
coverage and Desired/Enforced revision status. Toolbar: Block, Allow, Auto Detect.
Rules list: target, Private badge, operations, inheritance/source and state.
A rule editor supports Browse or absolute path input, file/folder identity,
recursive scope, list/read/write/create/delete/execute toggles, expiry and impact.
Unknown/unreadable paths have clear errors; do not create an unexpected target.

Workspace and permission targets accept canonical absolute paths across the host;
the Browse control can use typed paths when the owner session cannot enumerate a
directory. The worker setup dialog can restore ACL/ownership metadata from the
saved pre-worker snapshot without deleting files, and explains that workers stay
stopped until Repair completes. Auto Detect accepts a single file or any directory,
including hidden configuration paths. It never displays matched content.

The impact review distinguishes blocking structural errors from warnings. For a
warning, the first Apply click displays the acknowledgement step and the second
confirms enforcement. An exact-file private-path exception is visibly labeled and
requires this two-click flow. Explicit Blocks remain removable from the rule list;
removing a default private denial uses the corresponding exact-file exception.

Review grants and revocations before Apply, especially broad parent directories.
A preset change must not silently discard custom rules. Preview merge/reset choices.
Long operations show Applying; when restart is required explain which worker
tasks will stop and allow cancellation before applying. Success is Enforced only
after backend confirmation. Failure preserves inputs and offers a safe retry/rollback.
A lockout recovery method is owner-only and outside the worker UI.

The Credential Guard watch roots accept canonical absolute directories anywhere
on the host. Traversal is bounded by the inotify folder/watch limits and skips
protected stores and pseudo-filesystems. Cleanup roots may also be anywhere, but
must be owner-owned and outside protected stores; each log still needs a preview
and explicit confirmation before replacement.

Auto Detect has Block / Allow modes, scope picker and Start/Cancel controls.
Results show reasons/confidence/skipped items, selections and "Review selected".
No content previews, secret values or default Select All/auto-apply.
Allow suggestions warn "No known sensitive marker". Show zero-results and partial
scan states. Owner confirmation lists only selected changes and their effects.

Approvals show worker/workspace, operation, target, reason, expiry and policy
revision. Approve once / Deny are explicit. No indefinite broad allow default.
Expired or stale approvals cannot be accepted; show how the worker can request again.

## Files and Storage

Shared small file-browser component, distinct data adapters and authorization.
Breadcrumbs, back/up, sortable paginated list, selection count and keyboard context
menu. Path input/copy path lives in Storage and path picker; NAS uses its logical
root without exposing host topology to workers.

Primary toolbar: New folder, Upload, Download; contextual Rename, Cut, Copy, Paste.
Paste shows destination and collision choices; default skips conflicts. Cross-device
moves explain progress and remaining source. Clear clipboard state after a completed
cut, preserve it on partial failure with per-item results. Uploads support cancel and
never show a corrupt partial file as complete. Drag/drop has equivalent buttons.

Preview drawer/dialog: close returns focus to selected row; bounded text, lazy
images, video controls with no autoplay; unsupported formats offer Download.
Show total/used/free/available filesystem space with units and sampling timestamp
in Storage. Distinguish free blocks from space available to the browsing identity;
explain reserved space instead of displaying four ambiguously labelled numbers.
Network errors, permission denied, vanished objects, quota/full disk and unsupported
operations have specific recoverable states. Empty directories offer New folder.

## Acceptance

Test loading, empty, partial, success and failure states for each new journey.
Keyboard focus must enter/leave dialogs correctly, Escape cancels, async status uses
aria-live, names describe actions, mobile targets are usable, narrow screens do
not overflow. Respect reduced motion and preserve light theme. Do not persist owner
tokens or private file contents in localStorage. UI preferences may remain there.

Playwright assertions and screenshots are CI regression evidence. Human owner
acceptance of look/feel and real-device video support remains separately recorded.
