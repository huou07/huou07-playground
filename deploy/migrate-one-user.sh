#!/usr/bin/env bash
# Owner-run cutover. preflight is read-only; cutover is the only phase that stops services.
set -Eeuo pipefail
cd /
ACTION=${1:-}
case "$ACTION" in preflight|cutover|rollback) ;; *) echo "usage: $0 preflight|cutover|rollback" >&2; exit 2;; esac
[[ $EUID == 0 ]] || { echo "Run as root; this script never invokes sudo." >&2; exit 1; }

USER_NAME=huou07
HOME_DIR=/home/huou07
BACKUP_ROOT=/var/backups/huou07-one-user
RECORD=/var/lib/huou07-playground-migration/active-backup
PG_VOLUME=huou07-litellm-postgres
REPO=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
RUNTIME=/run/user/$(id -u "$USER_NAME")
SYSTEM_UNITS=(huou07-dsh.service huou07-opencode-web.service huou07-litellm.service huou07-litellm-db.service huou07-omniroute.service huou07-playground.service)
USER_UNITS=(huou07-playground.service huou07-dsh.service huou07-opencode-web.service huou07-omniroute.service huou07-litellm.service huou07-litellm-db.service)
declare -A SPACE_REQUIRED=() SPACE_PATH=() SPACE_PURPOSE=()
fail() { echo "Migration stopped: $*" >&2; exit 1; }
as_user() { runuser -u "$USER_NAME" -- env HOME="$HOME_DIR" XDG_RUNTIME_DIR="$RUNTIME" DBUS_SESSION_BUS_ADDRESS="unix:path=$RUNTIME/bus" "$@"; }
as_service() { local user=$1 home=$2 runtime=$3; shift 3; runuser -u "$user" -- env HOME="$home" XDG_RUNTIME_DIR="$runtime" "$@"; }
userctl() { as_user /usr/bin/systemctl --user "$@"; }
du_bytes() {
  local path output
  path=$1
  [[ -e $path ]] || return 0
  output=$(du -sx --apparent-size -B1 -- "$path") || fail "could not estimate storage use: $path"
  awk '{print $1}' <<<"$output"
}
wg_addresses() {
  /usr/sbin/ip -j -4 addr show dev wg0 | python3 -c '
import json, sys
for link in json.load(sys.stdin):
    for address in link.get("addr_info", []):
        if address.get("family") == "inet":
            print(address["local"])
'
}
check_dashboard_wireguard() {
  local addresses address
  addresses=$(wg_addresses) || fail "could not inspect the active wg0 address"
  [[ -n $addresses ]] || fail "wg0 has no IPv4 address; dashboard WireGuard access cannot be verified"
  while IFS= read -r address; do
    [[ -n $address ]] || continue
    if curl -fsS --max-time 3 "http://$address:8765/api/health" >/dev/null; then
      printf 'WireGuard dashboard check passed: %s:8765\n' "$address"
      return 0
    fi
  done <<< "$addresses"
  fail "dashboard is not healthy on any active wg0 IPv4 address"
}
add_space_need() {
  local path=$1 bytes=$2 purpose=$3 output fs available
  output=$(df -PB1 -- "$path") || fail "could not inspect free space for $purpose at $path"
  read -r fs available < <(awk 'NR == 2 {print $1, $4}' <<<"$output")
  [[ $available =~ ^[0-9]+$ ]] || fail "could not parse free space for $purpose at $path"
  SPACE_REQUIRED[$fs]=$(( ${SPACE_REQUIRED[$fs]:-0} + bytes ))
  SPACE_PATH[$fs]=$path
  SPACE_PURPOSE[$fs]="${SPACE_PURPOSE[$fs]:+${SPACE_PURPOSE[$fs]}, }$purpose"
}
check_cutover_space() {
  local state_bytes=0 pg_bytes=0 omni_bytes=0 image_bytes=0 amount output fs available needed
  local path image
  local -a state_paths=(
    /var/lib/huou07-dsh /var/lib/huou07-opencode
    /var/lib/huou07-playground/apps.json /var/lib/huou07-omniroute/data
    /etc/huou07-playground /etc/huou07-litellm /etc/huou07-omniroute
    /srv/huou07-dsh-workspaces /srv/huou07-opencode-workspaces
    /home/huou07/.codex /home/huou07/.config/opencode
    /home/huou07/.local/share/opencode /home/huou07/.local/state/opencode
    /home/huou07/.cache/opencode
  )
  for path in "${state_paths[@]}"; do
    amount=$(du_bytes "$path")
    state_bytes=$((state_bytes + amount))
  done
  local pg_mount
  pg_mount=$(as_service huou07-litellm /var/lib/huou07-litellm /run/huou07-litellm \
    /usr/bin/podman volume inspect --format '{{.Mountpoint}}' "$PG_VOLUME") || fail "could not locate PostgreSQL volume for space estimate"
  pg_bytes=$(du_bytes "$pg_mount")
  omni_bytes=$(du_bytes /var/lib/huou07-omniroute/data)
  for image in docker.io/library/postgres:16 ghcr.io/berriai/litellm:v1.103.1; do
    amount=$(as_service huou07-litellm /var/lib/huou07-litellm /run/huou07-litellm \
      /usr/bin/podman image inspect --format '{{.Size}}' "$image") || fail "could not estimate required image size: $image"
    [[ $amount =~ ^[0-9]+$ ]] || fail "invalid image size reported for $image"
    image_bytes=$((image_bytes + amount))
  done
  for image in docker.io/library/redis:8.6.5-alpine docker.io/diegosouzapw/omniroute:3.8.51; do
    amount=$(as_service huou07-omniroute /var/lib/huou07-omniroute /run/huou07-omniroute \
      /usr/bin/podman image inspect --format '{{.Size}}' "$image") || fail "could not estimate required image size: $image"
    [[ $amount =~ ^[0-9]+$ ]] || fail "invalid image size reported for $image"
    image_bytes=$((image_bytes + amount))
  done
  local graph_root
  graph_root=$(as_user /usr/bin/podman info --format '{{.Store.GraphRoot}}') || fail "could not locate target Podman graphroot"
  [[ -d $graph_root ]] || fail "target Podman graphroot is not an existing directory"

  # 25% headroom plus 1 GiB covers tar metadata and modest growth between preflight and cutover.
  # OmniRoute data is in state.tar and in its namespace-preserving archive.
  add_space_need /var/backups "$((state_bytes + pg_bytes + omni_bytes + (state_bytes + pg_bytes + omni_bytes) / 4 + 1073741824))" 'private backup'
  add_space_need "$HOME_DIR" "$((state_bytes + state_bytes / 4 + 1073741824))" 'HOME state and workspaces'
  add_space_need "$graph_root" "$((pg_bytes + image_bytes + (pg_bytes + image_bytes) / 4 + 1073741824))" 'rootless PostgreSQL volume and images'
  for fs in "${!SPACE_REQUIRED[@]}"; do
    output=$(df -PB1 -- "${SPACE_PATH[$fs]}") || fail "could not recheck free space for ${SPACE_PURPOSE[$fs]}"
    read -r _ available < <(awk 'NR == 2 {print $1, $4}' <<<"$output")
    needed=${SPACE_REQUIRED[$fs]}
    [[ $available =~ ^[0-9]+$ ]] || fail "could not parse available bytes for ${SPACE_PURPOSE[$fs]}"
    (( available >= needed )) || fail "insufficient space on $fs for ${SPACE_PURPOSE[$fs]}: need $needed bytes, available $available"
    printf 'Space check passed: %s need=%s bytes available=%s bytes\n' "${SPACE_PURPOSE[$fs]}" "$needed" "$available"
  done
}

