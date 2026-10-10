#!/usr/bin/env python3
"""Merge the managed OpenCode Web config into the owner's native config safely."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any


CONFIG_NAMES = ("opencode.json", "opencode.jsonc")


def parse_jsonc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    cleaned: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            cleaned.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            cleaned.append(char)
            index += 1
            continue
        if char == "/" and following == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and following == "*":
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError(f"unterminated JSONC comment in {path}")
            index = end + 2
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "]}":
                index += 1
                continue
        cleaned.append(char)
        index += 1
    try:
        value = json.loads("".join(cleaned))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid OpenCode JSONC in {path}: line {error.lineno}") from None
    if not isinstance(value, dict):
        raise ValueError(f"OpenCode config must be a JSON object: {path}")
    return value


def merge_config_files(directory: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in CONFIG_NAMES:
        path = directory / name
        if path.is_symlink():
            raise ValueError("OpenCode config file must not be a symbolic link")
        if path.is_file():
            # OpenCode loads JSON first and JSONC second. For each declared
            # top-level setting, the later document is the effective value.
            result.update(parse_jsonc(path))
    return result


def overlay(web: Any, owner: Any, path: tuple[str, ...] = ()) -> Any:
    """Deep merge objects; owner values win; plugin declarations are additive."""
    if path == ("plugin",) and isinstance(web, list) and isinstance(owner, list):
        merged = list(owner)
        seen = {json.dumps(item, sort_keys=True, separators=(",", ":")) for item in merged}
        for item in web:
            identity = json.dumps(item, sort_keys=True, separators=(",", ":"))
            if identity not in seen:
                merged.append(item)
                seen.add(identity)
        return merged
    if isinstance(web, dict) and isinstance(owner, dict):
        result = dict(web)
        for key, owner_value in owner.items():
            result[key] = overlay(result[key], owner_value, (*path, key)) if key in result else owner_value
        return result
    return owner


def auth_merge(source: Path, owner: Path) -> tuple[dict[str, Any], int, int]:
    source_auth = json.loads(source.read_text(encoding="utf-8"))
    owner_auth = json.loads(owner.read_text(encoding="utf-8")) if owner.is_file() else {}
    if not isinstance(source_auth, dict) or not isinstance(owner_auth, dict):
        raise ValueError("OpenCode auth files must contain a JSON object")
    result = dict(source_auth)
    conflicts = 0
    imported = len(source_auth.keys() - owner_auth.keys())
    for provider, owner_value in owner_auth.items():
        if provider in result and result[provider] != owner_value:
            conflicts += 1
        result[provider] = owner_value
    return result, conflicts, imported


def count_owner_conflicts(web: Any, owner: Any) -> int:
    if isinstance(web, dict) and isinstance(owner, dict):
        return sum(
            count_owner_conflicts(web[key], owner_value) if key in web else 0
            for key, owner_value in owner.items()
        )
    return int(web != owner)


def config_summary(source_dir: Path, owner_dir: Path) -> tuple[dict[str, Any], int, int]:
    web = merge_config_files(source_dir)
    owner = merge_config_files(owner_dir)
    merged = overlay(web, owner)
    conflicts = count_owner_conflicts(web, owner)
    web_plugins = web.get("plugin", [])
    owner_plugins = owner.get("plugin", [])
    if not isinstance(web_plugins, list):
        web_plugins = []
    if not isinstance(owner_plugins, list):
        owner_plugins = []
    plugins_added = 0
    owner_plugin_values = {
        json.dumps(item, sort_keys=True, separators=(",", ":")) for item in owner_plugins
    }
    plugins_added = sum(
        json.dumps(item, sort_keys=True, separators=(",", ":")) not in owner_plugin_values
        for item in web_plugins
    )
    return merged, conflicts, plugins_added


def write_atomic(path: Path, value: dict[str, Any], uid: int, gid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(value, output, indent=2, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.chown(temporary, uid, gid)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def snapshot(
    owner_config: Path, owner_data: Path, backup_dir: Path, auth_relative: Path | None
) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest: dict[str, Any] = {"config_jsonc": False, "auth_relative": None, "auth_existed": False}
    config_jsonc = owner_config / "opencode.jsonc"
    if config_jsonc.is_file():
        shutil.copy2(config_jsonc, backup_dir / "owner-opencode.jsonc")
        manifest["config_jsonc"] = True
    if auth_relative is not None:
        auth = owner_data / auth_relative
        manifest["auth_relative"] = auth_relative.as_posix()
        if auth.exists() or auth.is_symlink():
            if auth.is_symlink() or not auth.is_file():
                raise ValueError("owner OpenCode auth path must be a regular file")
            shutil.copy2(auth, backup_dir / "owner-auth.json")
            manifest["auth_existed"] = True
    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(manifest_path, 0o600)


def restore(owner_config: Path, owner_data: Path, backup_dir: Path, uid: int, gid: int) -> None:
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    config_jsonc = owner_config / "opencode.jsonc"
    if config_jsonc.is_file():
        shutil.copy2(config_jsonc, backup_dir / "migrated-opencode.jsonc")
    config_jsonc.unlink(missing_ok=True)
    if manifest["config_jsonc"]:
        shutil.copy2(backup_dir / "owner-opencode.jsonc", config_jsonc)
        os.chown(config_jsonc, uid, gid)
    relative = manifest["auth_relative"]
    if relative:
        auth_path = (owner_data / relative).resolve()
        if owner_data.resolve() not in auth_path.parents:
            raise ValueError("unsafe auth path in migration backup")
        if auth_path.is_file():
            shutil.copy2(auth_path, backup_dir / "migrated-auth.json")
        if manifest["auth_existed"]:
            auth_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_dir / "owner-auth.json", auth_path)
            os.chown(auth_path, uid, gid)
        else:
            auth_path.unlink(missing_ok=True)


def run(args: argparse.Namespace) -> None:
    source_config = args.source_config
    owner_config = args.owner_config
    source_data = args.source_data
    owner_data = args.owner_data
    if any(path.is_symlink() for path in (source_config, owner_config, source_data, owner_data)):
        raise ValueError("OpenCode migration directories must not be symbolic links")
    source_files = [source_config / name for name in CONFIG_NAMES if (source_config / name).is_file()]
    source_auth_candidates = sorted(source_data.rglob("auth.json")) if source_data.exists() else []
    if len(source_auth_candidates) > 1:
        raise ValueError("multiple Web OpenCode auth.json files; refusing ambiguous migration")
    source_auth = source_auth_candidates[0] if source_auth_candidates else None
    if source_auth and (source_auth.is_symlink() or not source_auth.is_file()):
        raise ValueError("Web OpenCode auth path must be a regular file")
    auth_relative = source_auth.relative_to(source_data) if source_auth else None
    owner_auth = owner_data / auth_relative if auth_relative else None
    if owner_auth:
        if owner_data.is_symlink():
            raise ValueError("owner OpenCode auth directory must not be a symbolic link")
        current = owner_data
        for part in auth_relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("owner OpenCode auth path must not contain symbolic links")
        if current.exists() and not current.is_file():
            raise ValueError("owner OpenCode auth path must be a regular file")
    merged, config_conflicts, plugins_added = config_summary(source_config, owner_config)
    auth_conflicts = auth_imports = 0
    merged_auth: dict[str, Any] | None = None
    if source_auth and owner_auth:
        merged_auth, auth_conflicts, auth_imports = auth_merge(source_auth, owner_auth)

    print(
        "OpenCode merge check: "
        f"Web config files={len(source_files)}, owner config files="
        f"{sum((owner_config / name).is_file() for name in CONFIG_NAMES)}, "
        f"owner-precedence conflicts={config_conflicts}, Web plugin entries to add={plugins_added}, "
        f"Web auth providers to add={auth_imports}, owner auth providers kept on conflict={auth_conflicts}."
    )
    if args.mode == "check":
        return

    if args.mode == "verify":
        if source_files and merge_config_files(owner_config) != merged:
            raise ValueError("effective owner OpenCode config does not match the planned merge")
        if source_auth and owner_auth:
            actual_auth = json.loads(owner_auth.read_text(encoding="utf-8")) if owner_auth.is_file() else {}
            if actual_auth != merged_auth:
                raise ValueError("owner OpenCode auth does not match the planned provider merge")
        print("OpenCode effective config and provider auth match the deterministic merge.")
        return

    if not source_files and not source_auth:
        print("No OpenCode Web config or auth files require migration.")
        return
    backup_dir = args.backup_dir
    if not backup_dir:
        raise ValueError("apply requires a private backup directory")
    snapshot(owner_config, owner_data, backup_dir, auth_relative)
    if source_files:
        write_atomic(owner_config / "opencode.jsonc", merged, args.uid, args.gid)
    if source_auth and owner_auth and merged_auth is not None:
        write_atomic(owner_auth, merged_auth, args.uid, args.gid)
    elif source_auth and auth_relative:
        target_auth = owner_data / auth_relative
        if not target_auth.exists():
            write_atomic(target_auth, json.loads(source_auth.read_text(encoding="utf-8")), args.uid, args.gid)
    print("OpenCode settings merged. Original owner config/auth files are backed up; Web source state remains untouched.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check", "apply", "verify", "restore"))
    parser.add_argument("--source-config", type=Path, required=True)
    parser.add_argument("--owner-config", type=Path, required=True)
    parser.add_argument("--source-data", type=Path, required=True)
    parser.add_argument("--owner-data", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--uid", type=int, default=os.getuid())
    parser.add_argument("--gid", type=int, default=os.getgid())
    args = parser.parse_args()
    try:
        if args.mode == "restore":
            if not args.backup_dir:
                raise ValueError("restore requires a private backup directory")
            restore(args.owner_config, args.owner_data, args.backup_dir, args.uid, args.gid)
            print("Original owner OpenCode config/auth files restored.")
        else:
            run(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        message = str(error)
        # Never surface JSON decoder snippets or exception data that could include config values.
        safe_message = re.sub(r"line \d+ column \d+.*", "", message)
        print(f"OpenCode migration check failed: {safe_message}", file=__import__("sys").stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
