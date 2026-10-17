---
name: h07p-files
description: Implement H07P private NAS and host Storage file operations, previews and recovery UX. Excludes generic navigation and isolation-only changes.
---

# H07P file journeys

Read [product](../../../docs/PRODUCT.md), [UX](../../../docs/UX.md) and
[security](../../../docs/SECURITY.md) for the affected flow.

## Procedure

1. Identify NAS versus Storage adapter, owner/service identity, destination scope
   and concrete journey. Do not mistake the existing Cockpit availability route
   for a NAS listing. Use fixture files with known hashes.
2. Reuse the current tokens, sidebar and compact panels. Specify loading/empty/
   error/cancel/recovery, keyboard focus and desktop/360px behavior.
3. Authorize before lookup/preview. Resolve paths safely using directory handles.
   Protect uploads, thumbnails, clipboard jobs and backups as private NAS data.
4. Stream bounded transfers; default no overwrite. Copy/move checks source and
   destination independently. Across filesystems finalize and verify durable copy
   before removal. Cancellation/partial failure must report each item truthfully.
5. Escape text; restrict active formats, decoder sizes and video Range requests.
   Do not enable autoplay/transcode workers by default.
6. Exercise on hosted fixtures: folder/create/rename, upload/download hash match,
   cut/copy/paste collisions, full disk/quota/disconnect, vanished targets and
   unauthorized worker filesystem/API/cache access. Reuse meaningful Playwright
   flows and capture dark/light desktop/mobile views.

## Completion and output

Owner completes the chosen file journey without data loss; private bytes remain
unavailable to workers. Report hashes, exact CI/run identity, recovery limitations,
source-only versus browser observations and any unverified human UX acceptance.
Do not use the owner's NAS or disk as a development test target.
