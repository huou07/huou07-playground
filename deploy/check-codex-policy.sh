#!/bin/sh
set -eu

if ! command -v codex >/dev/null 2>&1; then
  echo "Codex CLI must be available in PATH." >&2
  exit 1
fi
if [ ! -r /etc/codex/requirements.toml ]; then
  echo "The managed Codex requirements file is missing or unreadable." >&2
  exit 1
fi

umask 077
mkdir -p "$HOME/.cache"
workspace=$(mktemp -d "$HOME/.cache/huou07-codex-check.XXXXXX")
canary=$(mktemp "$HOME/.huou07-codex-canary.XXXXXX")
cleanup() {
  rm -rf "$workspace"
  rm -f "$canary"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
printf 'outside-workspace-canary\n' > "$canary"

codex sandbox --permission-profile huou07_workspace --include-managed-config --cd "$workspace" -- sh -c 'printf inside-ok > "$1"; test "$(cat "$1")" = inside-ok' sh "$workspace/inside.txt" >/dev/null
echo "Workspace write: PASS"

if codex sandbox --permission-profile huou07_workspace --include-managed-config --cd "$workspace" -- cat "$canary" >/dev/null 2>&1; then
  echo "Home-directory read was unexpectedly allowed." >&2
  exit 1
fi
echo "Home-directory read: BLOCKED"

if codex sandbox --permission-profile :danger-full-access --include-managed-config --cd "$workspace" -- cat "$canary" >/dev/null 2>&1; then
  echo "An unapproved full-access profile exposed the canary." >&2
  exit 1
fi
echo "Full-access override: BLOCKED"
