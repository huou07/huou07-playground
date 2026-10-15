# Security hardening — N2 (core dump) and N3 (same-UID memory access)

Patch set for the two worker-owned systemd units on the H07P host, plus the
host-wide ptrace scope. Prepared by an agent session for owner review; **not
applied** — the agent principal cannot and must not edit service units.

Measured on: `agent-workbench-dsh@3080.service` + `agent-workbench-opencode-web.service`,
Debian 13, kernel 7.2.6, systemd 257. Findings were re-measured in-session rather
than taken from earlier reports.

## Revision note — the first drop-in revision was defective

The first revision of `systemd/70-memory-exfil-hardening.conf` wrote
`SystemCallFilter=~ptrace ~process_vm_readv ~process_vm_writev ~pidfd_getfd ~kcmp`.
The tilde must appear **once**, marking the whole assignment as a deny-list.
systemd read `~process_vm_readv` as a syscall *name*, failed to resolve it, and
silently ignored it. The installed filter denied only `ptrace`:

```
$ systemctl show agent-workbench-dsh@3080.service -p SystemCallFilter --value
~ptrace syslog
$ systemd-analyze verify probe.service
System call ~process_vm_readv is not known, ignoring.
```

Nothing failed, the units stayed `active`, and `systemctl status` looked clean —
which is why the mistake survived installation. Corrected line:

```
SystemCallFilter=~ptrace process_vm_readv process_vm_writev pidfd_getfd kcmp
```

`apply.sh` now parses the line with `systemd-analyze verify` **before**
installing and refuses on any ignored entry, and its post-apply check asserts
every intended syscall is present in the effective value. Re-run it to replace
an already-installed defective revision.

Mitigating context: `kernel.yama.ptrace_scope=1` gates `ptrace`,
`process_vm_readv`, `process_vm_writev`, `pidfd_getfd` and `kcmp` through the same
ptrace access check, and it was applied. A process that is not an ancestor of the
target is therefore denied. N3 was largely closed by the sysctl even while the
filter was wrong; the filter is defence in depth.

## What is actually broken

| ID | Finding | Severity | Status |
| --- | --- | --- | --- |
| N1 | `.dsh/.credentials.yaml`, `.codex/auth.json`, `.opencode/data/opencode/auth.json` are all mode 600 owned by `agents-worker` — the same UID that runs untrusted agent commands. Readable and writable by any agent process. | Critical | **Not fixed by this patch** — structural, see Phase 1 |
| N2 | Both units run `LimitCORE=infinity`, and `core_pattern` is the bare `core`. A crash of the credential-holding process writes its full memory image into `/home/agents-worker/.agent-workbench-runtime-v6`, which the agent can read. | Critical | **Fixed here** |
| N3 | `kernel.yama.ptrace_scope=0`, and `/proc/<pid>/mem` + `/proc/<pid>/environ` are readable for every UID-987 process. Same UID implies memory access, so moving the credential file to root does not stop extraction from RAM. | High | **Partially fixed here** (seccomp + sysctl) |

### Why no DSH file policy can fix N1

The tempting fix is "stop using `danger-full-access`". That does not work. The
Landlock ruleset the sandbox builds for **every** mode is:

```js
// @deepseek-ai/dsh-sandbox-local/lib/index.js:45
function landlockProfileArgs(policy) {
    const readWrite = ["/dev/null"];
    if (policy.mode === "workspace-write") readWrite.push("/tmp", policy.workspaceRoot);
    return grantArgs({ readOnly: ["/"], readWrite });
}
```

`readOnly: ["/"]` grants read access to the entire filesystem. The first rung on
Linux, bubblewrap, agrees:

```js
// @deepseek-ai/dsh-sandbox-local/lib/index.js:23
"--ro-bind", "/", "/", "--dev", "/dev", "--unshare-pid", "--proc", "/proc", "--die-with-parent"
```

`workspace-write` and `read-only` both restrict **writes only**. The sandbox is
write-confining, not read-confining, so no configuration value protects the
credential store from being read. `danger-full-access` removes the write
restriction; it does not create the read exposure. Treat the policy as write
protection only.

One real protection does come from the sandbox, and `danger-full-access` removes
it: bubblewrap adds `--unshare-pid` with a fresh `--proc`, so a sandboxed command
cannot see any other process, which blocks same-UID `ptrace` from inside the
sandbox. But `--ro-bind / /` still exposes the credential file by path, so this
does not help N1. Conclusion: keep the policy at `workspace-write` for the PID
isolation, and do not expect it to hide credentials.

## What this patch does and does not do

Fixed:

- N2 completely — `LimitCORE=0` stops the core-dump path for the whole tree.
- N3 for the units' own process trees — seccomp denies `ptrace`,
  `process_vm_readv`, `process_vm_writev`, `pidfd_getfd`, `kcmp`. Seccomp
  filters are inherited and cannot be dropped by an unprivileged child. This
  covers both sandboxed and unsandboxed commands; the bubblewrap PID namespace
  only protects the former, and `danger-full-access` removes the latter.
