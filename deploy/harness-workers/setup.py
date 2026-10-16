#!/usr/bin/env python3
"""Owner-run Debian migration to separate harness UIDs and a shared home.

Only --apply changes the host. Secret contents are never read by this program.
"""
import argparse
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import time

HOME = Path('/home/huou07')
WORKERS = ('dsh-worker', 'codex-worker', 'opencode-worker')
NATIVE = {
    '.dsh': 'dsh-worker', '.codex': 'codex-worker',
    '.config/opencode': 'opencode-worker',
    '.local/share/opencode': 'opencode-worker',
    '.local/state/opencode': 'opencode-worker', '.cache/opencode': 'opencode-worker',
}
# Whole stores are private: sessions and backups can contain credentials too.
PRIVATE = (
    '.ssh', '.gnupg', '.aws', '.azure', '.kube', '.docker', '.pki', '.secrets',
    '.mozilla', '.var', '.claude', '.config/gh', '.config/gcloud',
    '.config/agent-workbench', '.config/huou07-playground', '.config/litellm',
    '.config/omniroute', '.config/keyrings', '.config/chromium',
    '.config/google-chrome', '.config/BraveSoftware', '.config/containers',
    '.local/share/keyrings', '.local/share/containers', '.local/share/docker',
    '.local/share/huou07-playground-migration', '.local/share/Trash', '.cache/mozilla', '.cache/chromium',
    '.cache/google-chrome', '.cache/BraveSoftware',
)
READONLY = (
    '.local/bin', '.local/lib', '.local/share/huou07-playground',
    '.cargo/bin', '.rustup', '.config/systemd', '.config/autostart',
    '.bashrc', '.bash_profile', '.bash_logout', '.profile', '.zshrc', '.zprofile',
    '.config/fish', '.config/environment.d', '.config/libvirt', '.gitconfig',
)
SECRET_NAMES = {
    '.netrc', '.npmrc', '.pypirc', '.git-credentials', '.bash_history',
    '.zsh_history', '.lesshst', 'auth.json', '.credentials.yaml',
    'credentials.json', 'credentials.yaml', 'credentials.yml', 'credentials',
    'credentials.toml', '.s3cfg', '.envrc', '.gitcookies',
    'id_rsa', 'id_ed25519', 'id_ecdsa', 'authorized_keys', 'known_hosts',
}


def under(path, roots):
    return any(path == root or path.startswith(root + '/') for root in roots)


def secret_name(name):
    lower = name.lower()
    sample = any(word in lower.split('.') for word in ('example', 'sample', 'template'))
    return (lower in SECRET_NAMES or lower.endswith(('.pem', '.key', '.p12', '.pfx'))
            or (not sample and (lower == '.env' or lower.startswith('.env.')
                                or lower.endswith('.env'))))


def policy(relative, extra=()):
    if under(relative, NATIVE):
        return 'native'
    if under(relative, (*PRIVATE, *extra)) or secret_name(Path(relative).name):
        return 'private'
    if '/' not in relative and (relative.startswith('clean-reinstall-')
                               or relative.startswith('an3-migration-')):
        return 'private'
    if under(relative, READONLY):
        return 'readonly'
    return 'shared'


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def validate_boundaries(extra):
    for relative in (*NATIVE, *PRIVATE, *READONLY, *extra):
        path = HOME / relative
        for candidate in (path, *path.parents):
            if candidate.is_symlink():
                raise RuntimeError(f'Refusing symlink in managed boundary: {candidate}')
            if candidate == HOME:
                break


