import json
import tempfile
import unittest
from pathlib import Path

from web import private_services


class PrivateServiceConfigTests(unittest.TestCase):
    def test_shared_ports_include_dsh_for_relays_firewall_and_tunnels(self):
        services = private_services.load_services()
        dsh = next(item for item in services if item["id"] == "dsh")
        self.assertEqual((dsh["backend_port"], dsh["wireguard_port"], dsh["relay"]), (3080, 3080, True))
        self.assertIn((3080, 3080), private_services.relay_pairs())
        self.assertIn(3080, private_services.wireguard_ports())
        self.assertIn((3080, 3080), private_services.ssh_forwards())

    def test_config_rejects_invalid_ports_duplicate_wireguard_ports_and_unknown_ssh_group(self):
        data = json.loads(private_services.CONFIG.read_text())
        data["services"][1]["backend_port"] = 70000
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ports.json"
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                private_services.load_services(path)
            data = json.loads(private_services.CONFIG.read_text())
            data["services"][1]["wireguard_port"] = data["services"][0]["wireguard_port"]
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                private_services.load_services(path)
            data = json.loads(private_services.CONFIG.read_text())
            data["services"][1]["ssh_group"] = "everything"
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                private_services.load_services(path)


if __name__ == "__main__":
    unittest.main()
