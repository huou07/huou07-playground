# Credential Guard P0 audit

Metadata-only audit of the actual Debian deployment. No authentication file,
log body, environment value, private key or process memory was read. Worker
permission probes ran after permanent UID/GID/group drops, not as root.

The running dashboard remains the prior Python release; integrated Rust/product
acceptance is separate. Actual identities, modes and kernel/service capabilities
are in compatibility-baseline.json. Effective DAC checks are in access-matrix.json.

Each native harness store is readable by its own executor UID. This is
UNRESOLVED_SAME_UID by design under the owner's earlier explicit instruction to
leave native authentication unchanged. It must not be reported as full isolation.
Cross-harness and owner boundaries are checked separately. Missing files and
unexercised debug/mandatory controls remain UNKNOWN. Effective DAC is not proof
that every mandatory policy or protocol endpoint has been exercised.

P0 permits implementation using the existing policy store/helper, while retaining
all prior denials. It does not authorize a new credential-holder architecture,
AppArmor rollout, provider changes, real model calls or log deletion.

The three directory-enumeration findings for `/etc/huou07-playground` are expected
public metadata access, not authentication-value access. Both specifically
inventoried private OpenCode environment files deny every worker. Do not lock the
whole configuration tree to hide public configuration names.
