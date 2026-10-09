#!/usr/bin/env python3
"""Back up and restore huou07 playground's private runtime state."""

from __future__ import annotations

import argparse
import datetime
import grp
import json
import os
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web.app import validate_app_entries

ROOT = Path("/opt/huou07-playground")
CONFIG = Path("/etc/huou07-playground/apps.json")
BACKUP_DIR = Path("/var/backups/huou07-playground")
MAX_CONFIG_BYTES = 1_000_000
MAX_BRANDING_BYTES = 5_000_000


def create_backup(config: Path, branding: Path, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink() or not directory.is_dir() or directory.stat().st_uid != os.geteuid():
        raise ValueError("Backup destination must be a real directory.")
    os.chmod(directory, 0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = directory / f"huou07-playground-{stamp}.tar.gz"
    fd, temporary = tempfile.mkstemp(prefix=".backup-", suffix=".tmp", dir=directory)
    os.close(fd)
    try:
        with tarfile.open(temporary, "w:gz") as archive:
            add_state_file(archive, config, "apps.json", MAX_CONFIG_BYTES, required=True)
            add_state_file(archive, branding, "branding.png", MAX_BRANDING_BYTES, required=False)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return destination


def add_state_file(archive: tarfile.TarFile, source: Path, name: str, limit: int, required: bool) -> None:
    if source.is_symlink():
        raise ValueError(f"Refusing to back up a symbolic link: {name}")
    if not source.exists() and not required:
        return
    if not source.is_file() or source.stat().st_size > limit:
        raise ValueError(f"State file is missing or too large: {name}")
    archive.add(source, arcname=name, recursive=False)


def read_backup(backup: Path) -> tuple[bytes, bytes | None]:
    with tarfile.open(backup, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) not in (1, 2) or len(set(names)) != len(names) or "apps.json" not in names or set(names) - {"apps.json", "branding.png"}:
            raise ValueError("Backup contains unexpected files.")
        for member in members:
            limit = MAX_CONFIG_BYTES if member.name == "apps.json" else MAX_BRANDING_BYTES
            if not member.isfile() or member.size < 0 or member.size > limit:
                raise ValueError("Backup contains an unsafe or oversized file.")
        files = {}
        for member in members:
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Backup file could not be read.")
            with source:
                data = source.read(member.size + 1)
            if len(data) != member.size:
                raise ValueError("Backup file size does not match its header.")
            files[member.name] = data
    try:
        validate_app_entries(json.loads(files["apps.json"]))
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("Backup contains an invalid application registry.") from exc
    return files["apps.json"], files.get("branding.png")


def restore_backup(backup: Path, config: Path, branding: Path, group_id: int | None = None) -> None:
    config_data, branding_data = read_backup(backup)
    atomic_write(config, config_data, 0o660, group_id)
    if branding_data is None:
        branding.unlink(missing_ok=True)
    else:
        atomic_write(branding, branding_data, 0o644)


def atomic_write(destination: Path, data: bytes, mode: int, group_id: int | None = None) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), mode)
            if group_id is not None:
                os.fchown(output.fileno(), 0, group_id)
        os.replace(temporary, destination)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def current_branding() -> Path:
    releases = (ROOT / "releases").resolve(strict=True)
    release = (ROOT / "current").resolve(strict=True)
    release.relative_to(releases)
    return release / "web/static/branding.png"


def require_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("Run this command as root through sudo.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup", help="Create a private local state archive")
    backup.add_argument("--directory", type=Path, default=BACKUP_DIR)
    restore = commands.add_parser("restore", help="Restore an archive created by this tool")
    restore.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        require_root()
        if args.command == "backup":
            path = create_backup(CONFIG, current_branding(), args.directory)
            print(path)
            return
        if CONFIG.parent.is_symlink() or not CONFIG.parent.is_dir():
            raise ValueError("The application configuration directory is missing or unsafe.")
        branding = current_branding()
        group_id = grp.getgrnam("huou07-playground").gr_gid
        restore_backup(args.archive, CONFIG, branding, group_id)
        print("Application configuration and branding restored.")
    except (OSError, tarfile.TarError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
