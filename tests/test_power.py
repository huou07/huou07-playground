import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy import power
from web import app


class PowerTelemetryTests(unittest.TestCase):
    def test_collector_parses_package_watts_with_fixed_shell_free_command(self):
        result = CompletedProcess([], 0, stdout="PkgWatt\n28.4\n", stderr="")

        def run(args, **kwargs):
            self.assertEqual(args, ["/usr/sbin/turbostat", "--quiet", "--Summary", "--show", "PkgWatt", "--interval", "1", "--num_iterations", "1"])
            self.assertFalse(kwargs.get("shell", False))
            return result

        with patch("deploy.power.shutil.which", return_value="/usr/sbin/turbostat"):
            sample = power.collect_power(run=run)
        self.assertEqual(sample, {"available": True, "watts": 28.4, "measurement": "CPU package power"})

    def test_collector_reports_device_permission_denial_even_when_turbostat_exits_zero(self):
        result = CompletedProcess([], 0, stdout="", stderr="turbostat: Failed to access /dev/cpu/0/msr.")
        with patch("deploy.power.shutil.which", return_value="/usr/sbin/turbostat"), patch("deploy.power.subprocess.run", return_value=result):
            sample = power.collect_power()
        self.assertIn("cannot read", sample["reason"])

    def test_collector_reports_missing_binary_and_rejects_invalid_power(self):
        with patch("deploy.power.shutil.which", return_value=None):
            self.assertIn("not installed", power.collect_power()["reason"])
        result = CompletedProcess([], 0, stdout="PkgWatt\n2001\n", stderr="")
        with patch("deploy.power.shutil.which", return_value="/usr/sbin/turbostat"), patch("deploy.power.subprocess.run", return_value=result):
            self.assertFalse(power.collect_power()["available"])

    def test_root_collector_writes_one_world_readable_atomic_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.json"
            power.write_sample(path, {"available": True, "watts": 18.3})
            self.assertEqual(json.loads(path.read_text())["watts"], 18.3)
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
            self.assertEqual(sorted(item.name for item in path.parent.iterdir()), ["sample.json"])

    def test_dashboard_reads_only_a_recent_sanitized_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.json"
            with patch.dict(os.environ, {"POWER_FILE": str(path)}):
                path.write_text(json.dumps({"available": True, "watts": 18.34, "sampled_at": time.time()}))
                self.assertEqual(app.cpu_package_power(), {"available": True, "watts": 18.3, "measurement": "CPU package power"})
                path.write_text(json.dumps({"available": True, "watts": 18.3, "sampled_at": 0}))
                self.assertIn("No current", app.cpu_package_power()["reason"])


if __name__ == "__main__":
    unittest.main()
