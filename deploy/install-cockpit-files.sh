#!/bin/sh
set -eu

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
  echo "Cockpit Files $installed is already installed."
  exit 0
fi

simulation=$(apt-get -s -t "$suite" --no-install-recommends install "cockpit-files=$version")
if printf '%s\n' "$simulation" | grep -q '^Remv '; then
  echo "The package plan would remove existing software; refusing installation." >&2
  exit 1
fi
apt-get -y -t "$suite" --no-install-recommends install "cockpit-files=$version"
test -f /usr/share/cockpit/files/manifest.json || { echo "Cockpit Files installed without its expected package manifest." >&2; exit 1; }
echo "Installed Cockpit Files $version. Reload Cockpit to use the file browser."
