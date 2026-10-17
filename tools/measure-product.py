#!/usr/bin/env python3
"""Bounded Linux /proc comparison of synthetic loopback Python and Rust workloads.

Commands are JSON arrays, never shell fragments. Output omits commands, env,
URLs, process names and response bodies. No credentials or model requests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import secrets
import sqlite3
import statistics
import sys
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def tree_snapshot(root):
    records = {}
    for item in Path('/proc').iterdir():
        if not item.name.isdigit():
            continue
        try:
            stat = (item / 'stat').read_text().rsplit(')', 1)[1].split()
            io = dict(line.split(':', 1) for line in (item / 'io').read_text().splitlines())
            records[int(item.name)] = (int(stat[1]), int(stat[11]) + int(stat[12]), int(stat[21]) * os.sysconf('SC_PAGE_SIZE'), int(io.get('write_bytes', 0)))
        except (OSError, ValueError, IndexError):
            continue
    family = {root}
    while True:
        children = {pid for pid, row in records.items() if row[0] in family}
        expanded = family | children
        if expanded == family:
            break
        family = expanded
    rows = [records[pid] for pid in family if pid in records]
    return {'cpu_seconds': sum(row[1] for row in rows) / os.sysconf('SC_CLK_TCK'), 'rss_bytes': sum(row[2] for row in rows), 'write_bytes': sum(row[3] for row in rows), 'processes': len(rows)}


def request(base, endpoint, headers=None):
    start = time.perf_counter()
    with LOCAL_HTTP.open(urllib.request.Request(base + endpoint, headers=headers or {}), timeout=15) as response:
        # Bound response reads; retain hashes for fixture integrity comparisons.
        payload = response.read(4 * 1024 * 1024 + 1)
        if len(payload) > 4 * 1024 * 1024:
            raise RuntimeError('Response exceeds fixture limit')
        return (time.perf_counter() - start) * 1000, response.status, hashlib.sha256(payload).hexdigest()


def fixture_session(fixture):
    """Exercise Rust's real session validator using a disposable synthetic DB."""
    token, csrf = secrets.token_hex(32), secrets.token_hex(32)
    with sqlite3.connect(fixture / 'state/owner.db') as db:
        db.execute('CREATE TABLE sessions(token TEXT PRIMARY KEY,username TEXT,csrf TEXT,expires INTEGER)')
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), 'synthetic-owner', csrf, int(time.time()) + 600))
    return {'Cookie': 'h07p_owner=' + token, 'X-H07P-CSRF': csrf}


