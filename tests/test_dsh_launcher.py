import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "deploy" / "dsh-launcher.py"
SPEC = importlib.util.spec_from_file_location("dsh_launcher", MODULE_PATH)
dsh_launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dsh_launcher)


class DshLauncherTests(unittest.TestCase):
    def test_dsh_port_and_environment_are_explicitly_isolated(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "private-services.json"
            config.write_text('{"version":1,"services":[{"id":"dsh","backend_port":3080,"wireguard_port":13080}]}')
            with patch.object(dsh_launcher, "PORT_CONFIG", config):
                self.assertEqual(dsh_launcher.configured_port("dsh"), 3080)
                self.assertEqual(dsh_launcher.configured_port("dsh", "wireguard_port"), 13080)
        environment = dsh_launcher.child_environment({"USER": "root", "LOGNAME": "root", "CODEX_HOME": "/root/.codex", "PATH": "/bin"})
        self.assertEqual(environment["USER"], "huou07-dsh")
        self.assertEqual(environment["LOGNAME"], "huou07-dsh")
        self.assertEqual(environment["HOME"], str(dsh_launcher.STATE))
        self.assertEqual(environment["CODEX_HOME"], str(dsh_launcher.STATE / ".codex"))
        self.assertTrue(environment["CODEX_HOME"].startswith(environment["HOME"] + "/"))

    def test_saves_only_a_single_well_formed_process_token(self):
        with tempfile.TemporaryDirectory() as temporary:
            token_file = Path(temporary) / "url"
            with patch.object(dsh_launcher, "TOKEN_FILE", token_file), patch.object(dsh_launcher, "configured_port", return_value=3080), patch.object(dsh_launcher.os, "chown"):
                line = "dsh web: http://127.0.0.1:3080/?token=" + "aBc123_-" * 5 + "xyz\n"
                self.assertTrue(dsh_launcher.save_url(line))
                self.assertEqual(token_file.read_text(), "/?token=" + "aBc123_-" * 5 + "xyz\n")
                self.assertEqual(token_file.stat().st_mode & 0o777, 0o440)

    def test_rejects_external_hosts_extra_query_fields_and_path_tokens(self):
        cases = (
            "dsh web: https://127.0.0.1:3080/?token=" + "a" * 43,
            "dsh web: http://127.0.0.1:3080/?token=" + "a" * 43 + "&next=evil",
            "dsh web: http://127.0.0.1:3080/" + "a" * 43,
            "dsh web: http://127.0.0.1:3080/?token=short",
        )
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(dsh_launcher, "TOKEN_FILE", Path(temporary) / "url"), patch.object(dsh_launcher, "configured_port", return_value=3080):
                for line in cases:
                    with self.subTest(line=line.split("?")[0]):
                        self.assertFalse(dsh_launcher.save_url(line))


if __name__ == "__main__":
    unittest.main()