preflight() {
  [[ $(getent passwd "$USER_NAME" | cut -d: -f6) == "$HOME_DIR" ]] || fail "unexpected target HOME"
  [[ $(loginctl show-user "$USER_NAME" -p Linger --value) == yes ]] || fail "lingering must remain enabled"
  [[ -S $RUNTIME/bus ]] || fail "huou07 user-manager bus unavailable"
  [[ -x /home/huou07/.local/bin/codex && -x "$HOME_DIR/.opencode/bin/opencode" ]] || fail "native Codex/OpenCode CLI missing"
  [[ -x /usr/local/libexec/huou07-litellm/prepare.sh && -x /usr/local/libexec/huou07-omniroute/prepare.sh ]] || fail "rootless service helpers missing"
  [[ -x /usr/bin/podman && -x /usr/bin/slirp4netns ]] || fail "rootless Podman dependencies missing"
  grep -q '^huou07:' /etc/subuid || fail "huou07 has no subordinate UID range for rootless Podman"
  grep -q '^huou07:' /etc/subgid || fail "huou07 has no subordinate GID range for rootless Podman"
  local login
  login=$(as_user /home/huou07/.local/bin/codex login status 2>&1) || fail "Codex login status could not be checked"
  [[ $login == *"Logged in using ChatGPT"* ]] || fail "native Codex ChatGPT login is not present; refusing to alter auth"
  for unit in "${SYSTEM_UNITS[@]}"; do
    systemctl is-active --quiet "$unit" || fail "expected production unit is not active: $unit"
    if userctl is-active --quiet "$unit"; then fail "target user unit is already active: $unit"; fi
    if [[ -e $HOME_DIR/.config/systemd/user/$unit ]]; then fail "target unit file already exists; refusing to replace it: $unit"; fi
  done
  local dsh_port
  dsh_port=$(python3 "$REPO/web/private_services.py" --port dsh backend_port) || fail "DSH port configuration could not be read"
  curl -fsS --max-time 3 http://127.0.0.1:4000/health/liveliness >/dev/null || fail "production LiteLLM health check failed"
  curl -fsS --max-time 3 http://127.0.0.1:20128/healthz >/dev/null || fail "production OmniRoute health check failed"
  curl -fsS --max-time 3 "http://127.0.0.1:$dsh_port/favicon.svg" >/dev/null || fail "production DSH health check failed"
  local opencode_status
  opencode_status=$(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:4096/) || fail "production OpenCode Web health check failed"
  [[ $opencode_status == 200 || $opencode_status == 401 || $opencode_status == 403 ]] || fail "production OpenCode Web HTTP $opencode_status"
  curl -fsS --max-time 3 http://127.0.0.1:8765/api/health >/dev/null || fail "production dashboard health check failed"
  check_dashboard_wireguard
  [[ -d /var/lib/huou07-dsh/dsh/profiles/web ]] || fail "DSH web profile/session tree missing"
  [[ -d /var/lib/huou07-opencode/data ]] || fail "OpenCode native data tree missing"
  local source_auth
  source_auth=$(find /var/lib/huou07-opencode/data -xdev -type f -name auth.json -print -quit) || fail "OpenCode credential discovery failed"
  [[ -n $source_auth ]] || fail "OpenCode Web provider auth.json missing"
  echo "OpenCode credential source path: $source_auth (contents not read)"
  [[ -f /etc/huou07-playground/opencode-web.env && -f /var/lib/huou07-playground/apps.json ]] || fail "OpenCode Web auth or dashboard registry missing"
  [[ -f /etc/huou07-litellm/config.yaml && -f /etc/huou07-litellm/litellm.env && -f /etc/huou07-litellm/postgres.env ]] || fail "LiteLLM state missing"
  [[ -f /etc/huou07-omniroute/omniroute.env && -d /var/lib/huou07-omniroute/data ]] || fail "OmniRoute state missing"
  as_service huou07-litellm /var/lib/huou07-litellm /run/huou07-litellm /usr/bin/podman info --format '{{.Host.Security.Rootless}}' | grep -qx true || fail "LiteLLM Podman discovery failed"
  as_service huou07-litellm /var/lib/huou07-litellm /run/huou07-litellm /usr/bin/podman volume exists "$PG_VOLUME" || fail "LiteLLM PostgreSQL volume missing"
  as_service huou07-omniroute /var/lib/huou07-omniroute /run/huou07-omniroute /usr/bin/podman info --format '{{.Host.Security.Rootless}}' | grep -qx true || fail "OmniRoute Podman discovery failed"
  local mapped_owner
  mapped_owner=$(as_service huou07-omniroute /var/lib/huou07-omniroute /run/huou07-omniroute /usr/bin/podman unshare stat -c '%u:%g' /var/lib/huou07-omniroute/data) || fail "OmniRoute namespace ownership could not be read"
  [[ $mapped_owner == 1000:1000 ]] || fail "OmniRoute data owner maps to $mapped_owner in its original namespace, expected 1000:1000"
  as_user /usr/bin/podman info --format '{{.Host.Security.Rootless}}' | grep -qx true || fail "target rootless Podman unavailable"
  local volume_rc=0
  as_user /usr/bin/podman volume exists "$PG_VOLUME" || volume_rc=$?
  [[ $volume_rc == 1 ]] || fail "target PostgreSQL volume check returned $volume_rc (expected 1=absent)"
  local target_groups sudo_policy
  target_groups=$(id -nG "$USER_NAME") || fail "could not inspect target group membership"
  sudo_policy=$(/usr/bin/sudo -n -l -U "$USER_NAME" 2>&1) || sudo_policy=''
  if [[ " $target_groups " == *" sudo "* || $sudo_policy =~ NOPASSWD|!authenticate || -n $sudo_policy ]]; then
    echo 'WARNING: owner-confirmed sudo privileges, including any NOPASSWD rules, are retained and can grant root-equivalent access. DSH/OpenCode NoNewPrivileges is unit-local defense in depth, not complete user isolation.' >&2
  fi
  if [[ " $target_groups " == *" docker "* ]]; then
    if [[ -S /run/docker.sock ]]; then
      echo 'WARNING: huou07 belongs to docker and the rootful Docker socket is present; this is root-equivalent access. DSH/OpenCode mask the socket as defense in depth, not a complete security boundary.' >&2
    else
      echo 'WARNING: huou07 belongs to docker; Docker socket access is root-equivalent when the rootful socket is available. DSH/OpenCode socket masking is defense in depth, not a complete security boundary.' >&2
    fi
  fi
  echo 'The migration does not stop or modify docker.service or unrelated Docker containers.'
  local target_uid
  target_uid=$(id -u "$USER_NAME")
  for path in "$HOME_DIR/Projects" "$HOME_DIR/.config" "$HOME_DIR/.local" "$HOME_DIR/.local/share" "$HOME_DIR/.local/state" "$HOME_DIR/.cache" "$HOME_DIR/.config/systemd/user"; do
    if [[ -L $path ]]; then fail "target path is a symlink; refusing path redirection: $path"; fi
    if [[ -e $path ]]; then
      [[ -d $path && $(stat -c '%u' "$path") == "$target_uid" ]] || fail "target directory must be an ordinary huou07-owned directory: $path"
    fi
  done
  for path in "$HOME_DIR/Projects/dsh" "$HOME_DIR/Projects/opencode" "$HOME_DIR/.config/litellm" "$HOME_DIR/.config/omniroute" "$HOME_DIR/.local/share/omniroute/data"; do
    if [[ -e $path ]]; then local contents; contents=$(find "$path" -mindepth 1 -maxdepth 1 -print) || fail "could not inspect $path"; [[ -z $contents ]] || fail "target path is not empty: $path"; fi
  done
  [[ ! -e $HOME_DIR/.dsh && ! -L $HOME_DIR/.dsh ]] || fail "destination exists; refusing to merge DSH profile/session tree: $HOME_DIR/.dsh"
  verify_merge /var/lib/huou07-dsh/config "$HOME_DIR/.config"
  verify_merge /var/lib/huou07-dsh/data "$HOME_DIR/.local/share"
  verify_merge /var/lib/huou07-dsh/state "$HOME_DIR/.local/state"
  verify_merge /var/lib/huou07-dsh/cache "$HOME_DIR/.cache"
  verify_merge /var/lib/huou07-opencode/config "$HOME_DIR/.config"
  verify_merge /var/lib/huou07-opencode/data "$HOME_DIR/.local/share"
  verify_merge /var/lib/huou07-opencode/state "$HOME_DIR/.local/state"
  verify_merge /var/lib/huou07-opencode/cache "$HOME_DIR/.cache"
  verify_merge /srv/huou07-dsh-workspaces "$HOME_DIR/Projects/dsh"
  verify_merge /srv/huou07-opencode-workspaces "$HOME_DIR/Projects/opencode"
  for path in "$HOME_DIR/.config/opencode/web.env" "$HOME_DIR/.local/state/huou07-playground/apps.json"; do
    [[ ! -e $path ]] || fail "destination exists; refusing to replace owner data: $path"
  done
  [[ ! -e /srv/huou07-dsh-workspaces-legacy && ! -e /srv/huou07-opencode-workspaces-legacy ]] || fail "workspace rollback destination exists"
  [[ -d /srv/huou07-dsh-workspaces && -d /srv/huou07-opencode-workspaces ]] || fail "legacy workspaces missing"
  for unit in "${SYSTEM_UNITS[@]}"; do
    state=$(systemctl is-enabled "$unit" 2>/dev/null || true)
    [[ $state == enabled || $state == enabled-runtime || $state == disabled || $state == static || $state == indirect || $state == generated ]] || fail "unsupported original unit enable state for $unit: ${state:-unknown}"
  done
  check_cutover_space
  echo 'Preflight passed. It did not stop or restart any service.'
}

