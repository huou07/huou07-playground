#!/usr/bin/env python3
"""Apply the deployment's workspace allowlist to the pinned DSH policy."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PACKAGE = Path("/opt/huou07-dsh/app/node_modules/@deepseek-ai/dsh-sandbox-policy")
POLICY = PACKAGE / "lib/index.js"
EXPECTED_VERSION = "0.2.0-rc.2"
OLD_IMPORT = 'import { isAbsolute } from "node:path";'
NEW_IMPORT = 'import { realpathSync } from "node:fs";\nimport { isAbsolute, relative, resolve } from "node:path";'
OLD_FUNCTION = '''function resolveWorkspaceRoot(path) {
	if (!isAbsolute(path)) throw new Error("sandbox-policy: workspace root must be an absolute execution-world path");
	return path;
}'''
NEW_FUNCTION = '''function resolveWorkspaceRoot(path) {
	if (!isAbsolute(path)) throw new Error("sandbox-policy: workspace root must be an absolute execution-world path");
	let canonical;
	try {
		canonical = realpathSync(resolve(path));
	} catch {
		throw new Error("sandbox-policy: workspace root must be an existing approved workspace directory");
	}
	const approvedRoot = "/srv/huou07-dsh-workspaces";
	const relativePath = relative(approvedRoot, canonical);
	if (relativePath === ".." || relativePath.startsWith(`..${process.platform === "win32" ? "\\\\" : "/"}`) || isAbsolute(relativePath)) {
		throw new Error("sandbox-policy: workspace root is outside /srv/huou07-dsh-workspaces");
	}
	return canonical;
}'''
OLD_EXPORT = 'export { SANDBOX_MODES, SandboxPolicyService, SandboxPolicyService as default, setSandboxMode };'
NEW_EXPORT = 'export { SANDBOX_MODES, SandboxPolicyService, SandboxPolicyService as default, setSandboxMode, resolveWorkspaceRoot };'


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch-dsh-workspace-policy.py check|apply", file=sys.stderr)
        return 2
    action = sys.argv[1]
    if action not in {"check", "apply"}:
        print("action must be check or apply", file=sys.stderr)
        return 2
    metadata = PACKAGE / "package.json"
    if not metadata.is_file() or json.loads(metadata.read_text())["version"] != EXPECTED_VERSION:
        print(f"expected pinned DSH sandbox policy {EXPECTED_VERSION}", file=sys.stderr)
        return 1
    source = POLICY.read_text()
    if OLD_IMPORT not in source and NEW_IMPORT not in source:
        print("unexpected DSH sandbox policy imports", file=sys.stderr)
        return 1
    if NEW_FUNCTION in source and NEW_IMPORT in source and NEW_EXPORT in source:
        return 0
    if OLD_FUNCTION not in source or OLD_IMPORT not in source or OLD_EXPORT not in source:
        print("unexpected DSH workspace-root policy source", file=sys.stderr)
        return 1
    if action == "check":
        print("DSH workspace policy needs its approved-root patch", file=sys.stderr)
        return 1
    POLICY.write_text(
        source.replace(OLD_IMPORT, NEW_IMPORT, 1)
        .replace(OLD_FUNCTION, NEW_FUNCTION, 1)
        .replace(OLD_EXPORT, NEW_EXPORT, 1)
    )
    print("DSH workspace policy now rejects roots outside the dedicated workspace tree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
