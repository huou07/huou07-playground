#!/bin/sh
set -eu

STATE_FILE=/etc/huou07-playground/wg-udp-access.rules
UFW=/usr/sbin/ufw
COMMENT="huou07 WireGuard endpoint"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root." >&2
  exit 1
fi
if [ ! -e "$STATE_FILE" ]; then
  echo "No huou07-managed WireGuard UDP rule is recorded."
  exit 0
fi
if [ -L "$STATE_FILE" ] || [ ! -f "$STATE_FILE" ] || [ ! -x "$UFW" ]; then
  echo "The WireGuard UDP state or UFW is invalid; refusing firewall changes." >&2
  exit 1
fi

while read -r interface port extra; do
  [ -n "${interface:-}" ] || continue
  case "$interface" in *[!A-Za-z0-9_.:-]*) echo "Invalid interface in WireGuard UDP state; refusing firewall changes." >&2; exit 1 ;; esac
  case "$port" in ''|*[!0-9]*) echo "Invalid port in WireGuard UDP state; refusing firewall changes." >&2; exit 1 ;; esac
  [ "$port" -ge 1 ] && [ "$port" -le 65535 ] && [ -z "${extra:-}" ] || { echo "Invalid WireGuard UDP state; refusing firewall changes." >&2; exit 1; }
done < "$STATE_FILE"

while read -r interface port extra; do
  [ -n "${interface:-}" ] || continue
  "$UFW" --force delete allow in on "$interface" to any port "$port" proto udp comment "$COMMENT" >/dev/null 2>&1 || true
done < "$STATE_FILE"
rm -f "$STATE_FILE"
echo "Removed only the recorded huou07 WireGuard UDP firewall rules."
