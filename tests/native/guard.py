#!/usr/bin/env python3
"""Real helper/UID/inotify acceptance. Synthetic exports only; no native auth reads."""
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import subprocess
import sys
import tempfile
import time


def main():
    if sys.platform != 'linux' or os.geteuid() != 0 or sys.argv[2:] != ['--disposable-fixture']:
        raise SystemExit('Linux root and --disposable-fixture required')
    binary = str(Path(sys.argv[1]).resolve())
    owner = pwd.getpwnam('huou07')
    service = pwd.getpwnam('huou07-playground')
    root = Path(tempfile.mkdtemp(prefix='h07p-guard-', dir='/var/tmp'))
    exports = Path(tempfile.mkdtemp(prefix='.h07p-guard-fixture-', dir='/home/huou07/Projects'))
    os.chown(exports, owner.pw_uid, owner.pw_gid)
    exports.chmod(0o700)
    root.chmod(0o755)
    nas = root / 'nas'
    nas.mkdir(mode=0o700)
    os.chown(nas, service.pw_uid, service.pw_gid)
    admin = root / 'run/admin.sock'
    control = root / 'control'
    env = {**os.environ, 'H07P_CONTROL_DIR': str(control), 'H07P_HELPER_SOCKET': str(admin),
           'H07P_NAS_DIR': str(nas), 'H07P_RELAYS': 'false', 'H07P_MANAGED_UNITS': ''}
    process = None
    checks = 0

    def check(ok, message):
        nonlocal checks
        if not ok:
            raise AssertionError(message)
        checks += 1

    def rpc(op, **values):
        with socket.socket(socket.AF_UNIX) as sock:
            sock.settimeout(30)
            sock.connect(str(admin))
            sock.sendall((json.dumps({'op': 'guard_' + op, **values}) + '\n').encode())
            result = json.loads(sock.makefile('rb').readline(1024 * 1024))
        return result

    def good(op, **values):
        response = rpc(op, **values)
        if not response['ok']:
            raise AssertionError(op + ': ' + response.get('error', 'failed'))
        return response['data']

    def create(name, data):
        path = exports / name
        path.write_bytes(data)
        os.chown(path, owner.pw_uid, owner.pw_gid)
        path.chmod(0o600)
        return path

    try:
        process = subprocess.Popen([binary, 'helper'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(200):
            if admin.exists():
                break
            if process.poll() is not None:
                raise AssertionError('Fixture helper exited')
            time.sleep(.05)
        status = good('status')
        check(status['state'] == 'PARTIAL' and 'SAME_UID' in status['limitation'], 'honest same-UID status')
        check(status['config']['enabled'] is False, 'opt-in monitoring')
        check(not rpc('configure', revision=0, enabled=True, content=True,
                      scopes=['/home/huou07/.codex'], safe_exports=[])['ok'], 'native stores excluded')
        cfg = good('configure', revision=0, enabled=True, content=True,
                   scopes=[str(exports)], safe_exports=[str(exports)])
        check(cfg['revision'] == 1, 'versioned configuration')
        check(not rpc('configure', revision=0, scopes=[], safe_exports=[])['ok'], 'stale config rejected')
        for _ in range(100):
            if good('status')['watcher'].get('watches', 0) > 0:
                break
            time.sleep(.05)
        synthetic = b'startup normal\nAuthorization: Bearer synthetic-guard-fixture-credential\nfinished\n'
        path = create('closed.log', synthetic)
        for _ in range(100):
            events = good('events')['events']
            if any(e['kind'] == 'secret_signature_in_closed_export' for e in events):
                break
            time.sleep(.1)
        check(any(e['kind'] == 'secret_signature_in_closed_export' for e in events), 'real inotify content detection')
        check('synthetic-guard-fixture-credential' not in json.dumps(events), 'incident content redacted')
        plan = good('plan', path=str(path))
        check(plan['summary']['redacted_lines'] == 1, 'preview known secret line')
        check(path.read_bytes() == synthetic, 'preview changes no file')
        check(not rpc('clean', plan_id=plan['plan_id'], confirmed=False)['ok'], 'confirmation required')
        with path.open('ab'):
            check(not rpc('plan', path=str(path))['ok'], 'active writer denied')
        path.write_bytes(synthetic + b'new line\n')
        check(not rpc('clean', plan_id=plan['plan_id'], confirmed=True)['ok'], 'changed preview denied')
        plan = good('plan', path=str(path))
        cleaned = good('clean', plan_id=plan['plan_id'], confirmed=True)
        check(b'synthetic-guard-fixture-credential' not in path.read_bytes(), 'secret removed from cleaned export')
        check(path.stat().st_mode & 0o777 == 0o600, 'cleaned result owner-only')
        backup = control / 'guard-quarantine' / cleaned['id']
        check(backup.read_bytes() == synthetic + b'new line\n', 'original preserved exactly')
        check(backup.stat().st_uid == 0 and backup.stat().st_mode & 0o777 == 0o600, 'quarantine root-private')
        check(not rpc('clean', plan_id=plan['plan_id'], confirmed=True)['ok'], 'preview single-use')
        time.sleep(.5)
        check(not any(e['kind'] == 'watch_gap_rescan_required' for e in good('events')['events']),
              'atomic replacement staging does not report a lost watch root')
        restored = good('restore', id=cleaned['id'])
        check((nas / restored['path'].lstrip('/')).read_bytes() == backup.read_bytes(), 'restore exact original into private NAS')
        check(backup.exists(), 'restoring retains backup')
        link = exports / 'alias.log'
        link.symlink_to(path)
        check(not rpc('plan', path=str(link))['ok'], 'symlink rejected')
        hard = exports / 'hard.log'
        os.link(path, hard)
        check(not rpc('plan', path=str(path))['ok'], 'hardlink rejected')
        hard.unlink()
        binary_log = create('binary.log', b'binary\0fake')
        check(not rpc('plan', path=str(binary_log))['ok'], 'binary log rejected')
        oversized = create('large.log', b'x' * (1024 * 1024 + 1))
        check(not rpc('plan', path=str(oversized))['ok'], 'size limit enforced')
        child = exports / 'rotating'
        child.mkdir(mode=0o700)
        os.chown(child, owner.pw_uid, owner.pw_gid)
        time.sleep(.5)
        child.rmdir()
        time.sleep(.5)
        check(not any(e['kind'] == 'watch_gap_rescan_required' for e in good('events')['events']),
              'ordinary child directory removal reconciles without losing a scope root')
        cfg = good('configure', revision=1, enabled=False, content=False,
                   scopes=[str(exports)], safe_exports=[str(exports)])
        for _ in range(100):
            if good('status')['watcher']['state'] == 'OFF':
                break
            time.sleep(.05)
        check(good('status')['watcher']['state'] == 'OFF', 'monitoring stops cleanly')
        for user in ['dsh-worker', 'codex-worker', 'opencode-worker']:
            result = subprocess.run(['runuser', '-u', user, '--', 'test', '-r', str(backup)], capture_output=True)
            check(result.returncode != 0, 'quarantine denied with detection off: ' + user)
        process.terminate()
        process.wait(timeout=10)
        process = subprocess.Popen([binary, 'helper'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                status = good('status')
                break
            except (ConnectionRefusedError, FileNotFoundError):
                time.sleep(.05)
        check(status['config']['revision'] == 2 and len(status['quarantine']) == 1, 'restart retains config and recovery manifest')
        process.terminate()
        process.wait(timeout=10)
        process = subprocess.Popen([binary, 'helper'], env={**env, 'H07P_SCANNER': '/bin/false'},
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                good('status')
                break
            except (ConnectionRefusedError, FileNotFoundError):
                time.sleep(.05)
        check(not rpc('plan', path=str(path))['ok'], 'scanner failure blocks cleanup rather than reporting safe')
        print(json.dumps({'result': 'passed', 'checks': checks, 'scope': 'synthetic helper/UID/inotify/closed exports; no native auth access'}))
    finally:
        if process:
            process.terminate()
            process.wait(timeout=10)
        shutil.rmtree(exports)
        shutil.rmtree(root)


if __name__ == '__main__':
    main()