def inventory(extra, max_entries=None, max_seconds=None):
    """Never follow symlinks or enter private/native stores or other mounts."""
    result = {'shared': [HOME], 'readonly': [], 'private': [], 'native': []}
    device = HOME.stat().st_dev
    started = time.monotonic()
    count = 0
    def visit(directory):
        nonlocal count
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                if ((max_entries is not None and count > max_entries)
                        or (max_seconds is not None and time.monotonic() - started > max_seconds)):
                    raise RuntimeError('Permission inventory limit reached before changes; reduce the shared-home tree and retry.')
                if entry.is_symlink():
                    continue
                path = Path(entry.path)
                metadata = entry.stat(follow_symlinks=False)
                if metadata.st_dev != device or not (
                        stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
                    continue
                kind = policy(str(path.relative_to(HOME)), extra)
                # Owner-created ordinary files are shared; root-managed files stay read-only.
                if kind == 'shared' and metadata.st_uid == 0:
                    kind = 'readonly'
                result[kind].append(path)
                if entry.is_dir(follow_symlinks=False) and kind not in ('private', 'native'):
                    visit(path)
    visit(HOME)
    return result


def acl(paths, permission, defaults=True):
    for offset in range(0, len(paths), 150):
        batch = paths[offset:offset + 150]
        entries = ','.join(f'u:{user}:{permission}' for user in WORKERS)
        run('setfacl', '-m', entries, '--', *batch)
        directories = [p for p in batch if p.is_dir()]
        if defaults and directories:
            run('setfacl', '-m', ','.join(f'd:u:{u}:{permission}' for u in WORKERS),
                '--', *directories)


def owner_systemctl(*args):
    uid = pwd.getpwnam('huou07').pw_uid
    return run('runuser', '-u', 'huou07', '--', 'env', f'XDG_RUNTIME_DIR=/run/user/{uid}',
               f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus',
               'systemctl', '--user', *args)


def backup(paths):
    directory = Path('/var/backups/h07p-harness-workers') / (time.strftime('%Y%m%d-%H%M%S') + '-' + str(time.time_ns()))
    directory.mkdir(parents=True, mode=0o700)
    directory.parent.chmod(0o700)
    # getfacl includes ownership, default ACLs and sticky flags; restore with --restore.
    with (directory / 'acl.restore').open('wb') as output:
        for offset in range(0, len(paths), 150):
            run('getfacl', '-p', '--', *paths[offset:offset + 150], stdout=output)
        for relative in NATIVE:
            path = HOME / relative
            if path.exists():
                run('getfacl', '-R', '-P', '-p', '--', path, stdout=output)
    saved = [Path('/etc/tmpfiles.d/huou07-dsh-link.conf')]
    for path in saved:
        if path.exists():
            shutil.copy2(path, directory / path.name)
    print(f'Permission/ownership rollback snapshot: {directory}', flush=True)
    return directory


def install_file(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Refuse redirecting root writes through a preexisting symlink.
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise RuntimeError(f'Refusing symlink in managed path: {path}')
    path.write_text(content)
    os.chown(path, 0, 0)
    path.chmod(mode)


def protect_ancestors(boundaries):
    # Prevent substitution of an owner-owned private/launch path via writable parents.
    for boundary in boundaries:
        for parent in boundary.parents:
            if parent == HOME or HOME in parent.parents:
                if parent.is_dir():
                    parent.chmod(stat.S_IMODE(parent.stat().st_mode) | stat.S_ISVTX)
            if parent == HOME:
                break


def service(harness, command):
    envfile = ('EnvironmentFile=/home/huou07/.config/huou07-playground/opencode-web.env\n'
               if harness == 'opencode' else '')
    runtime = ('RuntimeDirectory=huou07-dsh-link\nRuntimeDirectoryMode=2750\n'
               'RuntimeDirectoryPreserve=yes\nSupplementaryGroups=huou07-dsh-link\n'
               if harness == 'dsh' else '')
    return f'''[Unit]
Description=H07P {harness} (separate worker UID, shared owner applications)
After=network-online.target
[Service]
User={harness}-worker
Group={"huou07-dsh-link" if harness == "dsh" else harness + "-worker"}
WorkingDirectory=/home/huou07/Projects
Environment=HOME=/home/huou07
Environment=DSH_HOME=/home/huou07/.dsh
Environment=CODEX_HOME=/home/huou07/.codex
Environment=PATH=/home/huou07/.local/bin:/home/huou07/.cargo/bin:/usr/local/bin:/usr/bin:/bin
Environment=GIT_CONFIG_COUNT=1
Environment=GIT_CONFIG_KEY_0=safe.directory
Environment=GIT_CONFIG_VALUE_0=/home/huou07/*
Environment=NPM_CONFIG_USERCONFIG=/home/huou07/{'.config/opencode' if harness == 'opencode' else '.' + harness}/npmrc
{envfile}{runtime}ExecStart={command}
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
UMask=0002
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
[Install]
WantedBy=multi-user.target
'''


def apply(groups, extra):
    if os.geteuid() != 0:
        raise RuntimeError('--apply must run as root by the owner')
    for user in WORKERS:
        try:
            account = pwd.getpwnam(user)
            if account.pw_uid == 0 or account.pw_dir != str(HOME):
                raise RuntimeError(f'Unexpected existing account: {user}')
        except KeyError:
            run('useradd', '--system', '--no-create-home', '--user-group',
                '--home-dir', HOME, '--shell', '/bin/bash', user)
        # No supplementary groups: in particular no sudo, docker, disk or owner group.
        run('usermod', '-G', '', user)
        run('usermod', '--lock', user)
    owner_systemctl('disable', '--now', 'dsh.service', 'opencode-web.service')
    for paths in groups.values():
        # Inventory may include existing native roots but not their contents.
        for path in paths:
            if path.is_symlink():
                raise RuntimeError(f'Path changed to a symlink: {path}')
    # Denials come last so an ordinary hardlink alias cannot widen a known secret.
    for kind, permission in (('shared', 'rwX'), ('readonly', 'r-X'), ('private', '---')):
        acl(groups[kind], permission)
    for relative, user in NATIVE.items():
        path = HOME / relative
        path.mkdir(parents=True, exist_ok=True)
        run('chown', '-R', '-P', '--no-dereference', f'{user}:{user}', '--', path)
        # Native credentials retain their native modes and their harness UID owns them.
        # Peer denial at the store boundary also protects future native session files.
        peers = ','.join(f'u:{other}:---,d:u:{other}:---'
                         for other in WORKERS if other != user)
        run('setfacl', '-m', f'{peers},u:huou07:rwx,d:u:huou07:rwx', '--', path)
        rules = path / 'AGENTS.md'
        if relative in ('.dsh', '.codex', '.config/opencode') and not rules.exists():
            rules.write_text(f'# {user} global instructions\n\n'
                             'Use project AGENTS.md and .agents/skills from the working project.\n'
                             'Run as your own worker UID; never use another harness credential store.\n')
            os.chown(rules, pwd.getpwnam(user).pw_uid, pwd.getpwnam(user).pw_gid)
    # Writable ancestors otherwise permit renaming a private directory out of the way.
    boundaries = [*groups['private'], *(HOME / p for p in NATIVE),
                  *(HOME / p for p in READONLY)]
    protect_ancestors(boundaries)
    # The handoff token is readable only by DSH and the existing dashboard group.
    install_file(Path('/etc/tmpfiles.d/huou07-dsh-link.conf'),
                 'd /run/huou07-dsh-link 2750 dsh-worker huou07-dsh-link -\n')
    run('systemd-tmpfiles', '--create', '/etc/tmpfiles.d/huou07-dsh-link.conf')
    launcher = Path('/usr/local/libexec/h07p/dsh-dashboard-launcher.py')
    install_file(launcher, (Path(__file__).resolve().parents[1] / 'dsh-dashboard-launcher.py').read_text())
    units = {
        'h07p-dsh.service': service('dsh', f'/usr/bin/python3 {launcher}'),
        'h07p-opencode.service': service('opencode', '/home/huou07/.local/bin/opencode web --hostname 127.0.0.1 --port 4097'),
    }
    for name, content in units.items():
        install_file(Path('/etc/systemd/system') / name, content)
    install_file(Path('/etc/polkit-1/rules.d/40-h07p-workers.rules'), '''polkit.addRule(function(action, subject) {
    if (["dsh-worker", "codex-worker", "opencode-worker"].indexOf(subject.user) !== -1) {
        return polkit.Result.NO;
    }
});
''')
    wrapper = Path(__file__).with_name('h07p-harness')
    install_file(Path('/usr/local/sbin/h07p-harness'), wrapper.read_text(), 0o755)
    config = Path('/etc/h07p-workers')
    config.mkdir(exist_ok=True, mode=0o700)
    install_file(config / 'private-paths.json', json.dumps(extra, indent=2) + '\n', 0o600)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', '--now', *units)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if HOME.is_symlink() or pwd.getpwnam('huou07').pw_dir != str(HOME):
        raise RuntimeError('Unexpected owner home')
    for binary in ('setfacl', 'getfacl', 'runuser', 'systemctl'):
        if not shutil.which(binary):
            raise RuntimeError(f'Missing prerequisite: {binary}')
    manifest = Path('/etc/h07p-workers/private-paths.json')
    extra = json.loads(manifest.read_text()) if manifest.exists() else []
    if not isinstance(extra, list) or any(not isinstance(p, str) or not p
            or p.startswith('/') or '..' in Path(p).parts for p in extra):
        raise RuntimeError('Private paths must be relative paths inside the shared home')
    validate_boundaries(extra)
    if args.apply:
        if os.geteuid() != 0:
            raise RuntimeError('--apply requires the owner to use sudo')
        private_home = HOME / '.secrets'
        if not private_home.exists():
            private_home.mkdir(mode=0o700)
            owner = pwd.getpwnam('huou07')
            os.chown(private_home, owner.pw_uid, owner.pw_gid)
    groups = inventory(extra)
    print(json.dumps({kind: len(paths) for kind, paths in groups.items()}), flush=True)
    if args.apply:
        snapshot = backup([p for paths in groups.values() for p in paths])
        try:
            apply(groups, extra)
        except Exception:
            print(f'Migration failed; snapshot preserved at {snapshot}. See README rollback.', flush=True)
            raise
    else:
        print('Inspection only; use sudo setup.py --apply for the authorized cutover.')


if __name__ == '__main__':
    main()
