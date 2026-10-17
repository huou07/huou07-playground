#!/usr/bin/python3
"""Typed account/ACL provisioning only; never installs apps or rewrites native auth."""
import argparse
import atexit
import shutil
import grp
import importlib.util
import json
import sqlite3
import itertools
import resource
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


ACL_BASELINE_ROOT=Path(os.environ.get('H07P_ACL_BACKUP_ROOT') or '/var/backups/h07p-harness-workers')


def acl_snapshot_name(name):
    # The adapter writes YYYYMMDD-HHMMSS or YYYYMMDD-HHMMSS-<extra> snapshots.
    if len(name)<15 or not name[:8].isdigit() or name[8]!='-' or not name[9:15].isdigit():
        return False
    return len(name)==15 or name[15]=='-'


def select_acl_baseline(root=None,expected_uid=0):
    """Newest validated pre-worker ACL snapshot, replacing a fixed historical path."""
    root=ACL_BASELINE_ROOT if root is None else Path(root)
    best=None
    try: candidates=list(root.iterdir())
    except OSError: return None
    for directory in candidates:
        if not acl_snapshot_name(directory.name): continue
        candidate=directory/'acl.restore'
        try:
            info=candidate.lstat();parent=directory.lstat()
        except OSError: continue
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode): continue
        if info.st_uid!=expected_uid or info.st_mode&0o022: continue
        if not 1_000_000<=info.st_size<=500*1024*1024: continue
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=expected_uid or parent.st_mode&0o022: continue
        if best is None or info.st_mtime_ns>best[0]: best=(info.st_mtime_ns,candidate)
    return None if best is None else best[1]


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


def progress(control,job,phase,count):
    target=control/'worker-progress.json';temporary=target.with_suffix('.pending')
    with temporary.open('w') as output:
        os.chmod(temporary,0o600);json.dump(dict(id=job,phase=phase,count=count,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),output)
    temporary.replace(target)


def batches(database,kind=None):
    cursor=database.execute('SELECT path,dev,ino FROM paths'+(' WHERE kind=?' if kind else ''),() if kind is None else (kind,))
    while rows:=cursor.fetchmany(150):
        paths=[]
        for path,device,inode in rows:
            metadata=os.lstat(path)
            if stat.S_ISLNK(metadata.st_mode) or metadata.st_dev!=device or metadata.st_ino!=inode:
                raise RuntimeError('Managed object changed during provisioning')
            paths.append(Path(os.fsdecode(path)))
        yield paths


def home_inventory():
    """Yield metadata-only home paths without following symlinks or crossing mounts."""
    metadata=HOME.lstat();device=metadata.st_dev;count=0;started=time.monotonic()
    yield HOME,metadata
    stack=[iter(os.scandir(HOME))]
    while stack:
        entry=next(stack[-1],None)
        if entry is None:
            stack.pop();continue
        count+=1
        if count>5_000_000 or time.monotonic()-started>300:
            raise RuntimeError('Shared-home ACL reset exceeded its 5 million object / 5 minute bound')
        if entry.is_symlink():continue
        metadata=entry.stat(follow_symlinks=False)
        if metadata.st_dev!=device or not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):continue
        path=Path(entry.path)
        yield path,metadata
        if stat.S_ISDIR(metadata.st_mode):stack.append(iter(os.scandir(path)))


def decode_acl_path(raw):
    """Decode getfacl's octal pathname escapes without treating them as shell syntax."""
    if raw.startswith(b'"') and raw.endswith(b'"'):
        raw=raw[1:-1]
    decoded=bytearray();index=0
    while index<len(raw):
        if raw[index]!=ord('\\'):
            decoded.append(raw[index]);index+=1;continue
        tail=raw[index+1:index+4]
        if len(tail)==3 and all(ord('0')<=digit<=ord('7') for digit in tail):
            decoded.append(int(tail,8));index+=4;continue
        if index+1<len(raw) and raw[index+1] in (ord('\\'),ord('"')):
            decoded.append(raw[index+1]);index+=2;continue
        raise RuntimeError('The saved ACL baseline contains an unsupported pathname escape')
    return os.fsdecode(bytes(decoded))


