#!/usr/bin/env python3
"""Install predownloaded native packages after the approved worker stop."""
import os
from pathlib import Path
import shutil
import subprocess

HOME = Path('/home/huou07')
STAGE = HOME / 'clean-reinstall-20261015'

def main():
    assert os.getuid() == 1000 and Path.home() == HOME
    assert (STAGE / 'old-owner-apps').is_dir(), 'Run reset-owner-apps.py first.'
    os.umask(0o077)
    prefix = STAGE / 'fresh-prefix'
    for package in ['@openai/codex', 'opencode-ai', '@deepseek-ai/dsh', '@agentclientprotocol/codex-acp', 'pnpm']:
        source = prefix / 'lib/node_modules' / package
        target = HOME / '.local/lib/node_modules' / package
        assert source.is_dir() and not target.exists(), target
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, symlinks=True)
    for binary in ['codex', 'opencode', 'dsh', 'codex-acp', 'pnpm', 'pnpx']:
        source = prefix / 'bin' / binary
        target = HOME / '.local/bin' / binary
        assert source.is_symlink() and not target.exists() and not target.is_symlink(), target
        target.symlink_to(source.readlink())
    # Keep developer utilities that were relocated by the old isolation setup.
    tools = HOME / '.local/share/developer-tools'
    tools.mkdir(parents=True, exist_ok=True)
    for binary in ['rg', 'fd', 'ruff', 'shellcheck', 'gitleaks', 'osv-scanner', 'ast-grep']:
        source = Path('/opt/agent-workbench/bin') / binary
        target = HOME / '.local/bin' / binary
        if source.exists():
            assert not target.exists() or target.is_symlink(), target
            target.unlink(missing_ok=True)
            shutil.copy2(source, target)
    version = tools / 'codegraph/v1.6.0'
    assert not version.exists()
    shutil.copytree('/opt/agent-workbench/codegraph/v1.6.0', version, symlinks=True)
    target = HOME / '.local/bin/codegraph'
    assert target.is_symlink()
    target.unlink()
    target.write_text('#!/bin/sh\nset -eu\nexport CODEGRAPH_HOST_PPID="${CODEGRAPH_HOST_PPID:-$PPID}"\n'
                      f'exec "{version}/node" --liftoff-only --disable-warning=ExperimentalWarning '
                      f'"{version}/lib/dist/bin/codegraph.js" "$@"\n')
    target.chmod(0o755)
    old_version = HOME / '.codegraph/versions/v1.6.0'
    assert old_version.is_symlink()
    old_version.unlink()
    old_version.symlink_to(version)
    # Fresh plugin installation contains no provider login. Browser sessions
    # from staging are intentionally discarded before copying its profile.
    fresh_dsh = STAGE / 'fresh-home/.dsh'
    (fresh_dsh / '.credentials.yaml').unlink(missing_ok=True)
    assert not (HOME / '.dsh').exists()
    shutil.copytree(fresh_dsh, HOME / '.dsh', symlinks=True)
    (HOME / '.dsh').chmod(0o700)
    (HOME / '.codex').mkdir(mode=0o700)
    for binary in ['codex', 'opencode', 'dsh']:
        subprocess.run([str(HOME / '.local/bin' / binary), '--version'], check=True)
    assert not (HOME / '.codex/auth.json').exists()
    assert not (HOME / '.local/share/opencode/auth.json').exists()
    # Retire the old global hook override; project source changes stay intact.
    vce = HOME / 'Projects/VCE'
    subprocess.run(['git', '-C', str(vce), 'config', '--unset-all', 'core.hooksPath'], check=False)
    hub = HOME / 'AEH'
    registry = hub / 'projects/registry.json'
    import json
    data = json.loads(registry.read_text())
    for project in data.get('projects', {}).values():
        if project.get('path') == '/home/huou07/Projects/huou07-playground':
            project['path'] = '/home/huou07/Projects/H07P'
    registry.write_text(json.dumps(data, indent=2) + '\n')
    link = hub / '.agents/skills/prompt-assist'
    if link.is_symlink() and str(link.readlink()).startswith('/home/huou07/dsh projects/'):
        link.unlink()
        link.symlink_to('../../.opencode/skills/prompt-assist')
    print('Fresh native CLIs and AEH paths installed under huou07; no old provider authentication imported.')

if __name__ == '__main__':
    main()
