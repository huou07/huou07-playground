#!/usr/bin/env python3
"""Validate project documentation links and skill structure; no runtime claims."""
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "AGENTS.md", "docs/README.md", "docs/PRODUCT.md", "docs/ARCHITECTURE.md",
    "docs/SECURITY.md", "docs/UX.md", "docs/VALIDATION.md", "docs/ROADMAP.md",
    "docs/REUSE.md", "docs/SKILLS.md", "docs/AUDIT-2026-10-15.md",
    "docs/prompts/IMPLEMENT-H07P.md", "skills.md", "docs/WORKING.md", "docs/TOOLS.md",
)
SKILLS = {"h07p-isolation", "h07p-files", "h07p-efficiency-ci"}
errors = []
for name in REQUIRED:
    if not (ROOT / name).is_file():
        errors.append(f"Missing required document: {name}")
paths = [ROOT / name for name in REQUIRED if (ROOT / name).is_file()]
paths.append(ROOT / "README.md")
skill_paths = list((ROOT / ".agents/skills").glob("*/SKILL.md"))
if {p.parent.name for p in skill_paths} != SKILLS:
    errors.append("Project skill inventory differs from routing contract")
paths.extend(skill_paths)
for path in paths:
    content = path.read_text(encoding="utf-8")
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", content):
        target = match.group(1).strip().strip("<>")
        url = urlsplit(target)
        if url.scheme or url.netloc or not url.path:
            continue
        # Optional host catalog: not installed or claimed verified on hosted CI.
        if target == "/srv/agent-workbench/skills.md":
            continue
        resolved = (path.parent / unquote(url.path)).resolve()
        if not resolved.is_relative_to(ROOT) or not resolved.exists():
            errors.append(f"{path.relative_to(ROOT)}: missing/outside link {target}")
    if path.name == "SKILL.md":
        metadata = re.match(r"\A---\nname: ([a-z0-9-]+)\ndescription: ([^\n]+)\n---\n", content)
        if not metadata or metadata.group(1) != path.parent.name:
            errors.append(f"{path.relative_to(ROOT)}: invalid skill metadata")
        if "## Procedure" not in content or "## Completion and output" not in content:
            errors.append(f"{path.relative_to(ROOT)}: missing skill procedure/output")
        if f".agents/skills/{path.parent.name}/SKILL.md" not in (ROOT / "skills.md").read_text():
            errors.append(f"{path.relative_to(ROOT)}: absent from routing catalog")
if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
print(f"Framework structure OK: {len(paths)} documents/skills; runtime and discovery unverified.")