def filter_baseline(source,destination,control,job,home_device):
    """Drop stale/moved paths from the dated baseline before asking setfacl to restore it."""
    count=restored=missing=0;block=[];path=None;started=time.monotonic()
    with source.open('rb') as input_file,destination.open('xb') as output:
        os.chmod(destination,0o600)
        def flush():
            nonlocal restored,missing,block,path
            if path is None:
                output.writelines(block)
            else:
                try:metadata=os.lstat(path)
                except FileNotFoundError:
                    missing+=1
                else:
                    if stat.S_ISLNK(metadata.st_mode) or metadata.st_dev!=home_device:
                        missing+=1
                    else:
                        output.writelines(block);restored+=1
            block=[];path=None
        for line in input_file:
            if line.startswith(b'# file: '):
                flush();raw=line[len(b'# file: '):].rstrip(b'\r\n')
                path=decode_acl_path(raw)
                if not os.path.isabs(path) or os.path.commonpath((str(HOME),path))!=str(HOME):
                    raise RuntimeError('The saved ACL baseline contains a path outside the shared home')
                block=[line];count+=1
                if count>5_000_000 or time.monotonic()-started>300:
                    raise RuntimeError('Saved ACL baseline filtering exceeded its 5 million record / 5 minute bound')
                if count%10000==0:progress(control,job,'Filtering stale ACL baseline records',count)
            else:
                block.append(line)
        flush();output.flush();os.fsync(output.fileno())
    if not restored:
        raise RuntimeError('No existing home objects matched the saved ACL baseline')
    return restored,missing


def reset_acl(job,control):
    baseline=select_acl_baseline()
    if baseline is None:
        raise RuntimeError('No validated pre-worker ACL baseline snapshot is available')
    trusted(baseline)
    info=baseline.stat()
    if not 1_000_000<=info.st_size<=500*1024*1024:
        raise RuntimeError('The saved pre-worker ACL baseline has an unexpected size')
    # New rollback snapshots share the configured registry root so selection and
    # creation can never drift apart when the root is configured away from the default.
    ACL_BASELINE_ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    backup_dir=ACL_BASELINE_ROOT/(time.strftime('%Y%m%d-%H%M%S')+'-acl-reset-'+str(time.time_ns()))
    backup_dir.mkdir(mode=0o700);backup_dir.parent.chmod(0o700)
    backup=backup_dir/'acl.restore';count=0;paths=[]
    with backup.open('xb') as output:
        os.chmod(backup,0o600)
        for path,metadata in home_inventory():
            current=path.lstat()
            if current.st_dev!=metadata.st_dev or current.st_ino!=metadata.st_ino:
                raise RuntimeError('A shared-home object changed during ACL reset review')
            paths.append(path);count+=1
            if len(paths)>=150:
                subprocess.run(['getfacl','-p','--',*[str(item) for item in paths]],check=True,stdout=output,stderr=subprocess.DEVNULL,timeout=90)
                paths.clear()
            if count%10000==0:progress(control,job,'Saving current ACL rollback snapshot',count)
        if paths:subprocess.run(['getfacl','-p','--',*[str(item) for item in paths]],check=True,stdout=output,stderr=subprocess.DEVNULL,timeout=90)
        output.flush();os.fsync(output.fileno())
    filtered=backup_dir/'baseline.filtered.restore'
    root_device=HOME.stat().st_dev
    restored,missing=filter_baseline(baseline,filtered,control,job,root_device)
    try:
        subprocess.run(['setfacl','--test',f'--restore={filtered}'],check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=900)
    except Exception:
        raise RuntimeError(f'Saved ACL baseline could not be safely reviewed; current ACL snapshot is {backup}')
    progress(control,job,'Removing worker ACLs while preserving file contents',count)
    directories=[];files=[];cleared=0
    try:
        for path,metadata in home_inventory():
            batch=directories if stat.S_ISDIR(metadata.st_mode) else files
            batch.append(path)
            if len(batch)>=150:
                args=['setfacl','-b']+(['-k'] if batch is directories else [])+['--',*[str(item) for item in batch]]
                subprocess.run(args,check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90)
                cleared+=len(batch);batch.clear()
                if cleared%10000==0:progress(control,job,'Removing worker ACLs while preserving file contents',cleared)
        for batch,is_directory in ((directories,True),(files,False)):
            if batch:
                args=['setfacl','-b']+(['-k'] if is_directory else [])+['--',*[str(item) for item in batch]]
                subprocess.run(args,check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90)
        progress(control,job,'Restoring saved pre-worker ACL baseline',cleared)
        subprocess.run(['setfacl',f'--restore={filtered}'],check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=900)
    except Exception:
        try:subprocess.run(['setfacl',f'--restore={backup}'],check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=900)
        except Exception:raise RuntimeError(f'ACL reset failed and rollback needs recovery from {backup}')
        raise RuntimeError(f'ACL reset failed; the prior ACL snapshot was restored from {backup}')
    progress(control,job,f'Pre-worker ACL baseline restored ({missing} retired paths skipped); worker launches remain stopped',cleared)
    return str(backup)


