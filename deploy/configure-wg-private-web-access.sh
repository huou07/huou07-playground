#!/bin/sh
set -eu

STATE_DIR=/etc/huou07-playground
STATE_FILE=$STATE_DIR/wg-private-web-access.ports
UFW=/usr/sbin/ufw
COMMENT="huou07 private app access"
PORTS="8765 9090 4000 51821 14096 20128 20129 20132"

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
if [ -L "$STATE_FILE" ]; then
  echo "The private-access state file must not be a symbolic link." >&2
  exit 1
fi
install -d -o root -g root -m 0755 "$STATE_DIR"

rule_present() {
  port=$1
  "$UFW" status 2>/dev/null | awk -v rule="${port}/tcp" '
    $1 == rule && $2 == "ALLOW" && $3 == "IN" {
      for (i = 4; i < NF; i++) {
        if ($i == "on" && $(i + 1) == "wg0") found = 1
      }
    }
    END { exit !found }
  '
}

if [ -e "$STATE_FILE" ]; then
  for port in $(cat "$STATE_FILE"); do
    case " $PORTS " in *" $port "*) ;; *) echo "Invalid private-access state; refusing firewall changes." >&2; exit 1 ;; esac
    if ! rule_present "$port"; then
      "$UFW" allow in on wg0 to any port "$port" proto tcp comment "$COMMENT" >/dev/null
    fi
  done
  echo "Verified the existing WireGuard-only application firewall rules."
  exit 0
fi

added=""
rollback() {
  for port in $added; do
    "$UFW" --force delete allow in on wg0 to any port "$port" proto tcp comment "$COMMENT" >/dev/null 2>&1 || true
  done
}
trap rollback EXIT HUP INT TERM

for port in $PORTS; do
  if ! rule_present "$port"; then
    "$UFW" allow in on wg0 to any port "$port" proto tcp comment "$COMMENT" >/dev/null
    added="$added $port"
  fi
done

if [ -n "$added" ]; then
  state_tmp=$(mktemp "$STATE_DIR/.wg-private-web-access.XXXXXX")
  printf '%s\n' "$added" | tr ' ' '\n' | sed '/^$/d' > "$state_tmp"
  chown root:root "$state_tmp"
  chmod 0600 "$state_tmp"
  mv -f "$state_tmp" "$STATE_FILE"
fi
trap - EXIT HUP INT TERM
echo "Applied WireGuard-interface-only firewall allowances; SSH and default policies were preserved."
