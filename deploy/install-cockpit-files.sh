#!/bin/sh
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MOVE_PACKAGE=$SOURCE/deploy/cockpit/huou07-move-files

install_move_package() {
  if [ ! -f "$MOVE_PACKAGE/manifest.json" ] || [ ! -f "$MOVE_PACKAGE/move" ] || [ ! -f "$MOVE_PACKAGE/list" ]; then
    echo "The Cockpit Move files are missing from this checkout." >&2
    exit 1
  fi
  install -d -o root -g root -m 0755 /usr/share/cockpit/huou07-move-files /usr/libexec
  install -o root -g root -m 0644 "$MOVE_PACKAGE/index.html" "$MOVE_PACKAGE/index.js" "$MOVE_PACKAGE/style.css" /usr/share/cockpit/huou07-move-files/
  install -o root -g root -m 0755 "$MOVE_PACKAGE/move" /usr/libexec/huou07-move-files
  install -o root -g root -m 0755 "$MOVE_PACKAGE/list" /usr/libexec/huou07-list-files
  install -o root -g root -m 0644 "$MOVE_PACKAGE/manifest.json" /usr/share/cockpit/huou07-move-files/manifest.json
}

register_file_manager() {
  registry=/var/lib/huou07-playground/apps.json
  if [ -f "$registry" ] && [ ! -L "$registry" ]; then
    APPS_FILE=$registry python3 "$SOURCE/deploy/register_app.py" \
      --name "Cockpit Files" \
      --url http://127.0.0.1:9090/system/files \
      --category Files \
      --description "Browse, edit, upload, download, and manage files." \
      --health-url http://127.0.0.1:9090/ \
      --management-url http://127.0.0.1:9090/system/files \
      --migrate-url-from http://127.0.0.1:9090/
  fi
}

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root (for example: sudo ./deploy/install-cockpit-files.sh)." >&2
  exit 1
fi
. /etc/os-release
if [ "${ID:-}" != debian ] || [ "${VERSION_ID:-}" != 13 ]; then
  echo "This installer supports Debian 13 with its backports repository enabled." >&2
  exit 1
fi

suite="${VERSION_CODENAME}-backports"
version=$(apt-cache madison cockpit-files | awk -F '|' -v suite="$suite" 'index($3, suite) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit }')
if [ -z "$version" ]; then
  echo "Cockpit Files was not found in $suite; enable Debian backports first." >&2
  exit 1
fi

if dpkg-query -W -f='${Status}' cockpit-files 2>/dev/null | grep -q 'install ok installed'; then
  installed=$(dpkg-query -W -f='${Version}' cockpit-files)
  test -f /usr/share/cockpit/files/manifest.json || { echo "Cockpit Files is installed without its expected package manifest." >&2; exit 1; }
  install_move_package
  register_file_manager
  echo "Cockpit Files $installed is installed; Move files support is available."
  exit 0
fi

simulation=$(apt-get -s -t "$suite" --no-install-recommends install "cockpit-files=$version")
if printf '%s\n' "$simulation" | grep -q '^Remv '; then
  echo "The package plan would remove existing software; refusing installation." >&2
  exit 1
fi
apt-get -y -t "$suite" --no-install-recommends install "cockpit-files=$version"
test -f /usr/share/cockpit/files/manifest.json || { echo "Cockpit Files installed without its expected package manifest." >&2; exit 1; }
install_move_package
register_file_manager
echo "Installed Cockpit Files $version and Move files support. Reload Cockpit to use the file browser."
