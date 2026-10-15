#!/usr/bin/env bash
# =============================================================================
# Delete the two leaked worker credential stores, after the keys have been
# revoked at the provider.
#
#   ./revoke-and-delete-credentials.sh            dry run — prints, changes nothing
#   ./revoke-and-delete-credentials.sh --fingerprint
#                                                 dry run + masked identifiers, so
#                                                 you can match the key in the
#                                                 provider console
#   ./revoke-and-delete-credentials.sh --apply --i-revoked-these-at-the-provider
#                                                 stop units, shred, restart
#
# IRREVERSIBLE BY DESIGN: no backup is written, because a backup would recreate
# the exact exposure being removed. Recovery is re-authentication, which creates
# a fresh credential — not restoration of the old file.
#
# ORDER MATTERS: revoke at the provider FIRST. Deleting a local file does not
# revoke anything; a key that was read must be assumed disclosed until the
# provider stops accepting it. Deleting first only risks losing track of which
# key still needs revoking.
#
# Restarting agent-workbench-dsh@3080.service ends the hosting DSH session.
# The service may come back needing a fresh login; that is expected.
# =============================================================================
set -euo pipefail

ACK="--i-revoked-these-at-the-provider"
DSH_UNIT="agent-workbench-dsh@3080.service"
OPENCODE_UNIT="agent-workbench-opencode-web.service"
WORKER_HOME="/home/agents-worker/.agent-workbench-runtime-v6"
TARGETS=(
  "${WORKER_HOME}/.dsh/.credentials.yaml"
  "${WORKER_HOME}/.opencode/data/opencode/auth.json"
)

MODE="dry-run"
FINGERPRINT=0
ACKED=0
for arg in "$@"; do
  case "$arg" in
    --apply)       MODE="apply" ;;
    --dry-run)     MODE="dry-run" ;;
    --fingerprint) FINGERPRINT=1 ;;
    "$ACK")        ACKED=1 ;;
    -h|--help)     sed -n '2,25p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [[ "$MODE" == "apply" && "$ACKED" != "1" ]]; then
  cat >&2 <<EOF
refusing to delete without acknowledgement.

  This is irreversible and takes agent-workbench-dsh@3080.service down.
  Revoke both keys at the provider first, then re-run:

    sudo ./revoke-and-delete-credentials.sh --apply ${ACK}
EOF
  exit 3
fi

run() {
  if [[ "$MODE" == "dry-run" ]]; then
    printf '  [dry-run] %s\n' "$*"
  else
    printf '  [exec]    %s\n' "$*"
    "$@"
  fi
}

need_root() {
  if [[ "$(id -u)" != "0" ]]; then echo "must run as root" >&2; exit 4; fi
}

# Masked identifier only. Opt-in, because even a prefix and suffix are a partial
# disclosure — justified only while the key is being revoked anyway.
fingerprint() {
  local f="$1"
  python3 - "$f" <<'PY'
import sys, hashlib
path = sys.argv[1]
data = open(path, "rb").read()
print(f"      size={len(data)}B  sha256={hashlib.sha256(data).hexdigest()[:16]}")
text = data.decode("utf-8", "replace").replace('"', " ").replace("'", " ")
for tok in [t for t in text.split() if len(t) >= 16][:4]:
    print(f"      {tok[:6]}...{tok[-4:]}   (length {len(tok)})")
PY
}

show_targets() {
  echo "== targets"
  local found=0
  for f in "${TARGETS[@]}"; do
    if [[ -e "$f" ]]; then
      found=1
      printf '  PRESENT  %6s B  %s  %s\n' \
        "$(stat -c '%s' "$f")" "$(stat -c '%U:%G %a' "$f")" "$f"
      [[ "$FINGERPRINT" == "1" ]] && fingerprint "$f"
    else
      printf '  absent                       %s\n' "$f"
    fi
  done
  if [[ "$found" == "0" ]]; then
    echo "  nothing to delete; both files are already gone."
  fi
}

stop_units() {
  echo "== stopping units (this ends the hosting DSH session)"
  run systemctl stop "$OPENCODE_UNIT"
  run systemctl stop "$DSH_UNIT"
}

