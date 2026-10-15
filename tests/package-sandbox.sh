#!/bin/sh
# Actual kernel/UID checks inside a disposable mount namespace and synthetic chroot.
set -eu
if [ "${1:-}" != --inside ]; then
    [ "$(id -u)" = 0 ] || { echo 'Run this synthetic namespace test as root.' >&2; exit 1; }
    binary=$(realpath "${1:-target/release/h07p-server}")
    wrapper=$(realpath "$(dirname "$0")/../deploy/package/h07p-harness")
    fixture=$(mktemp -d /tmp/h07p-sandbox-fixture.XXXXXX)
    trap 'rm -rf "$fixture"' EXIT HUP INT TERM
    unshare --mount --fork "$0" --inside "$binary" "$fixture" "$wrapper"
    exit
fi
binary=$2
fixture=$3
wrapper=$4
mount --make-rprivate /
mkdir -p "$fixture/usr" "$fixture/proc" "$fixture/dev" "$fixture/etc" "$fixture/tmp" "$fixture/run" "$fixture/outside" "$fixture/var/lib/h07p-control" "$fixture/home/huou07/Projects" "$fixture/home/huou07/.local/bin" "$fixture/home/huou07/.dsh" "$fixture/home/huou07/.codex"
mount --bind /usr "$fixture/usr"
mount -o remount,bind,ro "$fixture/usr"
for directory in bin sbin lib lib64; do
    if [ -L "/$directory" ]; then
        ln -s "$(readlink "/$directory")" "$fixture/$directory"
    else
        mkdir "$fixture/$directory"
        mount --bind "/$directory" "$fixture/$directory"
        mount -o remount,bind,ro "$fixture/$directory"
    fi
done
mount -t proc proc "$fixture/proc"
mount -t tmpfs -o mode=0755 tmpfs "$fixture/dev"
mknod -m 666 "$fixture/dev/null" c 1 3
mknod -m 666 "$fixture/dev/urandom" c 1 9
mknod -m 666 "$fixture/dev/random" c 1 8
printf 'root:x:0:0:root:/root:/bin/sh\ndsh-worker:x:65001:65001:fixture:/home/huou07:/bin/sh\ncodex-worker:x:65002:65002:fixture:/home/huou07:/bin/sh\n' > "$fixture/etc/passwd"
printf 'root:x:0:\ndsh-worker:x:65001:\ncodex-worker:x:65002:\n' > "$fixture/etc/group"
printf 'passwd: files\ngroup: files\n' > "$fixture/etc/nsswitch.conf"
printf '127.0.0.1 localhost\n' > "$fixture/etc/hosts"
[ ! -f /etc/ld.so.cache ] || cp /etc/ld.so.cache "$fixture/etc/ld.so.cache"
cp "$binary" "$fixture/h07p-server"
mkdir -p "$fixture/opt/huou07-playground/current/bin"
ln "$fixture/h07p-server" "$fixture/opt/huou07-playground/current/bin/h07p-server"
chmod 0755 "$fixture" "$fixture/home" "$fixture/home/huou07" "$fixture/tmp"
chown 65001:65001 "$fixture/home/huou07/Projects" "$fixture/home/huou07/.dsh"
chown 65002:65002 "$fixture/home/huou07/.codex"
chmod 0700 "$fixture/home/huou07/.codex"
# Deliberately use production-style named owner ACL grants, not a misleading 0700-only fixture.
setfacl -m u:65002:---,u:65003:rwx,m::rwx,g::---,o::--- "$fixture/home/huou07/.dsh"
printf 'synthetic outside\n' > "$fixture/outside/secret"
printf 'synthetic peer\n' > "$fixture/home/huou07/.codex/private"
printf 'synthetic root descriptor\n' > "$fixture/inherited"
ln -s /outside/secret "$fixture/home/huou07/Projects/escape"
cat > "$fixture/home/huou07/.local/bin/dsh" <<'PY'
#!/usr/bin/python3
import errno
import os
from pathlib import Path
import subprocess
import sys

strict = sys.argv[1] in ('strict', 'balance')
status = Path('/proc/self/status').read_text()
for key in ('Uid:', 'Gid:'):
    values = next(line.split()[1:] for line in status.splitlines() if line.startswith(key))
    assert values == ['65001'] * 4, (key, values)
