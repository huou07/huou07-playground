import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('wg_mtu', Path(__file__).resolve().parents[1] / 'deploy/configure-wg-mtu.py')
mtu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mtu)


class WireGuardMtuTests(unittest.TestCase):
    def test_changes_only_mtu_preserving_native_keys_and_peers(self):
        config = '[Interface]\nPrivateKey = synthetic-not-a-real-key\nMTU = 1420\n\n[Peer]\nPublicKey = synthetic-public-key\nAllowedIPs = 10.8.0.2/32\n'
        self.assertEqual(mtu.replace_mtu(config, 1280), config.replace('MTU = 1420', 'MTU = 1280'))

    def test_refuses_ambiguous_or_missing_mtu_before_changes(self):
        for config in ('[Interface]\nAddress = 10.8.0.1/24\n', 'MTU = 1420\nMTU = 1400\n'):
            with self.assertRaises(ValueError):
                mtu.replace_mtu(config, 1280)


if __name__ == '__main__':
    unittest.main()
