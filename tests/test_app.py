import json
import os
import platform
import sys
import threading
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web import app


class DashboardApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_health_endpoint(self):
        with urlopen(f"{self.base}/api/health") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response), {"ok": True})
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_metrics_report_supported_host_or_explicit_reason(self):
        with urlopen(f"{self.base}/api/metrics") as response:
            metrics = json.load(response)
        if metrics["supported"]:
            self.assertIn("cpu", metrics)
            self.assertIn("memory", metrics)
            self.assertIn("storage", metrics)
            self.assertIn("swap", metrics)
            self.assertIn("zram", metrics)
            self.assertIn("network", metrics)
            self.assertGreater(metrics["storage"]["total"], 0)
            self.assertGreater(metrics["cpu"]["logical_cores"], 0)
            if platform.system() == "Linux":
                host_uptime = float(Path("/proc/uptime").read_text().split()[0])
                self.assertLess(abs(metrics["system"]["uptime_seconds"] - host_uptime), 5)
        else:
            self.assertTrue(metrics["reason"])

    def test_turbostat_package_power_parses_summary_without_running_a_shell(self):
        app._power_sample = None
        result = app.subprocess.CompletedProcess([], 0, stdout="PkgWatt\n28.4\n", stderr="")
        with patch("web.app.shutil.which", return_value="/usr/bin/turbostat"), patch("web.app.subprocess.run", return_value=result) as run:
            self.assertEqual(app.cpu_package_power(), {"available": True, "watts": 28.4, "measurement": "CPU package power"})
        self.assertEqual(run.call_args.args[0], ["/usr/bin/turbostat", "--quiet", "--Summary", "--show", "PkgWatt", "--interval", "1", "--num_iterations", "1"])
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_turbostat_reports_missing_tool_and_permission_failure(self):
        app._power_sample = None
        with patch("web.app.shutil.which", return_value=None):
            self.assertIn("not installed", app.cpu_package_power()["reason"])
        app._power_sample = None
        denied = app.subprocess.CompletedProcess([], 0, stdout="PkgWatt\n-\n", stderr="turbostat: Failed to access /dev/cpu/0/msr.")
        with patch("web.app.shutil.which", return_value="/usr/bin/turbostat"), patch("web.app.subprocess.run", return_value=denied):
            result = app.cpu_package_power()
        self.assertFalse(result["available"])
        self.assertIn("permissions", result["reason"])

    def test_process_and_service_endpoints_exclude_command_arguments(self):
        with urlopen(f"{self.base}/api/processes") as response:
            processes = json.load(response)
        if processes["available"]:
            self.assertGreaterEqual(processes["total"], len(processes["processes"]))
            self.assertLessEqual(len(processes["processes"]), 1000)
            for process in processes["processes"]:
                self.assertIn("pid", process)
                self.assertIn("owner", process)
                self.assertNotIn("cmdline", process)
                self.assertNotIn("argv", process)
        else:
            self.assertTrue(processes["reason"])
        with urlopen(f"{self.base}/api/services") as response:
            services = json.load(response)
        if services["available"]:
            self.assertIsInstance(services["services"], list)
            if services["services"]:
                self.assertIn("active", services["services"][0])
        else:
            self.assertTrue(services["reason"])

    def test_cockpit_status_endpoint_is_read_only_and_reports_socket_state(self):
        with patch("web.app.platform.system", return_value="Linux"), patch("web.app.subprocess.run", return_value=app.subprocess.CompletedProcess([], 0)) as run:
            with urlopen(f"{self.base}/api/cockpit") as response:
                self.assertEqual(json.load(response)["available"], True)
            self.assertEqual(run.call_args.args[0], ["systemctl", "is-active", "--quiet", "cockpit.socket"])
        with patch("web.app.platform.system", return_value="Linux"), patch("web.app.subprocess.run", return_value=app.subprocess.CompletedProcess([], 3)):
            with urlopen(f"{self.base}/api/cockpit") as response:
                status = json.load(response)
            self.assertFalse(status["available"])
            self.assertTrue(status["reason"])

    def test_vpn_status_reports_tailnet_connection_without_private_details(self):
        result = app.subprocess.CompletedProcess([], 0, stdout=json.dumps({"BackendState": "Running", "Self": {"Online": True, "TailscaleIPs": ["100.64.0.1"]}, "Peer": {"private-host": {"DNSName": "private.example.invalid"}}}))
        with patch("web.app.platform.system", return_value="Linux"), patch("web.app.shutil.which", return_value="/usr/bin/tailscale"), patch("web.app.subprocess.run", return_value=result) as run:
            with urlopen(f"{self.base}/api/vpn") as response:
                payload = response.read().decode()
            self.assertEqual(json.loads(payload), {"available": True, "connected": True, "state": "Connected"})
            self.assertNotIn("100.64.0.1", payload)
            self.assertNotIn("private.example.invalid", payload)
            self.assertEqual(run.call_args.args[0], ["/usr/bin/tailscale", "status", "--json"])

    def test_vpn_status_degrades_when_client_is_unavailable(self):
        with patch("web.app.platform.system", return_value="Linux"), patch("web.app.shutil.which", return_value=None):
            with urlopen(f"{self.base}/api/vpn") as response:
                payload = json.load(response)
        self.assertFalse(payload["available"])
        self.assertFalse(payload["connected"])

    def test_app_registry_checks_configured_health_and_hides_probe_url(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "apps.json"
            path.write_text(json.dumps({"apps": [{"name": "Status", "url": "https://status.example.invalid", "category": "Tools", "description": "Private app", "management_url": "https://admin.example.invalid", "health_url": f"{self.base}/api/health"}]}))
            with patch.dict(os.environ, {"APPS_FILE": str(path)}):
                with urlopen(f"{self.base}/api/apps") as response:
                    data = json.load(response)
            self.assertTrue(data["available"])
            self.assertEqual(data["apps"][0]["status"], "available")
            self.assertEqual(data["apps"][0]["management_url"], "https://admin.example.invalid")
            self.assertNotIn("health_url", data["apps"][0])

    def test_app_registry_rejects_script_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "apps.json"
            path.write_text(json.dumps({"apps": [{"name": "Unsafe", "url": "javascript:alert(1)"}]}))
            with patch.dict(os.environ, {"APPS_FILE": str(path)}):
                with urlopen(f"{self.base}/api/apps") as response:
                    data = json.load(response)
            self.assertFalse(data["available"])
            self.assertEqual(data["apps"], [])

    def test_app_registry_rejects_script_management_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "apps.json"
            path.write_text(json.dumps({"apps": [{"name": "Unsafe", "url": "https://example.invalid", "management_url": "javascript:alert(1)"}]}))
            with patch.dict(os.environ, {"APPS_FILE": str(path)}):
                with urlopen(f"{self.base}/api/apps") as response:
                    data = json.load(response)
            self.assertFalse(data["available"])
            self.assertEqual(data["apps"], [])

    def test_static_page_has_security_headers_and_no_path_escape(self):
        with urlopen(f"{self.base}/") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
            self.assertIn("<title>Workspace</title>", response.read().decode())
        with self.assertRaises(HTTPError) as error:
            urlopen(f"{self.base}/%2e%2e/app.py")
        self.assertEqual(error.exception.code, 404)

    def test_server_refuses_non_loopback_listener(self):
        with patch.dict(os.environ, {"HOST": "0.0.0.0"}):
            with self.assertRaisesRegex(SystemExit, "Only loopback binding"):
                app.main()


if __name__ == "__main__":
    unittest.main()
