"""Owner-authenticated HTTP boundary in front of credential-free agent engines."""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import os
import re
import socket
import stat
import threading
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailer", "transfer-encoding", "upgrade"}
HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
TOKEN_PATH = re.compile(r"/\?token=[A-Za-z0-9_-]{32,128}\n?\Z")
MAX_BODY = 300 * 1024 * 1024


class AgentAccessServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, address, *, backend_port, owner_username, owner_password,
                 kind="dsh", token_file=None, backend_username="", backend_password="", interface=""):
        if kind not in {"dsh", "opencode"} or not 1 <= backend_port <= 65535:
            raise ValueError("Invalid agent access configuration")
        if not owner_username or not owner_password:
            raise ValueError("Owner authentication must be configured")
        if backend_password and hmac.compare_digest(owner_password.encode(), backend_password.encode()):
            raise ValueError("Owner and worker passwords must differ")
        if kind == "opencode" and not all((backend_username, backend_password)):
            raise ValueError("Worker backend authentication must be configured")
        self.kind = kind
        self.backend_port = backend_port
        self.authority = f"127.0.0.1:{backend_port}"
        self.owner_login = f"{owner_username}:{owner_password}".encode()
        self.backend_login = base64.b64encode(f"{backend_username}:{backend_password}".encode()).decode()
        self.token_file = Path(token_file) if token_file else None
        digest = base64.urlsafe_b64encode(hashlib.sha256(self.authority.encode()).digest()).decode().rstrip("=")
        self.cookie_name = "dsh-auth-" + digest
        self.interface = interface
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(address, AgentAccessHandler)

    def server_bind(self):
        if self.interface:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.interface.encode() + b"\0")
        super().server_bind()

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # A backend/client failure must never print URL, headers or credentials.
        print("Agent access connection failed.", flush=True)


class AgentAccessHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *args):
        pass

    def handle_expect_100(self):
        self.reject(417)
        return False

    def reject(self, status):
        self.close_connection = True
        self.send_response(status)
        if status == 401:
            self.send_header("WWW-Authenticate", 'Basic realm="Playground owner"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    def authenticated(self):
        values = self.headers.get_all("Authorization", [])
        if len(values) != 1:
            return False
        parts = values[0].split()
        if len(parts) != 2 or parts[0].lower() != "basic":
            return False
        try:
            login = base64.b64decode(parts[1], validate=True)
        except ValueError:
            return False
        return hmac.compare_digest(login, self.server.owner_login)

    def do_request(self):
        self.close_connection = True
        if not self.authenticated():
            self.reject(401)
            return
        try:
            target = urlsplit(self.path)
            if target.scheme or target.netloc or not self.path.startswith("/") or self.path.startswith("//"):
                raise ValueError
            if "token" in parse_qs(target.query, keep_blank_values=True, max_num_fields=100):
                # Internal DSH bootstrap tokens never authenticate a public request.
                raise ValueError
            if len(self.headers.get_all("Host", [])) != 1:
                raise ValueError
            origin = self.headers.get("Origin")
            if origin and (origin != "http://" + self.headers["Host"]):
                self.reject(403)
                return
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.reject(403)
                return
            if self.headers.get_all("Transfer-Encoding"):
                raise ValueError
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) > 1 or (lengths and not re.fullmatch(r"[0-9]{1,10}", lengths[0])):
                raise ValueError
            length = int(lengths[0]) if lengths else 0
            if length > MAX_BODY:
                self.reject(413)
                return
            for key, value in self.headers.items():
                if not HEADER_NAME.fullmatch(key) or any(ord(c) < 32 or ord(c) == 127 for c in value):
                    raise ValueError
            upgrade = self.headers.get("Upgrade", "").lower() == "websocket"
            if upgrade:
                if self.command != "GET" or length or self.headers.get("Sec-WebSocket-Version") != "13":
                    raise ValueError
                if len(base64.b64decode(self.headers.get("Sec-WebSocket-Key", ""), validate=True)) != 16:
                    raise ValueError
        except (ValueError, UnicodeError):
            self.reject(400)
            return

        connection = http.client.HTTPConnection("127.0.0.1", self.server.backend_port, timeout=15)
        response = None
        tunnel_socket = None
        headers_sent = False
        try:
            connection.connect()
            connection.sock.settimeout(3600)
            if upgrade:
                tunnel_socket = connection.sock.dup()
            connection.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
            connection.putheader("Host", self.server.authority)
            nominated = {v.strip().lower() for v in self.headers.get("Connection", "").split(",")}
            forbidden = HOP_HEADERS | nominated | {"authorization", "cookie", "host", "origin", "referer", "content-length"}
            for key, value in self.headers.items():
                if key.lower() not in forbidden:
                    connection.putheader(key, value)
            if origin:
                connection.putheader("Origin", "http://" + self.server.authority)
            if self.server.kind == "opencode":
                connection.putheader("Authorization", "Basic " + self.server.backend_login)
            else:
                cookies = SimpleCookie()
                cookies.load(self.headers.get("Cookie", ""))
                if self.server.cookie_name in cookies:
                    connection.putheader("Cookie", self.server.cookie_name + "=" + cookies[self.server.cookie_name].value)
            connection.putheader("Content-Length", str(length))
            connection.putheader("Connection", "Upgrade" if upgrade else "close")
            if upgrade:
                connection.putheader("Upgrade", "websocket")
            connection.endheaders()
            remaining = length
            while remaining:
                block = self.rfile.read(min(65536, remaining))
                if not block:
                    raise ConnectionError
                connection.send(block)
                remaining -= len(block)
            response = connection.getresponse()
            if self.server.kind == "dsh" and self.command == "GET" and self.path == "/" and response.status == 401:
                response.close()
                connection.close()
                token_path = self.internal_token()
                connection = http.client.HTTPConnection("127.0.0.1", self.server.backend_port, timeout=15)
                connection.request("GET", token_path, headers={"Host": self.server.authority, "Connection": "close"})
                response = connection.getresponse()
                if response.status != 303:
                    raise ConnectionError
            self.forward_response(response, upgrade)
            headers_sent = True
            if response.status == 101:
                self.tunnel(response.fp, tunnel_socket)
            elif self.command != "HEAD":
                while True:
                    block = response.read1(65536)
                    if not block:
                        break
                    self.wfile.write(block)
                    self.wfile.flush()
        except (OSError, ValueError, CookieError, http.client.HTTPException):
            if not headers_sent:
                self.reject(502)
            # After headers have started, close the connection; never emit a second response.
        finally:
            if response:
                response.close()
            if tunnel_socket:
                tunnel_socket.close()
            connection.close()

    def internal_token(self):
        if self.server.token_file is None:
            raise ValueError
        fd = os.open(self.server.token_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError
            value = os.read(fd, 160).decode("ascii")
            if not TOKEN_PATH.fullmatch(value):
                raise ValueError
            return value.strip()
        finally:
            os.close(fd)

    def forward_response(self, response, upgrade):
        if response.status == 101:
            expected = base64.b64encode(hashlib.sha1((self.headers["Sec-WebSocket-Key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            if not upgrade or response.getheader("Sec-WebSocket-Accept") != expected:
                raise ValueError
        self.send_response(response.status)
        nominated = {v.strip().lower() for v in response.getheader("Connection", "").split(",")}
        forbidden = HOP_HEADERS | nominated | {"set-cookie", "www-authenticate", "authentication-info", "content-length"}
        for key, value in response.getheaders():
            if any(ord(c) < 32 or ord(c) == 127 for c in value):
                continue
            if key.lower() == "location":
                parsed = urlsplit(value)
                # No upstream-controlled redirect to owner control planes or token URL.
                if parsed.scheme or parsed.netloc or "token" in parse_qs(parsed.query, keep_blank_values=True):
                    continue
            if key.lower() not in forbidden:
                self.send_header(key, value)
            if key.lower() == "set-cookie" and self.server.kind == "dsh":
                cookie = SimpleCookie()
                try:
                    cookie.load(value)
                except CookieError:
                    continue
                item = cookie.get(self.server.cookie_name)
                if item and re.fullmatch(r"v1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", item.value) and len(item.value) < 4096:
                    max_age = "; Max-Age=" + item["max-age"] if re.fullmatch(r"[0-9]{1,9}", item["max-age"]) else ""
                    self.send_header("Set-Cookie", f"{self.server.cookie_name}={item.value}; Path=/; HttpOnly; SameSite=Strict{max_age}")
        if response.status == 101:
            self.send_header("Connection", "Upgrade")
            self.send_header("Upgrade", "websocket")
        else:
            self.send_header("Connection", "close")
        self.end_headers()

    def tunnel(self, upstream_file, upstream_socket):
        def send():
            try:
                while True:
                    block = self.rfile.read1(65536)
                    if not block:
                        break
                    upstream_socket.sendall(block)
            except OSError:
                pass
            finally:
                try:
                    upstream_socket.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
        sender = threading.Thread(target=send, daemon=True)
        sender.start()
        try:
            while True:
                block = upstream_file.read1(65536)
                if not block:
                    break
                self.wfile.write(block)
                self.wfile.flush()
        finally:
            for stream in (self.connection, upstream_socket):
                try:
                    stream.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            sender.join(timeout=2)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = do_request
