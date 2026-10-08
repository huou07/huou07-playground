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
            self.assertIn("storage_devices", metrics)
            self.assertIsInstance(metrics["storage_devices"], list)
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

    def test_storage_devices_report_physical_device_without_identifiers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            disk = root / "nvme0n1"
            (disk / "device").mkdir(parents=True)
            (disk / "queue").mkdir()
            (disk / "size").write_text("200")
            (disk / "queue/rotational").write_text("0")
            (disk / "device/model").write_text("Example NVMe\nDrive")
            virtual = root / "loop0"
            virtual.mkdir()
            (virtual / "size").write_text("100")
            devices = app.storage_devices(root)
        self.assertEqual(devices, [{"name": "nvme0n1", "model": "Example NVMe Drive", "kind": "SSD", "size": 200 * 512}])
        self.assertNotIn("serial", devices[0])

    def test_nvidia_gpu_metrics_parse_utilization_vram_and_temperature(self):
        result = app.subprocess.CompletedProcess([], 0, stdout="NVIDIA GeForce RTX 4090, 38, 4096, 8192, 55\n", stderr="")
        with patch("web.app.platform.system", return_value="Linux"), patch("web.app.shutil.which", return_value="/usr/bin/nvidia-smi"), patch("web.app.subprocess.run", return_value=result) as run:
            metrics = app.gpu_metrics()
        self.assertEqual(metrics, {"available": True, "model": "NVIDIA GeForce RTX 4090", "usage_percent": 38, "memory_used": 4096 * 1024 * 1024, "memory_total": 8192 * 1024 * 1024, "temperature_c": 55})
        self.assertEqual(run.call_args.args[0], ["/usr/bin/nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"])
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_nvidia_gpu_metrics_degrade_when_utility_is_missing(self):
        with patch("web.app.platform.system", return_value="Linux"), patch("web.app.shutil.which", return_value=None):
            metrics = app.gpu_metrics()
        self.assertFalse(metrics["available"])
        self.assertIn("nvidia-smi", metrics["reason"])

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
