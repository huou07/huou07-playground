#!/usr/bin/python3
"""Debian maintainer script; DPKG_ROOT confines fixture installs, never host commands."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = Path(os.environ.get('DPKG_ROOT', '/') or '/')
LIVE = ROOT == Path('/')
DASHBOARD = ('huou07-playground.service', 'h07p-helper.service')
WORKERS = ('h07p-dsh.service', 'h07p-opencode.service')
SERVICES = (*DASHBOARD, *WORKERS)
WRAPPER = '/usr/local/sbin/h07p-harness'


def path(value):
    return ROOT / value.lstrip('/')


def protected(value, mode=0o755):
    target = path(value)
    # Reject substituted ancestors before privileged writes, including final component.
    for component in (target, *target.parents):
        if component.is_symlink():
            raise RuntimeError('Refusing symbolic link in package state path')
    target.mkdir(parents=True, exist_ok=True, mode=mode)
    target.chmod(mode)
    if LIVE:
        os.chown(target, 0, 0)
    return target


def copy_tree(source, destination):
    shutil.copytree(source, destination, symlinks=True)
    # shutil preserves modes but drops UIDs; restore service ownership for rollback.
    if LIVE:
        for parent, directories, files in os.walk(source, followlinks=False):
            for entry in ['.', *directories, *files]:
                original = Path(parent) / entry
                copied = destination / original.relative_to(source)
                info = original.lstat()
                os.chown(copied, info.st_uid, info.st_gid, follow_symlinks=False)


def service(*args, check=True):
    if LIVE and path('/run/systemd/system').is_dir():
        subprocess.run(['systemctl', *args], check=check, stdout=subprocess.DEVNULL)


def service_state():
    if not LIVE or not path('/run/systemd/system').is_dir():
        return {}
    return {name: {key: subprocess.run(['systemctl', 'is-' + key, name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
                   for key in ('active', 'enabled')} for name in SERVICES}


def stop_transient_workers():
    if LIVE and path('/run/systemd/system').is_dir():
        result = subprocess.run(['systemctl', 'list-units', '--type=service', '--state=active,activating', '--plain', '--no-legend', 'h07p-worker-*'], check=True, capture_output=True, text=True)
        for line in result.stdout.splitlines():
            name = line.split()[0] if line.split() else ''
            if name.startswith('h07p-worker-') and name.endswith('.service'):
                service('stop', name)


def restore_workers(backup):
    states = json.loads((backup / 'services.json').read_text()) if (backup / 'services.json').exists() else {}
    for name in WORKERS:
        unit = path('/etc/systemd/system') / name
        unit.unlink(missing_ok=True)
        if (backup / name).exists():
            shutil.copy2(backup / name, unit)
    wrapper = path(WRAPPER)
    wrapper.unlink(missing_ok=True)
    if (backup / 'h07p-harness').exists():
        shutil.copy2(backup / 'h07p-harness', wrapper)
    service('daemon-reload', check=False)
    for name in WORKERS:
        if states.get(name, {}).get('enabled'):
            service('enable', name, check=False)
        if states.get(name, {}).get('active'):
            service('start', name, check=False)


def current_backup():
    pointer = path('/var/lib/huou07-package/transaction.json')
    if not pointer.exists():
        return None
    name = json.loads(pointer.read_text())['backup']
    if not name.isdigit():
        raise RuntimeError('Invalid package backup identifier')
    return path('/var/backups/huou07-playground') / name


def prepare():
    protected('/var/lib/huou07-package', 0o700)
    pending = path('/var/lib/huou07-package/pending.json')
    if pending.exists():
        rollback()
    base = protected('/var/backups/huou07-playground', 0o700)
    backup = base / str(time.time_ns())
    backup.mkdir(mode=0o700)
    states = service_state()
    for key in ('active', 'enabled'):
        (backup / (key + '-units')).write_text(''.join(name + '\n' for name in SERVICES if states.get(name, {}).get(key)))
    restored = path('/var/lib/huou07-package/workers-restored')
    if restored.exists():
        path('/var/lib/huou07-package/adoption.json').unlink(missing_ok=True)
        restored.unlink()
    (backup / 'services.json').write_text(json.dumps(states))
    known = {
        'huou07-playground.service': ('ExecStart=/usr/bin/python3 /opt/huou07-playground/current/web/app.py', 'ExecStart=/opt/huou07-playground/current/bin/h07p-server'),
        'h07p-helper.service': ('ExecStart=/opt/huou07-playground/current/bin/h07p-server helper',),
        'h07p-dsh.service': ('ExecStart=/usr/bin/python3 /usr/local/libexec/h07p/dsh-dashboard-launcher.py', 'ExecStart=/opt/huou07-playground/current/bin/h07p-server worker dsh --web'),
        'h07p-opencode.service': ('ExecStart=/home/huou07/.local/bin/opencode web --hostname 127.0.0.1 --port 4097', 'ExecStart=/opt/huou07-playground/current/bin/h07p-server worker opencode --web'),
    }
    for name in SERVICES:
        unit = path('/etc/systemd/system') / name
        if unit.exists() or unit.is_symlink():
            if unit.is_symlink() or not any(line in unit.read_text().splitlines() for line in known[name]):
                raise RuntimeError('Refusing to adopt an unrelated systemd override')
            shutil.copy2(unit, backup / name)
        if name in WORKERS:
            dropins = path('/etc/systemd/system') / (name + '.d')
            for item in dropins.glob('*.conf'):
                keys = {line.split('=', 1)[0].strip() for line in item.read_text().splitlines() if '=' in line}
                if keys & {'User', 'Group', 'SupplementaryGroups', 'ExecStart', 'ExecStartPre', 'CapabilityBoundingSet', 'RootDirectory', 'RootImage'}:
                    raise RuntimeError('A native service drop-in overrides the managed launcher; reconcile it before installation')
    wrapper = path(WRAPPER)
    if wrapper.exists() or wrapper.is_symlink():
        if wrapper.is_symlink() or ('harness-worker' not in wrapper.read_text() and '/opt/huou07-playground/current/bin/h07p-server worker' not in wrapper.read_text()):
            raise RuntimeError('Refusing to adopt an unrelated native owner entry point')
        shutil.copy2(wrapper, backup / 'h07p-harness')
    old = path('/opt/huou07-playground/current')
    if old.exists() or old.is_symlink():
        if old.is_symlink():
            link = os.readlink(old)
            resolved = (path(link) if link.startswith('/') else old.parent / link).resolve()
        else:
            resolved = old.resolve()
        releases = path('/opt/huou07-playground/releases').resolve()
        if resolved.parent != releases or not resolved.is_dir():
            raise RuntimeError('Current release is outside protected release directory')
        copy_tree(resolved, backup / 'release')
    # Stop both SQLite writers before copying a restorable, consistent state directory.
    try:
        stop_transient_workers()
        for name in SERVICES:
            if states.get(name, {}).get('active'):
                service('stop', name)
        for name, value in [('state', '/var/lib/huou07-playground'), ('control', '/var/lib/h07p-control')]:
            source = path(value)
            if source.is_symlink():
                raise RuntimeError('Refusing symbolic link state directory')
            if source.is_dir():
                copy_tree(source, backup / name)
    except Exception:
        for name in reversed(SERVICES):
            if states.get(name, {}).get('active'):
                service('start', name, check=False)
        raise
    pointer = path('/var/lib/huou07-package/transaction.new')
    pointer.write_text(json.dumps({'backup': backup.name}))
    pointer.replace(path('/var/lib/huou07-package/transaction.json'))
    pending.write_text(json.dumps({'backup': backup.name}))
    adoption = path('/var/lib/huou07-package/adoption.json')
    if not adoption.exists():
        adoption.write_text(json.dumps({'backup': backup.name}))


def activate(target):
    parent = protected('/opt/huou07-playground')
    temporary = parent / 'current.new'
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    temporary.replace(parent / 'current')


def rollback():
    backup = current_backup()
    if backup is None:
        raise RuntimeError('No package rollback snapshot')
    stop_transient_workers()
    for name in SERVICES:
        service('stop', name, check=False)
    release = backup / 'release'
    if release.is_dir():
        # A durable release copy survives dpkg removing files from an older version.
        restored = protected('/opt/huou07-playground/releases') / ('rollback-' + backup.name)
        if not restored.exists():
            copy_tree(release, restored)
        activate('/opt/huou07-playground/releases/' + restored.name)
    else:
        path('/opt/huou07-playground/current').unlink(missing_ok=True)
    for name in SERVICES:
        unit = path('/etc/systemd/system') / name
        unit.unlink(missing_ok=True)
        if (backup / name).exists():
            shutil.copy2(backup / name, unit)
    wrapper = path(WRAPPER)
    wrapper.unlink(missing_ok=True)
    if (backup / 'h07p-harness').exists():
        shutil.copy2(backup / 'h07p-harness', wrapper)
    for name, value in [('state', '/var/lib/huou07-playground'), ('control', '/var/lib/h07p-control')]:
        saved = backup / name
        if saved.is_dir():
            destination = path(value)
            # Retain failed-version data for diagnosis, never delete user state.
            failed = destination.with_name(destination.name + '.failed-' + backup.name + '-' + str(time.time_ns()))
            if destination.exists():
                destination.rename(failed)
            if not destination.exists():
                copy_tree(saved, destination)
    service('daemon-reload')
    states = json.loads((backup / 'services.json').read_text()) if (backup / 'services.json').exists() else {}
    for name in SERVICES:
        service('enable' if states.get(name, {}).get('enabled') else 'disable', name, check=False)
    if release.is_dir():
        if (release / 'bin/h07p-server').exists():
            service('start', 'h07p-helper.service', check=False)
        service('start', 'huou07-playground.service', check=False)
    for name in WORKERS:
        if states.get(name, {}).get('active'):
            service('start', name, check=False)
    path('/var/lib/huou07-package/pending.json').unlink(missing_ok=True)


def configure():
    if LIVE:
        if subprocess.run(['getent', 'group', 'huou07-dsh-link'], stdout=subprocess.DEVNULL).returncode:
            subprocess.run(['addgroup', '--system', 'huou07-dsh-link'], check=True, stdout=subprocess.DEVNULL)
        result = subprocess.run(['getent', 'passwd', 'huou07-playground'], capture_output=True, text=True)
        if result.returncode:
            subprocess.run(['adduser', '--system', '--group', '--no-create-home', '--home', '/nonexistent', 'huou07-playground'], check=True, stdout=subprocess.DEVNULL)
        else:
            fields = result.stdout.strip().split(':')
            if int(fields[2]) >= 1000 or fields[5] != '/nonexistent' or fields[6] != '/usr/sbin/nologin':
                raise RuntimeError('Existing dashboard account is not a dedicated service identity')
    state = protected('/var/lib/huou07-playground', 0o750)
    protected('/var/lib/h07p-control', 0o700)
    protected('/var/lib/h07p-private', 0o711)
    nas = protected('/var/lib/h07p-private/nas', 0o700)
    if LIVE:
        import pwd
        account = pwd.getpwnam('huou07-playground')
        os.chown(state, account.pw_uid, account.pw_gid)
        os.chown(nas, account.pw_uid, account.pw_gid)
    version = path('/usr/lib/huou07-playground/version').read_text().strip()
    if not version or '/' in version or version in ('.', '..'):
        raise RuntimeError('Invalid installed release version')
    for name in SERVICES:
        path('/etc/systemd/system').mkdir(parents=True, exist_ok=True)
        path('/etc/systemd/system/' + name).unlink(missing_ok=True)
    activate('/opt/huou07-playground/releases/' + version)
    destination = protected('/usr/local/sbin') / 'h07p-harness'
    shutil.copy2(path('/usr/lib/huou07-playground/h07p-harness'), destination)
    if LIVE:
        os.chown(destination, 0, 0)
    try:
        service('daemon-reload')
        service('enable', *DASHBOARD)
        service('restart', 'h07p-helper.service')
        service('restart', 'huou07-playground.service')
        if LIVE:
            backup = current_backup()
            states = json.loads((backup / 'services.json').read_text()) if backup else {}
            for name in WORKERS:
                harness = name.removeprefix('h07p-').removesuffix('.service')
                if subprocess.run(['getent', 'passwd', harness + '-worker'], stdout=subprocess.DEVNULL).returncode == 0:
                    previous = states.get(name, {})
                    if previous.get('enabled'):
                        service('enable', name)
                    if previous.get('active'):
                        service('restart', name)
                        time.sleep(0.5)
                        service('is-active', '--quiet', name)
        if LIVE and path('/run/systemd/system').is_dir():
            port = '8765'
            for line in path('/etc/huou07-playground/dashboard.env').read_text().splitlines():
                if line.startswith('PORT='):
                    port = str(int(line[5:]))
            for _ in range(40):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:' + port + '/api/health', timeout=0.5) as response:
                        healthy = response.status == 200 and json.load(response).get('ok') is True
                    if healthy:
                        service('is-active', '--quiet', *DASHBOARD)
                        return
                except (OSError, ValueError):
                    pass
                time.sleep(0.25)
            raise RuntimeError('Dashboard health check failed')
    except Exception:
        raise


def main():
    script = os.environ.get('H07P_MAINT_SCRIPT', Path(sys.argv[0]).name)
    for name in ('preinst', 'postinst', 'prerm', 'postrm'):
        if script.endswith('.' + name):
            script = name
            break
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    if script == 'preinst' and action in ('install', 'upgrade'):
        prepare()
    elif script == 'postinst' and action == 'configure':
        try:
            configure()
            path('/var/lib/huou07-package/pending.json').unlink(missing_ok=True)
        except Exception:
            rollback()
            raise
    elif script == 'postinst' and action == 'abort-upgrade':
        if path('/var/lib/huou07-package/pending.json').exists():
            rollback()
    elif script == 'postrm' and action in ('abort-install', 'abort-upgrade'):
        if path('/var/lib/huou07-package/pending.json').exists():
            rollback()
    elif script == 'prerm' and action == 'remove':
        stop_transient_workers()
        for name in SERVICES:
            service('disable', '--now', name, check=False)
    elif script == 'postrm' and action in ('remove', 'purge'):
        service('daemon-reload', check=False)
        adoption = path('/var/lib/huou07-package/adoption.json')
        if adoption.exists():
            name = json.loads(adoption.read_text())['backup']
            if not name.isdigit():
                raise RuntimeError('Invalid native service adoption snapshot')
            restore_workers(path('/var/backups/huou07-playground') / name)
        # Owner state, NAS, native CLI stores and rollback snapshots are intentionally retained.
    elif script == 'lifecycle.py' and action == 'rollback':
        rollback()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('H07P package operation failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
