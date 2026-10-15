#!/usr/bin/env python3
"""Real Codex Responses inference through the disposable gateway, without auth.json."""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


def main():
    if os.geteuid() != 987:
        raise SystemExit("Run as agents-worker (987)")
    with tempfile.TemporaryDirectory(prefix="codex-gateway-stage-") as directory:
        home = Path(directory)
        codex_home = home / ".codex"
        codex_home.mkdir(mode=0o700)
        (codex_home / "packages").mkdir(mode=0o700)
        (codex_home / "packages/standalone").mkdir(mode=0o700)
        project = home / "project"
        project.mkdir(mode=0o700)
        (codex_home / "config.toml").write_text('''model_provider = "stage_gateway"
model = "fixture"
model_reasoning_effort = "low"
[model_providers.stage_gateway]
name = "Disposable restricted gateway"
base_url = "http://127.0.0.1:14009/v1"
env_key = "STAGE_GATEWAY_CAPABILITY"
wire_api = "responses"
requires_openai_auth = false
supports_websockets = false
''')
        env = {"HOME": str(home), "CODEX_HOME": str(codex_home), "PATH": "/usr/local/bin:/usr/bin:/bin",
               "LANG": "C.UTF-8", "STAGE_GATEWAY_CAPABILITY": "sk-worker-staging-only-000000000000000000000000000"}
        result = subprocess.run(["/opt/agent-workbench/bin/codex", "exec", "--ephemeral", "--skip-git-repo-check",
                                 "--sandbox", "read-only", "--json", "Reply with: Staging inference complete."],
                                cwd=project, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        completed = False
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            completed |= event.get("type") == "turn.completed"
        checks = {"worker_uid": os.geteuid(), "exit_code": result.returncode, "turn_completed": completed,
                  "auth_json_absent": not (codex_home / "auth.json").exists(), "uses_live_oauth_tokens": False}
        print(json.dumps(checks, indent=2))
        if result.returncode != 0 or not completed:
            # This child has a fresh HOME and only a disposable capability.
            diagnostic = result.stderr[-1200:] + result.stdout[-1200:]
            diagnostic = diagnostic.replace(env["STAGE_GATEWAY_CAPABILITY"], "<fixture-capability>")
            diagnostic = re.sub(r"Bearer\s+\S+", "Bearer <redacted>", diagnostic)
            print(json.dumps({"fixture_engine_diagnostic": diagnostic}))
        assert result.returncode == 0 and completed, "Codex gateway inference failed; engine output withheld"


if __name__ == "__main__":
    main()
