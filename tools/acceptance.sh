#!/usr/bin/env bash
# H07P admission gate.
#
# Scope: the source gate the Hub runs (`make check`) plus the Rust lanes that
# GitHub Actions runs and that `make check` never did, the bounded performance
# budget, and (when node and node_modules are present) the browser matrix. The
# product is the Rust server, so a Python-only pass is not acceptance.
#
# Anything needing a disposable guest, root, /dev/kvm, a .deb install or a
# hosted runner stays the authority of CI and the owner's lab; it is not
# simulated here and it is reported as not_run, never as a silent pass.
#
# The run writes `.hub/gate-report.json` (the AEH gate report, section 4 of the
# AEH quality interface) so the Hub can read what this run covered and what it
# did not. `.hub/` is gitignored runtime state and writing it never changes the
# exit code below.
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

# --- AEH gate report ---------------------------------------------------------
# Rows are tab-separated records for tools/gate-report.py. A check that did not
# run is recorded in not_run with its real reason; a gate is recorded as covered
# only when its lane returned 0 in this run.
TAB=$'\t'
HUB_DIR="$ROOT/.hub"
REPORT="$HUB_DIR/gate-report.json"
PERF_OUTPUT="$HUB_DIR/product-measurement.json"
REPORT_ROWS=$(mktemp "${TMPDIR:-/tmp}/h07p-gate-rows.XXXXXX")
trap 'rm -f "$REPORT_ROWS"' EXIT HUP INT TERM
covered_gates=()
not_run_rows=()
artifact_rows=()
limitation_rows=()

add_covered() { covered_gates+=("$1"); }
add_not_run() { not_run_rows+=("not_run${TAB}$1${TAB}$2"); }
add_limitation() { limitation_rows+=("limitation${TAB}$1"); }
add_artifact() { artifact_rows+=("artifact${TAB}$1${TAB}$2${TAB}$3${TAB}$4${TAB}$5"); }

# Reasons for the lanes this script never exercises. They are the same limits
# the closing NOTE states, and the Hub reads them as coverage gaps.
HOSTED_REASON='hosted CI (the release-gate aggregate, the pinned Gitleaks secret scan and the .deb publication gates) runs on GitHub-hosted runners; a local run cannot provide hosted-runner evidence'
NATIVE_REASON='guest and worker isolation need a disposable guest or root with real worker accounts; this gate does not exercise them'
PACKAGE_REASON='the .deb install/upgrade/purge lifecycle needs a disposable dpkg root or a booted Debian systemd guest'

record_unavailable() {
  add_not_run 'source-integrity' "$1"
  add_not_run 'admission' "$1"
  add_not_run 'native-isolation' "$NATIVE_REASON"
  add_not_run 'package-lifecycle' "$PACKAGE_REASON"
  add_not_run 'hosted-acceptance' "$HOSTED_REASON"
}

emit_report() {
  {
    local name
    for name in "${covered_gates[@]:-}"; do [ -n "$name" ] && printf 'covered\t%s\n' "$name"; done
    for name in "${not_run_rows[@]:-}"; do [ -n "$name" ] && printf '%s\n' "$name"; done
    for name in "${artifact_rows[@]:-}"; do [ -n "$name" ] && printf '%s\n' "$name"; done
    for name in "${limitation_rows[@]:-}"; do [ -n "$name" ] && printf '%s\n' "$name"; done
  } > "$REPORT_ROWS" 2>/dev/null || return 0
  local source_sha arch os_id label
  source_sha=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)
  arch=$(uname -m 2>/dev/null || echo unknown)
  os_id=linux
  if [ -r /etc/os-release ]; then
    os_id=$(. /etc/os-release; printf '%s' "${ID:-linux}")
  fi
  label="$os_id-$arch"
  if [ -r /sys/class/dmi/id/product_name ] && grep -qi optiplex /sys/class/dmi/id/product_name 2>/dev/null; then
    label="$label-optiplex-class"
  fi
  python3 "$ROOT/tools/gate-report.py" \
    --input "$REPORT_ROWS" --output "$REPORT" \
    --runner-os "$os_id" --runner-arch "$arch" --runner-label "$label" \
    || printf 'WARN: could not write the AEH gate report to %s\n' "$REPORT"
}

failed=0
RUN_RC=0
run() {
  local name=$1; shift
  printf '\n== %s ==\n' "$name"
  local rc=0
  timeout --signal=TERM --kill-after=30 "${CHECK_TIMEOUT}s" "$@" || rc=$?
  RUN_RC=$rc
  case "$rc" in
    0) printf 'RESULT: PASS — %s\n' "$name" ;;
    124|137) printf 'RESULT: FAIL (timeout %ss) — %s\n' "$CHECK_TIMEOUT" "$name"; failed=1 ;;
    *) printf 'RESULT: FAIL (exit %s) — %s\n' "$rc" "$name"; failed=1 ;;
  esac
}

