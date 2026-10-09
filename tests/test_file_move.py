import subprocess
import tempfile
import unittest
from pathlib import Path


HELPER = Path(__file__).resolve().parents[1] / "deploy/cockpit/huou07-move-files/move"


class FileMoveTests(unittest.TestCase):
    def run_move(self, source, destination):
        return subprocess.run([str(HELPER), str(source), str(destination)], capture_output=True, text=True, check=False)

    def test_moves_file_and_preserves_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_dir, destination = root / "source", root / "destination"
            source_dir.mkdir()
            destination.mkdir()
            source = source_dir / "notes.txt"
            source.write_text("move safely\n")

            result = self.run_move(source, destination)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(source.exists())
            self.assertEqual((destination / source.name).read_text(), "move safely\n")

    def test_moves_paths_with_spaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_dir, destination = root / "source folder", root / "target folder"
            source_dir.mkdir()
            destination.mkdir()
            source = source_dir / "my notes.txt"
            source.write_text("space-safe\n")

            result = self.run_move(source, destination)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(source.exists())
            self.assertEqual((destination / source.name).read_text(), "space-safe\n")

    def test_refuses_to_replace_an_existing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_dir, destination = root / "source", root / "destination"
            source_dir.mkdir()
            destination.mkdir()
            source = source_dir / "notes.txt"
            source.write_text("source\n")
            (destination / source.name).write_text("keep this\n")

            result = self.run_move(source, destination)

            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(source.exists())
            self.assertEqual((destination / source.name).read_text(), "keep this\n")

    def test_refuses_to_move_directory_into_itself(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "folder"
            destination = source / "child"
            source.mkdir()
            destination.mkdir()

            result = self.run_move(source, destination)

            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(source.is_dir())
            self.assertTrue(destination.is_dir())

    def test_rejects_non_absolute_paths_without_touching_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            result = self.run_move("relative.txt", destination)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("absolute", result.stderr)


if __name__ == "__main__":
    unittest.main()
