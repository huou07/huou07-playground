"""Policy regressions; real UID/ACL integration is verify.py on Debian."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('harness_setup', ROOT / 'deploy/harness-workers/setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class HarnessPolicyTests(unittest.TestCase):
    def test_native_credential_files_are_left_to_native_store(self):
        for path in ('.codex/auth.json', '.dsh/.credentials.yaml', '.local/share/opencode/auth.json'):
            self.assertEqual(setup.policy(path), 'native')

    def test_secrets_and_backups_are_not_shared(self):
        for path in ('.ssh', '.secrets', '.config/gh/hosts.yml', '.local/share/containers',
                     'Projects/demo/.env', 'Projects/demo/.env.production',
                     'Projects/demo/keys/tls.key', '.npmrc', 'clean-reinstall-20261015',
                     '.local/share/huou07-playground-migration', 'AEH/private'):
            self.assertEqual(setup.policy(path, ['AEH/private']), 'private', path)

    def test_project_instructions_and_examples_remain_shared(self):
        for path in ('Projects/H07P/AGENTS.md', 'Projects/H07P/.agents/skills/a/SKILL.md',
                     'Projects/demo/.env.example', 'Projects/demo/service.py', 'AEH/docs'):
            self.assertEqual(setup.policy(path), 'shared', path)
        self.assertEqual(setup.policy('.local/lib/node_modules/tool/cli.js'), 'readonly')
        self.assertEqual(setup.policy('.config/systemd/user/a.service'), 'readonly')

    def test_inventory_never_enters_secret_native_store_or_follows_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            for directory in ('.ssh', '.codex', 'Projects'):
                (home / directory).mkdir()
            (home / '.ssh/private-key').write_text('synthetic')
            (home / '.codex/auth.json').write_text('synthetic')
            (home / 'Projects/a').write_text('shared')
            (home / 'alias').symlink_to(home / '.ssh', target_is_directory=True)
            with patch.object(setup, 'HOME', home):
                groups = setup.inventory([])
            paths = {str(p.relative_to(home)) for values in groups.values() for p in values}
            self.assertNotIn('alias', paths)
            self.assertNotIn('.ssh/private-key', paths)
            self.assertNotIn('.codex/auth.json', paths)
            self.assertIn('Projects/a', paths)

    def test_service_drops_privilege_and_retains_shared_application(self):
        unit = setup.service('opencode', '/home/huou07/.local/bin/opencode web')
        for required in ('User=opencode-worker', 'HOME=/home/huou07',
                         'NoNewPrivileges=yes', 'CapabilityBoundingSet=\n'):
            self.assertIn(required, unit)
        self.assertNotIn('User=huou07\n', unit)


if __name__ == '__main__':
    unittest.main()
