import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "deploy" / "user" / "dsh-launcher.py"
SPEC = importlib.util.spec_from_file_location("dsh_user_launcher", MODULE_PATH)
dsh_launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dsh_launcher)


class DshUserLauncherTests(unittest.TestCase):
    def test_environment_uses_the_native_user_home_and_auth_store(self):
        environment = dsh_launcher.child_environment({
            "PATH": "/safe/bin", "LANG": "C.UTF-8", "OPENAI_API_KEY": "not-forwarded",
            "OPENCODE_GO_API_KEY": "not-forwarded", "CODEX_HOME": "/tmp/other-codex",
        })
        home = str(dsh_launcher.HOME)
        self.assertEqual(environment["HOME"], home)
        self.assertEqual(environment["CODEX_HOME"], f"{home}/.codex")
        self.assertEqual(environment["DSH_HOME"], f"{home}/.dsh")
        self.assertEqual(environment["XDG_CONFIG_HOME"], f"{home}/.config")
        self.assertEqual(environment["XDG_DATA_HOME"], f"{home}/.local/share")
        self.assertEqual(environment["PATH"], "/safe/bin")
        self.assertEqual(environment["LANG"], "C.UTF-8")
        for name in ("OPENAI_API_KEY", "OPENCODE_GO_API_KEY"):
            self.assertNotIn(name, environment)

    def test_url_file_is_private_and_contains_only_valid_local_token_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            token_file = Path(temporary) / "url"
            with patch.object(dsh_launcher, "TOKEN_FILE", token_file), patch.object(dsh_launcher, "configured_port", return_value=3080):
                token = "aBc123_-" * 5 + "xyz"
                self.assertTrue(dsh_launcher.save_url(f"dsh web: http://127.0.0.1:3080/?token={token}\n"))
                self.assertEqual(token_file.read_text(), f"/?token={token}\n")
                self.assertEqual(token_file.stat().st_mode & 0o777, 0o600)
                self.assertFalse(dsh_launcher.save_url(f"dsh web: http://example.com:3080/?token={token}"))


if __name__ == "__main__":
    unittest.main()
