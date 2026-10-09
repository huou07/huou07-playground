import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy import wg_status


class WireGuardStatusTests(unittest.TestCase):
    def test_parser_returns_peer_count_and_latest_handshake_only(self):
        output = "public-key-one\t0\npublic-key-two\t1700000000\npublic-key-three\t1699999990\ninvalid\n"
        self.assertEqual(wg_status.parse_latest_handshakes(output), (3, 1700000000))

    def test_collector_uses_fixed_command_and_never_returns_peer_keys(self):
        result = wg_status.subprocess.CompletedProcess([], 0, stdout="public-key-one\t1700000000\n")
        with patch("deploy.wg_status.subprocess.run", return_value=result) as run, patch("deploy.wg_status.time.time", return_value=1700000010):
            sample = wg_status.collect_status("/usr/bin/wg")
        self.assertEqual(sample, {"available": True, "peer_count": 1, "latest_handshake_at": 1700000000, "sampled_at": 1700000010})
        self.assertNotIn("public-key-one", json.dumps(sample))
        self.assertEqual(run.call_args.args[0], ["/usr/bin/wg", "show", "wg0", "latest-handshakes"])

    def test_collector_reports_empty_interface_and_command_failure(self):
        empty = wg_status.subprocess.CompletedProcess([], 0, stdout="")
        failed = wg_status.subprocess.CompletedProcess([], 1, stdout="private diagnostic")
        self.assertEqual(wg_status.collect_status("/usr/bin/wg", run=lambda *a, **k: empty)["peer_count"], 0)
        self.assertEqual(wg_status.collect_status("/usr/bin/wg", run=lambda *a, **k: failed), {"available": False})

    def test_status_write_is_atomic_and_world_readable_without_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            wg_status.write_status(path, {"available": True, "peer_count": 0, "latest_handshake_at": None, "sampled_at": 1700000000})
            self.assertEqual(json.loads(path.read_text())["peer_count"], 0)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(list(path.parent.glob(".status-*")), [])


if __name__ == "__main__":
    unittest.main()
