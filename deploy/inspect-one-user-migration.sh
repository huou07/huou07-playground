#!/bin/sh
# Read-only privileged inventory for the huou07 single-user cutover.
# Deliberately prints metadata only; never prints environment/config contents.
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this inspection as root; it makes no changes." >&2
  exit 1
fi

echo "== Target identity =="
getent passwd huou07 | awk -F: '{printf "user=%s uid=%s gid=%s home=%s shell=%s\n", $1,$3,$4,$6,$7}'
id huou07 | sed -E 's/(groups=)[^)]*/\1[omitted]/'
loginctl show-user huou07 -p Linger --value | sed 's/^/linger=/'
for user in huou07-dsh huou07-opencode huou07-litellm huou07-omniroute huou07-playground; do
  entry=$(getent passwd "$user" 2>/dev/null || true)
  if [ -n "$entry" ]; then
    printf '%s\n' "$entry" | awk -F: '{printf "service_user=%s uid=%s gid=%s home=%s shell=%s\n", $1,$3,$4,$6,$7}'
  else
    printf 'service_user=%s absent\n' "$user"
  fi
done
for user in huou07 huou07-litellm huou07-omniroute; do
  awk -F: -v user="$user" '$1 == user {print "subuid=" $0}' /etc/subuid
  awk -F: -v user="$user" '$1 == user {print "subgid=" $0}' /etc/subgid
done

echo "== Managed service state =="
for unit in \
  huou07-dsh.service huou07-opencode-web.service \
  huou07-litellm.service huou07-litellm-db.service \
  huou07-omniroute.service huou07-playground.service; do
  if systemctl show "$unit" >/dev/null 2>&1; then
    printf '%s active=%s enabled=%s mainpid=%s\n' "$unit" \
      "$(systemctl show -p ActiveState --value "$unit")" \
      "$(systemctl is-enabled "$unit" 2>/dev/null || true)" \
      "$(systemctl show -p MainPID --value "$unit")"
  else
    printf '%s absent\n' "$unit"
  fi
done

echo "== Session/state volume summary =="
for path in /var/lib/huou07-dsh/dsh /var/lib/huou07-opencode /var/lib/huou07-omniroute/data; do
  if [ -d "$path" ]; then
    printf '%s files=' "$path"
    find "$path" -xdev -type f 2>/dev/null | wc -l | tr -d ' '
  fi
done

echo "== Source path metadata (no file contents) =="
for path in \
  /var/lib/huou07-dsh /var/lib/huou07-dsh/dsh \
  /var/lib/huou07-opencode /var/lib/huou07-opencode/config \
  /var/lib/huou07-opencode/data /etc/huou07-playground/opencode-web.env \
  /var/lib/huou07-playground/apps.json \
  /etc/huou07-litellm/config.yaml /etc/huou07-litellm/litellm.env \
  /etc/huou07-litellm/postgres.env /var/lib/huou07-omniroute/data \
  /etc/huou07-omniroute/omniroute.env \
  /srv/huou07-dsh-workspaces /srv/huou07-opencode-workspaces; do
  if [ -e "$path" ]; then
    stat -c '%F %U:%G %a %s bytes %n' "$path"
  else
    printf 'missing %s\n' "$path"
  fi
done

echo "== Credential file presence only =="
for path in \
  /var/lib/huou07-opencode/data/auth.json \
  /var/lib/huou07-opencode/auth.json \
  /home/huou07/.local/share/opencode/auth.json \
  /home/huou07/.local/share/opencode/data/auth.json \
  /home/huou07/.config/opencode/auth.json \
  /var/lib/huou07-dsh/.codex/auth.json \
  /var/lib/huou07-dsh/dsh/profiles/web; do
  if [ -e "$path" ]; then
    stat -c '%F %U:%G %a %s bytes %n' "$path"
  else
    printf 'missing %s\n' "$path"
  fi
done

echo "== Rootless Podman inventory (names/images/state only) =="
for user in huou07-litellm huou07-omniroute; do
  home=$(getent passwd "$user" | cut -d: -f6)
  runtime="/run/$user"
  printf '[%s]\n' "$user"
  runuser -u "$user" -- env HOME="$home" XDG_RUNTIME_DIR="$runtime" /usr/bin/podman ps -a \
    --format 'container={{.Names}} image={{.Image}} status={{.Status}}' 2>&1 || true
  runuser -u "$user" -- env HOME="$home" XDG_RUNTIME_DIR="$runtime" /usr/bin/podman volume ls \
    --format 'volume={{.Name}} driver={{.Driver}}' 2>&1 || true
done

echo "== User destination conflicts =="
for path in \
  /home/huou07/.dsh /home/huou07/.config/dsh \
  /home/huou07/.local/share/dsh /home/huou07/.local/state/dsh \
  /home/huou07/.config/litellm /home/huou07/.local/share/omniroute \
  /home/huou07/Projects/dsh /home/huou07/Projects/opencode; do
  if [ -e "$path" ]; then
    stat -c '%F %U:%G %a %s bytes %n' "$path"
  else
    printf 'missing %s\n' "$path"
  fi
done

echo "== Safety note =="
echo "No secret values, file listings, database rows, or process command lines were read or emitted."
