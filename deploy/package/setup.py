#!/usr/bin/env python3
"""Beginner-facing H07P maintenance. APT plans first, no package removals.

Diagnostics never read authentication stores, environments, journal bodies or
provider settings. Uninstall retains application/NAS data and native accounts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

PACKAGE='huou07-playground'
CACHE=Path('/var/cache/huou07-playground')
UNITS=['h07p-helper.service','huou07-playground.service','h07p-dsh.service','h07p-opencode.service']
DEPENDENCIES=['python3','libc6','libgcc-s1','libpam0g','adduser','passwd','iproute2','systemd','acl','gitleaks']


class SetupError(Exception):pass


def redact(value):
    lines=[]
    private=False
    for line in value.splitlines():
        line=re.sub(r'(?i)(https?://)[^/\s@]+@',r'\1[redacted]@',line)
        begin=bool(re.search(r'(?i)-----BEGIN .*PRIVATE KEY',line))
        end=bool(re.search(r'(?i)-----END .*PRIVATE KEY',line))
        if private or begin or len(line)>8192 or re.search(r'(?i)(authorization\s*[:=]|(?:api[_-]?key|password|refresh[_-]?token|access[_-]?token|client[_-]?secret)\s*["\x27]?\s*[:=]|\bBearer\s+\S+|-----BEGIN .*PRIVATE KEY)',line):
            line='[H07P: nội dung nhạy cảm đã được che]'
        if begin:private=True
        if end:private=False
        lines.append(re.sub(r'[\x00-\x08\x0b-\x1f\x7f]','',line))
    return '\n'.join(lines)


def command(arguments, timeout=180):
    env=dict(os.environ,LC_ALL='C',LANG='C',DEBIAN_FRONTEND='noninteractive')
    # Never interpolate package names, paths or diagnostics into a shell.
    try:
        result=subprocess.run(arguments,env=env,text=True,capture_output=True,timeout=timeout,check=False)
    except FileNotFoundError:
        raise SetupError('Thiếu công cụ hệ thống: '+Path(arguments[0]).name) from None
    except subprocess.TimeoutExpired:
        raise SetupError('Thao tác quá thời gian. Kiểm tra mạng hoặc tiến trình quản lý gói rồi thử lại.') from None
    return result.returncode,redact(result.stdout),redact(result.stderr)


def installed_version():
    code,out,_=command(['dpkg-query','-W','-f=${Status}\n${Version}',PACKAGE])
    fields=out.splitlines()
    return fields[1] if code==0 and len(fields)>1 and fields[0]=='install ok installed' else None


def file_sha256(source):
    digest=hashlib.sha256()
    for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def metadata(path):
    path=Path(path).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix!='.deb':raise SetupError('Chọn file cài đặt .deb của H07P.')
    code,out,error=command(['dpkg-deb','--field',str(path),'Package','Version','Architecture'])
    if code:raise SetupError('File cài đặt không hợp lệ. '+error)
    fields=dict(line.split(': ',1) for line in out.splitlines() if ': ' in line)
    if fields.get('Package')!=PACKAGE or fields.get('Architecture')!='amd64':raise SetupError('File này không phải H07P cho Debian amd64.')
    if not re.fullmatch(r'[0-9][A-Za-z0-9.+:~_-]*',fields.get('Version','')):raise SetupError('Phiên bản gói không hợp lệ.')
    with path.open('rb') as source: digest=file_sha256(source)
    checksum=Path(str(path)+'.sha256')
    if checksum.exists():
        expected=checksum.read_text().split()[0]
        if not re.fullmatch('[0-9a-fA-F]{64}',expected) or expected.lower()!=digest:raise SetupError('Checksum không khớp. Không cài file này; tải lại bản phát hành.')
    fields.update(path=str(path),sha256=digest,checksum_present=checksum.exists())
    return fields


def platform():
    if sys.platform!='linux':raise SetupError('Bản này dành cho Dell Debian Linux amd64.')
    code,architecture,_=command(['dpkg','--print-architecture'])
    if code or architecture.strip()!='amd64':raise SetupError('Bản cài này yêu cầu Debian amd64; không tự đổi kiến trúc hệ thống.')


def diagnose():
    platform()
    dependencies={}
    for package in DEPENDENCIES:
        code,out,_=command(['dpkg-query','-W','-f=${Status}\n${Version}',package])
        fields=out.splitlines()
        dependencies[package]=fields[1] if code==0 and len(fields)>1 and fields[0]=='install ok installed' else 'MISSING'
    services={unit:command(['systemctl','is-active',unit])[1].strip() or 'unknown' for unit in UNITS}
    code,audit,_=command(['dpkg','--audit'])
    current=Path('/opt/huou07-playground/current')
    active=current.resolve().name if current.exists() else None
    return dict(installed_version=installed_version(),active_release=active,dependencies=dependencies,
                services=services,free_bytes=shutil.disk_usage('/var').free,
                package_database_ok=code==0 and not audit.strip(),package_database_diagnostic=audit,
                data_retained=['owner state','private NAS','native harness accounts/authentication'],
                credential_values_read=False)


def latest_cached():
    if not CACHE.is_dir():raise SetupError('Chưa có file cài trong bộ nhớ đệm. Chọn file .deb bằng lệnh install hoặc update.')
    files=sorted(CACHE.glob(PACKAGE+'_*.deb'),key=lambda p:p.stat().st_mtime,reverse=True)
    if not files:raise SetupError('Không tìm thấy bộ cài đã lưu. Hãy chọn file .deb của bản phát hành.')
    return metadata(files[0])


def plan(info,repair=False):
    arguments=['apt-get','--simulate','--no-remove','--no-install-recommends']
    if repair:arguments.append('--reinstall')
    arguments.extend(['install',info['path']])
    code,out,error=command(arguments)
    if code:
        detail=(out+'\n'+error).lower()
        hint=('Trình quản lý gói khác đang chạy; chờ hoàn tất rồi thử lại. Không xóa lock hoặc kill dpkg.' if 'lock' in detail else
              'Kiểm tra kết nối Internet/DNS rồi thử lại.' if any(word in detail for word in ['resolving','network is unreachable','failed to fetch']) else
              'Chọn “Cập nhật danh sách gói” trong menu rồi thử lại. Nếu yêu cầu libc/systemd mới hơn, cần đúng bộ cài cho phiên bản Debian hiện tại.')
        raise SetupError('Chưa cài được vì dependency, kho gói hoặc khóa quản lý gói.\n'+out+'\n'+error+
                         '\n'+hint+'\nKhông gỡ gói khác hay nâng cấp hệ điều hành tự động. Dùng doctor để xem chẩn đoán.')
    if any(line.startswith('Remv ') for line in out.splitlines()):raise SetupError('APT đề xuất gỡ gói khác. H07P từ chối kế hoạch này để giữ hệ thống đang chạy.')
    if shutil.disk_usage('/var').free<512*1024*1024:raise SetupError('Cần ít nhất 512 MiB trống để lưu bản cũ và rollback. Chưa thay đổi hệ thống.')
    return dict(package=PACKAGE,version=info['Version'],sha256=info['sha256'],checksum_present=info['checksum_present'],
                actions=[line for line in out.splitlines() if line.startswith(('Inst ','Conf '))],
                apt_plan=out,removes_other_packages=False,repair=repair)


def confirm(question,yes):
    if yes:return
    if not sys.stdin.isatty():raise SetupError('Cần xác nhận tương tác; dùng --yes sau khi đã xem --dry-run.')
    if input(question+' [y/N]: ').strip().lower() not in ('y','yes','c','co','có'):raise SetupError('Đã hủy. Chưa thay đổi hệ thống.')


def require_root():
    if os.geteuid()!=0:raise SetupError('Chạy lại bằng sudo h07p-setup để thực hiện; doctor và --dry-run không cần quyền root.')


def cache(info):
    CACHE.mkdir(mode=0o755,parents=True,exist_ok=True)
    stat=CACHE.lstat()
    if CACHE.is_symlink() or stat.st_uid!=0 or stat.st_mode & 0o022:raise SetupError('Thư mục cache không an toàn; không ghi đè hoặc dùng thư mục do tài khoản khác kiểm soát.')
    destination=CACHE/(PACKAGE+'_'+info['Version']+'_amd64.deb')
    fd,name=tempfile.mkstemp(prefix='.incoming-',dir=CACHE)
    try:
        with os.fdopen(fd,'wb') as output,open(info['path'],'rb') as source:
            shutil.copyfileobj(source,output,1024*1024);output.flush();os.fsync(output.fileno())
        with open(name,'rb') as copied:
            if file_sha256(copied)!=info['sha256']:raise SetupError('Bộ cài thay đổi trong lúc sao chép; đã dừng an toàn.')
        os.chmod(name,0o644);os.replace(name,destination)
        Path(str(destination)+'.sha256').write_text(info['sha256']+'  '+destination.name+'\n')
        return destination
    finally:
        Path(name).unlink(missing_ok=True)


def install(info,args):
    proposal=plan(info,args.action=='repair')
    print(json.dumps(proposal,ensure_ascii=False,indent=2) if args.json else proposal['apt_plan'])
    if args.dry_run:return
    require_root()
    if not info['checksum_present']:print('Lưu ý: không có file checksum kèm theo. Chỉ tiếp tục nếu đây là bộ cài từ nguồn bạn tin cậy.')
    confirm('Cài phiên bản '+info['Version']+' theo đúng kế hoạch trên? Dữ liệu và credentials native được giữ lại.',args.yes)
    candidate=cache(info)
    arguments=['apt-get','--yes','--no-remove','--no-install-recommends','-o','Dpkg::Options::=--force-confold']
    if args.action=='repair':arguments.append('--reinstall')
    arguments.extend(['install',str(candidate)])
    code,out,error=command(arguments,timeout=900)
    if out:print(out)
    if code:raise SetupError(error+'\nCài đặt chưa hoàn tất. Không xóa dữ liệu hoặc file credentials. Chạy doctor; dùng repair với bộ cài đã lưu sau khi xử lý lỗi dependency/mạng.')
    health()
    print('H07P đã sẵn sàng: http://10.8.0.1:8765/ qua WireGuard. Đăng nhập bằng tài khoản Linux huou07.')


def health():
    import urllib.request
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:8765/api/health',timeout=5) as response:
            if response.status==200 and json.load(response).get('ok') is True:return
    except (OSError,ValueError):pass
    raise SetupError('Dashboard chưa phản hồi. Gói cài có rollback tự động khi khởi động lỗi; dùng doctor để xem trạng thái và repair/rollback để khôi phục.')


def menu():
    if not sys.stdin.isatty():raise SetupError('Dùng: h07p-setup doctor | install FILE.deb | update FILE.deb | repair | rollback | uninstall')
    print('\nH07P — cài đặt và bảo trì\n1. Kiểm tra / chẩn đoán\n2. Cài đặt hoặc cập nhật từ file .deb\n3. Repair — sửa chương trình, giữ dữ liệu\n4. Rollback — trở về bản trước\n5. Uninstall — gỡ H07P, giữ dữ liệu\n6. Cập nhật danh sách dependency (không nâng cấp gói)\n0. Thoát')
    choice=input('Chọn số: ').strip()
    if choice=='0':return []
    if choice=='1':return ['doctor']
    if choice=='2':return ['install',input('Kéo/thả hoặc nhập đường dẫn file .deb: ').strip().strip("\x27\"")]
    if choice in ['3','4','5']:return [{'3':'repair','4':'rollback','5':'uninstall'}[choice]]
    if choice=='6':return ['refresh-index']
    raise SetupError('Lựa chọn chưa đúng; chạy lại để chọn một số trong menu.')


def main(argv=None):
    arguments=sys.argv[1:] if argv is None else argv
    if not arguments:
        while True:
            selection=menu()
            if not selection:return 0
            try:main(selection)
            except (SetupError,OSError,ValueError) as error:print('H07P: '+redact(str(error)),file=sys.stderr)
            input('\nNhấn Enter để quay lại menu...')
    parser=argparse.ArgumentParser(description='Cài / update / repair / rollback / uninstall H07P, giữ nguyên dữ liệu và đăng nhập native.')
    parser.add_argument('action',choices=['doctor','install','update','repair','rollback','uninstall','refresh-index'])
    parser.add_argument('package',nargs='?',type=Path)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--yes',action='store_true')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args(arguments)
    platform()
    if args.action=='doctor':
        report=diagnose()
        if args.json:print(json.dumps(report,ensure_ascii=False,indent=2))
        else:
            print('H07P — chẩn đoán an toàn\nGói đã cài: '+str(report['installed_version'] or 'chưa cài')+'\nRelease đang dùng: '+str(report['active_release'] or 'chưa có'))
            print('Dung lượng trống: '+str(round(report['free_bytes']/1073741824,1))+' GiB')
            missing=[name for name,version in report['dependencies'].items() if version=='MISSING']
            print('Dependency: '+(', '.join(missing)+' còn thiếu; bộ cài sẽ nhờ APT giải quyết.' if missing else 'đủ các gói cần thiết'))
            for name,state in report['services'].items():print('  '+name+': '+state)
            if not report['package_database_ok']:print('Quản lý gói có thao tác dở dang:\n'+report['package_database_diagnostic'])
            print('Không đọc credentials hoặc nội dung log. Nếu chương trình lỗi, chọn Repair; nếu bản mới không phù hợp, chọn Rollback. Dữ liệu được giữ lại.')
        return 0
    if args.action in ['install','update','repair']:
        info=metadata(args.package) if args.package else latest_cached()
        install(info,args);return 0
    if args.action=='refresh-index':
        print('Chỉ cập nhật danh sách gói từ kho APT hiện có; không đổi kho, không nâng cấp hoặc gỡ gói.')
        if args.dry_run:return 0
        require_root();confirm('Tải lại danh sách dependency?',args.yes)
        code,out,error=command(['apt-get','update'],timeout=300)
        print(out)
        if code:raise SetupError(error+'\nKiểm tra mạng/DNS hoặc kho gói. Chưa thay đổi gói đã cài.')
        print('Danh sách đã cập nhật. Chọn lại Cài đặt/Update hoặc Repair.');return 0
    if args.action=='rollback':
        print('Khôi phục release/unit/config trước đó; giữ NAS, tài khoản và credentials native.')
        if args.dry_run:return 0
        require_root();confirm('Tiếp tục rollback?',args.yes)
        code,out,error=command(['/usr/bin/python3','/usr/lib/huou07-playground/lifecycle.py','rollback'])
        if code:raise SetupError(error+'\nKhông ghi đè conflict bằng tay. Dùng doctor và giữ lại snapshot để kiểm tra.')
        print(out);health();return 0
    print('Gỡ H07P và phục hồi entry point native trước đó. NAS, state, snapshot, tài khoản và credentials được giữ lại.\nCác hạn chế tùy chỉnh của H07P cần được xem xét trước khi bỏ launcher; không coi scanner tắt là quyền được mở lại.')
    if args.dry_run:return 0
    require_root();confirm('Gỡ H07P và giữ dữ liệu?',args.yes)
    code,out,error=command(['apt-get','--simulate','--no-auto-remove','remove',PACKAGE])
    removed=[line.split()[1] for line in out.splitlines() if line.startswith('Remv ')]
    if code or any(p.split(':')[0]!=PACKAGE for p in removed):raise SetupError('Kế hoạch gỡ có ảnh hưởng gói khác hoặc dependency đang lỗi. Chưa gỡ.\n'+out+'\n'+error)
    code,out,error=command(['apt-get','--yes','--no-auto-remove','remove',PACKAGE],timeout=300)
    if code:raise SetupError(error)
    print(out+'\nĐã gỡ chương trình; dữ liệu và bản sao rollback vẫn được giữ.');return 0


if __name__=='__main__':
    try:sys.exit(main())
    except (SetupError,OSError,ValueError) as error:
        print('H07P: '+redact(str(error)),file=sys.stderr);sys.exit(1)
    except KeyboardInterrupt:
        print('\nĐã ngắt. Không chạy thêm thao tác; dùng doctor để kiểm tra trạng thái.',file=sys.stderr);sys.exit(130)
