# Worker account and ACL adapter

`setup.py` is a first-party Linux package component. `tools/build-deb.sh` installs
it as the package's worker ACL adapter; the owner-facing flows are implemented
in Rust under `crates/server/src/worker_setup.rs` and `deploy/package/workers.py`.
It supports the managed worker setup and recovery paths used by Playground.

The adapter uses bounded planning, preserves file contents, and records ACL
metadata in a root-private rollback snapshot before applying changes. Worker
accounts do not receive root, sudo, container-socket, or policy-administration
privileges. The GUI and helper are the supported control path; do not run this
module as an ad hoc account migration or use it to change a production host
outside the current owner's explicit scope.

The shared-home model does not isolate a worker from intentionally shared
executable project code. Filename-based privacy checks cannot guarantee
detection of every secret copy. See the top-level [SECURITY](../../docs/SECURITY.md)
contract and [validation requirements](../../docs/VALIDATION.md).
