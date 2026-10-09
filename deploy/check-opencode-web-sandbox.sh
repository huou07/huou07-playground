#!/bin/sh
set -eu

APP_USER=huou07-opencode
WORKSPACE_GROUP=huou07-opencode-workspaces
STATE_DIR=/var/lib/huou07-opencode
WORKSPACE_DIR=/srv/huou07-opencode-workspaces
SANDBOX=/usr/local/libexec/huou07-opencode/bash
BINARY=/usr/local/libexec/huou07-opencode/opencode
CONFIG=/var/lib/huou07-opencode/config/opencode/opencode.json
DENIED=/etc/huou07-playground/.opencode-boundary-canary

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this check with sudo so it can test the installed service account." >&2
  exit 1
fi
if ! id "$APP_USER" >/dev/null 2>&1 || [ ! -d "$WORKSPACE_DIR" ] || [ ! -d "$STATE_DIR" ] || [ ! -x "$SANDBOX" ] || [ ! -x "$BINARY" ] || [ ! -f "$CONFIG" ]; then
  echo "The isolated OpenCode web sandbox is not installed." >&2
  exit 1
fi
owner=${SUDO_USER:-}
if [ -z "$owner" ] || [ "$owner" = root ]; then
  echo "Run this with sudo from the normal SSH owner's account." >&2
  exit 1
fi
owner_home=$(getent passwd "$owner" | cut -d: -f6)
canary=$(mktemp "$owner_home/.huou07-opencode-canary.XXXXXX")
project=$(runuser -u "$APP_USER" -- mktemp -d "$WORKSPACE_DIR/.boundary-project.XXXXXX")
sibling=$(runuser -u "$APP_USER" -- mktemp -d "$WORKSPACE_DIR/.boundary-sibling.XXXXXX")
worktree_repo=$(runuser -u "$APP_USER" -- mktemp -d "$WORKSPACE_DIR/.boundary-git.XXXXXX")
worktree_parent=$(runuser -u "$APP_USER" -- mktemp -d "$WORKSPACE_DIR/.boundary-worktrees.XXXXXX")
worktree=$worktree_parent/checkout
external_repo=$(runuser -u "$APP_USER" -- mktemp -d "$STATE_DIR/.boundary-git.XXXXXX")
external_worktree_parent=$(runuser -u "$APP_USER" -- mktemp -d "$WORKSPACE_DIR/.boundary-external-worktrees.XXXXXX")
external_worktree=$external_worktree_parent/checkout
state_probe=$(mktemp "$STATE_DIR/.boundary-state.XXXXXX")
DENIED=$(mktemp /etc/huou07-playground/.opencode-boundary-canary.XXXXXX)
rm -f "$DENIED"
test_home=$(mktemp -d /tmp/huou07-opencode-config.XXXXXX)
chown "$APP_USER:$APP_USER" "$state_probe"
chmod 0600 "$state_probe"
chown "$APP_USER:$APP_USER" "$test_home"
trap 'rm -f "$canary" "$DENIED" "$state_probe"; rm -rf "$project" "$sibling" "$worktree_repo" "$worktree_parent" "$external_repo" "$external_worktree_parent" "$test_home"' EXIT HUP INT TERM
printf 'owner-home-canary\n' > "$canary"
chmod 0644 "$canary"
runuser -u "$APP_USER" -- sh -c 'printf sibling-canary > "$1/secret"' sh "$sibling"
runuser -u "$APP_USER" -- sh -c 'printf state-canary > "$1"' sh "$state_probe"
for repository in "$worktree_repo" "$external_repo"; do
  runuser -u "$APP_USER" -- git -C "$repository" init -q
  runuser -u "$APP_USER" -- git -C "$repository" config user.name 'Sandbox boundary test'
  runuser -u "$APP_USER" -- git -C "$repository" config user.email sandbox@example.invalid
  runuser -u "$APP_USER" -- sh -c 'printf seed > "$1/seed"' sh "$repository"
  runuser -u "$APP_USER" -- git -C "$repository" add seed
  runuser -u "$APP_USER" -- git -C "$repository" commit -qm seed
done
runuser -u "$APP_USER" -- git -C "$worktree_repo" worktree add -qb boundary "$worktree"
runuser -u "$APP_USER" -- git -C "$external_repo" worktree add -qb boundary "$external_worktree"
install -d -o "$APP_USER" -g "$APP_USER" -m 0700 "$test_home/config/opencode" "$test_home/data" "$test_home/state" "$test_home/cache"
install -o "$APP_USER" -g "$APP_USER" -m 0600 "$CONFIG" "$test_home/config/opencode/opencode.json"

