from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy import patch_dsh_workspace_policy as policy_patch


class DshWorkspacePolicyPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.package = self.root / "node_modules/@deepseek-ai/dsh-sandbox-policy"
        self.package.mkdir(parents=True)
        (self.package / "package.json").write_text(json.dumps({"version": policy_patch.EXPECTED_VERSION}))
        self.policy = self.package / "lib/index.js"
        self.policy.parent.mkdir()
        self.policy.write_text(
            policy_patch.OLD_IMPORT
            + "\n"
            + policy_patch.OLD_FUNCTION
            + "\n"
            + policy_patch.OLD_EXPORT
            + "\n"
        )
        self.patchers = (
            patch.object(policy_patch, "PACKAGE", self.package),
            patch.object(policy_patch, "POLICY", self.policy),
        )
        for item in self.patchers:
            item.start()

    def tearDown(self) -> None:
        for item in self.patchers:
            item.stop()
        self.temp.cleanup()

    def test_patch_is_idempotent(self) -> None:
        with patch.object(sys, "argv", ["patch", "apply"]):
            self.assertEqual(policy_patch.main(), 0)
        patched = self.policy.read_text()
        with patch.object(sys, "argv", ["patch", "apply"]):
            self.assertEqual(policy_patch.main(), 0)
        self.assertEqual(self.policy.read_text(), patched)
        self.assertIn("outside /srv/huou07-dsh-workspaces", patched)

    def test_refuses_unknown_upstream_source(self) -> None:
        self.policy.write_text("unexpected upstream change")
        with patch.object(sys, "argv", ["patch", "apply"]):
            self.assertEqual(policy_patch.main(), 1)


if __name__ == "__main__":
    unittest.main()
