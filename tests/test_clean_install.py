import contextlib
import base64
import http.server
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


admin = load_module("clean_playground_apps", ROOT / "deploy/admin/clean-playground-apps.py")
launcher = load_module("dsh_dashboard_launcher", ROOT / "deploy/dsh-dashboard-launcher.py")


class CleanInstallTests(unittest.TestCase):
    def rollback_fixture(self, temp):
        root = Path(temp)
        home = root / "home"
        (home / ".config/containers/systemd").mkdir(parents=True)
        checkpoint = root / "rollback-state.json"
        checkpoint.write_text("checkpoint")
        registry = root / "apps.json"
        registry.write_text('{"apps": []}\n')
        state = {
            "active": {unit: True for unit in admin.APP_UNITS},
            "enabled": {unit: True for unit in admin.APP_UNITS},
            "dashboard_apps": '{"apps": []}\n',
        }
        return root, home, checkpoint, registry, state

    def rollback_patches(self, home, checkpoint, registry):
        return (
            patch.object(admin, "STATE_FILE", checkpoint),
            patch.object(admin, "DASHBOARD_APPS_FILE", registry),
            patch.object(admin, "validate_old_installation"),
            patch.object(admin, "validate_legacy_listeners"),
            patch.object(admin, "read_state", return_value={
                "active": {unit: True for unit in admin.APP_UNITS},
                "enabled": {unit: True for unit in admin.APP_UNITS},
                "dashboard_apps": '{"apps": []}\n',
            }),
            patch.object(admin.pwd, "getpwnam", return_value=SimpleNamespace(pw_dir=str(home), pw_uid=1234)),
        )

    @staticmethod
    def successful_rollback_command(args, *, check=True):
        output = ""
        if "show-environment" in args:
            pass
        elif "--property=LoadState" in args:
            output = "loaded\ninactive\n"
        elif "--property=ActiveState" in args:
            output = "active\n"
        elif "--property=UnitFileState" in args:
            output = "disabled\n" if "--user" in args else "enabled\n"
        elif args[:2] == ["runuser", "-u"]:
            output = ""
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    def test_rollback_connection_failure_preserves_checkpoint_and_does_not_restore_old_apps(self):
        with tempfile.TemporaryDirectory() as temp:
            _, home, checkpoint, registry, _ = self.rollback_fixture(temp)
            patches = self.rollback_patches(home, checkpoint, registry)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patch.object(
                admin, "run", side_effect=subprocess.CalledProcessError(1, ["systemctl", "show-environment"])
            ) as run:
                with self.assertRaisesRegex(RuntimeError, "user manager is unreachable"):
                    admin.rollback()
                self.assertTrue(checkpoint.exists())
                self.assertFalse(any(call.args[0][:2] == ["systemctl", "start"] for call in run.call_args_list))

    def test_rollback_stop_failure_preserves_checkpoint_and_does_not_restore_old_apps(self):
        with tempfile.TemporaryDirectory() as temp:
            _, home, checkpoint, registry, _ = self.rollback_fixture(temp)
            patches = self.rollback_patches(home, checkpoint, registry)

            def fail_stop(args, *, check=True):
                if "stop" in args:
                    raise subprocess.CalledProcessError(1, args)
                return self.successful_rollback_command(args, check=check)

            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patch.object(admin, "run", side_effect=fail_stop) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    admin.rollback()
                self.assertTrue(checkpoint.exists())
                self.assertFalse(any(call.args[0][:2] == ["systemctl", "start"] for call in run.call_args_list))

    def test_rollback_rejects_unknown_user_unit_state_and_preserves_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            _, home, checkpoint, registry, _ = self.rollback_fixture(temp)
            patches = self.rollback_patches(home, checkpoint, registry)

            def unknown_state(args, *, check=True):
                if "--property=LoadState" in args:
                    return subprocess.CompletedProcess(args, 0, stdout="not-found\ninactive\n", stderr="")
                return self.successful_rollback_command(args, check=check)

            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patch.object(admin, "run", side_effect=unknown_state):
                with self.assertRaisesRegex(RuntimeError, "known inactive state"):
                    admin.rollback()
                self.assertTrue(checkpoint.exists())

    def test_rollback_restores_legacy_services_after_new_units_and_containers_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            _, home, checkpoint, registry, _ = self.rollback_fixture(temp)
            patches = self.rollback_patches(home, checkpoint, registry)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patch.object(
                admin, "run", side_effect=self.successful_rollback_command
            ) as run:
                admin.rollback()
                self.assertFalse(checkpoint.exists())
                self.assertEqual(json.loads(registry.read_text()), {"apps": []})
                commands = [call.args[0] for call in run.call_args_list]
                podman_check = next(i for i, args in enumerate(commands) if args[-4:] == ["podman", "ps", "--format", "{{.Names}}"])
                legacy_restore = next(i for i, args in enumerate(commands) if args[:2] == ["systemctl", "start"])
                self.assertLess(podman_check, legacy_restore)

    def test_rollback_does_not_restore_legacy_services_while_new_container_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            _, home, checkpoint, registry, _ = self.rollback_fixture(temp)
            patches = self.rollback_patches(home, checkpoint, registry)

            def running_container(args, *, check=True):
                result = self.successful_rollback_command(args, check=check)
                if args[:2] == ["runuser", "-u"]:
                    result.stdout = "huou07-litellm-proxy\n"
                return result

            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patch.object(admin, "run", side_effect=running_container) as run:
                with self.assertRaisesRegex(RuntimeError, "containers remain running"):
                    admin.rollback()
                self.assertTrue(checkpoint.exists())
                self.assertFalse(any(call.args[0][:2] == ["systemctl", "start"] for call in run.call_args_list))

    def test_rollback_port_check_failure_preserves_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            _, home, checkpoint, registry, _ = self.rollback_fixture(temp)
            patches = self.rollback_patches(home, checkpoint, registry)

            def fail_port_check(args, *, check=True):
                if args and args[0] == "ss":
                    raise subprocess.CalledProcessError(1, args)
                return self.successful_rollback_command(args, check=check)

            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patch.object(admin, "run", side_effect=fail_port_check) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    admin.rollback()
                self.assertTrue(checkpoint.exists())
                self.assertFalse(any(call.args[0][:2] == ["systemctl", "start"] for call in run.call_args_list))

    def test_preflight_checks_user_manager_before_owner_preparation(self):
        with tempfile.TemporaryDirectory() as temp:
            state_file = Path(temp) / "state.json"
            tmpfiles_rule = Path(temp) / "tmpfiles.conf"
            with patch.object(admin, "STATE_FILE", state_file), patch.object(admin, "TMPFILES_RULE", tmpfiles_rule), \
                    patch.object(admin, "validate_old_installation"), patch.object(admin, "validate_legacy_listeners"), \
                    patch.object(admin, "verify_user_manager", side_effect=RuntimeError("manager offline")) as verify_manager, \
                    patch.object(admin.shutil, "which", return_value="/usr/bin/tool"), patch.object(admin, "run_as_owner") as prepare:
                with self.assertRaisesRegex(RuntimeError, "manager offline"):
                    admin.preflight()
                verify_manager.assert_called_once()
                prepare.assert_not_called()

    def test_dashboard_health_migrates_known_legacy_defaults_and_preserves_custom_url(self):
        entries = [
            {
                "name": "OpenCode Web", "url": "http://127.0.0.1:14096/", "description": "OpenCode",
                "category": "Coding Agents", "health_url": "http://127.0.0.1:4096/",
                "health_method": "GET", "management_url": "http://127.0.0.1:14096/",
            },
            {
                "name": "LiteLLM Gateway", "url": "http://127.0.0.1:4000/ui", "description": "LiteLLM",
                "category": "AI Gateway", "health_url": "http://127.0.0.1:4000/health/liveliness",
                "health_method": "GET", "management_url": "http://127.0.0.1:4000/ui",
            },
            {
                "name": "OmniRoute", "url": "http://127.0.0.1:20128/", "description": "Custom route",
                "category": "Personal", "health_url": "http://127.0.0.1:20128/custom-health",
                "health_method": "HEAD", "management_url": "http://127.0.0.1:20128/",
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            registry = Path(temp) / "apps.json"
            registry.write_text(json.dumps({"apps": entries}))
            with patch.dict(os.environ, {"APPS_FILE": str(registry)}):
                admin.register_dashboard_health()
            saved = {item["name"]: item for item in json.loads(registry.read_text())["apps"]}
        self.assertEqual(saved["OpenCode Web"]["health_url"], "http://127.0.0.1:4096/global/health")
        self.assertEqual(saved["LiteLLM Gateway"]["health_url"], "http://127.0.0.1:4000/health/readiness")
        self.assertEqual(saved["OmniRoute"]["health_url"], "http://127.0.0.1:20128/custom-health")
        self.assertEqual(saved["OmniRoute"]["health_method"], "HEAD")

    def test_health_checker_executes_dsh_cookie_flow_and_named_http_checks(self):
        expected_auth = "Basic " + base64.b64encode(b"synthetic-user:synthetic-password").decode()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/?token="):
                    self.send_response(302)
                    self.send_header("Location", "/")
                    self.send_header("Set-Cookie", "session=synthetic; Path=/")
                    self.end_headers()
                elif self.path == "/":
                    self.send_response(200 if self.headers.get("Cookie") == "session=synthetic" else 401)
                    self.end_headers()
                elif self.path == "/global/health":
                    self.send_response(200 if self.headers.get("Authorization") == expected_auth else 401)
                    self.end_headers()
                elif self.path in {"/dashboard", "/litellm", "/omniroute"}:
                    self.send_response(200)
                    self.end_headers()
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *_args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                env_file = root / "opencode.env"
                env_file.write_text(
                    "OPENCODE_SERVER_USERNAME=synthetic-user\n"
                    "OPENCODE_SERVER_PASSWORD=synthetic-password\n"
                )
                token_file = root / "dsh-url"
                token_file.write_text("/?token=" + "A" * 40 + "\n")
                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "deploy/check-user-app-health.py"),
                        "--opencode-env", str(env_file),
                        "--dsh-token-file", str(token_file),
                        "--dsh-url", base_url,
                        "--dashboard-url", base_url + "/dashboard",
                        "--opencode-url", base_url + "/global/health",
                        "--litellm-url", base_url + "/litellm",
                        "--omniroute-url", base_url + "/omniroute",
                        "--timeout", "5",
                        "--interval", "0.01",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                for name in ("dashboard", "OpenCode Web", "LiteLLM", "OmniRoute", "DSH Web"):
                    self.assertIn(name, result.stdout)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_admin_scope_excludes_dashboard_vpn_and_home(self):
        self.assertEqual(set(admin.APP_UNITS), {
            "huou07-dsh.service", "huou07-opencode-web.service",
            "huou07-litellm.service", "huou07-litellm-db.service", "huou07-omniroute.service",
        })
        targets = admin.OLD_PATHS + admin.OLD_FILES
        self.assertTrue(all("/home/" not in path for path in targets))
        self.assertFalse(any(path in {"/var/lib", "/etc", "/usr/local/libexec", "/srv"} for path in targets))
        self.assertFalse(any("docker" in path.lower() or "wireguard" in path.lower() for path in targets))

    def test_admin_cleanup_refuses_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            actual = root / "actual"
            actual.mkdir()
            link = root / "link"
            link.symlink_to(actual, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                admin.remove_exact(str(link))
            self.assertTrue(actual.is_dir())

    def test_dsh_launcher_saves_only_scoped_url_and_never_logs_token(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "url"
            launcher.URL_FILE = path
            token = "A" * 40
            stdout = io.StringIO()
            with contextlib.redirect_stderr(stdout):
                launcher.save_url(f"dsh web: http://127.0.0.1:3080/?token={token}")
            self.assertEqual(path.read_text(), f"/?token={token}\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertNotIn(token, stdout.getvalue())
            path.unlink()
            launcher.save_url(f"dsh web: http://0.0.0.0:3080/?token={token}")
            self.assertFalse(path.exists())

    def test_native_service_templates_use_home_and_loopback(self):
        dsh = (ROOT / "deploy/user/dsh.service").read_text()
        opencode = (ROOT / "deploy/user/opencode-web.service").read_text()
        self.assertIn("DSH_HOME=%h/.dsh", dsh)
        self.assertIn("/run/huou07-dsh-link/url", (ROOT / "deploy/dsh-dashboard-launcher.py").read_text())
        self.assertIn("dsh-dashboard-launcher.py", dsh)
        self.assertIn("--host", (ROOT / "deploy/dsh-dashboard-launcher.py").read_text())
        self.assertIn('"--trusted-host", host', (ROOT / "deploy/dsh-dashboard-launcher.py").read_text())
        self.assertIn("opencode web --hostname 127.0.0.1 --port 4096", opencode)
        self.assertNotIn("--pure", opencode)
        self.assertIn("InaccessiblePaths=-/run/docker.sock", dsh)
        self.assertIn("NoNewPrivileges=yes", opencode)

    def test_container_deployments_are_pinned_and_private(self):
        litellm = (ROOT / "deploy/user/litellm.container").read_text()
        omni = (ROOT / "deploy/user/omniroute.container").read_text()
        litellm_pod = (ROOT / "deploy/user/litellm.pod").read_text()
        omni_pod = (ROOT / "deploy/user/omniroute.pod").read_text()
        self.assertIn("ghcr.io/berriai/litellm:v1.104.2", litellm)
        self.assertIn("diegosouzapw/omniroute:3.8.51", omni)
        self.assertIn("Volume=huou07-omniroute-data:/app/data", omni)
        self.assertNotIn("UserNS=keep-id", (ROOT / "deploy/user/omniroute.pod").read_text())
        self.assertIn("postgres:16", (ROOT / "deploy/user/litellm-db.container").read_text())
        self.assertIn("redis:8.6.5-alpine", (ROOT / "deploy/user/omniroute-redis.container").read_text())
        for text in (litellm_pod, omni_pod):
            self.assertIn("127.0.0.1:", text)
            self.assertNotIn("0.0.0.0", text)

    def test_installer_is_user_scoped_and_model_free(self):
        installer = (ROOT / "deploy/install-user-apps.sh").read_text()
        self.assertNotIn("sudo ", installer)
        for pinned in ("@deepseek-ai/dsh@$DSH_VERSION", "@agentclientprotocol/codex-acp@$ACP_VERSION", "pnpm@$PNPM_VERSION", "@zaimokuza/dsh-acp-adapter@$ADAPTER_VERSION"):
            self.assertIn(pinned, installer)
        self.assertIn('"$HOME_DIR/.opencode/bin/opencode" auth list >/dev/null', installer)
        self.assertIn('login_status=$("$HOME_DIR/.local/bin/codex" login status 2>&1)', installer)
        self.assertIn("npm rebuild --global --prefix", installer)
        self.assertIn("--allow-scripts=@deepseek-ai/dsh-subprocess-local,koffi,node-pty,@google/genai,protobufjs", installer)
        self.assertIn("prepare) prepare ;;", installer)
        self.assertIn("deactivate) deactivate ;;", installer)
        self.assertIn("activate) activate ;;", installer)
        self.assertNotIn("systemctl --user enable litellm.service", installer)
        self.assertIn("systemctl --user start litellm.service omniroute.service", installer)
        self.assertIn("[ \"$cgroups\" = v2 ]", installer)
        self.assertIn("subprocess.Popen(command", installer)
        self.assertIn("process.stdin.flush()", installer)
        self.assertIn("huou07-omniroute-data", installer)
        self.assertIn("Could not verify rootless Podman", installer)
        self.assertIn('"JWT_SECRET=$jwt"', installer)
        self.assertIn('"API_KEY_SECRET=$api_key_secret"', installer)
        self.assertIn('"OMNIROUTE_WS_BRIDGE_SECRET=$ws_secret"', installer)
        self.assertIn('python3 "$ROOT/deploy/check-user-app-runtime.py"', installer)
        prepare = installer.split("prepare() {", 1)[1].split("\n}\n", 1)[0]
        self.assertNotIn("ports_free", prepare)
        self.assertNotIn("/v1/chat/completions", installer)

    def test_container_staging_uses_only_disposable_names_and_no_inference(self):
        staging = (ROOT / "deploy/check-user-app-runtime.py").read_text()
        self.assertIn('"h07-check-" + secrets.token_hex(5)', staging)
        self.assertIn("Temporary staging containers, pods, and volumes removed.", staging)
        self.assertIn("/health/readiness", staging)
        self.assertIn("/healthz", staging)
        self.assertIn("socket.SO_REUSEADDR", staging)
        self.assertIn("OmniRoute data volume did not persist across restart", staging)
        self.assertNotIn("/v1/chat/completions", staging)
        self.assertNotIn("huou07-litellm-postgres", staging)
        self.assertNotIn("huou07-omniroute-redis", staging)

    def test_admin_preflight_prepares_before_cutover_and_rollback_is_verified(self):
        admin_script = (ROOT / "deploy/admin/clean-playground-apps.py").read_text()
        self.assertIn('run_as_owner("prepare")', admin_script)
        self.assertIn('run_as_owner("activate")', admin_script)
        self.assertIn("validate_legacy_listeners()", admin_script)
        self.assertIn("except Exception as exc:", admin_script)
        self.assertIn('print("Previous application services were restored.', admin_script)
        self.assertIn('"huou07 OmniRoute AI gateway"', admin_script)

    def test_rollback_restores_dashboard_registry_atomically(self):
        with tempfile.TemporaryDirectory() as temp:
            original_path = admin.DASHBOARD_APPS_FILE
            path = Path(temp) / "apps.json"
            try:
                admin.DASHBOARD_APPS_FILE = path
                path.write_text('{"apps": []}\n')
                path.chmod(0o640)
                admin.restore_dashboard_registry('{"apps": [{"name": "old"}]}\n')
                self.assertEqual(path.read_text(), '{"apps": [{"name": "old"}]}\n')
                self.assertEqual(path.stat().st_mode & 0o777, 0o640)
                self.assertFalse(list(Path(temp).glob(".apps-rollback-*")))
            finally:
                admin.DASHBOARD_APPS_FILE = original_path


if __name__ == "__main__":
    unittest.main()
