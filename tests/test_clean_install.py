import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


admin = load_module("clean_playground_apps", ROOT / "deploy/admin/clean-playground-apps.py")
launcher = load_module("dsh_dashboard_launcher", ROOT / "deploy/dsh-dashboard-launcher.py")


class CleanInstallTests(unittest.TestCase):
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
        self.assertIn('"$HOME_DIR/.local/bin/codex" login status', installer)
        self.assertIn("prepare) prepare ;;", installer)
        self.assertIn("activate) activate ;;", installer)
        self.assertNotIn("systemctl --user enable litellm.service", installer)
        self.assertIn("systemctl --user start litellm.service omniroute.service", installer)
        self.assertIn("[ \"$cgroups\" = v2 ]", installer)
        self.assertIn('"JWT_SECRET=$jwt"', installer)
        self.assertIn('"API_KEY_SECRET=$api_key_secret"', installer)
        self.assertIn('"OMNIROUTE_WS_BRIDGE_SECRET=$ws_secret"', installer)
        prepare = installer.split("prepare() {", 1)[1].split("\n}\n", 1)[0]
        self.assertNotIn("ports_free", prepare)
        self.assertNotIn("/v1/chat/completions", installer)

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
