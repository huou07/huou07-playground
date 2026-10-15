#!/usr/bin/env python3
"""One-time, explicit reset of the owner's five applications, without sudo."""
import os
from pathlib import Path
import shutil
import subprocess

HOME = Path('/home/huou07')
BACKUP = HOME / 'clean-reinstall-20261015'
OLD = BACKUP / 'old-owner-apps'

def run(*args):
    subprocess.run(args, check=True)

def preserve(relative):
    source = HOME / relative
    if source.exists() or source.is_symlink():
        target = OLD / relative
        assert not target.exists() and not target.is_symlink(), target
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(source, target)

def main():
    assert os.getuid() == 1000 and Path.home() == HOME
    os.umask(0o077)
    assert (BACKUP / 'projects-verified.json').is_file()
    assert not OLD.exists(), 'Reset already started; inspect before retrying.'
    OLD.mkdir(mode=0o700)
    run('systemctl', '--user', 'stop', 'dsh.service', 'opencode-web.service',
        'dsh-proto-acp.socket',
        'litellm.service', 'litellm-db.service', 'litellm-pod.service',
        'omniroute.service', 'omniroute-redis.service', 'omniroute-pod.service')
    run('systemctl', '--user', 'disable', 'dsh-proto-acp.socket')
    volumes = ['huou07-litellm-postgres', 'huou07-omniroute-redis', 'huou07-omniroute-data']
    for name in volumes:
        if subprocess.run(['podman', 'volume', 'exists', name]).returncode == 0:
            run('podman', 'volume', 'export', '--output', str(OLD / (name + '.tar')), name)
            os.chmod(OLD / (name + '.tar'), 0o600)
            with open(os.devnull, 'w') as sink:
                subprocess.run(['tar', '-tf', str(OLD / (name + '.tar'))], stdout=sink, check=True)
    # Only these two application pods and their three volumes are disposable.
    for name in ['huou07-litellm', 'huou07-omniroute']:
        if subprocess.run(['podman', 'pod', 'exists', name]).returncode == 0:
            run('podman', 'pod', 'rm', '--force', name)
    for name in volumes:
        if subprocess.run(['podman', 'volume', 'exists', name]).returncode == 0:
            run('podman', 'volume', 'rm', name)
    paths = [
        '.codex', '.dsh', '.opencode', '.omniroute',
        '.config/opencode', '.local/share/opencode', '.local/state/opencode', '.cache/opencode',
        '.config/litellm', '.config/omniroute', '.local/share/omniroute',
        'dsh-access-v2-stage', 'dsh-security-review-20261015',
        '.huou07-codex-canary.e2QY7R', '.cache/huou07-codex-check.YrZg4R',
        '.config/huou07-playground/opencode-web.env', '.local/share/huou07-playground',
        '.local/bin/codex', '.local/bin/codex-acp', '.local/bin/dsh', '.local/bin/opencode',
        '.local/lib/node_modules/@openai/codex', '.local/lib/node_modules/opencode-ai',
        '.local/lib/node_modules/@deepseek-ai/dsh', '.local/lib/node_modules/@agentclientprotocol/codex-acp',
        '.config/systemd/user/dsh.service', '.config/systemd/user/opencode-web.service',
        '.config/systemd/user/dsh-proto-acp.socket', '.config/systemd/user/dsh-proto-acp@.service',
    ]
    for name in ['litellm.pod', 'litellm-postgres.volume', 'litellm-db.container', 'litellm.container',
                 'omniroute.pod', 'omniroute-redis.volume', 'omniroute-redis.container', 'omniroute.container']:
        paths.append('.config/containers/systemd/' + name)
    for relative in paths:
        preserve(relative)
    for filename in ['.bashrc', '.profile']:
        path = HOME / filename
        shutil.copy2(path, OLD / filename)
        lines = path.read_text().splitlines(keepends=True)
        path.write_text(''.join(line for line in lines if line.strip() != '. "$HOME/.opencode/data/../bin/env"'))
    run('systemctl', '--user', 'daemon-reload')
    print('Old owner application configuration and gateway data preserved privately; active paths reset.')

if __name__ == '__main__':
    main()
