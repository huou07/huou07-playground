#!/usr/bin/env bash
# =============================================================================
# H07P security hardening installer — N2 (core dump) + N3 (same-UID memory)
#
# Owner-run only. This script edits system service units and host sysctls; it
# must be executed by the owner with root, not by an agent session.
#
#   ./apply.sh                 dry run — prints every action, changes nothing
#   ./apply.sh --apply         install, reload, restart, verify, auto-rollback
#   ./apply.sh --rollback      remove everything this script installed
#
# Requires the acknowledgement flag below, because restarting
# agent-workbench-dsh@3080.service terminates the DSH session that is currently
# hosting the conversation. Apply it when you are ready to lose that session.
#
# Deliberately does NOT touch: credentials, owner ACLs, /home/huou07/Projects,
# libvirt, or any other unit.
# =============================================================================
set -euo pipefail

ACK_FLAG="--i-understand-this-restarts-dsh"
DSH_UNIT="agent-workbench-dsh@3080.service"
OPENCODE_UNIT="agent-workbench-opencode-web.service"
SYSCTL_NAME="60-agent-ptrace-scope.conf"
DROPIN_NAME="70-memory-exfil-hardening.conf"

SRC_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MODE="dry-run"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="/var/backups/h07p-security-hardening/${STAMP}"

for arg in "$@"; do
  case "$arg" in
    --apply)    MODE="apply" ;;
    --rollback) MODE="rollback" ;;
    --dry-run)  MODE="dry-run" ;;
    "$ACK_FLAG") ;; # handled below
    -h|--help)  sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [[ "$MODE" == "apply" ]]; then
  for arg in "$@"; do
    if [[ "$arg" == "$ACK_FLAG" ]]; then ACKED=1; fi
  done
  if [[ "${ACKED:-0}" != "1" ]]; then
    cat >&2 <<EOF
refusing to apply without acknowledgement.

  Applying this restarts ${DSH_UNIT}, which kills the DSH session
  that is hosting the current conversation.

  Re-run with:  sudo ./apply.sh --apply ${ACK_FLAG}
EOF
    exit 3
  fi
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
  if [[ "$(id -u)" != "0" ]]; then
    echo "must run as root" >&2
    exit 4
  fi
}

assert_parses() {
  # systemd ignores unresolvable SystemCallFilter entries silently, so an
  # installed-and-active unit is not evidence that the filter works. Parse the
  # exact line we are about to install and refuse on any ignored entry.
  local tmp filter out
  tmp="$(mktemp -d)"
  filter="$(grep -m1 '^SystemCallFilter=' "$SRC_DIR/systemd/$DROPIN_NAME" || true)"
  if [[ -z "$filter" ]]; then
    echo "  FAIL no SystemCallFilter= line found in $DROPIN_NAME" >&2
    rm -rf "$tmp"; return 1
  fi
  {
    printf '[Unit]\nDescription=h07p SystemCallFilter syntax probe\n'
    printf '[Service]\nType=oneshot\n%s\nExecStart=/bin/true\n' "$filter"
  } > "$tmp/probe.service"
  out="$(systemd-analyze verify "$tmp/probe.service" 2>&1 \
         | grep -F "$tmp/probe.service" \
         | grep -E 'not known|Unknown|Failed to' || true)"
  rm -rf "$tmp"
  if [[ -n "$out" ]]; then
    echo "  FAIL SystemCallFilter does not parse cleanly:" >&2
    printf '    %s\n' "$out" >&2
    return 1
  fi
  echo "  OK   SystemCallFilter parses with no ignored entries"
}

