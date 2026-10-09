#!/usr/bin/env python3
"""Add a built-in application link without overwriting owner settings."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web.app import mutate_app_registry, validate_app_entries


def register_default_app(app: dict, migrate_url_from: tuple[str, ...] = ()) -> bool:
    """Register installed apps, migrating only explicitly listed old defaults."""
    app = validate_app_entries({"apps": [app]})[0]
    path = Path(os.environ.get("APPS_FILE", "/var/lib/huou07-playground/apps.json"))
    if path.is_symlink() or not path.is_file():
        raise OSError("Application registry path is unavailable.")
    apps = validate_app_entries(json.loads(path.read_text()))
    existing = next((entry for entry in apps if entry["name"].casefold() == app.get("name", "").strip().casefold()), None)
    if existing is not None:
        if existing["url"] not in migrate_url_from:
            return False
        updated = {**existing, "url": app["url"]}
        mutate_app_registry({"action": "update", "name": existing["name"], "app": updated})
        return True
    mutate_app_registry({"action": "add", "name": app["name"], "app": app})
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--category", default="Application")
    parser.add_argument("--description", default="")
    parser.add_argument("--health-url")
    parser.add_argument("--health-method", choices=("GET", "HEAD"), default="GET")
    parser.add_argument("--management-url")
    parser.add_argument("--migrate-url-from", action="append", default=[])
    args = parser.parse_args()
    app = {
        "name": args.name,
        "url": args.url,
        "category": args.category,
        "description": args.description,
        "health_method": args.health_method,
        "health_url": args.health_url,
        "management_url": args.management_url,
    }
    try:
        added = register_default_app(app, tuple(args.migrate_url_from))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        print(f"Could not register {args.name}: {error}", file=sys.stderr)
        return 1
    print(f"Registered or migrated the default {args.name} link." if added else f"Preserved existing {args.name} settings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
