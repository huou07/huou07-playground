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
    def test_saves_only_a_single_well_formed_process_token(self):
        with tempfile.TemporaryDirectory() as temporary:
            token_file = Path(temporary) / "url"
            with patch.object(dsh_launcher, "TOKEN_FILE", token_file), patch.object(dsh_launcher.os, "chown"):
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
            with patch.object(dsh_launcher, "TOKEN_FILE", Path(temporary) / "url"):
                for line in cases:
                    with self.subTest(line=line.split("?")[0]):
                        self.assertFalse(dsh_launcher.save_url(line))


if __name__ == "__main__":
    unittest.main()
