#!/usr/bin/env python3
"""Check framework references and declared routes; never execute product code."""
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "AGENTS.md", "docs/README.md", "docs/PRODUCT.md", "docs/ARCHITECTURE.md",
    "docs/IMPLEMENTATION.md", "docs/SECURITY.md", "docs/UX.md", "docs/VALIDATION.md",
    "docs/ROADMAP.md", "docs/REUSE.md", "docs/SKILLS.md", "docs/AUDIT-2026-10-15.md",
    "docs/prompts/IMPLEMENT-H07P.md", "skills.md", "docs/WORKING.md", "docs/TOOLS.md",
)
# Snapshot of canonical catalog reviewed 2026-10-15; no host paths required in CI.
SHARED = {
    "code-investigate", "project-bootstrap", "project-steward", "verify-debug",
    "sustained-repair", "security-review", "skill-maintainer", "ui-ux-review",
}
PROJECT = {"h07p-isolation", "h07p-files", "h07p-efficiency-ci"}
errors = []
for name in (*REQUIRED, "README.md", "tools/framework-routing.json"):
    if not (ROOT / name).is_file():
        errors.append(f"Missing required framework file: {name}")
if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)

paths = [ROOT / name for name in (*REQUIRED, "README.md")]
skill_paths = sorted((ROOT / ".agents/skills").glob("*/SKILL.md"))
if {p.parent.name for p in skill_paths} != PROJECT:
    errors.append("Project skill inventory differs from routing contract")
paths.extend(skill_paths)
router = (ROOT / "skills.md").read_text(encoding="utf-8")
agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
links = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
heading_cache = {}


def anchors(path):
    """GitHub-style heading IDs, including duplicate-heading suffixes."""
    if path not in heading_cache:
        found = set()
        counts = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
            if match:
                slug = re.sub(r"[^\w\- ]", "", match.group(1).lower()).replace(" ", "-")
                count = counts.get(slug, 0)
                counts[slug] = count + 1
                found.add(f"{slug}-{count}" if count else slug)
        heading_cache[path] = found
    return heading_cache[path]


for path in paths:
    content = path.read_text(encoding="utf-8")
    for match in links.finditer(content):
        target = match.group(1).strip().strip("<>")
        url = urlsplit(target)
        if url.scheme or url.netloc:
            continue
        if url.path == "/srv/agent-workbench/skills.md":
            continue  # Optional host catalog; never a CI discovery claim.
        resolved = (path.parent / unquote(url.path)).resolve() if url.path else path
        if not resolved.is_relative_to(ROOT) or not resolved.exists():
            errors.append(f"{path.relative_to(ROOT)}: missing/outside link {target}")
        elif url.fragment and resolved.suffix == ".md":
            if unquote(url.fragment) not in anchors(resolved):
                errors.append(f"{path.relative_to(ROOT)}: missing heading {target}")
    if path.name == "SKILL.md":
        metadata = re.match(r"\A---\nname: ([a-z0-9-]+)\ndescription: ([^\n]+)\n---\n", content)
        if not metadata or metadata.group(1) != path.parent.name:
            errors.append(f"{path.relative_to(ROOT)}: invalid skill metadata")
        elif "Excludes " not in metadata.group(2):
            errors.append(f"{path.relative_to(ROOT)}: missing neighboring exclusion")
        for section in ("## Procedure", "## Completion and output"):
            if section not in content:
                errors.append(f"{path.relative_to(ROOT)}: missing {section}")
        if f".agents/skills/{path.parent.name}/SKILL.md" not in router:
            errors.append(f"{path.relative_to(ROOT)}: absent from routing catalog")
        if path.parent.name in SHARED:
            errors.append(f"{path.relative_to(ROOT)}: shared body duplicated locally")

navigation = (
    "skills.md", "docs/WORKING.md", "docs/TOOLS.md", "docs/PRODUCT.md",
    "docs/ARCHITECTURE.md", "docs/IMPLEMENTATION.md", "docs/SECURITY.md",
    "docs/UX.md", "docs/VALIDATION.md", "docs/ROADMAP.md", "docs/REUSE.md",
    "docs/README.md",
)
for name in navigation:
    if f"]({name})" not in agents:
        errors.append(f"AGENTS.md: missing navigation link {name}")
if len(agents.splitlines()) > 40 or "## " in agents or re.search(r"^\s*\d+\.", agents, re.M):
    errors.append("AGENTS.md must remain a short navigation table, not a procedure")

for name in SHARED:
    row = re.search(rf"^\| {re.escape(name)} \| ([^|]+) \| ([^|]+) \|$", router, re.M)
    if not row or not all(cell.strip() for cell in row.groups()):
        errors.append(f"skills.md: missing shared trigger/exclusion row {name}")

try:
    routing = json.loads((ROOT / "tools/framework-routing.json").read_text(encoding="utf-8"))
    if routing.get("schema_version") != 1 or not routing.get("authority"):
        raise ValueError("Missing schema version or evidence limitation")
    cases = routing["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("Expected non-empty routing cases")
    ids, categories, covered = set(), set(), set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Route case must be an object")
        ident, category = case.get("id"), case.get("category")
        if not isinstance(ident, str) or not ident or ident in ids:
            raise ValueError("Case IDs must be unique non-empty strings")
        ids.add(ident)
        if category not in {"positive", "subtle", "negative", "no-skill"}:
            raise ValueError(f"{ident}: unsupported category")
        categories.add(category)
        if not isinstance(case.get("request"), str) or not case["request"].strip():
            raise ValueError(f"{ident}: missing request")
        for key in ("expected", "excluded"):
            if not isinstance(case.get(key), list) or any(
                not isinstance(name, str) or name not in SHARED | PROJECT
                for name in case[key]
            ):
                raise ValueError(f"{ident}: invalid {key} skill names")
        if set(case["expected"]) & set(case["excluded"]):
            raise ValueError(f"{ident}: conflicting expectations")
        if category == "no-skill" and case["expected"]:
            raise ValueError(f"{ident}: no-skill case has required skills")
        if "optional_skill" in case and (
            case["optional_skill"] != "prompt-assist" or not case.get("fallback")
        ):
            raise ValueError(f"{ident}: unknown optional skill or missing fallback")
        covered.update(case["expected"])
    if categories != {"positive", "subtle", "negative", "no-skill"}:
        raise ValueError("Missing positive/subtle/negative/no-skill coverage")
    if not SHARED | PROJECT <= covered:
        raise ValueError("Routing cases do not cover the declared skill inventory")
except (ValueError, KeyError, TypeError) as exc:
    errors.append(f"tools/framework-routing.json: {exc}")

if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
print(f"Framework structure OK: {len(paths)} documents/skills, {len(cases)} declared route cases.")
print("Links, metadata and declared routing checked; live selection/discovery and product acceptance unverified.")
