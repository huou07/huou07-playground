#!/usr/bin/env python3
"""Owner-reviewed root steps for reverting the retired worker installation.

Run quiesce, then the normal-user reset/install, then connect. Run retire only
after fresh application and VPN acceptance. Private backups are not deleted.
"""
import json
import grp
import hashlib
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import time

HOME = Path('/home/huou07')
STAGE = HOME / 'clean-reinstall-20261015'
BACKUP = Path('/root/huou07-clean-reinstall-20261015')
UNITS = ['agent-workbench-dsh@3080.service', 'agent-workbench-opencode-web.service',
         'dsh-acp.socket', 'huou07-dsh.service', 'huou07-opencode-web.service',
         'huou07-litellm.service', 'huou07-litellm-db.service', 'huou07-omniroute.service']
ACCOUNTS = ['agents-worker', 'huou07-dsh', 'huou07-opencode', 'huou07-litellm', 'huou07-omniroute']
RETIRE = [
    '/home/agents-worker', '/opt/agent-workbench', '/srv/agent-workbench', '/etc/agent-workbench',
    '/usr/share/agent-workbench', '/usr/local/libexec/agent-workbench',
    '/usr/local/bin/agent-worker-next', '/usr/local/sbin/agent-workbench-apt',
    '/usr/local/sbin/agent-workbench-cli-v6', '/usr/local/sbin/agent-workbench-v7',
    '/usr/local/sbin/agent-workbench-deploy-v2', '/usr/local/sbin/agent-workbench-deploy-v3',
    '/usr/local/sbin/agent-workbench-repair-v5', '/usr/local/sbin/agent-workbench-repair-v6',
    '/etc/sudoers.d/agent-workbench-apt',
    '/etc/systemd/system/agent-workbench-dsh@.service',
    '/etc/systemd/system/agent-workbench-dsh@.service.d',
    '/etc/systemd/system/agent-workbench-dsh@3080.service.d',
    '/etc/systemd/system/agent-workbench-opencode-web.service',
    '/etc/systemd/system/agent-workbench-opencode-web.service.d',
    '/etc/systemd/system/dsh-acp.socket', '/etc/systemd/system/dsh-acp@.service',
    '/etc/systemd/system/dsh-acp@.service.d',
    '/etc/sysctl.d/60-agent-ptrace-scope.conf',
    '/opt/huou07-dsh', '/srv/huou07-dsh-workspaces', '/srv/huou07-opencode-workspaces',
    '/etc/huou07-litellm', '/etc/huou07-omniroute',
    '/usr/local/libexec/huou07-dsh', '/usr/local/libexec/huou07-opencode',
    '/usr/local/libexec/huou07-litellm', '/usr/local/libexec/huou07-omniroute',
    '/var/lib/huou07-dsh', '/var/lib/huou07-opencode', '/var/lib/huou07-litellm', '/var/lib/huou07-omniroute',
    '/etc/huou07-playground/opencode-web.env',
]
RETIRE += ['/etc/systemd/system/' + u for u in UNITS if u.startswith('huou07-')]

def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

def git(path, *args):
    # Repository config belongs to the old worker. Never let a status check
    # execute its fsmonitor or other repository-controlled helpers as root.
    return subprocess.check_output(['/usr/sbin/runuser', '-u', 'agents-worker', '--',
                                    '/usr/bin/git', '-c', 'safe.directory=*',
                                    '-c', 'core.fsmonitor=false', '-C', str(path), *args])

def save(relative):
    source = Path(relative)
    if source.exists() or source.is_symlink():
        target = BACKUP / 'retired-files' / str(source).lstrip('/')
        assert not target.exists() and not target.is_symlink(), target
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(source, target)

def marker(name):
    return BACKUP / (name + '.json')

def dashboard_candidate(source):
    old = 'if self.server.login_handoff and len(request_line) >= 2 and request_line[0] == b"GET" and request_line[1] == b"/":'
    new = old[:-1] + ' and b"\\r\\ncookie:" not in bytes(header).lower().split(b"\\r\\n\\r\\n", 1)[0]:'
    assert source.count(old) == 1, 'Live LAN handler changed; review before connecting.'
    candidate = source.replace(old, new)
    compile(candidate, 'dashboard candidate', 'exec')
    return candidate

