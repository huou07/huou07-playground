import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OneUserMigrationTests(unittest.TestCase):
    def test_inventory_is_read_only_and_podman_discovery_fails_closed(self):
        source = (ROOT / "deploy/inspect-one-user-migration.sh").read_text()
        self.assertIn("cd /", source)
        self.assertIn("Podman container discovery failed", source)
        self.assertIn("Podman volume discovery failed", source)
        self.assertIn("podman unshare stat", source)
        self.assertIn("podman unshare cat /proc/self/uid_map", source)
        self.assertNotIn("graphroot copy", source.lower())

    def test_runner_exports_application_data_not_rootless_graphroots(self):
        source = (ROOT / "deploy/migrate-one-user.sh").read_text()
        self.assertIn('podman volume export "$PG_VOLUME"', source)
        self.assertIn('podman volume import "$PG_VOLUME" -', source)
        self.assertIn('podman unshare tar --numeric-owner', source)
        self.assertIn('podman unshare stat -c', source)
        self.assertNotIn("/containers/storage", source)
        self.assertNotIn("graphroot", source.lower())

    def test_cutover_has_preflight_collision_checks_and_failure_recovery(self):
        source = (ROOT / "deploy/migrate-one-user.sh").read_text()
        self.assertLess(source.index("trap on_exit EXIT"), source.index("systemctl stop \"$unit\""))
        self.assertIn("verify_merge /var/lib/huou07-dsh/config", source)
        self.assertIn("state collision before cutover", source)
        self.assertIn("restore_legacy", source)
        self.assertIn('case "$state" in enabled|enabled-runtime)', source)


if __name__ == "__main__":
    unittest.main()
