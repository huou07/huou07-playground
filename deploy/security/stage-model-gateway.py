#!/usr/bin/env python3
"""Disposable pinned LiteLLM/Postgres with a fake provider. No production secrets."""
import argparse
import base64
import http.client
import http.server
import json
import os
import re
import secrets
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

PORT = 14009
DB_PORT = 14329
MASTER = "sk-owner-staging-only-0000000000000000000000000000"
WORKER = "sk-worker-staging-only-000000000000000000000000000"
UPSTREAM = "fixture-upstream-never-a-live-key"


def api(path, body=None, key=WORKER):
    connection = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    try:
        connection.request("POST" if body is not None else "GET", path,
                           json.dumps(body) if body is not None else None,
                           {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


class Provider(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.calls.append({"path": self.path, "expected_auth": self.headers.get("Authorization") == "Bearer " + UPSTREAM})
        if "fixture-delay" in json.dumps(body):
            self.server.slow_started.set()
            time.sleep(2)
        if self.path.endswith("/responses"):
            message = {"id": "msg_fixture", "type": "message", "role": "assistant", "status": "completed",
                       "content": [{"type": "output_text", "text": "Staging inference complete.", "annotations": []}]}
            response = {"id": "resp_fixture", "object": "response", "created_at": int(time.time()),
                        "status": "completed", "model": "mock-fixture", "output": [message],
                        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                                  "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}}
            events = [
                ("response.created", {"response": {**response, "status": "in_progress", "output": []}}),
                ("response.output_item.added", {"output_index": 0, "item": {**message, "status": "in_progress", "content": []}}),
                ("response.content_part.added", {"output_index": 0, "content_index": 0, "item_id": message["id"], "part": {"type": "output_text", "text": "", "annotations": []}}),
                ("response.output_text.delta", {"item_id": message["id"], "output_index": 0, "content_index": 0, "delta": "Staging inference complete."}),
                ("response.output_text.done", {"item_id": message["id"], "output_index": 0, "content_index": 0, "text": "Staging inference complete."}),
                ("response.content_part.done", {"item_id": message["id"], "output_index": 0, "content_index": 0, "part": message["content"][0]}),
                ("response.output_item.done", {"output_index": 0, "item": message}),
                ("response.completed", {"response": response}),
            ]
            if not body.get("stream"):
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps(response).encode())
                return
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            for sequence, (event, data) in enumerate(events):
                self.wfile.write(("event: " + event + "\ndata: " + json.dumps({"type": event, "sequence_number": sequence, **data}) + "\n\n").encode())
            return
        messages = body.get("messages", [])
        command = None
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, list):
                content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
            match = re.search(r"fixture-command-base64: ([A-Za-z0-9+/=]+)", content) if isinstance(content, str) else None
            if match:
                command = base64.b64decode(match.group(1)).decode()
        tools = body.get("tools", [])
        if command and any(t.get("function", {}).get("name") == "bash" for t in tools) and not any(m.get("role") == "tool" for m in messages):
            delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": "call_fixture", "type": "function",
                     "function": {"name": "bash", "arguments": json.dumps({"command": command, "description": "Check disposable staging project"})}}]}
            finish = "tool_calls"
        else:
            delta, finish = {"role": "assistant", "content": "Staging inference complete."}, "stop"
        if not body.get("stream"):
            output = {"id": "chatcmpl_fixture", "object": "chat.completion", "created": int(time.time()), "model": "mock-fixture",
                      "choices": [{"index": 0, "message": delta, "finish_reason": finish}],
                      "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps(output).encode())
            return
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        for part, reason in [(delta, None), ({}, finish)]:
            output = {"id": "chatcmpl_fixture", "object": "chat.completion.chunk", "created": int(time.time()), "model": "mock-fixture",
                      "choices": [{"index": 0, "delta": part, "finish_reason": reason}]}
            if reason:
                output["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
            self.wfile.write(("data: " + json.dumps(output) + "\n\n").encode())
        self.wfile.write(b"data: [DONE]\n\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hold-seconds", type=int, default=0)
    args = parser.parse_args()
    for port in [PORT, DB_PORT]:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    provider = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    provider.calls = []
    provider.slow_started = threading.Event()
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    names = []
    checks = {}
    stop_file = Path.home() / "dsh-security-review-20261015/gateway-stage-stop"
    stop_file.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="dsh-gateway-stage-") as directory:
        config = Path(directory) / "config.yaml"
        config.write_text(json.dumps({
            "model_list": [{"model_name": "fixture", "litellm_params": {
                "model": "openai/mock-fixture", "api_base": f"http://127.0.0.1:{provider.server_port}/v1", "api_key": UPSTREAM,
                "max_tokens": 2048}, "model_info": {"input_cost_per_token": 0.001, "output_cost_per_token": 0.002}}],
            "general_settings": {"master_key": MASTER, "allow_client_side_credentials": False, "proxy_batch_write_at": 1},
            "litellm_settings": {"set_verbose": False, "drop_params": True}
        }))
        config.chmod(0o600)

        def run(command):
            return subprocess.run(command, check=True, capture_output=True, text=True)

        try:
            suffix = secrets.token_hex(4)
            database = "dsh-stage-db-" + suffix
            gateway = "dsh-stage-gateway-" + suffix
            run(["podman", "run", "-d", "--name", database, "--network=host", "-e", "POSTGRES_USER=stage", "-e", "POSTGRES_DB=stage",
                 "-e", "POSTGRES_PASSWORD=fixture-password", "docker.io/library/postgres:16", "postgres", "-p", str(DB_PORT), "-c", "listen_addresses=127.0.0.1"])
            names.append(database)
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                result = subprocess.run(["podman", "exec", database, "pg_isready", "-p", str(DB_PORT), "-U", "stage"], capture_output=True)
                if result.returncode == 0:
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Staging database did not become ready")
            run(["podman", "run", "-d", "--name", gateway, "--network=host", "-v", str(config) + ":/app/config.yaml:ro",
                 "-e", f"DATABASE_URL=postgresql://stage:fixture-password@127.0.0.1:{DB_PORT}/stage", "-e", "STORE_MODEL_IN_DB=True",
                 "ghcr.io/berriai/litellm:v1.104.2", "--config", "/app/config.yaml", "--host", "127.0.0.1", "--port", str(PORT)])
            names.append(gateway)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                try:
                    if api("/health/liveliness", key=MASTER)[0] == 200:
                        break
                except (OSError, http.client.HTTPException):
                    pass
                time.sleep(1)
            else:
                # Do not dump container logs: a future config could contain real secrets.
                raise RuntimeError("Staging gateway did not become ready; logs withheld")
            key_config = {"key": WORKER, "key_alias": "dsh-isolation-fixture", "models": ["fixture"],
                          "max_budget": 10, "budget_duration": "1d", "rpm_limit": 60, "tpm_limit": 100000,
                          "max_parallel_requests": 2, "duration": "1h",
                          "allowed_routes": ["/chat/completions", "/v1/chat/completions", "/responses", "/v1/responses", "/models", "/v1/models"]}
            status, _ = api("/key/generate", key_config, MASTER)
            if status != 200:
                raise RuntimeError(f"Fixture virtual-key creation failed ({status}); response withheld")
            payload = {"model": "fixture", "messages": [{"role": "user", "content": "staging"}], "max_tokens": 16}
            checks["bounded_key_can_infer"] = api("/v1/chat/completions", payload)[0] == 200
            checks["unknown_key_denied"] = api("/v1/chat/completions", payload, "not-a-key")[0] in [401, 403]
            checks["unlisted_model_denied"] = api("/v1/chat/completions", {**payload, "model": "forbidden"})[0] in [400, 401, 403]
            checks["admin_key_creation_denied"] = api("/key/generate", {})[0] in [401, 403]
            checks["admin_model_info_denied"] = api("/model/info")[0] in [401, 403]
            for field, value in [("api_base", "http://127.0.0.1:1/v1"), ("model_list", []),
                                 ("extra_body", {"api_base": "http://127.0.0.1:1/v1"}),
                                 ("metadata", {"api_base": "http://127.0.0.1:1/v1"})]:
                before = len(provider.calls)
                status, _ = api("/v1/chat/completions", {**payload, field: value})
                checks["override_" + field + "_denied"] = status in [400, 401, 403] and len(provider.calls) == before
            checks["upstream_key_only_at_provider"] = bool(provider.calls) and all(c["expected_auth"] for c in provider.calls)
            def limited_key(name, **limits):
                key = "sk-fixture-" + name + "-000000000000000000000000000000"
                status, _ = api("/key/generate", {**key_config, "key": key, "key_alias": name, **limits}, MASTER)
                if status != 200:
                    raise RuntimeError("Fixture quota-key creation failed")
                return key
            rate_key = limited_key("rpm", rpm_limit=1)
            checks["request_rate_enforced"] = api("/v1/chat/completions", payload, rate_key)[0] == 200 and api("/v1/chat/completions", payload, rate_key)[0] == 429
            token_key = limited_key("tpm", tpm_limit=1)
            checks["token_rate_enforced"] = api("/v1/chat/completions", payload, token_key)[0] == 429
            budget_key = limited_key("budget", max_budget=0.000001)
            budget_before = len(provider.calls)
            budget_status, budget_error = api("/v1/chat/completions", payload, budget_key)
            if budget_status == 200:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    status, info = api("/key/info?key=" + budget_key, key=MASTER)
                    if status == 200 and json.loads(info).get("info", {}).get("spend", 0) > 0:
                        break
                    time.sleep(0.5)
                budget_before = len(provider.calls)
                budget_status, budget_error = api("/v1/chat/completions", payload, budget_key)
            # This pinned release reports budget exhaustion as HTTP 422.
            # Require the budget error AND no forwarded call, not just any 4xx.
            checks["spend_budget_enforced"] = (400 <= budget_status < 500 and b"budget" in budget_error.lower()
                                                 and len(provider.calls) == budget_before)
            if not checks["spend_budget_enforced"]:
                status, body = api("/key/info?key=" + budget_key, key=MASTER)
                info = json.loads(body).get("info", {}) if status == 200 else {}
                print(json.dumps({"budget_fixture_diagnostic": {"status": budget_status, "spend": info.get("spend"), "max_budget": info.get("max_budget")}}), flush=True)
            concurrency_key = limited_key("concurrency", max_parallel_requests=1)
            first_result = []
            first = threading.Thread(target=lambda: first_result.append(api("/v1/chat/completions", {**payload, "messages": [{"role": "user", "content": "fixture-delay"}]}, concurrency_key)[0]))
            first.start()
            if not provider.slow_started.wait(10):
                raise RuntimeError("Fixture concurrency request did not reach provider")
            second_status, _ = api("/v1/chat/completions", payload, concurrency_key)
            first.join(timeout=30)
            checks["concurrency_enforced"] = second_status == 429 and first_result == [200]
            print(json.dumps({"checks": checks, "ready_for_worker_tests": all(checks.values()), "port": PORT,
                              "gateway_uid_on_host": os.geteuid(), "live_credentials_used": False}), flush=True)
            if not all(checks.values()):
                raise RuntimeError("Gateway isolation checks failed")
            deadline = time.monotonic() + min(max(args.hold_seconds, 0), 900)
            while time.monotonic() < deadline and not stop_file.exists():
                time.sleep(1)
        finally:
            for name in reversed(names):
                subprocess.run(["podman", "rm", "-f", "-v", name], capture_output=True)
            provider.shutdown()
            provider.server_close()
            stop_file.unlink(missing_ok=True)
            print("Staging containers and disposable configuration removed.", flush=True)


if __name__ == "__main__":
    main()