def stage(acl,extra,control,job):
    plan=control/f'worker-plan-{job}.sqlite'
    descriptor=os.open(plan,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(descriptor)
    database=sqlite3.connect(plan)
    def cleanup_plan():
        database.close()
        plan.unlink(missing_ok=True)
    atexit.register(cleanup_plan)
    database.execute('PRAGMA journal_mode=OFF');database.execute('PRAGMA synchronous=OFF');database.execute('PRAGMA cache_size=-4096')
    database.execute('CREATE TABLE paths(path BLOB,kind TEXT,dev INTEGER,ino INTEGER)')
    batch=[];count=0
    for kind,path,metadata in acl.iter_inventory(extra,max_entries=5000000,max_seconds=300):
        batch.append((os.fsencode(path),kind,metadata.st_dev,metadata.st_ino));count+=1
        if len(batch)==1000:
            database.executemany('INSERT INTO paths VALUES(?,?,?,?)',batch);batch.clear()
            if count%10000==0:progress(control,job,'Inspecting metadata',count)
    if batch:database.executemany('INSERT INTO paths VALUES(?,?,?,?)',batch)
    database.commit();progress(control,job,'Saving ACL rollback snapshot',count)
    directory=Path('/var/backups/h07p-harness-workers')/(time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns()))
    directory.mkdir(parents=True,mode=0o700);directory.parent.chmod(0o700)
    try:
        with (directory/'acl.restore').open('wb') as output:
            os.chmod(directory/'acl.restore',0o600)
            for paths in batches(database):
                subprocess.run(['getfacl','-p','--',*[str(path) for path in paths]],check=True,stdout=output,stderr=subprocess.DEVNULL,timeout=90)
            for relative in acl.NATIVE:
                path=HOME/relative
                if path.exists():subprocess.run(['getfacl','-R','-P','-p','--',str(path)],check=True,stdout=output,stderr=subprocess.DEVNULL,timeout=90)
            output.flush();os.fsync(output.fileno())
    except Exception:
        shutil.rmtree(directory)
        raise
    return database,plan,directory


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('create','repair','remove','reset-acl'))
    parser.add_argument('--control-dir',required=True,type=Path)
    parser.add_argument('--job-id',required=True)
    parser.add_argument('workers',nargs='+',choices=CATALOG)
    args=parser.parse_args()
    assert os.geteuid()==0
    control=args.control_dir
    job=args.job_id
    if len(job)!=64 or any(character not in '0123456789abcdef' for character in job):raise RuntimeError('Invalid setup job')
    trusted(control)
    source=Path(__file__).with_name('worker-acl.py')
    trusted(source)
    spec=importlib.util.spec_from_file_location('h07p_worker_acl',source)
    acl=importlib.util.module_from_spec(spec);spec.loader.exec_module(acl)
    if HOME.is_symlink() or pwd.getpwnam('huou07').pw_dir!=str(HOME):
        raise RuntimeError('Unexpected shared owner home')
    for stale in control.glob('worker-plan-*.sqlite'):
        token=stale.name.removeprefix('worker-plan-').removesuffix('.sqlite')
        info=stale.lstat()
        if len(token)==64 and all(c in '0123456789abcdef' for c in token) and stat.S_ISREG(info.st_mode) and info.st_uid==0:
            stale.unlink()
    selected=tuple(dict.fromkeys(args.workers))
    if args.action=='reset-acl':
        if set(selected)!=set(CATALOG):raise RuntimeError('ACL reset requires all supported worker identities to be selected')
        rollback=reset_acl(job,control)
        print(json.dumps(dict(ok=True,workers=list(selected),action=args.action,data_retained=True,rollback_snapshot=rollback)))
        return
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
        database,plan,backup=stage(acl,extra,control,job)
        for name in selected:
            if account(name) is None:
                if records.get(name,{}).get('state')=='removing':
                    finish_retirement(name,records[name]);save_records(registry,records)
                command('useradd','--system','--no-create-home','--user-group','--home-dir',HOME,'--shell','/bin/bash',name)
            command('usermod','--groups','','--shell','/bin/bash',name);command('usermod','--lock',name)
        acl.WORKERS=selected
        for kind,permission in (('shared','rwX'),('readonly','r-X'),('private','---')):
            count=0
            for paths in batches(database,kind):
                acl.acl(paths,permission);count+=len(paths)
                if count%1500==0:progress(control,job,'Applying '+kind+' ACLs',count)
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
        private_paths=(Path(os.fsdecode(row[0])) for row in database.execute("SELECT path FROM paths WHERE kind='private'"))
        acl.protect_ancestors(itertools.chain(private_paths,(HOME/p for p in acl.NATIVE),(HOME/p for p in acl.READONLY)))
        for name in selected:
            records[name]=dict(state='ready',uid=account(name).pw_uid,backup=str(backup),at=int(time.time()))
        database.close();plan.unlink()
    save_records(registry,records)
    progress(control,job,'Account changes prepared; verifying policy',len(selected))
    print(json.dumps(dict(ok=True,workers=list(selected),action=args.action,data_retained=True)))


if __name__=='__main__':
    try:main()
    except Exception:
        # Never forward subprocess, owner-file or native-store content into logs/API.
        raise SystemExit('Worker setup failed. Workers must remain stopped; repair the account/ACL setup and retry.')
