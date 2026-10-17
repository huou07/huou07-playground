#!/usr/bin/env python3
"""Real Debian UID/PAM/API tests using disposable data, never owner credentials.

Run explicitly as root: product.py /absolute/path/to/h07p-server --host-fixture
The fixture helper cannot stop production worker units or bind VPN relays.
"""
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


def run(*args, **kwargs):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, **kwargs)


def main():
    assert os.geteuid() == 0 and sys.argv[2:] == ["--host-fixture"]
    binary = str(Path(sys.argv[1]).resolve())
    root = Path(tempfile.mkdtemp(prefix="h07p-native-", dir="/var/tmp"))
    os.chmod(root, 0o755)
    owner = pwd.getpwnam("huou07")
    service = pwd.getpwnam("huou07-playground")
    account = "h07p-test-" + secrets.token_hex(3)
    unit = account + ".service"
    # The workspace lives inside the fixture root so the fixture never depends on
    # host default ACLs or on a traversable owner home: /var/tmp and the fixture
    # root are world-traversable and both directories get explicit modes below.
    workspace = root / "workspace"
    workspace.mkdir(mode=0o755)
    os.chown(workspace, owner.pw_uid, owner.pw_gid)
    # Drop any inherited extended/default entries so the pre-policy state is the
    # plain mode bits this fixture asserts, on any host.
    run("setfacl", "-b", "-k", "--", str(workspace))
    os.chmod(workspace, 0o755)
    processes = []
    created_account = False
    checks = 0

    def check(condition, description):
        nonlocal checks
        assert condition, description
        checks += 1

    def demote(user):
        def apply():
            os.setgroups([])
            os.setgid(user.pw_gid)
            os.setuid(user.pw_uid)
        return apply

    try:
        run("useradd", "--no-create-home", "--shell", "/bin/sh", account)
        created_account = True
        password = secrets.token_urlsafe(32)
        run("chpasswd", input=f"{account}:{password}\n".encode())
        for name in ("nas", "state"):
            p = root / name
            p.mkdir(mode=0o700)
            os.chown(p, service.pw_uid, service.pw_gid)
        (root / "control").mkdir(mode=0o700)
        (root / "bin").mkdir(mode=0o755)
        wrapper=root / "bin/setfacl"
        wrapper.write_text('#!/bin/sh\nif [ -e "'+str(root / 'fail-enforce')+'" ]; then exit 1; fi\nexec /usr/bin/setfacl "$@"\n')
        wrapper.chmod(0o755)
        env = dict(os.environ, H07P_OWNER=account, H07P_RELAYS="false",
                   H07P_WORKER_SETUP=str(root / "fixture-no-live-account-provisioning.py"),
                   PATH=str(root / "bin")+":/usr/sbin:/usr/bin:/sbin:/bin",
                   H07P_MANAGED_UNITS=unit, H07P_CONTROL_DIR=str(root / "control"),
                   H07P_NAS_DIR=str(root / "nas"), H07P_STATE_DIR=str(root / "state"),
                   APPS_FILE=str(root / "state/apps.json"),
                   H07P_HELPER_SOCKET=str(root / "run/admin.sock"))
        log = open(root / "runtime.log", "wb")
        processes.append(subprocess.Popen([binary, "helper"], env=dict(env, OPENCODE_PUBLIC_USERNAME="fixture-web-owner", OPENCODE_PUBLIC_PASSWORD="synthetic-existing-web-password"), stdout=log, stderr=log))
        for _ in range(100):
            if (root / "run/admin.sock").exists():
                break
            time.sleep(.05)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env.update(PORT=str(port), HOST="127.0.0.1", STATIC_DIR=str(Path.cwd() / "web/static"))
        processes.append(subprocess.Popen([binary], env=env, preexec_fn=demote(service),
                                          stdout=log, stderr=log))
        base = f"http://127.0.0.1:{port}"
        jar = http.cookiejar.CookieJar()
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        csrf = ""

        def request(path, data=None, method=None, authenticated=True, headers=None):
            h = dict(headers or {})
            if isinstance(data, dict):
                data = json.dumps(data).encode()
                h["Content-Type"] = "application/json"
            if authenticated and csrf:
                h["X-H07P-CSRF"] = csrf
            req = urllib.request.Request(base + path, data=data, method=method, headers=h)
            try:
                r = (client.open(req, timeout=15) if authenticated else urllib.request.urlopen(req, timeout=15))
            except urllib.error.HTTPError as e:
                r = e
            return r.code, {k.lower(): v for k, v in r.headers.items()}, r.read()

        def value(path, data=None, **kwargs):
            code, _, body = request(path, data, **kwargs)
            return code, json.loads(body)

        for _ in range(100):
            try:
                if request("/api/health")[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(.05)
        check(request("/api/metrics", authenticated=False)[0] == 401, "telemetry requires owner")
        check(request('/api/apps/discover',{},authenticated=False)[0]==401,'web discovery requires owner authentication')
        check(request('/api/setup/vpn/apps',authenticated=False)[0]==401,'VPN app metadata requires owner authentication')
        check(request('/api/setup/workers',authenticated=False)[0]==401,'worker setup requires owner authentication')
        check(request('/api/fs/search',dict(area='nas',path='/',query='fixture'),authenticated=False)[0]==401,'private search requires owner authentication')
        check(value("/api/owner/session")[1]["authenticated"] is False, "anonymous session")
        check(request("/api/owner/login", {"username": account, "password": "incorrect"})[0] == 401,
              "PAM rejects invalid password")
        code, login = value("/api/owner/login", {"username": account, "password": password})
        check(code == 200 and login["authenticated"], "real PAM owner sign in")
        csrf = login["csrf"]
        check(all(c.has_nonstandard_attr("HttpOnly") for c in jar), "HTTP-only cookie")
        check(value("/api/owner/session")[1]["authenticated"], "session persisted")
        code,vpn_apps=value('/api/setup/vpn/apps')
        check(code==200 and vpn_apps['relays']==[],'owner can inspect isolated VPN app configuration')
        check(request('/api/setup/vpn/apps/unknown',{})[0]==404,'VPN setup rejects arbitrary helper operations')
        code,workers=value('/api/setup/workers')
        check(code==200 and len(workers['workers'])==3,'owner can inspect supported harness/account metadata')
        check(request('/api/setup/workers',dict(action='create',workers=['root'],confirmed=True,expected_revision=0))[0]==400,'worker setup cannot select an arbitrary Unix identity')
        check(request('/api/setup/workers',dict(action='repair',workers=['dsh-worker'],confirmed=False,expected_revision=0))[0]==400,'worker changes require explicit review confirmation')
        code,job=value('/api/setup/workers',dict(action='create',workers=['dsh-worker'],confirmed=True,expected_revision=999999))
        check(code==200 and job['id'],'owner reviewed worker maintenance returns a bounded job handle')
        for _ in range(100):
            state=value('/api/setup/workers/job')[1]
            if state['state']!='running':break
            time.sleep(.02)
        check(state['state']=='failed' and 'REVISION_CONFLICT' in state['result']['error'] and value('/api/control/status')[1]['revision']==0,'stale worker setup fails before account/ACL changes')
        code,logins=value('/api/setup/logins')
        check(code==200 and logins['file']['version']=='absent' and logins['sources'][0]['available'],'selected login status exposes capabilities without credentials')
        export=dict(selected=['opencode-public'],entries=[],expected_version='absent',replace=False)
        code,saved_logins=value('/api/setup/logins',export)
        check(code==200 and saved_logins['saved'] and 'synthetic-existing-web-password' not in json.dumps(saved_logins),'selected login export does not return credential values')
        login_file=root/'nas/apps-login-password.md'
        check(login_file.stat().st_mode&0o777==0o600 and 'synthetic-existing-web-password' in login_file.read_text(),'export creates private 0600 NAS Markdown with selected fixture login')
        original=hashlib.sha256(login_file.read_bytes()).digest()
        check(request('/api/setup/logins',export)[0]==400 and hashlib.sha256(login_file.read_bytes()).digest()==original,'stale export cannot overwrite an existing private login file')
        check('synthetic-existing-web-password' not in (root/'runtime.log').read_text(),'selected login export never logs its values')
        code,logins=value('/api/setup/logins')
        check(request('/api/setup/logins',dict(export,expected_version=logins['file']['version']))[0]==400,'replacing a login file requires explicit confirmation')
        updated=dict(export,selected=[],entries=[dict(name='Fixture manual app',username='fixture',password='synthetic-manual-web-password')],expected_version=logins['file']['version'],replace=True)
        check(request('/api/setup/logins',updated)[0]==200 and 'synthetic-manual-web-password' in login_file.read_text() and 'synthetic-existing-web-password' not in login_file.read_text(),'confirmed replacement retains only chosen existing logins')
        check(request('/api/fs/mutate',dict(area='nas',action='delete',path='/apps-login-password.md',confirmed=True))[0]==200,'owner can delete the saved login file through ordinary NAS GUI API')
        check(value('/api/setup/logins')[1]['file']['version']=='absent' and list((root/'nas').iterdir())==[],'deleting the file leaves no hidden NAS credential copy')
        saved = csrf
        csrf = ""
        check(value("/api/owner/session")[1]["authenticated"] is False,
              "cookie exposed to another port cannot bootstrap owner proof")
        check(request("/api/metrics")[0] == 403, "cookie alone cannot read owner telemetry")
        check(request('/api/apps/discover',{})[0]==403,'web discovery rejects a cross-port cookie without owner proof')
        csrf = saved
        check(request("/api/fs/mutate", {"area": "nas", "action": "mkdir", "path": "/forged"},
                      headers={"Origin": "http://evil.invalid"})[0] == 403, "cross-origin mutation rejected")
        saved = csrf
        csrf = ""
        check(request("/api/fs/mutate", {"area": "nas", "action": "mkdir", "path": "/forged"})[0] == 403,
              "missing CSRF rejected")
        csrf = saved
        payload = secrets.token_bytes(2 * 1024 * 1024 + 17)
        query = urllib.parse.urlencode({"area": "nas", "path": "/fixture.bin"})
        check(request("/api/fs/upload?" + query, payload, method="PUT")[0] == 201, "stream upload")
        code,search=value('/api/fs/search',dict(area='nas',path='/',query='FIXTURE',recursive=True))
        check(code==200 and [e['path'] for e in search['entries']]==['/fixture.bin'] and search['content_searched'] is False,'authenticated owner search uses actual NAS actor')
        storage_fixture = workspace / 'storage-search-fixture.txt'
        storage_fixture.write_text('synthetic fixture; contents are not searched')
        os.chown(storage_fixture, owner.pw_uid, owner.pw_gid)
        code,search=value('/api/fs/search',dict(area='storage',path=str(workspace),query='storage-search-fixture',recursive=True))
        check(code==200 and [e['path'] for e in search['entries']]==[str(storage_fixture)] and search['content_searched'] is False,'authenticated Storage search finds a synthetic owner file')
        code, _, body = request("/api/fs/download?" + query)
        check(code == 200 and hashlib.sha256(body).digest() == hashlib.sha256(payload).digest(), "download hash")
        code, ticket = value("/api/fs/ticket", dict(area="nas", path="/fixture.bin", kind="download"))
        check(code == 200, "owner issues a scoped file link")
        code, _, body = request(ticket["url"], authenticated=False)
        check(code == 200 and body == payload, "scoped link streams without general owner credentials")
        check(request(ticket["url"].replace("fixture.bin", "other.bin"), authenticated=False)[0] == 401,
              "file link cannot change target")
        check(request(ticket["url"].replace("/download?", "/preview?"), authenticated=False)[0] == 401,
              "download link cannot change operation")
        check(request("/api/fs/upload?" + query, b"overwrite", method="PUT")[0] == 400, "no implicit overwrite")
        if os.environ.get("H07P_NATIVE_BROWSER") == "true":
            report = run("node", "tests/native/browser.mjs", input=json.dumps(dict(
                base=base, username=account, password=password, nas=str(root / "nas"), download=str(root / "browser-download.bin")
            )).encode()).stdout
            check(hashlib.sha256((root / "browser-download.bin").read_bytes()).digest() == hashlib.sha256(payload).digest(),
                  "real browser download hash")
            print(report.decode().strip())
        if os.environ.get("H07P_NATIVE_CLI_DIR"):
            # Optional operator-controlled Playwright CLI lane, synthetic login only.
            cli = Path(os.environ['H07P_NATIVE_CLI_DIR'])
            assert cli.is_dir() and cli.stat().st_uid == 0 and cli.stat().st_mode & 0o077 == 0
            export = workspace / 'log-exports'
            export.mkdir(mode=0o700)
            os.chown(export, owner.pw_uid, owner.pw_gid)
            log_export = export / 'closed.log'
            log_export.write_text('normal startup\nAuthorization: Bearer synthetic-cli-secret\nnormal end\n')
            os.chown(log_export, owner.pw_uid, owner.pw_gid)
            log_export.chmod(0o600)
            fixture_file = cli / 'fixture.json'
            fixture_file.write_text(json.dumps(dict(base=base, username=account, password=password, exports=str(export), path=str(log_export))))
            fixture_file.chmod(0o600)
            print(json.dumps({'playwright_cli': 'ready', 'port': port}), flush=True)
            for _ in range(1800):
                if (cli / 'continue').exists():
                    break
                time.sleep(1)
            else:
                raise AssertionError('Playwright CLI lane timed out')
        code, headers, body = request("/api/fs/download?" + query, headers={"Range": "bytes=4-15"})
        check(code == 206 and body == payload[4:16], "single byte range")
        check(headers.get("content-range") == f"bytes 4-15/{len(payload)}", "range metadata")
        check(request("/api/fs/download?" + query, headers={"Range": "bytes=0-1,4-5"})[0] == 416, "multiple ranges rejected")
        for action, path, destination in [("copy", "/fixture.bin", "/copy.bin"),
                                           ("rename", "/copy.bin", "/renamed.bin")]:
            check(request("/api/fs/mutate", dict(area="nas", action=action, path=path,
                                                destination=destination))[0] == 200, action)
        check(request("/api/fs/mutate", dict(area="nas", action="delete", path="/renamed.bin"))[0] == 400,
              "delete requires confirmation")
        check(request("/api/fs/mutate", dict(area="nas", action="delete", path="/renamed.bin", confirmed=True))[0] == 200,
              "confirmed delete")
        check(request("/api/fs/list?area=nas&path=/../")[0] == 400, "path traversal rejected")
        os.symlink("/etc/passwd", root / "nas/alias")
        check(request("/api/fs/download?area=nas&path=/alias")[0] == 400, "symlink download rejected")
        for name in ("dsh-worker", "codex-worker", "opencode-worker"):
            denied = subprocess.run(["runuser", "-u", name, "--", "cat", str(root / "nas/fixture.bin")],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            check(denied.returncode != 0, name + " cannot read private NAS")
        target = workspace / "ordinary.txt"
        target.write_text("synthetic ordinary content")
        os.chown(target, owner.pw_uid, owner.pw_gid)
        run("setfacl", "-b", "--", str(target))
        os.chmod(target, 0o644)
        # Baseline: the plain mode must already allow every worker to read, so a
        # later "denied" result cannot pass for the wrong reason (a host ACL or a
        # non-traversable ancestor would deny both the block and the rollback).
        for name in ("dsh-worker", "codex-worker", "opencode-worker"):
            baseline = subprocess.run(["runuser", "-u", name, "--", "cat", str(target)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            check(baseline.returncode == 0 and baseline.stdout == b"synthetic ordinary content",
                  name + " baseline read access missing: "
                  + baseline.stderr.decode(errors="replace").strip() + " | "
                  + run("getfacl", "-p", "--", str(target)).stdout.decode())
        initial_revision = value("/api/control/status")[1]["revision"]
        draft = dict(expected_revision=initial_revision, preset="none", workspace=str(workspace), rules=[dict(
            worker="*", target=str(target), action="block", recursive=False,
            operations=["list", "read", "write", "create", "delete", "execute"])])
        check(request("/api/control/dry-run", draft)[0] == 200, "policy dry run")
        check(target.read_text() == "synthetic ordinary content", "dry run preserves data")
        run("systemd-run", "--quiet", "--unit=" + unit, "--property=User=dsh-worker",
            "--property=NoNewPrivileges=yes", "--property=KillMode=control-group",
            "--property=RuntimeMaxSec=90", "/bin/sh", "-c", "sleep 80 & wait")
        cgroup = run("systemctl", "show", "--value", "-p", "ControlGroup", unit).stdout.decode().strip()
        descendants = []
        for _ in range(40):
            descendants = (Path("/sys/fs/cgroup" + cgroup) / "cgroup.procs").read_text().split()
            if len(descendants) >= 2:
                break
            time.sleep(.05)
        check(len(descendants) >= 2, "real managed fixture has a descendant")
        code, policy = value("/api/control/apply", draft)
        check(code == 200 and policy["enforced_revision"] == initial_revision + 1, "real ACL policy applied")
        for _ in range(40):
            if not any(Path("/proc/" + pid).exists() for pid in descendants):
                break
            time.sleep(.05)
        check(not any(Path("/proc/" + pid).exists() for pid in descendants),
              "policy activation terminates complete managed process tree")
        for name in ("dsh-worker", "codex-worker", "opencode-worker"):
            denied = subprocess.run(["runuser", "-u", name, "--", "cat", str(target)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            check(denied.returncode != 0, name + " denied by applied ACL")
        check(request("/api/control/apply", draft)[0] == 409, "stale revision rejected")
        check(request("/api/control/rollback", dict(expected_revision=initial_revision + 1, revision=initial_revision))[0] == 200, "rollback applied")
        for name in ("dsh-worker", "codex-worker", "opencode-worker"):
            restored = subprocess.run(["runuser", "-u", name, "--", "cat", str(target)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            acl = run("getfacl", "-p", "--", str(target)).stdout.decode()
            check(restored.returncode == 0 and restored.stdout == b"synthetic ordinary content",
                  name + " positive access not restored: "
                  + restored.stderr.decode(errors="replace").strip() + " | " + acl)
            check("user:" + name not in acl, name + " named ACL entry still present after rollback")
        def broker(worker, message):
            code = "import socket,json,sys;s=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1]);s.sendall((sys.argv[2]+'\\n').encode());print(s.makefile().readline())"
            return json.loads(run("runuser", "-u", worker, "--", "python3", "-c", code,
                                  str(root / "run/broker.sock"), json.dumps(message)).stdout)

        pending = broker("dsh-worker", dict(op="request", operation="read", path=str(target)))
        check(pending["ok"], "real worker requests scoped approval")
        approval = pending["data"]["id"]
        check(not broker("dsh-worker", dict(op="redeem", id=approval))["ok"], "pending approval denies")
        check(request("/api/control/approve", dict(id=approval, allow=True))[0] == 200, "owner approves scoped read")
        check(not broker("codex-worker", dict(op="redeem", id=approval))["ok"], "approval cannot cross worker")
        redeemed = broker("dsh-worker", dict(op="redeem", id=approval))
        check(redeemed["ok"] and redeemed["data"]["data"] == "synthetic ordinary content", "approved read succeeds")
        check(not broker("dsh-worker", dict(op="redeem", id=approval))["ok"], "single-use approval cannot replay")
        pending = broker("dsh-worker", dict(op="request", operation="read", path=str(target)))
        approval = pending["data"]["id"]
        check(request("/api/control/approve", dict(id=approval, allow=True))[0] == 200, "second approval")
        replacement = workspace / "replacement.txt"
        replacement.write_text("replacement must never be disclosed")
        os.chown(replacement, owner.pw_uid, owner.pw_gid)
        replacement.replace(target)
        check(not broker("dsh-worker", dict(op="redeem", id=approval))["ok"], "inode replacement invalidates approval")
        secret_fixture = workspace / "ordinary.conf"
        secret_fixture.write_text("github_token = ghp_" + secrets.token_hex(18))
        os.chown(secret_fixture, owner.pw_uid, owner.pw_gid)
        code, detected = value("/api/control/scan", dict(scope=str(workspace), mode="block", content=False))
        check(code == 200 and not detected["content_scanned"], "content scan defaults off")
        if os.environ.get("H07P_SCANNER"):
            code, detected = value("/api/control/scan", dict(scope=str(workspace), mode="block", content=True))
            check(code == 200 and any(f["reason"] == "maintained_scanner_match" for f in detected["findings"]),
                  "opt-in maintained scanner finds synthetic content secret")
            check("ghp_" not in json.dumps(detected), "scan response contains no matching bytes")
        current_revision = value("/api/control/status")[1]["revision"]
        expiring = dict(draft, expected_revision=current_revision,
                        rules=[dict(draft["rules"][0], expires_at=int(time.time())+5)])
        check(request("/api/control/apply", expiring)[0] == 200, "expiring Block applies")
        for _ in range(90):
            expired = value("/api/control/status")[1]
            if expired["revision"] == current_revision+2:
                break
            time.sleep(.1)
        check(expired["revision"] == current_revision+2 and not expired["rules"],
              "expiry creates and enforces a new policy revision")
        check(run("runuser", "-u", "dsh-worker", "--", "cat", str(target)).stdout == b"replacement must never be disclosed",
              "expiry restores positive ordinary access")
        root_owned = workspace / "root-owned.txt"
        root_owned.write_text("synthetic root fixture")
        privileged = dict(draft, expected_revision=expired["revision"], rules=[dict(
            worker="*",target=str(root_owned),action="allow",recursive=False,operations=["read"])])
        check(request("/api/control/dry-run", privileged)[0] == 400,
              "policy cannot grant worker rights to root-owned files")
        group = next(g for g in os.getgrouplist("huou07", owner.pw_gid) if g != owner.pw_gid)
        group_file = workspace / "owner-group-only.txt"
        group_file.write_text("synthetic supplementary group access")
        os.chown(group_file, 0, group)
        run("setfacl", "-b", str(group_file))
        os.chmod(group_file, 0o640)
        code, _, body = request("/api/fs/download?" + urllib.parse.urlencode(dict(area="storage",path=str(group_file))))
        check(code == 200 and body == b"synthetic supplementary group access",
              "Storage preserves actual owner supplementary-group rights")
        (root / "fail-enforce").touch()
        failed_draft=dict(draft,expected_revision=expired["revision"])
        check(request("/api/control/apply",failed_draft)[0]==400,"failed OS policy activation reports failure")
        pending=value("/api/control/status")[1]
        check(pending["enforced_revision"] is None,"failed activation and rollback never claim Enforced")
        (root / "fail-enforce").unlink()
        repair=dict(draft,expected_revision=pending["revision"],rules=[])
        code,repaired=value("/api/control/apply",repair)
        check(code==200 and repaired["revision"]==repaired["enforced_revision"],"owner can repair a pending revision after the OS fault is removed")
        check(request("/api/owner/logout", {})[0] == 200, "logout")
        check(request("/api/fs/list")[0] == 401, "logged-out session revoked")
        check(request(ticket["url"], authenticated=False)[0] == 401, "logout revokes outstanding file links")
        print(json.dumps({"checks": checks, "result": "passed", "runtime": "Debian real PAM/UID/ACL/HTTP",
                          "production_services_changed": False}))
    finally:
        subprocess.run(["systemctl", "stop", unit], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["systemctl", "reset-failed", unit], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for p in reversed(processes):
            p.terminate()
        for p in reversed(processes):
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        if created_account:
            run("userdel", account)
        shutil.rmtree(workspace)
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