copy_merge() {
  local src=$1 dst=$2 item rel target
  [[ -d $src ]] || return 0
  install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$dst"
  find "$src" -mindepth 1 -xdev -print0 | while IFS= read -r -d '' item; do
    rel=${item#"$src"/}; target=$dst/$rel
    if [[ -e $target || -L $target ]]; then
      if [[ -d $item && -d $target && ! -L $item && ! -L $target ]]; then continue
      elif [[ -L $item && -L $target && $(readlink "$item") == "$(readlink "$target")" ]]; then continue
      elif [[ -f $item && -f $target ]] && cmp -s "$item" "$target"; then continue
      else fail "state collision; no destination was overwritten: $target"; fi
    fi
    if [[ -d $item && ! -L $item ]]; then install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$target"
    else install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$(dirname "$target")"; cp -a --no-preserve=ownership "$item" "$target"; chown -h "$USER_NAME:$USER_NAME" "$target"; fi
  done
}

verify_merge() {
  local src=$1 dst=$2 item rel target
  [[ -d $src ]] || return 0
  find "$src" -mindepth 1 -xdev -print0 | while IFS= read -r -d '' item; do
    rel=${item#"$src"/}; target=$dst/$rel
    if [[ -e $target || -L $target ]]; then
      if [[ -d $item && -d $target && ! -L $item && ! -L $target ]]; then continue
      elif [[ -L $item && -L $target && $(readlink "$item") == "$(readlink "$target")" ]]; then continue
      elif [[ -f $item && -f $target ]] && cmp -s "$item" "$target"; then continue
      else fail "state collision before cutover; destination will not be overwritten: $target"; fi
    fi
  done
}

stop_target() {
  local unit
  for unit in "${USER_UNITS[@]}"; do
    if userctl show "$unit" >/dev/null 2>&1; then userctl stop "$unit" >/dev/null; fi
  done
  for unit in "${USER_UNITS[@]}"; do
    if userctl is-active --quiet "$unit"; then fail "new user service is still active during rollback: $unit"; fi
    if userctl show "$unit" >/dev/null 2>&1; then userctl disable "$unit" >/dev/null; fi
  done
  local running
  running=$(as_user /usr/bin/podman ps --format '{{.Names}}') || fail 'could not verify target Podman containers stopped during rollback'
  for unit in huou07-litellm-proxy huou07-litellm-db huou07-omniroute-app huou07-omniroute-redis; do
    if grep -Fxq "$unit" <<< "$running"; then fail "target Podman container is still running during rollback: $unit"; fi
  done
}
restore_legacy() {
  stop_target
  for unit in "${USER_UNITS[@]}"; do rm -f "$HOME_DIR/.config/systemd/user/$unit"; done
  userctl daemon-reload >/dev/null 2>&1 || :
  for base in dsh opencode; do
    old=/srv/huou07-$base-workspaces; legacy=$old-legacy
    if [[ -L $old && -d $legacy ]]; then rm -- "$old"; mv -- "$legacy" "$old"; fi
  done
  if [[ -f ${backup:-}/dsh-policy.js && -f ${backup:-}/dsh-picker.js ]]; then
    install -o root -g root -m 0644 "$backup/dsh-policy.js" /opt/huou07-dsh/app/node_modules/@deepseek-ai/dsh-sandbox-policy/lib/index.js
    install -o root -g root -m 0644 "$backup/dsh-picker.js" /opt/huou07-dsh/app/node_modules/@deepseek-ai/dsh-host-directory-picker-browse/lib/index.js
  fi
  if [[ -f ${backup:-}/system-unit-states ]]; then
    while read -r unit state; do
      case "$state" in enabled|enabled-runtime) systemctl enable "$unit" >/dev/null;; *) systemctl disable "$unit" >/dev/null 2>&1 || :;; esac
    done < "$backup/system-unit-states"
  fi
  systemctl start "${SYSTEM_UNITS[@]}"
  for unit in "${SYSTEM_UNITS[@]}"; do systemctl is-active --quiet "$unit" || fail "legacy unit did not recover: $unit"; done
  rm -f "$RECORD"
}

