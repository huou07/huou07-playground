#!/bin/sh
# Resolve a usable CARGO_HOME / CARGO_TARGET_DIR / PYTHONPYCACHEPREFIX for this
# checkout and caller.
#
# The Hub verify gate can run as a worker that owns neither this checkout nor the
# ambient caches, and `test -w` is not enough on ACL-managed trees (the ACL can
# grant write on the directory while a new file is still denied). Probe for real
# writability by creating and removing a file, then fall back:
#
#   target dir: an explicit writable CARGO_TARGET_DIR -> $repo/target ->
#               $repo/.h07p-dev/target-uid<uid> -> ${TMPDIR:-/tmp}/h07p-target-uid<uid>
#   cargo home: an explicit writable CARGO_HOME -> $HOME/.cargo ->
#               $repo/.h07p-dev/cargo-home
#   pycache:    an explicit writable PYTHONPYCACHEPREFIX -> $repo/.h07p-dev/pycache
#               -> ${TMPDIR:-/tmp}/h07p-pycache-uid<uid>
#
# Usage: tools/cargo-env.sh target-dir|cargo-home|pycache-prefix
set -eu

repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

probe_dir() {
  [ -n "$1" ] || return 1
  mkdir -p "$1" 2>/dev/null || return 1
  probe="$1/.h07p-write-probe.$$"
  (umask 077; : > "$probe") 2>/dev/null || return 1
  rm -f "$probe" 2>/dev/null || true
  return 0
}

case "${1:-}" in
  target-dir)
    if probe_dir "${CARGO_TARGET_DIR:-}"; then
      printf '%s\n' "$CARGO_TARGET_DIR"
    elif probe_dir "$repo/target"; then
      printf '%s\n' "$repo/target"
    elif probe_dir "$repo/.h07p-dev/target-uid$(id -u)"; then
      printf '%s\n' "$repo/.h07p-dev/target-uid$(id -u)"
    else
      printf '%s\n' "${TMPDIR:-/tmp}/h07p-target-uid$(id -u)"
    fi
    ;;
  cargo-home)
    if probe_dir "${CARGO_HOME:-}"; then
      printf '%s\n' "$CARGO_HOME"
    elif probe_dir "${HOME:-}/.cargo"; then
      printf '%s\n' "${HOME}/.cargo"
    elif [ -d "$repo/.h07p-dev/cargo-home" ]; then
      printf '%s\n' "$repo/.h07p-dev/cargo-home"
    else
      printf '%s\n' "${CARGO_HOME:-${HOME:-/nonexistent}/.cargo}"
    fi
    ;;
  pycache-prefix)
    if probe_dir "${PYTHONPYCACHEPREFIX:-}"; then
      printf '%s\n' "$PYTHONPYCACHEPREFIX"
    elif probe_dir "$repo/.h07p-dev/pycache"; then
      printf '%s\n' "$repo/.h07p-dev/pycache"
    else
      printf '%s\n' "${TMPDIR:-/tmp}/h07p-pycache-uid$(id -u)"
    fi
    ;;
  *)
    printf 'usage: tools/cargo-env.sh target-dir|cargo-home|pycache-prefix\n' >&2
    exit 2
    ;;
esac
