"""Fixture-only boundary regressions; no root privileges or systemctl invocation."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('lifecycle', Path(__file__).resolve().parents[2] / 'deploy/package/lifecycle.py')
lifecycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifecycle)


class PackageBoundary(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.patch = patch.multiple(lifecycle, ROOT=self.root, LIVE=False)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temporary.cleanup)

    def test_rejects_state_symlink_before_writing(self):
        outside = self.root / 'outside'
        outside.mkdir()
        parent = self.root / 'var/lib'
        parent.mkdir(parents=True)
        (parent / 'huou07-playground').symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, 'symbolic link'):
            lifecycle.protected('/var/lib/huou07-playground')
        self.assertEqual(list(outside.iterdir()), [])

    def test_unknown_unit_is_never_adopted(self):
        unit = self.root / 'etc/systemd/system/huou07-playground.service'
        unit.parent.mkdir(parents=True)
        unit.write_text('ExecStart=/some/other/program\n')
        with self.assertRaisesRegex(RuntimeError, 'unrelated'):
            lifecycle.prepare()
        self.assertEqual(unit.read_text(), 'ExecStart=/some/other/program\n')

    def test_worker_dropin_cannot_bypass_policy_launcher(self):
        dropin = self.root / 'etc/systemd/system/h07p-dsh.service.d/custom.conf'
        dropin.parent.mkdir(parents=True)
        dropin.write_text('[Service]\nExecStart=/unmanaged/native\n')
        with self.assertRaisesRegex(RuntimeError, 'drop-in'):
            lifecycle.prepare()

    def test_dpkg_qualified_postinst_dispatches_and_rolls_back_failure(self):
        with patch('sys.argv', ['huou07-playground.postinst', 'configure']), \
                patch.object(lifecycle, 'configure', side_effect=RuntimeError('fixture health failure')) as configure, \
                patch.object(lifecycle, 'rollback') as rollback:
            with self.assertRaisesRegex(RuntimeError, 'fixture health'):
                lifecycle.main()
            configure.assert_called_once()
            rollback.assert_called_once()

    def test_rejected_new_upgrade_does_not_replay_previous_rollback(self):
        lifecycle.protected('/var/lib/huou07-package', 0o700)
        lifecycle.path('/var/lib/huou07-package/transaction.json').write_text('{"backup":"123"}')
        with patch('sys.argv', ['huou07-playground.postrm', 'abort-upgrade']), \
                patch.object(lifecycle, 'rollback') as rollback:
            lifecycle.main()
            rollback.assert_not_called()

    def test_snapshot_and_rollback_preserve_database(self):
        release = lifecycle.protected('/opt/huou07-playground/releases/old')
        (release / 'binary').write_bytes(b'old executable')
        lifecycle.activate('/opt/huou07-playground/releases/old')
        state = lifecycle.protected('/var/lib/huou07-playground')
        (state / 'owner.db').write_bytes(b'original policy')
        lifecycle.prepare()
        (state / 'owner.db').write_bytes(b'bad migration')
        lifecycle.rollback()
        self.assertEqual((state / 'owner.db').read_bytes(), b'original policy')
        self.assertTrue(list(state.parent.glob('huou07-playground.failed-*')))
        self.assertTrue(os.readlink(lifecycle.path('/opt/huou07-playground/current')).startswith('/opt/huou07-playground/releases/rollback-'))


if __name__ == '__main__':
    unittest.main()
