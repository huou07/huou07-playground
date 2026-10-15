#!/usr/bin/env python3
"""Real descriptor adapter, cancellation and ENOSPC in a private mount namespace.

sudo unshare --mount --fork --propagation private python3 tests/native/files.py BINARY
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile


def main():
    assert os.geteuid() == 0
    assert os.readlink('/proc/self/ns/mnt') != os.readlink('/proc/1/ns/mnt'), 'private mount namespace required'
    binary = str(Path(sys.argv[1]).resolve())
    root = Path(tempfile.mkdtemp(prefix='h07p-fs-', dir='/var/tmp'))
    root.chmod(0o755)
    nas = root / 'nas'
    nas.mkdir()
    user = pwd.getpwnam('huou07-playground')
    checks = 0

    def demote():
        os.setgroups([])
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)

    def actor(request, payload=b''):
        process = subprocess.run([binary, 'fs-actor'], input=(json.dumps(request)+'\n').encode()+payload,
                                 env={'H07P_NAS_DIR': str(nas)}, preexec_fn=demote,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
        line, _, data = process.stdout.partition(b'\n')
        return json.loads(line), data

    def check(condition, message):
        nonlocal checks
        assert condition, message
        checks += 1

    mounted = False
    try:
        subprocess.run(['mount', '-t', 'tmpfs', '-o', 'size=2M,mode=0700', 'tmpfs', str(nas)], check=True)
        mounted = True
        os.chown(nas, user.pw_uid, user.pw_gid)
        response, _ = actor(dict(op='fs_upload', area='nas', path='/full.bin', length=4*1024*1024), b'x'*(4*1024*1024))
        check(not response['ok'], 'ENOSPC is a failure')
        check(not (nas/'full.bin').exists(), 'ENOSPC never publishes a completed destination')
        check(not list(nas.glob('.h07p-upload-*')), 'ENOSPC removes temporary uploads')
        response, _ = actor(dict(op='fs_upload', area='nas', path='/short.bin', length=1000), b'partial')
        check(not response['ok'] and not (nas/'short.bin').exists(), 'canceled/short upload is not published')
        check(not list(nas.glob('.h07p-upload-*')), 'short upload cleans temporary files')
        response, _ = actor(dict(op='fs_list', area='nas', path='/'))
        check(response['data']['capacity']['total'] == 2*1024*1024, 'capacity reflects actual selected mount')
        os.mkfifo(nas/'fifo', 0o600)
        os.chown(nas/'fifo', user.pw_uid, user.pw_gid)
        response, _ = actor(dict(op='fs_read', area='nas', path='/fifo'))
        check(not response['ok'], 'FIFO replacement fails promptly instead of blocking')
        os.symlink('/etc/passwd', nas/'alias')
        response, _ = actor(dict(op='fs_read', area='nas', path='/alias'))
        check(not response['ok'], 'symlink cannot escape the NAS descriptor root')
        subprocess.run(['umount', str(nas)], check=True)
        mounted = False
        nas.chmod(0o700)
        os.chown(nas, user.pw_uid, user.pw_gid)
        # Stream two different sizes with fixed buffers; compare transfer hashes and RSS.
        peaks = []
        for size in (16*1024*1024, 64*1024*1024):
            name = '/stream-' + str(size)
            p = subprocess.Popen([binary,'fs-actor'], env={'H07P_NAS_DIR':str(nas)}, preexec_fn=demote,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            p.stdin.write((json.dumps(dict(op='fs_upload',area='nas',path=name,length=size))+'\n').encode())
            digest = hashlib.sha256()
            block = b'bounded synthetic file data\n' * 2048
            sent = 0
            peak = 0
            while sent < size:
                chunk = block[:min(len(block),size-sent)]
                p.stdin.write(chunk)
                digest.update(chunk)
                sent += len(chunk)
                fields = Path(f'/proc/{p.pid}/status').read_text().splitlines()
                peak = max(peak, *[int(line.split()[1]) for line in fields if line.startswith('VmRSS:')])
            p.stdin.close()
            check(json.loads(p.stdout.readline())['ok'] and p.wait(timeout=10)==0, 'streaming upload completes')
            p = subprocess.Popen([binary,'fs-actor'], env={'H07P_NAS_DIR':str(nas)}, preexec_fn=demote,
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            p.stdin.write((json.dumps(dict(op='fs_read',area='nas',path=name))+'\n').encode())
            p.stdin.close()
            check(json.loads(p.stdout.readline())['data']['length']==size, 'stream size metadata')
            received = hashlib.sha256()
            while chunk := p.stdout.read(65536):
                received.update(chunk)
            check(p.wait(timeout=10)==0 and received.digest()==digest.digest(), 'stream hash integrity')
            peaks.append(peak)
        check(max(peaks)<16*1024 and abs(peaks[1]-peaks[0])<8*1024, 'adapter RSS stays bounded across file sizes')
        print(json.dumps(dict(result='passed',checks=checks,runtime='real Debian private mount namespace',
                              upload_sizes_mib=[16,64],adapter_peak_rss_kib=peaks,production_data_used=False)))
    finally:
        if mounted:
            subprocess.run(['umount',str(nas)],check=True)
        shutil.rmtree(root)


if __name__ == '__main__':
    main()
