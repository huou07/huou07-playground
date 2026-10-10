import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy import merge_opencode_config as migration


class OpenCodeMigrationTests(unittest.TestCase):
    def test_jsonc_comments_and_trailing_commas_are_parsed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "opencode.jsonc"
            path.write_text(
                '{// comment\n"provider":{"opencode-go":{"options":{"region":"west",},},},}',
                encoding="utf-8",
            )
            self.assertEqual(
                migration.parse_jsonc(path),
                {"provider": {"opencode-go": {"options": {"region": "west"}}}},
            )

    def test_jsonc_is_later_effective_layer_than_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "opencode.json").write_text(
                '{"provider":{"opencode-go":{"options":{"region":"web","timeout":20}}},"plugin":["json"]}'
            )
            (directory / "opencode.jsonc").write_text(
                '{"provider":{"opencode-go":{"options":{"region":"jsonc"}}},"plugin":["jsonc"]}'
            )
            effective = migration.merge_config_files(directory)
            self.assertEqual(
                effective,
                {
                    "provider": {"opencode-go": {"options": {"region": "jsonc"}}},
                    "plugin": ["jsonc"],
                },
            )
    def test_web_settings_merge_without_overriding_owner_and_plugins_are_union(self):
        web = {
            "$schema": "web-schema",
            "provider": {"opencode-go": {"options": {"endpoint": "web", "region": "west"}}},
            "mcp": {"web-tool": {"type": "local"}},
            "plugin": ["owner-shared", "web-plugin"],
            "tui": {"scroll_speed": 2, "theme": "web-theme"},
        }
        owner = {
            "$schema": "owner-schema",
            "provider": {"opencode-go": {"options": {"endpoint": "owner"}}},
            "mcp": {"owner-tool": {"type": "remote"}},
            "plugin": ["owner-shared", "owner-plugin"],
            "tui": {"theme": "owner-theme"},
            "shell": "/bin/zsh",
        }
        merged = migration.overlay(web, owner)
        self.assertEqual(merged["provider"]["opencode-go"]["options"], {"endpoint": "owner", "region": "west"})
        self.assertEqual(merged["mcp"], {"web-tool": {"type": "local"}, "owner-tool": {"type": "remote"}})
        self.assertEqual(merged["plugin"], ["owner-shared", "owner-plugin", "web-plugin"])
        self.assertEqual(merged["tui"], {"scroll_speed": 2, "theme": "owner-theme"})
        self.assertEqual(merged["shell"], "/bin/zsh")

    def test_auth_merge_imports_web_provider_and_keeps_owner_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "web-auth.json"
            owner = root / "owner-auth.json"
            source.write_text(json.dumps({"opencode-go": {"token": "web-secret"}, "other": {"token": "other"}}))
            owner.write_text(json.dumps({"opencode-go": {"token": "owner-secret"}}))
            merged, conflicts, imported = migration.auth_merge(source, owner)
            self.assertEqual(merged["opencode-go"]["token"], "owner-secret")
            self.assertEqual(merged["other"]["token"], "other")
            self.assertEqual((conflicts, imported), (1, 1))

    def test_check_reports_counts_without_printing_configuration_or_auth_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_config = root / "web-config"
            owner_config = root / "owner-config"
            source_data = root / "web-data"
            owner_data = root / "owner-data"
            for directory in (source_config, owner_config, source_data, owner_data):
                directory.mkdir()
            (source_config / "opencode.jsonc").write_text(
                '{"provider":{"opencode-go":{"options":{"apiKey":"web-secret"}}},"plugin":["web-plugin"]}'
            )
            (owner_config / "opencode.jsonc").write_text(
                '{"provider":{"opencode-go":{"options":{"apiKey":"owner-secret"}}}}'
            )
            (source_data / "auth.json").write_text('{"opencode-go":{"key":"web-auth-secret"}}')
            (owner_data / "auth.json").write_text('{"opencode-go":{"key":"owner-auth-secret"}}')
            stdout = []
            args = type("Args", (), {
                "source_config": source_config,
                "owner_config": owner_config,
                "source_data": source_data,
                "owner_data": owner_data,
                "mode": "check",
                "backup_dir": None,
                "uid": os.getuid(),
                "gid": os.getgid(),
            })()
            with patch("builtins.print", side_effect=lambda *values, **kwargs: stdout.append(" ".join(map(str, values)))):
                migration.run(args)
            output = "\n".join(stdout)
            for secret in ("web-secret", "owner-secret", "web-auth-secret", "owner-auth-secret"):
                self.assertNotIn(secret, output)
            self.assertIn("owner-precedence conflicts=1", output)
            self.assertIn("owner auth providers kept on conflict=1", output)

    def test_apply_and_restore_preserve_owner_files_byte_for_byte_and_source_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_config, owner_config = root / "web-config", root / "owner-config"
            source_data, owner_data, backup = root / "web-data", root / "owner-data", root / "backup"
            for directory in (source_config, owner_config, source_data, owner_data):
                directory.mkdir()
            owner_jsonc = b'{"shell":"owner-shell", // keep exact backup\n "plugin":["owner"],}'
            owner_auth = b'{"opencode-go":{"key":"owner-auth-secret"}}\n'
            web_config = b'{"plugin":["web"],"tui":{"theme":"dark"}}\n'
            web_auth = b'{"opencode-go":{"key":"web-auth-secret"},"other":{"key":"other"}}\n'
            (owner_config / "opencode.jsonc").write_bytes(owner_jsonc)
            (owner_data / "opencode").mkdir()
            (owner_data / "opencode" / "auth.json").write_bytes(owner_auth)
            (source_config / "opencode.jsonc").write_bytes(web_config)
            (source_data / "opencode").mkdir()
            (source_data / "opencode" / "auth.json").write_bytes(web_auth)
            args = type("Args", (), {
                "source_config": source_config,
                "owner_config": owner_config,
                "source_data": source_data,
                "owner_data": owner_data,
                "mode": "apply",
                "backup_dir": backup,
                "uid": os.getuid(),
                "gid": os.getgid(),
            })()
            migration.run(args)
            effective = migration.parse_jsonc(owner_config / "opencode.jsonc")
            self.assertEqual(effective["shell"], "owner-shell")
            self.assertEqual(effective["tui"]["theme"], "dark")
            self.assertEqual(effective["plugin"], ["owner", "web"])
            auth = json.loads((owner_data / "opencode" / "auth.json").read_text())
            self.assertEqual(auth["opencode-go"]["key"], "owner-auth-secret")
            self.assertEqual(auth["other"]["key"], "other")
            self.assertEqual((source_config / "opencode.jsonc").read_bytes(), web_config)
            self.assertEqual((source_data / "opencode" / "auth.json").read_bytes(), web_auth)
            migration.restore(owner_config, owner_data, backup, os.getuid(), os.getgid())
            self.assertEqual((owner_config / "opencode.jsonc").read_bytes(), owner_jsonc)
            self.assertEqual((owner_data / "opencode" / "auth.json").read_bytes(), owner_auth)

    def test_restore_removes_config_and_auth_created_when_owner_had_none(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_config, owner_config = root / "web-config", root / "owner-config"
            source_data, owner_data, backup = root / "web-data", root / "owner-data", root / "backup"
            for directory in (source_config, owner_config, source_data, owner_data):
                directory.mkdir()
            (source_config / "opencode.json").write_text('{"plugin":["web"]}')
            (source_data / "auth.json").write_text('{"web":{"key":"secret"}}')
            args = type("Args", (), {
                "source_config": source_config,
                "owner_config": owner_config,
                "source_data": source_data,
                "owner_data": owner_data,
                "mode": "apply",
                "backup_dir": backup,
                "uid": os.getuid(),
                "gid": os.getgid(),
            })()
            migration.run(args)
            self.assertTrue((owner_config / "opencode.jsonc").is_file())
            self.assertTrue((owner_data / "auth.json").is_file())
            migration.restore(owner_config, owner_data, backup, os.getuid(), os.getgid())
            self.assertFalse((owner_config / "opencode.jsonc").exists())
            self.assertFalse((owner_data / "auth.json").exists())


if __name__ == "__main__":
    unittest.main()
