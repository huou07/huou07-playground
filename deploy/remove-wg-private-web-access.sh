#!/bin/sh
set -eu

STATE_FILE=/etc/huou07-playground/wg-private-web-access.ports
UFW=/usr/sbin/ufw
COMMENT="huou07 private app access"
PORTS="8765 9090 4000 51821 14096 20128 20129 20132"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root." >&2
  exit 1
fi
if [ ! -x "$UFW" ]; then
  echo "UFW is not installed; no firewall rules can be removed." >&2
  exit 1
fi
if [ ! -e "$STATE_FILE" ]; then
  echo "No huou07-managed WireGuard firewall rules are recorded."
  exit 0
fi
if [ -L "$STATE_FILE" ] || [ ! -f "$STATE_FILE" ]; then
  echo "The private-access state file is invalid; refusing firewall changes." >&2
  exit 1
fi
for port in $(cat "$STATE_FILE"); do
  case " $PORTS " in *" $port "*) ;; *) echo "Invalid private-access state; refusing firewall changes." >&2; exit 1 ;; esac
done
for port in $(cat "$STATE_FILE"); do
  "$UFW" --force delete allow in on wg0 to any port "$port" proto tcp comment "$COMMENT" >/dev/null 2>&1 || true
done
rm -f "$STATE_FILE"
echo "Removed only the recorded huou07 WireGuard firewall rules."
