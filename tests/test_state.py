import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy import state


class StateArchiveTests(unittest.TestCase):
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
