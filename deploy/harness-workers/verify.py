#!/usr/bin/env python3
"""Run real Linux UID/ACL checks with synthetic secrets; never open real secrets."""
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('harness_setup', HERE / 'setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
HOME = setup.HOME
passed = 0


def check(condition, label):
    global passed
    if not condition:
        raise AssertionError(label)
    passed += 1
    print(f'PASS {label}', flush=True)


def as_user(user, code, *args):
    return subprocess.run(['runuser', '-u', user, '--', 'env', '-i',
                           f'HOME={HOME}', 'PATH=/usr/bin:/bin:/usr/local/bin',
                           'GIT_CONFIG_COUNT=1', 'GIT_CONFIG_KEY_0=safe.directory',
                           'GIT_CONFIG_VALUE_0=/home/huou07/*',
                           'python3', '-c', code, *map(str, args)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run as the owner with sudo')
    fixture = Path(tempfile.mkdtemp(prefix='h07p-acl-acceptance-', dir=HOME / 'Projects'))
    secret_fixtures = []
    renames = []
    try:
        owner = pwd.getpwnam('huou07')
        os.chown(fixture, owner.pw_uid, owner.pw_gid)
        setup.acl([fixture], 'rwX')
        for user in setup.WORKERS:
            account = pwd.getpwnam(user)
            check(account.pw_uid != 0 and account.pw_dir == str(HOME), f'{user}: distinct non-root UID, shared HOME')
            check(as_user(user, 'import os; assert not os.getgroups() or set(os.getgroups()) <= {os.getgid()}'),
                  f'{user}: no administrative supplementary groups')
            check(not as_user(user, 'import subprocess; raise SystemExit(subprocess.call(["sudo", "-n", "true"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))'),
                  f'{user}: sudo denied')
            check(not as_user(user, 'open("/etc/shadow").read(1)'), f'{user}: root secrets denied')
            check(not as_user(user, 'import subprocess; raise SystemExit(subprocess.call(["runuser", "-u", "huou07", "--", "true"], stderr=subprocess.DEVNULL))'),
                  f'{user}: cannot switch to owner')
            check(as_user(user, 'from pathlib import Path; import sys; p=Path(sys.argv[1]); p.write_text("shared"); p.chmod(0o664)', fixture / user),
                  f'{user}: create shared project file')
            check(as_user(user, 'from pathlib import Path; import sys; assert Path(sys.argv[1]).read_text(); assert list(Path(sys.argv[2]).glob("*/SKILL.md"))',
                          HOME / 'Projects/H07P/AGENTS.md', HOME / 'Projects/H07P/.agents/skills'),
                  f'{user}: shared project instructions and skills readable')
            check(as_user(user, 'import subprocess,sys; subprocess.run(["git","-C",sys.argv[1],"status","--porcelain"],check=True,stdout=subprocess.DEVNULL)',
                          HOME / 'Projects/H07P'), f'{user}: Git accepts owner checkout under shared-home trust')
            for binary in ('dsh', 'codex', 'opencode'):
                check(as_user(user, 'import os,sys; assert os.access(sys.argv[1],os.R_OK|os.X_OK); assert not os.access(sys.argv[1],os.W_OK)',
                              HOME / '.local/bin' / binary), f'{user}: uses shared {binary} installation without modifying launcher')
        for user in setup.WORKERS:
            for peer in setup.WORKERS:
                check(as_user(user, 'from pathlib import Path; import sys; p=Path(sys.argv[1]); assert p.read_text(); p.write_text("edited"); moved=p.rename(str(p)+".moved"); moved.rename(p)', fixture / peer),
                      f'{user}: read/edit/rename {peer} shared file')
        secret = fixture / '.env'
        secret.write_text('synthetic secret')
        secret.chmod(0o644)
        os.chown(secret, owner.pw_uid, owner.pw_gid)
        alias = fixture / 'ordinary-looking-hardlink'
        os.link(secret, alias)
        setup.acl([alias], 'rwX')
        setup.acl([secret], '---')
        for user in setup.WORKERS:
            check(not as_user(user, 'import sys; open(sys.argv[1]).read(1)', alias),
                  f'{user}: final secret denial also covers hardlink alias')
        for relative, own_user in setup.NATIVE.items():
            path = HOME / relative / f'.h07p-synthetic-acceptance-{os.getpid()}'
            # Create as the harness itself with native 0600, without altering real credentials.
            check(as_user(own_user, 'import os,sys; fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,b"synthetic"); os.close(fd)', path),
                  f'{relative}: native worker creates own private file')
            secret_fixtures.append(path)
            for user in setup.WORKERS:
                readable = as_user(user, 'import sys; open(sys.argv[1]).read(1)', path)
                check(readable == (user == own_user), f'{relative}: access for {user} matches native ownership')
                if user != own_user:
                    source, destination = HOME / relative, fixture / ('stolen-' + user)
                    renames.append((source, destination))
                    check(not as_user(user, 'from pathlib import Path; import sys; p=Path(sys.argv[1]); moved=p.rename(sys.argv[2]); moved.rename(p)',
                                      source, destination),
                          f'{user}: cannot rename peer native store')
        # Test actual private roots using synthetic files; no real credential bytes are opened.
        for relative in ('.secrets', '.ssh', '.config/gh', '.config/huou07-playground'):
            directory = HOME / relative
            if not directory.exists():
                continue
            path = directory / f'.h07p-synthetic-acceptance-{os.getpid()}'
            path.write_text('synthetic owner secret')
            path.chmod(0o644)  # Boundary ACL must deny even world-readable new files.
            secret_fixtures.append(path)
            for user in setup.WORKERS:
                check(not as_user(user, 'import sys; open(sys.argv[1]).read(1)', path), f'{user}: {relative} owner secret denied')
                destination = fixture / ('private-' + user)
                renames.append((directory, destination))
                check(not as_user(user, 'from pathlib import Path; import sys; p=Path(sys.argv[1]); moved=p.rename(sys.argv[2]); moved.rename(p)', directory, destination),
                      f'{user}: cannot rename {relative} owner secret directory')
        for user in setup.WORKERS:
            check(not as_user(user, 'import socket; s=socket.socket(socket.AF_UNIX); s.connect("/var/run/docker.sock")'),
                  f'{user}: no root Docker socket')
            check(not as_user(user, 'from pathlib import Path; import sys; assert Path(sys.argv[1]).stat().st_mode & 0o222 and __import__("os").access(sys.argv[1],__import__("os").W_OK)',
                              HOME / '.config/systemd/user'), f'{user}: cannot edit owner service units')
        for name, user in (('h07p-dsh.service', 'dsh-worker'), ('h07p-opencode.service', 'opencode-worker')):
            raw = subprocess.check_output(['systemctl', 'show', name, '-p', 'User', '-p', 'MainPID', '-p', 'NoNewPrivileges'], text=True)
            properties = dict(line.split('=', 1) for line in raw.splitlines())
            check(properties['User'] == user and properties['NoNewPrivileges'] == 'yes' and int(properties['MainPID']) > 0,
                  f'{name}: running as intended worker with no new privileges')
            status = Path('/proc') / properties['MainPID'] / 'status'
            lines = dict(line.split(':', 1) for line in status.read_text().splitlines() if ':' in line)
            check(set(map(int, lines['Uid'].split())) == {pwd.getpwnam(user).pw_uid}, f'{name}: kernel UID matches configuration')
            for peer in setup.WORKERS:
                if peer != user:
                    check(not as_user(peer, 'import os,sys; assert os.access(sys.argv[1],os.R_OK)', status.with_name('environ')),
                          f'{peer}: cannot read {user} process environment')
        print(json.dumps({'passed': passed, 'scope': 'real Debian UIDs/ACLs and running service identities; no model/API calls'}))
    finally:
        # A failing negative test must never strand/remove a native store.
        for source, destination in reversed(renames):
            if destination.exists() and not source.exists():
                destination.rename(source)
        for path in secret_fixtures:
            path.unlink(missing_ok=True)
        shutil.rmtree(fixture)


if __name__ == '__main__':
    main()
