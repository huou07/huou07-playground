#!/usr/bin/env python3
"""Write the AEH gate report the Hub reads from `.hub/gate-report.json`.

Rows come from tools/acceptance.sh as tab-separated lines:

    covered<TAB>gate-name
    skipped<TAB>check<TAB>reason
    not_run<TAB>check<TAB>reason
    artifact<TAB>name<TAB>path<TAB>sha256<TAB>platform<TAB>result
    limitation<TAB>text

The report shape is fixed by section 4 of the AEH quality interface. AEH only
reads this file and never executes it. The file is runtime state: `.hub/` is
gitignored. A missing or malformed report is the caller's problem, not a pass;
this helper makes no claim about whether a check ran.
"""
import argparse
import json
from pathlib import Path


def parse_rows(text):
    report = {
        "skipped": [],
        "not_run": [],
        "covered_gates": [],
        "artifacts": [],
        "limitations": [],
    }
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        kind = parts[0]
        if kind == "covered" and len(parts) == 2:
            report["covered_gates"].append(parts[1])
        elif kind in ("skipped", "not_run") and len(parts) == 3:
            report[kind].append({"check": parts[1], "reason": parts[2]})
        elif kind == "artifact" and len(parts) == 6:
            report["artifacts"].append({
                "name": parts[1],
                "path": parts[2],
                "sha256": parts[3] or None,
                "platform": parts[4],
                "result": parts[5],
            })
        elif kind == "limitation" and len(parts) == 2:
            report["limitations"].append(parts[1])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner-os", default="linux")
    parser.add_argument("--runner-arch", default="unknown")
    parser.add_argument("--runner-label", default="local")
    parser.add_argument("--evidence-class", default="VERIFIED_SOURCE")
    args = parser.parse_args()

    report = parse_rows(args.input.read_text(encoding="utf-8", errors="replace"))
    report["runner"] = {
        "kind": "local",
        "os": args.runner_os,
        "arch": args.runner_arch,
        "label": args.runner_label,
        "run_url": None,
        "run_id": None,
        "job": None,
    }
    report["evidence_class"] = args.evidence_class

    ordered = {
        "skipped": report["skipped"],
        "not_run": report["not_run"],
        "covered_gates": report["covered_gates"],
        "artifacts": report["artifacts"],
        "runner": report["runner"],
        "evidence_class": report["evidence_class"],
        "limitations": report["limitations"],
    }
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
    print(f"gate report: {args.output}")


if __name__ == "__main__":
    main()
