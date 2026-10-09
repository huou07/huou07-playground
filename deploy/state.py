#!/usr/bin/env python3
"""Back up and restore huou07 playground state and workspace files."""

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
CONFIG = Path("/var/lib/huou07-playground/apps.json")
BACKUP_DIR = Path("/var/backups/huou07-playground")
WORKSPACE_DIR = Path("/srv/huou07-opencode-workspaces")
MAX_CONFIG_BYTES = 1_000_000
MAX_BRANDING_BYTES = 5_000_000
MAX_OPENCODE_BYTES = 1_073_741_824
MAX_OPENCODE_FILES = 20_000
MAX_WORKSPACE_FILES = 100_000
MAX_LITELLM_BYTES = 1_073_741_824
MAX_LITELLM_ENV_BYTES = 16_384
MAX_OMNIROUTE_BYTES = 1_073_741_824
MAX_OMNIROUTE_FILES = 20_000
MAX_OMNIROUTE_ENV_BYTES = 16_384
OPENCODE_STATE = Path("/var/lib/huou07-opencode")
OPENCODE_SERVICE = "huou07-opencode-web.service"
OPENCODE_UNIT = Path("/etc/systemd/system") / OPENCODE_SERVICE
LITELLM_SERVICE = "huou07-litellm.service"
LITELLM_DB_SERVICE = "huou07-litellm-db.service"
LITELLM_UNIT = Path("/etc/systemd/system") / LITELLM_SERVICE
LITELLM_DB_UNIT = Path("/etc/systemd/system") / LITELLM_DB_SERVICE
LITELLM_ENV_DIR = Path("/etc/huou07-litellm")
LITELLM_DATA_DIR = Path("/var/lib/huou07-litellm")
LITELLM_RUNTIME_DIR = Path("/run/huou07-litellm")
OMNIROUTE_SERVICE = "huou07-omniroute.service"
OMNIROUTE_UNIT = Path("/etc/systemd/system") / OMNIROUTE_SERVICE
OMNIROUTE_ENV_DIR = Path("/etc/huou07-omniroute")
OMNIROUTE_DATA_DIR = Path("/var/lib/huou07-omniroute/data")
OMNIROUTE_RUNTIME_DIR = Path("/run/huou07-omniroute")


