# Security and permission contract

## The two arrangements this product can run in

H07P has one security contract but two host arrangements, and they are mutually
exclusive per host. Reading them as one model is what made this document and
[ORDINARY-USER-REINSTALL.md](ORDINARY-USER-REINSTALL.md) disagree.

| Arrangement | How harnesses run | What enforces anything | Documented by |
| --- | --- | --- | --- |
| Ordinary-user | Every harness runs as the owner account (`huou07`) | Ordinary file permissions only; there is **no** per-harness UID boundary | [ORDINARY-USER-REINSTALL.md](ORDINARY-USER-REINSTALL.md) — Historical, once completed, do not rerun |
| Managed worker | Each harness runs under its own worker UID | ACL policy, permanent UID drop with empty groups, typed peer-checked IPC and the broker | this document, sections below |

The rest of this document describes the **managed-worker** arrangement, which is
what H07P's Permissions, broker and sandbox code implements. The ordinary-user
arrangement was the owner's 2026-10-15 choice; it deliberately removed the
credential/tool UID boundary, so none of the worker-isolation claims below apply
to it, and it cannot satisfy worker-isolation acceptance tests. A host that runs
harnesses as the owner must not be described as worker-isolated.

## Current owner-selected Debian account model

The 2026-10-16 owner task authorizes the H07P GUI to reset worker ACLs to the
saved pre-worker snapshot, detect/create/repair the supported DSH, Codex and
OpenCode workers, then configure broad ordinary-home access with private stores
and explicit Blocks preserved. A root-owned rollback snapshot is saved before
reset; project bytes and directories are not removed. The workers remain stopped
until Repair reapplies private-store protection.

The requested source behavior now supports an absolute workspace and rule target
anywhere on the system, including `/root`. A recursive Allow skips control-plane,
private-store, detected sensitive-name and hard-linked paths. Shared tool/runtime
trees remain read/execute only under a broad home Allow. Explicit Block rules are
enforced after all Allows and private exceptions. A private exception must name
one existing regular, unaliased file, applies only to its selected worker, and
requires an impact warning acknowledgement followed by a second Apply click.
Removing an explicit Block remains available in the rules list; removing a default
private denial requires an exact-file exception. Structural ACL limits still fail
closed; impact warnings do not reject a valid Apply.

The scanner accepts any canonical absolute file or directory, including hidden
directories such as `.config`, returns paths/reasons only, and keeps the existing
content/time/object limits. Its H07P GUI journey must be verified on the live
Debian host before these source changes are considered accepted. See
[harness workers](../deploy/harness-workers/README.md) and
[ROADMAP](ROADMAP.md).

## Threat model and immutable boundary

Workers execute arbitrary commands and may call HTTP APIs, follow symlinks,
create hardlinks, inherit file descriptors, fork processes or modify writable
configuration. A hidden GUI control is not enforcement. Trust the owner and
installed control plane; distrust worker code, imported files and scan results.
Protect NAS data, owner sessions, credentials and policy administration.

Root/kernel compromise and a deliberately cooperating owner are outside the
worker-isolation guarantee. Scope coverage to workers launched by H07P and their
descendants; do not claim this protects unmanaged processes or this editing session.
Workers cannot control policy, templates, approvals, helper binaries, installed
units, owner browser profiles, owner authentication material or writable ancestors.
These protections apply to every preset, including none, and cannot be edited
through the worker rule editor. Only the owner can administer them.

## Rule model

Use a versioned typed record: id, worker/workspace scope, absolute target,
file/directory kind, recursive flag, action (allow/block/ask), concrete operations,
source (manual/detection/template), optional expiry and policy revision.
Owner paths may be sensitive metadata; never publish a real host policy in Git.

| GUI operation | Required semantics |
| --- | --- |
| List | Enumerate directory entries without implicit content read |
| Read | Read bytes / preview / download |
| Write | Modify/truncate an existing file |
| Create | Create objects, separately from changing existing bytes |
| Delete | Unlink/remove; include parent-directory constraints |
| Execute / use | Execute a file; tool use may also require read, library and data access |

Rename/move requires source/destination operation checks; copy requires source
read and destination create/write. Directory write rights in Linux often permit
delete/rename: never claim those rights are independently isolated using chmod
alone. If a backend cannot enforce a selected combination, reject it or require
the broker; the UI explains the unsupported combination.

Execute means OS executable access; denying execute cannot stop an interpreter
from evaluating a readable script. Do not advertise prevention of arbitrary code
execution for a coding worker. Explain required read/runtime dependencies and
check whether direct access or a mediated operation can enforce the selected
rights. Unsupported granular rights must never be silently widened.

Evaluate immutable boundaries first, then any applicable block (deny wins),
then ask, then allow, then preset default. Overlapping allow cannot silently
override private descendants. To change a block, the owner edits/removes that
rule with an impact preview. Expiry/revision changes invalidate approvals.
A more permissive OS permission never overrides a compiled block.

Applying a template supplies editable defaults; custom rules remain explicit.
Show merge versus reset before changing templates. Neither template nor custom
Allow may cross the immutable administration/NAS boundary. A NAS Block rule is
an owner-visible dogfood operation with actual enforcement evidence; removing
that discretionary rule cannot grant worker NAS access, including under none.

## Presets

