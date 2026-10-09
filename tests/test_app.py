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
from urllib.request import Request, urlopen
from unittest.mock import Mock, patch

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

    def test_swap_and_zram_metrics_keep_disk_and_compressed_memory_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            device = Path(temporary) / "zram0"
            device.mkdir()
            (device / "disksize").write_text("524288")
            (device / "mm_stat").write_text("300000 125000 140000 0 0 0 0 0 0")
            swaps_text = "Filename Type Size Used Priority\n/dev/nvme0n1p3 partition 1024 256 -1\n/dev/zram0 partition 512 128 100\n"
            disk_swap, zram = app.swap_and_zram_metrics(swaps_text, Path(temporary))
        self.assertEqual(disk_swap["total"], 1024 * 1024)
        self.assertEqual(disk_swap["used"], 256 * 1024)
        self.assertEqual(zram["total"], 524288)
        self.assertEqual(zram["used"], 300000)
        self.assertEqual(zram["compressed"], 125000)
        self.assertEqual(zram["physical_used"], 140000)
        self.assertEqual(zram["swap_total"], 512 * 1024)
        self.assertEqual(zram["swap_used"], 128 * 1024)

    def test_nvidia_gpu_metrics_parse_utilization_vram_and_temperature(self):
        result = app.subprocess.CompletedProcess([], 0, stdout="NVIDIA GeForce RTX 4090, 38, 4096, 8192, 55\n", stderr="")
        with patch("web.app.platform.system", return_value="Linux"), patch("web.app.shutil.which", return_value="/usr/bin/nvidia-smi"), patch("web.app.subprocess.run", return_value=result) as run:
            metrics = app.gpu_metrics()
        self.assertEqual(metrics, {"available": True, "model": "NVIDIA GeForce RTX 4090", "usage_percent": 38, "memory_used": 4096 * 1024 * 1024, "memory_total": 8192 * 1024 * 1024, "temperature_c": 55})
        self.assertEqual(run.call_args.args[0], ["/usr/bin/nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"])
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_gpu_metrics_fall_back_to_intel_when_nvidia_tool_is_missing(self):
        with patch("web.app.platform.system", return_value="Linux"), patch("web.app.shutil.which", return_value=None):
            with patch("web.app.intel_gpu_metrics", return_value={"available": False, "reason": "No current Intel GPU sample is available."}) as intel:
                metrics = app.gpu_metrics()
        self.assertFalse(metrics["available"])
        self.assertIn("Intel", metrics["reason"])
        intel.assert_called_once_with()

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

    def test_files_endpoint_reports_installed_package_and_cockpit_availability(self):
        with patch("web.app.platform.system", return_value="Linux"), patch.object(app.Path, "is_file", return_value=True), patch("web.app.subprocess.run", return_value=app.subprocess.CompletedProcess([], 0)):
            with urlopen(f"{self.base}/api/files") as response:
                self.assertEqual(json.load(response), {"available": True, "installed": True})
        with patch("web.app.platform.system", return_value="Linux"), patch.object(app.Path, "is_file", return_value=False):
            with urlopen(f"{self.base}/api/files") as response:
                result = json.load(response)
            self.assertEqual(result["available"], False)
            self.assertEqual(result["installed"], False)
            self.assertIn("not installed", result["reason"])

    def test_app_registry_mutations_require_local_same_origin(self):
        body = json.dumps({"action": "add", "name": "Example", "app": {"name": "Example", "url": "http://127.0.0.1:4096", "description": "Test", "category": "Coding", "health_url": None, "management_url": None}}).encode()
        request = Request(f"{self.base}/api/apps", data=body, headers={"Origin": "http://attacker.invalid", "Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)

    def test_app_registry_update_preserves_health_probe_and_limits_it_to_loopback(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "apps.json"
            registry.write_text(json.dumps({"apps": [{"name": "Example", "url": "http://127.0.0.1:4096", "description": "Old", "category": "Coding", "health_url": "http://127.0.0.1:9/health", "health_method": "GET", "management_url": None}]}))
            payload = {"action": "update", "name": "Example", "app": {"name": "OpenCode", "url": "http://127.0.0.1:4096", "description": "Coding workspace", "category": "Coding", "management_url": None}}
            request = Request(f"{self.base}/api/apps", data=json.dumps(payload).encode(), headers={"Origin": self.base, "Content-Type": "application/json"})
            with patch.dict(os.environ, {"APPS_FILE": str(registry)}):
                with urlopen(request) as response:
                    data = json.load(response)
                self.assertEqual(data["apps"][0]["name"], "OpenCode")
                self.assertNotIn("health_url", data["apps"][0])
                stored = json.loads(registry.read_text())["apps"][0]
                self.assertEqual(stored["health_url"], "http://127.0.0.1:9/health")
                invalid = {"action": "add", "name": "Other", "app": {"name": "Other", "url": "http://127.0.0.1:3000", "health_url": "http://192.168.1.1:3000"}}
                request = Request(f"{self.base}/api/apps", data=json.dumps(invalid).encode(), headers={"Origin": self.base, "Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as error:
                    urlopen(request)
                self.assertEqual(error.exception.code, 400)

    def test_app_registry_add_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "apps.json"
            registry.write_text('{"apps":[]}')
            headers = {"Origin": self.base, "Content-Type": "application/json"}
            app_data = {"name": "OpenCode", "url": "http://127.0.0.1:4096", "description": "Coding workspace", "category": "Coding", "health_url": None, "management_url": None}
            with patch.dict(os.environ, {"APPS_FILE": str(registry)}):
                request = Request(f"{self.base}/api/apps", data=json.dumps({"action": "add", "name": "OpenCode", "app": app_data}).encode(), headers=headers)
                with urlopen(request) as response:
                    self.assertEqual(json.load(response)["total"], 1)
                request = Request(f"{self.base}/api/apps", data=json.dumps({"action": "delete", "name": "OpenCode"}).encode(), headers=headers)
                with urlopen(request) as response:
                    self.assertEqual(json.load(response)["total"], 0)
            self.assertEqual(json.loads(registry.read_text())["apps"], [])

    def test_vpn_status_reports_tailnet_connection_without_private_details(self):
        result = app.subprocess.CompletedProcess([], 0, stdout=json.dumps({"BackendState": "Running", "Self": {"Online": True, "TailscaleIPs": ["100.64.0.1"]}, "Peer": {"private-host": {"DNSName": "private.example.invalid"}}}))
        with tempfile.TemporaryDirectory() as directory:
            unit = Path(directory) / "huou07-wg-easy.service"
            unit.touch()
            with patch("web.app.WG_EASY_UNIT", unit), patch("web.app.platform.system", return_value="Linux"), patch("web.app.shutil.which", side_effect=lambda name: "/usr/bin/tailscale" if name == "tailscale" else None), patch("web.app.wg_status_sample", return_value=None), patch("web.app.wg_easy_needs_setup", return_value=False), patch("web.app.subprocess.run", return_value=result) as run:
                with urlopen(f"{self.base}/api/vpn") as response:
                    payload = response.read().decode()
        data = json.loads(payload)
        self.assertEqual(data["tailscale"], {"available": True, "connected": True, "state": "Connected"})
        self.assertEqual(data["wireguard"], {"available": True, "connected": False, "state": "Status unavailable", "peer_count": 0})
        self.assertEqual(data["state"], "Status unavailable")
        self.assertNotIn("100.64.0.1", payload)
        self.assertNotIn("private.example.invalid", payload)
        self.assertEqual(run.call_args.args[0], ["systemctl", "is-active", "--quiet", app.WG_EASY_SERVICE])

    def test_vpn_status_reports_wireguard_setup_without_peer_details(self):
        tailnet = app.subprocess.CompletedProcess([], 0, stdout=json.dumps({"BackendState": "Stopped"}))
        active = app.subprocess.CompletedProcess([], 0, stdout="")
        with tempfile.TemporaryDirectory() as directory:
            unit = Path(directory) / "huou07-wg-easy.service"
            unit.touch()
            with patch("web.app.WG_EASY_UNIT", unit), patch("web.app.platform.system", return_value="Linux"), patch("web.app.shutil.which", return_value="/usr/bin/tailscale"), patch("web.app.wg_status_sample", return_value={"peer_count": 0, "latest_handshake_at": None}), patch("web.app.wg_easy_needs_setup", return_value=True), patch("web.app.subprocess.run", side_effect=[tailnet, active]):
                with urlopen(f"{self.base}/api/vpn") as response:
                    data = json.load(response)
        self.assertEqual(data["wireguard"], {"available": True, "connected": False, "state": "Needs owner setup", "peer_count": 0})
        self.assertEqual(data["tailscale"]["state"], "Disconnected")
        self.assertEqual(data["state"], "Needs owner setup")

    def test_vpn_status_reports_recent_wireguard_handshake_without_peer_identity(self):
        tailnet = app.subprocess.CompletedProcess([], 0, stdout=json.dumps({"BackendState": "Stopped"}))
        active = app.subprocess.CompletedProcess([], 0, stdout="")
        now = 1700000010
        with tempfile.TemporaryDirectory() as directory:
            unit = Path(directory) / "huou07-wg-easy.service"
            unit.touch()
            with patch("web.app.WG_EASY_UNIT", unit), patch("web.app.platform.system", return_value="Linux"), patch("web.app.shutil.which", return_value="/usr/bin/tailscale"), patch("web.app.wg_status_sample", return_value={"peer_count": 2, "latest_handshake_at": now - 10}), patch("web.app.subprocess.run", side_effect=[tailnet, active]), patch("web.app.time.time", return_value=now):
                with urlopen(f"{self.base}/api/vpn") as response:
                    payload = response.read().decode()
        data = json.loads(payload)
        self.assertEqual(data["wireguard"], {"available": True, "connected": True, "state": "Connected", "peer_count": 2, "last_handshake_seconds": 10})
        self.assertNotIn("public-key", payload)

    def test_vpn_status_degrades_when_clients_are_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            unit = Path(directory) / "missing.service"
            with patch("web.app.WG_EASY_UNIT", unit), patch("web.app.platform.system", return_value="Linux"), patch("web.app.shutil.which", return_value=None):
                with urlopen(f"{self.base}/api/vpn") as response:
                    payload = json.load(response)
        self.assertFalse(payload["available"])
        self.assertFalse(payload["connected"])
        self.assertEqual(payload["wireguard"]["state"], "Not installed")
        self.assertEqual(payload["tailscale"]["state"], "Unavailable")

    def test_wg_easy_setup_detection_recognizes_only_setup_redirects(self):
        class Opener:
            def __init__(self, location):
                self.location = location

            def open(self, request, timeout):
                headers = {"Location": self.location}
                raise app.HTTPError(request.full_url, 302, "Found", headers, None)

        with patch("web.app.build_opener", side_effect=lambda *args: Opener("/setup/1")):
            self.assertTrue(app.wg_easy_needs_setup())
        with patch("web.app.build_opener", side_effect=lambda *args: Opener("/login")):
            self.assertFalse(app.wg_easy_needs_setup())

    def test_wg_status_sample_rejects_stale_data_and_returns_only_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text(json.dumps({"available": True, "peer_count": 1, "latest_handshake_at": 1700000000, "sampled_at": 1700000000, "public_key": "private-peer-key"}))
            with patch.dict(os.environ, {"WG_STATUS_FILE": str(path)}), patch("web.app.time.time", return_value=1700000010):
                self.assertEqual(app.wg_status_sample(), {"peer_count": 1, "latest_handshake_at": 1700000000})
            with patch.dict(os.environ, {"WG_STATUS_FILE": str(path)}), patch("web.app.time.time", return_value=1700000100):
                self.assertIsNone(app.wg_status_sample())

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

    def test_app_health_reports_authentication_required(self):
        error = HTTPError("http://127.0.0.1:4096/", 401, "Unauthorized", {}, None)
        opener = Mock()
        opener.open.side_effect = error
        with patch("web.app.build_opener", return_value=opener):
            self.assertEqual(app.app_health("http://127.0.0.1:4096/", "GET"), "authentication_required")

    def test_app_health_reports_redirecting_setup_page_as_available(self):
        error = HTTPError("http://127.0.0.1:51821/", 307, "Temporary Redirect", {}, None)
        opener = Mock()
        opener.open.side_effect = error
        with patch("web.app.build_opener", return_value=opener):
            self.assertEqual(app.app_health("http://127.0.0.1:51821/", "GET"), "available")

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
            html = response.read().decode()
            self.assertIn("<title>Home · huou07 playground</title>", html)
            self.assertIn('src="/navigation.js"', html)
            for route in ("home", "apps", "system", "services", "files", "ssh", "network", "storage", "settings"):
                self.assertIn(f'data-view="{route}"', html)
        with self.assertRaises(HTTPError) as error:
            urlopen(f"{self.base}/%2e%2e/app.py")
        self.assertEqual(error.exception.code, 404)

    def test_server_refuses_non_loopback_listener(self):
        with patch.dict(os.environ, {"HOST": "0.0.0.0"}):
            with self.assertRaisesRegex(SystemExit, "Only loopback binding"):
                app.main()


if __name__ == "__main__":
    unittest.main()
