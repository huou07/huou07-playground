import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy.register_app import register_default_app


class RegisterDefaultAppTests(unittest.TestCase):
    def test_registers_an_installed_app_once(self):
        app = {
            "name": "OpenCode Web",
            "url": "http://127.0.0.1:14096/",
            "category": "Coding Agents",
            "description": "Private coding workspace.",
            "health_url": "http://127.0.0.1:4096/",
            "health_method": "GET",
            "management_url": "http://127.0.0.1:14096/",
        }
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "apps.json"
            registry.write_text('{"apps":[]}')
            with patch.dict(os.environ, {"APPS_FILE": str(registry)}):
                self.assertTrue(register_default_app(app))
                self.assertFalse(register_default_app(app))
            self.assertEqual(json.loads(registry.read_text())["apps"], [app])

    def test_preserves_owner_customized_entry(self):
        customized = {
            "name": "Cockpit Files",
            "url": "http://127.0.0.1:19090/system/files",
            "category": "Files",
            "description": "Owner's preferred forwarded port.",
            "health_url": None,
            "health_method": "GET",
            "management_url": None,
        }
        default = {
            "name": "Cockpit Files",
            "url": "http://127.0.0.1:9090/system/files",
            "category": "Files",
            "description": "Browse and manage files.",
            "health_url": "http://127.0.0.1:9090/",
            "health_method": "GET",
            "management_url": "http://127.0.0.1:9090/system/files",
        }
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "apps.json"
            registry.write_text(json.dumps({"apps": [customized]}))
            with patch.dict(os.environ, {"APPS_FILE": str(registry)}):
                self.assertFalse(register_default_app(default))
            self.assertEqual(json.loads(registry.read_text())["apps"], [customized])

    def test_migrates_only_explicit_legacy_launch_url_and_preserves_other_settings(self):
        old_url = "http://127.0.0.1:9090/"
        existing = {
            "name": "Cockpit Files",
            "url": old_url,
            "category": "My Files",
            "description": "Owner's note.",
            "health_url": old_url,
            "health_method": "HEAD",
            "management_url": None,
        }
        default = {
            "name": "Cockpit Files",
            "url": "http://127.0.0.1:9090/system/files",
            "category": "Files",
            "description": "Browse and manage files.",
            "health_url": old_url,
            "health_method": "GET",
            "management_url": "http://127.0.0.1:9090/system/files",
        }
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "apps.json"
            registry.write_text(json.dumps({"apps": [existing]}))
            with patch.dict(os.environ, {"APPS_FILE": str(registry)}):
                self.assertTrue(register_default_app(default, (old_url,)))
            migrated = json.loads(registry.read_text())["apps"][0]
        self.assertEqual(migrated["url"], default["url"])
        self.assertEqual(migrated["category"], existing["category"])
        self.assertEqual(migrated["description"], existing["description"])
        self.assertEqual(migrated["health_url"], existing["health_url"])
        self.assertEqual(migrated["health_method"], existing["health_method"])
        self.assertEqual(migrated["management_url"], existing["management_url"])

    def test_rejects_invalid_builtin_app_without_changing_registry(self):
        app = {"name": "Bad", "url": "file:///etc/passwd"}
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "apps.json"
            original = '{"apps":[]}'
            registry.write_text(original)
            with patch.dict(os.environ, {"APPS_FILE": str(registry)}):
                with self.assertRaises(ValueError):
                    register_default_app(app)
            self.assertEqual(registry.read_text(), original)


if __name__ == "__main__":
    unittest.main()
