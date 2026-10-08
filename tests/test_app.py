import json
import os
import platform
import sys
import threading
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