def quiesce():
    assert not marker('quiesced').exists(), 'Already quiesced; inspect state before retrying.'
    assert not (BACKUP / 'original-system-config.tar').exists(), 'Partial cutover exists; inspect before retrying.'
    evidence = json.loads((STAGE / 'projects-verified.json').read_text())
    assert (STAGE / 'shared-docs-verified.json').is_file()
    assert (STAGE / 'project-contents-verified.json').is_file()
    for item in evidence.values():
        source = Path('/') / item['source']
        assert git(source, 'rev-parse', 'HEAD').decode().strip() == item['head'], source
        assert git(source, 'status', '--porcelain').decode() == item['status'], source
    # Save system configuration before changing the running services.
    paths = [str(p).lstrip('/') for p in [Path('/etc/agent-workbench'),
             Path('/etc/tmpfiles.d/huou07-dsh-link.conf'),
             Path('/etc/huou07-playground/opencode-proxy.env'),
             Path('/etc/systemd/system/huou07-playground.service')]
             if p.exists()]
    paths += [str(p).lstrip('/') for p in Path('/etc/systemd/system').glob('*agent-workbench*')]
    paths += [str(p).lstrip('/') for p in Path('/etc/systemd/system').glob('dsh-acp*')]
    run('tar', '-C', '/', '-cpf', str(BACKUP / 'original-system-config.tar'), *paths)
    account_state = {name: dict(zip(['uid', 'gid', 'home', 'shell'],
                     [pwd.getpwnam(name).pw_uid, pwd.getpwnam(name).pw_gid,
                      pwd.getpwnam(name).pw_dir, pwd.getpwnam(name).pw_shell])) for name in ACCOUNTS}
    (BACKUP / 'accounts-before.json').write_text(json.dumps(account_state, indent=2) + '\n')
    run('usermod', '--shell', '/usr/sbin/nologin', 'agents-worker')
    for unit in UNITS:
        state = subprocess.run(['systemctl', 'show', '-p', 'LoadState', '--value', unit],
                               capture_output=True, text=True, check=True).stdout.strip()
        if state != 'not-found':
            run('systemctl', 'disable', '--now', unit)
    worker = pwd.getpwnam('agents-worker')
    assert worker.pw_uid == 987 and worker.pw_dir == '/home/agents-worker'
    subprocess.run(['pkill', '-TERM', '-u', '987'], check=False)
    time.sleep(2)
    subprocess.run(['pkill', '-KILL', '-u', '987'], check=False)
    # Detect edits made after the initial transfer, including ignored/untracked
    # source contents. Never silently replace a newer original with its snapshot.
    for item in evidence.values():
        live = Path('/') / item['source']
        snapshot = STAGE / 'projects-snapshot' / item['source']
        assert git(live, 'rev-parse', 'HEAD').decode().strip() == item['head']
        assert git(live, 'status', '--porcelain').decode() == item['status']
        for folder, dirs, files in os.walk(snapshot, followlinks=False):
            if Path(folder) == snapshot:
                dirs[:] = [name for name in dirs if name != '.git']
            for name in files + [name for name in dirs if (Path(folder) / name).is_symlink()]:
                old = Path(folder) / name
                current = live / old.relative_to(snapshot)
                assert old.is_symlink() == current.is_symlink(), 'Source link changed since backup'
                if old.is_symlink():
                    assert old.readlink() == current.readlink(), 'Source link changed since backup'
                elif old.is_file():
                    with old.open('rb') as a, current.open('rb') as b:
                        assert hashlib.file_digest(a, 'sha256').digest() == hashlib.file_digest(b, 'sha256').digest(), 'Source file changed since backup'
    # Keep the exact remaining worker home privately, including old sessions.
    run('tar', '-C', '/', '-cpf', str(BACKUP / 'worker-home.tar'), 'home/agents-worker')
    finish_quiesce()

