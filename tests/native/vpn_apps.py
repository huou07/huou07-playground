#!/usr/bin/env python3
"""Actual dynamic relay checks in a disposable network namespace; no host VPN changes."""
import json
import base64
import http.client
import http.server
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time


def main():
    assert os.geteuid() == 0 and len(sys.argv) in (2, 3)
    binary = str(Path(sys.argv[1]).resolve())
    if len(sys.argv) == 2:
        subprocess.run(['unshare', '--net', '--fork', sys.executable, __file__, binary, '--inside'], check=True, timeout=45)
        return
    assert sys.argv[2] == '--inside'
    subprocess.run(['ip', 'link', 'set', 'lo', 'up'], check=True)
    subprocess.run(['ip', 'link', 'add', 'wg0', 'type', 'dummy'], check=True)
    subprocess.run(['ip', 'address', 'add', '10.8.0.1/32', 'dev', 'wg0'], check=True)
    subprocess.run(['ip', 'link', 'set', 'wg0', 'up'], check=True)
    with tempfile.TemporaryDirectory(prefix='h07p-relay-') as temporary:
        root = Path(temporary)
        (root/'control').mkdir(mode=0o700)
        control = str(root/'admin.sock')
        env = dict(PATH='/usr/sbin:/usr/bin:/sbin:/bin', LANG='C.UTF-8',
                   H07P_CONTROL_DIR=str(root/'control'), H07P_HELPER_SOCKET=control,
                   H07P_PRIVATE_SERVICES=str(root/'empty.json'),
                   OPENCODE_PUBLIC_USERNAME='fixture-web',OPENCODE_PUBLIC_PASSWORD='synthetic-old-web-password',
                   OPENCODE_BACKEND_USERNAME='fixture-native',OPENCODE_BACKEND_PASSWORD='synthetic-native-password')
        (root/'empty.json').write_text('{"services":[]}')
        disconnected=threading.Event()
        native_auth='Basic '+base64.b64encode(b'fixture-native:synthetic-native-password').decode()
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*arguments):pass
            def do_GET(self):
                assert self.headers.get('Authorization')==native_auth
                if self.path=='/hold':
                    self.send_response(200);self.send_header('Content-Length','1000000');self.end_headers();self.wfile.write(b'hello');self.wfile.flush()
                    self.connection.settimeout(4)
                    if self.connection.recv(1)==b'':disconnected.set()
                else:
                    self.send_response(200);self.send_header('Content-Length','4');self.end_headers();self.wfile.write(b'okay')
        native=http.server.ThreadingHTTPServer(('127.0.0.1',4097),Handler)
        serving=threading.Thread(target=native.serve_forever,daemon=True);serving.start()
        helper = subprocess.Popen([binary,'helper'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        backend = socket.socket()
        backend.bind(('127.0.0.1',0));backend.listen(5);backend.settimeout(5)
        backend_port = backend.getsockname()[1]
        free = socket.socket();free.bind(('10.8.0.1',0));port=free.getsockname()[1];free.close()
        try:
            for _ in range(100):
                if Path(control).exists():break
                time.sleep(.02)
            def rpc(op, **data):
                with socket.socket(socket.AF_UNIX) as channel:
                    channel.settimeout(10);channel.connect(control)
                    channel.sendall((json.dumps(dict(op=op,**data))+'\n').encode())
                    return json.loads(channel.makefile('rb').readline())
            def web_login(password,path='/'):
                client=http.client.HTTPConnection('127.0.0.1',4096,timeout=4)
                authorization='Basic '+base64.b64encode(('fixture-web:'+password).encode()).decode()
                client.request('GET',path,headers={'Authorization':authorization})
                return client,client.getresponse()
            for _ in range(100):
                try:
                    client,response=web_login('synthetic-old-web-password')
                    assert response.status==200 and response.read()==b'okay';client.close();break
                except ConnectionRefusedError:time.sleep(.02)
            else:raise AssertionError('existing public web bridge not ready')
            client,stream=web_login('synthetic-old-web-password','/hold')
            assert stream.status==200 and stream.read(5)==b'hello'
            assert not rpc('app_logins_change',source='anonymous-app',password='synthetic-new-web-password')['ok']
            changed=rpc('app_logins_change',source='opencode-public',password='synthetic-new-web-password')
            assert changed['ok'] and changed['data']['changed'],changed
            assert disconnected.wait(3),'rotation must close the active native backend stream'
            try:stream.read()
            except http.client.IncompleteRead:pass
            client.close()
            for password,status in [('synthetic-old-web-password',401),('synthetic-new-web-password',200)]:
                client,response=web_login(password);assert response.status==status;response.read();client.close()
            assert (root/'control/public-web-login.json').stat().st_mode&0o777==0o600
            helper.terminate();helper.wait(timeout=5)
            helper=subprocess.Popen([binary,'helper'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for _ in range(100):
                try:
                    client,response=web_login('synthetic-new-web-password')
                    assert response.status==200 and response.read()==b'okay';client.close();break
                except ConnectionRefusedError:time.sleep(.02)
            else:raise AssertionError('changed login must survive helper restart')
            # Absent original credentials must not create an authentication layer.
            empty=root/'noauth';empty.mkdir(mode=0o700)
            noauth=dict(env,H07P_CONTROL_DIR=str(empty),H07P_HELPER_SOCKET=str(root/'noauth.sock'),H07P_RELAYS='false')
            for key in tuple(noauth):
                if key.startswith('OPENCODE_'):del noauth[key]
            noauth_helper=subprocess.Popen([binary,'helper'],env=noauth,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    if (root/'noauth.sock').exists():break
                    time.sleep(.02)
                with socket.socket(socket.AF_UNIX) as channel:
                    channel.settimeout(3);channel.connect(str(root/'noauth.sock'))
                    channel.sendall((json.dumps(dict(op='app_logins_change',source='opencode-public',password='synthetic-new-web-password'))+'\n').encode())
                    assert not json.loads(channel.makefile('rb').readline())['ok']
                assert not (empty/'public-web-login.json').exists()
            finally:noauth_helper.terminate();noauth_helper.wait(timeout=3)
            config=dict(name='Anonymous fixture web app',target=f'127.0.0.1:{backend_port}',port=port)
            response=rpc('vpn_apps_add',config=config)
            assert response['ok'],response
            assert response['data']['relays'][0]['authentication']=='unchanged'
            saved=json.loads((root/'control/vpn-apps.json').read_text())
            assert saved[0]['target']==config['target']
            assert (root/'control/vpn-apps.json').stat().st_mode&0o777==0o600
            # Negative test must arrive from a different interface. Host-local
            # connections are deliberately allowed and do not model LAN ingress.
            peer=subprocess.Popen(['unshare','--net','sleep','30'])
            try:
                time.sleep(.1)
                subprocess.run(['ip','link','add','lan0','type','veth','peer','name','client0'],check=True)
                subprocess.run(['ip','link','set','client0','netns',str(peer.pid)],check=True)
                subprocess.run(['ip','addr','add','192.0.2.1/24','dev','lan0'],check=True)
                subprocess.run(['ip','link','set','lan0','up'],check=True)
                def remote(*arguments):
                    return subprocess.run(['nsenter','-t',str(peer.pid),'-n',*arguments],check=True,capture_output=True)
                remote('ip','addr','add','192.0.2.2/24','dev','client0')
                remote('ip','link','set','client0','up')
                remote('ip','route','add','10.8.0.1/32','via','192.0.2.1')
                result=remote(sys.executable,'-c','import socket,sys;s=socket.socket();s.settimeout(.3);sys.exit(1 if s.connect_ex(("10.8.0.1",int(sys.argv[1])))==0 else 0)',str(port))
                assert result.returncode==0
            finally:
                peer.terminate();peer.wait(timeout=3)
            client=socket.socket();client.settimeout(3)
            client.connect(('10.8.0.1',port))
            accepted=[]
            def serve():
                connection,_=backend.accept();connection.settimeout(3)
                assert connection.recv(4)==b'test';connection.sendall(b'okay')
                assert connection.recv(1)==b'';connection.close();accepted.append(True)
            thread=threading.Thread(target=serve);thread.start()
            client.sendall(b'test');assert client.recv(4)==b'okay'
            removed=rpc('vpn_apps_remove',port=port);assert removed['ok'],removed
            assert removed['data']['relays']==[]
            assert client.recv(1)==b'';client.close();thread.join(5);assert accepted
            assert json.loads((root/'control/vpn-apps.json').read_text())==[]
            assert not rpc('vpn_apps_add',config=dict(config,target='192.0.2.1:8080'))['ok']
            assert not rpc('vpn_apps_add',config=dict(config,target='127.0.0.1:4097'))['ok']
            print(json.dumps(dict(result='passed',checks=19,scope='actual UID0 typed helper, isolated network namespace, interface binding, byte preservation, active revocation, persistence',host_vpn_changed=False)))
        finally:
            native.shutdown();native.server_close();backend.close();helper.terminate()
            try:helper.wait(timeout=5)
            except subprocess.TimeoutExpired:helper.kill();helper.wait()

if __name__=='__main__':main()
