#!/bin/sh
# Build an already-compiled Linux amd64 release; never builds or installs on the host.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version=${1:?Usage: tools/build-deb.sh VERSION [BINARY] [OUTPUT_DIR]}
binary=${2:-$repo/target/release/h07p-server}
out=${3:-$repo/dist}
case "$version" in *[!0-9A-Za-z.+~:-]*|'') echo 'Invalid Debian version' >&2; exit 2;; esac
dpkg --validate-version "$version"
case "$(file -b "$binary")" in *ELF*64-bit*x86-64*) ;; *) echo 'Expected Linux amd64 ELF binary' >&2; exit 2;; esac
glibc=$(objdump -T "$binary" | sed -n 's/.*(GLIBC_\([0-9.]*\)).*/\1/p' | sort -V | tail -n 1)
glibc=${glibc:-2.34}
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
release="$stage/opt/huou07-playground/releases/$version"
install -d "$release/bin" "$release/web" "$release/deploy" "$stage/DEBIAN" "$stage/usr/lib/systemd/system" "$stage/usr/lib/huou07-playground" "$stage/etc/huou07-playground"
install -m 0755 "$binary" "$release/bin/h07p-server"
cp -R "$repo/web/static" "$release/web/static"
for collector in power.py gpu.py wg_status.py; do install -m 0644 "$repo/deploy/$collector" "$release/deploy/$collector"; done
install -m 0644 "$repo/deploy/private-services.json" "$release/deploy/private-services.json"
install -m 0644 "$repo/deploy/package/gitleaks.toml" "$release/deploy/gitleaks.toml"
install -m 0644 "$repo/deploy/private-services.json" "$stage/etc/huou07-playground/private-services.json"
install -m 0644 "$repo/deploy/package/dashboard.env" "$stage/etc/huou07-playground/dashboard.env"
install -m 0644 "$repo/deploy/package/"*.service "$stage/usr/lib/systemd/system/"
install -m 0755 "$repo/deploy/package/lifecycle.py" "$stage/usr/lib/huou07-playground/lifecycle.py"
install -m 0755 "$repo/deploy/package/h07p-harness" "$stage/usr/lib/huou07-playground/h07p-harness"
printf '%s\n' "$version" > "$stage/usr/lib/huou07-playground/version"
for script in preinst postinst prerm postrm; do install -m 0755 "$repo/deploy/package/lifecycle.py" "$stage/DEBIAN/$script"; done
cat > "$stage/DEBIAN/control" <<CONTROL
Package: huou07-playground
Version: $version
Architecture: amd64
Maintainer: H07P owner <owner@localhost>
Pre-Depends: python3
Depends: libc6 (>= $glibc), libgcc-s1, libpam0g, adduser, systemd (>= 254), acl, gitleaks (>= 8.16)
Section: admin
Priority: optional
Description: H07P owner dashboard and protected helper
 Linux dashboard with retained owner state and private storage.
CONTROL
printf '/etc/huou07-playground/dashboard.env\n/etc/huou07-playground/private-services.json\n' > "$stage/DEBIAN/conffiles"
find "$stage" -type d -exec chmod 0755 {} +
find "$release" -type f ! -path '*/bin/*' -exec chmod 0644 {} +
mkdir -p "$out"
SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -C "$repo" show -s --format=%ct HEAD)}
export SOURCE_DATE_EPOCH
find "$stage" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
dpkg-deb --root-owner-group --build "$stage" "$out/huou07-playground_${version}_amd64.deb"
(cd "$out" && sha256sum "huou07-playground_${version}_amd64.deb" > "huou07-playground_${version}_amd64.deb.sha256")
