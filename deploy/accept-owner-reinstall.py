#!/usr/bin/env python3
"""Check real localhost/VPN browser flows before removing the worker account."""
import base64
import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, HTTPCookieProcessor, ProxyHandler, build_opener

HOME = Path('/home/huou07')
STAGE = HOME / 'clean-reinstall-20261015'

def main():
    assert os.getuid() == 1000
    (STAGE / 'accepted.json').unlink(missing_ok=True)
    env = dict(line.split('=', 1) for line in (HOME / '.config/huou07-playground/opencode-web.env').read_text().splitlines() if '=' in line)
    auth = 'Basic ' + base64.b64encode((env['OPENCODE_SERVER_USERNAME'] + ':' + env['OPENCODE_SERVER_PASSWORD']).encode()).decode()
    checks = {}
    def request(url, authenticated=False):
        req = Request(url, headers={'Authorization': auth} if authenticated else {})
        try:
            with build_opener(ProxyHandler({})).open(req, timeout=10) as response:
                return response.status, response.read(65536)
        except HTTPError as error:
            return error.code, b''
    def browser(base, authenticated=False):
        cookies = http.cookiejar.CookieJar()
        opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(cookies))
        token = Path('/run/huou07-dsh-link/url').read_text().strip()
        headers = {'Authorization': auth} if authenticated else {}
        with opener.open(Request(base + token, headers=headers), timeout=10) as response:
            assert response.status == 200 and b'<html' in response.read(65536).lower()
        assert list(cookies), 'DSH did not issue a browser session cookie'
        with opener.open(Request(base + '/', headers=headers), timeout=10) as response:
            assert response.status == 200 and b'<html' in response.read(65536).lower()
        return True
    for unit in ['dsh.service', 'opencode-web.service']:
        subprocess.run(['systemctl', '--user', 'is-active', '--quiet', unit], check=True)
        pid = int(subprocess.check_output(['systemctl', '--user', 'show', '-p', 'MainPID', '--value', unit]))
        assert Path(f'/proc/{pid}').stat().st_uid == 1000
        checks[unit + ' uid'] = 1000
    # Exercise fresh startup and restart, including token renewal.
    token_before = Path('/run/huou07-dsh-link/url').read_text()
    subprocess.run(['systemctl', '--user', 'restart', 'dsh.service', 'opencode-web.service'], check=True)
    subprocess.run(['sh', str(Path(__file__).with_name('install-user-apps.sh')), 'status'], check=True)
    assert Path('/run/huou07-dsh-link/url').read_text() != token_before
    checks['localhost DSH browser and restart'] = browser('http://127.0.0.1:3080')
    checks['localhost OpenCode rejects anonymous'] = request('http://127.0.0.1:4096/global/health')[0] == 401
    checks['localhost OpenCode owner health'] = request('http://127.0.0.1:4096/global/health', True)[0] == 200
    interfaces = json.loads(subprocess.check_output(['/usr/sbin/ip', '-j', '-4', 'addr', 'show', 'dev', 'wg0']))
    addresses = [a['local'] for item in interfaces for a in item.get('addr_info', []) if a.get('family') == 'inet']
    assert addresses, 'WireGuard interface address missing'
    for address in addresses:
        base = 'http://' + address
        checks['VPN DSH browser'] = browser(base + ':3080')
        for port, path, authenticated in [(8765, '/api/health', False), (14096, '/global/health', True),
                                         (4000, '/health/readiness', False), (20128, '/healthz', False)]:
            checks[f'VPN port {port}'] = request(base + f':{port}' + path, authenticated)[0] == 200
    lan = json.loads(subprocess.check_output(['/usr/sbin/ip', '-j', '-4', 'addr', 'show', 'dev', 'wlp0s20f3']))
    for item in lan:
        for address in item.get('addr_info', []):
            if address.get('family') == 'inet':
                checks['LAN DSH browser'] = browser('http://' + address['local'] + ':3080', True)
    # The dashboard launch route must yield a usable real DSH browser session.
    cookies = http.cookiejar.CookieJar()
    opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(cookies))
    url = 'http://127.0.0.1:8765/api/apps/launch?name=DeepSeek%20Harness'
    with opener.open(Request(url, headers={'Authorization': auth}), timeout=10) as response:
        checks['Playground launches real DSH HTML'] = response.status == 200 and b'<html' in response.read(65536).lower() and bool(list(cookies))
    assert not (HOME / '.codex/auth.json').exists()
    assert not (HOME / '.local/share/opencode/auth.json').exists()
    assert all(checks.values()), 'Some real runtime checks failed; keep recovery material and inspect.'
    (STAGE / 'accepted.json').write_text(json.dumps({'checks': checks, 'inference_requested': False}, indent=2) + '\n')
    os.chmod(STAGE / 'accepted.json', 0o600)
    print(json.dumps(checks, indent=2))
    print('Localhost, host-side VPN routes, browser sessions and restart passed. A remote VPN client remains an owner check.')

if __name__ == '__main__':
    main()