- N3 host-wide for sibling processes — `ptrace_scope=1`.

Not fixed:

- N1. Same-UID read of the credential files is a DAC fact. No file mode, ACL or
  unit setting changes it while the credential holder and the command executor
  share UID 987.
- Retroactive confidentiality. If a key was read before, it must be considered
  disclosed. See the rotation checklist.

## Apply

```bash
cd deploy/security-hardening
chmod +x apply.sh
./apply.sh                  # dry run, changes nothing
sudo ./apply.sh --apply --i-understand-this-restarts-dsh
sudo ./apply.sh --rollback  # undo
```

The acknowledgement flag is required because restarting
`agent-workbench-dsh@3080.service` terminates the DSH session. `apply.sh`
verifies unit state, `LimitCORE=0`, `ptrace_scope=1` and `HTTP 302` on
`127.0.0.1:3080`, and rolls back automatically if verification fails. Backups
land in `/var/backups/h07p-security-hardening/`.

Before trusting the seccomp line on the owner host, validate it in the
disposable Debian guest: the codex-acp path uses rootless bubblewrap, and the
`40-codex-acp-sandbox.conf` drop-in already disables `ProtectKernelTunables`,
`ProtectKernelLogs` and `RestrictSUIDSGID` for that reason. Bubblewrap is not
expected to need the denied syscalls, but that is an expectation, not a
measurement. If nested bubblewrap breaks, drop the `SystemCallFilter` line and
keep `LimitCORE=0` plus the sysctl.

## Phase 1 — the only real fix for N1

The credential holder and the command executor must not share a UID. The host is
already partway there: `huou07-dsh` (UID 992) owns `/var/lib/huou07-dsh`, which
is mode 700 and was measured inaccessible to `agents-worker`.

Design: a scoped model-API broker running as `huou07-dsh`, holding the
credentials, listening on a Unix socket. DSH points its provider base URL at
that broker using its `peerCred` for authentication. The agent sends prompts and
receives completions; it never receives the key and never needs the store.
`agents-worker` then loses read access to all three credential files.

This follows `docs/SECURITY.md`: *"Same-UID workers require process/control-socket
isolation"* and *"Never introduce a generic sudo executor."* A broker that
performs one class of privileged action is the intended shape; a general
privilege bridge is not.

Ordering constraint: the broker only helps once N2 and N3 are closed. Without
them, a same-UID process can still extract the key from broker memory or a
broker core dump.

## Credential rotation checklist (do this first)

Rotating at the provider is the only action that undoes the historical
disclosure. Deleting local files does not revoke anything.

1. Revoke/rotate at the provider for each credential in the three stores.
2. Only then replace them locally; do not print them to a terminal — scrollback,
   `~/.bash_history` and logs turn one read into another disclosure. Prefix the
   command with a space under `HISTCONTROL=ignorespace`.
3. Restart the units so the new credentials are loaded.
4. Re-run this patch's verification, then confirm the core-dump path is closed
   before trusting the new keys to the same host.

## Related findings not covered here

- `agent-workbench-opencode-web.service` declares no `CapabilityBoundingSet=`
  (40 caps in the bounding set) while the DSH unit sets it empty. Effective
  `CapEff` is `0` for both, and `NoNewPrivileges=yes` prevents gaining
  privileges, so this is a latent defense-in-depth gap rather than an active
  hole. Set it empty for consistency.
- `/var/run/libvirt/libvirt-sock` is mode `666` and `libvirtd` is active; a
  non-root connect succeeds. Whether privileged libvirt operations are reachable
  depends on polkit, which could not be read without root. **Unverified** —
  audit as root, and narrow the socket to `root:libvirt 660`.
- `agents-worker` is in the `agent-skills` group, and
  `/srv/agent-workbench/skills` plus `/srv/agent-workbench/AGENTS.md` are
  worker-writable. The principal governed by the policy can rewrite it. Make the
  canonical policy `root:root 644` and keep worker-writable skill space separate.
- `/home/huou07` carries `user:agents-worker:r-x` **and** a `default:` entry, so
  new files inherit agent readability. Scope the ACL to `/home/huou07/Projects`
  and drop the `default:` entry at the home root.
- **Landmine:** `deploy/user/dsh.service` and `deploy/user/opencode-web.service`
  in this repository run with `%h` = `/home/huou07`, i.e. as **owner `huou07`**.
  If either is ever enabled, the worker runs with the owner's identity and the
  whole home directory. Verify they are not installed in
  `~/.config/systemd/user/` and consider deleting them.
- Detection is absent: `auditd` is inactive and `auditctl` is not installed, so
  a credential read leaves no trace. That is why an earlier read went unnoticed
  for hours. Installing `auditd` with a read watch on the three credential paths
  would give forensic evidence; that is an owner install decision.
