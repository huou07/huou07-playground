#!/usr/bin/env python3
"""Credential-free DSH under the real worker UID, for the protected-entry test."""
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

READY = Path('/tmp/h07-dsh-stage-ready.json')
STOP = Path('/tmp/h07-dsh-stage-stop')


def main():
    if os.geteuid() != 987:
        raise SystemExit('Worker UID 987 required')
    if READY.exists() or STOP.exists():
        raise SystemExit('Staging control path already exists; inspect before starting')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 13080))
    with tempfile.TemporaryDirectory(prefix='h07-worker-dsh-', dir='/tmp') as directory:
        home = Path(directory)
        home.chmod(0o711)  # Share only the disposable internal bootstrap with the owner test.
        dsh_home = home / '.dsh'
        dsh_home.mkdir(mode=0o700)
        capability = 'sk-worker-staging-only-000000000000000000000000000'
        patch = [
            {'id': 'llm-pi-ai', 'name': '@deepseek-ai/dsh-llm-pi-ai', 'config': {'providers': {
                'worker-gateway': {'displayName': 'Restricted fixture gateway', 'api': 'openai-completions',
                    'baseURL': 'http://127.0.0.1:14009/v1', 'apiKeyEnv': 'AGENT_GATEWAY_CAPABILITY',
                    'models': [{'id': 'fixture', 'name': 'Disposable fixture', 'contextWindow': 128000,
                                'maxTokens': 1000, 'input': ['text'], 'reasoningEfforts': False}]}}}},
            {'id': 'agent-default-model', 'name': '@deepseek-ai/dsh-agent-default-model',
             'config': {'provider': 'worker-gateway', 'model': 'fixture'}},
        ]
        (dsh_home / 'cordis.patch.yml').write_text(json.dumps(patch))
        credentials = dsh_home / '.credentials.yaml'
        credentials.write_text('version: 1\nrefs:\n  AGENT_GATEWAY_CAPABILITY: ' + capability + '\n')
        credentials.chmod(0o600)
        env = {'HOME': str(home), 'DSH_HOME': str(dsh_home), 'CODEX_HOME': str(home / '.codex'),
               'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8', 'NO_BROWSER': '1'}
        command = ['/opt/huou07-dsh/node/bin/node', '/opt/huou07-dsh/app/node_modules/@deepseek-ai/dsh/lib/bin.js']
        inference = subprocess.run([*command, 'headless', 'Reply only Staging inference complete. Do not use tools.'],
                                   env=env, cwd=home, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        model_ok = inference.returncode == 0 and 'Staging inference complete.' in inference.stdout
        if not model_ok:
            # Every credential in this isolated child is a disposable fixture.
            diagnostic = (inference.stderr[-1200:] + inference.stdout[-800:]).replace(capability, '<fixture-capability>')
            print(json.dumps({'dsh_gateway_inference_succeeded': False, 'fixture_diagnostic': diagnostic}), flush=True)
            raise SystemExit(1)
        child = subprocess.Popen([*command, 'web', '--host', '127.0.0.1', '--port', '13080', '--no-open'],
                                 env=env, cwd=home, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, close_fds=True)
        token_file = home / 'internal-url'
        published = threading.Event()

        def drain():
            for line in child.stdout:
                match = re.search(r'dsh web:\s+http://127\.0\.0\.1:13080(/\?token=[A-Za-z0-9_-]{32,128})', line)
                if match:
                    token_file.write_text(match.group(1))
                    token_file.chmod(0o644)
                    published.set()

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        ready_written = False
        try:
            if not published.wait(45):
                raise RuntimeError('Disposable worker DSH did not become ready; output withheld')
            fd = os.open(READY, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
            os.fchmod(fd, 0o644)
            with os.fdopen(fd, 'w') as stream:
                json.dump({'worker_uid': os.geteuid(), 'pid': child.pid, 'token_file': str(token_file),
                           'port': 13080, 'dsh_gateway_inference_succeeded': model_ok}, stream)
            ready_written = True
            print(json.dumps({'worker_uid': os.geteuid(), 'ready': True, 'port': 13080,
                              'dsh_gateway_inference_succeeded': model_ok, 'live_credentials_used': False}), flush=True)
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline and not STOP.exists() and child.poll() is None:
                time.sleep(1)
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait()
            reader.join(timeout=2)
            child.stdout.close()
            if ready_written:
                READY.unlink(missing_ok=True)
            print('Disposable worker DSH removed.', flush=True)


if __name__ == '__main__':
    main()
