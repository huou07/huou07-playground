import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "huou07-ssh-tunnel"


class SshTunnelTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.bin_dir = Path(self.tempdir.name)
        fake_ssh = self.bin_dir / "ssh"
        fake_ssh.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "Path(os.environ['SSH_ARGS_FILE']).write_text(json.dumps(sys.argv[1:]))\n"
        )
        fake_ssh.chmod(0o755)
        self.args_file = self.bin_dir / "args.json"
        self.env = dict(os.environ, PATH=f"{self.bin_dir}:{os.environ['PATH']}", SSH_ARGS_FILE=str(self.args_file))

    def run_tunnel(self, *args):
        return subprocess.run([str(SCRIPT), *args], env=self.env, capture_output=True, text=True)

    def assert_forwards(self, args, expected):
        self.assertEqual(args[:2], ["-N", "-T"])
        self.assertIn("ExitOnForwardFailure=yes", args)
        self.assertIn("ServerAliveInterval=30", args)
        self.assertIn("ServerAliveCountMax=3", args)
        self.assertEqual(args.count("-L"), len(expected))
        forwards = [args[index + 1] for index, value in enumerate(args[:-1]) if value == "-L"]
        self.assertEqual(forwards, list(expected))
        self.assertEqual(args[-1], "an3-dell")
        self.assertNotIn("StrictHostKeyChecking=no", args)

    def test_full_mode_forwards_all_dashboard_and_application_ports(self):
        result = self.run_tunnel("an3-dell")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.args_file.read_text())
        self.assert_forwards(args, (
            "127.0.0.1:8765:127.0.0.1:8765",
            "127.0.0.1:9090:127.0.0.1:9090",
            "127.0.0.1:4000:127.0.0.1:4000",
            "127.0.0.1:51821:127.0.0.1:51821",
            "127.0.0.1:14096:127.0.0.1:4096",
            "127.0.0.1:20128:127.0.0.1:20128",
            "127.0.0.1:20129:127.0.0.1:20129",
            "127.0.0.1:20132:127.0.0.1:20132",
        ))

    def test_omniroute_mode_adds_only_its_ports(self):
        result = self.run_tunnel("--omniroute-only", "an3-dell")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.args_file.read_text())
        self.assert_forwards(args, (
            "127.0.0.1:20128:127.0.0.1:20128",
            "127.0.0.1:20129:127.0.0.1:20129",
            "127.0.0.1:20132:127.0.0.1:20132",
        ))

    def test_invalid_arguments_fail_before_running_ssh(self):
        for args in ((), ("--bad", "an3-dell"), ("--omniroute-only",), ("-host",)):
            with self.subTest(args=args):
                result = self.run_tunnel(*args)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.args_file.exists())


if __name__ == "__main__":
    unittest.main()
