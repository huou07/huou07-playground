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

worker_spec = importlib.util.spec_from_file_location('harness_workers', ROOT / 'deploy/package/workers.py')
workers = importlib.util.module_from_spec(worker_spec)
worker_spec.loader.exec_module(workers)


class HarnessPolicyTests(unittest.TestCase):
    def test_native_credential_files_are_left_to_native_store(self):
        for path in ('.codex/auth.json', '.dsh/.credentials.yaml', '.local/share/opencode/auth.json'):
            self.assertEqual(setup.policy(path), 'native')

    def test_secrets_and_backups_are_not_shared(self):
        for path in ('.ssh', '.secrets', '.config/gh/hosts.yml', '.local/share/containers',
                     'Projects/demo/.env', 'Projects/demo/.env.production',
                     'Projects/demo/keys/tls.key', '.npmrc', 'clean-reinstall-20261015',
                     '.cargo/config', '.cargo/config.toml', '.cargo/credentials.toml',
                     '.local/share/huou07-playground-migration', 'AEH/private'):
            self.assertEqual(setup.policy(path, ['AEH/private']), 'private', path)

    def test_project_instructions_and_examples_remain_shared(self):
        for path in ('Projects/H07P/AGENTS.md', 'Projects/H07P/.agents/skills/a/SKILL.md',
                     'Projects/demo/.env.example', 'Projects/demo/service.py', 'AEH/docs'):
            self.assertEqual(setup.policy(path), 'shared', path)
        self.assertEqual(setup.policy('.local/lib/node_modules/tool/cli.js'), 'readonly')
        self.assertEqual(
            setup.policy('.local/share/playwright-cli/node_modules/@playwright/cli/index.js'),
            'readonly',
        )
        self.assertEqual(setup.policy('.cargo/registry/index/config.json'), 'readonly')
        self.assertEqual(setup.policy('.cargo/git/checkouts/library/src/lib.rs'), 'readonly')
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
                         'NoNewPrivileges=yes', 'CapabilityBoundingSet=\n',
                         'GIT_CONFIG_COUNT=0',
                         "GIT_CONFIG_PARAMETERS='safe.directory=/home/huou07/*'"):
            self.assertIn(required, unit)
        self.assertNotIn('GIT_CONFIG_KEY_0', unit)
        self.assertNotIn('GIT_CONFIG_VALUE_0', unit)
        self.assertNotIn('User=huou07\n', unit)

    def test_refuses_symlinked_native_boundary_before_privileged_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'ordinary').mkdir()
            (home / '.codex').symlink_to(home / 'ordinary', target_is_directory=True)
            with patch.object(setup, 'HOME', home):
                with self.assertRaisesRegex(RuntimeError, 'symlink in managed boundary'):
                    setup.validate_boundaries([])


class BaselineFilterTests(unittest.TestCase):
    def test_stale_paths_are_skipped_and_existing_acl_records_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'home'
            home.mkdir()
            existing = home / 'space name'
            existing.write_text('ordinary data')
            missing = home / 'retired path'
            source = Path(temp) / 'baseline.restore'
            destination = Path(temp) / 'filtered.restore'
            control = Path(temp) / 'control'
            control.mkdir()
            source.write_bytes(
                b'# file: ' + str(existing).encode() + b'\n'
                b'# owner: owner\nuser::rw-\ngroup::---\nother::---\n\n'
                b'# file: ' + str(missing).encode() + b'\n'
                b'# owner: owner\nuser::rw-\ngroup::---\nother::---\n'
            )
            with patch.object(workers, 'HOME', home):
                restored, skipped = workers.filter_baseline(
                    source, destination, control, 'a' * 64, home.stat().st_dev
                )
            self.assertEqual((restored, skipped), (1, 1))
            filtered = destination.read_bytes()
            self.assertIn(str(existing).encode(), filtered)
            self.assertNotIn(str(missing).encode(), filtered)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

    def test_getfacl_octal_path_escapes_decode_without_shell_interpretation(self):
        self.assertEqual(workers.decode_acl_path(b'/home/owner/space\\040name'),
                         '/home/owner/space name')

    def test_baseline_filter_rejects_paths_outside_home_before_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'home'
            home.mkdir()
            source = Path(temp) / 'baseline.restore'
            destination = Path(temp) / 'filtered.restore'
            control = Path(temp) / 'control'
            control.mkdir()
            source.write_bytes(b'# file: /root/.bashrc\nuser::rw-\n')
            with patch.object(workers, 'HOME', home), self.assertRaisesRegex(
                RuntimeError, 'outside the shared home'
            ):
                workers.filter_baseline(source, destination, control, 'b' * 64, home.stat().st_dev)


class AclBaselineRegistryTests(unittest.TestCase):
    """The ACL reset must not depend on one fixed historical snapshot path."""

    def _snapshot(self, root, name, size=1_100_000, mode=0o600, directory_mode=0o700):
        import os
        directory = root / name
        directory.mkdir()
        os.chmod(directory, directory_mode)
        target = directory / 'acl.restore'
        with target.open('wb') as output:
            output.truncate(size)
        os.chmod(target, mode)
        return target

    def test_selects_newest_validated_snapshot(self):
        import os
        import time
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            uid = os.getuid()
            older = self._snapshot(root, '20261001-000000-1')
            time.sleep(0.02)
            newer = self._snapshot(root, '20261015-220803')
            self.assertEqual(workers.select_acl_baseline(root, uid), newer)
            self.assertNotEqual(workers.select_acl_baseline(root, uid), older)

    def test_rejects_untrusted_or_unnamed_snapshots(self):
        import os
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            uid = os.getuid()
            self._snapshot(root, '20261010-101010-1', directory_mode=0o777)
            self._snapshot(root, 'unrelated')
            self._snapshot(root, '20261011-101010-1', size=10)
            self._snapshot(root, '20261012-101010-1', mode=0o666)
            self.assertIsNone(workers.select_acl_baseline(root, uid))

    def test_snapshot_name_shape(self):
        for name in ('20261015-220803', '20261017-120000-123456789'):
            self.assertTrue(workers.acl_snapshot_name(name))
        for name in ('not-a-stamp', '2026-1015-220803', '20261015-220803x'):
            self.assertFalse(workers.acl_snapshot_name(name))

    def test_registry_root_honours_environment(self):
        import importlib.util
        import os
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {'H07P_ACL_BACKUP_ROOT': temp}):
                spec = importlib.util.spec_from_file_location(
                    'harness_workers_env', ROOT / 'deploy/package/workers.py')
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.assertEqual(str(module.ACL_BASELINE_ROOT), temp)
                target = self._snapshot(module.ACL_BASELINE_ROOT, '20261015-220803')
                self.assertEqual(module.select_acl_baseline(root=module.ACL_BASELINE_ROOT,
                                                            expected_uid=os.getuid()), target)

    def test_reset_writes_rollback_snapshots_to_the_configured_root(self):
        # Regression guard: selection and creation previously used different roots,
        # so a configured registry could never see the snapshots it had just written.
        import inspect
        source = inspect.getsource(workers.reset_acl)
        self.assertIn('ACL_BASELINE_ROOT', source)
        self.assertNotIn("'/var/backups/h07p-harness-workers'", source)


if __name__ == '__main__':
    unittest.main()
