#!/usr/bin/env python3
"""Verify the clean native CLI binaries and both ACP handshakes without models."""
import json
import os
from pathlib import Path
import select
import subprocess
import time

STAGE = Path('/home/huou07/clean-reinstall-20261015')

def main():
    assert os.getuid() == 1000
    home = STAGE / 'fresh-home'
    (home / '.codex').mkdir(mode=0o700, exist_ok=True)
    prefix = STAGE / 'fresh-prefix/bin'
    env = {'HOME': str(home), 'DSH_HOME': str(home / '.dsh'), 'CODEX_HOME': str(home / '.codex'),
           'PATH': f'{prefix}:/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8'}
    evidence = {'uid': os.getuid(), 'provider_credentials_imported': False, 'inference_requested': False}
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': 1, 'clientCapabilities': {}, 'clientInfo': {'name': 'owner-reinstall-check', 'version': '1'}}}
    for label, argv in [('Codex ACP', [str(prefix / 'codex-acp')]),
                        ('OpenCode ACP', [str(prefix / 'opencode'), 'acp'])]:
        child = subprocess.Popen(argv, env=env, cwd=home, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            assert Path(f'/proc/{child.pid}').stat().st_uid == 1000
            child.stdin.write(json.dumps(request) + '\n')
            child.stdin.flush()
            deadline = time.monotonic() + 60
            passed = False
            while time.monotonic() < deadline and child.poll() is None:
                if not select.select([child.stdout], [], [], 1)[0]:
                    continue
                line = child.stdout.readline()
                try:
                    response = json.loads(line)
                except ValueError:
                    continue
                if response.get('id') == 1:
                    passed = 'result' in response and 'error' not in response
                    break
            assert passed, label + ' initialize failed; output withheld'
            evidence[label] = 'initialize passed under UID1000'
            print(label + ': native initialize passed under huou07.', flush=True)
        finally:
            child.stdin.close()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            child.stdout.close()
    assert not (home / '.codex/auth.json').exists()
    assert not (home / '.local/share/opencode/auth.json').exists()
    (STAGE / 'native-cli-verified.json').write_text(json.dumps(evidence, indent=2) + '\n')

if __name__ == '__main__':
    main()
