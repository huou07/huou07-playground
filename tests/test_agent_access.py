import base64
import hashlib
import http.client
import json
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from web.agent_access import AgentAccessServer


class AgentAccessTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.temp = tempfile.TemporaryDirectory()
        self.token = Path(self.temp.name) / "url"
        self.token.write_text("/?token=" + "A" * 40)
        requests = self.requests

        class Backend(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                requests.append((self.path, dict(self.headers)))
                if self.path.startswith("/?token="):
                    self.send_response(303)
                    self.send_header("Set-Cookie", self.server.cookie_name + "=v1.fixture.signature; Max-Age=86400; HttpOnly")
                    self.send_header("Set-Cookie", "owner-admin=must-not-forward; Path=/")
                    self.send_header("Location", "./")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if self.path == "/" and self.server.cookie_name not in self.headers.get("Cookie", ""):
                    self.send_response(401)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if self.path == "/ws":
                    self.send_response(101)
                    self.send_header("Upgrade", "websocket")
                    self.send_header("Connection", "Upgrade")
                    value = self.headers["Sec-WebSocket-Key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                    self.send_header("Sec-WebSocket-Accept", base64.b64encode(hashlib.sha1(value.encode()).digest()).decode())
                    self.end_headers()
                    self.wfile.write(self.rfile.read(4))
                    self.wfile.flush()
                    self.close_connection = True
                    return
                if self.path == "/sse":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    self.wfile.write(b"9\r\ndata: x\n\n\r\n0\r\n\r\n")
                    self.wfile.flush()
                    return
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                requests.append((self.path, dict(self.headers)))
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        self.proxy = AgentAccessServer(("127.0.0.1", 0), backend_port=self.backend.server_port,
                                       owner_username="owner", owner_password="owner-fixture", token_file=self.token)
        self.backend.cookie_name = self.proxy.cookie_name
        self.auth = "Basic " + base64.b64encode(b"owner:owner-fixture").decode()
        for server in [self.backend, self.proxy]:
            threading.Thread(target=server.serve_forever, daemon=True).start()

    def tearDown(self):
        for server in [self.proxy, self.backend]:
            server.shutdown()
            server.server_close()
        self.temp.cleanup()

    def request(self, path="/api", headers=None, method="GET", body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.proxy.server_port, timeout=3)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, response.getheaders(), response.read()
        finally:
            connection.close()

    def test_worker_bootstrap_token_and_forged_cookie_never_authenticate_owner(self):
        self.assertEqual(self.request("/?token=" + "A" * 40)[0], 401)
        self.assertEqual(self.request(headers={"Cookie": self.proxy.cookie_name + "=v1.forged.signature"})[0], 401)
        self.assertEqual(self.requests, [])

    def test_bootstrap_is_server_side_and_never_discloses_token_or_owner_cookie(self):
        status, headers, body = self.request("/", {"Authorization": self.auth})
        self.assertEqual(status, 303)
        self.assertNotIn("token=", str(headers))
        cookies = [v for k, v in headers if k.lower() == "set-cookie"]
        self.assertEqual(len(cookies), 1)
        self.assertIn("Max-Age=86400", cookies[0])
        self.assertNotIn("owner-admin", str(headers))
        cookie = cookies[0].split(";", 1)[0]
        self.assertEqual(self.request("/", {"Authorization": self.auth, "Cookie": cookie})[0], 200)

    def test_owner_auth_and_unrelated_cookies_are_removed_before_worker(self):
        self.request(headers={"Authorization": self.auth, "Cookie": "gateway-owner=private; " + self.proxy.cookie_name + "=v1.test.sig"})
        headers = self.requests[-1][1]
        self.assertNotIn("Authorization", headers)
        self.assertEqual(headers["Cookie"], self.proxy.cookie_name + "=v1.test.sig")

    def test_origin_is_checked_before_rewriting_for_backend(self):
        self.assertEqual(self.request(headers={"Authorization": self.auth, "Origin": "http://evil.test"})[0], 403)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.request(headers={"Authorization": self.auth, "Origin": f"http://127.0.0.1:{self.proxy.server_port}"})[0], 200)
        self.assertEqual(self.requests[-1][1]["Origin"], "http://" + self.proxy.authority)

    def test_body_and_streaming_responses_work(self):
        self.assertEqual(self.request("/echo", {"Authorization": self.auth}, "POST", b'{"ok":true}')[2], b'{"ok":true}')
        status, headers, body = self.request("/sse", {"Authorization": self.auth})
        self.assertEqual((status, body), (200, b"data: x\n\n"))
        self.assertNotIn("Transfer-Encoding", dict(headers))

    def test_pipelined_second_request_cannot_leak_authorization(self):
        with socket.create_connection(self.proxy.server_address, timeout=3) as client:
            first = f"GET /api HTTP/1.1\r\nHost: localhost\r\nAuthorization: {self.auth}\r\nConnection: keep-alive\r\n\r\n"
            client.sendall((first + first).encode())
            output = bytearray()
            while True:
                block = client.recv(65536)
                if not block:
                    break
                output.extend(block)
        self.assertEqual(len(self.requests), 1)
        self.assertNotIn("Authorization", self.requests[0][1])
        self.assertEqual(output.count(b"HTTP/1.1 200"), 1)

    def test_smuggling_headers_are_rejected(self):
        for extra in ["Content-Length: 0\r\nContent-Length: 1", "Transfer-Encoding: chunked"]:
            with socket.create_connection(self.proxy.server_address, timeout=3) as client:
                client.sendall(f"POST /api HTTP/1.1\r\nHost: localhost\r\nAuthorization: {self.auth}\r\n{extra}\r\n\r\n".encode())
                self.assertIn(b" 400 ", client.recv(4096))
        self.assertEqual(self.requests, [])

    def test_websocket_upgrade_and_tunnel_preserve_functionality(self):
        with socket.create_connection(self.proxy.server_address, timeout=3) as client:
            key = base64.b64encode(b"0123456789abcdef").decode()
            client.sendall(f"GET /ws HTTP/1.1\r\nHost: localhost\r\nAuthorization: {self.auth}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n\r\n".encode())
            stream = client.makefile("rb")
            self.assertIn(b" 101 ", stream.readline())
            while stream.readline() != b"\r\n":
                pass
            client.sendall(b"ping")
            self.assertEqual(stream.read(4), b"ping")
            stream.close()
        self.assertNotIn("Authorization", self.requests[-1][1])

    def test_missing_internal_token_fails_visibly_without_exposing_values(self):
        self.token.unlink()
        self.assertEqual(self.request("/", {"Authorization": self.auth})[0], 502)

    def test_opencode_backend_gets_worker_login_and_no_owner_cookies(self):
        self.proxy.kind = "opencode"
        self.proxy.backend_login = base64.b64encode(b"worker:backend-fixture").decode()
        self.assertEqual(self.request(headers={"Authorization": self.auth, "Cookie": "owner-admin=private"})[0], 200)
        self.assertEqual(self.requests[-1][1]["Authorization"], "Basic " + self.proxy.backend_login)
        self.assertNotIn("Cookie", self.requests[-1][1])

    def test_equal_owner_and_worker_passwords_are_refused(self):
        with self.assertRaisesRegex(ValueError, "must differ"):
            AgentAccessServer(("127.0.0.1", 0), backend_port=1, owner_username="owner", owner_password="same",
                              kind="opencode", backend_username="worker", backend_password="same")
