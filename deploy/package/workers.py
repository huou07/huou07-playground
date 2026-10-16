#!/usr/bin/python3
"""Typed account/ACL provisioning only; never installs apps or rewrites native auth."""
import argparse
import grp
import importlib.util
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import time

CATALOG=('dsh-worker','codex-worker','opencode-worker')
HOME=Path('/home/huou07')


def command(*arguments):
    subprocess.run([str(argument) for argument in arguments],check=True,stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90)


def trusted(path):
    for component in (path,*path.parents):
        info=component.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
            raise RuntimeError('Worker setup requires a root-owned protected installation')


def account(name):
    try: user=pwd.getpwnam(name)
    except KeyError:return None
    if (user.pw_uid==0 or user.pw_uid==pwd.getpwnam('huou07').pw_uid or user.pw_dir!=str(HOME)
            or user.pw_gid in (0,pwd.getpwnam('huou07').pw_gid)
            or grp.getgrnam(name).gr_gid!=user.pw_gid
            or any((other.pw_uid==user.pw_uid or other.pw_gid==user.pw_gid) and other.pw_name!=name for other in pwd.getpwall())):
        raise RuntimeError('Refusing an unrelated or aliased worker account')
    return user


def save_records(registry,records):
    temporary=registry.with_suffix(f'.{time.monotonic_ns()}.pending')
    with temporary.open('x') as output:
        os.chmod(temporary,0o600);json.dump(records,output);output.flush();os.fsync(output.fileno())
    temporary.replace(registry)
    directory=os.open(registry.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)


def finish_retirement(name,record):
    retired=pwd.getpwnam(record['retired'])
    if retired.pw_uid!=record['uid'] or retired.pw_gid!=record['gid'] or retired.pw_dir!='/nonexistent' or retired.pw_shell!='/usr/sbin/nologin':
        raise RuntimeError('Unexpected retired identity')
    try:old_group=grp.getgrnam(name)
    except KeyError:
        if grp.getgrnam(f"h07p-retired-{record['gid']}").gr_gid!=record['gid']:
            raise RuntimeError('Unexpected retired group')
    else:
        if old_group.gr_gid!=record['gid'] or old_group.gr_mem:
            raise RuntimeError('Refusing to rename an unrelated worker group')
        command('groupmod','--new-name',f"h07p-retired-{record['gid']}",name)
    record['state']='removed'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('create','repair','remove'))
    parser.add_argument('--control-dir',required=True,type=Path)
    parser.add_argument('workers',nargs='+',choices=CATALOG)
    args=parser.parse_args()
    assert os.geteuid()==0
    control=args.control_dir
    trusted(control)
    source=Path(__file__).with_name('worker-acl.py')
    trusted(source)
    spec=importlib.util.spec_from_file_location('h07p_worker_acl',source)
    acl=importlib.util.module_from_spec(spec);spec.loader.exec_module(acl)
    if HOME.is_symlink() or pwd.getpwnam('huou07').pw_dir!=str(HOME):
        raise RuntimeError('Unexpected shared owner home')
    selected=tuple(dict.fromkeys(args.workers))
    for name in selected: account(name)
    registry=control/'worker-accounts.json'
    records=json.loads(registry.read_text()) if registry.exists() else {}
    if args.action=='remove':
        for name in selected:
            user=account(name)
            if user is None:
                if records.get(name,{}).get('state')=='removing':finish_retirement(name,records[name])
                continue
            # Keep a locked UID tombstone so old file ownership/ACLs are never recycled.
            retired=f'h07p-retired-{user.pw_uid}'
            records[name]=dict(state='removing',retired=retired,uid=user.pw_uid,gid=user.pw_gid,at=int(time.time()))
            save_records(registry,records)
            command('usermod','--lock','--groups','','--shell','/usr/sbin/nologin',name)
            command('usermod','--login',retired,'--home','/nonexistent',name)
            finish_retirement(name,records[name])
    else:
        private=Path('/etc/h07p-workers/private-paths.json')
        extra=json.loads(private.read_text()) if private.exists() else []
        if not isinstance(extra,list) or any(not isinstance(p,str) or not p or p.startswith('/') or '..' in Path(p).parts for p in extra):
            raise RuntimeError('Invalid private-path manifest')
        acl.validate_boundaries(extra)
        # Complete inspection before any account/permission change. No secret contents.
        groups=acl.inventory(extra,max_entries=100000,max_seconds=15)
        backup=acl.backup([p for paths in groups.values() for p in paths])
        for name in selected:
            if account(name) is None:
                if records.get(name,{}).get('state')=='removing':
                    finish_retirement(name,records[name]);save_records(registry,records)
                command('useradd','--system','--no-create-home','--user-group','--home-dir',HOME,'--shell','/bin/bash',name)
            command('usermod','--groups','','--shell','/bin/bash',name);command('usermod','--lock',name)
        acl.WORKERS=selected
        for paths in groups.values():
            for path in paths:
                if path.is_symlink():raise RuntimeError('Managed boundary changed during provisioning')
        for kind,permission in (('shared','rwX'),('readonly','r-X'),('private','---')):
            acl.acl(groups[kind],permission)
        existing=tuple(name for name in CATALOG if account(name) is not None)
        for relative,owner in acl.NATIVE.items():
            path=HOME/relative
            if owner in selected:
                path.mkdir(parents=True,exist_ok=True)
                if path.stat().st_uid!=account(owner).pw_uid:
                    command('chown','-R','-P','--no-dereference',f'{owner}:{owner}','--',path)
                peers=[name for name in existing if name!=owner]
                entries=[f'u:{name}:---,d:u:{name}:---' for name in peers]
                entries.append('u:huou07:rwx,d:u:huou07:rwx')
                command('setfacl','-m',','.join(entries),'--',path)
                instructions=path/'AGENTS.md'
                if relative in ('.dsh','.codex','.config/opencode') and not instructions.exists():
                    instructions.write_text(f'# {owner} global instructions\n\nUse project AGENTS.md and .agents/skills. Run as your own worker UID.\n')
                    user=account(owner);os.chown(instructions,user.pw_uid,user.pw_gid)
            elif path.exists():
                command('setfacl','-m',','.join(f'u:{name}:---,d:u:{name}:---' for name in selected),'--',path)
        acl.protect_ancestors([*groups['private'],*(HOME/p for p in acl.NATIVE),*(HOME/p for p in acl.READONLY)])
        for name in selected:
            records[name]=dict(state='ready',uid=account(name).pw_uid,backup=str(backup),at=int(time.time()))
    save_records(registry,records)
    print(json.dumps(dict(ok=True,workers=list(selected),action=args.action,data_retained=True)))


if __name__=='__main__':
    try:main()
    except Exception:
        # Never forward subprocess, owner-file or native-store content into logs/API.
        raise SystemExit('Worker setup failed. Workers must remain stopped; repair the account/ACL setup and retry.')
