#!/usr/bin/env bash
# H07P admission gate.
#
# Scope: the source gate the Hub runs (`make check`) plus the Rust lanes that
# GitHub Actions runs and that `make check` never did. The product is the Rust
# server, so a Python-only pass is not acceptance.
#
# Anything needing a disposable guest, root, /dev/kvm, a .deb install or the
# browser matrix stays the authority of CI and the owner's lab; it is not
# simulated here.
#
# Usage: tools/acceptance.sh [--full] [--timeout N]
#   --full  also build the workspace in release mode (slow; CI also does this)
set -uo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT" || exit 1

CHECK_TIMEOUT=900
FULL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --full) FULL=1; shift ;;
    --timeout) CHECK_TIMEOUT=${2:?}; shift 2 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

failed=0
run() {
  local name=$1; shift
  printf '\n== %s ==\n' "$name"
  local rc=0
  timeout --signal=TERM --kill-after=30 "${CHECK_TIMEOUT}s" "$@" || rc=$?
  case "$rc" in
    0) printf 'RESULT: PASS — %s\n' "$name" ;;
    124|137) printf 'RESULT: FAIL (timeout %ss) — %s\n' "$CHECK_TIMEOUT" "$name"; failed=1 ;;
    *) printf 'RESULT: FAIL (exit %s) — %s\n' "$rc" "$name"; failed=1 ;;
  esac
}

if ! command -v cargo >/dev/null 2>&1; then
  printf 'RESULT: UNVERIFIED — cargo is not installed, so the Rust product lanes did not run\n'
  exit 3
fi

# The checked-out target/ cache was built by another UID and its file ACLs deny
# this worker, so cargo fails with "failed to link or copy". Use a per-worker
# target directory, the documented remedy for the shared-cache gap; CI keeps the
# default. Set CARGO_TARGET_DIR explicitly to opt out.
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$ROOT/.h07p-dev/target-uid$(id -u)}"
printf 'cargo target dir: %s\n' "$CARGO_TARGET_DIR"

run 'Source gate: Python reference, deploy scripts and tests (make check)' \
  make check
run 'Rust formatting' cargo fmt --all -- --check
run 'Rust lints (clippy, warnings are errors)' \
  cargo clippy --workspace --all-targets --locked -- -D warnings
run 'Rust workspace tests' cargo test --workspace --locked
if (( FULL )); then
  run 'Rust release build' cargo build --workspace --release --locked
else
  printf '\nRESULT: UNVERIFIED — release build not run (pass --full, or let CI run it)\n'
fi

printf '\nNOTE: guest isolation, .deb install/upgrade/purge, browser matrix and hosted\n'
printf '      acceptance remain CI/owner-lab authority and were not exercised here.\n'
if (( failed )); then
  printf '\nPROJECT_ACCEPTANCE=FAIL\n'
  exit 1
fi
printf '\nPROJECT_ACCEPTANCE=PASS\n'
