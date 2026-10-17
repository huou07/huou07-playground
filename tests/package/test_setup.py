import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('h07p_setup',Path(__file__).resolve().parents[2]/'deploy/package/setup.py')
setup=importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_repository_urls_and_authentication_values_never_reach_diagnostics(self):
        output=setup.redact('Fetch https://private-user:private-password@example.invalid/repo\nAuthorization: Bearer synthetic-secret\napi_key="synthetic-other"\nnormal package information')
        for value in ['private-user','private-password','synthetic-secret','synthetic-other']:self.assertNotIn(value,output)
        self.assertIn('normal package information',output)
        private=setup.redact('-----BEGIN PRIVATE KEY-----\nsynthetic-private-body\n-----END PRIVATE KEY-----\nnormal diagnostics')
        self.assertNotIn('synthetic-private-body',private)
        self.assertIn('normal diagnostics',private)

    def test_wrong_checksum_is_rejected_before_any_package_action(self):
        with tempfile.TemporaryDirectory() as directory:
            package=Path(directory)/'candidate.deb';package.write_bytes(b'synthetic package bytes')
            Path(str(package)+'.sha256').write_text('0'*64+'  candidate.deb\n')
            with patch.object(setup,'command',return_value=(0,'Package: huou07-playground\nVersion: 1.0\nArchitecture: amd64','')) as command:
                with self.assertRaisesRegex(setup.SetupError,'Checksum'):setup.metadata(package)
                self.assertEqual(command.call_count,1)
                self.assertEqual(command.call_args.args[0][0],'dpkg-deb')

    def test_foreign_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            package=Path(directory)/'candidate.deb';package.write_bytes(b'fixture')
            with patch.object(setup,'command',return_value=(0,'Package: other-application\nVersion: 1.0\nArchitecture: amd64','')):
                with self.assertRaisesRegex(setup.SetupError,'không phải H07P'):setup.metadata(package)

    def test_dependency_removal_plan_is_rejected_even_if_resolver_succeeds(self):
        with patch.object(setup,'command',return_value=(0,'Remv unrelated-package [1.0]\nInst huou07-playground (1.0 local)','')):
            with self.assertRaisesRegex(setup.SetupError,'gỡ gói khác'):setup.plan({'path':'/fixture.deb'})

    def test_dependency_conflict_does_not_trigger_a_global_fix_broken(self):
        with patch.object(setup,'command',return_value=(100,'','unmet dependencies')) as command:
            with self.assertRaisesRegex(setup.SetupError,'dependency'):setup.plan({'path':'/fixture.deb'})
            self.assertEqual(command.call_count,1)
            args=command.call_args.args[0]
            self.assertIn('--simulate',args);self.assertIn('--no-remove',args)
            self.assertNotIn('--fix-broken',args)

    def test_repair_uses_reinstall_and_never_removes_dependencies(self):
        info=dict(path='/fixture.deb',Version='1.0',sha256='a'*64,checksum_present=True)
        with patch.object(setup,'command',return_value=(0,'Inst huou07-playground (1.0 local)','')) as command:
            result=setup.plan(info,repair=True)
            self.assertIn('--reinstall',command.call_args.args[0])
            self.assertIn('--no-remove',command.call_args.args[0])
            self.assertTrue(result['repair']);self.assertFalse(result['removes_other_packages'])

    def test_dry_run_does_not_cache_install_restart_or_require_root(self):
        info=dict(path='/fixture.deb',Version='1.0',sha256='a'*64,checksum_present=True)
        with patch.object(setup,'platform'),patch.object(setup,'metadata',return_value=info),patch.object(setup,'plan',return_value={'apt_plan':'synthetic plan'}),patch.object(setup,'cache') as cache,patch.object(setup,'health') as health,patch.object(setup,'require_root') as root,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.main(['install','/fixture.deb','--dry-run']),0)
            cache.assert_not_called();health.assert_not_called();root.assert_not_called()

    def test_uninstall_cannot_remove_another_package(self):
        with patch.object(setup,'platform'),patch.object(setup,'require_root'),patch.object(setup,'command',return_value=(0,'Remv huou07-playground [1.0]\nRemv other-package [1.0]','')) as command,contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(setup.SetupError,'ảnh hưởng gói khác'):setup.main(['uninstall','--yes'])
            self.assertEqual(command.call_count,1)
            self.assertIn('--simulate',command.call_args.args[0])

    def test_cache_symlink_is_rejected_without_writing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'target';target.mkdir()
            link=Path(directory)/'cache';link.symlink_to(target,target_is_directory=True)
            with patch.object(setup,'CACHE',link):
                with self.assertRaisesRegex(setup.SetupError,'không an toàn'):setup.cache(dict(Version='1.0'))
            self.assertEqual(list(target.iterdir()),[])

    def test_install_retains_existing_owner_configuration_without_dpkg_prompt(self):
        from argparse import Namespace
        info=dict(path='/fixture.deb',Version='1.0',sha256='a'*64,checksum_present=True)
        with patch.object(setup,'plan',return_value={'apt_plan':'reviewed plan'}),patch.object(setup,'require_root'),patch.object(setup,'cache',return_value=Path('/root-cache/fixture.deb')),patch.object(setup,'command',return_value=(0,'','')) as command,patch.object(setup,'health'),contextlib.redirect_stdout(io.StringIO()):
            setup.install(info,Namespace(action='install',json=False,dry_run=False,yes=True))
            args=command.call_args.args[0]
            self.assertIn('Dpkg::Options::=--force-confold',args)
            self.assertIn('--no-remove',args)
            self.assertNotIn('--force-confnew',args)


if __name__=='__main__':unittest.main()
