#!/bin/sh
# Real dpkg lifecycle confined to a disposable root; never touches host services/data.
set -eu
# Fixed synthetic build timestamp; the disposable source copy need not contain .git.
SOURCE_DATE_EPOCH=1700000000
export SOURCE_DATE_EPOCH
PATH=/usr/local/sbin:/usr/sbin:/sbin:$PATH
export PATH
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
[ "$(uname -s)" = Linux ] || { echo 'Linux required' >&2; exit 1; }
fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT HUP INT TERM
root="$fixture/root"
mkdir -p "$root/var/lib/dpkg" "$root/etc/systemd/system"
: > "$root/var/lib/dpkg/status"
mkdir -p "$root/usr/local/sbin"
printf '[Service]\nExecStart=/usr/bin/python3 /usr/local/libexec/h07p/dsh-dashboard-launcher.py\nEnvironment=FIXTURE=retained\n' > "$root/etc/systemd/system/h07p-dsh.service"
printf '[Service]\nExecStart=/home/huou07/.local/bin/opencode web --hostname 127.0.0.1 --port 4097\n' > "$root/etc/systemd/system/h07p-opencode.service"
printf '#!/bin/sh\n# synthetic legacy harness-worker\n' > "$root/usr/local/sbin/h07p-harness"
legacy_hash=$(sha256sum "$root/etc/systemd/system/h07p-dsh.service" "$root/etc/systemd/system/h07p-opencode.service" "$root/usr/local/sbin/h07p-harness")
# A harmless ELF verifies packaging mechanics; this is not real-service acceptance.
"$repo/tools/build-deb.sh" 0.0.1 /bin/true "$fixture/dist"
"$repo/tools/build-deb.sh" 0.0.1 /bin/true "$fixture/repeat"
cmp "$fixture/dist/huou07-playground_0.0.1_amd64.deb" "$fixture/repeat/huou07-playground_0.0.1_amd64.deb"
(cd "$fixture/dist" && sha256sum -c huou07-playground_0.0.1_amd64.deb.sha256)
"$repo/tools/build-deb.sh" 0.0.2 /bin/true "$fixture/dist"
dpkg_fixture() {
  dpkg --root="$root" --log="$fixture/dpkg.log" --force-script-chrootless --force-not-root --force-depends "$@"
}
dpkg_fixture --install "$fixture/dist/huou07-playground_0.0.1_amd64.deb"
[ ! -e "$root/etc/systemd/system/h07p-dsh.service" ]
grep -q '/opt/huou07-playground/current/bin/h07p-server worker' "$root/usr/local/sbin/h07p-harness"
[ "$(readlink "$root/opt/huou07-playground/current")" = '/opt/huou07-playground/releases/0.0.1' ]
printf 'synthetic apps\n' > "$root/var/lib/huou07-playground/apps.json"
printf 'synthetic auth policy\n' > "$root/var/lib/h07p-control/policy.db"
printf 'synthetic private bytes\n' > "$root/var/lib/h07p-private/nas/retained.txt"
state_hash=$(sha256sum "$root/var/lib/huou07-playground/apps.json" "$root/var/lib/h07p-control/policy.db" "$root/var/lib/h07p-private/nas/retained.txt")
dpkg_fixture --install "$fixture/dist/huou07-playground_0.0.2_amd64.deb"
[ "$(readlink "$root/opt/huou07-playground/current")" = '/opt/huou07-playground/releases/0.0.2' ]
[ "$state_hash" = "$(sha256sum "$root/var/lib/huou07-playground/apps.json" "$root/var/lib/h07p-control/policy.db" "$root/var/lib/h07p-private/nas/retained.txt")" ]
# A deliberately invalid installed release marker makes real dpkg postinst fail.
"$repo/tools/build-deb.sh" 0.0.3 /bin/true "$fixture/dist"
dpkg-deb --raw-extract "$fixture/dist/huou07-playground_0.0.3_amd64.deb" "$fixture/broken"
printf 'invalid/version\n' > "$fixture/broken/usr/lib/huou07-playground/version"
dpkg-deb --root-owner-group --build "$fixture/broken" "$fixture/dist/broken.deb"
if dpkg_fixture --install "$fixture/dist/broken.deb"; then
  echo 'Invalid upgrade unexpectedly configured successfully.' >&2
  exit 1
fi
case "$(readlink "$root/opt/huou07-playground/current")" in /opt/huou07-playground/releases/rollback-*) ;; *) exit 1;; esac
[ "$state_hash" = "$(sha256sum "$root/var/lib/huou07-playground/apps.json" "$root/var/lib/h07p-control/policy.db" "$root/var/lib/h07p-private/nas/retained.txt")" ]
printf 'failed migration\n' > "$root/var/lib/h07p-control/policy.db"
DPKG_ROOT="$root" python3 "$repo/deploy/package/lifecycle.py" rollback
case "$(readlink "$root/opt/huou07-playground/current")" in /opt/huou07-playground/releases/rollback-*) ;; *) exit 1;; esac
[ "$state_hash" = "$(sha256sum "$root/var/lib/huou07-playground/apps.json" "$root/var/lib/h07p-control/policy.db" "$root/var/lib/h07p-private/nas/retained.txt")" ]
dpkg_fixture --remove huou07-playground
[ "$legacy_hash" = "$(sha256sum "$root/etc/systemd/system/h07p-dsh.service" "$root/etc/systemd/system/h07p-opencode.service" "$root/usr/local/sbin/h07p-harness")" ]
[ "$state_hash" = "$(sha256sum "$root/var/lib/huou07-playground/apps.json" "$root/var/lib/h07p-control/policy.db" "$root/var/lib/h07p-private/nas/retained.txt")" ]
dpkg_fixture --purge huou07-playground
[ "$legacy_hash" = "$(sha256sum "$root/etc/systemd/system/h07p-dsh.service" "$root/etc/systemd/system/h07p-opencode.service" "$root/usr/local/sbin/h07p-harness")" ]
[ "$state_hash" = "$(sha256sum "$root/var/lib/huou07-playground/apps.json" "$root/var/lib/h07p-control/policy.db" "$root/var/lib/h07p-private/nas/retained.txt")" ]
echo 'PASS: repeat-build checksum, isolated dpkg install/upgrade/failed-upgrade automatic rollback/manual rollback/remove/purge retained synthetic state and original worker entry points; real server installation acceptance remains separate.'