def run(command, base, endpoints, idle, count, fixture, wall_deadline, interval):
    environment = dict(os.environ)
    environment.update(HOST='127.0.0.1', PORT=str(urllib.parse.urlsplit(base).port), H07P_STATE_DIR=str(fixture / 'state'), H07P_CONTROL_DIR=str(fixture / 'control'), H07P_HELPER_SOCKET=str(fixture / 'helper.sock'), H07P_NAS_DIR=str(fixture / 'nas'), APPS_FILE=str(fixture / 'apps.json'))
    headers = fixture_session(fixture)
    process = subprocess.Popen(command, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError('Fixture process exited before readiness')
            try:
                request(base, '/api/health')
                break
            except (OSError, ValueError):
                time.sleep(0.05)
        else:
            raise RuntimeError('Fixture readiness timeout')
        before = tree_snapshot(process.pid)
        peak = before['rss_bytes']
        deadline = time.monotonic() + idle
        while time.monotonic() < deadline:
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
            peak = max(peak, tree_snapshot(process.pid)['rss_bytes'])
        after = tree_snapshot(process.pid)
        results = {}
        for endpoint in endpoints:
            samples, hashes, statuses = [], set(), set()
            for _ in range(count):
                if time.monotonic() >= wall_deadline:
                    raise RuntimeError('Measurement exceeded the 300-second total budget')
                latency, status, digest = request(base, endpoint, headers)
                samples.append(latency)
                hashes.add(digest)
                statuses.add(status)
                peak = max(peak, tree_snapshot(process.pid)['rss_bytes'])
                if interval and len(samples) < count:
                    remaining = wall_deadline - time.monotonic()
                    if remaining < interval:
                        raise RuntimeError('Measurement exceeded the 300-second total budget')
                    time.sleep(interval)
            ordered = sorted(samples)
            # Only endpoint ordinal is retained; source endpoints may contain private names.
            results[str(len(results))] = {'p50_ms': statistics.median(samples), 'p95_ms': ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)], 'samples': samples, 'statuses': sorted(statuses), 'sha256': sorted(hashes)}
        final = tree_snapshot(process.pid)
        return {'idle_seconds': idle, 'idle_cpu_seconds': max(0, after['cpu_seconds'] - before['cpu_seconds']), 'request_cpu_seconds': max(0, final['cpu_seconds'] - after['cpu_seconds']), 'idle_write_bytes': max(0, after['write_bytes'] - before['write_bytes']), 'request_write_bytes': max(0, final['write_bytes'] - after['write_bytes']), 'peak_tree_rss_bytes': peak, 'live_process_count': final['processes'], 'endpoints': results}
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        except ProcessLookupError:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    reference = parser.add_mutually_exclusive_group(required=True)
    reference.add_argument('--python-command', type=json.loads)
    reference.add_argument('--python-reference', type=Path, help='Reference web/app.py; serves loopback only without VPN relays')
    parser.add_argument('--rust-command', required=True, type=json.loads)
    parser.add_argument('--port', type=int, default=18765)
    parser.add_argument('--endpoint', action='append', default=[])
    parser.add_argument('--idle-seconds', type=float, default=5)
    parser.add_argument('--requests', type=int, default=30)
    parser.add_argument('--interval-seconds', type=float, default=0, help='Delay between endpoint requests; zero measures a bounded burst')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.python_reference:
        args.python_command = [sys.executable, str(Path(__file__).resolve()), '--serve-reference', str(args.python_reference.resolve())]
    if not Path('/proc/self/stat').exists():
        parser.error('Linux /proc required')
    if not 1024 <= args.port <= 65535 or not 0 <= args.idle_seconds <= 30 or not 1 <= args.requests <= 200 or not 1 <= args.repeats <= 5 or not 0 <= args.interval_seconds <= 5:
        parser.error('Workload exceeds measurement bounds')
    endpoints = args.endpoint or ['/api/health', '/']
    if len(endpoints) > 8 or any(not value.startswith('/') or value.startswith('//') or '?' in value or '#' in value for value in endpoints):
        parser.error('At most 8 fixed fixture endpoints; no queries or fragments')
    for command in (args.python_command, args.rust_command):
        if not isinstance(command, list) or not command or any(not isinstance(value, str) for value in command):
            parser.error('Commands must be nonempty JSON string arrays')
    base = 'http://127.0.0.1:' + str(args.port)
    # Refuse to benchmark or terminate an existing dashboard.
    import socket
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', args.port))
        except OSError:
            parser.error('Fixture port is occupied')
    report = {'schema': 2, 'interval_seconds': args.interval_seconds, 'authentication': 'Synthetic owner cookie sent to both backends; Rust validates a private SQLite session, legacy Python reference has no equivalent owner gate; excludes PAM login cost', 'units': {'latency': 'ms', 'cpu': 'seconds', 'memory': 'bytes'}, 'scope': 'launched process tree; excludes external services and exited children; RSS sums shared pages; no energy inference', 'python': [], 'rust': []}
    try:
        report['source_dirty'] = bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True, stderr=subprocess.DEVNULL).strip())
        report['source_sha'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError:
        report['source_sha'] = None
    executable = Path(args.rust_command[0])
    if executable.is_file():
        report['rust_executable_sha256'] = hashlib.sha256(executable.read_bytes()).hexdigest()
    if args.python_reference:
        report['python_source_sha256'] = hashlib.sha256(args.python_reference.read_bytes()).hexdigest()
    wall_deadline = time.monotonic() + 300
    with tempfile.TemporaryDirectory(prefix='h07p-measure-') as temporary:
        for repeat in range(args.repeats):
            # Alternate order to reduce systematic warmup/order bias.
            labels = ['python', 'rust'] if repeat % 2 == 0 else ['rust', 'python']
            for label in labels:
                if time.monotonic() >= wall_deadline:
                    raise RuntimeError('Measurement exceeded the 300-second total budget')
                fixture = Path(temporary) / (label + str(repeat))
                fixture.mkdir()
                (fixture / 'state').mkdir()
                (fixture / 'nas').mkdir()
                (fixture / 'control').mkdir()
                (fixture / 'apps.json').write_text('{"version":1,"apps":[]}')
                command = args.python_command if label == 'python' else args.rust_command
                report[label].append(run(command, base, endpoints, args.idle_seconds, args.requests, fixture, wall_deadline, args.interval_seconds))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    args.output.chmod(0o600)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--serve-reference':
        import importlib.util
        from http.server import HTTPServer
        source = Path(sys.argv[2])
        sys.path.insert(0, str(source.parent))
        spec = importlib.util.spec_from_file_location('h07p_reference', source)
        reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reference)
        HTTPServer(('127.0.0.1', int(os.environ['PORT'])), reference.Handler).serve_forever()
    else:
        main()
