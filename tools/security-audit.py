#!/usr/bin/env python3
"""Credential Guard P0: metadata and actual-UID access checks, never secret bytes.

Explicit authorized Debian execution:
  sudo python3 security-audit.py --output /private/audit-directory
No policies, credentials, services, logs or application data are modified.
"""
import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pwd
import subprocess

OWNER = 'huou07'
HOME = Path('/home') / OWNER
WORKERS = ['dsh-worker', 'codex-worker', 'opencode-worker']
STORES = {
    'dsh': [HOME/'.dsh', HOME/'.dsh/credentials.json'],
    'codex': [HOME/'.codex', HOME/'.codex/auth.json'],
    'opencode': [HOME/'.config/opencode', HOME/'.local/share/opencode',
                 HOME/'.local/share/opencode/auth.json', HOME/'.local/state/opencode', HOME/'.cache/opencode'],
    'owner': [HOME/'.ssh', HOME/'.gnupg', HOME/'.secrets',
              HOME/'.config/huou07-playground', HOME/'.config/litellm', HOME/'.config/omniroute',
              Path('/etc/huou07-playground'), Path('/etc/huou07-playground/opencode-proxy.env'),
              HOME/'.config/huou07-playground/opencode-web.env', Path('/var/lib/huou07-playground'),
              Path('/var/lib/h07p-control'), Path('/var/lib/h07p-private/nas')],
    'shared': [HOME/'Projects/H07P', HOME/'Projects/H07P/AGENTS.md',
               HOME/'Projects/H07P/.agents/skills', HOME/'.local/bin', HOME/'.cargo/bin'],
}
UNITS = ['huou07-playground.service', 'h07p-helper.service', 'h07p-dsh.service', 'h07p-opencode.service']
PROPERTIES = ['User','Group','SupplementaryGroups','MainPID','ActiveState','SubState',
              'NoNewPrivileges','CapabilityBoundingSet','LimitCORE','ProtectHome','ProtectSystem']


def command(args, **kwargs):
    try:
        return subprocess.run(args, capture_output=True, timeout=12, check=False, **kwargs)
    except (OSError, subprocess.TimeoutExpired):
        return None


def safe_path(path):
    return str(path).replace(str(HOME), '$OWNER_HOME')