def finish_quiesce():
    # Remove only retired identities' named ACLs, including defaults. Render
    # GID992 is deliberately unrelated to retired service UID992.
    retired_uids = {pwd.getpwnam(name).pw_uid for name in ACCOUNTS}
    retired_gids = {pwd.getpwnam(name).pw_gid for name in ACCOUNTS} | {978, 983}
    assert retired_uids == {987, 992, 993, 994, 995}
    assert retired_gids == {977, 978, 980, 981, 982, 983, 984}
    original_acl = BACKUP / 'owner-home-acls.before'
    if not original_acl.exists():
        with original_acl.open('w') as sink:
            run('getfacl', '-R', '-P', '-p', '-n', str(HOME), stdout=sink, stderr=subprocess.DEVNULL)
    # Restore only affected ACL records in one native operation. Large npm and
    # container caches can hold over a million records; one process per file
    # would make the application outage unnecessarily long.
    entry = re.compile(r'^(?:default:)?(user|group):(\d+):')
    cleaned_acl = BACKUP / 'owner-home-acls.cleaned'
    def write_block(block, sink):
        changed = False
        kept = []
        path = None
        for line in block:
            if line.startswith('# file: '):
                path = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), line[8:].rstrip('\n'))
            match = entry.match(line)
            if match and int(match[2]) in (retired_uids if match[1] == 'user' else retired_gids):
                changed = True
            else:
                kept.append(line)
        if changed and path and os.path.lexists(path):
            sink.writelines(kept)
            sink.write('\n')
    with original_acl.open() as source, cleaned_acl.open('w') as sink:
        block = []
        for line in source:
            if line.strip():
                block.append(line)
            else:
                write_block(block, sink)
                block = []
        write_block(block, sink)
    errors = BACKUP / 'acl-cleanup-errors.log'
    legacy_git_config = HOME / 'Projects/VCE/.git/config'
    if legacy_git_config.is_file():
        # The retired framework made this one Git config immutable. Preserve
        # its original attribute record, then release that obsolete restriction.
        attributes = BACKUP / 'vce-git-config-attributes.before'
        if not attributes.exists():
            attributes.write_bytes(subprocess.check_output(['lsattr', str(legacy_git_config)]))
        run('chattr', '-i', str(legacy_git_config))
    with errors.open('w') as sink:
        result = subprocess.run(['setfacl', '--restore', str(cleaned_acl)], stderr=sink,
                                env={**os.environ, 'LC_ALL': 'C'})
    if result.returncode:
        messages = [line for line in errors.read_text().splitlines() if line]
        assert messages and all(line.endswith(': No such file or directory') for line in messages), 'ACL cleanup failed; inspect private error log'
        print(f'Skipped {len(messages)} cache files already removed during maintenance.')
    # Reclaim worker-owned project artifacts without following symlinks.
    for flag, identifiers, command, owner in [('-uid', retired_uids, 'chown', '1000:1000'),
                                             ('-gid', retired_gids, 'chgrp', '1000')]:
        predicate = []
        for identifier in sorted(identifiers):
            if predicate:
                predicate.append('-o')
            predicate.extend([flag, str(identifier)])
        run('find', str(HOME), '-xdev', '(', *predicate, ')', '-exec', command, '-h', owner, '{}', '+')
    # Keep all old worktrees, including caches, until the owner accepts cleanup.
    for name in ['OR', 'VCE']:
        old = HOME / 'Projects' / name
        target = STAGE / 'original-projects' / name
        assert not target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        old.rename(target)
        (STAGE / 'prepared-projects' / name).rename(old)
    old_hub = HOME / 'dsh projects'
    target = STAGE / 'original-projects/AEH'
    assert not target.exists()
    old_hub.rename(target)
    # Normal owner publication; retain the dashboard's existing read group.
    config = Path('/etc/tmpfiles.d/huou07-dsh-link.conf')
    config.write_text('d /run/huou07-dsh-link 2750 huou07 huou07-dsh-link -\n')
    run('systemd-tmpfiles', '--create', str(config))
    Path('/run/huou07-dsh-link/url').unlink(missing_ok=True)
    marker('quiesced').write_text(json.dumps({'uid': 1000, 'projects_preserved': True}) + '\n')
    print('Worker stopped; original projects retained; normal owner handoff prepared.')

def resume_quiesce():
    assert not marker('quiesced').exists()
    assert (BACKUP / 'worker-home.tar').is_file() and (BACKUP / 'owner-home-acls.before').is_file()
    assert not (STAGE / 'original-projects').exists(), 'Project moves already started; inspect before resuming.'
    assert pwd.getpwnam('agents-worker').pw_shell == '/usr/sbin/nologin'
    assert subprocess.run(['pgrep', '-u', '987'], stdout=subprocess.DEVNULL).returncode == 1
    finish_quiesce()

