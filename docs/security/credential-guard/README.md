# Credential Guard

Credential Guard is an optional, bounded feature in the Rust Playground server.
It monitors only owner-selected scopes, reports metadata and redacted reasons,
and keeps content scanning as a separate explicit action.

## Monitoring

The watcher uses bounded inotify scopes and metadata inventories. It is reactive:
it cannot prevent a worker from copying a new secret into a path that the worker
can already access. Watch overflow, skipped paths, or missing roots are reported
as degraded coverage, not a clean result. Detection never changes worker ACLs.

## Reviewed export cleanup

Cleanup applies only to an owner-reviewed, closed export. A preview binds the
file identity and Guard revision and is single-use. Recognized credential
material is masked; if scanning still detects a known signature, the entire
export is withheld. Scanner failure prevents cleanup. Original bytes are kept in
protected quarantine before atomic replacement, and restoration creates a new
private NAS object. Live journals, active logs, databases, and authentication
stores are not rewritten.

The installed service redacts recognized sensitive output from managed web
workers before journald. Native applications that write directly elsewhere are
outside this filter. Large or binary lines can suppress diagnostics. Guard does
not guarantee detection of unknown secret formats or isolate same-UID native
authentication stores from their owner.

Source coverage is in `crates/server/src/guard.rs` and `redact.rs`; regression
coverage is in `tests/native/guard.py` and the package sandbox fixtures. CI and
production evidence must be reported separately.
