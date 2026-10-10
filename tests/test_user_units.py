import unittest
from pathlib import Path


UNIT_DIR = Path(__file__).resolve().parents[1] / "deploy" / "user"
UNITS = (
    "huou07-dsh.service",
    "huou07-opencode-web.service",
    "huou07-litellm-db.service",
    "huou07-litellm.service",
    "huou07-omniroute.service",
    "huou07-playground.service",
)


class UserUnitTests(unittest.TestCase):
    def test_app_services_run_in_the_calling_users_manager(self):
        for name in UNITS:
            with self.subTest(unit=name):
                text = (UNIT_DIR / name).read_text()
                self.assertNotRegex(text, r"(?m)^(?:User|Group|SupplementaryGroups)=")
                self.assertIn("WantedBy=default.target", text)

    def test_web_listeners_and_data_paths_are_user_scoped(self):
        dsh = (UNIT_DIR / "huou07-dsh.service").read_text()
        launcher = (UNIT_DIR / "dsh-launcher.py").read_text()
        opencode = (UNIT_DIR / "huou07-opencode-web.service").read_text()
        dashboard = (UNIT_DIR / "huou07-playground.service").read_text()
        self.assertIn("--host", launcher)
        self.assertIn('"127.0.0.1"', launcher)
        self.assertIn("DSH_URL_FILE=%t/huou07-dsh-link/url", dsh)
        self.assertIn("--hostname 127.0.0.1", opencode)
        self.assertIn("WorkingDirectory=%h/Projects", dsh)
        self.assertIn("AF_NETLINK", dsh)
        self.assertIn("APPS_FILE=%h/.local/state/huou07-playground/apps.json", dashboard)
        self.assertIn("DSH_URL_FILE=%t/huou07-dsh-link/url", dashboard)

    def test_gateway_state_and_runtime_use_users_native_paths(self):
        litellm = (UNIT_DIR / "huou07-litellm.service").read_text()
        database = (UNIT_DIR / "huou07-litellm-db.service").read_text()
        omniroute = (UNIT_DIR / "huou07-omniroute.service").read_text()
        self.assertIn("%h/.config/litellm/config.yaml", litellm)
        self.assertIn("%h/.config/litellm/postgres.env", database)
        self.assertIn("%h/.config/litellm/litellm.env", litellm)
        self.assertIn("%h/.local/share/omniroute/data", omniroute)
        self.assertIn("%h/.config/omniroute/omniroute.env", omniroute)
        for text in (litellm, database, omniroute):
            self.assertIn("XDG_RUNTIME_DIR=%t", text)
            self.assertIn("Delegate=yes", text)


if __name__ == "__main__":
    unittest.main()