if [[ $ACTION == preflight ]]; then
  preflight
  echo 'Review this exact command before any cutover: sudo sh deploy/migrate-one-user.sh cutover'
  exit 0
fi

if [[ $ACTION == rollback ]]; then
  [[ -f $RECORD ]] || fail "migration backup record not found"
  backup=$(cat "$RECORD")
  [[ -f $backup/dsh-policy.js && -f $backup/dsh-picker.js ]] || fail "rollback backup incomplete"
  restore_legacy
  echo 'Legacy services are restored against their untouched original data. New HOME data and backups remain in place.'
  exit 0
fi

preflight
[[ ! -e $RECORD && ! -L $RECORD ]] || fail "an existing migration record requires explicit review: $RECORD"
# Download images before stopping production writers; this does not start a
# second service and keeps network/image failures outside the outage window.
as_user /usr/bin/podman pull docker.io/library/postgres:16 >/dev/null
as_user /usr/bin/podman pull ghcr.io/berriai/litellm:v1.103.1 >/dev/null
as_user /usr/bin/podman pull docker.io/library/redis:8.6.5-alpine >/dev/null
as_user /usr/bin/podman pull docker.io/diegosouzapw/omniroute:3.8.51 >/dev/null
install -d -o root -g root -m 0700 "$BACKUP_ROOT" /var/lib/huou07-playground-migration
stamp=$(date -u +%Y%m%dT%H%M%SZ); backup=$BACKUP_ROOT/$stamp; mkdir -m 0700 "$backup"
printf '%s\n' "$backup" > "$RECORD"; chmod 0600 "$RECORD"
did_stop=0
cutover_success=0
on_exit() {
  status=$?
  trap - EXIT
  if ((did_stop && !cutover_success)); then
    echo 'Cutover failed; restoring original services.' >&2
    if restore_legacy; then echo 'Automatic rollback completed; original services passed active-state checks.' >&2
    else echo 'AUTOMATIC ROLLBACK FAILED. Keep all backup and source state; inspect services, then run the rollback command from the pinned checkout.' >&2; fi
  fi
  if (( ! cutover_success )); then echo "Private recovery data retained at $backup" >&2; fi
  exit "$status"
}
trap on_exit EXIT