| Template | Worker data access | Sudo default |
| --- | --- | --- |
| minimal | Block owner-confirmed detected sensitive targets; other data subject to ordinary OS rights and custom rules | Disabled |
| balance | Workspace according to rules; outside data only through explicit owner approval | Disabled |
| strict | No outside-workspace host data access | Disabled |
| none | No discretionary worker file restrictions; OS rights and immutable owner/NAS boundaries still apply | No new privilege granted |

Strict has a minimal read-only runtime image with executable/dependency files;
these are declared runtime dependencies, not a grant to arbitrary host data.
Private homes, devices and sockets remain excluded. Expose the runtime manifest
to the owner; broad /home or /etc access must never be called strict.

Minimal only protects confirmed discoveries: show scan scope/time, ignored paths
and incomplete status. Selecting minimal before confirmation must warn that no
detected rules have been applied; it must not silently apply scanner output.
Preset changes are draft changes until owner confirmation, show grants/revocations,
and become Custom when edited. Adding sudo is never implicit and is excluded from
initial release; do not add a generic privileged shell to make none work.

## Balance approvals

An ordinary denied open(2) does not produce an approval dialog. Use an explicit
worker broker request or launcher integration: operation, resolved object identity,
workspace, worker, current revision, reason and short expiry. Owner accepts or
rejects using an independently authenticated owner session. Timeout is denial.

Keep direct outside-workspace syscalls denied. The broker performs only the
approved operation with descriptor-relative safe paths and bounded data exchange.
For tools requiring direct file handles, implement a separately scoped launch with
new policy after approval; document broader access and restart costs. Do not grant
an entire directory because one file was approved. Write/create/delete require
their own approval. An approval for another worker/revision/object cannot be replayed.
Audit approvals without command output, secrets or sensitive excerpts.

## Path and process enforcement

Use descriptor-relative resolution, no-follow/beneath semantics where available,
and fresh object checks; string normalization is insufficient. Cover traversal,
symlink swaps, mount points, hardlink aliases, renamed targets, writable parents,
/proc file descriptors, inherited handles and worker-accessible control sockets.
Reject ambiguous aliases and unsupported guarantees. Deny writes that could create
a new route into a protected object. Close inherited handles before exec.

NAS has dedicated service ownership and non-worker-searchable parents. Its bytes,
thumbnails, temporary uploads, backups and scan output share the private boundary.
An authenticated owner may grant a selected worker access to any canonical
absolute host target. Apply records the exact target and worker, snapshots ACLs,
keeps immutable control-plane/NAS boundaries, preserves default private denials,
and applies explicit Blocks last. Recursive Allow skips known shared runtime
trees' write access and sensitive paths; those paths need a separate reviewed
exception where supported. GUI worker reset restores the saved pre-worker ACL
baseline without deleting files, retains a root-private rollback snapshot, and
keeps services stopped until Repair reapplies peer-store protection.
Only recursive rules add default ACL entries to directories; nonrecursive rules
change access on the selected directory without adding or changing its defaults.

Policy updates use expected revision to prevent lost edits. Validate compiled
enforcement before activation; report Desired / Applying / Enforced / Failed.
Revoking access requires terminating affected managed process trees and handles.
Revocation cannot erase bytes a worker already read or copies it made while access
was permitted. State that limit and deny future access; do not promise retroactive
confidentiality. Keep NAS private before any worker launch so this limit is not
used to excuse a NAS leak. Same-UID workers require process/control-socket isolation;
workspace or cgroup labels alone do not prevent another process accessing a handle.
On failure, retain known protection or stop affected workers, report the applied
revision and offer an owner rollback; never silently drop to none.

## Auto Detect

Scanning runs under an owner-authorized service, not agents-worker. Default scope
is explicit selection, with bounded depth/bytes/time, cancellation and exclusions
for pseudo-filesystems, devices, sockets and network mounts. Metadata detection
comes first; content scanning only when the owner authorizes that scope.
Never use real owner files or NAS content as development fixtures.

Reuse a reviewed scanner/rule set; ensure matches are redacted before any logging
or serialization, not merely hidden by CSS. Return a path/object reference,
reason code, confidence and error/skipped state. No snippets or secret-derived
hashes. Keep reports owner-only and expire them. Ordinary-file suggestions mean
"No known sensitive marker", not proven safe. Report false positives/negatives.
Neither scan mode applies policy until explicit owner selection and Apply.

## API and preview boundary

Independent owner authentication, secure session storage, CSRF protection and
request authorization are prerequisites for all mutating and private APIs.
Do not trust local source IP, Origin, a workspace parameter or caller-supplied UID.
Socket peer identity is checked by the receiving helper; web sessions need their
own authenticated authorization. Worker tokens cannot become owner tokens.

Text is escaped; HTML/SVG and other active content download by default or use an
isolated sandboxed origin without owner cookies. Images/decoders have size limits;
video uses Range with bounded reads and no autoplay. No worker-visible API/cache
includes NAS paths, bytes, thumbnails, scan report or owner credentials.

See [VALIDATION.md](VALIDATION.md) for actual OS adversarial tests. Passing unit
tests of rule evaluation is necessary but cannot establish isolation.

### Worker-owned discretionary Block targets

ACL denial cannot reliably protect an object or enclosing directory owned by the
worker: its owner can change permissions or replace directory entries. Rule review
rejects Block targets with a selected worker owning the target, a covered descendant
or an ancestor. It does not silently claim enforcement or change native credential
ownership. Move protected data into an owner-controlled directory before retrying.
Own-harness native authentication keeps its existing behavior.
