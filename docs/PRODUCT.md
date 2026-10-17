# Product behavior

Huou07 Playground is an owner-operated Linux dashboard for host monitoring,
coding-worker control, and private file management. The v0.3.7 source implements
the product areas below. Source implementation, production observation, CI
verification, and owner acceptance are separate claims; see [STATUS](STATUS.md)
and [VALIDATION](VALIDATION.md).

## Implemented product areas

- **Monitoring:** host metrics, process/service status, Cockpit, VPN, and
  application availability.
- **Worker control:** supported worker discovery/lifecycle, per-worker rules,
  security presets, ACL enforcement, restricted process launch, approvals,
  policy history, and bounded sensitive-file suggestions.
- **Files:** owner NAS and host Storage browsing, previews, bounded upload and
  download, rename/copy/move, atomic replacement, recovery, and filename search.
- **Integrations:** selected harnesses and existing web applications, with
  reviewed VPN relays and supported login adapters that preserve existing app
  authentication.
- **Maintenance:** Linux amd64 Debian package install/update/repair/rollback and
  data-retaining removal.

The source map lists the implementation files. Production inspection confirmed
the installed dashboard was active and healthy, but did not rerun each journey.
Do not describe every source feature as independently production-verified.

## Security behavior

Owner controls are backed by Linux filesystem and process enforcement. Blocks
take precedence over overlapping Allows; protected owner/NAS/control-plane paths
remain outside editable worker policy. A private-file exception is scoped to a
selected worker and explicit owner confirmation. Workers do not receive
administrative capabilities through a preset. See [SECURITY](SECURITY.md) for
operation semantics and limits.

## Known limitations

- Native app authentication stores owned by the same human account are not
  isolated from that account by Playground.
- Detection is bounded and opt-in; it cannot guarantee discovery of every
  credential or sensitive file.
- Worker isolation guarantees depend on supported kernel and systemd features;
  unsupported guarantees must remain incomplete or fail closed.
- External apps keep their own data, updates, authentication, and provider
  credentials. Playground integration does not mean those apps are part of this
  repository.
- Current CI and the observed production health response do not establish
  universal package installation, every browser journey, or every host's
  kernel-enforced isolation.
