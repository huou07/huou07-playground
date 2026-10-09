#!/usr/bin/env python3
"""Back up and restore huou07 playground's private runtime state."""

from __future__ import annotations

import argparse
import datetime
import grp
import io
import json
import os
import pwd
import shutil
import sys
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web.app import validate_app_entries

ROOT = Path("/opt/huou07-playground")
CONFIG = Path("/etc/huou07-playground/apps.json")
BACKUP_DIR = Path("/var/backups/huou07-playground")
MAX_CONFIG_BYTES = 1_000_000
MAX_BRANDING_BYTES = 5_000_000
MAX_OPENCODE_BYTES = 1_073_741_824
MAX_OPENCODE_FILES = 20_000
MAX_LITELLM_BYTES = 1_073_741_824
MAX_LITELLM_ENV_BYTES = 16_384
OPENCODE_STATE = Path("/var/lib/huou07-opencode")
OPENCODE_SERVICE = "huou07-opencode-web.service"
OPENCODE_UNIT = Path("/etc/systemd/system") / OPENCODE_SERVICE
LITELLM_SERVICE = "huou07-litellm.service"
LITELLM_DB_SERVICE = "huou07-litellm-db.service"
LITELLM_UNIT = Path("/etc/systemd/system") / LITELLM_SERVICE
LITELLM_DB_UNIT = Path("/etc/systemd/system") / LITELLM_DB_SERVICE
LITELLM_ENV_DIR = Path("/etc/huou07-litellm")
LITELLM_DATA_DIR = Path("/var/lib/huou07-litellm")


def create_backup(
    config: Path,
    branding: Path,
    directory: Path,
    opencode_state: Path = OPENCODE_STATE,
    litellm_env_dir: Path | None = None,
    litellm_dump: Path | None = None,
) -> Path:
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
            add_opencode_state(archive, opencode_state)
            if litellm_env_dir is not None or litellm_dump is not None:
                if litellm_env_dir is None or litellm_dump is None:
                    raise ValueError("LiteLLM backup is incomplete.")
                add_litellm_state(archive, litellm_env_dir, litellm_dump)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return destination


def add_litellm_state(archive: tarfile.TarFile, env_dir: Path, dump: Path) -> None:
    if env_dir.is_symlink() or not env_dir.is_dir() or dump.is_symlink() or not dump.is_file():
        raise ValueError("LiteLLM backup state is missing or unsafe.")
    environment = {}
    for name in ("litellm.env", "postgres.env"):
        source = env_dir / name
        if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_LITELLM_ENV_BYTES:
            raise ValueError("LiteLLM environment state is missing or unsafe.")
        data = source.read_bytes()
        environment[name] = data
        info = tarfile.TarInfo(f"litellm/{name}")
        info.size = len(data)
        info.mode = 0o600
        info.uid = 0
        info.gid = 0
        archive.addfile(info, io.BytesIO(data))
    validate_litellm_environment(environment)
    if dump.stat().st_size > MAX_LITELLM_BYTES:
        raise ValueError("LiteLLM database exceeds the private backup limit.")
    archive.add(dump, arcname="litellm/database.dump", recursive=False)


