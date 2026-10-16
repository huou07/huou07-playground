#!/usr/bin/env python3
"""Actual account/ACL lifecycle with private mounts and synthetic NSS files only."""
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import time
import subprocess
import sys
import tempfile


def main():
    assert os.geteuid()==0 and os.readlink('/proc/self/ns/mnt')!=os.readlink('/proc/1/ns/mnt')
    repository=Path(__file__).resolve().parents[2]
    driver_source=(repository/'deploy/package/workers.py').read_bytes()
    acl_source=(repository/'deploy/harness-workers/setup.py').read_bytes()
    root=Path(tempfile.mkdtemp(prefix='h07p-accounts-',dir='/var/tmp'))
    mounts=[]
    helper=None
    def bind(source,target):
        subprocess.run(['mount','--bind',str(source),str(target)],check=True);mounts.append(str(target))
    def command(*args,**kwargs):return subprocess.run([str(a) for a in args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
    try:
        etc=root/'etc';etc.mkdir();(etc/'default').mkdir();(etc/'h07p-workers').mkdir()
        (etc/'h07p-workers/private-paths.json').write_text('[]')
        (etc/'passwd').write_text('root:x:0:0:root:/root:/bin/sh\nhuou07:x:65000:65000:Fixture owner:/home/huou07:/bin/bash\nhuou07-playground:x:65030:65030:Fixture service:/nonexistent:/usr/sbin/nologin\n')
        (etc/'group').write_text('root:x:0:\nhuou07:x:65000:\nhuou07-playground:x:65030:\n')
        (etc/'shadow').write_text('root:!:19000:0:99999:7:::\nhuou07:!:19000:0:99999:7:::\nhuou07-playground:!:19000:0:99999:7:::\n')
        (etc/'gshadow').write_text('root:!::\nhuou07:!::\nhuou07-playground:!::\n')
        (etc/'nsswitch.conf').write_text('passwd: files\ngroup: files\nshadow: files\ngshadow: files\nhosts: files\n')
        (etc/'login.defs').write_text('SYS_UID_MIN 65001\nSYS_UID_MAX 65020\nSYS_GID_MIN 65001\nSYS_GID_MAX 65020\nUID_MIN 65500\nGID_MIN 65500\nCREATE_HOME no\nCREATE_MAIL_SPOOL no\nMAIL_DIR /run/mail\n')
        (etc/'default/useradd').write_text('SHELL=/bin/bash\nCREATE_MAIL_SPOOL=no\n')
        home=root/'home';home.mkdir(mode=0o755);os.chown(home,65000,65000)
        for relative in ('Projects','.ssh','.dsh','.codex','.config/opencode','.local/bin'):
            path=home/relative;path.mkdir(parents=True,exist_ok=True);os.chown(path,65000,65000)
        for relative in ('Projects/ordinary.txt','Projects/blocked-fixture','.ssh/private-fixture','.dsh/native-fixture','.codex/native-fixture','.local/bin/dsh'):
            path=home/relative;path.write_text('synthetic fixture bytes');os.chown(path,65000,65000);path.chmod(0o600 if 'fixture' in relative else 0o755)
        backups=root/'backups';backups.mkdir()
        bind(home,'/home/huou07');bind(backups,'/var/backups');bind(etc,'/etc')
        subprocess.run(['mount','-t','tmpfs','-o','mode=0755,size=8M','tmpfs','/run'],check=True);mounts.append('/run')
        install=Path('/run/h07p-workers-test');install.mkdir(mode=0o755)
        diagnostic=driver_source.replace(b'except Exception:',b'except Exception as failure:').replace(b'        # Never forward',b'        print(type(failure).__name__,file=__import__("sys").stderr)\n        # Never forward')
        (install/'workers.py').write_bytes(diagnostic);(install/'worker-acl.py').write_bytes(acl_source)
        control=install/'control';control.mkdir(mode=0o700)
        binary=str(Path(sys.argv[1]).resolve())
        channel_path=str(install/'admin.sock')
        helper=subprocess.Popen([binary,'helper'],env=dict(PATH='/usr/sbin:/usr/bin:/sbin:/bin',LANG='C.UTF-8',H07P_HELPER_SOCKET=channel_path,H07P_CONTROL_DIR=str(control),H07P_WORKER_SETUP=str(install/'workers.py'),H07P_RELAYS='false',H07P_MANAGED_UNITS='h07p-fixture.service'),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            if Path(channel_path).exists():break
            time.sleep(.02)
        def rpc(op,**values):
            with socket.socket(socket.AF_UNIX) as connection:
                connection.settimeout(8);connection.connect(channel_path)
                connection.sendall((json.dumps(dict(op=op,**values))+'\n').encode())
                reply=json.loads(connection.makefile('rb').readline());assert reply['ok'],reply
                return reply['data']
        def provision(action,*workers,success=True):
            revision=rpc('worker_setup_status')['revision']
            job=rpc('worker_setup_run',action=action,workers=list(workers),confirmed=True,expected_revision=revision)
            for _ in range(500):
                state=rpc('worker_setup_job')
                if state['state']!='running':break
                time.sleep(.02)
            assert state['id']==job['id'] and (state['state']=='completed')==success,state
            return state
        def worker_read(uid,path):
            return subprocess.run(['setpriv',f'--reuid={uid}',f'--regid={uid}','--clear-groups','cat',str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE).returncode
        rpc('apply',expected_revision=0,preset='none',workspace='/home/huou07/Projects',rules=[dict(id='fixture-block',worker='dsh-worker',target='/home/huou07/Projects/blocked-fixture',action='block',operations=['list','read','write','create','delete','execute'],recursive=False,source='manual')])
        provision('create','dsh-worker','codex-worker','opencode-worker')
        dsh=pwd.getpwnam('dsh-worker');codex=pwd.getpwnam('codex-worker')
        assert dsh.pw_uid>65000 and dsh.pw_dir=='/home/huou07'
        assert os.getgrouplist('dsh-worker',dsh.pw_gid)==[dsh.pw_gid]
        assert worker_read(dsh.pw_uid,Path('/home/huou07/Projects/ordinary.txt'))==0
        assert worker_read(dsh.pw_uid,Path('/home/huou07/Projects/blocked-fixture'))!=0
        assert worker_read(dsh.pw_uid,Path('/home/huou07/.ssh/private-fixture'))!=0
        assert worker_read(dsh.pw_uid,Path('/home/huou07/.codex/native-fixture'))!=0
        assert worker_read(dsh.pw_uid,Path('/home/huou07/.dsh/native-fixture'))==0
        assert worker_read(codex.pw_uid,Path('/home/huou07/.dsh/native-fixture'))!=0
        assert Path('/home/huou07/.dsh/AGENTS.md').exists()
        assert Path('/home/huou07/.codex/AGENTS.md').exists()
        provision('repair','dsh-worker')
        old=dsh.pw_uid
        provision('remove','dsh-worker')
        try:pwd.getpwnam('dsh-worker');raise AssertionError('active worker name must be removed')
        except KeyError:pass
        retired=pwd.getpwnam(f'h07p-retired-{old}')
        assert retired.pw_shell=='/usr/sbin/nologin' and retired.pw_dir=='/nonexistent'
        assert Path('/home/huou07/.dsh/native-fixture').exists()
        provision('create','dsh-worker')
        new=pwd.getpwnam('dsh-worker')
        assert new.pw_uid!=old and worker_read(new.pw_uid,Path('/home/huou07/.dsh/native-fixture'))==0
        assert worker_read(new.pw_uid,Path('/home/huou07/.codex/native-fixture'))!=0
        assert worker_read(new.pw_uid,Path('/home/huou07/Projects/blocked-fixture'))!=0
        assert json.loads((control/'worker-accounts.json').read_text())['dsh-worker']['state']=='ready'
        failing=install/'groupmod-fault';failing.write_text('#!/bin/sh\nexit 1\n');failing.chmod(0o755)
        bind(failing,'/usr/sbin/groupmod')
        provision('remove','dsh-worker',success=False)
        assert json.loads((control/'worker-accounts.json').read_text())['dsh-worker']['state']=='removing'
        subprocess.run(['umount','/usr/sbin/groupmod'],check=True);mounts.remove('/usr/sbin/groupmod')
        provision('repair','dsh-worker')
        recovered=pwd.getpwnam('dsh-worker')
        assert recovered.pw_uid not in (old,new.pw_uid)
        assert worker_read(recovered.pw_uid,Path('/home/huou07/.dsh/native-fixture'))==0
        (install/'workers.py').chmod(0o666)
        provision('repair','dsh-worker',success=False)
        pending=json.loads((control/'policy.json').read_text())
        assert pending['revision']!=pending['enforced_revision']
        (install/'workers.py').chmod(0o644)
        provision('repair','dsh-worker')
        enforced=json.loads((control/'policy.json').read_text())
        assert enforced['revision']==enforced['enforced_revision']
        print(json.dumps(dict(result='passed',checks=24,scope='real typed helper jobs, useradd/usermod/groupmod, worker DAC/ACL, failed pending policy and repair; synthetic NSS/private mounts',host_accounts_changed=False,owner_data_used=False)))
    finally:
        if helper is not None:
            helper.terminate()
            try:helper.wait(timeout=5)
            except subprocess.TimeoutExpired:helper.kill();helper.wait()
        for target in reversed(mounts):subprocess.run(['umount',target],check=True)
        shutil.rmtree(root)

if __name__=='__main__':main()
