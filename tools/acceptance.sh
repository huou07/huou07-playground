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

# The Hub can run this gate as a worker that owns neither this checkout nor the
# ambient cargo cache, and `test -w` is not reliable on ACL-managed trees. Resolve
# both with a real writability probe; an explicit value wins only when usable.
CARGO_HOME=$(sh "$ROOT/tools/cargo-env.sh" cargo-home)
export CARGO_HOME
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$(sh "$ROOT/tools/cargo-env.sh" target-dir)}"
printf 'cargo home: %s\ncargo target dir: %s\n' "$CARGO_HOME" "$CARGO_TARGET_DIR"
if ! mkdir -p "$CARGO_TARGET_DIR" 2>/dev/null \
  || ! (umask 077; : > "$CARGO_TARGET_DIR/.h07p-write-probe.$$") 2>/dev/null; then
  printf 'RESULT: UNVERIFIED — CARGO_TARGET_DIR=%s is not writable by uid %s; point CARGO_TARGET_DIR at a writable path\n' \
    "$CARGO_TARGET_DIR" "$(id -u)"
  exit 3
fi
rm -f "$CARGO_TARGET_DIR/.h07p-write-probe.$$"

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

# Browser journeys run locally when node_modules and node are present; the Rust
# backend lane additionally needs the checkout's own target/debug path because
# tests/e2e/run.mjs launches $ROOT/target/debug/h07p-server. Anything unavailable
# stays UNVERIFIED, never a silent PASS.
if [ -f "$ROOT/node_modules/@playwright/test/package.json" ] && command -v node >/dev/null 2>&1; then
  # Playwright removes outputDir before a run. A test-results/ owned by another
  # account cannot be removed from a sticky-bit checkout, so point the local gate
  # at a writable per-uid directory in that case; CI keeps the default path its
  # browser-evidence artifact uploads.
  if [ -e "$ROOT/test-results" ] \
    && [ -n "$(find "$ROOT/test-results" -maxdepth 0 ! -user "$(id -un)" -print 2>/dev/null)" ]; then
    export HUOU07_E2E_OUTPUT_DIR="$ROOT/.h07p-dev/e2e-results-uid$(id -u)"
    printf 'e2e output dir: %s\n' "$HUOU07_E2E_OUTPUT_DIR"
  fi
  run 'Browser journeys (Python backend)' env HUOU07_E2E_BACKEND=python npm run test:e2e
  if [ -w "$ROOT/target" ] || mkdir -p "$ROOT/target" 2>/dev/null; then
    run 'Rust debug server for browser acceptance' \
      env CARGO_TARGET_DIR="$ROOT/target" cargo build --locked -p h07p-server
    run 'Browser journeys (Rust backend)' env HUOU07_E2E_BACKEND=rust npm run test:e2e
  else
    printf '\nRESULT: UNVERIFIED — Rust browser lane needs a writable %s/target/debug (run.mjs path)\n' "$ROOT"
  fi
else
  printf '\nRESULT: UNVERIFIED — browser lanes need node_modules (@playwright/test) and node\n'
fi

printf '\nNOTE: guest isolation, .deb install/upgrade/purge and hosted acceptance remain\n'
printf '      CI/owner-lab authority and were not exercised here.\n'
if (( failed )); then
  printf '\nPROJECT_ACCEPTANCE=FAIL\n'
  exit 1
fi
printf '\nPROJECT_ACCEPTANCE=PASS\n'
