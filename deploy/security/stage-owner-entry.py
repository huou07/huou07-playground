#!/usr/bin/env python3
"""Actual DSH browser exchange through a distinct-UID trusted proxy."""
import base64
import http.client
import importlib.util
import json
import os
import secrets
import threading
import time
from pathlib import Path


def main():
    if os.geteuid() != 1000:
        raise SystemExit('Owner UID 1000 required for this staging test')
    ready = Path('/tmp/h07-dsh-stage-ready.json')
    if ready.is_symlink() or ready.stat().st_uid != 987:
        raise SystemExit('Unexpected staging metadata owner/type')
    metadata = json.loads(ready.read_text())
    if metadata['worker_uid'] != 987 or metadata['port'] != 13080:
        raise SystemExit('Unexpected worker staging configuration')
    module = Path(__file__).with_name('agent_access.py')
    spec = importlib.util.spec_from_file_location('agent_access', module)
    access = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(access)
    password = secrets.token_urlsafe(32)
    server = access.AgentAccessServer(('127.0.0.1', 13081), backend_port=13080, token_file=metadata['token_file'],
                                      owner_username='owner-stage', owner_password=password)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    login = 'Basic ' + base64.b64encode(('owner-stage:' + password).encode()).decode()
    checks = {}

    def request(path, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', 13081, timeout=5)
        try:
            connection.request('GET', path, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.getheaders(), response.read()
        finally:
            connection.close()

    try:
        checks['no_owner_login_denied'] = request('/')[0] == 401
        token = Path(metadata['token_file']).read_text().strip()
        checks['worker_internal_token_not_owner_capability'] = request(token)[0] == 401
        status, headers, _ = request('/', {'Authorization': login})
        cookie = next((v.split(';', 1)[0] for k, v in headers if k.lower() == 'set-cookie'), None)
        checks['real_dsh_cookie_exchange'] = status == 303 and bool(cookie)
        checks['internal_token_not_published'] = 'token=' not in str(headers)
        assert cookie, 'DSH bootstrap did not yield a scoped cookie'
        status, _, body = request('/', {'Authorization': login, 'Cookie': cookie})
        checks['authenticated_dsh_html'] = status == 200 and b'<html' in body.lower()
        checks['valid_backend_cookie_without_owner_login_denied'] = request('/', {'Cookie': cookie})[0] == 401
        checks['forged_cookie_without_owner_login_denied'] = request('/', {'Cookie': server.cookie_name + '=v1.forged.signature'})[0] == 401
        checks['worker_model_call_already_passed'] = metadata['dsh_gateway_inference_succeeded']
        print(json.dumps({'checks': checks, 'trusted_proxy_uid': os.geteuid(), 'worker_uid': 987,
                          'owner_password_disclosed': False}, indent=2), flush=True)
        assert all(checks.values()), 'Protected DSH entry staging failed'
        print('Protected staging entry ready at port 13081 for the independent worker probe.', flush=True)
        stop = Path(__file__).with_name('owner-entry-stage-stop')
        stop.unlink(missing_ok=True)
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline and not stop.exists():
            time.sleep(1)
        stop.unlink(missing_ok=True)
    finally:
        server.shutdown(); server.server_close()


if __name__ == '__main__':
    main()
