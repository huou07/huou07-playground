#!/usr/bin/env python3
"""Test the candidate against dummy tokens and owner/worker logins only."""
import base64
import http.client
import importlib.util
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


def main():
    sys.path.insert(0, "/opt/huou07-playground/current/web")
    candidate = Path(__file__).with_name("dashboard-candidate.py")
    spec = importlib.util.spec_from_file_location("dashboard_candidate", candidate)
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    observed = []

    class Backend(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            observed.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def request(server, path, auth=None, duplicate=False):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
        try:
            connection.putrequest("GET", path)
            if auth:
                connection.putheader("Authorization", auth)
                if duplicate:
                    connection.putheader("Authorization", auth)
            connection.endheaders()
            response = connection.getresponse()
            result = response.status, "token=" in response.getheader("Location", "")
            response.read()
            return result
        finally:
            connection.close()

    owner = "Basic " + base64.b64encode(b"owner-fixture:fixture-only").decode()
    worker = "Basic " + base64.b64encode(b"worker:fixture-only").decode()
    checks = {}
    with tempfile.TemporaryDirectory(prefix="dashboard-auth-stage-") as directory, patch.dict(os.environ, {
        "OPENCODE_PUBLIC_USERNAME": "owner-fixture", "OPENCODE_PUBLIC_PASSWORD": "fixture-only"
    }):
        token = Path(directory) / "url"
        token.write_text("/?token=" + "A" * 40)
        app.DSH_URL_FILE = token
        backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        dashboard = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        proxy = app.PrivateProxyServer(("127.0.0.1", 0), backend.server_port, "", login_handoff=True)
        servers = [backend, dashboard, proxy]
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            path = "/api/apps/launch?name=DeepSeek+Harness"
            checks["dashboard_denies_no_login"] = request(dashboard, path) == (401, False)
            checks["dashboard_denies_worker_login"] = request(dashboard, path, worker) == (401, False)
            checks["dashboard_accepts_owner_login"] = request(dashboard, path, owner) == (302, True)
            checks["dashboard_denies_duplicate_auth"] = request(dashboard, path, owner, True) == (401, False)
            checks["handoff_denies_no_login"] = request(proxy, "/") == (401, False)
            checks["handoff_denies_worker_login"] = request(proxy, "/", worker) == (401, False)
            checks["handoff_accepts_owner_login"] = request(proxy, "/", owner) == (302, True)
            checks["proxy_denies_duplicate_auth"] = request(proxy, "/api", owner, True) == (401, False)
            checks["owner_backend_request_works"] = request(proxy, "/api", owner) == (200, False)
            checks["owner_password_not_forwarded_to_worker"] = observed == [None]
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
        original_spec = importlib.util.spec_from_file_location("dashboard_original", candidate.with_name("dashboard-before.py"))
        original = importlib.util.module_from_spec(original_spec)
        original_spec.loader.exec_module(original)
        # Model rollback's systemd mask as an unavailable token path.
        original.DSH_URL_FILE = Path(directory) / "unavailable"
        rollback_dashboard = ThreadingHTTPServer(("127.0.0.1", 0), original.Handler)
        rollback_proxy = original.PrivateProxyServer(("127.0.0.1", 0), backend.server_port, "", login_handoff=True)
        for server in [rollback_dashboard, rollback_proxy]:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            checks["rollback_dashboard_handoff_fails_closed"] = request(rollback_dashboard, path) == (503, False)
            checks["rollback_lan_handoff_fails_closed"] = request(rollback_proxy, "/") == (503, False)
        finally:
            for server in [rollback_dashboard, rollback_proxy]:
                server.shutdown()
                server.server_close()
    print(json.dumps(checks, indent=2))
    assert all(checks.values()), "Dashboard candidate authentication check failed"


if __name__ == "__main__":
    main()
