import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy import state


class StateArchiveTests(unittest.TestCase):
    def test_litellm_podman_uses_the_service_account_home_as_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            account = type("Account", (), {"pw_dir": "/var/lib/huou07-litellm", "pw_uid": os.geteuid(), "pw_gid": os.getegid()})()
            runtime = Path(directory) / "runtime"
            with mock.patch.object(state, "LITELLM_RUNTIME_DIR", runtime), \
                 mock.patch.object(state.pwd, "getpwnam", return_value=account), \
                 mock.patch.object(state.subprocess, "run") as run:
                state.run_litellm_podman(["ps"])
            self.assertEqual(run.call_args.kwargs["cwd"], account.pw_dir)
            self.assertEqual(runtime.stat().st_mode & 0o777, 0o700)

    def test_litellm_backup_restore_round_trip_keeps_secrets_private(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "apps.json"
            config.write_text('{"apps":[]}')
            env_dir = root / "litellm"
            env_dir.mkdir()
            password = "a" * 64
            (env_dir / "postgres.env").write_text(
                f"POSTGRES_USER=litellm\nPOSTGRES_PASSWORD={password}\nPOSTGRES_DB=litellm\n"
            )
            (env_dir / "litellm.env").write_text(
                "LITELLM_MASTER_KEY=sk-master0123456789\n"
                "LITELLM_SALT_KEY=sk-salt0123456789\n"
                f"DATABASE_URL=postgresql://litellm:{password}@127.0.0.1:5432/litellm\n"
            )
            dump = root / "database.dump"
            dump.write_bytes(b"private database snapshot")
            archive = state.create_backup(config, root / "missing.png", root / "backups", litellm_env_dir=env_dir, litellm_dump=dump)
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            _, _, _, backed_up = state.read_backup(archive)
            self.assertEqual(backed_up["database.dump"], dump.read_bytes())
            self.assertEqual(backed_up["postgres.env"], (env_dir / "postgres.env").read_bytes())

            (env_dir / "postgres.env").write_text("old database settings\n")
            with mock.patch.object(state, "LITELLM_UNIT", root / "proxy.service"), \
                 mock.patch.object(state, "LITELLM_DB_UNIT", root / "database.service"), \
                 mock.patch.object(state, "litellm_db_service_active", return_value=True), \
                 mock.patch.object(state, "restore_litellm_database") as restore_db:
                state.LITELLM_UNIT.touch()
                state.LITELLM_DB_UNIT.touch()
                state.restore_backup(archive, config, root / "branding.png", litellm_env_dir=env_dir)

            self.assertEqual(restore_db.call_args.args, (b"private database snapshot", password))
            self.assertEqual((env_dir / "postgres.env").stat().st_mode & 0o777, 0o600)
            self.assertEqual((env_dir / "postgres.env").read_bytes(), backed_up["postgres.env"])

    def test_litellm_backup_rejects_inconsistent_credentials_and_partial_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "apps.json"
            config.write_text('{"apps":[]}')
            env_dir = root / "litellm"
            env_dir.mkdir()
            (env_dir / "postgres.env").write_text(
                f"POSTGRES_USER=litellm\nPOSTGRES_PASSWORD={'a' * 64}\nPOSTGRES_DB=litellm\n"
            )
            (env_dir / "litellm.env").write_text(
                "LITELLM_MASTER_KEY=sk-master0123456789\n"
                "LITELLM_SALT_KEY=sk-salt0123456789\n"
                "DATABASE_URL=postgresql://litellm:wrong@127.0.0.1:5432/litellm\n"
            )
            dump = root / "database.dump"
            dump.write_bytes(b"snapshot")
            with self.assertRaisesRegex(ValueError, "credentials do not match"):
                state.create_backup(config, root / "missing.png", root / "backups", litellm_env_dir=env_dir, litellm_dump=dump)

            archive = root / "partial.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                payload = b'{"apps":[]}'
                config_member = tarfile.TarInfo("apps.json")
                config_member.size = len(payload)
                tar.addfile(config_member, io.BytesIO(payload))
                member = tarfile.TarInfo("litellm/litellm.env")
                member.size = 1
                tar.addfile(member, io.BytesIO(b"x"))
            with self.assertRaisesRegex(ValueError, "LiteLLM backup is incomplete"):
                state.read_backup(archive)

    def test_backup_restore_round_trip_preserves_private_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "apps.json"
            branding = root / "branding.png"
            opencode = root / "opencode-state"
            config.write_text(json.dumps({"apps": []}))
            branding.write_bytes(b"private image bytes")
            (opencode / "config" / "opencode").mkdir(parents=True)
            (opencode / "data" / "opencode").mkdir(parents=True)
            (opencode / "config" / "opencode" / "opencode.json").write_text('{"permission":{"bash":"ask"}}')
            (opencode / "data" / "opencode" / "auth.json").write_text("private provider token")
            archive = state.create_backup(config, branding, root / "backups", opencode)
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            config.write_text('{"apps":[{"name":"temporary","url":"https://example.com"}]}')
            branding.write_bytes(b"temporary")
            (opencode / "data" / "opencode" / "auth.json").write_text("new token")
            (opencode / "data" / "opencode" / "new-session.db").write_text("new session")
            state.restore_backup(archive, config, branding, opencode_state=opencode, opencode_uid=os.geteuid(), opencode_gid=os.getegid(), opencode_config_gid=os.getegid(), opencode_config_uid=os.geteuid())
            self.assertEqual(json.loads(config.read_text()), {"apps": []})
            self.assertEqual(branding.read_bytes(), b"private image bytes")
            self.assertEqual((opencode / "data" / "opencode" / "auth.json").read_text(), "private provider token")
            self.assertFalse((opencode / "data" / "opencode" / "new-session.db").exists())
            self.assertEqual((opencode / "data" / "opencode" / "auth.json").stat().st_mode & 0o777, 0o600)

    def test_backup_rejects_unsafe_members_and_invalid_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                payload = b'{"apps":[]}'
                member = tarfile.TarInfo("../apps.json")
                member.size = len(payload)
                tar.addfile(member, io.BytesIO(payload))
            with self.assertRaisesRegex(ValueError, "unexpected files"):
                state.read_backup(archive)

            with tarfile.open(archive, "w:gz") as tar:
                payload = b'{"apps":[]}'
                config = tarfile.TarInfo("apps.json")
                config.size = len(payload)
                tar.addfile(config, io.BytesIO(payload))
                link = tarfile.TarInfo("branding.png")
                link.type = tarfile.SYMTYPE
                link.linkname = "../../etc/passwd"
                tar.addfile(link)
            with self.assertRaisesRegex(ValueError, "unsafe or oversized"):
                state.read_backup(archive)

            with tarfile.open(archive, "w:gz") as tar:
                payload = b'{"apps":[{"name":"Bad","url":"javascript:alert(1)"}]}'
                member = tarfile.TarInfo("apps.json")
                member.size = len(payload)
                tar.addfile(member, io.BytesIO(payload))
            with self.assertRaisesRegex(ValueError, "invalid application registry"):
                state.read_backup(archive)

            with tarfile.open(archive, "w:gz") as tar:
                payload = b"private"
                config = tarfile.TarInfo("apps.json")
                config.size = len(payload)
                tar.addfile(config, io.BytesIO(b'{"apps":[]}'))
                outside = tarfile.TarInfo("opencode/data/../../etc/passwd")
                outside.size = len(payload)
                tar.addfile(outside, io.BytesIO(payload))
            with self.assertRaisesRegex(ValueError, "unsafe OpenCode path"):
                state.read_backup(archive)

    def test_backup_rejects_opencode_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "apps.json"
            config.write_text('{"apps":[]}')
            opencode = root / "opencode-state"
            (opencode / "data").mkdir(parents=True)
            target = root / "outside"
            target.write_text("outside")
            (opencode / "data" / "link").symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                state.create_backup(config, root / "missing.png", root / "backups", opencode)

    def test_restore_removes_local_branding_when_backup_has_none(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "apps.json"
            branding = root / "branding.png"
            source_config = root / "source.json"
            source_config.write_text('{"apps":[]}')
            branding.write_bytes(b"newer private art")
            archive = state.create_backup(source_config, root / "missing.png", root / "backups")
            state.restore_backup(archive, config, branding)
            self.assertEqual(config.read_text(), '{"apps":[]}')
            self.assertFalse(branding.exists())


if __name__ == "__main__":
    unittest.main()