def text(path):
    # Callers name only public kernel metadata; never authentication/log files.
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def metadata(path):
    try:
        m = path.lstat()
        return dict(exists=True, uid=m.st_uid, gid=m.st_gid, mode=oct(m.st_mode & 0o7777),
                    symlink=path.is_symlink(), directory=path.is_dir(), device=m.st_dev, inode=m.st_ino)
    except OSError:
        return dict(exists=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if os.geteuid()!=0:
        parser.error('root is required for metadata and permanent per-UID checks')
    args.output.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(args.output,0o700)
    services={}
    process_groups={}
    for unit in UNITS:
        result=command(['systemctl','show',unit,'--property='+','.join(PROPERTIES)])
        values={}
        if result and result.returncode==0:
            for line in result.stdout.decode(errors='replace').splitlines():
                key,_,value=line.partition('=')
                if key in PROPERTIES:
                    values[key]=value
            pid=values.get('MainPID','0')
            if pid.isdigit() and int(pid)>0:
                status=text('/proc/'+pid+'/status') or ''
                allowed={}
                for line in status.splitlines():
                    key,_,value=line.partition(':')
                    if key in ['Uid','Gid','Groups','NoNewPrivs','CapEff','CoreDumping']:
                        allowed[key]=value.split()
                values['process_metadata']=allowed
                try: values['executable']=Path(os.readlink('/proc/'+pid+'/exe')).name
                except OSError: values['executable']='UNKNOWN'
                uid=int(allowed.get('Uid',['-1'])[0])
                process_groups[uid]=(int(allowed.get('Gid',['-1'])[0]),[int(g) for g in allowed.get('Groups',[])])
        services[unit]=values
    paths=[]
    for classification,items in STORES.items():
        for path in items:
            paths.append(dict(path=str(path),classification=classification,metadata=metadata(path)))
    for p in ['/var/run/docker.sock', '/run/user/1000/podman/podman.sock', '/run/h07p/admin.sock','/run/h07p/broker.sock']:
        path=Path(p);paths.append(dict(path=p,classification='socket',metadata=metadata(path)))
    matrix=[]
    identities={}
    probe="""import json,os,sys
paths=json.load(sys.stdin)
rows=[]
for item in paths:
 p=item['path']; exists=item['metadata']['exists']
 rows.append({'path':p,'classification':item['classification'],'operations':{
  name:('ALLOW' if os.access(p,mode,effective_ids=True) else 'DENY') if exists else 'UNKNOWN'
  for name,mode in [('read',os.R_OK),('write',os.W_OK),('traverse',os.X_OK),('execute',os.X_OK)]},'debug':'UNKNOWN'})
print(json.dumps({'uid':os.geteuid(),'gid':os.getegid(),'groups':os.getgroups(),'rows':rows}))
"""
    for principal in WORKERS:
        account=pwd.getpwnam(principal)
        gid,groups=process_groups.get(account.pw_uid,(account.pw_gid,os.getgrouplist(principal,account.pw_gid)))
        def demote(uid=account.pw_uid,gid=gid,groups=groups):
            os.setgroups(groups);os.setgid(gid);os.setuid(uid)
        env=dict(HOME=str(HOME),PATH='/usr/bin:/bin',DSH_HOME=str(HOME/'.dsh'),CODEX_HOME=str(HOME/'.codex'))
        result=command(['/usr/bin/python3','-c',probe],input=json.dumps(paths).encode(),env=env,preexec_fn=demote)
        if not result or result.returncode:
            raise SystemExit('Actual-UID metadata probe failed; audit is incomplete')
        values=json.loads(result.stdout)
        if values['uid']!=account.pw_uid:
            raise SystemExit('UID mismatch; audit is incomplete')
        identities[principal]={k:values[k] for k in ['uid','gid','groups']}
        for row in values['rows']:
            row['principal']=principal
            row['path']=safe_path(row['path'])
            matrix.append(row)
        sudo=command(['/usr/bin/sudo','-n','-u','root','/usr/bin/true'],env=env,preexec_fn=demote)
        identities[principal]['root_command']='ALLOW' if sudo and sudo.returncode==0 else 'DENY'
    libc=ctypes.CDLL(None,use_errno=True)
    abi=libc.syscall(444,0,0,1) # x86_64 landlock_create_ruleset(VERSION)
    aa=text('/sys/module/apparmor/parameters/enabled')
    profiles=text('/sys/kernel/security/apparmor/profiles')
    capability=dict(kernel=os.uname().release,architecture=os.uname().machine,
        landlock_abi=abi if abi>=0 else None,apparmor_enabled=aa=='Y',
        apparmor_enforce_profiles=sum(line.endswith('(enforce)') for line in (profiles or '').splitlines()),
        apparmor_complain_profiles=sum(line.endswith('(complain)') for line in (profiles or '').splitlines()),
        yama_ptrace_scope=text('/proc/sys/kernel/yama/ptrace_scope'),
        protected_hardlinks=text('/proc/sys/fs/protected_hardlinks'),
        core_collector_configured=(text('/proc/sys/kernel/core_pattern') or '').startswith('|'),
        hibernation_resume_configured=text('/sys/power/resume') not in [None,'0:0'])
    swaps=[]
    for line in (text('/proc/swaps') or '').splitlines()[1:]:
        fields=line.split()
        if fields:
            swaps.append(dict(path=safe_path(fields[0]),kind=fields[1],metadata=metadata(Path(fields[0]))))
    capability['swaps']=swaps
    capability['zram_backing']={p.parent.name:(text(p) or 'UNKNOWN') for p in Path('/sys/block').glob('zram*/backing_dev')}
    git=command(['/usr/bin/git','-c','safe.directory='+str(HOME/'Projects/H07P'),'-C',str(HOME/'Projects/H07P'),'rev-parse','HEAD'])
    baseline=dict(timestamp=datetime.now(timezone.utc).isoformat(),repository='$OWNER_HOME/Projects/H07P',
                  source_head=git.stdout.decode().strip() if git and git.returncode==0 else 'UNKNOWN',
                  services=services,identities=identities,capabilities=capability,
                  credential_values_read=False,provider_model_calls=False,system_changes=False,
                  running_backend=('Rust' if services['huou07-playground.service'].get('executable')=='h07p-server' else 'Python' if 'python' in services['huou07-playground.service'].get('executable','') else 'UNKNOWN'))
    risks=[]
    for principal in WORKERS:
        native=principal.removesuffix('-worker')
        own=[r for r in matrix if r['principal']==principal and r['classification']==native]
        risks.append(dict(principal=principal,status='UNRESOLVED_SAME_UID',
                          decision='Keep native harness credential handling unchanged as explicitly requested by the owner',
                          observed_own_store_read=any(r['operations']['read']=='ALLOW' for r in own)))
        for row in matrix:
            if row['principal']==principal and row['classification'] in ['dsh','codex','opencode','owner'] and row['classification']!=native and row['operations']['read']=='ALLOW':
                risks.append(dict(principal=principal,status='DIRECTORY_METADATA_ONLY' if row['path']=='/etc/huou07-playground' else 'REVIEW',path=row['path'],reason='Public configuration directory permits enumeration; both known private OpenCode environment files deny every worker' if row['path']=='/etc/huou07-playground' else 'protected-zone read is allowed by effective DAC'))
    access=dict(evidence='effective os.access under actual service/account UID and group set; no file opened for credential bytes',
                debug='UNKNOWN: real credential-holder memory was intentionally not probed',rows=matrix)
    for name,value in [('access-matrix.json',access),('risk-matrix.json',dict(status='PARTIAL',risks=risks)),('compatibility-baseline.json',baseline)]:
        (args.output/name).write_text(json.dumps(value,indent=2)+'\n')
        os.chmod(args.output/name,0o600)
    summary='''# Credential Guard P0 audit\n\nMetadata-only audit of the actual Debian deployment. No authentication file,\nlog body, environment value, private key or process memory was read. Worker\npermission probes ran after permanent UID/GID/group drops, not as root.\n\nThe running dashboard remains the prior Python release; integrated Rust/product\nacceptance is separate. Actual identities, modes and kernel/service capabilities\nare in compatibility-baseline.json. Effective DAC checks are in access-matrix.json.\n\nEach native harness store is readable by its own executor UID. This is\nUNRESOLVED_SAME_UID by design under the owner's earlier explicit instruction to\nleave native authentication unchanged. It must not be reported as full isolation.\nCross-harness and owner boundaries are checked separately. Missing files and\nunexercised debug/mandatory controls remain UNKNOWN. Effective DAC is not proof\nthat every mandatory policy or protocol endpoint has been exercised.\n\nP0 permits implementation using the existing policy store/helper, while retaining\nall prior denials. It does not authorize a new credential-holder architecture,\nAppArmor rollout, provider changes, real model calls or log deletion.\n'''
    (args.output/'security-audit.md').write_text(summary)
    (args.output/'deployment-preflight.md').write_text('''# Deployment preflight\n\n- P0 metadata/access probes executed without changing services or credential files.\n- Preserve the current worker accounts, shared applications and native login.\n- Keep owner/private/native peer denials even when detection is disabled.\n- Reuse the existing policy store, transaction lock, owner API and rollback.\n- Add no global AppArmor restriction without compatibility evidence.\n- Watch only configured paths; do not scan original authentication stores.\n- Log handling must produce metadata-only reports, with explicit scope and review.\n- Do not edit live journals/databases or silently delete forensic records.\n- Installer must simulate dependency changes and preserve prior units/data.\n- Deployment still requires the integrated native/package gates to pass.\n''')
    print(json.dumps(dict(result='P0_RECORDED',principals=len(identities),access_rows=len(matrix),
                          risks=len(risks),credential_values_read=False,system_changes=False)))


if __name__=='__main__':main()
