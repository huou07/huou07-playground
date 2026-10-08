#!/bin/sh
set -eu

SERVICE=cockpit.socket
OVERRIDE=/etc/systemd/system/cockpit.socket.d/listen.conf

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root (for example: sudo ./deploy/install-cockpit.sh)." >&2
  exit 1
fi
if ! command -v systemctl >/dev/null 2>&1 || [ ! -d /run/systemd/system ]; then
  echo "A running systemd installation is required." >&2
  exit 1
fi
. /etc/os-release
if [ "${ID:-}" != debian ] || [ "${VERSION_ID:-}" != 13 ]; then
  echo "This installer supports Debian 13 with its backports repository enabled." >&2
  exit 1
fi

suite="${VERSION_CODENAME}-backports"
version=$(apt-cache madison cockpit | awk -F '|' -v suite="$suite" 'index($3, suite) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit }')
if [ -z "$version" ] || ! dpkg --compare-versions "$version" ge 368; then
  echo "Cockpit 368 or newer was not found in $suite; refusing an older package." >&2
  exit 1
fi

if dpkg-query -W -f='${Status}' cockpit 2>/dev/null | grep -q 'install ok installed'; then
  installed=$(dpkg-query -W -f='${Version}' cockpit)
  if ! dpkg --compare-versions "$installed" ge 368 || ! grep -Fxq 'ListenStream=127.0.0.1:9090' "$OVERRIDE" 2>/dev/null; then
    echo "Cockpit is already installed with a different version or socket configuration; review it manually." >&2
    exit 1
  fi
  systemctl daemon-reload
  systemctl unmask --runtime "$SERVICE"
  systemctl enable --now "$SERVICE"
  listeners=$(ss -ltnH '( sport = :9090 )' | awk '{print $4}')
  [ "$listeners" = "127.0.0.1:9090" ] || { echo "Cockpit is not bound to loopback only." >&2; exit 1; }
  echo "Cockpit $installed is already configured for loopback access."
  exit 0
fi

simulation=$(apt-get -s -t "$suite" install --no-install-recommends "cockpit=$version")
if printf '%s\n' "$simulation" | grep -q '^Remv '; then
  echo "The package plan would remove existing software; refusing installation." >&2
  exit 1
fi
if ss -ltnH '( sport = :9090 )' | grep -q .; then
  echo "Port 9090 is already in use; refusing installation." >&2
  exit 1
fi
if [ -d "$(dirname "$OVERRIDE")" ] && [ ! -e "$OVERRIDE" ]; then
  echo "A different Cockpit socket drop-in already exists; review it manually." >&2
  exit 1
fi
if [ -e "$OVERRIDE" ] && ! grep -Fxq 'ListenStream=127.0.0.1:9090' "$OVERRIDE"; then
  echo "A different Cockpit socket override already exists; refusing to replace it." >&2
  exit 1
fi

failed=1
cleanup() {
  if [ "$failed" -eq 1 ]; then
    systemctl stop "$SERVICE" >/dev/null 2>&1 || true
    systemctl disable "$SERVICE" >/dev/null 2>&1 || true
    systemctl mask --runtime "$SERVICE" >/dev/null 2>&1 || true
    systemctl daemon-reload >/dev/null 2>&1 || true
    echo "Installation did not finish; Cockpit remains stopped and masked. Rerun this script to continue." >&2
  fi
}
trap cleanup EXIT HUP INT TERM
systemctl mask --runtime "$SERVICE"
install -d -o root -g root -m 0755 "$(dirname "$OVERRIDE")"
if [ ! -e "$OVERRIDE" ]; then
  cat > "$OVERRIDE" <<'EOF'
[Socket]
ListenStream=
ListenStream=127.0.0.1:9090
EOF
fi
chmod 0644 "$OVERRIDE"
apt-get -y -t "$suite" --no-install-recommends install "cockpit=$version"
systemctl daemon-reload
systemctl unmask --runtime "$SERVICE"
systemctl enable --now "$SERVICE"
systemctl is-active --quiet "$SERVICE"
listeners=$(ss -ltnH '( sport = :9090 )' | awk '{print $4}')
[ "$listeners" = "127.0.0.1:9090" ]
failed=0
trap - EXIT HUP INT TERM
echo "Installed Cockpit $version on 127.0.0.1:9090."
