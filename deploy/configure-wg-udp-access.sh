#!/bin/sh
set -eu

STATE_DIR=/etc/huou07-playground
STATE_FILE=$STATE_DIR/wg-udp-access.rules
UFW=/usr/sbin/ufw
IP=/usr/sbin/ip
WG=/usr/bin/wg
COMMENT="huou07 WireGuard endpoint"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root." >&2
  exit 1
fi
if [ ! -x "$UFW" ]; then
  echo "UFW is not installed; no firewall rules were changed."
  exit 0
fi
if ! "$UFW" status 2>/dev/null | grep -q '^Status: active$'; then
  echo "UFW is inactive; no firewall rules were changed."
  exit 0
fi
if [ ! -x "$IP" ] || [ ! -x "$WG" ]; then
  echo "The IP or WireGuard utility is unavailable; no firewall rules were changed." >&2
  exit 1
fi
if [ -L "$STATE_FILE" ] || { [ -e "$STATE_FILE" ] && [ ! -f "$STATE_FILE" ]; }; then
  echo "The WireGuard UDP state file is invalid; refusing firewall changes." >&2
  exit 1
fi
if [ -f "$STATE_FILE" ]; then
  while read -r saved_interface saved_port extra; do
    [ -n "${saved_interface:-}" ] || continue
    case "$saved_interface" in *[!A-Za-z0-9_.:-]*) echo "Invalid interface in WireGuard UDP state; refusing firewall changes." >&2; exit 1 ;; esac
    case "$saved_port" in ''|*[!0-9]*) echo "Invalid port in WireGuard UDP state; refusing firewall changes." >&2; exit 1 ;; esac
    [ "$saved_port" -ge 1 ] && [ "$saved_port" -le 65535 ] && [ -z "${extra:-}" ] || { echo "Invalid WireGuard UDP state; refusing firewall changes." >&2; exit 1; }
  done < "$STATE_FILE"
fi
install -d -o root -g root -m 0755 "$STATE_DIR"

port=$("$WG" show wg0 listen-port 2>/dev/null || true)
case "$port" in ''|*[!0-9]*) echo "wg0 has no valid UDP listen port; no firewall rules were changed."; exit 0 ;; esac
[ "$port" -ge 1 ] && [ "$port" -le 65535 ] || { echo "wg0 reported an invalid UDP listen port." >&2; exit 1; }
interface=$("$IP" -4 route get 1.1.1.1 2>/dev/null | awk '{ for (i = 1; i <= NF; i++) if ($i == "dev") { print $(i + 1); exit } }')
case "$interface" in ''|*[!A-Za-z0-9_.:-]*) echo "The default-route interface is unavailable; no firewall rules were changed."; exit 0 ;; esac

state_has_rule() {
  [ -f "$STATE_FILE" ] && awk -v interface="$interface" -v port="$port" '$1 == interface && $2 == port { found = 1 } END { exit !found }' "$STATE_FILE"
}

rule_present() {
  "$UFW" status 2>/dev/null | awk -v rule="${port}/udp" -v interface="$interface" \
    '$1 == rule && $2 == "on" && $3 == interface && $4 == "ALLOW" { found = 1 } END { exit !found }'
}

if rule_present; then
  if ! state_has_rule; then
    echo "The WireGuard UDP rule already exists and is not managed by this installer; preserving it."
  else
    echo "Verified the existing interface-scoped WireGuard UDP rule."
  fi
  exit 0
fi

added=0
state_tmp=""
rollback() {
  status=$?
  trap - EXIT HUP INT TERM
  [ -z "$state_tmp" ] || rm -f "$state_tmp"
  if [ "$added" -eq 1 ]; then
    "$UFW" --force delete allow in on "$interface" to any port "$port" proto udp comment "$COMMENT" >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap rollback EXIT HUP INT TERM

"$UFW" allow in on "$interface" to any port "$port" proto udp comment "$COMMENT" >/dev/null
added=1
state_tmp=$(mktemp "$STATE_DIR/.wg-udp-access.XXXXXX")
if [ -f "$STATE_FILE" ]; then cat "$STATE_FILE" > "$state_tmp"; fi
if ! state_has_rule; then printf '%s %s\n' "$interface" "$port" >> "$state_tmp"; fi
chown root:root "$state_tmp"
chmod 0600 "$state_tmp"
mv -f "$state_tmp" "$STATE_FILE"
state_tmp=""
added=0
trap - EXIT HUP INT TERM
echo "Allowed the wg0 UDP listener only on the default-route interface; the rule is recorded for rollback."