for unit in "${SYSTEM_UNITS[@]}"; do printf '%s %s\n' "$unit" "$(systemctl is-enabled "$unit" 2>/dev/null || true)"; done > "$backup/system-unit-states"
chmod 0600 "$backup/system-unit-states"

# This explicit cutover command is the first operation that stops production.
did_stop=1
for unit in huou07-playground.service huou07-dsh.service huou07-opencode-web.service huou07-omniroute.service huou07-litellm.service huou07-litellm-db.service; do systemctl stop "$unit"; done
source_paths=(var/lib/huou07-dsh var/lib/huou07-opencode var/lib/huou07-playground/apps.json var/lib/huou07-omniroute/data etc/huou07-playground etc/huou07-litellm etc/huou07-omniroute srv/huou07-dsh-workspaces srv/huou07-opencode-workspaces home/huou07/.codex home/huou07/.config/opencode home/huou07/.local/share/opencode home/huou07/.local/state/opencode home/huou07/.cache/opencode)
present=(); for path in "${source_paths[@]}"; do [[ ! -e /$path ]] || present+=("$path"); done
tar --numeric-owner --acls --xattrs -cpf "$backup/state.tar" -C / "${present[@]}"; chmod 0600 "$backup/state.tar"
tar -tf "$backup/state.tar" >/dev/null
cp /opt/huou07-dsh/app/node_modules/@deepseek-ai/dsh-sandbox-policy/lib/index.js "$backup/dsh-policy.js"
cp /opt/huou07-dsh/app/node_modules/@deepseek-ai/dsh-host-directory-picker-browse/lib/index.js "$backup/dsh-picker.js"
chmod 0600 "$backup/dsh-policy.js" "$backup/dsh-picker.js"
as_service huou07-litellm /var/lib/huou07-litellm /run/huou07-litellm /usr/bin/podman volume export "$PG_VOLUME" > "$backup/litellm-postgres-volume.tar"
chmod 0600 "$backup/litellm-postgres-volume.tar"
tar -tf "$backup/litellm-postgres-volume.tar" >/dev/null
as_service huou07-omniroute /var/lib/huou07-omniroute /run/huou07-omniroute /usr/bin/podman unshare tar --numeric-owner -cpf - -C /var/lib/huou07-omniroute/data . > "$backup/omniroute-data.tar"
chmod 0600 "$backup/omniroute-data.tar"
tar -tf "$backup/omniroute-data.tar" >/dev/null
  while read -r unit state; do
    case "$state" in enabled|enabled-runtime) systemctl disable "$unit";; esac
  done < "$backup/system-unit-states"

