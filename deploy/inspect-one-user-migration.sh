#!/bin/sh
# Read-only privileged inventory for the huou07 single-user cutover.
# Deliberately prints metadata only; never prints environment/config contents.
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this inspection as root; it makes no changes." >&2
  exit 1
fi
# Root may have invoked this from the SSH owner's non-searchable workspace.
# All service-account Podman inspection is explicitly anchored at `/`.
cd /

echo "== Target identity =="
getent passwd huou07 | awk -F: '{printf "user=%s uid=%s gid=%s home=%s shell=%s\n", $1,$3,$4,$6,$7}'
id huou07 | sed -E 's/(groups=)[^)]*/\1[omitted]/'
loginctl show-user huou07 -p Linger --value | sed 's/^/linger=/'
for user in huou07-dsh huou07-opencode huou07-litellm huou07-omniroute huou07-playground; do
  entry=$(getent passwd "$user") || { echo "required service account not found: $user" >&2; exit 1; }
  printf '%s\n' "$entry" | awk -F: '{printf "service_user=%s uid=%s gid=%s home=%s shell=%s\n", $1,$3,$4,$6,$7}'
done
for user in huou07 huou07-litellm huou07-omniroute; do
  awk -F: -v user="$user" '$1 == user {print "subuid=" $0; found=1} END {if (!found) print "subuid=missing user=" user}' /etc/subuid
  awk -F: -v user="$user" '$1 == user {print "subgid=" $0; found=1} END {if (!found) print "subgid=missing user=" user}' /etc/subgid
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

echo "== Privilege boundary inventory =="
for group in sudo docker; do
  getent group "$group" | awk -F: -v group="$group" -v user=huou07 '$4 ~ "(^|,)" user "(,|$)" {printf "group=%s contains huou07=yes\n", group; found=1} END {if (!found) printf "group=%s contains huou07=no\n", group}'
done
if [ -S /run/docker.sock ]; then
  stat -c 'docker_socket=present owner=%U group=%G mode=%a' /run/docker.sock
else
  echo 'docker_socket=absent'
fi
if systemctl is-active --quiet docker.service; then echo 'rootful_docker=active'; else echo 'rootful_docker=inactive'; fi
sudo_listing=$(mktemp)
chmod 0600 "$sudo_listing"
if ! /usr/bin/sudo -n -l -U huou07 >"$sudo_listing" 2>&1; then
  rm -f "$sudo_listing"
  echo 'Could not read huou07 sudo policy; inventory is incomplete.' >&2
  exit 1
fi
if grep -Eiq 'NOPASSWD|!authenticate' "$sudo_listing"; then
  echo 'sudo_policy=passwordless-rule-present'
else
  echo 'sudo_policy=no-passwordless-rule-reported'
fi
rm -f "$sudo_listing"

echo "== Session/state volume summary =="
for path in /var/lib/huou07-dsh/dsh /var/lib/huou07-opencode /var/lib/huou07-omniroute/data; do
  if [ -d "$path" ]; then
    printf '%s files=' "$path"
    count_file=$(mktemp)
    find "$path" -xdev -type f -printf x >"$count_file" || { rm -f "$count_file"; echo "file count failed for $path" >&2; exit 1; }
    count=$(wc -c <"$count_file" | tr -d ' ')
    rm -f "$count_file"
    printf '%s\n' "$count"
  fi
done

echo "== Target user-unit state =="
target_uid=$(id -u huou07)
target_runtime="/run/user/$target_uid"
if [ -S "$target_runtime/bus" ]; then
  for unit in huou07-litellm-db.service huou07-litellm.service huou07-omniroute.service huou07-opencode-web.service huou07-dsh.service huou07-playground.service; do
    active=$(runuser -u huou07 -- env HOME=/home/huou07 XDG_RUNTIME_DIR="$target_runtime" DBUS_SESSION_BUS_ADDRESS="unix:path=$target_runtime/bus" /usr/bin/systemctl --user is-active "$unit" 2>/dev/null || true)
    enabled=$(runuser -u huou07 -- env HOME=/home/huou07 XDG_RUNTIME_DIR="$target_runtime" DBUS_SESSION_BUS_ADDRESS="unix:path=$target_runtime/bus" /usr/bin/systemctl --user is-enabled "$unit" 2>/dev/null || true)
    printf '%s active=%s enabled=%s\n' "$unit" "${active:-unknown}" "${enabled:-unknown}"
  done