assert next(line.split()[1:] for line in status.splitlines() if line.startswith('Groups:')) == []
assert 'NoNewPrivs:\t1' in status
try:
    os.fstat(9)
except OSError as error:
    assert error.errno == errno.EBADF
else:
    raise AssertionError('root inherited descriptor survived')
assert os.environ.get('H07P_FIXTURE_SECRET') is None
assert os.environ['HOME'] == '/home/huou07'
assert os.environ['TMPDIR'] == '/tmp/h07p-65001'
assert Path.cwd() == Path('/home/huou07/Projects')
with open('/opt/huou07-playground/current/bin/h07p-server', 'rb') as broker:
    assert broker.read(4) == b'\x7fELF'
for directory in ('/home/huou07/Projects', '/home/huou07/.dsh', os.environ['TMPDIR']):
    target = Path(directory) / 'positive'
    target.write_text('synthetic allowed')
    assert target.read_text() == 'synthetic allowed'
    target.unlink()
for target in ('/outside/secret', '/home/huou07/Projects/escape'):
    try:
        Path(target).read_bytes()
    except PermissionError:
        assert strict
    else:
        assert not strict
try:
    Path('/home/huou07/.codex/private').read_bytes()
except PermissionError:
    pass
else:
    raise AssertionError('peer store was readable')
if strict:
    try:
        os.listdir('/outside')
    except PermissionError:
        pass
    else:
        raise AssertionError('outside listing was allowed')
    code = 'from pathlib import Path; Path("/outside/secret").read_bytes()'
    child = subprocess.run(['/usr/bin/python3', '-c', code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert child.returncode != 0
print('PASS: synthetic ' + sys.argv[1] + ' real UID/groups/NNP/FD/native/workspace/peer/descendant boundaries')
PY
chmod 0755 "$fixture/home/huou07/.local/bin/dsh"
for preset in none minimal strict balance; do
    printf '{"preset":"%s","workspace":"/home/huou07/Projects","rules":[]}\n' "$preset" > "$fixture/var/lib/h07p-control/policy.json"
    H07P_FIXTURE_SECRET=must-not-survive chroot "$fixture" /h07p-server worker dsh "$preset" 9< "$fixture/inherited"
done
# Invalid root policy must fail before native execution; no silent permissive fallback.
printf '{"preset":"typo","workspace":"/home/huou07/Projects"}\n' > "$fixture/var/lib/h07p-control/policy.json"
if chroot "$fixture" /h07p-server worker dsh none >/dev/null 2>&1; then
    echo 'Invalid policy unexpectedly launched a native worker.' >&2
    exit 1
fi
echo 'PASS: invalid policy fails closed; all fixtures synthetic; no native login or model invocation.'
cp "$wrapper" "$fixture/h07p-harness"
chmod 0755 "$fixture/h07p-harness"
cat > "$fixture/fake-systemd-run" <<'PY'
#!/usr/bin/python3
import os
import sys
args = sys.argv[1:]
assert '--wait' in args and '--collect' in args and '--expand-environment=no' in args
assert '--property=KillMode=control-group' in args
assert '--property=NoNewPrivileges=yes' in args
assert any(value.startswith('--unit=h07p-worker-dsh-') for value in args)
assert '--working-directory=/home/huou07/Projects' in args
assert ('--pty' in args) == (os.isatty(0) and os.isatty(1))
assert ('--pipe' in args) != ('--pty' in args)
assert args[-6:] == ['/opt/huou07-playground/current/bin/h07p-server', 'worker', 'dsh', 'fixture', 'literal$VALUE', 'arg with spaces']
print('PASS: owner CLI revocable cgroup arguments and ' + ('PTY' if '--pty' in args else 'pipe') + ' transport')
PY
chmod 0755 "$fixture/fake-systemd-run"
# Replace only this namespace's read-only runtime bind; no host binary is changed.
mount --bind "$fixture/fake-systemd-run" "$fixture/usr/bin/systemd-run"
chroot "$fixture" /h07p-harness dsh fixture 'literal$VALUE' 'arg with spaces'
script --return --quiet --command "chroot '$fixture' /h07p-harness dsh fixture 'literal\$VALUE' 'arg with spaces'" /dev/null
