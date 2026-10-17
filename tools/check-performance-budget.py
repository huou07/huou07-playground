#!/usr/bin/env python3
"""Enforce the bounded H07P performance budget for the named machine class.

Runs tools/measure-product.py (bounded /proc measurement of the launched process
tree) against the Rust server and compares the worst repeat with the calibrated
budgets in tools/performance-budget.json. Endpoint ordinals follow the
measure-product.py default endpoint list: 0 = /api/health, 1 = / (dashboard).

Exit codes: 0 the budget held, 1 the budget was exceeded, 2 usage error,
3 the measurement could not run (UNVERIFIED, never a silent pass).
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ENDPOINTS = {"0": "/api/health", "1": "/"}


def worst(values):
    return max(values) if values else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--idle-seconds", type=float, default=5)
    parser.add_argument("--port", type=int, default=18767)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    measure = root / "tools" / "measure-product.py"
    reference = root / "web" / "app.py"
    binary = args.binary.resolve()

    if not measure.is_file() or not reference.is_file():
        print("UNVERIFIED: tools/measure-product.py or web/app.py is missing")
        return 3
    if not binary.is_file():
        print(f"UNVERIFIED: the Rust server binary is missing: {binary}")
        return 3
    try:
        budget = json.loads(args.budget.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"UNVERIFIED: tools/performance-budget.json is unreadable ({error})")
        return 3
    limits = budget.get("budgets") or {}

    workdir = Path(tempfile.mkdtemp(prefix="h07p-perf-budget-"))
    raw = workdir / "measurement.json"
    command = [
        sys.executable, str(measure),
        "--python-reference", str(reference),
        "--rust-command", json.dumps([str(binary)]),
        "--port", str(args.port),
        "--idle-seconds", str(args.idle_seconds),
        "--requests", str(args.requests),
        "--repeats", str(args.repeats),
        "--output", str(raw),
    ]
    try:
        completed = subprocess.run(command, cwd=str(root), capture_output=True,
                                   text=True, timeout=290, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        shutil.rmtree(workdir, ignore_errors=True)
        print(f"UNVERIFIED: the bounded measurement could not complete ({type(error).__name__})")
        return 3
    if completed.returncode != 0 or not raw.is_file():
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()[-3:]
        shutil.rmtree(workdir, ignore_errors=True)
        print("UNVERIFIED: tools/measure-product.py exited "
              f"{completed.returncode}: {' | '.join(tail)}")
        return 3

    report = json.loads(raw.read_text(encoding="utf-8"))
    shutil.rmtree(workdir, ignore_errors=True)
    runs = report.get("rust") or []
    if not runs:
        print("UNVERIFIED: the measurement report carries no Rust run")
        return 3

    measured = {
        "rust_peak_rss_bytes": worst([row["peak_tree_rss_bytes"] for row in runs]),
        "health_p95_ms": worst([row["endpoints"][name]["p95_ms"]
                                for row in runs for name in ("0",) if name in row["endpoints"]]),
        "dashboard_p95_ms": worst([row["endpoints"][name]["p95_ms"]
                                   for row in runs for name in ("1",) if name in row["endpoints"]]),
        "idle_cpu_seconds": worst([row["idle_cpu_seconds"] for row in runs]),
        "repeats": [
            {
                "peak_tree_rss_bytes": row["peak_tree_rss_bytes"],
                "idle_cpu_seconds": row["idle_cpu_seconds"],
                "latency_p95_ms": {name: row["endpoints"][name]["p95_ms"]
                                   for name in sorted(row["endpoints"])},
            }
            for row in runs
        ],
    }

    failures = []
    for key, budget_key in (("rust_peak_rss_bytes", "rust_peak_rss_bytes"),
                            ("health_p95_ms", "health_p95_ms"),
                            ("dashboard_p95_ms", "dashboard_p95_ms")):
        limit = limits.get(budget_key)
        value = measured[key]
        if not isinstance(limit, (int, float)):
            failures.append(f"budget {budget_key} is not a number")
        elif value is None:
            failures.append(f"measurement {key} is unavailable")
        elif value > limit:
            failures.append(f"{key}={value} exceeds budget {budget_key}={limit}")

    verdict = "FAIL" if failures else "PASS"
    evidence = {
        "schema": 1,
        "verdict": verdict,
        "machine_class": budget.get("machine_class"),
        "source_sha": report.get("source_sha"),
        "source_dirty": report.get("source_dirty"),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "workload": {
            "idle_seconds": args.idle_seconds,
            "requests": args.requests,
            "repeats": args.repeats,
            "port": args.port,
            "endpoints": ENDPOINTS,
        },
        "budgets": limits,
        "measured": measured,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    for failure in failures:
        print(f"BUDGET EXCEEDED: {failure}")
    print(f"PERFORMANCE_BUDGET={verdict} ({args.output})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
