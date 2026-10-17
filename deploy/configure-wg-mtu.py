#!/usr/bin/env python3
"""Persist a mobile-safe wg-easy v15 server MTU without restarting tunnels.

Only --apply writes anything. Backups contain numeric MTU settings, never keys.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import time

ROOT = Path('/var/lib/huou07-wg-easy')
MTU = 1280


def replace_mtu(config, value):
    changed, count = re.subn(r'^MTU[ \t]*=[ \t]*\d+[ \t]*$', f'MTU = {value}', config,
                            flags=re.MULTILINE)
    if count != 1:
        raise ValueError('Expected exactly one MTU in wg0.conf')
    return changed


def write_private(path, content):
    fd, name = tempfile.mkstemp(prefix='.mtu-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.apply and os.geteuid() != 0:
        raise RuntimeError('Run --apply with sudo as the owner')
    config = ROOT / 'wg0.conf'
    database = ROOT / 'wg-easy.db'
    if any(p.is_symlink() for p in (ROOT, config, database)):
        raise RuntimeError('Refusing symlinked wg-easy state')
    connection = sqlite3.connect(f'file:{database}?mode={"rw" if args.apply else "ro"}',
                                 uri=True, timeout=10, isolation_level=None)
    with connection:
        interfaces = connection.execute('SELECT mtu FROM interfaces_table WHERE name=?', ('wg0',)).fetchall()
        defaults = connection.execute('SELECT id, default_mtu FROM user_configs_table').fetchall()
        if len(interfaces) != 1 or not defaults:
            raise RuntimeError('Unexpected wg-easy schema or interface inventory')
        original = config.read_text()
        updated = replace_mtu(original, MTU)
        runtime = json.loads(subprocess.check_output(['ip', '-j', 'link', 'show', 'wg0']))[0]['mtu']
        print(json.dumps({'saved_server_mtu': interfaces[0][0],
                          'saved_default_mtus': [r[1] for r in defaults],
                          'runtime_mtu': runtime, 'target_mtu': MTU}), flush=True)
        if not args.apply:
            return
        backup = Path('/var/backups/h07p-wg-mtu')
        backup.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup.chmod(0o700)
        record = backup / f'{time.time_ns()}.json'
        write_private(record, json.dumps({'server_mtu': interfaces[0][0],
                                          'user_config_default_mtus': defaults,
                                          'runtime_mtu': runtime}, indent=2) + '\n')
        try:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute('UPDATE interfaces_table SET mtu=? WHERE name=?', (MTU, 'wg0'))
            connection.execute('UPDATE user_configs_table SET default_mtu=?', (MTU,))
            subprocess.run(['ip', 'link', 'set', 'dev', 'wg0', 'mtu', str(MTU)], check=True)
            write_private(config, updated)
            connection.execute('COMMIT')
        except Exception:
            if connection.in_transaction:
                connection.execute('ROLLBACK')
            write_private(config, original)
            subprocess.run(['ip', 'link', 'set', 'dev', 'wg0', 'mtu', str(runtime)], check=False)
            raise
        print(f'Persisted MTU {MTU}; numeric-only rollback settings: {record}')


if __name__ == '__main__':
    main()