install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$HOME_DIR/Projects" "$HOME_DIR/.config" "$HOME_DIR/.local/share" "$HOME_DIR/.local/state" "$HOME_DIR/.cache" "$HOME_DIR/.dsh"
copy_merge /var/lib/huou07-dsh/dsh "$HOME_DIR/.dsh"
copy_merge /var/lib/huou07-dsh/config "$HOME_DIR/.config"
copy_merge /var/lib/huou07-dsh/data "$HOME_DIR/.local/share"
copy_merge /var/lib/huou07-dsh/state "$HOME_DIR/.local/state"
copy_merge /var/lib/huou07-dsh/cache "$HOME_DIR/.cache"
copy_merge /var/lib/huou07-opencode/config "$HOME_DIR/.config"
copy_merge /var/lib/huou07-opencode/data "$HOME_DIR/.local/share"
copy_merge /var/lib/huou07-opencode/state "$HOME_DIR/.local/state"
copy_merge /var/lib/huou07-opencode/cache "$HOME_DIR/.cache"
copy_merge /srv/huou07-dsh-workspaces "$HOME_DIR/Projects/dsh"
copy_merge /srv/huou07-opencode-workspaces "$HOME_DIR/Projects/opencode"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$HOME_DIR/.config/litellm" "$HOME_DIR/.config/omniroute" "$HOME_DIR/.local/share/omniroute/data" "$HOME_DIR/.local/state/huou07-playground"
install -o "$USER_NAME" -g "$USER_NAME" -m 0600 /etc/huou07-litellm/litellm.env "$HOME_DIR/.config/litellm/litellm.env"
install -o "$USER_NAME" -g "$USER_NAME" -m 0600 /etc/huou07-litellm/postgres.env "$HOME_DIR/.config/litellm/postgres.env"
install -o "$USER_NAME" -g "$USER_NAME" -m 0644 /etc/huou07-litellm/config.yaml "$HOME_DIR/.config/litellm/config.yaml"
install -o "$USER_NAME" -g "$USER_NAME" -m 0600 /etc/huou07-omniroute/omniroute.env "$HOME_DIR/.config/omniroute/omniroute.env"
install -o "$USER_NAME" -g "$USER_NAME" -m 0600 /etc/huou07-playground/opencode-web.env "$HOME_DIR/.config/opencode/web.env"
install -o "$USER_NAME" -g "$USER_NAME" -m 0600 /var/lib/huou07-playground/apps.json "$HOME_DIR/.local/state/huou07-playground/apps.json"

