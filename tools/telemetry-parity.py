#!/usr/bin/env python3
"""Generate deterministic legacy collector fixtures consumed by Rust unit tests."""
import argparse
import importlib.util
import json
import hashlib
import os
import signal
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
spec = importlib.util.spec_from_file_location("telemetry_reference", ROOT / "web/app.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)

def fixtures():
    with tempfile.TemporaryDirectory(prefix="telemetry-parity-") as temporary:
        root = Path(temporary)
        zram = root / "zram0"
        zram.mkdir()
        (zram / "disksize").write_text("1048576")
        (zram / "mm_stat").write_text("4096 1024 2048")
        swaps = "Filename Type Size Used Priority\n/swap file 100 10 -2\n/dev/zram0 partition 1024 4 100\n"
        swap, compressed = reference.swap_and_zram_metrics(swaps, root)
        app = {"name": " Example ", "url": "https://example.org", "health_url": "http://127.0.0.1:8888/status"}
        return {"swaps_text": swaps, "swap": swap, "zram": compressed,
                "app_input": {"apps": [app]}, "apps": reference.validate_app_entries({"apps": [app]})}


def native_http(binary, output):
    """Compare isolated native HTTP reads; never persist response bodies."""
    if not Path('/proc/self/stat').exists():
        raise SystemExit('Native HTTP parity requires Linux')
    measurement_spec = importlib.util.spec_from_file_location('telemetry_measurement', ROOT / 'tools/measure-product.py')
    measurement = importlib.util.module_from_spec(measurement_spec)
    measurement_spec.loader.exec_module(measurement)
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class FixtureService(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/health':
                media, payload = 'text/plain', b'healthy'
            elif self.path == '/icon.png':
                media, payload = 'image/png', b'\x89PNG\r\n\x1a\nsynthetic-fixture'
            else:
                media, payload = 'text/html', b'<link rel="icon" href="/icon.png">'
            self.send_response(200)
            self.send_header('Content-Type', media)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *args):
            pass
    icon_server = HTTPServer(('127.0.0.1', 0), FixtureService)
    icon_thread = threading.Thread(target=icon_server.serve_forever, daemon=True)
    icon_thread.start()
    snapshots = {}
    try:
        with tempfile.TemporaryDirectory(prefix='h07p-native-parity-') as temporary:
            root = Path(temporary)
            app_url = f'http://127.0.0.1:{icon_server.server_port}/'
            for label in ('python', 'rust'):
                fixture = root / label
                fixture.mkdir()
                (fixture / 'state').mkdir()
                headers = measurement.fixture_session(fixture)
                (fixture / 'apps.json').write_text(json.dumps({'apps': [{'name': 'Fixture', 'url': app_url, 'health_url': app_url + 'health'}]}))
                (fixture / 'power.json').write_text(json.dumps({'sampled_at': time.time(), 'available': True, 'watts': 4.2}))
                (fixture / 'gpu.json').write_text(json.dumps({'sampled_at': time.time(), 'available': True, 'usage_percent': 7.5, 'engines': {'Render': 7.5}, 'frequency_mhz': 400, 'rc6_percent': 80}))
                (fixture / 'wg.json').write_text(json.dumps({'sampled_at': time.time(), 'available': True, 'peer_count': 0, 'latest_handshake_at': None, 'listen_port': 51820}))
                with socket.socket() as probe:
                    probe.bind(('127.0.0.1', 0))
                    port = probe.getsockname()[1]
                base = f'http://127.0.0.1:{port}'
                environment = dict(os.environ, HOST='127.0.0.1', PORT=str(port), STATIC_DIR=str(ROOT / 'web/static'), H07P_STATE_DIR=str(fixture / 'state'), H07P_HELPER_SOCKET=str(fixture / 'absent.sock'), APPS_FILE=str(fixture / 'apps.json'), POWER_FILE=str(fixture / 'power.json'), GPU_FILE=str(fixture / 'gpu.json'), WG_STATUS_FILE=str(fixture / 'wg.json'))
                command = [sys.executable, str(ROOT / 'tools/measure-product.py'), '--serve-reference', str(ROOT / 'web/app.py')] if label == 'python' else [str(binary)]
                process = subprocess.Popen(command, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                try:
                    for _ in range(100):
                        if process.poll() is not None:
                            raise RuntimeError(f'{label} exited before readiness')
                        try:
                            measurement.request(base, '/api/health')
                            break
                        except OSError:
                            time.sleep(0.05)
                    else:
                        raise RuntimeError(f'{label} readiness timeout')
                    snapshot = {}
                    for endpoint in ('metrics', 'processes', 'services', 'cockpit', 'files', 'vpn', 'private-service-ports', 'apps'):
                        request = urllib.request.Request(base + '/api/' + endpoint, headers=headers)
                        with measurement.LOCAL_HTTP.open(request, timeout=15) as response:
                            data = response.read(4 * 1024 * 1024 + 1)
                            if len(data) > 4 * 1024 * 1024:
                                raise RuntimeError('Native response exceeded limit')
                            snapshot[endpoint] = json.loads(data)
                    with measurement.LOCAL_HTTP.open(urllib.request.Request(base + '/api/apps/icon?name=Fixture', headers=headers), timeout=15) as response:
                        snapshot['icon'] = (response.headers.get_content_type(), hashlib.sha256(response.read(128 * 1024 + 1)).hexdigest())
                    snapshots[label] = snapshot
                finally:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
    finally:
        icon_server.shutdown()
        icon_server.server_close()
        icon_thread.join(timeout=2)
    left, right = snapshots['python'], snapshots['rust']
    comparisons = {}
    for endpoint in ('services', 'cockpit', 'files', 'vpn', 'private-service-ports', 'apps'):
        a, b = dict(left[endpoint]), dict(right[endpoint])
        a.pop('sampled_at', None)
        b.pop('sampled_at', None)
        comparisons[endpoint] = a == b
    for section, field in [('cpu', 'logical_cores'), ('cpu', 'physical_cores'), ('cpu', 'model'), ('memory', 'total'), ('storage', 'total'), ('swap', 'total'), ('swap', 'disk_total')]:
        comparisons[f'metrics.{section}.{field}'] = left['metrics'][section][field] == right['metrics'][section][field]
    comparisons['metrics.storage_devices'] = left['metrics']['storage_devices'] == right['metrics']['storage_devices']
    comparisons['metrics.power.synthetic_sample'] = left['metrics']['power'] == right['metrics']['power']
    comparisons['metrics.gpu.synthetic_or_hardware_sample'] = left['metrics']['gpu'] == right['metrics']['gpu']
    comparisons['processes.schema'] = set(left['processes']) == set(right['processes']) and all(set(item) == {'pid', 'name', 'owner', 'cpu_percent', 'memory_bytes', 'memory_percent'} for endpoint in (left, right) for item in endpoint['processes'].get('processes', []))
    comparisons['icon.synthetic_png'] = left['icon'] == right['icon']
    report = {'schema': 1, 'comparisons': comparisons, 'passed': all(comparisons.values()), 'scope': 'Real HTTP reads from isolated processes; synthetic registry, app health/icon, power, Intel GPU and WireGuard status files. No production credentials or response bodies persisted.', 'limitations': ['Sequential host samples cannot compare CPU, RAM use, rates, process counts or timestamps exactly.', 'system.os platform description intentionally differs.', 'GPU fixture applies only when nvidia-smi is absent; actual NVIDIA readings may vary.', 'Owner session fixture exercises the real gate, not PAM login.', 'This is selected stable-field parity, not full collector or hardware parity.'], 'rust_binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'python_source_sha256': hashlib.sha256((ROOT / 'web/app.py').read_bytes()).hexdigest()}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    output.chmod(0o600)
    print(json.dumps({'passed': report['passed'], 'checks': len(comparisons), 'failed_fields': [key for key, passed in comparisons.items() if not passed]}))
    if not report['passed']:
        raise SystemExit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--native-binary", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.native_binary:
        if not args.output:
            parser.error("--native-binary requires --output")
        native_http(args.native_binary.resolve(), args.output)
        raise SystemExit(0)
    target = ROOT / "tests/telemetry-parity.json"
    actual = fixtures()
    if args.check:
        if json.loads(target.read_text()) != actual:
            raise SystemExit("Legacy fixture drift: regenerate with tools/telemetry-parity.py")
        print("Native Rust fixtures still match the Python reference.")
    else:
        target.write_text(json.dumps(actual, indent=2) + "\n")
