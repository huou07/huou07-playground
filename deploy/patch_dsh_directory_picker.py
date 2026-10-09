#!/usr/bin/env python3
"""Limit DSH's web directory picker to the dedicated agent workspace."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PACKAGE = Path("/opt/huou07-dsh/app/node_modules/@deepseek-ai/dsh-host-directory-picker-browse")
SOURCE = PACKAGE / "lib/index.js"
VERSION = "0.2.0-rc.2"
ROOT = "/srv/huou07-dsh-workspaces"

REPLACEMENTS = (
    (
        'import { mkdir, opendir, stat } from "node:fs/promises";',
        'import { mkdir, opendir, realpath, stat } from "node:fs/promises";',
    ),
    (
        'import { basename, dirname, join, posix, resolve, win32 } from "node:path";',
        'import { basename, dirname, isAbsolute, join, posix, relative, resolve, sep, win32 } from "node:path";',
    ),
    (
        """/** The `ctx.directoryPicker` browse implementation (stable capability object per service life). */
var BrowseDirectoryPicker = class extends DirectoryPicker {""",
        f'''/** The `ctx.directoryPicker` browse implementation (stable capability object per service life). */
function isWithinWorkspace(path) {{
\tconst relativePath = relative("{ROOT}", path);
\treturn relativePath === "" || (relativePath !== ".." && !relativePath.startsWith(`..${{sep}}`) && !isAbsolute(relativePath));
}}
var BrowseDirectoryPicker = class extends DirectoryPicker {{''',
    ),
    ("\t\tconst home = homedir();", f'\t\tconst home = "{ROOT}";'),
    (
        "\t\tconst target = resolve(path ?? home);",
        '''\t\tlet target = resolve(path ?? home);
\t\ttry {
\t\t\ttarget = await realpath(target);
\t\t} catch (error) {
\t\t\tthrow new DirectoryPickerError("directory-unreadable", target, `cannot list ${target}: ${messageOf(error)}`);
\t\t}
\t\tif (!isWithinWorkspace(target)) throw new DirectoryPickerError("directory-unreadable", target, `cannot list ${target}: outside the approved workspace`);''',
    ),
    (
        "\t\tconst parent = resolve(path);",
        '''\t\tlet parent = resolve(path);
\t\ttry {
\t\t\tparent = await realpath(parent);
\t\t} catch (error) {
\t\t\tthrow new DirectoryPickerError("directory-create-failed", parent, `cannot create under ${parent}: ${messageOf(error)}`);
\t\t}
\t\tif (!isWithinWorkspace(parent)) throw new DirectoryPickerError("directory-create-failed", parent, `cannot create under ${parent}: outside the approved workspace`);''',
    ),
)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"check", "apply"}:
        print("usage: patch_dsh_directory_picker.py check|apply", file=sys.stderr)
        return 2
    action = sys.argv[1]
    metadata = PACKAGE / "package.json"
    if not metadata.is_file() or json.loads(metadata.read_text())["version"] != VERSION:
        print(f"expected pinned DSH directory picker {VERSION}", file=sys.stderr)
        return 1
    source = SOURCE.read_text()
    if all(new in source for _, new in REPLACEMENTS):
        return 0
    if any(old not in source for old, _ in REPLACEMENTS):
        print("unexpected DSH directory-picker source", file=sys.stderr)
        return 1
    if action == "check":
        print("DSH directory picker needs its approved-root patch", file=sys.stderr)
        return 1
    for old, new in REPLACEMENTS:
        source = source.replace(old, new, 1)
    SOURCE.write_text(source)
    print("DSH web directory browsing is limited to the dedicated workspace tree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