def validate_litellm_environment(files: dict[str, bytes]) -> None:
    expected = {
        "litellm.env": {"LITELLM_MASTER_KEY", "LITELLM_SALT_KEY", "DATABASE_URL"},
        "postgres.env": {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"},
    }
    values = {}
    for filename, keys in expected.items():
        data = files.get(filename)
        if not isinstance(data, bytes) or len(data) > MAX_LITELLM_ENV_BYTES:
            raise ValueError("LiteLLM backup contains invalid environment data.")
        try:
            lines = data.decode("ascii").splitlines()
        except UnicodeDecodeError as exc:
            raise ValueError("LiteLLM backup environment is not plain ASCII.") from exc
        parsed = {}
        for line in lines:
            key, separator, value = line.partition("=")
            if not separator or key not in keys or key in parsed or not value or any(char.isspace() for char in value):
                raise ValueError("LiteLLM backup environment contains invalid entries.")
            parsed[key] = value
        if set(parsed) != keys:
            raise ValueError("LiteLLM backup environment is incomplete.")
        values[filename] = parsed
    app = values["litellm.env"]
    postgres = values["postgres.env"]
    if not app["LITELLM_MASTER_KEY"].startswith("sk-") or not app["LITELLM_SALT_KEY"].startswith("sk-"):
        raise ValueError("LiteLLM backup keys have an invalid format.")
    if any(not value.startswith("sk-") or not value[3:].isalnum() for value in (app["LITELLM_MASTER_KEY"], app["LITELLM_SALT_KEY"])):
        raise ValueError("LiteLLM backup keys have an invalid format.")
    if postgres["POSTGRES_USER"] != "litellm" or postgres["POSTGRES_DB"] != "litellm" or not postgres["POSTGRES_PASSWORD"].isalnum():
        raise ValueError("LiteLLM backup database settings have an invalid format.")
    database_url = f"postgresql://litellm:{postgres['POSTGRES_PASSWORD']}@huou07-litellm-db:5432/litellm"
    if app["DATABASE_URL"] != database_url:
        raise ValueError("LiteLLM backup database credentials do not match.")


def add_opencode_state(archive: tarfile.TarFile, source: Path) -> None:
    if source.is_symlink():
        raise ValueError("Refusing to back up a symbolic link: OpenCode state")
    if not source.exists():
        return
    if not source.is_dir():
        raise ValueError("OpenCode state is not a directory.")
    files = []
    total = 0
    allowed_roots = {"config", "data", "state", "cache"}
    generated_shell_files = {".bash_logout", ".bashrc", ".profile"}
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("OpenCode state contains a symbolic link.")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("OpenCode state contains an unsupported file type.")
        relative = path.relative_to(source)
        if len(relative.parts) == 1 and relative.name in generated_shell_files:
            continue
        if not relative.parts or relative.parts[0] not in allowed_roots or any(part in {".", ".."} for part in relative.parts):
            raise ValueError("OpenCode state contains an unexpected path.")
        total += path.stat().st_size
        files.append((path, relative))
        if len(files) > MAX_OPENCODE_FILES or total > MAX_OPENCODE_BYTES:
            raise ValueError("OpenCode state exceeds the private backup limit.")
    for path, relative in files:
        archive.add(path, arcname=PurePosixPath("opencode", *relative.parts).as_posix(), recursive=False)


def add_state_file(archive: tarfile.TarFile, source: Path, name: str, limit: int, required: bool) -> None:
    if source.is_symlink():
        raise ValueError(f"Refusing to back up a symbolic link: {name}")
    if not source.exists() and not required:
        return
    if not source.is_file() or source.stat().st_size > limit:
        raise ValueError(f"State file is missing or too large: {name}")
    archive.add(source, arcname=name, recursive=False)


def read_backup(backup: Path) -> tuple[bytes, bytes | None, dict[str, bytes], dict[str, bytes]]:
    with tarfile.open(backup, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) > MAX_OPENCODE_FILES + 5 or len(set(names)) != len(names) or "apps.json" not in names:
            raise ValueError("Backup contains unexpected files.")
        opencode_members = {}
        total_opencode = 0
        litellm_members = set()
        total_litellm = 0
        for member in members:
            if member.name == "apps.json":
                limit = MAX_CONFIG_BYTES
            elif member.name == "branding.png":
                limit = MAX_BRANDING_BYTES
            elif member.name.startswith("opencode/"):
                relative_name = member.name.removeprefix("opencode/")
                relative = PurePosixPath(relative_name)
                if relative.is_absolute() or not relative.parts or relative.as_posix() != relative_name or any(part in {"", ".", ".."} for part in relative.parts) or relative.parts[0] not in {"config", "data", "state", "cache"}:
                    raise ValueError("Backup contains an unsafe OpenCode path.")
                if member.name in opencode_members:
                    raise ValueError("Backup contains duplicate OpenCode paths.")
                opencode_members[member.name] = relative.as_posix()
                limit = MAX_OPENCODE_BYTES
                total_opencode += member.size
            elif member.name in {"litellm/litellm.env", "litellm/postgres.env"}:
                litellm_members.add(member.name)
                limit = MAX_LITELLM_ENV_BYTES
            elif member.name == "litellm/database.dump":
                litellm_members.add(member.name)
                limit = MAX_LITELLM_BYTES
                total_litellm += member.size
            else:
                raise ValueError("Backup contains unexpected files.")
            if not member.isfile() or member.size < 0 or member.size > limit:
                raise ValueError("Backup contains an unsafe or oversized file.")
        if total_opencode > MAX_OPENCODE_BYTES:
            raise ValueError("Backup contains too much OpenCode state.")
        required_litellm = {"litellm/litellm.env", "litellm/postgres.env", "litellm/database.dump"}
        if litellm_members and litellm_members != required_litellm:
            raise ValueError("LiteLLM backup is incomplete.")
        if total_litellm > MAX_LITELLM_BYTES:
            raise ValueError("Backup contains too much LiteLLM database state.")
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
    litellm = {name.removeprefix("litellm/"): files[name] for name in litellm_members}
    if litellm:
        validate_litellm_environment(litellm)
    opencode = {opencode_members[name]: files[name] for name in opencode_members}
    return files["apps.json"], files.get("branding.png"), opencode, litellm


def restore_backup(
    backup: Path,
    config: Path,
    branding: Path,
    group_id: int | None = None,
    opencode_state: Path | None = None,
    opencode_uid: int | None = None,
    opencode_gid: int | None = None,
    opencode_config_gid: int | None = None,
    opencode_config_uid: int = 0,
    litellm_env_dir: Path | None = None,
) -> None:
    config_data, branding_data, opencode_files, litellm_files = read_backup(backup)
    if litellm_files:
        if litellm_env_dir is None or litellm_env_dir.is_symlink() or not litellm_env_dir.is_dir():
            raise ValueError("Install the LiteLLM integration before restoring its private state.")
        if not LITELLM_UNIT.is_file() or not LITELLM_DB_UNIT.is_file():
            raise ValueError("Install both LiteLLM services before restoring its private state.")
        if not litellm_db_service_active():
            raise ValueError("Start the LiteLLM PostgreSQL service before restoring its private state.")
        previous = {name: (litellm_env_dir / name).read_bytes() for name in ("litellm.env", "postgres.env")}
        try:
            atomic_write(litellm_env_dir / "litellm.env", litellm_files["litellm.env"], 0o600)
            atomic_write(litellm_env_dir / "postgres.env", litellm_files["postgres.env"], 0o600)
            restore_litellm_database(litellm_files["database.dump"], parse_postgres_password(litellm_files["postgres.env"]))
        except BaseException:
            for name, contents in previous.items():
                atomic_write(litellm_env_dir / name, contents, 0o600)
            raise
    if opencode_files:
        if opencode_state is None or not opencode_state.is_dir() or opencode_state.is_symlink():
            raise ValueError("Install the OpenCode web service before restoring its private state.")
        state_stat = opencode_state.stat()
        config_dir = opencode_state / "config"
        if opencode_uid is None:
            opencode_uid = state_stat.st_uid
        if opencode_gid is None:
            opencode_gid = state_stat.st_gid
        if opencode_config_gid is None:
            opencode_config_gid = config_dir.stat().st_gid if config_dir.is_dir() else opencode_gid
        restore_opencode_tree(opencode_files, opencode_state, opencode_uid, opencode_gid, opencode_config_gid, opencode_config_uid)
    atomic_write(config, config_data, 0o660, group_id)
    if branding_data is None:
        branding.unlink(missing_ok=True)
    else:
        atomic_write(branding, branding_data, 0o644)


def parse_postgres_password(data: bytes) -> str:
    for line in data.decode("ascii").splitlines():
        key, separator, value = line.partition("=")
        if separator and key == "POSTGRES_PASSWORD":
            return value
    raise ValueError("LiteLLM backup database password is missing.")


def run_litellm_podman(args: list[str], stdin=None, stdout=None) -> subprocess.CompletedProcess:
    account = pwd.getpwnam("huou07-litellm")
    command = [
        "runuser", "-u", "huou07-litellm", "--", "env",
        f"HOME={account.pw_dir}", "XDG_RUNTIME_DIR=/run/huou07-litellm",
        "/usr/bin/podman", *args,
    ]
    return subprocess.run(command, stdin=stdin, stdout=stdout, check=True)


def restore_litellm_database(dump: bytes, postgres_password: str) -> None:
    with tempfile.TemporaryFile() as archive:
        archive.write(dump)
        archive.seek(0)
        run_litellm_podman(
            [
                "exec", "-i", "huou07-litellm-db", "pg_restore", "--clean", "--if-exists", "--single-transaction",
                "--no-owner", "--no-acl", "-U", "litellm", "-d", "litellm",
            ],
            stdin=archive,
        )
    sql = f"ALTER ROLE litellm WITH PASSWORD '{postgres_password}';\n".encode("ascii")
    run_litellm_podman(
        ["exec", "-i", "huou07-litellm-db", "psql", "-v", "ON_ERROR_STOP=1", "-U", "litellm", "-d", "postgres"],
        stdin=io.BytesIO(sql),
    )


def restore_opencode_tree(files: dict[str, bytes], destination: Path, owner_uid: int, owner_gid: int, config_gid: int, config_uid: int = 0) -> None:
    parent = destination.parent
    if parent.is_symlink() or not parent.is_dir() or destination.is_symlink() or not destination.is_dir():
        raise ValueError("OpenCode state path is unavailable or unsafe.")
    staging = Path(tempfile.mkdtemp(prefix=".huou07-opencode-restore-", dir=parent))
    old = parent / f".{destination.name}.previous-{os.getpid()}"
    try:
        os.chown(staging, owner_uid, owner_gid)
        os.chmod(staging, 0o700)
        for relative, data in sorted(files.items()):
            parts = PurePosixPath(relative).parts
            if not parts or parts[0] not in {"config", "data", "state", "cache"} or any(part in {"", ".", ".."} for part in parts):
                raise ValueError("OpenCode backup contains an unsafe path.")
            config_file = parts[0] == "config"
            directory_owner = config_uid if config_file else owner_uid
            directory_group = config_gid if config_file else owner_gid
            directory_mode = 0o750 if config_file else 0o700
            current = staging
            for part in parts[:-1]:
                current = current / part
                current.mkdir(mode=directory_mode, exist_ok=True)
                os.chown(current, directory_owner, directory_group)
                os.chmod(current, directory_mode)
            output_path = current / parts[-1]
            fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640 if config_file else 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
                os.fchown(output.fileno(), directory_owner, directory_group)
                os.fchmod(output.fileno(), 0o640 if config_file else 0o600)
        if old.exists() or old.is_symlink():
            raise ValueError("An earlier OpenCode restore staging directory exists.")
        os.replace(destination, old)
        try:
            os.replace(staging, destination)
        except BaseException:
            os.replace(old, destination)
            raise
        shutil.rmtree(old)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


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


def opencode_service_active() -> bool:
    if not OPENCODE_UNIT.is_file():
        return False
    return subprocess.run(["systemctl", "is-active", "--quiet", OPENCODE_SERVICE], check=False).returncode == 0


def litellm_service_active() -> bool:
    if not LITELLM_UNIT.is_file():
        return False
    return subprocess.run(["systemctl", "is-active", "--quiet", LITELLM_SERVICE], check=False).returncode == 0


def litellm_db_service_active() -> bool:
    if not LITELLM_DB_UNIT.is_file():
        return False
    return subprocess.run(["systemctl", "is-active", "--quiet", LITELLM_DB_SERVICE], check=False).returncode == 0


def dump_litellm_database(destination: Path) -> None:
    with destination.open("wb") as output:
        run_litellm_podman(
            ["exec", "huou07-litellm-db", "pg_dump", "-U", "litellm", "-Fc", "litellm"],
            stdout=output,
        )
    if destination.stat().st_size > MAX_LITELLM_BYTES:
        raise ValueError("LiteLLM database exceeds the private backup limit.")


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
            was_active = opencode_service_active()
            if was_active:
                subprocess.run(["systemctl", "stop", OPENCODE_SERVICE], check=True)
            try:
                if LITELLM_UNIT.is_file():
                    if not litellm_service_active() or not litellm_db_service_active():
                        raise ValueError("Start both LiteLLM services before backing up its private state.")
                    with tempfile.TemporaryDirectory(prefix="huou07-litellm-backup-") as temporary:
                        dump = Path(temporary) / "database.dump"
                        dump_litellm_database(dump)
                        path = create_backup(CONFIG, current_branding(), args.directory, OPENCODE_STATE, LITELLM_ENV_DIR, dump)
                else:
                    path = create_backup(CONFIG, current_branding(), args.directory, OPENCODE_STATE)
            finally:
                if was_active:
                    subprocess.run(["systemctl", "start", OPENCODE_SERVICE], check=True)
            print(path)
            return
        if CONFIG.parent.is_symlink() or not CONFIG.parent.is_dir():
            raise ValueError("The application configuration directory is missing or unsafe.")
        branding = current_branding()
        _, _, opencode_files, litellm_files = read_backup(args.archive)
        was_active = opencode_service_active() if opencode_files else False
        litellm_was_active = litellm_service_active() if litellm_files else False
        if litellm_files and not litellm_db_service_active():
            raise ValueError("Start the LiteLLM PostgreSQL service before restoring its private state.")
        if was_active:
            subprocess.run(["systemctl", "stop", OPENCODE_SERVICE], check=True)
        if litellm_was_active:
            subprocess.run(["systemctl", "stop", LITELLM_SERVICE], check=True)
        try:
            group_id = grp.getgrnam("huou07-playground").gr_gid
            restore_backup(
                args.archive,
                CONFIG,
                branding,
                group_id,
                OPENCODE_STATE if opencode_files else None,
                litellm_env_dir=LITELLM_ENV_DIR if litellm_files else None,
            )
        finally:
            if was_active:
                subprocess.run(["systemctl", "start", OPENCODE_SERVICE], check=True)
            if litellm_was_active:
                subprocess.run(["systemctl", "start", LITELLM_SERVICE], check=True)
        print("Application configuration and branding restored.")
    except (OSError, subprocess.CalledProcessError, tarfile.TarError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
