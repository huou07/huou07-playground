#!/usr/bin/env python3
"""Real OpenCode tool turn, mock provider, fresh HOME, harmless private fixture."""
import http.server
import argparse
import base64
import json
import os
import shlex
import subprocess
import tempfile
import threading
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protected-fixture", type=Path)
    parser.add_argument("--gateway-url")
    parser.add_argument("--gateway-key", default="sk-worker-staging-only-000000000000000000000000000")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="opencode-tool-stage-") as directory:
        home = Path(directory)
        fixture = home / "private-fixture"
        fixture.write_text("disposable fixture, no live credentials\n")
        fixture.chmod(0o600)
        marker = home / "tool-evidence.json"
        script = f"""import json,os
from pathlib import Path
fd=os.open({str(fixture)!r},os.O_RDONLY)
os.close(fd)
evidence={{'uid':os.geteuid(),'private_fixture_openable':True}}
project=Path('authorized-project')
project.mkdir()
(project/'answer.py').write_text('answer = 42\\n')
scope={{}}
exec((project/'answer.py').read_text(),scope)
assert scope['answer']==42
evidence['project_edit_and_test_succeeded']=True
"""
        if args.protected_fixture:
            script += f"""try:
    fd=os.open({str(args.protected_fixture)!r},os.O_RDONLY)
except PermissionError:
    evidence['protected_fixture_denied']=True
else:
    os.close(fd)
    evidence['protected_fixture_denied']=False
"""
        script += f"Path({str(marker)!r}).write_text(json.dumps(evidence))\n"
        command = "/usr/bin/python3 -c " + shlex.quote(script)
        state = {"tool_requested": False, "provider_fixture_auth_seen": False}

        class Provider(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                state["provider_fixture_auth_seen"] |= self.headers.get("Authorization") == "Bearer staging-only"
                tools = body.get("tools", [])
                has_bash = any(t.get("function", {}).get("name") == "bash" for t in tools)
                if has_bash and not state["tool_requested"]:
                    state["tool_requested"] = True
                    delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": "call_stage", "type": "function",
                             "function": {"name": "bash", "arguments": json.dumps({"command": command, "description": "Check disposable staging fixture"})}}]}
                    finish = "tool_calls"
                else:
                    delta, finish = {"role": "assistant", "content": "Staging complete."}, "stop"
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for item in [{"id": "mock", "object": "chat.completion.chunk", "model": "fixture",
                              "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                             {"id": "mock", "object": "chat.completion.chunk", "model": "fixture",
                              "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}]:
                    self.wfile.write(("data: " + json.dumps(item) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = {"provider": {"mock": {"npm": "@ai-sdk/openai-compatible", "name": "Disposable mock",
                  "options": {"baseURL": args.gateway_url or f"http://127.0.0.1:{server.server_port}/v1", "apiKey": args.gateway_key if args.gateway_url else "staging-only"},
                  "models": {"fixture": {"name": "Fixture", "limit": {"context": 16000, "output": 1000}}}}},
                  "model": "mock/fixture", "permission": {"bash": "allow"}}
        (home / "opencode.json").write_text(json.dumps(config))
        env = {"HOME": str(home), "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
               "XDG_CONFIG_HOME": str(home / "config"), "XDG_DATA_HOME": str(home / "data"),
               "XDG_STATE_HOME": str(home / "state"), "XDG_CACHE_HOME": str(home / "cache"),
               "OPENCODE_DISABLE_AUTOUPDATE": "true", "OPENCODE_DISABLE_MODELS_FETCH": "true"}
        try:
            result = subprocess.run(["/opt/agent-workbench/bin/opencode.real", "run", "--format", "json",
                                     "--model", "mock/fixture", "fixture-command-base64: " + base64.b64encode(command.encode()).decode() if args.gateway_url else "Run the disposable fixture check with bash."],
                                    cwd=home, env=env, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, timeout=50)
        finally:
            server.shutdown()
            server.server_close()
        if not marker.is_file():
            # Never forward engine stdout, stderr, request bodies, or headers.
            print(json.dumps({**state, "exit_code": result.returncode, "tool_evidence_created": False}))
            if args.gateway_url:
                diagnostic = (result.stderr[-800:] + result.stdout[-1600:]).replace(args.gateway_key, "<fixture-capability>")
                print(json.dumps({"fixture_engine_diagnostic": diagnostic}))
            raise SystemExit(1)
        evidence = json.loads(marker.read_text())
        print(json.dumps({**state, "exit_code": result.returncode, "tool_evidence": evidence,
                          "controller_uid": os.geteuid(), "tool_runs_as_controller_uid": evidence["uid"] == os.geteuid(),
                          "live_credentials_copied": False}, indent=2))
        assert result.returncode == 0 and (args.gateway_url or state["tool_requested"])
        if args.protected_fixture:
            assert evidence["protected_fixture_denied"], "Worker could open the protected fixture"


if __name__ == "__main__":
    main()