else
  echo "user_manager_bus=unavailable; target unit state not inspected"
fi

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
echo 'OpenCode auth.json locations under the known source/target data roots:'
for root in /var/lib/huou07-opencode/data /home/huou07/.local/share/opencode; do
  if [ -d "$root" ]; then
    find "$root" -xdev -type f -name auth.json -print \
      || { echo "OpenCode auth path discovery failed under $root" >&2; exit 1; }
  else
    printf 'data_root_missing=%s\n' "$root"
  fi
done
echo 'Codex native login status:'
runuser -u huou07 -- env HOME=/home/huou07 /home/huou07/.local/bin/codex login status

echo "== Rootless Podman inventory (names/images/state only) =="
for user in huou07-litellm huou07-omniroute; do
  home=$(getent passwd "$user" | cut -d: -f6)
  runtime="/run/$user"
  printf '[%s]\n' "$user"
  runuser -u "$user" -- env HOME="$home" XDG_RUNTIME_DIR="$runtime" /usr/bin/podman info --format 'rootless={{.Host.Security.Rootless}}' \
    || { echo "Podman info failed for $user; inventory is incomplete" >&2; exit 1; }
  runuser -u "$user" -- env HOME="$home" XDG_RUNTIME_DIR="$runtime" /usr/bin/podman ps -a \
    --format 'container={{.Names}} image={{.Image}} status={{.Status}}' \
    || { echo "Podman container discovery failed for $user; inventory is incomplete" >&2; exit 1; }
  runuser -u "$user" -- env HOME="$home" XDG_RUNTIME_DIR="$runtime" /usr/bin/podman volume ls \
    --format 'volume={{.Name}} driver={{.Driver}}' \
    || { echo "Podman volume discovery failed for $user; inventory is incomplete" >&2; exit 1; }
done

echo 'LiteLLM PostgreSQL volume metadata:'
litellm_home=$(getent passwd huou07-litellm | cut -d: -f6)
runuser -u huou07-litellm -- env HOME="$litellm_home" XDG_RUNTIME_DIR=/run/huou07-litellm \
  /usr/bin/podman volume inspect --format 'name={{.Name}} driver={{.Driver}} mountpoint={{.Mountpoint}}' huou07-litellm-postgres

echo "== OmniRoute data ownership through the original user namespace =="
omni_home=$(getent passwd huou07-omniroute | cut -d: -f6)
runuser -u huou07-omniroute -- env HOME="$omni_home" XDG_RUNTIME_DIR=/run/huou07-omniroute \
  /usr/bin/podman unshare stat -c 'container_view_owner=%u:%g mode=%a path=%n' /var/lib/huou07-omniroute/data
runuser -u huou07-omniroute -- env HOME="$omni_home" XDG_RUNTIME_DIR=/run/huou07-omniroute \
  /usr/bin/podman unshare cat /proc/self/uid_map
runuser -u huou07-omniroute -- env HOME="$omni_home" XDG_RUNTIME_DIR=/run/huou07-omniroute \
  /usr/bin/podman unshare cat /proc/self/gid_map
runuser -u huou07-omniroute -- env HOME="$omni_home" XDG_RUNTIME_DIR=/run/huou07-omniroute \
  /usr/bin/podman inspect huou07-omniroute-app \
  --format '{{range .Mounts}}{{printf "mount=%s -> %s\n" .Source .Destination}}{{end}}'

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