install_artifacts() {
  local dsh_dir="/etc/systemd/system/${DSH_UNIT}.d"
  local opencode_dir="/etc/systemd/system/${OPENCODE_UNIT}.d"
  local sysctl_dst="/etc/sysctl.d/${SYSCTL_NAME}"

  echo "== pre-flight: parsing the drop-in"
  if ! assert_parses; then
    echo "refusing to install a filter systemd would silently ignore" >&2
    exit 6
  fi

  echo "== backing up current state to ${BACKUP_ROOT}"
  run mkdir -p "$BACKUP_ROOT"
  for f in "$dsh_dir/$DROPIN_NAME" "$opencode_dir/$DROPIN_NAME" "$sysctl_dst"; do
    if [[ -e "$f" ]]; then
      run cp -a "$f" "$BACKUP_ROOT/$(echo "$f" | tr '/' '_')"
    fi
  done

  echo "== installing systemd drop-in into both units"
  run mkdir -p "$dsh_dir" "$opencode_dir"
  run install -m 0644 -o root -g root \
    "$SRC_DIR/systemd/$DROPIN_NAME" "$dsh_dir/$DROPIN_NAME"
  run install -m 0644 -o root -g root \
    "$SRC_DIR/systemd/$DROPIN_NAME" "$opencode_dir/$DROPIN_NAME"

  echo "== installing sysctl drop-in"
  run install -m 0644 -o root -g root \
    "$SRC_DIR/sysctl/$SYSCTL_NAME" "$sysctl_dst"

  echo "== reloading"
  run systemctl daemon-reload
  run sysctl --system

  echo "== restarting units (this ends the hosting DSH session)"
  run systemctl restart "$DSH_UNIT"
  run systemctl restart "$OPENCODE_UNIT"
}

verify() {
  echo "== verifying"
  local ok=0

  for u in "$DSH_UNIT" "$OPENCODE_UNIT"; do
    if [[ "$(systemctl is-active "$u" || true)" == "active" ]]; then
      echo "  OK   $u active"
    else
      echo "  FAIL $u not active"; ok=1
    fi
    local core
    core="$(systemctl show "$u" -p LimitCORE --value || true)"
    if [[ "$core" == "0" ]]; then
      echo "  OK   $u LimitCORE=0"
    else
      echo "  FAIL $u LimitCORE=$core"; ok=1
    fi
  done

  local scope
  scope="$(cat /proc/sys/kernel/yama/ptrace_scope 2>/dev/null || echo '?')"
  if [[ "$scope" == "1" ]]; then echo "  OK   ptrace_scope=1"
  else echo "  FAIL ptrace_scope=$scope"; ok=1; fi

  # systemd silently drops malformed SystemCallFilter entries, so checking that
  # the unit is active proves nothing about the filter. Assert every syscall we
  # intend to deny is actually present in the effective value.
  for u in "$DSH_UNIT" "$OPENCODE_UNIT"; do
    local filter missing=""
    filter="$(systemctl show "$u" -p SystemCallFilter --value || true)"
    for sc in ptrace process_vm_readv process_vm_writev pidfd_getfd kcmp; do
      [[ "$filter" == *"$sc"* ]] || missing="$missing $sc"
    done
    if [[ -z "$missing" ]]; then
      echo "  OK   $u SystemCallFilter covers all denied syscalls"
    else
      echo "  FAIL $u SystemCallFilter missing:$missing"; ok=1
    fi
  done

  # Positive journey: the portal must still answer, and answer with the token
  # redirect rather than an error. 503 here means the launch-token chain broke.
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:3080/ || true)"
  case "$code" in
    302|401) echo "  OK   localhost:3080 -> HTTP $code" ;;
    *)       echo "  FAIL localhost:3080 -> HTTP ${code:-none}"; ok=1 ;;
  esac

  return "$ok"
}

rollback() {
  local dsh_dir="/etc/systemd/system/${DSH_UNIT}.d"
  local opencode_dir="/etc/systemd/system/${OPENCODE_UNIT}.d"
  echo "== removing installed artifacts"
  run rm -f "$dsh_dir/$DROPIN_NAME" "$opencode_dir/$DROPIN_NAME" \
           "/etc/sysctl.d/${SYSCTL_NAME}"
  run systemctl daemon-reload
  run sysctl --system
  run systemctl restart "$DSH_UNIT"
  run systemctl restart "$OPENCODE_UNIT"
  echo "== done. Restore any backup from /var/backups/h07p-security-hardening/ if needed."
}

case "$MODE" in
  dry-run)
    echo "DRY RUN — nothing will change. Re-run with --apply ${ACK_FLAG}"
    install_artifacts
    echo "== verification that would run after restart"
    echo "   systemctl is-active ${DSH_UNIT} ${OPENCODE_UNIT}"
    echo "   systemctl show -p LimitCORE ${DSH_UNIT}"
    echo "   cat /proc/sys/kernel/yama/ptrace_scope   # expect 1"
    echo "   curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3080/   # expect 302"
    ;;
  apply)
    need_root
    install_artifacts
    if verify; then
      echo "== SUCCESS"
    else
      echo "== VERIFICATION FAILED — rolling back" >&2
      rollback || true
      exit 5
    fi
    ;;
  rollback)
    need_root
    rollback
    ;;
esac