def create_backup(
    config: Path,
    branding: Path,
    directory: Path,
    opencode_state: Path = OPENCODE_STATE,
    litellm_env_dir: Path | None = None,
    litellm_dump: Path | None = None,
    omniroute_env_dir: Path | None = None,
    omniroute_data_dir: Path | None = None,
    workspace_dir: Path | None = None,
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
            if omniroute_env_dir is not None or omniroute_data_dir is not None:
                if omniroute_env_dir is None or omniroute_data_dir is None:
                    raise ValueError("OmniRoute backup is incomplete.")
                add_omniroute_state(archive, omniroute_env_dir, omniroute_data_dir)
            if workspace_dir is not None:
                add_workspace_state(archive, workspace_dir)
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
    database_url = f"postgresql://litellm:{postgres['POSTGRES_PASSWORD']}@127.0.0.1:5432/litellm"
    if app["DATABASE_URL"] != database_url:
        raise ValueError("LiteLLM backup database credentials do not match.")


def add_omniroute_state(archive: tarfile.TarFile, env_dir: Path, data_dir: Path) -> None:
    if env_dir.is_symlink() or not env_dir.is_dir() or data_dir.is_symlink() or not data_dir.is_dir():
        raise ValueError("OmniRoute backup state is missing or unsafe.")
    environment_file = env_dir / "omniroute.env"
    if environment_file.is_symlink() or not environment_file.is_file() or environment_file.stat().st_size > MAX_OMNIROUTE_ENV_BYTES:
        raise ValueError("OmniRoute environment state is missing or unsafe.")
    environment = environment_file.read_bytes()
    validate_omniroute_environment(environment)
    info = tarfile.TarInfo("omniroute/omniroute.env")
    info.size = len(environment)
    info.mode = 0o600
    info.uid = 0
    info.gid = 0
    archive.addfile(info, io.BytesIO(environment))
    archive.add(data_dir, arcname="omniroute/data", recursive=False)
    files = []
    total = 0
    for path in sorted(data_dir.rglob("*")):
        if path.is_symlink():
            raise ValueError("OmniRoute data contains a symbolic link.")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("OmniRoute data contains an unsupported file type.")
        relative = path.relative_to(data_dir)
        if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("OmniRoute data contains an unsafe path.")
        total += path.stat().st_size
        files.append((path, relative))
        if len(files) > MAX_OMNIROUTE_FILES or total > MAX_OMNIROUTE_BYTES:
            raise ValueError("OmniRoute data exceeds the private backup limit.")
    for path, relative in files:
        archive.add(path, arcname=PurePosixPath("omniroute", "data", *relative.parts).as_posix(), recursive=False)


def validate_omniroute_environment(data: bytes) -> None:
    required = {
        "JWT_SECRET", "API_KEY_SECRET", "OMNIROUTE_WS_BRIDGE_SECRET", "MACHINE_ID_SALT",
        "OMNIROUTE_CLI_SALT", "INITIAL_PASSWORD", "REQUIRE_API_KEY", "ALLOW_API_KEY_REVEAL",
        "APP_BIND_HOST", "API_HOST", "DASHBOARD_PORT", "API_PORT", "LIVE_WS_PORT", "DATA_DIR", "REDIS_URL",
        "OMNIROUTE_MEMORY_MB", "NODE_ENV",
    }
    if not isinstance(data, bytes) or len(data) > MAX_OMNIROUTE_ENV_BYTES:
        raise ValueError("OmniRoute backup contains invalid environment data.")
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("OmniRoute backup environment is not plain ASCII.") from exc
    values = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if not separator or key not in required or key in values or not value or any(char.isspace() for char in value):
            raise ValueError("OmniRoute backup environment contains invalid entries.")
        values[key] = value
    if set(values) != required:
        raise ValueError("OmniRoute backup environment is incomplete.")
    secrets = ("JWT_SECRET", "API_KEY_SECRET", "OMNIROUTE_WS_BRIDGE_SECRET", "MACHINE_ID_SALT", "OMNIROUTE_CLI_SALT", "INITIAL_PASSWORD")
    if any(len(values[key]) < 32 or any(char not in "0123456789abcdef" for char in values[key]) for key in secrets):
        raise ValueError("OmniRoute backup secrets have an invalid format.")
    fixed = {
        "REQUIRE_API_KEY": "true", "ALLOW_API_KEY_REVEAL": "false", "APP_BIND_HOST": "127.0.0.1", "API_HOST": "0.0.0.0",
        "DASHBOARD_PORT": "20128", "API_PORT": "20129", "LIVE_WS_PORT": "20132",
        "DATA_DIR": "/app/data", "REDIS_URL": "redis://127.0.0.1:6379", "OMNIROUTE_MEMORY_MB": "8192",
        "NODE_ENV": "production",
    }
    if any(values[key] != value for key, value in fixed.items()):
        raise ValueError("OmniRoute backup runtime settings are invalid.")


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
    podman_state_path = ".local/share/containers/storage/db.sql"
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
        if not relative.parts or any(part in {".", ".."} for part in relative.parts):
            raise ValueError("OpenCode state contains an unexpected path.")
        if relative.parts[0] not in allowed_roots and relative.as_posix() != podman_state_path:
            raise ValueError("OpenCode state contains an unexpected path.")
        total += path.stat().st_size
        files.append((path, relative))
        if len(files) > MAX_OPENCODE_FILES or total > MAX_OPENCODE_BYTES:
            raise ValueError("OpenCode state exceeds the private backup limit.")
    for path, relative in files:
        archive.add(path, arcname=PurePosixPath("opencode", *relative.parts).as_posix(), recursive=False)


def add_workspace_state(archive: tarfile.TarFile, source: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("OpenCode workspace directory is missing or unsafe.")
    archive.add(source, arcname="workspace", recursive=False)
    count = 0
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("OpenCode workspace contains a symbolic link.")
        if not path.is_dir() and not path.is_file():
            raise ValueError("OpenCode workspace contains an unsupported file type.")
        relative = path.relative_to(source)
        if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("OpenCode workspace contains an unexpected path.")
        count += 1
        if count > MAX_WORKSPACE_FILES:
            raise ValueError("OpenCode workspace contains too many files and directories.")
        archive.add(path, arcname=PurePosixPath("workspace", *relative.parts).as_posix(), recursive=False)


def add_state_file(archive: tarfile.TarFile, source: Path, name: str, limit: int, required: bool) -> None:
    if source.is_symlink():
        raise ValueError(f"Refusing to back up a symbolic link: {name}")
    if not source.exists() and not required:
        return
    if not source.is_file() or source.stat().st_size > limit:
        raise ValueError(f"State file is missing or too large: {name}")
    archive.add(source, arcname=name, recursive=False)


def read_backup(backup: Path) -> tuple[bytes, bytes | None, dict[str, bytes], dict[str, bytes], dict[str, bytes], set[str]]:
    with tarfile.open(backup, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) > MAX_OPENCODE_FILES + MAX_OMNIROUTE_FILES + MAX_WORKSPACE_FILES + 7 or len(set(names)) != len(names) or "apps.json" not in names:
            raise ValueError("Backup contains unexpected files.")
        opencode_members = {}
        total_opencode = 0
        litellm_members = set()
        total_litellm = 0
        omniroute_members = set()
        omniroute_data_members = {}
        total_omniroute = 0
        workspace_members = set()
        for member in members:
            if member.name == "apps.json":
                limit = MAX_CONFIG_BYTES
            elif member.name == "branding.png":
                limit = MAX_BRANDING_BYTES
            elif member.name.startswith("opencode/"):
                relative_name = member.name.removeprefix("opencode/")
                relative = PurePosixPath(relative_name)
                safe_root = relative.parts[0] in {"config", "data", "state", "cache"} if relative.parts else False
                safe_podman_state = relative_name == ".local/share/containers/storage/db.sql"
                if relative.is_absolute() or not relative.parts or relative.as_posix() != relative_name or any(part in {"", ".", ".."} for part in relative.parts) or not (safe_root or safe_podman_state):
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
            elif member.name == "omniroute/omniroute.env":
                omniroute_members.add(member.name)
                limit = MAX_OMNIROUTE_ENV_BYTES
            elif member.name == "omniroute/data":
                omniroute_members.add(member.name)
                limit = 0
            elif member.name.startswith("omniroute/data/"):
                relative_name = member.name.removeprefix("omniroute/data/")
                relative = PurePosixPath(relative_name)
                if relative.is_absolute() or not relative.parts or relative.as_posix() != relative_name or any(part in {"", ".", ".."} for part in relative.parts):
                    raise ValueError("Backup contains an unsafe OmniRoute data path.")
                omniroute_members.add(member.name)
                omniroute_data_members[member.name] = relative.as_posix()
                limit = MAX_OMNIROUTE_BYTES
                total_omniroute += member.size
            elif member.name == "workspace" and member.isdir():
                workspace_members.add(member.name)
                limit = 0
            elif member.name.startswith("workspace/"):
                relative_name = member.name.removeprefix("workspace/")
                relative = PurePosixPath(relative_name)
                if relative.is_absolute() or not relative.parts or relative.as_posix() != relative_name or any(part in {"", ".", ".."} for part in relative.parts):
                    raise ValueError("Backup contains an unsafe workspace path.")
                if member.name in workspace_members:
                    raise ValueError("Backup contains duplicate workspace paths.")
                if not (member.isdir() or member.isfile()):
                    raise ValueError("Backup contains an unsupported workspace file type.")
                workspace_members.add(member.name)
                limit = member.size if member.isfile() else 0
            else:
                raise ValueError("Backup contains unexpected files.")
            workspace_directory = member.isdir() and (member.name == "workspace" or member.name.startswith("workspace/"))
            directory_marker = member.isdir() and member.size == 0 and (member.name == "omniroute/data" or workspace_directory)
            if workspace_directory and member.size != 0:
                raise ValueError("Backup contains an invalid workspace directory entry.")
            if not directory_marker and (not member.isfile() or member.size < 0 or member.size > limit):
                raise ValueError("Backup contains an unsafe or oversized file.")
        if total_opencode > MAX_OPENCODE_BYTES:
            raise ValueError("Backup contains too much OpenCode state.")
        required_litellm = {"litellm/litellm.env", "litellm/postgres.env", "litellm/database.dump"}
        if litellm_members and litellm_members != required_litellm:
            raise ValueError("LiteLLM backup is incomplete.")
        if total_litellm > MAX_LITELLM_BYTES:
            raise ValueError("Backup contains too much LiteLLM database state.")
        required_omniroute = {"omniroute/omniroute.env", "omniroute/data"}
        if omniroute_members and not required_omniroute.issubset(omniroute_members):
            raise ValueError("OmniRoute backup is incomplete.")
        if total_omniroute > MAX_OMNIROUTE_BYTES or len(omniroute_data_members) > MAX_OMNIROUTE_FILES:
            raise ValueError("Backup contains too much OmniRoute data.")
        if len(workspace_members) > MAX_WORKSPACE_FILES + 1:
            raise ValueError("Backup contains too many workspace files and directories.")
        if any(name.startswith("workspace/") for name in workspace_members) and "workspace" not in workspace_members:
            raise ValueError("Backup is missing its workspace root directory.")
        files = {}
        for member in members:
            if member.isdir() or member.name in workspace_members:
                continue
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
    omniroute = {"omniroute.env": files["omniroute/omniroute.env"]} if omniroute_members else {}
    if omniroute:
        validate_omniroute_environment(omniroute["omniroute.env"])
        omniroute.update({relative: files[name] for name, relative in omniroute_data_members.items()})
    return files["apps.json"], files.get("branding.png"), opencode, litellm, omniroute, workspace_members


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
    omniroute_env_dir: Path | None = None,
    omniroute_data_dir: Path | None = None,
    workspace_dir: Path | None = None,
) -> None:
    config_data, branding_data, opencode_files, litellm_files, omniroute_files, workspace_members = read_backup(backup)
    if workspace_members:
        if workspace_dir is None:
            raise ValueError("Install the OpenCode workspace before restoring its files.")
        restore_workspace_tree(backup, workspace_dir, workspace_members)
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
    if omniroute_files:
        if omniroute_env_dir is None or omniroute_env_dir.is_symlink() or not omniroute_env_dir.is_dir():
            raise ValueError("Install the OmniRoute integration before restoring its private state.")
        if omniroute_data_dir is None or omniroute_data_dir.is_symlink() or not omniroute_data_dir.is_dir() or not OMNIROUTE_UNIT.is_file():
            raise ValueError("Install the OmniRoute service and data directory before restoring its private state.")
        env_path = omniroute_env_dir / "omniroute.env"
        if env_path.is_symlink() or not env_path.is_file():
            raise ValueError("OmniRoute environment state is missing or unsafe.")
        previous_env = env_path.read_bytes()
        data_files = {name: data for name, data in omniroute_files.items() if name != "omniroute.env"}
        try:
            atomic_write(env_path, omniroute_files["omniroute.env"], 0o600)
            restore_omniroute_tree(data_files, omniroute_data_dir)
        except BaseException:
            atomic_write(env_path, previous_env, 0o600)
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


def restore_omniroute_tree(files: dict[str, bytes], destination: Path) -> None:
    parent = destination.parent
    if parent.is_symlink() or not parent.is_dir() or destination.is_symlink() or not destination.is_dir():
        raise ValueError("OmniRoute data path is unavailable or unsafe.")
    account = pwd.getpwnam("huou07-omniroute")
    staging = Path(tempfile.mkdtemp(prefix=".huou07-omniroute-restore-", dir=parent))
    old = parent / f".{destination.name}.previous-{os.getpid()}"
    try:
        os.chown(staging, account.pw_uid, account.pw_gid)
        os.chmod(staging, 0o700)
        for relative, data in sorted(files.items()):
            parts = PurePosixPath(relative).parts
            if not parts or any(part in {"", ".", ".."} for part in parts):
                raise ValueError("OmniRoute backup contains an unsafe path.")
            current = staging
            for part in parts[:-1]:
                current = current / part
                current.mkdir(mode=0o700, exist_ok=True)
                os.chown(current, account.pw_uid, account.pw_gid)
                os.chmod(current, 0o700)
            output_path = current / parts[-1]
            fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
                os.fchown(output.fileno(), account.pw_uid, account.pw_gid)
                os.fchmod(output.fileno(), 0o600)
        if old.exists() or old.is_symlink():
            raise ValueError("An earlier OmniRoute restore staging directory exists.")
        os.replace(destination, old)
        try:
            os.replace(staging, destination)
            run_omniroute_podman(["unshare", "chown", "-R", "1000:1000", str(destination)])
        except BaseException:
            if destination.exists():
                shutil.rmtree(destination)
            os.replace(old, destination)
            raise
        shutil.rmtree(old)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def parse_postgres_password(data: bytes) -> str:
    for line in data.decode("ascii").splitlines():
        key, separator, value = line.partition("=")
        if separator and key == "POSTGRES_PASSWORD":
            return value
    raise ValueError("LiteLLM backup database password is missing.")


def run_litellm_podman(args: list[str], stdin=None, stdout=None) -> subprocess.CompletedProcess:
    account = pwd.getpwnam("huou07-litellm")
    if LITELLM_RUNTIME_DIR.is_symlink():
        raise ValueError("The LiteLLM runtime directory must not be a symbolic link.")
    LITELLM_RUNTIME_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not LITELLM_RUNTIME_DIR.is_dir():
        raise ValueError("The LiteLLM runtime path is not a directory.")
    if os.geteuid() == 0:
        os.chown(LITELLM_RUNTIME_DIR, account.pw_uid, account.pw_gid)
    elif LITELLM_RUNTIME_DIR.stat().st_uid != account.pw_uid:
        raise ValueError("The LiteLLM runtime directory has an unexpected owner.")
    os.chmod(LITELLM_RUNTIME_DIR, 0o700)
    command = [
        "runuser", "-u", "huou07-litellm", "--", "env",
        f"HOME={account.pw_dir}", f"XDG_RUNTIME_DIR={LITELLM_RUNTIME_DIR}",
        "/usr/bin/podman", *args,
    ]
    return subprocess.run(command, stdin=stdin, stdout=stdout, check=True, cwd=account.pw_dir)


def run_omniroute_podman(args: list[str]) -> subprocess.CompletedProcess:
    account = pwd.getpwnam("huou07-omniroute")
    if OMNIROUTE_RUNTIME_DIR.is_symlink():
        raise ValueError("The OmniRoute runtime directory must not be a symbolic link.")
    OMNIROUTE_RUNTIME_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not OMNIROUTE_RUNTIME_DIR.is_dir():
        raise ValueError("The OmniRoute runtime path is not a directory.")
    if os.geteuid() == 0:
        os.chown(OMNIROUTE_RUNTIME_DIR, account.pw_uid, account.pw_gid)
    elif OMNIROUTE_RUNTIME_DIR.stat().st_uid != account.pw_uid:
        raise ValueError("The OmniRoute runtime directory has an unexpected owner.")
    os.chmod(OMNIROUTE_RUNTIME_DIR, 0o700)
    command = [
        "runuser", "-u", "huou07-omniroute", "--", "env",
        f"HOME={account.pw_dir}", f"XDG_RUNTIME_DIR={OMNIROUTE_RUNTIME_DIR}",
        "/usr/bin/podman", *args,
    ]
    return subprocess.run(command, check=True, cwd=account.pw_dir)


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
    with tempfile.TemporaryFile() as password_sql:
        password_sql.write(sql)
        password_sql.seek(0)
        run_litellm_podman(
            ["exec", "-i", "huou07-litellm-db", "psql", "-v", "ON_ERROR_STOP=1", "-U", "litellm", "-d", "postgres"],
            stdin=password_sql,
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
            safe_root = bool(parts) and parts[0] in {"config", "data", "state", "cache"}
            safe_podman_state = str(PurePosixPath(*parts)) == ".local/share/containers/storage/db.sql"
            if not parts or any(part in {"", ".", ".."} for part in parts) or not (safe_root or safe_podman_state):
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


def restore_workspace_tree(backup: Path, destination: Path, members: set[str]) -> None:
    parent = destination.parent
    if parent.is_symlink() or not parent.is_dir() or destination.is_symlink() or not destination.is_dir():
        raise ValueError("OpenCode workspace path is unavailable or unsafe.")
    owner = pwd.getpwnam("huou07-opencode")
    group_id = grp.getgrnam("huou07-opencode-workspaces").gr_gid
    staging = Path(tempfile.mkdtemp(prefix=".huou07-workspace-restore-", dir=parent))
    old = parent / f".{destination.name}.previous-{os.getpid()}"
    try:
        os.chown(staging, owner.pw_uid, group_id)
        os.chmod(staging, 0o2770)
        with tarfile.open(backup, "r:gz") as archive:
            for member in archive.getmembers():
                if member.name == "workspace":
                    continue
                if member.name not in members or not member.name.startswith("workspace/"):
                    continue
                relative = PurePosixPath(member.name.removeprefix("workspace/"))
                if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
                    raise ValueError("Backup contains an unsafe workspace path.")
                current = staging
                for part in relative.parts[:-1] if member.isfile() else relative.parts:
                    current = current / part
                    current.mkdir(mode=0o2770, exist_ok=True)
                    os.chown(current, owner.pw_uid, group_id)
                    os.chmod(current, 0o2770)
                if member.isdir():
                    continue
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("Backup workspace file could not be read.")
                output_path = current / relative.parts[-1]
                fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
                with source, os.fdopen(fd, "wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                    output.flush()
                    os.fsync(output.fileno())
                    os.fchown(output.fileno(), owner.pw_uid, group_id)
                    os.fchmod(output.fileno(), 0o660 | (member.mode & 0o110))
        if old.exists() or old.is_symlink():
            raise ValueError("An earlier workspace restore staging directory exists.")
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


def omniroute_service_active() -> bool:
    if not OMNIROUTE_UNIT.is_file():
        return False
    return subprocess.run(["systemctl", "is-active", "--quiet", OMNIROUTE_SERVICE], check=False).returncode == 0


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
    backup = commands.add_parser("backup", help="Create a private local state and workspace archive")
    backup.add_argument("--directory", type=Path, default=BACKUP_DIR)
    restore = commands.add_parser("restore", help="Restore an archive created by this tool")
    restore.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        require_root()
        if args.command == "backup":
            was_active = opencode_service_active()
            omniroute_was_active = omniroute_service_active()
            if OMNIROUTE_UNIT.is_file() and (OMNIROUTE_DATA_DIR.is_symlink() or not OMNIROUTE_DATA_DIR.is_dir() or OMNIROUTE_ENV_DIR.is_symlink() or not OMNIROUTE_ENV_DIR.is_dir()):
                raise ValueError("OmniRoute private state is missing or unsafe.")
            try:
                if was_active:
                    subprocess.run(["systemctl", "stop", OPENCODE_SERVICE], check=True)
                if omniroute_was_active:
                    subprocess.run(["systemctl", "stop", OMNIROUTE_SERVICE], check=True)
                with tempfile.TemporaryDirectory(prefix="huou07-private-backup-") as temporary:
                    dump = None
                    if LITELLM_UNIT.is_file():
                        if not litellm_service_active() or not litellm_db_service_active():
                            raise ValueError("Start both LiteLLM services before backing up its private state.")
                        dump = Path(temporary) / "database.dump"
                        dump_litellm_database(dump)
                    path = create_backup(
                        CONFIG,
                        current_branding(),
                        args.directory,
                        OPENCODE_STATE,
                        LITELLM_ENV_DIR if dump else None,
                        dump,
                        OMNIROUTE_ENV_DIR if OMNIROUTE_UNIT.is_file() else None,
                        OMNIROUTE_DATA_DIR if OMNIROUTE_UNIT.is_file() else None,
                        WORKSPACE_DIR if WORKSPACE_DIR.is_dir() else None,
                    )
            finally:
                if was_active:
                    subprocess.run(["systemctl", "start", OPENCODE_SERVICE], check=True)
                if omniroute_was_active:
                    subprocess.run(["systemctl", "start", OMNIROUTE_SERVICE], check=True)
            print(path)
            return
        if CONFIG.parent.is_symlink() or not CONFIG.parent.is_dir():
            raise ValueError("The application configuration directory is missing or unsafe.")
        branding = current_branding()
        _, _, opencode_files, litellm_files, omniroute_files, workspace_members = read_backup(args.archive)
        was_active = opencode_service_active() if opencode_files or workspace_members else False
        litellm_was_active = litellm_service_active() if litellm_files else False
        omniroute_was_active = omniroute_service_active() if omniroute_files else False
        if litellm_files and not litellm_db_service_active():
            raise ValueError("Start the LiteLLM PostgreSQL service before restoring its private state.")
        try:
            if was_active:
                subprocess.run(["systemctl", "stop", OPENCODE_SERVICE], check=True)
            if litellm_was_active:
                subprocess.run(["systemctl", "stop", LITELLM_SERVICE], check=True)
            if omniroute_was_active:
                subprocess.run(["systemctl", "stop", OMNIROUTE_SERVICE], check=True)
            group_id = grp.getgrnam("huou07-playground").gr_gid
            restore_backup(
                args.archive,
                CONFIG,
                branding,
                group_id,
                OPENCODE_STATE if opencode_files else None,
                litellm_env_dir=LITELLM_ENV_DIR if litellm_files else None,
                omniroute_env_dir=OMNIROUTE_ENV_DIR if omniroute_files else None,
                omniroute_data_dir=OMNIROUTE_DATA_DIR if omniroute_files else None,
                workspace_dir=WORKSPACE_DIR if workspace_members else None,
            )
        finally:
            if was_active:
                subprocess.run(["systemctl", "start", OPENCODE_SERVICE], check=True)
            if litellm_was_active:
                subprocess.run(["systemctl", "start", LITELLM_SERVICE], check=True)
            if omniroute_was_active:
                subprocess.run(["systemctl", "start", OMNIROUTE_SERVICE], check=True)
        print("Workspace, application configuration, and private state restored.")
    except (OSError, subprocess.CalledProcessError, tarfile.TarError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