systemd-run --quiet --wait --collect \
  --unit="huou07-opencode-boundary-$$" \
  --uid="$APP_USER" \
  --gid="$APP_USER" \
  --setenv=OPENCODE_SERVER_PASSWORD=disposable-canary \
  --property="SupplementaryGroups=$WORKSPACE_GROUP" \
  --property="WorkingDirectory=$project" \
  --property=NoNewPrivileges=yes \
  --property=PrivateDevices=yes \
  --property=PrivateTmp=yes \
  --property=ProtectSystem=strict \
  --property=ProtectHome=yes \
  --property="ReadWritePaths=$STATE_DIR $WORKSPACE_DIR" \
  "$SANDBOX" -l -c '
    shopt -s expand_aliases
    [[ -f ~/.bashrc ]] && source ~/.bashrc >/dev/null 2>&1 || true
    cd -- "$1"
    test -z "${OPENCODE_SERVER_PASSWORD-}"
    test ! -r "$2"
    test ! -r "$3"
    test ! -e "$4/secret"
    printf workspace-ok > workspace-write
    test "$(cat workspace-write)" = workspace-ok
    if touch "$5" 2>/dev/null; then
      echo "OpenCode shell can write outside its private state and workspace." >&2
      exit 22
    fi
  ' opencode "$project" "$canary" "$state_probe" "$sibling" "$DENIED"

systemd-run --quiet --wait --collect \
  --unit="huou07-opencode-git-boundary-$$" \
  --uid="$APP_USER" \
  --gid="$APP_USER" \
  --setenv=OPENCODE_SERVER_PASSWORD=disposable-canary \
  --property="SupplementaryGroups=$WORKSPACE_GROUP" \
  --property="WorkingDirectory=$worktree_repo" \
  --property=NoNewPrivileges=yes \
  --property=PrivateDevices=yes \
  --property=PrivateTmp=yes \
  --property=ProtectSystem=strict \
  --property=ProtectHome=yes \
  --property="ReadWritePaths=$STATE_DIR $WORKSPACE_DIR" \
  "$SANDBOX" -l -c '
    cd -- "$1"
    test -z "${OPENCODE_SERVER_PASSWORD-}"
    test ! -r "$2"
    test ! -r "$3"
    test ! -e "$4/secret"
    printf checkout-ok > checkout-write
    git add checkout-write
    git commit -qm sandbox-boundary-check
    test "$(git show HEAD:checkout-write)" = checkout-ok
  ' opencode "$worktree_repo" "$canary" "$state_probe" "$sibling"

systemd-run --quiet --wait --collect \
  --unit="huou07-opencode-worktree-boundary-$$" \
  --uid="$APP_USER" \
  --gid="$APP_USER" \
  --setenv=OPENCODE_SERVER_PASSWORD=disposable-canary \
  --property="SupplementaryGroups=$WORKSPACE_GROUP" \
  --property="WorkingDirectory=$worktree" \
  --property=NoNewPrivileges=yes \
  --property=PrivateDevices=yes \
  --property=PrivateTmp=yes \
  --property=ProtectSystem=strict \
  --property=ProtectHome=yes \
  --property="ReadWritePaths=$STATE_DIR $WORKSPACE_DIR" \
  "$SANDBOX" -l -c '
    cd -- "$1"
    test -z "${OPENCODE_SERVER_PASSWORD-}"
    test ! -r "$2"
    test ! -r "$3"
    test ! -e "$4/secret"
    printf worktree-ok > worktree-write
    git add worktree-write
    git commit -qm sandbox-boundary-check
    test "$(git show HEAD:worktree-write)" = worktree-ok
  ' opencode "$worktree" "$canary" "$state_probe" "$sibling"

if denial=$(systemd-run --quiet --wait --collect \
  --unit="huou07-opencode-external-git-boundary-$$" \
  --uid="$APP_USER" \
  --gid="$APP_USER" \
  --property="SupplementaryGroups=$WORKSPACE_GROUP" \
  --property="WorkingDirectory=$external_worktree" \
  --property=NoNewPrivileges=yes \
  --property=PrivateDevices=yes \
  --property=PrivateTmp=yes \
  --property=ProtectSystem=strict \
  --property=ProtectHome=yes \
  --property="ReadWritePaths=$STATE_DIR $WORKSPACE_DIR" \
  "$SANDBOX" -l -c 'exit 0' 2>&1); then
  echo "OpenCode accepted Git metadata outside its workspace." >&2
  exit 1
fi
printf '%s' "$denial" | grep -Fq "Git metadata must stay inside $WORKSPACE_DIR" || {
  printf '%s\n' "$denial" >&2
  echo "OpenCode rejected an external Git worktree for an unexpected reason." >&2
  exit 1
}

config_output=$(cd "$project" && runuser -u "$APP_USER" -- env HOME="$test_home" XDG_CONFIG_HOME="$test_home/config" XDG_DATA_HOME="$test_home/data" XDG_STATE_HOME="$test_home/state" XDG_CACHE_HOME="$test_home/cache" NO_COLOR=1 "$BINARY" debug config)
printf '%s' "$config_output" | python3 -c '
import json,sys
config=json.load(sys.stdin)
permissions=config.get("permission", {})
external=permissions.get("external_directory", {})
assert config.get("shell") == "/usr/local/libexec/huou07-opencode/bash"
assert external.get("/var/lib/huou07-opencode") == "deny"
assert external.get("/var/lib/huou07-opencode/**") == "deny"
'

echo "OpenCode sandbox passed: project files and Git worktrees are usable; owner home, service state, sibling workspaces, and server environment remain hidden; Git metadata outside the workspace is rejected."
