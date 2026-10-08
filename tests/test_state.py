import io
import json
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
            config.write_text(json.dumps({"apps": []}))
            branding.write_bytes(b"private image bytes")
            archive = state.create_backup(config, branding, root / "backups")
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            config.write_text('{"apps":[{"name":"temporary","url":"https://example.com"}]}')
            branding.write_bytes(b"temporary")
            state.restore_backup(archive, config, branding)
            self.assertEqual(json.loads(config.read_text()), {"apps": []})
            self.assertEqual(branding.read_bytes(), b"private image bytes")

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
