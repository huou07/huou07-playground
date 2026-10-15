#!/usr/bin/env python3
"""Prepare, never install, a patch against the actual dashboard deployment."""
import argparse
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path


def source_node(source, name):
    node = next(n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
    return ast.get_source_segment(source, node)


def replace_node(source, old_name, replacement):
    old = source_node(source, old_name)
    assert source.count(old) == 1
    return source.replace(old, replacement, 1)


def candidate(source, template):
    source = replace_node(source, "dsh_launch_url", source_node(template, "dsh_entry_url"))
    source = replace_node(source, "PrivateProxyHandler", source_node(template, "PrivateProxyHandler"))
    source = replace_node(source, "PrivateProxyServer", source_node(template, "PrivateProxyServer"))
    if "def opencode_authorized_header(" in source:
        source = replace_node(source, "opencode_authorized_header", "")
    start_marker = '        if self.path.startswith("/api/apps/launch?"):'
    end_marker = '        if self.path == "/api/apps":'
    start, end = source.index(start_marker), source.index(end_marker)
    local_start, local_end = template.index(start_marker), template.index(end_marker)
    source = source[:start] + template[local_start:local_end] + source[end:]
    main = source_node(source, "main")
    public_start = main.index('    opencode_local_port = ')
    public_end = main.index('    lan_interface = ', public_start)
    main = main[:public_start] + main[public_end:]
    main = main.replace('                auth_mode = "opencode" if listen_port == configured_port("opencode-web", "wireguard_port", 14096) else ""\n', '')
    main = main.replace(', "wg0", auth_mode=auth_mode)', ', "wg0")')
    main = main.replace('''        lan_services = (
            ("dsh", True, ""),
            ("opencode-web", False, "opencode"),
        )''', '''        lan_services = ("dsh", "opencode-web")''')
    main = main.replace('for service_id, login_handoff, auth_mode in lan_services:', 'for service_id in lan_services:')
    main = main.replace('                        login_handoff=login_handoff,\n', '')
    main = main.replace('                        auth_mode=auth_mode,\n', '')
    loop_start = template.index('    for server in agent_access_servers():')
    loop_end = template.index('    print(f"huou07 playground loopback', loop_start)
    main = main.replace('    wg_servers = []\n', '    wg_servers = []\n' + template[loop_start:loop_end], 1)
    source = replace_node(source, "main", source_node(template, "agent_access_servers") + "\n\n\n" + main)
    imports = '\ntry:\n    from .agent_access import AgentAccessServer\nexcept ImportError:\n    from agent_access import AgentAccessServer\n\n'
    source = source.replace('\nROOT = Path(__file__).resolve().parent', imports + '\nROOT = Path(__file__).resolve().parent', 1)
    assert 'login_handoff' not in source and 'opencode_authorized_header' not in source
    assert 'dsh_launch_url(' not in source
    compile(source, 'dashboard-access-candidate', 'exec')
    return source


def main():
    if os.geteuid() == 0:
        raise SystemExit("Preparation must run as the owner without sudo")
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--ports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.output.is_symlink() or args.output.stat().st_uid != os.geteuid():
        raise SystemExit("Staging directory must belong to the owner and not be a symlink")
    args.output.chmod(0o700)
    original = args.source.read_text()
    result = candidate(original, args.template.read_text())
    patch = ''.join(difflib.unified_diff(original.splitlines(True), result.splitlines(True), fromfile='a/web/app.py', tofile='b/web/app.py'))
    ports = json.loads(args.ports.read_text())
    entry = next(p for p in ports['services'] if p['id'] == 'opencode-web')
    assert entry['backend_port'] in [4096, 4097]
    entry['backend_port'] = 4096
    files = {'dashboard-before.py': original, 'dashboard-candidate.py': result,
             'production-access.patch': patch, 'agent_access.py': args.module.read_text(),
             'private-services-before.json': args.ports.read_text(),
             'private-services-candidate.json': json.dumps(ports, indent=2) + '\n'}
    manifest = {}
    for name, content in files.items():
        path = args.output / name
        if path.is_symlink():
            raise SystemExit("Unexpected symlink in staging directory")
        path.write_text(content)
        path.chmod(0o600)
        manifest[name] = hashlib.sha256(content.encode()).hexdigest()
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'prepared': True, 'production_changed': False, 'files': list(manifest)}, indent=2))


if __name__ == '__main__':
    main()