def connect():
    assert marker('quiesced').exists()
    assert (HOME / '.local/share/huou07-playground/readiness.json').is_file()
    source = HOME / '.config/huou07-playground/opencode-web.env'
    assert source.is_file() and not source.is_symlink() and source.stat().st_uid == 1000
    values = dict(line.split('=', 1) for line in source.read_text().splitlines() if '=' in line)
    user, password = values['OPENCODE_SERVER_USERNAME'], values['OPENCODE_SERVER_PASSWORD']
    assert re.fullmatch(r'[A-Za-z0-9_-]+', user) and re.fullmatch(r'[A-Za-z0-9_-]{32,}', password)
    target = Path('/etc/huou07-playground/opencode-proxy.env')
    assert not target.is_symlink()
    target.write_text(f'OPENCODE_PUBLIC_USERNAME={user}\nOPENCODE_PUBLIC_PASSWORD={password}\n'
                      f'OPENCODE_BACKEND_USERNAME={user}\nOPENCODE_BACKEND_PASSWORD={password}\n')
    target.chmod(0o600)
    # A browser that already has its DSH cookie must reach DSH's page rather
    # than repeatedly entering the LAN token -> cookie -> / redirect loop.
    app = Path('/opt/huou07-playground/current/web/app.py')
    source_text = app.read_text()
    candidate = dashboard_candidate(source_text)
    shutil.copy2(app, BACKUP / 'dashboard-app.before.py')
    app.write_text(candidate)
    run('systemctl', 'restart', 'huou07-playground.service')
    marker('connected').write_text('{"dashboard_restarted": true}\n')
    print('Playground authentication connected to the fresh owner OpenCode backend; VPN routes retained.')

def retire():
    assert marker('connected').exists()
    # The owner-side acceptance script must create this only after real checks.
    assert (STAGE / 'accepted.json').is_file(), 'Fresh runtime acceptance has not passed.'
    assert not marker('retired').exists()
    retire_legacy_broker()
    for binary in ['codex', 'opencode', 'dsh', 'codegraph', 'rg']:
        path = HOME / '.local/bin' / binary
        assert path.exists() and not str(path.resolve()).startswith('/opt/agent-workbench/'), path
    for source in RETIRE:
        save(source)
    Path('/run/dsh-acp.sock').unlink(missing_ok=True)
    for account in ACCOUNTS:
        try:
            record = pwd.getpwnam(account)
        except KeyError:
            continue
        assert record.pw_uid != 1000 and record.pw_name != 'huou07-playground'
        subprocess.run(['loginctl', 'disable-linger', account], check=False)
        run('userdel', account)
    for group in ['agent-skills', 'huou07-opencode-workspaces']:
        try:
            grp.getgrnam(group)
        except KeyError:
            continue
        run('groupdel', group)
    run('systemctl', 'daemon-reload')
    run('visudo', '-c', stdout=subprocess.DEVNULL)
    run('sshd', '-t')
    marker('retired').write_text('{"worker_removed": true, "private_backups_retained": true}\n')
    print('Old worker and legacy app accounts/configuration retired; private recovery material retained.')

def retire_legacy_broker():
    assert (STAGE / 'accepted.json').is_file()
    if marker('broker-retired').exists():
        return
    socket_unit = 'aeh-capabilities.socket'
    state = subprocess.check_output(['systemctl', 'show', '-p', 'LoadState', '--value', socket_unit], text=True).strip()
    if state != 'not-found':
        run('systemctl', 'disable', '--now', socket_unit)
        run('systemctl', 'stop', 'aeh-capabilities@*.service', 'aeh-tests.slice')
        subprocess.run(['systemctl', 'reset-failed', 'aeh-capabilities@*.service'], check=False)
    for path in ['/usr/local/bin/aehctl', '/usr/local/libexec/aeh-capabilities',
                 '/etc/systemd/system/aeh-capabilities.socket',
                 '/etc/systemd/system/aeh-capabilities@.service',
                 '/etc/systemd/system/aeh-tests.slice', '/var/lib/aeh-instruction-ledger']:
        save(path)
    runtime = Path('/run/aeh-capabilities')
    if runtime.exists():
        run('tar', '-C', '/run', '-cpf', str(BACKUP / 'broker-runtime.tar'), 'aeh-capabilities')
        shutil.rmtree(runtime)
    Path('/run/aeh-capabilities.sock').unlink(missing_ok=True)
    run('systemctl', 'daemon-reload')
    marker('broker-retired').write_text('{"old_worker_capability_broker_removed": true}\n')
    print('Retired worker-only AEH broker removed; project verification lab data left intact.')

if __name__ == '__main__':
    assert os.geteuid() == 0 and pwd.getpwnam('huou07').pw_uid == 1000
    assert len(sys.argv) == 2 and sys.argv[1] in ['quiesce', 'resume-quiesce', 'connect', 'retire', 'retire-broker']
    assert not BACKUP.is_symlink()
    BACKUP.mkdir(mode=0o700, exist_ok=True)
    BACKUP.chmod(0o700)
    os.umask(0o077)
    {'quiesce': quiesce, 'resume-quiesce': resume_quiesce, 'connect': connect,
     'retire': retire, 'retire-broker': retire_legacy_broker}[sys.argv[1]]()
