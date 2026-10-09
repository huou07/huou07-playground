import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


HELPER = Path(__file__).resolve().parents[1] / "deploy/cockpit/huou07-move-files/list"


class FileListTests(unittest.TestCase):
    def run_list(self, path):
        return subprocess.run([str(HELPER), str(path)], capture_output=True, text=True, check=False)

    def test_lists_directories_first_and_preserves_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "b file").write_text("content")
            (root / "Alpha").mkdir()
            (root / "hidden").write_text("hidden")
            (root / ".hidden").write_text("dot file")
            (root / "line\nbreak").write_text("newline name")
            try:
                (root / "linked-folder").symlink_to(root / "Alpha", target_is_directory=True)
            except OSError:
                pass

            result = self.run_list(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            listing = json.loads(result.stdout)
            self.assertEqual(listing["path"], os.path.realpath(root))
            self.assertEqual([entry["name"] for entry in listing["entries"][:2]], ["Alpha", "linked-folder"] if (root / "linked-folder").is_symlink() else ["Alpha", ".hidden"])
            names = {entry["name"]: entry for entry in listing["entries"]}
            self.assertTrue(names["Alpha"]["directory"])
            self.assertIn("line\nbreak", names)
            if (root / "linked-folder").is_symlink():
                self.assertTrue(names["linked-folder"]["directory"])
                self.assertTrue(names["linked-folder"]["symlink"])

    def test_rejects_relative_and_missing_directories(self):
        relative = self.run_list("relative")
        missing = self.run_list("/huou07-test-directory-that-does-not-exist")
        self.assertNotEqual(relative.returncode, 0)
        self.assertIn("absolute", relative.stderr)
        self.assertNotEqual(missing.returncode, 0)


if __name__ == "__main__":
    unittest.main()