# Like run(), but exit 3 means the check could not be attempted on this host:
# UNVERIFIED, not a product failure and never a pass.
run_unverified() {
  local name=$1; shift
  printf '\n== %s ==\n' "$name"
  local rc=0
  timeout --signal=TERM --kill-after=30 "${CHECK_TIMEOUT}s" "$@" || rc=$?
  RUN_RC=$rc
  case "$rc" in
    0) printf 'RESULT: PASS — %s\n' "$name" ;;
    3) printf 'RESULT: UNVERIFIED — %s\n' "$name" ;;
    124|137) printf 'RESULT: FAIL (timeout %ss) — %s\n' "$CHECK_TIMEOUT" "$name"; failed=1 ;;
    *) printf 'RESULT: FAIL (exit %s) — %s\n' "$rc" "$name"; failed=1 ;;
  esac
}

if ! command -v cargo >/dev/null 2>&1; then
  printf 'RESULT: UNVERIFIED — cargo is not installed, so the Rust product lanes did not run\n'
  record_unavailable 'cargo is not installed, so the source gate and the Rust product lanes did not run'
  emit_report
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
  record_unavailable "CARGO_TARGET_DIR=$CARGO_TARGET_DIR is not writable by uid $(id -u)"
  emit_report
  exit 3
fi
rm -f "$CARGO_TARGET_DIR/.h07p-write-probe.$$"

run 'Source gate: Python reference, deploy scripts and tests (make check)' \
  make check
if [ "$RUN_RC" = 0 ]; then
  add_covered 'source-integrity'
fi
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
    add_not_run 'browser-matrix-rust' "no writable $ROOT/target/debug for tests/e2e/run.mjs"
  fi
else
  printf '\nRESULT: UNVERIFIED — browser lanes need node_modules (@playwright/test) and node\n'
  add_not_run 'browser-matrix' 'node_modules (@playwright/test) or node is absent, so the browser journeys did not run'
  add_limitation 'Browser journeys for the Python and Rust backends were not run in this invocation.'
fi

# Bounded performance budget: worst of three repeats for the Rust server process
# tree (peak RSS) and for one health and one dashboard request (p95 latency),
# compared with tools/performance-budget.json, which is calibrated on the named
# machine class. A budget that cannot be measured is UNVERIFIED, never a pass.
if [ -f "$ROOT/tools/performance-budget.json" ]; then
  if [ ! -x "$ROOT/target/debug/h07p-server" ] \
    && { [ -w "$ROOT/target" ] || mkdir -p "$ROOT/target" 2>/dev/null; }; then
    run 'Rust debug server for the performance budget' \
      env CARGO_TARGET_DIR="$ROOT/target" cargo build --locked -p h07p-server
  fi
  if [ -x "$ROOT/target/debug/h07p-server" ]; then
    run_unverified 'Performance budget: server RSS and dashboard latency' \
      python3 "$ROOT/tools/check-performance-budget.py" \
        --binary "$ROOT/target/debug/h07p-server" \
        --budget "$ROOT/tools/performance-budget.json" \
        --output "$PERF_OUTPUT"
    if [ "$RUN_RC" = 0 ] && [ -f "$PERF_OUTPUT" ]; then
      add_artifact 'product-measurement' '.hub/product-measurement.json' \
        "$(sha256sum "$PERF_OUTPUT" 2>/dev/null | awk '{print $1}')" 'linux-x64' 'PASS'
    elif [ "$RUN_RC" = 3 ]; then
      add_not_run 'performance-budget' 'the bounded measurement could not run on this host; see .hub/product-measurement.json'
    fi
  else
    printf '\nRESULT: UNVERIFIED — the performance budget needs an executable %s/target/debug/h07p-server\n' "$ROOT"
    add_not_run 'performance-budget' "no executable $ROOT/target/debug/h07p-server"
  fi
else
  printf '\nRESULT: UNVERIFIED — tools/performance-budget.json is absent\n'
  add_not_run 'performance-budget' 'tools/performance-budget.json is absent'
fi

# A produced debug binary is evidence this run really built; hash it for the report.
if [ -x "$ROOT/target/debug/h07p-server" ]; then
  add_artifact 'h07p-server-debug' 'target/debug/h07p-server' \
    "$(sha256sum "$ROOT/target/debug/h07p-server" 2>/dev/null | awk '{print $1}')" 'linux-x64' 'PASS'
fi

add_not_run 'native-isolation' "$NATIVE_REASON"
add_not_run 'package-lifecycle' "$PACKAGE_REASON"
add_not_run 'hosted-acceptance' "$HOSTED_REASON"
add_limitation 'The pinned Gitleaks secret scan and the .deb publication path run only in hosted CI; no local lane covers them.'
add_limitation 'No guest, VM, /dev/kvm or root lane ran here: kernel/DAC isolation and package lifecycle stay CI/owner-lab evidence.'
if (( failed == 0 )); then
  add_covered 'admission'
fi
emit_report

printf '\nNOTE: guest isolation, .deb install/upgrade/purge and hosted acceptance remain\n'
printf '      CI/owner-lab authority and were not exercised here.\n'
if (( failed )); then
  printf '\nPROJECT_ACCEPTANCE=FAIL\n'
  exit 1
fi
printf '\nPROJECT_ACCEPTANCE=PASS\n'
