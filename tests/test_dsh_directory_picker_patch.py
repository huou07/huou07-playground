from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy import patch_dsh_directory_picker as picker_patch


class DshDirectoryPickerPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.package = Path(self.temp.name) / "picker"
        self.package.mkdir()
        (self.package / "package.json").write_text(json.dumps({"version": picker_patch.VERSION}))
        self.source = self.package / "lib/host.js"
        self.source.parent.mkdir()
        self.source.write_text("\n".join(old for old, _ in picker_patch.REPLACEMENTS))
        self.package_patch = patch.object(picker_patch, "PACKAGE", self.package)
        self.source_patch = patch.object(picker_patch, "SOURCE", self.source)
        self.package_patch.start()
        self.source_patch.start()

    def tearDown(self) -> None:
        self.source_patch.stop()
        self.package_patch.stop()
        self.temp.cleanup()

    def test_patch_is_idempotent_and_scopes_web_picker(self) -> None:
        with patch.object(sys, "argv", ["patch", "apply"]):
            self.assertEqual(picker_patch.main(), 0)
        patched = self.source.read_text()
        with patch.object(sys, "argv", ["patch", "apply"]):
            self.assertEqual(picker_patch.main(), 0)
        self.assertEqual(self.source.read_text(), patched)
        self.assertIn("outside the approved workspace", patched)
        self.assertIn(picker_patch.ROOT, patched)

    def test_refuses_unknown_upstream_source(self) -> None:
        self.source.write_text("unexpected upstream source")
        with patch.object(sys, "argv", ["patch", "apply"]):
            self.assertEqual(picker_patch.main(), 1)


if __name__ == "__main__":
    unittest.main()
