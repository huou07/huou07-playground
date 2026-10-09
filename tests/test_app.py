import json
import os
import platform
import sys
import threading
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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

    def test_wireguard_listener_discovers_only_private_wg0_ipv4_addresses(self):
        result = app.subprocess.CompletedProcess([], 0, stdout=json.dumps([
            {"ifname": "wg0", "addr_info": [
                {"family": "inet", "scope": "global", "local": "10.77.0.1", "prefixlen": 24},
                {"family": "inet", "scope": "global", "local": "8.8.8.8", "prefixlen": 24},
            ]},
            {"ifname": "wg1", "addr_info": [
                {"family": "inet", "scope": "global", "local": "10.88.0.1", "prefixlen": 24},
            ]},
        ]))
        with patch.object(app.shutil, "which", return_value="/usr/sbin/ip"), patch.object(app.subprocess, "run", return_value=result) as run:
            self.assertEqual(app.wireguard_interface_addresses(), ["10.77.0.1"])
        self.assertEqual(run.call_args.args[0], ["/usr/sbin/ip", "-j", "-4", "addr", "show", "dev", "wg0"])

    def test_wireguard_listener_falls_back_to_loopback_when_interface_is_unavailable(self):
        with patch.object(app.shutil, "which", return_value=None):
            self.assertEqual(app.wireguard_interface_addresses(), [])

    def test_wireguard_listener_ignores_malformed_address_data(self):
        result = app.subprocess.CompletedProcess([], 0, stdout=json.dumps([
            {"ifname": "wg0", "addr_info": "not a list"},
            {"ifname": "wg0", "addr_info": [
                {"family": "inet", "scope": "global", "local": None},
                {"family": "inet", "scope": "global", "local": "0.0.0.0"},
            ]},
        ]))
        with patch.object(app.shutil, "which", return_value="/usr/sbin/ip"), patch.object(app.subprocess, "run", return_value=result):
            self.assertEqual(app.wireguard_interface_addresses(), [])

    def test_wireguard_listener_falls_back_on_invalid_ip_output(self):
        result = app.subprocess.CompletedProcess([], 0, stdout=None)
        with patch.object(app.shutil, "which", return_value="/usr/sbin/ip"), patch.object(app.subprocess, "run", return_value=result):
            self.assertEqual(app.wireguard_interface_addresses(), [])

    def test_dsh_launch_url_only_targets_loopback_or_wireguard_dashboard_host(self):
        path = "/?token=" + "aBc123_-" * 5 + "xyz"
        self.assertEqual(app.dsh_launch_url(path, "127.0.0.1:8765"), f"http://127.0.0.1:3080{path}")
        self.assertEqual(app.dsh_launch_url(path, "127.0.0.1:18765"), f"http://127.0.0.1:3080{path}")
        with patch.object(app, "wireguard_interface_addresses", return_value=["10.8.0.1"]):
            self.assertEqual(app.dsh_launch_url(path, "10.8.0.1:8765"), f"http://10.8.0.1:3080{path}")
            self.assertIsNone(app.dsh_launch_url(path, "10.8.0.1:18765"))
            self.assertIsNone(app.dsh_launch_url(path, "192.168.1.10:8765"))
        self.assertIsNone(app.dsh_launch_url("/../etc/", "127.0.0.1:8765"))
        self.assertIsNone(app.dsh_launch_url("/token?target=https://example.test", "127.0.0.1:8765"))
        self.assertIsNone(app.dsh_launch_url("/?token=short", "127.0.0.1:8765"))
        self.assertIsNone(app.dsh_launch_url(path + "&target=evil", "127.0.0.1:8765"))
        self.assertIsNone(app.dsh_launch_url(path, "example.test:8765"))

    def test_interface_bound_listener_binds_socket_to_exact_device(self):
        server = object.__new__(app.InterfaceBoundHTTPServer)
        server.interface = "wg0"
        fake_socket = Mock()
        with patch.object(app.socket, "SO_BINDTODEVICE", 25, create=True), patch.object(app.HTTPServer, "server_bind"):
            server.socket = fake_socket
            app.InterfaceBoundHTTPServer.server_bind(server)
        fake_socket.setsockopt.assert_called_once_with(app.socket.SOL_SOCKET, 25, b"wg0\0")

    def test_private_proxy_binds_to_wireguard_and_only_fixed_application_ports(self):
        server = object.__new__(app.PrivateProxyServer)
        server.interface = "wg0"
        fake_socket = Mock()
        with patch.object(app.socket, "SO_BINDTODEVICE", 25, create=True), patch.object(app.socketserver.TCPServer, "server_bind"):
            server.socket = fake_socket
            app.PrivateProxyServer.server_bind(server)
        fake_socket.setsockopt.assert_called_once_with(app.socket.SOL_SOCKET, 25, b"wg0\0")
        self.assertEqual(app.PRIVATE_WG_PORTS, (
            (9090, 9090), (4000, 4000), (51821, 51821), (14096, 4096), (3080, 3080),
            (20128, 20128), (20129, 20129), (20132, 20132),
        ))

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
        self.assertEqual(disk_swap["total"], 1536 * 1024)
        self.assertEqual(disk_swap["used"], 384 * 1024)
        self.assertEqual(disk_swap["disk_total"], 1024 * 1024)
        self.assertEqual(disk_swap["disk_used"], 256 * 1024)
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
                self.assertEqual(json.load(response), {"available": True, "installed": True, "move_available": True})
        with patch("web.app.platform.system", return_value="Linux"), patch.object(app.Path, "is_file", autospec=True, side_effect=lambda path: str(path).endswith("/files/manifest.json")), patch("web.app.subprocess.run", return_value=app.subprocess.CompletedProcess([], 0)):
            with urlopen(f"{self.base}/api/files") as response:
                self.assertEqual(json.load(response), {"available": True, "installed": True, "move_available": False})
        with patch("web.app.platform.system", return_value="Linux"), patch.object(app.Path, "is_file", return_value=False):
            with urlopen(f"{self.base}/api/files") as response:
                result = json.load(response)
            self.assertEqual(result["available"], False)
            self.assertEqual(result["installed"], False)
            self.assertFalse(result["move_available"])
            self.assertIn("not installed", result["reason"])

    def test_app_registry_mutations_require_local_same_origin(self):
        body = json.dumps({"action": "add", "name": "Example", "app": {"name": "Example", "url": "http://127.0.0.1:4096", "description": "Test", "category": "Coding", "health_url": None, "management_url": None}}).encode()
        request = Request(f"{self.base}/api/apps", data=body, headers={"Origin": "http://attacker.invalid", "Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)

    def test_app_registry_mutations_allow_same_origin_on_the_bound_wireguard_address(self):
        self.assertTrue(app.dashboard_same_origin_request_allowed("http://10.77.0.1:8765", "10.77.0.1:8765", "10.77.0.1"))
        self.assertFalse(app.dashboard_same_origin_request_allowed("http://attacker.invalid:8765", "attacker.invalid:8765", "10.77.0.1"))
        self.assertFalse(app.dashboard_same_origin_request_allowed("http://10.77.0.2:8765", "10.77.0.2:8765", "10.77.0.1"))

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
        self.assertEqual(data["wireguard"], {"available": True, "connected": False, "state": "Status unavailable", "peer_count": 0, "listen_port": None})
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
            with patch("web.app.WG_EASY_UNIT", unit), patch("web.app.platform.system", return_value="Linux"), patch("web.app.shutil.which", return_value="/usr/bin/tailscale"), patch("web.app.wg_status_sample", return_value={"peer_count": 0, "latest_handshake_at": None, "listen_port": 51820}), patch("web.app.wg_easy_needs_setup", return_value=True), patch("web.app.subprocess.run", side_effect=[tailnet, active]):
                with urlopen(f"{self.base}/api/vpn") as response:
                    data = json.load(response)
        self.assertEqual(data["wireguard"], {"available": True, "connected": False, "state": "Needs owner setup", "peer_count": 0, "listen_port": 51820})
        self.assertEqual(data["tailscale"]["state"], "Disconnected")
        self.assertEqual(data["state"], "Needs owner setup")

    def test_vpn_status_reports_recent_wireguard_handshake_without_peer_identity(self):
        tailnet = app.subprocess.CompletedProcess([], 0, stdout=json.dumps({"BackendState": "Stopped"}))
        active = app.subprocess.CompletedProcess([], 0, stdout="")
        now = 1700000010
        with tempfile.TemporaryDirectory() as directory:
            unit = Path(directory) / "huou07-wg-easy.service"
            unit.touch()
            with patch("web.app.WG_EASY_UNIT", unit), patch("web.app.platform.system", return_value="Linux"), patch("web.app.shutil.which", return_value="/usr/bin/tailscale"), patch("web.app.wg_status_sample", return_value={"peer_count": 2, "latest_handshake_at": now - 10, "listen_port": 51820}), patch("web.app.subprocess.run", side_effect=[tailnet, active]), patch("web.app.time.time", return_value=now):
                with urlopen(f"{self.base}/api/vpn") as response:
                    payload = response.read().decode()
        data = json.loads(payload)
        self.assertEqual(data["wireguard"], {"available": True, "connected": True, "state": "Connected", "peer_count": 2, "listen_port": 51820, "last_handshake_seconds": 10})
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
            path.write_text(json.dumps({"available": True, "peer_count": 1, "latest_handshake_at": 1700000000, "listen_port": 51820, "sampled_at": 1700000000, "public_key": "private-peer-key"}))
            with patch.dict(os.environ, {"WG_STATUS_FILE": str(path)}), patch("web.app.time.time", return_value=1700000010):
                self.assertEqual(app.wg_status_sample(), {"peer_count": 1, "latest_handshake_at": 1700000000, "listen_port": 51820})
            path.write_text(json.dumps({"available": True, "peer_count": 1, "latest_handshake_at": 1700000000, "listen_port": 70000, "sampled_at": 1700000000}))
            with patch.dict(os.environ, {"WG_STATUS_FILE": str(path)}), patch("web.app.time.time", return_value=1700000010):
                self.assertIsNone(app.wg_status_sample())
            path.write_text(json.dumps({"available": True, "peer_count": 1, "latest_handshake_at": 1700000000, "listen_port": 51820, "sampled_at": 1700000000}))
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

    def test_app_icon_uses_only_a_registered_loopback_favicon_and_falls_back_cleanly(self):
        class IconHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/metadata/":
                    body = b'<html><head><link rel="icon" type="image/png" href="/icons/app.png"><link rel="icon" href="http://127.0.0.1:' + str(self.server.external_port).encode() + b'/favicon.ico"></head></html>'
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/icons/app.png":
                    body = b"local metadata icon"
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/favicon.ico":
                    self.send_response(302)
                    self.send_header("Location", self.server.redirect_target)
                    self.end_headers()
                elif self.path == "/icons/favicon.ico":
                    body = b"local icon"
                    self.send_response(200)
                    self.send_header("Content-Type", "image/x-icon")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/favicon.svg":
                    body = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M0 0h1v1H0z"/></svg>'
                    self.send_response(200)
                    self.send_header("Content-Type", "image/svg+xml")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_error(404)

            def log_message(self, fmt, *args):
                pass

        class ExternalIconHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.server.requests += 1
                self.send_response(200)
                self.send_header("Content-Type", "image/x-icon")
                self.end_headers()

            def log_message(self, fmt, *args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), ExternalIconHandler) as external_server, ThreadingHTTPServer(("127.0.0.1", 0), IconHandler) as icon_server, ThreadingHTTPServer(("127.0.0.1", 0), IconHandler) as redirect_server, tempfile.TemporaryDirectory() as directory:
            external_server.requests = 0
            icon_server.redirect_target = "/icons/favicon.ico"
            icon_server.external_port = external_server.server_port
            redirect_server.redirect_target = f"http://127.0.0.1:{external_server.server_port}/favicon.ico"
            servers = [external_server, icon_server, redirect_server]
            threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers]
            for thread in threads:
                thread.start()
            registry = Path(directory) / "apps.json"
            apps = [
                {"name": "Icon App", "url": f"http://127.0.0.1:{icon_server.server_port}/"},
                {"name": "Redirect App", "url": f"http://127.0.0.1:{redirect_server.server_port}/"},
                {"name": "Remote App", "url": "https://example.invalid/"},
                {"name": "Metadata App", "url": f"http://127.0.0.1:{icon_server.server_port}/metadata/"},
            ]
            registry.write_text(json.dumps({"apps": apps}))
            try:
                with patch.dict(os.environ, {"APPS_FILE": str(registry)}):
                    with urlopen(f"{self.base}/api/apps/icon?name=Icon%20App") as response:
                        self.assertEqual(response.headers.get_content_type(), "image/x-icon")
                        self.assertEqual(response.headers["Content-Security-Policy"], "default-src 'none'; sandbox")
                        self.assertEqual(response.read(), b"local icon")

                    with urlopen(f"{self.base}/api/apps/icon?name=Redirect%20App") as response:
                        self.assertEqual(response.headers.get_content_type(), "image/svg+xml")
                        self.assertIn(b"<svg", response.read())

                    with urlopen(f"{self.base}/api/apps/icon?name=Metadata%20App") as response:
                        self.assertEqual(response.headers.get_content_type(), "image/png")
                        self.assertEqual(response.read(), b"local metadata icon")
                    self.assertEqual(external_server.requests, 0)

                    with urlopen(f"{self.base}/api/apps/icon?name=Remote%20App") as response:
                        self.assertEqual(response.headers.get_content_type(), "image/gif")
                        self.assertEqual(response.read(), app.APP_ICON_PLACEHOLDER)
            finally:
                for server in servers:
                    server.shutdown()
                for thread in threads:
                    thread.join(timeout=2)

    def test_app_health_reports_authentication_required(self):
        error = HTTPError("http://127.0.0.1:4096/", 401, "Unauthorized", {}, None)
        opener = Mock()
        opener.open.side_effect = error
        with patch("web.app.build_opener", return_value=opener):
            self.assertEqual(app.app_health("http://127.0.0.1:4096/", "GET"), "authentication_required")

    def test_app_health_reports_setup_redirect_as_owner_setup_required(self):
        error = HTTPError("http://127.0.0.1:51821/", 307, "Temporary Redirect", {"Location": "/setup/1"}, None)
        opener = Mock()
        opener.open.side_effect = error
        with patch("web.app.build_opener", return_value=opener):
            self.assertEqual(app.app_health("http://127.0.0.1:51821/", "GET"), "setup_required")

    def test_app_health_keeps_non_setup_redirects_available(self):
        error = HTTPError("http://127.0.0.1:4000/", 302, "Temporary Redirect", {"Location": "/login"}, None)
        opener = Mock()
        opener.open.side_effect = error
        with patch("web.app.build_opener", return_value=opener):
            self.assertEqual(app.app_health("http://127.0.0.1:4000/", "GET"), "available")

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
