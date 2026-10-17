# Credential Guard integration

Guard reuses the Playground owner API, typed helper boundary, existing worker
policy, and private file service. It does not add a second policy engine or
rewrite native application authentication.

- Monitoring is optional, bounded, and metadata-focused.
- Content scanning runs only for an owner-selected scope and returns redacted
  results.
- Cleanup requires a reviewed closed export and retains the original in
  protected quarantine before replacement.
- Restoration writes the original into private NAS; it does not put it back in a
  worker-shared location.
- Existing native authentication stores remain under their existing owner and
  application controls. Their same-UID access limitation is explicit.
- Fanotify interception, global MAC policy, memory/swap scanning, and provider
  login or model-inference tests are outside the implemented feature.

The source and regression paths are linked from the
[Guard behavior guide](README.md). Do not use prior task-specific deployment
authorizations as current permission to change a host.
