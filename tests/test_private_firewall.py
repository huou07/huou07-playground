import subprocess
import tempfile
import unittest
from pathlib import Path

from deploy.private_firewall import PrivateFirewall, active_udp_endpoint, parse_status_rules


class FakeUfw:
    def __init__(self, rules):
        self.rules = list(rules)
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        if argv[1:] == ["status"]:
            rows = ["Status: active", "To Action From", "-- ------ ----"]
            for rule in self.rules:
                rows.append(f"{rule['port']}/{rule['protocol']} on {rule['interface']} ALLOW IN Anywhere # {rule['comment']}")
                rows.append(f"{rule['port']}/{rule['protocol']} (v6) on {rule['interface']} ALLOW IN Anywhere (v6) # {rule['comment']}")
            return subprocess.CompletedProcess(argv, 0, "\n".join(rows), "")
        if argv[1] == "allow":
            port = argv[argv.index("port") + 1]
            protocol = argv[argv.index("proto") + 1]
            interface = argv[argv.index("on") + 1]
            comment = argv[argv.index("comment") + 1]
            self.rules.extend([
                {"port": port, "protocol": protocol, "interface": interface, "comment": comment},
            ])
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[1:3] == ["--force", "delete"]:
            port = argv[argv.index("port") + 1]
            protocol = argv[argv.index("proto") + 1]
            interface = argv[argv.index("on") + 1]
            comment = argv[argv.index("comment") + 1]
            self.rules = [rule for rule in self.rules if not (
                rule["port"] == port and rule["protocol"] == protocol
                and rule["interface"] == interface and rule["comment"] == comment
            )]
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(argv, 1, "", "unexpected command")


class PrivateFirewallTests(unittest.TestCase):
    def test_parser_handles_ipv4_ipv6_and_ignores_unrelated_rules(self):
        rules = parse_status_rules("""Status: active
3080/tcp on wg0 ALLOW IN Anywhere # owner DSH access
3080/tcp (v6) on wg0 ALLOW IN Anywhere (v6) # owner DSH access
22/tcp ALLOW IN Anywhere
""")
        self.assertEqual(len(rules), 2)
        self.assertTrue(PrivateFirewall.matches(rules, 3080, "tcp", "wg0", "owner DSH access"))

    def test_tcp_reconcile_adds_configured_dsh_port_without_replacing_manual_rule(self):
        with tempfile.TemporaryDirectory() as temporary:
            manual = {"port": "3080", "protocol": "tcp", "interface": "wg0", "comment": "huou07 DSH private access"}
            runner = FakeUfw([manual])
            firewall = PrivateFirewall(Path(temporary), runner=runner)
            self.assertIn("Verified all configured TCP application ports", firewall.apply_tcp())
            self.assertIn(manual, runner.rules)
            added = [call for call in runner.calls if len(call) > 1 and call[1] == "allow"]
            self.assertNotIn("3080", [call[call.index("port") + 1] for call in added])
            self.assertEqual(manual["interface"], "wg0")
            self.assertTrue(firewall.state_path("tcp").exists())
            calls_before = len(runner.calls)
            firewall.apply_tcp()
            self.assertEqual(len([call for call in runner.calls[calls_before:] if call[1] == "allow"]), 0)

    def test_udp_migration_preserves_manual_3478_and_removes_only_recorded_stale_51820(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = FakeUfw([
                {"port": "3478", "protocol": "udp", "interface": "wlp0s20f3", "comment": "huou07 WireGuard UDP 3478"},
                {"port": "51820", "protocol": "udp", "interface": "wlp0s20f3", "comment": "huou07 WireGuard endpoint"},
            ])
            firewall = PrivateFirewall(Path(temporary), runner=runner)
            firewall.state_path("udp").write_text("wlp0s20f3 51820\n")
            firewall.apply_udp(3478, "wlp0s20f3")
            self.assertIn({"port": "3478", "protocol": "udp", "interface": "wlp0s20f3", "comment": "huou07 WireGuard UDP 3478"}, runner.rules)
            self.assertFalse(any(rule["port"] == "51820" for rule in runner.rules))
            self.assertEqual(firewall.read_state("udp"), [])

    def test_active_endpoint_is_discovered_from_listener_and_default_route(self):
        def runner(argv):
            if argv[0].endswith("wg"):
                return subprocess.CompletedProcess(argv, 0, "3478\n", "")
            return subprocess.CompletedProcess(argv, 0, "1.1.1.1 dev wlp0s20f3 src 192.0.2.4\n", "")
        self.assertEqual(active_udp_endpoint(runner), (3478, "wlp0s20f3"))


if __name__ == "__main__":
    unittest.main()
