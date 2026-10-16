#!/bin/sh
# One bounded synthetic systemd unit. Never starts/stops the owner's native services.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run this synthetic systemd test as root.' >&2; exit 1; }
binary=$(realpath "${1:-target/release/h07p-server}")
fixture=$(mktemp -d /tmp/h07p-cgroup-fixture.XXXXXX)
unit="h07p-worker-fixture-$(date +%s%N)-$$.service"
cleanup() {
    systemctl stop "$unit" >/dev/null 2>&1 || true
    systemctl reset-failed "$unit" >/dev/null 2>&1 || true
    rm -rf "$fixture"
}
trap cleanup EXIT HUP INT TERM
mkdir -p "$fixture/usr" "$fixture/proc" "$fixture/dev" "$fixture/etc" "$fixture/tmp" "$fixture/var/lib/h07p-control" "$fixture/home/huou07/Projects" "$fixture/home/huou07/.local/bin" "$fixture/home/huou07/.dsh"
chmod 0755 "$fixture" "$fixture/home" "$fixture/home/huou07"
chmod 1777 "$fixture/tmp"
for directory in bin sbin lib lib64; do
    [ -L "/$directory" ] || { echo 'This fixture requires merged-/usr Debian.' >&2; exit 1; }
    ln -s "$(readlink "/$directory")" "$fixture/$directory"
done
printf 'root:x:0:0:root:/root:/bin/sh\ndsh-worker:x:65001:65001:fixture:/home/huou07:/bin/sh\n' > "$fixture/etc/passwd"
printf 'root:x:0:\ndsh-worker:x:65001:\n' > "$fixture/etc/group"
printf 'passwd: files\ngroup: files\n' > "$fixture/etc/nsswitch.conf"
printf '{"preset":"none","workspace":"/home/huou07/Projects","rules":[]}\n' > "$fixture/var/lib/h07p-control/policy.json"
chown 65001:65001 "$fixture/home/huou07/Projects" "$fixture/home/huou07/.dsh"
chmod 0700 "$fixture/home/huou07/.dsh"
cp "$binary" "$fixture/h07p-server"
cat > "$fixture/home/huou07/.local/bin/dsh" <<'PY'
#!/usr/bin/python3
import json
import os
from pathlib import Path
import subprocess
import time
child = subprocess.Popen(['/usr/bin/python3', '-c', 'import time; time.sleep(60)'])
status = Path('/proc/self/status').read_text()
assert os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 65001
assert os.getgroups() == [] and 'NoNewPrivs:\t1' in status
Path('/home/huou07/Projects/identity.json').write_text(json.dumps({'parent': os.getpid(), 'child': child.pid}))
time.sleep(60)
PY
chmod 0755 "$fixture/home/huou07/.local/bin/dsh"
systemd-run --quiet --collect --service-type=exec --unit="$unit" \
    --property="RootDirectory=$fixture" --property=MountAPIVFS=yes \
    --property=BindReadOnlyPaths=/usr --property=KillMode=control-group \
    --property=TimeoutStopSec=3s --property=NoNewPrivileges=yes \
    --property=PrivateTmp=yes --property=ProtectKernelTunables=yes --property=ProtectKernelModules=yes \
    --property=Group=root --property=LimitCORE=0 --property=AmbientCapabilities= \
    '--property=CapabilityBoundingSet=CAP_SETUID CAP_SETGID CAP_CHOWN CAP_DAC_OVERRIDE CAP_DAC_READ_SEARCH' \
    /h07p-server worker dsh fixture
attempt=0
while [ ! -s "$fixture/home/huou07/Projects/identity.json" ]; do
    attempt=$((attempt + 1))
    [ "$attempt" -le 50 ] || { echo 'Synthetic worker readiness failed.' >&2; exit 1; }
    sleep 0.1
done
python3 - "$fixture/home/huou07/Projects/identity.json" "$unit" <<'PY'
import json
from pathlib import Path
import sys
record = json.loads(Path(sys.argv[1]).read_text())
for pid in record.values():
    assert sys.argv[2] in Path(f'/proc/{pid}/cgroup').read_text()
PY
systemctl stop "$unit"
python3 - "$fixture/home/huou07/Projects/identity.json" <<'PY'
import json
from pathlib import Path
import sys
import time
record = json.loads(Path(sys.argv[1]).read_text())
for _ in range(30):
    living = []
    for pid in record.values():
        try:
            if Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z':
                living.append(pid)
        except FileNotFoundError:
            pass
    if not living:
        break
    time.sleep(0.1)
else:
    raise SystemExit('Synthetic cgroup descendant survived stop')
print('PASS: actual synthetic systemd cgroup contained native worker+descendant; stop terminated both (UID65001/groups empty/NNP).')
PY