as_user /usr/bin/podman volume create "$PG_VOLUME" >/dev/null
as_user /usr/bin/podman volume import "$PG_VOLUME" - < "$backup/litellm-postgres-volume.tar"
as_user /usr/bin/podman unshare tar --numeric-owner --same-owner -xpf "$backup/omniroute-data.tar" -C "$HOME_DIR/.local/share/omniroute/data"
target_owner=$(as_user /usr/bin/podman unshare stat -c '%u:%g' "$HOME_DIR/.local/share/omniroute/data")
[[ $target_owner == 1000:1000 ]] || fail "imported OmniRoute owner is $target_owner, expected 1000:1000"
source_auth=$(find /var/lib/huou07-opencode/data -xdev -type f -name auth.json -print -quit)
target_auth="$HOME_DIR/.local/share/${source_auth#/var/lib/huou07-opencode/data/}"
[[ -f $target_auth ]] && cmp -s "$source_auth" "$target_auth" || fail 'OpenCode credential file did not migrate byte-for-byte'
login=$(as_user /home/huou07/.local/bin/codex login status 2>&1) || fail 'native Codex login status failed after state migration'
[[ $login == *"Logged in using ChatGPT"* ]] || fail 'native Codex ChatGPT login changed during migration'
[[ -d $HOME_DIR/.dsh/profiles/web ]] || fail 'DSH web profile/session tree did not migrate'
mv /srv/huou07-dsh-workspaces /srv/huou07-dsh-workspaces-legacy
ln -s "$HOME_DIR/Projects/dsh" /srv/huou07-dsh-workspaces
mv /srv/huou07-opencode-workspaces /srv/huou07-opencode-workspaces-legacy
ln -s "$HOME_DIR/Projects/opencode" /srv/huou07-opencode-workspaces
python3 "$REPO/deploy/patch_dsh_workspace_policy.py" apply
python3 "$REPO/deploy/patch_dsh_directory_picker.py" apply
install -o root -g root -m 0755 "$REPO/deploy/user/dsh-launcher.py" /usr/local/libexec/huou07-dsh/user-launcher.py
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$HOME_DIR/.config/systemd/user"
for file in "$REPO"/deploy/user/*.service; do install -o "$USER_NAME" -g "$USER_NAME" -m 0644 "$file" "$HOME_DIR/.config/systemd/user/$(basename "$file")"; done
userctl daemon-reload
userctl enable "${USER_UNITS[@]}"
userctl start huou07-litellm-db.service huou07-litellm.service huou07-omniroute.service huou07-opencode-web.service huou07-dsh.service

port=$(python3 "$REPO/web/private_services.py" --port dsh backend_port)
ready=0
for _ in $(seq 1 180); do
  if curl -fsS --max-time 2 http://127.0.0.1:4000/health/liveliness >/dev/null 2>&1 && curl -fsS --max-time 2 http://127.0.0.1:20128/healthz >/dev/null 2>&1 && curl -fsS --max-time 2 "http://127.0.0.1:$port/favicon.svg" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[[ $ready == 1 ]] || fail 'LiteLLM, OmniRoute, or DSH health check did not pass'
opencode_status=$(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:4096/)
[[ $opencode_status == 200 || $opencode_status == 401 || $opencode_status == 403 ]] || fail "OpenCode Web HTTP $opencode_status"
userctl start huou07-playground.service
curl -fsS --max-time 3 http://127.0.0.1:8765/api/health >/dev/null
check_dashboard_wireguard
userctl is-active huou07-playground.service >/dev/null
for unit in "${USER_UNITS[@]}"; do userctl is-active "$unit" >/dev/null; userctl is-enabled "$unit" >/dev/null; done
main_pid=$(userctl show -p MainPID --value huou07-playground.service)
[[ $(ps -o user= -p "$main_pid" | xargs) == "$USER_NAME" ]] || fail 'dashboard process is not owned by huou07'

cutover_success=1
trap - EXIT
echo "Cutover passed local health checks. Private backup: $backup"
echo 'Original accounts, service homes, PostgreSQL volume, source app data, and units are retained; legacy units are stopped.'
echo 'No provider/model request was made. Verify sign-ins and persistence; do not clean legacy state without separate owner approval.'
