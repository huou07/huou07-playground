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
SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -C "$repo" show -s --format=%ct HEAD)}
export SOURCE_DATE_EPOCH
audit_dir=${H07P_RELEASE_AUDIT_DIR:-$repo/artifacts/release-audit}
if [ "${H07P_PACKAGE_FIXTURE:-0}" != 1 ] && { [ ! -f "$audit_dir/THIRD_PARTY_LICENSES.txt" ] || [ ! -f "$audit_dir/sbom.cdx.json" ]; }; then
  echo 'Generate release audit artifacts first (or set H07P_RELEASE_AUDIT_DIR).' >&2
  exit 2
fi
if [ "${H07P_PACKAGE_FIXTURE:-0}" != 1 ]; then
  python3 - "$audit_dir/report.json" "$repo/Cargo.lock" <<'PY'
import hashlib, json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert report.get('status') == 'pass', 'Release audit is incomplete or failed'
assert report.get('lockfile_sha256') == hashlib.sha256(pathlib.Path(sys.argv[2]).read_bytes()).hexdigest(), 'Release audit does not match Cargo.lock'
PY
fi
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
release="$stage/opt/huou07-playground/releases/$version"
install -d "$release/bin" "$release/web" "$release/deploy" "$stage/DEBIAN" "$stage/usr/lib/systemd/system" "$stage/usr/lib/huou07-playground" "$stage/etc/huou07-playground"
install -m 0755 "$binary" "$release/bin/h07p-server"
strip --strip-unneeded "$release/bin/h07p-server"
cp -R "$repo/web/static" "$release/web/static"
find "$release/web/static" -type f \( -name '._*' -o -name '.DS_Store' \) -delete
for collector in power.py gpu.py wg_status.py; do install -m 0755 "$repo/deploy/$collector" "$release/deploy/$collector"; done
install -m 0644 "$repo/deploy/private-services.json" "$release/deploy/private-services.json"
install -m 0644 "$repo/deploy/package/gitleaks.toml" "$release/deploy/gitleaks.toml"
install -m 0644 "$repo/deploy/private-services.json" "$stage/etc/huou07-playground/private-services.json"
install -m 0644 "$repo/deploy/package/dashboard.env" "$stage/etc/huou07-playground/dashboard.env"
install -m 0644 "$repo/deploy/package/"*.service "$stage/usr/lib/systemd/system/"
install -m 0755 "$repo/deploy/package/lifecycle.py" "$stage/usr/lib/huou07-playground/lifecycle.py"
install -d "$stage/usr/sbin" "$stage/usr/share/applications"
install -m 0755 "$repo/deploy/package/setup.py" "$stage/usr/lib/huou07-playground/setup.py"
install -m 0755 "$repo/deploy/package/h07p-setup" "$stage/usr/sbin/h07p-setup"
install -m 0644 "$repo/deploy/package/h07p-setup.desktop" "$stage/usr/share/applications/h07p-setup.desktop"
install -m 0755 "$repo/deploy/package/h07p-harness" "$stage/usr/lib/huou07-playground/h07p-harness"
printf '%s\n' "$version" > "$stage/usr/lib/huou07-playground/version"
chmod 0644 "$stage/usr/lib/huou07-playground/version"
for script in preinst postinst prerm; do
  {
    printf '#!/bin/sh\nset -eu\nH07P_MAINT_SCRIPT=%s\nexport H07P_MAINT_SCRIPT\n' "$script"
    if [ "$script" = preinst ]; then
      printf 'exec /usr/bin/python3 - "$@" <<\047H07P_PACKAGE_PY\047\n'
      cat "$repo/deploy/package/lifecycle.py"
      printf '\nH07P_PACKAGE_PY\n'
    else
      printf 'exec /usr/bin/python3 "${DPKG_ROOT:-}/usr/lib/huou07-playground/lifecycle.py" "$@"\n'
    fi
  } > "$stage/DEBIAN/$script"
  chmod 0755 "$stage/DEBIAN/$script"
done
install -m 0755 "$repo/deploy/package/postrm" "$stage/DEBIAN/postrm"
doc="$stage/usr/share/doc/huou07-playground"
install -d "$doc" "$stage/usr/share/lintian/overrides"
{
  printf 'H07P owner dashboard\nCopyright: H07P contributors\nLicense: GPL-3 (repository LICENSE)\nThe complete GPL version 3 is in /usr/share/common-licenses/GPL-3.\n\nBundled Rust dependency copyright/license notices are in third-party-notices.gz.\n\n'
  if [ -f "$repo/web/static/branding.LICENSE" ]; then cat "$repo/web/static/branding.LICENSE"; fi
  printf '\nThe complete Apache License version 2.0 is in /usr/share/common-licenses/Apache-2.0.\n'
} > "$doc/copyright"
chmod 0644 "$doc/copyright"
if [ -f "$audit_dir/THIRD_PARTY_LICENSES.txt" ]; then gzip -n -9 -c "$audit_dir/THIRD_PARTY_LICENSES.txt" > "$doc/third-party-notices.gz"; fi
if [ -f "$audit_dir/sbom.cdx.json" ]; then install -m 0644 "$audit_dir/sbom.cdx.json" "$doc/sbom.cdx.json"; fi
printf 'huou07-playground (%s) unstable; urgency=medium\n\n  * Versioned Linux dashboard and managed worker policy launcher.\n\n -- H07P maintainers <huou07@users.noreply.github.com>  %s\n' "$version" "$(date -u -d "@$SOURCE_DATE_EPOCH" -R)" | gzip -n -9 > "$doc/changelog.gz"
printf '# Owner-distributed application intentionally retains its requested versioned /opt layout.\nhuou07-playground: dir-or-file-in-opt [opt/huou07-playground/*]\n' > "$stage/usr/share/lintian/overrides/huou07-playground"
chmod 0644 "$doc/"* "$stage/usr/share/lintian/overrides/huou07-playground"
cat > "$stage/DEBIAN/control" <<CONTROL
Package: huou07-playground
Version: $version
Architecture: amd64
Maintainer: H07P maintainers <huou07@users.noreply.github.com>
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
chmod 0755 "$release/deploy/"*.py
mkdir -p "$out"
find "$stage" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
dpkg-deb --root-owner-group --build "$stage" "$out/huou07-playground_${version}_amd64.deb"
(cd "$out" && sha256sum "huou07-playground_${version}_amd64.deb" > "huou07-playground_${version}_amd64.deb.sha256")

install -m 0755 "$repo/tools/h07p-install.sh" "$out/h07p-install.sh"
