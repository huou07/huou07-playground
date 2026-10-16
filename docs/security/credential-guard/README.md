# Credential Guard and log cleanup

Open **Permissions → Credential Guard** after owner sign-in. Guard reports
`PARTIAL`: the owner's requested own-harness credential access is preserved.
Native authentication files, provider settings and ACP transport are unchanged.

Register existing owner-owned log export folders under `/home/huou07/Projects`.
Metadata monitoring and content scanning are separate opt-ins. Monitoring uses a
single bounded inotify instance (512 directories, depth eight, 10,000 metadata
entries per inventory, 512 pending paths). Credential root watches inspect
metadata only. Closed registered exports may be scanned with the maintained
Gitleaks subprocess running as the owner. No matching contents enter incidents.
Unknown/unreadable files are not declared safe. New-file detection is reactive;
it cannot prevent a worker reading a new secret copy in an already shared folder.

For cleanup, enter a closed `.log`, `.jsonl`, `.out`, `.err` or `.txt` export,
choose **Preview log cleanup**, review the counts, check confirmation and apply.
Only UTF-8, single-link, owner-owned regular files up to 1 MiB are accepted.
Aliases, protected stores and files open for writing are rejected. The five-minute
single-use preview binds the file identity, ctime, policy and Guard revision.
Recognized secret-bearing lines and private-key blocks are masked; if Gitleaks
still detects signatures in the result, the entire export is suppressed. Scanner
failure prevents cleanup. No scanner proves absence of unknown secrets.

Original bytes are fsynced into root-private
`/var/lib/h07p-control/guard-quarantine` before atomic replacement. The cleaned
export becomes owner-only (0600). Interrupted/ENOSPC replacement retains the
original; incomplete recovery manifests remain visible. **Restore original to
private NAS** writes a new private NAS file and retains the root backup. It never
re-exposes the original in its shared location. Backups are not automatically
deleted. Live journald files, active logs, databases and authentication stores
are never rewritten or vacuumed by this feature.

Managed DSH/OpenCode web stdout/stderr pass through bounded line redaction before
systemd receives them. Interactive CLI terminal behavior stays unchanged. The
filter handles recognized headers, key assignments, token prefixes, URL userinfo,
private-key blocks and oversized/binary lines; it is not a general secret oracle.
An oversized line conservatively suppresses following output until a recognized
private-key end marker, so some diagnostics can be lost. Native apps writing
directly to other files are outside this source filter. Existing journal entries
remain unchanged. Managed service core dumps are disabled with `LimitCORE=0`.

Watcher gaps/overflow produce a degraded incident requiring an explicit scope
review/Auto Detect scan and acknowledgment. Acknowledging records an owner
decision, not proof of a complete scan. Missing protected roots or directory
budgets keep the watcher degraded. Turning detection off does not alter ACLs,
Landlock, root-private backups or native authentication.

`tests/native/guard.py` exercises real helper/inotify/UID behavior with synthetic
exports. `tests/package-sandbox.sh` also exercises web source redaction after
permanent UID drop. Playwright CLI exercised mobile settings, preview,
confirmation, cleanup, private restore and logout against real Rust/PAM.
The proposal's fanotify, global MAC, memory/swap scanning and performance targets
are not implemented or claimed. See [integration decisions](INTEGRATION.md).
