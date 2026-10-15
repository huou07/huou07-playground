#!/usr/bin/env python3
"""Exercise the live dashboard candidate against a fresh real DSH session."""
import base64
import http.client
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import threading
import types

ROOT = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    assert os.getuid() == 1000
    root_steps = load('retire_worker', ROOT / 'retire-worker-root.py')
    dsh = load('stage_dsh', ROOT / 'stage-dsh-auth.py')
    app = Path('/opt/huou07-playground/current/web/app.py')
    sys.path.insert(0, str(app.parent))
    source = root_steps.dashboard_candidate(app.read_text())
    candidate = types.ModuleType('dashboard_cookie_candidate')
    candidate.__file__ = str(app)
    exec(compile(source, str(app), 'exec'), candidate.__dict__)
    os.environ['OPENCODE_PUBLIC_USERNAME'] = 'fixture-owner'
    os.environ['OPENCODE_PUBLIC_PASSWORD'] = 'fixture-password-for-disposable-test'
    auth = 'Basic ' + base64.b64encode(b'fixture-owner:fixture-password-for-disposable-test').decode()
    with tempfile.TemporaryDirectory(prefix='fresh-owner-lan-') as directory:
        home = Path(directory)
        child, token = dsh.start(home)
        token_file = home / 'launch-url'
        token_file.write_text(token)
        token_file.chmod(0o600)
        candidate.DSH_URL_FILE = token_file
        proxy = candidate.PrivateProxyServer(('127.0.0.1', 0), dsh.PORT, '', login_handoff=True)
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        def request(path, cookie=None, login=True):
            headers = {'Host': f'127.0.0.1:{dsh.PORT}'}
            if login:
                headers['Authorization'] = auth
            if cookie:
                headers['Cookie'] = cookie
            connection = http.client.HTTPConnection('127.0.0.1', proxy.server_address[1], timeout=5)
            try:
                connection.request('GET', path, headers=headers)
                response = connection.getresponse()
                return response.status, response.getheader('Location'), response.getheader('Set-Cookie'), response.read()
            finally:
                connection.close()
        try:
            assert request('/', login=False)[0] == 401
            status, location, _, _ = request('/')
            assert status == 302 and location == token
            status, _, cookie, _ = request(location)
            assert status == 303 and cookie
            cookie = cookie.split(';', 1)[0]
            status, _, _, body = request('/', cookie)
            assert status == 200 and b'<html' in body.lower(), 'Authenticated LAN session loops instead of showing DSH'
            assert request('/', cookie + 'tampered')[0] == 401
            assert request('/', cookie, login=False)[0] == 401
            print('Live dashboard candidate: real DSH login, cookie HTML, forged-cookie rejection and owner gate passed.')
        finally:
            proxy.shutdown()
            proxy.server_close()
            dsh.stop(child)

if __name__ == '__main__':
    main()