shred_targets() {
  echo "== shredding"
  # Overwriting is best-effort: on SSDs with wear levelling, copy-on-write
  # filesystems or a snapshotting layer, the old blocks may survive. The real
  # protection is that the key is revoked and therefore worthless.
  local shredder=(rm -f --)
  command -v shred >/dev/null && shredder=(shred -u -z -n 1 --)
  for f in "${TARGETS[@]}"; do
    if [[ -e "$f" ]]; then
      # Re-check: a service may write the file again while shutting down.
      run "${shredder[@]}" "$f"
    else
      printf '  [skip]    already absent: %s\n' "$f"
    fi
  done
}

verify_gone() {
  echo "== verifying"
  local ok=0
  for f in "${TARGETS[@]}"; do
    if [[ -e "$f" ]]; then
      echo "  FAIL still present: $f"; ok=1
    else
      echo "  OK   gone: $f"
    fi
  done

  echo "== scanning for leftovers (names only, no file contents)"
  local leftovers
  leftovers="$(find "$WORKER_HOME" -maxdepth 6 \
      \( -name '.credentials.yaml*' -o -name 'auth.json*' -o -name '*.bak' \) \
      -not -path '*/node_modules/*' -printf '%p\n' 2>/dev/null || true)"
  if [[ -n "$leftovers" ]]; then
    printf '  WARN copies still on disk:\n%s\n' "$leftovers"
    ok=1
  else
    echo "  OK   no credential-named copies under ${WORKER_HOME}"
  fi

  local cores
  cores="$(find "$WORKER_HOME" -maxdepth 3 -type f \
      \( -name 'core' -o -name 'core.[0-9]*' \) -printf '%p\n' 2>/dev/null || true)"
  if [[ -n "$cores" ]]; then
    printf '  WARN core dumps present (they can contain the key in RAM):\n%s\n' "$cores"
    ok=1
  else
    echo "  OK   no core dumps"
  fi
  return "$ok"
}

start_units() {
  echo "== restarting units"
  run systemctl start "$DSH_UNIT"
  run systemctl start "$OPENCODE_UNIT"
  echo "   If DSH does not come up, it needs a fresh login. That is expected:"
  echo "   the credential store it used to read no longer exists."
}

report_followups() {
  cat <<'EOF'

== follow-ups (NOT done by this script)

  1. Codex session history may still contain the key in prompts or logs:
       /home/agents-worker/.agent-workbench-runtime-v6/.codex/logs_2.sqlite
       /home/agents-worker/.agent-workbench-runtime-v6/.codex/thread_history_1.sqlite
     Logging out does not scrub these; deleting them is a separate decision.

  2. Confirm at the provider that BOTH keys are revoked, not just deleted
     locally. This script removes bytes; it cannot revoke anything.

  3. Re-authenticate so a NEW key lands in the store. The exposure path (N1,
     same-UID worker) still exists, so the new key inherits the same risk until
     the broker separation is done.
EOF
}

for f in "${TARGETS[@]}"; do
  case "$f" in
    "$WORKER_HOME"/*) ;;
    *) echo "refusing: target outside worker home: $f" >&2; exit 5 ;;
  esac
done

if [[ "$MODE" == "dry-run" ]]; then
  echo "DRY RUN — nothing will be deleted."
  show_targets
  echo "== would then"
  echo "   systemctl stop  ${OPENCODE_UNIT} ${DSH_UNIT}"
  echo "   shred -u -z -n 1 -- <each present target>"
  echo "   verify absence + scan for copies"
  echo "   systemctl start ${DSH_UNIT} ${OPENCODE_UNIT}"
  if [[ "$FINGERPRINT" == "0" ]]; then
    echo "   (re-run with --fingerprint for masked key identifiers)"
  fi
else
  need_root
  show_targets
  stop_units
  shred_targets
  if verify_gone; then
    echo "== deletion verified"
  else
    echo "== WARNING: verification found leftovers; review the lines above" >&2
  fi
  start_units
  report_followups
fi
