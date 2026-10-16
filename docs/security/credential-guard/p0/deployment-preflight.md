# Deployment preflight

- P0 metadata/access probes executed without changing services or credential files.
- Preserve the current worker accounts, shared applications and native login.
- Keep owner/private/native peer denials even when detection is disabled.
- Reuse the existing policy store, transaction lock, owner API and rollback.
- Add no global AppArmor restriction without compatibility evidence.
- Watch only configured paths; do not scan original authentication stores.
- Log handling must produce metadata-only reports, with explicit scope and review.
- Do not edit live journals/databases or silently delete forensic records.
- Installer must simulate dependency changes and preserve prior units/data.
- Deployment still requires the integrated native/package gates to pass.
